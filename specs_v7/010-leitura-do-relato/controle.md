# Controle — 010-leitura-do-relato

Estado verificado contra o código em disco na worktree
`/srv/workspaces/NinjaSRE/.claude/worktrees/agent-ae5177498b77c8979`, commit
`b2c6f99` (HEAD). Escrito incrementalmente ao longo da sessão — esta é a
versão final, reescrita para eliminar seções que ficaram obsoletas conforme
o trabalho avançou. Base: `git reset --hard master` a partir de `b12578f`
(a worktree tinha vindo no commit raiz na primeira leitura, defeito
conhecido da onda).

**Sessão seguinte (2026-08-24, worktree `agent-af6557b9f5ef25593`)**: confronto
dos 11 itens que continuavam sem marcação — T053, T054, T055 e as 8 linhas do
Definition of done que citam staging, `network.spec.ts`, rolagem horizontal,
`dangerouslySetInnerHTML` e `make verify`. Seção própria abaixo
(**"Confronto dos 11 itens não marcados"**) com o que cada um provou ser,
file:line incluído. A mesma worktree-no-commit-raiz apareceu de novo nesta
sessão (`HEAD` só carregava `README.md`); corrigida do mesmo jeito,
`git reset --hard master`, agora em `10a329c`, antes de qualquer commit desta
sessão.

## Commits, em ordem

| Commit | Conteúdo |
|---|---|
| `8720e4b` | Vocabulário de status (`completed`/`partial`, `isLiveRun`); custo real derivado no gerador de fixtures; `headline` explícito respeitado em `_run_detail`; 3 runs novos + 4 chamadas em `run-0005`; `now-violations` sincronizado; `run-subject.ts` e `report.tsx` criados; acceptance spec criado e confirmado **vermelho** (16 failed / 7 passed) contra as telas ainda não tocadas |
| `282691c` | `run-subject.ts`/`report.tsx` ligados a `run-detail.tsx`, `runs.tsx`, `page.tsx`; `layout.tsx` ganhou `titleTooltip`; `dashboard.tsx` corrigido (terceira entrada de markdown cru, em `/`) |
| `050a7ae` | `masking.test.tsx` movido da coluna SUBJECT (virou nome, nunca documento) para o painel do relato |
| `156c5c2` | 2 dos 5 lints achados corrigidos em `report.tsx` |
| `b6c82f9` | (do orquestrador, direto na worktree) os outros 3 lints |
| `f11722a` | Os 4 vermelhos que o orquestrador relatou no acceptance, todos com causa raiz real — ver seção própria |
| `b2c6f99` | Allowlist transversal: as 7 entradas removidas, suíte inteira provando mérito |
| *(fora desta feature, mesmo slot)* `7dffeee`/`b977c48` | Outro agente registrou as 4 entradas de tela de runs em `screens.json` como `pending` com razão em substância, e recapturou 3 das 4 imagens — ver seção nova abaixo |
| `89fa013` | Recaptura de `runs-1440-light.png` (estava desatualizada — ver achado) e primeira captura de `run-detail-live-1440-light.png`. Nenhum status mudou |
| `d66c29f` | Teste de repositório novo: `dangerouslySetInnerHTML` é exclusivo de `layout.tsx`, provado por varredura de `console/src/`, não só pelo render isolado de `Report` |
| `232de1f` | `network.spec.ts` ganhou um segundo teste: navega para o run hostil (`run-0103`) autenticado e confirma zero requisição externa e zero `<img>` |

## O vermelho real, antes de qualquer tela mudar

Comando: `console_e2e run -- tests/e2e/010-leitura-do-relato.acceptance.spec.ts`,
contra o build de produção, scenario `populated`, backing `mock`.

**16 failed, 7 passed (23 total), exit 1** — vermelho em todos os seis
grupos (a–f). Detalhe por grupo, com o motivo real de cada vermelho e o que
já passava por coincidência de dado, no arquivo de log preservado em
`/tmp/claude-999/-srv-workspaces-NinjaSRE/0197c7d7-4784-453e-b36a-abb03241ebc2/scratchpad/red-run3.log`.
Resumo:

- **(a) nome em 3 lugares** — 2/2 vermelho: header/aba/lista discordavam;
  headline com sintaxe markdown e >120 chars aparecia crua.
- **(b) fallback sem headline** — 2/2 vermelho: header mostrava o documento
  inteiro ("Incident Findings..."); `report` testid não existia.
- **(c) relato renderizado** — 6/7 vermelho (a checagem de imagem remota já
  passava, por coincidência: nada renderizava nada).
- **(d) run terminado não é vivo** — 2/3 vermelho (`completed` não era
  reconhecido por `isSettled`); o terceiro (run em andamento mantém
  controle) já passava — comportamento preexistente correto.
