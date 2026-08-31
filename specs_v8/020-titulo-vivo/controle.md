# Controle — 020-titulo-vivo

Estado abaixo verificado contra o código atual do worktree
`/srv/workspaces/v8-s3-020`, no commit `6158b474` (resgate do orquestrador
após teto de turno) mais o trabalho desta sessão em cima dele. Toda linha da
tabela foi lida do arquivo citado nesta verificação, não copiada de uma
sessão anterior. Antes de continuar depois do resgate, confirmei por `grep -rn
"WIRE-CUT"` em todo o `.py` do repositório — **nenhum resultado** — e rodei de
novo as suítes relevantes (48 testes em `tests/contract/runs/
test_live_title_contract.py` + `tests/contract/persistence/
test_run_trace_store.py` + `tests/unit/platform/runs/test_recorder.py`, e os
662 de `tests/unit/gateway/http/`) para confirmar que nenhum mecanismo ficou
desligado. Nenhum fio seguia cortado.

## Tabela

| Peça | Estado | Detalhe |
|---|---|---|
| R1 — coluna `objective` no port | FEITO | `platform/persistence/ports/run_trace_store.py:82` (`AgentRun.objective: str = ""`) |
| R1 — migração `0020_run_objective` | FEITO | `platform/persistence/migrations/versions/0020_run_objective.py:26-27` (`revision="0020_run_objective"`, `down_revision="0019_users_email_optional"`); rodei contra Postgres real via docker local (`--postgres`) e a migração aplicou limpo |
| R2 — `RunRecorder.start_run` grava objetivo redigido + headline provisório no mesmo INSERT | FEITO | `platform/runs/recorder.py:167-236`; `redacted_objective` (linha 202) e `sanitized_labels` (linha 203) computados antes de qualquer uso; `AgentRun(objective=redacted_objective, headline=headline, ...)` na linha 228 |
| R2 — payload do `RUN_STARTED` inalterado | FEITO (verificado, não modificado por escolha) | `platform/runs/recorder.py:233-236` continua `payload={"trigger": trigger, RUN_METADATA_TEAM: team_node_id}` — decisão do lead antes do despacho, não reescrevi |
| R2 — `start_subagent_run` grava seu próprio objetivo | FEITO | `platform/runs/recorder.py:240-...` repassa `objective=objective` para o `self.start_run(...)` interno |
| R2 — Postgres/Fake stores implementam igual | FEITO | Postgres: `platform/persistence/postgres/repositories/run_trace_store.py:175` (`last_completed_stages`, `DISTINCT ON`); coluna `objective` em `_to_run`/`start_run`. Fake: `platform/persistence/fakes/run_trace_store.py:65` |
| R3 — `orchestration.py` sanitiza antes do runtime e do `start_run` | FEITO | `gateway/http/orchestration.py:30-47` (`_sanitized`/`_sanitized_labels`); `:86` computa `sanitized_objective` antes de abrir a transação; usado no `InvestigationStart` e no `recorder.start_run(...)` |
| R3 — `scheduler/executor.py` sanitiza o objetivo do job | FEITO | `platform/scheduler/executor.py:56-68` (`_sanitized`); `:151` substitui `schedule` por uma cópia com o objetivo já sanitizado antes de `start_run` e de `_investigate` |
| R3 — grep confirma nenhum outro chamador de `start_run` sem objetivo | FEITO (verificado) | Únicos chamadores em produção: `orchestration.py`, `executor.py` (ambos corrigidos), `platform/startup/demo/seeder.py:661` e `test-infra/backup/seed.py:48` — os dois últimos constroem `AgentRun(...)` direto no store, sem `objective`, dado de teste/demo aceito pelo lead |
| R4 — `_fallback_objective` removida; `summary_of` corrigida | FEITO | `gateway/http/routes/investigations.py:113-131`; a função antiga não existe mais no arquivo (confirmado por leitura completa) |
| R5 — `InvestigationSummary` ganha `last_completed_stage`/`stage_index` | FEITO | `gateway/http/routes/investigations.py:86-91` (campos); `:108` (`stage_index_of`); `:135` (`stages_of`, uma consulta); `:146` (`with_stage`) |
| R5 — `list_investigations` preenche em uma consulta para a página | FEITO | `gateway/http/routes/investigations.py:213-...`; provado por `tests/contract/runs/test_live_title_contract.py::TestTheListKnowsWhatStageALiveRunReached::test_the_list_reads_a_page_of_stages_in_exactly_two_store_calls` (conta chamadas ao store, não SQL bruto — ver seção de método abaixo) |
| R5 — detalhe (`linked_summary`) também preenche | FEITO | `gateway/http/routes/investigations.py:153-...`, compartilhada por `get_investigation` e `get_run` |
| R5 (extra, fora do plano literal) — `GET /v1/runs` (lista) também preenche | FEITO | `gateway/http/routes/runs.py:174-...`; ver "Desvio do plano" abaixo — é o endpoint que o console de fato lê |
| R6 — OpenAPI e cliente TS regenerados | **NÃO INICIADO** | Nenhum dos dois foi regenerado ainda nesta sessão. Comando exato: `uv run python -m tools.mockplane contract` (escreve `fixtures/contract/openapi.json`), depois `cd console && pnpm run client` (escreve `console/src/api/schema.ts`) |
| R7 — bans transversais (hash, "investigation triggered by", `trigger investigation`) | **NÃO INICIADO** | `console/tests/e2e/bans.ts`/`transversal-rules.spec.ts` ainda não tocados por esta sessão |
| T003 — contrato A1-A7 vermelho antes, verde depois | FEITO, com uma ressalva nomeada | `tests/contract/runs/test_live_title_contract.py`, 15 testes, todos verdes. Vermelho **genuíno** observado ao escrever o arquivo para 3 asserções (ver `evidence/red.log`); as demais foram verificadas por corte de fio manual porque a implementação (fases 2-3) já estava pronta antes deste arquivo nascer — ver "Desvio da ordem test-first" abaixo |
| T004 — `start_run` com objetivo persiste; `last_completed_stages` correto | FEITO, sem vermelho observado | `tests/contract/persistence/test_run_trace_store.py` (4 testes novos), roda contra fake **e** Postgres real (docker local); não observei vermelho porque a persistência (T005-T008) já estava implementada quando escrevi este teste — nomeado, não escondido |
| T009 — unit test com marcador secreto em `test_recorder.py` | **NÃO INICIADO** | Os 12 testes existentes continuam passando (não quebrei nada), mas não escrevi o teste unitário novo que T009 pede explicitamente com marcador de segredo — pendência real, fica para o próximo commit desta mesma sessão |
| T012 — ban transversal estendido | **NÃO INICIADO** | Mesma pendência de R7 acima |
| T013 — `make verify` completo, verde, evidência salva | **NÃO INICIADO** | A linha de base (T001) saiu contaminada por uma corrida com minhas próprias edições (ver abaixo); suítes específicas rodadas isoladamente estão verdes (662 gateway/http, 48 contract+persistence+recorder); `make verify` completo desde o commit do resgate ainda não rodou |

