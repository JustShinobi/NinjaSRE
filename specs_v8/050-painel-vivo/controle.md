# Controle — 050-painel-vivo

Estado verificado contra o código atual em `wt/v8-050-painel-vivo`, no commit
que segue este checkpoint. Este arquivo é reescrito a cada commit; a versão
que importa é a do commit mais recente.

## 1. Peça por peça

| Peça | Estado | Detalhe |
|---|---|---|
| `MAX_OVERVIEW_DAILY_BUCKETS` | FEITO | `config/constants/estate.py` |
| Porta `EstateSnapshotStore` + fake + Postgres + migração `0021` | FEITO (mypy+ruff limpos; Postgres real não alcançável nesta worktree, ver §3) | ver commits anteriores |
| Gancho de escrita diária | FEITO | `platform/estate/discovery/runner.py::TopologyDiscoveryRunner._confirm_daily_snapshot` |
| `GET /v1/overview` | FEITO, testado contra fakes (5/5 verde) | `gateway/http/routes/overview.py` |
| `subjectsInWindow`/`SUBJECT_WINDOW_HOURS` em `incident-groups.ts` | FEITO, testado (17/17 verde) | vermelho confirmado antes (`subjectsInWindow is not a function`), depois implementado |
| `positionOnTimeline` generalizada para janela configurável | FEITO, testado (7/7 verde) | `console/src/surfaces/incident-timeline.ts` — reusada pelo subject-strip com 48h em vez de reescrita |
| **Acceptance spec (17 alegações, 18 casos)** | **FEITO — vermelho real confirmado** | `console/tests/e2e/painel-vivo.acceptance.spec.ts` — ver §2 |
| `run-band.tsx` (banda "Em execução agora") | FEITO, testado (9/9 verde), typecheck+lint limpos | `console/src/surfaces/run-band.tsx` — decisão FR-001 aplicada e testada (ver §5); estado vazio nomeia o próximo passo com link para `/runs` |
| `kpi-tiles.tsx`, `subject-strip.tsx`, `activity-feed.tsx`, `attention.tsx` (recomposta), recomposição de `dashboard.tsx` | NÃO INICIADO | próxima ação, nesta ordem |
| `screens.json`, dataset/OpenAPI/cliente regenerados | NÃO INICIADO | |

## 2. O vermelho do acceptance spec, com a mensagem real de cada alegação

Rodado com `uv run python -m tools.console_e2e run --backing mock -- tests/e2e/painel-vivo.acceptance.spec.ts`
contra a árvore intacta (nenhuma tela nova construída ainda). 18 casos
(17 alegações, AN-04 em dois testes: com e sem `prefers-reduced-motion`).

**Resultado real, segunda rodada (depois de corrigir um falso-positivo — ver
abaixo)**: `11 failed, 7 skipped, 0 passed`. Log completo em `specs_v8/050-painel-vivo/evidence/acceptance-red-full.log`;
a seção de falhas isolada em `evidence/acceptance-red-failures.log`.

