# Tasks: Telas de área — Incidentes, Recursos, Conhecimento e O agente viram o board

**Input**: Design documents from `specs_v8/060-telas-de-area/`

**Prerequisites**: spec.md, plan.md, a 000 (fundação visual) mergeada — os
tokens, ícones, chips e formas usados abaixo vêm dela e estão congelados.

**Tests**: acceptance-first. Os quatro acceptance specs aterrissam **antes**
de qualquer implementação e são confirmados vermelhos com a mensagem real de
cada alegação registrada. Um agrupamento que já passa no teste é um teste que
não olha.

**Marcação**: `[x]` feita; `[ ]` pendente; `[~]` encerrada sem execução, com
a razão na própria linha e onde a obrigação foi cumprida por outro caminho.
Um `[~]` nunca é um `[x]` envergonhado.

## Regras que valem para toda tarefa deste arquivo

1. **Nada de identificador de planejamento em arquivo committed** — nenhum
   teste, comentário, string ou commit cita FR/AN/SC/feature/onda. A
   substância vai no arquivo; a referência fica aqui.
2. **O board é o critério.** Em dúvida de layout, cor, forma ou copy, a
   resposta está no artboard da tela e no `design/padrao-2026-08/SPEC.md` —
   não na memória de como o console era. Desvio deliberado tem um caminho
   só: `DIVERGENCIAS.md` + aprovação do operador, antes do merge.
3. **`console/src/design/` está congelado** (dono: 000). Token, ícone ou
   forma que falte é declarado no relatório final com o valor proposto; o
   orquestrador aplica. Nenhuma tarefa edita esses arquivos.
4. **Fan-out interno com dono único dos single-write**: as fases 3–6 rodam
   em paralelo, um implementer por tela; `console/src/i18n/*.ts`,
   `console/src/shell/routes.ts` e `console/visual/screens.json` são
   editados SÓ pela fase 3 (Incidentes). As fases 4–6 declaram chaves e
   variantes no relatório; a fase 7 aplica.
5. **Nenhuma tarefa toca** `dashboard.tsx` (050), rotas de decisão (040),
   `console/src/live/` (010), diretório de outra feature, nem inventa
   título de run (020).
6. **Arquivo gerado é regenerado** — documento de API, cliente TS, dataset
   simulado saem dos geradores.
7. **Gate não é afrouxado.** Visual ou transversal reprovando, o defeito é
   da mudança.

---

## Phase 0: Linha de base e caracterização (crava o que a spec deixou nomeado)

- [x] T001 Rodar `make verify` na árvore intacta; guardar log fora do
      repositório com exit code e contagens. Base não-verde → parar e
      reportar.
- [x] T002 Cravar por leitura de código (e registrar em
      `evidence/caracterizacao.md`, com file:line): (a) a rota e o handler
      do gateway que `ResourcesScreen` consome para a listagem, e os campos
      atuais da resposta; (b) a rota de episódios que a aba Aprendido lê e
      seus campos (inclusive o vocabulário real de `components` e o campo de
      run); (c) a rota da fila de propostas de conhecimento e o shape de uma
      proposta pendente; (d) o campo exato de contagem que a leitura de
      topologia devolve; (e) onde a contagem "achados degradados sem
      detector" do Painel nasce. Nenhuma implementação antes deste registro.
- [~] T003 Registrar as capturas "antes" das quatro telas no staging via
      Orca browser (dois temas), em `evidence/visual/antes/` — o par de
      comparação do veredito final. Encerrada sem execução por este
      implementer: exige o orquestrador (sem alcance a staging/Orca desta
      worktree). O lead já rodou e comitou as oito capturas em
      `evidence/visual/antes/` na árvore compartilhada.

## Phase 1: Acceptance primeiro, confirmado vermelho

- [x] T004 [P] Escrever
      `console/tests/e2e/incidents-by-subject.acceptance.spec.ts`
      codificando as alegações de Incidentes (agrupamento, subtítulo humano
      com id mono por último, segmented controls, faixa de 24 h com um ponto
      por disparo, link de investigação, bloco de causa, strip de
      recorrência, cartão de detector; as staging-safe marcadas). Assertar
      também a razão ≤ 1/3 entre assuntos e disparos da amostra 17/50 e a
      expansão completa do assunto mais recorrente. Rodar contra a árvore
      atual e registrar o vermelho de cada uma.
