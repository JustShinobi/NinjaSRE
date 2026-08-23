# Tasks: O incidente fecha o laço

**Input**: Design documents from `specs_v7/080-incidente-fecha-o-laco/`

**Prerequisites**: plan.md, spec.md; e a onda inteira mergeada e verificada —
000 (regras e modo de aceitação contra staging), 001 (recorder composto),
010 (leitura do relato), 020 (identidade endereçável), 030 (uma fonte por fato),
040 (decisão composta), 050 (primeiro administrador), 060 (o catálogo ensina),
070 (confiança de certificado).

**Natureza**: integração e demonstração. **Nenhuma tarefa abaixo altera arquivo
de produto.** Se uma tarefa levar você a `gateway/`, `platform/`, `core/`,
`capabilities/`, `integrations/`, `config/` ou `console/`, pare: o que você
encontrou é reparo de outra feature (Fase 11), não trabalho desta.

**O análogo do test-first aqui**: o gabarito antes da execução. Os roteiros e a
tabela de evidência esperada aterrissam **antes** da demo, e o coletor roda a
seco contra o staging pré-demo — devolvendo os valores de partida — como o
vermelho confirmado e registrado (Fase 5). Uma consulta que já devolvesse verde
antes da demo não estaria medindo o laço.

**Comandos de infraestrutura**: rodados por `ssh root@192.168.68.159 '<comando>'`
a partir desta máquina, nunca em sessão interativa. Leitura é livre; escrita
(parar um contêiner, religar) só nas tarefas que a nomeiam, e o passo destrutivo
é digitado por uma pessoa.

**Viewport de screenshot**: 1920×1080, full-page.

**Segredos**: nenhum roteiro, arquivo de evidência ou screenshot pode conter
token, chave, senha ou credencial. A tarefa T072 existe para conferir isso antes
de a evidência ser considerada entregue.

---

## Fase 1: Pré-voo — o staging é a ponta da onda (O-A)

**Objetivo**: garantir que a demo mede a onda, e não uma versão anterior dela.

- [ ] T001 Confirmar que todas as features da onda estão mergeadas na árvore da
      onda e que cada uma tem veredito PASS do seu verifier. Registrar o commit
      da árvore em `evidence/EVIDENCIA.md` (seção "A versão que a demo mediu").
      Se alguma feature não estiver PASS, a demo não começa — reportar ao
      orquestrador e parar.
- [ ] T002 Rodar `make verify` na árvore da onda **antes** de publicar, e
      registrar exit code, número de testes e duração. Um vermelho aqui é
      bloqueio: publicar uma árvore que não passa transforma qualquer falha da
      demo em ambiguidade.
- [ ] T003 Publicar em staging: `make deploy-stg` (sem `COMPONENTS=`, porque a
      onda mudou app e console). Registrar os digests que o script imprimiu.
- [ ] T004 Aguardar o Argo reconciliar:
      `ssh root@192.168.68.159 'kubectl get application stg-ninjasre -n argocd'`
      até `Synced + Healthy`. Registrar a saída com o instante.
- [ ] T005 Confirmar, **separadamente**, que o serviço responde — `Synced +
      Healthy` diz que o cluster reflete o Git, não que alguém atende. Conferir
      os pods (`kubectl get pods -n k3s-stg-ninjasre`), o `/health/ready` do app
      (`kubectl exec -n k3s-stg-ninjasre deploy/app -- curl -s
      http://localhost:8420/health/ready | jq .`) e a URL pública
      `https://stg-ninjasre.lan.kyo.ninja` respondendo. Registrar as três saídas.
- [ ] T006 Registrar em `evidence/EVIDENCIA.md` o digest publicado e o estado do
      Argo no instante da demo — a evidência precisa apontar uma versão.
      **Checkpoint**: sem T004+T005 verdes a demo não começa. Reprovar aqui é
      **ambiente**: reexecutável, não reprova a onda.

---

## Fase 2: Aptidão do ambiente (O-B) — conferir, nunca alterar

**Objetivo**: descobrir agora, com calma, tudo que faria a janela ser desperdiçada.
Nenhuma tarefa desta fase altera infraestrutura.

- [ ] T007 [P] Descobrir e registrar o identificador da organização do
      deployment de staging no banco — toda consulta de evidência é escopada por
      ele. `SELECT org_id, name FROM organisations;` no `ninjasre-stg-db`.
      Guardar como o parâmetro `:org` dos roteiros.
