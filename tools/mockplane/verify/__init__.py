"""Verification: the parts that are allowed to fail the build.

Anonymisation logic will have holes — a free-text field, a URL inside a log
line, a hostname in an error message. The defence is not a more careful
pipeline. It is an adversarial pass over the output that knows the real values,
a second net of secret-shaped patterns, and three structural checks that a
dataset which validates against the contract is also coherent as a history.
"""

from __future__ import annotations

__all__: list[str] = []