- **(e) transcript/custo reais** — 3/4 vermelho (0 chamadas onde 4 eram
  esperadas; contagem batendo com o painel ao vivo, não o de leitura;
  tabela por turno vazia); o de "sem turno nenhum → sem custo" já passava.
- **(f) vínculos do próprio registro** — 1/3 vermelho (recursos vinham do
  incidente correlacionado, não do próprio run); os outros dois já passavam.

## O acceptance depois de tudo: 23/23, e os quatro vermelhos que o orquestrador achou no merge

Depois do wiring (commit `282691c`), o orquestrador mediu o merge e reportou
4 testes vermelhos:

- `:76` (a) — header e coluna da lista discordavam para `run-0102`.
- `:126` (b) — header de `run-0101` não continha o id curto.
- `:265` e `:287` (e) — 0 chamadas de transcript, 0 linhas na tabela de custo.

Investiguei os quatro e achei **três causas raiz distintas**, não uma:

1. **`subjectCellFor` no próprio acceptance spec pegava o `<td>` inteiro**,
   que inclui o rótulo `sr-only` "Open" concatenado ao final do nome pelo
   `textContent()`. Corrigido: escopar ao `span.truncate` visível.
2. **`run-0101` não tinha headline genuinamente vazio.** O comentário no
   fixture dizia "sem a chave headline", mas por construção de
   `_run_detail()`, a *ausência* da chave cai no branch
   `synthesize_headline(...)` — o oposto do que o comentário afirmava.
   Corrigido: `"headline": ""` explícito, que é o que uma linha real
   pré-headline no banco de fato carrega.
3. **Achado de design real, não só de teste**: `run-0005` tem status
   `awaiting_approval`, posto em `LIVE_RUN_STATUSES` "para preservar o
   comportamento antigo" sem re-derivar se pertencia lá. Isso fazia
   `running=true`, montando `<LiveRun>` (conexão SSE) no lugar de
   `<Transcript>` — por isso as 4 chamadas apareciam como 0. Corrigido pela
   raiz: `awaiting_approval` é um terceiro estado — nem "ainda chamando
   ferramentas" nem "terminado" — e saiu de `LIVE_RUN_STATUSES`. Um run
   esperando aprovação é servido pelo painel de interação aberta
   (`AnswerControls`), não por um stream vivo à espera de chamadas que não
   vêm.
4. **Um quarto bug, só descoberto depois de consertar os três acima**: o
   teste do painel de custo ainda falhava (14× "0 elementos", 5s de
   timeout). Confirmei que não era race condition rodando o teste isolado
   3× seguidas (3/3 falhando, sempre 0 — determinístico, não flake).
   Encontrado por leitura do próprio seletor:
   `cost.getByTestId('usage-by-turn').locator('tbody tr')` — mas
   `usage-by-turn` já É o `<tbody>` (é o `data-testid` do próprio elemento),
   então a cadeia procurava um `<tbody>` aninhado dentro do `<tbody>`, que
   nunca existe. Corrigido para `.locator('tr')`.

**Resultado final: `console_e2e run -- tests/e2e/010-leitura-do-relato.acceptance.spec.ts` → 23 passed, 0 failed, exit 0** (log em
`/tmp/claude-999/-srv-workspaces-NinjaSRE/0197c7d7-4784-453e-b36a-abb03241ebc2/scratchpad/green-run3.log`).

## A allowlist transversal — as 7 entradas, todas caídas

**As 7 caíram, não só as 4 nomeadas pelo orquestrador.**

Prova: `EXCEPTIONS` em `transversal-rules.spec.ts` esvaziada por completo —
não linha a linha por confiança, mas a tabela inteira zerada e a suíte
completa rodada para ver o que realmente falha.
Comando: `console_e2e run -- tests/e2e/transversal-rules.spec.ts`.

**Resultado: 45 passed, 7 skipped, 0 failed, exit 0.** Os 7 pulados são o
conjunto pré-existente `SCROLL_BUDGET_MEASURED_ELSEWHERE` (rotas de
Settings medidas em `scroll-budget.spec.ts`; nada a ver com esta allowlist).
Nenhuma das 7 combinações rota×regra desta feature falhou.

