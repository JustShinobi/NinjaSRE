# Tasks: Regras e governança — as regras dizem a verdade antes de qualquer feature ser escrita contra elas

**Input**: Design documents from `specs_v7/000-regras-e-governanca/`

**Prerequisites**: spec.md, plan.md. Nenhuma feature anterior — esta é a raiz da
onda e roda sozinha no slot S0.

**Tests**: test-first onde há comportamento. Cada regra transversal nova aterrissa
com a allowlist **vazia** e é confirmada **vermelha** contra o cenário violador
antes de a allowlist existir. O backing novo aterrissa com as suas recusas
provadas antes de funcionar.

## Regras que valem para toda tarefa deste arquivo

1. **Nada de identificador de planejamento em arquivo committed.** Nenhum teste,
   comentário, docstring, entrada de allowlist, registro de decisão, linha de
   tabela ou mensagem de commit cita identificador de requisito, número de artigo
   da constituição, número de feature ou caminho de diretório de planejamento. A
   substância vai no arquivo committed; a referência fica nesta spec.
2. **A constituição nunca é commitada.** Ela é emendada no disco. Se um comando
   de staging de arquivos a incluir, o comando está errado. O mesmo vale para a
   orientação local.
3. **Registro de decisão aceito é imutável.** O único registro preexistente que
   esta feature toca tem **uma linha alterada**: a do status. Corpo, contexto,
   alternativas e consequências ficam palavra por palavra como estão.
4. **Nenhuma tarefa toca diretório de outra feature.** Nem de `specs_v6/`, nem de
   outra pasta de `specs_v7/`.
5. **Nenhum arquivo de escrita única é editado.** `console/src/i18n/*.ts`,
   `console/src/shell/routes.ts` e `console/visual/screens.json` são **lidos**,
   nunca escritos, por esta feature.
6. **Vermelho antes de allowlist.** Uma regra transversal cuja allowlist nasceu
   junto com ela é uma regra que ninguém viu funcionar.
7. **A credencial de staging nunca é impressa, gravada nem passada como
   argumento.** Se ela aparecer em qualquer saída de qualquer tarefa, a tarefa
   falhou.

## Phase 0: Linha de base

- [x] T001 Rodar a verificação completa do repositório na árvore intacta e
      guardar o log **fora do repositório**. Registrar, do próprio log: exit
      status, contagem de testes que passam e a lista dos que falham, se houver.
      **Sem este log, uma falha preexistente é debitada desta feature e uma falha
      desta feature se esconde atrás de "já estava assim".** Se a linha de base
      não estiver verde, parar e reportar antes de escrever qualquer coisa.
- [x] T002 Registrar as contagens de partida a partir da árvore, não de um
      documento: versão declarada no cabeçalho da constituição; número de
      arquivos de registro de decisão no diretório; número de linhas no índice de
      registros; número de linhas na tabela de traceability do roadmap; número de
      regras na suíte transversal e número de entradas na sua tabela de exceções;
      número de backings que a validação de navegador conhece. Esses sete números
      são o "antes" contra o qual esta feature é medida.

## Phase 1: A emenda pendente

Nenhum arquivo desta fase é committed.

- [x] T003 Auditar os quatro artigos que a orientação local acusa de exemplos
      defasados — o de runtime canônico, o de capacidades, o de datastore único e
      o de test-first —, **exemplo por exemplo**, contra a árvore. Para cada
      exemplo, registrar um resultado: corrigido (com o antes e o depois) ou
      conferido e correto (com o que foi conferido e onde). "Conferido e correto"
      é resultado aceitável; artigo sem resposta não é. Dois pontos de partida já
      conferidos na preparação desta spec, a reconferir e não a re-derivar: os
      cinco portos de persistência que o artigo de datastore nomeia existem em
      `platform/persistence/ports/`, e o adaptador de runtime alternativo que o
      artigo de runtime dá como exemplo existe em `core/agent/adapters/`.
- [x] T004 Acrescentar ao artigo de capacidades a cláusula de paridade: paridade
      por integração embarcada, inalterada em forma — os sete artefatos, todos,
      para toda integração do catálogo — e amplitude estagiada por ambiente capaz
      de validar a integração ponta a ponta, com as três condições (credencial
      armazenada, conexão verificada, ao menos uma leitura real exercitada). **Sem
      afirmar total.** O artigo hoje não tem cláusula de paridade nenhuma: isto é
      um acréscimo, não uma reescrita, e o sumário de emenda diz isso — senão o
      próximo leitor procura a diferença e não a encontra.
