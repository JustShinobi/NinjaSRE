# Feature Specification: Confiança de certificado — o hipervisor comum conecta, ou a recusa nomeia o certificado

**Feature Branch**: `feat/v7-070-confianca-de-certificado`

**Created**: 2026-08-23

**Status**: Draft

**Input**: Briefing 070 da onda specs_v7, e o item do `backlog.md` da raiz "A
vendor with a self-signed certificate cannot be connected" — que já é a análise
desta feature: o mecanismo existe, não é ligado por nada, não é um campo de
schema a mais porque o handshake TLS acontece no egress do proxy de credencial,
e por isso é uma **mudança de fronteira de segurança** que merece ser desenhada
como tal.

**Referência visual (DoD)**: nenhuma tela nova. Esta feature é de backend. O
console é tocado num ponto só — o painel da integração ganha os campos
declarados de confiança e passa a imprimir a frase certa quando a recusa é de
certificado. Não há mockup e não há `console/tests/e2e/<slug>.acceptance.spec.ts`
próprio: a alegação verificável desta feature é de servidor, e é onde o
acceptance mora. A transversal do console continua rodando na fronteira do slot.

**Par de slot**: S3, em paralelo com a 030. Esta feature **não é dona** dos
arquivos de escrita única. Toda chave de i18n e todo texto de UI que ela
precisar é declarado como bloco no relatório final; o merge do slot aplica.

---

## Por que isto existe

Um Proxmox comum — certificado self-signed, que é o **padrão de instalação**,
não uma excentricidade — é apontado, tem seu token de API guardado, o catálogo
reporta a integração configurada, e toda chamada falha com *"Neither the
credential proxy nor any configured Proxmox node answered"*. A rede está boa. O
token está bom. O que houve é que o proxy não aceitou o certificado, e a frase
manda o operador conferir uma rede que não tem nada de errado.

Um andar acima, `integrations/proxmox/certificates.py` já sabe dizer as três
coisas que um deployment pode declarar sobre esse certificado — fingerprint
pinado, certificado fornecido, e um `unverified` que exige razão e nome de quem
aceitou. A documentação do pacote ensina as três. **Nada as carrega**: nenhum
campo de configuração, nenhum caminho de escrita, e o cliente recebe o valor
padrão porque nunca ninguém passou outro.

E o cliente não é onde isso se resolve. O cliente não abre conexão nenhuma: toda
chamada a vendor atravessa o proxy de credencial, e o handshake TLS acontece no
egress dele. Uma decisão de confiança expressa no cliente não alcança nada. O
que carregar essa decisão precisa chegar em `platform/credentials/proxy` e no
remetente que o serve — que é o único lugar do repositório onde um
enfraquecimento deliberado de verificação de certificado pode existir.

É isso que faz desta uma feature de fronteira. As perguntas que ela responde não
são "que campo acrescentar": são **quem pode aceitar**, **para que endereço
vale**, **o que fica registrado**, e **o que acontece quando o certificado muda**.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - O Proxmox self-signed conecta (Priority: P1)

Um operador tem um Proxmox de instalação padrão. Ele copia da interface do
próprio Proxmox ou o fingerprint SHA-256 do nó, ou o certificado da autoridade
que o cluster mintou para si, cola no painel da integração, e a integração passa
a Verified. O estate começa a povoar com os nós, guests e datastores do cluster.

**Why this priority**: é o defeito. Sem isto, o produto não conecta o hipervisor
que o operador tem, e a cadeia inteira que depende dele — estate vazio, todo
alerta caindo em "Alerts for things not here", incidente sem sujeito resolvível,
zone "Unplaced" — continua cortada no primeiro elo.

**Independent Test**: declarar o fingerprint do nó real, pedir uma leitura
autenticada através do proxy, e conferir que a resposta é do Proxmox.

**Acceptance Scenarios**:

1. **Given** uma integração apontada para um endereço cujo certificado o
   repositório do sistema não conhece, **When** nenhuma confiança foi declarada,
   **Then** a chamada é recusada por certificado — não por rede.
2. **Given** o fingerprint SHA-256 correto do nó declarado, **When** a mesma
   chamada é feita, **Then** ela chega ao Proxmox e volta com a resposta dele.
3. **Given** o PEM da autoridade do cluster declarado em vez do fingerprint,
   **When** a mesma chamada é feita, **Then** ela chega ao Proxmox e volta com a
   resposta dele.
