# Feature Specification: Painel vivo — o que está rodando aparece sozinho, e o que precisa de você se decide ali

**Feature Branch**: `feat/v8-050-painel-vivo`

**Created**: 2026-08-27

**Status**: Draft

**Input**: User description: "O Painel (`/`) vira o que `design/padrao-2026-08/Main.dc.html`
desenha: banda 'Em execução agora' com um card por run — título humano, barra
de 6 estágios, tempo decorrido — entrando por SSE sem reload; banda 'precisa
de você' com Aprovar/Recusar/Ver plano inline; KPIs com sparkline e fonte
nomeada; 'O que insiste em acontecer' com mini-linha do tempo de disparos por
assunto; 'Atividade ao vivo' como linha do tempo com formas de status. Nenhum
número sem dono, nenhum empty state sem próximo passo."

**Referência visual (DoD)**: `design/padrao-2026-08/Main.dc.html` (tema
escuro) e `design/padrao-2026-08/DashboardLight.dc.html` (tema claro) são
**normativos** — decisão 1 da onda: desvio não registrado em
`design/padrao-2026-08/DIVERGENCIAS.md` é defeito, mesmo que pareça melhoria.
O acceptance spec é `console/tests/e2e/painel-vivo.acceptance.spec.ts`,
confirmado **vermelho antes de qualquer implementação**. O fechamento do slot
inclui o gate visual de `specs_v8/EXECUCAO.md` §3: captura Orca browser de `/`
nos dois temas, comparada aos dois artboards, veredito em
`evidence/visual/VEREDITO.md`.

**Viewport normativo de medição**: 1440×1080 (a largura dos artboards).

**Evidência**: auditoria de 2026-08-27 pela UI (README da onda, "Evidências de
partida"): um run iniciado pela UI só apareceu no Painel após navegação; os
KPIs são texto com seta ("See the list behind this figure"); "Recent activity"
repete o mesmo incidente cinco vezes sem forma nem hierarquia; "Quick actions"
são dois links de texto; a aprovação pendente exige navegar até Decisions para
ser decidida — onde hoje ela está expirada e sem saída.

---

## Fatos verificados em 2026-08-27 (não re-derivar)

1. **O Painel é um Server Component que lê onze fontes em paralelo.**
   `DashboardScreen` (`console/src/surfaces/screens/dashboard.tsx:142`) faz
   `Promise.all` sobre `panelRead` de: `/v1/approvals`, `/v1/proposals`,
   `/v1/runs`, `/v1/estate/summary`, `/health/ready`, `/v1/detectors`, duas
   listas de `/v1/incidents` (`HUMAN_INCIDENT_QUERY` e `AGENT_INCIDENT_QUERY`,
   `dashboard.tsx:92-99`), mais bloqueados, retidos e checklist.
2. **A atualização é por timer, não por evento.** `AutoRefresh`
   (`console/src/live/auto-refresh.tsx:112`) chama `fetch('/api/reachable')` e
   `router.refresh()` num `setTimeout` (`:158`); a feature 010 desta onda
   entrega o canal SSE de deployment e o store cliente — esta feature **consome**,
   não cria o canal.
3. **A banda de atenção existe** — `AttentionBlock`
   (`console/src/surfaces/attention.tsx:64`), pesos em `ATTENTION_WEIGHT` e
   `oldestAttention` (`dashboard.tsx:128`) — mas é só navegação: nenhum controle
   de decisão nela.
4. **Aprovar e recusar já são rotas do gateway** (entregues na v7):
   `POST /v1/interactions/{interaction_id}/approve` e
   `POST /v1/interactions/{interaction_id}/reject`
   (`gateway/http/routes/interactions.py:108,124`). O reject **exige** razão
   (`RejectRequest.reason`, `min_length=1`, `:45`). Approve recusa interação
   que não é `approval` com 400 (`:116`).
5. **A lista de incidentes já carrega a chave de agrupamento.**
   `IncidentSummaryView` (`gateway/http/routes/incidents.py:64`) serve
   `correlation_key` ("what two firings of one cause share", `:86`),
   `public_id`, `title`, `severity`, `state`, `opened_at`, `self_resolved`,
   `subjects`. O que **não existe** é uma agregação por assunto com os
   instantes de cada disparo — a mini-linha do tempo não tem fonte hoje.
6. **Não existe endpoint de overview.** Cada figura do cabeçalho atual é
   computada no próprio `dashboard.tsx` a partir das listas; não há série
   histórica servida para nenhuma delas, e o estate não guarda fotografia
   diária de contagens.
7. **O título humano do run é da 020** (mesmo slot, lado backend): a listagem
   de runs passa a servir o título — objetivo digitado em run vivo, headline
   em run completado. Esta feature lê o campo servido; não deriva título.
8. **A fundação visual é da 000** (slot S0, já mergeada quando este slot
   abre): tokens, ícones, chip com contorno, formas de status e as primitivas
   de motion (`pulse-live`, `slide-in` 240ms, `shimmer`) existem em
   `console/src/design/` e ficam **congeladas** — um token novo que esta
   feature precise é declarado no relatório, nunca editado por ela.
9. **Esta feature é dona dos single-write no S3** (`console/src/i18n/*.ts`,
   `console/src/shell/routes.ts`, `console/visual/screens.json`); a par (020)
   é backend puro.

---

## Alegações normativas

Frases curtas, individualmente testáveis; o acceptance spec codifica cada uma.
As marcadas **[staging]** são staging-safe e rodam também contra
`https://stg-ninjasre.lan.kyo.ninja`. A marcada **[staging-write]** dispara
uma investigação e decide uma aprovação em propose-only — permitida pelo
protocolo da onda (EXECUCAO.md §4: um run pela UI por slot; decisão
propose-only não executa nada no estate).

- **AN-01** Uma investigação iniciada pela UI aparece como card na banda "Em
  execução agora" **sem reload da página** (nenhum `page.reload()` no teste, e
  o load inicial aconteceu antes do disparo). **[staging-write]**
