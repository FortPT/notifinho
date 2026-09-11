from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_routes_page_renders_capability_catalogue_without_removing_legacy_controls_yet():
    index = (ROOT / "src/webui/index.html").read_text(encoding="utf-8")
    service = (ROOT / "src/webui/service.py").read_text(encoding="utf-8")
    routing_path = ROOT / "src/webui/routing_v2.js"

    assert routing_path.exists(), "Routing V2 should use a dedicated late-loaded WebUI module"
    routing = routing_path.read_text(encoding="utf-8")

    assert '<div id="route-capability-catalogue"' in index
    assert '<script src="/ui/routing_v2.js" defer></script>' in index
    assert index.index('/ui/qa_patch.js') < index.index('/ui/routing_v2.js') < index.index('/ui/i18n.js')
    assert '"/ui/routing_v2.js"' in service

    assert "state.routeSourceOptions" in routing
    assert 'byId("route-capability-catalogue")' in routing
    assert 'capability.assignments || []' in routing
    assert '"Configured"' in routing
    assert '"Not configured"' in routing
    assert "routingV2LegacyRenderRoutes" in routing


def test_route_capability_catalogue_can_assign_an_existing_destination():
    routing = (ROOT / "src/webui/routing_v2.js").read_text(encoding="utf-8")

    assert '"Assign destination"' in routing
    assert '"Add destination"' in routing
    assert 'data-routing-v2-action' in routing
    assert '"assign-route-capability"' in routing
    assert "capabilityId: capability.id" in routing
    assert "routingV2AvailableDestinations" in routing
    assert 'request("/route-assignments"' in routing
    assert "capability_id: capabilityId" in routing
    assert "destination_id: destinationId" in routing
    assert "enabled: true" in routing
    assert "await loadWorkspace();" in routing
    assert 'document.addEventListener("click", routingV2HandleClick);' in routing


def test_routes_page_retires_legacy_route_creation_from_normal_flow():
    index = (ROOT / "src/webui/index.html").read_text(encoding="utf-8")
    routing = (ROOT / "src/webui/routing_v2.js").read_text(encoding="utf-8")

    assert '<tbody id="route-table">' in index
    assert "routingV2DisableLegacyCreation" in routing
    assert 'byId("add-route-button")' in routing
    assert "addRouteButton.remove();" in routing
