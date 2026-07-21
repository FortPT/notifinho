"""Routing behavior shared by every notification source."""

from __future__ import annotations

import pytest

import router as router_module

from models import Notification
from router import Router


class Configuration:
    def __init__(self, data):
        self.data = data

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value


class RecordingOutput:
    def __init__(self):
        self.deliveries = []

    def send(self, notification, target):
        self.deliveries.append((notification, target))
        return True


@pytest.mark.parametrize("enabled", [False, None, "false", 0])
def test_disabled_output_is_not_called(monkeypatch, enabled):
    settings = {"routing": {"generic": {"outputs": [
        {"output": "discord", "target": "default"},
    ]}}}
    if enabled is not None:
        settings["outputs"] = {"discord": {"enabled": enabled}}
    else:
        settings["outputs"] = {"discord": {"enabled": None}}

    monkeypatch.setattr(router_module, "config", Configuration(settings))
    output = RecordingOutput()
    router = Router()
    router.outputs = {"discord": output}

    assert router.route(Notification(source="generic")) is False
    assert output.deliveries == []


@pytest.mark.parametrize("output_settings", [{"enabled": True}, {}])
def test_enabled_or_legacy_output_is_called(monkeypatch, output_settings):
    settings = {
        "outputs": {"discord": output_settings},
        "routing": {"generic": {"outputs": [
            {"output": "discord", "target": "default"},
        ]}},
    }
    monkeypatch.setattr(router_module, "config", Configuration(settings))
    output = RecordingOutput()
    router = Router()
    router.outputs = {"discord": output}
    notification = Notification(source="generic")

    assert router.route(notification) is True
    assert output.deliveries == [(notification, "default")]
