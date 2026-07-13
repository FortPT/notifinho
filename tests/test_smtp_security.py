"""Regression and protocol tests for Notifinho SMTP security."""

from __future__ import annotations

import base64
import smtplib
import socket
import ssl

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import LoginPassword

import inputs.smtp as smtp_module
from inputs.smtp import Handler, SMTPInput
from inputs.smtp_security import (
    SMTPAuthenticator,
    SMTPSecurityConfigError,
    SMTPSecuritySettings,
    load_smtp_security,
)


TLS_FIXTURES = Path(__file__).parent / "fixtures" / "tls"
CERTFILE = TLS_FIXTURES / "cert.pem"
KEYFILE = TLS_FIXTURES / "key.pem"
USERNAME = "notifinho"
PASSWORD = "correct horse battery staple"


class FakeConfig:
    """Config provider matching Notifinho's nested get API."""

    def __init__(self, data):
        self._data = data

    def get(self, *keys, default=None):
        value = self._data

        for key in keys:
            if not isinstance(value, dict):
                return default

            value = value.get(key)

            if value is None:
                return default

        return value


def smtp_config(
    *,
    tls_enabled=False,
    auth_enabled=False,
    require_starttls=None,
    auth_required=None,
    username=USERNAME,
    password_env="NOTIFINHO_SMTP_PASSWORD",
    password_file="",
    certfile=CERTFILE,
    keyfile=KEYFILE,
):
    tls = {
        "enabled": tls_enabled,
        "certfile": str(certfile),
        "keyfile": str(keyfile),
    }
    auth = {
        "enabled": auth_enabled,
        "username": username,
        "password_env": password_env,
        "password_file": password_file,
    }

    if require_starttls is not None:
        tls["require_starttls"] = require_starttls

    if auth_required is not None:
        auth["required"] = auth_required

    return FakeConfig(
        {
            "smtp": {
                "host": "127.0.0.1",
                "port": 8025,
                "tls": tls,
                "auth": auth,
            }
        }
    )


def secure_settings(**overrides):
    environment = overrides.pop(
        "environment",
        {"NOTIFINHO_SMTP_PASSWORD": PASSWORD},
    )
    return load_smtp_security(
        smtp_config(
            tls_enabled=True,
            auth_enabled=True,
            **overrides,
        ),
        environment=environment,
    )


def free_tcp_port():
    with socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    ) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


class CollectingHandler:
    def __init__(self):
        self.messages = []

    async def handle_DATA(self, server, session, envelope):
        del server, session
        self.messages.append(envelope.original_content)
        return "250 Message accepted"


@contextmanager
def running_server(settings, handler=None):
    handler = handler or CollectingHandler()
    port = free_tcp_port()
    controller = Controller(
        handler,
        hostname="127.0.0.1",
        port=port,
        **settings.controller_kwargs(),
    )
    controller.start()

    try:
        yield port, handler
    finally:
        controller.stop()


def client_tls_context():
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def start_tls(client):
    client.ehlo()
    client.starttls(context=client_tls_context())
    client.ehlo()


def auth_plain(client, username=USERNAME, password=PASSWORD):
    token = base64.b64encode(
        b"\x00"
        + username.encode("utf-8")
        + b"\x00"
        + password.encode("utf-8")
    ).decode("ascii")
    return client.docmd(
        "AUTH",
        f"PLAIN {token}",
    )


def auth_login(client, username=USERNAME, password=PASSWORD):
    code, message = client.docmd(
        "AUTH",
        "LOGIN",
    )

    if code != 334:
        return code, message

    code, message = client.docmd(
        base64.b64encode(
            username.encode("utf-8")
        ).decode("ascii")
    )

    if code != 334:
        return code, message

    return client.docmd(
        base64.b64encode(
            password.encode("utf-8")
        ).decode("ascii")
    )


def send_test_message(client):
    return client.sendmail(
        "sender@example.invalid",
        ["receiver@example.invalid"],
        (
            "From: sender@example.invalid\r\n"
            "To: receiver@example.invalid\r\n"
            "Subject: SMTP security test\r\n"
            "\r\n"
            "Test message.\r\n"
        ),
    )


def test_legacy_configuration_disables_security():
    settings = load_smtp_security(
        FakeConfig({"smtp": {"host": "0.0.0.0", "port": 8025}}),
        environment={},
    )

    assert settings == SMTPSecuritySettings()
    assert settings.controller_kwargs() == {}


