# Controle — 050-painel-vivo

Estado verificado contra o código atual em `wt/v8-050-painel-vivo`, no commit
`c0b6a975` (HEAD desta rodada). Este arquivo é reescrito a cada commit; a
versão que importa é a do commit mais recente. Esta rodada fechou os quatro
itens que a rodada anterior deixou abertos (`activity-feed.tsx`,
`screens.json`, `make verify`, `test_console_gate.py`), mais um quinto que
apareceu no caminho e precisou ser corrigido para o quarto fechar
(`estate_snapshots` fora do contrato de isolamento por tenant) — e corrigiu,
antes de tudo isso, três defeitos reais que a suíte de aceitação já vermelha
expôs em componentes que a rodada anterior tinha marcado como prontos
(`kpi-tiles.tsx`, `subject-strip.tsx`, `attention.tsx`): nenhum deles tinha
sido de fato executado contra o próprio acceptance spec antes desta rodada.

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
uma interação de run vivo. A rota certa é a que `attention.tsx` sempre
chamou, incluindo depois da recomposição desta rodada (ver §2 abaixo).

## 1. Peça por peça

| Peça | Estado | Detalhe |
|---|---|---|
| `MAX_OVERVIEW_DAILY_BUCKETS` | FEITO | `config/constants/estate.py` |
| Porta `EstateSnapshotStore` + fake + Postgres + migração `0021` | FEITO (mypy+ruff limpos; Postgres real inalcançável nesta worktree, ver §6) | `platform/persistence/ports/estate_snapshot_store.py` |
| `estate_snapshots` no contrato de isolamento por tenant | **FEITO nesta rodada** — não pedido, achado ao rodar `make verify`: a porta estava exposta em `UnitOfWork` mas ausente de `TENANT_SCOPED_PORTS`, o registro que `test_every_tenant_scoped_port_is_covered` mantém honesto | `tests/contract/persistence/test_tenant_isolation.py` — escreve uma fotografia em `write_one_of_everything`, confere que `globex` não a vê via `list_daily`, confere que `acme` continua com ela; 6/6 verde |
| Gancho de escrita diária | FEITO | `platform/estate/discovery/runner.py::TopologyDiscoveryRunner._confirm_daily_snapshot` |
| `GET /v1/overview` | FEITO, testado contra fakes (5/5 verde) | `gateway/http/routes/overview.py` |
| `subjectsInWindow`/`SUBJECT_WINDOW_HOURS` em `incident-groups.ts` | FEITO, testado (17/17 verde) | `console/src/surfaces/incident-groups.ts:188-230` |
| `positionOnTimeline` generalizada para janela configurável | FEITO, testado (7/7 verde) — **ressalva**: não é consumida por `subject-strip.tsx`; ver §5 | `console/src/surfaces/incident-timeline.ts:44-76` |
| **Acceptance spec (17 alegações, 18 casos)** | FEITO — vermelho real confirmado antes de qualquer implementação | `console/tests/e2e/painel-vivo.acceptance.spec.ts` |
| `run-band.tsx` | FEITO, testado (9/9 verde) | `console/src/surfaces/run-band.tsx` |
| `kpi-tiles.tsx` | **FEITO (corrigido nesta rodada)** — a rodada anterior construiu e testou o componente isoladamente, mas com um testid que o próprio acceptance spec dele não usa (`kpi-tile-{id}` em vez de `kpi-tile` + `data-kpi="{id}"`) e sem `data-testid="kpi-legend"`. Achado rodando o acceptance de verdade contra um build fresco do console, não por inspeção. Corrigido; 8/8 unit tests verdes, atualizados para o novo testid | `console/src/surfaces/kpi-tiles.tsx:129-149`; teste em `console/tests/unit/surfaces/kpi-tiles.test.tsx` |
| `subject-strip.tsx` | **FEITO (corrigido nesta rodada), com uma lacuna nomeada** — faltavam três testids que o acceptance spec exige (`subject-timeline`, `subject-chip` com `data-role`, `subject-subtitle`); nenhum existia. Corrigidos por composição — `RecurrenceStrip` (já existente, visualmente fiel ao artboard: barras crescendo em altura/opacidade para a direita, não um eixo de tempo proporcional) envolvida num `<span data-testid="subject-timeline">`; `Badge` envolvido num `<span data-testid="subject-chip" data-role={...}>` usando `statusPresentation` (congelada, importada, não editada); `subject-subtitle` adicionado ao `<span>` existente. 10/10 unit tests verdes (3 novos). Ver §5 pela ressalva sobre `positionOnTimeline` não ser a fonte do "mini-timeline" | `console/src/surfaces/subject-strip.tsx` |
| `AttentionDecisionControls` (novo) + `attention.tsx` recomposta | **FEITO (corrigido nesta rodada)** — a rodada anterior reusava `IncidentDecisionControls` (`screens/incident-decision-controls.tsx`, componente da 040/060), cujo testid único (`decision-control`, para os dois botões) e fluxo (campo de razão sempre visível) não correspondem ao que o próprio acceptance spec exige (`attention-approve`, `attention-reject`, `attention-reject-reason`, `attention-reject-submit`, com Recusar revelando o campo em vez de mostrá-lo sempre) — e ao que o artboard desenha (três controles lisos, sem textarea aberta ao lado). Extraído um componente novo e próprio da banda, sobre o mesmo courier (`POST /api/approval` → `POST /v1/approvals/{id}/decision}`), sem tocar o componente compartilhado. 10/10 unit tests verdes (7 novos, cobrindo aprovar, recusar com revelação, submit desabilitado até haver razão, e a falha de rede) | `console/src/surfaces/attention-decision-controls.tsx` (novo); `console/src/surfaces/attention.tsx` |
| `Textarea` (`components/form.tsx`) ganhou `data-testid` | FEITO nesta rodada — aditivo, mesmo padrão que `Input`/`Select` já usavam no mesmo arquivo (`FieldProps['data-testid']` já existia no tipo, só não estava sendo aplicada ao elemento); nenhum consumidor existente afetado | `console/src/components/form.tsx:245-276` |
| `console/src/surfaces/activity-feed.tsx` (novo) | **FEITO nesta rodada** — quatro formas (`investigation`=losango, `resolution`=círculo, `incident`=quadrado, `approval`=triângulo), `collapseFeed` dobrando disparos consecutivos do mesmo assunto numa entrada com contagem. 10/10 unit tests verdes | `console/src/surfaces/activity-feed.tsx` |
| Composição do feed em `dashboard.tsx` | **FEITO nesta rodada** — a seção antiga (dois tipos: `incident`/`run`) foi substituída por quatro tipos derivados das mesmas três listagens já lidas (runs, incidents, approvals): investigação iniciada/encerrada, incidente aberto/fechado sozinho, decisão proposta/decidida — nenhuma leitura nova. `collapseFeed` aplicado antes do corte em `FEED_LENGTH=8` | `console/src/surfaces/screens/dashboard.tsx` (bloco "The narrative") |
| `KpiTiles`/`SubjectStrip` compostos em `dashboard.tsx` | **NÃO FEITO — a lacuna mais importante que sobra.** Ver §4.1 | `console/src/surfaces/screens/dashboard.tsx` não importa `KpiTiles` nem `SubjectStrip` em lugar nenhum — confirmado por grep e pela leitura do arquivo inteiro |
| `console/visual/screens.json` | **FEITO nesta rodada, com o cuidado que a onda pede** — duas entradas novas (`dashboard-1440-dark`, `dashboard-1440-light`), `status: "pending"`, sem baseline fabricada por mim: o suite visual (`screens.spec.ts:126`) só itera `status === 'baselined'`, então `pending` fica inerte até a captura e a aceitação — que são do gate visual Orca do orquestrador, nomeadamente, não deste implementer | `console/visual/screens.json` |
| `make verify` | **FEITO nesta rodada, verde de verdade, três rodadas vermelhas antes** — ver §3 | `MAKE_VERIFY_EXIT=0`, log completo salvo |
| `test_console_gate.py` | **FEITO nesta rodada, 17/17 verde, 1411.32s reais** | ver §3.2 |
| Reprodutibilidade do dataset simulado | **FEITO nesta rodada — reverificado, não apenas herdado** | ver §3.3 |

