"""Compare media by bytes, without extracting archives or changing either input."""

from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import html
import json
import os
from pathlib import Path, PurePosixPath
import stat
import threading
from typing import Callable
import warnings
import zipfile

from . import __version__

try:
    from PIL import Image
except ImportError:
    Image = None

MEDIA = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff",
    ".heic", ".heif", ".avif", ".dng", ".cr2", ".cr3", ".nef", ".arw",
    ".raf", ".orf", ".rw2", ".mp4", ".mov", ".m4v", ".avi", ".mkv",
    ".webm", ".3gp", ".mts", ".m2ts", ".mpg", ".mpeg",
}
DECODE = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
CHUNK = 1024 * 1024
MAX_PIXELS = 80_000_000


@dataclass(frozen=True)
class Limits:
    max_entries: int = 250_000
    max_file_bytes: int = 32 * 1024**3
    max_total_bytes: int = 4 * 1024**4
    max_zip_ratio: int = 1000


class Cancelled(Exception):
    pass


class BudgetExceeded(Exception):
    pass


def _checkpoint(cancel):
    if cancel and cancel.is_set():
        raise Cancelled("用户已停止扫描")


def _fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _signature_error(ext: str, head: bytes) -> str | None:
    tests = {
        ".jpg": lambda b: b.startswith(b"\xff\xd8\xff"),
        ".jpeg": lambda b: b.startswith(b"\xff\xd8\xff"),
        ".png": lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"),
        ".gif": lambda b: b[:6] in (b"GIF87a", b"GIF89a"),
        ".webp": lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP",
        ".bmp": lambda b: b.startswith(b"BM"),
        ".tif": lambda b: b[:4] in (b"II*\0", b"MM\0*", b"II+\0", b"MM\0+"),
        ".tiff": lambda b: b[:4] in (b"II*\0", b"MM\0*", b"II+\0", b"MM\0+"),
        ".mp4": lambda b: b[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free"),
        ".mov": lambda b: b[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip", b"pnot"),
        ".m4v": lambda b: b[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free"),
        ".heic": lambda b: b[4:8] == b"ftyp",
        ".heif": lambda b: b[4:8] == b"ftyp",
        ".avif": lambda b: b[4:8] == b"ftyp",
        ".avi": lambda b: b[:4] == b"RIFF" and b[8:12] == b"AVI ",
        ".mkv": lambda b: b.startswith(b"\x1aE\xdf\xa3"),
        ".webm": lambda b: b.startswith(b"\x1aE\xdf\xa3"),
    }
    check = tests.get(ext)
    return "文件头与扩展名不符，可能是格式标注错误或文件损坏" if check and not check(head) else None


def _decode_image(opener, cancel):
    """Decode the first frame only; animations and multipage images are not fully checked."""
    _checkpoint(cancel)
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with opener() as stream:
            with Image.open(stream) as image:
                if image.width * image.height > MAX_PIXELS:
                    return "header_only", None
                image.verify()
        _checkpoint(cancel)
        with opener() as stream:
            with Image.open(stream) as image:
                image.load()
    return "first_frame_decoded", None


@contextmanager
def _local_open(path: Path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        yield stream


def _scan(root: Path, side: str, limits: Limits, cancel, progress) -> dict:
    records, issues = [], []
    stats = Counter(entries=0, media=0, ignored=0, archives=0, bytes_read=0, skipped=0)
    complete = True

    def issue(path, code, message, incomplete=False):
        nonlocal complete
        issues.append({"side": side, "path": str(path), "code": code, "message": message,
                       "incomplete": incomplete})
        if incomplete:
            complete = False

    def count_entry():
        stats["entries"] += 1
        if stats["entries"] > limits.max_entries:
            raise BudgetExceeded("条目数超过本次扫描上限")

    def media(opener, display, name, size, zip_crc=False, before=None):
        stats["media"] += 1
        if size > limits.max_file_bytes:
            stats["skipped"] += 1
            issue(display, "file_limit", "文件超过单文件读取上限", True)
            return
        progress({"side": side, "path": display, "files": len(records),
                  "bytes_read": stats["bytes_read"]})
        digest, head, actual = hashlib.sha256(), b"", 0
        ext = Path(name).suffix.lower()
        try:
            with opener() as stream:
                start = os.fstat(stream.fileno()) if before else None
                if start and _fingerprint(start) != before:
                    raise OSError("文件在读取前已发生变化")
                while True:
                    _checkpoint(cancel)
                    data = stream.read(CHUNK)
                    if not data:
                        break
                    actual += len(data)
                    stats["bytes_read"] += len(data)
                    if stats["bytes_read"] > limits.max_total_bytes:
                        raise BudgetExceeded("实际读取量超过本侧扫描上限")
                    if actual > limits.max_file_bytes:
                        raise OSError("实际读取量超过单文件上限")
                    if not head:
                        head = data[:64]
                    digest.update(data)
                if start:
                    end = os.fstat(stream.fileno())
                    if _fingerprint(end) != before:
                        raise OSError("文件在读取中发生变化，请暂停同步后重试")
            if actual != size:
                raise OSError("实际读取长度与文件记录不一致")
        except (Cancelled, BudgetExceeded):
            raise
        except (OSError, ValueError, RuntimeError, EOFError, zipfile.BadZipFile, NotImplementedError) as exc:
            issue(display, "read_error", str(exc), True)
            return
        validation = "header_only" if ext in DECODE | {".mp4", ".mov", ".m4v", ".heic", ".heif", ".avif", ".avi", ".mkv", ".webm"} else "unchecked"
        error = "文件为空" if not actual else _signature_error(ext, head)
        if not error and Image is not None and ext in DECODE:
            try:
                validation, error = _decode_image(opener, cancel)
            except Cancelled:
                raise
            except (Image.DecompressionBombWarning, Image.DecompressionBombError):
                validation = "header_only"
            except Exception as exc:
                error = f"图片解码检查未通过：{exc}"
        if before:
            try:
                if _fingerprint(Path(display).lstat()) != before:
                    raise OSError("文件在核对或图片解码过程中被替换或改写，请暂停同步后重试")
            except OSError as exc:
                issue(display, "file_changed", str(exc), True)
                return
        if error:
            validation = "failed"
            issue(display, "media_invalid", error)
        records.append({"path": display, "name": name, "size": actual,
                        "sha256": digest.hexdigest(), "validation": validation,
                        "zip_crc_checked": zip_crc})

    def archive(path: Path):
        stats["archives"] += 1
        try:
            before = path.stat()
            with _local_open(path) as handle, zipfile.ZipFile(handle) as zf:
                for index, entry in enumerate(zf.infolist()):
                    _checkpoint(cancel)
                    count_entry()
                    if entry.is_dir():
                        continue
                    name = entry.filename
                    display = f"{path}!/{name} [ZIP条目 {index + 1}]"
                    if Path(name).suffix.lower() not in MEDIA:
                        stats["ignored"] += 1
                        continue
                    if (PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
                            or "\\" in name or "\0" in name
                            or stat.S_ISLNK(entry.external_attr >> 16)):
                        stats["skipped"] += 1
                        issue(display, "unsafe_member", "跳过异常路径或符号链接条目", True)
                        continue
                    if entry.flag_bits & 1:
                        stats["skipped"] += 1
                        issue(display, "encrypted_member", "无法读取加密 ZIP 条目", True)
                        continue
                    if entry.file_size > 16 * 1024**2 and entry.file_size / max(entry.compress_size, 1) > limits.max_zip_ratio:
                        stats["skipped"] += 1
                        issue(display, "zip_ratio", "ZIP 条目压缩比超过保护上限", True)
                        continue
                    media(lambda e=entry: zf.open(e), display, PurePosixPath(name).name,
                          entry.file_size, zip_crc=True)
            after = path.stat()
            if _fingerprint(before) != _fingerprint(after):
                issue(path, "archive_changed", "ZIP 在扫描中发生变化，请重试", True)
        except (Cancelled, BudgetExceeded):
            raise
        except Exception as exc:
            issue(path, "archive_error", str(exc), True)

    def file(path: Path):
        _checkpoint(cancel)
        count_entry()
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                stats["skipped"] += 1
                issue(path, "not_regular", "跳过符号链接或非普通文件", True)
            elif path.suffix.lower() == ".zip":
                archive(path)
            elif path.suffix.lower() in MEDIA:
                before = _fingerprint(info)
                media(lambda p=path: _local_open(p), str(path), path.name, info.st_size, before=before)
            else:
                stats["ignored"] += 1
        except Cancelled:
            raise
        except OSError as exc:
            issue(path, "file_error", str(exc), True)

    try:
        if root.is_file():
            file(root)
        else:
            def walk_error(exc):
                issue(exc.filename or root, "directory_error", str(exc), True)
            for parent, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
                _checkpoint(cancel)
                dirs.sort()
                files.sort()
                for name in list(dirs):
                    path = Path(parent) / name
                    if path.is_symlink():
                        dirs.remove(name)
                        stats["skipped"] += 1
                        issue(path, "symlink_directory", "跳过符号链接目录", True)
                for name in files:
                    file(Path(parent) / name)
    except Cancelled:
        issue(root, "cancelled", "用户已停止扫描，以下结果仅覆盖已读取部分", True)
    except Exception as exc:
        issue(root, "scan_error", str(exc), True)
    return {"root": str(root), "records": records, "issues": issues,
            "stats": dict(stats), "complete": complete}


def validate_roots(source, target):
    roots = []
    for value in (source, target):
        original = Path(value).expanduser()
        if original.is_symlink():
            raise ValueError("扫描根路径不能是符号链接")
        path = original.resolve(strict=True)
        if not path.is_dir() and not (path.is_file() and path.suffix.lower() == ".zip"):
            raise ValueError("请选择目录或 ZIP 文件")
        roots.append(path)
    left, right = roots
    if left == right or left in right.parents or right in left.parents:
        raise ValueError("来源与目标不能相同，也不能互相包含")
    return left, right


def audit(source, target, *, limits=None, cancel: threading.Event | None = None,
          progress: Callable | None = None):
    """A complete scan is not proof of a complete cloud export or playable media."""
    source, target = validate_roots(source, target)
    limits, progress = limits or Limits(), progress or (lambda event: None)
    left = _scan(source, "source", limits, cancel, progress)
    right = _scan(target, "target", limits, cancel, progress)
    groups = []
    for scan in (left, right):
        grouped = defaultdict(list)
        for record in scan["records"]:
            grouped[record["sha256"]].append(record)
        groups.append(grouped)
    a, b = groups
    missing = [{"sha256": key, "files": files} for key, files in a.items() if key not in b]
    extras = [{"sha256": key, "files": files} for key, files in b.items() if key not in a]
    duplicates = [{"side": side, "sha256": key, "files": files}
                  for side, group in zip(("source", "target"), groups)
                  for key, files in group.items() if len(files) > 1]
    issues = left["issues"] + right["issues"]
    complete = left["complete"] and right["complete"]
    if not a:
        issues.append({"side": "source", "path": str(source), "code": "no_source_media",
                       "message": "未读取到可核对的来源媒体，不能据此判断搬家完成", "incomplete": True})
        complete = False
    summary = {
        "source_files": len(left["records"]), "target_files": len(right["records"]),
        "source_unique": len(a), "target_unique": len(b),
        "matched_unique": len(a.keys() & b.keys()), "missing_unique": len(missing),
        "extra_unique": len(extras), "duplicate_groups": len(duplicates),
        "duplicate_copies": sum(len(g["files"]) - 1 for g in duplicates),
        "issue_count": len(issues), "scan_complete": complete,
        "integrity": {"source": dict(Counter(r["validation"] for r in left["records"])),
                      "target": dict(Counter(r["validation"] for r in right["records"]))},
    }
    return {
        "schema_version": 1, "tool_version": __version__, "summary": summary,
        "scope": {
            "comparison": "SHA-256 of complete file bytes; equal content counts once",
            "image_decoder": f"Pillow {Image.__version__}" if Image else "not installed; header checks only",
            "image_scope": "Supported images: verify plus first-frame decode when Pillow is available; 80 megapixel cap",
            "video_scope": "No full video decoding; recognized headers only",
            "zip_scope": "Media entries only, streamed with ZIP CRC; no extraction, nested ZIPs ignored",
            "limits_per_side": asdict(limits),
            "excluded": "Non-media files (including metadata JSON), unknown extensions, empty directories",
            "not_proven": "Cloud export completeness, visual equivalence after editing, all-frame integrity, metadata/album preservation",
        },
        "source": left, "target": right,
        "missing": missing, "extras": extras, "duplicates": duplicates, "issues": issues,
    }


def report_html(report):
    def esc(value):
        return html.escape(str(value))
    s = report["summary"]
    status = "扫描完成" if s["scan_complete"] else "扫描未完成，结果仅供部分核对"
    parts = ["<!doctype html><html lang='zh-CN'><meta charset='utf-8'>",
             "<title>照片搬家核对报告</title><style>body{font:16px/1.7 system-ui;max-width:1000px;margin:40px auto;padding:24px;color:#193238}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd8d7;padding:10px;text-align:left;overflow-wrap:anywhere}h2{margin-top:40px}code{overflow-wrap:anywhere}</style>",
             f"<h1>照片搬家核对报告</h1><p>{status}</p>",
             f"<p>来源媒体 {s['source_files']} 个；不同内容 {s['source_unique']} 份；目标找到 {s['matched_unique']} 份；待找 {s['missing_unique']} 份。</p>",
             "<p>按完整文件 SHA-256 核对。不同副本数量不要求相同。结果不证明云端导出完整；不验证视频能否完整播放、所有图片帧或相册与日期保留情况。路径可能含隐私，分享前请检查。</p>",
             f"<p>来源：<code>{esc(report['source']['root'])}</code><br>目标：<code>{esc(report['target']['root'])}</code></p>"]
    for key, label in (("missing", "目标未找到的来源内容"), ("extras", "目标多出的内容"), ("duplicates", "重复内容组")):
        parts.append(f"<h2>{label}（{len(report[key])}组）</h2><table><tr><th>内容指纹</th><th>文件位置</th></tr>")
        for group in report[key]:
            paths = "<br>".join(esc(f["path"]) for f in group["files"])
            parts.append(f"<tr><td><code>{esc(group['sha256'])}</code></td><td>{paths}</td></tr>")
        parts.append("</table>")
    parts.append("<h2>异常与未完成项</h2><table><tr><th>位置</th><th>说明</th></tr>")
    for issue in report["issues"]:
        parts.append(f"<tr><td>{esc(issue['path'])}</td><td>{esc(issue['message'])}</td></tr>")
    parts.append("</table><h2>检查覆盖</h2><pre>" + esc(json.dumps({"integrity": s["integrity"], "scope": report["scope"]}, ensure_ascii=False, indent=2)) + "</pre></html>")
    return "".join(parts)
