# Tasks: Decisão composta — a metade do produto que age passa a existir

**Input**: Design documents from `specs_v7/040-decisao-composta/`

**Prerequisites**: spec.md, plan.md. Depende da feature de registro do que o
agente fez, que aterrissa no slot anterior; depende da feature de governança da
onda, contra cuja emenda o Constitution Check do plano foi feito.

**Tests**: test-first. O vermelho de cada comportamento novo é confirmado
contra a árvore **antes** de a composição existir, e capturado com a mensagem
real. Uma composição validada só depois do fato não distingue "liguei certo" de
"o teste não olha" — que é a forma de falha que esta onda inteira existe para
pegar.

## Regras que valem para toda tarefa deste arquivo

1. **Nada de identificador de planejamento em arquivo committed.** Nenhum
   teste, comentário, docstring, documento ou mensagem de commit cita
   identificador de requisito, número de artigo, número de feature ou caminho
   de diretório de planejamento. A substância vai no arquivo; a referência fica
   nesta spec.
2. **Nenhuma tarefa remove, afrouxa ou contorna uma recusa fail-closed.** Os
   corpos das capacidades de remediação continuam recusando a chamada direta,
   com a mesma frase. Se uma tarefa parecer exigir isso, ela está errada: pare
   e reporte.
3. **O portão é o caminho único.** Nenhuma tarefa faz a rota de aprovação, um
   comando de operador ou um run repetido chamarem o executor diretamente.
4. **Propose-only é o padrão e não muda.** Nenhuma tarefa acrescenta lista de
   permissão, muda para onde a política sem configuração resolve, ou cria
   dispensa automática de plano de reversão.
5. **O interruptor de emergência vem do estado do processo.** Nenhuma tarefa
   constrói um interruptor novo em lugar nenhum.
6. **Esta feature não toca o console.** Nem componente, nem catálogo de
   mensagens, nem tabela de rotas, nem registro de telas. Uma chave nova, se
   for mesmo necessária, é declarada no relatório final com o seu texto, e a
   feature dona do slot aplica no merge.
7. **Nada é executado contra o ambiente compartilhado.** O que roda lá é
   leitura e o caminho de proposta. Uma tarefa que aprove ou execute contra
   staging está fora de escopo.
8. **Gate não é afrouxado para a composição passar.** Se um contract test
   reprovar depois de a composição existir, o defeito é da composição.

## Phase 0: Linha de base

- [x] T001 Rodar a verificação completa do repositório na árvore intacta e
      guardar o log fora do repositório. Registrar, do próprio log: quantos
      testes passam, quais falham, e quanto tempo levou. **Sem este log, uma
      falha preexistente é debitada desta feature e uma falha desta feature se
      esconde atrás de "já estava assim".** Se a linha de base não estiver
      verde, parar e reportar antes de escrever qualquer coisa.
- [x] T002 Registrar as contagens de partida a partir da árvore, não de um
      documento: quantas capacidades o registro declara, quantas escrevem por
      nível, quantas declaram exigir aprovação, quantos componentes de
      remediação estão registrados, e quantos cenários sintéticos a suíte tem.
      Esses cinco números são o "antes".
- [x] T003 Rodar a suíte de cenários sintéticos isoladamente e guardar o
      resultado, cenário a cenário. É contra esta rodada que o efeito da
      mudança de seleção de ferramentas é medido no fechamento — e "sem efeito"
      só é resposta aceitável se tiver saído desta comparação.
- [x] T004 Varrer a árvore por construção de cada um dos dois portões e
      registrar, com arquivo e linha, cada ocorrência e o que ela é (teste,
      contract test, plano de dados de mentira, produção). Este é o inventário
      que a última tarefa da feature refaz para provar que agora existe uma
      ocorrência de produção.

## Phase 1: Testes primeiro, confirmados vermelhos

Toda tarefa desta fase escreve teste contra a árvore atual e **tem de falhar**,
com uma exceção nomeada. O vermelho de cada uma é capturado com a mensagem
real.

