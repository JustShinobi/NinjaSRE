# 035 — The agent

A melhor tela do console: o diagrama de estágios com "o que consulta" por
estágio responde exatamente "o que é isso que eu instalei". Reparos pontuais.

## Problemas

### 1. [bloqueia entendimento] Budgets "0 / ceiling N" leem-se como zero

"What one run may spend: agents.max_iterations **0** (ceiling 20)" — o 0
significa "não configurado, vale o default", mas lê-se "zero iterações
permitidas". E `agents.tool_budget 0 (ceiling 0)` — teto zero? — parece dado
errado. Mostrar o **valor efetivo** (o default real do deployment), com "não
customizado" como anotação; investigar o ceiling 0 do tool_budget.

### 2. [polimento] Chaves cruas como rótulos

`agents.max_iterations`, `agents.max_parallel_subagents` — a tela já traduz
tanta coisa; traduzir também os rótulos (com a chave como metadado).

### 3. [polimento] Duplicações internas

- "The same topology, as the document" repete o empty state de specialists já
  mostrado acima na mesma aba.
- As abas Tools e Autonomy desta tela versus as telas Catalogue e Autonomy:
  sobreposição a resolver na spec 090 (proposta: esta tela absorve a *leitura*
  — o que o agente é/pode — e as telas de escrita ficam com a mudança).

### 4. [polimento] "deployment default — nobody bound this role" ×8

A tabela de roles repete a mesma linha oito vezes. Dizer *qual é* o default
(provider/modelo efetivos — o dado existe no first-run) em vez de só dizer que
ninguém o mudou.

## Critérios de aceite

- Nenhum budget renderiza 0 quando o efetivo não é zero.
- A tabela de roles mostra o modelo efetivo de cada role.
