# Feature Specification: Primeiro administrador — um deployment novo produz o seu

**Feature Branch**: `feat/v7-050-primeiro-administrador`

**Created**: 2026-08-23

**Status**: Draft

**Input**: Briefing 050 da onda specs_v7, sobre a análise de requisitos que o
`backlog.md` da raiz já fez em dois itens: "A deployment should produce its own
first administrator" (os três mecanismos, os três critérios de julgamento, o
seam credencial↔sign-in) e "A deployment cannot hold two service accounts" (o
`UniqueViolationError` no e-mail vazio).

**Referência visual (DoD)**: nenhuma tela nova. Esta feature toca **duas telas
existentes** — o formulário de sign-in e o `/first-run` — e apenas no estado
"este deployment ainda não tem administrador local". Não há mockup próprio: as
**Alegações normativas** desta spec são o contrato visual, e
`console/tests/e2e/primeiro-administrador.acceptance.spec.ts` as codifica,
confirmado vermelho antes de qualquer mudança de tela. Viewport normativo de
medição: **1920×1080**.

**Propriedade de arquivos**: esta feature **não é dona** dos arquivos de
escrita única do slot S4 (`console/src/i18n/*.ts`, `console/src/shell/routes.ts`,
`console/visual/screens.json`). Toda chave i18n nova é **declarada no relatório
final** com o texto en e pt-BR e referenciada pela chave no código; a 060 é a
dona no slot e o merge aplica.

## O problema, em uma frase

Um deployment novo sobe, serve o formulário de sign-in, e recusa toda
combinação — inclusive a certa, porque não existe uma certa. Entrar pela
primeira vez hoje exige ler código-fonte: descobrir que
`NINJASRE_LOCAL_ACCOUNT_PASSWORD_HASH` existe, achar `hash_local_password`,
rodá-la contra uma passphrase escolhida à mão, pôr o resultado num Secret e
ligar esse Secret em dois Deployments. O staging precisou exatamente disso, e
nenhum desses passos é descobrível a partir da tela que recusa.

E o produto já imprime uma promessa que não cumpre. O bloco que `bring_up`
manda para o terminal no primeiro start diz, literalmente, "Sign in with this
credential" — e o formulário de sign-in não aceita aquela credencial, porque a
troca em `POST /v1/setup/durable-credential` produz um token de API e o
formulário quer um nome e uma passphrase. O operador termina segurando uma
credencial que a tela na frente dele não sabe usar.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Quem subiu o deployment e não leu nada entra (Priority: P1)

Uma pessoa sobe o deployment pelo compose, olha o terminal, executa **um**
comando que o próprio terminal nomeia, escolhe uma passphrase quando é
perguntada, abre o console e entra como administrador. Nada do que ela fez foi
aprendido lendo código-fonte.

**Why this priority**: é a feature. Um produto que só o autor consegue abrir na
primeira vez não é um produto para outros, e a decisão de audiência desta onda
diz que ele é para outros.

**Independent Test**: subir um deployment limpo por compose, ler só o que o
terminal diz, seguir só o que ele manda, e chegar autenticado no console.

**Acceptance Scenarios**:

1. **Given** um deployment limpo, **When** ele sobe, **Then** o terminal
   imprime um bloco que nomeia um comando único e completo para criar o
   primeiro administrador.
2. **Given** esse bloco, **When** o comando nomeado é executado, **Then** ele
   pergunta a passphrase sem ecoá-la, pede confirmação, e confirma a criação
   nomeando o administrador criado.
3. **Given** o administrador recém-criado, **When** o nome e a passphrase são
   entregues ao formulário de sign-in do console, **Then** a sessão é
   estabelecida e a pessoa está autenticada como administrador.
4. **Given** o mesmo deployment, **When** o terminal do primeiro start é
   perdido, **Then** o mesmo comando continua sendo o caminho, e continua
   funcionando, sem reiniciar nada.

---

### User Story 2 - "Tenho uma credencial" e "consigo entrar" são o mesmo fato (Priority: P1)

O operador que preferir o caminho da credencial de bootstrap — a que o boot
emite e escreve no host — troca essa credencial por uma conta que o formulário
de sign-in aceita. Não existe estado intermediário em que ele segura algo que a
tela não sabe usar.

