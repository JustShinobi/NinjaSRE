# Feature Specification: Regras e governança — as regras dizem a verdade antes de qualquer feature ser escrita contra elas

**Feature Branch**: `feat/v7-000-regras-e-governanca`

**Created**: 2026-08-23

**Status**: Draft

**Input**: User description: "As regras passam a dizer a verdade antes de qualquer
outra feature ser escrita contra elas. Três entregas: governança em dia (emenda
pendente escrita de fato, status e índice dos registros de decisão corrigidos,
orientação local atualizada), a emenda que fecha o buraco 'escrito mas não
composto' com registro de decisão próprio, e o ferramental que as outras features
assumem — os bans transversais novos com allowlist, e a validação de tela contra o
staging real."

**Referência visual (DoD)**: nenhuma. Esta feature **não tem tela própria** e não
redesenha nenhuma. Ela estende a suíte transversal, que mede telas que outras
features vão consertar — por isso não há `acceptance.spec.ts` próprio nem tarefa
de mockup. O que esta feature entrega em navegador são **asserções nomeadas**
(a seção "Alegações normativas" abaixo), codificadas na suíte transversal e
provadas vermelhas contra um dataset que reproduz as telas violadoras de hoje.

**Slot de execução**: S0, sozinha. Esta feature muda arquivos que **todas** as
outras leem — a constituição local, os registros de decisão, a orientação local,
a suíte transversal e o ferramental de validação. Nenhuma outra feature da onda
começa antes do merge desta.

## Fatos verificados na árvore (2026-08-23 — não re-derivar)

Cada item abaixo foi conferido no repositório antes desta spec existir. São fatos,
não hipóteses a validar.

1. `.specify/memory/constitution.md` está em **2.0.0**, "Last amended 2026-08-04 —
   Article XIII". A orientação local afirma 2.1.0 e depois 2.2.0. **As duas
   emendas que a orientação descreve não estão no arquivo.**
2. O Artigo IX (capacidades) da constituição **não tem cláusula de paridade
   nenhuma** — nem a dos sete artefatos, nem a de amplitude. O ADR 0015 declara
   emendar "the capabilities article's parity clause", e essa cláusula não
   existe no texto. A emenda pendente **acrescenta** a cláusula; não reescreve
   uma.
3. Os cinco portos que o Artigo XI nomeia (`EpisodeStore`, `TopologyGraph`,
   `VectorIndex`, `ConfigRepository`, `RunTraceStore`) existem todos em
   `platform/persistence/ports/`. O adaptador de runtime alternativo que o
   Artigo V dá como exemplo existe em `core/agent/adapters/claude_sdk.py`. Os
   exemplos citados nesses dois artigos **não estão defasados** — o que é um
   resultado da auditoria, não uma dispensa dela.
4. `docs/adr/0009-full-integration-parity.md:3` segue **`Status: Accepted`**,
   apesar de `docs/adr/0015-parity-per-embedded-integration.md:5` declarar
   `Supersedes: 0009`.
5. `docs/adr/README.md:8-18` lista **0001–0011**. Os arquivos `0012`, `0013`,
   `0014` e `0015` existem e não têm linha. A regra 4 do próprio índice
   (`docs/adr/README.md:27`) exige linha nas duas tabelas — nele e na
   traceability de `docs/roadmap.md:205-217`, que também para no 0011.
6. `integrations/` tem **15 pacotes de vendor** na árvore. O corte aconteceu.
7. `docs/roadmap.md` **não tem seção de escopo de integrações**: nenhuma
   ocorrência de vendor embarcado, de "deferred" ou de "embedded" no arquivo.
   O ADR 0015 diz, em texto committed, que a amplitude corrente "is read from
   the integration scope section of the roadmap". **O ponteiro não resolve.**
8. `docs/roadmap.md` afirma `~85` em três lugares que falam do presente
   (linhas 136, 142 e 192). A linha 215 é a linha de traceability do 0009 e
   carrega o *título* daquele registro — outra coisa.
9. `tests/architecture/test_no_committed_file_states_a_stale_catalogue_size.py`
   já permite deliberadamente que `docs/roadmap.md` e `docs/adr/` guardem um
   total antigo, "because a decision record explains what was decided then" e o
   roadmap "carries the record of scope that has moved". A decisão de deixar o
   histórico em paz é anterior a esta feature e continua valendo.
10. `console/tests/e2e/transversal-rules.spec.ts` tem **quatro regras**
    (vocabulário, orçamento de rolagem, contagem única de progresso de setup,
    coluna Value nunca vazia), varre as rotas de Settings lidas de
    `console/src/shell/routes.ts` mais `/integrations`, e traz uma tabela
    `EXCEPTIONS` (rota × regra × razão) hoje **vazia**, aplicada por
    `test.fixme`. Nenhuma tela do grupo "Now" é varrida por ela.
