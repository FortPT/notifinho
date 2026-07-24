# v2 authenticated platform API

Phase 4 exposes the local-account, ownership, routing, output, history, and
audit foundations through the `/api/v2` JSON API. It also provides the
user/application event-ingestion path used by platform routes. Phase 5 adds a
same-origin browser client for this contract; see the [WebUI guide](webui.md).

v2.3.2 exposes credential-free mounted YAML metadata, administrator-only
atomic mutations, notice lifecycle controls, backup destinations, and audited
restart. The browser never receives destination, application-token, or remote
share credential material.

## Default and activation boundary

The HTTP transport, API, and platform are enabled when their switches are
omitted. An operator can still disable any layer explicitly:

```yaml
http:
  enabled: true
  host: "0.0.0.0"
  port: 8080

api:
  enabled: true

platform:
  enabled: true
  state_dir: "/notifinho/state"
  configuration_model: "platform_database_v1"
  secure_cookies: false
```

On an empty database, `GET /api/v2/bootstrap` reports that setup is required.
The image prints a short-lived, single-use setup token to container output;
`POST /api/v2/bootstrap` consumes it while creating the first administrator
and browser session. The `false` value permits direct HTTP login only on a
trusted private network because a browser sends the session cookie without
transport encryption. Use `secure_cookies: true`, `webui.enforce_https: true`,
and a TLS reverse proxy for untrusted or Internet-facing access.

Do not expose port 8080 directly to the Internet. Terminate TLS at a trusted
reverse proxy, apply firewall restrictions, preserve the original client
address, and do not cache `/api/v2` responses.

## Authentication boundary

Browser and management operations use a local session:

- `POST /api/v2/session` accepts a username and password;
- the server returns an `HttpOnly`, `SameSite=Strict` session cookie;
- secure deployments use `__Host-` cookie names and the `Secure` attribute;
- the one-time CSRF value is returned in the login response and a readable,
  same-site CSRF cookie; and
- every session-authenticated `POST`, `PUT`, `PATCH`, and `DELETE` request must
  send the value as `X-CSRF-Token`.

Sessions have absolute and idle expiry. Logout, password reset, and account
disable revoke them. Login attempts retain the persistent lockout rules and
also have a per-client in-memory rate limit. Authenticated session requests
have a separate per-session/per-client rate limit.

Platform API tokens are accepted only by `POST /api/v2/events`. They cannot be
used for account, token, destination, route, preview, history, or audit
management. Tokens are source-scoped, rate-limited per token and client,
returned only at creation or rotation, and stored only as SHA-256 digests.

Legacy YAML application tokens are imported into SQLite during the v2.5 migration.
Their existing values continue working, but token management is database-only
after migration.

