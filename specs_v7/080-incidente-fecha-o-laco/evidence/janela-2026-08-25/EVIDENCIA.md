# A segunda janela — 2026-08-25

Autorizada pelo operador: *"o 122 não está em uso, qualquer teste nele está
liberado"*. Vítima CT122 (`redis`, nó `pve01`), fora por **5 minutos e 18
segundos**, das 19:28:50Z às 19:34:08Z.

A versão medida: `gitops fd98df056074`, componentes `app` + `proxy` + `web`
publicados sem `COMPONENTS=`, Argo `Synced/Healthy`, os três pods com 2m36s de
idade no marco zero. Rotas aquecidas antes do passo destrutivo — a mais lenta
respondeu em 1,67s, então nada aqui é primeira renderização a frio.

## O bloqueio caiu, e isso foi medido antes e depois

A onda anterior parou aqui porque `proxmox_start_guest` — a única ação que
conserta um convidado parado — pontuava 0,0000 contra um alerta descrito em
português e era cortada no teto de 40 capacidades.

**Antes da janela**, contra o catálogo real de 80 ferramentas:

| descrição do alerta | escore de `proxmox_start_guest` | posição |
|---|---|---|
| português | 0,0000 | 57ª de 80 — cortada |
| inglês (a regra de hoje) | 1,8182 | **7ª** |

**Dentro da janela**, lido da gravação do próprio run
(`run_turns.payload->'selection_rationale'`, run `88b24f72`):

    ranked 60, offered 40, cut by the ceiling 20
    ...
    + proxmox_start_guest (0.625): use cases overlap the summary (+0.625)

Vigésima de quarenta. **Oferecida.** O agente teve, pela primeira vez, a ação
que desfaz o estado que o alerta descreve.

## O laço, estação por estação

| | o que se pediu | o que aconteceu |
|---|---|---|
| **E1** | o alerta dispara sozinho | **cumprida** — `ProxmoxGuestStopped` ativo em 19:31:49Z, 2m59s depois do stop, sem ninguém emitir nada. `pve_up{id="lxc/122"}` já era 0 aos 43 segundos; o resto é o `for: 120s` da regra |
| **E2** | a entrega chega autenticada | **cumprida** — a tela do incidente diz *"the delivery was authenticated by alertmanager-delivery"* |
| **E3** | o incidente abre legível, com sujeito resolvido | **REPROVOU (produto)**, pelas mesmas duas razões da demo anterior — ver abaixo. Incidente `inc_9bc096025b6f46df` |
| **E4** | a investigação grava | **cumprida** — 5 turnos, 21s, quatro chamadas cada uma pareada com o seu resultado |
| **E5** | o relato é uma sentença | **cumprida** — *"Proxmox LXC container 122 running redis on node pve01 stopped unexpectedly"*, e ela nomeia o nó certo |
| **E6** | as ferramentas condizem | **cumprida, e desta vez sem a ressalva** — 40 oferecidas, `proxmox_start_guest` entre elas |
| **E7** | a proposta aparece com plano de reversão | **não exercida** — `approvals` = 0. A razão mudou de lugar e está abaixo |
| **E8/E9** | aprovar e executar pelo portão | **não exercidas** — dependem de E7 |

Contagens ao fim da janela, iguais às do marco zero: `approvals` 0,
`rollback_plans` 0, `remediation_outcomes` 0, `episodes` 0.

## Por que nada foi proposto, agora que havia com o quê

Quatro chamadas, na ordem:

| capacidade | resultado |
|---|---|
| `prometheus_active_alerts` | SUCCEEDED |
| `proxmox_guest_tasks` | FAILED — *proxmox answered 501 ... Method 'GET /nodes/pve01/lxc/122/status/tasks' not implemented* |
| `proxmox_guest_start_diagnosis` | FAILED — **o mesmo 501, no mesmo caminho** |
| `logs_for_resource` | FAILED — nenhuma fonte de log configurada neste deployment |

O relato do agente nomeia a lacuna que isso deixou:

> **Unestablished Details**: Direct LXC task history and internal shutdown
> reason on node `pve01` could not be retrieved due to API endpoint limitations
> and lack of a configured central log collector.

E o agente **não propôs**, o que é o desfecho que a própria tarefa declara
aceitável: uma investigação sem evidência suficiente não propõe nada.

