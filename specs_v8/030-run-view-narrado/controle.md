# Controle — Run view narrado

Estado abaixo verificado contra o código nesta árvore (worktree
`wt/v8-030-run-view-narrado`), incrementalmente, a cada commit. Este arquivo é
reescrito à medida que o trabalho avança; a versão final reflete o que foi de
fato aberto e rodado, não a intenção do plano.

**Commit 1** (`test(console): red acceptance and unit coverage for the
narrated run view`): a linha de base vermelha.

## Ledger — uma linha por obrigação atômica

| Peça | Estado | Detalhe |
|---|---|---|
| T001 — `make verify` na árvore intacta | FEITO (herdado, não remedido) | Pinado pelo despacho: exit 2, 12972 passed, 9 failed (todos o mesmo `test_transport_equivalence.py` parametrizado, rede real), 39 skipped. Não roda de novo aqui — fora do escopo de arquivo desta feature. |
| T002 — contagem da suíte sintética ("antes") | NÃO INICIADO | Pendente; registrar antes de fechar o slot. |
| T003 — captura "antes" no staging via Orca | **[~]** — do orquestrador | A worktree não alcança staging nem o Orca Browser. |
| T004 — acceptance das 14 alegações, vermelho confirmado | FEITO | `console/tests/e2e/run-view-narrado.acceptance.spec.ts`. Comando: `uv run python -m tools.console_e2e run -- tests/e2e/run-view-narrado.acceptance.spec.ts`. Resultado real: **15 falharam, 5 passaram** (rodada após o ajuste dos testes fracos de AN-06/08 — a primeira rodada, antes do ajuste, foi 14 falharam/6 passaram). As 5 que já passavam antes de qualquer implementação: as duas de AN-09 (contagem do cabeçalho — mecanismo pré-existente), as duas de AN-12 (controles de condução — `TakeoverControls`/`AddContext` já carregam `data-testid` e já não aparecem num run encerrado) e a primeira de AN-10/AN-11 tratada abaixo. Ver a lista completa de falhas no log; mensagens reais citadas por bloco na seção de evidência. |
| T005 — completude da narração (unidade) | FEITO (vermelho confirmado) | `console/tests/unit/surfaces/transcript-narration.test.ts`. A suíte inteira falha ao **construir** (`TypeError: Cannot convert undefined or null to object` em `Object.keys(STREAM_KINDS)`, linha 29) porque `STREAM_KINDS` e `narrate` ainda não são exportados de `transcript.ts` — um vermelho só, representando as ~40 asserções que a suíte geraria uma vez que o export exista. Comando: `pnpm exec vitest run tests/unit/surfaces/transcript-narration.test.ts`. |
| T006 — funil único (unidade) | FEITO (vermelho confirmado) | Mesmo arquivo acima, mesma causa (import quebrado). |
| T007 — acumulação do redutor (unidade) | FEITO (vermelho confirmado) | `console/tests/unit/live/reducer-stage-usage.test.ts`. **11 de 11 falharam**, todas por `state.stages`/`state.usage`/`state.touched` serem `undefined` — campos que ainda não existem em `LiveState`. Comando: `pnpm exec vitest run tests/unit/live/reducer-stage-usage.test.ts`. |
| T008 — contrato: `stages[]` com nome/duração/finding/falha, na ordem | **FEITO (já existia, verificado) + FEITO (lacuna fechada)** | `tests/contract/runs/test_replay_contract.py::TestReplayGroupsTheRunByStage` já cobria nome/ordem/duração/finding — rodei a suíte intacta (`uv run pytest tests/contract/runs/test_replay_contract.py -q`): **9 passed** antes de eu tocar o arquivo. A única lacuna real era `failed`: nenhum teste servia um estágio que de fato falhou pela rota HTTP. Acrescentei `test_a_failed_stage_is_served_with_its_own_failure_and_the_run_stops_there`; rodei de novo: **10 passed** — verde imediato, não fabricado, porque `ReplayStageView.failed`/`replay_stage_view` já propagavam o campo corretamente, só não estava testado no nível de contrato. |
| T009 — caracterização do painel de relatório e controles | PARCIAL — coberto por suíte existente, não duplicado | `console/tests/e2e/live.spec.ts` já prova `takeover`/`add-context` visíveis num run vivo e ausentes num encerrado; suítes de relatório (`Report`, `CopyReport`) já existem. Não escrevi um teste de caracterização novo — reli o existente e vou rodá-lo de novo no fim como rede de segurança de regressão, e registro esse resultado aqui quando fizer. |
| T010 — confronto `stages[]` servido × o que o rail precisa | FEITO | Ver seção "Confronto de campos" abaixo. Resultado: **nada faltou**. |
| T011 — regenerar contrato/cliente TS se T010 acrescentou campo | **Fora do escopo** — nada a fazer | T010 não acrescentou campo nenhum; não há o que regenerar. |
| T012 — tabela de narração no vocabulário compartilhado | FEITO | `console/src/surfaces/transcript.ts`: `narrate(event, locale)`, tabela `NARRATION_LEAD` (17 chaves = `STREAM_KINDS`), `namedOrFallback()` para ausência declarada. Verde: `pnpm exec vitest run tests/unit/surfaces/transcript-narration.test.ts` — 39 passed. |
| T013 — 17 frases × 2 idiomas + rótulos do toggle + linha "sem turno" | FEITO | 17 chaves `transcript.narration.*` + `transcript.view.{narrated,raw,payload}` + `run.usage.awaiting` + `run.links.watching` + `run.findings.{title,none}` + `run.stage.{rail.title,future}`, em `en.ts` e `pt-BR.ts`. Os seis nomes de estágio (`run.stage.resolve_integrations`…`deliver`) já existiam antes desta feature — reusados, não duplicados. |
| T014 — view do transcript: frase primária, `<details>`, toggle | FEITO | `console/src/surfaces/transcript-view.tsx`: `Entry` renderiza `narrations[event.id]` (testid `event-narration`) como conteúdo primário para todo kind que não é documento (`reasoning`/`report` mantêm `renderReport(detail)` inalterado — são já prosa, não JSON); o payload entra em `<details data-testid="event-payload-disclosure" open={view==='raw'}>`, fechado por padrão em Narrado, aberto em Bruto. Toggle `data-testid="transcript-view-toggle"` com `data-view`, botões `transcript-view-narrated`/`transcript-view-raw`. `labels.ts` ganhou `narrations(locale, events)`, espelhando `eventTimes()`. Os dois pontos de montagem (`run-detail.tsx`, `live-run.tsx`) e a suíte de testes existente (`transcript.test.tsx`) foram atualizados para o novo prop. `pnpm exec vitest run` nos quatro arquivos afetados: **71 testes, 60 passed, 11 failed** — os 11 são exatamente `reducer-stage-usage.test.ts` (T007, ainda não implementado); `transcript.test.tsx` (suíte pré-existente) e `run-detail-live-transcript.test.tsx` **inalterados, verdes** — nenhuma regressão. `uv run python -m tools.console_gate typecheck`: **falha só nos mesmos 14 erros esperados** de `reducer-stage-usage.test.ts` referenciando campos que T016 ainda vai criar; zero erros em qualquer outro arquivo. |
| T015 — componente do rail de estágios | NÃO INICIADO | |
| T016 — redutor acumula usage/touched; painéis religados | NÃO INICIADO | |
| T016a — reforma da lista `/runs` | NÃO INICIADO | |
| T017 — passe final contra o artboard | NÃO INICIADO | |
| T018 — gates locais verdes | NÃO INICIADO | |
| T019 — baselines visuais novos | NÃO INICIADO | |
| T020 — `make verify` completo | **Do orquestrador** | Rodarei as suítes locais que tocar; o `make verify` completo do slot é do orquestrador no merge, por instrução do despacho. |
| T021–T023 | **[~] — do orquestrador** | Staging, Orca Browser, leitura direta do trace store. |

