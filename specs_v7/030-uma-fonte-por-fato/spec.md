# Feature Specification: Uma fonte por fato — cada fato tem um dono, e toda tela que o cita lê do dono

**Feature Branch**: `feat/v7-030-uma-fonte-por-fato`

**Created**: 2026-08-23

**Status**: Draft

**Input**: User description: "Verified/Stored do provider numa fonte só, causa
de vazio dos Decisions/Knowledge dizendo a verdade, chips do incidente
derivados de leitura bem-sucedida (senão estado desconhecido), listas dinâmicas
(fim do Full Route Cache congelado) — com teste que prova que a lista bate no
gateway. Mais os dois seams: a chave do modelo vem do vault e não do ambiente, e
a credencial de time verificada verde é a credencial que a investigação usa."

**Referência visual (DoD)**: nenhuma imagem. A onda v7 não tem mockups prontos e
esta feature é **rework de telas existentes**, não tela nova — o normativo é a
seção **"Alegações normativas"** abaixo, codificada em
`console/tests/e2e/030-uma-fonte-por-fato.acceptance.spec.ts`, confirmada
vermelha antes de qualquer implementação. Viewport normativo de medição:
**1920×1080**.

**Evidência**: DIAGNOSTICO da onda §2, defeitos **P1-5** (estados contando
histórias diferentes sobre o mesmo fato) e **P1-6** (listas renderizam de cache
como se fossem vivas), mais os itens do `backlog.md` da raiz "Four seams between
what is configured and what runs" (o quarto — a chave do modelo vinda do
ambiente e não do vault) e "Two seams the deep verify opened rather than closed"
(o primeiro — credencial de time verde e invisível para a investigação).

---

## O que esta feature decide, em uma frase

Um fato do produto tem **um dono declarado**; toda superfície que cita esse fato
lê do dono; e **nenhuma superfície afirma o negativo de um fato cuja leitura
falhou** — nesse caso ela diz que não sabe, e diz o que falhou.

Os quatro fatos desta feature e seus donos:

| Fato | Dono | Quem hoje cita outra coisa |
|---|---|---|
| Uma credencial de provider **está guardada** | o vault | ninguém — está certo |
| Uma credencial de provider **foi verificada** | o registro de verificação (`VerificationLedger`, subject `model_provider`) | `/v1/setup/checklist` deriva de presença no vault e reporta "Stored" para o mesmo Gemini que Models & providers reporta "Verified" |
| **Por que esta tela está vazia** | o gating que de fato existe neste deployment | `setupCause` afirma "investigations cannot run until [setup] done" com 37 investigações concluídas |
| **Se este incidente tem investigação** | a leitura de `/v1/incidents/{id}` que deu certo | o chip afirma "No investigation" quando a leitura falhou |
| **Em que estado um run está** | a enumeração de estado de run do domínio de persistência, que é o que o gateway serve verbatim | as fixtures gravam `succeeded` e `awaiting_approval`, que o produto nunca emite; o vocabulário do console declara `queued`, `waiting` e `succeeded`, que ele nunca recebe |

E dois seams onde o dono é o mesmo mas a **resolução** difere:

| Seam | Como o console resolve | Como o runtime resolve | Consequência |
|---|---|---|---|
| Chave do provider de modelo | vault primeiro, ambiente depois, pelo time do caller | lease do vault tirada no boot com o handle **org-wide** | uma chave gravada sob o time do operador verifica verde e não é a que investiga |
| Credencial de vendor | deep verify resolve como o **time do caller** | `compose_integration_access` liga o binding **org-wide** | integração verificada verde contra o vendor real, e toda investigação reporta a mesma integração indisponível |

---

## Alegações normativas

Frases curtas, individualmente testáveis — **uma vírgula é fronteira de
requisito**. O acceptance spec codifica cada uma; o vermelho de cada uma é
confirmado e registrado antes da implementação. A coluna **staging-safe** diz
quais rodam contra `https://stg-ninjasre.lan.kyo.ninja` (leitura pura; nenhuma
escreve, nenhuma destrói dado).

