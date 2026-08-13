#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=deploy/lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

ENV_FILE="$PROJECT_ROOT/.env"
OPEN_FIREWALL=0
while (( $# )); do
    case "$1" in
        --env-file)
            (( $# >= 2 )) || die "--env-file requires a path"
            ENV_FILE="$2"
            shift 2
            ;;
        --open-firewall)
            OPEN_FIREWALL=1
            shift
            ;;
        *) die "Unknown option: $1" ;;
    esac
done

require_root
require_supported_linux
require_aza_marker
[[ -f "$AZA_INSTALL_RECORD" ]] || \
    die "AZA VPN installation is incomplete. Resume it with deploy/install.sh."
[[ -f "$AZA_ETC_DIR/aza-vpn.env" ]] || die "Installed environment file is missing."

load_env_file "$AZA_ETC_DIR/aza-vpn.env"
OLD_PORT="$AZA_VLESS_PORT"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl unzip python3 iproute2
require_python_312
load_env_file "$ENV_FILE"
validate_env_with_project "$PROJECT_ROOT" "$ENV_FILE"

if [[ "$AZA_VLESS_PORT" != "$OLD_PORT" ]]; then
    port_is_free "$AZA_VLESS_PORT" || {
        ss -lntup 2>/dev/null || true
        die "New TCP port $AZA_VLESS_PORT is occupied; update aborted before changes."
    }
fi
"$SCRIPT_DIR/preflight.sh" --env-file "$ENV_FILE" --allow-aza-port

ARTIFACT_ARCH="$(map_xray_architecture)"
STAGE="$(mktemp -d)"
trap 'rm -rf -- "$STAGE"' EXIT
download_xray_release "$XRAY_VERSION" "$ARTIFACT_ARCH" "$STAGE"

# Render and validate the complete new config with the downloaded binary before
# replacing any installed code, binary, environment, or active configuration.
PYTHONPATH="$PROJECT_ROOT/src" \
AZA_ENV_FILE="$ENV_FILE" \
AZA_STATE_FILE="$AZA_STATE_DIR/clients.json" \
AZA_SECRETS_FILE="$AZA_ETC_DIR/secrets.json" \
AZA_CONFIG_FILE="$STAGE/config.json" \
AZA_TEMPLATE_FILE="$PROJECT_ROOT/templates/xray/config.json.j2" \
AZA_XRAY_BINARY="$XRAY_DOWNLOADED_BINARY" \
AZA_LOCK_FILE="$STAGE/update.lock" \
python3 -m aza_vpn.cli init --no-restart

install -m 0755 "$AZA_OPT_DIR/xray/xray" "$STAGE/xray.old"
cp -a -- "$AZA_OPT_DIR/app" "$STAGE/app.old"
install -m 0644 "$AZA_OPT_DIR/templates/xray/config.json.j2" "$STAGE/template.old"
install -m 0600 "$AZA_ETC_DIR/aza-vpn.env" "$STAGE/env.old"
install -m 0644 /etc/systemd/system/aza-xray.service "$STAGE/unit.old"
install -m 0755 /usr/local/bin/aza-vpn "$STAGE/wrapper.old"

ROLLBACK_READY=0
rollback_update() {
    (( ROLLBACK_READY == 1 )) || return 0
    warn "Rolling back Xray binary, application code, environment, and unit."
    install -m 0755 -o root -g root "$STAGE/xray.old" "$AZA_OPT_DIR/xray/xray"
    rm -rf -- "$AZA_OPT_DIR/app"
    cp -a -- "$STAGE/app.old" "$AZA_OPT_DIR/app"
    install -m 0644 -o root -g root "$STAGE/template.old" \
        "$AZA_OPT_DIR/templates/xray/config.json.j2"
    install -m 0600 -o root -g root "$STAGE/env.old" "$AZA_ETC_DIR/aza-vpn.env"
    install -m 0644 -o root -g root "$STAGE/unit.old" /etc/systemd/system/aza-xray.service
    install -m 0755 -o root -g root "$STAGE/wrapper.old" /usr/local/bin/aza-vpn
    systemctl daemon-reload
    systemctl restart aza-xray.service || \
        warn "Rollback files were restored, but the old service did not restart; inspect the journal."
}

install -m 0755 -o root -g root "$XRAY_DOWNLOADED_BINARY" "$AZA_OPT_DIR/xray/xray"
rm -rf -- "$AZA_OPT_DIR/app"
install -d -m 0755 -o root -g root "$AZA_OPT_DIR/app"
cp -a -- "$PROJECT_ROOT/src/aza_vpn" "$AZA_OPT_DIR/app/"
install -m 0644 -o root -g root "$PROJECT_ROOT/templates/xray/config.json.j2" \
    "$AZA_OPT_DIR/templates/xray/config.json.j2"
install -m 0600 -o root -g root "$ENV_FILE" "$AZA_ETC_DIR/aza-vpn.env"
install -m 0644 -o root -g root "$SCRIPT_DIR/systemd/aza-xray.service" \
    /etc/systemd/system/aza-xray.service
install -m 0755 -o root -g root "$SCRIPT_DIR/bin/aza-vpn" /usr/local/bin/aza-vpn
ROLLBACK_READY=1
systemctl daemon-reload

if ! AZA_ENV_FILE="$AZA_ETC_DIR/aza-vpn.env" /usr/local/bin/aza-vpn config apply; then
    rollback_update
    die "Update activation failed; installed files were rolled back."
fi

AZA_ENV_FILE="$AZA_ETC_DIR/aza-vpn.env" /usr/local/bin/aza-vpn record-install \
    --requested "$XRAY_VERSION" \
    --installed "$RESOLVED_XRAY_VERSION" \
    --architecture "$(uname -m)/$ARTIFACT_ARCH"
ROLLBACK_READY=0

if (( OPEN_FIREWALL == 1 )) && ufw_is_active; then
    ufw allow "${AZA_VLESS_PORT}/tcp" comment 'aza-vpn VLESS'
elif [[ "$AZA_VLESS_PORT" != "$OLD_PORT" ]] && ufw_is_active; then
    log "UFW was not modified. Open the new port manually if required: ufw allow ${AZA_VLESS_PORT}/tcp comment 'aza-vpn VLESS'"
fi

log "Requested Xray: $XRAY_VERSION"
log "Installed Xray: $RESOLVED_XRAY_VERSION"
log "Architecture: $(uname -m)/$ARTIFACT_ARCH"
log "Update complete; existing nginx, x-ui, Docker, Redis, and other services were not modified."
