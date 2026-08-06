"""The question capability, and the binding that connects it to a run.

Two modules rather than one because they are read by different people. The
declaration is what a reviewer checks against the catalogue's rules and against
Article IV; the binding is composition-root machinery nobody should have to read
to understand the declaration.
"""

from __future__ import annotations

from capabilities.tools.system.ask_human.tool import TOOL_NAME, ask_human

__all__ = ["TOOL_NAME", "ask_human"]