- [x] T005 Aplicar as correções que T003 tiver acusado. Se T003 não acusou
      nenhuma, registrar isso explicitamente e não inventar edição.
- [x] T006 Subir a versão da constituição para 2.1.0 e escrever a entrada de
      emenda no cabeçalho: data, o que mudou em uma linha, e o registro de decisão
      que a motiva — que já existe e é o registro vigente sobre paridade. Nenhum
      registro novo é escrito para esta emenda; ela é a metade que faltou de uma
      decisão já aceita.
- [x] T007 Conferir que o arquivo continua fora de qualquer commit: o caminho da
      constituição não aparece em nada que esta feature esteja preparando para
      commitar.

## Phase 2: Composto ou não foi entregue

- [x] T008 Escrever o registro de decisão arquitetural novo, com o próximo número
      livre da série, no diretório de registros. Ele decide três coisas: (a) todo
      mecanismo mergeado é alcançável a partir de uma composition root de serving,
      ou o próprio módulo declara que está dormente e nomeia o que o ligaria; (b)
      um símbolo construído apenas por testes não é uma entrega; (c) o fechamento
      de toda feature inclui evidência do caminho de serving para o comportamento
      novo — o harness prova a peça, nunca a composição. Traz driver, alternativas
      consideradas e consequências, na estrutura que os registros existentes usam.
      **É committed e precisa se sustentar sozinho**: enuncia a regra inteira em
      substância, sem número de artigo, sem identificador de requisito e sem
      caminho de planejamento, e sem pedir ao leitor nenhum documento que não veio
      no clone.
- [x] T009 No campo de impacto normativo do registro novo, nomear o que a decisão
      governa **em palavras** — entrega e composição —, seguindo a forma dos
      registros existentes sem copiar deles a citação por número.
- [x] T010 Registrar no corpo do registro novo, como driver, a forma de falha que
      o motiva: cinco mecanismos independentes mergeados sem caminho de produção,
      com o mesmo desfecho em todos — plano aprovado, testes verdes, verificação
      completa passando, fio nunca ligado. Descrever a forma, não os números de
      onda nem os nomes dos documentos onde ela foi catalogada.
- [x] T011 Acrescentar o artigo novo à constituição local: composto ou não foi
      entregue, com as três cláusulas de T008 em texto normativo, cada uma
      enunciada em termos observáveis — o que precisa existir e o que serve de
      evidência. Acrescentar a linha correspondente ao índice de artigos do
      próprio documento, com o teste de uma linha: *quem constrói isso em
      produção, e onde?*
- [x] T012 Subir a versão da constituição para 2.2.0 e escrever a **segunda**
      entrada de emenda no cabeçalho, com data, sumário e ponteiro para o registro
      novo. Duas emendas nesta feature são duas linhas de histórico, não uma.

## Phase 3: Higiene dos registros de decisão

- [x] T013 Alterar **apenas a linha de status** do registro de paridade total:
      passa a constar como revertido pelo registro que o supersede, com data e
      ponteiro. O corpo não é tocado — um registro revertido continua explicando
      por que a decisão foi tomada então, e essa é a única razão de ele continuar
      no repositório.
- [x] T014 Completar o índice de registros com os quatro registros que existem
      sem linha e com o registro novo desta feature: cinco linhas. Cada linha traz
      número, título, status e o que a decisão governa **em palavras**.
- [x] T015 Atualizar no índice o status do registro revertido.
- [x] T016 Completar a tabela de traceability do roadmap committed com as mesmas
      cinco entradas, na forma que aquela tabela usa.
- [x] T017 Conferir a aritmética contra o diretório: todo arquivo de registro tem
      exatamente uma linha em cada uma das duas tabelas, nenhuma linha aponta para
      arquivo inexistente, e as duas tabelas cobrem o mesmo conjunto. Registrar os
      três números (arquivos, linhas no índice, linhas na traceability) e conferir
      que fecham. **As onze linhas preexistentes do índice não são reescritas.**

