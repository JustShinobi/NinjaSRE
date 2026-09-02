# Feature Specification: Investigação robusta, memória operacional e eficiência de tokens

**Feature Branch**: `feat/v9-000-investigacao-robusta`

**Created**: 2026-09-02

**Status**: Draft

**Input**: User description: "Transformar a auditoria do staging em uma spec voltada a
deixar os fluxos de incidentes e investigações mais robustos e eficientes em tokens;
adicionar a aba Postmortem em Conhecimento; permitir transformar incidentes e
investigações em postmortems; e consultar postmortems anteriores para correlacionar e
investigar problemas recorrentes."

## Objetivo do produto e problema observado

O NinjaSRE existe para investigar incidentes de produção, produzir causas raiz apoiadas
por evidência, aprender com cada investigação e provar que o aprendizado melhora o
resultado. Esta feature fecha lacunas observadas no staging que impedem esse ciclo:

- um alerta recorrente pode iniciar repetidamente investigações completas sobre o mesmo
  incidente, mesmo quando a causa já foi estabelecida;
- episódios anteriores são consultados, mas tarde demais para reduzir materialmente o
  plano, as chamadas e os tokens da investigação;
- conclusões equivalentes geram muitos episódios semelhantes e até desfechos
  contraditórios, sem uma verdade curada que o operador possa revisar;
- o estado técnico de um run concluído é apresentado como sucesso mesmo quando nenhum
  diagnóstico foi produzido;
- referências de evidência locais a um run podem ser confundidas com referências de
  outros runs, comprometendo reconstrução e auditoria;
- capacidades sabidamente indisponíveis continuam sendo oferecidas e chamadas;
- o operador não possui um fluxo direto para transformar o trabalho já feito em um
  postmortem reutilizável.

A feature transforma alertas, incidentes, investigações, episódios e postmortems em um
ciclo operacional único. Repetições continuam visíveis e auditáveis, mas deixam de
produzir trabalho e consumo equivalentes a um problema novo quando nenhuma evidência
material mudou.

## Baseline verificado no staging

Os critérios desta feature partem da auditoria somente leitura realizada em 2026-09-02:

- 180 incidentes, 789 investigações, 6.219 chamadas de capacidades e 75.051.924 tokens;
- um único alerta iniciou 111 investigações, consumiu 23.190.663 tokens e realizou
  1.286 chamadas;
- um segundo alerta iniciou 104 investigações e consumiu 15.133.321 tokens;
- os dois alertas concentraram aproximadamente 51% de todos os tokens observados;
- 1.372 chamadas falharam, das quais 1.089 eram indisponibilidades determinísticas;
- 146 runs marcados como completados não possuíam turnos ou chamadas;
- 525 runs completados não produziram episódio, e 114 produziram episódio inconclusivo;
- 253 episódios existiam, com uma assinatura repetida 54 vezes e outra 44 vezes;
- 11 estratégias existiam, das quais 7 estavam obsoletas;
- 12 incidentes permaneciam como “investigando”, com 294 runs encerrados anexados e
  nenhum run ainda em execução;
- 6.183 de 6.237 referências persistidas de evidência apontavam para um registro atribuído
  a outro run;
- a base documental possuía zero documentos e zero trechos pesquisáveis.

## Escopo

### Incluído

- correlação durável de alertas, incidentes, ocorrências e runs;
- distinção entre repetição sem mudança, recorrência conhecida e problema novo;
- caminhos de investigação completa e de validação curta de recorrência;
- eficiência de contexto, tokens, capacidades e evidências;
- integridade e veracidade dos estados e métricas de investigação;
- criação, revisão, publicação, consulta, versionamento e arquivamento de postmortems;
- nova aba **Postmortem** em Conhecimento;
- ações de postmortem nas áreas de Incidentes e Investigações;
- uso de postmortems publicados na correlação e no raciocínio de novas investigações;
- consolidação e rastreabilidade entre episódio bruto, postmortem curado e estratégia;
- medição com ablação do efeito de memória, postmortems e caminhos de recorrência.

### Fora do escopo

- alterar os níveis de autonomia ou permitir novas ações em produção;
- executar automaticamente ações corretivas descritas em postmortems;
- substituir episódios, documentos ou topologia por postmortems;
- publicar postmortems para fora da instalação do operador;
- transformar a área de postmortems em um gerenciador geral de projetos ou tarefas;
- adicionar novos fornecedores de modelos ou integrações externas como requisito desta
  feature.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Uma repetição não vira uma nova investigação completa (Priority: P1)

Como operador, quando o mesmo alerta continua disparando sem mudança material, quero que
o NinjaSRE registre cada ocorrência no incidente já conhecido e reutilize o diagnóstico
válido, para não repetir a mesma investigação e ainda preservar a linha do tempo completa.

