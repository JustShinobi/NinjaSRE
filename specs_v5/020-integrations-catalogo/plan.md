# Implementation Plan: Catálogo de integrações navegável

**Branch**: `feat/v5-020-integrations-catalogo` | **Date**: 2026-08-14 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v5/020-integrations-catalogo/spec.md`

**Referência visual (DoD)**: `specs_v5/mockups/settings-v5.html#mockup-2` e `#mockup-3`

## Summary

Reescrita da tela `/integrations` (que permanece entrada própria da sidebar):
seções Connected e Suggested primeiro, catálogo em grid compacto com busca e
filtros por categoria/estado, credencial em painel lateral com deep link, e a
prosa "Not covered" movida para página de referência. O backend já serve
categoria, resumo, saúde e sugestão (`GET /v1/integrations`); o gap de API é
metadado de credencial (label humana, instrução de obtenção, escopo mínimo)
por integração.

## Technical Context

**Language/Version**: TypeScript (console); Python 3.12 (gateway — metadado de credencial no catálogo)

**Primary Dependencies**: `console/src/surfaces/screens/integrations.tsx` (reescrita), `gateway/http/routes/integrations.py`, catálogo de integrações (`integrations/_base/`), componentes da 001 (StatusChip, EmptyState, Reference)

**Storage**: N/A — credenciais seguem no vault via fluxo existente (write-only)

**Testing**: vitest, Playwright behaviour + visual (o mockup-2/3 é o alvo do teste visual), pytest contract para o payload estendido

**Target Platform**: Console web

**Project Type**: Web + extensão de payload no gateway

**Performance Goals**: catálogo com 84+ itens renderiza em ≤ 2 viewports; busca filtra em tempo real sem request por tecla (dados já no cliente)

**Constraints**: Art. IV — o painel nunca exibe segredo armazenado; "Salvar e testar" usa as rotas existentes de credencial + verificação; nomes de exibição obrigatórios (001)

**Scale/Scope**: 84 integrações hoje, projetado para ~150

## Constitution Check

- **Art. IV (segredos)**: campos write-only, sem eco de valor; o teste de
  contrato `tests/security/surfaces/test_credentials_never_on_disk.py` e
  afins continuam passando; nenhum segredo em query/URL do deep link.
- **Art. VIII**: ordenação por relevância continua do backend; o console não
  deriva relevância própria (contrato documentado em `list_integrations`).
- **Art. XII**: teste visual/behaviour antes da reescrita; fixture de catálogo
  cheio para o teste de altura.
- **Art. IX**: o metadado de credencial entra no catálogo declarativo das
  integrações, não hardcoded na tela.

## Project Structure

### Documentation (this feature)

```text
specs_v5/020-integrations-catalogo/
├── spec.md
├── plan.md              # este arquivo
├── tasks.md
└── checklists/requirements.md
```

### Source Code (repository root)

```text
console/src/surfaces/screens/integrations.tsx     # reescrita: seções + grid + filtros
console/src/surfaces/screens/integration-panel.tsx # novo: slide-over de credencial
console/src/app/(shell)/integrations/[name]/       # novo: deep link do painel
console/src/app/(shell)/integrations/not-covered/  # novo: página de referência
gateway/http/routes/integrations.py                # credential_fields no payload
integrations/_base/                                # declaração de metadado por credencial
tests/contract/console/                            # payload + tela como cliente da API
console/tests/e2e/integrations.spec.ts                   # behaviour + visual
```

## Decisões de design

- **Grid**: uma dobra visível + "mostrar todas" com virtualização simples
  (CSS `content-visibility` + paginação por categoria); sem lib nova.
- **Painel**: rota paralela do App Router para deep link sem perder o estado
  do catálogo; fechar restaura rolagem e filtros.
- **Logos**: iniciais estilizadas (decisão da spec); componente da 001.
- **"Salvar e testar"**: composição das rotas existentes (store + verify) em
  uma ação com estados intermediários visíveis.