11. As rotas do grupo "Now" em `console/src/shell/routes.ts` são `/`,
    `/incidents`, `/runs` e `/decisions`. As telas de detalhe (`/runs/{id}`,
    `/incidents/{id}`) são dinâmicas e não têm entrada no manifesto.
12. O mock plane compõe cenários por herança (`derives_from`) e por override
    por endpoint, declarados em `fixtures/manifest.json`; um cenário que difere
    de `populated` em três endpoints carrega três arquivos. Os `summary` do
    cenário `populated` são sentenças limpas — **nenhuma tela viola os bans
    novos contra o dataset de hoje**.
13. `tools/spec_validation.py` conhece dois backings, `mock` e `compose`
    (`--backing`, linha 139), e ambos sobem ambiente por
    `tools/console_e2e.py:542` (`run`), que também serve o console local em
    `console()` (linha 487) e passa a credencial ao navegador pela variável
    declarada em `config/constants/console.py:39`.
14. `console/playwright.config.ts` tem três projetos (`behaviour`, `first-day`,
    `visual`), viewport global 1440×900, e nenhum teste da árvore usa tag.
    Playwright 1.62.1 — tags em `describe`/`test` e seleção por `--grep`
    disponíveis.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A regra escrita alcança a decisão que já foi tomada (Priority: P1)

Quem abre a constituição local encontra a cláusula de paridade que o registro de
decisão vigente descreve. O Constitution Check de qualquer plano da onda passa a
rodar contra um texto que nenhuma das duas fontes desmente.

**Why this priority**: hoje o Constitution Check das specs roda contra um texto
que a orientação local declara errado. Toda feature desta onda é planejada contra
essa checagem. Se a emenda não existe, cada plano da onda cita uma versão de
constituição que não é a do arquivo, e a checagem vira formalidade.

**Independent Test**: ler o artigo de capacidades e conferir que ele enuncia a
paridade por integração embarcada, com a condição de ambiente validável, e que o
cabeçalho do documento registra a emenda com versão e data.

**Acceptance Scenarios**:

1. **Given** a constituição local, **When** o artigo de capacidades é lido,
   **Then** ele traz uma cláusula de paridade que fala de integração embarcada e
   não afirma um total.
2. **Given** a constituição local, **When** o cabeçalho é lido, **Then** ele
   registra a emenda com número de versão, data e o registro de decisão que a
   motiva.
3. **Given** os quatro artigos que a orientação local acusa de exemplos
   defasados, **When** cada exemplo é conferido contra a árvore, **Then** cada um
   ou é corrigido ou é declarado conferido e correto — nenhum fica sem resposta.
4. **Given** a constituição, **When** o repositório é empacotado ou commitado,
   **Then** ela não entra em nenhum commit.

---

### User Story 2 - "Composto ou não foi entregue" passa a ser regra (Priority: P1)

Um mecanismo que foi mergeado e que nenhuma composition root de serving constrói
deixa de poder ser declarado entregue. Ou existe um caminho de serving que o
alcança, ou o próprio módulo declara que está dormente e nomeia o que o ligaria.

**Why this priority**: a forma se repetiu em cinco lugares independentes, com o
mesmo desfecho: Constitution Check aprovou, testes verdes provaram as peças,
`make verify` passou, e o fio nunca foi ligado. Nada no corpo de regras pega essa
falha. As features 001, 040 e 080 desta onda existem para consertar instâncias
dela — e nenhuma delas fecha o buraco que deixou as cinco passarem.

**Independent Test**: ler o registro de decisão novo e a cláusula nova e conferir
que os dois dizem a mesma coisa, que o registro se sustenta sozinho para quem
clonar o repositório, e que a exigência de evidência de caminho de serving é
enunciada em termos observáveis.

**Acceptance Scenarios**:

1. **Given** um registro de decisão novo committed, **When** ele é lido por quem
   só tem o clone, **Then** ele enuncia a regra inteira em substância, sem pedir
   nenhum documento que não veio no clone.
2. **Given** a constituição local emendada, **When** a regra nova é lida,
   **Then** ela exige alcance a partir de composition root de serving **ou**
   declaração de dormência no próprio módulo, e exige evidência do caminho de
   serving no fechamento de qualquer feature.
3. **Given** a versão da constituição antes desta feature, **When** as duas
   emendas são aplicadas, **Then** a versão sobe duas vezes, cada uma com seu
   sumário, e o índice de artigos reflete a regra nova.
4. **Given** o registro novo, **When** ele nomeia o que a regra governa,
   **Then** ele o nomeia em substância e não por número de artigo.

---

### User Story 3 - O índice descreve os registros que existem (Priority: P1)

