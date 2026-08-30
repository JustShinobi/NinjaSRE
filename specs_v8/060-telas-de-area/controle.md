# Controle — Telas de área (slot S2)

Estado abaixo verificado contra o código real desta árvore, não contra a
intenção. Escrito e atualizado a cada commit — não só no relatório final.

## Peça | Estado | Detalhe

| Peça | Estado | Detalhe |
|---|---|---|
| T001 — baseline `make verify` | FEITO | Verde antes de qualquer mudança: Python 0 falhas (log completo salvo fora do repo), console `190 arquivos / 3138 testes` verdes. Log real conferido, não a notificação de fundo. |
| T002 — caracterização (Fase 0) | FEITO | `specs_v8/060-telas-de-area/evidence/caracterizacao.md` — rota/campo de Recursos (`parent_name` já existe, bug de confiabilidade; `unhealthy_since` não existe), episódios, propostas, topologia, e a fonte de "achados sem detector" (não encontrada pronta — decisão registrada). |
| T003 — capturas "antes" no staging | Fora do escopo desta worktree (`[~]`) | Sem alcance a staging/Orca por aqui; o lead confirmou que já rodou e comitou as oito capturas em `evidence/visual/antes/`. |
| T004 — acceptance Incidentes red-first | FEITO (vermelho confirmado) | `console/tests/e2e/incidents-by-subject.acceptance.spec.ts`. Rodado contra `tools.mockplane console --scenario populated` local; 18 de 21 blocos observados vermelhos por falta real (nenhum `data-testid` do feature existe ainda), nenhum passou por medir nada — nenhum vazio verde entre os observados. |
| T005 — acceptance Recursos red-first | FEITO (vermelho confirmado) | `console/tests/e2e/resources-by-node.acceptance.spec.ts`. Rodado com timeout reduzido (8s) contra o mock local: todos os blocos vermelhos por falta real (nenhum `data-testid` do feature existe ainda). |
| T006 — acceptance Conhecimento red-first | FEITO (vermelho confirmado) | `console/tests/e2e/learned-knowledge.acceptance.spec.ts`. Rodado com timeout reduzido (8s): todos os blocos vermelhos por falta real, 1 pulado nomeadamente. |
| T007 — acceptance O agente red-first | FEITO (vermelho confirmado) | `console/tests/e2e/agent-pipeline.acceptance.spec.ts`. Rodado; 18 vermelhos reais + 2 achados de teste vazio (passavam sem medir nada porque `pipeline-metro-node`/`side-effect-chip` contam zero elementos hoje) — corrigidos para exigir contagem mínima antes de iterar, e reconfirmados vermelhos por leitura direta (`node:154` e `:59`, rodados isolados após a correção). |
| T008 — contrato pytest (node/unhealthy_since) | FEITO | Vermelho confirmado e depois fechado: `tests/contract/persistence/test_estate_repository.py` (unhealthy_since em lote, fakes), `tests/unit/platform/estate/test_estate_service.py` (novo — `parent_name` fora da página, `unhealthy_since` propagado), `tests/unit/gateway/http/test_estate_routes.py` (dois novos, no fio HTTP real). 328 testes relacionados a estate verdes, `mypy` limpo nos 5 arquivos tocados. |
| T009 — unitários vitest (faixa 24h, normalização, regime, efeito colateral, síntese) | NÃO INICIADO | |
| T010/T011 — contrato do estate + regeneração | FEITO | `platform/persistence/ports/estate_repository.py` ganhou `unhealthy_since` no protocolo; Postgres (`DISTINCT ON`, mesmo padrão de `signal_store.py:111`) e fake implementados. `EstateService.query()` resolve `parent_name` em lote para os pais fora da página (nunca mais depende de coincidência) e popula `ResourceView.unhealthy_since` só para o que está unhealthy agora. `ResourceSummaryView` ganhou o campo; `fixtures/contract/openapi.json` e `console/src/api/schema.ts` regenerados pelos geradores (`python -m tools.mockplane contract`, `make console-client`), nunca editados à mão. |
| T012–T016 — Incidentes (US1) | NÃO INICIADO | |
| T017–T019 — Recursos (US2) | NÃO INICIADO | |
| T020–T023a — Conhecimento (US3) | NÃO INICIADO | |
| T024–T026a — O agente (US4) | NÃO INICIADO | |
| T012–T015a — Incidentes (US1) | FEITO | `console/src/surfaces/incident-group-list.tsx` reescrito: `<li data-testid="row">` com o título como `<a>` para `/incidents/{publicId}` da occurrence mais nova (FR-001/T015a), faixa 24h (`incident-timeline.ts`, testado por unidade), bloco de causa/link ao vivo lendo `/v1/runs` uma vez por página via `subjectOf` (o módulo canônico de nome de run já existente, não uma segunda fonte), strip de recorrência SVG. `console/src/surfaces/screens/incidents.tsx`: segmented controls (`SegmentedLinks`, novo em `components/navigation.tsx`) no lugar de `<select>`, cartão de achados sem detector (`detector-coverage-gap.ts`, testado). **Prova real, não inferida**: `incidents-by-subject.acceptance.spec.ts` — 10 de 14 verdes, 3 pulados nomeadamente (sem assunto recorrente no dataset local), 1 corrigido para pular do mesmo jeito (SC-001). `transversal-rules.spec.ts` completo: 39 verdes, 6 falhas — **nenhuma em `/incidents` ou `/incidents/{id}`**, todas em `/runs/{id}` (herdadas, não desta feature, confirmado por leitura) e na regra de progresso do setup (não relacionada). As três falhas que T015a prometeu fechar (`markdown`, `identifier-as-name`, `two-placeholders` em `/incidents/{id}`) rodadas isoladas e verdes. |
| T017–T019 — Recursos (US2) | FEITO | `console/src/surfaces/screens/resources-grouping.ts` (novo, testado: `healthSegments`, `groupByNode`, `unhealthySynthesis`). `resources.tsx` reescrito: barra de saúde segmentada com legenda clicável (URL), busca compacta, chips de tipo com contagem (chip "Todos" com testid próprio, sem contagem por natureza), seções por nó com não-saudáveis primeiro (dentro e entre seções), síntese em lote (3+, mesmo nó/tipo/janela de 30min), aviso de zona/criticidade movido para cartão âmbar no rodapé. Painéis de detalhe (sinais/documentos/mudanças) e de divergência mantidos como estavam — sem artboard próprio, decisão 8. **Prova real**: `resources-by-node.acceptance.spec.ts` — 9 de 13 verdes, 4 pulados nomeadamente (dataset local sem os 4 estados de saúde simultâneos, sem `unhealthy_since` — campo novo que o fixture local antecede). `transversal-rules.spec.ts` sem regressão (mesmas 6 falhas pré-existentes de sempre, nenhuma em `/resources`). |
| T027–T033 — integração e fechamento | NÃO INICIADO | |

