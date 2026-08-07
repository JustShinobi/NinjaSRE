"""The demo application, its faults, and the runner that scores an investigation.

The cluster apparatus — the ``Cluster`` port, the validity probe, the cleanup
ledger — is the chaos framework's, reused rather than reimplemented. It is
cluster apparatus rather than fault-specific apparatus, and a second copy would
be a second place for "did the fault actually take effect" to be decided
differently.

What is specific to this suite is where the fault comes from. Chaos Mesh applies
an object to the cluster; the demo's faults are feature flags, which means
injection is a configuration patch and removal is the same patch back. The
consequence worth knowing is that a flag takes a moment to propagate to every
service, which is exactly why the validity probe is not optional here either.
"""

from __future__ import annotations
