# Feature Specification: O incidente fecha o laço

**Feature Branch**: `feat/v7-080-incidente-fecha-o-laco`

**Created**: 2026-08-23

**Status**: Draft

**Input**: User description: "A onda termina com um humano assistindo o laço fechar
no staging real — alerta do Alertmanager → webhook autenticado → investigação com
transcript gravado e legível → root cause com headline e report renderizado →
ferramentas condizentes com as integrações configuradas → proposta com rollback →
aprovação humana em propose-only → execução pelo gate com outcome, timeline e
episódio gravados → incidente refletindo o desfecho. A demo é um artefato
verificável, o backlog é reescrito, e o confronto da onda responde quem constrói
cada mecanismo em produção."

**Natureza desta feature**: integração e demonstração. O que ela **constrói** é
pouco e é cola: um roteiro executável, um coletor de evidência, e três documentos
(evidência consolidada, confronto da onda, backlog reescrito). O que ela
**prova** é a onda inteira. Ela roda sozinha, no último slot, com tudo mergeado.

## Pré-condições verificadas (2026-08-23 — não re-derivar)

Cada item abaixo foi confirmado antes desta spec existir. A spec os cita como
fatos; a implementação os **reconfere no instante em que os usa**, e não os
descobre de novo.

1. Staging roda em k3s no namespace `k3s-stg-ninjasre`, publicado em
   `https://stg-ninjasre.lan.kyo.ninja`, ingress `/ → web` (console Next) e
   `/webhooks → app` (gateway). Banco `ninjasre-stg-db` em `10.20.20.54`.
2. O Alertmanager da stack de monitoração entrega alertas reais neste
   deployment. Regras vistas disparando: `RestoreDrillStale`, `CronJobStale`,
   `InstanceDown`, `BlackboxProbeFailed`, `ProxmoxCriticalLogDetected`.
3. O provider Gemini está **Verified** via vault/proxy; 37 investigações
   completaram contra alertas reais antes desta onda começar.
4. O publish de staging é `make deploy-stg` (`COMPONENTS=` estreita), que
   escreve digests no repositório GitOps que o Argo reconcilia. `Synced +
   Healthy` no Argo significa que o cluster reflete o Git — não que o serviço
   responde. As duas coisas se verificam separadamente.
5. **Não existe regra que dispare quando um LXC qualquer para.** Existem
   `InstanceDown` (`up{job!="pve-exporter"} == 0`) sobre alvos de scrape e
   `BlackboxProbeFailed` sobre uma lista fixa de sondas. Uma vítima precisa ser
   ao mesmo tempo **descartável** e **observada**; a maioria dos contêineres do
   homelab é só a primeira coisa.
6. A vítima que satisfaz as duas condições, herdada da validação anterior e
   autorizada na época pelo operador, é o contêiner **`redis` (CT122, pve01,
   `10.20.20.52`)** — alvo de scrape `10.20.20.52:9121` do job `redis-exporter`,
   rotulado `service: redis`, `node: pve01`, `criticality: high`, declarado fora
   de uso. Parar a CT122 casa `InstanceDown` e `RedisExporterDown`, ambas com
   `for: 2m` e `severity: critical`; `RedisInstanceDown` tende a **não** disparar,
   porque a série `redis_up` some em vez de zerar.
7. `streamlink-webui` (CT139) e `bazarr` (CT103) — as vítimas do plano da
   validação anterior — **não servem**: não são alvo de scrape nem de sonda, e
   pará-las não dispara nada. A CT139 já estava parada em 2026-08-20.
8. O contêiner do próprio NinjaSRE **nunca** é vítima: derrubá-lo mede a ausência
   do observador, não o produto.
9. A capacidade de remediação que casa este cenário existe, declarada e
   registrada: **`proxmox_start_guest`** — "Start a Proxmox guest",
   `WRITE_REVERSIBLE`, `requires_approval=True`, com razão de aprovação e
   planejador de rollback declarados ao lado, e corpo que **recusa chamada
   direta** (`PERMISSION_DENIED`) para forçar o caminho do gate. Ela exige do
   token do Proxmox o privilégio `VM.PowerMgmt` no caminho `/vms`.
10. As tabelas em que o desfecho é lido existem e têm nome próprio:
    `agent_runs`, `run_turns`, `tool_calls`, `evidence`, `trace_events`,
    `approvals`, `rollback_plans`, `remediation_outcomes`, `episodes`,
    `incidents`, `incident_timeline`, `estate_resources`, `audit_events`.
11. O estado de partida da onda, medido no mesmo banco: `tool_calls = 0`,
    `run_turns = 0`, `evidence = 0`, `trace_events = 73` para 37 runs completed;
    todo `agent_runs.summary` recente começa com `###`; `/decisions` vazio;
    `/resources` vazio; detalhe de incidente de alerta irrecuperável.
