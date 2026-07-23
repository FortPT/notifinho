"""v2.3.5 source icon aliases, sizing, and body-free removal coverage."""

from pathlib import Path

from webui.service import WebUIService


ROOT = Path(__file__).resolve().parents[1]


class Configuration:
    def get(self, *_keys, default=None):
        return default


def test_v235_serves_rest_api_icon_and_uses_source_aliases():
    service = WebUIService(Configuration(), root=ROOT)
    response = service.response("/ui/source-icons/rest-api.svg")
    assert response is not None and response.status == 200
    assert response.content_type == "image/svg+xml"
    assert b"REST" in response.body

    script = (ROOT / "src/webui/app.js").read_text(encoding="utf-8")
    assert 'xo: "/ui/source-icons/xen-orchestra.png"' in script
    assert 'redfish: "/ui/source-icons/rest-api.svg"' in script
    assert 'dataset: { sourceKey: key }' in script
    assert 'xo: "Xen Orchestra"' in script
    assert 'redfish: "Redfish"' in script


def test_v235_overview_uses_source_key_specific_large_icon_rules():
    css = (ROOT / "src/webui/enhancements.css").read_text(encoding="utf-8")
    for key in (
        "dell_idrac",
        "unifi_network",
        "unifi_protect",
        "qnap",
        "synology",
    ):
        assert f'data-source-key="{key}"' in css
    assert "width: 112px !important" in css
    assert "height: 92px !important" in css
    assert "width: 104px !important" in css
    assert "height: 88px !important" in css


def test_v235_source_removal_does_not_depend_on_delete_request_body():
    script = (ROOT / "src/webui/app.js").read_text(encoding="utf-8")
    platform = (ROOT / "src/api/platform.py").read_text(encoding="utf-8")

    assert '`/source-categories/${encodeURIComponent(source)}`' in script
    assert 'body: { source }' not in script[
        script.index('} else if (action === "remove-source")'):
        script.index('} else if (action === "restore-backup")')
    ]
    assert 'path.startswith("/api/v2/source-categories/")' in platform
    assert "unquote(" in platform
    assert 'method == "DELETE"' in platform