## 2. O vermelho do acceptance spec, do início desta feature até agora

Quatro leituras, contra quatro estados diferentes do código, todas com
`uv run python -m tools.console_e2e run --backing mock --
tests/e2e/painel-vivo.acceptance.spec.ts` sobre um build fresco
(`console_gate build` rodado antes de cada uma — a suíte usa
`.next/standalone` já compilado e não reconstrói sozinha, uma armadilha desta
sessão que vale registrar: ver §7).

1. **Vermelho original** (nenhuma tela nova construída): 11 failed, 7
   skipped, 0 passed. `evidence/acceptance-red-full.log`.
2. **Início desta rodada** (árvore herdada, run-band e attention já
   compostos, mas contra um build *desatualizado* — ver §7): mesmos 11
   failed que o vermelho original, porque o build servido não refletia o
   código já commitado.
3. **Início desta rodada, build fresco**: 12 failed, 4 skipped, 2 passed
   (AN-10, AN-17). Foi aqui que os defeitos de `kpi-tiles`/`subject-strip`/
   `attention` ficaram visíveis pela primeira vez — AN-06/07/08 pararam de
   pular (o dataset tem uma aprovação pendente) e falharam de verdade por
   `attention-approve` não existir.
4. **Final desta rodada**, `evidence/acceptance-current-state.log`: **8
   failed, 4 skipped, 6 passed** (55.1s). Passam agora: AN-06, AN-07, AN-08,
   AN-10, AN-13, AN-17.

