# Feature Specification: O catálogo ensina — todo campo diz o que criar e o que marcar

**Feature Branch**: `feat/v7-060-o-catalogo-ensina`

**Created**: 2026-08-23

**Status**: Draft

**Input**: Briefing da onda (`specs_v7/briefings/060.md`) e o item
"The screen has room the packages have not filled" do `backlog.md` da raiz, mais
a metade "credencial em HTTP claro" do item "Two seams the deep verify opened
rather than closed".

**Referência visual (DoD)**: nenhuma tela nova. As duas superfícies tocadas já
existem e já foram desenhadas — o slide-over de credencial
(`/integrations/{name}`, registrado como tela visual) e o passo de integrações
do primeiro acesso. Esta feature preenche o que elas já sabem renderizar e
acrescenta uma seção de documentação ao slide-over. Por isso **não há mockup
próprio**: as alegações normativas abaixo substituem o mockup, e o
`console/tests/e2e/catalogue-teaches.acceptance.spec.ts` as codifica, confirmado
vermelho antes de qualquer implementação. **Viewport normativo de medição:
1920×1080.**

---

## Alegações normativas

Frases curtas, individualmente testáveis, derivadas do diagnóstico e do backlog.
Cada uma vira uma asserção do acceptance spec. Uma vírgula é fronteira de
requisito: nenhuma delas carrega duas obrigações.

- **AN-01** — Todo campo secreto de todo vendor embarcado mostra uma linha de
  permissão mínima.
- **AN-02** — Nenhum campo que não é secreto mostra linha de permissão mínima.
- **AN-03** — Todo campo de todo vendor embarcado oferece um link "onde
  conseguir".
- **AN-04** — Todo link "onde conseguir" aponta um endereço absoluto.
- **AN-05** — A tela da integração mostra a frase "onde obter" do vendor.
- **AN-06** — A frase "onde obter" que a tela da integração mostra é a mesma que
  o primeiro acesso mostra para o mesmo vendor.
- **AN-07** — A tela da integração oferece a documentação do pacote sem sair do
  console.
- **AN-08** — A documentação renderizada não exibe nenhum caractere de sintaxe
  markdown como texto.
- **AN-09** — Uma integração cuja documentação o deployment não devolveu diz que
  não conseguiu lê-la.
- **AN-10** — Apontar um vendor para `http://` com credencial armazenada produz
  uma frase que nomeia o esquema.
- **AN-11** — Essa mesma frase nomeia as duas saídas: usar o endereço TLS, ou não
  armazenar credencial.
- **AN-12** — Nenhum campo sem permissão mínima declarada renderiza uma linha de
  permissão vazia.
- **AN-13** — Nenhum campo sem guia declarado renderiza um link sem destino.

**Staging-safe**: AN-01 a AN-09 e AN-12/AN-13 são leitura pura e rodam contra
`https://stg-ninjasre.lan.kyo.ninja`, abrindo `grafana`, `prometheus` e
`proxmox` — três integrações reais do estate. AN-10 e AN-11 **não** são
staging-safe: exigem escrever uma credencial contra um endereço `http://`, o que
é escrita em ambiente compartilhado. Rodam só no backing local.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Quem nunca abriu o console do vendor sabe o que criar lá (Priority: P1)

Um operador abre `/integrations/grafana`, vê três campos, e ao lado de cada um
lê qual é a permissão mínima que aquele valor precisa ter e um link para o
passo-a-passo oficial de como emiti-lo. Ele não abre uma segunda aba para
pesquisar, e não descobre que o token estava curto demais durante um incidente.

**Why this priority**: é a feature inteira. A metade maior deste item do backlog
já foi entregue — endereço declarável, escrita separada por tipo de campo, três
vendors `credential_optional`, direção do tráfego na tela, "Test again" contra a
instância do próprio operador. O que restou é a orientação, e sem ela um campo
que alguém pode preencher continua sendo um campo que alguém precisa pesquisar.

**Independent Test**: pedir o catálogo ao gateway e conferir que todo campo
secreto de todo vendor traz permissão mínima, e que todo campo de todo vendor
traz um endereço de guia.

**Acceptance Scenarios**:

1. **Given** o catálogo servido, **When** os campos de um vendor embarcado são
   lidos, **Then** cada campo secreto declara a permissão mínima que o modelo de
   permissões do vendor precisa conceder.
2. **Given** o catálogo servido, **When** os campos de um vendor embarcado são
   lidos, **Then** cada campo declara um endereço de guia.
3. **Given** a tela de uma integração, **When** um campo secreto é renderizado,
   **Then** a permissão mínima aparece abaixo do controle e o link do guia
   aparece abaixo dela.
4. **Given** a tela de uma integração, **When** um campo que não é secreto é
   renderizado, **Then** nenhuma linha de permissão mínima aparece.

---

### User Story 2 - A regressão é impedida por gate, não por revisão (Priority: P1)

Um contribuidor acrescenta um campo de credencial a um vendor e esquece a
permissão mínima. A verificação do repositório reprova nomeando o vendor e o
campo, antes de o campo chegar a uma tela.

**Why this priority**: preencher quarenta campos uma vez é trabalho de um dia;
mantê-los preenchidos é uma propriedade que só existe se algo a enforçar. É a
mesma família dos sete artefatos de paridade — que é enforçada, não revisada — e
pelo mesmo argumento: um catálogo cuja completude depende de alguém lembrar já
está incompleto em algum vendor que ninguém olhou.

**Independent Test**: apagar a permissão mínima de um campo secreto e conferir
que a verificação reprova nomeando aquele vendor e aquele campo; restaurar e
conferir que volta a passar.

**Acceptance Scenarios**:

1. **Given** um campo secreto sem permissão mínima, **When** a verificação de
   integrações roda, **Then** ela reprova nomeando o vendor e o campo.
2. **Given** um campo qualquer sem endereço de guia, **When** a verificação de
   integrações roda, **Then** ela reprova nomeando o vendor e o campo.
3. **Given** um campo que não é secreto com uma permissão mínima declarada,
   **When** a verificação roda, **Then** ela reprova nomeando o vendor e o campo,
   porque um endereço e um nome de namespace não concedem permissão nenhuma.
4. **Given** a árvore com os quarenta campos orientados, **When** a verificação
   completa do repositório roda, **Then** ela passa.

---

### User Story 3 - A mesma frase alcança as duas telas (Priority: P1)

O operador que conecta um vendor pelo primeiro acesso e o operador que conecta o
mesmo vendor pela tela da integração leem a mesma frase sobre onde obter aquela
credencial. Nenhuma das duas telas sabe algo que a outra não sabe.

**Why this priority**: é o defeito literal do backlog — `IntegrationPanel` nunca
passa `whereToGetIt` e o formulário de credencial já renderiza a frase quando
recebe. Duas telas com a mesma responsabilidade e uma informação a menos numa
delas é como uma passa a ser "a tela certa para conectar", que é uma regra que
ninguém escreveu e todo mundo tem de aprender.

**Independent Test**: abrir o mesmo vendor nas duas telas e comparar as duas
frases, que têm de ser idênticas por virem de uma declaração só.

**Acceptance Scenarios**:

1. **Given** um vendor embarcado, **When** a tela da integração é aberta,
   **Then** a frase "onde obter" daquele vendor aparece no formulário.
2. **Given** o mesmo vendor, **When** o passo de integrações do primeiro acesso é
   aberto, **Then** a mesma frase aparece no formulário.
3. **Given** um vendor sem frase declarada, **When** qualquer uma das duas telas
   é aberta, **Then** nenhuma linha vazia ocupa o lugar dela.

---

### User Story 4 - A documentação do pacote é lida sem sair do console (Priority: P2)

Cada pacote de integração carrega um documento que responde o que um operador
pergunta — o que cada campo é, onde no console do vendor a permissão é
concedida, e o que a integração não consegue fazer. Hoje nenhuma rota o serve.
O operador passa a lê-lo no próprio slide-over.

**Why this priority**: P2 e não P1 porque o documento existe e é encontrável por
quem tem o repositório; o que falta é o operador de um deployment, que não tem.
A orientação por campo (P1) resolve o preenchimento; este documento resolve as
perguntas que sobram — limitações, o que cada permissão desbloqueia, por que a
verificação prova o que prova.

