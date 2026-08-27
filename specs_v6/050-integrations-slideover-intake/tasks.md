# Tasks: Integrações em slide-over e Alert intake enxuto

**Input**: Design documents from `specs_v6/050-integrations-slideover-intake/`

**Prerequisites**: spec.md, plan.md, e a feature 001 concluída (catálogo em 15,
fontes de intake reduzidas a `alertmanager`, `grafana` e `generic`).

**Tests**: test-first, sem exceção. O vermelho é confirmado e a saída registrada
em `controle.md` antes de a implementação correspondente ser escrita.

**Convenção**: `[P]` marca tarefas sem dependência entre si, que podem correr em
paralelo. Nenhuma tarefa instrui escrever identificador de requisito, número de
artigo, número de feature ou caminho de planejamento em arquivo committed — o
que o código ou o teste precisar saber é dito por extenso lá.

**Arquivos de escrita única na onda** (execução sequencial, sem worker
paralelo): `console/src/i18n/en.ts`, `console/src/i18n/pt-BR.ts`,
`console/src/shell/routes.ts`, `console/visual/screens.json`.

---

## Fase 1: Setup e pré-condições

- [x] T001 Confirmar que a 001 aterrissou: `GET /v1/integrations` lista 15
      integrações, e as fontes de intake servidas são exatamente `alertmanager`,
      `grafana` e `generic`. Registrar os dois números observados em
      `controle.md`. Se qualquer um divergir, parar — nenhum critério de rolagem
      desta feature é alcançável com o catálogo antigo.
- [x] T002 Registrar o estado de partida das duas telas, para haver contra o quê
      comparar: altura de `/integrations` e de `/settings/alert-intake` em 1080p,
      presença do controle de paginação, e a posição de rolagem em que
      `/integrations/prometheus` aterrissa hoje. Números reais, medidos, em
      `controle.md`.
- [x] T003 [P] Fixtures das duas telas para vitest e Playwright: catálogo com
      conectadas, sugeridas e disponíveis; uma integração verificada, uma
      guardada sem verificação e uma falhando; três fontes de intake com uma
      recebendo e duas caladas. **Nenhuma fixture escreve o total do catálogo**:
      o número vem do que a API devolveu, e as asserções são sobre a relação —
      "todo item aparece", "a altura cabe" — nunca sobre o literal.

---

## Fase 2: Acceptance-first — o mockup vira teste antes da tela

- [x] T004 Criar `console/tests/e2e/050-integrations-slideover-intake.acceptance.spec.ts`
      codificando as alegações normativas de M4 e M3, e nada além delas:
      - **Catálogo**: as três seções na ordem Connected → Suggested by your
        estate → Available; nenhum controle de paginação e nenhuma contagem
        "Page N of M"; a contagem única do topo com os três números derivados do
        payload; a busca por nome e por capacidade filtrando dentro das seções;
        o rodapé com a contagem das movidas para o roadmap e o link da lista;
        altura ≤2 viewports com o viewport 1080p declarado no próprio teste.
      - **Slide-over**: a posição de rolagem medida antes de abrir, com o painel
        aberto e depois de fechar, provando que não muda; o deep-link abrindo o
        painel com a rolagem no topo do catálogo; os filtros preservados ao
        fechar; o painel sobreposto ao catálogo e não no rodapé do documento.
      - **Integração verificada**: nenhum campo de credencial vazio com ação
        desabilitada; as três ações nomeadas presentes.
      - **Intake**: exatamente três fontes; as palavras exatas dos chips —
        "Receiving" na que recebe, "Ready — nothing arrived yet" nas caladas; a
        fonte que recebe expandida com última entrega e volume da semana; as
        caladas em uma linha; "Format & test" recolhido.
      - **YAML e confiança**: o conteúdo copiado contendo a URL de entrega deste
        deployment e o nome do delivery token; a linha de confiança nomeando o
        token e oferecendo rotação; nenhuma ocorrência do nome de permissão cru
        como mecanismo de confiança.
      - **Cadeia**: quatro nós, na ordem entrada → regra → ação → destino, cada
        um navegando para a tela dona.
- [x] T005 Rodar T004 e **confirmar o vermelho**, com a lista de asserções que
      falham colada em `controle.md`. Uma asserção que passa antes da
      implementação é uma asserção que não mede o que promete: revisar antes de
      seguir.

---

## Fase 3: Foundational — o que o payload precisa dizer