Os 8 que ainda falham, por causa raiz — nenhuma delas nova nesta leitura,
todas com a mensagem real citada:

- **AN-09, AN-15** (2): `getByTestId('kpi-tile')` não encontrado.
  Causa: `KpiTiles` não está composta em `dashboard.tsx` (§4.1). Corrigir
  isto por si só torna as duas verdes — não há outro defeito atrás delas.
- **AN-01, AN-02, AN-04 (2 casos), AN-05, AN-14** (5, o teto de tudo que
  ainda falha nas Alegações 1 e 5): `runCards(page).count()` e
  `activityEntries(page).count()` nunca saem de 0 depois de
  `startInvestigation()`. Causa raiz, **descoberta nesta rodada, fora do
  escopo desta feature**: ver §4.2 — o botão existente de investigar navega
  para fora de `/` ao suceder, sempre, hoje, antes de qualquer coisa que
  esta feature tenha tocado.

Puladas (4), inalteradas: AN-03 (nomeadamente, precisa de `stage_index` da
020); AN-11, AN-12 (o dataset `populated` não tem assunto recorrente visível
sem `subject-strip` composta — a mesma causa de AN-09/15, uma vez resolvida
essas duas alegações deixam de pular); AN-16 (o dataset tem uma aprovação
pendente, então o estado vazio genuinamente não se aplica).

## 3. As três verificações pedidas nesta rodada, com o comando e o exit real

### 3.1 `make verify`

**Sim, foi executado de novo e terminou verde**, no commit `c0b6a975`
(HEAD). Não estava verde da primeira vez — três rodadas vermelhas, cada uma
lida do log e corrigida antes da próxima:

1. `MAKE_VERIFY_EXIT=2` — `mypy`: `tools/mockplane/dataset/served.py:3473`,
   `empty_kpi` sem anotação de tipo (`dict` heterogêneo: `None`, `dict`,
   `list`, `str` conforme o call site). Corrigido:
   `empty_kpi: dict[str, Any] = {...}`, seguindo a mesma convenção já usada
   duas vezes no mesmo arquivo.
2. `MAKE_VERIFY_EXIT=2` — `prettier --check` em 5 arquivos que esta rodada
   tocou. Corrigido com `pnpm exec prettier --write` nos mesmos 5; diff
   revisado, puramente cosmético (quebra de linha).
3. `MAKE_VERIFY_EXIT=2` — `pytest`:
   `tests/contract/persistence/test_tenant_isolation.py::test_every_tenant_scoped_port_is_covered`
   falhou porque `estate_snapshots` está exposta em `UnitOfWork` mas ausente
   do registro `TENANT_SCOPED_PORTS`. Corrigido (ver §1); 13122 passed (era
   13121 passed + 1 failed antes).
