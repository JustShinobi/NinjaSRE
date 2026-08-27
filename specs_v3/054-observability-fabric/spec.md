# 054 — Ligar os sinais

**Depende de:** 051, 053. **Bloqueia:** 055.

O estate diz o que existe. Esta spec diz como está.

## O que está lá, e o que já temos para falar com cada um

Nove serviços de observabilidade, todos na zona `infra`, todos no `pve01`, todos
alcançáveis a partir do CT 254.

| Serviço | Endereço | O que ele responde | Integração |
|---|---|---|---|
| Prometheus | 10.20.20.37 | métricas de tudo, via exporters | `prometheus` ✅ |
| Alertmanager | 10.20.20.36 | o que está disparando agora | `alertmanager` ✅ |
| Grafana | 10.20.20.33 | painéis e as queries por trás deles | `grafana` ✅ |
| Loki | 10.20.20.12 | logs | `loki` ✅ |
| OpenObserve | 10.20.20.61 | logs e traces | `openobserve` ✅ |
| SigNoz | 10.20.20.62 | traces OTLP, gateway de coleta | `signoz` ✅ |
| PVE exporter | 10.20.20.35 | CPU, memória, disco, rede, load dos guests | via `prometheus` |
| Blackbox exporter | 10.20.20.34 | disponibilidade externa | via `prometheus` |
| Gatus | 10.20.20.38 | health checks sintéticos | **nenhuma** |

Seis integrações prontas. **Nenhuma delas foi escrita para este cluster** — são
integrações de catálogo, e o valor de validar aqui é justamente descobrir onde
uma integração genérica encontra um ambiente real.

## O detalhe que muda a estratégia de coleta

Do `services/signoz/README.md` do repositório de infraestrutura, sobre o perfil
padrão de um CT:

> CPU, memória, disco, rede, load e paging de capacidade são obtidos
> exclusivamente do `pve-exporter`, porque LXC compartilha o kernel do host e não
> fornece todos [os contadores].

Isto não é um detalhe de configuração — é uma regra de correção. **Uma
investigação que perguntar "qual era o uso de memória deste container" ao agente
dentro do container recebe um número errado.** A resposta certa vem do
`pve-exporter`, pelo Prometheus, indexada pelo VMID.

O NinjaSRE precisa saber disso. Consequência concreta: para um recurso do tipo
container LXC, as ferramentas de pressão de recurso consultam métricas do host
com o VMID como chave, e não métricas coletadas de dentro. O `guest_pressure` da
integração Proxmox já toma esse caminho; o que falta é a mesma regra valer quando
o sinal vier do Prometheus.

Um postmortem do próprio cluster (`2026-07-20-adguard-dns-recurrence-memcg-oom.md`)
é sobre OOM de cgroup de memória — exatamente a classe de problema que se
diagnostica errado olhando o lugar errado.

## Escopo

### A. Onboarding dos seis, dirigido pelo estate

No assistente, depois da descoberta do estate: as integrações relevantes vêm
primeiro, e "relevante" é derivado, não digitado. O estate descoberto contém um
container chamado `prometheus` na zona infra; a integração `prometheus` é
oferecida com o endereço já preenchido.

Isso é possível porque a descoberta do 053 acontece antes, e é a razão da ordem
dos passos.

### B. Um mapa de sinal por recurso

Para cada recurso do estate, registrar qual serviço responde a qual pergunta:

| Pergunta | Fonte para esta validação |
|---|---|
| está de pé? | Proxmox (estado do guest), Gatus (sintético) |
| está sob pressão? | Prometheus via `pve-exporter`, **por VMID** |
| o que ele registrou? | Loki, OpenObserve |
| o que ele chamou? | SigNoz (OTLP), para os CTs instrumentados |
| o que está disparando? | Alertmanager |
| o que um humano olha? | Grafana |

Esse mapa é o que evita a investigação que consulta a fonte errada e conclui com
confiança um número que não significa o que parece.

### C. Verificação que investiga, não que faz ping

`POST /v1/integrations/{name}/verify` hoje reporta credencial presente e legível.
Para observabilidade isso é fraco demais. A verificação precisa responder:

- a consulta autenticou;
- **retornou séries/linhas para uma janela recente** — um Prometheus que responde
  200 com resultado vazio está tão inútil quanto um fora do ar, e é bem mais
  difícil de perceber;
- o relógio da fonte bate com o da plataforma dentro de uma tolerância. Existe
  ferramenta de `clock_skew` na integração Proxmox pelo mesmo motivo, e uma
  janela deslocada faz correlação temporal mentir.

### D. Gatus e NetBox: a decisão

Nenhum dos dois tem integração. Recomendação:

- **Gatus — não construir agora.** Ele responde "está de pé", que Proxmox e
  blackbox exporter já respondem por dois caminhos. Duplicar é custo sem sinal
  novo.
- **NetBox — não construir agora, mas registrar.** É fonte de verdade de rede e
  endereçamento, e essa informação já chega pelo `zones.yaml` e pelo próprio
  Proxmox no 053. Vira valioso quando o estate crescer para além do que o
  inventário do repositório cobre.

Ambos ficam registrados como lacuna conhecida, com o motivo. Uma lacuna com
motivo escrito é diferente de uma esquecida.

## Fora de escopo

- Alterar a stack de observabilidade do cluster. O NinjaSRE lê; o `infra-cluster`
  é dono dela.
- Instrumentar aplicações com OTLP.
- Ingestão de métricas para dentro do NinjaSRE. Ele consulta na origem; um
  segundo armazenamento de séries temporais seria um segundo lugar para os
  números discordarem.

## Aceitação

1. As seis integrações verificam contra os endereços reais e cada verificação
   devolve dado de uma janela recente, não apenas 200.
2. Consultar pressão de recurso de um container LXC usa métrica do host por VMID,
   e um teste prova que não usa métrica coletada de dentro do guest.
3. Cada recurso do estate resolve para pelo menos uma fonte de "está de pé" e uma
   de "o que registrou".
4. Uma fonte com relógio deslocado além da tolerância é reportada como degradada
   na verificação, com o desvio medido.
5. Gatus e NetBox aparecem como lacunas conhecidas com o motivo, não como
   ausências silenciosas.
