# Feature Specification: Decisões estruturadas — o cartão no lugar do JSON, e a expirada com saída

**Feature Branch**: `feat/v8-040-decisoes-estruturadas`

**Created**: 2026-08-27

**Status**: Draft

**Input**: User description: "Em /decisions temos uma coisa horrorosa. O
documento inteiro da ação é impresso como texto no campo Target. A proposta
expirada manda 'pedir de novo' sem nenhum controle para isso. O badge da
sidebar conta uma decisão que não aceita mais decisão. O board é definitivo:
cartão por campo, medidor de risco, evidência com fonte, reversão visível,
'Propor de novo, agora' na expirada, histórico de decididas."

**Referência visual (DoD)**: `design/padrao-2026-08/Decisions.dc.html` (tema
escuro) e `design/padrao-2026-08/DecisionsLight.dc.html` (claro) são
**normativos** — decisão 1 da onda: desvio não registrado em
`design/padrao-2026-08/DIVERGENCIAS.md` é defeito. O acceptance spec
`console/tests/e2e/decisoes-estruturadas.acceptance.spec.ts` codifica as
alegações normativas abaixo, confirmado **vermelho antes de qualquer
implementação**. O gate visual da onda (EXECUCAO.md §3) compara a tela servida
no staging com os dois artboards, nos dois temas.

**Viewport normativo de medição**: 1440×1040 — o frame do artboard.

**Evidência**: auditoria de 2026-08-27 pela UI do staging (Orca browser),
seção "Evidências de partida" do README da onda; fatos cravados abaixo.

---

## Fatos verificados em 2026-08-27 (não re-derivar)

1. **A tela imprime o documento da ação como texto.** O campo "Target" de
   `/decisions` carrega ~40 linhas de JSON serializado, começando em
   `path = proxmox_start_guest · state = pending · target = pve01 · current =
   {"lock":"", ...}`. Nenhum campo é renderizado individualmente.
2. **O documento já é estruturado.** O payload observado no staging carrega,
   com estes nomes: `proposed.steps[]` (cada passo com `description`,
   `capability`, `arguments`), `intent`, `rollback[]` (passos com
   `description`), `evidence[]` (itens com `summary` e `reference` —
   ex.: `alertmanager:incident_timeline:res-7a73…`, `proxmox:quorum:HAL9000`),
   `blast_radius` (`count`, `depth`, `known`, `origin`, `services`,
   `truncated`), `risk_class` (`"low"`), `reversible` (`true`),
   `side_effect_level` (`"write_reversible"`), `requester`
   (`"alert-router"`), `capability` (`"proxmox_start_guest"`), `run_id`,
   `action_id`, `plan_id`, `summary`, `created_at`,
   `prior_effectiveness` (`known`, `total`, `counts`, `last_at`, `summary`),
   `recorded_state`, `sub_targets` (`["lxc/122"]`). A tela não precisa de
   dado novo — precisa que o dado que existe seja servido por campo.
3. **A expirada é um beco sem saída.** O rodapé do cartão diz, verbatim: "The
   window for answering this closed, and the deployment refuses a decision
   taken after it. […] so ask for it again to decide on a current reading."
   Não há controle nenhum para "ask for it again". A seção se chama "Past its
   expiry" e não oferece ação alguma.
4. **O badge conta o inacionável.** A sidebar mostra "Decisões 1" apontando
   para essa expirada. O comentário em
   `console/src/surfaces/screens/decisions.tsx:24-26` documenta: "The badge in
   the sidebar is the sum of both" — somado por `countsFrom` em
   `console/src/shell/load.ts`, sem distinguir expirada de pendente.
