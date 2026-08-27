# Capability reference

Generated from the declarations by `tools/generate_capability_docs.py`. Do not
edit by hand — edit the capability and regenerate, or the two will disagree and
this file will be the one that is wrong.

80 tools and 25 skills, 24 of them approval-gated.

## Skills

### `changes`

Asking what changed before this broke, and refusing to blame a coincidence.

- **Domain:** changes

Directs no tools — methodology only.


### `cicd-argocd`

What Argo CD has actually applied: which applications are synced and healthy, and the ones that are not.

- **Domain:** cicd
- **Applies to alerts from:** argocd
- **Requires:** argocd

**Directs:**

- `argocd_pipeline_statistics`
- `argocd_failed_runs`

### `cloud_control_plane-grafana`

What Grafana knows about a stack: which dashboards and folders exist, and the annotation timeline of deploys, alert state changes, and anything else a human marked.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** grafana
- **Requires:** grafana

**Directs:**

- `grafana_resource_inventory`
- `grafana_recent_changes`

### `cloud_control_plane-kubernetes`

Events before logs, and what shipped before either. Events expire in an hour.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** kubernetes, alertmanager
- **Requires:** kubernetes

**Directs:**

- `kubernetes_workload_events`
- `kubernetes_rollout_history`

### `cloud_control_plane-proxmox`

Quorum before nodes, nodes before guests. A cluster that cannot decide has already answered.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** proxmox, alertmanager, prometheus
- **Requires:** proxmox

**Directs:**

- `proxmox_cluster_health`
- `proxmox_quorum_status`
- `proxmox_corosync_links`
- `proxmox_ha_state`
- `proxmox_clock_skew`

### `cloud_control_plane-proxmox-backup`

A job that names a guest is not a backup, and a file with a size is not a restore.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** proxmox, alertmanager

**Directs:**

- `proxmox_backup_coverage`
- `proxmox_backup_failures`
- `proxmox_protection_gaps`
- `proxmox_replication_lag`

### `cloud_control_plane-proxmox-guest`

Every distinction that changes the remedy is a pair of readings that look alike.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** proxmox, alertmanager

**Directs:**

- `proxmox_guest_start_diagnosis`
- `proxmox_guest_pressure`
- `proxmox_guest_tasks`
- `proxmox_migration_feasibility`

### `cloud_control_plane-proxmox-node-host`

The layer beneath the API, where the outages that no cluster reading can see actually live.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** proxmox, alertmanager

**Directs:**

- `proxmox_cluster_health`
- `proxmox_corosync_links`
- `proxmox_clock_skew`

### `cloud_control_plane-proxmox-storage`

Four levels fail independently and the datastore percentage is the least useful of them.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** proxmox, alertmanager, prometheus

**Directs:**

- `proxmox_storage_pressure`
- `proxmox_zfs_health`
- `proxmox_disk_health`
- `proxmox_reclaimable_space`
- `proxmox_orphaned_volumes`
- `proxmox_datastore_availability`

### `cloud_control_plane-proxmox-two-node`

Two nodes have an even vote count and no majority when one is gone. What survives depends on configuration nobody remembers making.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** proxmox, alertmanager

**Directs:**

- `proxmox_quorum_status`
- `proxmox_corosync_links`
- `proxmox_replication_lag`
- `proxmox_migration_feasibility`

### `communication-pushover`

Pushover as a last-resort notification path: which delivery groups exist, and a finding pushed to a responder's device.

- **Domain:** communication
- **Applies to alerts from:** pushover
- **Requires:** pushover

**Directs:**

- `pushover_recent_messages`
- `pushover_post_message`

### `communication-telegram`

A Telegram chat used as an alerting channel: what has arrived recently, and a finding delivered into it.

- **Domain:** communication
- **Applies to alerts from:** telegram
- **Requires:** telegram

**Directs:**

- `telegram_recent_messages`
- `telegram_post_message`

### `database-redis`

The Redis Cloud control plane: which databases exist in a subscription and in what state, which is what an HTTP-reachable Redis can answer.

- **Domain:** database
- **Applies to alerts from:** redis
- **Requires:** redis

**Directs:**

- `redis_session_statistics`
- `redis_slow_queries`

### `incident-alertmanager`

What Prometheus Alertmanager is currently holding: which alerts are firing, how they are grouped, and which are silenced rather than resolved.

- **Domain:** incident
- **Applies to alerts from:** alertmanager
- **Requires:** alertmanager

**Directs:**

- `alertmanager_incident_statistics`
- `alertmanager_incident_timeline`
- `alertmanager_acknowledge_incident`

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

### `logstore-hermes`

Hermes log tailing and classification: what a stream is currently emitting, grouped by the class its own model assigned.

- **Domain:** logstore
- **Applies to alerts from:** hermes
- **Requires:** hermes

**Directs:**

- `hermes_log_statistics`
- `hermes_sample_logs`

### `logstore-loki`

Log search over Loki's label index and LogQL, with the shape of a query counted before any line of it is read.

- **Domain:** logstore
- **Applies to alerts from:** loki
- **Requires:** loki

**Directs:**

- `loki_log_statistics`
- `loki_sample_logs`

### `logstore-openobserve`

SQL search over OpenObserve streams, counted by field before any record is read, for the estates that chose it for its storage cost.

- **Domain:** logstore
- **Applies to alerts from:** openobserve
- **Requires:** openobserve

**Directs:**

- `openobserve_log_statistics`
- `openobserve_sample_logs`

### `metrics-prometheus`

PromQL evaluation and the alert rules currently firing, from the server that holds the series rather than from a dashboard on top of it.

- **Domain:** metrics
- **Applies to alerts from:** prometheus
- **Requires:** prometheus

**Directs:**

- `prometheus_metric_statistics`
- `prometheus_active_alerts`

### `model-provider-google-gemini`

Whether this deployment's provider key can call the model it is configured for, which is the failure a refusal naming a model hides behind one naming the key.

- **Domain:** model_provider
- **Requires:** google_gemini

**Directs:**

- `google_gemini_available_models`

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

### `tracing-signoz`

SigNoz's span store: where latency and errors concentrate for a service, and the slowest traces behind that concentration.

- **Domain:** tracing
- **Applies to alerts from:** signoz
- **Requires:** signoz

**Directs:**

- `signoz_trace_statistics`
- `signoz_slow_traces`

### `vcs-github`

What landed in a repository and when: the commits on its default branch and the pull requests recently merged into it.

- **Domain:** vcs
- **Applies to alerts from:** github
- **Requires:** github

