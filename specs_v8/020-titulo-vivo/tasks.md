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

## O que o lead resolveu antes do despacho (achados do analyze)

1. **O payload interno do evento de início não muda.** `RUN_STARTED` grava
   `{trigger, team_node_id}` no traço, e é o tradutor do stream público que
   constrói `{run_id}` — são dois mecanismos, não um. A exigência é que
   objetivo e rótulos **nunca vazem** para nenhum dos dois; ler R2/A4 como
   ordem para reescrever a chamada de `record_event` seria uma mudança que
   ninguém pediu e que contradiz o fato já verificado nesta própria spec.
2. **A evidência do ambiente real é do orquestrador** (T002 e T014, agora
   ambos rotulados). Entregue a consulta, não a medição.
3. **A cláusula da SC2 sobre "o próximo alerta real" é oportunista.** Nenhuma
   tarefa a possui e o orçamento do slot é de **um** run, criado pela 050 —
   forçar um alerta real não está ao alcance de ninguém aqui. O mecanismo se
   prova no teste de contrato (T003b): rótulos de alerta produzem
   "alertname on recurso". No staging, o orquestrador mede o que existe —
   `SELECT count(*), headline FROM agent_runs WHERE trigger='alert'` — e
   registra "observado" ou "nenhum alerta real na janela". A segunda resposta
   é aceitável; um verde inferido não é.
4. **Três casos de borda não têm teste novo** — objetivo só com espaços,
   objetivo longo demais, e headline provisório que permanece em
   `PARTIAL/FAILED/INTERRUPTED`. O analyze conferiu que os três já se
   comportam certo por construção (`headline.py` faz `strip` e trunca por
   fronteira de palavra; `complete_run` preserva o headline quando recebe
   `None`). Corretos por reúso não é o mesmo que protegidos por regressão:
   acrescente os três casos ao teste de contrato, ou nomeie a lacuna no
   relatório. "Não medido" não é resposta.

## Phase 0: Linha de base

- [~] T001 Rodar `make verify` na árvore intacta; guardar log fora do
      repositório; registrar exit code e contagem. Linha de base não-verde:
      parar e reportar. **Rodada, mas não válida como linha de base**: o
      job de fundo correu enquanto a primeira edição desta sessão
      (`last_completed_stages` no protocolo `RunTraceStore`) ainda estava
      pousando, então a árvore que ele mediu não era mais a intacta —
      contaminação explicada e comprovada em `evidence/baseline.md`
      (`git show f02bf942:...` confirma que porta/fake/Postgres estavam
      mutuamente consistentes no commit de partida). `make verify` completo
      rodou de novo, verde, sobre o estado final — ver T013.
- [~] T002 **(orquestrador — a worktree não alcança o cluster nem o banco)**
      Registrar o "antes" no staging, em `evidence/antes.md`:
      `SELECT count(*) FROM agent_runs WHERE headline LIKE 'investigation
      triggered by%';` e `SELECT run_id, trigger, headline FROM agent_runs
      ORDER BY started_at DESC LIMIT 5;` — os números contra os quais SC2 é
      medido. O implementer não executa esta tarefa: entrega no relatório a
      consulta exata que quer ver rodada, e nada mais. **Reatribuída ao
      orquestrador: uma worktree não alcança nem o cluster nem o banco.**
      O "antes" real já foi lido pelo orquestrador de dentro do cluster
      (704 `agent_runs`, 699 por alerta, 155 com headline vazio entre
      esses, 1/699 na forma nova, 0 no padrão `LIKE 'investigation
      triggered by%'` — esse padrão nunca é persistido, só era sintetizado
      na leitura, então vai continuar 0 antes e depois do deploy para
      sempre). Consultas corrigidas para o "depois" entregues no relatório
      final e em
      `/tmp/claude-999/-srv-workspaces-NinjaSRE/ec6dd9db-b857-442a-ad52-779c42f3a2c8/scratchpad/t014-queries.md`.

## Phase 1: Vermelho

- [x] T003 Escrever o teste de contrato novo em
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
- [x] T004 Estender `tests/contract/persistence/test_run_trace_store.py`
      (roda contra fake E Postgres): `start_run` com objective persiste a
      coluna; `last_completed_stages` devolve o último estágio por run e
      ignora runs sem nenhum. Confirmar vermelho junto com T003.

## Phase 2: Persistência

- [x] T005 `AgentRun.objective: str = ""` no port
      (`platform/persistence/ports/run_trace_store.py`) e assinatura
      `last_completed_stages(run_ids)` no protocolo `RunTraceStore`, com
      docstring dizendo a semântica "último estágio **completado**" (um run
      parado dentro de um estágio não o tem).
