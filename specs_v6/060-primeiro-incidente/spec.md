# Feature Specification: O primeiro incidente ponta a ponta

**Feature Branch**: `feat/v6-060-primeiro-incidente`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "Um alerta real do cluster atravessa o produto inteiro
e termina numa timeline que um humano lê e decide. O runtime de investigação deixa
de ser suposição e vira pré-condição verificável; o Alertmanager da stack entrega
no NinjaSRE autenticado por delivery token; os cenários T1 (sintético) e T2 (falha
real controlada) são roteiros reexecutáveis; a ação de remediação é proposta, com
blast radius e postura visíveis, e espera decisão."

**Referência visual (DoD)**: [../mockups/settings-v6.html#m6](../mockups/settings-v6.html#m6)
— timeline com recebimento, hipóteses, evidências com a consulta real, diagnóstico
em uma frase e entrega; cabeçalho da investigação com passos, duração e custo;
painel "Proposed action" com blast radius, postura e os dois controles de decisão.

## Pré-condições verificadas (2026-08-16 — não re-derivar)

Cada item abaixo foi confirmado no ambiente antes desta spec existir. A spec os
cita como fatos, não como hipóteses a validar.

1. O backend roda em pve02/CT254, endereço `192.168.68.74`, gateway na porta
   `8420`, publicado por release-symlink no commit `eb8c6f1`.
2. `POST /webhooks/alertmanager` responde **401** sem delivery token. O trust da
   entrega é o token, não o endereço de origem.
3. O Alertmanager real é o da stack de monitoring em `10.20.20.37`, com
   configuração em
   `/root/infra-cluster/services/monitoring/stack/alertmanager/alertmanager.yml`.
   Ele já entrega webhook para o antecessor em `10.20.20.65:9001`, com
   `send_resolved: false`. O NinjaSRE assume esse padrão de entrega, ao lado do
   receiver existente e sem substituí-lo.
4. As regras de alerta já estão ativas e disparam sozinhas: `InstanceDown`,
   `BlackboxProbeFailed` (HTTP/TCP/DNS), `RedisInstanceDown`, `SSLCertExpiry`,
   `ProxmoxClusterApiDown` / `ProxmoxNodeApiDown`.
5. As vítimas aprovadas pelo operador para o cenário T2 são `streamlink-webui`
   (CT139) ou `bazarr` (CT103). A reversão do cenário é `pct start` do CT parado.
6. O dashboard do deployment mostra hoje **2 incidentes mortos** na mensagem "este
   deployment não tem runtime com que investigar", parados há cinco dias.
7. A postura é **propose-only de ponta a ponta**: nada executa sem aprovação
   humana registrada, inclusive durante o cenário T2.

Três fatos sobre o produto, igualmente verificados, delimitam o tamanho do
trabalho:

8. O produto já decide "este deployment tem runtime?" perguntando ao objeto que a
   composição construiu, e não lendo a configuração — três superfícies (o passo do
   setup, o self-check e a rota que inicia investigação) compartilham essa
   resposta.
9. Não existe hoje nenhuma composição de runtime no repositório: o único
   implementador do contrato de investigação é o recusador que nomeia o que falta.
   Portanto "fornecer um runtime" é trabalho de produto seguido de trabalho de
   deploy, não só de deploy.
10. A timeline do incidente registra hoje **ciclo de vida** (aberto, correlacionado,
    assunto adicionado, estado mudou, run iniciado, ação tomada, escalado,
    suprimido, encerrado) e **não registra raciocínio**. Recebimento com rótulos,
    hipóteses, evidência com a consulta, diagnóstico e entrega são registros que
    ainda não existem.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - O alerta do cluster chega ao produto (Priority: P1)

O operador emite um delivery token de finalidade única em Alert intake, configura
o Alertmanager da stack para entregar no NinjaSRE, e a partir daí todo alerta que
casa a rota de intake aparece no produto sem intervenção manual.

**Why this priority**: Enquanto o alerta não entra, nada mais desta feature pode
ser observado. É a primeira metade da frase "o produto é usado, não só
configurado".

**Independent Test**: Emitir o token, aplicar o receiver, disparar um alerta
sintético pela API do Alertmanager e conferir a entrega na tela de Alert intake e
o incidente em `/incidents` — sem tocar em nenhuma outra parte do produto.

**Acceptance Scenarios**:

1. **Given** um delivery token emitido e configurado no Alertmanager, **When** a
   stack entrega uma notificação no webhook, **Then** a entrega é aceita e aparece
   na tela de Alert intake com origem, horário, resultado e amostra mascarada.
2. **Given** uma entrega aceita que casa uma regra de intake, **When** ela é
   processada, **Then** um incidente abre em `/incidents` com título legível e o
   recurso afetado resolvido como assunto.
3. **Given** a mesma notificação reentregue pelo Alertmanager (retry), **When** ela
   chega de novo, **Then** é reconhecida como duplicada, respondida com sucesso e
   não abre um segundo incidente.
4. **Given** uma requisição sem token, ou com um token revogado, **When** ela
   chega, **Then** é recusada com 401, a recusa é registrada com o motivo, e nenhum
   incidente é aberto.

### User Story 2 - O deployment tem com o que investigar (Priority: P1)

O operador vê, no próprio produto, que este deployment tem runtime de investigação
— e investigações param de morrer antes de começar.

**Why this priority**: É a pré-condição que hoje mata 2 incidentes de 2. Sem ela a
timeline do M6 não tem o que desenhar.

**Independent Test**: Ler o passo de runtime no setup antes e depois de fornecer o
runtime, e iniciar uma investigação nos dois estados.

**Acceptance Scenarios**:

1. **Given** um deployment sem runtime, **When** o operador abre o setup, **Then**
   o passo de runtime aparece pendente com a consequência declarada, e iniciar uma
   investigação recusa nomeando o que falta — sem derrubar as demais telas.
2. **Given** um runtime fornecido e efetivamente composto, **When** o setup é lido,
   **Then** o passo de runtime aparece concluído, e essa é a mesma resposta que a
   rota de investigação dá.
3. **Given** runtime presente, **When** um incidente novo abre a partir de uma
   entrega, **Then** uma investigação inicia e o incidente passa a referenciar o
   run correspondente.
4. **Given** um runtime nomeado que não pode ser carregado, **When** o processo
   sobe, **Then** a falha nomeia a configuração a corrigir e o produto continua se
   comportando como um deployment sem runtime — nunca como um que tem.

### User Story 3 - A timeline conta o raciocínio, não só o desfecho (Priority: P1)

Em `/incidents/[id]` o operador lê, na ordem, o que chegou, o que se cogitou, o que
se consultou, o que se concluiu e o que foi entregue — cada passo com hora, e o
conjunto com contagem de passos, duração e custo.

**Why this priority**: É o mockup M6, e é o que transforma um incidente numa peça
que alguém consegue auditar às 3 da manhã.

**Independent Test**: Abrir um incidente já investigado e ler a página inteira sem
abrir nenhuma outra tela nem consultar quem operou.

**Acceptance Scenarios**:

1. **Given** um incidente investigado, **When** a página abre, **Then** o cabeçalho
   traz a trilha "Incidents › <título>", o título do incidente, o chip do estado do
   incidente e o chip do estado da investigação.
2. **Given** o mesmo incidente, **When** a página abre, **Then** o subtítulo nomeia
   a regra de origem, a fonte da entrega, o instante de início, a zona e o host ou
   contêiner afetado.
3. **Given** a investigação concluída, **When** o cartão de investigação é lido,
   **Then** seu título carrega a contagem de passos, a duração e o custo.
4. **Given** a timeline, **When** ela é lida de cima para baixo, **Then** os passos
   aparecem na ordem alerta recebido → hipóteses → evidências → diagnóstico →
   entrega, cada um com a hora em que ocorreu.
5. **Given** o passo de recebimento, **When** lido, **Then** mostra os rótulos que
   chegaram e nomeia o token de entrega que autenticou a notificação.
6. **Given** um passo de evidência, **When** lido, **Then** mostra a consulta
   efetivamente executada e o resultado obtido, e não apenas a conclusão tirada
   deles.
7. **Given** um incidente sem investigação (runtime ausente, ou investigação ainda
   não iniciada), **When** a página abre, **Then** o cartão de investigação mostra
   um estado vazio que nomeia a pendência e o caminho para resolvê-la — nunca um
   cartão em branco.

### User Story 4 - A ação proposta declara o risco e espera decisão (Priority: P1)

O operador lê o que o produto propõe fazer, quanto isso alcança e sob que postura,
e decide ali mesmo.

**Why this priority**: É onde o Artigo III do produto fica visível no momento em
que importa. Uma proposta sem blast radius é uma decisão pedida no escuro.

**Independent Test**: Abrir um incidente com ação proposta, aprovar num caso e
rejeitar noutro, e conferir os dois registros no audit.

**Acceptance Scenarios**:

1. **Given** uma investigação que concluiu com uma remediação cabível, **When** a
   página do incidente abre, **Then** existe um cartão "Proposed action" com o chip
   de estado da decisão.
2. **Given** o cartão, **When** lido, **Then** a ação é dita em uma frase que nomeia
   o efeito pretendido, seguida do blast radius (quantos recursos, em que zona, com
   que criticidade) e da postura vigente com a frase de que nada executa sem o
   operador.
3. **Given** o cartão, **When** o operador decide, **Then** há exatamente dois
   controles — aprovar e executar, e rejeitar — e nenhum deles executa antes da
   decisão.
4. **Given** uma rejeição, **When** submetida sem motivo, **Then** é recusada; com
   motivo, é registrada.
5. **Given** qualquer uma das duas decisões, **When** tomada, **Then** ela aparece
   no audit log com autor, ação, assunto e resultado.

### User Story 5 - Os dois cenários são reexecutáveis (Priority: P2)

T1 (alerta sintético, risco zero) e T2 (falha real controlada) existem como
roteiros que outra pessoa executa do começo ao fim sem perguntar nada a quem os
escreveu.

**Why this priority**: Um cenário executado uma vez prova o dia; um roteiro prova
todos os dias seguintes. É também como a onda demonstra o DoD sem depender de
quem estava na sala.

**Independent Test**: Entregar o roteiro a alguém que não participou da feature e
observar a execução de T1 sem assistência.

**Acceptance Scenarios**:

1. **Given** o roteiro T1, **When** executado, **Then** produz um incidente com
   timeline completa e um relatório, e a reversão declarada é "nenhuma" porque nada
   real foi derrubado.
2. **Given** o roteiro T2 e a janela combinada com o operador, **When** executado,
   **Then** o alerta dispara de verdade, o diagnóstico nomeia que o contêiner está
   parado, a ação proposta é religá-lo, e a reversão do cenário está escrita no
   próprio roteiro.
3. **Given** qualquer um dos roteiros, **When** lido, **Then** nenhum segredo
   aparece nele — token, chave ou credencial são referenciados por onde buscá-los,
   nunca transcritos.

### Edge Cases

- **Rede da zona de infraestrutura para a LAN bloqueada**: a stack em `10.20.20.37`
  não alcança `192.168.68.74:8420`. Nenhuma entrega chega, e o produto não pode
  inventar uma. A tela de Alert intake mostra a origem como configurada e **sem
  entrega recebida**, com o instante da última entrega vazio — nunca como uma fonte
  saudável. O roteiro de T1 falha no primeiro passo, com a verificação de rota
  nomeada como a coisa a consertar, e o rollback do receiver está declarado.
- **Token revogado depois de configurado**: a entrega seguinte é recusada com 401 e
  registrada com o motivo; nenhum incidente abre; a tela de Alert intake mostra a
  recusa em vez de silêncio, para que a revogação apareça como causa e não como
  ausência de alertas.
- **Alerta duplicado**: o Alertmanager reentrega a mesma notificação em cada
  intervalo de repetição. A segunda entrega é reconhecida como duplicada,
  respondida com sucesso, registrada como duplicada e não abre segundo incidente
  nem inicia segunda investigação.
- **Notificação de resolução**: `send_resolved` está desligado no receiver
  existente. Se ela vier, a resolução é uma entrega **diferente** da que abriu o
  incidente (mesmo grupo, status distinto) e registra o encerramento no incidente
  correspondente — nunca é descartada como repetição da abertura.
- **Runtime ausente**: iniciar investigação recusa nomeando a pendência, o
  incidente permanece aberto com o cartão de investigação em estado vazio que
  aponta o passo do setup, e o dashboard nomeia a pendência em vez de dizer que
  está investigando.
- **Runtime presente, provider degradado**: a investigação inicia e pode concluir
  com menos evidência. O produto reporta a degradação com a palavra canônica
  (Degradada), não como falha, e o diagnóstico que não se sustenta em evidência
  fica registrado como hipótese.
- **Grupo com vários alertas na mesma notificação**: a entrega é uma, os alertas
  são vários. A correlação decide se abrem um incidente ou mais de um, e a decisão
  aparece na timeline como correlação, não como incidentes duplicados sem
  explicação.
- **O contêiner é religado à mão antes da decisão**: a ação proposta continua
  aguardando decisão e não vira executada por conta própria; aprovar depois disso
  encontra o recurso já no estado desejado e registra esse resultado em vez de
  fingir que agiu.
- **Investigação sem evidência suficiente**: nenhuma frase é apresentada como
  diagnóstico. O que houver é registrado como hipótese, e o cartão de ação proposta
  não aparece — propor uma remediação sobre evidência inexistente é o pior desfecho
  possível desta tela.
- **Custo ou duração indisponíveis**: o cabeçalho da investigação mostra o que
  existe e omite o que não existe, sem zeros fabricados.

## Requirements *(mandatory)*

### Functional Requirements

#### Entrega autenticada do Alertmanager

- **FR-001**: A tela de Alert intake DEVE oferecer a emissão de um delivery token
  de finalidade única, rotulado como token de entrega de alertas, cujo escopo é
  exclusivamente a permissão de entrega.
- **FR-002**: O valor do token DEVE ser exibido uma única vez, no momento da
  emissão, e não DEVE ser recuperável depois por nenhuma tela.
- **FR-003**: O endpoint de entrega do Alertmanager DEVE recusar com 401 toda
  notificação sem token válido.
- **FR-004**: Um token revogado DEVE ser recusado na entrega seguinte, com o mesmo
  desfecho de um token ausente, sem abrir incidente e sem erro de servidor.
- **FR-005**: Toda entrega recusada DEVE ser registrada com o motivo da recusa.
- **FR-006**: Toda entrega aceita DEVE aparecer na tela de Alert intake com origem,
  horário, resultado e amostra mascarada do corpo.
- **FR-007**: O produto DEVE aceitar o corpo de notificação agrupada do Alertmanager
  na versão que a stack envia, sem exigir formato próprio nem transformação
  intermediária.
- **FR-008**: A reentrega da mesma notificação DEVE ser reconhecida como duplicada,
  respondida com sucesso, registrada como duplicada e NÃO DEVE abrir um segundo
  incidente.
- **FR-009**: A notificação de resolução DEVE ser tratada como entrega distinta da
  que abriu o incidente e DEVE registrar o encerramento no incidente correspondente.
- **FR-010**: A tela de Alert intake DEVE mostrar, por fonte, o instante da última
  entrega recebida, de modo que uma rota de rede bloqueada apareça como ausência de
  entregas e não como configuração concluída.

#### Runtime de investigação

- **FR-011**: O deployment DEVE poder compor um runtime de investigação de primeira
  classe — o loop canônico do produto — sem que o operador escreva código.
- **FR-012**: A pergunta "este deployment pode investigar?" DEVE continuar sendo
  respondida pelo objeto que a composição construiu, nunca pela leitura da
  configuração, de modo que uma configuração que não carregou responda "não".
- **FR-013**: Enquanto não houver runtime, iniciar uma investigação DEVE recusar
  com uma mensagem que nomeia o que falta e a consequência, e as demais superfícies
  do produto DEVEM continuar funcionando.
- **FR-014**: O passo de runtime do setup DEVE ficar concluído quando o runtime
  estiver composto e pendente quando não estiver, servido pela mesma fonte que a
  rota de investigação consulta.
- **FR-015**: Nenhuma superfície DEVE apresentar como "investigando" um incidente
  cuja investigação não pôde iniciar; a pendência DEVE ser nomeada.
- **FR-016**: O texto que o operador lê sobre o runtime NÃO DEVE conter nome de
  variável de ambiente nem instrução de deploy; a instrução vive na documentação de
  operação e na recusa que o processo registra.

#### Registro da investigação

- **FR-017**: A investigação DEVE registrar o recebimento do alerta com os rótulos
  que chegaram e a identidade da entrega que o trouxe.
- **FR-018**: A investigação DEVE registrar as hipóteses consideradas,
  explicitamente, antes de qualquer consulta a integração.
- **FR-019**: Cada evidência DEVE registrar a consulta efetivamente executada e o
  resultado obtido, além da conclusão tirada deles.
- **FR-020**: O diagnóstico DEVE ser registrado como uma frase e DEVE referenciar
  as evidências que o sustentam.
- **FR-021**: Uma conclusão sem evidência que a sustente DEVE ser registrada como
  hipótese e NÃO DEVE ser apresentada como diagnóstico.
- **FR-022**: A entrega do relatório DEVE ser registrada nomeando os destinos para
  onde foi.
- **FR-023**: A investigação DEVE registrar contagem de passos, duração total e
  custo acumulado, legíveis junto do incidente.
- **FR-024**: Todo passo registrado DEVE carregar o instante em que ocorreu.
- **FR-025**: Os registros de raciocínio DEVEM conviver com os registros de ciclo de
  vida já existentes na mesma timeline, sem substituí-los.

#### A tela do incidente (M6)

- **FR-026**: A página DEVE apresentar a trilha "Incidents › <título do incidente>".
- **FR-027**: O título da página DEVE ser o título do incidente.
- **FR-028**: O cabeçalho DEVE trazer o chip do estado do incidente.
- **FR-029**: O cabeçalho DEVE trazer o chip do estado da investigação.
- **FR-030**: O subtítulo DEVE nomear a regra de origem do alerta.
- **FR-031**: O subtítulo DEVE nomear a fonte da entrega.
- **FR-032**: O subtítulo DEVE trazer o instante de início.
- **FR-033**: O subtítulo DEVE nomear a zona e o host ou contêiner afetado.
- **FR-034**: A página DEVE usar duas colunas: a investigação à esquerda; a ação
  proposta e a trilha de evidências à direita.
- **FR-035**: O título do cartão de investigação DEVE carregar a contagem de passos.
- **FR-036**: O título do cartão de investigação DEVE carregar a duração.
- **FR-037**: O título do cartão de investigação DEVE carregar o custo.
- **FR-038**: A timeline DEVE apresentar os passos na ordem alerta recebido →
  hipóteses → evidências → diagnóstico → entrega.
- **FR-039**: O passo de recebimento DEVE mostrar os rótulos do alerta em tipografia
  monoespaçada.
- **FR-040**: O passo de recebimento DEVE nomear o token de entrega que autenticou a
  notificação.
- **FR-041**: O passo de hipóteses DEVE listar as hipóteses consideradas.
- **FR-042**: Cada passo de evidência DEVE mostrar, em bloco próprio, a consulta
  executada e o resultado.
- **FR-043**: O diagnóstico DEVE aparecer como uma frase.
- **FR-044**: O passo de entrega DEVE nomear os destinos e ser apresentado com peso
  visual reduzido em relação aos demais.
- **FR-045**: Cada passo DEVE mostrar a hora em que ocorreu.
- **FR-046**: A página DEVE trazer um cartão de ação proposta com o chip de estado
  da decisão.
- **FR-047**: A ação proposta DEVE ser dita em uma frase que nomeia o efeito
  pretendido sobre o recurso.
- **FR-048**: O cartão DEVE declarar o blast radius: quantos recursos, em que zona,
  com que criticidade.
- **FR-049**: O cartão DEVE declarar a postura vigente e afirmar que nada executa
  sem o operador.
- **FR-050**: O cartão DEVE oferecer exatamente dois controles de decisão: aprovar e
  executar, e rejeitar.
- **FR-051**: A página DEVE trazer um cartão de trilha de evidências com o caminho
  para o run completo.
- **FR-052**: Cada cartão sem conteúdo DEVE mostrar um estado vazio que nomeia a
  pendência e o caminho para resolvê-la.
- **FR-053**: A página NÃO DEVE exibir identificadores crus onde existe nome de
  exibição, e DEVE usar o vocabulário canônico de estado.
- **FR-054**: A página DEVE caber em no máximo dois viewports de 1080p.

#### Decisão

- **FR-055**: Aprovar DEVE registrar a decisão, o decisor e o instante antes de
  qualquer efeito.
- **FR-056**: Uma ação acima do nível de leitura DEVE ter plano de reversão
  registrado antes de executar.
- **FR-057**: Rejeitar DEVE exigir um motivo e registrar a decisão com ele.
- **FR-058**: As duas decisões DEVEM aparecer no audit log com autor, ação, assunto
  e resultado.
- **FR-059**: Nenhuma ação acima do nível de leitura DEVE executar sem decisão
  humana registrada, inclusive durante o cenário T2.

#### Cenários

- **FR-060**: T1 e T2 DEVEM existir como roteiros reexecutáveis, cada um com
  pré-condições, comandos, evidência esperada e reversão.
- **FR-061**: O roteiro de T2 DEVE nomear a vítima aprovada e a reversão manual, e
  DEVE exigir janela combinada com o operador antes de executar.
- **FR-062**: Nenhum roteiro DEVE transcrever segredo; token, chave e credencial são
  referenciados por onde obtê-los.
- **FR-063**: A verificação de rota da zona de infraestrutura até o gateway DEVE ser
  o primeiro passo do roteiro T1, e sua falha DEVE interromper o roteiro nomeando o
  que consertar.

### Key Entities

- **Delivery token**: credencial de finalidade única para entrega de alertas —
  identidade, finalidade, escopo de entrega, instante de emissão, estado de
  revogação. Valor visível uma vez.
- **Entrega**: uma notificação recebida — origem, instante, identidade da entrega,
  desfecho (aceita, duplicada, recusada, descartada por regra), amostra mascarada.
- **Incidente**: o que está errado — título, estado, severidade, assunto (recurso),
  chave de correlação, instante de abertura, run associado.
- **Passo de investigação**: um momento do raciocínio — tipo (recebimento,
  hipóteses, evidência, diagnóstico, entrega), instante, ator, conteúdo e, para
  evidência, a consulta executada e o resultado.
- **Ação proposta**: o que se propõe fazer — efeito em uma frase, recurso alvo,
  blast radius, postura vigente, plano de reversão, estado da decisão.
- **Decisão**: aprovação ou rejeição — decisor, instante, motivo (obrigatório na
  rejeição), resultado da execução quando houver.
- **Roteiro de cenário**: T1 ou T2 — pré-condições, comandos, evidência esperada,
  reversão, e quem precisa estar ciente antes.

## Success Criteria *(mandatory)*

- **SC-001**: Uma notificação emitida no Alertmanager da stack vira um incidente
  visível em `/incidents` em menos de 60 segundos, sem nenhuma intervenção manual
  entre a emissão e a tela.
- **SC-002**: Cada um dos dois cenários produz um incidente com os cinco tipos de
  passo presentes na timeline e uma ação proposta aguardando decisão (hoje: zero,
  as investigações não iniciam).
- **SC-003**: O produto reporta runtime presente, e nenhum incidente aberto durante
  a janela de validação morre por falta de runtime (hoje: 2 de 2 mortos assim).
- **SC-004**: 100% dos passos de evidência da timeline exibem a consulta que os
  produziu (hoje: 0%, porque a timeline não registra evidência).
- **SC-005**: Zero ações acima do nível de leitura executadas sem decisão humana
  registrada, medido no audit ao fim dos dois cenários.
- **SC-006**: A página do incidente cabe em no máximo dois viewports de 1080p.
- **SC-007**: Uma pessoa que não participou da feature executa o roteiro T1 do
  começo ao fim, sem assistência, em menos de 10 minutos.
- **SC-008**: 100% das entregas sem token válido são recusadas, e nenhuma delas
  abre incidente.
- **SC-009**: A mesma notificação reentregue pelo menos três vezes durante T1
  produz exatamente um incidente.
- **SC-010**: No cenário T2, o diagnóstico nomeia que o contêiner está parado e a
  ação proposta é religar exatamente o contêiner derrubado.
- **SC-011**: Um operador identifica, lendo apenas a página do incidente, qual
  consulta sustentou cada evidência e qual o alcance da ação proposta — sem abrir
  outra tela.

## Assumptions

- O receiver novo do Alertmanager convive com o receiver existente do antecessor;
  esta feature não desliga a entrega atual para `10.20.20.65:9001`.
- `send_resolved` permanece desligado no receiver existente; o comportamento de
  resolução é especificado porque a rota nova pode ligá-lo, não porque a atual o
  liga.
- O runtime composto usa o loop canônico do produto. Runtimes alternativos ficam
  fora desta feature.
- Os destinos de entrega de relatório disponíveis são os que o catálogo pós-corte
  embarca; nenhum destino novo nasce aqui.
- A correlação de alertas em incidentes é a que o produto já faz; esta feature
  torna a decisão visível na timeline, não muda a regra.
- O custo por investigação é o que o provider verificado reporta; esta feature o
  exibe, não o calcula de forma nova.

## Dependencies

- **001 — escopo validável**: o catálogo pós-corte e o intake enxuto definem quais
  fontes existem e quais integrações a investigação pode consultar.
- **010 — provider out-of-the-box**: sem provider verificado com tool-calling
  forçado, o runtime compõe mas não conclui; o estado espelhado (passed ·
  degraded · failed) é o que esta feature reporta quando a investigação degrada.
- **050 — integrations em slide-over e intake enxuto**: a tela de Alert intake com
  a cadeia visível é onde o delivery token é emitido e onde a entrega aparece.

## Gates tocados

- Suíte transversal do console (bans de vocabulário, orçamento de rolagem,
  contagem única, coluna de valor preenchida), rodada na fronteira desta feature.
- Testes de contrato do console contra a API que ele consome.
- Testes de contrato do gateway para as rotas de entrega e de incidente.
- Cobertura de contrato por capacidade, para a capacidade de remediação proposta.
- Registro de telas visuais e captura deliberada de baseline para a página do
  incidente.
- `make verify` completo (lint, formatação, tipos, contratos de import, guardas de
  constantes/protocolos/dependências e a suíte).

## Out of scope

- Execução autônoma de remediação, allow-list de ações automáticas e kill switch:
  esta feature é propose-only de ponta a ponta.
- Integração PostgreSQL e Proxmox Backup Server (roadmap; o cluster não tem PBS).
- Novos destinos de notificação além dos já embarcados.
- Aprendizado a partir do incidente (memória episódica, síntese de estratégia): o
  incidente é registrado, e o que se faz com ele depois é outra feature.
- Substituição do receiver existente do antecessor no Alertmanager.
