# Controle — 010-leitura-do-relato

Estado abaixo verificado contra o código em disco nesta worktree
(`/srv/workspaces/NinjaSRE/.claude/worktrees/agent-ae5177498b77c8979`), commit
`8720e4b` em diante. Escrito incrementalmente — a versão em disco é o que já
foi provado, nunca uma intenção. Base: `git reset --hard master` a partir de
`b12578f` (a worktree tinha vindo no commit raiz, defeito conhecido da onda).

## PARADA LIMPA #2 — 87% da janela, teto ~15min

Commits até `156c5c2`. `masking.test.tsx` já corrigido (commit `050a7ae`,
mudou de ler a coluna SUBJECT para ler o painel do relato em run-detail —
a coluna virou nome, nunca mais o documento cru, exatamente a propriedade
desta feature). Suíte de unidade inteira: **2707/2707 passed**. `eslint`
achou 5 problemas; 2 corrigidos (`report.tsx`: acesso indexado
`string|undefined`, `border-l-2` fora da escala → `edge
border-{y,r}-0`); **3 pendentes, não tocados**: template literal com
`number` em `010-leitura-do-relato.acceptance.spec.ts:82,106`
(provavelmente `formatCount`/interpolação de `drawn`/contagem — trocar por
`String(...)`), e `report.test.tsx:57` usa `https://example.test/...`
que a regra `no-restricted-syntax` (nenhuma origem de terceiro) rejeita —
precisa do mesmo domínio `.invalid` que já uso no fixture hostil
(`verdant.example.invalid` ou similar), não `.test`.

**Não rodei**: rebuild do console nem o acceptance spec de novo desde os
commits de wiring — é o próximo passo, depois de fechar os 3 lints
restantes. Não rodei a suíte transversal (allowlist) ainda.

## Commits desta feature

| Commit | Conteúdo |
|---|---|
| `8720e4b` | `feat(console): derive real per-turn cost, name a run's status vocabulary honestly` — status.ts (completed/partial/isLiveRun), served.py (custo real derivado, headline explícito respeitado, 3 runs novos, 4 chamadas em run-0005), now-violations/runs.json sincronizado, run-subject.ts e report.tsx **criados mas ainda não ligados a nenhuma tela**, acceptance spec criado e confirmado vermelho contra as telas não modificadas |
| `282691c` | `feat(console): wire the run's own name and rendered report into the screens` — run-subject.ts/report.tsx ligados a `run-detail.tsx` (título, breadcrumb, painel do relato, vínculos por `touched_resources`, `isLiveRun`), `runs.tsx` (coluna SUBJECT, removido fallback morto "Not recorded"), `page.tsx` (aba), `layout.tsx` (`PageHeader` ganhou `titleTooltip`), `dashboard.tsx` (feed de atividade recente e banda de atenção — **terceira entrada de markdown cru, em `/`**, corrigida; taxa de sucesso agora por `roleFor` em vez de string literal), bug real achado pelo teste próprio do `report.tsx` (parênteses aninhados em `javascript:alert(1)` — corrigido com `matchingParen`) |

## Vermelho real, capturado antes de qualquer tela mudar

Comando: `uv run python -m tools.console_e2e run -- tests/e2e/010-leitura-do-relato.acceptance.spec.ts --reporter=list`,
contra o build de produção (`uv run python -m tools.console_gate build`),
scenario `populated` (padrão), backing `mock`.

**Resultado: 16 failed, 7 passed (23 total), exit 1.** Os 16 vermelhos reais,
por grupo:

- **(a) nome** — 2/2 vermelho: header/aba/lista não concordavam e continham
  sintaxe markdown (`run-0102`, headline com ênfase e comprimento > 120);
  tooltip do recorte ausente.
- **(b) fallback sem headline** — 2/2 vermelho: header de `run-0101` continha
  o documento cru ("Incident Findings..."); painel do relato inexistente
  (`getByTestId('report')` não resolvia).
- **(c) relato renderizado** — 6/7 vermelho (o teste de "imagem remota não
  requisitada" já passava, por coincidência: hoje nada renderiza `<img>`
  porque nada renderiza nada). Vermelhos reais: `h3/h4` ausente para
  "Evidence gathered", lista/tabela ausentes, `<pre>` ausente (overflow),
  link `javascript:` ausente **mas texto também ausente** (nada renderizado),
  `<script>` — o teste falhou porque o texto não aparecia (painel vazio),
  disclosure `report-raw` inexistente.
- **(d) run terminado** — 2/3 vermelho: painel de controle presente e texto
  de conexão ociosa presente em `run-0101` (`completed` não reconhecido por
  `isSettled` antes desta feature); `live-run` testid presente quando não
  deveria. O terceiro teste ("run em andamento mantém controle") já passava
  — comportamento preexistente correto, preservado.