- [ ] T008 [P] Conferir que o provider de modelo está **Verified** no console
      (`/settings/models-providers`) e que a resolução da chave é a do vault.
      Screenshot em `evidence/telas/`. Se estiver Stored, é achado da 030.
- [ ] T009 [P] Conferir que o Proxmox está conectado (`/integrations`) com a
      confiança de certificado declarada pela 070, e que `/resources` lista
      recursos reais. Screenshot das duas telas. `SELECT count(*) FROM
      estate_resources WHERE org_id = :org;` — o valor de partida da onda é zero
      recursos na tela.
- [ ] T010 Conferir que o token do Proxmox guardado por este deployment tem o
      privilégio de gerência de energia de convidados (`VM.PowerMgmt` no caminho
      `/vms`). **Sem alterar o token.** Se ele for de leitura, registrar como
      **decisão pendente do operador** — conceder escrita é decisão de fronteira
      de segurança dele — e marcar a estação E9 como possivelmente não exercível.
- [ ] T011 Conferir com o operador, e registrar a resposta: a vítima candidata
      `redis` (CT122, pve01, `10.20.20.52`) continua fora de uso e autorizada?
      Se não, qual alvo de scrape ou sonda real pode ficar fora por dez minutos?
      **Nenhum passo destrutivo acontece sem esta resposta.**
- [ ] T012 Conferir o estado inicial da vítima:
      `ssh root@192.168.68.159 'ssh pve01 "pct status <VMID>"'` (ou o caminho
      equivalente ao nó). Precisa dizer **running**. Uma vítima já parada não
      pode ser parada pelo passo destrutivo, e um alerta já disparando não foi
      disparado por este teste — seguir assim é colher um incidente verdadeiro e
      concluir dele uma coisa falsa.
- [ ] T013 [P] Conferir que a regra de alerta que cobre a vítima existe e está
      ativa no Prometheus, e que a rota do Alertmanager casa a severidade que ela
      emite. Registrar a expressão da regra e o `for`. Sem isso, a estação E1
      falharia por ausência de regra e alguém leria isso como defeito do produto.
- [ ] T014 [P] Conferir que o webhook aceita entrega autenticada e recusa sem
      credencial — a sonda de recusa, não a de aceitação, porque ela não cria
      dado. Registrar o código de resposta.
- [ ] T015 [P] Listar os alertas que **já estão** disparando agora no
      Alertmanager. Escolher um deles como matéria-prima do laço de leitura, e
      registrar qual e por quê.
- [ ] T016 Registrar em `evidence/EVIDENCIA.md` a tabela de aptidão: cada item
      das tarefas T007–T015 com conferido/não conferido e a saída.
      **Checkpoint**: um item não conferido não bloqueia por si — bloqueia a
      estação que depende dele, e isso fica escrito.

---

## Fase 3: Os roteiros e o gabarito, antes de qualquer execução

**Objetivo**: escrever o que se espera ver **antes** de ver. Um roteiro escrito
depois da execução é um relatório disfarçado.

- [ ] T017 Escrever `runbooks/laco-de-leitura.md`: pré-condições, o alerta já
      ativo escolhido em T015, os passos de E1 a E7, as URLs exatas do staging, o
      que se espera ver em cada estação, a evidência a coletar, e a afirmação de
      que ele não faz escrita nenhuma e não precisa de janela.
- [ ] T018 Escrever `runbooks/laco-inteiro.md`: o que este roteiro **não é** (o
      passo destrutivo é digitado por uma pessoa, uma vítima por vez, uma janela
      por vez); a vítima com a evidência de ser descartável **e** observada; o
      estado inicial a conferir; o passo destrutivo; as estações E1 a E10; a
      reversão manual; e a regra de que a reversão vale a qualquer instante e não
      espera pelo produto.
- [ ] T019 Escrever, dentro dos dois roteiros, a **tabela de estações**: nome, o
      que se espera ver, onde se olha, evidência exigida.
- [ ] T020 Escrever, para cada estação, a **classificação de desfechos**: quais
      são de ambiente (reexecutável, nomeando o que reconferir e por onde
      reentrar) e quais são de produto (bloqueiam, com a feature dona nomeada).
      A regra que separa: se a mesma execução amanhã, sem mudar código, tem
      chance razoável de passar, é ambiente; se vai falhar igual até alguém mudar
      código, é produto.
