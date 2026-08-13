#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=deploy/lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

ENV_FILE="$PROJECT_ROOT/.env"
ALLOW_AZA_PORT=0
while (( $# )); do
    case "$1" in
        --env-file)
            (( $# >= 2 )) || die "--env-file requires a path"
            ENV_FILE="$2"
            shift 2
            ;;
        --allow-aza-port)
            ALLOW_AZA_PORT=1
            shift
            ;;
        *) die "Unknown option: $1" ;;
    esac
done

require_root
require_supported_linux
log "Operating system: ${PRETTY_NAME:-unknown}"
log "Architecture: $(uname -m) (Xray artifact $(map_xray_architecture))"

missing=()
for command_name in curl unzip sha256sum ss python3 awk grep sed install df; do
    command -v "$command_name" >/dev/null 2>&1 || missing+=("$command_name")
done
(( ${#missing[@]} == 0 )) || die "Missing utilities: ${missing[*]}. install.sh can install prerequisites."
require_python_312
load_env_file "$ENV_FILE"
validate_env_with_project "$PROJECT_ROOT" "$ENV_FILE"
log "Deployment configuration: valid"

if (( ALLOW_AZA_PORT == 0 )); then
    port_is_free "$AZA_VLESS_PORT" || {
        ss -lntup 2>/dev/null || true
        die "TCP port $AZA_VLESS_PORT is already occupied; nothing was changed."
    }
    log "TCP port $AZA_VLESS_PORT: free"
else
    log "TCP port occupancy check: allowed only for the existing AZA service during update"
fi

detect_existing_services

available_kib="$(df -Pk /opt | awk 'NR==2 {print $4}')"
[[ "$available_kib" =~ ^[0-9]+$ ]] || die "Cannot determine free disk space."
(( available_kib >= 204800 )) || die "At least 200 MiB free space is required under /opt."
log "Disk space: sufficient"

for parent in /opt /etc /var/lib /var/log; do
    [[ -d "$parent" && -w "$parent" ]] || die "Cannot create managed directories below $parent."
done
log "Managed directory parents: writable"

curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
    --max-time 15 -o /dev/null 'https://api.github.com/repos/XTLS/Xray-core/releases/latest' || \
    die "Cannot reach the official Xray release API."
log "Official Xray release source: reachable"

check_reality_destination "$REALITY_DEST" "$REALITY_SERVER_NAME" || \
    die "REALITY_DEST TLS connectivity/certificate check failed from this server."

if ufw_is_active; then
    log "UFW is active. Required rule: ufw allow ${AZA_VLESS_PORT}/tcp comment 'aza-vpn VLESS'"
else
    log "UFW is not active or not installed; no firewall changes will be made."
fi

log "Preflight passed. No existing service or firewall configuration was modified."