**Why this priority**: é o seam nomeado no backlog. A maquinaria já existe
quase inteira; o que falta é que os dois caminhos terminem no mesmo lugar. Um
produto com duas noções de "credencial" tem uma delas errada em qualquer tela
que só conheça a outra.

**Independent Test**: trocar uma credencial de bootstrap pela conta durável e,
com o que a troca devolveu, entrar pelo formulário de sign-in — sem passar por
nenhum outro passo.

**Acceptance Scenarios**:

1. **Given** um deployment com credencial de bootstrap viva, **When** a troca
   é feita, **Then** ela cria um administrador com passphrase e devolve também
   o token durável, e ambos identificam o mesmo principal.
2. **Given** essa troca concluída, **When** o nome e a passphrase escolhidos
   nela são entregues ao formulário de sign-in, **Then** a sessão é
   estabelecida.
3. **Given** a mesma credencial de bootstrap, **When** a troca é tentada uma
   segunda vez, **Then** ela é recusada, e a recusa não é um erro de servidor.
4. **Given** o bloco impresso no boot, **When** ele é lido, **Then** ele não
   afirma que a credencial serve para o formulário de sign-in a menos que
   sirva.

---

### User Story 3 - A janela fecha de vez (Priority: P1)

Depois que o primeiro administrador existe, o caminho que o criou deixa de
criar administradores para quem não estava autorizado. Réplicas concorrentes
não reabrem a janela, e duas réplicas subindo juntas não produzem dois
primeiros administradores nem dois convites.

**Why this priority**: um caminho de criação do primeiro administrador que
sobrevive à criação é uma porta aberta. E o modo de falha é silencioso: ninguém
percebe que continuou aberta.

**Independent Test**: criar o primeiro administrador, repetir exatamente o
caminho que o criou, e conferir que é recusado; depois disparar N criações
concorrentes contra o mesmo banco e conferir que exatamente uma vence.

**Acceptance Scenarios**:

1. **Given** um deployment que já tem administrador local, **When** o caminho
   de bootstrap é tentado de novo, **Then** ele é recusado com uma frase que
   diz que este deployment já é administrado.
2. **Given** um deployment que já tem administrador local, **When** ele
   reinicia, **Then** nenhuma credencial de bootstrap nova é emitida e nenhum
   convite é impresso.
3. **Given** N tentativas simultâneas de criar o primeiro administrador,
   **When** todas rodam contra o mesmo banco, **Then** exatamente uma cria, as
   outras são recusadas por uma frase de gente, e o banco tem exatamente um
   registro de abertura.
4. **Given** uma recusa de concorrência, **When** ela é lida, **Then** ela não
   contém nome de constraint, nome de índice, nem texto de exceção do driver.

---

### User Story 4 - Deployment com identity provider não ganha segunda porta (Priority: P1)

Um deployment cujo identity provider está ativo não adquire uma entrada local
por instalar este release, nem por alguém rodar o comando, nem por alguém criar
um principal.

**Why this priority**: é a invariante que o código já defende de propósito, e a
razão pela qual "embarcar uma senha padrão" nunca foi a resposta. Qualquer
correção que a quebre troca um problema de usabilidade por um problema de
segurança.

**Independent Test**: ativar o identity provider, tentar cada um dos caminhos
locais, e conferir que nenhum abre.

**Acceptance Scenarios**:

1. **Given** um deployment com identity provider ativo, **When** o comando de
   criação de administrador local é executado, **Then** ele recusa, diz que o
   identity provider é a porta deste deployment, e nomeia o caminho de
   emergência que existe para quem ficou de fora.
2. **Given** um deployment com identity provider ativo, **When** ele sobe,
   **Then** nenhuma credencial de bootstrap é emitida e nenhum convite é
   impresso.
3. **Given** um deployment com identity provider ativo e nenhum administrador
   local, **When** um sign-in local é tentado, **Then** ele é recusado com a
   mesma recusa única de sempre.
4. **Given** um deployment com identity provider ativo, **When** um principal é
   criado pela rota de identidade, **Then** isso não abre entrada local para
   ninguém.

---

### User Story 5 - Um deployment pode ter dois service accounts (Priority: P1)