**Independent Test**: pedir a documentação de um vendor embarcado ao gateway e
conferir que o texto devolvido é o do pacote; abrir a tela e conferir que ele
aparece renderizado.

**Acceptance Scenarios**:

1. **Given** um vendor embarcado, **When** sua documentação é pedida ao gateway,
   **Then** o texto do documento do pacote é devolvido.
2. **Given** um nome que não é de vendor embarcado, **When** a documentação é
   pedida, **Then** a resposta é uma ausência nomeada, e nenhum arquivo fora do
   diretório dos pacotes é lido.
3. **Given** a tela de uma integração, **When** ela é aberta, **Then** a
   documentação do pacote está disponível nela, renderizada como leitura.
4. **Given** a documentação renderizada, **When** ela é lida, **Then** nenhum
   caractere de sintaxe markdown aparece como texto.
5. **Given** uma leitura de documentação que falhou, **When** a tela é
   renderizada, **Then** ela diz que não conseguiu ler, e não que não existe.

---

### User Story 5 - A recusa de credencial em claro diz o que fazer (Priority: P2)

Um operador aponta um vendor para `http://…` e armazena um token. A chamada é
recusada — como sempre foi — e agora a frase diz o que aconteceu e quais são as
duas saídas: usar o endereço TLS do vendor, ou não armazenar credencial nenhuma e
conectá-lo só por endereço.

**Why this priority**: P2 porque o comportamento já está correto e é seguro; o
que está errado é o texto. A recusa hoje chega com a sentença da lista de
egresso — "may not reach 'http://host'. Its declared hosts are …" — que é a
frase de um problema diferente e manda o operador conferir uma allow-list que
está certa.

**Independent Test**: configurar um vendor com endereço `http://` e credencial
armazenada, disparar a verificação e ler a frase devolvida.

**Acceptance Scenarios**:

1. **Given** um vendor com credencial armazenada e endereço `http://`, **When**
   uma chamada é feita, **Then** ela é recusada.
2. **Given** essa recusa, **When** a frase é lida, **Then** ela nomeia o esquema
   inseguro.
3. **Given** essa recusa, **When** a frase é lida, **Then** ela oferece usar o
   endereço TLS.
4. **Given** essa recusa, **When** a frase é lida, **Then** ela oferece não
   armazenar credencial.
5. **Given** um vendor com endereço `http://` e **nenhuma** credencial
   armazenada, **When** uma chamada é feita, **Then** ela não é recusada por este
   motivo — nada vai em claro.
6. **Given** a recusa, **When** o estado da integração é lido, **Then** ele é o
   mesmo estado que a classificação de egresso sempre produziu, espelhado e não
   traduzido.

---

### Edge Cases

- **Um vendor sem site de documentação próprio.** `hermes` é auto-hospedado e
  não tem um endereço público de documentação de fornecedor. O guia dele aponta
  a própria documentação do pacote, servida por este deployment pela rota desta
  feature — o único guia que existe de fato. Ver "Assumptions".
- **Um campo que é secreto mas não carrega permissão.** `proxmox.ticket` e
  `proxmox.csrf_token` são material de sessão emitido pelo próprio Proxmox, não
  um token com escopo. A permissão mínima deles é a do login que os emitiu, e é
  isso que a declaração diz — não uma invenção de escopo.
- **Alternativas mutuamente exclusivas.** `proxmox.api_token` e
  `proxmox.password` declaram um ao outro como alternativa. Cada um carrega sua
  própria permissão mínima e seu próprio guia; a orientação é por campo, não por
  caminho de autenticação.
- **Um vendor que não pede autenticação.** `alertmanager` e `prometheus` têm
  token opcional. O campo continua existindo, continua sendo secreto, e continua
  precisando de orientação — a permissão mínima de um token que atravessa um
  proxy reverso é o que aquele proxy aceita, e dizer isso é mais útil que deixar
  em branco.
- **Um link oficial que morre.** Documentação de fornecedor muda de endereço. O
  gate valida presença e forma do endereço, nunca alcançabilidade — ver
  "Assumptions".
- **A tabela de Setup do documento do pacote diverge do schema.** O documento
  passa a ser servido ao operador, então uma tabela desatualizada deixa de ser um
  detalhe de repositório e vira uma tela mentindo. As tarefas por vendor
  atualizam as duas metades juntas; um gate de divergência entre elas fica fora
  de escopo e registrado.
