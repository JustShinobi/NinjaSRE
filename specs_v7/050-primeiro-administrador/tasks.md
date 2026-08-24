# Tasks: Primeiro administrador — um deployment novo produz o seu

**Input**: Design documents from `specs_v7/050-primeiro-administrador/`

**Prerequisites**: spec.md, plan.md. Nenhuma feature desta onda bloqueia esta.
Slot S4, em par com a 060.

**Tests**: test-first, sem exceção. Cada comportamento novo tem um teste que
falha **antes** da implementação, e o vermelho é capturado com a mensagem real
no `controle.md`. Um teste escrito depois do fato não distingue "funciona" de
"o teste não olha".

## Regras que valem para toda tarefa deste arquivo

1. **Nada de identificador de planejamento em arquivo committed.** Nenhum
   teste, comentário, docstring, migração, mensagem de erro, documento gerado
   ou mensagem de commit cita identificador de requisito, número de artigo,
   número de feature ou caminho de diretório de planejamento. A substância vai
   no arquivo committed; a referência fica nesta spec.
2. **Esta feature não é dona dos arquivos de escrita única do slot.** Nenhuma
   tarefa edita `console/src/i18n/en.ts`, `console/src/i18n/pt-BR.ts`,
   `console/src/shell/routes.ts` ou `console/visual/screens.json`. As chaves
   novas são **declaradas no relatório final**, com texto en e pt-BR, e
   referenciadas pela chave no código. O merge do slot aplica.
3. **Nenhuma tarefa toca outro diretório de feature.**
4. **Nenhuma passphrase em log, auditoria, saída de comando, resposta HTTP,
   argumento de linha de comando ou variável de ambiente lida por conta
   própria.** Se uma tarefa parecer exigir isso, ela está errada.
5. **Nenhuma rota não autenticada nova que crie administrador.** A única rota
   pública nova é a de disponibilidade, que lê um fato ternário e não escreve
   nada.
6. **Mensagem de erro nomeia o que fazer.** Nenhuma mensagem de produto contém
   nome de índice, nome de constraint, nem texto de exceção do driver.
7. **"Testes verdes no harness" não fecham tarefa de comportamento.** As
   tarefas marcadas **[serving]** só fecham com evidência de um deployment de
   compose ou do staging.

---

## Phase 0: Linha de base

- [x] T001 Rodar `make verify` na árvore intacta e guardar o log fora do
      repositório. Registrar do próprio log: exit code, contagem de testes que
      passam, e quais falham. Sem esta linha de base, uma falha preexistente é
      debitada desta feature e uma falha desta feature se esconde atrás de "já
      estava assim". Se a linha de base não estiver verde, parar e reportar
      antes de escrever qualquer coisa.

- [x] T002 Registrar, a partir do banco de staging e não de um documento: se
      `NINJASRE_LOCAL_ACCOUNT_PASSWORD_HASH` está configurado no deployment de
      staging, quantos principals existem, quantos deles têm endereço vazio, e
      qual é o estado ativo da configuração de single sign-on. Esses quatro
      números são o "antes" contra o qual a preservação da conta local do
      staging é medida.

- [x] T003 Levantar um deployment limpo por `deploy/compose/docker-compose.yml`
      **sem** `NINJASRE_LOCAL_ACCOUNT_PASSWORD_HASH`, capturar a saída do
      primeiro start e a tentativa de sign-in que falha. Este é o defeito, na
      forma em que ele aparece para quem instalou. A captura vai para
      `evidence/` da feature e é o "antes" do DoD.

---

## Phase 1: Testes vermelhos — a porta e o comando

Todas as tarefas desta fase escrevem teste contra a árvore atual e **têm de
falhar**. O vermelho de cada uma é capturado com a mensagem real.

- [x] T004 Em `tests/unit/platform/identity/`, teste: um deployment sem conta
      de ambiente e **com** administrador local habilitado aceita o sign-in
      desse administrador. Vermelho: hoje a ausência de conta de ambiente
      recusa todo mundo.

- [x] T005 [P] No mesmo lugar, teste: um deployment sem conta de ambiente e sem
      abertura registrada recusa **também** um principal criado pela rota de
      identidade, com a recusa única de sempre. Este teste guarda a invariante
      e precisa passar antes **e** depois.

- [x] T006 [P] Teste: criar um principal pela rota de identidade **não**
      registra abertura. Guarda a segunda metade da invariante.

