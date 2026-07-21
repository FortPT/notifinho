"""Permanent v1.9.7 release icon wiring regressions."""

import json
from pathlib import Path

from models import Notification
from outputs.discord import DiscordOutput
import outputs.discord as discord_output_module


ROOT = Path(__file__).resolve().parents[1]


def notification():
    item = Notification(
        source="synology",
        title="Storage Pool Degraded",
        body="Storage Pool 1 entered a degraded state.",
        category="storage",
        status="warning",
    )
    item.metadata = {
        "nas_name": "NAS-02",
        "severity": "warning",
        "event_time": "2026-07-21T03:38:00+01:00",
        "message": "Storage Pool 1 entered a degraded state.",
    }
    return item


def find_thumbnail_media(value):
    if isinstance(value, dict):
        if value.get("type") == 11 and isinstance(value.get("media"), dict):
            return value["media"]
        for child in value.values():
            found = find_thumbnail_media(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_thumbnail_media(child)
            if found is not None:
                return found
    return None


def test_official_release_build_pins_icon_base_to_checked_out_commit():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    workflow = (
        ROOT / ".github" / "workflows" / "docker-release.yml"
    ).read_text(encoding="utf-8")

    assert "ARG NOTIFINHO_ICON_BASE_URL=" in dockerfile
    assert "FortPT/notifinho/main/assets/icons" in dockerfile
    assert 'ENV NOTIFINHO_ICON_BASE_URL="${NOTIFINHO_ICON_BASE_URL}"' in dockerfile
    assert "id: release" in workflow
    assert "icon_base_url=${ICON_BASE_URL}" in workflow
    assert "${GITHUB_REPOSITORY}/${HEAD_SHA}/assets/icons" in workflow
    assert "NOTIFINHO_ICON_BASE_URL=${{ steps.release.outputs.icon_base_url }}" in workflow


def test_components_v2_delivery_uploads_packaged_icon(monkeypatch, tmp_path):
    icon = tmp_path / "synology.png"
    icon.write_bytes(b"synthetic-png")
    captured = {}

    class Config:
        def get(self, *keys, default=None):
            if keys[-1:] == ("webhook",):
                return "https://discord.com/api/webhooks/123/token"
            return default

    class Response:
        status_code = 204
        text = ""

    def fake_post(url, data, files, timeout):
        captured["url"] = url
        captured["payload"] = json.loads(data["payload_json"])
        captured["filename"] = files["files[0]"][0]
        captured["content"] = files["files[0]"][1].read()
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(discord_output_module, "config", Config())
    monkeypatch.setattr(discord_output_module.requests, "post", fake_post)

    output = DiscordOutput()
    output.ICON_DIR = tmp_path
    assert output.send(notification(), target="synology")

    payload = captured["payload"]
    media = find_thumbnail_media(payload["components"])
    assert media == {"url": "attachment://synology.png"}
    assert payload["attachments"] == [{"id": 0, "filename": "synology.png"}]
    assert captured["filename"] == "synology.png"
    assert captured["content"] == b"synthetic-png"
    assert payload["flags"] == 32768
    assert captured["timeout"] == 15
