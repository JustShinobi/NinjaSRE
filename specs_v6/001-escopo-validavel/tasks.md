# Tasks: Escopo validável — o catálogo cai para o que o ambiente valida

**Input**: Design documents from `specs_v6/001-escopo-validavel/`

**Prerequisites**: spec.md, plan.md. Nenhuma feature anterior — esta é a raiz da
onda.

**Tests**: test-first. O vermelho de cada gate é confirmado contra a árvore de
85 **antes** de qualquer pacote sair. Uma remoção validada só depois do fato não
distingue "removi certo" de "o teste não olha".

## Regras que valem para toda tarefa deste arquivo

1. **Nada de identificador de planejamento em arquivo committed.** Nenhum
   teste, comentário, docstring, documento gerado, registro de decisão ou
   mensagem de commit cita identificador de requisito, número de artigo,
   número de feature ou caminho de diretório de planejamento. A substância vai
   no arquivo; a referência fica nesta spec.
2. **A remoção é por vendor, com os satélites juntos.** Cada vendor removido sai
   com cinco coisas: o pacote em `integrations/<nome>/`, a skill de metodologia
   em `capabilities/skills/<nome>/`, o cenário sintético em
   `tests/synthetic/integration_scenarios/<nome>.py`, a documentação por
   integração (que vive dentro do pacote) e as fixtures que só existiam para
   ele.
3. **Nunca apagar por padrão de nome.** `redis` é substring de `redis_server`,
   `proxmox` é prefixo de `proxmox_backup_server`, `aws` é prefixo de oito
   pacotes dos quais todos saem mas cujo nome-base também sai. Remova por nome
   exato, conferindo a lista.
4. **Componente homônimo não é o pacote de integração.** Destinos de notificação
   e superfícies de chat com nome de vendor removido (Slack, Microsoft Teams,
   Discord, PagerDuty) ficam onde estão. Se uma remoção quebrar um deles, a
   remoção passou do alvo.
5. **Documentação gerada é regenerada, nunca editada à mão.**
6. **Gate não é afrouxado para o corte passar.** Se a paridade reprovar uma das
   15 mantidas, o defeito é da remoção, não do gate.

## Amendment (post-start): skills are archived, not deleted

Decisão do operador tomada depois que a execução começou, e que emenda a spec
neste ponto: as 70 skills de metodologia dos vendors removidos **não são
apagadas**. Elas têm valor como base para trabalho futuro. Ficam movidas,
frontmatter preservado, para um diretório de arquivo committed fora da raiz de
descoberta de skills — de modo que `discover_skills`/`build_registry` não as
varra (o pacote de integração que `directs_tools`/`requires.integrations`
apontam já não existe, e continuar descobrindo essas skills quebraria o
catálogo de capacidades). Onde este arquivo falar em "70 skills removidas",
leia-se "70 skills arquivadas fora da raiz de descoberta". Os cenários
sintéticos dos 70 continuam saindo por completo — a decisão vale só para o
texto de metodologia.

## Phase 0: Linha de base

- [x] T001 Rodar a verificação completa do repositório na árvore intacta e
      guardar o log fora do repositório. Registrar, do próprio log: quantas
      integrações a verificação de integrações reporta em paridade total,
      quantos testes passam e quais falham. **Sem este log, uma falha
      preexistente é debitada do corte e uma falha do corte se esconde atrás de
      "já estava assim".** Se a linha de base não estiver verde, parar e
      reportar antes de remover qualquer coisa.
      **FEITO** (pelo orquestrador, antes desta sessão): log em
      `baseline-001-pre.log`, fora do repositório. `make verify` exit 0;
      `14096 passed, 25 skipped, 15 warnings in 609.95s`; `85 integration(s)
      at full parity, every permission probed`; `29 documented example(s)
      check out`.
