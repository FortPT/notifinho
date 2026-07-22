# v2 WebUI

Phase 5 packages a responsive, dependency-free browser interface in the
Notifinho image. It uses the authenticated `/api/v2` contract over the same
origin and never reads or writes the YAML configuration directly.

## Activation

The WebUI is deliberately gated by four switches:

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

webui:
  enabled: true
```

Bootstrap the first administrator with `tools/manage_users.py`, restart
Notifinho, and open the HTTPS URL for port 8080. The interface is served at
`/`; its packaged assets live below `/ui/`.

Keep `platform.secure_cookies: true` outside isolated loopback development.
The login session is unusable over plain HTTP with secure cookies enabled by
design. Terminate TLS at a trusted reverse proxy and do not expose port 8080
directly to the Internet.

## Included workflows

- local login, logout, current-session status, and password change;
- responsive overview and first-run progress;
- private/shared destination creation, editing, enable/disable, deletion,
  preview, and explicit test delivery;
- output-specific settings and write-only credential forms for Discord,
  Microsoft Teams, Slack, generic webhooks, MQTT, and ntfy;
- user-owned route creation, filtering, editing, ordering, enable/disable, and
  deletion;
- one-time application-token creation and rotation plus permanent revocation;
- searchable delivery history and audit events;
- administrator account creation, enable/disable, and password reset;
- administrator-only safe JSON export/import, v1.x YAML migration preview,
  private state backup, and confirmed restore; and
- account-aware navigation that hides administrator controls from users.

Destination secrets and application-token values are never loaded back into
forms. Token values exist in the page only until the one-time value dialog is
closed. The application does not persist credentials, CSRF values, or API
responses in `localStorage` or `sessionStorage`.

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

## Test delivery caution

Preview is local and never contacts the destination. Test delivery is an
explicitly confirmed external action and uses the configured owner-only
credential. Run tests only against a destination you are authorized to use.
Delivery results contain bounded status and safe error fields, never remote
response bodies or credentials.

## Data tools

Administrators can export credential-free platform JSON, preview and apply an
unchanged JSON import, migrate supported v1.x Discord/Teams YAML targets and
routes, and manage private server-side state snapshots. The browser never
downloads state backups or receives stored credential values. See the
[data-portability guide](data-portability.md) for fingerprint, rollback,
retention, and restore-token cautions. Existing YAML routing continues
unchanged until the operator deliberately changes it.
