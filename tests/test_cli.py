from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import socket
import unittest

from photo_audit.__main__ import main
from photo_audit.demo import make_demo, png


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.target = make_demo(self.root / "demo")

    def run_cli(self, arguments):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return main(arguments)

    def test_report_exports_and_exit_one_for_missing(self):
        output = self.root / "report.json"
        html = self.root / "report.html"
        code = self.run_cli(["check", self.source, self.target, "--json", str(output), "--html", str(html)])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.read_text())["summary"]["missing_unique"], 1)
        self.assertIn("未搬走.png", html.read_text())

    def test_existing_report_is_never_overwritten(self):
        output = self.root / "report.json"
        output.write_text("preserve me")
        self.assertEqual(self.run_cli(["check", self.source, self.target, "--json", str(output)]), 2)
        self.assertEqual(output.read_text(), "preserve me")

    def test_output_inside_input_is_rejected(self):
        output = Path(self.source) / "report.json"
        self.assertEqual(self.run_cli(["check", self.source, self.target, "--json", str(output)]), 2)
        self.assertFalse(output.exists())

    def test_complete_byte_match_exits_zero(self):
        a, b = self.root / "a", self.root / "b"
        a.mkdir()
        b.mkdir()
        (a / "first.png").write_bytes(png((1, 2, 3)))
        (b / "renamed.png").write_bytes(png((1, 2, 3)))
        self.assertEqual(self.run_cli(["check", str(a), str(b)]), 0)

    def test_empty_source_exits_two(self):
        a, b = self.root / "a", self.root / "b"
        a.mkdir()
        b.mkdir()
        self.assertEqual(self.run_cli(["check", str(a), str(b)]), 2)

    def test_occupied_port_exits_cleanly_without_traceback(self):
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen(1)
            errors = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(errors):
                code = main(["serve", "--no-browser", "--port", str(occupied.getsockname()[1])])
            self.assertEqual(code, 2)
            self.assertIn("无法启动本机界面", errors.getvalue())
            self.assertNotIn("Traceback", errors.getvalue())

    def test_invalid_port_values_have_parser_errors(self):
        for value in ("-1", "65536", "abc"):
            with self.subTest(value=value), redirect_stderr(io.StringIO()) as errors:
                with self.assertRaises(SystemExit) as stopped:
                    main(["serve", "--no-browser", "--port", value])
                self.assertEqual(stopped.exception.code, 2)
                self.assertIn("端口须为", errors.getvalue())
                self.assertNotIn("Traceback", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
