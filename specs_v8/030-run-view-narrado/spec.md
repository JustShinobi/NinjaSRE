# Feature Specification: Run view narrado — a investigação conta o que faz, em frases, enquanto faz

**Feature Branch**: `feat/v8-030-run-view-narrado`

**Created**: 2026-08-27

**Status**: Draft

**Input**: User description: "A tela do run mostra cada evento como bloco JSON
com 'Copy the raw payload'; o custo mostra empty state durante o run; os seis
estágios do pipeline não aparecem em lugar nenhum da tela que os executa. O
board manda: pipeline de estágios no topo, transcript narrado por tipo de
evento com o payload atrás de um disclosure, e a rail direita viva —
descobertas, recursos tocados, custo por turno — durante o run, não só depois."

**Referência visual (DoD)**: `design/padrao-2026-08/RunView.dc.html` (tema
escuro) e `design/padrao-2026-08/RunViewLight.dc.html` (tema claro) são os
mockups **normativos** — decisão 1 da onda: desvio não registrado em
`design/padrao-2026-08/DIVERGENCIAS.md` é defeito. O acceptance spec é
`console/tests/e2e/run-view-narrado.acceptance.spec.ts`, confirmado
**vermelho antes de qualquer implementação**. Os dados dos artboards são
exemplo; a comparação do gate visual é estrutural (layout, tokens, ícones,
formas, motion), nunca de dado.

**Viewport normativo de medição**: 1920×1080.

**Evidência**: auditoria de uso do staging em 2026-08-27, run
`0951c31e19e24c609e41b17d509f3205`, disparado pela UI com o objetivo "Procure
anomalias no cluster proxmos"; specs_v8/README.md, "Evidências de partida".

---

## Fatos verificados em 2026-08-27 (não re-derivar)

1. **O transcript imprime JSON como conteúdo primário.** Cada evento da tela
   do run em staging é um bloco `{...}` com o link "Copy the raw payload"
   embaixo. A fonte: `eventFromStream`
   (`console/src/surfaces/transcript.ts:269`) põe em `payload` o documento
   inteiro serializado por `payloadOf` (`transcript.ts:114`), e a view o
   renderiza aberto.
2. **O vocabulário de eventos já existe e é fechado.** `STREAM_KINDS`
   (`console/src/surfaces/transcript.ts:126-144`) mapeia 17 kinds crus
   (`run_started`, `turn_started`, `model_reasoned`, `tool_called`,
   `tool_succeeded`, `tool_failed`, `observation_recorded`,
   `evidence_retained`, `memory_recalled`, `subagent_dispatched`,
   `subagent_returned`, `guardrail_withheld`, `guardrail_applied`,
   `interaction_opened`, `interaction_answered`, `run_completed`,
   `run_failed`) para 11 `TranscriptKind`; `kindOf` devolve `reasoning` para
   kind desconhecido. Não há frase narrada em lugar nenhum — título do evento
   é `payload.name` ou o próprio kind cru.
3. **Os estágios existem, são seis, e a tela não os mostra.** `STAGE_ORDER`
   vive em `core/state/types.py`; o pipeline emite `stage_start`/`stage_end`
   por estágio (`core/pipeline/lifecycle.py:176-192`) com detail carregando
   `finding`, `llm_calls`, `prompt_tokens`, `completion_tokens`
   (`config/constants/runs.py`, constantes `STAGE_DETAIL_*`), e
   `replay(events)` (`core/pipeline/streaming.py:329`) já reconstrói
   `InvestigationView.stages` com início, fim e falha por estágio. Nada disso
   chega à tela: o operador viu "Reasoning stage_completed" seguido do JSON.
