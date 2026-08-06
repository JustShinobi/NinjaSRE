# Configuring NinjaSRE

Everything NinjaSRE reads at run time — which prompts, which models, which
capabilities, which integrations, which policy switches — comes from one place:
a tree of configuration nodes with an organisation at the root and your teams
below it. A team's *effective* configuration is the deep merge of its ancestors'
with its own.

This page is for the person who has to answer six questions: how the tree should
be shaped, what merging actually does, how to stop a team weakening something,
what happens when a change needs a second pair of eyes, how to start from a
template, and what to do when a value is not what you expected.

**A fresh deployment needs no configuration at all.** Every field has a default
that ships in the code. Configuration is what a team *changes*, never what makes
the platform start.

## Shaping the tree

One organisation is one tenant and one root. Beneath it, nodes are whatever
grouping your organisation actually has:

```
acme                      the organisation — platform team's defaults
└── platform-division     shared standards for everything under it
    ├── payments          a team
    │   └── checkout      a service
    └── search            a team
```

Four levels is the shape the system is designed and measured against. Twelve is
the hard limit, and a tree approaching it is a modelling problem: every
investigation beneath a node pays for the depth at resolution time.

Two writes the tree refuses:

- **Deleting a node that still has descendants.** Cascading would silently drop
  the configuration of every service beneath a team somebody meant to rename,
  and you would not find out until the next investigation resolved to defaults
  nobody chose. Reparent them, or delete them first.
- **Reparenting a node under its own descendant.** That is a chain with no end.

## What merging does

Root to leaf, each level overriding its ancestors:

| In the parent | In the child | Result |
|---|---|---|
| a section | a section | merged, key by key, recursively |
| anything | a list | the child's list, entirely |
| anything | a scalar | the child's value |
| anything | `null` | `null` — a null is a value, not an absence |
| absent | anything | the child's value |
| anything | absent | the parent's value |

**Lists replace; they do not concatenate.** Merging them would require identity
semantics per list, which means a directive saying which, which means a
configuration language. You can always restate a list. Nobody can restate a
merge rule they cannot see.

**No key is a directive.** A field called `_append` is a field called `_append`.
What a document says is what it does, and what a reviewer read in the pull
request is what the deployment gets.

## What can be configured

Six sections, and only six. Configuration is a closed, typed schema rather than
key-value storage, which is what makes a reference to a capability that does not
exist an error at the write instead of a surprise at three in the morning — and
what lets the console render a credential form without hard-coding a vendor's
fields.

| Section | What it holds |
|---|---|
| `agents` | System prompt overrides per role, sub-agent topology, iteration and tool budgets |
| `models` | Provider and model per role: investigator, sub-agent, intake, diagnose, extraction, embedding |
| `capabilities` | Allow-list, deny-list, disabled tags, per-capability parameters |
| `integrations` | Which integrations are active, the vault entry each one's credential is under, and non-secret settings such as region or site |
| `policies` | Memory, strategy, knowledge, masking, guardrails, and approvals |
| `surfaces` | Chat channels, report destinations, notification sinks |

A key that is not one of those, or a field a section does not declare, is
rejected with the path you wrote it at. That is deliberate: a typo in a field
name is otherwise a setting that is stored, shown in the console, and never
read, and nothing in the system can tell that apart from a field that works.

### Budgets are bounded above by the code

A team may *lower* `agents.max_iterations`. It may not raise it past the
platform ceiling. Every loop bound is a named constant, and a configuration
field that could exceed one would make the constant advisory.

### Configuration never holds a secret

An integration entry names a **vault entry**; it does not carry a key. There is
no `api_key` field and there never will be. On top of that absence, every string
value you submit is scanned by the same rules that scan evidence, and anything
matching a secret shape is refused with a pointer to the vault. The refusal
names the field and never the value.

## Locking, requiring, and gating a field

A node can say three things about a field beyond what its value is.

**Locked.** No descendant may override it. This is how a security team pins the
masking policy or a platform team pins the guardrail ruleset. A write that tries
is refused naming both the field *and* the node that locked it — a constraint
whose origin is invisible is one people route around instead of arguing with.

