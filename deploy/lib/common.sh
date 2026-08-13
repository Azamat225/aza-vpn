#!/usr/bin/env bash

set -Eeuo pipefail

readonly AZA_OPT_DIR="/opt/aza-vpn"
readonly AZA_ETC_DIR="/etc/aza-vpn"
readonly AZA_STATE_DIR="/var/lib/aza-vpn"
readonly AZA_LOG_DIR="/var/log/aza-vpn"
readonly AZA_SERVICE="aza-xray.service"
readonly AZA_USER="aza-vpn"
readonly AZA_MARKER="/opt/aza-vpn/.aza-vpn-managed"

log() { printf '[aza-vpn] %s\n' "$*"; }
warn() { printf '[aza-vpn] WARNING: %s\n' "$*" >&2; }
die() { printf '[aza-vpn] ERROR: %s\n' "$*" >&2; exit 1; }

trim() {
    local value="$*"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    printf '%s' "$value"
}

require_root() {
    [[ "${EUID}" -eq 0 ]] || die "Run this script with sudo/root."
}

require_supported_linux() {
    [[ "$(uname -s)" == "Linux" ]] || die "This deployment script runs only on Linux."
    [[ -r /etc/os-release ]] || die "/etc/os-release is missing."
    # shellcheck disable=SC1091
    . /etc/os-release
    local family="${ID:-} ${ID_LIKE:-}"
    [[ "$family" == *ubuntu* || "$family" == *debian* ]] || \
        die "Only Ubuntu/Debian-compatible systems are supported."
}

load_env_file() {
    local env_file="$1"
    [[ -f "$env_file" ]] || die "Environment file not found: $env_file"
    local raw line key value first last
    declare -A seen=()
    while IFS= read -r raw || [[ -n "$raw" ]]; do
        raw="${raw%$'\r'}"
        line="$(trim "$raw")"
        [[ -z "$line" || "${line:0:1}" == "#" ]] && continue
        [[ "$line" == *=* ]] || die "Invalid .env line (expected KEY=value): $raw"
        key="$(trim "${line%%=*}")"
        value="$(trim "${line#*=}")"
        [[ "$key" =~ ^[A-Z][A-Z0-9_]*$ ]] || die "Invalid .env key: $key"
        [[ -z "${seen[$key]+x}" ]] || die "Duplicate .env key: $key"
        seen["$key"]=1
        if (( ${#value} >= 2 )); then
            first="${value:0:1}"
            last="${value: -1}"
            if [[ ( "$first" == "\"" && "$last" == "\"" ) || \
                  ( "$first" == "'" && "$last" == "'" ) ]]; then
                value="${value:1:${#value}-2}"
            elif [[ "$first" == "\"" || "$first" == "'" || \
                    "$last" == "\"" || "$last" == "'" ]]; then
                die "Mismatched quotes for .env key: $key"
            fi
        fi
        export "$key=$value"
    done < "$env_file"
}

require_python_312() {
    python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' || \
        die "Python 3.12 or newer is required."
}

validate_env_with_project() {
    local project_root="$1"
    local env_file="$2"
    PYTHONPATH="$project_root/src" AZA_ENV_FILE="$env_file" python3 -c \
        'from aza_vpn.config import AppPaths, load_settings; load_settings(AppPaths.from_environment())' || \
        die "Deployment configuration is invalid; see the Python error above."
}

map_xray_architecture() {
    case "$(uname -m)" in
        x86_64|amd64) printf '64' ;;
        aarch64|arm64) printf 'arm64-v8a' ;;
        *) die "Unsupported CPU architecture: $(uname -m)" ;;
    esac
}

port_is_free() {
    local port="$1"
    ! ss -H -lnt "sport = :$port" 2>/dev/null | grep -q .
}

check_reality_destination() {
    local target="$1"
    local server_name="$2"
    python3 - "$target" "$server_name" <<'PY'
import socket
import ssl
import sys

target, server_name = sys.argv[1:]
if target.startswith("["):
    end = target.find("]")
    if end < 0 or target[end + 1 : end + 2] != ":":
        raise SystemExit("invalid bracketed REALITY_DEST")
    host, port_text = target[1:end], target[end + 2 :]
else:
    host, port_text = target.rsplit(":", 1)
port = int(port_text)
context = ssl.create_default_context()
context.minimum_version = ssl.TLSVersion.TLSv1_3
with socket.create_connection((host, port), timeout=8) as raw:
    with context.wrap_socket(raw, server_hostname=server_name) as tls:
        if tls.version() != "TLSv1.3":
            raise RuntimeError(f"unexpected TLS version: {tls.version()}")
        print(f"REALITY destination TLS check: {host}:{port} -> {tls.version()}")
PY
}

detect_existing_services() {
    local detected=0
    if command -v systemctl >/dev/null 2>&1; then
        if systemctl list-unit-files --type=service --no-legend 2>/dev/null | \
            grep -Eiq '(^|[[:space:]])(nginx|x-ui|3x-ui)(\.service)?([[:space:]]|$)'; then
            detected=1
        fi
    fi
    if command -v pgrep >/dev/null 2>&1 && pgrep -f '(nginx|x-ui|3x-ui)' >/dev/null 2>&1; then
        detected=1
    fi
    if (( detected == 1 )); then
        log "Existing service detected. It will not be modified."
    fi
}

resolve_xray_version() {
    local requested="$1"
    if [[ "$requested" == "latest" ]]; then
        local response
        response="$(mktemp)"
        curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
            --max-time 30 -H 'Accept: application/vnd.github+json' \
            -o "$response" 'https://api.github.com/repos/XTLS/Xray-core/releases/latest' || {
                rm -f -- "$response"
                die "Cannot resolve latest Xray release from the official GitHub API."
            }
        RESOLVED_XRAY_VERSION="$(python3 - "$response" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle).get("tag_name", "")
if not isinstance(value, str):
    value = ""
print(value)
PY
)"
        rm -f -- "$response"
    else
        RESOLVED_XRAY_VERSION="v${requested#v}"
    fi
    [[ "$RESOLVED_XRAY_VERSION" =~ ^v[0-9]+(\.[0-9]+){2}([.-][0-9A-Za-z]+)*$ ]] || \
        die "Official release tag has an unexpected format: $RESOLVED_XRAY_VERSION"
    export RESOLVED_XRAY_VERSION
}

