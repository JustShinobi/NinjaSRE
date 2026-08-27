# O laço de leitura, executado — 2026-08-24

Travessia não destrutiva, sobre um alerta que já existia. Nada foi derrubado,
nada foi emitido à mão. Capturas a **1920×1080**, que é o viewport que a
especificação declara — a demo do laço inteiro fora capturada a 1280 e isso
está dito lá.

## E1 — o alerta, e por que este

Dezessete alertas ativos no Alertmanager. Escolhido:

    RestoreDrillStale
    severidade  critical
    início      2026-08-24 11:08:43Z
    alvo        192.168.68.159:9100 (exportador de nó do pve02)

**Por quê:** o critério do roteiro é que um alerta cujo sujeito o estate conhece
dá uma travessia mais rica em E3. O estate deste deployment carrega `pve02` como
nó descoberto, então o sujeito resolve — ao contrário de, por exemplo, o
`ContainerMemoryHigh` sobre o convidado 184, que o estate não tem e que a tela
de recursos já reporta corretamente como "alerta para coisa que não está aqui".

De passagem, um achado sobre os dados de origem: o `GatusEndpointHealthcheckFailed`
tem `startsAt: 2099-12-31T23:59:59`. Um alerta que começa daqui a setenta e três
anos não é deste roteiro, mas alguém deve olhar.

## E2 — a entrega, e a recusa

**A sonda que vale é a de recusa, porque não cria dado.** Duas, contra
`POST /webhooks/alertmanager`:

| enviado | resposta |
|---|---|
| sem `Authorization` | **401** |
| `Bearer` com token inventado | **401** |

    {"error":{"type":"unverified",
              "message":"this alertmanager webhook did not verify against any
                         configured route"}}

Mensagem idêntica nos dois casos, e isso é correto: duas mensagens diferentes
diriam a quem sonda qual metade acertou. Conferido depois no banco: **nenhum
incidente foi aberto** no intervalo. A recusa recusa.

A tela de entradas está em `e2-01-alert-intake.png`.

## E3 — o incidente

`e3-01-incidentes.png`, `e3-02-detalhe.png`.

| o que o roteiro exige | resultado |
|---|---|
| endereço sem `%3A`, `%40`, `%2B` | **cumpre** — `/incidents/inc_5c836cbc6d57e28a` |
| nenhum painel diz que não pôde preencher | **cumpre** |
| o chip diz o estado real | **cumpre** — *Investigating* + *Investigation running* |
| o sujeito aponta recurso que o estate lista | **cumpre** — `node pve02` |
| o título é uma frase | **NÃO cumpre** — mostra `RestoreDrillStale` |

O painel `Proposed action` diz *"Nothing proposed yet — No investigation has
concluded with a remediation to decide on for this incident."*, e a trilha de
evidência diz *"Every query, answer and token spent, in order. Nothing here is
prose without a source."*

O incidente mostra a mesma entrega chegando **sete vezes** ao longo do dia,
anexadas ao mesmo incidente em vez de abrirem sete — agrupamento correto.

## E4 a E6 — a investigação, lida do store

`e4-01-run-primeiro.png`, `e4-02-run-setimo.png`. Ambas capturadas depois de um
`reload`, que é o que faz a leitura vir do store e não do processo que rodou.

As sete investigações deste incidente produzem a mesma forma: **14 blocos de
transcript** cada. As manchetes:

    primeira (11:08):  "The weekly restore drill cron jobs on node pve02
                        exceeded their maximum ..."
    sétima  (17:38):   "Weekly restore drill jobs on node pve02 exceeded
                        their maximum healthy e..."

**São frases.** Dizem o quê, onde e o que excedeu.

## E8 — a repetibilidade

Respondida sem esforço extra: o mesmo incidente foi investigado sete vezes em
seis horas e meia, e as sete produziram a mesma forma e o mesmo tipo de
manchete. Não é uma travessia que funcionou uma vez.

## O que esta travessia afia nos achados da demo

### O título: terceira confirmação, e agora com o contraste dentro do mesmo incidente

A demo já mostrara `ProxmoxGuestStopped` onde ia uma frase. Aqui é
`RestoreDrillStale`, noutro alerta e noutro incidente — e **a frase existe, na
tela seguinte, escrita pela investigação do próprio incidente**:

    cabeçalho do incidente:  RestoreDrillStale
    manchete da investigação: The weekly restore drill cron jobs on node pve02
                              exceeded their maximum ...

O produto tem a frase. O cabeçalho do incidente não a recebe.

### O nó: a causa exata, que a demo sozinha não dava

Na demo o cabeçalho dizia `node pve02` e os rótulos diziam `node=pve01`. Aqui
o cabeçalho diz `node pve02` e os rótulos **também** dizem `node=pve02`.

A diferença explica o mecanismo: o cabeçalho lê o *host do exportador*. Um
exportador de nó roda no nó que descreve, então coincide. O `pve-exporter` roda
num nó e descreve os convidados de **todos** — e aí o cabeçalho nomeia a máquina
que raspou a métrica, não a que hospeda o sujeito.

Não é "às vezes erra": erra sempre que o exportador não é local ao sujeito, que
é o caso de todo convidado deste cluster.

### O custo: segunda confirmação

`5 steps · 32s · Not recorded`, na mesma posição em que a demo mostrou
`5 steps · 23s · Not recorded`. A tela do run mostra a repartição por turno.
Duas superfícies, o mesmo run, duas respostas.