4. **Given** a confiança declarada e a integração verificada, **When** a
   descoberta do estate roda, **Then** recursos de origem Proxmox aparecem no
   estate.

---

### User Story 2 - A recusa nomeia o certificado (Priority: P1)

Quando o produto não confia no que o endereço apresentou, ele diz **qual**
certificado apresentou — o fingerprint observado — e o que fazer com essa
informação. Quando o endereço de fato não responde, ele diz o que diz hoje. As
duas frases nunca se trocam de lugar.

**Why this priority**: a mensagem errada é metade do custo do defeito. Um
operador mandado conferir a rede confere a rede, encontra a rede boa, e conclui
que o produto está quebrado. A frase certa resolve o problema em um minuto sem
ninguém abrir código.

**Independent Test**: provocar as duas falhas separadamente contra o mesmo
endereço e comparar as duas mensagens.

**Acceptance Scenarios**:

1. **Given** um endereço que responde com um certificado não confiado, **When**
   a chamada é feita, **Then** a recusa nomeia o fingerprint observado e o
   caminho para confiar nele, e **não** contém a frase de "nenhum nó respondeu".
2. **Given** um endereço que não responde, **When** a chamada é feita, **Then** a
   mensagem é a de hoje, e **não** menciona certificado.
3. **Given** um PEM declarado que valida a cadeia mas cujo certificado não nomeia
   o endereço configurado, **When** a chamada é feita, **Then** a recusa diz
   exatamente isso — certificado confiado, nome não confere — e nomeia os dois.
4. **Given** qualquer uma das três recusas, **When** o painel da integração é
   lido, **Then** ele mostra a frase da recusa que de fato aconteceu.

---

### User Story 3 - Pin quebrado é recusa, nunca acomodação (Priority: P1)

O certificado do nó muda — reinstalação, renovação, ou alguém no meio do
caminho. O produto recusa, nomeia o fingerprint novo ao lado do declarado, e
para. Não volta para o repositório do sistema, não passa a não verificar, e não
adota o fingerprint novo sozinho. Voltar a conectar é uma decisão de gente, com
a mesma permissão e o mesmo registro que a primeira.

**Why this priority**: é a propriedade que faz o pin valer alguma coisa. Um pin
que se atualiza sozinho quando não bate é um campo decorativo, e a substituição
de certificado é exatamente o evento que ele existe para pegar.

**Independent Test**: declarar um fingerprint, apresentar outro, ler a mensagem
e conferir que nenhuma chamada seguinte passa.

**Acceptance Scenarios**:

1. **Given** um fingerprint declarado que não corresponde ao apresentado,
   **When** a chamada é feita, **Then** ela é recusada e a mensagem contém os
   dois fingerprints, identificados como esperado e observado.
2. **Given** a mesma situação, **When** a chamada é repetida, **Then** ela é
   recusada de novo — não há degradação para o repositório do sistema nem para
   não verificado.
3. **Given** a mesma situação, **When** a configuração é lida depois,
   **Then** o fingerprint declarado é o que o operador declarou, inalterado.
4. **Given** um cluster de vários nós com um fingerprint declarado por nó,
   **When** um dos nós troca de certificado, **Then** só as chamadas àquele nó
   são recusadas, e o failover para os outros continua funcionando.

---

### User Story 4 - Não verificar é uma decisão registrada, não um checkbox (Priority: P1)

Existe um caminho para o deployment que não consegue nem pinar nem fornecer
certificado. Ele não é uma caixinha "skip TLS verify": exige uma permissão que
não é a de configurar integração, exige uma razão escrita, registra quem
decidiu, quando, e para qual endereço, e vale só para aquele endereço.

**Why this priority**: a opção insegura é também a conveniente, e essa é a
dificuldade inteira. O mecanismo que já existe em código força razão e
identidade; o caminho de configuração tem de preservar isso, senão a feature
troca um mecanismo cuidadoso por um atalho.

**Independent Test**: tentar aceitar não verificado sem razão, sem permissão, e
com as duas — e conferir os três resultados.

**Acceptance Scenarios**:

1. **Given** um principal sem a permissão dedicada, **When** ele tenta aceitar
   um certificado não verificado, **Then** a escrita é recusada nomeando a
   permissão que falta, e nada é gravado.
2. **Given** um principal com a permissão, **When** ele tenta aceitar sem
   escrever razão, **Then** a escrita é recusada nomeando o que falta.
