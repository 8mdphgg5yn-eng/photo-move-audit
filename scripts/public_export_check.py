"""Check a pinned community Takeout through the CLI, using an independent oracle.

No downloads, uploads or photo_audit imports. Original bytes stay read-only; all
mutations use temporary copies. Reports and manifests are retained, not photos.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import time
import zipfile


SAMPLE_URL = "https://github.com/user-attachments/files/16448727/takeout-test.zip"
DISCUSSION_URL = "https://github.com/immich-app/immich/discussions/11500"
SAMPLE_SHA256 = "e1542f664e82147726531fb99113047227227e206e0e2c706f6357fc8cefcc2c"
# This sample has exactly two JPEGs and two MP4s. Do not reuse the application's
# extension table, traversal, hashing, grouping or summary code as the oracle.
SAMPLE_MEDIA = {".jpg", ".mp4"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventory(files):
    return [{"name": name, "bytes": len(data), "sha256": digest(data)}
            for name, data in sorted(files.items())]


def snapshot(directory):
    return {str(p.relative_to(directory)): digest(p.read_bytes())
            for p in directory.rglob("*") if p.is_file()}


def grouped(files):
    result = defaultdict(list)
    for name, data in files.items():
        result[digest(data)].append(name)
    return result


def make_folder(path, files):
    path.mkdir()
    for name, data in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def make_zip(path, files):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)


def validate_report(report, left, right):
    a, b = grouped(left), grouped(right)
    duplicates = {(side, key): len(names)
                  for side, group in (("source", a), ("target", b))
                  for key, names in group.items() if len(names) > 1}
    expected = {
        "source_files": len(left), "target_files": len(right),
        "source_unique": len(a), "target_unique": len(b),
        "matched_unique": len(a.keys() & b.keys()),
        "missing_unique": len(a.keys() - b.keys()),
        "extra_unique": len(b.keys() - a.keys()),
        "duplicate_groups": len(duplicates),
        "duplicate_copies": sum(n - 1 for n in duplicates.values()),
        "issue_count": 0, "scan_complete": True,
    }
    for key, value in expected.items():
        assert report["summary"][key] == value, (key, report["summary"][key], value)
    assert {x["sha256"] for x in report["missing"]} == a.keys() - b.keys()
    assert {x["sha256"] for x in report["extras"]} == b.keys() - a.keys()
    assert {(x["side"], x["sha256"]): len(x["files"]) for x in report["duplicates"]} == duplicates
    for side, files in (("source", left), ("target", right)):
        records = report[side]["records"]
        assert Counter((r["sha256"], r["size"]) for r in records) == Counter(
            (digest(data), len(data)) for data in files.values())
        # Resolve every reported location to an independent logical member name.
        observed = {}
        for record in records:
            location = record["path"]
            if "!/" in location:
                assert record["zip_crc_checked"] is True
                name = re.sub(r" \[ZIP条目 \d+\]$", "", location.split("!/", 1)[1])
            else:
                name = str(Path(location).relative_to(report[side]["root"]))
            observed[name] = (record["sha256"], record["size"])
        assert observed == {name: (digest(data), len(data)) for name, data in files.items()}
    return expected


def verify(args):
    original = args.archive.resolve()
    output = args.output.resolve()
    # Keep the venv executable symlink; resolving it would bypass the venv.
    args.python = args.python.expanduser().absolute()
    if output.exists():
        raise ValueError("Choose a new output directory; previous evidence is never overwritten")
    original_hash = digest(original.read_bytes())
    assert original_hash == SAMPLE_SHA256, "Sample checksum differs; review provenance before testing"
    output.mkdir(parents=True)
    with zipfile.ZipFile(original) as archive:
        assert archive.testzip() is None
        all_files = {entry.filename: archive.read(entry) for entry in archive.infolist() if not entry.is_dir()}
    assert len(all_files) == 8 and "Takeout/archive_browser.html" in all_files
    media = {name: data for name, data in all_files.items() if PurePosixPath(name).suffix.lower() in SAMPLE_MEDIA}
    assert len(media) == len(grouped(media)) == 4
    assert Counter(PurePosixPath(name).suffix.lower() for name in media) == {".jpg": 2, ".mp4": 2}
    (output / "original-manifest.json").write_text(json.dumps(inventory(all_files), indent=2), encoding="utf-8")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    results = []
    with tempfile.TemporaryDirectory(prefix="photo-audit-real-export-") as work:
        work = Path(work)
        module = subprocess.run([str(args.python), "-c",
                                 "import json,photo_audit,sys; print(json.dumps({'module':photo_audit.__file__,'version':photo_audit.__version__,'python':sys.version.split()[0]}))"],
                                cwd=work, env=env, capture_output=True, text=True, check=True)
        runtime = json.loads(module.stdout)
        # Run outside the source checkout and require an installed module.
        assert "site-packages" in Path(runtime["module"]).parts, runtime
        package_root = Path(runtime["module"]).parent
        runtime["package_files_sha256"] = {
            str(p.relative_to(package_root)): digest(p.read_bytes())
            for p in sorted(package_root.rglob("*"))
            if p.is_file() and p.suffix in {".py", ".html", ".css", ".js"}
        }
        names = sorted(media)
        jpg = next(name for name in names if name.endswith(".jpg"))
        mp4 = next(name for name in names if name.endswith(".MP4"))
        renamed = {f"改名 文件夹/照片 {index}{PurePosixPath(name).suffix}": media[name]
                   for index, name in enumerate(names)}
        missing = {name: data for name, data in media.items() if name != jpg}
        edited = dict(media)
        changed = bytearray(edited[mp4])
        changed[len(changed) // 2] ^= 1
        edited[mp4] = bytes(changed)
        assert edited[mp4][:64] == media[mp4][:64] and len(edited[mp4]) == len(media[mp4])
        combined = {name: data for name, data in edited.items() if name != jpg}
        combined["重复 副本/clip.MP4"] = media[mp4]
        # Keep the edited MP4 and a byte-identical original copy as separate
        # contents; duplicate another untouched JPEG to exercise both semantics.
        other_jpg = next(name for name in names if name.endswith(".jpg") and name != jpg)
        combined["重复 副本/photo.jpg"] = media[other_jpg]
        cases = [
            ("original_zip_to_folder", media, media),
            ("rename_chinese_spaces", media, renamed),
            ("missing_jpeg", media, missing),
            ("same_name_middle_byte_edit", media, edited),
            ("combined_changes", media, combined),
            ("empty_target", media, {}),
            ("constructed_two_parts_with_duplicates", {**media, "duplicate/source.jpg": media[jpg]},
             {**renamed, "duplicate/target.jpg": media[jpg]}),
        ]
        for case, left, right in cases:
            location = work / case
            location.mkdir()
            target = location / "target"
            make_folder(target, right)
            source = original
            if case == "constructed_two_parts_with_duplicates":
                source = location / "source-parts"
                source.mkdir()
                entries = list(left.items())
                make_zip(source / "part-001.zip", dict(entries[::2]))
                make_zip(source / "part-002.zip", dict(entries[1::2]))
            before = snapshot(location)
            case_output = output / case
            case_output.mkdir()
            command = [str(args.python), "-m", "photo_audit", "check", str(source), str(target),
                       "--json", str(case_output / "report.json"), "--html", str(case_output / "report.html")]
            if os.uname().sysname == "Darwin":
                command = ["/usr/bin/time", "-l", *command]
            started = time.perf_counter()
            checked = subprocess.run(command, cwd=work, env=env, capture_output=True, text=True, timeout=90)
            elapsed = time.perf_counter() - started
            (case_output / "cli.json").write_text(checked.stdout, encoding="utf-8")
            report = json.loads((case_output / "report.json").read_text())
            expected = validate_report(report, left, right)
            assert checked.returncode == (1 if expected["missing_unique"] else 0), checked.stderr
            assert "照片搬家核对报告" in (case_output / "report.html").read_text()
            assert snapshot(location) == before, "An input copy changed during audit"
            assert digest(original.read_bytes()) == original_hash, "Original archive changed"
            memory = re.search(r"(\d+)\s+maximum resident set size", checked.stderr)
            results.append({"case": case, "status": "passed", "expected": expected,
                            "input_copies_unchanged": True, "seconds": round(elapsed, 4),
                            "peak_rss_bytes": int(memory[1]) if memory else None,
                            "integrity": report["summary"]["integrity"],
                            "image_decoder": report["scope"]["image_decoder"]})
        damaged = work / "truncated.zip"
        damaged.write_bytes(original.read_bytes()[:original.stat().st_size // 2])
        target = work / "empty"
        target.mkdir()
        report_path = output / "truncated-report.json"
        before_damaged = digest(damaged.read_bytes())
        checked = subprocess.run([str(args.python), "-m", "photo_audit", "check", str(damaged), str(target),
                                  "--json", str(report_path)], cwd=work, env=env, capture_output=True, text=True, timeout=30)
        report = json.loads(report_path.read_text())
        assert checked.returncode == 2 and report["summary"]["scan_complete"] is False
        assert any(x["code"] == "archive_error" and x["incomplete"] for x in report["issues"])
        assert digest(damaged.read_bytes()) == before_damaged
        results.append({"case": "truncated_zip", "status": "passed", "expected_exit": 2,
                        "expected_scan_complete": False, "input_copy_unchanged": True})
    assert digest(original.read_bytes()) == original_hash
    result = {"status": "passed", "sample": {"url": SAMPLE_URL, "discussion": DISCUSSION_URL,
               "sha256": original_hash, "archive_bytes": original.stat().st_size,
               "entries": len(all_files), "media_files": len(media),
               "media_bytes": sum(len(data) for data in media.values()), "zip_crc": "passed",
               "provenance": "Public user-shared Takeout bug reproduction sample; not independently exported by us",
               "permission_scope": "Shared as Test Sample for issue reproduction; no blanket redistribution license established"},
              "runtime": runtime, "original_unchanged": True, "cases": results,
              "script_sha256": digest(Path(__file__).read_bytes()),
              "limits": ["One small 2024 community sample, not a large personal library",
                         "Constructed multi-part case uses real media bytes but is not a Google-generated split export",
                         "No full video decoding, cloud completeness, albums or date metadata validation"]}
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": result["status"], "version": runtime["version"], "python": runtime["python"],
            "cases_passed": len(results), "original_unchanged": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True, help="Interpreter with an installed photo-move-audit wheel")
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(verify(parser.parse_args()), ensure_ascii=False, indent=2))
