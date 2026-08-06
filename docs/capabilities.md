# Capability reference

Generated from the declarations by `tools/generate_capability_docs.py`. Do not
edit by hand — edit the capability and regenerate, or the two will disagree and
this file will be the one that is wrong.

10 tools and 4 skills, 4 of them approval-gated.

## Skills

### `infrastructure`

Working down the stack from workload to node to network, one layer at a time.

- **Domain:** infrastructure

Directs no tools — methodology only.


### `investigate`

The five phases every investigation moves through, and what ends each one.

- **Domain:** methodology

**Directs:**

- `record_hypothesis`
- `assess_evidence_sufficiency`
- `recall_similar_incidents`

### `observability`

Reading logs, metrics, and traces in the order that narrows fastest.

- **Domain:** observability

Directs no tools — methodology only.


### `remediation`

What must be true before acting, and what the action must carry with it.

- **Domain:** remediation

**Directs:**

- `restart_workload`
- `rollback_release`
- `scale_workload`

## Tools

### methodology

#### `assess_evidence_sufficiency`

Judge whether the evidence gathered so far supports a conclusion, and name what kind of evidence is missing if it does not. Use before concluding.

- **Side effect:** `read` — reads only
- **Evidence:** analysis from reasoning
- **Parallel safe:** yes

**Use when:**

- decide whether the evidence gathered so far supports a conclusion
- identify which kind of evidence is missing before concluding

#### `propose_knowledge`

Propose an addition or amendment to the team's knowledge base. The proposal enters a review queue with the investigation that produced it attached, and it does NOT become part of the knowledge base until a human approves it — a later search in this investigation will not find it, and you must not cite it. Use it for something you established with evidence and that a future investigation would want, not for a hypothesis.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** document from knowledge_base
- **Parallel safe:** no
- **Approval:** required — The agent is proposing text for the team's knowledge base. Approving means a human has read the proposed content and the investigation behind it, and accepts it as documentation a future investigation will read and cite.

**Use when:**

- record a symptom-to-cause link this investigation established, for the next one
- propose an amendment to a runbook that turned out to be wrong or incomplete
- capture a diagnostic step that worked and is not written down anywhere

**Not for:**

- recording an unconfirmed hypothesis as though it were established
- restating what a runbook already says
- using this to store notes for the current investigation — it is not readable back

#### `recall_similar_incidents`

Search previous investigations for incidents resembling this one, and return what was concluded, what the cause turned out to be, and which capabilities found it. Where enough similar incidents exist, a synthesised playbook is returned alongside them — common causes, an effective investigation order, and approaches that previously led nowhere. Search on evidence you have gathered — an error string, an exit code, a failing component — not on the alert text.

- **Side effect:** `read` — reads only
- **Evidence:** incident from memory
- **Parallel safe:** yes

**Use when:**

- find previous incidents with the same symptom on the same service
- check whether this alert has fired before and what resolved it
- recall which investigation strategy worked on this class of failure

**Not for:**

- looking up current system state, which a vendor tool reads directly
- searching on the raw alert text before any evidence has been gathered

#### `record_hypothesis`

State a candidate explanation, the evidence that suggests it, and the single next observation that would confirm or eliminate it. Use before gathering more evidence, so the investigation is directed rather than exploratory.

- **Side effect:** `read` — reads only
- **Evidence:** analysis from reasoning
- **Parallel safe:** yes

**Use when:**

- state what you believe is happening before gathering more evidence
- record an explanation you have ruled out, so it is not investigated twice
- commit to the next observation that would distinguish two explanations

**Not for:**

- reporting a conclusion that is already supported by gathered evidence
- narrating what a tool call is about to do

#### `run_analysis_code`

Execute Python over evidence already gathered in this investigation, inside a sandbox with no network and no credentials. Use for arithmetic over large evidence sets, never to reach an external system.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** analysis from sandbox
- **Parallel safe:** no
- **Requires:** analysis

**Use when:**

- correlate timestamps across two evidence sets too large to read directly
- compute a distribution or percentile over gathered metric points
- diff two configuration snapshots field by field

**Not for:**

- calling an external API, which belongs to that vendor's own tool
- running a command against a production system

#### `search_knowledge_base`

Search this team's runbooks, post-mortems, architecture notes, and operational procedures, and return the matching passages with the document and section they came from. Search on concrete symptoms you have observed — an error string, a failing check, an established boundary — not on the alert text. Cite what comes back rather than restating it: a runbook records what was true when somebody wrote it, and where it disagrees with what you have observed, what you observed wins.

- **Side effect:** `read` — reads only
- **Evidence:** document from knowledge_base
- **Parallel safe:** yes

**Use when:**

- find the runbook for a symptom you have already observed
- check whether a documented procedure exists before improvising one
- read the post-mortem of a previous incident with the same signature

**Not for:**

- searching on the raw alert text before any symptom has been established
- looking up current system state, which a vendor tool reads directly
- treating a returned passage as an observation of this incident

### remediation

#### `restart_workload`

Restart a workload's instances. Drops in-flight requests and destroys the process state an investigation may still need, so use only after the cause is established.

- **Side effect:** `write_irreversible` — changes something that cannot be undone
- **Evidence:** change from control_plane
- **Parallel safe:** no
- **Approval:** required — Restarting drops every in-flight request and destroys the process state that would explain the failure. Neither is recoverable.

**Use when:**

- clear a workload stuck in a state a restart resolves, after the cause is known
- recover a service whose connection pool has become unusable

**Not for:**

- restarting before the cause is understood, which destroys the evidence
- restarting a workload whose failure will recur immediately

#### `rollback_release`

Return a workload to a previous release. Reversible by re-deploying the revision it is on now, which the rollback plan records first.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** change from control_plane
- **Parallel safe:** no
- **Approval:** required — Rolling back changes what is running in production. It is reversible, but it moves every user onto different code while it is in effect.

**Use when:**

- return a service to the previous release after a deploy correlates with the alert
- undo a configuration change identified as the trigger

#### `scale_workload`

Change a workload's replica count. Reversible by restoring the count recorded in the rollback plan before the change.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** change from control_plane
- **Parallel safe:** no
- **Approval:** required — Scaling changes capacity and cost, and scaling down can turn a degradation into an outage.

**Use when:**

- add capacity to a workload saturating its current replicas
- reduce a replica count raised during an earlier incident

### topology

#### `query_service_topology`

Return what a service depends on, what depends on it, and the blast radius of an outage at it, from the team's topology graph. Dependencies narrow where the cause can be; dependents are the impact statement. Each result carries when it was last verified, and an unverified dependency is a lead to confirm rather than a fact. Call this once you have identified an affected service — not on the alert text.

- **Side effect:** `read` — reads only
- **Evidence:** topology from knowledge_base
- **Parallel safe:** yes

**Use when:**

- find what an affected service depends on, to narrow where the cause can be
- establish the blast radius of an outage before writing an impact statement
- check whether two services are connected at all before assuming they are

**Not for:**

- querying on the alert text before an affected service has been identified
- reading current health or state, which a vendor tool reads directly
- guessing dependencies from service names when the graph has no record
