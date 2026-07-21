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
