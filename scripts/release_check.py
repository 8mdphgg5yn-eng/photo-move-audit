"""Offline build, clean installation and source ZIP smoke checks. Never publishes."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import select
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOP_FILES = ("README.md", "LICENSE", "CONTRIBUTING.md", "CHANGELOG.md", "pyproject.toml", "MANIFEST.in",
             ".gitignore", "启动照片核对器.command")
TOP_DIRS = ("photo_audit", "tests", "docs", "scripts")


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(data)
    return result.hexdigest()


def public_files(root):
    result = [root / name for name in TOP_FILES]
    for directory in TOP_DIRS:
        result.extend(p for p in (root / directory).rglob("*")
                      if p.is_file() and "__pycache__" not in p.parts
                      and p.suffix != ".pyc" and p.name != ".DS_Store")
    return sorted(result)


def service_check(command, cwd, env, browser_command=None, browser_output=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        if not select.select([process.stdout], [], [], 10)[0]:
            raise RuntimeError("Local service did not start within ten seconds")
        first = process.stdout.readline()
        found = re.search(r"http://127\.0\.0\.1:\d+/#([\w-]+)", first)
        if not found:
            raise RuntimeError("Local service did not print a session URL")
        origin = found.group(0).split("/#")[0]
        token = found.group(1)

        def request(path, data=None):
            payload = json.dumps(data).encode() if data is not None else None
            request = urllib.request.Request(origin + path, payload,
                                             {"X-Photo-Audit-Token": token})
            with opener.open(request, timeout=5) as response:
                return response.read()

        for path, marker in (("/", "照片搬家核对器"), ("/app.js", "initialize"), ("/style.css", ".path-card")):
            assert marker in request(path).decode(), path
        session = json.loads(request("/api/session"))
        browser_status = "not_run"
        if browser_command:
            browser_env = env.copy()
            browser_env["PHOTO_AUDIT_TEST_OUTPUT"] = str(browser_output)
            checked = subprocess.run([*browser_command, found.group(0)], cwd=cwd, env=browser_env,
                                     capture_output=True, text=True, timeout=120)
            browser_output.mkdir(parents=True, exist_ok=True)
            (browser_output / "browser-check.log").write_text(checked.stdout + checked.stderr, encoding="utf-8")
            if checked.returncode:
                raise RuntimeError("Installed-package browser check failed; inspect browser-check.log")
            browser_status = "passed"
        demo = json.loads(request("/api/demo", {}))
        job = json.loads(request("/api/jobs", demo))["id"]
        for _ in range(100):
            status = json.loads(request(f"/api/jobs/{job}"))
            if status["state"] != "running":
                break
            time.sleep(.05)
        assert status["state"] == "done", status["state"]
        assert status["summary"]["missing_unique"] == 1
        assert status["summary"]["matched_unique"] == 2
        report = json.loads(request(f"/api/jobs/{job}/report.json"))
        assert report["tool_version"] == session["version"]
        assert "未搬走.png" in request(f"/api/jobs/{job}/report.html").decode()
        return {"version": session["version"], "static_assets": "passed", "demo_api": "passed",
                "html_json_download": "passed", "service_shutdown": "passed", "browser": browser_status}
    finally:
        try:
            os.killpg(process.pid, signal.SIGINT)
        except ProcessLookupError:
            pass
        try:
            process.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.communicate(timeout=3)
            raise RuntimeError("Service did not exit after SIGINT")


def verify(args):
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Use a new output directory; existing evidence is never overwritten")
    output.mkdir(parents=True)
    logs = []
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.update(UV_OFFLINE="1", UV_NO_CONFIG="1", UV_PYTHON_DOWNLOADS="never")
    version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M)[1]

    def run(command, cwd, expected=(0,)):
        completed = subprocess.run([str(x) for x in command], cwd=cwd, env=env,
                                   capture_output=True, text=True, timeout=120)
        logs.append({"command": [str(x) for x in command], "returncode": completed.returncode,
                     "stdout": completed.stdout, "stderr": completed.stderr})
        (output / "private-build-log.json").write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")
        if completed.returncode not in expected:
            raise RuntimeError("Command failed; inspect private-build-log.json")
        return completed

    with tempfile.TemporaryDirectory(prefix="photo-audit-build-") as scratch:
        scratch = Path(scratch)
        stage = scratch / f"photo-move-audit-{version}"
        stage.mkdir()
        for path in public_files(ROOT):
            relative = path.relative_to(ROOT)
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        build_flags = [args.uv, "build", "--offline", "--no-config", "--no-python-downloads",
                       "--no-build-isolation", "--python", args.build_python,
                       "--out-dir", str(output)]
        run([*build_flags, "--sdist", str(stage)], scratch)
        sdist, = output.glob("*.tar.gz")
        run([*build_flags, "--wheel", str(sdist)], scratch)
        wheel, = output.glob("*.whl")
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            for name in ("photo_audit/web/index.html", "photo_audit/web/app.js", "photo_audit/web/style.css", "photo_audit/picker.py"):
                assert name in names, name
            assert any(name.endswith("/licenses/LICENSE") for name in names)
            assert not any("artifacts/" in name or "__pycache__" in name for name in names)
        with tarfile.open(sdist) as archive:
            names = archive.getnames()
            for suffix in ("/启动照片核对器.command", "/tests/browser-check.cjs", "/MANIFEST.in"):
                assert any(name.endswith(suffix) for name in names), suffix
        source_zip = output / f"photo-move-audit-{version}-source.zip"
        with zipfile.ZipFile(source_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in public_files(stage):
                archive.write(path, Path(stage.name) / path.relative_to(stage))
        installations = []
        for index, interpreter in enumerate(args.runtime_python or [sys.executable]):
            venv = scratch / f"clean-venv-{index}"
            run([interpreter, "-m", "venv", "--without-pip", str(venv)], scratch)
            python = venv / "bin" / "python"
            entry = venv / "bin" / "photo-audit"
            run([args.uv, "pip", "install", "--offline", "--no-index", "--no-config", "--no-deps",
                 "--python", str(python), str(wheel)], scratch)
            imported = run([python, "-c", "import photo_audit,sys,json; print(json.dumps({'version':photo_audit.__version__,'module':photo_audit.__file__,'python':sys.version.split()[0]}))"], scratch)
            info = json.loads(imported.stdout)
            assert Path(info["module"]).resolve().is_relative_to(venv.resolve()), "Imported source checkout instead of installed package"
            assert info["version"] == version
            run([entry, "--help"], scratch)
            demo = json.loads(run([entry, "demo"], scratch, expected=(1,)).stdout)
            assert demo["missing_unique"] == 1 and demo["matched_unique"] == 2
            browser = [args.node, str(stage / "tests" / "browser-check.cjs")] if args.browser_check and index == 0 else None
            service = service_check([str(entry), "serve", "--no-browser"], scratch, env,
                                    browser, output / "installed-browser")
            installations.append({"python": info["python"], "isolated_import": "passed",
                                  "cli": "passed", "service": service})
        source_result = {"status": "not_run", "reason": "native .command launcher is macOS only"}
        if sys.platform == "darwin":
            extracted = scratch / "source-unpacked"
            extracted.mkdir()
            run(["/usr/bin/ditto", "-x", "-k", str(source_zip), str(extracted)], scratch)
            launch = extracted / stage.name / "启动照片核对器.command"
            assert os.access(launch, os.X_OK), "Executable mode was lost in source ZIP"
            service = service_check([str(launch), "--no-browser"], scratch, env)
            source_result = {"status": "passed", "executable_mode": "preserved", "service": service}
        artifacts = {path.name: digest(path) for path in (wheel, sdist, source_zip)}
        (output / "SHA256SUMS").write_text("".join(f"{value}  {name}\n" for name, value in artifacts.items()), encoding="utf-8")
        result = {"version": version, "build": "passed", "wheel_built_from_sdist": True,
                  "network": "offline", "installations": installations,
                  "source_zip": source_result, "artifacts": artifacts,
                  "gate_scope": "Distribution only; native dialogs and real exports require separate evidence in release-gate.json",
                  "scope": "Fresh virtual environments on this Mac; not separate physical machines"}
        (output / "installation-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-python", required=True, help="Existing interpreter containing setuptools>=77 and wheel")
    parser.add_argument("--runtime-python", action="append", help="Existing interpreter for a new clean venv; repeatable")
    parser.add_argument("--uv", default=shutil.which("uv") or "uv")
    parser.add_argument("--browser-check", action="store_true", help="Run distributed browser checks against the first clean installation")
    parser.add_argument("--node", default=shutil.which("node") or "node")
    options = parser.parse_args()
    print(json.dumps(verify(options), ensure_ascii=False, indent=2))
