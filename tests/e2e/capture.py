"""Turning a real failure into a synthetic scenario the fast suite runs for ever.

This is the point of running expensive suites. A chaos experiment or a demo
fault that the agent got wrong is a finding, and a finding that is not written
down is one somebody discovers again next release. So the run's own telemetry
becomes a scenario directory: the fixtures the vendors actually returned, the
alert that actually fired, and a drafted answer key.

Three things about the design are load-bearing.

**Recording happens at the transport, not at the capability.** What gets written
is what the vendor put on the wire — including the fields nobody predicted and
the shapes a hand-written fixture would have simplified away. That is the whole
reason a captured scenario is worth more than one somebody wrote from memory.

**Everything is scrubbed through one mapping.** Scrubbing is not satisfied by
masking each file separately: a namespace masked to one token in the evidence and
another in the transcript would produce a scenario that cannot replay. One
mapping for the whole capture means the URL a matcher holds, the argument the
recorded model turn passes, and the body the vendor returned all agree — so the
scrubbed scenario runs, and runs the same way.

**The answer key is a draft and says so.** A captured scenario's ground truth is
what a human decided about a run, and a file that read like a finished key would
turn an unreviewed guess into the thing every future release is measured
against.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.constants.chaos import (
    CAPTURE_DEFAULT_DIFFICULTY,
    CAPTURE_MAX_EXCHANGES,
    CAPTURE_REVIEW_MARKER,
    CAPTURE_SUITE,
)
from config.constants.evaluation import (
    SCENARIO_ALERT_FILENAME,
    SCENARIO_ANSWER_FILENAME,
    SCENARIO_MANIFEST_FILENAME,
    SCENARIO_SCHEMA_VERSION,
    SCENARIO_TRANSCRIPT_FILENAME,
)
from core.domain.alerts.normalisation import RawAlert
from platform.credentials.proxy.model import OutboundResponse, ProxyRequest
from platform.masking.context import MaskingContext
from platform.masking.detectors import detect
from platform.masking.policy import MaskingLevel, MaskingPolicy
from tests.harness.offline import Transcript
from tests.harness.realruns import RealRunExpectation
from tests.harness.scoring.composite import Observation

#: What a captured scenario is scrubbed at. Strict rather than the deployment
#: default: this is a file that will be committed and read by people who were
#: not on the incident, which is a wider audience than one run's prompt.
CAPTURE_POLICY = MaskingPolicy(level=MaskingLevel.STRICT)


class CaptureError(RuntimeError):
    """A run could not be turned into a scenario."""


@dataclass(frozen=True, slots=True)
class Exchange:
    """One request a capability made and what the vendor answered."""

    integration: str
    method: str
    url: str
    status: int = 200
    content_type: str = "application/json"
    body_text: str = ""
    request_body: str = ""

    @property
    def path(self) -> str:
        """Return the path a recorded fixture matches this exchange by."""
        from urllib.parse import urlsplit

        return urlsplit(self.url).path


@dataclass(slots=True)
class RecordingTransport:
    """A proxy transport with a tap on it.

    Wrapping rather than reimplementing, for the same reason the transcript
    recorder wraps the provider: whatever the real path actually did is what
    lands in the file, including the parts nobody would have thought to record.
    """

    inner: Any
    exchanges: list[Exchange] = field(default_factory=list)
    limit: int = CAPTURE_MAX_EXCHANGES

    async def forward(self, request: ProxyRequest) -> OutboundResponse:
        """Return the vendor's answer to ``request``, keeping the exchange."""
        response: OutboundResponse = await self.inner.forward(request)
        if len(self.exchanges) < self.limit:
            self.exchanges.append(
                Exchange(
                    integration=request.integration,
                    method=request.method,
                    url=request.url,
                    status=response.status_code,
                    content_type=str(response.headers.get("content-type", "application/json")),
                    body_text=response.body.decode("utf-8", errors="replace"),
                    request_body=(request.body or b"").decode("utf-8", errors="replace"),
                )
            )
        return response


@dataclass(frozen=True, slots=True)
class CapturedRun:
    """Everything one real run left behind that a scenario can be made from."""

    expectation: RealRunExpectation
    #: The alert that triggered the run, verbatim. The whole object rather than
    #: its payload, because a captured scenario has to replay from the same
    #: instant: an alert whose ``received_at`` moved would compute a different
    #: incident window and read different evidence.
    alert: RawAlert
    observation: Observation
    exchanges: Sequence[Exchange] = ()
    transcript: Transcript | None = None
    note: str = ""