12. As três tarefas operacionais da onda (resolver DNS nos contêineres de
    monitoração, autenticação do operador Infisical, chave do gateway de modelos)
    têm dono fora deste repositório. Esta feature **verifica a evidência** de
    cada uma; não executa nenhuma.

## O que esta feature não faz (fronteira, declarada antes dos requisitos)

Esta é a única feature da onda cujo maior risco é fazer trabalho alheio.

- **Não conserta funcionalidade.** Um defeito encontrado durante a demo volta
  como reparo da **feature dona**, pelo ciclo de reparo da onda, ou entra no
  backlog novo se for descoberta genuína sem dono. Nenhuma tarefa desta feature
  altera comportamento de produto.
- **Não executa mudança de infraestrutura.** Nem DNS, nem operador Infisical, nem
  emissão de chave de gateway, nem privilégio de token do Proxmox. Ela verifica,
  registra o estado real, e nomeia quem faz.
- **Não cria tela nova, nem acceptance spec de tela nova.** As alegações de tela
  já são das features donas (010, 020, 030); esta feature as **reexecuta contra
  staging** e as fotografa.
- **Não afrouxa nada.** Propose-only continua sendo a postura; a única execução
  de escrita da demo acontece porque um humano aprovou, uma vez, olhando.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - O laço fecha uma vez, com um humano assistindo (Priority: P1)

Numa janela combinada, o operador para um contêiner descartável e observado, e
assiste — sem tocar em mais nada — o alerta disparar sozinho, a entrega chegar
autenticada, o incidente abrir com título legível, a investigação rodar e gravar
o que fez, o relato aparecer legível, a proposta de religar surgir com plano de
reversão, e a execução acontecer **só depois** de ele aprovar. No fim, o incidente
mostra o desfecho.

**Why this priority**: é a razão de a onda existir. Toda a v6 e metade da v7
provaram peças; esta história é a primeira vez que a linha inteira roda.

**Independent Test**: a janela combinada, executada uma vez, com a evidência de
cada estação anexada. Nada mais desta feature precisa estar pronto para ela ser
julgada.

**Acceptance Scenarios**:

1. **Given** a vítima confirmada `running` e a janela aberta, **When** o operador
   a para à mão, **Then** o alerta dispara por conta própria dentro da janela de
   `for` da regra, sem ninguém emitir nada.
2. **Given** o alerta ativo, **When** o Alertmanager entrega no webhook, **Then**
   a entrega é aceita com autenticação e um incidente abre com **título legível**
   — nunca um id, nunca markdown.
3. **Given** o incidente aberto, **When** a investigação roda, **Then** ela grava
   turnos, chamadas de ferramenta com o que cada uma devolveu, evidência e custo
   por turno, e tudo isso é lido de volta **depois de um reload**, não do processo
   que rodou.
4. **Given** a investigação concluída, **When** o operador abre o run, **Then** o
   título é uma sentença, o report é markdown renderizado, e nenhum caractere de
   sintaxe aparece como texto.
5. **Given** as integrações configuradas deste deployment, **When** o modelo
   recebe o conjunto de ferramentas, **Then** ele não recebe capacidade de vendor
   que este deployment não conectou, nem capacidade de remediação que só
   devolveria recusa.
6. **Given** o diagnóstico de que o convidado está parado, **When** a investigação
   conclui, **Then** existe uma proposta de remediação com plano de reversão
   visível em Decisions e no incidente, **aguardando decisão**.
7. **Given** a proposta aguardando, **When** ninguém aprova, **Then** nada executa,
   e a razão declarada é a **política** deste deployment — não uma composição
   ausente.
8. **Given** a proposta aguardando, **When** o operador aprova pela interface,
   **Then** a decisão, o decisor e o instante são registrados **antes** de
   qualquer efeito, e o plano de reversão está registrado antes da execução.
9. **Given** a aprovação registrada, **When** a execução acontece pelo gate,
   **Then** o convidado volta a rodar, o desfecho é gravado, o episódio é gravado,
   a timeline do incidente ganha a entrada da ação, e o incidente reflete o
   desfecho em vez de continuar parado no diagnóstico.
10. **Given** qualquer momento do roteiro, **When** algo parece errado, **Then** a
    reversão manual (religar o contêiner) vale imediatamente e não depende do
    produto.

### User Story 2 - O laço de leitura é reexecutável por quem não estava na sala (Priority: P1)

Existe um segundo roteiro, sem passo destrutivo e sem aprovação: pega um alerta
que **já está** disparando, atravessa da entrega até a proposta, e para ali. Ele
roda contra staging quantas vezes for preciso, por qualquer pessoa, sem janela
combinada.

**Why this priority**: um cenário executado uma vez prova o dia. Este prova todos
os dias seguintes, e é o que um verificador independente consegue repetir sem
pedir nada a ninguém.

**Independent Test**: entregar o roteiro de leitura a alguém que não participou da
onda e observar a execução inteira sem assistência.

**Acceptance Scenarios**:

