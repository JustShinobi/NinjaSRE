"""The sentence that names an investigation, apart from the document it wrote.

Two operations, deliberately kept apart.

``normalize_headline`` cleans up whatever text it is handed — markdown
stripped, collapsed to one line, cut at a word boundary inside the declared
ceiling. It does not care where the text came from; it is used both on a
candidate a model produced and, indirectly, in every test that proves it
reduces a messy string to a clean one.

``synthesize_headline`` is the fallback for a run whose model gave none: a
run from before this feature existed, or one where the model ignored the
instruction. It derives a sentence from the investigation's subject alone —
the alert's name and the resource it named, or the operator's declared
objective when there was no alert — and it has no parameter through which a
document's text could reach it. That is what makes "the synthesised headline
never derives from the document" a property of the function's signature, not
a promise about its body: the regression this module exists to prevent was
exactly a title cut from the document's own opening line.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from config.constants.runs import HEADLINE_MARKER, MAX_HEADLINE_LENGTH

#: Label keys tried, in order, for "the resource this alert named" — there is
#: no one canonical key across the alert sources this product ingests, so the
#: first of these a delivery actually carries wins.
_RESOURCE_LABEL_KEYS: tuple[str, ...] = (
    "resource",
    "resource_id",
    "instance",
    "node",
    "host",
    "pod",
)

#: Markdown syntax stripped from a headline candidate. Heading markers,
#: emphasis, and inline code — the marks a model's prose carries that a title
#: must not.
_HEADING_MARKER = re.compile(r"^\s*#{1,6}\s*")
_EMPHASIS_OR_CODE = re.compile(r"[*_`]+")

#: The line, anywhere in a model's answer, that carries the headline it was
#: asked for. Case-insensitive because a model asked for "Headline:" just as
#: often writes "headline:".
_MARKER_LINE = re.compile(
    rf"^\s*{re.escape(HEADLINE_MARKER)}\s*(?P<candidate>.*)$", re.IGNORECASE | re.MULTILINE
)

#: The fallback sentence when even the subject is empty — an operator-started
#: run with no objective at all is not a case this feature invents evidence
#: for, but it must still hand back a non-empty string (FR-032).
_NO_SUBJECT_HEADLINE = "Investigation with no declared subject"

#: How a headline synthesised from an alert reads.
_FROM_ALERT_AND_RESOURCE = "{alert_name} on {resource}"
_FROM_ALERT_ONLY = "{alert_name}"
_FROM_OBJECTIVE = "{objective}"


def normalize_headline(raw: str) -> str:
    """Return ``raw`` reduced to one clean line, within the declared ceiling.

    Markdown is stripped, every run of whitespace — including newlines
    separating paragraphs — collapses to a single space, and the result is
    cut at the nearest word boundary at or before ``MAX_HEADLINE_LENGTH``. A
    model that answered with three paragraphs and inline emphasis does not
    turn into a three-paragraph title; it turns into this.
    """
    if not raw or not raw.strip():
        return ""

    without_headings = "\n".join(_HEADING_MARKER.sub("", line) for line in raw.splitlines())
    without_marks = _EMPHASIS_OR_CODE.sub("", without_headings)
    collapsed = " ".join(without_marks.split())

    if len(collapsed) <= MAX_HEADLINE_LENGTH:
        return collapsed

    cut = collapsed[:MAX_HEADLINE_LENGTH]
    boundary = cut.rfind(" ")
    return cut[:boundary] if boundary > 0 else cut


def extract_headline(text: str) -> str | None:
    """Return the raw headline candidate a model's answer marked, or ``None``.

    Looks for a line starting with ``Headline:`` (see
    ``config.constants.runs.HEADLINE_MARKER``) anywhere in ``text`` and
    returns everything after the marker on that line, unnormalised — the
    caller runs it through ``normalize_headline``. Returns ``None`` when no
    such line exists, which is the caller's signal to fall back to
    synthesis.
    """
    match = _MARKER_LINE.search(text)
    if match is None:
        return None
    candidate = match.group("candidate").strip()
    return candidate or None


def synthesize_headline(*, alert_name: str = "", resource: str = "", objective: str = "") -> str:
    """Return a deterministic headline derived from the investigation's subject.

    Never reads a document: there is no parameter here through which one
    could arrive. The alert's name and the resource it named come first,
    because they are what the operator already recognises; the declared
    objective is the fallback for a run an operator started directly, with
    no alert behind it.
    """
    alert_name = alert_name.strip()
    resource = resource.strip()
    objective = objective.strip()

    if alert_name and resource:
        return normalize_headline(
            _FROM_ALERT_AND_RESOURCE.format(alert_name=alert_name, resource=resource)
        )
    if alert_name:
        return normalize_headline(_FROM_ALERT_ONLY.format(alert_name=alert_name))
    if objective:
        return normalize_headline(_FROM_OBJECTIVE.format(objective=objective))
    return _NO_SUBJECT_HEADLINE


def headline_for(
    model_text: str, *, alert_name: str = "", resource: str = "", objective: str = ""
) -> str:
    """Return the headline for a concluding answer: extracted, else synthesised.

    The primary path asks the model, through ``extract_headline`` reading
    the marker line it was asked to write. When the model did not provide
    one, the fallback derives a sentence from the subject alone — never by
    reading ``model_text`` itself, which is exactly the distinction that
    keeps this function from reproducing the regression it exists to fix.
    """
    candidate = extract_headline(model_text)
    if candidate:
        return normalize_headline(candidate)
    return synthesize_headline(alert_name=alert_name, resource=resource, objective=objective)


def resource_from_labels(labels: Mapping[str, str]) -> str:
    """Return the resource an alert's labels name, or the empty string.

    Tried in a fixed order because alert sources do not share one key for
    "the thing this fired about" — the first label this delivery actually
    carries, from ``_RESOURCE_LABEL_KEYS``, is what a headline names.
    """
    for key in _RESOURCE_LABEL_KEYS:
        value = labels.get(key, "").strip()
        if value:
            return value
    return ""


__all__ = [
    "extract_headline",
    "headline_for",
    "normalize_headline",
    "resource_from_labels",
    "synthesize_headline",
]
