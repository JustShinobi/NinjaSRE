"""The write actions, and the three things every one of them declares.

Remediation is cross-vendor by nature: restarting a workload, rolling back a
release, and changing a replica count are the same three actions whether the
control plane is Kubernetes, ECS, or a virtual machine fleet. Putting them in
one package rather than in each vendor's is what stops the approval rules being
re-implemented, slightly differently, eighty-five times.

Every tool here is above ``read_sensitive``, and the metadata type enforces
what that means: approval is required, the reason a human is being asked is
written down, and a rollback plan is generated *before* the action rather than
looked for afterwards. That last one is the whole discipline — a plan produced
after the fact is a plan written by whoever is already in trouble.

The execution is a later feature. What lands here is the contract: the
declarations, the planners, and the refusal to act without an approval, so that
approval and rollback are built against a real shape rather than an imagined
one.
"""

from __future__ import annotations
