"""Parser for Portainer BE Alerting webhook envelopes."""

from __future__ import annotations

import re

from models import Notification


class Parser:
    """Validate and normalize Alertmanager-compatible Portainer alerts."""

    PORTAINER_LABEL_KEYS = {
        "alert_metric_name",
        "alert_rule_id",
        "alert_source",
    }

    @classmethod
    def is_envelope(cls, payload) -> bool:
        if not isinstance(payload, dict):
            return False
        if str(payload.get("status", "")).casefold() not in {
            "firing",
            "resolved",
        }:
            return False
        alerts = payload.get("alerts")
        if not isinstance(alerts, list) or not alerts:
            return False

        common_labels = payload.get("commonLabels")
        common_annotations = payload.get("commonAnnotations")
        if not isinstance(common_labels, dict) or not isinstance(
            common_annotations,
            dict,
        ):
            return False

        portainer_keys = set(common_labels) & cls.PORTAINER_LABEL_KEYS
        values = [
            common_labels.get("source"),
            common_labels.get("alert_source"),
            common_annotations.get("created_by"),
        ]

        for alert in alerts:
            if not isinstance(alert, dict):
                return False
            labels = alert.get("labels")
            annotations = alert.get("annotations")
            if not isinstance(labels, dict) or not isinstance(annotations, dict):
                return False
            if str(alert.get("status", "")).casefold() not in {
                "firing",
                "resolved",
            }:
                return False
            portainer_keys.update(set(labels) & cls.PORTAINER_LABEL_KEYS)
            values.extend(
                (
                    labels.get("source"),
                    labels.get("alert_source"),
                    annotations.get("created_by"),
                )
            )

        branded = any("portainer" in cls._text(value).casefold() for value in values)
        return branded and len(portainer_keys) >= 2

    def parse(self, payload: dict) -> list[Notification]:
        if not self.is_envelope(payload):
            raise ValueError("invalid Portainer Alerting webhook envelope")

        common_labels = payload.get("commonLabels") or {}
        common_annotations = payload.get("commonAnnotations") or {}
        notifications = []

        for alert in payload["alerts"]:
            labels = {**common_labels, **(alert.get("labels") or {})}
            annotations = {
                **common_annotations,
                **(alert.get("annotations") or {}),
            }
            state = self._text(alert.get("status") or payload.get("status")).casefold()
            severity = self._text(labels.get("severity")).casefold()
            title = self._title(
                labels.get("summary")
                or labels.get("alertname")
                or "Portainer alert"
            )
            description = self._text(annotations.get("description"))

            notification = Notification(
                source="portainer",
                category=self._category(labels, title),
                status=self._status(state, severity),
                title=title,
                subject=title,
                body=description or title,
                start_time=self._text(alert.get("startsAt")),
                end_time=self._text(alert.get("endsAt")) if state == "resolved" else "",
            )
            notification.metadata = {
                "provider": "Portainer",
                "state": state,
                "severity": severity or "information",
                "alert_name": self._text(labels.get("alertname")),
                "summary": self._text(labels.get("summary")),
                "description": description,
                "instance": self._text(labels.get("instance")),
                "host": self._text(labels.get("instance")),
                "alert_source": self._text(labels.get("alert_source")),
                "source_label": self._text(labels.get("source")),
                "metric": self._text(labels.get("alert_metric_name")),
                "authentication_method": self._text(
                    labels.get("authentication_method")
                ),
                "username": self._text(labels.get("username")),
                "created_by": self._text(annotations.get("created_by")),
                "event_time": notification.start_time,
                "resolved_time": notification.end_time,
                "alert_count": len(payload["alerts"]),
                "truncated_alerts": self._integer(payload.get("truncatedAlerts")),
                "parser_confidence": "high",
                "format": "webhook",
            }
            notifications.append(notification)

        return notifications

    @staticmethod
    def _status(state: str, severity: str) -> str:
        if state == "resolved":
            return "success"
        if severity in {"critical", "error", "failure", "failed"}:
            return "failure"
        if severity in {"warning", "warn"} or state == "firing":
            return "warning"
        return "information"

    @classmethod
    def _category(cls, labels: dict, title: str) -> str:
        text = " ".join(
            cls._text(value)
            for value in (
                labels.get("alert_source"),
                labels.get("alertname"),
                labels.get("summary"),
                title,
            )
        ).casefold()
        if any(marker in text for marker in ("auth", "brute", "security", "tls")):
            return "security"
        if "backup" in text:
            return "backup"
        if any(marker in text for marker in ("environment", "cpu", "memory", "network")):
            return "environment"
        return "administration"

    @classmethod
    def _title(cls, value) -> str:
        text = cls._text(value)
        text = re.sub(r"[_-]+", " ", text)
        text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
        return " ".join(text.split()) or "Portainer alert"

    @staticmethod
    def _integer(value) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _text(value) -> str:
        return "" if value is None else str(value).strip()
