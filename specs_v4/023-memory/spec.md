# 023 — Memory

Tela saudável; os empty states são dos melhores do console (explicam o ciclo:
episódio ← investigação encerrada; estratégia ← episódios concordantes). Os
reparos são pequenos.

## Problemas

### 1. [bloqueia entendimento] O vazio não fecha a cadeia causal

"An episode is written when an investigation ends. None has ended yet" — e,
como nas specs 011/021, a razão de nenhuma ter terminado é o setup incompleto.
Uma linha a mais ("investigações exigem o setup completo — faltam N passos")
com link fecha a cadeia.

### 2. [polimento] Filtros vazios e contador órfão

Component/Outcome com única opção "Any" (esconder sem dados); "Episodes: 0"
solto no canto superior direito duplicando o que o painel já diz.

### 3. [polimento] Dois painéis empilhados de vazio

Episodes e Strategies gastam ~700px verticais para dizer duas frases. Quando
ambos estão vazios, colapsar a uma única seção explicando o ciclo completo
(investigação → episódio → estratégia) — o texto de Strategies já quase faz
isso.

## Critérios de aceite

- Sem episódios, a página cabe numa viewport e aponta o motivo real.
- Nenhum filtro com única opção visível.