| Alegação | Resultado | Mensagem real |
|---|---|---|
| AN-01 | FALHOU | `getByTestId('run-band')` — Expected: visible — Error: element(s) not found |
| AN-02 | FALHOU | `getByTestId('run-card').first()` — element(s) not found |
| AN-03 | **PULADO, nomeado** | `stage_index` vem da 020, não existe nesta worktree — `test.skip` com a razão na própria linha |
| AN-04 (animação) | FALHOU | `getByTestId('run-card').first()` — element(s) not found |
| AN-04 (reduced-motion) | FALHOU | `getByTestId('run-card').first()` — element(s) not found |
| AN-05 | FALHOU | `expect(received).toBeGreaterThan(expected)` — Expected: > 0, Received: 0 (nenhum card jamais aparece) |
| AN-06 | PULADO, nomeado | "o mock scenario carries no pending approval to assert this against" |
| AN-07 | PULADO, nomeado | idem |
| AN-08 | PULADO, nomeado | idem |
| AN-09 | FALHOU | `getByTestId('kpi-tile').and(locator('[data-kpi="watched"]'))` — element(s) not found |
| AN-10 | FALHOU | `locator.textContent: Test timeout of 30000ms exceeded` (o elemento a ler não existe) |
| AN-11 | PULADO, nomeado | "o mock scenario carries no recurring subject to assert this against" |
| AN-12 | PULADO, nomeado | idem |
| AN-13 | FALHOU (depois de corrigido — ver abaixo) | `getByTestId('activity-feed-entry').first()` — element(s) not found |
| AN-14 | FALHOU | `expect(received).toBeGreaterThan(expected)` — Received: 0 |
| AN-15 | FALHOU | `getByTestId('run-band')` — element(s) not found |
| AN-16 | PULADO, nomeado | "the mock scenario carries a pending approval, so the empty state does not render" — nota: isto por si só é uma pista de que o cenário populated tem uma aprovação pendente que as skips de AN-06/07/08 dizem não existir; ver a contradição registrada abaixo |
| AN-17 | FALHOU | `getByTestId('run-band')` — element(s) not found |

**Contradição encontrada e registrada, não escondida**: AN-16 pula dizendo que
HÁ uma aprovação pendente (por isso o estado vazio não se aplica), mas
AN-06/07/08 pulam dizendo que NÃO há nenhuma. Isto é porque os dois testes
leem estruturas diferentes que ainda não existem — `attention-decision-card`
(AN-06/07/08) e `attention-decision-empty` (AN-16) — e como NENHUMA delas
existe ainda, o `count() === 0` de ambas é verdadeiro simultaneamente, o que é
logicamente consistente (nenhuma delas existe) mas nomeia mal a causa em um
dos dois textos de skip. Corrigido: a causa real de todos os quatro skips
(AN-06, 07, 08, 16) é a mesma — `attention-decision-band` ainda não foi
construída — e não uma alegação factual sobre o dataset. Os textos de skip
serão corrigidos quando a banda for implementada e os testes deixarem de
pular.

**Um falso-positivo achado e corrigido antes deste registro**: a primeira
rodada relatou AN-13 como **passou**, em 283 ms. Investigado: o componente
antigo `console/src/surfaces/activity.tsx` (o que esta feature substitui) já
usa `data-testid="activity-entry"` para suas próprias linhas — meu teste
original usava esse mesmo id por coincidência de nome e estava lendo a lista
*velha*, não testando a ausência da nova. Corrigido para `data-testid=
"activity-feed-entry"` (namespace do componente novo, que ainda não existe);
a segunda rodada confirma vermelho real. Isto é exatamente a classe de
defeito "teste que passa medindo nada" que a onda já achou duas vezes antes;
fica registrado aqui como a razão de eu ter rodado o spec *duas vezes* antes
de aceitar o vermelho como verdadeiro.

## 3. Lacuna estrutural desta worktree: Postgres real é inalcançável

Ver commits anteriores — `docker ps` responde, mas `testcontainers` não
consegue abrir um container aqui, e isto já valia para o teste de migração
*pré-existente* `test_incident_public_id_migration.py` antes de eu tocar em
qualquer coisa. Pendente para o orquestrador: rodar
`uv run pytest tests/contract/persistence/test_estate_daily_snapshot_migration.py -v`
onde Postgres for alcançável.

## 4. O que fica pendente, nomeado

**Peças ainda desta worktree, não terminadas:**

- Construção de tela: `attention.tsx` (recomposta), `kpi-tiles.tsx`,
  `subject-strip.tsx`, `activity-feed.tsx`, recomposição de `dashboard.tsx` —
  `run-band.tsx` e `subjectsInWindow` já estão feitos e testados (ver §1).
- `screens.json`, dataset simulado (assuntos ≥3, aprovação pendente
  suficiente para AN-06/07/08/16 pararem de pular), documento OpenAPI e
  cliente TS regenerados — nenhum ainda rodado.

