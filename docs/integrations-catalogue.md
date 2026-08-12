# Integration catalogue

Generated from the declarations by `tools/generate_integration_docs.py`. Do not
edit by hand — edit the integration and regenerate, or the two will disagree and
this file will be the one that is wrong.

Every integration ships the same seven artefacts. The build fails naming both
the integration and the artefact when one is missing, which is what makes "full
parity" a property rather than an aspiration.

85 integration(s), 85 at full parity, 9 recorded as unreachable.

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

### `jenkins`

Jenkins build history: how a job has been doing lately, and the builds that failed, for the estates whose pipelines still run there.

- **Category:** cicd
- **Regions:** self-hosted
- **Credentials:** username, password
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `jenkins_failed_runs`
- `jenkins_pipeline_statistics`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `Overall/Read` | read the Jenkins instance at all | `jenkins_pipeline_statistics`, `jenkins_failed_runs` |
| `Job/Read` | read job configuration and build history | `jenkins_pipeline_statistics`, `jenkins_failed_runs` |

**Pagination:**

- `list_runs` — cursor on `from`
- `list_failed_runs` — cursor on `from`

### `railway`

Railway deployments and their status, for the services this project runs on it.

- **Category:** cicd
- **Regions:** global
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `railway_failed_runs`
- `railway_pipeline_statistics`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `deployments:read` | read the project's deployments | `railway_pipeline_statistics`, `railway_failed_runs` |
| `me:read` | read the token's own identity, which the probe uses | `railway_pipeline_statistics` |

**Pagination:**

- `list_runs` — cursor on `after`
- `list_failed_runs` — cursor on `after`

### `vercel`

Vercel deployments: how the recent ones have gone for a project, and the ones that errored, which is usually the whole story for a frontend incident.

- **Category:** cicd
- **Regions:** global
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `vercel_failed_runs`
- `vercel_pipeline_statistics`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `deployments:read` | list deployments and their state | `vercel_pipeline_statistics`, `vercel_failed_runs` |
| `user:read` | read the token's own account, which the probe uses | `vercel_pipeline_statistics` |

**Pagination:**

- `list_runs` — cursor on `until`
- `list_failed_runs` — cursor on `until`

### cloud_control_plane

### `aws_cloudtrail`

Who changed what in this AWS account, and when. The change history most incidents turn out to need and most investigations reach for too late.

- **Category:** cloud_control_plane
- **Regions:** us-east-1, us-east-2, us-west-1, us-west-2, eu-west-1, eu-west-2, eu-central-1, ap-south-1, ap-southeast-1, ap-southeast-2, ap-northeast-1, sa-east-1
- **Credentials:** access_key_id, secret_access_key
- **SDK strategy:** `proxy_signed`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `aws_cloudtrail_recent_changes`
- `aws_cloudtrail_resource_inventory`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `cloudtrail:LookupEvents` | read the management-event history | `aws_cloudtrail_resource_inventory`, `aws_cloudtrail_recent_changes` |

**Pagination:**

- `list_resources` — page_token on `NextToken`
- `list_changes` — page_token on `NextToken`

### `aws_ec2`

EC2 instance state for a region: how many instances are in which state, and the instances themselves with their type, zone, and launch time.

- **Category:** cloud_control_plane
- **Regions:** us-east-1, us-east-2, us-west-1, us-west-2, eu-west-1, eu-west-2, eu-central-1, ap-south-1, ap-southeast-1, ap-southeast-2, ap-northeast-1, sa-east-1
- **Credentials:** access_key_id, secret_access_key
- **SDK strategy:** `proxy_signed`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `aws_ec2_recent_changes`
- `aws_ec2_resource_inventory`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `ec2:DescribeInstanceStatus` | read instance state and any scheduled events | `aws_ec2_resource_inventory` |
| `ec2:DescribeInstances` | read instance detail and tags | `aws_ec2_recent_changes` |

**Pagination:**

- `list_resources` — page_token on `NextToken`
- `list_changes` — page_token on `NextToken`

### `aws_ecs`

The ECS control plane: which clusters this account runs and which task definitions have been registered, which is where a deployment shows up.

- **Category:** cloud_control_plane
- **Regions:** us-east-1, us-east-2, us-west-1, us-west-2, eu-west-1, eu-west-2, eu-central-1, ap-south-1, ap-southeast-1, ap-southeast-2, ap-northeast-1, sa-east-1
- **Credentials:** access_key_id, secret_access_key
- **SDK strategy:** `proxy_signed`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `aws_ecs_recent_changes`
- `aws_ecs_resource_inventory`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `ecs:ListClusters` | list the clusters in this account and region | `aws_ecs_resource_inventory` |
| `ecs:ListTaskDefinitions` | list registered task definitions, newest first | `aws_ecs_recent_changes` |

**Pagination:**

- `list_resources` — page_token on `nextToken`
- `list_changes` — page_token on `nextToken`

### `aws_eks`

The EKS control plane: which clusters this account runs, their version and status, and the cluster updates that have been applied to them.

- **Category:** cloud_control_plane
- **Regions:** us-east-1, us-east-2, us-west-1, us-west-2, eu-west-1, eu-west-2, eu-central-1, ap-south-1, ap-southeast-1, ap-southeast-2, ap-northeast-1, sa-east-1
- **Credentials:** access_key_id, secret_access_key
- **SDK strategy:** `proxy_signed`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `aws_eks_recent_changes`
- `aws_eks_resource_inventory`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `eks:ListClusters` | list the clusters in this account and region | `aws_eks_resource_inventory`, `aws_eks_recent_changes` |
| `eks:DescribeCluster` | read a cluster's version, endpoint, and status | `aws_eks_recent_changes` |