- **AN-02** O card do run novo mostra como título o objetivo digitado, nunca
  "interactive investigation" nem um identificador hexadecimal.
  **[staging-write]**
- **AN-03** O card do run vivo mostra a barra de seis segmentos com o estágio
  corrente distinto dos concluídos e dos futuros. **[staging-write]**
- **AN-04** O card do run novo entra com a animação de chegada e ela não roda
  quando `prefers-reduced-motion: reduce`.
- **AN-05** Quando o run completa, o card sai da banda e a contagem "em voo"
  decresce, sem reload. **[staging-write]**
- **AN-06** A banda "precisa de você" mostra, para uma aprovação pendente, o
  resumo do plano (o que vai acontecer e a reversão) antes de qualquer botão
  ser clicável — nunca aprovação cega.
- **AN-07** Aprovar na banda fecha a aprovação e a banda reflete isso sem
  reload. **[staging-write]**
- **AN-08** Recusar na banda exige uma razão não vazia antes de submeter.
  **[staging-write]**
- **AN-09** Cada um dos cinco KPIs mostra o número, a sparkline e a legenda
  com a decomposição que o artboard desenha. **[staging]**
- **AN-10** Nenhum número do Painel diverge da fonte que o serve: a contagem
  de runs em voo é a de runs não terminados da listagem; a de aprovações é a
  da lista de aprovações. **[staging]**
- **AN-11** "O que insiste em acontecer" agrupa por assunto e mostra, por
  assunto, a mini-linha do tempo de disparos, a contagem `N×` e o chip de
  estado com forma. **[staging]**
- **AN-12** Nenhum assunto exibe identificador cru (`res-…`, hex ≥16) como
  subtítulo; o subtítulo nomeia recurso e nó. **[staging]**
- **AN-13** "Atividade ao vivo" é uma linha do tempo vertical onde cada
  entrada carrega a forma do seu tipo (losango investigação, círculo
  resolução, quadrado incidente, triângulo aprovação). **[staging]**
- **AN-14** Um evento novo do deployment insere entrada no topo da atividade
  sem reload. **[staging-write]**
- **AN-15** Com o stream caído, o chip de frescor da topbar diz que está em
  fallback, e o Painel continua servindo dados por leitura.
- **AN-16** Todo painel vazio do Painel diz o próximo passo com um link, nunca
  só "nada aqui".
- **AN-17** O Painel renderiza sem erro nos dois temas, com os tokens da
  fundação (nenhuma cor fora de `console/src/design/tokens.ts`). **[staging]**