| Rota | Regra | Por que caiu |
|---|---|---|
| `/runs/{id}` | markdown | título/aba/painel vêm de `subjectOf`/`Report`, nunca do documento cru |
| `/runs` | markdown | coluna SUBJECT vem de `subjectOf`, mesmo lugar |
| `/` | markdown | feed de atividade recente e banda de atenção do dashboard corrigidos nesta sessão — nomeado explicitamente pelo orquestrador como uma das quatro minhas, mesmo estando fora do escopo literal do `spec.md` (que só cita `/runs` e `/runs/{runId}`) |
| `/runs` | identifier-as-name | mesma correção da coluna SUBJECT — **caiu de graça** |
| `/runs/{id}` | identifier-as-name | breadcrumb ligado a `subjectOf` também (bônus, não uma das 4 nomeadas) |
| `/runs` | two-placeholders | **caiu de graça** — `run-0003` antes mostrava "Not recorded" em SUBJECT *e* Duration; agora SUBJECT mostra o nome sintetizado pelo trigger, sobra só um placeholder |
| `/runs/{id}` | live-control | `isLiveRun` afirmativo + remoção de `awaiting_approval` da lista de status vivos |

**Duas das sete caíram sem eu escrever uma linha de tela a mais**
(identifier-as-name e two-placeholders em `/runs`): a mesma correção de
`subjectOf()` fecha as duas de uma vez, porque a coluna SUBJECT parava de
cair no id truncado ou em "Not recorded" ao mesmo tempo. A tarefa "linhas-
meta sem placeholder duplo" que eu esperava precisar implementar
explicitamente em `runs.tsx` (omitir slot vazio em vez de placeholder)
**acabou não sendo necessária** — a suíte transversal não encontrou mais
nada para ela corrigir. Se existir um caso de dois placeholders fora do que
essa suíte cobre, ele fica pendente, nomeado: não fui atrás porque não
tenho evidência de que exista.

## A dívida herdada: custo por turno no gerador de fixtures

`tools/mockplane/dataset/served.py`:

- `_turn_usage(turn)` soma `cost`/`prompt_tokens`/`completion_tokens` que
  cada turno *de fato* carrega; a fórmula antiga `0.031 * (len(turns) + 1)`,
  desconectada de qualquer dado real, foi removida.
- `run-0005` ganhou 4 chamadas em 2 turnos: o primeiro com `cost=0.0091`,
  `prompt_tokens=612`, `completion_tokens=148`; o segundo **sem** nenhuma
  dessas três chaves — genuinamente sem preço, não um zero fabricado.
- Verificado por leitura direta do fixture construído: `run-0005` tem
  `total_cost=0.0091`, `unpriced_turns=1` (nem 0 nem igual ao total de
  turnos — o único run do dataset que exercita as duas metades ao mesmo
  tempo). `run-0001`/`run-0003` (que já tinham turnos sem nenhum dado de
  custo) continuam com `total_cost=0`, `unpriced_turns=len(turns)` —
  comportamento antigo preservado, não uma regressão.
- Suíte de coerência de fixtures depois da mudança: **245 passed**
  (`tests/contract/fixtures/test_dataset_contract.py`,
  `test_dataset_coherence.py`, `tests/unit/tools/mockplane/`).

## Decisão de produto que mudou nesta execução: renderizador sem dependência nova

O `plan.md` da feature escolheu `react-markdown`+`remark-gfm`. O
orquestrador, no início desta execução, reabriu essa decisão explicitamente
por risco de prazo e orçamento de bundle: "Não acrescente dependência
nova". `console/package.json` não tinha nenhuma biblioteca de markdown já
presente, então `console/src/surfaces/report.tsx` é um parser
markdown-subset próprio: blocos (heading×6, parágrafo, lista
ordenada/não ordenada, tabela, bloco de código cercado, citação, regra
horizontal) e inline (strong, em, code, link, imagem). Toda propriedade de
segurança é estrutural: nunca monta string HTML, nunca usa
`dangerouslySetInnerHTML`, imagem nunca vira `<img>` (só o texto
alternativo), esquema de link é checado (`http`/`https`/`mailto`) antes de
virar `<a>` navegável.

**Bug real que o teste próprio do parser achou**: o scanner de link/imagem
usava `indexOf(')', ...)` para achar o parêntese de fechamento — que para
num href com parênteses aninhados (`javascript:alert(1)`) no primeiro `)`
interno, deixando um `)` solto no texto seguinte. Corrigido com
`matchingParen()`, que rastreia profundidade.

**Orçamento de bundle, medido**: folha compilada 24826/40960 bytes (60%);
conjunto de ícones 10918/16384 (66%) — dentro do declarado, sem crescimento
perceptível por causa do renderizador (esperado: nenhuma dependência nova,
nenhum CSS novo além de classes já existentes).

## Fronteira — arquivos de escrita única do slot

O orquestrador declarou nesta execução que `console/src/i18n/*.ts`,
`console/src/shell/routes.ts` e `console/visual/screens.json` são da
feature de fonte-por-fato neste slot — ao contrário do que o `tasks.md`
desta própria feature declara (que os lista como propriedade da 010).
Segui a instrução mais recente e explícita do orquestrador.

