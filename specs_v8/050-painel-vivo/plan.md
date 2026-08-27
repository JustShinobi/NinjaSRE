# Implementation Plan: Painel vivo — o que está rodando aparece sozinho, e o que precisa de você se decide ali

**Branch**: `feat/v8-050-painel-vivo` | **Date**: 2026-08-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v8/050-painel-vivo/spec.md`

**Referência visual (DoD)**: `design/padrao-2026-08/Main.dc.html` e
`design/padrao-2026-08/DashboardLight.dc.html`, normativos (decisão 1 da
onda). Acceptance em `console/tests/e2e/painel-vivo.acceptance.spec.ts`,
vermelho antes da implementação. Viewport normativo: 1440×1080. Fechamento do
slot com o gate visual de `specs_v8/EXECUCAO.md` §3.

## Summary

O Painel deixa de ser onze leituras coladas por um timer e vira a projeção
viva do deployment, em cinco movimentos:

1. **Um endpoint de leitura novo** no gateway: `GET /v1/overview` (cinco
   KPIs com decomposição e série diária). O agrupamento por assunto NÃO ganha
   endpoint: vem do módulo `groupBySubject` do console sobre a listagem
   existente (reconciliado com a 060 — "uma fonte por fato"). Uma memória
   nova e só uma: a fotografia diária de contagens do estate.
2. **A banda "Em execução agora"**: cards de run com título (020), barra de
   seis estágios e tempo decorrido, inseridos/atualizados/removidos pelos
   eventos do store da 010 — reconciliados por id de run.
3. **A banda "precisa de você"** com Aprovar/Recusar/Ver-plano inline sobre as
   rotas de interação existentes (`gateway/http/routes/interactions.py:108,124`),
   com o resumo estruturado da 040 visível antes do clique e razão obrigatória
   no recusar.
4. **KPIs, assuntos e atividade** renderizados do endpoint novo e das rotas
   existentes, com
   sparkline SVG, mini-linha do tempo por assunto e feed colapsando disparos
   repetidos — formas de status e motion da fundação (000), nada declarado de
   novo.
5. **Honestidade de leitura**: falha de leitura vira estado dito; empty state
   diz o próximo passo; nenhuma recomputação paralela de um número que um
   endpoint já serve.

O que **não** muda: o canal SSE e o store (010), a derivação de título (020),
o shape da decisão (040), qualquer arquivo de `console/src/design/` (000,
congelado), e a tela de Decisões.

## Technical Context

**Language/Version**: TypeScript (console Next 16.3.0) e Python 3.12
(gateway, persistência)

**Primary Dependencies**:
`console/src/surfaces/screens/dashboard.tsx` (reescrita da composição),
`console/src/surfaces/attention.tsx` (banda de decisão inline),
`console/src/live/` (store da 010 — consumo, não edição),
`gateway/http/routes/` (módulo novo de overview; agregação em incidents),
`platform/estate/` (fotografia diária no varredor existente),
`platform/persistence/` (porta + repositório da fotografia; migração),
`platform/persistence/ports/estate_snapshot_store.py` (porta explícita da
fotografia) e `platform/persistence/ports/transaction.py` (propriedade
`estate_snapshots`),
`config/constants/estate.py` (`MAX_OVERVIEW_DAILY_BUCKETS = 14`),
`gateway/http/security/route_permissions.py` (uma rota declarada),
`fixtures/contract/openapi.json` e `console/src/api/schema.ts` (regenerados),
`console/src/i18n/en.ts`, `console/src/i18n/pt-BR.ts`,
`console/visual/screens.json` (dona no S3)

**Storage**: PostgreSQL. Uma tabela nova de fotografia diária do estate
(uma linha por organização por dia, contagens por tipo e por saúde), com
índice único `(org_id, snapshot_date)`, em migração reversível. Nenhuma outra
tabela; overview e assuntos são agregações de leitura sobre `agent_runs` e
`incidents`.

**Testing**: pytest (contrato do endpoint; propriedade da agregação por
assunto; fotografia idempotente por dia; migração ida-e-volta); vitest
(reconciliação por id de run; colapso de disparos no feed; razão obrigatória
no recusar; sparkline com N baldes); Playwright (acceptance das 17 alegações;
o fluxo staging-write usa o fixture único de run criado pela UI no slot S3);
suíte visual nos dois temas.

**Target Platform**: gateway Python + console web no k3s de staging
(`stg-ninjasre.lan.kyo.ninja`)

**Project Type**: integração de console — a feature que compõe 000+010+020+040
numa tela; backend restrito a um endpoint de leitura e uma fotografia

**Performance Goals**: o overview responde de agregações indexadas (janela
≤ `MAX_OVERVIEW_DAILY_BUCKETS` dias); o recorte de 48 h dos assuntos é feito no cliente sobre grupos já
carregados; nenhuma varredura sem índice em caminho de tela; o
Painel inicial continua um render de servidor único.

**Constraints**: `make verify` verde partindo de verde; migração reversível;
`console/src/design/` congelado (lacuna vira declaração no relatório);
interseção nula com a 020 (par do slot); os limites visuais do artboard como
constantes nomeadas.

**Scale/Scope**: um endpoint, uma porta, uma tabela, uma migração; uma tela
recomposta em cinco painéis; ~30 strings i18n novas ×2 línguas; 2 baselines
visuais novas.

## Constitution Check

*GATE: precisa passar antes da execução. Reconferir ao final.*

| Artigo | Como este plano satisfaz |
|---|---|
| I — Evidência sobre asserção | Cada número com fonte nomeada; leitura falhada dita, nunca zero inventado; o acceptance corre contra o staging real. |
| II — Autonomia limitada | Aprovar/recusar inline usa as rotas de interação existentes sob as mesmas permissões; nada executa sem pessoa. |
| III — Leitura por padrão | As escritas novas são: a fotografia diária (agregado de contagens, sem dado de terceiro) e a decisão que uma pessoa clicou. Todo o resto é leitura. |
| IV — Segredo nunca chega ao agente | Não toca credenciais nem proxy. |
| V — Um runtime canônico | Não toca o runtime nem produz avaliação. |
| VI — Neutralidade de provedor | Não toca SDK ou configuração de provedor. |
| VII — Aprendizado é medido | Não altera mecanismos de aprendizado. |
| VIII — Arquitetura em camadas | A agregação vive atrás das portas de persistência; o console fala com o gateway pelo cliente gerado; `check-imports` no fecho. |
| IX — Capacidades declaradas | Nenhuma capacidade nova de agente. |
| X — O operador é dono dos dados | A fotografia diária agrega contagens do próprio estate; a migração é reversível e o downgrade só derruba a tabela nova. |
| XI — Datastore único | `EstateSnapshotStore` em `platform/persistence/ports/estate_snapshot_store.py`, com fake e Postgres; nenhum SQL fora da persistência. |
| XII — Test-first | Acceptance e contratos vermelhos antes; caracterização da banda de atenção atual antes de recompô-la; efeito sobre cenários sintéticos medido ("sem efeito" esperado). |
| XIII — Idioma | Código e commits em inglês; UI pelo catálogo em `en` e `pt-BR`; nenhum identificador de planejamento em arquivo committed. |
| XIV — Composto ou não foi entregue | Ver abaixo. |

### Qual composition root constrói isto

- **O endpoint**: registrado no router do gateway e declarado em
  `RouteTable` (`gateway/http/security/route_permissions.py:98`) — a rota não
  declarada nem sobe (`UndeclaredRoute`, `:32`). O serving é o mesmo
  `GatewayState` que serve as rotas vizinhas.
- **A fotografia diária**: escrita somente pelo varredor de estate que já roda
  em produção (o caminho de `platform/estate/` acionado pelo tick de
  observação), através de `EstateSnapshotStore.record`. A tarefa nomeia o
  `file:line` do gancho ao aterrissar; se não houver ponto diário natural, a
  execução para e reporta, sem transformar uma leitura em escrita.
- **O consumo do Painel**: `DashboardScreen` é Server Component servido em
  `/`; o store da 010 é client component composto no mesmo screen. A prova de
  composição é o SC-001 no staging — o card entrando sem reload.

### Complexity Tracking

Uma tabela nova é o único acréscimo estrutural, e existe porque uma série
temporal de contagens não é derivável retroativamente. Em troca, o Painel
deixa de computar onze agregações no cliente e os números ganham dono único.

## Project Structure

### Documentation (this feature)

```text
specs_v8/050-painel-vivo/
├── spec.md
├── plan.md                    # este arquivo
├── tasks.md
├── controle.md                # do implementer, não deste plano
└── evidence/
    └── visual/                # capturas Orca dos dois temas + VEREDITO.md