4. **`MAKE_VERIFY_EXIT=0`.** `13122 passed, 32 skipped` na suíte principal
   (`pytest -n workers`) e `38 passed, 13154 deselected` na suíte de
   benchmark (`pytest -m benchmark`) — os dois comandos que
   `make verify`'s alvo `test` roda. Log completo preservado fora do
   repositório; nada mudou na árvore desde este commit.

### 3.2 `uv run pytest tests/contract/console/test_console_gate.py`

Rodado sem wrapper de `timeout`, em árvore limpa (`git status` conferido
antes). **17 passed, 0 failed, em 1411.32s (23m31s) reais** — lido do log,
não de notificação: a notificação de tarefa em segundo plano do harness
relatou "completed (exit code 0)" para um monitor que na verdade checava o
PID errado (o processo do shell persistente, não o do `pytest`), bem antes
do `pytest` de fato terminar — a mesma classe de mentira que as rodadas S1 e
S2 já registraram, desta vez capturada com o próprio `ps aux` mostrando o
`pytest` e o `console_gate e2e` ainda vivos no momento em que a notificação
disse "completo". A linha real, do próprio arquivo de log:

```
======================= 17 passed in 1411.32s (0:23:31) ========================
CONSOLE_GATE_EXIT=0
```

`git status` conferido imediatamente depois: árvore limpa, nenhum
`console/tests/e2e/seeded.spec.ts` órfão desta vez (a rodada terminou sem
interrupção, então a própria limpeza do teste rodou). Uma tentativa anterior
nesta mesma sessão *foi* interrompida pelo teto de 600s do próprio wait-loop
usado para esperar — o processo em si nunca foi morto, só o monitor —, e
deixou o mesmo arquivo órfão que a onda já viu duas vezes; o orquestrador
removeu antes desta segunda tentativa, que rodou até o fim sem intervenção.

### 3.3 Reprodutibilidade do dataset simulado

`fixtures/scenarios/populated/overview.json` — e as outras 237 arquivos que
o mesmo comando escreve — são gerados, não editados à mão. Prova, nesta
ordem, nesta rodada:

1. `sha256sum fixtures/scenarios/populated/overview.json` antes:
   `5729fdb2b1e9acd3053e71ba70f5f79a85736889bacf66e3084ef398b3dd18b8`.
2. `uv run python -m tools.mockplane build` em árvore limpa (`git status`
   vazio antes de rodar) → `wrote 238 files across 6 scenarios`, exit 0.
3. `git status --short` depois: **vazio** — nenhum dos 238 arquivos gerados
   diverge, em nenhum byte, do que está commitado.
4. `sha256sum` do mesmo arquivo depois: **idêntico** ao passo 1.
5. `uv run python -m tools.mockplane verify` → `the dataset is clean`, exit
   0. `uv run python -m tools.mockplane report` → `86 of 86 console
   endpoints are covered`, exit 0.

O comando gerador é `python -m tools.mockplane build`; `overview_record()`
(`tools/mockplane/dataset/served.py:3463`) é chamada por
`populated_records()`/`empty_records()`, nunca escrita por fora.

## 4. O que fica pendente, nomeado, não escondido

### 4.1 `KpiTiles` e `SubjectStrip` não estão compostas em `dashboard.tsx`

Esta é a lacuna real mais importante que sobra, e o motivo por trás de
AN-09, AN-11, AN-12 e AN-15 ainda não fecharem. Os dois componentes existem,
estão testados isoladamente (8/8 e 10/10), e as correções de testid desta
rodada (§1) os deixaram alinhados ao próprio acceptance spec — mas
`dashboard.tsx` continua renderizando o grid antigo de `<Figure>` para os
cinco KPIs (lendo de cálculos locais sobre `runs`/`incidents`/`estate`, não
de `GET /v1/overview` — o que também é, por si, uma violação ainda aberta de
FR-019/"nenhuma recomputação paralela") e o painel antigo `IncidentGroupList`
para "o que insiste em acontecer", em vez de `SubjectStrip`.