**Pagination:**

- `list_resources` — page_token on `nextToken`
- `list_changes` — page_token on `nextToken`

### `aws_elb`

Elastic Load Balancing state: which load balancers exist and in what state, and the target groups behind them.

- **Category:** cloud_control_plane
- **Regions:** us-east-1, us-east-2, us-west-1, us-west-2, eu-west-1, eu-west-2, eu-central-1, ap-south-1, ap-southeast-1, ap-southeast-2, ap-northeast-1, sa-east-1
- **Credentials:** access_key_id, secret_access_key
- **SDK strategy:** `proxy_signed`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `aws_elb_recent_changes`
- `aws_elb_resource_inventory`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `elasticloadbalancing:DescribeLoadBalancers` | read load balancer state and scheme | `aws_elb_resource_inventory` |
| `elasticloadbalancing:DescribeTargetGroups` | read the target groups behind each load balancer | `aws_elb_recent_changes` |

**Pagination:**

- `list_resources` — page_token on `Marker`
- `list_changes` — page_token on `Marker`

### `aws_lambda`

The Lambda control plane: which functions exist, on which runtime and memory setting, and when each was last modified.

- **Category:** cloud_control_plane
- **Regions:** us-east-1, us-east-2, us-west-1, us-west-2, eu-west-1, eu-west-2, eu-central-1, ap-south-1, ap-southeast-1, ap-southeast-2, ap-northeast-1, sa-east-1
- **Credentials:** access_key_id, secret_access_key
- **SDK strategy:** `proxy_signed`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `aws_lambda_recent_changes`
- `aws_lambda_resource_inventory`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `lambda:ListFunctions` | list the functions in this region | `aws_lambda_resource_inventory`, `aws_lambda_recent_changes` |
| `lambda:GetFunctionConfiguration` | read a function's runtime, memory, and last modification | `aws_lambda_recent_changes` |

**Pagination:**

- `list_resources` — page_token on `Marker`
- `list_changes` — page_token on `Marker`

### `aws_rds`

The RDS control plane: which database instances exist and in what state, and the events RDS recorded against them — failovers, restarts, parameter changes.

- **Category:** cloud_control_plane
- **Regions:** us-east-1, us-east-2, us-west-1, us-west-2, eu-west-1, eu-west-2, eu-central-1, ap-south-1, ap-southeast-1, ap-southeast-2, ap-northeast-1, sa-east-1
- **Credentials:** access_key_id, secret_access_key
- **SDK strategy:** `proxy_signed`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `aws_rds_recent_changes`
- `aws_rds_resource_inventory`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `rds:DescribeDBInstances` | read instance state and configuration | `aws_rds_resource_inventory` |
| `rds:DescribeEvents` | read the failover, restart, and parameter-change history | `aws_rds_recent_changes` |

**Pagination:**

- `list_resources` — page_token on `Marker`
- `list_changes` — page_token on `Marker`

### `aws_s3`

What is in the bucket this team configured: the objects and their storage class, and the version history, which is the closest S3 has to a change log.

- **Category:** cloud_control_plane
- **Regions:** us-east-1, us-east-2, us-west-1, us-west-2, eu-west-1, eu-west-2, eu-central-1, ap-south-1, ap-southeast-1, ap-southeast-2, ap-northeast-1, sa-east-1
- **Credentials:** access_key_id, secret_access_key, bucket
- **SDK strategy:** `proxy_signed`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `aws_s3_recent_changes`
- `aws_s3_resource_inventory`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `s3:ListBucket` | list the objects in the configured bucket | `aws_s3_resource_inventory` |
| `s3:ListBucketVersions` | list object versions, which is what makes a change history | `aws_s3_recent_changes` |

**Pagination:**

- `list_resources` — cursor on `continuation-token`
- `list_changes` — cursor on `key-marker`

### `azure`

The Azure Resource Manager control plane: what exists in a subscription, and the activity log entries that changed it.

- **Category:** cloud_control_plane
- **Regions:** global
- **Credentials:** token, subscription
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `azure_recent_changes`
- `azure_resource_inventory`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `Microsoft.Resources/subscriptions/resources/read` | list resources | `azure_resource_inventory` |
| `Microsoft.Insights/eventtypes/values/read` | read the activity log, which is the change history | `azure_recent_changes` |

**Pagination:**

- `list_resources` — cursor on `$skipToken`
- `list_changes` — cursor on `$skipToken`

### `docker`

The Docker Engine API: which containers exist and in what state, and the engine events that changed them.

- **Category:** cloud_control_plane
- **Regions:** self-hosted
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `docker_recent_changes`
- `docker_resource_inventory`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `containers:list` | list containers and their state | `docker_resource_inventory` |
| `events:read` | read the engine event stream | `docker_recent_changes` |

**Pagination:**

- `list_resources` — cursor on `since`
- `list_changes` — cursor on `since`

### `flagd`

OpenFeature's flagd: which feature flags this deployment is serving and in what state, which is the change history nothing else records.

- **Category:** cloud_control_plane
- **Regions:** self-hosted
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `flagd_recent_changes`
- `flagd_resource_inventory`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `evaluation:resolve` | resolve every flag for a context | `flagd_resource_inventory`, `flagd_recent_changes` |
| `healthz` | read liveness, which the connectivity probe uses | `flagd_resource_inventory` |

**Pagination:**

- `list_resources` — cursor on `cursor`
- `list_changes` — cursor on `cursor`

### `gcp`

The Google Cloud control plane through Cloud Asset Inventory and Cloud Logging: what exists in a project, and the admin activity that changed it.