| # | Alegação | Staging-safe |
|---|---|---|
| AN-01 | O mesmo provider nunca aparece com dois estados diferentes em duas telas no mesmo instante (a navegação é `/first-run` → `/settings/models-providers`, sem recarregar credencial entre as duas). | sim |
| AN-02 | Um provider cujo último check registrado passou aparece como **Verified** em `/first-run`. | sim |
| AN-03 | Um provider com credencial guardada e nenhum check registrado aparece como **Stored**, e a frase abaixo dele diz que ninguém verificou. | sim |
| AN-04 | Um provider cujo último check registrado **falhou** nunca aparece como Stored nem como Verified. | sim |
| AN-05 | Um provider sem credencial aparece como **Not connected**. | sim |
| AN-06 | `/decisions` vazio explica a causa da própria tela e não cita passos de setup pendentes. | sim |
| AN-07 | `/knowledge` vazio explica a causa da própria tela e não cita passos de setup pendentes. | sim |
| AN-08 | Nenhuma tela cita setup incompleto como causa de vazio num deployment onde ao menos uma investigação já concluiu. | sim |
| AN-09 | Uma tela que cita setup incompleto como causa nomeia **qual** passo pendente é o que a bloqueia, e não uma contagem solta. | sim |
| AN-10 | O chip de investigação em `/incidents/{id}` tem exatamente quatro estados: Running, Finished, None, Unknown. | sim |
| AN-11 | O chip aparece como **Unknown** quando, e somente quando, a leitura do incidente falhou. | não (exige injeção de falha na leitura) |
| AN-12 | O chip Unknown nomeia a dependência que falhou, na mesma linha ou no seu tooltip. | não (mesma razão) |
| AN-13 | Nenhuma tela do console imprime uma negativa de existência ("No investigation", "No proposal", "no resources") num painel cujo `PanelState` é `error`. | sim |
| AN-14 | Um incidente criado depois do primeiro load aparece em `/incidents` em **um** recarregamento. | não (é escrita no ambiente) |
| AN-15 | Carregar `/incidents` emite ao menos uma requisição ao gateway. | não (exige contador no backing de mock) |
| AN-16 | Carregar `/runs` emite ao menos uma requisição ao gateway. | não (idem) |
| AN-17 | Carregar `/incidents/{id}` emite ao menos uma requisição ao gateway. | não (idem) |
| AN-18 | Nenhuma rota sob o shell aparece como pré-renderizada na saída do build de produção. | n/a (é gate de build) |
| AN-19 | O cabeçalho do first-run, o painel de checklist e o card do dashboard citam o mesmo par total/pendentes. | sim |
| AN-20 | Um provider verificado verde é o provider que a investigação chama: o registro da resolução nomeia a mesma origem (vault) e o mesmo time que a verificação usou. | sim (é leitura de log/audit) |
| AN-21 | Uma integração verificada verde é a integração que a investigação enxerga: a resolução do binding de ferramentas e a resolução do deep verify nomeiam o mesmo handle. | sim (idem) |
| AN-22 | Nenhuma fixture serve um estado de run que o produto não emite. | n/a (é gate de repositório) |
| AN-23 | O vocabulário de estado de run do console é exatamente o que o gateway serve, sem valor a mais. | n/a (é gate de repositório) |
| AN-24 | Uma fixture com um estado de run inventado reprova o gate, nomeando o arquivo e o valor. | n/a (idem) |

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - O provider tem um estado, não dois (Priority: P1)

Um operador acaba de colar a chave do Gemini no first-run e apertar verify. A
tela de Models & providers diz **Verified**. Ele volta ao first-run para
continuar o passo seguinte e o mesmo Gemini diz **Stored — You are here**. Ele
não sabe se verificou ou não, e o passo do checklist nunca fecha.

**Why this priority**: é o defeito que trava o setup. O passo "Connect a model
provider" é pré-requisito dos três seguintes no próprio checklist, então um
provider que verifica numa tela e não na outra deixa o deployment
permanentemente "3 steps outstanding" — que é exatamente o texto que a US2 vai
encontrar mentindo em `/decisions`. Os dois defeitos são o mesmo defeito visto
de dois lugares.

**Independent Test**: com uma credencial de provider guardada e um check
registrado que passou, abrir as duas telas em sequência e comparar a palavra que
cada uma usa para o mesmo provider.

**Acceptance Scenarios**:

1. **Given** um provider com credencial guardada e um check registrado que
   passou, **When** `/first-run` é aberto, **Then** ele mostra Verified.
2. **Given** o mesmo deployment, **When** `/settings/models-providers` é aberto,
   **Then** ele mostra Verified para o mesmo provider.
3. **Given** um provider com credencial guardada e nenhum check registrado,
   **When** as duas telas são abertas, **Then** as duas mostram Stored.
4. **Given** um provider cujo último check registrado falhou, **When** as duas
   telas são abertas, **Then** nenhuma das duas mostra Stored nem Verified, e as
   duas dizem a mesma coisa.
5. **Given** um provider sem credencial, **When** as duas telas são abertas,
   **Then** as duas mostram Not connected.
6. **Given** uma credencial de provider substituída, **When** as duas telas são
   abertas de novo, **Then** nenhuma das duas mostra Verified, porque o veredito
   pertencia à chave que foi trocada.

---

### User Story 2 - A tela vazia diz por que ela, especificamente, está vazia (Priority: P1)

Um operador abre `/decisions` num deployment que rodou 37 investigações e lê
"3 step(s) are outstanding, and investigations cannot run until they are done".
Ele vai ao `/runs`, conta 37 investigações concluídas, e para de acreditar na
tela. A causa verdadeira é outra e é acionável: nenhuma investigação terminou
propondo remediação.

**Why this priority**: uma causa falsa é pior que nenhuma causa. Ela manda o
operador para a tela errada, e é a segunda vez que o produto afirma causalidade
que o seu próprio gating não tem — a primeira foi o passo de provider da US1.

**Independent Test**: num deployment com ao menos uma investigação concluída e
passos de checklist pendentes, abrir `/decisions` e `/knowledge` e ler a
sentença de causa.

