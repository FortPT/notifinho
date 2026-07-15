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

The current stable release is **v1.8.0**.

Instead of receiving plain text emails, your infrastructure platforms can deliver beautiful notifications to collaboration tools such as Discord and Microsoft Teams.

Current features include:

- Xen Orchestra parser
- Zabbix, QNAP, Grafana Alerting, and TrueNAS notification support
- UniFi Network, Protect, and Drive native HTTP webhooks
- UniFi Drive delivered-email parsing remains supported
- Portainer Business Edition Alerting webhooks
- Fixture-validated Proxmox VE SMTP and native webhook ingestion
- Fixture-validated Synology DSM SMTP plus JSON/form custom webhooks
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

```yaml
services:
  notifinho:

    image: fortpt/notifinho:latest

    container_name: notifinho

    restart: unless-stopped

    ports:
      - "8025:8025"
      - "18080:8080"

    # Uncomment after configuring SMTP authentication.
    # environment:
    #   NOTIFINHO_SMTP_PASSWORD: "${NOTIFINHO_SMTP_PASSWORD}"

    volumes:
      - ./config:/notifinho/config
      # Mount certificates read-only when STARTTLS is enabled.
      # - ./config/tls:/notifinho/config/tls:ro
      - ./logs:/notifinho/logs
```

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

v1.8.0 also provides `/portainer/alerts`, `/proxmox/events`, and
`/synology/events`. Portainer Alerting has real firing/resolved validation.
Proxmox VE and Synology DSM are fixture-validated and remain pending real-system
compatibility validation.

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

- Microsoft Teams
- Zabbix
- TrueNAS
- Redfish hardware-management sources
- Home Assistant
- Secure event and configuration APIs
- Additional UniFi event variants
- Slack
- Telegram

---

⚡ Powered by FortPT

Copyright © 2026 FortPT