1. **Given** um alerta real já ativo no Alertmanager, **When** o roteiro de
   leitura é executado, **Then** ele atravessa entrega → incidente → investigação
   gravada → relato legível → proposta, e para na proposta.
2. **Given** o roteiro de leitura, **When** executado duas vezes seguidas,
   **Then** produz a mesma evidência nas duas — ou nomeia, na própria saída, qual
   passo variou e por quê.
3. **Given** o roteiro de leitura, **When** lido, **Then** nenhum segredo aparece
   nele: token, chave e credencial são referenciados por onde buscá-los.
4. **Given** um alerta que não dispara na hora da execução, **When** o roteiro
   chega nesse passo, **Then** ele classifica o desfecho como **ambiente**, não
   como falha de produto, e diz o que reexecutar.

### User Story 3 - A demo é um artefato, não uma lembrança (Priority: P1)

Ao fim, existe um conjunto de arquivos que outra pessoa lê e julga: o roteiro, uma
screenshot full-page por estação com tela, a saída literal de cada consulta ao
banco, e um documento de evidência que amarra estação, screenshot e consulta.

**Why this priority**: é o gate da onda. Sem artefato, "o laço fechou" é a palavra
de quem estava assistindo, que é exatamente o tipo de prova que esta onda existe
para substituir.

**Independent Test**: um verificador que não assistiu à demo abre o documento de
evidência e consegue dizer, estação por estação, se passou — sem perguntar nada.

**Acceptance Scenarios**:

1. **Given** a demo executada, **When** o documento de evidência é lido, **Then**
   cada estação tem: o que se esperava ver, a evidência que se viu, e o veredito.
2. **Given** uma estação que é tela, **When** a evidência é conferida, **Then**
   existe uma screenshot **full-page** dela, tirada em 1920×1080, com nome que
   identifica a estação.
3. **Given** uma estação que alega gravação, **When** a evidência é conferida,
   **Then** existe a consulta SQL exata **e a saída literal dela**, não uma
   afirmação sobre a saída.
4. **Given** o documento, **When** lido, **Then** nenhuma credencial, token,
   chave ou senha aparece — nem em texto, nem dentro de uma screenshot.

### User Story 4 - Falha de ambiente não é reprovação de produto (Priority: P1)

O roteiro separa, na própria estrutura, três desfechos: **o laço não fecha**
(reprova a onda), **o ambiente não colaborou nesta hora** (reexecuta), e **a demo
encontrou um defeito com dono** (vira reparo da feature dona).

**Why this priority**: sem essa separação, a primeira execução com um alerta
preguiçoso vira "a onda reprovou" e a segunda vira "a onda passou" — e nenhuma das
duas leituras é verdadeira.

**Independent Test**: percorrer os desfechos possíveis de cada estação e conferir
que cada um está classificado antes de a demo rodar, e não depois.

**Acceptance Scenarios**:

1. **Given** o roteiro, **When** lido antes da execução, **Then** cada estação já
   declara quais desfechos são de ambiente e quais são de produto.
2. **Given** um desfecho de ambiente, **When** ele ocorre, **Then** o roteiro
   nomeia a condição a reconferir e o passo por onde reentrar — e a demo não é
   declarada reprovada.
3. **Given** um desfecho de produto, **When** ele ocorre, **Then** a estação
   nomeia a **feature dona** do defeito, e a demo para até a decisão do
   orquestrador sobre reparo.
4. **Given** um defeito sem dono na onda, **When** ele ocorre, **Then** ele entra
   no backlog novo com o estado real, e não é silenciosamente absorvido.

### User Story 5 - O backlog reescrito diz onde cada coisa terminou (Priority: P1)

O `backlog.md` da raiz passa a conter apenas o que esta onda descobriu de novo.
Cada item antigo saiu porque tem evidência de fechamento; cada item operacional
não feito continua lá, com o estado real, e não desaparece.

**Why this priority**: é uma das duas metades do DoD da onda. Um backlog que
encolhe sem evidência é um backlog que mentiu.

**Independent Test**: comparar o backlog anterior com o novo, item a item, e
conferir que cada remoção tem uma evidência nomeada e cada permanência tem um
estado.

**Acceptance Scenarios**:

1. **Given** o backlog anterior, **When** o novo é escrito, **Then** todo item
   removido tem, no registro da onda, a evidência que o fecha — tela, consulta ou
   comportamento observado.
2. **Given** uma tarefa operacional não executada, **When** o novo backlog é
   escrito, **Then** ela aparece com o estado real e o que falta, nunca omitida.
3. **Given** o backlog novo, **When** lido por alguém de fora, **Then** ele não
   referencia nenhum documento de planejamento, número de feature ou caminho que
   essa pessoa não tenha ao clonar o repositório.
4. **Given** um item que a onda **não** fechou, **When** o novo backlog é escrito,
   **Then** ele continua descrito como problema, com o desfecho pelo qual seria
   julgado — a forma que o próprio backlog já pratica.

