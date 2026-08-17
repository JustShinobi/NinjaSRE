# Integration catalogue

Generated from the declarations by `tools/generate_integration_docs.py`. Do not
edit by hand — edit the integration and regenerate, or the two will disagree and
this file will be the one that is wrong.

Every integration ships the same seven artefacts. The build fails naming both
the integration and the artefact when one is missing, which is what makes "full
parity" a property rather than an aspiration.

15 integration(s), 15 at full parity, 9 recorded as unreachable.

## The seven artefacts

| Artefact | Without it |
|---|---|
| `schema.py` | nothing declares what this vendor's credential is made of, so an operator configuring it is guessing at field names |
| `verifier.py` | nothing can check the credential before it is needed, so a wrong token is discovered during an incident |
| `client.py` | there is no client on the shared base, so any call this integration makes has its own retry, its own error handling, and its own way past the proxy |
| `tools/` | the integration declares no capability, so the agent cannot call it and nothing in an investigation can reach this vendor |
| `SKILL.md` | there is no methodology, so the agent knows this vendor's API and not how to investigate with it |
| `docs.md` | setup is tribal knowledge, and the third team to configure this integration will configure it wrongly |
| `synthetic scenario` | nothing exercises this integration end to end, so it rots quietly and the first to notice is the investigation that needed it |

## Integrations

### cicd

### `argocd`

What Argo CD has actually applied: which applications are synced and healthy, and the ones that are not.

- **Category:** cicd
- **Regions:** self-hosted
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `argocd_failed_runs`
- `argocd_pipeline_statistics`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `applications, get` | read application state and sync status | `argocd_pipeline_statistics`, `argocd_failed_runs` |
| `account, get` | read the account, which the probe uses | `argocd_pipeline_statistics` |

**Pagination:**

- `list_runs` — cursor on `cursor`
- `list_failed_runs` — cursor on `cursor`

### cloud_control_plane

### `grafana`

What Grafana knows about a stack: which dashboards and folders exist, and the annotation timeline of deploys, alert state changes, and anything else a human marked.

- **Category:** cloud_control_plane
- **Regions:** self-hosted
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `grafana_recent_changes`
- `grafana_resource_inventory`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `dashboards:read` | list dashboards and folders | `grafana_resource_inventory` |
| `annotations:read` | read the annotation timeline, including deploy markers | `grafana_recent_changes` |

**Pagination:**

- `list_resources` — page_number on `page`
- `list_changes` — cursor on `from`

### `kubernetes`

Workload events and rollout history from a cluster's API server, at whichever endpoints the operator declared.

- **Category:** cloud_control_plane
- **Regions:** in-cluster
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `kubernetes_rollout_history`
- `kubernetes_workload_events`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `list events` | read events in the namespaces this deployment investigates | `kubernetes_workload_events` |
| `get deployments.apps` | read a deployment and its rollout history | `kubernetes_rollout_history` |
| `list replicasets.apps` | read the replica sets behind a deployment, which is the rollout history | `kubernetes_rollout_history` |

**Pagination:**

- `list_events` — cursor on `continue`

### `proxmox`

A Proxmox VE cluster read whole: quorum, nodes, containers, virtual machines, datastores, thin pools, backups and replication, at whichever addresses the operator declared.

- **Category:** cloud_control_plane
- **Regions:** self-hosted
- **Credentials:** api_token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `proxmox_backup_coverage`
- `proxmox_backup_failures`
- `proxmox_clock_skew`
- `proxmox_cluster_health`
- `proxmox_corosync_links`
- `proxmox_datastore_availability`
- `proxmox_disk_health`
- `proxmox_guest_pressure`
- `proxmox_guest_start_diagnosis`
- `proxmox_guest_tasks`
- `proxmox_ha_state`
- `proxmox_migration_feasibility`
- `proxmox_node_health`
- `proxmox_orphaned_volumes`
- `proxmox_protection_gaps`
- `proxmox_quorum_status`
- `proxmox_reclaimable_space`
- `proxmox_replication_lag`
- `proxmox_storage_pressure`
- `proxmox_zfs_health`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `Sys.Audit on /` | read cluster status, quorum, corosync configuration and the cluster log | `proxmox_cluster_health` |
| `VM.Audit on /vms` | read every guest's status, configuration, snapshots and task history | `proxmox_protection_gaps` |
| `Datastore.Audit on /storage` | read datastore status, contents and the thin pools underneath them | `proxmox_storage_pressure` |

**Pagination:**

- `node_tasks` — offset on `start`

### communication

### `pushover`

Pushover as a last-resort notification path: which delivery groups exist, and a finding pushed to a responder's device.

- **Category:** communication
- **Regions:** global
- **Credentials:** token, user_key
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `pushover_post_message`
- `pushover_recent_messages`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `validate` | confirm the token and user key are valid | `pushover_recent_messages` |
| `messages:write` | push a message to the user or group | `pushover_post_message` |

**Pagination:**

