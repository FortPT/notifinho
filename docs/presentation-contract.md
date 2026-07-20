# Notification presentation contract

Notifinho uses a shared presentation contract so new integrations behave like
the existing Discord embeds and Microsoft Teams Adaptive Cards.

## Event time

The event source owns the visible timestamp.

- Use the timestamp emitted by the source machine or service.
- Preserve its date and wall-clock hour. Do not convert an ISO timestamp to
  the Notifinho container timezone, UTC, or the output recipient's timezone.
- Do not append `UTC` or a numeric timezone suffix to the card.
- Render recognized timestamps as `20 Jul 2026 • 18:09`.
- If the source sends an epoch value, interpret it as the UTC instant encoded
  by that value, but still omit the `UTC` label.
- If no source timestamp is available, show `—` in the Teams event-time metric
  or omit the optional Discord time field. Never substitute Notifinho's
  receipt time.

Timezone conversion is intentionally deferred until a future WebUI can offer
an explicit global or per-device policy. The current behavior is deterministic
for containers deployed in any host timezone.

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

## Status semantics

The shared renderer maps normalized states to accessible icon and color pairs:

| State family | Icon | Teams color |
|---|---:|---|
| Critical, disaster, failure | 🚨 | Attention |
| Warning, degraded, average | ⚠️ | Warning |
| Resolved, recovered, success | ✅ | Good |
| Information or unknown | ℹ️ | Accent |

The icon remains part of the text so status is not communicated by color
alone.

## Integration images

Card images must be publicly reachable over HTTPS, render without
authentication or redirects, and use a Teams-supported raster format. The
current self-hosted PNG badges satisfy that delivery contract and avoid a
runtime dependency on vendor CDNs. Product names and marks are used only to
identify the event source.

If an image is replaced with an official vendor asset, keep it unmodified,
verify the vendor's current brand/trademark terms, commit a raster PNG to
`assets/icons/`, and retain a compact transparent or square-safe variant for
the 48 px Teams header slot.