- [x] T006 Migração `platform/persistence/migrations/versions/
      0020_run_objective.py`: coluna `objective TEXT NOT NULL DEFAULT ''` em
      `agent_runs`; índice parcial em `trace_events (run_id, sequence DESC)
      WHERE kind='stage_completed'` **somente se** T003(f) reprovar sem ele;
      downgrade completo.
- [x] T007 Postgres store: gravar/ler `objective`; implementar
      `last_completed_stages` com `SELECT DISTINCT ON (run_id)` filtrado por
      `kind='stage_completed'`, ordenado por run e sequência decrescente,
      extraindo o nome do estágio do payload.
- [x] T008 Fake store (`platform/persistence/fakes/run_trace_store.py`):
      mesmos comportamentos, varredura em memória.

## Phase 3: Escrita do título

- [x] T009 `RunRecorder.start_run` (`platform/runs/recorder.py`): parâmetros
      `objective=""` e `alert_labels=None`; gravar
      `redacted_objective=self._redact(objective)` antes de qualquer escrita;
      sanitizar labels; computar o provisório com
      `synthesize_headline(alert_name=labels.get("alertname",""),
      resource=resource_from_labels(labels), objective=redacted_objective)` e
      gravar como `headline` no mesmo INSERT; manter o payload do evento de
      início somente com `run_id`, conforme a 010. `start_subagent_run` repassa
      somente o objetivo sanitizado que recebe. Unit em
      `tests/unit/platform/runs/test_recorder.py`, incluindo marcador secreto.
- [x] T010 `gateway/http/orchestration.py::start_investigation` repassa
      `objective` e `alert_labels` já sanitizados ao runtime e ao `start_run`.
      `platform/scheduler/executor.py` também sanitiza o objetivo do job
      agendado antes de qualquer prompt ou persistência.
      Verificar por grep que nenhum outro chamador de `start_run` produz run
      de investigação sem objetivo (seed de test-infra pode ficar vazio —
      é dado de teste).

## Phase 4: Leitura

- [x] T011 `gateway/http/routes/investigations.py`: remover
      `_fallback_objective`; `summary_of` passa a `run.headline or
      synthesize_headline(objective=run.objective)`; `InvestigationSummary`
      ganha `last_completed_stage`/`stage_index`; `list_investigations` e o
      detalhe preenchem via UMA chamada a `last_completed_stages` com todos
      os run_ids da página; `stage_index` derivado da posição em `StageName`.
      Regenerar OpenAPI e cliente TS pelos geradores.

## Phase 5: Ban transversal

- [x] T012 Estender a suíte transversal (`console/tests/e2e/bans.ts` e
      `transversal-rules.spec.ts`): nenhum título renderizado (h1,
      célula-título, aba, breadcrumb) contém "investigation triggered by" nem
      casa `/^(interactive|alert|schedule|subagent) investigation$/`. **O ban
      de hash cru já existe** — `RAW_HEX = /^[0-9a-f]{8,}$/i` em `bans.ts`,
      ligado à regra "identificador como nome" e já rodando contra estas
      mesmas superfícies em `/runs` e `/runs/{id}`. Oito ou mais dígitos é
      superconjunto de dezesseis: reutilize o detector existente em vez de
      somar um segundo mais estreito, e diga no relatório o que ele já pegava
      antes desta feature. Rodar contra o produto atual para calibrar o
      seletor de "título".

## Phase 6: Verde e evidência

- [x] T013 T003/T004 verdes; `make verify` completo; logs em `evidence/`.
      `EXIT=0` lido do log (não da notificação — três rodadas antes saíram 2
      de verdade enquanto a notificação dizia 0): 13137 passed/31 skipped na
      suíte principal, 38 passed no benchmark. Três correções reais no
      caminho (format, mypy, prettier) — ver `evidence/make-verify.md`.
- [~] T014 No fechamento do slot (orquestrador, EXECUCAO.md §4): após
      `make deploy-stg COMPONENTS=app web`, reutilizar o único run criado pela
      UI no S3 por 050; capturar a requisição POST emitida pelo modal e o GET
      com o headline vivo, SELECT das contagens de T002 inalteradas para
      linhas novas — e guardar em `evidence/staging.md`. Não criar outro run.
      O acceptance visual do Painel exibindo estes títulos é da 050, no
      mesmo slot. **Reatribuída ao orquestrador: uma worktree não alcança
      nem o cluster nem o banco.** As consultas exatas do "depois" (SC1 no
      run único, SC2 pela medida real — não pela string morta — e a
      varredura de A6/A7 na API ao vivo) estão no relatório final e em
      `/tmp/claude-999/-srv-workspaces-NinjaSRE/ec6dd9db-b857-442a-ad52-779c42f3a2c8/scratchpad/t014-queries.md`.
