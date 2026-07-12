# Synthetic QNAP email fixtures

Every `.eml` file in this directory is a synthetic test fixture created for
Notifinho development. None of these messages came from a physical QNAP NAS,
and none contains a real address, IP address, serial number, webhook, or other
private data. Synthetic mailboxes and domains use the reserved `.invalid`
top-level domain.

These fixtures are inspired by common QTS and QuTS hero Notification Center
layouts, but the initial parser is provisional until it can be compared with
anonymized real QNAP emails. The fixtures must not be treated as proof of
compatibility with every QTS, QuTS hero, Notification Center, or application
version.

Each message includes this explicit marker:

```text
X-Notifinho-Synthetic-Fixture: true
```

## Included events

| Fixture | Event | Body format |
|---|---|---|
| `notification_center_test.eml` | Notification Center test message | Plain text |
| `failed_login.eml` | Failed login/security warning | Multipart plain text and HTML |
| `storage_warning.eml` | Storage pool and RAID warning | HTML |
| `smart_warning.eml` | Disk S.M.A.R.T. warning | Plain text |
| `hbs_backup_failure.eml` | HBS backup job failure | Multipart plain text and HTML |
| `update_notice.eml` | Firmware/application update notice | HTML |
| `ups_power_event.eml` | UPS/power event | Plain text |

## Replay against the development SMTP listener

The replay utility defaults to the development listener at
`127.0.0.1:8026`:

```bash
python3 scripts/replay_email.py tests/fixtures/qnap/storage_warning.eml
```

The target can also be supplied explicitly:

```bash
python3 scripts/replay_email.py \
  tests/fixtures/qnap/storage_warning.eml \
  --host 127.0.0.1 \
  --port 8026
```

The local development flow does not use SMTP authentication or TLS.

Please contribute anonymized real `.eml` samples before expanding or claiming
broad QNAP compatibility. Remove or replace all personal data, addresses,
hostnames, IP addresses, serial numbers, identifiers, and embedded links first.