- [x] T005 [P] Teste de contrato em `tests/contract/remediation/`: toda
      capacidade de escrita embarcada, invocada diretamente, recusa, e a frase
      da recusa é a mesma para todas. **Este é o único teste da fase que nasce
      verde**, e o motivo fica escrito no próprio arquivo: ele é a rede que
      pega esta feature afrouxando a garantia enquanto a faz funcionar.
      Registrar que passou.
- [x] T006 [P] Teste em `tests/unit/gateway/http/`: o balcão de remediação é
      composto pela root assíncrona quando a loja responde e o deployment tem
      como remediar. Confirmar vermelho: hoje nada o compõe.
- [x] T007 [P] Teste em `tests/unit/gateway/http/`: o balcão de remediação é
      composto **depois** de o runner ser reconstruído, e o balcão que o runner
      segura é o mesmo objeto que a rota de aprovação lê. Confirmar vermelho.
- [x] T008 [P] Teste em `tests/unit/gateway/http/`: um deployment sem perfil de
      sandbox que provisione, ou sem componentes registrados, não compõe o
      balcão, e a linha de log nomeia o que falta. Confirmar vermelho.
- [x] T009 [P] Teste em `tests/unit/gateway/runtime/`: o laço construído para
      uma investigação tem o portão de remediação registrado no ponto que
      decide se uma chamada de ferramenta acontece, com o contexto daquele run.
      Confirmar vermelho: hoje o registro de hooks tem só o guarda de janela.
- [x] T010 [P] Teste em `tests/unit/gateway/runtime/`: dois runs simultâneos têm
      portões distintos, cada um com o seu contexto, e a proposta de um não é
      atribuída ao requisitante do outro. Confirmar vermelho.
- [x] T011 [P] Teste em `tests/unit/gateway/runtime/`: uma capacidade acima de
      leitura sensível não é oferecida quando o balcão não está composto.
      Confirmar vermelho: hoje a seleção não olha o nível de efeito colateral.
- [x] T012 [P] Teste em `tests/unit/gateway/runtime/`: uma capacidade acima de
      leitura sensível não é oferecida quando este deployment não tem
      componentes registrados para ela, mesmo com o balcão composto. Confirmar
      vermelho.
- [x] T013 [P] Teste em `tests/unit/gateway/runtime/`: nenhuma ferramenta
      oferecida exige uma integração que o time não conectou. Confirmar
      vermelho: hoje a seleção ranqueia contra o alerta e não contra a
      configuração.
- [x] T014 [P] Teste em `tests/unit/gateway/runtime/`: o corte pelo teto de
      esquemas acontece depois dos dois estreitamentos, provado por um caso em
      que cortar antes deixaria de fora uma capacidade que o time tem.
      Confirmar vermelho.
- [x] T015 [P] Teste em `tests/unit/gateway/runtime/`: um time sem nenhuma
      integração conectada termina com a resposta que nomeia o que conectar,
      quantas capacidades cada sugestão destravaria e exemplos delas, com a
      correspondente à fonte do alerta primeiro. Confirmar vermelho.
- [x] T016 [P] Teste em `tests/unit/capabilities/registry/`: o resolvedor de
      catálogo por time devolve a mesma resolução pela entrada com estado e pela
      entrada sem estado, para a mesma disponibilidade. Confirmar vermelho: a
      entrada sem estado não existe.
- [x] T017 [P] Teste em `tests/unit/gateway/runtime/`: as interações pendentes
      de um run devolvem a pergunta que aquele run levantou, respondê-la a
      fecha, e a resposta chega ao run. Confirmar vermelho: hoje a listagem
      devolve vazio incondicionalmente e a resposta recusa.
- [x] T018 [P] Teste em `tests/unit/gateway/runtime/`: dois runs concorrentes
      levantam perguntas e a resposta a uma não fecha a do outro. Confirmar
      vermelho.
