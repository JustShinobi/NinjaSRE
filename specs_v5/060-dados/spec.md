# Feature Specification: Dados — Alert intake, Schedules & destinations

**Feature Branch**: `feat/v5-060-dados`

**Created**: 2026-08-14

**Status**: Draft

**Input**: User description: "Duas páginas no grupo Dados de Settings, sucedendo a tela Signals: Alert intake (receptores de webhook com configuração à frente e referência recolhida) e Schedules & destinations (agendas recorrentes e para onde vão os resultados, com CTA correto para o catálogo)."

**Referência visual (DoD)**: [../mockups/settings-v5.html#mockup-1](../mockups/settings-v5.html#mockup-1) — as duas páginas aparecem no grupo Data da subnav; o CTA de Destinations aterrissa no catálogo do [#mockup-2](../mockups/settings-v5.html#mockup-2) filtrado por categoria.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Apontar um alerta para cá em um minuto (Priority: P1)

Um operador conectando o Alertmanager (ou Grafana, Datadog, etc.) abre Alert
intake, copia o endpoint e o segredo do receptor, cola no emissor e vê o
primeiro payload chegar — a referência técnica existe, mas só quando pedida.

**Why this priority**: A aba Intake atual é uma página de documentação com uma
ferramenta de teste ao lado: cada receptor exibe payload, headers e assinatura
expandidos, e a ação real (copiar o endpoint, emitir o token) fica no meio da
prosa. Apontar alertas é o passo 7 do setup — o funil termina aqui.

**Independent Test**: Conectar um Alertmanager real usando só o que a página
mostra; medir o tempo até o primeiro evento aparecer como recebido.

**Acceptance Scenarios**:

1. **Given** a página Alert intake, **When** ela abre, **Then** cada receptor
   é uma linha com nome de exibição, endpoint com ação de copiar, chip de
   atividade ("nada chegou ainda" / "último evento há N min") e acesso ao
   detalhe — o payload e a autenticação ficam no detalhe, recolhidos.
2. **Given** o detalhe de um receptor, **When** expandido, **Then** mostra o
   formato esperado, o mecanismo de confiança (segredo, assinatura, token de
   entrega) e o teste de entrega com payload de exemplo preenchido.
3. **Given** um payload de teste enviado, **When** a simulação roda, **Then**
   a página mostra qual regra o capturaria e que time alcançaria antes de
   qualquer gravação (capacidade atual, preservada).
4. **Given** um evento real recebido, **When** a página atualiza, **Then** o
   chip de atividade do receptor reflete a chegada e "para onde foi" abre o
   rastro (o "Where did this go?" atual, com conteúdo).

### User Story 2 - Agendar investigações com ajuda de cron (Priority: P2)

Um operador cria uma investigação recorrente escolhendo preset de frequência
ou cron explícito, com prévia da próxima execução.

**Why this priority**: O formulário atual funciona mas fala "Identifier",
"Cron", "IANA name" sem ajuda prática; o custo de polir é baixo e o ganho de
completude do funil é real.

**Independent Test**: Criar uma agenda com preset e outra com cron manual;
verificar a prévia da próxima execução e o fuso.

**Acceptance Scenarios**:

1. **Given** o formulário de agenda, **When** o operador escolhe frequência,
   **Then** presets legíveis ("toda segunda às 08:00") geram o cron, o campo
   cron permanece editável para quem prefere, e a prévia mostra as três
   próximas execuções no fuso escolhido.
2. **Given** uma agenda criada, **When** a lista exibe, **Then** nome,
   objetivo, frequência legível, próxima execução e habilitada/desabilitada
   aparecem com edição inline do estado.

### User Story 3 - Declarar para onde vão os resultados (Priority: P1)

O operador declara destinos (chat, notificação) escolhendo entre integrações
conectadas; se nenhuma serve, o CTA leva ao catálogo já filtrado.

**Why this priority**: O defeito de CTA confirmado: a aba Destinations manda
conectar "in the catalogue" mas o botão abre o editor de schema. É o exemplo
perfeito do contrato de CTA da fundação aplicado.

**Independent Test**: Sem integração de chat: o CTA aterrissa no catálogo
filtrado. Com uma conectada: declarar o destino e enviar um teste.

**Acceptance Scenarios**:

1. **Given** nenhuma integração capaz de entregar mensagem, **When** a seção
   Destinations abre, **Then** o empty state explica e o CTA "Conectar uma
   integração de chat" leva ao catálogo filtrado pela categoria — nunca ao
   editor de configuração.
2. **Given** uma integração de chat conectada, **When** o operador declara um
   destino, **Then** escolhe a integração e o alvo (canal, rota) e envia uma
   mensagem de teste dali mesmo.

### Edge Cases

- Receptor que nunca recebeu nada vs receptor com falha de autenticação
  recente: chips distintos (silêncio não é erro; assinatura recusada é).
- Cron inválido ou fuso desconhecido: validação inline com exemplo correto.
- Agenda cujo objetivo referencia capacidade que o deployment não tem: aviso
  na criação, não falha na execução.
- Destino cuja integração passa a Failing: o destino aparece degradado com
  link para o painel da credencial.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A página Alert intake DEVE apresentar os receptores como lista
  compacta (nome de exibição, endpoint copiável, chip de atividade), com
  formato, autenticação e teste no detalhe recolhido.
- **FR-002**: A emissão de token de entrega DEVE ser contextual ao receptor
  (a ação existe onde ela é usada), mantendo o registro atual.
- **FR-003**: A simulação de entrega (qual regra captura, que time alcança)
  DEVE ser preservada e acessível do detalhe do receptor.
- **FR-004**: O formulário de agendas DEVE oferecer presets de frequência que
  geram o cron, cron editável, prévia das próximas execuções no fuso, e
  validação inline.
- **FR-005**: A lista de agendas DEVE mostrar frequência legível, próxima
  execução e estado, com habilitar/desabilitar inline.
- **FR-006**: Destinations DEVE listar destinos declarados com estado da
  integração subjacente e teste de envio; o empty state segue o contrato de
  CTA levando ao catálogo filtrado.
- **FR-007**: As duas páginas DEVEM caber em 2 viewports (1080p) com os
  receptores atuais e uma dúzia de agendas; nada de referência expandida por
  padrão.

### Key Entities

- **Receptor**: nome de exibição, endpoint, mecanismo de confiança, atividade
  (último evento, contagem), detalhe de formato.
- **Agenda**: identificador estável, nome, objetivo, cron, fuso, estado,
  próxima execução.
- **Destino**: integração conectada, alvo (canal/rota), estado, último teste.

## Success Criteria *(mandatory)*

- **SC-001**: Conectar um emissor de alertas real usando só a página: menos
  de 5 minutos até o primeiro evento visível (teste com Alertmanager).
- **SC-002**: O CTA de Destinations aterrissa no catálogo filtrado em 100%
  dos casos; o defeito atual (botão para o editor de schema) desaparece.
- **SC-003**: Criar uma agenda válida com preset em menos de 1 minuto, sem
  conhecer sintaxe cron.
- **SC-004**: Altura de cada página ≤ 2 viewports com dados representativos
  (hoje a aba Intake passa de 2 com a referência expandida).

## Assumptions

- Os receptores suportados e seus mecanismos de confiança não mudam; muda a
  apresentação.
- "Continuous observation" (detectores) permanece fora desta página — é
  superfície de leitura/observação, não de configuração de entrada/saída; a
  tela atual de Signals se dissolve nestas duas páginas mais o que a 070
  mapear.
- O rastro "para onde foi" usa o mecanismo de transit existente.

## Dependencies

- 010 (subnav Dados), 001 (vocabulário, CTA), 020 (catálogo filtrado por
  categoria como destino de CTA).
- A 070 depende desta para aposentar os grupos de schema de transit e
  observação correspondentes.
