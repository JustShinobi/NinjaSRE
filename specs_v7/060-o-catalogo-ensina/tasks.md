# Tasks: O catálogo ensina — todo campo diz o que criar e o que marcar

**Input**: Design documents from `specs_v7/060-o-catalogo-ensina/`

**Prerequisites**: spec.md, plan.md. Depende do renderizador de markdown
entregue pela feature de leitura do relato (slot anterior, já mergeada) e do modo
de aceitação contra staging entregue pela feature de governança.

**Tests**: test-first, sem exceção. O acceptance aterrissa vermelho antes de
qualquer tela; o gate aterrissa vermelho contra a árvore atual — que tem 28
campos sem permissão mínima e 29 sem guia — antes de qualquer conteúdo ser
escrito. Cada vermelho é capturado com a mensagem real.

## Regras que valem para toda tarefa deste arquivo

1. **Nada de identificador de planejamento em arquivo committed.** Nenhum teste,
   comentário, docstring, documento de pacote ou mensagem de commit cita
   identificador de requisito, número de artigo, número de feature ou caminho de
   diretório de planejamento. A substância vai no arquivo; a referência fica na
   spec.
2. **Conteúdo por vendor é pesquisa, nunca geração.** Toda permissão mínima e
   todo guia sai da documentação do próprio fornecedor, lida agora. A fonte é
   citada no `docs.md` daquele pacote. **Um escopo plausível é pior que um campo
   em branco** — se a documentação do fornecedor não responder, pare a tarefa e
   registre a pergunta em vez de escrever um valor verossímil.
3. **Nunca copiar orientação de um vendor para outro.** `grafana` e `loki` são da
   mesma casa e têm modelos de permissão diferentes. `alertmanager` e
   `prometheus` não têm modelo de permissão nenhum, e a resposta honesta para
   eles é sobre o que o proxy reverso à frente aceita.
4. **Um segundo renderizador de markdown é proibido.** Localize o que o slot
   anterior mergeou e use-o. Não acrescente dependência ao `console/package.json`.
5. **Esta feature é dona dos arquivos de escrita única no slot.** Catálogo de
   mensagens e registro de telas visuais são editados aqui. O registro de rotas
   do console **não é tocado** — nenhum endereço novo de console nasce.
6. **A verificação não pode adquirir dependência de rede.** O gate checa presença
   e forma do guia. Nenhuma requisição, em nenhum alvo de build.
7. **"Testes verdes no harness" não fecha tarefa de comportamento.** O endereço
   novo fecha contra a aplicação construída; o gate fecha com `make verify`; as
   telas fecham com o acceptance.

---

## Phase 0: Linha de base

- [ ] T001 Rodar `make verify` na árvore intacta e guardar o log fora do
      repositório. Registrar, do próprio log: o resultado da verificação de
      integrações e quantos testes passam. Se não estiver verde, parar e reportar
      antes de escrever qualquer coisa. **Sem este log, uma falha preexistente é
      debitada desta feature e uma falha desta feature se esconde atrás de "já
      estava assim".**
- [x] T002 Registrar as contagens de partida a partir dos schemas reais, não
      deste documento: total de campos de credencial por vendor, quantos são
      secretos, quantos são de configuração pública, quantos são de endereço,
      quantos declaram permissão mínima e quantos declaram guia. A spec afirma
      40 / 21 / 8 / 11 / 12 / 11 — confirmar cada número contra a árvore e
      reportar qualquer divergência antes de prosseguir.
- [x] T003 Localizar o renderizador de markdown que o slot anterior mergeou e
      registrar seu caminho e sua política de sanitização no relatório. Registrar
      também qual dependência do `console/package.json` o sustenta — é o número
      que a tarefa de fechamento vai reconferir.

## Phase 1: Vermelhos, antes de tudo

Toda tarefa desta fase escreve teste contra a árvore atual e **tem de falhar**.

- [x] T004 [P] `console/tests/e2e/catalogue-teaches.acceptance.spec.ts`: as
      treze alegações normativas da spec, uma asserção cada, medidas em
      1920×1080. As que abrem `grafana`, `prometheus` e `proxmox` são marcadas
      como seguras contra ambiente compartilhado; as duas da recusa em HTTP claro
      **não** são, porque escrevem credencial. Confirmar vermelho.
- [x] T005 [P] Teste de contrato em `tests/contract/integrations/`: todo campo
      secreto de todo vendor embarcado declara permissão mínima. Confirmar
      vermelho — hoje faltam nove.
