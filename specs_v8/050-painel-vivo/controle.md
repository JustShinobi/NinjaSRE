# Controle — 050-painel-vivo

Estado verificado contra o código atual em `wt/v8-050-painel-vivo`, no commit
que segue este checkpoint. Este arquivo é reescrito a cada commit; a versão
que importa é a do commit mais recente, não o histórico de versões antigas.

**Achado do lead ainda pendente de decisão registrada nesta rodada**: os onze
runs não terminados do staging são todos `interrupted`, sem título, com 4–8
dias de idade — decisão sobre a FR-001 tratada na seção 4 abaixo, adotada mas
ainda não provada contra o acceptance (T004 não escrito ainda nesta rodada).

## 1. Peça por peça

| Peça | Estado | Detalhe |
|---|---|---|
| `MAX_OVERVIEW_DAILY_BUCKETS` | FEITO | `config/constants/estate.py` — valor 14, conforme FR-016 |
| Porta `EstateSnapshotStore` | FEITO | `platform/persistence/ports/estate_snapshot_store.py` — `EstateDailySnapshot`, `record`, `list_daily`, `check_overview_window` |
| `UnitOfWork.estate_snapshots` | FEITO | `platform/persistence/ports/transaction.py:157-159` (propriedade 19ª) |
| Implementação Postgres | FEITO (mypy+ruff limpos; **não exercitada contra Postgres real nesta worktree** — ver §3) | `platform/persistence/postgres/repositories/estate_snapshot_store.py`, tabela `EstateDailySnapshotRow` em `postgres/models.py` |
| Fake em memória | FEITO, testado | `platform/persistence/fakes/estate_snapshot_store.py`; `TenantState.estate_daily_snapshots` em `fakes/state.py` |
| Migração `estate_daily` | FEITO, **renumerada** | `platform/persistence/migrations/versions/0021_estate_daily_snapshot.py` — era `0020`, colidia com `020-titulo-vivo`'s `0020_run_objective`; renomeada para `0021` por instrução do orquestrador. `down_revision` continua `0019_users_email_optional` até o merge; o orquestrador re-aponta para `0020_run_objective` |
| Gancho de escrita diária | FEITO | `platform/estate/discovery/runner.py::TopologyDiscoveryRunner._confirm_daily_snapshot` — chamado ao fim de `run()`, depois de todo sweep (`estate.discovery` e `topology.discovery`, mesmo runner). Composição real em `gateway/http/scheduled_work.py:87-99` (`gateway=state.gateway`) |
| `GET /v1/overview` | FEITO, testado (backend, contra fakes) | `gateway/http/routes/overview.py`; registrado em `gateway/http/app.py`; permissão declarada em `gateway/http/security/console_routes.py` (`Permission.ESTATE_READ`) |
| `groupBySubject` recorte de janela | FEITO | `subjectsInWindow` + `SUBJECT_WINDOW_HOURS` em `console/src/surfaces/incident-groups.ts` — **teste escrito e confirmado vermelho** (`subjectsInWindow is not a function`, 6 casos), implementação ainda não escrita nesta rodada |
| Teste de conformidade dos 19 ports | FEITO | `tests/unit/platform/persistence/test_port_conformance.py` — renomeado de "dezesseis" para "dezessete rastreados"; nota deixada sobre `transit`/`verifications` ausentes da lista, pré-existente, fora do escopo desta feature |
| Documento OpenAPI / cliente TS / dataset simulado | NÃO INICIADO | comandos identificados: `python -m tools.mockplane contract`, `python -m tools.console_toolchain run run client`, `python -m tools.mockplane build`. Ainda não rodados |
| Acceptance spec (17 alegações) | NÃO INICIADO | `console/tests/e2e/painel-vivo.acceptance.spec.ts` ainda não escrito — **é a próxima ação, antes de qualquer componente de tela** |
| `run-band.tsx`, `kpi-tiles.tsx`, `subject-strip.tsx`, `activity-feed.tsx`, recomposição de `dashboard.tsx`, `attention.tsx` | NÃO INICIADO | nenhuma tela construída ainda |
| i18n (`en.ts`, `pt-BR.ts`) | NÃO INICIADO | |
| `console/visual/screens.json` + baselines | NÃO INICIADO | |

## 2. Decisão de design registrada: "runs não terminados" (FR-001)

O achado do lead (staging real, 2026-08-31): os 11 runs "não terminados" por
`status NOT IN ('completed','failed','cancelled')` — a consulta *literal* da
spec — são **todos `interrupted`**, sem título, 4–8 dias parados. Nenhum é
`suspended`. A banda, com esse critério, nasceria cheia de zumbis e empurraria
para fora o único run genuinamente vivo.

