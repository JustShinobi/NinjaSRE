# Tasks: Telas do agente

**Input**: Design documents from `specs_v5/040-agente/`

**Prerequisites**: plan.md, spec.md, specs_v5/001 e 010 entregues

**Tests**: test-first (Art. XII).

## Phase 1: Setup

- [ ] T001 Fixtures de configuração resolvida (default puro; com definições
      locais; com override ativo) para vitest/Playwright.

## Phase 2: Foundational — prévia e origem

- [ ] T002 Teste (vitest) de `resolution-preview.tsx`: dado um patch, exibe
      valor efetivo resultante + escopo de origem usando a rota de preview
      existente — falhando primeiro.
- [ ] T003 Implementar `console/src/surfaces/settings/resolution-preview.tsx`
      e o hook de edição comum (montar patch → preview → aplicar).
- [ ] T004 Teste de contrato dos payloads de config/preview consumidos pelas
      três páginas em `tests/contract/console/test_console_gate_configuration.py`
      (estender).

## Phase 3: User Story 1 — Models & providers (P1)

- [ ] T005 [US1] Teste behaviour `console/tests/e2e/settings-agent.spec.ts`: página
      mostra provider + chip de credencial, modelo do investigator com badge
      de tool calling, papéis avançados recolhidos com herança visível;
      trocar modelo dispara verificação e exibe resultado inline — falhando
      primeiro.
- [ ] T006 [US1] Implementar `settings/models.tsx` conforme mockup-1
      (formulário, "Salvar e verificar" primário, "Testar sem salvar"
      secundário, anotação de reprovação anterior).
- [ ] T007 [US1] Papéis avançados: fixar/devolver herança por papel, origem
      do valor visível (usa T003).

## Phase 4: User Story 2 — Autonomy & guardrails (P1)

- [ ] T008 [US2] Teste behaviour: empty state cria a primeira regra na
      própria página (nenhum link para editor cru); regra com escopo + nível
      descritos; congelamento e teto criados; override com nome/razão/
      expiração e revogação; simulação como etapa do salvar — falhando
      primeiro.
- [ ] T009 [US2] Implementar `settings/autonomy.tsx` absorvendo a tela atual
      (postura, override, simulate/explain) + formulários de regra,
      congelamento e teto via hook comum.
- [ ] T010 [US2] Guardrails (masking, aprovações, segredo detectado) como
      formulários na mesma página; invariantes constitucionais renderizados
      como fatos (teste assegura que não há toggle para eles).
- [ ] T011 [US2] Teste de conflito de edição concorrente: segunda gravação
      informa e mostra o valor atual (usa o mecanismo da API; fixture).
- [ ] T012 [US2] Remover `console/src/surfaces/screens/autonomy.tsx` e apontar
      a subnav para a página nova; teste de redirect da 010 passa a cobrir o
      destino final.

## Phase 5: User Story 3 — Notifications (P2)

- [ ] T013 [P] [US3] Teste behaviour: controles nomeados (silêncio, supressão,
      teto/hora) com valores efetivos + origem; nota "só pode estreitar o teto
      da plataforma" presente — falhando primeiro.
- [ ] T014 [US3] Implementar `settings/notifications.tsx` sobre
      `surfaces.notification_policy` via hook comum.

## Phase 6: Polish

- [ ] T015 Edge: provider sem credencial bloqueia escolha de modelo com CTA
      ao painel do provider (020); regra órfã de recurso avisa na lista.
- [ ] T016 Varredura de vocabulário (001) passa nas três páginas;
      `make verify` + suítes; `controle.md`; insumo de paridade para a 070
      (lista dos grupos de schema cobertos, anexada ao controle).

## Dependencies

- T002→T003→(T005..T014); T004 em paralelo com T003.
- US1, US2, US3 paralelizáveis após Fase 2; T012 por último em US2.
