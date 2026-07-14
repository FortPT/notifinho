# Portainer discovery for v1.8.0

This guide preserves the private-sample discovery workflow used to design the
production integration. Production configuration now lives in the
[Portainer integration guide](portainer.md). The first validation target is
Portainer Business Edition 2.42.0 running on VM-04 (`192.168.0.164`).

[Portainer Alerting](https://docs.portainer.io/user/observability/alerting) is
a Business Edition feature and is configured by a Portainer administrator
under **Additional Functionality > Alerting**. Its notification channels
include webhook and email. Notifinho consumes those outbound alert
notifications; it does not use Portainer's stack redeployment webhooks, poll
the Portainer API, or retain an administrator credential.

## Confirmed BE 2.42.0 findings

- Portainer can reach a listener on VM-04 through its container network.
- The alert-manager **Test** action checks instance reachability but does not
  send a channel notification.
- An actual firing rule emits an Alertmanager-compatible versioned JSON
  envelope with `alerts`, common labels and annotations, group metadata,
  receiver, status, and truncated-alert count.
- Each alert contains status, labels, annotations, start/end times, generator
  URL, and fingerprint.
- Confirmed Portainer labels include alert metric and rule identifiers, alert
  source and name, authentication method, instance, job, severity, source,
  status, summary, and username.
- Confirmed annotations include creator and description.
- A warning-severity firing event was validated using a nonexistent synthetic
  username.
- Firing and resolved channel delivery were validated end to end by submitting
  a short-lived synthetic alert to Portainer's internal Alertmanager API. Both
  events reached the authenticated Notifinho development endpoint and were
  delivered to Discord with the expected warning and recovery presentation.

Private values from the original request were not copied into Git. The
production test fixture is synthetic and preserves only the reviewed schema.

## Safety boundary

Original webhook requests and emails can contain hostnames, environment or
endpoint identifiers, stack and container names, addresses, URLs, tokens, and
other private infrastructure data. Keep them on VM-04 and never commit them.

Create these local directories as needed:

```text
private-samples/portainer/webhook/
private-samples/portainer/email/
```

Open `.git/info/exclude` in the development checkout and add:

```gitignore
/private-samples/portainer/
```

Confirm the exclusion before capture:

```bash
cd /docker/notifinho-dev
git check-ignore -v private-samples/portainer/webhook/test.raw
```

The command must report `.git/info/exclude`. Do not continue until it does.

## Temporary webhook capture on VM-04

The capture server uses Python's standard library. It defaults to loopback and
does not save raw requests unless an output directory is explicitly supplied.
Port `18083` is reserved for this temporary discovery session so it does not
overlap the production or existing development HTTP listeners.

From `/docker/notifinho-dev`, start an isolated disposable container:

```bash
docker run --rm --name notifinho-portainer-capture \
  --network host \
  -v /docker/notifinho-dev:/notifinho \
  -w /notifinho \
  python:3.13-slim \
  python scripts/capture_portainer_webhook.py \
    --host 0.0.0.0 \
    --port 18083 \
    --output-dir private-samples/portainer/webhook
```

If VM-04's firewall blocks the request, add only a temporary rule appropriate
to the local Portainer-to-host path. Do not expose port `18083` outside the
trusted management network.

In Portainer:

1. Open **Additional Functionality > Alerting**.
2. Open **Settings** for the internal alert manager.
3. Add a **Webhook** notification channel named `Notifinho discovery`.
4. Set its URL to `http://192.168.0.164:18083/portainer/alerts`.
5. Use a channel test if the UI offers one. Otherwise enable one narrow,
   low-volume test rule and deliberately trigger and recover it.

Do not enable broad alert collection during discovery. One firing notification
and, where possible, one resolved notification are enough for the first pass.

For every request, the terminal prints only a deterministic sanitized summary.
Because `--output-dir` was supplied, a private `.raw` original is also retained
under `private-samples/portainer/webhook/`. Treat that file as sensitive.

Stop the capture with Ctrl+C immediately after the narrow test. Remove or
disable the discovery channel and remove any temporary firewall rule.

## Offline webhook analysis

Analyze a private original locally without replaying it over the network:

```bash
python3 scripts/analyze_portainer_webhook.py \
  private-samples/portainer/webhook/REQUEST.raw
```

To retain a candidate sanitized summary for human review:

```bash
python3 scripts/analyze_portainer_webhook.py \
  private-samples/portainer/webhook/REQUEST.raw \
  --output private-samples/portainer/webhook/REQUEST.sanitized.json
```

The analyzer never modifies its input. It reports structural details such as
method, redacted path shape, safe header names, content type, body size, JSON
types and shape, parsing status, and likely Portainer/Alertmanager markers.

## Email discovery

Webhook is the preferred first path because it preserves structured data. To
compare Portainer's email format, configure a development-only Alerting email
channel to VM-04's development SMTP listener on port `8026`. Do not change the
production SMTP destination. Trigger only the same narrow test event and keep
the original `.eml` under `private-samples/portainer/email/`.

Print a private-safe structural summary:

```bash
python3 scripts/analyze_portainer_email.py \
  private-samples/portainer/email/sample.eml
```

Or write a review copy:

```bash
python3 scripts/analyze_portainer_email.py \
  private-samples/portainer/email/sample.eml \
  --output private-samples/portainer/email/sample.sanitized.json
```

The summary contains only safe header names, MIME structure, subject shape,
body-alternative presence, private-safe attachment metadata, parser defects,
and likely Portainer markers. It never reports the sender address or domain.

## Human review and issue update

Before sharing any sanitized JSON, manually inspect it for email addresses,
URLs, webhook values, hostnames, domains, IP or MAC addresses, UUIDs, serials,
environment IDs, endpoint IDs, stack or container names, usernames,
authorization values, cookies, and tokens. Replace anything questionable with
`<redacted>`.

Build synthetic test fixtures from the reviewed structure; never lightly edit
or copy a private payload. Record the confirmed transport, payload family,
firing/resolved behavior, and Portainer BE 2.42.0 compatibility on issue #42.
Keep the issue open until parsing, presentation, routing, documentation, and
real delivery validation are complete.

Before every commit, run:

```bash
git status --short
git diff --cached
```

No path under `private-samples/` may appear. Sanitization is defense in depth,
not a guarantee; human review remains mandatory.