- [x] T005 [P] Escrever
      `console/tests/e2e/resources-by-node.acceptance.spec.ts` (barra
      segmentada proporcional com legenda clicável e filtro na URL, chips de
      tipo com contagem, seções por nó com não-saudáveis primeiro, cards com
      ícone/forma/duração, síntese com "investigar em lote", cartão de zona
      no rodapé). Medir o primeiro paint e afirmar que a síntese vem da
      mesma resposta, sem segunda request. Confirmar vermelho.
- [x] T006 [P] Escrever
      `console/tests/e2e/learned-knowledge.acceptance.spec.ts`
      (Aprendido como default e deep links preservados, filtro agrupado sem
      duplicata guest/container, cards de episódio com forma no resultado e
      link de investigação, painel de propostas pendentes com CTA, faixa
      inferior com contagens). Confirmar vermelho.
- [x] T007 [P] Escrever
      `console/tests/e2e/agent-pipeline.acceptance.spec.ts` (linha de metrô
      com seis nós na ordem servida e regime derivado de `model_role`,
      microcopy de uma frase, chip de runs em voo, três cards com números
      das rotas reais, abas completas preservadas, realce de estágio ausente
      sem quebrar). Confirmar vermelho.
- [x] T008 [P] Testes de contrato pytest para os dois campos novos do
      estate: a listagem serve `node` por recurso descoberto com placement e
      `unhealthy_since` para não-saudável com transição registrada; ausência
      honesta (null) nos dois quando o dado não existe. Confirmar vermelho.
- [x] T009 [P] Testes unitários vitest, vermelhos: (a) posicionamento da
      faixa de 24 h (janela, proporção por timestamp, occurrence fora da
      janela vira "e mais N", disparo único sem faixa); (b) tabela de
      normalização de componentes (`container:lxc/122` + `guest:lxc/122` →
      uma opção; grafias sem par intactas; agrupamento por tipo com
      contagens); (c) derivação de regime do estágio ("sem modelo" /
      "modelo: intake" / "determinístico"); (d) contagens de efeito
      colateral e top-6 domínios do card Ferramentas; (e) agrupamento da
      síntese de Recursos (3+ mesmo nó/tipo/janela de 30 min).

## Phase 2: Contrato do estate (bloqueia só a fase 4)

- [x] T010 Estender a query do repositório do estate para juntar placement e
      última transição de saúde (arquivos cravados em T002a; porta em
      `platform/persistence/ports/estate_repository.py`, Postgres e fake em
      paridade), e o view model da rota para servir `node` e
      `unhealthy_since`. Verde nos testes de T008.
- [x] T011 Regenerar documento de API e cliente TS
      (`fixtures/contract/openapi.json`, `console/src/api/schema.ts`) pelos
      geradores; gate de desvio verde.

## Phase 3: Incidentes (dona interna dos single-write) — US1

- [x] T012 [US1] Reescrever a apresentação de
      `console/src/surfaces/screens/incidents.tsx` conforme
      `Incidents.dc.html`: linha por grupo (marca quadrada de severidade,
      título `group.title`, subtítulo humano com id mono truncado por
      último), strip de recorrência SVG por occurrences, chips
      severidade/estado com forma, `N×` mono, tempo relativo; visão "Cada
      disparo" mantida re-skinada.
- [x] T013 [US1] Implementar a expansão: faixa "Disparos nas últimas 24 h"
      (componente puro testado em T009a), link "investigação em andamento →"
      para `/runs/<run_id>` do disparo falante, bloco "Última causa
      encontrada:" com headline resolvido por uma leitura da listagem de
      runs por página (nunca por linha).
- [x] T014 [US1] Trocar os `<select>` por segmented controls (Estado,
      Severidade, Visão) mantendo `readViewState`/URL; linha-resumo com as
      contagens da própria listagem.
- [x] T015 [US1] Cartão de detector no rodapé lendo a fonte cravada em
      T002e; zero → ausente; CTA para a configuração de detectores.
- [x] T015a [US1] Fechar de verdade a dívida transversal herdada do S1 em
      `/incidents/{id}` (specs_v8/CONFRONTO.md §6; três das sete falhas
      pré-existentes — `markdown`/`identifier-as-name`/`two-placeholders` —
      são desta feature, as de `/runs/{id}` não): a linha fechada da lista
      agrupada carrega `data-testid="row"` com um link a um clique para
      `/incidents/{publicId}` de `group.occurrences[0]` (a occurrence mais
      nova, já ordenada primeiro por `groupBySubject`), no mesmo padrão que
      `console/src/surfaces/rows.tsx:352` já dá às demais telas "Now".
      Confirmar rodando `console/tests/e2e/transversal-rules.spec.ts` para
      `/incidents/{id}` até verde sem `test.fixme` nem entrada nova em
      `EXCEPTIONS` — Regra 7 proíbe fechar por allowlist.