Criar um segundo principal sem endereço de e-mail funciona. Se dois principals
disputarem o mesmo endereço de verdade, a recusa é uma frase que uma pessoa lê.

**Why this priority**: o defeito bloqueia o próprio caminho que esta feature
constrói — o principal de bootstrap já ocupa o e-mail vazio, e o segundo
service account de qualquer deployment morre num `UniqueViolationError` cru.

**Independent Test**: criar dois principals sem e-mail no mesmo deployment e
conferir que os dois existem; depois criar dois com o mesmo e-mail e conferir a
mensagem.

**Acceptance Scenarios**:

1. **Given** um deployment cujo principal de bootstrap já existe sem e-mail,
   **When** um segundo principal sem e-mail é criado, **Then** ele é criado.
2. **Given** dois principals sem e-mail, **When** a busca por endereço é feita
   com o endereço vazio, **Then** ela não devolve nenhum dos dois como se fosse
   uma conta encontrada.
3. **Given** um principal com o endereço `a@b.c`, **When** um segundo é criado
   com `A@B.C`, **Then** a recusa nomeia o endereço e diz que já existe alguém
   nele, sem citar índice nem constraint.
4. **Given** a mudança de esquema desta feature, **When** ela é revertida,
   **Then** a reversão acontece, ou recusa nomeando exatamente quais principals
   impedem a volta e o que fazer com eles.

---

### User Story 6 - Rotação e o segundo administrador têm resposta (Priority: P2)

Trocar a passphrase de um administrador e criar um segundo administrador são o
mesmo comando, com a mesma forma, e nenhum dos dois exige tocar em variável de
ambiente nem reiniciar nada.

**Why this priority**: sem isso, o produto responde "como entro na primeira
vez" e volta a mandar ler código-fonte na segunda pergunta. É P2 porque não
bloqueia o primeiro dia.

**Independent Test**: criar um segundo administrador e depois rotacionar a
passphrase do primeiro, entrando com a nova e sendo recusado com a antiga.

**Acceptance Scenarios**:

1. **Given** um deployment já administrado, **When** o comando é executado com
   um nome novo, **Then** um segundo administrador é criado.
2. **Given** um administrador existente, **When** o comando é executado com o
   nome dele sem pedir rotação, **Then** ele recusa dizendo que aquele nome já
   existe e como rotacionar.
3. **Given** um administrador existente, **When** o comando é executado com o
   nome dele pedindo rotação, **Then** a passphrase nova passa a valer e a
   antiga passa a ser recusada.
4. **Given** uma rotação concluída, **When** as sessões abertas com a
   passphrase antiga são consideradas, **Then** o que acontece com elas está
   declarado e é o que acontece.

---

### User Story 7 - A tela diz o que fazer (Priority: P2)

Quem chega ao console de um deployment sem administrador local lê, na própria
tela, o mesmo comando que o terminal imprimiu — e não uma recusa que parece um
erro de digitação.

**Why this priority**: o terminal do primeiro start rola, e a segunda pessoa a
chegar nunca o viu. É P2 porque o caminho já funciona sem a tela; a tela é o
que faz o caminho ser encontrado por quem não estava lá.

**Independent Test**: apontar um console para um deployment sem administrador
local e conferir que a tela nomeia o comando; apontar para um deployment
administrado e conferir que não nomeia nada.

**Acceptance Scenarios**:

1. **Given** um deployment sem administrador local e sem identity provider
   ativo, **When** a tela de sign-in é aberta, **Then** ela mostra um aviso que
   nomeia o comando, e o comando aparece como texto copiável.
2. **Given** um deployment já administrado, **When** a tela de sign-in é
   aberta, **Then** nenhum aviso desses aparece.
3. **Given** um deployment com identity provider ativo, **When** a tela de
   sign-in é aberta, **Then** ela não nomeia o comando local.
4. **Given** uma tentativa de sign-in recusada, **When** a recusa é mostrada,
   **Then** ela é exatamente a recusa que já existia — o aviso de "sem
   administrador" não muda, não substitui e não enriquece nenhuma recusa.

### Edge Cases

