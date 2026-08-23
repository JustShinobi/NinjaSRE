# Tarefas — 050 Duas telas quebradas

Ordenadas; cada tarefa é um commit, test-first: o teste falhando aterrissa e
é confirmado como falhando antes do código que o faz passar.

## T-001 — a reprodução falhando, para ambas as telas

Adicione testes unitários em `console/tests/unit/surfaces/` renderizando
`CatalogueScreen` e `AutonomyScreen` com um viewer cujo `teamNodeId` é `''`
e sem `?node=` nos parâmetros de busca, fetch stubbed para responder
`/v1/config` com uma árvore vazia. Afirme que cada uma se resolve para uma
página renderizada (painéis em estado vazio), não um lançamento. Confirme
que ambas falham hoje com `… needs a value for {node_id}`.

## T-002 — o resolvedor de nó compartilhado

Teste primeiro: `console/tests/unit/surfaces/` (testes de url-state) —
`resolveNode` retorna `?node=` quando presente, senão um `viewer.teamNodeId`
não vazio, senão a raiz da árvore de um payload `/v1/config`, senão `''`.
Depois implemente em `console/src/surfaces/url-state.ts` ao lado de
`readViewState`.

## T-003 — catalogue resolve um nó antes de chamar

Faça o caso de catalogue de T-001 passar: `catalogue.tsx` lê a árvore
`/v1/config` via `panelRead`, resolve o nó com o helper de T-002, e
substitui um `PanelData` vazio pronto pelo painel catalogue-entries quando nó
algum se resolve. Testes de comportamento existentes de catalogue ficam verdes.

## T-004 — autonomy resolve um nó antes de chamar

Mesma mudança em `autonomy.tsx`, mantendo `AUTONOMY_FILTERS` e a
ordem `?node=`-first. Faça o caso de autonomy de T-001 passar.

## T-005 — cada tela do shell sobrevive a um gateway morto

Apenas teste (mais correções se pegar uma terceira tela): um teste unitário
que enumera `AREAS` de `console/src/shell/routes.ts`, renderiza cada tela
com toda requisição de fetch rejeitando, e afirma uma página renderizada com
estados de erro de painel. Qualquer tela que lança é corrigida nesta tarefa
com o tratamento de estado de painel.

## T-006 — o percurso de smoke do console

Teste primeiro: um teste unitário sob `tests/` afirmando que a lista de
caminhos em `tools/console_smoke.py` é igual aos caminhos `AREAS` (leia da
mesma forma que `tests/contract/console/test_console_shell.py` lê). Depois
implemente `tools/console_smoke.py`: entre, GET todos os 14 caminhos do shell,
saia com código não-zero nomeando cada caminho que não retornou 200.

## T-007 — conecte o percurso ao fluxo canary

`.canary/deploy.sh`: depois de `guest smoke`, execute `tools/console_smoke.py`
contra `CONSOLE_SMOKE_URL` de `.canary/config.env` quando definido; pule com
uma razão impressa quando não definido; honre `--no-smoke`. Uma falha para
antes de `promote`, canary parado, par estável intacto. (Mudança de shell —
verificada executando `--canary-only` contra o container de validação, registrada
em deviations.)

## T-008 — baselines visuais, se pixels se moveram

Execute o gate do console; re-capture baselines afetados com
`make console-visual-accept` apenas para as duas telas, e diga assim em
deviations.

## Definição de pronto

Observável, cada item verificável sem ler o histórico deste repo:

1. `GET /catalogue` e `GET /autonomy` num deployment com nada configurado
   retornam 200 — prováveis no navegador contra o container de validação, e por
   T-001 no gate.
2. Com toda requisição API falhando, todos os 14 percursos do shell renderizam
   com estados de erro de painel — T-005 é a prova, e enumera `AREAS` para que
   uma 15ª tela seja coberta no dia em que é adicionada.
3. `./.canary/deploy.sh` com `CONSOLE_SMOKE_URL` definido percorre os 14
   percursos autenticado e recusa promover em qualquer não-200; com não definido,
   imprime que o percurso do console foi pulado e por quê.
4. O caso "nó nenhum selecionado" é um teste nomeado para cada tela cujos dados
   são com escopo de nó (hoje: catalogue, autonomy; configuration já tem o
   comportamento).
5. `make verify` verde, incluindo o gate do console.

## Dependências em outras features specs_v3

Nenhuma. Esta feature deve fazer merge primeiro; 058 e 060 constroem seus
editores na resolução de nó que T-002 introduz.
