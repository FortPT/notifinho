# Changelog

## Unreleased

## 2.5.1 - 2026-07-25

### Changed

- Treat wildcard routes as fallback-only and suppress duplicate deliveries to the
  same destination.
- Standardize every integration input label to SMTP, HTTP, or Redfish.
- Replace passive destination badges with clickable Enabled/Disabled and
  Shared/Private controls.
- Rename Applications to Event API tokens and populate source scopes from the
  built-in integration catalogue.
- Move Xen Orchestra outcome selection into route status filters and add
  include/exclude filters for hosts, events, severities, and statuses.

### Fixed

- Prevent dedicated iDRAC events from also reaching the default destination.
- Remove redundant source-input descriptions and the positive Credentials set
  badge.
- Correct integration-settings card spacing and preserve independent resource
  error boundaries.
- Make production validation use a durable pre-upgrade baseline when available
  and continue current-state validation when it is unavailable.

## 2.5.0 - 2026-07-24

### Changed

- Make SQLite authoritative for destinations, routes, API applications,
  regional preferences, backup scheduling, integration behavior, and aliases.
- Normalize `config.yaml` to process bootstrap, listener, and security settings.
- Add WebUI editors for XO, Zabbix, Dell iDRAC, UniFi Protect, Home Assistant,
  and Redfish behavior.
- Upgrade platform state to schema 8 with isolated settings records.

### Fixed

- Keep valid destinations and routes available when one stored row is invalid.
- Fall back safely when one integration-settings row is damaged.
- Preserve existing application-token values during one-way YAML migration.
- Replace generic event-submission failures with safe reference-coded errors.

## 2.4.0 - 2026-07-24

### Changed

- Replace discovered Sources with an always-available built-in integration catalogue.
- Expand integrations to show their supported SMTP, HTTP, or Redfish inputs.
- Store integration category overrides in SQLite instead of `config.yaml`.
- Replace free-text route sources with integration/input choices such as
  Zabbix (SMTP), Zabbix (HTTP), Generic (HTTP), and Generic (Redfish).
- Allow administrators to change a destination type while preserving route intent.

### Fixed

- Reject duplicate destination display names before writing `config.yaml`.
- Enable the parent output provider when an enabled destination is created or enabled.
- Roll back YAML changes when synchronization fails and preserve file ownership/mode.
- Return actionable API errors with HTTP status, endpoint, error code, and reference ID.
- Retire the test-only Home Lab Generic route during the source-model migration.


## 2.3.7 - 2026-07-24

### Fixed

- Keep every WebUI Overview source card the same size as Home Assistant.
- Keep desktop icon layout boxes at 48 × 48 px and mobile boxes at 44 × 44 px.
- Scale only the visible Notifinho, Dell iDRAC, UniFi Network, UniFi Protect,
  QNAP, and Synology artwork without changing card or icon-box dimensions.
- Leave notification payloads, formatters, destination icons, and delivery
  rendering unchanged.

## 2.3.6 - 2026-07-24

### Fixed

- Restore every non-target Overview source icon to the pre-v2.3.5 size.
- Keep enlargement limited to Notifinho, Dell iDRAC, UniFi Network, UniFi
  Protect, QNAP, and Synology.
- Use the official DMTF Redfish logo for the `redfish` source while retaining the
  neutral REST icon for `restful` and `rest_api` aliases.

## 2.3.5 - 2026-07-23

### Fixed

- Map `xo` to Xen Orchestra and map `redfish`, `restful`, and `rest_api` to a
  packaged neutral REST API icon instead of the generic Notifinho fallback.
- Increase the visual size of Notifinho, Dell iDRAC, UniFi Network, UniFi
  Protect, QNAP, and Synology icons in the Overview routing flow.
- Make inactive-source removal independent of DELETE request bodies by placing
  the source key in the URL path.

## 2.3.4 - 2026-07-23

### Fixed

- Keep the active WebUI page across F5 and browser reloads more reliably by
  reapplying the requested hash-backed view after the authenticated workspace is
  rendered.
- Accept inactive-source removal requests using `source`, `id`, or `name`, so
  the current Sources view no longer returns `request is invalid!`.
- Finalize transparent source icon sizing for Notifinho, Dell iDRAC, UniFi
  Network, UniFi Protect, QNAP, and Synology.
- Retain source-aware destination-card tests, bounded GitHub update checks, and
  selected 12/24-hour backup time entry while publishing the final release as
  `2.3.4`.

### Changed

- Keep platform schema 6 and the v2.3.3 unified configuration/state model
  directly compatible.

## 2.3.3 - 2026-07-23

### Fixed

- Preserve the active WebUI page across F5 and browser reloads, with the URL
  hash authoritative and a session-scoped fallback when it is absent.
- Allow safe removal of an inactive exact source when only a wildcard route is
  enabled, while returning HTTP 409 when an enabled exact route still uses it.
- Send destination-card tests through the formatter associated with the best
  specific route for that destination, including Supermicro, HPE iLO, Dell
  iDRAC, Home Assistant, Grafana, Portainer, Proxmox, UniFi, and Zabbix.
- Render and validate scheduled backup time using the selected 12-hour or
  24-hour preference instead of the browser or operating-system locale.

### Added

- Add a Home Assistant-style three-dot operations menu with Check for updates
  and administrator-only Restart Notifinho actions.
- Check the official GitHub releases API after authenticated startup, every six
  hours, when a stale tab becomes visible, and on demand without sending
  Notifinho credentials.

### Changed

- Present packaged source icons transparently at a larger size without the
  former white background tile.
- Keep platform schema 6 and the v2.3.2 unified configuration/state model
  directly compatible.

## 2.3.2 - 2026-07-23

### Fixed

- Prefer the browser-session cookie matching the configured HTTP/HTTPS mode
  when legacy Secure and current standard cookies coexist.
- Treat enabled wildcard routes as activating every discovered source.
- Send destination-card tests as generic Notifinho events instead of Home
  Assistant events, preserving the selected destination and channel.
- Complete the managed-mount Compose override with `DAC_OVERRIDE`, `FOWNER`,
  and `SYS_ADMIN` so root can read existing configuration, write logs, secure
  platform state, and mount NFS/SMB shares after capabilities are dropped.
