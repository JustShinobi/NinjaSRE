# Feature Specification: Iniciar investigação — o modal que começa do ambiente, não de um campo vazio

**Feature Branch**: `feat/v8-070-iniciar-investigacao`

**Created**: 2026-08-27

**Status**: Draft

**Input**: User description: "O fluxo de iniciar investigação precisa vender o
produto: modal central com foco, sugestões derivadas do estado real do
ambiente, atalho de teclado, e um rodapé que diz o que vai acontecer — time,
modelo, postura, estágios — lido do deployment, nunca hardcoded. O popover
atual é um campo vazio encostado na topbar."

**Referência visual (DoD)**: `design/padrao-2026-08/StartInvestigation.dc.html`
(tema escuro; o claro segue o mapa de tokens do padrão). O board é o contrato
— decisão 1 da onda: desvio não registrado em
`design/padrao-2026-08/DIVERGENCIAS.md` é defeito. O acceptance spec
`console/tests/e2e/iniciar-investigacao.acceptance.spec.ts` codifica as
alegações normativas abaixo, confirmado **vermelho antes de qualquer
implementação**.

**Viewport normativo de medição**: 1920×1080.

**Evidência**: auditoria de uso do staging em 2026-08-27 (fluxo executado pela
UI com o objetivo "Procure anomalias no cluster proxmos") e leitura de código
cravada abaixo.

---

## Fatos verificados em 2026-08-27 (não re-derivar)

1. **O controle atual é um drawer flutuante, não um modal.**
   `InvestigateDrawer` (`console/src/live/investigate.tsx:57`) renderiza
   dentro de `Drawer` (`console/src/components/overlay.tsx:205`,
   `FLOATING_DRAWER_CLASS_NAME`) — painel encostado no canto superior direito.
   No staging: título "Start an investigation", campo "What should be looked
   into?", botão "Start it" desabilitado até digitar, hint "An objective is
   what the investigation is about." Nada mais: sem sugestões, sem atalho
   declarado, sem contexto do que vai rodar.
2. **Quem o abre**: `Shell` (`console/src/shell/shell.tsx:293-302`) o
   renderiza com `open/locale/integrationsConfigured/runtimeComposed/onClose/
   navigate`; o gatilho é `onInvestigate` da `Topbar` (`shell.tsx:233-235`).
3. **O gating de setup já existe e é comportamento a preservar**:
   `ShellProps.setup` (`shell.tsx:67`) carrega `integrationsConfigured` (o
   drawer mostra um caveat quando nada está conectado) e `runtimeComposed`
   (desabilita iniciar quando o processo não tem runtime).
4. **A escrita passa por `act`** (`console/src/live/act.ts:26`) — o padrão de
   courier do console, porque a credencial é cookie HTTP-only que o browser
   não lê (mesmo padrão de `console/src/app/api/verify/route.ts`).
5. **O contrato de início é `POST /v1/investigations`** com corpo
   `{"objective": <texto>, "context": {<str:str>}}` — documentado por
   `ConsoleClient.start_investigation` (`surfaces/console/client.py:217-223`).
6. **O que acontece no gateway**: a rota chama `start_investigation`
   (`gateway/http/orchestration.py:29`): grava a identidade do run
   (`RunRecorder.start_run`), resolve o time — `scope.team_node_id` ou, vazio,
   o nó raiz da configuração (`orchestration.py:64-86`) — dispara `_drive` em
   background e devolve o `run_id`. O trigger de operador é `interactive`
   (observado no staging: `{"team_node_id": "default", "trigger":
   "interactive"}`).
7. **O destino pós-início é `/runs/<run_id>`** (observado:
   `/runs/0951c31e19e24c609e41b17d509f3205`).
