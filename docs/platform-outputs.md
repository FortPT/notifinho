# v2 platform output adapters and previews

Phase 3 implements the disabled output-adapter layer for Discord, Microsoft
Teams, Slack, generic outbound webhooks, MQTT, and ntfy. It uses the ownership,
secret, route, retry, history, and audit services from Phases 1 and 2.

Phase 4 exposes these adapters through authenticated, ownership-safe preview,
test, and platform event endpoints. v2.1.0 mirrors the authoritative YAML
destinations into the same delivery services for all legacy inputs. See the
[platform API guide](platform-api.md).

## Common contract

Every adapter accepts public destination metadata, an internally resolved
secret value, and the shared `Notification` model. It provides:

- a credential-free preview built by backend formatters;
- one bounded transport attempt returning a structured `DeliveryResult`;
- no response-body, exception-text, or credential persistence; and
- compatibility with the Phase 2 route delivery and retry service.

HTTP 408, 409, 425, 429, and 5xx responses are retryable. Other 4xx responses
are terminal. MQTT connection and timeout failures are retryable. The Phase 2
service still enforces the maximum of five total attempts and records only safe
per-attempt history.

## Destination settings and secrets

Destination settings are public metadata. Unknown settings, oversized values,
credential-like keys, invalid headers, MQTT wildcard publish topics, and
non-HTTPS outbound URLs are rejected. Credential values belong only in the
owner-scoped secret store.

| Output | Public settings | Owner-scoped secret |
| --- | --- | --- |
| Discord | `components_v2` | webhook URL or `{"url":"..."}` |
| Teams | none | workflow webhook URL or `{"url":"..."}` |
| Slack | `include_metadata` | Slack webhook URL or `{"url":"..."}` |
| Webhook | method, timeout, safe headers, JSON template, HMAC flag | URL; optional HMAC key and credential headers |
| MQTT | host, port, topic template, QoS, retain, TLS, keepalive, client ID | optional username/password JSON |
| ntfy | server, topic, priority, tags, title template, action flag, timeout | optional access token or username/password JSON |

Plain secret values are accepted for the common one-value case. Outputs that
need multiple values use a JSON object. For example, a signed webhook secret
record can contain:

```json
{
  "url": "https://events.example.com/notifinho",
  "hmac_secret": "REPLACE_IN_SECRET_STORE",
  "headers": {
    "Authorization": "Bearer REPLACE_IN_SECRET_STORE"
  }
}
```

The JSON object is stored in the owner-only secret file, never in destination
settings or API-facing metadata.

## Slack

Slack previews use bounded Block Kit with a plain-text fallback, normalized
source/severity/host context, credential sanitization, and an optional safe
HTTPS action. Delivery accepts official `hooks.slack.com` and
`hooks.slack-gov.com` incoming-webhook hosts.

## Generic outbound webhook

The default body is the versioned `notifinho.event.v1` JSON envelope. Metadata
is bounded recursively and credential-like keys are redacted. An optional JSON
object template supports a fixed set of escaped substitutions:

```json
{
  "summary": "${source}: ${title}",
  "host": "${host}",
  "severity": "${severity}",
  "event_id": "${event_id}"
}
```

Supported substitutions are `body`, `category`, `event_id`, `host`,
`severity`, `source`, `status`, and `title`. Methods are limited to POST, PUT,
and PATCH. Unsafe hop-by-hop and credential headers cannot be stored in public
settings. Credential headers can be supplied only in the owner-scoped secret.

Every request receives `X-Notifinho-Idempotency-Key`. When HMAC is enabled,
the canonical UTF-8 JSON body is signed with HMAC-SHA256 and sent in
`X-Notifinho-Signature` as `sha256=<hex digest>`.

## MQTT

MQTT publishes the same stable `notifinho.event.v1` envelope using Eclipse
Paho's one-shot publisher. Topic templates use the fixed substitutions above.
QoS is limited to 0, 1, or 2; publish topics cannot contain `+` or `#`; TLS is
enabled by default; and authentication remains inside the secret store.

## ntfy

ntfy sends the normalized title, bounded message, configured priority/tags,
and an optional HTTPS `view` action. Hosted and self-hosted HTTPS servers are
supported. Access tokens or basic-auth credentials remain in the secret store
and never appear in previews.

## Outbound network policy

Outbound URLs and MQTT hosts resolve only to globally routable addresses by
default. This blocks accidental loopback, link-local, and private-network
delivery. Only an administrator can enable `allow_private_network` on webhook,
MQTT, or ntfy destinations for an intentional self-hosted deployment.

Discord, Teams, and Slack platform destinations never offer that override.

## Preview and test delivery

`PlatformOutputService` applies destination visibility before preview and
enabled-state checks before test delivery. Private destinations remain
owner/admin only. Shared destinations may be previewed or tested by an
authorized user, while their secret is resolved internally as the real owner
and never returned.

Preview and test actions can write database-backed audit events. Test results
contain only success, retryability, HTTP-like status, and a safe error code.
Real response bodies and adapter exceptions are discarded.
