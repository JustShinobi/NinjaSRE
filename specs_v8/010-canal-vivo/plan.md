# Implementation Plan: Canal vivo — o deployment empurra, o console para de perguntar

**Branch**: `010-canal-vivo` | **Date**: 2026-08-27 | **Spec**: [spec.md](spec.md)

## Summary

Um endpoint SSE novo de escopo deployment (`GET /v1/events/stream`) fan-outa
dez kinds de evento (quatro de run, dois de incidente, três de decisão, um de
controle) a partir de um broker em memória alimentado por três seams que já
existem: o caminho de publicação do `RunEventBroker`, o
`InteractionClosure.subscribe`, e um decorador de store composto no root. No
console, uma conexão nova em `console/src/live/deployment.ts` reutiliza a
mecânica de `connection.ts` e passa a ser o **gatilho** do
`router.refresh()`; o timer de `auto-refresh.tsx` vira fallback. O mecanismo
de render não muda nada — por isso a feature cabe num slot e não colide com a
030, que retrabalha as surfaces do run.

## Technical Context

**Language/Version**: Python 3.12 (gateway/platform), TypeScript/Next.js
(console) — os dois lados desta feature.
**Primary Dependencies**: FastAPI `StreamingResponse` (já usada em
`gateway/http/routes/investigations.py:242`), `EventSource` do browser via o
`StreamSource` injetável de `console/src/live/connection.ts:69`.
**Storage**: nenhum novo. O canal é deliberadamente não-durável (spec,
alegação 4); o que precisa de história já tem log próprio
(`RunTraceStore`).
**Testing**: pytest (contrato do endpoint, broker, taps), vitest
(deployment.ts, integração com o chip), Playwright acceptance
(`console/tests/e2e/canal-vivo.acceptance.spec.ts`).
**Target Platform**: staging k3s atrás de Traefik; compose no CT254.
**Performance Goals**: evento→refresh ≤ 5 s ponta a ponta; conexão viva
≥ 10 min atravessando o Traefik (SC-004).
**Constraints**: nenhum call site de gravação muda; single-write do S1
(i18n, routes.ts, screens.json) pertence à 030 — chaves novas vão no
relatório final.

## Constitution Check

*GATE: precisa passar antes da execução. Reconferir ao final.*

| Artigo | Como este plano satisfaz |
|---|---|
| I — Evidência sobre asserção | O evento carrega somente a identidade da mudança; estado e conclusão vêm das rotas de leitura. `resync`, cursor e falhas de conexão são observáveis no acceptance. |
| II — Autonomia limitada | A feature só publica fatos e atualiza leituras; não inicia, decide ou executa remediação. |
| III — Leitura por padrão | Não há escrita nova: broker, SSE e store cliente são leitura/entrega; a configuração de proxy é declarativa e revisada pelo operador. |
| IV — Segredo nunca chega ao agente | O runner de staging usa uma sessão opaca emitida pelo credential proxy. Nenhum segredo fica no processo do agente, prompt, argumento, filesystem ou trace; frames e logs carregam apenas IDs. |
| V — Um runtime canônico | Não toca o runtime de investigação nem produz avaliação. |
| VI — Neutralidade de provedor | Não importa SDK nem escolhe provedor; o canal é independente do LLM. |
| VII — Aprendizado é medido | Não altera aprendizado nem seus números. |
| VIII — Arquitetura em camadas | Broker fica em `platform`, rota em `gateway`, cliente em `console`; a composição ocorre no root do gateway e os contratos gerados permanecem na fronteira HTTP. |
| IX — Capacidades declaradas | Nenhuma capacidade de agente nova; o canal é infraestrutura de observação. |
| X — O operador é dono dos dados | Não há telemetry, analytics ou version check; o acceptance usa somente o staging do operador e não exporta dados. |
| XI — Datastore único | Não cria tabela nem acesso direto a banco; eventos de deployment são efêmeros e os fatos persistidos continuam nas portas existentes. |
| XII — Test-first, rastreado | Acceptance, contrato de payload, broker e cliente nascem vermelhos; cada vermelho, regeneração e resultado de staging entra no controle. |
| XIII — Idioma e atribuição | Código, paths e commits novos são em inglês; textos de UI entram em `en` e `pt-BR`; nenhum segredo ou identificador de planejamento é commitado. |
| XIV — Composto ou não foi entregue | O broker é construído no gateway servido, o cliente é composto pelo `AutoRefresh` e o evento efetivamente aciona `router.refresh()`; não existe mecanismo dormente. |

### Qual composition root constrói isto

O estado do gateway — o mesmo lugar que hoje constrói `state.broker`
(`RunEventBroker`) para a rota por run. Ali nascem:

1. `DeploymentEventBroker` (novo, `platform/runs/deployment.py`) — guardado
   em `state.deployment_events`.
2. O tap de runs: um wrapper do broker de runs que, após `publish`, traduz os
   quatro kinds filtrados e entrega ao broker de deployment.
