#!/usr/bin/env bash
set -euo pipefail

umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

readonly AGE_VERSION="v1.3.1"
readonly AGE_LINUX_AMD64_SHA256="bdc69c09cbdd6cf8b1f333d372a1f58247b3a33146406333e30c0f26e8f51377"
readonly AGE_LINUX_ARM64_SHA256="c6878a324421b69e3e20b00ba17c04bc5c6dab0030cfe55bf8f68fa8d9e9093"
readonly AGE_RELEASE_BASE="https://github.com/FiloSottile/age/releases/download/v1.3.1"

runtime_root="$(mktemp -d "${TMPDIR:-/tmp}/our-ledger-offsite-verify.XXXXXX")"
runtime_root="$(cd "$runtime_root" && pwd -P)"
case "$runtime_root" in
  */our-ledger-offsite-verify.*) ;;
  *)
    printf 'Offsite 검증 임시 directory 경계가 잘못됐습니다.\n' >&2
    exit 1
    ;;
esac

cleanup() {
  local original_status=$?
  trap - EXIT HUP INT TERM
  case "$runtime_root" in
    */our-ledger-offsite-verify.*)
      rm -rf -- "$runtime_root"
      ;;
  esac
  exit "$original_status"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

age_binary=""
age_keygen_binary=""
if [[ -x /opt/homebrew/bin/age && -x /opt/homebrew/bin/age-keygen ]] \
  && [[ "$(/opt/homebrew/bin/age --version)" == "$AGE_VERSION" ]] \
  && [[ "$(/opt/homebrew/bin/age-keygen --version)" == "$AGE_VERSION" ]]; then
  age_binary=/opt/homebrew/bin/age
  age_keygen_binary=/opt/homebrew/bin/age-keygen
elif [[ "$(uname -s)" == Linux ]]; then
  case "$(uname -m)" in
    x86_64)
      age_arch=amd64
      expected_sha256="$AGE_LINUX_AMD64_SHA256"
      ;;
    aarch64|arm64)
      age_arch=arm64
      expected_sha256="$AGE_LINUX_ARM64_SHA256"
      ;;
    *)
      printf '지원하지 않는 Hosted age architecture입니다.\n' >&2
      exit 1
      ;;
  esac
  archive="$runtime_root/age-${AGE_VERSION}-linux-${age_arch}.tar.gz"
  curl \
    --fail \
    --location \
    --proto '=https' \
    --retry 3 \
    --silent \
    --show-error \
    --tlsv1.2 \
    --output "$archive" \
    "$AGE_RELEASE_BASE/age-${AGE_VERSION}-linux-${age_arch}.tar.gz"
  actual_sha256="$(python3 -B - "$archive" <<'PY'
import hashlib
import sys
from pathlib import Path

digest = hashlib.sha256()
with Path(sys.argv[1]).open("rb") as source:
    for block in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(block)
print(digest.hexdigest())
PY
)"
  if [[ "$actual_sha256" != "$expected_sha256" ]]; then
    printf 'Pinned age archive SHA-256이 다릅니다.\n' >&2
    exit 1
  fi
  mkdir -m 700 "$runtime_root/age-release"
  tar -xzf "$archive" -C "$runtime_root/age-release"
  age_binary="$runtime_root/age-release/age/age"
  age_keygen_binary="$runtime_root/age-release/age/age-keygen"
else
  printf 'Pinned age v1.3.1 executable을 찾을 수 없습니다.\n' >&2
  exit 1
fi

if [[ ! -x "$age_binary" || ! -x "$age_keygen_binary" ]] \
  || [[ "$($age_binary --version)" != "$AGE_VERSION" ]] \
  || [[ "$($age_keygen_binary --version)" != "$AGE_VERSION" ]]; then
  printf 'Pinned age executable authority가 잘못됐습니다.\n' >&2
  exit 1
fi

before_cache="$runtime_root/before-cache.txt"
after_cache="$runtime_root/after-cache.txt"
find "$ROOT_DIR/scripts" \
  \( -type d -name __pycache__ -o -type f -name '*.pyc' \) \
  -print | LC_ALL=C sort > "$before_cache"

bash -n "$ROOT_DIR/scripts/offsite-backup-production.sh"
OUR_LEDGER_REQUIRE_AGE_ROUNDTRIP=1 \
OUR_LEDGER_TEST_AGE_BINARY="$age_binary" \
OUR_LEDGER_TEST_AGE_KEYGEN_BINARY="$age_keygen_binary" \
PYTHONDONTWRITEBYTECODE=1 \
python3 -m unittest \
  scripts.backup_tools.test_offsite_backup

python3 -B -m scripts.backup_tools.offsite_backup --help >/dev/null
"$ROOT_DIR/scripts/offsite-backup-production.sh" --help >/dev/null

python3 -B - "$ROOT_DIR" <<'PY'
import plistlib
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
plist_path = root / "launchd" / "com.homeserver.our-ledger-offsite.plist.example"
with plist_path.open("rb") as source:
    value = plistlib.load(source)

assert value["Label"] == "com.homeserver.our-ledger.offsite"
assert value["ProgramArguments"] == [
    "/Users/homeserver/Server/scripts/offsite/offsite-our-ledger-bootstrap.sh",
    "run",
]
assert value["StartCalendarInterval"] == [
    {"Hour": 0, "Minute": 50},
    {"Hour": 6, "Minute": 50},
    {"Hour": 12, "Minute": 50},
    {"Hour": 18, "Minute": 50},
]
assert "KeepAlive" not in value
assert "EnvironmentVariables" not in value

worker = (root / "scripts" / "backup_tools" / "offsite_backup.py").read_text(
    encoding="utf-8"
)
wrapper = (root / "scripts" / "offsite-backup-production.sh").read_text(
    encoding="utf-8"
)
assert "python3 -B -m scripts.backup_tools.offsite_backup" in wrapper
assert "shell=True" not in worker
assert "AGE-SECRET-KEY-" not in worker
assert "HOMEOPS" not in worker.upper()
assert "renamex_np" in worker
assert "DARWIN_RENAME_EXCL = 0x00000004" in worker
assert "renameat2" in worker
assert "LINUX_RENAME_NOREPLACE = 1" in worker
assert "os.rename(partial_path, final_path)" not in worker
assert re.search(r"FRESHNESS_GRACE_SECONDS\s*=\s*8\s*\*\s*60\s*\*\s*60", worker)
assert "PRODUCTION_AGE_ENTRYPOINT = Path(\"/opt/homebrew/bin/age\")" in worker
assert "PRODUCTION_TAR_EXECUTABLE = Path(\"/usr/bin/bsdtar\")" in worker
PY

find "$ROOT_DIR/scripts" \
  \( -type d -name __pycache__ -o -type f -name '*.pyc' \) \
  -print | LC_ALL=C sort > "$after_cache"
if ! cmp -s "$before_cache" "$after_cache"; then
  printf 'Offsite gate가 repository에 Python bytecode residue를 만들었습니다.\n' >&2
  exit 1
fi

printf 'Encrypted offsite backup source 검증을 통과했습니다.\n'
