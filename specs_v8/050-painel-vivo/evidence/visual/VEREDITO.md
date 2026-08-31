# Veredito visual — 050 Painel vivo, slot S3

Feito no Orca Browser contra o staging (`https://stg-ninjasre.lan.kyo.ninja/`),
depois do deploy dos três componentes e das rotas aquecidas, com um run vivo
na tela. Locale pt-BR, escolhido pelo cookie `ninjasre_locale` — que é como um
leitor troca de idioma, e o que `requestLocale` prefere sobre o
`accept-language`. O `DEFAULT_LOCALE` do console é `en`, então a primeira
renderização em inglês era o comportamento correto e não um defeito.

| Tela | Tema | Veredito |
|---|---|---|
| `/` | dark | **DESVIO** — um, nomeado abaixo. Todo o resto confere. |
| `/` | light | **DESVIO** — o mesmo, e nada além dele. |

## O desvio

**"O que continua acontecendo" onde o board manda "O que insiste em acontecer".**

O board diz a frase nos dois artboards (`Main.dc.html`, `DashboardLight.dc.html`).
A própria spec da 050 a repete sete vezes, entre elas a AN-11 e a SC-006. O
console desenhava outra, e nada em `DIVERGENCIAS.md` registra a troca — e
desvio sem registro aprovado é FAIL de slot pelo §3 do `EXECUCAO.md`.

Passou por baixo da suíte porque **nenhum teste afirma o nome da seção**: a
AN-11 e as vizinhas localizam o painel por `data-testid`. A suíte ficava verde
enquanto a tela dizia outra coisa — a mesma família de "medir nada" que esta
onda vem encontrando.

O comentário de seção do próprio catálogo pt-BR, na linha 599, ainda diz
"O que insiste em acontecer". A string embaixo dele discordava do seu próprio
cabeçalho.

Corrigido pelo lead em `pt-BR.ts:800`, como dono do single-write de i18n no
merge. A asserção sobre o título existe agora — `console/tests/e2e/
painel-vivo.acceptance.spec.ts` (commit `ec1d8336`), o teste
`'AN-11: the panel is named "O que insiste em acontecer", in the board's own
words'`: troca para o cookie `ninjasre_locale=pt-BR`, abre `/` e lê o `<h3>`
de nível 3 dentro de `data-testid="recurring-problems"`, sem guarda de skip
— uma janela sem recorrências ainda renderiza o cabeçalho, então o teste
segue sendo uma asserção real mesmo vazia. É exatamente o que falhava antes
dela existir: com a grafia antiga restaurada a alegação falha citando o
`<h3>` que de fato encontrou, e o portão não pode mais fechar verde com o
nome errado. O par em inglês fica como está: o item 6 do `DIVERGENCIAS.md`
deixa o inglês livre.

## O que confere

- Todas as seções que a spec nomeia estão lá e com dado real, nos dois temas:
  a banda de execução com cartão vivo, a banda "Precisa de você", os cinco KPIs
  com valor, sparkline e legenda de decomposição, o agrupamento por assunto e a
  linha do tempo de atividade ao vivo.
- Os seis segmentos de estágio da AN-03 aparecem no cartão vivo, com o atual
  distinto do concluído e do futuro — visível nas duas capturas.
- O cartão é titulado pelo objetivo digitado, palavra por palavra: a alegação
  da 020 vista na tela, não no banco.
- O chip de frescor foi apanhado nos dois estados entre as duas capturas
  ("Ao vivo" e "Atualizando").

## Observações que não são defeitos desta feature

- Os chips de assunto dizem "Resolved" num console em pt-BR. É deliberado e
  documentado: `status.tsx:192` diz que o `Badge` é "o único chip que carrega
  uma palavra que o deployment escreveu, não uma que este console escolheu".
  Vale decisão do operador só porque a mesma palavra sai "Resolvido" em
  `/incidents` — duas telas nomeando uma coisa de dois jeitos.
- `dashboard.kpi.sparkline.label` é `'Tendência de {count} dias'`, então com
  `count=1` anuncia "Tendência de 1 dias". É nome acessível da sparkline, não
  texto desenhado, então não afeta a comparação com o artboard — mas é erro de
  concordância de verdade, numa chave da própria 050.

## Evidência

- `dashboard-dark.png` — `/`, tema escuro, run vivo aos 46s
- `dashboard-light.png` — `/`, tema claro, run vivo aos 26s

Ambas com o run `0a8e5cb259614ac7baeaaea1bc0566e8`, o único criado no slot.
