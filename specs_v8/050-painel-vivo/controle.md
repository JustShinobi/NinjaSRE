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
| `subjectsInWindow`/`SUBJECT_WINDOW_HOURS` em `incident-groups.ts` | Teste escrito, vermelho confirmado (`subjectsInWindow is not a function`) — implementação ainda não escrita |
| **Acceptance spec (17 alegações, 18 casos)** | **FEITO — vermelho real confirmado** | `console/tests/e2e/painel-vivo.acceptance.spec.ts` — ver §2 |
| `run-band.tsx`, `kpi-tiles.tsx`, `subject-strip.tsx`, `activity-feed.tsx`, recomposição de `dashboard.tsx`, `attention.tsx` | NÃO INICIADO | próxima ação |
| i18n, `screens.json`, dataset/OpenAPI/cliente regenerados | NÃO INICIADO | |

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

- Toda a construção de tela (run-band, attention, kpi-tiles, subject-strip,
  activity-feed, dashboard.tsx) — próxima ação, nesta ordem, um componente por
  vez, cada um fechando as alegações que só ele resolve.
- `subjectsInWindow` — teste vermelho escrito, implementação pendente.
- i18n, `screens.json`, dataset simulado (assuntos ≥3, aprovação pendente
  suficiente para AN-06/07/08/16 pararem de pular), documento OpenAPI e
  cliente TS regenerados.
- T008 contra Postgres real — do orquestrador ou de um ambiente com Docker
  funcional para testcontainers.
- T002, T033–T036 — do orquestrador.

## 5. Decisão de design registrada: "runs não terminados" (FR-001)

Ver commit anterior — resumo: `!isSettled(status)` de `@/design/status`
(já exportada, já testada, já congelada), resultando em `{running, suspended}`.
A consulta de evidência 1 do `spec.md` (`status NOT IN ('completed','failed',
'cancelled')`) mede a coisa errada depois desta decisão — a corrigida é
`status IN ('running', 'suspended')`.