- [x] T006 [P] Teste de contrato em `tests/contract/integrations/`: nenhum campo
      de endereço e nenhum campo de configuração pública declara permissão
      mínima. **Este nasce verde** — hoje os 19 estão em branco — e é a rede que
      pega uma tarefa de conteúdo inventando escopo para um namespace. Registrar
      que passou, e por quê.
- [x] T007 [P] Teste de contrato em `tests/contract/integrations/`: todo campo de
      todo vendor embarcado declara um guia, e todo guia é um endereço absoluto.
      Confirmar vermelho — hoje faltam 29.
- [x] T008 [P] Teste de contrato em `tests/contract/integrations/`: todo vendor
      embarcado declara a frase que diz onde obter sua credencial. Confirmar
      vermelho — hoje nenhum declara. **A frase é enforçada por teste de contrato
      e não pelo gate**: o relatório do gate é sobre campos de credencial, e a
      frase é sobre o vendor.
- [x] T009 [P] Teste de contrato em `tests/contract/gateway/`: o endereço de
      documentação de um vendor embarcado, pedido **à aplicação construída**,
      devolve o texto do documento daquele pacote; um nome que não é de vendor
      embarcado é uma ausência nomeada. Confirmar vermelho — o endereço não
      existe.
- [x] T010 [P] Teste em `tests/security/`: o endereço de documentação está
      declarado no registro de rotas do gateway com a mesma permissão da leitura
      do catálogo. Confirmar vermelho.
- [x] T011 [P] Teste em `tests/unit/platform/credentials/`: uma chamada com
      credencial resolvida contra endereço `http://` é recusada com uma frase que
      nomeia o esquema, oferece o endereço TLS e oferece não armazenar
      credencial; a classificação da recusa é a mesma de hoje. Confirmar
      vermelho — hoje a frase é a da lista de egresso.
- [x] T012 [P] Teste em `tests/unit/platform/credentials/`: uma chamada **sem**
      credencial resolvida contra endereço `http://` não é recusada por este
      motivo. Caracterização — deve passar antes e continuar passando depois.
      Registrar que passou.
- [x] T013 [P] Teste em `console/tests/unit/surfaces/`: o painel da integração
      renderiza a frase "onde obter" quando o vendor a declara, e não renderiza
      lugar nenhum quando não declara. Confirmar vermelho.
- [x] T014 [P] Teste em `console/tests/unit/surfaces/`: o passo de integrações do
      primeiro acesso renderiza a mesma frase para o mesmo vendor. Confirmar
      vermelho.
- [x] T015 [P] Teste em `console/tests/unit/surfaces/`: o painel da integração
      oferece a documentação do pacote renderizada, e diz que não conseguiu ler
      quando a leitura falhou — nunca que o documento não existe. Confirmar
      vermelho.
- [x] T016 Confirmar e registrar o vermelho de T004, T005, T007, T008, T009,
      T010, T011, T013, T014 e T015 com a mensagem real de cada um, e o verde de
      T006 e T012. **Portão**: nenhuma implementação começa antes disto.

## Phase 2: A regra e o gate

- [x] T017 Escrever `integrations/_catalogue/guidance.py`: a regra de orientação
      por tipo de campo — permissão mínima obrigatória em campo secreto, proibida
      em campo de endereço e em campo de configuração pública, guia obrigatório em
      todo campo e obrigatoriamente absoluto. O módulo devolve, para um schema,
      a lista do que falta e do que sobra, **nomeando campo e dizendo o que a
      ausência custa** — a mesma forma que a validação de paridade já usa ao lado.
      O módulo diz de si mesmo, em substância, que verifica presença e forma do
      guia e nunca alcançabilidade, e por quê.
- [x] T018 Ligar a regra em `tools/verify_integrations.py` como uma regra a mais
      do relatório de problemas, ao lado de paridade e de sondagem de permissão.
      Todos os problemas coletados antes de falhar; cada linha nomeia vendor e
      campo. Nenhum alvo novo no `Makefile` — a regra roda dentro da verificação
      de integrações, que já está em `make verify`.
- [x] T019 Provar o gate pelos dois lados: apagar a permissão mínima de um campo
      secreto e ver `make check-integrations` reprovar nomeando aquele vendor e
      aquele campo; declarar uma permissão mínima num campo de endereço e ver
      reprovar do mesmo jeito; restaurar as duas. Capturar as mensagens reais.
      T005, T006 e T007 continuam refletindo a árvore real (T005 e T007 seguem
      vermelhos até a Fase 3 terminar).

