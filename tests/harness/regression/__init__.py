"""Comparing a run against a stored one, and failing a build when it got worse.

A gate on a stochastic system has one failure mode that matters more than all the
others: it goes red on noise, somebody widens the tolerance to make the build
green, and from then on it gates nothing. Every design decision here is aimed at
that.

**A baseline is a file with an identifier.** "Compared to what?" always has an
answer, and the answer survives the shell that produced it.

**A baseline records its corpus.** A scenario added, retired, or re-keyed moves
the corpus version, and comparing across two of them is refused rather than
subtracted — because a fixture change and an agent regression look identical in a
pass rate and mean opposite things.

**A drop has to clear both the tolerance and the variance.** N attempts, the
baseline's own standard deviation, and a drop the baseline itself would have
produced one run in twenty is not a regression.

**Three gates, not one.** Correctness, trajectory, and cost fail separately. A
change that improves accuracy at triple the cost is a real trade-off somebody
should decide on, and one number cannot present it as one.
"""

from __future__ import annotations