- [x] T016 [US1] Chaves i18n en+pt-BR de toda string nova das QUATRO telas
      (as das fases 4–6 chegam por declaração nos relatórios) e variantes
      novas em `console/visual/screens.json`. Feito para Incidentes,
      Recursos, Conhecimento e o núcleo de O agente (T024–T026); nada de
      T023a/T026a existe para ter chave.

## Phase 4: Recursos — US2 (depende da Phase 2)

- [x] T017 [P] [US2] Reescrever
      `console/src/surfaces/screens/resources.tsx` conforme
      `Resources.dc.html`: barra de saúde segmentada + legenda clicável com
      filtro na URL; busca compacta; chips de tipo com contagem; seções por
      `node` (não saudáveis primeiro, "sem nó declarado" para placement
      desconhecido); grade de cards com ícone por tipo, forma de estado,
      visto-por-último e duração do não-saudável (`unhealthy_since`).
- [x] T018 [US2] Síntese dos não saudáveis (função pura de T009e) acima das
      seções, com "investigar em lote →" pré-preenchendo o objetivo "O que
      derrubou N <tipo> em <nó> desde <hora>?" no fluxo de investigar atual.
- [x] T019 [US2] Mover o aviso de zona/criticidade para o cartão âmbar do
      rodapé, presente só sem declaração alguma; declarar chaves i18n e
      variantes de captura no relatório.

## Phase 5: Conhecimento — US3

- [x] T020 [P] [US3] Aprendido como aba de entrada: ordem
      learned/documents/topology nas pills (reskin sobre `TabLinks`),
      `tabFrom` (`console/src/surfaces/screens/knowledge.tsx:231`) devolvendo
      `learned` no default, deep links preservados (teste unitário do
      `tabFrom` ajustado).
- [x] T021 [US3] Filtro de componente agrupado por tipo com contagens e
      normalização (módulo puro de T009b) — uma opção por identificador,
      query com valor canônico, "limpar filtro" quando o valor da URL não
      resolve mais.
- [x] T022 [US3] Cards de episódio conforme o artboard (título-frase,
      sub-linha classe+detalhe mono, chip de resultado com forma, chips de
      componente que filtram, "abrir investigação →" quando há run).
- [x] T023 [US3] Painel "O que o agente aprendeu com isso" lendo a fila de
      propostas pendentes (rota de T002c): card por proposta com origem e
      "promover a documento" para a fila de revisão; vazio honesto de duas
      frases. Faixa inferior com os dois cards-prévia (contagens de T002d e
      da listagem de documentos). Chaves i18n e capturas declaradas no
      relatório.

- [~] T023a [US3] Reformar as abas Documentos e Topologia conforme
      `design/padrao-2026-08/KnowledgeDocuments.dc.html` e
      `KnowledgeTopology.dc.html` (AN-C7): Documentos com empty state de uma
      frase + CTA duplo + revisão de propostas na aba + grid de configuração
      avançada; Topologia com grafo por vizinhança (profundidade 1–3), nó
      selecionável e rail de detalhe, empty state de uma linha. Capturas e
      chaves i18n declaradas no relatório. Encerrada sem execução: o slot
      apertou e a própria tasks.md (Implementation Strategy) nomeia esta
      dupla como a primeira a cortar antes de tocar qualquer coisa da 3
      (Incidentes). Documentos/Topologia continuam servindo o vocabulário da
      000 (tokens/ícones/chips) sem a reforma estrutural do artboard próprio.

## Phase 6: O agente — US4

- [x] T024 [P] [US4] Linha de metrô na aba Pipeline de
      `console/src/surfaces/screens/agent.tsx` a partir de
      `/v1/agent/pipeline`: seis nós com ícone, regime derivado (T009c),
      nome via `humaniseIdentifier`, microcopy de uma frase i18n; prosa
      longa fora desta visão (listagem detalhada mantida abaixo,
      re-skinada); empty/failure via `Panel` como hoje.
- [x] T025 [US4] Chip "N investigações em voo" contando runs `running` da
      listagem; realce do nó de estágio corrente condicionado à presença do
      campo na resposta (ausente → sem realce, sem erro).
