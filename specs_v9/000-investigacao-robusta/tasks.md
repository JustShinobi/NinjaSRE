---

description: "Tasks test-first para investigação robusta, recorrência e postmortems"
---

# Tasks: Investigação robusta, recorrência e postmortems

**Input**: documentos de design em `/specs_v9/000-investigacao-robusta/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/` e
`quickstart.md`

**Tests**: obrigatórios. A constituição e a spec exigem test-first; em cada fase, execute os
tasks de teste, confirme a falha pelo comportamento ausente e só então implemente.

**Organization**: tasks agrupados por user story. Código, identificadores e comentários novos
devem ser em inglês; textos de produto e artefatos de planejamento podem ser em pt-BR.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode ser executado em paralelo porque usa arquivos distintos e não depende de outro
  task incompleto da mesma fase.
- **[Story]**: mapeia para as oito user stories de `spec.md`.
- Todo task cita o caminho exato dos arquivos que deve criar ou alterar.
- IDs são estáveis e alocados por acréscimo. T132–T134 nasceram de uma análise cruzada
  posterior e vivem na fase a que pertencem, não no fim do arquivo: a ordem de execução é a
  ordem do documento, e o número é apenas um nome.

## Phase 1: Setup (infraestrutura compartilhada)

**Purpose**: preparar os módulos e fixtures sem introduzir comportamento de serving.

- [ ] T001 Criar o package vazio de domínio em `platform/knowledge/postmortems/__init__.py` e os diretórios de testes `tests/unit/platform/knowledge/postmortems/` e `tests/contract/persistence/`
- [ ] T002 [P] Registrar o baseline anonimizado de staging e seu schema de validação em `tests/synthetic/fixtures/recurrence_baseline.json` e `tests/unit/harness/test_fixture_validation.py`

---

## Phase 2: Foundational (pré-requisitos bloqueantes)

**Purpose**: corrigir a identidade de evidência e fornecer o contrato persistente mínimo usado
por correlação, postmortem, recall e auditoria.

**⚠️ CRITICAL**: nenhum incremento da feature pode ser considerado confiável antes desta fase.

### Tests da fundação — escrever e confirmar falha primeiro

- [ ] T003 [P] Adicionar casos de dois runs com o mesmo `evidence_id`, citação escopada e rejeição cross-run em `tests/contract/persistence/test_run_trace_store.py`
- [ ] T004 [P] Criar testes de upgrade, downgrade sem colisão e recusa segura/rewrite com colisão em `tests/contract/persistence/test_run_scoped_evidence_migration.py`
- [ ] T005 [P] Caracterizar resolução de evidence refs e o contrato completo de toda tool call — início, fim, duração, entrada/resultado protegidos, estado, outcome, cache/reuse e refs — em `tests/unit/platform/runs/test_recorder.py`, `tests/unit/platform/reporting/test_models.py`, `tests/unit/platform/memory/test_extraction_and_lifecycle.py`, `tests/unit/core/agent/test_trace_replay.py` e `tests/contract/persistence/test_run_trace_store.py`
- [ ] T006 [P] Criar o contrato parametrizado de postmortem store para tenant, revisão imutável, fontes, evidence refs e criação/leitura/agregação de `KnowledgeAssociation` em `tests/contract/persistence/test_postmortem_store.py`

### Implementação da fundação

- [ ] T007 Definir `EvidenceReference(run_id, evidence_id)` e alterar `mark_cited` para exigir run em `platform/persistence/ports/run_trace_store.py` e `platform/reporting/models.py`
- [ ] T008 Implementar a chave composta e validação cross-run no fake em `platform/persistence/fakes/run_trace_store.py`
- [ ] T009 Implementar a chave composta em PostgreSQL em `platform/persistence/postgres/models.py` e `platform/persistence/postgres/repositories/run_trace_store.py`
- [ ] T010 Criar a migration reversível `platform/persistence/migrations/versions/0023_run_scoped_evidence.py` com relatório de referências irrecuperáveis e proteção contra perda no downgrade
- [ ] T011 Migrar gravação e citação para referências escopadas preservando todos os campos protegidos e temporais da tool call definidos no contrato interno em `platform/runs/recorder.py`, `platform/runs/recording.py` e `platform/incidents/lifecycle.py`
- [ ] T012 Migrar consumidores de evidência em `platform/reporting/builder.py`, `platform/memory/extraction.py`, `core/agent/session.py` e `core/state/evidence.py`
- [ ] T013 Definir os modelos editoriais mínimos e o protocolo `PostmortemStore` em `platform/knowledge/postmortems/models.py` e `platform/persistence/ports/postmortem_store.py`
- [ ] T014 Implementar o contrato mínimo do postmortem store no fake em `platform/persistence/fakes/postmortem_store.py` e registrá-lo em `platform/persistence/fakes/gateway.py`
- [ ] T015 Implementar tabelas/repositório do postmortem store e a migration inicial em `platform/persistence/postgres/models.py`, `platform/persistence/postgres/repositories/postmortem_store.py` e `platform/persistence/migrations/versions/0024_postmortems.py`
- [ ] T016 Expor `PostmortemStore` pela UoW e pelos composition gateways em `platform/persistence/ports/transaction.py`, `platform/persistence/postgres/gateway.py` e `platform/persistence/fakes/gateway.py`

**Checkpoint**: evidence refs são inequívocas nos fakes e no PostgreSQL; postmortems podem ser
persistidos por port sem ainda estarem expostos ao produto.

---

## Phase 3: User Story 1 — Uma repetição não vira nova investigação completa (Priority: P1) 🎯 MVP

**Goal**: preservar todas as entregas/ocorrências e, sob concorrência ou restart, manter no
máximo um incidente vivo e um run ativo para a mesma condição sem mudança material.

**Independent Test**: enviar simultaneamente retries e novos eventos equivalentes, reiniciar o
estado do gateway e comprovar tentativas auditáveis, uma ocorrência lógica por evento, um
incidente vivo e apenas um run ativo; uma mudança material precisa abrir nova avaliação.

### Tests para User Story 1 — escrever e confirmar falha primeiro