## User Scenarios & Testing *(mandatory)*

### User Story 1 - O run que eu disparei aparece sozinho, com o meu objetivo como nome (Priority: P1)

Um operador dispara "Procurar anomalias no cluster Proxmox" pelo modal, volta
ao Painel — ou já estava nele — e o card do run entra sozinho na banda "Em
execução agora", deslizando para dentro, com o objetivo digitado como título e
a barra de estágios andando. Ele não aperta F5 em momento nenhum.

**Why this priority**: é a queixa literal do operador que originou a onda ("no
dashboard quando ele começa a investigar algo novo só aparece se eu atualizar
a página") e é o que integra as três features de que este slot depende (SSE da
010, título da 020, fundação da 000) numa única prova visível.

**Independent Test**: com o Painel aberto no staging, disparar uma
investigação pela UI e observar o card entrar sem reload, com o objetivo como
título e estágio corrente visível.

**Acceptance Scenarios**:

1. **Given** o Painel carregado e o stream conectado, **When** uma
   investigação é iniciada pela UI, **Then** um card entra na banda "Em
   execução agora" sem reload, com a animação de chegada.
2. **Given** esse card, **When** o título é lido, **Then** ele é o objetivo
   digitado, e nenhum identificador hexadecimal aparece nele.
3. **Given** esse card, **When** um estágio do run completa, **Then** o
   segmento correspondente da barra muda de estado sem reload.
4. **Given** esse card, **When** o run completa, **Then** o card sai da banda,
   a contagem "em voo" decresce e a atividade ganha a entrada de conclusão.
5. **Given** `prefers-reduced-motion: reduce`, **When** um card entra,
   **Then** ele aparece sem animação de deslocamento.

---

### User Story 2 - O que precisa de mim se decide onde eu estou (Priority: P1)

Uma remediação proposta aparece na banda "precisa de você" com o que vai
acontecer, a reversão, o risco e há quanto tempo espera — e os botões Aprovar,
Recusar e Ver plano ali mesmo. Aprovar fecha a pendência sem sair do Painel;
Recusar pede a razão; Ver plano abre o cartão completo em Decisões.

**Why this priority**: hoje decidir exige navegar a `/decisions`, onde a
proposta de exemplo está expirada e sem saída. A banda com decisão inline é o
segundo gancho de venda do artboard e usa rotas que já existem — o custo é de
console, o valor é de produto.

**Independent Test**: com uma aprovação pendente no staging (produzida pelo
run do cenário 1 ou semeada), aprovar pela banda e verificar o fechamento na
API sem reload.

**Acceptance Scenarios**:

1. **Given** uma aprovação pendente, **When** a banda renderiza, **Then** ela
   mostra título humano da ação, risco, idade da espera, o resumo do plano e a
   reversão — antes de qualquer clique.
2. **Given** a banda, **When** o operador clica Aprovar, **Then** a interação
   é fechada como aprovada e a banda reflete o fechamento sem reload.
3. **Given** a banda, **When** o operador clica Recusar, **Then** um campo de
   razão obrigatório aparece e o envio só acontece com razão não vazia.
4. **Given** a banda, **When** o operador clica "Ver plano →", **Then** a
   navegação termina no cartão daquela decisão em `/decisions`.
5. **Given** nenhuma pendência, **When** a banda renderiza, **Then** ela diz
   que nada espera decisão e aponta para o histórico em Decisões.

---

### User Story 3 - O que insiste em acontecer, com o tempo desenhado (Priority: P2)

O operador vê os assuntos recorrentes — RedisExporterDown, InstanceDown — cada
um com sua mini-linha do tempo de disparos nas últimas 48 h, a contagem, o
chip de estado com forma, e o subtítulo nomeando recurso e nó em vez de
`res-7a73b8aa…`.

**Why this priority**: o agrupamento por assunto já existe na lista; o que
falta é a dimensão temporal (a fonte da mini-linha) e o vocabulário humano do
subtítulo. É P2 porque depende da listagem existente e do módulo compartilhado
da 060, mas não de uma rota nova.

**Independent Test**: carregar o overview e a listagem de incidentes existente,
aplicar `groupBySubject` no cliente com janela de 48 h e conferir que o painel
desenha um strip por assunto com o mesmo número de disparos que a listagem
carrega.