- **O documento do pacote não chega na imagem construída.** A rota lê um arquivo
  que vive dentro do pacote Python. Se o empacotamento não incluir `docs.md`, a
  rota responde ausência num deployment real e passa em todo teste local.
- **Um nome de vendor vindo da URL.** A rota de documentação nunca compõe um
  caminho de arquivo a partir do segmento da URL: resolve o nome contra o
  catálogo e usa o caminho que o próprio relatório de paridade já conhece.

## Requirements *(mandatory)*

### Os 40 campos de credencial dos 15 vendors embarcados

Derivados dos schemas reais em `integrations/*/schema.py` (varredura de
2026-08-23). `E` = endereço, `S` = secreto, `P` = configuração pública. As duas
últimas colunas são o estado **hoje**.

| Vendor | Campo | Tipo | Obrigatório | `min_scope` hoje | `guide_url` hoje |
|---|---|---|---|---|---|
| alertmanager | `endpoint` | E | não | — | — |
| alertmanager | `token` | S | não | sim | — |
| argocd | `endpoint` | E | não | — | — |
| argocd | `token` | S | sim | sim | sim |
| github | `endpoint` | E | não | — | — |
| github | `token` | S | sim | sim | sim |
| github | `owner` | P | sim | — | — |
| google_gemini | `api_key` | S | sim | sim | sim |
| grafana | `endpoint` | E | não | — | — |
| grafana | `token` | S | sim | sim | sim |
| grafana | `org` | P | sim | — | — |
| hermes | `endpoint` | E | não | — | — |
| hermes | `api_key` | S | sim | sim | — |
| hermes | `stream` | P | sim | — | — |
| kubernetes | `endpoint` | E | não | — | — |
| kubernetes | `token` | S | sim | sim | sim |
| kubernetes | `cluster` | P | não | — | — |
| kubernetes | `namespace` | P | não | — | — |
| loki | `endpoint` | E | não | — | — |
| loki | `token` | S | não | sim | — |
| loki | `tenant` | P | sim | — | sim |
| openobserve | `endpoint` | E | não | — | — |
| openobserve | `username` | S | sim | — | — |
| openobserve | `password` | S | sim | sim | — |
| openobserve | `organisation` | P | sim | — | — |
| prometheus | `endpoint` | E | não | — | — |
| prometheus | `token` | S | não | sim | — |
| proxmox | `endpoint` | E | não | — | — |
| proxmox | `api_token` | S | sim | sim | sim |
| proxmox | `username` | P | sim | — | — |
| proxmox | `password` | S | não | — | — |
| proxmox | `ticket` | S | não | — | — |
| proxmox | `csrf_token` | S | não | — | — |
| pushover | `token` | S | sim | — | sim |
| pushover | `user_key` | S | sim | — | sim |
| redis | `api_key` | S | sim | — | sim |
| redis | `secret_key` | S | sim | sim | — |
| signoz | `endpoint` | E | não | — | — |
| signoz | `api_key` | S | sim | — | — |
| telegram | `token` | S | sim | — | sim |

**A aritmética que esta spec afirma**: 40 campos em 15 vendors — 21 secretos, 8
públicos, 11 endereços. `min_scope` hoje em 12 campos, todos secretos: faltam
**9 campos secretos** (`openobserve.username`, `proxmox.password`,
`proxmox.ticket`, `proxmox.csrf_token`, `pushover.token`, `pushover.user_key`,
`redis.api_key`, `signoz.api_key`, `telegram.token`). `guide_url` hoje em 11
campos: faltam **29**.

### A forma da orientação, por tipo de campo

