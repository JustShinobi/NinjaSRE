# Controle — 032 Configuration

Confrontado em 2026-08-14. Ver `relatorio-confronto.md` para a evidência
completa, `file:line` a `file:line`, e os gates realmente executados (não
apenas os que "deveriam" passar).

| Item | Estado |
|---|---|
| 1. Docstrings internas vazando (FR/artigos/caminhos) | **FEITO** (lote 6) — confirmado de novo, suite de regressão executada de facto: 340 testes |
| 2. Tudo expandido, salvar a quilômetros | **FEITO com desvio** (lote 6) — confirmado de novo, e2e re-executado num browser real |
| 3. Campo não definido esconde o default efetivo | **FEITO PARCIALMENTE** (lote 6 + confrontação 032) — ver nota abaixo |
| 4. "Set at default" ambíguo | **FEITO** (lote 6) — confirmado de novo, nas duas vocabulárias da tela |
| 5. Efetiva: colapso críptico + badge UNKNOWN | **FEITO** (lote 6) — confirmado de novo |
| 6. Rótulos gerados (EVALUATED 1/2, toggle isolado) | **FEITO** (lote 6 + confrontação 032) — ver nota abaixo |
| 7. Compete com as telas dedicadas | **NÃO INICIADO** (estrutural, vai com a 090) — confirmado de novo |

## Item 3 — corrigido pela metade, e a metade que falta tem dono próprio

A linha do campo no editor ("usando o padrão: 5") está correta e testada —
é o caso de maior volume que o problema nomeia (~80 campos). O que o lote 6
registou como recusa sustentada — a coluna NOW do diff do preview continuar
vazia para um campo nunca definido neste nó — foi reexaminado nesta
confrontação, e a razão registada ("seria merge do lado do cliente que o
AGENTS.md proíbe") é verdadeira sobre a consola e incompleta sobre o
sistema: o valor em causa já é algo que o *servidor* calcula noutro sítio
(`inherited`, dentro do próprio `preview_of`), portanto uma correção do lado
do servidor não seria aquele merge.

Desenhei essa correção por inteiro, em análise, e não a construí: mudaria um
invariante deliberadamente testado e pré-existente de
`platform/config_service/preview.py` —
`test_clearing_a_field_nothing_inherits_reverts_to_no_value_at_all`
(`tests/unit/platform/config_service/test_preview_redundancy.py:176-183`),
do commit `827ec0b`, 171 commits antes do próprio commit desta spec
(`c512fae`). Não é uma decisão que o lote 6 tenha tomado e possa rever; é um
desenho de fundação do `config_service`, anterior à spec 032, e mudá-lo é
uma decisão de quem for dono do contrato de `preview.py`, não desta
confrontação de tela. Nenhum código foi escrito para esta metade — nem
teste, nem implementação.

## Item 6 — o cartão já não é "Evaluated 1"; o toggle sem nome ainda era

`entryTitle` já lia só o campo `name` da própria entrada — "Evaluated N"
passou a ser uma posição honesta ao lado do nome, não mais o nome em si.
O que sobrou: um toggle booleano dentro de uma entrada *sem nome ainda*
(o estado de qualquer entrada logo após "Add another", antes de alguém
digitar) continuava a não dizer de quem é, exatamente o "toggles 'Enabled'
sem objeto" que o problema cita — só que para o único caso que a correção
anterior tinha deixado de fora. Corrigido nesta confrontação, com teste
vermelho confirmado primeiro
(`console/tests/unit/surfaces/config-editor.test.tsx:495-503`): o toggle
agora usa a posição ("Evaluated 1 — Enabled") quando não há nome.

## O levantamento de português do Brasil, só neste bloco da tela

Sete correções, todas no bloco `configuration.*` de `console/src/i18n/pt-BR.ts`,
nenhuma com teste a fixar o texto (como em toda a série, `resolveLocale`
usa inglês por padrão nos testes):

- `Configuração efectiva` / `Ver os valores efectivos` → `efetiva`/`efetivos`
  (consoante muda pré-acordo, a mesma classe de `Objectivo`→`Objetivo`).
- `Cada controlo abaixo...` → `controle` (o mesmo par `controlo`/`controle`
  que a 024 Knowledge já corrigiu uma vez noutra tela).
- `A guardar…` → `Guardando…` (progressivo "a + infinitivo" é
  especificamente europeu; é a mesma forma de `surface.loading`'s "A
  carregar…", só que esta chave pertence só a esta tela).
- `...o único sítio onde a herança é visível.` → `lugar` (`sítio` em
  português do Brasil é uma propriedade rural pequena, não "lugar" — o
  mesmo formato de `equipa`/`equipe`).
- `Não foi possível contactar o deployment.` → `contatar`.
- `Uma lista ou uma secção livre...` → `seção` (a mesma tela já dizia
  `seção` seis linhas abaixo, em `configuration.editor.toc` — inconsistência
  interna ao próprio bloco).

Rastreados e deliberadamente não tocados, por pertencerem a outras telas:
`surface.loading` (52 pontos de uso, já nomeado como fora de escopo),
`teamContext.*`'s própria `secção`/`contactar`/`A guardar…`/`ecrã`, e
`signIn.unreachable`'s `contactar` — os mesmos padrões, noutro bloco.
`equipa` em `nav.teamContext`/`page.teamContext.title` é o mesmo já
conhecido cluster de Team Context/schedules citado no briefing desta
confrontação — confirmado presente, não redescoberto, não tocado.

## O que ficou confirmado sem mudança nenhuma

Itens 1, 2, 4, 5 e 7: o lote 6 estava certo, e desta vez foi verificado a
sério — os testes que cada um cita foram *executados*, não apenas lidos, e
o e2e/visual foram corridos num browser real (`make console-visual`: 35/35,
incluindo `configuration-1440-light`; `make console-e2e`: 84/84, incluindo o
teste que prova o critério de aceite 2 — alcançar um campo pela busca, sem
rolar, num browser de verdade).