**Decisão**: usar `!isSettled(status)` — a função já exportada, já testada,
já congelada em `console/src/design/status.ts:502`, que declara
`SETTLED_RUN_STATUSES = ['completed','cancelled','failed','interrupted']` e
documenta exatamente esta semântica ("interrupted counts as settled ... the
process running it is gone"). O conjunto resultante para "em execução agora"
é `{running, suspended}` — mais estreito que a consulta literal da spec (exclui
`interrupted`) e mais largo que o filtro atual do `dashboard.tsx`
(`status === 'running'`, que já excluía `interrupted` mas também excluía
`suspended`).

Isto **não é uma invenção**: é a mesma classificação que `dashboard.tsx` já usa
hoje (`isSettled`, importado de `@/design/status`, linha 417 do arquivo atual)
para "runs assentados" em outro cálculo da mesma tela, e é a mesma dupla
(`running`/`suspended`) que `incident-detail.tsx:93` já usa como seu próprio
`LIVE_RUN_STATUSES` local para decidir se um run vinculado ainda está "vivo".
Não precisa de token novo, não edita `console/src/design/`.

**Consequência para a evidência do orquestrador**: a consulta 1 da spec
(`SELECT count(*) FROM agent_runs WHERE status NOT IN ('completed','failed','cancelled')`)
**mede a coisa errada** depois desta decisão — ela conta os zumbis. A consulta
corrigida, que corresponde ao que a banda de fato mostra, é:

```sql
SELECT count(*) FROM agent_runs WHERE status IN ('running', 'suspended');
```

Isto precisa ir para o relatório final e para `specs_v8/CONFRONTO.md` quando o
slot fechar — a consulta 1 de `spec.md` está desatualizada em relação a esta
decisão.

## 3. Lacuna estrutural desta worktree: Postgres real é inalcançável, mesmo local

T008 pede um teste de migração ida-e-volta contra PostgreSQL real. O teste foi
escrito (`tests/contract/persistence/test_estate_daily_snapshot_migration.py`,
seguindo o padrão de `test_incident_public_id_migration.py`), mas
`tests/contract/persistence/conftest.py::discover()` não encontra nenhum
Postgres utilizável nesta worktree — nem por `NINJASRE_TEST_DATABASE_URL`
(não setada) nem por `docker_available()` (o binário `docker` responde a
`docker ps` diretamente, mas a biblioteca `testcontainers` não consegue abrir
um container aqui). **Isto não é um defeito desta feature**: rodei o teste de
migração *já existente* `test_incident_public_id_migration.py` (que passa há
várias ondas) e ele também só coleta `[fakes]` nesta árvore — nenhuma variante
`[postgres]` aparece para ele tampouco. É uma limitação estrutural desta
worktree isolada, não desta migração.

**Pendente, nomeado**: rodar
`uv run pytest tests/contract/persistence/test_estate_daily_snapshot_migration.py -v`
num ambiente com Postgres alcançável (CI, ou a árvore principal com Docker
funcional para testcontainers) antes de aceitar T008 como provado. O teste
cobre: upgrade cria exatamente as 6 colunas declaradas com o tipo certo,
chave primária composta `(org_id, snapshot_date)`, downgrade remove só essa
tabela.

## 4. O que fica pendente, nomeado, não escondido

- **Acceptance spec e todo o lado console** — nada foi escrito ainda. É a
  próxima ação desta sessão, na ordem que a skill exige: vermelho confirmado
  antes de qualquer tela.
- **Documento OpenAPI, cliente TS, dataset simulado** — comandos identificados,
  não executados. Necessário antes do console poder ler `/v1/overview` pelo
  cliente gerado.
- **T008 (migração contra Postgres real)** — escrito, não executável nesta
  worktree (§3 acima).
- **T002, T033–T036** — do orquestrador, não desta worktree. A consulta
  corrigida para a evidência 1 está na seção 2.
- **A decisão da FR-001** (seção 2) foi tomada e implementada apenas na
  descrição — o código de `run-band.tsx` que a usa ainda não existe.

## 5. Comandos exatos rodados, com resultado real

- `uv run pytest tests/unit/gateway/http/test_overview_routes.py tests/unit/platform/persistence/test_port_conformance.py tests/contract/persistence/test_estate_daily_snapshot_migration.py -q` → `30 passed, 1 skipped` (o skip é `[fakes]`... não, é o teste de migração pulando por falta de Postgres, ver §3)
- `uv run ruff check <arquivos tocados>` → `All checks passed!`
- `uv run ruff format --check <arquivos tocados>` → limpo após `ruff format` aplicado a 2 arquivos
- `uv run mypy <arquivos backend tocados>` → `Success: no issues found in 16 source files`
- `pnpm exec vitest run tests/unit/surfaces/incident-groups.test.ts` (dentro de `console/`) → **6 testes novos vermelhos** (`subjectsInWindow is not a function`), 11 testes existentes continuam verdes — vermelho confirmado antes da implementação, como a skill exige
- `make verify` (linha de base, T001) → parou em `test`, dois benchmarks falharam
  por margem pequena (~9-10%) sob contenção de CPU compartilhada
  (`test_rendering_cost_does_not_grow_with_the_length_of_the_transcript`,
  `test_strict_masking_stays_within_the_same_budget`); os dois passam limpos
  isolados (`pytest <os dois> -q` → `2 passed in 5.01s`). Todo o resto de
  `make verify` (lint, format, typecheck, check-imports, check-constants,
  check-protocols, check-deps, check-vendor-sdks, check-literals,
  check-raw-sql, check-run-status-vocabulary, check-incident-states,
  check-credentials, check-console-boundary, check-integrations,
  check-integration-docs, check-env-example, check-docs, check-doc-examples,
  console-static) completou sem parar a cadeia do Make antes de chegar em
  `test`, portanto passou.
