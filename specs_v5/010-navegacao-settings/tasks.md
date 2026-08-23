# Tasks: Navegação híbrida e shell de Settings

**Input**: Design documents from `specs_v5/010-navegacao-settings/`

**Prerequisites**: plan.md, spec.md, specs_v5/001 (EmptyState, i18n)

**Tests**: test-first (Art. XII); os testes que enumeram o manifesto são a
rede de segurança central desta feature.

## Phase 1: Setup

- [x] T001 Chaves i18n dos grupos e páginas de Settings em `console/src/i18n/en.ts`.
      Feito também em `pt-BR.ts` (não pedido explicitamente pela task, mas exigido
      pelas regras da onda). Ver `controle.md` §6 — não vi vermelho isolado para
      este item.

## Phase 2: Foundational — manifesto

- [x] T002 Teste (vitest) do manifesto estendido em
      `console/tests/unit/shell/routes.test.ts`: `SettingsPage` enumerada, grupos na
      ordem Organization/Agent/Data, regra de ausência por permissão, grupo
      vazio omitido — falhando primeiro. Vermelho visto genuinamente: 20 failed
      antes da T003.
- [x] T003 Estender `console/src/shell/routes.ts` com as 9 páginas de Settings
      (ids, paths `/settings/*`, permissões copiadas do gateway por nome),
      respeitando o contrato do comentário sobre a regex do teste.
- [x] T004 Atualizar `tests/contract/console/test_console_shell.py` para
      percorrer também as páginas de Settings contra a tabela de rotas do
      gateway — confirmado falhando antes de T003, passando depois. Vermelho
      genuíno visto para o teste pré-existente `test_the_deploy_walk_covers_
      exactly_the_areas_the_console_declares` (consequência da T003); os
      testes novos que eu mesmo escrevi não foram vistos vermelhos antes de
      existir — ver `controle.md` §6.

## Phase 3: User Story 1 — Dois cliques até qualquer configuração (P1)

- [x] T005 [US1] Teste Playwright `console/tests/e2e/settings-nav.spec.ts`: sidebar
      contém exatamente Integrations + Settings no grupo Settings; abrir
      Settings mostra a subnav e a primeira página alcançável; viewer sem
      permissão não vê o grupo — falhando primeiro. Vermelho genuíno visto
      contra navegador real (2 de 11 falhando na primeira execução, por causa
      de `sso.manage` ausente no fixture, não um defeito do código).
- [x] T006 [US1] Criar `console/src/app/(shell)/settings/layout.tsx` com a
      subnav (grupos por intenção, estado ativo, colapso responsivo) conforme
      o mockup-1.
- [x] T007 [US1] Criar as rotas `console/src/app/(shell)/settings/<pagina>/page.tsx`
      renderizando, nesta fase, as telas atuais equivalentes (transição
      declarada no plano). 9 rotas: 4 reaproveitam tela atual (2 telas inteiras
      + 2 corpos exportados), 5 renderizam `EmptyState` declarado — ver
      `controle.md` §2.
- [x] T008 [US1] Reduzir o grupo Settings do `sidebar.tsx` às duas entradas.
      **Sem diff em `sidebar.tsx`** — a redução é inteiramente consequência de
      `visible: () => false` em `routes.ts` mais a lógica pré-existente de
      `groupsFor`. Ver `controle.md` §6.

## Phase 4: User Story 2 — Endereços antigos funcionam (P1)

- [x] T009 [P] [US2] Tabela de redirecionamento antiga→nova como dado testável
      no manifesto; teste de deep link estendido cobrindo variantes com query
      (`?tab=`) — falhando primeiro. Vermelho visto no mesmo lote de 20 falhas
      da T002.
- [x] T010 [US2] Implementar os redirects nas rotas antigas
      (`/autonomy`, `/administration`, `/signals`, `/first-run`;
      `/configuration` permanece ativa até a 070). Vermelho genuíno visto para
      autonomy/administration/signals antes de reescrever os três route files
      (`route-files.test.tsx` acusando "Number of calls: 0").

## Phase 5: User Story 3 — Setup é tarefa (P2)

- [x] T011 [US3] Remover `first-run` do grupo Settings do manifesto; regra
      `visible` migra para o convite do dashboard; rota antiga redireciona
      para o wizard (030) ou dashboard quando completo — testes do manifesto e
      do dashboard atualizados antes. **Implementado como `visible: () =>
      false` incondicional (não remoção do array), porque o próprio
      `FirstRunScreen` resolve `areaFor('first-run')` para seu cabeçalho** — a
      rota continua servida. `SetupHero` (pré-existente, não tocado) já é o
      convite do dashboard. Vermelho visto **depois** da implementação, não
      antes — ver `controle.md` §6, este é o item mais importante dessa lista.

## Phase 6: Polish

- [x] T012 [P] Paleta de comandos e busca indexam as páginas de Settings por
      nome de exibição (`console/src/shell/palette.tsx` + teste).
      **FEITO pelo orquestrador**, depois que o implementer o reportou como não
      iniciado (o relato dele estava correto e foi confirmado: nenhuma função
      derivava `Command`s de `SETTINGS_PAGES`). Test-first com o vermelho visto:
      `console/tests/unit/shell/palette.test.tsx:38` falhou com "no palette
      command reaches /settings/members-roles" antes da implementação.
      `settingsCommands` (`console/src/shell/commands.ts:180`) deriva um comando
      por página alcançável, composto em `commandsFor`. Função nova em vez de
      alargar `navigationCommands`: o teste pré-existente "offers every area the
      viewer may reach, and no other" define aquela função como sendo exatamente
      as áreas, e redefinir contrato testado para caber mais é como um teste
      deixa de significar o que diz. Dois testes novos, um deles a regra de
      ausência por permissão.
- [ ] T013 Breadcrumb Settings → grupo → página via `trailFor` (+ teste).
      **PARCIAL.** Mecanismo (`SettingsPageHeader`, `console/src/shell/area.tsx`)
      funciona para 8 das 9 páginas; `autonomy-guardrails` mantém o cabeçalho
      antigo (gap deliberado, ver `controle.md` §1/FR-008). Sem teste unitário
      dedicado a `SettingsPageHeader` isoladamente — só cobertura indireta via
      e2e e via os testes já existentes de `trailFor`. Ver `controle.md` §4,
      item 3.
- [ ] T014 `make verify` + suíte do console (`pnpm test`, `pnpm e2e`) e
      atualização do `controle.md`. **PARCIAL.** Gates do console rodados e
      verdes (vitest 1985/1985, tsc limpo, `console_gate` lint/typecheck/test
      limpos, `settings-nav.spec.ts` 11/11, `shell.spec.ts` 23/23, demais specs
      `behaviour` 48 passed + 6 skipped nomeados, `first-day` 4/5 com 1 falha
      não atribuída com confiança). `make verify` completo **não foi rodado por
      mim** — é gate do orquestrador, e a regra da rodada final também proibiu
      explicitamente rodar comandos. `controle.md` escrito. Ver `controle.md`
      §9 para a lista completa de gates e resultados reais.

## Dependencies

- T002→T003→T004 bloqueia tudo; T005→T006→T007→T008; T009→T010; T011 após T007.
- US1 e US2 independentes após a Fase 2; T012–T013 após US1.
