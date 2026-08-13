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

if [[ -e "$AZA_MARKER" ]]; then
    die "AZA VPN is already installed. Use deploy/update.sh."
fi
if [[ -e "$AZA_OPT_DIR" || -e "$AZA_ETC_DIR" ]]; then
    die "A managed path already exists without the AZA marker; refusing to overwrite it."
fi

log "Installing required Ubuntu/Debian packages (no upgrades or service removals)."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl unzip python3 iproute2

"$SCRIPT_DIR/preflight.sh" --env-file "$ENV_FILE"
load_env_file "$ENV_FILE"
ARTIFACT_ARCH="$(map_xray_architecture)"
STAGE="$(mktemp -d)"
trap 'rm -rf -- "$STAGE"' EXIT
download_xray_release "$XRAY_VERSION" "$ARTIFACT_ARCH" "$STAGE"

if ! id "$AZA_USER" >/dev/null 2>&1; then
    useradd --system --home-dir "$AZA_STATE_DIR" --shell /usr/sbin/nologin --user-group "$AZA_USER"
else
    die "System user $AZA_USER already exists without an AZA installation; refusing a collision."
fi

install -d -m 0755 -o root -g root "$AZA_OPT_DIR" "$AZA_OPT_DIR/app" \
    "$AZA_OPT_DIR/xray" "$AZA_OPT_DIR/templates/xray"
install -d -m 2750 -o root -g "$AZA_USER" "$AZA_ETC_DIR"
install -d -m 0700 -o root -g root "$AZA_STATE_DIR"
install -d -m 0750 -o "$AZA_USER" -g "$AZA_USER" "$AZA_LOG_DIR"

cp -a -- "$PROJECT_ROOT/src/aza_vpn" "$AZA_OPT_DIR/app/"
install -m 0644 -o root -g root "$PROJECT_ROOT/templates/xray/config.json.j2" \
    "$AZA_OPT_DIR/templates/xray/config.json.j2"
install -m 0755 -o root -g root "$XRAY_DOWNLOADED_BINARY" "$AZA_OPT_DIR/xray/xray"
install -m 0600 -o root -g root "$ENV_FILE" "$AZA_ETC_DIR/aza-vpn.env"
install -m 0755 -o root -g root "$SCRIPT_DIR/bin/aza-vpn" /usr/local/bin/aza-vpn
install -m 0644 -o root -g root "$SCRIPT_DIR/systemd/aza-xray.service" \
    /etc/systemd/system/aza-xray.service
printf 'aza-vpn-v0.1\n' > "$AZA_MARKER"
chmod 0600 "$AZA_MARKER"

AZA_ENV_FILE="$AZA_ETC_DIR/aza-vpn.env" /usr/local/bin/aza-vpn init --no-restart
chown root:"$AZA_USER" "$AZA_ETC_DIR/config.json"
chmod 0640 "$AZA_ETC_DIR/config.json"
AZA_ENV_FILE="$AZA_ETC_DIR/aza-vpn.env" /usr/local/bin/aza-vpn record-install \
    --requested "$XRAY_VERSION" \
    --installed "$RESOLVED_XRAY_VERSION" \
    --architecture "$(uname -m)/$ARTIFACT_ARCH"

# This explicit native validation is mandatory before the first systemd start.
AZA_ENV_FILE="$AZA_ETC_DIR/aza-vpn.env" /usr/local/bin/aza-vpn config validate
systemctl daemon-reload
systemctl enable aza-xray.service
systemctl start aza-xray.service
systemctl is-active --quiet aza-xray.service || \
    die "aza-xray.service did not become active. Inspect journalctl -u aza-xray.service."

if (( OPEN_FIREWALL == 1 )); then
    if ufw_is_active; then
        ufw allow "${AZA_VLESS_PORT}/tcp" comment 'aza-vpn VLESS'
        log "Opened only TCP $AZA_VLESS_PORT in active UFW."
    else
        warn "--open-firewall was requested, but UFW is inactive or unavailable; nothing changed."
    fi
elif ufw_is_active; then
    log "UFW was not modified. If desired, run: ufw allow ${AZA_VLESS_PORT}/tcp comment 'aza-vpn VLESS'"
fi

log "Requested Xray: $XRAY_VERSION"
log "Installed Xray: $RESOLVED_XRAY_VERSION"
log "Architecture: $(uname -m)/$ARTIFACT_ARCH"
log "Installation complete. Create the first client with: sudo aza-vpn client create azamat"

