# Feature Specification: Setup como wizard com contagem única

**Feature Branch**: `feat/v5-030-setup-wizard`

**Created**: 2026-08-14

**Status**: Draft

**Input**: User description: "O checklist de first-run vira um wizard com stepper, fonte única de contagem de passos, verificações com correção acionável (deep link ao campo que resolve), e 'continuar mesmo assim' para quem quer explorar."

**Referência visual (DoD)**: [../mockups/settings-v5.html#mockup-4](../mockups/settings-v5.html#mockup-4) — stepper de sete passos, chips canônicos por verificação, falha com correção nomeada, "Continuar mesmo assim".

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Um caminho com começo, meio e fim (Priority: P1)

Um operador configurando um deployment novo percorre um stepper com os sete
passos, sempre sabendo onde está, o que falta e qual o próximo gesto.

**Why this priority**: O Setup atual mostra três painéis com o mesmo estado em
vocabulários diferentes ("2 of 7 steps left", "stored, unchecked",
"it answered") e passos que "continuam em" outras telas sem trilha de volta. É
a primeira impressão do produto, e hoje ela ensina que o produto é confuso.

**Independent Test**: Completar um setup do zero num deployment limpo, medindo
desvios de rota e retornos manuais ao wizard.

**Acceptance Scenarios**:

1. **Given** um deployment novo, **When** o operador abre o wizard, **Then**
   vê o stepper com os sete passos, os concluídos marcados, o atual destacado
   e um subtítulo "Passo N de 7 — <nome>".
2. **Given** um passo que se completa em outra tela (estate em Resources,
   alertas em Alert intake), **When** o operador o conclui lá, **Then** ao
   voltar ao wizard o passo está marcado — e a tela de destino ofereceu o
   caminho de volta ("Continuar o setup").
3. **Given** qualquer superfície que cite o progresso (dashboard, empty
   states), **When** exibida junto do wizard, **Then** todas mostram a mesma
   contagem, servida pela fonte única.

### User Story 2 - Verificação que aponta a correção (Priority: P1)

No passo de verificação, cada conexão testa com um clique e uma falha vem com
diagnóstico curto e uma ação que leva ao campo exato que corrige.

**Why this priority**: O backend já produz diagnóstico excelente (detectou
modelo sem tool calling e disse o que fazer); a UI o apresenta como parágrafo
denso sem link. A distância entre "diagnóstico certo" e "correção a um clique"
é onde o funil trava hoje.

**Independent Test**: Provocar uma falha conhecida (modelo sem tool calling) e
verificar que a correção leva ao campo de modelo e que o re-teste é oferecido
ao voltar.

**Acceptance Scenarios**:

1. **Given** o passo de verificação, **When** a tela abre, **Then** cada item
   (provider de modelo e integrações conectadas) aparece com chip do
   vocabulário canônico e botão de testar; itens nunca testados leem
   "Stored", não "Nobody has checked this one".
2. **Given** uma verificação reprovada, **When** o resultado aparece, **Then**
   traz uma frase de diagnóstico e a ação nomeada ("Escolher outro modelo →")
   que aterrissa no campo que resolve, conforme o contrato de CTA.
3. **Given** uma verificação aprovada, **When** o resultado aparece, **Then**
   o chip vira "Verified" com o tempo de resposta.
4. **Given** falhas pendentes, **When** o operador quer seguir, **Then**
   "Continuar mesmo assim" está disponível, com a pendência anotada no
   dashboard.

### User Story 3 - O wizard some quando termina (Priority: P2)

Ao concluir o último passo, o wizard celebra brevemente, resume o que ficou
configurado e leva ao dashboard; a partir daí só é alcançável se houver algo
pendente.

**Independent Test**: Concluir o setup e verificar os pontos de entrada.

**Acceptance Scenarios**:

1. **Given** o último passo concluído, **When** o wizard fecha, **Then** o
   operador está no dashboard sem o convite de setup, e a rota do wizard
   passa a redirecionar ao dashboard.
2. **Given** um passo desfeito depois (credencial removida), **When** o
   dashboard recalcula, **Then** o convite reaparece apontando o passo
   pendente específico.

### Edge Cases

- Gateway indisponível no meio do wizard: o passo atual degrada com erro
  nomeado e o stepper preserva o progresso já persistido.
- Dois operadores no wizard ao mesmo tempo: o progresso é do deployment, não
  da sessão; o segundo vê os passos que o primeiro concluiu.
- Ids crus no resumo ("google_gemini"): o wizard usa nomes de exibição em
  todo o texto, conforme a fundação.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O wizard DEVE apresentar os sete passos existentes num stepper
  com estado por passo (concluído, atual, pendente) e navegação para trás.
- **FR-002**: A contagem e o estado dos passos DEVEM vir exclusivamente da
  fonte única de progresso; o wizard não recalcula nem armazena contagem
  própria.
- **FR-003**: Passos que se completam em outras telas DEVEM levar à tela com
  um parâmetro de retorno, e a tela de destino DEVE oferecer o retorno ao
  wizard enquanto o setup estiver incompleto.
- **FR-004**: O passo de verificação DEVE listar cada item verificável com
  chip canônico, ação de teste individual e re-teste após correção.
- **FR-005**: Toda falha de verificação DEVE exibir diagnóstico de até duas
  frases e uma ação que aterrissa no campo que corrige (contrato de CTA);
  o diagnóstico completo permanece acessível em expansão.
- **FR-006**: "Continuar mesmo assim" DEVE existir para falhas não
  bloqueantes; o que é bloqueante (sem provider de modelo, por exemplo) é
  declarado por passo.
- **FR-007**: A conclusão DEVE resumir o que ficou configurado (nomes de
  exibição, estados) e encerrar no dashboard; a rota passa a redirecionar.
- **FR-008**: Os três painéis da tela atual (What is left / What is set up so
  far / Check that each of them works) DEVEM ser substituídos pelo wizard —
  nenhum estado duplicado permanece.

### Key Entities

- **Passo de setup**: id, nome de exibição, estado, bloqueante ou não, tela
  de conclusão (própria do wizard ou externa com retorno).
- **Item de verificação**: alvo (provider ou integração), estado canônico,
  diagnóstico, ação de correção (destino do contrato de CTA).

## Success Criteria *(mandatory)*

- **SC-001**: Um operador novo completa o setup de um deployment limpo sem
  abandonar o funil (teste de usabilidade; hoje o funil exige recomposição
  manual entre três telas).
- **SC-002**: Uma única contagem de progresso aparece em todas as superfícies
  em qualquer estado do deployment (hoje: "2 of 7" e "3 outstanding"
  simultâneos).
- **SC-003**: Da falha de verificação à tela de correção: um clique; do
  retorno ao re-teste: um clique.
- **SC-004**: Zero vocabulário fora do canônico no wizard.

## Assumptions

- Os sete passos atuais permanecem os mesmos em conteúdo e ordem; esta spec
  muda a apresentação e a fonte de verdade, não o funil.
- A rota do wizard fica fora da sidebar (decisão da 010); o convite no
  dashboard é o ponto de entrada primário.
- A fonte única de progresso é a entregue pela 001 (FR-007).

## Dependencies

- 001 (vocabulário, contrato de CTA, fonte única de contagem).
- 010 (wizard fora da sidebar; redirecionamentos).
- 040 fornece o destino da correção de modelo (Models & providers).
