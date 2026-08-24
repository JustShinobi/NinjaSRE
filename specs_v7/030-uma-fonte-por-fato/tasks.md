# Tasks: Uma fonte por fato

**Input**: Design documents from `specs_v7/030-uma-fonte-por-fato/`

**Prerequisites**: `spec.md`, `plan.md`. Depende da feature de governança da onda
(regras e suíte transversal) e do estado pós-merge do slot que tocou o detalhe
de incidente e a identidade endereçável.

**Tests**: test-first, sem exceção. O acceptance nasce vermelho e o vermelho é
registrado com a mensagem real antes de qualquer implementação. O gate de build
nasce reprovando. O teste de contagem de requisições nasce falhando contra o
comportamento atual — e se ele **passar** na primeira execução, isso é um achado
a registrar, não uma tarefa cumprida: significa que a causa nomeada no
diagnóstico não é a causa.

---

## Regras que valem para toda tarefa deste arquivo

1. **Nada de identificador de planejamento em arquivo committed.** Nenhum teste,
   comentário, docstring, mensagem de UI, documento ou mensagem de commit cita
   identificador de requisito, número de artigo da constituição, número de
   feature ou caminho de diretório de planejamento. A substância vai no arquivo;
   a referência fica nesta spec.
2. **Nenhum valor de credencial em lugar nenhum.** Nem em log, nem em teste, nem
   em fixture, nem em mensagem de erro, nem em evidência. O que pode ser escrito
   é nome de provider, nome de integração, identificador de time e a palavra
   "vault" ou "environment".
3. **"Teste verde no harness" não fecha tarefa de comportamento.** As três
   tarefas de composição só fecham com a evidência do caminho de serving que
   elas mesmas nomeiam.
4. **Esta feature é a dona dos arquivos de escrita única no slot** —
   `console/src/i18n/*.ts`, `console/src/shell/routes.ts`,
   `console/visual/screens.json`. Ela os edita. A feature par entrega as suas
   chaves como bloco no relatório final.
5. **Nenhuma tarefa toca outro diretório de feature.**
6. **Gate não é afrouxado para a mudança passar.** Se um orçamento reprovar, o
   defeito é da mudança, e a saída é reportar — nunca alargar o orçamento.
7. **Nenhum acceptance que escreve roda contra staging.** Os marcados
   staging-safe na spec são os únicos que vão para lá.
8. **Uma vírgula é fronteira de requisito.** Uma tarefa que faz duas coisas é
   duas tarefas.

---

## Phase 0: Linha de base

- [x] T001 Rodar `make verify` na árvore intacta e guardar o log **fora do
      repositório**. Registrar do próprio log: quantos testes passam, quais
      falham, e o tempo. Sem esta linha de base, uma falha preexistente é
      debitada desta feature e uma falha desta feature se esconde atrás de "já
      estava assim". Se a linha de base não estiver verde, parar e reportar
      antes de tocar em qualquer coisa.

- [x] T002 Medir a linha de base de latência: primeira pintura de `/incidents`,
      `/runs` e `/incidents/{id}`, a **1920×1080**, contra o backing de mock, 20
      loads por rota, p50 e p95. Guardar em `evidence/latency-before.md`. É o
      "antes" contra o qual a decisão de dinamismo é julgada, e sem ele a
      medição de depois não significa nada.

- [x] T003 Registrar o estado de partida das telas, do código e não de um
      documento: quais telas usam a causa de vazio, quantos valores tem o
      vocabulário de prontidão hoje, quais rotas sob o shell existem, e quais
      delas declaram dinamismo por si. Esses quatro números são o "antes" desta
      feature.

- [x] T004 **Diagnosticar a camada de cache real.** Com o console em produção
      contra o backing, comparar três formas de chegar a `/incidents`: reload
      duro, navegação suave pelo menu, e primeira visita. Para cada uma,
      registrar se o backing recebeu requisição. Escrever a conclusão em
      `evidence/cache-layer.md` nomeando a camada. **É uma tarefa de medição, e
      a resposta pode contradizer o diagnóstico da onda** — se contradisser, ela
      é registrada como está e o remédio das tarefas de rota é ajustado a ela,
      sem alterar as alegações que a spec exige.

