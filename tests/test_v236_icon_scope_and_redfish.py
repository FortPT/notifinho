"""v2.3.6 official Redfish identity and normal Overview baseline coverage."""

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


def test_v236_establishes_normal_overview_icon_and_card_baseline():
    css = (ROOT / "src/webui/enhancements.css").read_text(encoding="utf-8")

    assert ".flow-node.source-node" in css
    assert "min-height: 72px" in css
    assert "height: 48px !important" in css
    assert "width: 48px !important" in css
    assert "height: 74px !important" not in css
    assert "min-height: 104px" not in css
    assert "grid-template-columns: minmax(250px" not in css


def test_v240_source_removal_is_retired():
    script = (ROOT / "src/webui/app.js").read_text(encoding="utf-8")
    assert 'action === "remove-source"' not in script
    assert 'request("/integrations")' in script
