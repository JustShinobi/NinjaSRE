# Feature Specification: Título vivo — o run chama-se pelo assunto desde o primeiro evento

**Feature Branch**: `feat/v8-020-titulo-vivo`

**Created**: 2026-08-27

**Status**: Draft

**Input**: Decisão 4 da onda (specs_v8/README.md): "Título é humano do
primeiro evento ao último. O objetivo digitado é o título provisório do run;
o headline da entrega (v7) o substitui ao completar; run disparado por alerta
chama-se pelo alerta e pelo recurso. Hash como título é ban transversal."

**Referência visual (DoD)**: `design/padrao-2026-08/Main.dc.html` (card de
run em voo: "Procurar anomalias no cluster Proxmox" / "RedisExporterDown em
redis · lxc/122") e `design/padrao-2026-08/RunView.dc.html` (h1 = objetivo).
Esta feature é **backend puro** — ela entrega os dados que essas telas
exibem; quem as desenha é a 030 e a 050. O DoD visual desta feature é a
resposta JSON, não o pixel.

**Viewport normativo de medição**: n/a (feature de API).

**Evidência**: auditoria de 2026-08-27 pela UI do staging (README da onda,
"Evidências de partida"): run manual com objetivo "Procure anomalias no
cluster proxmos" intitulado "interactive investigation" durante toda a
execução; runs por alerta intitulados "investigation triggered by
bc7bdbd452fae…" (64 hex).

## Fatos verificados em 2026-08-27 (não re-derivar)

Cada um foi lido do código nesta data; um implementer que encontre diferente
reporta antes de prosseguir.

1. O objetivo digitado **chega e se perde**. `gateway/http/routes/
   investigations.py:142-162` (`create_investigation`) recebe
   `body.objective` e o passa a `start_investigation`
   (`gateway/http/orchestration.py:29`), que o entrega ao investigador — mas
   `RunRecorder.start_run` (`platform/runs/recorder.py:166-215`) **não tem
   parâmetro `objective`** e a linha `agent_runs` nasce sem ele. O evento
   `RUN_STARTED` (recorder.py:210-214) publica só
   `{"trigger", "team_node_id"}`.
2. Os dois títulos-defeito nascem na mesma função. `_fallback_objective`
   (`gateway/http/routes/investigations.py:97-101`): run com `alert_id` →
   `f"investigation triggered by {run.alert_id}"`; sem →
   `f"{run.trigger} investigation"` (= "interactive investigation").
   `summary_of` (linhas 104-115) chama isso sempre que `run.headline` é vazio
   — ou seja, para **todo run vivo**, porque o headline só é gravado por
   `complete_run` (`gateway/http/orchestration.py:164-180`).
3. A síntese de título humano **já existe e não é chamada no início**.
   `platform/runs/headline.py:106-127` (`synthesize_headline`) produz
   "{alert_name} on {resource}" / "{objective}";
   `resource_from_labels` (linhas 168-179) extrai o recurso dos labels.
   `start_investigation` já recebe `alert_labels` (orchestration.py:40).
4. `AgentRun` (`platform/persistence/ports/run_trace_store.py:62-80`) tem
   `headline: str = ""` (migração `0015_run_headline.py`) e **não tem**
   `objective`.
5. Os seis estágios têm nomes canônicos: `StageName`
   (`core/state/types.py:20-28`) = `resolve_integrations`, `intake`,
   `plan_evidence`, `gather_evidence`, `diagnose`, `deliver`, nessa ordem.
   O fim de cada um vira evento `STAGE_COMPLETED` com o nome no payload
   (`platform/runs/recorder.py:382-423`), gravado **ao terminar** — um run
   parado no meio de um estágio não tem esse estágio registrado.
6. A lista que o console lê é `GET /v1/investigations`
   (`investigations.py:165-174`) → `uow.run_traces.list_runs`
   (`platform/persistence/ports/run_trace_store.py:196`), que devolve
   `AgentRun` sem nada de estágio.
7. O objetivo de um run por alerta é construído por `objective_for(incident)`
   (`platform/incidents/dispatch.py`, chamado em
   `gateway/webhooks/router.py:405,427`) — texto, não hash; o hash que
   aparece hoje vem do fato 2, não dele.

## Alegações normativas

- **A1** Um run vivo iniciado pelo fluxo que emite `POST /v1/investigations
  {"objective": "X"}` responde `headline == "X"` no próprio POST, em
  `GET /v1/investigations` e em `GET /v1/investigations/{run_id}` **enquanto
  roda**. No staging do S3, o POST é o emitido pela UI e é o único run criado
  pelo slot; o contrato também é exercitado diretamente no harness local.
- **A2** Um run vivo iniciado por alerta responde `headline ==
  synthesize_headline(alert_name=<labels["alertname"]>,
  resource=<resource_from_labels(labels)>)` — p.ex. "RedisExporterDown on
  redis" — **enquanto roda**. Nunca o `alert_id`.
- **A3** Ao completar, o headline extraído/sintetizado pela entrega (v7)
  **substitui** o provisório na mesma coluna; nenhum campo novo de leitura é
  criado para o título.
- **A4** O objetivo persiste: a linha de `agent_runs` guarda `objective`
  verbatim após a redação de guardrail; o evento `RUN_STARTED` carrega apenas
  `{"run_id"}` conforme o contrato da 010, e as rotas de leitura servem o
  objetivo já redigido para replay e detalhe do run.
- **A5** `InvestigationSummary` ganha `last_completed_stage: str` (um valor
  de `StageName` ou `""`) e `stage_index: int` (1–6, ou 0), preenchidos na
  **lista e no detalhe**, derivados do último `STAGE_COMPLETED` do run —
  em **uma** consulta para a lista inteira, nunca uma por run.
- **A6** Nenhuma resposta do gateway e nenhum título de tela casa
  `/^[0-9a-f]{16,}$/`, `"investigation triggered by"` ou
  `/^(interactive|alert|schedule|subagent) investigation$/` como headline.
  O ban vale para runs novos **e antigos** (fallback de leitura, A7).
- **A7** Run gravado antes da migração (sem `objective`, `headline` vazio):
  a leitura sintetiza — `synthesize_headline()` já devolve "Investigation
  with no declared subject" — e **nunca** consulta `alert_id` para compor
  título. `_fallback_objective` deixa de existir.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - O run que eu iniciei chama-se pelo que eu pedi (Priority: P1)

Um operador digita "Procurar anomalias no cluster Proxmox" e inicia. A lista
de investigações, o painel e o detalhe mostram esse texto como nome do run
imediatamente — não "interactive investigation", não depois de completar.

**Why this priority**: é a evidência de partida da onda; o defeito é visível
em toda tela que liste runs, o dia inteiro.

**Independent Test**: `curl -X POST .../v1/investigations -d '{"objective":
"Procurar anomalias no cluster Proxmox"}'` seguido de `curl
.../v1/investigations` antes do run terminar.

**Acceptance Scenarios**:

1. **Given** o gateway do staging e o único run criado pela UI no S3,
   **When** o modal emite esse POST com o objetivo, **Then** a resposta do
   POST já traz `headline` igual ao objetivo, e a lista traz o mesmo enquanto
   `status == "running"`; nenhum segundo run é criado para esta verificação.
2. **Given** o mesmo run completado, **When** a lista é relida, **Then**
   `headline` é a sentença da entrega (extraída ou sintetizada pela v7) e
   `report` continua o documento integral.

### User Story 2 - O run de alerta chama-se pelo alerta (Priority: P1)

Um alerta RedisExporterDown com labels `{alertname, instance}` dispara um
run. A lista mostra "RedisExporterDown on <instance>" desde o início.

**Independent Test**: entregar um alerta sintético pelo caminho do webhook em
ambiente de teste (contrato), e no staging observar o próximo alerta real.

**Acceptance Scenarios**:

1. **Given** um alerta com `alertname` e um label de recurso, **When** o run
   nasce, **Then** `headline == "<alertname> on <recurso>"` e `alert_id` não
   aparece em nenhum campo de título.
2. **Given** um alerta sem label de recurso, **Then**
   `headline == "<alertname>"`.

### User Story 3 - A lista sabe em que estágio cada run vivo está (Priority: P1)

O board desenha a barra de 6 segmentos por run em voo. A lista responde, por
run, qual foi o último estágio completado.

**Acceptance Scenarios**:

1. **Given** um run que completou `plan_evidence`, **When** a lista é lida,
   **Then** esse run traz `last_completed_stage == "plan_evidence"` e
   `stage_index == 3`.
2. **Given** um run recém-criado sem estágio completado, **Then**
   `last_completed_stage == ""` e `stage_index == 0`.
3. **Given** 50 runs na lista, **Then** a leitura de estágios é uma consulta
   (provado por teste de contrato que conta queries, no padrão de
   `tests/contract/persistence/`).

### User Story 4 - Runs antigos não regridem para hash (Priority: P2)

**Acceptance Scenarios**:

1. **Given** uma linha de `agent_runs` anterior à migração, com `headline`
   vazio e `alert_id` preenchido, **When** a lista é lida, **Then** o
   headline servido é a síntese sem assunto — nunca contém o `alert_id`.

### Edge Cases

- Objetivo só com espaços → tratado como vazio; headline provisório cai na
  cadeia de síntese (A7).
- Objetivo acima de `MAX_HEADLINE_LENGTH` → o **objetivo** persiste inteiro;
  o headline provisório é `normalize_headline(objetivo)` (corte em fronteira
  de palavra, já implementado).
- Objetivo com segredo → passa pela mesma redação de guardrail que `summary`
  e `headline` já passam em `complete_run` (recorder.py:263-271); o
  `start_run` aplica `self._redact` ao gravar.
- Run `subagent`: `start_subagent_run` (recorder.py:217-248) já recebe
  `objective` — passa a gravá-lo na própria linha como os demais.
- `PARTIAL`/`FAILED`/`INTERRUPTED`: o provisório permanece (a entrega não
  produziu sentença melhor); `mark_interrupted` (recorder.py:302-339) não
  apaga headline.

## Requirements *(mandatory)*

### Persistência do objetivo

- **R1** `AgentRun` ganha `objective: str = ""`
  (`platform/persistence/ports/run_trace_store.py:62`), com coluna nova em
  `agent_runs` via migração alembic
  `platform/persistence/migrations/versions/0020_run_objective.py`
  (precedente: `0015_run_headline.py`), default `''`, reversível, sem
  reescrever linhas existentes.
- **R2** `RunRecorder.start_run` ganha `objective: str = ""` e
  `alert_labels: Mapping[str, str] | None = None`; grava
  `redacted_objective = self._redact(objective)` antes de qualquer
  persistência, grava `objective=redacted_objective` na linha, grava
  `headline=synthesize_headline(alert_name=labels.get("alertname",""),
  resource=resource_from_labels(labels), objective=redacted_objective)` como
  provisório **no mesmo INSERT**. O evento `RUN_STARTED` mantém o payload
  somente com `run_id`, conforme o contrato da 010; o objetivo redigido é
  servido pelas rotas de leitura. `alert_labels` também passa pela
  sanitização antes de formar `alert_name` ou `resource`; o valor cru nunca
  chega ao headline, prompt, trace, API ou relatório. Fake
  (`platform/persistence/fakes/run_trace_store.py:30`) e Postgres implementam
  igual — os testes de contrato de
  `tests/contract/persistence/test_run_trace_store.py` cobrem os dois.
- **R3** `gateway/http/orchestration.py::start_investigation` sanitiza
  `objective` e `alert_labels` antes de construir o pedido do runtime e de
  repassá-los ao `start_run`; o recorder repete a defesa antes do writer.
  Nenhum outro chamador de `start_run` (scheduler:
  `platform/scheduler/executor.py`; seed: `test-infra/backup/seed.py`) fica
  para trás — o parâmetro tem default e o scheduler também sanitiza o objetivo
  do job. O valor cru não entra no prompt, trace, evento, API ou relatório.

### Leitura

- **R4** `_fallback_objective` (`investigations.py:97-101`) é removida.
  `summary_of` serve `headline = run.headline or
  synthesize_headline(objective=run.objective)` — sem acesso a `alert_id`.
- **R5** `InvestigationSummary` (`investigations.py:38`) ganha
  `last_completed_stage: str = ""` e `stage_index: int = 0` na listagem e no
  resumo do detalhe. `RunTraceStore`
  ganha `last_completed_stages(run_ids: Sequence[str]) -> Mapping[str, str]`
  (Postgres: um `SELECT DISTINCT ON (run_id)` sobre `trace_events` filtrado
  por `kind = 'stage_completed'` ordenado por sequência decrescente; fake:
  varredura em memória). `list_investigations` e o resumo do detalhe preenchem
  os dois campos; `stage_index` deriva da posição em `StageName` (1-based).
  Esta feature é dona apenas desses campos sumários; a lista detalhada de
  estágios (`stages[]`, duração e finding) pertence à 030 e não deve ser
  duplicada aqui.
- **R6** OpenAPI (`fixtures/contract/openapi.json`) e o cliente TS gerado
  (`console/src/api/schema.ts`) são **regenerados** — nunca editados — e o
  gate de desvio prova.

### Ban transversal

- **R7** A suíte transversal do console ganha os padrões proibidos para
  qualquer título renderizado (h1, célula-título de lista, aba, breadcrumb):
  `/^[0-9a-f]{16,}$/`, `investigation triggered by`,
  `/^(interactive|alert|schedule|subagent) investigation$/`. Localizar a
  transversal existente em `console/tests/e2e/` (a v7 a estendeu; o arquivo
  é achável por `rg -l "transversal" console/tests/e2e`) e estender no
  mesmo arquivo. **Esta é a única escrita desta feature sob `console/`** e
  é teste, não tela — o slot S3 não disputa arquivos com a 050.

## Success Criteria *(mandatory)*

- **SC1** No staging pós-deploy: reutilizar o único run criado pela UI no S3,
  cujo POST leva objetivo "X" → `GET /v1/investigations` com
  `status=="running"` traz `headline=="X"`, `last_completed_stage` avançando
  pelos seis valores de `StageName`, e a linha de `agent_runs` (leitura direta
  no banco) traz `objective=='X'`.
- **SC2** No staging: o run vivo de um alerta real traz headline
  "<alertname> on <recurso>"; `SELECT count(*) FROM agent_runs WHERE
  headline LIKE 'investigation triggered by%'` continua contando **só** as
  linhas anteriores ao deploy (nenhuma nova), e nenhuma resposta da API
  serve esse texto (A6/A7 cobrem a leitura das antigas).
- **SC3** Contrato: o teste de contagem de queries prova lista de 50 runs
  com estágios em ≤ 2 consultas (runs + estágios).
- **SC4** Transversal verde com os bans novos; acceptance da feature
  registrado vermelho antes da implementação e verde no fim.
