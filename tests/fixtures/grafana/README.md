# Synthetic Grafana email fixtures

Every `.eml` file in this directory is synthetic and was created for
Notifinho development. None came from a production Grafana instance. The
fixtures use reserved `.invalid` domains, invented dashboards, folders,
panels, datasources, rules, organizations, and hosts, and contain no real
addresses, IP addresses, credentials, webhooks, or private information.

Each message includes:

```text
X-Notifinho-Synthetic-Fixture: true
```

The layouts are inspired by common Grafana Alerting email concepts, but they
are not proof of compatibility with every Grafana version, contact point, or
custom notification template. The parser remains provisional until it can be
verified with anonymized real Grafana `.eml` samples.

| Fixture | Event | Format |
|---|---|---|
| `test_notification.eml` | Contact-point test | Plain text |
| `alert_firing.eml` | Critical firing alert | Multipart plain/HTML |
| `alert_resolved.eml` | Resolved alert | HTML |
| `alert_pending.eml` | Pending warning | Plain text |
| `alert_no_data.eml` | No Data alert | HTML |
| `datasource_error.eml` | Datasource/evaluation error | Multipart plain/HTML |
| `multiple_alerts.eml` | Two alerts in one notification | Plain text |

Replay the firing fixture through the development SMTP listener:

```bash
python3 scripts/replay_email.py \
  tests/fixtures/grafana/alert_firing.eml \
  --host 127.0.0.1 \
  --port 8026
```

Do not place captured production mail in this directory. Anonymize addresses,
hostnames, URLs, labels, values, organization names, and identifiers before
sharing any real sample.
