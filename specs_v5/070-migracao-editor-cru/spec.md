# Feature Specification: Aposentadoria do editor de configuração cru

**Feature Branch**: `feat/v5-070-migracao-editor-cru`

**Created**: 2026-08-14

**Status**: Draft

**Input**: User description: "Substituir 100% o editor de schema de /configuration por telas humanas, com paridade total verificável: todo grupo do schema tem exatamente uma tela dona, o preview de resolução é preservado como componente compartilhado, e a rota antiga redireciona por seção. Decisão do operador: sem escape hatch."

**Referência visual (DoD)**: [../mockups/settings-v5.html#mockup-1](../mockups/settings-v5.html#mockup-1) — a subnav final não tem grupo "Advanced" nem editor cru: a ausência é parte do DoD. O padrão "valor efetivo + origem + prévia de resolução" aparece nos formulários dos mockups 1 e 4.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Nenhuma configuração órfã (Priority: P1)

Tudo que era configurável pelo editor cru continua configurável — agora em
exatamente uma tela humana. Nenhum campo perde o seu único lugar de edição.

**Why this priority**: A decisão "matar o editor cru" só é segura se a
paridade for um fato verificado, não uma intenção. Um campo órfão é uma
regressão de capacidade que ninguém percebe até precisar dele.

**Independent Test**: Percorrer o inventário completo dos grupos do schema
(38 hoje) e confirmar que cada campo tem tela dona declarada e funcional.

**Acceptance Scenarios**:

1. **Given** o inventário de grupos do schema, **When** a migração é dada por
   completa, **Then** cada grupo consta do mapa grupo → tela dona, e cada
   campo é editável na tela declarada.
2. **Given** um campo novo adicionado ao schema no futuro, **When** ele não
   tem tela dona declarada, **Then** a verificação automática de paridade
   falha — a ausência é um defeito de build, não uma descoberta de usuário.
3. **Given** o mapa de paridade, **When** um grupo é intrinsecamente técnico
   e raro (ex.: claims de SSO com nomes fora do padrão), **Then** sua tela
   dona pode expô-lo numa seção avançada recolhida da página humana — dentro
   da página dona, nunca num editor genérico ressuscitado.

### User Story 2 - Prévia de resolução onde a edição acontece (Priority: P1)

Antes de aplicar qualquer mudança de configuração, o operador vê o que a
gravação resolve — o valor efetivo resultante e em que escopo — na própria
tela onde edita.

**Why this priority**: O preview do editor atual ("see what saving would
resolve to") é a sua única virtude, e é exatamente o que as telas humanas não
podem perder ao substituí-lo: a hierarquia de resolução continua existindo
por baixo.

**Independent Test**: Editar um valor em três telas donas diferentes e
conferir que a prévia mostra o resultado resolvido antes de aplicar.

**Acceptance Scenarios**:

1. **Given** uma mudança pendente em qualquer tela dona, **When** o operador
   pede para salvar, **Then** vê a prévia da resolução (valor efetivo, escopo
   de origem) e confirma ou ajusta.
2. **Given** um valor herdado do default, **When** exibido em qualquer tela
   dona, **Then** a origem ("default do deployment" / "definido aqui") está
   visível, como o editor atual faz com "Set at: default".

### User Story 3 - A rota antiga encontra a tela nova (Priority: P2)

Quem abre `/configuration` — ou um link antigo para um grupo específico —
aterrissa na tela dona daquele grupo.

**Independent Test**: Tabela seção → destino percorrida por teste de deep
link.

**Acceptance Scenarios**:

1. **Given** `/configuration`, **When** aberto após a migração, **Then**
   redireciona para a página inicial de Settings.
2. **Given** um link com âncora/parâmetro de grupo (ex.: o grupo de
   autonomia), **When** aberto, **Then** redireciona para a tela dona com a
   seção correspondente em foco.

### Edge Cases

- Migração parcial (entre a entrega de 040/050/060 e esta): o editor cru
  continua servindo apenas os grupos ainda sem dona; grupos migrados exibem
  nele um aviso com link para a tela dona — estágio transitório declarado,
  com data de morte.
- Configuração gravada por API/CLI continua possível; esta spec governa a
  superfície do console, não o serviço de configuração.
- Valor inválido gravado por fora (API) num campo agora dono de tela humana:
  a tela exibe o valor com aviso de validação, sem quebrar.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: DEVE existir um mapa completo grupo-do-schema → tela dona,
  mantido junto ao schema, cobrindo 100% dos grupos e campos.
- **FR-002**: Uma verificação automática de paridade DEVE falhar quando
  qualquer campo do schema não tem tela dona declarada (no espírito dos guard
  checks existentes do repositório).
- **FR-003**: A prévia de resolução DEVE virar componente compartilhado usado
  por todas as telas donas antes de aplicar mudanças.
- **FR-004**: A exibição de origem do valor efetivo (default vs definido no
  escopo) DEVE existir em toda tela dona, preservando a semântica da
  hierarquia de configuração.
- **FR-005**: O editor cru DEVE ser removido do console ao fim da migração;
  `/configuration` e variantes redirecionam conforme a tabela seção→destino.
- **FR-006**: Durante a transição, grupos já migrados DEVEM apontar do editor
  para a tela dona; a ordem de migração segue as entregas de 040, 050 e 060.
- **FR-007**: Grupos sem página própria óbvia DEVEM ser alocados
  explicitamente no mapa (nenhum "resto"): capacidades por time,
  mudanças/git host, memória e conhecimento, observação/bridge, superfícies
  e console — cada um com dona nomeada no mapa, ainda que como seção avançada
  recolhida de uma página existente.

### Key Entities

- **Mapa de paridade**: grupo do schema, campos, tela dona, seção (principal
  ou avançada), estado de migração.
- **Prévia de resolução**: mudança pendente → valor efetivo resultante por
  escopo, origem.

## Success Criteria *(mandatory)*

- **SC-001**: 100% dos grupos e campos do schema têm tela dona funcional; a
  verificação de paridade passa e é executada pelo gate padrão do repositório.
- **SC-002**: O console não contém mais nenhum CTA, rota ativa ou tela que
  exponha o editor de schema genérico.
- **SC-003**: Toda mudança de configuração feita pelo console passa pela
  prévia de resolução (inventário das telas donas auditado).
- **SC-004**: Deep links antigos para `/configuration` aterrissam no destino
  correto em 100% da tabela de redirecionamento.

## Assumptions

- O serviço hierárquico de configuração e sua API não mudam; muda apenas a
  superfície de edição no console.
- O inventário de 38 grupos observado em 2026-08-14 é o ponto de partida; o
  mapa de paridade é vivo e acompanha o schema.
- A alocação fina dos grupos "restantes" (capacidades, mudanças, memória,
  conhecimento, observação, superfícies) é decidida no plano desta feature,
  com a regra do FR-007: toda alocação é explícita e nomeada.

## Dependencies

- 040, 050, 060 (as telas donas dos domínios principais).
- 010 (redirecionamentos e subnav).
- 001 (prévia e origem seguem o vocabulário e os contratos da fundação).
