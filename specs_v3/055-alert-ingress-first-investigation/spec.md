# 055 — Fechar o ciclo

**Depende de:** 053, 054.

Tudo antes disto é preparação. Esta spec é a primeira vez que o cluster acorda a
plataforma sozinho.

## O que já existe

Sete receptores de webhook, montados e roteados:

```
POST /webhooks/alertmanager      POST /webhooks/grafana
POST /webhooks/datadog           POST /webhooks/pagerduty
POST /webhooks/opsgenie          POST /webhooks/sentry
POST /webhooks/generic
```

Os dois primeiros são exatamente os sistemas que este cluster tem. **Nada aponta
para eles.** O Alertmanager em 10.20.20.36 tem seus próprios receivers
configurados pelo `infra-cluster`; o NinjaSRE não é um deles.

Do outro lado, `POST /v1/investigations` cria uma investigação,
`GET /v1/investigations/{run_id}/stream` a transmite, e as telas `/runs` e
`/incidents` já renderizam. O caminho existe inteiro. Falta o começo.

## Escopo

### A. Um receptor que o cluster possa apontar

Emitir, no console, o que o operador precisa colar na configuração do
Alertmanager: URL, token e o formato esperado. O token é um token de máquina
comum (`POST /identity/tokens`) com permissão mínima — receber alerta não é
permissão de investigar tudo.

A configuração fica do lado do `infra-cluster`, aplicada pelo `./infra`. O
NinjaSRE **não** escreve na stack de observabilidade — é a mesma regra da 054.

### B. Do alerta ao recurso

Um alerta do Alertmanager chega com labels. Esta spec define como eles viram um
recurso do estate:

- `instance` / `host` → endereço → zona pelo `/24` → recurso, pela descoberta do
  053;
- alerta do `pve-exporter` traz o VMID, que é a chave direta do guest;
- alerta do blackbox traz o alvo, que é um domínio, que o `services.yaml` liga ao
  workload.

**Um alerta que não resolve para um recurso não é descartado.** Ele vira um
achado — "chegou alerta para um alvo que não conheço" é informação sobre o estate,
não lixo. É o mesmo princípio da divergência de reconciliação em 053.

### C. Deduplicação e agrupamento

O Alertmanager já agrupa. A plataforma não pode desfazer isso abrindo uma
investigação por notificação: um `resolved` seguido de `firing` do mesmo grupo é
um evento, não dois. A correlação é por fingerprint do grupo mais recurso, com
janela.

Este cluster já provou por que isso importa: o postmortem de OOM recorrente do
AdGuard e o de tempestade de logs do ClickHouse são ambos falhas que geram muitas
notificações do mesmo problema.

### D. O primeiro investigar de verdade

O objetivo mensurável desta spec: **um alerta real do cluster produz uma
investigação que cita evidência de mais de uma fonte.**

Concretamente, uma investigação sobre um container sob pressão deve reunir:
estado do guest (Proxmox), métrica do host por VMID (Prometheus/pve-exporter),
linhas de log da janela (Loki ou OpenObserve), e o que já se escreveu sobre
aquele recurso (056). Quatro fontes, uma conclusão, cada afirmação com origem.

Esse é o teste da tese do produto. Se a investigação não conseguir juntar as
quatro, o problema não é o prompt — é o mapa de sinal da 054 ou o estate da 053,
e é melhor descobrir isso aqui.

### E. Modo proposta antes de modo ação

O primeiro ciclo termina numa proposta, não numa remediação. `dry-run` da
política de autonomia (058) fica ligado, e o registro do que a plataforma *teria*
feito é o material para decidir o que ela pode fazer sozinha depois.

Um cluster de casa com 26 workloads de criticidade alta não é lugar para
descobrir que a política estava larga demais.

## Fora de escopo

- Remediação automática. Depois de haver histórico.
- Integração com chat. Existe no catálogo; não é necessária para fechar o ciclo.
- Agendamento de investigações periódicas. As rotas existem; valem depois de o
  ciclo reativo funcionar.

## Aceitação

1. Um alerta disparado de propósito no Alertmanager do cluster chega ao NinjaSRE
   e cria uma investigação em menos de um minuto.
2. O alerta resolve para o recurso certo do estate, e um alerta com alvo
   desconhecido produz um achado em vez de silêncio.
3. Um `firing` seguido de `resolved` do mesmo grupo não produz duas
   investigações.
4. A investigação resultante cita evidência de pelo menos três fontes distintas,
   cada afirmação atribuída à sua origem.
5. Toda remediação proposta fica registrada como proposta, e nada é executado com
   dry-run ligado.
6. A investigação inteira é reproduzível por `GET /v1/runs/{run_id}/replay`.
