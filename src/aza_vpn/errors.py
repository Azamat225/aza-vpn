"""Application-specific exceptions with safe, user-facing messages."""


class AzaVpnError(Exception):
    """Base exception for expected CLI failures."""


class ConfigurationError(AzaVpnError):
    """Deployment or runtime configuration is missing or invalid."""


class StateError(AzaVpnError):
    """Persistent state cannot be safely read or changed."""


class XrayError(AzaVpnError):
    """An Xray command or configuration validation failed."""


class ServiceError(AzaVpnError):
    """The dedicated systemd service could not be managed safely."""

