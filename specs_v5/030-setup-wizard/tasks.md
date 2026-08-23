# Tasks: Setup como wizard com contagem única

**Input**: Design documents from `specs_v5/030-setup-wizard/`

**Prerequisites**: plan.md, spec.md, specs_v5/001 (fonte única, chips, CTA), specs_v5/010 (wizard fora da sidebar)

**Tests**: test-first (Art. XII).

## Phase 1: Setup

- [x] T001 Fixtures de checklist em três estados (limpo, meio, completo) para
      vitest/Playwright.

## Phase 2: Foundational

- [x] T002 Teste de contrato estendido em
      `tests/contract/console/test_console_first_run.py`: o wizard consome
      exclusivamente a fonte única de progresso; passos como dados do payload —
      falhando primeiro.
- [x] T003 Modelo de passos derivado do checklist em
      `console/src/surfaces/first-run/plan.ts` (id, nome de exibição,
      bloqueante, onde-completa) + teste vitest. **Esse módulo já existe e já é
      o modelo de passos**: `WIZARD_STEPS` (plan.ts:24) declara exatamente os
      sete passos do mockup-4 — provider, credential, model, integrations,
      verify, estate, alerts — e `planFor` (plan.ts:222) já resolve
      feito/atual/href. Estenda-o com o que falta (nome de exibição,
      bloqueante, onde-completa); **não crie um `steps.ts` ao lado**, porque um
      segundo modelo de passos é exatamente a fonte dupla que esta feature
      existe para matar.

## Phase 3: User Story 1 — Stepper com começo, meio e fim (P1)

- [x] T004 [US1] Teste behaviour `console/tests/e2e/setup-wizard.spec.ts`: stepper
      mostra 7 passos com estados corretos nas três fixtures; "Passo N de 7";
      passo externo navega com retorno e volta marcado — falhando primeiro.
- [x] T005 [US1] Implementar o stepper e o corpo dos passos internos conforme
      mockup-4, substituindo os três painéis atuais de
      `console/src/surfaces/screens/first-run.tsx`.
- [x] T006 [US1] Banner de retorno ("Continuar o setup") nas telas de destino
      externas enquanto o checklist estiver incompleto (Resources, Alert
      intake atual) + teste.

## Phase 4: User Story 2 — Verificação acionável (P1)

- [x] T007 [US2] Teste behaviour: item nunca testado lê "Stored"; falha exibe
      diagnóstico ≤ 2 frases + ação nomeada cujo href aterrissa no campo
      de correção; re-teste oferecido ao voltar — falhando primeiro
      (reproduz o caso real: gemini-2.5-flash sem tool calling).
- [x] T008 [US2] Implementar o passo de verificação com chips canônicos, teste
      individual, expansão do diagnóstico completo e CTA de correção
      (destino transitório: telas atuais; final: 040).
- [x] T009 [US2] "Continuar mesmo assim" para falhas não bloqueantes;
      bloqueio declarado por passo (sem provider ⇒ bloqueante) + teste.

## Phase 5: User Story 3 — O wizard some (P2)

- [x] T010 [US3] Teste: checklist completo ⇒ rota redireciona ao dashboard e
      convite some; passo desfeito ⇒ convite volta apontando o passo.
- [x] T011 [US3] Implementar conclusão (resumo com nomes de exibição) +
      redirecionamento; convite do dashboard consome a fonte única.

## Phase 6: Polish

- [x] T012 Edge: gateway indisponível no meio do wizard degrada com erro
      nomeado preservando progresso (teste com fixture de erro).
- [x] T013 Varredura de vocabulário da 001 passa no wizard; `make verify` +
      suítes do console; `controle.md`.

## Dependencies

- T002→T003 bloqueia tudo; T004→T005→T006; T007→T008→T009; T010→T011.
- US1 e US2 paralelizáveis após Fase 2; US3 após US1.
