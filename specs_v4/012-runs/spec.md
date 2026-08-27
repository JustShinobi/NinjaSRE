# 012 — Runs / Investigations (lista e detalhe)

## Problemas — lista

### 1. [bloqueia entendimento] A tela não sabe o próprio nome

Sidebar: **Runs**. Título da página: **Investigations**. Breadcrumb do
detalhe: **Investigations**. Palette: **Runs**. Escolher um nome (proposta:
**Investigations** — é o vocabulário do produto inteiro, "run" é o termo de
implementação) e usá-lo em sidebar, título, palette, empty states e badges.

### 2. [bloqueia entendimento] O ID hex é a identidade visual da linha

`9a5474b0d6db48f5854c3f387819b3b5` como primeira coluna, em negrito, é a coisa
menos informativa da linha. A identidade de uma investigação é **o assunto** —
"InvestigatorNotConfigured..." hoje, "payment-service 500s" amanhã. Propor:
coluna 1 = assunto (truncado com tooltip), com o id curto (8 chars) em
metadado. A referência lista runs por título do cenário, nunca por id.

### 3. [bloqueia entendimento] Subject = stack de erro

O assunto exibido é o texto de exceção inteiro. Mesma tradução da spec 010:
erros conhecidos têm nome curto ("Investigador não configurado") e o cru fica
no detalhe.

### 4. [polimento] Vazamento de rótulos de sort

O texto de acessibilidade das colunas concatena "SORT, SMALLEST FIRST" em cada
header (aparece também em Resources e Audit). Rótulo correto por estado
("ordenar por X, crescente/decrescente"), idealmente com indicador visual.

### 5. [polimento] "Trigger: interactive"

Slug interno. Vocabulário do operador: "manual", "alerta", "agendada".

## Problemas — detalhe

### 6. [bloqueia entendimento] Cabeçalho de lista numa página de detalhe

O detalhe reusa título ("Investigations") e subtítulo ("Every run this
deployment has recorded, newest first.") da lista — nenhum dos dois é verdade
nesta página. O título do detalhe é o assunto do run; o subtítulo, seus
metadados (quando, gatilho, duração, custo).

### 7. [bloqueia entendimento] O mesmo erro três vezes na mesma tela

"What this run found", "Investigation transcript > Report" e o título da aba
repetem o mesmo texto de exceção. Uma vez, traduzido, com o cru colapsado.

### 8. [polimento] Título da aba do navegador é o hex

`9a5474b0d6db48f5854c3f387819b3b5 · NinjaSRE`. Usar o assunto.

### 9. [polimento] Coluna direita de empty states

"No cost recorded" e "Nothing linked yet" ocupam a coluna inteira com CTAs
("Back to the run list", "See the estate") que são navegação disfarçada de
ação. Em um run que falhou antes de começar, colapsar essas seções a uma linha.

## Critérios de aceite

- Um único nome para o conceito em todas as superfícies.
- Nenhuma linha da lista exibe hex de 32 chars como primeira coluna.
- O detalhe tem título próprio (assunto) e não repete o subtítulo da lista.
- O mesmo texto de erro não aparece mais de uma vez por tela.
