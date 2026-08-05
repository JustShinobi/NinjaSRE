"""Rules with no I/O and no dependency beyond ``config``.

Everything here is a pure function of its arguments: alert normalisation,
incident correlation, and the diagnosis vocabulary. That is what makes this the
one package testable without a single mock, and it is why the stages import
from it rather than growing the rules inside themselves.
"""

from __future__ import annotations