Bloqueia as fases 5, 6 e 8. As tarefas de teste desta fase são independentes
entre si.

- [x] T006 [P] Teste de contrato, falhando primeiro: o catálogo distingue
      explicitamente credencial ausente, credencial guardada sem verificação e
      credencial verificada — em `tests/contract/console/`.
- [x] T007 [P] Teste de contrato, falhando primeiro: quando o estate descobriu
      o serviço, o item de catálogo carrega o endereço descoberto num campo
      próprio, utilizável como placeholder, e o nome de serviço e o container
      separados do identificador do recurso.
- [x] T008 [P] Teste de contrato, falhando primeiro: a fonte de intake do
      Alertmanager serve um bloco de receiver pronto, contendo a URL de entrega
      do deployment e o header de autorização com o nome do delivery token em
      uso — e **não** contendo o valor de um segredo já guardado.
- [x] T009 Servir a distinção de estado de credencial e o endereço descoberto em
      `gateway/http/routes/integrations.py`; regenerar o client
      (`make console-client`) e conferir `make console-client-check`.
- [x] T010 Gerar o bloco de receiver no módulo que possui a entrega de ingress e
      servi-lo por `gateway/http/routes/ingress.py`. A URL sai da configuração
      do deployment; o nome do token, do token em uso. Sem literais de endereço
      no código da rota.
- [x] T011 Servir o volume de entregas da janela da semana por fonte, junto do
      que a tela de intake já lê.

---

## Fase 4: User Story 1 — catálogo numa rolagem curta (P1)

- [x] T012 [US1] Teste de unidade (vitest), falhando primeiro: as três seções
      saem na ordem; uma seção vazia não é renderizada; a contagem do topo
      deriva do payload e perde o terceiro termo quando não há sugestões.
- [x] T013 [US1] Remover a paginação de
      `console/src/surfaces/integration-catalogue.tsx`: a seção Available lista
      o que resta, e a constante de tamanho de página sai junto com o seu único
      consumidor — não fica um número órfão em nenhum dos dois lados do
      espelhamento.
- [x] T014 [US1] Nomear a terceira seção como Available em
      `console/src/surfaces/screens/integrations.tsx` e ajustar a contagem do
      topo, com as strings em `en.ts` e `pt-BR.ts`.
- [x] T015 [US1] Busca por nome de exibição **e por capacidade**, filtrando
      dentro das seções sem alterar a ordem delas. A cobertura de capacidade é a
      lacuna que a onda anterior deixou aberta; o teste de T012 a cobre
      explicitamente.
- [x] T016 [US1] Teste de orçamento de rolagem para `/integrations`, com o
      viewport 1080p declarado no próprio spec e o catálogo pós-corte inteiro.

---

## Fase 5: User Story 2 — o detalhe sem perder o lugar (P1)

Depende da Fase 3 apenas para o placeholder do formulário; a geometria não
depende de payload.

- [x] T017 [US2] Teste de unidade, falhando primeiro: o `Drawer` renderiza
      sobreposto — com posição própria, acima do conteúdo — e não como bloco no
      fluxo do documento.
- [x] T018 [US2] Dar ao `Drawer` a sua sobreposição em
      `console/src/components/overlay.tsx`: ancorado, acima do conteúdo, sem
      empurrar nem redimensionar o catálogo. A trava de foco, o Escape e o
      retorno de foco que o overlay já faz permanecem intactos — o teste de
      T017 os cobre para provar que a mudança de geometria não os quebrou.
      **Antes de mexer, abrir os outros três consumidores do `Drawer`** —
      `console/src/shell/shell.tsx`, `console/src/live/investigate.tsx` e
      `console/src/gallery/registry.tsx` — e registrar em `controle.md` como
      cada um se comporta. Se algum depender de o drawer ocupar espaço no fluxo,
      a sobreposição vira opção do componente, pedida por quem a quer, em vez de
      comportamento único.
- [x] T019 [US2] Verificar, no acceptance spec, que a rolagem não muda ao abrir,
      que o deep-link aterrissa no topo do catálogo e que fechar devolve posição
      e filtros. A restauração de rolagem já existe no painel; o que faltava era
      medi-la.
- [x] T020 [US2] Placeholder do campo de endereço vindo do endereço descoberto
      pelo estate, e instrução por campo, em
      `console/src/surfaces/integration-panel.tsx`. Sem endereço descoberto, sem
      placeholder — nunca um endereço inventado.
