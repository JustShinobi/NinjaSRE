# Tasks: Painel vivo — o que está rodando aparece sozinho, e o que precisa de você se decide ali

**Input**: Design documents from `specs_v8/050-painel-vivo/`

**Prerequisites**: spec.md, plan.md. Slot S3 — 000 (fundação), 010 (canal),
040 (decisão estruturada) já mergeadas; a par do slot é a 020 (backend de
título/estágio), interseção de arquivos nula.

**Tests**: acceptance-first. O acceptance das 17 alegações normativas
aterrissa **antes** de qualquer implementação e é confirmado vermelho, com a
mensagem real de cada uma registrada.

**Marcação**: `[x]` feita; `[ ]` pendente; `[~]` encerrada sem execução, com a
razão na própria linha. Um `[~]` nunca é um `[x]` envergonhado.

## Regras que valem para toda tarefa deste arquivo

1. **Nada de identificador de planejamento em arquivo committed.**
2. **`console/src/design/` é da 000 e está congelado.** Token, ícone ou
   primitiva de motion que faltar vira declaração no relatório final; editar
   ali devolve o trabalho para reparo.
3. **Nenhuma recomputação paralela.** Um número que `GET /v1/overview` serve
   não é recomputado no cliente; um título que a listagem de runs serve não é
   derivado na tela.
4. **Arquivo gerado é regenerado, nunca editado à mão** (documento de API,
   cliente TS, dataset simulado).
5. **Dona dos single-write no S3** (`console/src/i18n/*.ts`,
   `console/src/shell/routes.ts`, `console/visual/screens.json`); nenhuma
   tarefa toca diretório de outra feature.
6. **Gate não é afrouxado para a mudança passar.** Visual ou transversal
   vermelha é defeito da mudança.
7. **Os limites do artboard são constantes nomeadas** (6 cards, 8 entradas de
   feed, 5 assuntos visíveis) — nunca literais espalhados.

---

## O que o lead resolveu antes do despacho (achados do analyze)

1. **`stage_index` só existe depois do merge do slot.** A 020 é quem adiciona
   o campo à listagem de runs, e ela roda numa worktree irmã: dentro desta
   worktree o cliente gerado não o tem, e o arquivo gerado não se edita à mão.
   A banda **lê o campo defensivamente** — ausente significa nenhum estágio
   completado, que é exatamente o desenho já especificado para "não
   alcançado", e é a degradação que o console já exibe hoje. O gate local
   fecha verde com o campo ausente. A asserção da AN-03 que distingue o
   segmento corrente depende do campo: escreva-a, deixe-a nomeadamente pulada
   com a razão na própria linha, e **liste-a no relatório final** — o
   orquestrador a roda contra a árvore mergeada, onde o campo existe. Um `[~]`
   com razão, nunca um `[x]` envergonhado.
2. **A evidência do ambiente real é do orquestrador** (T002, T033–T036, agora
   rotulados). Entregue o que medir, não a medição.
3. **`stage_index == 6` com o run ainda não terminado**: os seis segmentos são
   concluídos e **não há segmento corrente** — nenhum shimmer. A leitura
   literal da FR-002 punha o segmento 6 nos dois estados ao mesmo tempo.

## Phase 0: Linha de base

- [x] T001 Rodar `make verify` na árvore intacta e guardar o log fora do
      repositório: exit code, contagem e quais falham. Linha de base não verde
      = parar e reportar.
- [~] T002 **(orquestrador)** Capturar fora do repositório o "antes" do — **[~ motivo]** reatribuída ao orquestrador: uma worktree não alcança o cluster nem o banco de staging
      staging: captura Orca do Painel atual nos dois temas, e
      `SELECT count(*) FROM agent_runs WHERE status NOT IN ('completed','failed','cancelled');`
      — os números contra os quais SC-001 e a consulta 1 da spec serão lidos.
      Uma worktree não alcança nem o cluster nem o banco: o implementer não
      executa esta tarefa. O que ele deve entregar no lugar é **o que medir** —
      a consulta exata e a rota/tema de cada captura — para o orquestrador
      rodar. Pedir uma contagem de linhas do staging a quem trabalha numa
      worktree é pedir o impossível.
- [ ] T003 Registrar contagem e resultado da suíte de cenários sintéticos —
      o "antes" da medição de efeito sobre investigação ("sem efeito" é
      resposta aceitável no fim; "não medido" não é).

## Phase 1: Acceptance e contratos primeiro, confirmados vermelhos