Fechar isto exige: (1) uma leitura nova de `/v1/overview` no `Promise.all`
de `DashboardScreen`; (2) montar os cinco `KpiData` a partir da resposta
(`value: number | null`, nunca `0` inventado — `number()` de `read.ts`
teria voltado a inventar zero, precisa de um leitor próprio); (3) remover o
grid de `<Figure>` e os cálculos locais que ele sozinho alimentava
(`watched`, `degraded`, `kinds`, `liveDetectors`, `unattended*`,
`succeededRuns`, `successRate`, `finished`, `median`, `slowest`,
`settledRuns` — nenhum deles tem outro consumidor na tela, confirmado lendo
o arquivo inteiro); (4) trocar `IncidentGroupList` por `SubjectStrip` na
seção "o que insiste", alimentada por
`subjectsInWindow(groupBySubject(incidentRecords), now, SUBJECT_WINDOW_HOURS).filter(g => g.count > 1)`;
(5) atualizar `dashboard.test.tsx` — a suíte tem hoje ~10 casos escritos
contra o grid de `Figure` antigo (`data-testid="figure"`,
`dashboard.stat.*`) que quebrariam e precisariam virar equivalentes contra
`kpi-tile`/`data-kpi`.

Não fiz este trabalho nesta rodada porque o orquestrador pediu
explicitamente para eu não abrir uma quinta frente depois de já ter
reconstruído `attention`/`kpi-tiles`/`subject-strip` sem ter sido pedido —
uma instrução que aceito e seguido. Fica nomeado, não escondido, como a
lacuna de maior alavancagem que resta nesta feature.

### 4.2 Achado novo, fora do escopo desta feature: o botão de investigar navega para fora do Painel

`console/src/live/investigate.tsx:76-90` — `InvestigateDrawer.start()` —
chama, ao suceder, `navigate(href)` com `href = /runs/{runId}`, sempre, sem
condição. Como `shell.tsx:301` passa o próprio `navigate` (que por padrão é
`window.location.assign`, uma navegação de página inteira, não uma troca de
rota client-side) para todo `InvestigateDrawer` montado em qualquer tela, o
botão "investigar" existente — o mesmo que `spec.md` manda esta feature usar
no acceptance ("esta usa o botão existente da topbar") — **sempre tira o
operador do Painel e o leva para a página do run**, antes de qualquer
assertiva deste acceptance rodar.

Confirmado lendo o código (não apenas inferido do teste): `git log` mostra
que este mecanismo é anterior a toda a onda `specs_v8` (commits `b7003f1c`,
`19431fc0`, ambos v7). Não é um regressão desta feature nem da 070 — é o
comportamento atual, de produção, do único botão que o `spec.md` autoriza
o acceptance a usar.

**Consequência**: AN-01, AN-02, AN-04 (dois casos) e AN-05 — o User Story 1
inteiro, a "queixa literal do operador" que abriu a onda — e AN-14, não
podem passar contra este botão como ele existe hoje, porque a premissa da
alegação ("o operador não sai do Painel") contradiz o comportamento
documentado e deliberado do mecanismo que o próprio `spec.md` manda usar.
Isto é uma descoberta desta rodada, obtida rodando o acceptance de verdade
contra um build fresco e lendo "navigated to .../runs/run-000X" no log do
Playwright — não presumida, não inferida de um comentário.

**O que não fiz, e por quê**: não toquei `console/src/live/investigate.tsx`
nem `console/src/shell/shell.tsx`. São mecanismos compartilhados por toda
tela que usa o botão de investigar, não apenas o Painel; `spec.md` desta
feature nomeia explicitamente "o modal de iniciar investigação" como
escopo da 070 ("Out of Scope"); e mudar o comportamento de navegação global
por causa de uma tela é exatamente o tipo de mudança de raio largo que uma
worktree isolada, sem o resto da onda em vista, não deveria decidir sozinha.
Fica para o orquestrador decidir entre três caminhos, nenhum deles meu para
escolher: (a) a 070 muda esse comportamento quando reconstruir o modal,
e este acceptance destrava sozinho depois; (b) o acceptance é reescrito para
não presumir que o botão fica no Painel; (c) o modal ganha uma variante
"fique aqui" quando disparado a partir do Painel especificamente.

### 4.3 T008 — migração `0021`, não executável nesta worktree

