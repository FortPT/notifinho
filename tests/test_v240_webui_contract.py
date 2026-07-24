"""Static WebUI contract for v2.4 integrations and safe destination editing."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_sources_are_built_in_integrations_without_status_removal_or_ids():
    markup = (ROOT / "src/webui/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/webui/app.js").read_text(encoding="utf-8")
    assert "<th>Integration</th><th>Available inputs</th><th>Category</th>" in markup
    source_block = script[script.index("function renderSources") : script.index("async function saveSourceCategory")]
    assert "state.integrations" in source_block
    assert "integration.inputs" in source_block
    assert "Built-in integration" in source_block
    assert "Inactive" not in source_block
    assert "remove-source" not in source_block
    assert 'text: source' not in source_block


def test_routes_use_integration_input_catalogue():
    markup = (ROOT / "src/webui/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/webui/app.js").read_text(encoding="utf-8")
    assert '<select id="route-source" required></select>' in markup
    assert 'request("/integrations")' in script
    assert "state.routeSourceOptions" in script
    assert 'input_type: inputType' in script
    assert 'setRouteSourceOptions(item ? item.source : "zabbix", item ? item.input_type : "smtp")' in script


def test_destination_type_is_dynamic_and_duplicate_submits_are_bounded():
    markup = (ROOT / "src/webui/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/webui/app.js").read_text(encoding="utf-8")
    assert 'id="destination-original-type"' in markup
    assert 'byId("destination-type").disabled = false' in script
    assert 'output_type: byId("destination-type").value' in script
    assert "A destination named" in script
    assert "submit.disabled = true" in script
    assert "New credentials are required because the destination type changed." in script


def test_api_errors_include_status_path_and_reference():
    script = (ROOT / "src/webui/app.js").read_text(encoding="utf-8")
    platform = (ROOT / "src/api/platform.py").read_text(encoding="utf-8")
    assert "HTTP ${status}" in script
    assert "reference ${reference}" in script
    assert '"code": "resource_conflict"' in platform
    assert '"reference": reference' in platform
    assert "Platform API request failed reference=%s path=%s" in platform