- [x] T021 [US2] Deep-link para integração ausente do catálogo: o painel diz que
      ela não está disponível e oferece voltar ao catálogo e ver o roadmap.
      Teste incluído — é o caminho de quem procura um vendor que o corte tirou.

---

## Fase 6: User Story 3 — integração já conectada (P1)

Depende de T009.

- [x] T022 [US3] Teste de unidade, falhando primeiro: com credencial guardada, o
      painel não renderiza campo de credencial vazio nem ação desabilitada, e
      afirma que a credencial está no vault.
- [x] T023 [US3] Teste de unidade, falhando primeiro: as três ações — testar de
      novo, substituir a credencial, desconectar — estão presentes e nomeadas;
      substituir revela o mesmo formulário write-only.
- [x] T024 [US3] Implementar as três ações em
      `console/src/surfaces/integration-panel.tsx`, ramificando pelo estado de
      credencial que T009 passou a servir.
- [x] T025 [US3] Desconectar exige confirmação que nomeia a integração e o que
      será removido, pela confirmação destrutiva que a biblioteca já impõe.
- [x] T026 [US3] Teste de segurança: depois de guardar e depois de testar de
      novo, nenhum valor de credencial aparece na resposta da API nem em
      qualquer atributo do DOM do painel. Credencial guardada e nunca verificada
      é exibida como armazenada, nunca como falhando.

---

## Fase 7: User Story 4 — três fontes com estado real (P1)

- [x] T027 [US4] Teste de unidade, falhando primeiro: exatamente três fontes; a
      que recebeu vem expandida com o chip de recebimento, a última entrega e o
      volume da semana; as caladas ocupam uma linha com o chip de prontidão, nas
      palavras exatas do mockup.
- [x] T028 [US4] Reescrever a lista de fontes em
      `console/src/surfaces/settings/alert-intake.tsx`: expandida versus linha
      única, com as strings novas em `en.ts` e `pt-BR.ts`.
- [x] T029 [US4] Recolher formato esperado e envio de teste sob uma seção única
      por fonte, fechada por padrão; as rejeições recentes continuam visíveis na
      fonte.
- [x] T030 [US4] Teste de orçamento de rolagem para `/settings/alert-intake`,
      viewport 1080p declarado no próprio spec.

---

## Fase 8: User Story 5 — colar o receiver num gesto (P1)

Depende de T010.

- [x] T031 [US5] Teste, falhando primeiro: a URL completa da fonte é exibida com
      a ação de copiar ao lado; o conteúdo copiado do receiver do Alertmanager
      contém a URL de entrega deste deployment e o nome do delivery token.
- [x] T032 [US5] Exibir a URL completa por fonte com a ação de copiar, e a ação
      de copiar o receiver na fonte do Alertmanager, consumindo o bloco que o
      gateway devolve — sem montar o YAML por concatenação na tela.
- [x] T033 [US5] Trocar a linha de confiança: some o nome de permissão cru,
      entra "autenticada por delivery token `<nome>`" com a ação de rotação.
      Strings em `en.ts` e `pt-BR.ts`.
- [x] T034 [US5] A rotação leva a Machine tokens já filtrada para os tokens de
      entrega; sem token emitido, a linha diz isso e a ação oferecida é emitir.
      Teste do destino do CTA — o rótulo promete e o destino cumpre.
- [x] T035 [US5] Teste de segurança do bloco copiado: fora do gesto de emissão,
      o lugar do valor do token é um marcador explícito, e nenhum segredo
      guardado aparece no conteúdo copiado.

---

## Fase 9: User Story 6 — a cadeia visível (P2)

- [x] T036 [US6] Teste, falhando primeiro: quatro nós na ordem entrada → regra →
      ação → destino, cada um com o valor efetivo do deployment e cada um
      navegando para a tela dona; um nó sem valor configurado diz que não há e
      oferece configurá-lo, sem a cadeia encolher.
- [x] T037 [US6] Renomear as duas seções avançadas de
      `console/src/surfaces/settings/schedules-destinations.tsx` para termos
      disjuntos — ou fundi-las numa seção só. Nenhum substantivo em comum entre
      os dois nomes; strings em `en.ts` e `pt-BR.ts`. Esta tarefa vem **antes**
      da cadeia: enquanto as duas seções disputarem a mesma palavra, o nó de
      destino não consegue prometer um lugar e aterrissar nele.
- [x] T038 [US6] Teste de unidade dos nomes: os dois títulos não compartilham
      substantivo. O teste afirma a propriedade, não a string — e é pareado com
      a navegação de T039, que exercita o comportamento.