- **Category:** cloud_control_plane
- **Regions:** global
- **Credentials:** token, project
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `gcp_recent_changes`
- `gcp_resource_inventory`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `cloudasset.assets.listResource` | list the resources in the configured project | `gcp_resource_inventory`, `gcp_recent_changes` |
| `cloudasset.assets.searchAllResources` | read a resource's state at a point in time | `gcp_recent_changes` |

**Pagination:**

- `list_resources` — page_token on `pageToken`
- `list_changes` — page_token on `pageToken`

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

### `proxmox_backup_server`

Datastore usage, snapshots, verification outcomes and garbage-collection state from a Proxmox Backup Server, at whichever address the operator declared.

- **Category:** cloud_control_plane
- **Regions:** self-hosted
- **Credentials:** api_token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `proxmox_backup_server_datastore_health`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `Datastore.Audit on /datastore` | read datastore usage, snapshots, verification outcomes and garbage-collection state | `proxmox_backup_server_datastore_health` |

**Pagination:**

- `snapshots` — offset on `start`

### communication

### `discord`

A Discord channel used for incident response: what has been said recently, and a finding posted into it.

- **Category:** communication
- **Regions:** global
- **Credentials:** token, channel_id
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `discord_post_message`
- `discord_recent_messages`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `View Channel` | read the channel's message history | `discord_recent_messages` |
| `Send Messages` | post a message into the channel | `discord_post_message` |

**Pagination:**

- `recent_messages` — cursor on `before`

### `microsoft_teams`

The Teams channel an incident is being run from: what has been said, and a finding posted where the responders are.

- **Category:** communication
- **Regions:** global
- **Credentials:** token, team_id
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `microsoft_teams_post_message`
- `microsoft_teams_recent_messages`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `ChannelMessage.Read.All` | read channel messages | `microsoft_teams_recent_messages` |
| `ChannelMessage.Send` | post a message to a channel | `microsoft_teams_post_message` |

**Pagination:**

- `recent_messages` — cursor on `$skiptoken`

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

### `rocket_chat`

A Rocket.Chat channel used for incident response: what has been said, and a finding posted into it.

- **Category:** communication
- **Regions:** self-hosted
- **Credentials:** token, user_id
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `rocket_chat_post_message`
- `rocket_chat_recent_messages`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `view-c-room` | read a public channel's history | `rocket_chat_recent_messages` |
| `post-message` | post a message into a channel | `rocket_chat_post_message` |

**Pagination:**

- `recent_messages` — offset on `offset`

### `slack`

The conversation an incident is already happening in: what responders have said, and a finding delivered where they will read it.

- **Category:** communication
- **Regions:** global
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `slack_post_message`
- `slack_recent_messages`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `channels:history` | read messages in the channels the bot is in | `slack_recent_messages` |
| `chat:write` | post a message as the bot | `slack_post_message` |

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

### `twilio`

Twilio as an SMS notification path: the messages this account has sent recently, and a finding delivered to a responder's phone.

- **Category:** communication
- **Regions:** global
- **Credentials:** username, password, account_sid
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `twilio_post_message`
- `twilio_recent_messages`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `messages:read` | read the account's message history | `twilio_recent_messages` |
| `messages:create` | send a message from the account | `twilio_post_message` |

**Pagination:**

- `recent_messages` — page_number on `Page`

### `whatsapp`

A WhatsApp Business number used for on-call notification: the message templates available, and a finding delivered to a responder.

- **Category:** communication
- **Regions:** global
- **Credentials:** token, phone_number_id
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `whatsapp_post_message`
- `whatsapp_recent_messages`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `whatsapp_business_management` | read the number's message templates | `whatsapp_recent_messages` |
| `whatsapp_business_messaging` | send a message from the number | `whatsapp_post_message` |

**Pagination:**

- `recent_messages` — cursor on `after`

### data_platform

### `airflow`

Airflow's scheduler state: which DAG runs are in which state, and the task instances that failed, which is where a data-freshness incident starts.

- **Category:** data_platform
- **Regions:** self-hosted
- **Credentials:** username, password
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `airflow_pipeline_health`
- `airflow_recent_failures`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `can_read on DAG Runs` | list DAG runs and their state | `airflow_pipeline_health`, `airflow_recent_failures` |
| `can_read on Task Instances` | read the tasks behind a failed run | `airflow_recent_failures` |

**Pagination:**

- `list_tasks` — offset on `offset`
- `list_failures` — offset on `offset`

### `dagster`

Dagster run state through its GraphQL API: which runs are in which status, and the failures behind a stale asset.

- **Category:** data_platform
- **Regions:** self-hosted
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `dagster_pipeline_health`
- `dagster_recent_failures`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `runs:read` | read run status through the GraphQL API | `dagster_pipeline_health`, `dagster_recent_failures` |
| `version:read` | read the version, which the probe uses | `dagster_pipeline_health` |

**Pagination:**

- `list_tasks` — offset on `cursor`
- `list_failures` — offset on `cursor`

### `flink`

Flink's JobManager REST API: which jobs are running, and the ones that failed or restarted, which is where a streaming backlog starts.

- **Category:** data_platform
- **Regions:** self-hosted
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `flink_pipeline_health`
- `flink_recent_failures`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `jobs:read` | read the job overview and per-job detail | `flink_pipeline_health`, `flink_recent_failures` |
| `config:read` | read the cluster config, which the probe uses | `flink_pipeline_health` |

**Pagination:**

- `list_tasks` — cursor on `cursor`
- `list_failures` — cursor on `cursor`

### `kafka`

Kafka through its REST Proxy: which topics and consumer groups exist on a cluster, and which groups are not in a stable state.