## Achado desde já, para não se perder

- **`console/src/components/navigation.tsx` ganhou `SegmentedLinks`** (+
  export em `components/index.ts`) — primitiva nova, não um arquivo
  congelado (só `design/tokens.ts`, `icons.tsx`, `components/status.tsx` e as
  fontes são da 000). As quatro telas precisam do mesmo padrão (filtro sem
  `<select>`, estado na URL) e `FilterBar`/`Select` são compartilhados com
  toda tela fora desta feature — mexer neles reformaria telas sem artboard.
  Um componente novo, ao lado de `TabLinks` (mesmo padrão de link com estado
  na URL), evita isso.
- **Achados de Fase 0 que mudam a Fase 2**: `ResourceSummaryView` já declara
  `parent_id`/`parent_name` — FR-006 não pede um campo `node` novo, pede
  corrigir `EstateService.query()` para resolver o pai mesmo fora da página
  atual. `unhealthy_since` é genuinamente novo, com a fonte já existente
  (`HealthTransitionRow`) mas sem método em lote.
- **"achados degradados sem detector" (FR-005/AN-I9) não tem fonte pronta**
  em lugar nenhum do código — busca exaustiva registrada em
  `evidence/caracterizacao.md`. Decisão tomada: computado nesta feature,
  função pura testada, para a 050 reusar.
- **Dataset local (`populated`) não tem assunto recorrente** (10 incidentes,
  todos count=1) nem componente `container:`/`guest:` duplicado nos
  episódios, nem proposta `knowledge` pendente. As alegações que dependem
  disso são `@staging-safe` e/ou testadas por unidade com dado sintético
  (T009), nunca inventadas como passando localmente.

## Correção de método, registrada para quem retomar

`tools.mockplane console` (que este relatório usou nas primeiras corridas)
**não serve o console React** — serve `surfaces/console` (a UI antiga
renderizada em Python, tema azul, `surfaces/console/theme.py`, exatamente o
que DIVERGENCIAS.md item 5 chama de "outra era"). Os testes contra ele
voltavam sempre para a tela de login (cookie de sessão de nome diferente,
`ninjasre_console_session` vs `ninjasre_session` que os specs esperam) e
qualquer "vermelho" medido assim não provava nada sobre esta feature. A
ferramenta certa, e a única usada a partir do commit `a5b70669`, é
`python -m tools.console_e2e run --backing mock --scenario populated -- <args
do Playwright>` — que compila `.next/standalone` (exige `make console-build`
ou `python -m tools.console_gate build` antes, a cada mudança de código; não
há rebuild automático) e serve o console de verdade contra o mock. Perdido
tempo real com isso; fica registrado para não repetir.

## O que fica pendente, nomeado, não escondido

Tudo do Phase 2 em diante — ver tabela acima. Nada foi implementado ainda
além dos testes de aceitação e da caracterização.
