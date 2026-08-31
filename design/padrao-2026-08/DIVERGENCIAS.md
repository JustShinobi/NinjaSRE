# Divergências registradas

O operador decidiu (2026-08-27) que este board é o padrão e que convenções do
projeto que digam o contrário devem ser **registradas e ignoradas**. Este é o
registro. Cada item nomeia a convenção anterior, onde ela vive (ou viveu), e o
que vale agora.

## 1. Chip de status volta a ter contorno

O board `console-redesign/StatusStyle.html` (removido; recuperável no git)
escolhia "B · Soft pill — a tint, **no stroke**". O padrão novo desenha chips
com tint **e** borda de 1px na própria cor do estado. O contorno sutil sobre
fundos elevados é parte do que faz o novo tema vender; a crítica original era
ao *box dentro de box* com glyph bordado, que continua banido. As formas de
status como segundo portador de significado permanecem.

## 2. Tipografia deixa de ser "do sistema"

`console/src/design/tokens.ts` declara "The two families, both from the
operating system". O padrão novo usa **Space Grotesk** (display/números),
**IBM Plex Sans** (corpo) e **IBM Plex Mono** (ids/dados). Os artboards
referenciam Google Fonts por `<link>`; a implementação deve **self-hostear**
os woff2 no repositório (`console/public/fonts/`) — nenhuma request a
terceiros sai de uma página do console em produção. O README antigo desta
pasta prometia boards "sem rede"; os artboards degradam para os fallbacks
declarados quando offline, e a promessa forte de no-network passa para o
produto, não para os mockups.

## 3. O polling deliberado dá lugar a SSE

`console/src/live/auto-refresh.tsx` documenta com orgulho um refresh por
timer que "não encurta o intervalo sob falha" — filosofia construída em cima
de `router.refresh()`. O padrão novo exige eventos empurrados (SSE) para
Painel, listas e run view; o timer vira fallback quando o stream cai. A regra
que **sobrevive** do comentário em `topbar.tsx` é o indicador único de
frescor por página (o chip "Ao vivo") — um por frame, nunca um por painel.

## 4. Baselines visuais ficam todos obsoletos

`console/visual/screens.json` e os baselines em `console/visual/` descrevem o
console anterior. Aplicar o padrão exige re-baseline completo do gate visual
(que já estava vermelho de cobertura antes deste board). Nenhuma comparação
contra baseline antigo é evidência de drift.

## 5. A paleta servida em `surfaces/console/theme.py` é de outra era

O `stylesheet()` server-side carrega o azul `#0b5cab` de uma superfície
anterior ao console React. Qualquer tela ainda servida por ele diverge do
padrão e deve migrar para os tokens novos ao ser tocada.

## 6. UI bilíngue, board em pt-BR

O board desenha a UI em pt-BR. O console é i18n (en, pt-BR) via `message()`;
a implementação continua i18n — as strings do board entram como pt-BR e
ganham par em inglês. Não é conflito, é nota: ninguém deve hardcodar as
strings do mockup.

## 7. O contrato de contraste tratava `border-strong` como limite obrigatório

Decidido pelo operador em 2026-08-27, ao aplicar a paleta na fundação visual:
**o artboard é a fonte da verdade; o board não está errado, o que estava
errado é o que foi feito.** O registro do que isso significa, medido:

`console/src/design/tokens.ts` gera em `boundaryPairs()` um par
`border-strong` contra cada um dos quatro fundos, e a suíte
(`tests/unit/design/contrast.test.ts`) exige 3:1 em cada um, por WCAG 1.4.11.
Com a paleta do board, nenhum dos oito pares alcança esse número:

| Fundo | dark (`#35493f`) | light (`#9fb0a8`) |
|---|---|---|
| `surface` | 1.87:1 | 2.27:1 |
| `sunken` | 1.99:1 | 2.08:1 |
| `raised` | 1.71:1 | 2.27:1 |
| `hover` | 1.56:1 | 1.94:1 |

