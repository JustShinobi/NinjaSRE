"""The cross-vendor tools: everything the agent can call that belongs to no vendor.

Nothing is registered here. Discovery walks this package and takes what it
finds, so a new tool is a new module and no edit to this file — which is what
keeps "adding a capability edits zero existing files" true rather than nearly
true.

Where things go:

* ``system/`` — reasoning, memory, and sandboxed execution. No vendor, always
  available, and the capabilities the per-turn reserve exists to protect.
* ``remediation/`` — the write actions. Cross-vendor by nature, every one above
  ``read_sensitive``, every one approval-gated with a rollback plan.
* ``cross_vendor/`` — a tool that spans several vendors' data rather than
  belonging to any of them.

A tool that reaches exactly one vendor's API belongs in that vendor's
``integrations/<vendor>/tools/`` package, not here.
"""

from __future__ import annotations
