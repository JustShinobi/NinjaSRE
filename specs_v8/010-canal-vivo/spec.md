# Feature Specification: Canal vivo — o deployment empurra, o console para de perguntar

**Feature Branch**: `010-canal-vivo`

**Created**: 2026-08-27

**Status**: Draft

**Input**: specs_v8 decisão 3 (vivo é push, não polling) + board normativo `design/padrao-2026-08/` (chip "Ao vivo" pulsando em `Main.dc.html`, nota "PAINEL — o que muda": "Tudo chega por SSE: run novo desliza pra dentro (sem F5, sem auto-refresh por timer)").

## Fatos verificados em 2026-08-27 (não re-derivar)

- O produto **já serve SSE por run**: `GET /v1/investigations/{run_id}/stream`
  (`gateway/http/routes/investigations.py:242`, `stream_investigation`) —
  `StreamingResponse` com `media_type="text/event-stream"`, headers
  `Cache-Control: no-cache` e `X-Accel-Buffering: no`, retomada por header
  `Last-Event-ID` via `parse_cursor`, auth por `Depends(authorized)` +
  visibilidade do run.
- O fan-out em processo existe e é run-escopado: `RunEventBroker`
  (`platform/runs/stream.py:148`) com `attach(run_id)`, `publish`, `deliver`,
  ponte entre réplicas via `StreamBridge` (`platform/runs/stream.py:66`), e
  catch-up-then-live via `RunStream` (`platform/runs/stream.py:217`) lendo
  `RunTraceStore.events_for_run`. O broker vive no estado do gateway
  (`state.broker` na rota acima).
- Os tipos de evento são um enum fechado: `TraceEventKind`
  (`platform/runs/events.py:25`) — entre eles `RUN_STARTED`,
  `STAGE_COMPLETED`, `ATTENTION_CHANGED`, `APPROVAL_REQUESTED`,
  `RUN_FINISHED`.
- O cliente por run existe em `console/src/live/`: `connection.ts`
  (`RunConnection`, estados `ConnectionState`, backoff, pausa por
  visibilidade), `sse.ts`, `cursor.ts`, `store.ts` (`RunStore.subscribe`,
  `console/src/live/store.ts:75`), `use-run.ts`.
- O que mantém as **listas e o Painel** atuais é um timer:
  `console/src/live/auto-refresh.tsx:112` (`AutoRefresh`) sonda
  `/api/reachable` e chama `router.refresh()`; o chip de frescor renderiza os
  quatro estados de `Freshness` (`console/src/live/freshness.ts:49`:
  `live | refreshing | stale | paused`). Auditado no staging em 2026-08-27:
  um run iniciado só apareceu no Painel após navegação manual.
- Fechamentos de interação já têm um publicador com assinantes:
  `InteractionClosure.subscribe(surface)`
  (`core/agent/interaction/closure.py:154`) entrega `present` e `closed` a
  cada `InteractionSurface` registrada.
- O badge da sidebar e a banda do dashboard leem `ProposalCount.pending`
  (`gateway/http/routes/proposals.py:96`).
- O chart neste repositório é um stub (`chart/Chart.yaml` apenas); o ingress
  do staging (Traefik, k3s) vive no repositório GitOps que o
  `make deploy-stg` (Makefile:617) publica via Argo. A rota SSE por run já
  atravessa esse Traefik hoje — com o indicador do transcript oscilando para
  "Reconnecting" no staging (observado 2026-08-27).

## Alegações normativas

1. **Um canal, escopo deployment.** Existe exatamente um endpoint novo,
   `GET /v1/events/stream`, servindo `text/event-stream` com os mesmos
   headers anti-buffering da rota por run. Ele carrega o que as páginas de
   lista precisam saber que mudou: runs (começou, completou estágio, pediu
   atenção, terminou), incidentes (aberto, fechado) e decisões (proposta,
   expirada, decidida).
2. **Push substitui o timer como gatilho; o mecanismo de render não muda.**
   Nesta feature, o evento que chega dispara o mesmo `router.refresh()` que o
   timer disparava — os Server Components continuam a única fonte do HTML. O
   timer não morre: vira fallback declarado, ativo somente enquanto o canal
   está caído. (Os cards que deslizam sem refresh são da 050, sobre este
   canal.)
3. **O chip diz a verdade nova.** O chip único de frescor por página passa a
   distinguir: stream entregando (`live`, com o pulso do board), stream caído
   com timer cobrindo (`stale`, rotulado como fallback), pausado por aba
   oculta (`paused`). Nunca um chip por painel.
4. **Perder eventos é sobrevivível e explícito.** O canal não ganha um log
   durável próprio: numa lacuna de retomada o servidor manda um evento de
   controle `resync` e o cliente faz um `router.refresh()` — os dados nunca
   vêm do canal, então a lacuna custa um refresh, não um buraco.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - O run novo aparece sem F5 (Priority: P1)

