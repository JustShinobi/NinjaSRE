# Controle — 024 Knowledge

Confrontado em 2026-08-13 contra o código em `f73917f`. Ver
`relatorio-confronto.md` para a evidência linha a linha.

| Item | Estado | Detalhe |
|---|---|---|
| 1. "Configure ingestion" sem destino claro | **FEITO** (onda 3, confirmado) | Confirmado nesta confrontação, com verificação no backend, não só na tela. O gateway declara só duas rotas de knowledge e ambas são leituras (`gateway/http/routes/knowledge.py`); uma busca em todo `gateway/http/routes/` por rota de escrita nomeando knowledge/sync/ingest/document não achou nada. Um documento chega por `KnowledgeSync` (`platform/knowledge/base/sync/port.py`, acionado só por um worker de fundo, sem rota HTTP) ou por `propose_knowledge` (`capabilities/tools/system/knowledge_propose/tool.py`), que enfileira uma proposta e devolve um recibo dizendo que nada foi escrito. O texto da tela nomeia os dois caminhos e o botão vai a `/proposals`, o único alcançável. Nada mudou neste item. |
| 2. "Proposed by an agent" duplica a fila de Proposals? | **FEITO** (onda 3) → **corrigido nesta confrontação** | A metade estrutural (nenhuma segunda lista, um link para a fila real) já estava certa e testada — isso o controle anterior acertou. A metade que faltava: o critério de aceite pede que a relação esteja **explícita**, em palavras, e a frase visível ("Changes an investigation proposed, awaiting review.") nunca dizia se é a mesma fila de Proposed changes ou uma fila separada. Um teste novo confirmado vermelho antes da correção; corrigido só no catálogo (`knowledge.proposals.lead`, en.ts e pt-BR.ts), sem mudança de componente. Ver `relatorio-confronto.md` item 2. |
| 3. Filtro "Kind: Any" único; dois painéis de vazio empilhados | **Não estava na tabela — item inteiro ausente do controle anterior** | Duas metades em estados diferentes. A dos painéis empilhados já estava estruturalmente impossível (efeito colateral do redesenho do item 2: o painel "Proposed by an agent" nunca fica `empty`) — confirmado com um novo teste que passou de primeira, sem mudar código. A do filtro estava viva: `FilterBar` mostrava "Kind ▾ [Any]" com zero opções reais nos cenários `empty` e `first-run`, porque `knowledge.tsx` nunca filtrava a escolha vazia como `memory.tsx` já fazia. Dois testes novos confirmados vermelhos antes da correção; corrigido espelhando o padrão exato de `memory.tsx`. Ver `relatorio-confronto.md` item 3. |

## O que esta confrontação mudou

Estrutura: um filtro passou a esconder-se quando não tem opção nenhuma atrás
dele, em `console/src/surfaces/screens/knowledge.tsx` — mesmo padrão que
`memory.tsx` já usava, agora espelhado aqui.

Texto: a frase de "Proposed by an agent" passou a dizer, nas duas línguas, que
é a mesma fila de qualquer outra mudança proposta — antes só dizia que estava
à espera de revisão, sem dizer de qual fila.

Dialeto, em `console/src/i18n/pt-BR.ts`, dois pontos na mesma seção de
`knowledge.*` (achados lendo o bloco inteiro, não só a primeira ocorrência):
`knowledge.column.updated` ("Actualizado" → "Atualizado", consoante muda
pré-acordo) e `knowledge.documents.empty.body` ("nenhum **controlo** de
upload" → "nenhum **controle** de upload" — o substantivo, não o verbo; o
mesmo par que distingue "controlo remoto" de "controle remoto"). Nenhum teste
deste repositório verifica o português desta tela, então nenhuma das duas
correções tinha um teste para ficar vermelho antes — isso está dito
explicitamente no relatório, não inferido.

5 testes novos: 4 confirmados vermelhos antes da implementação (a frase da
relação explícita, e dois dos três do filtro); o terceiro do filtro passou de
primeira contra o código antigo (guarda de regressão, não prova de defeito —
dito assim no relatório) e o teste de contagem de painéis vazios também
passou de primeira, por não haver nada quebrado nessa metade.

Traçado e deliberadamente não tocado, por não ser alcançado por esta tela ou
por já estar nomeado em confrontações anteriores: `surface.loading` (52
pontos de chamada em todo o console), `knowledge.search` (chave declarada,
não referenciada em lugar nenhum), as três chaves
`knowledge.proposals.empty.*` (compostas mas comprovadamente inalcançáveis,
porque o painel "Proposed by an agent" nunca chega ao estado `empty`), e
`tree.tsx` (indicado como ponto de partida provável, mas confirmado sem
nenhuma relação de chamada com `knowledge.tsx`).
