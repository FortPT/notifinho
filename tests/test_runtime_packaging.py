"""Container and process-lifecycle deployment invariants."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_production_image_uses_immutable_python_base_and_pinned_dependencies():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "FROM python:3.13.14-slim-bookworm@sha256:" in dockerfile
    for line in requirements.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            assert "==" in stripped


def test_start_script_execs_python_as_the_container_process():
    script = (ROOT / "start.sh").read_text(encoding="utf-8")

    assert "exec python3 main.py" in script


def test_production_compose_applies_runtime_hardening():
    compose = yaml.safe_load(
        (ROOT / "compose.production.yaml").read_text(encoding="utf-8")
    )
    service = compose["services"]["notifinho"]

    assert service["read_only"] is True
    assert service["init"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert service["user"] == "${NOTIFINHO_UID:-1000}:${NOTIFINHO_GID:-1000}"
    assert "${NOTIFINHO_STATE_DIR:-./state}:/notifinho/state" in service["volumes"]
    assert service["environment"]["NOTIFINHO_STATE_DIR"] == "/notifinho/state"


def test_public_configuration_enables_secure_webui_bootstrap_defaults():
    configuration = yaml.safe_load(
        (ROOT / "config" / "config.example.yaml").read_text(encoding="utf-8")
    )

    assert configuration["http"]["enabled"] is True
    assert configuration["api"]["enabled"] is True
    assert configuration["platform"]["enabled"] is True
    assert configuration["platform"]["secure_cookies"] is False
    assert configuration["webui"]["enforce_https"] is False
    assert configuration["platform"]["state_dir"] == (
        "/notifinho/config/platform-state"
    )
    assert configuration["webui"]["enabled"] is True


def test_ci_validates_webui_compose_and_production_image():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "actions/setup-node@v7" in workflow
    assert 'node-version: "24"' in workflow
    assert "package-manager-cache: false" in workflow
    assert "node --check src/webui/app.js" in workflow
    assert "docker compose -f compose.production.yaml config" in workflow
    assert "docker build --tag notifinho:ci ." in workflow
