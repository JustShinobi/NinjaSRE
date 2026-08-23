# Controle — 037 Data

| Item | Estado | Detalhe |
|---|---|---|
| 1. Três features numa tela / simulador sem nome | **FEITO** — controle anterior dizia NÃO INICIADO; metade já existia, metade corrigida em 2026-08-14 | A régua de regras (numerada, com "no rule above matched") já só aparecia quando havia mais que o catch-all implícito — correto e já testado. O "título honesto" ainda não existia de fato: o `<h4>` acrescentado reaproveitava a palavra "Simulate", a mesma que já estava no botão e que a própria spec cita como insuficiente, sem nenhuma frase de propósito. Corrigido com duas chaves novas de catálogo (`data.simulate.title`: "Test a delivery"/"Testar uma entrega", ecoando quase literalmente a sugestão da spec; `data.simulate.purpose`, uma frase dizendo o que a ferramenta responde) e um parágrafo novo abaixo do título. Ver `relatorio-confronto.md`. |
| 2. URLs http:// com IP interno | **FEITO** — controle anterior dizia NÃO INICIADO e estava errado | Já corrigido antes desta auditoria: um esquema http:// nunca é renderizado — a tela cai para o caminho relativo (sem host, que não pode mentir) — e as duas formas copiam com um clique via `CopyValue`. Os 12 testes entre `data.test.tsx`/`data-copy.test.tsx`, construídos com o IP exato que a spec cita, já cobriam isso e passaram sem alteração. A parte condicional (mostrar o host público correto quando a URL é a real) foi rastreada até o fim: o console não tem, em lugar nenhum, o conceito de "host público" do deployment, e a própria rota do backend (`gateway/http/routes/ingress.py`) já documenta por que não existe uma segunda configuração para isso — decisão mantida, não uma omissão. Ver `relatorio-confronto.md`. |
| 3. "Nothing has ever arrived" em cor de erro ×7 | **FEITO** — controle anterior dizia NÃO INICIADO e estava errado | Já corrigido antes desta auditoria: o marcador usa `text-muted`, nunca `text-danger` — testado diretamente. Encontrado e corrigido nesta auditoria: a nota de aceite do baseline visual (`visual/screens.json`, `data-1440-light`) ainda descrevia o comportamento antigo ("in the danger tone"), mesmo com o PNG commitado já mostrando o tom neutro — texto corrigido para refletir o que o baseline de fato guarda hoje. Ver `relatorio-confronto.md`. |
| 4. "Where did this go?" sem indicação | **FEITO** — controle anterior dizia NÃO INICIADO e estava errado | Já corrigido antes desta auditoria: o resumo do disclosure já lê "Where did this go? (N)", com N sendo a contagem real de entregas daquela fonte — testado para uma fonte com uma entrega e outra com zero. Ver `relatorio-confronto.md`. |
| 5. "Issue a delivery token" solto | **FEITO** — controle anterior dizia NÃO INICIADO e estava errado | Já corrigido antes desta auditoria: o botão já fica dentro de um grupo (`delivery-token-group`) logo abaixo da linha que nomeia a permissão que o token precisa — testado. Ver `relatorio-confronto.md`. |

## Nota da auditoria de 2026-08-14