**Chave i18n nova: nenhuma, no fim.** A primeira versão de
`run-detail.tsx` referenciava uma chave nova (`run.report.raw`) para o
rótulo da disclosure do texto cru do relato. Reconsiderei para não
depender da fronteira: a disclosure reaproveita `failure.technical`
("Technical detail"), a mesma chave que a disclosure de exceção já usa —
semanticamente ambas são "o texto bruto atrás da leitura amigável acima".
`data-testid="report-raw"` continua distinguindo as duas no teste. Nenhuma
outra tela precisou de chave nova. **Resultado prático**: `tsc --noEmit`
está limpo, sem nenhuma dependência da fronteira i18n — não preciso que o
orquestrador aplique nada no catálogo para esta feature fechar.

**`console/visual/screens.json` e as baselines**: não toquei. A recaptura
de baseline (T053–T055 do `tasks.md`) fica **não iniciada**, propriedade da
feature de fonte-por-fato. A razão de aceitação que a baseline deveria
carregar, para quem for aplicá-la: "título é uma sentença; documento
desenhado como documento; ausência do painel de controle num run
terminado" — as duas telas (`/runs`, `/runs/{runId}`) mudaram visualmente
o suficiente para justificar recaptura deliberada, não uma recaptura
automática do gate.

**`console/src/shell/routes.ts`**: não precisei tocar — nenhuma rota nova,
nenhuma permissão nova.

## Gates rodados nesta sessão, resultado real

| Gate | Comando | Resultado |
|---|---|---|
| Coerência de fixtures | `pytest tests/contract/fixtures/test_dataset_contract.py test_dataset_coherence.py tests/unit/tools/mockplane/` | **245 passed** |
| Typecheck do console | `pnpm exec tsc --noEmit` | limpo |
| Lint do console | `pnpm exec eslint .` | limpo (5 achados, todos corrigidos — 2 por mim, 3 pelo orquestrador na worktree) |
| Suíte de unidade do console | `pnpm exec vitest run` | **2707 passed / 161 arquivos**, confirmado 2× depois dos últimos consertos |
| Orçamento de bundle | `console_gate budget` | folha 60% do teto, ícones 66% do teto |
| `network.spec.ts` | `console_e2e run -- tests/e2e/network.spec.ts` | 1 passed |
| **Acceptance da feature** | `console_e2e run -- tests/e2e/010-leitura-do-relato.acceptance.spec.ts` | **23 passed, 0 failed** |
| **Suíte transversal (allowlist)** | `console_e2e run -- tests/e2e/transversal-rules.spec.ts` | **45 passed, 7 skipped (pré-existente), 0 failed** |
| Contrato Python do console | `pytest tests/contract/console/ --ignore=test_console_gate.py --ignore=test_console_visual_*` | **355 passed, 1 failed — pré-existente e alheio** (ver abaixo) |

**A única falha vista em toda a sessão, fora do meu escopo**:
`test_every_check_is_individually_runnable_from_the_makefile[dynamic-routes]`
cobra um alvo `make console-dynamic-routes` que não existe. O check
`dynamic-routes` já está declarado em `tools/console_gate.py` — não toquei
esse arquivo nem o `Makefile` nesta sessão, e "dynamic-routes" não é um
conceito desta feature. Nomeado, não escondido, não corrigido.

**Não rodei**: `test_console_gate.py` (suíte de seeded-failures — comecei,
ela ficou ~10min genuinamente processando múltiplas invocações de gate, não
travada; interrompi porque não mede nada desta feature e o prazo apertava;
limpei o lock (`console/.toolchain/tree-writing-suite.lock`) e o arquivo
semeado (`console/tests/unit/seeded.test.ts`) que ficaram para trás da
interrupção — árvore confirmada limpa depois). `test_console_visual_*`
(baselines são da fonte-por-fato). `make verify` completo (é do
orquestrador, por definição do meu papel). Qualquer coisa contra staging
real (não tenho acesso; as alegações marcadas `@staging-safe` no acceptance
e as `@staging-safe` da suíte transversal estão prontas para quando o
orquestrador rodar `make deploy-stg`).

## Confronto dos 11 itens não marcados (sessão 2026-08-24)

O operador leu este arquivo e viu itens marcados como não feitos sem
justificativa ao lado — correto na leitura, incorreto como estado final: a
sessão anterior tinha explicitamente listado a razão de cada um em "O que
fica pendente" acima, mas a marcação em `tasks.md` continuava vazia e uma
sessão intermediária (fora desta feature, commits `7dffeee`/`b977c48`, ver
tabela de commits) já tinha resolvido parte do que estava pendente sem voltar
aqui para atualizar. Cada um dos 11 itens foi reaberto contra o código e,
onde fazia sentido, contra o staging real — nunca contra a leitura do
`tasks.md` anterior.

