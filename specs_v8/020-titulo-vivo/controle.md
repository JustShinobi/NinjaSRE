# Controle — 020-titulo-vivo

Estado abaixo verificado contra o código atual do worktree
`/srv/workspaces/v8-s3-020`, a partir do commit `6158b474` (resgate do
orquestrador após teto de turno) mais o trabalho desta sessão em cima dele.
Toda linha da tabela foi lida do arquivo citado nesta verificação. Confirmei
por `grep -rn "WIRE-CUT" --include="*.py" --include="*.ts" --include="*.tsx" .`
em todo o repositório, mais de uma vez ao longo da sessão — **sempre sem
resultado** — e rodei de novo as suítes afetadas a cada vez para confirmar
por execução, não por leitura do diff.

## Tabela

| Peça | Estado | Detalhe |
|---|---|---|
| R1 — coluna `objective` no port | FEITO | `platform/persistence/ports/run_trace_store.py:82` |
| R1 — migração `0020_run_objective` | FEITO | `platform/persistence/migrations/versions/0020_run_objective.py:26-27` (`revision="0020_run_objective"`, `down_revision="0019_users_email_optional"`); aplicada com sucesso contra Postgres real (docker local, `--postgres`) em três rodadas separadas desta sessão |
| R2 — `RunRecorder.start_run` grava objetivo redigido + headline no mesmo INSERT | FEITO | `platform/runs/recorder.py:167-236`; `redacted_objective`/`sanitized_labels` computados antes de qualquer uso |
| R2 — payload do `RUN_STARTED` inalterado | FEITO (verificado, não modificado por escolha do lead) | `platform/runs/recorder.py:233-236` continua `{"trigger": trigger, RUN_METADATA_TEAM: team_node_id}` |
| R2 — `start_subagent_run` grava seu próprio objetivo | FEITO | `platform/runs/recorder.py:240+`; testado em `tests/unit/platform/runs/test_recorder.py::test_a_subagent_run_records_its_own_objective` |
| R2 — Postgres/Fake implementam igual | FEITO | Postgres: `platform/persistence/postgres/repositories/run_trace_store.py:175` (`last_completed_stages`, `DISTINCT ON`); Fake: `platform/persistence/fakes/run_trace_store.py:65` |
| R3 — `orchestration.py` sanitiza antes do runtime e do `start_run` | FEITO | `gateway/http/orchestration.py:30-47` (`_sanitized`/`_sanitized_labels`), `:86` |
| R3 — `scheduler/executor.py` sanitiza o objetivo do job | FEITO | `platform/scheduler/executor.py:56-68`, `:151` |
| R3 — grep confirma nenhum chamador de `start_run` sem objetivo além dos aceitos | FEITO (verificado) | `platform/startup/demo/seeder.py:661` e `test-infra/backup/seed.py:48` constroem `AgentRun` direto no store, sem objetivo — dado de teste/demo, aceito pelo lead |
| R4 — `_fallback_objective` removida; `summary_of` corrigida | FEITO | `gateway/http/routes/investigations.py:113-131`; função antiga não existe mais |
| R5 — `InvestigationSummary` ganha `last_completed_stage`/`stage_index` | FEITO | `gateway/http/routes/investigations.py:86-91`, `:108` (`stage_index_of`), `:135` (`stages_of`), `:146` (`with_stage`) |
| R5 — `list_investigations` e `linked_summary` preenchem em uma consulta | FEITO | `gateway/http/routes/investigations.py:153+` (detalhe), `:215+` (lista) |
| R5 (fora do plano literal, justificado) — `GET /v1/runs` também preenche | FEITO | `gateway/http/routes/runs.py:174+`; ver "Desvio do plano" abaixo |
| R6 — OpenAPI e cliente TS regenerados | FEITO | `uv run python -m tools.mockplane contract` → `fixtures/contract/openapi.json` (diff de 11 linhas: os dois campos novos + a nova docstring de `create_investigation`); `cd console && pnpm run client` → `console/src/api/schema.ts` (diff de 15 linhas, mesmo conteúdo). Nenhum dos dois foi editado à mão |
| R7 — bans transversais | FEITO | `console/tests/e2e/bans.ts` ganhou `inventedRunTitle` (6º detector, era "os cinco"); `console/tests/e2e/transversal-rules.spec.ts` ganhou o describe `título inventado`, varrendo os mesmos `NOW_LABELS` que já cobrem lista e detalhe (`/runs`, `/runs/{id}`, e todo o resto do grupo "now"); `console/tests/unit/e2e/bans.test.ts` ganhou 4 casos determinísticos. O padrão de hash (16+) **reaproveita** `RAW_HEX` (8+, já existente em `identifierAsName`, linha 81 de `bans.ts`) — não somei um segundo detector mais estreito |
| T003 — contrato A1-A7 vermelho antes, verde depois | FEITO, ressalva nomeada abaixo | `tests/contract/runs/test_live_title_contract.py`, 15 testes, verdes |
| T004 — persistência (`objective`, `last_completed_stages`) | FEITO, sem vermelho observado (nomeado abaixo) | `tests/contract/persistence/test_run_trace_store.py`, 4 testes novos, rodam contra fake **e** Postgres real |
| T009 — unit test com marcador secreto | FEITO | `tests/unit/platform/runs/test_recorder.py`: 5 testes novos (`test_the_objective_is_stored_and_becomes_the_provisional_headline`, `test_alert_labels_become_the_provisional_headline_never_the_objective`, `test_a_secret_in_the_objective_is_redacted_before_the_headline_is_derived`, `test_a_secret_in_an_alert_label_is_redacted_before_the_headline_is_derived`, `test_a_subagent_run_records_its_own_objective`); reusa o mesmo padrão `AKIA[0-9A-Z]{16}`/`AKIAIOSFODNN7EXAMPLE` do teste de payload já existente no arquivo |
| T012 — ban transversal estendido | FEITO | ver R7 acima |
| T013 — `make verify` completo, verde | FEITO | `EXIT=0` lido do log; ver seção própria abaixo para as quatro rodadas e as três correções reais que levaram até lá |

