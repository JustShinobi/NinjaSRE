"""Reading a structured result out of whatever the model actually wrote.

The last resort, and it is here because the alternative is worse. A quantised
local model asked for JSON produces JSON *nearly* every time: inside a fenced
code block, with a sentence in front of it, with a trailing comma, with the
closing brace missing because generation hit the token limit. Refusing all of
those means a no-egress deployment cannot run the stages that need structure,
which is the deployment the whole provider layer exists to make possible.

Everything here is a recovery from a specific, observed malformation. Nothing
guesses at meaning: a repair either produces a document that parses, or it does
not and the next one is tried. The mechanism is recorded on the result, so how
often this fires is a number the evaluation suite watches rather than a surprise.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from config.constants.llm import MAX_STRUCTURED_PARSE_CHARS

_FENCE_PATTERN = re.compile(r"```(?:json|JSON)?\s*(?P<body>.*?)```", re.DOTALL)
_TRAILING_COMMA_PATTERN = re.compile(r",\s*(?P<closer>[}\]])")

#: Openers and their closers, for completing a document generation cut short.
_CLOSERS = {"{": "}", "[": "]"}


def _balanced_document_at(text: str, start: int) -> str | None:
    """Return the balanced document beginning at ``start``, if it closes."""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        character = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in _CLOSERS:
            depth += 1
        elif character in _CLOSERS.values():
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _balanced_documents(text: str) -> list[str]:
    """Return every balanced ``{...}`` or ``[...]`` in ``text``, in order.

    Every one, not the first. A model's prose contains braces for its own
    reasons — a templated placeholder, a code fragment it is describing — and
    stopping at the first balanced run means a well-formed answer two sentences
    later is never seen.

    Scans rather than regexes because a regex cannot count braces.
    """
    found: list[str] = []
    index = 0
    while index < len(text):
        if text[index] not in _CLOSERS:
            index += 1
            continue
        document = _balanced_document_at(text, index)
        if document is None:
            index += 1
            continue
        found.append(document)
        index += len(document)
    return found


def _complete_truncated(text: str) -> str | None:
    """Return ``text`` with unclosed brackets closed, when generation was cut off.

    Only when the imbalance runs one way. Text with more closers than openers is
    not a truncation, it is something else, and inventing an opener would be
    guessing at meaning.
    """
    stack: list[str] = []
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in _CLOSERS:
            stack.append(_CLOSERS[character])
        elif character in _CLOSERS.values():
            if not stack or stack[-1] != character:
                return None
            stack.pop()

    if not stack:
        return None
    completed = text.rstrip().rstrip(",")
    if in_string:
        completed += '"'
    return completed + "".join(reversed(stack))


def _candidates(text: str) -> list[str]:
    """Return the substrings worth attempting, most likely first."""
    attempts: list[str] = []
    stripped = text.strip()
    if stripped:
        attempts.append(stripped)

    for match in _FENCE_PATTERN.finditer(text):
        body = match.group("body").strip()
        if body:
            attempts.append(body)

    attempts.extend(_balanced_documents(text))

    return attempts


def _repairs(candidate: str) -> list[str]:
    """Return ``candidate`` and the repaired forms of it, in order."""
    attempts = [candidate]

    without_trailing_commas = _TRAILING_COMMA_PATTERN.sub(r"\g<closer>", candidate)
    if without_trailing_commas != candidate:
        attempts.append(without_trailing_commas)

    for text in list(attempts):
        completed = _complete_truncated(text)
        if completed:
            attempts.append(completed)

    return attempts


def parse_prose(text: str) -> Mapping[str, Any] | None:
    """Return the JSON object ``text`` contains, or ``None``.

    Only an object is accepted. A bare array or scalar may be valid JSON, but a
    structured-output schema describes an object, and returning something of the
    wrong shape moves the failure to a caller with less context to handle it.
    """
    if not text or len(text) > MAX_STRUCTURED_PARSE_CHARS:
        return None

    for candidate in _candidates(text):
        for attempt in _repairs(candidate):
            try:
                parsed = json.loads(attempt)
            except (ValueError, RecursionError):
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


__all__ = ["parse_prose"]