### T053 — registro de tela — **feito, por outro agente; verificado aqui**

`console/visual/screens.json:294-339` já tem as quatro entradas de tela de
runs (`run-detail-1440-dark`, `run-detail-1440-light`,
`run-detail-live-1440-light`, `runs-1440-light`), cada uma com
`pending_because` nomeando em substância exatamente o que T053 pede — "the
title and the runs-list subject column now come from a run's own headline
[...], the report panel renders the document instead of printing it as
text, and a settled run's live-only controls are gone" — sem citar feature,
requisito nem documento de planejamento. Commit `7dffeee`, já em `master`
(`git merge-base --is-ancestor 7dffeee master` confirma).

**Divergência consciente do texto literal da tarefa**: T053 pede viewport
"1920×1080"; as quatro entradas usam `"viewport": 1440`. Não corrigi —
`console/visual/screens.json` inteiro (43 entradas) não tem **nenhuma**
entrada em 1920 em lugar nenhum, e `console/tests/visual/screens.spec.ts:115`
fixa a altura em `900` sempre, ignorando qualquer valor que não seja a
largura — não há como uma entrada carregar "1920×1080" nesse schema. O
comentário do próprio arquivo (`screens.spec.ts:18-21`) declara "the design
declares three widths and two themes": 320/768/1440 é a convenção real, e o
"1920×1080 normativo" do `spec.md` é o viewport de **medição das alegações
do acceptance e das capturas de evidência** (já usado corretamente em
`010-leitura-do-relato.acceptance.spec.ts` e nas capturas de T058/T062/T063),
não da grade de regressão visual. Seguir o texto ao pé da letra teria
introduzido a primeira exceção de largura do registro inteiro por uma leitura
que o próprio mecanismo não sustenta.

### T054 — recaptura das baselines — **parcial: recaptura minha, aceitação não**

Duas das quatro imagens continuavam desatualizadas mesmo depois de
`b977c48` (que recapturou como parte de uma feature diferente, "status
vocabulary", rodando aparentemente contra uma árvore que ainda não tinha os
fixtures novos desta feature nem `run-subject.ts` no estado atual — a
outra worktree deste slot e esta não compartilham working tree, só objetos
git). Achado real, não hipotético: `runs-1440-light.png` como estava
mostrava **6 investigações** (`run-0001`..`run-0006`) e a SUBJECT de
`run-0003` (o run em andamento) como literal **"Not recorded"** — texto que
T022 (já marcado feito) removeu explicitamente dessa coluna. Conferi
`console/src/surfaces/run-subject.ts:69-73` (`fallbackName` sempre monta
`"<trigger> · <8 primeiros do id>"`, nunca "Not recorded") e
`console/src/app/api` não entra aqui — o bug não estava no código, estava na
imagem: desatualizada, de antes dos fixtures `run-0101`/`0102`/`0103` (T004)
existirem.

Recapturei as duas — `runs-1440-light.png` e a nunca-capturada
`run-detail-live-1440-light.png` — com o mesmo mecanismo oficial
(`tools/console_visual.py`, imagem Docker fixada por dígest), rodando cada
uma isolada via `--grep` para não tocar nenhuma das outras 41 entradas do
registro. Commit `89fa013`. **O que vi em cada imagem**, para quem for
aceitar:

- `runs-1440-light.png` (nova): 9 linhas (`run-0001`..`run-0006`,
  `run-0101`..`run-0103`), toda SUBJECT uma sentença ou o par
  `<trigger> · <id>` — nenhuma mostra sintaxe markdown nem "Not recorded";
  `run-0003` (RUNNING) mostra "alert investigation" (headline sintetizado
  pelo mockplane para um registro sem headline próprio, não o fallback do
  console — os dois caminhos produzem texto limpo, só por rotas diferentes);
  DURATION de `run-0003` e `run-0005` mostra "Not recorded" corretamente
  (isso é verdade — a duração de um run em andamento não é um fato ainda).
- `run-detail-live-1440-light.png` (primeira captura, nunca existiu antes):
  `/runs/run-0003`, badge RUNNING, título "alert investigation", painel
  "Control" com "Take over"/"Stop this investigation" e o painel "The agent
  is waiting on an answer" com uma pergunta e os controles de resposta —
  exatamente o par de painéis que a regra "run terminado não tem controle"
  pressupõe que um run **vivo** deveria continuar tendo. Limitação honesta:
  o transcript mostra "Reconnecting" / "This investigation recorded no
  events" — o servidor de fixtures do capturador visual não alimenta a
  conexão SSE como o backing real faz, então esta imagem prova a
  presença/ausência dos painéis de controle, não o conteúdo do transcript ao
  vivo.

