#!/usr/bin/env python3

import json
import sys


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


if len(sys.argv) != 2:
    fail("검증할 Compose project 이름이 필요합니다.")

project = sys.argv[1]
containers = json.load(sys.stdin)
by_service = {
    item.get("Config", {}).get("Labels", {}).get("com.docker.compose.service"): item
    for item in containers
}
require(set(by_service) == {"web", "api", "postgres"}, "runtime container 구성이 web/api/postgres와 다릅니다.")

for service_name, item in by_service.items():
    config = item.get("Config", {})
    host = item.get("HostConfig", {})
    labels = config.get("Labels", {}) or {}
    require(labels.get("com.docker.compose.project") == project,
            f"{service_name} container가 고유 검증 project 소유가 아닙니다.")
    require(host.get("Privileged") is False, f"{service_name} container가 privileged입니다.")
    require(host.get("NetworkMode") != "host", f"{service_name} container가 host network를 사용합니다.")
    require(host.get("Init") is True, f"{service_name} container init이 비활성입니다.")
    require(host.get("RestartPolicy", {}).get("Name") == "unless-stopped",
            f"{service_name} restart policy가 적용되지 않았습니다.")
    require(host.get("PidsLimit", 0) > 0, f"{service_name} pids limit가 적용되지 않았습니다.")
    require(host.get("NanoCpus", 0) > 0, f"{service_name} CPU limit가 적용되지 않았습니다.")
    require(host.get("Memory", 0) > 0, f"{service_name} memory limit가 적용되지 않았습니다.")
    require(bool(host.get("Tmpfs")), f"{service_name} runtime tmpfs가 적용되지 않았습니다.")
    require(bool(config.get("StopSignal")), f"{service_name} stop signal이 적용되지 않았습니다.")
    require(bool(config.get("Healthcheck")), f"{service_name} runtime healthcheck가 없습니다.")
    for mount in item.get("Mounts", []) or []:
        require(mount.get("Type") != "bind", f"{service_name} runtime에 bind mount가 있습니다.")
        require("docker.sock" not in str(mount.get("Source", ""))
                and "docker.sock" not in str(mount.get("Destination", "")),
                f"{service_name} runtime에 Docker socket이 있습니다.")

for service_name in ("web", "api"):
    item = by_service[service_name]
    config = item["Config"]
    host = item["HostConfig"]
    user = str(config.get("User", ""))
    require(user not in {"", "0", "0:0", "root"}, f"{service_name} runtime user가 root입니다.")
    require(host.get("ReadonlyRootfs") is True, f"{service_name} runtime root filesystem이 writable입니다.")
    require("ALL" in (host.get("CapDrop", []) or []), f"{service_name} runtime capability drop이 누락됐습니다.")
    require("no-new-privileges:true" in (host.get("SecurityOpt", []) or []),
            f"{service_name} runtime no-new-privileges가 누락됐습니다.")
    require(not (item.get("Mounts", []) or []), f"{service_name} runtime에 persistent mount가 있습니다.")

require("no-new-privileges:true" in (by_service["postgres"]["HostConfig"].get("SecurityOpt", []) or []),
        "postgres runtime no-new-privileges가 누락됐습니다.")

web_bindings = by_service["web"]["HostConfig"].get("PortBindings", {}) or {}
require(set(web_bindings) == {"8080/tcp"}, "web runtime publish port가 정확히 하나가 아닙니다.")
published = web_bindings["8080/tcp"] or []
require(len(published) == 1 and published[0].get("HostIp") == "127.0.0.1",
        "web runtime port가 loopback에만 bind되지 않았습니다.")
for service_name in ("api", "postgres"):
    bindings = by_service[service_name]["HostConfig"].get("PortBindings", {}) or {}
    require(not bindings, f"{service_name} runtime이 host port를 publish합니다.")

postgres_mounts = by_service["postgres"].get("Mounts", []) or []
require(len(postgres_mounts) == 1, "postgres runtime data volume 수가 잘못됐습니다.")
postgres_mount = postgres_mounts[0]
require(postgres_mount.get("Type") == "volume", "postgres runtime data가 named volume이 아닙니다.")
require(postgres_mount.get("Name") == f"{project}_postgres-data",
        "postgres runtime volume이 고유 검증 project로 격리되지 않았습니다.")
require(postgres_mount.get("Destination") == "/var/lib/postgresql",
        "postgres runtime data mount 경로가 잘못됐습니다.")

expected_networks = {
    "web": {f"{project}_application"},
    "api": {f"{project}_application", f"{project}_database"},
    "postgres": {f"{project}_database"},
}
for service_name, expected in expected_networks.items():
    actual = set(by_service[service_name].get("NetworkSettings", {}).get("Networks", {}))
    require(actual == expected, f"{service_name} runtime network 경계가 잘못됐습니다.")

print("Production runtime hardening 검사를 통과했습니다.")