**Acceptance Scenarios**:

1. **Given** um deployment com ao menos uma investigação concluída, **When**
   `/decisions` está vazia, **Then** a causa exibida é a da própria tela e não
   menciona passos de setup.
2. **Given** o mesmo deployment, **When** `/knowledge` está vazia, **Then** vale
   o mesmo.
3. **Given** um deployment onde nenhuma investigação jamais concluiu e o passo
   de runtime de investigação está pendente, **When** `/decisions` está vazia,
   **Then** a causa exibida é o setup, e ela nomeia o passo que bloqueia.
4. **Given** uma tela que cita o setup como causa, **When** a sentença é lida,
   **Then** ela nomeia um passo pendente pelo título e não apenas uma contagem.
5. **Given** um deployment configurado e sem nada errado, **When** uma tela está
   vazia, **Then** ela mantém as suas próprias palavras sobre o mecanismo, sem
   causa de deployment por cima.

---

### User Story 3 - Um chip nunca afirma o negativo de uma leitura que falhou (Priority: P1)

O operador vê **INVESTIGATING** na lista de incidentes, abre o incidente, e o
detalhe mostra **No investigation**. As duas telas não discordam sobre o
incidente: uma leu e a outra não conseguiu ler, e a que não conseguiu afirmou
que não existe.

**Why this priority**: é a forma mais cara de mentira de tela, porque é
indistinguível de um fato. "Não existe investigação" e "não consegui saber" têm
ações opostas — a primeira é iniciar uma, a segunda é olhar por que a leitura
falhou.

**Independent Test**: com a leitura de `/v1/incidents/{id}` recusada pelo
backing, abrir o detalhe do incidente e ler o chip.

**Acceptance Scenarios**:

1. **Given** um incidente cuja leitura de detalhe falhou, **When** o detalhe é
   aberto, **Then** o chip de investigação diz que o estado é desconhecido.
2. **Given** o mesmo caso, **When** o chip é lido, **Then** ele nomeia a
   dependência que falhou.
3. **Given** um incidente cuja leitura deu certo e que não tem investigação,
   **When** o detalhe é aberto, **Then** o chip diz que não há investigação.
4. **Given** um incidente com investigação em curso, **When** o detalhe é
   aberto, **Then** o chip diz que está rodando.
5. **Given** um incidente com investigação que entregou relatório, **When** o
   detalhe é aberto, **Then** o chip diz que terminou.
6. **Given** qualquer painel do console em estado de erro, **When** o painel é
   lido, **Then** ele não afirma a inexistência do que ele mostraria.

---

### User Story 4 - A lista mostra o presente (Priority: P1)

Um operador recarrega `/incidents` para ver se algo mudou. A página é servida de
um cache e nenhuma requisição chega ao gateway. Ele está olhando o passado sem
nenhum aviso de que é o passado.

**Why this priority**: uma lista de incidentes congelada é a falha silenciosa de
um produto de SRE. Não há sintoma na tela — ela parece funcional, e é o defeito
que só aparece quando já custou.

**Independent Test**: contar, no backing, quantas requisições o load de
`/incidents` produziu, e comparar com zero.

**Acceptance Scenarios**:

1. **Given** o console em produção, **When** `/incidents` é carregada, **Then**
   ao menos uma requisição chega ao gateway.
2. **Given** o console em produção, **When** `/runs` é carregada, **Then** ao
   menos uma requisição chega ao gateway.
3. **Given** o console em produção, **When** `/incidents/{id}` é carregada,
   **Then** ao menos uma requisição chega ao gateway.
4. **Given** um incidente criado depois do primeiro load, **When** `/incidents`
   é recarregada uma vez, **Then** o incidente novo está na lista.
5. **Given** o build de produção do console, **When** a saída do build é
   inspecionada, **Then** nenhuma rota sob o shell consta como pré-renderizada.
6. **Given** as rotas tocadas por esta feature, **When** o orçamento de primeira
   pintura é medido, **Then** ele continua dentro do orçamento declarado.

---

### User Story 5 - A chave que o operador verificou é a chave que investiga (Priority: P1)

Um operador cola a chave do provider no first-run, vê verificar verde contra o
endpoint real, e a investigação chama o provider com o que o container recebeu
no ambiente — que num deployment configurado pelo vault é nada.

**Why this priority**: é o seam do backlog, e é o que faz o resto desta feature
valer alguma coisa. Uma tela que diz a verdade sobre uma chave que não é usada
continua sendo uma tela que engana.

**Independent Test**: com uma chave só no vault e nenhuma no ambiente, disparar
uma investigação e ler o registro da resolução — sem revelar o valor.

**Acceptance Scenarios**:

1. **Given** uma chave de provider apenas no vault, **When** o processo compõe a
   sua resolução de credenciais, **Then** o registro nomeia o vault como origem
   para aquele provider.
2. **Given** o mesmo deployment, **When** uma investigação roda, **Then** ela
   alcança o provider.
3. **Given** uma chave apenas no ambiente, **When** o processo compõe, **Then**
   o registro nomeia o ambiente e a investigação continua funcionando.
