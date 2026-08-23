# Implementation Plan: Aposentadoria do editor de configuração cru

**Branch**: `feat/v5-070-migracao-editor-cru` | **Date**: 2026-08-14 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v5/070-migracao-editor-cru/spec.md`

**Referência visual (DoD)**: `specs_v5/mockups/settings-v5.html#mockup-1` — a ausência do editor e do grupo "Advanced" é parte do DoD

## Summary

Fecha a substituição 100%: um mapa de paridade grupo-do-schema → tela dona,
verificado por guard check, garante que nenhum campo perde seu lugar de
edição; os grupos que 040/050/060 não cobriram são alocados explicitamente
(seção avançada recolhida da página dona pertinente); a prévia de resolução
vira componente compartilhado formal; o editor cru é removido e
`/configuration` redireciona por seção.

## Technical Context

**Language/Version**: TypeScript (console); Python 3.12 (guard check lê o schema do serviço de configuração)

**Primary Dependencies**: schema do serviço de configuração hierárquica (fonte dos 38 grupos), `resolution-preview.tsx` (nascido na 040), manifesto de rotas (010), telas donas (040/050/060 + telas existentes de Environment)

**Storage**: N/A

**Testing**: guard check no `make verify` (paridade), pytest contract, Playwright (redirects, ausência do editor)

**Target Platform**: Console web + verificação no toolchain

**Project Type**: Web + guard check Python

**Performance Goals**: nenhum novo

**Constraints**: nenhum campo órfão em momento algum da transição (o editor só deixa de servir um grupo quando a dona existe); API/CLI de configuração intocadas

**Scale/Scope**: 38 grupos hoje; mapa vivo acompanhando o schema

## Constitution Check

- **Art. XII**: o guard check de paridade é o teste central e nasce falhando
  (grupos ainda sem dona listados); a remoção do editor só acontece com ele
  verde.
- **Art. VIII**: o mapa vive junto ao schema (backend) e o console o consome;
  nada de lista paralela no front.
- **Art. II**: nenhuma perda de capacidade de configurar limites — paridade
  é exatamente essa garantia.

## Project Structure

### Documentation (this feature)

```text
specs_v5/070-migracao-editor-cru/
├── spec.md
├── plan.md              # este arquivo
├── tasks.md
└── checklists/requirements.md
```

### Source Code (repository root)

```text
platform/…/config schema                          # mapa de paridade junto ao schema
scripts / Makefile                                # guard check `check-config-parity`
console/src/design/resolution-preview.tsx         # promoção do componente da 040
console/src/surfaces/settings/…                   # seções avançadas dos grupos restantes
console/src/app/(shell)/configuration/            # redirect por seção (tabela)
console/src/surfaces/screens/configuration.tsx    # removida ao fim
tests/contract/console/ + console/tests/e2e/            # paridade, redirects, ausência do editor
```

## Alocação dos grupos (verificada contra `platform/config_service/schema/` em 2026-08-14)

O schema fecha em **sete seções de raiz** (`ROOT_SECTIONS` em
`platform/config_service/schema/root.py`): `agents`, `models`, `capabilities`,
`integrations`, `policies`, `surfaces`, `transit` — os "38 grupos" da UI são
os subníveis achatados. `section_fields()` já expõe os campos por seção como
dado para o console; o mapa de paridade e o guard check iteram por aí, não por
lista paralela. O schema também declara a frase de ajuda por campo e por seção
(`field_help`/`section_help` em `schema/types.py`): as telas donas consomem
esses textos — a regra FR-011 da 001 depende disso.

| Seção / subseção | Dona (verificada) |
|---|---|
| `agents.prompts`, `agents.operating_context`, `agents.subagents`, orçamentos (`max_iterations`, `tool_budget`, …) | The agent → seção de edição (Team context já foi absorvido lá na v4) |
| `models.*` — 8 papéis: investigator, subagent, intake, diagnose, extraction, embedding, selection, summarisation | Models & providers (040) |
| `capabilities` | The agent → seção avançada |
| `integrations` (entradas por vendor: nome, credencial, base_url, enabled) | painel da integração no catálogo (020) |
| `policies.changes` (+ `git_host`) | Knowledge → seção avançada |
| `policies.memory`, `policies.strategy`, `policies.knowledge` | Knowledge → seção avançada |
| `policies.masking`, `policies.guardrails`, `policies.approvals`, `policies.autonomy` | Autonomy & guardrails (040) |
| `policies.sso` (+ `claims`) | Single sign-on (050) |
| `policies.observation` (+ `bridge`, `bridge.metrics`, `bridge.logs`, `guardian`) | Alert intake → seção avançada (060) |
| `surfaces.channels`, `surfaces.report_destinations`, `surfaces.notification_sinks` | Schedules & destinations (060) — são exatamente os "destinos" da spec |
| `surfaces.notification_policy` | Notifications (040) |
| `surfaces.enabled` (quais superfícies o time usa) | Schedules & destinations → seção avançada (alocação explícita; é entrega/alcance, não política de atenção) |
| `surfaces.console.tutorial_dismissed` | **Estado interno gravado pelo console** — dona é o próprio console, sem formulário. O mapa ganha esta categoria: campo de máquina, declarado como tal, para o guard check não exigir tela para ele |
| `transit` | Alert intake + Schedules & destinations (060) — as duas metades de "de onde veio / para onde foi" |

Nenhum grupo ficou sem dona nomeada; a categoria "campo de máquina" cobre o
caso `tutorial_dismissed` sem abrir brecha para um "resto" genérico (FR-007).
