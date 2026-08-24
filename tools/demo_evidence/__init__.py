"""Collect, from a live database, the readings a demonstration claims to prove.

Repository tooling. Nothing in the seven runtime packages imports this, and it
imports nothing that would let it write: it takes SQL, refuses everything that
is not one ``SELECT``, hands the statement to a command it was given, and
writes down the query with the answer exactly as it came back.

The point is narrow and worth stating. A demonstration is judged later, by
somebody who was not there, and the only thing that survives the evening is the
file. A count typed from memory under the wrong heading is indistinguishable
from a measurement, which is why the query and the literal answer are stored
together and why the value from before the work is carried beside both.
"""

from __future__ import annotations

from tools.demo_evidence.collector import (
    NOT_COLLECTED,
    OUTPUT_CLOSES,
    OUTPUT_OPENS,
    REFUSAL_CLOSES,
    REFUSAL_OPENS,
    NotASelect,
    Parameters,
    ShellFreeRunner,
    UnusableParameter,
    collect,
    file_name_for,
    only_select,
    plan,
    render,
)
from tools.demo_evidence.queries import STATIONS, Query, Station

__all__ = [
    "NOT_COLLECTED",
    "OUTPUT_CLOSES",
    "OUTPUT_OPENS",
    "REFUSAL_CLOSES",
    "REFUSAL_OPENS",
    "STATIONS",
    "NotASelect",
    "Parameters",
    "Query",
    "ShellFreeRunner",
    "Station",
    "UnusableParameter",
    "collect",
    "file_name_for",
    "only_select",
    "plan",
    "render",
]
