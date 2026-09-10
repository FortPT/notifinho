"""Built-in integration catalogue and route input choices."""

from __future__ import annotations

from copy import deepcopy


CATEGORIES = (
    "virtualization",
    "monitoring",
    "storage",
    "networking",
    "hardware",
    "automation",
    "containers",
    "security",
    "generic",
)

_INPUT_NAMES = {
    "smtp": "SMTP",
    "http": "HTTP",
    "redfish": "Redfish",
}

# ``source`` is the value produced by the parser and persisted on routes.
# Display names and input names are deliberately separate from those internal
# identifiers so the WebUI never needs to expose values such as dell_idrac.
_CATALOGUE = (
    {
        "source": "xo",
        "name": "Xen Orchestra",
        "category": "virtualization",
        "icon_key": "xen_orchestra",
        "inputs": ("smtp",),
        "aliases": ("xen_orchestra", "xenorchestra"),
    },
    {
        "source": "zabbix",
        "name": "Zabbix",
        "category": "monitoring",
        "icon_key": "zabbix",
        "inputs": ("smtp", "http"),
        "aliases": (),
    },
    {
        "source": "grafana",
        "name": "Grafana",
        "category": "monitoring",
        "icon_key": "grafana",
        "inputs": ("http",),
        "aliases": (),
    },
    {
        "source": "portainer",
        "name": "Portainer",
        "category": "containers",
        "icon_key": "portainer",
        "inputs": ("http",),
        "aliases": (),
    },
    {
        "source": "proxmox",
        "name": "Proxmox",
        "category": "virtualization",
        "icon_key": "proxmox",
        "inputs": ("http",),
        "aliases": (),
    },
    {
        "source": "qnap",
        "name": "QNAP",
        "category": "storage",
        "icon_key": "qnap",
        "inputs": ("smtp",),
        "aliases": (),
    },
    {
        "source": "synology",
        "name": "Synology",
        "category": "storage",
        "icon_key": "synology",
        "inputs": ("smtp", "http"),
        "aliases": (),
    },
    {
        "source": "truenas",
        "name": "TrueNAS",
        "category": "storage",
        "icon_key": "truenas",
        "inputs": ("smtp",),
        "aliases": (),
    },
    {
        "source": "unifi_network",
        "name": "UniFi Network",
        "category": "networking",
        "icon_key": "unifi_network",
        "inputs": ("http",),
        "aliases": ("network",),
    },
    {
        "source": "unifi_protect",
        "name": "UniFi Protect",
        "category": "security",
        "icon_key": "unifi_protect",
        "inputs": ("http",),
        "aliases": ("protect",),
    },
    {
        "source": "unifi_drive",
        "name": "UniFi Drive",
        "category": "storage",
        "icon_key": "unifi_drive",
        "inputs": ("http",),
        "aliases": ("drive",),
    },
    {
        "source": "supermicro",
        "name": "Supermicro",
        "category": "hardware",
        "icon_key": "supermicro",
        "inputs": ("redfish",),
        "aliases": (),
    },
    {
        "source": "hpe_ilo",
        "name": "HPE iLO",
        "category": "hardware",
        "icon_key": "hpe_ilo",
        "inputs": ("redfish",),
        "aliases": ("hpe",),
    },
    {
        "source": "dell_idrac",
        "name": "Dell iDRAC",
        "category": "hardware",
        "icon_key": "dell_idrac",
        "inputs": ("redfish",),
        "aliases": ("dell",),
    },
    {
        "source": "home_assistant",
        "name": "Home Assistant",
        "category": "automation",
        "icon_key": "home_assistant",
        "inputs": ("http",),
        "aliases": (),
    },
)