- [x] T019 [P] Teste em `tests/unit/gateway/runtime/`: responder um
      identificador que nenhum run levantou é distinguido de responder um que já
      foi respondido. Confirmar vermelho.
- [x] T020 [P] Teste em `tests/unit/gateway/http/`: aprovar um pedido de
      remediação leva a ação adiante pelo portão e grava o resultado com o
      identificador da aprovação; rejeitar não executa nada e grava a razão.
      Confirmar vermelho: hoje a rota só registra a decisão.
- [x] T021 [P] Teste em `tests/unit/gateway/http/`: um pedido expirado não é
      executado, e o interruptor acionado entre a aprovação e a execução a
      recusa nomeando o interruptor. Confirmar vermelho.
- [x] T022 [P] Teste estrutural em `tests/contract/remediation/`: o executor de
      remediação é chamado a partir do portão e de nenhum outro lugar. Deve
      passar hoje — é a garantia vigente — e é a rede que pega a rota de
      aprovação chamando o executor por atalho. Registrar que passou.
- [x] T023 [P] Teste em `tests/architecture/`: exatamente um caminho de
      orquestração de investigação é alcançável a partir da composition root de
      serving, e o outro declara de si mesmo que não está composto, nomeando o
      que o constrói. Confirmar vermelho: hoje os dois existem sem dono
      declarado.
- [x] T024 Confirmar e registrar o vermelho de T006–T021 e T023 com a mensagem
      real de cada um, e o verde de T005 e T022. **Portão: nenhuma composição
      começa antes disto.**

## Phase 2: O compositor e o campo de estado

- [x] T025 Acrescentar ao estado do gateway o campo que segura o balcão de
      remediação composto, com o comentário dizendo o que significa ele estar
      ausente: este deployment propõe e não age, e as capacidades de escrita não
      são oferecidas. Ausente é o padrão.
- [x] T026 Escrever o módulo compositor novo em `gateway/http/`, na forma que o
      compositor do verificador profundo já pratica: uma função que recebe o
      estado e a organização, constrói o balcão, o instala, e — quando este
      deployment não tem como remediar — não instala nada e escreve a linha de
      log que nomeia o que falta.
- [x] T027 Construir o registro de componentes de remediação dentro do
      compositor, passando os sinais que as fontes de observação deste
      deployment produzem, de modo que uma capacidade que nomeia um sinal que
      ninguém emite falhe na composição e não na primeira execução.
- [x] T028 Construir o gerador de plano de reversão e o construtor de pedido
      dentro do compositor, com o serviço de aprovação, o handle de
      persistência, o escopo do tenant e a consulta de eficácia sobre o registro
      de resultados.
- [x] T029 Construir o executor dentro do compositor, com o interruptor vindo do
      estado do processo, o auditor sobre o gravador de auditoria, as obrigações
      de verificação sobre o registro de resultados, e o aplicador de desfazer
      para o caso do meio-aplicado.
- [x] T030 Construir o isolamento de execução dentro do compositor, com o perfil
      lido da resolução de perfil que já existe e o provisionador
      correspondente. Um deployment cujo perfil não provisiona não compõe o
      balcão — é o caso de T008.
- [x] T031 Construir a política de portamento a partir da política de segurança
      da organização, deixando o padrão de silêncio no estrito: uma organização
      que não declarou nada porta tudo acima de leitura sensível.
- [x] T032 Colocar no balcão o construtor do portão de autonomia — um
      construtor, não um portão pronto — que resolve a política do nó de
      configuração do time no momento da decisão, através do mesmo serviço que a
      explicação publicada usa, com o interruptor do processo.
- [x] T033 Chamar o compositor na root assíncrona, **depois** da composição do
      acesso a integrações, da composição das credenciais de provedor e da
      reconstrução do runner, com o comentário no lugar da chamada explicando a
      ordem — em particular por que compor antes da reconstrução entregaria o
      balcão ao objeto que foi descartado. T006, T007 e T008 passam a verde.

