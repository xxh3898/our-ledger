FROM scratch

ARG REVISION

LABEL org.opencontainers.image.source="https://github.com/xxh3898/our-ledger"
LABEL org.opencontainers.image.revision="${REVISION}"
LABEL org.opencontainers.image.version="${REVISION}"
LABEL io.chochiho.runtime-config.project="our-ledger"

COPY --chmod=0600 runtime-manifest.json /runtime/runtime-manifest.json
COPY --chmod=0600 compose.prod.yaml /runtime/compose.yaml
COPY --chmod=0600 infra/nginx/nginx.conf /runtime/infra/nginx/nginx.conf
COPY --chmod=0700 scripts/backup-our-ledger-bootstrap.sh /runtime/scripts/backup-our-ledger-bootstrap.sh
COPY --chmod=0700 scripts/backup-production.sh /runtime/scripts/backup-production.sh
COPY --chmod=0600 scripts/backup_tools/backup_artifact.py /runtime/scripts/backup_tools/backup_artifact.py
COPY --chmod=0600 scripts/backup_tools/backup_core.sh /runtime/scripts/backup_tools/backup_core.sh
COPY --chmod=0600 scripts/backup_tools/offsite_backup.py /runtime/scripts/backup_tools/offsite_backup.py
COPY --chmod=0700 scripts/bootstrap-production.sh /runtime/scripts/bootstrap-production.sh
COPY --chmod=0700 scripts/deploy-production.sh /runtime/scripts/deploy-production.sh
COPY --chmod=0600 scripts/host_tools/deploy_transaction.py /runtime/scripts/host_tools/deploy_transaction.py
COPY --chmod=0600 scripts/host_tools/fresh_bootstrap_state.py /runtime/scripts/host_tools/fresh_bootstrap_state.py
COPY --chmod=0600 scripts/host_tools/fresh_host_bootstrap.py /runtime/scripts/host_tools/fresh_host_bootstrap.py
COPY --chmod=0600 scripts/host_tools/host_state.py /runtime/scripts/host_tools/host_state.py
COPY --chmod=0600 scripts/host_tools/production_deploy.py /runtime/scripts/host_tools/production_deploy.py
COPY --chmod=0600 scripts/host_tools/production_fresh_bootstrap.py /runtime/scripts/host_tools/production_fresh_bootstrap.py
COPY --chmod=0600 scripts/host_tools/production_host.py /runtime/scripts/host_tools/production_host.py
COPY --chmod=0700 scripts/monitor-production.sh /runtime/scripts/monitor-production.sh
COPY --chmod=0700 scripts/offsite-backup-production.sh /runtime/scripts/offsite-backup-production.sh
COPY --chmod=0700 scripts/offsite-our-ledger-bootstrap.sh /runtime/scripts/offsite-our-ledger-bootstrap.sh
COPY --chmod=0700 scripts/production-status.sh /runtime/scripts/production-status.sh
COPY --chmod=0700 scripts/release_tools/release_contract.py /runtime/scripts/release_tools/release_contract.py
COPY --chmod=0600 scripts/status_tools/monitor_policy.py /runtime/scripts/status_tools/monitor_policy.py
COPY --chmod=0600 scripts/status_tools/monitor_worker.py /runtime/scripts/status_tools/monitor_worker.py
COPY --chmod=0600 scripts/status_tools/production_status.py /runtime/scripts/status_tools/production_status.py

CMD ["/runtime/compose.yaml"]