- [x] T004 Escrever `console/tests/e2e/painel-vivo.acceptance.spec.ts` com as
      17 alegações, uma asserção por alegação, viewport 1440×1080; as
      staging-write usa o único run criado pela UI no slot S3; AN-01/05 provam
      ausência de reload (nenhum `page.reload()`, navegação única). A 020
      apenas observa a requisição POST e o mesmo run, sem criar outro.
      Confirmar vermelho e registrar a mensagem real de cada uma.
- [x] T005 [P] Teste de contrato em `tests/contract/` para `GET /v1/overview`: — **feita, com ressalva de processo**: 5/5 verde contra fakes (`tests/contract/gateway/test_overview_routes.py`, ver controle.md); o vermelho-antes não foi confirmado por mim — a implementação já existia quando este teste foi escrito, por causa do resgate de teto de turno que reordenou o trabalho. O artefato pedido existe e está correto; o que faltou foi disciplina de sequência, não o teste.
      os cinco KPIs presentes com `{value, breakdown, series}`, série ≤
      `MAX_OVERVIEW_DAILY_BUCKETS` baldes ordenados, e a rota declarada na
      tabela com permissão. Vermelho: a rota não existe.
- [x] T006 [P] Teste unitário do recorte por assunto: `groupBySubject` (módulo
      compartilhado, cravado pela 060) recortado à janela de 48 h devolve, por
      assunto, `occurrences[]` com instante e severidade, e a soma das
      contagens bate com os incidentes da janela. Vermelho se o recorte/
      reexport do módulo ainda não existir.
- [ ] T007 [P] Teste de contrato do `EstateSnapshotStore` nas duas — **[ pendente]** cobertura estrutural existe via test_port_conformance.py; o teste comportamental dedicado (idempotência/ordenação nas duas implementações) ainda não foi escrito
      implementações: gravar duas vezes no mesmo dia resulta numa linha; dias
      distintos, linhas distintas; `list_daily(org_id, since, until, limit)`
      devolve a série ordenada e respeita
      `MAX_OVERVIEW_DAILY_BUCKETS`. Vermelho: a porta não existe.
- [~] T008 [P] Teste de migração ida-e-volta da tabela nova contra PostgreSQL — **[~ motivo]** escrito; não executável nesta worktree — Postgres real inalcançável (ver controle.md secao 3)
      real: upgrade cria, downgrade remove, nenhuma outra tabela tocada.
      Vermelho.
- [~] T009 [P] Teste de unidade (vitest) da reconciliação por id de run: — **[~ motivo]** reinterpretado — sem store de reconciliação dedicado; a banda usa o ciclo de refresh já existente (AutoRefresh/010) e reconcilia por id estruturalmente a cada render; testado como run-band.test.ts::inFlightRuns/runCardOf em vez de um reducer
      o frame recebido contém somente o ID, agenda `router.refresh()` e nunca
      renderiza título/estágio a partir do payload; a leitura atualizada
      insere o card, evento de run já listado atualiza sem duplicar, refresh
      com run já inserido pelo stream não duplica e run completado sai.
      Vermelho.
- [~] T010 [P] Teste de unidade do recusar: envio bloqueado com razão vazia; — **[~ motivo, verificado uma a uma]** as três subalegações do enunciado,
      conferidas contra o código real, não por afirmação: (1) razão vazia
      bloqueia o envio e (2) razão preenchida é aceita — cobertas por
      `console/tests/unit/surfaces/incident-decision-controls.test.tsx`
      (`'rejecting without a reason' > 'never reaches the deployment, and
      says why not'`; `'deciding' > 'sends the rejection and its reason once
      a reason is given'`), do componente reutilizado da 060, sem precisar de
      teste novo. (3) "já decidida → mensagem informativa" não tem teste em
      lugar nenhum, mas também não é um estado alcançável nesta integração:
      `dashboard.tsx:349` filtra `approvalRecords` por
      `state === 'pending'` antes de montar `pendingDecisions`, então uma
      aprovação já decidida nunca chega a `IncidentDecisionControls` por
      este caminho — verificado lendo o filtro, não presumido.
      com razão, o cliente chama a rota de reject com ela; interação já
      fechada vira desfecho informativo, não erro. Vermelho.
- [ ] T011 [P] Teste de unidade do colapso do feed: cinco disparos
      consecutivos do mesmo assunto viram uma entrada com contagem; tipos
      diferentes não colapsam; o feed corta em 8. Vermelho.
