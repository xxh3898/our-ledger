#!/usr/bin/env python3

import json
import os
import sys


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def mounts(service: dict) -> list[dict]:
    return service.get("volumes", []) or []


def network_names(service: dict) -> set[str]:
    networks = service.get("networks", {}) or {}
    return set(networks if isinstance(networks, dict) else networks)


config = json.load(sys.stdin)
services = config.get("services", {})
require(
    set(services) == {"web", "api", "api-migration", "api-bootstrap", "postgres"},
    "production service는 web/api/api-migration/api-bootstrap/postgres만 허용합니다.",
)

web = services["web"]
api = services["api"]
migration = services["api-migration"]
bootstrap = services["api-bootstrap"]
postgres = services["postgres"]

for service_name, service in services.items():
    require("build" not in service, f"{service_name} production service는 host build를 포함할 수 없습니다.")
    require(not service.get("privileged", False), f"{service_name} service는 privileged일 수 없습니다.")
    require(service.get("network_mode") != "host", f"{service_name} service는 host network를 사용할 수 없습니다.")
    require(service.get("init") is True, f"{service_name} service는 init을 활성화해야 합니다.")
    if service_name in {"api-migration", "api-bootstrap"}:
        require(service.get("restart") == "no", f"{service_name}은 one-shot restart policy여야 합니다.")
        require(not service.get("healthcheck"), f"{service_name}에는 healthcheck가 없어야 합니다.")
    else:
        require(service.get("restart") == "unless-stopped", f"{service_name} restart policy가 누락됐습니다.")
        require(bool(service.get("healthcheck")), f"{service_name} healthcheck가 누락됐습니다.")
    require(service.get("pids_limit", 0) > 0, f"{service_name} pids_limit가 누락됐습니다.")
    require(float(service.get("cpus", 0)) > 0, f"{service_name} CPU limit가 누락됐습니다.")
    require(int(service.get("mem_limit", 0)) > 0, f"{service_name} memory limit가 누락됐습니다.")
    require(bool(service.get("tmpfs")), f"{service_name} writable tmpfs가 누락됐습니다.")
    require(bool(service.get("stop_grace_period")), f"{service_name} stop grace period가 누락됐습니다.")
    for mount in mounts(service):
        require(mount.get("type") != "bind", f"{service_name}에 host bind mount가 있습니다.")
        source = str(mount.get("source", ""))
        target = str(mount.get("target", ""))
        require("docker.sock" not in source and "docker.sock" not in target,
                f"{service_name}에 Docker socket mount가 있습니다.")

for service_name, service in (
    ("web", web),
    ("api", api),
    ("api-migration", migration),
    ("api-bootstrap", bootstrap),
):
    require(service.get("read_only") is True, f"{service_name} root filesystem은 read-only여야 합니다.")
    require("ALL" in (service.get("cap_drop", []) or []), f"{service_name}는 Linux capability를 모두 drop해야 합니다.")
    security_options = service.get("security_opt", []) or []
    require("no-new-privileges:true" in security_options,
            f"{service_name} no-new-privileges 설정이 누락됐습니다.")
    require(not mounts(service), f"{service_name}에는 persistent mount가 없어야 합니다.")

require("no-new-privileges:true" in (postgres.get("security_opt", []) or []),
        "postgres no-new-privileges 설정이 누락됐습니다.")
require(web.get("depends_on", {}).get("api", {}).get("condition") == "service_healthy",
        "web은 healthy api에 의존해야 합니다.")
require(api.get("depends_on", {}).get("postgres", {}).get("condition") == "service_healthy",
        "api는 healthy postgres에 의존해야 합니다.")
require(migration.get("depends_on", {}).get("postgres", {}).get("condition") == "service_healthy",
        "api-migration은 healthy postgres에 의존해야 합니다.")
require(bootstrap.get("depends_on", {}).get("postgres", {}).get("condition") == "service_healthy",
        "api-bootstrap은 healthy postgres에 의존해야 합니다.")