Quem procura a decisão que governa alguma coisa a encontra pelo índice. Nenhum
registro existe sem linha, e nenhum registro revertido continua se apresentando
como vigente.

**Why this priority**: quatro registros existem sem linha no índice e um registro
superseded se apresenta como aceito. Uma feature planejada contra o 0009 herda uma
regra que já foi revertida, e a reversão está escrita em um arquivo que o índice
não mostra.

**Independent Test**: comparar a lista de arquivos de registro com as linhas das
duas tabelas, e conferir o status de cada registro contra o que os outros
registros dizem dele.

**Acceptance Scenarios**:

1. **Given** o registro de paridade total, **When** seu status é lido, **Then**
   ele consta como revertido, com data e ponteiro para o sucessor, e o corpo
   continua explicando por que a decisão foi tomada então.
2. **Given** o índice de registros, **When** ele é comparado com o diretório,
   **Then** todo arquivo de registro tem exatamente uma linha, e nenhuma linha
   aponta para arquivo inexistente.
3. **Given** a tabela de traceability, **When** ela é comparada com o índice,
   **Then** as duas cobrem o mesmo conjunto de registros.
4. **Given** as linhas escritas por esta feature, **When** elas nomeiam o que a
   decisão governa, **Then** o nomeiam em substância, não por número de artigo.

---

### User Story 4 - A suíte transversal alcança as telas onde o produto está mentindo (Priority: P1)

As cinco formas de mentira que o diagnóstico encontrou nas telas de "Now" viram
regras da suíte transversal. Cada regra nasce com a lista explícita das telas que
hoje a violam, e cada entrada dessa lista diz o que precisa acontecer para ela
sumir.

**Why this priority**: sem os bans, cada feature de console desta onda consertaria
a sua tela e nada impediria a próxima de reintroduzir o mesmo defeito na tela
seguinte. Com os bans, o conserto é medido e o retrocesso é uma falha de gate.
E a allowlist é o que permite os bans existirem hoje sem quebrar a árvore.

**Independent Test**: rodar a suíte transversal contra a árvore atual e conferir
que ela passa; rodar contra o dataset que reproduz as telas violadoras e conferir
que cada ban acusa, nomeando rota, regra e o texto ofensor.

**Acceptance Scenarios**:

1. **Given** a suíte transversal com os bans novos e a allowlist, **When** ela
   roda contra o dataset determinístico da árvore, **Then** ela passa.
2. **Given** um ban qualquer dos cinco e a allowlist vazia, **When** ele roda
   contra o dataset que reproduz a tela violadora, **Then** ele falha, e a
   mensagem nomeia a rota, a regra e o trecho que a violou.
3. **Given** uma entrada de allowlist, **When** ela é lida, **Then** ela nomeia
   uma rota e uma regra, dá a razão em substância, e diz o que a remove.
4. **Given** uma rota do grupo "Now" sem entrada de allowlist para um ban,
   **When** a suíte roda, **Then** aquela rota é medida contra aquele ban de
   verdade, sem asserção afrouxada.
5. **Given** as telas de detalhe de run e de incidente, **When** a suíte precisa
   alcançá-las, **Then** ela chega nelas seguindo a primeira linha da lista
   correspondente, sem nenhum identificador digitado no arquivo de teste.

---

### User Story 5 - A validação de tela acontece contra o staging real (Priority: P1)

Quem termina um slot da onda aponta os testes de aceitação para o staging que
acabou de receber o deploy, com credencial de operador vinda do ambiente, sem
subir nada. Só os testes declarados seguros para ambiente compartilhado rodam lá,
e a evidência de tela sai do mesmo run.

**Why this priority**: é a peça que destrava o protocolo de execução da onda
inteira. Sem ela, cada slot valida contra um dataset committed e a promessa de
"validação visível no staging real" não tem ferramenta. Sete features dependem
disso para fechar.

**Independent Test**: apontar a validação para o staging com a credencial no
ambiente e conferir que um teste de leitura passa lá, que nenhum ambiente subiu,
que nada foi construído, e que a credencial não apareceu em log, em arquivo nem
em linha de comando.

**Acceptance Scenarios**:

1. **Given** um endereço de staging e uma credencial no ambiente, **When** a
   validação de navegador roda contra esse backing, **Then** nenhum processo de
   dados é iniciado, nenhum console é servido localmente e nenhuma construção
   acontece.
2. **Given** nenhuma credencial no ambiente, **When** a validação contra staging
   é pedida, **Then** ela recusa dizendo qual variável falta, antes de abrir
   qualquer navegador.
3. **Given** um teste não declarado seguro para ambiente compartilhado, **When**
   ele é nomeado explicitamente numa execução contra staging, **Then** ele não
   roda.
4. **Given** uma execução contra staging que terminou, **When** o diretório de
   evidência é aberto, **Then** ele traz uma captura de página inteira por rota
   varrida, do mesmo run.