4. **A tela é `RunDetailScreen`**
   (`console/src/surfaces/screens/run-detail.tsx:66`), servida por
   `console/src/app/(shell)/runs/[runId]/page.tsx`. Ela lê 4 rotas
   (`/v1/runs/{run_id}`, `/v1/runs/{run_id}/replay`, `/v1/incidents`,
   `/v1/investigations/{run_id}/interactions`); um run vivo renderiza
   `LiveRun` sobre o stream por run, um encerrado renderiza `Transcript`
   sobre o replay ("dois leitores, um vocabulário", `transcript.ts:261-268`).
5. **O custo de um run vivo nasce vazio.** `usageFrom(replayed)`
   (`run-detail.tsx:115`) computa só do replay; no staging o painel "Cost
   and tokens" exibiu o empty state ("No cost recorded") com o run em
   andamento e turnos já registrados — os dados chegaram só em re-render
   posterior. As tabelas `run_turns`/`tool_calls` são graváveis desde a v7
   (recorder composto, verificação independente PASS).
6. **"O que tocou" não vive.** `touched_resources` é lido uma vez do registro
   do run (`run-detail.tsx:130`); durante o run em staging o painel mostrou
   "Nothing linked yet" com evento de observação já no stream.
7. **A camada live já ordena e reduz.** `LiveState`/`applyEvents`
   (`console/src/live/reducer.ts:99,269`) aplicam eventos por `sequence`,
   seguram os que chegam cedo, e derivam fase, esperas e decisões; os testes
   `console/tests/unit/live/reducer.test.ts` e
   `console/tests/unit/surfaces/run-detail-live-transcript.test.tsx` cobrem o
   caminho. A oscilação "Reconnecting" observada é da conexão, não do
   redutor, e pertence à feature do canal vivo.
8. **Os controles de run vivo já existem e ficam.** `TakeoverControls`,
   `AddContext`, e os painéis de interação aberta (`run-detail.tsx:326-372`)
   correspondem ao que o artboard desenha (Assumir/Parar, "Diga algo…").

---

## Alegações normativas

Frases curtas, individualmente testáveis; o acceptance spec codifica cada
uma. As marcadas **[staging]** são staging-safe (leitura e o fixture único de
run disparado pela UI no slot S1, criado pela 010 e reutilizado por esta
feature, conforme o protocolo da onda).

- **AN-01** O detalhe de um run mostra os seis estágios do pipeline, na ordem
  de execução, no topo da página. **[staging]**
- **AN-02** Um estágio concluído mostra a própria duração; o estágio ativo é
  visualmente distinto dos concluídos e dos futuros; um futuro mostra o
  próprio número. **[staging]**
- **AN-03** Com a visão em Narrado, nenhum bloco JSON está visível no
  transcript. **[staging]**
- **AN-04** Cada evento do transcript narrado é uma frase no idioma do
  operador, composta pelo tipo do evento, e o payload bruto do evento está
  atrás de um disclosure fechado por padrão. **[staging]**
- **AN-05** A visão Bruto mostra os payloads integrais; alternar entre
  Narrado e Bruto não perde nem duplica evento.
- **AN-06** Durante um run vivo com ao menos um turno registrado, o painel de
  custo mostra tokens e turnos — nunca um empty state. **[staging]**
- **AN-07** Durante um run vivo, um recurso tocado aparece no painel "O que
  tocou" quando o evento que o registra chega, sem reload.
- **AN-08** "Descobertas até agora" lista o finding de cada estágio concluído
  que registrou um, cada um com sua forma de status.
- **AN-09** A contagem de eventos no cabeçalho do transcript é igual ao
  número de eventos renderizados no corpo. **[staging]**
- **AN-10** Um run encerrado renderiza as mesmas frases narradas que o vivo
  renderizou para os mesmos eventos.
- **AN-11** Todo kind do vocabulário do stream tem frase narrada; um kind
  desconhecido rende uma frase genérica que nomeia o kind, nunca JSON cru.
- **AN-12** Os controles de condução (Assumir, Parar, "Diga algo…") existem
  em run vivo e não existem em run encerrado. **[staging]**