4. **Given** uma chave trocada no vault depois do boot, **When** a próxima
   investigação roda, **Then** ela usa a chave nova sem reinício.
5. **Given** qualquer um dos casos acima, **When** o registro é lido, **Then**
   ele não contém nenhum valor de credencial.

---

### User Story 6 - Verificado verde é enxergado pela investigação (Priority: P1)

Um operador conecta uma integração sob o seu time, vê o deep verify passar
contra o vendor real, e toda investigação reporta aquela mesma integração como
indisponível — porque as ferramentas rodam sob o handle org-wide e o deep verify
resolveu como o time dele.

**Why this priority**: é a segunda metade da mesma promessa da US5, e é a que
decide se `/integrations` significa alguma coisa. Verde numa tela e ausente na
investigação é o mesmo defeito de "uma fonte por fato", exercido na resolução em
vez de na leitura.

**Independent Test**: para cada integração configurada, comparar o handle que a
verificação resolveu com o handle que o binding de ferramentas resolve.

**Acceptance Scenarios**:

1. **Given** uma credencial gravada sob um time, **When** a verificação e o
   binding de ferramentas resolvem, **Then** os dois nomeiam o mesmo handle.
2. **Given** uma credencial gravada no handle org-wide, **When** os dois
   resolvem, **Then** os dois nomeiam o handle org-wide.
3. **Given** uma integração cuja credencial só existe sob um time, **When** uma
   investigação usa uma ferramenta daquela integração, **Then** a ferramenta não
   se reporta indisponível por falta de credencial.
4. **Given** dois times com credencial para a mesma integração, **When** o
   binding é composto, **Then** o processo não escolhe um em silêncio: ele
   registra a ambiguidade nomeando a integração e resolve pelo handle org-wide.
5. **Given** o caso ambíguo acima, **When** o console mostra a integração,
   **Then** ele diz que mais de um time detém credencial para ela.

---

### User Story 7 - A suíte não pode passar verde sobre um vocabulário que o produto não fala (Priority: P1)

A suíte de console inteira passa verde enquanto o staging está quebrado, porque
as fixtures gravam `"status": "succeeded"` para um run — e o produto **nunca**
emite essa palavra. O gateway serve o estado do run verbatim da enumeração do
domínio, que diz `running`, `suspended`, `completed`, `cancelled`, `failed`,
`interrupted`. As fixtures também gravam `awaiting_approval`, que não existe em
lugar nenhum. E o vocabulário do console declara `queued`, `waiting` e
`succeeded`, três palavras que ele nunca vai receber.

**Why this priority**: é "uma fonte por fato" aplicada ao próprio aparato de
teste, e é a razão de os outros defeitos desta feature terem sobrevivido a
tantas rodadas de verde. Uma fixture que fala um vocabulário inventado não
testa o produto: ela testa a fixture. É a mesma classe de mentira das telas —
uma afirmação sobre um estado que ninguém mediu — exercida um nível abaixo,
onde ela é mais cara, porque desarma tudo o que está acima.

**Independent Test**: varrer todo estado de run que qualquer fixture serve e
todo estado de run que o console declara conhecer, e comparar os dois conjuntos
com a enumeração do domínio.

**Acceptance Scenarios**:

1. **Given** a árvore de fixtures, **When** todo estado de run servido é
   coletado, **Then** cada valor é um membro da enumeração do domínio.
2. **Given** o vocabulário de estado de run do console, **When** ele é lido,
   **Then** ele não declara nenhum valor que o gateway não serve.
3. **Given** uma fixture com um estado de run inventado, **When** o gate roda,
   **Then** ele reprova nomeando o arquivo e o valor.
4. **Given** o vocabulário do console ampliado com um valor que o gateway não
   serve, **When** o gate roda, **Then** ele reprova nomeando o valor.
5. **Given** a migração das fixtures, **When** as baselines visuais afetadas são
   recapturadas, **Then** cada recaptura é deliberada e revisável como mudança,
   e nenhuma é substituída por captura fabricada.
6. **Given** um estado de run que o produto emite e o console não sabe desenhar,
   **When** o gate roda, **Then** ele reprova — a checagem vale nas duas
   direções, não só contra o excesso.

### Edge Cases

- **`succeeded` é uma palavra real, do fato errado.** A enumeração de estado de
  **tool call** tem `succeeded`, e é quase certamente de lá que a fixture o
  tomou emprestado. A migração não pode tocar em estado de tool call ao varrer
  estado de run: são dois fatos distintos que compartilham uma palavra.
- **Provider que também é integração do catálogo.** O Gemini aparece nas duas
  listas do checklist — como provider e como vendor. As duas entradas passam a
  derivar do mesmo registro de verificação, então elas não podem discordar; a
  tela de verificação continua não pedindo o mesmo check duas vezes.
- **Registro de verificação ilegível.** Um erro ao ler o registro é "ninguém
  verificou", nunca "falhou". Uma tela que não consegue ler o registro perde o
  Verified e não ganha um vermelho que ninguém mediu.
