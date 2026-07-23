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

The current stable release is **v2.3.0**.

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
- Session- or token-protected health, masked configuration, validation, log,
  preview, and test-send API foundations
- Environment-, owner-only file-, or SHA-256-backed API tokens, rate limits,
  private audit logs, and atomic configuration backups
- Rich Discord notifications
- Microsoft Teams Adaptive Cards
- SMTP gateway input
- Optional STARTTLS and SMTP AUTH security
- Native HTTP webhook input enabled for the same-origin WebUI
- Docker deployment
- Parser-driven architecture
- Repository and transfer statistics
- VM-level backup reporting
- Extensible formatter/output system
- Local accounts, scoped application tokens, owned destinations and routes
- Authenticated same-origin WebUI and `/api/v2` management/event API
- Discord, Teams, Slack, generic webhook, MQTT, and ntfy platform destinations
- Credential-free import/export, live mounted-YAML synchronization, and private state recovery

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
mkdir -p logs/emails secrets state external-backups
chmod 600 .env config/config.yaml
chmod 700 logs logs/emails secrets state external-backups
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

The HTTP listener, platform, API, and WebUI are enabled by default. Publishing
port `8080` remains an explicit deployment choice. On first start, copy the
short-lived setup token from container output and use it in the HTTPS WebUI to
choose the first administrator credentials. No default password exists.

Existing YAML installations are visible immediately after login. In v2.2.0,
the mounted `config.yaml` is the single configuration authority: valid external
edits appear in the WebUI, and administrator WebUI edits are validated, backed
up, and written atomically to the same file. SQLite remains a private mirror
for history, preview/test delivery, and retries; it is not a competing fallback
configuration.

The v2.3.0 WebUI adds immediate notice and audit updates, source categories and
real input transports, animated route flow, channel-aware destination tests,
semantic Delivery History, avatar cropping, and separate Inputs and Backups
views. Backups support named Local, NFS, and SMB targets, connection/write
tests, manual runs, and schedules. Host-mounted shares remain recommended; the
repository documents an explicit privileged override for deployments that
require application-managed remote mounts.

```yaml
http:
  enabled: true
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

## v2.0 platform

- Migration-aware SQLite state, local account/login protection, hashed
  sessions/CSRF, ownership records, and owner-only secret rotation
- Source-scoped tokens, private/shared destinations, user route filters,
  bounded delivery retries, audit events, and safe delivery history
- Ownership-safe preview/test contracts and adapters for Discord,
  Teams, Slack, generic webhooks, MQTT, and ntfy
- Authenticated `/api/v2` sessions, CSRF, owned-resource management,
  preview/test endpoints, and source-scoped platform event submission
- Responsive, same-origin v2.0 WebUI for accounts, destinations, routes,
  application tokens, preview/test delivery, history, and audit
- Digest-only, expiring, single-use first-run administrator setup without a
  shared password or account-management shell command
- Local administrator and user accounts
- User- and application-scoped event endpoints and API tokens
- Private/shared destinations and user-owned routing
- Searchable delivery history, safe errors, and audit events
- Preview, test delivery, credential-free configuration import/export,
  integrity-checked private backup/restore, and v1.x YAML migration previews
- Slack output
- Generic outbound webhook output
- MQTT output
- ntfy output
- Previewed v1.x Discord/Teams YAML import
- Production Docker Compose, Portainer, and reverse-proxy examples
- Broader real-system Redfish compatibility validation
- Additional UniFi event variants

Telegram and other destination adapters remain candidates for later v2.x
releases.

---

⚡ Powered by FortPT

Copyright © 2026 FortPT