**Checkpoint**: quatro artefatos de partida existem, e a causa das listas
congeladas está nomeada por medição em vez de por hipótese.

---

## Phase 1: Os testes que precisam falhar

Toda tarefa desta fase escreve teste contra a árvore atual e **tem de falhar**.
O vermelho de cada uma é capturado com a mensagem real e colado na tarefa.

### 1a. Instrumentação, sem a qual três alegações não têm teste honesto

- [x] T005 No plano de mock (`tools/mockplane/server.py`), contar as requisições
      por rota e por sessão, e servi-las numa rota de controle fora do espaço de
      caminhos do gateway. A rota de controle é do backing e não existe em
      produção; ela é resolvida **antes** do casamento de rota do gateway, e
      nunca colide com um caminho servido. Teste unitário Python do contador
      junto.

- [x] T006 No harness (`tools/console_e2e.py`), exportar o endereço do backing
      para o processo do Playwright, do mesmo jeito que a URL do console e a
      credencial já são exportadas, por uma constante declarada em
      `config/constants/`. Sem isso o acceptance não tem como perguntar ao
      contador.

- [x] T007 [P] No gate do console (`tools/console_gate.py`), adicionar o check
      que lê a saída do build de produção e reprova quando qualquer rota sob o
      shell consta como pré-renderizada. **Confirmar primeiro, contra uma saída
      de build real, qual arquivo de manifesto carrega esse fato e como ele
      nomeia as rotas** — não afirmar sobre um nome de arquivo presumido.
      Pendurar o check no alvo que constrói, e declará-lo "pulado por política"
      quando não houver build, como os dois checks que já dependem de
      infraestrutura fazem. Confirmar que ele **reprova** hoje, ou registrar que
      ele passa e por quê.

### 1b. O acceptance da feature

- [x] T008 Criar `console/tests/e2e/030-uma-fonte-por-fato.acceptance.spec.ts`
      com as alegações da spec, uma por bloco de teste, cada bloco nomeado pela
      frase que ele codifica. Marcar no próprio arquivo, por anotação de teste,
      quais são seguras contra ambiente compartilhado — leitura pura — e quais
      exigem o backing. Rodar e **confirmar vermelho**, colando aqui a mensagem
      de cada bloco que falhou.

- [x] T009 Estender `console/tests/e2e/transversal-rules.spec.ts` com o ban
      desta rodada: nenhuma tela imprime negativa de existência num painel cujo
      estado é de erro. A regra é da feature de governança; a asserção que a
      exercita é escrita aqui. Confirmar vermelho contra o detalhe de incidente
      atual.

### 1c. Unitários que fixam a verdade antes da mudança

- [x] T010 [P] `tests/unit/platform/startup/test_checklist.py`: o passo de
      provider reporta verificado quando existe um registro de verificação que
      passou, sem chamar o endpoint. Vermelho: hoje ele reporta guardado.

- [x] T011 [P] Mesmo arquivo: o passo de provider reporta falhando quando o
      último registro falhou. Vermelho: hoje não existe esse valor.

- [x] T012 [P] Mesmo arquivo: uma integração cujo último registro falhou é
      reportada como falhando, não como guardada. Vermelho pela mesma razão.

- [x] T013 [P] Mesmo arquivo: um registro de verificação ausente é reportado
      como não verificado, e um registro ilegível é tratado como ausente — nunca
      como falha. Deve **passar** já, e é a rede que pega a mudança inventando
      um vermelho que ninguém mediu. Registrar que passou e por quê.

- [x] T014 [P] `tests/unit/gateway/http/`: a resolução de handle de credencial
      devolve o handle do time que detém a credencial, e o handle org-wide
      quando ninguém a detém por time. Vermelho: a função não existe.

- [x] T015 [P] Mesmo lugar: com dois times detendo credencial para a mesma
      integração, a resolução devolve o handle org-wide e reporta a ambiguidade
      nomeando a integração. Vermelho pela mesma razão.