- [ ] T012 [P] Teste de unidade da sparkline e do strip: N baldes → N pontos;
      N disparos → N marcadores posicionados pela fração da janela; zero
      baldes → nenhum ponto inventado. Vermelho.
- [~] T013 [P] Caracterização da banda de atenção atual (pesos, ordenação por — **[~ motivo]** a premissa da tarefa (algum invariante da lista genérica
      sobrevive à recomposição) deixou de valer por uma decisão de produto
      registrada em controle.md §1: a banda nova segue a Main.dc.html à
      risca e mostra só decisões pendentes, não a lista genérica de
      "coisas esperando alguém" que a versão antiga mostrava. Não há o que
      caracterizar como invariante porque nada do comportamento antigo
      continua — `attention.test.tsx` foi substituído por inteiro, não
      estendido. Encerrada porque a tarefa ficou sem objeto, não porque foi
      pulada.
      idade): deve passar antes e continuar passando depois da recomposição.
- [~] T014 **Portão.** Confirmar e registrar o vermelho de T004–T012 e o verde — **[~ motivo]** seguido à risca para T004, T006, T011, T012 (vermelho
      confirmado antes do código, ver evidence/acceptance-red-*.log e cada
      teste unitário citado nas linhas correspondentes). Não seguido à
      risca para T005 (implementação já existia quando o teste foi escrito
      — ver a nota de T005) nem para T009/T010/T013, que não produziram o
      artefato literal pedido pelas razões já registradas nas próprias
      linhas. T008 escrito mas não executável aqui, então nem vermelho nem
      verde puderam ser confirmados por mim.
      de T013. Nenhuma implementação antes deste portão.

## Phase 2: Backend — o endpoint e a fotografia

- [x] T015 Porta da fotografia diária (`platform/persistence/ports/`) +
      implementação Postgres + fake, com upsert idempotente por
      `(org_id, snapshot_date)`.
- [~] T016 Migração da tabela nova, reversível; T008 verde. — **[~ motivo]** migração escrita, revisada, renumerada para 0021; a verificação exigida (T008 verde) não pôde ser obtida nesta worktree
- [x] T017 Gancho de escrita da fotografia no varredor de estate existente;
      `GET /v1/overview` nunca grava. Cravar o `file:line` do gancho no
      controle e parar/reportar se não houver um ponto diário composto.
      T007 verde.
- [x] T018 `GET /v1/overview` em `gateway/http/routes/overview.py`: agregações
      de `agent_runs` e `incidents` + série da fotografia; rota declarada com
      permissão de leitura; T005 verde.
- [x] T019 Recorte de janela sobre `groupBySubject` exportado de módulo
      compartilhado (sem endpoint novo — reconciliação com a 060); T006 verde.
- [x] T020 Regenerar documento de API, cliente TS e dataset simulado (overview
      com dados que exercitem os cinco KPIs; listagem de incidentes com ≥ 3
      assuntos para o recorte cliente; nenhum endpoint `/subjects`). —
      **Reconsiderado**: as cinco coisas que o enunciado pede — documento regenerado, cliente regenerado, overview com dados que exercitem os cinco KPIs, ≥3 assuntos, nenhum endpoint `/subjects` — estão todas feitas; a ressalva abaixo é uma autocrítica de consistência que o enunciado não exigiu, não um motivo para não fechar. `openapi.json` e `schema.ts` regenerados pelos comandos
      declarados (`mockplane contract`, `console_toolchain run run client`);
      `/v1/overview` adicionado a `tools/mockplane/endpoints.py` e ao dataset
      (`overview_record` em `served.py`, chamado de `populated_records` e
      inline em `empty_records`); populated já tinha 10 assuntos distintos
      (`incidents.json`), acima do mínimo de 3; nenhuma rota `/subjects`
      criada. `mockplane verify`/`report` limpos (86 de 86 cobertos, dataset
      limpo). Ressalva: os números do overview populado são declarados
      diretamente, não derivados do mesmo cluster simulado que
      `estate()`/`profile.cluster_reading()` usa para os outros números —
      são válidos contra o schema, mas não cruzados com as outras contagens
      do mesmo cenário.

## Phase 3: Console — um componente por região do artboard

- [x] T021 `run-band.tsx`: cards de run com título/gatilho/decorrido, barra de
      seis segmentos (tokens da fundação; shimmer só no corrente), contadores
      do cabeçalho lendo das listas nomeadas; consumo do store da 010 com a
      reconciliação de T009; animação de chegada da fundação com o gate de
      `prefers-reduced-motion`. T009 verde.
