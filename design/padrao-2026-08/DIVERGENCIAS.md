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
