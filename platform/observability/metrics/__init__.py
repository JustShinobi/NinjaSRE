"""Instruments, the bounds on what may label them, and cost attribution.

Three modules and one rule between them: an instrument's label set is declared
where the instrument is, checked when it is written, and bounded in how many
distinct values it may carry. Everything a metric can say about a run has to fit
inside that, and a field that does not fit is not a label.
"""

from __future__ import annotations