**Acceptance Scenarios**:

1. **Given** incidentes reais agrupáveis por causa, **When** o painel
   renderiza, **Then** há uma linha por assunto com contagem `N×` igual ao
   número de disparos que a agregação devolve.
2. **Given** uma linha de assunto, **When** a mini-linha do tempo renderiza,
   **Then** ela desenha um marcador por disparo, posicionado pelo instante
   dele na janela.
3. **Given** uma linha de assunto em investigação, **When** o chip renderiza,
   **Then** ele carrega o losango; resolvido, o círculo.
4. **Given** uma linha de assunto, **When** o subtítulo renderiza, **Then**
   ele nomeia recurso e nó, e nenhum identificador cru aparece.
5. **Given** um assunto com investigação vinculada, **When** o operador clica
   nele, **Then** a navegação termina no incidente ou na investigação dele.

---

### User Story 4 - Cada número tem dono, e o dono tem história (Priority: P2)

Os cinco KPIs — Recursos vigiados, Degradados agora, Fechados sozinhos, Taxa
de sucesso, Tempo até a causa — mostram número, sparkline de 14 dias e a
decomposição, cada um lendo de uma fonte nomeada única.

**Why this priority**: decisão 3 da onda (uma fonte por fato, herdada da v7) e
o custo do overview: um endpoint que consolida o que hoje são onze leituras e
dá ao Painel a série que nenhuma lista carrega.

**Independent Test**: pedir o overview ao gateway e conferir que cada figura
do Painel é igual ao campo correspondente da resposta.

**Acceptance Scenarios**:

1. **Given** o overview servido, **When** os KPIs renderizam, **Then** cada
   número é o campo da resposta, sem recomputação divergente no cliente.
2. **Given** um KPI, **When** a sparkline renderiza, **Then** ela desenha um
   ponto por balde diário devolvido, na ordem temporal.
3. **Given** o deployment sem detector ligado, **When** o KPI de degradados
   renderiza, **Then** a legenda diz isso e aponta para a configuração de
   detectores.
4. **Given** a leitura do overview falhada, **When** os KPIs renderizam,
   **Then** eles dizem que não puderam ser lidos — nenhum zero inventado.

---

### User Story 5 - A atividade é uma narrativa ao vivo (Priority: P3)

A coluna "Atividade ao vivo" conta o que o deployment fez, em ordem, com a
forma de cada tipo — e cresce sozinha conforme os eventos chegam.

**Why this priority**: é a superfície que faz o produto parecer vivo o tempo
todo, mas depende só de composição sobre o que as outras histórias já provam.

**Acceptance Scenarios**:

1. **Given** o feed carregado, **When** cada entrada renderiza, **Then** ela
   carrega a forma do seu tipo e um instante relativo.
2. **Given** o stream conectado, **When** um evento chega, **Then** a entrada
   entra no topo sem reload, com a animação de chegada.
3. **Given** cinco disparos do mesmo assunto em sequência, **When** o feed
   renderiza, **Then** eles são uma entrada com contagem, não cinco linhas
   idênticas.

### Edge Cases

- **O stream cai no meio.** O store da 010 degrada para o fallback por timer;
  o chip de frescor diz "fallback"; nenhum card duplica quando o refresh
  seguinte traz o run que o SSE já tinha inserido — a reconciliação é por id
  do run, não por posição.
- **Evento SSE de um run que a leitura inicial ainda não viu** (corrida entre
  load e stream): o card entra pelo evento e a leitura seguinte não o
  duplica.
- **Aprovação decidida por outra pessoa enquanto a banda está aberta**: o
  clique em Aprovar recebe a interação já fechada; a banda mostra o desfecho
  ("decidida por X agora mesmo") em vez de erro.
- **Duas aprovações pendentes**: a banda mostra a mais antiga expandida e as
  demais como linhas compactas com contagem — o artboard desenha uma; a regra
  para N > 1 é esta.
- **Mais de seis runs em voo**: a banda mostra os seis mais recentes e o link
  "todas as investigações →" carrega a contagem total.
- **Janela sem disparos** em "o que insiste": o painel diz que nada se repetiu
  na janela e aponta para Incidentes.
