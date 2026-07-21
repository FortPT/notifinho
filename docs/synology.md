# Synology DSM integration

Notifinho v1.8 includes Synology DSM ingestion through SMTP and an
authenticated native HTTP endpoint:

```text
POST /synology/events
```

Real DSM delivery has been validated with DSM 7.3.2 custom JSON webhook and
Hyper Backup events, plus DSM 7.1.1 SMTP delivery using STARTTLS. Both paths
were routed successfully to a dedicated Microsoft Teams destination. Broader
warning, failure, and operational event coverage remains compatibility work.

Synology documents custom webhook providers under **Control Panel >
Notification > Webhook**. DSM 7 supports custom providers, GET or POST
selection, configurable parameters, notification rules, and event-template
variables such as `%HOSTNAME%`:

- [DSM 7 Webhooks](https://kb.synology.com/en-global/DSM/help/DSM/AdminCenter/system_notification_webhook?version=7)
- [DSM 7 Events and notification variables](https://kb.synology.com/en-global/DSM/help/DSM/AdminCenter/system_notification_filter?version=7)
- [DSM 7 notification rules](https://kb.synology.com/en-global/DSM/help/DSM/AdminCenter/system_notification_rule?version=7)

The exact variables and resulting request depend on the installed DSM version
and selected event. For that reason, Notifinho uses a small versioned contract
and clearly retains the real-system validation requirement.

## Supported events

- system health, DSM updates, temperature, fan, memory, and CPU events;
- storage pools, volumes, RAID, cache, and capacity;
- disks, drives, bad sectors, and S.M.A.R.T. tests;
- Hyper Backup, Active Backup, restore, and Snapshot Replication;
- UPS, battery, power outage, and power-recovery events;
- packages and services;
- authentication, login, certificate, malware, firewall, and blocked-IP events;
- network and NAS availability events.

## Notifinho configuration

```yaml
http:
  enabled: true
  host: 0.0.0.0
  port: 8080
  max_body_bytes: 1048576
  shared_secret: "PASTE_64_CHARACTER_HEX_SECRET"

outputs:
  discord:
    enabled: true
    synology:
      webhook: "PASTE_SYNOLOGY_DISCORD_WEBHOOK"

  teams:
    enabled: false
    synology:
      webhook: "PASTE_SYNOLOGY_TEAMS_WORKFLOW_WEBHOOK"

routing:
  synology:
    outputs:
      - output: discord
        target: synology

      # - output: teams
      #   target: synology
```

Do not commit the real HTTP secret or destination URLs.

## SMTP input

Configure DSM email notifications to use Notifinho's SMTP listener. Detection
accepts Synology/DiskStation branding in the sender or subject and bounded DSM
notification subjects. It does not require a particular private domain or NAS
hostname.

The parser accepts text, HTML, and multipart email, extracts labelled fields,
and produces concise cards instead of repeating the complete email. Useful
labels include NAS name, model, severity, event time, storage pool, volume,
disk, package, task, user, and source IP. Unknown layouts still produce a
bounded Synology notification.

## Native webhook contract

The JSON representation is:

```json
{
  "schema": "notifinho.synology.v1",
  "source": "synology-dsm",
  "event_type": "backup",
  "title": "Synthetic Hyper Backup failure",
  "message": "Synthetic backup task stopped because the destination was unavailable.",
  "severity": "error",
  "status": "active",
  "timestamp": "2026-07-15T12:45:00Z",
  "metadata": {
    "nas_name": "synthetic-dsm-01",
    "task": "Synthetic Nightly Backup",
    "storage": "synthetic-backup-vault"
  }
}
```

The same fields may be sent as
`application/x-www-form-urlencoded`. Form providers use flat fields such as
`nas_name`, `model`, `storage_pool`, `volume`, `disk`, `package`, `task`,
`username`, and `source_ip` instead of the nested `metadata` object.

Keep `schema` and `source` literal. Map only variables exposed by the installed
DSM notification template into `title`, `message`, `timestamp`, and operational
fields. Prefer an `event_type` of `availability`, `backup`, `disk`, `network`,
`package`, `power`, `replication`, `security`, `storage`, or `system`; otherwise
Notifinho performs bounded keyword classification.

Severity accepts `debug`, `info`, `information`, `notice`, `warning`, `warn`,
`error`, `critical`, or `success`. An explicit `resolved`, `recovered`, or
`restored` status takes precedence over failure wording retained in the title.

## Authentication and network boundary

Every native endpoint accepts:

```text
X-Notifinho-Token: PASTE_64_CHARACTER_HEX_SECRET
```

For DSM custom providers that cannot add the header, the Synology endpoint also
accepts one query token:

```text
http://192.168.0.164:18082/synology/events?token=PASTE_64_CHARACTER_HEX_SECRET
```

Use the private direct address, restrict the host port to the management
network, and avoid a reverse proxy that records query strings. Notifinho
suppresses HTTP access logs. Duplicate query tokens and duplicate form fields
are rejected.

## Development validation

With host port `18082` mapped to container port `8080`, test the committed JSON
fixture without printing the secret:

```bash
TOKEN=$(python3 - <<'PY'
import yaml
from pathlib import Path

data = yaml.safe_load(Path("config/config.yaml").read_text()) or {}
print((data.get("http") or {}).get("shared_secret", ""))
PY
)

curl -sS -o /dev/null -w 'missing_token=%{http_code}\n' \
  -H 'Content-Type: application/json' \
  --data @tests/fixtures/synology/backup_failure.json \
  http://127.0.0.1:18082/synology/events

curl -sS -o /dev/null -w 'authenticated=%{http_code}\n' \
  -H 'Content-Type: application/json' \
  -H "X-Notifinho-Token: ${TOKEN}" \
  --data @tests/fixtures/synology/backup_failure.json \
  http://127.0.0.1:18082/synology/events

unset TOKEN
```

Expected responses are `401` and `204`.

Replay the synthetic email fixture after the SMTP listener is ready:

```bash
python3 scripts/replay_email.py \
  tests/fixtures/synology/storage_degraded.eml \
  --host 127.0.0.1 \
  --port 8026
```

## Additional compatibility validation

When validating additional DSM versions and event families:

1. record the exact DSM version, NAS model, and transport;
2. send DSM's built-in test through email and a custom POST provider;
3. capture only sanitized structure and confirm actual variable names and
   content type;
4. validate success, warning, critical, and recovery where safely available;
5. validate representative storage, disk/SMART, backup, replication, UPS,
   package, security, and availability events;
6. confirm authentication, routing, and visible Discord/Teams details;
7. ensure no production identifiers, tokens, URLs, or raw payloads enter the
   repository.

Issue #43 records the completed baseline validation. New warning/failure
templates or DSM-specific differences should be tracked as compatibility
issues without changing the validated status of the existing SMTP and webhook
contracts.

## Rollback

Disable the DSM email/custom webhook target and remove `routing.synology`. If
the HTTP listener is still used by UniFi, Portainer, or Proxmox, keep it
enabled. Existing sources and routes are unchanged.