### User Story 6 - O confronto responde quem constrói cada mecanismo em produção (Priority: P1)

O registro de confronto da onda ganha uma coluna fixa — "quem constrói isso em
produção?" — respondida com `file:line` da composition root de serving, e não com
o nome do teste que instancia a peça.

**Why this priority**: é a regra nova de 2.2.0 em forma de evidência. Cinco vezes
seguidas um mecanismo passou por "escrito, testado, mergeado, nunca ligado". A
coluna é o lugar onde isso deixa de caber.

**Independent Test**: pegar três mecanismos da onda, seguir o `file:line` da
coluna, e confirmar que o caminho leva a código que roda em serving.

**Acceptance Scenarios**:

1. **Given** o confronto da onda, **When** a tabela é lida, **Then** cada
   mecanismo entregue tem `file:line` de quem o constrói no caminho de serving.
2. **Given** um mecanismo que ninguém constrói em serving, **When** a tabela é
   lida, **Then** ele aparece declarado **dormant** com a referência do que o
   ligaria — nunca com a célula em branco e nunca apontando um teste.
3. **Given** a coluna, **When** conferida, **Then** ela está preenchida no mínimo
   para o recorder de investigação, os dois gates de ação, e a confiança de
   certificado até o egress do proxy.

### Edge Cases

- **A vítima já está parada quando a janela abre.** O passo destrutivo não pode
  parar o que já está parado, e o alerta que já estava disparando não foi
  disparado pelo teste. O roteiro **interrompe** antes de parar qualquer coisa e
  exige o estado inicial conferido — colher um incidente verdadeiro e concluir
  dele uma coisa falsa é o pior desfecho possível deste roteiro.
- **O alerta não dispara dentro da janela esperada.** Desfecho de ambiente. O
  roteiro nomeia o que reconferir (a regra existe, o alvo de scrape é o que se
  pensa, a rota do Alertmanager casa `severity: critical`) e por onde reentrar.
  Silêncio antes do `for` da regra é o esperado, não sintoma.
- **A entrega não chega, mas o alerta disparou.** Recorta entre produto e
  infraestrutura: se a origem não resolve o nome do deployment, é o mesmo defeito
  que a tarefa operacional de DNS trata, e o roteiro diz isso em vez de acusar o
  webhook.
- **A investigação conclui sem evidência suficiente para propor.** Nenhuma
  proposta aparece — e isso é **correto**. A estação da proposta declara este
  desfecho como aceitável e registra o run como cenário de leitura, não como
  laço fechado. A demo do laço inteiro reexecuta com outra ocorrência.
- **O convidado migrou de nó entre a proposta e a aprovação.** O alvo aprovado
  deixou de ser o alvo real. A execução não pode agir sobre "o mesmo número em
  outro nó"; se ela agir, é defeito de produto com dono, e o roteiro registra
  assim.
- **Alguém religa o contêiner à mão antes da aprovação.** A proposta continua
  aguardando e não vira executada sozinha; aprovar depois disso encontra o
  recurso já no estado desejado e registra **esse** resultado, em vez de fingir
  que agiu.
- **A aprovação expira antes de o operador decidir.** A proposta expirada é um
  desfecho legítimo e registrado; a demo reexecuta a partir da investigação, e a
  expiração não é apagada do registro.
- **A execução falha no vendor** (privilégio insuficiente, quorum ausente, guest
  locked). O desfecho gravado é a falha, com a razão nomeada; o plano de reversão
  não é executado porque nada mudou. Falha nomeada é laço fechado com desfecho
  negativo — o que **não** fecha o laço é falha silenciosa.
- **O Argo ainda não reconciliou o digest publicado.** Desfecho de ambiente. A
  demo não começa antes de `Synced + Healthy` **e** de o serviço responder; as
  duas coisas conferidas separadamente.
- **Uma tarefa operacional não foi executada.** Não bloqueia a demo, salvo se a
  estação depender dela; entra no backlog novo com o estado real, e a estação
  afetada é marcada como não exercida em vez de aprovada por omissão.
- **Um defeito encontrado é de uma feature já dada como PASS.** Volta como reparo
  da feature dona, dentro do limite de ciclos de reparo da onda; esta feature não
  o conserta e não o esconde.

## Alegações normativas (verificadas na demo, não numa tela nova)

Frases curtas, individualmente testáveis, que a demo confere estação por estação.
Nenhuma delas nasce aqui: cada uma é a alegação de uma feature da onda, e o papel
desta feature é exercê-las **contra staging, com dado real**.

1. O título de um run é uma sentença; nenhum caractere de sintaxe markdown
   aparece como texto em título, aba, coluna ou parágrafo de resumo.
2. Um run que fez N chamadas de ferramenta mostra N entradas de transcript, cada
   uma com o que devolveu.
