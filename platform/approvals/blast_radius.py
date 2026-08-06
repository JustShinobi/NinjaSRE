"""Who else this change would reach, computed from the same tree it inherits down.

A reviewer's first question is not "what does this change" but "who does it
change it for". Configuration inherits downward, so a value set at a division
lands on every team beneath it that has not overridden it — and the difference
between "this affects the payments team" and "this affects nineteen teams
including payments" is the difference between an approval somebody grants in
five seconds and one they read first.

**Overriding descendants are excluded and counted separately.** A team that sets
its own value for the path is not affected by an ancestor changing it, and
including them would inflate every blast radius until the number stopped meaning
anything. Counting them separately keeps the reviewer's other question
answerable: "did anybody already disagree with this value?"

**The list is bounded and the count is not.** Above the reporting limit the
nodes are counted rather than named, because a reviewer reads a list of ten
teams and reads "412 teams" the same way whether the list is there or not.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from config.constants.security import MAX_BLAST_RADIUS_NODES_REPORTED
from platform.config_service import paths
from platform.config_service.document import NodeDocument
from platform.config_service.hierarchy import Hierarchy
from platform.persistence.ports import ConfigNode, ConfigNodeKind


@dataclass(frozen=True, slots=True)
class BlastRadius:
    """The nodes and teams one change would reach through inheritance."""

    node_id: str | None
    affected: tuple[str, ...] = field(default_factory=tuple)
    overriding: tuple[str, ...] = field(default_factory=tuple)
    #: How many nodes are affected in total, which is not ``len(affected)``
    #: whenever the list was capped.
    affected_count: int = 0
    teams: tuple[str, ...] = field(default_factory=tuple)
    team_count: int = 0
    truncated: bool = False
    #: Whether the tree was available to compute this against. ``False`` says
    #: "not known", which is a different fact from "nothing beneath it" — and
    #: the difference matters, because the second reads as reassurance.
    known: bool = True

    @property
    def is_local(self) -> bool:
        """Return whether this change reaches nothing but the node it is made at."""
        return self.affected_count == 0

    def describe(self) -> str:
        """Return the sentence shown above the diff, before the reviewer reads it.

        Above, deliberately. The stakes decide how carefully somebody reads the
        diff, and a reviewer who learns the scope after reading it has already
        decided how much attention to spend.
        """
        if not self.known:
            return (
                "The blast radius of this change could not be computed: this organisation's "
                "hierarchy was not readable. Treat its scope as unknown rather than small."
            )
        if self.is_local:
            return f"This affects {self.node_id or 'the organisation'} and nothing beneath it."
        listed = ", ".join(self.teams[:_LISTED_TEAMS])
        more = (
            f" and {self.team_count - _LISTED_TEAMS} more"
            if self.team_count > _LISTED_TEAMS
            else ""
        )
        overridden = (
            f" {len(self.overriding)} node(s) already set their own value and are unaffected."
            if self.overriding
            else ""
        )
        return (
            f"This affects {self.affected_count} node(s) beneath "
            f"{self.node_id or 'the organisation'}, including {self.team_count} team(s): "
            f"{listed}{more}.{overridden}"
        )

    def to_record(self) -> dict[str, Any]:
        """Return the stored form retained beside the decision."""
        return {
            "node_id": self.node_id,
            "affected": list(self.affected),
            "affected_count": self.affected_count,
            "overriding": list(self.overriding),
            "teams": list(self.teams),
            "team_count": self.team_count,
            "truncated": self.truncated,
            "known": self.known,
        }


#: How many team names the one-line description spells out before it counts.
_LISTED_TEAMS = 5


def compute(
    hierarchy: Hierarchy | None,
    node_id: str | None,
    *,
    path: str | None = None,
    limit: int = MAX_BLAST_RADIUS_NODES_REPORTED,
) -> BlastRadius:
    """Return what a change at ``node_id`` would reach.

    ``path`` narrows the answer to the nodes that would actually resolve
    differently. Without it every descendant is affected, which is the honest
    answer for a change whose path is not known — a blast radius that guessed
    narrow would be one a reviewer trusted and should not have.

    Without a hierarchy at all the answer is *unknown*, and says so. Returning
    an empty radius would read as "this affects nothing else", which is the one
    reassurance a reviewer must not be given by an absent input.
    """
    if hierarchy is None:
        return BlastRadius(node_id=node_id, known=False)

    if node_id is None:
        return _organisation_wide(hierarchy, path=path, limit=limit)

    if node_id not in hierarchy.nodes:
        return BlastRadius(node_id=node_id)

    beneath = hierarchy.descendants(node_id)
    return _radius(node_id, beneath, path=path, limit=limit)


def _organisation_wide(hierarchy: Hierarchy, *, path: str | None, limit: int) -> BlastRadius:
    """Return the radius of a change made at the organisation rather than a node."""
    if not hierarchy.nodes:
        return BlastRadius(node_id=None)
    root = hierarchy.root()
    return _radius(None, hierarchy.descendants(root.node_id), path=path, limit=limit)


def _radius(
    node_id: str | None, beneath: Sequence[ConfigNode], *, path: str | None, limit: int
) -> BlastRadius:
    """Return the radius over ``beneath``, splitting overriders out of the affected."""
    affected: list[str] = []
    overriding: list[str] = []
    for node in beneath:
        if path is not None and _overrides(node, path):
            overriding.append(node.node_id)
        else:
            affected.append(node.node_id)

    teams = [
        node.node_id
        for node in beneath
        if node.kind is ConfigNodeKind.TEAM and node.node_id in set(affected)
    ]
    return BlastRadius(
        node_id=node_id,
        affected=tuple(sorted(affected)[:limit]),
        overriding=tuple(sorted(overriding)),
        affected_count=len(affected),
        teams=tuple(sorted(teams)[:limit]),
        team_count=len(teams),
        truncated=len(affected) > limit,
    )


def _overrides(node: ConfigNode, path: str) -> bool:
    """Return whether ``node`` sets its own value for ``path``.

    Prefix-aware in one direction only: a node setting ``policies.masking``
    overrides a change to ``policies.masking.level``, and a node setting
    ``policies.masking.level`` does not shield it from a change to
    ``policies``. Getting that backwards would report a team as unaffected by a
    change that will land on it.
    """
    settings: Mapping[str, Any] = NodeDocument.of_node(node).settings
    return any(known == path or paths.covers(known, path) for known, _ in paths.leaves(settings))


__all__ = ["BlastRadius", "compute"]