3. **Given** um principal com a permissão e uma razão escrita, **When** ele
   aceita, **Then** a aceitação é gravada com a identidade autenticada dele —
   não com um nome que o cliente mandou no corpo — e o instante do servidor.
4. **Given** uma aceitação gravada, **When** a auditoria é consultada, **Then**
   existe um evento nomeando quem, quando, qual integração, qual endereço, qual
   âncora e qual razão.
5. **Given** uma aceitação gravada para um endereço, **When** o endereço da
   integração é trocado por outro, **Then** a aceitação deixa de valer e a
   chamada ao endereço novo é recusada por certificado até nova decisão.

---

### User Story 5 - O enfraquecimento mora num lugar só (Priority: P1)

Verificação de certificado só pode ser afrouxada no egress do proxy de
credencial. Nenhum cliente de integração, nenhuma capacidade, nenhuma rota do
gateway e nenhum sandbox ganha a capacidade de fazer isso, e nenhum deles ganha
sequer como ler a declaração.

**Why this priority**: é a razão de a feature ser desenhada e não improvisada.
Um segundo lugar capaz de não verificar é um lugar a menos que uma revisão de
segurança consegue auditar, e o vazamento típico é justamente o conveniente —
uma flag no cliente "para testar".

**Independent Test**: varrer a árvore por qualquer construção de contexto TLS
que não verifique fora do remetente do proxy, e por qualquer campo booleano de
"pular verificação" em qualquer schema.

**Acceptance Scenarios**:

1. **Given** a árvore ao fim da feature, **When** ela é varrida por construções
   de contexto TLS sem verificação, **Then** existe exatamente uma, no remetente
   do proxy, alcançável só pela declaração registrada.
2. **Given** qualquer schema de credencial, de configuração ou de capacidade,
   **When** ele é lido, **Then** não existe campo booleano que desligue
   verificação.
3. **Given** o catálogo de capacidades, **When** ele é enumerado, **Then**
   nenhuma capacidade lê nem escreve declaração de confiança.
4. **Given** a política de rede dos sandboxes, **When** ela é comparada com a de
   antes da feature, **Then** ela é idêntica — sandbox não fala com o proxy e
   isso não muda.

---

### Edge Cases

- **O cluster tem três nós e um certificado por nó.** A declaração de
  fingerprint é um conjunto, não um valor. Um PEM de autoridade do cluster cobre
  os três de uma vez, e é por isso que ele é a forma recomendada para cluster.
- **O operador aponta para um endereço IP e fornece o PEM.** A cadeia valida e o
  nome não confere, porque o certificado nomeia o nó e não o endereço. É a
  terceira mensagem, e ela precisa dizer isso em vez de virar "certificado não
  confiado". O fingerprint pinado não tem esse problema, porque o pin substitui
  a verificação de identidade em vez de acrescentar a ela.
- **O operador cola uma chave privada no campo do certificado.** Recusado
  nomeando a recusa, e o valor não é gravado em lugar nenhum — nem no documento,
  nem no log, nem no evento de auditoria.
- **A autoridade que o appliance mintou para si não carrega a extensão de uso
  de chave que a norma pede.** É o caso comum de hipervisor e já é tratado hoje
  no remetente quando existe um bundle nomeado; a declaração vinda da
  configuração recebe o mesmo tratamento, e apenas ele — cadeia, validade e nome
  continuam sendo verificados.
- **A declaração é removida.** A chamada seguinte volta a ser verificada contra o
  repositório do sistema, no mesmo ciclo em que o endereço removido deixa de ser
  alcançável. Uma permissão que sobrevive à decisão que a concedeu é a falha que
  a reconstrução periódica da allow-list já existe para evitar.
- **A configuração não pode ser lida no momento do ciclo.** O proxy mantém o que
  já tem e registra a falha, exatamente como faz hoje com a allow-list. Recusar
  todas as chamadas porque uma leitura falhou transforma um soluço de banco em
  queda de todas as integrações.
- **Uma integração declara confiança e não está instalada neste build.** A
  declaração é ignorada e registrada, pela mesma razão que uma allow-list não é
  aberta para integração que ninguém declarou.
- **Dois nós com o mesmo fingerprint.** Legítimo (certificado wildcard ou
  compartilhado) e não é caso especial: a comparação é de pertencimento a um
  conjunto.

## Requirements *(mandatory)*

### A declaração