- **AN-13** Nos dois temas, a tela corresponde estruturalmente ao artboard —
  veredito do gate visual da onda, por captura no staging. **[staging]**
- **AN-14** A LISTA de `/investigations` é reformada conforme
  `design/padrao-2026-08/Investigations.dc.html` (acrescentado ao board em
  2026-08-27 pela decisão 8 da onda): runs vivos primeiro como cards com
  losango pulsante, barra de seis estágios e tempo decorrido; completados
  como linhas com headline de frase inteira (nunca truncada no meio de
  palavra), chip de alegações com forma (círculo pleno / anel parcial),
  duração e gatilho; falhados com quadrado vermelho, o estágio onde pararam
  e link para o transcript; filtros como chips. Os dados (título, estágio)
  são os que a listagem já serve — com os campos da feature de título vivo
  quando presentes, degradando sem eles. **[staging]**

## User Scenarios & Testing *(mandatory)*

### User Story 1 - O operador entende o que a investigação está fazendo (Priority: P1)

Um operador dispara "Procurar anomalias no cluster Proxmox" e fica olhando. A
página diz, em frases: que o Proxmox foi consultado e o que voltou, que uma
hipótese foi registrada, em que estágio dos seis o run está e há quanto
tempo. Ele nunca precisa ler `{"completion_tokens": 104, ...}` para saber o
que aconteceu — mas pode, atrás do disclosure, quando quiser conferir.

**Why this priority**: é a tela onde o produto se vende ou se enterra. A
investigação de hoje produz root cause correto em 2m43s e o operador assiste
a isso como um despejo de JSON — o valor existe e a tela o esconde. É o
defeito nomeado pela decisão 5 da onda.

**Independent Test**: disparar um run pela UI no staging e conferir na página
do run: seis estágios no topo com o ativo distinto, frases no lugar de JSON,
payload só atrás de disclosure.

**Acceptance Scenarios**:

1. **Given** um run vivo, **When** a página renderiza, **Then** o topo mostra
   os seis estágios na ordem de execução com o ativo visualmente distinto.
2. **Given** um evento `tool_succeeded` no stream, **When** ele chega,
   **Then** o transcript ganha uma frase que nomeia a capacidade chamada e o
   que ela devolveu, no idioma do operador.
3. **Given** qualquer evento narrado, **When** o operador abre o disclosure,
   **Then** o payload bruto integral está lá.
4. **Given** a visão em Narrado, **When** o corpo do transcript é inspecionado,
   **Then** não há bloco JSON visível.
5. **Given** um estágio que terminou, **When** o rail de estágios renderiza,
   **Then** aquele estágio mostra a duração que o stream registrou para ele.

---

### User Story 2 - A rail direita vive junto com o run (Priority: P1)

Enquanto o run anda, a coluna direita acompanha: as descobertas de cada
estágio concluído aparecem, os recursos tocados pingam um a um, e o custo
mostra tokens e turnos desde o primeiro turno. Nada na página afirma "nada
registrado" sobre um run que está registrando.

**Why this priority**: os três painéis existem hoje e mentem durante o run
("No cost recorded", "Nothing linked yet") — afirmação do negativo sobre uma
leitura que simplesmente ainda não olhou o stream, o mesmo defeito que a v7
baniu das telas de incidente.

**Independent Test**: com um run vivo que já registrou um turno, conferir que
o painel de custo mostra números e que um recurso tocado aparece sem reload.

**Acceptance Scenarios**:

1. **Given** um run vivo com um turno registrado, **When** o painel de custo
   renderiza, **Then** ele mostra tokens e contagem de turnos, e nenhum empty
   state.
2. **Given** um evento de observação que registra um recurso, **When** ele
   chega pelo stream, **Then** o chip do recurso aparece em "O que tocou" sem
   reload.
3. **Given** dois estágios concluídos com findings, **When** a rail renderiza,
   **Then** "Descobertas até agora" lista os dois findings, cada um com sua
   forma de status.
