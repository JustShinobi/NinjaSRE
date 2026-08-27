# Tasks: Autonomy & guardrails em três abas

**Input**: Design documents from `specs_v6/040-autonomy-tres-abas/`

**Prerequisites**: plan.md, spec.md, feature 020 entregue (componente de tabela
com coluna de valor preenchida e suíte transversal executável); 030 já passou na
ordem da onda

**Tests**: test-first, obrigatório. O acceptance da feature nasce antes da tela
e é confirmado vermelho; cada fase abre pelo seu teste.

**Onde cada teste mora** (os runners só coletam nestes caminhos): "teste de
tela" e "teste (vitest)" são unidade em `console/tests/unit/`; Playwright fica
em `console/tests/e2e/` e aparece aqui em três lugares apenas — o acceptance da
feature, a medição de orçamento e a suíte transversal. Um caminho não coletado
é evidência fabricada.

**Formato**: `[ID] [P?] [Story] Descrição` — `[P]` marca tarefas paralelizáveis
(arquivos distintos, sem dependência entre si).

> **Regra de escrita que vale para toda tarefa abaixo**: nenhum arquivo
> committed — código, teste, JSON de registro, catálogo de idioma — cita
> identificador de requisito, artigo de constituição, número de feature ou
> caminho de documento de planejamento. A substância vai no arquivo; a
> referência fica nesta spec. A única exceção é o nome do arquivo de acceptance,
> que a convenção da onda fixa.

---

## Phase 1: Acceptance-first (bloqueante) 🔴

**Purpose**: codificar as alegações normativas do mockup como teste executável,
e confirmar que elas falham contra a tela de hoje.

- [x] **T001** Criar `console/tests/e2e/autonomy-tabs.acceptance.spec.ts`
      declarando no próprio arquivo o viewport de 1920×1080 (a suíte global roda
      em 1440×900) e codificando, como asserções distintas:
      (a) três abas presentes, nomeadas Posture, Rules & windows e Guardrails,
      nessa ordem;
      (b) cada aba alcançável diretamente pelo seu endereço, e a aba ativa
      refletida na URL;
      (c) a rota sem aba nomeada abre em Posture, e um nome desconhecido também;
      (d) altura de cada aba dentro do orçamento, lido da constante nomeada e não
      escrito no teste;
      (e) nenhuma célula vazia na coluna de valor da tabela de guardrails, nas
      duas aparições;
      (f) override ausente do corpo e alcançável por botão do cabeçalho que abre
      painel lateral;
      (g) nenhum parágrafo entre o título e o primeiro controle;
      (h) nenhum CTA na rota cujo rótulo prometa destino diferente do que abre;
      (i) um só CTA primário na seção de simulação.
- [x] **T002** Rodar o acceptance e **registrar o vermelho**: anexar ao controle
      da feature a saída com a contagem de asserções falhando e o motivo de cada
      uma. Um acceptance que passa antes da implementação está medindo outra
      coisa e precisa ser corrigido aqui, não depois.

**Checkpoint**: o alvo está escrito e provado ausente.

---

## Phase 2: Foundational (bloqueante para todas as histórias)

**Purpose**: as três decisões que as abas compartilham — quanto cabe, qual aba
possui um campo, e o que a célula de valor diz.

- [x] **T003** Declarar em `config/constants/surfaces.py` a constante nomeada do
      orçamento de rolagem **por aba** (1.5), ao lado das que já definem o
      viewport de medição e o orçamento de página inteira; incluí-la no `__all__`
      do módulo. `make check-constants` continua verde.
- [x] **T004** Teste (vitest) de `console/src/surfaces/settings/autonomy-tabs.ts`
      — falhando primeiro: resolução do parâmetro de aba (ausente → Posture,
      desconhecido → Posture, válido → a aba pedida), preservação do nó de escopo
      na troca de aba, e a consulta "qual aba possui este campo de política" para
      cada campo que o mapa de paridade atribui a esta tela.
- [x] **T005** Implementar `console/src/surfaces/settings/autonomy-tabs.ts`: as
      três abas, a resolução do parâmetro e o mapa campo → aba dona, declarado
      como dado e não inferido do JSX.
- [x] **T006** Teste (vitest) de
      `console/src/surfaces/settings/guardrail-values.ts` — falhando primeiro:
      para cada guardrail, o par (campo, valor resolvido) produz a frase da
      célula; um valor ausente produz o texto que diz que está ausente, nunca
      string vazia; a origem é texto separado do valor.
- [x] **T007** Implementar `console/src/surfaces/settings/guardrail-values.ts`,
      consumido tanto pela leitura resumida de Posture quanto pela tabela
      editável de Guardrails — uma fonte só para as duas aparições.