- [ ] T017 [P] [US1] Estender o contrato de incident store com delivery attempts, occurrences, correlation decisions, active run e dispatch claim/lease em `tests/contract/persistence/test_incident_store.py`
- [ ] T018 [P] [US1] Criar teste PostgreSQL de barreira concorrente, winner/loser, lease expirado e ausência de run órfão em `tests/contract/persistence/test_incident_dispatch_concurrency.py`
- [ ] T019 [P] [US1] Criar testes de migration para consolidação auditável de incidentes vivos duplicados e backfill de `active_run_id` em `tests/contract/persistence/test_incident_correlation_migration.py`
- [ ] T020 [P] [US1] Cobrir retry, material change, alertas diferentes de múltiplas fontes na mesma e fora da janela causal, diagnóstico dentro e fora da janela de atualidade de FR-006, preservação de identidade/evidência, resolução e recorrência pós-fechamento em `tests/unit/platform/incidents/test_incident_lifecycle.py`, `tests/unit/platform/incidents/test_dispatch_and_escalation.py` e `tests/unit/platform/incidents/test_joining_a_live_investigation.py`
- [ ] T021 [P] [US1] Cobrir restart/múltiplas réplicas e garantir um único `RUN_STARTED` no serving path em `tests/unit/gateway/webhooks/test_router.py`, `tests/unit/gateway/webhooks/test_alertmanager_delivery_identity.py` e `tests/contract/alerts/test_alertmanager_delivery_contract.py`

### Implementação para User Story 1

- [ ] T022 [US1] Definir `DeliveryAttempt`, `IncidentOccurrence`, `CorrelationDecision`, resultados fechados e as constantes nomeadas de fallback, lease, janela causal e atualidade de diagnóstico (24 h, FR-006) em `platform/incidents/ingestion.py`, `platform/incidents/correlation.py`, `platform/incidents/dispatch.py`, `config/constants/investigation.py` e `config/constants/__init__.py`
- [ ] T023 [US1] Estender o port e fake com ocorrência, decisão, `claim_open_incident` e `DispatchClaim` em `platform/persistence/ports/incident_store.py` e `platform/persistence/fakes/incident_store.py`
- [ ] T024 [US1] Implementar constraints, locks/claims e queries duráveis em `platform/persistence/postgres/models.py` e `platform/persistence/postgres/repositories/incident_store.py`
- [ ] T025 [US1] Criar `platform/persistence/migrations/versions/0025_durable_incident_correlation.py` com unique partial index, consolidação auditável e downgrade reversível
- [ ] T026 [US1] Fazer `IncidentLifecycle` continuar como único construtor e usar claim atômico em `platform/incidents/lifecycle.py` e `platform/incidents/service.py`
- [ ] T027 [US1] Implementar dispatch claim com lease/reaper e tornar limites em memória apenas throttle local em `platform/incidents/dispatch.py`
- [ ] T028 [US1] Criar run, anexar `run_ids`, preencher `active_run_id` e confirmar claim na mesma UoW, agendando `_drive` somente pós-commit em `gateway/http/orchestration.py`
- [ ] T029 [US1] Implementar o intake canônico que registra tentativa, resolve ocorrência, correlaciona alertas distintos pela janela causal nomeada sem perder nomes/fontes/evidências e decide join/start em `platform/incidents/ingestion.py` e `platform/incidents/correlation.py`
- [ ] T030 [US1] Delegar webhooks ao intake durável e retirar `IdempotencyIndex`/`DeduplicationIndex` do caminho autoritativo em `gateway/webhooks/router.py`, `gateway/http/state.py` e `gateway/http/asgi.py`
- [ ] T031 [US1] Reconciliar finalização, cancelamento, expiração e resolução upstream sem apagar histórico em `platform/incidents/lifecycle.py`, `platform/incidents/joining.py` e `gateway/http/orchestration.py`
- [ ] T032 [US1] Expor estado real, `active_run_id`, occurrences e correlation rationale em `gateway/http/routes/models.py` e `gateway/http/routes/incidents.py`
- [ ] T033 [P] [US1] Escrever testes de console para incidente aberto versus run ativo e grupo expandido de ocorrências em `console/tests/unit/surfaces/incidents.test.tsx`, `console/tests/unit/surfaces/incident-detail.test.tsx` e `console/tests/unit/surfaces/incident-group-list.test.tsx`
- [ ] T034 [US1] Atualizar as superfícies de incidente e seus estados em `console/src/surfaces/screens/incidents.tsx`, `console/src/surfaces/screens/incident-detail.tsx`, `console/src/surfaces/incident-group-list.tsx` e `console/src/design/status.ts`
- [ ] T035 [US1] Adicionar cenários sintéticos Proxmox de muitas entregas e de alertas distintos correlacionáveis/não correlacionáveis para a mesma VM, com assert de redução de runs sem perda de nomes, fontes, evidências ou ocorrências, em `tests/synthetic/test_durable_incident_recurrence.py` e `tests/synthetic/proxmox/guests/repeated-powered-off/`
- [ ] T132 [P] [US1] Cobrir que a triagem recebe a `CorrelationDecision` durável, nunca rotula como novo um incidente com ocorrências ou runs anexados e não abre nem anexa incidente por índice próprio, e que resta uma única autoridade de correlação no serving path, em `tests/unit/core/pipeline/stages/test_intake.py` e `tests/architecture/test_one_incident_correlation_authority.py`
- [ ] T133 [US1] Fazer o stage de intake consumir a decisão durável em vez de decidir — remover `IncidentIndex`, fingerprint e janela do caminho decisório, mantendo a classificação apenas como anotação explicável — em `core/pipeline/stages/intake/node.py`, `core/pipeline/stages/intake/dedup.py`, `core/pipeline/ports.py` e `gateway/runtime/investigator.py`

**Checkpoint**: o MVP reduz investigações duplicadas sem depender de postmortem e pode ser
implantado/medido isoladamente. Existe exatamente uma autoridade de correlação, e ela é
durável.

---

## Phase 4: User Story 2 — Recorrência conhecida usa postmortem antes do trabalho amplo (Priority: P1)

**Goal**: usar critérios estruturados publicados antes do plano amplo e recall semântico apenas
depois de evidence anchor, confirmando rápido ou escalando no mesmo runtime.

