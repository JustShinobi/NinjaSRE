"""Proving an integration works before an incident needs it to.

Four modules, and the split is by what each answers rather than by size.
``permissions`` says what an integration needs and how one need is probed;
``diagnostics`` asks a signal source the two questions a permission check cannot
reach — is there anything in it, and does its clock agree with ours;
``framework`` runs the probes and assembles a report; ``reporting`` turns the
report into the sentence an operator acts on. Keeping the last separate is
deliberate — the wording *is* the feature here, and a message assembled inline
next to the logic that produced it is a message nobody reviews.
"""

from __future__ import annotations

from integrations._verification.diagnostics import (
    ClockSkewOutcome,
    ClockSkewProbe,
    DataWindow,
    DataWindowOutcome,
    DataWindowProbe,
    EmptyWindow,
    SkewState,
    WindowState,
    client_clock_probe,
    client_window_probe,
    http_date,
)
from integrations._verification.framework import (
    Connectivity,
    IntegrationVerifier,
    SignalSourceVerifier,
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
    clock_message,
    connectivity_message,
    permission_message,
    report_lines,
    report_message,
    window_message,
)

__all__ = [
    "ClockSkewOutcome",
    "ClockSkewProbe",
    "Connectivity",
    "DataWindow",
    "DataWindowOutcome",
    "DataWindowProbe",
    "EmptyWindow",
    "IntegrationVerifier",
    "PermissionOutcome",
    "PermissionProbe",
    "ProbeState",
    "RequiredPermission",
    "SignalSourceVerifier",
    "SkewState",
    "VerificationReport",
    "VerificationRunner",
    "WindowState",
    "clock_message",
    "client_clock_probe",
    "client_probe",
    "client_window_probe",
    "connectivity_message",
    "http_date",
    "permission_message",
    "report_lines",
    "report_message",
    "runner_for",
    "window_message",
]