@dataclass(frozen=True, slots=True)
class CaptureResult:
    """Where the scenario landed, and what still needs a human."""

    directory: Path
    files: tuple[Path, ...] = ()
    identifiers_masked: int = 0
    review: tuple[str, ...] = ()

    @property
    def scenario_id(self) -> str:
        """Return the identifier the captured scenario is filed under."""
        return self.directory.name


def capture(
    run: CapturedRun,
    *,
    root: Path,
    scenario_id: str = "",
    policy: MaskingPolicy = CAPTURE_POLICY,
) -> CaptureResult:
    """Write ``run`` out as a synthetic scenario directory and return where it went.

    Raises:
        CaptureError: the run carries no vendor exchanges, so the scenario it
            would produce could not be investigated by anything.
    """
    if not run.exchanges:
        raise CaptureError(
            "this run recorded no vendor exchanges, so a scenario made from it would offer the "
            "agent nothing to read; capture a run whose transport was recording"
        )

    identifier = scenario_id or run.expectation.scenario_id
    directory = Path(root) / CAPTURE_SUITE / identifier
    directory.mkdir(parents=True, exist_ok=True)

    # One context for the whole capture. Separate contexts per file would issue
    # different tokens for the same identifier, and the scenario would not replay.
    context = MaskingContext(policy=policy)
    written: list[Path] = []

    written.append(
        _write(
            directory / SCENARIO_MANIFEST_FILENAME,
            _manifest(run, identifier=identifier, context=context),
        )
    )
    written.append(_write_json(directory / SCENARIO_ALERT_FILENAME, _alert_document(run, context)))
    for fixture, document in _fixtures(run, context).items():
        written.append(_write_json(directory / fixture, document))
    written.append(_write(directory / SCENARIO_ANSWER_FILENAME, _answer(run, context=context)))
    if run.transcript is not None:
        written.append(
            _write_json(
                directory / SCENARIO_TRANSCRIPT_FILENAME,
                _scrub(run.transcript.to_record(), context),
            )
        )

    return CaptureResult(
        directory=directory,
        files=tuple(written),
        identifiers_masked=len(context.mapping),
        review=_review_notes(run),
    )


