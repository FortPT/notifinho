# Integrations and inputs

Notifinho distinguishes an **integration** from the **input** used to receive
its events. Integrations such as Zabbix, Dell iDRAC, and Home Assistant are
part of the image, always available, and cannot be disabled or removed.

Inputs are transport types: `smtp`, `http`, or `redfish`. A single integration
can expose more than one input. Zabbix currently exposes SMTP and HTTP; Dell
iDRAC exposes Redfish. Route records persist both dimensions.

```text
Zabbix (SMTP)  -> Operations Teams
Zabbix (HTTP)  -> Automation Discord
Generic (Redfish) -> Hardware Teams
```

Integration categories, routes, and destinations are stored in private SQLite
platform state. The first v2.5 migration imports known legacy categories and
routes, removes the test-only `Home Lab Generic` route, and normalizes
`config.yaml`. Existing filters, priorities, destination IDs, credentials, and
delivery history are preserved.
