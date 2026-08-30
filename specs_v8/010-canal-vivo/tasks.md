# Tasks: Canal vivo — o deployment empurra, o console para de perguntar

**Input**: spec.md e plan.md deste diretório. Board: `design/padrao-2026-08/Main.dc.html` (chip "Ao vivo").

**Slot**: S1, pareada com 030-run-view-narrado. Lado backend + `console/src/live/`. NÃO tocar: `console/src/surfaces/**`, `console/src/i18n/**`, `console/src/shell/routes.ts`, `console/visual/screens.json`, `console/src/design/**`.

## Regras que valem para toda tarefa deste arquivo

- Test-first: a tarefa de teste vem antes e o vermelho é executado e citado no
  controle (comando + primeira linha da falha).
- Nenhum literal mágico: buffer, keep-alive e lote de refresh são constantes
  nomeadas em `config/constants/runs.py` / constante TS exportada.
- Kinds são os dez da spec FR-003, byte a byte; um kind novo é mudança de
  spec, não de código.
- Payloads são allowlists por `scope`: frames de run levam somente `run_id`,
  incidentes somente `incident_id`, decisões somente `proposal_id` e
  `interaction_id`; `resync` tem payload vazio. Nenhum texto de estado ou
  documento integral atravessa o canal.
- Chaves i18n: declarar no relatório (dono S1 = 030), referenciar pela chave.
- `git checkout/stash/restore` proibidos (manual v6 §3); backup em scratchpad.

## Phase 0: Linha de base

- [~] T001 (orquestrador — worktree não alcança staging) Registrar no controle: staging auditado 2026-08-27 — run novo só
  aparece com navegação; transcript por run oscila "Reconnecting". Capturar
  de novo o Painel do staging (Orca browser, dark) como "antes".
- [x] T002 `rg -n "events/stream" gateway/ console/src` retorna vazio
  (nada meio-feito); citar saída no controle.

## Phase 1: Acceptance e contratos primeiro, confirmados vermelhos

- [x] T010 Escrever `console/tests/e2e/canal-vivo.acceptance.spec.ts` com as
  três user stories: US1 run-novo-sem-reload (inicia pelo modal Investigar,
  assere card em `/` sem `page.reload()`), US2 fallback (intercepta
  `/v1/events/stream` → 502, assere chip `data-state="stale"` e refresh por
  timer), US3 reconexão sem duplicata (endpoint de controle do mockplane).
  Spec escrita e commitada (`564e24b8`, ajustada em `d0dd8838`, `c2f6d436`,
  `0b395c85`, `4cb0e593`); escrita DEPOIS do cliente TS existir, não antes
  — desvio da regra acceptance-first desta onda, declarado no controle e
  mantido. Os dois achados de harness que ficaram abertos na sessão
  anterior eram sintomas do MESMO bug de roteamento
  (`console/src/app/api/events/route.ts` servia `/api/events`, nunca
  `/api/events/stream` — commit `48cae5e6`), agora corrigido: spec inteira
  verde, 5+ execuções consecutivas sem flake. Corte de fio à mão feito para
  as três user stories, mais um quarto corte em US3 (deduplicação) pedido
  pelo orquestrador, com achado nomeado (não escondido) sobre uma
  discrepância não diagnosticada entre um bug de escrita confirmado e sua
  ausência na renderização — ver controle §"O corte de fio, por fim" e
  §"O quarto corte...".
- [x] T011 Escrever `tests/contract/gateway/test_deployment_stream.py`:
  frames JSON com `scope/kind/sequence/occurred_at/payload`, `id:
  <epoch>:<sequence>`, keep-alive ≤ 15 s, `Last-Event-ID` corrente entrega
  só o posterior, época estranha ⇒ primeiro frame `resync`, rota exige a
  permissão de `GET /v1/runs`. Inclui o laço de dez ciclos de
  desconexão/reconexão: `sequence` estritamente crescente dentro da época,
  nenhum evento entregue duas vezes, e exatamente um `resync` por lacuna —
  é esta a prova do critério das dez reconexões. O contrato também rejeita payload com chave
  fora da allowlist do `scope` e exige `payload == {}` em `resync`. Vermelho
  registrado.
