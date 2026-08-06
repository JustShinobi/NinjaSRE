"""Replacing identifiers with tokens, and putting them back.

Both directions are one pass over the string with no re-entry, which matters
for a reason that is easy to miss: replacing left to right while the offsets
were computed against the original text shifts every subsequent span. Building
the result from slices avoids that entirely — there is no second scan and
therefore no chance of masking a token that masking just wrote.

``unmask`` restores only tokens this run issued. A token the model invented is
left exactly as it is, because resolving it to *something* would put a pod name
in a sentence that was never about that pod, and an engineer acting on a report
cannot tell the difference. An unresolved token is visibly wrong; a wrongly
resolved one is invisibly wrong.
"""

from __future__ import annotations

import re

from platform.masking.detectors import detect
from platform.masking.mapping import TOKEN_PATTERN, MaskMapping
from platform.masking.policy import MaskingPolicy


def mask(text: str, *, policy: MaskingPolicy, mapping: MaskMapping) -> str:
    """Return ``text`` with every identifier ``policy`` covers replaced by a token.

    ``mapping`` is updated in place with any identifier seen for the first
    time, so the same call twice produces the same output and allocates
    nothing the second time.
    """
    if not text or not policy.masks_anything:
        return text

    identifiers = detect(text, policy)
    if not identifiers:
        return text

    pieces: list[str] = []
    cursor = 0
    for identifier in identifiers:
        pieces.append(text[cursor : identifier.start])
        pieces.append(mapping.token_for(identifier.label, identifier.value))
        cursor = identifier.end
    pieces.append(text[cursor:])
    return "".join(pieces)


def unmask(text: str, *, mapping: MaskMapping) -> str:
    """Return ``text`` with every token this run issued replaced by its identifier.

    Cheap to call on text that contains no token: the prefix is a literal, so
    the scan fails at the first character of nearly every position.
    """
    if not text or not len(mapping):
        return text

    def restore(match: re.Match[str]) -> str:
        token = match.group(0)
        value = mapping.value_for(token)
        return token if value is None else value

    return TOKEN_PATTERN.sub(restore, text)


__all__ = ["mask", "unmask"]
