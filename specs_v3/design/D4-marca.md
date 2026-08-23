# D4 — A marca

## A ideia

**Um shuriken. Oito pontas iguais, e o furo.**

O objeto que diz ninja sem precisar de legenda, desenhado como emblema e não
como ilustração: geometria pura, uma cor, simetria de oito.

O furo não é detalhe — é o que faz a forma ser **um objeto** e não um enfeite.
Uma estrela cheia é brilho; uma estrela com furo é uma coisa que alguém segura.

## Por que oito pontas, e não quatro

Esta foi a decisão do desenho, e ela só apareceu quando as duas ficaram lado a
lado em quatro tamanhos.

**Quatro pontas em diagonal é a forma que virou padrão de "produto com IA".**
Reduzida a 16px ela devolve exatamente esse brilho, e uma marca que se confunde
com metade da categoria não está marcando nada.

**Oito pontas com furo não lê como brilho em tamanho nenhum.** É a silhueta do
shuriken de verdade, e sobrevive ao item de menu.

A proporção do entalhe foi calibrada renderizando três razões juntas, e o
resultado contrariou o palpite:

| Razão interno/externo | O que vira |
|---|---|
| 0,36 — entalhe fundo | o brilho-clichê |
| 0,44 — médio | ainda brilho, com cintura |
| 0,52 — raso | losango com furo |
| **0,48 em oito pontas** | **shuriken** |

## O que mais foi desenhado e recusado

Sete alternativas, em três rodadas, todas renderizadas em quatro tamanhos e nos
dois temas antes de julgar:

- **Lâmina gestual com um ponto** — bonita e com o DNA da referência que inspirou
  o exercício, mas dizia "corte", não "ninja". Foi a primeira escolha e caiu
  quando o critério passou a ser evocar shinobi.
- **Shuriken de seis pontas** — lê como Estrela de Davi. Recusada de imediato.
- **Capuz shinobi, fresta reta** — vira cápsula com listra.
- **Capuz, fresta em lente** — vira grão de café.
- **Faixa dos olhos** — lê como máscara de bandido, e infantiliza uma ferramenta
  de operação.
- **Quatro lâminas com entalhe raso** — losango.
- **Pinwheel de braços dobrados** — nunca chegou a ser desenhado, e não deve
  ser: quatro braços dobrados em rotação leem como suástica.

## Os arquivos

```
mark.svg          a marca. Acima de 24px.
mark-small.svg    o corte óptico. 24px e abaixo: favicon, menu, avatar.
emblem.svg        o selo — a marca dentro de um anel. Acima de 32px.
lockup.svg        marca + nome, horizontal.
```

**Dois cortes, uma marca.** Reduzir o corte principal a 16px afila as oito
pontas até elas se fecharem umas nas outras, e o furo some — o desenho vira uma
mancha redonda. O corte pequeno tem pontas mais grossas (razão 0,53) e furo
maior do que a redução proporcional pediria. Mesma lógica de um tipo de letra ter
corte de texto e corte de display; usar o corte errado é o erro mais provável e é
o que a revisão procura primeiro.

**O selo não é uma segunda marca.** É a forma heráldica japonesa — uma figura
dentro de um círculo vira crista. Serve onde a marca precisa ler como emblema e
não como ícone de interface: capa de documento, adesivo, avatar grande. Nunca
abaixo de 32px, porque o anel e as pontas se encontram antes disso.

## Cor

A marca não tem cor própria. É desenhada em `currentColor` e herda:

| Contexto | Cor |
|---|---|
| tema claro | `--accent` (`#0f6f5c`) |
| tema escuro | `--accent` (`#4fd6b0`) |
| sobre o acento | `--on-accent` |
| impressão, uma cor | preto ou branco integral |

Nunca em gradiente, nunca com sombra, nunca com duas cores dentro do próprio
desenho. O contraste da marca contra o fundo segue a mesma verificação que o
resto do sistema já roda — a marca não é exceção por ser marca.

## Área de respiro e tamanho mínimo

- **Respiro**: metade da altura da marca em todos os lados. Nada entra nessa
  faixa, inclusive a borda do container.
- **Mínimo**: 16px, com o corte pequeno.
- **Rotação**: proibida. Um shuriken girado parece um erro de renderização, não
  um movimento — e a simetria de oito faz qualquer ângulo parecer quase-certo.
- **Lockup**: o nome nunca é redesenhado, reespaçado ou recomposto em coluna. Se
  não couber horizontal, usa-se a marca sozinha.

## O nome escrito

`NinjaSRE` — uma palavra, sem espaço, sem hífen, `S`, `R` e `E` maiúsculos.

No lockup, `Ninja` no peso do texto e `SRE` no acento. A cor não decora: separa
o nome próprio do que a coisa é. Em contexto de uma cor só, o `SRE` fica no mesmo
peso e a distinção desaparece — perda aceitável.

A família é a do sistema, como todo o resto do produto. **Nenhuma fonte é
buscada.** Um deployment fechado, sem saída para a internet, não pode depender de
um servidor de fontes para renderizar a própria marca — e este produto é
instalado exatamente nesses lugares.

## Onde os arquivos vão morar

Hoje estão em `specs_v3/design/brand/`, que é material de planejamento e não é
versionado. Aprovada a marca, mudam-se para `console/public/brand/` e viram parte
do produto, junto com o favicon derivado do corte pequeno.
