# TrueNAS 26 integration

TrueNAS support is provisional in Notifinho `1.4.0-dev`. It follows the public
TrueNAS 26 middleware alert-service layout and must still be validated against
private real TrueNAS 26 mail on VM-04.

## How TrueNAS mail reaches Notifinho

TrueNAS has two related settings:

1. **System email transport** controls the SMTP server, port, sender, and
   recipients used for mail delivery.
2. **Email alert service** controls whether alerts are emailed and the minimum
   alert level.

Configure both. **Send Test Email** (also shown as **Send Test Mail** in some
TrueNAS 26 documentation/UI revisions) validates the global SMTP transport.
It is not guaranteed to use the alert-service body and can therefore use
Notifinho's generic fallback. **Send Test Alert** exercises the Email alert
service and should produce the TrueNAS layout that this integration detects.

TrueNAS 26 documentation places system email under **System > General
Settings > Email > Settings**. It places the alert service under **System >
Alert Settings > Alert Services > Email > Edit**. The top-right Alerts panel
also links to both screens. UI labels can move between TrueNAS early-release
builds; consult the [TrueNAS 26 system email guide](https://www.truenas.com/docs/scale/26/systemsettings/general/settingupsystememail/)
and [alert settings reference](https://www.truenas.com/docs/scale/26/systemsettings/alertssettingsservicescreen/)
for the installed build.

## Configure global SMTP transport

In **Email Options**, select **SMTP** and use values equivalent to these:

| Setting | Development | Production |
|---|---|---|
| Outgoing Mail Server | VM-04 hostname or reachable address | `notifinho.example.invalid` or the real Notifinho host |
| Mail Server Port | `8026` | `8025` |
| Security/TLS | None | None, unless a separate SMTP proxy adds TLS |
| Authentication | Disabled | Disabled |
| From Email | `truenas@synthetic-truenas.example.invalid` for isolated testing | A deployment-owned sender address |
| Email Recipients | A deployment-owned address accepted by the listener | A deployment-owned address accepted by the listener |

Use VM-04's address as seen from the TrueNAS appliance. `127.0.0.1` refers to
TrueNAS itself and is only correct if Notifinho is running on that same host.
Do not commit deployment addresses or credentials.

Save the transport and use **Send Test Email** to confirm that TrueNAS can
connect to the listener. A generic classification for this transport-only
message is acceptable; the next step validates TrueNAS alert detection.

## Configure the Email alert service

Edit or add the Email alert service:

- enable the service;
- set **Type** to Email/Mail;
- set an alert recipient if the screen provides one (an empty API `email`
  value uses the system default in v26);
- choose the minimum **Level** required by the deployment; and
- save, then select **Send Test Alert**.

TrueNAS sends the selected level and more severe alerts. The v26 API calls the
service type `Mail` and supports Info, Notice, Warning, Error, Critical, Alert,
and Emergency levels. See the official
[v26 alertservice API](https://api.truenas.com/v26.0/api_methods_alertservice.create.html).

## Dedicated routing

Only edit the deployment's private `config/config.yaml` locally. The public
shape is:

```yaml
outputs:
  discord:
    truenas:
      webhook: "PASTE_TRUENAS_DISCORD_WEBHOOK_HERE"

  teams:
    truenas:
      webhook: "PASTE_TRUENAS_TEAMS_WORKFLOW_WEBHOOK_HERE"

routing:
  truenas:
    outputs:
      - output: discord
        target: truenas

      - output: teams
        target: truenas
```

Keep `outputs.teams.enabled: true` when enabling the Teams route. Dedicated
targets use the existing `webhook` key. Routes can instead target `default` if
separate TrueNAS destinations are not wanted.

## Replay synthetic fixtures

The replay tool defaults to the VM development listener at
`127.0.0.1:8026`:

```bash
python3 scripts/replay_email.py tests/fixtures/truenas/test_alert.eml
python3 scripts/replay_email.py tests/fixtures/truenas/pool_degraded.eml
python3 scripts/replay_email.py tests/fixtures/truenas/smart_warning.eml
python3 scripts/replay_email.py tests/fixtures/truenas/scrub_failure.eml
python3 scripts/replay_email.py tests/fixtures/truenas/replication_failure.eml
python3 scripts/replay_email.py tests/fixtures/truenas/ups_on_battery.eml
python3 scripts/replay_email.py tests/fixtures/truenas/cleared_alert.eml
python3 scripts/replay_email.py tests/fixtures/truenas/grouped_alerts.eml
python3 scripts/replay_email.py tests/fixtures/truenas/malformed.eml
```

To target another development host explicitly:

```bash
python3 scripts/replay_email.py \
  tests/fixtures/truenas/grouped_alerts.eml \
  --host VM-04-HOSTNAME \
  --port 8026
```

Inspect logs for `Detected TrueNAS email`, `TRUENAS PARSED`, the hostname,
event types and count, `routing.truenas`, formatter selection, and delivery
result. Replay does not require external network access or a webhook when
parser-only validation is being performed.

## Supported event areas

The parser classifies recognizable messages into the project's existing
categories:

- storage pool and ZFS health;
- disk and SMART health;
- scrub failures;
- replication, backup, snapshot, and related task failures;
- UPS, battery, and utility-power alerts;
- system and hardware conditions;
- network conditions;
- security and certificate conditions;
- applications and services; and
- generic TrueNAS alerts when no stronger category is identifiable.

The shared status values remain `information`, `warning`, `failure`, and
`success`. Cleared alerts are recoveries with `success`; grouped messages keep
individual new, cleared, and current items in notification metadata.

## Provisional format assumptions

The implementation is based on the public TrueNAS middleware behavior:

- the mail subject is commonly `Alerts`, but that weak subject never detects
  TrueNAS by itself;
- visible alert content starts with `TrueNAS @ <hostname>`;
- test alerts contain `This is a test alert`;
- normal mail uses New alert(s), cleared alert(s), and Current alerts sections;
- alert messages are HTML list items; and
- one message can contain new, cleared, and current sections together.

The parser does not currently receive TrueNAS alert class, category, level, or
structured timestamp fields because the upstream mail formatter emits each
alert's human-readable text. Category, severity, status, and event time are
therefore inferred from that text. Customized templates, localization,
Enterprise HA node prefixes, wording changes, and alert-specific HTML remain
provisional until real TrueNAS 26 replay confirms them.

## Safe real-sample handling

Private `.eml` files can contain hostnames, addresses, pool/dataset names,
disk serial numbers, usernames, message IDs, routing headers, and recipient
addresses. Keep originals outside Git. Before sharing a sample:

1. work on a copy;
2. replace identifying headers and body values with synthetic names;
3. remove attachments unless required to reproduce a parser issue;
4. verify no credentials, tokens, webhook URLs, or private domains remain;
5. replay the anonymized copy locally; and
6. commit only a clearly marked synthetic derivative when it adds coverage.

The private real TrueNAS 26 **test email** and **test alert** on VM-04 remain
the final authority and must not be committed.