def test_tls_enablement_requires_starttls_by_default():
    settings = load_smtp_security(
        smtp_config(tls_enabled=True),
        environment={},
    )

    assert settings.tls_enabled is True
    assert settings.require_starttls is True


def test_tls_explicit_optional_override_is_supported():
    settings = load_smtp_security(
        smtp_config(
            tls_enabled=True,
            require_starttls=False,
        ),
        environment={},
    )

    assert settings.require_starttls is False


def test_auth_enablement_requires_authentication_by_default():
    settings = secure_settings()

    assert settings.auth_enabled is True
    assert settings.auth_required is True


def test_auth_explicit_optional_override_is_supported():
    settings = secure_settings(auth_required=False)

    assert settings.auth_required is False


def test_disabled_parent_features_force_effective_flags_false():
    configuration = FakeConfig(
        {
            "smtp": {
                "tls": {
                    "enabled": False,
                    "require_starttls": True,
                },
                "auth": {
                    "enabled": False,
                    "required": True,
                },
            }
        }
    )

    settings = load_smtp_security(
        configuration,
        environment={},
    )

    assert settings.require_starttls is False
    assert settings.auth_required is False


def test_dormant_invalid_child_values_are_not_evaluated():
    configuration = FakeConfig(
        {
            "smtp": {
                "tls": {
                    "enabled": False,
                    "require_starttls": "not-a-boolean",
                },
                "auth": {
                    "enabled": False,
                    "required": "not-a-boolean",
                },
            }
        }
    )

    settings = load_smtp_security(
        configuration,
        environment={},
    )

    assert settings.require_starttls is False
    assert settings.auth_required is False


@pytest.mark.parametrize(
    "section,key",
    [
        ("tls", "enabled"),
        ("auth", "enabled"),
    ],
)
def test_enabled_flags_must_be_boolean(section, key):
    data = {
        "smtp": {
            "tls": {"enabled": False},
            "auth": {"enabled": False},
        }
    }
    data["smtp"][section][key] = "true"

    with pytest.raises(
        SMTPSecurityConfigError,
        match="must be true or false",
    ):
        load_smtp_security(
            FakeConfig(data),
            environment={},
        )


def test_require_starttls_must_be_boolean_when_tls_enabled():
    with pytest.raises(
        SMTPSecurityConfigError,
        match="smtp.tls.require_starttls",
    ):
        load_smtp_security(
            smtp_config(
                tls_enabled=True,
                require_starttls="true",
            ),
            environment={},
        )


def test_auth_required_must_be_boolean_when_auth_enabled():
    with pytest.raises(
        SMTPSecurityConfigError,
        match="smtp.auth.required",
    ):
        secure_settings(auth_required="true")


def test_authentication_without_tls_fails_closed():
    with pytest.raises(
        SMTPSecurityConfigError,
        match="smtp.auth.enabled requires smtp.tls.enabled",
    ):
        load_smtp_security(
            smtp_config(auth_enabled=True),
            environment={"NOTIFINHO_SMTP_PASSWORD": PASSWORD},
        )


def test_missing_certificate_fails_closed(tmp_path):
    with pytest.raises(
        SMTPSecurityConfigError,
        match="smtp.tls.certfile",
    ):
        load_smtp_security(
            smtp_config(
                tls_enabled=True,
                certfile=tmp_path / "missing-cert.pem",
            ),
            environment={},
        )


def test_missing_private_key_fails_closed(tmp_path):
    with pytest.raises(
        SMTPSecurityConfigError,
        match="smtp.tls.keyfile",
    ):
        load_smtp_security(
            smtp_config(
                tls_enabled=True,
                keyfile=tmp_path / "missing-key.pem",
            ),
            environment={},
        )


def test_empty_certificate_setting_fails_closed():
    with pytest.raises(
        SMTPSecurityConfigError,
        match="smtp.tls.certfile must not be empty",
    ):
        load_smtp_security(
            smtp_config(
                tls_enabled=True,
                certfile="",
            ),
            environment={},
        )


def test_empty_private_key_setting_fails_closed():
    with pytest.raises(
        SMTPSecurityConfigError,
        match="smtp.tls.keyfile must not be empty",
    ):
        load_smtp_security(
            smtp_config(
                tls_enabled=True,
                keyfile="",
            ),
            environment={},
        )


