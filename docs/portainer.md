# Portainer Alerting integration

Notifinho v1.8 accepts Portainer Business Edition Alerting webhooks at:

```text
POST /portainer/alerts
```

The integration consumes notifications emitted by Portainer. It does not poll
the Portainer API, use stack-redeployment webhooks, or retain administrator
credentials.

## Compatibility

| Portainer | Edition | Transport | Validation |
|---|---|---|---|
| 2.42.0 | Business Edition | Alerting webhook | Firing event validated on VM-04 |
| 2.42.0 | Business Edition | Alerting email | Discovery pending |

The validated webhook is an Alertmanager-compatible envelope containing one or
more alerts. Notifinho creates one normalized notification per alert and maps
Portainer `firing` events by severity. A `resolved` event maps to a successful
recovery notification.

## Notifinho configuration

Generate a URL-safe secret:

```bash
openssl rand -hex 32
```

Add it to the Notifinho configuration. The same HTTP secret continues to
protect UniFi webhooks through the `X-Notifinho-Token` header.

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
    portainer:
      webhook: "PASTE_PORTAINER_DISCORD_WEBHOOK"

  teams:
    enabled: false
    portainer:
      webhook: "PASTE_PORTAINER_TEAMS_WORKFLOW_WEBHOOK"

routing:
  portainer:
    outputs:
      - output: discord
        target: portainer

      # - output: teams
      #   target: portainer
```

Do not commit the real secret or webhook URLs.

## Portainer channel

For the production Compose example, host port `18080` maps to Notifinho's
container port `8080`. On VM-04, configure the Portainer Alerting webhook URL
as:

```text
http://192.168.0.164:18080/portainer/alerts?token=PASTE_64_CHARACTER_HEX_SECRET
```

In Portainer:

1. Open **Additional Functionality > Alerting > Settings**.
2. Edit the enabled `internal` alert manager.
3. Add a **Webhook** notification channel.
4. Give the channel a descriptive name and enter the private direct URL.
5. Save the settings.

Portainer's alert-manager **Test** action verifies that the internal instance
is reachable; it does not emit a notification through the channel. Validate
delivery with a narrow, reversible alert rule.

## Network and authentication boundary

Prefer direct traffic between Portainer and VM-04's private host address.
Nginx Proxy Manager is not required for this same-host integration. Restrict
host port `18080` to the trusted management network and do not expose it to the
internet.

The query token exists because Portainer's webhook channel accepts only a URL
and cannot set `X-Notifinho-Token`. Notifinho accepts `?token=` only on the
Portainer endpoint, requires exactly one value, and compares it using a
timing-safe operation. Header authentication remains accepted on every native
endpoint.

Avoid sending the query-token URL through a reverse proxy whose access logs
record query strings. Notifinho suppresses HTTP access logging, raw request
bodies, query strings, and payload identifiers.

## Event mapping

Notifinho uses these validated fields:

| Portainer field | Notifinho use |
|---|---|
| `status` | Firing or resolved state |
| `alerts[].labels.severity` | Information, warning, or failure mapping |
| `summary` / `alertname` | Card title |
| `annotations.description` | Alert message |
| `instance` | Instance field and optional host routing metadata |
| `alert_source` | Category and source field |
| `authentication_method` | Security-alert context |
| `username` | Security-alert context |
| `startsAt` / `endsAt` | Started and resolved times |

Internal rule IDs, fingerprints, group keys, generator URLs, and Portainer's
external URL are deliberately not displayed in Discord or Teams cards.

## Safe validation and rollback

Use a narrow rule with synthetic activity. The initial BE 2.42.0 validation
used **High Authentication Failures (Single User)** with a nonexistent test
username. Immediately restore the original threshold, duration, severity, and
disabled state after capture.

Watch Notifinho without printing configuration values:

```bash
docker logs -f notifinho
```

A successful request returns HTTP `204`. Invalid authentication returns `401`,
an unsupported path returns `404`, invalid JSON returns `400`, and an oversized
request returns `413`.

To roll back, disable or remove the Portainer notification channel and remove
the `routing.portainer` block. Existing SMTP and UniFi webhook inputs remain
unchanged.
