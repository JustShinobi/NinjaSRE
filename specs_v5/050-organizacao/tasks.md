# Tasks: Organização — Members, SSO, Machine tokens, Audit

**Input**: Design documents from `specs_v5/050-organizacao/`

**Prerequisites**: plan.md, spec.md, specs_v5/001 e 010 entregues

**Tests**: test-first (Art. XII); os defeitos confirmados entram como testes
de reprodução antes de qualquer correção.

## Phase 1: Setup

- [x] T001 Fixtures: principals (pessoa + service account) — já valiam.
      ~15 tokens duplicados do bootstrap — construídos em
      `fixtures/scenarios/populated/tokens.json`. Audit com e sem eventos no
      período — já valia (`populated` tem 8, `empty` tem 0).

## Phase 2: Foundational — defeitos raiz do Audit

- [x] T002 Teste de reprodução (contract/pytest) — vermelho visto
      (`TypeError: FakeAuditRepository.count() got an unexpected keyword
      argument 'action'`).
- [x] T003 Gateway: contagem e lista da mesma consulta; T002 passa.
- [x] T004 Reprodução do "Widen the period" — vermelho visto num teste
      temporário contra o `screens/audit.tsx` de então (apagado depois de
      provar); prova permanente em `console/tests/e2e/settings-org.spec.ts`
      contra o build de produção real.
- [x] T005 Console: alargar período reexecuta a consulta com o novo intervalo;
      confirmado em navegador real.

## Phase 3: User Story 4 — Audit log confiável (P1)

- [x] T006 [US4] Teste behaviour: vermelho visto (`settings-audit.test.tsx`
      rodado antes de `settings/audit.tsx` existir).
- [x] T007 [US4] `console/src/surfaces/settings/audit.tsx` implementado
      (novo módulo, não herdou de `screens/audit.tsx`, que foi removido na
      Fase 7).

## Phase 4: User Story 2 — SSO guiado (P1)

- [x] T008 [US2] Teste escrito (`sso-setup.test.tsx`) — **não test-first**:
      a implementação (`sso-setup.tsx`) foi escrita antes do teste. Ver
      `controle.md` §4.
- [x] T009 [US2] `settings/sso.tsx` + `sso-setup.tsx` implementados como
      fluxo em três etapas sobre as rotas existentes.
- [x] T010 [US2] Teste escrito — comportamento já existia no servidor
      (`set_settings` já audita todo campo mudado); o teste só o torna
      explícito. Ver `controle.md` §4.

## Phase 5: User Story 3 — Machine tokens (P2)

- [x] T011 [US3] Teste de contrato — vermelho visto (`KeyError:
      'superseded'`).
- [x] T012 [US3] Gateway: emissão com substituição por finalidade
      (`platform/identity/tokens.py`, `gateway/http/routes/identity.py`) +
      causa raiz do acúmulo do bootstrap tratada
      (`platform/startup/bootstrap.py`, `gateway/http/asgi.py`).
- [x] T013 [US3] `settings/machine-tokens.tsx` + `machine-token-groups.tsx`
      implementados — **não test-first**: implementação antes do teste. Ver
      `controle.md` §4.

## Phase 6: User Story 1 — Members & roles (P2)

- [x] T014 [P] [US1] Teste behaviour — vermelho visto
      (`settings-members.test.tsx` rodado antes de `settings/members.tsx`
      existir). Confirmação para papel administrativo construída no ciclo de
      reparo (`grants.tsx`'s `requestGrant()`/`ADMINISTRATIVE_ROLES`) — ver
      `controle.md` §1 e §4.
- [x] T015 [US1] `settings/members.tsx` implementado. Guarda de último
      administrador — já existia no gateway, verificado e superficiado no
      console (não reconstruída).

## Phase 7: Polish

- [x] T016 Desmembramento final: `screens/administration.tsx`,
      `screens/audit.tsx` e o `sso.tsx` órfão removidos, com seus testes.
      Subnav e redirects já valiam (obra da 010, verificado).
- [x] T017 As quatro páginas ≤ 2 viewports em 1080p, confirmado em
      `scroll-budget.spec.ts` contra build de produção. Varredura de
      vocabulário limpa. `controle.md` escrito. Insumo de paridade para a
      070 registrado em prosa no `controle.md` (não achei nem criei um
      arquivo de checklist de paridade). **`make verify` completo não foi
      rodado** — não pedido pelas instruções desta entrega, que listam os
      quatro gates do console mais os gates Python relevantes; todos rodados
      e reportados em `controle.md` §2.

## Dependencies

- T002→T003, T004→T005 bloqueiam US4; T011→T012→T013.
- US1, US2, US3, US4 paralelizáveis após a Fase 2; T016 por último.
