# Tasks: Fundação de vocabulário e contratos de UX

**Input**: Design documents from `specs_v5/001-fundacao-vocabulario-ux/`

**Prerequisites**: plan.md, spec.md

**Tests**: test-first é regra do repositório (Constituição Art. XII): o teste
que falha entra antes da implementação, e a falha é confirmada.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [x] T001 Declarar constantes da fundação em `config/constants/surfaces.py`:
      orçamento de rolagem (viewports de referência 1920×1080) e o conjunto
      canônico de estados; exportar via `config/constants/__init__` conforme o
      guard `check-constants`.

## Phase 2: Foundational

- [x] T002 [P] Teste (vitest) do módulo de estados: só os cinco estados
      canônicos existem, cada um com chave i18n e cor semântica —
      `console/tests/unit/design/status.test.ts` falhando primeiro. **O arquivo
      já existe**: estenda-o com os casos novos e confirme o vermelho deles,
      não o substitua.
- [x] T003 Estender `console/src/design/status.ts` com o vocabulário canônico
      {not_connected, stored, verified, failing, unknown} e o componente
      `StatusChip` único; migrar consumidores existentes.
- [x] T004 [P] Chaves i18n dos estados e verbos de CTA em `console/src/i18n/en.ts`.

## Phase 3: User Story 1 — Um estado, uma palavra (P1)

- [x] T005 [US1] Teste de varredura (Playwright behaviour) que abre as telas de
      configuração e falha ao encontrar vocabulário proibido ("HEALTHY",
      "it answered", "stored, unchecked", "UNCONFIGURED", "Nobody has checked") —
      `console/tests/e2e/vocabulary.spec.ts`, confirmado falhando contra o console atual.
- [x] T006 [US1] Substituir todo texto de estado por `StatusChip` nas telas
      atuais que exibem credencial/verificação (integrations, first-run,
      administration), até T005 passar.

## Phase 4: User Story 2 — Nomes de gente (P1)

- [x] T007 [P] [US2] Teste de contrato: todo item servido pelo catálogo de
      integrações carrega `display_name` e `category` não vazios —
      `tests/contract/console/test_console_display_registry.py`, falhando primeiro.
- [x] T008 [US2] Adicionar `display_name` ao payload do catálogo no gateway
      (`gateway/http/routes/integrations.py` e origem no catálogo de
      integrações); regenerar o client (`pnpm client`).
      **Onde a origem mora, e por quê.** O nome de exibição é declarado em
      `IntegrationProfile` (`integrations/_catalogue/entry.py:80`), no pacote do
      próprio vendor, ao lado do `DESCRIPTOR` — **não** num mapa central. A
      razão está escrita no módulo: o catálogo é montado caminhando na árvore,
      e "adicionar uma integração edita zero arquivos existentes"; um mapa
      central `id → nome` é exatamente o arquivo central que esse desenho
      existe para não ter. Daí ele sobe por `CatalogueEntry.to_record()`
      (`entry.py:168`) e entra em `IntegrationView`
      (`gateway/http/routes/integrations.py:117`), que hoje serve `name`,
      `category` e `summary` e **não** serve `display_name`.
      `KnownGapView` (`integrations.py:101`) já serve `display_name` — é o
      precedente do formato, não uma segunda fonte.
      Os providers de modelo já têm o seu: `display_name="Google Gemini"` em
      `core/llm/onboarding/gemini.py:11`, e irmãos para anthropic, vertex_ai e
      nvidia_nim.
- [x] T009 [US2] Guard check `check-display-names` no Makefile: falha quando um
      id de catálogo não tem nome de exibição registrado; ligado ao `make verify`.
      **Prefira a invariante de construção ao guard, quando ela couber**:
      `IntegrationProfile.__post_init__` (`entry.py:100`) já levanta para
      `summary` em branco, com a mensagem dizendo o que o console perde. Um
      `display_name` em branco morre no mesmo lugar, e aí nenhum catálogo
      inválido chega a existir para o guard encontrar. O guard do Makefile
      cobre o que a invariante não alcança — os catálogos que não passam por
      `IntegrationProfile` (providers, modelos, papéis).
- [x] T010 [US2] Console: títulos e labels passam a usar display name; id cru
      só em contexto técnico (mono) — varredura por snake_case em posição de
      título adicionada a `console/tests/e2e/vocabulary.spec.ts`.

## Phase 5: User Story 3 — CTA aterrissa no alvo (P2)

- [x] T011 [P] [US3] Teste (vitest) do componente `EmptyState`: exige destino
      tipado (rota existente no manifesto + âncora/filtro) e verbo; CTA para
      rota fora do manifesto não compila/reprova — `console/tests/unit/design/empty-state.test.tsx`.
- [ ] T012 [US3] Implementar `console/src/design/empty-state.tsx` e migrar os
      empty states existentes das telas de Settings para ele.
- [x] T013 [US3] Inventário executável dos empty states (fixture) verificado em
      `tests/contract/console/test_console_success_criteria.py`: cada CTA
      declara destino que o manifesto de rotas conhece.

## Phase 6: User Story 4 — Referência fora do fluxo (P2)

- [x] T014 [P] [US4] Teste (vitest) do componente `Reference` (recolhido por
      padrão, título + resumo de uma linha visíveis) —
      `console/tests/unit/design/reference.test.tsx`.
- [ ] T015 [US4] Implementar `console/src/design/reference.tsx`; será consumido
      por 020/060 (não migrar telas aqui além de um uso de prova).

## Phase 7: User Story 5 — Contagem única (P2)

- [x] T016 [US5] Teste de contrato: a contagem de progresso vem de um único
      endpoint e o console não a recomputa — asserção sobre o payload e sobre
      os consumidores (`tests/contract/console/test_console_first_run.py`, estender).
- [x] T017 [US5] Consolidar a fonte no gateway (checklist existente) e fazer
      dashboard e first-run consumirem o mesmo valor; remover contagens locais.
      A recomputação local a matar é `remaining()` em
      `console/src/surfaces/first-run/plan.ts:188`
      (`WIZARD_STEPS.filter((step) => !stepDone(step, setup)).length`), e o
      divergente "N step(s) are outstanding" que a aba de observação contínua
      exibe. O endpoint é `GET /v1/setup/checklist`
      (`gateway/http/routes/first_run.py:120`), cuja `ChecklistView` hoje serve
      `complete`, `steps`, `next`, `provider` e `integrations` — mas **não** uma
      contagem. Ou o gateway passa a servi-la, ou o console deriva de `steps` em
      **um** lugar; escolha uma e diga qual no `controle.md`.

## Phase 8: Polish

- [x] T018 Teste Playwright de orçamento de rolagem: telas de configuração com
      fixtures representativas ≤ 2 viewports — `console/tests/e2e/scroll-budget.spec.ts`
      (as telas grandes atuais entram na lista com annotation de "esperado
      falhar até 020/070"; o teste é o instrumento de medição da onda).
      **O viewport global do Playwright é 1440×900, fixo e deliberado**
      (`console/playwright.config.ts`); o orçamento é medido em 1080p, então o
      spec declara o próprio viewport 1920×1080 a partir da constante de T001,
      em vez de herdar 1440×900 e chamar isso de 1080p.
- [x] T019 `make verify` completo (cada componente rodado e confirmado
      individualmente — ver `controle.md`) e atualização do `controle.md` da
      feature.

## Dependencies

- T002→T003→T005/T006; T007→T008→T009/T010; T011→T012→T013; T016→T017.
- Fase 2 bloqueia todas as user stories; US1–US5 são independentes entre si.