- [x] T016 [P] Mesmo lugar: o handle que a verificação resolve e o handle que o
      binding de ferramentas resolve são o mesmo, percorrendo o catálogo
      configurado. Vermelho: hoje um é o do caller e o outro é org-wide.

- [x] T017 [P] `console/tests/unit/surfaces/`: a causa de setup não é produzida
      num deployment com investigação concluída. Vermelho: hoje ela é produzida
      por contagem de passos pendentes.

- [x] T018 [P] Mesmo lugar: a causa de setup, quando produzida, nomeia o passo
      pendente que a justifica. Vermelho: hoje ela cita uma contagem.

- [x] T019 [P] Mesmo lugar: a derivação do chip de investigação devolve
      desconhecido quando a leitura falhou, e nomeia a dependência. Vermelho: a
      derivação não existe e o chip afirma o negativo.

- [x] T020 [P] Mesmo lugar: as três superfícies que citam progresso de setup
      citam o mesmo par de números. Caracterização — deve passar já, e é o que
      distingue "verifiquei e estava certo" de "presumi que a onda anterior
      resolveu". Registrar o resultado, seja qual for.

**Checkpoint**: todo teste desta fase existe, roda, e falha pela razão certa —
com as duas exceções declaradas (T013 e T020), cujo verde está registrado com o
motivo. Nada de implementação começou.

---

## Phase 2: Verdade de estado no backend

- [x] T021 Acrescentar o quarto valor ao vocabulário de prontidão em
      `config/constants/first_run.py`, ao lado dos três que já existem, com o
      comentário que diz por que ele é distinto de "guardada".

- [x] T022 Em `platform/startup/checklist.py`, derivar a prontidão do provider e
      das integrações de quatro entradas — registro que passou, registro que
      falhou, credencial presente, nada — por uma função só, usada pelos dois.
      O módulo continua sem alcançar o catálogo nem o registro por si: eles
      chegam por parâmetro, como as integrações já chegam.

- [x] T023 Em `platform/startup/checklist.py`, fazer o texto sob o passo de
      provider dizer o que o último check encontrou quando existe um, e que
      ninguém verificou quando não existe. A frase é do documento que o console
      renderiza, e não nomeia variável de ambiente nem instrução de deploy.

- [x] T024 Em `gateway/http/routes/first_run.py`, ler o registro de verificação
      de provider — pelo mesmo helper que já lê o de integração — e injetá-lo no
      builder. **Esta é uma tarefa de composição**: ela só fecha com a evidência
      de serving da Phase 5, não com o unitário verde.

- [x] T025 Ampliar o modelo de resposta do checklist para o quarto valor, sem
      renomear nem remover nenhum dos três existentes.

- [x] T026 Varrer quem lê a prontidão e tratar o quarto valor explicitamente: o
      console (first-run, dashboard, integrações) e o `doctor` do CLI. Um leitor
      que caísse no ramo errado por omissão é o defeito que esta feature
      existiria para não criar.

- [x] T027 Confirmar T010, T011, T012 e T013 verdes, e o passo de provider ainda
      **sem** chamada ao endpoint — a propriedade que o injetor de verificação
      protege e que esta mudança não pode gastar.

**Checkpoint**: o documento que o console lê diz a verdade sobre o provider.
`make verify` estreito no lado Python.

---

## Phase 2b: O vocabulário de estado de run tem um dono

Esta fase é gate-primeiro, migração-depois, purga por último. Uma migração
validada só depois do fato não distingue "migrei certo" de "o gate não olha".

- [ ] T060 Registrar o estado de partida a partir da **árvore**, não de um
      documento: todo valor de estado de run que qualquer fixture serve, o
      vocabulário que o console declara, e a enumeração que o gateway serve
      verbatim. Os três conjuntos, escritos lado a lado em
      `evidence/run-status-before.md`. É o "antes" contra o qual a migração é
      medida, e é o que impede a correção de mirar na enumeração errada.

- [ ] T061 Escrever `tools/check_run_status_vocabulary.py`: lê a enumeração do
      domínio **como dado** — nunca uma lista literal repetida no próprio check,
      que seria mais um vocabulário —, coleta todo estado de run servido por
      fixture e o declarado pelo console, e reprova nomeando arquivo e valor.
      Checa nas **duas** direções: valor a mais é tela que ninguém verá, valor a
      menos é run real caindo no fallback. Confirmar **vermelho** hoje, colando
      a saída com os valores que ele acusa.

