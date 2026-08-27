# Feature Specification: Decisão composta — a metade do produto que age passa a existir

**Feature Branch**: `feat/v7-040-decisao-composta`

**Created**: 2026-08-23

**Status**: Draft

**Input**: User description: "Os portões que já estão escritos são compostos na
composition root de serving, em propose-only, com fail-closed intacto:
investigação com diagnóstico → proposta com plano de reversão → aprovação
humana pelas rotas já permissionadas → execução através do portão, que grava a
aprovação e o plano antes de qualquer mudança → resultado gravado. Interações
pendentes ganham onde existir. A seleção de ferramentas passa a filtrar por
nível de efeito colateral e pelas integrações que o time conectou. Decisions
deixa de estar vazio porque passa a haver dado."

**Referência visual (DoD)**: nenhuma. Esta feature **não tem tela própria** e é
backend puro. A tela de Decisions já existe, com as duas abas que leem as rotas
de aprovação e de proposta; o que falta nela é dado, e o dado é o que esta
feature produz. A causa falsa de vazio ("investigations cannot run until 3
steps are done") é defeito de outra feature desta onda e **não** é corrigida
aqui. Por isso **não há acceptance spec Playwright nesta feature**: não há
alegação de tela para codificar, e a prova de staging é uma leitura autenticada
de `/v1/approvals` mais contagens no banco.

**Par de slot**: executa em paralelo com a feature de leitura do relato, que é
console puro. Esta feature **não** é dona dos arquivos de escrita única
(catálogo i18n, tabela de rotas do console, registro de telas visuais) e **não
os edita**. Nenhuma string de UI nova é necessária; se a implementação
descobrir que precisa de uma, ela é declarada no relatório final em vez de
escrita.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Uma investigação que conclui propõe a ação, com o desfazer ao lado (Priority: P1)

Um operador olha um incidente cuja investigação terminou com um diagnóstico e
encontra, junto do relato, uma ação proposta: o que seria mudado, em qual
recurso, com que raio de alcance, e como aquilo seria desfeito. A proposta
existe porque o agente pediu para agir e o portão a transformou em pedido de
aprovação, não porque alguém a escreveu à mão.

**Why this priority**: é a razão de a feature existir. Hoje toda investigação
para no diagnóstico, e para não por decisão de política — a política diz
propor — mas porque nada constrói o portão. O operador não consegue distinguir
"o produto decidiu não agir" de "o produto não sabe agir", e essas são coisas
muito diferentes para quem depende dele às três da manhã.

**Independent Test**: rodar uma investigação sintética cujo diagnóstico leva a
uma capacidade de escrita, e conferir que existe no armazenamento um pedido de
aprovação com plano de reversão gravado, vinculado àquela investigação.

**Acceptance Scenarios**:

1. **Given** um deployment com o portão composto e uma investigação que alcança
   uma capacidade de escrita, **When** o agente chama essa capacidade, **Then**
   um pedido de aprovação é gravado com a ação, o recurso, o raio de alcance e
   a razão.
2. **Given** o mesmo pedido, **When** ele é gravado, **Then** o plano de
   reversão é gravado junto, na mesma unidade de trabalho.
3. **Given** uma capacidade de escrita sem plano de reversão derivável e sem
   dispensa registrada, **When** o agente a chama, **Then** nada é enfileirado
   e a recusa nomeia a ausência do plano.
4. **Given** o pedido gravado, **When** a lista de aprovações é pedida ao
   gateway, **Then** ele aparece com o plano de reversão junto.

---

### User Story 2 - Em propose-only a ação para, e a razão é a política (Priority: P1)

Um operador que não ligou autonomia vê a investigação propor a mudança e
parar. A frase que ele lê diz que a política deste deployment é propor, e não
que alguma coisa está faltando. O turno do agente termina com a proposta
registrada e a investigação segue sem a ação.

**Why this priority**: é a diferença entre um produto seguro e um produto
inacabado, e hoje os dois são indistinguíveis do lado de fora. O padrão não
muda com esta feature — propor continua sendo o padrão — mas passa a ser uma
decisão declarada em vez de um efeito de composição ausente.

**Independent Test**: com a política de autonomia num deployment que configurou
nada, exercitar uma capacidade de escrita e conferir que a razão devolvida ao
modelo nomeia a política, que nada foi executado, e que a proposta ficou
gravada.

**Acceptance Scenarios**:

1. **Given** um deployment que configurou nenhuma política de autonomia,
   **When** uma ação de escrita é decidida, **Then** o desfecho é propor e a
   razão nomeia a política.
2. **Given** o mesmo deployment, **When** a ação é decidida, **Then** nada é
   executado e nenhum estado do recurso é alterado.
3. **Given** a mesma ação, **When** o modelo lê o resultado da chamada, **Then**
   ele lê uma recusa que diz que a ação espera por uma pessoa, e a investigação
   continua sem ela.
4. **Given** o interruptor de emergência acionado, **When** uma ação de escrita
   é decidida sob qualquer política, **Then** ela é recusada, o interruptor é
   nomeado como a causa, e nenhum nível de autonomia a atravessa.

---

### User Story 3 - Uma pessoa aprova, e a execução acontece pelo portão (Priority: P1)

Um operador com permissão abre a aprovação pendente, lê a ação, o raio de
alcance e o plano de reversão, e aprova. A ação é executada, e o que aconteceu
fica gravado: o que mudou, quem autorizou, quando, e com qual plano de reversão
ao lado. A execução passa pelo portão — não há segundo caminho.

**Why this priority**: sem esta metade, a proposta é um bilhete que ninguém
pode responder. É P1 e não P2 porque é o que fecha o laço da onda; é
deliberadamente **fora** do que roda contra o ambiente compartilhado, porque
aprovar de verdade em staging é a demonstração assistida da feature final.

**Independent Test**: aprovar um pedido de remediação num ambiente de teste com
plano de controle ligado, e conferir que o resultado ficou gravado com o
identificador da aprovação, e que nada foi executado antes da aprovação.

**Acceptance Scenarios**:

1. **Given** um pedido de remediação pendente, **When** uma pessoa autorizada o
   aprova, **Then** a ação é levada adiante pelo portão e o resultado é gravado
   com o identificador da aprovação.
2. **Given** o mesmo pedido, **When** ele é aprovado, **Then** o plano de
   reversão já estava gravado antes de a execução começar.
3. **Given** um pedido rejeitado, **When** a decisão é registrada, **Then** nada
   é executado e a razão da rejeição fica gravada.
4. **Given** um pedido que expirou sem resposta, **When** ele é lido, **Then**
   ele consta como expirado e nada é executado por causa dele.
5. **Given** o interruptor de emergência acionado depois da aprovação e antes da
   execução, **When** a execução é tentada, **Then** ela é recusada nomeando o
   interruptor.

---

### User Story 4 - A recusa direta continua sendo a recusa (Priority: P1)

Uma capacidade de remediação chamada fora do portão continua respondendo que
não é chamável diretamente. Compor o portão não afrouxa nada: acrescenta o
único caminho por onde uma escrita pode acontecer.

**Why this priority**: é a razão de a metade não composta ser segura em vez de
perigosa, e é exatamente o tipo de proteção que uma feature de composição
apaga por engano ao "fazer funcionar". A garantia é estrutural e permanece
enforçada por teste.

**Independent Test**: chamar cada capacidade de escrita embarcada diretamente e
conferir que todas recusam, com a mesma frase, depois da feature inteira estar
composta.

**Acceptance Scenarios**:

1. **Given** a árvore com o portão composto, **When** qualquer capacidade de
   escrita embarcada é invocada diretamente, **Then** ela recusa, e a recusa
   diz que a chamada passa pelo portão.
2. **Given** a mesma árvore, **When** a execução é tentada sem plano de controle
   ligado, **Then** cada capacidade reporta que nada está configurado, por
   nome.
3. **Given** a política de aprovação de uma organização, **When** ela deixa um
   nível de escrita fora da sua lista, **Then** aquele nível continua sendo
   portado, porque nível de escrita não é preferência organizacional.

---

### User Story 5 - O modelo só recebe ferramenta que este deployment consegue levar adiante (Priority: P1)

Um turno do agente não gasta chamada numa capacidade que só poderia responder
que não é chamável. As capacidades de escrita entram no orçamento de esquemas
quando este deployment tem como levá-las até o portão; quando não tem, ficam
de fora e a exclusão fica registrada.

**Why this priority**: o defeito medido é um turno perdido e um transcript
confuso em toda investigação que ranqueia uma capacidade de remediação para
cima. O orçamento de esquemas é pequeno, e uma vaga gasta com uma recusa é uma
leitura que a investigação não fez.

**Independent Test**: com a mesma investigação e o mesmo alerta, comparar a
lista de ferramentas oferecidas num deployment que pode remediar e num que não
pode, e conferir que a segunda não contém capacidade de escrita.

**Acceptance Scenarios**:

1. **Given** um deployment sem o portão composto, **When** as ferramentas de uma
   investigação são escolhidas, **Then** nenhuma capacidade acima de leitura
   sensível está entre elas.
2. **Given** um deployment com o portão composto e componentes registrados para
   uma capacidade de escrita, **When** as ferramentas são escolhidas, **Then**
   aquela capacidade pode estar entre elas.
3. **Given** um deployment com o portão composto e **sem** componentes para uma
   capacidade de escrita, **When** as ferramentas são escolhidas, **Then**
   aquela capacidade não está entre elas.
4. **Given** qualquer uma das exclusões acima, **When** a investigação é lida
   depois, **Then** a exclusão consta com a razão, e não como ausência
   silenciosa.

---

### User Story 6 - As ferramentas são as do que o time conectou (Priority: P1)

Uma investigação de um time que não conectou um determinado sistema não recebe
as capacidades daquele sistema. E um time que não conectou nada não recebe uma
lista vazia sem explicação: recebe a resposta que já está escrita e nunca
rodou — qual integração conectar, quantas capacidades ela destravaria, e quais
delas serviriam para o alerta que acabou de disparar.

**Why this priority**: é o mesmo seam dos portões, medido no mesmo lugar. Hoje
o investigador de serving ranqueia contra o que o alerta diz e não contra o que
o time tem; o resolvedor que sabe a resposta nunca é instanciado, e o estágio
que a formula bem não tem chamador de produção.

**Independent Test**: resolver o catálogo para um time com uma integração
conectada e para um time sem nenhuma, e conferir que a primeira lista não
contém capacidade de sistema não conectado e que a segunda produz a resposta
nomeada.

**Acceptance Scenarios**:

1. **Given** um time com um conjunto declarado de integrações, **When** as
   ferramentas da investigação são escolhidas, **Then** nenhuma delas exige uma
   integração fora daquele conjunto.
2. **Given** um time sem nenhuma integração conectada, **When** a investigação
   começa, **Then** ela termina com a resposta que nomeia o que conectar,
   quantas capacidades aquilo destravaria e exemplos delas.
3. **Given** o alerta que disparou, **When** a resposta é montada, **Then** a
   integração cujo nome corresponde à fonte do alerta é sugerida primeiro.
4. **Given** dois lugares no repositório capazes de produzir essa resposta,
   **When** a árvore é lida depois desta feature, **Then** exatamente um está
   no caminho de serving e o outro declara de si mesmo que não está, nomeando o
   que o constrói.

---

### User Story 7 - Uma pergunta do agente tem onde aparecer e onde ser respondida (Priority: P2)

Quando a investigação precisa de algo que só uma pessoa sabe — se aquele deploy
era esperado, se o alerta é falso positivo conhecido — a pergunta aparece como
interação pendente daquele run, uma pessoa responde pelas rotas que já existem,
e a investigação continua com a resposta. Uma pergunta sem resposta dentro da
janela é fechada como não respondida, e o agente registra a lacuna em vez de
preenchê-la.

**Why this priority**: é P2 porque a proposta com plano de reversão fecha o laço
sem ela. Está aqui porque é o mesmo seam — as peças estão escritas, o desk
nunca é composto, `pending_interactions` devolve vazio incondicionalmente e
`answer_interaction` recusa — e porque um portão composto sem lugar para a
pergunta é um portão que só sabe dizer não.

**Independent Test**: levantar uma pergunta dentro de um run, listá-la pela
rota de interações pendentes daquele run, respondê-la, e conferir que o run
recebeu a resposta e que a interação consta fechada.

**Acceptance Scenarios**:

1. **Given** um run que levantou uma pergunta, **When** as interações pendentes
   daquele run são pedidas, **Then** a pergunta consta, aberta, com o texto e as
   opções.
2. **Given** a mesma pergunta, **When** uma pessoa autorizada a responde,
   **Then** a interação é fechada e a resposta chega ao run que esperava.
3. **Given** uma interação já respondida, **When** uma segunda resposta chega,
   **Then** a primeira permanece valendo e a segunda é informada de quem
   respondeu antes.
4. **Given** um identificador de interação que nenhum run levantou, **When** ele
   é respondido, **Then** a recusa distingue "ninguém perguntou isso" de "isso
   já foi respondido".
5. **Given** dois runs concorrentes no mesmo processo, **When** cada um levanta
   uma pergunta, **Then** a resposta a uma não fecha a do outro.

---

### User Story 8 - Decisions mostra o que foi proposto (Priority: P2)

Um operador abre Decisions e encontra a aprovação pendente que a investigação
gerou, com a ação, o recurso, o raio de alcance e o plano de reversão. A tela
não muda; o que muda é que existe dado para ela ler.

**Why this priority**: é a consequência visível das histórias 1 e 3, e é a
evidência que o operador consegue conferir sozinho. É P2 porque não há
trabalho de tela nesta feature — se a tela estiver errada, o defeito é de outra
feature desta onda.

**Independent Test**: depois de uma investigação real em staging, pedir a lista
de aprovações ao gateway com credencial de operador e conferir que a proposta
está lá, com o plano de reversão junto.

**Acceptance Scenarios**:

1. **Given** uma investigação que propôs uma ação, **When** a lista de
   aprovações é lida, **Then** a proposta consta como pendente.
2. **Given** a mesma proposta, **When** ela é lida individualmente, **Then** o
   plano de reversão vem com ela.
3. **Given** um deployment onde nada foi proposto ainda, **When** a lista é
   lida, **Then** ela é uma lista vazia e não um erro.

### Edge Cases

- **Ação de escrita cujo recurso não pode ser lido.** O estado anterior é o que
  a aprovação é decidida contra e o que a reversão compara. Um recurso ilegível
  produz um instantâneo declaradamente ilegível, e isso bloqueia a ação em vez
  de virar um instantâneo vazio que compararia igual a outro vazio.
- **Ação sem reversão derivável.** Existe uma capacidade embarcada assim de
  propósito. Ela segue pelo caminho da dispensa: recusada a menos que um
  operador aceite explicitamente, com a aceitação registrada. Esta feature
  **não** cria uma dispensa automática.
- **Duas propostas sobre o mesmo recurso.** A segunda é enfileirada declarando o
  conflito, e as duas passam a ser respondidas contra o estado atual. Nada aqui
  aprova em lote.
- **Aprovação de um recurso que se recuperou sozinho.** O estado mudou desde o
  enfileiramento, e a checagem de conflito que já existe é o que pega isso. A
  execução não acontece contra um estado que ninguém revisou.
- **Interruptor acionado no meio da execução.** A mudança já aconteceu. O
  registro é escrito assim mesmo — abandoná-lo deixaria uma escrita que ninguém
  consegue ver — e o interruptor barra a próxima.
- **Deployment sem plano de controle ligado.** As capacidades de escrita
  reportam que nada está configurado, por nome, e a seleção de ferramentas não
  as oferece. Esta feature não inventa um plano de controle a partir de
  configuração ambiente.
- **Time cuja configuração não pôde ser lida.** A resolução de política falhando
  não pode virar permissão. A ausência de resposta é lida como a postura mais
  estrita, e o motivo fica no registro.
- **Dois runs concorrentes no mesmo processo.** Cada um tem seu portão com seu
  contexto de run e seu balcão de perguntas. Um binding único de processo para
  qualquer um dos dois seria o mecanismo pelo qual a resposta de um incidente
  fecha a pergunta de outro.
- **Investigação iniciada por operador, sem incidente.** Ela não tem incidente
  nem credencial de entrega, e isso não é erro. A proposta que ela gerar
  continua sendo uma proposta com plano de reversão.
- **Capacidade de escrita com componentes registrados mas sem declaração de
  verificação conhecida.** O registro recusa registrar uma capacidade que nomeia
  um sinal que este deployment não produz, e essa recusa acontece na composição,
  não na primeira execução.

## Requirements *(mandatory)*

### Composição dos portões

- **FR-001**: O portão de remediação DEVE ser construído numa composition root
  de serving.
- **FR-002**: O portão de autonomia DEVE ser construído numa composition root
  de serving.
- **FR-003**: O portão de remediação DEVE ser alcançável a partir do caminho que
  serve uma investigação real, e não apenas de testes.
- **FR-004**: O portão de remediação DEVE ser registrado no ponto do laço que
  decide se uma chamada de ferramenta pode acontecer.
- **FR-005**: O portão de autonomia DEVE resolver a política do nó de
  configuração do time do run.
- **FR-006**: O portão de autonomia DEVE ler o interruptor de emergência do
  processo, e não construir um interruptor próprio.
- **FR-007**: A resolução de política que o portão usa e a que a explicação
  publicada usa DEVEM ser a mesma, de modo que o que uma tela prevê e o que o
  portão faz não possam divergir.
- **FR-008**: Um deployment que não configurou política de autonomia DEVE
  resolver para propor, e não para agir.
- **FR-009**: O contexto de run do portão — quem pede, qual time, qual run, qual
  ambiente — DEVE ser vinculado por investigação.
- **FR-010**: Dois runs concorrentes no mesmo processo NÃO DEVEM compartilhar um
  portão que carregue o contexto de um deles.

### Fail-closed intacto

- **FR-011**: O corpo de toda capacidade de remediação DEVE continuar recusando
  a chamada direta.
- **FR-012**: A frase da recusa direta NÃO DEVE mudar.
- **FR-013**: Nenhuma capacidade de escrita DEVE executar sem aprovação ou sem
  entrada de lista de permissão correspondente.
- **FR-014**: O plano de reversão DEVE ser gravado antes de a execução começar.
- **FR-015**: Uma ação sem plano de reversão derivável DEVE ser recusada a menos
  que exista dispensa explícita registrada.
- **FR-016**: Uma organização NÃO DEVE conseguir tirar um nível de escrita do
  portão deixando-o fora da sua lista.
- **FR-017**: O interruptor de emergência DEVE recusar em qualquer nível de
  autonomia.
- **FR-018**: O interruptor DEVE ser reavaliado na execução, e não apenas na
  decisão.
- **FR-019**: Nenhuma tarefa desta feature DEVE remover, afrouxar ou contornar
  qualquer uma das recusas acima.

### O caminho da proposta

- **FR-020**: Uma chamada a capacidade de escrita sob a política de propor DEVE
  produzir um pedido de aprovação gravado.
- **FR-021**: O pedido de aprovação DEVE carregar a ação proposta.
- **FR-022**: O pedido de aprovação DEVE carregar o recurso alvo.
- **FR-023**: O pedido de aprovação DEVE carregar o raio de alcance, ou declarar
  que ele é desconhecido.
- **FR-024**: Um raio de alcance desconhecido DEVE reprovar uma condição de raio
  máximo, nunca passar por ela.
- **FR-025**: O pedido de aprovação DEVE carregar o plano de reversão.
- **FR-026**: O pedido e o plano DEVEM ser gravados na mesma unidade de
  trabalho.
- **FR-027**: O pedido DEVE ser vinculado à investigação que o originou.
- **FR-028**: A razão devolvida ao modelo DEVE dizer que a ação espera por uma
  pessoa.
- **FR-029**: A razão devolvida ao modelo DEVE nomear a política quando foi a
  política que decidiu.
- **FR-030**: A investigação DEVE continuar depois de a proposta ser
  enfileirada.
- **FR-031**: Em propose-only, nenhum estado do recurso DEVE ser alterado.

### Aprovação e execução

- **FR-032**: A aprovação de um pedido de remediação DEVE levar a ação adiante
  através do portão.
- **FR-033**: A execução NÃO DEVE ter nenhum caminho que contorne o portão.
- **FR-034**: A execução DEVE gravar o resultado com o identificador da
  aprovação.
- **FR-035**: A execução DEVE gravar quem aprovou.
- **FR-036**: A rejeição de um pedido NÃO DEVE executar coisa alguma.
- **FR-037**: A rejeição DEVE gravar a razão.
- **FR-038**: Um pedido expirado NÃO DEVE ser executado.
- **FR-039**: A aprovação DEVE valer para uma ação e não generalizar para uma
  seguinte.
- **FR-040**: A decisão DEVE ser auditada, aprovada ou rejeitada.

### Seleção de ferramentas

- **FR-041**: A seleção de ferramentas DEVE filtrar por nível de efeito
  colateral.
- **FR-042**: Uma capacidade acima de leitura sensível NÃO DEVE ser oferecida a
  um deployment sem portão composto.
- **FR-043**: Uma capacidade acima de leitura sensível NÃO DEVE ser oferecida
  quando este deployment não tem os componentes registrados para executá-la.
- **FR-044**: A seleção de ferramentas DEVE filtrar pelas integrações que o time
  tem configuradas.
- **FR-045**: Uma capacidade que exige uma integração não conectada NÃO DEVE ser
  oferecida.
- **FR-046**: Uma capacidade excluída DEVE constar como excluída com a razão.
- **FR-047**: O corte pelo teto de esquemas DEVE acontecer depois dos dois
  filtros, e não antes.
- **FR-048**: Um time sem nenhuma integração conectada DEVE receber a resposta
  que nomeia o que conectar.
- **FR-049**: Essa resposta DEVE dizer quantas capacidades cada integração
  sugerida destravaria.
- **FR-050**: Essa resposta DEVE nomear exemplos das capacidades bloqueadas.
- **FR-051**: Essa resposta DEVE sugerir primeiro a integração correspondente à
  fonte do alerta.
- **FR-052**: Essa resposta DEVE ser produzida por uma única implementação, e
  não por duas que possam divergir.

### Caminho duplicado

- **FR-053**: Exatamente um caminho de orquestração de investigação DEVE estar
  no caminho de serving.
- **FR-054**: O caminho de orquestração que não serve produção DEVE declarar de
  si mesmo que não está composto.
- **FR-055**: Essa declaração DEVE nomear o que constrói aquele caminho.
- **FR-056**: O resolvedor de catálogo por time DEVE ser instanciado no caminho
  de serving, ou deixar de existir.

### Interações

- **FR-057**: A listagem de interações pendentes de um run DEVE devolver as
  perguntas que aquele run levantou.
- **FR-058**: A listagem NÃO DEVE devolver vazio incondicionalmente.
- **FR-059**: Responder uma interação pendente DEVE fechá-la.
- **FR-060**: A resposta DEVE chegar ao run que estava esperando.
- **FR-061**: A primeira resposta DEVE vencer, e a segunda DEVE ser informada de
  quem respondeu antes.
- **FR-062**: Uma interação de identificador desconhecido DEVE ser distinguida de
  uma já respondida.
- **FR-063**: Uma pergunta que pede credencial DEVE ser recusada antes de
  aparecer para qualquer pessoa.
- **FR-064**: Uma pergunta não respondida dentro da janela DEVE ser fechada como
  não respondida.
- **FR-065**: A pergunta de um run NÃO DEVE poder ser fechada pela resposta de
  outro run.

### Registro

- **FR-066**: O resultado de uma remediação executada DEVE ser gravado no
  registro de resultados.
- **FR-067**: O registro DEVE dizer se a execução foi autônoma ou aprovada.
- **FR-068**: A obrigação de verificar se aquilo funcionou DEVE ser gravada
  quando a execução mudou alguma coisa.
- **FR-069**: A decisão do portão de autonomia DEVE ser auditada, tenha ela
  executado ou não.

### Sem regressão

- **FR-070**: Os cenários sintéticos DEVEM continuar passando.
- **FR-071**: O efeito desta feature sobre a suíte sintética DEVE ser medido e
  reportado, e "sem efeito" é resposta aceitável enquanto "não medido" não é.
- **FR-072**: A verificação completa do repositório DEVE ficar verde ao final,
  tendo partido de verde.

### Fronteiras desta feature

- **FR-073**: Nenhum arquivo de escrita única do console DEVE ser editado por
  esta feature.
- **FR-074**: Nenhuma tela DEVE ser alterada por esta feature.
- **FR-075**: Nenhum acceptance que rode contra o ambiente compartilhado DEVE
  aprovar uma ação ou executar uma escrita.

### Key Entities

- **Ação proposta**: uma escrita que o agente pediu para fazer, com o recurso, o
  nível de efeito colateral, a classe de risco, o raio de alcance e o plano de
  reversão. É o que um portão decide sobre e o que uma pessoa aprova.
- **Plano de reversão**: como a ação seria desfeita, derivado do estado lido
  antes dela e gravado antes de ela acontecer. Um plano produzido depois da
  falha é um plano escrito sob pressão com informação incompleta.
- **Decisão de autonomia**: o que aconteceu com uma ação e o porquê inteiro —
  executar, simular, pedir aprovação, propor ou recusar — com a regra que
  resolveu e o limite que barrou.
- **Contexto de run**: quem age, por qual time, em qual investigação e em qual
  ambiente. Vinculado quando o portão é registrado, e não reconstruído por
  chamada.
- **Interação pendente**: uma pergunta que um run levantou e ainda espera
  resposta, com as opções quando o conjunto é fechado. Vive junto da sessão que
  a espera.
- **Registro de resultado**: o que uma execução fez, se divergiu do que
  pretendia, quem autorizou e qual plano de reversão vale para ela.
- **Deployment que pode remediar**: um que tem o portão composto, componentes
  registrados para a capacidade, e um plano de controle ligado. Menos que isso
  é um deployment que propõe e não age.

## Success Criteria *(mandatory)*

- **SC-001**: Uma varredura pela árvore por construção dos dois portões devolve
  pelo menos uma ocorrência que não é teste, contract test nem plano de dados de
  mentira, e essa ocorrência é alcançável a partir da composition root de
  serving.
- **SC-002**: Uma investigação sintética cujo diagnóstico leva a uma capacidade
  de escrita deixa, no armazenamento, um pedido de aprovação e um plano de
  reversão, contados.
- **SC-003**: Em propose-only, a mesma investigação não altera nenhum estado de
  recurso, e a razão registrada nomeia a política.
- **SC-004**: A aprovação de teste executa a ação e deixa um resultado gravado
  com o identificador da aprovação.
- **SC-005**: Toda capacidade de escrita embarcada, invocada diretamente,
  continua recusando com a mesma frase, e o teste que prova isso continua verde.
- **SC-006**: Para um mesmo alerta, a lista de ferramentas oferecida a um time
  sem uma integração não contém nenhuma capacidade daquela integração.
- **SC-007**: Para um mesmo alerta, a lista de ferramentas oferecida por um
  deployment que não pode remediar não contém nenhuma capacidade acima de
  leitura sensível.
- **SC-008**: Um time sem integrações recebe a resposta que nomeia o que
  conectar, e essa resposta é produzida por uma implementação só.
- **SC-009**: Exatamente um caminho de orquestração serve produção, e o outro
  declara de si mesmo que não serve, nomeando o que o constrói.
- **SC-010**: Uma pergunta levantada num run é listada, respondida e fechada, e
  o run recebe a resposta.
- **SC-011**: Dois runs concorrentes levantam perguntas e cada resposta fecha
  apenas a sua.
- **SC-012**: A suíte sintética passa, com a contagem antes e depois comparada.
- **SC-013**: A verificação completa do repositório passa integralmente, e o
  resultado é comparado contra a mesma verificação rodada antes.
- **SC-014**: Em staging, depois de uma investigação real, a lista de aprovações
  do gateway traz a proposta com o plano de reversão, e nenhuma aprovação foi
  concedida automaticamente.

### Contagens no banco de staging que provam a gravação

Rodadas contra o banco do staging depois do ciclo de deploy do slot, com a
investigação real já concluída:

- `select count(*) from approvals where arguments->>'change_type' = 'remediation';`
  — maior que zero.
- `select count(*) from rollback_plans;` — maior que zero, e ao menos um plano
  correspondendo a um pedido de remediação da consulta acima.
- `select count(*) from approvals where arguments->>'change_type' = 'remediation'
  and state <> 'pending';` — **zero**. Nenhuma decisão automática em staging.
- `select count(*) from remediation_outcomes;` — **zero** em staging. A execução
  é exercitada fora do ambiente compartilhado, e um valor diferente de zero aqui
  é um defeito, não um progresso.

## Assumptions

- **Propose-only continua sendo o padrão.** Um deployment que configurou nada
  resolve para propor. Esta feature compõe o portão; ela não muda para onde a
  política sem configuração aponta, e não introduz nenhum interruptor que a
  mude de uma vez.
- **A recusa direta é a rede, não o portão.** Ela permanece porque uma segunda
  entrada — um botão de console, um comando de operador, um run repetido — não
  pode depender de alguém ter lembrado de checar. Compor por cima é o desenho.
- **A demonstração de aprovação real é da feature final da onda.** Aqui a
  aprovação é exercitada num ambiente que este trabalho controla, com plano de
  controle ligado; contra o ambiente compartilhado, o que roda para na proposta.
- **A tela de Decisions já existe e não é escopo.** As duas abas leem as rotas
  que esta feature passa a povoar. Se elas mostrarem a causa de vazio errada, o
  defeito é da feature de verdade-de-estado desta onda.
- **O registro do que a investigação fez é de outra feature.** Esta depende dele
  para que a proposta apareça vinculada a um run legível, e não o implementa.
- **O plano de controle genérico não é entregue aqui.** As sete capacidades
  transversais precisam de uma ligação de plano de controle que este repositório
  hoje só tem para o hipervisor. Onde não há, a seleção de ferramentas não as
  oferece e a recusa nomeia a ausência — que é a resposta correta, e é
  deliberadamente diferente de fabricar uma ligação a partir de configuração
  ambiente.
- **A política de autonomia vive na configuração e é escrita pelas rotas que já
  existem.** Esta feature lê; não acrescenta caminho de escrita de política.

## Dependencies

- Depende da feature de registro do que o agente fez: a proposta precisa
  aparecer vinculada a uma investigação que conta o que fez, e o vínculo é
  gravado lá.
- Depende de a onda ter emendado a constituição com a regra de composição — é
  contra ela que o plano faz a checagem.
- Não depende da feature de leitura do relato, que corre no mesmo slot: esta é
  backend puro e não toca console.
- Bloqueia a feature final da onda, que fecha o laço no staging real com a
  aprovação assistida.

## Out of Scope

- Qualquer alteração de tela, componente ou catálogo de mensagens do console.
- A causa falsa de vazio em Decisions e Knowledge.
- Uma ligação de plano de controle genérica para as capacidades transversais.
- Aprovação inline em superfície de chat.
- Qualquer alargamento de autonomia: nenhuma lista de permissão nova, nenhum
  padrão que passe a agir sozinho, nenhuma dispensa automática de plano de
  reversão.
- A janela de verificação de eficácia — a obrigação é gravada, e quem a fecha é
  o trabalho já existente do laço fechado.
- Migração de dados de qualquer espécie.
- Aprovação real executada contra o ambiente compartilhado.