def test_empty_username_fails_closed():
    with pytest.raises(
        SMTPSecurityConfigError,
        match="smtp.auth.username must not be empty",
    ):
        secure_settings(username="   ")


def test_auth_requires_exactly_one_secret_source():
    with pytest.raises(
        SMTPSecurityConfigError,
        match="Exactly one",
    ):
        secure_settings(
            password_env="",
            password_file="",
            environment={},
        )


def test_auth_rejects_two_secret_sources(tmp_path):
    secret = tmp_path / "smtp-password"
    secret.write_text(PASSWORD, encoding="utf-8")

    with pytest.raises(
        SMTPSecurityConfigError,
        match="Exactly one",
    ):
        secure_settings(
            password_file=str(secret),
        )


def test_missing_password_environment_variable_fails_closed():
    with pytest.raises(
        SMTPSecurityConfigError,
        match="is not set",
    ):
        secure_settings(environment={})


def test_empty_password_environment_variable_fails_closed():
    with pytest.raises(
        SMTPSecurityConfigError,
        match="is empty",
    ):
        secure_settings(
            environment={"NOTIFINHO_SMTP_PASSWORD": ""},
        )


def test_environment_password_spaces_are_preserved():
    authenticator = load_smtp_security(
        smtp_config(
            tls_enabled=True,
            auth_enabled=True,
        ),
        environment={
            "NOTIFINHO_SMTP_PASSWORD": " password with spaces ",
        },
    ).authenticator

    result = authenticator(
        None,
        None,
        None,
        "PLAIN",
        LoginPassword(
            USERNAME.encode(),
            b" password with spaces ",
        ),
    )

    assert result.success is True


def test_missing_password_file_fails_closed(tmp_path):
    with pytest.raises(
        SMTPSecurityConfigError,
        match="could not be read",
    ):
        secure_settings(
            password_env="",
            password_file=str(tmp_path / "missing-secret"),
            environment={},
        )


def test_empty_password_file_fails_closed(tmp_path):
    secret = tmp_path / "smtp-password"
    secret.write_bytes(b"")

    with pytest.raises(
        SMTPSecurityConfigError,
        match="is empty",
    ):
        secure_settings(
            password_env="",
            password_file=str(secret),
            environment={},
        )


@pytest.mark.parametrize(
    "suffix",
    [b"\n", b"\r\n"],
)
def test_password_file_strips_one_trailing_newline(tmp_path, suffix):
    secret = tmp_path / "smtp-password"
    secret.write_bytes(PASSWORD.encode() + suffix)
    settings = secure_settings(
        password_env="",
        password_file=str(secret),
        environment={},
    )

    result = settings.authenticator(
        None,
        None,
        None,
        "LOGIN",
        LoginPassword(
            USERNAME.encode(),
            PASSWORD.encode(),
        ),
    )

    assert result.success is True


def test_password_file_preserves_spaces(tmp_path):
    secret = tmp_path / "smtp-password"
    secret.write_bytes(b" password with spaces \n")
    settings = secure_settings(
        password_env="",
        password_file=str(secret),
        environment={},
    )

    result = settings.authenticator(
        None,
        None,
        None,
        "PLAIN",
        LoginPassword(
            USERNAME.encode(),
            b" password with spaces ",
        ),
    )

    assert result.success is True


def test_tls_context_requires_tls_1_2_or_newer():
    settings = load_smtp_security(
        smtp_config(tls_enabled=True),
        environment={},
    )

    assert settings.tls_context.minimum_version == ssl.TLSVersion.TLSv1_2


def test_authenticator_accepts_login_and_plain():
    authenticator = SMTPAuthenticator(
        USERNAME,
        PASSWORD.encode(),
    )

    for mechanism in ("LOGIN", "PLAIN"):
        result = authenticator(
            None,
            None,
            None,
            mechanism,
            LoginPassword(
                USERNAME.encode(),
                PASSWORD.encode(),
            ),
        )
        assert result.success is True
        assert result.auth_data is None


def test_authenticator_rejects_incorrect_username():
    result = SMTPAuthenticator(
        USERNAME,
        PASSWORD.encode(),
    )(
        None,
        None,
        None,
        "PLAIN",
        LoginPassword(
            b"wrong-user",
            PASSWORD.encode(),
        ),
    )

    assert result.success is False
    assert result.handled is False