E `hover` sobre `raised` no dark mede 1.098:1 contra o mínimo interno de 1.1
(`HOVER_MINIMUM`, que não é WCAG) — reprova na terceira casa decimal.

O que os artboards de fato fazem com esse token decide a questão. Ele aparece
como `.kpi:hover { border-color: #35493f }`, uma ênfase de hover num cartão
que já tem a própria borda `1px solid #223029`, e como contorno de chips
secundários ("Recusar", "Ver plano →") cujos rótulos vêm em `#e9f0ec` ou
`#9fb2aa`. Em nenhum artboard `border-strong` é a única coisa que identifica
um controle ou um estado — que é a condição em que 1.4.11 se aplica. O
contrato foi calibrado contra a paleta anterior, que passava por acaso, e
descreve uma exigência que a linguagem visual deste board nunca teve: ela não
possui limite neutro de alto contraste, e isso é a estética escura e discreta
que o operador aprovou, não um descuido.

**O que vale agora**: os hexes do board entram intactos. Os pares continuam
sendo gerados e medidos, com as razões acima fixadas como literais na suíte —
um número que some do teste é pior que um número que falha, e a regra "gate
não é afrouxado" existe contra exatamente esse sumiço. Qualquer par fora
deste registro continua reprovando normalmente, e qualquer um destes que se
mover do valor tabelado também.

**O custo, dito por inteiro**: limites neutros de controle nesta paleta ficam
perto de 1.9:1 sobre todo fundo escuro. É uma propriedade real do padrão
aprovado, não um efeito colateral desta feature, e fica aqui para que
ninguém a redescubra como defeito nem a "conserte" em silêncio.

## 8. Dois desfechos de episódio que o board não desenha

`Knowledge.dc.html` desenha um único desfecho — `inconclusivo`, em âmbar
vazado — e o console o segue exatamente. Mas a enumeração que o produto
declara tem quatro membros: `resolved`, `mitigated`, `inconclusive` e
`false_positive`. Dois deles não têm desenho em lugar nenhum do board.

**Onde eles vivem hoje.** O caminho de escrita de uma investigação real não
produz nenhum dos dois: `MemoryEpisode.outcome` é `RESOLVED if resolved else
INCONCLUSIVE` — um booleano. Quem os produz é o semeador da demonstração, que
mapeia as palavras do próprio dataset (`platform/startup/demo/seeder.py`), e
ele é alcançável de um root que serve: a rota de primeira execução e o comando
de setup. Ou seja, um deployment real pode ter episódios `mitigated` e
`false_positive` — no inquilino da demonstração, que é a primeira coisa que um
operador novo vê.

**O que foi decidido.** Os dois entram no mapa de status, com valores
derivados do próprio vocabulário e não inventados:

| Palavra | Papel | Forma | Por quê |
|---|---|---|---|
| `mitigated` | `warning` | `dimmed-circle` | o sintoma parou e a causa não foi consertada. Não é `success` pela mesma razão que `closed_without_action` não é: desenhar de verde uma coisa inacabada é como a taxa de sucesso de um deployment mente. Círculo porque a investigação terminou ali; esmaecido porque não é o que `resolved` afirma. |
| `false_positive` | `neutral` | `dash` | o alerta estava errado e não havia o que consertar. Nada foi feito e nada é devido — o traço é o que isso significa em todo lugar onde ele aparece neste mapa. Quem precisa de atenção é o detector, não o ambiente. |

**Por que os dois, e não um.** A recomendação que chegou primeiro era declarar
só `mitigated`, com o argumento de que dois dos cinco episódios do dataset
simulado são `mitigated` enquanto nada produz `false_positive`. O argumento é
circular: aquele dataset diz `mitigated` porque foi editado para dizer, seguindo
o mesmo mapeamento do semeador que também produz `false_positive`. Os dois estão
na mesmíssima posição, e tratá-los de forma diferente registraria uma assimetria
que o produto não tem.

