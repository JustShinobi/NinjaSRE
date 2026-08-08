"""What failed, why, what to do — and the same answer an hour later.

A bring-up failure is printed to a terminal that, by the time anybody is asked
about it, has scrolled or been closed. So it is also written to the host, and the
console and the CLI read it back. FR-022 is not "produce a good message"; it is
"produce a good message that is still there afterwards", and the second half is
the part that needs a file.

**Every failure carries an action, including the ones nobody wrote a remedy
for.** The startup errors this package defines already say what to do — that is
what they are for. An arbitrary exception does not, and the temptation is to
report it bare. What it gets instead is the honest generic action: run the
self-check, take a support bundle. That is genuinely the next step, and it is
better than a stack trace with no sentence attached.

**The bundle is the one that already exists, with two things added.**
``platform.observability.diagnostics`` collects the version, the configuration
allow-listed by the settings catalogue and scanned value by value, and the recent
logs. What first run adds is the self-check's findings and the schema revision,
which that module has no way to know about. Writing a second bundle here with
its own redaction would be a second thing to get right, and the one that got it
wrong would be the newer one.

**Nothing is transmitted.** The bundle is a file the operator reads and decides
about. Article X, and there is a test asserting this object has no method that
could send it anywhere.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config.constants.first_run import (
    BOOTSTRAP_CREDENTIAL_FILE_MODE,
    BRING_UP_FAILURE_FILENAME,
    NINJASRE_STATE_DIR_ENV,
    SUPPORT_BUNDLE_LOG_LINES,
)
from platform.observability.diagnostics import DiagnosticBundle, build_bundle
from platform.observability.logging import get_logger
from platform.startup.errors import (
    ConfigurationInvalid,
    MigrationFailed,
    SchemaIncompatible,
    StartupError,
)
from platform.startup.selfcheck import SelfCheckReport

logger = get_logger(__name__)

#: What to do about a failure nobody wrote a remedy for. Generic, and honestly
#: so: these two commands are what somebody debugging an unknown startup failure
#: should actually run next.
_GENERIC_ACTION = (
    "run 'ninjasre self-check' to see which dependency this came from, then "
    "'ninjasre support-bundle' and read the result before sharing it"
)


def _state_dir(environ: Mapping[str, str] | None = None) -> Path:
    """Return where host state lives, without importing the bootstrap module.

    Duplicated deliberately rather than imported: ``bootstrap`` imports the
    identity system and the persistence ports, and a diagnostics module that
    could only be loaded once those imported successfully would be unavailable
    for exactly the failures it exists to report.
    """
    from config.constants.first_run import DEFAULT_STATE_DIR

    source = environ if environ is not None else os.environ
    return Path(source.get(NINJASRE_STATE_DIR_ENV) or DEFAULT_STATE_DIR)


@dataclass(frozen=True, slots=True)
class BringUpFailure:
    """One bring-up that did not finish, in the three parts FR-022 requires."""

    stage: str
    problem: str
    action: str
    detail: str = ""
    settings: tuple[str, ...] = ()
    occurred_at: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form written to the host and served."""
        return {
            "stage": self.stage,
            "problem": self.problem,
            "action": self.action,
            "detail": self.detail,
            "settings": list(self.settings),
            "occurred_at": self.occurred_at,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> BringUpFailure:
        """Return the failure a host file describes."""
        return cls(
            stage=str(record.get("stage", "")),
            problem=str(record.get("problem", "")),
            action=str(record.get("action", "")),
            detail=str(record.get("detail", "")),
            settings=tuple(str(name) for name in record.get("settings", ())),
            occurred_at=str(record.get("occurred_at", "")),
        )

    def summary(self) -> str:
        """Return the block a terminal prints and a console renders."""
        lines = [f"Bring-up failed at {self.stage}.", f"  what: {self.problem}"]
        if self.settings:
            lines.append(f"  settings: {', '.join(self.settings)}")
        lines.append(f"  do: {self.action}")
        return "\n".join(lines)


def describe(error: BaseException, *, stage: str) -> BringUpFailure:
    """Return what ``error`` means, as something with an action in it.

    The startup errors carry their own remedy in their message — that is what
    they were written for — so for those the message *is* the problem and the
    action is the specific one their type implies. Everything else gets the
    generic action, which is honest rather than empty.
    """
    problem = str(error) or type(error).__name__
    settings: tuple[str, ...] = ()
    action = _GENERIC_ACTION

    if isinstance(error, ConfigurationInvalid):
        settings = tuple(getattr(error, "settings", ()) or ())
        named = ", ".join(settings) or "the setting named above"
        action = f"correct {named} and start the deployment again; nothing has been changed"
    elif isinstance(error, SchemaIncompatible):
        action = (
            "roll the application forward to the release that migrated this database, or "
            "restore the backup taken before the upgrade — this release will not guess"
            if getattr(error, "ahead", False)
            else "start the deployment with migrations enabled, or run the migration job"
        )
    elif isinstance(error, MigrationFailed):
        action = (
            "fix the cause named above and start again; every revision before the failure "
            "committed, so the run resumes from where it stopped"
        )
    elif isinstance(error, StartupError):
        action = "correct what the message names and start again; nothing has been changed"

    return BringUpFailure(
        stage=stage,
        problem=problem,
        action=action,
        detail=type(error).__name__,
        settings=settings,
        occurred_at=datetime.now(UTC).isoformat(),
    )


def failure_path(environ: Mapping[str, str] | None = None) -> Path:
    """Return where the last bring-up failure is left for later reading."""
    return _state_dir(environ) / BRING_UP_FAILURE_FILENAME


def record_failure(
    error: BaseException, *, stage: str, environ: Mapping[str, str] | None = None
) -> BringUpFailure:
    """Describe ``error``, write it where it can be read again, and return it.

    A write failure here is swallowed. A deployment that could not report why it
    failed to start should still report *that* it failed to start, and raising
    from the reporting path would replace the real cause with a filesystem one.
    """
    failure = describe(error, stage=stage)
    path = failure_path(environ)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(failure.to_record(), indent=2), encoding="utf-8")
    except OSError as write_error:  # pragma: no cover - the host is read-only
        logger.warning("bringup.failure_not_recorded", reason=str(write_error))
    logger.error("bringup.failed", stage=stage, problem=failure.problem)
    return failure


