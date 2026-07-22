"""Release metadata invariants for v2.0.0."""

from pathlib import Path

from version import VERSION


ROOT = Path(__file__).resolve().parents[1]


def test_application_version_is_v200():
    assert VERSION == "2.0.0"


def test_readme_stable_and_next_release_are_current():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "stable-v2.0.0-blue" in readme
    assert "| **Current Stable Release** | **v2.0.0** |" in readme
    assert "| **Next Planned Release** | **v2.x** |" in readme


def test_changelog_contains_dated_release():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## 2.0.0 - 2026-07-22" in changelog
    assert changelog.index("## Unreleased") < changelog.index("## 2.0.0")


def test_release_notes_and_docker_hub_metadata_are_current():
    notes = ROOT / "docs" / "releases" / "v2.0.0.md"
    docker_hub = (ROOT / "DOCKERHUB_README.md").read_text(encoding="utf-8")
    assert notes.is_file()
    assert notes.read_text(encoding="utf-8").startswith(
        "# Notifinho v2.0.0 release notes"
    )
    assert "current stable release is **v2.0.0**" in docker_hub


def test_production_quick_starts_prepare_platform_state_mount():
    for path in (ROOT / "README.md", ROOT / "DOCKERHUB_README.md"):
        document = path.read_text(encoding="utf-8")
        assert "mkdir -p logs/emails secrets state" in document
        assert "chmod 700 logs logs/emails secrets state" in document


def test_release_notes_record_completed_publication_and_roadmap():
    notes = (ROOT / "docs" / "releases" / "v2.0.0.md").read_text(encoding="utf-8")
    assert "All roadmap issues listed above were closed as completed" in notes


def test_release_deployment_defaults_are_versioned():
    environment = (ROOT / ".env.example").read_text(encoding="utf-8")
    compose = (ROOT / "compose.production.yaml").read_text(encoding="utf-8")

    assert "NOTIFINHO_IMAGE=fortpt/notifinho:2.0.0" in environment
    assert "fortpt/notifinho:2.0.0" in compose


def test_release_notes_cover_upgrade_rollback_and_acceptance():
    notes = (ROOT / "docs" / "releases" / "v2.0.0.md").read_text(
        encoding="utf-8"
    )

    for heading in (
        "## Upgrade from v1.9.7",
        "## Compatibility boundary",
        "## Rollback",
        "## Release acceptance",
        "## Roadmap issue coverage",
    ):
        assert heading in notes
    for issue in (15, 16, 22, 49, 50, 51, 52, 53):
        assert f"#{issue}" in notes