## Phase 3: O portão por investigação

- [x] T034 Acrescentar ao runner de serving o campo que recebe o balcão de
      remediação, com a mesma disposição do campo que já existe para o registro
      do que aconteceu: ausente é um estado válido e o comportamento sem ele é
      exatamente o de antes.
- [x] T035 Construir, por investigação, o contexto de run — quem pede, qual
      time, qual run, qual ambiente — e o portão de remediação daquele run, e
      registrá-lo no registro de hooks do laço. T009 passa a verde.
- [x] T036 Confirmar por teste que a ordem de registro deixa o portão depois dos
      guardrails: uma chamada que um guardrail vai bloquear não deve primeiro
      custar a uma pessoa a interrupção de ser consultada.
- [x] T037 Garantir que nada compartilha portão entre runs simultâneos. T010
      passa a verde.
- [x] T038 Conferir, com teste, que a proposta gerada por uma chamada de
      ferramenta chega ao armazenamento com a ação, o recurso, o raio de
      alcance — ou a declaração de que ele é desconhecido — e o plano de
      reversão, escritos na mesma unidade de trabalho.
- [x] T039 Conferir, com teste, que em propose-only nada é executado, que a
      razão devolvida ao modelo diz que a ação espera por uma pessoa, que ela
      nomeia a política, e que a investigação continua.

## Phase 4: Aprovação e execução

- [x] T040 Dar ao portão de remediação a entrada pública que significa "esta
      aprovação foi concedida, leve a ação adiante": ela reconfere o interruptor
      e as travas do laço fechado e desce pelo mesmo caminho de execução que o
      portão já usa. **Não** um segundo chamador do executor.
- [x] T041 Reconstruir a ação a partir do que o pedido de aprovação guardou, de
      modo que a execução seja da ação que a pessoa leu, e não de uma
      reconstruída por aproximação. Um pedido cujo conteúdo não permita
      reconstruir a ação é recusado nomeando o que falta.
- [x] T042 Fazer a rota que decide uma aprovação chamar essa entrada quando o
      veredito é aprovar e a mudança é de remediação, **depois** de a decisão
      estar gravada, e nunca antes. Atualizar a docstring da rota para dizer o
      que ela passa a fazer, porque hoje ela afirma explicitamente que nunca
      invoca a capacidade. T020 passa a verde.
- [x] T043 Deixar a rejeição, a expiração e o interruptor acionado no caminho
      certo: nenhuma delas executa, cada uma grava o que houve. T021 passa a
      verde.
- [x] T044 Conferir que o resultado gravado diz se a execução foi autônoma ou
      aprovada, carrega o identificador da aprovação, e que a obrigação de
      verificar se aquilo funcionou foi gravada quando a execução mudou alguma
      coisa.
- [x] T045 Reconfirmar T022: o executor continua sendo chamado do portão e de
      nenhum outro lugar, agora que existe uma segunda entrada.

## Phase 5: Seleção de ferramentas

- [x] T046 Dar ao resolvedor de catálogo por time a entrada sem estado que
      recebe a disponibilidade já derivada, com a entrada existente delegando
      nela. Uma implementação de resolução, dois chamadores. T016 passa a
      verde.
- [x] T047 Instanciar o resolvedor no caminho de serving, derivando a
      disponibilidade da configuração resolvida do nó do time — a mesma lista
      que a visão de catálogo lê, para que o que a tela conta e o que a
      investigação recebe não possam discordar.
- [x] T048 Tratar a configuração do time que não pôde ser lida como a postura
      mais estrita, com o motivo no registro. Uma leitura falhada não vira
      permissão.
- [x] T049 Estreitar a seleção pelo nível de efeito colateral: uma capacidade
      acima de leitura sensível só entra quando o balcão está composto **e** o
      registro de componentes tem aquela capacidade. T011 e T012 passam a
      verde.