- [ ] T062 Pendurar o check em `make verify`, na família dos que não precisam de
      build nem de infraestrutura, e escrever o teste de arquitetura que o
      exercita — inclusive o caso negativo: uma fixture com valor inventado
      reprova, e o gate diz qual.

- [ ] T063 Migrar as fixtures de run para os valores do domínio, arquivo por
      arquivo, escolhendo para cada uma o estado que descreve a **situação que
      ela já retratava** — não o que faz a suíte passar. As duas ocorrências de
      `succeeded` e a de `awaiting_approval` em `runs.json` e `run-detail.json`
      são o núcleo; `run-stream.json`, `run-threads.json`, `run-replay.json` e
      `incident-live/run-stream.json` entram na mesma varredura.

- [ ] T064 **Não tocar em nenhum estado de tool call.** A enumeração de tool
      call tem `succeeded` de verdade, e é de lá que a fixture tomou a palavra
      emprestada. Conferir, arquivo por arquivo, que cada `succeeded` alterado
      era de um run — e registrar quantos eram de tool call e ficaram.

- [ ] T065 Tirar os estados do gerador de dados em escala do plano de mock da
      mesma enumeração, em vez da lista própria que ele mantém.

- [ ] T066 Purgar do vocabulário do console os valores que o gateway não serve,
      e acrescentar os que ele serve e faltam. **Só depois de T063 e T065** —
      purgar antes derruba as fixtures que ainda usam o valor, e o vermelho
      resultante mede a ordem das tarefas em vez do produto.

- [ ] T067 Recapturar, uma a uma, as baselines visuais que a migração moveu.
      Cada recaptura é um passo deliberado e revisável no diff. **Nenhuma
      baseline é apagada para o gate passar, e nenhuma é substituída por captura
      fabricada** — se uma tela deixou de existir, isso é um achado a reportar,
      não uma captura a inventar.

- [ ] T068 Confirmar o check de T061 aprovando, e confirmar que ele volta a
      reprovar se um valor inventado for reintroduzido — testado reintroduzindo
      um e desfazendo.

- [ ] T069 Registrar, para o relatório final, quais estados do domínio **nenhuma
      fixture exercita**. É lacuna de cobertura a nomear, nunca valor a
      fabricar.

**Checkpoint**: a suíte deixa de poder passar verde sobre um vocabulário que o
produto não fala. `make verify` verde.

---

## Phase 3: Uma resolução de handle, três chamadores

- [ ] T028 Criar `gateway/http/credential_handles.py` com a função que responde
      **qual handle** uma integração resolve: o time que detém a credencial,
      descoberto por leitura de metadado do vault; o handle org-wide quando
      ninguém a detém por time; e o handle org-wide, com a ambiguidade
      registrada nomeando a integração, quando mais de um time a detém. Nada
      aqui lê valor de credencial.

- [ ] T029 Em `gateway/http/integration_access.py`, ligar o binding de
      ferramentas pelo handle que a nova função resolve, em vez do literal
      org-wide. **Tarefa de composição**: fecha com a evidência de serving.

- [ ] T030 Em `gateway/http/provider_credentials.py`, tirar o lease de provider
      pelo handle que a nova função resolve. **Tarefa de composição**: fecha com
      a evidência de serving.

- [ ] T031 Em `gateway/http/routes/integrations.py` e
      `gateway/http/routes/providers.py`, passar a resolver o handle pela mesma
      função, em vez de repetir a expressão do time do caller em cada rota.

- [ ] T032 Registrar, por provider, de onde a credencial veio — vault ou
      ambiente — e sob qual time, na linha de log que a composição já emite.
      Nomes apenas. É o que torna a alegação auditável sem revelar segredo.

- [ ] T033 Expor a ambiguidade de time na superfície que mostra a integração:
      mais de um time detém credencial para ela, dito em uma frase, com as
      chaves de mensagem em en e pt-BR.