**Independent Test**: com um postmortem publicado semeado diretamente no store, executar três
casos — recorrência confirmada, fato contraditório e problema novo semelhante — e comprovar
evidence própria, recall posterior ao anchor, caminho curto somente no primeiro e escalada nos
demais.

### Tests para User Story 2 — escrever e confirmar falha primeiro

- [ ] T036 [P] [US2] Cobrir exact/semantic/weak match, score mínimo 0,80, margem 0,10, empate determinístico, fato obrigatório ausente/contradito, conflito entre revisões, `recall@3` e filtro de published/current/tenant em `tests/unit/platform/knowledge/postmortems/test_matching.py` e `tests/unit/platform/knowledge/postmortems/test_search.py`
- [ ] T037 [P] [US2] Cobrir ordem evidence-anchor → recall → plano, ausência de score na classificação pré-run, confirmação citada e escalada monotônica em `tests/unit/core/pipeline/test_recurrence_flow.py` e `tests/unit/core/pipeline/stages/test_gather_evidence.py`
- [ ] T038 [P] [US2] Definir corpus versionado e pré-rotulado com no mínimo 200 cenários — ao menos 100 recorrências relevantes e 100 negativos — cobrindo confirmação, empate, contradição, mudança material e novo problema semelhante em `tests/synthetic/test_postmortem_recurrence.py` e `tests/synthetic/fixtures/postmortem_recurrence/`

### Implementação para User Story 2

- [ ] T039 [US2] Implementar dois classificadores separados conforme FR-013/FR-014 — o pré-run, determinístico, sem score nem recuperação semântica, e o pós-anchor, com score/margem explicáveis — e busca somente de revisões publicadas/vigentes em `platform/knowledge/postmortems/matching.py` e `platform/knowledge/postmortems/search.py`
- [ ] T040 [US2] Estender `KnowledgeService` e a capability existente com resultados tipados de postmortem em `platform/knowledge/service.py`, `capabilities/tools/system/knowledge_search/results.py`, `capabilities/tools/system/knowledge_search/tool.py` e `capabilities/tools/system/knowledge_search/binding.py`
- [ ] T041 [US2] Definir modo, critérios, decisões, score/margem/ordenação versionados e ceilings nomeados de validação curta, reexportando toda constante, em `core/pipeline/ports.py`, `config/constants/investigation.py`, `config/constants/knowledge.py` e `config/constants/__init__.py`
- [ ] T042 [US2] Implementar o stage de validação/contradição/escalada no runtime canônico em `core/pipeline/stages/recurrence_validation.py`
- [ ] T043 [US2] Fazer o pipeline coletar evidence anchor antes de recall e registrar passos removidos/priorizados/mantidos em `core/pipeline/stages/gather_evidence.py` e `core/pipeline/stages/plan_evidence.py`
- [ ] T044 [US2] Estender o port e as implementações fake/PostgreSQL e persistir `KnowledgeAssociation` com query digest, candidates, decisão, influência e refs somente pela UoW em `platform/persistence/ports/postmortem_store.py`, `platform/persistence/fakes/postmortem_store.py`, `platform/persistence/postgres/repositories/postmortem_store.py` e `platform/knowledge/postmortems/service.py`
- [ ] T045 [US2] Emitir os eventos `knowledge.queried`, `postmortem.considered`, `recurrence.validated` e `investigation.escalated` em `core/agent/hooks/builtin/tracing.py` e `platform/runs/recorder.py`
- [ ] T046 [US2] Compor matcher, KnowledgeService e modo do pipeline no serving path em `gateway/runtime/investigator.py` e `gateway/http/asgi.py`
- [ ] T047 [US2] Implementar relação entre nova recorrência, incidente anterior e revisão de postmortem sem reabrir histórico em `platform/incidents/correlation.py` e `platform/incidents/lifecycle.py`
- [ ] T048 [US2] Executar e estabilizar os cenários de `tests/synthetic/test_postmortem_recurrence.py`, registrando tokens, calls, duração, precisão, `recall@3`, falsa confirmação, empates e cobertura de evidência no resultado do harness, e falhar quando menos de 95% das recorrências confirmadas concluírem em até 60 segundos (SC-003)

**Checkpoint**: a história funciona com postmortem publicado por fixture, independentemente da
UI/editor de postmortem da US3/US6.

---

## Phase 5: User Story 3 — Transformar incidente ou investigação em postmortem (Priority: P1)

**Goal**: criar um draft determinístico, citável e revisável a partir de incidente ou run sem
alterar nenhuma fonte original.

**Independent Test**: a partir de um incidente/run com timeline e evidência, criar o draft,
confirmar campos preenchidos/proveniência/lacunas, links recíprocos e ausência de mutação das
fontes; repetir com a mesma idempotency key e obter o mesmo resultado.

### Tests para User Story 3 — escrever e confirmar falha primeiro

- [ ] T049 [P] [US3] Cobrir projeção determinística, campos `review_required`, múltiplas fontes e não mutação das origens em `tests/unit/platform/knowledge/postmortems/test_drafts.py`
- [ ] T050 [P] [US3] Criar contract tests para POST por incidente/run, idempotência, tenant e duplicate candidates em `tests/unit/gateway/http/test_postmortem_routes.py` e `tests/contract/console/test_postmortem_contract.py`
- [ ] T051 [P] [US3] Escrever testes das ações e editor inicial no console em `console/tests/unit/surfaces/incident-detail.test.tsx`, `console/tests/unit/surfaces/run-detail.test.tsx` e `console/tests/unit/surfaces/postmortem-editor.test.tsx`

### Implementação para User Story 3

