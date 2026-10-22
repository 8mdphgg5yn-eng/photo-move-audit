from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from photo_audit import core
from photo_audit.core import Limits, audit, report_html
from photo_audit.demo import make_demo, png


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.a, self.b = self.root / "a", self.root / "b"
        self.a.mkdir()
        self.b.mkdir()
        self.image = png((12, 34, 56))

    def test_renamed_file_matches_content(self):
        (self.a / "原照片.png").write_bytes(self.image)
        (self.b / "new-name.png").write_bytes(self.image)
        result = audit(self.a, self.b)
        self.assertEqual(result["summary"]["matched_unique"], 1)
        self.assertFalse(result["missing"])
        self.assertEqual(result["source"]["records"][0]["sha256"], hashlib.sha256(self.image).hexdigest())

    def test_same_filename_different_bytes_is_missing_and_extra(self):
        (self.a / "photo.png").write_bytes(self.image)
        (self.b / "photo.png").write_bytes(png((50, 60, 70)))
        result = audit(self.a, self.b)
        self.assertEqual(result["summary"]["missing_unique"], 1)
        self.assertEqual(result["summary"]["extra_unique"], 1)

    def test_duplicates_do_not_require_duplicate_target_copies(self):
        for name in ("one.png", "two.png"):
            (self.a / name).write_bytes(self.image)
        (self.b / "copy.png").write_bytes(self.image)
        result = audit(self.a, self.b)
        self.assertEqual(result["summary"]["source_files"], 2)
        self.assertEqual(result["summary"]["source_unique"], 1)
        self.assertEqual(result["summary"]["matched_unique"], 1)
        self.assertEqual(result["summary"]["duplicate_copies"], 1)
        self.assertFalse(result["missing"])

    def test_multipart_export_folder_reads_all_zips_without_extraction(self):
        for index, color in enumerate(((1, 2, 3), (4, 5, 6))):
            data = png(color)
            with zipfile.ZipFile(self.a / f"takeout-{index}.zip", "w") as archive:
                archive.writestr("photos/image.png", data)
                archive.writestr("photos/image.png.json", "{}")
            (self.b / f"{index}.png").write_bytes(data)
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        result = audit(self.a, self.b)
        self.assertEqual(result["summary"]["matched_unique"], 2)
        self.assertEqual(result["source"]["stats"]["ignored"], 2)
        self.assertTrue(all(r["zip_crc_checked"] for r in result["source"]["records"]))
        self.assertEqual(before, sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")))

    def test_zip_crc_failure_is_incomplete_not_clean(self):
        path = self.a / "broken.zip"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("photo.png", self.image)
        data = bytearray(path.read_bytes())
        name_len, extra_len = struct.unpack_from("<HH", data, 26)
        data[30 + name_len + extra_len + 15] ^= 0x10
        path.write_bytes(data)
        (self.b / "photo.png").write_bytes(self.image)
        result = audit(self.a, self.b)
        self.assertFalse(result["summary"]["scan_complete"])
        self.assertTrue(any(i["code"] == "read_error" for i in result["issues"]))
        self.assertEqual(result["summary"]["matched_unique"], 0)

    def test_empty_and_wrong_signature_reported(self):
        (self.a / "empty.jpg").write_bytes(b"")
        (self.a / "bad.png").write_bytes(b"not a PNG")
        result = audit(self.a, self.b)
        self.assertEqual(sum(i["code"] == "media_invalid" for i in result["issues"]), 2)
        self.assertTrue(result["summary"]["scan_complete"])

    def test_no_pillow_reports_header_only_honestly(self):
        (self.a / "good.png").write_bytes(self.image)
        (self.b / "good.png").write_bytes(self.image)
        with patch.object(core, "Image", None):
            result = audit(self.a, self.b)
        self.assertEqual(result["source"]["records"][0]["validation"], "header_only")
        self.assertIn("not installed", result["scope"]["image_decoder"])

    @unittest.skipIf(core.Image is None, "optional Pillow not installed")
    def test_truncated_image_with_valid_header_fails_decoder(self):
        (self.a / "cut.png").write_bytes(self.image[:35])
        result = audit(self.a, self.b)
        self.assertEqual(result["source"]["records"][0]["validation"], "failed")

    def test_empty_source_never_claims_success(self):
        result = audit(self.a, self.b)
        self.assertFalse(result["summary"]["scan_complete"])
        self.assertIn("no_source_media", [i["code"] for i in result["issues"]])

    def test_unsupported_extension_is_counted_as_ignored(self):
        (self.a / "unknown.xyz").write_bytes(self.image)
        result = audit(self.a, self.b)
        self.assertEqual(result["source"]["stats"]["ignored"], 1)
        self.assertFalse(result["summary"]["scan_complete"])

    def test_overlapping_and_same_roots_rejected(self):
        for target in (self.a, self.a / "nested"):
            target.mkdir(exist_ok=True)
            with self.assertRaises(ValueError):
                audit(self.a, target)

    def test_zip_path_traversal_is_skipped_and_not_extracted(self):
        with zipfile.ZipFile(self.a / "unsafe.zip", "w") as archive:
            archive.writestr("../../escaped.png", self.image)
            archive.writestr("normal.png", self.image)
        (self.b / "normal.png").write_bytes(self.image)
        result = audit(self.a, self.b)
        self.assertFalse(result["summary"]["scan_complete"])
        self.assertEqual(result["summary"]["matched_unique"], 1)
        self.assertFalse((self.root / "escaped.png").exists())

    def test_symlinks_are_not_followed(self):
        (self.a / "link.png").symlink_to(self.root / "outside.png")
        (self.root / "outside.png").write_bytes(self.image)
        result = audit(self.a, self.b)
        self.assertFalse(result["summary"]["scan_complete"])
        self.assertEqual(result["summary"]["source_files"], 0)

    def test_total_byte_limit_stops_instead_of_repeatedly_reading(self):
        for index in range(5):
            (self.a / f"{index}.png").write_bytes(self.image)
        result = audit(self.a, self.b, limits=Limits(max_total_bytes=1))
        self.assertFalse(result["summary"]["scan_complete"])
        self.assertEqual(result["source"]["stats"]["media"], 1)
        self.assertIn("scan_error", [i["code"] for i in result["issues"]])

    def test_entry_limit_is_not_clean(self):
        for index in range(3):
            (self.a / f"{index}.png").write_bytes(self.image)
        result = audit(self.a, self.b, limits=Limits(max_entries=1))
        self.assertFalse(result["summary"]["scan_complete"])
        self.assertEqual(result["summary"]["source_files"], 1)

    def test_read_failure_is_not_reported_as_clean(self):
        (self.a / "private.png").write_bytes(self.image)
        original = core._local_open

        @contextmanager
        def opener(path):
            if path.parent == self.a.resolve():
                raise PermissionError("synthetic denial")
            with original(path) as handle:
                yield handle

        with patch.object(core, "_local_open", opener):
            result = audit(self.a, self.b)
        self.assertFalse(result["summary"]["scan_complete"])
        self.assertIn("read_error", [i["code"] for i in result["issues"]])

    def test_cancellation_preserves_partial_verdict(self):
        (self.a / "photo.png").write_bytes(self.image)
        stop = threading.Event()
        stop.set()
        result = audit(self.a, self.b, cancel=stop)
        self.assertFalse(result["summary"]["scan_complete"])
        self.assertIn("cancelled", [i["code"] for i in result["issues"]])

    def test_malicious_filename_is_escaped_in_html(self):
        name = "<img src=x onerror=alert(1)>.png"
        (self.a / name).write_bytes(self.image)
        result = audit(self.a, self.b)
        rendered = report_html(result)
        self.assertNotIn("<img src=x", rendered)
        self.assertIn("&lt;img", rendered)

    def test_synthetic_demo_has_expected_independent_counts(self):
        result = audit(*make_demo(self.root / "demo"))
        summary = result["summary"]
        self.assertEqual((summary["source_files"], summary["source_unique"],
                          summary["matched_unique"], summary["missing_unique"],
                          summary["duplicate_groups"], summary["extra_unique"],
                          summary["issue_count"]), (4, 3, 2, 1, 2, 2, 1))
        json.dumps(result)


if __name__ == "__main__":
    unittest.main()