- `recent_messages` — cursor on `cursor`

### `telegram`

A Telegram chat used as an alerting channel: what has arrived recently, and a finding delivered into it.

- **Category:** communication
- **Regions:** global
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `telegram_post_message`
- `telegram_recent_messages`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `getUpdates` | read updates addressed to the bot | `telegram_recent_messages` |
| `sendMessage` | send a message to a chat the bot is in | `telegram_post_message` |

**Pagination:**

- `recent_messages` — offset on `offset`

### database

### `redis`

The Redis Cloud control plane: which databases exist in a subscription and in what state, which is what an HTTP-reachable Redis can answer.

- **Category:** database
- **Regions:** global
- **Credentials:** api_key, secret_key
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `redis_session_statistics`
- `redis_slow_queries`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `subscriptions:read` | list subscriptions and their status | `redis_session_statistics`, `redis_slow_queries` |
| `databases:read` | read database state within a subscription | `redis_slow_queries` |

**Pagination:**

- `list_sessions` — offset on `offset`
- `slow_queries` — offset on `offset`

### incident

### `alertmanager`

What Prometheus Alertmanager is currently holding: which alerts are firing, how they are grouped, and which are silenced rather than resolved.

- **Category:** incident
- **Regions:** self-hosted
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `alertmanager_acknowledge_incident`
- `alertmanager_incident_statistics`
- `alertmanager_incident_timeline`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `alerts:read` | read the alerts Alertmanager is holding | `alertmanager_incident_statistics`, `alertmanager_incident_timeline` |
| `silences:write` | create a silence, which is how it acknowledges | `alertmanager_acknowledge_incident` |

**Pagination:**

- `list_incidents` — cursor on `filter`
- `incident_timeline` — cursor on `filter`

### logstore

### `hermes`

Hermes log tailing and classification: what a stream is currently emitting, grouped by the class its own model assigned.

- **Category:** logstore
- **Regions:** self-hosted
- **Credentials:** api_key
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `hermes_log_statistics`
- `hermes_sample_logs`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `logs:read` | search and tail the workspace's streams | `hermes_log_statistics`, `hermes_sample_logs` |
| `streams:list` | list streams, which the connectivity probe uses | `hermes_log_statistics` |

**Pagination:**

- `search_logs` — cursor on `cursor`
- `recent_logs` — cursor on `cursor`

### `loki`

Log search over Loki's label index and LogQL, with the shape of a query counted before any line of it is read.

- **Category:** logstore
- **Regions:** self-hosted
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `loki_log_statistics`
- `loki_sample_logs`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `logs:read` | run LogQL queries against the tenant's streams | `loki_log_statistics`, `loki_sample_logs` |
| `labels:read` | list label names and values, which the probe uses | `loki_log_statistics` |

**Pagination:**

- `search_logs` — cursor on `start`
- `recent_logs` — cursor on `start`

### `openobserve`

SQL search over OpenObserve streams, counted by field before any record is read, for the estates that chose it for its storage cost.

- **Category:** logstore
- **Regions:** self-hosted
- **Credentials:** username, password, organisation
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `openobserve_log_statistics`
- `openobserve_sample_logs`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `streams:read` | search the streams this user can see | `openobserve_log_statistics`, `openobserve_sample_logs` |
| `health:read` | read health, which the connectivity probe uses | `openobserve_log_statistics` |

**Pagination:**

- `search_logs` — offset on `from`
- `recent_logs` — offset on `from`

### metrics

### `prometheus`

PromQL evaluation and the alert rules currently firing, from the server that holds the series rather than from a dashboard on top of it.

- **Category:** metrics
- **Regions:** self-hosted
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `prometheus_active_alerts`
- `prometheus_metric_statistics`
- `prometheus_resource_pressure`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `query` | evaluate PromQL over the stored series | `prometheus_metric_statistics` |
| `rules:read` | read alerting rules and their current state | `prometheus_active_alerts` |

**Pagination:**

- `query_metric` — cursor on `start`
- `list_alerts` — cursor on `start`

### model_provider

### `google_gemini`

Google Gemini, declared so a provider key stored in the vault is reachable through the credential proxy rather than only through the process environment.

- **Category:** model_provider
- **Regions:** global
- **Credentials:** api_key
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `google_gemini_available_models`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `generativelanguage.models.list` | list the models this key may use, and call them | `google_gemini_available_models` |

### tracing

### `signoz`

SigNoz's span store: where latency and errors concentrate for a service, and the slowest traces behind that concentration.

- **Category:** tracing
- **Regions:** self-hosted
- **Credentials:** api_key
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `signoz_slow_traces`
- `signoz_trace_statistics`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `traces:read` | query the span store | `signoz_trace_statistics`, `signoz_slow_traces` |
| `version:read` | read the build version, which the probe uses | `signoz_trace_statistics` |

**Pagination:**

- `search_traces` — offset on `offset`
- `slow_traces` — offset on `offset`

### vcs

### `github`