- **Overview sem série ainda** (primeiro dia após o deploy, fotografia diária
  vazia): a sparkline desenha os baldes que existem; nenhum inventado.
- **`prefers-reduced-motion`**: todas as animações de chegada e shimmer são
  suprimidas; o conteúdo é idêntico.

## Requirements *(mandatory)*

### A banda "Em execução agora"

- **FR-001**: A banda DEVE mostrar um card por run não terminado, com título
  servido pela listagem de runs, gatilho (manual/alerta) e tempo decorrido.
- **FR-002**: O card DEVE desenhar a barra de seis segmentos com três estados
  distintos — concluído, corrente, futuro — derivados do `stage_index` que a
  020 serve na listagem (último estágio **completado**): concluídos são os
  segmentos ≤ `stage_index`, corrente é `stage_index + 1` quando esse valor
  ainda nomeia um segmento, futuros os demais; entre leituras, os eventos
  `stage_completed` do stream avançam o mesmo índice. Com `stage_index == 6`
  num run ainda não terminado os seis são concluídos e **não há corrente** —
  um segmento não pode carregar os dois estados. Ausência do campo significa
  nenhum estágio completado: os seis desenham futuro.
- **FR-003**: O segmento corrente DEVE carregar o shimmer da fundação; os
  demais, cor estática dos tokens.
- **FR-004**: Um run novo DEVE entrar na banda por evento do stream, sem
  reload, com a animação de chegada da fundação (240 ms) e realce de borda.
- **FR-005**: Um run que completa DEVE sair da banda por evento do stream, e
  as contagens do cabeçalho da banda DEVEM decrescer no mesmo movimento.
- **FR-006**: As três contagens do cabeçalho da banda (em voo, acompanhados,
  bloqueado em você) DEVEM nomear as fontes: runs não terminados da listagem,
  incidentes em estados de agente, itens de atenção — as mesmas listas que o
  Painel já lê, nunca uma recomputação paralela.
- **FR-007**: Nenhum card DEVE mostrar identificador hexadecimal como título;
  o ban transversal da 020 vale para esta banda.
- **FR-008**: A reconciliação entre leitura inicial e eventos DEVE ser por id
  de run: o mesmo run nunca vira dois cards.

### A banda "precisa de você"

- **FR-009**: A banda DEVE mostrar, por aprovação pendente: título humano da
  ação, risco (medidor de cinco posições), idade da espera, resumo do plano e
  da reversão — lidos dos campos estruturados que a 040 serve.
- **FR-010**: Aprovar DEVE chamar `POST /v1/interactions/{id}/approve` e
  refletir o fechamento sem reload.
- **FR-011**: Recusar DEVE exigir razão não vazia e chamar
  `POST /v1/interactions/{id}/reject` com ela.
- **FR-012**: "Ver plano →" DEVE terminar no cartão da decisão em
  `/decisions`.
- **FR-013**: Uma interação já fechada no momento do clique DEVE virar
  desfecho informativo, nunca erro.
- **FR-014**: Com mais de uma pendência, a mais antiga DEVE vir expandida e as
  demais compactas com contagem; com nenhuma, a banda DEVE dizer isso e
  apontar para o histórico.
- **FR-015**: Os botões DEVEM respeitar permissão: sem a permissão de decidir,
  a banda é informativa e diz por quê.

### KPIs e o overview

- **FR-016**: Um endpoint novo `GET /v1/overview` DEVE servir, num documento
  só: os cinco valores correntes, a decomposição de cada um (contagens por
  tipo de recurso; abertos sem detector; N de M; mediana e pior caso) e uma
  série de até `MAX_OVERVIEW_DAILY_BUCKETS` baldes diários por KPI, com o
  valor 14 declarado em `config/constants/estate.py`.
- **FR-017**: As séries de runs e incidentes DEVEM ser derivadas das tabelas
  existentes (`agent_runs`, `incidents`) por agregação diária.
- **FR-018**: A série de recursos vigiados DEVE vir de uma fotografia diária
  de contagens do estate, gravada uma vez por dia por organização pelo
  varredor que já existe — nunca recomputada retroativamente.
- **FR-019**: Cada KPI do Painel DEVE renderizar número, sparkline (um ponto
  por balde devolvido) e legenda de decomposição, lendo só do overview.