4. **Given** um run que ainda não registrou turno nenhum, **When** o painel de
   custo renderiza, **Then** ele diz que o primeiro turno ainda não chegou —
   uma linha, não um empty state com call to action.

---

### User Story 3 - O run encerrado conta a mesma história (Priority: P2)

Quem abre o run no dia seguinte lê o mesmo transcript narrado, os mesmos seis
estágios com suas durações, o mesmo custo — reconstruído do registro, não do
processo que rodou.

**Why this priority**: "dois leitores, um vocabulário" já é a regra do
transcript (`transcript.ts`); a narração tem de entrar nesse mesmo funil, ou
o vivo e o registrado divergem — e o registrado é o que auditoria e
pós-mortem leem.

**Independent Test**: abrir um run encerrado e comparar as frases com as que
o mesmo run mostrou vivo (fixture com os mesmos eventos).

**Acceptance Scenarios**:

1. **Given** um run encerrado, **When** a página renderiza, **Then** o rail de
   estágios mostra os estágios executados com suas durações, e nenhum anel de
   ativo.
2. **Given** os mesmos eventos servidos por replay e por stream, **When** os
   dois caminhos renderizam, **Then** as frases narradas são idênticas.
3. **Given** um run encerrado, **When** a página renderiza, **Then** não há
   controles de condução.

---

### Edge Cases

- **Kind desconhecido no stream.** Um deployment mais novo emite um kind que
  este console não conhece. `kindOf` já degrada para `reasoning`; a narração
  degrada para a frase genérica que nomeia o kind cru. Nunca JSON como
  conteúdo primário, nem frase vazia.
- **Payload sem os campos que a frase usa.** Frase composta com ausência
  declarada ("uma capacidade" quando `name` falta), nunca `undefined`
  interpolado. A frase genérica é o piso.
- **Estágio que falhou.** O rail o mostra com a forma de falha (quadrado
  vermelho) e a duração até a falha; os estágios seguintes ficam como
  futuros que não virão — o run encerrou. `InvestigationView.stages` já
  carrega `failed` por estágio.
- **Run parado antes do primeiro estágio.** O rail mostra os seis como
  futuros; o transcript mostra o que houver; o custo diz que nenhum turno
  chegou. O caso `failedBeforeStart` (`run-detail.tsx:141`) continua com sua
  linha única.
- **Run com mais estágios executados que o vocabulário local** (pipeline
  encurtado ou estendido por configuração): o rail desenha os estágios que o
  registro nomeia, na ordem do registro — a ordem canônica é a do dado, não a
  do hardcode.
- **Evento que chega fora de ordem.** Já é problema resolvido do redutor
  (`held` em `LiveState`); a narração não introduz caminho novo de ordenação.
- **Toggle durante chegada de eventos.** Alternar Narrado/Bruto é estado de
  visão; nenhum evento é perdido nem re-pedido — os dois lados renderizam da
  mesma lista.
- **Locale.** Frases pelo catálogo i18n em `en` e `pt-BR`; dado do payload
  (nomes de capacidade, hosts) fica como veio.

## Requirements *(mandatory)*

### O rail de estágios

- **FR-001**: O detalhe de um run DEVE mostrar os estágios do pipeline na
  ordem de execução, no topo da página, conforme o artboard.
- **FR-002**: O dado dos estágios DEVE vir do registro do run servido pelo
  gateway (os eventos de estágio que o stream e o trace já carregam),
  nunca de uma lista fixa no console.
- **FR-003**: Um estágio concluído DEVE mostrar sua duração; um falhado, a
  forma de falha; o ativo, o anel pulsante do artboard; um futuro, seu
  número.
- **FR-004**: Em run vivo, a transição de estágio DEVE mover o rail sem
  reload, pelo mesmo stream que o transcript já consome.
- **FR-005**: Em run encerrado, o rail DEVE ser reconstruído do registro e
  mostrar durações finais, sem estado ativo.