- [ ] T052 [US3] Implementar draft builder determinístico a partir de incident, occurrence, run, episode e evidence refs em `platform/knowledge/postmortems/drafts.py`
- [ ] T053 [US3] Implementar criação manual/from-source, idempotência, detecção explicável de duplicatas e proposals de grupos repetidos bem-evidenciados em `platform/knowledge/postmortems/service.py` e `platform/knowledge/proposals.py`
- [ ] T054 [US3] Implementar POST `/v1/incidents/{incident_id}/postmortem`, POST `/v1/investigations/{run_id}/postmortem` e criação manual em `gateway/http/routes/incidents.py`, `gateway/http/routes/investigations.py` e `gateway/http/routes/knowledge.py`
- [ ] T055 [US3] Expor links recíprocos e fontes navegáveis nos modelos de incidente, run e postmortem em `gateway/http/routes/models.py`, `gateway/http/routes/incidents.py` e `gateway/http/routes/investigations.py`
- [ ] T056 [US3] Incorporar os schemas/operations de criação ao OpenAPI canônico e fixture em `gateway/http/app.py` e `fixtures/contract/openapi.json`, depois regenerar `console/src/api/schema.ts`
- [ ] T057 [US3] Criar courier route idempotente para drafts em `console/src/app/api/postmortem/route.ts`
- [ ] T058 [US3] Adicionar ações “Criar postmortem”, seleção de fontes e editor de draft em `console/src/surfaces/screens/incident-detail.tsx`, `console/src/surfaces/screens/run-detail.tsx` e `console/src/surfaces/screens/postmortem-editor.tsx`
- [ ] T059 [P] [US3] Adicionar mensagens pt-BR/en do fluxo de criação e lacunas em `console/src/i18n/pt-BR.ts`, `console/src/i18n/en.ts` e `console/src/i18n/messages.ts`
- [ ] T134 [P] [US3] Adicionar a ação “Criar postmortem” à representação expandida de incidentes com fonte suficiente, e ocultá-la quando não houver, em `console/src/surfaces/incident-group-list.tsx` e `console/tests/unit/surfaces/incident-group-list.test.tsx`
- [ ] T060 [US3] Criar E2E de draft por incidente e por run, incluindo retry idempotente e fontes intactas, em `console/tests/e2e/postmortem-from-incident.acceptance.spec.ts`

**Checkpoint**: operadores criam drafts úteis sem depender do lifecycle completo de publicação.

---

## Phase 6: User Story 4 — Toda conclusão aponta para a evidência correta do próprio run (Priority: P1)

**Goal**: detectar refs quebradas/cross-run e impedir que claims, reports, episodes ou
postmortems as apresentem como validadas.

**Independent Test**: persistir `e1` em dois runs, citar corretamente cada uma e tentar uma ref
cruzada; as refs válidas devem navegar à observação correta e a cruzada deve virar violação de
integridade/hipótese, bloqueando publicação.

### Tests para User Story 4 — escrever e confirmar falha primeiro

- [ ] T061 [P] [US4] Criar replay sintético com IDs locais iguais e referências válidas/quebradas em `tests/synthetic/test_run_scoped_evidence_replay.py`
- [ ] T062 [P] [US4] Cobrir auditoria, rebaixamento de claim e bloqueio de postmortem com ref inválida em `tests/unit/platform/runs/test_evidence_integrity.py`, `tests/unit/platform/reporting/test_models.py` e `tests/unit/platform/knowledge/postmortems/test_drafts.py`

### Implementação para User Story 4

- [ ] T063 [US4] Adicionar auditoria paginada de evidence refs ao port/fake/Postgres em `platform/persistence/ports/run_trace_store.py`, `platform/persistence/fakes/run_trace_store.py` e `platform/persistence/postgres/repositories/run_trace_store.py`
- [ ] T064 [US4] Implementar o validador de integridade e seus reason codes em `platform/runs/evidence.py`
- [ ] T065 [US4] Integrar o validador a claims, reports, episodes e publicação de postmortem em `platform/reporting/builder.py`, `platform/memory/extraction.py` e `platform/knowledge/postmortems/service.py`
- [ ] T066 [US4] Expor resolução/navegação e violações de evidence refs em `gateway/http/routes/investigations.py` e `gateway/http/routes/knowledge.py`
- [ ] T067 [US4] Renderizar fonte correta, run de origem e estado inválido sem mascará-lo em `console/src/surfaces/run-evidence.tsx`, `console/src/surfaces/screens/run-detail.tsx` e `console/src/surfaces/screens/postmortem-editor.tsx`

**Checkpoint**: 100% das refs novas resolvem para seu run; nenhuma ref cruzada sustenta finding.

---

## Phase 7: User Story 5 — A investigação gasta apenas no que pode mudar a conclusão (Priority: P2)

**Goal**: filtrar capabilities inviáveis, parar repetições, limitar contexto/coleta e atribuir
custo e outcome por fase sem fabricar zeros.

**Independent Test**: executar uma investigação com capability não configurada, falha
determinística descoberta, chamadas idênticas e claims já apoiadas; verificar catálogo filtrado,
cache negativo/reuse informado ao raciocínio, conclusão limitada e métricas por fase.

### Tests para User Story 5 — escrever e confirmar falha primeiro

- [ ] T068 [P] [US5] Cobrir snapshot baseado em configuração+verificação e exclusão anterior à seleção em `tests/unit/gateway/runtime/test_run_availability.py` e `tests/contract/persistence/test_verification_ledger.py`
- [ ] T069 [P] [US5] Cobrir cache negativo por run levantado somente por verificação bem-sucedida da fonte (nunca por tempo, passo do plano ou parâmetro diferente), falha transitória seguindo retry normal, janela de validade padrão do run com override por capability e cache hit comunicado ao modelo em `tests/unit/gateway/runtime/test_react_investigation_runner.py` e `tests/unit/core/agent/test_tool_cache.py`
- [ ] T070 [P] [US5] Cobrir phase metrics, `unknown`, outcomes separados e completion gate em `tests/unit/platform/runs/test_stage_recording.py`, `tests/unit/platform/runs/test_recording.py` e `tests/unit/core/agent/test_stagnation.py`
- [ ] T071 [P] [US5] Criar cenário de eficiência com calls inúteis, contexto repetido e baseline comparável em `tests/synthetic/test_investigation_token_efficiency.py`

### Implementação para User Story 5