web_ports = web.get("ports", []) or []
require(len(web_ports) == 1, "web은 정확히 한 개 port만 publish해야 합니다.")
web_port = web_ports[0]
require(int(web_port.get("target", 0)) == 8080, "web publish target은 8080이어야 합니다.")
require(web_port.get("host_ip") == "127.0.0.1", "web port는 127.0.0.1에만 bind해야 합니다.")
require(web_port.get("protocol") == "tcp", "web publish protocol은 tcp여야 합니다.")
require(not (api.get("ports", []) or []), "api는 host port를 publish할 수 없습니다.")
require(not (migration.get("ports", []) or []), "api-migration은 host port를 publish할 수 없습니다.")
require(not (bootstrap.get("ports", []) or []), "api-bootstrap은 host port를 publish할 수 없습니다.")
require(not (postgres.get("ports", []) or []), "postgres는 host port를 publish할 수 없습니다.")

expected_postgres_image = (
    "postgres:18.6-alpine3.23@sha256:"
    "697c180dbf244d3ce4a8f4cbc0156cde840af055c1bf8b76aebe422a4822086f"
)
require(postgres.get("image") == expected_postgres_image, "PostgreSQL image tag/digest가 계약과 다릅니다.")
for service_name, service in (
    ("web", web),
    ("api", api),
    ("api-migration", migration),
    ("api-bootstrap", bootstrap),
):
    image = str(service.get("image", ""))
    require(bool(image), f"{service_name} image가 비어 있습니다.")
    require(not image.endswith(":latest"), f"{service_name} image에 latest tag를 사용할 수 없습니다.")
require(migration.get("image") == api.get("image"), "api와 api-migration은 동일한 candidate image를 사용해야 합니다.")
require(bootstrap.get("image") == api.get("image"), "api와 api-bootstrap은 동일한 candidate image를 사용해야 합니다.")

api_environment = api.get("environment", {}) or {}
required_api_environment = {
    "SPRING_PROFILES_ACTIVE",
    "SPRING_DATASOURCE_URL",
    "SPRING_DATASOURCE_USERNAME",
    "SPRING_DATASOURCE_PASSWORD",
    "CLOUDFLARE_ACCESS_ISSUER",
    "CLOUDFLARE_ACCESS_JWK_SET_URI",
    "CLOUDFLARE_ACCESS_AUDIENCE",
    "OUR_LEDGER_BOOTSTRAP_ENABLED",
    "OUR_LEDGER_RECURRING_SCHEDULER_ENABLED",
    "OUR_LEDGER_RECURRING_INITIAL_DELAY_MS",
    "OUR_LEDGER_RECURRING_POLL_DELAY_MS",
}
require(required_api_environment <= set(api_environment), "api production 환경변수 계약이 누락됐습니다.")
require(api_environment["SPRING_PROFILES_ACTIVE"] == "production", "api는 production profile만 활성화해야 합니다.")
require(api_environment["OUR_LEDGER_BOOTSTRAP_ENABLED"] == "false", "production bootstrap은 false여야 합니다.")
require(api_environment["OUR_LEDGER_RECURRING_SCHEDULER_ENABLED"] == "true", "production recurring scheduler는 true여야 합니다.")
require(str(api_environment["OUR_LEDGER_RECURRING_INITIAL_DELAY_MS"]).isdigit()
        and int(api_environment["OUR_LEDGER_RECURRING_INITIAL_DELAY_MS"]) >= 0,
        "production recurring initial delay가 잘못됐습니다.")
require(str(api_environment["OUR_LEDGER_RECURRING_POLL_DELAY_MS"]).isdigit()
        and int(api_environment["OUR_LEDGER_RECURRING_POLL_DELAY_MS"]) > 0,
        "production recurring poll delay가 잘못됐습니다.")
require("OUR_LEDGER_LOCAL_IDENTITY_EMAIL" not in api_environment,
        "production api에 local identity 환경변수가 전달되면 안 됩니다.")

migration_profiles = migration.get("profiles", []) or []
require(migration_profiles == ["migration"], "api-migration은 migration profile로만 활성화돼야 합니다.")
migration_environment = migration.get("environment", {}) or {}
expected_migration_environment = {
    "SPRING_PROFILES_ACTIVE",
    "SPRING_DATASOURCE_URL",
    "SPRING_DATASOURCE_USERNAME",
    "SPRING_DATASOURCE_PASSWORD",
    "OUR_LEDGER_BOOTSTRAP_ENABLED",
    "OUR_LEDGER_RECURRING_SCHEDULER_ENABLED",
}
require(
    set(migration_environment) == expected_migration_environment,
    "api-migration 환경변수 allowlist가 계약과 다릅니다.",
)
require(
    migration_environment["SPRING_PROFILES_ACTIVE"] == "production,migration",
    "api-migration은 production,migration profile만 활성화해야 합니다.",
)
require(migration_environment["OUR_LEDGER_BOOTSTRAP_ENABLED"] == "false",
        "api-migration bootstrap은 false여야 합니다.")