- **O staging já tem conta local por variável de ambiente.** O deployment de
  staging roda hoje com `NINJASRE_LOCAL_ACCOUNT_PASSWORD_HASH` configurado. Essa
  conta continua entrando, com o mesmo nome e a mesma passphrase, sem migração e
  sem passo manual. Uma feature de primeiro acesso que tranca o operador atual
  para fora falhou.
- **A passphrase embarcada continua recusada.** O deployment que não se declara
  demonstração e carrega a passphrase que este projeto embarca continua se
  recusando a subir. Nenhum caminho novo desta feature aceita essa passphrase.
- **Credencial de bootstrap órfã no host.** Um arquivo de credencial que sobrou
  de antes, num deployment que já tem administrador, não vale nada: a troca é
  recusada porque o deployment já é administrado, mesmo com o arquivo presente.
- **Duas réplicas, dois arquivos de host.** Réplicas compartilham banco e cada
  uma guarda o próprio arquivo. A abertura é um fato do banco, não do arquivo,
  e é ela que decide.
- **Identity provider ativado depois de já haver administrador local.** As
  contas locais existentes não são apagadas por esta feature, e a decisão sobre
  fechá-las está declarada nos requisitos em vez de ficar implícita.
- **Sessão viva de um administrador cuja passphrase foi rotacionada.** O
  destino das sessões já emitidas é declarado, não descoberto.
- **Comando rodado num host sem banco alcançável.** O comando falha dizendo que
  não alcançou o banco, e não dizendo que a passphrase é inválida.
- **Comando rodado sem terminal interativo.** Sem TTY não há como perguntar a
  passphrase sem eco; o comando recusa nomeando a alternativa em vez de ler algo
  do ambiente por conta própria.
- **A segunda superfície de console.** Existe um segundo console em
  `surfaces/console`, com sign-in próprio. Esta feature não decide o estatuto
  dele; declara o que acontece com ele e não o deixa contradizendo o console
  canônico.

## Requirements *(mandatory)*

### A decisão de mecanismo

O backlog analisou três formas. Esta spec decide por um **híbrido de duas**, e
recusa a terceira:

- **Adotado — o comando que o operador roda**, `ninjasre setup admin`, como
  caminho canônico. É o único dos três que não acrescenta porta nenhuma na
  rede: quem pode rodá-lo já tem shell no host, o que já é mais poder do que a
  conta que ele cria. Não há janela para fechar, logo não há janela que possa
  ficar aberta. Responde de graça a rotação e ao segundo administrador.
- **Adotado — a credencial impressa no boot**, que já existe, promovida a
  convite: o bloco impresso passa a nomear o comando, e a troca da credencial
  passa a produzir uma conta com passphrase em vez de só um token. É o que
  torna o comando descobrível por quem não leu nada, e é o que fecha o seam.
- **Recusado — a tela de first-run que cria a primeira conta.** É a forma mais
  descobrível das três e é também a única que instala uma rota não autenticada
  cuja correção depende de fechar direito: sob réplicas concorrentes, sob um
  arquivo de estado que diverge do banco, sob um deployment com identity
  provider. Recusá-la é o que permite dizer, sem asterisco, que **nenhuma rota
  não autenticada desta feature cria administrador**. A tela continua tendo
  papel: ela **nomeia** o mecanismo, e não o executa.

### A porta, redefinida por substância

Hoje a porta do sign-in local é um campo: `LocalAccount.from_environment`
devolver algo. A ausência dele recusa todo mundo, inclusive principals criados
— de propósito, para que criar uma pessoa não transforme um deployment com
identity provider num deployment com segunda entrada. Esta feature **preserva
essa invariante por substância** e generaliza a porta de um campo para um fato:

- **FR-001**: A porta do sign-in local DEVE ser "este deployment tem
  administrador local habilitado", e não "a variável de ambiente está
  configurada".
- **FR-002**: Esse fato DEVE ser verdadeiro quando a conta de ambiente está
  configurada, exatamente como hoje.
- **FR-003**: Esse fato DEVE passar a ser verdadeiro também quando um
  administrador local foi criado deliberadamente por um dos caminhos desta
  feature.
- **FR-004**: Esse fato NÃO DEVE se tornar verdadeiro por instalar um release,
  por subir o deployment, nem por qualquer padrão.
