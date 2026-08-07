"""The alert the injected fault raises, in the shape production's entry point takes.

The pipeline has to be entered where a real alert enters it, and the reason is
narrow and worth stating: an investigation started from a hand-built
objective skips intake's normalisation, its noise verdict, and its component
extraction — three stages that are part of what is being measured. A chaos run
that skipped them would be measuring the loop, not the product.

So the experiment ships an alert document in the vendor's own webhook shape, and
this module fills in what only the run knows: when it fired, which object the
fault was applied to, and which experiment it belongs to. Everything downstream
then behaves exactly as it does for an alert somebody's monitoring sent.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from config.constants.chaos import ALERT_EXPERIMENT_LABEL, ALERT_FAULT_LABEL
from core.domain.alerts.normalisation import RawAlert
from tests.chaos.framework.catalogue import Experiment
from tests.chaos.framework.cleanup import FaultRecord

#: The label carrying the experiment, so a normalised alert can be traced back
#: to the fault that raised it without parsing prose.
EXPERIMENT_LABEL = ALERT_EXPERIMENT_LABEL

#: The label carrying the injected fault's own name.
FAULT_LABEL = ALERT_FAULT_LABEL


def alert_payload(experiment: Experiment, fault: FaultRecord, *, at: datetime) -> dict[str, Any]:
    """Return the webhook payload the fault raises, stamped for this run."""
    document = dict(experiment.alert)
    payload = dict(document.get("payload") or {})
    alerts = [dict(entry) for entry in payload.get("alerts") or ()]

    for entry in alerts:
        labels = dict(entry.get("labels") or {})
        labels[EXPERIMENT_LABEL] = experiment.experiment_id
        labels[FAULT_LABEL] = fault.name
        if fault.namespace:
            labels.setdefault("namespace", fault.namespace)
        entry["labels"] = labels
        entry["startsAt"] = at.isoformat()
        entry.setdefault("status", "firing")

    payload["alerts"] = alerts
    payload.setdefault("status", "firing")
    return payload


def alert_for(experiment: Experiment, fault: FaultRecord, *, at: datetime) -> RawAlert:
    """Return the alert ``experiment``'s fault raises, as the pipeline receives one."""
    payload = alert_payload(experiment, fault, at=at)
    document: Mapping[str, Any] = experiment.alert
    return RawAlert(
        text=str(document.get("text", "")),
        payload=payload,
        source_hint=str(document.get("source_hint", "alertmanager")),
        received_at=at if at.tzinfo is not None else at.replace(tzinfo=UTC),
    )


__all__ = ["EXPERIMENT_LABEL", "FAULT_LABEL", "alert_for", "alert_payload"]
