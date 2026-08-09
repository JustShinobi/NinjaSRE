# Capability reference

Generated from the declarations by `tools/generate_capability_docs.py`. Do not
edit by hand — edit the capability and regenerate, or the two will disagree and
this file will be the one that is wrong.

190 tools and 88 skills, 23 of them approval-gated.

## Skills

### `cicd-argocd`

What Argo CD has actually applied: which applications are synced and healthy, and the ones that are not.

- **Domain:** cicd
- **Applies to alerts from:** argocd
- **Requires:** argocd

**Directs:**

- `argocd_pipeline_statistics`
- `argocd_failed_runs`

### `cicd-jenkins`

Jenkins build history: how a job has been doing lately, and the builds that failed, for the estates whose pipelines still run there.

- **Domain:** cicd
- **Applies to alerts from:** jenkins
- **Requires:** jenkins

**Directs:**

- `jenkins_pipeline_statistics`
- `jenkins_failed_runs`

### `cicd-railway`

Railway deployments and their status, for the services this project runs on it.

- **Domain:** cicd
- **Applies to alerts from:** railway
- **Requires:** railway

**Directs:**

- `railway_pipeline_statistics`
- `railway_failed_runs`

### `cicd-vercel`

Vercel deployments: how the recent ones have gone for a project, and the ones that errored, which is usually the whole story for a frontend incident.

- **Domain:** cicd
- **Applies to alerts from:** vercel
- **Requires:** vercel

**Directs:**

- `vercel_pipeline_statistics`
- `vercel_failed_runs`

### `cloud_control_plane-aws_cloudtrail`

Who changed what in this AWS account, and when. The change history most incidents turn out to need and most investigations reach for too late.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** aws_cloudtrail
- **Requires:** aws_cloudtrail

**Directs:**

- `aws_cloudtrail_resource_inventory`
- `aws_cloudtrail_recent_changes`

### `cloud_control_plane-aws_ec2`

EC2 instance state for a region: how many instances are in which state, and the instances themselves with their type, zone, and launch time.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** aws_ec2
- **Requires:** aws_ec2

**Directs:**

- `aws_ec2_resource_inventory`
- `aws_ec2_recent_changes`

### `cloud_control_plane-aws_ecs`

The ECS control plane: which clusters this account runs and which task definitions have been registered, which is where a deployment shows up.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** aws_ecs
- **Requires:** aws_ecs

**Directs:**

- `aws_ecs_resource_inventory`
- `aws_ecs_recent_changes`

### `cloud_control_plane-aws_eks`

The EKS control plane: which clusters this account runs, their version and status, and the cluster updates that have been applied to them.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** aws_eks
- **Requires:** aws_eks

**Directs:**

- `aws_eks_resource_inventory`
- `aws_eks_recent_changes`

### `cloud_control_plane-aws_elb`

Elastic Load Balancing state: which load balancers exist and in what state, and the target groups behind them.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** aws_elb
- **Requires:** aws_elb

**Directs:**

- `aws_elb_resource_inventory`
- `aws_elb_recent_changes`

### `cloud_control_plane-aws_lambda`

The Lambda control plane: which functions exist, on which runtime and memory setting, and when each was last modified.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** aws_lambda
- **Requires:** aws_lambda

**Directs:**

- `aws_lambda_resource_inventory`
- `aws_lambda_recent_changes`

### `cloud_control_plane-aws_rds`

The RDS control plane: which database instances exist and in what state, and the events RDS recorded against them — failovers, restarts, parameter changes.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** aws_rds
- **Requires:** aws_rds

**Directs:**

- `aws_rds_resource_inventory`
- `aws_rds_recent_changes`

### `cloud_control_plane-aws_s3`

What is in the bucket this team configured: the objects and their storage class, and the version history, which is the closest S3 has to a change log.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** aws_s3
- **Requires:** aws_s3

**Directs:**

- `aws_s3_resource_inventory`
- `aws_s3_recent_changes`

### `cloud_control_plane-azure`

The Azure Resource Manager control plane: what exists in a subscription, and the activity log entries that changed it.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** azure
- **Requires:** azure

**Directs:**

- `azure_resource_inventory`
- `azure_recent_changes`

### `cloud_control_plane-docker`

The Docker Engine API: which containers exist and in what state, and the engine events that changed them.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** docker
- **Requires:** docker

**Directs:**

- `docker_resource_inventory`
- `docker_recent_changes`

### `cloud_control_plane-flagd`

OpenFeature's flagd: which feature flags this deployment is serving and in what state, which is the change history nothing else records.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** flagd
- **Requires:** flagd

**Directs:**

- `flagd_resource_inventory`
- `flagd_recent_changes`

### `cloud_control_plane-gcp`

The Google Cloud control plane through Cloud Asset Inventory and Cloud Logging: what exists in a project, and the admin activity that changed it.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** gcp
- **Requires:** gcp

**Directs:**

- `gcp_resource_inventory`
- `gcp_recent_changes`

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
- `proxmox_storage_pressure`
- `proxmox_protection_gaps`

### `cloud_control_plane-proxmox_backup_server`

A snapshot nobody verified is a file. Check verification and garbage collection, not just usage.

- **Domain:** cloud_control_plane
- **Applies to alerts from:** proxmox, proxmox_backup_server, alertmanager
- **Requires:** proxmox_backup_server

**Directs:**

- `proxmox_backup_server_datastore_health`

### `communication-discord`

A Discord channel used for incident response: what has been said recently, and a finding posted into it.

- **Domain:** communication
- **Applies to alerts from:** discord
- **Requires:** discord

**Directs:**

- `discord_recent_messages`
- `discord_post_message`

### `communication-microsoft_teams`

The Teams channel an incident is being run from: what has been said, and a finding posted where the responders are.

- **Domain:** communication
- **Applies to alerts from:** microsoft_teams
- **Requires:** microsoft_teams

**Directs:**

- `microsoft_teams_recent_messages`
- `microsoft_teams_post_message`

### `communication-pushover`

Pushover as a last-resort notification path: which delivery groups exist, and a finding pushed to a responder's device.

- **Domain:** communication
- **Applies to alerts from:** pushover
- **Requires:** pushover

**Directs:**

- `pushover_recent_messages`
- `pushover_post_message`

### `communication-rocket_chat`

A Rocket.Chat channel used for incident response: what has been said, and a finding posted into it.

- **Domain:** communication
- **Applies to alerts from:** rocket_chat
- **Requires:** rocket_chat

**Directs:**

- `rocket_chat_recent_messages`
- `rocket_chat_post_message`

### `communication-slack`

The conversation an incident is already happening in: what responders have said, and a finding delivered where they will read it.

- **Domain:** communication
- **Applies to alerts from:** slack
- **Requires:** slack

**Directs:**

- `slack_recent_messages`
- `slack_post_message`

### `communication-telegram`

A Telegram chat used as an alerting channel: what has arrived recently, and a finding delivered into it.

- **Domain:** communication
- **Applies to alerts from:** telegram
- **Requires:** telegram

**Directs:**

- `telegram_recent_messages`
- `telegram_post_message`

### `communication-twilio`

Twilio as an SMS notification path: the messages this account has sent recently, and a finding delivered to a responder's phone.

- **Domain:** communication
- **Applies to alerts from:** twilio
- **Requires:** twilio

**Directs:**

- `twilio_recent_messages`
- `twilio_post_message`

### `communication-whatsapp`

A WhatsApp Business number used for on-call notification: the message templates available, and a finding delivered to a responder.

- **Domain:** communication
- **Applies to alerts from:** whatsapp
- **Requires:** whatsapp

**Directs:**

- `whatsapp_recent_messages`
- `whatsapp_post_message`

### `data_platform-airflow`

Airflow's scheduler state: which DAG runs are in which state, and the task instances that failed, which is where a data-freshness incident starts.

- **Domain:** data_platform
- **Applies to alerts from:** airflow
- **Requires:** airflow

**Directs:**

- `airflow_pipeline_health`
- `airflow_recent_failures`

### `data_platform-dagster`

Dagster run state through its GraphQL API: which runs are in which status, and the failures behind a stale asset.

- **Domain:** data_platform
- **Applies to alerts from:** dagster
- **Requires:** dagster

**Directs:**

- `dagster_pipeline_health`
- `dagster_recent_failures`

### `data_platform-flink`

Flink's JobManager REST API: which jobs are running, and the ones that failed or restarted, which is where a streaming backlog starts.

- **Domain:** data_platform
- **Applies to alerts from:** flink
- **Requires:** flink

**Directs:**

- `flink_pipeline_health`
- `flink_recent_failures`

### `data_platform-kafka`

Kafka through its REST Proxy: which topics and consumer groups exist on a cluster, and which groups are not in a stable state.

- **Domain:** data_platform
- **Applies to alerts from:** kafka
- **Requires:** kafka

**Directs:**

- `kafka_pipeline_health`
- `kafka_recent_failures`

### `data_platform-prefect`

Prefect flow runs: which are in which state, and the ones that failed, for the estates orchestrating their pipelines with it.

- **Domain:** data_platform
- **Applies to alerts from:** prefect
- **Requires:** prefect

**Directs:**

- `prefect_pipeline_health`
- `prefect_recent_failures`

### `data_platform-rabbitmq`

RabbitMQ's management API: which queues exist and how deep they are, which is the first question of every message-backlog incident.

- **Domain:** data_platform
- **Applies to alerts from:** rabbitmq
- **Requires:** rabbitmq

**Directs:**

- `rabbitmq_pipeline_health`
- `rabbitmq_recent_failures`

### `data_platform-spark`

Spark's history and status API: which applications and jobs are in which state, and the ones that failed.

- **Domain:** data_platform
- **Applies to alerts from:** spark
- **Requires:** spark

**Directs:**

- `spark_pipeline_health`
- `spark_recent_failures`

### `data_platform-temporal`

Temporal workflow executions over its HTTP API: which are open, which failed, and how that distribution has changed.

- **Domain:** data_platform
- **Applies to alerts from:** temporal
- **Requires:** temporal

**Directs:**

- `temporal_pipeline_health`
- `temporal_recent_failures`

### `database-azure_sql`

Azure SQL through Resource Manager: which databases exist in a subscription and in what state, and their recent service-level events.

- **Domain:** database
- **Applies to alerts from:** azure_sql
- **Requires:** azure_sql

**Directs:**

- `azure_sql_session_statistics`
- `azure_sql_slow_queries`

### `database-bigquery`

BigQuery job state for a project: what is running or queued, and the jobs that took longest, which is where a data-freshness incident usually starts.

- **Domain:** database
- **Applies to alerts from:** bigquery
- **Requires:** bigquery

**Directs:**

- `bigquery_session_statistics`
- `bigquery_slow_queries`

### `database-clickhouse`

ClickHouse over its HTTP interface: what the server is currently executing, and the slowest queries in the log.

- **Domain:** database
- **Applies to alerts from:** clickhouse
- **Requires:** clickhouse

**Directs:**

- `clickhouse_session_statistics`
- `clickhouse_slow_queries`

### `database-mongodb_atlas`

The Atlas control plane: which clusters and processes exist in a project, and the slow-query entries Atlas's performance advisor has collected.

- **Domain:** database
- **Applies to alerts from:** mongodb_atlas
- **Requires:** mongodb_atlas

**Directs:**

- `mongodb_atlas_session_statistics`
- `mongodb_atlas_slow_queries`

### `database-redis`

The Redis Cloud control plane: which databases exist in a subscription and in what state, which is what an HTTP-reachable Redis can answer.

- **Domain:** database
- **Applies to alerts from:** redis
- **Requires:** redis

**Directs:**

- `redis_session_statistics`
- `redis_slow_queries`

### `database-snowflake`

Snowflake over its SQL REST API: what is running in the account now, and the slowest statements the query history recorded.

- **Domain:** database
- **Applies to alerts from:** snowflake
- **Requires:** snowflake

**Directs:**

- `snowflake_session_statistics`
- `snowflake_slow_queries`

### `database-supabase`

The Supabase management API: which projects exist in an organisation and in what state, for the estates that run their Postgres there.

- **Domain:** database
- **Applies to alerts from:** supabase
- **Requires:** supabase

**Directs:**

- `supabase_session_statistics`
- `supabase_slow_queries`

### `incident-alertmanager`

What Prometheus Alertmanager is currently holding: which alerts are firing, how they are grouped, and which are silenced rather than resolved.

- **Domain:** incident
- **Applies to alerts from:** alertmanager
- **Requires:** alertmanager

