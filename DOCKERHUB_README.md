<p align="center">
  <img src="https://raw.githubusercontent.com/FortPT/notifinho/main/docs/images/logo.png" width="220" alt="Notifinho Logo">
</p>

<h1 align="center">Notifinho</h1>

<p align="center">
<strong>Infrastructure Notification Engine</strong>
</p>

<p align="center">
Transform infrastructure events into rich, actionable notifications.
</p>

<p align="center">
Built for Homelabs • Ready for Enterprise
</p>

---

## Overview

Notifinho is an Infrastructure Notification Engine that transforms traditional infrastructure notifications into rich, actionable collaboration messages.

The current stable release is **v1.9.7**.

Instead of receiving plain text emails, your infrastructure platforms can deliver beautiful notifications to collaboration tools such as Discord and Microsoft Teams.

Current features include:

- Xen Orchestra parser
- Zabbix, QNAP, Grafana Alerting, and TrueNAS notification support
- UniFi Network, Protect, and Drive native HTTP webhooks
- UniFi Drive delivered-email parsing remains supported
- Portainer Business Edition Alerting webhooks
- Fixture-validated Proxmox VE SMTP and native webhook ingestion
- Fixture-validated Synology DSM SMTP plus JSON/form custom webhooks
- Shared Redfish Event Service ingestion with duplicate suppression
- Fixture-validated Supermicro BMC/IPMI, HPE iLO, and Dell iDRAC adapters
- Authenticated Home Assistant and generic source-scoped event submission
- Disabled-by-default health, masked configuration, validation, log, preview,
  and test-send API foundations
- Environment-, owner-only file-, or SHA-256-backed API tokens, rate limits,
  private audit logs, and atomic configuration backups
- Rich Discord notifications
- Microsoft Teams Adaptive Cards
- SMTP gateway input
- Optional STARTTLS and SMTP AUTH security
- Disabled-by-default native HTTP webhook input
- Docker deployment
- Parser-driven architecture
- Repository and transfer statistics
- VM-level backup reporting
- Extensible formatter/output system

---

## Quick Start

```bash
docker pull fortpt/notifinho:latest
```

The repository provides `compose.production.yaml`, `.env.example`, and a
development-only `docker-compose.yml`. Production uses a versioned image,
non-root deployment identity, read-only root filesystem, dropped capabilities,
and persistent configuration/log mounts.

```bash
cp .env.example .env
cp config/config.example.yaml config/config.yaml
mkdir -p logs/emails secrets
chmod 600 .env config/config.yaml
chmod 700 logs logs/emails secrets
docker compose -f compose.production.yaml config
docker compose -f compose.production.yaml up -d
```

Set `NOTIFINHO_UID` and `NOTIFINHO_GID` in `.env` from `id -u` and `id -g`.
Portainer deployments should replace relative mount paths with absolute host
paths. Full deployment and rollback guidance is in `docs/deployment.md`.

The container exposes two independent ports:

- `8025/tcp` for the existing SMTP listener;
- `8080/tcp` for the native HTTP webhook listener.

SMTP STARTTLS and authentication remain disabled by default. Deployment and
rollout guidance is available in the repository's `docs/smtp-security.md`.

Publishing port `8080` does not enable HTTP input. It remains disabled by
default and must be explicitly enabled in `config/config.yaml`:

```yaml
http:
  enabled: false
  host: "0.0.0.0"
  port: 8080
  max_body_bytes: 1048576
  shared_secret: ""
```

UniFi Network, Protect, and Drive send JSON to `/unifi/network`,
`/unifi/protect`, and `/unifi/drive`. All three endpoints can use the same
`X-Notifinho-Token`. Drive delivered-email parsing remains supported; Notifinho
does not poll IMAP, Microsoft Graph, Gmail, or other mailbox providers.

v1.8.x also provides `/portainer/alerts`, `/proxmox/events`, and
`/synology/events`. Portainer Alerting has real firing/resolved validation.
Synology DSM has real JSON webhook and SMTP/STARTTLS validation. Proxmox VE
remains fixture-validated pending real-system compatibility testing.

v1.9.0 adds `/redfish/events`, `/redfish/supermicro`, `/redfish/hpe`,
`/redfish/dell`, `/home-assistant/events`, and the disabled-by-default `/api/*`
backend. Hardware adapters remain fixture-validated pending representative
real systems. See the repository integration and API guides before enabling
these endpoints.

v1.9.1 adds dedicated generic API event presentation and concise,
service-aware Home Assistant cards. It preserves all v1.9.0 configuration,
token, routing, and endpoint contracts.

v1.9.2 adds optional Home Assistant endpoint/component aliases, bare IPv4
endpoint extraction, structured integration error codes, and concise Tapo/Kasa
and IPP cards. Existing configurations and Home Assistant payloads remain
compatible; aliases are optional.

v1.9.3 presents the Redfish subscription Context as Host, scopes duplicate
suppression by host and origin, and omits empty recommended actions. Existing
Redfish endpoints, tokens, routes, and payloads remain compatible.

v1.9.4 standardizes every Microsoft Teams formatter on one shared card
hierarchy and preserves the wall-clock timestamp emitted by each source in
both Teams and Discord. Existing configuration, routes, endpoints, targets,
and secrets remain compatible.

v1.9.6 replaces generated initial badges with documented official vendor
assets across all Teams and Discord integrations. It gives Discord the same
device/event hierarchy, source-time metrics, and status semantics as Teams
while retaining richer source details and enforcing Discord embed limits. It
also omits missing Xen Orchestra Duration/Result facts, preserves identifier
casing, removes duplicated UniFi details, and rejects malformed Teams webhook
placeholders before delivery. Existing valid webhooks and routing remain
compatible.

A shared Discord target can receive all three normalized UniFi sources:

```yaml
outputs:
  discord:
    enabled: true
    unifi:
      webhook: "PASTE_UNIFI_DISCORD_WEBHOOK_HERE"

routing:
  unifi_network:
    outputs:
      - output: discord
        target: unifi
  unifi_protect:
    outputs:
      - output: discord
        target: unifi
  unifi_drive:
    outputs:
      - output: discord
        target: unifi
```

---

## Documentation

GitHub Repository

https://github.com/FortPT/notifinho

---

## Roadmap

- Migration-aware SQLite state, local account/login protection, hashed
  sessions/CSRF, ownership records, and owner-only secret rotation
- Source-scoped tokens, private/shared destinations, user route filters,
  bounded delivery retries, audit events, and safe delivery history
- Ownership-safe preview/test contracts and disabled adapters for Discord,
  Teams, Slack, generic webhooks, MQTT, and ntfy
- Responsive v2.0 WebUI
- Local administrator and user accounts
- User- and application-scoped event endpoints and API tokens
- Private/shared destinations and user-owned routing
- Searchable delivery history, safe errors, and audit events
- Preview, test delivery, configuration import/export, backup, and restore
- Slack output
- Generic outbound webhook output
- MQTT output
- ntfy output
- Automatic v1.x YAML import
- Production Docker Compose, Portainer, and reverse-proxy examples
- Broader real-system Redfish compatibility validation
- Additional UniFi event variants

Telegram and other destination adapters remain candidates for the v2.x series
after the v2.0 security, routing, and core output model are stable.

---

⚡ Powered by FortPT

Copyright © 2026 FortPT
