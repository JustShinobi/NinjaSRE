# Implementation Plan: Telas do agente — Models & providers, Autonomy & guardrails, Notifications

**Branch**: `feat/v5-040-agente` | **Date**: 2026-08-14 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v5/040-agente/spec.md`

**Referência visual (DoD)**: `specs_v5/mockups/settings-v5.html#mockup-1`

## Summary

Três páginas humanas no grupo Agent da subnav (010), cobrindo os grupos de
schema de modelos, autonomia/guardrails e política de notificação. As páginas
editam pela API de configuração hierárquica existente (a mesma que o editor
cru usa), ganhando por cima: nomes humanos, estado de credencial inline,
verificação no salvar, prévia de resolução e origem do valor efetivo. A tela
Autonomy atual é absorvida — o loop Autonomy ⇄ Configuration morre aqui.

## Technical Context

**Language/Version**: TypeScript (console); Python 3.12 (gateway apenas se faltar leitura pontual de metadado de modelo)

**Primary Dependencies**: API de configuração hierárquica (rotas existentes de config/preview), `console/src/surfaces/screens/{autonomy,configuration}.tsx` (fontes de absorção), catálogo de providers/modelos do gateway (capacidade tool-calling), componentes 001

**Storage**: N/A — valores no serviço de configuração existente

**Testing**: vitest, Playwright behaviour, pytest contract (payloads de config e preview)

**Target Platform**: Console web

**Project Type**: Web + leitura de metadados existentes

**Performance Goals**: nenhum novo

**Constraints**: semântica hierárquica preservada (valor efetivo + origem); simulação de autonomia preservada; invariantes constitucionais aparecem como fatos, não opções

**Scale/Scope**: 3 páginas; ~10 grupos de schema cobertos (models.*, capabilities parcial, policies.autonomy/guardrails/masking/approvals, surfaces.notification_policy)

## Constitution Check

- **Art. II (autonomia limitada)**: a página de autonomia edita limites que
  continuam sendo constantes nomeadas/config declarada; nenhum limite novo em
  literal de tela.
- **Art. III (read-only por default)**: default propose-only na ausência de
  regra é apresentado e preservado; override exige nome/razão/expiração e cai
  no audit — comportamento existente, agora visível.
- **Art. IV**: estado de credencial de provider é lido do gateway; nenhum
  segredo transita pela página.
- **Art. XII**: cada página nasce do teste behaviour do fluxo de edição
  (editar → prévia → aplicar → origem atualizada).

## Project Structure

### Documentation (this feature)

```text
specs_v5/040-agente/
├── spec.md
├── plan.md              # este arquivo
├── tasks.md
└── checklists/requirements.md
```

### Source Code (repository root)

```text
console/src/surfaces/settings/models.tsx         # novo: Models & providers
console/src/surfaces/settings/autonomy.tsx       # novo: absorve a tela atual + edição de regras
console/src/surfaces/settings/notifications.tsx  # novo
console/src/surfaces/settings/resolution-preview.tsx # prévia de resolução (compartilhada; a 070 a promove)
console/src/app/(shell)/settings/{models,autonomy,notifications}/
console/src/surfaces/screens/autonomy.tsx        # removida ao fim (rota já redireciona pela 010)
tests/contract/console/                          # contrato de edição/preview por página
console/tests/e2e/settings-agent.spec.ts
```

## Decisões de design

- **Uma API, três apresentações**: as páginas montam patches para o serviço
  de configuração existente; a prévia usa a rota de preview que o editor cru
  já usa — `resolution-preview.tsx` nasce aqui e é promovida a componente
  compartilhado pela 070.
- **Tool calling**: badge derivado do catálogo de providers (capacidade já
  conhecida pelo gateway); verificação reprovada anterior anotada a partir do
  resultado de check persistido.
- **Seletor de escopo**: aparece apenas com >1 nó na hierarquia (hoje oculto).
- **Simulação**: "what would this decide differently" vira etapa opcional do
  fluxo de salvar da página de autonomia, não três botões soltos.