Inalterado desde a rodada anterior: Postgres real inalcançável aqui (nem
`NINJASRE_TEST_DATABASE_URL`, nem `testcontainers` conseguindo abrir um
container, embora `docker ps` responda) — a mesma limitação que já valia
para `test_incident_public_id_migration.py` antes de qualquer coisa desta
feature. Pendente para quem tiver Postgres alcançável:
`uv run pytest tests/contract/persistence/test_estate_daily_snapshot_migration.py -v`.

### 4.4 T003/T031 — medição de efeito sobre a suíte de cenários sintéticos

T003 (a contagem "antes") nunca foi feita, por nenhuma das sessões
anteriores nem por esta. Sem essa baseline, T031 não tem contra o que medir
literalmente. A evidência disponível em seu lugar: a suíte completa de
`pytest` (13122 testes, que inclui os testes de dataset/fixture
determinísticos) está verde tanto antes quanto depois das mudanças desta
sessão — mas isto é "make verify ficou verde", não "medi o efeito
especificamente sobre a suíte de cenários sintéticos", que são reivindicações
diferentes. Nomeado como não feito, não como feito por proximidade.

### 4.5 T002, T033, T034, T035, T036 — do orquestrador, inalterado

`tasks.md` já rotula estas cinco explicitamente `(orquestrador)`. Nenhuma
delas foi tentada por mim — uma worktree isolada não alcança o cluster nem o
banco de staging.

## 5. Ressalva registrada sobre o "mini-timeline" de assunto (FR-023)

`subject-strip.tsx` usa `RecurrenceStrip` (barras por ocorrência, altura e
opacidade crescendo para a mais recente) para o elemento que agora carrega
`data-testid="subject-timeline"`, não `positionOnTimeline`/`TwentyFourHourStrip`
(pontos posicionados proporcionalmente numa janela de tempo real, o padrão
que a Incidents screen usa para o próprio strip de 24h). As duas leituras do
artboard (`Main.dc.html:255-289`) mostram barras de altura/opacidade
crescente sem posicionamento proporcional real — o SVG do próprio mockup não
posiciona os retângulos pela fração exata da janela, só pela ordem — o que
faz `RecurrenceStrip` uma leitura visualmente fiel, e é a que já estava em
uso. O acceptance spec (AN-11) só exige que `subject-timeline` exista e
seja visível, não testa a lógica de posicionamento, então esta escolha
satisfaz a alegação testável. A generalização de `positionOnTimeline` para
janela configurável (feita numa rodada anterior, 7/7 testes verdes) fica
como capacidade não consumida por este componente — não é código morto (a
Incidents screen a usa para outra coisa), mas a alegação anterior de que
seria "reusada pelo subject-strip" não se confirmou no código final e é
corrigida aqui.

## 6. Vazamento de segredo — declaração que este relatório carrega adiante

O lead relatou que o objetivo cru e labels de alerta chegam sem redação até
a timeline do incidente e o prompt do agente — reparo da feature irmã
(020/060), não desta. O que esta feature lê da mesma classe de fonte, para
ser reconferido quando aquele reparo aterrissar, **sem presumir limpo por
proximidade**:

- `activity-feed.tsx`, via a composição em `dashboard.tsx` (nova nesta
  rodada): `text(record, 'title')` de cada `Incident` para as entradas
  "incidente aberto"/"incidente fechado sozinho", e `text(record, 'summary')`
  de cada `ApprovalRequest` para "remediação proposta"/"decisão registrada".
- `activity-feed.tsx` também usa `subjectOf(record, locale).text` (que lê
  `AgentRun.headline`) para "investigação iniciada"/"investigação encerrada"
  — o mesmo campo que `run-band.tsx` já lia e que a rodada anterior já
  tinha nomeado como precisando reconferência.
- `subject-strip.tsx` lê `IncidentGroup.title` (`groupBySubject`, derivado
  de `Incident.title`) para o título de cada linha, e chama
  `SubjectLine`/`subjectTitle` (`incident-group-list.tsx`) para o
  subtítulo — o mesmo caminho que já resolve nome de recurso/nó em vez de
  identificador cru, mas que lê da mesma fonte potencialmente não redigida.

Nenhum destes foi comprovado vazando — apenas nomeados como leitores da
mesma classe de campo que o lead já encontrou vazando em outra tela. Precisa
ser reconferido contra dados reais depois que o reparo da feature irmã
mergear, não presumido limpo por este relatório.

