# Implementation Plan: Setup como wizard com contagem única

**Branch**: `feat/v5-030-setup-wizard` | **Date**: 2026-08-14 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v5/030-setup-wizard/spec.md`

**Referência visual (DoD)**: `specs_v5/mockups/settings-v5.html#mockup-4`

## Summary

A tela de first-run (três painéis com estado duplicado) vira um wizard com
stepper, alimentado exclusivamente pela fonte única de progresso (001). O
conteúdo dos sete passos e os checks reais existentes são preservados — muda a
apresentação, a navegação (ida-e-volta com telas externas) e a acionabilidade
das falhas (CTA para o campo que corrige, via contrato da 001).

## Technical Context

**Language/Version**: TypeScript (console)

**Primary Dependencies**: `console/src/surfaces/first-run/` e `console/src/surfaces/screens/first-run.tsx` (substituição), checklist/checks do gateway (existentes), EmptyState/StatusChip (001), rotas de destino (010, 040)

**Storage**: N/A — progresso é do deployment, persistido onde já é

**Testing**: vitest (stepper, estados), Playwright behaviour (funil completo), pytest contract (`tests/contract/console/test_console_first_run.py`, estender)

**Target Platform**: Console web

**Project Type**: Web (somente console)

**Performance Goals**: nenhum novo

**Constraints**: checks fazem requisição real (comportamento atual preservado); nada de contagem local; wizard fora da sidebar (010)

**Scale/Scope**: 7 passos, ~3 itens verificáveis no passo de verificação hoje

## Constitution Check

- **Art. XII**: o funil completo vira teste behaviour antes da reescrita
  (deployment limpo → concluído), usando o harness live existente.
- **Art. I (evidência)**: o diagnóstico de falha exibido é o do backend,
  encurtado por apresentação (duas frases + expansão), nunca reescrito no
  front.
- **Art. VIII**: o wizard lê o checklist da API; não infere estado de passos
  por conta própria.

## Project Structure

### Documentation (this feature)

```text
specs_v5/030-setup-wizard/
├── spec.md
├── plan.md              # este arquivo
├── tasks.md
└── checklists/requirements.md
```

### Source Code (repository root)

```text
console/src/surfaces/first-run/            # wizard: stepper, passos, verificação
console/src/surfaces/screens/first-run.tsx # substituído pelo wizard
console/src/app/(shell)/first-run/         # rota do wizard (redireciona quando completo)
console/src/surfaces/screens/dashboard.tsx # convite "Continue setting up" (fonte única)
tests/contract/console/test_console_first_run.py
console/tests/e2e/setup-wizard.spec.ts           # funil de ponta a ponta
```

## Decisões de design

- **Stepper**: os sete passos atuais viram dados (id, nome, bloqueante,
  onde-completa) derivados do checklist servido — sem lista paralela no front.
- **Ida-e-volta**: passos externos navegam com `?return=setup`; a tela de
  destino mostra o banner de retorno enquanto o setup estiver incompleto.
- **Falha acionável**: cada check reprovado carrega um destino do contrato de
  CTA (ex.: modelo → página Models & providers da 040; até a 040 existir, o
  destino transitório é a tela atual equivalente).
- **Conclusão**: resumo com nomes de exibição; rota redireciona ao dashboard
  quando o checklist está completo (regra `visible` de hoje, invertida).
