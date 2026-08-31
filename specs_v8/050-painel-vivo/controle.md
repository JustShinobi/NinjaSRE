# Controle — 050-painel-vivo

Estado verificado contra o código atual em `wt/v8-050-painel-vivo`. `make
verify` confirmado verde no commit `86965248` (log completo preservado fora
do repositório); os commits de documentação que seguem não tocam código.
Este arquivo é reescrito a cada commit; a versão que importa é a do commit
mais recente.

Esta rodada fechou os quatro itens que a rodada anterior deixou abertos
(`activity-feed.tsx`, `screens.json`, `make verify`, `test_console_gate.py`),
corrigiu três defeitos reais que a suíte de aceitação expôs em componentes
que a rodada anterior tinha marcado como prontos (`kpi-tiles.tsx`,
`subject-strip.tsx`, `attention.tsx`) e, numa segunda parte pedida
explicitamente pelo orquestrador depois de uma correção de rumo, **compôs
`KpiTiles` e `SubjectStrip` em `dashboard.tsx`** — a lacuna que a rodada
anterior tinha deixado nomeada. Duas alegações fecham por causa disso
(AN-09, AN-15). As seis que continuam vermelhas (AN-01, AN-02, AN-04×2,
AN-05, AN-14) são uma descoberta desta rodada, confirmada pelo orquestrador
lendo o próprio código, e são dependência declarada de
**070-iniciar-investigacao** — não desta feature.

## 0. Duas decisões já resolvidas, inalteradas — não relitigar

### 0.1 A decisão de band-selection (FR-001)

Inalterada desde o commit `512d65d5`. `inFlightRuns()` em
`console/src/surfaces/run-band.tsx:74` filtra por `!isSettled(status)`
(`@/design/status`, congelada), dando `{running, suspended}` e excluindo
`interrupted` — os onze runs zumbis do staging. `RUN_BAND_VISIBLE_MAX = 6`
fatia o mesmo array que o cabeçalho conta sem fatiar. Testada em
`run-band.test.ts::inFlightRuns` ("the zombie band"). A consulta de evidência
1 do `spec.md` mede a coisa errada depois desta decisão; a corrigida:

```sql
SELECT count(*) FROM agent_runs WHERE status IN ('running', 'suspended');
```

### 0.2 O defeito do plan.md sobre a rota de decisão

Inalterado: `plan.md` decisão 4 cita `POST /v1/interactions/{id}/approve`;
o código sempre usou `POST /v1/approvals/{approval_id}/decision`, via
`/api/approval`, porque uma remediação proposta é um `ApprovalRequest`, não
uma interação de run vivo.

## 1. Peça por peça