**Directs:**

- `github_change_statistics`
- `github_recent_changes`

## Tools

### changes

#### `changes_in_window`

Return what changed for a specific resource in a window, correlated through the resource rather than by time: each result says whether the change altered something that manages this resource, touched policy the resource shares, or merely landed in the same window. A change reported as a temporal coincidence is not evidence of a cause. An empty answer is a finding — it states that nothing touched this resource, and names what was consulted to establish it. Call this once you know which resource is affected, not on the alert text.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** change from change_history
- **Parallel safe:** yes

**Use when:**

- checking whether anything was deployed shortly before a symptom started
- ruling deploys out, so an investigation stops looking at them and looks elsewhere
- finding which apply touched the component that manages an affected workload

**Not for:**

- asking on the alert text before an affected resource has been identified
- reading what a change contained, which this deliberately never reports
- listing a repository's history, which is a report rather than an investigation

### cicd

#### `argocd_failed_runs`

Return the failed runs for a project in a window, newest first and capped, with the stage that failed. Use it after the statistics: the first failure in a run of them is the one worth reading.

- **Side effect:** `read` — reads only
- **Evidence:** event from argocd
- **Parallel safe:** yes
- **Requires:** argocd

**Use when:**

- finding the first failing run after a period of green ones
- checking whether a deployment succeeded before blaming the release

**Not for:**

- whether failures are unusual, which the statistics answer
- an application error unrelated to any build

#### `argocd_pipeline_statistics`

Count the pipeline runs for a project in a window, grouped by outcome. It says whether a failure is new, chronic, or the first of its kind, which decides whether the pipeline is the story at all.

- **Side effect:** `read` — reads only
- **Evidence:** event from argocd
- **Parallel safe:** yes
- **Requires:** argocd

**Use when:**

- an incident following a deployment whose history is unknown
- deciding whether a red build is new or has been red for a week

**Not for:**

- why one run failed, which needs that run rather than a count
- a runtime failure with no build in the window

### cloud_control_plane

#### `grafana_recent_changes`

Return the control-plane changes in a window, newest first and capped. Most incidents follow a change, and this is the capability that turns 'it started at 14:05' into a specific thing somebody did.

- **Side effect:** `read` — reads only
- **Evidence:** change from grafana
- **Parallel safe:** yes
- **Requires:** grafana

**Use when:**

- an incident whose start time is known and whose cause is not
- checking whether anything was changed shortly before the symptom

**Not for:**

- how much of the estate is affected, which the inventory answers
- a symptom with no change window, where the history is noise

#### `grafana_resource_inventory`

List the resources of one kind, grouped by state, so the answer is the distribution rather than every resource. Reach for it when the question is how much of the estate is in a bad state rather than which one is.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from grafana
- **Parallel safe:** yes
- **Requires:** grafana

**Use when:**

- an alert naming a service whose current state is unknown
- establishing whether a failure is one resource or a whole class of them

**Not for:**

- why a resource changed, which the change history answers
- application-level errors, which a control plane never sees

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

#### `proxmox_backup_coverage`

Return which Proxmox guests an *enabled* backup job covers, each guest's last successful backup with its age and size, and the retention depth of every job. A job that exists and is switched off satisfies every coverage count and protects nothing; two retained copies and thirty read identically without the depth.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- finding which guests no enabled backup job covers, as opposed to which are named by one
- checking how many copies a job actually retains before trusting it as history
- reading each guest's last successful backup with its age and size, not its job membership

**Not for:**

- running a backup or enabling a job — nothing here writes
- why a backup failed, which proxmox_backup_failures reads with the vendor's error
- whether a Backup Server snapshot was verified, which the Backup Server answers

#### `proxmox_backup_failures`

Return the Proxmox backup tasks that failed, each with the vendor's own error text, and — separately — the guests whose every attempt has failed. A guest that failed last night and succeeded the night before has a backup; a guest with nothing but failures has never had one, and both are one row in a list of failures.

- **Side effect:** `read` — reads only
- **Evidence:** event from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- reading why a backup failed, in the words Proxmox used rather than a category
- finding the guests whose every backup attempt has failed, which a failure list hides
- checking whether a backup window failed as a whole or one guest inside it did

**Not for:**

- re-running a backup — nothing here writes
- which guests no job covers, which proxmox_backup_coverage answers
- whether a stored backup would restore, which the Backup Server's verification answers

#### `proxmox_clock_skew`

Return each Proxmox node's clock and how far apart they are, measured against what corosync tolerates rather than against what looks close to a person. Two nodes a minute apart present as random link failures and unmigratable guests, and nothing in those symptoms mentions time.

- **Side effect:** `read` — reads only
- **Evidence:** metric from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- checking clock agreement across a cluster whose corosync membership keeps changing
- ruling time out before investigating link failures that have no physical cause
- finding a node whose NTP has stopped without anything reporting a failure

**Not for:**

- setting a clock or restarting a time daemon — nothing here writes
- corosync link behaviour, which proxmox_corosync_links reads
- whether the cluster is quorate, which proxmox_quorum_status answers

#### `proxmox_cluster_health`

Return a Proxmox cluster's quorum state, its vote arithmetic, and which nodes are answering. Reports the quorum margin — how many votes can be lost before the cluster stops being able to decide anything — which on a two-node cluster is usually zero even when everything is green.

- **Side effect:** `read` — reads only
- **Evidence:** metric from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- establishing whether the cluster can start, stop or migrate anything at all
- finding out how many node failures the cluster survives before it stops deciding
- checking whether a quorum device that is configured is actually contributing a vote

**Not for:**

- why one guest is unhealthy, which is a guest question and this does not answer
- how full a datastore is, which proxmox_storage_pressure reads
- changing anything about the cluster — nothing here writes

#### `proxmox_corosync_links`

Return each corosync link's recent behaviour: how many times it changed state, whether it is flapping or was simply lost, which nodes declare it, and how many knet retransmits the cluster logged. A link that went down and came back is healthy now and is the most urgent thing on the cluster; a link that went down once and stayed down is usually an address that no longer exists.

- **Side effect:** `read` — reads only
- **Evidence:** event from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- telling a corosync link that is flapping from one that is simply gone
- finding a corosync ring that only one node declares and therefore can never come up
- counting knet retransmits on a cluster whose membership keeps changing

**Not for:**

- whether the cluster currently has quorum, which proxmox_quorum_status answers
- a node's own interface configuration, which is a host-layer reading
- restarting corosync or editing its configuration — nothing here writes

#### `proxmox_datastore_availability`

