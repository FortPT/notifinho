"""Release metadata invariants for v1.8.1."""

from pathlib import Path

from version import VERSION


ROOT = Path(__file__).resolve().parents[1]


def test_application_version_is_v181():
    assert VERSION == "1.8.1"


def test_readme_stable_and_next_release_are_current():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "stable-v1.8.1-blue" in readme
    assert "| **Current Stable Release** | **v1.8.1** |" in readme
    assert "| **Next Planned Release** | **v1.9.0** |" in readme


def test_changelog_contains_dated_release():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## 1.8.1 - 2026-07-15" in changelog
    assert changelog.index("## Unreleased") < changelog.index("## 1.8.1")


def test_release_notes_and_docker_hub_metadata_are_current():
    notes = ROOT / "docs" / "releases" / "v1.8.1.md"
    docker_hub = (ROOT / "DOCKERHUB_README.md").read_text(encoding="utf-8")
    assert notes.is_file()
    assert notes.read_text(encoding="utf-8").startswith(
        "# Notifinho v1.8.1 release notes"
    )
    assert "current stable release is **v1.8.1**" in docker_hub