- [x] T039 [US6] Desenhar a cadeia em
      `console/src/surfaces/settings/alert-intake.tsx`, lendo dos mesmos dados
      que intake, regras e destinos já consomem, com cada nó linkando a tela
      dona.
- [x] T040 [US6] Rodar a suíte transversal
      (`console/tests/e2e/transversal-rules.spec.ts`) nas duas rotas desta
      feature e em `/settings/schedules-destinations`, que esta fase tocou.

---

## Fase 10: User Story 7 — o corte auditável (P3)

- [x] T041 [P] [US7] Rodapé do catálogo com a contagem das integrações movidas
      para o roadmap, derivada do payload, e o link para a página de referência;
      o empty state da busca sem resultado oferece limpar a busca e o mesmo
      link. Teste do link e da contagem.
- [x] T042 [P] [US7] Rodapé de Alert intake nomeando as fontes de intake que
      foram para o roadmap e a razão. Teste da presença e do texto.

---

## Fase 11: Polimento, baselines e gates

- [x] T043 Conferir en e pt-BR: toda string nova existe nos dois, e o
      vocabulário canônico de estado — não conectada, armazenada, verificada,
      degradada, falhando — não foi traduzido para nenhuma outra palavra em
      nenhuma das telas tocadas.
- [x] T044 `console/visual/screens.json`: a entrada do painel de credencial
      aponta hoje para `/integrations/slack`, um vendor que o corte da 001
      removeu. Repointar para uma integração sobrevivente — `/integrations/alertmanager`,
      que é a que o mockup desenha — ou registrá-la de novo nesse endereço caso
      a 001 a tenha removido junto com o vendor. A razão registrada na entrada
      diz o que a captura protege: o painel sobreposto ao catálogo, com
      instrução por campo e uma ação primária única.
- [x] T045 `make console-visual` para ver o que mudou nas rotas registradas, e
      revisar o diff de imagem antes de aceitar qualquer coisa.
- [x] T046 **Recaptura deliberada das baselines visuais das duas rotas** via
      `make console-visual-accept`: `/integrations` (catálogo e painel) e
      `/settings/alert-intake`. As três capturas são revisadas por uma pessoa
      antes de virarem mudança commitada, e a razão de aceitação de cada entrada
      em `screens.json` é atualizada para dizer contra o quê ela foi revisada.
      Uma baseline que um gate fabricou sozinho não conta e é apagada.
- [x] T047 Rodar o acceptance spec da Fase 2 inteiro e **confirmar o verde**,
      com a saída registrada em `controle.md`.
- [x] T048 `make verify` e `make console-check` verdes. Conferir nominalmente os
      gates que esta feature toca: nomes de exibição, documentação de
      integrações, integridade do catálogo, paridade de configuração, exemplos
      de documentação, e a cobertura de contrato do console contra a API.
- [x] T049 Reportar o efeito no corpus de cenários sintéticos. A expectativa é
      nenhum — nada aqui toca investigação —, e "nenhum efeito, medido" é o
      resultado a registrar. "Não medido" não é.
- [x] T050 Atualizar `controle.md` da feature: cada tarefa com o seu estado
      real, os números medidos (alturas antes e depois, posições de rolagem,
      contagens de fonte e de catálogo), a saída do vermelho e do verde do
      acceptance, e toda ressalva de honestidade — parcial é parcial, e um teste
      cujo vermelho não foi visto diz isso.

---

## Dependencies

- T001 bloqueia tudo: sem o corte da 001 na árvore, nenhuma medição desta
  feature é válida.
- T004 → T005 → todas as fases de implementação. O vermelho confirmado é a
  porta de entrada.
- Fase 3 (T006–T011) bloqueia T020 (placeholder), a Fase 6 inteira (estado de
  credencial) e a Fase 8 (bloco de receiver).
- T012 → T013 → T014 → T015 → T016.
- T017 → T018 → T019; T018 é o conserto de geometria de que T019 depende.
- T022, T023 → T024 → T025 → T026.
- T027 → T028 → T029 → T030.
- T031 → T032 → T033 → T034 → T035.
- T037 → T038 e T037 → T039 → T036 verde. A renomeação vem antes da cadeia.
- T043 → T044 → T045 → T046. Nenhuma baseline é aceita antes de o texto estar
  no lugar.
- T047 → T048 → T049 → T050.
