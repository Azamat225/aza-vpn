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

INSTALL_MODE="fresh"
if [[ -e "$AZA_MARKER" ]]; then
    require_aza_marker
    if [[ -f "$AZA_INSTALL_RECORD" ]]; then
        die "AZA VPN installation is complete. Use deploy/update.sh."
    fi
    INSTALL_MODE="recovery"
    log "Incomplete managed AZA VPN installation detected; safely resuming it."
else
    for unmanaged_path in \
        "$AZA_OPT_DIR" \
        "$AZA_ETC_DIR" \
        "$AZA_STATE_DIR" \
        "$AZA_LOG_DIR" \
        /etc/systemd/system/aza-xray.service \
        /usr/local/bin/aza-vpn; do
        [[ ! -e "$unmanaged_path" ]] || \
            die "Path exists without the AZA ownership marker: $unmanaged_path"
    done
    id "$AZA_USER" >/dev/null 2>&1 && \
        die "System user $AZA_USER exists without an AZA ownership marker."
    install -d -m 0755 -o root -g root "$AZA_OPT_DIR"
    printf '%s\n' "$AZA_MARKER_VALUE" > "$AZA_MARKER"
    chmod 0600 "$AZA_MARKER"
fi

log "Installing required Ubuntu/Debian packages (no upgrades or service removals)."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl unzip python3 iproute2

if [[ "$INSTALL_MODE" == "recovery" ]]; then
    "$SCRIPT_DIR/preflight.sh" --env-file "$ENV_FILE" --allow-aza-port
else
    "$SCRIPT_DIR/preflight.sh" --env-file "$ENV_FILE"
fi
load_env_file "$ENV_FILE"
ARTIFACT_ARCH="$(map_xray_architecture)"
STAGE="$(mktemp -d)"
trap 'rm -rf -- "$STAGE"' EXIT
download_xray_release "$XRAY_VERSION" "$ARTIFACT_ARCH" "$STAGE"

if ! id "$AZA_USER" >/dev/null 2>&1; then
    useradd --system --home-dir "$AZA_STATE_DIR" --shell /usr/sbin/nologin --user-group "$AZA_USER"
elif [[ "$INSTALL_MODE" == "recovery" ]] && managed_account_matches; then
    log "Reusing the dedicated AZA system account from the incomplete installation."
else
    die "System user $AZA_USER does not match the dedicated managed account; refusing a collision."
fi

install -d -m 0755 -o root -g root "$AZA_OPT_DIR" "$AZA_OPT_DIR/app" \
    "$AZA_OPT_DIR/xray" "$AZA_OPT_DIR/templates/xray"
install -d -m 2750 -o root -g "$AZA_USER" "$AZA_ETC_DIR"
install -d -m 0700 -o root -g root "$AZA_STATE_DIR"
install -d -m 0750 -o "$AZA_USER" -g "$AZA_USER" "$AZA_LOG_DIR"

# The exact ownership marker was verified above, so replacing only our installed
# Python package is safe and prevents stale modules after a resumed installation.
rm -rf -- "$AZA_OPT_DIR/app/aza_vpn"
cp -a -- "$PROJECT_ROOT/src/aza_vpn" "$AZA_OPT_DIR/app/"
install -m 0644 -o root -g root "$PROJECT_ROOT/templates/xray/config.json.j2" \
    "$AZA_OPT_DIR/templates/xray/config.json.j2"
install -m 0755 -o root -g root "$XRAY_DOWNLOADED_BINARY" "$AZA_OPT_DIR/xray/xray"
install -m 0600 -o root -g root "$ENV_FILE" "$AZA_ETC_DIR/aza-vpn.env"
install -m 0755 -o root -g root "$SCRIPT_DIR/bin/aza-vpn" /usr/local/bin/aza-vpn
install -m 0644 -o root -g root "$SCRIPT_DIR/systemd/aza-xray.service" \
    /etc/systemd/system/aza-xray.service

systemctl daemon-reload
systemctl enable aza-xray.service

# init renders a candidate, validates it with the downloaded Xray binary, moves
# it atomically, then restarts the dedicated service. ConfigApplier restores the
# previous config if that restart fails.
AZA_ENV_FILE="$AZA_ETC_DIR/aza-vpn.env" /usr/local/bin/aza-vpn init
chown root:"$AZA_USER" "$AZA_ETC_DIR/config.json"
chmod 0640 "$AZA_ETC_DIR/config.json"

# Keep an explicit post-activation native validation as a diagnostic invariant.
AZA_ENV_FILE="$AZA_ETC_DIR/aza-vpn.env" /usr/local/bin/aza-vpn config validate
systemctl is-active --quiet aza-xray.service || \
    die "aza-xray.service did not become active. Inspect journalctl -u aza-xray.service."

# This is the completion record. It is deliberately written only after the
# service is active, so an interrupted run remains safely resumable.
AZA_ENV_FILE="$AZA_ETC_DIR/aza-vpn.env" /usr/local/bin/aza-vpn record-install \
    --requested "$XRAY_VERSION" \
    --installed "$RESOLVED_XRAY_VERSION" \
    --architecture "$(uname -m)/$ARTIFACT_ARCH"

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