**Directs:**

- `alertmanager_incident_statistics`
- `alertmanager_incident_timeline`
- `alertmanager_acknowledge_incident`

### `incident-blameless`

Blameless's incident record: what is open, one incident's events, and the update that says an automated investigation is under way.

- **Domain:** incident
- **Applies to alerts from:** blameless
- **Requires:** blameless

**Directs:**

- `blameless_incident_statistics`
- `blameless_incident_timeline`
- `blameless_acknowledge_incident`

### `incident-firehydrant`

FireHydrant's incident record: what is active, one incident's events, and the note that says an automated investigation has started.

- **Domain:** incident
- **Applies to alerts from:** firehydrant
- **Requires:** firehydrant

**Directs:**

- `firehydrant_incident_statistics`
- `firehydrant_incident_timeline`
- `firehydrant_acknowledge_incident`

### `incident-incident_io`

incident.io's record of what is happening: the open incidents, one incident's timeline, and the acknowledgement that says somebody is on it.

- **Domain:** incident
- **Applies to alerts from:** incident_io
- **Requires:** incident_io

**Directs:**

- `incident_io_incident_statistics`
- `incident_io_incident_timeline`
- `incident_io_acknowledge_incident`

### `incident-opsgenie`

Opsgenie alerts and their state: what is open, one alert's log, and the acknowledgement that stops the escalation.

- **Domain:** incident
- **Applies to alerts from:** opsgenie
- **Requires:** opsgenie

**Directs:**

- `opsgenie_incident_statistics`
- `opsgenie_incident_timeline`
- `opsgenie_acknowledge_incident`

### `incident-pagerduty`

Who is being paged and for what: the incidents PagerDuty is holding, one incident's log, and the acknowledgement that stops the escalation clock.

- **Domain:** incident
- **Applies to alerts from:** pagerduty
- **Requires:** pagerduty

**Directs:**

- `pagerduty_incident_statistics`
- `pagerduty_incident_timeline`
- `pagerduty_acknowledge_incident`

### `incident-servicenow`

ServiceNow incident records: what is open, one incident's work notes, and the update that records an automated investigation.

- **Domain:** incident
- **Applies to alerts from:** servicenow
- **Requires:** servicenow

**Directs:**

- `servicenow_incident_statistics`
- `servicenow_incident_timeline`
- `servicenow_acknowledge_incident`

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

### `logstore-azure_monitor`

KQL against a Log Analytics workspace: the shape of what a query matched, and the records behind it, for the estates whose telemetry lands in Azure.

- **Domain:** logstore
- **Applies to alerts from:** azure_monitor
- **Requires:** azure_monitor

**Directs:**

- `azure_monitor_log_statistics`
- `azure_monitor_sample_logs`

### `logstore-better_stack`

Better Stack's log search and the monitors it is currently reporting as down, for teams using it as both log store and uptime checker.

- **Domain:** logstore
- **Applies to alerts from:** better_stack
- **Requires:** better_stack

**Directs:**

- `better_stack_log_statistics`
- `better_stack_sample_logs`

### `logstore-coralogix`

Coralogix log search over DataPrime or Lucene, counted by severity or application before any line is read.

- **Domain:** logstore
- **Applies to alerts from:** coralogix
- **Requires:** coralogix

**Directs:**

- `coralogix_log_statistics`
- `coralogix_sample_logs`

### `logstore-datadog`

Datadog log search. Aggregate before sampling, and compare against normal.

- **Domain:** logstore
- **Applies to alerts from:** datadog
- **Requires:** datadog

**Directs:**

- `datadog_log_statistics`
- `datadog_sample_logs`

### `logstore-elasticsearch`

Search over Elasticsearch indices, counted by field before any document is read, for the deployments whose logs live there rather than in a hosted log product.

- **Domain:** logstore
- **Applies to alerts from:** elasticsearch
- **Requires:** elasticsearch

**Directs:**

- `elasticsearch_log_statistics`
- `elasticsearch_sample_logs`

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

### `logstore-opensearch`

Search over OpenSearch indices, counted by field before any document is read, for the deployments whose logs live in the fork rather than in Elasticsearch.

- **Domain:** logstore
- **Applies to alerts from:** opensearch
- **Requires:** opensearch

**Directs:**

- `opensearch_log_statistics`
- `opensearch_sample_logs`

### `logstore-sentry`

Application errors as Sentry groups them: which issues are open, how often each is firing, and the events behind the ones that matter.

- **Domain:** logstore
- **Applies to alerts from:** sentry
- **Requires:** sentry

**Directs:**

- `sentry_log_statistics`
- `sentry_sample_logs`

### `logstore-splunk`

SPL search against Splunk, counted before it is read, for the estates whose logs have been in Splunk longer than the services producing them.

- **Domain:** logstore
- **Applies to alerts from:** splunk
- **Requires:** splunk

**Directs:**

- `splunk_log_statistics`
- `splunk_sample_logs`

### `logstore-victorialogs`

LogsQL against VictoriaLogs, counted by stream field before any line is read, for the estates that chose it for its ingest cost.

- **Domain:** logstore
- **Applies to alerts from:** victorialogs
- **Requires:** victorialogs

**Directs:**

- `victorialogs_log_statistics`
- `victorialogs_sample_logs`

### `metrics-amplitude`

Amplitude's product analytics: how user-facing event volume moved during a window, and which annotations mark what changed.

- **Domain:** metrics
- **Applies to alerts from:** amplitude
- **Requires:** amplitude

**Directs:**

- `amplitude_metric_statistics`
- `amplitude_active_alerts`

### `metrics-groundcover`

groundcover's eBPF-derived service metrics and the monitors currently firing, for clusters instrumented without code changes.

- **Domain:** metrics
- **Applies to alerts from:** groundcover
- **Requires:** groundcover

**Directs:**

- `groundcover_metric_statistics`
- `groundcover_active_alerts`

### `metrics-new_relic`

NRQL over New Relic's telemetry, and the alert violations currently open, for the accounts whose metrics and events live there.

- **Domain:** metrics
- **Applies to alerts from:** new_relic
- **Requires:** new_relic

**Directs:**

- `new_relic_metric_statistics`
- `new_relic_active_alerts`

### `metrics-posthog`

PostHog's product analytics: how event volume moved during a window, and which feature flags are currently on.

- **Domain:** metrics
- **Applies to alerts from:** posthog
- **Requires:** posthog

**Directs:**

- `posthog_metric_statistics`
- `posthog_active_alerts`

### `metrics-prometheus`

PromQL evaluation and the alert rules currently firing, from the server that holds the series rather than from a dashboard on top of it.

- **Domain:** metrics
- **Applies to alerts from:** prometheus
- **Requires:** prometheus

**Directs:**

- `prometheus_metric_statistics`
- `prometheus_active_alerts`

### `metrics-victoriametrics`

MetricsQL against VictoriaMetrics and the alerts vmalert is holding, for the estates that use it as a long-term Prometheus store.

- **Domain:** metrics
- **Applies to alerts from:** victoriametrics
- **Requires:** victoriametrics

**Directs:**

- `victoriametrics_metric_statistics`
- `victoriametrics_active_alerts`

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

### `ticketing-clickup`

What ClickUp already tracks: the tasks in a list, in what status, and which are worth reading before another is created.

- **Domain:** ticketing
- **Applies to alerts from:** clickup
- **Requires:** clickup

**Directs:**

- `clickup_issue_statistics`
- `clickup_recent_issues`

### `ticketing-confluence`

What has already been written down: the Confluence pages matching a search, and the ones most recently changed.

- **Domain:** ticketing
- **Applies to alerts from:** confluence
- **Requires:** confluence

**Directs:**

- `confluence_issue_statistics`
- `confluence_recent_issues`

### `ticketing-google_docs`

What the team has written in Google Docs: the documents matching a search, and the ones most recently modified.

- **Domain:** ticketing
- **Applies to alerts from:** google_docs
- **Requires:** google_docs

**Directs:**

- `google_docs_issue_statistics`
- `google_docs_recent_issues`

### `ticketing-jira`

What Jira already knows about a symptom: how many issues match, in what state, and which ones are worth reading before another is opened.

- **Domain:** ticketing
- **Applies to alerts from:** jira
- **Requires:** jira

**Directs:**

- `jira_issue_statistics`
- `jira_recent_issues`

### `ticketing-linear`

What Linear already tracks about a symptom: how many issues match, in what state, and which are worth reading before another is filed.

- **Domain:** ticketing
- **Applies to alerts from:** linear
- **Requires:** linear

**Directs:**

- `linear_issue_statistics`
- `linear_recent_issues`

### `ticketing-notion`

What the team has written in Notion: the pages matching a search, and the ones most recently edited.

- **Domain:** ticketing
- **Applies to alerts from:** notion
- **Requires:** notion

**Directs:**

- `notion_issue_statistics`
- `notion_recent_issues`

### `ticketing-trello`

What a Trello board is holding: the cards on it, which list each is in, and which were touched most recently.

- **Domain:** ticketing
- **Applies to alerts from:** trello
- **Requires:** trello

**Directs:**

- `trello_issue_statistics`
- `trello_recent_issues`

### `tracing-honeycomb`

Honeycomb's query engine over trace events: where latency and errors concentrate in a dataset, and the slowest traces behind that concentration.

- **Domain:** tracing
- **Applies to alerts from:** honeycomb
- **Requires:** honeycomb

**Directs:**

- `honeycomb_trace_statistics`
- `honeycomb_slow_traces`

### `tracing-jaeger`

Jaeger's trace store: where a service's operations concentrate latency, and the slowest traces behind that concentration.

- **Domain:** tracing
- **Applies to alerts from:** jaeger
- **Requires:** jaeger

**Directs:**

- `jaeger_trace_statistics`
- `jaeger_slow_traces`

### `tracing-signoz`

SigNoz's span store: where latency and errors concentrate for a service, and the slowest traces behind that concentration.

- **Domain:** tracing
- **Applies to alerts from:** signoz
- **Requires:** signoz

**Directs:**

- `signoz_trace_statistics`
- `signoz_slow_traces`

### `tracing-tempo`

TraceQL against Grafana Tempo: which traces match a latency or error condition, and the slowest of them, for estates storing traces in object storage.

- **Domain:** tracing
- **Applies to alerts from:** tempo
- **Requires:** tempo

**Directs:**

- `tempo_trace_statistics`
- `tempo_slow_traces`

### `vcs-bitbucket`

What landed in a Bitbucket workspace: the repositories that changed recently and the pull requests merged into them.

- **Domain:** vcs
- **Applies to alerts from:** bitbucket
- **Requires:** bitbucket

**Directs:**

- `bitbucket_change_statistics`
- `bitbucket_recent_changes`

### `vcs-github`

What landed in a repository and when: the commits on its default branch and the pull requests recently merged into it.

- **Domain:** vcs
- **Applies to alerts from:** github
- **Requires:** github

**Directs:**

- `github_change_statistics`
- `github_recent_changes`

### `vcs-gitlab`

What landed in a GitLab project: the commits on a branch and the merge requests recently merged into it.

- **Domain:** vcs
- **Applies to alerts from:** gitlab
- **Requires:** gitlab

**Directs:**

- `gitlab_change_statistics`
- `gitlab_recent_changes`

### `vcs-sourcegraph`

Code search across every repository at once: where a symbol, a string, or a configuration key actually appears.

- **Domain:** vcs
- **Applies to alerts from:** sourcegraph
- **Requires:** sourcegraph

**Directs:**

- `sourcegraph_change_statistics`
- `sourcegraph_recent_changes`

## Tools

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

#### `jenkins_failed_runs`

Return the failed runs for a project in a window, newest first and capped, with the stage that failed. Use it after the statistics: the first failure in a run of them is the one worth reading.

- **Side effect:** `read` — reads only
- **Evidence:** event from jenkins
- **Parallel safe:** yes
- **Requires:** jenkins

**Use when:**

- finding the first failing run after a period of green ones
- checking whether a deployment succeeded before blaming the release

**Not for:**

- whether failures are unusual, which the statistics answer
- an application error unrelated to any build

#### `jenkins_pipeline_statistics`

Count the pipeline runs for a project in a window, grouped by outcome. It says whether a failure is new, chronic, or the first of its kind, which decides whether the pipeline is the story at all.

- **Side effect:** `read` — reads only
- **Evidence:** event from jenkins
- **Parallel safe:** yes
- **Requires:** jenkins

**Use when:**