## Cortes de fio, todos os seis mecanismos de backend mais o detector novo do console

Cada um foi cortado, rodado, confirmado vermelho com a mensagem real,
restaurado, e a suíte voltou a verde antes do próximo corte. Mensagens
completas em `evidence/red.log`.

1. **Headline no início, para runs de alerta** (`recorder.py`, `headline=""`)
   — reprovou os dois testes de alerta; os de run manual continuaram verdes
   (achado real: `summary_of`'s fallback de leitura reconstrói o mesmo
   headline a partir de `objective` só no caso manual — não no de alerta,
   porque labels de alerta nunca são persistidos por si).
2. **`_fallback_objective` reintroduzida** em `summary_of` — reprovou o
   teste de linha legada, mostrando o hash no headline.
3. **Redação desligada** em `recorder.start_run` (`redacted_objective =
   objective`, sem `_redact`) — reprovou os dois testes de segredo.
4. **Campo de estágio desligado** em `linked_summary` (`return summary` sem
   `with_stage`) — reprovou só o teste que exercita o detalhe; os dois que
   exercitam a lista continuaram verdes, confirmando isolamento correto.
5. **Contagem de queries** — troquei a chamada única de `stages_of` por um
   laço de uma chamada por run em `list_investigations` — reprovou com
   `assert 50 == 1`, a forma exata de um N+1.
6. **Round-trip de `objective` no Postgres** — zerei `objective=run.objective`
   para `objective=""` em `PostgresRunTraceStore.start_run` — reprovou só a
   variante `[postgres]`; a `[fakes]` continuou verde (o fake guarda o
   dataclass inteiro, isolamento correto, não falso-negativo).
7. **`inventedRunTitle` no console** — `return null` logo no topo da função
   — reprovou os dois testes de "accuses" em `bans.test.ts`.