Return which datastores each Proxmox node is declared for and which it can currently reach, keeping the two apart. A datastore reporting unknown is a mount that failed, not an empty share and not a fill level, and a guest cannot move to a node its disk's datastore is not declared on however healthy both nodes are.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- checking whether a guest could move to a node before proposing that it does
- finding a datastore reporting unknown, which is a failed mount rather than an empty share
- seeing which datastores are node-local and therefore pin the guests on them in place

**Not for:**

- mounting a datastore or changing its node restriction — nothing here writes
- how full each datastore is, which proxmox_storage_pressure reads
- whether a particular guest can migrate, which proxmox_migration_feasibility answers

#### `proxmox_disk_health`

Return each physical disk's SMART verdict, the attributes that predict a failure before the verdict changes, and which ZFS pool it backs. A drive reporting PASSED with a climbing reallocated-sector count is the ordinary way a disk fails, and the verdict is the last field to move.

- **Side effect:** `read` — reads only
- **Evidence:** metric from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- finding a drive whose SMART verdict still passes while its pending sectors climb
- checking which pool or datastore a failing disk is underneath before planning anything
- reading the wear indicator on solid-state drives that back a hypervisor's guests

**Not for:**

- replacing a disk or starting a self-test — nothing here writes
- how full a datastore is, which proxmox_storage_pressure reads
- ZFS pool state, which proxmox_zfs_health reads

#### `proxmox_guest_pressure`

Return where the pressure on a Proxmox guest is: host memory against guest memory, the node's swap, ballooning, and the guest's own filesystems against the datastores its disks are on — with the attribution stated. A stalling guest looks the same whether the cause is inside it or underneath it, and the two are fixed on different machines. CPU steal is named as unreadable rather than omitted.

- **Side effect:** `read` — reads only
- **Evidence:** analysis from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- telling host memory pressure from a guest that is at its own memory ceiling
- telling a guest filesystem that is full from a host datastore that is full
- checking what a guest agent reports about the guest's own disks before blaming the host

**Not for:**

- resizing a guest's memory or its disk — nothing here writes
- why a stopped guest will not start, which proxmox_guest_start_diagnosis answers
- cluster-wide storage pressure, which proxmox_storage_pressure reads per node

#### `proxmox_guest_start_diagnosis`

Return why a Proxmox guest will not start: its lock and whether the task holding it is alive or dead, the errors from its recent failed tasks, the datastores its disks need and whether this node reaches them, the node's free resources, and passthrough devices that exist on one node only — with the most likely cause named. A lock held by a live task and one orphaned by a dead task look identical and have opposite fixes.

- **Side effect:** `read` — reads only
- **Evidence:** analysis from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- finding out why one guest will not start, with the causes ranked rather than listed
- telling a lock held by a running backup from one left behind by a task that died
- checking whether a guest's disk is on a datastore its node cannot currently reach

**Not for:**

- starting the guest, or clearing its lock — nothing here writes
- whether the guest is under memory pressure while running, which proxmox_guest_pressure answers
- whether the cluster is quorate at all, which proxmox_quorum_status answers directly

#### `proxmox_guest_tasks`

Return a Proxmox guest's recent tasks with the vendor's own error text, keeping failed tasks apart from ones that are still running. A running task is not evidence of a failure and is usually the reason a lock is held. An empty history is reported as a finding: the guest was changed on the node rather than through the API.

- **Side effect:** `read` — reads only
- **Evidence:** event from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- reading the vendor's own error text from a guest's most recent failed operation
- finding out whether a task against a guest is still running before touching its lock
- establishing that a guest has no API task history, which means it was changed on the node

**Not for:**

- cancelling or re-running a task — nothing here writes
- why the guest will not start, which proxmox_guest_start_diagnosis answers using this
- cluster-wide backup failures, which proxmox_backup_failures reads

#### `proxmox_ha_state`

Return which Proxmox guests high availability manages, the state the manager wants each in against the state it is actually in, which node is manager, and whether fencing has occurred or is imminent. A cluster that has lost quorum with managed resources is a cluster whose watchdogs are counting down, which no field says.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- finding out whether high availability is about to reset a node
- seeing what state the manager wants a guest in against what it is actually in
- checking which guests high availability manages before proposing to stop one

**Not for:**

- why a guest will not start, which proxmox_guest_start_diagnosis answers
- moving a resource or changing its group — nothing here writes
- whether the cluster is quorate, which proxmox_quorum_status answers directly

#### `proxmox_migration_feasibility`

Return whether a Proxmox guest could move and, per candidate node, exactly what prevents it: no quorum, a node-local disk, a datastore the target cannot reach, a passthrough device that exists in one machine, or not enough memory on the target. Moving the guest is the first thing anybody suggests and on a small cluster it is usually impossible for a reason nobody checked.

- **Side effect:** `read` — reads only
- **Evidence:** analysis from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- checking whether a guest could actually move before proposing that it does
- finding out which node could receive a guest and which could not, with the reason
- seeing that a guest is pinned by node-local storage rather than by anything about itself

**Not for:**

- performing a migration — nothing here writes
- which datastores exist where, which proxmox_datastore_availability reads
- why the guest will not start where it is, which proxmox_guest_start_diagnosis answers

#### `proxmox_node_health`

Return a node's failed systemd units, whether its configured bridges are up, and its LVM thin-pool metadata usage — the three readings that explained the reference cluster's only total outage and that no Proxmox REST endpoint answers. Reported as unavailable, by name, for whichever of the three nothing is publishing, rather than as an absence that could be mistaken for health.

- **Side effect:** `read` — reads only
- **Evidence:** metric from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- checking whether a node's failed systemd units explain a guest that will not start
- checking whether a configured bridge is down before blaming the guests on top of it
- checking an LVM thin pool's metadata usage, which stops writes while data usage still looks comfortable

**Not for:**

- a guest's own CPU or memory pressure, which proxmox_guest_pressure reads
- a physical disk's SMART attributes, which proxmox_disk_health reads
- trend or history over these three readings — this asks for the node's state now

#### `proxmox_orphaned_volumes`

Return the disk volumes on a Proxmox cluster that belong to no existing guest, each with the guest id it was named for and the space it occupies. Proxmox keeps a volume when a guest is destroyed with its disks retained, and nothing afterwards mentions it again while it still counts towards the datastore's fill.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- finding out why a datastore is filling when no guest on it has grown
- listing disks left behind by guests that were destroyed with their disks retained
- checking whether a volume is genuinely unused before anybody proposes removing it

**Not for:**

