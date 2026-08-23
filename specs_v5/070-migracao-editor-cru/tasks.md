# Tasks: Aposentadoria do editor de configuração cru

**Input**: Design documents from `specs_v5/070-migracao-editor-cru/`

**Prerequisites**: plan.md, spec.md, specs_v5/040, 050 e 060 entregues (donas dos domínios principais)

**Tests**: test-first (Art. XII); o guard check de paridade nasce falhando.

## Phase 1: Foundational — mapa e guard check

- [x] T001 Corrigir o mapa de paridade que já existe em
      `console/src/shell/config-ownership.ts`: três categorias (com dona /
      campo de máquina / sem controle-por-tipo), os 24 campos de `models.*` e
      `policies.sso.*` movidos para "com dona", `page` aceitando qualquer
      área declarada (`declared_areas()`), não só as nove páginas Settings.
      O mapa continua no console (briefing §1.6 revoga "junto ao schema" do
      plano) — ver `controle.md`.
- [x] T002 Guard check `check-config-parity` no Makefile: falha quando um
      campo do schema não tem dona declarada — confirmado FALHANDO no estado
      atual (47 campos editáveis ainda sem controle), ligado ao `make verify`.
- [ ] T003 Deliberadamente não construído — ver `controle.md` (briefing §1.6:
      id de tela é conhecimento do console, um mapa no backend nomeando
      página do console inverteria a tabela de tiers).

## Phase 2: User Story 2 — Prévia como componente formal (P1)

- [x] T004 Promovido `resolution-preview` (040) de
      `console/src/surfaces/settings/resolution-preview.tsx` para
      `console/src/design/resolution-preview.tsx`, teste movido junto; os
      três importadores reais (`models-editor.tsx`, `notifications.tsx`,
      `autonomy.tsx`, todos 040) migrados para o import novo — 050 e 060 não
      importavam este módulo.
- [ ] T005 Não construído nesta entrega — fora da lista concreta que a
      delegação desta parte fechou; ver `controle.md`.

## Phase 3: User Story 1 — Nenhum campo órfão (P1)

- [ ] T006 Seções avançadas recolhidas nas donas alocadas para os grupos
      restantes (The agent, Knowledge, Alert intake), com o padrão
      valor-efetivo + origem + prévia; uma task por dona:
      - [ ] T006a The agent — `agents.*`, `capabilities`
      - [ ] T006b Knowledge — `policies.changes*`, `policies.memory`,
            `policies.strategy`, `policies.knowledge`
      - [ ] T006c Alert intake — `policies.observation*`
      - [ ] T006d Notifications/Schedules — `surfaces.channels`,
            `surfaces.report_destinations`, `surfaces.notification_sinks`,
            `surfaces.enabled` e `transit` (060); `surfaces.notification_policy`
            já é da 040; `surfaces.console.tutorial_dismissed` é declarado no
            mapa como campo de máquina (dona: o console, sem formulário)
- [ ] T007 Durante a transição: grupos migrados exibem no editor cru o aviso
      com link para a dona (teste behaviour); editor serve apenas grupos sem
      dona.
- [ ] T008 `check-config-parity` VERDE: todo campo com dona funcional.

## Phase 4: User Story 3 — Redirecionamento e remoção (P2)

- [ ] T009 Tabela seção→destino para `/configuration` (âncora/parâmetro de
      grupo → tela dona com seção em foco); teste de deep link falhando
      primeiro.
- [ ] T010 Remover `console/src/surfaces/screens/configuration.tsx` e a rota;
      ativar os redirects; teste Playwright: nenhum CTA, rota ou tela expõe o
      editor genérico (varredura).

## Phase 5: Polish

- [ ] T011 Edge: valor inválido gravado via API aparece na dona com aviso de
      validação (fixture + teste).
- [ ] T012 `make verify` completo (com o guard novo), suítes do console,
      atualização do `controle.md` e do README da onda (estado: editor
      removido em <data>).

## Dependencies

- T001→T002→T003 bloqueia tudo; T004→T005; T006*→T007→T008; T008→T009→T010.
- T006a–T006d paralelizáveis entre si.
