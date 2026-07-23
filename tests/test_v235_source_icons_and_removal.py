"""v2.3.5 source aliases and body-free removal compatibility coverage."""

from pathlib import Path

from webui.service import WebUIService


ROOT = Path(__file__).resolve().parents[1]


class Configuration:
    def get(self, *_keys, default=None):
        return default


def test_v235_serves_rest_and_redfish_icons_and_uses_source_aliases():
    service = WebUIService(Configuration(), root=ROOT)

    rest = service.response("/ui/source-icons/rest-api.svg")
    assert rest is not None and rest.status == 200
    assert rest.content_type == "image/svg+xml"
    assert b"REST" in rest.body

    redfish = service.response("/ui/source-icons/redfish.jpg")
    assert redfish is not None and redfish.status == 200
    assert redfish.content_type == "image/jpeg"
    assert redfish.body.startswith(b"\xff\xd8")

    script = (ROOT / "src/webui/app.js").read_text(encoding="utf-8")
    assert 'xo: "/ui/source-icons/xen-orchestra.png"' in script
    assert 'redfish: "/ui/source-icons/redfish.jpg"' in script
    assert 'restful: "/ui/source-icons/rest-api.svg"' in script
    assert 'rest_api: "/ui/source-icons/rest-api.svg"' in script
    assert 'dataset: { sourceKey: key }' in script
    assert 'xo: "Xen Orchestra"' in script
    assert 'redfish: "Redfish"' in script


def test_v235_overview_keeps_source_key_specific_large_icon_rules():
    css = (ROOT / "src/webui/enhancements.css").read_text(encoding="utf-8")
    for key in (
        "dell_idrac",
        "unifi_network",
        "unifi_protect",
        "qnap",
        "synology",
    ):
        assert f'data-source-key="{key}"' in css
    assert ".flow-node.source-node .source-product-icon" in css
    assert "height: 48px !important" in css
    assert "width: 48px !important" in css


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