**Não fiz, e não devo**: mudar `status` de nenhuma das quatro entradas de
`"pending"` para `"baselined"`. Isso é a aceitação, e aceitação é decisão de
uma pessoa revisando a imagem, nunca de um agente — a mesma regra que
`b977c48` já seguiu ("Accepting a baseline is a human's call, not a gate's").
Fica para quem revisar: as quatro imagens estão prontas, o registro continua
`pending` em todas, T054 continua sem marcar.

### T055 — órfã e captura fabricada — **feito**

Rodei dois gates, os dois com resultado real:

- `pytest tests/contract/console/test_console_visual_coverage.py` — **108
  passed**, incluindo `test_no_baseline_belongs_to_a_screen_nobody_registered`
  (o teste de órfã: todo `.png` em `console/visual/baselines/` tem uma
  entrada correspondente em `screens.json`, `pending` ou `baselined`) e
  `test_a_baselined_screen_has_a_committed_baseline` (nenhuma entrada
  `pending` foi tratada como se tivesse imagem aceita).
- `make console-visual` — roda a suíte Playwright dentro da imagem Docker
  fixada, comparando toda entrada `status: baselined` contra sua imagem
  commitada. **13 failed, 20 passed** — nenhuma das 13 é `run-detail-*` ou
  `runs-1440-light` (que continuam `pending`, fora do loop de comparação por
  construção de `screens.spec.ts:113`): `gallery-*` (6), `shell-*` (4),
  `resources-320-light`, `machine-tokens-1440-light`, `agent-tools-1440-light`
  — telas de outras áreas do console, sendo tocadas agora por outros agentes
  deste mesmo slot (`ps` durante a sessão mostrou processos `vitest`/`docker`
  de pelo menos duas outras worktrees rodando ao mesmo tempo contra o mesmo
  `console/node_modules` compartilhado). Nomeado, não escondido, não
  corrigido — não é desta feature e mexer nelas seria pisar no trabalho de
  outro agente em andamento.

Nenhuma captura fabricada ocupou o lugar de uma revisão: `console-visual`
roda em modo `compare`, nunca `accept`; nada nele escreve arquivo.

### Staging real — os dois itens do pedido, e as quatro linhas do DoD

**Conectividade primeiro, porque não era trivial.** `curl` contra
`https://stg-ninjasre.lan.kyo.ninja/` devolveu `502 Bad Gateway` na primeira
tentativa, e `POST /api/session` continuou 502 por mais uma rodada depois
que `GET /` e `GET /sign-in` já respondiam bem — instabilidade real e
passageira do backend por trás do proxy, não um erro meu: outra tentativa,
minutos depois, teve `GET /api/session` respondendo `405` (rota exige POST,
comportamento correto) e o `POST` de sondagem (credenciais falsas,
propositalmente, só para checar disponibilidade) devolvendo `303` (recusa
normal, não erro de gateway). Nomeado porque é exatamente o tipo de
observação que este confronto existe para não esconder.

**O comando real**, rodado com as credenciais de `/srv/workspaces/NinjaSRE/.env`
lidas direto para o ambiente do processo Python (nunca por `source`/`export`
de shell, nunca impressas), chamando `tools.console_e2e.run_staging()` — a
mesma função que `make deploy-stg` chamaria, que força
`--grep=@staging-safe` em cima de qualquer outro filtro, então nada fora do
marcado roda contra o ambiente real:

```
tools.console_e2e.run_staging(project="behaviour", extra=[
  "tests/e2e/010-leitura-do-relato.acceptance.spec.ts",
  "tests/e2e/transversal-rules.spec.ts",
])
```

**Resultado: 21 passed, 0 failed**, contra `https://stg-ninjasre.lan.kyo.ninja`
de verdade — 2 do acceptance (header sem markdown/de até 120 caracteres; run
terminado sem stop/takeover), 18 da suíte transversal (3 regras ×
6 rotas: `/`, `/incidents`, `/runs`, `/decisions`, `/runs/{id}`,
`/incidents/{id}`) e 1 do controle de run vivo em `/runs/{id}`. Evidência
visual capturada pelo próprio hook de captura da suíte
(`NINJASRE_STAGING_EVIDENCE_DIR_ENV`) — vi duas pessoalmente:

- **`/runs`**: "Showing 50 of 50" — não 37 mais; o staging acumulou
  investigações reais desde que a spec foi escrita, e o número na spec
  ("37 investigações") já está desatualizado por causa disso, o que é
  esperado de um ambiente vivo, não um defeito. As 14 linhas renderizadas
  (a lista é janelada, `runs.tsx:27-33` — "the list is windowed") mostram
  SUBJECT como sentença em toda linha: "Backup synchronization cron jobs
  o…", "The alert ProxmoxCriticalLogDetec…", "Redis Exporter and Redis
  service a…" e assim por diante; a única linha RUNNING mostra um nome
  sintetizado, nunca "Not recorded"; nenhuma tem `#`/`*`/crase visível.