**Why this priority**: a repetição observada é a maior fonte de desperdício e contradiz a
promessa de aprender com investigações anteriores.

**Independent Test**: disparar simultaneamente e depois periodicamente o mesmo alerta,
mantendo recurso, condição e evidência estáveis; verificar que existe uma única
investigação completa, todas as ocorrências estão registradas e o operador consegue abrir
o diagnóstico reutilizado.

**Acceptance Scenarios**:

1. **Given** um incidente aberto com uma investigação completa anexada, **When** o mesmo
   alerta volta a disparar sem mudança material, **Then** a ocorrência é anexada ao
   incidente e nenhum novo run completo é iniciado.
2. **Given** duas entregas simultâneas da mesma condição, **When** ambas são aceitas,
   **Then** somente uma pode iniciar investigação e ambas ficam registradas.
3. **Given** que o processo foi reiniciado, **When** o mesmo alerta volta a disparar,
   **Then** a decisão usa o histórico durável e não depende de memória do processo.
4. **Given** um alerta repetido com evidência materialmente diferente, **When** ele chega,
   **Then** o sistema registra a mudança e inicia ou amplia uma investigação apropriada,
   em vez de reutilizar silenciosamente uma conclusão antiga.

---

### User Story 2 - Uma recorrência conhecida usa postmortem antes do trabalho amplo (Priority: P1)

Como operador, quero que uma condição semelhante a um postmortem publicado seja
reconhecida cedo, validada contra o estado atual e investigada com um caminho curto quando
a causa realmente se repete.

**Why this priority**: o valor de uma base de conhecimento operacional não é apenas
lembrar; é reduzir o tempo e o custo da próxima ocorrência sem reduzir a confiança.

**Independent Test**: publicar um postmortem para uma falha conhecida, repetir o cenário e
verificar que o sistema encontra o postmortem, explica a associação, coleta evidência
atual mínima e evita o plano completo quando a associação é confirmada.

**Acceptance Scenarios**:

1. **Given** um postmortem publicado para o mesmo recurso e assinatura, **When** a condição
   recorre, **Then** a correlação é registrada antes da abertura de um run completo e o
   postmortem candidato é mostrado ao operador.
2. **Given** uma recorrência candidata, **When** a evidência atual confirma os fatos
   discriminantes do postmortem, **Then** o sistema conclui pelo caminho curto, citando
   evidência atual e o postmortem.
3. **Given** uma recorrência candidata, **When** a evidência atual contradiz o postmortem,
   **Then** o postmortem permanece apenas como hipótese histórica e uma investigação
   completa é iniciada.
4. **Given** múltiplos postmortems plausíveis ou contraditórios, **When** não existe um
   candidato com score de associação de pelo menos 0,80 e margem mínima de 0,10 sobre o
   segundo colocado, ou qualquer candidato possui fato discriminante contradito, **Then**
   nenhum é tratado como causa e a ambiguidade é registrada no plano.

---

### User Story 3 - Transformar incidente ou investigação em postmortem (Priority: P1)

Como operador, quero criar um postmortem a partir de um incidente ou de uma investigação,
receber um rascunho já ligado às evidências e editar o conteúdo antes de publicá-lo como
conhecimento confiável.

**Why this priority**: aprendizado automático bruto não substitui a curadoria humana da
causa, impacto, resolução e prevenção.

**Independent Test**: abrir um incidente resolvido e uma investigação completada, usar a
ação “Criar postmortem”, revisar o rascunho, publicar e encontrá-lo na aba Postmortem com
links de ida e volta para as fontes.

**Acceptance Scenarios**:

1. **Given** uma investigação com causa apoiada por evidência, **When** o operador cria um
   postmortem, **Then** o rascunho traz causa, impacto, linha do tempo, evidências,
   resolução e componentes de origem sem alterar o registro original.
2. **Given** um incidente com várias ocorrências e runs, **When** o operador cria um
   postmortem, **Then** ele pode selecionar quais ocorrências e investigações compõem o
   documento canônico.
3. **Given** que já existe postmortem para o mesmo assunto, **When** o operador tenta criar
   outro, **Then** o sistema oferece adicionar evidência, criar nova revisão ou declarar um
   postmortem distinto, sem duplicar silenciosamente.
4. **Given** uma investigação inconclusiva, **When** o operador publica seu postmortem,
   **Then** o documento permanece explicitamente inconclusivo e não inventa causa raiz.

---

### User Story 4 - Toda conclusão aponta para a evidência correta do próprio run (Priority: P1)

Como operador ou auditor, quero reconstruir qualquer conclusão e chegar exatamente às
observações que a sustentaram naquela investigação, sem colisão com evidências de outros
runs.