- [x] T002 Registrar as contagens de partida a partir da árvore, não de um
      documento: pacotes de vendor em `integrations/`, diretórios de skill de
      metodologia que correspondem a vendor, arquivos de cenário sintético por
      integração, e fontes de intake declaradas. Esses quatro números são o
      "antes" contra o qual o corte é medido: a árvore precisa perder exatamente
      70 pacotes, 70 skills e 70 cenários, e as fontes precisam cair de sete
      para três.
      **FEITO**: confirmado na árvore antes de qualquer remoção —
      `integrations/`: 85 pacotes de vendor; `capabilities/skills/`: 97
      entradas (96 diretórios + `README.md`), das quais 85 correspondem
      exatamente a um vendor instalado e 12 não (`_templates` e 11 skills de
      metodologia geral: `changes`, `infrastructure`, `investigate`,
      `observability`, `remediation`, `proxmox_backup`, `proxmox_guest`,
      `proxmox_node_host`, `proxmox_storage`, `proxmox_two_node`, mais o
      próprio `proxmox` correspondendo ao vendor); `tests/synthetic/integration_scenarios/`:
      87 entradas (85 arquivos de cenário + `__init__.py` + `__pycache__`);
      fontes de intake declaradas em `gateway/webhooks/router.py` (`PROFILES`)
      e replicadas em `gateway/http/security/gateway_routes.py`
      (`WEBHOOK_ROUTES`) e em `tests/security/test_gateway_route_permissions.py`:
      7 (`alertmanager`, `pagerduty`, `datadog`, `grafana`, `sentry`,
      `opsgenie`, `generic`).

## Phase 1: Gates primeiro, confirmados vermelhos

Todas as tarefas desta fase escrevem teste contra a árvore de 85 e **têm de
falhar**. O vermelho de cada uma é capturado com a mensagem real.

- [x] T003 [P] Teste de contrato em `tests/contract/integrations/`: o catálogo
      descoberto contém exatamente os 15 nomes mantidos, e nenhum outro. O teste
      carrega a lista dos 15 como dado do próprio teste — é a única lista
      literal que esta feature autoriza, porque ela **é** a decisão. Confirmar
      vermelho: hoje o catálogo tem 85.
      **FEITO**: `tests/contract/integrations/test_the_catalogue_matches_the_validated_scope.py`.
- [x] T004 [P] Teste de contrato em `tests/contract/integrations/`: toda
      integração do catálogo está em paridade completa nos sete artefatos. Deve
      passar já (é a garantia vigente) e é a rede que pega uma das 15 perdendo
      artefato durante a remoção. Registrar que **passou** — este é o único
      teste da fase que não nasce vermelho, e o motivo fica escrito.
      **FEITO (já existia, verificado)**: `test_the_integration_ships_all_seven_artefacts`
      em `tests/contract/integrations/test_integration_parity.py`.
- [x] T005 [P] Teste de contrato do intake em `tests/contract/`: a enumeração de
      fontes de alerta do domínio declara exatamente `alertmanager`, `grafana` e
      `generic`. Confirmar vermelho: hoje são sete.
      **FEITO**: `tests/contract/alerts/test_intake_sources.py`.
- [x] T006 [P] Teste de contrato do intake em `tests/contract/`: o endereço de
      intake de cada uma das quatro fontes removidas responde como endereço
      inexistente, e não como falha de autenticação nem de servidor. Confirmar
      vermelho: hoje as rotas existem.
      **FEITO**: mesmo arquivo de T005.
- [x] T007 [P] Teste de contrato do intake em `tests/contract/`: as três fontes
      mantidas aceitam a mesma carga que aceitam hoje, com o mesmo resultado.
      Caracterização — deve passar antes e continuar passando depois. É o que
      distingue "reduzi as fontes" de "quebrei o intake".
      **FEITO**: mesmo arquivo de T005; verde antes e depois, confirmado nas
      duas rodadas.
- [x] T008 [P] Teste em `tests/architecture/`: nenhum arquivo committed nomeia
      um vendor removido, com duas exceções nomeadas no próprio teste — o
      roadmap committed e o registro de decisão novo. O teste inspeciona texto,
      então declara isso de si mesmo e é pareado com T003, que exerce o
      comportamento. Confirmar vermelho: hoje há 70 pacotes.
      **FEITO**: `tests/architecture/test_removed_vendor_references.py`, duas
      checagens (import Python + referência textual em superfícies de
      documentação/console). Terceira exceção (`docs/methodology/archive/`)
      adicionada junto da emenda de arquivamento. Reconfirmado verde depois
      de toda a Fase 2–3: `2 passed`.
