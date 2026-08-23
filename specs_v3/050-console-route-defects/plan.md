# Plano — 050 Duas telas quebradas

## O defeito, localizado no código que existe hoje

O HTTP 500 não está no gateway. É um lançamento do lado do console que escapa
do isolamento do painel:

1. `console/src/session/viewer.ts` — `parseViewer` mapeia um `team_node_id`
   ausente ou vazio para `teamNodeId: ''` (linha 87). Num deployment cujo
   principal não resolve para nó algum, cada tela vê a string vazia.
2. `console/src/surfaces/screens/catalogue.tsx:40` faz
   `const node = viewer.teamNodeId;` e passa direto para
   `read('/v1/config/{node_id}/catalogue', { params: { node_id: node } })`.
   `console/src/surfaces/screens/autonomy.tsx:86` faz o mesmo:
   `const nodeId = state.filters.node ?? viewer.teamNodeId;`.
3. `console/src/lib/api.ts` — `bind()` lança um simples
   `Error("… needs a value for {node_id}")` quando um parâmetro é `undefined`
   **ou `''`** (linhas 66–79). Essa mensagem é exatamente a que a spec cita do
   log do servidor.
4. `console/src/surfaces/read.ts` — `panelRead` captura apenas `ApiError` e
   `TypeError` e deliberadamente relança tudo o resto ("engoli-lo aqui
   transformaria um bug num painel que diz que o gateway está caído"). Um
   simples `Error` portanto se propaga até o limite da rota
   (`console/src/app/(shell)/error.tsx`) — HTTP 500.

Então as duas telas quebram *antes de qualquer requisição ser feita*, e o
isolamento de falha de painel está funcionando como projetado: este é um
defeito do console, não uma falha de dependência, e o comportamento de
relançamento de `panelRead` está correto e permanece.

O padrão funcionando para copiar está em
`console/src/surfaces/screens/configuration.tsx:40–62`: lê `/v1/config`
primeiro, monta a árvore com `placeNodes`, depois
`const selected = state.filters.node ?? placed[0]?.id ?? ''`, e **pula a
leitura com escopo de nó inteiramente quando `selected === ''`**, substituindo
um `PanelData` vazio pronto. Configuration já renderiza corretamente num
deployment sem nó algum.

## Escopo A — resolver o nó antes de chamar

Ambas as telas adotam o padrão de configuration palavra por palavra:

- `catalogue.tsx`: ganha `CATALOGUE_FILTERS: readonly FilterName[] = ['node']`
  (ela atualmente não lê estado de visualização algum), lê a árvore `/v1/config`,
  e resolve `?node=` → raiz. Quando nó algum se resolve, o painel
  catalogue-entries renderiza seu estado `empty` existente (as mensagens
  `catalogue.empty.*` já existem) em vez de chamar `/v1/config/{node_id}/catalogue`.
  Os painéis `/v1/capabilities` e `/v1/integrations` são livres de nó e
  inalterados.
- `autonomy.tsx`: já lê `AUTONOMY_FILTERS = ['node']`; a mudança é
  a cadeia de fallback — `state.filters.node ?? <raiz de /v1/config> ??
  render-empty`, nunca `viewer.teamNodeId` sozinho. `viewer.teamNodeId`
  permanece como o padrão *preferido* quando não está vazio (é o próprio time
  do chamador), com a raiz da árvore como fallback: `node ?? (teamNodeId || root) ?? ''`.

A leitura extra de `/v1/config` é uma requisição por visualização de página,
corresponde ao que configuration já paga, e passa por `panelRead` para que uma
falha do config-service degrade o seletor de nó, não a página.

**Decisão que a spec deixou aberta — quem é proprietário da resolução de nó.**
Três telas agora compartilham "árvore → `?node=` → raiz". Isto aterrissa como
um pequeno helper `resolveNode(search, filters, viewer, tree)` em
`console/src/surfaces/url-state.ts` (ao lado de `readViewState`, que todas as
três já importam) em vez de duplicado por tela ou içado para o layout do shell.
Não o layout, porque apenas telas com escopo de nó pagam pela leitura da árvore;
não por tela, porque a próxima tela com escopo de nó (058/060 constroem
exatamente sobre isto) faria a regra se bifurcar.

## Escopo B — falhar como painel, nunca como rota

O mecanismo de isolamento já existe (`panelRead` → `stateOf` → estado de
erro de `Panel`) e 33 sites de chamada o usam. O que *não* existe é um teste
que mantém a propriedade para cada rota do shell. Duas camadas:

- Um teste unitário em `console/tests/unit/surfaces/` que renderiza **todas** as
  telas em `console/src/surfaces/screens/` (enumeradas a partir de `AREAS` em
  `console/src/shell/routes.ts`, a lista fechada) com um stub de fetch que
  rejeita toda requisição, e afirma que a tela se resolve para um ReactNode
  contendo estados de erro de painel em vez de lançar. As duas telas corrigidas
  ganham um caso adicional: fetch sucessivo, viewer com `teamNodeId: ''`, sem
  `?node=` — o estado inicial exato que 500 hoje.
- O `console/tests/e2e/shell.spec.ts` existente já percorre rotas; ele
  ganha a variante "gateway caído" apenas se já não tiver uma
  (verifique na implementação; a camada unitária é a obrigatória).

Nada mais nas 14 telas é *mudado* por este escopo — a auditoria é o
teste, e qualquer tela que o novo teste pega lançando é corrigida nesta
feature com o mesmo tratamento de estado de painel.

## Escopo C — cobertura de smoke que teria pego isto

O smoke de hoje é `phase_smoke` em `.canary/guest/canary.sh:257–289`: cinco
verificações, todas contra o processo API. O console não é servido por caminho
de deploy algum (README "Evidências"), então o percurso do shell não pode
rodar dentro do guest.

**Decisão: o percurso do shell é um passo do lado do host em `.canary/deploy.sh`,
não uma fase de guest.** `deploy.sh` roda onde o console de desenvolvimento roda;
o guest não tem runtime Node e não tem build de console. Um novo passo entre
`smoke` e `promote`:

- Lê `CONSOLE_SMOKE_URL` de `.canary/config.env` (não definido ⇒ o passo diz
  assim e é pulado — mesma postura que os chaos suites: pule com uma mensagem
  nomeando o que está faltando, nunca passe silenciosamente).
- Entra contra a rota de session do console com credenciais de
  `config.env` (a suite e2e's `console/tests/e2e/session.ts` mostra a
  forma de entrada), depois GETs cada um dos 14 caminhos e exige 200.
- A lista de rotas **não** é retipada no shell. Um pequeno script
  `tools/console_smoke.py` imprime/percorre os caminhos; sua lista é
  afirmada igual a `AREAS` por um teste unitário da mesma forma que
  `tests/contract/console/test_console_shell.py` já mantém permissões de rota
  contra o gateway — um fato, dois titulares, um teste forçando concordância.
  (`tools/` é tooling do repositório, não chamável por agent — tier certo
  para uma verificação de deploy.)
- Falha antes da promoção ⇒ `deploy.sh` para exatamente como uma falha de smoke
  faz hoje: canary parado, par estável intacto.

## O que esta feature NÃO faz

- Sem superfície de escrita, sem editor: `/catalogue` e `/autonomy` permanecem
  somente-leitura. Editores são 058 (política de autonomy, configuration) e
  060 (tela de agent).
- Sem mudança ao lançamento throw-on-empty de `bind` ou ao relançamento de
  `panelRead` — ambos estão corretos; os chamadores estavam errados.
- Sem UI de seletor de nó *além do que `?node=` e `OrgTree` já dão
  a configuration. Um componente seletor de nó compartilhado é preocupação de
  058.
- Sem servir o console do container. A lacuna de deployment-note permanece;
  Escopo C trabalha ao redor dela explicitamente.

## Verificação de constituição

- **I / II / III–VII, IX–XI** — não tocados: caminhos de leitura apenas, nenhuma
  nova capacidade, nenhum acesso de armazenamento, nenhum envolvimento de LLM.
- **VIII** — mudanças de console ficam dentro de `console/`;
  `tools/console_smoke.py` não importa nada first-party acima de sua estação
  (fala HTTP apenas, como a linha de console da tabela de tier exige).
- **XII** — cada mudança aterrissa test-first; os testes falhando são nomeados
  por tarefa abaixo.
- **XIII** — inglês em todo o lugar; nada comprometido referencia `specs_v3/`.

## Raio de impacto

- `catalogue.tsx`, `autonomy.tsx` — cobertos hoje por
  `console/tests/unit/surfaces/behaviour.test.tsx` e suites e2e/visual;
  baselines visuais para essas duas telas podem precisar de
  `make console-visual-accept` re-captura se o estado vazio muda pixels.
- `url-state.ts` — 16+ importadores; o helper é aditivo, nenhum símbolo
  existente muda de forma.
- `.canary/deploy.sh` — voltado para desenvolvedor; `--no-smoke` deve continuar
  pulando o novo passo também.
