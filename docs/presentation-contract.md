# Notification presentation contract

Notifinho uses a shared presentation contract so new integrations behave like
the existing Discord embeds and Microsoft Teams Adaptive Cards.

## Event time

The event source owns the visible timestamp.

- Use the timestamp emitted by the source machine or service.
- Convert timezone-aware source timestamps and epoch instants to the
  Notifinho machine/container local timezone before display.
- Treat a source timestamp without timezone information as an already-local
  wall clock. Do not reinterpret it as UTC.
- Do not append `UTC` or a numeric timezone suffix to the card.
- Render recognized timestamps as `20 Jul 2026 • 18:09`.
- If no source timestamp is available, omit the Event time metric. Never
  substitute Notifinho's receipt time.

The default is the machine/container local clock. An optional IANA-zone
override is reserved for installations—and the future WebUI—that intentionally
need a different display timezone:

```yaml
presentation:
  timezone: Europe/Lisbon
```

If this setting is absent, Notifinho discovers the container's local timezone.
The packaged `tzdata` database and local-zone discovery support worldwide
deployments. The selected timezone affects presentation only; it never replaces
the source event timestamp with Notifinho's receipt time.

## Microsoft Teams hierarchy

Every integration supplies normalized data to the shared Teams renderer:

1. Header: `device • event`, with a device icon, status icon, severity-aware
   title color, and the integration image at the top right.
2. Context: `integration • state • source area`.
3. Message: one emphasized event body with an event icon.
4. Metrics: exactly three horizontal values—Severity, Category, and Event
   time.
5. Details: optional, icon-labelled integration-specific facts.
6. Optional integration-specific sections and actions.
7. Notifinho version footer.

The normalized card model lives in `src/formatters/teams_common.py`. New Teams
formatters should inherit `TeamsCardFormatter`, create a `TeamsCardData`
instance, and keep vendor parsing outside the renderer.

## Discord hierarchy

Every integration supplies the same normalized concepts to the shared Discord
renderer while retaining more source-specific detail than the compact Teams
layout:

1. Header: `device • event`, with device and status icons, a severity-aware
   embed color, and the official integration thumbnail.
2. Context: `integration • state • source area`.
3. Message: one full-width highlighted event body without a redundant label.
4. Metrics: Severity, Category, and Event time as the first three inline
   fields.
5. Details: optional icon-labelled integration-specific fields, links, and
   bounded multi-item sections.
6. Notifinho version footer.

The shared renderer separates the context line from the title, presents the
unlabelled event message in a dark full-width highlight, places a full-width
rule directly below it, keeps Severity, Category, and Event time on one row,
then places source-specific facts in a vertical list. A final full-width rule
immediately follows the last detail and separates the one-line footer. There
is no rule after the footer because Discord has no card content below it.

The normalized Discord model lives in `src/formatters/discord_common.py`. New
Discord formatters should inherit `DiscordCardFormatter`, create a
`DiscordCardData` instance, and keep source parsing outside the renderer. The
renderer enforces Discord's 25-field and 6,000-character embed limits by
dropping the lowest-priority optional details first; the event message and the
three standard metrics are always retained.

Optional facts whose source value is missing or represented by `-`, `—`,
`N/A`, `None`, or `null` are omitted. Identifiers and acronyms such as
`PVE-01`, `VMID`, and `CPU` retain their source casing.

## Status semantics

The shared renderer maps normalized states to accessible icon and color pairs:

| State family | Icon | Teams color | Discord color |
|---|---:|---|---|
| Critical, disaster, failure | 🚨 | Attention | Red |
| Warning, degraded, average | ⚠️ | Warning | Orange |
| Resolved, recovered, success | ✅ | Good | Green |
| Information or unknown | ℹ️ | Accent | Blue |

The icon remains part of the text so status is not communicated by color
alone.

## Integration images

Card images must be publicly reachable over HTTPS, render without
authentication or redirects, and use a Teams- and Discord-supported raster format.
Notifinho stores normalized 256 px transparent PNGs in `assets/icons/` and
serves them with the project documentation, avoiding a runtime dependency on
vendor CDNs.

Production uses the repository's `main/assets/icons` URL. Preview builds and
installations that mirror the official assets can set
`NOTIFINHO_ICON_BASE_URL` to another public HTTPS directory; the filenames and
asset contract remain unchanged.

Product-specific images must originate from an official vendor page or source
repository. Record the source and any mechanical transformation in
`assets/icons/README.md`. Do not introduce generated initials or lookalike
artwork as a product logo. Product names and marks are used only to identify
the event source.
