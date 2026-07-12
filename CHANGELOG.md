# Changelog

## Unreleased (v1.3.0)

### Added

- Initial QNAP QTS and QuTS hero email detection and parser.
- QNAP event classification for storage, security, backup, system, power,
  and generic notifications.
- QNAP-specific Discord embed and Microsoft Teams Adaptive Card formatters.
- Seven synthetic QNAP `.eml` fixtures covering Notification Center tests,
  login security, storage/RAID, disk/SMART, HBS backup, updates, and UPS power
  events.
- Local SMTP fixture replay utility with development defaults for port `8026`.
- QNAP routing examples and integration documentation.
- Dedicated QNAP source routing for Discord and Microsoft Teams targets.
- Pytest coverage for QNAP detection, parsing, formatting, and existing-source
  selection regressions.
- Initial Grafana Alerting email detection and parser.
- Grafana event handling for test, firing, resolved, pending, No Data,
  datasource/evaluation error, and grouped alert notifications.
- Grafana-specific Discord embed and Microsoft Teams Adaptive Card formatters.
- Seven synthetic Grafana `.eml` fixtures covering plain-text, HTML, and
  multipart alert layouts.
- Dedicated Grafana Discord/Teams target and routing examples.
- Grafana parser, formatter, output-selection, payload-budget, and source
  precedence regression tests.
- Grafana integration and synthetic fixture replay documentation.
- Source-detection regression protection for multipart bodies, competing
  vendor messages, attachment-only markers, and existing integrations.
- Aggregate Discord embed-budget enforcement while preserving essential event
  fields.
- Updated source-aware architecture documentation covering dispatch, parsing,
  the shared model, routing, formatter selection, and webhook delivery.

- Automated GitHub Release creation for stable `vMAJOR.MINOR.PATCH` tags.
- Release validation that the tag, checked-out commit, and `src/version.py`
  contain the same stable version.
- Rerun-safe updates of existing GitHub Releases and manual publication of
  existing stable tags.

### Notes

- QNAP support is provisional. Synthetic fixtures do not guarantee
  compatibility with every QTS or QuTS hero version; anonymized real email
  samples are still needed for verification.
- Grafana support is provisional. Synthetic fixtures do not guarantee
  compatibility with every Grafana version or custom alert template;
  anonymized real email samples are still needed for verification.

### Remaining before release

- Change the development version to the stable v1.3.0 version only after final
  validation.
- Complete final validation, tag and image publication, and
  [GitHub Release](https://github.com/FortPT/notifinho/releases) publication.

---

## 1.2.0 - 2026-07-10

### Added

- Zabbix email detection and parser.
- Zabbix problem notifications.
- Zabbix recovery notifications.
- Zabbix-specific Discord embed formatter.
- Zabbix-specific Microsoft Teams Adaptive Card formatter.
- Severity-aware Zabbix notification icons and colors.
- Optional Zabbix problem ID display.
- Conditional host-based output routing.
- Support for sending selected Zabbix hosts to secondary webhook targets.
- Configuration examples for Zabbix routing.
- Configuration examples for filtered secondary destinations.

### Improved

- Microsoft Teams Zabbix card layout.
- Zabbix problem and recovery date formatting.
- Source-specific formatter selection for Discord and Microsoft Teams.
- Case-insensitive email sender detection.
- Router logging for matched and skipped conditional destinations.
- Configuration documentation for multiple output targets.

---

## 1.1.1

### Fixed

- Fixed Discord footer version to use the application version dynamically instead of a hardcoded value.

---

## 1.1.0

### Added

- Microsoft Teams output support.
- Microsoft Teams Adaptive Card formatter.
- Multiple-output routing support.
- Ability to send the same notification to Discord and Microsoft Teams.
- Formatter abstraction for future notification platforms.

### Improved

- Teams backup notification layout.
- Teams date formatting using Portuguese-friendly `DD/MM/YY HH:mm` format.
- Development environment and startup banner.
- Configuration example for multi-output routing.

---

## 1.0.1

Initial public release.

---

## 1.0.0

### Added

- SMTP Gateway.
- Xen Orchestra parser.
- Discord formatter.
- Docker support.
- Routing.
- VM details.
- Repository information.
- Transfer speed.
- Rich embeds.