Os cinco itens já tinham sido resolvidos, quase por completo, pelo commit
`1ef8dd6` ("fix: mark the session cookie secure behind a proxy, and three
more screens", 2026-08-13) — um commit antes do `HEAD` em que esta auditoria
começou — sem que nada disso tivesse chegado a este arquivo. Rodar as
suítes de teste já existentes contra a árvore sem alteração (73 testes,
`data.test.tsx`/`data-copy.test.tsx`/`simulation.test.tsx`/`delivery-
token.test.tsx`/`resend.test.tsx`/`ingress.test.tsx`/`transit-
routes.test.ts`) confirmou os itens 2, 3, 4 e 5 e a metade da régua de regras
do item 1, todos já verdes antes de qualquer mudança desta auditoria.

O único gap de código genuíno era a segunda metade do item 1: o título dado
ao simulador de roteamento era apenas a palavra "Simulate" — a mesma que já
estava escrita no botão logo abaixo, e uma das duas etiquetas que a própria
spec cita como insuficientes ("sem dizer que isto é um testador de
roteamento") — sem nenhuma frase de propósito, quando o critério de aceite
pede as duas coisas ("nome **e** propósito legíveis"). Corrigido com teste
vermelho primeiro: `data.test.tsx` foi reescrito para exigir o título "Test a
delivery" e uma frase de propósito visível; rodado contra o código sem a
correção, falhou (1 de 28), confirmando vermelho pela razão certa. Depois da
correção (duas chaves novas de catálogo, nos dois idiomas, e um parágrafo
novo em `data.tsx`), os 28 testes passam.

Uma correção adicional, fora do código de produção: a nota de aceite do
baseline visual da tela (`visual/screens.json`, entrada `data-1440-light`)
ainda descrevia o marcador "nunca chegou nada" como desenhado "in the danger
tone" — exatamente o defeito que o item 3 corrige — mesmo com o PNG
commitado já tendo sido recapturado, no mesmo commit que mudou a cor, para
mostrar o tom neutro. Deixado como estava, o texto contradizia tanto o
código quanto a própria imagem ao lado dele. Corrigido para descrever o que
o baseline de fato guarda hoje (a ordem e a neutralidade, juntas).

Uma inconsistência de português (não um europeísmo) foi encontrada e
corrigida nas três strings de `ingress.token.*` que o botão de emitir token
renderiza (`shownOnce`, `failed`, `unreachable`): chamavam o deployment de
"a implantação", enquanto 64 outros pontos do mesmo arquivo de catálogo —
incluindo duas frases irmãs nesta mesma tela — já usam "o deployment" como
empréstimo. Duas das três frases corrigidas ficaram idênticas, palavra por
palavra, a frases que já existiam em outro lugar do mesmo arquivo. As duas
chaves vizinhas (`ingress.title`/`ingress.body`), que também diziam
"implantação", foram checadas e confirmadas como não-renderizadas em lugar
nenhum do código ou dos testes — o mesmo padrão de "declarado mas
inalcançável" que 022 Detectors e 024 Knowledge já encontraram e decidiram
não tocar — e foram deixadas como estavam.

Duas coisas foram rastreadas até o fim e deliberadamente não tocadas,
nomeadas em vez de descartadas em silêncio. Primeiro, a metade condicional
do item 2 ("exibir com o host público correto do deployment" quando a URL é
a real): o console não carrega, em lugar nenhum, um conceito de "host
público" do deployment — só um nome de exibição e um fuso horário — e a
própria rota do backend que serve essas URLs já explica, no seu próprio
docstring, por que deliberadamente não existe uma segunda configuração para
isso (evitar uma segunda fonte de verdade que fica desatualizada).
Como o comportamento atual (nunca anunciar http://; sempre oferecer algo
copiável) já satisfaz os dois critérios de aceite do item por completo,
inventar essa segunda fonte do lado do console iria contra o raciocínio que
o próprio backend já registrou — decisão mantida, com o raciocínio nomeado
por inteiro, não uma fuga do trabalho. Segundo, o botão "Save" do simulador
de roteamento nunca teve (e não pode ter ainda) uma ação — não existe rota
`POST /rules` nem equivalente no backend para receber uma regra salva. Isso
é anterior a qualquer um dos cinco itens desta spec (existe desde a
construção original da tela), nenhum dos itens pede para resolver isso, e
precisaria de uma capacidade de backend que ainda não existe — nomeado aqui
para quem confrontar esta tela em seguida.

Ver `relatorio-confronto.md` para a evidência completa, arquivo e linha, e
os testes que confirmaram cada item antes de qualquer correção.