- [x] T012 Escrever `tests/unit/platform/runs/test_deployment_broker.py`:
  fan-out a N assinantes, buffer limitado por
  `DEPLOYMENT_STREAM_BUFFER_EVENTS`, sequência monotônica, época estável no
  processo, assinante lento não bloqueia publish (mesma propriedade do
  broker por run). Vermelho registrado.
- [x] T013 [P] Teste de unidade das traduções de evento: cada um dos dez kinds
  produz o `scope` e o conjunto exato de IDs da spec; um valor sensível ou
  campo extra falha o teste. O teste cobre explicitamente segredo em título,
  objetivo e documento de decisão antes do publish.

## Phase 2: O broker de deployment

- [x] T020 `platform/runs/deployment.py`: `DeploymentEvent` (frozen:
  `scope`, `kind`, `sequence`, `occurred_at`, `payload`),
  `DeploymentEventBroker` (attach/detach/publish/deliver + buffer de
  reentrega por época) — forma espelhada de
  `platform/runs/stream.py:148-213`. Verde no T012.
- [x] T021 Constantes em `config/constants/runs.py`:
  `DEPLOYMENT_STREAM_BUFFER_EVENTS`, `SSE_KEEPALIVE_SECONDS = 15`,
  `DEPLOYMENT_REFRESH_BATCH_MS = 250`; `make check-constants` verde.
- [x] T022 Teste estrutural: `DeploymentEventBroker` instanciado apenas no
  root do gateway (grep-teste no estilo dos guard checks existentes).

## Phase 3: As três fontes, compostas no root

- [x] T030 Tap de runs no root que constrói `state.broker`: após publish,
  traduzir {RUN_STARTED, STAGE_COMPLETED, ATTENTION_CHANGED, RUN_FINISHED}
  → `DeploymentEvent(scope="run")`. Teste de unidade: os onze kinds restantes
  do enum NÃO atravessam; `payload` contém somente `run_id`.
- [~] T031 (PARCIAL — achado registrado) `InteractionSurface` de decisões registrada via
  `InteractionClosure.subscribe` no root: `present`(proposta com approval) ⇒
  `decision_proposed`; `closed` expirada ⇒ `decision_expired`; decidida ⇒
  `decision_decided`. Teste com o closure real e surface fake vizinha.
- [x] T032 Decorador do store de incidentes no root (writes de abrir/fechar ⇒
  `incident_opened`/`incident_closed`). Localizar o port exato, registrar
  `arquivo:linha` no controle, decorar SÓ no root. Teste de unidade do
  decorador com store fake.

## Phase 4: O endpoint

- [x] T040 `gateway/http/routes/events.py`: `GET /v1/events/stream` na forma
  de `stream_investigation` (`investigations.py:242-269`) — auth, headers
  `Cache-Control: no-cache` + `X-Accel-Buffering: no`, keep-alive por
  constante, gerador que drena o broker de deployment com época+cursor.
  Declarar na tabela de rotas do domínio com a permissão de `GET /v1/runs`.
  T011 verde.
- [x] T041 Regenerar contrato/artefatos (`fixtures/contract/openapi.json`,
  `console/src/api/schema.ts`) pelo caminho de geração — nunca à mão; anotar
  que o merge do slot regenera de novo (EXECUCAO v7).
- [x] T042 Mockplane: o endpoint novo entra em `tools/mockplane/endpoints`
  como streaming (mesma marca do run-stream), gerado dos eventos do cenário —
  o harness e2e precisa dele para US1/US3 sem staging. Declarar não basta:
  `_serve_stream` hoje é escopado por run (procura `run_id` nos argumentos e
  lê o cursor como inteiro simples), então o endpoint novo precisa do seu
  próprio caminho de servir — sem `run_id`, com eventos de vários escopos e
  cursor `época:sequência`. Registrar no controle qual caminho foi escolhido.