- **(e) transcript/custo** — 3/4 vermelho: `run-0005` mostrava 0 chamadas
  (mensagem real: `Received: 0` onde esperado `4`); contagem do cabeçalho
  batendo com o vazio (`"Investigation transcript11 eventsReconnecting..."` —
  o painel ao vivo, não o de leitura, porque `running` estava incorretamente
  `true`); tabela por turno com 0 linhas. O teste "sem turno nenhum → sem
  custo" (`run-0002`) já passava — preexistente, preservado.
- **(f) vínculos** — 1/3 vermelho: painel mostrava os *subjects* do
  incidente (`backup-1f376301`, `backup-7d831311`) em vez dos
  `touched_resources` do próprio run (`proxmox:container/hal9000/110`,
  `ct-101`) — mensagem real capturada, "Expected substring:
  proxmox:container/hal9000/110 / Received string: ...Resourcesbackup-..." .
  Os outros dois (incidente por título, run sem vínculo nenhum) já passavam
  — preexistente, preservado.
- **staging-safe (2 testes)**: ambos passaram contra `populated` — esperado e
  correto, porque "o run mais recente" no dataset determinístico não é
  necessariamente um dos que carrega o defeito; o valor desses dois é medir
  o staging real, não o mock.

Log completo salvo nesta sessão em
`/tmp/claude-999/-srv-workspaces-NinjaSRE/0197c7d7-4784-453e-b36a-abb03241ebc2/scratchpad/red-run3.log`.

## Peça | Estado | Detalhe

| Peça | Estado | Detalhe |
|---|---|---|
| Vocabulário de status (completed/partial) | FEITO | `console/src/design/status.ts` — `RUN_STATUSES` inclui `completed`/`partial`; `DECLARED` tem papel+forma para os dois; `isSettled` vira lookup num conjunto terminal nomeado |
| Decisão "vivo" afirmativa | FEITO | `console/src/design/status.ts` — `isLiveRun()` novo, substitui a negação de `isSettled`; status desconhecido não é vivo (testado) |
| Teste do vocabulário | FEITO | `console/tests/unit/design/status.test.ts` — 35 passed, incluindo os 5 casos novos (enumera os 4 valores do runtime como dado do próprio teste, sem importar Python) |
| Custo real derivado no gerador | FEITO | `tools/mockplane/dataset/served.py` — `_turn_usage()` soma `cost`/`prompt_tokens`/`completion_tokens` que cada turno de fato carrega; fórmula fake `0.031*(turns+1)` removida |
| Headline explícito respeitado | FEITO | `served.py` `_run_detail()` — `run["headline"]` vence quando a chave existe (mesmo `""`), só cai em `synthesize_headline` na ausência da chave |
| Fixtures novas (3 runs + 4 chamadas) | FEITO | `RUNS` em `served.py`: `run-0101` (sem headline, terminal `completed`, relato markdown completo), `run-0102` (headline com ênfase e >120 chars, `partial`), `run-0103` (relato hostil: HTML cru, imagem externa, link `javascript:`, linha de código sem quebra); `_TURNS["run-0005"]` com 4 chamadas em 2 turnos, um precificado outro não |
| Suíte de coerência de fixtures | FEITO | `uv run pytest tests/contract/fixtures/test_dataset_contract.py tests/contract/fixtures/test_dataset_coherence.py tests/unit/tools/mockplane/` → **245 passed** |
| Sincronização now-violations | FEITO | `fixtures/scenarios/now-violations/runs.json` ganhou os mesmos 3 runs (cópia do que `populated` gera), resolvendo referência quebrada que o dataset coerente acusou |
| `run-subject.ts` (nome de um run, lugar único) | FEITO (módulo pronto, não ligado ainda) | `console/src/surfaces/run-subject.ts` — `subjectOf()`, `MAX_RUN_NAME_LENGTH=120`; headline → tradução de falha conhecida → `trigger · id curto`; nunca o documento |
| Teste de `run-subject.ts` | FEITO | `console/tests/unit/surfaces/run-subject.test.ts` — vermelho confirmado (módulo não resolvia), 13 casos |
| `report.tsx` (relato renderizado) | FEITO (módulo pronto, não ligado ainda) | `console/src/surfaces/report.tsx` — parser markdown próprio, sem dependência nova (decisão do orquestrador, ver abaixo), mapa de elementos fechado, `img` nunca vira `<img>`, esquema de link checado antes de navegável |
| Acceptance spec | FEITO | `console/tests/e2e/010-leitura-do-relato.acceptance.spec.ts` — vermelho real confirmado nos 6 grupos (ver seção acima) |
| **Ligar `run-subject.ts`/`report.tsx`/`isLiveRun` às telas** | **NÃO INICIADO** | Este é o próximo passo — `run-detail.tsx`, `runs.tsx`, `runs/[runId]/page.tsx` ainda chamam o caminho antigo |
| Transcript sem injeção do relato | NÃO INICIADO | `run-detail.tsx:104-107` ainda injeta `said.title` como `summary` do replay |
| Painel de vínculos lendo `touched_resources` | NÃO INICIADO | ainda lê só `incident.subjects` |
| Linhas-meta sem placeholder duplo | NÃO INICIADO | |
| Allowlist transversal encolhida | NÃO INICIADO | as 4 entradas seguem na tabela; a ligação da tela é pré-requisito |
| Catálogo i18n (`run.report.raw`) | BLOQUEADO PELA FRONTEIRA | ver seção própria abaixo |
| `screens.json` / baselines visuais | BLOQUEADO PELA FRONTEIRA | ver seção própria abaixo |

