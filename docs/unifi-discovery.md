# UniFi discovery for v1.5.0

The initial v1.5.0 discovery phase is complete. The tools in this guide remain
available for safely inspecting future variants without committing private
samples. Production configuration and security guidance now lives in the
[UniFi integration guide](unifi.md).

## Application boundaries

"UniFi" covers separate applications whose notification formats and event
models must not be assumed to match:

- **UniFi Network** manages gateways, switches, access points, clients, and
  network connectivity. Useful early samples include test notifications,
  device health, adoption, upgrades, and connectivity changes.
- **UniFi Protect** manages cameras, doorbells, detections, recording, and
  Protect storage. Useful early samples include test, camera health,
  connectivity, recording, and storage notifications.
- **UniFi Drive** manages file storage, disks, storage pools, and backups.
  Useful early samples include test, storage health, disk health, backup, and
  connectivity notifications.

Classification produced by the discovery scripts is a heuristic marker, not a
source-detection contract.

The production listener is implemented separately in `src/inputs/http.py` and
does not invoke either discovery utility.

## Private sample layout

Keep original captures only in these local directories:

```text
private-samples/unifi/network/
private-samples/unifi/protect/
private-samples/unifi/drive/
```

`private-samples/unifi/` must be present in the checkout's
`.git/info/exclude`. Original emails, HTTP requests, screenshots, and copied
payloads must never be committed. Before every commit, check `git status` and
scan the staged diff for webhook URLs and private identifiers.

Do not collect normal motion, person, or vehicle detections broadly during
discovery. They can be high-volume and may contain especially sensitive
context. Prefer storage, backup, connectivity, device-health, and explicit
test notifications as initial samples.

## SMTP discovery

Point one development-only UniFi notification destination at VM-04's
development SMTP service on port `8026`. Do not change the production SMTP
destination. Use a narrow test notification or a low-volume health event, then
store the resulting original `.eml` under the matching private directory.

Codex does not receive access to these originals. A human reviewer runs the
local analyzer and shares only its sanitized output after inspection.

From the repository root, print a sanitized structural summary without
writing another file:

```bash
python scripts/analyze_unifi_email.py private-samples/unifi/network/sample.eml
```

Write the same sanitized JSON only when an explicit review path is wanted:

```bash
python scripts/analyze_unifi_email.py private-samples/unifi/network/sample.eml --output private-samples/unifi/network/sample.sanitized.json
```

The analyzer never modifies the input. It reports the sanitized subject shape,
sender domain, header names, MIME structure, text alternatives, private-safe
attachment metadata, parser defects, and likely UniFi application markers.

## Temporary HTTP discovery

The capture server uses Python's standard library and defaults to loopback on
the non-production port `18080`. Raw request saving is disabled by default:

```bash
python scripts/capture_unifi_webhook.py --host 127.0.0.1 --port 18080
```

Allow GET only if an application needs it for discovery:

```bash
python scripts/capture_unifi_webhook.py --host 127.0.0.1 --port 18080 --allow-get
```

To retain originals, explicitly select an already-private location:

```bash
python scripts/capture_unifi_webhook.py --host 127.0.0.1 --port 18080 --output-dir private-samples/unifi/protect/http
```

Use firewall rules and development-only application settings appropriate to
the lab when a remote device must reach this listener. Do not reuse a
production port or expose it broadly. Stop the server with Ctrl+C; SIGTERM is
also handled gracefully.

For each request, the console shows only a sanitized deterministic summary:
method, redacted path shape, media type, safe header names, body size, JSON
shape, top-level keys, parse status, and likely application markers. When raw
saving is explicitly enabled, the private raw file includes sensitive request
data and must remain excluded from Git.

## Private-safe local replay

The replay utility reads only the captured JSON body and content type. It does
not resend Host, Authorization, Cookie, shared-secret, or other captured
headers, and it accepts loopback destinations only.

Network example:

```bash
python scripts/replay_unifi_webhook.py private-samples/unifi/network/http/network-client-disconnected-01.raw http://127.0.0.1:18080/unifi/network
```

Protect example:

```bash
python scripts/replay_unifi_webhook.py private-samples/unifi/protect/http/protect-motion-01.raw http://127.0.0.1:18080/unifi/protect
```

For Drive, use the existing saved-email replay mechanism:

```bash
python scripts/replay_email.py private-samples/unifi/drive/drive-backup-task-partially-completed-01.eml --host 127.0.0.1 --port 8026
```

These paths are documentation examples only and are never required by tests.

## Sanitization and review workflow

1. Trigger one narrow, low-volume development notification.
2. Preserve its original only under `private-samples/unifi/`.
3. Run the matching analyzer and redirect or write only sanitized output.
4. Manually inspect every sanitized result for email addresses, URLs, webhook
   values, hostnames, domains, IP and MAC addresses, UUIDs, serials, disk or
   device identifiers, camera names, usernames, authorization values, cookies,
   and tokens.
5. Replace anything questionable with `<redacted>` before sharing it or using
   it to create a synthetic fixture.
6. Build synthetic fixtures from the reviewed structure, never by lightly
   editing or copying a private payload.
7. Confirm `git status`, `git diff --cached`, and the privacy scan are clean
   before committing.

Sanitization is defense in depth, not a guarantee. Human review is mandatory.
The findings should be recorded on issue #32 without closing it until the full
implementation and validation scope is complete.
