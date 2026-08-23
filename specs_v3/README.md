# specs_v3 — de um deployment que roda para um deployment que se usa

Treze especificações, numeradas 050–062 na ordem em que o runner as executa —
que é a ordem das dependências, não a ordem em que foram escritas. Existem porque a
plataforma hoje roda num container de validação e **não pode ser configurada por
nenhuma superfície que uma pessoa procuraria**, e porque o primeiro estate ao
qual ela será apontada é um cluster Proxmox real de dois nós, cujo inventário,
stack de observabilidade e histórico operacional já estão escritos.

Tudo abaixo de "Evidências" foi medido contra o deployment em execução em
2026-08-10 — não inferido do código.

---

## A descoberta que ordena todo o resto

A lógica de onboarding existe e é boa. Ela é inalcançável.

`surfaces/cli/wizard/flow.py` implementa um primeiro-uso guiado em quatro passos
— provider, credencial no cofre, modelo, integrações, verificação — e é dirigido
por dados, não por uma lista fixa: cada provider declara seu próprio descritor
`ProviderOnboarding`, e cada uma das 91 integrações declara seu próprio schema de
credencial. Adicionar um fornecedor é um pacote, não uma edição.

Mas esse fluxo só roda quando a plataforma está **composta em processo**. No
instante em que um cliente fala HTTP — que é o que o console faz, e o que
`ninjasre --endpoint` faz — o `RemotePlatformClient` recusa quatro das chamadas
de que o fluxo depende, porque a API não as expõe:

| Chamada | Recusa em `surfaces/cli/client.py` | Estado real |
|---|---|---|
| `store_integration_credential` | "this surface has no credential-write route" | **Nenhuma rota existe.** Bloqueio duro. |
| `verify_provider` | "this surface has no provider route" | **Nenhuma rota existe.** Bloqueio duro. |
| `credential_fields` | "credential schemas are reachable per node, not per client" | `GET /v1/config/{node_id}/integration-schemas` **existe** — o cliente simplesmente não a usa. |
| `diagnose` | "this surface has no diagnostics route" | `GET /v1/setup/diagnostics`, `/self-check`, `/checklist` **todas existem** — o cliente não as usa. |

Ou seja: há **duas lacunas reais de API** (gravar uma credencial, e qualquer
superfície de provider) e **duas lacunas de fiação** sobre rotas que já existem.
É essa distinção que torna a spec 051 pequena em vez de grande.

