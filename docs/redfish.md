# Redfish Event Service

Notifinho v1.9.0 accepts bounded standard Redfish Event Service envelopes and
normalizes them through the existing notification model, router, Discord
formatters, and Microsoft Teams formatters.

## Endpoints

| Endpoint | Source key | Purpose |
|---|---|---|
| `/redfish/events` | detected vendor or `redfish` | Standards-oriented shared endpoint |
| `/redfish/supermicro` | `supermicro` | Explicit Supermicro adapter |
| `/redfish/hpe` | `hpe_ilo` | Explicit HPE iLO adapter |
| `/redfish/dell` | `dell_idrac` | Explicit Dell iDRAC adapter |

Requests must use `POST` with `Content-Type: application/json`. Authentication
may use the existing global `http.shared_secret` or an enabled v1.9 token whose
`sources` contains the normalized source. Send the token in
`X-Notifinho-Token` or as `Authorization: Bearer TOKEN`.

```yaml
http:
  enabled: true
  host: 0.0.0.0
  port: 8080
  shared_secret: ""

redfish:
  deduplication_window_seconds: 300

api:
  enabled: true
  tokens:
    hardware:
      enabled: true
      role: application
      sources: [redfish, supermicro, hpe_ilo, dell_idrac]
      token_file: /run/secrets/notifinho_hardware_token
      rate_limit_per_minute: 120
```

The token file must be readable only by its owner (`0600`). Notifinho accepts
at most 64 events per envelope. Duplicate fingerprints inside the configured
window return `204` but are not routed again. Raw payloads, credentials, event
fingerprints, and full management URLs are not shown in cards or access logs.

## Validation status

The v1.9.0 adapters are validated with synthetic standard envelopes and SMTP
fixtures. Vendor firmware versions can change registries and fields; real
Supermicro, HPE, and Dell delivery remains a post-release compatibility gate.
Use a non-critical test event first and compare the received card with the
source controller event log.

