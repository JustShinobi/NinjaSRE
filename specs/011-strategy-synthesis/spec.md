# Feature 011 — Strategy Synthesis

- **Wave:** 2 — Memory & Knowledge
- **Branch:** `feat/011-strategy-synthesis`
- **Status:** Draft
- **Depends on:** 010
- **Blocks:** 028

## Summary

Individual episodes are anecdotes. Strategy synthesis turns N similar episodes
into a **playbook**: common root causes, an effectiveness-ordered investigation
sequence, the capabilities that worked, and — most valuably — **anti-patterns
mined from the episodes that failed**. Playbooks are cached, invalidated when the
underlying episodes change, and measured by ablation like every other learning
mechanism.

## User scenarios

### Primary story

The team has hit Kafka consumer lag five times over three months. Two
investigations went nowhere; three found the cause. When lag appears again, the
agent retrieves a synthesised playbook that names the two common causes, gives the
capability sequence that worked, and explicitly warns that broker metrics were a
dead end in two prior runs.

### Acceptance scenarios

1. **Given** fewer than `MIN_EPISODES_FOR_STRATEGY` similar episodes, **when**
   synthesis is requested, **then** no strategy is generated and the reason is
   recorded.
2. **Given** the threshold is met, **when** synthesis runs, **then** a playbook is
   produced with sections for common root causes, ordered investigation steps,
   effective capabilities, and anti-patterns.
3. **Given** unresolved or low-effectiveness episodes in the input set, **when**
   the playbook is generated, **then** the anti-patterns section is derived
   specifically from them.
4. **Given** a generated strategy, **when** it is requested again with the same
   inputs, **then** the cached version returns without a new LLM call.
5. **Given** a new episode matching an existing strategy's issue type and
   component, **when** it is written, **then** the cached strategy is invalidated
   and regenerated on next request.
6. **Given** a strategy, **when** it is surfaced to the agent, **then** it arrives
   through the memory capability alongside individual episodes, clearly labelled
   as a synthesised playbook rather than a single observation.
7. **Given** the ablation switch disables strategies, **when** investigations run,
   **then** only individual episodes are surfaced and the run is otherwise
   identical.
8. **Given** a team boundary, **when** strategies are retrieved, **then** only that
   team's strategies are visible.
9. **Given** synthesis fails, **when** it happens, **then** individual episode
   recall still works — degradation, not failure.

### Edge cases

- Episodes that are similar by embedding but semantically unrelated.
- A strategy generated from episodes that were all wrong in the same way.
- Component keys that drift (`payments` vs `payments-api` vs `payments-service`).
- A strategy older than the infrastructure it describes.
- All input episodes unresolved — the playbook is entirely anti-patterns.
- Concurrent synthesis requests for the same key.

## Requirements

### Functional

**Synthesis**

- **FR-001** Synthesis MUST require at least `MIN_EPISODES_FOR_STRATEGY` episodes
  sharing issue type and component key.
- **FR-002** A strategy MUST contain four sections: common root causes,
  recommended investigation steps ordered by effectiveness, key capabilities and
  commands that worked, and anti-patterns.
- **FR-003** The anti-patterns section MUST be derived from unresolved and
  low-effectiveness episodes in the input set, and MUST be explicitly labelled as
  such.
- **FR-004** Synthesis MUST be bounded in output length by a named constant so a
  playbook stays usable in context.
- **FR-005** A strategy MUST record its source episode ids, episode count,
  generation timestamp, and the synthesis prompt version.
- **FR-006** Synthesis failure MUST NOT fail retrieval of individual episodes.

**Caching and invalidation**

- **FR-007** Strategies MUST be cached keyed on org, team, issue type, and
  component key.
- **FR-008** A cached strategy MUST be returned without a new LLM call when its
  inputs are unchanged.
- **FR-009** Writing an episode matching a strategy's key MUST invalidate that
  strategy.
- **FR-010** Concurrent synthesis for the same key MUST produce one generation,
  not N.
- **FR-011** A strategy older than `STRATEGY_MAX_AGE_DAYS` MUST be regenerated on
  next request even if not otherwise invalidated.

**Component identity**

- **FR-012** Component keys MUST be normalised so naming variants of the same
  subject group together, using a documented normalisation with an operator-
  configurable alias map.
- **FR-013** Normalisation MUST be conservative: when unsure, keep components
  distinct rather than merging unrelated subjects.

**Delivery**

- **FR-014** Strategies MUST surface through the memory capability alongside
  episodes, labelled distinctly as synthesised.
- **FR-015** A strategy MUST carry its episode count and date range so the agent
  can weigh it.
- **FR-016** Strategies MUST be readable and editable by operators through the
  console (feature 021 wires the UI), with operator edits marked and preserved
  through regeneration.

**Ablation and isolation**

- **FR-017** A team-scoped switch MUST disable strategy synthesis and retrieval
  independently of episodic memory.
- **FR-018** Strategies MUST be scoped by org and team.
- **FR-019** Strategy content MUST pass the guardrail engine before persistence.

### Key entities

| Entity | Description |
|---|---|
| **Strategy** | A cached synthesised playbook for an issue type and component key |
| **StrategyKey** | `(org, team, issue_type, component_key)` |
| **ComponentNormaliser** | Documented normalisation plus operator alias map |
| **SynthesisInput** | The scored episodes feeding one generation |
| **OperatorEdit** | A human amendment preserved across regeneration |

## Success criteria

- **SC-001** A playbook generated from a mixed set (resolved and unresolved)
  contains anti-patterns traceable to the unresolved episodes — verified by a
  fixture with known content.
- **SC-002** Cache hit produces no LLM call, verified by a call counter.
- **SC-003** Writing a matching episode invalidates the strategy; the next request
  regenerates.
- **SC-004** Concurrent requests for the same key produce exactly one generation.
- **SC-005** On a scenario family with prior episodes, strategy availability
  improves scores or reduces iterations measurably versus episodes alone — the
  feature's proof of value.
- **SC-006** With strategies disabled, results match the episodes-only baseline.
- **SC-007** Component normalisation groups known variants and keeps known
  distinct subjects separate — a fixture table asserts both directions.
- **SC-008** Synthesis failure leaves episode recall fully functional.

## Out of scope

- Episodic memory itself (feature 010)
- Operator-authored runbooks (feature 012)
- Strategy editing UI (feature 021)

## Clarifications

| Question | Resolution |
|---|---|
| Why are anti-patterns the most valuable section? | Because they are the only part that cannot be derived from documentation. Runbooks describe what should work; only accumulated failure describes what looked promising and was not. This is the clearest advantage of episodic memory over static knowledge. |
| Could a strategy propagate a systematic error? | Yes — if every input episode was wrong the same way. Mitigated by recording source episode ids so a bad playbook is traceable, by operator editability (FR-016), and by ablation measurement catching aggregate degradation. |
| Why cache rather than synthesise on demand? | Synthesis is an LLM call over several episodes. On the incident critical path that is latency the agent cannot afford, and the inputs change slowly. |
| What happens to operator edits when regeneration occurs? | They are marked and preserved (FR-016). A human correcting a playbook is the highest-quality signal in the system and must not be overwritten by the next generation. |