- [ ] T021 [P] Escrever no roteiro do laço inteiro o bloco de reversão manual com
      o comando exato, **antes** do bloco do passo destrutivo — a reversão é
      escrita antes de a mudança acontecer, não depois.
- [ ] T022 [P] Escrever no roteiro do laço inteiro a estação E8 deixando
      explícito que a aprovação é dada por uma pessoa, na interface, e que
      aprovar por chamada de API invalida a demo.
- [ ] T023 [P] Escrever no roteiro do laço inteiro a instrução de **não aprovar
      antes de conferir E4 a E7**: a aprovação é o último passo, e aprová-la
      antes de olhar desperdiça a única execução que responde "o registro ficou
      completo?".
- [ ] T024 [P] Escrever a estação de rejeição: em ocorrência **diferente** da que
      foi aprovada, rejeitar sem motivo (deve ser recusado) e depois com motivo
      (deve ser registrado).
- [ ] T025 Escrever o esqueleto de `evidence/EVIDENCIA.md`: uma seção por
      estação, com os campos expectativa / evidência / consulta / saída /
      veredito / instante, **em branco**. O esqueleto vazio é o gabarito; ele
      aterrissa antes da demo.
- [ ] T026 Revisar os dois roteiros à procura de segredo transcrito. Token,
      chave e credencial são referenciados por onde obtê-los, nunca copiados.

---

## Fase 4: O coletor de evidência

**Objetivo**: as consultas viram ferramenta, com saída literal, para que ninguém
digite um `SELECT` de memória às onze da noite e anexe o resultado errado.

- [ ] T027 Criar `tools/demo_evidence/` com as consultas nomeadas por estação,
      todas `SELECT`, todas escopadas por `:org`, parametrizadas por `run_id`,
      `incident_id`, `approval_id` e `resource_id`. Nenhuma escrita, em nenhuma
      hipótese.
- [ ] T028 As consultas, no mínimo — cada uma com o valor de partida da onda ao
      lado, porque o contraste é a evidência:
      - E4 gravação: `SELECT count(*) FROM run_turns WHERE org_id=:org AND
        run_id=:run;` idem `tool_calls`, `evidence`, `trace_events` (partida:
        `0`, `0`, `0`, `73` no total da instância).
      - E4 custo: `SELECT index, started_at, finished_at, usage FROM run_turns
        WHERE org_id=:org AND run_id=:run ORDER BY index;`
      - E4 o que cada chamada devolveu: `SELECT tool_name, status, started_at,
        finished_at, error FROM tool_calls WHERE org_id=:org AND run_id=:run
        ORDER BY recorded_seq;`
      - E5 sentença separada do documento: o campo de sentença do run mais
        `SELECT left(summary, 120) FROM agent_runs WHERE org_id=:org AND
        run_id=:run;` (partida: todo `summary` recente começa com `###`).
      - E7 proposta: `SELECT approval_id, action, side_effect_level, state,
        requested_at, expires_at FROM approvals WHERE org_id=:org AND
        run_id=:run;` (partida: nenhuma linha, para nenhum run).
      - E7 reversão registrada: `SELECT plan_id, created_at, steps FROM
        rollback_plans WHERE org_id=:org AND approval_id=:approval;`
      - E8 decisão humana: `SELECT state, decided_by, decided_at, reason FROM
        approvals WHERE org_id=:org AND approval_id=:approval;`
      - E8 auditoria: os eventos de auditoria da aprovação e da rejeição, com
        autor, ação, assunto e resultado.
      - E9 desfecho: `SELECT capability, resource_id, state, due_at FROM
        remediation_outcomes WHERE org_id=:org AND resource_id=:resource ORDER BY
        due_at DESC;`
      - E9 episódio: `SELECT episode_id, title, outcome, occurred_at, components
        FROM episodes WHERE org_id=:org AND run_id=:run;`
      - E10 timeline: `SELECT kind, at, actor, cause, left(detail,160) FROM
        incident_timeline WHERE org_id=:org AND incident_id=:incident ORDER BY
        at;`
      - E10 incidente: `SELECT title, state, severity, subjects, run_ids,
        actions, closed_at, close_reason FROM incidents WHERE org_id=:org AND
        incident_id=:incident;`
      - E3 estate: `SELECT count(*) FROM estate_resources WHERE org_id=:org;` e a
        linha do recurso que é sujeito do incidente (partida: estate vazio).
