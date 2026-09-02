# Gate visual — 030-run-view-narrado (slot S1)

Revisor: modelo, via Orca Browser, contra `https://stg-ninjasre.lan.kyo.ninja`
com o build deste slot. Artboards de referência:
`design/padrao-2026-08/RunView.dc.html` e `RunViewLight.dc.html`.

Tema trocado pelo botão da topbar, confirmado por
`getComputedStyle(document.body).backgroundColor` antes de cada captura.
Run real do staging: `e529b03b6a1d46b0acf42947044ae7cb` (concluído).

| Tela × tema | Veredito |
|---|---|
| `/runs` escuro | **CONFORME** |
| `/runs` claro | **CONFORME** |
| `/runs/{id}` escuro | **CONFORME com um desvio nomeado** (ver §2) |
| `/runs/{id}` claro | **CONFORME com o mesmo desvio** |

## 1. O que confere

Comparação estrutural, não pixel-a-pixel, como o protocolo manda:

- **O rail de seis estágios**, horizontal, com conectores entre eles, marca
  de concluído por estágio e duração sob o nome. O artboard desenha
  Resolver integrações / Triagem / Planejar evidência / Coletar evidência /
  Diagnosticar / Entregar; a tela serve os seis, na ordem, com as durações.
- **O transcript narrado** com contagem de eventos no cabeçalho, a legenda
  "newest first" e o par de controles Narrado | Bruto. A ordem invertida
  — mais recente no topo — é a decisão do operador registrada neste slot, e
  ela está na tela.
- **O payload atrás de um controle fechado**: cada resultado de capacidade
  traz "Raw payload ▸" recolhido, nunca JSON aberto no corpo.
- **As formas de status** como segundo portador de significado, além da cor,
  nos chips de resultado (Succeeded / Failed).
- **O rail direito** com "Findings so far" e sua barra de alegações
  respaldadas, "What this investigation touched" com chips de recurso, e o
  painel de custo — na largura que o artboard usa.
- **As três famílias tipográficas** e os ícones do set novo.

## 2. O desvio, nomeado

**O painel de custo e tokens tem composição diferente da do artboard.**

O artboard desenha uma figura de display grande ("445 tokens · 2 turnos"),
uma linha de modelo, e barras por turno. A tela serve uma **tabela**: linhas
Tokens / Cost / Model, e abaixo uma segunda tabela Turn / Calls / Cost, uma
linha por turno.

A tela mostra *mais* informação; isso não a torna conforme. O board é
normativo exatamente para que "melhorias" não entrem sem passar pelo
registro — a onda anterior morreu disso, e o protocolo desta dá dois
destinos e nenhum terceiro: corrigir o código, ou registrar em
`DIVERGENCIAS.md` com aprovação explícita do operador.

**Atribuição: herdada, não desta feature.** Ficou declarada como incerta
neste arquivo até o verifier independente resolvê-la, e ele resolveu:
`git show c01f8412:console/src/surfaces/screens/run-detail.tsx` já traz a
mesma tabela, as mesmas chaves `run.usage.*` e o mesmo `usage.byTurn.map`
byte a byte. O diff da 030 sobre esse arquivo muda apenas o `state`/
`dependency` do painel (vivo × encerrado) e acrescenta um
`data-testid="usage-tokens"`. O `spec.md` da própria feature rastreia o
painel ao recorder da v7.

O desvio é real e continua devendo um dos dois destinos — corrigir ou
registrar em `DIVERGENCIAS.md` — mas o dono é anterior a esta onda. Vai
para o CONFRONTO da onda, não para o ledger da 030.

## 3. Diferenças de dado, explicitamente não de desenho

O artboard desenha um run **vivo**; o run capturado está **concluído**. Daí
vêm, legitimamente:

- a ausência de "Assumir"/"Parar" e do campo "Diga algo…" — controles de
  condução que FR-020 congela para run vivo e que a própria 030 asseriu não
  existirem num run encerrado;
- a ausência do shimmer no estágio ativo, já que nenhum estágio está ativo;
- a ausência do painel "Quando terminar", que fala do futuro de um run que
  já terminou;
- números e textos inteiramente diferentes, que é o esperado entre dados
  vivos e dados de exemplo.

A UI em inglês contra board em pt-BR não é desvio: `DIVERGENCIAS.md` §6.

## 4. Evidência

`runs-dark.png`, `runs-light.png`, `run-detail-dark.png`,
`run-detail-light.png` — full-page pelo Orca Browser, na URL real.
