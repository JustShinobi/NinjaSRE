# Specification Quality Checklist: O primeiro incidente ponta a ponta

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-16
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Cobertura do mockup M6

Cada alegação normativa da âncora `#m6` virou requisito individual, com a vírgula
tratada como fronteira de requisito.

- [x] Trilha e título da página — FR-026, FR-027
- [x] Os dois chips do cabeçalho — FR-028, FR-029
- [x] Subtítulo com regra, fonte, instante, zona e host — FR-030 a FR-033
- [x] Duas colunas, investigação à esquerda — FR-034
- [x] Cabeçalho da investigação com passos, duração e custo — FR-035 a FR-037
- [x] Ordem dos cinco passos da timeline — FR-038
- [x] Rótulos em monoespaçado e nome do token no recebimento — FR-039, FR-040
- [x] Hipóteses explícitas antes das consultas — FR-041 (registro: FR-018)
- [x] Consulta e resultado em cada evidência — FR-042 (registro: FR-019)
- [x] Diagnóstico em uma frase — FR-043 (registro: FR-020, FR-021)
- [x] Entrega nomeando destinos, em peso reduzido — FR-044
- [x] Hora em cada passo — FR-045
- [x] Cartão de ação proposta com chip de decisão — FR-046
- [x] Frase da ação, blast radius e postura — FR-047 a FR-049
- [x] Exatamente dois controles de decisão — FR-050
- [x] Cartão de trilha de evidências — FR-051
- [x] Regras transversais: vocabulário canônico e orçamento de rolagem — FR-053, FR-054

## Cobertura dos edge cases exigidos

- [x] Rede da zona de infraestrutura para a LAN bloqueada — edge case declarado,
      requisito de tela em FR-010, verificação e fallback nas fases operacionais
- [x] Token revogado — edge case declarado, FR-004 e FR-005
- [x] Alerta duplicado — edge case declarado, FR-008
- [x] Notificação de resolução — edge case declarado, FR-009
- [x] Runtime ausente — edge case declarado, FR-013, FR-015 e FR-052

## Notes

- **Numeração do mockup**: a linha de referência da âncora `#m6` no mockup diz
  "Feature 050". É rótulo obsoleto, herdado da numeração proposta no diagnóstico
  (§6), onde o primeiro incidente era a 050. O índice do README da onda e o
  `progress.json` são a fonte de verdade: esta feature é a **060**, e a 050 é
  Integrations em slide-over com o Alert intake enxuto. A âncora do mockup continua
  correta; só o rótulo textual ficou para trás.
- **Rotas citadas** (`/incidents`, `/incidents/[id]`, o endpoint de entrega do
  Alertmanager) são endereços visíveis ao operador e ao sistema que entrega, não
  detalhe de implementação. Os nomes de módulo e arquivo aparecem apenas no
  `plan.md`, onde são a decisão de estrutura.
- **Ausência de marcadores de clarificação**: as decisões que normalmente exigiriam
  pergunta já foram tomadas pelo operador e registradas no diagnóstico da onda —
  vítimas aprovadas para o cenário destrutivo, runtime como pré-condição de DoD
  desta feature, e postura propose-only de ponta a ponta. As demais lacunas foram
  preenchidas por padrão razoável e estão declaradas em Assumptions.
- **Fatos de infra**: a spec cita como pré-condições verificadas os endereços, o
  401 sem token, o receiver existente do antecessor com `send_resolved` desligado,
  as regras de alerta já ativas e os dois incidentes mortos no dashboard. Nenhum
  deles é re-derivado durante a implementação; o que a implementação faz é
  verificá-los de novo no momento em que os usa.
- **Escopo do trabalho de produto**: a spec afirma que não existe hoje composição de
  runtime alguma no repositório — o único implementador do contrato de investigação
  é o recusador que nomeia o que falta. Isso move "fornecer um runtime" de tarefa de
  deploy para tarefa de produto seguida de deploy, e é a razão de a Fase 4 existir
  antes da Fase 7.
- **Roteiros de cenário**: vivem no diretório desta feature, que não é committed.
  Nenhum arquivo committed aponta para eles, e a evidência de execução vai para o
  `controle.md` da feature.