- [ ] T029 O coletor escreve, por estação, um arquivo em `evidence/consultas/`
      com **a consulta e a saída literal**, nunca uma afirmação sobre a saída.
- [ ] T030 O coletor recusa executar qualquer instrução que não seja `SELECT`, e
      falha alto se receber uma. É o guarda que impede um coletor de evidência de
      virar um caminho de escrita ao banco de staging.
- [ ] T031 Teste de unidade do coletor em `tests/unit/tools/`, confirmado
      vermelho antes: que ele escopa por organização, que ele recusa não-`SELECT`,
      que ele grava saída literal e não formatada, e que o nome do arquivo
      identifica a estação. Um coletor que escreve o arquivo errado corrompe a
      única prova que a onda tem.
- [ ] T032 [P] O coletor nunca imprime nem grava valor de credencial; se uma
      coluna puder conter segredo, ela não entra em consulta nenhuma.
- [ ] T033 Registrar o comando exato de invocação do coletor no cabeçalho dos dois
      roteiros, para que a coleta seja reexecutável por outra pessoa.

---

## Fase 5: O vermelho — o gabarito roda a seco antes da demo (O-C)

- [ ] T034 Rodar o coletor contra o staging **antes** da demo, com os parâmetros
      de um run pré-onda. Registrar a saída em
      `evidence/consultas/000-partida.txt`.
- [ ] T035 Conferir que as consultas devolvem os valores de partida esperados. Se
      alguma já devolver o valor "verde" antes da demo, ela está medindo outra
      coisa — corrigir a consulta antes de seguir. **Este é o vermelho
      confirmado desta feature; registrá-lo é obrigatório.**
- [ ] T036 Registrar o vermelho em `evidence/EVIDENCIA.md`, seção "O que o
      staging media antes da demo".
      **Checkpoint**: sem T035 registrado, a evidência posterior não tem
      contraste e o gabarito não foi provado.

---

## Fase 6: O laço de leitura, executado (E1 a E7, sem escrita)

- [ ] T037 Executar `runbooks/laco-de-leitura.md` do começo ao fim, contra
      `https://stg-ninjasre.lan.kyo.ninja`, com o alerta já ativo escolhido em
      T015.
- [ ] T038 [P] E2/E3 — screenshot full-page da lista de incidentes e do detalhe do
      incidente escolhido. Conferir: título legível, zero painéis "não foi
      possível preencher", nenhuma URL com `%3A`/`%40`/`%2B`, sujeito resolvido.
- [ ] T039 [P] E4 — screenshot full-page do detalhe do run: transcript com as
      chamadas reais e o que cada uma devolveu, custo por turno, "o que esta
      investigação tocou" preenchido, e nenhum controle de run vivo num run
      terminado.
- [ ] T040 [P] E5 — screenshot full-page do relato: título é uma sentença, report
      renderizado, nenhum caractere de sintaxe markdown visível como texto.
- [ ] T041 E6 — conferir que o conjunto de ferramentas oferecido condiz com as
      integrações que este deployment conectou, e que nenhuma capacidade de
      remediação foi oferecida só para devolver recusa. Evidência: o transcript e
      a tela de ferramentas do agente.
- [ ] T042 [P] E7 — screenshot full-page de `/decisions` e do painel de ação
      proposta no incidente: a proposta, o plano de reversão, o alcance, a
      postura, e o chip aguardando decisão. **Nada é aprovado aqui.**
- [ ] T043 Rodar o coletor para o run deste laço e anexar as saídas por estação.
- [ ] T044 Executar o laço de leitura **uma segunda vez** e conferir que produz a
      mesma evidência — ou nomear, na saída, qual passo variou e por quê. É o que
      prova a repetibilidade que o laço inteiro não pode provar.

---

## Fase 7: A janela — o laço inteiro (O-D)

**Pré-condições desta fase**: T012 (vítima `running`), T011 (vítima confirmada
pelo operador), T016 (aptidão registrada), T036 (vermelho registrado), operador
presente e a par.

- [ ] T045 Abrir a janela com o operador. Registrar o instante de abertura e a
      confirmação verbal da vítima. Reconferir `pct status` — o estado pode ter
      mudado desde T012.
