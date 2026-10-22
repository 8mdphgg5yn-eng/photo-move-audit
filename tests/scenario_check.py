"""Independent synthetic migration oracle and I/O check. No personal media."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import random
import tempfile
import time
import zipfile

from photo_audit import core
from photo_audit.demo import png


def payload(index):
    return png(((index >> 16) & 255, (index >> 8) & 255, index & 255))


def fingerprint_tree(root):
    return {str(path.relative_to(root)): (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
            for path in root.rglob("*") if path.is_file()}


def create_migration(root):
    source, target = root / "原始导出", root / "搬家完成"
    source.mkdir()
    target.mkdir()
    for part in range(3):
        with zipfile.ZipFile(source / f"takeout-{part}.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for index in range(part * 1000, (part + 1) * 1000):
                archive.writestr(f"Takeout/旅行 照片/原图-{index}.PNG", payload(index))
                archive.writestr(f"Takeout/旅行 照片/原图-{index}.PNG.json", json.dumps({"title": f"原图-{index}.PNG"}))
    with zipfile.ZipFile(source / "重复副本.zip", "w") as archive:
        for index in range(100):
            archive.writestr(f"收藏/副本-{index}.png", payload(index))
    for index in range(137, 3000):
        folder = target / f"重新整理 {index % 20:02}"
        folder.mkdir(exist_ok=True)
        (folder / f"renamed-{index}.png").write_bytes(payload(index))
    for index in range(137, 217):
        (target / f"重复-{index}.png").write_bytes(payload(index))
    for index in range(3000, 3045):
        (target / f"新增-{index}.png").write_bytes(payload(index))
    (target / "bad-one.jpg").write_bytes(b"not a JPEG, one")
    (target / "bad-two.jpg").write_bytes(b"not a JPEG, two")
    return source, target


def run(root):
    source, target = create_migration(root)
    before = fingerprint_tree(root)
    started = time.perf_counter()
    report = core.audit(source, target)
    elapsed = time.perf_counter() - started
    expected = {"source_files": 3100, "source_unique": 3000, "target_files": 2990,
                "matched_unique": 2863, "missing_unique": 137, "extra_unique": 47,
                "duplicate_groups": 180, "duplicate_copies": 180, "issue_count": 2,
                "scan_complete": True}
    for key, value in expected.items():
        assert report["summary"][key] == value, (key, value, report["summary"][key])
    expected_missing = {hashlib.sha256(payload(i)).hexdigest() for i in range(137)}
    assert {item["sha256"] for item in report["missing"]} == expected_missing
    assert fingerprint_tree(root) == before, "input bytes or mtime changed"
    result = {"migration": {"expected": expected, "actual": report["summary"],
                            "elapsed_seconds": round(elapsed, 3), "input_unchanged": True}}
    # A 64 MiB header-bearing synthetic file; this is an I/O test, not a playable movie.
    left, right = root / "字节源", root / "字节目标"
    left.mkdir()
    right.mkdir()
    block = random.Random(42).randbytes(1024 * 1024)
    for folder in (left, right):
        with (folder / "synthetic.mp4").open("wb") as handle:
            handle.write(b"\x00\x00\x00\x18ftyp" + block[8:])
            for _ in range(63):
                handle.write(block)
    started = time.perf_counter()
    same = core.audit(left, right)
    assert same["summary"]["matched_unique"] == 1
    with (right / "synthetic.mp4").open("r+b") as handle:
        handle.seek(32 * 1024 * 1024)
        old = handle.read(1)
        handle.seek(-1, 1)
        handle.write(bytes((old[0] ^ 1,)))
    changed = core.audit(left, right)
    assert changed["summary"]["matched_unique"] == 0
    assert changed["summary"]["missing_unique"] == 1
    assert changed["summary"]["extra_unique"] == 1
    result["full_file_io"] = {"bytes_per_file": 64 * 1024 * 1024,
                               "identical_match": True, "middle_byte_change_detected": True,
                               "elapsed_seconds_two_audits": round(time.perf_counter() - started, 3),
                               "scope": "synthetic bytes; no video decoding claim"}
    if core.Image is not None:
        a, b = root / "格式源", root / "格式目标"
        a.mkdir()
        b.mkdir()
        for fmt, extension in (("JPEG", "jpg"), ("PNG", "png"), ("GIF", "gif"),
                               ("WEBP", "webp"), ("BMP", "bmp"), ("TIFF", "tiff")):
            image = core.Image.new("RGB", (128, 96), (12, 78, 150))
            buffer = io.BytesIO()
            image.save(buffer, format=fmt)
            for folder in (a, b):
                (folder / f"test.{extension}").write_bytes(buffer.getvalue())
        formats = core.audit(a, b)
        assert formats["summary"]["matched_unique"] == 6
        assert formats["summary"]["issue_count"] == 0
        assert all(record["validation"] == "first_frame_decoded" for side in ("source", "target") for record in formats[side]["records"])
        result["image_formats"] = {"formats": ["JPEG", "PNG", "GIF", "WebP", "BMP", "TIFF"],
                                    "all_first_frames_decoded": True}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="photo-audit-scenario-") as directory:
        result = run(Path(directory))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