- [x] T026 [US4] Três cards-resumo (Ferramentas com "X de Y", mini-barras
      top-6 domínios e chips de efeito colateral com destrutiva em vermelho;
      Autonomia com a escada das cinco classes e a perigosa em âmbar;
      Contexto do time com a barra N de M) — cada um lendo a rota que sua
      aba já lê e linkando a aba. Chaves i18n e capturas declaradas no
      relatório.
- [~] T026a [US4] Reformar as três abas conforme seus artboards (AN-A8):
      Ferramentas por `design/padrao-2026-08/AgentTools.dc.html` (rail de
      domínios com contagens, grade de cards com chip de efeito colateral e
      toggle, filtro por efeito como chips, destrutivas com borda vermelha);
      Autonomia por `AgentAutonomy.dc.html` (escada das cinco classes, uma
      frase por classe, veredito em chip, uma linha expansível com o porquê
      completo, card "Mudar a política"); Contexto do time por
      `AgentTeam.dc.html` (editor de seções com contagem de tokens por
      seção, rail com orçamento N de M e destino Investigador/Subagente).
      Mesmas rotas de dados que as abas já leem — reforma de apresentação,
      nenhuma rota nova. Encerrada sem execução: mesmo corte que T023a, pela
      mesma ordem que a Implementation Strategy autoriza (6 antes de 5, antes
      de 4, nunca antes de 3). As três abas seguem completas no vocabulário
      da 000, servindo o conteúdo integral de hoje — AN-A8's "seguem
      completas" está cumprido; a reforma estrutural própria de cada artboard
      não.

## Phase 7: Integração e fechamento

- [x] T027 Aplicar as chaves i18n e variantes de captura declaradas pelas
      fases 4–6 (dono: quem executa a integração), conferindo par en/pt-BR
      de cada uma. Sem fan-out real nesta execução (um implementer, sequencial)
      — nada para reconciliar de outro relatório; paridade conferida por
      `tests/unit/i18n/catalogue.test.ts`, verde.
- [x] T028 Rodar os quatro acceptance specs locais até verde; rodar a
      transversal (inclusive as três falhas de `/incidents/{id}` fechadas em
      T015a — verde de verdade, não por allowlist); nenhum teste afrouxado.
- [~] T029 Re-baseline visual das quatro telas
      (`python -m tools.console_visual accept`), revisar o diff de PNGs
      tela a tela contra os artboards antes de aceitar, e commitar como
      revisão consciente. Encerrada sem rodar `accept`: `console/visual/screens.json`
      foi atualizado (nova entrada `incidents-1440-light`, cinco entradas
      existentes voltaram a `pending` com o motivo escrito) mas a captura e
      o julgamento visual em si ficam para o gate do lead (Orca Browser,
      T032) — fabricar uma baseline sem revisão visual real é exatamente o
      anti-padrão que a runtime deste implementer proíbe. Confirmar em especial que `resources-1440-light` e
      `resources-320-light` (débito herdado do S1, specs_v8/CONFRONTO.md §6
      — a lista de hoje virtualiza altura fixa e não captura por inteiro em
      janela nenhuma) capturam de verdade sob a grade de cards da Fase 4;
      isso fecha aquele débito, não é um efeito colateral presumido.
- [x] T030 Gates locais do domínio editado (lint/format/typecheck do console
      e Python onde a Phase 2 tocou) e `make verify` completo verde.
- [~] T031 Fechamento do slot — do lead: sem alcance a staging/deploy desta
      worktree. `make deploy-stg COMPONENTS=app web`, aguardar Argo Synced+Healthy,
      acceptance staging-safe das quatro telas contra
      `https://stg-ninjasre.lan.kyo.ninja` via
      `tools/spec_validation browser --backing staging`.
- [~] T032 Gate visual — do lead: sem alcance a Orca Browser desta worktree.
      Capturar via Orca browser as quatro rotas nos dois
      temas (tema trocado pelo botão da topbar — tri-state, levar a uma escolha
      explícita e não presumir "um clique" troca de tema), salvar
      `evidence/visual/{incidents,resources,knowledge,agent}-{dark,light}.png`,
      escrever `evidence/visual/VEREDITO.md` — uma linha por tela×tema,
      CONFORME ou o desvio nomeado; qualquer desvio → corrigir ou registrar
      em `design/padrao-2026-08/DIVERGENCIAS.md` com aprovação do operador.
      Sem terceiro destino.