**Why this priority**: evidência incorretamente atribuída compromete relatório,
postmortem, aprendizado e auditoria ao mesmo tempo.

**Independent Test**: criar dois runs cujas evidências usam os mesmos identificadores
locais; verificar que citações, relatórios, postmortems e replay de cada run resolvem
somente para suas próprias observações.

**Acceptance Scenarios**:

1. **Given** dois runs contendo uma evidência local chamada `e1`, **When** qualquer um é
   reaberto ou exportado, **Then** `e1` resolve para a observação pertencente àquele run.
2. **Given** uma alegação sem evidência válida no próprio run, **When** o relatório é
   produzido, **Then** ela aparece como hipótese ou não validada, nunca como achado.
3. **Given** uma evidência citada por postmortem, **When** sua origem é aberta, **Then** o
   operador chega ao run, à chamada e à observação exatas que a produziram.

---

### User Story 5 - A investigação gasta apenas no que pode mudar a conclusão (Priority: P2)

Como responsável pelo deployment, quero que o NinjaSRE exclua capacidades indisponíveis,
evite chamadas repetidas, limite contexto histórico e pare quando a evidência já for
suficiente, para obter diagnósticos equivalentes com menos tokens e menor latência.

**Why this priority**: eficiência é parte da confiabilidade; loops caros atrasam a resposta
e tornam incidentes simultâneos mais difíceis de atender.

**Independent Test**: executar cenários novos e recorrentes com capacidades parcialmente
indisponíveis e comparar chamadas, tokens, tempo e qualidade de evidência contra o
baseline.

**Acceptance Scenarios**:

1. **Given** uma capacidade sabidamente indisponível, **When** o plano é montado, **Then**
   ela não é chamada e sua ausência é registrada uma única vez como limitação.
2. **Given** um resultado atual já presente no run, **When** o mesmo pedido é repetido sem
   mudança de parâmetros ou validade, **Then** o resultado existente é reutilizado e o
   agente é informado disso.
3. **Given** que todas as alegações necessárias possuem evidência suficiente, **When** o
   próximo passo não pode acrescentar evidência relevante, **Then** o run conclui.
4. **Given** um postmortem recuperado, **When** ele entra no contexto, **Then** somente os
   trechos necessários e suas citações são incluídos, não os transcripts históricos
   completos.

---

### User Story 6 - Operar a biblioteca de postmortems (Priority: P2)

Como operador, quero consultar, filtrar, revisar, corrigir, superseder e arquivar
postmortems na área de Conhecimento, para manter uma fonte confiável e evitar que uma
conclusão antiga continue orientando investigações.

**Why this priority**: conhecimento sem ciclo de validade acumula contradições e se torna
mais perigoso à medida que cresce.

**Independent Test**: criar postmortems com estados e componentes diferentes; buscar,
filtrar, revisar um documento, supersedê-lo e confirmar que somente versões publicadas e
vigentes orientam novas investigações.

**Acceptance Scenarios**:

1. **Given** postmortems em estados diferentes, **When** a aba Postmortem é aberta,
   **Then** o operador distingue rascunhos, publicados, supersedidos e arquivados.
2. **Given** um postmortem publicado incorreto ou antigo, **When** ele é supersedido ou
   arquivado, **Then** deixa de orientar novas investigações e o motivo permanece
   auditável.
3. **Given** um postmortem utilizado por uma investigação, **When** o operador abre o
   documento, **Then** vê onde ele foi consultado, qual influência teve e se a associação
   foi confirmada ou rejeitada.

---

### User Story 7 - Provar que o aprendizado melhorou a investigação (Priority: P2)

Como responsável pelo produto, quero comparar cenários com e sem postmortems, memória e
reutilização de recorrência, para demonstrar economia e qualidade sem depender de uma
alegação de marketing.

**Why this priority**: “aprende” só é uma propriedade do NinjaSRE quando existe uma
medição isolando sua contribuição.

**Independent Test**: executar o mesmo corpus com o mecanismo habilitado e desabilitado e
comparar correção, cobertura de evidência, tokens, chamadas e tempo até a causa.

**Acceptance Scenarios**:

1. **Given** um conjunto de cenários recorrentes e inéditos, **When** a avaliação por
   ablação é executada, **Then** o resultado separa o efeito de postmortems, memória
   episódica e estratégia.
2. **Given** uma redução de tokens acompanhada de piora de qualidade, **When** a regressão é
   avaliada, **Then** ela falha e não é reportada como melhoria.
3. **Given** uma investigação encerrada, **When** suas métricas são exibidas, **Then** o
   operador distingue término técnico, causa estabelecida, evidência suficiente,
   recorrência reutilizada e produção efetivamente recuperada.

---

### User Story 8 - Degradar honestamente quando conhecimento ou integrações faltam (Priority: P3)