3. O custo do run aparece por turno; "sem custo registrado" só quando não houve
   turno.
4. Nenhuma URL do console exibe `%3A`, `%40` ou `%2B`.
5. O detalhe do incidente de alerta abre com título legível e zero painéis "não
   foi possível preencher".
6. O mesmo provider não aparece com dois estados em duas telas no mesmo instante.
7. Uma lista recarregada reflete um incidente novo em no máximo um reload.
8. Um run terminado não oferece controle de run vivo.
9. `/resources` lista recursos reais do Proxmox, e o incidente aponta um sujeito
   resolvível — "alerta para coisa que não está aqui" só para o que de fato não
   está.
10. `/decisions` lista a proposta real, com plano de reversão, e a causa de vazio
    (quando vazio) é a específica da tela.
11. A proposta declara alcance e postura, e afirma que nada executa sem o
    operador.
12. Depois da aprovação, o incidente reflete o desfecho — e não continua parado
    no diagnóstico.

**Viewport normativo de medição e de screenshot**: 1920×1080.

## Requirements *(mandatory)*

### Functional Requirements

#### O cenário nomeado, estação por estação

- **FR-001**: O cenário DEVE ser escrito como **duas** execuções distintas: um
  **laço de leitura** (alerta já ativo, termina na proposta, sem janela e sem
  escrita) e um **laço inteiro** (falha controlada, aprovação humana, execução).
- **FR-002**: O laço inteiro DEVE ter as estações nomeadas na ordem: (E1) o
  alerta dispara sozinho; (E2) a entrega chega autenticada; (E3) o incidente abre
  com título legível e sujeito resolvido; (E4) a investigação grava turnos,
  chamadas, evidência e custo; (E5) o relato é legível — sentença e documento
  renderizado; (E6) as ferramentas oferecidas condizem com as integrações
  configuradas; (E7) a proposta com plano de reversão aparece aguardando decisão;
  (E8) o humano aprova, e a decisão é registrada antes de qualquer efeito; (E9) a
  execução acontece pelo gate e o desfecho, o episódio e a entrada de timeline
  são gravados; (E10) o incidente reflete o desfecho.
- **FR-003**: Cada estação DEVE declarar, antes da execução: o que se espera ver,
  onde se olha, e qual evidência a comprova.
- **FR-004**: Cada estação DEVE declarar quais desfechos são de **ambiente**
  (reexecutável) e quais são de **produto** (bloqueiam), com a feature dona
  nomeada no segundo caso.
- **FR-005**: O passo destrutivo DEVE ser digitado por uma pessoa, uma vez, numa
  janela combinada. NÃO DEVE existir script, automação ou laço que o execute.
- **FR-006**: O roteiro DEVE exigir a conferência do estado inicial da vítima
  (rodando) e DEVE interromper quando ela já estiver parada.
- **FR-007**: O roteiro NÃO DEVE emitir alerta sintético no laço inteiro: o
  alerta dispara por conta própria ou a estação reprova como ambiente.
- **FR-008**: Uma vítima DEVE ser ao mesmo tempo descartável e observada, e o
  roteiro DEVE registrar a evidência de ambas as coisas — a autorização e a regra
  de alerta que a cobre.
- **FR-009**: O contêiner do próprio deployment NÃO DEVE ser vítima.
- **FR-010**: O roteiro DEVE declarar a reversão manual, independente do produto,
  válida a qualquer instante, e DEVE afirmar que ela não espera pelo produto.
- **FR-011**: O laço de leitura DEVE ser executável sem janela combinada, sem
  aprovação e sem qualquer escrita no estate.
- **FR-012**: Nenhum roteiro DEVE transcrever segredo; token, chave e credencial
  são referenciados por onde obtê-los.

#### A aprovação e a execução

- **FR-013**: A aprovação do laço inteiro DEVE ser dada por uma pessoa, na
  interface, durante a demo. NÃO DEVE ser feita por chamada de API automatizada,
  por fixture, nem por qualquer caminho que dispense o humano.
- **FR-014**: A postura vigente DEVE permanecer propose-only: nenhuma ação acima
  de leitura executa sem decisão humana registrada, inclusive durante a demo.
- **FR-015**: A decisão, o decisor e o instante DEVEM ser registrados antes de
  qualquer efeito.
- **FR-016**: O plano de reversão DEVE estar registrado antes da execução.
- **FR-017**: A execução DEVE acontecer **através do gate**; a recusa da chamada
  direta à capacidade DEVE continuar valendo, e nenhuma tarefa desta feature a
  remove ou a contorna.
- **FR-018**: A remediação escolhida DEVE ser reversível e de alcance mínimo — um
  único recurso, sem efeito sobre vizinhos.
- **FR-019**: A demo DEVE exercitar o caminho de **recusa** também: uma proposta
  rejeitada com motivo, e a rejeição sem motivo recusada — em ocorrência
  diferente da que foi aprovada, nunca na mesma.