download_xray_release() {
    local requested="$1"
    local artifact_arch="$2"
    local destination="$3"
    resolve_xray_version "$requested"
    local archive="Xray-linux-${artifact_arch}.zip"
    local base="https://github.com/XTLS/Xray-core/releases/download/${RESOLVED_XRAY_VERSION}"
    local zip_file="$destination/$archive"
    local digest_file="$zip_file.dgst"
    mkdir -p -- "$destination/extracted"
    log "Downloading official Xray release $RESOLVED_XRAY_VERSION ($archive)."
    curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
        --max-time 120 -o "$zip_file" "$base/$archive" || \
        die "Failed to download the official Xray archive."
    curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
        --max-time 30 -o "$digest_file" "$base/$archive.dgst" || \
        die "Official .dgst is unavailable; refusing an unverified installation."

    local expected actual
    expected="$(awk -F '= ' '/256=/ {print $2; exit}' "$digest_file" | tr '[:upper:]' '[:lower:]')"
    [[ "$expected" =~ ^[0-9a-f]{64}$ ]] || \
        die "Official .dgst SHA-256 format is unknown; refusing to guess."
    actual="$(sha256sum "$zip_file" | awk '{print tolower($1)}')"
    [[ "$actual" == "$expected" ]] || die "Xray archive SHA-256 verification failed."
    unzip -q "$zip_file" -d "$destination/extracted" || die "Cannot extract Xray archive."
    [[ -f "$destination/extracted/xray" ]] || die "Verified archive does not contain xray."
    XRAY_DOWNLOADED_BINARY="$destination/extracted/xray"
    export XRAY_DOWNLOADED_BINARY
}

ufw_is_active() {
    command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'
}