- **Category:** data_platform
- **Regions:** self-hosted
- **Credentials:** username, password, cluster
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `kafka_pipeline_health`
- `kafka_recent_failures`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `DescribeTopics` | list topics on the cluster | `kafka_pipeline_health` |
| `DescribeGroups` | list consumer groups and their state | `kafka_recent_failures` |

**Pagination:**

- `list_tasks` — cursor on `page_token`
- `list_failures` — cursor on `page_token`

### `prefect`

Prefect flow runs: which are in which state, and the ones that failed, for the estates orchestrating their pipelines with it.

- **Category:** data_platform
- **Regions:** cloud
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `prefect_pipeline_health`
- `prefect_recent_failures`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `flow_runs:read` | read flow runs and their state | `prefect_pipeline_health`, `prefect_recent_failures` |
| `health:read` | read server health, which the probe uses | `prefect_pipeline_health` |

**Pagination:**

- `list_tasks` — offset on `offset`
- `list_failures` — offset on `offset`

### `rabbitmq`

RabbitMQ's management API: which queues exist and how deep they are, which is the first question of every message-backlog incident.

- **Category:** data_platform
- **Regions:** self-hosted
- **Credentials:** username, password
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `rabbitmq_pipeline_health`
- `rabbitmq_recent_failures`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `monitoring` | read queues, overview, and node statistics | `rabbitmq_pipeline_health`, `rabbitmq_recent_failures` |
| `management` | reach the management plugin at all | `rabbitmq_pipeline_health`, `rabbitmq_recent_failures` |

**Pagination:**

- `list_tasks` — page_number on `page`
- `list_failures` — page_number on `page`

### `spark`

Spark's history and status API: which applications and jobs are in which state, and the ones that failed.

- **Category:** data_platform
- **Regions:** self-hosted
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `spark_pipeline_health`
- `spark_recent_failures`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `applications:read` | list applications and their attempts | `spark_pipeline_health`, `spark_recent_failures` |
| `version:read` | read the version, which the probe uses | `spark_pipeline_health` |

**Pagination:**

- `list_tasks` — offset on `offset`
- `list_failures` — offset on `offset`

### `temporal`

Temporal workflow executions over its HTTP API: which are open, which failed, and how that distribution has changed.

- **Category:** data_platform
- **Regions:** self-hosted
- **Credentials:** token, namespace
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `temporal_pipeline_health`
- `temporal_recent_failures`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `workflows:read` | list workflow executions | `temporal_pipeline_health`, `temporal_recent_failures` |
| `namespaces:read` | read the namespace, which the probe uses | `temporal_pipeline_health` |

**Pagination:**

- `list_tasks` — page_token on `nextPageToken`
- `list_failures` — page_token on `nextPageToken`

### database

### `azure_sql`

Azure SQL through Resource Manager: which databases exist in a subscription and in what state, and their recent service-level events.

- **Category:** database
- **Regions:** global
- **Credentials:** token, subscription
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `azure_sql_session_statistics`
- `azure_sql_slow_queries`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `Microsoft.Sql/servers/read` | list logical servers | `azure_sql_session_statistics` |
| `Microsoft.Sql/servers/databases/read` | read database state and service tier | `azure_sql_slow_queries` |

**Pagination:**

- `list_sessions` — cursor on `$skipToken`
- `slow_queries` — cursor on `$skipToken`

### `bigquery`

BigQuery job state for a project: what is running or queued, and the jobs that took longest, which is where a data-freshness incident usually starts.

- **Category:** database
- **Regions:** global
- **Credentials:** token, project
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `bigquery_session_statistics`
- `bigquery_slow_queries`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `bigquery.jobs.list` | list jobs in the project | `bigquery_session_statistics`, `bigquery_slow_queries` |
| `bigquery.jobs.get` | read a job's statistics and errors | `bigquery_slow_queries` |

**Pagination:**

- `list_sessions` — page_token on `pageToken`
- `slow_queries` — page_token on `pageToken`

### `clickhouse`

ClickHouse over its HTTP interface: what the server is currently executing, and the slowest queries in the log.

- **Category:** database
- **Regions:** self-hosted
- **Credentials:** username, password
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `clickhouse_session_statistics`
- `clickhouse_slow_queries`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `SELECT on system.processes` | read what is executing now | `clickhouse_session_statistics` |
| `SELECT on system.query_log` | read the completed-query log | `clickhouse_slow_queries` |

**Pagination:**

- `list_sessions` — offset on `offset`
- `slow_queries` — offset on `offset`

### `mongodb_atlas`

The Atlas control plane: which clusters and processes exist in a project, and the slow-query entries Atlas's performance advisor has collected.

- **Category:** database
- **Regions:** global
- **Credentials:** username, password, group
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `mongodb_atlas_session_statistics`
- `mongodb_atlas_slow_queries`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `Project Read Only` | read processes and clusters in the project | `mongodb_atlas_session_statistics`, `mongodb_atlas_slow_queries` |
| `Project Monitoring Admin` | read process measurements and the performance advisor | `mongodb_atlas_slow_queries` |

**Pagination:**

- `list_sessions` — page_number on `pageNum`
- `slow_queries` — page_number on `pageNum`

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

### `snowflake`

Snowflake over its SQL REST API: what is running in the account now, and the slowest statements the query history recorded.

- **Category:** database
- **Regions:** account
- **Credentials:** token, account
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `snowflake_session_statistics`
- `snowflake_slow_queries`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `MONITOR on the account` | read query history | `snowflake_session_statistics`, `snowflake_slow_queries` |
| `USAGE on the warehouse` | run the statements that read it | `snowflake_session_statistics`, `snowflake_slow_queries` |