Como operador, quero saber antes e durante o run quais fontes estão disponíveis, para que
o sistema não desperdice chamadas nem trate uma fonte não configurada como ausência de
problema.

**Why this priority**: uma investigação robusta precisa funcionar parcialmente sem
transformar configuração ausente em evidência negativa.

**Independent Test**: executar uma investigação sem base documental, executor de nó ou
fonte de mudanças e verificar que cada ausência aparece como limitação, nenhuma capacidade
impossível é chamada e o relatório não conclui a partir dela.

**Acceptance Scenarios**:

1. **Given** uma fonte não configurada, **When** o run começa, **Then** ela aparece como
   indisponível e não é apresentada como capacidade executável.
2. **Given** que uma fonte fica indisponível durante o run, **When** a primeira chamada
   falha por indisponibilidade, **Then** chamadas equivalentes posteriores são evitadas e a
   limitação permanece visível.
3. **Given** que contagem de tokens ou custo não está disponível, **When** o run é exibido,
   **Then** o valor é mostrado como desconhecido, nunca como zero.

### Edge Cases

- Alertas idênticos chegam em paralelo a réplicas diferentes do serviço.
- O alerta resolve enquanto uma validação curta ou investigação completa está em curso.
- Um alerta resolvido volta a disparar imediatamente, depois de horas ou depois de meses.
- O recurso foi renomeado, recriado, movido de nó ou substituído desde o postmortem.
- A assinatura é igual, mas severidade, impacto ou raio de alcance aumentaram.
- O postmortem descreve uma versão ou topologia que não corresponde mais ao ambiente.
- Dois postmortems publicados discordam sobre a mesma assinatura.
- O postmortem relevante pertence a outro time ou organização.
- O operador inicia a criação a partir de um grupo com centenas de ocorrências.
- Evidências ou runs de origem foram arquivados conforme a política de retenção.
- Um rascunho contém texto sensível, identificador mascarado ou alegação sem citação.
- A criação do rascunho é interrompida e retomada por outro operador autorizado.
- Um postmortem publicado é corrigido enquanto uma investigação o está consultando.
- A memória encontra episódios relevantes, mas nenhum postmortem publicado.
- O postmortem é pertinente ao sintoma, mas a causa atual é diferente.
- A capacidade necessária muda de disponível para indisponível durante o plano.
- O provedor não reporta tokens ou preço para parte dos turnos.
- O incidente continua aberto depois que todos os runs anexados terminaram.
- Uma ocorrência é recebida depois que o incidente foi fechado automaticamente.
- Um replay histórico usa identificadores locais de evidência iguais aos de outro run.

## Requirements *(mandatory)*

### Functional Requirements

#### Correlação, idempotência e ciclo de vida

- **FR-001**: O sistema DEVE atribuir a cada entrega aceita uma decisão durável de
  correlação, incluindo o motivo e os fatos usados para decidir.
- **FR-002**: Entregas simultâneas da mesma condição NÃO DEVEM iniciar mais de uma
  investigação completa.
- **FR-003**: A proteção contra repetição DEVE sobreviver a reinício, substituição e
  concorrência entre instâncias do serviço.
- **FR-004**: Toda entrega repetida DEVE permanecer visível como ocorrência; eficiência
  nunca pode significar descartar o registro do alerta.
- **FR-005**: Uma ocorrência sem mudança material DEVE ser anexada ao incidente e ao
  diagnóstico existente sem iniciar novo run completo.
- **FR-006**: A decisão de reutilizar DEVE comparar, no mínimo, identidade da condição,
  recurso, estado do incidente, atualidade do diagnóstico e todos os fatos discriminantes
  obrigatórios declarados pela revisão publicada; fato obrigatório ausente ou contradito
  impede confirmação automática. Um diagnóstico é atual enquanto o intervalo entre sua
  conclusão e a ocorrência recebida não ultrapassar 24 horas e nenhuma mudança material
  tiver sido registrada nesse intervalo; passada a janela, a reutilização deixa de ser
  automática e a ocorrência é reavaliada. A janela é uma constante nomeada e versionada,
  nunca um número no ponto de chamada.
- **FR-007**: Mudança material de sintoma, recurso, severidade, impacto, topologia ou
  evidência DEVE invalidar a reutilização automática e provocar nova avaliação.
- **FR-008**: O sistema DEVE diferenciar “incidente aberto”, “run em execução”, “aguardando
  decisão”, “monitorando recorrência” e “resolvido”, sem representar um como outro.
- **FR-009**: Um incidente sem run ativo NÃO DEVE ser apresentado como “investigação em
  andamento”.
- **FR-010**: Uma resolução upstream DEVE encerrar a condição correspondente sem apagar
  ocorrências, investigações, decisões de correlação ou postmortems associados.
