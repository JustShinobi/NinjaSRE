# A terceira janela — 2026-08-25, com o endpoint consertado

CT122 fora das 21:28:25Z às 21:32:51Z, **4 minutos e 26 segundos**. Desta vez a
parada foi provocada de um jeito que nenhum operador poderia ter feito pela
API: `kill -9` no init do convidado, a partir do host.

Versão medida: `gitops bc33825d716c`, `app` + `proxy` + `web`, três pods novos,
rotas aquecidas antes do passo destrutivo (a mais lenta 0,99s). Portão local
verde na árvore publicada: 12.778 passed / 31 skipped, mais 37 benchmarks.

## A parada é atribuível a defeito, e isso foi verificado

O log de tarefas do nó, para o convidado 122, imediatamente depois da parada:

    vzstart  OK  2026-08-25T19:34:00Z  root@pam
    vzstop   OK  2026-08-25T19:28:52Z  root@pam
    vzstart  OK  2026-08-24T20:19:03Z  root@pam

A tarefa mais recente é um **start**, de duas horas antes. Nada registra a
parada das 21:28. O convidado foi iniciado e está fora, e ninguém o derrubou
pela API — que é a assinatura que a janela anterior não conseguia produzir.

## O conserto do endpoint funciona no ambiente real

As duas capacidades que morriam em 501 três horas atrás:

| capacidade | janela das 19:28 | janela das 21:28 |
|---|---|---|
| `proxmox_guest_tasks` | FAILED (501) | **SUCCEEDED** |
| `proxmox_guest_start_diagnosis` | FAILED (501) | **SUCCEEDED** |

E o run ficou mais fundo: **nove** chamadas contra quatro, 52 segundos contra
21.

## E ainda assim nada foi proposto

`approvals` = 0 ao fim, igual ao marco zero.

A última chamada do run foi `assess_evidence_sufficiency`, e o que o agente
declarou nela é o registro que importa:

```json
"sufficient": true,
"missing_evidence": [],
"conclusion": "LXC container 122 (redis) on node pve01 was stopped. There are
               no blocking locks, datastore unreachable errors, or insufficient
               resources preventing it from running."
```

Evidência suficiente. Nada faltando. Nada impedindo o convidado de rodar. E
`proxmox_start_guest` estava entre as 40 capacidades oferecidas — 20ª, escore
0,625, lido da gravação do próprio run.

**O agente concluiu e parou.** Não chamou a capacidade que desfaz o estado.

## O que esta janela elimina

Cada explicação anterior para o zero foi agora derrubada por medição, e as
quatro estão registradas nesta onda:

| explicação | como foi eliminada |
|---|---|
| "o catálogo não tem ação de infraestrutura" | tem 24 capacidades de escrita, 20 de remediação |
| "o escorador corta a ação por causa do idioma" | corrigido; oferecida em 20ª de 40, duas janelas seguidas |
| "a evidência do motivo não chega" | endpoint consertado; as duas leituras passaram |
| "a parada parece manutenção deliberada" | provocada sem registro de tarefa nenhum |

**O que sobra é o passo entre concluir e propor.** A mesa de remediação está
composta — foi ela que permitiu as ações de escrita passarem por `_can_carry`
antes do ranqueamento. A maquinaria abaixo está provada por teste: 33 contratos
em `test_proposed_action_decision.py`, incluindo a recusa de aprovar sem plano
de reversão armazenado. O que nenhuma medição em ambiente real mostrou até
agora é uma investigação **chamando** uma capacidade de escrita.

Dito com o cuidado que o achado merece: o que está medido é que a capacidade
foi oferecida, que o agente declarou evidência suficiente, que ele não a
chamou, e que nenhuma linha de aprovação existe. O que **não** está medido é o
que aconteceria se ele a chamasse — esse caminho continua provado só por teste.

## Telas

Em `telas/`, full-page a 1920, contra o staging real.

| arquivo | o que se lê |
|---|---|
| `incident-detail.png` | o incidente `inc_b1154a0f1f183107` e o painel de ação proposta |
| `run-detail.png` | as nove chamadas, com as duas que agora passam |
| `decisions.png` | a fila de decisões, vazia |

## Segredos

Nenhum token, chave, senha ou credencial neste arquivo, nas telas ou nas
consultas.