- an incident following a deployment whose history is unknown
- deciding whether a red build is new or has been red for a week

**Not for:**

- why one run failed, which needs that run rather than a count
- a runtime failure with no build in the window

#### `railway_failed_runs`

Return the failed runs for a project in a window, newest first and capped, with the stage that failed. Use it after the statistics: the first failure in a run of them is the one worth reading.

- **Side effect:** `read` — reads only
- **Evidence:** event from railway
- **Parallel safe:** yes
- **Requires:** railway

**Use when:**

- finding the first failing run after a period of green ones
- checking whether a deployment succeeded before blaming the release

**Not for:**

- whether failures are unusual, which the statistics answer
- an application error unrelated to any build

#### `railway_pipeline_statistics`

Count the pipeline runs for a project in a window, grouped by outcome. It says whether a failure is new, chronic, or the first of its kind, which decides whether the pipeline is the story at all.

- **Side effect:** `read` — reads only
- **Evidence:** event from railway
- **Parallel safe:** yes
- **Requires:** railway

**Use when:**

- an incident following a deployment whose history is unknown
- deciding whether a red build is new or has been red for a week

**Not for:**

- why one run failed, which needs that run rather than a count
- a runtime failure with no build in the window

#### `vercel_failed_runs`

Return the failed runs for a project in a window, newest first and capped, with the stage that failed. Use it after the statistics: the first failure in a run of them is the one worth reading.

- **Side effect:** `read` — reads only
- **Evidence:** event from vercel
- **Parallel safe:** yes
- **Requires:** vercel

**Use when:**

- finding the first failing run after a period of green ones
- checking whether a deployment succeeded before blaming the release

**Not for:**

- whether failures are unusual, which the statistics answer
- an application error unrelated to any build

#### `vercel_pipeline_statistics`

Count the pipeline runs for a project in a window, grouped by outcome. It says whether a failure is new, chronic, or the first of its kind, which decides whether the pipeline is the story at all.

- **Side effect:** `read` — reads only
- **Evidence:** event from vercel
- **Parallel safe:** yes
- **Requires:** vercel

**Use when:**

- an incident following a deployment whose history is unknown
- deciding whether a red build is new or has been red for a week

**Not for:**

- why one run failed, which needs that run rather than a count
- a runtime failure with no build in the window

### cloud_control_plane

#### `aws_cloudtrail_recent_changes`

Return the control-plane changes in a window, newest first and capped. Most incidents follow a change, and this is the capability that turns 'it started at 14:05' into a specific thing somebody did.

- **Side effect:** `read` — reads only
- **Evidence:** change from aws_cloudtrail
- **Parallel safe:** yes
- **Requires:** aws_cloudtrail

**Use when:**

- an incident whose start time is known and whose cause is not
- checking whether anything was changed shortly before the symptom

**Not for:**

- how much of the estate is affected, which the inventory answers
- a symptom with no change window, where the history is noise

#### `aws_cloudtrail_resource_inventory`

List the resources of one kind, grouped by state, so the answer is the distribution rather than every resource. Reach for it when the question is how much of the estate is in a bad state rather than which one is.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from aws_cloudtrail
- **Parallel safe:** yes
- **Requires:** aws_cloudtrail

**Use when:**

- an alert naming a service whose current state is unknown
- establishing whether a failure is one resource or a whole class of them

**Not for:**

- why a resource changed, which the change history answers
- application-level errors, which a control plane never sees

#### `aws_ec2_recent_changes`

Return the control-plane changes in a window, newest first and capped. Most incidents follow a change, and this is the capability that turns 'it started at 14:05' into a specific thing somebody did.

- **Side effect:** `read` — reads only
- **Evidence:** change from aws_ec2
- **Parallel safe:** yes
- **Requires:** aws_ec2

**Use when:**

- an incident whose start time is known and whose cause is not
- checking whether anything was changed shortly before the symptom

**Not for:**

- how much of the estate is affected, which the inventory answers
- a symptom with no change window, where the history is noise

#### `aws_ec2_resource_inventory`

List the resources of one kind, grouped by state, so the answer is the distribution rather than every resource. Reach for it when the question is how much of the estate is in a bad state rather than which one is.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from aws_ec2
- **Parallel safe:** yes
- **Requires:** aws_ec2

**Use when:**

- an alert naming a service whose current state is unknown
- establishing whether a failure is one resource or a whole class of them

**Not for:**

- why a resource changed, which the change history answers
- application-level errors, which a control plane never sees

#### `aws_ecs_recent_changes`

Return the control-plane changes in a window, newest first and capped. Most incidents follow a change, and this is the capability that turns 'it started at 14:05' into a specific thing somebody did.

- **Side effect:** `read` — reads only
- **Evidence:** change from aws_ecs
- **Parallel safe:** yes
- **Requires:** aws_ecs

**Use when:**

- an incident whose start time is known and whose cause is not
- checking whether anything was changed shortly before the symptom

**Not for:**

- how much of the estate is affected, which the inventory answers
- a symptom with no change window, where the history is noise

#### `aws_ecs_resource_inventory`

List the resources of one kind, grouped by state, so the answer is the distribution rather than every resource. Reach for it when the question is how much of the estate is in a bad state rather than which one is.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from aws_ecs
- **Parallel safe:** yes
- **Requires:** aws_ecs

**Use when:**

- an alert naming a service whose current state is unknown
- establishing whether a failure is one resource or a whole class of them

**Not for:**

- why a resource changed, which the change history answers
- application-level errors, which a control plane never sees

#### `aws_eks_recent_changes`

Return the control-plane changes in a window, newest first and capped. Most incidents follow a change, and this is the capability that turns 'it started at 14:05' into a specific thing somebody did.

- **Side effect:** `read` — reads only
- **Evidence:** change from aws_eks
- **Parallel safe:** yes
- **Requires:** aws_eks

**Use when:**

- an incident whose start time is known and whose cause is not
- checking whether anything was changed shortly before the symptom

**Not for:**

- how much of the estate is affected, which the inventory answers
- a symptom with no change window, where the history is noise

#### `aws_eks_resource_inventory`

List the resources of one kind, grouped by state, so the answer is the distribution rather than every resource. Reach for it when the question is how much of the estate is in a bad state rather than which one is.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from aws_eks
- **Parallel safe:** yes
- **Requires:** aws_eks

**Use when:**

- an alert naming a service whose current state is unknown
- establishing whether a failure is one resource or a whole class of them

**Not for:**

- why a resource changed, which the change history answers
- application-level errors, which a control plane never sees

#### `aws_elb_recent_changes`

Return the control-plane changes in a window, newest first and capped. Most incidents follow a change, and this is the capability that turns 'it started at 14:05' into a specific thing somebody did.

- **Side effect:** `read` — reads only
- **Evidence:** change from aws_elb
- **Parallel safe:** yes
- **Requires:** aws_elb

**Use when:**

- an incident whose start time is known and whose cause is not
- checking whether anything was changed shortly before the symptom

**Not for:**

- how much of the estate is affected, which the inventory answers
- a symptom with no change window, where the history is noise

#### `aws_elb_resource_inventory`

List the resources of one kind, grouped by state, so the answer is the distribution rather than every resource. Reach for it when the question is how much of the estate is in a bad state rather than which one is.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from aws_elb
- **Parallel safe:** yes
- **Requires:** aws_elb

**Use when:**

- an alert naming a service whose current state is unknown
- establishing whether a failure is one resource or a whole class of them

**Not for:**

- why a resource changed, which the change history answers
- application-level errors, which a control plane never sees

#### `aws_lambda_recent_changes`

Return the control-plane changes in a window, newest first and capped. Most incidents follow a change, and this is the capability that turns 'it started at 14:05' into a specific thing somebody did.

- **Side effect:** `read` — reads only
- **Evidence:** change from aws_lambda
- **Parallel safe:** yes
- **Requires:** aws_lambda

**Use when:**

- an incident whose start time is known and whose cause is not
- checking whether anything was changed shortly before the symptom

**Not for:**

- how much of the estate is affected, which the inventory answers
- a symptom with no change window, where the history is noise

#### `aws_lambda_resource_inventory`

List the resources of one kind, grouped by state, so the answer is the distribution rather than every resource. Reach for it when the question is how much of the estate is in a bad state rather than which one is.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from aws_lambda
- **Parallel safe:** yes
- **Requires:** aws_lambda

**Use when:**

- an alert naming a service whose current state is unknown
- establishing whether a failure is one resource or a whole class of them

**Not for:**

- why a resource changed, which the change history answers
- application-level errors, which a control plane never sees

#### `aws_rds_recent_changes`

Return the control-plane changes in a window, newest first and capped. Most incidents follow a change, and this is the capability that turns 'it started at 14:05' into a specific thing somebody did.

- **Side effect:** `read` — reads only
- **Evidence:** change from aws_rds
- **Parallel safe:** yes
- **Requires:** aws_rds

**Use when:**

- an incident whose start time is known and whose cause is not
- checking whether anything was changed shortly before the symptom

**Not for:**

- how much of the estate is affected, which the inventory answers
- a symptom with no change window, where the history is noise

#### `aws_rds_resource_inventory`

List the resources of one kind, grouped by state, so the answer is the distribution rather than every resource. Reach for it when the question is how much of the estate is in a bad state rather than which one is.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from aws_rds
- **Parallel safe:** yes
- **Requires:** aws_rds

**Use when:**

- an alert naming a service whose current state is unknown
- establishing whether a failure is one resource or a whole class of them

**Not for:**

- why a resource changed, which the change history answers
- application-level errors, which a control plane never sees

#### `aws_s3_recent_changes`

Return the control-plane changes in a window, newest first and capped. Most incidents follow a change, and this is the capability that turns 'it started at 14:05' into a specific thing somebody did.

- **Side effect:** `read` — reads only
- **Evidence:** change from aws_s3
- **Parallel safe:** yes
- **Requires:** aws_s3

**Use when:**

- an incident whose start time is known and whose cause is not
- checking whether anything was changed shortly before the symptom

**Not for:**

- how much of the estate is affected, which the inventory answers
- a symptom with no change window, where the history is noise

#### `aws_s3_resource_inventory`

List the resources of one kind, grouped by state, so the answer is the distribution rather than every resource. Reach for it when the question is how much of the estate is in a bad state rather than which one is.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from aws_s3
- **Parallel safe:** yes
- **Requires:** aws_s3

**Use when:**

- an alert naming a service whose current state is unknown
- establishing whether a failure is one resource or a whole class of them

**Not for:**

- why a resource changed, which the change history answers
- application-level errors, which a control plane never sees

#### `azure_recent_changes`

Return the control-plane changes in a window, newest first and capped. Most incidents follow a change, and this is the capability that turns 'it started at 14:05' into a specific thing somebody did.

- **Side effect:** `read` — reads only
- **Evidence:** change from azure
- **Parallel safe:** yes
- **Requires:** azure

**Use when:**

- an incident whose start time is known and whose cause is not
- checking whether anything was changed shortly before the symptom

**Not for:**

- how much of the estate is affected, which the inventory answers
- a symptom with no change window, where the history is noise

#### `azure_resource_inventory`

List the resources of one kind, grouped by state, so the answer is the distribution rather than every resource. Reach for it when the question is how much of the estate is in a bad state rather than which one is.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from azure
- **Parallel safe:** yes
- **Requires:** azure

**Use when:**

- an alert naming a service whose current state is unknown
- establishing whether a failure is one resource or a whole class of them

**Not for:**

- why a resource changed, which the change history answers
- application-level errors, which a control plane never sees

#### `docker_recent_changes`

Return the control-plane changes in a window, newest first and capped. Most incidents follow a change, and this is the capability that turns 'it started at 14:05' into a specific thing somebody did.

- **Side effect:** `read` — reads only
- **Evidence:** change from docker
- **Parallel safe:** yes
- **Requires:** docker

**Use when:**

- an incident whose start time is known and whose cause is not
- checking whether anything was changed shortly before the symptom

**Not for:**

- how much of the estate is affected, which the inventory answers
- a symptom with no change window, where the history is noise

#### `docker_resource_inventory`

List the resources of one kind, grouped by state, so the answer is the distribution rather than every resource. Reach for it when the question is how much of the estate is in a bad state rather than which one is.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from docker
- **Parallel safe:** yes
- **Requires:** docker

**Use when:**

- an alert naming a service whose current state is unknown
- establishing whether a failure is one resource or a whole class of them

**Not for:**

- why a resource changed, which the change history answers
- application-level errors, which a control plane never sees

