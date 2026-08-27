# 024 — Knowledge

Mesma família da Memory: estrutura sã, reparos pequenos.

## Problemas

### 1. [bloqueia entendimento] "Configure ingestion" sem destino claro

O CTA principal do empty state não diz para onde vai nem o que "ingestão"
envolve (upload? apontar para um repositório? colar texto?). Para o operador
de primeira viagem, esta é a tela em que ele traria seus runbooks — o caminho
precisa estar desenhado: o que pode ser ingerido, de onde, e o que o agente
faz com isso.

### 2. [polimento] Painel "Proposed by an agent" duplica a fila de Proposals?

"When an investigation learns something worth writing down it proposes the
change here rather than making it." — existe também a tela Proposed changes
para propostas do agente. Se são filas distintas (documentos vs configuração),
os textos precisam dizer isso; se é a mesma fila filtrada, é mais um argumento
para o inbox único de decisões (spec 090).

### 3. [polimento] Filtro "Kind: Any" único; dois painéis de vazio empilhados

Mesmos reparos da spec 023.

## Critérios de aceite

- O caminho de ingestão está descrito na própria tela (o que, de onde, como).
- A relação entre "Proposed by an agent" e Proposed changes está explícita.
