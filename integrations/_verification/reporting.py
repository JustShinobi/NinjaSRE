"""Turning a verification result into the sentence somebody acts on.

This module is separate from the framework because the wording *is* the feature.
FR-010 does not ask for a failure to be reported; it asks for the specific
missing permission to be named. The difference between those two is an hour of
somebody's evening, and a message assembled inline beside the logic that
produced it is a message nobody reviews.

Three rules, applied to every line below.

**Name the thing, not the category.** "Missing permission" is a category.
``logs:FilterLogEvents`` is the thing, and it is the string the operator will
paste into their vendor's console.

**Say what stops working.** An operator who does not recognise a permission name
still recognises the capability that needs it. "so acme_log_statistics cannot
run" is what turns a report into a decision about whether to care.

**Say where to fix it.** A permission is granted somewhere specific — an IAM
policy, an application key's scopes, a service account's role binding — and the
verifier knows which. Leaving it out means the operator's next step is a search.

Nothing here ever renders a credential. The inputs cannot carry one — a
``VerificationReport`` holds statuses and vendor prose — and that is the property
that lets this output go to a CLI, a console, and CI without three separate
reviews of what each one is allowed to print.
"""

from __future__ import annotations

from integrations._verification.diagnostics import (
    ClockSkewOutcome,
    DataWindowOutcome,
    EmptyWindow,
    SkewState,
    WindowState,
)
from integrations._verification.framework import Connectivity, VerificationReport
from integrations._verification.permissions import PermissionOutcome, ProbeState


def connectivity_message(integration: str, connectivity: Connectivity) -> str:
    """Return one line on whether ``integration`` reached its vendor."""
    if connectivity.reachable:
        return f"{integration}: the credential works"
    detail = connectivity.detail.strip() or "the vendor did not say why"
    status = f" ({connectivity.status_code})" if connectivity.status_code else ""
    return f"{integration}: could not be used{status} — {detail}"


def permission_message(outcome: PermissionOutcome) -> str:
    """Return one line on what a probe established about one permission."""
    permission = outcome.permission
    affected = (
        f" Without it, {_listed(permission.capabilities)} cannot run."
        if permission.capabilities
        else ""
    )
    where = f" Grant it in {permission.where}." if permission.where else ""

    if outcome.state is ProbeState.GRANTED:
        return f"  granted  {permission.name} — {permission.grants}"
    if outcome.state is ProbeState.DENIED:
        return (
            f"  MISSING  {permission.name} — this credential may not "
            f"{permission.grants}.{affected}{where}"
        )
    if outcome.state is ProbeState.UNCHECKED:
        return (
            f"  unknown  {permission.name} — not checked, because the credential itself "
            f"was rejected first"
        )
    detail = outcome.detail.strip()
    return f"  unknown  {permission.name} — could not be checked" + (
        f": {detail}" if detail else ""
    )


def window_message(outcome: DataWindowOutcome) -> str:
    """Return one line on whether this source is holding anything worth reading.

    The empty case is the one the wording carries. "Returned no data" is a
    status; "answered and holds nothing for the last fifteen minutes — check
    its scrape targets" is the sentence that ends the investigation into why
    verification failed.
    """
    span = f"the last {outcome.window_minutes}m"
    if outcome.state is WindowState.RETURNED:
        return f"  data     {outcome.rows} series or line(s) over {span} — {outcome.description}"
    if outcome.state is WindowState.EMPTY_WINDOW:
        if outcome.empty_means is EmptyWindow.EXPECTED:
            return (
                f"  data     nothing over {span}, and for this source an empty answer is a "
                f"real answer — {outcome.description}"
            )
        return (
            f"  NO DATA  it answered and holds nothing over {span}. {outcome.advice} "
            f"(probed by: {outcome.description})"
        )
    if outcome.state is WindowState.DENIED:
        return f"  NO DATA  the read over {span} was refused — {outcome.detail}"
    if outcome.state is WindowState.UNCHECKED:
        return "  data     not read, because the credential itself was rejected first"
    return f"  data     could not be read over {span}" + (
        f": {outcome.detail}" if outcome.detail.strip() else ""
    )


def clock_message(outcome: ClockSkewOutcome) -> str:
    """Return one line on whether this source's timestamps can be correlated."""
    if outcome.state is SkewState.UNREPORTED:
        return (
            f"  clock    this source does not report its own time, so whether its timestamps "
            f"line up with the platform's is unmeasured — {outcome.description}"
        )
    if outcome.state is SkewState.UNCHECKED:
        return "  clock    not read, because the credential itself was rejected first"

    offset = abs(outcome.offset_seconds or 0.0)
    tolerance = outcome.tolerance_seconds
    if outcome.state is SkewState.IN_TOLERANCE:
        return (
            f"  clock    {offset:.1f}s from the platform's, inside the {tolerance:.1f}s tolerance"
        )
    return (
        f"  SKEWED   {offset:.1f}s from the platform's clock, outside the {tolerance:.1f}s "
        f"correlation tolerates — every timestamp this source contributes is off by that much"
    )


def report_lines(report: VerificationReport) -> tuple[str, ...]:
    """Return the report as the lines a terminal prints, in reading order."""
    lines = [connectivity_message(report.integration, report.connectivity)]
    if report.probe_description.strip():
        lines.append(f"  probe    {report.probe_description}")
    lines.extend(permission_message(outcome) for outcome in report.permissions)
    if report.data_window is not None:
        lines.append(window_message(report.data_window))
    if report.clock is not None:
        lines.append(clock_message(report.clock))

    if report.missing_permissions:
        lines.append(
            f"  {report.integration} is degraded: "
            f"{_listed(report.missing_permissions)} "
            f"{'is' if len(report.missing_permissions) == 1 else 'are'} missing"
        )
    return tuple(lines)


def report_message(report: VerificationReport) -> str:
    """Return the whole report as one printable block."""
    return "\n".join(report_lines(report))


def summary_line(reports: tuple[VerificationReport, ...]) -> str:
    """Return the one line CI prints when everything is fine, or is not."""
    failing = [report.integration for report in reports if not report.ok]
    if not failing:
        return f"{len(reports)} integration(s) verified"
    return f"{len(failing)} of {len(reports)} integration(s) failed: {_listed(tuple(failing))}"


def _listed(names: tuple[str, ...]) -> str:
    """Return ``names`` as prose: "a", "a and b", "a, b, and c"."""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


__all__ = [
    "clock_message",
    "connectivity_message",
    "permission_message",
    "report_lines",
    "report_message",
    "summary_line",
    "window_message",
]
