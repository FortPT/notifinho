# Supermicro BMC / IPMI

Notifinho v1.9.0 provides a fixture-validated Supermicro candidate through the
explicit `/redfish/supermicro` endpoint and conservative delivered-email
detection. Both paths normalize to the `supermicro` routing key.

Configure the BMC Redfish Event Service subscription URL as:

```text
http://notifinho.example:8080/redfish/supermicro
```

Use `X-Notifinho-Token` when the BMC supports custom subscription headers. If
it cannot send a header, place the endpoint behind a trusted reverse proxy that
injects the token, or use the isolated SMTP compatibility path. Never expose an
unauthenticated Redfish endpoint to an untrusted network.

```yaml
routing:
  supermicro:
    outputs:
      - output: discord
        target: hardware
```

Thermal, fan, power, memory, storage, security, firmware, network, chassis, and
availability categories share a consistent server-hardware presentation.
SMTP recognition requires both Supermicro/BMC/IPMI identity and hardware-event
language to avoid stealing unrelated mail. Real BMC firmware compatibility is
pending representative hardware validation.