- [ ] T046 **O passo destrutivo**, digitado por uma pessoa, uma vez:
      `ssh pve01 'pct stop <VMID>'`. Anotar a hora; ela é a referência de tudo o
      que vem depois. **Não emitir alerta nenhum** — o alerta tem que disparar
      por conta própria, e é isso que separa este roteiro do laço de leitura.
- [ ] T047 E1 — o alerta dispara sozinho. Evidência: o alerta ativo no
      Alertmanager, com o instante, sem ninguém o ter emitido. Contar com o `for`
      da regra mais o `group_wait` da rota; silêncio antes disso é o esperado,
      não sintoma. **Desfecho de ambiente**: não disparou na janela ⇒ reconferir
      a regra e o alvo, reexecutar.
- [ ] T048 E2 — a entrega chega autenticada. Evidência: a entrega registrada, com
      origem, horário e resultado; screenshot da tela de intake.
      **Desfecho de ambiente**: alerta disparou e entrega não chegou por não
      resolver o nome do deployment ⇒ é a tarefa operacional de resolução de
      nomes, não o webhook.
- [ ] T049 E3 — o incidente abre com título legível e sujeito resolvido.
      Screenshot full-page do detalhe. Registrar o identificador do incidente.
- [ ] T050 E4 — a investigação grava. Screenshot full-page do run **depois de um
      reload** (o ponto é ler do store, não do processo). Rodar o coletor para
      este run e anexar as contagens e o custo por turno.
- [ ] T051 E5 — o relato é legível. Screenshot full-page; anexar a consulta que
      mostra a sentença separada do documento.
- [ ] T052 E6 — as ferramentas condizem com o que está conectado. Evidência: o
      transcript, mais a lista de ferramentas do agente.
- [ ] T053 E7 — a proposta aparece com plano de reversão, aguardando decisão.
      Screenshot de `/decisions` e do painel no incidente; anexar as consultas de
      `approvals` e `rollback_plans`.
      **Desfecho aceitável e declarado**: investigação sem evidência suficiente
      não propõe nada — e isso é correto. Neste caso o run vira cenário de
      leitura, e o laço inteiro reexecuta com outra ocorrência.
- [ ] T054 **Conferir E4 a E7 antes de aprovar.** Só depois seguir para T055.
- [ ] T055 E8 — o operador aprova, pela interface, olhando. Registrar o instante.
      Anexar a consulta que mostra estado, decisor, instante e motivo, e o evento
      de auditoria correspondente. Conferir que decisão, decisor e instante foram
      gravados **antes** de qualquer efeito, e que o plano de reversão já estava
      registrado.
- [ ] T056 E9 — a execução acontece pelo gate. Evidência: o convidado voltando a
      rodar (`pct status` dizendo `running`), o desfecho gravado em
      `remediation_outcomes`, o episódio gravado em `episodes`, e a entrada de
      ação na timeline do incidente.
      **Desfecho legítimo e registrável**: falha no vendor por privilégio, quorum
      ou lock ⇒ grava-se a falha com a razão nomeada, e o plano de reversão não
      roda porque nada mudou. Falha nomeada fecha o laço com desfecho negativo; o
      que não fecha o laço é falha silenciosa.
- [ ] T057 E10 — o incidente reflete o desfecho. Screenshot full-page do detalhe
      do incidente depois da execução; anexar as consultas de `incident_timeline`
      e `incidents`.
- [ ] T058 Conferir que o alerta resolveu e que a resolução fechou o incidente que
      a abertura criou.
- [ ] T059 **Reversão**: confirmar que o convidado está `running`. Se a execução
      não o religou, religar à mão imediatamente — a validação não deixa o serviço
      refém dela.
- [ ] T060 Fechar a janela. Registrar o instante e o resumo do que aconteceu, em
      `evidence/EVIDENCIA.md`.

---

## Fase 8: A rejeição

- [ ] T061 Em ocorrência **diferente** da aprovada — outro alerta real com
      proposta, ou uma segunda janela combinada com o operador —, rejeitar a
      proposta **sem motivo**. Conferir que é recusado. Screenshot.
- [ ] T062 Rejeitar a mesma proposta **com motivo**. Conferir que é registrado.
      Screenshot; anexar a consulta de `approvals` mostrando estado e motivo.
- [ ] T063 Conferir que as duas decisões — a aprovação de T055 e a rejeição de
      T062 — aparecem na auditoria com autor, ação, assunto e resultado. Anexar a
      saída.