#### `flagd_recent_changes`

Return the control-plane changes in a window, newest first and capped. Most incidents follow a change, and this is the capability that turns 'it started at 14:05' into a specific thing somebody did.

- **Side effect:** `read` — reads only
- **Evidence:** change from flagd
- **Parallel safe:** yes
- **Requires:** flagd

**Use when:**

- an incident whose start time is known and whose cause is not
- checking whether anything was changed shortly before the symptom

**Not for:**

- how much of the estate is affected, which the inventory answers
- a symptom with no change window, where the history is noise

#### `flagd_resource_inventory`

List the resources of one kind, grouped by state, so the answer is the distribution rather than every resource. Reach for it when the question is how much of the estate is in a bad state rather than which one is.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from flagd
- **Parallel safe:** yes
- **Requires:** flagd

**Use when:**

- an alert naming a service whose current state is unknown
- establishing whether a failure is one resource or a whole class of them

**Not for:**

- why a resource changed, which the change history answers
- application-level errors, which a control plane never sees

#### `gcp_recent_changes`

Return the control-plane changes in a window, newest first and capped. Most incidents follow a change, and this is the capability that turns 'it started at 14:05' into a specific thing somebody did.

- **Side effect:** `read` — reads only
- **Evidence:** change from gcp
- **Parallel safe:** yes
- **Requires:** gcp

**Use when:**

- an incident whose start time is known and whose cause is not
- checking whether anything was changed shortly before the symptom

**Not for:**

- how much of the estate is affected, which the inventory answers
- a symptom with no change window, where the history is noise

#### `gcp_resource_inventory`

List the resources of one kind, grouped by state, so the answer is the distribution rather than every resource. Reach for it when the question is how much of the estate is in a bad state rather than which one is.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from gcp
- **Parallel safe:** yes
- **Requires:** gcp

**Use when:**

- an alert naming a service whose current state is unknown
- establishing whether a failure is one resource or a whole class of them

**Not for:**

- why a resource changed, which the change history answers
- application-level errors, which a control plane never sees

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

#### `proxmox_backup_server_datastore_health`

Return whether a Proxmox Backup Server datastore holds something that would restore: its usage, its snapshots, whether those snapshots have been verified, and when garbage collection last ran. An unverified snapshot is a file rather than a restore, and a store that has never verified looks identical to one that passes.

- **Side effect:** `read` — reads only
- **Evidence:** configuration from proxmox_backup_server
- **Parallel safe:** yes
- **Requires:** proxmox_backup_server

**Use when:**

- checking whether a guest's most recent snapshot has actually been verified
- finding out whether a datastore's usage figure reflects a garbage collection that ran
- establishing that a backup exists and is recent before planning a restore

**Not for:**

- restoring, pruning or collecting garbage — nothing here writes
- whether the hypervisor's backup job ran, which proxmox_protection_gaps answers
- what is inside a snapshot, which is a restore rather than a read

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

### communication

#### `discord_post_message`

Post a message to a channel. Used to deliver a finding where the incident is already being discussed, rather than in a place somebody has to go and look.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** document from discord
- **Parallel safe:** no
- **Risk class:** `moderate` — Undone only by a further action, or reaching several resources at once.
- **Requires:** discord
- **Approval:** required — A message to a channel is visible to everyone in it and cannot be unsaid, only followed by a correction. A human decides whether a finding is ready to be read by the people responding.

**Use when:**

- delivering a finding into the channel an incident is being run from
- telling responders that an automated investigation has concluded

**Not for:**

- paging somebody, which is an escalation rather than a message
- anything an investigation has not finished establishing

#### `discord_recent_messages`

Return the recent messages in a channel, newest first and capped. What people have already said about an incident is evidence, and reading it is what stops an investigation repeating work that is already done.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** document from discord
- **Parallel safe:** yes
- **Requires:** discord

**Use when:**

- joining an incident channel where responders have already been talking
- finding what was tried before an automated investigation started

**Not for:**

- system state, which chat reports secondhand and often wrongly
- a channel with no relation to the incident, where the messages are noise

#### `microsoft_teams_post_message`

Post a message to a channel. Used to deliver a finding where the incident is already being discussed, rather than in a place somebody has to go and look.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** document from microsoft_teams
- **Parallel safe:** no
- **Risk class:** `moderate` — Undone only by a further action, or reaching several resources at once.
- **Requires:** microsoft_teams
- **Approval:** required — A message to a channel is visible to everyone in it and cannot be unsaid, only followed by a correction. A human decides whether a finding is ready to be read by the people responding.

**Use when:**

- delivering a finding into the channel an incident is being run from
- telling responders that an automated investigation has concluded

**Not for:**

- paging somebody, which is an escalation rather than a message
- anything an investigation has not finished establishing

#### `microsoft_teams_recent_messages`

Return the recent messages in a channel, newest first and capped. What people have already said about an incident is evidence, and reading it is what stops an investigation repeating work that is already done.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** document from microsoft_teams
- **Parallel safe:** yes
- **Requires:** microsoft_teams

**Use when:**

- joining an incident channel where responders have already been talking
- finding what was tried before an automated investigation started

**Not for:**

- system state, which chat reports secondhand and often wrongly
- a channel with no relation to the incident, where the messages are noise

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

#### `rocket_chat_post_message`

Post a message to a channel. Used to deliver a finding where the incident is already being discussed, rather than in a place somebody has to go and look.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** document from rocket_chat
- **Parallel safe:** no
- **Risk class:** `moderate` — Undone only by a further action, or reaching several resources at once.
- **Requires:** rocket_chat
- **Approval:** required — A message to a channel is visible to everyone in it and cannot be unsaid, only followed by a correction. A human decides whether a finding is ready to be read by the people responding.

**Use when:**

- delivering a finding into the channel an incident is being run from
- telling responders that an automated investigation has concluded

**Not for:**

- paging somebody, which is an escalation rather than a message
- anything an investigation has not finished establishing

#### `rocket_chat_recent_messages`

Return the recent messages in a channel, newest first and capped. What people have already said about an incident is evidence, and reading it is what stops an investigation repeating work that is already done.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** document from rocket_chat
- **Parallel safe:** yes
- **Requires:** rocket_chat

**Use when:**

- joining an incident channel where responders have already been talking
- finding what was tried before an automated investigation started

**Not for:**

- system state, which chat reports secondhand and often wrongly
- a channel with no relation to the incident, where the messages are noise

#### `slack_post_message`

Post a message to a channel. Used to deliver a finding where the incident is already being discussed, rather than in a place somebody has to go and look.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** document from slack
- **Parallel safe:** no
- **Risk class:** `moderate` — Undone only by a further action, or reaching several resources at once.
- **Requires:** slack
- **Approval:** required — A message to a channel is visible to everyone in it and cannot be unsaid, only followed by a correction. A human decides whether a finding is ready to be read by the people responding.

**Use when:**

- delivering a finding into the channel an incident is being run from
- telling responders that an automated investigation has concluded

**Not for:**

- paging somebody, which is an escalation rather than a message
- anything an investigation has not finished establishing

#### `slack_recent_messages`

Return the recent messages in a channel, newest first and capped. What people have already said about an incident is evidence, and reading it is what stops an investigation repeating work that is already done.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** document from slack
- **Parallel safe:** yes
- **Requires:** slack

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

#### `twilio_post_message`

Post a message to a channel. Used to deliver a finding where the incident is already being discussed, rather than in a place somebody has to go and look.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** document from twilio
- **Parallel safe:** no
- **Risk class:** `moderate` — Undone only by a further action, or reaching several resources at once.
- **Requires:** twilio
- **Approval:** required — A message to a channel is visible to everyone in it and cannot be unsaid, only followed by a correction. A human decides whether a finding is ready to be read by the people responding.

**Use when:**

- delivering a finding into the channel an incident is being run from
- telling responders that an automated investigation has concluded

**Not for:**

- paging somebody, which is an escalation rather than a message
- anything an investigation has not finished establishing

#### `twilio_recent_messages`

Return the recent messages in a channel, newest first and capped. What people have already said about an incident is evidence, and reading it is what stops an investigation repeating work that is already done.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** document from twilio
- **Parallel safe:** yes
- **Requires:** twilio

**Use when:**

- joining an incident channel where responders have already been talking
- finding what was tried before an automated investigation started

**Not for:**

- system state, which chat reports secondhand and often wrongly
- a channel with no relation to the incident, where the messages are noise

#### `whatsapp_post_message`

Post a message to a channel. Used to deliver a finding where the incident is already being discussed, rather than in a place somebody has to go and look.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** document from whatsapp
- **Parallel safe:** no
- **Risk class:** `moderate` — Undone only by a further action, or reaching several resources at once.
- **Requires:** whatsapp
- **Approval:** required — A message to a channel is visible to everyone in it and cannot be unsaid, only followed by a correction. A human decides whether a finding is ready to be read by the people responding.

**Use when:**

- delivering a finding into the channel an incident is being run from
- telling responders that an automated investigation has concluded

**Not for:**

- paging somebody, which is an escalation rather than a message
- anything an investigation has not finished establishing

#### `whatsapp_recent_messages`

Return the recent messages in a channel, newest first and capped. What people have already said about an incident is evidence, and reading it is what stops an investigation repeating work that is already done.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** document from whatsapp
- **Parallel safe:** yes
- **Requires:** whatsapp

**Use when:**

- joining an incident channel where responders have already been talking
- finding what was tried before an automated investigation started

**Not for:**

- system state, which chat reports secondhand and often wrongly
- a channel with no relation to the incident, where the messages are noise

### data_platform

#### `airflow_pipeline_health`

Group the current tasks or partitions by state, so the answer is whether the platform is behind, failing, or idle. Lag and backlog before internals: a pipeline that is merely behind needs a different investigation.

- **Side effect:** `read` — reads only
- **Evidence:** event from airflow
- **Parallel safe:** yes
- **Requires:** airflow

**Use when:**

- a data-freshness alert where the cause is not yet known
- deciding whether a backlog is growing or draining

**Not for:**

- one task's error text, which the failure list returns
- the downstream service's own errors, which this never sees

#### `airflow_recent_failures`

Return the recently failed tasks or jobs, newest first and capped, with the reason each gave. Call it after the health summary, so the ones read are from whichever stage the backlog pointed at.

- **Side effect:** `read` — reads only
- **Evidence:** event from airflow
- **Parallel safe:** yes
- **Requires:** airflow

**Use when:**

- finding the first failure in a chain of downstream ones
- checking whether a retry succeeded before treating a failure as current

**Not for:**

- how far behind the platform is, which the health summary answers
- a slow but succeeding pipeline, where nothing has failed to list

#### `dagster_pipeline_health`

Group the current tasks or partitions by state, so the answer is whether the platform is behind, failing, or idle. Lag and backlog before internals: a pipeline that is merely behind needs a different investigation.

- **Side effect:** `read` — reads only
- **Evidence:** event from dagster
- **Parallel safe:** yes
- **Requires:** dagster

**Use when:**

- a data-freshness alert where the cause is not yet known
- deciding whether a backlog is growing or draining

**Not for:**

- one task's error text, which the failure list returns
- the downstream service's own errors, which this never sees

#### `dagster_recent_failures`

Return the recently failed tasks or jobs, newest first and capped, with the reason each gave. Call it after the health summary, so the ones read are from whichever stage the backlog pointed at.

- **Side effect:** `read` — reads only
- **Evidence:** event from dagster
- **Parallel safe:** yes
- **Requires:** dagster

**Use when:**

- finding the first failure in a chain of downstream ones
- checking whether a retry succeeded before treating a failure as current

**Not for:**

- how far behind the platform is, which the health summary answers
- a slow but succeeding pipeline, where nothing has failed to list

#### `flink_pipeline_health`

Group the current tasks or partitions by state, so the answer is whether the platform is behind, failing, or idle. Lag and backlog before internals: a pipeline that is merely behind needs a different investigation.

- **Side effect:** `read` — reads only
- **Evidence:** event from flink
- **Parallel safe:** yes
- **Requires:** flink

**Use when:**

- a data-freshness alert where the cause is not yet known
- deciding whether a backlog is growing or draining

**Not for:**

- one task's error text, which the failure list returns
- the downstream service's own errors, which this never sees

#### `flink_recent_failures`

Return the recently failed tasks or jobs, newest first and capped, with the reason each gave. Call it after the health summary, so the ones read are from whichever stage the backlog pointed at.

