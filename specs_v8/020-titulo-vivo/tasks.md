# Tasks: Título vivo — o run chama-se pelo assunto desde o primeiro evento

**Input**: Design documents from `specs_v8/020-titulo-vivo/`

**Prerequisites**: spec.md, plan.md. Slot S3 (EXECUCAO.md §1), pareada com a
050; esta feature **não** é dona dos single-write do console e não toca tela.

**Tests**: acceptance-first. O teste de contrato das alegações A1–A7 aterrissa
antes de qualquer implementação e é confirmado vermelho, com a mensagem real
de cada asserção registrada em `evidence/red.log`.

**Marcação**: `[x]` feita; `[ ]` pendente; `[~]` encerrada sem execução, com a
razão na própria linha. Um `[~]` nunca é um `[x]` envergonhado.

## Regras que valem para toda tarefa deste arquivo

1. **Nada de identificador de planejamento em arquivo committed** — nem
   número de requisito, nem de feature, nem caminho de specs_v8. A substância
   vai no código e no teste; a referência fica aqui.
2. **Nenhuma tela é tocada.** A única escrita sob `console/` é o arquivo
   transversal de testes (T012). Um diff que toque surface/tsx devolve a
   tarefa.
3. **Arquivo gerado é regenerado, nunca editado** — OpenAPI e cliente TS
   saem dos geradores.
4. **`git checkout`/`stash`/`restore` proibidos na árvore compartilhada**
   (lição registrada da v6); backup em scratchpad quando precisar comparar.
5. **Gate não é afrouxado para a mudança passar.**

---

## Phase 0: Linha de base

- [ ] T001 Rodar `make verify` na árvore intacta; guardar log fora do
      repositório; registrar exit code e contagem. Linha de base não-verde:
      parar e reportar.
- [ ] T002 Registrar o "antes" no staging, em `evidence/antes.md`:
      `SELECT count(*) FROM agent_runs WHERE headline LIKE 'investigation
      triggered by%';` e `SELECT run_id, trigger, headline FROM agent_runs
      ORDER BY started_at DESC LIMIT 5;` — os números contra os quais SC2 é
      medido.

## Phase 1: Vermelho

- [ ] T003 Escrever o teste de contrato novo em
  `tests/contract/runs/test_live_title_contract.py`: (a) run criado com
  objetivo responde headline==objetivo enquanto running; (b) run com
  alert_labels responde "alertname on recurso"; (c) run antigo (linha
  semeada sem objective/headline) nunca serve alert_id como headline;
  (d) objetivo e labels com conteúdo sensível nunca aparecem no headline,
  payload `RUN_STARTED` ou resposta; (e) lista traz
  last_completed_stage/stage_index; (f) lista de 50 runs
  lê estágios em ≤ 2 consultas (contador de queries no padrão de
  `tests/contract/persistence/`). Rodar; **confirmar vermelho**; salvar
  as mensagens em `evidence/red.log`.
- [ ] T004 Estender `tests/contract/persistence/test_run_trace_store.py`
      (roda contra fake E Postgres): `start_run` com objective persiste a
      coluna; `last_completed_stages` devolve o último estágio por run e
      ignora runs sem nenhum. Confirmar vermelho junto com T003.

## Phase 2: Persistência

- [ ] T005 `AgentRun.objective: str = ""` no port
      (`platform/persistence/ports/run_trace_store.py`) e assinatura
      `last_completed_stages(run_ids)` no protocolo `RunTraceStore`, com
      docstring dizendo a semântica "último estágio **completado**" (um run
      parado dentro de um estágio não o tem).
- [ ] T006 Migração `platform/persistence/migrations/versions/
      0020_run_objective.py`: coluna `objective TEXT NOT NULL DEFAULT ''` em
      `agent_runs`; índice parcial em `trace_events (run_id, sequence DESC)
      WHERE kind='stage_completed'` **somente se** T003(e) reprovar sem ele;
      downgrade completo.
- [ ] T007 Postgres store: gravar/ler `objective`; implementar
      `last_completed_stages` com `SELECT DISTINCT ON (run_id)` filtrado por
      `kind='stage_completed'`, ordenado por run e sequência decrescente,
      extraindo o nome do estágio do payload.
- [ ] T008 Fake store (`platform/persistence/fakes/run_trace_store.py`):
      mesmos comportamentos, varredura em memória.

## Phase 3: Escrita do título

- [ ] T009 `RunRecorder.start_run` (`platform/runs/recorder.py`): parâmetros
      `objective=""` e `alert_labels=None`; gravar
      `redacted_objective=self._redact(objective)` antes de qualquer escrita;
      sanitizar labels; computar o provisório com
      `synthesize_headline(alert_name=labels.get("alertname",""),
      resource=resource_from_labels(labels), objective=redacted_objective)` e
      gravar como `headline` no mesmo INSERT; manter o payload do evento de
      início somente com `run_id`, conforme a 010. `start_subagent_run` repassa
      somente o objetivo sanitizado que recebe. Unit em
      `tests/unit/platform/runs/test_recorder.py`, incluindo marcador secreto.
- [ ] T010 `gateway/http/orchestration.py::start_investigation` repassa
      `objective` e `alert_labels` já sanitizados ao runtime e ao `start_run`.
      `platform/scheduler/executor.py` também sanitiza o objetivo do job
      agendado antes de qualquer prompt ou persistência.
      Verificar por grep que nenhum outro chamador de `start_run` produz run
      de investigação sem objetivo (seed de test-infra pode ficar vazio —
      é dado de teste).

## Phase 4: Leitura

- [ ] T011 `gateway/http/routes/investigations.py`: remover
      `_fallback_objective`; `summary_of` passa a `run.headline or
      synthesize_headline(objective=run.objective)`; `InvestigationSummary`
      ganha `last_completed_stage`/`stage_index`; `list_investigations` e o
      detalhe preenchem via UMA chamada a `last_completed_stages` com todos
      os run_ids da página; `stage_index` derivado da posição em `StageName`.
      Regenerar OpenAPI e cliente TS pelos geradores.

## Phase 5: Ban transversal

- [ ] T012 Localizar a suíte transversal (`rg -l "transversal"
      console/tests/e2e` ou o nome que a v7 usou) e estender: nenhum título
      renderizado (h1, célula-título, aba, breadcrumb) casa
      `/^[0-9a-f]{16,}$/`, contém "investigation triggered by", ou casa
      `/^(interactive|alert|schedule|subagent) investigation$/`. Rodar
      contra o produto atual para calibrar o seletor de "título".

## Phase 6: Verde e evidência

- [ ] T013 T003/T004 verdes; `make verify` completo; logs em `evidence/`.
- [ ] T014 No fechamento do slot (orquestrador, EXECUCAO.md §4): após
      `make deploy-stg COMPONENTS=app web`, reutilizar o único run criado pela
      UI no S3 por 050; capturar a requisição POST emitida pelo modal e o GET
      com o headline vivo, SELECT das contagens de T002 inalteradas para
      linhas novas — e guardar em `evidence/staging.md`. Não criar outro run.
      O acceptance visual do Painel exibindo estes títulos é da 050, no
      mesmo slot.
