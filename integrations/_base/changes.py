"""A git host's commit listing, as the change record the platform reasons about.

The catalogue speaks to GitHub, and it can list what landed in a repository.
What it cannot do is say what a deployment *applied*, and the difference is why
this is the second change source rather than the first: a commit is a statement
about a repository, and an estate is broken by something that reached it.

So this adapter is deliberately thin and deliberately honest about what it
cannot supply.

**Thin**: the vendor differences are three field maps, because that is genuinely
all they are. Every one of these clients already returns bounded, paginated
records through the proxy, and reimplementing any of that per vendor is how a
catalogue of integrations becomes unmaintainable.

**Honest**: no commit-listing endpoint of the three returns the paths a commit
touched, and a change with no paths cannot be correlated to a component, which
means it cannot be correlated to a resource. The record says so in its detail
rather than carrying an empty tuple that a reader would take for "this commit
touched nothing". A weak correlation reported as weak is useful; the same one
reported as strong is the failure this whole feature exists to prevent.

This lives beside the clients rather than in ``platform/changes/`` because it
imports them, and the platform tier may not. The protocol it satisfies is the
platform's, which is the arrangement the tier table asks for: the tier that owns
the concept names the contract, and the tier with the vendor knowledge satisfies
it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

from config.constants.changes import CHANGES_TOOL_NAME, MAX_CHANGES_PER_WINDOW
from integrations._base.access import current
from integrations._base.client import IntegrationClient
from integrations._base.errors import IntegrationError
from integrations.github.client import GithubClient
from platform.changes.models import Change, ChangeWindow
from platform.changes.screening import screen_all
from platform.observability.logging import get_logger

logger = get_logger(__name__)


class UnsupportedGitHost(ValueError):
    """The configured vendor has no commit listing this adapter can read.

    Raised where the source is built rather than where it is first called. A
    deployment that misconfigured its change source should learn about it at
    composition, not during the first investigation that needed it.
    """


@dataclass(frozen=True, slots=True)
class VendorShape:
    """Where one vendor's commit record puts each field, as dotted paths.

    Several candidates per field rather than one, because these payloads differ
    within a vendor as well as between them — GitLab's listing carries both
    ``title`` and ``message``, and a caller wants the first line of whichever
    arrived.
    """

    client: type[IntegrationClient]
    identifier: tuple[str, ...]
    author: tuple[str, ...]
    instant: tuple[str, ...]
    message: tuple[str, ...]


#: The vendor in the catalogue whose client lists commits. Adding another is a
#: row here and nothing else, which is the property that makes the adapter
#: worth having at all.
GIT_HOST_SHAPES: Final[Mapping[str, VendorShape]] = {
    "github": VendorShape(
        client=GithubClient,
        identifier=("sha",),
        author=("commit.author.name", "author.login"),
        instant=("commit.author.date", "commit.committer.date"),
        message=("commit.message",),
    ),
}

#: The vendor names, for a refusal that says what the alternatives are.
GIT_HOST_VENDORS: Final[tuple[str, ...]] = tuple(sorted(GIT_HOST_SHAPES))

#: Characters of a commit identifier kept. Seven, because that is what every one
#: of these hosts abbreviates to in its own interface, and a change identifier a
#: person cannot match to what their terminal prints is one they cannot follow.
SHORT_IDENTIFIER_CHARS: Final[int] = 7

#: Said on every change from this source, once, so a reader is never left to
#: infer why the correlation was weak.
NO_PATHS_DETAIL: Final = (
    "this vendor's commit listing does not report which files a commit touched, "
    "so this change cannot be correlated to a component"
)


@dataclass(slots=True)
class GitHostChangeSource:
    """One configured git host, answering the platform's window question.

    ``vendor`` is configuration. Nothing above this line knows which one was
    chosen, and the record that comes out is the same shape the apply record
    produces — which is what lets a deployment with no infrastructure repository
    still answer "what changed".
    """

    vendor: str
    repository: str = ""
    name: str = ""
    provides_paths: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if self.vendor not in GIT_HOST_SHAPES:
            raise UnsupportedGitHost(
                f"{self.vendor!r} has no commit listing this adapter reads. The vendors that "
                f"do are {', '.join(GIT_HOST_VENDORS)}."
            )
        if not self.name:
            self.name = f"git:{self.vendor}"

    async def changes_in(
        self,
        window: ChangeWindow,
        *,
        limit: int = MAX_CHANGES_PER_WINDOW,
    ) -> Sequence[Change]:
        """Return the commits this host reports inside ``window``, newest first.

        An empty answer for a deployment that composed no access binding. A
        change source that raised into an investigation because nobody had
        configured a git host would stop the investigation over the absence of
        an optional source.
        """
        access = current()
        if access is None:
            logger.info("changes.git_host_unconfigured", vendor=self.vendor)
            return ()

        shape = GIT_HOST_SHAPES[self.vendor]
        client = access.client(shape.client, capability=CHANGES_TOOL_NAME)
        try:
            found = await self._list(client, limit=limit)
        except IntegrationError as failure:
            logger.warning("changes.git_host_failed", vendor=self.vendor, error=str(failure.reason))
            return ()

        changes = [
            change
            for change in (self._change(record, shape) for record in found)
            if change is not None and window.contains(change.instant)
        ]
        changes.sort(key=lambda change: (change.instant, change.change_id), reverse=True)
        return screen_all(changes[:limit])

    # -- internals -------------------------------------------------------------

    async def _list(self, client: Any, *, limit: int) -> Sequence[Mapping[str, Any]]:
        """Return the raw records the vendor's commit listing returned."""
        pages = await client.list_commits(self.repository, limit=limit)
        return [record for record in pages.items if isinstance(record, dict)]

    def _change(self, record: Mapping[str, Any], shape: VendorShape) -> Change | None:
        """Return one vendor record as a change, or ``None`` when it is not one."""
        identifier = _first(record, shape.identifier)
        instant = _instant(_first(record, shape.instant))
        if not identifier or instant is None:
            # A record with no identifier or no instant is not a change: it
            # cannot be cited and it cannot be placed in a window.
            return None

        return Change(
            change_id=identifier[:SHORT_IDENTIFIER_CHARS],
            occurred_at=instant,
            # The address is dropped where a vendor supplies "name <address>":
            # an investigation needs to know who to ask, and a trace does not
            # need somebody's mailbox.
            author=_first(record, shape.author).split("<", 1)[0].strip(),
            message=_first_line(_first(record, shape.message)),
            paths=(),
            source=self.name,
            detail={"paths": NO_PATHS_DETAIL, "vendor": self.vendor},
        )


def _first(record: Mapping[str, Any], paths: Sequence[str]) -> str:
    """Return the first of ``paths`` that resolves to a non-empty string."""
    for path in paths:
        found: Any = record
        for segment in path.split("."):
            found = found.get(segment) if isinstance(found, Mapping) else None
        if isinstance(found, str) and found.strip():
            return found.strip()
    return ""


def _first_line(message: str) -> str:
    """Return a commit message's subject line, which is what a report quotes."""
    return message.splitlines()[0].strip() if message else ""


def _instant(value: str) -> datetime | None:
    """Return ``value`` as an aware UTC instant, or ``None`` when it is not one."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


__all__ = [
    "GIT_HOST_SHAPES",
    "GIT_HOST_VENDORS",
    "NO_PATHS_DETAIL",
    "SHORT_IDENTIFIER_CHARS",
    "GitHostChangeSource",
    "UnsupportedGitHost",
    "VendorShape",
]