- [x] T007 [P] Teste: a conta de ambiente continua sendo resolvida na
      construção, e um deployment que não se declara demonstração carregando a
      passphrase embarcada continua se recusando a subir. Guarda a terceira
      invariante; precisa passar antes e depois.

- [x] T008 [P] Teste: com abertura registrada e sem conta de ambiente, o
      caminho de recusa faz o mesmo número de verificações de passphrase que
      faz hoje. Escrito como contagem observável, não como medição de tempo de
      parede.

- [x] T009 [P] Teste: a abertura é lida por tentativa de sign-in — registrar a
      abertura com o objeto de sign-in já construído passa a permitir a entrada
      sem reconstruir nada.

- [x] T010 Em `tests/unit/platform/identity/`, teste da criação de
      administrador: cria o usuário, armazena a passphrase pela mesma
      construção de hash da conta de ambiente, concede a permissão de dono,
      registra auditoria sem a passphrase, e registra a abertura quando é a
      primeira.

- [x] T011 [P] Teste: criar administrador com um nome que já existe é recusado,
      e a recusa diz como rotacionar.

- [x] T012 [P] Teste: rotação explícita troca a passphrase; a nova entra, a
      antiga é recusada.

- [x] T013 [P] Teste: criar um segundo administrador num deployment já
      administrado funciona e **não** cria uma segunda abertura.

- [x] T014 [P] Teste: com o identity provider ativo, a criação de administrador
      é recusada, a recusa nomeia o caminho de emergência, e não existe opção
      de override.

- [x] T015 Em `tests/unit/surfaces/cli/commands/test_setup.py`, testes do
      comando: pergunta a passphrase sem eco, pede confirmação, recusa quando
      as duas não coincidem, não aceita passphrase por argumento, não lê do
      ambiente, recusa sem terminal interativo nomeando a alternativa, e
      distingue "banco não alcançado" de "passphrase não serve".

- [x] T016 [P] Teste: a saída do comando, em texto e em dados, não contém a
      passphrase nem o hash dela.

---

## Phase 2: Testes vermelhos — persistência, corrida e e-mail

- [x] T017 Em `tests/contract/persistence/test_identity_repository.py`, teste
      rodando contra **os dois backends**: dois principals sem endereço no mesmo
      deployment são criados com sucesso. Vermelho contra Postgres com a
      violação real, capturada.

- [x] T018 [P] No mesmo arquivo, teste: a busca por endereço com endereço vazio
      não devolve um principal sem endereço.

- [x] T019 [P] No mesmo arquivo, teste: dois principals com o mesmo endereço em
      caixas diferentes colidem, e a colisão sai como erro de domínio nomeando
      o endereço — sem nome de índice, sem nome de constraint, sem texto do
      driver.

- [x] T020 Em `tests/contract/persistence/`, teste de concorrência contra o
      Postgres real da suíte: N tentativas simultâneas de criar o primeiro
      administrador produzem exatamente uma abertura registrada e N-1 recusas
      legíveis. O teste falha se qualquer recusa carregar texto de driver.

- [x] T021 [P] Teste: duas réplicas simuladas subindo juntas contra o mesmo
      banco, com uma delas já tendo aberto a porta, não produzem dois convites
      impressos.

- [x] T022 Em `tests/unit/platform/startup/test_bootstrap.py`, testes do
      gating: nenhuma credencial de bootstrap é emitida quando há abertura
      registrada; nenhuma é emitida quando o identity provider está ativo; e a
      idempotência que já existe continua valendo nos casos em que a emissão
      ainda acontece.

- [x] T023 [P] Teste do convite: o bloco impresso nomeia o comando completo, e
      **não** afirma que a credencial serve para o formulário de sign-in. O
      teste procura a afirmação falsa de hoje e exige a ausência dela.

- [x] T024 [P] Teste de que a credencial de bootstrap continua não aparecendo
      em log nem em auditoria — o teste de segurança que já existe é estendido
      para cobrir os caminhos novos, não substituído.

---

## Phase 3: Testes vermelhos — o seam e o console

- [x] T025 Em `tests/contract/deployment/test_first_run_sign_in.py`, teste do
      seam: a troca da credencial de bootstrap cria um administrador com
      passphrase, devolve o token durável, e o nome e a passphrase escolhidos
      são **aceitos pelo sign-in** logo em seguida. É o teste que transforma
      "tenho uma credencial" e "consigo entrar" em um fato só.

