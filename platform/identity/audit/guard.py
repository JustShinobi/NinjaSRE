"""The startup check that no repository has grown a way to edit the audit log.

The port has no mutator and neither backend implements one. That is true today
because somebody wrote it that way, and a property that holds because somebody
wrote it that way stops holding the week somebody else writes it differently —
usually while adding a retention pass, in a hurry, with the best intentions.

So the absence is executable. A deployment runs ``assert_append_only`` at boot,
and a build that grew ``delete_before(cutoff)`` fails to start rather than
running for six months and being discovered during an incident review.

The check is deliberately about *names*, not about behaviour. There is no way to
prove a method does not delete; there is a very easy way to notice that somebody
wrote one whose name says it does, and the cost of the false positive — renaming
a method that genuinely only reads — is a conversation, which is the point.
"""

from __future__ import annotations

import inspect
from typing import Any, Final

from platform.identity.errors import AuditMutationPath

#: Verb prefixes that would make the log editable. Prefixes rather than exact
#: names, so ``delete``, ``delete_before``, and ``deleteAll`` are all caught, and
#: a leading underscore is stripped before the comparison because privacy is a
#: convention and not a boundary.
MUTATING_METHOD_PREFIXES: Final[tuple[str, ...]] = (
    "delete",
    "destroy",
    "drop",
    "edit",
    "erase",
    "expunge",
    "modify",
    "prune",
    "purge",
    "redact",
    "remove",
    "replace",
    "rewrite",
    "truncate",
    "update",
    "upsert",
    "wipe",
)


def mutating_methods(subject: type[Any]) -> tuple[str, ...]:
    """Return the callable names on ``subject`` that would change a record."""
    return tuple(
        sorted(
            name
            for name, _ in inspect.getmembers(subject, callable)
            if not name.startswith("__") and name.lstrip("_").startswith(MUTATING_METHOD_PREFIXES)
        )
    )


def assert_append_only(subject: type[Any]) -> None:
    """Raise ``AuditMutationPath`` if ``subject`` exposes a way to change a record.

    Takes the class rather than an instance so a deployment can run it before it
    has opened a transaction — the point is to fail at boot, and boot is before
    there is a unit of work to get a repository from.
    """
    found = mutating_methods(subject)
    if found:
        raise AuditMutationPath(subject.__name__, found)


__all__ = [
    "MUTATING_METHOD_PREFIXES",
    "AuditMutationPath",
    "assert_append_only",
    "mutating_methods",
]
