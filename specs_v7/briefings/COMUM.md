# Briefing comum — vale para toda feature da onda specs_v7

Leia antes do briefing da sua feature, nesta ordem:
[../README.md](../README.md) (decisões e recorte),
[../DIAGNOSTICO.md](../DIAGNOSTICO.md) (defeitos com `file:line` e evidência de
banco), [../REGRAS.md](../REGRAS.md) (auditoria das regras e emendas
propostas), [../EXECUCAO.md](../EXECUCAO.md) (pares, donos de single-write,
validação em staging), e o `backlog.md` da raiz quando a sua feature o citar.

## Forma da casa

- Escreva `spec.md`, `plan.md`, `tasks.md` e `checklists/requirements.md` no
  diretório da sua feature, seguindo `.specify/templates/*` na forma que a v6
  praticou — use `specs_v6/001-escopo-validavel/` como exemplar de voz e
  estrutura (e `specs_v6/060-primeiro-incidente/` quando a feature for de
  fluxo ponta-a-ponta). **Não** escreva `controle.md` — é do implementer.
- **pt-BR** nos documentos de spec; código e strings de produto em inglês.
  Texto de UI via i18n (en sempre; pt-BR junto quando a feature tocar o
  catálogo de mensagens).
- Specs podem citar FR-/SC- entre si e apontar documentos da onda (não
  committed). **Nenhuma tarefa pode instruir** escrever FR-, artigos da
  constituição, números de feature ou caminhos de planejamento em arquivo
  committed. A substância vai no arquivo committed; a referência fica na spec.
- Plan inclui Constitution Check contra a constituição **como ela estará após
  a 000** (2.2.0 — inclui "composed or it is not shipped"). Toda feature que
  entrega mecanismo novo declara no plan **qual composition root o constrói**
  e o tasks.md tem tarefa explícita de composição + prova no caminho de
  serving. "Testes verdes no harness" não fecham tarefa de comportamento.
- Test-first: o teste que falha aterrissa antes da implementação, com o
  vermelho confirmado e registrado. Testes moram onde os runners coletam:
  unit console em `console/tests/unit/`, Playwright em `console/tests/e2e/`,
  visual em `console/tests/visual/`, Python conforme `pytest.ini`.

## Alegações normativas no lugar de mockup (decisão desta onda)

A v7 não tem mockups prontos. Feature de console traz no spec uma seção
**"Alegações normativas"** — frases curtas, individualmente testáveis (uma
vírgula é fronteira de requisito), derivadas do DIAGNOSTICO — e o
`console/tests/e2e/<slug>.acceptance.spec.ts` as codifica, confirmado
**vermelho antes da tela**. Tela genuinamente nova (não rework) pode ter
tarefa de mockup HTML próprio em `specs_v7/mockups/` antes do acceptance.
Viewport normativo de medição: **1920×1080** (declarado no spec que medir).

## Validação em staging (todo slot)

O ciclo do EXECUCAO.md §3 vale para a sua feature: o orquestrador roda
`make deploy-stg` no fim do slot e os acceptance rodam contra
`https://stg-ninjasre.lan.kyo.ninja`. Se a sua feature alega gravação
(traces, custo, vínculos), o DoD inclui **contagens no banco de staging** —
enumere no spec as consultas exatas que provam. Specs marcam quais acceptance
são staging-safe (leitura/propose-only) — só esses rodam lá.

## Single-write e fronteiras

`console/src/i18n/*.ts`, `console/src/shell/routes.ts`,
`console/visual/screens.json` têm dono por slot (EXECUCAO.md §2). Se a sua
feature **não** é a dona no seu slot, o tasks.md instrui a declarar
chaves/rotas no relatório final em vez de editar. Nenhuma tarefa toca outro
diretório de feature.

## Fatos que nenhuma spec re-deriva (verificados em 2026-08-23)

- Staging k3s `k3s-stg-ninjasre`, ingress `/ → web` (console Next 16.3.0),
  `/webhooks → app`; banco `ninjasre-stg-db` em `10.20.20.54`.
- Banco: `tool_calls=0`, `run_turns=0`, `evidence=0`, `trace_events=73` com
  37 runs completed; todo `agent_runs.summary` recente começa com `###`.
- Contrato: `InvestigationSummary` em
  `gateway/http/routes/investigations.py:35-60` — só `summary`, sem headline.
- Console: `readFailure` (`console/src/surfaces/failures.ts:154`) devolve o
  documento como título; `run-detail.tsx:96,129` e
  `runs/[runId]/page.tsx:50` o usam; sem lib de markdown no `package.json`.
- Ids de incidente: `alert:alertmanager:<sha256>@<ISO+00:00>`; Next entrega
  `params.incidentId` percent-encoded; `bind()` re-encoda
  (`console/src/lib/api.ts:66-76`); painéis de `/v1/incidents/{id}` falham.
- Gates de ação: `RemediationGate` (`platform/remediation/gating.py:187`),
  `AutonomyGate` (`platform/autonomy/decision.py:168`) — construídos só em
  testes/mocks. 80 capacidades: 44 read + 12 read_sensitive; 24 escrevem
  (15 reversíveis, 6 irreversíveis, 3 destrutivas); 24 `requires_approval`.
- Cache: `/incidents` renderizou sem requisição ao gateway (Full Route Cache);
  `authorised()` já usa `cache: 'no-store'` por request
  (`console/src/surfaces/read.ts:26`).
- Constituição no arquivo: **2.0.0**; CLAUDE.md afirma 2.1.0; ADR 0009 sem
  status Superseded; índice de ADRs para no 0011.
- Vocabulário de credencial (herdado, continua normativo): **Not connected ·
  Stored · Verified · Degraded · Failing**.
- Gemini Verified via vault/proxy; Alertmanager real entregando
  RestoreDrillStale, CronJobStale, InstanceDown, BlackboxProbeFailed,
  ProxmoxCriticalLogDetected.

## Ferramentas

Use `codegraph_explore` para blast radius e fonte antes de citar símbolos —
não re-derive o que o DIAGNOSTICO já cravou. `SPECIFY_FEATURE_DIRECTORY` em
vez de editar `.specify/feature.json` se usar scripts do spec-kit (a v6
abandonou o caminho scriptado; escrever direto dos templates é a forma aceita).
