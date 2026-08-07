# Capability reference

Generated from the declarations by `tools/generate_capability_docs.py`. Do not
edit by hand — edit the capability and regenerate, or the two will disagree and
this file will be the one that is wrong.

21 tools and 7 skills, 8 of them approval-gated.

## Skills

### `cloud_control_plane-kubernetes`

Events before logs, and what shipped before either. Events expire in an hour.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** kubernetes, alertmanager
- **Requires:** kubernetes

**Directs:**

- `kubernetes_workload_events`
- `kubernetes_rollout_history`

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

### `logstore-aws`

CloudWatch logs. Find the group, bound the window, then read.

- **Domain:** logstore
- **Applies to alerts from:** aws, cloudwatch
- **Requires:** aws

**Directs:**

- `aws_list_log_groups`
- `aws_filter_log_events`

### `logstore-datadog`

Datadog log search. Aggregate before sampling, and compare against normal.

- **Domain:** logstore
- **Applies to alerts from:** datadog
- **Requires:** datadog

**Directs:**

- `datadog_log_statistics`
- `datadog_sample_logs`

### `observability`

Reading logs, metrics, and traces in the order that narrows fastest.

- **Domain:** observability

Directs no tools — methodology only.


### `remediation`

What must be true before acting, and what the action must carry with it.

- **Domain:** remediation

**Directs:**

- `restart_workload`
- `rollback_deployment`
- `scale_workload`
- `cordon_drain_node`
- `update_resource_limits`
- `toggle_feature_flag`
- `clear_cache`

## Tools

### cloud_control_plane

#### `kubernetes_rollout_history`

Return a deployment's revisions, newest first, with the image and creation time of each. Answers 'did something ship, and when' in one call — compare the newest revision's time against the symptom's onset. It reports the timeline and does not claim causality.

- **Side effect:** `read` — reads only
- **Evidence:** change from kubernetes
- **Parallel safe:** yes
- **Requires:** kubernetes

**Use when:**

- checking whether a deployment rolled out shortly before a symptom appeared
- finding which image the previous revision ran, to decide what a rollback restores
- establishing that nothing shipped, which rules out a whole class of cause

**Not for:**

- changes that did not go through this deployment — a config map, a feature flag
- why a rollout failed, which the workload's events say and this does not
- the code in a change, which the version-control integration reads

#### `kubernetes_workload_events`

Read Kubernetes events for a namespace, optionally for one object by name. Events carry the reason a pod was killed, evicted, or failed to schedule — the mechanism behind a restart rather than the fact of it. Call this first: events expire in about an hour, so they are the shortest-lived evidence available.

- **Side effect:** `read` — reads only
- **Evidence:** event from kubernetes
- **Parallel safe:** yes
- **Requires:** kubernetes

**Use when:**

- finding why a pod restarted, which the event's reason states outright
- distinguishing an eviction from a crash from a failed image pull
- establishing when a workload's trouble started, from the first warning event

**Not for:**

- reading application output, which is a log question and not an event one
- anything older than the cluster's event retention, typically one hour
- cluster-wide health, where every workload's events at once is noise

### logstore

#### `aws_filter_log_events`

Read CloudWatch log events from one log group between two epoch-millisecond timestamps, optionally narrowed by a CloudWatch filter pattern. Both ends of the window are required. Returns the messages with their timestamps and stream names, and says when more matched than were read.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** log from aws
- **Parallel safe:** yes
- **Requires:** aws

**Use when:**

- reading the error text behind a Lambda or ECS failure in a known window
- checking whether a service logged anything at all during an outage
- finding the first occurrence of an error, to establish onset

**Not for:**

- counting events, which this does expensively and a metric does in one call
- searching every log group at once, which CloudWatch cannot do
- a window wider than the group's retention, which returns nothing either way

#### `aws_list_log_groups`

List CloudWatch log groups in the configured region, optionally narrowed by name prefix. Call it before filtering events when the exact group name is not certain — a query against a mistyped group fails in a way that costs a turn. Returns names, retention, and stored size.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from aws
- **Parallel safe:** yes
- **Requires:** aws

**Use when:**

- confirming a log group's exact name before querying it
- finding which log groups a service writes to when the naming is not obvious
- checking whether a Lambda or ECS task logs anywhere at all

**Not for:**

- reading log content, which filtering events does
- listing every group in a large account with no prefix, which returns noise
- discovering non-logging AWS resources, which this cannot see

#### `datadog_log_statistics`

Count Datadog logs matching a query over a window, grouped by one facet — status, service, host, or any other. Returns the distribution rather than the lines, so it is affordable on a query matching millions. Call this before sampling: the group it singles out is where the samples should come from.