- **FR-020**: A falha de leitura do overview DEVE render um estado de leitura
  falhada por KPI — nenhum zero, nenhum traço mudo.
- **FR-021**: O KPI de degradados DEVE dizer, quando nenhum detector está
  ligado, que nada promove achado a incidente, com link para a configuração.

### "O que insiste em acontecer" e a agregação por assunto

- **FR-022**: A agregação por assunto DEVE vir do módulo compartilhado
  `groupBySubject` do console sobre a listagem de incidentes existente — a
  060 cravou (fato 1 da spec dela, com `file:line`) que cada grupo já carrega
  `firstAt`, `lastAt` e `occurrences[]` com instante e severidade por
  disparo. **Nenhum endpoint novo**: reconciliado pelo orquestrador em
  2026-08-27 pela regra "uma fonte por fato"; o Painel importa o mesmo módulo
  que `/incidents` usa e recorta a janela de 48 h no cliente.
- **FR-023**: O painel DEVE desenhar uma linha por assunto — as em estado
  ativo primeiro — com a mini-linha do tempo posicionando um marcador por
  disparo devolvido.
- **FR-024**: O subtítulo de assunto DEVE nomear recurso e nó; identificador
  interno aparece no máximo como tooltip, nunca como texto da linha.
- **FR-025**: A linha DEVE linkar para o incidente (forma pública) ou para a
  investigação vinculada quando houver.

### Atividade ao vivo

- **FR-026**: O feed DEVE compor entradas de investigações (iniciada, causa
  encontrada), incidentes (aberto, fechado sozinho) e decisões (proposta,
  decidida), cada tipo com sua forma, ordenadas por instante, limitadas às 8
  mais recentes.
- **FR-027**: Disparos consecutivos do mesmo assunto DEVEM colapsar numa
  entrada com contagem.
- **FR-028**: Um evento do stream DEVE inserir a entrada no topo sem reload,
  com a animação de chegada.

### Vivo, fallback e honestidade

- **FR-029**: O Painel DEVE consumir o store da 010; o `AutoRefresh` continua
  como fallback e o chip de frescor único da topbar diz em qual modo a página
  está.
- **FR-030**: Nenhum painel do Painel DEVE afirmar o negativo quando a leitura
  falhou; todo empty state genuíno DEVE dizer o próximo passo com link.
- **FR-031**: Toda cor, forma, raio e animação DEVEM vir da fundação da 000;
  esta feature não declara token novo — o que faltar é declarado no relatório
  para o orquestrador aplicar.

### Contrato, i18n e artefatos

- **FR-032**: O endpoint novo `GET /v1/overview` DEVE entrar na tabela de
  rotas com permissão declarada, no documento de API committed e no cliente TS
  regenerado.
- **FR-033**: O dataset simulado DEVE servir o overview e a listagem de
  incidentes com pelo menos três assuntos para a suíte determinística do
  console; não existe rota `/subjects`.
- **FR-034**: Toda string nova DEVE existir em `en` e `pt-BR` pelo catálogo.
- **FR-035**: `console/visual/screens.json` DEVE cobrir o Painel novo nos dois
  temas, com baselines recapturadas.

### Key Entities

- **Overview** — o documento que responde "como o ambiente está": cinco
  valores correntes com decomposição e série diária. Derivado; não é tabela
  nova, exceto a fotografia diária do estate.
- **Fotografia diária do estate** — uma linha por dia por organização com as
  contagens por tipo e por saúde; escrita pelo varredor existente na porta
  `EstateSnapshotStore`; a única memória nova que esta feature cria.
- **Assunto** — o agrupamento de incidentes pela chave de correlação, com os
  instantes dos disparos na janela. Agregação de leitura, sem escrita.
- **Card de run** — a projeção de um run não terminado: título, gatilho,
  estágio corrente (1–6), decorrido. Vive da listagem + eventos do stream.

## Success Criteria *(mandatory)*

- **SC-001**: No staging, com o Painel aberto e sem reload, uma investigação
  disparada pela UI aparece como card em até 3 s, com o objetivo digitado como
  título.
- **SC-002**: A barra de estágios do card muda de segmento durante o run, sem
  reload, e o card sai da banda quando o run completa.
- **SC-003**: Uma aprovação pendente é aprovada pela banda e
  `GET /v1/approvals` deixa de listá-la, sem reload da página.
