"""Previewable v2 platform adapters for every supported output type."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import socket
import base64

from dataclasses import dataclass
from urllib.parse import urlsplit

import requests

try:
    import paho.mqtt.publish as mqtt_publish
except ImportError:  # pragma: no cover - production requirements include paho
    mqtt_publish = None

from formatters.slack import SlackFormatter
from models import Notification
from outputs.discord import DiscordOutput
from outputs.platform_common import (
    decode_secret,
    event_identifier,
    http_delivery_result,
    notification_context,
    render_template,
    request_failure,
    safe_action_url,
    safe_event_envelope,
    secret_url,
    validate_network_host,
    validate_outbound_url,
)
from outputs.settings import normalize_output_settings
from outputs.teams import TeamsOutput
from storage.delivery import DeliveryResult
from storage.destinations import Destination


@dataclass(frozen=True)
class OutputPreview:
    output_type: str
    content_type: str
    payload: dict
    metadata: dict


class PlatformOutputAdapter:
    output_type = ""

    def preview(
        self,
        destination: Destination,
        notification: Notification,
    ) -> OutputPreview:
        raise NotImplementedError

    def deliver(
        self,
        destination: Destination,
        secret_value: bytes | None,
        notification: Notification,
    ) -> DeliveryResult:
        raise NotImplementedError

    def __call__(self, destination, secret_value, notification):
        return self.deliver(destination, secret_value, notification)


class _HTTPAdapter(PlatformOutputAdapter):
    def __init__(self, *, http_client=requests, resolver=socket.getaddrinfo):
        self.http_client = http_client
        self.resolver = resolver

    def _url(self, value, settings) -> str:
        return validate_outbound_url(
            value,
            allow_private_network=bool(settings.get("allow_private_network")),
            resolver=self.resolver,
        )

    def _post(self, url, *, payload, timeout, headers=None):
        try:
            response = self.http_client.post(
                url,
                json=payload,
                headers=headers,
                timeout=timeout,
            )
        except requests.RequestException as error:
            return request_failure(error)
        except Exception:
            return DeliveryResult(False, error_code="transport_error")
        return http_delivery_result(response)


class DiscordPlatformAdapter(_HTTPAdapter):
    output_type = "discord"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.output = DiscordOutput()

    def preview(self, destination, notification):
        settings = normalize_output_settings("discord", destination.settings)
        formatter = self.output.source_formatters.get(
            str(notification.source or "").casefold(),
            self.output.default_formatter,
        )
        if settings["components_v2"] and hasattr(formatter, "format_components_v2"):
            payload = formatter.format_components_v2(notification)
        else:
            payload = formatter.format(notification)
        payload = formatter._sanitize_payload(payload)
        return OutputPreview(
            "discord",
            "application/json",
            payload,
            {"formatter": formatter.__class__.__name__},
        )

    def deliver(self, destination, secret_value, notification):
        try:
            preview = self.preview(destination, notification)
            url = self._url(secret_url(secret_value), destination.settings)
            url = self.output._delivery_webhook(url, preview.payload)
        except ValueError:
            return DeliveryResult(False, error_code="invalid_destination")
        return self._post(url, payload=preview.payload, timeout=15)


class TeamsPlatformAdapter(_HTTPAdapter):
    output_type = "teams"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.output = TeamsOutput()

    def preview(self, destination, notification):
        normalize_output_settings("teams", destination.settings)
        formatter = self.output.source_formatters.get(
            str(notification.source or "").casefold(),
            self.output.default_formatter,
        )
        payload = formatter._sanitize_payload(formatter.format(notification))
        return OutputPreview(
            "teams",
            "application/json",
            payload,
            {"formatter": formatter.__class__.__name__},
        )

    def deliver(self, destination, secret_value, notification):
        try:
            preview = self.preview(destination, notification)
            url = self._url(secret_url(secret_value), destination.settings)
        except ValueError:
            return DeliveryResult(False, error_code="invalid_destination")
        return self._post(url, payload=preview.payload, timeout=15)


class SlackPlatformAdapter(_HTTPAdapter):
    output_type = "slack"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.formatter = SlackFormatter()

    def preview(self, destination, notification):
        settings = normalize_output_settings("slack", destination.settings)
        payload = self.formatter.format(
            notification,
            include_metadata=settings["include_metadata"],
        )
        return OutputPreview(
            "slack",
            "application/json",
            payload,
            {"formatter": self.formatter.__class__.__name__},
        )

    def deliver(self, destination, secret_value, notification):
        try:
            preview = self.preview(destination, notification)
            url = self._url(secret_url(secret_value), destination.settings)
            parsed_host = str(urlsplit(url).hostname or "")
            if parsed_host.casefold() not in {"hooks.slack.com", "hooks.slack-gov.com"}:
                raise ValueError("Slack webhook host is invalid")
        except ValueError:
            return DeliveryResult(False, error_code="invalid_destination")
        return self._post(url, payload=preview.payload, timeout=15)


class WebhookPlatformAdapter(_HTTPAdapter):
    output_type = "webhook"

    def preview(self, destination, notification):
        settings = normalize_output_settings(
            "webhook",
            destination.settings,
            require_complete=True,
        )
        template = settings.get("body_template")
        payload = (
            render_template(template, notification)
            if template is not None
            else safe_event_envelope(notification)
        )
        return OutputPreview(
            "webhook",
            "application/json",
            payload,
            {
                "method": settings["method"],
                "signed": settings["sign_hmac"],
            },
        )

    def deliver(self, destination, secret_value, notification):
        try:
            settings = normalize_output_settings(
                "webhook",
                destination.settings,
                require_complete=True,
            )
            preview = self.preview(destination, notification)
            credentials = decode_secret(secret_value)
            url = self._url(
                credentials.get("url") or credentials.get("value"),
                settings,
            )
            headers = {"Content-Type": "application/json", **settings["headers"]}
            secret_headers = credentials.get("headers", {})
            if secret_headers:
                if not isinstance(secret_headers, dict):
                    raise ValueError("secret headers must be an object")
                for key, value in secret_headers.items():
                    name = str(key or "").strip()
                    text = str(value or "").strip()
                    if (
                        not re.fullmatch(r"[A-Za-z0-9!#$%&'*+.^_`|~-]{1,64}", name)
                        or name.casefold() in {"host", "content-length", "transfer-encoding"}
                        or not text
                        or "\r" in text
                        or "\n" in text
                        or len(text) > 2048
                    ):
                        raise ValueError("secret header is invalid")
                    headers[name] = text
            body = json.dumps(
                preview.payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            headers["X-Notifinho-Idempotency-Key"] = event_identifier(notification)
            if settings["sign_hmac"]:
                signing_secret = credentials.get("hmac_secret")
                if not signing_secret:
                    raise ValueError("HMAC secret is required")
                digest = hmac.new(
                    str(signing_secret).encode("utf-8"),
                    body,
                    hashlib.sha256,
                ).hexdigest()
                headers["X-Notifinho-Signature"] = f"sha256={digest}"
            response = self.http_client.request(
                settings["method"],
                url,
                data=body,
                headers=headers,
                timeout=settings["timeout_seconds"],
            )
        except requests.RequestException as error:
            return request_failure(error)
        except ValueError:
            return DeliveryResult(False, error_code="invalid_destination")
        except Exception:
            return DeliveryResult(False, error_code="transport_error")
        return http_delivery_result(response)


class MQTTPlatformAdapter(PlatformOutputAdapter):
    output_type = "mqtt"

    def __init__(self, *, publisher=None, resolver=socket.getaddrinfo):
        self.publisher = publisher or (mqtt_publish.single if mqtt_publish else None)
        self.resolver = resolver

    def preview(self, destination, notification):
        settings = normalize_output_settings(
            "mqtt",
            destination.settings,
            require_complete=True,
        )
        topic = render_template(settings["topic"], notification)
        normalized = normalize_output_settings(
            "mqtt",
            {**settings, "topic": topic},
            require_complete=True,
        )
        return OutputPreview(
            "mqtt",
            "application/json",
            safe_event_envelope(notification),
            {
                "topic": normalized["topic"],
                "qos": normalized["qos"],
                "retain": normalized["retain"],
            },
        )

    def deliver(self, destination, secret_value, notification):
        if self.publisher is None:
            return DeliveryResult(False, error_code="adapter_dependency_unavailable")
        try:
            settings = normalize_output_settings(
                "mqtt",
                destination.settings,
                require_complete=True,
            )
            preview = self.preview(destination, notification)
            validate_network_host(
                settings["host"],
                settings["port"],
                allow_private_network=settings["allow_private_network"],
                resolver=self.resolver,
            )
            credentials = decode_secret(secret_value)
            username = credentials.get("username")
            password = credentials.get("password")
            if password and not username:
                raise ValueError("MQTT username is required with a password")
            auth = (
                {"username": str(username), "password": str(password or "")}
                if username
                else None
            )
            body = json.dumps(
                preview.payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            self.publisher(
                preview.metadata["topic"],
                payload=body,
                qos=settings["qos"],
                retain=settings["retain"],
                hostname=settings["host"],
                port=settings["port"],
                client_id=settings.get("client_id", ""),
                keepalive=settings["keepalive_seconds"],
                auth=auth,
                tls={} if settings["tls"] else None,
            )
        except ValueError:
            return DeliveryResult(False, error_code="invalid_destination")
        except (OSError, TimeoutError):
            return DeliveryResult(
                False,
                retryable=True,
                error_code="transport_unavailable",
            )
        except Exception:
            return DeliveryResult(False, error_code="transport_error")
        return DeliveryResult(True)


class NtfyPlatformAdapter(_HTTPAdapter):
    output_type = "ntfy"

    def preview(self, destination, notification):
        settings = normalize_output_settings(
            "ntfy",
            destination.settings,
            require_complete=True,
        )
        context = notification_context(notification)
        payload = {
            "topic": settings["topic"],
            "title": render_template(settings["title"], notification)[:256],
            "message": context["body"][:4096],
            "priority": settings["priority"],
            "tags": settings["tags"],
        }
        action = safe_action_url((notification.metadata or {}).get("action_link"))
        if settings["include_action"] and action:
            payload["actions"] = [
                {"action": "view", "label": "Open event", "url": action}
            ]
        return OutputPreview(
            "ntfy",
            "application/json",
            payload,
            {"server": settings["server"]},
        )

    def deliver(self, destination, secret_value, notification):
        try:
            settings = normalize_output_settings(
                "ntfy",
                destination.settings,
                require_complete=True,
            )
            preview = self.preview(destination, notification)
            url = self._url(settings["server"], settings)
            credentials = decode_secret(secret_value)
            headers = None
            token = credentials.get("token") or credentials.get("value")
            username = credentials.get("username")
            password = credentials.get("password")
            if token:
                headers = {"Authorization": f"Bearer {token}"}
            elif username:
                encoded = base64.b64encode(
                    f"{username}:{password or ''}".encode("utf-8")
                ).decode("ascii")
                headers = {"Authorization": f"Basic {encoded}"}
        except ValueError:
            return DeliveryResult(False, error_code="invalid_destination")
        return self._post(
            url,
            payload=preview.payload,
            timeout=settings["timeout_seconds"],
            headers=headers,
        )


class PlatformOutputRegistry:
    def __init__(self, adapters: list[PlatformOutputAdapter] | None = None):
        configured = (
            adapters
            if adapters is not None
            else [
                DiscordPlatformAdapter(),
                TeamsPlatformAdapter(),
                SlackPlatformAdapter(),
                WebhookPlatformAdapter(),
                MQTTPlatformAdapter(),
                NtfyPlatformAdapter(),
            ]
        )
        self.adapters = {adapter.output_type: adapter for adapter in configured}

    def get(self, output_type: str) -> PlatformOutputAdapter:
        try:
            return self.adapters[str(output_type).casefold()]
        except KeyError as error:
            raise KeyError("output adapter is unavailable") from error

    def delivery_adapters(self) -> dict[str, PlatformOutputAdapter]:
        return dict(self.adapters)
