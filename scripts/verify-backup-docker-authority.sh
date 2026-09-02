#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

/bin/bash -n "$ROOT_DIR/scripts/backup_tools/backup_core.sh"

platform="$(/usr/bin/uname -s)"
case "$platform" in
  Darwin)
    expected_docker=/usr/local/bin/docker
    ;;
  Linux)
    expected_docker=/usr/bin/docker
    ;;
  *)
    printf '지원하지 않는 Docker authority 검증 platform입니다.\n' >&2
    exit 1
    ;;
esac

actual_docker="$(command -v docker)"
[[ "$actual_docker" == "$expected_docker" ]] || {
  printf 'Docker command path가 fixed platform authority와 다릅니다.\n' >&2
  exit 1
}
[[ -f "$expected_docker" && -x "$expected_docker" ]] || {
  printf 'Fixed Docker executable authority를 사용할 수 없습니다.\n' >&2
  exit 1
}

canonical_docker="$(python3 -B -c '
from pathlib import Path
import sys
print(Path(sys.argv[1]).resolve(strict=True))
' "$expected_docker")"
[[ "$canonical_docker" == /* ]] || {
  printf 'Docker canonical path가 absolute path가 아닙니다.\n' >&2
  exit 1
}

docker_client_version="$($expected_docker version --format '{{.Client.Version}}')"
docker_server_version="$($expected_docker version --format '{{.Server.Version}}')"
docker_compose_version="$($expected_docker compose version --short)"

cd "$ROOT_DIR"
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest \
  scripts.backup_tools.test_backup_core_docker_authority

printf 'platform=%s\n' "$platform"
printf 'docker-command-path=%s\n' "$actual_docker"
printf 'docker-canonical-path=%s\n' "$canonical_docker"
printf 'docker-client-version=%s\n' "$docker_client_version"
printf 'docker-server-version=%s\n' "$docker_server_version"
printf 'docker-compose-version=%s\n' "$docker_compose_version"
printf 'Backup Docker executable authority 검증을 통과했습니다.\n'
