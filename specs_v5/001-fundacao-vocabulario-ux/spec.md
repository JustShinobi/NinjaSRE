# Feature Specification: Fundação de vocabulário e contratos de UX

**Feature Branch**: `feat/v5-001-fundacao-vocabulario-ux`

**Created**: 2026-08-14

**Status**: Draft

**Input**: User description: "Fundação de UX do produto inteiro: vocabulário único de estado, registro de nomes de exibição, contrato de CTA para empty states, documentação fora do fluxo, orçamento de rolagem e fonte única para contagens."

**Referência visual (DoD)**: [../mockups/settings-v5.html](../mockups/settings-v5.html) — a seção "Regras transversais para a spec" e o uso consistente de chips, nomes de exibição e CTAs em todos os mockups são a expressão visual desta fundação.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Um estado, uma palavra (Priority: P1)

Um operador olha para uma credencial em qualquer tela — Setup, Integrations,
Administration, um card de verificação — e lê o mesmo vocabulário de estado,
com a mesma cor e o mesmo componente visual.

**Why this priority**: Hoje o mesmo fato aparece como "stored, unchecked",
"it answered", "HEALTHY", "Verified — the last check passed" e "UNCONFIGURED"
dependendo da tela. O operador precisa retraduzir o produto a cada página; é a
causa mais barata de consertar da sensação de "confuso" relatada.

**Independent Test**: Percorrer todas as telas que exibem estado de credencial
ou verificação e conferir que só as palavras do vocabulário canônico aparecem.

**Acceptance Scenarios**:

1. **Given** uma credencial recém-gravada e ainda não testada, **When**
   qualquer tela a exibe, **Then** o estado exibido é "Stored" (chip neutro),
   nunca "stored, unchecked" nem "UNCONFIGURED".
2. **Given** uma verificação que passou, **When** qualquer tela a exibe,
   **Then** o estado é "Verified" (chip positivo), nunca "it answered" nem
   "HEALTHY".
3. **Given** uma verificação que falhou, **When** qualquer tela a exibe,
   **Then** o estado é "Failing" (chip crítico) acompanhado do diagnóstico.

### User Story 2 - Nomes de gente, não de código (Priority: P1)

Todo item de catálogo (integração, provider, modelo) aparece na interface com
nome de exibição e categoria; o identificador cru só aparece em contextos
técnicos (endpoint, audit, API).

**Why this priority**: `google_gemini`, `azure_monitor` e `better_stack` como
títulos são a segunda maior fonte do aspecto "não terminado" da UI.

**Independent Test**: Varredura das telas por identificadores snake_case em
posição de título ou label.

**Acceptance Scenarios**:

1. **Given** a integração `azure_monitor`, **When** ela aparece em qualquer
   lista ou título, **Then** lê-se "Azure Monitor" com a categoria
   "Observability", e o id cru não aparece.
2. **Given** um contexto técnico (URL de webhook, entrada de audit), **When**
   o id é a informação, **Then** o id cru aparece em fonte mono, deliberadamente.

### User Story 3 - Todo CTA aterrissa no alvo (Priority: P2)

Um empty state ou aviso que pede uma ação leva o operador, em um clique, à
tela **e ao campo** que resolve — nunca a uma tela genérica.

**Why this priority**: Hoje "Open configuration" (Destinations) e "Look at the
configuration" (Autonomy) despejam o operador num editor de schema com 38
seções fechadas. O fluxo de configuração quebra exatamente nesses saltos.

**Independent Test**: Inventariar todos os empty states e conferir destino e
âncora de cada CTA.

**Acceptance Scenarios**:

1. **Given** a aba Destinations sem integração de chat conectada, **When** o
   operador clica no CTA, **Then** chega ao catálogo de integrações já
   filtrado pela categoria de chat/notificação.
2. **Given** uma verificação de modelo reprovada por falta de tool calling,
   **When** o operador clica na correção, **Then** chega ao campo de seleção
   de modelo, não à raiz de uma tela.

### User Story 4 - Referência fora do fluxo (Priority: P2)

Prosa de referência (payloads de webhook, "not covered, and why", explicações
conceituais) vive recolhida ou em página de referência — nunca entre o
operador e o formulário.

**Independent Test**: Nenhuma tela de configuração exibe, expandido por
padrão, texto de referência com mais de duas frases por item.

**Acceptance Scenarios**:

1. **Given** a tela de intake de alertas, **When** ela abre, **Then** cada
   receptor mostra endpoint, estado e ações; o detalhe de payload/assinatura
   abre sob demanda.
2. **Given** o catálogo de integrações, **When** o operador quer saber por que
   um vendor não é coberto, **Then** encontra um link para a página de
   referência — o texto não está no rodapé do catálogo.

### User Story 5 - Contagens com fonte única (Priority: P2)

