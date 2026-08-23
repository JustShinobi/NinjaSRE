# Tasks: Registro do que o agente fez — se rodou, está escrito

**Input**: Design documents from `specs_v7/001-registro-do-que-o-agente-fez/`

**Prerequisites**: spec.md, plan.md. Nenhuma dependência de código em outra
feature. A 000 precede esta por regra, não por artefato.

**Tests**: test-first. Todo teste de comportamento desta feature é escrito e
**confirmado vermelho** contra a árvore atual antes de qualquer composição. Uma
gravação validada só depois do fato não distingue "gravei certo" de "o teste não
olha" — que é exatamente como um mecanismo escrito e não composto atravessou
cinco ondas com o harness verde.

## Regras que valem para toda tarefa deste arquivo

1. **Nada de identificador de planejamento em arquivo committed.** Nenhum teste,
   comentário, docstring, migração, prompt, documento gerado ou mensagem de
   commit cita identificador de requisito, número de artigo da constituição,
   número de feature ou caminho de diretório de planejamento. A substância vai
   no arquivo; a referência fica nesta spec.
2. **Nenhuma escrita nova fala com o store diretamente.** Toda gravação de
   turno, chamada ou evidência passa pelo `RunRecorder`, que redige por
   guardrail e trunca antes de persistir. Um caminho que chame o repositório
   direto é um caminho que pode gravar segredo, e ele não é aceito nem "só nos
   testes de integração".
3. **Verde no harness não fecha tarefa de comportamento.** As tarefas de
   composição e de gravação só fecham com evidência do caminho de serving: a
   contagem no banco depois de uma investigação real.
4. **Custo ausente nunca vira zero.** Se em qualquer ponto for mais fácil
   escrever `0.0` do que propagar a ausência, o caminho está errado. Um total
   que parece autoritativo e está errado é o que ninguém mais questiona.
5. **A síntese da sentença nunca lê o documento.** Se uma implementação
   conseguir produzir a sentença cortando o report, ela reproduziu o defeito que
   esta feature existe para eliminar.
6. **Artefato gerado é regenerado, nunca editado à mão.** Vale para o documento
   HTTP e para o cliente TypeScript.
7. **Esta feature não toca `console/src/i18n/*.ts`, `console/src/shell/routes.ts`
   nem `console/visual/screens.json`.** No slot dela, esses arquivos têm outro
   dono. Ela também não toca nenhum outro diretório de feature.

## Phase 0: Linha de base

- [x] T001 Rodar a verificação completa do repositório na árvore intacta e
      guardar o log **fora do repositório**. Registrar, do próprio log: quantos
      testes passam, quais falham, e o tempo. Se a linha de base não estiver
      verde, parar e reportar antes de mudar qualquer coisa. Sem este log, uma
      falha preexistente é debitada desta feature e uma falha desta feature se
      esconde atrás de "já estava assim".
- [x] T002 Rodar a suíte de cenários sintéticos na árvore intacta e guardar o
      resultado fora do repositório: quantos cenários existem, quantos passam, e
      os escores. Este é o "antes" contra o qual o efeito desta mudança sobre
      investigação será reportado no fechamento. "Sem efeito" será uma resposta
      aceitável; "não medido" não.
- [ ] T003 Registrar as contagens de partida direto do banco de staging, não de
      um documento: turnos, chamadas, evidência e eventos de trace, no total e
      para os runs completed da última hora. É o "antes" que a evidência de
      fechamento compara.

## Phase 1: Gates primeiro, confirmados vermelhos

Todas as tarefas desta fase escrevem teste contra a árvore atual e **têm de
falhar**. O vermelho de cada uma é capturado com a mensagem real. Elas são
independentes entre si.

- [x] T004 [P] Teste em `tests/unit/gateway/runtime/`: uma investigação
      executada pelo runner, com um lugar para gravar composto, deixa um
      registro de turno por iteração e um registro de chamada por chamada de
      capacidade. Dirigido por um laço falso que produz turnos e execuções
      conhecidos, contra um store falso. Confirmar vermelho: hoje o runner não
      tem onde gravar e nada é escrito.
- [x] T005 [P] Teste em `tests/unit/platform/runs/`: o adaptador de gravação
      traduz um turno do laço para o vocabulário do recorder preservando modelo,
      tokens de entrada, tokens de saída, duração e capacidades oferecidas.
      Confirmar vermelho: o módulo não existe.
- [x] T006 [P] Teste em `tests/unit/platform/runs/`: um turno cujo provedor não
      publicou preço é gravado **sem custo**, e a agregação de custo o conta como
      turno sem preço em vez de somar zero. Confirmar vermelho: o tipo de entrada
      do recorder não sabe expressar ausência de custo.
