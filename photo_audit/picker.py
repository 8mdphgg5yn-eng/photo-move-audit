"""Native macOS selection, invoked only by an explicit button click."""

from pathlib import Path
import subprocess
import sys

SCRIPTS = {
    "folder": 'activate\nPOSIX path of (choose folder with prompt "选择要核对的文件夹")',
    "zip": 'activate\nPOSIX path of (choose file with prompt "选择 ZIP 文件" of type {"zip"})',
}

LOCATION_SCRIPTS = {
    "folder": 'on run argv\nactivate\nreturn POSIX path of (choose folder with prompt "选择要核对的文件夹" default location (POSIX file (item 1 of argv)))\nend run',
    "zip": 'on run argv\nactivate\nreturn POSIX path of (choose file with prompt "选择 ZIP 文件" of type {"zip"} default location (POSIX file (item 1 of argv)))\nend run',
}


def available():
    return sys.platform == "darwin" and Path("/usr/bin/osascript").is_file()


def choose_path(kind, initial_directory=None):
    if kind not in SCRIPTS:
        raise ValueError("请选择文件夹或 ZIP")
    if not available():
        raise ValueError("此系统不支持原生选择窗口，请粘贴完整路径")
    command = ["/usr/bin/osascript", "-e", SCRIPTS[kind]]
    if initial_directory:
        initial = Path(initial_directory).expanduser()
        if initial.is_file():
            initial = initial.parent
        if initial.is_dir():
            command = ["/usr/bin/osascript", "-e", LOCATION_SCRIPTS[kind], str(initial.resolve())]
    try:
        result = subprocess.run(command,
                                capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("选择窗口等待超时，请重试或粘贴完整路径") from exc
    if result.returncode:
        if "(-128)" in result.stderr:
            return None
        raise ValueError("无法打开选择窗口，请粘贴完整路径。" + result.stderr.strip()[:200])
    value = result.stdout.rstrip("\r\n")
    if not value:
        raise ValueError("没有获得文件路径，请重试")
    path = Path(value)
    if kind == "folder" and not path.is_dir():
        raise ValueError("选择的文件夹不存在或无法访问")
    if kind == "zip" and not (path.is_file() and path.suffix.lower() == ".zip"):
        raise ValueError("请选择 ZIP 文件")
    return str(path)
