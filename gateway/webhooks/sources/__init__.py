"""Per-source webhook profiles: which alert source, and its event identifier.

Normalisation itself is not reimplemented here — ``core.domain.alerts.normalisation``
already has one adapter per vendor (feature 005). Each module in this package
supplies the two things that are specific to *receiving* a webhook rather than
to reading its body: the ``AlertSource`` this endpoint is for, and how to pull
a stable event identifier out of the payload for idempotency (FR-022). Not
every vendor has one; ``event_id_of`` returns the empty string where none
exists, and an empty identifier never counts as a duplicate
(``gateway/webhooks/idempotency.py``).
"""

from __future__ import annotations
