# v2 user tokens, destinations, routes, and delivery history

The platform state provides an ownership-enforcing backend service layer
exposed through the [authenticated platform API](platform-api.md). v2.0.2 adds
an explicit routing-authority boundary: YAML behavior is preserved until an
administrator previews and confirms mounted-configuration takeover, after
which the WebUI-managed database routes handle legacy inputs as well.

## API tokens

Platform API tokens belong to one local user. A token value is generated with
cryptographic randomness, returned once, and stored only as a SHA-256 digest.
Metadata contains the token name, role, source scopes, rate limit, version,
expiry, last-use time, and revocation time; it never contains the token value
or digest.

Application tokens require one or more explicit source scopes. Wildcard scopes
and administrator tokens require an administrator. Authentication also rejects
disabled owners, expired tokens, revoked tokens, and events outside the token's
source scopes. The returned principal is compatible with the existing
per-token/per-client rate limiter.

Rotation generates a new value, invalidates the previous value, increments the
non-secret version, and clears last-use metadata. Revocation is final; a
revoked token cannot be rotated back into service.

## Destinations and secrets

A destination has one owner, a display name, output type, non-secret JSON
settings, enabled state, and optional owner-scoped secret reference. Supported
schema types are Discord, Microsoft Teams, Slack, generic webhook, MQTT, and
ntfy. The disabled adapters and preview/test contracts are documented in the
[platform output guide](platform-outputs.md).

Credential-like keys are rejected anywhere in destination settings. Webhook
URLs, passwords, tokens, and similar values must use the owner-only secret
store. Public destination metadata reports only whether a secret is configured.

Private destinations are visible only to their owner and administrators. Only
an administrator can share a destination. Another user can reference a shared
destination from a route, but cannot reveal or rotate its secret. A shared
destination cannot be made private while another user's route references it.

## User routes

Routes belong to one user and point to either that user's destination or an
explicitly shared destination. Matching is deterministic and ordered first by
numeric priority and then by normalized route name.

Each route selects one source. Administrators may use the `*` source. Optional
filters are ANDed across categories and ORed within each category:

```json
{
  "hosts": ["pve-01"],
  "events": ["backup*"],
  "severities": ["critical", "warning"],
  "statuses": ["active"]
}
```

- `hosts` checks normalized `host`, `hostname`, `device`, and `node` metadata;
- `events` checks event metadata, notification category, and title;
- `severities` checks severity metadata and normalized notification status;
- `statuses` checks notification status and state/status metadata.

Filter values are case-insensitive and may use shell-style patterns such as
`backup*`. Unknown filter categories, empty lists, oversized values, and
oversized filter documents are rejected. Disabled routes and disabled
destinations never match.

## Delivery orchestration

The platform delivery service accepts injected output adapters. This keeps
transport code separate from ownership, routing, retries, and history, and
lets every platform output reuse the same policy.

For every matched route, the service:

1. rechecks destination visibility and enabled state;
2. resolves the destination secret internally as its real owner;
3. invokes only the adapter registered for the destination output type;
4. retries only results explicitly marked retryable, with at most five
   attempts; and
5. records one safe history row per attempt.

Adapter exceptions become the generic `delivery_exception` code. Exception
text is not persisted. Missing adapters, destinations, or secret values become
safe terminal error codes.

Delivery history contains owner, route/destination identifiers, bounded source,
title and severity, outcome, attempt number, retryability, HTTP-like status,
safe error code, and sanitized error text. It never stores destination secret
values, token values, adapter exception messages, or response bodies. Users see
only their own history; administrators may inspect all history.

Retries in this phase are bounded within the service call. A persistent
background retry queue is deliberately deferred until the worker/runtime phase
so no unfinished scheduler is enabled in production.

## Audit events

Token, destination, and route mutations can write database-backed audit events.
Sensitive detail keys are replaced with `<redacted>`, and credential patterns
inside other text are sanitized. Users see their own audit activity;
administrators may inspect all activity.

## Routing authority

`platform.routing_authority` accepts exactly `yaml` or `database` and defaults
to `yaml` when omitted.

- `yaml`: SMTP and native HTTP/Redfish/Home Assistant webhook notifications use
  the original YAML router. The WebUI displays those resources as YAML-managed.
- `database`: those same parsed notifications are delivered to every enabled
  platform route owner through the platform adapters and recorded in delivery
  history. The YAML outputs and routes are labelled rollback fallback.

Authenticated `/api/v2/events` submissions always remain owner-scoped to the
submitting session or application token. Routing-authority selection changes
only the legacy SMTP and source-specific webhook pipeline.

The mounted-configuration takeover imports supported destinations and routes
before atomically changing authority. A legacy event therefore sees exactly one
routing backend: there is no interval where both YAML and database delivery run
for the same event. Disabled users, destinations, and routes never receive
legacy events. Matching stays deterministic within each owner, and delivery
history preserves the owner boundary.

Returning to YAML requires an administrator confirmation and creates a fresh
configuration backup. Database resources remain intact, so WebUI routing can be
reactivated without repeating migration or re-importing credentials.
