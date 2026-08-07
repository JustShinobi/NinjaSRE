"""Reading a vendor's answer without trusting its shape.

Eighty-odd clients parse a JSON document somebody else's service produced, and
each of them wants the same four things: a value several levels down, the list
of records, a cursor as a string, and — for the statistics-first capabilities —
counts of those records grouped by one field.

Written per vendor, each of those is an index expression, and an index
expression is the failure this module exists to prevent. A vendor's error
response has the same content type as its successful one, so
``answer["data"]["results"]`` on a 200-with-a-body-shaped-differently raises a
``KeyError`` inside a capability, which ends the turn and takes the trace with
it. Every reader here answers "nothing" instead, and a capability that reports
nothing is a capability whose empty answer an investigation can still weigh.

``counted`` is the other half of the statistics-first discipline. Where a vendor
aggregates server-side, the client asks it to; where a vendor cannot, the
capability reads one bounded page and groups it here — and says so, because a
distribution over a capped sample and a distribution over everything are
different claims.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any
from xml.etree import ElementTree

#: What a record with no value for the grouping field is counted as. Counted
#: rather than dropped: the total is the number a reader checks the buckets
#: against, and a silently smaller one is a statistic that does not add up.
UNKNOWN_GROUP = "unknown"


def dig(payload: Any, *path: str) -> Any:
    """Return the value at ``path``, or ``None`` if the document does not go there."""
    found: Any = payload
    for key in path:
        if not isinstance(found, Mapping):
            return None
        found = found.get(key)
    return found


def records(payload: Any, *path: str) -> tuple[dict[str, Any], ...]:
    """Return the mappings in the list at ``path``, dropping anything else.

    An empty path reads a document that is itself a list, which is what the
    vendors that answer a collection endpoint with a bare array return.
    """
    found = dig(payload, *path) if path else payload
    if not isinstance(found, Sequence) or isinstance(found, str | bytes):
        return ()
    return tuple(dict(entry) for entry in found if isinstance(entry, Mapping))


def text(payload: Any, *path: str) -> str:
    """Return the value at ``path`` as a string, or ``""`` when there is none.

    Blank for absent, and blank for a null the vendor sent — a pagination walk
    ends on a falsy cursor, and one that stringified ``None`` to ``"None"``
    would ask for the same page until the page bound stopped it.
    """
    found = dig(payload, *path)
    return "" if found is None or found == "" else str(found)


def named(payload: Any, *path: str, key: str = "name") -> tuple[dict[str, Any], ...]:
    """Return a list of bare identifiers as one mapping each.

    Several vendors — the AWS list operations most of all — answer a collection
    endpoint with an array of names or ARNs rather than an array of objects.
    ``records`` drops those, correctly, because a string is not a record. This
    turns them into records so the same capability code counts and reports them,
    and the identifier lands under a field name the grouping can reach.
    """
    found = dig(payload, *path) if path else payload
    if not isinstance(found, Sequence) or isinstance(found, str | bytes):
        return ()
    return tuple({key: str(entry)} for entry in found if isinstance(entry, str | int))


def tabular(
    payload: Any, columns: str, rows: str, *, name: str = "name"
) -> tuple[dict[str, Any], ...]:
    """Return a column-and-row answer as one mapping per row.

    The SQL-shaped vendors answer with the column names once and the values as
    arrays, which is compact on the wire and useless to a capability that wants
    to group by a field. ``columns`` and ``rows`` are dotted paths to the two
    halves, and ``name`` is the key inside a column descriptor that holds its
    name — vendors disagree about that, and it is one word rather than a branch.

    A row longer or shorter than the column list is zipped to the shorter of the
    two rather than raising: a partial record is still evidence, and an exception
    here would end the turn.
    """
    headers = [
        text(column, name) if isinstance(column, Mapping) else str(column)
        for column in (dig(payload, *columns.split(".")) or [])
    ]
    found: list[dict[str, Any]] = []
    for row in dig(payload, *rows.split(".")) or []:
        if isinstance(row, Mapping):
            found.append(dict(row))
        elif isinstance(row, Sequence) and not isinstance(row, str | bytes):
            found.append(dict(zip(headers, row)))
    return tuple(found)


def xml_records(document: str, tag: str) -> tuple[dict[str, Any], ...]:
    """Return one mapping per ``tag`` element in an XML answer.

    A handful of vendors — the AWS query-protocol services among them — answer
    with XML and have no JSON dialect to ask for instead. Rather than give those
    clients a parser each, they get this: the same tuple-of-mappings the JSON
    readers produce, so a capability written against one shape works against the
    other and ``counted`` can group either.

    Namespaces are dropped. A vendor that revises its schema version changes
    every tag's namespace and none of its names, and a client matching on the
    fully qualified name would stop finding anything on a day when nothing about
    the data changed.
    """
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError:
        return ()
    return tuple(_element(found) for found in root.iter() if _tag_of(found) == tag)


def xml_text(document: str, tag: str) -> str:
    """Return the text of the first ``tag`` element, or ``""``.

    What reads a next-page token out of an XML answer. Blank when the element is
    absent, which is how the vendors that page this way say there is no more —
    and a walk handed ``"None"`` instead would ask for the same page again.
    """
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError:
        return ""
    for found in root.iter():
        if _tag_of(found) == tag:
            return (found.text or "").strip()
    return ""


def _tag_of(element: ElementTree.Element) -> str:
    """Return an element's local name, without its namespace."""
    return element.tag.rpartition("}")[2]


def _element(element: ElementTree.Element) -> dict[str, Any]:
    """Return one element as a mapping of its attributes and children."""
    found: dict[str, Any] = {
        name.rpartition("}")[2]: value for name, value in element.attrib.items()
    }
    for child in element:
        name = _tag_of(child)
        found[name] = _element(child) if len(child) else (child.text or "").strip()
    return found


def counted(
    entries: Sequence[Mapping[str, Any]],
    field: str,
) -> tuple[dict[str, Any], ...]:
    """Return ``entries`` counted by ``field``, largest group first.

    ``field`` may be dotted, because the field worth grouping by is usually one
    level down in whatever envelope the vendor wraps a record in.
    """
    path = tuple(part for part in field.split(".") if part)
    tally = Counter(
        text(entry, *path) or UNKNOWN_GROUP if isinstance(entry, Mapping) else UNKNOWN_GROUP
        for entry in entries
    )
    ordered = sorted(tally.items(), key=lambda item: (-item[1], item[0]))
    return tuple({"by": name, "count": count} for name, count in ordered)


def total_of(buckets: Sequence[Mapping[str, Any]]) -> int:
    """Return the sum across ``buckets``, for the one line a finding quotes."""
    return sum(int(bucket.get("count") or 0) for bucket in buckets)


def leader_of(buckets: Sequence[Mapping[str, Any]]) -> str:
    """Return the largest group's name, or ``""`` when nothing was counted."""
    if not buckets:
        return ""
    return str(max(buckets, key=lambda bucket: int(bucket.get("count") or 0)).get("by", ""))


__all__ = [
    "UNKNOWN_GROUP",
    "counted",
    "dig",
    "leader_of",
    "named",
    "records",
    "tabular",
    "text",
    "total_of",
    "xml_records",
    "xml_text",
]