## Phase 3: Conteúdo por vendor — quinze tarefas independentes

Cada tarefa cobre um vendor e faz três coisas nele: preenche o que falta no
`schema.py`, declara a frase "onde obter" no perfil do pacote, e atualiza o
`docs.md` com a fonte de cada valor novo e com a tabela de campos em dia. **A
fonte é a documentação do próprio fornecedor, lida agora, e o endereço dela vai
citado no `docs.md`.** Se a documentação não responder, a tarefa para e registra
a pergunta — nada é preenchido por verossimilhança.

O que falta em cada vendor está nomeado abaixo, derivado dos schemas em
2026-08-23. Reconferir contra a árvore antes de escrever: a lista é o ponto de
partida, não a autoridade.

- [x] T020 [P] **alertmanager** — guia para `endpoint` e para `token`. A
      permissão mínima de `token` já existe e diz que depende do proxy reverso à
      frente; confirmar que continua sendo a resposta verdadeira e citar a fonte.
- [x] T021 [P] **argocd** — guia para `endpoint`. Permissão mínima e guia de
      `token` já existem; confirmar e citar a fonte.
- [x] T022 [P] **github** — guia para `endpoint` e para `owner`. Permissão mínima
      e guia de `token` já existem; confirmar contra o modelo de permissões atual
      de token de acesso pessoal e citar a fonte.
- [x] T023 [P] **google_gemini** — nada falta: `api_key` já declara os dois, e o
      vendor não tem campo de endereço. A tarefa é confirmar que a permissão
      mínima declarada continua verdadeira, citar a fonte no `docs.md`, e
      declarar a frase "onde obter".
- [x] T024 [P] **grafana** — guia para `endpoint` e para `org`. Permissão mínima
      e guia de `token` já existem; confirmar e citar a fonte.
- [x] T025 [P] **hermes** — guia para `endpoint`, `api_key` e `stream`. **Este é
      o vendor sem site de documentação de fornecedor**: os guias apontam o
      documento do próprio pacote, servido por este deployment pelo endereço da
      Fase 5. Registrar a decisão no `docs.md` em substância e reportá-la ao
      operador no relatório final.
- [x] T026 [P] **kubernetes** — guia para `endpoint`, `cluster` e `namespace`.
      Permissão mínima e guia de `token` já existem e citam verbos sobre recursos
      concretos; confirmar contra o que as capacidades do pacote realmente chamam
      e citar a fonte.
- [x] T027 [P] **loki** — guia para `endpoint` e para `token`. A permissão mínima
      de `token` já existe; confirmar que ela é a de Loki e não a de Grafana, e
      citar a fonte.
- [x] T028 [P] **openobserve** — permissão mínima **e** guia para `username`
      (que é secreto porque viaja com a senha), guia para `endpoint`, `password`
      e `organisation`. A permissão mínima de `password` já existe; confirmar e
      citar a fonte.
- [x] T029 [P] **prometheus** — guia para `endpoint` e para `token`. A permissão
      mínima de `token` já existe e diz que depende do proxy reverso à frente;
      confirmar e citar a fonte.
- [x] T030 [P] **proxmox** — o vendor com mais campos e o mais delicado. Guia
      para `endpoint` e `username`; permissão mínima **e** guia para `password`,
      `ticket` e `csrf_token`. A permissão mínima de `api_token` já existe e nomeia
      privilégios de auditoria concretos; confirmar e citar a fonte. `ticket` e
      `csrf_token` são material de sessão emitido pelo próprio Proxmox: a
      permissão mínima deles é a do login que os emitiu, e é isso que a declaração
      diz — não um escopo inventado. `api_token` e `password` são alternativas um
      do outro e cada um carrega a sua própria orientação.
- [x] T031 [P] **pushover** — permissão mínima para `token` e para `user_key`. Os
      guias já existem; confirmar que continuam apontando as páginas certas e
      citar a fonte. Pushover não tem modelo de escopo: se a resposta verdadeira
      for "o token de aplicação não carrega escopo, e a chave identifica o
      destinatário", é isso que a declaração diz.
- [x] T032 [P] **redis** — permissão mínima para `api_key` e guia para
      `secret_key`. A permissão mínima de `secret_key` e o guia de `api_key` já
      existem; confirmar os dois contra a documentação da API de conta e citar a
      fonte.
- [x] T033 [P] **signoz** — permissão mínima e guia para `api_key`, guia para
      `endpoint`. O vendor não declara nenhum dos dois hoje; é o único nessa
      situação.
