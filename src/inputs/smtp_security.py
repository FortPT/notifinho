"""
Notifinho

smtp_security.py

Optional SMTP STARTTLS and authentication support.
"""

from __future__ import annotations

import hmac
import os
import ssl

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from aiosmtpd.smtp import AuthResult, LoginPassword

from config import config


class SMTPSecurityConfigError(ValueError):
    """Raised when SMTP security configuration is incomplete or unsafe."""


@dataclass(frozen=True)
class SMTPSecuritySettings:
    """Validated effective SMTP security settings."""

    tls_enabled: bool = False
    require_starttls: bool = False
    auth_enabled: bool = False
    auth_required: bool = False
    tls_context: ssl.SSLContext | None = None
    authenticator: Callable[..., AuthResult] | None = None

    def controller_kwargs(self) -> dict:
        """Return only the SMTP keyword arguments required by this mode."""

        values = {}

        if self.tls_enabled:
            values.update(
                {
                    "tls_context": self.tls_context,
                    "require_starttls": self.require_starttls,
                }
            )

        if self.auth_enabled:
            values.update(
                {
                    "authenticator": self.authenticator,
                    "auth_required": self.auth_required,
                    "auth_require_tls": True,
                }
            )

        elif self.tls_enabled:
            values["auth_exclude_mechanism"] = {"LOGIN", "PLAIN"}

        return values

    def safe_summary(self) -> str:
        """Return a startup summary containing no credential material."""

        if not self.tls_enabled and not self.auth_enabled:
            return "SMTP security: disabled"

        tls_mode = "required" if self.require_starttls else "available"

        if not self.auth_enabled:
            auth_mode = "disabled"
        elif self.auth_required:
            auth_mode = "required"
        else:
            auth_mode = "optional"

        return (
            "SMTP security: TLS enabled, STARTTLS %s, authentication %s"
            % (tls_mode, auth_mode)
        )


class SMTPAuthenticator:
    """Validate one configured SMTP service account."""

    def __init__(self, username: str, password: bytes):
        self._username = username.encode("utf-8")
        self._password = bytes(password)

    def __call__(
        self,
        server,
        session,
        envelope,
        mechanism,
        auth_data,
    ) -> AuthResult:
        """Return an aiosmtpd authentication decision."""

        del server, session, envelope

        if str(mechanism).upper() not in {"LOGIN", "PLAIN"}:
            return AuthResult(
                success=False,
                handled=False,
            )

        if not isinstance(auth_data, LoginPassword):
            return AuthResult(
                success=False,
                handled=False,
            )

        try:
            supplied_username = bytes(auth_data.login)
            supplied_password = bytes(auth_data.password)
        except (TypeError, ValueError):
            return AuthResult(
                success=False,
                handled=False,
            )

        username_matches = hmac.compare_digest(
            supplied_username,
            self._username,
        )
        password_matches = hmac.compare_digest(
            supplied_password,
            self._password,
        )

        if username_matches & password_matches:
            return AuthResult(
                success=True,
            )

        return AuthResult(
            success=False,
            handled=False,
        )


def _boolean(
    configuration,
    *keys: str,
    default: bool,
) -> bool:
    value = configuration.get(
        *keys,
        default=default,
    )

    if not isinstance(value, bool):
        setting = ".".join(keys)
        raise SMTPSecurityConfigError(
            f"{setting} must be true or false."
        )

    return value


def _text(
    configuration,
    *keys: str,
    default: str = "",
) -> str:
    value = configuration.get(
        *keys,
        default=default,
    )

    if value is None:
        return default

    if not isinstance(value, str):
        setting = ".".join(keys)
        raise SMTPSecurityConfigError(
            f"{setting} must be a string."
        )

    return value.strip()


def _required_text(
    configuration,
    *keys: str,
) -> str:
    value = _text(
        configuration,
        *keys,
    )

    if not value:
        setting = ".".join(keys)
        raise SMTPSecurityConfigError(
            f"{setting} must not be empty."
        )

    return value