- **FR-020**: As duas decisões DEVEM aparecer na auditoria com autor, ação,
  assunto e resultado.

#### A demo como artefato

- **FR-021**: A feature DEVE produzir um **roteiro executável** por cenário, com
  pré-condições, passos, URLs, o que se espera ver, evidência esperada e
  reversão.
- **FR-022**: A feature DEVE produzir um **documento de evidência consolidada**
  que amarre, por estação: expectativa, screenshot, consulta, saída e veredito.
- **FR-023**: Toda estação que é tela DEVE ter screenshot **full-page**, tirada em
  1920×1080, nomeada pela estação.
- **FR-024**: Toda estação que alega gravação DEVE ter a consulta SQL exata **e a
  saída literal** anexadas — nunca uma afirmação sobre a saída.
- **FR-025**: A evidência DEVE viver no diretório desta feature, em `evidence/`.
- **FR-026**: Nenhum artefato de evidência DEVE conter credencial, token, chave
  ou senha, inclusive dentro de screenshots.
- **FR-027**: O documento de evidência DEVE registrar o instante de cada estação,
  de modo que a ordem temporal do laço seja auditável.
- **FR-028**: O documento de evidência DEVE registrar o digest publicado e o
  estado do Argo no momento da demo, para que a evidência aponte uma versão.
- **FR-029**: O roteiro de leitura DEVE ser executável por quem não participou da
  onda, sem assistência.

#### A evidência no banco

- **FR-030**: A feature DEVE enumerar, e executar, as consultas que provam cada
  alegação de gravação, no banco de staging, escopadas pela organização do
  deployment.
- **FR-031**: A gravação da investigação DEVE ser provada por contagens de
  `run_turns`, `tool_calls`, `evidence` e `trace_events` para o run da demo, todas
  maiores que zero.
- **FR-032**: O custo por turno DEVE ser provado pela leitura de `usage` em
  `run_turns`, turno a turno.
- **FR-033**: A separação de sentença e documento DEVE ser provada lendo o campo
  de sentença do run da demo e confirmando que ele não começa com sintaxe
  markdown.
- **FR-034**: A proposta DEVE ser provada pela linha em `approvals` ligada ao run,
  com ação, nível de efeito e estado, e pela linha correspondente em
  `rollback_plans`.
- **FR-035**: A decisão humana DEVE ser provada pelo estado, decisor, instante e
  motivo em `approvals`, e pelo evento correspondente em `audit_events`.
- **FR-036**: O desfecho DEVE ser provado por `remediation_outcomes` para o
  recurso e a capacidade da demo.
- **FR-037**: O aprendizado registrado DEVE ser provado por `episodes` para o run
  da demo.
- **FR-038**: O reflexo no incidente DEVE ser provado por `incident_timeline` e
  pelo estado do incidente em `incidents`.
- **FR-039**: O estate povoado DEVE ser provado pela contagem de
  `estate_resources` e pela presença do recurso que é sujeito do incidente.
- **FR-040**: Cada consulta DEVE ser apresentada com o valor **antes** da onda,
  quando houver, ao lado do valor medido — o contraste é a evidência.

#### As tarefas operacionais

- **FR-041**: A feature DEVE verificar a evidência de cada tarefa operacional da
  onda, sem executar nenhuma mudança de infraestrutura.
- **FR-042**: A verificação de resolução de nomes DEVE ser um nome do domínio do
  deployment resolvendo de dentro de cada contêiner de monitoração.
- **FR-043**: A verificação de sincronização de segredos DEVE ser um recurso de
  segredo gerenciado efetivamente sincronizando, ou a decisão registrada de
  conviver com o segredo manual.
- **FR-044**: A verificação da chave do gateway de modelos DEVE ser o provider
  correspondente aparecendo **Verified** no console.
- **FR-045**: Uma tarefa operacional não concluída NÃO DEVE ser omitida: ela entra
  no backlog novo com o estado real e o que falta.
- **FR-046**: Uma tarefa operacional não concluída NÃO DEVE, por si, reprovar a
  demo — salvo quando uma estação depender dela, caso em que a estação é marcada
  como não exercida.

#### O backlog reescrito

- **FR-047**: A feature DEVE reescrever `backlog.md` contendo apenas o que esta
  onda descobriu de novo mais o que ela não fechou.
- **FR-048**: Cada item removido DEVE ter, no registro da onda, a evidência que o
  fecha nomeada — tela, consulta ou comportamento observado.
- **FR-049**: O backlog novo NÃO DEVE citar caminho de planejamento, número de
  feature, identificador de requisito ou artigo de constituição: ele é lido por
  quem clonou o repositório e não tem nenhum desses documentos.
- **FR-050**: O backlog novo DEVE preservar a forma que o arquivo já pratica:
  problema descrito, o que acontece hoje, e o desfecho pelo qual seria julgado.
- **FR-051**: O backlog novo NÃO DEVE nomear os projetos de origem de que este
  produto se inspira.
