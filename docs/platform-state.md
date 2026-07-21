# v2 platform state and local accounts

Notifinho's v2 platform foundation uses SQLite and owner-only secret files. It
does not require PostgreSQL, Redis, or another container. The feature remains
disabled by default while the v2 API and WebUI are under development, so the
existing v1.x YAML configuration, tokens, routes, and delivery behavior remain
authoritative.

## Storage layout

When enabled, the default container layout is:

```text
/notifinho/state/
|- notifinho.db
`- secrets/
   `- generated-identifier.v1
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

The browser login and platform-routing endpoints are intentionally not exposed
in these foundation phases. They will be wired to these services with CSRF and
ownership enforcement before the WebUI is enabled.

## Production preparation

Create the state directory with the same UID/GID used by the container:

```bash
mkdir -p state
chmod 700 state
```

`compose.production.yaml` mounts `NOTIFINHO_STATE_DIR` at
`/notifinho/state`. Keep the platform disabled in `config/config.yaml` until
account bootstrap and v2 API validation are planned:

```yaml
platform:
  enabled: false
  state_dir: "/notifinho/state"
```

Enabling platform state initializes or migrates the database at application
startup. It does not enable a WebUI or replace YAML routes.

## Administrator CLI

The CLI prompts for passwords without echoing or placing them in shell history.
Initialize a temporary development state and create its first administrator:

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

Before a schema-changing upgrade, stop the container and copy the complete
state directory to an owner-only backup. Do not copy a live SQLite database
with ordinary filesystem tools.

Phase 1 rollback is non-destructive: set `platform.enabled` to `false` and run
the previously validated image. The older image ignores the preserved state
directory. Never delete or downgrade the database; restore a matching backup
if a later release's migration notes require it.
