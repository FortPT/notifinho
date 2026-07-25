# v2 user tokens, destinations, routes, and delivery history

The platform state provides an ownership-enforcing backend service layer
exposed through the [authenticated platform API](platform-api.md). Since
v2.5.0, SQLite is authoritative for API tokens, destinations, routes, settings,
delivery history, retries, previews, and test delivery. `config.yaml` contains
only process bootstrap, listener, and security configuration.

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
include filters are ANDed across categories and ORed within each category.
Exclude filters always win:

```json
{
  "hosts": ["pve-01"],
  "events": ["backup*"],
  "severities": ["critical", "warning"],
  "statuses": ["active"],
  "exclude_hosts": ["test-*"],
  "exclude_events": ["heartbeat*"]
}
```

- `hosts` checks normalized `host`, `hostname`, `device`, and `node` metadata;
- `events` checks event metadata, notification category, and title;
- `severities` checks severity metadata and normalized notification status;
- `statuses` checks notification status and state/status metadata;
- `exclude_hosts`, `exclude_events`, `exclude_severities`, and
  `exclude_statuses` reject matching values after include filters pass.

Filter values are case-insensitive and may use shell-style patterns such as
`backup*`. Unknown filter categories, empty lists, oversized values, and
oversized filter documents are rejected. Disabled routes and disabled
destinations never match.

Since v2.5.1, wildcard (`*`) routes are fallback-only. Notifinho first evaluates
specific integration routes. It evaluates wildcard routes only when no specific
route matches. When multiple matching routes resolve to the same destination,
only the highest-priority route delivers the event.

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

## Database resource authority

The first v2.5.0 start validates the legacy `unified_yaml_v1` document, imports
its tokens, destinations, routes, and WebUI-managed settings into schema 8, and
then atomically normalizes the mounted file to
`platform.configuration_model: platform_database_v1`.

After migration, destination and route API requests never synchronize the whole
YAML document. Each store uses its own database transaction and returns valid
rows independently from malformed rows. Integration behavior, regional
preferences, and backup scheduling use isolated `settings_records`; a damaged
record reports a scoped warning and falls back to its validated default without
preventing other pages from loading.

Existing credential values are not copied into YAML or API responses. YAML
application token values are imported as hashes, destination credentials remain
in the owner-only secret store, and the original token/secret files remain
mounted for rollback and auditability.

Listener binding changes such as ports, TLS certificates, HTTP publication, and
SMTP authentication remain process-level `config.yaml` settings and require a
container restart. Destination, route, token, alias, presentation, deduplication,
and backup schedule changes take effect through their database stores.