- **Side effect:** `read` — reads only
- **Evidence:** event from flink
- **Parallel safe:** yes
- **Requires:** flink

**Use when:**

- finding the first failure in a chain of downstream ones
- checking whether a retry succeeded before treating a failure as current

**Not for:**

- how far behind the platform is, which the health summary answers
- a slow but succeeding pipeline, where nothing has failed to list

#### `kafka_pipeline_health`

Group the current tasks or partitions by state, so the answer is whether the platform is behind, failing, or idle. Lag and backlog before internals: a pipeline that is merely behind needs a different investigation.

- **Side effect:** `read` — reads only
- **Evidence:** event from kafka
- **Parallel safe:** yes
- **Requires:** kafka

**Use when:**

- a data-freshness alert where the cause is not yet known
- deciding whether a backlog is growing or draining

**Not for:**

- one task's error text, which the failure list returns
- the downstream service's own errors, which this never sees

#### `kafka_recent_failures`

Return the recently failed tasks or jobs, newest first and capped, with the reason each gave. Call it after the health summary, so the ones read are from whichever stage the backlog pointed at.

- **Side effect:** `read` — reads only
- **Evidence:** event from kafka
- **Parallel safe:** yes
- **Requires:** kafka

**Use when:**

- finding the first failure in a chain of downstream ones
- checking whether a retry succeeded before treating a failure as current

**Not for:**

- how far behind the platform is, which the health summary answers
- a slow but succeeding pipeline, where nothing has failed to list

#### `prefect_pipeline_health`

Group the current tasks or partitions by state, so the answer is whether the platform is behind, failing, or idle. Lag and backlog before internals: a pipeline that is merely behind needs a different investigation.

- **Side effect:** `read` — reads only
- **Evidence:** event from prefect
- **Parallel safe:** yes
- **Requires:** prefect

**Use when:**

- a data-freshness alert where the cause is not yet known
- deciding whether a backlog is growing or draining

**Not for:**

- one task's error text, which the failure list returns
- the downstream service's own errors, which this never sees

#### `prefect_recent_failures`

Return the recently failed tasks or jobs, newest first and capped, with the reason each gave. Call it after the health summary, so the ones read are from whichever stage the backlog pointed at.

- **Side effect:** `read` — reads only
- **Evidence:** event from prefect
- **Parallel safe:** yes
- **Requires:** prefect

**Use when:**

- finding the first failure in a chain of downstream ones
- checking whether a retry succeeded before treating a failure as current

**Not for:**

- how far behind the platform is, which the health summary answers
- a slow but succeeding pipeline, where nothing has failed to list

#### `rabbitmq_pipeline_health`

Group the current tasks or partitions by state, so the answer is whether the platform is behind, failing, or idle. Lag and backlog before internals: a pipeline that is merely behind needs a different investigation.

- **Side effect:** `read` — reads only
- **Evidence:** event from rabbitmq
- **Parallel safe:** yes
- **Requires:** rabbitmq

**Use when:**

- a data-freshness alert where the cause is not yet known
- deciding whether a backlog is growing or draining

**Not for:**

- one task's error text, which the failure list returns
- the downstream service's own errors, which this never sees

#### `rabbitmq_recent_failures`

Return the recently failed tasks or jobs, newest first and capped, with the reason each gave. Call it after the health summary, so the ones read are from whichever stage the backlog pointed at.

- **Side effect:** `read` — reads only
- **Evidence:** event from rabbitmq
- **Parallel safe:** yes
- **Requires:** rabbitmq

**Use when:**

- finding the first failure in a chain of downstream ones
- checking whether a retry succeeded before treating a failure as current

**Not for:**

- how far behind the platform is, which the health summary answers
- a slow but succeeding pipeline, where nothing has failed to list

#### `spark_pipeline_health`

Group the current tasks or partitions by state, so the answer is whether the platform is behind, failing, or idle. Lag and backlog before internals: a pipeline that is merely behind needs a different investigation.

- **Side effect:** `read` — reads only
- **Evidence:** event from spark
- **Parallel safe:** yes
- **Requires:** spark

**Use when:**

- a data-freshness alert where the cause is not yet known
- deciding whether a backlog is growing or draining

**Not for:**

- one task's error text, which the failure list returns
- the downstream service's own errors, which this never sees

#### `spark_recent_failures`

Return the recently failed tasks or jobs, newest first and capped, with the reason each gave. Call it after the health summary, so the ones read are from whichever stage the backlog pointed at.

- **Side effect:** `read` — reads only
- **Evidence:** event from spark
- **Parallel safe:** yes
- **Requires:** spark

**Use when:**

- finding the first failure in a chain of downstream ones
- checking whether a retry succeeded before treating a failure as current

**Not for:**

- how far behind the platform is, which the health summary answers
- a slow but succeeding pipeline, where nothing has failed to list

#### `temporal_pipeline_health`

Group the current tasks or partitions by state, so the answer is whether the platform is behind, failing, or idle. Lag and backlog before internals: a pipeline that is merely behind needs a different investigation.

- **Side effect:** `read` — reads only
- **Evidence:** event from temporal
- **Parallel safe:** yes
- **Requires:** temporal

**Use when:**

- a data-freshness alert where the cause is not yet known
- deciding whether a backlog is growing or draining

**Not for:**

- one task's error text, which the failure list returns
- the downstream service's own errors, which this never sees

#### `temporal_recent_failures`

Return the recently failed tasks or jobs, newest first and capped, with the reason each gave. Call it after the health summary, so the ones read are from whichever stage the backlog pointed at.

- **Side effect:** `read` — reads only
- **Evidence:** event from temporal
- **Parallel safe:** yes
- **Requires:** temporal

**Use when:**

- finding the first failure in a chain of downstream ones
- checking whether a retry succeeded before treating a failure as current

**Not for:**

- how far behind the platform is, which the health summary answers
- a slow but succeeding pipeline, where nothing has failed to list

### database

#### `azure_sql_session_statistics`

Group the current sessions by state or wait, so the answer says whether the database is blocked, saturated, or idle. This is the first database call in an investigation, before anything is asked about a query plan.

- **Side effect:** `read` — reads only
- **Evidence:** metric from azure_sql
- **Parallel safe:** yes
- **Requires:** azure_sql

**Use when:**

- a latency alert on a service whose database may be the constraint
- deciding whether connections are exhausted or queries are simply slow

**Not for:**

- the text of a specific slow query, which the query capability returns
- application errors that never reached the database

#### `azure_sql_slow_queries`

Return the slowest statements recorded, capped, with their timing. Call it after the session statistics: a slow query on an unblocked database is a different problem from the same query behind a lock queue.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** analysis from azure_sql
- **Parallel safe:** yes
- **Requires:** azure_sql

**Use when:**

- a database whose sessions are dominated by one kind of work
- finding the statement behind a latency change with a known start

**Not for:**

- whether the database is the problem at all, which sessions answer first
- a connectivity failure, where no statement ever ran

#### `bigquery_session_statistics`

Group the current sessions by state or wait, so the answer says whether the database is blocked, saturated, or idle. This is the first database call in an investigation, before anything is asked about a query plan.

- **Side effect:** `read` — reads only
- **Evidence:** metric from bigquery
- **Parallel safe:** yes
- **Requires:** bigquery

**Use when:**

- a latency alert on a service whose database may be the constraint
- deciding whether connections are exhausted or queries are simply slow

**Not for:**

- the text of a specific slow query, which the query capability returns
- application errors that never reached the database

#### `bigquery_slow_queries`

Return the slowest statements recorded, capped, with their timing. Call it after the session statistics: a slow query on an unblocked database is a different problem from the same query behind a lock queue.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** analysis from bigquery
- **Parallel safe:** yes
- **Requires:** bigquery

**Use when:**

- a database whose sessions are dominated by one kind of work
- finding the statement behind a latency change with a known start

**Not for:**

- whether the database is the problem at all, which sessions answer first
- a connectivity failure, where no statement ever ran

#### `clickhouse_session_statistics`

Group the current sessions by state or wait, so the answer says whether the database is blocked, saturated, or idle. This is the first database call in an investigation, before anything is asked about a query plan.

- **Side effect:** `read` — reads only
- **Evidence:** metric from clickhouse
- **Parallel safe:** yes
- **Requires:** clickhouse

**Use when:**

- a latency alert on a service whose database may be the constraint
- deciding whether connections are exhausted or queries are simply slow

**Not for:**

- the text of a specific slow query, which the query capability returns
- application errors that never reached the database

#### `clickhouse_slow_queries`

Return the slowest statements recorded, capped, with their timing. Call it after the session statistics: a slow query on an unblocked database is a different problem from the same query behind a lock queue.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** analysis from clickhouse
- **Parallel safe:** yes
- **Requires:** clickhouse

**Use when:**

- a database whose sessions are dominated by one kind of work
- finding the statement behind a latency change with a known start

**Not for:**

- whether the database is the problem at all, which sessions answer first
- a connectivity failure, where no statement ever ran

#### `mongodb_atlas_session_statistics`

Group the current sessions by state or wait, so the answer says whether the database is blocked, saturated, or idle. This is the first database call in an investigation, before anything is asked about a query plan.

- **Side effect:** `read` — reads only
- **Evidence:** metric from mongodb_atlas
- **Parallel safe:** yes
- **Requires:** mongodb_atlas

**Use when:**

- a latency alert on a service whose database may be the constraint
- deciding whether connections are exhausted or queries are simply slow

**Not for:**

- the text of a specific slow query, which the query capability returns
- application errors that never reached the database

#### `mongodb_atlas_slow_queries`

Return the slowest statements recorded, capped, with their timing. Call it after the session statistics: a slow query on an unblocked database is a different problem from the same query behind a lock queue.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** analysis from mongodb_atlas
- **Parallel safe:** yes
- **Requires:** mongodb_atlas

**Use when:**

- a database whose sessions are dominated by one kind of work
- finding the statement behind a latency change with a known start

**Not for:**

- whether the database is the problem at all, which sessions answer first
- a connectivity failure, where no statement ever ran

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

#### `snowflake_session_statistics`

Group the current sessions by state or wait, so the answer says whether the database is blocked, saturated, or idle. This is the first database call in an investigation, before anything is asked about a query plan.

- **Side effect:** `read` — reads only
- **Evidence:** metric from snowflake
- **Parallel safe:** yes
- **Requires:** snowflake

**Use when:**

- a latency alert on a service whose database may be the constraint
- deciding whether connections are exhausted or queries are simply slow

**Not for:**

- the text of a specific slow query, which the query capability returns
- application errors that never reached the database

#### `snowflake_slow_queries`

Return the slowest statements recorded, capped, with their timing. Call it after the session statistics: a slow query on an unblocked database is a different problem from the same query behind a lock queue.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** analysis from snowflake
- **Parallel safe:** yes
- **Requires:** snowflake

**Use when:**

- a database whose sessions are dominated by one kind of work
- finding the statement behind a latency change with a known start

**Not for:**

- whether the database is the problem at all, which sessions answer first
- a connectivity failure, where no statement ever ran

#### `supabase_session_statistics`

Group the current sessions by state or wait, so the answer says whether the database is blocked, saturated, or idle. This is the first database call in an investigation, before anything is asked about a query plan.

- **Side effect:** `read` — reads only
- **Evidence:** metric from supabase
- **Parallel safe:** yes
- **Requires:** supabase

**Use when:**

- a latency alert on a service whose database may be the constraint
- deciding whether connections are exhausted or queries are simply slow

**Not for:**

- the text of a specific slow query, which the query capability returns
- application errors that never reached the database

#### `supabase_slow_queries`

Return the slowest statements recorded, capped, with their timing. Call it after the session statistics: a slow query on an unblocked database is a different problem from the same query behind a lock queue.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** analysis from supabase
- **Parallel safe:** yes
- **Requires:** supabase

**Use when:**

- a database whose sessions are dominated by one kind of work
- finding the statement behind a latency change with a known start

**Not for:**

- whether the database is the problem at all, which sessions answer first
- a connectivity failure, where no statement ever ran

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

#### `blameless_acknowledge_incident`

Acknowledge an incident and attach a note saying an automated investigation is under way. It stops the escalation clock, which is a change to who gets woken and therefore needs a human to agree to it.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** incident from blameless
- **Parallel safe:** no
- **Risk class:** `low` — Reversible, reaches one resource, and costs a brief loss of availability at most.
- **Requires:** blameless
- **Approval:** required — Acknowledging stops the escalation clock, so the next person in the rotation is not paged. That is a decision about who is woken up, and it belongs to a human even though it is reversible.