- [x] T009 Confirmar e registrar o vermelho de T003, T005, T006 e T008 com a
      mensagem real de cada um, e o verde de T004 e T007. Só depois disto a
      Fase 2 começa.
      **FEITO** — mensagens reais capturadas e citadas no relatório final e no
      `controle.md`.

## Phase 2: Remoção dos 70 pacotes

As oito tarefas são independentes entre si — a descoberta do catálogo varre o
diretório e não há arquivo de registro central para disputar. Cada uma remove o
pacote, a skill, o cenário e as fixtures próprias de cada vendor do seu grupo.

- [x] T010 [P] Família AWS (9): `aws`, `aws_cloudtrail`, `aws_ec2`, `aws_ecs`,
      `aws_eks`, `aws_elb`, `aws_lambda`, `aws_rds`, `aws_s3`.
- [x] T011 [P] Outras nuvens e armazéns de dados (11): `azure`, `azure_monitor`,
      `azure_sql`, `gcp`, `bigquery`, `snowflake`, `clickhouse`, `opensearch`,
      `elasticsearch`, `mongodb_atlas`, `supabase`.
- [x] T012 [P] Observabilidade de terceiros (11): `datadog`, `new_relic`,
      `honeycomb`, `coralogix`, `better_stack`, `splunk`, `groundcover`,
      `jaeger`, `tempo`, `victoriametrics`, `victorialogs`.
- [x] T013 [P] Incidente e plantão (7): `sentry`, `pagerduty`, `opsgenie`,
      `incident_io`, `firehydrant`, `blameless`, `servicenow`.
- [x] T014 [P] Ticketing e documentos (7): `jira`, `linear`, `trello`,
      `clickup`, `notion`, `confluence`, `google_docs`.
- [x] T015 [P] Chat e mensageria de terceiros (6): `slack`, `microsoft_teams`,
      `discord`, `rocket_chat`, `twilio`, `whatsapp`. **Atenção redobrada aqui**:
      quatro destes nomes também existem como destino de notificação ou como
      superfície de chat, em módulos próprios. Só o pacote de integração sai.
      Confirmado: `gateway/slack/`, `gateway/discord/`, `gateway/teams/` e
      `platform/notifications/sinks/pagerduty.py` intactos.
- [x] T016 [P] Código, build e entrega (6): `gitlab`, `bitbucket`, `jenkins`,
      `vercel`, `railway`, `sourcegraph`.
- [x] T017 [P] Dados em movimento, produto e o resto (13): `airflow`, `dagster`,
      `prefect`, `flink`, `spark`, `kafka`, `rabbitmq`, `temporal`, `amplitude`,
      `posthog`, `flagd`, `proxmox_backup_server`, `docker`.
      Pacotes e cenários dos 70 removidos por completo. Skills **arquivadas**
      (emenda acima) em `docs/methodology/archive/<vendor>/SKILL.md`,
      frontmatter preservado, fora da raiz de descoberta.
      **FEITO**: as 70 skills foram restauradas de `HEAD` (nunca via
      `git checkout`/`git mv` — leitura de conteúdo com `git show HEAD:<path>`
      seguida de `Write` num caminho novo, depois remoção do original com
      `mv`/`rm` de shell) e agora vivem em
      `docs/methodology/archive/<vendor>/SKILL.md`, frontmatter e corpo
      idênticos ao committed. `docs/methodology/archive/README.md` explica a
      decisão sem citar identificador de planejamento.
- [x] T018 Conferir a aritmética contra a árvore: 85 menos 70 são 15, os 15 são
      os nomeados, e as contagens de skill e de cenário caíram na mesma
      proporção. Rodar T003 e T004 — o primeiro passa a verde, o segundo
      continua verde. Se T004 reprovar, uma das 15 perdeu artefato na remoção.
      **FEITO**: `integrations/` = 15 pacotes de vendor;
      `tests/synthetic/integration_scenarios/` = 15 arquivos de cenário;
      `capabilities/skills/` = 26 entradas (15 vendor + 11 não-vendor, 0
      arquivo de vendor removido restante); `docs/methodology/archive/` = 70
      diretórios de vendor + `README.md`. T003 verde (5/5); T004 verde
      (paridade das 15, sete artefatos cada).