- [x] T033 Relatório final do fan-out: o que cada tela entregou, chaves
      aplicadas, contagens dos acceptance (X de Y verdes, staging incluso),
      e a lista de qualquer token/ícone declarado à 000. Entregue como a
      resposta final desta sessão ao orquestrador, e como este `controle.md`.

---

## Dependencies & Execution Order

- Phase 0 → Phase 1 → (Phase 2 ∥ Phases 3/5/6) → Phase 4 (após 2) →
  Phase 7.
- Fases 3–6 em paralelo, um implementer por tela; single-write só na 3;
  4 espera a 2; nenhuma depende de outra tela.
- Phase 7 é sequencial e fecha com o orquestrador (deploy é dele, EXECUCAO
  §3).

## Implementation Strategy

MVP = Phase 3 (Incidentes) sozinha já entrega valor e valida o vocabulário
(faixa de tempo, chips, segmented) que as outras três reutilizam. Se o slot
apertar, a ordem de corte é 6 → 5 → 4, nunca 3 — e o corte é `[~]` com
razão, não silêncio.

## Phase 8: Convergence

- [x] T034 [US2] Consertar o locator quebrado do teste "within a section,
      unhealthy cards draw before healthy ones"
      (`console/tests/e2e/resources-by-node.acceptance.spec.ts`, describe
      `AN-R4/AN-R6`): ele filtra `node-section` com
      `.filter({ has: page.locator('[data-has-unhealthy="true"]') })`, mas
      `data-has-unhealthy` é atributo do próprio `node-section`
      (`console/src/surfaces/screens/resources.tsx:611`), nunca de um
      descendente — `filter({ has })` do Playwright só casa descendente, não
      o próprio elemento, então a contagem é sempre zero e o teste sempre se
      autopula com "no unhealthy section in this dataset", em qualquer
      dataset. O dataset local `populated` tem o dado que a alegação AN-R6
      precisa: `fixtures/scenarios/populated/estate-resources.json` mostra
      node02 com 21 saudáveis/11 não saudáveis e node01 com 49/3, as duas
      seções misturadas — confirmado pelo teste vizinho ("a section holding
      unhealthy resources sorts before an all-healthy one", mesmo describe)
      passando de verdade. A metade "entre seções" de AN-R6 está provada; a
      metade "dentro da seção" nunca roda — mascarada de limite de dado
      quando é bug de seletor. Localizar a seção pelo próprio atributo
      (ex.: `page.locator('[data-testid="node-section"][data-has-unhealthy="true"]')`
      em vez de `.filter({ has })`) e confirmar que o teste passa a exercitar
      a ordenação real (verde, ou um skip de verdade motivado por dado, não
      um skip que dispara sempre).

## Phase 9: Reparos do gate visual do slot S2

Quatro desvios que o veredito visual em staging encontrou contra
`design/padrao-2026-08/`, cada um com teste vermelho-primeiro confirmado
contra o build real antes da correção.

- [x] T035 [US1] Incidentes: resolver o nome da estante para um assunto
      opaco em vez de mostrar só o id encurtado
      (`console/src/surfaces/incident-group-list.tsx`: `SubjectLine`,
      `subjectTitle`, `resolvedName` novo). A tela já buscava
      `/v1/estate/resources` para o cartão de cobertura de detector
      (`console/src/surfaces/screens/incidents.tsx`); apenas construiu, da
      mesma leitura, um mapa `resource_id -> display_name` (`subjectNames`,
      resolvido uma vez por página, nunca por linha — o mesmo padrão de
      `runHeadlines`) e passou para `IncidentGroupList`. Nenhuma mudança de
      gateway: o campo já existe em `ResourceSummaryView.display_name`
      (`gateway/http/routes/estate.py`). Um assunto que a estante
      genuinamente não tem (`cluster`, um datastore, um job de backup) não
      ganha entrada no mapa e continua a renderizar o id encurtado, nunca
      em branco. Prova: dois testes novos em
      `incidents-by-subject.acceptance.spec.ts`; confirmado vermelho contra
      o build sem o wiring (`element(s) not found` no locator
      `incident-subject-name`), verde depois.

- [x] T036 [US2] Recursos: limitar a grade por seção de nó, com o link
      "ver todos"/"ver os não saudáveis" que o board desenha
      (`console/src/surfaces/screens/resources-grouping.ts`:
      `capNodeSection`, novo, testado — uma linha (`NODE_SECTION_ROW`) quando
      nada na seção é não saudável, duas quando algo é; `console/src/surfaces/screens/resources.tsx`:
      grade renderiza `capped.shown`, não mais `section.resources` inteiro).
      A regra reproduz os dois exemplos do próprio board exatamente: pve01
      (58 recursos, 0 não saudáveis) mostra 4 e "ver os 58 recursos de
      pve01 →"; pve02 (41, 14 não saudáveis) mostra 8 e "ver os 14 não
      saudáveis de pve02 →" — o link nomeia o total de não saudáveis, nunca
      o total do nó, sempre que ainda sobra um não saudável escondido atrás
      do corte. Filtro `node` novo (`RESOURCE_FILTERS`, `FilterName = string`
      já suporta), com um valor-sentinela (`NO_NODE_FILTER_VALUE =
      'none'`) para a seção "sem nó declarado", cujo `nodeId` é a string
      vazia que `withFilter` trataria como "filtro ausente". Uma seção
      alcançada por esse filtro (`drilledIntoNode`) nunca é recortada de
      novo — foi pedida por inteiro — e ganha um link "voltar" no cabeçalho
      do painel (`action` do `Panel`, mesmo padrão do "voltar à lista" que a
      seleção de um recurso já usa). Prova: cinco testes novos em
      `resources-by-node.acceptance.spec.ts`; confirmado vermelho contra o
      build sem o corte (52 cartões numa seção, 2423px de altura no dataset
      local — o board cita 3230px em staging), verde depois (altura
      capturada: 1103px). `console/visual/screens.json`: os dois registros
      de `/resources` (1440/320) já estavam `pending`; motivo atualizado
      para não afirmar mais que a grade "não tem esse problema".

- [x] T037 [US3] Conhecimento: o desfecho do episódio usa o vocabulário
      compartilhado de status, com o chip que o board desenha
      (`console/src/surfaces/screens/memory.tsx`: `EpisodeCard` trocou o
      `<span>` calculado à mão (`outcomeShape`, binário resolvido/o-resto)
      por `StatusDot` no ponto à esquerda e o novo `OutcomeChip`
      (`ResolvedChip` + `statusPresentation`) no chip à direita — ambos
      lidos de `outcome`, nenhum mais desenhando por conta própria).
      `EPISODE_OUTCOME_LABEL` traduz as quatro palavras que
      `EpisodeOutcome` declara (`platform/persistence/ports/episode_store.py`);
      uma palavra fora desse conjunto ainda ganha papel e forma do
      vocabulário compartilhado e imprime a si mesma — o mesmo
      comportamento gracioso que `Badge` já tem para um status que o
      catálogo não conhece. Achado ao investigar, não assumido: o fixture
      que a sessão anterior corrigiu (`4ebdbee5`) tinha nivelado dois
      episódios que eram `"acknowledged"` e um que era `"unresolved"` para
      um único `"inconclusive"`; a própria tabela de tradução do seeder de
      demonstração (`platform/startup/demo/seeder.py`, `_EPISODE_OUTCOME`)
      já mapeia esse vocabulário legado para o enum real e mapeia os dois
      de forma diferente — `"acknowledged"` para `MITIGATED`,
      `"unresolved"` para `INCONCLUSIVE` — então `tools/mockplane/dataset/served.py`
      foi corrigido para seguir essa mesma tradução (dois episódios agora
      `"mitigated"`, um `"inconclusive"`) e `fixtures/scenarios/populated/episodes.json`
      regenerado por `python -m tools.mockplane build --scenario populated`,
      nunca editado à mão. `mitigated`/`false_positive` não estão em
      `console/src/design/status.ts` (congelado, decisão do lead) — um
      episódio `mitigated` real agora existe no dataset local e passa pelo
      caminho de "palavra não ensinada" (papel neutro, rótulo próprio,
      `known: false`), honesto e testado, não escondido. Prova: três
      testes novos em `learned-knowledge.acceptance.spec.ts`; confirmado
      vermelho contra o build sem o wiring (`element(s) not found` no
      locator `episode-outcome`), verde depois; corte de fio em
      `statusPresentation(outcome)` → `statusPresentation('')` reproduziu
      vermelho só no teste que fixa papel por palavra (`Received: "neutral"`
      onde esperava `"success"`), confirmando que o teste mede a tela e não
      o fixture — restaurado e reconfirmado verde.

Registrados aqui à medida que cada um fecha; ver a seção "O que fica
pendente" no `controle.md` para o estado agregado no meio da execução.