- [x] T026 [P] Teste: a troca sem passphrase é recusada.

- [x] T027 [P] Teste: o administrador criado pela troca e o dono do token
      durável são o mesmo principal.

- [x] T028 [P] Teste: a troca é recusada quando já há abertura registrada,
      mesmo com o arquivo de credencial presente no host.

- [x] T029 [P] Teste: a troca é recusada com identity provider ativo.

- [x] T030 [P] Teste: a ordem preservada — a credencial antiga só é revogada
      depois de a substituta existir — e a segunda troca com a mesma credencial
      continua recusada.

- [x] T031 [P] Teste da tabela de rotas: a rota de disponibilidade está
      declarada, é pública por declaração, e a permissão exigida pela rota de
      troca não foi alargada.

- [x] T032 Escrever `console/tests/e2e/primeiro-administrador.acceptance.spec.ts`
      codificando as **dez alegações normativas** da spec, uma asserção por
      alegação, a 1920×1080. Marcar como staging-safe apenas as alegações 5, 6,
      7, 8 e 10. Rodar e **capturar o vermelho** antes de tocar em qualquer
      arquivo de tela.

- [x] T033 [P] Em `console/tests/unit/`, testes do bloco de aviso: aparece no
      estado sem administrador, não existe no documento nos outros dois
      estados, o comando é literal e não passa pelo catálogo de tradução, e a
      região é selecionável.

- [x] T034 [P] Em `console/tests/unit/`, teste-guarda: a recusa de sign-in é
      byte-a-byte a que já existe, e o bloco de aviso não a altera, não a
      substitui e não a enriquece.

---

## Phase 4: Persistência — o registro e o índice

- [x] T035 Declarar na porta de identidade a operação de ler e a de registrar a
      abertura do sign-in local, com o registro carregando quando aconteceu e
      por qual caminho. Declarar também, na própria porta, que a ausência de
      endereço é um valor legítimo e não participa da unicidade — hoje o tipo
      não dá nenhuma dica disso e o primeiro service account leva o vazio.

- [x] T036 Implementar as duas operações no fake, com a unicidade da abertura
      valendo lá também.

- [x] T037 Implementar as duas operações no repositório Postgres. A inserção da
      abertura não sobrescreve e é seguida de leitura de volta: quem leu a linha
      de outro perdeu a corrida.

- [x] T038 Escrever a revisão de migração que cria a tabela da abertura, com
      chave primária por deployment e `downgrade` que a remove.

- [x] T039 Escrever a revisão de migração que tira os principals sem endereço da
      unicidade: a dobra do endereço passa a ficar ausente quando não há
      endereço, e o índice único passa a ignorar as ausências. Os dados
      existentes são convertidos na subida.

- [x] T040 Escrever o `downgrade` dessa segunda revisão: ele reconverte e
      recria a unicidade total quando os dados permitem, e **recusa nomeando os
      principals que impedem a volta** quando não permitem, dizendo o que fazer
      com eles. Nenhuma linha é apagada por conta própria.

- [x] T041 Ajustar o repositório Postgres para escrever a dobra ausente quando
      não há endereço, e a busca por endereço para não casar com essas linhas.
      Ajustar o fake para o mesmo comportamento — a suíte de contrato roda
      contra os dois e é ela que prova que não divergiram.

- [x] T042 Fazer a colisão real de endereço sair pela fronteira que já traduz
      violações em erros de domínio, com mensagem que nomeia o endereço. A
      verificação prévia na rota de identidade fica onde está: ela cobre o caso
      comum, a tradução cobre a corrida.

- [x] T043 Confirmar T017–T019 verdes contra os dois backends, e registrar a
      mensagem de colisão exata no `controle.md`.

---

## Phase 5: A regra — a porta e a criação de administrador

- [x] T044 Criar o módulo de identidade que concentra a regra: ler a abertura,
      registrar a abertura, criar administrador, rotacionar passphrase. Um lugar
      só, porque tem dois clientes de produção — o CLI e a rota de troca — e
      nenhum dos dois pode possuí-la.

- [x] T045 Usar, para a exclusão do caminho de criação, o mesmo tipo de
      exclusão que o boot já usa para as migrações, com chave própria declarada
      junto das outras. Não inventar um segundo mecanismo de coordenação.

