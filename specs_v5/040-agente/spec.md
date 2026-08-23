# Feature Specification: Telas do agente — Models & providers, Autonomy & guardrails, Notifications

**Feature Branch**: `feat/v5-040-agente`

**Created**: 2026-08-14

**Status**: Draft

**Input**: User description: "Três páginas humanas no grupo Agente de Settings, substituindo os grupos de schema correspondentes do editor cru: Models & providers (models.*), Autonomy & guardrails (funde a tela Autonomy atual com policies.autonomy/guardrails/masking/approvals), Notifications (surfaces.notification_policy)."

**Referência visual (DoD)**: [../mockups/settings-v5.html#mockup-1](../mockups/settings-v5.html#mockup-1) — a página Models & providers dentro do shell híbrido: formulário humano, chip de credencial, badge de tool calling, "Salvar e verificar", papéis avançados recolhidos.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Escolher provider e modelo sem abrir schema (Priority: P1)

Um operador troca o provider ou o modelo de qualquer papel do agente num
formulário com nomes humanos, estado da credencial inline e verificação como
parte do salvar.

**Why this priority**: Trocar o modelo — a configuração mais consequente do
produto — hoje exige achar `models.investigator` entre 38 acordeões e editar
uma estrutura próxima de JSON. É também a correção apontada pelo diagnóstico
de verificação do Setup ("escolha um modelo com tool calling"), que precisa de
um destino digno.

**Independent Test**: Trocar o modelo do papel investigator e verificar de
ponta a ponta sem tocar no editor cru.

**Acceptance Scenarios**:

1. **Given** a página Models & providers, **When** ela abre, **Then** mostra o
   provider ativo com o estado da credencial (chip canônico), o modelo padrão
   do papel investigator, e os papéis avançados recolhidos ("herdam o padrão").
2. **Given** a lista de modelos do provider, **When** exibida, **Then** cada
   modelo indica se suporta tool calling, e um modelo reprovado em verificação
   anterior carrega essa anotação.
3. **Given** uma troca de modelo, **When** o operador salva, **Then** a
   verificação roda no mesmo gesto e o resultado aparece inline; salvar sem
   verificar existe como ação secundária explícita.
4. **Given** um papel avançado (subagent, intake, diagnose, extraction,
   embedding, selection, summarisation — os papéis além do investigator que o
   schema declara), **When** o operador expande, **Then** pode fixar provider e
   modelo por papel ou devolvê-lo à herança, vendo de onde o valor efetivo vem.

### User Story 2 - Autonomia editável onde ela é explicada (Priority: P1)

A página Autonomy & guardrails é a única dona do domínio: postura, regras por
escopo, janelas de congelamento, tetos de gasto, overrides temporários e os
guardrails (masking, aprovação, detecção de segredo) — com a simulação junto.

**Why this priority**: Hoje a tela Autonomy explica o modelo em prosa e manda
editar no editor cru ("Look at the configuration"), que edita a mesma coisa
por outro caminho. Duas verdades, nenhuma completa — num domínio onde erro
significa ação autônoma indevida ou operador travado.

**Independent Test**: Criar uma regra, um congelamento e um override, e
simular o efeito, tudo na mesma página; confirmar que o editor cru não é
visitado.

**Acceptance Scenarios**:

1. **Given** a página aberta sem política registrada, **When** o empty state
   aparece, **Then** explica o default seguro (propose-only) e oferece "Criar
   a primeira regra" ali mesmo — não um link para outra tela.
2. **Given** o formulário de regra, **When** o operador o preenche, **Then**
   escolhe escopo (deployment → recurso) e nível com descrições humanas, e vê
   a ordem de resolução das regras existentes.
3. **Given** uma mudança pendente, **When** o operador pede simulação,
   **Then** vê o que decidiria diferente antes de salvar (capacidade que a
   tela atual já tem, preservada e hierarquizada como parte do fluxo de
   salvar).
4. **Given** os guardrails (masking, regras de aprovação, tratamento de
   segredo detectado), **When** o operador os edita, **Then** os edita nesta
   página em formulários humanos, e o efeito declarado respeita os invariantes
   constitucionais (aprovação para writes; um match de segredo sempre é
   olhado).
5. **Given** um override ativo, **When** a página abre, **Then** ele aparece
   com nome, razão, expiração e revogação a um clique.

### User Story 3 - Notificações com controles nomeados (Priority: P2)

Uma página Notifications expõe a política de atenção — horários de silêncio,
supressão de repetição, teto por hora — como controles nomeados.

**Why this priority**: A política existe (`surfaces.notification_policy`,
"quanto da atenção do time uma notificação pode tomar"), mas está enterrada
como schema. É o tipo de configuração que todo operador procura e nenhum
encontra.

**Independent Test**: Ajustar silêncio noturno e teto por hora sem tocar no
editor cru.

**Acceptance Scenarios**:

1. **Given** a página Notifications, **When** ela abre, **Then** mostra os
   controles com os valores efetivos e a nota de contrato existente ("cada
   valor aqui só pode tornar o teto da plataforma mais estrito").
2. **Given** um ajuste salvo, **When** a política resolve, **Then** o valor
   efetivo e sua origem (default ou definido aqui) ficam visíveis.

### Edge Cases

- Provider sem credencial: a página de modelos mostra "Not connected" com CTA
  para o painel de credencial do provider (catálogo), e bloqueia a escolha de
  modelo com explicação — não com formulário mudo.
- Regra de autonomia que referencia recurso inexistente: aviso na lista, não
  falha silenciosa.
- Edição concorrente (duas sessões): a segunda gravação informa o conflito e
  mostra o valor atual, sem sobrescrever às cegas.
- Escopo por nó da organização: cada página expõe o seletor de escopo quando
  a hierarquia tem mais de um nó, mostrando de onde o valor efetivo herda.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A página Models & providers DEVE cobrir integralmente o que os
  grupos de schema de modelos e providers permitem hoje (papel padrão e
  papéis avançados, provider por papel, herança), com nomes de exibição.
- **FR-002**: A escolha de modelo DEVE anotar suporte a tool calling e
  verificações reprovadas anteriores; salvar-e-verificar é a ação primária.
- **FR-003**: A página Autonomy & guardrails DEVE absorver a tela Autonomy
  atual (postura, overrides, simulação) e a edição de regras, congelamentos,
  tetos e guardrails — tornando-se a única superfície de edição do domínio.
- **FR-004**: Toda edição de autonomia DEVE preservar os comportamentos de
  segurança vigentes: default propose-only na ausência de regra, override com
  nome/razão/expiração registrados em audit, aprovação humana para writes.
- **FR-005**: A página Notifications DEVE expor a política de notificação
  como controles nomeados com valores efetivos e origem visível.
- **FR-006**: As três páginas DEVEM mostrar, por campo, o valor efetivo e de
  onde ele veio (default do deployment ou definição local), preservando a
  semântica de resolução hierárquica existente.
- **FR-007**: Salvar em qualquer das páginas DEVE oferecer a prévia do que a
  gravação resolve (o "preview this change" atual, reapresentado por página),
  antes de aplicar.
- **FR-008**: Os empty states das três páginas DEVEM seguir o contrato de CTA
  da fundação; nenhum aponta para editor genérico.

### Key Entities

- **Papel de modelo**: nome de exibição, provider, modelo, herança, estado de
  verificação.
- **Regra de autonomia**: escopo, nível, ordem de resolução; **Congelamento**:
  janela, escopo; **Teto**: métrica, limite, intervalo; **Override**: nome,
  nível, razão, expiração.
- **Política de notificação**: silêncio, supressão de repetição, teto/hora.

## Success Criteria *(mandatory)*

- **SC-001**: Trocar o modelo do agente: da abertura de Settings à
  verificação concluída em menos de 1 minuto, sem tocar em schema.
- **SC-002**: Criar regra + congelamento + override e simular o efeito sem
  sair da página Autonomy & guardrails.
- **SC-003**: 100% dos campos dos grupos de schema cobertos por estas páginas
  são editáveis nelas (insumo direto da paridade exigida pela 070).
- **SC-004**: O loop Autonomy → Configuration deixa de existir: nenhum CTA
  destas páginas aponta para o editor cru.

## Assumptions

- A hierarquia de configuração (nós da organização) permanece; o seletor de
  escopo só aparece quando há mais de um nó (hoje: "Default organisation").
- A simulação de autonomia existente ("what would this decide differently")
  é preservada como capacidade, reapresentada dentro do fluxo de edição.
- Guardrails que a constituição fixa (ex.: um match de segredo sempre é
  olhado) aparecem como fatos, não como opções desligáveis.

## Dependencies

- 010 (as páginas vivem na subnav de Settings).
- 001 (vocabulário, CTA, valores efetivos com origem).
- A 070 depende desta para aposentar os grupos de schema correspondentes.
