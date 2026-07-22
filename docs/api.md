# Backend and event API

Notifinho v1.9.0 introduces the disabled-by-default YAML administration and
event API. It reuses the existing dispatcher, notification model, router,
formatters, and outputs; it is not a second delivery pipeline.

The separate opt-in local-session, owned-resource, preview, and user-scoped
event contract is documented in the
[v2 authenticated platform API guide](platform-api.md).

## Authentication

Tokens are configured by environment-variable name, owner-only file, or
SHA-256 digest. Plaintext YAML tokens are rejected. Send a token as
`Authorization: Bearer TOKEN` or `X-Notifinho-Token: TOKEN`.

Roles:

- `application`: submit only sources listed in `sources`;
- `admin`: access backend administration endpoints and any source.

These YAML-backed tokens are not browser sessions and cannot manage v2
platform resources. Do not mix them with the `/api/v2` authentication model.

## Endpoints

| Method | Path | Access | Result |
|---|---|---|---|
| GET | `/api/health` | public when enabled | version and uptime |
| POST | `/api/events` | application/admin | normalized event submission |
| GET | `/api/config` | admin | recursively masked configuration |
| PUT | `/api/config` | admin | validate, back up, atomically replace, reload |
| POST | `/api/config/validate` | admin | schema errors without saving |
| GET | `/api/logs` | admin | last 200 sanitized application-log lines |
| POST | `/api/preview` | admin | real Discord or Teams formatter payload |
| POST | `/api/test-send` | admin | route through configured outputs |

Example generic event:

```bash
curl -sS \
  -H 'Authorization: Bearer TOKEN' \
  -H 'Content-Type: application/json' \
  --data '{
    "schema":"notifinho.event.v1",
    "source":"home_lab",
    "title":"Synthetic warning",
    "message":"A bounded application event.",
    "severity":"warning",
    "status":"active",
    "timestamp":"2026-07-15T21:00:00Z"
  }' \
  http://127.0.0.1:18080/api/events
```

The token must include `home_lab`, and `routing.home_lab` must select at least
one configured output target.

## Configuration safety

`GET /api/config` returns `<configured>` for secret leaves. Sending that masked
document back in `PUT /api/config` preserves the existing secret values. The
service validates before writing, creates mode-`0600` backups, uses an atomic
replace, reloads configuration under a lock, and retains the ten newest
backups. Output routes and token definitions are read from the reloaded
configuration. Listener bind address, port, maximum request size, SMTP
transport, and TLS settings require a controlled container restart. Audit
records omit bodies, credentials, and query strings and are
created mode `0600`.

The API should remain on a trusted network or behind TLS termination in Nginx
Proxy Manager. Do not publish port 8080 directly to the Internet. Apply
firewall restrictions, use long random tokens, mount token files read-only,
and configure conservative per-token rate limits.