- **Side effect:** `read` — reads only
- **Evidence:** log from datadog
- **Parallel safe:** yes
- **Requires:** datadog

**Use when:**

- an error-rate alert where the failing status, service, or host is not yet known
- establishing whether one thing is failing loudly or everything is failing
- comparing the shape of a window against the equivalent window before the symptom

**Not for:**

- reading a specific error message, which is what sampling is for
- latency across services, which a trace answers and a log count does not
- a question about a single known request, where the count is one

#### `datadog_sample_logs`

Return a small sample of Datadog log lines matching a query in a window, newest first. Use it after the statistics call has singled out a status, service, or host, and narrow the query to that group — a sample from an unnarrowed query is arbitrary. The result says whether more matched than were returned.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** log from datadog
- **Parallel safe:** yes
- **Requires:** datadog

**Use when:**

- reading the actual error message from the group an aggregation singled out
- getting the stack trace behind a spike the counts have already located
- quoting two or three representative lines into a finding

**Not for:**

- an unnarrowed query, where the sample is arbitrary and teaches nothing
- counting anything — the statistics capability answers that in one call
- exporting logs in bulk, which this deliberately cannot do

### methodology

#### `ask_human`

Ask a person something only they can know — whether a change was expected, what a service is meant to do, whether an alert is a known false positive. Give a reason saying what you will do differently depending on the answer, and offer options when the question has a small closed set. You may not ask anyone for a password, key, token, or any other credential; that request is refused. If nobody answers in time you will be told so, and you must then record the gap rather than fill it in.

- **Side effect:** `read` — reads only
- **Evidence:** document from human
- **Parallel safe:** no

**Use when:**

- check whether a deploy, migration, or failover happening now was intended
- confirm what a service is supposed to do when no runbook says
- ask whether an alert is a known false positive during a maintenance window

**Not for:**

- anything another capability could establish by reading the system
- asking for a password, key, token, or any other credential — always refused
- asking a person to run a command on your behalf, which is a remediation

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

#### `clear_cache`

Empty a cache, or one namespace within it. There is no rollback: the entries are gone and only traffic repopulates them, so every miss goes to the origin until it does.

- **Side effect:** `write_irreversible` — changes something that cannot be undone
- **Evidence:** change from control_plane
- **Parallel safe:** no
- **Approval:** required — A cleared cache cannot be restored, and every request that would have hit it goes to the origin until traffic refills it. On a busy service that is a second incident.

**Use when:**

- clear a cache holding a value a deploy has since made wrong
- empty a cache whose corruption is established as the cause

**Not for:**

- clearing a cache to see whether it helps, which is an irreversible experiment
- clearing during peak load, which sends every miss to the origin at once

#### `cordon_drain_node`

Stop a node accepting new work, and optionally evict what is running on it. Reversible by uncordoning; the evicted workloads stay where they rescheduled.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** change from control_plane
- **Parallel safe:** no
- **Approval:** required — Cordoning removes capacity from the pool, and draining moves running workloads. In a pool with little headroom the two together are an outage.

**Use when:**

- take a node with failing hardware out of service before it takes workloads with it
- stop new work landing on a node while its disk pressure is investigated

**Not for:**

- cordoning the last healthy node in a pool, which has nowhere to reschedule to
- draining during a capacity shortage, which moves the outage rather than fixing it

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

#### `rollback_deployment`

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

#### `toggle_feature_flag`

Change a feature flag's value or rollout percentage. Reversible by restoring both, which the rollback plan records before the change.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** change from control_plane
- **Parallel safe:** no
- **Approval:** required — A flag changes behaviour for real users immediately and without a deploy, which is what makes it the fastest mitigation and the easiest to get wrong.

**Use when:**

- turn off a flag whose rollout correlates with the onset of the symptom
- reduce a rollout percentage while the cause is established

**Not for:**

- toggling flags one at a time to see which helps, which is a change per attempt
- turning a flag on as a mitigation, which is a launch nobody reviewed

#### `update_resource_limits`

Change a workload's CPU and memory requests and limits. Reversible by restoring the values recorded in the rollback plan before the change.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** change from control_plane
- **Parallel safe:** no
- **Approval:** required — Changing limits restarts the workload on most control planes, and a limit set below current usage turns a slow degradation into an immediate kill.

**Use when:**

- raise a memory limit for a workload the kernel is killing under normal load
- restore a limit lowered during an earlier cost exercise

**Not for:**

- raising a limit to hide a leak, which delays the failure rather than fixing it
- lowering a limit during an incident, which is a second change nobody asked for

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