- [x] T050 Estreitar a seleção pelo que o time conectou, mantendo o registro do
      que foi excluído e por qual requisito, para que a exclusão seja legível
      depois e não uma ausência silenciosa. T013 passa a verde.
- [x] T051 Mover o corte pelo teto de esquemas para depois dos dois
      estreitamentos. T014 passa a verde.
- [x] T052 Fazer o caminho de serving produzir a resposta de zero integrações
      chamando a mesma função que o estágio de resolução já chama — não uma
      segunda redação dela. T015 passa a verde.
- [x] T053 Atualizar a docstring do método de seleção: hoje ela declara, como
      limitação conhecida, exatamente as duas coisas que esta fase resolve.
      Deixá-la como está seria o arquivo mentindo sobre o próprio
      comportamento.

## Phase 6: O balcão de perguntas

- [x] T054 Construir, por investigação, o balcão de perguntas daquele run com o
      seu próprio registro de interações, e guardá-lo junto do que o processo já
      lembra sobre o run enquanto pode agir sobre ele.
- [x] T055 Substituir, na seleção de ferramentas, a capacidade de pergunta
      declarada pela do run — mesmo nome, mesmo esquema — de modo que o vínculo
      de processo não seja usado pelo gateway. Duas grafias da mesma capacidade
      competindo no orçamento de esquemas seria um defeito por si só.
- [x] T056 Fazer a listagem de interações pendentes devolver as perguntas
      daquele run em vez de vazio incondicional. T017 passa a verde para a
      parte de listagem.
- [x] T057 Fazer a busca de uma interação por identificador responder pelo
      balcão do run correspondente.
- [x] T058 Fazer a resposta a uma interação fechá-la e chegar ao run que
      esperava, com a primeira resposta vencendo e a segunda sendo informada de
      quem respondeu antes. T017, T018 e T019 passam a verde.
- [x] T059 Conferir, com teste, que uma pergunta que pede credencial é recusada
      antes de aparecer para qualquer pessoa, e que uma pergunta não respondida
      dentro da janela é fechada como não respondida.
- [x] T060 Atualizar a docstring do módulo do investigador de serving, que hoje
      afirma que nada nesta composição vincula o balcão de perguntas. A
      afirmação deixa de ser verdadeira nesta fase.

## Phase 7: O caminho duplicado ganha dono

- [x] T061 Declarar, no módulo que monta o pipeline de seis estágios, que ele
      não está no caminho de serving e nomear o que o constrói — o harness de
      avaliação que roda o corpus sintético. A declaração é sobre composição,
      não sobre qualidade: "não serve produção" e não "está morto".
- [x] T062 Conferir, com teste, que o caminho de serving é o outro e que ele é
      alcançável da composition root. T023 passa a verde.
- [x] T063 Conferir que a resposta de zero integrações continua tendo uma
      implementação só, com os dois chamadores apontando para ela.

## Phase 8: O cenário ponta a ponta

- [x] T064 Escrever o cenário sintético em `tests/synthetic/`: uma investigação
      cujo diagnóstico leva à capacidade de escala de carga de trabalho — a
      escolhida no plano por ser reversível, de risco baixo e com plano de
      reversão derivável — sobre uma carga de trabalho do próprio deployment,
      nunca do estate. Sob propose-only, ele para na proposta, e a asserção é o
      que ficou gravado.
- [x] T065 Estender o cenário com a metade da aprovação, **num ambiente que
      este trabalho controla, com plano de controle ligado**: a aprovação
      executa pelo portão, o resultado fica gravado com o identificador da
      aprovação, e o plano de reversão já estava gravado antes.
- [x] T066 Conferir, no mesmo cenário, que nada foi executado antes da
      aprovação, e que o estado do recurso é o mesmo do início até ela
      acontecer.

## Phase 9: Fechamento

- [ ] T067 Rodar a suíte de cenários sintéticos e comparar com T003, cenário a
      cenário. Reportar o efeito da mudança de seleção de ferramentas.
      "Nenhum efeito" só é resposta aceitável saindo desta comparação; "não
      medido" não é resposta.