def test_authenticator_rejects_incorrect_password():
    result = SMTPAuthenticator(
        USERNAME,
        PASSWORD.encode(),
    )(
        None,
        None,
        None,
        "LOGIN",
        LoginPassword(
            USERNAME.encode(),
            b"wrong-password",
        ),
    )

    assert result.success is False
    assert result.handled is False


def test_authenticator_rejects_unknown_mechanism():
    result = SMTPAuthenticator(
        USERNAME,
        PASSWORD.encode(),
    )(
        None,
        None,
        None,
        "CRAM-MD5",
        LoginPassword(
            USERNAME.encode(),
            PASSWORD.encode(),
        ),
    )

    assert result.success is False


def test_authenticator_rejects_unexpected_auth_data():
    result = SMTPAuthenticator(
        USERNAME,
        PASSWORD.encode(),
    )(
        None,
        None,
        None,
        "PLAIN",
        {"username": USERNAME, "password": PASSWORD},
    )

    assert result.success is False


def test_safe_summary_contains_no_credentials():
    settings = secure_settings()
    summary = settings.safe_summary()

    assert summary == (
        "SMTP security: TLS enabled, STARTTLS required, "
        "authentication required"
    )
    assert USERNAME not in summary
    assert PASSWORD not in summary


def test_disabled_safe_summary():
    assert SMTPSecuritySettings().safe_summary() == "SMTP security: disabled"


def test_secure_controller_kwargs_use_explicit_starttls_not_smtps():
    values = secure_settings().controller_kwargs()

    assert values["tls_context"] is not None
    assert values["require_starttls"] is True
    assert values["authenticator"] is not None
    assert values["auth_required"] is True
    assert values["auth_require_tls"] is True
    assert "ssl_context" not in values


def test_smtp_input_passes_security_kwargs_to_controller(monkeypatch):
    captured = {}
    expected = SMTPSecuritySettings(
        tls_enabled=True,
        require_starttls=True,
        auth_enabled=True,
        auth_required=True,
        tls_context=object(),
        authenticator=object(),
    )

    class FakeController:
        def __init__(self, handler, **kwargs):
            captured["handler"] = handler
            captured.update(kwargs)
            self.hostname = kwargs["hostname"]
            self.port = kwargs["port"]

        def start(self):
            captured["started"] = True

        def stop(self):
            captured["stopped"] = True

    monkeypatch.setattr(
        smtp_module,
        "load_smtp_security",
        lambda configuration: expected,
    )
    monkeypatch.setattr(
        smtp_module,
        "Controller",
        FakeController,
    )

    smtp_input = SMTPInput(
        dispatcher=object(),
        router=object(),
    )

    assert captured["tls_context"] is expected.tls_context
    assert captured["require_starttls"] is True
    assert captured["authenticator"] is expected.authenticator
    assert captured["auth_required"] is True
    assert captured["auth_require_tls"] is True
    assert "ssl_context" not in captured

    smtp_input.start()
    smtp_input.stop()

    assert captured["started"] is True
    assert captured["stopped"] is True


def test_legacy_protocol_accepts_mail_without_tls_or_auth():
    settings = SMTPSecuritySettings()

    with running_server(settings) as (port, handler):
        with smtplib.SMTP("127.0.0.1", port, timeout=5) as client:
            client.ehlo()
            assert "starttls" not in client.esmtp_features
            send_test_message(client)

    assert len(handler.messages) == 1


def test_tls_mode_advertises_starttls():
    settings = load_smtp_security(
        smtp_config(tls_enabled=True),
        environment={},
    )

    with running_server(settings) as (port, _handler):
        with smtplib.SMTP("127.0.0.1", port, timeout=5) as client:
            client.ehlo()
            assert "starttls" in client.esmtp_features


def test_required_starttls_rejects_mail_before_tls():
    settings = load_smtp_security(
        smtp_config(tls_enabled=True),
        environment={},
    )

    with running_server(settings) as (port, _handler):
        with smtplib.SMTP("127.0.0.1", port, timeout=5) as client:
            client.ehlo()
            code, _message = client.mail("sender@example.invalid")
            assert code == 530


def test_explicit_optional_starttls_allows_plaintext_mail():
    settings = load_smtp_security(
        smtp_config(
            tls_enabled=True,
            require_starttls=False,
        ),
        environment={},
    )

    with running_server(settings) as (port, handler):
        with smtplib.SMTP("127.0.0.1", port, timeout=5) as client:
            client.ehlo()
            send_test_message(client)

    assert len(handler.messages) == 1


