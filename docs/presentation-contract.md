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

Every integration supplies normalized data to the shared Discord Components
V2 renderer:

1. Header: `device • event`, device/status icons, severity-aware accent color,
   and the official integration thumbnail.
2. Context: `integration • state • source area`.
3. A native responsive separator followed by the highlighted event message.
4. One compact text row containing Severity, Category, and Event time.
5. A native responsive separator followed by optional integration details.
6. A final native separator and the one-line Notifinho version footer.

Discord controls separator width at render time, so rules remain aligned on
desktop and mobile without fixed underscore or dash strings. The renderer does
not add a redundant Event label or synthetic spacer fields. Source-specific
details remain richer than the compact Teams card and are ordered vertically
for phone readability.

The normalized model and Components V2 renderer live in
`src/formatters/discord_common.py`; delivery and packaged icon attachments live
in `src/outputs/discord.py`. New formatters create `DiscordCardData` and
`DiscordFact` values rather than constructing destination JSON independently.
The renderer enforces Discord's component and text budgets, removing the
lowest-priority optional facts first while retaining title, context, event,
metrics, and footer.

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

Card images use a Teams- and Discord-supported raster format. Notifinho stores
normalized 256 px transparent PNGs in `assets/icons/` and includes that
directory in the production image. Discord uploads the matching packaged PNG
with each webhook request and references it through an `attachment://` URL;
this prevents a card from silently losing its thumbnail when an external image
host is unavailable. Teams continues to use the public HTTPS asset URL because
Adaptive Cards do not support Discord-style webhook attachments.

Production uses the repository's `main/assets/icons` URL. Preview builds and
installations that mirror the official assets can set
`NOTIFINHO_ICON_BASE_URL` to another public HTTPS directory; the filenames and
asset contract remain unchanged.

Product-specific images must originate from an official vendor page or source
repository. Record the source and any mechanical transformation in
`assets/icons/README.md`. Do not introduce generated initials or lookalike
artwork as a product logo. Product names and marks are used only to identify
the event source.
