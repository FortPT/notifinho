# v2 platform state and local accounts

Notifinho's v2 platform foundation uses SQLite and owner-only secret files. It
does not require PostgreSQL, Redis, or another container. Platform state and
the same-origin WebUI are enabled by default, while explicit
`platform.enabled: false` and `webui.enabled: false` settings remain
authoritative. Existing YAML configuration is the single configuration source;
SQLite mirrors file-backed outputs and routes for delivery operations.

## Storage layout

The hardened production Compose layout is:

```text
/notifinho/state/
|- notifinho.db
|- secrets/
|  `- generated-identifier.v1
|- backups/
|  `- state-YYYYMMDDTHHMMSSZ-identifier/
`- schema-backups/
   `- notifinho-schema-3-before-4-TIMESTAMP.db
```

The state directory and secret directory are mode `0700`. The SQLite database
and each secret value are mode `0600`. Secret filenames are generated; user
input is never used as a path. Secret metadata contains only ownership, type,
version, and configured state. Values and their filesystem paths are not
returned by metadata operations.

SQLite foreign keys and transactional migrations protect relationships among:

- local users and hashed browser sessions;
- user-owned API tokens;
- owner-scoped secret records;
- private or shared destinations;
- user-owned routes; and
- future database-backed audit events.

Schema migrations run in order and are recorded in `schema_migrations`. Schema
version 2 adds API-token rotation metadata and safe delivery-attempt history.
Schema version 3 adds digest-only, expiring, single-use first-run setup tokens.
Schema version 4 adds stable configuration keys for the YAML runtime mirror.
A pre-migration SQLite snapshot is created automatically before schema 4 and
before the v2.2.0 schema-5 operational tables and columns are installed.
Schema version 6 records each account's first login for notice enrollment,
adds mutable notice timestamps, and stores credential-free backup-target
metadata. SMB passwords remain separate owner-only encrypted secrets.
A database created by a newer Notifinho schema is rejected instead of being
silently downgraded. See the
[user routing and delivery guide](platform-routing.md) for the schema-v2
service contracts.

## Account security foundation

Passwords use the existing salted PBKDF2-SHA256 record with 600,000 iterations
and a minimum length of 12 characters. The database never stores plaintext
passwords, session tokens, or CSRF tokens.

Local login protection includes:

- case-insensitive, normalized usernames;
- persistent failed-login counters;
- a 15-minute lockout after five failed attempts;
- equivalent password verification work for unknown usernames;
- automatic session revocation after a password reset or account disable;
- protection against disabling the last enabled administrator;
- absolute and idle session expiry; and
- a `__Host-` session cookie with `HttpOnly`, `Secure`, `SameSite=Strict`, and
  path `/` defaults.

The platform API wires browser login and platform routing to these services
with CSRF and ownership enforcement. See the
[authenticated platform API guide](platform-api.md) and [WebUI guide](webui.md).

## Production preparation

Create the state directory with the same UID/GID used by the container:

```bash
mkdir -p state
chmod 700 state
```

`compose.production.yaml` mounts `NOTIFINHO_STATE_DIR` at
`/notifinho/state`. Legacy configurations that omit `platform.state_dir` use
`/notifinho/config/platform-state`, allowing an upgrade to reuse the existing
persistent configuration mount. The production Compose mount remains the
recommended layout:

```yaml
platform:
  enabled: true
  state_dir: "/notifinho/state"
  backup_retention: 20
  configuration_model: "unified_yaml_v1"
  secure_cookies: false
```

Platform state initializes or migrates at application startup. When no users
exist, every startup rotates a random 256-bit setup token, writes only its
SHA-256 digest to SQLite, and prints the plaintext token once to container
output. Open the WebUI over HTTPS, enter that token, and choose the first
administrator username and password. The token expires after 30 minutes and is
consumed immediately after successful setup. The WebUI reads and writes the
mounted YAML through validated, atomic server-side operations. External edits
are synchronized automatically; invalid YAML leaves the last known-good
runtime active and is reported for operator repair.

## Trusted recovery CLI

Normal first-run setup does not require the CLI. These commands remain available
for isolated development and host-trusted recovery. Password prompts do not echo
or place values in shell history:

```bash
python3 tools/manage_users.py --state-dir /tmp/notifinho-state init
python3 tools/manage_users.py --state-dir /tmp/notifinho-state \
  create-admin --username administrator
python3 tools/manage_users.py --state-dir /tmp/notifinho-state list-users
```

For a running production image, use the mounted state directory inside the
container:

```bash
docker compose -f compose.production.yaml exec notifinho \
  python3 tools/manage_users.py create-admin --username administrator
```

Additional host-trusted operations are `create-user`, `enable-user`,
`disable-user`, and `reset-password`. Automation may use `--password-env NAME`
instead of a command-line password; the CLI removes that variable from its own
environment after reading it. Never pass passwords as command arguments.

## Backup and rollback

The administrator Data tools page can create a consistent live SQLite and
secret-file snapshot with an integrity manifest. These private snapshots stay
below the state mount and are subject to `platform.backup_retention`. Restore
creates a safety snapshot, stages and verifies the selected backup, and revokes
every browser session. See the [data-portability guide](data-portability.md).

For off-host disaster recovery, stop the container and copy the complete state
directory into encrypted owner-only storage. Do not copy a live SQLite database
with ordinary filesystem tools. Server-side snapshots are not a substitute for
off-host backups.

v2.3.0 through v2.3.2 use schema 6. A v2.2.1 image rejects that newer database, so rollback
requires stopping the container and restoring the complete pre-upgrade state
and configuration backups before pinning `2.2.1`. Never delete or hand-edit
the database to imitate a downgrade.


## Schema 7 integration catalogue state

v2.4.0 adds `routes.input_type` and the `integration_categories` table. The
integration catalogue itself is built into the application image; SQLite stores
only administrator category overrides. A v2.3.7 image cannot open schema-7
state, so application rollback requires restoring the matching schema-6 backup.
