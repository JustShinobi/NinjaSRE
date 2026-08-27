# Tasks: Confiabilidade das telas

**Input**: Design documents from `specs_v6/020-confiabilidade-telas/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md). Nenhuma feature
desta onda precede esta.

**Tests**: test-first é obrigatório. Todo teste de reprodução é rodado **antes**
da correção, o vermelho é lido e a mensagem exata registrada no `controle.md`.
Um teste que nunca foi visto vermelho não prova nada, e um vermelho não
registrado não é verificável depois.

**Onde os testes moram**: unidade em `console/tests/unit/` (é só o que o Vitest
coleta), comportamento em `console/tests/e2e/` (projeto `behaviour` do
Playwright). Um caminho não coletado é evidência fabricada.

**Regra de escrita para todo arquivo committed produzido aqui** (código, teste,
fixture): nada de identificadores de requisito, artigos de constituição,
números de feature, nomes de onda ou caminhos de planejamento. Quando um teste
precisar de uma regra que está escrita num documento de planejamento, ele
enuncia a regra em si mesmo.

## Format: `[ID] [P?] [Story] Descrição`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência)
- **[Story]**: a qual user story a tarefa pertence (US1…US6)

---

## Phase 1: Setup — fixtures que reproduzem o estado real

**Purpose**: sem o shape real nas fixtures, todo teste desta feature passa por
acidente.

- [x] T001 [P] Estender `fixtures/scenarios/populated/audit-events.json` (ou
      criar o cenário irmão, se o populated for usado por testes que dependem
      do estado atual) com o shape observado no deployment: 200 eventos no
      fetch, **todos** com ator igual ao principal do próprio deployment, e um
      total muito maior que o número de eventos devolvidos. É o estado que
      produz cabeçalhos sem linhas com uma contagem cheia por cima.
- [x] T002 [P] Fixture do checklist de setup com a divergência viva: a lista
      servida pelo deployment com dois passos não concluídos, num deployment
      cuja sequência de telas do console tem sete posições. É o dado que hoje
      produz três números diferentes em três lugares.
- [x] T003 [P] Fixture de SSO não configurado: a configuração ausente e a
      lista de problemas que o deployment devolve para ela (os oito campos
      obrigatórios), para que o teste do formulário virgem tenha o que
      **não** exibir.
- [x] T004 [P] Fixture de campos de configuração no default herdado, sem
      nenhum override, cobrindo booleano, duração, número e enumeração — o
      estado em que a coluna de valor hoje fica vazia.

**Checkpoint**: os quatro estados defeituosos são reproduzíveis a partir de
fixture, sem depender do deployment.

---

## Phase 2: Acceptance spec da feature (test-first, vermelho confirmado)

**Purpose**: as alegações normativas desta feature viram teste antes de
qualquer correção.

- [x] T005 Criar `console/tests/e2e/020-confiabilidade-telas.acceptance.spec.ts`
      contra o build de produção, cobrindo:
      **(a) audit** — em `/settings/audit-log`, o corpo da tabela tem pelo
      menos uma linha, e o número que a tela afirma descreve a população
      desenhada (contagem afirmada = linhas desenhadas, ou o texto de
      truncamento ausente quando não há truncamento);
      **(b) audit, filtros** — escolher 7 dias e 30 dias reexecuta a consulta e
      o conjunto exibido muda, com o preset ativo indicado;
      **(c) contagem única** — o header do wizard, o painel de passos e o card
      do dashboard citam o mesmo total, o mesmo índice e o mesmo número de
      pendentes, e o número de pendentes é igual ao número de itens desenhados
      como não concluídos na lista;
      **(d) SSO virgem** — `/settings/single-sign-on` sem configuração e sem
      interação não exibe nenhuma mensagem de erro, não exibe nenhum
      identificador em snake_case no texto visível, e mostra o resumo neutro de
      "ainda não configurado";
      **(e) valor presente** — em `/settings/autonomy-guardrails`, as linhas de
      guardrail exibem valor legível ("On · level strict", "2 hours") com a
      origem na coluna de origem ("Deployment default"), e nenhuma célula de
      valor vazia.
- [x] T006 Rodar T005 e **confirmar o vermelho de cada alegação**, registrando
      a mensagem exata de cada falha no `controle.md`. Uma alegação que passar
      de primeira é suspeita: ou o defeito não existe como descrito, ou o
      seletor não está olhando para a tela — investigar antes de seguir.

**Checkpoint**: o acceptance spec existe, roda, e falha pelas razões certas.

---

## Phase 3: Suíte transversal (test-first, com exceção por rota)

**Purpose**: as quatro regras da onda viram instrumento permanente, rodado a
cada fronteira de feature. Nasce aqui, e daqui em diante é ela que diz se uma
regra regrediu.

- [x] T007 [US6] Criar `console/tests/e2e/transversal-rules.spec.ts` com as quatro
      regras, cada uma como um teste por rota de Settings:
      **(1) vocabulário** — o texto visível da rota não contém identificador de
      conta de serviço em caixa alta, estado de saúde cru em caixa alta,
      prefixo de caminho de configuração (`policies.`, `surfaces.`), caminho de
      modelo de investigador, nome de rota de entrega de webhook, nem mensagem
      de campo obrigatório em snake_case (`_id is required`);
      **(2) orçamento de rolagem** — a altura do documento renderizado cabe no
      orçamento em viewports;
      **(3) contagem única** — os números de progresso de setup são iguais em
      todas as superfícies que os exibem;
      **(4) coluna de valor** — nenhuma célula da coluna de valor de uma tabela
      de configuração está vazia.
- [x] T008 [US6] Na regra de rolagem, **declarar explicitamente o viewport
      1920×1080** no próprio arquivo (o viewport global do Playwright é
      1440×900 e não serve para medir este orçamento), lendo largura, altura e
      orçamento em viewports das constantes nomeadas que já os definem em
      `config/constants/surfaces.py` — não repetir os números no teste.
- [x] T009 [US6] Implementar o mecanismo de exceção: uma tabela de exceções no topo
      do arquivo, chaveada por **rota + regra**, cada entrada carregando o
      motivo substantivo escrito por extenso, e aplicada como `test.fixme`
      naquele par. A exceção nunca relaxa a regra para as outras rotas.
      O motivo é escrito em prosa técnica — o que a rota faz hoje que a coloca
      fora da regra — e **não** cita feature, onda, spec nem documento de
      planejamento. Precedente de forma no repositório:
      `console/tests/e2e/scroll-budget.spec.ts` (`expectedOverBudget`, nomeado
      em vez de escondido).
- [x] T010 [US6] Popular a tabela de exceções com o que se sabe hoje: a tela de
      autonomia excede o orçamento de rolagem porque ainda concentra postura,
      regras, freeze, budgets, overrides, simulação e guardrails numa página; a
      tela de alert intake excede porque repete sete fontes idênticas; as rotas
      com vocabulário cru remanescente (chips de conta de serviço e de saúde,
      títulos de grupo de configuração, jargão de entrega de webhook) ficam
      anotadas por rota. Cada entrada descreve o estado, e some quando a tela
      for redesenhada.
- [x] T011 [US6] Rodar T007 e **confirmar o vermelho** nas rotas que esta feature vai
      corrigir e o `fixme` nas anotadas, registrando o mapa rota × regra ×
      resultado no `controle.md`. Esse mapa é o inventário que as features
      seguintes usam para saber o que ainda devem.
- [x] T012 [US6] Verificar que a suíte é auto-suficiente: nenhuma referência a
      documento de planejamento, número de feature, onda ou caminho não
      committed, e nenhuma leitura de arquivo ausente de um clone limpo.
      Conferir também que ela não duplica asserção já feita por
      `console/tests/e2e/vocabulary.spec.ts` ou
      `console/tests/e2e/scroll-budget.spec.ts` — onde a sobreposição for
      exata, a cópia sai da suíte nova.

**Checkpoint**: existe um instrumento que reprova, por rota e por regra, e
declara o que ainda não cobra.

---

## Phase 4: User Story 1 — Audit log que mostra o que afirma (P1)

**Goal**: a tela desenha as linhas e nunca afirma uma população maior que a
exibida.

**Independent Test**: com a fixture de T001, a tela exibe linhas e a contagem
afirmada bate com elas.

- [x] T013 [US1] Teste de unidade em `console/tests/unit/surfaces/settings/`
      cobrindo a derivação: dada a resposta da fixture de T001, a população
      exibida e a contagem afirmada são a mesma; e o estado vazio é decidido
      pela população exibida, não pela buscada. **Rodar e confirmar o
      vermelho**, registrando a mensagem.
- [x] T014 [US1] Corrigir `console/src/surfaces/settings/audit.tsx`: corpo e
      contagem passam a descrever a mesma população; o estado vazio do painel
      passa a ser decidido pelo que sobrou depois de qualquer exclusão; o aviso
      de truncamento só aparece quando há truncamento de fato. T013 fica verde.
- [x] T015 [US1] Quando a exclusão implícita de atores esconder linhas, a tela
      declara a exclusão e oferece a ação que a desfaz — o caso em que o fetch
      inteiro é do principal do próprio deployment não pode terminar em tabela
      muda.
- [x] T016 [US1] Confirmar que os presets de período reexecutam a consulta e
      que o preset ativo fica indicado; se a reprodução mostrar que a
      divergência vem do contrato do gateway e não da tela, a correção da causa
      raiz entra aqui, com o teste de contrato em `tests/contract/` escrito
      antes e visto vermelho.
- [x] T017 [US1] Rodar as partes (a) e (b) do acceptance spec e confirmar
      verde.

**Checkpoint**: `/settings/audit-log` deixa de mentir.

---

## Phase 5: User Story 2 — Uma só contagem do setup (P1)

**Goal**: uma fonte deriva total, índice e pendentes; três superfícies exibem a
mesma tripla.

**Independent Test**: com a fixture de T002, wizard, painel e card citam os
mesmos três números.

- [x] T018 [US2] Teste de unidade em `console/tests/unit/surfaces/` sobre a
      fonte de progresso: dada a lista de passos, ela devolve total, índice do
      passo atual e pendentes, e os pendentes são exatamente os itens não
      concluídos daquela lista. **Rodar e confirmar o vermelho.**
- [x] T019 [US2] Implementar a derivação única em
      `console/src/surfaces/first-run/plan.ts`: uma função devolve a tripla a
      partir da mesma lista que desenha o stepper. A segunda lista deixa de ser
      um denominador.
- [x] T020 [US2] `console/src/surfaces/screens/first-run.tsx` passa a consumir
      a tripla no header e no painel, na forma que o mockup fixa: posição, nome
      do passo e pendentes numa linha só. **Remover o comentário que declara a
      divergência intencional** — ele defende um comportamento que deixa de
      existir, e um comentário que sobrevive à decisão que ele explicava passa
      a ser instrução errada para quem ler depois.
- [x] T021 [US2] `console/src/surfaces/setup-hero.tsx` (card do dashboard)
      passa a consumir a mesma tripla.
- [x] T022 [US2] Varrer as demais superfícies que citam progresso de setup
      (banner de retorno, estados vazios que mencionam passos pendentes) e
      apontá-las para a mesma fonte; nenhuma introduz denominador próprio.
- [x] T023 [US2] Quando a fonte não puder ser lida, nenhuma superfície exibe
      total inferido — teste de unidade cobrindo o caso.
- [x] T024 [US2] Rodar a parte (c) do acceptance spec e a regra 3 da suíte
      transversal; confirmar verde nas duas.

**Checkpoint**: um número, três lugares.

---

## Phase 6: User Story 3 — SSO que não acusa antes de perguntar (P1)

**Goal**: formulário virgem sem erro; erro depois de interação; label humano.

**Independent Test**: com a fixture de T003, a página abre limpa; após submeter
vazio, os problemas aparecem nomeando os campos como o formulário os chama.

- [x] T025 [US3] Teste de unidade em `console/tests/unit/surfaces/` para o
      estado do formulário: virgem não exibe erro; blur de um campo exibe o
      problema daquele campo; submissão exibe os problemas pendentes; as
      mensagens usam os labels humanos declarados pelo próprio formulário.
      **Rodar e confirmar o vermelho.**
- [x] T026 [US3] Implementar o estado de formulário em
      `console/src/surfaces/sso-setup.tsx`: campos tocados, submissão, e a
      decisão de exibir erro derivada disso — não da existência de problemas.
- [x] T027 [US3] `console/src/surfaces/settings/sso.tsx`: a configuração
      ausente vira resumo neutro em vez de lista de requisitos não atendidos.
      Chaves novas em `console/src/i18n/en.ts` e `console/src/i18n/pt-BR.ts`,
      sempre em par.
- [x] T028 [US3] Mapear problema do deployment para o campo que o causou, de
      modo que a mensagem apareça ancorada no campo, usando os labels que o
      formulário já declara — sem uma segunda tabela de tradução.
- [x] T029 [US3] Rodar a parte (d) do acceptance spec e a regra 1 da suíte
      transversal na rota de SSO; confirmar verde.

**Checkpoint**: a tela mais perigosa do produto para de receber o operador com
oito acusações.

---

## Phase 7: User Story 4 — Tabela de configuração com valor (P2)

**Goal**: nenhuma célula de valor vazia; valor efetivo formatado por tipo;
origem na coluna de origem.

**Independent Test**: com a fixture de T004, as linhas exibem valor legível em
Autonomy e Notifications.

- [x] T030 [US4] Teste de unidade em `console/tests/unit/surfaces/` para a
      formatação por tipo: booleano vira estado, duração vira tempo, número
      vira número, enumeração vira frase; e a ausência real de valor vira marca
      explícita, nunca string vazia. **Rodar e confirmar o vermelho.**
- [x] T031 [US4] Teste de unidade provando que o componente de tabela de
      configuração **recusa** uma linha sem valor renderizável — a garantia que
      impede a próxima tela de repetir o defeito. **Vermelho confirmado.**
- [x] T032 [US4] Implementar em `console/src/surfaces/preview.tsx`: a célula de
      valor passa a exibir o valor efetivo (override quando existe, default
      herdado quando não), formatado por tipo, com a origem na coluna de
      origem.
- [x] T033 [US4] Verificar `/settings/autonomy-guardrails` e
      `/settings/notifications` com a fixture: as doze linhas hoje vazias
      exibem valor. Nenhuma mudança de layout da autonomia entra aqui — o
      redesenho da tela pertence a outra feature; esta entrega os valores.
- [x] T034 [US4] Rodar a parte (e) do acceptance spec e a regra 4 da suíte
      transversal; confirmar verde.

**Checkpoint**: a tabela informa o que está valendo.

---

## Phase 8: User Story 5 — Copy que conta e não se repete (P3)

**Goal**: singular e plural corretos; um só "Set at".

- [x] T035 [P] [US5] Teste de unidade cobrindo a contagem de tokens com
      exatamente um token (forma singular) e com vários (plural), nos dois
      idiomas. **Vermelho confirmado.**
- [x] T036 [US5] Corrigir `console/src/surfaces/machine-token-groups.tsx`: as
      três contagens montadas por substituição manual de marcador passam pela
      função de formatação de contagem que já escolhe singular ou plural. As
      chaves de mensagem ganham as duas formas, em inglês e pt-BR.
- [x] T037 [P] [US5] Teste de unidade para a célula de origem: sob uma coluna
      já intitulada com o rótulo, a célula carrega apenas o nó; o rótulo
      prefixado só aparece onde a linha é autônoma. **Vermelho confirmado.**
- [x] T038 [US5] Corrigir a duplicação de rótulo na origem, em
      `console/src/surfaces/preview.tsx` (mesma região tocada em T032, então
      esta tarefa vem depois dela).

**Checkpoint**: "1 tokens" e "Set at Set at:" não são mais reproduzíveis.

---

## Phase 9: Polish — evidência visual, gates e controle

- [ ] T039 Atualizar `console/visual/screens.json` para as telas alteradas e
      **capturar as baselines deliberadamente**, olhando cada captura antes de
      aceitá-la: audit log, first-run, autonomy-guardrails, notifications e
      models-providers já estão registradas; single sign-on entra no registro
      se a mudança do estado virgem merecer baseline. Uma baseline aceita sem
      ser olhada transforma um defeito em contrato.
- [x] T040 Rodar a suíte transversal inteira e registrar o mapa final rota ×
      regra × resultado, com as exceções que sobraram e o motivo de cada uma.
      Esse mapa é o que as features seguintes herdam.
- [x] T041 Provar que a suíte transversal reprova de fato: introduzir
      deliberadamente uma violação de cada uma das quatro regras numa rota
      conforme, verificar que a suíte reprova nomeando rota e regra, e desfazer.
      Registrar as quatro mensagens no `controle.md`. Uma regra que nunca foi
      vista reprovando não é uma regra.
- [ ] T042 Rodar `make verify` completo (lint, format-check, typecheck,
      check-imports, check-constants, check-protocols, check-deps e a suíte) e
      registrar o resultado. Se algum gate não for rodado, dizer qual e por quê
      — silêncio sobre um gate é o mesmo que reprovar nele.
- [x] T043 Escrever `specs_v6/020-confiabilidade-telas/controle.md`: o que o
      código prova, com os vermelhos confirmados (mensagem exata, por tarefa),
      os verdes correspondentes, o mapa de exceções da suíte transversal, os
      gates rodados e os não rodados, e qualquer alegação da spec que **não**
      ficou satisfeita — nomeada, não omitida.

---

## Dependencies & Execution Order

### Entre fases

- **Phase 1** não depende de nada e habilita todo o resto.
- **Phase 2** e **Phase 3** dependem da Phase 1 e **precedem toda correção** —
  é o que torna esta feature test-first em vez de test-depois.
- **Phases 4–8** dependem das Phases 2 e 3. Entre si, são independentes: tocam
  arquivos distintos, com uma exceção — T038 (copy da origem) toca o mesmo
  arquivo que T032 (valor), e vem depois.
- **Phase 9** depende de todas.

### Ordem interna obrigatória

- T013→T014, T018→T019, T025→T026, T030→T032, T031→T032, T035→T036, T037→T038:
  o teste antes, o vermelho visto, a correção depois.
- T019→T020→T021→T022: a fonte antes dos consumidores.
- T032→T038: mesmo arquivo.

### Paralelismo

- T001–T004 em paralelo.
- Depois da Phase 3: US1 (T013–T017), US2 (T018–T024), US3 (T025–T029) e US5
  (T035–T037) podem andar em paralelo; US4 (T030–T034) e T038 compartilham
  `preview.tsx` e ficam em série entre si.
- Nesta árvore compartilhada, o paralelismo é de ordenação, não de sessões
  simultâneas: `console/src/i18n/*.ts` é arquivo de escrita única na onda e é
  tocado por T027, T036 e T032.

## Implementation Strategy

1. Fixtures (Phase 1) → os defeitos passam a ser reproduzíveis sem o
   deployment.
2. Acceptance spec e suíte transversal (Phases 2–3) → o vermelho é registrado
   antes de qualquer linha de correção, e o inventário do que ainda não se
   cobra fica escrito.
3. P1 primeiro, na ordem audit → contagem → SSO: são os três que o acceptance
   spec cobre e os três que o operador encontra primeiro.
4. P2 e P3 depois, com atenção ao arquivo compartilhado.
5. Polish: baseline olhada, suíte provada reprovando, gates rodados,
   `controle.md` dizendo só o que o código sustenta.