## Phase 4: O ponteiro que o registro de paridade faz

- [x] T018 Escrever no roadmap committed a seção de escopo de integrações que o
      registro de decisão vigente sobre paridade nomeia como o lugar onde a
      amplitude corrente é lida — hoje essa seção **não existe**, e o ponteiro que
      um documento committed faz não resolve. A seção nomeia o conjunto embarcado
      derivado da árvore (não copiado de documento: os pacotes de vendor que
      `integrations/` de fato contém) e registra o conjunto diferido com a
      condição que o traz de volta.
- [x] T019 Conferir que o registro histórico de amplitude que o roadmap já guarda
      continua legível e não foi reescrito. Uma checagem de arquitetura já isenta
      deliberadamente o roadmap de citar um total antigo, com a razão escrita nela
      mesma — a seção nova convive com o histórico, não o substitui. Rodar essa
      checagem e confirmar verde.

## Phase 5: Os bans transversais — vermelho primeiro

- [x] T020 Criar o cenário de dados que reproduz as telas violadoras: declará-lo
      no manifesto de cenários derivando do cenário cheio, e escrever **só** os
      arquivos dos endpoints que precisam mudar. As cinco formas a reproduzir, com
      as fontes exatas que o diagnóstico registrou no staging: um `summary`
      começando com `###` e contendo `**` e crase; um identificador de incidente
      composto e percent-encoded chegando onde a tela põe título; uma linha-meta
      de lista com sujeito e duração ambos ausentes; um run com estado terminal
      cujo payload ainda carrega o estado de run em curso; e uma leitura de painel
      que falha, de modo que a tela derive dela uma afirmação negativa. A
      descrição do cenário no manifesto diz, em uma frase, que ele existe para dar
      dentes às regras — e é o que os testes chamam, não uma cópia de produção.
- [x] T021 [P] Extrair os detectores para um módulo próprio ao lado da suíte
      transversal: um detector por regra, puro — texto entra, violação sai —,
      chamável tanto pela varredura de navegador quanto por um teste
      determinístico. A varredura fica com o que só o navegador sabe: quais rotas
      existem e o que a página desenhou.
- [x] T022 Escrever a regra de markdown cru na suíte transversal, **com a
      allowlist vazia**, varrendo as rotas do grupo "Now" lidas do manifesto de
      rotas do produto. A mensagem de falha nomeia rota, regra e trecho ofensor.
- [x] T023 Escrever a regra de identificador no papel de nome, com a allowlist
      vazia. Cobre hexadecimal nu, identificador composto e identificador
      percent-encoded, em título de página, coluna-sujeito de lista e trilha.
- [x] T024 Escrever a regra de dois placeholders na mesma linha-meta, com a
      allowlist vazia. Uma linha de metadados — subtítulo de página ou linha de
      lista — admite no máximo um slot em fallback.
- [x] T025 Escrever a regra de controle de run vivo em run terminado, com a
      allowlist vazia. Cobre tanto o controle quanto o distintivo de run em curso.
- [x] T026 Escrever a regra de afirmação negativa depois de leitura falhada, com
      a allowlist vazia.
- [x] T027 Fazer a varredura alcançar as telas de detalhe de run e de incidente
      **seguindo a primeira linha da lista correspondente**. Nenhum identificador
      de run nem de incidente é escrito literalmente no arquivo de teste — um
      identificador literal é uma dependência de dataset disfarçada, que quebra
      quando o cenário muda e mente quando o mesmo identificador existe com outro
      conteúdo.
- [x] T028 Declarar o viewport de medição das regras novas: 1920×1080, lido das
      mesmas constantes nomeadas de onde a suíte já lê o seu viewport, nunca
      repetido como literal.
- [x] T029 **Portão.** Rodar a suíte transversal contra o cenário violador, com
      as cinco allowlists ainda vazias, e capturar o vermelho de cada uma das
      cinco regras com a **mensagem real**. Nenhuma allowlist é escrita antes
      disto. Se uma regra não ficar vermelha, ela não está medindo o que diz
      medir — corrigir a regra, não o cenário.
