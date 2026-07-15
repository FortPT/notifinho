# Dell iDRAC

Notifinho v1.9.0 provides a fixture-validated Dell iDRAC candidate through
`POST /redfish/dell` and conservative delivered iDRAC email alerts. Both paths
use the `dell_idrac` routing key.

Use this Redfish Event Service destination:

```text
http://notifinho.example:8080/redfish/dell
```

Authenticate with a source-scoped header token where supported. Otherwise use
a trusted token-injecting reverse proxy or the existing SMTP listener. The
adapter recognizes storage, power, thermal, memory, network, security,
firmware, chassis, and availability events and retains safe operator actions.

```yaml
routing:
  dell_idrac:
    outputs:
      - output: discord
        target: hardware
```

Notifinho does not call the iDRAC API, poll Lifecycle Controller data, or need
permanent administrative credentials. Real validation across iDRAC releases
remains pending and should begin with a harmless test alert.

