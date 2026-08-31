# Veredito visual — 050 Painel vivo, slot S3

Orca Browser contra o staging (`https://stg-ninjasre.lan.kyo.ninja/`), depois
do deploy dos três componentes, da geração de pods confirmada por listagem
(20:08:01Z, sem sobra da anterior) e das nove rotas aquecidas autenticadas.
Locale pt-BR pelo cookie `ninjasre_locale`, que é como um leitor troca de
idioma. O `DEFAULT_LOCALE` do console é `en`, então a primeira renderização em
inglês era comportamento correto, não defeito.

| Tela | Tema | Veredito |
|---|---|---|
| `/` | dark | **DESVIO** — a composição confere; o detalhe ainda não |
| `/` | light | **DESVIO** — idem |

**O CONFORME anterior foi revertido, e a razão importa mais que o veredito.**
Três rodadas seguidas deste gate acharam alguns desvios, consertaram, e
declararam a tela conforme — e o operador achou mais, de olho, nas três. O
defeito não estava na tela, estava no método: comparação reativa, item a item,
conforme alguém repara. A varredura sistemática — enumerar tudo primeiro,
decidir depois, consertar por último — está em curso, e este veredito só volta
a CONFORME quando existir a tabela elemento a elemento que a sustente.

Desvios confirmados e ainda abertos nesta terceira rodada: o chip
"Parar automação" não desenha o ícone que o board desenha; e cada entrada da
atividade ao vivo carrega só o tempo relativo, onde o board dá
`há 2 min · investigação · 1m 27s` — tempo, tipo e duração.

E um que **não** é desvio, mas precisa de registro: o contador da barra lateral
e o badge do sino não contam incidentes em `investigating`/`remediating`. É
deliberado, do commit `d019dd77`, cuja razão está escrita nele — um produto
cuja alegação é investigar sem você não deve contar o próprio trabalho como o
seu backlog.

Cada tema foi nomeado pelo valor **medido** de `data-theme`, não pelo
presumido. Na primeira rodada deste gate os dois arquivos saíram trocados
justamente por presunção.

## O que este gate achou com a suíte verde

Três defeitos reais, nenhum deles visível a um teste que passava.

**1. O título da seção.** O board e a própria spec (AN-11, SC-006, sete
menções) dizem "O que insiste em acontecer"; o console dizia "O que continua
acontecendo", sem registro em `DIVERGENCIAS.md`. Nenhum teste afirmava o nome
da seção. E, mais fundo: `playwright.config.ts:40` fixa `locale: 'en-GB'`, de
modo que **nenhum teste e2e conseguia ver uma string em pt-BR** — a superfície
inteira de conformidade com o artboard era invisível ao Playwright por
construção. Achado de onda, não da 050.

**2. O identificador cru como texto de linha.** A linha lia `res-76ab1466…`.
O primeiro reparo resolveu o nome do estate e ela passou a `pve01 ·
res-76ab1466…` — e a AN-12 **ficou verde**, porque seu regex era ancorado em
`^res-` e o nome entrou na frente. O defeito andou de lado. A SC-007 proíbe o
padrão em *qualquer texto visível*; a FR-024 diz que o identificador aparece no
máximo como tooltip. Segundo reparo, e asserção reescrita sem âncora.

**3. A composição.** O board põe "O que insiste em acontecer" e "Atividade ao
vivo" lado a lado; o console empilhava. Faltavam o contador do cabeçalho, os
dois rodapés e o `todas as investigações →`. E o limite de **5 assuntos** que a
spec exige na linha 486 nunca tinha sido implementado — os outros dois limites
existiam como constante nomeada, esse não, então o painel desenhava todos.

## Conferido na tela, nesta captura

- Duas colunas, "O que insiste em acontecer" ao lado de "Atividade ao vivo".
- Cabeçalho com `3 assuntos · 7 disparos · agrupado por assunto`, onde a soma
  dos disparos vem dos mesmos `count` que as linhas imprimem como `N×` — então
  cabeçalho e linhas não podem discordar.
- `ver os 3 assuntos →` e `linha do tempo completa →`.
- `todas as investigações →` na banda de execução.
- Marca de status à esquerda de cada assunto.
- Sparkline por assunto em eixo fixo, não mais `occurrences.length * 6` — que
  dava 12 pixels a um assunto de dois disparos e punha duas linhas em escalas
  diferentes.
- Zero ocorrências de `res-[0-9a-f]{8}` e de hex ≥16 no snapshot inteiro.
- "Ações rápidas" ausente, e a remoção foi decidida com razão verificada:
  `/knowledge` duplica entrada permanente da barra lateral, e `/autonomy` é
  rota aposentada (`routes.ts:318`, `visible: () => false`) que o
  `GuardianFooter` alcança do rodapé de toda página. Nenhum destino se perde.

## Onde o dado vivo difere do artboard, e isso não é desvio

O §3 do `EXECUCAO.md` manda dizer isto explicitamente. O board desenha 5
assuntos e 6 entradas de atividade, com as duas colunas de altura parecida. O
staging tem 3 assuntos e 8 entradas, então a coluna da esquerda termina bem
antes da direita e sobra um vazio grande. **É o dado, não a composição** — com
5 assuntos as colunas se aproximam. Registro para que ninguém leia o vazio como
defeito de layout depois.

## Divergências registradas nesta rodada

`design/padrao-2026-08/DIVERGENCIAS.md`, entradas 9–12: o trilho vertical
ausente no feed; o chip `stream` e a legenda `atualizado por eventos` recusados
sob a regra de um indicador de frescor por página; a decomposição de
`Recursos vigiados` imprimindo as palavras do próprio estate, porque o conjunto
de tipos é aberto por integração; e o chip `Resolved`, que **não** foi
consertado de propósito — o vocabulário de status é da fundação e o mesmo chip
está em `/incidents`, `/runs` e `/decisions`.

## Evidência

| Arquivo | O que mostra | De que é evidência |
|---|---|---|
| `dashboard-dark.png` | `/`, escuro, layout conformado | composição, contador, rodapés, SC-007 |
| `dashboard-light.png` | `/`, claro, layout conformado | idem |
| `dashboard-dark-live-run.png` | `/`, escuro, run vivo aos 46s | **só** AN-01/AN-02/AN-03 |
| `dashboard-light-live-run.png` | `/`, claro, run vivo aos 26s | idem |
| `ARTBOARD-DashboardLight.png` | o board renderizado | o termo de comparação |

**As duas capturas com cartão vivo são anteriores aos consertos** — de 16:48.
Elas mostram o título antigo e o id cru, isto é, os defeitos que este gate
depois fechou, e **não** valem como evidência da SC-007 nem da AN-11. Ficam
porque são a única evidência do cartão vivo e dos seis segmentos, e porque
registram o "antes". Não foram recapturadas porque o §4 do `EXECUCAO.md` dá um
run por slot e ele já foi gasto.

Uma versão anterior deste arquivo listava os quatro juntos sob uma frase que
afirmava zero ocorrências do id cru. Dois dos quatro exibiam o id cru. Um
verifier independente pegou.
