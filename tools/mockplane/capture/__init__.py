"""Capture: two sources, one record format, and a report of what was not reached.

The gateway answers what it already serves. The cluster answers the rest, over a
read-only SSH channel — ``pvesh`` for anything its own API covers, a shell for
what no API level reports. Every record carries which of the three produced it.
"""

from __future__ import annotations

__all__: list[str] = []