Adding a lock where a descendant *already* overrides the field is refused too,
listing the descendants. Applying it would change what those teams resolve to,
and you are the one person who could not see that happen. Resolve the overrides
first.

**Required.** Effective configuration missing the field fails validation, naming
it. Not the same as "has a default" — a field with a default is never missing.
Required is for the values only you know.

**Approval-gated.** Changing it enters the approval queue instead of taking
effect. Prompts and capability enablement change how production incidents get
investigated, and that is not a change one person makes alone. The write returns
an approval id; nothing is stored until a human decides.

Constraints accumulate downward and never weaken. A team may add a lock its
parent did not declare, or tighten a ceiling; it cannot remove one.

## Starting from a template

Seven templates ship, each configuring one way of working:

| Template | For |
|---|---|
| `incident-triage-slack` | Pages investigated as they arrive, reported in the on-call channel |
| `ci-failure-investigation` | Failing pipelines against the changes that preceded them |
| `cost-investigation` | Spend changes attributed to what actually changed |
| `postmortem-authoring` | First drafts assembled from the investigation's own trace |
| `alert-fatigue-reduction` | High-volume alerts classified on a short budget |
| `dr-validation` | Scheduled, read-only checks that recovery posture has not drifted |
| `observability-advisory` | Where coverage would leave an investigation unable to answer |

Applying one always produces a **diff first**. Read the overwrites: an addition
is the template doing its job, and an overwrite is it disagreeing with a
decision somebody already made. The diff and the application are the same merge,
so they cannot show you one thing and do another.

A template applies to one node. It obeys locks like any other write.

## When a value is not what you expected

Every value in an effective configuration records the node that supplied it. Ask
for the resolution and read the provenance rather than walking the tree by hand:

```python
effective = await service.resolve("team-payments")
effective.value_at("models.investigator.model")   # 'claude-sonnet-5'
effective.source_of("models.investigator.model")  # 'acme' — set at the org
effective.locked_by("policies.masking.level")     # 'acme' — and pinned there
```

`effective.explain()` returns every path with its value and its source, which is
what the console shows beside a team's configuration.

If a value is not what you set, the three usual answers are: an ancestor locked
it, a descendant overrode it, or the change is still in the approval queue. The
provenance and the lock map answer the first two; the queue answers the third.

## Caching, and when a change takes effect

An investigation resolves configuration **once**, at the start, and everything
it does afterwards reads that one object. Resolving per stage would let a
mid-run change make the first half of an investigation disagree with the second.

Resolutions are cached per node, keyed on the versions of that node's ancestor
chain. A write anywhere in a chain changes the key for every node beneath it, so
**a change at the organisation is visible to every descendant's next
resolution** — including across processes, because the version comes from the
stored row rather than from an in-memory counter. There is nothing to flush and
no interval to wait out.

An investigation already running keeps the configuration it started with. That
is the point.

## Auditing

Every changed field is one audit row: who, when, which node, which field, the
previous value, the new value. One row per *field* rather than per submission,
because "the payments team changed something" is not reviewable and "who has
ever changed the masking policy" has to be answerable.

Two things about the values in those rows:

- **They pass the guardrail rules first.** A value matching a secret shape is
  replaced by a marker naming the rule. The audit table is append-only and
  exempt from every retention sweep, so it is the last place a mistakenly-pasted
  credential should be preserved.
- **A refused write is audited too**, with the field and the reason and *never*
  the value. An attempt to put a credential into configuration is worth knowing
  about; the record of it must not be where the credential survives.

## Two operators editing one node

The second write is refused rather than merged. Re-read, re-apply, and submit
again. Two people editing the same node have made a decision the store is not
entitled to make for them.

---

Credentials themselves are [`integrations.md`](integrations.md). What masking
and the guardrail rules actually do is
[`guardrails-and-masking.md`](guardrails-and-masking.md). The learning switches
under `policies` are explained in [`episodic-memory.md`](episodic-memory.md),
[`strategy-synthesis.md`](strategy-synthesis.md), and
[`topology-and-knowledge.md`](topology-and-knowledge.md).