- [x] T007 [P] Teste em `tests/unit/platform/runs/`: uma chamada que falhou e
      uma chamada recusada por política são ambas gravadas, com seus desfechos
      próprios, e não omitidas. Confirmar vermelho.
- [x] T008 [P] Teste em `tests/unit/platform/runs/`: uma falha na escrita de um
      registro não interrompe a investigação e aparece como falha de hook no
      resultado do run. Confirmar vermelho.
- [x] T009 [P] Teste em `tests/unit/platform/runs/`: a normalização da sentença
      reduz marcação, múltiplas linhas e excesso de tamanho a uma linha limpa,
      cortada na fronteira de palavra. Confirmar vermelho: o módulo não existe.
- [x] T010 [P] Teste em `tests/unit/platform/runs/`: a síntese da sentença deriva
      do sujeito — nome do alerta e recurso quando há alerta, objetivo declarado
      quando não há — e **nunca** do documento. O teste inclui o caso adversário:
      um documento que começa com um cabeçalho markdown atraente não pode
      aparecer na sentença. Confirmar vermelho.
- [x] T011 [P] Teste de contrato em `tests/contract/`: a leitura de uma
      investigação traz sentença e documento em campos distintos, e a sentença é
      uma linha sem marcação. Confirmar vermelho: o contrato tem um campo só.
- [x] T012 [P] Teste de contrato em `tests/contract/`: a leitura de um run
      gravado antes desta mudança — sem sentença armazenada — devolve o documento
      que ele sempre teve e uma sentença sintetizada não vazia. Confirmar
      vermelho.
- [x] T013 [P] Teste de contrato em `tests/contract/`: o replay de um run traz,
      por turno, o modelo e os tokens, traz custo quando há preço, e declara os
      turnos sem preço em vez de somá-los como zero. Confirmar vermelho: hoje o
      replay de qualquer run real vem sem turno nenhum.
- [x] T014 [P] Teste de contrato em `tests/contract/`: a leitura de um run diz a
      que incidente ele pertence, ou diz explicitamente que não pertence a
      nenhum, sem que o cliente precise pedir a lista de incidentes. Confirmar
      vermelho.
- [x] T015 [P] Teste de contrato em `tests/contract/`: a leitura de um run lista
      os recursos que suas chamadas tocaram, derivados do que foi registrado.
      Confirmar vermelho.
- [x] T016 [P] Teste em `tests/architecture/`: o caminho de serving compõe o
      recorder — construir o deployment a partir de uma configuração que nomeia
      o runtime de investigação produz um runner que tem onde gravar, e
      reconstruí-lo depois de a configuração ser lida preserva isso. É o teste
      que reprova se alguém desfizer a composição. Confirmar vermelho.
- [x] T017 [P] Teste em `tests/architecture/`: exatamente um caminho grava o
      recibo do alerta. O teste inspeciona a árvore e falha se houver mais de um
      construtor de gravação de recibo alcançável de produção; é pareado com
      T018, que exerce o comportamento. Confirmar vermelho: hoje há dois
      caminhos escritos, ainda que só um esteja ligado.
- [x] T018 [P] Teste de contrato em `tests/contract/`: uma investigação
      disparada por alerta deixa exatamente uma entrada de recibo na linha do
      tempo do incidente, e nenhum evento repetido no log do run. Deve **passar**
      hoje — é caracterização, e é a rede que pega a duplicação que ligar o
      recorder poderia introduzir. Registrar que passou, e por quê.
- [x] T019 Confirmar e registrar o vermelho de T004–T017 com a mensagem real de
      cada um, e o verde de T018. Só depois disto a Fase 2 começa.

## Phase 2: O tipo que sabe dizer "sem preço"

- [x] T020 Fazer o tipo de entrada de turno do recorder admitir custo ausente, e
      gravar a ausência como ausência no corpo de uso do turno. Não tocar a
      leitura: ela já distingue ausente de zero. T006 passa a verde.
- [x] T021 Conferir que os chamadores existentes do recorder — o executor de
      agendamento, o semeador de demonstração, os traces de notificação e de
      entrega de relatório — continuam corretos com o tipo novo, e que nenhum
      deles passou a gravar ausência onde antes gravava um zero verdadeiro.

## Phase 3: O adaptador que grava

- [x] T022 Escrever o adaptador de gravação em `platform/runs/`: recebe um
      recorder por escrita e traduz o vocabulário do laço para o do recorder —
      turno, chamadas do turno, evidência produzida. Uma unidade de trabalho por
      escrita, porque o run vive mais que qualquer transação. T005 passa a verde.
