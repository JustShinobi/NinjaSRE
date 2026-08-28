# Implementation Plan: Run view narrado — a investigação conta o que faz, em frases, enquanto faz

**Branch**: `feat/v8-030-run-view-narrado` | **Date**: 2026-08-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v8/030-run-view-narrado/spec.md`

**Referência visual (DoD)**: `design/padrao-2026-08/RunView.dc.html` e
`RunViewLight.dc.html`, normativos (decisão 1 da onda); acceptance
`console/tests/e2e/run-view-narrado.acceptance.spec.ts` confirmado vermelho
antes da implementação. Viewport normativo: 1920×1080.

## Summary

Quatro movimentos sobre uma tela que já existe e um vocabulário que já é
fechado:

1. **Estágios visíveis.** O gateway **já serve** os estágios reconstruídos do
   trace: `GET /v1/runs/{run_id}/replay` devolve `stages[]` por
   `platform/runs/replay.py`, e o console lê esse corpo sem usar o campo. O
   movimento é do lado do console — o rail do artboard — e o backend só entra
   se algum campo do rail faltar; o console desenha o rail e, em run vivo,
   move o estágio ativo pelos eventos `stage_completed` que o stream por run
   já entrega.
2. **Narração no funil único.** A frase narrada nasce dentro do vocabulário
   que os dois leitores já compartilham (`console/src/surfaces/transcript.ts`)
   — um template i18n por kind de `STREAM_KINDS`, campos do payload como
   matéria-prima, frase genérica como piso. A view (`transcript-view.tsx`)
   passa a renderizar a frase como conteúdo primário e o payload atrás de
   `<details>`; um toggle de tela alterna Narrado/Bruto.
3. **Rail viva.** O redutor live (`console/src/live/reducer.ts`) passa a
   acumular uso (tokens/turnos, dos detalhes de `stage_completed` e eventos
   de turno) e recursos tocados (eventos de observação/evidência); os painéis
   de custo e de vínculos leem do estado live quando `running`, do replay
   quando não.
4. **Empty states honestos.** Em run vivo, os painéis da rail nunca afirmam
   ausência; a linha "primeiro turno ainda não chegou" substitui o empty
   state com call to action.

O que **não** muda: como o run se chama (`subjectOf`), o painel de report da
v7, os controles de condução, o stream por run e seu transporte, e qualquer
arquivo do par do slot (canal vivo de deployment).

## Technical Context

**Language/Version**: TypeScript (console Next 16.3.0); Python 3.12 só na
borda do gateway que expõe os estágios do trace já gravado.

**Primary Dependencies**:
`console/src/surfaces/transcript.ts` (vocabulário e os dois leitores),
`console/src/surfaces/transcript-view.tsx` (renderização),
`console/src/surfaces/labels.ts` (rótulos por kind),
`console/src/surfaces/screens/run-detail.tsx` (a tela),
`console/src/live/reducer.ts` + `console/src/live/store.ts` (acumulação live),
`console/src/i18n/*.ts` (frases, en + pt-BR — single-write desta feature no
slot), `gateway/http/routes/` rota de detalhe/replay do run,
`platform/runs/replay.py` + `gateway/http/routes/runs.py::replay` (os
estágios já servidos),
`config/constants/runs.py` (chaves de detail dos estágios),
`console/visual/screens.json` (telas do gate visual — single-write desta
feature no slot).

**Storage**: nenhum esquema novo. Tudo que a tela mostra já está gravado
(trace de eventos, `run_turns`, `tool_calls`) desde a v7.

**Testing**: vitest para a tabela de narração (completude contra
`STREAM_KINDS`, frase idêntica nos dois leitores, acumulação do redutor);
pytest de contrato para o campo de estágios servido; Playwright para o
acceptance (14 alegações, as staging-safe marcadas); suíte visual com
baselines novos do detalhe de run (vivo e encerrado, dois temas).

**Target Platform**: console web servido no k3s de staging
(`stg-ninjasre.lan.kyo.ninja`).

**Project Type**: console-pesado com uma exposição de leitura no gateway.

**Performance Goals**: narrar é formatação por evento já chegado — O(1) por
evento, sem leitura nova; o rail de estágios não adiciona request (vem no
detalhe/replay que a tela já lê).

**Constraints**: `make verify` verde partindo de verde; interseção nula com
010-canal-vivo (nenhum toque em endpoint SSE novo, chart, ou
`console/src/live/` além de redutor/tipos que esta feature estende);
`design/padrao-2026-08/` intocado (fundação congelada — token novo se pede à
000 via relatório); diff em `run-detail.tsx` contido a esta tela.

**Scale/Scope**: 17 frases × 2 idiomas; 1 componente novo de rail de
estágios; 1 campo de contrato (estágios) com documento de API e cliente
regenerados; 3 painéis da rail religados ao estado live; baselines visuais
de 2 telas × 2 temas.

## Constitution Check

| Artigo | Como este plano satisfaz |
|---|---|
| I — Evidência sobre asserção | O coração: painéis deixam de afirmar "nada registrado" sobre run vivo; toda frase narrada deriva de evento gravado; contagem exibida = contagem renderizada. |
| II — Autonomia limitada | Não toca laço de decisão; controles de condução preservados sem mudança de comportamento. |
| III — Leitura por padrão | Nada de escrita nova; a feature só lê o que o recorder da v7 grava. |
| IV — Segredo nunca chega ao agente | Não toca credenciais. Payloads exibidos já passam pelo masking existente do stream; a narração não desmascara nada — ela usa os mesmos campos que a view atual já imprime. |
| V — Um runtime canônico | Não toca runtime. |
| VI — Neutralidade de provedor | Frases não citam provedor; modelo aparece como dado (`payload.model`), não como template. |
| VII — Aprendizado é medido | Não toca aprendizado. |
| VIII — Arquitetura em camadas | A reconstrução de estágios usa `replay()` onde ele vive (core), exposta pela rota existente do gateway; console continua falando só pelo cliente gerado. |
| IX — Capacidades declaradas | Nenhuma capacidade nova. |
| X — O operador é dono dos dados | Nada sai do host; nenhuma request externa nova (fontes já são da fundação, self-hosted). |
| XI — Datastore único | Nenhum acesso novo a banco; o gateway lê o trace pela porta que o replay já usa. |
| XII — Test-first, rastreado | Acceptance e testes de completude vermelhos antes; caracterização do transcript atual antes da troca; efeito sobre a suíte sintética medido e reportado ("sem efeito" esperado). |
| XIII — Idioma e atribuição | Código e commits em inglês; frases pelo catálogo i18n em `en` e `pt-BR`; nenhum identificador de planejamento em arquivo committed. |
| XIV — Composto ou não foi entregue | Ver abaixo. |

### Qual composition root constrói isto

Não há objeto novo de backend: `stages[]` entra na resposta da rota de
detalhe/replay que o composition root do gateway já constrói e serve — a
prova de composição é o acceptance no staging lendo os estágios de um run
real. Os campos sumários da listagem e do resumo do detalhe continuam sendo
servidos pela 020. No console, o rail e o toggle montam dentro de
`RunDetailScreen`, que a
rota `/runs/[runId]` já serve. Nada nasce dormente: cada mecanismo novo
(frase, rail, acumulação) é alcançável na tela servida no mesmo slot em que
entra.

## Project Structure

```
console/src/surfaces/
  transcript.ts          # + narration(event, locale): frase por kind (funil único)
  transcript-view.tsx    # frase primária, <details> payload, modo Narrado/Bruto
  labels.ts              # rótulos por kind reusados pela narração
  stage-rail.tsx         # NOVO: o rail de estágios do artboard (vivo/encerrado)
  screens/run-detail.tsx # monta rail; religa custo/tocados ao estado live
console/src/live/
  reducer.ts             # + usage acumulado, + touched acumulado (mesmos eventos)
console/src/i18n/
  en.ts, pt-BR.ts        # 17 frases × 2, rótulos do toggle, linha "sem turno ainda"
gateway/http/routes/…    # detalhe/replay ganha stages[] do replay(); campos sumários são da 020
fixtures/contract/openapi.json, console/src/api/schema.ts  # regenerados
console/tests/e2e/run-view-narrado.acceptance.spec.ts      # 14 alegações
console/tests/unit/…     # completude da narração, funil único, redutor
console/visual/screens.json + baselines                    # run vivo/encerrado × 2 temas
specs_v8/030-run-view-narrado/evidence/                    # vermelhos, staging, visual/VEREDITO.md
```

## Decisões de plano

1. **Estágios viajam no corpo que a tela já lê** (detalhe ou replay — o que
   o contrato acomodar com menos cirurgia), reconstruídos por `replay()` no
   backend. Alternativa rejeitada: reconstruir estágios no console a partir
   do catch-up do stream — funciona para vivo, deixa o encerrado dependente
   de um catch-up que a tela encerrada não abre.
2. **A frase nasce em `transcript.ts`, não na view.** É o único ponto por
   onde replay e stream já passam; a view só escolhe entre frase e payload.
   Assim AN-10 (leitores idênticos) é propriedade de construção, não de
   disciplina.
3. **Acumulação live no redutor, não em efeito de componente.** `LiveState`
   ganha `usage` e `touched` derivados em `applyEvents` — puro, testável, e
   os testes de burst existentes cobrem a ordem.
4. **Toggle é estado local com padrão Narrado.** Sem URL state: a visão crua
   é ferramenta de depuração momentânea, não endereço compartilhável.
5. **Baselines**: as duas entradas de detalhe de run em
   `console/visual/screens.json` ganham captura nos dois temas; o aceite dos
   PNGs é commit revisado, conforme a mecânica pinada de
   `tools/console_visual.py`.
