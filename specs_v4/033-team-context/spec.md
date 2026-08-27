# 033 — Team context

Conceito bom (fatos do ambiente que entram no prompt de toda investigação),
execução com arestas.

## Problemas

### 1. [quebrado] Links corridos sem pontuação

"…where it is auditable and reversible. **Runbooks live in Knowledge
Procedures live in Autonomy**" — duas frases-link coladas sem separador,
lendo-se como uma frase sem sentido. Separar ("Runbooks vivem em Knowledge ·
Procedimentos vivem em Autonomy").

### 2. [bloqueia entendimento] O editor não se explica

- "Section name" + "Add a section" sem exemplo do que é uma seção boa (o
  próprio texto da página tem um ótimo exemplo — "Container metrics come from
  the host, by vmid" — que deveria estar como placeholder/exemplo aplicável).
- **"Start from this"** — botão sem contexto: começar de quê? (template?).
  Renomear para o que faz ("Usar exemplo como base", se for isso).
- "Show me the prompt" desabilitado sem tooltip do porquê.

### 3. [polimento] Orçamento técnico

"Prompt budget 0 of 1200 tokens" — correto e útil, mas sem consequência
explicada ("o que passa de 1200 é recusado, não truncado" — a doc do schema
diz isso; uma linha aqui resolve).

### 4. [polimento] Coluna "Organisation" desperdiçada

Painel esquerdo inteiro para listar um único nó ("Default organisation"). Com
um nó só, colapsar a um breadcrumb; a árvore só aparece quando houver árvore.
(Vale igual para Configuration e Autonomy, que têm o mesmo painel.)

## Critérios de aceite

- Nenhum link colado em prosa; todos com separador e verbo próprio.
- Um exemplo concreto de seção visível no editor vazio.
- Todo botão desabilitado explica por quê (tooltip ou texto).