5. **Given** um argumento que só faz sentido para um backing que sobe ambiente,
   **When** ele é passado junto do backing de staging, **Then** o comando recusa
   em vez de ignorar em silêncio.
6. **Given** a saída completa do comando, **When** ela é lida, **Then** a
   credencial não aparece nela.

---

### User Story 6 - A orientação local descreve o repositório de hoje (Priority: P2)

Uma sessão nova é orientada pelo estado atual: as ondas que já rodaram, o que
elas entregaram, onde estão as specs da onda corrente e qual é a versão da
constituição no disco.

**Why this priority**: é o documento que toda sessão lê primeiro e ele descreve a
fundação pré-ondas. Uma sessão orientada por fatos velhos re-deriva o que já
existe. É P2 porque o custo é de tempo de agente, não de comportamento do produto.

**Independent Test**: ler a seção de estado do repositório e conferir que cada
afirmação dela corresponde à árvore.

**Acceptance Scenarios**:

1. **Given** a orientação local, **When** a seção de estado é lida, **Then** ela
   descreve o pós-v6 e aponta o diretório de specs da onda corrente.
2. **Given** a orientação local, **When** ela afirma a versão da constituição,
   **Then** o número afirmado é o do arquivo.
3. **Given** a orientação local, **When** ela é lida ao fim da feature, **Then**
   ela não afirma nenhuma emenda que não esteja escrita no arquivo.

---

### User Story 7 - O ponteiro que o registro de paridade faz resolve (Priority: P2)

O registro de decisão vigente sobre paridade diz, em texto committed, onde se lê a
amplitude corrente do catálogo. Quem segue esse ponteiro chega numa seção que
existe e que descreve o catálogo que a árvore tem.

**Why this priority**: é um ponteiro quebrado dentro do material committed, escrito
pela decisão que governa o catálogo. É a mesma classe de defeito que a regra de
autossuficiência existe para impedir, e cai exatamente no mandato desta feature.
É P2 porque nenhuma feature da onda depende dele para rodar.

**Independent Test**: seguir o ponteiro do registro de paridade e conferir que a
seção existe, nomeia o conjunto embarcado que a árvore tem, e registra o
diferido com a condição que o traz de volta.

**Acceptance Scenarios**:

1. **Given** o registro de decisão vigente sobre paridade, **When** o ponteiro
   que ele faz ao roadmap é seguido, **Then** a seção apontada existe.
2. **Given** essa seção, **When** ela é comparada com a árvore, **Then** o
   conjunto embarcado que ela nomeia é o que a árvore tem.
3. **Given** o registro histórico de amplitude que o roadmap guarda, **When** a
   seção nova é escrita, **Then** o histórico continua legível e não é
   reescrito.

---

### User Story 8 - O deployment legado sai do chart (Priority: P3, opcional)

O deployment de console legado que continua de pé no cluster ao lado do `web`
deixa de ser reconciliado.

**Why this priority**: é a única coisa do inventário desta onda que não é produto
nem regra — é um commit num repositório de GitOps fora desta árvore. Entra se
sobrar folga no slot; a execução é do operador.

**Independent Test**: ler a tarefa e conferir que ela nomeia o repositório, o
caminho e o comando, e que não pretende ter executado nada.

**Acceptance Scenarios**:

1. **Given** a última fase do plano de tarefas, **When** ela é lida, **Then** ela
   documenta o caminho e o comando e declara que a execução é do operador.
2. **Given** esta feature, **When** o seu diff é inspecionado, **Then** ele não
   contém nenhuma alteração fora desta árvore.

### Edge Cases

- **A emenda pendente descreve uma cláusula que não existe.** O registro de
  decisão vigente diz que emenda "a cláusula de paridade" do artigo de
  capacidades, e o artigo não tem cláusula de paridade nenhuma. A emenda
  **acrescenta** a cláusula em vez de reescrever uma inexistente, e o sumário
  registra isso — senão o próximo leitor procura a diferença e não a encontra.
- **Um exemplo acusado de defasado que está correto.** Dois dos quatro artigos
  citados têm exemplos que a árvore confirma. A auditoria registra "conferido e
  correto" como resultado; o que não é aceitável é o artigo ficar sem resposta.
- **O registro superseded é imutável.** A regra do próprio índice diz que um
  registro é imutável depois de aceito e que reverter é escrever outro. Mudar o
  status **não** é editar a decisão: é declarar o que outro registro já decidiu
  sobre ele. O corpo não é tocado.
- **Nenhuma tela viola os bans contra o dataset determinístico.** Os `summary`
  do cenário `populated` são sentenças limpas. Um ban que só é exercitado contra
  o staging é um ban que ninguém sabe se funciona — o dataset que reproduz as
  telas violadoras existe para que o vermelho seja reproduzível em qualquer
  máquina, hoje e daqui a três meses.