- **FR-011**: A reabertura de condição resolvida DEVE ser registrada como nova ocorrência
  relacionada à recorrência anterior, com decisão explícita entre validação curta e
  investigação completa.
- **FR-012**: Alertas diferentes sobre o mesmo recurso e janela causal DEVEM poder
  participar de um único incidente, preservando seus nomes, fontes e evidências próprias.

#### Investigação robusta e eficiência de tokens

- **FR-013**: A classificação acontece em dois momentos, com entradas distintas, e nenhum
  deles pode usar as entradas do outro. Antes do run, o sistema DEVE classificar a
  ocorrência como repetição ativa, recorrência candidata, ambígua ou problema novo usando
  somente sinais determinísticos — identidade da condição, recurso, histórico durável do incidente,
  mudança material e os critérios estruturados declarados por revisões publicadas. Esse
  primeiro momento NÃO PODE usar score de similaridade nem recuperação semântica: ele
  roteia o run, não conclui por ele. Depois do evidence anchor e antes do plano amplo, o
  sistema DEVE decidir entre recorrência conhecida, candidato ambíguo e problema novo.
- **FR-014**: Correlação exata com incidente ativo ou postmortem publicado PODE ocorrer
  antes do run; recuperação semântica pelo agente DEVE ocorrer somente depois de existir
  evidência atual concreta e antes do plano amplo de coleta. O score de associação pertence
  a esse segundo momento: sem contradição material, deixar de ser ambíguo exige score de
  pelo menos 0,80 e margem mínima de 0,10 sobre o segundo candidato, enquanto empate,
  margem inferior ou fato discriminante obrigatório ausente ou contradito mantém o caso
  ambíguo.
- **FR-015**: Uma recorrência conhecida DEVE usar um caminho de validação curto e limitado
  aos fatos capazes de confirmar ou refutar a causa anterior.
- **FR-016**: O caminho curto DEVE produzir evidência atual própria; um postmortem anterior
  não pode, sozinho, provar a causa da ocorrência atual.
- **FR-017**: Falha ou contradição em qualquer fato discriminante DEVE promover o caso para
  investigação completa.
- **FR-018**: O sistema DEVE excluir do conjunto executável capacidades sabidamente
  indisponíveis no escopo do time.
- **FR-019**: A primeira indisponibilidade determinística descoberta durante um run DEVE
  impedir novas tentativas equivalentes naquele run. A supressão só é levantada por uma
  verificação bem-sucedida da própria fonte, registrada no snapshot de disponibilidade do
  run; passagem do tempo, fim de um passo do plano ou tentativa com parâmetros diferentes
  não contam como recuperação. Falha transitória não abre cache negativo e segue o retry
  normal.
- **FR-020**: Chamadas idênticas dentro de sua janela de validade DEVEM reutilizar o
  resultado já registrado e informar essa reutilização ao raciocínio. A janela padrão é a
  duração do próprio run; uma capacidade cujo resultado envelhece mais rápido PODE declarar
  uma janela menor. Ambas são constantes nomeadas, nunca literais no ponto de chamada.
- **FR-021**: Todo run DEVE possuir limites observáveis para turnos, tokens, chamadas,
  contexto histórico e tentativas sem nova evidência.
- **FR-022**: Um run que não obtém nova evidência por seu limite declarado DEVE concluir
  como suficiente, inconclusivo ou bloqueado, em vez de continuar repetindo trabalho.
- **FR-023**: Contexto histórico DEVE ser limitado aos trechos relevantes de episódios,
  estratégias e postmortems, sempre com proveniência; transcripts completos não devem ser
  incluídos por padrão.
- **FR-024**: O plano DEVE registrar quais passos foram removidos, priorizados ou mantidos
  por influência de conhecimento anterior.
- **FR-025**: Como obrigação de instrumentação de cada run, tokens, chamadas, duração e
  resultado DEVEM ser atribuíveis por fase e por caminho completo ou curto; ausência de
  medição DEVE ser “desconhecida”, nunca zero.
- **FR-026**: O sistema DEVE encerrar a coleta quando todas as alegações necessárias
  estiverem apoiadas e nenhum passo restante puder alterar materialmente a conclusão.
- **FR-027**: Uma triagem DEVE receber o estado real da correlação e NÃO PODE classificar
  como novo um incidente ao qual já existam ocorrências ou runs anexados. A decisão de
  correlação durável é a única autoridade sobre a identidade do incidente: nenhuma etapa
  posterior ao intake pode manter índice, fingerprint ou janela própria capaz de abrir,
  anexar ou reclassificar um incidente por conta própria.

#### Postmortems e Conhecimento

- **FR-028**: Conhecimento DEVE possuir uma nova aba rotulada **Postmortem**, acessível por
  URL estável e incluída na navegação por teclado.