| Peça | Estado | Detalhe |
|---|---|---|
| `MAX_OVERVIEW_DAILY_BUCKETS` | FEITO | `config/constants/estate.py` |
| Porta `EstateSnapshotStore` + fake + Postgres + migração `0021` | FEITO (mypy+ruff limpos; Postgres real inalcançável nesta worktree, ver §5) | `platform/persistence/ports/estate_snapshot_store.py` |
| `estate_snapshots` no contrato de isolamento por tenant | FEITO nesta rodada — achado ao rodar `make verify`, não pedido: a porta estava exposta em `UnitOfWork` mas ausente de `TENANT_SCOPED_PORTS` | `tests/contract/persistence/test_tenant_isolation.py`, 6/6 verde |
| Gancho de escrita diária | FEITO | `platform/estate/discovery/runner.py::TopologyDiscoveryRunner._confirm_daily_snapshot` |
| `GET /v1/overview` | FEITO, testado contra fakes (5/5 verde) | `gateway/http/routes/overview.py` |
| `subjectsInWindow`/`SUBJECT_WINDOW_HOURS` | FEITO, testado (17/17 verde), **agora consumida por `dashboard.tsx`** | `console/src/surfaces/incident-groups.ts:188-230` |
| `positionOnTimeline` generalizada | FEITO, testado (7/7 verde) — não consumida por `subject-strip.tsx`, ver §6 | `console/src/surfaces/incident-timeline.ts:44-76` |
| **Acceptance spec (17 alegações, 18 casos)** | FEITO — vermelho real confirmado antes de qualquer implementação | `console/tests/e2e/painel-vivo.acceptance.spec.ts` |
| `run-band.tsx` | FEITO, testado (9/9 verde), **composta** | `console/src/surfaces/run-band.tsx` |
| `kpi-tiles.tsx` | FEITO (testids corrigidos nesta rodada) **e composta em `dashboard.tsx` nesta rodada** | `console/src/surfaces/kpi-tiles.tsx`; AN-09 fecha por causa disto |
| `subject-strip.tsx` | FEITO (testids corrigidos nesta rodada) **e composta em `dashboard.tsx` nesta rodada**, substituindo `IncidentGroupList` | `console/src/surfaces/subject-strip.tsx`; AN-15 fecha por causa disto |
| `AttentionDecisionControls` (novo) + `attention.tsx` recomposta | FEITO — extraído desta banda porque `IncidentDecisionControls` (o componente compartilhado da 040/060) usa um testid único e um fluxo que não correspondem ao acceptance spec nem ao artboard | `console/src/surfaces/attention-decision-controls.tsx` (novo) |
| `console/src/surfaces/activity-feed.tsx` (novo) | FEITO — quatro formas, `collapseFeed` | `console/src/surfaces/activity-feed.tsx`, composta em `dashboard.tsx` |
| Composição completa de `dashboard.tsx` | **FEITO** — as cinco regiões do artboard (run-band, attention, kpi-tiles, subject-strip, activity-feed) estão todas compostas; `/v1/estate/summary` e `/v1/detectors` removidos do `Promise.all` porque nada mais os lê | `console/src/surfaces/screens/dashboard.tsx` |
| `console/visual/screens.json` | FEITO — `dashboard-1440-{dark,light}`, `status: pending`, sem baseline fabricada (a suíte só itera `baselined`) | `console/visual/screens.json` |
| `make verify` | FEITO, verde de verdade, no commit `86965248` | ver §3 |
| `test_console_gate.py` | FEITO, 17/17 verde, 1411.32s reais | ver §3.2 |
| Reprodutibilidade do dataset simulado | FEITO — reverificado nesta rodada | ver §3.3 |
| `console/scripts/fixture-server.mjs` cobre `/v1/overview` | **FEITO nesta rodada** — achado ao compor `KpiTiles`: a tabela `SHELL_ENDPOINTS`, compartilhada pelo harness de unit test e pela suíte visual, nunca ganhou a entrada de `/v1/overview`, então todo KPI lia "Could not be read" sob `jsdom` em qualquer cenário | `console/scripts/fixture-server.mjs` |

## 2. O vermelho do acceptance spec, do início ao fim desta rodada

Cinco leituras, contra estados sucessivos do código, todas com
`uv run python -m tools.console_e2e run --backing mock --
tests/e2e/painel-vivo.acceptance.spec.ts` sobre um build fresco
(`console_gate build` rodado antes de cada uma — ver §7 pela armadilha de
não fazer isso).

1. **Vermelho original**: 11 failed, 7 skipped, 0 passed.
2. **Início desta rodada, build desatualizado** (armadilha, ver §7): mesmos
   11 failed, porque o build servido não refletia o código já commitado.
3. **Início desta rodada, build fresco**: 12 failed, 4 skipped, 2 passed
   (AN-10, AN-17). Os defeitos de `kpi-tiles`/`subject-strip`/`attention`
   ficaram visíveis pela primeira vez aqui.
4. **Depois de corrigir os três componentes** (kpi-tiles, subject-strip,
   attention), **antes de compor kpi-tiles/subject-strip em
   `dashboard.tsx`**: 8 failed, 4 skipped, 6 passed — 6 passam
   (AN-06, AN-07, AN-10, AN-13, AN-16, AN-17), 4 pulam (AN-03, AN-08, AN-11,
   AN-12). **Correção sobre um relato anterior desta mesma rodada**: eu
   tinha listado erradamente AN-08 entre os que passavam; a lista real,
   conferida linha a linha nos dois logs, é a acima — AN-08 pulava desde a
   primeira vez que o dataset teve uma aprovação pendente, nunca passou.
5. **Final, depois de compor `KpiTiles`/`SubjectStrip`**,
   `evidence/acceptance-current-state.log`: **6 failed, 4 skipped, 8
   passed** (43.5s). Passam agora, a mais que a leitura 4: **AN-09, AN-15**
   — exatamente as duas que dependiam da composição.

