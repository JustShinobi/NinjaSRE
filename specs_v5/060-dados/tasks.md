# Tasks: Dados — Alert intake, Schedules & destinations

**Input**: Design documents from `specs_v5/060-dados/`

**Prerequisites**: plan.md, spec.md, specs_v5/001, 010 e 020 entregues

**Tests**: test-first (Art. XII).

## Phase 1: Setup

- [ ] T001 Fixtures: receptores (nunca recebeu / recebendo / assinatura
      recusada), agendas (preset e cron manual), destinos (com e sem
      integração de chat conectada).

## Phase 2: User Story 1 — Alert intake acionável (P1)

- [ ] T002 [US1] Teste behaviour `console/tests/e2e/settings-data.spec.ts`: lista de
      receptores com endpoint copiável e chip de atividade; silêncio ≠ erro de
      autenticação; detalhe recolhido com formato/confiança/teste; token de
      entrega contextual — falhando primeiro.
- [ ] T003 [US1] Implementar `console/src/surfaces/settings/alert-intake.tsx`
      com Reference (001) para o detalhe técnico, absorvendo a aba Intake.
- [ ] T004 [US1] Preservar a simulação ("qual regra captura, que time
      alcança") acessível do detalhe; rastro "para onde foi" com conteúdo
      real (teste com evento de fixture).

## Phase 3: User Story 2 — Agendas com presets (P2)

- [ ] T005 [P] [US2] Testes (vitest) do gerador de cron por preset e da
      prévia de próximas execuções por fuso; validação inline com exemplo —
      falhando primeiro.
- [ ] T006 [US2] Implementar a seção de agendas em
      `console/src/surfaces/settings/schedules.tsx`: lista com frequência
      legível, próxima execução, estado inline; formulário com presets +
      cron editável.

## Phase 4: User Story 3 — Destinos com CTA correto (P1)

- [ ] T007 [US3] Teste behaviour de reprodução: o CTA atual de Destinations
      aterrissa no editor de schema — registrado como defeito; teste novo
      exige aterrissagem em `/integrations?category=chat` com o filtro ativo —
      falhando primeiro.
- [ ] T008 [US3] Implementar a seção de destinos na mesma página: declarar
      destino sobre integração conectada (canal/rota), mensagem de teste,
      degradação visível quando a integração está Failing; EmptyState (001)
      com o destino do contrato.

## Phase 5: Polish

- [ ] T009 Dissolução final: `screens/signals.tsx` removida; subnav aponta
      para as duas páginas; redirects da 010 cobrem `?tab=` de Signals.
- [ ] T010 Altura ≤ 2 viewports com fixtures (scroll-budget.spec); varredura
      de vocabulário; `make verify` + suítes; `controle.md`; insumo de
      paridade para a 070 (grupos transit/observation tocados).

## Dependencies

- US1, US2, US3 paralelizáveis após T001; T009 por último.
- T007 depende do filtro por categoria da 020 estar navegável por URL.