---

## Fase 9: As tarefas operacionais, verificadas e não executadas (O-E)

**Nenhuma tarefa desta fase altera infraestrutura.** Cada uma confere a evidência
e registra o estado real.

- [ ] T064 [P] Resolução de nomes: conferir, de dentro de **cada** contêiner de
      monitoração, que um nome do domínio do deployment resolve. Anexar a saída
      por contêiner. Estado real registrado, feito ou não.
- [ ] T065 [P] Sincronização de segredos: conferir se os recursos de segredo
      gerenciado estão sincronizando, ou registrar a decisão explícita de
      conviver com o segredo escrito à mão. Anexar a saída.
- [ ] T066 [P] Chave do gateway de modelos: conferir se o provider correspondente
      aparece **Verified** no console. Screenshot. Se não, registrar o estado
      real.
- [ ] T067 Para cada uma das três que **não** estiver feita, escrever a entrada
      correspondente do backlog novo com o estado real e o que falta — a redação
      final entra em T086. Nenhuma some.
- [ ] T068 Registrar, por estação da demo, quais dependiam de uma tarefa
      operacional não concluída, e marcá-las **não exercidas** em vez de
      aprovadas por omissão.

---

## Fase 10: A evidência consolidada

- [ ] T069 Preencher `evidence/EVIDENCIA.md` estação por estação: expectativa,
      evidência, consulta, saída literal, veredito, instante.
- [ ] T070 Conferir que **toda** estação que é tela tem screenshot full-page em
      1920×1080, nomeada pela estação, em `evidence/telas/`.
- [ ] T071 Conferir que **toda** estação que alega gravação tem consulta e saída
      literal em `evidence/consultas/`, com o valor de partida ao lado.
- [ ] T072 Varrer a evidência inteira — texto e screenshots — à procura de
      credencial, token, chave ou senha. Uma screenshot com um valor de token é
      um vazamento tão real quanto um commit com ele. Sem esta varredura a
      evidência não é entregue.
- [ ] T073 Rodar, contra staging, os acceptance das features donas que são
      seguros em ambiente compartilhado, mais a suíte transversal. Registrar
      passados, falhados e pulados. Uma falha aqui é achado da feature dona
      (Fase 11), não desta.
- [ ] T074 Escrever, no topo de `evidence/EVIDENCIA.md`, o veredito da demo em
      uma frase, seguido da lista de estações com veredito individual e das
      estações não exercidas com a razão.

---

## Fase 11: Os achados — reparo da dona, ou backlog novo

- [ ] T075 Listar todo achado da demo em `evidence/EVIDENCIA.md`, seção
      "Achados": descrição, estação onde apareceu, classificação
      (ambiente / produto), e feature dona ou "sem dono".
- [ ] T076 Para cada achado de produto com dona: entregar ao orquestrador com a
      estação e a evidência. **Não consertar aqui.** A decisão de gastar um ciclo
      de reparo é dele.
- [ ] T077 Para cada achado sem dona na onda: redigir a entrada do backlog novo,
      na forma que o arquivo já pratica — o que acontece hoje, por que não é
      trivial, e o desfecho pelo qual seria julgado.
- [ ] T078 Depois de qualquer reparo aceito, **reexecutar a estação afetada e
      substituir a evidência**. Nunca acumular as duas capturas como se as duas
      fossem verdadeiras.

---

## Fase 12: O confronto da onda ganha a coluna

- [ ] T079 Criar ou completar `specs_v7/CONFRONTO.md` com uma seção por feature
      da onda: o que entregou, o gate, o veredito do verifier, os commits, e o
      que ficou nomeado como dívida.
- [ ] T080 Adicionar a coluna fixa **"quem constrói isso em produção?"** à tabela
      de mecanismos, respondida com `file:line` da composition root de serving.
- [ ] T081 Preencher a coluna, no mínimo, para: o recorder de investigação (001),
      o gate de remediação e o gate de autonomia (040), o resolvedor de
      integrações do time e o caminho canônico de pipeline (040), e a confiança
      de certificado até o egress do proxy (070). Obter cada `file:line` lendo o
      código — o índice de símbolos do repositório é o caminho barato.
- [ ] T082 Para todo mecanismo cuja única construção seja teste, contract test ou
      plano de dados simulado: declarar **dormant** com a referência do que o
      ligaria. Uma célula apontando um teste é pior que uma célula vazia, porque
      parece resposta.