Depois do sétimo corte e restauração, varredura final:
`grep -rn "WIRE-CUT" --include="*.py" --include="*.ts" --include="*.tsx" .`
sem resultado.

## Método usado para "uma consulta para a lista inteira" (SC3)

O teste conta **chamadas ao método do store**
(`FakeRunTraceStore.list_runs`/`.last_completed_stages`, via
`monkeypatch.setattr` na classe), não instruções SQL brutas — não existe em
lugar nenhum deste repositório um listener `before_cursor_execute` do
SQLAlchemy nomeado como infraestrutura de contagem, então "o padrão de
tests/contract/persistence/" é convenção de fixture (`gateway`/`scope`,
parametrização fake+Postgres), não uma ferramenta de contagem de SQL já
existente. Como cada um desses métodos é, no Postgres, exatamente uma
instrução SQL sem laço, contar chamadas ao método é prova fiel — e o corte de
fio #5 acima prova que a asserção reage a um N+1 de verdade, não só a uma
mudança de contagem cosmética.

## Desvio do plano: `gateway/http/routes/runs.py` também foi tocado

`plan.md` lista só `investigations.py` na escrita. Toquei `routes/runs.py`
mesmo assim porque **o console lê `GET /v1/runs` para todas as suas telas de
lista** (`runs.tsx`, `agent.tsx`, `memory.tsx`, `incidents.tsx`,
`dashboard.tsx` — confirmado por grep em `console/src/surfaces/screens/*.tsx`
e `console/src/shell/load.ts`) e usa `POST /v1/investigations` só para criar.
Sem essa mudança, `last_completed_stage`/`stage_index` existiriam num
endpoint que nada no console chama para listar — a classe de defeito do
Artigo XIV. Achei a pista num comentário já commitado da 030
(`console/tests/e2e/run-view-narrado.acceptance.spec.ts:527`), que já
antecipava exatamente isso. A mudança é aditiva, reusa `stages_of`/`with_stage`
já escritos para `investigations.py`.

## Desvio da ordem test-first, dito sem rodeio

As Fases 2 e 3 (persistência, recorder, sanitização) foram implementadas
**antes** de T003/T004 nascerem — erro de sequenciamento meu, não uma escolha.
Consequência: não observei vermelho genuíno para T004 inteiro, nem para os
itens (a) [headline do objetivo] e (d) [redação] de T003 na primeira vez que
os escrevi — a implementação já estava pronta. Compensei com os sete cortes
de fio manuais listados acima, cada um com execução real e mensagem real, o
que a própria instrução desta tarefa aceita como prova quando o vermelho
histórico não existe ("inspection is not confirmation" — corte e rodou, não
só leu o diff).

O que **de fato** ficou vermelho na primeira escrita real de T003 (bugs no
próprio arquivo de teste, não na produção — mensagens completas em
`evidence/red.log`):
- um teste que criava o run via `POST` completo e por isso corria contra
  `UnconfiguredInvestigator`, que falha o run quase na hora — `status` virou
  `failed` no meio do teste;
- dois testes de segredo que construíam `RunRecorder(store=uow.run_traces)`
  sem `guardrails=`, então a redação nunca rodava.

Os três foram corrigidos no próprio arquivo de teste (semeando via recorder
direto como o resto do arquivo já faz; passando `guardrails=GuardrailEngine()`
explicitamente), não no código de produção — a produção já estava certa.

## make verify — quatro rodadas, três correções reais até agora

Cada `EXIT=` abaixo foi lido do próprio arquivo de log, nunca de notificação
de segundo plano — as notificações desta sessão relataram "exit code 0"
**três vezes seguidas** para rodadas que na verdade saíram 2. Se tivesse
confiado nelas, teria reportado T013 feito três vezes de forma errada.

**Rodada 1**: `format-check` (ruff) reprovou — 3 arquivos Python precisavam
de `ruff format` (`investigations.py`, `test_live_title_contract.py`,
`test_recorder.py`). Corrigido nos três arquivos nomeados, não no
repositório inteiro. `EXIT=2`.

