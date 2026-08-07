"""The interactive session: a stateful REPL over the same core every surface drives.

``loop`` is the session; ``routing`` decides where a typed line goes and is the
single place that decision is made; ``commands/`` is the slash catalogue;
``streaming`` renders the investigation as it happens; ``interaction`` presents
questions and approvals inline; ``session`` is what survives leaving.
"""

from __future__ import annotations