- Disable NLM for managed NFS backup mounts so NFSv3 does not require
  `rpc.statd` runtime files on the read-only container filesystem.

### Added

- Serve the packaged official vendor icons in Overview and Sources, with the
  Notifinho icon used for wildcard, custom, and otherwise generic sources.
- Add Virtualization, Monitoring, Storage, Networking, Hardware, Automation,
  Containers, Security, and Generic source categories.
- Add confirmation-protected removal for inactive sources while retaining
  delivery history and rejecting removal through enabled exact or wildcard
  routes.

### Changed

- Move the administrator Restart action from Settings to the top-right WebUI
  header while retaining the mandatory reason and audit trail.
- Preserve legacy source-category values during upgrade by mapping them to the
  new purpose-specific categories.
- Platform schema remains 6 and v2.3.1 configuration/state are directly
  compatible.

## 2.3.1 - 2026-07-23

### Fixed

- Allowed direct HTTP WebUI login on trusted networks by making HTTPS
  redirection explicit and defaulting new installations to non-Secure cookies.
- Replaced the header connection, refresh, and sign-out controls with a profile
  picture dropdown containing Security and Sign out.
- Fixed administrator notice create/update rendering without F5 by retaining
  the form reference across the asynchronous request.
- Corrected Home Assistant API and vendor Redfish input names in Routing Flow,
  Routes, and Sources.
- Automatically enables managed mounting when an NFS or SMB destination is
  saved through the WebUI.
- Made scheduled-backup display follow the selected 12/24-hour preference.
- Added a bitmap/data-URL profile-picture decode fallback before drag/zoom crop.

### Added

- Added Sources and Updates views plus administrator-editable source tags.
- Added category-specific source colours, stopped yellow disabled flows, moving
  red error crosses, and blue information deliveries.

### Changed

- Metric cards now explicitly count Active Sources, Active Destinations, and
  Active Routes.
- Moved Audit Log row selection to the bottom and increased spacing before
  Restart Notifinho.
- Platform schema remains 6 and v2.3.0 configuration/state are directly
  compatible.

## 2.3.0 - 2026-07-23

### Added

- Added named Local, NFS, and SMB backup destinations with masked credentials,
  connectivity and write tests, per-target scheduling, manual execution, and
  an explicitly privileged Compose override for managed remote mounts.
- Added administrator notice editing and resolution, first-login notice
  enrollment, categorized source presentation, animated routing direction,
  a reasoned and audited restart action, and a movable/zoomable avatar crop.
- Added read-only user access to Overview resources and shared Delivery
  History, plus Audit Log page sizes of 25, 50, 100, 150, 250, and 500.
- Added an optional canonical HTTPS URL so requests arriving over HTTP can be
  redirected before login while secure cookies remain enabled.

### Changed

- Simplified and centered the login page, enlarged its brand, moved Sign out to
  the header, separated Inputs from Backups, and placed the history range next
  to the Success and Requests metrics.
- Destination cards now show channel labels and provide immediate test
  delivery; preview tests use the edited payload, output types are immutable,
  and preview generation no longer produces a redundant success notice.
- Removed route-order controls in favor of semantic priority and improved the
  flow view with source categories, real input transports, and reduced-motion
  aware animation.
- Reworked Delivery History titles, spacing, event details, input transport,
  and severity styling so error and failure events remain red even when their
  delivery succeeds.

### Fixed

- Notice publishing, editing, resolving, health checks, Audit Log updates, and
  other affected workspace actions now refresh their component immediately
  without requiring a browser reload.
- New accounts see only the two operational defaults before first login and
  receive subsequent administrator announcements only after joining.

### Security

- Remote-share passwords remain write-only encrypted secrets and are never
  returned by the API. Host-mounted shares remain the recommended production
  model; managed NFS/SMB mounting requires the explicit privileged override.
- Restart is administrator-only, CSRF-protected, requires a recorded reason,
  and produces an audit event before the process receives its termination
  signal.

## 2.2.1 - 2026-07-22

### Fixed

- Fixed the administrator configuration inventory after a route action writes
  a semantic priority such as `normal`, preserving the route's enabled state
  and returning its normalized numeric and named priority.
- Isolated WebUI workspace requests so a failed component no longer prevents
  successful destinations, routes, deliveries, or other sections from
  rendering.
- Preserved an authenticated session when a non-authentication workspace
  request fails and added a visible component-specific failure notice.

## 2.2.0 - 2026-07-22

### Added

- Added administrator announcements and account-specific notice dismissal.
  Configuration, routing, backup, and update notices remain visible until the
  underlying condition is resolved and then clear automatically.
- Added server-side Overview metrics for 10 minutes, 1 hour, 1 day, 1 month,
  and 1 year, including active resources, request volume, and delivery success.
- Added complete routing-flow status, semantic priority names and ordering,
  channel labels, original packaged Discord/MQTT/ntfy icons, and disabled or
  unhealthy route visibility.
- Added application usage counters, enable/disable/delete controls, account
  profile pictures, delivery device/event/input fields, and operational health
  checks alongside the audit log.
- Added daily, weekly, and monthly private-state backup scheduling with safe
  copying to host-mounted NFS or SMB storage.

### Changed

- Reworked Destinations, Routes, Applications, Users, Delivery history, and
  Inputs & backups so status badges are direct controls and configuration-only
  labels no longer leak into ordinary resource presentation.
- Destination preview now uses the selected output with a representative live
  source, destination sharing persists through YAML synchronization, and route
  filters use named priority, severity, and status choices.
- Increased the navigation brand icon size and made dismissed notice panels
  collapse without leaving layout gaps.

### Security

- Profile pictures accept only signature-validated PNG, JPEG, or WebP data up
  to 256 KiB and remain inside protected platform state.
- External backups require a bounded existing host-mounted directory; the
  application does not mount NFS/SMB itself or handle network-share passwords.
- Schema 5 preserves an automatic pre-upgrade SQLite snapshot and retains the
  last-known-good unified configuration when external YAML is invalid.

## 2.1.0 - 2026-07-22

### Added

- Added a live, bidirectional `config.yaml` synchronization layer. Valid file
  edits are detected before WebUI refreshes and event routing; administrator
  WebUI edits are validated, backed up, and written atomically to that same
  mounted file.
- Added an Overview signal-flow map covering every active route and enabled
  destination, while retaining operational metrics and recent deliveries.