def last_failure(environ: Mapping[str, str] | None = None) -> BringUpFailure | None:
    """Return the last bring-up failure on this host, or ``None`` if it started."""
    try:
        document = json.loads(failure_path(environ).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(document, Mapping):
        return None
    return BringUpFailure.from_record(document)


def forget_failure(environ: Mapping[str, str] | None = None) -> None:
    """Clear the recorded failure. Called on a start that got all the way up."""
    failure_path(environ).unlink(missing_ok=True)


# --- The support bundle ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SupportBundle:
    """What ``build_bundle`` already collects, plus what first run adds to it.

    ``platform.observability.diagnostics`` already produces the hard part — the
    version, the configuration allow-listed by the settings catalogue and
    scanned value by value through the guardrail engine, the recent logs. This
    adds the two things T-030 asks for that it has no way to know about: the
    self-check's findings and the schema this deployment is actually at.

    Composed rather than reimplemented, deliberately. A second bundle with its
    own redaction would be a second thing to get right, and the one that got it
    wrong would be the newer one.

    Deliberately has no method that sends it anywhere. What happens to it is the
    operator's decision (Article X), and the shape of this object is what makes
    that true rather than a policy somebody follows.
    """

    diagnostics: DiagnosticBundle
    schema_revision: str = ""
    self_check: SelfCheckReport | None = None
    failure: BringUpFailure | None = None

    @property
    def version(self) -> str:
        """Return the release this deployment is running."""
        return self.diagnostics.version

    @property
    def logs(self) -> tuple[str, ...]:
        """Return the log lines the bundle carries."""
        return self.diagnostics.logs

    @property
    def settings(self) -> Mapping[str, str]:
        """Return the documented configuration, with every secret already gone."""
        return self.diagnostics.configuration

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form written to the file or served."""
        return {
            **self.diagnostics.to_record(),
            "settings": dict(self.diagnostics.configuration),
            "schema_revision": self.schema_revision,
            "self_check": None if self.self_check is None else self.self_check.to_record(),
            "failure": None if self.failure is None else self.failure.to_record(),
        }

    def render(self) -> str:
        """Return the document a person reads before deciding to share it."""
        lines = [
            self.diagnostics.render(),
            "## Schema",
            "",
            f"- revision: {self.schema_revision}",
            "",
        ]
        if self.failure is not None:
            lines.extend(["## Last bring-up failure", "", self.failure.summary(), ""])
        if self.self_check is not None:
            lines.extend(["## Self-check", "", self.self_check.summary(), ""])
        return "\n".join(lines)

    def write(self, path: Path) -> Path:
        """Write the bundle to ``path``, owner-readable only, and return it.

        Redacted is not the same as harmless: the bundle still carries a node
        inventory and whatever a vendor put in an error message, and it is
        written on a host that may have other people on it.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, BOOTSTRAP_CREDENTIAL_FILE_MODE
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(self.to_record(), handle, indent=2)
        os.chmod(path, BOOTSTRAP_CREDENTIAL_FILE_MODE)
        return path


def support_bundle(
    *,
    environ: Mapping[str, str],
    self_check: SelfCheckReport | None,
    logs: Sequence[str],
    schema_revision: str,
    health: Mapping[str, Any] | None = None,
) -> SupportBundle:
    """Return this deployment's support bundle, in one command's worth of work.

    The log lines are bounded here rather than by the caller. A bundle an
    operator cannot read before sharing is one they share unread, and the last
    five hundred lines are the ones that matter — the first five hundred of a
    container's life are the same every time.
    """
    kept = tuple(logs)[-SUPPORT_BUNDLE_LOG_LINES:]
    return SupportBundle(
        diagnostics=build_bundle(environ=environ, logs=kept, health=health),
        schema_revision=schema_revision,
        self_check=self_check,
        failure=last_failure(environ),
    )


__all__ = [
    "BringUpFailure",
    "SupportBundle",
    "describe",
    "failure_path",
    "forget_failure",
    "last_failure",
    "record_failure",
    "support_bundle",
]