- **FR-052**: O que a demo encontrou e ninguém consertou DEVE entrar no backlog
  novo com o estado real.

#### O confronto da onda

- **FR-053**: O registro de confronto da onda DEVE ganhar a coluna "quem constrói
  isso em produção?", com `file:line` da composition root de serving.
- **FR-054**: A coluna DEVE estar preenchida no mínimo para: o recorder de
  investigação, o gate de remediação, o gate de autonomia, o resolvedor de
  integrações do time, e a confiança de certificado até o egress do proxy.
- **FR-055**: Uma célula NÃO DEVE apontar teste, contract test ou plano de dados
  simulado. Um mecanismo cuja única construção é de teste DEVE ser declarado
  **dormant**, com a referência do que o ligaria.
- **FR-056**: O confronto DEVE citar a demo como evidência do fechamento da onda,
  com o caminho da evidência consolidada.

#### A fronteira do reparo

- **FR-057**: Um defeito de produto encontrado na demo DEVE ser registrado com a
  feature dona nomeada, e NÃO DEVE ser corrigido por esta feature.
- **FR-058**: Um defeito sem dono na onda DEVE entrar no backlog novo.
- **FR-059**: Nenhuma tarefa desta feature DEVE alterar comportamento de produto,
  executar mudança de infraestrutura, ou tocar diretório de outra feature.
- **FR-060**: Depois de qualquer reparo aceito, a estação afetada DEVE ser
  reexecutada e a evidência **substituída**, nunca acumulada como se as duas
  fossem verdadeiras.

### Key Entities

- **Estação**: um ponto do laço — nome, o que se espera ver, onde se olha,
  evidência exigida, desfechos de ambiente, desfechos de produto com dono.
- **Roteiro**: um cenário executável — pré-condições, passos, URLs, evidência
  esperada, reversão, e quem precisa estar ciente antes.
- **Evidência de estação**: screenshot, consulta com saída literal, ou saída de
  comando — com instante e veredito.
- **Vítima**: o recurso derrubado de propósito — identidade, onde vive, por que é
  descartável, qual regra de alerta a observa, como se reverte à mão.
- **Proposta**: a ação que o produto sugere — efeito em uma frase, alvo, alcance,
  plano de reversão, estado da decisão.
- **Desfecho**: o que a execução produziu — sucesso, falha nomeada, ou estado já
  desejado — com o sinal que o verifica.
- **Achado da demo**: um defeito encontrado — descrição, estação onde apareceu,
  feature dona ou "sem dono", destino (reparo ou backlog).
- **Item de backlog**: um problema descrito por desfecho julgável, sem referência
  a documento de planejamento.

## Success Criteria *(mandatory)*

- **SC-001**: O laço inteiro fecha **uma vez**, com um humano assistindo, e as dez
  estações têm evidência anexada (hoje: o laço nunca fechou uma vez).
- **SC-002**: Para o run da demo, `run_turns`, `tool_calls` e `evidence` são todos
  maiores que zero (hoje: `0`, `0` e `0` para 37 runs completed).
- **SC-003**: A sentença de relato do run da demo não começa com sintaxe markdown
  (hoje: 100% dos `summary` recentes começam com `###`).
- **SC-004**: Existe exatamente uma proposta com plano de reversão registrada para
  o run da demo, e ela está visível em Decisions (hoje: zero propostas, Decisions
  eternamente vazio).
- **SC-005**: Zero ações acima do nível de leitura executadas sem decisão humana
  registrada, medido na auditoria ao fim da demo.
- **SC-006**: O incidente da demo termina com o desfecho refletido: entrada de
  timeline da ação, desfecho gravado e episódio gravado (hoje: o fluxo do
  incidente para no diagnóstico).
- **SC-007**: O detalhe do incidente da demo abre com título legível e zero
  painéis "não foi possível preencher" (hoje: todo incidente de alerta é
  irrecuperável).
- **SC-008**: `/resources` lista recursos reais e o incidente da demo aponta um
  sujeito resolvível (hoje: estate vazio e "zone Unplaced").
- **SC-009**: O roteiro de leitura é executado por alguém que não participou da
  onda, sem assistência, em menos de 15 minutos.
- **SC-010**: 100% das estações que alegam gravação têm consulta **e saída
  literal** anexadas.
- **SC-011**: 100% das estações que são tela têm screenshot full-page em
  1920×1080.
- **SC-012**: Todo item do backlog anterior tem destino explícito: fechado com
  evidência nomeada, ou presente no backlog novo com o estado real. Zero itens sem
  destino.
- **SC-013**: A coluna "quem constrói isso em produção?" está preenchida para
  todos os mecanismos entregues pela onda, e nenhuma célula aponta um teste.
- **SC-014**: Zero arquivos de produto alterados por esta feature.
- **SC-015**: `make verify` verde ao fim, com o número de testes e a duração
  registrados.