- [ ] T072 [US5] Construir e persistir `CapabilityAvailabilitySnapshot` com reason codes reais em `core/pipeline/ports.py`, `gateway/runtime/investigator.py` e `platform/runs/recorder.py`
- [ ] T073 [US5] Filtrar o catálogo e implementar cache negativo estritamente por run, com a supressão levantada apenas por nova verificação bem-sucedida registrada no availability snapshot, em `core/state/catalogue.py`, `core/agent/tool_cache.py` e `core/agent/react_loop.py`
- [ ] T074 [US5] Declarar ceilings de recurrence, contexto histórico, tool calls, no-new-evidence e a janela de validade de reuso de chamada de FR-020 (padrão: duração do run; override por capability) em `config/constants/investigation.py`, `config/constants/capabilities.py`, `config/constants/memory.py` e `config/constants/__init__.py`
- [ ] T075 [US5] Registrar tokens/calls/duração/context peak por fase e preservar `unknown` em `core/agent/hooks/builtin/accounting.py`, `platform/runs/recording.py` e `platform/runs/recorder.py`
- [ ] T076 [US5] Persistir mode, termination kind, diagnostic outcome, production status, availability, `applied_limits` (FR-055) e phase metrics com contadores de token anuláveis — `null` é desconhecido, `0` é medido — em `platform/persistence/postgres/models.py`, `platform/persistence/postgres/repositories/run_trace_store.py` e `platform/persistence/migrations/versions/0026_run_outcomes_and_phase_metrics.py`
- [ ] T077 [US5] Reconciliar outcome técnico/diagnóstico/produção e excluir runs vazios de sucesso em `platform/runs/recording.py`, `platform/incidents/investigation_summary.py` e `platform/memory/lifecycle.py`
- [ ] T078 [US5] Encerrar coleta quando claims estão apoiadas ou o ceiling sem evidência é atingido em `core/agent/stagnation.py`, `core/agent/conclusion.py` e `core/agent/react_loop.py`
- [ ] T079 [US5] Limitar recall a trechos relevantes e registrar influência sobre o plano em `platform/memory/guidance.py`, `platform/knowledge/guidance.py` e `core/pipeline/stages/plan_evidence.py`
- [ ] T080 [US5] Expor outcome, availability e phase metrics sem zeros fabricados em `gateway/http/routes/investigations.py` e `gateway/http/routes/models.py`
- [ ] T081 [P] [US5] Escrever testes de console para outcome, produção, `unknown` e breakdown por fase em `console/tests/unit/surfaces/run-detail.test.tsx` e `console/tests/unit/surfaces/runs.test.tsx`
- [ ] T082 [US5] Atualizar run detail/list para separar término, diagnóstico, recuperação, limitações e custo por fase em `console/src/surfaces/screens/run-detail.tsx`, `console/src/surfaces/screens/runs.tsx` e `console/src/design/status.ts`
- [ ] T083 [US5] Executar `tests/synthetic/test_investigation_token_efficiency.py` e registrar comparação contra `tests/synthetic/fixtures/recurrence_baseline.json` sem aceitar regressão de evidência

**Checkpoint**: eficiência é mensurável e não altera a qualidade do caminho de problema novo.

---

## Phase 8: User Story 6 — Operar a biblioteca de postmortems (Priority: P2)

**Goal**: buscar, revisar, publicar, superseder, arquivar e avaliar postmortems com tenant,
secret guard, histórico imutável e UI acessível.

**Independent Test**: criar/revisar/publicar um postmortem, localizar pela URL/filtros, fornecer
feedback, superseder/arquivar e comprovar que somente a revisão publicada vigente aparece no
recall e que usuários sem `knowledge.curate` não publicam.

### Tests para User Story 6 — escrever e confirmar falha primeiro

- [ ] T084 [P] [US6] Cobrir state machine, retomada de draft por outro operador com autoria/ETag, revisão concorrente, snapshot imutável quando publicação ocorre durante recall, publicação humana, supersessão, archive e feedback em `tests/unit/platform/knowledge/postmortems/test_service.py`
- [ ] T085 [P] [US6] Estender o contrato de persistence para transições, idempotência, tenant e histórico append-only em `tests/contract/persistence/test_postmortem_store.py`
- [ ] T086 [P] [US6] Cobrir `knowledge.read/write/curate`, isolamento, secret guard e audit rows para toda transição em `tests/security/test_postmortem_permissions.py` e `tests/unit/platform/identity/test_permissions.py`
- [ ] T087 [P] [US6] Escrever testes de tab/URL/filtros/lista com todos os campos de FR-030/editor/history/feedback e benchmarks bem-sucedidos com 10.000 postmortems, página máxima 50, p95 API 500 ms e p95 console 1 s em `console/tests/unit/surfaces/knowledge.test.tsx`, `console/tests/unit/surfaces/postmortems.test.tsx`, `tests/benchmarks/test_postmortem_listing.py` e `console/tests/e2e/postmortem-list-performance.spec.ts`

### Implementação para User Story 6