**Rodada 2**: `format-check` passou; `typecheck` (mypy) reprovou —
`gateway/http/routes/investigations.py:143: error: Returning Any from
function declared to return "Mapping[str, str]"  [no-any-return]`, na função
nova `stages_of` (`uow: Any` faz `uow.run_traces.last_completed_stages(...)`
inferir como `Any`). Corrigido com `cast(Mapping[str, str], ...)`, mesmo
padrão de tipagem fraca que `linked_summary` já usa para `uow` nesse arquivo.
`EXIT=2`.

**Rodada 3**: `format-check`, `typecheck`, `check-imports` e os guards
Python passaram; `console-static` reprovou no `prettier --check` — dois
arquivos TypeScript que eu editei via script Python/sed
(`transversal-rules.spec.ts`, `bans.test.ts`) não seguiam o estilo Prettier
do projeto (edição por script não formata; só o toolchain formata).
Corrigido com `npx prettier --write` nos três arquivos que esta feature
tocou em `console/tests/e2e/` — confirmado depois com `prettier --check`
limpo e a suíte de `bans.test.ts` (22/22) rodando de novo sem mudança de
comportamento. `EXIT=2`.

**Rodada 4**: verde de ponta a ponta. Lido do próprio log (esperei com
`until grep -q "^EXIT=" ...; do sleep 5; done`, não da notificação de
segundo plano, que desta vez também disse 0 mas eu já não confiava nela por
princípio depois das três vezes anteriores): `EXIT=0`. Suíte principal —
`13136 passed, 31 skipped, 33 warnings in 111.05s`, zero falhas (a base
tinha 13111; a diferença de 25 é o líquido dos testes novos desta feature:
15 em `test_live_title_contract.py`, 4 em `test_run_trace_store.py`, 5 em
`test_recorder.py`, menos 1 removido). Suíte de benchmark —
`38 passed, 13167 deselected in 36.34s`. Todos os gates estáticos (ruff,
mypy, import-linter, os `check_*` de constants/protocols/deps/vendor-sdks/
raw-sql/console-boundary, vocabulário de status e de incidente,
`verify_integrations`, docs) e o `console-static`/`console-test` (prettier,
eslint, tsc, 197 arquivos/3193 testes vitest) passaram. Log completo fora do
repositório em
`/tmp/claude-999/-srv-workspaces-NinjaSRE/ec6dd9db-b857-442a-ad52-779c42f3a2c8/scratchpad/evidence/final-make-verify-4.log`.

**Rodada 5** (depois de fechar a lacuna do `GET /v1/runs` acima, mais uma
mudança): `EXIT=0` de novo, lido do log da mesma forma. Suíte principal —
`13137 passed, 31 skipped` (mais um teste que a rodada 4, o novo de
`GET /v1/runs`). Benchmark — `38 passed, 13168 deselected`. Nenhuma outra
correção foi necessária.

**T013: FEITO**, com `EXIT=0` confirmado na última rodada sobre o estado
final desta sessão.

## O que fica pendente, nomeado, não escondido

1. **T006 (índice parcial condicional)** — não criado; T003(f) passa sem ele
   contra Postgres local. Se a tabela `trace_events` do staging for grande o
   bastante para o plano de consulta divergir, é a próxima coisa a medir.
2. **T002/T014 (orquestrador)** — não são minhas; consultas exatas entregues
   no relatório final, em
   `/tmp/claude-999/-srv-workspaces-NinjaSRE/ec6dd9db-b857-442a-ad52-779c42f3a2c8/scratchpad/t014-queries.md`.
3. ~~`GET /v1/runs` sem teste de contrato próprio~~ — **fechado**: adicionei
   `TestTheListKnowsWhatStageALiveRunReached::
   test_get_v1_runs_reports_the_same_stage_the_console_actually_reads`,
   batendo em `/v1/runs` (lista) e `/v1/runs/{id}` diretamente. 16/16 verde
   em `test_live_title_contract.py`.
