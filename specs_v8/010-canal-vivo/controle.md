# Controle — 010-canal-vivo

Documento de trabalho, atualizado incrementalmente a cada commit — ainda
NÃO é o relatório final de fechamento da feature (esse vem por cima deste
mesmo arquivo quando a implementação estiver completa). Um espelho idêntico
fica fora do repositório em
`/tmp/claude-999/-srv-workspaces-NinjaSRE/06510f59-f4a1-41e0-8b90-2554e9cacfc7/scratchpad/controle-010.md`,
atualizado junto — a rede de segurança caso este commit nunca aconteça.
Estado abaixo verificado contra o código no commit `0d189a9c`.

Última atualização: sessão em andamento, após o commit `0d189a9c`
("wip(gateway): declare the events route permission and wire the broker
into state").

## Commits feitos até agora

1. `835cf69c` — `feat(runs): add the deployment event broker and its two
   write-path taps`. `platform/runs/deployment.py` (broker, cursor,
   tradução de kinds de run), `platform/persistence/deployment_taps.py`
   (decoradores de incidente/decisão), quatro arquivos de teste.
2. `0d189a9c` — `wip(gateway): declare the events route permission and
   wire the broker into state`. `gateway/http/security/events_routes.py`
   (novo), `gateway/http/state.py` (campo `deployment_events` +
   `EVENTS_ROUTES` na tabela), `gateway/http/streaming/sse.py`
   (`deployment_sse_frame`).

**Ainda NÃO comitado / NÃO feito**: o handler da rota
(`gateway/http/routes/events.py`), o registro em `gateway/http/app.py`, e
o mais importante — `gateway/http/asgi.py` (`build_deployment`, linha
~239) ainda constrói `broker = RunEventBroker()` puro. O broker de
deployment e os decoradores de persistência EXISTEM mas **não estão
compostos no root ainda**. Isso é o próximo passo, literalmente onde a
sessão foi interrompida (estava adicionando `follow_deployment_events`
em `platform/runs/deployment.py` antes de escrever
`gateway/http/routes/events.py`).

## Ledger — requisito por requisito, com prova

Convenção de Estado: FEITO (com prova rodada) | PARCIAL | NÃO INICIADO.

| Item | Estado | Prova |
|---|---|---|
| FR-002 (forma do frame: scope/kind/sequence/occurred_at/payload, allowlist por scope) | FEITO | `platform/runs/deployment.py:132` (`DeploymentEvent.__post_init__`), vermelho provado cortando o allowlist à mão — ver abaixo |
| FR-003 (dez kinds exatos, quatro de run traduzidos, onze do enum retidos) | FEITO | `platform/runs/deployment.py:338` (`deployment_kind_of`), `tests/unit/platform/runs/test_deployment_run_tap.py` — vermelho provado vazando um 11º kind |
| FR-004 (epoch+sequência, resync em lacuna, buffer limitado) | FEITO | `platform/runs/deployment.py:234-323` (`DeploymentEventBroker.attach`/`_coverable`), vermelho provado desligando `_coverable` |
| FR-005 (tap de run sem mudar call site) | FEITO | `platform/runs/deployment.py:349` (`DeploymentPublishingRunEventBroker`) — mas **NÃO composto ainda** em `gateway/http/asgi.py` (ainda usa `RunEventBroker()` puro na linha 239). A classe existe e prova via teste que funciona; falta o root usá-la |
| FR-006 (decisão: proposed/decided do write path; expired idem; achado sobre closure não-composto) | PARCIAL | `platform/persistence/deployment_taps.py:85` (`_EventPublishingApprovalStore`). Achado registrado no docstring do módulo (linhas 16-25): `InteractionClosure`/`ClosurePublisher` não são construídos em nenhum lugar de produção (`rg -n "ClosurePublisher\(|InteractionClosure\(" --type=py` só retorna testes) — decisão de usar o mesmo mecanismo de decorador do FR-007 em vez de inventar uma instância. Gap nomeado: `interaction_id` nunca é populado (nenhuma aprovação in-run publica um). Falta compor no root |
| FR-007 (incidente: decorador no root, aberto/fechado) | PARCIAL | `platform/persistence/deployment_taps.py:45` (`_EventPublishingIncidentStore`), porta exata: `IncidentStore.upsert` (`platform/persistence/ports/incident_store.py:453`). Vermelho provado desligando a detecção de fechamento. Falta compor no root |
| FR-008 (cliente reusa StreamSource/backoff/visibilidade) | NÃO INICIADO | — |
| FR-009/010 (AutoRefresh integra o canal, mapeamento de 5→4 estados) | NÃO INICIADO | — |
| FR-011 (pulse-live) | NÃO INICIADO | depende do FR-010 |
| FR-012 (keep-alive por constante nomeada) | PARCIAL | constante `SSE_KEEPALIVE_SECONDS` existe (`config/constants/runs.py`), rota ainda não a usa |
| FR-013 (bloco Traefik) | NÃO INICIADO | bloco de manifesto ainda não redigido |
| FR-001 (o endpoint em si) | NÃO INICIADO | `gateway/http/routes/events.py` não existe ainda |
| T042 (mockplane) | NÃO INICIADO | |

## Vermelhos provados até agora (comando + primeira linha real da falha)

Nota honesta sobre ordem: `platform/runs/deployment.py` e
`platform/persistence/deployment_taps.py` foram desenhados e
implementados primeiro (o desenho tinha peças demais interligadas —
forma do cursor, allowlist, semântica de resync — para acertar em
vermelho-primeiro linha a linha sem um desenho prévio). Os testes foram
escritos na sequência, rodados verdes contra a implementação real, e
**depois** o vermelho foi provado cortando o mecanismo à mão e rodando de
novo — exatamente a exceção que a orientação do agente prevê para "a
ausência de um mecanismo é o defeito inteiro". Isso é uma correção
proposital ao processo estritamente vermelho-primeiro, registrada aqui em
vez de apresentada como se tivesse sido vermelho-primeiro.

1. Allowlist de payload por scope (`DeploymentEvent.__post_init__`)
   desligado à mão:
   ```
   .venv/bin/python -m pytest tests/unit/platform/runs/test_deployment_events.py -q
   ```
   Primeira falha real:
   `FAILED tests/unit/platform/runs/test_deployment_events.py::test_a_sensitive_field_never_crosses_the_channel[title] - Failed: DID NOT RAISE ValueError`
   (7 falharam de 18). Restaurado, verde de novo.

2. `_coverable` (decide resync vs. backlog) desligado à mão (sempre
   `True`):
   ```
   .venv/bin/python -m pytest tests/unit/platform/runs/test_deployment_broker.py -q
   ```
   Primeira falha real:
   `FAILED tests/unit/platform/runs/test_deployment_broker.py::test_a_gap_past_the_buffer_is_answered_with_exactly_one_resync - AssertionError: assert 256 == 1`
   Restaurado, verde de novo (11 passaram).

3. Detecção de fechamento de incidente
   (`_EventPublishingIncidentStore.upsert`) removida à mão:
   ```
   .venv/bin/python -m pytest tests/unit/platform/persistence/test_deployment_taps.py -q
   ```
   Primeira falha real:
   `FAILED tests/unit/platform/persistence/test_deployment_taps.py::test_closing_a_live_incident_publishes_closed - AssertionError: assert [] == [...]`
   Restaurado, verde de novo (8 passaram).

4. Um quinto kind (`CAPABILITY_CALLED`) vazado para dentro da tabela de
   tradução do tap de run:
   ```
   .venv/bin/python -m pytest tests/unit/platform/runs/test_deployment_run_tap.py -q
   ```
   Primeira falha real:
   `FAILED tests/unit/platform/runs/test_deployment_run_tap.py::test_every_other_kind_translates_to_nothing[capability_called] - AssertionError: assert <DeploymentEventKind.RUN_STARTED: 'run_started'> is None`
   (2 falharam de 20). Restaurado, verde de novo.

Suite completa dos quatro arquivos novos, verde, depois de cada restauração:
```
.venv/bin/python -m pytest tests/unit/platform/runs/test_deployment_broker.py tests/unit/platform/runs/test_deployment_events.py tests/unit/platform/runs/test_deployment_run_tap.py tests/unit/platform/persistence/test_deployment_taps.py -q
57 passed
```

Lint/tipo, nos módulos de produção novos:
```
.venv/bin/ruff check platform/runs/deployment.py platform/persistence/deployment_taps.py  → All checks passed!
.venv/bin/mypy platform/runs/deployment.py platform/persistence/deployment_taps.py  → Success: no issues found in 2 source files
```

## Decisões de design registradas (para citar no relatório final)

- **FR-006, achado**: `InteractionClosure`/`ClosurePublisher` não são
  instanciados em nenhum arquivo de produção — `rg -n
  "ClosurePublisher\(|InteractionClosure\(" --type=py` só bate em
  `tests/`. Não há instância única alcançável do root para assinar.
  Decisão: usar o MESMO mecanismo de decorador do FR-007
  (`with_deployment_events`, `platform/persistence/deployment_taps.py:185`)
  também para decisões, decorando `ApprovalStore.create_request` (→
  `decision_proposed`), `.decide` (→ `decision_decided`) e `.expire_due`
  (→ `decision_expired`) — a mesma porta que tanto `/v1/approvals`
  quanto `/v1/proposals` escrevem. Consequência nomeada: `interaction_id`
  no payload de decisão nunca é populado por esta feature — só
  `proposal_id`. Se uma aprovação in-run (interativa, levantada por
  `core.agent.interaction`) precisar aparecer no canal por
  `interaction_id`, é trabalho futuro, não coberto aqui.
- **Porta exata do incidente**: `IncidentStore.upsert`
  (`platform/persistence/ports/incident_store.py:453`) é o ÚNICO método
  de escrita tanto para abrir quanto para fechar (e para toda transição
  intermediária) — o decorador distingue abertura/fechamento comparando o
  que existia antes (`get(incident_id)`) com o que foi escrito depois,
  não pelo nome do método chamado.
- **Buffer do canal de deployment é memória curta, não durável** — 256
  eventos (`DEPLOYMENT_STREAM_BUFFER_EVENTS`, metade do
  `MAX_STREAM_BUFFER_EVENTS` de 512 por run), por decisão de projeto
  (alegação 4 da spec): perder um evento custa um `resync` + refresh,
  nunca um buraco.

## Próximos passos exatos (para retomar sem re-derivar)

1. Adicionar `follow_deployment_events` (gerador assíncrono de poll) em
   `platform/runs/deployment.py`, mesma cadência que
   `platform/runs/stream.py`'s `_POLL_SECONDS`.
2. Escrever `deployment_event_source`/`parse_deployment_cursor` em
   `gateway/http/streaming/subscription.py` (paralelo a `event_source`/
   `parse_cursor` que já existem lá para o stream por run).
3. Escrever `gateway/http/routes/events.py` (`GET /v1/events/stream`),
   registrar em `gateway/http/app.py`.
4. **O passo que falta e que é o mais importante**: em
   `gateway/http/asgi.py`, dentro de `build_deployment` (linha ~232-239):
   - `deployment_events = DeploymentEventBroker()`
   - `store = with_deployment_events(PostgresPersistence.from_url(...), deployment_events)`
   - `broker = DeploymentPublishingRunEventBroker(deployment_events=deployment_events)`
   - passar `deployment_events=deployment_events` para `GatewayState(...)`
5. Escrever `tests/contract/gateway/test_deployment_stream.py` +
   `tests/contract/gateway/conftest.py` (T011) — contrato do endpoint,
   laço de dez reconexões (prova do critério SC-003).
6. Teste estrutural T022 (broker só instanciado no root) —
   `tests/architecture/`.
7. mockplane (T042): `tools/mockplane/endpoints.py` (novo
   `ConsoleEndpoint` `deployment-stream`), `tools/mockplane/server.py`
   (`_serve_deployment_stream`, sessão-aware, publica um evento
   `run_started` sintético no `_apply_write` de `investigation-start`).
8. Cliente TS: `console/src/live/deployment.ts`,
   `console/src/live/auto-refresh.tsx` (integração), `console/src/app/api/events/route.ts`.
9. Acceptance spec `console/tests/e2e/canal-vivo.acceptance.spec.ts`.
10. Regenerar `fixtures/contract/openapi.json` (`python -m tools.mockplane
    contract`) e `console/src/api/schema.ts` (`make console-client`).
11. Bloco de manifesto Traefik (T061) — ainda não redigido.
12. Gates locais estreitos (T060).

## Chaves i18n a declarar no relatório final (dono S1 = 030, não editar)

Ainda não finalizadas — dependem de FR-010's mapeamento de estado. O rótulo
atual de `live.state.stale` ("Not updating" / "Sem atualizar") muda de
sentido para também cobrir "canal caído, timer cobrindo" (fallback). Duas
opções em aberto para o relatório final: (a) reescrever o VALOR da chave
existente `live.state.stale` para dizer "fallback" explicitamente, ou (b)
manter o texto atual se já for genérico o bastante. Decisão a fechar antes
do relatório final, com o texto exato em en e pt-BR.

## Bloco Traefik (T061) — placeholder, a preencher

Ainda não escrito. Vai precisar: `flushInterval` curto/sem buffering, e um
`ResponseHeaderTimeout`/`readTimeout` longo o bastante para `SC-004` (≥10
min sem queda), especificamente para `/v1/events/stream`. Mesma forma do
que já existe para `/v1/investigations/{run_id}/stream` no repositório
GitOps (não neste repositório) — a ser confirmado contra o que já está lá,
se algo já está, ou redigido do zero espelhando o SSE_KEEPALIVE_SECONDS=15
deste código.
