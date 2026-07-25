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
Fallback (Redfish) -> Hardware Teams
```

Integration categories, routes, and destinations are stored in private SQLite
platform state. The first v2.5 migration imports known legacy categories and
routes, removes the test-only `Home Lab Generic` route, and normalizes
`config.yaml`. Existing filters, priorities, destination IDs, credentials, and
delivery history are preserved.


Since v2.5.1 the WebUI displays only the normalized input names **SMTP**,
**HTTP**, and **Redfish**. Wildcard route options are labelled Fallback and run
only when no dedicated integration route matches.