- **Credencial trocada com veredito antigo.** Trocar a credencial já esquece o
  veredito. A nova leitura do checklist tem de refletir isso na mesma requisição
  seguinte, sem cache próprio.
- **Deployment que nunca investigou e tem setup pendente.** A causa de setup
  continua sendo a certa e continua sendo dita. Esta feature restringe quando
  ela pode ser dita; não a remove.
- **Deployment completo com tela vazia.** Nenhuma causa de deployment é
  aplicada; a tela mantém a explicação do próprio mecanismo.
- **Leitura de detalhe parcialmente bem-sucedida.** O incidente lê e a
  investigação não: o chip de estado do incidente é derivado da leitura que deu
  certo e o chip de investigação é o desconhecido — os dois chips não compartilham
  destino.
- **Rota dinâmica com custo.** Declarar dinâmico tira o cache de rota e não o de
  dados. Se a medição mostrar a primeira pintura fora do orçamento, a saída é
  cache de dados curto por requisição, nunca página congelada.
- **Ambiente sem contador no backing.** O acceptance que conta requisições não
  roda contra staging. A alegação equivalente que roda lá é a de conteúdo (um
  fato novo aparece em um reload), e a spec marca as duas separadamente.
- **Uma fixture que muda de estado muda o que a tela desenha.** A cor, a forma e
  o rótulo de um run mudam com o estado, então migrar `succeeded` para o valor
  do domínio move baselines visuais. Isso é resultado correto, não dano
  colateral: a baseline anterior registrava uma tela que o produto não produz.
- **Um estado do domínio que nenhuma fixture exercita.** A migração não é
  obrigada a cobrir os seis estados; ela é obrigada a não inventar nenhum. Um
  estado sem fixture é uma lacuna de cobertura a registrar, não um valor a
  fabricar.
- **Ambiguidade de time por integração.** Mais de um time com credencial para o
  mesmo vendor é um caso real e não pode ser resolvido por sorteio. A resolução
  é declarada, registrada e visível.
- **Deployment sem proxy de credencial.** Nada muda: sem proxy não há binding, e
  as ferramentas continuam se reportando indisponíveis por nome.

## Requirements *(mandatory)*

### Vocabulário (herdado, continua normativo)

**Not connected · Stored · Verified · Degraded · Failing**. Esta feature não
inventa palavra nova de estado de credencial; ela faz mais telas dizerem a
palavra certa. "Degraded" continua sendo a palavra do painel de integrações
para um vendor que respondeu parcialmente, e esta feature não a redefine.

### Verified/Stored numa fonte só

- **FR-001**: O checklist de setup DEVE derivar o estado de verificação do
  provider do registro de verificação, e não da presença de uma credencial.
- **FR-002**: O checklist de setup DEVE continuar derivando "guardada" da
  presença de uma credencial no vault.
- **FR-003**: O checklist de setup e a listagem de providers DEVEM reportar o
  mesmo estado para o mesmo provider no mesmo instante.
- **FR-004**: O checklist de setup NÃO DEVE fazer chamada ao endpoint do
  provider para responder.
- **FR-005**: O vocabulário de prontidão servido pelo checklist DEVE distinguir
  quatro estados: ausente, guardada, verificada e falhando.
- **FR-006**: Um provider cujo último check registrado falhou DEVE ser reportado
  como falhando, e não como guardada.
- **FR-007**: Uma integração cujo último check registrado falhou DEVE ser
  reportada como falhando, e não como guardada.
- **FR-008**: Um registro de verificação ausente DEVE ser reportado como "não
  verificada", nunca como falha.
- **FR-009**: Um registro de verificação ilegível DEVE ser tratado como ausente.
- **FR-010**: Toda superfície que hoje lê o vocabulário de três estados DEVE
  passar a tratar o quarto sem cair no estado errado por omissão.
- **FR-011**: O texto sob o passo de provider DEVE dizer o que o último check
  encontrou quando existe um, e que ninguém verificou quando não existe.

### Causas de vazio que dizem a verdade

- **FR-012**: A causa de setup NÃO DEVE ser exibida num deployment onde ao menos
  uma investigação já concluiu.
- **FR-013**: A causa de setup NÃO DEVE afirmar que investigações não podem
  rodar, salvo quando o passo que de fato as impede está pendente.
- **FR-014**: A causa de setup DEVE nomear o passo pendente que a justifica.
- **FR-015**: `/decisions` vazia DEVE explicar a causa específica da tela quando
  a causa de setup não se aplica.
- **FR-016**: `/knowledge` vazia DEVE explicar a causa específica da tela quando
  a causa de setup não se aplica.
- **FR-017**: Toda tela que hoje usa a causa de setup DEVE continuar tendo uma
  causa própria, específica e acionável para o caso em que a de setup não se
  aplica.
- **FR-018**: Uma leitura de checklist que falhou DEVE continuar resolvendo para
  "nada pendente", deixando a tela com as suas próprias palavras.
