# HPE iLO

Notifinho v1.9.0 provides a fixture-validated HPE iLO candidate through
`POST /redfish/hpe` and conservative HPE iLO AlertMail parsing. Both paths use
the `hpe_ilo` routing key.

Create an iLO Redfish Event Service subscription pointing to:

```text
http://notifinho.example:8080/redfish/hpe
```

Prefer a source-scoped token sent as `X-Notifinho-Token`. Where the installed
iLO release cannot add a header, use a protected reverse proxy or AlertMail to
Notifinho SMTP. Configure routing independently from other hardware sources:

```yaml
routing:
  hpe_ilo:
    outputs:
      - output: teams
        target: hardware
```

The adapter preserves safe registry/message identifiers, the affected origin,
severity, category, and recommended action. It does not poll iLO or store iLO
administrator credentials. Live validation across iLO generations remains
pending; compare a test card with the Integrated Management Log before relying
on the integration operationally.

