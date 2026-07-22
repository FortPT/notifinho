# v2 authenticated platform API

Phase 4 exposes the local-account, ownership, routing, output, history, and
audit foundations through an opt-in `/api/v2` JSON API. It also provides the
user/application event-ingestion path used by platform routes. Phase 5 adds a
same-origin browser client for this contract; see the [WebUI guide](webui.md).

The API does not include automatic v1.x YAML import or an implicit production
migration. Existing YAML inputs and routes continue to operate independently.

## Activation boundary

All three switches must be intentional:

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
  secure_cookies: true
```

Create the first administrator with `tools/manage_users.py` before enabling
remote access. Keep `secure_cookies: true` behind HTTPS. The `false` value is
only for isolated loopback development because a browser will otherwise send
the session cookie over plain HTTP.

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

The older YAML token API at `/api/events` remains separate and unchanged.

## Endpoints

| Method | Path | Access | Purpose |
|---|---|---|---|
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
| GET | `/api/v2/tokens` | session | list current-user token metadata |
| POST | `/api/v2/tokens` | session + CSRF | create and return a token once |
| POST | `/api/v2/tokens/{id}/rotate` | owner/admin + CSRF | rotate and return a token once |
| POST | `/api/v2/tokens/{id}/revoke` | owner/admin + CSRF | revoke a token permanently |
| GET | `/api/v2/destinations` | session | list owned and visible destinations |
| POST | `/api/v2/destinations` | session + CSRF | create with a write-only secret |
| GET | `/api/v2/destinations/{id}` | visible session | return secret-free metadata |
| PATCH | `/api/v2/destinations/{id}` | owner/admin + CSRF | update metadata or secret |
| DELETE | `/api/v2/destinations/{id}` | owner/admin + CSRF | delete an unused destination |
| POST | `/api/v2/destinations/{id}/preview` | visible session + CSRF | preview payload |
| POST | `/api/v2/destinations/{id}/test` | visible session + CSRF | test delivery |
| GET | `/api/v2/routes` | session | list current-user routes |
| POST | `/api/v2/routes` | session + CSRF | create an owned route |
| GET | `/api/v2/routes/{id}` | owner/admin session | return a route |
| PATCH | `/api/v2/routes/{id}` | owner/admin + CSRF | update a route atomically |
| DELETE | `/api/v2/routes/{id}` | owner/admin + CSRF | delete a route |
| POST | `/api/v2/events` | scoped token or session + CSRF | route an event |
| GET | `/api/v2/deliveries` | session | list up to 100 visible attempts |
| GET | `/api/v2/audit-events` | session | list up to 100 visible audit events |
| GET | `/api/v2/portability/export` | administrator session | export credential-free platform JSON |
| POST | `/api/v2/portability/preview` | administrator + CSRF | preview platform JSON import |
| POST | `/api/v2/portability/import` | administrator + CSRF | apply fingerprinted JSON import |
| POST | `/api/v2/migrations/v1/preview` | administrator + CSRF | preview v1.x YAML migration |
| POST | `/api/v2/migrations/v1/import` | administrator + CSRF | apply fingerprinted YAML migration |
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

Enabling the platform API does not import, modify, or disable existing YAML
tokens, destinations, routes, or listeners. Platform events use only platform
routes. Administrators may explicitly preview and import supported v1.x
Discord/Teams targets and routes, but the migration never rewrites the YAML
file. See the [data-portability guide](data-portability.md).