- **FR-019**: O catálogo de mensagens DEVE ganhar as sentenças novas em inglês.
- **FR-020**: O catálogo de mensagens DEVE ganhar as mesmas sentenças em pt-BR.
- **FR-021**: A sentença que hoje afirma causalidade de setup DEVE deixar de
  existir na forma em que ela afirma o que o gating não tem.

### Chips derivados de leitura bem-sucedida

- **FR-022**: O chip de investigação do detalhe de incidente DEVE ter quatro
  estados: rodando, terminada, nenhuma e desconhecida.
- **FR-023**: O chip DEVE ser desconhecido quando a leitura de que ele depende
  falhou.
- **FR-024**: O chip NÃO DEVE ser desconhecido quando a leitura deu certo.
- **FR-025**: O chip desconhecido DEVE nomear a dependência que falhou.
- **FR-026**: Nenhum painel em estado de erro DEVE afirmar a inexistência do que
  ele mostraria.
- **FR-027**: A derivação de estado a partir de uma leitura DEVE ser feita por
  um caminho único, reutilizável, e não repetida por tela.
- **FR-028**: A regra transversal de UI DEVE ganhar o banimento de negativa de
  existência sobre painel em erro.

### Listas dinâmicas

- **FR-029**: Toda rota de lista do console DEVE se declarar dinâmica no próprio
  arquivo de rota, sem depender de herança de um segmento acima.
- **FR-030**: Toda rota de detalhe do console DEVE fazer o mesmo.
- **FR-031**: Nenhuma rota sob o shell DEVE constar como pré-renderizada na
  saída do build de produção.
- **FR-032**: Um gate do repositório DEVE reprovar quando uma rota sob o shell
  passar a constar como pré-renderizada.
- **FR-033**: Um teste DEVE provar que o load de uma lista produz ao menos uma
  requisição ao gateway, contada do lado do gateway.
- **FR-034**: O mesmo DEVE valer para uma rota de detalhe.
- **FR-035**: Um teste DEVE provar que um fato novo aparece em um único
  recarregamento.
- **FR-036**: A primeira pintura das rotas tocadas DEVE permanecer dentro do
  orçamento declarado do console.
- **FR-037**: Nenhuma leitura de superfície DEVE deixar de ser por requisição.

### A chave do modelo vem do vault

- **FR-038**: A resolução de credencial de provider do processo DEVE preferir o
  vault e cair para o ambiente.
- **FR-039**: Essa resolução DEVE ser construída numa composition root de
  serving e alcançável a partir dela.
- **FR-040**: A troca de uma credencial de provider DEVE passar a valer sem
  reinício do processo.
- **FR-041**: O registro dessa composição DEVE nomear, por provider, de onde a
  credencial veio.
- **FR-042**: Esse registro NÃO DEVE conter valor de credencial.
- **FR-043**: A resolução do processo e a resolução da rota de verificação DEVEM
  usar a mesma ordem de preferência.

### Credencial de time e binding de ferramentas resolvem igual

- **FR-044**: A resolução do handle de credencial de uma integração DEVE ser
  respondida por um caminho único, usado tanto pela verificação quanto pelo
  binding de ferramentas.
- **FR-045**: Uma credencial gravada sob um time DEVE ser alcançável pelas
  ferramentas daquela integração.
- **FR-046**: Uma credencial gravada no handle org-wide DEVE continuar sendo
  alcançável exatamente como hoje.
- **FR-047**: Quando mais de um time detém credencial para a mesma integração, o
  processo NÃO DEVE escolher um em silêncio.
- **FR-048**: Esse caso DEVE ser registrado nomeando a integração.
- **FR-049**: Esse caso DEVE ser visível na superfície que mostra a integração.
- **FR-050**: A resolução do binding NÃO DEVE ler nenhum valor de credencial.
- **FR-051**: A mesma resolução DEVE valer para o lease de credencial de
  provider de modelo.
- **FR-052**: Um teste DEVE provar que verificado verde implica alcançável pela
  investigação, para uma credencial de time.

### Contagens do first-run coerentes

- **FR-053**: O cabeçalho do first-run, o painel de checklist e o card do
  dashboard DEVEM citar o mesmo total e o mesmo número de pendentes.
- **FR-054**: Essa contagem DEVE vir de uma única derivação.
- **FR-055**: Nenhuma superfície DEVE computar um segundo "quanto falta" a
  partir de uma lista que não é a do checklist.

### Vocabulário de estado de run numa fonte só

- **FR-059**: Todo estado de run que uma fixture serve DEVE ser um membro da
  enumeração de estado de run do domínio.
- **FR-060**: As fixtures que hoje servem um estado que o produto não emite
  DEVEM passar a servir o estado do domínio que corresponde à situação que elas
  descrevem.
- **FR-061**: O vocabulário de estado de run do console NÃO DEVE declarar
  nenhum valor que o gateway não serve.
- **FR-062**: O vocabulário de estado de run do console DEVE declarar todo valor
  que o gateway serve.
- **FR-063**: Um gate do repositório DEVE reprovar quando uma fixture servir um
  estado de run fora da enumeração do domínio.