**Use when:**

- an investigation that has started and will report shortly
- stopping a second escalation while a first responder is already engaged

**Not for:**

- an incident nobody is actually working, where the clock should run
- closing an incident, which acknowledging deliberately does not do

#### `blameless_incident_statistics`

Count the incidents in a window, grouped by status, service, or urgency. It answers 'is this one thing or many' in a single call, which is the question that decides whether an investigation is scoped correctly.

- **Side effect:** `read` — reads only
- **Evidence:** incident from blameless
- **Parallel safe:** yes
- **Requires:** blameless

**Use when:**

- a page arriving while other services may already be alerting
- establishing whether a recurrence is the same incident returning

**Not for:**

- the timeline of one incident, which the timeline capability returns
- the underlying telemetry, which an incident record never carries

#### `blameless_incident_timeline`

Return one incident's timeline — the notes, escalations, and status changes, oldest first and capped. It is what tells an investigation what humans already tried, so it does not repeat them.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** incident from blameless
- **Parallel safe:** yes
- **Requires:** blameless

**Use when:**

- picking up an incident somebody else has already been working
- recovering what was tried before the current responder arrived

**Not for:**

- how many incidents there are, which the statistics answer
- system state, which the timeline only reports secondhand

#### `firehydrant_acknowledge_incident`

Acknowledge an incident and attach a note saying an automated investigation is under way. It stops the escalation clock, which is a change to who gets woken and therefore needs a human to agree to it.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** incident from firehydrant
- **Parallel safe:** no
- **Risk class:** `low` — Reversible, reaches one resource, and costs a brief loss of availability at most.
- **Requires:** firehydrant
- **Approval:** required — Acknowledging stops the escalation clock, so the next person in the rotation is not paged. That is a decision about who is woken up, and it belongs to a human even though it is reversible.

**Use when:**

- an investigation that has started and will report shortly
- stopping a second escalation while a first responder is already engaged

**Not for:**

- an incident nobody is actually working, where the clock should run
- closing an incident, which acknowledging deliberately does not do

#### `firehydrant_incident_statistics`

Count the incidents in a window, grouped by status, service, or urgency. It answers 'is this one thing or many' in a single call, which is the question that decides whether an investigation is scoped correctly.

- **Side effect:** `read` — reads only
- **Evidence:** incident from firehydrant
- **Parallel safe:** yes
- **Requires:** firehydrant

**Use when:**

- a page arriving while other services may already be alerting
- establishing whether a recurrence is the same incident returning

**Not for:**

- the timeline of one incident, which the timeline capability returns
- the underlying telemetry, which an incident record never carries

#### `firehydrant_incident_timeline`

Return one incident's timeline — the notes, escalations, and status changes, oldest first and capped. It is what tells an investigation what humans already tried, so it does not repeat them.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** incident from firehydrant
- **Parallel safe:** yes
- **Requires:** firehydrant

**Use when:**

- picking up an incident somebody else has already been working
- recovering what was tried before the current responder arrived

**Not for:**

- how many incidents there are, which the statistics answer
- system state, which the timeline only reports secondhand

#### `incident_io_acknowledge_incident`

Acknowledge an incident and attach a note saying an automated investigation is under way. It stops the escalation clock, which is a change to who gets woken and therefore needs a human to agree to it.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** incident from incident_io
- **Parallel safe:** no
- **Risk class:** `low` — Reversible, reaches one resource, and costs a brief loss of availability at most.
- **Requires:** incident_io
- **Approval:** required — Acknowledging stops the escalation clock, so the next person in the rotation is not paged. That is a decision about who is woken up, and it belongs to a human even though it is reversible.

**Use when:**

- an investigation that has started and will report shortly
- stopping a second escalation while a first responder is already engaged

**Not for:**

- an incident nobody is actually working, where the clock should run
- closing an incident, which acknowledging deliberately does not do

#### `incident_io_incident_statistics`

Count the incidents in a window, grouped by status, service, or urgency. It answers 'is this one thing or many' in a single call, which is the question that decides whether an investigation is scoped correctly.

- **Side effect:** `read` — reads only
- **Evidence:** incident from incident_io
- **Parallel safe:** yes
- **Requires:** incident_io

**Use when:**

- a page arriving while other services may already be alerting
- establishing whether a recurrence is the same incident returning

**Not for:**

- the timeline of one incident, which the timeline capability returns
- the underlying telemetry, which an incident record never carries

#### `incident_io_incident_timeline`

Return one incident's timeline — the notes, escalations, and status changes, oldest first and capped. It is what tells an investigation what humans already tried, so it does not repeat them.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** incident from incident_io
- **Parallel safe:** yes
- **Requires:** incident_io

**Use when:**

- picking up an incident somebody else has already been working
- recovering what was tried before the current responder arrived

**Not for:**

- how many incidents there are, which the statistics answer
- system state, which the timeline only reports secondhand

#### `opsgenie_acknowledge_incident`

Acknowledge an incident and attach a note saying an automated investigation is under way. It stops the escalation clock, which is a change to who gets woken and therefore needs a human to agree to it.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** incident from opsgenie
- **Parallel safe:** no
- **Risk class:** `low` — Reversible, reaches one resource, and costs a brief loss of availability at most.
- **Requires:** opsgenie
- **Approval:** required — Acknowledging stops the escalation clock, so the next person in the rotation is not paged. That is a decision about who is woken up, and it belongs to a human even though it is reversible.

**Use when:**

- an investigation that has started and will report shortly
- stopping a second escalation while a first responder is already engaged

**Not for:**

- an incident nobody is actually working, where the clock should run
- closing an incident, which acknowledging deliberately does not do

#### `opsgenie_incident_statistics`

Count the incidents in a window, grouped by status, service, or urgency. It answers 'is this one thing or many' in a single call, which is the question that decides whether an investigation is scoped correctly.

- **Side effect:** `read` — reads only
- **Evidence:** incident from opsgenie
- **Parallel safe:** yes
- **Requires:** opsgenie

**Use when:**

- a page arriving while other services may already be alerting
- establishing whether a recurrence is the same incident returning

**Not for:**

- the timeline of one incident, which the timeline capability returns
- the underlying telemetry, which an incident record never carries

#### `opsgenie_incident_timeline`

Return one incident's timeline — the notes, escalations, and status changes, oldest first and capped. It is what tells an investigation what humans already tried, so it does not repeat them.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** incident from opsgenie
- **Parallel safe:** yes
- **Requires:** opsgenie

**Use when:**

- picking up an incident somebody else has already been working
- recovering what was tried before the current responder arrived

**Not for:**

- how many incidents there are, which the statistics answer
- system state, which the timeline only reports secondhand

#### `pagerduty_acknowledge_incident`

Acknowledge an incident and attach a note saying an automated investigation is under way. It stops the escalation clock, which is a change to who gets woken and therefore needs a human to agree to it.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** incident from pagerduty
- **Parallel safe:** no
- **Risk class:** `low` — Reversible, reaches one resource, and costs a brief loss of availability at most.
- **Requires:** pagerduty
- **Approval:** required — Acknowledging stops the escalation clock, so the next person in the rotation is not paged. That is a decision about who is woken up, and it belongs to a human even though it is reversible.

**Use when:**

- an investigation that has started and will report shortly
- stopping a second escalation while a first responder is already engaged

**Not for:**

- an incident nobody is actually working, where the clock should run
- closing an incident, which acknowledging deliberately does not do

#### `pagerduty_incident_statistics`

Count the incidents in a window, grouped by status, service, or urgency. It answers 'is this one thing or many' in a single call, which is the question that decides whether an investigation is scoped correctly.

- **Side effect:** `read` — reads only
- **Evidence:** incident from pagerduty
- **Parallel safe:** yes
- **Requires:** pagerduty

**Use when:**

- a page arriving while other services may already be alerting
- establishing whether a recurrence is the same incident returning

**Not for:**

- the timeline of one incident, which the timeline capability returns
- the underlying telemetry, which an incident record never carries

#### `pagerduty_incident_timeline`

Return one incident's timeline — the notes, escalations, and status changes, oldest first and capped. It is what tells an investigation what humans already tried, so it does not repeat them.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** incident from pagerduty
- **Parallel safe:** yes
- **Requires:** pagerduty

**Use when:**

- picking up an incident somebody else has already been working
- recovering what was tried before the current responder arrived

**Not for:**

- how many incidents there are, which the statistics answer
- system state, which the timeline only reports secondhand

#### `servicenow_acknowledge_incident`

Acknowledge an incident and attach a note saying an automated investigation is under way. It stops the escalation clock, which is a change to who gets woken and therefore needs a human to agree to it.

- **Side effect:** `write_reversible` — changes something, undoable by plan
- **Evidence:** incident from servicenow
- **Parallel safe:** no
- **Risk class:** `low` — Reversible, reaches one resource, and costs a brief loss of availability at most.
- **Requires:** servicenow
- **Approval:** required — Acknowledging stops the escalation clock, so the next person in the rotation is not paged. That is a decision about who is woken up, and it belongs to a human even though it is reversible.

**Use when:**

- an investigation that has started and will report shortly
- stopping a second escalation while a first responder is already engaged

**Not for:**

- an incident nobody is actually working, where the clock should run
- closing an incident, which acknowledging deliberately does not do

#### `servicenow_incident_statistics`

Count the incidents in a window, grouped by status, service, or urgency. It answers 'is this one thing or many' in a single call, which is the question that decides whether an investigation is scoped correctly.

- **Side effect:** `read` — reads only
- **Evidence:** incident from servicenow
- **Parallel safe:** yes
- **Requires:** servicenow

**Use when:**

- a page arriving while other services may already be alerting
- establishing whether a recurrence is the same incident returning

**Not for:**

- the timeline of one incident, which the timeline capability returns
- the underlying telemetry, which an incident record never carries

#### `servicenow_incident_timeline`

Return one incident's timeline — the notes, escalations, and status changes, oldest first and capped. It is what tells an investigation what humans already tried, so it does not repeat them.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** incident from servicenow
- **Parallel safe:** yes
- **Requires:** servicenow

**Use when:**

- picking up an incident somebody else has already been working
- recovering what was tried before the current responder arrived

**Not for:**

- how many incidents there are, which the statistics answer
- system state, which the timeline only reports secondhand

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

#### `azure_monitor_log_statistics`

Count the log lines matching a query over a window and return the distribution across one field rather than the lines themselves. Call this first: the group it singles out is where the samples should come from.

- **Side effect:** `read` — reads only
- **Evidence:** log from azure_monitor
- **Parallel safe:** yes
- **Requires:** azure_monitor

**Use when:**

- an error-rate alert where the failing service or host is not yet known
- establishing whether one thing is failing loudly or everything is failing
- comparing a window's shape against the equivalent window before the symptom

**Not for:**

- reading a specific error message, which is what sampling is for
- latency across services, which a trace answers and a log count does not

#### `azure_monitor_sample_logs`

Return a small, capped sample of the log lines matching a query over a window, newest first. Narrow the query with the statistics capability before calling this: a sample from an unnarrowed query is arbitrary.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** log from azure_monitor
- **Parallel safe:** yes
- **Requires:** azure_monitor

**Use when:**

- reading the actual error text behind a spike the statistics located
- checking whether a stack trace matches one from a previous incident

**Not for:**

- establishing how much of something there is, which sampling cannot answer
- a query that has not been narrowed, where the sample is arbitrary

#### `better_stack_log_statistics`

Count the log lines matching a query over a window and return the distribution across one field rather than the lines themselves. Call this first: the group it singles out is where the samples should come from.

- **Side effect:** `read` — reads only
- **Evidence:** log from better_stack
- **Parallel safe:** yes
- **Requires:** better_stack

**Use when:**

- an error-rate alert where the failing service or host is not yet known
- establishing whether one thing is failing loudly or everything is failing
- comparing a window's shape against the equivalent window before the symptom

**Not for:**

- reading a specific error message, which is what sampling is for
- latency across services, which a trace answers and a log count does not

#### `better_stack_sample_logs`

Return a small, capped sample of the log lines matching a query over a window, newest first. Narrow the query with the statistics capability before calling this: a sample from an unnarrowed query is arbitrary.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** log from better_stack
- **Parallel safe:** yes
- **Requires:** better_stack

**Use when:**

- reading the actual error text behind a spike the statistics located
- checking whether a stack trace matches one from a previous incident

**Not for:**

