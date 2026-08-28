# Tasks: Run view narrado — a investigação conta o que faz, em frases, enquanto faz

**Input**: Design documents from `specs_v8/030-run-view-narrado/`

**Prerequisites**: spec.md, plan.md, e o slot S0 da onda (fundação visual)
mergeado — tokens, ícones, formas e motion são consumidos aqui, nunca
definidos aqui.

**Tests**: acceptance-first. O acceptance spec das quatorze alegações normativas
aterrissa **antes** de qualquer implementação e é confirmado vermelho, com a
mensagem real de cada uma registrada.

**Marcação**: `[x]` é feita; `[ ]` é pendente; `[~]` é **encerrada sem
execução**, com a razão na própria linha. Um `[~]` nunca é um `[x]`
envergonhado.

## Regras que valem para toda tarefa deste arquivo

1. **Nada de identificador de planejamento em arquivo committed.** A
   substância vai no arquivo; a referência fica na spec.
2. **O artboard é o critério.** `design/padrao-2026-08/RunView.dc.html` e
   `RunViewLight.dc.html` decidem layout, tokens, formas e motion. Desvio é
   defeito ou vai para `DIVERGENCIAS.md` com aprovação do operador — nunca
   silencioso, nem "para melhor".
3. **Interseção nula com o par do slot.** Nenhuma tarefa toca endpoint SSE de
   deployment, chart, ou `console/src/live/store.ts` de deployment. O redutor
   por run (`reducer.ts`) é desta feature; o transporte não.
4. **A fundação está congelada.** Token, ícone ou forma que faltar é
   declarado no relatório final e aplicado pelo orquestrador via 000 — nunca
   editado aqui.
5. **Arquivo gerado é regenerado, nunca editado à mão** (documento de API,
   cliente TS, dataset simulado).
6. **Esta feature é dona dos single-write no slot** (`console/src/i18n/*.ts`,
   `console/src/shell/routes.ts`, `console/visual/screens.json`).
7. **Gate não é afrouxado para a mudança passar.**

---

## Phase 0: Linha de base

- [~] T001 (pinado pelo despacho, não re-rodado aqui) Rodar `make verify` na árvore intacta e guardar o log fora do
      repositório: exit code, contagem de testes, quais falham. Se não estiver
      verde, parar e reportar. Resultado pinado: exit 2, 12972 passed, 9 failed
      (todos o mesmo teste de rede real, fora do escopo de arquivo desta
      feature), 39 skipped.
- [ ] T002 Registrar a contagem e o resultado da suíte de cenários sintéticos
      — o "antes" da medição que test-first exige. "Sem efeito" é resposta
      aceitável ao final; "não medido" não é.
- [~] T003 **Executada pelo orquestrador** (a worktree não alcança staging
      nem o Orca browser): capturar o estado atual da tela no staging como
      evidência do "antes" — run vivo e run encerrado, dois temas, via Orca
      browser, para `evidence/visual/antes/`.

## Phase 1: Vermelho primeiro

- [x] T004 Escrever
      `console/tests/e2e/run-view-narrado.acceptance.spec.ts` codificando as
      quatorze alegações normativas, uma asserção nomeada por alegação, viewport
      1920×1080, marcando staging-safe as declaradas na spec (o run disparado
      pelo teste reutiliza o único fixture de run criado por 010 no slot S1 e
      nunca cria um segundo run nem destrói dado). Confirmar vermelho e
      registrar a mensagem real de cada alegação.
- [x] T005 [P] Teste de unidade: completude da narração — para cada chave de
      `STREAM_KINDS` existe frase no catálogo `en` e no `pt-BR`; um kind fora
      do vocabulário rende a frase genérica nomeando o kind. Confirmar
      vermelho (a tabela ainda não existe).
- [x] T006 [P] Teste de unidade: funil único — a mesma fixture de eventos
      servida como replay e como stream rende frases idênticas, evento a
      evento. Confirmar vermelho.
- [x] T007 [P] Teste de unidade do redutor: uma sequência com eventos de
      estágio e de observação acumula `usage` (tokens, turnos) e `touched`
      (recursos) no estado; eventos fora de ordem passam pelo `held` sem
      dupla contagem. Confirmar vermelho.
- [x] T008 [P] Teste de contrato (pytest): o corpo servido para um run com
      trace gravado carrega os estágios com nome, duração, finding e falha, na
      ordem executada — reconstruídos do trace, não de lista fixa. O corpo de
      replay já serve `stages[]`, então este teste pode nascer **verde** para o
      run encerrado: registrar isso como o resultado real, e isolar o vermelho
      no que de fato falta (o caminho vivo, e qualquer campo do rail ausente).
      Um vermelho fabricado é pior que um verde honesto.
- [~] T009 (coberto por suíte existente, não duplicado) Caracterização (verde, protege o que fica): o painel de report da
      v7 (headline, markdown renderizado, copiar) e os controles de condução
      renderizam como hoje nos dois estados do run.