### O transcript narrado

- **FR-006**: Todo kind do vocabulário do stream DEVE ter uma frase narrada
  no catálogo i18n, em `en` e `pt-BR`.
- **FR-007**: A frase DEVE ser composta no único ponto por onde os dois
  leitores já passam, de modo que replay e stream rendam frases idênticas
  para o mesmo evento.
- **FR-008**: A frase de um evento de ferramenta DEVE nomear a capacidade e
  resumir o desfecho; a de hipótese, a hipótese; a de raciocínio, o
  raciocínio — os campos que `eventFromStream` já extrai (`title`, `detail`,
  `status`, `durationMs`) são a matéria-prima.
- **FR-009**: Um kind desconhecido DEVE render a frase genérica que nomeia o
  kind cru. JSON NUNCA é o conteúdo primário de um evento.
- **FR-010**: O payload bruto de cada evento DEVE existir atrás de um
  disclosure fechado por padrão, na visão Narrado.
- **FR-011**: A tela DEVE oferecer o toggle Narrado/Bruto do artboard; Bruto
  mostra os payloads integrais; a escolha não altera a lista de eventos.
- **FR-012**: A contagem de eventos exibida DEVE ser derivada da mesma lista
  que o corpo renderiza.
- **FR-013**: O link "Copy the raw payload" por evento DEVE deixar de ser
  conteúdo primário; copiar o payload continua possível a partir do
  disclosure aberto.

### A rail viva

- **FR-014**: Durante um run vivo com turno registrado, o painel de custo
  DEVE mostrar tokens e turnos acumulados dos eventos já chegados; o empty
  state é proibido nesse estado.
- **FR-015**: Sem turno registrado ainda, o painel de custo DEVE dizer isso
  em uma linha, sem call to action.
- **FR-016**: "O que tocou" DEVE acrescentar o chip de um recurso quando o
  evento que o registra chega, sem reload; em run encerrado DEVE continuar
  lendo `touched_resources` do registro.
- **FR-017**: "Descobertas até agora" DEVE listar o finding de cada estágio
  concluído que registrou um, com a forma de status do artboard, vivo e
  encerrado.
- **FR-018**: Nenhum painel da tela DEVE afirmar ausência ("nada registrado",
  "nada vinculado") enquanto o run está vivo e o dado simplesmente ainda não
  chegou — a ausência afirmada é só do registro encerrado.

### Identidade e fronteiras

- **FR-019**: O título da página DEVE continuar vindo de `subjectOf` — esta
  feature não muda como um run se chama; isso é da feature de título vivo.
- **FR-020**: Os controles de condução e os painéis de interação DEVEM
  permanecer como estão, reestilizados pelos tokens da fundação, sem mudança
  de comportamento.
- **FR-021**: O painel de relatório da v7 (headline, report renderizado,
  copiar markdown) DEVE permanecer; num run encerrado ele continua sendo o
  primeiro painel.
- **FR-021a**: A lista de `/investigations` DEVE renderizar conforme AN-14,
  no mesmo arquivo de surface que a serve hoje; nenhuma rota nova — a
  reforma é de apresentação sobre a resposta existente da listagem.
- **FR-022**: Esta feature NÃO DEVE tocar `console/src/live/` além do que a
  acumulação de custo/tocados exigir do redutor, e NÃO DEVE tocar gateway de
  stream — o canal do deployment é da feature par do slot.

### Contrato e artefatos

- **FR-023**: O detalhe/replay DEVE expor a sequência detalhada `stages[]`,
  com duração e finding, pelo contrato regenerado e pelo dataset simulado.
  Os campos sumários `last_completed_stage` e `stage_index` continuam sendo
  os campos da 020; esta feature não os duplica nem cria outra fonte.
- **FR-024**: O registro de telas visuais DEVE cobrir o detalhe de run vivo e
  encerrado nos dois temas, com baselines novos aceitos por commit.

## Key Entities

