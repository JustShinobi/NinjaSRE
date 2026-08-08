"""How a demonstration record says so, and how a sweep finds every one of them.

Two labels, and both are columns rather than conventions.

**The tenant.** Every row in this schema carries ``org_id``, so seeding the
demonstration into an organisation of its own labels every record — including
the record kinds a later feature adds, which is the half a per-record stamp can
never cover, because it depends on whoever writes the next seeder remembering.
It is also what makes removal a single operation rather than a sweep of thirteen
ports, and what makes FR-020's refusal structural.

**The field.** Where a record has a structured column of its own — a resource's
``attributes``, a run's ``metadata``, an episode's ``metadata``, an approval's
``arguments``, a topology node's ``properties`` — the label is stamped there
too, so a record exported out of its tenant still says what it is. A prefix on
a name would not survive that, and is a convention the first person to write a
query forgets.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from config.constants.fixtures import DEMONSTRATION_LABEL, DEMONSTRATION_LABEL_FIELD


def labelled(values: Mapping[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    """Return ``values`` carrying the demonstration label."""
    merged: dict[str, Any] = dict(values or {})
    merged.update(extra)
    merged[DEMONSTRATION_LABEL_FIELD] = DEMONSTRATION_LABEL
    return merged


def is_demonstration(values: Mapping[str, Any] | None) -> bool:
    """Return whether this record's structured column marks it as a demonstration."""
    if not values:
        return False
    return values.get(DEMONSTRATION_LABEL_FIELD) is DEMONSTRATION_LABEL


#: The same label where the column is typed ``Mapping[str, str]`` rather than
#: ``Mapping[str, Any]`` — an incident subject's evidence is the only one. A
#: boolean written there would come back as the string anyway on a real store,
#: so it is written as the string deliberately rather than by accident.
DEMONSTRATION_LABEL_TEXT = "true"


def labelled_text(values: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return ``values`` carrying the label, for a string-valued column."""
    merged = dict(values or {})
    merged[DEMONSTRATION_LABEL_FIELD] = DEMONSTRATION_LABEL_TEXT
    return merged


def is_demonstration_text(values: Mapping[str, str] | None) -> bool:
    """Return whether a string-valued column marks this record as a demonstration."""
    if not values:
        return False
    return values.get(DEMONSTRATION_LABEL_FIELD) == DEMONSTRATION_LABEL_TEXT


__all__ = [
    "DEMONSTRATION_LABEL_TEXT",
    "is_demonstration",
    "is_demonstration_text",
    "labelled",
    "labelled_text",
]
