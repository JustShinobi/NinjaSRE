# 013 — Approvals

Mecanicamente sã; o problema é de identidade dentro do produto.

## Problemas

### 1. [bloqueia entendimento] Dois inboxes quase sinônimos

O sidebar tem **Approvals** (grupo Now) e **Proposed changes** (grupo
Settings). Ambos são "coisas esperando um humano decidir". A distinção real —
"pode o agente fazer isto agora" vs "o deployment deveria ser diferente de
amanhã em diante" — é boa, mas está enterrada em dois nomes que não a
comunicam e em dois lugares diferentes do menu. Nenhuma das duas telas
menciona a existência da outra.

Correção mínima (sem mudar rotas): cada tela ganha uma linha apontando a
outra ("Procurando mudanças de configuração propostas pelo agente? Estão em
Proposed changes"), e os nomes se afastam ("Approvals" → "Ações aguardando
aprovação"). A correção estrutural está na spec 090 (fusão em um inbox de
decisões com duas abas).

### 2. [bloqueia entendimento] O vazio não diz como algo chegaria aqui

"A change that needs a person appears here with its blast radius and its
rollback plan. None does." — correto, mas neste deployment o threshold de
aprovação nem está configurado (`policies.approvals`: "Set at nothing yet").
Como em Incidents: o empty state deveria dizer qual regra alimenta a fila e
seu estado atual ("hoje, tudo acima de read_sensitive exige aprovação — regra
padrão").

### 3. [polimento] CTA duplicado na árvore de acessibilidade

"See what is running" duas vezes (mesmo padrão das outras telas de empty
state).

## Critérios de aceite

- Um leitor que abra Approvals e Proposed changes em sequência consegue dizer,
  pelas telas, qual fila serve para quê.
- O empty state cita a regra ativa que alimenta a fila.