## Decisão de produto que mudou nesta execução: renderizador sem dependência nova

O `plan.md` da feature escolheu `react-markdown`+`remark-gfm`. O orquestrador,
nesta execução, **reabriu essa decisão explicitamente** por risco de prazo e
orçamento de bundle: "Não acrescente dependência nova". `console/package.json`
não tinha nenhuma biblioteca de markdown já presente, então `report.tsx` é um
parser markdown-subset próprio (blocos: heading×6, parágrafo, lista
ordenada/não ordenada, tabela, bloco de código cercado, citação, regra
horizontal; inline: strong, em, code, link, imagem). Toda propriedade de
segurança do FR-018 a FR-033 é estrutural: nunca monta string HTML, nunca usa
`dangerouslySetInnerHTML`, imagem nunca vira elemento, esquema de link é
checado antes de virar `<a>`. Ainda não medido: bundle/orçamento
(`make console-budget`) — pendente, tarefa da Fase 9.

## Fronteira — arquivos de escrita única do slot

O orquestrador desta execução declarou que `console/src/i18n/*.ts`,
`console/src/shell/routes.ts` e `console/visual/screens.json` são da feature
de fonte-por-fato neste slot, não minha — ao contrário do que o `tasks.md`
desta própria feature declara (que a lista esses três como propriedade da
010). Sigo a instrução do orquestrador, que é a mais recente e explícita.

**Chave i18n que vou precisar e não vou escrever no catálogo:**

- `run.report.raw` — texto (`en`): `"Original text, as recorded"` — rótulo do
  `<summary>` da disclosure fechada que revela o texto cru do relato
  (FR-030). pt-BR sugerido: `"Texto original, como foi gravado"`.

Nenhuma outra chave nova é necessária — o painel do relato reaproveita
`run.summary.title` existente, e o separador do nome (` · `) segue o mesmo
padrão não-traduzido que o subtítulo do detalhe já usa.

Vou referenciar `message(locale, 'run.report.raw')` no código de
`run-detail.tsx` quando ligar a disclosure. Até o orquestrador aplicar a
chave, `tsc`/o teste de completude de catálogo vão reprovar nesse ponto
específico — reportado, não escondido.

**`screens.json`**: não vou tocar. A tarefa de recaptura de baseline (T053-T055
do `tasks.md`) fica **não iniciada**, de propriedade da feature de
fonte-por-fato, com a razão de aceitação que a baseline deveria carregar
escrita aqui para quem for aplicá-la: "título é uma sentença; documento
desenhado como documento; ausência do painel de controle num run terminado".

## Próximos passos (ordem do orquestrador)

1. Ligar `run-subject.ts`, `report.tsx` e `isLiveRun` a `run-detail.tsx`,
   `runs.tsx` e `runs/[runId]/page.tsx` — isso fecha (a), (b), (c), (d) do
   acceptance e derruba as 3 entradas de markdown cru + 1 de identificador em
   `/runs`.
2. Vínculos lendo `touched_resources` do próprio run.
3. Transcript sem a injeção do relato.
4. Linhas-meta sem placeholder duplo.
5. Allowlist: remover as 4 entradas, rodar a suíte transversal inteira,
   provar que passa por mérito.
6. Gates: `console-typecheck`, `console-lint`, `console-test`,
   `console-budget`, `network.spec.ts`, `make verify`.

## O que fica pendente, nomeado, não escondido

- Nada das telas foi alterado ainda — só os módulos que as telas vão
  consumir, e a base de dados/testes que prova o defeito.
- `make verify` completo ainda não rodou nesta sessão (rodei apenas a suíte
  de fixtures/mockplane, 245 passed, e vitest/status isolado). Vou rodar ao
  final.
