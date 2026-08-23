# Feature Specification: Leitura do relato — o console lê o que a investigação registrou

**Feature Branch**: `feat/v7-010-leitura-do-relato`

**Created**: 2026-08-23

**Status**: Draft

**Input**: User description: "O console lê o que a 001 gravou. Nenhuma tela volta
a imprimir `###` cru; o título de um run é uma sentença; o transcript mostra as
tool calls reais; o custo é real; markdown vira leitura renderizada. Controles de
run vivo não aparecem em run terminado, e as telas de runs saem da allowlist dos
bans transversais."

**Referência visual (DoD)**: não há mockup. Esta onda substituiu o mockup
normativo pela seção **[Alegações normativas](#alegações-normativas)** deste
documento — frases curtas, individualmente testáveis, que
`console/tests/e2e/010-leitura-do-relato.acceptance.spec.ts` codifica e que são
confirmadas **vermelhas antes de qualquer mudança de tela**. As duas telas desta
feature são rework de telas existentes (`/runs` e `/runs/{id}`), não telas novas,
então nenhum mockup HTML precisa ser desenhado antes.

**Viewport normativo de medição**: **1920×1080**. Toda alegação que fala de
rolagem, de largura ou de recorte de texto é medida nesse viewport, e a evidência
visual é capturada nele.

## Fatos verificados (2026-08-23 — não re-derivar)

Cada item abaixo foi visto no staging, confirmado no banco ou lido no código com
`file:line`. A spec os trata como fatos.

1. **O documento inteiro é o título.** `readFailure`
   (`console/src/surfaces/failures.ts:125-155`) devolve `title: raw` — o texto
   completo — quando o texto não parece uma exceção levantada. Todo
   `agent_runs.summary` recente do staging começa com `###`, então o título é o
   documento.
2. **Três superfícies consomem esse título.** `run-detail.tsx:96` calcula
   `said = readFailure(...)`, `:129` faz `title = said.title` para o `PageHeader`,
   `:190` imprime `said.title` num `<p>` do painel "What this investigation
   found"; `runs/[runId]/page.tsx:42-55` repete o cálculo para o `<title>` da aba;
   `runs.tsx:85` repete para a coluna SUBJECT.
3. **Não existe renderizador de markdown no console.** `console/package.json`
   declara três dependências de runtime: `next`, `react`, `react-dom`. Nenhum
   `remark`, `marked`, `markdown-it` ou equivalente.
4. **O console não conhece os status que o produto emite.** O domínio declara
   `RunStatus = completed | partial | cancelled | failed`
   (`core/agent/runtime_port.py:28-39`). O console declara
   `RUN_STATUSES = queued | running | waiting | succeeded | failed | cancelled`
   (`console/src/design/status.ts:20-27`), a tabela `DECLARED`
   (`:189-196`) repete essa lista, e `isSettled`
   (`:333-335`) reconhece `succeeded | failed | cancelled`.
   **Consequência mecânica, e é a causa do defeito das telas:** para um run
   `completed`, `isSettled` devolve `false`, `run-detail.tsx:86` conclui
   `running = true`, o caminho vivo é renderizado (daí "Paused in the background",
   `live.connection.idle`) e o painel Control aparece porque a condição é
   `steerable && running` (`:261`). O badge desenha `completed` como palavra
   desconhecida, em neutro.
5. **As fixtures escondem isso.** `fixtures/scenarios/populated/runs.json` e
   `run-detail.json` gravam `status: "succeeded"` — um valor que o enum do domínio
   não emite. Por isso toda suíte de console passa enquanto o staging está
   quebrado.
6. **O replay não carrega relato.** `RunReplayView`
   (`gateway/http/routes/runs.py:28-34`) traz `run_id`, `turns`, `total_cost`,
   `total_tokens`, `is_interrupted`. O campo `summary` que `eventsFromReplay`
   (`console/src/surfaces/transcript.ts:214-224`) lê é **injetado pela tela**
   (`run-detail.tsx:104-107`), não vem do deployment.
7. **O custo é apurado por rateio, e a tela diz isso.** `usageFrom`
   (`transcript.ts:320-346`) divide `total_cost`/`total_tokens` pelo número de
   turnos. Com zero turnos gravados no staging, `byTurn` é vazio e o painel cai no
   estado "No cost recorded".
8. **`dangerouslySetInnerHTML` existe em exatamente um arquivo do console**,
   `src/app/layout.tsx` (3 usos, todos sobre string que o próprio console gerou).
   Nenhuma superfície o usa.
9. **Vínculos são derivados de uma busca na lista de incidentes.**
   `run-detail.tsx:110-112` procura em `/v1/incidents` um registro cujo `run_id`
   bata com o da URL; o painel "What this investigation touched" só tem conteúdo
   se essa busca acertar.
10. **A allowlist transversal é uma tabela nomeada.** `EXCEPTIONS`
    (`console/tests/e2e/transversal-rules.spec.ts:166`) é hoje uma lista vazia de
    `{ path, rule, reason }`, e `ROUTES_UNDER_THESE_RULES` (`:136-141`) é o
    conjunto de rotas que a suíte percorre. A feature de governança desta onda
    acrescenta os bans novos e nasce com as telas de runs na allowlist; esta
    feature as remove de lá.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - O nome de uma investigação é uma sentença (Priority: P1)

Um operador abre a lista de investigações e reconhece cada linha pelo que ela
investigou. Abre uma delas e a aba do navegador, o cabeçalho da página e a coluna
de onde ele veio dizem a mesma sentença. Em lugar nenhum ele lê `###`, `**` ou
uma crase.

**Why this priority**: é o defeito que torna o produto ilegível. Um operador com
três investigações abertas não distingue nenhuma delas hoje: as três abas
começam com "### Incident Findings & Root Cause Analysis".

**Independent Test**: abrir `/runs`, ler as células de SUBJECT, abrir uma linha,
ler o `<title>` da aba e o `<h1>` — nenhum dos três contém caractere de sintaxe
markdown, e os três dizem a mesma coisa.

**Acceptance Scenarios**:

1. **Given** um run cujo registro tem headline, **When** a tela de detalhe abre,
   **Then** o cabeçalho da página mostra o headline em uma linha.
2. **Given** o mesmo run, **When** a aba do navegador é lida, **Then** ela mostra
   a mesma sentença que o cabeçalho.
3. **Given** o mesmo run, **When** a lista é aberta, **Then** a célula de SUBJECT
   daquela linha mostra a mesma sentença.
4. **Given** um headline que veio do modelo com ênfase markdown, **When** ele é
   usado como nome, **Then** o caractere de ênfase não aparece na tela.
5. **Given** um headline mais longo que o limite declarado, **When** ele é usado
   como nome, **Then** ele é recortado no limite com indicação de recorte, e o
   texto completo fica disponível como tooltip.

---

### User Story 2 - Um run antigo tem nome honesto, e não é o documento (Priority: P1)

O staging tem 37 investigações gravadas antes de o registro passar a ter headline.
Elas continuam abrindo, e nenhuma delas volta a usar o documento como nome.

**Why this priority**: o fallback **é** o comportamento em produção no dia do
deploy — todo run já gravado cai nele. Um fallback que devolvesse o documento
faria a feature inteira não ter acontecido para o operador que abriu o console.

**Independent Test**: abrir um run sem headline gravado e conferir que o nome é
composto de rótulo de trigger e id curto, e que o documento não aparece como nome
em nenhuma das três superfícies.

**Acceptance Scenarios**:

1. **Given** um run sem headline e com um documento markdown gravado, **When** a
   tela de detalhe abre, **Then** o cabeçalho mostra o rótulo do trigger seguido
   do id curto.
2. **Given** o mesmo run, **When** a coluna SUBJECT da lista o desenha, **Then**
   ela mostra o mesmo par, e não "Not recorded".
3. **Given** o mesmo run, **When** o painel do relato é lido, **Then** o documento
   está lá, renderizado — o fallback tirou o documento do *nome*, não da tela.
4. **Given** um run sem headline e sem documento nenhum, **When** ele é desenhado,
   **Then** o nome ainda é trigger mais id curto, e nenhuma célula fica vazia.
5. **Given** um run cujo texto gravado é uma exceção do deployment, **When** ele é
   desenhado, **Then** o nome é a tradução que o console já tem para aquela falha,
   e não a exceção.

---

### User Story 3 - O relato é leitura, não fonte (Priority: P1)

O documento que o modelo escreveu aparece como documento: cabeçalhos com peso de
cabeçalho, listas com marcador, tabela com colunas, bloco de código com rolagem
própria. Nada dele executa, nada dele sai do deployment.

**Why this priority**: o relato é o produto. Um root cause correto entregue como
texto cru é um root cause que o operador não lê.

**Independent Test**: abrir um run cujo report tem cabeçalho, lista, tabela e
bloco de código, e conferir que os quatro estão desenhados como tais e que
nenhuma requisição saiu para fora do deployment.

**Acceptance Scenarios**:

1. **Given** um report com um cabeçalho de terceiro nível, **When** o painel o
   desenha, **Then** existe um elemento de cabeçalho e o texto `###` não aparece.
2. **Given** um report com um bloco de código largo, **When** ele é desenhado em
   1920×1080, **Then** o bloco rola dentro de si mesmo e o corpo da página não
   rola horizontalmente.
3. **Given** um report que referencia uma imagem remota, **When** ele é desenhado,
   **Then** nenhuma requisição sai para o host da imagem.
4. **Given** um report com um link cujo esquema é executável, **When** ele é
   desenhado, **Then** o link não é navegável para aquele esquema.
5. **Given** um report contendo HTML cru, **When** ele é desenhado, **Then** o
   HTML aparece como texto e não vira elemento.
6. **Given** qualquer report, **When** o operador quer o original, **Then** existe
   uma disclosure fechada que revela o texto como foi gravado.

---

### User Story 4 - Um run que terminou não é oferecido para pilotar (Priority: P1)

Um run terminado há vinte minutos não diz "Paused in the background", não oferece
"Take over" e não oferece "Stop this investigation".

**Why this priority**: é o defeito que faz o produto parecer que perdeu o controle
do próprio estado. Oferecer parar algo que acabou é o tipo de erro que um operador
lembra na hora de confiar numa proposta de remediação.

**Independent Test**: abrir um run cujo status é o que o produto de fato emite ao
terminar e conferir que o painel de controle não está no DOM e que o texto de
conexão ociosa não aparece.

**Acceptance Scenarios**:

1. **Given** um run terminado, **When** a tela abre, **Then** o painel de controle
   não existe no DOM.
2. **Given** um run terminado, **When** a tela abre, **Then** o transcript é o de
   leitura, e não o vivo.
3. **Given** um run terminado, **When** o badge de status é lido, **Then** ele é
   desenhado como estado conhecido, com forma além da cor.
4. **Given** um run em andamento, **When** a tela abre, **Then** o painel de
   controle continua existindo — esta feature não remove o controle, remove a
   oferta falsa.
5. **Given** um run terminado num estado degradado, **When** a tela abre, **Then**
   ele é tratado como terminado, e não como vivo.

---

### User Story 5 - O transcript e o custo dizem o que aconteceu (Priority: P1)

Uma investigação que fez quatro chamadas de ferramenta mostra quatro chamadas com
o que cada uma devolveu, e um custo que corresponde aos turnos gravados.

**Why this priority**: é a metade "mostrar" do laço que a onda fecha. Sem ela, o
registro que a feature anterior grava não chega a ninguém.

**Independent Test**: contra um run com quatro chamadas gravadas, contar as
entradas do transcript e as linhas da tabela por turno.

**Acceptance Scenarios**:

1. **Given** um run com quatro chamadas gravadas, **When** o transcript é
   desenhado, **Then** há quatro entradas de chamada e quatro de resultado.
2. **Given** o mesmo run, **When** o cabeçalho do painel afirma uma contagem,
   **Then** essa contagem é o número de entradas desenhadas.
3. **Given** um run com turnos gravados, **When** o painel de custo é desenhado,
   **Then** ele não diz que não houve custo registrado.
4. **Given** um run com turnos gravados, **When** a tabela por turno é lida,
   **Then** há uma linha por turno.
5. **Given** um run que de fato não teve nenhum turno, **When** o painel é
   desenhado, **Then** ele diz que não houve custo — a frase continua existindo
   para o caso em que ela é verdadeira.
6. **Given** um run cujo relato já está no painel do relato, **When** o transcript
   é desenhado, **Then** o relato não aparece novamente como entrada final do
   transcript.

---

### User Story 6 - "O que esta investigação tocou" está vivo (Priority: P2)

O painel de vínculos nomeia o incidente de origem e os recursos que a investigação
tocou, lidos do registro, e só diz "nada vinculado" quando de fato não há vínculo.

**Why this priority**: P2 e não P1 porque o painel já tem uma fonte parcial que
funciona (o incidente correlacionado) e o resto depende do que a feature anterior
grava. O que não pode continuar é afirmar o negativo por leitura ausente.

**Independent Test**: abrir um run cujo registro nomeia recursos e conferir que
eles aparecem como links; abrir um run sem nenhum vínculo e conferir que a frase
de vazio aparece.

**Acceptance Scenarios**:

1. **Given** um run cujo registro nomeia recursos, **When** o painel é desenhado,
   **Then** cada recurso aparece como um link.
2. **Given** um run vinculado a um incidente, **When** o painel é desenhado,
   **Then** o incidente aparece pelo título, não pelo id.
3. **Given** um run sem nenhum vínculo registrado, **When** o painel é desenhado,
   **Then** ele diz que nada foi vinculado.
4. **Given** uma leitura de vínculos que falhou, **When** o painel é desenhado,
   **Then** ele reporta a falha de leitura, e não afirma que não há vínculo.

---

### User Story 7 - As telas de runs saem da allowlist (Priority: P2)

As regras que a suíte transversal passou a enforçar nesta onda valem para `/runs`
e `/runs/{id}` sem exceção nomeada.

**Why this priority**: a allowlist é uma dívida datada. Uma feature que corrige os
defeitos e deixa a exceção de pé não muda nada para a próxima regressão, que é
exatamente o que a allowlist deveria pegar.

**Independent Test**: ler a tabela de exceções da suíte transversal e conferir que
nenhuma entrada nomeia uma rota de runs; rodar a suíte transversal e ver as duas
rotas passando por mérito.

**Acceptance Scenarios**:

1. **Given** a tabela de exceções da suíte transversal, **When** ela é lida,
   **Then** nenhuma entrada nomeia `/runs` nem uma rota de detalhe de run.
2. **Given** a suíte transversal, **When** ela roda sobre as duas rotas de runs,
   **Then** todos os bans passam sem `fixme` nem `skip`.
3. **Given** uma regressão que reintroduza markdown cru num título, **When** a
   suíte transversal roda, **Then** ela falha nomeando a rota e a regra.

### Edge Cases

- **Headline vazio, mas presente no contrato.** Campo existe e veio `""`. Trata-se
  como ausente e cai no fallback — um nome em branco é pior que um nome composto.
- **Headline com quebra de linha.** O modelo entrega duas frases. O nome usa a
  primeira linha não vazia; o resto pertence ao report.
- **Headline longo.** Recorte no limite declarado, com indicação de recorte e o
  texto integral no tooltip. Nunca recorte silencioso.
- **Report vazio com headline presente.** O painel do relato mostra o headline
  como sentença em vez de ficar vazio; a disclosure de texto cru não aparece,
  porque não há texto além do que já está na tela.
- **Report presente e headline ausente.** O nome vem do fallback e o painel mostra
  o report renderizado. Esse é o caso de todo run já gravado no staging.
- **Report que é só uma linha de texto.** Renderiza como um parágrafo. Nenhum
  cabeçalho fabricado.
- **Report com tabela larga.** Rola dentro do próprio container, como o bloco de
  código.
- **Report gigante.** O painel tem altura máxima com rolagem própria, para que o
  orçamento de rolagem da página continue medindo a página e não o documento.
- **Report com conteúdo hostil.** O texto vem de um modelo, e um modelo pode
  repetir o que leu numa saída de ferramenta. Link com esquema executável, HTML
  cru, imagem remota e referência a fonte externa são tratados como dados, nunca
  como instrução ao navegador.
- **Run com status que nenhuma das duas listas conhece.** Continua desenhado como
  palavra crua em neutro, que é a regra que o console já tem, mas **não** é
  tratado como vivo: um status desconhecido não autoriza oferecer "Stop".
- **Run em andamento de verdade.** Nada nesta feature muda o caminho vivo além de
  ele deixar de ser escolhido para runs terminados.
- **Leitura de detalhe que falhou.** O painel reporta a falha de leitura com sua
  própria ação de repetir. Nenhum fallback de nome é aplicado sobre uma leitura
  que não aconteceu — a tela não inventa um nome para um run que não leu.

## Requirements *(mandatory)*

### Alegações normativas

Cada frase abaixo é uma afirmação sobre a tela, individualmente testável, e é o
que o acceptance spec codifica. Uma vírgula é fronteira de requisito: nenhuma
frase carrega duas obrigações.

**Caracteres de sintaxe** — para as alegações AN-001 a AN-004, "caractere de
sintaxe markdown" significa qualquer um de `#`, `*`, `` ` ``, `_`, `~`, `[`, `]`,
`|` ou `>` ocorrendo como caractere literal no texto visível.

- **AN-001**: O cabeçalho da tela de um run não contém caractere de sintaxe
  markdown.
- **AN-002**: O título da aba do navegador de um run não contém caractere de
  sintaxe markdown.
- **AN-003**: Nenhuma célula de sujeito da lista de runs contém caractere de
  sintaxe markdown.
- **AN-004**: Nenhum parágrafo de resumo de run contém caractere de sintaxe
  markdown como texto.
- **AN-005**: O nome de um run tem no máximo 120 caracteres.
- **AN-006**: O nome de um run não contém quebra de linha.
- **AN-007**: O nome de um run com headline gravado é o headline.
- **AN-008**: O nome de um run sem headline gravado é o rótulo do trigger seguido
  do id curto.
- **AN-009**: O nome de um run nunca é o documento do report.
- **AN-010**: Nenhuma célula de sujeito da lista de runs mostra o texto de "não
  registrado".
- **AN-011**: Nenhuma linha-meta de run exibe o mesmo texto de placeholder duas
  vezes.
- **AN-012**: Um cabeçalho markdown do report é desenhado como elemento de
  cabeçalho.
- **AN-013**: Uma lista markdown do report é desenhada como lista.
- **AN-014**: Um bloco de código do report rola horizontalmente dentro do próprio
  bloco.
- **AN-015**: O corpo da página de detalhe não rola horizontalmente em 1920×1080.
- **AN-016**: Uma imagem referenciada pelo report não gera requisição a host
  externo.
- **AN-017**: Um link do report com esquema executável não é navegável.
- **AN-018**: HTML cru escrito no report aparece como texto.
- **AN-019**: O texto do report como foi gravado está disponível numa disclosure.
- **AN-020**: Essa disclosure nasce fechada.
- **AN-021**: O painel do relato não repete o headline quando há report.
- **AN-022**: Um run com headline e sem report mostra o headline no painel do
  relato.
- **AN-023**: Um run terminado não exibe o texto de conexão ociosa.
- **AN-024**: Um run terminado não oferece parar a investigação.
- **AN-025**: Um run terminado não oferece assumir a investigação.
- **AN-026**: O badge de um run terminado é desenhado como estado conhecido.
- **AN-027**: Um run com quatro chamadas de ferramenta gravadas mostra quatro
  entradas de chamada no transcript.
- **AN-028**: Cada entrada de chamada tem uma entrada de resultado
  correspondente.
- **AN-029**: A contagem que o cabeçalho do transcript afirma é o número de
  entradas desenhadas.
- **AN-030**: O relato não aparece como entrada final do transcript.
- **AN-031**: Um run com turnos gravados não exibe o texto de custo não
  registrado.
- **AN-032**: A tabela de custo por turno tem uma linha por turno gravado.
- **AN-033**: Um run cujo registro nomeia recursos não exibe o texto de nada
  vinculado.
- **AN-034**: Nenhuma rota de runs consta na tabela de exceções da suíte
  transversal.
- **AN-035** *(staging-safe)*: No run mais recente do staging, AN-001, AN-002,
  AN-005, AN-006, AN-009, AN-023, AN-024 e AN-025 valem.

### Functional Requirements

#### Uma fonte para o nome de um run

- **FR-001**: O console DEVE ter um só lugar que decide o nome de um run.
- **FR-002**: A tela de detalhe DEVE obter o nome desse lugar.
- **FR-003**: O título da aba DEVE obter o nome desse lugar.
- **FR-004**: A coluna de sujeito da lista DEVE obter o nome desse lugar.
- **FR-005**: Esse lugar DEVE preferir o headline que o registro carrega.
- **FR-006**: Esse lugar DEVE tratar headline em branco como headline ausente.
- **FR-007**: Esse lugar DEVE usar apenas a primeira linha não vazia do headline.
- **FR-008**: Esse lugar DEVE remover a sintaxe markdown do headline antes de
  devolvê-lo.
- **FR-009**: Esse lugar DEVE recortar o nome no limite declarado.
- **FR-010**: Esse lugar DEVE indicar visualmente que houve recorte.
- **FR-011**: O texto completo do nome recortado DEVE estar disponível como
  tooltip.
- **FR-012**: Na ausência de headline, esse lugar DEVE devolver o rótulo do
  trigger seguido do id curto.
- **FR-013**: Esse lugar NÃO DEVE devolver o documento do report em nenhuma
  circunstância.
- **FR-014**: Esse lugar NÃO DEVE devolver o texto de "não registrado".
- **FR-015**: Quando o texto gravado é uma exceção que o console reconhece, esse
  lugar DEVE devolver a tradução que o console já tem.
- **FR-016**: A tradução de falhas DEVE continuar existindo para falhas.
- **FR-017**: A tradução de falhas NÃO DEVE continuar sendo a fonte do nome de um
  run bem-sucedido.

#### O relato renderizado

- **FR-018**: O painel do relato DEVE desenhar o report como markdown renderizado.
- **FR-019**: O renderizador DEVE produzir uma árvore de elementos, e não uma
  string de HTML.
- **FR-020**: Nenhuma superfície DEVE passar o report por `dangerouslySetInnerHTML`.
- **FR-021**: O renderizador DEVE tratar HTML cru do documento como texto.
- **FR-022**: O renderizador DEVE recusar esquema de link que não seja `http`,
  `https` ou `mailto`.
- **FR-023**: O renderizador NÃO DEVE emitir elemento de imagem com origem remota.
- **FR-024**: Uma imagem referenciada pelo documento DEVE ser representada pelo seu
  texto alternativo.
- **FR-025**: O conjunto de elementos que o renderizador desenha DEVE ser
  declarado explicitamente.
- **FR-026**: Um elemento fora desse conjunto DEVE ser desenhado como texto.
- **FR-027**: Um bloco de código DEVE ter rolagem horizontal própria.
- **FR-028**: Uma tabela DEVE ter rolagem horizontal própria.
- **FR-029**: O painel do relato DEVE ter altura máxima com rolagem própria.
- **FR-030**: O painel do relato DEVE oferecer o texto gravado numa disclosure
  fechada.
- **FR-031**: Essa disclosure NÃO DEVE aparecer quando não há report.
- **FR-032**: Todo estilo do relato DEVE vir do vocabulário de design existente.
- **FR-033**: O renderizador DEVE rodar no componente de servidor da tela.

#### Vocabulário de status e controles de run

- **FR-034**: A lista de status de run do console DEVE nomear os status que o
  produto emite.
- **FR-035**: A tabela de apresentação de status DEVE declarar papel e forma para
  cada um deles.
- **FR-036**: A decisão de "terminado" DEVE reconhecer todo status terminal que o
  produto emite.
- **FR-037**: Um status que nenhuma lista conhece NÃO DEVE ser tratado como run
  vivo.
- **FR-038**: O painel de controle NÃO DEVE existir no DOM de um run terminado.
- **FR-039**: O transcript de um run terminado DEVE ser o de leitura.
- **FR-040**: O caminho vivo NÃO DEVE ser montado para um run terminado.
- **FR-041**: O painel de controle DEVE continuar existindo para um run vivo com
  permissão.

#### Transcript e custo

- **FR-042**: A tela NÃO DEVE injetar o relato no corpo do replay.
- **FR-043**: O transcript DEVE ter uma entrada de chamada por chamada gravada.
- **FR-044**: O transcript DEVE ter uma entrada de resultado por chamada gravada.
- **FR-045**: A contagem exibida no cabeçalho do transcript DEVE ser o número de
  entradas desenhadas.
- **FR-046**: O painel de custo DEVE ter uma linha por turno gravado.
- **FR-047**: O painel de custo DEVE ter uma linha por modelo usado.
- **FR-048**: O texto de custo não registrado DEVE aparecer somente quando não há
  turno gravado.
- **FR-049**: A tela DEVE continuar declarando que o custo por turno é rateado.

#### Vínculos

- **FR-050**: O painel de vínculos DEVE nomear os recursos que o registro do run
  carrega.
- **FR-051**: O painel de vínculos DEVE nomear o incidente de origem pelo título.
- **FR-052**: O texto de nada vinculado DEVE aparecer somente quando a leitura
  foi bem-sucedida e não trouxe vínculo.
- **FR-053**: Uma leitura de vínculos que falhou DEVE ser reportada como falha de
  leitura.

#### Lista de runs

- **FR-054**: A coluna de sujeito DEVE mostrar o nome do run.
- **FR-055**: A coluna de sujeito DEVE oferecer o nome completo como tooltip.
- **FR-056**: A coluna de identificador DEVE continuar mostrando o id curto.
- **FR-057**: Nenhuma linha DEVE exibir o texto de "não registrado" na coluna de
  sujeito.
- **FR-058**: A ordenação da lista NÃO DEVE passar a ordenar por documento.
- **FR-059**: O status de cada linha DEVE ser desenhado como estado conhecido.

#### Meta-linhas e suíte transversal

- **FR-060**: Nenhuma linha-meta de run DEVE repetir o mesmo texto de placeholder.
- **FR-061**: Uma linha-meta DEVE omitir o slot vazio em vez de preenchê-lo com
  placeholder.
- **FR-062**: As duas rotas de runs DEVEM sair da tabela de exceções da suíte
  transversal.
- **FR-063**: As duas rotas de runs DEVEM permanecer no conjunto de rotas que a
  suíte percorre.
- **FR-064**: A suíte transversal DEVE passar nas duas rotas sem marcação de
  pendência.

#### Dados de teste e evidência

- **FR-065**: O conjunto de fixtures DEVE conter um run cujo status é o que o
  produto emite ao terminar.
- **FR-066**: O conjunto de fixtures DEVE conter um run com report em markdown e
  sem headline.
- **FR-067**: O conjunto de fixtures DEVE conter um run com headline e report.
- **FR-068**: O conjunto de fixtures DEVE conter um run com quatro chamadas de
  ferramenta gravadas.
- **FR-069**: O conjunto de fixtures DEVE conter um report com conteúdo hostil.
- **FR-070**: O registro de telas visuais DEVE cobrir as duas telas retocadas no
  viewport normativo.
- **FR-071**: Toda baseline visual que mudar DEVE ser aceita deliberadamente, com
  a razão escrita no registro.
- **FR-072**: Os testes de console existentes das duas telas DEVEM ser
  estendidos, e não duplicados.

#### Aceitação

- **FR-073**: Um acceptance spec próprio DEVE codificar as alegações normativas.
- **FR-074**: Esse spec DEVE ser confirmado vermelho antes de qualquer mudança de
  tela.
- **FR-075**: As alegações que podem rodar contra um ambiente compartilhado DEVEM
  estar marcadas como seguras para staging.
- **FR-076**: Nenhuma alegação marcada como segura para staging DEVE escrever
  dado.

### Key Entities

- **Headline** — a sentença que nomeia uma investigação. Uma linha, sem sintaxe,
  apta a ser título de página, título de aba, célula de lista e assunto de
  notificação. Vem do registro; o console não a inventa.
- **Report** — o documento markdown que a investigação produziu. Vive num painel
  de leitura, renderizado, com o texto original a uma disclosure de distância.
- **Nome de um run** — o que a tela mostra: o headline quando existe, a tradução
  de falha quando o texto é uma exceção, e o par trigger mais id curto quando não
  há nem um nem outro. Nunca o report.
- **Run terminado** — um run cujo status está no conjunto terminal que o produto
  emite. Não é pilotável, não é assinável e não tem conexão viva.
- **Allowlist transversal** — a tabela de pares rota-regra que a suíte transversal
  aceita como violação conhecida. Esta feature a encolhe; nenhuma feature a
  amplia sem razão escrita.

## Success Criteria *(mandatory)*

- **SC-001**: Todas as alegações normativas passam no acceptance spec contra o
  backing determinístico, e todas foram vistas vermelhas antes.
- **SC-002**: As alegações marcadas como seguras para staging passam contra
  `https://stg-ninjasre.lan.kyo.ninja`.
- **SC-003**: Abrir os três runs de fixture — com headline, sem headline, e com
  falha antes de começar — produz três nomes distintos, nenhum deles contendo
  caractere de sintaxe markdown.
- **SC-004**: Nenhuma das 37 investigações já gravadas no staging mostra o
  documento como nome em nenhuma das três superfícies.
- **SC-005**: Um run terminado do staging não tem painel de controle no DOM.
- **SC-006**: A tabela de exceções da suíte transversal não nomeia nenhuma rota de
  runs, e a suíte passa nas duas.
- **SC-007**: O relatório de rede do build de produção não registra nenhum host
  fora do deployment na tela de detalhe de run.
- **SC-008**: O corpo da página de detalhe de run não rola horizontalmente em
  1920×1080, com o report de fixture hostil carregado.
- **SC-009**: As baselines visuais das duas telas foram recapturadas e aceitas, e
  o registro de telas nomeia a razão de cada aceitação.
- **SC-010**: `make verify` passa, tendo partido de verde, e o orçamento de bundle
  do console continua dentro do declarado.
- **SC-011**: Screenshots full-page das duas telas, em 1920×1080, estão no
  diretório de evidência da feature.

## Assumptions

- **O contrato com headline e report já está mergeado.** A feature de registro
  desta onda roda no slot anterior e entrega os dois campos servidos por
  `/v1/runs` e `/v1/runs/{run_id}`. Esta spec consome o contrato; não o negocia.
  Se, no início da execução, o contrato não tiver os campos, a feature ainda
  entrega tudo o que não depende deles — fallback, status, controles, transcript,
  custo, renderizador, allowlist — e o consumo do headline vira a última tarefa,
  com o fallback cobrindo cem por cento dos runs até lá.
- **O nome dos campos é lido do cliente gerado.** O console não escolhe como o
  contrato se chama; ele lê o cliente que `make console-client` gera do documento
  committed. Um campo que não estiver no documento não existe para o console.
- **A correção do vocabulário de status é do console.** O produto emite
  `completed` e `partial`; o console é quem não os conhece. A correção fica aqui
  porque o arquivo é do console e porque ela precisa valer mesmo que o backend
  nunca mude uma palavra.
- **As fixtures ganham runs novos em vez de terem os antigos reescritos.** Trocar
  `succeeded` por `completed` nos runs existentes moveria baselines e testes que
  não são desta feature. Os casos novos entram como registros novos.
- **`readFailure` continua sendo o tradutor de falhas.** Ele foi escrito para
  impedir que uma exceção do gateway vire manchete, e continua fazendo isso. O que
  sai dele é o papel de nomear um run bem-sucedido.
- **O renderizador roda no servidor.** A tela de detalhe é um componente de
  servidor, e o relato é lido de uma vez. Nenhum estado de cliente participa.
- **O texto do relato é dado, não instrução.** Ele vem de um modelo que leu saídas
  de ferramentas. A postura da tela é a mesma que a do resto do produto: renderiza,
  não obedece.
- **A marca de "seguro para staging" é a que a feature de governança definir.** Se
  ela ainda não existir quando esta feature começar, os testes seguros carregam
  uma etiqueta no próprio título e a spec declara qual é.

## Dependencies

- **Depende da feature de registro desta onda** (slot anterior) para headline,
  report, turnos, chamadas, custo e vínculos. Sem o registro, as telas ficam
  corretas e vazias — que já é melhor do que hoje, mas não é o objetivo.
- **Depende da feature de governança desta onda** (slot zero) para os bans
  transversais novos, para a allowlist que esta feature encolhe, e para a
  execução de acceptance contra staging.
- **Bloqueia a feature de fim de onda**, que precisa de uma investigação legível
  na tela para o cenário ponta a ponta.
- **É dona dos arquivos de escrita única do seu slot**: o catálogo de mensagens, a
  lista de rotas e o registro de telas visuais. Pode editá-los.

## Out of Scope

- Gravar qualquer coisa. Esta feature só lê.
- O prompt de entrega e a forma como o headline é gerado.
- O id opaco de incidente e a dupla codificação na montagem de URL.
- A causa falsa de vazio em Decisions e Knowledge.
- O cache de rota que serve listas congeladas.
- Os redirects das rotas que respondem por outro nome.
- Compor os portões de remediação e de autonomia.
- Qualquer mudança em telas fora de `/runs` e `/runs/{runId}`.
- Traduzir o relato. O documento é servido como o deployment o gravou.
