# Integration catalogue

Generated from the declarations by `tools/generate_integration_docs.py`. Do not
edit by hand — edit the integration and regenerate, or the two will disagree and
this file will be the one that is wrong.

Every integration ships the same seven artefacts. The build fails naming both
the integration and the artefact when one is missing, which is what makes "full
parity" a property rather than an aspiration.

3 integration(s), 3 at full parity.

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

### cloud_control_plane

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

### logstore

### `aws`

CloudWatch Logs: log group inventory and event reads, with every request signed by the credential proxy rather than by this process.

- **Category:** logstore
- **Regions:** us-east-1
- **Credentials:** access_key_id, secret_access_key
- **SDK strategy:** `proxy_signed`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `aws_filter_log_events`
- `aws_list_log_groups`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `logs:DescribeLogGroups` | list the log groups in this account and region | `aws_list_log_groups` |
| `logs:FilterLogEvents` | read log events from a log group over a time window | `aws_filter_log_events` |

**Pagination:**

- `filter_log_events` — page_token on `nextToken`

### `datadog`

Log search and aggregation, metric series, and monitor state, across Datadog's six regional deployments.

- **Category:** logstore
- **Regions:** datadoghq.com, datadoghq.eu, us3.datadoghq.com, us5.datadoghq.com, ap1.datadoghq.com, ddog-gov.com
- **Credentials:** api_key, app_key
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `datadog_log_statistics`
- `datadog_sample_logs`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `logs_read_data` | read log events and their aggregations | `datadog_log_statistics`, `datadog_sample_logs` |
| `monitors_read` | list monitors and their alerting state | `datadog_log_statistics` |

**Pagination:**

- `search_logs` — cursor on `cursor`