## 7. Achados de processo desta rodada

- **`console_e2e run` não builda o console sozinho.** Ele espera
  `.next/standalone/server.js` já existir (`console_e2e.py:507-509`,
  levanta `HarnessError` se faltar) — mas se o diretório existir e estiver
  *desatualizado*, ele serve o build velho sem avisar. A primeira leitura
  desta rodada (§2, item 2) rodou contra um build de antes de
  `run-band`/`attention` existirem, mesmo com o código já commitado, porque
  ninguém tinha rodado `make console-build`/`console_gate build` depois
  daqueles commits. `make console-build` (ou
  `uv run python -m tools.console_gate build`) antes de qualquer leitura do
  acceptance é obrigatório, não opcional, e o sintoma de esquecê-lo é
  silencioso: a suíte roda, produz números, e mede o código errado.
- **Notificação de tarefa em segundo plano mentiu de novo, capturada com o
  processo ainda vivo no `ps aux`** — ver §3.2. Confirma o padrão já
  registrado em S1/S2/rodadas anteriores desta mesma feature: a notificação
  não é evidência, só o log é.
- **A regra "reveal" é uma palavra banida em todo `console/src`,
  mecanicamente, sem exceção de contexto.**
  `tests/unit/surfaces/masking.test.tsx::test_..._with_no_branch_in_between`
  varre todo `.ts`/`.tsx` (exceto o cliente gerado) por
  `/unmask|reveal|deredact|restoreMask/i` e falha por qualquer ocorrência —
  incluindo prosa de comentário sobre "revelar um campo de formulário", sem
  relação nenhuma com desmascarar um segredo. `attention-decision-controls.tsx`
  e `attention.tsx` usavam a palavra em prosa descrevendo a UI de recusa;
  reescrito para "abre"/"aparece" em vez de reformular o teste.

## 8. Declarações para o orquestrador aplicar no merge

- **Migração `0021_estate_daily_snapshot`**: `down_revision` continua
  `0019_users_email_optional` nesta worktree; o orquestrador re-aponta para
  `0020_run_objective` (da 020) no merge das duas árvores. Nota no
  docstring do próprio arquivo de migração; inalterado nesta rodada.
- **AN-03 continua nomeadamente pulada** (`test.skip`, razão na própria
  linha): depende de `stage_index`, que só existe depois do merge com a 020.
  Rodar a suíte de novo, sem editar o teste, depois do merge do slot.
- **O achado do §4.2 (o botão de investigar navega para fora do Painel)
  precisa de uma decisão do orquestrador antes que AN-01/02/04/05/14 possam
  fechar** — não é uma tarefa que uma próxima rodada desta worktree resolve
  sozinha, porque o mecanismo é compartilhado e a decisão é de produto.
- **Vazamento de segredo**: ver §6 — `activity-feed.tsx` e
  `subject-strip.tsx` leem `Incident.title`/`summary` e `ApprovalRequest.summary`;
  reconferir contra dados reais depois que o reparo da feature irmã mergear.
- **Nenhum token, ícone ou primitiva de motion faltando da fundação.** Um
  ajuste nesta rodada mereceu registro: `Textarea` (`components/form.tsx`,
  não é parte da fundação 000 — não está na lista congelada de
  `tokens.ts`/`icons.tsx`/`components/status.tsx`) ganhou um `data-testid`
  que já existia no seu próprio tipo (`FieldProps`) mas nunca tinha sido
  aplicado ao elemento; `Input`/`Select` no mesmo arquivo já faziam isso.
  Aditivo, sem consumidor existente afetado.
- **Capacidade retirada, nomeada, não substituída** (inalterado desde a
  rodada anterior): a banda "precisa de você" antiga mostrava um run
  falho com link para `/first-run`; a nova, seguindo `Main.dc.html`, só
  mostra aprovações pendentes. Dois testes em `dashboard.test.tsx`
  permanecem `it.skip` com a razão na própria linha.
- **Chaves i18n órfãs, inalterado**: `dashboard.attention.*` e
  `dashboard.band.*` (da `GuardianBand` retirada) continuam sem consumidor.
  Não removidas — decisão da rodada anterior, mantida.
