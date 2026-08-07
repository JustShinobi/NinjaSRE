"""The mock data plane: a deterministic dataset, and a server that speaks the API.

Repository tooling, not a runtime package. Nothing here is imported by
``config``, ``core``, ``platform``, ``integrations``, ``capabilities``,
``gateway`` or ``surfaces``, and nothing here runs in a deployment. It exists so
the console can be built, reviewed and regression-tested without a backend, a
cluster, a database or a model.

The parts, in the order data moves through them:

``endpoints``
    Every endpoint the console consumes, split into what the gateway serves
    today and what it will serve once the estate, observation and Proxmox work
    lands. The split is data the capture reads, not a comment.
``allowlist``
    The read-only commands the infrastructure capture may run. Extending it is a
    change to a declared file, which is a thing a reviewer sees.
``capture``
    Two sources — the live gateway, and the cluster over SSH — each record
    carrying how it was obtained.
``anonymise``
    The single path into the dataset: keyed pseudonyms, credential removal, a
    timestamp shift that keeps every interval.
``verify``
    The adversarial identifier scan, the secret-pattern net, referential
    integrity, contract validation, plausibility and distribution.
``scenarios``
    The named sets and their per-endpoint overrides.
``server``
    The mock itself, in-process for tests and standalone for development.
"""

from __future__ import annotations

__all__: list[str] = []
