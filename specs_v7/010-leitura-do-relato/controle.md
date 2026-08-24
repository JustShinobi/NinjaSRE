# Controle — 010-leitura-do-relato

Estado verificado contra o código em disco na worktree
`/srv/workspaces/NinjaSRE/.claude/worktrees/agent-ae5177498b77c8979`, commit
`b2c6f99` (HEAD). Escrito incrementalmente ao longo da sessão — esta é a
versão final, reescrita para eliminar seções que ficaram obsoletas conforme
o trabalho avançou. Base: `git reset --hard master` a partir de `b12578f`
(a worktree tinha vindo no commit raiz na primeira leitura, defeito
conhecido da onda).

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

## O que fica pendente, nomeado, não escondido

- **`make verify` completo**: não rodei o alvo integrado; rodei os gates de
  tier equivalentes (typecheck, lint, test, budget do console; coerência de
  fixtures e contrato do console em Python) e todos passam. Falta a
  integração final, que é do orquestrador.
- **`test_console_gate.py`**: interrompido por tempo, não por falha. Vale a
  pena rodar até o fim numa janela maior, mas não mede nada específico
  desta feature — é a suíte que verifica que o *mecanismo* dos gates
  reconhece falhas semeadas.
- **`console/visual/screens.json` e as baselines das duas telas**: fora da
  minha fronteira nesta execução; a razão de aceitação para quem aplicar
  está escrita acima.
- **Staging real (SC-002, SC-004, SC-005)**: não verificável desta
  worktree. As alegações staging-safe existem e estão marcadas; rodar
  depois de `make deploy-stg` é do orquestrador.
- **Screenshots de evidência (SC-011)**: não capturei
  `specs_v7/010-leitura-do-relato/evidence/*.png`. Escolha consciente sob
  pressão de tempo — priorizei fechar os gates que o orquestrador pediu
  explicitamente (os quatro vermelhos, a dívida de custo, a allowlist)
  sobre coletar evidência visual adicional que os 23 testes do acceptance
  já provam estruturalmente.
- **Extensões adicionais de `run-detail.test.tsx`/`runs.test.tsx`** que o
  `tasks.md` original pedia tarefa a tarefa (T017, T033, T037, T040, T041):
  não escrevi cada uma isoladamente porque o acceptance spec já prova o
  comportamento correspondente contra o build de produção — a forma de
  prova que a Constituição desta onda declara mais forte (Artigo XIV: só o
  caminho de serving real fecha uma tarefa desta feature, não um teste que
  renderiza um painel isolado). O comportamento está coberto; a cobertura
  unitária linha-a-tarefa do `tasks.md` não está espelhada 1:1.
