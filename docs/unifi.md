# UniFi integration

Notifinho `1.7.0` provides three independent normalized UniFi sources:

- `unifi_network` receives UniFi Network Alarm Manager JSON webhooks;
- `unifi_protect` receives UniFi Protect Alarm Manager JSON webhooks; and
- `unifi_drive` receives UniFi Drive Alarm Manager JSON webhooks or parses
  delivered UniFi Drive notification email through SMTP.

All three sources use the shared `Notification` model, router, Discord output,
and Microsoft Teams output.

## Native HTTP input

The HTTP input runs alongside SMTP and remains disabled unless explicitly enabled:

```yaml
http:
  enabled: true
  host: "0.0.0.0"
  port: 8080
  max_body_bytes: 1048576
  shared_secret: "REPLACE_WITH_A_RANDOM_SECRET"
```

Supported endpoints:

```text
POST /unifi/network
POST /unifi/protect
POST /unifi/drive
```

Successful parse and dispatch returns HTTP 204. Invalid JSON or an invalid
source envelope returns 400, unknown paths return 404, unsupported methods
return 405, and oversized bodies return 413.

When `shared_secret` is non-empty, every request must include:

```text
X-Notifinho-Token: <secret>
```

Use HTTPS termination, a strong token, and source restrictions. Do not expose
the native listener directly to the public internet.

## Container ports

```yaml
ports:
  - "8025:8025"
  - "18080:8080"
```

Publishing port `8080` does not enable HTTP; `http.enabled` must also be true.

## UniFi Network

Configure Alarm Manager to POST JSON to `/unifi/network`. Network notifications
normalize controller, event, category, severity, client, network or Wi-Fi,
connected-device, duration, RSSI, and event-time context. MAC addresses remain
excluded from visible cards by default.

## UniFi Protect

Configure Alarm Manager to POST JSON to `/unifi/protect`. Protect notifications
use the actual trigger event and trigger device while preserving the configured
rule as `Alarm rule`.

## UniFi Drive webhooks

Configure Alarm Manager to POST JSON to `/unifi/drive`.

The discovered default Drive payload is intentionally small:

```json
{
  "alarm_id": "00000000-0000-4000-8000-000000000001",
  "text": "Alarm \"Notifinho | Drive - Backup Task Partially Completed\" was triggered"
}
```

The alarm ID is internal metadata and is not displayed in Discord or Teams.

Unlike Protect, Drive does not identify the exact condition inside a
multi-trigger alarm. Create one Drive alarm per event and use descriptive names:

```text
Notifinho | Drive - Backup Task Partially Completed
Notifinho | Drive - Backup Task Failed
Notifinho | Drive - Backup Task Completed
Notifinho | Drive - Storage Pool Suspended
```

For names using `Drive - <event>` or `Drive | <event>`, Notifinho uses the final
event segment as the card title and preserves the full name in `Alarm rule`.

## UniFi Drive delivered email

Drive email support remains available. Notifinho does not poll IMAP, Microsoft
Graph, Gmail, or any mailbox and stores no mailbox credentials. Email-based
Drive notifications require an external forwarding rule or SMTP relay.

## Routing and targets

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

Equivalent Teams targets use `outputs.teams.<target>.webhook`. Dedicated output
configuration always uses `webhook`, never `webhook_url`.

## Reverse proxy

All three paths can use the same production backend:

```text
/unifi/network -> notifinho:8080
/unifi/protect -> notifinho:8080
/unifi/drive   -> notifinho:8080
```

Keep the shared token enabled even on a private Docker network.
