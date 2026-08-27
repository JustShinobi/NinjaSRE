# Feature Specification: Organização — Members & roles, Single sign-on, Machine tokens, Audit log

**Feature Branch**: `feat/v5-050-organizacao`

**Created**: 2026-08-14

**Status**: Draft

**Input**: User description: "Quatro páginas no grupo Organização de Settings, desmembrando a tela Administration atual: Members & roles, Single sign-on (página própria com teste guiado), Machine tokens (agrupados, com expurgo e causa do acúmulo tratada), Audit log (consertando o período que não alarga e a contagem contraditória)."

**Referência visual (DoD)**: [../mockups/settings-v5.html#mockup-1](../mockups/settings-v5.html#mockup-1) — as quatro páginas aparecem no grupo Organization da subnav; padrões de formulário, chips e ajuda por campo seguem os mockups 1 e 3.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pessoas e acessos numa página só de pessoas (Priority: P2)

Um administrador vê quem existe (pessoas e contas de serviço), que papéis têm
e as sessões ativas — sem tokens de máquina e formulário de SSO no meio.

**Why this priority**: A tela Administration atual empilha cinco assuntos numa
página; nenhum fica bom. Members & roles é o mais simples e o que já funciona
melhor — a mudança aqui é desmembramento e polimento.

**Independent Test**: Conceder e revogar um papel e encerrar uma sessão, tudo
na página, com as permissões do papel legíveis antes de conceder.

**Acceptance Scenarios**:

1. **Given** a página Members & roles, **When** ela abre, **Then** lista
   pessoas e contas de serviço com tipo e estado como chips canônicos, os
   grants de cada uma e as sessões ativas com expiração.
2. **Given** o formulário de grant, **When** o administrador escolhe um papel,
   **Then** as permissões que o papel carrega aparecem legíveis (não como a
   linha espremida de ids atual), e a concessão pede confirmação para papéis
   administrativos.

### User Story 2 - SSO com teste guiado, em página própria (Priority: P1)

Um administrador configura o provedor de identidade num fluxo com validação
por etapa e teste com claims reais antes de ligar — sem risco de trancar todo
mundo para fora.

**Why this priority**: O formulário de SSO hoje são 8 campos OIDC crus no
rodapé da aba People. É a configuração mais perigosa do produto (um valor
errado tranca a organização) e a que menos orientação tem. O produto já exige
teste antes de ligar — a página precisa fazer esse contrato ser um fluxo, não
uma frase.

**Independent Test**: Configurar um provedor de teste de ponta a ponta só com
o que a página mostra; tentar ligar sem teste aprovado e ser impedido com
explicação.

**Acceptance Scenarios**:

1. **Given** a página Single sign-on sem configuração, **When** ela abre,
   **Then** o estado "Disabled — not tested" aparece como chip com a regra
   ("não pode virar o caminho de entrada até ser testado"), e os campos têm
   ajuda por campo (o que é, onde encontrar no provedor).
2. **Given** a configuração salva, **When** o administrador cola o resultado
   de um sign-in de teste, **Then** a página mostra o que cada claim resolveu
   (identidade, time, papel) e aprova ou reprova com diagnóstico.
3. **Given** teste aprovado, **When** o administrador liga o SSO, **Then** a
   mudança é registrada em audit e o caminho de fallback (conta local) fica
   declarado na página.

### User Story 3 - Tokens de máquina agrupados e expurgáveis (Priority: P2)

Um administrador vê os tokens agrupados por finalidade, entende por que
existem, e revoga em massa os que não deveriam se acumular.

**Why this priority**: A lista atual tem ~15 linhas idênticas "bootstrap —
investigation.read, token.manage" sem explicação nem ação em massa — sintoma
visível de emissão repetida que a spec trata na causa e no sintoma.

**Independent Test**: Com o acúmulo atual, agrupar, revogar em massa e
verificar que a emissão repetida pela mesma finalidade reutiliza ou substitui
em vez de acumular.

**Acceptance Scenarios**:

1. **Given** a página Machine tokens, **When** ela abre, **Then** tokens da
   mesma finalidade aparecem agrupados com contagem, escopos legíveis, último
   uso, e ação "revogar todos menos o mais recente".
2. **Given** uma nova emissão para finalidade que já tem token ativo, **When**
   ela ocorre, **Then** o comportamento é declarado e visível (substituição
   registrada em audit) — o acúmulo silencioso deixa de ser o default.
3. **Given** a emissão de um token, **When** o formulário abre, **Then** os
   escopos são escolhidos de uma lista legível, não digitados de memória.

### User Story 4 - Audit log que responde ao filtro (Priority: P1)

Um administrador filtra o audit por período, ator e tipo de ação com controles
nomeados, e o que a página afirma é consistente com o que ela mostra.

**Why this priority**: Dois defeitos confirmados ao vivo: "Widen the period"
não faz nada, e a página diz "default — 200 events" e "Nothing has been
recorded" ao mesmo tempo. Um audit em que não se pode confiar é pior que
nenhum.

**Independent Test**: Reproduzir os dois defeitos no estado atual; verificar
que na página nova o alargamento de período altera o resultado e que contagem
e lista vêm da mesma consulta.

**Acceptance Scenarios**:

1. **Given** um período sem eventos, **When** o administrador clica em
   alargar o período, **Then** a consulta reexecuta com o período maior e o
   resultado muda de acordo (defeito atual: botão sem efeito).
2. **Given** qualquer estado, **When** a página exibe uma contagem de
   eventos, **Then** a lista exibida e a contagem vêm da mesma consulta e
   coincidem (defeito atual: 200 vs nada).
3. **Given** os filtros, **When** exibidos, **Then** têm rótulos nomeados
   (período com presets legíveis, ator, tipo de ação) em vez da fila de
   datas cruas atual, e o export respeita os filtros ativos.

### Edge Cases

- Revogar o próprio grant de administrador: bloqueado com explicação quando é
  o último administrador (hoje a página oferece "Remove" no OWNER do próprio
  bootstrap sem aviso aparente).
- SSO ligado com fallback local desabilitado e teste expirado: a página
  impede e explica — o invariante "um provedor não testado é todo operador
  trancado" vira regra de interface.
- Audit com milhares de eventos: paginação com contagem total honesta
  (truncamento declarado, seguindo o padrão do produto para respostas
  truncadas).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A tela Administration DEVE ser desmembrada em quatro páginas da
  subnav Organização: Members & roles, Single sign-on, Machine tokens, Audit
  log — cada uma com a permissão que a API já exige para os dados que lê.
- **FR-002**: Members & roles DEVE listar principals com chips canônicos,
  grants com permissões legíveis e sessões ativas com revogação.
- **FR-003**: Single sign-on DEVE ser um fluxo com etapas (configurar →
  testar com claims reais → ligar), ajuda por campo, e bloqueio de ativação
  sem teste aprovado — preservando o contrato existente de que mudanças
  exigem novo teste.
- **FR-004**: Machine tokens DEVE agrupar por finalidade com contagem, último
  uso, escopos legíveis, revogação em massa, e emissão que substitui em vez
  de acumular para a mesma finalidade (comportamento registrado em audit).
- **FR-005**: Audit log DEVE ter filtros nomeados (período com presets, ator,
  tipo), export respeitando filtros, e contagem sempre consistente com a
  lista (mesma consulta).
- **FR-006**: O defeito do alargamento de período DEVE ser corrigido: a ação
  reexecuta a consulta com o novo período.
- **FR-007**: Ações consequentes destas páginas (grant, revogação, ativação
  de SSO, expurgo de tokens) DEVEM continuar registradas no audit, e as
  perigosas pedem confirmação explícita.

### Key Entities

- **Principal**: pessoa ou conta de serviço, tipo, estado, grants, sessões.
- **Configuração de SSO**: provedor, campos OIDC, estado do teste, ativação.
- **Grupo de tokens**: finalidade, tokens (escopos, emissão, último uso).
- **Consulta de audit**: período, ator, tipo → eventos + contagem (uma fonte).

## Success Criteria *(mandatory)*

- **SC-001**: Os dois defeitos confirmados do Audit (botão sem efeito;
  contagem contraditória) não são reproduzíveis na página nova.
- **SC-002**: Configurar SSO de ponta a ponta sem documentação externa, com o
  teste guiado impedindo ativação insegura (teste de usabilidade).
- **SC-003**: A lista de tokens com o acúmulo atual (~15 duplicados) cabe em
  uma dobra, agrupada, e o expurgo em massa a reduz em um gesto.
- **SC-004**: Cada página do desmembramento cabe em até 2 viewports em 1080p
  com dados representativos.

## Assumptions

- O modelo de papéis e permissões existente não muda; muda a apresentação e o
  desmembramento das superfícies.
- A causa do acúmulo de tokens do bootstrap (emissões repetidas a cada
  deploy/execução) é tratável no fluxo de emissão; a spec exige o
  comportamento, o plano decide o mecanismo.
- O export do audit mantém o formato atual.

## Dependencies

- 010 (subnav Organização).
- 001 (vocabulário, chips, contrato de CTA).
- A 070 depende desta para aposentar os grupos de schema de SSO
  (`policies.sso`, `policies.sso.claims`).
