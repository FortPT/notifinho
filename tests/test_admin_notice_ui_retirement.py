"""Regression contract for retiring administrator-authored WebUI notices."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_administrator_announcement_composer_is_removed_at_runtime():
    markup = (ROOT / "src" / "webui" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "src" / "webui" / "dashboard.js").read_text(encoding="utf-8")

    # The hidden element remains only long enough for the legacy app.js event
    # binding pass. The final presentation layer removes it before users can
    # interact with the authenticated workspace.
    assert 'id="notice-composer" class="panel notice-composer" hidden' in markup
    assert 'id="notice-panel"' in markup
    assert 'id="notice-list"' in markup
    assert 'const adminNoticeComposer = byId("notice-composer")' in script
    assert "adminNoticeComposer.remove()" in script


def test_webui_system_notice_renderer_excludes_human_announcements():
    script = (ROOT / "src" / "webui" / "dashboard.js").read_text(encoding="utf-8")

    assert 'item.kind !== "announcement"' in script
    assert "renderNotices = renderSystemNotices" in script
    assert 'actionButton("Edit", "edit-notice"' not in script

    # Lifecycle-bound platform notices keep their operational actions.
    assert '"open-notice-target"' in script
    assert '"dismiss-notice"' in script
