"""Release metadata invariants for v1.9.7."""

from pathlib import Path

from version import VERSION


ROOT = Path(__file__).resolve().parents[1]


def test_application_version_is_v197():
    assert VERSION == "1.9.7"


def test_readme_stable_and_next_release_are_current():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "stable-v1.9.7-blue" in readme
    assert "| **Current Stable Release** | **v1.9.7** |" in readme
    assert "| **Next Planned Release** | **v2.0.0** |" in readme


def test_changelog_contains_dated_release():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## 1.9.7 - 2026-07-21" in changelog
    assert changelog.index("## Unreleased") < changelog.index("## 1.9.7")


def test_release_notes_and_docker_hub_metadata_are_current():
    notes = ROOT / "docs" / "releases" / "v1.9.7.md"
    docker_hub = (ROOT / "DOCKERHUB_README.md").read_text(encoding="utf-8")
    assert notes.is_file()
    assert notes.read_text(encoding="utf-8").startswith(
        "# Notifinho v1.9.7 release notes"
    )
    assert "current stable release is **v1.9.7**" in docker_hub
