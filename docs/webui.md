# v2 WebUI

Phase 5 packages a responsive, dependency-free browser interface in the
Notifinho image. It uses the authenticated `/api/v2` contract over the same
origin. The backend inventories and updates the mounted YAML configuration on
the server; secret values never enter the browser.

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
  configuration_model: "unified_yaml_v1"
  secure_cookies: false

webui:
  enabled: true
  public_url: ""
  enforce_https: false
  language: "en-GB"

presentation:
  timezone: "Europe/Lisbon"
  time_format: "24"
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
  deletion for both issued and YAML-managed applications;
- searchable semantic device/event/input delivery history, audit events with
  selectable 25–500-row page sizes, and operational health checks;
- administrator account creation, enable/disable, and password reset plus a
  resiliently decoded, movable, zoomable circular crop for account pictures;
- separate administrator Inputs and Backups views, named Local/NFS/SMB backup
  targets, private state backup, scheduled or manual copies, safe JSON
  export/import, mounted YAML synchronization, and confirmed restore;
- administrator-only, reasoned, audited process restart (the container
  supervisor performs the actual restart; no shutdown action exists);
- English/Portuguese, IANA timezone, and 12/24-hour global presentation
  settings; and
- account-aware navigation that hides administrator controls from users.

Destination secrets and application-token values are never loaded back into
forms. Token values exist in the page only until the one-time value dialog is
closed. The application does not persist credentials, CSRF values, or API
responses in `localStorage` or `sessionStorage`.

Existing installations do not appear empty. v2.2.0 shows one list of mounted
YAML destinations and routes. Administrators can edit the shared file-backed
resources; users can inspect and preview them but cannot mutate credentials or
routing. Existing `api.tokens` entries are shown as safe metadata, including
scope, rate limit, enabled state, and credential source—never the credential.

An application configured with `token_env` becomes usable only when that
environment variable exists inside the container (for Portainer, add it to the
stack environment). `token_file` requires a readable mode-0600 mounted secret
file at the configured container path. `token_sha256` is immediately available
when it contains a valid 64-character digest. The Applications status reports
**Credential unavailable** when the configured environment variable or file is
missing.

## Browser security boundary

The WebUI contains no CDN, analytics, remote font, frontend package manager,
or runtime template dependency. Every label and API value is inserted with DOM
text nodes rather than interpreted as HTML.

The server sends a restrictive policy on every WebUI asset:

- scripts, styles, images, and API connections are same-origin only;
- frames, plugins, camera, microphone, and geolocation are disabled;
- forms cannot submit off-origin;
- HTML is not cached;
- MIME sniffing is disabled; and
- referrer information is not sent.

The API remains the authority for CSRF, roles, ownership, sharing, rate limits,
secret storage, validation, and audit. Hiding an action in the browser is only
a usability behavior and is not treated as authorization.

## Notice enrollment

Every account sees the two built-in operational notices. Administrator
announcements are enrolled by time: an account starts receiving new
announcements after its first successful login, so a newly created user does
not inherit the complete historical announcement backlog. Persistent system
error and update notices remain lifecycle-bound and are not dismissible.

## Test delivery caution

Preview is local and never contacts the destination. Card-level and preview
test delivery are intentional one-click external actions and use the
configured owner-only credential. Run tests only against a destination you are
authorized to use.
Delivery results contain bounded status and safe error fields, never remote
response bodies or credentials.

## Data tools

Administrators can export credential-free platform JSON, preview and apply an
unchanged JSON import, and manage private server-side state snapshots. Imported
destinations and routes are adopted into the mounted YAML automatically. The
browser never downloads state backups or receives stored credential values.
See the [data-portability guide](data-portability.md) for fingerprints,
retention, and restore-token cautions.
