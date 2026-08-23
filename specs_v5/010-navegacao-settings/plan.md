# Implementation Plan: Navegação híbrida e shell de Settings

**Branch**: `feat/v5-010-navegacao-settings` | **Date**: 2026-08-14 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v5/010-navegacao-settings/spec.md`

**Referência visual (DoD)**: `specs_v5/mockups/settings-v5.html#mockup-1`

## Summary

A sidebar principal passa a ter, no grupo Settings, só Integrations e
Settings; Settings abre um layout com subnav própria (Organization / Agent /
Data). O manifesto `console/src/shell/routes.ts` continua sendo a única
resposta a "que rotas existem" — ganha a noção de página aninhada de Settings
para que os testes de contrato, permissão e deep link cubram as páginas novas
por construção. Rotas antigas redirecionam; o wizard sai da sidebar.

## Technical Context

**Language/Version**: TypeScript (Next.js 16 App Router, React 19)

**Primary Dependencies**: `console/src/shell/` (routes.ts, sidebar.tsx, shell.tsx, palette.tsx), grupo de rotas `console/src/app/(shell)/`, sistema de permissões do viewer (`console/src/session/viewer.ts`)

**Storage**: N/A

**Testing**: vitest (routes, sidebar), Playwright behaviour (navegação, redirects), pytest `tests/contract/console/test_console_shell.py` (permissões contra a tabela do gateway)

**Target Platform**: Console web

**Project Type**: Web (somente console)

**Performance Goals**: nenhum novo

**Constraints**: permissão de cada página copiada do gateway por nome (contrato existente); ausência, não desabilitado, para páginas sem permissão

**Scale/Scope**: 9 páginas de Settings em 3 grupos; ~8 redirects; paleta e busca atualizadas

## Constitution Check

- **Art. VIII**: mudança confinada ao console; nenhuma rota nova de API.
- **Art. XII**: os testes que enumeram o manifesto (deep link, role matrix,
  contrato de permissão) são estendidos antes das telas.
- **Art. XIII**: sem identificadores de projeto upstream; copy via i18n.
- O comentário-contrato em `routes.ts` (regex do teste lê `id` após a chave)
  continua respeitado pelas entradas novas.

## Project Structure

### Documentation (this feature)

```text
specs_v5/010-navegacao-settings/
├── spec.md
├── plan.md              # este arquivo
├── tasks.md
└── checklists/requirements.md
```

### Source Code (repository root)

```text
console/src/shell/routes.ts                   # áreas + páginas de Settings (estender o manifesto)
console/src/shell/sidebar.tsx                 # grupo Settings: 2 entradas
console/src/shell/palette.tsx                 # comandos de navegação por página
console/src/app/(shell)/settings/layout.tsx   # novo: layout com subnav
console/src/app/(shell)/settings/<pagina>/    # novo: uma rota por página
console/src/app/(shell)/{autonomy,administration,signals,configuration,first-run}/
                                              # viram redirects (tabela antiga→nova)
tests/contract/console/test_console_shell.py  # cobre páginas novas por construção
console/tests/e2e/settings-nav.spec.ts              # novo: navegação e redirects
```

## Decisões de design

- **Manifesto**: `Area` ganha irmã `SettingsPage` (id, path, group da subnav,
  label, permission) enumerada no mesmo módulo; `groupsFor` da subnav segue a
  mesma regra de ausência do sidebar.
- **Transição**: até 040/050/060 entregarem as páginas, a subnav aponta para
  as telas atuais equivalentes (rotas antigas), mantendo o produto navegável —
  os redirects invertem no fim da migração.
- **Wizard**: a entrada `first-run` sai do manifesto de sidebar; a regra
  `visible` migra para os pontos de entrada (dashboard) — detalhado na 030.
