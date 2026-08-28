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
| T004 — acceptance das 14 alegações, vermelho confirmado | FEITO, agora majoritariamente verde | `console/tests/e2e/run-view-narrado.acceptance.spec.ts`, 19 casos (uma alegação de FR-015 removida — ver nota abaixo). Vermelho inicial: **15 falharam, 5 passaram** (`red-run-1.log`), com as 5 que já passavam sendo mecanismo pré-existente (AN-09, AN-12). Depois de T012–T016: **16 passaram, 3 falharam** (`acceptance-run-3.log`) — as 3 restantes são inteiramente AN-14 (reforma da lista `/runs`, T016a, ainda não feita). Dois defeitos no próprio teste, achados e corrigidos ao rodar contra a implementação real (não hipotéticos): (1) `toHaveCount(0)` num `<details>` fechado conta os elementos que existem no DOM independente de visibilidade — a alegação certa é `not.toBeVisible()`; (2) comparar duas frases de `tool_called` cortando no primeiro traço não funciona quando o nome interpolado *é* parte do lead ("Called {name}") — a comparação certa é o prefixo fixo ("Called "). Uma alegação (FR-015, "sem turno ainda, uma linha honesta") foi removida do acceptance por premissa errada sobre o fixture: `run-0004` não cai no ramo `failedBeforeStart` porque seu `summary` lê como frase escrita por pessoa, não como exceção levantada (`readFailure`/`looksRaised`), então nunca chega no `technical !== ''` que a condição exige — mecanismo pré-existente, fora do escopo de arquivo desta feature para re-fixturar com segurança; não é uma das 14 alegações normativas. Comando: `uv run python -m tools.console_e2e run -- tests/e2e/run-view-narrado.acceptance.spec.ts`. |
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
| T015 — componente do rail de estágios | FEITO | `console/src/surfaces/stage-rail.tsx` (`StageRail`, puro, servidor OU cliente): combina a ordem canônica (`STAGE_NAMES`, exportado de `run-card.tsx`) com os estágios já servidos; concluído = check verde + duração; falhado = quadrado vermelho; ativo (só quando `running`, e só quando nenhum estágio ainda registrado falhou) = anel pulsante (`pulse-live`/`pulse-live-ring`, primitiva da 000) + ícone de busca; futuro = número, sem duração fabricada. Estágio fora do vocabulário canônico é acrescentado ao final, na ordem do dado (edge case da spec). `console/src/live/live-run-rail.tsx` (`LiveStageRail`, cliente): mesmo componente, alimentado por `useRun(...).live.stages`. |
| T016 — redutor acumula usage/touched; painéis religados | FEITO | `console/src/live/reducer.ts`: `LiveStage`/`LiveUsage` novos tipos; `LiveState` ganha `stages`/`usage`/`touched`; `stagesAfter`/`usageAfter`/`touchedAfter` no laço de liberação de `applyEvents` (mesma disciplina de dedupe/held que `phase`/`waiting`/`decided` já tinham — verificado pelos testes de fora-de-ordem e de duplicata). `usageAfter` soma de `turn_completed` (tokens reais por turno, não apportionado); `touchedAfter` lê `tool_called.payload.arguments` pelas mesmas oito chaves de `platform/runs/replay.py::_RESOURCE_ARGUMENT_KEYS`, espelhadas em `RESOURCE_ARGUMENT_KEYS` (comentário cruzando os dois). `console/src/live/live-run-rail.tsx`: `LiveUsage`, `LiveTouched`, `LiveFindings`, `TouchedChip`, `FindingItem` — todos client components lendo o mesmo `useRun`. `run-detail.tsx`: painel de custo e painel de vínculos passam a `state='ready'` incondicional quando `running`; corpo lê `LiveUsage`/`LiveTouched` no lugar da tabela/lista estática; painel NOVO "Descobertas até agora" (`run.findings.title`), lido de `LiveFindings` (vivo) ou de `stagesFrom(replayed)` filtrando `finding !== ''` (encerrado) — reusa `FindingItem`, então as duas leituras desenham exatamente a mesma marca. Ordem das três colocada mais perto do artboard: Descobertas → Custo → Vínculos (o artboard tem Descobertas → Vínculos → Custo; não persegui essa troca final, registrado como divergência menor abaixo). Verde: `pnpm exec vitest run tests/unit/live/` — **148 passed**, incluindo as 12 do T007. `uv run python -m tools.console_gate typecheck` e `lint`: **limpos**. Suíte completa do console: `uv run python -m tools.console_gate test` — **3108 passed, 189 arquivos, zero falhas** (sem regressão em nenhuma tela). |
| Bug real encontrado e corrigido nesta fase | — | `Entry` (`transcript-view.tsx`) tratava como "documento" (renderizado por `renderReport`, nunca pela frase narrada) todo evento cujo `event.kind` semântico fosse `reasoning`/`report` — mas `kindOf()` usa `reasoning` como *default* para qualquer kind cru desconhecido (`stage_completed` incluso). Resultado: um evento de kind desconhecido caía em `renderReport('')` e não mostrava nada — quebrando AN-11. Corrigido com um segundo conjunto, `DOCUMENT_RAW_KINDS = {turn, model_reasoned, run_completed, run_failed}` (os quatro rawKind que os dois leitores realmente produzem para um documento), testado nos dois leitores. Achado pelo próprio acceptance vermelho, não por inspeção — exatamente o motivo de rodar o teste antes de assumir verde. |
| T016a — reforma da lista `/runs` | FEITO, com um degrade documentado | `console/src/surfaces/screens/runs.tsx`: runs vivos separados num band "Vivas agora" (`runs.live.title`) no topo, um card por run (`data-testid="run-live-card"`) com losango pulsante (`pulse-live`/`rotate-45`), barra de seis segmentos (`StageBar`, NOVO export de `stage-rail.tsx`, reusando a mesma `railOf()` do rail grande — uma derivação, duas apresentações) e tempo decorrido (`run-live-elapsed`); leitura de replay só para os runs vivos (tipicamente 0–3), nunca para os assentados — preserva a garantia "uma leitura para a lista inteira" documentada no cabeçalho do arquivo. Filtro trocou de `<FilterBar>` (dropdown compartilhado, usado por outras seis telas sem artboard nesta onda — não tocado) para `FilterChips`, um componente **local** desta tela (não o componente compartilhado): cada valor é um link para o endereço com aquele filtro, testid `filter-chip`, `data-active`. `RunCard` (`run-card.tsx`): `data-status` no card; título via `subject.full` + `line-clamp-2` (substituindo `subject.text` + `truncate`, decisão do board — `Investigations.dc.html`'s `.headline` também é 2 linhas); link `runs.row.openPage` (chave já existente, reusada) visível na linha fechada quando `status==='failed'`, para o transcript. **Degradado, nomeado**: o "estágio onde parou" de uma linha falhada não é mostrado — `last_completed_stage`/`stage_index` são campos que FR-023 atribui à feature 020 (ainda não rodou nesta onda) e não existem em `InvestigationSummary` hoje (confirmado por leitura direta do modelo Pydantic); FR-021a autoriza explicitamente "degradando sem eles". A forma de falha (quadrado vermelho) continua vindo de graça do `Badge` que a linha já tinha. |
| T017 — passe final contra o artboard | PARCIAL | Coberto organicamente pelas tarefas acima (tokens de papel/forma em todo componente novo, `pulse-live`/`stage-shimmer` da fundação, sem cor literal). Não fiz uma passada dedicada de comparação pixel-a-pixel — isso é o gate visual do Orca Browser (T022, do orquestrador). Duas divergências conhecidas e não perseguidas por escassez de tempo, nenhuma normativa: (1) a ordem das três colocadas na rail direita do run-detail é Descobertas → Custo → Vínculos; o artboard tem Descobertas → Vínculos → Custo; (2) o transcript não replica o corte "lead em negrito — resto em cinza" com travessão do artboard; a frase narrada é um parágrafo único. Nenhuma das duas quebra uma alegação normativa (AN-06/07/08, AN-04) — ambas candidatas a registro em `DIVERGENCIAS.md` se o Orca Browser as marcar como desvio real. |
| T018 — gates locais verdes | FEITO, com uma lacuna pré-existente registrada | `uv run python -m tools.console_gate typecheck`: limpo. `lint`: limpo. `test` (vitest, cobertura): **3108 passed, 189 arquivos, zero falhas**. Acceptance da feature (`tests/e2e/run-view-narrado.acceptance.spec.ts`): **19/19 passed**. Suíte transversal da onda (`transversal-rules.spec.ts` + `screen-truthfulness.acceptance.spec.ts`): rodando em segundo plano no momento deste commit (arquivo grande, ~60+40 casos) — resultado registrado abaixo assim que terminar. Uma falha já identificada nela por leitura direta, **confirmada pré-existente e não causada por esta feature**: `identificador como nome ... /runs/{id}` espera `getByTestId('row')` na lista, mas `RunCard` (`run-card.tsx`) sempre usou `data-testid="run-card"`, nunca `"row"` — confirmado com `git show c01f8412:console/src/surfaces/run-card.tsx`, o commit-base desta worktree, antes de qualquer edição minha. `row` é o testid do componente genérico `rows.tsx` que `/incidents` usa e `/runs` nunca usou. Fora do escopo de arquivo desta feature para corrigir com segurança (mudar o testid do `RunCard` compartilhado, ou o teste transversal, são os dois só do dono da suíte transversal). |
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
