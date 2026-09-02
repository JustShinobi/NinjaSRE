# Caracterização (Fase 0) — antes de qualquer implementação

Lido em código nesta árvore (base `083fca3a`). Cada item cita `file:line`.

## (a) Rota/handler que `ResourcesScreen` consome, e campos atuais

- Rota: `GET /v1/estate/resources` → `list_resources`
  (`gateway/http/routes/estate.py:535-`), `response_model=ResourceListView`
  (`:117`), item = `ResourceSummaryView` (`:83-115`).
- `ResourceSummaryView` **já declara** `parent_id: str | None` (`:102`) e
  `parent_name: str = ""` (`:103-105`, comentário: "The parent's display name
  when the same read produced it, empty otherwise. A table shows this rather
  than the parent's identifier."). **Não existe campo `node` a criar** — o
  campo que FR-006 chama de "node" já é `parent_name`; o defeito é de
  confiabilidade no preenchimento, não de ausência de campo.
- A causa raiz: `EstateService.query()` (`platform/estate/service.py:123-134`)
  resolve `parent_name` só quando o pai calha de estar **na mesma página**
  (`names = {resource.resource_id: r.display_name for r in found}`, `:133`,
  passado como `parent_names` a `_view`). Um filtro por saúde que exclui os nós
  saudáveis (ex.: `health=unhealthy`) deixa `parent_name` vazio para toda a
  página. `_view` só usa o mapa passado (`:274-308`), nunca busca o pai fora
  dele.
- `unhealthy_since` **não existe em lugar nenhum do contrato hoje** —
  confirmado por leitura de `ResourceView` (`platform/estate/service.py:51-76`,
  sem esse campo) e de `ResourceSummaryView` (idem). A fonte existe como
  histórico: `HealthTransitionRow`
  (`platform/persistence/postgres/models.py:759-777`, índice
  `ix_estate_transitions_resource(org_id, resource_id, occurred_at)`) e o
  método `transitions(resource_id, limit)` (porta:567-574; Postgres:439-458;
  fake:230-242) — mas é **por recurso**, não em lote, e nenhuma tela hoje o lê
  na listagem. Fechado com um método novo em lote (Fase 2, abaixo).

## (b) Rota de episódios (aba Aprendido) e seus campos

- Rota: `GET /v1/memory/search?component=` → `search_memory`
  (`gateway/http/routes/memory.py:71-84`), item = `EpisodeView`
  (`:22-34`): `episode_id`, `title`, `summary`, `outcome`, `components:
  list[str]`, `occurred_at`, `run_id`.
- **Não existe campo "classe do episódio" separado.** O `Episode` do domínio
  (`platform/persistence/ports/episode_store.py:55-68`) carrega `tags` e
  `metadata`, mas `EpisodeView`/`_view()` (`memory.py:60-68`) não os serve. A
  "classe + detalhe mono" do artboard (AN-C3) é lida deste feature como o
  próprio `summary` (a única prosa estruturada que a resposta de fato
  carrega) — nenhum campo novo pedido ao backend, condizente com o plano
  ("Conhecimento é reorganização... nenhum endpoint novo").
- Vocabulário real de `components`: strings livres vindas do episódio
  (`platform/persistence/ports/episode_store.py:65`); no staging carrega
  `container:<id>` e `guest:<id>` para o mesmo id (fato 6 da spec).

## (c) Rota da fila de propostas de conhecimento

- Rota: `GET /v1/proposals` → `list_proposals`
  (`gateway/http/routes/proposals.py:239-256`), já **filtrada a `pending`**
  pelo próprio serviço (`queue.pending(limit=...)`), sem parâmetro de tipo.
  Item = `ProposalView` (`:60-82`): `proposal_id`, `proposal_type`,
  `node_id`, `summary`, `rationale`, `evidence`, `run_id`, `correlation_id`,
  `state`, `proposed_at`.
- `ProposalType.KNOWLEDGE = "knowledge"` (`platform/proposals/models.py:73-76`).
  Uma proposta de conhecimento pendente filtra-se no cliente por
  `proposal_type === 'knowledge'` sobre a mesma leitura — sem endpoint novo,
  sem segunda fonte da fila (a mesma que `/decisions?tab=changes` já lê).
- "promover a documento": mantido como link para a fila existente
  (`/decisions?tab=changes`), no mesmo padrão que `DocumentsTab` já usa
  (`console/src/surfaces/screens/knowledge.tsx:196-208`) — não há parâmetro de
  seleção por proposta na aba de mudanças hoje.

## (d) Campo de contagem que a topologia devolve

- Rota: `GET /v1/topology/{node_id}` (único endpoint;
  `gateway/http/routes/topology.py:63`), sem endpoint de resumo do grafo
  inteiro. **Não existe uma contagem "nós que a topologia registrou"
  pronta.** Aproximação adotada (declarada, não inventada como fato): o card
  de prévia (AN-C5) lê `/v1/topology/root` (o nó padrão que `TopologyTab` já
  usa, `console/src/surfaces/screens/topology.tsx:59`) e conta a união de
  `dependencies`+`dependents` como "nós observados". Nenhum endpoint novo;
  assunção registrada no relatório final.

## (e) Onde nasce "achados degradados sem detector"

- **Busca exaustiva, sem resultado de uma fonte pronta.** `dashboard.tsx` usa
  `detectorRecords.length`/`liveDetectors` só para contextualizar a contagem
  de `degraded` (quantos detectores existem/estão ligados), nunca "quantos
  achados degradados NENHUM detector cobre" — são perguntas diferentes.
  `DetectorService.observations()` (`platform/incidents/service.py:246-263`)
  devolve o que os detectores **ligados** concluem agora — o conjunto
  coberto, não o não-coberto. `DetectorView.subjects_covered/subjects_total`
  (`platform/incidents/service.py:76-89`) é cobertura por detector sobre o
  estate, não por recurso individual sem nenhum detector.
- **Decisão tomada e registrada**: computado nesta feature como `recursos com
  saúde degraded/unhealthy` menos `resource_id`s presentes em
  `/v1/incidents/observations` (achados que detectores ligados produziram
  agora) — a definição mais direta de "degradado que nenhum detector
  observou". Função pura, testada, exportada de
  `console/src/surfaces/screens/incidents-detector-gap.ts` para que a 050
  (Painel) possa reusá-la quando for construída — decisão 3 da v7 ("uma fonte
  por fato") cumprida pela reusabilidade, não por uma fonte pré-existente que
  não foi encontrada. Isto é uma leitura de código que não achou o que a spec
  presumiu existir, e é dito aqui sem eufemismo.

## Débito transversal herdado do S1 (FR-001/T015a) — mecanismo exato

- `console/tests/e2e/transversal-rules.spec.ts:601-620` (`openNowLabel`):
  para `/incidents/{id}`, navega a `/incidents`,
  `page.getByTestId('row').first().locator('a').first().click()`.
- `console/src/surfaces/rows.tsx:352-384` (`RowList`): todo `<tr
  data-testid="row">` genérico tem, na primeira célula, `<NextLink
  href={row.href}>` envolvendo o valor — o padrão a replicar.
- `console/src/surfaces/incident-group-list.tsx` hoje: o `<li>` carrega
  `data-testid="incident-group"` (não `row`) e o único link para
  `/incidents/{publicId}` de cada occurrence vive dentro do corpo do
  `<details>` (fechado por padrão, inacessível a um clique). O título
  (`:120`) é um `<span>`, não um link.
- **Fechamento**: `data-testid="incident-group"` (+ `data-live`/`data-count`)
  move do `<li>` para o `<details>` que já envolve o mesmo conteúdo — os
  testes existentes (`incident-group-list.test.tsx:99-108`,
  `dashboard.test.tsx:675`) só pedem que o elemento com esse testid **contenha**
  os testids/textos internos, nunca a tag exata, então o descolamento é
  seguro. O `<li>` externo ganha `data-testid="row"` + `data-row={group.key}`.
  O título dentro do `<summary>` (sempre visível mesmo fechado) vira `<a
  href={"/incidents/" + group.occurrences[0].publicId}>` — o primeiro link do
  `row`, um clique, sem expandir. `group.occurrences[0]` já é a mais nova
  (ordenado por `groupBySubject`, `incident-groups.ts:70-71`.129-134`).

Nenhuma implementação foi feita antes deste registro.