Um operador está com o Painel aberto. Outra pessoa (ou um alerta) inicia uma
investigação. O card do run aparece na tela do operador sem reload e sem
clique, em segundos.

**Why this priority**: é a reclamação literal do operador que originou a onda
("no dashboard quando ele começa a investigar algo novo só aparece se eu
atualizar a página").

**Independent Test**: Playwright abre `/` autenticado, dispara
`POST /v1/investigations` **pela UI de outra página** (o modal Investigar), e
assere o card novo na primeira página **sem** `page.reload()` e sem navegação
de documento.

**Acceptance Scenarios**:

1. **Given** o Painel aberto com o canal conectado, **When** um run começa,
   **Then** o card do run aparece em ≤ 5 s sem reload e o chip permanece
   `live`.
2. **Given** o Painel aberto, **When** um run termina, **Then** a linha some
   de "em execução" e a contagem de runs em voo decai, sem reload.

### User Story 2 - O canal cai e o console não mente (Priority: P1)

O Traefik derruba a conexão (deploy, timeout, rede). O console reconecta com
backoff; enquanto não consegue, o timer antigo cobre e o chip diz que está em
fallback — nunca `live`.

**Why this priority**: o indicador que mente é pior que o polling; o stream
por run já oscila para "Reconnecting" no staging hoje.

**Independent Test**: bloquear a rota `/v1/events/stream` no teste (route
interception), observar o chip sair de `live`, o timer reassumir, e dados
continuarem atualizando na cadência do fallback.

**Acceptance Scenarios**:

1. **Given** o canal conectado, **When** a rota passa a responder 502,
   **Then** o chip muda para o estado de fallback em ≤ 30 s e o
   `router.refresh()` por timer volta a acontecer.
2. **Given** o fallback ativo, **When** a rota volta, **Then** o cliente
   reconecta sozinho e o chip volta a `live`.

### User Story 3 - Reconectar não duplica nem perde (Priority: P2)

Uma reconexão apresenta `Last-Event-ID`; eventos já vistos não reprocessam;
uma lacuna real produz `resync` e um refresh único.

**Independent Test**: teste de contrato do endpoint com um cliente que
desconecta e volta com o cursor; asserção de não-duplicação e do evento
`resync` quando o cursor é de outra época do broker.

**Acceptance Scenarios**:

1. **Given** um cliente com cursor válido, **When** reconecta, **Then**
   recebe apenas eventos posteriores ao cursor.
2. **Given** um cursor de uma época anterior do processo, **When** reconecta,
   **Then** recebe `resync` como primeiro evento e segue vivo dali.

### Edge Cases

- Aba oculta: a conexão pausa como `RunConnection` já pausa (visibilidade), e
  reconecta ao voltar — sem acumular buffer de aba morta.
- Duas abas do mesmo operador: duas conexões independentes; o limite de
  assinantes é por processo e a spec não promete coalescing.
- Deploy do gateway no meio: época nova do broker → `resync` → um refresh.
- Permissão: um principal sem leitura de runs não abre o canal (403 na
  tabela de rotas), e o console não tenta reabrir em loop contra 403.

## Requirements *(mandatory)*

### O endpoint

- **FR-001**: `GET /v1/events/stream` existe em
  `gateway/http/routes/events.py` (módulo novo), declarado na tabela de
  rotas com a mesma permissão que hoje guarda `GET /v1/runs`, servindo
  `text/event-stream` com `Cache-Control: no-cache` e
  `X-Accel-Buffering: no` — os mesmos headers de
  `gateway/http/routes/investigations.py:266-268`.
- **FR-002**: cada frame carrega um JSON `{"scope": "run"|"incident"|
  "decision"|"control", "kind": <nome literal>, "sequence": <int>,
  "occurred_at": <ISO>, "payload": {...}}` e um `id:` no formato
  `<epoch>:<sequence>`, onde `epoch` identifica a vida do broker no processo.
  O payload é uma allowlist fechada: run `{run_id}`, incidente
  `{incident_id}`, decisão `{proposal_id, interaction_id}` somente com os IDs
  conhecidos, e controle `resync` `{}`; nenhum outro campo atravessa o canal.
- **FR-003**: os kinds servidos são exatamente:
  `run_started`, `stage_completed`, `attention_changed`, `run_finished`
  (traduzidos de `TraceEventKind`, filtrados — os demais kinds do enum não
  atravessam o canal), `incident_opened`, `incident_closed`,
  `decision_proposed`, `decision_expired`, `decision_decided`, e o de
  controle `resync`. Payload de run carrega `run_id`; de incidente,
  `incident_id`; de decisão, `proposal_id`/`interaction_id` — ids apenas, os
  dados continuam vindo das rotas de leitura.
- **FR-004**: `Last-Event-ID` com `epoch` corrente ⇒ entrega do buffer em
  memória a partir de `sequence`; `epoch` diferente ou lacuna além do buffer
  ⇒ primeiro frame é `resync`. O buffer é limitado por constante nova em
  `config/constants/runs.py` (irmã de `MAX_STREAM_BUFFER_EVENTS`).

### As fontes que publicam

- **FR-005**: eventos de run nascem de um tap no caminho que já publica no
  `RunEventBroker` — composto no mesmo lugar do estado do gateway que constrói
  `state.broker`, filtrando os quatro kinds de FR-003. Nenhum call site de
  gravação muda.
- **FR-006**: eventos de decisão nascem de uma `InteractionSurface` registrada
  via `InteractionClosure.subscribe` (`core/agent/interaction/closure.py:154`)
  para expiração/decisão, e do caminho de escrita de propostas para
  `decision_proposed` — decorado na composition root, não nos handlers.
- **FR-007**: eventos de incidente nascem de um decorador do store de
  incidentes na composition root do gateway, nos writes de abertura e
  fechamento. (A tarefa de implementação localiza o port exato e o registra
  no controle; o mecanismo — decorador no root, jamais espalhado por call
  sites — é normativo.)

### O cliente

- **FR-008**: `console/src/live/deployment.ts` (novo) implementa a conexão do
  canal reutilizando `StreamSource`, o backoff e a pausa por visibilidade de
  `connection.ts` — não uma segunda implementação de reconexão.
- **FR-009**: com o canal entregando, o timer de `AutoRefresh` fica suspenso e
  cada evento (ou lote em ≤ 250 ms) dispara `router.refresh()`; com o canal
  caído, o timer atual volta exatamente como está escrito hoje
  (`delayAfter(failures)`); `resync` dispara um refresh imediato.
- **FR-010**: o chip único (`auto-refresh.tsx`) mapeia: conectado→`live`,
  reconectando→`refreshing`, caído-com-timer→`stale`, aba oculta→`paused` —
  os quatro `Freshness` existentes, sem estado novo; o rótulo do estado
  `stale` passa a dizer fallback. Chaves i18n novas são declaradas no
  relatório (dono dos arquivos i18n no S1 é a 030).
- **FR-011**: o pulso visual do estado `live` é o `pulse-live` da fundação
  (000) — o chip do board em `Main.dc.html`, tema escuro e claro.

### Operação

- **FR-012**: a rota nova envia keep-alive (comentário SSE) a cada 15 s para
  atravessar idle-timeouts de proxy; o valor é constante nomeada, não literal.
- **FR-013**: o ingress do staging ganha, no repositório GitOps, a
  configuração Traefik da rota `/v1/events/stream` (flush imediato e timeout
  de resposta longo). O bloco exato de manifesto é entregue como evidência da
  feature e aplicado pelo operador no ciclo `make deploy-stg`; validação é o
  acceptance rodando contra o staging real.

## Success Criteria *(mandatory)*

- **SC-001**: com o Painel aberto e o canal saudável, um run iniciado em outra
  sessão aparece em ≤ 5 s, com **zero** reloads de documento (asserido por
  Playwright sem `page.reload()` e sem navegação).
- **SC-002**: derrubar a rota do canal não congela nada: o chip reporta
  fallback em ≤ 30 s e o conteúdo continua avançando na cadência do timer.
- **SC-003**: em 10 ciclos de desconexão/reconexão de contrato, nenhum evento
  duplicado atravessa (`sequence` estritamente crescente por época no
  cliente) e toda lacuna produz exatamente um `resync`.
- **SC-004**: no staging real, atravessando o Traefik, uma conexão do canal
  vive ≥ 10 min sem queda com keep-alive — medido no acceptance @staging.

## Consultas de evidência em staging

- Run iniciado pela UI durante o acceptance: presença do card no Painel sem
  reload (screenshot antes/depois + trace do Playwright sem navegação).
- `curl -N https://stg-ninjasre.lan.kyo.ninja/v1/events/stream` autenticado:
  frames de keep-alive a cada 15 s; um `run_started` durante um run real.
- Gate visual (EXECUCAO.md §3): chip "Ao vivo" pulsando, dois temas, contra
  `Main.dc.html`.

## Assumptions

- A 000 (fundação) já entregou `pulse-live` e os tokens do chip; este slot
  (S1) roda depois do S0.
- O buffer em memória por processo é suficiente: perda de evento custa um
  `resync` + refresh, nunca dado errado — aceito e declarado na alegação 4.
- Réplica única do gateway no staging hoje; o desenho já acomoda múltiplas
  via `StreamBridge`, mas provar isso fica fora desta feature.

## Dependencies

- 000-fundacao-visual (tokens do chip, keyframes `pulse-live`).
- v7-001 (recorder composto publica os RunEvents que o tap filtra).

## Out of Scope

- Cards deslizando por estado de cliente sem refresh (050-painel-vivo).
- Estágio corrente na listagem de runs (020-titulo-vivo).
- Canal durável/replay histórico do deployment (o log por run já existe; um
  log de deployment não se justifica enquanto o custo de uma lacuna é um
  refresh).
- Notificações push/browser.