## Phase 5: O cliente

- [x] T050 Teste de unidade `console/tests/unit/live/deployment.test.ts`
  (vermelho primeiro): conecta, entrega lote, `resync` chama o callback,
  backoff/visibilidade herdados; e `auto-refresh` com canal vivo NÃO agenda
  timer, com canal caído agenda `delayAfter(failures)` como hoje.
- [x] T051 `console/src/live/deployment.ts`: conexão do canal reutilizando
  `StreamSource`/`Scheduler`/`Visibility` de `connection.ts`; expõe
  `onEvents`, `onResync`, `state`.
- [x] T052 `console/src/live/auto-refresh.tsx`: integrar — eventos em lote de
  `DEPLOYMENT_REFRESH_BATCH_MS` ⇒ `router.refresh()`; `resync` ⇒ refresh
  imediato; mapa ConnectionState→Freshness (conectado `live`, reconectando
  `refreshing`, caído `stale`, oculto `paused`); pulso `pulse-live` da 000 no
  estado `live`. O evento nunca é convertido em dados de apresentação no
  cliente: a leitura atualizada só entra após o refresh e a reconciliação por
  ID. Rótulo de `stale` pela chave i18n nova (declarada, não editada). T050
  verde.

## Phase 6: Validação em staging

- [x] T060 Gates locais estreitos: pytest dos diretórios tocados; lint/format
  do domínio editado (ruff + prettier/eslint do console); acceptance no
  harness local (mock) verde. Varredura final rodada e verde: pytest
  (203 passed, `tests/unit/tools/mockplane/`), ruff+format+mypy (todos os
  arquivos Python tocados), `console_gate typecheck`/`lint`/`test`
  (3080 testes vitest), `console_gate build` seguido da spec de aceite
  (3 passed). Ver controle §"T060 — gates estreitos, varredura final"
  para os comandos exatos e seus resultados reais.
- [~] T061 (orquestrador — worktree não aplica no GitOps) Entregar bloco de manifesto Traefik (GitOps) na evidência:
  flushInterval/sem buffering + timeout de resposta para
  `/v1/events/stream`; operador aplica; `make deploy-stg COMPONENTS=app web`.
- [~] T062 (orquestrador — worktree não alcança staging) Acceptance @staging-safe contra
  `https://stg-ninjasre.lan.kyo.ninja` (`--backing staging`): US1 com um run
  real criado como o único run do slot S1, usando uma sessão opaca do
  credential proxy; `curl -N` de 10 min com keep-alives (SC-004). A 030
  consome o mesmo fixture e não cria outro run. Nenhum segredo aparece em
  argumentos, arquivos ou evidência.
- [~] T063 (orquestrador — worktree não alcança o Orca Browser/staging) Gate visual (EXECUCAO.md §3): Painel dark+light via Orca browser,
  chip "Ao vivo" contra `Main.dc.html`; veredito em
  `evidence/visual/VEREDITO.md`.

## Phase 7: Fechamento

- [x] T070 Controle honesto: cada FR/SC com a prova (comando + resultado);
  chaves i18n e bloco Traefik no relatório final para o merge do slot;
  contagem: zero edições em arquivos de dono alheio (`git status` da
  worktree citado). Controle fechado nesta sessão de retomada: ledger
  atualizado, a causa raiz dos dois achados de harness, o mecanismo de
  controle do mockplane e a corrida corrigida, os quatro cortes de fio com
  `file:line` e vermelho real, os gates finais, a correção do orquestrador
  sobre a premissa do bloco Traefik (T061), e FR-006/FR-008 preservados
  exatamente como a sessão anterior os deixou, para o verifier julgar.

## Dependencies

- 000-fundacao-visual mergeada (S0) — tokens do chip e `pulse-live`.
- v7-001 no ar (recorder publica RunEvents) — já entregue.
- T010–T013 antes de qualquer implementação; T020→T030; T040 depois de
  T020/T030; T052 depois de T051 e T040 (o harness mock cobre a ordem
  inversa no e2e local).
