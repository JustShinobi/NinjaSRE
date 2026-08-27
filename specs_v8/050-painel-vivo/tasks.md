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

## Phase 0: Linha de base

- [ ] T001 Rodar `make verify` na árvore intacta e guardar o log fora do
      repositório: exit code, contagem e quais falham. Linha de base não verde
      = parar e reportar.
- [ ] T002 Capturar fora do repositório o "antes" do staging: captura Orca do
      Painel atual nos dois temas, e
      `SELECT count(*) FROM agent_runs WHERE status NOT IN ('completed','failed','cancelled');`
      — os números contra os quais SC-001 e a consulta 1 da spec serão lidos.
- [ ] T003 Registrar contagem e resultado da suíte de cenários sintéticos —
      o "antes" da medição de efeito sobre investigação ("sem efeito" é
      resposta aceitável no fim; "não medido" não é).

## Phase 1: Acceptance e contratos primeiro, confirmados vermelhos

- [ ] T004 Escrever `console/tests/e2e/painel-vivo.acceptance.spec.ts` com as
      17 alegações, uma asserção por alegação, viewport 1440×1080; as
      staging-write usa o único run criado pela UI no slot S3; AN-01/05 provam
      ausência de reload (nenhum `page.reload()`, navegação única). A 020
      apenas observa a requisição POST e o mesmo run, sem criar outro.
      Confirmar vermelho e registrar a mensagem real de cada uma.
- [ ] T005 [P] Teste de contrato em `tests/contract/` para `GET /v1/overview`:
      os cinco KPIs presentes com `{value, breakdown, series}`, série ≤
      `MAX_OVERVIEW_DAILY_BUCKETS` baldes ordenados, e a rota declarada na
      tabela com permissão. Vermelho: a rota não existe.
- [ ] T006 [P] Teste unitário do recorte por assunto: `groupBySubject` (módulo
      compartilhado, cravado pela 060) recortado à janela de 48 h devolve, por
      assunto, `occurrences[]` com instante e severidade, e a soma das
      contagens bate com os incidentes da janela. Vermelho se o recorte/
      reexport do módulo ainda não existir.
- [ ] T007 [P] Teste de contrato do `EstateSnapshotStore` nas duas
      implementações: gravar duas vezes no mesmo dia resulta numa linha; dias
      distintos, linhas distintas; `list_daily(org_id, since, until, limit)`
      devolve a série ordenada e respeita
      `MAX_OVERVIEW_DAILY_BUCKETS`. Vermelho: a porta não existe.
- [ ] T008 [P] Teste de migração ida-e-volta da tabela nova contra PostgreSQL
      real: upgrade cria, downgrade remove, nenhuma outra tabela tocada.
      Vermelho.
- [ ] T009 [P] Teste de unidade (vitest) da reconciliação por id de run:
      o frame recebido contém somente o ID, agenda `router.refresh()` e nunca
      renderiza título/estágio a partir do payload; a leitura atualizada
      insere o card, evento de run já listado atualiza sem duplicar, refresh
      com run já inserido pelo stream não duplica e run completado sai.
      Vermelho.
- [ ] T010 [P] Teste de unidade do recusar: envio bloqueado com razão vazia;
      com razão, o cliente chama a rota de reject com ela; interação já
      fechada vira desfecho informativo, não erro. Vermelho.
- [ ] T011 [P] Teste de unidade do colapso do feed: cinco disparos
      consecutivos do mesmo assunto viram uma entrada com contagem; tipos
      diferentes não colapsam; o feed corta em 8. Vermelho.
- [ ] T012 [P] Teste de unidade da sparkline e do strip: N baldes → N pontos;
      N disparos → N marcadores posicionados pela fração da janela; zero
      baldes → nenhum ponto inventado. Vermelho.
- [ ] T013 [P] Caracterização da banda de atenção atual (pesos, ordenação por
      idade): deve passar antes e continuar passando depois da recomposição.
- [ ] T014 **Portão.** Confirmar e registrar o vermelho de T004–T012 e o verde
      de T013. Nenhuma implementação antes deste portão.

## Phase 2: Backend — o endpoint e a fotografia

- [ ] T015 Porta da fotografia diária (`platform/persistence/ports/`) +
      implementação Postgres + fake, com upsert idempotente por
      `(org_id, snapshot_date)`.
- [ ] T016 Migração da tabela nova, reversível; T008 verde.
- [ ] T017 Gancho de escrita da fotografia no varredor de estate existente;
      `GET /v1/overview` nunca grava. Cravar o `file:line` do gancho no
      controle e parar/reportar se não houver um ponto diário composto.
      T007 verde.