- **FR-001** A configuração de uma integração ativa carrega uma declaração de
  confiança de certificado com exatamente quatro formas: repositório do sistema,
  fingerprint pinado, certificado fornecido, e não verificado.
- **FR-002** A forma padrão é o repositório do sistema, e um deployment que não
  declarou nada permanece nela sem configurar coisa alguma.
- **FR-003** A forma "não verificado" só existe acompanhada de razão e da
  identidade de quem aceitou, ambas não vazias.
- **FR-004** A validação do documento recusa uma declaração "não verificado" sem
  razão ou sem identidade, nomeando o que falta.
- **FR-005** Não existe, em nenhum ponto do caminho — schema de credencial,
  documento de configuração, corpo de requisição, variável de ambiente ou
  argumento de construtor — campo booleano que desligue verificação.
- **FR-006** O campo de fingerprint aceita as duas grafias que as ferramentas
  produzem: pares hexadecimais separados por dois-pontos, e a mesma sequência sem
  separadores.
- **FR-007** O campo de fingerprint é um conjunto: um cluster declara um
  fingerprint por nó numa única declaração.
- **FR-008** O campo de certificado recusa qualquer valor que não comece pelo
  cabeçalho de certificado, e recusa nominalmente um valor que carregue
  cabeçalho de chave privada.
- **FR-009** A declaração registra os endereços para os quais foi feita.

### Quem pode

- **FR-010** Declarar fingerprint pinado ou certificado fornecido exige a
  permissão que já governa configurar uma integração.
- **FR-011** Aceitar um certificado não verificado exige uma permissão dedicada,
  distinta daquela, e não concedida ao papel que apenas opera integrações.
- **FR-012** A identidade gravada como quem aceitou é a identidade autenticada de
  quem faz a escrita, carimbada pelo servidor; um valor de identidade vindo do
  cliente é ignorado.
- **FR-013** O instante da aceitação é carimbado pelo servidor.
- **FR-014** A recusa por falta da permissão dedicada nomeia a permissão e não
  grava nada — nem parcialmente.
- **FR-015** Nenhuma capacidade do agente lê, escreve ou influencia uma
  declaração de confiança.

### Para onde vale

- **FR-016** A confiança vale por endereço, não por vendor: uma declaração
  autoriza os endereços que ela nomeia e nenhum outro.
- **FR-017** Trocar o endereço de uma integração invalida a declaração feita para
  o endereço anterior; a chamada ao endereço novo é recusada por certificado até
  que uma declaração o alcance.
- **FR-018** Acrescentar um endereço a uma integração não estende a ele uma
  aceitação "não verificado" existente.
- **FR-019** Um certificado fornecido cobre os endereços cuja cadeia ele valida,
  que é como um PEM de autoridade cobre um cluster inteiro — e é uma
  consequência de o operador ter fornecido aquela autoridade, não uma extensão
  implícita.

### Onde é aplicada

- **FR-020** O handshake TLS de uma chamada encaminhada usa a declaração da
  integração e do endereço daquela chamada.
- **FR-021** Sob fingerprint pinado, a conexão é aceita se e somente se o SHA-256
  do certificado apresentado pertencer ao conjunto declarado.
- **FR-022** Sob certificado fornecido, o certificado declarado é a âncora de
  confiança, e a verificação de cadeia, de validade e de nome do endereço
  permanecem ligadas.
- **FR-023** Sob não verificado, cadeia e nome não são verificados, e apenas para
  os endereços que a declaração nomeia.
- **FR-024** A declaração chega ao processo do proxy sem reinício, pelo mesmo
  ciclo que já reconstrói a allow-list a partir da configuração.
- **FR-025** Esse ciclo reconstrói em vez de acumular: uma declaração removida
  deixa de valer no ciclo seguinte.
- **FR-026** Uma declaração que nomeia uma integração que este build não tem é
  ignorada e registrada.
- **FR-027** O afrouxamento da conformidade que hoje acompanha um bundle nomeado
  acompanha também um certificado fornecido pela configuração, e nada além dele.
- **FR-028** Existe exatamente um lugar na árvore capaz de construir um contexto
  TLS que não verifica, e é o remetente do proxy.

### O que a recusa diz

- **FR-029** Certificado não confiado é uma razão de erro própria, distinta de
  "upstream inalcançável".
- **FR-030** A mensagem de certificado não confiado nomeia o fingerprint
  observado e diz por onde se declara confiança nele.