- [ ] T088 [US6] Implementar revisão, publish, supersede, archive, feedback, diff legível e eventos auditáveis em `platform/knowledge/postmortems/service.py`, `platform/knowledge/postmortems/models.py` e `platform/identity/audit/recorder.py`
- [ ] T089 [US6] Persistir transições idempotentes, autoria de retomada, ETag/version, snapshot da revisão consultada e feedback append-only em `platform/persistence/fakes/postmortem_store.py` e `platform/persistence/postgres/repositories/postmortem_store.py`
- [ ] T090 [US6] Materializar somente a revisão publicada vigente no namespace `postmortems` e invalidar chunks antigos em `platform/knowledge/postmortems/search.py`, `platform/knowledge/base/ingestion.py` e `platform/persistence/postgres/repositories/knowledge_store.py`
- [ ] T091 [US6] Fazer feedback incorrect/outdated reduzir confiança e abrir revisão sem apagar associações históricas em `platform/knowledge/postmortems/matching.py` e `platform/knowledge/postmortems/service.py`
- [ ] T092 [US6] Adicionar `KNOWLEDGE_CURATE`, atribuição explícita de role e rotas read/write/curate em `platform/identity/permissions.py`, `gateway/http/security/console_routes.py` e `gateway/http/security/route_permissions.py`
- [ ] T093 [US6] Implementar list/get/patch/publish/supersede/archive/feedback/metrics, todos os campos de FR-030, página default/máxima de 50 e budgets nomeados/reexportados conforme o contrato em `gateway/http/routes/knowledge.py`, `platform/knowledge/postmortems/service.py`, `config/constants/knowledge.py` e `config/constants/__init__.py`
- [ ] T094 [US6] Atualizar OpenAPI/fixtures e regenerar o cliente em `fixtures/contract/openapi.json` e `console/src/api/schema.ts`
- [ ] T095 [US6] Criar courier routes para revisão, publicação, invalidação e feedback em `console/src/app/api/postmortem/route.ts`
- [ ] T096 [US6] Adicionar tab `postmortem`, filtros em URL, lista e detalhe em `console/src/surfaces/screens/knowledge.tsx` e `console/src/surfaces/screens/postmortems.tsx`
- [ ] T097 [US6] Implementar editor, history/diff, publish/supersede/archive e feedback em `console/src/surfaces/screens/postmortem-editor.tsx` e `console/src/surfaces/screens/postmortem-detail.tsx`
- [ ] T098 [P] [US6] Completar i18n pt-BR/en e navegação por teclado em `console/src/i18n/pt-BR.ts`, `console/src/i18n/en.ts`, `console/src/i18n/messages.ts` e `console/src/shell/routes.ts`
- [ ] T099 [US6] Criar E2E do lifecycle editorial, retomada por outro operador, publicação concorrente ao recall, permissão e filtros persistentes em `console/tests/e2e/postmortem-library.acceptance.spec.ts`

**Checkpoint**: biblioteca operável ponta a ponta, sem participação automática de drafts no
recall.

---

## Phase 9: User Story 7 — Provar que o aprendizado melhorou a investigação (Priority: P2)

**Goal**: isolar o valor de memória episódica, estratégia, postmortem e caminho curto, além de
mostrar uso/economia sem aceitar regressão de qualidade.

**Independent Test**: executar as células de ablação sobre o mesmo corpus/provider e comprovar
que cada mecanismo pode ser desligado isoladamente, que métricas usam baseline/período e que a
combinação só recebe veredicto de melhoria quando precisão e evidência não regredirem.

### Tests para User Story 7 — escrever e confirmar falha primeiro

- [ ] T100 [P] [US7] Cobrir switches independentes `postmortems` e `recurrence_path` preservando `memory_read` e `memory_strategy` em `tests/unit/harness/ablation/test_ablation_switches.py` e `tests/unit/platform/knowledge/test_guidance_and_switches.py`
- [ ] T101 [P] [US7] Criar gate de qualidade/custo e quatro células direcionadas em `tests/synthetic/test_postmortem_recurrence_ablation.py` e `tests/unit/harness/ablation/test_ablation_runner.py`
- [ ] T102 [P] [US7] Cobrir consolidação por assinatura sem perda de episódios/runs em `tests/unit/platform/memory/test_episode_signature_view.py`
- [ ] T103 [P] [US7] Cobrir fontes, vigência, supersessão e obsolescência de estratégias em `tests/unit/platform/memory/strategy/test_policy.py` e `tests/unit/platform/memory/strategy/test_delivery_and_edits.py`
- [ ] T104 [P] [US7] Criar contrato fake/PostgreSQL para `LearningEvaluation`, coorte comparável e métricas `unknown`, mais teste de composição do job real, UoW e rota de leitura em `tests/contract/persistence/test_learning_evaluation_store.py` e `tests/contract/deployment/test_learning_evaluation_composition.py`

### Implementação para User Story 7

- [ ] T105 [US7] Adicionar os dois eixos, policies e trace keys em `tests/harness/ablation/switches.py`, `tests/harness/ablation/config.py`, `platform/knowledge/policy.py` e `config/constants/evaluation.py`
- [ ] T106 [US7] Persistir `LearningEvaluation` pelo gateway único e compor seu produtor no job `learning.evaluation` do scheduler em `platform/persistence/ports/learning_evaluation_store.py`, `platform/persistence/ports/transaction.py`, `platform/persistence/ports/__init__.py`, `platform/persistence/fakes/learning_evaluation_store.py`, `platform/persistence/fakes/gateway.py`, `platform/persistence/postgres/repositories/learning_evaluation_store.py`, `platform/persistence/postgres/gateway.py`, `platform/persistence/postgres/models.py`, `platform/persistence/migrations/versions/0027_learning_evaluations.py`, `platform/evaluation/__init__.py`, `platform/evaluation/service.py`, `gateway/http/evaluation_job.py`, `gateway/http/scheduled_work.py`, `config/constants/evaluation.py` e `config/constants/__init__.py`
- [ ] T107 [US7] Implementar `EpisodeSignatureView` reconstruível e links completos em `platform/memory/models.py`, `platform/memory/retrieval.py` e `platform/memory/service.py`
- [ ] T108 [US7] Adicionar fontes/vigência/obsolescência às estratégias e filtrar stale guidance em `platform/memory/strategy/models.py`, `platform/memory/strategy/policy.py`, `platform/memory/strategy/invalidation.py` e `platform/memory/guidance.py`
- [ ] T109 [US7] Calcular e persistir consulta/aceite/rejeição/short-path/erro, `recall@3` e economia somente entre coortes com cenário/corpus/runtime/provider/modelo/limites/período equivalentes em `tests/harness/ablation/report.py`, `platform/evaluation/service.py` e `platform/knowledge/postmortems/service.py`
- [ ] T110 [P] [US7] Escrever testes do painel de métricas e ausência `unknown` em `console/tests/unit/surfaces/postmortems.test.tsx`
- [ ] T111 [US7] Exibir uso, economia, baseline e período no detalhe de postmortem em `console/src/surfaces/screens/postmortem-detail.tsx`
- [ ] T112 [US7] Fazer regressões de causa/evidência/material-change falharem no corpus em `tests/synthetic/test_postmortem_recurrence_ablation.py` e `tests/harness/scoring/axes/evidence.py`

**Checkpoint**: qualquer alegação de aprendizagem possui benchmark reproduzível e ablação.

---

## Phase 10: User Story 8 — Degradar honestamente quando conhecimento ou integrações faltam (Priority: P3)

