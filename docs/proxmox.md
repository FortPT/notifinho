# Proxmox VE integration candidate

Notifinho v1.8 includes fixture-validated Proxmox VE ingestion through SMTP and
an authenticated native HTTP endpoint:

```text
POST /proxmox/events
```

Real Proxmox delivery has not yet been validated. Keep this integration on the
development instance until representative Proxmox VE notifications can be
tested. The parser is designed to tolerate missing fields, but synthetic
fixtures cannot prove compatibility with every Proxmox release and template.

## Supported candidate events

- backup and restore, including `vzdump` guest-result rows;
- replication;
- node and guest availability;
- cluster, quorum, and high-availability events;
- storage, Ceph, ZFS, pool, disk, and volume events;
- security, certificate, update, and general system notifications.

Both transports normalize to the `proxmox` source key and use dedicated
Discord embeds or Microsoft Teams Adaptive Cards.

## Notifinho configuration

```yaml
http:
  enabled: true
  host: 0.0.0.0
  port: 8080
  max_body_bytes: 1048576
  shared_secret: "PASTE_64_CHARACTER_HEX_SECRET"

outputs:
  discord:
    enabled: true
    proxmox:
      webhook: "PASTE_PROXMOX_DISCORD_WEBHOOK"

  teams:
    enabled: false
    proxmox:
      webhook: "PASTE_PROXMOX_TEAMS_WORKFLOW_WEBHOOK"

routing:
  proxmox:
    outputs:
      - output: discord
        target: proxmox

      # - output: teams
      #   target: proxmox
```

Do not commit the real secret or destination URLs.

## SMTP candidate

Point a Proxmox notification target at Notifinho's SMTP listener. Detection
accepts Proxmox-branded senders or characteristic `pve`/`vzdump` backup,
replication, and status subjects. It does not require the sender address to be
`root@pam` or use a particular private domain.

The initial parser handles text and HTML MIME bodies, labelled fields, and
common guest-result rows shaped like:

```text
VMID NAME STATUS TIME SIZE MESSAGE
100 synthetic-guest OK 00:12:00 32.00 GiB
101 synthetic-db FAILED 00:00:18 8.00 GiB synthetic timeout
```

Unknown Proxmox layouts still produce a bounded generic Proxmox notification
instead of exposing or retaining raw content in output cards.

## Native webhook contract

Proxmox webhook targets use administrator-defined request templates, so
Notifinho defines an explicit versioned JSON contract instead of guessing a
release-specific payload:

```json
{
  "schema": "notifinho.proxmox.v1",
  "source": "proxmox-ve",
  "type": "storage",
  "title": "Synthetic storage warning",
  "message": "Synthetic storage usage exceeded the configured threshold.",
  "severity": "warning",
  "status": "firing",
  "timestamp": "2026-07-15T01:15:00Z",
  "metadata": {
    "node": "synthetic-pve-01",
    "storage": "synthetic-backup-store"
  }
}
```

Configure the target to send `Content-Type: application/json` and:

```text
X-Notifinho-Token: PASTE_64_CHARACTER_HEX_SECRET
```

Map Proxmox's available notification template values into the contract. Do not
copy illustrative placeholder syntax from another Proxmox release: confirm the
variables and JSON-escaping helper offered by the installed version. Keep
`schema` and `source` literal. `type` should preferably be one of `backup`,
`replication`, `storage`, `cluster`, `availability`, `security`, `guest`, or
`system`; otherwise Notifinho infers a category from the bounded text fields.

Only scalar values are accepted in `metadata`, and at most 64 metadata keys are
processed. Extra metadata is retained for normalization but is not rendered in
Discord or Teams cards.

## Development validation

With host port `18082` mapped to container port `8080`, verify authentication
and parsing with the committed synthetic fixture:

```bash
curl -sS -o /dev/null -w 'missing_token=%{http_code}\n' \
  -H 'Content-Type: application/json' \
  --data @tests/fixtures/proxmox/event_warning.json \
  http://127.0.0.1:18082/proxmox/events

curl -sS -o /dev/null -w 'authenticated=%{http_code}\n' \
  -H 'Content-Type: application/json' \
  -H "X-Notifinho-Token: ${TOKEN}" \
  --data @tests/fixtures/proxmox/event_warning.json \
  http://127.0.0.1:18082/proxmox/events
```

Expected responses are `401` and `204`. The authenticated request should
produce one development Discord or Teams card.

Replay the synthetic SMTP fixture through the existing safe replay tool:

```bash
python scripts/replay_email.py \
  tests/fixtures/proxmox/backup_failure.eml \
  --host 127.0.0.1 \
  --port 8026
```

## Deferred real-system validation

Before marking Proxmox support validated:

1. record the exact Proxmox VE version and notification transport;
2. send a test notification through SMTP and the configured webhook target;
3. validate one success, warning, failure, and recovery where the product can
   safely produce them;
4. validate backup, replication, node/cluster, storage, and availability
   layouts that are available in the environment;
5. confirm authentication returns `401` without the token and `204` with it;
6. confirm visible cards contain no internal IDs, secrets, URLs, or unnecessary
   infrastructure metadata;
7. replace or extend synthetic fixtures only with fully anonymized shapes.

Until this checklist is complete, leave issue #13 open and describe the
integration as a fixture-validated candidate.

## Rollback

Disable the Proxmox notification target and remove `routing.proxmox`. If the
HTTP listener is used only by Proxmox, it may also be disabled; otherwise keep
it enabled for UniFi and Portainer. Existing sources and routes are unchanged.