**Pagination:**

- `list_sessions` — offset on `partition`
- `slow_queries` — offset on `partition`

### `supabase`

The Supabase management API: which projects exist in an organisation and in what state, for the estates that run their Postgres there.

- **Category:** database
- **Regions:** global
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `supabase_session_statistics`
- `supabase_slow_queries`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `projects:read` | list projects and their status | `supabase_session_statistics`, `supabase_slow_queries` |
| `organizations:read` | read organisations, which the probe uses | `supabase_session_statistics` |

**Pagination:**

- `list_sessions` — cursor on `cursor`
- `slow_queries` — cursor on `cursor`

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

### `blameless`

Blameless's incident record: what is open, one incident's events, and the update that says an automated investigation is under way.

- **Category:** incident
- **Regions:** tenant
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `blameless_acknowledge_incident`
- `blameless_incident_statistics`
- `blameless_incident_timeline`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `incidents:read` | read incidents and their events | `blameless_incident_statistics`, `blameless_incident_timeline` |
| `incidents:write` | post an event onto an incident | `blameless_acknowledge_incident` |

**Pagination:**

- `list_incidents` — offset on `offset`
- `incident_timeline` — offset on `offset`

### `firehydrant`

FireHydrant's incident record: what is active, one incident's events, and the note that says an automated investigation has started.

- **Category:** incident
- **Regions:** global
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `firehydrant_acknowledge_incident`
- `firehydrant_incident_statistics`
- `firehydrant_incident_timeline`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `incidents:read` | read incidents and their events | `firehydrant_incident_statistics`, `firehydrant_incident_timeline` |
| `incidents:write` | post a note onto an incident | `firehydrant_acknowledge_incident` |

**Pagination:**

- `list_incidents` — page_number on `page`
- `incident_timeline` — page_number on `page`

### `incident_io`

incident.io's record of what is happening: the open incidents, one incident's timeline, and the acknowledgement that says somebody is on it.

- **Category:** incident
- **Regions:** global
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `incident_io_acknowledge_incident`
- `incident_io_incident_statistics`
- `incident_io_incident_timeline`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `incidents:read` | read incidents and their updates | `incident_io_incident_statistics`, `incident_io_incident_timeline` |
| `incidents:write` | post an incident update | `incident_io_acknowledge_incident` |

**Pagination:**

- `list_incidents` — cursor on `after`
- `incident_timeline` — cursor on `after`

### `opsgenie`

Opsgenie alerts and their state: what is open, one alert's log, and the acknowledgement that stops the escalation.

- **Category:** incident
- **Regions:** us, eu
- **Credentials:** api_key
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `opsgenie_acknowledge_incident`
- `opsgenie_incident_statistics`
- `opsgenie_incident_timeline`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `read` | read alerts and their logs | `opsgenie_incident_statistics`, `opsgenie_incident_timeline` |
| `configuration access` | acknowledge an alert | `opsgenie_acknowledge_incident` |

**Pagination:**

- `list_incidents` — offset on `offset`
- `incident_timeline` — offset on `offset`

### `pagerduty`

Who is being paged and for what: the incidents PagerDuty is holding, one incident's log, and the acknowledgement that stops the escalation clock.

- **Category:** incident
- **Regions:** global
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `pagerduty_acknowledge_incident`
- `pagerduty_incident_statistics`
- `pagerduty_incident_timeline`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `incidents.read` | read incidents and their log entries | `pagerduty_incident_statistics`, `pagerduty_incident_timeline` |
| `incidents.write` | acknowledge an incident | `pagerduty_acknowledge_incident` |

**Pagination:**

- `list_incidents` — offset on `offset`
- `incident_timeline` — offset on `offset`

### `servicenow`

ServiceNow incident records: what is open, one incident's work notes, and the update that records an automated investigation.

- **Category:** incident
- **Regions:** instance
- **Credentials:** username, password
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `servicenow_acknowledge_incident`
- `servicenow_incident_statistics`
- `servicenow_incident_timeline`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `itil` | read and update incident records | `servicenow_incident_statistics`, `servicenow_incident_timeline`, `servicenow_acknowledge_incident` |
| `rest_service` | reach the Table API at all | `servicenow_incident_statistics`, `servicenow_incident_timeline`, `servicenow_acknowledge_incident` |

**Pagination:**

- `list_incidents` — offset on `sysparm_offset`
- `incident_timeline` — offset on `sysparm_offset`

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

### `azure_monitor`

KQL against a Log Analytics workspace: the shape of what a query matched, and the records behind it, for the estates whose telemetry lands in Azure.

- **Category:** logstore
- **Regions:** global
- **Credentials:** token, workspace
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `azure_monitor_log_statistics`
- `azure_monitor_sample_logs`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `Log Analytics Reader` | run KQL against the workspace | `azure_monitor_log_statistics`, `azure_monitor_sample_logs` |
| `workspace:metadata` | read the workspace schema, which the probe uses | `azure_monitor_log_statistics` |

**Pagination:**

- `search_logs` — cursor on `cursor`
- `recent_logs` — cursor on `cursor`

### `better_stack`

Better Stack's log search and the monitors it is currently reporting as down, for teams using it as both log store and uptime checker.

- **Category:** logstore
- **Regions:** global
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `better_stack_log_statistics`
- `better_stack_sample_logs`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `logs:read` | query the sources this token can see | `better_stack_log_statistics`, `better_stack_sample_logs` |
| `sources:read` | list the sources a query may name | `better_stack_log_statistics` |

**Pagination:**

- `search_logs` — cursor on `cursor`
- `recent_logs` — cursor on `cursor`

### `coralogix`

