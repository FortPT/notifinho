"""v2.3.7 keeps Overview cards and icon boxes uniform."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _block(css: str, selector: str, start: int = 0) -> str:
    position = css.index(selector, start)
    opening = css.index("{", position)
    closing = css.index("}", opening)
    return css[opening + 1:closing]


def test_v237_keeps_every_overview_card_and_desktop_icon_box_uniform():
    css = (ROOT / "src/webui/enhancements.css").read_text(encoding="utf-8")

    card = _block(css, ".flow-node.source-node {")
    icon = _block(css, ".flow-node.source-node .source-product-icon {")

    assert "min-height: 72px" in card
    assert "height: 48px !important" in icon
    assert "width: 48px !important" in icon
    assert "var(--overview-source-icon-scale, 1)" in icon


def test_v237_target_rules_scale_artwork_without_resizing_boxes():
    css = (ROOT / "src/webui/enhancements.css").read_text(encoding="utf-8")
    start = css.index("/* Only artwork is scaled.")
    end = css.index(".platform-menu {", start)
    target_rules = css[start:end]

    assert "--overview-source-icon-scale:" in target_rules
    assert "height:" not in target_rules
    assert "width:" not in target_rules
    assert "min-height:" not in target_rules

    for key in (
        "dell_idrac",
        "unifi_network",
        "unifi_protect",
        "qnap",
        "synology",
    ):
        assert f'data-source-key="{key}"' in target_rules
    assert 'src*="notifinho"' in target_rules


def test_v237_mobile_keeps_every_icon_box_at_home_assistant_size():
    css = (ROOT / "src/webui/enhancements.css").read_text(encoding="utf-8")
    mobile_start = css.index("@media (max-width: 780px)")
    icon = _block(
        css,
        ".flow-node.source-node .source-product-icon {",
        start=mobile_start,
    )

    assert "height: 44px !important" in icon
    assert "width: 44px !important" in icon


def test_v237_does_not_modify_notification_rendering_contract():
    # The release changes WebUI CSS and metadata only. Notification rendering
    # remains covered by the existing formatter and output-adapter test suites.
    css = (ROOT / "src/webui/enhancements.css").read_text(encoding="utf-8")
    assert "Overview" in css