## Método usado para "uma consulta para a lista inteira"

O teste de contagem (`test_the_list_reads_a_page_of_stages_in_exactly_two_store_calls`)
não intercepta SQL bruto — ele conta **chamadas ao método do store**
(`FakeRunTraceStore.list_runs` e `.last_completed_stages`, via
`monkeypatch.setattr` na classe) para uma página de 50 runs, e afirma
exatamente 1 chamada de cada. Como cada um desses métodos é, no Postgres,
exatamente uma instrução SQL (`SELECT` único, sem laço), contar chamadas ao
método é uma prova fiel de contagem de consultas, sem precisar de um listener
`before_cursor_execute` do SQLAlchemy — que não existe em lugar nenhum deste
repositório hoje (procurei; não é "o padrão de tests/contract/persistence/",
é convenção de fixture/estilo, não uma infra de contagem SQL nomeada).
Rodei também com um Postgres real local (`--postgres`, container docker) para
os testes de T004 e confirmei que a migração e a consulta `DISTINCT ON`
funcionam contra o banco de verdade, não só contra o fake.

## Desvio do plano: `gateway/http/routes/runs.py` também foi tocado

`plan.md` lista `gateway/http/routes/investigations.py` na escrita e não
menciona `routes/runs.py`. Toquei `routes/runs.py` mesmo assim, por uma razão
concreta e verificada, não por gosto: **o console lê `GET /v1/runs` para
todas as suas telas de lista** (`runs.tsx`, `agent.tsx`, `memory.tsx`,
`incidents.tsx`, `dashboard.tsx` — confirmado por `grep` em
`console/src/surfaces/screens/*.tsx` e `console/src/shell/load.ts`), e usa
`POST /v1/investigations` só para criar. Se eu tivesse seguido o plano ao pé
da letra, `last_completed_stage`/`stage_index` existiriam num endpoint que
nada no console chama para listar — exatamente a classe de defeito do
Artigo XIV (mecanismo sem root que serve). Achei essa pista num comentário já
commitado da 030 (`console/tests/e2e/run-view-narrado.acceptance.spec.ts:527`),
que já antecipava "`last_completed_stage`/`stage_index`) the title-vivo
feature of this same wave adds to `GET /v1/runs`". A mudança em `runs.py` é
estritamente aditiva — reusa `stages_of`/`with_stage` já escritos para
`investigations.py`, sem duplicar a lógica de consulta.

