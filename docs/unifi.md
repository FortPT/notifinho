# UniFi integration

Notifinho `1.5.0-dev` provides three independent normalized sources:

- `unifi_network` receives UniFi Network Alarm Manager JSON webhooks;
- `unifi_protect` receives UniFi Protect Alarm Manager JSON webhooks; and
- `unifi_drive` parses UniFi Drive notification email delivered through the
  existing SMTP input.

All three sources use the shared `Notification` model, router, Discord output,
and Microsoft Teams output. The v1.4.0 release remains the current stable
release while this integration is under development in issue #32.

## Native HTTP input

The production HTTP input uses Python's standard library and runs alongside
SMTP. It remains disabled unless explicitly enabled:

```yaml
smtp:
  host: "0.0.0.0"
  port: 8025

http:
  enabled: true
  host: "0.0.0.0"
  port: 8080
  max_body_bytes: 1048576
  shared_secret: "REPLACE_WITH_A_RANDOM_SECRET"
```

Supported endpoints are:

```text
POST /unifi/network
POST /unifi/protect
```

Successful parse and dispatch returns HTTP 204. Invalid JSON or an invalid
source envelope returns 400, unknown paths return 404, unsupported methods
return 405, and oversized bodies return 413. JSON media types include
`application/json` and `application/*+json`.

When `shared_secret` is non-empty, every request must include:

```text
X-Notifinho-Token: <secret>
```

Notifinho compares this value using a timing-safe comparison. Some UniFi or
reverse-proxy configurations may not support custom headers directly. In that
case, keep the listener on a strictly trusted network or configure a private
TLS-terminating reverse proxy that injects the header after authenticating the
request.

Do not expose the listener directly to the public internet. Restrict the
published port to the UniFi controller or reverse proxy using host and network
firewall rules. Use TLS termination and the shared secret wherever supported.
The listener never logs full webhook payloads or sensitive webhook identifiers
at INFO level.

## Container ports

SMTP continues to use container port `8025`. HTTP uses a separate container
port, `8080`:

```yaml
ports:
  - "8025:8025"
  - "18080:8080"
```

The development Compose example uses host port `18081` for HTTP so it can run
beside another local capture listener. Publishing the port does not enable the
input; `http.enabled` must also be true.

## UniFi Network

Configure Alarm Manager to POST JSON to `/unifi/network`. Detection requires
the Network application identity, expected envelope fields, an object-valued
`parameters` member, and UniFi-specific event evidence. Arbitrary JSON that
merely contains the word "network" is rejected.

Network notifications normalize the event name, category, vendor severity,
controller, client, network/Wi-Fi context, last connected device, duration,
RSSI, event time, and private identifiers retained only as metadata. Numeric
vendor severity is preserved. A routine client disconnect is informational
unless stronger failure evidence is present. Cards omit client and device MAC
addresses by default.

## UniFi Protect

Configure Alarm Manager to POST JSON to `/unifi/protect`. Protect detection
requires the discovered nested alarm shape. The notification uses the actual
trigger device and does not list every configured source device.

Protect motion, person, vehicle, and doorbell alarms may be very high-volume.
Use narrow Alarm Manager device and event scope. Do not broadly enable all
detection events during initial deployment. Event links are included only when
they are valid HTTP or HTTPS URLs.

## UniFi Drive email

Drive detection requires the `notifications.ui.com` sender domain plus UniFi
Drive identity and known Drive event vocabulary. Plain text is preferred. When
only HTML exists, style, scripts, tracking images, branding images, footers,
postal-address text, and copyright text are excluded from operational content.

Provisional classification covers failed, partial, paused, completed, storage,
disk, encryption, and administrative events. Unknown strongly identified Drive
events still produce a generic useful notification.

Notifinho does **not** poll IMAP, Microsoft Graph, Gmail, or any mailbox and
stores no mailbox credentials. Live Drive notifications require an external
mail-forwarding rule, SMTP relay, or another delivery mechanism that sends the
RFC822 message to Notifinho's existing SMTP input.

## Routing and targets

Network, Protect, and Drive can share one Discord destination:

```yaml
outputs:
  discord:
    enabled: true
    unifi:
      webhook: "PASTE_UNIFI_DISCORD_WEBHOOK_HERE"

routing:
  unifi_network:
    outputs:
      - output: discord
        target: unifi

  unifi_protect:
    outputs:
      - output: discord
        target: unifi

  unifi_drive:
    outputs:
      - output: discord
        target: unifi
```

Equivalent Teams targets use `outputs.teams.<target>.webhook`. Separate targets
may be configured when high-volume Protect traffic should not share the
Network or Drive destination. Dedicated output configuration always uses
`webhook`, never `webhook_url`.

## Local replay

For private captures and safe replay commands, see
[the discovery guide](unifi-discovery.md). The HTTP replay utility sends only
the JSON body and media type to a loopback endpoint and never forwards captured
authentication, cookie, Host, or token headers.