**O que isto não conserta, e é maior.** Uma investigação de verdade não
consegue dizer "mitiguei" nem "era falso positivo" — o caminho de escrita
colapsa quatro palavras num booleano. E essas são justamente as duas que um
corpus de aprendizado mais precisa distinguir: um falso positivo é problema do
detector, uma mitigação é um conserto pela metade. Enquanto o colapso existir,
estas duas formas só aparecem na demonstração. Está registrado no confronto da
onda, porque é lacuna de produto e não de desenho.

## 9. A atividade ao vivo não desenha o trilho vertical

`Main.dc.html` e `DashboardLight.dc.html` desenham, na coluna "Atividade ao
vivo", um trilho de 1,5px em degradê atrás das entradas, com a forma de cada
entrada posicionada em cima dele (`position: absolute; left: -18px`). O
console desenha as mesmas quatro formas — losango, círculo, quadrado,
triângulo — mas **ao lado** do texto, numa linha flex por entrada, sem
trilho.

**Por quê.** O trilho do board passa pelo centro de quatro formas de
geometrias diferentes. Centralizá-lo de verdade exige um deslocamento
próprio por forma — o triângulo do board é feito de bordas e nasce 1px acima
do círculo de mesmo tamanho — e cada um desses deslocamentos é um valor fora
da escala de espaçamento declarada, que não tem base e não abre exceção para
decoração. A alternativa honesta seria alinhar o trilho a uma forma só e
deixar as outras três tortas, que é pior do que não ter trilho.

O que o trilho carrega de significado — "isto é uma sequência no tempo" — a
ordem das entradas e o instante relativo de cada uma já carregam. A razão
está escrita no próprio componente (`console/src/surfaces/activity-feed.tsx`).

**O custo, dito por inteiro**: a coluna lê como lista, não como linha do
tempo desenhada. Se a escala ganhar um degrau que sirva a esses
deslocamentos, o trilho volta a ser possível e este registro cai.

## 10. Um segundo e um terceiro indicador de frescor não entram

O board diz três vezes, no mesmo quadro, que a página se atualiza sozinha: o
chip "Ao vivo" na topbar, o chip `stream` ao lado do título "Atividade ao
vivo", e a legenda "atualizado por eventos · sem recarregar" à direita do
cabeçalho da página.

O console implementa **o primeiro** e nenhum dos outros dois. É a regra que o
registro 3 desta lista já preservou por escrito — indicador único de frescor
por página, um por quadro, nunca um por painel — aplicada aos dois lugares
onde este board a contraria. Um leitor que precisa saber se a tela está viva
tem um lugar para olhar, e quando o stream cai é esse mesmo lugar que muda,
em vez de três afirmações que discordam entre si por alguns segundos.

## 11. A decomposição de "Recursos vigiados" usa as palavras do estate

O board escreve `68 contêineres · 21 datastores · 2 nós`: nomes traduzidos,
pluralizados, e só três tipos. O console escreve as chaves que a decomposição
do overview devolve, como o deployment as soletra — `63 container · 21
datastore · 2 node · 5 backup_job · 1 cluster · 1 virtual_machine` — e todas
elas.

**Por quê.** O conjunto de tipos é aberto: cada integração declara os seus, e
o catálogo do console não tem como conhecer de antemão o tipo que a próxima
trouxer. Um substantivo traduzido por tipo é um catálogo que envelhece na
primeira integração nova, e o que ele imprime nesse dia é a chave crua no
meio de palavras — exatamente o defeito que a tradução existia para evitar,
só que intermitente. A palavra do estate é também a que toda outra tela
mostra para o mesmo recurso, então ela concorda com `/resources` em vez de
divergir dele em um lugar só.

Cortar em três, como o board faz, é o que sobra a decidir; hoje a legenda
mostra todos. Fica registrado porque é desvio visível, não porque esteja
resolvido.

## 12. O chip de estado do assunto diz a palavra do deployment

O board escreve `investigando` e `resolvido` nos chips de "O que insiste em
acontecer". O console escreve a palavra que a API mandou, capitalizada —
`Investigating`, `Resolved` — inclusive num console em pt-BR.