- **FR-064**: Esse gate DEVE nomear o arquivo e o valor ao reprovar.
- **FR-065**: Esse gate DEVE reprovar também quando o vocabulário do console
  divergir do que o gateway serve, em qualquer das duas direções.
- **FR-066**: A migração NÃO DEVE alterar nenhum estado de tool call, que é
  outro fato com outra enumeração.
- **FR-067**: Toda baseline visual afetada pela migração DEVE ser recapturada
  deliberadamente, como mudança revisável.
- **FR-068**: Nenhuma baseline afetada DEVE ser substituída por captura
  fabricada nem apagada para o gate passar.
- **FR-069**: O gerador de dados em escala do plano de mock DEVE tirar os seus
  estados da mesma enumeração.

### Fronteiras desta feature

- **FR-056**: Esta feature NÃO DEVE alterar o contrato de resumo de
  investigação.
- **FR-057**: Esta feature NÃO DEVE compor nenhum portão de remediação nem de
  autonomia.
- **FR-058**: Esta feature NÃO DEVE alterar a identidade de incidente nas URLs.

### Key Entities

- **Fato do produto**: uma afirmação que mais de uma tela cita — "esta
  credencial foi verificada", "este incidente tem investigação", "faltam N
  passos". Tem exatamente um dono.
- **Dono de um fato**: o registro que responde por ele. Vault para "guardada",
  registro de verificação para "verificada", a leitura bem-sucedida do detalhe
  para "tem investigação", o checklist para "quanto falta".
- **Estado desconhecido**: o terceiro valor de toda leitura de estado, distinto
  do positivo e do negativo, que existe porque uma leitura pode falhar. Nomeia a
  dependência que o produziu.
- **Prontidão**: quão longe uma coisa está de funcionar — ausente, guardada,
  verificada, falhando. Distinto do estado de um passo, que só tem feito e não
  feito.
- **Handle de credencial**: o par integração e time sob o qual uma credencial
  foi gravada. É o que a verificação e o binding de ferramentas precisam
  resolver igual.
- **Vocabulário de estado**: o conjunto fechado de palavras que o produto emite
  para um fato. Tem um dono — a enumeração do domínio — e toda fixture, todo
  gerador e todo mapa de apresentação derivam dele. Um valor que só existe numa
  fixture não é um estado: é uma invenção que a suíte confirma para si mesma.
- **Rota dinâmica**: uma rota cujo HTML é produzido a cada requisição. Distinta
  de uma rota sem cache de dados: o cache de dados é a saída aceitável se a
  latência exigir, a página congelada não é.

## Success Criteria *(mandatory)*

- **SC-001**: Navegando de `/first-run` a `/settings/models-providers` sem
  alterar nada entre as duas, o mesmo provider é descrito pela mesma palavra do
  vocabulário nas duas telas, nos quatro estados possíveis.
- **SC-002**: Num deployment com investigações concluídas, nenhuma tela do
  console cita passos de setup pendentes como causa de vazio.
- **SC-003**: Numa varredura de todas as telas do console com todos os painéis
  em erro, nenhuma negativa de existência é impressa.
- **SC-004**: O contador do backing mostra ao menos uma requisição por load em
  cada rota de lista e de detalhe declarada nesta spec, e zero é uma falha do
  teste.
- **SC-005**: A saída do build de produção não marca nenhuma rota sob o shell
  como pré-renderizada, e o gate reprova se alguma passar a ser.
- **SC-006**: A primeira pintura de `/incidents` e de `/runs` medida a
  1920×1080 fica dentro do orçamento declarado do console, com a medição antes e
  depois registrada.
- **SC-007**: Numa investigação rodada no staging com a chave apenas no vault, o
  registro da composição nomeia o vault como origem, a investigação alcança o
  provider, e nenhum valor de credencial aparece em nenhum registro.
- **SC-008**: Para toda integração configurada no staging, o handle que a
  verificação resolveu e o handle que o binding de ferramentas resolve são o
  mesmo, verificado por consulta e não por inspeção visual.
- **SC-009**: As três superfícies que citam progresso de setup citam o mesmo par
  de números, conferido na mesma sessão.
- **SC-010**: Uma varredura de toda fixture do repositório não encontra nenhum
  estado de run fora da enumeração do domínio, e o gate reprova se algum voltar.
- **SC-011**: O vocabulário de estado de run do console e o conjunto que o
  gateway serve são o mesmo conjunto, conferido pelo gate nas duas direções.
- **SC-012**: Toda baseline visual movida pela migração consta como recaptura
  deliberada no diff, e nenhuma foi apagada.
- **SC-013**: `make verify` termina verde, tendo partido de verde, e a
  comparação entre as duas rodadas é o artefato.
- **SC-014**: Os acceptance marcados staging-safe rodam verdes contra
  `https://stg-ninjasre.lan.kyo.ninja` depois do deploy do slot.

### Consultas de banco exigidas no DoD

A feature alega leitura coerente com o que está gravado, então o DoD inclui
contagens no banco de staging (`ninjasre-stg-db`, `10.20.20.54`), executadas
depois do deploy do slot:

