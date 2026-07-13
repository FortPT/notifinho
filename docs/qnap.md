# QNAP notification support

QNAP QTS and QuTS hero support remains provisional in Notifinho `v1.5.1`.
It was initially developed from clearly labelled synthetic messages resembling
common Notification Center layouts and is now being validated against real QNAP
systems and Microsoft Teams delivery workflows.

## Initial event coverage

The initial parser classifies these event families:

- Notification Center test messages and generic notices
- Failed logins and other security warnings
- Storage pool, volume, and RAID warnings
- Disk and SMART warnings
- HBS and other backup failures
- Firmware and application update notices
- UPS and power events

Both plain-text and HTML messages are supported. Unknown labelled fields are
retained in notification metadata so new QTS and QuTS hero variants can be
studied without silently discarding useful values.

## Test without a QNAP device

Install the development dependencies and run the test suite:

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
```

The synthetic fixtures live in `tests/fixtures/qnap/`. They contain only
reserved `.invalid` addresses and invented system names. They must never be
replaced with unredacted production mail.

With the development container listening on host port `8026`, replay a
fixture through the complete SMTP pipeline:

```bash
python3 scripts/replay_email.py \
  tests/fixtures/qnap/storage_warning.eml \
  --host 127.0.0.1 \
  --port 8026
```

Other useful examples are:

```bash
python3 scripts/replay_email.py tests/fixtures/qnap/failed_login.eml
python3 scripts/replay_email.py tests/fixtures/qnap/hbs_backup_failure.eml
python3 scripts/replay_email.py tests/fixtures/qnap/ups_power_event.eml
```

The replay utility intentionally performs no SMTP authentication. Its
defaults are for the local development listener only.

## Routing

Add a QNAP route to the public configuration shape:

```yaml
routing:
  qnap:
    outputs:
      - output: discord
        target: default

      # - output: teams
      #   target: default
```

Configure the corresponding Discord or Teams webhook under `outputs`. Keep
real webhook URLs only in the ignored `config/config.yaml`; never add them to
`config/config.example.yaml` or fixture files.

## Configure QNAP Notification Center

The exact menu labels vary between QTS and QuTS hero releases. When a device
is available, create an SMTP service account or custom SMTP server in
Notification Center and use:

| Setting | Development | Production |
|---------|-------------|------------|
| SMTP server | Host running Notifinho | Host running Notifinho |
| Port | `8026` when connecting to the published dev port | `8025` |
| Authentication | Disabled | Disabled unless a future deployment adds it |
| TLS | Disabled for the current built-in listener | Disabled for the current built-in listener |
| Recipient | Any syntactically valid local notification address | Deployment-defined address |

Send Notification Center's test message first, then enable only the event
classes that should be forwarded. Notifinho detects the source from a
case-insensitive combination of sender, subject, and QNAP-specific body
markers; it does not rely on the recipient address.

## Known limitations

- Synthetic fixtures cannot represent every QTS, QuTS hero, language,
  firmware, application, or Notification Center template.
- The initial labelled-field parser targets English-style field names.
- Category, status, and event-type inference is heuristic when a message does
  not provide explicit labels.
- HTML styling is discarded; only operational text and labelled values are
  forwarded.
- SMTP authentication and TLS are not provided by Notifinho's current local
  listener.

## Help verify real formats

Anonymized real `.eml` samples are welcome. Before sharing a sample, remove
or replace email addresses, public and private IP addresses, hostnames,
usernames, serial numbers, storage identifiers, message IDs, and any other
private data. Never include webhook URLs or credentials. Please state the
QTS or QuTS hero version and the originating application when known.

Real samples will be used to refine the provisional parser and expand the
synthetic regression corpus; they should not be committed verbatim when they
contain production data.
