"""One module per axis, and one rule they all obey: score one thing only.

The temptation with a scorer is to give it the run and let it work everything
out. That is what produces a single verdict with a reason string, and a reason
string is not a measurement — you cannot subtract two of them to say what
episodic memory was worth.

So each function here takes the answer key and the *observations it needs*, and
nothing else. A scorer that cannot see the trajectory cannot accidentally let
the trajectory move the accuracy number, which is the property every ablation
figure computed downstream depends on. It also means an axis is testable without
standing up a pipeline, and the tests that prove the axes are independent are
five lines each rather than five scenarios each.
"""

from __future__ import annotations