# User-facing route filter values exposed by each integration.
#
# These are keyed ONLY by parser source. Input transport is deliberately
# excluded: an integration has the same event vocabulary over SMTP/HTTP.
#
# Empty tuples mean that dimension is not exposed by that integration.
_ROUTE_FILTERS = {
    "xo": {
        "severities": (),
        "statuses": (
            "info",
            "success",
            "failure",
            "skipped",
        ),
    },
    "zabbix": {
        "severities": (
            "not classified",
            "information",
            "warning",
            "average",
            "high",
            "disaster",
        ),
        "statuses": (
            "failure",
            "success",
        ),
    },
    "grafana": {
        "severities": (
            "information",
            "warning",
            "error",
            "critical",
        ),
        "statuses": (
            "firing",
            "pending",
            "resolved",
            "no data",
            "error",
            "test",
            "not resolved",
        ),
    },
    "portainer": {
        "severities": (
            "information",
            "warning",
            "critical",
            "error",
            "failure",
        ),
        "statuses": (
            "firing",
            "resolved",
        ),
    },
    "proxmox": {
        "severities": (
            "debug",
            "info",
            "information",
            "notice",
            "warning",
            "warn",
            "error",
            "critical",
            "success",
        ),
        "statuses": (
            "information",
            "warning",
            "failure",
            "failed",
            "success",
            "resolved",
            "recovered",
        ),
    },
    "qnap": {
        "severities": (
            "information",
            "normal",
            "warning",
            "error",
            "critical",
        ),
        "statuses": (),
    },
    "synology": {
        "severities": (
            "debug",
            "info",
            "information",
            "notice",
            "warning",
            "warn",
            "error",
            "critical",
            "success",
        ),
        "statuses": (
            "information",
            "warning",
            "failure",
            "failed",
            "success",
            "resolved",
            "recovered",
            "restored",
        ),
    },
    "truenas": {
        "severities": (
            "information",
            "warning",
            "critical",
            "normal",
        ),
        "statuses": (),
    },
    "unifi_network": {
        "severities": (
            "information",
            "warning",
            "critical",
        ),
        "statuses": (),
    },
    "unifi_protect": {
        "severities": (
            "information",
        ),
        "statuses": (),
    },
    "unifi_drive": {
        "severities": (
            "information",
            "warning",
            "critical",
        ),
        "statuses": (),
    },
    "supermicro": {
        "severities": (
            "critical",
            "fatal",
            "emergency",
            "alert",
            "warning",
            "caution",
            "ok",
            "normal",
            "cleared",
            "informational",
            "information",
            "info",
        ),
        "statuses": (),
    },
    "hpe_ilo": {
        "severities": (
            "critical",
            "fatal",
            "emergency",
            "alert",
            "warning",
            "caution",
            "ok",
            "normal",
            "cleared",
            "informational",
            "information",
            "info",
        ),
        "statuses": (),
    },
    "dell_idrac": {
        "severities": (
            "critical",
            "fatal",
            "emergency",
            "alert",
            "warning",
            "caution",
            "ok",
            "normal",
            "cleared",
            "informational",
            "information",
            "info",
        ),
        "statuses": (),
    },
    "home_assistant": {
        "severities": (
            "information",
            "info",
            "success",
            "warning",
            "warn",
            "error",
            "critical",
            "fatal",
            "emergency",
        ),
        "statuses": (),
    },
}

_BY_SOURCE = {item["source"]: item for item in _CATALOGUE}
_ALIASES = {
    alias: item["source"]
    for item in _CATALOGUE
    for alias in (item["source"], *item["aliases"])
}


def canonical_source(value: str) -> str:
    """Normalize known aliases while preserving custom source identifiers."""

    normalized = str(value or "").strip().casefold()
    return _ALIASES.get(normalized, normalized)


def integration(value: str) -> dict | None:
    """Return one integration definition by parser source."""

    item = _BY_SOURCE.get(canonical_source(value))
    if item is None:
        return None
    return _public(item)


def integrations(overrides: dict[str, str] | None = None) -> list[dict]:
    """Return every integration, including ones not yet observed at runtime."""

    overrides = overrides or {}
    result = []
    for source in _CATALOGUE:
        item = _public(source)
        item["category"] = overrides.get(source["source"], source["category"])
        result.append(item)
    return result


def route_options(overrides: dict[str, str] | None = None) -> list[dict]:
    """Return stable integration/input combinations for route forms."""

    result = []
    for item in integrations(overrides):
        for input_item in item["inputs"]:
            result.append(
                {
                    "id": f'{item["source"]}:{input_item["id"]}',
                    "source": item["source"],
                    "input_type": input_item["id"],
                    "integration_name": item["name"],
                    "input_name": input_item["name"],
                    "label": f'{item["name"]} ({input_item["name"]})',
                    "generic": False,
                }
            )
    result.extend(
        (
            {
                "id": "fallback:smtp",
                "source": "*",
                "input_type": "smtp",
                "integration_name": "Fallback",
                "input_name": "SMTP",
                "label": "Fallback (SMTP)",
                "generic": True,
            },
            {
                "id": "fallback:http",
                "source": "*",
                "input_type": "http",
                "integration_name": "Fallback",
                "input_name": "HTTP",
                "label": "Fallback (HTTP)",
                "generic": True,
            },
            {
                "id": "fallback:redfish",
                "source": "*",
                "input_type": "redfish",
                "integration_name": "Fallback",
                "input_name": "Redfish",
                "label": "Fallback (Redfish)",
                "generic": True,
            },
        )
    )
    return result


def infer_input_type(source: str) -> str:
    """Infer a safe input for legacy routes that did not persist one."""

    normalized = canonical_source(source)
    if normalized in {"redfish"}:
        return "redfish"
    if normalized in {"generic", "restful", "rest_api", "home_lab"}:
        return "http"
    item = _BY_SOURCE.get(normalized)
    if item is None:
        return ""
    # Zabbix and Synology routes in releases through 2.3 were SMTP routes.
    if normalized in {"zabbix", "synology"}:
        return "smtp"
    return item["inputs"][0] if len(item["inputs"]) == 1 else ""


def _public(item: dict) -> dict:
    source = item["source"]
    route_filters = _ROUTE_FILTERS[source]
    return {
        "id": source,
        "source": source,
        "sources": [source, *item["aliases"]],
        "name": item["name"],
        "category": item["category"],
        "icon_key": item["icon_key"],
        "inputs": [
            {"id": value, "name": _INPUT_NAMES[value]}
            for value in item["inputs"]
        ],
        "route_filters": {
            "severities": list(route_filters["severities"]),
            "statuses": list(route_filters["statuses"]),
        },
    }
