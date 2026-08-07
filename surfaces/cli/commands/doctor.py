"""``ninjasre doctor`` — what is broken, and what to do about each thing.

Every check reports a remedy. A diagnostic that says "provider not configured"
and stops has moved the work rather than done it, and the person reading it at
03:00 is the one who then has to go and find out what that means.

``--bundle`` writes a redacted report the operator can read before deciding to
share it. Redacted here rather than trusted to be safe: the check details carry
endpoints, node identifiers, and error text from vendors, and "it probably has
nothing sensitive in it" is not a claim anybody can make about a vendor's error
message. Nothing is transmitted — the file is written locally and the operator
decides what happens to it (Article X).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import typer

from platform.guardrails.engine import GuardrailEngine
from platform.guardrails.sinks import Sink, SinkGuard
from surfaces.cli.errors import CliError
from surfaces.cli.invocation import Invocation, Output, run_command
from surfaces.cli.models import CheckState, DiagnosticCheck, DiagnosticReport
from surfaces.cli.output.tables import Column, bullet_list, table_of

_COLUMNS = (
    Column("Name", weight=2),
    Column("State", weight=1),
    Column("Detail", weight=4),
    Column("Remedy", weight=4),
)


def _state_glyph(state: CheckState, invocation: Invocation) -> str:
    """Return the glyph one check state is shown with."""
    match state:
        case CheckState.OK:
            return invocation.terminal.glyph("ok")
        case CheckState.WARNING:
            return invocation.terminal.glyph("warning")
        case CheckState.FAILED:
            return invocation.terminal.glyph("failed")
        case _:
            return invocation.terminal.glyph("pending")


def _report_text(report: DiagnosticReport, invocation: Invocation) -> str:
    """Return the human rendering of a diagnostic report."""
    records = [
        {**check.to_record(), "state": f"{_state_glyph(check.state, invocation)} {check.state}"}
        for check in report.checks
    ]
    verdict = (
        f"{invocation.terminal.glyph('ok')} this deployment can investigate"
        if report.healthy
        else f"{invocation.terminal.glyph('failed')} this deployment cannot investigate yet"
    )
    blocks = [
        verdict,
        "",
        table_of(
            records,
            _COLUMNS,
            terminal=invocation.terminal,
            empty="nothing was checked, which is itself a problem",
        ).render(invocation.terminal),
    ]
    if report.failures:
        blocks.extend(
            (
                "",
                "Fix these first",
                bullet_list(
                    [f"{check.name}: {check.remedy or check.detail}" for check in report.failures],
                    terminal=invocation.terminal,
                ),
            )
        )
    return "\n".join(blocks)


def redacted_bundle(
    report: DiagnosticReport,
    checks: Sequence[DiagnosticCheck] | None = None,
    *,
    guard: SinkGuard | None = None,
) -> str:
    """Return the report as a document safe to hand to somebody else.

    Rendered through the report sink rather than the terminal sink: the local
    terminal may show full detail — the person at it is authenticated on the
    host and can read the logs anyway — while anything written down or
    transmitted is filtered. A bundle is written down, and it is written down
    precisely so it can be transmitted.
    """
    boundary = guard or SinkGuard(engine=GuardrailEngine())
    lines = [
        "# NinjaSRE diagnostic bundle",
        "",
        f"version: {report.version}",
        f"healthy: {report.healthy}",
        "",
    ]
    for check in checks if checks is not None else report.checks:
        lines.extend(
            (
                f"## {check.name}",
                f"state: {check.state.value}",
                f"detail: {boundary.render(check.detail, sink=Sink.REPORT)}",
                f"remedy: {boundary.render(check.remedy, sink=Sink.REPORT)}",
                "",
            )
        )
    return "\n".join(lines)


def doctor(
    ctx: typer.Context,
    bundle: Path = typer.Option(
        None,
        "--bundle",
        help="Write a redacted report here for you to review before sharing it.",
    ),
) -> None:
    """Diagnose configuration, connectivity, providers, and integrations."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        report = await invocation.client().diagnose()
        warnings = tuple(f"{check.name}: {check.detail}" for check in report.warnings)

        text = _report_text(report, invocation)
        if bundle is not None:
            try:
                bundle.write_text(redacted_bundle(report), encoding="utf-8")
            except OSError as failure:
                raise CliError(f"could not write {bundle}: {failure}") from failure
            text = f"{text}\n\nredacted bundle written to {bundle} — read it before sharing it"

        return Output(
            command="doctor",
            data=report.to_record(),
            text=text,
            warnings=warnings,
        )

    raise typer.Exit(run_command(invocation, "doctor", body))


__all__ = ["doctor", "redacted_bundle"]