- Added global timezone, English/Portuguese language, and 12/24-hour settings.
  Twelve-hour timestamps include AM/PM and remain on one line.
- Added safe visibility for legacy YAML application-token metadata without
  exposing token values, hashes, environment values, or secret-file contents.
- Added automatic pre-schema-upgrade SQLite backups and schema 4 mirror keys.

### Changed

- Replaced the v2.0.2 database-authority takeover and duplicated YAML fallback
  rows with one YAML-backed destination list and one YAML-backed route list.
- Administrators can create, rename, edit, enable, disable, and delete shared
  destinations and routes; users have read/preview access only.
- Destination test delivery now reports the real success/failure result and is
  restricted to administrators for shared YAML credentials.
- The dashboard treats the persisted `delivered` outcome as success and no
  longer shows the setup-oriented Quick Start panel.
- Administrators can reset another user's password from Users; their own
  password remains exclusively managed through Account security.

### Security

- Invalid external YAML never replaces the last known-good runtime state. The
  WebUI reports the validation error until the operator repairs the file.
- Nested credential objects are recursively redacted while non-secret token
  metadata remains visible.

## 2.0.2 - 2026-07-22

### Added

- Added an administrator-only server-side inventory of mounted YAML inputs,
  Discord/Teams destinations, routes, credential presence, supported migration
  scope, and active routing authority. Secret values never enter the browser,
  preview response, or database.
- Added a previewed mounted-configuration takeover that verifies an unchanged
  SHA-256 fingerprint, creates automatic platform-state and atomic YAML
  backups, imports credentials directly into owner-only secret files, and
  activates WebUI-managed routing in one confirmed operation.
- Added clearly labelled YAML-managed and WebUI-managed resources throughout
  the dashboard, destinations, routes, and Data tools views.
- Added confirmed routing-authority controls that can immediately return legacy
  SMTP and webhook events to the retained YAML fallback or reactivate WebUI
  routing without repeating migration.

### Changed

- Updated GitHub and Docker workflow actions to their current Node.js 24
  majors, removing the release-runner Node.js 20 deprecation annotation.
- Legacy SMTP and native webhook events use platform-owned destinations and
  routes after `platform.routing_authority` becomes `database`; before takeover
  the existing YAML router remains the only authority.
- Dashboard counts now reflect the active routing authority, so upgraded
  installations no longer appear unconfigured while YAML routing is active.
- The manual YAML upload remains available for another server, while the
  mounted configuration uses the safer server-side flow.

### Security

- Migration is administrator-only, CSRF-protected, preview-first, fingerprint
  bound, collision rejecting, and single-authority. A failed configuration
  switch removes only the newly created database resources and leaves the
  original YAML routing active.
- The original YAML destinations and routes remain untouched as an inactive
  rollback fallback after takeover, preventing both destructive migration and
  duplicate delivery.

## 2.0.1 - 2026-07-22

### Changed

- Enabled the HTTP listener, platform API, persistent platform state, and
  same-origin WebUI by default while continuing to honor every explicit
  `enabled: false` setting.
- Changed the missing-state-directory fallback to
  `/notifinho/config/platform-state`, preserving first-run state for legacy
  upgrades that already persist the configuration mount. Production Compose
  continues to use its dedicated `/notifinho/state` mount.
- Kept the legacy SMTP/webhook pipeline running when an upgraded configuration
  omits the platform switch but its existing configuration mount is not
  writable; explicit platform enablement continues to fail closed.

### Added

- Added an image-managed first-run flow that rotates a cryptographically random
  setup token on startup until an account exists, stores only its SHA-256
  digest, expires it after 30 minutes, rate-limits attempts, and consumes it
  after creating the first administrator.
- Added a responsive first-run WebUI that accepts the one-time container-output
  token and lets the operator choose the initial administrator username and
  password without running an account-management command.

### Security

- No shared default password or unauthenticated first-visitor registration is
  introduced. Existing account databases skip bootstrap, secure cookies remain
  enabled, and the setup token is invalid after use or restart.

## 2.0.0 - 2026-07-22

### Changed

- Added pull-request and main-branch CI, automated dependency update checks,
  exact Python dependency pins, and immutable Python container base images.
- Separated development and production Compose workflows and documented a
  hardened production deployment with a non-root user, read-only filesystem,
  dropped capabilities, and bounded shutdown behavior.
- Updated contributor, Docker Hub, Grafana, QNAP, and Synology documentation
  to match the current branch, validation status, security guidance, and v2.0
  roadmap.

### Fixed

- Output-level `enabled` settings are now validated and honored by routing,
  while configurations that omit the setting retain legacy enabled behavior.
- Container shutdown now reaches the application signal handler and exits
  cleanly instead of relying on forced termination.

### Added

- Added administrator-only safe platform JSON export/import with owner-aware
  destination references, strict schema/size validation, merge-only behavior,
  credential exclusion, preview fingerprints, and failed-import rollback.
- Added previewed v1.x Discord/Teams YAML target and route migration with
  write-only credential storage, placeholder detection, supported host-filter
  translation, and unchanged legacy YAML behavior.
- Added integrity-manifested private state backups for SQLite and secret files,
  bounded retention, pre-restore safety snapshots, staged rollback, exact-ID
  confirmation, and mandatory browser-session revocation after restore.
- Added responsive administrator Data tools for safe download, JSON/YAML
  previews, confirmed imports, backup creation/listing, and restore, plus data
  portability and restore-security documentation.
- Added a disabled-by-default, responsive, same-origin v2 WebUI for login,
  account security, destinations, routes, application tokens, delivery
  history, audit events, and administrator user management.
- Added output-specific destination forms, write-only credential handling,
  one-time token display, safe preview, confirmed test delivery, searchable
  operational history, responsive navigation, and accessible dialogs.
- Added a dependency-free packaged asset service with exact route allowlisting,
  strict content security, frame, referrer, permission, cache, and MIME headers.
- Added WebUI configuration, transport, packaging, semantic-markup, unsafe-DOM,
  and browser-security regression coverage plus deployment documentation.
- Added runtime-packaging, routing, configuration-validation, CI, Compose,
  and graceful-shutdown regression coverage.
- Added an opt-in, migration-aware SQLite foundation for local users, hashed
  sessions and CSRF credentials, user-owned API tokens, destinations, routes,
  secrets, and future database-backed audit events.
