from contextlib import contextmanager
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from photo_audit import core
from photo_audit.demo import png


class ConcurrentChangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source, self.target = self.root / "source", self.root / "target"
        self.source.mkdir()
        self.target.mkdir()
        self.file = self.source / "photo.png"
        self.original = png((10, 20, 30))
        self.changed = png((40, 50, 60))
        self.file.write_bytes(self.original)
        (self.target / "renamed.png").write_bytes(self.original)

    def assert_incomplete_without_stale_match(self, result):
        self.assertFalse(result["summary"]["scan_complete"])
        self.assertEqual(result["summary"]["matched_unique"], 0)
        self.assertTrue(any(i["code"] == "file_changed" for i in result["issues"]))

    def test_replacement_after_hash_before_record_is_not_a_match(self):
        original_open = core._local_open
        replaced = False

        @contextmanager
        def replace_after_read(path):
            nonlocal replaced
            with original_open(path) as stream:
                yield stream
            if path == self.file and not replaced:
                replacement = self.source / "new-file.tmp"
                replacement.write_bytes(self.changed)
                replacement.replace(self.file)
                replaced = True

        with patch.object(core, "Image", None), patch.object(core, "_local_open", replace_after_read):
            result = core.audit(self.source, self.target)
        self.assert_incomplete_without_stale_match(result)

    @unittest.skipIf(core.Image is None, "optional Pillow not installed")
    def test_changed_during_optional_decode_is_not_a_match(self):
        decode = core._decode_image
        changed = False

        def change_before_decode(opener, cancel):
            nonlocal changed
            if not changed:
                self.file.write_bytes(self.changed)
                changed = True
            return decode(opener, cancel)

        with patch.object(core, "_decode_image", change_before_decode):
            result = core.audit(self.source, self.target)
        self.assert_incomplete_without_stale_match(result)

    def test_cancel_after_first_file_keeps_partial_result(self):
        (self.source / "second.png").write_bytes(self.changed)
        stop = threading.Event()
        calls = 0

        def progress(event):
            nonlocal calls
            if event["side"] == "source":
                calls += 1
                if calls == 2:
                    stop.set()

        result = core.audit(self.source, self.target, cancel=stop, progress=progress)
        self.assertFalse(result["summary"]["scan_complete"])
        self.assertEqual(result["summary"]["source_files"], 1)
        self.assertIn("cancelled", [issue["code"] for issue in result["issues"]])


if __name__ == "__main__":
    unittest.main()