Toda contagem de progresso de configuração (passos restantes, verificações
pendentes) vem de uma única fonte e é idêntica em todas as superfícies.

**Independent Test**: Com o deployment em estado conhecido, comparar a
contagem exibida no dashboard, no Setup e nos empty states que a citam.

**Acceptance Scenarios**:

1. **Given** um deployment com N passos restantes, **When** dashboard, Setup e
   qualquer empty state citam o progresso, **Then** todos exibem N.

### Edge Cases

- Estado desconhecido (gateway inacessível): o chip degrada para "Unknown"
  com tooltip explicando, nunca inventa um dos quatro estados.
- Item de catálogo sem display name registrado: o build/CI falha — a ausência
  é um defeito de catálogo, não um fallback silencioso para o id cru.
- CTA cujo alvo o viewer não tem permissão de abrir: o CTA não é exibido; o
  empty state explica o estado sem oferecer ação impossível.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O produto DEVE adotar um vocabulário canônico de quatro estados
  para credenciais e verificações — Not connected, Stored, Verified, Failing —
  mais o degradado Unknown, definido em um único módulo e consumido por todas
  as superfícies (console, CLI, notificações).
- **FR-002**: Cada estado DEVE ter exatamente um componente visual (chip com
  cor semântica) reutilizado em todas as telas; texto livre de estado é
  proibido.
- **FR-003**: Todo id de catálogo (integrações, providers, modelos, papéis)
  DEVE ter nome de exibição e categoria registrados; a interface DEVE usar o
  nome de exibição em títulos, listas e labels.
- **FR-004**: Um item de catálogo sem nome de exibição DEVE reprovar em
  verificação automática (guard check), não degradar em runtime.
- **FR-005**: Todo CTA de empty state ou aviso DEVE declarar destino preciso
  (rota + âncora/filtro) e verbo específico ("Conectar uma integração de
  chat"), e NUNCA apontar para um editor genérico.
- **FR-006**: Conteúdo de referência DEVE ser apresentado recolhido por padrão
  ou em página de referência dedicada, mantendo no fluxo apenas o necessário
  para agir.
- **FR-007**: Contagens de progresso de configuração DEVEM ser servidas por
  uma única fonte no gateway e exibidas sem recomputação local.
- **FR-008**: Nenhuma tela de configuração DEVE exceder ~2 viewports de altura
  em 1080p; listas que excederiam DEVEM ganhar busca, filtro e paginação ou
  virtualização.
- **FR-009**: Todo texto novo DEVE entrar pelo catálogo de i18n existente; o
  vocabulário canônico é um conjunto de chaves de catálogo.
- **FR-010**: O contrato de CTA e o orçamento de rolagem DEVEM ser verificáveis
  por teste (inventário de empty states; medição de altura das telas com dados
  representativos).
- **FR-011**: Ajuda mora no campo. Títulos de página NÃO carregam subtítulo de
  prosa (subtítulo de dado — contagens, "Passo N de 7" — é permitido). A frase
  de ajuda aparece sob o controle que ela explica, consumida da declaração que
  o schema de configuração já carrega por campo e por seção (`field_help` /
  `section_help`); tooltips nunca carregam informação essencial (escondem o
  conteúdo e não existem em touch). Uma descrição de seção só aparece quando o
  rótulo da seção sozinho não diz o que ela faz.

### Key Entities

- **Vocabulário de estado**: conjunto fechado {Not connected, Stored,
  Verified, Failing, Unknown}, com cor semântica e chave i18n por estado.
- **Registro de exibição**: mapa id → {display name, categoria, iniciais/logo}
  cobrindo todos os catálogos do produto.
- **Contrato de CTA**: destino (rota, âncora/filtro), verbo, permissão exigida.

## Success Criteria *(mandatory)*

- **SC-001**: Zero ocorrências de vocabulário de estado fora do canônico nas
  telas do console (varredura automatizada).
- **SC-002**: Zero identificadores snake_case em posição de título/label nas
  telas do console.
- **SC-003**: 100% dos empty states com CTA levam ao alvo que resolve em um
  clique (inventário auditado).
- **SC-004**: Nenhuma tela de configuração passa de 2 viewports em 1080p com
  dados representativos (84 integrações, 15 tokens, 200 eventos de audit).
- **SC-005**: A mesma contagem de progresso aparece em todas as superfícies
  que a citam, verificado com o deployment em três estados distintos.

## Assumptions

- A língua da interface permanece inglês (catálogo i18n `en`), como hoje; o
  vocabulário canônico é definido em inglês.
- O registro de exibição pode viver junto ao catálogo de integrações no
  backend, que já serve `category` e `summary` — a spec não fixa onde.
- O guard check de nomes de exibição segue o padrão dos três guard checks
  existentes no `make verify`.

## Dependencies

- Nenhuma. Esta é a fundação; 010–070 a consomem.
