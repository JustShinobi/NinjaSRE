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
| T009 — unitários vitest das cinco derivações | PARCIAL | (a) `incident-timeline.ts` — FEITO, testado. (b) `component-normalisation.ts` — FEITO, testado, com a correção do valor canônico (ver "achado do slot" abaixo). (e) síntese de Recursos — FEITO, dentro de `resources-grouping.ts`, testado. (c) regime do estágio e (d) contagens de efeito colateral — NÃO INICIADO, pertencem à fase de O agente que não foi alcançada. |
| T010/T011 — contrato do estate + regeneração | FEITO | Porta, Postgres (`DISTINCT ON`), fake — todos com paridade testada. `openapi.json`/`schema.ts` regenerados pelos geradores. |
| T012–T015a — Incidentes (US1) | FEITO | `incident-group-list.tsx` reescrito: `data-testid="row"` com título como link para `/incidents/{publicId}` da occurrence mais nova (FR-001/T015a), faixa 24h, bloco de causa/link ao vivo (uma leitura de `/v1/runs` por página via `subjectOf`, o módulo canônico já existente — nunca uma segunda fonte de nome), strip de recorrência. `incidents.tsx`: segmented controls (só aparecem quando há escolha real — regra "mobília" preservada), cartão de achados sem detector. **Prova**: `incidents-by-subject.acceptance.spec.ts` 11 de 14 verdes isolado (3 pulados nomeadamente, sem assunto recorrente local). `transversal-rules.spec.ts` para `/incidents/{id}`: 4 de 4 verdes isolado — as três falhas herdadas do S1 (markdown, identifier-as-name, two-placeholders) e a quarta regra (negative-assertion) todas fecham de verdade, sem allowlist. |
| T016 — i18n single-write das quatro telas | PARCIAL | Chaves de Incidentes/Recursos/Conhecimento aplicadas em `en.ts`+`pt-BR.ts`, paridade mantida (`catalogue.test.ts` verde). Chaves de O agente pendentes — fase não alcançada. |
| T017–T019 — Recursos (US2) | FEITO | `resources-grouping.ts` (novo, testado): `healthSegments`, `groupByNode`, `unhealthySynthesis`. `resources.tsx` reescrito: barra de saúde segmentada com "N vigiados" + legenda clicável, busca compacta, chips de tipo com contagem, seções por nó (não-saudáveis primeiro, dentro e entre seções), síntese em lote, aviso de zona/criticidade no rodapé, painel `undeclared` (achado de divergência que o grid de cards não tinha mais onde marcar por linha — ver "achado do slot"). **Prova**: `resources-by-node.acceptance.spec.ts` 9 de 13 verdes isolado (4 pulados nomeadamente: quatro estados simultâneos e `unhealthy_since` são fatos que só staging tem). |
| T020–T023 — Conhecimento (US3) | FEITO | `component-normalisation.ts` (novo, testado, com a correção de valor canônico). `memory.tsx` reescrito: Aprendido como aba padrão (`knowledge.tsx` `tabFrom`), episódios como cards com chip de resultado moldado, filtro de componente agrupado por tipo (consulta ao servidor por spelling bruto real, nunca sintetizado — ver achado abaixo), painel "o que o agente aprendeu" lendo `/v1/proposals` filtrado a `proposal_type==='knowledge'`, faixa inferior com Documentos/Topologia. **Prova**: `learned-knowledge.acceptance.spec.ts` 13 de 14 verdes isolado (1 pulado nomeadamente). |
| T023a — reforma de Documentos/Topologia | `[~]` cortado | Onda autoriza este corte primeiro, antes de tocar Incidentes (Implementation Strategy do tasks.md). Documentos/Topologia continuam com o vocabulário da 000 (tokens/chips/ícones), sem a reforma estrutural do artboard próprio — inclusive o `<select>` de "kind" do Documents, que `AN-T1` por isso mede só em Aprendido. |
| T024–T026a — O agente (US4) | NÃO INICIADO | Não alcançado neste ciclo — ver "o que fica pendente". |
| T027–T033 — integração e fechamento | PARCIAL | Ver tabela de gates abaixo; T031/T032 são do lead. |

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

- **T024–T026a (O agente, US4) — não iniciado.** A linha de metrô, o chip
  "N investigações em voo", os três cards-resumo e a reforma das três abas
  (Ferramentas/Autonomia/Contexto do time) não foram construídos. O
  `agent-pipeline.acceptance.spec.ts` (T007) existe e está vermelho — não
  fechado.
- **T023a (Documentos/Topologia) — cortado deliberadamente**, primeiro na
  ordem que a própria tasks.md autoriza.
- **T009 (c)/(d)** — regime do estágio e contagens de efeito colateral —
  pertencem a O agente, não feitas.
- **T016 parcial** — chaves de O agente pendentes.
- **T027–T030, T033** — integração final, re-baseline visual local e relatório
  do fan-out não feitos; dependem de T024–T026a existirem primeiro.
- **T031/T032** — do lead (staging, Orca browser).