- **Estágio de run** — nome, início, fim, duração, falha, finding; nasce dos
  eventos `stage_start`/`stage_end` do pipeline; `InvestigationView.stages`
  já o reconstrói no backend.
- **Frase narrada** — a leitura humana de um evento: template i18n escolhido
  pelo kind + campos extraídos do payload. Uma por evento, idêntica nos dois
  leitores.
- **Visão do transcript** — Narrado ou Bruto; estado de tela, não de dado.
- **Uso acumulado** — tokens/turnos derivados dos eventos chegados de um run
  vivo; converge para o que o replay serve quando o run encerra.

## Success Criteria *(mandatory)*

- **SC-001**: Num run vivo disparado pela UI no staging, os seis estágios
  aparecem no topo e o ativo é distinguível sem ler texto (forma + motion).
- **SC-002**: Com a visão em Narrado, zero blocos JSON visíveis no corpo do
  transcript — contado por seletor no acceptance.
- **SC-003**: Todo kind de `STREAM_KINDS` tem frase em `en` e `pt-BR`;
  teste de unidade compara as chaves do catálogo com o vocabulário e falha
  se um kind ficar sem frase.
- **SC-004**: Durante o run vivo do acceptance, o painel de custo mostrou
  número de tokens > 0 antes do run encerrar.
- **SC-005**: Frases de replay e de stream idênticas para a mesma fixture de
  eventos — asserção de igualdade, não de semelhança.
- **SC-006**: A contagem do cabeçalho do transcript é igual ao número de
  eventos renderizados, vivo e encerrado, no staging.
- **SC-007**: Captura Orca dos dois temas contra os artboards com veredito
  CONFORME registrado em `evidence/visual/VEREDITO.md`.
- **SC-008**: O acceptance spec foi confirmado vermelho antes da
  implementação, com a mensagem real de cada alegação registrada.
- **SC-009**: `make verify` termina verde, tendo partido de verde.

## Assumptions

- **Os eventos de estágio chegam ao console.** O stream por run já carrega
  `stage_completed` (observado no staging com payload de finding e tokens); o
  que falta é renderização, não emissão. Se o catch-up de um run encerrado
  não servir os eventos de estágio, o plano expõe os estágios reconstruídos
  (`replay()` do backend) por campo do contrato — decisão de plano, não de
  spec.
- **A fundação visual já aterrissou** (slot S0): tokens, fontes, ícones,
  formas e primitivas de motion existem; esta feature os usa e não os define.
- **A feature é dona dos single-write no S1** (i18n, routes.ts,
  screens.json); o par (canal vivo) é gateway/chart/live-store e não os toca.
- **O run disparado pelo acceptance no staging é barato e seguro** — mesma
  classe do que o protocolo da onda já permite; propose-only segue valendo.

## Dependencies

- **000-fundacao-visual** (slot anterior): tokens, ícones, motion, chip.
- **Par do slot: 010-canal-vivo.** Interseção nula declarada: 010 é gateway
  (endpoint SSE de deployment), chart e `console/src/live/store.ts` de
  deployment; esta é surfaces do run + vocabulário do transcript. O stream
  **por run** que esta feature consome já existe e não é mexido por nenhuma
  das duas.
- **É pré-requisito visual da 050-painel-vivo**: as barras de estágio dos
  cards do Painel reusam o dado de estágio que esta feature faz o gateway
  servir.

## Out of Scope

- O canal SSE de escopo deployment e a conexão que oscila "Reconnecting"
  (010-canal-vivo).
- Como um run se chama — título provisório do objetivo, headline no fim
  (020-titulo-vivo). Esta tela lê o que a API servir.
- O cartão de decisão e qualquer coisa de `/decisions` (040).
- O Painel e suas barras de estágio (050).
- Renderização do report e headline (entregues na v7; permanecem).
- Qualquer mudança de emissão de eventos no pipeline Python além de servir
  os estágios já registrados.