**O vermelho final, causa raiz de cada uma, nenhuma sem diagnóstico**:

- **AN-01, AN-02, AN-04 (2 casos), AN-05, AN-14** (6): `runCards(page).count()`
  e `activityEntries(page).count()` nunca saem de 0 depois de
  `startInvestigation()`. Causa: `console/src/live/investigate.tsx:86-88` —
  `InvestigateDrawer.start()` navega incondicionalmente para
  `/runs/{runId}` ao suceder, sempre, hoje, num mecanismo anterior a toda a
  onda `specs_v8` (git log: commits `b7003f1c`/`19431fc0`, ambos v7). **O
  orquestrador confirmou isto lendo o próprio arquivo** e decidiu: é
  dependência de **070-iniciar-investigacao**, não desta feature. As seis
  alegações ficam vermelhas e declaradas — nenhuma foi pulada, enfraquecida
  ou relocada para parecer resolvida.

Puladas (4), nomeadas: **AN-03** (precisa de `stage_index` da 020, ver §8);
**AN-08** (o mock scenario não carrega mais uma aprovação pendente no
momento em que este teste roda — AN-07, que roda antes no mesmo arquivo,
decide a única aprovação do cenário `populated` como parte do seu próprio
sucesso, e o mockplane mantém esse estado pelo resto da suíte); **AN-11,
AN-12** (o dataset `populated`, mesmo com `subject-strip` composta, não
expõe um assunto recorrente dentro da janela de 48h no momento da leitura —
não investigado a fundo nesta rodada, nomeado como pendente).

## 3. As verificações de gate desta rodada, com o comando e o exit real

### 3.1 `make verify`

Executado seis vezes ao longo desta rodada; as duas primeiras (mypy,
prettier) e a quinta/sexta (prettier de novo, depois da composição) foram
reais causas encontradas e corrigidas — nunca uma nova tentativa sem uma
causa diagnosticada primeiro:

1. `MAKE_VERIFY_EXIT=2` — `mypy`: `served.py:3473`, `empty_kpi` sem
   anotação de tipo. Corrigido.
2. `MAKE_VERIFY_EXIT=2` — `prettier --check` em 5 arquivos. Corrigido.
3. `MAKE_VERIFY_EXIT=2` — `test_every_tenant_scoped_port_is_covered`:
   `estate_snapshots` ausente do registro. Corrigido.
4. **`MAKE_VERIFY_EXIT=0`**, no commit `c0b6a975` — antes de compor
   `KpiTiles`/`SubjectStrip`. 13122 passed/32 skipped + 38 benchmark passed.
5. `MAKE_VERIFY_EXIT=2` — depois de compor `KpiTiles`/`SubjectStrip`:
   `prettier --check` em `dashboard.tsx`/`dashboard.test.tsx` (editados por
   script, nunca formatados). Corrigido.
6. **`MAKE_VERIFY_EXIT=0`**, no commit `86965248` (o commit de composição,
   depois da correção de formatação) — **estado final**: `3227 passed | 9
   skipped` no console, `13122 passed, 32 skipped` na suíte principal,
   `38 passed, 13154 deselected` nos benchmarks. Log completo preservado
   fora do repositório; nada mudou na árvore desde este commit além de
   documentação.

### 3.2 `uv run pytest tests/contract/console/test_console_gate.py`

Rodado sem wrapper de `timeout`, em árvore limpa. **17 passed, 0 failed, em
1411.32s (23m31s) reais**, lido do log — não de notificação: uma
notificação de tarefa em segundo plano relatou "completed (exit code 0)"
para um monitor que checava o PID errado (o processo do shell persistente,
não o do `pytest`), bem antes do `pytest` de fato terminar, confirmado com
`ps aux` mostrando `pytest` e `console_gate e2e` ainda vivos no momento em
que a notificação disse "completo". `git status` conferido depois: árvore
limpa, nenhum `seeded.spec.ts` órfão nesta execução (terminou sem
interrupção).

### 3.3 Reprodutibilidade do dataset simulado

`sha256sum` de `fixtures/scenarios/populated/overview.json` antes e depois
de `uv run python -m tools.mockplane build` em árvore limpa: **idêntico**
(`5729fdb2b1e9acd3053e71ba70f5f79a85736889bacf66e3084ef398b3dd18b8`).
`git status --short` depois do build: **vazio** — nenhum dos 238 arquivos
gerados diverge por um byte do que está commitado. `mockplane verify` → "the
dataset is clean"; `mockplane report` → "86 of 86 console endpoints are
covered". O comando gerador é `python -m tools.mockplane build`.