- [x] T046 Ler o estado ativo do identity provider da mesma fonte que o console
      já lê, pelo serviço de configuração. Não introduzir uma segunda noção de
      "tem identity provider".

- [x] T047 Escrever as recusas novas como erros de domínio com mensagem para
      gente: deployment já administrado, identity provider é a porta deste
      deployment (nomeando o caminho de emergência), nome já existe (dizendo
      como rotacionar), corrida perdida.

- [x] T048 Redefinir a porta em `platform/identity/local_accounts.py`: o ramo
      que hoje recusa por ausência de conta de ambiente passa a recusar por
      ausência de abertura **ou** conta de ambiente, com a mesma recusa única, o
      mesmo silêncio sobre qual credencial foi tentada, e um desfecho de
      auditoria distinguível para o caso novo. Preservar o raciocínio escrito no
      módulo, reescrito para o fato novo — não apagá-lo.

- [x] T049 Manter a resolução da conta de ambiente na construção do processo, e
      a leitura da abertura por tentativa. Confirmar T004–T009 verdes, T005 e
      T007 continuando verdes.

---

## Phase 6: O comando

- [x] T050 Implementar `ninjasre setup admin` em
      `surfaces/cli/commands/setup.py`, usando o `store_factory` que os outros
      comandos de setup já usam: nome por opção, passphrase perguntada sem eco e
      confirmada, recusa sem terminal interativo, rotação por opção explícita.

- [x] T051 **[composição]** Confirmar que o comando está alcançável no CLI que a
      imagem distribui — o grupo `setup` já está registrado, e a tarefa fecha
      exercitando `ninjasre setup admin --help` **dentro do container do
      compose**, não no ambiente de desenvolvimento.

- [x] T052 Confirmar T010–T016 verdes.

---

## Phase 7: O boot, o convite e o seam

- [x] T053 Colocar o texto do comando canônico num lugar só, junto das outras
      constantes de first-run, para que o convite impresso, a mensagem da tela e
      a documentação não possam divergir em redação.

- [x] T054 Gatear a emissão da credencial de bootstrap: nada é emitido quando há
      abertura registrada, nada é emitido quando o identity provider está ativo.
      Preservar a idempotência existente nos casos em que a emissão acontece.

- [x] T055 Reescrever o bloco impresso no boot: ele nomeia o comando completo e
      **deixa de afirmar** que a credencial serve para o formulário de sign-in.
      Continua impresso e não logado.

- [x] T056 Fazer a troca da credencial de bootstrap criar um administrador com
      passphrase além do token durável, pelo mesmo módulo de regra do comando —
      não por uma segunda implementação. A passphrase é obrigatória; sem ela a
      troca recusa.

- [x] T057 Recusar a troca quando já há abertura registrada e quando o identity
      provider está ativo, preservando a ordem de revogação e a recusa da
      segunda troca.

- [x] T058 Regenerar o contrato HTTP publicado e conferir que a mudança da rota
      de troca aparece nele.

- [x] T059 Confirmar T022–T031 verdes.

---

## Phase 8: O console

- [x] T060 Declarar e servir a rota pública de disponibilidade: um fato
      ternário — sem administrador, administrado, identity provider — sem nome
      de deployment, sem versão, sem organização, sem contagem de nada.
      Registrar na tabela de rotas como pública por declaração.

- [x] T061 Ler esse fato no console pela leitura sem cache que já existe, e não
      por uma segunda forma de falar com o gateway.

- [x] T062 Acrescentar o bloco de aviso à tela de sign-in, acima do formulário,
      com o comando como texto literal copiável. O formulário continua com dois
      campos e um botão. Nenhum arquivo de escrita única é editado: as chaves
      novas são referenciadas e declaradas no relatório.

- [x] T063 Acrescentar o mesmo bloco à tela de first-run, no mesmo estado, pela
      **mesma chave** — não por uma segunda redação.

- [x] T064 Confirmar T032–T034 verdes contra o backing de compose. As alegações
      que dependem de um deployment sem administrador não rodam contra o
      staging, e o spec as marca.

- [x] T065 Escrever, para o relatório final, o bloco de chaves i18n novas com
      texto en e pt-BR, na forma que o merge do slot aplica sem editar nada
      mais. O nome do comando não é traduzido em nenhuma das duas.

---

## Phase 9: Prova no caminho de serving