- **FR-005**: Criar um principal pela rota de identidade NÃO DEVE tornar esse
  fato verdadeiro.
- **FR-006**: Com esse fato falso, o sign-in local DEVE recusar toda
  combinação, com a mesma recusa única que já existe hoje.
- **FR-007**: A recusa DEVE continuar sendo uma só, com uma só mensagem, para
  todo modo de estar errado.
- **FR-008**: O registro de auditoria DEVE continuar distinguindo os desfechos
  amplos que hoje distingue, e DEVE registrar o novo desfecho de "não há
  administrador local habilitado" de forma distinguível.
- **FR-009**: A leitura desse fato DEVE ser feita por tentativa de sign-in, e
  não fixada na construção do processo, para que habilitar não exija
  reiniciar.
- **FR-010**: A leitura desse fato NÃO DEVE acrescentar verificação de
  passphrase alguma ao caminho de recusa, para não alterar o custo comparativo
  entre um nome que existe e um que não existe.
- **FR-011**: A conta de ambiente DEVE continuar sendo resolvida na construção
  do processo, de modo que um deployment carregando a passphrase embarcada
  continue falhando ao subir e não no primeiro sign-in.

### O comando

- **FR-012**: DEVE existir um comando do CLI que cria um administrador local.
- **FR-013**: O comando DEVE receber o nome do administrador por opção.
- **FR-014**: O comando DEVE perguntar a passphrase sem ecoá-la.
- **FR-015**: O comando DEVE pedir a passphrase duas vezes e recusar quando as
  duas não coincidirem.
- **FR-016**: O comando NÃO DEVE aceitar a passphrase por argumento de linha de
  comando.
- **FR-017**: O comando NÃO DEVE ler a passphrase de variável de ambiente por
  conta própria.
- **FR-018**: Sem terminal interativo, o comando DEVE recusar nomeando a
  alternativa, em vez de tentar adivinhar de onde ler a passphrase.
- **FR-019**: O comando DEVE armazenar a passphrase pela mesma construção de
  hash que a conta de ambiente já usa, e não por uma segunda inventada aqui.
- **FR-020**: O comando DEVE conceder ao administrador criado a permissão de
  dono.
- **FR-021**: O comando DEVE registrar em auditoria a criação, sem a passphrase
  em nenhuma forma.
- **FR-022**: O comando DEVE habilitar o sign-in local do deployment quando for
  a primeira criação.
- **FR-023**: O comando DEVE funcionar sem que nada seja reiniciado.
- **FR-024**: O comando DEVE recusar quando o nome pedido já existe, dizendo
  como rotacionar.
- **FR-025**: O comando DEVE rotacionar a passphrase de um administrador
  existente quando a rotação for pedida explicitamente.
- **FR-026**: O comando DEVE poder criar um segundo administrador num
  deployment já administrado.
- **FR-027**: O comando DEVE recusar quando o identity provider deste
  deployment está ativo.
- **FR-028**: Essa recusa DEVE nomear o caminho de emergência que existe para
  quem ficou de fora, e NÃO DEVE oferecer um `--force`.
- **FR-029**: O comando DEVE distinguir "o banco não foi alcançado" de "a
  passphrase não serve", em mensagens diferentes.
- **FR-030**: A saída do comando NÃO DEVE conter a passphrase, nem o hash dela.

### O convite impresso no boot

- **FR-031**: O bloco impresso no primeiro start DEVE nomear o comando completo
  que cria o primeiro administrador, na forma em que o deployment corrente é
  operado.
- **FR-032**: O bloco NÃO DEVE afirmar que a credencial de bootstrap serve para
  o formulário de sign-in.
- **FR-033**: O bloco DEVE continuar sendo impresso e não logado, e a
  credencial DEVE continuar não aparecendo em log nem em auditoria.
- **FR-034**: Nenhuma credencial de bootstrap DEVE ser emitida quando o
  deployment já tem administrador local habilitado.
- **FR-035**: Nenhum convite DEVE ser impresso quando o deployment já tem
  administrador local habilitado.
- **FR-036**: Nenhuma credencial de bootstrap DEVE ser emitida quando o
  identity provider deste deployment está ativo.
