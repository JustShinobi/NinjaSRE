# Controle — 021 Topology

Reconciliado por confronto em 2026-08-13. Ver
`specs_v4/021-topology/relatorio-confronto.md` para as evidências,
arquivo:linha, e os gates rodados. Ao contrário do confronto anterior (020
Resources), aqui o controle já estava certo: as três linhas abaixo foram
reexecutadas (código lido de novo, os 7 testes de `topology.test.tsx`
rodados, não só inferidos) e continuam **FEITO**, sem nenhuma mudança de
código necessária.

| Item | Estado | Detalhe |
|---|---|---|
| 1. Dois painéis com o mesmo vazio | **FEITO** (onda 3, `fb80663`; reconfirmado no confronto de 2026-08-13) | `console/src/surfaces/screens/topology.tsx:126-133` desenha um único `Panel` quando `resolvedState === 'empty'`; a grade de dois painéis (`:134-231`) só aparece quando há dependência ou dependente. Coberto por `topology.test.tsx:136-142` e `:174-186`, os dois rodados e passando contra a árvore atual. |
| 2. O vazio esconde a dependência real | **FEITO** (onda 3, `fb80663`; reconfirmado no confronto de 2026-08-13) | `emptyBecause(..., setupCause(locale, setup))` (`topology.tsx:103-112`) troca cabeçalho/corpo/ação pela causa do setup enquanto há passo pendente, e devolve o texto do mecanismo assim que o setup fecha — o mesmo `emptiness.ts:45-53`/`:79-87` que outras 7 telas (memory, knowledge, detectors, data, approvals, proposals, incidents) já compartilham. Coberto por `topology.test.tsx:144-171`, rodado e passando. |
| 3. Breadcrumb "root" | **FEITO** (onda 3, `fb80663`; reconfirmado no confronto de 2026-08-13) | `DEFAULT_NODE = 'root'` (`topology.tsx:48`) nunca é impresso: o crumb no endereço não qualificado lê o nome da organização em `/v1/config` (`:115-120`) ou é omitido quando a árvore não nomeia nada, porque `trailFor`/`AreaHeader` não desenham breadcrumb para uma trilha de um item só (`shell/routes.ts:435-437`, `shell/area.tsx:53`). Coberto por `topology.test.tsx:188-218`, rodado e passando. |

7 testes, todos rodados de novo neste confronto (não só lidos) — os mesmos
que o controle anterior já citava. **Fica fora, como antes:** a caixa do
próprio sujeito dentro do SVG ainda mostra o `nodeId` cru (`graph.tsx:131-148`)
— a API não dá nome ao sujeito da consulta, só aos vizinhos, e o critério de
aceite fala de breadcrumb, não do desenho.

**Duas observações novas deste confronto, também fora do escopo e também não
mexidas:** (a) o nó padrão `'root'` pertence ao espaço de identificadores da
árvore de organização, não ao do grafo de topologia (cujos nós são serviços
como `svc-ledger`), e nada no console cria hoje um link para
`/topology?node=<id real>` — na prática o endereço não qualificado desta tela
está sempre vazio, mesmo num deployment populado; só se chega a um nó real
clicando dentro de um grafo já aberto ou editando a URL à mão. Nenhum dos três
problemas deste spec pede um seletor de nó, e a "onda 4" (fusão em Knowledge,
spec 090) é onde isso provavelmente pertence. (b) `gateway/http/routes/topology.py`
nunca devolve 404 de fato para um nó nunca visto — devolve 200 com listas
vazias — enquanto `fixtures/scenarios/empty/topology.json` e
`fixtures/scenarios/first-run/topology.json` declaram status 404 para a mesma
condição; não gera nenhum defeito visível (as duas formas caem na mesma
computação de `empty` em `topology.tsx:89`), então não foi tocado.

Onda 4 traz a fusão em Knowledge (spec 090).
