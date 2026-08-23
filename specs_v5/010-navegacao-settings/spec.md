# Feature Specification: Navegação híbrida e shell de Settings

**Feature Branch**: `feat/v5-010-navegacao-settings`

**Created**: 2026-08-14

**Status**: Draft

**Input**: User description: "Sidebar híbrida: Integrations permanece como entrada própria; o resto do grupo Settings vira uma entrada única com navegação secundária própria, agrupada por intenção (Organização / Agente / Dados). Setup sai da sidebar e vira wizard."

**Referência visual (DoD)**: [../mockups/settings-v5.html#mockup-1](../mockups/settings-v5.html#mockup-1) — sidebar híbrida (grupo Settings com exatamente Integrations + Settings) e subnav com os grupos Organization / Agent / Data. O mockup é normativo em estrutura, agrupamento e vocabulário.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Encontrar qualquer configuração em dois cliques (Priority: P1)

Um operador que quer mudar qualquer coisa configurável — modelo, SSO, regra de
autonomia, destino de notificação — abre **Settings** e encontra a página
certa numa navegação secundária agrupada por intenção, sem precisar saber a
arquitetura interna do produto.

**Why this priority**: Hoje o grupo Settings tem seis entradas organizadas por
subsistema (catálogo, pipeline, política, schema, identidade), e três delas
apontam umas para as outras. É a causa raiz do "fluxo de configuração confuso".

**Independent Test**: Dar a um operador que nunca viu o produto dez tarefas de
configuração ("troque o modelo", "veja quem tem acesso", "silencie
notificações à noite") e medir cliques e acertos de primeira.

**Acceptance Scenarios**:

1. **Given** o console aberto, **When** o operador clica em Settings na
   sidebar, **Then** vê a navegação secundária com os grupos Organização
   (Members & roles, Single sign-on, Machine tokens, Audit log), Agente
   (Models & providers, Autonomy & guardrails, Notifications) e Dados
   (Alert intake, Schedules & destinations), e a primeira página do primeiro
   grupo que sua permissão alcança já aberta.
2. **Given** um viewer sem permissão administrativa, **When** abre Settings,
   **Then** os grupos e páginas que sua permissão não alcança estão ausentes
   (não desabilitados), preservando a regra atual de ausência.
3. **Given** qualquer página de Settings, **When** o operador olha a sidebar
   principal, **Then** ela contém apenas Now, Environment, Integrations e
   Settings — Setup, Signals, Autonomy, Configuration e Administration não
   são mais entradas de primeiro nível.

### User Story 2 - Endereços antigos continuam funcionando (Priority: P1)

Quem chega por um link antigo (`/autonomy`, `/administration`,
`/signals?tab=destinations`) aterrissa na página nova equivalente.

**Why this priority**: O projeto já estabeleceu o padrão "endereços antigos
encontram os novos" na reorganização anterior; quebrá-lo agora invalidaria
links em relatórios, notificações e na memória dos operadores.

**Independent Test**: Tabela de redirecionamentos antiga→nova percorrida por
teste de deep link.

**Acceptance Scenarios**:

1. **Given** o endereço `/autonomy`, **When** aberto, **Then** redireciona
   para a página Autonomy & guardrails dentro de Settings.
2. **Given** `/signals?tab=destinations`, **When** aberto, **Then**
   redireciona para Schedules & destinations.
3. **Given** `/configuration`, **When** aberto antes da spec 070 concluir,
   **Then** continua servindo o editor atual; depois da 070, redireciona para
   Settings (a 070 define o destino fino por seção).

### User Story 3 - Setup é uma tarefa, não um lugar (Priority: P2)

O primeiro contato com um deployment não configurado leva ao wizard de setup;
depois de completo, o wizard some e o dashboard oferece "revisar configuração"
apontando para Settings.

**Independent Test**: Deployment novo → wizard aparece; checklist completo →
entrada some e deep link volta ao dashboard.

**Acceptance Scenarios**:

1. **Given** um deployment com passos pendentes, **When** o operador entra no
   console, **Then** o dashboard exibe o convite ao wizard (comportamento
   atual do checklist), e o wizard vive em rota própria fora da sidebar.
2. **Given** o checklist completo, **When** o operador abre a rota do wizard,
   **Then** é levado ao dashboard, sem erro.

### Edge Cases

- Busca global (Ctrl+K): os comandos de navegação passam a incluir as páginas
  de Settings por nome de exibição ("Single sign-on"), não só as áreas de
  primeiro nível.
- Página de Settings aberta quando a permissão é revogada em sessão: o
  comportamento degrada como hoje (403 da API na tela), sem quebrar a subnav.
- Viewport estreito: a subnav de Settings colapsa (padrão responsivo), sem
  criar segunda barra de rolagem horizontal.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A sidebar principal DEVE passar a conter, no grupo Settings,
  exatamente duas entradas: Integrations e Settings.
- **FR-002**: Settings DEVE ter navegação secundária própria com os grupos e
  páginas: Organização — Members & roles, Single sign-on, Machine tokens,
  Audit log; Agente — Models & providers, Autonomy & guardrails,
  Notifications; Dados — Alert intake, Schedules & destinations.
- **FR-003**: Cada página de Settings DEVE declarar a permissão da API que a
  gata, seguindo o contrato atual (permissão do servidor, copiada por nome, e
  verificada pelo teste de contrato existente).
- **FR-004**: Grupos sem nenhuma página alcançável pela permissão do viewer
  DEVEM ser omitidos por inteiro.
- **FR-005**: Toda rota antiga do grupo Settings DEVE redirecionar para a
  página nova equivalente, incluindo variantes com query de aba; a tabela de
  redirecionamento é parte da entrega.
- **FR-006**: O wizard de Setup DEVE sair da sidebar e viver em rota própria;
  a regra de visibilidade condicionada ao checklist é transferida para os
  pontos de entrada (dashboard, redirecionamento).
- **FR-007**: A paleta de comandos e a busca global DEVEM indexar as páginas
  de Settings por nome de exibição.
- **FR-008**: Breadcrumb e título de página DEVEM refletir a hierarquia
  (Settings → grupo → página) usando o mecanismo de trilha existente.
- **FR-009**: O manifesto de rotas DEVE continuar sendo a única resposta a
  "que rotas existem", com as páginas de Settings enumeradas nele para que os
  testes de contrato, deep link e permissão as cubram por construção.

### Key Entities

- **Página de Settings**: id, rota, grupo, nome de exibição, permissão,
  componente; enumerada no manifesto de rotas.
- **Tabela de redirecionamento**: rota antiga (com padrão de query) → rota
  nova.

## Success Criteria *(mandatory)*

- **SC-001**: Dez tarefas de configuração dadas a um operador novo terminam
  na página certa em no máximo dois cliques a partir da sidebar, sem uso da
  busca.
- **SC-002**: 100% das rotas antigas do grupo Settings redirecionam para o
  destino correto (teste de deep link com a tabela completa).
- **SC-003**: A sidebar principal exibe no máximo 4 grupos e 10 entradas em
  qualquer estado do deployment.
- **SC-004**: Nenhuma regressão nos testes de contrato de permissão do
  console.

## Assumptions

- Os nomes das páginas ficam em inglês na UI (catálogo i18n atual), com os
  grupos da subnav também em inglês ("Organization", "Agent", "Data") — os
  nomes em português nesta spec são descritivos.
- Integrations mantém a rota `/integrations` atual (decisão híbrida).
- A fusão Decisions/Knowledge/Agent (grupos Now e Environment da v4) não é
  tocada por esta onda.

## Dependencies

- 001 (vocabulário e contrato de CTA) para os textos e destinos da subnav.
- As páginas listadas na subnav são entregues por 040, 050 e 060; até lá a
  subnav aponta para as telas atuais equivalentes (Autonomy atual, seções de
  Administration), mantendo o produto navegável durante a migração.