- **FR-029**: A aba Postmortem DEVE permitir buscar e filtrar por texto, componente,
  classe do problema, estado editorial, desfecho, período e recorrência.
- **FR-030**: Cada item DEVE mostrar título, estado editorial, desfecho, componentes,
  causa ou ausência dela, última revisão, número de ocorrências relacionadas e vínculo
  para as fontes.
- **FR-031**: Incidentes e Investigações DEVEM oferecer a ação “Criar postmortem” em seus
  detalhes e nas representações expandidas que possuam fonte suficiente.
- **FR-032**: Criar postmortem NÃO DEVE converter, remover ou reescrever o incidente, run,
  episódio ou evidência de origem.
- **FR-033**: O rascunho gerado DEVE conter, quando disponíveis: resumo executivo,
  impacto, sintomas, linha do tempo, causa raiz, fatores contribuintes, evidências,
  resolução, ações corretivas/preventivas, forma de detecção e critérios de recorrência.
- **FR-034**: Todo campo inferido pelo sistema DEVE manter vínculo com sua fonte ou ser
  identificado como texto a revisar.
- **FR-035**: Um postmortem DEVE poder agregar múltiplos incidentes, ocorrências e runs
  selecionados pelo operador.
- **FR-036**: O sistema DEVE detectar postmortem possivelmente duplicado e oferecer
  adicionar fontes, criar revisão, superseder ou confirmar que é um problema distinto.
- **FR-037**: Postmortems DEVEM possuir os estados rascunho, publicado, supersedido e
  arquivado; somente publicados e vigentes podem orientar novas investigações.
- **FR-038**: Publicação DEVE ser uma ação humana atribuída e auditada; rascunhos gerados
  automaticamente nunca podem ser publicados sem decisão humana.
- **FR-039**: Um postmortem com causa raiz publicada DEVE citar evidência válida; um
  postmortem sem causa pode ser publicado somente com desfecho inconclusivo explícito.
- **FR-040**: Alterações em postmortem publicado DEVEM criar histórico de revisão com
  autor, instante, motivo e diferença legível.
- **FR-041**: Superseder ou arquivar DEVE exigir motivo e impedir uso futuro sem apagar o
  histórico de consultas anteriores.
- **FR-042**: Incidente, investigação e postmortem DEVEM apresentar links recíprocos.
- **FR-043**: O operador DEVE poder marcar uma associação de postmortem como útil,
  incorreta ou desatualizada; esse feedback DEVE influenciar usos posteriores sem alterar
  o registro histórico.
- **FR-044**: A instalação PODE propor rascunhos a partir de grupos repetidos e
  bem-evidenciados, mas DEVE explicar o agrupamento e nunca publicar automaticamente.
- **FR-045**: Postmortems DEVEM respeitar os mesmos limites de organização e time das
  fontes; nenhum resultado de outro escopo pode ser revelado ou usado.
- **FR-046**: Conteúdo de postmortem DEVE passar pelas mesmas regras de mascaramento e
  proteção contra segredos antes de ser salvo, exibido, pesquisado ou enviado a modelo.
- **FR-047**: Resultados de consulta DEVEM explicar por que cada postmortem foi associado,
  distinguindo correspondência exata, sinais semelhantes e hipótese fraca.
- **FR-048**: Um postmortem recuperado DEVE entrar no trace como fonte consultada,
  incluindo consulta, candidatos, decisão de uso e citações efetivamente utilizadas.
- **FR-049**: Episódios brutos repetidos DEVEM poder ser consolidados em uma visão
  canônica por assinatura, preservando contagem, primeira e última ocorrência, variações
  de desfecho e links para todos os runs.
- **FR-050**: Estratégias derivadas de episódios ou postmortems DEVEM indicar vigência,
  fontes e motivo de obsolescência; estratégia obsoleta não pode orientar silenciosamente
  um run.

#### Evidência, veracidade e auditoria

- **FR-051**: A identidade persistida de uma evidência DEVE ser inequívoca dentro da
  organização e do run que a produziu.
- **FR-052**: Toda referência de evidência em chamada, alegação, relatório, episódio ou
  postmortem DEVE resolver para uma observação do mesmo run de origem.
- **FR-053**: Citações quebradas ou cruzadas entre runs DEVEM ser detectadas e impedir que
  a alegação seja apresentada como validada.
- **FR-054**: Toda chamada DEVE registrar início, fim, duração, entrada protegida,
  resultado protegido, estado e referências de evidência.
- **FR-055**: Todo run DEVE registrar runtime, modelo, contagem de tokens disponível,
  limites aplicados, motivo de conclusão e resultado diagnóstico.
