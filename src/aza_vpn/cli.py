"""Administrative command-line interface for AZA VPN V0.1."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Sequence

from aza_vpn import __version__
from aza_vpn.clients.repository import ClientRepository, SecretRepository
from aza_vpn.clients.service import ClientService
from aza_vpn.config import AppPaths, load_settings
from aza_vpn.errors import AzaVpnError, ServiceError, XrayError
from aza_vpn.models import Client
from aza_vpn.utils.files import atomic_write_json
from aza_vpn.utils.shell import run_command, systemd_state


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aza-vpn",
        description="Manage the dedicated AZA VLESS + REALITY Xray instance.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--env-file", type=Path, help="Override /etc/aza-vpn/aza-vpn.env")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show safe diagnostic information")

    client = subparsers.add_parser("client", help="Manage VLESS clients")
    client_sub = client.add_subparsers(dest="client_command", required=True)
    create = client_sub.add_parser("create", help="Create and activate a client")
    create.add_argument("name")
    client_sub.add_parser("list", help="List clients")
    show = client_sub.add_parser("show", help="Show one client and its import URI")
    show.add_argument("name")
    remove = client_sub.add_parser("remove", help="Remove and revoke a client")
    remove.add_argument("name")

    config = subparsers.add_parser("config", help="Validate or reconcile Xray config")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser("validate", help="Run the native Xray config test")
    apply_parser = config_sub.add_parser("apply", help="Render, validate, and atomically apply")
    apply_parser.add_argument("--no-restart", action="store_true")

    init_parser = subparsers.add_parser("init", help="Initialize server state (deployment use)")
    init_parser.add_argument("--no-restart", action="store_true")

    record = subparsers.add_parser(
        "record-install", help="Record resolved Xray release metadata (deployment use)"
    )
    record.add_argument("--requested", required=True)
    record.add_argument("--installed", required=True)
    record.add_argument("--architecture", required=True)
    return parser


def _paths(args: argparse.Namespace) -> AppPaths:
    environment = dict(os.environ)
    if args.env_file is not None:
        environment["AZA_ENV_FILE"] = str(args.env_file)
    return AppPaths.from_environment(environment)


def _require_root() -> None:
    geteuid = getattr(os, "geteuid", None)
    if geteuid is not None and geteuid() != 0:
        raise ServiceError("This state-changing command must be run as root (use sudo).")


def _print_client(client: Client, service: ClientService) -> None:
    settings = load_settings(service.paths)
    print(f"Client: {client.name}")
    print(f"Server: {settings.server_label}")
    print("Protocol: VLESS Reality Vision")
    print(f"Address: {settings.server_address}")
    print(f"Port: {settings.port}")
    print()
    print("Import URL:")
    print(service.uri_for(client))


def _xray_version(paths: AppPaths) -> str:
    if not paths.xray_binary.is_file():
        return "not installed"
    result = run_command([str(paths.xray_binary), "version"], timeout=10)
    if result.returncode != 0:
        return "unavailable"
    return result.stdout.splitlines()[0] if result.stdout else "unknown"


def _install_record(paths: AppPaths) -> dict[str, str]:
    try:
        raw = json.loads(paths.install_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _status(paths: AppPaths) -> None:
    settings = load_settings(paths)
    state = ClientRepository(paths.state_file).load()
    secrets_value = SecretRepository(paths.secrets_file).load()
    record = _install_record(paths)
    try:
        ClientService(paths).validate_active()
        config_state = "valid"
    except (XrayError, ServiceError) as exc:
        config_state = f"invalid ({exc})"

    print("AZA VPN V0.1")
    print(f"Xray version: {_xray_version(paths)}")
    if record:
        print(f"Requested Xray: {record.get('requested_xray', 'unknown')}")
        print(f"Installed Xray: {record.get('installed_xray', 'unknown')}")
        print(f"Architecture: {record.get('architecture', 'unknown')}")
    print(f"Service: {systemd_state(paths.service_name)}")
    print(f"Config validation: {config_state}")
    print(f"Configured TCP port: {settings.port}")
    print(f"Clients: {len(state.clients)}")
    print(f"Server address: {settings.server_address}")
    print(f"Server label: {settings.server_label}")
    print(f"Reality server name: {settings.reality_server_name}")
    print(f"Reality target: {settings.reality_dest}")
    print(f"Reality public key/password: {secrets_value.public_key}")
    print(f"Reality shortId: {secrets_value.short_id}")


def _record_install(paths: AppPaths, args: argparse.Namespace) -> None:
    _require_root()
    atomic_write_json(
        paths.install_file,
        {
            "schema_version": 1,
            "requested_xray": args.requested,
            "installed_xray": args.installed,
            "architecture": args.architecture,
        },
        mode=0o600,
    )


def dispatch(args: argparse.Namespace) -> None:
    paths = _paths(args)
    service = ClientService(paths)

    if args.command == "status":
        _status(paths)
        return
    if args.command == "init":
        _require_root()
        service.initialize(restart=not args.no_restart)
        print("AZA VPN state and validated Xray config initialized.")
        return
    if args.command == "record-install":
        _record_install(paths, args)
        return
    if args.command == "config":
        if args.config_command == "validate":
            print(f"Xray config: {service.validate_active()}")
            return
        _require_root()
        service.reconcile(restart=not args.no_restart)
        print("Validated Xray config applied atomically.")
        return
    if args.command != "client":
        raise AssertionError(f"Unhandled command: {args.command}")

    if args.client_command == "list":
        clients = service.list_clients()
        if not clients:
            print("No clients configured.")
            return
        print("NAME\tUUID\tCREATED")
        for client in clients:
            print(f"{client.name}\t{client.uuid}\t{client.created_at}")
        return
    if args.client_command == "show":
        _print_client(service.get_client(args.name), service)
        return

    _require_root()
    if args.client_command == "create":
        _print_client(service.create_client(args.name), service)
        return
    if args.client_command == "remove":
        removed = service.remove_client(args.name)
        print(f"Removed client: {removed.name}")
        print("A validated config was activated and the service was restarted.")
        return
    raise AssertionError(f"Unhandled client command: {args.client_command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        dispatch(args)
    except AzaVpnError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