- [ ] T083 Fechar o confronto citando a demo como evidência, com o caminho de
      `evidence/EVIDENCIA.md` e o veredito de uma frase.

---

## Fase 13: O backlog reescrito

**`backlog.md` é committed.** Quem clona o repositório não tem a onda, nem os
briefings, nem esta spec, nem número de feature nenhum. A redação obedece a isso.

- [ ] T084 Montar a tabela de destino, no confronto (não no backlog), de **todos**
      os itens do backlog anterior: fechado com a evidência nomeada, ou presente
      no backlog novo com o estado real. Zero itens sem destino.
      Os itens a percorrer são os onze do arquivo atual: primeiro administrador;
      guias de credencial no catálogo; as quatro costuras entre configurado e em
      execução; vendor com certificado self-signed; o roteador de alertas sem
      caminho até o deployment; as duas costuras que o verify profundo abriu;
      dois service accounts; investigação que deixa o detalhe vazio; a metade que
      age não composta; operador de segredos sem autenticar; gateway de modelos
      sem chave.
- [ ] T085 Reescrever `backlog.md` contendo **apenas**: o que esta onda descobriu
      de novo, mais o que ela não fechou (inclusive as tarefas operacionais
      pendentes de T067, com o estado real).
- [ ] T086 Conferir a redação do arquivo novo contra as regras do que é committed:
      sem caminho de planejamento, sem número de feature, sem identificador de
      requisito, sem artigo de constituição, sem nome de projeto de origem.
      A substância vai no arquivo; a referência fica nos documentos da onda.
- [ ] T087 Conferir que a forma do arquivo foi preservada: problema descrito, o
      que acontece hoje, por que não é trivial quando não é, e o desfecho pelo
      qual seria julgado. É o melhor documento do repositório e a reescrita não o
      empobrece.
- [ ] T088 Conferir que nenhum item removido saiu sem evidência nomeada no
      confronto, e que nenhuma tarefa operacional pendente sumiu.

---

## Fase 14: Fechamento

- [ ] T089 `make verify` completo na árvore final. Registrar exit code, número de
      testes, pulados e duração.
- [ ] T090 Confirmar que esta feature não alterou arquivo de produto: o diff dela
      contém apenas `tools/demo_evidence/`, `tests/unit/tools/`, `backlog.md`,
      `specs_v7/CONFRONTO.md` e o próprio diretório da feature.
- [ ] T091 Escrever `controle.md` desta feature afirmando **apenas** o que a
      evidência prova, com o veredito por estação, as estações não exercidas com
      a razão, os achados e seus destinos, e as decisões que ficaram com o
      operador.
- [ ] T092 Reportar ao orquestrador: veredito da demo em uma frase, caminho da
      evidência, lista de achados com dona, estado das três tarefas operacionais,
      e as decisões do operador que ficaram pendentes.

---

## Dependências entre fases

```
Fase 1 (pré-voo) → Fase 2 (aptidão) → Fase 3 (roteiros) → Fase 4 (coletor)
                                                              ↓
                                                    Fase 5 (o vermelho)
                                                              ↓
                                          Fase 6 (laço de leitura)
                                                              ↓
                                          Fase 7 (a janela) → Fase 8 (rejeição)
                                                              ↓
Fase 9 (ops, paralela a partir da Fase 2) ──────────→ Fase 10 (evidência)
                                                              ↓
                                          Fase 11 (achados) → Fase 12 (confronto)
                                                              ↓
                                          Fase 13 (backlog) → Fase 14 (fechamento)
```

A Fase 9 não depende da demo e pode rodar em paralelo a partir do fim da Fase 2.
A Fase 3 pode começar durante a Fase 2, mas **não termina** antes de T011 e T015,
que fixam a vítima e o alerta.

## O que reprova esta feature

- O laço não fecha, e a razão é de produto.
- A demo rodou e a evidência não existe, ou existe sem saída literal.
- A aprovação foi dada por outro caminho que não uma pessoa na interface.
- Uma estação foi marcada aprovada sem ter sido exercida.
- Um item do backlog anterior sumiu sem evidência de fechamento.
- Uma célula da coluna nova do confronto aponta um teste.
- Esta feature consertou funcionalidade de produto.
- Um segredo apareceu num roteiro, numa consulta ou numa screenshot.