- **SC-004**: Recusar sem razão é impossível pela UI; com razão, a interação
  fecha como rejeitada com a razão gravada.
- **SC-005**: Cada figura dos cinco KPIs é igual ao campo correspondente de
  `GET /v1/overview` no mesmo instante.
- **SC-006**: "O que insiste em acontecer" desenha, por assunto, o mesmo
  número de marcadores que `groupBySubject` devolve em `occurrences` para a
  janela de 48 h — e o número confere com `/incidents` para o mesmo assunto.
- **SC-007**: Nenhum texto visível do Painel casa `res-[0-9a-f]{8}` nem
  `[0-9a-f]{16,}`.
- **SC-008**: O gate visual da onda: capturas Orca de `/` nos dois temas com
  veredito CONFORME contra `Main.dc.html` e `DashboardLight.dc.html`, ou
  desvio registrado e aprovado — nenhum desvio silencioso.
- **SC-009**: O acceptance spec foi confirmado vermelho antes da
  implementação, com a mensagem real de cada alegação registrada.
- **SC-010**: `make verify` termina verde, tendo partido de verde.

## Consultas de evidência em staging

No banco `ninjasre-stg-db` (10.20.20.54), entram no DoD:

1. Concordância banda×banco: com o Painel aberto, o número de cards em "Em
   execução agora" é igual a
   `SELECT count(*) FROM agent_runs WHERE status NOT IN ('completed','failed','cancelled');`
2. Fotografia diária existe e é única:
   `SELECT org_id, snapshot_date, count(*) FROM estate_daily GROUP BY 1,2 HAVING count(*) > 1;`
   devolve 0 linhas.
3. Decisão inline gravada: após o SC-003/SC-004, a interação aparece fechada
   com `selected_option` respectivo na tabela de interações.

## Assumptions

- **A 010 entrega o canal e o store; a 020 entrega título e estágio na
  listagem; a 040 entrega os campos estruturados da aprovação.** Esta feature
  compõe as três no Painel — é o ponto declarado de integração do slot S3, e o
  acceptance dela é a prova de integração das outras.
- **A fotografia diária do estate é a única memória nova.** As demais séries
  derivam de tabelas existentes; recomputar contagens de estate para trás é
  impossível e a spec não finge o contrário — a série começa no dia do deploy.
- **Aprovação inline usa as rotas de interação existentes.** Nenhuma rota nova
  de decisão nasce aqui; o que a 040 mudar no shape, esta feature consome pelo
  cliente regenerado.
- **Os limites visuais (6 cards, 8 entradas, 5 assuntos + link) são os do
  artboard** e ficam como constantes nomeadas no código da tela.
- **Esta feature é a dona dos single-write no S3**; a par (020) é backend puro
  e não os toca.

## Dependencies

- **000-fundacao-visual** (S0): tokens, formas, chip, motion — congelados;
  esta feature só consome.
- **010-canal-vivo** (S1): o canal SSE e o store cliente; esta feature é a
  primeira consumidora completa.
- **040-decisoes-estruturadas** (S2): os campos estruturados da aprovação e o
  cartão em `/decisions` que "Ver plano" abre.
- **020-titulo-vivo** (par do slot): título e estágio na listagem de runs;
  interseção de arquivos nula — 020 é backend, esta é console + um endpoint
  de leitura novo (`overview`) que a 020 não toca; assuntos continuam sendo
  agrupados no cliente a partir da listagem existente.
- Bloqueia o **sweep final (S5)**: o Painel é a primeira tela do confronto
  visual da onda.

## Out of Scope

- **O modal de iniciar investigação** — feature 070; esta usa o botão
  existente da topbar no acceptance.
- **O cartão completo de decisão e o repropor** — 040; aqui só a banda e a
  navegação para lá.
- **A tela de run** — 030; o clique num card termina na rota do run, o que a
  rota mostra é da 030.
- **Alterar o mecanismo do canal SSE** — 010; esta feature consome o store e
  reporta lacunas, não o edita.
- **Séries históricas retroativas do estate** — a fotografia começa a existir
  no deploy desta feature; nenhum backfill inventado.
- **Qualquer edição em `console/src/design/`** — congelado pela 000; lacunas
  viram declaração no relatório.