**Checkpoint**: fundação pronta; as histórias podem começar.

---

## Phase 3: User Story 1 — Três abas endereçáveis (P1) 🎯 MVP

**Goal**: a rota vira três perguntas, cada uma dentro do orçamento.

**Independent Test**: percorrer as três abas pela URL e medir a altura de cada
uma em 1920×1080.

- [x] **T008** [US1] Estender o teste de tela existente
      `console/tests/unit/surfaces/settings/autonomy.test.tsx` — falhando
      primeiro: a tela renderiza as três abas na ordem declarada, marca a ativa,
      e cada aba é um link com endereço próprio (não um botão que só muda estado
      de cliente). Toda tarefa de teste de tela abaixo estende este mesmo
      arquivo, salvo quando outro caminho for nomeado.
- [x] **T009** [US1] Reorganizar `console/src/surfaces/settings/autonomy.tsx` em
      três abas usando o módulo de T005, distribuindo o conteúdo existente sem
      ainda mudar nenhum controle: postura e resumo de guardrails em Posture;
      regras, congelamentos, tetos e simulação em Rules & windows; guardrails em
      Guardrails.
- [x] **T010** [US1] Registrar o parâmetro de aba entre os filtros que a tela
      lê, ao lado do nó de escopo, para que a troca de aba preserve o nó.
- [x] **T011** [US1] Estender `console/tests/e2e/scroll-budget.spec.ts` para
      medir esta rota **por aba** contra a constante de T003, mantendo a medição
      de página inteira das demais telas intacta.

**Checkpoint**: as abas existem, são endereços, e o orçamento é medido.

---

## Phase 4: User Story 2 — Posture (P1)

**Goal**: a decisão mais consequente da tela, sem prosa na frente dela.

**Independent Test**: num nó sem regra alguma, ler o que a tela diz do vazio,
trocar a postura e salvar.

- [x] **T012** [US2] Teste de tela — falhando primeiro: subtítulo declara nó e
      postura vigente; zero parágrafos entre título e primeiro controle; seletor
      de níveis em nomes de exibição com a ação de salvar ao lado; um nível sem
      nome de exibição aparece pelo identificador declarado.
- [x] **T013** [US2] Teste de tela do empty state — falhando primeiro: com
      nenhuma regra registrada, o texto afirma que tudo resolve para
      propose-only, que esse é o default seguro e não um erro, e nomeia a aba de
      regras; o CTA aterrissa no destino que o rótulo promete.
- [x] **T014** [US2] Implementar a aba Posture: seletor, salvar, empty state e o
      subtítulo com nó e postura vigente.
- [x] **T015** [US2] Remover os três parágrafos conceituais do topo e reescrever
      cada conceito como uma frase única no controle onde ele é usado
      (`console/src/i18n/en.ts` + `console/src/i18n/pt-BR.ts`, sempre no mesmo
      commit).
- [x] **T016** [US2] Retirar da rota o rótulo de CTA que promete outra tela e
      abre uma âncora da mesma página, substituindo-o pelo verbo da ação que
      executa.
- [x] **T017** [US2] Montar em Posture a leitura resumida dos guardrails
      (Setting, Value, Set at) usando o resolvedor de T007, sem controles de
      edição.

**Checkpoint**: quem abre a tela decide a postura sem ler três parágrafos.

---

## Phase 5: User Story 3 — Guardrails com valor à vista (P1)

**Goal**: devolver a edição à aba dona, e **provar** que a coluna de valor
continua preenchida depois do corte em abas.

**Remedido em 2026-08-18**: a metade "matar a coluna de valor vazia" **já está
feita**. Hoje são zero células vazias nas duas aparições da tabela, e não por
acaso — `EffectiveFieldsTable` lança exceção se qualquer linha vier com valor ou
origem em branco. O T018 é portanto **verificação**, não implementação: ele
prova que a propriedade sobrevive ao corte em abas. Não vale escrever asserção
contra "reduzir de 12 para 0" partindo de 0 — ela passaria sem provar nada.

**Independent Test**: percorrer a tabela sem achar célula de valor vazia; editar
um escalar e ver valor e origem mudarem.

- [x] **T018** [US3] Teste de tela — **verificação**, não redução: cada linha
      traz Setting, Value e Set at; nenhuma célula de Value vazia depois do corte
      em abas; valor efetivo em Value e herança em Set at, dizendo coisas
      diferentes. O vermelho honesto aqui é contra a aba que ainda não existe,
      não contra uma coluna vazia que já não existe.