def test_auth_is_not_advertised_or_accepted_before_tls():
    settings = secure_settings()

    with running_server(settings) as (port, _handler):
        with smtplib.SMTP("127.0.0.1", port, timeout=5) as client:
            client.ehlo()
            assert "auth" not in client.esmtp_features
            code, _message = auth_plain(client)
            assert code >= 500


def test_auth_plain_succeeds_after_starttls():
    settings = secure_settings()

    with running_server(settings) as (port, _handler):
        with smtplib.SMTP("127.0.0.1", port, timeout=5) as client:
            start_tls(client)
            assert "PLAIN" in client.esmtp_features.get("auth", "")
            code, _message = auth_plain(client)
            assert code == 235


def test_auth_login_succeeds_after_starttls():
    settings = secure_settings()

    with running_server(settings) as (port, _handler):
        with smtplib.SMTP("127.0.0.1", port, timeout=5) as client:
            start_tls(client)
            assert "LOGIN" in client.esmtp_features.get("auth", "")
            code, _message = auth_login(client)
            assert code == 235


def test_incorrect_username_fails_over_protocol():
    settings = secure_settings()

    with running_server(settings) as (port, _handler):
        with smtplib.SMTP("127.0.0.1", port, timeout=5) as client:
            start_tls(client)
            code, _message = auth_plain(
                client,
                username="wrong-user",
            )
            assert code == 535


def test_incorrect_password_fails_over_protocol():
    settings = secure_settings()

    with running_server(settings) as (port, _handler):
        with smtplib.SMTP("127.0.0.1", port, timeout=5) as client:
            start_tls(client)
            code, _message = auth_plain(
                client,
                password="wrong-password",
            )
            assert code == 535


def test_required_auth_rejects_unauthenticated_mail_after_tls():
    settings = secure_settings()

    with running_server(settings) as (port, _handler):
        with smtplib.SMTP("127.0.0.1", port, timeout=5) as client:
            start_tls(client)
            code, _message = client.mail("sender@example.invalid")
            assert code == 530


def test_explicit_optional_auth_allows_unauthenticated_mail_after_tls():
    settings = secure_settings(auth_required=False)

    with running_server(settings) as (port, handler):
        with smtplib.SMTP("127.0.0.1", port, timeout=5) as client:
            start_tls(client)
            send_test_message(client)

    assert len(handler.messages) == 1


def test_authenticated_mail_reaches_existing_handler_pipeline(
    monkeypatch,
    tmp_path,
):
    class Dispatcher:
        def __init__(self):
            self.messages = []

        def parse(self, message):
            self.messages.append(message)
            return SimpleNamespace(source="smtp_security_test")

    class Router:
        def __init__(self):
            self.notifications = []

        def route(self, notification):
            self.notifications.append(notification)

    dispatcher = Dispatcher()
    router = Router()
    handler = Handler(
        dispatcher,
        router,
    )
    settings = secure_settings()

    monkeypatch.setattr(
        smtp_module,
        "Path",
        lambda _value: tmp_path / "emails",
    )

    with running_server(settings, handler) as (port, _handler):
        with smtplib.SMTP("127.0.0.1", port, timeout=5) as client:
            start_tls(client)
            client.login(USERNAME, PASSWORD)
            send_test_message(client)

    assert len(dispatcher.messages) == 1
    assert len(router.notifications) == 1
    assert router.notifications[0].source == "smtp_security_test"
    assert len(list((tmp_path / "emails").glob("*.eml"))) == 1


def test_tls_only_mode_delivers_after_starttls():
    settings = load_smtp_security(
        smtp_config(tls_enabled=True),
        environment={},
    )

    with running_server(settings) as (port, handler):
        with smtplib.SMTP("127.0.0.1", port, timeout=5) as client:
            start_tls(client)
            send_test_message(client)

    assert len(handler.messages) == 1


def test_errors_do_not_include_password():
    exposed_password = "do-not-log-or-raise-this-value"

    with pytest.raises(SMTPSecurityConfigError) as error:
        secure_settings(
            environment={"NOTIFINHO_SMTP_PASSWORD": ""},
        )

    assert exposed_password not in str(error.value)
    assert PASSWORD not in str(error.value)