```

### Source Code (repository root)

```text
gateway/http/routes/overview.py                  # novo: GET /v1/overview
gateway/http/security/…                          # a rota nova declarada
platform/estate/…                                # fotografia diária no varredor
platform/persistence/ports/estate_snapshot_store.py # EstateSnapshotStore + EstateDailySnapshot
platform/persistence/postgres/models.py          # tabela estate_daily
platform/persistence/postgres/repositories/…     # repositório da fotografia
platform/persistence/fakes/…                     # o mesmo, em memória
platform/persistence/migrations/versions/00XX_*  # tabela; reversível
fixtures/contract/openapi.json                   # regenerado
console/src/api/schema.ts                        # regenerado
console/src/surfaces/screens/dashboard.tsx       # a recomposição
console/src/surfaces/attention.tsx               # banda com decisão inline
console/src/surfaces/run-band.tsx                # novo: cards de run + barra de estágios
console/src/surfaces/kpi-tiles.tsx               # novo: KPI + sparkline
console/src/surfaces/subject-strip.tsx           # novo: mini-linha do tempo
console/src/surfaces/activity-feed.tsx           # novo: linha do tempo com formas
console/src/i18n/en.ts, pt-BR.ts                 # dona no S3
console/visual/screens.json                      # dona no S3
tests/contract/…                                 # overview, fotografia
tests/unit/platform/…                            # agregações e migração
console/tests/unit/…                             # reconciliação, colapso, recusa
console/tests/e2e/painel-vivo.acceptance.spec.ts # novo
```

**Structure Decision**: quatro componentes novos de superfície em vez de um
`dashboard.tsx` de mil linhas — o corte por componente é a regra de execução
da casa, e cada um corresponde a uma região nomeada do artboard.

### Propriedade de escrita única

Dona de `console/src/i18n/*.ts`, `console/src/shell/routes.ts` e
`console/visual/screens.json` no S3. `console/src/design/` é da 000 e está
congelado: lacuna de token/ícone vira declaração no relatório final.

## Decisões de design

### 1. `GET /v1/overview` é um documento, não cinco

Uma resposta com os cinco KPIs — cada um `{value, breakdown, series[]}`,
série de baldes diários `{date, value}` limitada a
`MAX_OVERVIEW_DAILY_BUCKETS` — porque o Painel
renderiza os cinco juntos e cinco endpoints seriam cinco chances de metade da
tela falhar. A decomposição é a legenda do artboard (por tipo de recurso;
"abertos sem detector"; "N de M"; "mediana · pior"). Runs e incidentes agregam
das tabelas que a v7 compôs; recursos vigiados lê da fotografia diária.

**Recusado**: séries retroativas de estate (inventáveis, não deriváveis);
estender `/v1/estate/summary` (mistura o corrente com o histórico e obriga o
console a compor de novo o que o endpoint existe para compor).

### 2. A fotografia diária é idempotente e mínima

`estate_daily(org_id, snapshot_date, counts_by_kind, counts_by_health)` com
único em `(org_id, snapshot_date)`; upsert — o primeiro gatilho do dia grava,
os demais confirmam. O único gatilho válido é o varredor de estate existente;
uma leitura do overview nunca escreve. `EstateSnapshotStore` expõe
`record(snapshot)` e `list_daily(org_id, since, until, limit)`; o limite usa
`MAX_OVERVIEW_DAILY_BUCKETS` em `config/constants/estate.py`.

### 3. Cards de run reconciliam por id, e o estado vem de um lugar

O render de servidor entrega a lista inicial; o store da 010 aplica
`run_started`/`stage_completed`/`run_completed`. A chave do card é o id do
run: evento de run já listado atualiza, não duplica; refresh de fallback que
traga um run já inserido pelo stream também não. O card lê título e estágio
dos campos servidos (020) — nenhuma derivação local de nome ou de estágio.

### 4. Aprovação inline mostra o plano antes do botão

A banda renderiza os campos estruturados da 040 (o que acontece, reversão,
risco, idade) e só então os controles. Aprovar → `POST
/v1/interactions/{id}/approve`; Recusar abre campo de razão obrigatório →
`…/reject` (o contrato exige `reason` não vazio — `interactions.py:45`);
interação já fechada vira desfecho informativo (o 400/404 do gateway é
traduzido, nunca vazado cru). Sem a permissão de decidir, a banda é
informativa e diz por quê — o mesmo gate de permissão que a tela de Decisões
usa.

### 5. Sparkline e mini-linha do tempo são SVG locais, dados do endpoint

Sparkline 90×28 (SPEC.md da fundação): polyline com um ponto por balde, cor
pelo token semântico do KPI. Mini-linha do tempo: strip 120×18, um marcador
por disparo posicionado por instante na janela, opacidade crescendo com a
recência (o desenho do artboard). Nenhuma biblioteca de gráfico: são vinte
linhas de SVG cada e a dependência nova custaria mais que ela paga.

### 6. O feed colapsa repetição no servidor de página, não no endpoint

O colapso de disparos consecutivos do mesmo assunto é regra de apresentação
(FEED_LENGTH=8 continua), então vive na composição da tela — o endpoint de
assuntos serve fatos, a tela decide narrativa. A regra é caracterizada por
teste de unidade com o caso real da auditoria (5× DNSResolverProbeFailed).

### 7. Acceptance-primeiro, e o vermelho é registrado

As 17 alegações aterrissam no acceptance antes de qualquer implementação; as
staging-write consomem o run único do slot S3, criado pela UI pela tarefa
T034 (o modal existente antes da 070; o teste usa o controle da topbar pelo
test-id atual). Linha de base:
`make verify` verde registrado fora do repositório antes da primeira escrita.
