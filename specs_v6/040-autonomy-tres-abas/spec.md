# Feature Specification: Autonomy & guardrails em três abas

**Feature Branch**: `feat/v6-040-autonomy-tres-abas`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "Autonomy & guardrails deixa de ser um kitchen-sink
de 2.3 viewports e vira três perguntas em três abas: Posture (o que pode
sozinho), Rules & windows (quando não pode), Guardrails (o que sempre vale).
Estado na URL, ≤1.5 viewport por aba, tabela com valores presentes, override
em painel lateral, paridade de schema preservada."

**Referência visual (DoD)**: [../mockups/settings-v6.html#m2](../mockups/settings-v6.html#m2)
— M2: as três abas, o subtítulo "Node: deployment · Posture now: propose-only",
o cartão "What this deployment may do on its own", a tabela "Guardrails in
effect" com a coluna Value preenchida, e o painel lateral "Temporary override".
As quatro alegações anotadas do mockup (callouts 1–4) são requisitos, uma a uma.

**Evidência do estado atual** (Full HD, preview 3100, backend CT254 em
`eb8c6f1`): `/settings/autonomy-guardrails` mede **2026px = 2.3 viewports**;
três parágrafos conceituais sob o título; tabela Guardrails com a coluna VALUE
vazia nas 12 linhas; override ocupando um terço permanente do corpo; CTA "Look
at the configuration" que abre `#new-rule` na própria página; grupos
`policies.masking` / `policies.guardrails` / `policies.approvals` como títulos
de seção; simulação com três botões de três estilos e nenhum contexto.
Diagnóstico §1 e §2 — P1-4, P2-10, P2-11.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Uma pergunta por aba, endereçável pela URL (Priority: P1)

Um operador que abre Autonomy & guardrails encontra três abas — Posture, Rules
& windows, Guardrails — e cada uma responde a exatamente uma pergunta. A aba
aberta está na URL, então um link leva um colega ao mesmo lugar e o botão de
voltar funciona.

**Why this priority**: É o recorte que faz todo o resto caber. Enquanto as sete
preocupações dividem uma página só, nenhuma delas tem espaço para ser
respondida bem, e a tela mede 2.3 viewports contra um orçamento de 2.

**Independent Test**: Abrir a rota, percorrer as três abas pela URL, e medir a
altura de cada uma em 1920×1080.

**Acceptance Scenarios**:

1. **Given** a rota sem parâmetro de aba, **When** a tela abre, **Then**
   Posture está ativa e a URL passa a nomeá-la.
2. **Given** um endereço que nomeia uma das três abas, **When** aberto
   diretamente, **Then** aquela aba está ativa sem passar por outra.
3. **Given** um nome de aba que não existe, **When** aberto, **Then** a tela
   abre em Posture, sem erro e sem tela em branco.
4. **Given** qualquer uma das três abas, **When** sua altura é medida em
   1920×1080, **Then** ela cabe em 1.5 viewport.
5. **Given** uma troca de aba, **When** o operador usa o botão de voltar do
   navegador, **Then** retorna à aba anterior.

---

### User Story 2 - Postura decidida onde ela é explicada (Priority: P1)

A aba Posture responde "o que este deployment pode fazer sozinho": um seletor
de nível, um salvar, e — quando não há regra nenhuma registrada — uma frase que
diz o que o vazio significa em vez de deixar o operador achar que algo quebrou.

**Why this priority**: É a decisão mais consequente da tela e hoje ela chega
depois de três parágrafos conceituais que ninguém lê. O empty state atual
manda "Look at the configuration" — um rótulo que promete outra tela e abre uma
âncora da mesma página.

**Independent Test**: Num nó sem nenhuma regra, ler o que a tela diz sobre o
vazio, trocar a postura e salvar.

**Acceptance Scenarios**:

1. **Given** a tela aberta, **When** o cabeçalho é lido, **Then** o subtítulo
   diz o nó e a postura vigente, e não há parágrafo conceitual entre o título e
   o primeiro controle.
2. **Given** a aba Posture, **When** ela abre, **Then** o seletor traz os
   níveis que o deployment declara, em nomes de exibição, com a ação de salvar
   ao lado.
3. **Given** um nó sem nenhuma regra registrada, **When** o empty state
   aparece, **Then** ele afirma que tudo resolve para propose-only, que esse é
   o default seguro e não um erro, e nomeia Rules & windows como o lugar de
   estreitar ou ampliar um escopo.
4. **Given** o empty state, **When** o operador segue o CTA, **Then** chega ao
   destino que o rótulo prometeu.
5. **Given** a aba Posture, **When** ela abre, **Then** traz os guardrails em
   vigor em leitura resumida, com valor e origem — sem duplicar a edição que a
   aba Guardrails detém.

---

### User Story 3 - Guardrails com valor efetivo à vista e editável (Priority: P1)

A aba Guardrails responde "o que sempre vale": cada guardrail com o seu valor
efetivo, a origem desse valor, e a edição dos campos que o schema permite ali
mesmo.

**Why this priority**: Hoje a coluna VALUE está vazia nas 12 linhas — a tabela
informa só "Deployment default" e o operador não descobre o valor efetivo de
nada. Uma tela de configuração que não diz o valor configurado é pior que
nenhuma: ela parece funcionar.

**Independent Test**: Percorrer a tabela e confirmar que nenhuma célula de
valor está vazia; editar um campo escalar e ver o valor e a origem mudarem.

**Acceptance Scenarios**:

1. **Given** a aba Guardrails, **When** a tabela é lida, **Then** cada linha
   traz Setting, Value e Set at, e nenhuma célula de Value está vazia.
2. **Given** um valor herdado, **When** exibido, **Then** o valor efetivo está
   na coluna Value e a herança está em Set at — as duas colunas dizem coisas
   diferentes.
3. **Given** um campo que o schema declara editável, **When** o operador o
   altera na própria linha, **Then** a gravação acontece na aba e a origem
   passa a dizer que foi definido aqui.
4. **Given** os grupos de política, **When** a aba é lida, **Then** nenhum
   caminho técnico de grupo aparece como título de seção; cada um tem nome de
   exibição.
5. **Given** um guardrail que a constituição fixa, **When** exibido, **Then**
   aparece como fato declarado, não como controle que se desliga.

---

### User Story 4 - Nenhum campo de configuração fica órfão (Priority: P1)

Todo campo que o editor cru aposentado alcançava e que pertence a esta tela
continua alcançável — agora dentro da aba dona.

**Why this priority**: Reorganizar uma tela em abas é exatamente o movimento em
que um campo se perde: ele não some da tela, some de todas as três. O mapa de
paridade que a v5 estabeleceu existe para essa hipótese, e ele é verificado por
teste, não por leitura.

**Independent Test**: Percorrer os campos que o mapa de paridade atribui a esta
tela e confirmar que cada um tem uma aba dona e um controle funcional.

**Acceptance Scenarios**:

1. **Given** o mapa de paridade, **When** o rework é dado por completo,
   **Then** cada campo atribuído a esta tela continua atribuído a ela e
   alcançável numa das três abas.
2. **Given** um campo que perdeu o seu controle no rework, **When** a
   verificação roda, **Then** ela falha nomeando o campo — a ausência é um
   defeito de build, não uma descoberta de usuário.
3. **Given** um endereço antigo com âncora de seção do editor aposentado,
   **When** aberto, **Then** aterrissa nesta tela na aba que possui aquela
   seção, e não numa aba onde a seção não existe.

---

### User Story 5 - Regras, janelas e tetos com a simulação em contexto (Priority: P2)

A aba Rules & windows responde "quando ele não pode": criar uma regra, uma
janela de congelamento ou um teto de gasto, e simular o efeito antes de salvar
— por um fluxo só, com um CTA primário.

**Why this priority**: A capacidade já existe e funciona; o que falta é
hierarquia. Três botões de três estilos ("Explain one action", "Simulate
everything", "What would this decide differently?") soltos na página não
formam um fluxo, e nenhum deles diz o que a simulação responde.

**Independent Test**: Criar regra, congelamento e teto na mesma aba, e simular
o efeito por um único caminho.

**Acceptance Scenarios**:

1. **Given** a aba Rules & windows, **When** ela abre, **Then** traz a criação
   de regra, de janela de congelamento e de teto, e a lista de regras em ordem
   de resolução.
2. **Given** a seção de simulação, **When** lida, **Then** tem título próprio e
   uma linha que diz o que ela responde.
3. **Given** a simulação, **When** o operador a usa, **Then** há um só CTA
   primário; as variações que hoje competem como botões irmãos deixam de
   competir.
4. **Given** uma regra ainda não simulada, **When** o operador tenta salvar,
   **Then** a gravação continua exigindo que o efeito tenha sido visto.
5. **Given** o empty state de Rules, **When** o CTA é lido, **Then** o rótulo
   nomeia a ação que ele executa.

---

### User Story 6 - Override temporário como ação rara (Priority: P2)

Conceder um override é raro e consequente. Ele sai do corpo permanente da
página e passa a abrir num painel lateral, por um botão no cabeçalho.

**Why this priority**: Hoje o override ocupa um terço permanente de uma tela já
sobrecarregada, cobrando de todo operador o espaço de uma ação que quase
nenhum executa. Mover não muda o que ele faz; muda quanto ele custa a quem não
o usa.

**Independent Test**: Abrir o painel pelo botão do cabeçalho, conceder um
override com nome, nível, razão e duração, e revogá-lo.

**Acceptance Scenarios**:

1. **Given** a tela em qualquer aba, **When** lida, **Then** o override não
   ocupa espaço no corpo; há um botão "Temporary override" no cabeçalho.
2. **Given** o botão, **When** acionado, **Then** o painel lateral abre com
   Name, Level, Reason e Duration.
3. **Given** o campo de razão, **When** lido, **Then** o próprio rótulo declara
   que ela é registrada no audit.
4. **Given** nenhum override ativo, **When** o painel abre, **Then** ele diz
   que nenhum está ativo, em vez de mostrar uma lista vazia.
5. **Given** um override ativo, **When** o painel abre, **Then** ele aparece
   com nome, nível, razão e expiração, e pode ser revogado ali.
6. **Given** uma concessão ou revogação, **When** ela acontece, **Then** entra
   no audit com nome, nível, razão e expiração.

### Edge Cases

- **Deep link com âncora de seção do editor aposentado**: um endereço que
  carrega a âncora de uma seção `policies.*` precisa abrir a aba que possui
  aquela seção. Aterrissar na aba padrão com uma âncora que não existe nela é
  a regressão específica que abas introduzem.
- **Nó com muitas regras**: a aba Rules & windows não pode estourar o
  orçamento porque um nó acumulou regras. A lista é a região que rola, não a
  página.
- **Override ativo quando a tela abre**: a postura efetiva mostrada no
  subtítulo é a que vigora, e o cabeçalho declara que ela vem de um override
  com prazo — não é o nível salvo.
- **Leitor sem permissão de escrita**: lê valores, origens e regras nas três
  abas; não recebe os formulários nem o botão de override, em vez de receber
  controles que falham ao serem usados.
- **Edição concorrente**: uma segunda gravação informa o conflito e mostra o
  valor atual, sem sobrescrever às cegas — comportamento vigente, preservado.
- **Aba pedida por um cliente sem JavaScript**: as abas são endereços, então a
  navegação entre elas não depende de estado só de cliente.
- **Nível de postura que o deployment declara e a tela não tem nome para**:
  renderiza o identificador declarado em vez de omitir a opção.

## Requirements *(mandatory)*

### Functional Requirements

#### Estrutura em abas e estado na URL

- **FR-001**: A rota `/settings/autonomy-guardrails` DEVE apresentar exatamente
  três abas, na ordem Posture, Rules & windows, Guardrails.
- **FR-002**: A aba ativa DEVE estar refletida na URL pelo mesmo parâmetro de
  aba que as demais telas do produto usam.
- **FR-003**: Cada aba DEVE ser um endereço navegável, de modo que o histórico
  do navegador registre a troca.
- **FR-004**: Abrir a rota sem nomear aba DEVE aterrissar em Posture.
- **FR-005**: Um nome de aba desconhecido DEVE aterrissar em Posture, sem erro.
- **FR-006**: Trocar de aba DEVE preservar o nó de escopo selecionado.
- **FR-007**: Nenhuma das três abas DEVE exceder 1.5 viewport de altura medida
  em 1920×1080.
- **FR-008**: O orçamento de 1.5 viewport DEVE ser uma constante nomeada num
  único módulo dono, lida pelo teste que o mede em vez de repetida nele.

#### Cabeçalho e o fim da prosa conceitual

- **FR-009**: O subtítulo da tela DEVE declarar o nó e a postura vigente.
- **FR-010**: A tela NÃO DEVE trazer nenhum parágrafo conceitual entre o título
  e o primeiro controle; os três parágrafos de hoje deixam de existir.
- **FR-011**: Cada conceito retirado do topo DEVE reaparecer como uma frase
  única no controle onde é usado.
- **FR-012**: Nenhum CTA da rota DEVE prometer um destino diferente do que
  abre; em particular, o rótulo "Look at the configuration" desta rota deixa de
  existir.

#### Aba Posture

- **FR-013**: A aba Posture DEVE oferecer um seletor com os níveis de postura
  que o deployment declara, em nomes de exibição.
- **FR-014**: A aba Posture DEVE oferecer uma ação explícita de salvar a
  postura.
- **FR-015**: Um nível declarado pelo deployment para o qual a tela não tem
  nome de exibição DEVE aparecer pelo identificador declarado, nunca omitido.
- **FR-016**: Na ausência de qualquer regra registrada, a aba Posture DEVE
  afirmar que tudo resolve para propose-only.
- **FR-017**: Esse mesmo texto DEVE afirmar que se trata do default seguro, e
  não de um erro.
- **FR-018**: Esse mesmo texto DEVE nomear Rules & windows como o lugar onde se
  estreita ou amplia um escopo.
- **FR-019**: A aba Posture DEVE mostrar os guardrails em vigor em leitura
  resumida, com Setting, Value e Set at.
- **FR-020**: Essa leitura resumida NÃO DEVE duplicar a edição que a aba
  Guardrails detém.

#### Aba Guardrails

- **FR-021**: A aba Guardrails DEVE apresentar cada guardrail com Setting,
  Value e Set at.
- **FR-022**: A coluna Value NUNCA DEVE ficar vazia, em nenhuma linha e em
  nenhuma das duas aparições da tabela.
- **FR-023**: A coluna Value DEVE trazer o valor efetivo resolvido.
- **FR-024**: A coluna Set at DEVE trazer a origem desse valor — default do
  deployment ou definido aqui.
- **FR-025**: Os campos que o schema declara editáveis DEVEM ser editáveis na
  própria aba.
- **FR-026**: Nenhum caminho técnico de grupo de política DEVE aparecer como
  título de seção; cada grupo recebe nome de exibição.
- **FR-027**: O caminho técnico do campo DEVE permanecer disponível onde é
  técnico — registro de auditoria e API —, nunca como título de tela.
- **FR-028**: Os guardrails que a constituição fixa DEVEM aparecer como fatos
  declarados, nunca como controles que se desligam.
- **FR-029**: Nenhuma das três abas DEVE abrir tendo um editor genérico de
  schema como conteúdo primário.

#### Aba Rules & windows

- **FR-030**: A aba Rules & windows DEVE conter a criação de regra, de janela
  de congelamento e de teto de gasto.
- **FR-031**: A lista de regras DEVE ser apresentada em ordem de resolução.
- **FR-032**: A seção de simulação DEVE ter título próprio.
- **FR-033**: A seção de simulação DEVE trazer uma linha que diz o que ela
  responde.
- **FR-034**: A simulação DEVE ser alcançada por um único CTA primário; os três
  controles concorrentes de hoje convergem num fluxo só.
- **FR-035**: Salvar uma regra DEVE continuar exigindo que o efeito simulado
  tenha sido visto para a entrada corrente.
- **FR-036**: O CTA do empty state de Rules DEVE nomear a ação que executa.
- **FR-037**: A lista de regras DEVE ser a região que rola quando um nó acumula
  regras, preservando o orçamento da aba.

#### Override temporário

- **FR-038**: O override NÃO DEVE ocupar espaço permanente no corpo de nenhuma
  aba.
- **FR-039**: Um botão no cabeçalho, rotulado como override temporário, DEVE
  abrir o painel lateral.
- **FR-040**: O painel DEVE pedir nome, nível, razão e duração.
- **FR-041**: O rótulo do campo de razão DEVE declarar que ela é registrada no
  audit.
- **FR-042**: Sem nenhum override ativo, o painel DEVE afirmá-lo em texto.
- **FR-043**: Com override ativo, o painel DEVE mostrá-lo com nome, nível,
  razão e expiração, e permitir revogá-lo.
- **FR-044**: Conceder e revogar um override DEVEM entrar no registro de
  auditoria com nome, nível, razão e expiração.
- **FR-045**: Com um override ativo, o subtítulo DEVE mostrar a postura que
  vigora e declarar que ela vem de um override com prazo.

#### Paridade, permissões e vocabulário

- **FR-046**: Todo campo de configuração que o mapa de paridade atribui a esta
  tela DEVE continuar alcançável, dentro de exatamente uma das três abas.
- **FR-047**: A verificação de paridade DEVE falhar nomeando o campo quando um
  deles perde o seu controle.
- **FR-048**: O conjunto de campos declarados sem controle NÃO DEVE crescer por
  causa desta feature.
- **FR-049**: Um endereço com âncora de seção do editor aposentado DEVE
  aterrissar na aba que possui aquela seção.
- **FR-050**: Um leitor sem permissão de escrita DEVE ver valores, origens e
  regras nas três abas, e não receber formulários nem o botão de override.
- **FR-051**: A rota DEVE passar na suíte transversal sem nenhuma exceção
  declarada, incluindo os bans de vocabulário.
- **FR-052**: Todo texto novo DEVE nascer nos dois catálogos de idioma juntos.

### Key Entities

- **Aba**: uma das três perguntas — o que pode sozinho, quando não pode, o que
  sempre vale; identificada na URL, dona dos campos que apresenta.
- **Postura**: o nível vigente de autonomia do nó, com origem (salvo, herdado
  ou concedido por override).
- **Regra de autonomia**: escopo, nível, ordem de resolução.
- **Janela de congelamento**: nome, início, fim, razão.
- **Teto**: nome, limite, unidade de contagem.
- **Guardrail**: nome de exibição, valor efetivo, origem, editabilidade
  declarada pelo schema.
- **Override temporário**: nome, nível, razão, expiração, quem concedeu.
- **Mapa de paridade**: campo de configuração → tela responsável, verificado
  por contrato.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Cada uma das três abas mede no máximo 1.5 viewport de altura em
  um viewport de 1920×1080 declarado pelo próprio teste — contra os **2065px
  (1.91 viewports)** da página única de hoje. *(Número remedido em 2026-08-18:
  a spec dizia 2026px / 2.3 viewports, escrito antes de as features anteriores
  mexerem nesta tela. Os 2065px são maiores porque o fixture de override desta
  onda faz a linha de override renderizar pela primeira vez — a altura real de
  partida das fatias de abas é esta.)*
- **SC-002**: Zero células vazias na coluna de valor, contadas nas duas
  aparições da tabela de guardrails. *(Remedido em 2026-08-18: a spec dizia
  "contra 12 células vazias hoje"; hoje são **zero**, nas duas aparições —
  tabela principal 6 linhas, seção avançada 4 linhas. A feature que entregou a
  coluna de valor fechou isso estruturalmente: `EffectiveFieldsTable` lança
  exceção se qualquer linha vier com valor ou origem em branco, então o estado
  não é incidental e não pode regredir em silêncio. As tarefas ligadas a este
  critério são de **verificação**, não de implementação: provam que a
  propriedade se mantém depois do corte em abas.)*
- **SC-003**: 100% dos campos que o mapa de paridade atribui a esta tela
  continuam alcançáveis numa aba dona, e a contagem de campos sem controle não
  aumenta.
- **SC-004**: Zero parágrafos conceituais entre o título da tela e o primeiro
  controle, contra três hoje.
- **SC-005**: Zero CTAs na rota cujo destino difere do rótulo, contra um hoje.
- **SC-006**: Exatamente um CTA primário na seção de simulação, contra três
  botões concorrentes hoje.
- **SC-007**: Zero pixels do corpo da página reservados a override quando
  nenhum painel está aberto, contra um terço da largura hoje.
- **SC-008**: A suíte transversal roda nesta rota com zero exceções declaradas
  — nenhum teste marcado para falhar ou pular por causa dela. *(Remedido em
  2026-08-18: a exceção de orçamento de rolagem desta rota **já não existe** —
  `EXCEPTIONS` guarda apenas `/settings/alert-intake`. Esta rota está em
  `SCROLL_BUDGET_MEASURED_ELSEWHERE` e delega a `scroll-budget.spec.ts`, que a
  mede e passa. Fica uma ambiguidade a resolver por quem escrever a primeira
  tarefa: o arquivo faz um `test.skip` literal para esta rota, mas o motivo é
  "medida em outro lugar", não "isenta" — as outras duas regras rodam de
  verdade e passam.)*
- **SC-009**: Conceder um override temporário exige quatro campos e nenhuma
  navegação para fora da rota.
- **SC-010**: Um operador encontra o valor efetivo de qualquer guardrail sem
  abrir outra tela e sem expandir um editor de schema.

## Assumptions

- A 020 entrega o componente de tabela de configuração com a coluna de valor
  preenchida e a suíte transversal executável; esta feature os consome em vez
  de reimplementá-los.
- A 030 precede esta feature na ordem de execução da onda e é de onde vem o
  vocabulário humano dos grupos de política. Se algum nome de exibição ainda
  não existir quando esta feature começar, ela o cria na aba dona — não espera.
- A hierarquia de configuração e o seletor de nó permanecem como estão; esta
  feature não muda a semântica de resolução, só onde ela é lida.
- A capacidade de simulação existente é preservada integralmente; o que muda é
  a hierarquia visual e o número de portas de entrada.
- O parâmetro de aba na URL segue o padrão já usado por outras telas do
  produto, sem inventar um esquema novo.
- Os níveis de postura continuam sendo declarados pelo deployment, não
  enumerados pela tela.

## Dependencies

- **020** (declarada): componente de tabela com coluna de valor preenchida,
  contagem única e a suíte transversal executável.
- **030** (ordem da onda): vocabulário humano para os grupos de política.
- O mapa de paridade estabelecido pela v5 (feature de aposentadoria do editor
  cru) é insumo desta feature e precisa continuar verde ao fim dela.

## Gates que esta feature toca

- Contrato do mapa de paridade campo → tela (o que impede um campo órfão).
- Suíte transversal de regras de tela, na rota desta feature, sem exceções.
- Medição do orçamento de rolagem, agora também por aba.
- Guarda de constantes: o orçamento por aba é constante nomeada no módulo dono.
- Registro de telas para captura visual: a entrada desta rota está pendente
  justamente por altura e campos descobertos, e é esta feature que a resolve.
- Paridade dos catálogos de idioma.
- A verificação completa do repositório (lint, formato, tipos, contratos de
  importação, protocolos, dependências e a suíte).