- deleting a volume — nothing here writes, and this is the tool whose output looks most like a delete list
- how full a datastore is, which proxmox_storage_pressure reads
- what a backup contains, which is a restore rather than a read

#### `proxmox_protection_gaps`

Return which Proxmox guests are covered by an enabled backup job, which are covered only by a disabled one, and whether any replication exists. A job that exists and is switched off satisfies every coverage count and protects nothing.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- finding which guests are covered by no enabled backup job
- checking whether a node loss is recoverable inside the cluster at all
- seeing a backup job that exists and is switched off, which every coverage count misses

**Not for:**

- restoring a guest, or running a backup — nothing here writes
- whether a backup that ran succeeded, which the task history answers
- how full the backup datastore is, which proxmox_storage_pressure reads

#### `proxmox_quorum_status`

Return whether a Proxmox cluster is quorate, by what margin, under which corosync settings, and what follows from the answer. Reports how many node losses the cluster survives — zero on a two-node cluster with no quorum device, while everything is green — and, when quorum is lost, that /etc/pve is read-only and nothing can be started or migrated while running guests carry on.

- **Side effect:** `read` — reads only
- **Evidence:** metric from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- establishing whether a cluster can act at all before investigating why a guest will not start
- finding out how many node losses a cluster survives, including when it is entirely green
- checking whether a configured quorum device is actually contributing a vote

**Not for:**

- why one guest is unhealthy, which is a guest question this does not answer
- corosync link quality, which proxmox_corosync_links reads
- forcing quorum or changing expected votes — nothing here writes

#### `proxmox_reclaimable_space`

Return what could be freed on a Proxmox node — snapshots, backups and orphaned volumes — with, for every entry, how much it would return and what it is protecting. No entry is produced without its protection statement, because the most reclaimable item is very often the only recent recovery point. Bounded by ranking rather than truncation, and it says what it ranked by.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- finding what could be freed on a node that is running out of space, with what each item is protecting
- checking whether the largest reclaimable item is the only recent recovery point
- seeing which backups are kept by a retention rule and which are kept by nothing

**Not for:**

- deleting a snapshot, a backup or a volume — nothing here writes, and this is the tool whose output most resembles a delete list
- how full a datastore is, which proxmox_storage_pressure reads
- whether a guest is protected at all, which proxmox_backup_coverage answers

#### `proxmox_replication_lag`

Return each Proxmox replication job's last success and the recovery-point exposure it leaves — how much work would be lost if the source node were lost now, stated in time. Reports the absence of any replication as a finding when guests sit on node-local storage, because a node loss then makes them unrecoverable inside the cluster and nothing that iterates over existing jobs can see it.

- **Side effect:** `read` — reads only
- **Evidence:** metric from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- finding out how much work a node loss would cost right now, in time
- seeing that a cluster has no replication at all while its guests sit on local disks
- checking a replication job that reports success and has not actually run for days

**Not for:**

- creating or running a replication job — nothing here writes
- whether a backup exists, which proxmox_backup_coverage answers
- whether a guest could migrate, which proxmox_migration_feasibility answers

#### `proxmox_storage_pressure`

Return how full a Proxmox node's storage is at the three levels that fail independently: datastores, LVM-thin pools with data and metadata reported separately, and each guest's own thin volume. A guest at 99% of its volume while its datastore reports 84% is the case a datastore threshold cannot see.

- **Side effect:** `read` — reads only
- **Evidence:** metric from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- finding out whether a guest that cannot write is out of its own volume rather than out of datastore space
- checking a thin pool's metadata, which stops writes while its data figure looks fine
- listing the datastores a node currently cannot reach at all

**Not for:**

- growing a volume or a pool — nothing here writes
- what is inside a backup, which is a datastore-contents question
- whether a guest is healthy, which storage pressure is only one cause of

#### `proxmox_zfs_health`

Return each ZFS pool's state, per-device error counts, scrub age, fragmentation, and capacity against the level at which the write path degrades. A pool that reports ONLINE at 96% capacity with a device quietly accumulating checksum errors is the case a health word cannot express. A node without ZFS is answered as inapplicable rather than as empty.

- **Side effect:** `read` — reads only
- **Evidence:** metric from proxmox
- **Parallel safe:** yes
- **Requires:** proxmox

**Use when:**

- checking whether a ZFS pool that reports ONLINE is above the capacity its write path degrades at
- finding a device accumulating checksum errors inside a pool that still says it is healthy
- establishing when a pool last scrubbed, which is the only thing that verifies its data

**Not for:**

- scrubbing, replacing a device, or expanding a pool — nothing here writes
- LVM-thin pools, which proxmox_storage_pressure reads instead
- a physical drive's SMART attributes, which proxmox_disk_health reads

### communication

#### `pushover_post_message`

Post a message to a channel. Used to deliver a finding where the incident is already being discussed, rather than in a place somebody has to go and look.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** document from pushover
- **Parallel safe:** no
- **Risk class:** `moderate` — Undone only by a further action, or reaching several resources at once.
- **Requires:** pushover
- **Approval:** required — A message to a channel is visible to everyone in it and cannot be unsaid, only followed by a correction. A human decides whether a finding is ready to be read by the people responding.

**Use when:**

- delivering a finding into the channel an incident is being run from
- telling responders that an automated investigation has concluded

**Not for:**

- paging somebody, which is an escalation rather than a message
- anything an investigation has not finished establishing

#### `pushover_recent_messages`

Return the recent messages in a channel, newest first and capped. What people have already said about an incident is evidence, and reading it is what stops an investigation repeating work that is already done.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** document from pushover
- **Parallel safe:** yes
- **Requires:** pushover

**Use when:**

- joining an incident channel where responders have already been talking
- finding what was tried before an automated investigation started

**Not for:**

- system state, which chat reports secondhand and often wrongly
- a channel with no relation to the incident, where the messages are noise

#### `telegram_post_message`

Post a message to a channel. Used to deliver a finding where the incident is already being discussed, rather than in a place somebody has to go and look.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** document from telegram
- **Parallel safe:** no
- **Risk class:** `moderate` — Undone only by a further action, or reaching several resources at once.
- **Requires:** telegram
- **Approval:** required — A message to a channel is visible to everyone in it and cannot be unsaid, only followed by a correction. A human decides whether a finding is ready to be read by the people responding.

**Use when:**

- delivering a finding into the channel an incident is being run from
- telling responders that an automated investigation has concluded

**Not for:**

- paging somebody, which is an escalation rather than a message
- anything an investigation has not finished establishing