- **FR-037**: A idempotência que o boot já tem — nenhuma organização a mais,
  nenhum grant a mais, nenhuma credencial a mais — DEVE ser preservada.

### O seam: a troca produz uma conta, não só um token

- **FR-038**: A troca da credencial de bootstrap DEVE criar um administrador
  local com passphrase, além de devolver o token durável.
- **FR-039**: A passphrase DEVE ser escolhida por quem faz a troca, e a troca
  DEVE recusar sem ela.
- **FR-040**: O administrador criado pela troca e o dono do token durável
  DEVEM ser o mesmo principal.
- **FR-041**: A troca DEVE habilitar o sign-in local do deployment.
- **FR-042**: Depois da troca, o nome e a passphrase escolhidos DEVEM ser
  aceitos pelo formulário de sign-in do console.
- **FR-043**: A troca DEVE continuar gastando a credencial de bootstrap, e uma
  segunda troca com a mesma credencial DEVE continuar sendo recusada.
- **FR-044**: A troca DEVE ser recusada quando o deployment já tem
  administrador local habilitado, mesmo que um arquivo de credencial ainda
  exista no host.
- **FR-045**: A troca DEVE ser recusada quando o identity provider deste
  deployment está ativo.
- **FR-046**: A ordem que já existe — revogar a credencial antiga só depois de
  a substituta existir — DEVE ser preservada.
- **FR-047**: A permissão que a rota de troca exige NÃO DEVE ser alargada por
  esta mudança.

### Concorrência

- **FR-048**: A abertura do sign-in local DEVE ser um registro único por
  deployment, e a unicidade DEVE ser garantida pelo armazenamento.
- **FR-049**: Duas criações concorrentes do primeiro administrador DEVEM
  resultar em exatamente uma abertura registrada.
- **FR-050**: O perdedor de uma corrida DEVE receber uma recusa escrita para
  gente, e não uma exceção do driver de banco.
- **FR-051**: O caminho de criação DEVE usar o mesmo tipo de exclusão que o
  boot já usa para as migrações, em vez de inventar um segundo mecanismo de
  coordenação.
- **FR-052**: Duas réplicas subindo juntas NÃO DEVEM produzir dois convites
  impressos para o mesmo deployment quando um deles já tiver aberto a porta.
- **FR-053**: O registro de abertura DEVE guardar quando aconteceu e por qual
  dos caminhos.

### O e-mail vazio e o segundo service account

- **FR-054**: Um deployment DEVE poder ter mais de um principal sem endereço de
  e-mail.
- **FR-055**: A unicidade de endereço DEVE deixar de se aplicar a principals
  sem endereço.
- **FR-056**: A unicidade de endereço DEVE continuar valendo, sem folga, para
  principals que têm endereço.
- **FR-057**: A comparação de endereço DEVE continuar sendo insensível a caixa,
  pela mesma dobra que hoje é usada dos dois lados.
- **FR-058**: A busca por endereço com um endereço vazio NÃO DEVE devolver um
  principal sem endereço como se fosse uma conta encontrada.
- **FR-059**: A mudança de esquema DEVE vir como migração reversível.
- **FR-060**: A reversão DEVE acontecer quando os dados permitirem.
- **FR-061**: Quando os dados não permitirem, a reversão DEVE recusar nomeando
  quais principals impedem a volta e o que fazer com eles.
- **FR-062**: Uma colisão real de endereço DEVE produzir uma mensagem que nomeia
  o endereço.
- **FR-063**: Essa mensagem NÃO DEVE conter nome de índice, nome de constraint,
  nem texto de exceção do driver.
- **FR-064**: A porta de persistência DEVE dizer, em si mesma, que a ausência de
  endereço é um valor legítimo e não é único.
- **FR-065**: O comportamento DEVE ser o mesmo nos dois backends de
  persistência, provado pela suíte de contrato que já roda contra os dois.

### O identity provider

- **FR-066**: A condição "este deployment tem identity provider" DEVE ser lida
  de uma fonte só, a mesma que o console já lê.
- **FR-067**: Com identity provider ativo, nenhum dos caminhos locais desta
  feature DEVE abrir.
- **FR-068**: Com identity provider ativo, a tela de sign-in NÃO DEVE nomear o
  comando local.
