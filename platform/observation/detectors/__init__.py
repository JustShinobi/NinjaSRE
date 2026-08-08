"""What is watched for, and how a window becomes a verdict.

``model`` is the declaration: four condition kinds, two durations, a grouping
key, and no expressions. ``conditions`` is the evaluation: pure functions from a
declaration and a window to a verdict, with no state carried between calls.
``registry`` is what an operator holds — the detectors this deployment has,
enabled and disabled, and the dry run that tests one against history without
firing.
"""

from __future__ import annotations
