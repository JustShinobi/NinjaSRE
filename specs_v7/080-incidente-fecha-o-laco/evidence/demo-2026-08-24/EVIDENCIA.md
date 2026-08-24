# A demo, executada — 2026-08-24

Contra staging real (`stg-ninjasre.lan.kyo.ninja`) e o hipervisor Proxmox real
do cluster HAL9000. Contêiner CT122 (`redis`, nó `pve01`) parado com
autorização explícita do operador, fora por **18 minutos**, religado.

## A linha do tempo

| | o que | quando (UTC) |
|---|---|---|
| — | `pct stop 122` | 10:26:29 |
| E1 | `ProxmoxGuestStopped` ativa | 10:27:34 |
| E1 | dispara, cumprido o `for: 2m` | 10:29:34 |
| E2 | `POST /webhooks/alertmanager` → **202** | 10:29:45 |
| E3 | incidente `inc_05328c58ca88676b` aberto | 10:29:45 |
| E4 | investigação `d393d5d0…` gravada | 10:29:45 |
| E5 | investigação conclui, 5 passos, 23s | 10:30:08 |
| — | `pct start 122` | 10:44:47 |
| E10 | incidente fecha sozinho | 10:50:06 |

Nenhum alerta foi emitido à mão. Cada passo depois do `pct stop` aconteceu
porque o anterior aconteceu.

## Estações cumpridas

**E1 — o alerta dispara sozinho.** `activeAt` 10:27:34, disparo 10:29:34,
nomeando `redis` e `lxc/122`.

**E2 — a entrega chega.** `202`, autenticada. A tela do incidente diz por quem:
*"the delivery was authenticated by alertmanager-delivery"*.

**E3 — o incidente abre com identidade endereçável.**
`/incidents/inc_05328c58ca88676b` — curto, estável, sem `%3A`, `%40` ou `%2B`.
Nenhum painel diz que não pôde preencher. O chip diz o estado real
(*Investigation running*), não *Unknown*. `Proposed action` diz *"Nothing
proposed yet"* com a frase inteira, que é o estado correto naquele instante.

**E4 — a investigação gravou.** 13 eventos, 5 turnos, 44.746 tokens, com o
custo repartido por turno.

**E5 — o relato é legível.** A manchete é uma frase:

> Proxmox LXC container redis on node pve01 stopped unexpectedly causing
> service and exporter outages

Não é identificador, não é markdown cru, e **nomeia o nó certo**.

**E6 — as ferramentas condizem.** Cada chamada pareada com seu resultado e um
estado honesto:

| capacidade | resultado |
|---|---|
| `prometheus_active_alerts` | SUCCEEDED |
| `proxmox_guest_tasks` | FAILED — *proxmox answered 501: Method 'GET /nodes/pve01/lxc/122/status/tasks' not implemented* |
| `changes_in_window` | FAILED — *No change source is configured for this deployment, so whether anything changed before this incident is unknown rather than answered.* |
| `assess_evidence_sufficiency` | SUCCEEDED |

As duas falhas trazem a mensagem real do upstream, verbatim. A segunda recusa
afirmar um negativo — *"unknown rather than answered"* —, que é a disciplina
que esta onda inteira persegue.

**E10 — o incidente reflete o desfecho.** Fechou sozinho às 10:50:06:

    state:         resolved
    close_reason:  ProxmoxGuestStopped was resolved upstream
    self_resolved: true

O produto **não reivindica** ter consertado nada. Registra que a causa sumiu a
montante e que a resolução não foi dele. Foi um humano quem religou, e o
registro diz isso.

## Estações NÃO exercidas, e por quê

**E7, E8, E9 — propor, aprovar, executar.** Não aconteceram, e a razão não é
falha de ambiente nem de tela.

O catálogo inteiro deste deployment tem **três** capacidades de escrita:

    integrations/alertmanager/tools/acknowledge_incident.py   WRITE_REVERSIBLE
    integrations/pushover/tools/post_message.py               WRITE_REVERSIBLE
    integrations/telegram/tools/post_message.py               WRITE_REVERSIBLE

As três são aviso ou reconhecimento. **Nenhuma capacidade, em lugar algum do
catálogo, atua sobre infraestrutura** — nada reinicia um serviço, liga um
convidado ou muda estado de sistema. As vinte capacidades do Proxmox são todas
de leitura; até `proxmox_guest_start_diagnosis` diagnostica uma partida que
falhou, não a executa.

A maquinaria em volta está inteira e funcionando: o balcão compôs 20
capacidades, o portão se registra por run em `pre_tool_use`
(`gateway/runtime/investigator.py:375`), o fluxo de aprovação existe, o teto de
ferramentas é 40 e só 4 foram usadas — logo nada foi cortado por orçamento.

**O agente se comportou corretamente: não tinha o que propor.** O laço fecha
até "entendi e registrei"; não fecha em "agi", porque o vocabulário de ação
está vazio.

## Achados de produto

### 1. O título do incidente é o nome do alerta, não uma frase

A tela mostra `ProxmoxGuestStopped`. O roteiro exige frase. A frase existe e o
próprio produto a produz — a manchete da investigação é uma frase correta e
completa —, mas o título do incidente não a recebe.

### 2. O cabeçalho do incidente atribui o incidente ao nó errado

O cabeçalho diz **`node pve02`**. Três linhas abaixo, na mesma tela, os rótulos
do alerta dizem **`node=pve01`**. E a investigação, na tela seguinte, também diz
`pve01`, corretamente.

A CT122 roda no `pve01`. `192.168.68.159` é o `pve02`, que é apenas onde o
`pve-exporter` está hospedado. O cabeçalho está lendo `instance` — o endereço de
quem *raspou* a métrica — e apresentando-o como o nó do sujeito.

Um operador que leia o cabeçalho abre sessão no nó errado. O produto tem o dado
certo em duas outras superfícies.

### 3. A descoberta não resolve o nó do convidado

Todo convidado descoberto tem `native_id` na forma `lxc/HAL9000/unknown/122` —
o segmento do nó é literalmente `unknown`. O `pve_guest_info` do exportador
carrega `node=pve01`, então o dado está disponível. Provável causa do achado 2.

### 4. O custo aparece de duas formas em duas telas

O painel do incidente diz `5 steps · 23s · Not recorded`. A tela do run diz
`Cost $0.00` com repartição por turno. As duas descrevem o mesmo run.

## Sobre a regra de alerta que escrevi

Antes de parar o contêiner procurei uma regra que o vigiasse e, não achando
nenhuma sobre `pve_up` de convidado, escrevi uma
(`ProxmoxGuestStopped`, commitada em `infra-cluster` como `5cbeb0e`).

**Meu diagnóstico estava incompleto.** Quatro regras já cobriam a CT122 pelo
lado do serviço e dispararam *antes* da minha: `DatabaseTcpProbeFailed`
(10:28:15), `GatusEndpointHealthcheckFailed` (10:28:30), `InstanceDown` e
`RedisExporterDown` (10:29:45). O alerta teria chegado sem eu escrever nada; o
que faltava era cobertura do convidado *como convidado*, não cobertura alguma.

A regra continua correta — verificada silenciosa contra as séries vivas antes
de carregar, e exige que o convidado estivesse rodando na última meia hora, o
que a distingue dos dezesseis convidados deliberadamente parados neste cluster.
Mas ela não era a precondição que afirmei ser.

## Imprecisão no roteiro

`ssh root@192.168.68.159 'ssh pve01 "pct stop 122"'` não funciona: `pve01` não
resolve a partir do host de entrada. O endereço que funciona é
`192.168.68.149`. A primeira tentativa falhou sem parar nada.
