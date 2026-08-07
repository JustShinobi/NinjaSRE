"""Rendering: what the terminal can show, and the machine-readable shape.

``degradation`` decides what the destination can render, ``tables`` renders for
a human, and ``json_`` renders the documented shape a script reads. Every
command produces the same payload and hands it to one of the last two.
"""

from __future__ import annotations