O console, por sua vez, é uma superfície de observação completa e somente-leitura
— 14 telas em Operate, Estate, Learn e Govern — **sem um único formulário**. Isso
é deliberado e está documentado no próprio código (`administration.tsx`: *"a form
that posted nowhere would be worse than a sentence saying where it will live"*).
É honesto, e é também a razão de um operador entrar e não encontrar nada para
fazer.

## As especificações

Na ordem de execução:

| # | Spec | Depende de | Por que está aqui |
|---|---|---|---|
| [050](050-console-route-defects/spec.md) | Duas telas quebradas | — | `/catalogue` e `/autonomy` devolvem HTTP 500 hoje. A menor, e conserta algo que já deveria funcionar. |
| [051](051-onboarding-http-surface/spec.md) | A superfície HTTP de onboarding | — | Duas rotas faltando e duas não usadas. Nada avança sem isso. |
| [052](052-console-first-run/spec.md) | Primeiro uso no console | 051 | O assistente que o operador encontra. |
| [053](053-proxmox-estate-onboarding/spec.md) | O cluster Proxmox como primeiro estate | 051 | 2 nós, 57 containers, 7 zonas, já inventariados. |
| [054](054-observability-fabric/spec.md) | Ligar os sinais | 051, 053 | 9 serviços de observabilidade, todos alcançáveis, 6 com integração pronta. |
| [055](055-alert-ingress-first-investigation/spec.md) | Fechar o ciclo | 053, 054 | As rotas de webhook já existem. Nada chega nelas. |
| [056](056-operational-knowledge-corpus/spec.md) | A história escrita | — | 54 runbooks, 10 postmortems, 3 ADRs, política de firewall. |
| [057](057-code-and-deploy-as-signal/spec.md) | Código e deploy como sinal | 051, 053 | "O que mudou antes disso quebrar" não tinha resposta. |
| [058](058-configuration-write-surfaces/spec.md) | Configuração, depois do primeiro uso | 051 | Editar o que o primeiro uso estabeleceu: árvore de config, autonomia, tokens. |
| [059](059-team-operating-context/spec.md) | Contexto operacional da equipe | 058 | Fatos que o operador escreve uma vez e entram em toda investigação. |
| [060](060-agent-visible-and-tunable/spec.md) | O agente visível e ajustável | 058 | O que ele é, o que pode fazer, o que fará sozinho. |
| [061](061-proposed-changes/spec.md) | Mudanças propostas pelo agente | 056, 058, 059 | Onde "aprende a cada investigação" fica visível e reversível. |
| [062](062-data-ingress-and-delivery/spec.md) | Ingestão e entrega de dados | 051, 058 | De onde veio, para onde vai — a seção própria de trânsito. |

Leia 051 e 052 como um único trabalho. De 053 a 055 é a validação propriamente
dita, e cada uma vale ser entregue sozinha. A 050 vem primeiro por ser barata e
por deixar o console verde antes de qualquer coisa ser construída em cima dele.

As specs 057 e 060 foram acrescentadas depois das oito primeiras, ao conferir o
conjunto contra as quatro categorias de fonte que descrevem o propósito do
produto — **Production Systems, Observability, Knowledge, Code**. As três
primeiras estavam cobertas por 053, 054 e 056; **Code não estava coberta por
nada**, e é a categoria que responde à primeira pergunta que um SRE faz. A 060
veio da mesma conferência: nenhuma spec dava ao operador como responder "o que
esta coisa vai fazer sozinha".

As specs 059 e 061, e a revisão da 052, vieram de percorrer uma implementação
madura do mesmo problema instalada no cluster. Três correções saíram dali:

- **A 052 estava errada no modelo de entrada.** Ela mandava redirecionar para uma
  rota de primeiro uso, bloqueando o produto. O certo é dashboard sempre visível,
  tutorial dispensável por cima, e checklist persistente. Revisada.
- **Faltava contexto operacional aditivo** (059). O `AgentsConfig` só tem
  *substituir* o prompt de um papel. Um operador que precisa dizer "nossos
  containers são LXC e a métrica vem do host" hoje é forçado a copiar o prompt
  inteiro e congelá-lo.
- **Faltava a fila de propostas** (061). O agente já tem `knowledge_propose` e a
  plataforma já tem aprovações; o que não existe é o lugar onde uma melhoria
  espera decisão humana — e sem ele "aprende a cada investigação" não tem como
  virar mudança.

A mesma passagem melhorou a 060: `AgentsConfig` já modela a topologia inteira
como configuração, então aquela spec desenha o editor de um schema existente em
vez de modelar coisa nova.

---

## Evidências

### O deployment em execução

CT 254 (`ninjasre-py314-alpine`) no `pve02`, em `192.168.68.74`. Três serviços
OpenRC — aplicação na 8420, console na 8421, proxy de credenciais na 8422
(loopback), PostgreSQL 18 na 5432 (loopback). `/health/ready` reporta
`ready:true`, `store_state:healthy`, `migrations_current:true`, schema em
`0008_remediation_ledger`.

**O serviço chamado `console` não é o console web.** É a mesma aplicação ASGI
Python numa segunda porta. O console Next.js não é construído nem servido por
nenhum caminho de deploy — nem o fluxo de provisionamento LXC, nem o
`console.Dockerfile`, que é o mesmo wheel com outro entry point. Durante a
validação o console roda fora do container, apontando para a `:8420`.

### O que a API expõe

88 rotas. Completa para leitura: estate, topologia, incidentes, investigações com
streaming, runs, aprovações, remediação, detectores, autonomia, memória,
conhecimento, agendamentos, auditoria, identidade. Sete receptores de webhook já
existem — `alertmanager`, `grafana`, `datadog`, `pagerduty`, `opsgenie`,
`sentry`, `generic`.

Escritas que existem: `PUT /v1/config/{node_id}`,
`PUT /v1/autonomy/policy/{node_id}`, `POST /identity/tokens`, habilitar/desabilitar
detector, janelas de manutenção, fechar/suprimir incidente, CRUD de agendamento.

Escritas que não existem: **qualquer credencial**, e **qualquer operação de
provider**.

### O que o console renderiza

14 telas. `/configuration`, `/administration`, `/resources` e `/topology`
devolvem 200; `/catalogue` e `/autonomy` devolvem **500** — o cliente monta
`/v1/config/{node_id}/catalogue` e `/v1/autonomy/policy/{node_id}` sem substituir
`{node_id}` quando nenhum nó está selecionado.

O principal autenticado tem `owner` com as 31 permissões, incluindo
`config.write`. A permissão não é o motivo de nada ser editável; simplesmente não
existe editor.

### O cluster contra o qual isto será validado

Cluster `HAL9000`, Proxmox VE 9.2, dois nós, quorate 2/2.

| Nó | Endereço | Papel |
|---|---|---|
| `pve01` | 192.168.68.149 | primary |
| `pve02` | 192.168.68.159 | secondary |

57 containers, 49 em execução. Por zona: infra 25, apps 21, dmz 7, ci 2, backup
1. Por criticidade: alta 26, média 27. Sete zonas SDN, cada uma um `/24` com seu
próprio vnet — `mgmt`, `infra`, `apps`, `dmz`, `backup`, `ci` e `vk8s` (MTU
1450).

Observabilidade, toda na zona `infra`, toda no `pve01`:

| Serviço | Endereço | CT | Integração NinjaSRE |
|---|---|---|---|
| Prometheus | 10.20.20.37 | 137 | `prometheus` ✅ |
| Alertmanager | 10.20.20.36 | 136 | `alertmanager` ✅ |
| Grafana | 10.20.20.33 | 133 | `grafana` ✅ |
| Loki | 10.20.20.12 | 112 | `loki` ✅ |
| OpenObserve | 10.20.20.61 | 121 | `openobserve` ✅ |
| SigNoz | 10.20.20.62 | 111 | `signoz` ✅ |
| Blackbox exporter | 10.20.20.34 | 134 | via `prometheus` |
| PVE exporter | 10.20.20.35 | 135 | via `prometheus` |
| Gatus | 10.20.20.38 | 138 | **nenhuma** |
| NetBox | 10.20.20.19 | 119 | **nenhuma** |

Seis dos nove já têm integração construída. Gatus e NetBox não — ver 054 para se
isso importa.

### O repositório de infraestrutura

`/root/infra-cluster` no `pve02`. 621 MB, 15.880 arquivos, dirigido por OpenTofu,
com um único ponto de entrada `./infra` sobre componentes.

- `inventory/cluster/` — `nodes`, `cts`, `vms`, `services`, `zones`,
  `proxmox-backup-jobs`, cada um com JSON Schema em `inventory/schemas/`. 2.470
  linhas de estate estruturado: todo workload carrega zona, criticidade, IP
  primário, tags e seu domínio no Traefik.
- `docs/runbooks/` — 54 documentos.
- `docs/postmortem/` — 10, vários com diretórios de evidência.
- `docs/adr/` — 3.
- `policies/firewall/` — aliases de datacenter, ipsets, regras de cluster, perfis
  por workload.
- `services/` — 16 componentes, incluindo `monitoring`, `signoz`, `k3s`,
  `traefik`, `netbox`, `runners`.

Esse repositório é a razão de 053 e 056 serem baratas: o estate não precisa ser
descoberto do zero e a história operacional não precisa ser escrita.

---

## Restrições que estas specs herdam

- **Neutralidade de provider.** Nenhuma spec pode exigir um fornecedor de modelo
  específico.
- **Credenciais nunca saem do cofre.** O proxy de credenciais é o único
  portador; nenhuma rota, linha de log ou página renderizada pode carregar um
  segredo. A 051 é escrita em torno disso, não apesar disso.
- **Uma superfície somente-leitura é melhor que um formulário que não posta em
  lugar nenhum.** Onde uma spec adiciona um editor, ela adiciona a rota por trás
  dele, na mesma spec.
- **O estate é a fonte de verdade sobre si mesmo.** O NinjaSRE reconcilia contra
  o que o Proxmox reporta, não contra uma cópia do arquivo de inventário.