5. **A composição da tela hoje**: `DecisionsScreen`
   (`console/src/surfaces/screens/decisions.tsx:39`) com abas
   `actions`/`changes` (`DECISIONS_TABS`, `:28`); a aba Actions é
   `ApprovalsTab` (`console/src/surfaces/screens/approvals.tsx`), que renderiza
   `ProposalCard` (`console/src/surfaces/proposal.tsx`) com `DecisionControls`
   (`console/src/surfaces/decision.tsx`); a lógica de janela fechada ("Whether
   `record`'s window for being answered has closed, on the clock") vive em
   `approvals.tsx`.
6. **O contrato de leitura que o produto já serve** (documentado em
   `surfaces/console/client.py:260-270`): `GET /v1/approvals` (não decididas,
   mais antiga primeiro; parâmetros `run_id`, `limit`),
   `GET /v1/approvals/{approval_id}` ("with its rollback plan and evidence"),
   `POST /v1/approvals/{approval_id}/rollback`. A decisão em si é
   `POST /v1/interactions/{interaction_id}/approve` e
   `POST /v1/interactions/{interaction_id}/reject` (`client.py:250-256`).
7. **Histórico já existe no serviço de propostas**:
   `ProposalQueue.decided(limit=MAX_DECIDED_PROPOSAL_HISTORY)`
   (`platform/proposals/service.py:224`) — para a aba Changes. O vocabulário
   de decisão já existe no cliente vivo: `Decision {id, decidedBy, surface,
   verdict, at}` (`console/src/live/reducer.ts:88`).
8. **A cadeia proposta→aprovação→execução registrada existe** — composta pela
   onda anterior (RemediationGate/AutonomyGate na composition root). Esta
   feature não cria o mecanismo de decidir; ela cria a leitura por campo, a
   re-proposta e a tela.
9. **A aba Changes vazia** mostra "The agent has proposed nothing" + link
   "See what is running" — este empty state está correto em substância e é
   mantido (uma linha + um link), só re-vestido no padrão visual.

---

## Alegações normativas

Frases curtas, individualmente testáveis; o acceptance spec codifica cada uma.
As marcadas **[staging]** são staging-safe e rodam também contra
`https://stg-ninjasre.lan.kyo.ninja` — leitura pura, exceto AN-08, que é
propose-only (cria proposta pendente; não aplica nada).

- **AN-01** O cartão de decisão tem como título uma sentença humana derivada
  da ação e do alvo — nunca `path = …`, nunca JSON, nunca um identificador.
  **[staging]**
- **AN-02** Nenhum texto contendo `{"` é visível na página com todos os
  `<details>` fechados. **[staging]**
- **AN-03** O risco é um medidor de 5 segmentos com N preenchidos e o rótulo
  "risco N de 5". **[staging]**
- **AN-04** O cartão apresenta, cada uma como seção nomeada: "O que vai
  acontecer" (passos numerados), "Se der errado — reversão" (passos
  numerados), "Por quê" (uma frase), "Evidência que sustenta" (itens com
  link), "Raio de alcance", e a linha de autonomia ("Escrita reversível —
  fica na fila e só aplica depois do seu sim"). **[staging]**
- **AN-05** O payload bruto da ação existe na página atrás de um `<details>`
  fechado por padrão, rotulado "payload bruto da ação". **[staging]**
- **AN-06** Uma decisão pendente e não expirada mostra os controles Aprovar e
  Recusar.
- **AN-07** Uma decisão expirada mostra "Propor de novo, agora" e "Descartar",
  e não mostra Aprovar. **[staging]**
- **AN-08** Acionar "Propor de novo, agora" resulta numa proposta nova
  pendente, com leitura atual do ambiente, visível na mesma tela sem
  navegação manual. **[staging — propose-only]**
- **AN-09** O badge de Decisões na sidebar é igual ao número de decisões
  pendentes não expiradas, e ignora expiradas e decididas. **[staging]**
- **AN-10** A seção "Decididas recentemente" lista decisões decididas com
  desfecho, autor e instante relativo. **[staging]**
- **AN-11** Cada item de evidência do cartão é um link para a fonte daquele
  item, e o href não é vazio.
- **AN-12** A aba Mudanças sem propostas mostra uma linha de estado e um link,
  e nenhum parágrafo além disso. **[staging]**
- **AN-13** Com a leitura da lista falhada, a tela diz que não conseguiu ler e
  não afirma que nada está proposto.
- **AN-14** Todo texto novo da tela existe em `en` e `pt-BR`, pelo catálogo.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Decidir lendo um cartão, não um dump (Priority: P1)

Um operador abre Decisões e encontra um cartão que responde, em campos
separados e nesta ordem de leitura: o que o agente quer fazer, por quê, o que
exatamente vai acontecer, como se desfaz, que evidência sustenta, o que é
atingido, e quão arriscado é. Ele decide — Aprovar ou Recusar — sem abrir o
payload bruto nem uma vez.

**Why this priority**: é a queixa literal do operador ("uma coisa horrorosa")
e o momento de maior consequência do produto: a única escrita em produção que
o agente pode fazer passa por esta tela. Um reviewer que decide lendo um dump
de 40 linhas ou não lê, ou não decide.

**Independent Test**: no staging, abrir `/decisions` com uma proposta
pendente e conferir AN-01 a AN-06 e AN-11 sem tocar em nada além da página.

**Acceptance Scenarios**:

1. **Given** uma proposta de remediação pendente, **When** a tela renderiza,
   **Then** o título do cartão é uma sentença humana com a ação e o alvo, e o
   requester e a investigação de origem aparecem como meta-linha.
2. **Given** esse cartão, **When** as seções renderizam, **Then** os passos de
   execução e os de reversão aparecem numerados, cada um com uma frase.
3. **Given** esse cartão, **When** a evidência renderiza, **Then** cada item é
   uma frase com um link para a fonte.
4. **Given** esse cartão, **When** o risco renderiza, **Then** ele é um
   medidor de 5 segmentos com o rótulo "risco N de 5".
5. **Given** esse cartão com todos os `<details>` fechados, **When** o corpo
   da página é lido, **Then** nenhum fragmento de JSON está visível.
6. **Given** um operador com a permissão de decidir, **When** o cartão de uma
   pendente não expirada renderiza, **Then** Aprovar e Recusar estão
   presentes e operantes.

---

### User Story 2 - A expirada tem uma saída (Priority: P1)

Um operador chega numa proposta que expirou enquanto ninguém olhava. A tela
diz por que ela não aceita mais decisão — o ambiente foi lido antes de expirar
— e oferece o único ato que faz sentido: pedir uma proposta nova, sobre uma
leitura atual. Um clique, e a proposta nova pendente está na tela.

**Why this priority**: hoje este é um beco sem saída que o produto **aponta**
("ask for it again") sem oferecer. É a segunda queixa literal do operador, e é
o que faz o badge mentir (US4). Sem a re-proposta, toda expirada vira lixo
permanente que continua contando como trabalho pendente.

**Independent Test**: no staging, com a proposta expirada real, acionar
"Propor de novo, agora" e conferir que uma pendente nova aparece e que a
expirada some da fila de acionáveis.

**Acceptance Scenarios**:

1. **Given** uma proposta expirada, **When** o cartão renderiza, **Then** o
   rodapé diz que a janela fechou e por quê, e oferece "Propor de novo,
   agora" e "Descartar".
2. **Given** uma proposta expirada, **When** o operador aciona "Propor de
   novo, agora", **Then** o deployment produz uma proposta nova pendente com
   leitura atual do ambiente, e a tela passa a mostrá-la.
3. **Given** a proposta nova criada em 2, **When** ela é inspecionada,
   **Then** o instante de criação dela é posterior ao da expirada e o estado
   dela é pendente.
4. **Given** uma expirada cuja origem não existe mais (o plano ou a
   capacidade saiu do catálogo), **When** o operador aciona a re-proposta,
   **Then** a resposta é uma recusa nomeada dizendo o que faltou, e não um
   erro de servidor.
5. **Given** uma proposta expirada, **When** o operador aciona "Descartar",
   **Then** ela deixa a fila de pendentes e entra no histórico como
   descartada.

---

### User Story 3 - O que já foi decidido tem registro visível (Priority: P2)

Abaixo da fila, o operador vê as últimas decisões tomadas: o que era, quem
decidiu, qual foi o veredito, e — quando aplicada — se a verificação passou.

**Why this priority**: a tela hoje só mostra o presente; a confiança no
propose-only se constrói vendo o passado ("aprovada por você, aplicada e
verificada"). O dado já existe (`ProposalQueue.decided`, o ledger de
remediação); é leitura, não mecanismo novo.

**Independent Test**: decidir uma proposta (ou usar uma decidida existente) e
conferir que ela aparece em "Decididas recentemente" com desfecho, autor e
instante.

**Acceptance Scenarios**:

1. **Given** decisões já tomadas, **When** a tela renderiza, **Then**
   "Decididas recentemente" lista cada uma com forma de status, sentença,
   desfecho e instante relativo.
2. **Given** uma aprovada que foi aplicada e verificada, **When** a linha
   renderiza, **Then** ela diz "aprovada por «autor», aplicada e verificada".
3. **Given** uma recusada, **When** a linha renderiza, **Then** ela carrega a
   razão da recusa quando registrada.
4. **Given** nenhuma decisão passada, **When** a seção renderiza, **Then**
   ela declara a ausência em uma linha, sem parágrafo.

---

### User Story 4 - O badge diz o que é acionável (Priority: P2)

O número vermelho ao lado de "Decisões" na sidebar é a resposta à pergunta
"quantas coisas esperam a minha decisão agora" — pendentes e dentro da
janela. Expirada não conta; decidida não conta.

**Why this priority**: um badge que conta o inacionável treina o operador a
ignorá-lo — que é o pior desfecho possível para o único contador que pede
ação humana em produção.

**Independent Test**: com uma expirada e nenhuma pendente, o badge é zero (ou
ausente); criar uma pendente via re-proposta e o badge vira 1.

**Acceptance Scenarios**:

1. **Given** só uma proposta expirada, **When** a sidebar renderiza, **Then**
   o badge de Decisões não mostra 1 — mostra zero ou nada.
2. **Given** uma pendente dentro da janela, **When** a sidebar renderiza,
   **Then** o badge mostra 1.
3. **Given** a pendente decidida, **When** a sidebar re-renderiza, **Then** o
   badge decresce no mesmo ciclo de leitura.

---

### User Story 5 - A aba Mudanças no mesmo padrão (Priority: P3)

A aba Mudanças mantém seu conteúdo (propostas de configuração), vestida no
padrão do board: vazia, é uma linha e um link; com conteúdo, os cartões usam a
mesma anatomia de cartão de decisão.

**Why this priority**: P3 porque o staging não tem propostas de mudança e o
conteúdo da aba não muda — só a pele. Fica na feature para a tela inteira
sair dela no padrão, não metade.

**Acceptance Scenarios**:

1. **Given** nenhuma proposta de mudança, **When** a aba renderiza, **Then**
   uma linha de estado e um link "ver o que está rodando", nada mais.
2. **Given** as duas abas, **When** elas renderizam, **Then** são pills no
   padrão do artboard, com a contagem na aba Ações.

### Edge Cases

- **Proposta pendente que expira com a tela aberta.** O `expires_at` passa
  enquanto o operador lê. A decisão enviada depois disso é recusada pelo
  backend (comportamento existente); a tela troca o rodapé para o estado
  expirado na resposta, sem stack trace e sem afirmar que foi aprovada.
- **Re-proposta concorrente.** Dois operadores acionam "Propor de novo" na
  mesma expirada. O mecanismo devolve a mesma proposta nova para o segundo
  (idempotência por origem) ou uma recusa nomeada — nunca duas pendentes
  idênticas na fila.
- **Evidência cuja referência não resolve mais.** `reference` aponta para uma
  timeline ou leitura que já não existe. O link leva à superfície da fonte
  com a ausência declarada lá; o cartão não esconde o item nem quebra.
- **Campos ausentes no documento.** Proposta antiga sem `intent` ou sem
  `prior_effectiveness`: a seção correspondente declara a ausência ("não
  registrado"), o cartão renderiza; nenhum campo ausente derruba a página.
- **`steps` vazio com `summary` presente.** O cartão mostra o `summary` como
  passo único, marcado como resumo — nunca seção vazia ao lado de payload
  cheio.
- **Rollback ausente (`reversible: false`).** A seção "Se der errado" diz
  "sem reversão registrada — esta ação não é reversível" em vocabulário de
  perigo (vermelho), e o medidor de risco reflete a classe servida.
- **Muitas pendentes.** A fila ordena mais antiga primeiro (ordem que o
  gateway já serve); o cartão expandido é o primeiro; os demais colapsados em
  linhas de uma sentença com risco e idade.
- **Sem permissão de decidir.** Os controles não renderizam (padrão `may()`
  existente); o cartão continua legível por inteiro.

## Requirements *(mandatory)*

### O contrato por campo

- **FR-001**: A listagem de decisões DEVE servir cada decisão com os campos
  estruturados que o cartão renderiza — sem exigir que o cliente interprete o
  documento serializado.
- **FR-002**: O detalhe de uma decisão DEVE carregar, com nomes estáveis no
  contrato: identidade, estado (`pending`/`expired`/`approved`/`rejected`/
  `discarded`), título humano, requester, origem (run e, quando houver,
  incidente), intenção, passos de execução (ordinal + sentença), passos de
  reversão (ordinal + sentença), evidência (sentença + referência), raio de
  alcance (contagem, profundidade, conhecido), risco (classe + score numa
  escala declarada), autonomia (nível de efeito colateral, reversível,
  enfileirada), instantes (criada, expira, decidida) e decisor/veredito
  quando decidida.
- **FR-003**: O título humano DEVE ser uma sentença com ação e alvo, derivada
  no backend — o mesmo título para toda superfície que o mostrar.
- **FR-004**: O documento integral da ação DEVE continuar disponível no
  detalhe, como campo único, para o `<details>` de payload bruto.
- **FR-005**: O score de risco DEVE ser servido pelo backend com a escala
  (N de M); a tela NÃO DEVE derivar risco por conta própria.
- **FR-006**: A listagem DEVE aceitar `state=pending|expired|decided`, com
  limite. `pending` inclui somente pendentes dentro da janela; `expired`
  inclui somente expiradas; `decided` inclui somente `approved`, `rejected` e
  `discarded`. A ordem das pendentes segue mais antiga primeiro e a das
  expiradas/decididas, mais recente primeiro.
- **FR-007**: Campos ausentes no documento DEVEM chegar como ausência
  declarada no contrato, nunca como omissão silenciosa que o cliente tem de
  adivinhar.

### O cartão

- **FR-008**: A aba Ações DEVE renderizar cada decisão como o cartão do
  artboard: cabeçalho (forma triangular de atenção, título, meta-linha com
  requester e origem, medidor de risco, chip de estado), grade com "O que vai
  acontecer" e "Se der errado — reversão" à esquerda e "Por quê", "Evidência
  que sustenta", "Raio de alcance" e a linha de autonomia à direita.
- **FR-009**: Os passos de execução e de reversão DEVEM renderizar numerados,
  uma sentença por passo, com o nome da capacidade em tipografia mono como
  detalhe, não como título.
- **FR-010**: Cada item de evidência DEVE ser um link para a superfície da
  fonte daquele item.
- **FR-011**: O payload bruto DEVE existir só atrás de um `<details>` fechado
  por padrão; nenhum JSON DEVE ser visível com os `<details>` fechados.
- **FR-012**: Aprovar e Recusar DEVEM operar pelos endpoints de decisão
  existentes, e só renderizar para quem tem a permissão de decidir.
- **FR-013**: O estado da decisão DEVE usar as formas de status do padrão
  (triângulo = atenção/aprovação; círculo = decidida-ok; quadrado =
  recusada/perigo), com o texto ao lado — nunca cor sozinha.

### A expirada

- **FR-014**: Uma decisão expirada DEVE mostrar um rodapé que diz que a
  janela fechou e por quê, com "Propor de novo, agora" e "Descartar".
- **FR-015**: Um endpoint de re-proposta DEVE existir: dado o identificador de
  uma decisão expirada, ele produz uma proposta nova pendente com leitura
  atual do ambiente, pelo mesmo mecanismo que produziu a original, e devolve
  a identidade da nova.
- **FR-016**: A re-proposta de uma decisão cuja origem não existe mais DEVE
  ser recusada com a causa nomeada, e NÃO DEVE derrubar nada.
- **FR-017**: A re-proposta DEVE ser idempotente por origem enquanto a nova
  proposta estiver pendente: acioná-la de novo devolve a mesma pendente.
- **FR-018**: Descartar DEVE tirar a expirada da fila e registrá-la no
  histórico como descartada, sem apagá-la.
- **FR-019**: Uma decisão que expira DEVE deixar de oferecer Aprovar/Recusar,
  e uma decisão enviada fora da janela DEVE resultar na recusa existente do
  backend apresentada como troca de estado do cartão.

### Badge e histórico

- **FR-020**: O contador de Decisões da sidebar DEVE contar somente decisões
  pendentes e dentro da janela.
- **FR-021**: A tela DEVE mostrar "Decididas recentemente": as últimas
  decisões com forma de status, sentença, desfecho (aprovada/recusada/
  descartada, e aplicada+verificada quando for o caso), autor e instante
  relativo.
- **FR-022**: A ausência de decididas DEVE ser uma linha declarada, não uma
  seção vazia nem um parágrafo.

### Honestidade de leitura e i18n

- **FR-023**: Com a leitura da lista falhada, a tela DEVE dizer que não
  conseguiu ler e NÃO DEVE afirmar que nada está proposto.
- **FR-024**: Todo texto novo DEVE existir em `en` e `pt-BR` pelo catálogo;
  esta feature NÃO edita os arquivos de i18n (a dona do slot é a feature par)
  — as chaves são declaradas no relatório final e aplicadas no merge.
- **FR-025**: A aba Mudanças vazia DEVE ser uma linha de estado e um link.

### Contrato e artefatos gerados

- **FR-026**: O documento de API committed DEVE refletir o contrato por campo
  e o endpoint de re-proposta; o cliente TS DEVE ser regenerado a partir
  dele.
- **FR-027**: O dataset simulado DEVE servir decisões nos três estados
  (pendente, expirada, decidida) com os campos novos, para a suíte de console
  e o registro visual.
- **FR-028**: O registro de telas visuais DEVE cobrir a tela de Decisões nos
  estados pendente e expirada.

### Key Entities

- **Decisão (ação proposta)** — o que o agente quer fazer agora: uma ação
  com alvo, plano, reversão, evidência e janela. Estados: pendente,
  expirada, aprovada, recusada, descartada. A identidade é a do registro de
  aprovação existente.
- **Título humano** — a sentença que nomeia a decisão em toda superfície.
  Derivada no backend da ação e do alvo; nunca um identificador.
- **Re-proposta** — o ato de pedir ao mecanismo de origem uma proposta nova
  sobre leitura atual, a partir de uma expirada. Produz decisão nova;
  a expirada permanece no histórico.
- **Evidência da decisão** — item com sentença e referência resolvível para a
  superfície da fonte.

## Success Criteria *(mandatory)*

- **SC-001**: No staging, `/decisions` renderiza a proposta real como cartão:
  título humano, medidor de risco, passos, reversão, evidência com links — e
  nenhum JSON visível com os `<details>` fechados.
- **SC-002**: A proposta expirada real do staging exibe "Propor de novo,
  agora"; acioná-la produz uma pendente nova visível na tela, com
  `created_at` posterior e estado pendente, confirmada também pela API.
- **SC-003**: O badge da sidebar no staging é igual ao número de pendentes
  não expiradas devolvido pela API, nas duas situações medidas (só expirada →
  zero; uma pendente → 1).
- **SC-004**: "Decididas recentemente" lista a decisão tomada em SC-002
  depois de decidida, com autor e desfecho.
- **SC-005**: O acceptance spec foi confirmado vermelho antes da
  implementação, com a mensagem real de cada alegação registrada.
- **SC-006**: O gate visual da onda (EXECUCAO.md §3) tem VEREDITO.md CONFORME
  para `/decisions` nos dois temas contra os dois artboards, com as capturas
  em `evidence/visual/`.
- **SC-007**: `make verify` termina verde, tendo partido de verde.
- **SC-008**: Zero strings novas fora do catálogo i18n; as chaves declaradas
  no relatório final cobrem `en` e `pt-BR`.

## Consultas de evidência em staging

A feature alega escrita nova (re-proposta) e contagem honesta. Provas no
staging, parte do DoD:

1. Antes da re-proposta: `GET /v1/approvals` devolve a expirada e nenhuma
   pendente; o badge mostra zero.
2. Depois de "Propor de novo, agora": `GET /v1/approvals` devolve exatamente
   uma pendente nova; `created_at` dela > `created_at` da expirada; o badge
   mostra 1. Acionar de novo não cria uma segunda (FR-017).
3. Depois de decidir a nova: ela aparece em "Decididas recentemente" e a
   listagem de decididas da API a devolve com decisor e veredito.
4. A contagem de linhas da tabela de aprovações não diminui em nenhum passo
   (descartar e expirar marcam, nunca apagam) — a consulta SQL literal é
   fixada no plano, com o nome real da tabela do store de aprovações.

## Assumptions

- **O documento da ação é a fonte; nenhum dado novo é inventado.** Tudo que o
  cartão mostra já existe no payload observado (fato 2). O trabalho é servi-lo
  por campo e derivar o título e o score no backend — não redesenhar o
  mecanismo de proposta.
- **Aprovar/Recusar continuam pelos endpoints existentes** de interações
  (fato 6); esta feature não cria caminho novo de decisão, só a re-proposta.
- **A re-proposta reusa o mecanismo que propôs a original** (o gate composto
  pela onda anterior). Se a origem exigir contexto que só o run tinha, a
  recusa nomeada de FR-016 é a resposta certa — a feature não fabrica
  contexto.
- **A tela continua Server Components + leitura pelo cliente gerado**, como
  toda tela do console; o vivo por push desta tela (chegar proposta nova sem
  reload) é da feature de canal vivo e não desta.
- **Esta feature NÃO é dona dos single-write no S2** — a par dela é. Chaves
  i18n e a linha nova de `console/visual/screens.json` são declaradas no
  relatório final e aplicadas pelo orquestrador no merge.
- **O nome da tabela de aprovações** e a rota-arquivo do gateway são
  confirmados na partida do plano via codegraph — os caminhos de API estão
  cravados (fato 6), os arquivos Python do serving são localizados antes da
  primeira edição, nunca presumidos.

## Dependencies

- **Depende da 000-fundacao-visual** (S0): tokens, chip com contorno, formas,
  fontes e shell novos — o cartão é desenhado com eles.
- **Interseção nula com a par do slot (060-telas-de-area)**: esta é rotas de
  decisão no gateway + `platform` de propostas/aprovações + as telas
  `decisions.tsx`/`approvals.tsx`/`proposals.tsx`/`proposal.tsx`/
  `decision.tsx`; aquela é `/incidents`, `/resources`, `/knowledge`,
  `/agent`. Nenhum arquivo em comum; single-write é dela.
- **A 050-painel-vivo consome esta**: a banda de aprovação inline do Painel
  usa o contrato por campo e os mesmos endpoints; o cartão completo fica a um
  clique. Esta feature não toca o Painel.
- **A demo do S5** precisa desta: decidir a partir do cartão estruturado é um
  passo do roteiro.

## Out of Scope

- **O Painel** e sua banda de aprovação inline — da 050-painel-vivo.
- **Chegada por push de proposta nova** (SSE) — da 010-canal-vivo; esta tela
  continua lendo no request e revalidando como as demais.
- **Executar remediação nova ou mudar a política de autonomia** — o
  propose-only permanece; nenhuma escrita além de decidir/repropor/descartar.
- **O vocabulário de verificação pós-aplicação** (o "aplicada e verificada"
  lê o ledger existente; medir/estender a verificação é de outra onda).
- **Notificações** (push/e-mail) de proposta nova.
- **Qualquer outra tela** e qualquer token/ícone novo — a fundação está
  congelada; necessidade nova é declarada no relatório.