- **Uma entrada de allowlist deixa a rota sem medição.** Uma entrada é uma
  ausência de teste declarada, não uma passagem. Ela diz isso de si mesma, e o
  fechamento da feature reporta quantas existem — o número precisa cair a cada
  slot, e o relatório de quem o aumentar tem de explicar por quê.
- **A suíte transversal contra staging pode falhar por motivo alheio ao ban.**
  O orçamento de rolagem e a contagem de progresso de setup medem coisas que
  dependem dos dados do deployment. Por isso a declaração de "seguro para
  ambiente compartilhado" é **por teste**, nunca por arquivo: contra staging
  rodam os bans, não a suíte inteira.
- **Credencial de staging em máquina compartilhada.** A credencial é lida do
  ambiente e nunca é gravada, nunca é impressa e nunca vira argumento de linha
  de comando — argumento de processo é legível por qualquer processo do host.
- **Um teste que escreve marcado como seguro para staging.** A marcação é
  declarativa e ninguém a valida por análise. A regra é enunciada onde a marca é
  declarada: leitura e fluxo de proposta, nunca escrita nem destruição. Um teste
  que escreve e se marca é um defeito de quem o marcou, e o fechamento de cada
  feature confere as marcas que ela adicionou.
- **A árvore muda de rota entre slots.** A varredura lê as rotas do manifesto do
  próprio produto, então uma rota nova do grupo "Now" entra na varredura no dia
  em que aterrissa, sem ninguém lembrar de acrescentar uma linha.

## Alegações normativas — os cinco bans

Frases curtas, individualmente testáveis, derivadas do diagnóstico. Cada uma vira
uma asserção nomeada na suíte transversal, com allowlist própria. Viewport
normativo de medição: **1920×1080** (o mesmo que a suíte já usa para o orçamento
de rolagem).

1. **Markdown cru nunca é impresso como texto.** Nenhum título, célula de tabela,
   coluna de lista ou parágrafo de tela do grupo "Now" mostra `###`, `**` ou
   crase visível. Um documento markdown é renderizado ou é resumido; não é
   despejado.
2. **Um identificador nunca faz o papel de nome.** Nenhum título de página, nome
   de coluna-sujeito ou entrada de trilha é um identificador — nem hexadecimal
   nu, nem identificador composto, nem identificador percent-encoded.
3. **Uma linha-meta não tem dois placeholders.** Numa mesma linha de metadados —
   subtítulo de página ou linha de lista — no máximo um slot está em fallback.
   Duas ausências lado a lado formam uma sentença sem sujeito.
4. **Controle de run vivo não aparece em run terminado.** Uma tela de run cujo
   estado é terminal não oferece controle que só faz sentido em run em curso,
   nem exibe distintivo de run em curso.
5. **Nenhuma tela afirma o negativo depois de uma leitura falhada.** Quando o
   painel que sustentaria a afirmação não pôde ser lido, a tela diz que não
   sabe. "Não há investigação" é uma afirmação sobre o mundo, e uma leitura
   falhada não a sustenta.

### As telas que hoje violam (allowlist de partida, derivada do diagnóstico)

| Rota | Ban | Por que viola hoje |
|---|---|---|
| `/runs/{id}` | markdown cru | o documento do modelo chega como título, como título de aba e como corpo do painel |
| `/runs` | markdown cru | a coluna de sujeito trunca o mesmo documento |
| `/runs` | identificador como nome | a coluna de investigação é hexadecimal nu |
| `/runs/{id}` | identificador como nome | a trilha é o identificador inteiro |
| `/incidents/{id}` | identificador como nome | o título é o identificador composto percent-encoded |
| `/runs` | dois placeholders | uma linha traz sujeito e duração ambos em fallback |
| `/incidents/{id}` | dois placeholders | o subtítulo tem cinco slots e três em fallback |
| `/runs/{id}` | controle de run vivo | run terminado oferece parar a investigação e exibe distintivo de pausa |
| `/incidents/{id}` | afirmação negativa | o chip afirma ausência de investigação derivando de uma leitura que falhou |

Nove entradas. É o número que o fechamento desta feature registra e que cada slot
seguinte precisa fazer cair.

## Requirements *(mandatory)*

### A emenda pendente

- **FR-001**: A constituição local DEVE receber uma cláusula de paridade no
  artigo de capacidades.
- **FR-002**: Essa cláusula DEVE enunciar a paridade por integração embarcada,
  com os sete artefatos, na forma que o registro de decisão vigente descreve.
- **FR-003**: Essa cláusula DEVE enunciar a amplitude como estagiada por ambiente
  capaz de validar a integração ponta a ponta.
