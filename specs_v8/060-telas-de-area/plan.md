# Implementation Plan: Telas de área — Incidentes, Recursos, Conhecimento e O agente viram o board

**Branch**: `feat/v8-060-telas-de-area` | **Date**: 2026-08-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v8/060-telas-de-area/spec.md`

**Referência visual (DoD)**: `design/padrao-2026-08/{Incidents,Resources,Knowledge,TheAgent}.dc.html`,
normativos por decisão 1 da onda. Acceptance red-first por tela; gate visual
de EXECUCAO §3 (Orca browser, dois temas, VEREDITO.md) fecha o slot.

## Summary

Quatro telas, um princípio: **o dado que a tela precisa já existe quase
inteiro — o que falta é desenhá-lo como o board manda e expor dois campos.**

1. **Incidentes** é rework de apresentação puro. `groupBySubject` já devolve
   occurrences com timestamp, estado e run — a linha expandida vira eixo de
   tempo + link + causa em vez de N linhas idênticas. Zero endpoint novo.
2. **Recursos** é o único lugar com contrato novo: a listagem passa a servir
   `node` e `unhealthy_since` (o backend já os conhece; hoje não os expõe).
   Todo o resto — barra segmentada, seções, síntese — é leitura da mesma
   resposta.
3. **Conhecimento** é reorganização: Aprendido vira a aba de entrada, o
   filtro normaliza `container:`/`guest:`, e o painel lateral lê a fila de
   propostas de conhecimento que já existe.
4. **O agente** é síntese: a linha de metrô e os três cards leem as cinco
   rotas que as abas já leem (`agent.tsx:212-248`); as abas completas
   continuam.

Execução em **fan-out interno: um implementer por tela**, porque as quatro
não compartilham arquivo de surface (a lição da v6: fatiar por componente).
Os single-write (`i18n`, `routes.ts`, `screens.json`) são desta feature no
slot, mas **dentro** do fan-out têm um dono só (a tela de Incidentes), com
as outras três declarando chaves no relatório — mesma mecânica do slot,
um nível abaixo.

## Technical Context

**Language/Version**: TypeScript (console Next), Python 3.12 (contrato do
estate no gateway)

**Primary Dependencies**:
- Incidentes: `console/src/surfaces/screens/incidents.tsx`,
  `console/src/surfaces/incident-groups.ts` (leitura, sem mudança de shape),
  `gateway/http/routes/incidents.py` (leitura), a listagem de runs para
  headline.
- Recursos: `console/src/surfaces/screens/resources.tsx`,
  `console/src/app/(shell)/resources/page.tsx`, a rota do estate no gateway
  (cravada na Fase 0 a partir do que `ResourcesScreen` consome),
  `platform/persistence/ports/estate_repository.py` e o repositório Postgres
  correspondente (campos `node`/`unhealthy_since` na resposta),
  `platform/observation/sources/estate_health.py` (fonte do since).
- Conhecimento: `console/src/surfaces/screens/knowledge.tsx` (+ os
  componentes de aba que ele monta), a rota de episódios e a rota de
  propostas de conhecimento (cravadas na Fase 0).
- O agente: `console/src/surfaces/screens/agent.tsx` e as cinco rotas já
  cravadas nele (`/v1/agent/pipeline`, `/v1/capabilities`,
  `/v1/config/{node}/catalogue`, `/v1/autonomy/policy/{node}/outlook`,
  preview).
- Todas: tokens/ícones/chips/formas da 000 (`console/src/design/*`,
  congelados — falta é declarada, nunca criada aqui), `Tabs`/`TabLinks`
  (`console/src/components/navigation.tsx`), `Panel` e seus estados.

**Storage**: nenhum esquema novo. `node` e `unhealthy_since` são leitura de
dados já persistidos (discovery + histórico de saúde do estate); se a
consulta atual não os junta, a mudança é na query do repositório e no view
model da rota — não em tabela.

**Testing**: vitest para a faixa de 24 h (posicionamento por timestamp,
janela, "e mais N"), a normalização de componentes (tabela de casos com
`container:`/`guest:`), a derivação de regime do estágio e as contagens de
efeito colateral; pytest de contrato para os dois campos novos do estate;
quatro acceptance specs Playwright red-first; suíte visual re-baselined nas
quatro telas (variantes em `console/visual/screens.json`).

**Target Platform**: console web servido no k3s de staging; gate visual via
Orca browser contra `https://stg-ninjasre.lan.kyo.ninja`.

**Project Type**: console-pesado com um toque de contrato (estate). Par do
slot S2 é a 040 (decisões, backend-pesado) — interseção declarada: nenhuma.

**Performance Goals**: nenhuma requisição adicional por linha — headline de
causa resolvido com uma leitura da listagem de runs por página; a síntese de
Recursos derivada da resposta única da listagem; os cards de O agente leem o
que as abas já liam (mesmo número de requests da tela atual).

**Constraints**: `make verify` verde partindo de verde; os artboards são o
critério — desvio visível não registrado é FAIL do slot (EXECUCAO §3);
nenhum arquivo de `console/src/design/` editado (congelados pela 000);
nenhum toque em `dashboard.tsx` (050), rotas de decisão (040), `live/`
(010); strings novas nas duas línguas; ids nunca como início de título
(transversal AN-T2); a suíte transversal de `/incidents/{id}` fecha verde de
verdade, não por allowlist — débito herdado do S1 (specs_v8/CONFRONTO.md
§6), fechado por FR-001/T015a.

**Scale/Scope**: 4 surfaces reescritas na apresentação, 2 campos novos num
contrato de leitura, 1 mudança de default de aba, ~4 specs e2e novos, 8
capturas visuais.

## Constitution Check

*GATE: precisa passar antes da execução. Reconferir ao final.*

| Artigo | Como este plano satisfaz |
|---|---|
| I — Evidência sobre asserção | A síntese de Recursos e a "última causa" de Incidentes citam dados servidos (unhealthy_since, headline de run) — nunca frase inventada para descrever um conjunto. Empty states dizem o que não há e apontam ação; nenhum painel afirma o negativo sobre leitura falhada (estados do `Panel` preservados). |
| II — Autonomia limitada | Nada aqui age. "Investigar em lote" pré-preenche um objetivo para uma pessoa disparar. |
| III — Leitura por padrão | As quatro telas são leitura; a única mudança de backend expõe dois campos numa resposta de leitura. |
| IV — Segredo nunca chega ao agente | Não toca credencial nem proxy. |
| V — Um runtime canônico | Não toca o runtime de investigação nem produz avaliação. |
| VI — Neutralidade de provedor | Não toca SDK, modelo ou configuração de provedor. |
| VII — Aprendizado é medido | Não altera aprendizado nem seus números. |
| VIII — Arquitetura em camadas | As telas consomem o gateway pelo cliente gerado; os dois campos novos são servidos pelas portas de persistência; nenhum import cruza a direção das camadas. |
| IX — Paridade por integração embutida | Os campos `node`/`unhealthy_since` nascem no contrato do estate, não num caminho especial do Proxmox — outra integração que registre placement/health os serve igual. |
| X — O operador é dono dos dados | Nada envia telemetria ou analytics; as telas leem o deployment do operador e os testes não gravam staging. |
| XI — Datastore único | Os campos do estate usam as portas existentes e suas implementações fake/Postgres; nenhum SQL fica fora de `platform/persistence/`. |
| XII — Test-first, rastreado | Os quatro acceptance specs e os contratos do estate são vermelhos antes; as métricas de agrupamento, primeiro paint e requests têm assertions nomeadas. |
| XIII — Idioma e atribuição | Código e paths novos em inglês; strings pelo catálogo `en`/`pt-BR`; nenhum segredo ou identificador de planejamento é commitado. |
| XIV — Composto ou não é entrega | Tudo aqui nasce em tela servida; os dois campos novos são consumidos pela mesma feature que os expõe. Nenhum mecanismo dormente. |
| Decisão 1 da onda (board é contrato) | O gate visual de EXECUCAO §3 é tarefa explícita com veredito por tela×tema. |
| Decisão 2 da onda (spec diz o que executa) | FRs nomeiam arquivo, rota, campo e valor; o que não estava cravado tem tarefa de caracterização na Fase 0 que crava antes de qualquer implementação. |

## Estrutura da execução (fan-out por tela)

```
specs_v8/060-telas-de-area/
├── spec.md          # este contrato
├── plan.md          # este plano
├── tasks.md         # fases 0–2 comuns + uma fase por tela + fechamento
└── evidence/
    └── visual/      # <rota>-{dark,light}.png + VEREDITO.md (fim do slot)
```

Ordem interna: Fase 0 (caracterização: cravar rotas/campos ainda não
cravados) → Fase 1 (acceptance red-first, os quatro em paralelo) → Fase 2
(contrato do estate, porque Recursos depende dele) → Fases 3–6 (as quatro
telas em paralelo, um implementer cada; Incidentes é o dono interno dos
single-write) → Fase 7 (integração, i18n aplicado, visual re-baseline,
gates).

## O que não muda

A chave de agrupamento e o shape de `IncidentGroup`; o contrato de
incidentes; a mecânica de filtros-na-URL (`readViewState`); os componentes
`Tabs`/`TabLinks`/`Panel` (reskin é da 000, uso é daqui); as abas completas
de O agente; a fila de propostas de conhecimento (só lida); qualquer arquivo
das features irmãs do slot.
