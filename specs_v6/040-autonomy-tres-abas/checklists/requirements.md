# Specification Quality Checklist: Autonomy & guardrails em três abas

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

## Cobertura do mockup (M2) — cada alegação anotada vira requisito

- [x] Callout 1 — uma pergunta por aba, três abas, nenhuma acima de 1.5
      viewport (FR-001, FR-007, e a medição de SC-001)
- [x] Callout 2 — os três parágrafos conceituais saem do topo; cada conceito
      vira uma frase onde é usado; o empty state diz o que o vazio significa e
      aponta a aba certa; fim do CTA que promete outra tela (FR-010 a FR-012,
      FR-016 a FR-018)
- [x] Callout 3 — tabela de guardrails com a coluna de valor preenchida; grupos
      de política deixam de ser título de seção; o nome técnico do campo
      sobrevive só no audit e na API (FR-021 a FR-027)
- [x] Callout 4 — override como painel lateral aberto por botão, não um terço
      permanente da página (FR-038, FR-039, SC-007)
- [x] Subtítulo do mockup ("Node · Posture now") e os quatro campos do painel
      (Name/Level/Reason/Duration) (FR-009, FR-040, FR-041)

## Notes

- **Sobre "no implementation details"**: FR-008 exige que o orçamento por aba
  seja uma constante nomeada num único módulo dono. Isso é uma exigência de
  governança do projeto — todo limite é constante nomeada —, não uma escolha de
  stack, e é o que impede o número de ser reescrito dentro do teste que o mede.
  Mantido deliberadamente no nível de spec.
- Rotas, parâmetros de URL e o viewport de medição (1920×1080) são endereços e
  condições observáveis pelo usuário, não detalhe de implementação — mesma
  leitura que a onda anterior registrou.
- Nenhum marcador [NEEDS CLARIFICATION] restou: o recorte desta feature foi
  fechado no briefing e no diagnóstico, ambos com evidência medida na tela de
  hoje (2026px, 12 células de valor vazias, CTA divergente).
- SC-002, SC-004, SC-005 e SC-006 são contagens contra um estado atual medido,
  então cada um tem numerador e denominador conhecidos antes de a implementação
  começar.
- **Dependência viva**: a coluna de valor preenchida chega como componente da
  020. Se a 020 entregar o componente com contrato diferente do assumido aqui,
  o afetado é o resolvedor de valores (fase 2 do tasks.md), não os requisitos —
  a exigência "a célula nunca fica vazia" independe de quem desenha a tabela.
- **Limite conhecido**: o orçamento de 1.5 viewport é medido contra o dataset
  determinístico da suíte, que não tem a escala de um deployment carregado. A
  spec cobre o caso pela via do comportamento (a lista de regras é a região que
  rola, FR-037), e não pela via da medição — nenhum teste de suíte prova o
  orçamento num nó com centenas de regras.
