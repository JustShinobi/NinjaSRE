# 034 — Proposed changes

## Problemas

### 1. [quebrado] O endpoint não responde

A tela renderiza apenas: *"This panel could not be filled — `/v1/proposals`
did not answer"*. Reproduzível a cada visita. É uma das telas "que não
funcionam" do feedback original. Diagnosticar o gateway (rota ausente?
permissão? erro interno) e cobrir com teste de contrato — o padrão da spec_v3
050 ("nenhuma tela responde 500 por dependência; o erro é do painel") foi
seguido na forma, mas a causa segue viva.

### 2. [bloqueia entendimento] Nome da tela vs rota vs conceito

Sidebar: **Proposed changes**; rota: `/proposals`; empty states de outras
telas dizem "proposes the change here". Unificar o nome (e ver spec 013/090
sobre a fusão com Approvals num inbox de decisões).

### 3. [a fazer junto da correção] O vazio real precisa do mesmo padrão das demais

Quando o endpoint voltar, o empty state deve explicar de onde nasce uma
proposta (investigação que aprende algo → propõe mudança de config/knowledge)
e em que estado do deployment isso é possível.

## Critérios de aceite

- `/v1/proposals` responde e a tela lista (ou mostra vazio saudável).
- Teste de contrato cobrindo a rota.
- Um único nome para o conceito em sidebar, título e textos de outras telas.