- **FR-004**: Essa cláusula NÃO DEVE afirmar um total de integrações.
- **FR-005**: Cada um dos quatro artigos que a orientação local acusa de exemplos
  defasados DEVE ser conferido exemplo por exemplo contra a árvore.
- **FR-006**: Todo exemplo conferido DEVE receber um resultado registrado —
  corrigido, ou conferido e correto. Nenhum artigo fica sem resposta.
- **FR-007**: A versão da constituição DEVE subir para 2.1.0, com data e sumário
  de emenda no cabeçalho, nomeando o registro de decisão que a motiva.
- **FR-008**: A constituição NÃO DEVE entrar em nenhum commit desta feature.

### Composto ou não foi entregue

- **FR-009**: Um registro de decisão arquitetural novo DEVE ser escrito e aceito,
  com o próximo número livre da série.
- **FR-010**: Esse registro DEVE decidir que todo mecanismo mergeado é alcançável
  a partir de uma composition root de serving, ou declara-se dormente no próprio
  módulo com a referência do que o ligaria.
- **FR-011**: Esse registro DEVE decidir que um símbolo construído apenas por
  testes não conta como entrega.
- **FR-012**: Esse registro DEVE decidir que o fechamento de qualquer feature
  inclui evidência do caminho de serving para o comportamento novo.
- **FR-013**: Esse registro DEVE registrar driver, alternativas consideradas e
  consequências, conforme a regra de emenda do documento que ele emenda.
- **FR-014**: Esse registro DEVE se sustentar sozinho para quem só tem o clone.
- **FR-015**: Esse registro NÃO DEVE citar número de artigo, identificador de
  requisito, número de feature nem caminho de diretório de planejamento.
- **FR-016**: A constituição local DEVE receber a mesma regra como texto
  normativo próprio.
- **FR-017**: A versão da constituição DEVE subir para 2.2.0, com data e sumário
  de emenda, e o índice de artigos DEVE refletir a regra nova com o seu teste de
  uma linha.
- **FR-018**: A regra nova DEVE ser enunciada em termos observáveis — o que
  precisa existir, e o que serve de evidência — e não como intenção.

### Higiene dos registros de decisão

- **FR-019**: O registro de paridade total DEVE passar a constar como revertido,
  com data e ponteiro para o sucessor.
- **FR-020**: O corpo desse registro NÃO DEVE ser alterado.
- **FR-021**: O índice de registros DEVE ter exatamente uma linha por arquivo de
  registro existente.
- **FR-022**: O índice DEVE refletir o novo status do registro revertido.
- **FR-023**: A tabela de traceability do roadmap committed DEVE cobrir o mesmo
  conjunto de registros que o índice.
- **FR-024**: As linhas que esta feature escreve nas duas tabelas DEVEM nomear o
  que a decisão governa em substância, e não por número de artigo.
- **FR-025**: Nenhuma linha de nenhuma das duas tabelas DEVE apontar para arquivo
  inexistente.
- **FR-026**: As onze linhas preexistentes do índice NÃO DEVEM ser reescritas por
  esta feature.

### Os bans transversais

- **FR-027**: A suíte transversal DEVE passar a varrer as rotas do grupo "Now" do
  manifesto de rotas do produto.
- **FR-028**: A suíte DEVE alcançar a tela de detalhe de run e a tela de detalhe
  de incidente seguindo a primeira linha da lista correspondente.
- **FR-029**: Nenhum identificador de run nem de incidente DEVE ser escrito
  literalmente no arquivo de teste.
- **FR-030**: A suíte DEVE ganhar uma regra que reprova markdown cru impresso
  como texto em título, célula, coluna ou parágrafo.
- **FR-031**: A suíte DEVE ganhar uma regra que reprova identificador no papel de
  nome — hexadecimal nu, composto ou percent-encoded — em título, coluna-sujeito
  ou trilha.
- **FR-032**: A suíte DEVE ganhar uma regra que reprova mais de um placeholder na
  mesma linha de metadados.
- **FR-033**: A suíte DEVE ganhar uma regra que reprova controle de run vivo, ou
  distintivo de run vivo, em tela de run com estado terminal.
- **FR-034**: A suíte DEVE ganhar uma regra que reprova afirmação negativa de
  estado quando a leitura que a sustentaria falhou.
- **FR-035**: Cada regra nova DEVE ter allowlist por rota e por regra, com razão
  em substância e com o que a remove.
- **FR-036**: Uma entrada de allowlist NÃO DEVE afrouxar a asserção para as
  demais rotas.
- **FR-037**: Nenhuma entrada de allowlist DEVE citar número de feature,
  identificador de requisito nem caminho de planejamento.
- **FR-038**: Cada regra nova DEVE falhar contra um dataset que reproduza a tela
  violadora, e esse vermelho DEVE ser confirmado antes de a allowlist existir.
