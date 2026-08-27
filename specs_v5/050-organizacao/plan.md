# Implementation Plan: Organização — Members, SSO, Machine tokens, Audit

**Branch**: `feat/v5-050-organizacao` | **Date**: 2026-08-14 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v5/050-organizacao/spec.md`

**Referência visual (DoD)**: `specs_v5/mockups/settings-v5.html#mockup-1` (grupo Organization da subnav; padrões de formulário dos mockups 1 e 3)

## Summary

A tela Administration (cinco assuntos numa página) desmembra em quatro páginas
do grupo Organization da subnav (010). Duas são reapresentação (Members &
roles; Machine tokens com agrupamento e expurgo), uma vira fluxo guiado (SSO
com teste antes de ligar — contrato que o backend já impõe), e a quarta
conserta dois defeitos confirmados (Audit: período que não alarga; contagem
contraditória com a lista).

## Technical Context

**Language/Version**: TypeScript (console); Python 3.12 (gateway: consulta de audit unificada; emissão de token com substituição)

**Primary Dependencies**: `console/src/surfaces/screens/{administration,audit}.tsx` (fontes de absorção), rotas de identidade/tokens/audit/SSO do gateway, componentes 001

**Storage**: N/A — modelos existentes de identidade, token e audit

**Testing**: vitest, Playwright behaviour, pytest contract (identidade/audit), testes de segurança existentes de rotas

**Target Platform**: Console web

**Project Type**: Web + duas correções de comportamento no gateway

**Performance Goals**: audit paginado com contagem honesta (truncamento declarado, padrão do produto)

**Constraints**: permissões atuais preservadas (`identity.read` cobre audit por construção — comentário em routes.ts); ações consequentes seguem em audit

**Scale/Scope**: 4 páginas; 2 defeitos raiz no gateway/console a corrigir

## Constitution Check

- **Art. X (dados do operador)**: export de audit respeitando filtros;
  nenhuma retenção nova.
- **Art. III**: revogações/ativações pedem confirmação explícita; ativação de
  SSO sem teste aprovado é bloqueada — o invariante existente vira regra de
  interface.
- **Art. XII**: os dois defeitos do Audit são reproduzidos como testes
  falhando (o botão no-op e a contagem divergente) antes de qualquer correção.
- **Art. IV**: tokens exibidos apenas na emissão (comportamento atual);
  nenhuma superfície nova ecoa segredo.

## Project Structure

### Documentation (this feature)

```text
specs_v5/050-organizacao/
├── spec.md
├── plan.md              # este arquivo
├── tasks.md
└── checklists/requirements.md
```

### Source Code (repository root)

```text
console/src/surfaces/settings/members.tsx        # novo
console/src/surfaces/settings/sso.tsx            # novo: fluxo em etapas
console/src/surfaces/settings/machine-tokens.tsx # novo: agrupado + expurgo
console/src/surfaces/settings/audit.tsx          # novo: filtros nomeados (absorve audit.tsx)
console/src/app/(shell)/settings/{members,sso,machine-tokens,audit}/
gateway/http/routes/…                            # audit: uma consulta para contagem+lista;
                                                 # tokens: emissão com substituição por finalidade
tests/contract/console/ + tests/security/        # contrato e segurança das 4 páginas
console/tests/e2e/settings-org.spec.ts
```

## Decisões de design

- **Audit — causa raiz primeiro**: contagem e lista saem da mesma consulta no
  gateway (defeito da divergência); o alargamento de período é estado do
  filtro que reexecuta a consulta (defeito do no-op é do front). Correções
  test-first contra reprodução ao vivo.
- **Tokens**: agrupamento por finalidade no gateway (o dado já existe no
  registro de emissão); "revogar todos menos o mais recente" é uma operação,
  não N cliques; emissão para finalidade ativa substitui e registra.
- **SSO**: etapas configurar → testar com claims → ligar; o teste de claims
  usa a rota existente ("run through the same reading a real sign-in takes");
  fallback local declarado na página.
- **Members**: reapresentação com chips 001 e permissões de papel legíveis;
  guarda de "último administrador" no gateway se ainda não existir.