What landed in a repository and when: the commits on its default branch and the pull requests recently merged into it.

- **Category:** vcs
- **Regions:** github.com, enterprise
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `github_change_statistics`
- `github_recent_changes`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `contents:read` | search and read commits in a repository | `github_change_statistics` |
| `pull_requests:read` | search and read pull requests | `github_recent_changes` |

**Pagination:**

- `list_commits` — page_number on `page`
- `list_pull_requests` — page_number on `page`

## Recorded gaps

A vendor nobody wrote is a vendor nobody is told about, so the omissions are a declaration rather than an absence. Each names why it cannot be built the way every other integration is, and what would have to change.

### `postgresql` — PostgreSQL

- **Category:** database
- **Why not:** The server speaks its own binary wire protocol on its own port. The credential proxy is HTTP: it attaches a secret to a request, and there is no request here to attach one to. Building the client anyway would mean holding the credential in the agent's process, which Article IV forbids outright.
- **What would change it:** A protocol bridge that terminates the credential outside the agent process, the way the HTTP proxy does. Nothing in the catalogue reaches a managed PostgreSQL's control plane today.

### `mysql` — MySQL

- **Category:** database
- **Why not:** The server speaks its own binary wire protocol on its own port. The credential proxy is HTTP: it attaches a secret to a request, and there is no request here to attach one to. Building the client anyway would mean holding the credential in the agent's process, which Article IV forbids outright.
- **What would change it:** The same bridge PostgreSQL needs. Nothing in the catalogue reaches a managed MySQL's control plane today.

### `mariadb` — MariaDB

- **Category:** database
- **Why not:** The server speaks its own binary wire protocol on its own port. The credential proxy is HTTP: it attaches a secret to a request, and there is no request here to attach one to. Building the client anyway would mean holding the credential in the agent's process, which Article IV forbids outright.
- **What would change it:** The same bridge MySQL needs — MariaDB speaks the MySQL protocol and has the same constraint for the same reason.

### `mongodb` — MongoDB

- **Category:** database
- **Why not:** The server speaks its own binary wire protocol on its own port. The credential proxy is HTTP: it attaches a secret to a request, and there is no request here to attach one to. Building the client anyway would mean holding the credential in the agent's process, which Article IV forbids outright.
- **What would change it:** A protocol bridge. Nothing in the catalogue reaches a hosted deployment's administration API today, and a self-hosted replica set on port 27017 has no equivalent either way.

### `redis_server` — Redis (self-hosted)

- **Category:** database
- **Why not:** The server speaks its own binary wire protocol on its own port. The credential proxy is HTTP: it attaches a secret to a request, and there is no request here to attach one to. Building the client anyway would mean holding the credential in the agent's process, which Article IV forbids outright.
- **What would change it:** A protocol bridge. `redis` is in the catalogue and reads Redis Cloud's control plane over HTTP; the keyspace, the slow log, and `INFO` on a self-hosted server are RESP and are not reachable.

### `smtp` — SMTP

- **Category:** communication
- **Why not:** SMTP is a stateful line protocol over its own port, not a request-response API. The credential proxy attaches a secret to an HTTP request; an SMTP session has no such request, and authentication happens inside a conversation the proxy cannot participate in.
- **What would change it:** Either a protocol bridge that terminates the SMTP credential outside the agent process, or delivery through a vendor with an HTTP API — `pushover` is in the catalogue and reaches a person without an SMTP session.

### `helm` — Helm

- **Category:** cicd
- **Why not:** Helm 3 has no server component. A release is a Secret in the cluster and the CLI is what reads it, so there is no API for an integration to hold a credential against — the credential that matters is the cluster's.
- **What would change it:** Nothing about Helm. Release history is already reachable: `kubernetes` reads the release Secrets in a namespace, and `argocd` answers the same question for the estates that deploy charts through it.

### `gatus` — Gatus

- **Category:** observability
- **Why not:** Gatus answers one question — is this endpoint responding — and two configured sources already answer it by different routes: the hypervisor reports each guest's own state, and a blackbox exporter reports reachability from outside, both reaching the platform through Prometheus. A third path to the same answer is a third thing to keep credentials for and no new signal, and an investigation offered three sources for one question spends turns choosing between them.
- **What would change it:** A synthetic check that asserts something neither of the other two can — a login flow, a certificate chain, a response body — or an estate where Gatus is the only thing watching a class of endpoint the hypervisor cannot see.

### `netbox` — NetBox

- **Category:** infrastructure
- **Why not:** NetBox is a source of truth for network and addressing, and both already reach the platform: the addressing comes from the hypervisor with each guest, and the zones come from the declared inventory the estate is reconciled against. Ingesting the same facts from a third place is a third answer to 'which network is this on', and the failure that produces is two of them disagreeing quietly.
- **What would change it:** An estate that grows past what the repository's own inventory describes — hardware, circuits, addressing NetBox is the only record of — at which point it stops being a duplicate and becomes the source for facts nothing else holds.
