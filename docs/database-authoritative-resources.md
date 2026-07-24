# Database-authoritative resources

Notifinho v2.5.0 separates process bootstrap from WebUI-managed resources.

## Core configuration

`config/config.yaml` contains only listener, transport-security, API-enable,
state-directory, cookie, and WebUI bootstrap settings. It is not parsed during
normal destination or route requests.

## Platform state

The SQLite database stores destinations, routes, application-token hashes,
regional preferences, backup scheduling, integration behavior, aliases, users,
notices, audit events, and delivery history. Destination credential values stay
in private secret files referenced by SQLite.

Each resource uses an independent transaction and API error boundary. A malformed
destination, route, or settings row is reported with its resource identifier;
valid rows remain visible and unrelated pages continue loading.

## One-way migration

The first v2.5.0 start reads a v2.4 `unified_yaml_v1` configuration, validates it,
imports every supported resource, and only then atomically replaces the mounted
file with the normalized `platform_database_v1` document. The migration is
idempotent. If an import or file replacement fails, the legacy YAML remains in
place and the next start can retry.

Existing API-token values are not rotated. Notifinho imports their hashes from
the configured file, environment variable, or SHA-256 value. Token values never
appear in the WebUI or logs.

## Backups and rollback

A production upgrade backup must keep `config`, `state`, and `secrets` together.
Private state backups preserve all database resources and secret files. Portable
exports omit passwords, application-token values, and destination credentials.

Rollback to a pre-v2.5 image requires restoring the matched pre-upgrade YAML,
database, and secrets because older versions cannot open schema 8 or reconstruct
resources from the normalized core file.
