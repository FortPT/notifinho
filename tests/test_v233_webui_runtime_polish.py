"""v2.3.3 WebUI navigation, operations menu, source, test, update, and clock fixes."""

from pathlib import Path

from webui.service import SECURITY_HEADERS, WebUIService


ROOT = Path(__file__).resolve().parents[1]


class Configuration:
    def get(self, *_keys, default=None):
        return default


def test_webui_service_serves_v233_runtime_assets():
    service = WebUIService(Configuration(), root=ROOT)

    script = service.response("/ui/enhancements.js")
    assert script is not None and script.status == 200
    assert b"notifinho.active-view" in script.body
    assert b"sourceAwareCardSampleEvent" in script.body
    assert b"Check for updates" in script.body
    assert b"innerHTML" not in script.body

    stylesheet = service.response("/ui/enhancements.css")
    assert stylesheet is not None and stylesheet.status == 200
    assert b"#restart-header-button" in stylesheet.body
    assert b"background: transparent !important" in stylesheet.body


def test_v233_update_check_is_bounded_to_the_official_github_api():
    csp = dict(SECURITY_HEADERS)["Content-Security-Policy"]
    assert "connect-src 'self' https://api.github.com" in csp

    script = (ROOT / "src" / "webui" / "enhancements.js").read_text(
        encoding="utf-8"
    )
    assert "https://api.github.com/repos/FortPT/notifinho/releases/latest" in script
    assert "6 * 60 * 60 * 1000" in script
    assert 'credentials: "omit"' in script
    assert "visibilitychange" in script


def test_v233_runtime_polish_keeps_reload_source_tests_and_clock_source_aware():
    script = (ROOT / "src" / "webui" / "enhancements.js").read_text(
        encoding="utf-8"
    )
    assert "window.location.hash.slice(1)" in script
    assert "window.sessionStorage" in script
    assert "route.enabled && route.source === source" in script
    assert 'route.source !== "*"' in script
    assert 'sourceTestSample(route ? route.source : "notifinho"' in script
    assert 'provider: "Supermicro BMC"' in script
    assert "parseCanonicalTime" in script
    assert "displayClockTime" in script
    assert "platform-menu-popover" in script
