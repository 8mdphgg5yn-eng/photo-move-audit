import argparse
import json
from pathlib import Path
import sys
import tempfile

from .core import audit, report_html, validate_roots
from .demo import make_demo
from .server import serve


def port_number(value):
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("端口须为 0 到 65535 的整数") from exc
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError("端口须为 0 到 65535；0 表示自动选择")
    return port


def main(argv=None):
    parser = argparse.ArgumentParser(description="照片搬家核对器：本地只读，按完整文件内容核对")
    sub = parser.add_subparsers(dest="command")
    ui = sub.add_parser("serve", help="打开本机浏览器界面")
    ui.add_argument("--port", type=port_number, default=0)
    ui.add_argument("--no-browser", action="store_true")
    check = sub.add_parser("check", help="核对两个目录或 ZIP")
    check.add_argument("source")
    check.add_argument("target")
    check.add_argument("--json", type=Path, help="另存 JSON；不覆盖现有文件")
    check.add_argument("--html", type=Path, help="另存可独立打开的 HTML 报告")
    sub.add_parser("demo", help="使用临时自制样本运行命令行演示")
    args = parser.parse_args(argv)
    if args.command in (None, "serve"):
        try:
            serve(getattr(args, "port", 0), not getattr(args, "no_browser", False))
        except (ValueError, OSError) as exc:
            print(f"无法启动本机界面：{exc}。若端口已占用，请省略 --port 或换一个端口。", file=sys.stderr)
            return 2
        return 0
    try:
        if args.command == "demo":
            with tempfile.TemporaryDirectory(prefix="photo-audit-cli-demo-") as folder:
                report = audit(*make_demo(folder))
        else:
            roots = validate_roots(args.source, args.target)
            outputs = []
            for path in (args.json, args.html):
                if path:
                    path = path.expanduser().resolve()
                    if any(path == root or root in path.parents for root in roots):
                        raise ValueError("报告须保存在来源和目标目录之外")
                    if path.exists():
                        raise FileExistsError(f"报告已存在，未覆盖：{path}")
                    outputs.append(path)
            if len(set(outputs)) != len(outputs):
                raise ValueError("JSON 与 HTML 报告不能使用同一路径")
            report = audit(*roots)
            for destination, content in ((args.json, json.dumps(report, ensure_ascii=False, indent=2)),
                                         (args.html, report_html(report))):
                if destination:
                    with destination.expanduser().open("x", encoding="utf-8") as handle:
                        handle.write(content)
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        summary = report["summary"]
        if not summary["scan_complete"]:
            return 2
        return 1 if summary["missing_unique"] or summary["issue_count"] else 0
    except (ValueError, OSError) as exc:
        print(f"无法核对：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