- **FR-056**: O estado “completado” DEVE significar somente término técnico e não pode ser
  usado isoladamente como taxa de sucesso diagnóstico.
- **FR-057**: As superfícies DEVEM distinguir ao menos: término técnico, causa apoiada,
  inconclusivo, evidência insuficiente, interrompido, bloqueado e produção recuperada.
- **FR-058**: Indicadores de sucesso e tempo até a causa DEVEM excluir ou separar runs sem
  turnos, sem diagnóstico ou sem evidência avaliada.
- **FR-059**: O estado de disponibilidade apresentado por uma fonte ou provedor DEVE
  refletir configuração e verificação reais, não apenas presença no catálogo.
- **FR-060**: Toda reutilização, correlação, criação/publicação de postmortem, feedback e
  invalidação DEVE produzir registro auditável e explicável ao operador.

#### Medição do aprendizado

- **FR-061**: Como obrigação de avaliação comparativa sobre a instrumentação de FR-025, o
  sistema DEVE medir, por investigação e agregado, tokens, chamadas, tempo, qualidade de
  evidência e desfecho com e sem reutilização de conhecimento.
- **FR-062**: Postmortem, memória episódica, estratégia e caminho de recorrência DEVEM
  possuir avaliações por ablação que isolem sua contribuição.
- **FR-063**: Uma economia NÃO DEVE ser classificada como melhoria se reduzir cobertura de
  evidência, precisão da causa ou detecção de mudança material.
- **FR-064**: O operador DEVE conseguir ver quantas vezes um postmortem foi consultado,
  aceito, rejeitado, útil para encurtar um run e associado incorretamente.
- **FR-065**: Como obrigação de apresentação dos resultados calculados por FR-061, o operador
  DEVE conseguir ver economia observada de tokens, chamadas e tempo por recorrência, com
  baseline, coorte comparável e período declarados.
- **FR-066**: Regressões no corpus de recorrência e nos cenários de problema novo DEVEM
  bloquear a alegação de melhoria da feature.

### Key Entities

- **Incident**: unidade operacional que reúne uma condição, seu estado, assuntos,
  ocorrências, runs e conhecimento relacionado.
- **Incident Occurrence**: uma entrega individual e imutável de alerta, com fonte,
  instante, sinais normalizados e decisão de correlação.
- **Correlation Decision**: explicação durável que classifica uma ocorrência como
  repetição ativa, recorrência conhecida, candidata ambígua ou problema novo.
- **Investigation Run**: execução limitada que registra fases, chamadas, uso, diagnóstico,
  evidências e motivo de conclusão.
- **Evidence Reference**: endereço inequívoco de uma observação no contexto de seu run,
  utilizado por alegações, relatórios, episódios e postmortems.
- **Episode**: memória bruta extraída de um run, útil para frequência e recuperação, mas
  não equivalente a conhecimento publicado.
- **Postmortem**: conhecimento curado sobre um problema, com estado editorial, escopo,
  causa ou inconclusão, impacto, evidências, critérios de recorrência e fontes.
- **Postmortem Revision**: versão atribuída e auditável de um postmortem, incluindo motivo
  da mudança e relação com versões anteriores.
- **Knowledge Association**: registro de que episódio, estratégia ou postmortem foi
  considerado por uma ocorrência ou run, por que foi associado e qual influência teve.
- **Investigation Strategy**: síntese vigente e atribuída de uma ordem de investigação,
  causas comuns, capacidades úteis e anti-padrões.
- **Capability Availability Snapshot**: verdade observada sobre quais fontes podiam ou não
  responder no escopo de uma investigação.
- **Learning Evaluation**: comparação reproduzível que isola contribuição, custo e
  qualidade de cada mecanismo de aprendizado.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Em alertas idênticos e sem mudança material, o número de investigações
  completas é reduzido em pelo menos 90% em relação ao baseline do staging, sem perder
  nenhuma ocorrência do histórico.
- **SC-002**: Recorrências confirmadas por postmortem consomem pelo menos 80% menos tokens
  e 50% menos chamadas do que a mediana de investigações completas do mesmo cenário, versão
  do corpus, runtime, provider/modelo e configuração de limites, executadas no mesmo período
  de avaliação com `postmortems` e `recurrence_path` desligados.
- **SC-003**: Em cenários recorrentes confirmados, 95% das conclusões ficam disponíveis ao
  operador em até 60 segundos.
- **SC-004**: Cem por cento das entregas simultâneas da mesma condição resultam em no
  máximo uma investigação completa ativa.
- **SC-005**: Cem por cento das referências de evidência resolvem para a observação e o run
  corretos; nenhuma referência cruzada entre runs é aceita como válida.
- **SC-006**: Cem por cento dos postmortems publicados possuem fontes navegáveis e causa
  apoiada por evidência, ou desfecho inconclusivo explícito.