- **FR-039**: Um cenário de dados que reproduz as telas violadoras DEVE existir
  na árvore, composto a partir do cenário cheio, alterando só o que precisa
  mudar.
- **FR-040**: Cada detector de regra nova DEVE ter prova determinística de que
  acusa o texto ofensor e não acusa o texto limpo, rodando no gate padrão.
- **FR-041**: A suíte transversal DEVE passar contra o dataset determinístico da
  árvore ao final desta feature.
- **FR-042**: A mensagem de falha de cada regra nova DEVE nomear a rota, a regra
  e o trecho ofensor.
- **FR-043**: A suíte DEVE medir as regras novas no viewport normativo de
  1920×1080.

### Validação contra o staging real

- **FR-044**: A validação de navegador DEVE aceitar um backing que não sobe
  ambiente nenhum.
- **FR-045**: Esse backing NÃO DEVE iniciar plano de dados, NÃO DEVE servir
  console local e NÃO DEVE construir nada.
- **FR-046**: O endereço do staging DEVE ser lido do ambiente, com o endereço
  conhecido como padrão.
- **FR-047**: A credencial de operador DEVE ser lida do ambiente.
- **FR-048**: A credencial NÃO DEVE ser gravada em arquivo, NÃO DEVE ser impressa
  e NÃO DEVE ser passada como argumento de linha de comando.
- **FR-049**: Na ausência da credencial, o comando DEVE recusar nomeando a
  variável que falta, antes de provisionar navegador.
- **FR-050**: Só os testes declarados seguros para ambiente compartilhado DEVEM
  rodar contra esse backing.
- **FR-051**: Um teste não declarado seguro NÃO DEVE rodar contra esse backing
  nem quando é nomeado explicitamente.
- **FR-052**: A declaração de segurança DEVE ser por teste, nunca por arquivo.
- **FR-053**: O significado da declaração — leitura e fluxo de proposta, nunca
  escrita nem destruição de dados — DEVE estar enunciado onde ela é declarada.
- **FR-054**: Um argumento que só faz sentido para um backing que sobe ambiente
  DEVE ser recusado quando passado junto do backing de staging.
- **FR-055**: A execução contra staging DEVE produzir uma captura de página
  inteira por rota varrida, no diretório de evidência que o chamador nomear.
- **FR-056**: Os nomes de variável de ambiente novos DEVEM viver na camada de
  constantes.
- **FR-057**: A marca que declara um teste seguro para ambiente compartilhado
  DEVE ter uma única grafia com um único dono.

### A orientação local

- **FR-058**: A seção de estado do repositório DEVE descrever o estado pós-v6.
- **FR-059**: Ela DEVE apontar o diretório de specs da onda corrente.
- **FR-060**: A versão de constituição que ela afirma DEVE ser a do arquivo ao
  final desta feature.
- **FR-061**: Ela NÃO DEVE afirmar nenhuma emenda que não esteja escrita no
  arquivo.

### O ponteiro do registro de paridade

- **FR-062**: O roadmap committed DEVE ganhar a seção de escopo de integrações
  que o registro de decisão vigente sobre paridade nomeia.
- **FR-063**: Essa seção DEVE nomear o conjunto embarcado que a árvore tem.
- **FR-064**: Essa seção DEVE registrar o conjunto diferido com a condição que o
  traz de volta.
- **FR-065**: O registro histórico de amplitude que o roadmap já guarda NÃO DEVE
  ser reescrito.

### O deployment legado

- **FR-066**: A remoção do deployment legado DEVE ser documentada com
  repositório, caminho e comando.
- **FR-067**: Esta feature NÃO DEVE alterar nenhum arquivo fora desta árvore.

### Key Entities

- **Emenda**: uma alteração da constituição local, com registro de decisão
  próprio, aumento de versão e sumário no cabeçalho. Nunca committed.
- **Registro de decisão**: documento committed, imutável depois de aceito,
  autossuficiente para quem só tem o clone. Reverter é escrever outro.
- **Ban transversal**: uma asserção nomeada que vale para um conjunto de rotas
  lido do manifesto do produto, com allowlist por rota e por regra.
- **Entrada de allowlist**: uma ausência de teste declarada — rota, regra, razão
  em substância, e o que a remove. Nunca uma asserção afrouxada.
- **Backing de staging**: um alvo de validação que já existe e que a validação
  não constrói nem derruba. Endereço e credencial vêm do ambiente.
- **Teste seguro para ambiente compartilhado**: um teste que lê, ou que exercita
  proposta sem executá-la. Declarado por marca no próprio teste.
- **Composition root de serving**: o lugar do caminho de produção onde um
  mecanismo é efetivamente construído. É o que a regra nova exige nomear.

## Success Criteria *(mandatory)*