Coralogix log search over DataPrime or Lucene, counted by severity or application before any line is read.

- **Category:** logstore
- **Regions:** eu1, eu2, us1, us2, ap1, ap2
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `coralogix_log_statistics`
- `coralogix_sample_logs`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `DataQuerying` | run DataPrime and Lucene queries | `coralogix_log_statistics`, `coralogix_sample_logs` |
| `LogsQuerying` | read the log entries a query matched | `coralogix_sample_logs` |

**Pagination:**

- `search_logs` — cursor on `cursor`
- `recent_logs` — cursor on `cursor`

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

### `elasticsearch`

Search over Elasticsearch indices, counted by field before any document is read, for the deployments whose logs live there rather than in a hosted log product.

- **Category:** logstore
- **Regions:** self-hosted
- **Credentials:** api_key
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `elasticsearch_log_statistics`
- `elasticsearch_sample_logs`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `read` | search the indices this key is scoped to | `elasticsearch_log_statistics`, `elasticsearch_sample_logs` |
| `monitor` | read cluster health, which is what the connectivity probe uses | `elasticsearch_log_statistics` |

**Pagination:**

- `search_logs` — cursor on `search_after`
- `recent_logs` — cursor on `search_after`

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

### `opensearch`

Search over OpenSearch indices, counted by field before any document is read, for the deployments whose logs live in the fork rather than in Elasticsearch.

- **Category:** logstore
- **Regions:** self-hosted
- **Credentials:** username, password
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `opensearch_log_statistics`
- `opensearch_sample_logs`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `indices:data/read/search` | search the indices this user can see | `opensearch_log_statistics`, `opensearch_sample_logs` |
| `cluster:monitor/health` | read cluster health, which the connectivity probe uses | `opensearch_log_statistics` |

**Pagination:**

- `search_logs` — cursor on `search_after`
- `recent_logs` — cursor on `search_after`

### `sentry`

Application errors as Sentry groups them: which issues are open, how often each is firing, and the events behind the ones that matter.

- **Category:** logstore
- **Regions:** us, de, self-hosted
- **Credentials:** token, organisation
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `sentry_log_statistics`
- `sentry_sample_logs`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `project:read` | list projects and their issues | `sentry_log_statistics`, `sentry_sample_logs` |
| `event:read` | read the events behind an issue | `sentry_sample_logs` |

**Pagination:**

- `search_logs` — cursor on `cursor`
- `recent_logs` — cursor on `cursor`

### `splunk`

SPL search against Splunk, counted before it is read, for the estates whose logs have been in Splunk longer than the services producing them.

- **Category:** logstore
- **Regions:** self-hosted
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `splunk_log_statistics`
- `splunk_sample_logs`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `search` | run SPL searches in the app context | `splunk_log_statistics`, `splunk_sample_logs` |
| `rest_properties_get` | read server info, which the probe uses | `splunk_log_statistics` |

**Pagination:**

- `search_logs` — offset on `offset`
- `recent_logs` — offset on `offset`

### `victorialogs`

LogsQL against VictoriaLogs, counted by stream field before any line is read, for the estates that chose it for its ingest cost.

- **Category:** logstore
- **Regions:** self-hosted
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `victorialogs_log_statistics`
- `victorialogs_sample_logs`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `select` | run LogsQL queries against the tenant's streams | `victorialogs_log_statistics`, `victorialogs_sample_logs` |
| `hits` | read the hit counts the connectivity probe uses | `victorialogs_log_statistics` |

**Pagination:**

- `search_logs` — cursor on `start`
- `recent_logs` — cursor on `start`

### metrics

### `amplitude`

Amplitude's product analytics: how user-facing event volume moved during a window, and which annotations mark what changed.

- **Category:** metrics
- **Regions:** us, eu
- **Credentials:** username, password
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `amplitude_active_alerts`
- `amplitude_metric_statistics`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `events:read` | run event segmentation queries | `amplitude_metric_statistics` |
| `annotations:read` | read chart annotations | `amplitude_active_alerts` |

**Pagination:**

- `query_metric` — cursor on `cursor`
- `list_alerts` — cursor on `cursor`

### `groundcover`

groundcover's eBPF-derived service metrics and the monitors currently firing, for clusters instrumented without code changes.

- **Category:** metrics
- **Regions:** saas
- **Credentials:** api_key
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `groundcover_active_alerts`
- `groundcover_metric_statistics`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `metrics:read` | evaluate PromQL against the ingested series | `groundcover_metric_statistics` |
| `monitors:read` | list monitors and their current state | `groundcover_active_alerts` |

**Pagination:**

- `query_metric` — cursor on `start`
- `list_alerts` — cursor on `cursor`

### `new_relic`

NRQL over New Relic's telemetry, and the alert violations currently open, for the accounts whose metrics and events live there.

- **Category:** metrics
- **Regions:** us, eu
- **Credentials:** api_key
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `new_relic_active_alerts`
- `new_relic_metric_statistics`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `apm:read` | read application summaries and their health | `new_relic_metric_statistics` |
| `alerts:read` | read open alert violations | `new_relic_active_alerts` |

**Pagination:**

- `query_metric` — page_number on `page`
- `list_alerts` — page_number on `page`

### `posthog`

PostHog's product analytics: how event volume moved during a window, and which feature flags are currently on.

- **Category:** metrics
- **Regions:** us, eu, self-hosted
- **Credentials:** token, project_id
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `posthog_active_alerts`
- `posthog_metric_statistics`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `event:read` | read the project's events | `posthog_metric_statistics` |
| `feature_flag:read` | read feature flags and their state | `posthog_active_alerts` |

**Pagination:**