require(migration_environment["OUR_LEDGER_RECURRING_SCHEDULER_ENABLED"] == "false",
        "api-migration recurring scheduler는 false여야 합니다.")

bootstrap_profiles = bootstrap.get("profiles", []) or []
require(bootstrap_profiles == ["bootstrap"], "api-bootstrap은 bootstrap profile로만 활성화돼야 합니다.")
bootstrap_environment = bootstrap.get("environment", {}) or {}
expected_bootstrap_environment = {
    "SPRING_PROFILES_ACTIVE",
    "SPRING_DATASOURCE_URL",
    "SPRING_DATASOURCE_USERNAME",
    "SPRING_DATASOURCE_PASSWORD",
    "SPRING_FLYWAY_ENABLED",
    "SPRING_JPA_HIBERNATE_DDL_AUTO",
    "SPRING_MAIN_WEB_APPLICATION_TYPE",
    "OUR_LEDGER_BOOTSTRAP_ENABLED",
    "OUR_LEDGER_RECURRING_SCHEDULER_ENABLED",
}
require(
    set(bootstrap_environment) == expected_bootstrap_environment,
    "api-bootstrap 환경변수 allowlist가 계약과 다릅니다.",
)
require(
    bootstrap_environment["SPRING_PROFILES_ACTIVE"] == "production,bootstrap",
    "api-bootstrap은 production,bootstrap profile만 활성화해야 합니다.",
)
require(bootstrap_environment["SPRING_FLYWAY_ENABLED"] == "false",
        "api-bootstrap Flyway는 false여야 합니다.")
require(bootstrap_environment["SPRING_JPA_HIBERNATE_DDL_AUTO"] == "validate",
        "api-bootstrap JPA mode는 validate여야 합니다.")
require(bootstrap_environment["SPRING_MAIN_WEB_APPLICATION_TYPE"] == "none",
        "api-bootstrap Web application type은 none이어야 합니다.")
require(bootstrap_environment["OUR_LEDGER_BOOTSTRAP_ENABLED"] == "true",
        "api-bootstrap bootstrap은 true여야 합니다.")
require(bootstrap_environment["OUR_LEDGER_RECURRING_SCHEDULER_ENABLED"] == "false",
        "api-bootstrap recurring scheduler는 false여야 합니다.")

postgres_mounts = mounts(postgres)
require(len(postgres_mounts) == 1, "postgres는 정확히 한 개 data volume을 사용해야 합니다.")
postgres_mount = postgres_mounts[0]
require(postgres_mount.get("type") == "volume", "postgres data는 named volume이어야 합니다.")
require(postgres_mount.get("target") == "/var/lib/postgresql", "PostgreSQL 18 data mount 경로가 잘못됐습니다.")

require(network_names(web) == {"application"}, "web은 application network에만 연결해야 합니다.")
require(network_names(api) == {"application", "database"}, "api network 경계가 잘못됐습니다.")
require(network_names(migration) == {"application", "database"}, "api-migration network 경계가 잘못됐습니다.")
require(network_names(bootstrap) == {"database"}, "api-bootstrap은 database network에만 연결해야 합니다.")
require(network_names(postgres) == {"database"}, "postgres는 database network에만 연결해야 합니다.")

networks = config.get("networks", {}) or {}
require(networks.get("database", {}).get("internal") is True, "database network는 internal이어야 합니다.")

expected_project = os.environ.get("OUR_LEDGER_EXPECTED_COMPOSE_PROJECT")
if expected_project:
    require(config.get("name") == expected_project, "검증 Compose project 이름이 고유 project와 다릅니다.")
    expected_volume = f"{expected_project}_postgres-data"
    require(postgres_mount.get("source") == "postgres-data", "PostgreSQL volume logical key가 잘못됐습니다.")
    volume_config = (config.get("volumes", {}) or {}).get("postgres-data", {})
    require(volume_config.get("name") == expected_volume,
            "PostgreSQL volume이 검증 project로 격리되지 않았습니다.")

print("Production Compose 구조 검사를 통과했습니다.")
