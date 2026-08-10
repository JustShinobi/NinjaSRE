"""The record of what was actually applied to this cluster, read from the repository.

The most valuable change source and the one that needs no credential. A cluster
driven by ``./infra apply --component <x>`` keeps its own record of every
application: which component, which revision, who ran it, when, and which paths
that revision touched. That record answers the question a commit listing cannot
— *did anybody actually apply this* — and the answer is what separates a change
that broke something from a change that merely happened nearby.

Two things come out of one read, and they are deliberately not two sources.

**The changes**, filtered to a window and ordered newest first. A revision the
record holds with no apply instant is a commit somebody merged and nobody
deployed; it is returned, marked, and never silently promoted to an apply.

**The component map** — what each component manages, as the correlation keys the
estate identifies its resources by. This is the half of "path → component →
workload" that a repository layout cannot tell you: a directory name says which
component owns a file, and only the component's own state says which machines
that component built.

The transport is a directory this deployment can see, which is the same shape
the declared inventory and the documentation corpus already use. Nothing here
executes anything out of the repository, and nothing here needs the repository's
history: an apply record is a fact the tooling wrote down, not something derived
by running ``git``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from config.constants.changes import (
    APPLY_RECORD_SUFFIX,
    INFRA_STATE_ROOT,
    MAX_APPLY_RECORD_BYTES,
    MAX_CHANGES_PER_WINDOW,
    MAX_COMPONENTS,
)
from platform.changes.errors import ChangeStateInvalid
from platform.changes.models import Change, ChangeWindow
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: What this source is called wherever a change's origin is reported. The name
#: an operator would use for it, because it appears in the sentence "the
#: infra-apply record was consulted".
INFRA_APPLY_SOURCE: Final = "infra_apply"

#: The keys one apply entry may carry. Anything else is ignored rather than
#: refused: the tooling that writes these records is free to grow a field
#: without every deployment reading them having to be upgraded first.
_REQUIRED_APPLY_KEYS: Final[tuple[str, ...]] = ("revision", "committed_at")


@dataclass(frozen=True, slots=True)
class ChangeState:
    """Everything one read of a repository's apply record produced.

    Both halves together, because they came from one document and separating
    them would let a caller correlate this hour's changes against last hour's
    component map.
    """

    changes: tuple[Change, ...] = ()
    #: Component name to the correlation keys of what it manages, sorted.
    components: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def in_window(self, window: ChangeWindow, *, limit: int) -> tuple[Change, ...]:
        """Return the changes inside ``window``, newest first, capped at ``limit``."""
        inside = [change for change in self.changes if window.contains(change.instant)]
        inside.sort(key=lambda change: (change.instant, change.change_id), reverse=True)
        return tuple(inside[:limit])


@dataclass(slots=True)
class InfraApplySource:
    """One repository's ``.infra-state`` directory, as changes and components.

    ``root`` is the repository root rather than the state directory, so a
    deployment configures the same path it configures the documentation corpus
    with. A root without the state directory reads as "nothing has been applied
    through this tooling", which is the ordinary condition of a repository and
    not a fault worth stopping an investigation for.
    """

    root: Path
    name: str = INFRA_APPLY_SOURCE
    max_record_bytes: int = MAX_APPLY_RECORD_BYTES
    max_components: int = MAX_COMPONENTS

    async def changes_in(
        self,
        window: ChangeWindow,
        *,
        limit: int = MAX_CHANGES_PER_WINDOW,
    ) -> Sequence[Change]:
        """Return what was applied or committed inside ``window``, newest first."""
        return self.read_state().in_window(window, limit=limit)

    def components(self) -> Mapping[str, tuple[str, ...]]:
        """Return what each component manages, by the estate's correlation keys."""
        return self.read_state().components

    def read_state(self) -> ChangeState:
        """Return the whole apply record, or raise naming every problem in it.

        Raises:
            ChangeStateInvalid: any document is unreadable, is past the byte
                ceiling, or holds an apply entry without the two fields a change
                cannot be placed in time without. Every problem is reported at
                once, each naming its file.
        """
        directory = self.root / INFRA_STATE_ROOT
        if not directory.is_dir():
            return ChangeState()

        problems: list[str] = []
        changes: list[Change] = []
        components: dict[str, tuple[str, ...]] = {}

        # Sorted by name: a filesystem promises no order, and two reads of an
        # unchanged directory have to produce the same answer.
        documents = sorted(
            path for path in directory.iterdir() if path.suffix == APPLY_RECORD_SUFFIX
        )
        if len(documents) > self.max_components:
            problems.append(
                f"{directory} holds {len(documents)} component records, above the "
                f"{self.max_components} one deployment reads, which is MAX_COMPONENTS. A "
                f"directory this size is not one cluster's infrastructure state."
            )
            raise ChangeStateInvalid(problems)

        for path in documents:
            document = self._document(path, problems)
            if document is None:
                continue
            component = str(document.get("component", path.stem)).strip() or path.stem
            components[component] = tuple(
                sorted(
                    str(entry).strip()
                    for entry in _sequence(document.get("manages"))
                    if str(entry).strip()
                )
            )
            changes.extend(
                self._applies(document, component=component, where=path.name, problems=problems)
            )

        if problems:
            raise ChangeStateInvalid(problems)

        logger.info(
            "changes.infra_state_read",
            root=str(self.root),
            components=len(components),
            changes=len(changes),
        )
        return ChangeState(changes=tuple(changes), components=dict(sorted(components.items())))

    # -- internals -------------------------------------------------------------

    def _document(self, path: Path, problems: list[str]) -> Mapping[str, Any] | None:
        """Return one component record, or ``None`` having recorded why not."""
        try:
            size = path.stat().st_size
        except OSError as failure:  # pragma: no cover — listed a moment ago
            problems.append(f"{path.name} could not be read: {failure}")
            return None

        if size > self.max_record_bytes:
            problems.append(
                f"{path.name} is {size} bytes, above the {self.max_record_bytes} one apply "
                f"record may carry, which is MAX_APPLY_RECORD_BYTES. The record arrives from "
                f"a repository this deployment does not control, so its size is not a "
                f"decision this process takes."
            )
            return None

        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as failure:
            problems.append(f"{path.name} is not a readable apply record: {failure}")
            return None

        if not isinstance(loaded, dict):
            problems.append(
                f"{path.name} is a {type(loaded).__name__} at the top level, and an apply "
                f"record is an object with an 'applies' array"
            )
            return None
        return loaded

    def _applies(
        self,
        document: Mapping[str, Any],
        *,
        component: str,
        where: str,
        problems: list[str],
    ) -> list[Change]:
        """Return one component's applies as changes, recording every problem."""
        found: list[Change] = []
        for index, entry in enumerate(_sequence(document.get("applies"))):
            if not isinstance(entry, dict):
                problems.append(f"{where}: applies[{index}] is not an object")
                continue

            missing = [key for key in _REQUIRED_APPLY_KEYS if not str(entry.get(key, "")).strip()]
            if missing:
                problems.append(
                    f"{where}: applies[{index}] declares no {' and no '.join(missing)}, and a "
                    f"change that cannot be identified or placed in time is not one"
                )
                continue

            committed = _instant(entry.get("committed_at"), f"{where}: applies[{index}]", problems)
            if committed is None:
                continue
            applied = (
                _instant(entry.get("applied_at"), f"{where}: applies[{index}]", problems)
                if str(entry.get("applied_at", "")).strip()
                else None
            )

            found.append(
                Change(
                    change_id=str(entry["revision"]).strip(),
                    occurred_at=committed,
                    author=str(entry.get("author", "")).strip(),
                    message=str(entry.get("message", "")).strip(),
                    paths=tuple(
                        sorted(
                            str(path).strip()
                            for path in _sequence(entry.get("paths"))
                            if str(path).strip()
                        )
                    ),
                    source=self.name,
                    component=component,
                    applied_at=applied,
                    detail={"outcome": str(entry.get("outcome", "")).strip()}
                    if str(entry.get("outcome", "")).strip()
                    else {},
                )
            )
        return found


def _sequence(value: Any) -> Sequence[Any]:
    """Return ``value`` as a sequence, or an empty one when it is not a list."""
    return value if isinstance(value, list) else ()


def _instant(value: Any, where: str, problems: list[str]) -> datetime | None:
    """Return ``value`` as an aware UTC instant, or ``None`` having said why not."""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        problems.append(f"{where}: {value!r} is not an ISO 8601 instant")
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


__all__ = ["INFRA_APPLY_SOURCE", "ChangeState", "InfraApplySource"]