**Por quê.** `Badge` (`console/src/components/status.tsx`) é declaradamente o
único chip que carrega uma palavra escrita pelo deployment e não escolhida
por este console: um estado que a enumeração local não conhece aparece com o
papel neutro e o texto que veio, em vez de em branco ou como erro. Traduzir
aqui significa ou uma tabela que cala o que não conhece, ou duas fontes para
a mesma palavra.

**Onde isso se decide, e não é aqui.** O vocabulário de status é da fundação
visual, e o mesmo chip aparece em `/incidents`, `/runs` e `/decisions`. A
050 não muda o vocabulário de estado de toda a UI a partir de uma tela; se o
operador quiser as palavras do board, o conserto é da fundação — um rótulo
por estado conhecido, com a palavra crua como degradação — e vale para todas
as telas de uma vez.

**O custo, dito por inteiro**: numa tela em pt-BR, o chip é a única palavra
em inglês da linha.

---

# Varredura do Painel, 2026-08-31

O que segue saiu de uma comparação elemento a elemento do Painel contra
`DashboardLight.dc.html` e `Main.dc.html` — os dois são o mesmo board, com uma
única diferença fora de cor no diff inteiro (`.card` tem `box-shadow` no claro
e nenhuma no escuro). Três rodadas anteriores nesta tela compararam por
reação, item a item conforme se notava, e o operador achou mais divergências a
olho depois de cada uma. Esta enumerou primeiro e decidiu depois: 38 itens,
dos quais 8 viraram conserto, 20 entram aqui, 7 são de outra feature e 3 são
diferença de dado, não de código.

Uma nota que vale para tudo abaixo: **dado de staging não é divergência.** O
board desenha sete assuntos recorrentes e o deployment tem três; desenha um
run em voo e a captura tem zero. Onde a diferença vem do que o estate contém,
está dito, e não foi "consertado".

## 13. Contagens da barra lateral e do sino não contam o que o agente segura

O board mostra `Incidentes 4` na navegação e um badge no sino. O console não
mostra nenhum dos dois, porque `countsFrom`
(`console/src/shell/load.ts:305-319`) deriva as contagens da listagem de
atenção, e o commit `d019dd77` estreitou essa listagem deliberadamente a
`open` e `awaiting_human`.

**Por quê.** O raciocínio daquele commit é explícito e é bom: um produto que
investiga sozinho não deve contar o próprio trabalho como pendência de quem
olha. Um incidente em `investigating` ou `remediating` está sendo tratado pelo
agente — colocá-lo num badge é pedir atenção para o que já tem dono, e o badge
que pede atenção sem motivo é o badge que ninguém olha na terceira semana.

**O custo, dito por inteiro**: a navegação fica sem número numa tela onde o
board tem dois, e quem quiser saber quantos incidentes existem ao todo tem que
abrir `/incidents`. O comportamento **não muda**; fica registrado porque é
desvio visível do board e porque a próxima varredura ia reencontrá-lo.

## 14. Um tratamento de contagem para toda área, não um por área

O board pinta as duas contagens da navegação de formas diferentes: `Incidentes`
é texto mono cru em vermelho, sem pílula; `Decisões` é uma pílula sólida âmbar
com texto branco. O sino ganha uma terceira variação — pílula sólida âmbar,
texto branco, 9,5px.

O console desenha as três iguais: a pílula suave da fundação
(`bg-danger-bg text-danger`, `console/src/shell/sidebar.tsx:213`) na navegação,
e `bg-danger` no sino (`console/src/shell/topbar.tsx:186`).

**Por quê.** As três contam a mesma coisa — quantos itens de uma área esperam
uma pessoa — e três desenhos para um fato são três coisas para reconciliar
quando uma quarta área ganhar contagem. A pílula é o tratamento de contagem da
fundação e vale para as dezoito áreas, incluindo as que ainda não existem.

## 15. Nenhuma marca de "tem coisa rodando" por área na navegação