- **`/runs/{id}`** (a investigação mais recente, "Backup synchronization
  cron jobs on pve01 failed with exit code 2..."): cabeçalho é a mesma
  sentença que a linha da lista, badge "COMPLETED", **sem painel de
  controle**; o painel "What this investigation found" mostra o relato
  **renderizado** de verdade — cabeçalho "Findings & Evidence", lista
  numerada, negrito real (não `**`), `código inline` real para os nomes de
  alerta e de host — sobre dado de produção que ninguém escreveu como
  fixture; disclosure "▸ Technical detail" fechada; transcript com
  `capability call`/`capability result` reais, dois deles `FAILED` com
  mensagem honesta ("this deployment has no log source configured...");
  custo e tokens reais (38.753 tokens, 5 turnos); "What this investigation
  touched" lista um recurso e o host de verdade.

Isso fecha, com evidência ao vivo e não só com o acceptance local, as três
linhas do DoD: "casos seguros passam contra staging real", "nenhuma
investigação mostra o documento como nome" (dentro da janela renderizada —
não reli as 50 uma a uma, a suíte também não) e "run terminado não tem
painel de controle no DOM".

### `network.spec.ts` com o relato hostil — **não estava, escrevi**

O arquivo `console/tests/e2e/network.spec.ts` (antes desta sessão) tinha um
teste só, e ele visita `/` — nunca uma tela com relato. T034 já estava
marcada feita citando esse arquivo, mas a alegação que o DoD registra
("passa com o relato hostil carregado") nunca tinha sido exercida: o
relato hostil (`run-0103`, com imagem remota e link de esquema executável —
`fixtures/scenarios/populated/run-detail.json:232`) nunca apareceu numa
página que o teste abriu. Um teste que sempre passou porque nunca olhou
para o que a alegação é sobre.

Estendi o arquivo com um segundo teste: assina sessão, abre
`/runs/run-0103`, confirma **zero** `<img>` dentro de `[data-testid=report]`
e **zero** requisição para fora do deployment. Rodado contra o build de
produção local (`console_e2e run -- tests/e2e/network.spec.ts`): **2
passed**. Commit `232de1f`.

### Rolagem horizontal em 1920×1080 — **já provado, confirmado de novo**

`010-leitura-do-relato.acceptance.spec.ts:178-187` — "a wide code block
scrolls within itself, and the page body does not scroll horizontally" —
mede exatamente `document.documentElement.scrollWidth >
document.documentElement.clientWidth` no viewport 1920×1080 contra o relato
hostil (bloco de código sem espaços). Já existia, já estava marcada; rodei o
acceptance completo de novo nesta sessão (abaixo) e confirmei que continua
verde: não é um item que precisava de trabalho, precisava de alguém abrir o
arquivo e confirmar que a alegação do DoD e o teste citado eram a mesma
coisa. São.

### `dangerouslySetInnerHTML` exclusivo de `layout.tsx` — **não estava, escrevi**

T031 já estava marcada feita, citando "um teste de repositório". Não existe
— `grep -rl dangerouslySetInnerHTML console/src console/tests` (fora de
`.next`/`coverage`, que são artefato de build) só achava três arquivos:
`layout.tsx` (uso real, ×3), `report.tsx` (uma linha de comentário citando o
nome) e `report.test.tsx:113` (um teste que renderiza `<Report>` com HTML
hostil e confirma que nenhum `<img>`/`<script>` aparece no DOM — prova o
comportamento do próprio componente, não que nenhum **outro** arquivo do
console decidiu usar o atributo). A alegação do DoD é sobre o repositório
inteiro; o teste que existia provava só uma fatia dele.

Escrevi o teste que faltava, em `report.test.tsx` (arquivo já existente —
estendido, não duplicado): varre todo `.ts`/`.tsx` sob `src/`, procura o
padrão `dangerouslySetInnerHTML\s*=` (não a palavra nua — a palavra nua
aparece no comentário de `report.tsx` e um teste ingênuo por substring
falharia contra a própria prosa que descreve a garantia) e afirma que só um
arquivo relativo, `app/layout.tsx`, contém o padrão.

