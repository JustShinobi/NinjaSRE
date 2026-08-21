"""Proving an integration works before an incident needs it to.

Three modules, and the split is by what each answers rather than by size.
``permissions`` says what an integration needs and how one need is probed;
``framework`` runs the probes and assembles a report; ``reporting`` turns the
report into the sentence an operator acts on. Keeping the third separate is
deliberate — the wording *is* the feature here, and a message assembled inline
next to the logic that produced it is a message nobody reviews.
"""

from __future__ import annotations

from integrations._verification.framework import (
    Connectivity,
    IntegrationVerifier,
    VerificationReport,
    VerificationRunner,
    runner_for,
)
from integrations._verification.permissions import (
    PermissionOutcome,
    PermissionProbe,
    ProbeState,
    RequiredPermission,
    client_probe,
)
from integrations._verification.reporting import (
    connectivity_message,
    permission_message,
    report_lines,
    report_message,
)

__all__ = [
    "Connectivity",
    "IntegrationVerifier",
    "PermissionOutcome",
    "PermissionProbe",
    "ProbeState",
    "RequiredPermission",
    "VerificationReport",
    "VerificationRunner",
    "client_probe",
    "connectivity_message",
    "permission_message",
    "report_lines",
    "report_message",
    "runner_for",
]
