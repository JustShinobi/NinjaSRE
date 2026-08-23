# Controle — 035 The agent

Confrontado em 2026-08-14. Ver `relatorio-confronto.md` para a evidência
completa, `file:line` a `file:line`, e os gates realmente executados.

| Item | Estado | Detalhe |
|---|---|---|
| 1. Budgets "0 / ceiling N" | **FEITO** (`1ef8dd6`) | Reconfirmado nesta confrontação, rodando os testes em vez de confiar no controle anterior. `effectiveBudget` (`agent.tsx:578`) lê o default do schema quando ninguém customizou e nunca converte um teto ausente em `0`; `agents.tool_budget` genuinely não tem teto no schema (`Field(ge=1)`, sem `le`, confirmado rodando `declared_fields()` direto) — o "teto 0" era `number()` lendo `null` como zero, não dado errado. Cinco testes existentes já cobriam os dois lados e passaram sem alteração. Nenhuma mudança de código. |
| 2. Chaves cruas como rótulos | **FEITO** — corrigido em 2026-08-14 | O mecanismo (rótulo traduzido + chave crua como metadado) já tinha sido construído por `1ef8dd6`, mas a tabela que ele precisava, `BUDGET_LABELS`, tinha sido deixada vazia — então todo rótulo, em todo idioma incluindo português, caía para o `label` cru do schema (o nome do campo em inglês, nunca traduzido). Preenchida com as quatro chaves de catálogo (`agent.budgets.maxIterations`/`maxParallelSubagents`/`maxSubagentDepth`/`toolBudget`, `en.ts:1328-1331`, `pt-BR.ts:1198-1201`). Cinco testes novos, confirmados vermelhos antes da correção. |
| 3. Duplicações internas (abas vs telas) | **FEITO** (primeira frase) / **fora do escopo, corretamente** (segunda frase) | A primeira frase (documento repetindo o empty state de specialists) já estava corrigida por `1ef8dd6`: `DocumentPanel` nunca entra em estado vazio (`stateOf(effective, false)`, `agent.tsx:730`), mostra `{"agents": {}}` de verdade em vez de repetir a explicação. Teste existente confirma, sem alteração. A segunda frase (sobreposição Tools/Autonomy desta tela vs. Catalogue/Autonomy) é a própria fusão que a spec 090 reivindica no seu próprio texto ("'The agent' já tem abas Topology/Tools/Autonomy... Proposta: ela vira a casa de ler o agente"), sequenciada como onda própria — não é uma tela isolada que resolve isso aos pedaços. Declinado aqui, rastreado até essa propriedade, não para evitar o trabalho. |
| 4. "deployment default" ×8 sem dizer qual | **FEITO** (`1ef8dd6`) | Reconfirmado nesta confrontação, rodando os testes. `roleBinding` (`agent.tsx:455`) resolve o default do schema (provider/modelo) para um papel não vinculado, e `ModelRolePanel` mostra `{provider} / {modelo}` em toda linha, vinculada ou não — "deployment default" fica como anotação de proveniência, não como a resposta inteira. Oito papéis existem (`MODEL_ROLES`), confirmado lendo a constante. Testes existentes já cobriam isso e passaram sem alteração. Nenhuma mudança de código. |

## O que esta confrontação mudou

Um único item tinha trabalho genuíno pendente: o item 2. `console/src/surfaces/screens/agent.tsx`
teve `budgetLabel` exportada (visibilidade, sem mudança de comportamento) e
`BUDGET_LABELS` preenchida com as quatro chaves que o próprio comentário da
função já prometia ("filled in as the words arrive"). Quatro chaves novas de
catálogo, nos dois idiomas. Cinco testes novos em `agent.test.tsx`: um de
página inteira (renderizando em pt-BR via o mesmo padrão de cookie que
`tests/unit/shell/pages.test.tsx` já usa) e quatro direto contra
`budgetLabel`. Todos confirmados vermelhos antes da correção, verdes depois.

Os itens 1, 3 (primeira frase) e 4 já estavam prontos — nenhum deles foi
tocado; o controle anterior (`NÃO INICIADO` nos quatro) estava errado na
direção de subestimar, como o resto desta série já vinha encontrando.

## Rastreado e deliberadamente não tocado

- `console/src/surfaces/preview.tsx` (`EditableField`/`ItemField`, usado pela
  tela Configuration, spec 032): mesma classe de defeito do item 2 — `label`
  é o texto cru do schema, sem tradução nenhuma, usado tanto para exibir
  quanto para a busca em página. Em escala muito maior (todo campo do schema
  inteiro, não quatro caminhos conhecidos) — o mecanismo fechado construído
  aqui não generaliza para isso. Pertence à superfície da spec 032, já
  confrontada de forma independente. Nomeado, não tocado.
- `"exacto"`, citado como conhecido nesta tela: não encontrado em lugar
  nenhum alcançável por `agent.tsx`. A única instância real no repositório é
  de `dashboard.tsx` (spec 010); uma segunda aparição era só um cache de
  build do Next (`.next/`, não é fonte) com o texto antigo de
  `teamContext.preview.lead`, já corrigido no código-fonte commitado pela
  spec 033.
- `"registada"`, citada como presente em várias telas: confirmado ausente do
  bloco `agent.*` inteiro. As duas linhas que a busca de 031 Autonomy tinha
  tocado nesta tela (`agent.bridged.empty.heading`,
  `agent.replay.empty.heading`) já são "registrado" (brasileiro) — o próprio
  relatório de 031 já registrava isso; só o resumo do `controle.md` de 031
  lista "Agent" de um jeito que lê como pendência.
- `console/src/surfaces/transcript.ts`, `transcript-view.tsx`,
  `quick-actions.tsx`, oferecidos como pontos de partida prováveis:
  confirmados, pelo próprio grafo de chamadas, como exclusivos de outras
  telas (Runs/Incidents/Dashboard) — nenhum é importado por `agent.tsx`.

## Gates executados, todos limpos

`make console-visual`: **35 passados, 0 falhos**, incluindo as três telas
`agent-*` registradas — a escolha deliberada de manter o texto em inglês
idêntico ao que o schema já produzia (para os dois caminhos que a fixture
`populated` de fato mostra) evitou qualquer diferença visual. Nenhum
baseline precisou de recaptura.

Ver `relatorio-confronto.md` para a evidência completa, linha por linha, e
todos os gates com o resultado exato.