## Endpoints

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/v2/bootstrap` | public | report whether first-run setup is required |
| POST | `/api/v2/bootstrap` | single-use setup token | create the first administrator and session |
| POST | `/api/v2/session` | public | authenticate a local account |
| GET | `/api/v2/session` | session | return the current account |
| DELETE | `/api/v2/session` | session + CSRF | revoke the current session |
| GET | `/api/v2/users` | administrator session | list local accounts |
| POST | `/api/v2/users` | administrator session + CSRF | create an account |
| GET | `/api/v2/users/{id}` | administrator session | return an account |
| PATCH | `/api/v2/users/{id}` | administrator session + CSRF | enable or disable an account |
| PUT | `/api/v2/users/{id}/password` | administrator + CSRF | reset password and sessions |
| GET | `/api/v2/users/{id}/tokens` | administrator session | list an owner's token metadata |
| GET | `/api/v2/users/{id}/routes` | administrator session | list an owner's routes |
| PUT | `/api/v2/account/password` | session + CSRF | change the current password |
| PUT/DELETE | `/api/v2/account/avatar` | session + CSRF | set or remove the current profile picture |
| GET/PUT | `/api/v2/source-categories` | session / administrator + CSRF for PUT | list or update source presentation tags |
| GET | `/api/v2/integration-settings` | session | list isolated integration behavior and per-resource errors |
| GET/PUT | `/api/v2/integration-settings/{source}` | session / administrator + CSRF for PUT | inspect or update one integration settings record |
| GET | `/api/v2/version` | session | return running and advertised update versions |
| GET/POST | `/api/v2/notices` | session / administrator + CSRF | list or publish operational notices |
| POST | `/api/v2/notices/{id}/dismiss` | session + CSRF | dismiss an ordinary notice for this account |
| PATCH/DELETE | `/api/v2/notices/{id}` | administrator + CSRF | edit or resolve an administrator notice |
| GET | `/api/v2/metrics/{range}` | session | return Overview metrics for 10m, 1h, 1d, 1m, or 1y |
| GET | `/api/v2/health-checks` | session | run safe operational checks |
| GET/PUT | `/api/v2/backup-settings` | administrator + CSRF for PUT | inspect or update backup schedule and target |
| GET/POST | `/api/v2/backup-targets` | administrator + CSRF for POST | list or create Local/NFS/SMB backup targets |
| GET/PATCH/DELETE | `/api/v2/backup-targets/{id}` | administrator + CSRF for mutation | inspect, update, or remove a target |
| POST | `/api/v2/backup-targets/{id}/test` | administrator + CSRF | test connectivity and write access |
| POST | `/api/v2/backups/run` | administrator + CSRF | run a backup against the selected target |
| POST | `/api/v2/reboot` | administrator + CSRF | record a reason and request process restart |
| GET | `/api/v2/tokens` | session | list current-user token metadata |
| POST | `/api/v2/tokens` | session + CSRF | create and return a token once |
| POST | `/api/v2/tokens/{id}/rotate` | owner/admin + CSRF | rotate and return a token once |
| POST | `/api/v2/tokens/{id}/revoke` | owner/admin + CSRF | revoke a token permanently |
| PATCH/DELETE | `/api/v2/tokens/{id}` | owner/admin + CSRF | enable, disable, or delete an application |
| GET | `/api/v2/destinations` | session | list database-backed destinations plus isolated row errors |
| POST | `/api/v2/destinations` | administrator + CSRF | create a database destination with a write-only secret |
| GET | `/api/v2/destinations/{id}` | visible session | return secret-free metadata |
| PATCH | `/api/v2/destinations/{id}` | administrator + CSRF | update database metadata, type, or secret while preserving the ID |
| DELETE | `/api/v2/destinations/{id}` | administrator + CSRF | delete an unused database destination |
| POST | `/api/v2/destinations/{id}/preview` | visible session + CSRF | preview payload |
| POST | `/api/v2/destinations/{id}/test` | administrator + CSRF | test delivery |
| GET | `/api/v2/routes` | session | list database-backed routes plus isolated row errors |
| POST | `/api/v2/routes` | administrator + CSRF | create a database-backed route |
| GET | `/api/v2/routes/{id}` | owner/admin session | return a route |
| PATCH | `/api/v2/routes/{id}` | owner/admin + CSRF | update a route atomically |
| DELETE | `/api/v2/routes/{id}` | owner/admin + CSRF | delete a route |
| POST | `/api/v2/events` | scoped token or session + CSRF | route an event |
| GET | `/api/v2/deliveries` | session | list visible owned or shared attempts |
| GET | `/api/v2/audit-events` | session | list up to 500 visible audit events |
| GET | `/api/v2/portability/export` | administrator session | export credential-free platform JSON |
| POST | `/api/v2/portability/preview` | administrator + CSRF | preview platform JSON import |
| POST | `/api/v2/portability/import` | administrator + CSRF | apply fingerprinted JSON import |
| POST | `/api/v2/migrations/v1/preview` | administrator + CSRF | preview v1.x YAML migration |
| POST | `/api/v2/migrations/v1/import` | administrator + CSRF | apply fingerprinted YAML migration |
| GET | `/api/v2/configuration/inventory` | administrator session | inspect mounted YAML without credentials |
| GET | `/api/v2/preferences` | session | read language, timezone, and clock format |
| PUT | `/api/v2/preferences` | administrator + CSRF | update the isolated regional settings record |
| GET | `/api/v2/backups` | administrator session | list verified state backups |
| POST | `/api/v2/backups` | administrator + CSRF | create a private state backup |
| POST | `/api/v2/backups/{id}/restore` | administrator + CSRF | confirmed restore and session revocation |

An administrator may create a resource for another owner by including
`owner_user_id`. A regular user cannot select another owner. Only an
administrator can create or change a shared destination, create wildcard
tokens/routes, create administrator tokens, or allow private-network output
delivery.

## Session example

Login saves both cookies and returns the CSRF value:

```bash
curl --fail-with-body \
  --cookie-jar /tmp/notifinho.cookies \
  --header 'Content-Type: application/json' \
  --data '{"username":"administrator","password":"REPLACE_ME"}' \
  https://notifinho.example.com/api/v2/session
```

Send the returned `csrf_token` on every state-changing session request:

```bash
curl --fail-with-body \
  --cookie /tmp/notifinho.cookies \
  --header 'Content-Type: application/json' \
  --header 'X-CSRF-Token: RETURNED_LOGIN_VALUE' \
  --data '{
    "name":"Home lab application",
    "source_scopes":["home_lab"],
    "rate_limit_per_minute":60
  }' \
  https://notifinho.example.com/api/v2/tokens
```

The `value` field appears only in this response or a successful rotation.
Store it immediately in the submitting application. It cannot be retrieved
later.

## Destination secret example

Public settings and credentials are deliberately separate in the request:

```json
{
  "name": "Operations webhook",
  "output_type": "webhook",
  "settings": {
    "method": "POST",
    "timeout_seconds": 15,
    "sign_hmac": true
  },
  "secret": {
    "url": "https://receiver.example.com/notifinho",
    "hmac_secret": "REPLACE_ME"
  }
}
```

The response contains `secret_configured: true`; it never contains the secret,
secret-file path, stored digest, webhook URL, password, or token. Updating the
`secret` field rotates the owner-only secret. A user may route to or test a
shared destination but cannot read or replace its owner's credentials.

## Event submission

Applications submit the stable event envelope with a platform token:

```bash
curl --fail-with-body \
  --header 'Authorization: Bearer PLATFORM_TOKEN' \
  --header 'Content-Type: application/json' \
  --data '{
    "schema":"notifinho.event.v1",
    "source":"home_lab",
    "title":"Synthetic warning",
    "message":"A bounded application event.",
    "severity":"warning",
    "status":"active"
  }' \
  https://notifinho.example.com/api/v2/events
```

The token must include `home_lab`. The service evaluates only the token owner's
enabled platform routes and internally resolves secrets as each destination's
true owner. The response reports matched routes, successful/failed deliveries,
and total attempts; it never includes response bodies or destination secrets.

## Safe responses and compatibility

All `/api/v2` responses use `Cache-Control: no-store`,
`X-Content-Type-Options: nosniff`, and `Referrer-Policy: no-referrer`. Error
messages are intentionally generic. Preview and test responses use bounded
backend formatters and safe transport results. Delivery history and audit
events are owner-filtered; administrators may inspect all retained records.

The mounted file is authoritative. The legacy v1.x upload endpoints remain for
API compatibility; successful imports are adopted into YAML automatically.
See the [data-portability guide](data-portability.md).
