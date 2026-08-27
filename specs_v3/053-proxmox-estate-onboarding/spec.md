# 053 — O cluster Proxmox como primeiro estate

**Depende de:** 051. **Bloqueia:** 054, 055.

O estate deixa de ser um conceito e passa a ser 57 containers, 2 nós e 7 zonas
com nome, IP, zona e criticidade.

## O que já existe do lado do NinjaSRE

A integração `proxmox` é uma das mais completas do catálogo — **20 ferramentas**,
todas de leitura e todas específicas do problema:

`cluster_health`, `quorum_status`, `corosync_links`, `ha_state`,
`migration_feasibility`, `replication_lag`, `guest_pressure`,
`guest_start_diagnosis`, `guest_tasks`, `storage_pressure`, `zfs_health`,
`disk_health`, `datastore_availability`, `backup_coverage`, `backup_failures`,
`protection_gaps`, `orphaned_volumes`, `reclaimable_space`, `clock_skew`.

Além delas, o pacote traz `discovery.py`, `inventory.py`, `topology` via
`investigation.py`, `privileges.py` (o que o token pode fazer), `redaction.py`, e
`verifier.py`. Há ainda `proxmox_backup_server` como integração separada.

O schema de credencial aceita dois caminhos, e a diferença importa:

| Campo | Formato | Observação |
|---|---|---|
| `api_token` | `user@realm!tokenid=segredo` | Uma linha, exatamente como o header quer. Separação de privilégio é propriedade do token. |
| `username` + `password` | `ninjasre@pve` + senha | Só para deployments que não conseguem emitir token. Trocado por ticket de 2h **do lado do proxy**. |
| `ticket`, `csrf_token` | — | Escritos pelo refresher, nunca por um operador. |

**Decisão para esta validação: token de API.** O caminho por senha existe para
quem não tem alternativa; usá-lo aqui trocaria uma credencial de longa duração
por uma renovação a cada duas horas, sem ganho.

## O token que o cluster precisa emitir

O `privileges.py` reporta o que o token consegue fazer, e a verificação diz o que
falta — mas é melhor acertar de primeira. Para a validação inicial o pedido do
usuário foi acesso a **todos os recursos e logs do cluster**, o que em termos de
Proxmox significa:

- papel com `Sys.Audit`, `Datastore.Audit`, `VM.Audit`, `SDN.Audit` e
  `Sys.Syslog` no caminho `/`, propagando;
- **sem** `VM.PowerMgmt`, `VM.Config.*` ou `Sys.Modify` neste primeiro momento —
  a plataforma entra observando. A escrita é decisão da 058 (política de
  autonomia), tomada depois de haver histórico para julgar.

Isso deve ser dito na tela: um token que não consegue ler `syslog` produz uma
investigação que não encontra a causa, e o momento de descobrir isso não é o
incidente.

## Escopo

### A. Onboarding do estate no assistente

Um passo que recebe o endpoint do cluster e a credencial, e imediatamente:

1. verifica a credencial contra a API do Proxmox;
2. **relata os privilégios que o token tem e os que faltam**, por nome, com o
   efeito de cada ausência descrito em uma frase;
3. roda a descoberta e mostra o que encontrou antes de gravar qualquer coisa.

O passo 3 é o que transforma isto de um formulário numa confirmação: o operador
vê "2 nós, 57 containers, 49 em execução, 7 zonas" e reconhece o próprio cluster.

### B. Descoberta e reconciliação

O `discovery.py` e o `inventory.py` já existem. Esta spec define o que fazer com
o resultado:

- todo guest vira um recurso do estate com nó, status, endereço e zona;
- a **zona vem da rede**, não de um palpite: os sete `/24` de
  `inventory/cluster/zones.yaml` mapeiam IP → zona sem ambiguidade
  (`10.20.20.0/24` = infra, `10.20.30.0/24` = apps, `10.20.40.0/24` = dmz, e
  assim por diante);
- a **reconciliação é periódica e a divergência é um sinal**: um container que
  aparece no Proxmox e não estava na varredura anterior é informação, não ruído.
  É a diferença entre um inventário e uma foto.

### C. A relação com o `infra-cluster`

O repositório em `/root/infra-cluster` tem 2.470 linhas de inventário estruturado
com JSON Schema, incluindo dois atributos que o Proxmox **não** sabe: `criticality`
e `tier`. Um container parado na zona `apps` com criticidade média e um parado na
zona `dmz` com criticidade alta são situações diferentes, e só o repositório sabe
qual é qual.

**A regra é: o Proxmox é a verdade sobre o que existe; o repositório é a verdade
sobre o que importa.** O NinjaSRE descobre do Proxmox e enriquece com o
inventário — nunca o contrário. Um recurso presente só no arquivo é um recurso
que não existe mais, e isso também é um achado.

Formato do enriquecimento: ingestão dos YAML por caminho ou URL, validados contra
os schemas que o próprio repositório publica em `inventory/schemas/`. Sem
acoplamento ao `./infra`, sem executar nada do repositório.

### D. Topologia

`GET /v1/topology/{node_id}` já existe e a tela `/topology` já renderiza. O que
falta é o grafo ser povoado: nó → zona → workload, com as arestas que o cluster
declara (um guest roda num nó; um serviço atende num domínio; uma zona tem um
gateway). O `services.yaml` traz o domínio Traefik de cada workload, que é a
aresta entre "o serviço que caiu" e "o container que o serve".

## Fora de escopo

- Qualquer escrita no cluster. Migração, start/stop e alteração de configuração
  ficam para depois da política de autonomia.
- Backup Server como integração separada — vale, mas depois de o estate básico
  estar de pé.
- k3s / vk8s. A zona existe e tem MTU 1450 documentado por um postmortem, mas o
  cluster Kubernetes é um segundo estate, não uma extensão deste.

## Aceitação

1. Um token com privilégio insuficiente é recusado no assistente com a lista
   nominal do que falta, e não com uma falha genérica.
2. A descoberta encontra 2 nós e 57 containers, e a contagem por zona bate com
   `inventory/cluster/cts.yaml` (infra 25, apps 21, dmz 7, ci 2, backup 1).
3. Cada recurso tem zona derivada do IP, e nenhum recurso fica sem zona.
4. Após enriquecimento, todo recurso com criticidade no repositório carrega essa
   criticidade; recursos presentes só no arquivo são reportados como divergência.
5. Uma segunda varredura depois de parar um container reporta a mudança de estado
   em vez de reescrever o recurso silenciosamente.
6. A topologia de um nó devolve seus guests, e o grafo liga serviço → workload.
