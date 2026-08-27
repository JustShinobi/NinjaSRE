# Tasks — 025 Integration Catalogue Parity

Each integration task means the full ten-step checklist from `plan.md`:
scaffold, schema, client, verifier, capabilities, skill, docs, scenario, contract
suite green, live verification where credentials exist.

## Phase 1 — Tier 1 (18)

- **T001** Kubernetes — the reference integration; validates the framework on a
  non-REST-shaped API.
- **T002** AWS EKS — validates proxy-side SigV4.
- **T003** [P] AWS EC2.
- **T004** [P] AWS CloudWatch (metrics and logs, statistics-first variants).
- **T005** [P] AWS RDS.
- **T006** [P] AWS Lambda.
- **T007** [P] AWS ECS.
- **T008** [P] AWS CloudTrail.
- **T009** [P] Grafana (dashboards, alerts, datasources).
- **T010** [P] Loki (statistics-first log capabilities).
- **T011** [P] Prometheus.
- **T012** [P] Datadog (logs, metrics, monitors, APM).
- **T013** [P] Elasticsearch.
- **T014** [P] PagerDuty.
- **T015** [P] Slack.
- **T016** [P] GitHub.
- **T017** [P] Jira.
- **T018** [P] PostgreSQL.
- **T019** [P] Sentry.
- **T020** [P] Alertmanager.

## Phase 2 — Tier 1 gate

- **T021** End-to-end investigation on a Kubernetes and AWS stack using only
  tier-1 integrations (SC-006).
- **T022** Measure actual per-integration effort against feature 024's SC-001
  estimate; record the finding.
- **T023** Adjust the framework, templates, or scaffold based on tier-1 experience
  before committing the remaining ~68.

## Phase 3 — Tier 2, observability and cloud

- **T024** [P] New Relic. **T025** [P] Honeycomb. **T026** [P] Coralogix.
- **T027** [P] groundcover. **T028** [P] OpenSearch. **T029** [P] Better Stack.
- **T030** [P] Splunk. **T031** [P] VictoriaLogs. **T032** [P] VictoriaMetrics.
- **T033** [P] SigNoz. **T034** [P] OpenObserve. **T035** [P] Azure Monitor.
- **T036** [P] Jaeger. **T037** [P] Tempo. **T038** [P] Hermes.
- **T039** [P] GCP. **T040** [P] Azure. **T041** [P] ArgoCD.
- **T042** [P] Jenkins. **T043** [P] Helm. **T044** [P] Docker.

## Phase 4 — Tier 2, data and version control

- **T045** [P] MySQL. **T046** [P] Redis. **T047** [P] Kafka.
- **T048** [P] GitLab. **T049** [P] Opsgenie. **T050** [P] Microsoft Teams.
- **T051** [P] Confluence. **T052** [P] Bitbucket. **T053** [P] MongoDB.

## Phase 5 — Tier 3, databases and data platform

- **T054** [P] MariaDB. **T055** [P] MongoDB Atlas. **T056** [P] ClickHouse.
- **T057** [P] Azure SQL. **T058** [P] Snowflake. **T059** [P] BigQuery.
- **T060** [P] Supabase. **T061** [P] Airflow. **T062** [P] Spark.
- **T063** [P] Prefect. **T064** [P] RabbitMQ. **T065** [P] Dagster.
- **T066** [P] Temporal. **T067** [P] Flink.

## Phase 6 — Tier 3, project, communication, analytics

- **T068** [P] Linear. **T069** [P] ClickUp. **T070** [P] Trello.
- **T071** [P] Notion. **T072** [P] Google Docs. **T073** [P] Sourcegraph.
- **T074** [P] incident.io. **T075** [P] Blameless. **T076** [P] FireHydrant.
- **T077** [P] ServiceNow. **T078** [P] Telegram. **T079** [P] Discord.
- **T080** [P] Rocket.Chat. **T081** [P] WhatsApp. **T082** [P] Pushover.
- **T083** [P] SMTP. **T084** [P] Twilio. **T085** [P] Amplitude.
- **T086** [P] PostHog. **T087** [P] flagd/OpenFeature.
- **T088** [P] Vercel. **T089** [P] Railway. **T090** [P] AWS S3. **T091** [P] AWS ELB.

## Phase 7 — Catalogue completion

- **T092** Documentation generated for all 86 from the catalogue, drift-checked
  (FR-014); confirm SC-007.
- **T093** Live verification for every integration where maintainers hold
  credentials.
- **T094** Explicit unverified marking for the rest (SC-008).
- **T095** Record any integration that could not reach parity with its external
  reason (FR-003).
- **T096** Full contract suite run across all 86 (SC-001).
- **T097** Full synthetic scenario run across all 86 (SC-002).
- **T098** Catalogue-wide credential-access assertion (SC-003).
- **T099** Catalogue-wide write-capability audit: level declared and rollback
  generator present (SC-004).
- **T100** Catalogue-wide skill validation: binding valid, shell anti-pattern lint
  clean (SC-005).
- **T101** Capability-selection sanity check across overlapping domains (acceptance
  scenario 5).
- **T102** Update `docs/provenance-map.md` with every harvested module; confirm
  `make check-provenance`.

## Definition of done

- [ ] All 86 pass the parameterised contract suite (SC-001)
- [ ] All 86 have a solvable synthetic scenario (SC-002)
- [ ] No integration client reads a credential (SC-003)
- [ ] Every write declares its level and has a rollback generator (SC-004)
- [ ] Every skill passes binding and anti-pattern validation (SC-005)
- [ ] Tier-1-only end-to-end investigation works (SC-006)
- [ ] Documentation generated for all 86 without drift (SC-007)
- [ ] Live verification done or explicitly marked unverified (SC-008)
- [ ] `make verify` green