- [x] T019 Remover as dependências opcionais declaradas que só existiam para
      pacote removido, e atualizar o arquivo de lock correspondente.
      **Verificado, nada a remover**: `pyproject.toml`'s
      `[project.optional-dependencies]` só declara SDKs de provedor de modelo
      (anthropic, openai, azure, openrouter, nvidia, ollama, bedrock, google,
      litellm), nenhum ligado a um vendor de integração; nenhum dos 70
      pacotes importava um SDK de vendor (todos usavam o cliente
      compartilhado via proxy). `uv.lock` não mudou.

## Phase 3: Intake enxuto

- [x] T020 Reduzir as fontes de intake às três mantidas: retirar as quatro
      removidas do roteamento de webhook e da enumeração de fonte do domínio.
      T005 e T006 passam a verde; T007 continua verde.
      **FEITO**, incluindo dois pontos de duplicação achados fora da lista
      explícita: `gateway/http/security/gateway_routes.py:WEBHOOK_ROUTES` e
      `tests/security/test_gateway_route_permissions.py`.
- [x] T021 Ajustar as fixtures de intake que descrevem fonte removida para as
      três mantidas, sem inventar carga nova — a fixture de uma fonte removida
      some, e a de uma mantida fica como está.
      **FEITO**: `fixtures/scenarios/{empty,first-run,populated}/ingress-sources.json`
      (fontes removidas retiradas), `fixtures/scenarios/{empty,first-run,populated}/transit-ingress.json`
      (achado além da lista explícita — é o que a tela de intake realmente
      renderiza; 7→3 fontes nos três) e `fixtures/scenarios/{empty,first-run,populated}/integrations.json`
      (catálogo simulado filtrado às 15 mantidas + 3 entradas fictícias
      pré-existentes; texto dos gaps atualizado para não citar vendor
      removido). `fixtures/contract/openapi.json` e `console/src/api/schema.ts`
      regenerados em consequência (rotas de webhook 7→3).

## Phase 4: Gates, contagens e documentação gerada

- [x] T022 Regenerar a documentação de integrações e conferir que a checagem de
      desvio passa. Não editar arquivo gerado à mão.
- [x] T023 Três categorias perdem todos os seus vendors — integração contínua,
      plataforma de dados e ticketing. Fazer o gerador deixar de emitir a página
      de uma categoria vazia e deixar de listá-la no índice, com teste antes
      confirmado vermelho. Reconferir depois quais categorias de fato esvaziaram
      na árvore, em vez de confiar nesta lista.
- [x] T024 [P] Corrigir toda afirmação de total de integrações em arquivo
      committed para 15, ou torná-la derivada do catálogo. Os pontos conhecidos:
      o guia do diretório de integrações, o documento de visão, a tabela de onda
      e a linha de índice do registro de decisão no roadmap, o comentário de
      rota do console e o número exibido na galeria do console. Varrer para
      confirmar que não sobrou outro.
- [x] T025 [P] Conferir que a lista de vendors não cobertos continua com o
      significado que tem e **não** recebeu nenhum dos 70 removidos.
- [x] T026 [P] Conferir que a isenção de paginação da categoria provedor de
      modelo continua intacta, continua exercitada pelo provedor mantido e não
      foi alargada. Nenhuma outra categoria ganha isenção neste corte.
- [x] T027 Medir e registrar o efeito sobre a suíte de cenários sintéticos:
      quantos cenários existiam, quantos saíram, quantos restam, e o resultado
      da suíte antes e depois. "Sem efeito" seria uma resposta aceitável; "não
      medido" não é.
- [x] T028 Validar a consistência do roadmap committed: a lista de escopo
      embarcado nomeia exatamente as 15, e a lista de escopo diferido cobre os
      70 removidos. Corrigir apenas o que essas duas checagens acusarem — o
      roadmap não é reescrito por esta feature.

## Phase 5: Registro de decisão e emenda da constituição

