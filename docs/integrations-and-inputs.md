# Integrations and inputs

Notifinho distinguishes an **integration** from the **input** used to receive
its events. Integrations such as Zabbix, Dell iDRAC, and Home Assistant are
part of the image, always available, and cannot be disabled or removed.

Inputs are transport types: `smtp`, `http`, or `redfish`. A single integration
can expose more than one input. Zabbix currently exposes SMTP and HTTP; Dell
iDRAC exposes Redfish. Route records persist both dimensions.

```yaml
routing:
  zabbix:
    outputs:
      - id: zabbix-smtp-operations
        name: Zabbix SMTP to Operations
        input: smtp
        output: teams
        target: operations
        enabled: true

  "*":
    outputs:
      - id: generic-redfish-hardware
        name: Generic Redfish to Hardware
        input: redfish
        output: teams
        target: hardware
        enabled: true
```

Integration category overrides are stored in the private SQLite platform state.
The first v2.4 synchronization imports known legacy
`webui.source_categories`, removes it and `webui.removed_sources` from YAML,
and removes the test-only route named `Home Lab Generic`. Existing supported
routes, destinations, filters, priorities, and credentials remain authoritative.
