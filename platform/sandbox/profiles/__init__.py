"""The three implementations of the ``Sandbox`` port.

Nothing here is imported by a caller that wants a sandbox. A caller resolves a
profile (``platform.sandbox.selection``) and is handed one; naming a profile at
a call site is how a deployment ends up with two of them and no way to reason
about which ran.

They are separate subpackages rather than three modules because two of them need
a runtime adapter of their own — a container CLI, a Kubernetes API — and those
adapters have no business being importable from the profile that does not use
them.
"""

from __future__ import annotations

__all__: list[str] = []