- [ ] T068 Rodar a verificação completa do repositório e comparar, alvo por
      alvo, com o log de T001. Toda diferença é explicada ou corrigida, nunca
      omitida.
- [ ] T069 Refazer a varredura de T004 e registrar o inventário novo: cada
      construção dos dois portões, com arquivo e linha, e o que ela é. Ao menos
      uma tem de ser produção, alcançável da composition root de serving.
- [ ] T070 Reconfirmar T005: toda capacidade de escrita embarcada, invocada
      diretamente, continua recusando com a mesma frase. Se esta tarefa
      falhar, a feature afrouxou o que existia para não afrouxar.
- [ ] T071 Declarar no relatório final, para o merge do slot: qualquer chave de
      catálogo de mensagens que a implementação tenha descoberto precisar, com o
      texto proposto; e a confirmação de que nenhum arquivo de escrita única do
      console foi tocado.
- [x] T072 Atualizar o `controle.md` desta feature com o que o código prova: o
      inventário antes e depois dos construtores dos portões, o vermelho
      capturado de cada teste da Fase 1, as contagens no armazenamento depois do
      cenário sintético, o efeito medido sobre a suíte de cenários, e toda
      ressalva de honestidade — inclusive qualquer teste cujo vermelho não foi
      visto antes da implementação, e por quê.

## Validação em staging (fim do slot, pelo orquestrador)

Não são tarefas do implementer. Ficam aqui porque são o DoD da feature.

- [ ] S01 Depois do ciclo de deploy do slot, disparar uma investigação real e
      conferir, com credencial de operador, que a lista de aprovações do
      gateway traz a proposta com o plano de reversão junto.
- [ ] S02 Contar no banco de staging: pedidos de aprovação de remediação maior
      que zero; planos de reversão maior que zero, com ao menos um
      correspondendo a um daqueles pedidos.
- [ ] S03 Contar no banco de staging: pedidos de remediação em estado diferente
      de pendente igual a **zero**, e resultados de remediação igual a
      **zero**. Um valor diferente de zero em qualquer um dos dois é defeito,
      não progresso: nada aprova nem executa sozinho no ambiente compartilhado.

## Dependencies

- T001 → T002 → T003 → T004 → toda a Fase 1. A linha de base precede qualquer
  escrita.
- T024 é portão: nenhuma composição começa antes do vermelho confirmado.
- T005 e T022 nascem verdes e são reconferidos no fechamento (T070, T045).
- Fase 2 em ordem: T025 → T026 → T027 → T028 → T029 → T030 → T031 → T032 →
  T033. O compositor precisa existir antes de ser chamado, e T033 é o que fecha
  T006, T007 e T008.
- Fase 3 depende de T033. T034 → T035 → T036 → T037; T038 e T039 dependem de
  T035.
- Fase 4 depende de T033 e da Fase 3. T040 → T041 → T042 → T043 → T044 → T045.
- Fase 5 é independente das Fases 3 e 4 quanto à ordem interna, mas T049 depende
  de T025 (a seleção precisa poder perguntar se o balcão existe). T046 → T047 →
  T048; T049 e T050 são paralelas entre si; T051 depende das duas; T052 depende
  de T050; T053 depende de T049, T050 e T051.
- Fase 6 depende de T034. T054 → T055 → T056 → T057 → T058 → T059 → T060.
- Fase 7 depende de T052 (a resposta de zero integrações precisa já ter dois
  chamadores para T063 significar alguma coisa).
- Fase 8 depende das Fases 2 a 5. T064 → T065 → T066.
- Fase 9 depende de tudo. T067 depende de T003; T068 depende de T001; T069
  depende de T004; T070 depende de T005; T072 é a última.
- S01–S03 dependem do merge do slot e do ciclo de deploy, e são do
  orquestrador.