- **FR-069**: Ativar o identity provider num deployment que já tem
  administradores locais NÃO DEVE apagá-los.
- **FR-070**: O que acontece com o sign-in local depois de o identity provider
  ser ativado DEVE estar declarado no produto, e não deixado para o leitor
  inferir.

### O console

- **FR-071**: A tela de sign-in DEVE mostrar, no estado "sem administrador
  local", um aviso que nomeia o comando.
- **FR-072**: O comando DEVE aparecer como texto que se copia.
- **FR-073**: Esse aviso NÃO DEVE aparecer num deployment já administrado.
- **FR-074**: Esse aviso NÃO DEVE aparecer num deployment com identity provider
  ativo.
- **FR-075**: A recusa de uma tentativa de sign-in NÃO DEVE mudar por causa
  desta feature — nem o texto, nem o código, nem o que ela distingue.
- **FR-076**: O fato que a tela lê NÃO DEVE revelar nome do deployment, versão,
  organização, nem contagem de nada.
- **FR-077**: A tela de first-run DEVE dizer a mesma coisa que a tela de
  sign-in diz, no mesmo estado, sem uma segunda redação.
- **FR-078**: Todo texto novo de tela DEVE vir do catálogo de mensagens, com a
  chave declarada no relatório final desta feature em vez de escrita nos
  arquivos de escrita única do slot.
- **FR-079**: O nome do comando NÃO DEVE ser traduzido.

### Composição e prova no caminho de serving

- **FR-080**: O mecanismo novo DEVE ser construído a partir da composition root
  de serving, e não apenas em teste.
- **FR-081**: O comando novo DEVE estar registrado no CLI que a imagem
  distribui.
- **FR-082**: A prova de que o caminho existe DEVE vir de um deployment
  levantado por compose, e não de teste com store em memória.
- **FR-083**: O contrato HTTP publicado DEVE refletir a mudança da rota de
  troca.

## Alegações normativas

Frases curtas, individualmente testáveis, que
`console/tests/e2e/primeiro-administrador.acceptance.spec.ts` codifica,
confirmado vermelho antes de qualquer mudança de tela. Medidas a 1920×1080.

1. Num deployment sem administrador local e sem identity provider, a tela de
   sign-in mostra um bloco de aviso identificável.
2. Esse bloco contém o comando, literal, numa região que se seleciona e copia.
3. Esse bloco aparece **acima** do formulário, não dentro dele.
4. O formulário continua tendo exatamente dois campos e um botão.
5. Num deployment já administrado, o bloco não existe no documento — não está
   apenas oculto.
6. Num deployment com identity provider ativo, o bloco não existe no documento.
7. Uma tentativa recusada mostra a mesma frase de recusa de hoje, e o bloco de
   aviso não é alterado por ela.
8. A tela de sign-in continua não nomeando o deployment em lugar nenhum.
9. A tela de first-run, no mesmo estado, mostra o mesmo comando, com a mesma
   redação vinda da mesma chave.
10. Nenhuma das duas telas imprime chave de i18n crua.

**Staging-safe**: as alegações 5, 6, 7, 8 e 10 são de leitura e rodam contra o
staging. As alegações 1, 2, 3, 4 e 9 exigem um deployment sem administrador —
o staging tem um — e rodam contra o backing de compose, não contra o staging.

## Key Entities

- **Administrador local**: um principal deste deployment com passphrase
  armazenada, criado deliberadamente por um dos caminhos desta feature ou
  configurado por ambiente. É o que o formulário de sign-in aceita.
- **Abertura do sign-in local**: o registro, um por deployment, de que a porta
  local foi aberta — quando, e por qual caminho. É o árbitro da corrida e é o
  que fecha a janela.
- **Credencial de bootstrap**: o que o boot emite, imprime e escreve no host,
  com vida curta e duas permissões. Gasta na troca.
- **Conta durável**: o que a troca produz. Depois desta feature, é um par
  nome-e-passphrase *e* um token, do mesmo principal.
- **Principal sem endereço**: um service account que não tem e-mail. Legítimo,
  possível em qualquer número, e fora da regra de unicidade de endereço.

## Success Criteria *(mandatory)*

