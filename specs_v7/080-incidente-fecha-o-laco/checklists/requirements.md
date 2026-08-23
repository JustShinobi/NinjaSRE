# Specification Quality Checklist: O incidente fecha o laço

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-23
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

## Cobertura das dez estações do laço

Cada estação do cenário virou requisito individual, com evidência exigida e
classificação de desfecho.

- [x] E1 — o alerta dispara sozinho — FR-002, FR-005, FR-006, FR-007
- [x] E2 — a entrega chega autenticada — FR-002, FR-003
- [x] E3 — incidente com título legível e sujeito resolvido — FR-002, FR-039,
      alegações normativas 5 e 9
- [x] E4 — turnos, chamadas, evidência e custo gravados — FR-031, FR-032,
      alegações normativas 2 e 3
- [x] E5 — sentença e documento renderizado — FR-033, alegação normativa 1
- [x] E6 — ferramentas condizentes com o que está conectado — FR-002
- [x] E7 — proposta com plano de reversão aguardando decisão — FR-034,
      alegações normativas 10 e 11
- [x] E8 — aprovação humana, registrada antes de qualquer efeito — FR-013 a
      FR-016, FR-020, FR-035
- [x] E9 — execução pelo gate, desfecho e episódio gravados — FR-017, FR-036,
      FR-037
- [x] E10 — o incidente reflete o desfecho — FR-038, alegação normativa 12

## Cobertura das exigências da onda

- [x] A demo é artefato verificável — FR-021 a FR-029, SC-010, SC-011
- [x] Consultas SQL com resultado anexado — FR-024, FR-030 a FR-040
- [x] Screenshots full-page por estação, 1920×1080 — FR-023, SC-011
- [x] Flakiness de ambiente separada de falha de feature — FR-004, US4 inteira
- [x] Esta feature não conserta funcionalidade — FR-057 a FR-060, seção
      "O que esta feature não faz", SC-014
- [x] Tarefas operacionais verificadas sem serem executadas — FR-041 a FR-046
- [x] Uma tarefa operacional não feita entra no backlog com o estado real —
      FR-045, FR-052
- [x] `backlog.md` reescrito com cada item antigo apontando evidência de
      fechamento — FR-047 a FR-052, SC-012
- [x] Coluna "quem constrói isso em produção?" com `file:line` — FR-053 a
      FR-056, SC-013
- [x] Aprovação humana literalmente humana — FR-013, e a razão escrita no plano
- [x] Remediação reversível de alcance mínimo — FR-018, com a capacidade nomeada
      no plano

## Cobertura dos edge cases exigidos

- [x] Vítima já parada quando a janela abre — edge case declarado, FR-006
- [x] Alerta não dispara na janela — edge case declarado, FR-004, FR-007
- [x] Entrega não chega com alerta disparando — edge case declarado, recortado
      contra a tarefa operacional de resolução de nomes
- [x] Investigação sem evidência suficiente para propor — edge case declarado,
      tratado como desfecho correto e não como falha
- [x] Convidado migrou entre proposta e aprovação — edge case declarado
- [x] Recurso religado à mão antes da decisão — edge case declarado
- [x] Aprovação expirada — edge case declarado
- [x] Execução falha no vendor — edge case declarado, com a distinção entre falha
      nomeada e falha silenciosa
- [x] Argo ainda não reconciliou — edge case declarado, classificado como
      ambiente
- [x] Tarefa operacional não executada — edge case declarado, FR-045, FR-046
- [x] Defeito numa feature já dada como PASS — edge case declarado, FR-057

## Notes

- **Ausência de marcadores de clarificação, com seis decisões abertas.** A spec
  não carrega nenhum `[NEEDS CLARIFICATION]` e, ainda assim, tem uma seção de
  decisões do operador. Elas não são lacunas de especificação: são decisões que
  **pertencem** ao operador e cuja resposta só existe com o ambiente na frente —
  a vítima, o privilégio do token do Proxmox, a janela, a ocorrência da
  rejeição, o destino das tarefas operacionais, e o gasto de ciclo de reparo. A
  spec declara o comportamento exigido em cada ramo das respostas possíveis, que
  é o que a torna implementável sem elas.
- **Por que não há mockup nem tela nova.** Esta feature não desenha nada: as
  telas que a demo fotografa são das features donas (010, 020, 030), e as
  alegações normativas listadas na spec são **as delas**, reexecutadas contra
  staging com dado real. Um mockup aqui descreveria uma tela que outra feature já
  entregou, e criaria uma segunda fonte de verdade sobre ela.
- **Por que não há acceptance spec própria.** O artefato desta feature é o
  roteiro assistido mais a evidência; a metade automatizável já existe nos
  acceptance das features donas, e a tarefa é apontá-los para a URL real. Criar
  um acceptance novo aqui duplicaria a alegação e deslocaria a dona.
- **O test-first desta feature é o gabarito antes da execução.** O roteiro e a
  tabela de evidência vazia aterrissam antes da demo, e o coletor roda a seco
  contra o staging pré-demo devolvendo os valores de partida — que é o vermelho
  confirmado e registrado. Uma consulta que já devolvesse verde antes da demo
  não estaria medindo o laço, e a tarefa manda corrigi-la antes de seguir.
- **Fatos de infra citados como pré-condição, não re-derivados.** Endereços,
  namespace, banco, regras de alerta que disparam, a inexistência de regra
  genérica para "um LXC parou", a vítima que satisfaz descartável **e**
  observada, e o fato de as vítimas do plano anterior não servirem. A
  implementação os **reconfere no instante em que os usa** — a spec dá isso como
  tarefa, não como suposição.
- **Dois roteiros, de propósito.** O laço de leitura prova repetibilidade e é
  reexecutável por um verificador independente; o laço inteiro prova a única
  coisa que nenhuma automação prova por construção — que uma pessoa olhou uma
  proposta e decidiu. Uma aprovação por chamada de API é uma aprovação que o
  produto poderia ter dado a si mesmo.
- **Escrita no estate, e por que ela é aceitável.** A demo executa exatamente uma
  ação de escrita: religar um convidado que ela mesma parou, reversível, sobre um
  único recurso, aprovada por uma pessoa, com plano de reversão registrado antes.
  A reversão manual é independente do produto e vale a qualquer instante.
- **A leitura direta ao banco é instrumento de verificação, não caminho de
  produto.** As consultas vivem numa ferramenta de repositório, são todas
  `SELECT`, e o coletor recusa qualquer outra coisa. Nenhum código de produto
  ganha SQL fora da camada de persistência.
- **`backlog.md` é o único arquivo committed que esta feature reescreve**, e por
  isso a redação obedece à regra de que um arquivo committed não depende de um
  que não é: sem caminho de planejamento, sem número de feature, sem
  identificador de requisito, sem artigo de constituição, sem nome de projeto de
  origem. A evidência de fechamento de cada item vive no confronto da onda, e o
  backlog não aponta para lá.
- **Roteiros e evidência não são committed.** Vivem no diretório desta feature.
  Nada committed aponta para eles.
- **O risco maior desta feature é fazer trabalho alheio**, e é por isso que a
  fronteira aparece antes dos requisitos em vez de no fim, e que "esta feature
  consertou funcionalidade de produto" está na lista do que a reprova.
