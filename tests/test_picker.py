from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from photo_audit import picker


class PickerTests(unittest.TestCase):
    def choose(self, kind, result):
        with patch.object(picker, "available", return_value=True), patch.object(picker.subprocess, "run", return_value=result):
            return picker.choose_path(kind)

    def test_folder_with_spaces_and_unicode_is_preserved(self):
        with tempfile.TemporaryDirectory(prefix="照片 选择 ") as folder:
            result = SimpleNamespace(returncode=0, stdout=folder + "/\n", stderr="")
            self.assertEqual(self.choose("folder", result), str(Path(folder)))

    def test_zip_is_selected_without_opening_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.ZIP"
            path.write_bytes(b"not read by the picker")
            result = SimpleNamespace(returncode=0, stdout=str(path) + "\n", stderr="")
            self.assertEqual(self.choose("zip", result), str(path))

    def test_cancel_returns_none(self):
        self.assertIsNone(self.choose("folder", SimpleNamespace(returncode=1, stdout="", stderr="User canceled. (-128)")))

    def test_unsupported_platform_does_not_launch_process(self):
        with patch.object(picker, "available", return_value=False), patch.object(picker.subprocess, "run") as run:
            with self.assertRaises(ValueError):
                picker.choose_path("folder")
            run.assert_not_called()

    def test_timeout_has_actionable_error(self):
        with patch.object(picker, "available", return_value=True), patch.object(picker.subprocess, "run", side_effect=subprocess.TimeoutExpired("osascript", 300)):
            with self.assertRaisesRegex(ValueError, "等待超时"):
                picker.choose_path("folder")

    def test_invalid_kind_does_not_launch_process(self):
        with patch.object(picker.subprocess, "run") as run:
            with self.assertRaises(ValueError):
                picker.choose_path("script")
            run.assert_not_called()

    def test_initial_directory_is_passed_as_argument_not_script_text(self):
        with tempfile.TemporaryDirectory(prefix="照片 ' test ") as folder:
            result = SimpleNamespace(returncode=0, stdout=folder + "\n", stderr="")
            with patch.object(picker, "available", return_value=True), patch.object(picker.subprocess, "run", return_value=result) as run:
                self.assertEqual(picker.choose_path("folder", folder), folder)
                command = run.call_args.args[0]
                self.assertEqual(command[-1], str(Path(folder).resolve()))
                self.assertNotIn(folder, command[2])

    def test_selected_zip_uses_parent_as_initial_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.zip"
            path.write_bytes(b"dummy")
            result = SimpleNamespace(returncode=1, stdout="", stderr="cancelled (-128)")
            with patch.object(picker, "available", return_value=True), patch.object(picker.subprocess, "run", return_value=result) as run:
                self.assertIsNone(picker.choose_path("zip", str(path)))
                self.assertEqual(run.call_args.args[0][-1], str(Path(folder).resolve()))


if __name__ == "__main__":
    unittest.main()
