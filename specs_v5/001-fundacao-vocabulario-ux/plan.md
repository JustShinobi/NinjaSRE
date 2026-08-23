# Implementation Plan: Fundação de vocabulário e contratos de UX

**Branch**: `feat/v5-001-fundacao-vocabulario-ux` | **Date**: 2026-08-14 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v5/001-fundacao-vocabulario-ux/spec.md`

## Summary

Cinco fundações consumidas por toda a onda: (1) vocabulário canônico de estado
com um componente de chip único; (2) registro de nomes de exibição/categoria
para todo id de catálogo, com guard check; (3) contrato tipado de CTA para
empty states; (4) padrão de conteúdo de referência recolhido; (5) fonte única
de contagem de progresso. Tudo é extensão de mecanismos que já existem —
`console/src/design/status.ts`, o catálogo de integrações do gateway, o
checklist de first-run — nada é infraestrutura nova.

## Technical Context

**Language/Version**: TypeScript (console: Next.js 16, React 19); Python 3.12 (gateway)

**Primary Dependencies**: console/src/design (tokens, status, icons), catálogo i18n `console/src/i18n/en.ts`, catálogo de integrações do gateway (`gateway/http/routes/integrations.py`), checklist de first-run existente

**Storage**: N/A (o registro de exibição vive no catálogo do gateway, já servido)

**Testing**: vitest (unit console), Playwright behaviour/visual, pytest em `tests/contract/console/`, guard checks no `make verify`

**Target Platform**: Console web (desktop-first, 1080p como viewport de referência)

**Project Type**: Web (console) + extensão de payloads no gateway

**Performance Goals**: nenhum novo; chips e registry são dados estáticos por request

**Constraints**: orçamento de rolagem ≤ 2 viewports em 1080p por tela de configuração; ausência de fallback silencioso (registro faltante quebra o build, não a tela)

**Scale/Scope**: ~5 catálogos de ids (integrações, providers, modelos, papéis, receptores); ~12 empty states inventariados

## Constitution Check

- **Art. VIII (camadas)**: o console permanece cliente da API — o registro de
  exibição é servido pelo gateway, não duplicado no front. `test_console_is_an_api_client` continua passando.
- **Art. XII (test-first)**: cada entrega abaixo nasce com o teste que a
  verifica (varredura de vocabulário, guard check de display name, inventário
  de CTA, medição de altura).
- **Art. II (bounds nomeados)**: o orçamento de rolagem vira constante nomeada
  em `config/constants/`, não número mágico em teste.
- **Art. XIII (linguagem)**: nenhum nome de projeto upstream em código ou
  fixture; copy nova entra pelo catálogo i18n.

## Project Structure

### Documentation (this feature)

```text
specs_v5/001-fundacao-vocabulario-ux/
├── spec.md
├── plan.md              # este arquivo
├── tasks.md
└── checklists/requirements.md
```

Research e data-model foram dispensados: os mecanismos-alvo já existem no
repositório e estão nomeados no Technical Context.

### Source Code (repository root)

```text
console/src/design/status.ts          # vocabulário canônico + chip (estender)
console/src/design/empty-state.tsx    # novo: EmptyState com CTA tipado
console/src/design/reference.tsx      # novo: bloco de referência recolhível
console/src/i18n/en.ts                # chaves do vocabulário e CTAs
console/src/api/                      # tipos do registro de exibição (via openapi)
gateway/http/routes/integrations.py   # display_name/categoria no payload (já tem category/summary)
config/constants/surfaces.py          # SCROLL_BUDGET_VIEWPORTS e afins
scripts/ (console)                    # guard check de display name
tests/contract/console/               # contrato: vocabulário, CTA, progresso
console/tests/e2e/                          # Playwright: altura de telas, varredura de texto
```

## Fases

- **Fase A — vocabulário**: estados canônicos em `status.ts` + chip único;
  varredura automatizada por texto proibido ("HEALTHY", "it answered",
  "stored, unchecked", "UNCONFIGURED") nas telas.
- **Fase B — registro de exibição**: payloads do gateway carregam display
  name/categoria; guard check falha para id sem registro; console para de
  renderizar ids crus em título/label.
- **Fase C — contratos**: `EmptyState` com destino tipado (rota + âncora +
  permissão); `Reference` recolhível; fonte única de progresso exposta e
  consumida por dashboard/first-run.
- **Fase D — orçamento de rolagem**: constante nomeada + teste Playwright
  medindo altura das telas de configuração com fixtures representativas.