O board põe um losango de 8px à direita de `Investigações`, que é o vocabulário
dele para "há trabalho em voo aqui". O console não tem marca por área: o
`nav-arriving` (`console/src/shell/sidebar.tsx:118-126`) só pulsa durante uma
navegação, que é outro fato.

**Por quê.** É a mesma regra dos registros 3 e 10 — um portador de frescor por
quadro. A banda "Em execução agora" está na mesma tela dizendo, com nome e
barra de estágio, exatamente o que está rodando; um losango na navegação dizendo
de novo é uma segunda afirmação que discorda da primeira sempre que uma das
duas chega antes.

## 16. O rótulo de grupo da navegação não é caixa alta

O board escreve `AGORA`, `AMBIENTE`, `CONFIGURAÇÃO` a 10,5px com
`letter-spacing: .1em` e `text-transform: uppercase`. O console usa o degrau
`micro` da escala (11px/600, sem tracking, sem caixa alta) —
`console/src/shell/sidebar.tsx:170`.

**Por quê.** `micro` é o degrau declarado para exatamente este papel, e a
escala de tipo não abre exceção por tela. Caixa alta com tracking é um quarto
tratamento tipográfico que só existiria aqui.

## 17. A busca diz "Procurar", sem reticências

Board: `Buscar recursos, investigações, incidentes…`. Console:
`Procurar recursos, investigações, incidentes` (`shell.search`).

**Por quê.** É a mesma string que a paleta de comandos usa, e ela é
alcançável de toda tela por `Ctrl K`. Duas palavras para a mesma caixa, uma na
topbar e outra na paleta, é pior que a palavra que o board não escolheu. As
reticências prometem um menu que abre digitando, o que a paleta faz — e a
topbar, que só abre a paleta, não deve prometê-lo duas vezes.

## 18. A topbar carrega dois controles que o board não desenha

O board desenha, à direita da busca: chip "Ao vivo", ícone de tema, sino,
"Parar automação", "Investigar", avatar. O console carrega ainda o **nome do
deployment** (`console/src/shell/topbar.tsx:126-131`) e o **alternador de
densidade** (`:154-173`).

**Por quê.** O nome existe porque um operador com três deployments abertos tem
três abas, e uma aba que diz só "Painel" é uma aba onde ele age por engano — o
mesmo motivo pelo qual o `<title>` carrega o deployment. A densidade fica ao
lado do tema porque são a mesma classe de coisa: como este leitor lê, guardado
para ele, sem mudar nada que outra pessoa veja. Nenhum dos dois é da 050; os
dois aparecem em toda rota.

## 19. O avatar é azul, não verde

Board: círculo de 30px preenchido com o acento, iniciais em branco. Console:
`bg-info-bg text-info` a `size-5` (`console/src/components/navigation.tsx:343`).

**Por quê.** O acento neste console significa **interação** — é a cor do que se
clica. Um avatar preenchido de acento é uma superfície que promete uma ação que
ela não tem (o menu abre no `summary`, não no círculo). `info` é o papel que a
fundação já usa para "isto é uma pessoa", e o avatar aparece em toda tela.

## 20. O subtítulo do Painel não é palavra por palavra o do board

Board: `O que precisa de alguém, o que está rodando, e como o ambiente está.`
Console (`page.dashboard.context`): `O que precisa de uma pessoa, o que está em
curso e como está o parque.`

**Por quê.** A substância é a mesma e a fonte é o inglês (`What needs a person,
what is running, and how the estate is.`), do qual o pt-BR é tradução — o
registro 6 já diz que este console é i18n e que as strings do board entram como
pt-BR. `parque` é a palavra que o catálogo usa para *estate* em todas as telas;
trocá-la aqui faria o Painel discordar de `/resources` e de `/incidents` numa
palavra só.

## 21. O cabeçalho da banda e os títulos de painel usam o degrau `strong`

O board escreve `Em execução agora` a 14px/600 e os títulos de painel a 15px/600
em Space Grotesk (`class="sg"`). O console usa `text-strong` — 16px/600, IBM
Plex Sans, porque `text-strong` carrega tamanho e peso e não família
(`console/src/design/tokens.ts:408`).

