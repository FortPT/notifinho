"""Regression contract for retiring administrator-authored WebUI notices."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_administrator_announcement_composer_is_not_shipped():
    markup = (ROOT / "src" / "webui" / "index.html").read_text(encoding="utf-8")

    for identifier in (
        "notice-composer",
        "notice-form",
        "notice-id",
        "notice-name",
        "notice-status",
        "notice-message",
        "notice-submit",
    ):
        assert f'id="{identifier}"' not in markup

    # Genuine platform/system notices still have a dedicated presentation surface.
    assert 'id="notice-panel"' in markup
    assert 'id="notice-list"' in markup


def test_webui_renders_system_notices_without_announcement_authoring_actions():
    script = (ROOT / "src" / "webui" / "app.js").read_text(encoding="utf-8")

    # The API remains available for lifecycle-bound system notices, but human
    # administrator announcements are not presented in the customer workspace.
    assert 'item.kind !== "announcement"' in script
    assert 'byId("notice-form").addEventListener' not in script
    assert "function saveNotice(" not in script
    assert "function beginNoticeEdit(" not in script
    assert 'action === "edit-notice"' not in script
    assert 'action === "resolve-notice"' not in script

    # Users can still dismiss non-persistent system notices and follow their target.
    assert 'action === "dismiss-notice"' in script
    assert 'action === "open-notice-target"' in script