8. **As matérias-primas das sugestões já são servidas**: a lista de incidentes
   agrupa por assunto com contagem de disparos (observado no staging: "17
   subjects · 50 firings", RedisExporterDown 8×, InstanceDown 8×,
   GatusEndpointHealthcheckFailed 6×; rota de incidentes em
   `gateway/http/routes/incidents.py`), e o estate conta saúde por recurso
   (observado: 99 vigiados · 14 unhealthy, os 14 contêineres com "visto há 3
   min"; serviço em `platform/estate/`). Nenhuma agregação nova de banco é
   necessária — a sugestão é uma leitura composta do que já se serve.
9. **O modelo que um run usa é fato do deployment**, não do console: o painel
   de custo do run real exibiu `gemini-flash-latest` vindo do registro do run.
   A postura ("só propõe") já chega ao shell (`ShellProps.guardian`; rodapé da
   sidebar "Guardian active · propose-only").

## Alegações normativas

Frases curtas, individualmente testáveis. O acceptance spec codifica cada uma;
as marcadas **[staging]** são staging-safe (leitura pura) e também rodam
contra `https://stg-ninjasre.lan.kyo.ninja`. A **AN-06** é a única escrita e é
o run-pela-UI que o slot S4 tem direito (EXECUCAO.md §4).

- **AN-01** O botão Investigar abre um modal centrado sobre um overlay que
  cobre a página inteira. **[staging]**
- **AN-02** Ao abrir, o foco está no campo de objetivo. **[staging]**
- **AN-03** Esc fecha o modal, clique no overlay fecha o modal, e o foco
  retorna ao botão Investigar. **[staging]**
- **AN-04** Com o campo vazio, o controle Investigar está desabilitado.
  **[staging]**
- **AN-05** O modal declara o atalho, e Ctrl+Enter com objetivo preenchido
  inicia a investigação.
- **AN-06** Iniciar navega para a página do run recém-criado. **[staging,
  a escrita única do slot]**
- **AN-07** Quando o deployment tem assunto recorrente nas últimas 24 horas, o
  modal oferece ao menos uma sugestão que o nomeia, com a contagem de
  disparos. **[staging]**
- **AN-08** Cada sugestão carrega a forma de status do seu tipo — quadrado
  para assunto crítico, círculo para leitura informativa — além da cor.
  **[staging]**
- **AN-09** Clicar numa sugestão preenche o campo de objetivo com a frase
  dela, e nada inicia sem confirmação. **[staging]**
- **AN-10** O rodapé nomeia o time, o modelo e a postura que o run vai usar,
  lidos do deployment. **[staging]**
- **AN-11** Nem time, nem modelo, nem postura, nem contagem de estágios
  existem como literais no código do console.
- **AN-12** Quando a leitura de sugestões falha, o modal abre com o campo
  utilizável e sem a seção de sugestões — investigar nunca fica refém da
  sugestão.
- **AN-13** Sem integração configurada, o caveat existente continua dito; sem
  runtime composto, iniciar continua desabilitado com a razão dita.
- **AN-14** O modal renderiza nos dois temas com os tokens do padrão.
  **[staging]**
- **AN-15** Com `prefers-reduced-motion`, o modal abre sem animação de
  entrada.
- **AN-16** Toda string nova do modal existe nas duas línguas e chega via o
  mecanismo de mensagens do console.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Investigar começa do que o ambiente está gritando (Priority: P1)

Um operador vê o Painel cheio de RedisExporterDown e aperta Investigar. O
modal que abre já oferece "Por que RedisExporterDown insiste em voltar? 8
disparos desde ontem". Ele clica na sugestão, o campo se preenche, Ctrl+Enter,
e ele está na página do run — que a partir da 020/030 mostra esse objetivo
como título.

**Why this priority**: é a diferença entre um formulário e um produto que se
vende. O popover atual pede que o operador saiba o que perguntar; o ambiente
já sabe o que está errado e o produto já serve esses dados — só não os oferece
no único lugar onde a pergunta nasce.

**Independent Test**: no staging, com os incidentes reais de lá, abrir o
modal e conferir que existe sugestão nomeando um assunto recorrente com a
contagem; clicar; conferir o campo preenchido; iniciar; conferir a navegação
para `/runs/<id>` de um run novo.

**Acceptance Scenarios**:

1. **Given** um deployment com assunto recorrente nas últimas 24h, **When** o
   operador abre o modal, **Then** uma sugestão nomeia o assunto e a contagem
   de disparos.
2. **Given** o modal aberto, **When** o operador clica numa sugestão, **Then**
   o campo de objetivo contém a frase da sugestão e nenhum run foi criado.
3. **Given** o campo preenchido, **When** o operador aperta Ctrl+Enter,
   **Then** um run é criado e a navegação termina na página dele.
4. **Given** o início a partir de uma sugestão, **When** o run é criado,
   **Then** o contexto do run registra de qual sugestão ele veio.

---

### User Story 2 - O modal diz o que vai acontecer antes de acontecer (Priority: P1)

Antes de apertar Investigar, o operador lê no rodapé: com que time o run vai
rodar, com que modelo, que a postura é só-propor, e que são 6 estágios
acompanháveis ao vivo. Nenhum desses fatos é decoração: cada um é lido do
deployment que vai executá-lo.

**Why this priority**: confiança se constrói antes do clique. Hoje o operador
descobre o modelo no painel de custo, o time em lugar nenhum, e a postura num
rodapé de sidebar — três lugares depois de já ter começado.

**Independent Test**: comparar o rodapé do modal no staging com as fontes: o
time resolvido pela mesma regra do gateway, o modelo configurado do runtime, a
postura do guardião. Mudar a configuração muda o rodapé sem tocar no console.

**Acceptance Scenarios**:

1. **Given** o modal aberto no staging, **When** o rodapé renderiza, **Then**
   ele nomeia time, modelo e postura não vazios.
2. **Given** o código do console, **When** se procura pelos valores do rodapé,
   **Then** nenhum existe como literal — todos chegam da resposta do
   deployment.
3. **Given** a leitura do rodapé falhada, **When** o modal renderiza, **Then**
   o rodapé mostra ausência declarada e o campo continua utilizável.

---

### User Story 3 - O modal é um modal (Priority: P2)

Foco no campo ao abrir, Esc fecha, clique fora fecha, foco de volta ao botão,
entrada animada de 240ms que respeita `prefers-reduced-motion`, tokens do
padrão nos dois temas.

**Why this priority**: é o que o board manda e o que o gate visual da onda
mede. P2 apenas porque US1/US2 carregam o valor novo; sem esta, porém, o slot
não fecha — a decisão 1 não admite entregar o desenho errado.

**Independent Test**: teclado e captura Orca nos dois temas contra o artboard.

**Acceptance Scenarios**:

1. **Given** qualquer tela do console, **When** Investigar é pressionado,
   **Then** o modal abre centrado com o foco no campo.
2. **Given** o modal aberto, **When** Esc é pressionado, **Then** ele fecha e
   o foco volta ao botão Investigar.
3. **Given** o sistema com `prefers-reduced-motion`, **When** o modal abre,
   **Then** não há transição de entrada.
4. **Given** os dois temas, **When** o modal é capturado, **Then** as capturas
   correspondem ao artboard nos tokens, tipografia, formas e geometria.

### Edge Cases

- **Deployment recém-instalado, sem incidente e sem estate.** Nenhuma
  sugestão se qualifica: a seção inteira ausente, o rótulo dela ausente, o
  campo no lugar. Um modal com seção vazia rotulada é pior que o popover
  atual.
- **A leitura de sugestões demora.** O modal nunca espera por ela para abrir:
  campo primeiro, sugestões chegam quando chegam. Sem spinner bloqueante.
- **Duplo Ctrl+Enter.** O segundo não cria segundo run: o controle desabilita
  no primeiro envio até a resposta.
- **Objetivo só de espaços.** Continua desabilitado — a regra atual do drawer
  (campo vazio) vale para vazio-efetivo.
- **Sugestão clicada e depois editada.** O texto editado é o que vai; o
  contexto de origem da sugestão só acompanha se o texto enviado ainda é o da
  sugestão.
- **`runtimeComposed=false` com sugestões presentes.** As sugestões aparecem
  (são leitura), mas iniciar está desabilitado com a razão — o gating de setup
  não é afrouxado pelo redesign.
- **Locale.** As frases de sugestão são compostas no console via i18n a partir
  de campos estruturados; a resposta do deployment não carrega prosa pronta em
  língua nenhuma.

## Requirements *(mandatory)*

### O modal e a abertura

- **FR-001**: O controle de iniciar investigação DEVE ser um modal centrado
  sobre overlay de página inteira, substituindo o drawer flutuante atual no
  mesmo ponto de composição do shell.
- **FR-002**: O overlay DEVE usar os valores do padrão: `rgba(6,10,8,.82)` no
  escuro e `rgba(23,33,29,.45)` no claro.
- **FR-003**: O contêiner DEVE ter 640px de largura, raio 16px, e a borda e
  sombra do artboard (escuro: borda `#2a5c44`, sombra `0 24px 64px
  rgba(0,0,0,.55)` mais anel `rgba(58,209,149,.12)`; claro: borda
  `#9fb0a8`, sombra `0 8px 24px rgba(17,22,28,.08)` e anel
  `rgba(10,116,82,.12)`.
- **FR-004**: Ao abrir, o foco DEVE estar no campo de objetivo; Esc e clique
  no overlay DEVEM fechar; ao fechar, o foco DEVE voltar ao controle
  Investigar da topbar.
- **FR-005**: A entrada DEVE animar 240ms ease-out conforme a primitiva de
  motion da fundação, e NÃO DEVE animar sob `prefers-reduced-motion`.
- **FR-006**: O campo DEVE mostrar a borda accent de 1.5px com halo `0 0 0 3px
  rgba(58,209,149,.12)` quando focado, e a linha de apoio "O objetivo diz do
  que a investigação trata — o agente decide o caminho." com o atalho
  declarado à direita.

### Sugestões derivadas do estado

- **FR-007**: O deployment DEVE servir `GET /v1/investigations/suggestions`
  devolvendo `{"suggestions": [...], "preamble": {...}}`.
- **FR-008**: Cada sugestão DEVE ser estruturada — no mínimo `kind`,
  `subject`, `severity`, `state`, `count_24h`, `resource` — e NÃO DEVE
  carregar prosa pronta.
- **FR-009**: Os tipos DEVEM ser exatamente três: `recurring_subject` (assunto
  de incidente com 2+ disparos nas últimas 24h, os 2 maiores por contagem),
  `unhealthy_batch` (um candidato para o grupo de 3+ recursos não saudáveis
  com maior contagem, desempate lexicográfico por nó e tipo) e `cluster_audit`
  (um candidato sempre que o estate conhece um cluster, nomeando-o).
- **FR-010**: As sugestões emitidas DEVEM ser no máximo 3, na ordem:
  recorrentes por contagem decrescente, depois lote não saudável, depois
  auditoria. Se houver 2 recorrentes + lote + auditoria, a lista trunca os
  últimos candidatos após o terceiro; a auditoria pode ser calculada mas não
  emitida por causa do limite. A regra de truncamento é determinística.
- **FR-011**: As sugestões DEVEM ser computadas das leituras que já existem
  (incidentes por assunto; saúde do estate) — nenhuma tabela ou coluna nova.
- **FR-012**: O console DEVE compor a frase de cada sugestão via i18n a partir
  dos campos estruturados, nas duas línguas.
- **FR-013**: Cada sugestão renderizada DEVE carregar a forma de status do seu
  tipo — quadrado na cor de perigo para assunto crítico recorrente e para lote
  não saudável, círculo na cor informativa para auditoria — e a seta de ação,
  como no artboard.
- **FR-014**: Clicar numa sugestão DEVE preencher o campo com a frase composta
  e NÃO DEVE iniciar nada.
- **FR-015**: Quando nenhuma sugestão se qualifica, a seção e o rótulo dela
  DEVEM estar ausentes.
- **FR-016**: Quando a leitura de sugestões falha ou demora, o modal DEVE
  abrir e funcionar sem a seção; a chegada tardia PODE inseri-la com o
  slide-in da fundação.
- **FR-017**: O console DEVE alcançar o endpoint por um courier próprio (o
  padrão de `console/src/app/api/`), porque a credencial é cookie HTTP-only.

### O rodapé factual

- **FR-018**: A resposta DEVE carregar `preamble` com `team_node_id`,
  `team_name`, `model`, `posture` e `stages`.
- **FR-019**: `team_name`/`team_node_id` DEVEM resolver pela mesma regra que o
  início do run usa — o time do escopo ou, vazio, o nó raiz da configuração —
  e o plano DEVE apontar os dois para a mesma função.
- **FR-020**: `model` DEVE ser o modelo que o runtime do investigador está
  configurado para usar; `posture` DEVE ser a postura de autonomia vigente;
  `stages` DEVE ser a contagem de estágios do pipeline, lida da definição
  dele.
- **FR-021**: O rodapé DEVE renderizar as duas linhas do artboard — "Vai rodar
  com o time … · … · só propõe" e "… estágios · você acompanha ao vivo, evento
  a evento" — com todos os valores vindos do `preamble`; nenhum DEVE existir
  como literal no console.
- **FR-022**: Com o `preamble` indisponível, o rodapé DEVE mostrar ausência
  declarada, nunca valores inventados, e iniciar DEVE continuar possível.

### Início e navegação

- **FR-023**: Iniciar DEVE continuar sendo `POST /v1/investigations` com
  `{"objective", "context"}` pelo courier existente — nenhuma rota de escrita
  nova.
- **FR-024**: Ctrl+Enter com objetivo não vazio DEVE iniciar; o controle DEVE
  desabilitar até a resposta; a navegação DEVE terminar na página do run
  criado.
- **FR-025**: Um início a partir de sugestão não editada DEVE enviar
  `context.origin = "suggestion:<kind>:<subject>"`; editado, o contexto de
  origem é omitido.
- **FR-026**: O caveat de integrações não configuradas e o desabilitado de
  runtime não composto DEVEM permanecer, com as mesmas fontes
  (`ShellProps.setup`).

### Strings, contrato e artefatos

- **FR-027**: Toda string nova DEVE existir em `en` e `pt-BR` e chegar via o
  mecanismo de mensagens; o artboard é a referência do pt-BR.
- **FR-028**: O documento de API committed DEVE ganhar o endpoint de
  sugestões; o cliente TS gerado DEVE ser regenerado; o dataset simulado DEVE
  servir sugestões e preamble para a suíte determinística.
- **FR-029**: O registro de telas visuais DEVE ganhar o estado "modal de
  investigar aberto", e as baselines DEVEM ser capturadas na imagem pinada.
- **FR-030**: O acceptance spec DEVE existir e ter sido confirmado vermelho
  antes de qualquer implementação, com a mensagem real de cada alegação
  registrada.

### Key Entities

- **Sugestão de investigação** — uma leitura composta do estado do
  deployment que vale uma pergunta: tipo, assunto, severidade, contagem,
  recurso. Efêmera, computada por pedido, nunca armazenada.
- **Preâmbulo do run** — os fatos que serão verdade do run que ainda não
  existe: time, modelo, postura, estágios. Lidos das mesmas fontes que o run
  usará, no momento do pedido.
- **Origem da sugestão** — o rastro `context.origin` que liga um run à
  sugestão que o pariu, para o registro do run dizer de onde a pergunta veio.

## Success Criteria *(mandatory)*

- **SC-001**: No staging, o modal aberto oferece sugestão nomeando um assunto
  recorrente real com contagem — verificado com os incidentes de lá.
- **SC-002**: Clicar, iniciar por Ctrl+Enter e chegar em `/runs/<id>` de um
  run novo, num único fluxo de teclado — o run único permitido ao slot.
- **SC-003**: O rodapé do modal no staging exibe time, modelo e postura não
  vazios, e uma busca por esses valores no código do console não os encontra
  como literais.
- **SC-004**: Captura Orca do modal nos dois temas com veredito CONFORME
  contra `StartInvestigation.dc.html` em
  `specs_v8/070-iniciar-investigacao/evidence/visual/VEREDITO.md`.
- **SC-005**: Com o mock sem sugestões, o modal abre sem a seção e o início
  funciona — provado na suíte determinística.
- **SC-006**: O acceptance spec foi confirmado vermelho antes da
  implementação, com as mensagens registradas.
- **SC-007**: `make verify` termina verde, tendo partido de verde.

## Assumptions

- **O endpoint de sugestões é leitura pura e barata.** Ele compõe leituras já
  servidas; se uma fonte estiver indisponível, ele responde com as que tem —
  parcial é melhor que 500, e o modal já degrada por FR-016.
- **A frase é do console, o fato é do deployment.** Composição de prosa é
  i18n; um deployment que servisse frases prontas escolheria uma língua no
  lugar do viewer.
- **O drawer atual morre.** Não há período de convivência: o modal o substitui
  no mesmo ponto do shell, e os testes do drawer são reescritos para o modal.
- **SSE não é pré-requisito funcional.** A dependência da 010 é de
  precedência de slot (S1 antes de S4); nada aqui lê o canal — a promessa "ao
  vivo" do rodapé é cumprida pelas 010/030/050, já entregues quando S4 roda.
- **Esta feature é a dona dos single-write no S4** (`console/src/i18n/*.ts`,
  `console/src/shell/routes.ts`, `console/visual/screens.json`); roda solo.
- **A fundação (000) já congelou tokens, ícones, formas e motion.** Qualquer
  token ou ícone que faltar é declarado no relatório e aplicado pelo
  orquestrador — nunca acrescentado por aqui (EXECUCAO.md §2).

## Dependencies

- **000-fundacao-visual**: tokens, tipografia, formas de status, primitiva de
  motion e o overlay/modal restyled que este modal usa. Precedência dura.
- **010-canal-vivo**: precedência de slot apenas; nenhum arquivo em comum.
- **020/030/050**: consomem o que este modal produz (o objetivo como título, o
  card no Painel); nada aqui depende delas.
- Bloqueia o sweep final (S5): o fluxo de demo da onda começa neste modal.

## Out of Scope

- **O título do run e a página do run** — 020 e 030.
- **O card aparecendo no Painel sem reload** — 050 assere isso.
- **Qualquer mudança no pipeline de estágios ou na postura de autonomia** — o
  rodapé lê, não define.
- **Sugestões persistidas, ranqueadas por modelo, ou "aprendidas"** — as três
  fontes são determinísticas; inteligência aqui é outra onda.
- **O atalho global de teclado para abrir o modal** (a topbar continua sendo o
  gatilho; a palette já cobre navegação por teclado).
