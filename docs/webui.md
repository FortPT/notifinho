# v2 WebUI

Phase 5 packages a responsive, dependency-free browser interface in the
Notifinho image. It uses the authenticated `/api/v2` contract over the same
origin. The backend manages destinations, routes, applications, preferences, aliases,
and integration behavior in isolated SQLite resources; secret values never
enter the browser. The mounted YAML contains only process bootstrap, listeners,
and transport security.

## Default activation

The WebUI is enabled by default and remains gated by four switches so an
operator can explicitly disable any layer:

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

webui:
  enabled: true
  public_url: ""
  enforce_https: false
```

On the first start, read the single-use setup token from container output and
open the HTTP URL for port 8080 on the trusted LAN. The first-run screen lets you choose the
administrator username and password. No default account exists, and no shell
command is required. The interface is served at `/`; packaged assets live
below `/ui/`.

`webui.public_url` is optional. A plain-HTTP WebUI request receives a 308
redirect only when the canonical URL is set and `webui.enforce_https: true`.
Notifinho does not provision a certificate or HTTPS listener; the configured
reverse proxy must terminate TLS at that URL.

Use `platform.secure_cookies: false` only on a trusted private network. Set it
to `true` with HTTPS enforcement for Internet-facing or reverse-proxied access.
The login session is intentionally unusable over plain HTTP when Secure cookies
are enabled.

## Included workflows

- local login, logout, current-session status, and password change;
- administrator notice publishing, per-user ordinary-notice dismissal, and
  lifecycle-bound system error/update notices;
- a profile-picture dropdown for Security and Sign out, plus dedicated Sources
  and Updates views;
- packaged vendor icons, built-in integrations, expandable SMTP/HTTP/Redfish
  inputs, and integration-level categories;
- responsive overview with every active, disabled, or unhealthy source → route
  → destination path, five server-side history ranges, and recent deliveries;
- private/shared destination creation, editing, enable/disable, deletion,
  preview, and explicit test delivery;
- output-specific settings and write-only credential forms for Discord,
  Microsoft Teams, Slack, generic webhooks, MQTT, and ntfy;
- user-owned route creation, filtering, semantic-priority editing,
  enable/disable, and
  deletion;
- one-time application-token creation and rotation plus enable/disable and
  deletion for database-managed applications, including safely migrated values;
- searchable semantic device/event/input delivery history, audit events with
  selectable 25–500-row page sizes, and operational health checks;
- administrator account creation, enable/disable, and password reset plus a
  resiliently decoded, movable, zoomable circular crop for account pictures;
- separate administrator Inputs and Backups views, named Local/NFS/SMB backup
  targets, private state backup, scheduled or manual copies, safe JSON
  export/import, database resource backups, and confirmed restore;
- a top-right administrator-only, reasoned, audited process restart (the
  container supervisor performs the actual restart; no shutdown action exists);
- English/Portuguese, IANA timezone, and 12/24-hour global presentation
  settings; and
- account-aware navigation that hides administrator controls from users.

Destination secrets and application-token values are never loaded back into
forms. Token values exist in the page only until the one-time value dialog is
closed. The application does not persist credentials, CSRF values, or API
responses in `localStorage` or `sessionStorage`.

Existing v2.4 installations do not appear empty. On the first v2.5 start,
Notifinho imports mounted YAML destinations, routes, API applications, aliases,
notification preferences, regional settings, and backup scheduling into schema
8. The YAML file is then normalized atomically and all later edits happen in the
WebUI.
