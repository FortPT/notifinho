# Grafana notification support

Grafana Alerting support is provisional in Notifinho `v1.3.0-dev`. It was
implemented without production Grafana email samples and is currently
verified only against clearly labelled synthetic fixtures.

## Initial event coverage

- Grafana contact-point test notifications
- Firing alerts
- Resolved and normal alerts
- Warning and pending alerts
- No Data alerts
- Datasource and evaluation errors
- Grouped notifications containing multiple alerts

The parser supports plain-text, HTML, and multipart email, retains unknown
labelled fields in metadata, and extracts common rule, folder, dashboard,
panel, datasource, labels, values, event-time, and link fields.

## Configure Grafana conceptually

Grafana must first be configured with an SMTP server, normally through its
configuration file or equivalent environment variables. Point that SMTP
configuration at the host running Notifinho:

| Setting | Development | Production |
|---|---|---|
| SMTP host | Notifinho development host | Notifinho host |
| SMTP port | `8026` when using the published development port | `8025` |
| Authentication | Disabled | Disabled for the current listener |
| TLS | Disabled for the current listener | Disabled for the current listener |

Then create an Email contact point in Grafana Alerting and route the desired
notification policies to it. Menu labels and template fields vary between
Grafana releases and custom contact-point templates.

## Dedicated Discord routing

Keep real webhook values only in the ignored `config/config.yaml`:

```yaml
outputs:
  discord:
    enabled: true

    grafana:
      webhook: "PASTE_GRAFANA_DISCORD_WEBHOOK_HERE"

routing:
  grafana:
    outputs:
      - output: discord
        target: grafana

      # - output: teams
      #   target: grafana
```

The public example uses the key `webhook`. Do not use `webhook_url`.

## Test without Grafana

Install the development dependencies and run the regression suite:

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
```

With Notifinho listening on the development host port, replay the synthetic
firing fixture:

```bash
python3 scripts/replay_email.py \
  tests/fixtures/grafana/alert_firing.eml \
  --host 127.0.0.1 \
  --port 8026
```

Other useful fixtures include:

```bash
python3 scripts/replay_email.py tests/fixtures/grafana/alert_resolved.eml
python3 scripts/replay_email.py tests/fixtures/grafana/alert_no_data.eml
python3 scripts/replay_email.py tests/fixtures/grafana/datasource_error.eml
```

The replay utility performs no SMTP authentication and defaults to
`127.0.0.1:8026` for local development.

## Known limitations

- Synthetic fixtures do not prove compatibility with every Grafana release,
  Grafana Cloud template, or custom contact-point template.
- Initial labelled-field aliases target English-style templates.
- Labels and values are preserved as readable text rather than interpreted as
  a complete Grafana data model.
- Grouped notifications expose their count and preserve per-alert labelled
  fields, but do not yet create a separate card section for every alert.
- SMTP authentication and TLS are not implemented by Notifinho's current
  listener.

## Request for anonymized samples

Anonymized real Grafana `.eml` samples are welcome. Before sharing, replace
email addresses, instance and organization names, URLs, hostnames, labels,
values, dashboard and panel names, datasource names, rule identifiers, and
any credentials or private annotations. Never share webhook URLs.

Please include the Grafana version, deployment type, and whether a custom
notification template was used when known. Real samples will help verify and
refine this provisional parser; they should not be committed verbatim when
they contain production data.