- establishing how much of something there is, which sampling cannot answer
- a query that has not been narrowed, where the sample is arbitrary

#### `coralogix_log_statistics`

Count the log lines matching a query over a window and return the distribution across one field rather than the lines themselves. Call this first: the group it singles out is where the samples should come from.

- **Side effect:** `read` — reads only
- **Evidence:** log from coralogix
- **Parallel safe:** yes
- **Requires:** coralogix

**Use when:**

- an error-rate alert where the failing service or host is not yet known
- establishing whether one thing is failing loudly or everything is failing
- comparing a window's shape against the equivalent window before the symptom

**Not for:**

- reading a specific error message, which is what sampling is for
- latency across services, which a trace answers and a log count does not

#### `coralogix_sample_logs`

Return a small, capped sample of the log lines matching a query over a window, newest first. Narrow the query with the statistics capability before calling this: a sample from an unnarrowed query is arbitrary.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** log from coralogix
- **Parallel safe:** yes
- **Requires:** coralogix

**Use when:**

- reading the actual error text behind a spike the statistics located
- checking whether a stack trace matches one from a previous incident

**Not for:**

- establishing how much of something there is, which sampling cannot answer
- a query that has not been narrowed, where the sample is arbitrary

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

#### `elasticsearch_log_statistics`

Count the log lines matching a query over a window and return the distribution across one field rather than the lines themselves. Call this first: the group it singles out is where the samples should come from.

- **Side effect:** `read` — reads only
- **Evidence:** log from elasticsearch
- **Parallel safe:** yes
- **Requires:** elasticsearch

**Use when:**

- an error-rate alert where the failing service or host is not yet known
- establishing whether one thing is failing loudly or everything is failing
- comparing a window's shape against the equivalent window before the symptom

**Not for:**

- reading a specific error message, which is what sampling is for
- latency across services, which a trace answers and a log count does not

#### `elasticsearch_sample_logs`

Return a small, capped sample of the log lines matching a query over a window, newest first. Narrow the query with the statistics capability before calling this: a sample from an unnarrowed query is arbitrary.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** log from elasticsearch
- **Parallel safe:** yes
- **Requires:** elasticsearch

**Use when:**

- reading the actual error text behind a spike the statistics located
- checking whether a stack trace matches one from a previous incident

**Not for:**

- establishing how much of something there is, which sampling cannot answer
- a query that has not been narrowed, where the sample is arbitrary

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

#### `opensearch_log_statistics`

Count the log lines matching a query over a window and return the distribution across one field rather than the lines themselves. Call this first: the group it singles out is where the samples should come from.

- **Side effect:** `read` — reads only
- **Evidence:** log from opensearch
- **Parallel safe:** yes
- **Requires:** opensearch

**Use when:**

- an error-rate alert where the failing service or host is not yet known
- establishing whether one thing is failing loudly or everything is failing
- comparing a window's shape against the equivalent window before the symptom

**Not for:**

- reading a specific error message, which is what sampling is for
- latency across services, which a trace answers and a log count does not

#### `opensearch_sample_logs`

Return a small, capped sample of the log lines matching a query over a window, newest first. Narrow the query with the statistics capability before calling this: a sample from an unnarrowed query is arbitrary.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** log from opensearch
- **Parallel safe:** yes
- **Requires:** opensearch

**Use when:**

- reading the actual error text behind a spike the statistics located
- checking whether a stack trace matches one from a previous incident

**Not for:**

- establishing how much of something there is, which sampling cannot answer
- a query that has not been narrowed, where the sample is arbitrary

#### `sentry_log_statistics`

Count the log lines matching a query over a window and return the distribution across one field rather than the lines themselves. Call this first: the group it singles out is where the samples should come from.

- **Side effect:** `read` — reads only
- **Evidence:** log from sentry
- **Parallel safe:** yes
- **Requires:** sentry

**Use when:**

- an error-rate alert where the failing service or host is not yet known
- establishing whether one thing is failing loudly or everything is failing
- comparing a window's shape against the equivalent window before the symptom

**Not for:**

- reading a specific error message, which is what sampling is for
- latency across services, which a trace answers and a log count does not

#### `sentry_sample_logs`

Return a small, capped sample of the log lines matching a query over a window, newest first. Narrow the query with the statistics capability before calling this: a sample from an unnarrowed query is arbitrary.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** log from sentry
- **Parallel safe:** yes
- **Requires:** sentry

**Use when:**

- reading the actual error text behind a spike the statistics located
- checking whether a stack trace matches one from a previous incident

**Not for:**

- establishing how much of something there is, which sampling cannot answer
- a query that has not been narrowed, where the sample is arbitrary

#### `splunk_log_statistics`

Count the log lines matching a query over a window and return the distribution across one field rather than the lines themselves. Call this first: the group it singles out is where the samples should come from.

- **Side effect:** `read` — reads only
- **Evidence:** log from splunk
- **Parallel safe:** yes
- **Requires:** splunk

**Use when:**

- an error-rate alert where the failing service or host is not yet known
- establishing whether one thing is failing loudly or everything is failing
- comparing a window's shape against the equivalent window before the symptom

**Not for:**

- reading a specific error message, which is what sampling is for
- latency across services, which a trace answers and a log count does not

#### `splunk_sample_logs`

Return a small, capped sample of the log lines matching a query over a window, newest first. Narrow the query with the statistics capability before calling this: a sample from an unnarrowed query is arbitrary.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** log from splunk
- **Parallel safe:** yes
- **Requires:** splunk

**Use when:**

- reading the actual error text behind a spike the statistics located
- checking whether a stack trace matches one from a previous incident

**Not for:**

- establishing how much of something there is, which sampling cannot answer
- a query that has not been narrowed, where the sample is arbitrary

#### `victorialogs_log_statistics`

Count the log lines matching a query over a window and return the distribution across one field rather than the lines themselves. Call this first: the group it singles out is where the samples should come from.

- **Side effect:** `read` — reads only
- **Evidence:** log from victorialogs
- **Parallel safe:** yes
- **Requires:** victorialogs

**Use when:**

- an error-rate alert where the failing service or host is not yet known
- establishing whether one thing is failing loudly or everything is failing
- comparing a window's shape against the equivalent window before the symptom

**Not for:**

- reading a specific error message, which is what sampling is for
- latency across services, which a trace answers and a log count does not

#### `victorialogs_sample_logs`

Return a small, capped sample of the log lines matching a query over a window, newest first. Narrow the query with the statistics capability before calling this: a sample from an unnarrowed query is arbitrary.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** log from victorialogs
- **Parallel safe:** yes
- **Requires:** victorialogs

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

### metrics

#### `amplitude_active_alerts`

List the alert rules currently firing, with their labels and the time each started. Reach for it early: what else is already alerting is the cheapest way to tell a local failure from a shared one.

- **Side effect:** `read` — reads only
- **Evidence:** event from amplitude
- **Parallel safe:** yes
- **Requires:** amplitude

**Use when:**

- establishing what else was already broken when this alert fired
- finding the earliest firing alert, which is usually nearest the cause

**Not for:**

- the value of a metric, which needs a query rather than an alert list
- an alert that resolved before the investigation started

#### `amplitude_metric_statistics`

Evaluate a metric query over a window and return the series grouped by one label, with counts, rather than every sample. Use it to find which label value moved before asking anything about why.

- **Side effect:** `read` — reads only
- **Evidence:** metric from amplitude
- **Parallel safe:** yes
- **Requires:** amplitude

**Use when:**

- a saturation or error-rate alert where the affected instance is unknown
- establishing whether a change is one instance or the whole fleet

**Not for:**

- reading an individual log line, which a metric never contains
- a question about a single request, where a metric has no resolution

#### `groundcover_active_alerts`

List the alert rules currently firing, with their labels and the time each started. Reach for it early: what else is already alerting is the cheapest way to tell a local failure from a shared one.

- **Side effect:** `read` — reads only
- **Evidence:** event from groundcover
- **Parallel safe:** yes
- **Requires:** groundcover

**Use when:**

- establishing what else was already broken when this alert fired
- finding the earliest firing alert, which is usually nearest the cause

**Not for:**

- the value of a metric, which needs a query rather than an alert list
- an alert that resolved before the investigation started

#### `groundcover_metric_statistics`

Evaluate a metric query over a window and return the series grouped by one label, with counts, rather than every sample. Use it to find which label value moved before asking anything about why.

- **Side effect:** `read` — reads only
- **Evidence:** metric from groundcover
- **Parallel safe:** yes
- **Requires:** groundcover

**Use when:**

- a saturation or error-rate alert where the affected instance is unknown
- establishing whether a change is one instance or the whole fleet

**Not for:**

- reading an individual log line, which a metric never contains
- a question about a single request, where a metric has no resolution

#### `new_relic_active_alerts`

List the alert rules currently firing, with their labels and the time each started. Reach for it early: what else is already alerting is the cheapest way to tell a local failure from a shared one.

- **Side effect:** `read` — reads only
- **Evidence:** event from new_relic
- **Parallel safe:** yes
- **Requires:** new_relic

**Use when:**

- establishing what else was already broken when this alert fired
- finding the earliest firing alert, which is usually nearest the cause

**Not for:**

- the value of a metric, which needs a query rather than an alert list
- an alert that resolved before the investigation started

#### `new_relic_metric_statistics`

Evaluate a metric query over a window and return the series grouped by one label, with counts, rather than every sample. Use it to find which label value moved before asking anything about why.

- **Side effect:** `read` — reads only
- **Evidence:** metric from new_relic
- **Parallel safe:** yes
- **Requires:** new_relic

**Use when:**

- a saturation or error-rate alert where the affected instance is unknown
- establishing whether a change is one instance or the whole fleet

**Not for:**

- reading an individual log line, which a metric never contains
- a question about a single request, where a metric has no resolution

#### `posthog_active_alerts`

List the alert rules currently firing, with their labels and the time each started. Reach for it early: what else is already alerting is the cheapest way to tell a local failure from a shared one.

- **Side effect:** `read` — reads only
- **Evidence:** event from posthog
- **Parallel safe:** yes
- **Requires:** posthog

**Use when:**

- establishing what else was already broken when this alert fired
- finding the earliest firing alert, which is usually nearest the cause

**Not for:**

- the value of a metric, which needs a query rather than an alert list
- an alert that resolved before the investigation started

#### `posthog_metric_statistics`

Evaluate a metric query over a window and return the series grouped by one label, with counts, rather than every sample. Use it to find which label value moved before asking anything about why.

- **Side effect:** `read` — reads only
- **Evidence:** metric from posthog
- **Parallel safe:** yes
- **Requires:** posthog

**Use when:**

- a saturation or error-rate alert where the affected instance is unknown
- establishing whether a change is one instance or the whole fleet

**Not for:**

- reading an individual log line, which a metric never contains
- a question about a single request, where a metric has no resolution

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

#### `victoriametrics_active_alerts`

List the alert rules currently firing, with their labels and the time each started. Reach for it early: what else is already alerting is the cheapest way to tell a local failure from a shared one.

- **Side effect:** `read` — reads only
- **Evidence:** event from victoriametrics
- **Parallel safe:** yes
- **Requires:** victoriametrics

**Use when:**

- establishing what else was already broken when this alert fired
- finding the earliest firing alert, which is usually nearest the cause

**Not for:**

- the value of a metric, which needs a query rather than an alert list
- an alert that resolved before the investigation started

#### `victoriametrics_metric_statistics`

Evaluate a metric query over a window and return the series grouped by one label, with counts, rather than every sample. Use it to find which label value moved before asking anything about why.

- **Side effect:** `read` — reads only
- **Evidence:** metric from victoriametrics
- **Parallel safe:** yes
- **Requires:** victoriametrics

**Use when:**

- a saturation or error-rate alert where the affected instance is unknown
- establishing whether a change is one instance or the whole fleet

**Not for:**

- reading an individual log line, which a metric never contains
- a question about a single request, where a metric has no resolution

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

### ticketing

#### `clickup_issue_statistics`

Count the issues matching a query, grouped by status or assignee. It is the search-before-create step: if twelve issues already describe this, the investigation should link to them rather than open a thirteenth.

- **Side effect:** `read` — reads only
- **Evidence:** document from clickup
- **Parallel safe:** yes
- **Requires:** clickup

**Use when:**

- checking whether this symptom is already tracked before opening anything
- establishing how long a class of problem has been outstanding

**Not for:**

- reading one issue in full, which the issue list returns
- live system state, which a tracker never has

#### `clickup_recent_issues`