- [x] T023 Fazer o adaptador registrar-se nos pontos de hook do laço: fim de
      turno para o turno e suas chamadas, e o ponto pós-chamada para a evidência
      que ela produziu. Nenhum ponto novo é inventado; são os que o registro de
      hooks já expõe. T004 e T007 passam a verde.
- [x] T024 Fazer a falha de escrita ser engolida e registrada como falha de hook,
      nunca propagada para a investigação. T008 passa a verde.
- [x] T025 Conferir que o registro de um sub-agente continua sendo um run
      aninhado com vínculo ao pai, e que o adaptador não achata os turnos do
      filho dentro do pai. Se a forma quebrar, o defeito é do adaptador.

## Phase 4: Composição no caminho de serving

Esta é a fase que fecha o defeito. Nenhuma tarefa dela fecha com teste verde
sozinho.

- [x] T026 Completar o objeto de início de investigação com a identidade da
      organização, ao lado do nó de time que ele já carrega, e propagá-la a
      partir de quem já tem o escopo autenticado — tanto na rota de operador
      quanto no caminho de alerta.
- [x] T027 Fazer a função que resolve o investigador a partir da configuração
      receber o store e **anexar** o adaptador de gravação ao runner que a
      fábrica devolveu. Um só ponto de anexo. A fábrica que a configuração nomeia
      continua sem argumento e continua sem store — é o que permite a um operador
      nomear um runtime em vez de escrevê-lo.
- [x] T028 Fazer as duas chamadoras dessa função — a construção do deployment e
      a reconstrução do investigador depois que a configuração é lida — passarem
      o store. A segunda é a que faz a composição sobreviver ao rebuild; sem ela
      a feature funciona no boot e some depois que o operador escolhe um
      provedor. T016 passa a verde.
- [x] T029 Conferir que um deployment que **não** nomeia runtime de investigação
      continua subindo, sem recorder e sem erro, e que o produto continua
      respondendo que nada está composto — é um estado que a checagem de primeiro
      uso e a rota de início leem, e um anexo que produzisse algo no lugar do
      substituto responderia errado às duas.
- [x] T030 Fazer o registro de hooks da investigação carregar o hook de gravação
      quando o runner tem onde escrever, e continuar carregando só a guarda de
      janela quando não tem.

## Phase 5: Um só escritor

- [x] T031 Remover da árvore o caminho concorrente de gravação de recibo dentro
      do runner, com o colaborador que só existia para ele. Não desligar por
      configuração: a compatibilidade morre na mesma mudança que a torna
      desnecessária, e um segundo escritor desligado é um segundo escritor
      esperando alguém religá-lo.
- [x] T032 Reapontar os testes que exerciam aquele caminho para afirmar o
      escritor único, em vez de apagá-los. Um teste que provava um comportamento
      que saiu vira o teste que prova que ele saiu. T017 passa a verde e T018
      continua verde.
- [x] T033 Conferir, e deixar escrito no docstring do lugar que ficou, que o
      pipeline por estágios continua **sem** chamador de produção e que esta
      feature deliberadamente não lhe dá um. A frase é sobre o que o módulo é,
      não sobre o plano — nenhum identificador de planejamento nela.

## Phase 6: A sentença e o documento

- [x] T034 Escrever a normalização da sentença em `platform/runs/`: uma linha,
      sem marcação, cortada na fronteira de palavra num limite declarado como
      constante. T009 passa a verde.
- [x] T035 Escrever a síntese da sentença: deriva do sujeito — nome do alerta e
      recurso quando o run veio de alerta, objetivo declarado quando veio de
      operador — e **nunca** do documento. T010 passa a verde.
- [x] T036 Migração reversível acrescentando a coluna da sentença em
      `agent_runs`, com valor padrão vazio e sem reescrever nenhuma linha
      existente. Próximo número livre da série, pai declarado. A volta é escrita
      junto e é exercitada, não apenas escrita.
- [x] T037 Levar a sentença ao objeto de domínio do run, ao modelo relacional, ao
      repositório e ao duplo em memória, de forma que os quatro digam a mesma
      coisa. Um duplo que não carrega o campo é um teste que passa sobre um
      contrato que o banco não cumpre.
- [x] T038 Fazer o prompt de entrega pedir ao modelo a sentença além do
      documento, em `config/prompts/`. Uma constante, revisável como diff — não
      uma f-string no ponto de chamada. O texto diz o que a sentença é: uma
      linha, sem marcação, que serve de nome.
- [x] T039 Fazer o caminho que conclui a investigação extrair a sentença da
      resposta do modelo, normalizá-la, e cair para a síntese quando ela não
      vier. Gravar a sentença junto do fechamento do run, na mesma escrita que já
      grava o documento.
