# 021 — Topology

## Problemas

### 1. [bloqueia entendimento] Dois painéis, o mesmo vazio, lado a lado

"Neighbourhood" e "The same graph, as a list" mostram empty states idênticos
("No topology recorded") com o mesmo CTA, um ao lado do outro. Quando não há
grafo, não há "mesmo grafo como lista": renderizar **um** empty state de
página, e só dividir em dois painéis quando houver dados.

### 2. [bloqueia entendimento] O vazio esconde a dependência real

"The graph is built from what investigations observe. Nothing has been
observed about this node yet." — mas neste deployment **nenhuma investigação
pode rodar** (investigador não configurado). O operador não tem como sair
desse vazio pela porta indicada ("See the estate" leva a Resources, que não
alimenta o grafo). O empty state precisa da cadeia causal: investigações
alimentam o grafo → investigações exigem o setup completo → "termine o passo
X". Mesmo padrão das specs 011/013: o vazio explica o *porquê deste
deployment*, não a teoria geral.

### 3. [polimento] Breadcrumb "Topology > root"

`root` é o nome interno do nó raiz. Exibir o nome da organização ("Default
organisation") ou omitir o crumb enquanto só existe um nó.

## Critérios de aceite

- Sem dados, a página mostra um único empty state que aponta a causa real
  (setup/investigações), não dois idênticos.
- Nenhum identificador interno (`root`) em breadcrumb.