#### `telegram_recent_messages`

Return the recent messages in a channel, newest first and capped. What people have already said about an incident is evidence, and reading it is what stops an investigation repeating work that is already done.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** document from telegram
- **Parallel safe:** yes
- **Requires:** telegram

**Use when:**

- joining an incident channel where responders have already been talking
- finding what was tried before an automated investigation started

**Not for:**

- system state, which chat reports secondhand and often wrongly
- a channel with no relation to the incident, where the messages are noise

### database

#### `redis_session_statistics`

Group the current sessions by state or wait, so the answer says whether the database is blocked, saturated, or idle. This is the first database call in an investigation, before anything is asked about a query plan.

- **Side effect:** `read` — reads only
- **Evidence:** metric from redis
- **Parallel safe:** yes
- **Requires:** redis

**Use when:**

- a latency alert on a service whose database may be the constraint
- deciding whether connections are exhausted or queries are simply slow

**Not for:**

- the text of a specific slow query, which the query capability returns
- application errors that never reached the database

#### `redis_slow_queries`

Return the slowest statements recorded, capped, with their timing. Call it after the session statistics: a slow query on an unblocked database is a different problem from the same query behind a lock queue.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** analysis from redis
- **Parallel safe:** yes
- **Requires:** redis

**Use when:**

- a database whose sessions are dominated by one kind of work
- finding the statement behind a latency change with a known start

**Not for:**

- whether the database is the problem at all, which sessions answer first
- a connectivity failure, where no statement ever ran

### estate

#### `run_on_node`

Run one command from a closed, declared list on a cluster node and return what it said. Used for the readings a hypervisor's API does not have — failed systemd units, bridge state, thin-pool metadata fill — each of which has decided a real outage and none of which is a REST endpoint. The command is named, never composed: this cannot run arbitrary commands and cannot change anything.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** configuration from node
- **Parallel safe:** yes

**Use when:**

- reading a node's failed systemd units, which no Proxmox endpoint reports
- checking whether a configured bridge exists before blaming the guests behind it
- reading a thin pool's metadata fill, which stops writes while its data fill looks fine

**Not for:**

- running an arbitrary command, which this deliberately cannot do
- changing anything on a node, which goes through the path that requires an approval
- reaching a guest's own shell, which this never does — every command runs on the host

### incident

#### `alertmanager_acknowledge_incident`

Acknowledge an incident and attach a note saying an automated investigation is under way. It stops the escalation clock, which is a change to who gets woken and therefore needs a human to agree to it.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** incident from alertmanager
- **Parallel safe:** no
- **Risk class:** `low` — Reversible, reaches one resource, and costs a brief loss of availability at most.
- **Requires:** alertmanager
- **Approval:** required — Acknowledging stops the escalation clock, so the next person in the rotation is not paged. That is a decision about who is woken up, and it belongs to a human even though it is reversible.

**Use when:**

- an investigation that has started and will report shortly
- stopping a second escalation while a first responder is already engaged

**Not for:**

- an incident nobody is actually working, where the clock should run
- closing an incident, which acknowledging deliberately does not do

#### `alertmanager_incident_statistics`

Count the incidents in a window, grouped by status, service, or urgency. It answers 'is this one thing or many' in a single call, which is the question that decides whether an investigation is scoped correctly.

- **Side effect:** `read` — reads only
- **Evidence:** incident from alertmanager
- **Parallel safe:** yes
- **Requires:** alertmanager

**Use when:**

- a page arriving while other services may already be alerting
- establishing whether a recurrence is the same incident returning

**Not for:**

- the timeline of one incident, which the timeline capability returns
- the underlying telemetry, which an incident record never carries

#### `alertmanager_incident_timeline`

Return one incident's timeline — the notes, escalations, and status changes, oldest first and capped. It is what tells an investigation what humans already tried, so it does not repeat them.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** incident from alertmanager
- **Parallel safe:** yes
- **Requires:** alertmanager

**Use when:**

- picking up an incident somebody else has already been working
- recovering what was tried before the current responder arrived

**Not for:**

- how many incidents there are, which the statistics answer
- system state, which the timeline only reports secondhand

### logstore

#### `hermes_log_statistics`

Count the log lines matching a query over a window and return the distribution across one field rather than the lines themselves. Call this first: the group it singles out is where the samples should come from.

- **Side effect:** `read` — reads only
- **Evidence:** log from hermes
- **Parallel safe:** yes
- **Requires:** hermes

**Use when:**

- an error-rate alert where the failing service or host is not yet known
- establishing whether one thing is failing loudly or everything is failing
- comparing a window's shape against the equivalent window before the symptom

**Not for:**

- reading a specific error message, which is what sampling is for
- latency across services, which a trace answers and a log count does not

#### `hermes_sample_logs`

Return a small, capped sample of the log lines matching a query over a window, newest first. Narrow the query with the statistics capability before calling this: a sample from an unnarrowed query is arbitrary.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** log from hermes
- **Parallel safe:** yes
- **Requires:** hermes

**Use when:**

- reading the actual error text behind a spike the statistics located
- checking whether a stack trace matches one from a previous incident

**Not for:**

- establishing how much of something there is, which sampling cannot answer
- a query that has not been narrowed, where the sample is arbitrary

#### `loki_log_statistics`

Count the log lines matching a query over a window and return the distribution across one field rather than the lines themselves. Call this first: the group it singles out is where the samples should come from.

- **Side effect:** `read` — reads only
- **Evidence:** log from loki
- **Parallel safe:** yes
- **Requires:** loki

**Use when:**

- an error-rate alert where the failing service or host is not yet known
- establishing whether one thing is failing loudly or everything is failing
- comparing a window's shape against the equivalent window before the symptom

**Not for:**

- reading a specific error message, which is what sampling is for
- latency across services, which a trace answers and a log count does not

#### `loki_sample_logs`

Return a small, capped sample of the log lines matching a query over a window, newest first. Narrow the query with the statistics capability before calling this: a sample from an unnarrowed query is arbitrary.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** log from loki
- **Parallel safe:** yes
- **Requires:** loki

**Use when:**

- reading the actual error text behind a spike the statistics located
- checking whether a stack trace matches one from a previous incident

**Not for:**

- establishing how much of something there is, which sampling cannot answer
- a query that has not been narrowed, where the sample is arbitrary

#### `openobserve_log_statistics`

Count the log lines matching a query over a window and return the distribution across one field rather than the lines themselves. Call this first: the group it singles out is where the samples should come from.