- [x] T030 Escrever as nove entradas de allowlist, uma por par rota × regra, na
      tabela que a suíte já usa para exceções. Cada entrada nomeia a rota, a
      regra, a razão em substância — o que a tela faz hoje que viola — e o que a
      remove, dito como trabalho ("a separação entre a sentença de manchete e o
      documento de relato"), **nunca** como número de feature. Rodar contra o
      dataset determinístico da árvore e confirmar verde.
- [x] T031 [P] Escrever o teste determinístico dos detectores, no lugar onde o
      runner de unidade do console coleta: cada detector recebe os textos exatos
      que o diagnóstico registrou no staging e precisa acusar; recebe os textos
      limpos equivalentes e precisa absolver. É o que mantém a regra provada todo
      dia, e não só no dia em que alguém apontou a suíte para o cenário violador.
      Confirmar que ele falha se o detector for neutralizado, e registrar como
      isso foi confirmado.

## Phase 6: O backing que não sobe nada

- [x] T032 Declarar as constantes novas no tier de constantes: o nome da variável
      que carrega o endereço do staging, o nome da variável que carrega a
      credencial de operador, o nome da variável que carrega o diretório de
      evidência, o endereço conhecido como padrão, e a grafia única da marca que
      declara um teste seguro para ambiente compartilhado. Rodar o guarda de
      constantes e confirmar que ele fica verde — nome de variável de ambiente
      fora deste tier é o que ele existe para reprovar.
- [x] T033 Escrever os testes de recusa do backing novo, **antes** de ele
      funcionar, e confirmá-los vermelhos: (a) sem credencial no ambiente, o
      comando recusa nomeando a variável que falta e não provisiona navegador; (b)
      um argumento que só faz sentido para um backing que sobe ambiente é recusado
      em vez de ignorado; (c) o backing novo não inicia plano de dados, não serve
      console local e não constrói.
- [x] T034 Escrever o teste, também vermelho primeiro, de que a seleção contra o
      backing novo é a interseção do que foi pedido com o que foi marcado: um
      teste não marcado como seguro para ambiente compartilhado não roda lá **nem
      quando é nomeado explicitamente**.
- [x] T035 Implementar o backing novo no harness de navegador: recebe o endereço
      do ambiente com o padrão conhecido, recebe a credencial do ambiente, e
      aponta o navegador direto para esse endereço — sem plano de dados, sem
      console local, sem construção. A credencial é repassada pela variável que a
      suíte de navegador já lê para o backing que precisa de credencial real: o
      caminho existe, e reusá-lo é uma superfície a menos.
- [x] T036 Garantir que a credencial não vaza: não é impressa na linha que anuncia
      contra o que o navegador está rodando, não é gravada em arquivo nenhum e não
      entra em argumento de processo. A linha de anúncio nomeia o endereço e nada
      mais.
- [x] T037 Expor a opção nova na linha de comando da validação de spec, com as
      recusas de T033 e T034 ligadas ali também, e sem construir o console quando
      o backing é este.
- [x] T038 Marcar como seguros para ambiente compartilhado **apenas** os testes
      das cinco regras novas da suíte transversal, e enunciar o significado da
      marca onde ela é declarada: leitura e fluxo de proposta, nunca escrita nem
      destruição de dados. A marcação é por teste, nunca por arquivo — as demais
      regras da suíte medem coisas que dependem dos dados do deployment e não
      fazem sentido contra um ambiente vivo.
- [x] T039 Fazer a marca ter uma grafia só: a suíte lê a grafia da mesma camada de
      constantes onde T032 a declarou, pela mesma técnica de leitura de texto que
      ela já usa para o viewport normativo. Duas grafias de uma marca de seleção
      não falham — elas selecionam zero testes e reportam sucesso, que é o pior
      resultado disponível.
- [x] T040 Fazer a execução contra staging produzir uma captura de página inteira
      por rota varrida, no diretório de evidência que o chamador nomear, do mesmo
      run. Sem segunda passada manual.
- [x] T041 Confirmar que T033 e T034 passaram a verde e que a checagem de
      fronteira do console continua verde — a suíte lê a camada de constantes por
      texto, não por import, e a fronteira depende disso.

## Phase 7: A orientação local

- [x] T042 Reescrever a seção de estado do repositório da orientação local para
      descrever o estado pós-v6: o que as ondas anteriores entregaram, onde estão
      as specs da onda corrente, e a versão da constituição **como ela ficou ao
      final desta feature**. Remover toda afirmação de emenda que não esteja
      escrita no arquivo. O documento não é committed.

## Phase 8: Fechamento

- [x] T043 Rodar a suíte transversal completa contra o dataset determinístico da
      árvore e confirmar verde, com as cinco regras ativas e as nove entradas de
      allowlist declaradas. Registrar o número de entradas — é o número que cada
      slot seguinte precisa fazer cair.
- [x] T044 Rodar a suíte transversal contra o **staging real**, pelo backing novo,
      com a credencial no ambiente. Confirmar: um teste de leitura passa lá; nada
      foi construído; nada foi iniciado; o diretório de evidência tem uma captura
      por rota varrida. Guardar as capturas em `evidence/` desta feature.
- [x] T045 Buscar a credencial de staging na saída completa do run de T044 e
      confirmar que ela não está lá. Se estiver, é defeito desta feature e não
      passa.
- [x] T046 Rodar a verificação completa do repositório e comparar, alvo por alvo,
      com o log de T001. Todo alvo que passava continua passando. Qualquer
      diferença é explicada ou corrigida, nunca omitida. Registrar também o efeito
      medido sobre a suíte de cenários sintéticos: esta feature não toca prompt,
      capacidade, pipeline nem provedor, e o efeito esperado é nulo — "sem efeito"
      é resultado aceitável, "não medido" não é.
- [x] T047 Atualizar o `controle.md` desta feature com o que o código prova: os
      sete números de partida de T002 e os de chegada; o resultado por artigo da
      auditoria de T003; o vermelho capturado de cada uma das cinco regras em
      T029, com a mensagem real; o número de entradas de allowlist; a evidência do
      run contra staging; e toda ressalva de honestidade — inclusive qualquer
      teste cujo vermelho não foi visto antes da implementação, e por quê.
      Registrar também, como observação de verificação e não como conserto, o que
      esta feature encontrou e **não** consertou: o passe editorial das onze
      linhas preexistentes do índice, que citam número de artigo, e os corpos de
      registros já aceitos que fazem o mesmo.

## Phase 9: Se sobrar folga (opcional)

- [x] T048 Documentar a remoção do deployment de console legado que continua de pé
      no cluster ao lado do console servido: nomear o repositório de GitOps, o
      caminho do workload e o comando. **A execução é do operador** — é um commit
      fora desta árvore, e esta feature não altera nada fora dela. A tarefa
      entrega o texto no relatório final; não pretende ter executado nada.

## Dependencies

- T001 → T002 → tudo. A linha de base precede qualquer escrita.
- Fase 1 é independente das Fases 3 a 6; T004 depende de T003 (a auditoria diz o
  que o artigo já tem antes de ele ganhar cláusula); T006 depende de T004 e T005.
- Fase 2 depende da Fase 1 apenas na ordem do cabeçalho: T012 escreve a segunda
  entrada de emenda e precisa que T006 tenha escrito a primeira. T008, T009 e T010
  podem correr antes.
- T013 é independente; T014 depende de T008 (o registro novo precisa existir para
  ter linha); T015 depende de T013; T016 depende de T014 e T015; T017 depende de
  T016.
- Fase 4 é independente das Fases 1 a 3 e pode correr a qualquer momento; T019
  depende de T018.
- T020 e T021 são paralelas entre si. T022..T026 dependem de T021. T027 e T028
  valem para as cinco regras e podem entrar junto de T022.
- **T029 é portão**: nenhuma entrada de allowlist é escrita antes do vermelho
  capturado. T030 depende de T029. T031 depende de T021 e pode correr em paralelo
  com T029.
- T032 precede T033..T037. T033 e T034 precedem T035 (vermelho antes de verde).
  T036 depende de T035. T038 e T039 dependem de T032. T040 depende de T035 e da
  Fase 5. T041 depende de T035, T037 e T039.
- Fase 7 depende de T012 (a versão que a orientação afirma é a do arquivo) e de
  T017.
- T043 depende da Fase 5 inteira. T044 depende de T043 e da Fase 6 inteira. T045
  depende de T044. T046 depende de tudo. T047 é a última das obrigatórias.
- T048 depende de nada e é a última do arquivo.