**Por quê.** `strong` é o degrau declarado para o título de uma região, e ele
titula região em dezoito telas. Um tamanho por tela é a escala de tipo deixando
de ser escala. A família display fica onde a fundação a pôs: no título da
página e nos números dos KPIs, que é onde ela vende.

## 22. O card de run não ganha um chip "agora mesmo", e todos têm a mesma superfície

O board dá ao run recém-chegado um chip `agora mesmo`, uma borda de acento, um
anel e uma sombra; aos demais, fundo rebaixado e borda comum. O console desenha
todo card igual (`bg-raised`, `console/src/surfaces/run-band.tsx:152`) e marca a
chegada só com `slide-in`.

**Por quê.** O chip é um terceiro indicador de frescor na mesma tela, que é o
que o registro 10 já recusou duas vezes; e a idade relativa já está no card, no
tempo decorrido. A animação de chegada é o que diz "isto acabou de entrar", ela
toca só na montagem real do nó, e ela some sozinha — que é exatamente o que uma
afirmação sobre "agora" deve fazer, ao contrário de um chip que continua dizendo
`agora mesmo` cinco minutos depois.

## 23. A idade e o risco da decisão não cabem numa linha de metadados

O board escreve, sob o título, `remediação reversível · risco 3 de 5 ·
esperando há 1 h` — uma linha, texto corrido. O console põe a idade no canto
superior direito do card e o risco na própria linha, como `RiskLadder`
(`console/src/surfaces/attention.tsx:106-118`).

**Por quê.** A FR-009 exige o risco como **medidor de cinco posições**, e um
medidor não é texto: "risco 3 de 5" escrito por extenso é a mesma informação
sem a comparação visual que faz alguém parar antes de aprovar o quarto. **O
requisito ganha do artboard**, e este é o caso em que ele ganha.

## 24. "Ver plano →" é link, não chip

O board desenha os três controles do card como chips do mesmo tamanho:
`Aprovar` preenchido, `Recusar` vazado, `Ver plano →` vazado. No console os
dois primeiros são botões e o terceiro é um link
(`console/src/surfaces/attention.tsx:160-166`).

**Por quê.** Dois deles decidem e um navega, e este console não desenha
navegação como botão — é a lição que `panel.tsx` já registrou por escrito ao
aposentar o botão-com-âncora-escondida de todo estado vazio. Um chip que parece
com "Aprovar" e leva para outra tela é a forma de errar que a diferença existe
para evitar.

## 25. A legenda "nenhum detector" é acento, não âmbar

Board: `nenhum detector promove a incidente` em `#8a5a12`. Console: a mesma
frase em `text-accent`, porque ela é o único link daquele tile
(`console/src/surfaces/kpi-tiles.tsx:231-238`).

**Por quê.** Acento significa interação neste console e a frase leva a
`/config?tab=detectors`. Pintá-la de âmbar faria um link ler diferente de todos
os outros links da página, e a cor do estado passaria a competir com a cor do
que se clica.

## 26. A unidade não encolhe dentro do número

O board escreve `100` a 30px com `%` a 18px, e `1m 15s` com o `m` e o `s` a
18px. O console encolhe só o `%` (`text-meta`) e deixa a duração inteira no
tamanho do número, porque ela vem de `formatDuration`.

**Por quê.** `formatDuration` é o formatador compartilhado; partir a string
por unidade dentro deste componente é um segundo vocabulário de duração, e o
console tem durações em run view, em incidentes e em decisões, todas por ele.

## 27. O total do painel fica à direita, não colado ao título

Board: `O que insiste em acontecer` e `7 assuntos · 40 disparos · agrupado por
assunto` adjacentes, na mesma linha de base, com 10px entre eles. Console: o
total vai para o slot `action` de `Panel`, que é alinhado à direita
(`console/src/surfaces/panel.tsx:172`).