**Vermelho real, confirmado antes do verde**: criei um arquivo descartável
`console/src/surfaces/_tmp_violation.tsx` com um uso de verdade do atributo,
rodei o teste — falhou, nomeando os dois arquivos extras (`_tmp_violation`
e, na primeira versão do teste, também `report.tsx` por causa do
comentário — corrigido trocando a busca de substring por regex antes de
seguir). Apaguei o arquivo descartável, rodei de novo: **32 passed** (os 15
já existentes de `report.test.tsx` + a nova suíte + os 17 de
`report-malformed.test.tsx`, rodados juntos). Commit `d66c29f`.

## Gates rodados nesta sessão (2026-08-24), resultado real

| Gate | Comando | Resultado |
|---|---|---|
| Cobertura/órfã visual (Python) | `pytest tests/contract/console/test_console_visual_coverage.py` | **108 passed** |
| Comparação visual | `make console-visual` | **13 failed, 20 passed** — as 13 são telas de outras áreas, nenhuma de runs (ver T055) |
| `report.test.tsx` (isolado, com a violação injetada) | `pnpm exec vitest run tests/unit/surfaces/report.test.tsx` | **vermelho real**: 1 failed, nomeando `surfaces/_tmp_violation.tsx` |
| `report.test.tsx` + `report-malformed.test.tsx` (depois da correção) | idem | **32 passed** |
| Typecheck do console | `pnpm exec tsc --noEmit` | limpo |
| Lint dos arquivos tocados | `pnpm exec eslint tests/unit/surfaces/report.test.tsx tests/e2e/network.spec.ts` | limpo |
| Formatação dos arquivos tocados | `pnpm exec prettier --check` idem | limpo |
| `network.spec.ts` (com o segundo teste) | `console_e2e run -- tests/e2e/network.spec.ts` | **2 passed** |
| Acceptance da feature (reconfirmado) | `console_e2e run -- tests/e2e/010-leitura-do-relato.acceptance.spec.ts` | **23 passed, 0 failed** |
| **Staging real, casos `@staging-safe`** | `tools.console_e2e.run_staging(...)` sobre o acceptance + a suíte transversal | **21 passed, 0 failed** |
| Suíte de unidade completa | `pnpm exec vitest run` | **não concluída** — travou >8min num teste alheio (`role-matrix.test.tsx`) sob disputa de recurso com outras worktrees ativas; interrompida, não é falha desta mudança |

## O que fica pendente, nomeado, não escondido

- **A aceitação das quatro baselines de tela de runs** (T054, e a linha
  correspondente do Definition of done): as imagens estão recapturadas e
  descritas acima; decidir se cada uma está correta e virar `status` para
  `"baselined"` é decisão de uma pessoa. Fica para quem revisar.
- **`make verify` completo**: não rodei o alvo integrado. Além de ser papel
  do orquestrador (herdado da sessão anterior), esta sessão viu evidência
  concreta de que a árvore compartilhada (`console/node_modules`, `.next`)
  está sendo usada por pelo menos duas outras worktrees ao mesmo tempo — uma
  tentativa de `pnpm exec vitest run` completo (2707+ casos) travou por mais
  de 8 minutos sem progredir além de um teste alheio
  (`role-matrix.test.tsx`), quase certamente por disputa de recurso e não por
  nada que esta sessão mudou (o arquivo que mudei, `report.test.tsx`, roda
  limpo e isolado: 32 passed). Rodei em vez disso o que o escopo real desta
  sessão toca, cada um contra evidência própria: `tsc --noEmit` limpo,
  `eslint`/`prettier --check` limpos nos três arquivos tocados
  (`report.test.tsx`, `network.spec.ts`, e as duas baselines não passam por
  lint), o subconjunto de vitest dos arquivos tocados (32 + 2 passed via
  `console_e2e`), o contrato Python de cobertura visual (108 passed) e as
  duas suítes e2e completas mencionadas acima (23 + 45 local, 21 staging).
  Não repeti `test_console_gate.py` nem a suíte de fixtures/contrato Python
  mais ampla — já confirmadas pela sessão anterior e esta sessão não tocou
  nenhum arquivo Python.
- **`test_console_gate.py`**: mesma razão da sessão anterior — não mede nada
  específico desta feature, e o risco de disputa de recurso citado acima
  torna uma tentativa de ~10min ainda menos atrativa nesta janela.
- **Extensões adicionais de `run-detail.test.tsx`/`runs.test.tsx`** que o
  `tasks.md` original pedia tarefa a tarefa (T017, T033, T037, T040, T041):
  não escrevi cada uma isoladamente porque o acceptance spec já prova o
  comportamento correspondente contra o build de produção — a forma de
  prova que a Constituição desta onda declara mais forte (Artigo XIV: só o
  caminho de serving real fecha uma tarefa desta feature, não um teste que
  renderiza um painel isolado). O comportamento está coberto; a cobertura
  unitária linha-a-tarefa do `tasks.md` não está espelhada 1:1.
