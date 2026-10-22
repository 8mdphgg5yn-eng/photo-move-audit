import json
import threading
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from photo_audit.server import make_server
from photo_audit.core import audit
from photo_audit.demo import make_demo


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.server.app.close()

    def request(self, path, data=None, headers=None, token=True):
        values = {"X-Photo-Audit-Token": self.server.app.token} if token else {}
        values.update(headers or {})
        body = json.dumps(data).encode() if data is not None else None
        return urlopen(Request(self.base + path, body, values), timeout=5)

    def test_static_page_and_no_remote_assets(self):
        with self.request("/", token=False) as response:
            page = response.read().decode()
            self.assertIn("照片搬家核对器", page)
            self.assertNotIn("https://", page)
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    def test_api_rejects_absent_token(self):
        with self.assertRaises(HTTPError) as error:
            self.request("/api/demo", {}, token=False)
        self.addCleanup(error.exception.close)
        self.assertEqual(error.exception.code, 403)

    def test_cross_origin_rejected_even_with_token(self):
        with self.assertRaises(HTTPError) as error:
            self.request("/api/demo", {}, headers={"Origin": "https://outside.example"})
        self.addCleanup(error.exception.close)
        self.assertEqual(error.exception.code, 403)

    def test_foreign_host_rejected(self):
        with self.assertRaises(HTTPError) as error:
            self.request("/", headers={"Host": "outside.example"})
        self.addCleanup(error.exception.close)
        self.assertEqual(error.exception.code, 403)

    def test_static_traversal_rejected(self):
        with self.assertRaises(HTTPError) as error:
            self.request("/../core.py")
        self.addCleanup(error.exception.close)
        self.assertEqual(error.exception.code, 404)

    def test_demo_job_results_and_downloads(self):
        with self.request("/api/demo", {}) as response:
            roots = json.load(response)
        with self.request("/api/jobs", roots) as response:
            key = json.load(response)["id"]
        for _ in range(100):
            with self.request(f"/api/jobs/{key}") as response:
                result = json.load(response)
            if result["state"] != "running":
                break
            time.sleep(.02)
        self.assertEqual(result["state"], "done")
        self.assertEqual(result["summary"]["missing_unique"], 1)
        with self.request(f"/api/jobs/{key}/items?kind=missing") as response:
            self.assertEqual(json.load(response)["total"], 1)
        with self.request(f"/api/jobs/{key}/report.json") as response:
            self.assertEqual(json.load(response)["summary"]["matched_unique"], 2)
            self.assertIn("attachment", response.headers["Content-Disposition"])
        with self.request(f"/api/jobs/{key}/report.html") as response:
            self.assertIn("未搬走.png", response.read().decode())

    def test_bad_input_has_clear_error(self):
        with self.assertRaises(HTTPError) as error:
            self.request("/api/jobs", {"source": "/no-such-source", "target": "/no-such-target"})
        self.addCleanup(error.exception.close)
        self.assertEqual(error.exception.code, 400)

    def test_mid_scan_cancel_and_parallel_job_rejection(self):
        started = threading.Event()

        def controlled(source, target, *, cancel, progress):
            started.set()
            cancel.wait(timeout=3)
            return audit(source, target, cancel=cancel, progress=progress)

        with tempfile.TemporaryDirectory() as directory:
            source, target = make_demo(directory)
            with patch("photo_audit.server.audit", controlled):
                with self.request("/api/jobs", {"source": source, "target": target}) as response:
                    key = json.load(response)["id"]
                self.assertTrue(started.wait(timeout=1))
                with self.assertRaises(HTTPError) as error:
                    self.request("/api/jobs", {"source": source, "target": target})
                self.addCleanup(error.exception.close)
                self.assertEqual(error.exception.code, 400)
                with self.request(f"/api/jobs/{key}/cancel", {}) as response:
                    self.assertTrue(json.load(response)["ok"])
                for _ in range(100):
                    with self.request(f"/api/jobs/{key}") as response:
                        result = json.load(response)
                    if result["state"] != "running":
                        break
                    time.sleep(.02)
                self.assertEqual(result["state"], "done")
                self.assertFalse(result["summary"]["scan_complete"])

    def test_non_ascii_token_is_rejected_instead_of_crashing(self):
        with self.assertRaises(HTTPError) as error:
            self.request("/api/session", headers={"X-Photo-Audit-Token": "\xff"}, token=False)
        self.addCleanup(error.exception.close)
        self.assertEqual(error.exception.code, 403)

    def test_session_retains_last_result_after_invalid_start(self):
        with self.request("/api/demo", {}) as response:
            roots = json.load(response)
        with self.request("/api/jobs", roots) as response:
            key = json.load(response)["id"]
        for _ in range(100):
            with self.request(f"/api/jobs/{key}") as response:
                status = json.load(response)
            if status["state"] == "done":
                break
            time.sleep(.02)
        self.assertEqual(status["state"], "done")
        with self.assertRaises(HTTPError) as error:
            self.request("/api/jobs", {"source": "/no-such-source", "target": "/no-such-target"})
        self.addCleanup(error.exception.close)
        with self.request("/api/session") as response:
            session = json.load(response)
        self.assertEqual(session["latest"]["id"], key)
        self.assertEqual(session["latest"]["source"], status["source"])
        self.assertEqual(session["latest"]["state"], "done")

    def test_picker_requires_token_and_preserves_cancel(self):
        with patch("photo_audit.server.picker.choose_path", return_value=None) as choose:
            with self.assertRaises(HTTPError) as error:
                self.request("/api/pick", {"kind": "folder"}, token=False)
            self.addCleanup(error.exception.close)
            choose.assert_not_called()
            with self.request("/api/pick", {"kind": "folder"}) as response:
                self.assertEqual(json.load(response), {"path": None, "cancelled": True})
            choose.assert_called_once_with("folder", None)


if __name__ == "__main__":
    unittest.main()