def verify_scrubbed(directory: Path, *, policy: MaskingPolicy = CAPTURE_POLICY) -> tuple[str, ...]:
    """Return every identifier still detectable under ``directory``.

    Run before a captured scenario is committed. An empty tuple is the claim
    scrubbing makes; anything in it is a real identifier about to enter version
    control, where deleting it later does not delete it.
    """
    remaining: list[str] = []
    for path in sorted(Path(directory).rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for found in detect(text, policy):
            remaining.append(f"{path.name}: {found.kind.value} {found.value!r}")
    return tuple(sorted(set(remaining)))


# -- what each file is built from ---------------------------------------------


def _manifest(run: CapturedRun, *, identifier: str, context: MaskingContext) -> str:
    """Return the scenario manifest for a captured run."""
    expectation = run.expectation
    integrations = sorted({exchange.integration for exchange in run.exchanges})
    title = context.mask(expectation.title or f"captured from {expectation.key}")
    return "\n".join(
        [
            f"# Captured from a real run of {expectation.key}. Scrubbed before writing;",
            "# the answer key beside this file is a draft and says so.",
            f"schema_version: '{SCENARIO_SCHEMA_VERSION}'",
            f"scenario_id: {identifier}",
            f"title: {title}",
            f"failure_mode: {expectation.failure_mode}",
            f"severity: {expectation.severity}",
            f"scenario_difficulty: {CAPTURE_DEFAULT_DIFFICULTY}",
            "adversarial_signals: []",
            "available_evidence:",
            *(f"- {name}" for name in integrations),
            "integrations:",
            *(f"- {name}" for name in integrations),
            f"team_id: {expectation.team_id}",
            "",
        ]
    )


def _alert_document(run: CapturedRun, context: MaskingContext) -> dict[str, Any]:
    """Return the alert as a scenario fixture holds one."""
    alert = run.alert
    document: dict[str, Any] = {
        "payload": _scrub(dict(alert.payload or {}), context),
        "received_at": alert.at().isoformat(),
    }
    # Only what the alert actually carried. An optional field written as an
    # empty string is a field the fixture validator rejects, and a captured
    # scenario that will not load is worse than one that says less.
    if alert.text.strip():
        document["text"] = context.mask(alert.text)
    if alert.source_hint.strip():
        document["source_hint"] = alert.source_hint
    return document


def _fixtures(run: CapturedRun, context: MaskingContext) -> dict[str, dict[str, Any]]:
    """Return one evidence document per integration the run actually called."""
    documents: dict[str, dict[str, Any]] = {}
    for exchange in run.exchanges:
        document = documents.setdefault(
            f"{exchange.integration}.json",
            {"integration": exchange.integration, "responses": []},
        )
        document["responses"].append(
            {
                "match": {
                    "method": exchange.method.upper(),
                    "path_contains": context.mask(exchange.path),
                },
                "status": exchange.status,
                "content_type": exchange.content_type,
                "body_text": context.mask(exchange.body_text),
            }
        )
    return documents


def _answer(run: CapturedRun, *, context: MaskingContext) -> str:
    """Return the drafted answer key, marked everywhere a human still has to decide."""
    expectation = run.expectation
    said = context.mask(run.observation.answer_text).strip().splitlines()
    lines = [
        f"# {CAPTURE_REVIEW_MARKER}: drafted from a real run the agent got wrong.",
        f"# {CAPTURE_REVIEW_MARKER}: the category and keywords below come from the",
        f"# {CAPTURE_REVIEW_MARKER}: experiment's own declaration, not from anything",
        f"# {CAPTURE_REVIEW_MARKER}: observed. Confirm them against the fixtures before",
        f"# {CAPTURE_REVIEW_MARKER}: this scenario is trusted as ground truth.",
        f"root_cause_category: {expectation.root_cause_category}",
        "required_keywords:",
        *(f"- {keyword}" for keyword in expectation.required_keywords),
    ]
    if expectation.forbidden_categories:
        lines.append("forbidden_categories:")
        lines.extend(f"- {category}" for category in expectation.forbidden_categories)
    if expectation.required_evidence_sources:
        lines.append("required_evidence_sources:")
        lines.extend(f"- {source}" for source in expectation.required_evidence_sources)
    lines.extend(
        [
            f"# {CAPTURE_REVIEW_MARKER}: no golden trajectory is drafted. The run this came",
            f"# {CAPTURE_REVIEW_MARKER}: from was wrong, so the route it took is not one to",
            f"# {CAPTURE_REVIEW_MARKER}: score against.",
            "model_response: |",
            *(f"  {line}" for line in (said or ["the run reached no conclusion"])),
            "",
        ]
    )
    return "\n".join(lines)


def _review_notes(run: CapturedRun) -> tuple[str, ...]:
    """Return what a human has to decide before this scenario is ground truth."""
    notes = [
        "confirm the root cause category and keywords against the captured fixtures",
        (
            "raise the difficulty and declare the confounders: it is drafted at level 1 because "
            "every level above that asserts a planted confounder, and this run's noise was real "
            "rather than planted"
        ),
        "add a golden trajectory once somebody has decided what the right route was",
    ]
    if run.transcript is None:
        notes.append(
            "no transcript was recorded, so this scenario needs a provider to run; record one "
            "to make it part of the offline suite"
        )
    if run.note:
        notes.append(run.note)
    return tuple(notes)


def _scrub(document: Any, context: MaskingContext) -> Any:
    """Return ``document`` with every identifier replaced, structure preserved."""
    if isinstance(document, str):
        return context.mask(document)
    if isinstance(document, Mapping):
        return {context.mask(str(key)): _scrub(value, context) for key, value in document.items()}
    if isinstance(document, list | tuple):
        return [_scrub(item, context) for item in document]
    return document


def _write(path: Path, text: str) -> Path:
    """Write ``text`` to ``path`` and return where it went."""
    path.write_text(text, encoding="utf-8")
    return path


def _write_json(path: Path, document: Any) -> Path:
    """Write ``document`` as JSON to ``path`` and return where it went."""
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


__all__ = [
    "CAPTURE_POLICY",
    "CaptureError",
    "CaptureResult",
    "CapturedRun",
    "Exchange",
    "RecordingTransport",
    "capture",
    "verify_scrubbed",
]
