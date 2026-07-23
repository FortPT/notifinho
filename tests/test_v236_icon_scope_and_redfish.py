"""v2.3.6 scopes icon enlargement and uses the official Redfish identity."""

from pathlib import Path

from webui.service import WebUIService


ROOT = Path(__file__).resolve().parents[1]


class Configuration:
    def get(self, *_keys, default=None):
        return default


def test_v236_uses_official_redfish_asset_without_changing_rest_aliases():
    script = (ROOT / "src/webui/app.js").read_text(encoding="utf-8")
    service = WebUIService(Configuration(), root=ROOT)

    assert 'redfish: "/ui/source-icons/redfish.jpg"' in script
    assert 'restful: "/ui/source-icons/rest-api.svg"' in script
    assert 'rest_api: "/ui/source-icons/rest-api.svg"' in script

    response = service.response("/ui/source-icons/redfish.jpg")
    assert response is not None and response.status == 200
    assert response.content_type == "image/jpeg"
    assert response.body.startswith(b"\xff\xd8")
    assert len(response.body) > 10_000


def test_v236_restores_normal_overview_icons_and_enlarges_only_requested_keys():
    css = (ROOT / "src/webui/enhancements.css").read_text(encoding="utf-8")

    default = css[
        css.index(".flow-node.source-node .source-product-icon {"):
        css.index("/* Only the explicitly requested products are enlarged. */")
    ]
    assert "height: 48px !important" in default
    assert "width: 48px !important" in default
    assert "transform: none !important" in default
    assert "height: 74px !important" not in css
    assert "min-height: 104px" not in css
    assert "grid-template-columns: minmax(250px" not in css

    for key in (
        "dell_idrac",
        "unifi_network",
        "unifi_protect",
        "qnap",
        "synology",
    ):
        assert f'data-source-key="{key}"' in css

    assert 'src*="notifinho"' in css
    assert 'data-source-key="redfish"' not in css
    assert 'data-source-key="xo"' not in css


def test_v236_retains_body_free_source_removal():
    script = (ROOT / "src/webui/app.js").read_text(encoding="utf-8")
    assert '`/source-categories/${encodeURIComponent(source)}`' in script