- [x] T034 [P] **telegram** — permissão mínima para `token`. O guia já existe.
      Se a resposta verdadeira for que um token de bot não carrega escopo e vale
      exatamente o que o bot pode fazer, é isso que a declaração diz.
- [x] T035 Acrescentar ao perfil de integração o campo que carrega a frase "onde
      obter", com valor padrão vazio, e a validação que o perfil já aplica aos
      seus outros textos. Esta tarefa precede as quinze acima em ordem de escrita,
      mas é listada aqui porque é a mesma unidade de trabalho: sem o campo, as
      quinze não têm onde declarar a frase.
- [x] T036 Conferir a aritmética contra a árvore: os 21 campos secretos declaram
      permissão mínima, os 19 restantes não declaram nenhuma, os 40 declaram guia,
      os 15 vendors declaram a frase. T005, T007 e T008 passam a verde; T006
      continua verde. `make check-integrations` passa.

## Phase 4: A mesma frase nas duas telas

- [x] T037 Servir a frase "onde obter" no catálogo: acrescentá-la à visão de
      integração da rota e ao leitor de catálogo que já existe ao lado, lendo do
      perfil do vendor. Nenhuma cópia da frase em nenhum dos dois.
- [x] T038 Ler a frase na tela do catálogo e passá-la ao painel; o painel passa-a
      ao formulário de credencial. Corrigir, no mesmo passo, o comentário do
      leitor de campos que hoje diz que a permissão mínima "o schema quase sempre
      deixa em branco" — deixa de ser verdade nesta feature, e um comentário que
      mente sobre o dado ao lado é a próxima pessoa tomando a decisão errada.
      T013 passa a verde.
- [x] T039 Levar a mesma frase à oferta de integração do primeiro acesso e ao
      passo que a renderiza. Duas edições localizadas: o bloco que monta as
      ofertas e a chamada do passo. **Declará-las no relatório final** — o arquivo
      que compõe os passos do primeiro acesso é tocado também pela feature
      parceira do slot. T014 passa a verde.
- [x] T040 Provar que as duas telas leem a mesma declaração: um teste que afirma
      que a frase renderizada num lado é caractere por caractere a mesma do outro,
      para o mesmo vendor.

## Phase 5: A documentação do pacote, servida

- [x] T041 Acrescentar o endereço de documentação ao router de integrações que a
      aplicação já monta. A resposta é um documento com o nome, o nome de exibição
      e o markdown. **O caminho do arquivo vem do relatório de paridade da entrada
      de catálogo, nunca composto a partir do valor recebido na URL**; um nome que
      não é de vendor embarcado é ausência nomeada antes de qualquer acesso a
      disco. T009 passa a verde.
- [x] T042 Declarar o endereço no registro de rotas do gateway com a mesma
      permissão que a leitura do catálogo exige. T010 passa a verde.
- [x] T043 Regenerar o contrato da API e o tipo derivado que o console consome,
      pelos geradores existentes. Nenhum arquivo gerado editado à mão.
- [x] T044 Ler a documentação na tela do catálogo quando — e só quando — um
      painel está aberto, e passá-la ao painel como propriedade. Uma leitura
      falhada é dita como leitura falhada, com o vocabulário de falha de leitura
      que a tela já usa, e nunca como documento inexistente.
- [x] T045 Renderizar a documentação no painel com o renderizador que a Fase 0
      localizou, dentro de uma seção que o operador abre. Nenhuma dependência
      nova. Chaves de mensagem novas em `en` e `pt-BR` — título da seção, o
      controle que a abre, e a frase de leitura falhada. T015 passa a verde.
- [x] T046 Provar que o documento de cada um dos 15 pacotes chega na imagem
      construída do produto, e não só no checkout: ajustar a inclusão de arquivos
      do pacote se for preciso, e verificar contra o artefato construído. **Se
      isto não for provado contra a construção, a rota responde ausência em
      produção e passa em todo teste local.**

## Phase 6: A recusa de credencial em claro

- [x] T047 Acrescentar, ao lado da recusa de lista de egresso, uma recusa própria
      para credencial em conexão não cifrada: **mesma classificação**, mensagem
      que nomeia o esquema pelo qual o vendor foi apontado e oferece as duas
      saídas — apontar para o endereço TLS, ou não armazenar credencial e conectar
      só por endereço. A mensagem não cita valor nenhum, como nenhuma mensagem
      deste módulo cita.
