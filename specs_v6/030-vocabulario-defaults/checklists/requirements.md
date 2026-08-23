# Specification Quality Checklist: Vocabulário sem cru e defaults seguros de token

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

## Cobertura do briefing (específico desta feature)

Cada vazamento enumerado no briefing tem FR próprio, com a tela e a string:

- [x] `SERVICE_ACCOUNT` em Members & roles → FR-001
- [x] `HEALTHY` em pessoas → FR-002
- [x] `HEALTHY` em grupos de token → FR-003
- [x] `models.investigator.model` no preview do wizard → FR-004
- [x] Grupos `policies.*` como títulos (Autonomy) → FR-005
- [x] Grupos `surfaces.*` como títulos (Notifications) → FR-006
- [x] "Trusted by webhook.deliver" em Alert intake → FR-007
- [x] `res-8f81848…` nas sugestões do estate → FR-008
- [x] Sessão exibida como "59" → FR-009
- [x] Lista de permissões crua como help text do grant → FR-010
- [x] O caminho técnico permanece disponível em contexto técnico → FR-011
- [x] Default de escopos: nenhum marcado, templates de finalidade, agrupamento
      por domínio, aviso destrutivo → FR-012 a FR-015, FR-017
- [x] Garantia de servidor (token sem escopos explícitos não ganha tudo) →
      FR-016, com teste próprio no tasks.md (T013/T014)
- [x] Members & roles com ação primária de criar pessoa → FR-018, precedida de
      tarefa de descoberta explícita (T001) antes de propor endpoint
- [x] Grants com Role legível → FR-019
- [x] i18n en + pt-BR juntos em toda string → FR-020
- [x] Queda dos `fixme` de vocabulário da suíte transversal → FR-021

## Notas

- **Nenhum marcador [NEEDS CLARIFICATION] restou.** As decisões de escopo da onda
  foram tomadas pelo operador em 2026-08-16 e estão registradas no README e no
  diagnóstico da onda; o briefing desta feature enumera os vazamentos um a um,
  com tela e string, e não deixou ambiguidade que exigisse pergunta.
- **A única incerteza real é de fato, não de escopo**: se o gateway já expõe
  criação de principal com senha local. A spec declara a capacidade exigida
  (FR-018) e a assume resolvida por descoberta, e o tasks.md abre com essa
  descoberta (T001) bloqueando qualquer desenho de rota. Isso é
  deliberadamente uma tarefa e não um marcador de clarificação: a resposta está
  no repositório, não com o operador.
- **Rotas e nomes de tela citados** (`/settings/members-roles`,
  `/settings/machine-tokens`, `/integrations`, `/first-run`) são endereços
  visíveis ao usuário, não detalhe de implementação. As strings citadas
  (`SERVICE_ACCOUNT`, `HEALTHY`, `policies.*`, `webhook.deliver`, `res-…`) são o
  texto que o operador lê hoje na tela — citá-las é o que torna o requisito
  verificável.
- **Duas telas desta feature não têm mockup na v6.** Members & roles e Machine
  tokens são normatizadas pelas regras transversais da v5 e pelo mockup-1 da v5,
  declarado no cabeçalho da spec. Os requisitos que tocam telas com mockup v6
  citam a âncora (`#m2`, `#m3`).
- **Fronteiras declaradas** com 010 (vocabulário de erro do provider), 040
  (rework estrutural de Autonomy) e 001 (corte do catálogo), para que nenhuma
  tarefa desta feature invada o escopo de outra da mesma onda.
