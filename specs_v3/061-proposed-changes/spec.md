# 061 — Mudanças propostas pelo agente

**Depende de:** 058, 056, 059.

A plataforma promete melhorar a cada investigação. Esta spec é onde essa promessa
fica visível, revisável e reversível — em vez de acontecer sozinha ou não
acontecer.

## O que já existe

Mais do que eu supunha:

- `capabilities/tools/system/knowledge_propose/` — a ferramenta com que o agente
  **propõe** conhecimento novo. Propor, não gravar. A distinção já está no nome.
- `/v1/approvals`, `/v1/approvals/{id}`, `/v1/approvals/{id}/rollback` — o
  circuito de aprovação, hoje voltado a remediação.
- `POST /v1/config/{node_id}/preview` — o que uma mudança de configuração
  resolveria, antes de aplicá-la.
- `platform/memory/guidance.py` e `platform/knowledge/guidance.py` — a síntese
  que transforma episódios em orientação.

O que falta é a **fila** e a **tela**: um lugar onde tudo que o agente propôs
espera decisão humana.

## Por que isto é a peça que fecha o produto

Um sistema que aprende tem três desenhos possíveis, e dois são ruins:

1. **Aplica sozinho.** Rápido, e ninguém sabe por que a configuração de hoje é
   diferente da de ontem. Num cluster com 26 workloads de criticidade alta, é
   como se perde a confiança de uma vez.
2. **Não aplica nada.** Seguro e inútil: o aprendizado fica num relatório que
   ninguém releu.
3. **Propõe, com evidência, e espera.** É o único que produz melhoria acumulada
   *e* mantém alguém responsável.

O terceiro exige uma superfície. Sem ela, o desenho degenera no segundo.

## Escopo

### A. Uma fila de propostas

Toda proposta carrega, sem exceção: **o que mudaria**, **por quê**, **de qual
investigação veio**, e **o que muda em consequência**. Três origens:

| Origem | Exemplo neste cluster |
|---|---|
| Conhecimento | "esta investigação virou um procedimento que ainda não existe como runbook" |
| Contexto operacional (059) | "toda investigação de container LXC precisou aprender que a métrica vem do host — isto deveria ser fato declarado" |
| Configuração / detectores | "este sintoma apareceu três vezes; existe consulta de verificação que o pegaria antes" |

A terceira liga direto com a 056: as consultas de verificação do repositório de
infraestrutura já são candidatas a detector, e uma recorrência observada é a
evidência que justifica habilitar uma.

### B. Revisar é ver o efeito, não ler o texto

Aprovar sem ver a consequência é carimbar. Cada tipo mostra seu efeito com o
mecanismo que já existe:

- configuração → `POST /v1/config/{node_id}/preview`, o mesmo diff com
  proveniência da 058;
- detector → `POST /v1/detectors/{id}/dry-run`, o que ele teria disparado sobre
  o histórico real;
- conhecimento e contexto → o texto final, e onde ele passa a aparecer.

### C. Rejeitar é informação

Uma proposta recusada com motivo é sinal de treino: se a mesma proposta volta
três vezes e é recusada três vezes, ou o motivo não está sendo aprendido ou a
proposta está certa e o operador está errado. As duas conclusões são úteis, e
nenhuma é alcançável se a recusa for um botão sem campo.

### D. Aplicado é reversível

Uma proposta aprovada vira uma mudança com autor (`agente, aprovado por X`),
instante e reversão. O `POST /v1/approvals/{id}/rollback` já existe para
remediação; aqui vale a mesma garantia. Uma melhoria que não pode ser desfeita
não é uma melhoria, é um risco acumulado.

### E. Visível de onde se trabalha

Um contador de pendências no dashboard, junto com a checklist da 052. Uma fila
que só existe atrás de um item de menu é uma fila que cresce até alguém
descobri-la.

## Fora de escopo

- Aplicar proposta automaticamente, ainda que com alta confiança. Depois de
  haver histórico de aprovação suficiente para julgar — e essa decisão é da
  política de autonomia (058), não desta spec.
- Propor mudança em credencial. Nunca.
- Propor mudança no guardrail. É o arquivo que impede o resto; um agente que
  propõe afrouxar a própria contenção é exatamente o que não se quer.

## Aceitação

1. Uma investigação que descobre algo novo produz uma proposta com evidência e
   ligação para a investigação de origem.
2. Nenhuma proposta é aplicada sem aprovação humana explícita.
3. Aprovar uma proposta de configuração exige ver o preview; de detector, o
   dry-run.
4. Recusar exige motivo, e o motivo é recuperável na próxima proposta parecida.
5. Toda proposta aplicada é reversível e aparece na auditoria com agente e
   aprovador.
6. Propostas que toquem credencial ou guardrail são recusadas na origem.