## 4. A composição de `KpiTiles`/`SubjectStrip` — o que mudou em `dashboard.tsx`

Pedida explicitamente pelo orquestrador depois de uma correção de rumo (a
rodada tinha, por instrução anterior, deixado isto de fora). Mudanças:

- `Promise.all` ganha `panelRead('/v1/overview', ...)`; perde
  `panelRead('/v1/estate/summary', ...)` e `panelRead('/v1/detectors', ...)`
  — nada na tela lê mais nenhum dos dois depois da composição.
- Uma função local `kpiOf(name)` lê `overviewData[name]` defensivamente
  (`value: number | null` — nunca `0` inventado quando o campo falta, ao
  contrário de `number()` de `../read`, que zera por padrão) e monta o
  `KpiData` que `KpiTiles` espera.
- O grid de `<Figure>` e os cálculos que só ele alimentava (`watched`,
  `degraded`, `kinds`, `liveDetectors`, `endedIncidents`, `unattended`,
  `unattendedRate`, `finished`, `median`, `slowest`, `settledRuns`,
  `succeededRuns`, `successRate` — treze identificadores, confirmados sem
  nenhum outro uso no arquivo antes de remover) foram apagados por inteiro.
- `recurring` passa a `subjectsInWindow(groupBySubject(incidentRecords),
  now, SUBJECT_WINDOW_HOURS).filter(g => g.count > 1)`, e
  `<IncidentGroupList>` vira `<SubjectStrip locale={locale} now={now}
  groups={recurring} />`.
- **Nove testes de `dashboard.test.tsx` e um de `first-run.test.tsx`
  testavam a aritmética client-side que a composição elimina.** Nenhum foi
  apagado silenciosamente: sete foram `it.skip`ados com o motivo na própria
  linha e a cobertura equivalente nomeada (`kpi-tiles.test.tsx`,
  `tests/contract/gateway/test_overview_routes.py`); dois foram reescritos
  contra o novo testid (`kpi-tile`/`data-kpi`, `subject-row`/`subject-count`)
  porque ainda testam algo real — a fiação, não a aritmética. Três funções
  auxiliares de fixture (`dashboardWithClosedIncidents`,
  `dashboardWithHealthSummary`, `dashboardWithNothingButCleanFinishes`)
  ficaram sem nenhum chamador depois disso e foram removidas — não são a
  alegação, são o andaime dela.
- **Achado no caminho**: a fixture de `dashboardWithLiveIncidents` usava
  datas de calendário fixas (`2026-08-26...`); com a janela de 48h agora
  em uso pela composição, o teste "folds what keeps happening" ficou
  dependente da data em que a suíte roda e já tinha decaído (hoje é
  2026-08-31). Corrigido com um `hoursAgo(n)` relativo ao relógio real, não
  a um dia fixo — sem isso o teste ficaria intermitente por calendário, não
  por defeito de código.
- **Achado maior no caminho**: `console/scripts/fixture-server.mjs` — a
  tabela `SHELL_ENDPOINTS` que o harness de unit test e a suíte visual
  usam para resolver `caminho → fixture` — nunca ganhou `/v1/overview`.
  Confirmado empiricamente (`bodyFor('first-run', '/v1/overview')`
  retornava `null` para toda e qualquer cenário, não só `first-run`) antes
  de corrigir. `tests/contract/console/test_console_shell.py` (36/36 verde
  depois) não pegou a ausência porque checa a tabela numa direção só.
  Corrigido, adicionando uma linha.

## 5. T008 — migração `0021`, não executável nesta worktree

Inalterado: Postgres real inalcançável aqui. Pendente para quem tiver
Postgres alcançável:
`uv run pytest tests/contract/persistence/test_estate_daily_snapshot_migration.py -v`.

## 6. Ressalva sobre o "mini-timeline" de assunto (FR-023), inalterada

