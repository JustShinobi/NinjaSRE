# Controle — 023 Memory

Confrontado em 2026-08-13 contra o código em `c325c45`. Ver
`relatorio-confronto.md` para a evidência linha a linha; os quatro veredictos
abaixo foram reexecutados (nove testes existentes rodados, não só lidos) e
confirmados corretos — nada estava incompleto e nada regrediu.

| Item | Estado | Detalhe |
|---|---|---|
| 1. O vazio não fecha a cadeia causal | **FEITO** (onda 3, confirmado) | A explicação do ciclo que já era boa **fica**; acrescenta-se a linha que faltava (nenhuma investigação terminou porque o setup não fechou) e o link vai ao passo. Composto à mão em vez de `emptyBecause`, porque esse substitui o corpo e a spec pedia acrescentar. Com o setup fechado e o corpus vazio, a ação volta a "ver o que está em execução" — corrigido nesta confrontação: dizia "está a correr" (português europeu), tanto nesta frase quanto na sentença partilhada de `empty.cause.setup` ("continua a ser configurado" → "continua sendo configurado"), usada por oito telas. Ver `relatorio-confronto.md` item 1. |
| 2. Filtros vazios e contador órfão | **FEITO** (onda 3, confirmado) | Filtros com só "Any" saem; o "Episodes: N" solto saiu, e com ele uma leitura de rede que já não servia ninguém. `memory.search`/`memory.stats.episodes`/`memory.strategies.lead|supporting|antipatterns|edit` seguem declaradas no catálogo e não são mais referenciadas por nada — resíduo inofensivo, não é defeito, não mexido. |
| 3. Dois painéis empilhados de vazio | **FEITO** (onda 3, confirmado) | Com o corpus vazio, um painel só a explicar o ciclo inteiro. Com pelo menos um episódio, ou com a leitura falhada, os dois painéis ficam como estavam. |
| (CTA duplicado na acessibilidade) | **FEITO** (onda 3, no `Panel`, confirmado) | Ver o controlo da 011: a causa era partilhada e foi corrigida na raiz (`EmptyStateAction` como união em `components/state.tsx`), não em Memory. |

9 testes novos, todos rodados contra a árvore antes de qualquer mudança desta
confrontação: 9 passaram. A condição de "verdadeiramente vazio" é o número de
registos **sem filtro**: cair em `?outcome=resolved` sem correspondências
continua a mostrar a vista filtrada normal, porque atribuir uma escolha de
filtro a um setup partido seria mentir.

## O que esta confrontação mudou

Nada na estrutura — os quatro itens acima já estavam prontos. Dois pontos de
português europeu foram corrigidos em `console/src/i18n/pt-BR.ts`, únicos
arquivos tocados:

- `memory.episodes.empty.action`: "Ver o que está a correr" → "Ver o que está
  em execução" (alinhado com `proposals.empty.action`, mesma string de
  origem em inglês, já correta).
- `empty.cause.setup` (partilhada por oito telas via `setupCause`): "este
  deployment continua a ser configurado" → "continua sendo configurado".

Nenhum teste ficou vermelho para nenhuma das duas correções — são conteúdo
puro em entradas de catálogo que já estavam completas e já passavam em tudo
que as toca; nada nesta base verifica dialeto. Isso está dito explicitamente
no relatório, não inferido.

Traçado e deliberadamente não tocado, por não ser alcançado pela tela de
Memory ou por ser vocabulário genérico partilhado por todo o console (não
específico desta spec) — nomeado no relatório para não se perder:
`empty.cause.watching` (mesmo defeito, só em `incidents.tsx`/`detectors.tsx`),
`surface.loading` (usado por 52 pontos de chamada em todo o console),
`dashboard.attention.empty.action`, `approvals.empty.action` (mesma frase de
`memory.episodes.empty.action`, em telas diferentes) e o subtítulo de
`page.detectors.context`.