**Goal**: mostrar limitações reais, evitar capabilities impossíveis e representar métricas
ausentes como desconhecidas sem inferir saúde/causa pela ausência de fonte.

**Independent Test**: executar sem knowledge documents, node executor, change source e token
usage; nenhuma capability impossível é oferecida, cada ausência aparece como limitação e o
resultado permanece inconclusivo/hipótese quando a evidência necessária não existe.

### Tests para User Story 8 — escrever e confirmar falha primeiro

- [ ] T113 [P] [US8] Cobrir knowledge vazio, integração ausente e token usage desconhecido em `tests/unit/gateway/runtime/test_react_investigation_runner.py` e `tests/unit/platform/reporting/test_models.py`
- [ ] T114 [P] [US8] Cobrir contratos HTTP de limitations/availability/unknown sem zero fabricado em `tests/unit/gateway/http/test_investigations.py`
- [ ] T115 [P] [US8] Cobrir estados vazios/degradados e linguagem honesta no console em `console/tests/unit/surfaces/run-detail.test.tsx` e `console/tests/unit/surfaces/knowledge.test.tsx`

### Implementação para User Story 8

- [ ] T116 [US8] Propagar ausência de knowledge/integration/token accounting como limitation tipada em `core/agent/degradation.py`, `gateway/runtime/investigator.py` e `platform/runs/recording.py`
- [ ] T117 [US8] Impedir conclusão validada baseada em fonte ausente e separar hypotheses/findings em `core/agent/conclusion.py` e `platform/reporting/builder.py`
- [ ] T118 [US8] Expor limitations, availability verificada e usage desconhecido em `gateway/http/routes/investigations.py` e `gateway/http/routes/knowledge.py`
- [ ] T119 [US8] Renderizar conhecimento vazio, capability indisponível e custo desconhecido em `console/src/surfaces/screens/run-detail.tsx` e `console/src/surfaces/screens/knowledge.tsx`
- [ ] T120 [US8] Criar cenário sintético sem fontes opcionais e assert de degradação honesta em `tests/synthetic/test_missing_sources_degradation.py`

**Checkpoint**: configuração ausente nunca vira evidência negativa nem sucesso falso.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: provar composição real, segurança, reversibilidade e objetivos quantitativos de
todas as histórias.

