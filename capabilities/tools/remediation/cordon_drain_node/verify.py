"""A cordon took effect when the node stopped accepting work."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from capabilities.tools.remediation._base import FieldVerifier
from platform.remediation.models import RemediationAction, StateSnapshot


def intended(action: RemediationAction, before: StateSnapshot) -> Mapping[str, Any]:
    """Return the node state the action intended.

    Schedulability only. Whether the drain finished is a question about the
    workloads rather than about the node, and a verifier that waited for it
    would report a divergence for every eviction still in flight.
    """
    del action, before
    return {"schedulable": False}


verifier = FieldVerifier(intended_of=intended)

__all__ = ["intended", "verifier"]
