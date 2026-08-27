# Implementation Plan: Dados — Alert intake, Schedules & destinations

**Branch**: `feat/v5-060-dados` | **Date**: 2026-08-14 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v5/060-dados/spec.md`

**Referência visual (DoD)**: `specs_v5/mockups/settings-v5.html#mockup-1` (grupo Data); CTA de Destinations aterrissa no `#mockup-2` filtrado

## Summary

A tela Signals se dissolve em duas páginas do grupo Data da subnav (010).
Alert intake inverte a hierarquia atual (ação primeiro, referência recolhida)
mantendo receptores, simulação e token de entrega existentes. Schedules &
destinations junta o par agenda/destino numa página, poliendo o formulário de
cron com presets e consertando o CTA de Destinations (hoje aponta para o
editor de schema; passa a aterrissar no catálogo filtrado — contrato da 001).

## Technical Context

**Language/Version**: TypeScript (console)

**Primary Dependencies**: `console/src/surfaces/screens/signals.tsx` (fonte de absorção), rotas existentes de webhooks/simulação/schedules/destinations/token de entrega, componentes 001 (Reference, EmptyState, StatusChip), catálogo 020 (filtro por categoria via deep link)

**Storage**: N/A

**Testing**: vitest, Playwright behaviour, pytest contract das superfícies

**Target Platform**: Console web

**Project Type**: Web (somente console; nenhum comportamento novo de gateway)

**Performance Goals**: nenhum novo

**Constraints**: mecanismos de confiança dos receptores inalterados; fuso IANA validado; ≤ 2 viewports por página

**Scale/Scope**: 2 páginas; 7 receptores hoje; agendas na casa da dúzia

## Constitution Check

- **Art. VIII**: o console segue cliente das rotas existentes; a prévia de
  próximas execuções do cron é derivada de biblioteca local sem chamar o
  agente.
- **Art. XII**: behaviour test do funil "copiar endpoint → evento chega →
  rastro visível" antes da reescrita, usando o harness live.
- **Art. I**: o rastro "para onde foi" continua exibindo o transit real, sem
  resumo inventado pelo front.

## Project Structure

### Documentation (this feature)

```text
specs_v5/060-dados/
├── spec.md
├── plan.md              # este arquivo
├── tasks.md
└── checklists/requirements.md
```

### Source Code (repository root)

```text
console/src/surfaces/settings/alert-intake.tsx       # novo
console/src/surfaces/settings/schedules.tsx          # novo: agendas + destinos
console/src/app/(shell)/settings/{alert-intake,schedules}/
console/src/surfaces/screens/signals.tsx             # removida ao fim (redirects na 010)
tests/contract/console/                              # contrato das duas páginas
console/tests/e2e/settings-data.spec.ts
```

## Decisões de design

- **Intake**: linha por receptor (nome de exibição, endpoint copiável, chip
  de atividade distinguindo silêncio de erro de autenticação); detalhe
  recolhido com formato/assinatura (componente Reference) + teste de entrega
  + emissão de token contextual.
- **Cron**: presets → expressão gerada, campo editável, prévia das 3 próximas
  execuções no fuso; validação inline com exemplo.
- **Destinations**: destinos declarados sobre integrações conectadas; empty
  state usa EmptyState com destino `/integrations?category=chat` (020).
- **Continuous observation**: fica fora — superfície de leitura, permanece
  onde a 070 mapear (não é entrada/saída de configuração).