- [x] **T019** [US3] Implementar a aba Guardrails sobre o componente de tabela da
      020, alimentado pelo resolvedor de T007. **Inclui remover o parágrafo de
      abertura da aba** (`settings.autonomy.guardrails.lead`, `en.ts:1907`): o
      corte em abas o deixou, pela primeira vez, entre o título da aba e o seu
      primeiro controle, e o acceptance o acusa em `tab=guardrails`. Não é falso
      positivo do walk — o mockup M2 é normativo e explícito: na aba Guardrails,
      o título "Guardrails in effect" é seguido **direto** pela tabela, e na aba
      Posture a frase explicativa vem **depois** do controle ("Save posture"),
      nunca antes. O padrão que FR-011 e FR-033 pedem é uma frase junto ao
      controle onde o conceito é usado, e o mockup a coloca depois dele — o que
      não conflita com FR-010.
- [x] **T020** [US3] Edição inline dos campos que o schema declara editáveis, na
      própria linha, com a origem passando a dizer que foi definido aqui após
      gravar.
- [x] **T021** [US3] Substituir os caminhos técnicos de grupo de política por
      nomes de exibição como títulos, mantendo o caminho técnico onde ele é
      técnico — registro de auditoria e API.
- [x] **T022** [US3] Teste — falhando primeiro — de que os guardrails fixados
      pela constituição são renderizados como fatos e não têm controle que os
      desligue; e de que nenhuma aba abre com editor genérico de schema como
      conteúdo primário.
- [x] **T023** [US3] Teste de permissão: um leitor sem escrita vê valores,
      origens e regras nas três abas, e não recebe formulários nem o botão de
      override.

**Checkpoint**: o operador descobre o valor efetivo de qualquer guardrail.

---

## Phase 6: User Story 4 — Paridade sem campo órfão (P1)

**Goal**: provar por teste que a reorganização não perdeu nenhum campo.

**Independent Test**: percorrer os campos que o mapa atribui a esta tela e
confirmar aba dona e controle funcional para cada um.

- [x] **T024** [US4] Rodar `tests/contract/console/test_console_config_ownership.py`
      contra a tela reorganizada e tratar qualquer vermelho como campo órfão a
      reatribuir — nunca como asserção a afrouxar. A contagem de campos
      declarados sem controle não pode aumentar.
- [x] **T025** [US4] Teste (vitest) — falhando primeiro — de que todo campo que o
      mapa atribui a esta tela é reivindicado por exatamente uma aba no módulo de
      T005, e que a verificação falha nomeando o campo quando um deles fica sem
      dona.
- [x] **T026** [US4] Teste (vitest) em
      `console/tests/unit/shell/configuration-redirect.test.ts` — falhando
      primeiro: um endereço com âncora de seção do editor aposentado aterrissa
      nesta tela **na aba que possui aquela seção**, e não na aba padrão com uma
      âncora que ali não existe.
- [x] **T027** [US4] Estender `console/src/shell/configuration-redirect.ts` para
      compor o destino com a aba dona, consultando o mesmo mapa de T005 em vez de
      escrever a correspondência uma segunda vez.

**Checkpoint**: paridade é fato verificado, não afirmação.

---

## Phase 7: User Story 5 — Rules & windows com simulação em contexto (P2)

**Goal**: um fluxo com um CTA primário, no lugar de três botões concorrentes.

**Independent Test**: criar regra, congelamento e teto na mesma aba, e simular o
efeito por um caminho só.

- [x] **T028** [US5] Teste de tela — falhando primeiro: a aba traz criação de
      regra, de janela de congelamento e de teto, e a lista de regras em ordem de
      resolução.
- [x] **T029** [US5] Teste de tela da simulação — falhando primeiro: a seção
      tem título próprio, uma linha que diz o que ela responde, e exatamente um
      CTA primário; a trava que exige o efeito visto antes de salvar continua
      valendo para a entrada corrente.
- [x] **T030** [US5] Reorganizar os controles existentes de regra, congelamento e
      teto dentro da aba, sem alterar o contrato de escrita — em particular,
      continuar carregando congelamentos e tetos inalterados em toda gravação de
      regra.
- [x] **T031** [US5] Unificar em `console/src/surfaces/autonomy-editor.tsx` os
      três controles de simulação num CTA primário com as variações subordinadas
      a ele; atualizar os dois catálogos de idioma no mesmo commit.
- [x] **T032** [US5] Fazer da lista de regras a região que rola, de modo que um
      nó com muitas regras não estoure o orçamento da aba; teste com fixture de
      nó carregado.
- [x] **T033** [US5] CTA do empty state de Rules com rótulo que nomeia a ação que
      executa, criando a primeira regra ali mesmo.

**Checkpoint**: a simulação é um passo do fluxo, não três botões soltos.

---