- **FR-031** Sob pin quebrado, a mensagem nomeia o fingerprint esperado **e** o
  observado, identificados como tais.
- **FR-032** Um pin que não bate nunca resulta em conexão: não há degradação para
  o repositório do sistema nem para não verificado.
- **FR-033** Um pin que não bate nunca é atualizado automaticamente.
- **FR-034** Nome de endereço que não confere sob certificado fornecido é uma
  mensagem própria, distinta das outras duas, nomeando o endereço configurado e o
  nome que o certificado carrega.
- **FR-035** A mensagem de rede indisponível permanece a de hoje e não menciona
  certificado.
- **FR-036** O painel da integração mostra a frase da recusa que de fato
  aconteceu, e o vocabulário de estado de credencial herdado — Not connected ·
  Stored · Verified · Degraded · Failing — continua valendo sem termo novo.
- **FR-037** A verificação profunda da integração relata a forma de confiança em
  vigor em uma linha legível.

### O registro

- **FR-038** Gravar uma declaração escreve um evento de auditoria com quem,
  quando, qual integração, quais endereços, qual forma, os fingerprints quando
  há, e a razão quando há.
- **FR-039** A linha de auditoria de cada resolução de credencial passa a
  carregar a forma de confiança usada, e o fingerprint quando a forma é pinada.
- **FR-040** Uma recusa por certificado é auditada com a mesma prioridade de um
  sucesso, carregando o fingerprint observado.
- **FR-041** O payload de auditoria continua sendo um conjunto fixo de escalares:
  os campos novos são declarados, e não há caminho para acrescentar um campo no
  ponto de chamada.
- **FR-042** Nenhum evento de auditoria e nenhuma linha de log carrega material
  de certificado em PEM, chave privada, token, ticket ou senha.
- **FR-043** Fingerprint pode ser registrado em log e em auditoria — ele não é
  segredo, e é o que o operador compara com o que o nó mostra.

### O console

- **FR-044** Os campos de confiança aparecem no painel da integração pelo mesmo
  mecanismo de campos declarados que os demais campos usam, sem componente novo.
- **FR-045** Aceitar não verificado no console exige a razão escrita na própria
  tela e não é apresentado como uma caixa de seleção solta.
- **FR-046** Um operador sem a permissão dedicada não vê a ação de aceitar não
  verificado como disponível, e uma tentativa mesmo assim é recusada pelo
  servidor com o nome da permissão.
- **FR-047** Todo texto de interface novo é declarado como bloco de chaves de
  i18n no relatório final desta feature; esta feature não edita o catálogo.

### O que não muda

- **FR-048** Sandboxes continuam sem falar com o proxy, e a política de rede
  deles é idêntica à de antes desta feature.
- **FR-049** Nenhum outro pacote de integração é alterado nesta feature: o
  carregador é genérico, a declaração e os textos são do Proxmox.
- **FR-050** O caminho sancionado do cliente — construído sem credencial, toda
  chamada pelo proxy — permanece como está; o cliente não ganha nenhum poder
  novo sobre TLS.

### Key Entities

- **Declaração de confiança**: o que este deployment aceita de um endereço.
  Quatro formas, uma padrão, e as duas informações que a forma insegura exige.
  Vive na configuração, ao lado do endereço, com proveniência e auditoria como
  todo o resto do documento.
- **Endereço**: o par vendor + host que apresenta o certificado. É a unidade de
  escopo da confiança, e já é a unidade da allow-list de egress.
- **Recusa por certificado**: uma razão de erro de primeira classe, com três
  formas distinguíveis — não confiado, pin quebrado, nome não confere — cada uma
  com sua frase e seu par de fatos.
- **Evento de aceitação**: a linha da auditoria que responde "quem decidiu
  confiar nisto, quando, e por quê".

## Success Criteria *(mandatory)*

- **SC-001** O Proxmox real do homelab, com seu certificado self-signed, sai de
  Degraded e chega a Verified no staging, com a confiança declarada pela
  interface e sem editar código nem reiniciar processo.
- **SC-002** Depois disso, o estate deixa de estar vazio de Proxmox: a contagem
  de recursos de origem Proxmox presentes é maior que zero.
- **SC-003** Com um fingerprint declarado errado de propósito, a mensagem
  apresentada contém os dois fingerprints e não contém a frase de "nenhum nó
  respondeu".
- **SC-004** Com o endereço inalcançável, a mensagem apresentada é a de hoje e
  não menciona certificado.
