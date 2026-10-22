#!/bin/zsh
set -eu
cd -- "${0:A:h}"
if ! command -v python3 >/dev/null 2>&1; then
  print '需要 Python 3.10 或更新版本。安装说明见本目录 README.md。'
  if [[ -t 0 ]]; then read -r '?按回车退出。'; fi
  exit 1
fi
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  print '当前 Python 版本过低，需要 Python 3.10 或更新版本。'
  if [[ -t 0 ]]; then read -r '?按回车退出。'; fi
  exit 1
fi
photo_audit_status=0
python3 -m photo_audit serve "$@" || photo_audit_status=$?
if (( photo_audit_status != 0 )) && [[ -t 0 ]]; then
  read -r '?启动未完成，请查看上方原因。按回车退出。'
fi
exit "$photo_audit_status"