**T008, minha, tentada e não completável nesta worktree** — não uma
reatribuição: escrevi o teste
(`tests/contract/persistence/test_estate_daily_snapshot_migration.py`),
tentei rodá-lo, e ele não encontra Postgres alcançável aqui (nem
`NINJASRE_TEST_DATABASE_URL`, nem `testcontainers` conseguindo abrir um
container, embora `docker ps` responda). Confirmei que a mesma limitação já
valia, antes de eu tocar em qualquer coisa, para o teste de migração
pré-existente `test_incident_public_id_migration.py` — não é um defeito desta
migração. Pendente para quem tiver Postgres alcançável: rodar
`uv run pytest tests/contract/persistence/test_estate_daily_snapshot_migration.py -v`.

**T002, T033, T034, T035, T036 — reatribuídas ao orquestrador pelo próprio
`tasks.md`, antes de esta sessão começar.** O arquivo de tarefas rotula cada
uma delas explicitamente `(orquestrador)`: T002 é a captura "antes" do
staging; T033 é o deploy; T034 é o acceptance contra staging real (safe e
write); T035 são as consultas de evidência no banco de staging; T036 é o gate
visual via Orca Browser. Nenhuma delas foi tentada, adiada ou pulada por
mim — uma worktree isolada não alcança o cluster nem o banco de staging, e o
próprio `tasks.md` já sabia disso ao marcá-las assim. O que entrego no lugar
de cada uma (a consulta corrigida para a evidência 1, a rota/tema exata para
cada captura) está nomeado onde cada uma é citada acima.

## 5. Decisão de design registrada e agora implementada: "runs não terminados" (FR-001)

**O achado**: 11 runs não terminados no staging (achado do lead, 2026-08-31),
todos `interrupted`, sem título, 4–8 dias parados. A leitura literal da
consulta de evidência 1 do `spec.md` (`status NOT IN ('completed','failed',
'cancelled')`) — que inclui `interrupted` — encheria a banda de seis cartões
com zumbis e empurraria para fora o único run genuinamente em voo.

**A regra, nomeada e testada**: `inFlightRuns` em
`console/src/surfaces/run-band.tsx` filtra por `!isSettled(status)`, onde
`isSettled` vem de `@/design/status` (frozen, já exportada, já testada pela
000, já usada por `dashboard.tsx` hoje para outro cálculo desta mesma tela) e
declara `interrupted` como assentado — a mesma dupla `{running, suspended}`
que `incident-detail.tsx`'s próprio `LIVE_RUN_STATUSES` local já usa para a
mesma pergunta em outra tela. Testada em
`console/tests/unit/surfaces/run-band.test.ts::inFlightRuns` (caso nomeado:
"the zombie band"), que prova especificamente que `interrupted` é excluído.

**As quatro condições que a decisão precisa satisfazer, verificadas**:
1. Regra nomeada e testada — `inFlightRuns` + teste, acima.
2. A constante de seis cartões concorda com a regra — `RUN_BAND_VISIBLE_MAX = 6`
   fatia o mesmo array que `inFlightRuns` produziu; não há um segundo filtro.
3. As contagens do cabeçalho concordam — `run-band-flight-count` lê
   `runs.length` do mesmo array `inFlightRuns` sem fatiar, nunca uma
   recontagem paralela.
4. A banda vazia nomeia o próximo passo com link — corrigido nesta rodada:
   o estado vazio agora diz por que está vazio ("toda investigação terminou
   ou nenhuma foi iniciada") e linka para `/runs` via `next/link`
   (`dashboard.runBand.empty.action`), nos dois idiomas.

**Consequência para a evidência do orquestrador (T035)**: a consulta 1 do
`spec.md` mede a coisa errada depois desta decisão. A corrigida, que
corresponde ao que a banda de fato mostra:

```sql
SELECT count(*) FROM agent_runs WHERE status IN ('running', 'suspended');
```