- Added persistent login lockouts, session expiry/revocation, last-admin
  protection, owner/admin authorization policy, and atomic owner-only secret
  rotation with integrity checks.
- Added a trusted-host account-management CLI and platform-state deployment,
  backup, rollback, and security documentation.
- Added user-owned, source-scoped API-token creation, authentication, rotation,
  revocation, expiry, rate-limit metadata, and secret-free token responses.
- Added private/shared destination policy, strict separation of destination
  settings and owner-scoped secrets, and source/host/event/severity/status user
  route matching.
- Added injected-adapter delivery orchestration with bounded explicit retries,
  sanitized per-attempt history, safe terminal error codes, and database-backed
  audit events.
- Added transactional schema version 2 and tested upgrades from the existing
  schema version 1 database.
- Added disabled platform adapters and secret-free previews for Discord,
  Microsoft Teams, Slack, generic outbound webhooks, MQTT, and ntfy.
- Added bounded Slack Block Kit, a versioned generic JSON envelope, safe JSON
  templates, HMAC-SHA256 webhook signing, idempotency keys, MQTT QoS/TLS/topic
  controls, and ntfy priority/tag/action presentation.
- Added output-specific destination validation, administrator-controlled
  private-network delivery, ownership-safe preview/test delivery, retry-safe
  transport results, and adapter integration coverage.
- Added an opt-in `/api/v2` contract for local login/logout, strict session
  cookies, CSRF enforcement, account administration, password reset, and
  session/client rate limits.
- Added owner-scoped HTTP management for one-time API tokens, private/shared
  destinations, write-only secret rotation, user routes, previews, test
  delivery, safe history, and audit events.
- Added user/application event submission through source-scoped platform
  tokens or CSRF-protected sessions, using only the submitting owner's platform
  routes and the six Phase 3 output adapters.
- Added native HTTP `PATCH` and `DELETE` support, no-store/security response
  headers, strict request fields, non-partial update validation, and platform
  API integration coverage.

### Compatibility

- Data import is additive and never overwrites existing platform resource
  names or modifies the legacy YAML file. Credential-dependent safe-JSON
  imports remain disabled until a new write-only credential is supplied.
- State backups remain server-side under the private state mount. Restore
  revokes browser sessions and may return application-token records to the
  selected snapshot, so sensitive deployments should review token rotation.
- The WebUI is served only when `http.enabled`, `api.enabled`,
  `platform.enabled`, and `webui.enabled` are all explicitly true. Existing
  configurations omit the new switch and therefore retain current behavior.
- Platform state remains disabled by default. Existing v1.x YAML tokens,
  routes, destinations, inputs, outputs, and delivery behavior are unchanged.
- Platform tokens, routes, and delivery services are exposed only when the
  HTTP listener, API, and platform are all explicitly enabled.
- Platform event submission does not replace or import the existing YAML
  router. Existing SMTP/webhook inputs and Discord/Teams YAML delivery remain
  unchanged.

---

## 1.9.7 - 2026-07-21

### Fixed

- Official Docker images now embed an immutable icon base URL pinned to the
  exact release commit, preserving official Teams and Discord logos after a
  preview is promoted to a stable tag.
- Discord Components V2 delivery now uploads the packaged product thumbnail
  as a multipart attachment instead of applying attachment logic only to the
  legacy embed structure.
- Release validation now checks the effective Docker build argument and the
  actual Components V2 outbound attachment payload rather than merely counting
  PNG files inside the image.

### Compatibility

- Existing configuration, routes, webhook targets, secrets, parsers, card
  layouts, timestamps, and v1.9.6 presentation behavior are unchanged.
- No stack environment variable, configuration migration, or credential
  rotation is required.

---

## 1.9.6 - 2026-07-21

### Changed

- Replaced generated initial badges with official vendor assets across all 17
  Microsoft Teams integration presentations, including the generic Notifinho
  card.
- Normalized all locally served header assets to transparent 256 px PNGs and
  documented each official source and mechanical transformation.
- Added an optional `NOTIFINHO_ICON_BASE_URL` override for immutable branch
  previews and installations that mirror the same official assets.
- Preserved source casing for identifiers and acronyms such as `PVE-01`,
  `CPU`, and `VMID`.
- Shortened the UniFi Network last-device label and removed duplicated UniFi
  state, source-area, and icon presentation.
- Standardized all Discord integrations on the shared device/event, context,
  message, Severity/Category/Event time, rich-detail, and official-thumbnail
  hierarchy.
- Added centralized Discord field-count and embed-text budgeting that protects
  the event and three standard metrics before optional details are removed.
- Refined Discord cards with Teams-like spacing, an unlabelled dark event
  highlight, full-width rules in the correct hierarchy, separated vertical
  details, and a single-line footer.
- Packaged the official icon directory in the container and upload Discord
  thumbnails as webhook attachments, preventing integrations such as Grafana
  and Redfish from losing their logo when Discord cannot fetch a remote URL.
- Changed the shared Teams/Discord time policy so timezone-aware source values
  and epochs display in the Notifinho machine/container local time by default.
  Naive values remain source-local, missing source times remain omitted, and
  an optional IANA override is available for the future WebUI.
- Preserved native UniFi Network and Protect epochs until shared Teams and
  Discord presentation applies the configured timezone.

### Fixed

- Xen Orchestra cards now omit unavailable Duration and Result facts while
  retaining real values and the triggered backup name when supplied.
- Teams output and configuration validation now reject placeholder, malformed,
  credential-bearing, and non-HTTPS webhook values before attempting delivery.
- Home Assistant string tags no longer render character by character.
- Removed Discord's redundant Event field, synthetic blank rows, wrapped rule
  fragments, and duplicate footer separator while preserving exactly one rule
  before the highlight, one after the metrics, and one before the footer when
  details are present.
- Trusted Dell iDRAC `USR0030` and `USR0032` session audit records can be
  suppressed by exact client address across REDFISH/IPMI transports while
  failed logins and all other security events remain routed.
- Dell session events use concise titles such as `User Login` and normalize
  legacy contexts such as `NotifinhoAlfaCompat` to the device name `ALFA`.

### Compatibility