- **Side effect:** `read` — reads only
- **Evidence:** log from openobserve
- **Parallel safe:** yes
- **Requires:** openobserve

**Use when:**

- an error-rate alert where the failing service or host is not yet known
- establishing whether one thing is failing loudly or everything is failing
- comparing a window's shape against the equivalent window before the symptom

**Not for:**

- reading a specific error message, which is what sampling is for
- latency across services, which a trace answers and a log count does not

#### `openobserve_sample_logs`

Return a small, capped sample of the log lines matching a query over a window, newest first. Narrow the query with the statistics capability before calling this: a sample from an unnarrowed query is arbitrary.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** log from openobserve
- **Parallel safe:** yes
- **Requires:** openobserve

**Use when:**

- reading the actual error text behind a spike the statistics located
- checking whether a stack trace matches one from a previous incident

**Not for:**

- establishing how much of something there is, which sampling cannot answer
- a query that has not been narrowed, where the sample is arbitrary

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
- **Risk class:** `trivial` — Reversible, reaches one resource, and loses neither data nor availability.
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

Search previous investigations for incidents resembling this one, and return what was concluded, what the cause turned out to be, and which capabilities found it. Where enough similar incidents exist, a synthesised playbook is returned alongside them — common causes, an effective investigation order, and approaches that previously led nowhere. Search on evidence you have gathered — an error string, an exit code, a failing component — not on the alert text. Naming a component or an issue type ranks those episodes first and excludes nothing, so name what you believe even when you are not sure of it.

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

### metrics

#### `prometheus_active_alerts`

List the alert rules currently firing, with their labels and the time each started. Reach for it early: what else is already alerting is the cheapest way to tell a local failure from a shared one.

- **Side effect:** `read` — reads only
- **Evidence:** event from prometheus
- **Parallel safe:** yes
- **Requires:** prometheus

**Use when:**

- establishing what else was already broken when this alert fired
- finding the earliest firing alert, which is usually nearest the cause

**Not for:**

- the value of a metric, which needs a query rather than an alert list
- an alert that resolved before the investigation started

#### `prometheus_metric_statistics`

Evaluate a metric query over a window and return the series grouped by one label, with counts, rather than every sample. Use it to find which label value moved before asking anything about why.

- **Side effect:** `read` — reads only
- **Evidence:** metric from prometheus
- **Parallel safe:** yes
- **Requires:** prometheus

**Use when:**

- a saturation or error-rate alert where the affected instance is unknown
- establishing whether a change is one instance or the whole fleet

**Not for:**

- reading an individual log line, which a metric never contains
- a question about a single request, where a metric has no resolution

#### `prometheus_resource_pressure`

Return what one estate resource is short of — memory, CPU, disk — with the query built from the signal map rather than written by hand. For a container the series read are the host's, keyed by the guest's own identifier, because a container shares the host's kernel and counters read from inside it report the host's figures under the guest's name.

- **Side effect:** `read` — reads only
- **Evidence:** metric from prometheus
- **Parallel safe:** yes
- **Requires:** prometheus

**Use when:**

- how much memory, CPU or disk a hypervisor guest is using, without asking inside it
- checking whether a container that is being OOM-killed is at its own ceiling
- resource usage for a guest where no agent runs and nothing can be installed

**Not for:**

- an arbitrary PromQL expression, which prometheus_metric_statistics evaluates
- which alerts are firing, which prometheus_active_alerts answers
- reading a log line, which a metric never contains

### model_provider

#### `google_gemini_available_models`

List the models this deployment's Google Gemini key is allowed to call. The question an operator has after storing a key, and the one a provider refusal naming a model raises. Spends no inference quota.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from google_gemini
- **Parallel safe:** yes
- **Requires:** google_gemini

**Use when:**

- checking that a stored provider key can call the model this deployment is configured for
- explaining a provider refusal that names a model rather than the key

**Not for:**

- running an inference, which goes through the model layer rather than here
- choosing a model for a task, which is a configuration decision rather than a reading

### observability

#### `logs_for_resource`

Return what a specific resource's log stream held in a recent window, with the bound that shaped the answer. Every result says how much of the window was actually read: a source keeping less than the window asked for, or an answer stopped at the line limit, is reported rather than left to look like a quiet guest. An empty answer from a source that responded is a finding — it means the resource logged nothing, not that nobody could look. Call this once you know which resource is affected, not on the alert text.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** log from logs
- **Parallel safe:** yes

**Use when:**

- reading what a guest was logging around the time a symptom started
- confirming a service inside a container restarted, rather than inferring it from metrics
- establishing that a guest logged nothing unusual, so the cause is elsewhere

**Not for:**

- asking on the alert text before an affected resource has been identified
- searching the whole cluster's logs for a string, which this deliberately cannot do
- reading a log stream to build a dashboard, which is a report rather than an investigation

### remediation

#### `clear_cache`

Empty a cache, or one namespace within it. There is no rollback: the entries are gone and only traffic repopulates them, so every miss goes to the origin until it does.

- **Side effect:** `write_irreversible` — changes something that cannot be undone
- **Evidence:** change from control_plane
- **Parallel safe:** no
- **Risk class:** `low` — Reversible, reaches one resource, and costs a brief loss of availability at most.
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
- **Risk class:** `high` — Not reversible without a restore, or reaching many resources at once.
- **Approval:** required — Cordoning removes capacity from the pool, and draining moves running workloads. In a pool with little headroom the two together are an outage.

**Use when:**

- take a node with failing hardware out of service before it takes workloads with it
- stop new work landing on a node while its disk pressure is investigated

**Not for:**

- cordoning the last healthy node in a pool, which has nowhere to reschedule to
- draining during a capacity shortage, which moves the outage rather than fixing it

#### `proxmox_ha_relocate`

Change what the Proxmox high-availability manager holds about one resource, so it runs somewhere else. Distinct from a manual migration: the manager acts on its own schedule and may move other resources as a consequence.

- **Side effect:** `write_irreversible` — changes something that cannot be undone
- **Evidence:** change from proxmox
- **Parallel safe:** no
- **Risk class:** `high` — Not reversible without a restore, or reaching many resources at once.
- **Requires:** proxmox
- **Approval:** required — This changes what the cluster's manager believes rather than moving one guest. It stops and starts the resource, and what else the manager then does follows from it.

**Use when:**

- move a managed resource off a node that is being taken out of service
- correct a resource pinned to a group whose nodes can no longer run it

**Not for:**

- relocating a resource away from a node that is merely unreachable
- using this where a manual migration would do, which is almost always

#### `proxmox_migrate_guest`

