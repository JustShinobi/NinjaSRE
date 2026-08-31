# Controle — Telas de área (slot S2)

Estado abaixo verificado contra o código real desta árvore, não contra a
intenção. Cada linha cita `file:line` ou o comando que a comprova.

## Peça | Estado | Detalhe

| Peça | Estado | Detalhe |
|---|---|---|
| T001 — baseline `make verify` | FEITO | Verde antes de qualquer mudança: Python 0 falhas, console 190 arquivos/3138 testes verdes. |
| T002 — caracterização (Fase 0) | FEITO | `evidence/caracterizacao.md` — `parent_name` já existia (bug de confiabilidade, não campo ausente); `unhealthy_since` genuinamente novo; episódios/propostas/topologia cravados; "achados sem detector" sem fonte pronta (decisão registrada). |
| T003 — capturas "antes" no staging | `[~]` do lead | Sem alcance a staging/Orca desta worktree; o lead confirmou as oito capturas já comitadas em `evidence/visual/antes/`. |
| T004–T007 — os quatro acceptance specs, red-first | FEITO | Todos os quatro escritos e confirmados vermelhos contra o build real (`tools.console_e2e`, não o `tools.mockplane console` que este relatório usou por engano nas primeiras corridas — ver nota de método abaixo). Dois blocos de Agent passavam medindo zero elementos; corrigidos para exigir contagem mínima antes de iterar, reconfirmados vermelhos isolados. |
| T008 — contrato pytest (node/unhealthy_since) | FEITO | `tests/contract/persistence/test_estate_repository.py`, `tests/unit/platform/estate/test_estate_service.py` (novo), `tests/unit/gateway/http/test_estate_routes.py` — vermelho confirmado, depois verde. 328 testes de estate verdes, mypy limpo. |
| T009 — unitários vitest das cinco derivações | FEITO | (a) `incident-timeline.ts`. (b) `component-normalisation.ts`, com a correção do valor canônico (achado do slot, abaixo). (c) `stageRegime` em `agent-pipeline-metro.ts`. (d) `toolSummary` (as três contagens de efeito colateral) no mesmo módulo, testado; o agrupamento por domínio (top 6) é real e exercitado pelo acceptance (`domain-bar`), mas ficou inline no componente — não isolado como função pura própria, diferente dos outros quatro. (e) síntese de Recursos em `resources-grouping.ts`. Todos os cinco testados e verdes, exceto a ressalva de (d). |
| T010/T011 — contrato do estate + regeneração | FEITO | Porta, Postgres (`DISTINCT ON`), fake — todos com paridade testada. `openapi.json`/`schema.ts` regenerados pelos geradores. |
| T012–T015a — Incidentes (US1) | FEITO | `incident-group-list.tsx` reescrito: `data-testid="row"` com título como link para `/incidents/{publicId}` da occurrence mais nova (FR-001/T015a), faixa 24h, bloco de causa/link ao vivo (uma leitura de `/v1/runs` por página via `subjectOf`, o módulo canônico já existente — nunca uma segunda fonte de nome), strip de recorrência. `incidents.tsx`: segmented controls (só aparecem quando há escolha real — regra "mobília" preservada), cartão de achados sem detector. **Prova**: `incidents-by-subject.acceptance.spec.ts` 11 de 14 verdes isolado (3 pulados nomeadamente, sem assunto recorrente local). `transversal-rules.spec.ts` para `/incidents/{id}`: 4 de 4 verdes isolado — as três falhas herdadas do S1 (markdown, identifier-as-name, two-placeholders) e a quarta regra (negative-assertion) todas fecham de verdade, sem allowlist. |
| T016 — i18n single-write das quatro telas | PARCIAL | Chaves de Incidentes/Recursos/Conhecimento aplicadas em `en.ts`+`pt-BR.ts`, paridade mantida (`catalogue.test.ts` verde). Chaves de O agente pendentes — fase não alcançada. |
| T017–T019 — Recursos (US2) | FEITO | `resources-grouping.ts` (novo, testado): `healthSegments`, `groupByNode`, `unhealthySynthesis`. `resources.tsx` reescrito: barra de saúde segmentada com "N vigiados" + legenda clicável, busca compacta, chips de tipo com contagem, seções por nó (não-saudáveis primeiro, dentro e entre seções), síntese em lote, aviso de zona/criticidade no rodapé, painel `undeclared` (achado de divergência que o grid de cards não tinha mais onde marcar por linha — ver "achado do slot"). **Prova**: `resources-by-node.acceptance.spec.ts` 9 de 13 verdes isolado (4 pulados nomeadamente: quatro estados simultâneos e `unhealthy_since` são fatos que só staging tem). |
| T020–T023 — Conhecimento (US3) | FEITO | `component-normalisation.ts` (novo, testado, com a correção de valor canônico). `memory.tsx` reescrito: Aprendido como aba padrão (`knowledge.tsx` `tabFrom`), episódios como cards com chip de resultado moldado, filtro de componente agrupado por tipo (consulta ao servidor por spelling bruto real, nunca sintetizado — ver achado abaixo), painel "o que o agente aprendeu" lendo `/v1/proposals` filtrado a `proposal_type==='knowledge'`, faixa inferior com Documentos/Topologia. **Prova**: `learned-knowledge.acceptance.spec.ts` 13 de 14 verdes isolado (1 pulado nomeadamente). |
| T023a — reforma de Documentos/Topologia | `[~]` cortado | Onda autoriza este corte primeiro, antes de tocar Incidentes (Implementation Strategy do tasks.md). Documentos/Topologia continuam com o vocabulário da 000 (tokens/chips/ícones), sem a reforma estrutural do artboard próprio — inclusive o `<select>` de "kind" do Documents, que `AN-T1` por isso mede só em Aprendido. |
| T024–T026 — O agente, núcleo (US4) | FEITO | `agent-pipeline-metro.ts` (novo, testado: `stageRegime`, `toolSummary`). `agent.tsx`: linha de metrô acima do que já existia (grafo hierárquico + lista de estágios — intactos, sem artboard que os reforme, ficam abaixo da dobra), seis nós na ordem servida com ícone/regime/nome/microcopy, chip "N em voo" lendo `/v1/runs`, três cards-resumo (Ferramentas/Autonomia/Contexto do time) cada um lendo a mesma rota que sua aba já lê, uma vez a mais só na aba Pipeline. **Prova real**: `agent-pipeline.acceptance.spec.ts` — 13 de 14 verdes na primeira corrida real, 1 pulado nomeadamente (a figura auditada 63 de 80 é staging-only). `tests/unit/surfaces/agent.test.tsx` sem regressão (66 de 66). |
| T026a — reforma de Ferramentas/Autonomia/Contexto do time | `[~]` cortado | Mesma ordem de corte que T023a autoriza (6 antes de 5, antes de 4, nunca antes de 3). As três abas seguem completas no vocabulário da 000 (AN-A8's "seguem completas" cumprido), sem a reforma estrutural do artboard próprio de cada uma. |
| T027–T033 — integração e fechamento | PARCIAL | Ver tabela de gates abaixo; T031/T032 são do lead. |
| T034 — corrigir o locator quebrado de "within a section, unhealthy cards draw before healthy ones" (Fase 8, convergência) | FEITO | `console/tests/e2e/resources-by-node.acceptance.spec.ts:172-178`: trocado `.filter({ has: page.locator('[data-has-unhealthy="true"]') })` (que só casa descendente, nunca o próprio elemento) por `page.locator('[data-testid="node-section"][data-has-unhealthy="true"]')`, que lê o atributo do próprio `node-section` (`console/src/surfaces/screens/resources.tsx:611`). O teste deixou de se autopular com "no unhealthy section in this dataset" e passou a exercitar a ordenação real, com um corte de fio confirmando que ele falha de verdade quando a ordenação é desfeita — ver as três linhas de gate abaixo. Nenhuma mudança em `resources.tsx` ou `resources-grouping.ts` (`git diff` limpo nos dois após o corte de fio e a restauração). |

## Gates rodados, com o resultado real

| Gate | Comando | Resultado |
|---|---|---|
| `make verify` (baseline, T001) | `make verify` | Verde, log fora do repo, conferido pelo próprio arquivo (não pela notificação). |
| `console_gate static` (prettier+eslint+tsc+vitest+build+orçamentos) | `python -m tools.console_gate static` | **Verde, exit 0, 3151 testes.** Falhou por formatação (prettier) por boa parte da sessão sem que eu rodasse este gate específico até tarde — corrigido com `prettier --write` em todos os arquivos tocados; ver "achado de processo" abaixo. |
| `mypy` nos 5 arquivos de backend tocados | `uv run mypy platform/estate/service.py platform/persistence/ports/estate_repository.py platform/persistence/postgres/repositories/estate_repository.py platform/persistence/fakes/estate_repository.py gateway/http/routes/estate.py` | Limpo. |
| pytest do estate (contrato + unit + rota HTTP) | `pytest tests/ -k estate` | 328 passaram, 1 pulado, 0 falhas. |
| `check_constants`, `check_dependencies` | `python tools/check_constants.py`, `python -m tools.check_dependencies` | Ambos exit 0. |
| Acceptance Incidentes isolado | `console_e2e run ... -- incidents-by-subject` | 11 de 14 verdes, 3 pulados nomeadamente. |
| Acceptance Recursos isolado | `console_e2e run ... -- resources-by-node` | 9 de 13 verdes, 4 pulados nomeadamente. |
| Acceptance Conhecimento isolado | `console_e2e run ... -- learned-knowledge` | 13 de 14 verdes, 1 pulado nomeadamente. |
| Acceptance O agente | não rodado | Fase não implementada. |
| `transversal-rules.spec.ts` completo | `console_e2e run ... -- transversal-rules` | Isolado por rota: `/incidents/{id}` 4 de 4 verdes. Numa corrida combinada de ~2m40s junto com as outras três specs, 10 falharam por timeout de 15s — **todas reproduzidas como falso-negativo de contenção**, não defeito: refeitas isoladas (`/incidents/{id}` sozinho, `incidents-by-subject` sozinho) e todas passaram. A máquina builda a feature pareada (040) ao mesmo tempo, exatamente o aviso que o despacho já dava. Nenhum veredito deste controle vem da corrida combinada. |
| `make console-client` / `python -m tools.mockplane contract` | rodados após a mudança de contrato | `openapi.json` (+12 linhas) e `schema.ts` (+2 linhas) — diffs mínimos, gerados, nunca editados à mão. |
| T034 — rebuild + acceptance Recursos isolado, com o locator corrigido | `uv run python -m tools.console_gate build` seguido de `uv run python -m tools.console_e2e run --backing mock --scenario populated -- resources-by-node.acceptance.spec.ts` | Build exit 0. Spec: **10 de 13 verdes (era 9 de 13 antes do T034), 3 pulados nomeadamente (era 4)** — exit 0. O quarto skip que desapareceu era o autopulo do seletor quebrado, não um limite de dado; os três que restam são genuinamente só-staging (quatro estados de saúde simultâneos, `unhealthy_since`, síntese em lote) e não mudaram. |
| T034 — corte de fio: prova de que o teste falha de verdade | corte manual em `resources-grouping.ts:74` (`const byHealth = Number(isUnhealthy(right)) - Number(isUnhealthy(left));` → `const byHealth = 0;`, desligando a ordenação "não saudável primeiro" dentro do nó), rebuild, `console_e2e run --backing mock --scenario populated -- resources-by-node.acceptance.spec.ts -g "within a section, unhealthy cards draw before healthy ones"` | **Vermelho, exit 1**: `expect(lastUnhealthy).toBeLessThan(firstHealthy)` → `Expected: < 0, Received: 51`, apontado em `resources-by-node.acceptance.spec.ts:189`. Linha restaurada logo em seguida, rebuild refeito, `git diff -- console/src/surfaces/screens/resources-grouping.ts` confirmado vazio antes de seguir. |
| `console_gate static` pós-T034, sem o corte de fio | `python -m tools.console_gate static` | Verde, **exit 0**: prettier/eslint/tsc limpos, vitest 195 arquivos/3156 testes verdes, build ok, orçamentos dentro (stylesheet 29662/40960 bytes, ícones 13277/16384 bytes). |

## Verificação final, limpa (sem contenção)

Depois de todas as fases acima, nesta ordem, sem nada mais rodando ao mesmo
tempo:

- `make verify` — **exit 0**, Python inteiro verde (13118 selecionados nos
  módulos tocados + a amostra de benchmarks, 0 falhas), `console_gate static`
  verde (prettier + eslint + tsc + 3151 testes vitest + build + orçamentos de
  bundle).
- Os quatro acceptance specs juntos (`console_e2e run ... --
  incidents-by-subject resources-by-node learned-knowledge agent-pipeline`):
  **46 passaram, 9 pulados nomeadamente, 0 falharam, exit 0.**
- `transversal-rules.spec.ts` completo, isolado: **39 passaram, 7 pulados,
  6 falharam — as mesmas seis de sempre** (`/runs/{id}` × 4, herdadas do S1
  e atribuídas a quem reformar `/runs`; a regra de progresso do setup × 2,
  sem relação com esta feature). **Nenhuma falha em `/incidents`,
  `/resources`, `/knowledge` ou `/agent`.**

A corrida anterior deste mesmo arquivo, com dez falhas por timeout de 15s
numa corrida combinada, foi contenção real: aconteceu com um `make verify`
rodando ao mesmo tempo em segundo plano (meu próprio, não o da feature
pareada) — refeita depois que ele terminou, limpa, com o resultado acima.
Fica registrado como confirmação de que a hipótese de contenção era
verificável, não uma desculpa.

## Achados do slot, registrados para não se perderem

1. **`tools.mockplane console` não serve o console React.** Serve
   `surfaces/console`, a UI antiga renderizada em Python (tema azul,
   DIVERGENCIAS.md item 5). As primeiras corridas deste relatório usaram essa
   ferramenta por engano e todo "vermelho"/"verde" medido contra ela não
   provava nada desta feature — a sessão de cookie nem tem o mesmo nome
   (`ninjasre_console_session` vs `ninjasre_session`). A partir da correção,
   toda medição usa `python -m tools.console_e2e run --backing mock --scenario
   populated -- <specs>`, que builda `.next/standalone` (via `python -m
   tools.console_gate build`, sempre antes) e serve o console de verdade.
2. **O filtro de componente do Aprendido quase mandou um valor que nenhum
   episódio carrega.** `normaliseComponents` originalmente sintetizava
   `guest:<id>` como valor canônico sempre que unia `container:<id>` e
   `guest:<id>` — mesmo quando só uma das duas grafias existia de verdade no
   corpus. Como o filtro continua sendo resolvido no servidor
   (`/v1/memory/search?component=`, correspondência exata), um link de filtro
   com um valor inventado é um link que silenciosamente não devolve nada.
   Corrigido para que o valor canônico seja sempre uma grafia realmente
   observada; uma opção fundida carrega as duas grafias em `raw`, e a tela
   consulta cada uma e funde por `episode_id` — nunca lê o corpus inteiro e
   filtra no navegador (o vocabulário do filtro em si é lido sem filtro, para
   não encolher a cada seleção, o que o código antigo também não garantia).
   Achado ao responder uma pergunta direta do lead, não por iniciativa
   própria — registrado assim mesmo porque é a explicação que um verifier
   precisa.
3. **O grid de cards de Recursos não tinha mais onde marcar uma divergência.**
   A tabela antiga marcava, por linha, quando o provedor relata um recurso
   que o inventário declarado não nomeia (`only_in_provider`). O artboard do
   card não tem essa marca — mas a informação não podia simplesmente
   desaparecer. Fechado com um painel `undeclared`, simétrico ao `departed`
   que já existia para a direção oposta (`only_in_file`).
4. **A barra de saúde perdeu o "N vigiados" no primeiro rascunho.** O
   artboard mostra o total pareado com os quatro segmentos; corrigido.
5. **Processo, dito sem rodeio**: `console_gate static` (prettier+eslint+tsc+
   testes+build) só foi rodado pela primeira vez tarde nesta sessão — antes
   disso, tsc/eslint/vitest focados passavam, mas o prettier estava quebrado
   em 14 arquivos sem que nada acusasse. A partir daqui, `console_gate
   static` roda antes de cada commit que toque `console/`, não só os
   checkpoints de fase.
6. **`SegmentedLinks` é um componente novo, não quatro soluções locais.**
   As quatro telas precisam do mesmo padrão — escolha mutuamente exclusiva,
   estado na URL, nunca um `<select>` — e `FilterBar`/`Select` são
   compartilhados com toda tela fora desta feature; reformá-los teria
   reformado telas sem artboard. Um componente ao lado de `TabLinks` (mesmo
   padrão de link com estado na URL) evita isso. Custou dois retrabalhos que
   ficam registrados para quem herdar o padrão: precisa de entrada na galeria
   de componentes (`tests/unit/gallery.test.tsx` audita cobertura), e seu
   wrapper usa o mesmo landmark `<nav>` que `TabLinks` já usa — `role="group"`
   não está no conjunto fechado de papéis ARIA que o auditor de acessibilidade
   deste console reconhece (`tests/unit/support/accessibility.ts`).

## O que fica pendente, nomeado, não escondido

- **T023a e T026a — cortados deliberadamente**, na ordem que a própria
  tasks.md autoriza (Documentos/Topologia primeiro, depois as três abas de O
  agente), nunca tocando a 3 (Incidentes). Nenhum artboard próprio aplicado
  a essas cinco superfícies; todas seguem completas no vocabulário da 000.
- **O agrupamento por domínio (top 6) do card Ferramentas** não tem função
  pura própria testada — está inline no componente, único ponto das cinco
  derivações do T009 sem essa forma. Comportamento real, exercitado pelo
  acceptance, não uma lacuna funcional.
- **T027–T030, T033** — integração final (aplicar qualquer chave/variante
  ainda solta), re-baseline visual local e relatório final do fan-out não
  feitos nesta passada — ver a seção de fechamento abaixo.
- **T031/T032** — do lead (staging, Orca browser).

## Reparos do gate visual — slot S2

Quatro desvios que `evidence/visual/VEREDITO.md` encontrou contra o staging
real, cada um fechado nesta passada com teste vermelho-primeiro confirmado
contra o build real, e um corte de fio depois do verde provando que o teste
falha de verdade. Tabela à parte da acima porque nasce de um veredito, não
de uma tarefa planejada antes da execução.

| Desvio | Estado | Detalhe |
|---|---|---|
| 1. Incidentes — subtítulo é identificador, não nome (T035) | FEITO | `console/src/surfaces/incident-group-list.tsx`: `SubjectLine` e `subjectTitle` agora resolvem o nome da estante por `resolvedName` (novo), que só aceita um nome quando ele difere do próprio id — a queda do gateway para `display_name or resource_id` (`gateway/http/routes/estate.py`, `_row`) não conta como nome ganho. `console/src/surfaces/screens/incidents.tsx`: mapa `subjectNames` (`resource_id -> display_name`) construído uma vez por página a partir da MESMA leitura de `/v1/estate/resources` que o cartão de cobertura de detector já fazia (linha ~183) — nenhuma segunda requisição, nenhuma mudança de gateway. Um assunto que a estante genuinamente não tem (`cluster`, um datastore, um job de backup, no dado local) não ganha entrada no mapa e continua a mostrar o id encurtado, nunca em branco — comportamento herdado, não reescrito. |
| 2. Recursos — a grade nunca termina (T036) | FEITO | `console/src/surfaces/screens/resources-grouping.ts`: `capNodeSection`, nova, testada (13 casos) — uma linha (4 cartões) quando a seção não tem nada não saudável, duas (8) quando tem; reproduz os dois exemplos do próprio board exatamente (pve01: 58/0 → 4 + "ver todos"; pve02: 41/14 → 8 + "ver os não saudáveis"). `resources.tsx`: grade renderiza `capped.shown`; filtro `node` novo em `RESOURCE_FILTERS` (mesmo padrão de `zone`/`kind`/etc., `FilterName` já é `string`) para que os dois links levem a algo real — `?node=<id>` (mais `health=problem` para "ver os não saudáveis") — em vez de um `href="#"` decorativo; uma seção alcançada assim (`drilledIntoNode`) nunca é recortada de novo e ganha um link "voltar" (`action` do `Panel`). Sentinela `NO_NODE_FILTER_VALUE='none'` para a seção "sem nó declarado", cujo `nodeId` é `''` — que `withFilter` trata como "filtro ausente" e apagaria da URL. Prova: cinco testes novos em `resources-by-node.acceptance.spec.ts`; vermelho confirmado contra o build sem o corte (52 cartões numa seção só, altura 2423px no dataset local), verde depois — **altura capturada: 1103px** (o board cita 3230px em staging antes desta correção). `console/visual/screens.json`: os dois registros de `/resources` já estavam `pending`; motivo corrigido para não afirmar mais que a grade em cartões "não tem esse problema" — ela tinha, por um motivo diferente do da tabela antiga. |
| 3. Conhecimento — desfecho do episódio sem chip e fora do vocabulário de status (T037) | FEITO | `console/src/surfaces/screens/memory.tsx`: `EpisodeCard` trocou o `<span>` calculado à mão (`outcomeShape`, binário resolvido/o-resto, sem `data-role`) por `StatusDot` (ponto à esquerda) mais `OutcomeChip` novo (`ResolvedChip` + `statusPresentation`, chip à direita) — confirmado no ambiente real que nenhum elemento de `/knowledge` carregava `data-role`; agora carrega. `EPISODE_OUTCOME_LABEL` traduz as quatro palavras que `EpisodeOutcome` declara; uma quinta palavra ainda ganha papel e forma do vocabulário compartilhado e imprime a si mesma, como `Badge` já faz. **Achado ao investigar, não a correção como recebida**: o fixture de `4ebdbee5` tinha nivelado os dois episódios que eram `"acknowledged"` e o que era `"unresolved"` para um único `"inconclusive"`; a tabela de tradução do seeder de demonstração (`platform/startup/demo/seeder.py`, `_EPISODE_OUTCOME`) já mapeia esse vocabulário legado para o enum real, e mapeia os dois de forma diferente — `"acknowledged"` para `MITIGATED`, `"unresolved"` para `INCONCLUSIVE`. `tools/mockplane/dataset/served.py` corrigido para essa mesma tradução (dois episódios agora `"mitigated"`, um `"inconclusive"`) e `fixtures/scenarios/populated/episodes.json` regenerado por `python -m tools.mockplane build --scenario populated` — sem edição manual, `git diff` conferido contra o gerador. `mitigated`/`false_positive` não entraram em `console/src/design/status.ts` (congelado); um episódio `mitigated` real existe agora no dataset local e passa pelo caminho de "palavra não ensinada" (papel neutro, rótulo próprio, `known: false`), exercitado por teste, não escondido — ver recomendação abaixo. Prova: três testes novos em `learned-knowledge.acceptance.spec.ts`; vermelho confirmado contra o build sem o wiring (`element(s) not found` no locator `episode-outcome`), verde depois. Corte de fio: `statusPresentation(outcome)` → `statusPresentation('')` em `memory.tsx` — vermelho só no teste que fixa papel por palavra (`Expected: "success", Received: "neutral"`), os outros dois continuaram verdes (medem "tem um papel"/"renderiza", não qual), provando que só aquele teste mede a derivação real; linha restaurada, `git diff` limpo, verde de novo. |
| 4. O agente — primeira aba com o nome antigo, linha de metrô sem trilho (T038) | FEITO | `console/src/surfaces/screens/agent.tsx`: `agent.tab.topology` (`en.ts`/`pt-BR.ts`) passou de "Topology"/"Topologia" para "Pipeline" — o slug interno `'topology'` (`AGENT_TABS[0]`) fica como está, de propósito (URL, `data-tab`, os ramos que leem `tab === 'topology'`), documentado em comentário para não ser "corrigido" por engano depois. `PipelineMetro` ganhou `data-testid="pipeline-metro-rail"`, absolutamente posicionado atrás da grade de seis nós, `insetInlineStart`/`insetInlineEnd` calculados de `stages.length` e de `--space-4` (o mesmo token de `gap-4`) — não uma aproximação — e visível só em `lg:`, onde a grade é uma única linha; antes dos nós no DOM, então o preenchimento opaco de cada ícone cobre o trecho atrás dele. O chip "N em voo" não mudou: staging tem 682 runs completos, 11 interrompidos, zero rodando, medido, não um defeito. Prova: dois testes novos em `agent-pipeline.acceptance.spec.ts`; vermelho confirmado contra o build sem a mudança (`Received: "Topology"`; `pipeline-metro-rail` ausente), verde depois. Corte de fio duplo — tradução revertida (mesmo vermelho do rótulo) e divisor dos insets encolhido (`Expected: <= 543.5, Received: 642`, alcance quebrado) — ambos restaurados, `git diff` limpo, verde de novo. **Achado durante a implementação, não um corte proposital**: a primeira versão usava `size-6` no invólucro do trilho, que fixa `width` além de `height` e ignorava `insetInlineEnd` por completo (`Received: 575.5` esperando `>= 1608.5`) — pego pelo próprio teste de alcance antes de qualquer corte deliberado; corrigido para `h-6` (só altura). |

## Achados do slot, registrados para não se perderem (continuação)

7. **`ResourceSummaryView.display_name` já cai para o próprio `resource_id`
   quando o recurso não tem nome** (`gateway/http/routes/estate.py`, `_row`:
   `display_name=resource.display_name or resource.resource_id`). Um mapa de
   nomes que confiasse cegamente nesse campo teria mostrado o id duas vezes
   sob dois rótulos diferentes em vez de uma vez só — `resolvedName` em
   `incident-group-list.tsx` existe por isso: só conta como nome quando
   `display_name !== resource_id`.
8. **O primeiro teste de `capNodeSection` que localizava o link "ver os N
   não saudáveis" pelo `data-has-unhealthy` da seção, não pelo próprio
   link, achava o nó errado.** node01 e node02 no dataset local carregam os
   dois `data-has-unhealthy="true"` (node01 tem 3 não saudáveis, abaixo do
   corte; node02 tem 11, acima) e `groupByNode` desempata por nome quando o
   `hasUnhealthy` empata — node01 vem primeiro. `.first()` sobre "toda
   seção não saudável" pegava o link errado (`data-only-unhealthy="false"`)
   antes mesmo de chegar em node02. Corrigido para localizar
   `[data-testid="node-section-more"][data-only-unhealthy="true"]`
   diretamente — o mesmo padrão que o teste vizinho já usava.
9. **A correção de `4ebdbee5` tinha resolvido a palavra fora de vocabulário,
   mas não a tinha traduzido certo.** `"acknowledged"` e `"unresolved"` foram
   ambos nivelados para `"inconclusive"` — o que já fecha "o backend nunca
   emitiu essas palavras", mas não é a mesma coisa que fechar "o backend, se
   tivesse que traduzir essas palavras, traduziria as duas para o mesmo
   valor". `platform/startup/demo/seeder.py` já declara essa tradução
   (`_EPISODE_OUTCOME`) para o mesmo propósito — semear uma implantação real
   a partir do mesmo `fixtures/`, que `platform/startup/demo/dataset.py` lê
   diretamente — e ela mapeia `"acknowledged"` para `MITIGATED`,
   `"unresolved"` para `INCONCLUSIVE`: duas palavras, dois destinos. Seguida
   essa tradução em vez da nivelada: dois episódios que eram "acknowledged"
   (`ep-0002`, `ep-0005`) agora servem `"mitigated"`; o que era "unresolved"
   (`ep-0003`) continua `"inconclusive"`, que já estava certo.

## Recomendação — `mitigated` e `false_positive` em `console/src/design/status.ts`

Não aplicada (o diretório é congelado e a decisão é do lead); registrada
aqui com o raciocínio para quem decidir.

**`mitigated` — declarar.** Não é um valor hipotético: é a tradução que o
próprio backend já declara para uma palavra de captura real
(`_EPISODE_OUTCOME` acima), e com essa tradução aplicada o dataset local
`populated` — o mesmo que os quatro acceptance specs desta feature rodam
contra — carrega dois episódios `mitigated` em cinco, não um caso de borda.
Deixado sem declarar, os dois recebem o papel neutro de "palavra não
ensinada" ao lado de um `resolved` verde e de um `inconclusive` âmbar — o
que é honesto, mas achata numa cor cinza um terceiro ponto real do espectro
de desfecho. Proposta: `role: 'info'`, `shape: 'dimmed-circle'` — a mesma
combinação que `stored` já usa para "sabemos algo aconteceu, mas não temos a
mesma confiança que um `resolved`/`verified` tem" (`console/src/design/status.ts`,
comentário de `stored`: "ahead of anything a live check could say about it"
— o mesmo formato epistêmico de "alguém agiu e o sintoma parou, mas a causa
raiz não foi estabelecida com a evidência que `resolved` exige", que é a
única leitura de "mitigado" que o docstring de `MemoryEpisode.resolved`
sustenta ("A root cause was established with evidence behind it. **Not** a
claim that production was fixed"). Nenhuma combinação `{success, hollow-circle}`
existe hoje no mapa — cogitada e descartada: "sucesso" é uma reivindicação
mais forte do que "mitigado" garante, e `info`+`dimmed-circle` reaproveita
um par já declarado em vez de inventar mais um.

**`false_positive` — não declarar agora.** Zero episódios no corpus local ou
em qualquer teste/seeder emitem esse valor hoje — `rg` no repositório inteiro
só o encontra na própria declaração do enum e na entrada `"false_positive":
EpisodeOutcome.FALSE_POSITIVE` de `_EPISODE_OUTCOME`, nunca produzido. O
board também não desenha essa palavra em canto nenhum de `Knowledge.dc.html`.
Sem um episódio real para exercitar, declarar um papel seria adivinhar — e
o fallback (`neutral`, `hollow-circle`, rótulo próprio, `known: false`) já é
honesto e testável quando esse dia chegar. Se o lead quiser aplicar mesmo
assim, por analogia: `role: 'neutral'`, `shape: 'dash'` — o mesmo par que
`closed_without_action` usa por um raciocínio que se transporta quase
inteiro ("Terminal com nada feito... não é um incidente que foi resolvido, e
desenhá-lo em verde é como um índice de sucesso mente"), mas essa segunda
proposta é mais fraca que a primeira porque nasce de analogia, não de dado.

## Achado do slot, registrado para não se perder (T038)

10. **`size-*` fixa largura além de altura, e um invólucro pensado só para
    centralizar verticalmente travou a largura do trilho em 24px.** A
    primeira versão do trilho de `PipelineMetro` usava `size-6` no
    `<div>` que envolve o trilho (para ficar da mesma altura do ícone e
    centralizar a linha nele) — mas `size-6` declara `width` e `height`
    juntos, e um elemento `position: absolute` com `width` explícito
    ignora `insetInlineEnd` por completo mesmo com os dois insets
    definidos. O trilho ficava preso a 24px de largura no ponto de
    `insetInlineStart`, nunca alcançando o outro lado. Pego pelo próprio
    teste de alcance (`Received: 575.5` esperando `>= 1608.5`) antes de
    qualquer corte de fio proposital — corrigido trocando `size-6` por
    `h-6` (só altura), deixando a largura livre para os dois insets
    calculados a decidirem.