- Existing valid Teams and Discord webhooks, routes, source payloads,
  endpoints, and secrets remain compatible. Timezone-aware source instants now
  deliberately render in the local Notifinho machine clock.
- No configuration migration or secret rotation is required.

### Validation

- Expanded automated parser, API, formatter, routing, security, release, and
  backwards-compatibility coverage for local-machine time and trusted Dell
  session filtering.
- Added exact product-asset assertions for all 17 Teams presentations.
- Added cross-integration Discord hierarchy, exact-asset, source-time,
  recovery-state, rich-detail, and platform-limit regressions.
- Added transparent-PNG, asset-removal, Xen Orchestra optional-fact, identifier,
  UniFi duplication, and webhook-validation regressions.

---

## 1.9.4 - 2026-07-20

### Changed

- Standardized every Microsoft Teams formatter on one shared hierarchy:
  device and event header, integration/state/source context, event message,
  horizontal Severity/Category/Event time metrics, icon-labelled details,
  optional actions, and the Notifinho footer.
- Standardized Discord and Teams timestamps as `DD Mon YYYY • HH:MM` while
  preserving the wall-clock time emitted by the source machine.
- Removed visible UTC and numeric-offset suffixes and stopped timezone
  conversion in the shared and UniFi Protect presentation helpers.
- Documented the presentation contract for future integrations and the
  planned WebUI timezone policy.

### Compatibility

- Existing parsers, routes, output targets, webhooks, and product-image URLs
  remain compatible.
- If an event has no source timestamp, Teams displays `—` and Discord omits
  the optional time field; Notifinho does not invent a receipt timestamp.

### Validation

- Passed 530 automated parser, API, formatter, routing, security, release, and
  backwards-compatibility tests.
- Added cross-integration checks for the Teams hierarchy and source-wall-clock
  timestamp behavior, including offset-bearing ISO and epoch inputs.

---

## 1.9.3 - 2026-07-20

### Fixed

- Presented the Redfish subscription `Context` as Host in Supermicro, HPE iLO,
  and Dell iDRAC Discord and Microsoft Teams cards.
- Scoped Redfish duplicate suppression by host and origin so identical event
  identifiers from different systems do not collide.
- Stopped treating an empty Redfish `MessageArgs` array as a recommended
  action.

### Compatibility

- Existing Redfish endpoints, shared secrets, routes, output targets, and
  payloads remain compatible.
- Payloads without `Context` continue to work and simply omit the Host field.
- Rollback requires only restoring the previous v1.9.2 image tag.

### Validation

- Passed 512 automated parser, API, formatter, routing, security, release, and
  backwards-compatibility tests.
- Added regression coverage for multi-host Redfish context, per-host
  deduplication, Discord and Teams Host fields, and empty recommended actions.

---

## 1.9.2 - 2026-07-18

### Added

- Added optional Home Assistant endpoint and component aliases so site-local
  equipment names and addresses can remain in Notifinho configuration instead
  of being duplicated across automations.
- Added structured Home Assistant error-code fields to Discord and Microsoft
  Teams cards.

### Fixed

- Extracted bare IPv4 addresses from Home Assistant system-log messages into
  the dedicated Endpoint field.
- Added concise Tapo/Kasa and Internet Printing Protocol event summaries and
  service labels while hiding repeated internal method details.
- Stopped presenting a service or integration name as a Device when no real
  device or configured alias is known.

### Compatibility

- Existing configurations remain valid. The new `home_assistant.aliases`
  section is optional and no migration is required.
- Existing `notifinho.home_assistant.v1` payloads, endpoints, tokens, routes,
  SMTP behavior, and explicit automation fields remain compatible.
- Rollback to v1.9.1 requires only restoring the previous image tag; the
  optional alias section is ignored by that version.

### Validation

- Passed 511 automated parser, API, formatter, routing, security, and
  backwards-compatibility tests.
- Passed 58 focused Home Assistant, API HTTP, and presentation-contract tests.
- Validated live Tapo/Kasa and IPP development cards with concise Event text
  and separate Service, Device, Endpoint, and Error fields.
- Confirmed successful Discord delivery, equivalent Microsoft Teams regression
  coverage, and clean development-container startup.

---

## 1.9.1 - 2026-07-18

### Fixed

- Replaced the Xen Orchestra fallback used for unknown and authenticated API
  event sources with dedicated generic Discord and Microsoft Teams
  presentation, while retaining explicit Xen Orchestra formatting for `xo`.
- Made Home Assistant cards concise and service-aware by deriving the
  responsible integration, device, entity, endpoint, and retry information
  from raw system-log events.
- Removed Python source paths and verbose internal service-object text from
  Home Assistant cards and bounded the remaining event summary.

### Changed

- Simplified the documented Home Assistant automation to a generic transport
  contract so reusable presentation remains inside Notifinho and
  deployment-specific exclusions remain in Home Assistant.

### Compatibility

- Preserves the v1.9.0 configuration schema, API tokens, routes, endpoints,
  SMTP behavior, and existing source-specific formatter selection.
- Existing Home Assistant `notifinho.home_assistant.v1` payloads remain
  compatible; explicit fields from purpose-built automations still take
  precedence over derived values.

### Validation

- Passed 506 automated parser, API, formatter, routing, security, and
  backwards-compatibility tests.
- Validated generic API, Chromecast, MQTT, and Calendar event presentation in
  the dedicated VM-09 development environment with successful Discord
  delivery and no formatter or delivery errors.
- Covered equivalent generic and Home Assistant Microsoft Teams presentation
  through the regression suite.

---

## 1.9.0 - 2026-07-15

### Added

- Shared Redfish Event Service ingestion with bounded batches, normalized
  server-hardware events, safe origin paths, and configurable duplicate
  suppression.
- Fixture-validated Supermicro BMC/IPMI, HPE iLO, and Dell iDRAC Redfish and
  delivered-email adapters with dedicated Discord and Teams presentation.
- Authenticated Home Assistant automation events using the versioned
  `notifinho.home_assistant.v1` contract.
- Generic `notifinho.event.v1` submission through `/api/events` with explicit
  per-token source scopes.
- Disabled-by-default health, masked configuration, validation, logs, preview,
  test-send, and atomic configuration-update API foundations.
- Environment-, owner-only file-, and SHA-256-backed tokens; per-token and
  per-client rate limits; PBKDF2 password helpers; private audit logs; and
  owner-only configuration backups.
