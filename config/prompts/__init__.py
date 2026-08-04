"""Prompt text, as constants.

Prompts live in tier 4 so any tier may read one without creating a cycle: the
investigation stages in ``core/``, the specialist sub-agents, the diagnosis
formatter in ``platform/reporting/``, and the console's preview all reach the
same string.

Convention
----------

One module per prompt domain, named for what it prompts about — ``intake.py``,
``diagnosis.py``, ``memory_recall.py`` — and re-exported here the way
``config.constants`` re-exports its domains.

Within a module:

- A prompt is an ``UPPER_SNAKE_CASE`` ``Final[str]`` module-level constant.
  Text that varies at runtime is a ``str.format`` template with named fields,
  never an f-string built at the call site, so the same text can be read,
  diffed, reviewed, and version-controlled as one artefact.
- Each constant carries a comment naming which stage or sub-agent sends it, and
  the structured output it expects back if any.
- A prompt that asks for structured output names the schema it is paired with.
  The two change together or the change is wrong.

Rules
-----

- **English only** (Constitution Article XIII). A prompt is source.
- **No secrets, no identifiers.** Prompts are templates, not data. Values are
  substituted by the caller, and everything bound for an external provider
  passes through the masking layer first (Article IV, clause 5).
- **No behaviour here.** Selection, composition, and budget-aware truncation
  belong to the module that sends the prompt. This package only holds text.
- Prompts are gated changes: editing one goes through the approval workflow in
  feature 015, which is why they are constants in a reviewable file rather than
  rows in a database.
"""

from __future__ import annotations

__all__: list[str] = []