Move a Proxmox guest to another node online, after checking that the receiving node can see every datastore the guest has disks on. Refuses rather than falling back to an offline migration, and refuses in a two-node cluster whose other member is not answering, because nothing there distinguishes a dead node from an unreachable one.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** change from proxmox
- **Parallel safe:** no
- **Risk class:** `moderate` — Undone only by a further action, or reaching several resources at once.
- **Requires:** proxmox
- **Approval:** required — The guest pauses at the switch-over, both nodes and the link between them carry the memory copy, and a migration that fails at the far end leaves the guest stopped.

**Use when:**

- move a guest off a node that is running out of memory
- empty a node before planned work on it

**Not for:**

- moving a guest whose disk the receiving node cannot see
- moving a guest off a node that is merely not answering

#### `proxmox_reboot_guest`

Reboot a Proxmox guest through its own operating system. A guest that has not gone after the declared timeout is not hard-stopped here: the escalation is a separate, separately classified action.

- **Side effect:** `write_irreversible` — changes something that cannot be undone
- **Evidence:** change from proxmox
- **Parallel safe:** no
- **Risk class:** `moderate` — Undone only by a further action, or reaching several resources at once.
- **Requires:** proxmox
- **Approval:** required — The guest's processes and their in-flight work are destroyed, along with the state that would have explained the failure. Neither is recoverable.

**Use when:**

- recover a guest whose services have become unusable, after the cause is known
- apply a change inside a guest that only takes effect on restart

**Not for:**

- rebooting before the cause is understood, which destroys the evidence
- rebooting a guest whose failure will recur immediately

#### `proxmox_reclaim_storage`

Delete an explicit list of volumes from a Proxmox datastore. Takes the identifiers themselves and never a rule such as 'oldest first', because a rule is evaluated against whatever the datastore holds at execution and nobody reviewed that. Any item that is a recovery point — a snapshot, a backup, the last replication base — is the highest risk class regardless of its size.

- **Side effect:** `destructive` — destroys something
- **Evidence:** change from proxmox
- **Parallel safe:** no
- **Risk class:** `critical` — Can destroy data that has no other copy, or take an estate's availability down.
- **Requires:** proxmox
- **Approval:** required — Deletion is permanent and there is no rollback. If one of these items was the only recent recovery point for a guest, this removes the way back.

**Use when:**

- free space on a datastore by removing items an operator has reviewed and named
- remove backups of a guest that no longer exists, once somebody has confirmed it

**Not for:**

- deleting by a rule such as 'the oldest three', which this refuses
- deleting a backup in order to make room for a backup

#### `proxmox_remove_orphaned_volume`

Delete a Proxmox volume that belongs to no guest, verifying at execution rather than at proposal that nothing references it. A guest created between the two is exactly the volume nobody would think to re-check.

- **Side effect:** `destructive` — destroys something
- **Evidence:** change from proxmox
- **Parallel safe:** no
- **Risk class:** `critical` — Can destroy data that has no other copy, or take an estate's availability down.
- **Requires:** proxmox
- **Approval:** required — A whole disk image goes, permanently. It belongs to nobody only as far as anybody has checked, and there is no rollback.

**Use when:**

- reclaim a disk left behind when a guest was removed with its disks retained
- clear a volume that no guest configuration has referenced for a long time

**Not for:**

- removing a volume a guest created since the proposal was written
- removing a volume that is a replication base, which is a recovery point

#### `proxmox_resume_guest`

Resume a suspended Proxmox guest from the memory image it was suspended with, and confirm it reached a running state.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** change from proxmox
- **Parallel safe:** no
- **Risk class:** `low` — Reversible, reaches one resource, and costs a brief loss of availability at most.
- **Requires:** proxmox
- **Approval:** required — The guest starts serving again and takes back the memory its suspension released.

**Use when:**

- bring back a guest suspended to relieve a node that has since recovered
- resume a guest after the work its suspension made room for has finished

**Not for:**

- resuming a guest onto a node that still has no memory for it
- resuming a guest whose datastore is still unreachable

#### `proxmox_resync_replication`

Run one Proxmox storage replication job now, under an explicit rate limit. The limit is a parameter rather than a setting because corosync shares the link a resync saturates, and a cluster that loses its membership layer to a storage sync has traded a lagging replica for an unquorate cluster.

- **Side effect:** `write_irreversible` — changes something that cannot be undone
- **Evidence:** change from proxmox
- **Parallel safe:** no
- **Risk class:** `moderate` — Undone only by a further action, or reaching several resources at once.
- **Requires:** proxmox
- **Approval:** required — The run overwrites the target with the source's state and holds the link between the nodes for as long as it takes, which is the link corosync also runs over.

**Use when:**

- catch up a replication job that has fallen behind its schedule
- re-run a job that failed while the link was down and has since returned

**Not for:**

- resyncing at full rate over the link corosync uses
- resyncing towards a node that is not answering

#### `proxmox_retry_backup`

Run one Proxmox guest's backup now, outside its schedule. Refuses when a scheduled run is close enough to collide with it, because two vzdump runs against one guest contend for the same lock and the same datastore.

- **Side effect:** `write_irreversible` — changes something that cannot be undone
- **Evidence:** change from proxmox
- **Parallel safe:** no
- **Risk class:** `moderate` — Undone only by a further action, or reaching several resources at once.
- **Requires:** proxmox
- **Approval:** required — The guest and its datastore carry the I/O for as long as it runs, and the copy it writes consumes space that a scheduled run may be counting on.

**Use when:**

- retake a backup that failed for a reason since fixed
- take a copy before a change, when the last scheduled run is too old to rely on

**Not for:**

- retrying into the hour before a scheduled run, which this refuses
- retrying a backup whose failure is a full datastore

#### `proxmox_shutdown_guest`

Ask a Proxmox guest's own operating system to shut down, waiting for it to close its files. Never escalates to a hard stop on its own — that is a separate action with a separate risk class.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** change from proxmox
- **Parallel safe:** no
- **Risk class:** `moderate` — Undone only by a further action, or reaching several resources at once.
- **Requires:** proxmox
- **Approval:** required — The guest stops serving, entirely, until somebody starts it again. Whatever depends on it stops with it.

**Use when:**

- free a node's memory by stopping a guest that is not needed right now
- stop a guest cleanly before its node is worked on

**Not for:**

- stopping a guest to clear a symptom whose cause is unknown
- hard-stopping a guest that is merely slow to shut down

#### `proxmox_start_guest`