- `query_metric` — cursor on `after`
- `list_alerts` — cursor on `offset`

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

### `victoriametrics`

MetricsQL against VictoriaMetrics and the alerts vmalert is holding, for the estates that use it as a long-term Prometheus store.

- **Category:** metrics
- **Regions:** self-hosted
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `victoriametrics_active_alerts`
- `victoriametrics_metric_statistics`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `select` | evaluate MetricsQL over the stored series | `victoriametrics_metric_statistics` |
| `alerts:read` | read the alerts vmalert is holding | `victoriametrics_active_alerts` |

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

### ticketing

### `clickup`

What ClickUp already tracks: the tasks in a list, in what status, and which are worth reading before another is created.

- **Category:** ticketing
- **Regions:** global
- **Credentials:** api_key, list_id
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `clickup_issue_statistics`
- `clickup_recent_issues`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `tasks:read` | read tasks in the configured list | `clickup_issue_statistics`, `clickup_recent_issues` |
| `list:read` | read the list itself, which the probe uses | `clickup_issue_statistics` |

**Pagination:**

- `search_issues` — page_number on `page`
- `recent_issues` — page_number on `page`

### `confluence`

What has already been written down: the Confluence pages matching a search, and the ones most recently changed.

- **Category:** ticketing
- **Regions:** site
- **Credentials:** username, password
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `confluence_issue_statistics`
- `confluence_recent_issues`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `read:confluence-content.all` | search and read pages | `confluence_issue_statistics`, `confluence_recent_issues` |
| `read:confluence-space.summary` | list spaces, which the probe uses | `confluence_issue_statistics` |

**Pagination:**

- `search_issues` — offset on `start`
- `recent_issues` — offset on `start`

### `google_docs`

What the team has written in Google Docs: the documents matching a search, and the ones most recently modified.

- **Category:** ticketing
- **Regions:** global
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `google_docs_issue_statistics`
- `google_docs_recent_issues`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `drive.readonly` | list and read document metadata | `google_docs_issue_statistics`, `google_docs_recent_issues` |
| `drive.about.get` | read the token's own account, which the probe uses | `google_docs_issue_statistics` |

**Pagination:**

- `search_issues` — page_token on `pageToken`
- `recent_issues` — page_token on `pageToken`

### `jira`

What Jira already knows about a symptom: how many issues match, in what state, and which ones are worth reading before another is opened.

- **Category:** ticketing
- **Regions:** site
- **Credentials:** username, password
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `jira_issue_statistics`
- `jira_recent_issues`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `Browse Projects` | search and read issues in a project | `jira_issue_statistics`, `jira_recent_issues` |
| `read:jira-user` | read the token owner, which the probe uses | `jira_issue_statistics` |

**Pagination:**

- `search_issues` — offset on `startAt`
- `recent_issues` — offset on `startAt`

### `linear`

What Linear already tracks about a symptom: how many issues match, in what state, and which are worth reading before another is filed.

- **Category:** ticketing
- **Regions:** global
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `linear_issue_statistics`
- `linear_recent_issues`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `read` | read issues and their state | `linear_issue_statistics`, `linear_recent_issues` |
| `viewer` | read the key's own identity, which the probe uses | `linear_issue_statistics` |

**Pagination:**

- `search_issues` — cursor on `after`
- `recent_issues` — cursor on `after`

### `notion`

What the team has written in Notion: the pages matching a search, and the ones most recently edited.

- **Category:** ticketing
- **Regions:** global
- **Credentials:** token, api_version
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `notion_issue_statistics`
- `notion_recent_issues`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `read content` | search and read pages the integration is shared with | `notion_issue_statistics`, `notion_recent_issues` |
| `read user information` | read the bot user, which the probe uses | `notion_issue_statistics` |

**Pagination:**

- `search_issues` — cursor on `start_cursor`
- `recent_issues` — cursor on `start_cursor`

### `trello`

What a Trello board is holding: the cards on it, which list each is in, and which were touched most recently.

- **Category:** ticketing
- **Regions:** global
- **Credentials:** token, board
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `trello_issue_statistics`
- `trello_recent_issues`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `read` | read boards, lists, and cards | `trello_issue_statistics`, `trello_recent_issues` |
| `boards:read` | read the configured board, which the probe uses | `trello_issue_statistics` |

**Pagination:**

- `search_issues` — cursor on `before`
- `recent_issues` — cursor on `before`

### tracing

### `honeycomb`

Honeycomb's query engine over trace events: where latency and errors concentrate in a dataset, and the slowest traces behind that concentration.

- **Category:** tracing
- **Regions:** us, eu
- **Credentials:** api_key, dataset
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `honeycomb_slow_traces`
- `honeycomb_trace_statistics`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `query` | run queries against a dataset's events | `honeycomb_trace_statistics`, `honeycomb_slow_traces` |
| `auth:read` | read what the key is allowed to do, which the probe uses | `honeycomb_trace_statistics` |

**Pagination:**

- `search_traces` — cursor on `cursor`
- `slow_traces` — cursor on `cursor`

### `jaeger`

Jaeger's trace store: where a service's operations concentrate latency, and the slowest traces behind that concentration.

- **Category:** tracing
- **Regions:** self-hosted
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `jaeger_slow_traces`
- `jaeger_trace_statistics`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `traces:read` | query the trace store | `jaeger_trace_statistics`, `jaeger_slow_traces` |
| `services:read` | list services, which the probe uses | `jaeger_trace_statistics` |

**Pagination:**

- `search_traces` — offset on `offset`
- `slow_traces` — offset on `offset`

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

### `tempo`

TraceQL against Grafana Tempo: which traces match a latency or error condition, and the slowest of them, for estates storing traces in object storage.