## Phase 8: User Story 6 — Override em painel lateral (P2)

**Goal**: a ação rara para de cobrar espaço de quem não a usa.

**Independent Test**: abrir o painel pelo cabeçalho, conceder um override e
revogá-lo.

- [x] **T034** [US6] Teste de tela — falhando primeiro: nenhuma aba reserva
      espaço de corpo para override; há botão no cabeçalho; acioná-lo abre painel
      lateral com nome, nível, razão e duração; o rótulo da razão declara que ela
      é registrada no audit.
- [x] **T035** [US6] Teste de tela dos dois estados — falhando primeiro: sem
      override ativo o painel afirma isso em texto; com override ativo ele mostra
      nome, nível, razão e expiração, e permite revogar.
- [x] **T036** [US6] Montar `console/src/surfaces/override-editor.tsx` no painel
      lateral aberto pelo cabeçalho, preservando o contrato atual de concessão e
      revogação.
- [x] **T037** [US6] Teste de que conceder e revogar entram no registro de
      auditoria com nome, nível, razão e expiração.
- [x] **T038** [US6] Com override ativo, o subtítulo mostra a postura que vigora
      e declara que ela vem de um override com prazo, em vez do nível salvo.

**Checkpoint**: override é ação rara com custo de ação rara.

---

## Phase 9: Fechamento

- [x] **T039** Rodar `console/tests/e2e/autonomy-tabs.acceptance.spec.ts`
      **verde**, e comparar asserção a asserção com o vermelho registrado em
      T002: cada falha registrada lá tem que ter virado passagem aqui.
- [x] **T040** Rodar a suíte transversal na rota. **Remedido em 2026-08-18**: não
      há exceção a remover — `EXCEPTIONS` em `transversal-rules.spec.ts` guarda
      apenas `/settings/alert-intake`, e esta rota já roda os bans de vocabulário
      e a contagem única de verdade. A tarefa é portanto de **verificação**:
      provar que a suíte continua sem exceção declarada para esta rota depois do
      corte em abas, e resolver a única ambiguidade que sobra — a rota está em
      `SCROLL_BUDGET_MEASURED_ELSEWHERE`, que faz um `test.skip` literal cujo
      motivo é "medida em outro lugar" (`scroll-budget.spec.ts`), não "isenta".
      Com a medição passando a ser **por aba** em T011, decidir e registrar se a
      delegação continua correta ou se a regra transversal passa a medir aqui.
- [x] **T041** Conferir a paridade dos catálogos de idioma: toda chave nova
      existe nos dois, sem sobra em nenhum.
- [x] **T042** Atualizar `console/visual/screens.json`: a entrada desta rota sai
      de pendente — a razão registrada para a pendência era altura acima do
      orçamento e campos ainda descobertos, e esta feature resolve as duas —, com
      a justificativa reescrita para o que a tela é agora, e uma entrada por aba
      se o registro precisar cobrir as três.
- [x] **T043** Captura deliberada de baseline visual para a rota nas abas
      registradas, revisada antes de aceita.
- [x] **T044** `make verify` verde (lint, formato, tipos, contratos de
      importação, constantes, protocolos, dependências e a suíte), mais vitest e
      as três suítes Playwright.
- [x] **T045** Escrever `specs_v6/040-autonomy-tres-abas/controle.md` no padrão
      da onda, declarando **apenas o que o código prova**: estado por requisito,
      a saída vermelha de T002 e a verde de T039, a medição de altura por aba com
      o viewport declarado, a contagem de células de valor preenchidas, o
      resultado do contrato de paridade e a lista dos gates rodados.

---

## Dependencies

- T001 → T002 → todo o resto. Nada de implementação começa antes do vermelho
  registrado.
- T003, T004→T005, T006→T007 formam a fundação; T005 e T007 bloqueiam as
  histórias.
- US1 (T008–T011) precede as demais histórias: é ela que cria as abas onde as
  outras montam conteúdo.
- US2 (T012–T017) e US3 (T018–T023) são paralelizáveis entre si depois de US1.
- US4 (T024–T027) depende de T005 e de as três abas existirem; T027 depende de
  T026.
- US5 (T028–T033) e US6 (T034–T038) são paralelizáveis entre si depois de US1.
- Fase 9 depois de tudo; T039 antes de T040; T042 → T043; T045 por último.

## Arquivos de escrita única na onda

`console/src/i18n/en.ts`, `console/src/i18n/pt-BR.ts` e
`console/visual/screens.json` são compartilhados por toda a onda. Toda tarefa
que os toca (T015, T016, T031, T033, T041, T042) escreve neles de uma vez, na
sua própria fase, e não fica com edição pendente atravessando fronteira de
feature.
