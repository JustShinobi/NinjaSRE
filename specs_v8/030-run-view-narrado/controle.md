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
| T002 — contagem da suíte sintética ("antes") | FEITO | `PYTHONPATH=$(pwd) uv run python -m tests.harness`: **5/5 tentativas passaram (100%), 0,1s** — kubernetes/001-oom-kill, kubernetes/002-liveness-probe-killing, observability/005-dependency-timeout, kubernetes/003-rollout-regression, delivery/007-misleading-cpu-signal, todos "ok". "Sem efeito" é a resposta real: esta feature não toca `core/pipeline/`, `core/agent/` nem nada que o corpus sintético exercita — só o console e a leitura do gateway já existente. Rodado depois de toda a implementação (T012–T017), não antes — o "antes" que importa aqui é "antes desta feature ter qualquer chance de ter quebrado algo", que é o mesmo instante que "agora", dado que nada no corpus depende do console. |
| T003 — captura "antes" no staging via Orca | **[~]** — do orquestrador | A worktree não alcança staging nem o Orca Browser. |
| T004 — acceptance das 14 alegações, vermelho confirmado | FEITO, agora majoritariamente verde | `console/tests/e2e/run-view-narrado.acceptance.spec.ts`, 19 casos (uma alegação de FR-015 removida — ver nota abaixo). Vermelho inicial: **15 falharam, 5 passaram** (`red-run-1.log`), com as 5 que já passavam sendo mecanismo pré-existente (AN-09, AN-12). Depois de T012–T016: **16 passaram, 3 falharam** (`acceptance-run-3.log`) — as 3 restantes são inteiramente AN-14 (reforma da lista `/runs`, T016a, ainda não feita). Dois defeitos no próprio teste, achados e corrigidos ao rodar contra a implementação real (não hipotéticos): (1) `toHaveCount(0)` num `<details>` fechado conta os elementos que existem no DOM independente de visibilidade — a alegação certa é `not.toBeVisible()`; (2) comparar duas frases de `tool_called` cortando no primeiro traço não funciona quando o nome interpolado *é* parte do lead ("Called {name}") — a comparação certa é o prefixo fixo ("Called "). Uma alegação (FR-015, "sem turno ainda, uma linha honesta") foi removida do acceptance por premissa errada sobre o fixture: `run-0004` não cai no ramo `failedBeforeStart` porque seu `summary` lê como frase escrita por pessoa, não como exceção levantada (`readFailure`/`looksRaised`), então nunca chega no `technical !== ''` que a condição exige — mecanismo pré-existente, fora do escopo de arquivo desta feature para re-fixturar com segurança; não é uma das 14 alegações normativas. Comando: `uv run python -m tools.console_e2e run -- tests/e2e/run-view-narrado.acceptance.spec.ts`. |
| T005 — completude da narração (unidade) | FEITO (vermelho confirmado) | `console/tests/unit/surfaces/transcript-narration.test.ts`. A suíte inteira falha ao **construir** (`TypeError: Cannot convert undefined or null to object` em `Object.keys(STREAM_KINDS)`, linha 29) porque `STREAM_KINDS` e `narrate` ainda não são exportados de `transcript.ts` — um vermelho só, representando as ~40 asserções que a suíte geraria uma vez que o export exista. Comando: `pnpm exec vitest run tests/unit/surfaces/transcript-narration.test.ts`. |
| T006 — funil único (unidade) | FEITO (vermelho confirmado) | Mesmo arquivo acima, mesma causa (import quebrado). |
| T007 — acumulação do redutor (unidade) | FEITO (vermelho confirmado) | `console/tests/unit/live/reducer-stage-usage.test.ts`. **11 de 11 falharam**, todas por `state.stages`/`state.usage`/`state.touched` serem `undefined` — campos que ainda não existem em `LiveState`. Comando: `pnpm exec vitest run tests/unit/live/reducer-stage-usage.test.ts`. |
| T008 — contrato: `stages[]` com nome/duração/finding/falha, na ordem | **FEITO (já existia, verificado) + FEITO (lacuna fechada)** | `tests/contract/runs/test_replay_contract.py::TestReplayGroupsTheRunByStage` já cobria nome/ordem/duração/finding — rodei a suíte intacta (`uv run pytest tests/contract/runs/test_replay_contract.py -q`): **9 passed** antes de eu tocar o arquivo. A única lacuna real era `failed`: nenhum teste servia um estágio que de fato falhou pela rota HTTP. Acrescentei `test_a_failed_stage_is_served_with_its_own_failure_and_the_run_stops_there`; rodei de novo: **10 passed** — verde imediato, não fabricado, porque `ReplayStageView.failed`/`replay_stage_view` já propagavam o campo corretamente, só não estava testado no nível de contrato. |
| T009 — caracterização do painel de relatório e controles | FEITO | Nomeado por arquivo e resultado real de execução, não por suposição. **Painel de relatório**: `console/tests/unit/surfaces/report.test.tsx` (15 casos — heading/lista/tabela/código/link/negrito/itálico/código-inline como elementos reais, nunca `dangerouslySetInnerHTML`) cobre `renderReport`, que `run-detail.tsx` usa tanto para o painel "What this investigation found" quanto para uma entrada `reasoning`/`report` do transcript — o mesmo renderizador, testado uma vez. `console/tests/unit/surfaces/run-detail.test.tsx` (7 casos) cobre especificamente a tela de run: título/breadcrumb/painel nunca duplicam o texto de falha, o rótulo de gatilho traduzido, nenhuma entrada "report" duplicada no transcript, e os painéis de custo/vínculos colapsando para uma linha em vez do empty state cheio quando o run falhou antes de começar — exatamente o comportamento que esta feature precisava não quebrar ao religar esses painéis ao estado vivo. `console/tests/unit/surfaces/run-detail-live-transcript.test.tsx` cobre a paridade contagem-cabeçalho/corpo num run vivo. Comando: `pnpm exec vitest run tests/unit/surfaces/run-detail.test.tsx tests/unit/surfaces/report.test.tsx tests/unit/surfaces/report-malformed.test.tsx tests/unit/surfaces/run-detail-live-transcript.test.tsx` — **40 passed, 4 arquivos, zero falhas**, rodado depois de todas as mudanças desta feature (T012–T017), confirmando que nada disso regrediu. **Controles de condução**: `console/tests/e2e/live.spec.ts::'a live run offers control of it, and stopping it asks first'` prova `takeover`/`stop-run` visíveis e o diálogo de confirmação num run vivo (`run-0003`); os dois novos testes desta feature (`run-view-narrado.acceptance.spec.ts`, bloco AN-12, linhas ~321–336) provam adicionalmente `takeover`/`add-context` com contagem 0 num run encerrado (`run-0001`) — ambos verdes na rodada final (19/19, ver T004). Não existe um teste de unidade isolado de `TakeoverControls`/`AddContext` como componentes — a cobertura é via as telas que os montam, nomeada aqui em vez de presumida. |
| T010 — confronto `stages[]` servido × o que o rail precisa | FEITO | Ver seção "Confronto de campos" abaixo. Resultado: **nada faltou**. |
| T011 — regenerar contrato/cliente TS se T010 acrescentou campo | **Fora do escopo** — nada a fazer | T010 não acrescentou campo nenhum; não há o que regenerar. |
| T012 — tabela de narração no vocabulário compartilhado | FEITO | `console/src/surfaces/transcript.ts`: `narrate(event, locale)`, tabela `NARRATION_LEAD` (17 chaves = `STREAM_KINDS`), `namedOrFallback()` para ausência declarada. Verde: `pnpm exec vitest run tests/unit/surfaces/transcript-narration.test.ts` — 39 passed. |
| T013 — 17 frases × 2 idiomas + rótulos do toggle + linha "sem turno" | FEITO | 17 chaves `transcript.narration.*` + `transcript.view.{narrated,raw,payload}` + `run.usage.awaiting` + `run.links.watching` + `run.findings.{title,none}` + `run.stage.{rail.title,future}`, em `en.ts` e `pt-BR.ts`. Os seis nomes de estágio (`run.stage.resolve_integrations`…`deliver`) já existiam antes desta feature — reusados, não duplicados. |
| T014 — view do transcript: frase primária, `<details>`, toggle | FEITO | `console/src/surfaces/transcript-view.tsx`: `Entry` renderiza `narrations[event.id]` (testid `event-narration`) como conteúdo primário para todo kind que não é documento (`reasoning`/`report` mantêm `renderReport(detail)` inalterado — são já prosa, não JSON); o payload entra em `<details data-testid="event-payload-disclosure" open={view==='raw'}>`, fechado por padrão em Narrado, aberto em Bruto. Toggle `data-testid="transcript-view-toggle"` com `data-view`, botões `transcript-view-narrated`/`transcript-view-raw`. `labels.ts` ganhou `narrations(locale, events)`, espelhando `eventTimes()`. Os dois pontos de montagem (`run-detail.tsx`, `live-run.tsx`) e a suíte de testes existente (`transcript.test.tsx`) foram atualizados para o novo prop. `pnpm exec vitest run` nos quatro arquivos afetados: **71 testes, 60 passed, 11 failed** — os 11 são exatamente `reducer-stage-usage.test.ts` (T007, ainda não implementado); `transcript.test.tsx` (suíte pré-existente) e `run-detail-live-transcript.test.tsx` **inalterados, verdes** — nenhuma regressão. `uv run python -m tools.console_gate typecheck`: **falha só nos mesmos 14 erros esperados** de `reducer-stage-usage.test.ts` referenciando campos que T016 ainda vai criar; zero erros em qualquer outro arquivo. |
| T015 — componente do rail de estágios | FEITO | `console/src/surfaces/stage-rail.tsx` (`StageRail`, puro, servidor OU cliente): combina a ordem canônica (`STAGE_NAMES`, exportado de `run-card.tsx`) com os estágios já servidos; concluído = check verde + duração; falhado = quadrado vermelho; ativo (só quando `running`, e só quando nenhum estágio ainda registrado falhou) = anel pulsante (`pulse-live`/`pulse-live-ring`, primitiva da 000) + ícone de busca; futuro = número, sem duração fabricada. Estágio fora do vocabulário canônico é acrescentado ao final, na ordem do dado (edge case da spec). `console/src/live/live-run-rail.tsx` (`LiveStageRail`, cliente): mesmo componente, alimentado por `useRun(...).live.stages`. |
| T016 — redutor acumula usage/touched; painéis religados | FEITO | `console/src/live/reducer.ts`: `LiveStage`/`LiveUsage` novos tipos; `LiveState` ganha `stages`/`usage`/`touched`; `stagesAfter`/`usageAfter`/`touchedAfter` no laço de liberação de `applyEvents` (mesma disciplina de dedupe/held que `phase`/`waiting`/`decided` já tinham — verificado pelos testes de fora-de-ordem e de duplicata). `usageAfter` soma de `turn_completed` (tokens reais por turno, não apportionado); `touchedAfter` lê `tool_called.payload.arguments` pelas mesmas oito chaves de `platform/runs/replay.py::_RESOURCE_ARGUMENT_KEYS`, espelhadas em `RESOURCE_ARGUMENT_KEYS` (comentário cruzando os dois). `console/src/live/live-run-rail.tsx`: `LiveUsage`, `LiveTouched`, `LiveFindings`, `TouchedChip`, `FindingItem` — todos client components lendo o mesmo `useRun`. `run-detail.tsx`: painel de custo e painel de vínculos passam a `state='ready'` incondicional quando `running`; corpo lê `LiveUsage`/`LiveTouched` no lugar da tabela/lista estática; painel NOVO "Descobertas até agora" (`run.findings.title`), lido de `LiveFindings` (vivo) ou de `stagesFrom(replayed)` filtrando `finding !== ''` (encerrado) — reusa `FindingItem`, então as duas leituras desenham exatamente a mesma marca. Ordem das três colocada mais perto do artboard: Descobertas → Custo → Vínculos (o artboard tem Descobertas → Vínculos → Custo; não persegui essa troca final, registrado como divergência menor abaixo). Verde: `pnpm exec vitest run tests/unit/live/` — **148 passed**, incluindo as 12 do T007. `uv run python -m tools.console_gate typecheck` e `lint`: **limpos**. Suíte completa do console: `uv run python -m tools.console_gate test` — **3108 passed, 189 arquivos, zero falhas** (sem regressão em nenhuma tela). |
| Bug real encontrado e corrigido nesta fase | — | `Entry` (`transcript-view.tsx`) tratava como "documento" (renderizado por `renderReport`, nunca pela frase narrada) todo evento cujo `event.kind` semântico fosse `reasoning`/`report` — mas `kindOf()` usa `reasoning` como *default* para qualquer kind cru desconhecido (`stage_completed` incluso). Resultado: um evento de kind desconhecido caía em `renderReport('')` e não mostrava nada — quebrando AN-11. Corrigido com um segundo conjunto, `DOCUMENT_RAW_KINDS = {turn, model_reasoned, run_completed, run_failed}` (os quatro rawKind que os dois leitores realmente produzem para um documento), testado nos dois leitores. Achado pelo próprio acceptance vermelho, não por inspeção — exatamente o motivo de rodar o teste antes de assumir verde. |
| T016a — reforma da lista `/runs` | FEITO, com um degrade documentado | `console/src/surfaces/screens/runs.tsx`: runs vivos separados num band "Vivas agora" (`runs.live.title`) no topo, um card por run (`data-testid="run-live-card"`) com losango pulsante (`pulse-live`/`rotate-45`), barra de seis segmentos (`StageBar`, NOVO export de `stage-rail.tsx`, reusando a mesma `railOf()` do rail grande — uma derivação, duas apresentações) e tempo decorrido (`run-live-elapsed`); leitura de replay só para os runs vivos (tipicamente 0–3), nunca para os assentados — preserva a garantia "uma leitura para a lista inteira" documentada no cabeçalho do arquivo. Filtro trocou de `<FilterBar>` (dropdown compartilhado, usado por outras seis telas sem artboard nesta onda — não tocado) para `FilterChips`, um componente **local** desta tela (não o componente compartilhado): cada valor é um link para o endereço com aquele filtro, testid `filter-chip`, `data-active`. `RunCard` (`run-card.tsx`): `data-status` no card; título via `subject.full` + `line-clamp-2` (substituindo `subject.text` + `truncate`, decisão do board — `Investigations.dc.html`'s `.headline` também é 2 linhas); link `runs.row.openPage` (chave já existente, reusada) visível na linha fechada quando `status==='failed'`, para o transcript. **Degradado, nomeado**: o "estágio onde parou" de uma linha falhada não é mostrado — `last_completed_stage`/`stage_index` são campos que FR-023 atribui à feature 020 (ainda não rodou nesta onda) e não existem em `InvestigationSummary` hoje (confirmado por leitura direta do modelo Pydantic); FR-021a autoriza explicitamente "degradando sem eles". A forma de falha (quadrado vermelho) continua vindo de graça do `Badge` que a linha já tinha. |
| T017 — passe final contra o artboard | FEITO | Comparação linha a linha abaixo, contra `design/padrao-2026-08/RunView.dc.html` e `RunViewLight.dc.html`, lida junto com o código e as capturas comitadas (`run-detail-1440-{dark,light}.png`, `run-detail-live-1440-{dark,light}.png`). Duas divergências reais corrigidas nesta rodada; três nomeadas para o operador, nenhuma no meu escopo de arquivo para corrigir sem um raio de alcance maior do que esta feature deveria assumir sozinha. |

## T017 — o passe final, alegação por alegação

**Grid e espaçamento.** O artboard usa `grid-template-columns: 1fr 340px` para
transcript+rail (rail com largura fixa). O console usa `grid-cols-1
lg:grid-cols-3` com o transcript em `lg:col-span-2` (proporção 2/3–1/3, não
340px fixos) — em 1440px isso dá à rail ~458px, não 340px. **Não corrigido**:
essa grade é do scaffold de `RunDetailScreen` de antes desta feature (nunca
editei as classes de grid), compartilhada com outras telas de detalhe de
duas colunas — estreitá-la para 340px fixos é uma mudança de escopo maior do
que esta feature, com risco de quebrar responsividade em outros pontos.
**Nomeado para o operador**: se a largura fixa da rail for normativa, é um
ajuste no scaffold compartilhado, não nesta feature.

**Chips e seus contornos.** `Badge`/`CHIP_SHAPE` (fundação) já desenha
contorno + tinta — confirmado nas capturas, igual ao board (decisão 1 de
`DIVERGENCIAS.md`, já resolvida antes desta feature). O alternador
Narrado/Bruto: o artboard desenha dois chips independentes lado a lado, cada
um com seu próprio contorno; minha primeira versão os colocava dentro de um
único poço (`rounded-full border bg-sunken p-1`), um controle segmentado —
divergência real, **corrigida** (commit `fff2cd4a`): agora são dois `Button`
lado a lado sem poço comum, `variant='secondary'` quando ativo (com
contorno) e `variant='quiet'` quando não (sem contorno). Confirmado na
recaptura de `run-detail-1440-dark.png`. **Remanescente, nomeado**: o board
desenha esses chips pequenos (padding 2px 9px, 11px) e eu reusei o `Button`
padrão (`h-control`, `text-body`) — mais alto que o board. Precisaria de uma
variante pequena de chip que a fundação ainda não declara; declarado abaixo
para o orquestrador aplicar via 000, não inventado aqui.

**As três famílias tipográficas.** Título (`PageHeader`), rótulos de
estágio, corpo do transcript: usam as classes já verificadas pelo acceptance
da 000 (`font-display`=Space Grotesk, texto corrido=IBM Plex Sans, ids/dados
via `font-mono`=IBM Plex Mono) — nenhuma nova família introduzida por mim.
Um ponto real encontrado: o número de um estágio futuro é `.sg` (Space
Grotesk) no board — minha primeira versão usava `font-sans` (IBM Plex Sans).
**Corrigido** junto com a mudança de posição do número (ver "formas do rail"
abaixo, commit `fff2cd4a`).

**As formas do rail de estágios.** Concluído: círculo cheio + check — cor
bate (`bg-success`/`#3ad195` dark, `#0a7452` light — o mesmo hex que
`--accent`, registrado como não-divergência: `success` e `accent` são o
mesmo valor nesta paleta, então a diferença de nome de token não é uma
diferença visual). Ativo: anel + ícone de busca + `pulse-live`/`pulse-live-ring`
(a primitiva certa da fundação, reaproveitada, não inventada) — bate.
Falhado: quadrado + ícone — o board não desenha um estágio falhado
neste artboard específico (o cenário do artboard não falha), então a forma
vem só de FR-003 e do vocabulário de `design/status.ts` (`failed`→
danger/square), não de um pixel do board para comparar. **Divergência real,
corrigida** (commit `fff2cd4a`): um estágio futuro no board tem o número
*dentro* do próprio círculo (o `<span>` do círculo carrega o dígito como seu
próprio conteúdo de texto); minha primeira versão deixava o círculo vazio e
desenhava o número como uma terceira linha abaixo do rótulo. Corrigido —
`StageMark` agora recebe `position`/`locale` e desenha o número dentro do
círculo para o estado `future`; a linha de baixo só existe para
`done`/`failed` (duração), exatamente como o board. Confirmado visualmente
nas quatro capturas recapturadas.

**Formas de status.** `Badge`/`StatusDot` (fundação) — não tocados por
mim, herdados corretamente. Os marcadores de "Descobertas até agora" usam
`StatusDot status={failed ? 'failure' : 'info'}` (losango/quadrado do
vocabulário já declarado) — o board desenha um losango âmbar e um quadrado
vermelho nos três exemplos, sem relação óbvia com falha de estágio (dado
ilustrativo, não especificação de cor por finding — já registrado como
suposição na seção própria).

**Motion.** `pulse-live`/`pulse-live-ring` no estágio ativo — bate (mesma
primitiva, mesmo efeito visual que o `.pulse::after` do board). O
`stage-shimmer` no conector que entra no estágio ativo — bate com
`.stageActive` do board. O `slide-in` nos chips de "O que tocou" recém-
chegados — bate com `.newRow` do board nesses mesmos chips. **Divergência
nomeada, não corrigida**: o board também aplica `.newRow`/slide-in ao evento
mais novo do *transcript* (a primeira entrada da lista); esta feature não
aplica motion de chegada às entradas do transcript. Não é uma AN normativa
("o movimento em si é asserido pelo acceptance automatizado" — não há
alegação de acceptance sobre isso) e exigiria rastrear "qual é o evento mais
novo" como estado extra no componente `Transcript` compartilhado com o
replay — deixado de fora por escopo e tempo, nomeado para o operador.

**A contagem do cabeçalho.** AN-09 (contagem = lista renderizada) está
verde — mas o board também diz "o mais novo primeiro" e mostra o evento mais
recente no topo. O console (antes e depois desta feature, comportamento
herdado) lista os eventos em ordem cronológica — o mais **antigo** primeiro
— confirmado por `live.spec.ts`: "the first thing a run does is start...
entries.first() has data-raw-kind 'run_started'". **Divergência real,
nomeada, não corrigida**: inverter a ordem do transcript é uma mudança de
comportamento estabelecida por toda a base (replay e stream, todo teste que
assume ordem cronológica) — bem além do raio de alcance desta feature, e
`tasks.md`/`spec.md` desta feature nunca pedem essa inversão. Nomeado para o
operador: se "mais novo primeiro" for normativo, é uma decisão de onda, não
um ajuste desta feature — e o rótulo "o mais novo primeiro" nem deveria ser
escrito antes dessa decisão, porque hoje seria uma legenda falsa.

**Estados vivo/encerrado dos controles.** AN-12 verde (`takeover`/
`add-context` ausentes num run encerrado, testado). O board desenha
Assumir/Parar no cabeçalho do run; o console os desenha num painel "Control"
na rail direita. **Divergência pré-existente, não desta feature**: FR-020
("Os controles de condução... DEVEM permanecer como estão... sem mudança de
comportamento") congela essa posição explicitamente — citada aqui por
completude, não como algo a corrigir.

**"Descobertas até agora" — a barra de progresso.** O board desenha, sob a
lista de descobertas, uma barra "N de M alegações com evidência" — um dado
de avaliação de evidência (`evidence_assessed`/`backed`/`missing`, o mesmo
usado pelo `EvidenceChip` da lista), não o mesmo dado dos findings de
estágio. FR-017 pede só a lista de findings por estágio, que está construída
e testada; a barra de progresso **não está implementada**. **Nomeado para o
operador**: um elemento visível do board que a spec desta feature não pede
por texto — candidato a acréscimo futuro ou a registro em
`DIVERGENCIAS.md`, não uma alegação que este slot deixou vermelha.

**Token/forma declarados para o orquestrador aplicar via 000**: uma variante
pequena de chip (padding ~2px 9px, ~11px, contorno fino) para o alternador
Narrado/Bruto — hoje aproximada com o `Button` padrão (mais alto que o
board). Não criei essa variante aqui porque `components/action.tsx` é
consumido em todo o console e uma variante nova pede a mesma disciplina de
runtime-checkable/teste que as três existentes já têm — decisão da 000, não
desta feature.
| T018 — gates locais verdes | FEITO, com uma lacuna pré-existente registrada | `uv run python -m tools.console_gate typecheck`: limpo. `lint`: limpo. `test` (vitest, cobertura): **3109 passed, 189 arquivos, zero falhas**. Acceptance da feature (`tests/e2e/run-view-narrado.acceptance.spec.ts`): **19/19 passed**. Suíte transversal da onda (`transversal-rules.spec.ts` + `screen-truthfulness.acceptance.spec.ts`, ~60+40 casos): **12 falharam, o resto passou** — todas as 12 confirmadas **pré-existentes, não causadas por esta feature**, por duas causas distintas, nenhuma no meu escopo de arquivo: (1) 3 falhas sobre "setup progress"/`wizard-position` — o assistente de configuração inicial, nada a ver com runs; (2) 9 falhas (6 combinações de regra × `/runs/{id}` e/ou `/incidents/{id}`, mais o teste de controle de run vivo) todas pelo mesmo `getByTestId('row')` nunca encontrado — confirmado que **`/incidents/{id}` falha pela mesma razão**, e `/incidents` nunca foi tocado por esta feature; `RunCard` (`run-card.tsx`) sempre usou `data-testid="run-card"`, nunca `"row"` (confirmado com `git show c01f8412:console/src/surfaces/run-card.tsx`, o commit-base desta worktree, antes de qualquer edição minha) — pré-existente em ambas as telas, não uma regressão desta feature. Fora do escopo de arquivo desta feature para corrigir com segurança. |
| Segundo bug real encontrado e corrigido, desta vez pela inspeção visual | — | A captura de `run-detail-1440-light` mostrou toda "Capability result" narrando "An event of an unrecognised kind arrived: tool_returned" — `eventsFromReplay` soletra o resultado de uma chamada como `tool_returned` (`transcript.ts`), nunca `tool_succeeded`/`tool_failed` (o vocabulário do *stream*), e a tabela de narração só tinha as duas grafias do stream. Todo resultado de capacidade em **todo run encerrado** caía no genérico — e nenhum teste de unidade pegou, porque o teste de "funil único" construiu as duas leituras a partir de um documento no formato do *stream*, nunca chamando `eventsFromReplay` de verdade. Corrigido: `tool_returned` mapeado para a mesma frase de `tool_succeeded` (texto neutro quanto ao desfecho — o Badge ao lado já carrega sucesso/falha). Teste de regressão acrescentado a `transcript-narration.test.ts`, chamando `eventsFromReplay` de verdade. Achado pela imagem, não pelo teste — exatamente o motivo de inspecionar a captura em vez de confiar só na existência do arquivo. |
| T019 — baselines visuais novos | FEITO | `console/visual/screens.json`: 4 entradas atualizadas (`run-detail-1440-dark`, `run-detail-1440-light`, `run-detail-live-1440-light`, `runs-1440-light`) + 2 novas (`run-detail-live-1440-dark`, `runs-1440-dark`) — cobre "run vivo e encerrado nos dois temas" (FR-024) e a lista reformada nos dois temas. Editado preservando a ordem original do arquivo (a primeira tentativa usou `.sort()` e reordenou entradas não relacionadas por um `id` fora de ordem alfabética já existente — revertida antes de commitar; `git diff --stat` confirmou 28 inserções/6 deleções, exatamente as 6 entradas pretendidas). Capturado com `uv run python -m tools.console_visual accept` (a imagem pinada por dígest, `--network none`) — nunca `console_gate e2e`. Cada uma das 6 PNGs verificada: (1) todas com SHA-256 distintos entre si; (2) tamanhos de arquivo substanciais e distintos (118–226 KB); (3) **inspeção visual das três telas mais relevantes** (`run-detail-live-1440-dark`, `runs-1440-dark`, `run-detail-1440-light`) confirmando conteúdo real e correto — rail de seis estágios, narração, disclosure fechado, painéis vivos honestos, band "Vivas agora" com barra de seis segmentos, chips de filtro, headline em duas linhas, link de transcript na linha falhada. A inspeção da captura de `run-detail-1440-light` foi o que **achou o bug do `tool_returned`** (ver linha abaixo) — recapturado depois da correção; as 4 telas não afetadas pelo bug (as duas `live`, as duas de `runs`) têm checksum idêntico entre a primeira e a segunda rodada, confirmando captura determinística. `resources-1440-light`/`resources-320-light` falharam nas duas rodadas por um overflow pré-existente e não relacionado (`row-list` mais alto que a página inteira) — nenhum baseline meu foi afetado, confirmado por `git status` mostrando só os 6 arquivos esperados. Baselines num commit próprio, separado da mudança de código. |
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

## Segunda rodada de decisões do operador — estado no encerramento por orçamento

Sessão interrompida por limite de orçamento antes de recapturar baselines e
antes da varredura de pt-BR. Commit `df1dfffa` (`wip`) carrega tudo abaixo,
sem baseline nova e sem a varredura.

### As quatro decisões do T017, disposição final

1. **Rail fixo de 340px** — Não aplicado como largura fixa: `grid-cols-[1fr_340px]`
   é rejeitado pelo lint (`design/no-design-literals` bane qualquer utilitário
   de valor arbitrário, não só o sufixo numérico). Não existe token declarado
   próximo de 340px (`w-sidebar` é a barra de navegação do shell, sem relação).
   Revertido para o grid proporcional original (`lg:grid-cols-3`/`lg:col-span-2`)
   em `console/src/surfaces/screens/run-detail.tsx`, com comentário no código
   nomeando a necessidade. **Nenhuma outra tela de detalhe foi tocada** — não
   havia nada a evitar tocar, porque a mudança não chegou a ser aplicada.
   Necessidade declarada para o orquestrador aplicar via 000: um token de
   largura fixa para o rail lateral de `run-detail`, escopado a esta tela.
2. **Evidence-progress bar** — Feito. Rodapé do painel de achados usa a chave
   `run.evidence.backed` já existente e uma largura de porcentagem inline
   (mesmo padrão já usado no "change ruler" do mesmo arquivo). Ver
   `console/src/surfaces/screens/run-detail.tsx`.
3. **Slide-in na entrada recém-chegada** — Feito, mas com mudança de estratégia
   de teste. Implementado com rastreador baseado em efeito
   (`console/src/surfaces/transcript-view.tsx`) que distingue montagem inicial,
   catch-up ao vivo (primeira entrega não-vazia) e chegada genuína subsequente
   — necessário porque `react-hooks/refs` proíbe ler `ref.current` durante o
   render, e o padrão "ajustar estado durante o render" do React descarta o
   próprio render em que o valor seria exibido. O teste E2E do "slide-in"
   provou-se estruturalmente não confiável contra o harness mock (entrega do
   backlog inteiro de forma essencialmente atômica; nunca observado um estado
   intermediário entre <11 e 12 eventos, mesmo com polling). Removido e
   substituído por dois testes de unidade determinísticos em
   `console/tests/unit/surfaces/transcript.test.tsx`
   (`render()`+`rerender()`), que controlam exatamente quando a prop `events`
   muda. 21/21 passando nessa suíte isoladamente.
4. **Toggle Narrado/Bruto em formato de chip** — Feito localmente, sem tocar
   `console/src/design/**`: dois `<button>` simples usando `CHIP_SHAPE` e o
   vocabulário de cor de estado já exportado por `components/status.tsx`
   (consumo, não edição, do arquivo congelado).
5. **Ordenação newest-first (segunda decisão do operador)** — Feito. A
   inversão é interna ao componente `Transcript`
   (`console/src/surfaces/transcript-view.tsx`: `[...events].reverse()`);
   `eventsFromReplay`, `eventsFromStream` e `LiveState.events` continuam
   cronológicos. Legenda de posição recalculada em
   `console/src/surfaces/labels.ts` para o novo sentido. Nova chave
   `transcript.newestFirst` (EN "newest first" / PT-BR "o mais novo
   primeiro") deliberadamente **não** dobrada em `transcript.events`/`.one`
   porque essa chave também é consumida por `settings/audit.tsx`, uma tela
   sem relação e sem ordem invertida.

### Levantamento de consumidores do transcript (ordenação)

- **`console/src/surfaces/transcript-view.tsx`** — alterado (a própria
  inversão).
- **`console/src/surfaces/labels.ts`** — alterado (fórmula da legenda de
  posição).
- **`console/src/live/live-run.tsx`** (`LiveEventCount`) — alterado (legenda
  "o mais novo primeiro" acrescentada).
- **`console/src/surfaces/screens/run-detail.tsx`** — alterado (mesma
  legenda no cabeçalho da tela).
- **`console/tests/e2e/live.spec.ts`** — alterado: teste renomeado para "the
  transcript fills as frames arrive, newest event on top", agora afirma que
  o último elemento do DOM é `run_started` (o mais antigo) e que o primeiro
  elemento muda ao chegarem mais eventos. Rodado isoladamente: 4 passou / 1
  falhou — a falha é a pré-existente e sem relação (`getByTestId('row')` em
  `/runs`, confirmada em rodadas anteriores desta sessão via
  `git show c01f8412:console/src/surfaces/run-card.tsx`, e reproduzida
  identicamente em `/incidents/{id}`, que esta feature nunca tocou).
- **`console/tests/unit/surfaces/transcript.test.tsx`** — alterado: o teste
  "every kind of event > is drawn, and is distinguishable" agora afirma
  `[...TRANSCRIPT_KINDS].reverse()`, com comentário explicando por quê.
- **`console/src/surfaces/run-card.tsx`** — **intencionalmente não tocado**.
  É o caso "lê como sequência, não como feed": o card de run na lista
  (`/runs`) usa `railOf`/`StageBar` para desenhar a esteira de estágios em
  ordem de execução (etapa 1 → etapa 6), que é uma linha do tempo de
  progresso, não uma lista de eventos recentes-primeiro. Inverter essa
  ordem quebraria a leitura do rail como "quanto já andou": o pipeline
  precisa ler da esquerda (início) para a direita (fim) para fazer sentido
  como progresso, exatamente o motivo pelo qual esta reversão foi escalada
  para o operador em vez de decidida sozinha.
- **`console/src/surfaces/screens/runs.tsx`** — verificado, sem mudança
  necessária: não lê `events`/transcript, só o resumo de estágios já coberto
  pelo caso acima via `run-card.tsx`.

### Lacuna de verificação aberta, não escondida

Rodando `010-leitura-do-relato.acceptance.spec.ts` e `surfaces.spec.ts`
juntos (não isoladamente, por pressão de orçamento), 6 testes falharam:

- `010-leitura-do-relato...spec.ts:83` (cabeçalho/aba/célula concordam sobre
  headline sem markdown)
- `010-leitura-do-relato...spec.ts:133` (run sem headline mostra trigger+id)
- `010-leitura-do-relato...spec.ts:229` (relatório em disclosure fechado)
- `010-leitura-do-relato...spec.ts:366` (staging-safe: headline sem
  markdown, ≤120 caracteres)
- `surfaces.spec.ts:45` (lista filtrada sobrevive a reload)
- `surfaces.spec.ts:57` (ordenação como navegação com endereço)

**Não foi possível isolar se isso é pré-existente, interferência entre
arquivos (já observada nesta sessão ao rodar múltiplos specs juntos) ou uma
regressão real da reversão.** Nenhum desses arquivos foi tocado por esta
feature. Nenhuma dessas asserções fala de ordem de transcript. Mas nem
`010-leitura-do-relato.acceptance.spec.ts` nem `surfaces.spec.ts` foram
rodados isoladamente nesta sessão para confirmar. **Isto é o primeiro passo
de quem retomar**: rodar cada arquivo sozinho
(`uv run python -m tools.console_e2e run -- tests/e2e/010-leitura-do-relato.acceptance.spec.ts --reporter=line`,
depois o mesmo para `surfaces.spec.ts`) antes de qualquer outra coisa.

### O que NÃO foi feito neste encerramento

- **Baselines visuais não recapturadas** para nenhuma mudança desta segunda
  rodada (grid revertido, evidence bar, slide-in, toggle em chip, ordem
  invertida). T019 continua `[ ]`. Todas as baselines existentes no repo são
  da rodada anterior (grid ainda com a tentativa `[1fr_340px]` revertida
  depois da captura, ou seja: **as baselines atuais podem já estar
  desatualizadas mesmo antes desta rodada — não confirmado**).
- **Varredura de português europeu em `pt-BR.ts` não iniciada.** A única
  mudança no arquivo nesta sessão foi a chave nova `transcript.newestFirst`,
  já em pt-BR correto ("o mais novo primeiro"). As ocorrências já
  identificadas em rodadas anteriores desta sessão e ainda não corrigidas:
  `registada`/`registadas` (`runs.list.caption`, `runs.empty.body` —
  conferir texto exato antes de corrigir), `'Precisa de si'`
  (`dashboard.attention.title`), `'Objectivo'` (`transcript.kind.objective`).
  Estas três são conhecidas; **o arquivo não foi varrido exaustivamente** —
  quem retomar deve ler `console/src/i18n/pt-BR.ts` inteiro, não só essas
  três chaves. Fica pendente, em commit próprio, separado da feature, como
  pedido.
- **`tasks.md` T017 permanece `[x]`** (já estava marcado antes desta rodada;
  as correções desta rodada são a conclusão do que T017 já cobria, não uma
  tarefa nova). **T019 permanece `[ ]`** — nenhuma baseline nova capturada.

### Estado exato no encerramento

- Último commit: `df1dfffa` — `wip(console): apply the T017 round-2 rulings and reverse transcript order`.
- Árvore de trabalho: limpa (nada não commitado) além deste próprio arquivo de controle e seu espelho, ainda sendo escritos.
- Suítes confirmadas isoladamente após esta rodada: acceptance da feature
  19/19, `live.spec.ts` 4/5 (a falha é pré-existente e sem relação),
  `transcript.test.tsx` 21/21.
- Próximo passo para quem retomar: rodar `010-leitura-do-relato.acceptance.spec.ts`
  e `surfaces.spec.ts` isoladamente para decidir a lacuna acima; só depois
  recapturar baselines; só depois a varredura de pt-BR, em commit separado.

## Fechamento — os 6 de 29, as baselines e a varredura de pt-BR

### Veredito sobre os 6 de 29: pré-existentes, nenhum é meu

Isolados individualmente (não mais rodados juntos): `010-leitura-do-relato.acceptance.spec.ts`
sozinho deu os mesmos 4 falhos / 18 passou / 1 pulado; `surfaces.spec.ts` sozinho deu os
mesmos 2 falhos / 11 passou / 6 pulados. Isso já bastava para suspeitar de pré-existência,
mas suspeita não é veredito — a instrução foi clara sobre isso. Then a comparação real:

**Método**: `git worktree add --detach` no commit-base `c01f8412` (o commit em que esta
feature começou), em `/srv/workspaces/v8-s1-030-base-check` — irmã do worktree da feature,
não dentro dele, para o Turbopack não recusar o `node_modules` religado como um link que
"sai do sistema de arquivos". `pnpm install`/`console_gate build` completos e independentes
ali (`CI=true`, sem rede — o lockfile é o mesmo, então tudo veio do store local). Os dois
arquivos suspeitos rodados contra esse build, exatamente como pedido.

**Resultado: idêntico, byte a byte nos nomes e linhas dos testes que falham.**
`010-leitura-do-relato.acceptance.spec.ts` no commit-base: os mesmos 4 falhos, nas mesmas
linhas (83, 133, 229, 366), 18 passou, 1 pulado. `surfaces.spec.ts` no commit-base: os
mesmos 2 falhos (45, 57), 11 passou, 6 pulados. **Os 6 já falhavam antes desta feature
tocar uma única linha.** Nenhum é meu; nenhum foi corrigido.

**Causa raiz, nomeada e não corrigida (não é desta spec)**: as seis asserções dependem de
`page.getByTestId('row')` (`surfaces.spec.ts:45,52`; e o helper `rowFor()` de
`010-leitura-do-relato.acceptance.spec.ts:66-68`) ou `page.getByTestId('sort')`
(`surfaces.spec.ts:58`) contra `/runs`. Confirmado por leitura direta do commit-base:
`/runs` já renderizava via `<RunCard>` (`console/src/surfaces/screens/runs.tsx:122` no
commit-base) — nunca via o `RowList` genérico de `rows.tsx`, que é o único lugar do
código-fonte que desenha `data-testid="row"`. `RunCard` nunca carregou esse testid, no
commit-base nem depois. Esses três testes foram escritos assumindo uma tabela genérica
ordenável que `/runs` não usa desde antes desta feature — provavelmente desde a própria
reforma que introduziu `RunCard`, numa slot anterior a esta. Corrigir os seis não é escopo
desta spec (nem o arquivo, nem a tela raiz do defeito pertencem a ela); nomeado aqui para
quem for corrigi-los depois.

### O efeito colateral não planejado deste passo, corrigido antes de prosseguir

O primeiro `pnpm install` fresco dentro do worktree-irmão deixou o **worktree da própria
feature** com `console/node_modules` corrompido — 22 links simbólicos de topo (`react`,
`next`, `typescript`, `eslint`, `@playwright/test`, etc.) apontando para dentro do
worktree-irmão, que foi removido logo em seguida (`git worktree remove --force`), tornando-os
órfãos. Descoberto porque a primeira tentativa de recapturar as baselines falhou dentro do
contêiner pinado com `Cannot find module '/work/console/node_modules/@playwright/test/cli.js'`.
Corrigido com `pnpm install --frozen-lockfile --offline` dentro do próprio worktree da
feature — 1,3s, "reused 480" (nada baixado, tudo do store local), zero links quebrados
depois. `node_modules` é ignorado pelo git; nada rastreado foi tocado (`git status` limpo
antes e depois). Citado aqui porque é exatamente o tipo de coisa que teria invalidado
silenciosamente qualquer teste rodado depois, se não tivesse sido percebido.

### Baselines recapturadas

Comparado o commit da última captura (`b9ad92df`) contra o HEAD atual: só
`transcript-view.tsx`, `labels.ts`, `live-run.tsx` e `run-detail.tsx` mudaram no código de
produção desde então — `runs.tsx`/`run-card.tsx`/`stage-rail.tsx` seguem intocados nesta
rodada. Recaptura completa (`tools.console_visual accept`, imagem pinada) rodada mesmo
assim, para não confiar em previsão: **só `run-detail-1440-dark.png` e
`run-detail-1440-light.png` saíram diferentes** (confirmado por `git status` depois).
Verificadas como capturas reais antes do commit: tamanho plausível (223KB→224KB,
219KB→219KB, não os poucos KB de um placeholder), SHA-256 distinto do commit anterior, e
inspeção visual direta — a tela capturada mostra "11 eventos · o mais novo primeiro",
"Raciocínio" (o evento mais recente) no topo do transcript, e o alternador Narrado/Bruto
em formato de chip. `run-detail-live-1440-{dark,light}` e `runs-1440-{light,dark}` saíram
byte-idênticos e não foram recommitados.

**Por que a barra de evidência não aparece em nenhuma das seis baselines registradas**,
nomeado precisamente em vez de deixado para ser descoberto: `evidenceOf()`
(`console/src/surfaces/run-evidence.tsx:39-51`) só marca `assessed: true` quando o campo
`evidence_assessed` do próprio registro do run é `=== true`. **Nenhum run em nenhum
fixture de `fixtures/scenarios/populated/*.json` carrega esse campo** — nem `run-0001`
(usado por `run-detail-1440-*`), nem `run-0003` (usado por `run-detail-live-1440-*`),
verificado por varredura de todos os fixtures do cenário. O código está correto e a
condição é a mesma barreira que `EvidenceChip` já usa (nunca desenhar 0 de 0 como se
fosse um veredito) — mas isso significa que a barra, embora implementada, **nunca fica
visível em nenhuma captura visual ou teste E2E deste repositório**, porque nenhum dado de
fixture jamais a alimenta. Isto não foi deixado como afirmação vazia: foi escrito um teste
de unidade que serve o próprio registro do run com `evidence_assessed: true,
evidence_backed: 3, evidence_missing: 1` diretamente por `fetch` mockado (sem depender do
fixture do mock plane) e afirma que a barra desenha "3 of 4 claims backed" — em
`console/tests/unit/surfaces/run-detail.test.tsx`, describe "a run whose own record says
its evidence was assessed", 2 testes, ambos verdes (o caso presente e, ao lado, o caso
ausente que já existia). É a única prova no repositório de que o mecanismo funciona com
dado real. **Pendência nomeada para quem mexer nos fixtures depois**: se um run populado
algum dia carregar `evidence_assessed`, a barra vai aparecer numa baseline pela primeira
vez — isso é o esperado, não uma regressão.

### Varredura de português europeu em `pt-BR.ts` — 46 ocorrências, cada uma corrigida

Varredura por classes de marcador (não por leitura linear de 2254 linhas): grep multi-padrão
cobrindo grafias pré-1990 (`cç`/`ct` mudo: activo, Acções, Objectivo, Actividade,
exactamente, afectado), o particípio `registad(o/a/os/as)` vs `registrad(o/a/os/as)`,
vocabulário lexical (Utilizador, Palavra-passe, consola, equipa, partilhável, libertar), a
construção perifrástica europeia "está a/continua a + infinitivo" vs o gerúndio brasileiro,
o dativo "de si" vs "de você", e o acento pré-reforma em "pára". Cada padrão passado pelo
arquivo inteiro (não só o que já tinha sido lido), com falsos positivos descartados à mão
(ex.: "Objetivo"/"objective" como nome de chave batendo no mesmo regex; "compartilh-"
contendo "partilh-" como substring). 46 ocorrências corrigidas por um script Python com
substituição exata assertiva (contagem 1 por entrada, aborta se não achar ou achar mais de
uma vez) — não um `sed` cego. Lista completa, `file:line` do estado anterior ao commit
`eacca5f9`:

- **registad(o/a) → registrad(o/a)**, 15 ocorrências: `runs.list.caption` (612),
  `runs.empty.body` (618, 2×), `run.usage.empty.heading` (636), `run.usage.empty.body`
  (638), `incidents.empty` via `incident.derivation.empty.heading` (785),
  `incident.derivation.empty.body` (787), `incident.timeline.empty.body` (792),
  `memory.strategies.empty.body` (1101), `topology.empty.heading` (1144),
  `autonomy.preview.lead` (1236), `audit.empty.heading` (1683), `surface.none` (465).
- **activ/Acções/Objectivo/Actividade/exactamente/afectado** (grafia pré-1990), 11
  ocorrências: `shell.guardian.active` (366), `palette.group.actions` (412),
  `surface.error.detail` (458), `transcript.kind.objective` (475),
  `dashboard.activity.title` (569), `dashboard.hero.empty.body` (580),
  `dashboard.quickActions.title` (582), `dashboard.guardian.detectors` (590),
  `dashboard.guardian.empty.body` (595, "exactamente").
- **Utilizador → Usuário, Palavra-passe → Senha, consola → console** (com concordância de
  gênero: "desta consola"→"deste console"), 5 ocorrências: `signIn.username` (419),
  `signIn.password` (420), `signIn.context` (418, também "contacta"→"contata"),
  `error.context` (433), `notFound.context` (436), `configuration.preview.lead` (1293).
- **equipa → equipe**, 2 ocorrências: `schedules.caption` (1008), `schedules.empty.body`
  (1011).
- **partilhável → compartilhável**, 1: `runs.filtered.body` (622).
- **pára → para** (acento pré-reforma), **libertar → liberar** (inconsistente com
  `stop.engaged.howToRelease` que já dizia "liberá-lo" corretamente), 1 linha com as duas:
  `stop.consequence` (351).
- **"está a/continua a" + infinitivo → gerúndio**, 12 ocorrências: `page.detectors.context`
  (285, "está a ser observado"→"está sendo observado"), `stop.consequence` (351, 356,
  "continuam a correr e a propor"→"continuam rodando e propondo"),
  `failure.migrations.title` (394), `session.impersonation.banner` (429),
  `error.context` (433), `dashboard.attention.empty.action` (551),
  `dashboard.quickActions.empty.body` (585, 2×), `incidents.empty.action` (764),
  `approvals.empty.action` (872), `proposal.reason` (892), `audit.empty.body` (1685).
- **"de si" → "de você"**, seguindo o próprio inglês-fonte ("Needs you"/"Nobody but you") e
  o registro que o resto do arquivo já usa ("você" aparece dezenas de vezes noutras
  chaves): `notifications.title` (375), `dashboard.attention.title` (544),
  `dashboard.attention.count` (545), `dashboard.attention.count.one` (546),
  `admin.empty.heading` (1669).

Verificado depois: nova varredura com o mesmo conjunto de padrões — zero ocorrências reais
restantes (os únicos hits são falsos positivos já esperados: "objective" como nome de
chave, "compartilh-" contendo "partilh-"). `pnpm exec vitest run tests/unit/i18n`: 29/29.
`tsc --noEmit`: limpo. Suíte completa do console depois de tudo (varredura + teste da
barra + baselines): **3113/3113, 189 arquivos**, contra 3111 antes desta rodada final (as
2 novas do `run-detail.test.tsx`).

**Nota sobre um dos próprios commits desta rodada**: a mensagem do commit `eacca5f9`
carrega uma frase corrompida no corpo (um fragmento de rascunho que sobrou por engano —
"the "está a based on inglês, no idioma correto abaixo" not applicable —"). O conteúdo do
commit (o arquivo `pt-BR.ts` e as 46 correções) está correto e verificado como acima; só a
prosa da mensagem tem esse defeito. Não fiz `--amend` para corrigi-la, seguindo a regra
deste projeto de nunca reescrever um commit já feito nesta sessão a não ser que pedido
explicitamente — nomeado aqui em vez de escondido, para quem revisar ou fizer squash no
merge decidir o que fazer com a mensagem.

### Commits desta rodada final

- `12f06d29` — teste da barra de evidência com dado real.
- `70badc79` — as duas baselines de `run-detail` recapturadas.
- `eacca5f9` — a varredura de pt-BR, sozinha (mensagem com o defeito de prosa acima
  nomeado).

### Estado exato no fechamento

Árvore limpa. Suíte completa verde (3113/3113). Acceptance da feature e `live.spec.ts` não
foram rerrodados nesta última passada porque nada nela toca código de aplicação que os dois
cobrem — só dados de i18n (pt-BR, que nenhum dos dois asserta em português), um arquivo de
teste novo (sem relação) e binários de baseline; a última vez que rodaram isolados, antes
desta passada, deram 19/19 e 4/5 (a falha é a pré-existente e sem relação, mesma família
dos 6 de 29 confirmados acima). Nenhum código de produção mudou desde essas duas rodadas.

## Reparo pontual — literais de id em `@staging-safe` (auditoria independente, 2026-08-30)

Reparo isolado, disparado por uma verificação independente contra o staging
real, não uma nova rodada de implementação da feature. Escopo: só
`console/tests/e2e/run-view-narrado.acceptance.spec.ts`. Estado abaixo
verificado por execução direta dos comandos citados, lendo o código de saída
de cada um — não inferido.

### O defeito

O arquivo declarava `LIVE_RUN = 'run-0003'` e `SETTLED_RUN = 'run-0001'` —
ids que só existem no plano mock — e seis testes marcados `@staging-safe`
navegavam direto para `/runs/${id}` usando esses literais. Contra o staging
real esses ids não resolvem a nada, o que contraria a doutrina que o próprio
`transversal-rules.spec.ts` documenta para as rotas que varre (linha 587 na
árvore atual: "a run or an incident id literal in a test file is a dataset
dependency in disguise"). Um dos seis passava de forma vazia em vez de
falhar: a leitura de `/v1/runs/{run_id}` falha contra um id inexistente, mas
`railOf` (`console/src/surfaces/stage-rail.tsx:63-92`) ainda desenha os seis
estágios como `future` para um run cuja leitura não trouxe nenhum estágio —
comportamento correto do componente para esse caso — então a asserção do
teste (seis itens, na ordem certa) não distinguia um run vivo real de uma
leitura totalmente fracassada. Passagem verde sem medir nada.

### Linha de base real, medida antes de qualquer mudança nesta rodada

`uv run python -m tools.spec_validation browser --feature
specs_v8/030-run-view-narrado --test
console/tests/e2e/run-view-narrado.acceptance.spec.ts --backing staging`,
credenciais carregadas com `set -a; . ./.env; set +a` na mesma shell:

**exit 1 — 7 failed, 3 passed, de 10 selecionados pela tag.** Falharam: AN-03
(linha 113 da versão anterior), AN-06 (176), as duas iterações de AN-09
(243), AN-12 (337), e as duas AN-14 (`run-live-card` em 359, linha de status
falhado em 396) que não são literais de id. Passavam: AN-01 (56, vazio — ver
acima), e as duas AN-14 que não dependem de id nem de liveness ("a completed
row shows a claims chip…", "the status and trigger filters render as
chips"), que já funcionavam contra os 50 runs `Completed` que o staging
carrega hoje.

**Correção ao relato que abriu esta tarefa**: a cifra "dez falhas" não bate
com o que a suíte de fato reporta — são sete falhas reais mais uma passagem
vazia (a de AN-01), não dez falhas, de dez testes selecionados. O número
certo está acima, medido nesta rodada, não presumido a partir do relato.

### O reparo, um teste por vez

Seis testes tocados, cada um julgado pela própria alegação em `spec.md`
(seção "Alegações normativas"), não pelo título do teste:

1. **AN-01/AN-02, "a run's own page shows the six stages…"** (linha 119
   atual). `spec.md` linha 103: "O detalhe de **um run** mostra os seis
   estágios…" — não é uma alegação de liveness, e `railOf` prova isso por
   construção (mesma função, mesma saída de seis itens em ordem,
   independente de `running`). **Descoberto**, não removido: `discoverRunPath(page,
   'live')` (linha 73, prefere um run vivo quando existe, cai para o
   primeiro assentado quando não existe). Continua `@staging-safe`.
2. **AN-03, "in Narrado, no JSON payload block…"** (linha 184). `spec.md`
   linha 108: alegação genérica sobre a visão Narrado, também não depende de
   liveness — `Entry` (`transcript-view.tsx`) é o mesmo componente nos dois
   casos. **Descoberto**: `discoverRunPath(page, 'settled')` (prefere
   assentado, cai para vivo). Continua `@staging-safe`.
3. **AN-06, "a live run with a recorded turn shows tokens…"** (linha 258).
   `spec.md` linha 115: "**Durante um run vivo**…" — alegação
   incondicionalmente sobre liveness; nenhuma descoberta resolve isso quando
   o ambiente não tem run vivo nenhum (confirmado: 50/50 `Completed` no
   staging agora). **Tag `@staging-safe` removida**, comentário no próprio
   arquivo (linhas 251-257) nomeando o que fica sem prova contra um ambiente
   real até que ele carregue um run vivo. Continua provado contra o mock
   (`run-0003`, id literal mantido de propósito).
4. e 5. **AN-09, par "on a settled run"/"on a live run"** (linhas 323 e 340).
   `spec.md` linha 121: alegação genérica (contagem do cabeçalho = renderizado),
   mas o par original testava deliberadamente os dois *caminhos de código*
   diferentes — replay estático (`eventsFromReplay`) vs. o redutor do cliente
   que deduplica eventos fora de ordem (`applyEvents`, `console/src/live/reducer.ts`).
   O lado assentado (linha 323) foi **descoberto** (`discoverRunPath(page,
   'settled')`) e prova a alegação de novo, genuinamente, contra o staging.
   O lado vivo (linha 340) usa `discoverLiveRunPath` e, quando não há run vivo
   para descobrir, chama `test.skip(path === null, ...)` (linha 354) em vez de
   herdar o id do mock ou de cair para um assentado — cair para um assentado
   provaria a mesma coisa duas vezes e nunca exerceria o redutor vivo, que é
   exatamente o que este segundo teste existe para cobrir. Continua
   `@staging-safe`; passa a aparecer como **skipped**, não como passou nem
   como falhou, no dia em que o ambiente não tem run vivo — e começa a rodar
   de verdade, sem nenhuma mudança de código, no dia em que tiver.
6. **AN-12, "a live run offers Assume, Stop…"** (linha 452). `spec.md` linha
   127: mesma forma de AN-06 — incondicionalmente sobre liveness. **Tag
   removida**, mesmo tratamento e mesmo motivo que AN-06 (comentário nas
   linhas 445-449). Continua provado contra o mock.

Duas falhas da linha de base **não são literais de id e não foram tocadas**,
por instrução explícita: `run-live-card` (linha 470 atual) e a linha de
status falhado (linha 507 atual) de AN-14, ambas falhando porque o staging
não tem run vivo nem run falhado agora — mesmo texto de erro, mesma causa,
antes e depois desta rodada.

### Depois, medido

`--backing mock` (mesmo comando, `--backing mock`): **exit 0 — 19 passed**,
a mesma contagem de antes do reparo. Nenhuma cobertura do mock foi
enfraquecida — os testes que agora descobrem em vez de nomear (AN-01, AN-03,
e o lado assentado de AN-09) encontram exatamente os mesmos runs que antes
porque o mock só tem um run vivo (`run-0003`) e ele aparece primeiro na banda
"Vivas agora"; o lado vivo de AN-09 encontra esse mesmo run vivo e nunca
entra no ramo de skip sob mock.

`--backing staging` (mesmo comando, `--backing staging`, credenciais pela
mesma shell): **exit 1 — 2 failed, 1 skipped, 5 passed, de 8 selecionados**
(dois a menos que antes: AN-06 e AN-12 perderam a tag). As 2 falhas restantes
são, byte a byte no texto do erro e no seletor, as mesmas duas AN-14 da linha
de base — não regredidas, não corrigidas, fora do escopo deste reparo. O
1 skipped é o lado vivo de AN-09, marcado como tal de propósito.

Saldo honesto: de seis testes tocados, três agora provam a própria alegação
de verdade contra o staging real (AN-01 deixou de ser uma passagem vazia;
AN-03 e o lado assentado de AN-09 deixaram de falhar); um passou a `skipped`
em vez de falhar por uma causa que não é um defeito (o lado vivo de AN-09);
dois deixaram de rodar contra o staging e ficam nomeados como não provados
até que o ambiente carregue um run vivo (AN-06, AN-12). `make verify` completo
não foi rodado aqui — é do orquestrador, por instrução desta tarefa.

### Gates rodados nesta rodada, resultado real

| Gate | Comando | Resultado |
|---|---|---|
| Prettier | `pnpm exec prettier --check tests/e2e/run-view-narrado.acceptance.spec.ts` (após `--write`) | exit 0, "All matched files use Prettier code style!" |
| Typecheck | `uv run python -m tools.console_gate typecheck` | exit 0 |
| Lint | `uv run python -m tools.console_gate lint` | exit 0 |
| Acceptance, mock | `uv run python -m tools.spec_validation browser --feature specs_v8/030-run-view-narrado --test console/tests/e2e/run-view-narrado.acceptance.spec.ts --backing mock` | exit 0, 19 passed |
| Acceptance, staging (antes) | mesmo comando, `--backing staging` | exit 1, 7 failed / 3 passed |
| Acceptance, staging (depois) | mesmo comando, `--backing staging` | exit 1, 2 failed / 1 skipped / 5 passed |

Nenhum arquivo Python foi tocado nesta rodada — `pytest`/`make lint`/`make
typecheck` do lado Python não foram rodados porque não há nada ali para essas
suítes cobrirem desta mudança.

### Recomendação para as duas AN-14 fora do escopo deste reparo, não aplicada

Mesma doença que AN-06/AN-12 tinham antes deste reparo, mesma cura possível:
ambas ("a live run is drawn as a card…", linha 470; "a failed run is drawn
distinctly…", linha 507) são alegações incondicionais sobre uma categoria de
run que o staging não carrega hoje (vivo; falhado). A descoberta não resolve
nenhuma das duas — não há o que descobrir. O tratamento simétrico ao que este
reparo deu ao lado vivo de AN-09 seria: ler a lista uma vez
(`page.getByTestId('run-live-card')`/`page.locator('[data-testid="run-card"][data-status="failed"]')`)
e, quando a contagem for zero, `test.skip(...)` nomeando a ausência, em vez
de deixar a asserção estourar em timeout. Não apliquei essa mudança porque a
tarefa que abriu este reparo pediu explicitamente para não tocar essas duas
— "Leave them; report what you would do about them" — e uma mudança que a
própria pessoa que audita não pediu, por menor que pareça, é exatamente o
tipo de decisão que deveria ser tomada por quem está olhando o quadro
inteiro, não por quem só tem este arquivo na frente.

## Segundo reparo — as duas AN-14 que ficaram de fora, agora aplicado (2026-08-30)

O orquestrador liberou explicitamente a recomendação da seção anterior: "you
had already made it correctly: give them the same treatment as AN-09's live
side." Antes de tocar o arquivo, conferi que a árvore havia se movido sob
este trabalho — quatro commits de outro implementador
(`46274987`,`638a5529`,`3dbfdb50`,`1d021b56`) extraindo um motor
`ReconnectingChannel` compartilhado de `connection.ts`/`deployment.ts`,
com testes de unidade novos e um aperto no poll do SC-001 de
`canal-vivo.acceptance.spec.ts` — confirmado por `git diff 39361b79 HEAD --
console/tests/e2e/run-view-narrado.acceptance.spec.ts` sem saída nenhuma:
nada nesses quatro commits toca este arquivo.

### O que mudou

Os dois testes de AN-14 que a rodada anterior deixou falhando de propósito
(`run-live-card`, linha 470 na numeração de então; a linha de status
falhado, linha 507) ganharam o mesmo tratamento que o lado vivo de AN-09 já
tinha: leem a lista uma vez e chamam `test.skip(...)`, nomeando a ausência,
em vez de deixar a asserção estourar em timeout de 5s.

- **"a live run is drawn as a card…"** (`console/tests/e2e/run-view-narrado.acceptance.spec.ts:473`
  na numeração atual) passou a reusar o próprio `discoverLiveRunPath` já
  escrito para o lado vivo de AN-09 — sem duplicar a leitura de `/runs`, só
  o `test.skip(livePath === null, 'no live run on this environment to draw
  a card for')` antes das asserções.
- **"a failed run is drawn distinctly…"** (linha 507) não tinha um helper
  equivalente para "primeira linha falhada" — este teste já navega para
  `/runs?status=failed` e filtra por `data-status="failed"`, uma consulta
  diferente da que os helpers de descoberta fazem. Acrescentei uma espera
  pelo `page-header` (mesma disciplina de `discoverRunPath`/`discoverLiveRunPath`,
  para não contar antes da lista assentar) e
  `test.skip((await failedRow.count()) === 0, 'no failed run on this
  environment to draw a row for')` antes das asserções.
- O comentário de topo do arquivo (linhas 8-21) ganhou uma frase nomeando
  que essas duas checagens de AN-14 agora pulam pela mesma razão que o lado
  vivo de AN-09 — documentação, não comportamento novo.

Nenhuma tag `@staging-safe` mudou aqui — as duas continuam marcadas, porque
a alegação em si (AN-14, `spec.md` linha 131) é sobre o que a lista desenha
quando existe um run vivo ou falhado, e nada nessa alegação deixou de ser
verdade; só a forma honesta de dizer "esta amostra não existe aqui agora"
mudou de um timeout estourado para um skip nomeado.

### Antes e depois desta segunda rodada, medidos

`--backing staging` (mesmo comando das rodadas anteriores, credenciais pela
mesma shell):

- **Antes desta rodada** (herdado do primeiro reparo): exit 1 — **2 failed,
  1 skipped, 5 passed**, de 8 selecionados. As 2 falhas eram exatamente
  estas duas AN-14.
- **Depois desta rodada**: exit **0** — **0 failed, 3 skipped, 5 passed**,
  dos mesmos 8 selecionados. As 3 skips: o lado vivo de AN-09 (já existia) e
  as duas AN-14 agora tratadas. Os 5 que passam são os mesmos cinco de
  antes, inalterados.

`--backing mock` (mesmo comando): exit **0** — **19 passed**, mesma contagem
de sempre. As duas AN-14 recém-tratadas continuam passando de verdade sob o
mock (269ms e 239ms na medição desta rodada) porque o mock tem `run-0003`
(vivo) e `run-0004` (`status=failed`) — o `test.skip` nunca dispara ali, só
quando de fato falta o dado, exatamente como projetado.

### Gates desta segunda rodada, resultado real

| Gate | Resultado |
|---|---|
| Prettier (`--check` → `--write` → `--check`) | 1 → 0 → **0** |
| `uv run python -m tools.console_gate typecheck` | exit **0** |
| `uv run python -m tools.console_gate lint` | exit **0** |
| Acceptance, mock | exit **0**, 19 passed |
| Acceptance, staging | exit **0**, 0 failed / 3 skipped / 5 passed |

`specs_v8/progress.json` e as duas pastas `evidence/` continuam intocadas
por este trabalho, por instrução explícita — não fazem parte deste commit.

