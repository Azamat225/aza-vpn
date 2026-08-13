#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy/lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

PURGE_DATA=0
while (( $# )); do
    case "$1" in
        --purge-data) PURGE_DATA=1; shift ;;
        *) die "Unknown option: $1" ;;
    esac
done

require_root
require_supported_linux
[[ -f "$AZA_MARKER" ]] || die "AZA VPN marker is missing; refusing to delete any path."

PORT="unknown"
if [[ -f "$AZA_ETC_DIR/aza-vpn.env" ]]; then
    # Uninstall must still work if the installed .env is partially damaged.
    candidate_port="$(awk -F= '/^[[:space:]]*AZA_VLESS_PORT[[:space:]]*=/ {
        print $2; exit
    }' "$AZA_ETC_DIR/aza-vpn.env" 2>/dev/null | tr -d "[:space:]\"'" || true)"
    [[ "$candidate_port" =~ ^[0-9]+$ ]] && PORT="$candidate_port"
fi

if [[ -f /etc/systemd/system/aza-xray.service ]]; then
    systemctl disable --now aza-xray.service || warn "The AZA service was already stopped or could not be stopped."
fi
rm -f -- /etc/systemd/system/aza-xray.service /usr/local/bin/aza-vpn
rm -rf -- "$AZA_OPT_DIR" "$AZA_ETC_DIR" "$AZA_LOG_DIR"

if (( PURGE_DATA == 1 )); then
    rm -rf -- "$AZA_STATE_DIR"
    log "Purged /var/lib/aza-vpn client state as explicitly requested."
else
    log "Preserved /var/lib/aza-vpn. Use --purge-data only when permanent deletion is intended."
fi

if id "$AZA_USER" >/dev/null 2>&1; then
    if command -v getent >/dev/null 2>&1; then
        user_home="$(getent passwd "$AZA_USER" | cut -d: -f6)"
        user_shell="$(getent passwd "$AZA_USER" | cut -d: -f7)"
        if [[ "$user_home" == "$AZA_STATE_DIR" && "$user_shell" == */nologin ]]; then
            userdel "$AZA_USER" || warn "Could not remove the dedicated system user."
        else
            warn "User $AZA_USER does not match the managed account; it was not removed."
        fi
    else
        warn "getent is unavailable; the dedicated system user was not removed."
    fi
fi
systemctl daemon-reload

log "Removed only AZA VPN managed files and service."
log "No nginx, x-ui, Xray from x-ui, Docker, Redis, firewall, or unrelated config was modified."
if [[ "$PORT" != "unknown" ]]; then
    log "Firewall rules were intentionally left untouched. Review TCP $PORT manually if AZA opened it."
fi