def _read_password(
    configuration,
    environment: Mapping[str, str],
) -> bytes:
    password_env = _text(
        configuration,
        "smtp",
        "auth",
        "password_env",
    )
    password_file = _text(
        configuration,
        "smtp",
        "auth",
        "password_file",
    )

    if bool(password_env) == bool(password_file):
        raise SMTPSecurityConfigError(
            "Exactly one of smtp.auth.password_env or "
            "smtp.auth.password_file must be configured."
        )

    if password_env:
        if password_env not in environment:
            raise SMTPSecurityConfigError(
                "The environment variable named by "
                "smtp.auth.password_env is not set."
            )

        password = environment[password_env]

        if password == "":
            raise SMTPSecurityConfigError(
                "The environment variable named by "
                "smtp.auth.password_env is empty."
            )

        return password.encode("utf-8")

    path = Path(password_file)

    try:
        password = path.read_bytes()
    except (OSError, ValueError) as exc:
        raise SMTPSecurityConfigError(
            "smtp.auth.password_file could not be read."
        ) from exc

    if password.endswith(b"\r\n"):
        password = password[:-2]
    elif password.endswith(b"\n"):
        password = password[:-1]

    if not password:
        raise SMTPSecurityConfigError(
            "smtp.auth.password_file is empty."
        )

    return password


def _tls_context(
    certfile: str,
    keyfile: str,
) -> ssl.SSLContext:
    certificate = Path(certfile)
    private_key = Path(keyfile)

    if not certificate.is_file():
        raise SMTPSecurityConfigError(
            "smtp.tls.certfile does not exist or is not a file."
        )

    if not private_key.is_file():
        raise SMTPSecurityConfigError(
            "smtp.tls.keyfile does not exist or is not a file."
        )

    context = ssl.SSLContext(
        ssl.PROTOCOL_TLS_SERVER,
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_2

    try:
        context.load_cert_chain(
            certfile=certificate,
            keyfile=private_key,
        )
    except (OSError, ssl.SSLError, ValueError) as exc:
        raise SMTPSecurityConfigError(
            "smtp.tls.certfile and smtp.tls.keyfile could not be loaded."
        ) from exc

    return context


def load_smtp_security(
    configuration=config,
    *,
    environment: Mapping[str, str] | None = None,
) -> SMTPSecuritySettings:
    """Load, validate, and construct effective SMTP security settings."""

    if environment is None:
        environment = os.environ

    tls_enabled = _boolean(
        configuration,
        "smtp",
        "tls",
        "enabled",
        default=False,
    )
    auth_enabled = _boolean(
        configuration,
        "smtp",
        "auth",
        "enabled",
        default=False,
    )

    if auth_enabled and not tls_enabled:
        raise SMTPSecurityConfigError(
            "smtp.auth.enabled requires smtp.tls.enabled."
        )

    require_starttls = False
    context = None

    if tls_enabled:
        require_starttls = _boolean(
            configuration,
            "smtp",
            "tls",
            "require_starttls",
            default=True,
        )
        certfile = _required_text(
            configuration,
            "smtp",
            "tls",
            "certfile",
        )
        keyfile = _required_text(
            configuration,
            "smtp",
            "tls",
            "keyfile",
        )
        context = _tls_context(
            certfile,
            keyfile,
        )

    auth_required = False
    authenticator = None

    if auth_enabled:
        auth_required = _boolean(
            configuration,
            "smtp",
            "auth",
            "required",
            default=True,
        )
        username = _required_text(
            configuration,
            "smtp",
            "auth",
            "username",
        )
        password = _read_password(
            configuration,
            environment,
        )
        authenticator = SMTPAuthenticator(
            username,
            password,
        )

    return SMTPSecuritySettings(
        tls_enabled=tls_enabled,
        require_starttls=require_starttls,
        auth_enabled=auth_enabled,
        auth_required=auth_required,
        tls_context=context,
        authenticator=authenticator,
    )