- **SC-007**: O `recall@3` é de pelo menos 90% em um corpus versionado de no mínimo 200
  cenários rotulados antes da execução, contendo ao menos 100 recorrências com postmortem
  relevante conhecido e 100 casos negativos de problema novo, contradição ou mudança
  material; empates usam ordenação determinística declarada.
- **SC-008**: Associações incorretas aceitas como recorrência ficam abaixo de 2% no corpus
  validado, e toda contradição material promove investigação completa.
- **SC-009**: Chamadas a capacidades determinísticas e previamente indisponíveis caem pelo
  menos 95% em comparação ao baseline de 1.089 falhas.
- **SC-010**: Nenhum run sem turnos, diagnóstico ou avaliação de evidência contribui para
  a métrica de sucesso diagnóstico.
- **SC-011**: Cem por cento dos runs novos registram estado temporal completo das chamadas,
  identidade de runtime/modelo quando conhecida e uso como valor ou “desconhecido”.
- **SC-012**: Em teste moderado de primeira utilização com pelo menos 10 operadores que
  possuam permissão de curadoria e não tenham executado o roteiro antes, pelo menos 90%
  conseguem criar, revisar e publicar um postmortem a partir de um incidente ou run em menos
  de cinco minutos, sem ajuda do moderador nem documentação externa; amostra, tempos, falhas e
  versão da interface ficam registrados de forma anonimizada.
- **SC-013**: Cem por cento das publicações, revisões, arquivamentos, supersessões e usos de
  postmortem aparecem no histórico auditável com ator e motivo.
- **SC-014**: Nenhum segredo ou credencial é persistido, exibido ou enviado a modelo por
  meio do fluxo de postmortem nos testes de segurança.
- **SC-015**: A avaliação por ablação demonstra redução de custo sem regressão na precisão
  da causa, cobertura de evidência ou detecção de mudança material.
- **SC-016**: Cem por cento das telas testadas representam corretamente a diferença entre
  incidente aberto e run ativo, e entre término técnico e sucesso diagnóstico.
- **SC-017**: O corpus de episódios repetidos oferece uma visão consolidada por assinatura
  sem perder acesso a qualquer ocorrência ou run original.
- **SC-018**: O caminho de problema novo mantém qualidade e cobertura de evidência iguais
  ou superiores ao baseline após a introdução das otimizações de recorrência.
- **SC-019**: Com 10.000 postmortems no escopo autorizado e página de até 50 itens, pelo menos
  95% das buscas e mudanças de filtro bem-sucedidas exibem a primeira página em até um segundo,
  medido da ação do operador até a superfície terminar o carregamento; erros são medidos e
  reportados separadamente e nunca contam como atendimento do objetivo de latência.

## Assumptions

- A aba solicitada terá o rótulo **Postmortem** em pt-BR e inglês para preservar o termo
  operacional usado pelo produto e pelo operador.
- Postmortems são privados à instalação e ao escopo de organização/time das fontes.
- Qualquer operador com permissão para curar conhecimento pode criar rascunhos; publicar,
  superseder e arquivar exige permissão explícita de curadoria.
- Rascunhos podem ser sugeridos automaticamente, mas publicação é sempre humana.
- Um postmortem publicado é conhecimento mais confiável que um episódio bruto, mas nunca
  substitui evidência atual sobre a ocorrência presente.
- Correlação exata antes do run é uma decisão determinística sobre identidade e histórico;
  recuperação semântica ampla permanece agent-driven depois de evidência concreta, em
  conformidade com a constituição.
- A política de retenção existente continua valendo; esta feature adiciona referências e
  estados de validade, não uma nova política global de retenção.
- Ações corretivas e preventivas podem ser registradas e vinculadas, mas sua execução
  continua sujeita aos fluxos existentes de aprovação, rollback e verificação.
- A feature utiliza as superfícies e mecanismos de autenticação, autorização,
  mascaramento e auditoria já existentes.
- Eficiência nunca autoriza omitir uma ocorrência, esconder uma limitação ou transformar
  conhecimento histórico em evidência atual.
- Scores de associação são normalizados entre 0 e 1; os limites iniciais de 0,80 e margem de
  0,10 são versionados e só podem mudar acompanhados de nova medição do corpus rotulado.
- A janela inicial de atualidade de diagnóstico é de 24 horas: longa o bastante para cobrir
  um alerta que repete durante um plantão inteiro, curta o bastante para que uma causa de
  ontem não decida sozinha um incidente de hoje. Como os limites de associação, ela é
  versionada e só muda acompanhada de nova medição do corpus rotulado.
- O corpus quantitativo fixa cenário, versão, runtime, provider/modelo, configuração de
  limites e janela de execução para tornar células de ablação comparáveis.