- [ ] T121 [P] Adicionar checks de arquitetura para único lifecycle/orchestration e serving composition roots em `tests/architecture/test_one_incident_lifecycle.py`, `tests/architecture/test_one_investigation_orchestration.py` e `tests/contract/deployment/test_investigation_runtime_agreement.py`
- [ ] T122 [P] Adicionar testes cross-tenant, secret masking, retenção e ausência de credenciais em embeddings/trace em `tests/security/test_postmortem_tenant_and_secrets.py` e `tests/unit/platform/sandbox/test_trace_and_egress_audit.py`
- [ ] T123 [P] Executar a matriz de upgrade/downgrade das migrations 0023–0027 e registrar casos de recusa segura em `tests/contract/persistence/test_feature_v9_migration_chain.py`
- [ ] T124 Regenerar catálogo OpenAPI/cliente/documentação e eliminar drift em `fixtures/contract/openapi.json`, `console/src/api/schema.ts`, `docs/site/configuration/memory--knowledge--and-the-runtime.md` e `docs/site/capabilities/incident.md`
- [ ] T125 Executar o cenário completo de `specs_v9/000-investigacao-robusta/quickstart.md` e registrar os resultados redigidos em `specs_v9/000-investigacao-robusta/validation.md`
- [ ] T126 [P] Adicionar E2E composto e visual para desktop/viewport estreita em `console/tests/e2e/postmortem-recurrence.acceptance.spec.ts` e `console/tests/visual/screens.spec.ts`, depois registrar a revisão Orca de staging em `specs_v9/000-investigacao-robusta/validation.md`
- [ ] T127 Executar `make fast` por área, corrigir falhas nos arquivos tocados e registrar os comandos em `specs_v9/000-investigacao-robusta/validation.md`
- [ ] T128 Executar `make verify` e registrar comando/resultado em `specs_v9/000-investigacao-robusta/validation.md`
- [ ] T129 Executar `make test-postgres`, synthetic corpus, ablações e benchmark de listagem, registrando SC-001–SC-019, coortes comparáveis e deltas contra o baseline em `specs_v9/000-investigacao-robusta/validation.md`
- [ ] T130 Documentar shadow-write, feature flags locais, lease recovery, rollback e critérios de ativação em `docs/site/deployment/postmortem-rollout-and-rollback.md`
- [ ] T131 Executar o protocolo moderado de primeira utilização com pelo menos 10 operadores elegíveis, anonimizar amostra/tempo/falha/versão da interface e registrar o resultado de SC-012 em `specs_v9/000-investigacao-robusta/validation.md` conforme `specs_v9/000-investigacao-robusta/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências.
- **Foundational (Phase 2)**: depende de Setup e bloqueia todos os incrementos confiáveis.
- **US1 (Phase 3)**: depende de Foundational; é o MVP operacional.
- **US2 (Phase 4)**: depende de Foundational; usa postmortem publicado semeado pelo store e não
  depende do editor da US3/US6.
- **US3 (Phase 5)**: depende de Foundational; pode avançar em paralelo com US1 e US2.
- **US4 (Phase 6)**: depende de Foundational e de US3 — T062, T065 e T067 escrevem em
  `postmortems/test_drafts.py`, `postmortems/service.py` e `postmortem-editor.tsx`, criados na
  US3. Valida end-to-end a integridade estabelecida na fundação e deve concluir antes da
  publicação da US6.
- **US5 (Phase 7)**: depende de Foundational; integra melhor depois de US2, mas seus mecanismos
  de disponibilidade/budget podem ser implementados em paralelo.
- **US6 (Phase 8)**: depende de Foundational, US3 para drafts e US4 para publicação citável.
- **US7 (Phase 9)**: depende de US1, US2, US5 e US6 para medir os mecanismos completos.
- **US8 (Phase 10)**: seus testes de domínio podem começar depois de Foundational, mas a
  implementação e o independent test dependem de US5 e US6, cujos estados reais são propagados.
- **Polish (Phase 11)**: depende de todas as histórias incluídas no release.

### User Story Dependency Graph

```text
Setup → Foundational → {US1, US2, US3, mecanismos internos de US5}
US2 → integração de US5
US3 → US4
US3 + US4 → US6
US1 + US2 + US5 + US6 → US7
US5 + US6 → US8
US1–US8 → Polish
```

### Within Each User Story

- Tests da fase devem ser escritos e falhar antes da implementação correspondente.
- Ports/models precedem fake e PostgreSQL; ambos devem passar o mesmo contrato.
- Services precedem routes; routes precedem cliente/courier/UI.
- Background work só inicia depois do commit do estado autoritativo.
- Uma story só fecha com seu independent test e evidência do serving path.

### Parallel Opportunities

- T002 pode avançar em paralelo com T001.
- Tests marcados [P] dentro de cada fase podem ser escritos simultaneamente em arquivos
  distintos.
- Depois de T016, US1, US2, US3 e os mecanismos internos de US5 podem começar em paralelo; US4
  começa depois que US3 criou o draft builder, o serviço e o editor que ela audita.
- UI tests de uma história podem avançar enquanto o serviço/backend da mesma história é
  implementado, desde que o contrato já esteja fixado e os arquivos não conflitem.
- Tests de domínio de US8 podem iniciar cedo; T116–T120 só começam depois de US5 e US6 porque
  precisam usar os campos reais de availability, usage e knowledge lifecycle.

---

## Parallel Example: User Story 1

```text
Task T017: contrato de occurrence/decision/claim em persistence
Task T018: corrida real e lease no PostgreSQL
Task T019: migration de incidentes vivos duplicados
Task T020: regras de lifecycle/correlation
Task T021: serving path de webhook/restart
```

## Parallel Example: User Story 2

```text
Task T036: matching/search de postmortem
Task T037: ordem e comportamento do pipeline
Task T038: corpus sintético confirmado/contraditório/novo
```

## Parallel Example: User Story 6

```text
Task T084: state machine do domínio
Task T085: contrato fake/Postgres
Task T086: permissão/tenant/secret guard
Task T087: tab/editor no console
```

## Parallel Example: User Story 7

```text
Task T100: switches de ablação
Task T101: gate sintético de qualidade/custo
Task T102: visão canônica de episódios
Task T103: vigência de estratégias
Task T104: persistence de LearningEvaluation
```

---

## Implementation Strategy

### MVP First — User Story 1

1. Completar Setup e Foundational.
2. Implementar US1 em TDD até T133.
3. Parar e validar concorrência, restart, resolução e serving composition.
4. Implantar em staging com shadow-write antes de tornar o claim durável autoritativo.
5. Comparar runs/occurrences com o baseline sem habilitar ainda recall de postmortem.

### Incremental Delivery

1. **MVP**: US1 elimina explosão de investigações repetidas.
2. **Conhecimento útil**: US2 valida recorrências publicadas sem esperar UI editorial.
3. **Captura de conhecimento**: US3 cria drafts; US4 garante citações corretas.
4. **Eficiência e curadoria**: US5 reduz desperdício; US6 entrega library/lifecycle completos.
5. **Prova**: US7 mede contribuição e bloqueia regressão.
6. **Resiliência**: US8 fecha comportamento sem fontes opcionais.
7. **Release**: Polish executa migrations, segurança, E2E, visual e gates quantitativos.

### Parallel Team Strategy

Depois de Foundational:

- frente A: US1 (intake/incidents/dispatch);
- frente B: US2 (matching/pipeline/trace);
- frente C: US3 e depois US6 (postmortem API/console);
- frente D: US4/US5 (integridade/runtime efficiency);
- frente E, após mecanismos compostos: US7/US8 (evaluation/degradation).

Conflitos de arquivos exigem serialização ou ownership explícito. Os conhecidos são:

| Arquivo | Frentes que o disputam |
|---|---|
| `platform/persistence/postgres/models.py` | A (T024), D (T076), foundational (T009/T015) |
| `platform/persistence/ports/transaction.py` | foundational (T016), E (T106) |
| `platform/knowledge/postmortems/service.py` | B (T044), C (T053/T088/T091), D (T065), E (T109) |
| `gateway/http/routes/knowledge.py` | C (T054/T093), D (T066), E (T118) |
| `gateway/http/routes/investigations.py` | C (T054/T055), D (T066/T080), E (T118) |
| `console/src/surfaces/screens/run-detail.tsx` | C (T058), D (T067/T082), E (T119) |
| `console/src/surfaces/screens/incident-detail.tsx` | A (T034), C (T058) |
| `console/tests/unit/surfaces/incident-detail.test.tsx` | A (T033), C (T051) — ambos `[P]` |
| `console/src/surfaces/incident-group-list.tsx` | A (T034), C (T134) |
| `console/src/i18n/{pt-BR,en,messages}.ts` | C (T059), C tardia (T098) |
| `console/src/surfaces/screens/postmortem-editor.tsx` | C (T058/T097), D (T067) |
| `console/src/app/api/postmortem/route.ts` | C (T057), C tardia (T095) |

Nas linhas com duas frentes distintas, quem chega depois estende o arquivo existente; nunca o
recria.

---

## Notes

- Tasks [P] usam arquivos distintos ou são testes que podem ser preparados sem depender de
  implementação ainda incompleta.
- Toda constante nova pertence a `config/constants/` e é reexportada por `__init__.py`.
- SQL/Cypher fica exclusivamente em `platform/persistence/`.
- Postmortem draft nunca entra no recall; publish/supersede/archive exigem humano com
  `knowledge.curate`.
- Recall semântico acontece somente depois de evidence anchor e sempre deixa trace.
- Um task não fecha apenas porque o teste unitário passou: deve existir caminho a partir do
  composition root real ou declaração explícita de estado dormant.
- `LearningEvaluation` só fecha quando o job `learning.evaluation` estiver registrado no scheduler,
  o store estiver exposto pela UoW fake/PostgreSQL e a rota de métricas ler esses registros.
- Faça commits por task ou grupo lógico pequeno; não misture refactor sem caracterização.