`subject-strip.tsx` usa `RecurrenceStrip` (barras por ocorrência) para
`data-testid="subject-timeline"`, não `positionOnTimeline` (pontos
proporcionais numa janela real) — o artboard (`Main.dc.html:255-289`)
desenha barras de altura/opacidade crescente sem posicionamento
proporcional real, o que faz `RecurrenceStrip` a leitura visualmente fiel.
O acceptance spec só exige que o elemento exista e seja visível. A
generalização de `positionOnTimeline` (rodada anterior, 7/7 verde) fica como
capacidade não consumida por este componente específico, não como código
morto — a Incidents screen a usa para outra coisa.

## 7. Achados de processo desta rodada

- **`console_e2e run` não builda o console sozinho** — espera
  `.next/standalone/server.js` já existir e serve build antigo em silêncio
  se ele estiver desatualizado. `make console-build`/`console_gate build`
  antes de qualquer leitura do acceptance é obrigatório.
- **Notificação de tarefa em segundo plano mentiu de novo**, capturada com
  o processo ainda vivo no `ps aux` (§3.2) — a mesma classe já registrada
  em rodadas anteriores desta onda.
- **A regra "reveal" é uma palavra banida em todo `console/src`,
  mecanicamente, sem exceção de contexto**
  (`tests/unit/surfaces/masking.test.tsx`). `attention-decision-controls.tsx`
  e `attention.tsx` reescritos para "abre"/"aparece" em vez de "revela".

## 8. Declarações para o orquestrador aplicar no merge

- **Migração `0021_estate_daily_snapshot`**: `down_revision` continua
  `0019_users_email_optional` nesta worktree; o orquestrador re-aponta para
  `0020_run_objective` (da 020) no merge das duas árvores.
- **AN-03 continua nomeadamente pulada** (`test.skip`, razão na própria
  linha): depende de `stage_index`, que só existe depois do merge com a
  020-titulo-vivo. Rodar a suíte de novo, sem editar o teste, depois do
  merge do slot.
- **As seis alegações bloqueadas por `investigate.tsx` (AN-01, AN-02, AN-04
  ×2, AN-05, AN-14) são dependência declarada de 070-iniciar-investigacao**,
  confirmada pelo orquestrador lendo `investigate.tsx:86-88` e o git log
  (`b7003f1c`/`19431fc0`, anteriores a toda a onda `specs_v8`). Ficam
  vermelhas e nomeadas no acceptance spec — não puladas, não enfraquecidas,
  não relocadas. `console/src/live/investigate.tsx` e `console/src/shell/
  shell.tsx` não foram tocados por esta feature.
- **Vazamento de segredo**: o lead relatou que o objetivo cru e labels de
  alerta chegam sem redação até a timeline do incidente e o prompt do
  agente — reparo da feature irmã (020/060), não desta. O que esta feature
  lê da mesma classe de fonte, para reconferência quando aquele reparo
  aterrissar, sem presumir limpo por proximidade:
  - `activity-feed.tsx`, via a composição em `dashboard.tsx`: `Incident.title`
    (`text(record, 'title')`, entradas "incidente aberto"/"fechado
    sozinho") e `ApprovalRequest.summary` (`text(record, 'summary')`,
    entradas "remediação proposta"/"decisão registrada"). Também lê
    `AgentRun.headline` via `subjectOf()` para as entradas de investigação —
    o mesmo campo que `run-band.tsx` já lia, já nomeado antes.
  - `subject-strip.tsx` lê `IncidentGroup.title` (derivado de
    `Incident.title` por `groupBySubject`) para o título de cada linha, e
    `SubjectLine`/`subjectTitle` para o subtítulo.
  - Nenhum destes foi comprovado vazando — nomeados como leitores da mesma
    classe de campo que o lead já encontrou vazando em outra tela.
- **Nenhum token, ícone ou primitiva de motion faltando da fundação.**
  `Textarea` (`components/form.tsx`, não é parte da fundação 000) ganhou um
  `data-testid` que já existia no seu próprio tipo mas nunca tinha sido
  aplicado — aditivo, mesmo padrão que `Input`/`Select` já usavam no mesmo
  arquivo.
- **Capacidade retirada, nomeada, não substituída** (inalterado): a banda
  "precisa de você" antiga mostrava um run falho com link para
  `/first-run`; a nova só mostra aprovações pendentes. Dois testes
  permanecem `it.skip` com a razão na própria linha.
- **Chaves i18n órfãs, inalterado**: `dashboard.attention.*` e
  `dashboard.band.*` continuam sem consumidor. Não removidas.