- [x] T029 Escrever o registro de decisão arquitetural novo, com o próximo
      número livre da série. Ele declara: paridade por integração embarcada,
      inalterada em forma — sete artefatos; amplitude estagiada por ambiente
      capaz de validar a integração ponta a ponta (credencial armazenada,
      conexão verificada, ao menos uma leitura real exercitada); driver,
      alternativas consideradas e consequências, conforme a regra de emenda.
      **O documento é committed e precisa se sustentar sozinho**: enuncia a
      regra em substância, sem exigir do leitor nenhum documento que não veio no
      clone. O único ponteiro externo permitido é a seção de escopo de
      integrações do roadmap committed. Não afirma um total de integrações.
- [x] T030 Marcar o registro de decisão anterior sobre paridade como superseded,
      com data e ponteiro para o sucessor, preservando o corpo — um registro
      superseded continua explicando por que a decisão foi tomada então.
- [x] T031 Atualizar o índice de registros de decisão com o registro novo e com
      o novo estado do anterior, e a tabela de rastreabilidade do roadmap na
      linha correspondente.
- [x] T032 Emendar a cláusula de paridade do artigo de capacidades da
      constituição local: paridade por integração embarcada, com a condição de
      ambiente validável, sem citar um total. Subir a versão de 2.1.0 para
      2.2.0 e registrar a emenda no sumário do cabeçalho, incluindo repontar
      para o registro de decisão sucessor a referência que hoje aponta para o
      superseded. **A constituição é local-only e não entra em nenhum commit.**

## Phase 6: Console sem órfãos

- [x] T033 Varrer rotas, fixtures e testes do console por nome de vendor
      removido e corrigir cada ocorrência. Uma rota de detalhe de vendor
      removido deixa de existir.
- [x] T034 Atualizar o registro de telas visuais: a entrada que hoje aponta para
      a rota de detalhe de um vendor removido é repontada para um vendor
      mantido, ou removida se a tela deixar de existir. Se a entrada for
      repontada e a tela for registrada, a baseline correspondente é capturada
      **deliberadamente**, pelo alvo de aceitação visual — nunca por placeholder
      que o gate fabrique. Se a entrada for removida, a baseline órfã é apagada
      no mesmo passo.
- [x] T035 Rodar as suítes de console existentes — unitária, de comportamento,
      de primeiro dia e visual — e confirmar verde. Nenhuma delas é reescrita
      por esta feature; elas são a regressão do que já passava.

## Phase 7: Fechamento

- [x] T036 Rodar a verificação completa do repositório e comparar, alvo por
      alvo, com o log de T001. Todo alvo que passava continua passando; a
      verificação de integrações reporta 15 em paridade total. Qualquer
      diferença é explicada ou corrigida, nunca omitida.
- [x] T037 Confirmar que uma varredura por cada um dos 70 nomes removidos em
      arquivo committed retorna ocorrências apenas no roadmap committed e no
      registro de decisão novo. T008 passa a verde.
- [x] T038 Atualizar o `controle.md` desta feature com o que o código prova:
      número real de cada rodada, o antes e o depois das quatro contagens, o
      efeito medido sobre a suíte de cenários, o vermelho capturado de cada
      gate na Fase 1, e toda ressalva de honestidade — inclusive qualquer teste
      cujo vermelho não foi visto antes da implementação, e por quê.

## Dependencies

- T001 → T002 → toda a Fase 1. A linha de base precede qualquer escrita.
- T009 é portão: nenhuma remoção começa antes do vermelho confirmado.
- T010..T017 são paralelas entre si; T018 depende de todas as oito.
- T019 depende de T018 (só se sabe qual dependência ficou órfã depois da
  remoção).
- Fase 3 é independente da Fase 2 e pode correr em paralelo com ela; T020
  depende de T005, T006 e T007.
- T022 depende da Fase 2 inteira; T023 depende de T022.
- T024, T025 e T026 são paralelas entre si e dependem de T018.
- T027 depende de T018 (a contagem de depois) e de T002 (a de antes).
- Fase 5 é independente das Fases 2 a 4 e pode correr a qualquer momento depois
  de T009 — exceto T031, que toca o roadmap e coordena com T028.
- Fase 6 depende de T018.
- T036 depende de tudo; T037 depende de T036; T038 é a última.