A leitura crua do backlog é "28 de 40 sem `min_scope`, preencher os 40". Esta
spec recusa essa leitura e decide outra, porque preencher os 28 exigiria inventar
uma permissão para um endereço e para um nome de namespace — exatamente o que a
declaração de campo proíbe em texto ("um escopo adivinhado é uma permissão que o
operador cola no console do fornecedor e descobre errada durante um incidente").
A regra fica:

- **Permissão mínima**: obrigatória em todo campo secreto; proibida em campo de
  endereço e em campo de configuração pública. 21 obrigatórias, 19 obrigatoriamente
  em branco.
- **Guia**: obrigatório em todo campo, dos três tipos. 40 obrigatórios. Sempre
  existe um lugar que diz de onde vem aquele valor — inclusive o endereço, cuja
  documentação é a do próprio fornecedor sobre onde sua API responde.

"40/40 orientados" é o número que o DoD afirma, e ele significa isto: cada campo
carrega a orientação que o seu tipo admite.

### Functional Requirements

#### Conteúdo por vendor

- **FR-001**: Todo campo secreto de todo vendor embarcado DEVE declarar a
  permissão mínima que o modelo de permissões do fornecedor precisa conceder.
- **FR-002**: Toda permissão mínima declarada DEVE ser a permissão real do
  fornecedor, verificada na documentação dele.
- **FR-003**: Nenhuma permissão mínima DEVE ser inferida do nome do campo nem
  copiada de outro vendor.
- **FR-004**: Nenhum campo de endereço DEVE declarar permissão mínima.
- **FR-005**: Nenhum campo de configuração pública DEVE declarar permissão
  mínima.
- **FR-006**: Todo campo de todo vendor embarcado DEVE declarar um endereço de
  guia.
- **FR-007**: Todo endereço de guia DEVE ser um endereço absoluto.
- **FR-008**: Todo endereço de guia DEVE apontar a documentação oficial do
  fornecedor, exceto para um vendor sem site de documentação próprio, cujo guia
  aponta a documentação do pacote servida por este deployment.
- **FR-009**: A fonte de cada permissão mínima e de cada guia DEVE ficar citada
  no documento do pacote do vendor.
- **FR-010**: A tabela de campos do documento de cada vendor tocado DEVE
  concordar com o schema daquele vendor ao final.

#### O gate

- **FR-011**: A verificação de integrações DEVE reprovar um campo secreto sem
  permissão mínima.
- **FR-012**: A verificação de integrações DEVE reprovar qualquer campo sem
  endereço de guia.
- **FR-013**: A verificação de integrações DEVE reprovar um campo de endereço ou
  de configuração pública que declare permissão mínima.
- **FR-014**: A verificação de integrações DEVE reprovar um endereço de guia que
  não seja absoluto.
- **FR-015**: Cada reprovação DEVE nomear o vendor e o campo.
- **FR-016**: Cada reprovação DEVE dizer o que a ausência custa, na mesma forma
  que as reprovações de paridade já usam.
- **FR-017**: Todas as reprovações DEVEM ser reportadas de uma vez, e não uma por
  execução.
- **FR-018**: A verificação NÃO DEVE fazer requisição de rede para checar um
  endereço de guia.
- **FR-019**: O gate novo DEVE rodar dentro da verificação completa do
  repositório sem que ela ganhe um alvo novo.

#### A frase "onde obter", nas duas telas

- **FR-020**: Todo vendor embarcado DEVE declarar, no seu próprio pacote, a frase
  que diz onde obter sua credencial.
- **FR-021**: O catálogo servido DEVE carregar essa frase por vendor.
- **FR-022**: A tela da integração DEVE mostrar essa frase no formulário de
  credencial.
- **FR-023**: O passo de integrações do primeiro acesso DEVE mostrar a mesma
  frase no formulário de credencial.
- **FR-024**: As duas telas DEVEM ler a frase da mesma declaração, e nenhuma das
  duas DEVE carregar uma cópia.
- **FR-025**: Nenhuma das duas telas DEVE renderizar um lugar vazio quando a
  frase não existe.

#### A documentação do pacote, servida

- **FR-026**: O produto DEVE servir a documentação de um vendor embarcado por um
  endereço próprio.
- **FR-027**: O texto servido DEVE ser o do documento que vive no pacote do
  vendor.
- **FR-028**: O endereço DEVE exigir a mesma permissão que a leitura do catálogo
  já exige.
- **FR-029**: O endereço DEVE responder ausência nomeada para um nome que não é
  de vendor embarcado.
- **FR-030**: A resolução do documento NÃO DEVE compor um caminho de arquivo a
  partir do valor recebido na URL.
- **FR-031**: A tela da integração DEVE oferecer essa documentação sem que o
  operador saia do console.
- **FR-032**: A documentação DEVE ser renderizada como leitura, e não impressa
  como texto cru.
- **FR-033**: A renderização DEVE reutilizar o renderizador de markdown que já
  existe no console.
- **FR-034**: NÃO DEVE ser introduzido um segundo renderizador de markdown.
- **FR-035**: A saída renderizada DEVE ser sanitizada.
- **FR-036**: Uma leitura de documentação que falhou DEVE ser dita como falha de
  leitura, nunca como ausência de documento.
- **FR-037**: O documento de cada pacote DEVE continuar presente na imagem
  construída do produto.

#### A recusa de credencial em HTTP claro

- **FR-038**: A recusa de enviar credencial por conexão não cifrada DEVE produzir
  uma frase distinta da recusa de lista de egresso.
- **FR-039**: Essa frase DEVE nomear o esquema pelo qual o vendor foi apontado.
- **FR-040**: Essa frase DEVE oferecer apontar o vendor para o endereço TLS.
- **FR-041**: Essa frase DEVE oferecer não armazenar credencial para aquele
  vendor.
- **FR-042**: Essa frase DEVE ser escrita num lugar só e espelhada por toda
  superfície que a mostra.
- **FR-043**: A classificação da recusa NÃO DEVE mudar.
- **FR-044**: O comportamento de recusar NÃO DEVE mudar: continua recusando
  exatamente quando uma credencial resolveu e o esquema não é o permitido.
- **FR-045**: Um vendor apontado para `http://` sem credencial armazenada NÃO
  DEVE ser recusado por este motivo.

#### Fronteiras desta feature

- **FR-046**: Nenhum arquivo committed DEVE citar identificador de requisito,
  número de artigo, número de feature ou caminho de documento de planejamento.
- **FR-047**: Nenhum arquivo committed DEVE depender de um arquivo que não esteja
  no repositório.
- **FR-048**: A verificação completa do repositório DEVE ficar verde ao final,
  tendo partido de verde.

### Key Entities

- **Campo de credencial**: uma parte nomeada da credencial de um vendor, com um
  tipo (secreto, configuração pública, endereço), um rótulo, uma permissão mínima
  quando é secreto, e um guia sempre.
- **Permissão mínima**: o menos que o modelo de permissões do próprio fornecedor
  precisa conceder para que aquele valor sirva — nas palavras do fornecedor, e
  nunca uma paráfrase inventada aqui.
- **Guia**: o endereço do passo-a-passo que produz aquele valor. Presença e forma
  são verificadas; alcançabilidade não é.
- **Frase "onde obter"**: uma sentença por vendor, declarada no pacote, mostrada
  igual nas duas telas que pedem a credencial daquele vendor.
- **Documentação do pacote**: o documento que cada pacote de integração já carrega
  — campos, permissões, limitações — passando a ser legível de dentro do produto.
- **Recusa de credencial em claro**: a negativa de enviar material secreto por
  conexão não cifrada, classificada como sempre foi e dita numa frase própria.

## Success Criteria *(mandatory)*

- **SC-001**: Os 21 campos secretos dos 15 vendors embarcados declaram permissão
  mínima; nenhum dos outros 19 declara.
- **SC-002**: Os 40 campos declaram endereço de guia.
- **SC-003**: Apagar a permissão mínima de qualquer um dos 21 faz a verificação
  reprovar nomeando aquele vendor e aquele campo.
- **SC-004**: Apagar o guia de qualquer um dos 40 faz a verificação reprovar
  nomeando aquele vendor e aquele campo.
- **SC-005**: Abrir `grafana`, `prometheus` e `proxmox` no staging mostra, para
  cada campo secreto, a permissão mínima e o link do guia.
- **SC-006**: A frase "onde obter" de um mesmo vendor é caractere por caractere a
  mesma nas duas telas.
- **SC-007**: A documentação de `grafana`, `prometheus` e `proxmox` é lida no
  staging dentro do slide-over, renderizada, sem nenhum caractere de sintaxe
  markdown visível como texto.
- **SC-008**: O `console/package.json` declara exatamente um renderizador de
  markdown ao final, o mesmo de antes desta feature.
- **SC-009**: Uma chamada com credencial armazenada contra endereço `http://`
  produz uma frase que contém o esquema, a saída TLS e a saída sem credencial.
- **SC-010**: A mesma chamada continua classificada exatamente como estava antes
  desta feature.
- **SC-011**: A documentação de cada um dos 15 vendors é legível a partir da
  imagem construída do produto, e não só do checkout.
- **SC-012**: O acceptance spec desta feature foi visto vermelho antes de
  qualquer implementação, e o vermelho está registrado.
- **SC-013**: A verificação completa do repositório passa, comparada contra a
  mesma verificação rodada antes.

## Assumptions

- **Conteúdo por vendor é pesquisa, não geração.** Cada permissão mínima e cada
  guia sai da documentação do próprio fornecedor, lida na hora, e a fonte é
  citada no documento do pacote. Um escopo plausível é pior que um campo em
  branco: em branco o operador sabe que precisa pesquisar; plausível e errado ele
  descobre durante um incidente.
- **O gate valida presença e forma do guia, nunca alcançabilidade.** Uma
  verificação que faz requisição HTTP transforma toda execução da verificação
  numa dependência de rede e reprova o repositório quando um fornecedor
  reorganiza o site — uma falha que não é do contribuidor, num alvo que precisa
  ser determinístico. Link morto é um problema real e o remédio é outro: uma
  varredura periódica fora do caminho de build, fora do escopo desta feature.
- **Um vendor sem site de documentação próprio aponta a documentação deste
  deployment.** `hermes` é o caso; o guia dele passa a ser o endereço em que este
  produto serve o documento do pacote, que é o único passo-a-passo que existe. É
  uma decisão a confirmar com o operador, e o gate a aceita como forma válida.
- **A documentação servida vem de arquivo committed.** O documento vive dentro do
  pacote do vendor, no repositório, e é o que a rota lê. Nenhum arquivo committed
  passa a depender de arquivo que não esteja no repositório.
- **O renderizador de markdown já existe quando esta feature roda.** Ele é
  entregue no slot anterior pela feature de leitura do relato. Esta feature o
  reutiliza e não escolhe biblioteca nenhuma.
- **O estado da integração continua sendo espelhado, nunca traduzido.** A recusa
  de credencial em claro muda de frase e não de classificação; o console continua
  mostrando o estado que o backend classificou.
- **A frase "onde obter" é declarada por vendor, no pacote.** É a mesma forma que
  os provedores de modelo já usam para a mesma informação, e mantém a propriedade
  de que acrescentar um vendor é um pacote e nenhuma edição em arquivo central.
- **Esta feature é dona dos arquivos de escrita única no seu slot.** Catálogo de
  mensagens, registro de rotas e registro de telas visuais são editados aqui; a
  feature parceira declara suas chaves no relatório final.

## Dependencies

- A feature de leitura do relato (slot anterior) entrega o renderizador de
  markdown sanitizado que esta reutiliza. Sem ele, a documentação do pacote não
  tem como ser renderizada e a tarefa correspondente para.
- A feature de governança (primeiro slot) entrega a regra de composição e o modo
  de rodar acceptance contra o staging real, que esta feature usa.
- Nenhuma dependência sobre a feature de identidade, que é a parceira de slot. As
  áreas de console são distintas; a única sobreposição possível é o arquivo que
  compõe os passos do primeiro acesso, coordenada no plano.
- Não bloqueia nenhuma feature posterior. O cenário ponta-a-ponta do último slot
  se beneficia dela (Proxmox conectado com orientação real), mas não depende.

## Out of Scope

- Alcançabilidade dos endereços de guia, e qualquer varredura periódica que a
  cheque.
- Um gate de divergência entre a tabela de campos do documento do pacote e o
  schema daquele pacote.
- Qualquer alteração no modo como uma credencial é armazenada, validada ou
  injetada.
- A confiança de certificado do Proxmox, que é outra feature desta onda — esta
  aqui não toca `CertificateTrust` nem o caminho de egresso do proxy além da
  frase de recusa.
- A unificação entre credencial de time e vínculo de organização, que é outra
  feature desta onda.
- Documentação gerada em `docs/`, que continua saindo do gerador e não é tocada
  aqui.
- Qualquer vendor fora dos 15 embarcados.