## Confronto de campos — T010

`GET /v1/runs/{run_id}/replay` (`gateway/http/routes/runs.py::ReplayStageView`,
construído por `platform/runs/replay.py::replay_stage_view`) já serve, por
estágio: `stage` (nome), `finding`, `duration_ms`, `prompt_tokens`,
`completion_tokens`, `llm_calls`, `failed`, `turns[]`. O que o rail do artboard
(`RunView.dc.html`, linhas 64–98) precisa desenhar por estágio: o nome (rótulo
localizado — já existe em `run.stage.*`, ver abaixo), se está concluído
(check + duração), se é o ativo (anel pulsante, sem duração numérica — ver
"O que assumi" abaixo), se é futuro (o próprio número) e se falhou (forma de
falha + duração até a falha). Todos os quatro já estão no corpo servido.
**Nada faltou.** A prova é `tests/contract/runs/test_replay_contract.py`
(9 casos pré-existentes + 1 acrescentado para `failed`, todos verdes,
comando acima).

O "ativo" não é um campo do contrato — é derivado no console: o primeiro
estágio da ordem canônica que ainda não apareceu em `stages[]`, enquanto o run
está `running`. Isso é consistente com o próprio backend: `stage_start` nunca
chega ao trace nem ao broker (`platform/runs/recording.py::emit` só grava em
`stage_end`/erro — comentário do próprio código: "a stage that stopped inside
it leaves that stage unrecorded... never claims one completed on the strength
of having been seen to start"), então não há sinal de "estágio X começou" para
o console consumir — só "estágio X terminou".

Os nomes e a ordem canônica dos seis estágios já existem no console, fora
desta feature: `console/src/surfaces/run-card.tsx` já declara `STAGE_NAMES`
(não exportado antes desta feature) e `stageLabel()`, com as seis chaves de
i18n `run.stage.*` já presentes em `en.ts`/`pt-BR.ts` desde antes. Reusado, não
duplicado.

## Fixtures alteradas, e por quê

- `fixtures/scenarios/populated/run-stream.json` (run-0003, o run vivo do
  slot): os três `stage_completed` que a própria réplica desse run já afirma
  terem acontecido (`run-replay.json` já tinha os três com os mesmos valores)
  agora também chegam pelo stream — antes, o stream pulava direto de
  `run_started` para `turn_started`, o que não descrevia nenhum evento real de
  estágio em lugar nenhum do stream. Sequências renumeradas de 0 a 11. Um
  `stage_completed` extra (`gather_evidence`, sequência 11) foi acrescentado
  para que um teste local possa observar o rail mover sem reload — o mesmo
  jeito que `live.spec.ts` já prova a contagem de eventos crescendo com
  `.poll()`.
- `fixtures/scenarios/populated/run-replay.json` (run-0004, `status=failed`):
  tinha `stages: []` — um run marcado como falhado sem nenhum estágio
  descrevendo a falha. Agora tem três: dois concluídos e o terceiro
  (`plan_evidence`) com `failed: true`, satisfazendo o requisito do dataset
  ("um com estágio falhado").

## O que assumi onde a spec calou

- **A forma de status de cada finding em "Descobertas até agora"**: um
  `ReplayedStage`/`RunCardStage` não carrega severidade — só `failed`. Assumi
  `status='failure'` (papel danger/quadrado) quando o estágio falhou e
  `status='info'` (papel info/círculo oco) para um finding de estágio normal —
  reusando o vocabulário de status já declarado em `design/status.ts`, sem
  inventar palavra nova. O artboard desenha um losango âmbar e um quadrado
  vermelho para findings de exemplo sem relação óbvia com falha de estágio —
  tratado como dado ilustrativo, não como especificação de cor por finding.
- **A duração do estágio ativo**: não fabricada. Sem `stage_start` no
  registro, não há como medir "há quanto tempo este estágio está rodando" sem
  inventar uma origem. O rail desenha o estágio ativo com o anel pulsante e o
  rótulo, sem um número de tempo decorrido.
- **T009**: interpretado como "não regredir", verificado contra a suíte já
  existente em vez de duplicado.

## Evidência

- Log completo da primeira rodada vermelha do acceptance:
  `/tmp/claude-999/-srv-workspaces-NinjaSRE/06510f59-f4a1-41e0-8b90-2554e9cacfc7/scratchpad/red-run-1.log`
- Mirror deste arquivo, fora do repositório:
  `/tmp/claude-999/-srv-workspaces-NinjaSRE/06510f59-f4a1-41e0-8b90-2554e9cacfc7/scratchpad/controle-030.md`