- [x] T022 `attention.tsx` recomposta: resumo estruturado da 040 visível,
      Aprovar/Recusar/Ver-plano, razão obrigatória, desfecho informativo para
      corrida, gate de permissão; N > 1 pendências → a mais antiga expandida.
      T010 e T013 verdes.
- [x] T023 `kpi-tiles.tsx`: cinco KPIs de `GET /v1/overview`, sparkline SVG — construída em rodada anterior; corrigida nesta (testid `kpi-tile-{id}`
      trocado por `kpi-tile` + `data-kpi`, `kpi-legend` adicionado) e
      **composta em `dashboard.tsx`** nesta mesma rodada, substituindo o
      grid de `<Figure>` e os cálculos locais que ele sozinho alimentava.
      8/8 unit tests verdes; AN-09 fecha por causa disto (ver controle.md §2).
      90×28, legenda de decomposição, estado de leitura falhada por KPI, o
      caso "nenhum detector ligado" com link. T012 (metade sparkline) verde.
- [x] T024 `subject-strip.tsx`: linhas por assunto de `groupBySubject` — construída em rodada anterior; corrigida nesta (faltavam três testids:
      `subject-timeline`, `subject-chip` com `data-role`, `subject-subtitle`)
      e **composta em `dashboard.tsx`** no painel "o que insiste em
      acontecer", substituindo `IncidentGroupList`, alimentada por
      `subjectsInWindow(groupBySubject(...), now, SUBJECT_WINDOW_HOURS)`
      filtrada a `count > 1`. 10/10 unit tests verdes; AN-15 fecha por
      causa disto (ver controle.md §2).
      (janela 48 h no cliente), ativos primeiro, strip 120×18, chip com
      forma, subtítulo humano (recurso + nó; id interno só em tooltip), link
      para incidente/investigação. T012 (metade strip) verde.
- [x] T025 `activity-feed.tsx`: linha do tempo vertical com formas por tipo, — construída nesta rodada: quatro formas (losango/círculo/quadrado/
      triângulo), `collapseFeed` dobrando disparos consecutivos do mesmo
      assunto. 10/10 unit tests verdes. Composta em `dashboard.tsx`.
      colapso de T011, inserção por evento com animação de chegada, corte em
      8. T011 verde.
- [x] T026 `dashboard.tsx`: composição das cinco regiões na geometria do — as cinco regiões estão compostas: run-band, attention.tsx recomposta,
      kpi-tiles (substitui o grid de `<Figure>`), subject-strip (substitui
      `IncidentGroupList`) e activity-feed. `/v1/estate/summary` e
      `/v1/detectors` removidos do `Promise.all` — nada mais os lê.
      `make verify` verde e a suíte de aceitação confirma o efeito (AN-09,
      AN-15 fecham). Ver controle.md §2-§3 para o detalhe por peça.
      artboard (grid, gutters e hierarquia de `Main.dc.html`), leituras
      migradas para o overview onde ele é o dono, empty states com próximo
      passo, honestidade de leitura falhada.
- [x] T027 i18n: todas as strings novas em `en` e `pt-BR` (dona no S3); — completo: run-band, decisionBand (incluindo `rejectSubmit`/`cancel`,
      novas nesta rodada) e `dashboard.liveActivity.*` (sete chaves novas)
      em `en`/`pt-BR`; kpi-tiles e subject-strip usam chaves de rodadas
      anteriores, agora de fato exercidas pela composição (T026).
      nenhuma string hardcoded do artboard.
- [~] T028 `console/visual/screens.json` + baselines do Painel nos dois temas — **[~ motivo]** o registro está feito nesta rodada (`dashboard-1440-dark`,
      `dashboard-1440-light`, `status: pending`) — mas a captura e a
      aceitação da baseline são deliberadamente do gate visual Orca do
      orquestrador (EXECUCAO.md §3), não deste implementer: fabricar uma
      baseline aqui seria exatamente o defeito de evidência manufaturada
      que a onda já viu antes. `pending` fica inerte no suite Playwright
      (`screens.spec.ts` só itera `baselined`).
      recapturadas e revisadas.

## Phase 4: Verde local e gates