## Phase 2: O gateway serve os estágios

- [x] T010 Confrontar `stages[]` já servido por
      `GET /v1/runs/{run_id}/replay` (`platform/runs/replay.py`) contra o que o
      rail do artboard precisa. Acrescentar somente o campo que faltar, no
      mesmo caminho de reconstrução; run sem trace serve lista vazia, nunca
      erro. Registrar no controle o confronto campo a campo — inclusive
      "nada faltou", se for o caso.
- [x] T011 Regenerar documento de API e cliente TS **se** T010 acrescentou
      campo; dataset simulado passa a servir estágios em todo run que descreve
      (vivo com estágio ativo, encerrado completo, um com estágio falhado).
      T008 verde em todos os caminhos.

## Phase 3: O console narra

- [x] T012 Tabela de narração no vocabulário compartilhado do transcript:
      frase por kind composta dos campos já extraídos (`title`, `detail`,
      `status`, `durationMs`), frase genérica como piso, ausência declarada
      quando um campo falta. T005 e T006 ficam verdes.
- [x] T013 As 17 frases × 2 idiomas no catálogo i18n, mais rótulos do toggle
      (Narrado/Bruto), a linha "o primeiro turno ainda não chegou", e os seis
      nomes de estágio — `en` e `pt-BR`, tom do artboard.
- [x] T014 A view do transcript renderiza a frase como conteúdo primário com
      o payload atrás de `<details>` fechado; o toggle global alterna para a
      visão Bruto (payloads integrais); "Copy the raw payload" sai do caminho
      primário. AN-03/04/05 do acceptance ficam verdes.
- [x] T015 Componente do rail de estágios conforme o artboard: concluído com
      check e duração, ativo com anel pulsante da fundação, futuro numerado,
      falhado com forma de falha; ordem vinda do dado. Montado no topo de
      `run-detail.tsx`, vivo (movido pelos eventos do stream) e encerrado
      (estático do registro). AN-01/02 ficam verdes.
- [x] T016 Redutor acumula `usage` e `touched`; painéis de custo e "O que
      tocou" leem do estado live quando o run está vivo e do replay quando
      não; "Descobertas até agora" lista findings dos estágios concluídos com
      forma de status; empty states vivos substituídos pela linha honesta.
      T007 e AN-06/07/08 ficam verdes.
- [x] T016a Reformar a lista de runs — `/runs`, em
      `console/src/surfaces/screens/runs.tsx`; `/investigations` é
      redirecionamento legado e fica intocado — conforme
      `design/padrao-2026-08/Investigations.dc.html` (AN-14/FR-021a): vivos
      como cards com barra de estágios, completados com headline inteira e
      chip de alegações com forma, falhados com estágio e link, filtros como
      chips. Estender o acceptance da feature com a asserção da lista
      (vermelho antes desta task).
- [~] T017 (parcial — sem passada dedicada de comparação; ver controle) Passe final da tela contra o artboard: grid, espaçamentos, chips,
      tipografia e motion pelos tokens da fundação; contagem do cabeçalho
      derivada da lista renderizada (AN-09); estados vivo/encerrado dos
      controles (AN-12).

## Phase 4: Gates locais

- [x] T018 Suítes de unidade do console e do gateway verdes; acceptance verde
      no harness local (mock backing); a suíte transversal da onda passa (sem
      JSON primário, sem hash como título — regressões de outras features não
      introduzidas aqui).
- [ ] T019 `console/visual/screens.json`: detalhe de run vivo e encerrado nos
      dois temas; recapturar baselines na imagem pinada
      (`tools/console_visual.py accept`) e commitar o aceite como revisão.
- [~] T020 (do orquestrador, no merge do slot) `make verify` completo, verde, partindo do verde de T001.

## Phase 5: Staging e o gate visual da onda

Executada pelo orquestrador no fim do slot, com os dois diffs mergeados
(protocolo da onda §3–§4).

- [~] T021 (do orquestrador — staging real) Após `make deploy-stg COMPONENTS=web` e Argo Synced+Healthy:
      acceptance staging-safe contra `https://stg-ninjasre.lan.kyo.ninja`,
      incluindo o run disparado pela UI; registrar o log em `evidence/`.
- [~] T022 (do orquestrador — Orca Browser) Captura Orca browser: `/investigations`, `/runs/<run-vivo>` e `/runs/<run-encerrado>`
      nos dois temas (alternância pelo botão de tema), para
      `evidence/visual/`; comparação estrutural contra `RunView.dc.html` e
      `RunViewLight.dc.html`; veredito linha a linha em
      `evidence/visual/VEREDITO.md`. Qualquer desvio: corrigir, ou
      DIVERGENCIAS.md com aprovação do operador — sem terceiro caminho.
- [~] T023 (do orquestrador — leitura direta do trace store) Evidência de contagem: número de eventos na tela do run do
      acceptance = número de eventos no trace do banco para o mesmo run;
      registrar as duas contagens no relatório final.
