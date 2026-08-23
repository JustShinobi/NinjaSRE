# Architecture Decision Records

Decisions that shape NinjaSRE and constrain every feature specification. An ADR is
immutable once accepted — a reversal is a new ADR that supersedes it.

| ADR | Title | Status | Constitution articles |
|---|---|---|---|
| [0001](0001-greenfield-with-module-reuse.md) | Greenfield repository with deliberate module reuse | Accepted | VIII, XIII |
| [0002](0002-hybrid-capability-model.md) | Hybrid capability model: skills for methodology, tools for execution | Accepted | IX |
| [0003](0003-single-canonical-runtime.md) | One canonical runtime, SDK adapter experimental only | Accepted | II, V, VI |
| [0004](0004-single-datastore.md) | Single datastore: PostgreSQL with pgvector and Apache AGE | Accepted | X, XI |
| [0005](0005-mandatory-credential-proxy.md) | Credential proxy mandatory in every profile | Accepted | IV |
| [0006](0006-read-only-by-default.md) | Read-only by default, with approval and rollback for writes | Accepted | III |
| [0007](0007-no-external-telemetry.md) | No first-party telemetry | Accepted | X |
| [0008](0008-full-provider-parity.md) | Full parity across all supported LLM providers | Accepted | VI, XII |
| [0009](0009-full-integration-parity.md) | Full parity across all ~85 integrations | Superseded by 0015 | IX, XII |
| [0010](0010-english-only.md) | English-only codebase and documentation | Accepted | XIII |
| [0011](0011-attribution-in-readme-only.md) | Attribution lives in README and NOTICE only | Partly superseded by 0017 | XIII |
| [0012](0012-design-fidelity-expires.md) | A design-fidelity acceptance expires | Accepted | acceptance expiring when its design reference changes |
| [0013](0013-palette-revisions-keep-the-role-vocabulary.md) | A palette revision changes values, never the role vocabulary | Accepted | a palette revision preserving the role vocabulary |
| [0014](0014-a-design-reference-is-committed.md) | A design reference is a committed artefact, and need not be a picture | Accepted | a design reference being a committed, self-contained document |
| [0015](0015-parity-per-embedded-integration.md) | Parity per embedded integration, breadth staged by validatable environment | Accepted | capabilities: parity per embedded integration, breadth staged by validatable environment |
| [0016](0016-composed-or-it-is-not-shipped.md) | Composed or it is not shipped | Accepted | composition and delivery: a merged mechanism is reachable from a serving composition root or declares itself dormant |
| [0017](0017-everything-but-a-credential.md) | The repository carries everything but a credential | Accepted | what may be committed: everything except a secret, so a committed file may link to a specification and a test may read one |

## Writing a new ADR

1. Copy the structure of an existing record: Context → Decision → Rationale →
   Alternatives considered → Consequences (positive, negative, mitigations).
2. Number sequentially. Never renumber.
3. State which constitution articles the decision touches. If it contradicts one,
   the ADR must also amend `.specify/memory/constitution.md` and bump its version.
4. Add a row to this table and to the traceability table in `docs/roadmap.md`.

## Where decisions do *not* belong

- Implementation choices scoped to one feature → that feature's `plan.md`
- Coding conventions → the root `AGENTS.md`