- **SC-001**: Num deployment limpo levantado por compose, uma pessoa que leia
  apenas o terminal chega autenticada no console executando um comando e
  respondendo a um prompt.
- **SC-002**: Do primeiro start até a sessão estabelecida, nenhum passo exigiu
  abrir um arquivo de código-fonte, e a evidência é a transcrição da sessão de
  terminal.
- **SC-003**: Repetir, depois de criado o administrador, exatamente o caminho
  que o criou termina em recusa, e a recusa é uma frase de gente.
- **SC-004**: N criações concorrentes do primeiro administrador contra o mesmo
  banco produzem exatamente uma abertura registrada e N-1 recusas legíveis.
- **SC-005**: Num deployment com identity provider ativo, os três caminhos
  locais recusam, e a tela não nomeia nenhum deles.
- **SC-006**: Um segundo service account sem e-mail é criado com sucesso num
  deployment cujo principal de bootstrap já existe.
- **SC-007**: Uma colisão real de endereço produz uma mensagem que nomeia o
  endereço e não nomeia `ix_users_email`.
- **SC-008**: A migração desta feature sobe e desce contra um banco com dados,
  e a descida ou acontece ou recusa nomeando os principals que a impedem.
- **SC-009**: A conta local que o staging já usa continua entrando, com o mesmo
  nome e a mesma passphrase, depois do deploy.
- **SC-010**: O bloco impresso no boot não contém nenhuma afirmação falsa sobre
  onde a credencial serve.
- **SC-011**: A composition root de serving constrói o mecanismo novo, e o
  caminho é exercitado num deployment de compose — não só no harness.
- **SC-012**: `make verify` termina verde, tendo partido de verde.

## Assumptions

- **Quem pode rodar o comando já é dono do host.** O caminho canônico é um
  comando executado dentro do deployment. Quem consegue executá-lo já pode ler o
  banco e as variáveis de ambiente, então a conta que ele cria não concede nada
  que quem o rodou já não tivesse. Essa é a razão de ele não precisar de
  autenticação própria.
- **A pessoa que sobe o deployment vê o terminal.** É verdade para compose e
  para o primeiro `kubectl logs`. Para quem não vê, o comando continua sendo o
  caminho e a tela continua nomeando-o — o terminal é a rota mais curta, não a
  única.
- **O caminho de emergência existe e não é este.** Há um mecanismo de
  break-glass no produto, com prazo, motivo escrito e log em nível de erro, para
  quem ficou de fora de um identity provider quebrado. Esta feature aponta para
  ele e não o duplica.
- **O identity provider tem um estado "ativo" já modelado.** A configuração de
  single sign-on deste deployment já carrega esse estado e o console já o lê.
  Esta feature lê o mesmo, e não introduz uma segunda noção.
- **Esta feature não faz limpeza de dados.** Nenhuma conta local existente é
  apagada, nem quando um identity provider é ativado.
- **A segunda superfície de console não é decidida aqui.** O estatuto do
  console em `surfaces/console` é uma questão de governança levantada na
  auditoria de regras desta onda. Esta feature não o promove nem o remove; só
  garante que ele não afirme o contrário do console canônico.

## Dependencies

- Nenhuma feature desta onda bloqueia esta. Ela roda no slot S4, em par com a
  060, em áreas de console distintas.
- Depende da constituição como ela fica depois da 000 — a cláusula de
  composição é o que obriga a prova no caminho de serving.
- A suíte de contrato de persistência que roda contra os dois backends já
  existe e é onde a mudança de e-mail é provada.

## Out of Scope

- Qualquer tela nova. O aviso é um bloco em duas telas que já existem.
- Uma rota não autenticada que crie administrador. Recusada por decisão, com
  rationale registrada acima.
- Fluxo de recuperação de passphrase por e-mail, ou qualquer envio de mensagem.
- Convite de usuário, auto-registro, ou qualquer forma de criar conta a partir
  do navegador sem credencial.
- Política de complexidade de passphrase, expiração, ou histórico.
- Mudança na semântica do break-glass.
- Mudança na configuração de single sign-on: esta feature lê o estado dela e
  não o escreve.
- O estatuto da segunda superfície de console.
- Limpeza dos registros de credencial de bootstrap acumulados em deployments
  antigos.
