"""Real managed services, provisioned, exercised, and destroyed.

This is the only suite in the repository that can cost money, and every design
decision in it follows from that.

**Everything is tagged.** Not for tidiness — the tags are how a resource whose
run is gone gets found. A resource with no run tag is a resource nobody can
attribute, and an account full of those is one nobody dares clean.

**Teardown happens twice, by two mechanisms.** A deferred destroy on the way out
of the run, and a tag sweep that runs on a schedule and knows nothing about any
run. Two, because teardown itself can fail, and the failure mode of "the thing
that cleans up is the thing that broke" is an accumulating bill.

**Every scenario declares what it may cost, and the actual is reported.** A
bound nobody compares against is a comment.

**No credential passes through this process.** The provisioning tool
authenticates itself from the operator's own environment; nothing here reads,
holds, or forwards a secret.
"""

from __future__ import annotations