- Product badges, synthetic Redfish/SMTP/Home Assistant fixtures, routing
  examples, integration guides, and release validation tooling.

### Security

- Rejects inline plaintext API tokens in YAML configuration.
- Preserves existing secret values when a masked configuration is safely
  round-tripped through the API.
- Bounds event batches, payload fields, metadata, tags, links, and log reads.
- Avoids raw request logging and suppresses credentials, event fingerprints,
  full management URLs, and secret query values from cards and audit records.

### Compatibility

- Existing v1.8.1 SMTP, HTTP endpoints, YAML routes, Discord targets, Teams
  targets, and formatter behavior remain covered by the full regression suite.
- The backend API, Redfish adapters, and Home Assistant endpoint remain
  disabled until explicitly configured.
- Supermicro, HPE, and Dell support is a fixture-validated candidate pending
  representative real-system delivery tests.
- Browser sessions, CSRF protection, local account management, user-owned
  destinations, user routing, and the responsive WebUI remain v2.0 scope.

### Validation

- Passed 499 automated parser, HTTP, authentication, config-safety, formatter,
  routing, and backwards-compatibility tests.
- Started an isolated v1.9.0 release-candidate container and verified its SMTP
  and HTTP listeners without replacing development or production containers.
- Verified missing-token rejection, authenticated Redfish vendor and Home
  Assistant inputs, generic event submission, configuration masking and
  round-trip validation, private backups, and audit-file permissions.
- Accepted the hardware, Proxmox, and Synology SMTP fixture matrix and
  delivered the new Redfish, hardware-vendor, and Home Assistant cards to the
  development Discord destination before tagging.

---

## 1.8.1 - 2026-07-15

### Added

- Self-hosted product badges for Zabbix, QNAP, Grafana, TrueNAS, UniFi,
  Portainer, Proxmox VE, and Synology DSM cards.
- A shared Discord and Microsoft Teams presentation contract with product
  branding, canonical timestamps, field limits, and credential sanitization.
- Cross-source regression coverage for all dedicated formatter pairs and the
  Xen Orchestra default formatters.

### Changed

- Standardized visible dates as `DD Mon YYYY • HH:MM`, retaining an explicit
  UTC or numeric offset when the source timestamp includes one.
- Added compact top-right product badges to Microsoft Teams Adaptive Cards and
  Discord embeds while retaining the established source and status icons.
- Improved TrueNAS list extraction so wrapped alert details remain readable
  and duplicate New/Current copies of the same active condition collapse into
  one card item.
- Added clearer TrueNAS field icons and normalized UniFi Protect event times.

### Security

- Added a final recursive credential scrub to every Discord and Microsoft
  Teams payload before delivery.
- Redacts token, API key, password, secret, session ID, authorization bearer,
  Discord webhook, and sensitive query-string values while retaining useful
  operational context.

### Validation

- Passed 458 automated tests, including shared presentation, formatter,
  routing, parser, payload-budget, and secret-redaction regression coverage.
- Preserved existing YAML, routing keys, webhook endpoints, SMTP behavior, and
  destination target configuration.
- Recorded real Synology DSM JSON webhook and SMTP/STARTTLS delivery to Teams,
  real Portainer firing/resolved delivery, and a real TrueNAS grouped-alert
  delivery as compatibility evidence.

---

## 1.8.0 - 2026-07-15

### Added

- Fixture-validated Synology DSM SMTP parsing for system, storage, disk/SMART,
  backup, replication, UPS/power, package, security, network, and availability
  notifications.
- A versioned Synology contract at `POST /synology/events` accepting bounded
  JSON and form-encoded custom-provider fields with header or query-token
  authentication.
- Dedicated Synology DSM Discord embeds, Microsoft Teams Adaptive Cards,
  routing examples, synthetic email/JSON fixtures, and integration guidance.
- Fixture-validated Proxmox VE SMTP parsing for backup, replication, node,
  cluster, storage, availability, security, guest, and system notifications.
- A versioned Proxmox webhook contract at `POST /proxmox/events`, protected by
  the existing `X-Notifinho-Token` HTTP authentication boundary.
- Dedicated Proxmox VE Discord embeds, Microsoft Teams Adaptive Cards,
  routing examples, synthetic email/JSON fixtures, and integration guidance.
- Native Portainer BE Alerting ingestion at `POST /portainer/alerts`, including
  grouped firing/resolved events and URL query-token authentication for
  Portainer's URL-only webhook channel.
- Portainer-specific normalization and dedicated Discord embeds and Microsoft
  Teams Adaptive Cards based on a private-safe BE 2.42.0 firing-event
  validation.
- Synthetic Alertmanager-compatible Portainer fixtures and production HTTP,
  parser, presentation, routing, privacy, and authentication coverage.
- Private-safe Portainer Alerting webhook capture and offline webhook/email
  analysis tools for the v1.8.0 discovery phase.
- Shared discovery sanitization helpers with regression coverage for private
  identifiers, credentials, URLs, and infrastructure metadata.
- A Portainer BE 2.42.0 discovery runbook for development-only validation on
  VM-04 without API polling or permanent Portainer credentials.

### Changed

- Replanned v1.8.0 as the Proxmox VE, Portainer, and Synology DSM integration
  release.
- Replanned v1.9.0 as the Redfish hardware-management, Home Assistant, secure
  event API, and configuration API foundation release.
- Expanded the v2.0.0 scope into a user-facing notification platform with
  administrator and user roles, scoped event submission, user-owned routing,
  and private or shared destinations.
- Planned Slack, generic outbound webhook, MQTT, and ntfy outputs for v2.0.0.
- Updated the README source and destination matrices, architecture, production
  Docker Compose and Portainer example, Nginx Proxy Manager guidance, example
  configuration, routing model, and roadmap through v2.0.0.
- Replaced raw Proxmox backup email bodies in output cards with a concise
  result summary and structured successful/failed guest details.

### Validation

- Passed the final v1.8.0 release suite with 430 automated tests.
- Passed the full automated suite with 426 tests, including synthetic Synology
  SMTP, JSON/form webhook, authentication, recovery, routing, and formatter
  coverage.
- Marked real Synology DSM email and custom-webhook delivery as pending; the
  initial integration remains a fixture-validated candidate.