- [ ] T018 `GET /v1/overview` em `gateway/http/routes/overview.py`: agregações
      de `agent_runs` e `incidents` + série da fotografia; rota declarada com
      permissão de leitura; T005 verde.
- [ ] T019 Recorte de janela sobre `groupBySubject` exportado de módulo
      compartilhado (sem endpoint novo — reconciliação com a 060); T006 verde.
- [ ] T020 Regenerar documento de API, cliente TS e dataset simulado (overview
      com dados que exercitem os cinco KPIs; listagem de incidentes com ≥ 3
      assuntos para o recorte cliente; nenhum endpoint `/subjects`).

## Phase 3: Console — um componente por região do artboard

- [ ] T021 `run-band.tsx`: cards de run com título/gatilho/decorrido, barra de
      seis segmentos (tokens da fundação; shimmer só no corrente), contadores
      do cabeçalho lendo das listas nomeadas; consumo do store da 010 com a
      reconciliação de T009; animação de chegada da fundação com o gate de
      `prefers-reduced-motion`. T009 verde.
- [ ] T022 `attention.tsx` recomposta: resumo estruturado da 040 visível,
      Aprovar/Recusar/Ver-plano, razão obrigatória, desfecho informativo para
      corrida, gate de permissão; N > 1 pendências → a mais antiga expandida.
      T010 e T013 verdes.
- [ ] T023 `kpi-tiles.tsx`: cinco KPIs de `GET /v1/overview`, sparkline SVG
      90×28, legenda de decomposição, estado de leitura falhada por KPI, o
      caso "nenhum detector ligado" com link. T012 (metade sparkline) verde.
- [ ] T024 `subject-strip.tsx`: linhas por assunto de `groupBySubject`
      (janela 48 h no cliente), ativos primeiro, strip 120×18, chip com
      forma, subtítulo humano (recurso + nó; id interno só em tooltip), link
      para incidente/investigação. T012 (metade strip) verde.
- [ ] T025 `activity-feed.tsx`: linha do tempo vertical com formas por tipo,
      colapso de T011, inserção por evento com animação de chegada, corte em
      8. T011 verde.
- [ ] T026 `dashboard.tsx`: composição das cinco regiões na geometria do
      artboard (grid, gutters e hierarquia de `Main.dc.html`), leituras
      migradas para o overview onde ele é o dono, empty states com próximo
      passo, honestidade de leitura falhada.
- [ ] T027 i18n: todas as strings novas em `en` e `pt-BR` (dona no S3);
      nenhuma string hardcoded do artboard.
- [ ] T028 `console/visual/screens.json` + baselines do Painel nos dois temas
      recapturadas e revisadas.

## Phase 4: Verde local e gates

- [ ] T029 T004 verde alegação por alegação no backing local (mock); as
      staging-write ficam para a Phase 5. Registrar a virada.
- [ ] T030 Gates do domínio editado antes de commitar: lint/format Python e
      TS/prettier, `check-imports`, suíte de console, suíte visual.
- [ ] T031 Medir a suíte de cenários sintéticos contra T003 e registrar
      ("sem efeito" esperado).
- [ ] T032 `make verify` completo verde, partindo do verde de T001.

## Phase 5: Staging — deploy, acceptance e o gate visual (EXECUCAO.md §3–§4)

- [ ] T033 No fim do slot (orquestrador): `make deploy-stg COMPONENTS="app web"`,
      aguardar Argo Synced+Healthy.
- [ ] T034 Acceptance staging-safe + staging-write contra
      `https://stg-ninjasre.lan.kyo.ninja` via
      `tools/spec_validation browser --backing staging`: AN-01→AN-05 com run
      real disparado pela UI, o único run criado no slot S3; a sessão vem do
      credential proxy e nenhum segredo entra no agente, argumentos ou
      evidência. A 020 reutiliza este fixture. AN-07/AN-08 decidindo uma
      aprovação em propose-only. Registrar SC-001→SC-004.
- [ ] T035 Consultas de evidência da spec no banco de staging (cards×banco,
      fotografia única em `estate_daily`, decisão gravada) — resultados no
      controle.
- [ ] T036 **Gate visual**: captura Orca de `/` nos dois temas (alternando
      pelo botão de tema), salvas em `evidence/visual/`, comparadas a
      `Main.dc.html` e `DashboardLight.dc.html`; `VEREDITO.md` com uma linha
      por tela×tema — CONFORME ou o desvio nomeado. Desvio sem registro
      aprovado em `design/padrao-2026-08/DIVERGENCIAS.md` = FAIL do slot.
- [ ] T037 Relatório final: chaves i18n/tokens declarados para o orquestrador
      (se houver lacuna da fundação), evidências anexadas, controle.md com o
      que o código prova — e nada além.