- [x] T040 Acrescentar os dois campos ao contrato de leitura de investigação, e
      servir a sentença sintetizada quando a armazenada estiver vazia. Manter
      `summary` servindo o mesmo texto do documento, com a descrição do campo
      declarando-o substituído pelos dois novos. T011 e T012 passam a verde.

## Phase 7: Vínculos e custo na leitura

- [x] T041 Fazer a leitura de um run dizer a que incidente ele pertence, do lado
      do servidor, e dizer explicitamente quando não pertence a nenhum — de forma
      distinguível de uma leitura que falhou. T014 passa a verde.
- [x] T042 Fazer a leitura de um run listar os recursos que suas chamadas
      tocaram, derivados do que foi registrado e não dos sujeitos declarados no
      alerta. T015 passa a verde.
- [x] T043 Fazer o replay informar quantos turnos ficaram sem preço, ao lado do
      total que soma só os precificados. T013 passa a verde.
- [x] T044 Cravar e registrar, no relatório final, a causa do badge que aparece
      num run terminado. A apuração desta rodada é que ele é rótulo de **estado
      de conexão ao vivo**, não de estado do run: o run já fecha com status
      terminal e já emite o evento de fim. Confirmar que isso continua verdadeiro
      depois desta feature — o run termina, o evento de fim está no log, e o
      replay lê o run como terminado — e entregar a apuração à feature que
      renderiza a tela, em vez de mexer no console aqui.

## Phase 8: Fronteira de contrato

- [x] T045 Regenerar o documento de contrato HTTP committed a partir da
      aplicação. Não editar à mão.
- [x] T046 Regenerar o cliente TypeScript a partir desse documento, e rodar a
      checagem de desvio. Uma mudança de contrato que deixa o cliente para depois
      é uma fronteira quebrada que só aparece no slot seguinte.
- [x] T047 [P] Atualizar as fixtures do plano de dados simulado para trazerem os
      campos novos, sem inventar conteúdo que o produto não produziria: sentença
      curta e coerente com o documento da mesma fixture.
- [x] T048 [P] Conferir que as suítes de console existentes continuam passando
      com o cliente regenerado. Nenhuma delas é reescrita aqui; elas são a
      regressão do que já passava. Se uma quebrar por ler `summary`, a correção é
      da feature que reescreve a tela — reportar, não consertar aqui.

## Phase 9: Fechamento e evidência

- [x] T049 Rodar a suíte de persistência contra um PostgreSQL real e conferir a
      migração nos dois sentidos, contra um banco **com dados**: aplicar,
      conferir que o conteúdo das linhas existentes está idêntico, desaplicar,
      conferir de novo. Uma migração cuja volta nunca foi rodada é uma migração
      que não tem volta.
- [x] T050 Medir e registrar o efeito sobre a suíte de cenários sintéticos:
      quantos cenários havia, quantos há, o resultado antes e depois, e qualquer
      movimento de escore. Comparar com o registro de T002. "Sem efeito" é
      resposta aceitável; "não medido" não é.
- [x] T051 Rodar a verificação completa do repositório e comparar, alvo por
      alvo, com o log de T001. Todo alvo que passava continua passando. Qualquer
      diferença é explicada ou corrigida, nunca omitida.
- [x] T052 **Evidência de serving.** Depois do deploy do slot, disparar uma
      investigação a partir de um alerta real que o Alertmanager já entrega, e
      rodar as seis consultas enumeradas na spec contra o banco de staging.
      Capturar a saída de cada uma. A tarefa fecha quando turnos, chamadas e
      evidência daquele run forem maiores que zero, a contagem de chamadas bater
      com a que o replay devolve, e o recibo aparecer uma vez só. Nenhuma outra
      forma de verde fecha esta tarefa.
- [x] T053 **Evidência de contrato no ambiente real.** Pedir a leitura do run e o
      replay do run ao staging e capturar as respostas: sentença presente e com
      uma frase, documento presente, turnos com modelo e tokens, custo presente
      ou declaradamente ausente. As duas são leituras e são seguras contra o
      ambiente compartilhado.
- [x] T054 Reportar ao orquestrador do slot, no relatório final: (a) que esta
      feature regenerou o documento de contrato e o cliente TypeScript e que, se
      a outra feature do slot também o fez, os dois artefatos gerados devem ser
      **descartados no merge e regenerados uma vez só** a partir do código
      mergeado, nunca resolvidos linha a linha; (b) a apuração da causa do badge
      de run terminado, endereçada à feature que renderiza a tela; (c) que
      `summary` continua no contrato e sai quando o último leitor sair.
