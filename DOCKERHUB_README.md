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

Instead of receiving plain text emails, your infrastructure platforms can deliver beautiful notifications to collaboration tools such as Discord and Microsoft Teams.

Current features include:

- Xen Orchestra parser
- Rich Discord notifications
- SMTP gateway input
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

    volumes:
      - ./config:/notifinho/config
      - ./logs:/notifinho/logs
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
- Proxmox VE
- UniFi Network, Protect, and Drive (`v1.5.0-dev`)
- Slack
- Telegram

---

⚡ Powered by FortPT

Copyright © 2026 FortPT