- Passed the full automated suite with 408 tests, including synthetic Proxmox
  SMTP and webhook transport, parser, authentication, routing, and formatter
  coverage.
- Marked real Proxmox VE SMTP and webhook delivery as pending; the initial
  implementation is intentionally not described as production-validated.
- Validated Portainer Business Edition 2.42.0 firing and resolved Alertmanager
  delivery through the authenticated native endpoint to development Discord.
- Confirmed missing Portainer query tokens return `401`, valid tokens return
  `204`, and the Portainer container network can reach the private development
  listener.
- Marked QNAP QTS / QuTS hero support as validated following successful real
  QNAP Notification Center delivery.
- Kept anonymized synthetic QNAP fixtures and broader template coverage as
  ongoing compatibility-hardening work.

---

## 1.7.0 - 2026-07-14

### Added

- Native authenticated `POST /unifi/drive` Alarm Manager webhook input.
- Shared `X-Notifinho-Token` authentication for Network, Protect, and Drive.
- Dedicated Drive JSON parsing while preserving Drive email parsing through SMTP.
- Drive `Alarm rule` fields for Discord and Microsoft Teams.
- Release, deployment, alarm-naming, and rollback documentation.

### Changed

- Drive webhook titles now derive a readable event label from descriptive alarm names.
- The complete configured Drive alarm name remains visible as `Alarm rule`.
- Raw `Alarm "..." was triggered` text is replaced by a concise description.
- Proxmox VE moves to v1.8.0, the Configuration API to v1.9.0, and the
  Community WebUI to v2.0.0.

### Compatibility

- Existing Network and Protect endpoints are unchanged.
- Existing Drive delivered-email parsing remains supported.
- Existing SMTP and SMTP security configurations remain compatible.
- The HTTP listener remains disabled by default.
- Drive uses the existing global `http.shared_secret`.
- Drive payloads do not identify the condition inside a multi-trigger alarm;
  descriptive, single-event Drive alarm rules are recommended.

### Validation

- 357 automated tests passed.
- 44 focused UniFi Drive tests passed.
- Real Drive delivery succeeded over HTTPS and routed to Discord.
- Alarm IDs remain hidden from visible cards.
- No private payload, token, webhook URL, or production configuration was included.

---

## 1.6.0 - 2026-07-13

### Added

- Optional explicit STARTTLS support for the SMTP listener.
- SMTP AUTH LOGIN and PLAIN support after a TLS session is established.
- Password loading from an environment variable or Docker-compatible secret
  file.
- A dedicated SMTP security configuration and validation layer.
- Deployment guidance for Docker Compose, Portainer, certificates, secrets,
  rollout, and rollback.

### Security

- Enforced TLS 1.2 or newer.
- Prevented AUTH advertisement and use before STARTTLS.
- Used timing-safe comparisons for usernames and passwords.
- Added fail-closed validation for missing certificates, private keys,
  usernames, environment variables, and secret files.
- Prevented inline plaintext password configuration.
- Prevented password, AUTH payload, and secret-file content logging.
- Made STARTTLS required by default whenever TLS is enabled.
- Made authentication required by default whenever AUTH is enabled.
- Disabled the built-in LOGIN and PLAIN mechanisms in TLS-only mode.
- Avoided retaining submitted credential data after successful authentication.

### Compatibility

- SMTP security remains disabled by default.
- Existing configurations containing only `smtp.host` and `smtp.port` remain
  compatible.
- The SMTP container port remains `8025`.
- The HTTP listener, parsers, routing, formatters, and outputs are unchanged.
- Explicit optional STARTTLS or optional authentication modes remain available
  for controlled migration.

### Validation

- 348 automated tests passed.
- 51 focused SMTP security tests passed.
- Python syntax validation passed.
- Docker release-candidate validation passed.
- Real sender-device compatibility remains dependent on each appliance's
  STARTTLS, AUTH, certificate-trust, and hostname-validation capabilities.

---

## 1.5.2 - 2026-07-13

### Fixed

- Humanized UniFi Protect trigger identifiers such as `admin_access` to
  `Admin Access`.
- Changed Protect notification titles to use the actual trigger event instead
  of the configured Alarm Manager rule name.
- Preserved the configured Protect rule name in a dedicated `Alarm rule` field.
- Removed incomplete and redundant Protect condition text such as
  `admin_access is`.
- Normalized known Protect device labels such as `nvr` to `NVR`.
- Applied the presentation correction consistently to Discord and Microsoft
  Teams notifications.

### Validation

- 297 automated tests passed.
- 72 focused UniFi parser, formatter, and presentation tests passed.
- Python syntax validation passed.
- Existing privacy filtering for MAC addresses, UUIDs, and opaque device
  identifiers remained enabled.
- Real UniFi Protect delivery will be verified after publication.

---

## 1.5.1 - 2026-07-13

### Changed

- Polished QNAP Microsoft Teams Adaptive Cards with a NAS identity icon,
  status-aware severity icons, category-specific icons, event-specific
  headings, and icon-prefixed operational details.
- Humanized QNAP event-type values such as `test_message` to `Test Message`.
- Removed redundant test-message metadata from visible Teams cards while
  preserving useful parsed operational information.
- Updated the QNAP integration documentation for real-device validation.

### Validation

- 295 automated tests passed.
- 20 focused QNAP formatter tests passed.
- Python syntax validation passed for the changed formatter and regression test.
- Real QNAP Notification Center delivery will be verified immediately after
  publication using the production SMTP listener.

---

## 1.5.0 - 2026-07-13

### Added

- Native, disabled-by-default HTTP input for UniFi Network and Protect Alarm
  Manager webhooks, with bounded JSON bodies, optional shared-secret
  authentication, and graceful lifecycle integration alongside SMTP.
- Strong-envelope Network and Protect parsers using the shared `Notification`
  model, dispatcher, router, and existing delivery pipeline.
- Provisional UniFi Drive email detection and parsing with plain-text
  preference and sanitized HTML fallback.
- Dedicated Discord embeds and Microsoft Teams Adaptive Cards for UniFi
  Network, Protect, and Drive.
- Independent `unifi_network`, `unifi_protect`, and `unifi_drive` routing keys
  with a practical shared `unifi` output target example.
