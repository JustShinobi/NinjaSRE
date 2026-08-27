# Implementation Plan: Iniciar investigação — o modal que começa do ambiente

**Branch**: `feat/v8-070-iniciar-investigacao` | **Date**: 2026-08-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v8/070-iniciar-investigacao/spec.md`

**Referência visual (DoD)**: `design/padrao-2026-08/StartInvestigation.dc.html`,
medida pelo gate visual da onda (EXECUCAO.md §3) nos dois temas. Acceptance:
`console/tests/e2e/iniciar-investigacao.acceptance.spec.ts`, vermelho antes.
Viewport normativo: 1920×1080.

## Summary

Um rework de fronteira dupla, pequeno dos dois lados:

1. **Gateway**: uma rota de leitura nova, `GET /v1/investigations/suggestions`,
   que compõe três leituras que já existem — assuntos recorrentes dos
   incidentes, lote não saudável do estate, presença de cluster — e anexa o
   `preamble` (time, modelo, postura, estágios) lido das mesmas fontes que o
   início do run usa. Nenhuma tabela nova, nenhuma escrita.
2. **Console**: `InvestigateDrawer` vira `InvestigateModal` — centrado,
   focado, com atalho, sugestões clicáveis e rodapé factual — no mesmo ponto
   de composição do shell, com um courier novo de leitura para as sugestões.

O que **não** muda: o contrato de início (`POST /v1/investigations`), o gating
de setup, o padrão de courier, e qualquer arquivo das outras features da onda.

## Technical Context

**Language/Version**: TypeScript (console Next), Python 3.12 (gateway)

**Primary Dependencies**:
`console/src/live/investigate.tsx` (o componente reescrito),
`console/src/live/act.ts` (inalterado, reusado),
`console/src/components/overlay.tsx` (variante modal centrada — `Drawer`
continua para os usos que são drawer),
`console/src/app/api/investigations/suggestions/route.ts` (courier novo de
GET, no padrão de `console/src/app/api/verify/route.ts`),
`console/src/shell/shell.tsx` (troca do componente montado, props iguais),
`console/src/i18n/*.ts` (frases das sugestões, rodapé, atalho — en e pt-BR),
`gateway/http/routes/investigations.py` (a rota nova),
`gateway/http/orchestration.py:64-86` (a resolução de time que o preamble
reusa — extraída para função nomeada compartilhada, não duplicada),
`gateway/http/routes/incidents.py` e `platform/estate/` (as leituras que as
sugestões compõem),
`surfaces/console/client.py` (método `suggestions()` novo, para CLI/contrato),
`fixtures/contract/openapi.json` e `console/src/api/schema.ts` (regenerados),
`tools/mockplane/` dataset (sugestões e preamble no cenário padrão),
`console/visual/screens.json` (estado "modal aberto").

**Storage**: N/A — leitura composta, nada persistido. `context.origin` viaja
no campo `context` que o contrato de início já tem.

**Testing**: pytest (contrato da rota nova: shape, cap de 3, ordem, parcial
sob fonte indisponível; unit da resolução de preamble); vitest (composição de
frase por locale, degradação sem sugestões, duplo-envio desabilitado);
Playwright (acceptance das 16 alegações; visual do estado novo); a marcação
staging-safe roda contra o staging no fechamento do slot.

**Target Platform**: gateway Python + console web no k3s de staging
(`stg-ninjasre.lan.kyo.ninja`)

**Project Type**: fronteira dupla console+gateway, um endpoint de leitura

**Performance Goals**: a rota de sugestões responde com as leituras que as
telas de incidentes/recursos já fazem; sem N+1 — uma passada por fonte. O
modal abre sem esperar por ela (FR-016).

**Constraints**: `make verify` verde partindo de verde; tokens/ícones/motion
congelados pela 000 — falta é declarada, nunca acrescentada aqui; strings
novas nas duas línguas; nenhum literal de time/modelo/postura/estágios no
console; diff contido aos arquivos desta feature mais os single-write de que
o slot é dono.

**Scale/Scope**: uma rota de leitura, um courier, um componente reescrito, ~12
chaves i18n × 2 línguas, um estado visual novo, contrato e cliente
regenerados.

## Constitution Check

*GATE: precisa passar antes da execução. Reconferir ao final.*

| Artigo | Como este plano satisfaz |
|---|---|
| I — Evidência sobre asserção | Cada sugestão é estruturada, nomeia sua fonte e degrada com ausência declarada quando uma leitura falha; o preamble usa valores servidos, não prosa inventada. |
| II — Autonomia limitada | Sugestões apenas preenchem o objetivo; iniciar continua sendo ação explícita da pessoa e usa o gating existente. |
| III — Leitura por padrão | A rota nova é somente leitura; o único POST continua sendo o fluxo de início já existente e disparado pela pessoa. |
| IV — Segredo nunca chega ao agente | O modal lê apenas dados estruturados sem credenciais; autenticação fica na sessão/proxy e nenhum segredo aparece no preamble, prompt ou trace. |
| V — Um runtime canônico | Não cria runtime nem altera a avaliação do investigador. |
| VI — Neutralidade de provedor | O modelo aparece como dado factual do preamble; nenhum SDK ou lógica de fornecedor entra no console. |
| VII — Aprendizado é medido | Não altera mecanismos de aprendizado nem reivindica ganho de aprendizagem. |
| VIII — Arquitetura em camadas | A composição fica no gateway; o console usa courier e cliente existentes; leituras vêm das portas abaixo do gateway. |
| IX — Capacidades declaradas | Nenhuma capacidade nova de agente. |
| X — O operador é dono dos dados | Nenhuma request externa, telemetria ou version check; o dataset e o staging permanecem locais ao deployment. |
| XI — Datastore único | A rota compõe as leituras existentes pelos ports/repositorios; não há SQL ou driver fora da persistência. |
| XII — Test-first, rastreado | Acceptance, contrato da rota e testes de seleção nascem vermelhos; as mensagens e a virada ficam em `evidence/`. |
| XIII — Idioma e atribuição | Código e paths novos em inglês; UI pelo catálogo `en`/`pt-BR`; nenhum identificador de planejamento ou segredo é commitado. |
| XIV — Composto ou não é entrega | A rota nova é chamada pelo modal no shell servido; o fluxo de sugestões e seu consumo são alcançáveis em produção. |

O gating de `runtimeComposed` não é afrouxado, e time/modelo/postura/estágios
continuam vindo de funções compartilhadas com quem executa — uma fonte por
fato.

## Project Structure

### Documentation (this feature)

```text
specs_v8/070-iniciar-investigacao/
├── spec.md
├── plan.md
├── tasks.md
└── evidence/
    └── visual/            # capturas Orca + VEREDITO.md, no fechamento do slot
```

### Source Code (repository root)

```text
gateway/http/routes/investigations.py    # + GET /v1/investigations/suggestions
gateway/http/orchestration.py            # resolução de time extraída e reusada
platform/estate/                         # leitura de saúde (fonte, inalterada)
surfaces/console/client.py               # + suggestions()

console/src/live/investigate.tsx         # o modal (reescrito)
console/src/live/act.ts                  # reusado
console/src/components/overlay.tsx       # + variante modal centrada
console/src/app/api/investigations/suggestions/route.ts   # courier GET novo
console/src/shell/shell.tsx              # monta o modal no lugar do drawer
console/src/i18n/en.ts, pt-BR.ts         # chaves novas (dono no S4)
console/visual/screens.json              # estado novo (dono no S4)

fixtures/contract/openapi.json           # regenerado
console/src/api/schema.ts                # regenerado
tools/mockplane/                         # dataset: sugestões + preamble

tests: tests/unit/gateway/http/ (rota), tests/contract/ (shape),
console/tests/unit/live/ (modal), console/tests/e2e/ (acceptance, visual)
```

**Structure Decision**: fronteira dupla na mesma feature porque a sugestão
nasce no gateway e morre no clique do modal — separá-las deixaria ou uma rota
sem consumidor (Art. XIV) ou um modal mockado em produção.

## Complexity Tracking

Sem violações a justificar: nenhuma tabela, nenhum estado novo de servidor,
um componente, uma rota de leitura.
