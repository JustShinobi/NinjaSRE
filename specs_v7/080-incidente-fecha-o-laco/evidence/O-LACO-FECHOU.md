# O laço fechou — 2026-08-26, 00:53:37Z

A primeira vez que este produto propôs uma remediação, um operador a aprovou
olhando, e o portão a executou. Sete janelas contra a CT122 e seis consertos de
produto para chegar aqui.

## A prova, em quatro fatos que qualquer um confere

```
approvals              2      a primeira proposta que este deployment já escreveu
rollback_plans         2      nenhuma aprovação é aceita sem plano armazenado
remediation_outcomes   1      executed_at 00:53:40, signal proxmox.guest.running
vzstart OK   2026-08-26T00:53:37Z     no hipervisor, pelo token do deployment
```

A decisão foi gravada às **00:53:37.308** e o `vzstart` no hipervisor às
**00:53:37**. O mesmo segundo. Não foi ninguém religando o convidado à mão: foi
o portão levando a decisão até o efeito.

## A cadeia, oito elos

Cinco explicações para o zero caíram por medição antes de a verdadeira aparecer.
Cada uma era verdadeira a respeito de algo; nenhuma era a causa.

| # | elo | como estava | conserto |
|---|---|---|---|
| 1 | o catálogo tem ação de infraestrutura | **já tinha** — 24 de escrita, 20 de remediação | — |
| 2 | o escorador oferece a ação certa | 0,0000 e 57ª contra alerta em português | regra reescrita em inglês → 1,8182 e 7ª |
| 3 | a evidência do motivo chega | 501 num endpoint que **nunca existiu** na API | `/nodes/{node}/tasks?vmid=` |
| 4 | a parada é atribuível a defeito | um `pct stop` é sempre deliberado | `kill -9` no init, sem registro de tarefa |
| 5 | o agente sabe que pode propor | prompt de sub-agente: "descubra e diga o que significa" | prompt próprio da investigação |
| 6 | a proposta consegue nascer | a sonda de conflito ia sem argumentos e levantava **dentro** da criação da aprovação | o payload viaja até a sonda |
| 7 | a proposta consegue ser achada | `run_id` sintético (`remediation:pve01`) | a linha carrega o run que propôs |
| 8 | a proposta consegue ser decidida | o cartão só falava com *interação*, e remediação não levanta uma | cai para o controle de aprovação |

**Onde a causa real foi encontrada**: no log do processo, no instante da falha.
As cinco anteriores vieram de leitura de código e contagens, e nenhuma acertou.

## O que foi consertado e está publicado

Seis consertos de produto, cada um com o vermelho confirmado antes, portão
completo verde e publicado em staging:

- **Proxmox**: histórico de tarefas lido do endpoint que existe
- **Investigação**: o agente que serve é informado de que propor faz parte
- **Aprovações**: a sonda de conflito recebe os argumentos que nomeiam o alvo
- **Aprovações**: a mudança é guardada sob o run que a propôs
- **Aprovações**: o prazo é cobrado pelo relógio, não pelo rótulo
- **Console**: `/decisions` deixa decidir o que ela pede para decidir

Mais dois de outras features, achados no caminho:

- **Identidade**: a porta do primeiro administrador sob trava de transação
  (a prova que existia rodava contra um fake que não tinha como falhar)
- **Verificação**: a frase de recusa em claro chega ao operador, em 15 vendors

E um mecanismo novo:

- **Runs**: o gateway fecha, ao subir, os runs cujo processo morreu. Na primeira
  subida fechou **nove**, um deles preso havia três dias.

## O que continua aberto, dito sem maquiagem

**A verificação nunca corre.** O desfecho está `awaiting_verification` desde
00:55. Nenhum job agendado lê o `due_at`. O produto executa remediações e não
confirma que adiantaram — que é metade do que "laço fechado" significa.
Diagnosticado, não construído.

**`episodes` = 0.** O laço fechou e nenhum episódio foi gravado. Não apurado.

**A rejeição nunca foi exercitada.** Nenhuma proposta foi recusada com motivo.

**11 caixas seguem abertas** nos ledgers das features 040, 060 e 080. As sete da
080 descrevem uma demonstração contínua, e o que houve foram sete janelas
entremeadas de conserto. Uma passagem limpa de ponta a ponta as marcaria de uma
vez — e agora ela é possível, o que não era ontem.