## Desvio da ordem test-first, dito sem rodeio

Fiz uma pesquisa extensa (codegraph + leitura de spec/plan/README/CONFRONTO)
antes de qualquer código, como manda o método — mas ao entrar na
implementação, escrevi e apliquei as Fases 2 e 3 inteiras (persistência,
recorder, sanitização em orchestration.py/executor.py) **antes** de escrever
T003/T004. Isso quebrou a ordem test-first para as partes que essas fases
cobrem. Não escondo: **não observei vermelho genuíno** para T004 inteiro, nem
para os itens (a) [headline do objetivo], (b) [redação de segredo] de T003 —
a implementação já estava pronta quando os testes nasceram.

Para compensar com o rigor que dava, cortei os fios à mão depois, com
verificação real de execução (não inspeção):

1. **Headline no início, para runs de alerta** — zerei `headline=""` na
   construção do `AgentRun` em `recorder.py`; os dois testes de
   `TestAnAlertTriggeredRunIsNamedByTheAlertAndTheResource` reprovaram com a
   mensagem real (`'Investigation with no declared subject' ==
   'RedisExporterDown on redis-1'`); os testes de run manual **não**
   reprovaram — achado genuíno, não defeito: para run manual,
   `summary_of`'s fallback de leitura (`synthesize_headline(objective=
   run.objective)`) já reconstrói o mesmo headline a partir do `objective`
   persistido, então a escrita no início é redundante *só* para o caso
   manual. Para alerta não é redundante: os labels do alerta nunca são
   persistidos por si, só entram na síntese no momento do `start_run` — é a
   única janela em que existem.
2. **`_fallback_objective`/`summary_of`** — reintroduzi a lógica antiga
   (`f"investigation triggered by {run.alert_id}"`) dentro de `summary_of`;
   `TestAnOldRowNeverServesTheAlertIdAsATitle` reprovou com a mensagem real
   mostrando o hash no headline; restaurado, verde de novo.
3. **Redação de segredo** — troquei `redacted_objective = self._redact(objective)`
   por `= objective` (bypass) em `recorder.py`; os dois testes de
   `TestASecretNeverReachesAnyTitleOrTheStartEvent` reprovaram mostrando o
   literal `AKIAIOSFODNN7EXAMPLE` no headline da resposta; restaurado.
4. **Campo de estágio no detalhe** — troquei o `return with_stage(...)` por
   `return summary` em `linked_summary`; o teste dos "três estágios
   completados" reprovou (`'' == 'plan_evidence'`); os outros dois da mesma
   classe (lista, e run recém-criado) continuaram verdes porque testam o
   caminho de **lista**, que é uma wiring separada — confirma que o corte
   isolou exatamente o mecanismo do detalhe, não testou nada por acidente.

Cada corte foi restaurado e a suíte voltou a ficar 100% verde antes do
próximo. **Não fiz** o corte de fio da contagem de queries (N+1) nem do
round-trip de `objective` na camada de persistência (T004) antes do resgate
— ficam nomeados como pendência de verificação, não como "já confirmado".

## Achado sobre a linha de base (T001)

O primeiro `make verify` que rodei (log espelhado em
`evidence/baseline-make-verify.log`) terminou com **1 failed, 13111 passed,
31 skipped** — `test_every_tenant_scoped_fake_satisfies_its_port[run_traces]`.
Não é defeito pré-existente: o job rodou em segundo plano enquanto eu ainda
fazia a pesquisa inicial, e minha primeira edição (adicionar
`last_completed_stages` ao protocolo `RunTraceStore`, em
`platform/persistence/ports/run_trace_store.py`) pousou no disco antes de eu
ter adicionado o método correspondente ao `FakeRunTraceStore` — pytest importa
os módulos no início da coleta, então essa corrida específica produziu essa
falha específica. Confirmei via `git show f02bf942:platform/persistence/
ports/run_trace_store.py` que a árvore no commit de partida **não** tinha
`last_completed_stages` no protocolo, então fake e Postgres estavam
mutuamente consistentes ali — a linha de base real era verde. Não recomecei
o `make verify` completo do zero (custaria minutos só de pytest, mais lint/
typecheck) porque a explicação é verificável sem isso; `T013` vai rodar o
`make verify` completo de qualquer forma antes de fechar.

## O que fica pendente, nomeado, não escondido

1. **T006 (índice parcial condicional)** — não criei o índice parcial
   `(run_id, sequence DESC) WHERE kind='stage_completed'` porque T003(f)
   passou sem ele (1 consulta de qualquer forma, sem plano de consulta ruim
   percebido contra Postgres local). Se o Postgres real do slot tiver uma
   tabela `trace_events` grande o bastante para o plano de consulta divergir,
   é a próxima coisa a medir — nomeio a condição, não afirmo que nunca vai
   precisar.
2. **T009 — teste unitário com marcador secreto** em
   `tests/unit/platform/runs/test_recorder.py` — não escrito ainda. Os testes
   existentes (12) continuam verdes, mas a cobertura nova que T009 pede
   explicitamente falta. Vou fechar antes do próximo commit.
3. **R6/T011 — regeneração de OpenAPI e cliente TS** — não rodei ainda.
   Comandos exatos: `uv run python -m tools.mockplane contract` e, dentro de
   `console/`, `pnpm run client`.
4. **R7/T012 — bans transversais** — não tocado ainda. Vou localizar o
   arquivo por `rg -l "transversal" console/tests/e2e` (já sei que é
   `bans.ts` + `transversal-rules.spec.ts`) e estender no mesmo arquivo,
   reaproveitando `RAW_HEX` existente (linha 81 de `bans.ts`), conforme a
   regra do tasks.md.
5. **T002/T014 (orquestrador)** — não são minhas; consulta exata entregue no
   relatório final.
6. **Corte de fio não feito**: contagem de queries (N+1) e round-trip de
   `objective` na persistência (T004) — implementados e cobertos por teste,
   mas não verificados por desconexão manual. Ficam como corte pendente se
   houver tempo, ou nomeados como não verificados por esse método específico.
7. **`make verify` completo** — ainda não rodou de ponta a ponta sobre o
   estado atual (pós-resgate). Vou rodar antes de reportar T013 como feito.
