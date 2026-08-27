# Tasks: Catálogo de integrações navegável

**Input**: Design documents from `specs_v5/020-integrations-catalogo/`

**Prerequisites**: plan.md, spec.md, specs_v5/001 (StatusChip, EmptyState, Reference, display names)

**Tests**: test-first (Art. XII).

## Phase 1: Setup

- [x] T001 Fixture de catálogo cheio (2 conectadas, 1 sugerida, 1 failing) para
      vitest/Playwright em `console/src/surfaces/screens/__fixtures__/`.
      **O "84" desta spec é observação de 2026-08-14, não constante.** A árvore
      hoje tem **85** (`make verify` → `verify_integrations`: "85 integration(s)
      at full parity"), e a próxima integração faz 86. Nenhum teste e nenhuma
      fixture escreve o total: o número vem do catálogo
      (`integrations/_catalogue/discovery.py:161`, `catalogue()`), e a asserção
      é sobre a relação — "todo item do catálogo aparece", "a altura cabe em 2
      viewports com o catálogo inteiro" — nunca sobre o literal. O mesmo vale
      para o subtítulo "N disponíveis · M conectadas", que conta o que recebeu.

## Phase 2: Foundational — metadado de credencial

- [x] T002 Teste de contrato: cada credencial exigida no payload do catálogo
      carrega label humana, instrução de obtenção e escopo mínimo —
      `tests/contract/console/test_console_surfaces.py` (estender), falhando primeiro.
- [ ] T003 Declarar o metadado por credencial no catálogo das integrações
      (`integrations/_base/`, preenchendo os vendors com credencial hoje
      exigida) e servi-lo em `gateway/http/routes/integrations.py`;
      regenerar o client (`pnpm client`).
      **PARCIAL — ver controle.md.** O mecanismo (declaração, serviço,
      client regenerado) está completo. O preenchimento não está: dos 85
      vendors reais, todos têm ao menos um campo de credencial obrigatório
      (134 no total), e só 1 campo (`slack.token`) recebeu metadado à mão.

## Phase 3: User Story 1 — Conectadas primeiro (P1)

- [x] T004 [US1] Teste Playwright `console/tests/e2e/integrations.spec.ts`: primeira
      dobra contém Connected (com chips canônicos) e Suggested (com evidência
      do estate) acima do catálogo; sem seção vazia — falhando primeiro.
      **Ressalva de honestidade, ver controle.md**: não consegui ver o
      vermelho antes, porque a implementação já estava na árvore quando o
      teste entrou.
- [x] T005 [US1] Reescrever o topo de
      `console/src/surfaces/screens/integrations.tsx`: seções Connected e
      Suggested conforme mockup-2, consumindo `health` e `suggested` do
      payload existente.

## Phase 4: User Story 2 — Busca e grid (P1)

- [x] T006 [P] [US2] Testes (vitest) do filtro: busca por nome/categoria/
      capacidade, chips de categoria e estado, contagens por filtro.
      **Ressalva, ver controle.md**: a busca indexa nome, categoria e
      resumo; não indexa "capacidade" (`capabilities`) — a cláusula não
      está coberta.
- [x] T007 [US2] Grid compacto (nome de exibição, categoria, resumo de uma
      linha) com uma dobra + expansão paginada; linhas de estado redundantes
      removidas.
- [x] T008 [US2] Teste de altura no Playwright: página ≤ 2 viewports com a
      fixture cheia (entra no `console/tests/e2e/scroll-budget.spec.ts` da 001,
      agora devendo passar para esta tela).
- [x] T009 [US2] Empty state de busca sem resultado via `EmptyState` (limpar
      busca + link para referência).

## Phase 5: User Story 3 — Painel de credencial (P2)

- [ ] T010 [US3] Teste behaviour: abrir painel preserva posição/filtros;
      deep link `/integrations/<nome>` abre o painel; fechar restaura —
      falhando primeiro.
      **PARCIAL, ver controle.md.** Filtros: preservados e comprovados.
      Deep link: comprovado. Posição de rolagem ao fechar: medida (1092px
      → 0px) e **não** restaurada — não implementado. Também não vi o
      vermelho antes de escrever o teste, pela mesma razão de T004.
- [x] T011 [US3] Implementar `integration-panel.tsx` + rota
      `console/src/app/(shell)/integrations/[name]/` conforme mockup-3:
      labels, ajuda por campo, escopo mínimo, link de guia.
- [x] T012 [US3] "Salvar e testar" compondo store + verify existentes, com
      resultado em chip canônico e diagnóstico; teste de segurança: nenhum
      valor de credencial ecoado na resposta nem no DOM após salvar.
- [ ] T013 [US3] Teste visual (Playwright `--project=visual`) do catálogo e do
      painel contra o layout do mockup (estrutura, não pixels).
      **PARCIAL, ver controle.md.** `integrations-panel-1440-light` está
      registrada em `console/visual/screens.json` sem baseline commitado; o
      placeholder que o gate fabricou foi apagado (duas vezes — reapareceu
      numa rodada de medição e foi apagado de novo). Falta a captura
      deliberada via `make console-visual-accept`, que não rodei.

## Phase 6: User Story 4 — Referência "not covered" (P3)

- [x] T014 [P] [US4] Página `console/src/app/(shell)/integrations/not-covered/`
      estruturando os `known_gaps` do payload (causa, razão, o que mudaria);
      rodapé do catálogo vira link; teste behaviour do link e da página.
      **Ressalva de honestidade, ver controle.md**: não consegui ver o
      vermelho antes, porque a implementação já estava na árvore quando o
      teste entrou.

## Phase 7: Polish

- [x] T015 Estados edge: Stored aparece em Connected com ação de testar;
      Failing permanece em Connected com diagnóstico (testes vitest).
- [ ] T016 `make verify` + `pnpm test`/`e2e`/`visual` e `controle.md`.
      Em andamento: todas as peças individuais rodaram e têm número real
      (ver controle.md); a rodada agregada de `make verify` está em
      execução no momento em que este arquivo foi editado pela última vez.

## Dependencies

- T002→T003 bloqueia US3 (labels vêm do payload); US1/US2 só dependem da Fase 1.
- T004→T005; T006→T007→T008; T010→T011→T012→T013.