- **Category:** tracing
- **Regions:** self-hosted
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `tempo_slow_traces`
- `tempo_trace_statistics`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `traces:read` | search the trace store | `tempo_trace_statistics`, `tempo_slow_traces` |
| `echo` | the unauthenticated liveness endpoint the probe uses | `tempo_trace_statistics` |

**Pagination:**

- `search_traces` — cursor on `start`
- `slow_traces` — cursor on `start`

### vcs

### `bitbucket`

What landed in a Bitbucket workspace: the repositories that changed recently and the pull requests merged into them.

- **Category:** vcs
- **Regions:** global
- **Credentials:** username, password, workspace
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `bitbucket_change_statistics`
- `bitbucket_recent_changes`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `repository:read` | list repositories in the workspace | `bitbucket_change_statistics`, `bitbucket_recent_changes` |
| `pullrequest:read` | read pull requests on those repositories | `bitbucket_recent_changes` |

**Pagination:**

- `list_commits` — cursor on `page`
- `list_pull_requests` — cursor on `page`

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

### `gitlab`

What landed in a GitLab project: the commits on a branch and the merge requests recently merged into it.

- **Category:** vcs
- **Regions:** gitlab.com, self-managed
- **Credentials:** api_key
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `gitlab_change_statistics`
- `gitlab_recent_changes`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `read_api` | read projects, commits, and merge requests | `gitlab_change_statistics`, `gitlab_recent_changes` |
| `read_user` | read the token's own identity, which the probe uses | `gitlab_change_statistics` |

**Pagination:**

- `list_commits` — page_number on `page`
- `list_pull_requests` — page_number on `page`

### `sourcegraph`

Code search across every repository at once: where a symbol, a string, or a configuration key actually appears.

- **Category:** vcs
- **Regions:** self-hosted
- **Credentials:** token
- **SDK strategy:** `direct_client`
- **Parity:** complete
- **Health:** unknown

**Capabilities:**

- `sourcegraph_change_statistics`
- `sourcegraph_recent_changes`

**Permissions:**

| Permission | Grants | Without it |
|---|---|---|
| `search` | run code searches across the indexed repositories | `sourcegraph_change_statistics`, `sourcegraph_recent_changes` |
| `user:read` | read the token's own identity, which the probe uses | `sourcegraph_change_statistics` |

**Pagination:**

- `list_commits` — cursor on `cursor`
- `list_pull_requests` — cursor on `cursor`

## Recorded gaps

A vendor nobody wrote is a vendor nobody is told about, so the omissions are a declaration rather than an absence. Each names why it cannot be built the way every other integration is, and what would have to change.

### `postgresql` — PostgreSQL

- **Category:** database
- **Why not:** The server speaks its own binary wire protocol on its own port. The credential proxy is HTTP: it attaches a secret to a request, and there is no request here to attach one to. Building the client anyway would mean holding the credential in the agent's process, which Article IV forbids outright.
- **What would change it:** A protocol bridge that terminates the credential outside the agent process, the way the HTTP proxy does. Until there is one, a managed PostgreSQL is reachable through its cloud control plane — `aws_rds` for RDS and Aurora, `supabase` for Supabase — which answers instance state, failovers, and parameter changes but not sessions or query plans.

### `mysql` — MySQL

- **Category:** database
- **Why not:** The server speaks its own binary wire protocol on its own port. The credential proxy is HTTP: it attaches a secret to a request, and there is no request here to attach one to. Building the client anyway would mean holding the credential in the agent's process, which Article IV forbids outright.
- **What would change it:** The same bridge PostgreSQL needs. A managed MySQL is reachable through `aws_rds`, which answers instance state and the event history and not what is executing inside the engine.

### `mariadb` — MariaDB

- **Category:** database
- **Why not:** The server speaks its own binary wire protocol on its own port. The credential proxy is HTTP: it attaches a secret to a request, and there is no request here to attach one to. Building the client anyway would mean holding the credential in the agent's process, which Article IV forbids outright.
- **What would change it:** The same bridge MySQL needs — MariaDB speaks the MySQL protocol and has the same constraint for the same reason.

### `mongodb` — MongoDB

- **Category:** database
- **Why not:** The server speaks its own binary wire protocol on its own port. The credential proxy is HTTP: it attaches a secret to a request, and there is no request here to attach one to. Building the client anyway would mean holding the credential in the agent's process, which Article IV forbids outright.
- **What would change it:** A protocol bridge, or Atlas: `mongodb_atlas` reaches a hosted deployment through the Atlas administration API and answers process and cluster state. A self-hosted replica set on port 27017 has no equivalent.

### `redis_server` — Redis (self-hosted)

- **Category:** database
- **Why not:** The server speaks its own binary wire protocol on its own port. The credential proxy is HTTP: it attaches a secret to a request, and there is no request here to attach one to. Building the client anyway would mean holding the credential in the agent's process, which Article IV forbids outright.
- **What would change it:** A protocol bridge. `redis` is in the catalogue and reads Redis Cloud's control plane over HTTP; the keyspace, the slow log, and `INFO` on a self-hosted server are RESP and are not reachable.

### `smtp` — SMTP

- **Category:** communication
- **Why not:** SMTP is a stateful line protocol over its own port, not a request-response API. The credential proxy attaches a secret to an HTTP request; an SMTP session has no such request, and authentication happens inside a conversation the proxy cannot participate in.
- **What would change it:** Either a protocol bridge that terminates the SMTP credential outside the agent process, or delivery through a vendor with an HTTP API — `twilio` and `pushover` are both in the catalogue and reach a person without an SMTP session.

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