- **SC-005** A auditoria do staging tem exatamente um evento de aceitação por
  declaração feita, nomeando o principal autenticado que a fez.
- **SC-006** Uma varredura dos eventos de auditoria e dos logs da feature não
  encontra nenhum cabeçalho de certificado, nenhum cabeçalho de chave privada e
  nenhum token.
- **SC-007** Os três modos de confiança têm teste de contrato do proxy, e o
  quarto caso — pin quebrado — também.
- **SC-008** Uma tentativa de aceitar não verificado sem a permissão dedicada é
  recusada em 100% das tentativas, e nenhuma delas grava nada.
- **SC-009** `make verify` termina verde.

### As consultas que provam, no banco de staging

Enumeradas aqui porque o ciclo de validação da onda exige contagem no banco
quando a feature alega gravação, e alegar sem a consulta escrita é alegar.

```sql
-- SC-002: o estate deixou de estar vazio de Proxmox
select count(*) from estate_resources
 where source = 'proxmox' and absent_since is null;

-- SC-001: o veredito da integração
select kind, subject, outcome, checked_at, detail
  from verifications where subject = 'proxmox';

-- SC-005: a aceitação registrada, com quem e quando
select occurred_at, actor_kind, actor_id, outcome, detail
  from audit_events
 where resource_kind = 'integration' and resource_id = 'proxmox'
 order by occurred_at desc limit 10;

-- SC-006: nenhum material sensível no registro
select count(*) from audit_events
 where detail::text like '%BEGIN CERTIFICATE%'
    or detail::text like '%PRIVATE KEY%'
    or detail::text like '%PVEAPIToken%';
-- esperado: 0
```

## Assumptions

- O staging tem o Proxmox de verdade (pve02, self-signed) e ele é a prova real.
  O acceptance de staging é **read-only**: declarar a confiança, verificar, e ver
  a descoberta povoar o estate. Descoberta é leitura; nada nesta feature escreve
  no hipervisor.
- O endereço de uma integração já viaja da tela até o proxy pela árvore de
  configuração, com proveniência, prévia e auditoria, e o proxy já relê essa
  árvore periodicamente em vez de só no arranque. A confiança viaja pelo mesmo
  caminho, e não por um segundo caminho paralelo.
- A entrada de integração na configuração é, hoje, uma por vendor, com um
  endereço. Um cluster com vários nós é declarado no que a entrada já oferece
  para isso; esta feature não introduz uma segunda forma de declarar endereço.
- Um certificado público não é segredo. Ele pode viver na árvore de configuração
  como o endereço vive. Uma chave privada não pode, e por isso o campo a recusa
  em vez de confiar em quem cola.
- O vocabulário de estado de credencial herdado continua normativo e nenhum
  termo novo é criado para descrever confiança.

## Dependencies

- Nenhuma feature desta onda. A 070 roda em paralelo com a 030 no slot S3.
- A **080** depende desta: o cenário ponta a ponta precisa do Proxmox conectado
  de verdade para o estate ter sujeito e o incidente ter onde aterrissar.
- A **030** é a dona dos arquivos de escrita única no slot; as chaves de i18n
  desta feature são entregues como bloco.

## Out of Scope

- **Confiança para outros vendors.** O carregador é genérico porque a fronteira é
  do proxy e um carregador por vendor seria dois dentro de um release. Mas a
  declaração, a documentação e os textos são do Proxmox nesta feature, e nenhum
  outro pacote de integração é alterado. O critério de pronto é o Proxmox real
  conectando, não um catálogo inteiro habilitado.
- **Certificado de cliente (mTLS) para vendor.** É a outra metade do TLS e uma
  decisão diferente — colocaria chave privada na configuração, que é justamente
  o que esta feature recusa. Fica para quem tiver um vendor que exija.
- **Rotação e renovação automáticas de pin.** Explicitamente fora: um pin que se
  atualiza sozinho não é um pin.
- **Descoberta automática do fingerprint apresentado, oferecida como
  "confiar neste".** É a caixinha de novo, com uma etapa a mais. O fingerprint
  observado aparece na mensagem de recusa para o operador **comparar** com o que
  o nó mostra; adotá-lo continua sendo uma escrita deliberada.
- **Mudar como o cliente Proxmox faz failover entre nós.** O anel de endereços
  fica como está.
- **Bundle de autoridade por variável de ambiente.** Continua existindo e
  continua funcionando; esta feature não o remove nem o transforma.