- **SC-001**: A constituição local está em 2.2.0, com duas entradas de emenda no
  cabeçalho, e não aparece em nenhum commit desta feature.
- **SC-002**: O artigo de capacidades enuncia a paridade por integração embarcada
  com condição de ambiente validável e sem total afirmado.
- **SC-003**: Os quatro artigos auditados têm resultado registrado, um a um.
- **SC-004**: Existe registro de decisão committed que enuncia a regra de
  composição por inteiro, legível sem nenhum documento fora do clone, e ele não
  cita nenhum identificador de planejamento.
- **SC-005**: Toda linha das duas tabelas de registros aponta para um arquivo que
  existe, e todo arquivo de registro tem exatamente uma linha em cada uma.
- **SC-006**: O registro de paridade total consta como revertido, com o corpo
  intacto.
- **SC-007**: A suíte transversal passa contra o dataset determinístico da árvore,
  com as cinco regras novas ativas e nove entradas de allowlist declaradas.
- **SC-008**: Cada uma das cinco regras novas tem um vermelho capturado, com a
  mensagem real, contra o dataset que reproduz a tela violadora.
- **SC-009**: Cada detector novo tem prova determinística no gate padrão de que
  acusa o ofensor e absolve o limpo.
- **SC-010**: Uma execução da suíte transversal contra o staging real termina
  verde nos bans, sem que nada tenha sido construído nem iniciado, com uma
  captura por rota no diretório de evidência.
- **SC-011**: A busca pela credencial de staging na saída completa dessa execução
  não a encontra.
- **SC-012**: Seguir o ponteiro do registro de paridade a partir do clone chega
  numa seção que existe e nomeia o catálogo que a árvore tem.
- **SC-013**: A verificação completa do repositório termina verde, tendo partido
  de verde, e a comparação entre as duas rodadas é o artefato.

## Assumptions

- **A constituição é local-only e continua sendo.** As duas emendas existem no
  disco desta máquina. O que fica legível para quem clona é o registro de decisão
  novo, e é por isso que ele precisa se sustentar sozinho.
- **Um registro superseded não é editado, só reclassificado.** Mudar o status é
  registrar o que outro registro decidiu sobre ele; o corpo é história e fica.
- **O histórico de amplitude do roadmap fica.** Uma checagem de arquitetura já
  isenta o roadmap e os registros de decisão de citarem um total antigo, com a
  razão escrita nela mesma. Esta feature acrescenta a seção que falta em vez de
  reescrever o que existe.
- **Os bans são medidos contra dados, não contra a intenção da tela.** Uma tela
  que passa contra o dataset determinístico e viola contra o staging tem entrada
  de allowlist até a feature dona consertar a origem do dado.
- **A allowlist é uma dívida declarada.** Ela é o preço de os bans existirem hoje
  sem quebrar o gate. Nove entradas na partida; o número é reportado a cada slot.
- **O staging é um só.** Quem roda contra ele é o orquestrador, no fim do slot,
  com os diffs mergeados. Esta feature entrega a ferramenta, não a política de
  quando usá-la.
- **A árvore parte de verde.** A rodada de verificação anterior a qualquer escrita
  é capturada, senão uma falha preexistente é debitada desta feature.
- **Nada aqui muda comportamento de produto.** Nenhuma rota, nenhum contrato,
  nenhum dado de operador. O que muda é o que as regras dizem e o que os gates
  medem.

## Dependencies

- Nenhuma feature anterior. Esta é a raiz da onda e roda sozinha.
- O registro de decisão vigente sobre paridade já existe e é committed; esta
  feature o absorve na constituição e conserta o ponteiro que ele faz.
- Bloqueia **todas** as outras features da onda: elas planejam contra a
  constituição emendada, herdam a exigência de declarar composition root, rodam
  contra os bans transversais e usam o backing de staging para validar.

## Out of Scope

- Consertar qualquer uma das telas que violam os bans. Cada uma é de outra
  feature; aqui elas só ganham entrada de allowlist.
- Normalizar as onze linhas preexistentes do índice de registros e os corpos dos
  registros já aceitos que citam número de artigo. É passe editorial próprio, e
  um registro aceito é imutável.
- A decisão sobre idioma de interface, que a auditoria de regras levantou. Ela
  pede registro de decisão e emenda próprios e não bloqueia nenhuma feature desta
  onda.
- A decisão sobre o estatuto das duas superfícies de console, que a auditoria
  também levantou. Fora do recorte desta onda.
- Migrar o viewport global do Playwright de 1440×900 para Full HD. As regras
  novas declaram o seu próprio viewport, como a suíte já faz.
- Executar a remoção do deployment legado no repositório de GitOps. A tarefa
  documenta; o operador executa.
- Qualquer mudança de comportamento do produto.
