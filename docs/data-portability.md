# Platform data portability and migration

Phase 6 adds administrator-only, preview-first tools for moving platform
destinations and routes and for protecting the private platform state. These
tools operate on the opt-in SQLite platform. They do not rewrite or disable the
existing YAML notification pipeline.

## Safe platform export

The WebUI **Data tools** page can download a versioned
`notifinho.platform.v1` JSON document. It contains:

- destination owner names, display names, output types, public settings,
  sharing, and enabled state; and
- route owner names, sources, filters, priorities, enabled state, and portable
  destination references.

The export never contains password hashes, session material, API-token hashes
or values, secret identifiers, secret-file paths, stored digests, webhook URLs,
passwords, or other destination credentials. A destination records only that a
credential is required.

Import requires the owner account to exist on the target instance. It is
merge-only: an existing destination or route name is rejected rather than
overwritten. A credential-dependent destination imported from safe JSON is
disabled, and its imported routes are disabled, until an administrator enters
the credential through the normal write-only destination form.

## Preview and fingerprint boundary

JSON and YAML documents are limited to 1 MiB. The backend performs all
normalization, ownership, output-setting, route-filter, and name-collision
checks. The preview returns a SHA-256 fingerprint plus credential-free actions,
warnings, and errors.

Apply succeeds only when:

1. the preview has no errors;
2. the administrator explicitly confirms the operation; and
3. the submitted document produces the exact preview fingerprint.

New resources are rolled back if any unexpected create fails. Imports never
update or delete existing resources.

## v1.x YAML migration

The YAML migration accepts the existing `outputs.discord`, `outputs.teams`,
and `routing` structures. It creates shared administrator-owned destinations,
owner routes, and owner-only secret files. Supported v1 host match filters are
translated to platform route filters.

Placeholders and routes whose target was not imported are skipped with a safe
warning. Webhook values are accepted only as credential-free HTTPS URLs and
never appear in the preview, audit event, or API response. Unsupported output
types and match fields are rejected rather than guessed.

Migration is additive. The YAML file remains authoritative for existing SMTP
and source-specific webhook delivery until an operator deliberately changes
that configuration. Running both route models can produce duplicate external
notifications, so validate platform ingestion separately before changing the
legacy routes.

## Private state backups

State backups are directories below `platform.state_dir/backups`. Each backup
contains a consistent SQLite snapshot, owner-scoped secret files, and a
SHA-256 integrity manifest. Directories are mode `0700`; database, manifest,
and secret files are mode `0600`. Backup bytes are never downloadable through
the platform API or WebUI.

`platform.backup_retention` keeps 20 snapshots by default and accepts values
from 1 through 100. Create a backup before migration, account changes, or a
platform upgrade. Continue to include the entire state bind mount in the
host's encrypted backup policy; the WebUI snapshots are not a substitute for
off-host disaster recovery.

Restore requires the exact backup identifier. Before restoring, Notifinho
creates a safety backup of the current state, verifies every stored digest,
runs SQLite integrity and schema checks, and stages the replacement. A failed
swap rolls back to the live database and secret directory.

Every browser session is revoked after a successful restore. Application-token
records return to the selected snapshot, which can revive a token that was
valid at backup time or remove one created later. Review and rotate application
tokens after restore when that history is security-sensitive.

## API routes

All routes require an administrator session. Every POST additionally requires
the session CSRF token.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/v2/portability/export` | return a credential-free JSON document |
| POST | `/api/v2/portability/preview` | validate and fingerprint platform JSON |
| POST | `/api/v2/portability/import` | apply the unchanged confirmed JSON import |
| POST | `/api/v2/migrations/v1/preview` | validate and fingerprint v1.x YAML |
| POST | `/api/v2/migrations/v1/import` | apply the unchanged confirmed YAML migration |
| GET | `/api/v2/backups` | list verified server-side snapshots |
| POST | `/api/v2/backups` | create a server-side snapshot |
| POST | `/api/v2/backups/{id}/restore` | restore after exact-ID confirmation |

All responses use the platform no-store and browser-security headers. Audit
details contain only bounded counts, identifiers, outcomes, and explicit
secret-redaction facts.