Return the issues matching a query, newest first and capped, with title, status, and assignee. Call it after the statistics so the ones read are from the group that matters.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** document from clickup
- **Parallel safe:** yes
- **Requires:** clickup

**Use when:**

- reading the ticket that already describes the symptom under investigation
- finding who last worked on a recurring failure

**Not for:**

- how many issues there are, which the statistics answer more cheaply
- the current state of the system, which a ticket only describes secondhand

#### `confluence_issue_statistics`

Count the issues matching a query, grouped by status or assignee. It is the search-before-create step: if twelve issues already describe this, the investigation should link to them rather than open a thirteenth.

- **Side effect:** `read` — reads only
- **Evidence:** document from confluence
- **Parallel safe:** yes
- **Requires:** confluence

**Use when:**

- checking whether this symptom is already tracked before opening anything
- establishing how long a class of problem has been outstanding

**Not for:**

- reading one issue in full, which the issue list returns
- live system state, which a tracker never has

#### `confluence_recent_issues`

Return the issues matching a query, newest first and capped, with title, status, and assignee. Call it after the statistics so the ones read are from the group that matters.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** document from confluence
- **Parallel safe:** yes
- **Requires:** confluence

**Use when:**

- reading the ticket that already describes the symptom under investigation
- finding who last worked on a recurring failure

**Not for:**

- how many issues there are, which the statistics answer more cheaply
- the current state of the system, which a ticket only describes secondhand

#### `google_docs_issue_statistics`

Count the issues matching a query, grouped by status or assignee. It is the search-before-create step: if twelve issues already describe this, the investigation should link to them rather than open a thirteenth.

- **Side effect:** `read` — reads only
- **Evidence:** document from google_docs
- **Parallel safe:** yes
- **Requires:** google_docs

**Use when:**

- checking whether this symptom is already tracked before opening anything
- establishing how long a class of problem has been outstanding

**Not for:**

- reading one issue in full, which the issue list returns
- live system state, which a tracker never has

#### `google_docs_recent_issues`

Return the issues matching a query, newest first and capped, with title, status, and assignee. Call it after the statistics so the ones read are from the group that matters.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** document from google_docs
- **Parallel safe:** yes
- **Requires:** google_docs

**Use when:**

- reading the ticket that already describes the symptom under investigation
- finding who last worked on a recurring failure

**Not for:**

- how many issues there are, which the statistics answer more cheaply
- the current state of the system, which a ticket only describes secondhand

#### `jira_issue_statistics`

Count the issues matching a query, grouped by status or assignee. It is the search-before-create step: if twelve issues already describe this, the investigation should link to them rather than open a thirteenth.

- **Side effect:** `read` — reads only
- **Evidence:** document from jira
- **Parallel safe:** yes
- **Requires:** jira

**Use when:**

- checking whether this symptom is already tracked before opening anything
- establishing how long a class of problem has been outstanding

**Not for:**

- reading one issue in full, which the issue list returns
- live system state, which a tracker never has

#### `jira_recent_issues`

Return the issues matching a query, newest first and capped, with title, status, and assignee. Call it after the statistics so the ones read are from the group that matters.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** document from jira
- **Parallel safe:** yes
- **Requires:** jira

**Use when:**

- reading the ticket that already describes the symptom under investigation
- finding who last worked on a recurring failure

**Not for:**

- how many issues there are, which the statistics answer more cheaply
- the current state of the system, which a ticket only describes secondhand

#### `linear_issue_statistics`

Count the issues matching a query, grouped by status or assignee. It is the search-before-create step: if twelve issues already describe this, the investigation should link to them rather than open a thirteenth.

- **Side effect:** `read` — reads only
- **Evidence:** document from linear
- **Parallel safe:** yes
- **Requires:** linear

**Use when:**

- checking whether this symptom is already tracked before opening anything
- establishing how long a class of problem has been outstanding

**Not for:**

- reading one issue in full, which the issue list returns
- live system state, which a tracker never has

#### `linear_recent_issues`

Return the issues matching a query, newest first and capped, with title, status, and assignee. Call it after the statistics so the ones read are from the group that matters.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** document from linear
- **Parallel safe:** yes
- **Requires:** linear

**Use when:**

- reading the ticket that already describes the symptom under investigation
- finding who last worked on a recurring failure

**Not for:**

- how many issues there are, which the statistics answer more cheaply
- the current state of the system, which a ticket only describes secondhand

#### `notion_issue_statistics`

Count the issues matching a query, grouped by status or assignee. It is the search-before-create step: if twelve issues already describe this, the investigation should link to them rather than open a thirteenth.

- **Side effect:** `read` — reads only
- **Evidence:** document from notion
- **Parallel safe:** yes
- **Requires:** notion

**Use when:**

- checking whether this symptom is already tracked before opening anything
- establishing how long a class of problem has been outstanding

**Not for:**

- reading one issue in full, which the issue list returns
- live system state, which a tracker never has

#### `notion_recent_issues`

Return the issues matching a query, newest first and capped, with title, status, and assignee. Call it after the statistics so the ones read are from the group that matters.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** document from notion
- **Parallel safe:** yes
- **Requires:** notion

**Use when:**

- reading the ticket that already describes the symptom under investigation
- finding who last worked on a recurring failure

**Not for:**

- how many issues there are, which the statistics answer more cheaply
- the current state of the system, which a ticket only describes secondhand

#### `trello_issue_statistics`

Count the issues matching a query, grouped by status or assignee. It is the search-before-create step: if twelve issues already describe this, the investigation should link to them rather than open a thirteenth.

- **Side effect:** `read` — reads only
- **Evidence:** document from trello
- **Parallel safe:** yes
- **Requires:** trello

**Use when:**

- checking whether this symptom is already tracked before opening anything
- establishing how long a class of problem has been outstanding

**Not for:**

- reading one issue in full, which the issue list returns
- live system state, which a tracker never has

#### `trello_recent_issues`

Return the issues matching a query, newest first and capped, with title, status, and assignee. Call it after the statistics so the ones read are from the group that matters.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** document from trello
- **Parallel safe:** yes
- **Requires:** trello

**Use when:**

- reading the ticket that already describes the symptom under investigation
- finding who last worked on a recurring failure

**Not for:**

- how many issues there are, which the statistics answer more cheaply
- the current state of the system, which a ticket only describes secondhand

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

#### `honeycomb_slow_traces`

Return the slowest traces for a service in a window, capped, with their duration and root operation. Use it after the statistics have named the operation, so the exemplars are from the part that is actually slow.

- **Side effect:** `read` — reads only
- **Evidence:** trace from honeycomb
- **Parallel safe:** yes
- **Requires:** honeycomb

**Use when:**

- finding an exemplar of the latency an aggregate has already located
- seeing which downstream call dominates a slow request

**Not for:**

- establishing how common the slowness is, which needs the aggregate
- an error with no latency component, where traces add nothing

#### `honeycomb_trace_statistics`

Count the traces for a service over a window and return them grouped by operation or status, rather than the spans. It is what says where the latency is concentrated before any single trace is opened.

- **Side effect:** `read` — reads only
- **Evidence:** trace from honeycomb
- **Parallel safe:** yes
- **Requires:** honeycomb

**Use when:**

- a latency alert where the slow operation is not yet known
- deciding whether one endpoint is slow or the whole service is

**Not for:**

- the contents of a log line, which a trace does not carry
- a single known request, where one trace is the whole answer

#### `jaeger_slow_traces`

Return the slowest traces for a service in a window, capped, with their duration and root operation. Use it after the statistics have named the operation, so the exemplars are from the part that is actually slow.

- **Side effect:** `read` — reads only
- **Evidence:** trace from jaeger
- **Parallel safe:** yes
- **Requires:** jaeger

**Use when:**

- finding an exemplar of the latency an aggregate has already located
- seeing which downstream call dominates a slow request

**Not for:**

- establishing how common the slowness is, which needs the aggregate
- an error with no latency component, where traces add nothing

#### `jaeger_trace_statistics`

Count the traces for a service over a window and return them grouped by operation or status, rather than the spans. It is what says where the latency is concentrated before any single trace is opened.

- **Side effect:** `read` — reads only
- **Evidence:** trace from jaeger
- **Parallel safe:** yes
- **Requires:** jaeger

**Use when:**

- a latency alert where the slow operation is not yet known
- deciding whether one endpoint is slow or the whole service is

**Not for:**

- the contents of a log line, which a trace does not carry
- a single known request, where one trace is the whole answer

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

#### `tempo_slow_traces`

Return the slowest traces for a service in a window, capped, with their duration and root operation. Use it after the statistics have named the operation, so the exemplars are from the part that is actually slow.

- **Side effect:** `read` — reads only
- **Evidence:** trace from tempo
- **Parallel safe:** yes
- **Requires:** tempo

**Use when:**

- finding an exemplar of the latency an aggregate has already located
- seeing which downstream call dominates a slow request

**Not for:**

- establishing how common the slowness is, which needs the aggregate
- an error with no latency component, where traces add nothing

#### `tempo_trace_statistics`

Count the traces for a service over a window and return them grouped by operation or status, rather than the spans. It is what says where the latency is concentrated before any single trace is opened.

- **Side effect:** `read` — reads only
- **Evidence:** trace from tempo
- **Parallel safe:** yes
- **Requires:** tempo

**Use when:**

- a latency alert where the slow operation is not yet known
- deciding whether one endpoint is slow or the whole service is

**Not for:**

- the contents of a log line, which a trace does not carry
- a single known request, where one trace is the whole answer

### vcs

#### `bitbucket_change_statistics`

Count the commits landing on a repository in a window, grouped by author or branch. It answers 'was there a deploy-shaped amount of change here' before any individual diff is read.

- **Side effect:** `read` — reads only
- **Evidence:** change from bitbucket
- **Parallel safe:** yes
- **Requires:** bitbucket

**Use when:**

- an incident with a known start time and a suspected release
- establishing whether a quiet service was changed at all

**Not for:**

- what one change did, which needs the change list rather than a count
- a runtime failure with no deployment in the window

#### `bitbucket_recent_changes`

Return the changes merged into a repository in a window, newest first and capped, with title and author. This is what turns a time correlation into a specific change somebody can read.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** change from bitbucket
- **Parallel safe:** yes
- **Requires:** bitbucket

**Use when:**

- identifying the release that lines up with the start of a symptom
- reading what changed in a service between two known-good times

**Not for:**

- how much changed overall, which the statistics answer more cheaply
- a configuration change made outside version control

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

#### `gitlab_change_statistics`

Count the commits landing on a repository in a window, grouped by author or branch. It answers 'was there a deploy-shaped amount of change here' before any individual diff is read.

- **Side effect:** `read` — reads only
- **Evidence:** change from gitlab
- **Parallel safe:** yes
- **Requires:** gitlab

**Use when:**

- an incident with a known start time and a suspected release
- establishing whether a quiet service was changed at all

**Not for:**

- what one change did, which needs the change list rather than a count
- a runtime failure with no deployment in the window

#### `gitlab_recent_changes`

Return the changes merged into a repository in a window, newest first and capped, with title and author. This is what turns a time correlation into a specific change somebody can read.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** change from gitlab
- **Parallel safe:** yes
- **Requires:** gitlab

**Use when:**

- identifying the release that lines up with the start of a symptom
- reading what changed in a service between two known-good times

**Not for:**

- how much changed overall, which the statistics answer more cheaply
- a configuration change made outside version control

#### `sourcegraph_change_statistics`

Count the commits landing on a repository in a window, grouped by author or branch. It answers 'was there a deploy-shaped amount of change here' before any individual diff is read.

- **Side effect:** `read` — reads only
- **Evidence:** change from sourcegraph
- **Parallel safe:** yes
- **Requires:** sourcegraph

**Use when:**

- an incident with a known start time and a suspected release
- establishing whether a quiet service was changed at all

**Not for:**

- what one change did, which needs the change list rather than a count
- a runtime failure with no deployment in the window

#### `sourcegraph_recent_changes`

Return the changes merged into a repository in a window, newest first and capped, with title and author. This is what turns a time correlation into a specific change somebody can read.

- **Side effect:** `read_sensitive` — reads data that may identify people
- **Evidence:** change from sourcegraph
- **Parallel safe:** yes
- **Requires:** sourcegraph

**Use when:**

- identifying the release that lines up with the start of a symptom
- reading what changed in a service between two known-good times

**Not for:**

- how much changed overall, which the statistics answer more cheaply
- a configuration change made outside version control
