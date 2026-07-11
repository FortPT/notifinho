# Changelog

## Unreleased (v1.3.0)

### Planned

- QNAP QTS and QuTS hero notification support.
- QNAP Discord and Microsoft Teams formatting.
- QNAP parser fixtures and regression tests.
- Automated GitHub Release creation.

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