### O caminho que o produto chama nunca existiu

`integrations/proxmox/client.py:756` monta
`/nodes/{node}/{kind}/{vmid}/status/tasks`. Conferido contra o hipervisor,
Proxmox 9.2.6:

    $ pvesh get /nodes/pve01/lxc/122/status/tasks
    No 'get' handler defined for '/nodes/pve01/lxc/122/status/tasks'

Não é limitação de versão nem privilégio: **esse endpoint não existe na API do
Proxmox**. O que existe é `/nodes/{node}/tasks?vmid=`, e ele devolve
exatamente a evidência que faltava:

    $ pvesh get /nodes/pve01/tasks --vmid 122 --limit 3
    [{"type":"vzstop","status":"OK","starttime":1787686132,
      "user":"root@pam","id":"122","node":"pve01", ...

`starttime 1787686132` é 19:28:52Z — o nosso `pct stop`, com o usuário que o
deu. Duas das quatro chamadas do run morreram num caminho errado, e a resposta
que elas buscavam estava a um caminho de distância.

### O que isso muda, e o que não muda

Muda a dona: é `integrations/proxmox/client.py`, não o escorador, não o balcão
de remediação, não o vocabulário do catálogo.

**Não muda o desfecho da estação, e é importante dizer por quê.** Se a chamada
tivesse funcionado, o agente teria lido `vzstop` por `root@pam` — uma parada
manual e deliberada. Diante disso a decisão correta continua sendo não propor
religar: alguém parou de propósito. **O passo destrutivo desta demonstração é
indistinguível de uma manutenção**, e essa é uma propriedade do roteiro, não
um defeito do produto. Uma ocorrência que exercite E7 a E9 precisa de uma falha
que o agente possa atribuir a um defeito, não à ação de uma pessoa.

## E3, reprovada de novo, com a origem visível na série

O cabeçalho diz **`node pve02`**. Os rótulos do alerta, na mesma tela, dizem
`node=pve01`. A investigação, na tela seguinte, diz `pve01`.

Desta vez a origem foi medida antes de o produto tocar no dado:

    pve_up{id="lxc/122", instance="192.168.68.159", job="pve-exporter"} = 0

`192.168.68.159` é o pve02 — o host onde o `pve-exporter` roda. O sujeito
gravado é `res-47555daca81efa67dacce16fb42c898e` (`node/HAL9000/pve02`), com
`matched_on: address` e `target_label: instance`.

**A assimetria que prova a causa**: o mesmo stop abriu cinco incidentes. Os
outros quatro — `RedisExporterDown`, `InstanceDown`,
`GatusEndpointHealthcheckFailed`, `DatabaseTcpProbeFailed` — casaram por
`10.20.20.52`, o endereço do próprio convidado, e resolveram o sujeito
**certo**. Só o alerta do hipervisor erra, porque só nele o `instance` é o
raspador em vez do raspado.

O título continua sendo `ProxmoxGuestStopped`, o nome do alerta, e não uma
frase — enquanto o mesmo produto produz a frase certa uma tela adiante.

## Um achado novo, da tela

O cartão da investigação mostra `5 steps · 21s · Not recorded` ao lado de um
chip dizendo **`Investigation running`**. O run está `completed` desde
19:32:06Z. A duração de um run terminado e um chip de run vivo convivem no
mesmo cartão: o chip lê o estado do incidente e é rotulado como se lesse o do
run.

## Telas

Em `telas/`, full-page a 1920, capturadas às 19:34:30Z contra o staging real,
com a sessão trocada por token (a senha nunca vira cookie).

| arquivo | o que se lê |
|---|---|
| `incident-detail.png` | E2, E3, E7 — a entrega autenticada, o cabeçalho `pve02` contra os rótulos `pve01`, e *"Nothing proposed yet"* com a frase inteira |
| `incidents-list.png` | os cinco incidentes do mesmo stop, e os títulos que são identificadores |
| `run-detail.png` | E4, E5 — as quatro chamadas com o resultado de cada uma, os dois 501 verbatim, e o relato renderizado |
| `decisions.png` | E7 — a fila vazia |

## Segredos

Nenhum token, chave, senha ou credencial neste arquivo, nas telas ou nas
consultas. A credencial de staging foi lida do processo que a guarda e trocada
por token de sessão; o token não está escrito aqui.