- [ ] T034 Confirmar T014, T015 e T016 verdes, e confirmar que o gate que reprova
      leitura direta de credencial fora do pacote de proxy continua passando sem
      exceção nova.

**Checkpoint**: verificado verde e alcançável pela investigação passam a ser a
mesma resolução. `make verify` estreito no lado Python.

---

## Phase 4: Console

### 4a. Causas de vazio

- [x] T035 Em `console/src/surfaces/emptiness.ts`, fazer a causa de setup
      depender do passo que de fato bloqueia a tela que a pede, em vez da
      contagem de pendentes. A assinatura passa a receber qual dependência a
      tela tem.

- [x] T036 Fazer a causa de setup nomear o passo pendente que a justifica, com a
      chave de mensagem nova.

- [x] T037 Escrever a causa própria de `/decisions`: nenhuma proposta porque
      nenhuma investigação concluiu com remediação a propor. Chave nova em en.

- [x] T038 Escrever a causa própria de `/knowledge`: nenhum episódio porque
      nenhuma investigação terminou de forma que produzisse um. Chave nova em
      en.

- [x] T039 [P] Percorrer as demais telas que usam a causa de setup e dar a cada
      uma a sua causa própria para quando a de setup não se aplicar. Uma tela
      que ficar sem causa própria mantém as suas palavras de mecanismo — o que é
      correto — e isso é registrado por tela, não deixado por omissão.

- [x] T040 Retirar do catálogo a sentença que afirma que investigações não podem
      rodar enquanto o setup não termina, na forma em que ela afirma o que o
      gating não tem.

- [x] T041 Traduzir para pt-BR toda chave nova ou alterada desta feature, no
      mesmo commit em que a chave em inglês entra.

- [x] T042 Confirmar T017 e T018 verdes.

### 4b. Chips e o estado desconhecido

- [x] T043 Em `console/src/surfaces/read.ts`, acrescentar a derivação de estado
      que devolve desconhecido quando a leitura falhou, ao lado da que já devolve
      erro/vazio/pronto, e que devolve junto a dependência que falhou.

- [x] T044 Em `console/src/surfaces/screens/incident-detail.tsx`, derivar o chip
      de investigação dessa função, a partir do resultado da leitura e não do
      corpo dela. Quatro estados; o desconhecido nomeia a dependência.

- [x] T045 [P] Varrer os demais chips e rótulos que afirmam o negativo a partir
      de um corpo que pode ser de leitura falhada, e corrigi-los pelo mesmo
      caminho. A varredura é por uso da derivação, não por texto.

- [x] T046 Chaves de mensagem do estado desconhecido, en e pt-BR.

- [x] T047 Confirmar T019 verde e a asserção transversal de T009 verde.

### 4c. Rotas dinâmicas

- [x] T048 Aplicar o remédio que T004 indicou, rota por rota: cada rota de lista
      e cada rota de detalhe declara o seu próprio dinamismo no próprio arquivo,
      sem depender de herança de segmento. Se T004 tiver apontado uma camada
      diferente da do diagnóstico, o remédio é o dela — e a declaração por rota
      entra de todo jeito, porque depender de herança é a fragilidade que
      permitiu a dúvida.

- [x] T049 Confirmar que o check de build de T007 passa a **aprovar**, e que ele
      reprova de novo se uma rota for revertida — testado revertendo uma e
      desfazendo.

- [x] T050 Confirmar verdes os blocos do acceptance que contam requisições e o
      que exige o fato novo em um reload.

- [x] T051 Medir de novo a latência exatamente como em T002 e escrever
      `evidence/latency-after.md` com a comparação. Aplicar a decisão do plano:
      dentro do orçamento, aceito sem cache de dados; fora, cache de dados curto
      com a janela em constante declarada e a alegação do reload continuando a
      passar. **Página congelada não é saída** — se nem o cache curto fechar, a
      tarefa reporta.

### 4d. Contagens

- [x] T052 Fechar o que sobrou da coerência de contagens de setup entre
      cabeçalho, painel e dashboard, guiado pelo resultado registrado em T020. Se
      T020 passou, esta tarefa é uma confirmação escrita e nada mais — e dizer
      isso é o trabalho.

