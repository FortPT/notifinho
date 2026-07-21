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

Trusted management systems can generate routine `USR0030` and `USR0032`
login/logout audit records over REDFISH, IPMI over LAN, or another management
transport. These successful session records can be handled without delivery
by listing only the trusted client addresses:

```yaml
notifications:
  dell_idrac:
    suppress_ipmi_session_audit_from:
      - 192.0.2.10
      - 192.0.2.11
```

The filter requires all three signals: a Dell iDRAC notification, message ID
`USR0030` or `USR0032`, and an exact configured source address. Transport text
is deliberately irrelevant. Failed logins, untrusted addresses, and all other
security events continue through normal routing. Suppressed events are logged
as handled so the BMC does not retry them.

Notifinho does not call the iDRAC API, poll Lifecycle Controller data, or need
permanent administrative credentials. Real validation across iDRAC releases
remains pending and should begin with a harmless test alert.