- [x] T048 Passar a levantá-la no ponto que já faz a recusa, sem mudar quando a
      recusa acontece. T011 passa a verde; T012 continua verde.
- [x] T049 Provar que a frase atravessa o fio: um teste que faz a chamada passar
      pelo motor do proxy e lê a sentença do outro lado, pelo registro de erro que
      o transporte já reconstrói. **Nenhuma superfície recebe uma cópia da
      frase** — se alguma precisar, a tarefa parou no lugar errado.
- [ ] T050 Conferir na tela: com um vendor apontado para `http://` e credencial
      armazenada, a frase aparece no painel como o detalhe do veredito, e o chip
      de estado é o mesmo que a classificação sempre produziu. As duas alegações
      correspondentes do acceptance passam a verde, no backing local.

## Phase 7: Evidência e fechamento

- [x] T051 Rodar o acceptance completo no backing local e confirmar verde. Cada
      alegação normativa com uma asserção que a nomeia.
- [ ] T052 Atualizar o registro de telas visuais para o slide-over, que mudou de
      conteúdo, e aceitar a baseline **deliberadamente**, revisada como imagem —
      nunca uma captura que o gate fabrique. Declarar no registro qual viewport a
      entrada mede.
- [x] T053 Rodar a suíte transversal de regras de interface e confirmar que a
      seção de documentação não viola nenhum ban — em particular o de markdown
      cru impresso como texto, que esta feature acrescenta uma superfície nova
      para violar.
- [ ] T054 Rodar as suítes unitárias do console e a suíte Python inteira, e
      confirmar verde.
- [x] T055 Depois do merge do slot e do deploy de staging feito pelo orquestrador,
      rodar contra `https://stg-ninjasre.lan.kyo.ninja` as alegações marcadas como
      seguras, abrindo `grafana`, `prometheus` e `proxmox`, e guardar screenshot
      full-page de cada uma no `evidence/` da feature. As duas alegações da recusa
      em HTTP claro **não** rodam lá.
- [ ] T056 Rodar `make verify` e comparar, alvo por alvo, com o log de T001. Todo
      alvo que passava continua passando; a verificação de integrações reporta as
      15 em paridade e nenhum campo sem orientação. Qualquer diferença é explicada
      ou corrigida, nunca omitida.
- [x] T057 Conferir que o `console/package.json` declara exatamente um
      renderizador de markdown, o mesmo que a Fase 0 registrou.
- [x] T058 Conferir que nenhum arquivo committed desta feature cita identificador
      de requisito, número de artigo, número de feature ou caminho de documento de
      planejamento, e que nenhum teste lê arquivo fora do repositório.
- [x] T059 Atualizar o `controle.md` desta feature com o que o código prova: o
      vermelho capturado de cada teste da Fase 1, o antes e o depois das seis
      contagens de T002, a fonte citada de cada permissão mínima e de cada guia
      novo, a resposta de "quem constrói isso em produção?" para os quatro
      mecanismos, as evidências de staging, e toda ressalva de honestidade —
      inclusive qualquer teste cujo vermelho não foi visto antes da implementação,
      e por quê.
- [x] T060 Reportar ao operador, no relatório final: a decisão do guia de
      `hermes`; qualquer vendor cuja documentação não respondeu e cujo campo ficou
      com uma pergunta em vez de um valor; as chaves de mensagem criadas; e as
      duas edições no arquivo que compõe os passos do primeiro acesso, para o
      merge do slot.

## Dependencies

- T001 → T002 → T003 → toda a Fase 1.
- T016 é portão: nenhuma implementação começa antes do vermelho confirmado.
- T017 → T018 → T019. A Fase 2 é independente da Fase 3 e pode correr antes dela;
  correr antes é melhor, porque o gate passa a nomear exatamente o que falta.
- T035 precede T020..T034 na ordem de escrita (o campo antes das quinze
  declarações). T020..T034 são paralelas entre si — vendors distintos, arquivos
  distintos, nenhuma disputa. T036 depende das quinze e de T035.
- T037 depende de T035 e T036; T038 e T039 dependem de T037; T040 depende de T038
  e T039.
- T041 → T042 → T043; T044 → T045 dependem de T041 e de T003. T046 depende de
  T041.
- A Fase 6 é independente das Fases 3 a 5 e pode correr a qualquer momento depois
  de T016. T047 → T048 → T049 → T050.
- T051 depende das Fases 3 a 6. T052 depende de T051. T055 depende do merge do
  slot e do deploy, feitos pelo orquestrador. T056 depende de tudo; T059 e T060
  são as últimas.