## Assumptions

- A demo roda contra o staging na ponta da onda — todas as features mergeadas,
  `make deploy-stg` executado, Argo reconciliado e o serviço respondendo.
- O operador está presente e acordado durante a janela do laço inteiro; a
  aprovação é literalmente humana e não há substituto para isso.
- A vítima e a remediação são as do plano, **confirmadas pelo operador na abertura
  da janela**; se ele recusar, o plano tem candidatos alternativos e o roteiro é
  ajustado antes de qualquer passo destrutivo.
- O provider de modelo continua Verified pelo caminho do vault; a demo não
  configura provider.
- As regras do Alertmanager e a rota de entrega continuam como estão; esta feature
  não altera a configuração de monitoração.
- Duas execuções do laço inteiro não são necessárias: uma execução com evidência
  completa é o critério. A repetibilidade é responsabilidade do laço de leitura.
- O limite de ciclos de reparo da onda vale aqui: no máximo dois, e a decisão de
  gastá-los é do orquestrador, não desta feature.

## Decisões que o operador confirma (e que a demo não toma sozinha)

Estas não são lacunas de especificação: são decisões que **pertencem** ao
operador e cuja resposta precisa ser dita no dia, com o ambiente na frente.

1. **A vítima.** A candidata é a `redis` (CT122, pve01) — a única que a validação
   anterior encontrou sendo descartável **e** observada. Continua fora de uso? Há
   alguma coisa dependendo dela hoje? Se não servir, qual alvo de scrape ou sonda
   real pode ser derrubado por dez minutos?
2. **O privilégio do token do Proxmox.** Religar um convidado exige
   `VM.PowerMgmt` em `/vms`. Se o token que este deployment guarda é de leitura,
   a execução da estação E9 falha por privilégio — e conceder escrita ao token do
   produto é uma decisão de fronteira de segurança do operador, não desta
   feature.
3. **A janela.** Quando, e por quanto tempo, o operador consegue assistir do
   começo ao fim sem interromper.
4. **A ocorrência da rejeição.** A demo exercita aprovar e rejeitar em
   ocorrências diferentes; a segunda ocorrência é outro alerta real já ativo, ou
   uma segunda janela?
5. **As tarefas operacionais.** Alguma delas será executada antes da demo, ou
   todas entram no backlog novo com o estado real?
6. **O gasto de reparo.** Se a demo encontrar um defeito de produto com dono, a
   onda para para reparar ou registra e segue? O limite de ciclos é o teto; a
   decisão de usá-lo é do operador.

## Dependencies

Esta feature depende de **todas** as anteriores da onda, mergeadas e verificadas:

- **001** — sem o recorder composto no caminho de serving, as estações E4 e E5
  não têm o que fotografar e as contagens do banco continuam zeradas.
- **010** — sem a leitura do relato, a estação E5 mostra markdown cru e o título
  do run continua sendo um documento.
- **020** — sem identidade endereçável, as estações E3 e E10 não abrem: o detalhe
  do incidente de alerta é hoje irrecuperável.
- **030** — sem uma fonte por fato, a estação E7 lê "Decisions vazio porque o
  setup não terminou" com a proposta existindo no store, e as listas podem
  renderizar de cache.
- **040** — sem os gates compostos, não há proposta, não há aprovação e não há
  execução: as estações E6 a E9 inexistem.
- **070** — sem confiança de certificado, o Proxmox não conecta, o estate fica
  vazio, o sujeito do incidente não resolve, e a capacidade de religar o
  convidado não tem por onde chegar ao vendor.
- **000** — a regra de composição de 2.2.0 é o que dá substância à coluna do
  confronto, e o modo de rodar aceitação contra staging é o que permite
  reexecutar as alegações das features donas contra a URL real.

## Gates tocados

- Suíte transversal do console, rodada contra staging na fronteira desta feature.
- Acceptance specs das features donas (010, 020, 030), rodados contra staging,
  restritos aos que são seguros em ambiente compartilhado.
- Contagens no banco de staging, enumeradas nesta spec.
- `make verify` completo ao fim: lint, formatação, tipos, contratos de import,
  guardas de constantes/protocolos/dependências e a suíte.
- Nenhum gate novo nasce aqui.

## Out of scope

- Qualquer correção de comportamento de produto — pertence à feature dona.
- Qualquer mudança de infraestrutura: DNS, operador de segredos, chave do gateway
  de modelos, privilégio de token do Proxmox.
- Autonomia acima de propose-only, allow-list de ações automáticas, kill switch.
- Segunda execução do laço inteiro "para conferir": uma execução com evidência
  completa é o critério; a repetição é do laço de leitura.
- Julgamento editorial da qualidade do root cause ("este relato salvaria alguém
  às três da manhã?"): é a sessão de leitura que a recomendação da onda pede, e
  ela vem depois.
- Remoção do deployment legado do chart, que é um commit no repositório GitOps.
