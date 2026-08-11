"""What an agent proposed, waiting for a person — the shape all four origins share.

Deliberately shallow. This package holds the vocabulary and the two invariants
that must hold identically whichever origin a proposal came from; it holds no
applier, because applying one means writing configuration or knowledge, and the
packages that own those must not be imported from below them.

Nothing is re-exported here. A module imports what it needs by name, so
``platform.knowledge`` can take the state enum without dragging in a queue it
never uses — which is also what keeps this package free of a cycle with the
approval layer that supplies its appliers.
"""

from __future__ import annotations

__all__: list[str] = []
