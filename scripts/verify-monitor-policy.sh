#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONITOR_PLIST="$ROOT_DIR/launchd/com.homeserver.our-ledger-monitor.plist.example"
BACKUP_PLIST="$ROOT_DIR/launchd/com.homeserver.our-ledger-backup.plist.example"

export PYTHONDONTWRITEBYTECODE=1

cd "$ROOT_DIR"

LEGACY_MONITOR_PATTERN='Uptime K[u]ma|STATUS_HEART[B]EAT_URL|/api/pu[s]h/|K[u]ma up|K[u]ma down|K[u]ma adapter'
if git grep -n -E "$LEGACY_MONITOR_PATTERN" -- .; then
  echo "legacy direct monitor 계약이 tracked repository에 남아 있습니다." >&2
  exit 1
fi
if git grep -n -E 'urllib[.](error|parse|request)' -- scripts/status_tools/monitor_worker.py; then
  echo "monitor worker에 direct HTTP sender가 남아 있습니다." >&2
  exit 1
fi

python3 -B -m unittest scripts.status_tools.test_monitor_policy
python3 -B -m unittest scripts.backup_tools.test_backup_artifact

bash -n "$ROOT_DIR/scripts/monitor-production.sh"
"$ROOT_DIR/scripts/monitor-production.sh" --help >/dev/null

python3 -B - "$MONITOR_PLIST" "$BACKUP_PLIST" <<'PY'
import pathlib
import plistlib
import sys

monitor_path = pathlib.Path(sys.argv[1])
backup_path = pathlib.Path(sys.argv[2])
with monitor_path.open("rb") as source:
    monitor = plistlib.load(source)
with backup_path.open("rb") as source:
    backup = plistlib.load(source)

assert monitor == {
    "Label": "com.homeserver.our-ledger.monitor",
    "ProgramArguments": [
        "/Users/homeserver/Server/scripts/monitor/monitor-our-ledger-bootstrap.sh"
    ],
    "StartInterval": 60,
    "StandardOutPath": "/Users/homeserver/Library/Logs/our-ledger-monitor.out.log",
    "StandardErrorPath": "/Users/homeserver/Library/Logs/our-ledger-monitor.err.log",
}
assert "KeepAlive" not in monitor

assert backup == {
    "Label": "com.homeserver.our-ledger.backup",
    "ProgramArguments": [
        "/Users/homeserver/Server/scripts/backup/backup-our-ledger-bootstrap.sh"
    ],
    "StartCalendarInterval": [
        {"Hour": 0, "Minute": 35},
        {"Hour": 6, "Minute": 35},
        {"Hour": 12, "Minute": 35},
        {"Hour": 18, "Minute": 35},
    ],
    "StandardOutPath": "/Users/homeserver/Library/Logs/our-ledger-backup.out.log",
    "StandardErrorPath": "/Users/homeserver/Library/Logs/our-ledger-backup.err.log",
}
assert "KeepAlive" not in backup
for value in monitor["ProgramArguments"] + backup["ProgramArguments"]:
    assert value.startswith("/Users/homeserver/Server/scripts/")
    assert not value.startswith(str(pathlib.Path.cwd()))
PY

if command -v plutil >/dev/null 2>&1; then
  plutil -lint "$MONITOR_PLIST" "$BACKUP_PLIST" >/dev/null
fi

if find "$ROOT_DIR/scripts" -type f -name '*.pyc' -print | grep -q .; then
  echo "monitor policy 검증 중 Python bytecode가 생성됐습니다." >&2
  exit 1
fi

echo "Monitor policy/HomeOps synthetic 검증을 통과했습니다."