- Private-safe loopback webhook replay tooling and synthetic Network, Protect,
  Drive, HTTP, formatting, routing, and regression coverage.
- Discovery-only tooling for sanitized structural analysis of private UniFi
  RFC822 email samples.
- A temporary, standard-library HTTP capture server with sanitized summaries
  and explicitly opt-in private raw-request storage.
- A private-sample collection and review workflow for UniFi Network, Protect,
  and Drive.
- Synthetic regression coverage for discovery sanitization and application
  marker classification.

### Notes

- v1.5.0 is the current stable release.
- Network and Protect accept direct HTTP webhooks. Drive supports parsing
  delivered RFC822 email but does not poll IMAP, Microsoft Graph, Gmail, or any
  mailbox provider.

---

## 1.4.0 - 2026-07-12

### Added

- Provisional TrueNAS 26 alert-service email detection and parsing.
- Plain-text, HTML, multipart, test, new, cleared, current, and grouped alert
  handling using the shared `Notification` model.
- TrueNAS classification for storage, disk/SMART, scrub, replication, backup,
  UPS/power, system, network, security, and application/service events.
- TrueNAS-specific Discord embeds and Microsoft Teams Adaptive Cards with
  bounded grouped-alert payloads.
- Nine anonymized synthetic `.eml` fixtures and offline regression coverage.
- Dedicated TrueNAS Discord/Teams targets, routing examples, and integration
  documentation.

### Validation

- 169 automated tests passed.
- 54 Python files passed cache-free syntax validation.
- All nine synthetic TrueNAS fixtures were replayed successfully through SMTP.
- Private TrueNAS 26 test-email and test-alert samples were replayed on VM-04.
- A fresh TrueNAS 26 Send Test Alert was detected, parsed, routed, formatted,
  and delivered successfully.
- The Docker release-candidate image passed startup, SMTP, parsing, routing,
  formatting, and delivery smoke tests.

### Notes

- TrueNAS support remains provisional for broader real-world alert variants,
  localized wording, customized templates, and Enterprise HA layouts.

---

## 1.3.0 - 2026-07-12

### Added

- Initial QNAP QTS and QuTS hero email detection and parser.
- QNAP event classification for storage, security, backup, system, power,
  and generic notifications.
- QNAP-specific Discord embed and Microsoft Teams Adaptive Card formatters.
- Seven synthetic QNAP `.eml` fixtures covering Notification Center tests,
  login security, storage/RAID, disk/SMART, HBS backup, updates, and UPS power
  events.
- Local SMTP fixture replay utility with development defaults for port `8026`.
- QNAP routing examples and integration documentation.
- Dedicated QNAP source routing for Discord and Microsoft Teams targets.
- Pytest coverage for QNAP detection, parsing, formatting, and existing-source
  selection regressions.
- Initial Grafana Alerting email detection and parser.
- Grafana event handling for test, firing, resolved, pending, No Data,
  datasource/evaluation error, and grouped alert notifications.
- Grafana-specific Discord embed and Microsoft Teams Adaptive Card formatters.
- Seven synthetic Grafana `.eml` fixtures covering plain-text, HTML, and
  multipart alert layouts.
- Dedicated Grafana Discord/Teams target and routing examples.
- Grafana parser, formatter, output-selection, payload-budget, and source
  precedence regression tests.
- Grafana integration and synthetic fixture replay documentation.
- Source-detection regression protection for multipart bodies, competing
  vendor messages, attachment-only markers, and existing integrations.
- Aggregate Discord embed-budget enforcement while preserving essential event
  fields.
- Updated source-aware architecture documentation covering dispatch, parsing,
  the shared model, routing, formatter selection, and webhook delivery.
- Automated GitHub Release creation for stable `vMAJOR.MINOR.PATCH` tags.
- Release validation that the tag, checked-out commit, and `src/version.py`
  contain the same stable version.
- Rerun-safe updates of existing GitHub Releases and manual publication of
  existing stable tags.

### Validation

- 123 automated tests passed.
- 49 Python files passed cache-free syntax validation.
- The GitHub Actions release workflow passed `actionlint` and invariant checks.
- Representative QNAP and Grafana fixture replays confirmed source detection,
  parsing, dedicated Discord routing, and successful delivery.
- The production image passed version, startup, and SMTP listener smoke tests.

### Notes

- QNAP support is provisional. Synthetic fixtures do not guarantee
  compatibility with every QTS or QuTS hero version; anonymized real email
  samples are still needed for verification.
- Grafana support is provisional. Synthetic fixtures do not guarantee
  compatibility with every Grafana version or custom alert template;
  anonymized real email samples are still needed for verification.

---

## 1.2.0 - 2026-07-10

### Added

- Zabbix email detection and parser.
- Zabbix problem notifications.
- Zabbix recovery notifications.
- Zabbix-specific Discord embed formatter.
- Zabbix-specific Microsoft Teams Adaptive Card formatter.
- Severity-aware Zabbix notification icons and colors.
- Optional Zabbix problem ID display.
- Conditional host-based output routing.
- Support for sending selected Zabbix hosts to secondary webhook targets.
- Configuration examples for Zabbix routing.
- Configuration examples for filtered secondary destinations.

### Improved

- Microsoft Teams Zabbix card layout.
- Zabbix problem and recovery date formatting.
- Source-specific formatter selection for Discord and Microsoft Teams.
- Case-insensitive email sender detection.
- Router logging for matched and skipped conditional destinations.
- Configuration documentation for multiple output targets.

---

## 1.1.1

### Fixed

- Fixed Discord footer version to use the application version dynamically instead of a hardcoded value.

---

## 1.1.0

### Added

- Microsoft Teams output support.
- Microsoft Teams Adaptive Card formatter.
- Multiple-output routing support.
- Ability to send the same notification to Discord and Microsoft Teams.
- Formatter abstraction for future notification platforms.

### Improved

- Teams backup notification layout.
- Teams date formatting using Portuguese-friendly `DD/MM/YY HH:mm` format.
- Development environment and startup banner.
- Configuration example for multi-output routing.

---

## 1.0.1

Initial public release.

---

## 1.0.0

### Added

- SMTP Gateway.
- Xen Orchestra parser.
- Discord formatter.
- Docker support.
- Routing.
- VM details.
- Repository information.
- Transfer speed.
- Rich embeds.
