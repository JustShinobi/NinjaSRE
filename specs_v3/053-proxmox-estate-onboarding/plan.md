# Plano — 053 O cluster Proxmox como o primeiro estate

## O que existe, verificado contra o código

A afirmação da spec que esta feature é barata se sustenta:

- **Discovery**: `integrations/proxmox/discovery.py::ProxmoxDiscovery.discover`
  (linha 210) enumera cluster → nodes → guests → detalhe em passos encenados, orçados,
  resumíveis; `tests/benchmarks/test_proxmox_sweep_budget.py` já
  prova que um cluster de dois-nós, cinqüenta-guests varre dentro de seu orçamento de chamada —
  quase exatamente a forma do HAL9000.
- **Reconciliação**: `platform/estate/discovery/reconcile.py::reconcile`
  maneja atualizações vs duplicatas, correlação de duas-fontes, movimentos de pai, e
  reutilização de identificador; `sweep` (`platform/estate/discovery/sweep.py:127`, 30
  chamadores) faz suspensão/retomada, marcação de ausência com o
  limite `since`, e reportagem por-sweep. **Aceitação 5 ("um container parado é
  uma mudança de estado, não uma reescrita") é comportamento existente** — o modelo
  de saúde de estate registra transições; a tarefa aqui é um teste contra o
  caminho Proxmox, não um mecanismo.
- **Privilégios**: `integrations/proxmox/privileges.py::privilege_report`
  retorna suficiência de leitura/escrita separadamente com cada falha nomeada com seu
  caminho e uma frase `grants`, mais `GRANTED_AT` dizendo ao operador onde
  corrigi-lo. `to_record()` está pronto para console. A substância de Aceitação 1 existe;
  o que falta é a superfície que a mostra. Nota a lista de privilégio da spec vs a do código: `READ_PRIVILEGES` requer `Sys.Audit /`,
  `VM.Audit /vms`, `Datastore.Audit /storage`. A spec também nomeia
  `SDN.Audit` e `Sys.Syslog`. Esses dois são adicionados a `READ_PRIVILEGES`
  nesta feature (topologia de zona precisa de leitura de SDN; ferramentas de leitura de log precisam
  de syslog), com `capabilities` nomeando o que cada um desbloqueia — o mecanismo que
  mantém a lista honesta (docstring de `WRITE_PRIVILEGES`: afirmada contra
  declarações de capacidades) se aplica às adições.
- **Inventário declarado**: `integrations/proxmox/inventory.py` ingere
  uma lista de node/guest declarada pelo operador como uma *segunda fonte*
  (`INVENTORY_SOURCE = "proxmox_inventory"`, reconciliada em vez de
  sobrescrever, relida a cada `INVENTORY_INTERVAL_SECONDS = 900`). Este é
  o ponto de costura que o enriquecimento do infra-cluster estende — é deliberadamente não a
  visualização ao vivo, que é o "Proxmox é a verdade sobre o que existe" da spec.
- **Topologia**: `NodeKind.RESOURCE`, `EdgeKind.HOSTED_ON` existem (feature de
  estate); `GET /v1/topology/{node_id}` e `/topology` renderizam.

O que não existe: derivação de zona do IP, enriquecimento de criticality/tier
a partir do YAML de infra-cluster, o relatório de divergência, o traefik-domain →
workload edge, e o passo do wizard.

## Escopo A — o passo de estate no wizard

Um passo no wizard de 052 (o console possui a renderização; esta feature possui as
rotas e os comportamentos):

1. Credencial via `PUT /v1/integrations/proxmox/credential` de 051
   (`api_token` field — a decisão que a spec fixa; o caminho username/password
   permanece disponível mas não é o padrão do wizard).
2. Relatório de privilégio via o verifier: `integrations/proxmox/verifier.py`
   já chama `privilege_report`; a lacuna é expor seu `to_record()`
   através da resposta de verify. `POST /v1/integrations/proxmox/verify` hoje
   retorna apenas o estado de credencial (`gateway/http/routes/integrations.py:90` —
   presente/current/decryptable); esta feature adiciona um *deep verify opcional*
   (`?deep=true` ou uma rota `/verify/report` separada — decisão abaixo) que
   executa o próprio verifier da integração e retorna o relatório de privilégio.
3. **Preview antes de commit**: uma nova rota `POST /v1/estate/discovery/preview`
   que executa `ProxmoxDiscovery.discover` e retorna contagens (nodes, guests,
   em execução, zonas uma vez derivadas) *sem* chamar `sweep` — nada armazenado.
   O wizard mostra "2 nodes, 57 containers, 49 em execução, 7 zonas" e o
   operador confirma; confirmação registra a fonte de discovery então o
   scheduled sweep (`platform/estate/discovery/schedule.py`) assume.

**Decisão — deep verify é uma rota separada**,
`POST /v1/integrations/{name}/verify/report`, em vez de uma flag: o shallow
verify é barato e seguro chamar de qualquer tela; o profundo faz chamadas
ao vivo de vendor e retorna um documento maior, e dois comportamentos atrás de uma
rota com flag é como uma tela acidentalmente faz a chamada cara.
Se generaliza: qualquer integração cujo verifier produz um relatório (054 precisa
exatamente disto) o serve aqui.

## Escopo B — zona da rede

Zonas são dados declarados ingeridos do repositório de infra-cluster
(`inventory/cluster/zones.yaml`: sete `/24`s com nomes, o MTU `vk8s`),
validados contra o JSON Schema publicado do repositório. Implementação:

- Um valor `ZoneMap` em `platform/estate/` — CIDR → nome de zona, construído a partir da
  declaração ingerida, função total `zone_for(ip) -> str | ""`.
- Aplicado no tempo de enriquecimento (abaixo), nunca adivinhado: um recurso cuja
  IP primária não combina com CIDR declarada alguma não carrega zona *e aparece no relatório de
  divergência* (aceitação 3 diz que nenhum recurso pode acabar sem zona contra este
  cluster — o teste afirma zero sem correspondência na fixture HAL9000, e o
  mecanismo reporta em vez de ocultar qualquer não-correspondência futura).
- Zona aterrissa como um atributo de recurso (`zone`) mais um label, então `/resources`
  pode agrupar e filtrar por ela (D3 §3: agrupado por zona, ordenado por criticality).

## Escopo C — enriquecimento do repositório de infra-cluster

Uma nova ingestão ao lado do inventário declarado existente, não uma substituição:
`integrations/proxmox/enrichment.py` (ou lado-plataforma se se provar
neutro a provider — veja decisão) lê `nodes`, `cts`, `vms`, `services`,
`zones` YAML por caminho ou URL, valida contra os schemas que o repositório
publica em `inventory/schemas/`, e produz:

- atributos por-guest `criticality` e `tier`, combinados por VMID;
- o traefik domain por workload (de `services.yaml` /
  `tags: host-*.kyo.ninja`), armazenado como um atributo e usado por Escopo D;
- o `ZoneMap` do Escopo B;
- um **relatório de divergência**: recursos presentes apenas no arquivo (idos de
  Proxmox — "não existe mais, e isso é um achado"), recursos em Proxmox
  ausentes do arquivo, criticality declarado para um VMID que Proxmox não
  reporta. Divergência é *conteúdo*: é armazenado com o relatório de sweep e
  renderizado em `/resources` como uma linha marcada, nunca um alerta e nunca dropado
  (D3 §3: "Divergência é conteúdo, não erro").

**Decisão — o módulo de enriquecimento vive em `integrations/proxmox/`**, não
`platform/estate/`. Os formatos de arquivo são deste repositório (VMID-chaveado,
formato Proxmox); um segundo estate traria sua própria fonte de enriquecimento. As
metades genéricas — `ZoneMap`, as formas de registro de divergência — vão em
`platform/estate/enrichment.py` então uma futura fonte NetBox (054 registra a
lacuna) reutiliza. A direção de verdade é forçada em código: enriquecimento pode
apenas *anotar* recursos que a fonte ao vivo reportou; nunca cria um
(a costura `INVENTORY_SOURCE` já possui essa propriedade — reconciliada, não
sobrescrita).

**Decisão — transporte de ingestão é path-or-URL, somente-leitura, sem execução `./infra`.** O campo do wizard toma um caminho de diretório (o CT pode montar ou
buscar) ou uma URL HTTPS para os arquivos brutos do repo. Nada do
repositório é executado, e apenas `inventory/cluster/*.yaml` é lido — a
regra de secret-sweep de 056 se aplica aqui também (o enriquecimento tela cada
string ingerida através do ruleset de guardrail antes do armazenamento, reutilizando
`platform/estate/attributes.screened`, que já existe para exatamente
isto).

## Escopo D — preenchimento de topologia

Depois de um sweep + enriquecimento, o gráfico de topologia ganha:

- node → guest: `HOSTED_ON` (existe — escrito pelo manuseio de pai da reconciliação);
- nós de zona e guest → edges de membros de zona (novo uso de edge, maquinário
  `upsert_edge` existente);
- service → workload: um edge do traefik domain (um nó de serviço) para o
  guest que o serve, de `services.yaml`. Este é o edge que 055 usa para
  resolver alertas de blackbox.

O teste de Aceitação 6 dirige `GET /v1/topology/{node_id}` para um node e
afirma que seus guests retornam, e um domain se resolve para seu workload.

## O que esta feature NÃO faz

- Sem escritas no cluster — `WRITE_PRIVILEGES` permanecem declaradas-mas-não-requeridas
  (a postura somente-leitura da docstring do módulo é a postura desta spec).
- Sem integração de Proxmox Backup Server, sem segundo estate k3s/vk8s.
- Sem integrações de observabilidade (054), sem resolução de alerta (055 — ela
  *consome* o mapa de zona e domain edges construído aqui).
- Sem telas de console além do passo do wizard e da marcação de divergência em
  `/resources`; a agregação de detalhe de recurso "o que se sabe sobre isto" é
  054/056/057 preenchendo progressivamente painéis que existem.

## Verificação de constituição

- **I** — o relatório de privilégio e relatório de divergência ambos nomeiam sua
  evidência (caminho concedido, arquivo vs API); a preview mostra o que discovery
  realmente encontrou antes de qualquer coisa ser armazenada.
- **II** — discovery já é orçado (`_Spend`, cursor encenado);
  ingestão de enriquecimento ganha seus próprios limites em `config/constants/estate.py`
  (tamanho máximo do arquivo, entradas máximas) como constantes nomeadas.
- **III** — token somente-leitura por design; a tela de privilégio do wizard declara
  o que um token capaz de escrita *adicionaria* e não pede por ele.
- **IV** — o token vai através da rota de 051 para o vault; discovery não
  segura credencial (`test_the_sweep_module_imports_nothing_from_the_credential_layer`
  já afirma isto).
- **VIII** — enriquecimento em tier 2 (`integrations/proxmox/`), formas genéricas
  em tier 3 (`platform/estate/`), sem imports para cima.
- **XI** — tudo através de portas `EstateRepository` / topology.
- **XII** — teste-primeiro por módulo; as contagens HAL9000 (2 nodes, 57 CTs,
  contagens de zona infra 25 / apps 21 / dmz 7 / ci 2 / backup 1) se tornam um
  dataset de fixture, e a execução de cluster ao vivo é registrada em deviations, não no
  gate (a postura chaos/e2e: um gate que precisa de um cluster é um gate que pessoas
  pulam).