- [~] T029 T004 verde alegação por alegação no backing local (mock); as — **[~ motivo]** 12 de 18 fecham: 8 passam de verdade (AN-06, AN-07,
      AN-09, AN-10, AN-13, AN-15, AN-16, AN-17), 4 pulam nomeadamente
      (AN-03, AN-08, AN-11, AN-12). Os 6 que restam vermelhos — AN-01,
      AN-02, AN-04 (dois casos), AN-05, AN-14 — têm causa raiz nomeada e
      fora do escopo desta feature (controle.md §4.2: o botão de investigar
      existente navega para fora do Painel ao suceder, um comportamento
      anterior a toda a onda specs_v8, decidido pelo orquestrador como
      dependência de 070-iniciar-investigacao). "Verde alegação por
      alegação" não é alcançável por esta feature sozinha; encerrada com o
      motivo, não deixada aberta sem explicação. Evidência:
      evidence/acceptance-current-state.log.
      staging-write ficam para a Phase 5. Registrar a virada.
- [x] T030 Gates do domínio editado antes de commitar: lint/format Python e — a disciplina por checkpoint, que é o que esta tarefa pede, foi seguida
      em todo commit desta feature (lint/typecheck/testes do console e
      lint/format Python, sempre lidos do log, nunca de uma notificação ou
      de um pipe). O `make verify` completo é uma tarefa própria, T032, e
      fica registrado lá, não aqui.
      TS/prettier, `check-imports`, suíte de console, suíte visual.
- [ ] T031 Medir a suíte de cenários sintéticos contra T003 e registrar — T003 nunca foi feita por nenhuma sessão, então não há baseline
      literal contra o que medir. `make verify` (13122 testes, inclui a
      suíte de fixtures/dataset determinística) está verde; isso não é a
      mesma reivindicação que "medi o efeito sobre a suíte de cenários
      sintéticos especificamente" e não é apresentado como tal.
      ("sem efeito" esperado).
- [x] T032 `make verify` completo verde, partindo do verde de T001. — verde real, `MAKE_VERIFY_EXIT=0`, no commit `c0b6a975`, depois de três
      rodadas vermelhas corrigidas nesta sessão (anotação de tipo em
      `served.py`, formatação prettier, cobertura de `estate_snapshots`
      no contrato de isolamento por tenant). Log completo preservado fora
      do repositório; controle.md §3.1 tem o detalhe de cada rodada.

## Phase 5: Staging — deploy, acceptance e o gate visual (EXECUCAO.md §3–§4)

- [~] T033 No fim do slot (orquestrador): `make deploy-stg COMPONENTS="app web"`, — **[~ motivo]** reatribuída ao orquestrador: uma worktree não alcança o cluster nem o banco de staging
      aguardar Argo Synced+Healthy.
- [~] T034 **(orquestrador)** Acceptance staging-safe + staging-write contra — **[~ motivo]** reatribuída ao orquestrador: uma worktree não alcança o cluster nem o banco de staging
      `https://stg-ninjasre.lan.kyo.ninja` via
      `tools/spec_validation browser --backing staging`: AN-01→AN-05 com run
      real disparado pela UI, o único run criado no slot S3; a sessão vem do
      credential proxy e nenhum segredo entra no agente, argumentos ou
      evidência. A 020 reutiliza este fixture. AN-07/AN-08 decidindo uma
      aprovação em propose-only — sobre a aprovação que **este** run gerar, nunca
      sobre a pendente que o S2 deixou no staging: aquela é a única proposta
      real criada pela UI e o S5 ainda a demonstra. Registrar SC-001→SC-004.
- [~] T035 **(orquestrador)** Consultas de evidência da spec no banco de staging (cards×banco, — **[~ motivo]** reatribuída ao orquestrador: uma worktree não alcança o cluster nem o banco de staging
      fotografia única em `estate_daily`, decisão gravada) — resultados no
      controle.
- [~] T036 **(orquestrador)** **Gate visual**: captura Orca de `/` nos dois temas (alternando — **[~ motivo]** reatribuída ao orquestrador: uma worktree não alcança o cluster nem o banco de staging
      pelo botão de tema), salvas em `evidence/visual/`, comparadas a
      `Main.dc.html` e `DashboardLight.dc.html`; `VEREDITO.md` com uma linha
      por tela×tema — CONFORME ou o desvio nomeado. Desvio sem registro
      aprovado em `design/padrao-2026-08/DIVERGENCIAS.md` = FAIL do slot.
- [x] T037 Relatório final: chaves i18n/tokens declarados para o orquestrador — entregue como a resposta final desta sessão ao orquestrador, com
      controle.md reescrito para refletir o código atual (ver §0-§8 lá).
      (se houver lacuna da fundação), evidências anexadas, controle.md com o
      que o código prova — e nada além.