Start a stopped Proxmox container or virtual machine and confirm it reached a running state, including that its guest agent answers where one is present. Refused when the cluster has no quorum or the guest is locked.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** change from proxmox
- **Parallel safe:** no
- **Risk class:** `low` — Reversible, reaches one resource, and costs a brief loss of availability at most.
- **Requires:** proxmox
- **Approval:** required — Starting a guest commits the node's memory and disk to it, and a guest that was stopped deliberately is one somebody stopped for a reason.

**Use when:**

- bring back a guest that a failed host reboot left stopped
- start a container whose start was blocked by a datastore that has since returned

**Not for:**

- starting a guest whose disk is on a datastore that is still unreachable
- starting a guest that was stopped deliberately, before finding out why

#### `proxmox_stop_guest`

Stop a Proxmox guest immediately, without telling anything inside it. The hardware equivalent of pulling the power: anything the guest had not written is gone. This is the escalation a reboot proposes when a graceful shutdown does not complete.

- **Side effect:** `destructive` — destroys something
- **Evidence:** change from proxmox
- **Parallel safe:** no
- **Risk class:** `critical` — Can destroy data that has no other copy, or take an estate's availability down.
- **Requires:** proxmox
- **Approval:** required — Nothing inside the guest is told. Unflushed writes are lost, and a database or a filesystem may come back needing repair.

**Use when:**

- stop a guest that did not respond to a graceful shutdown within its declared timeout
- stop a guest that is taking a node down with it

**Not for:**

- stopping a guest that is shutting down cleanly and slowly
- using this where a graceful shutdown has not been tried

#### `proxmox_suspend_guest`

Suspend a Proxmox guest, writing its memory image to disk so it can be resumed exactly where it left off. Needs room on the datastore for the image.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** change from proxmox
- **Parallel safe:** no
- **Risk class:** `moderate` — Undone only by a further action, or reaching several resources at once.
- **Requires:** proxmox
- **Approval:** required — The guest stops serving until it is resumed, and writing its memory image needs space on a datastore that may not have it.

**Use when:**

- free a node's memory without losing the state inside a guest
- pause a guest that is contending for a disk something more urgent needs

**Not for:**

- suspending a guest onto a datastore with no room for its memory image
- suspending a guest that is serving traffic somebody depends on

#### `proxmox_unlock_guest`

Clear the lock a dead task left on a Proxmox guest, so the guest is manageable again. Refuses unless the task named in the lock is confirmed finished — a lock cleared while its holder is running lets a second operation start against a guest a live one is already changing.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** change from proxmox
- **Parallel safe:** no
- **Risk class:** `trivial` — Reversible, reaches one resource, and loses neither data nor availability.
- **Requires:** proxmox
- **Approval:** required — A lock is what stops two operations changing one guest at once. Clearing one whose holder is still alive is how a guest ends up with two writers.

**Use when:**

- free a guest a backup left locked when the backup process died
- make a guest manageable again after a migration was interrupted

**Not for:**

- clearing a lock whose task is still running
- clearing a lock to work around a backup that keeps failing

#### `restart_workload`

Restart a workload's instances. Drops in-flight requests and destroys the process state an investigation may still need, so use only after the cause is established.

- **Side effect:** `write_irreversible` — changes something that cannot be undone
- **Evidence:** change from control_plane
- **Parallel safe:** no
- **Risk class:** `moderate` — Undone only by a further action, or reaching several resources at once.
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
- **Risk class:** `moderate` — Undone only by a further action, or reaching several resources at once.
- **Approval:** required — Rolling back changes what is running in production. It is reversible, but it moves every user onto different code while it is in effect.

**Use when:**

- return a service to the previous release after a deploy correlates with the alert
- undo a configuration change identified as the trigger

#### `scale_workload`

Change a workload's replica count. Reversible by restoring the count recorded in the rollback plan before the change.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** change from control_plane
- **Parallel safe:** no
- **Risk class:** `low` — Reversible, reaches one resource, and costs a brief loss of availability at most.
- **Approval:** required — Scaling changes capacity and cost, and scaling down can turn a degradation into an outage.

**Use when:**

- add capacity to a workload saturating its current replicas
- reduce a replica count raised during an earlier incident

#### `toggle_feature_flag`

Change a feature flag's value or rollout percentage. Reversible by restoring both, which the rollback plan records before the change.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** change from control_plane
- **Parallel safe:** no
- **Risk class:** `moderate` — Undone only by a further action, or reaching several resources at once.
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
- **Risk class:** `moderate` — Undone only by a further action, or reaching several resources at once.
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

### tracing

#### `signoz_slow_traces`

Return the slowest traces for a service in a window, capped, with their duration and root operation. Use it after the statistics have named the operation, so the exemplars are from the part that is actually slow.

- **Side effect:** `read` — reads only
- **Evidence:** trace from signoz
- **Parallel safe:** yes
- **Requires:** signoz

**Use when:**

- finding an exemplar of the latency an aggregate has already located
- seeing which downstream call dominates a slow request

**Not for:**

- establishing how common the slowness is, which needs the aggregate
- an error with no latency component, where traces add nothing

#### `signoz_trace_statistics`

Count the traces for a service over a window and return them grouped by operation or status, rather than the spans. It is what says where the latency is concentrated before any single trace is opened.

- **Side effect:** `read` — reads only
- **Evidence:** trace from signoz
- **Parallel safe:** yes
- **Requires:** signoz

**Use when:**

- a latency alert where the slow operation is not yet known
- deciding whether one endpoint is slow or the whole service is

**Not for:**

- the contents of a log line, which a trace does not carry
- a single known request, where one trace is the whole answer

### vcs

#### `github_change_statistics`

Count the commits landing on a repository in a window, grouped by author or branch. It answers 'was there a deploy-shaped amount of change here' before any individual diff is read.

- **Side effect:** `read` — reads only
- **Evidence:** change from github
- **Parallel safe:** yes
- **Requires:** github

**Use when:**

- an incident with a known start time and a suspected release
- establishing whether a quiet service was changed at all

**Not for:**

- what one change did, which needs the change list rather than a count
- a runtime failure with no deployment in the window

#### `github_recent_changes`

Return the changes merged into a repository in a window, newest first and capped, with title and author. This is what turns a time correlation into a specific change somebody can read.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** change from github
- **Parallel safe:** yes
- **Requires:** github

**Use when:**

- identifying the release that lines up with the start of a symptom
- reading what changed in a service between two known-good times

**Not for:**

- how much changed overall, which the statistics answer more cheaply
- a configuration change made outside version control