- [x] T066 **[serving]** Levantar um deployment limpo por compose, sem conta de
      ambiente configurada, e percorrer o caminho lendo **apenas** o que o
      terminal diz: subir, executar o comando nomeado, responder ao prompt,
      abrir o console, entrar. Capturar a transcrição completa da sessão de
      terminal e uma captura da tela autenticada em `evidence/`. Esta tarefa é
      o DoD da feature; nenhuma outra a substitui.

- [x] T067 **[serving]** No mesmo deployment, repetir o caminho que criou o
      administrador e capturar a recusa. Conferir que ela é uma frase de gente.

- [x] T068 **[serving]** No mesmo deployment, criar um segundo service account
      sem e-mail e capturar o sucesso.

- [x] T069 **[serving]** No mesmo deployment, ativar o identity provider e
      capturar as três recusas locais, mais a tela que deixa de nomear o
      comando.

- [x] T070 **[serving]** No mesmo deployment, subir e descer a migração de
      e-mail contra o banco com dados, capturando os dois resultados —
      inclusive a recusa nomeada, se for o caso.

- [x] T071 Anotar em `evidence/` a comparação com T003: o mesmo deployment,
      antes e depois, na forma em que ele aparece para quem instalou.

---

## Phase 10: Staging e fechamento

- [x] T072 **[serving]** Depois do `make deploy-stg` do slot (que é do
      orquestrador, não desta feature), conferir no staging que a conta local
      existente continua entrando, com o mesmo nome e a mesma passphrase. Uma
      feature de primeiro acesso que tranca o operador atual para fora falhou.

- [x] T073 **[serving]** Rodar contra o staging apenas os acceptance marcados
      como staging-safe, e anexar as capturas.

- [x] T074 Consultas de contagem no banco de staging para a evidência: quantas
      aberturas registradas existem, quantos principals sem endereço existem, e
      se algum principal ficou sem grant. As consultas exatas vão no
      `controle.md` junto dos resultados.

- [x] T075 Rodar `make verify` e comparar com a linha de base de T001. Verde,
      tendo partido de verde.
      → **Cumprida.** O log da linha de base foi produzido rodando o portão em
      `abbc418`, num worktree separado — a árvore intacta existe no git —
      e deu `MAKE_VERIFY_EXIT=0`, 12.247 passed, 0 failed
      (`specs_v7/060-o-catalogo-ensina/evidence/baseline-abbc418-make-verify.log.gz`,
      conferido descompactando e lendo o próprio log, não por citação). A
      comparação alvo por alvo está em
      `specs_v7/060-o-catalogo-ensina/controle.md`, seção "A comparação com a
      linha de base": todo alvo que passava continua passando, a suíte
      cresceu ~525 testes, e as diferenças que apareceram no caminho foram
      consertadas, cada uma no commit que a corrige. Conferido também por
      conta própria, nesta árvore: os dois vermelhos que essa mesma seção
      registrava como corrigidos por outro trabalho da onda —
      `test_dataset_coherence.py::test_rebuilding_the_dataset_reproduces_what_is_committed`
      e
      `test_onboarding_against_a_deployment.py::test_the_deployment_reads_as_ready_once_the_flow_has_run`
      — rodam verdes agora (`2 passed in 3.24s`), fechando o único ponto em
      aberto que a versão anterior deste arquivo citava para T075.

- [x] T076 Escrever o relatório final: o bloco de chaves i18n de T065, as
      questões abertas para o operador que a spec levanta, e a linha do
      confronto respondendo "quem constrói isso em produção?" com `file:line`
      para cada mecanismo novo — a tabela do plano é a fonte, mas a resposta é
      conferida contra o código que ficou, não contra o plano.

---

## Dependências entre tarefas

- T001–T003 antes de tudo.
- Fase 1, 2 e 3 são vermelhos e vêm antes das fases 4 a 8. Dentro de cada fase,
  as marcadas `[P]` são paralelizáveis entre si.
- T035–T037 antes de T038–T041; T038–T041 antes de T043.
- T044–T048 dependem de T035–T037 (a porta precisa existir para a regra lê-la).
- T050 depende de T044. T056 depende de T044 — a rota e o comando usam a mesma
  regra, e essa é a razão de T044 vir antes das duas.
- T060 depende de T044 (o fato servido é a leitura da abertura mais o estado do
  identity provider). T062–T063 dependem de T060–T061.
- Fase 9 depende de tudo. T072–T074 dependem do deploy do slot, que é do
  orquestrador.
- T075 e T076 por último, nessa ordem.