**Por quê.** O slot `action` é alinhado à direita em 32 rotas. Uma exceção por
tela é uma segunda gramática de painel, e a gramática de painel é o que faz
seis regiões independentes lerem como uma página.

## 28. A linha de disparos é desenhada também no assunto encerrado

O board omite a mini-linha do tempo nas linhas resolvidas. O console desenha em
todas (`console/src/surfaces/subject-strip.tsx:109-116`).

**Por quê.** A AN-11 exige a mini-linha do tempo por assunto, e um assunto que
disparou sete vezes e parou é exatamente o caso em que *quando* ele disparou é
a informação toda — foi de hora em hora ontem, ou uma vez por mês desde março?
A linha é o único lugar da tela que responde. **O requisito ganha do artboard.**

## 29. As entradas da atividade ficam separadas por um fio

O board separa as entradas pelo trilho vertical, e nada mais. Sem o trilho
(registro 9), o console mantém o fio de 1px entre entradas
(`console/src/surfaces/activity-feed.tsx:116`).

**Por quê.** É o que sobrou de estrutura na coluna. Oito entradas de duas
linhas cada, sem trilho e sem fio, leem como um parágrafo. O fio cai junto com
o registro 9, no dia em que a escala ganhar o degrau que o trilho precisa.

## 30. O ícone de parada entra num controle que aparece em toda tela

O board desenha um quadrado dentro de um círculo antes de `Parar automação`. O
console não desenhava ícone nenhum; agora desenha (`StopIcon`,
`console/src/design/icons.tsx`), e o controle mora na topbar, não no Painel.

**Por quê o conserto mesmo sendo território do shell.** A regra que ele
restabelece não é do board: é a regra de que cor nunca carrega significado
sozinha. O botão de parada era o único controle destrutivo do console
identificado apenas por ser vermelho. O acréscimo é um glifo aditivo, não muda
comportamento, não muda a superfície de props de nenhum export, e
`icon-export-surface.test.tsx` — que existe para provar que nada foi renomeado
nem removido — recebeu o nome novo explicitamente no fim da lista.

**O que isto arrasta**: o ícone aparece em toda rota, porque o controle
aparece em toda rota. Está dito aqui para que não seja redescoberto como
efeito colateral do Painel.

## 31. Quatro itens da tela pertencem à fundação e não foram tocados

Ficam nomeados, com dono, porque uma varredura que os omitisse faria a próxima
recomeçar por eles:

| O que o board faz | O que o console faz | Dono |
|---|---|---|
| Cabeçalho de página sem ícone, título e subtítulo na mesma linha de base (idêntico em `Incidents`, `Resources`, `Investigations`) | `PageHeader` desenha um poço de ícone em acento e empilha título sobre subtítulo (`console/src/components/layout.tsx:60-79`) | fundação visual — 32 rotas |
| Sem fio entre o cabeçalho do card e o corpo | `Panel` desenha o fio (`console/src/surfaces/panel.tsx:163`) | fundação visual |
| Lavagem radial de acento no fundo do quadro, `padding 24px 28px` no conteúdo | sem lavagem, `p-5` (`console/src/shell/shell.tsx:283`) | shell |
| Quadro de 1080px sem rolagem, com a última linha em `flex: 1` | a página rola | modelo de rolagem do shell — `scroll-budget.spec.ts` |

## 32. Um assunto pode aparecer com a chave crua do deployment

Na captura de staging, duas linhas de "O que insiste em acontecer" têm por
subtítulo `unresolved-target:traefik.lan.kyo.ninja · Traefik Dashbo…`. O
prefixo `unresolved-target:` é a chave que o próprio deployment grava quando
não resolve o alvo do alerta, e `isOpaque`
(`console/src/surfaces/incident-group-list.tsx:170-204`) não a considera
identificador interno — ela nomeia o host, então passa.

Não foi mexido aqui: `incident-group-list.tsx` é da 060 e a suíte dela já está
vermelha por motivo independente. Fica nomeado para a 060 decidir se
`unresolved-target:` é palavra de máquina que a FR-024 devia barrar.