3. A `InteractionSurface` de decisões, registrada via
   `InteractionClosure.subscribe` onde o closure é construído.
4. O decorador do store de incidentes, envolvendo o port na construção do
   unit-of-work do gateway.

Nenhum desses quatro existe fora do root; um teste estrutural (Phase 2)
falha se `DeploymentEventBroker` for instanciado em qualquer outro módulo de
produção.

### Complexity Tracking

Sem desvios da constituição. A escolha "não-durável + resync" está na spec
(alegação 4) e é a alternativa de MENOR complexidade — a rejeitada (log de
eventos de deployment) está em Out of Scope com a razão.

## Project Structure

### Documentation (this feature)

```
specs_v8/010-canal-vivo/
├── spec.md
├── plan.md
├── tasks.md
└── evidence/           # criado na execução; inclui visual/ (EXECUCAO.md §3)
```

### Source Code (repository root)

```
platform/runs/deployment.py          # NOVO: DeploymentEvent, DeploymentEventBroker, época+buffer
platform/runs/stream.py              # intocado (o broker por run não muda)
gateway/http/routes/events.py        # NOVO: GET /v1/events/stream
gateway/http/security/…              # declaração da rota nova na tabela do domínio
gateway/…(estado do gateway)         # composição dos 4 itens acima
config/constants/runs.py             # DEPLOYMENT_STREAM_BUFFER_EVENTS, SSE_KEEPALIVE_SECONDS
console/src/live/deployment.ts       # NOVO: conexão do canal (reusa connection.ts)
console/src/live/auto-refresh.tsx    # timer vira fallback; chip mapeia ConnectionState→Freshness
console/tests/unit/live/…            # deployment.test.ts, auto-refresh fallback
console/tests/e2e/canal-vivo.acceptance.spec.ts   # NOVO
tests/unit/platform/runs/…           # broker de deployment, época, resync
tests/contract/gateway/…             # contrato do endpoint (frames, cursor, keep-alive)
```

### Propriedade de escrita única

Esta feature NÃO edita `console/src/i18n/*.ts`, `console/src/shell/routes.ts`
nem `console/visual/screens.json` (dono no S1: 030). As chaves i18n novas do
rótulo de fallback do chip são declaradas no relatório final com texto en +
pt-BR. Também não edita `tokens.ts`/`icons.tsx` (congelados pós-000).

## Decisões de design

### 1. O canal transporta ids, nunca dados

Um frame diz "o run X mudou", não o estado do run X. O cliente nunca monta um
card rico a partir do payload: entrega o lote ao `AutoRefresh`, que agenda um
único `router.refresh()` e deixa as rotas de leitura reidratarem a tela. Isso
preserva "uma fonte por fato" (v7 decisão 3), mantém o canal não-durável e
define a ordem de reconciliação usada pelo Painel.

### 2. Época + sequência, e `resync` como confissão

`id: <epoch>:<sequence>` — `epoch` é um identificador gerado na construção do
broker (boot do processo). Reconexão com época corrente e sequência dentro do
buffer: entrega do que faltou. Qualquer outra combinação: `resync` como
primeiro frame. O cliente trata `resync` como "refresh e segue" — a lacuna
custa uma re-leitura, nunca silêncio.

### 3. O gatilho troca, o mecanismo fica

`AutoRefresh` já sabe re-renderizar a rota sem perder scroll nem estado
(`router.refresh()`, comentário em `auto-refresh.tsx:19-24`). A feature troca
o **quando** (timer → evento) e conserva o **como**. É o menor diff que
cumpre a decisão 3 da onda, e deixa a 050 construir os cards client-side por
cima do mesmo canal, não de outro.

### 4. Reuso da mecânica de conexão, não segunda implementação

`connection.ts` já resolve backoff, pausa por visibilidade, flush em lote e
teardown à prova de leak — com fakes injetáveis (`StreamSource`, `Scheduler`,
`Visibility`). `deployment.ts` parametriza essa mecânica para o endpoint de
deployment (a diferença real: sem run_id, cursor de época, callback de
`resync`). Se a generalização exigir tocar `connection.ts`, a mudança é
aditiva e coberta pelos testes de unidade existentes de `store.test.ts`.

### 5. Keep-alive de 15 s e a configuração do Traefik são a mesma decisão

O comentário SSE periódico existe para o proxy não matar a conexão ociosa; a
configuração do Traefik existe para o proxy não bufferizar nem cortar a
resposta longa. Os dois viajam juntos: a constante nomeada no código, o bloco
de manifesto na evidência, e o SC-004 mede o resultado no staging real — não
em compose local, onde o problema não se manifesta.

### 6. Acceptance dirige pela UI, como o operador

O teste da US1 inicia a investigação pelo modal (mesmo fluxo auditado em
2026-08-27) e observa o Painel noutra página. Sem `page.reload()`, sem POST
direto de API no caminho feliz — a régua é a experiência que falhou na
auditoria, não um atalho que a contorna.