**Checkpoint**: acceptance inteiro verde localmente. `make verify` verde.

---

## Phase 5: Staging — a evidência do caminho de serving

Esta fase acontece depois do merge do slot, e o deploy é do orquestrador.

- [x] T053 Confirmar o deploy do slot com os componentes que esta feature mudou,
      e o ambiente Synced e Healthy antes de qualquer medição.

- [x] T054 Rodar contra `https://stg-ninjasre.lan.kyo.ninja` os blocos do
      acceptance marcados como seguros para ambiente compartilhado, mais a
      transversal. Screenshots full-page por tela retocada em `evidence/`.

- [x] T055 **Evidência de serving do checklist**: `/first-run` e
      `/settings/models-providers` no staging dizem a mesma palavra para o mesmo
      provider, capturada nas duas telas na mesma sessão.

- [x] T056 **Evidência de serving da resolução de provider**: o log de boot do
      pod nomeia a origem por provider e o time, sem valor nenhum; e uma
      investigação disparada no staging alcança o provider. Colar as linhas
      relevantes, redigidas de qualquer coisa que não seja nome.

- [x] T057 **Evidência de serving da resolução de handle**: para cada integração
      configurada, o handle do registro de verificação e o handle que o binding
      reporta são o mesmo. Consulta ao banco, não inspeção de tela.

- [x] T058 Rodar as quatro consultas de banco que a spec enumera e colar as
      contagens. Uma consulta que não puder ser executada é reportada como tal,
      nunca substituída por uma inspeção de tela.

- [x] T059 Confirmar `make verify` verde ao final e comparar com o log de T001.

**Checkpoint final**: as três tarefas de composição têm a sua evidência de
serving; os acceptance staging-safe estão verdes contra o ambiente real; as
contagens de banco estão coladas; a verificação completa está verde tendo
partido de verde.

---

## Relatório final (para o merge do slot)

O relatório de fim de feature declara, além do de praxe:

1. **Chaves de i18n criadas ou alteradas**, com o texto en e pt-BR — esta
   feature é a dona no slot e as aplicou; a lista existe para o confronto.
2. **A camada de cache que T004 encontrou**, mesmo que contradiga o diagnóstico
   da onda.
3. **A decisão de latência de T051**, com os dois conjuntos de números.
4. **A direção do seam de time**, e se alguma coisa no código real obrigou a
   revisá-la.
5. **Qualquer alegação normativa que não pôde ser codificada**, e por quê.
6. **Os três conjuntos de estado de run de T060**, o que a migração mudou, e
   quais estados do domínio nenhuma fixture exercita (T069).
7. **As baselines visuais recapturadas**, uma linha por baseline, com o estado
   que mudou nela.
8. **A observação sobre as duas enumerações de estado de run** — a do runtime e
   a do store se sobrepõem em quatro palavras e descrevem fatos diferentes.
   Unificá-las é decisão do dono do contrato de runs e **não** foi feita aqui.

---

## Ordem sugerida e paralelismo

Phase 0 inteira antes de tudo. Dentro da Phase 1, 1a e 1c são paralelas entre si
e 1b depende de 1a (o acceptance pergunta ao contador). Phase 2, Phase 2b e
Phase 3 são paralelas entre si — tocam arquivos diferentes, e o único encontro
das duas primeiras com a terceira é o gate de credencial direto, que todas
respeitam sem se coordenar. Phase 4 depende das três, porque o console lê o que
elas servem — e a purga de vocabulário de T066 tem de estar feita antes de T067,
que move baselines que a Phase 4 também pode mover. Phase 5 depende do merge do
slot e é do orquestrador convocar.

**Uma sequência interna é rígida e não pode ser paralelizada**: T061 (gate
vermelho) → T063 e T065 (migração) → T066 (purga) → T067 (baselines) → T068
(gate verde). Cada elo mede o anterior; fora de ordem, o vermelho e o verde
medem a ordem em vez do produto.

Tarefas marcadas `[P]` não dependem umas das outras e podem ser feitas em
qualquer ordem entre si.
