# Control — 013 Approvals

The statuses below were verified against the implementation, tests, and the
backend configuration schema. They are not copied from a previous checklist.

| Item | Status |
|---|---|
| 1. Two nearly synonymous inboxes (mutual reference / rename) | DONE — both queues explain their purpose and the approvals queue is named Actions awaiting approval |
| 2. Empty state does not cite the active rule | DONE — reads the canonical field value/default and provenance |
| 3. Duplicate accessibility CTA | DONE — one link is rendered for the navigation action |

The structural merge (Decisions, spec 090) remains planned for wave 4; the
items above are the minimum correction if that merge is delayed.

See [the confrontation report](relatorio-confronto.md) for evidence, code
locations, and verification results.