1. Registros de verificação por tipo e desfecho — para confirmar que o estado
   que a tela mostra tem um registro por trás:
   `select kind, outcome, count(*) from verification_records group by 1,2;`
2. O registro do provider de modelo, com o time que o gravou e o modelo
   exercitado — para confirmar AN-02 e AN-20:
   `select subject, outcome, team_node_id, model_id, checked_at from verification_records where kind = 'model_provider';`
3. Handles de credencial vivos, por integração e por time — para confirmar
   AN-21 e a decisão de ambiguidade:
   `select handle, count(*) from credentials group by 1 order by 1;`
4. Investigações concluídas — para confirmar que a causa de vazio de
   `/decisions` e `/knowledge` **não** pode citar setup:
   `select status, count(*) from agent_runs group by 1;`

Os nomes exatos de tabela e coluna são conferidos contra o esquema no momento da
execução; o que a spec fixa é **qual pergunta** cada consulta responde. Uma
consulta que não puder ser executada é reportada como tal, nunca substituída por
uma inspeção de tela.

## Assumptions

- **O registro de verificação é o dono de "verificada", não o vault.** O
  briefing diz "o vault"; o vault responde por "guardada". A rota de providers já
  lê os dois — este é o comportamento que o checklist passa a copiar, e por isso
  a decisão é adotar a fonte que já existe em vez de criar uma terceira.
- **O registro de verificação é por organização e não por time**, por decisão já
  tomada e documentada no próprio port: a pergunta é "alguém neste deployment
  fez isto funcionar". Esta feature não a reabre; ela usa essa propriedade.
- **A composição da resolução de credencial de provider já existe.** O caminho
  vault-primeiro-ambiente-depois está escrito e é chamado no boot. Esta feature
  **verifica que continua composto** e fecha a metade que falta — a dimensão de
  time —, em vez de reescrever o que já está lá.
- **A causa nomeada no DIAGNOSTICO para as listas congeladas é uma hipótese.** O
  segmento do shell já se declara dinâmico e a página de incidentes já espera
  `searchParams`, duas coisas que sozinhas tirariam a rota do Full Route Cache.
  A spec exige a **propriedade observável** e o **teste**, e o plano exige
  identificar a camada real antes de escolher o remédio.
- **Esta feature é a dona dos arquivos de escrita única no seu slot.** As
  chaves de i18n, as rotas e o registro de telas visuais são editados aqui; a
  feature par entrega as suas como bloco no relatório final.
- **O estado de partida do detalhe de incidente é o pós-merge do slot
  anterior.** A tela foi tocada por outra feature e esta trabalha sobre o
  resultado, não sobre o diagnóstico anterior a ele.
- **Nenhum acceptance escreve no staging.** Os que precisam escrever rodam só
  contra o backing de mock, e a spec diz quais.
- **O dono do estado de run é a enumeração do domínio de persistência.** Há três
  enumerações de estado de run na árvore — a do runtime, a do store, e a lista
  que o console declara conhecer — e é a do **store** que o gateway serve
  verbatim ao console. Ela é a fonte desta feature. A do runtime é sobre como
  um run terminou dentro do laço, é outro fato, e esta feature não a unifica com
  a do store: fazer isso é uma decisão maior, do dono do contrato de runs, e a
  spec a registra como observação em vez de resolvê-la de passagem.
- **A feature de leitura do relato manteve `succeeded` de propósito.** Ela
  acrescentou os valores do domínio ao vocabulário do console e deixou o valor
  inventado na lista para não derrubar baselines no seu próprio slot. A purga é
  desta feature, que roda depois, e as baselines caem aqui.

## Dependencies

- Depende da feature de governança da onda, pelas regras novas e pela extensão
  da suíte transversal com os bans desta rodada — o ban de negativa sobre painel
  em erro é registrado lá e exercitado aqui.
- Depende do estado pós-merge do slot que tocou o detalhe de incidente e a
  identidade endereçável: o título e o id opaco vêm de lá, e esta feature não os
  refaz.
- É par de slot da feature de confiança de certificado, que cede a esta as
  strings de console de que precisar.
- Bloqueia a feature de fechamento do laço ponta a ponta: o cenário final
  depende de a lista mostrar o presente e de o estado do provider ser um só.

## Out of Scope

- O contrato de relato da investigação, headline e report — de outra feature.
- Renderização de markdown, transcript e custo — de outra feature.
- Id opaco de incidente, redirects de rota e título de incidente — de outra
  feature.
- Composição dos portões de remediação e autonomia, e a tela de Decisions viva —
  de outra feature. Esta aqui só faz a tela vazia dizer a verdade enquanto ela
  está vazia.
- Confiança de certificado e o desbloqueio do Proxmox — da feature par.
- Guias de credencial, `min_scope` e `guide_url` — de outra feature.
- Qualquer mudança no modelo de times, papéis ou permissões. A decisão de
  resolução de handle é sobre **qual handle**, nunca sobre quem pode o quê.
- Qualquer relaxamento do fail-closed dos stubs de remediação.
- Migração de credenciais entre handles. Um deployment com credencial sob um
  time continua com ela onde está.
