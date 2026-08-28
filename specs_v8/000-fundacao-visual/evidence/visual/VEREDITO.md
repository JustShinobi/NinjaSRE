# Veredito visual — 000-fundacao-visual

Revisão feita pelo modelo no Orca Browser, contra o staging real
(`https://stg-ninjasre.lan.kyo.ninja/`), com o build desta feature confirmado
no cluster: pod `web` rodando o digest `ceb807791af046e3…`, o mesmo publicado
pelo `make deploy-stg` deste slot, iniciado às 01:58:38Z. Não é uma inferência
de "Synced/Healthy" — é o digest conferido.

Temas alternados **pelo botão de tema da topbar**, nunca por `data-theme`
injetado: o botão faz parte do que se valida, e clicá-lo levou
`--accent` de `#0a7452` para `#3ad195` e o fundo de `#f2f6f4` para `#0a100e`
sem recarregar a página.

| Captura | Artboard comparado |
|---|---|
| `shell-dark.png` | `design/padrao-2026-08/Main.dc.html` |
| `shell-light.png` | `design/padrao-2026-08/DashboardLight.dc.html` |

## Veredito por tela × tema

| Tela × tema | Veredito |
|---|---|
| `/` dark | **CONFORME** |
| `/` light | **CONFORME** |

Houve um desvio na primeira passagem — o controle destrutivo vinha
preenchido onde o board o desenha tingido. Foi **corrigido**, não
registrado: o operador aprovou alinhar ao artboard e deixou a regra
permanente ("na dúvida o artboard sempre ganha"). O item 1 abaixo fica como
o registro do que foi encontrado e do que se fez.

As capturas desta pasta são as de **depois** da correção, tiradas contra o
digest `1a528388…`, com o rollout confirmado terminado (`kubectl rollout
status`) para que nenhuma medição caísse no pod antigo — havia dois `web`
no ar durante a substituição.

## O que confere, medido e não impressionista

Valores lidos do DOM servido pelo staging, não do source:

| Alegação | Medido em staging |
|---|---|
| Paleta dark | `sunken` `rgb(10,16,14)` = `#0a100e`; `accent` `#3ad195` |
| Paleta light | `sunken` `rgb(242,246,244)` = `#f2f6f4`; `accent` `#0a7452` |
| `border-strong` do board preservado | `#35493f` no dark — a decisão do operador chegou ao build servido, não só ao source |
| Corpo em IBM Plex Sans | `font-family` computado começa em `"IBM Plex Sans"` |
| Sidebar 232px | `nav` mede exatamente `232` |
| Troca de tema sem reload | `--accent` muda em lugar, sem navegação |

E, conferido nas capturas contra os artboards: os três grupos da sidebar
("Agora/Ambiente/Configuração" ↔ "Now/The environment/Configuration"), o item
ativo com fundo accent + texto accent + barra interna, o rodapé do guardião
com a marca redonda, o logotipo shuriken + "Ninja"/"SRE", H1 e números de KPI
na família display visivelmente mais pesados que o corpo, chips de status com
contorno na própria cor (Critical, Investigating, Resolved), e os raios da
escala nos cartões e chips. Ícones no traço fino do board — relógio em
Incidentes, lupa em Investigações, escudo em Decisões.

## 1. Desvio encontrado e corrigido: o controle destrutivo vinha preenchido

**O que o board manda.** `Main.dc.html` desenha "Parar automação" como chip
tingido: `background: #2a1616` (`danger-bg`), `color: #ef7070` (`danger`),
borda `#5c2525`. O `DashboardLight.dc.html` faz o equivalente no claro.

**O que o staging serve.** Medido no DOM: `background rgb(239,112,112)`
(`#ef7070`, o `danger`), `color rgb(42,22,22)` (`#2a1616`). Os mesmos dois
tokens, com os papéis **invertidos** — o fundo virou o texto e o texto virou
o fundo. Nos dois temas.

**Onde mora.** `console/src/components/action.tsx:54`:
`destructive: 'bg-danger text-on-danger border-danger …'`. Não é estilo da
topbar: é a variante compartilhada do `Button`, usada por todo botão
destrutivo do console. O tratamento tingido que o board pede já existe na
casa — `components/status.tsx:69` e `components/feedback.tsx:163` escrevem
exatamente `bg-danger-bg text-danger border-danger`.

**Por que não corrigi sozinho.** `components/action.tsx` não está na lista de
arquivos desta feature, e mudar a variante muda todo botão destrutivo do
console — inclusive em telas que não têm artboard, que a decisão 8 do README
manda não reformar. Há leitura defensável dos dois lados: a decisão 8 também
diz que toda tela recebe de graça "tokens, fontes, ícones, chips e shell
compartilhados", e a pele de um botão destrutivo é vocabulário compartilhado
como um chip. É uma decisão do operador, não minha.

**O que foi feito.** O operador aprovou alinhar ao artboard.
`action.tsx:54` passou a `bg-danger-bg text-danger border-danger`, 35
baselines foram recapturadas (o controle vive no shell, logo está em toda
tela), e a mudança foi conferida no staging real depois do redeploy:

| Medida | Antes | Depois (staging, digest `1a528388…`) |
|---|---|---|
| fundo | `rgb(239,112,112)` = `danger` | `rgb(42,22,22)` = `danger-bg` |
| texto | `rgb(42,22,22)` | `rgb(239,112,112)` = `danger` |

Confere com o artboard nos dois temas. O `Investigar` ao lado continua
preenchido no accent, que é como o artboard também o desenha — a correção
não o arrastou junto.

## O que **não** é desvio, e por que

**A estrutura do Painel.** O artboard mostra a banda "Em execução agora" com
barras de estágio, sparklines nos KPIs, mini-timeline de disparos por assunto,
"Atividade ao vivo" como linha do tempo, e a banda de aprovação com
Aprovar/Recusar/Ver plano em linha. O staging não mostra nada disso, e está
certo: pela decisão 8, a 000 entrega vocabulário e **nada estrutural**. Essas
bandas são da 050-painel-vivo, da 040-decisoes-estruturadas e da
060-telas-de-area. Registrar a ausência delas como desvio da 000 seria cobrar
desta feature o trabalho de três outras.

**Os números e os textos.** O artboard tem 99 recursos, 14 degradados, 7
assuntos; o staging tem 95, 9 e 10. O artboard está em pt-BR e o console em
inglês nesta sessão. Diferença de dado e de idioma, não de desenho — o
console é i18n por contrato e as strings do board entram como o par pt-BR.

**Controles a mais na topbar.** O staging tem "Compact rows" e o nome do
deployment, que o artboard não desenha. São pré-existentes; a 000 tinha
ordem de não acrescentar nem remover controle, e não o fez. O artboard é um
mockup do desenho, não um inventário de controles.

## Fora do escopo, registrado para não sumir

As duas capturas de `/resources` não foram recapturadas no gate de baseline:
a lista daquela tela limita a própria altura e rola por dentro, então
nenhuma janela mais alta satisfaz o harness — cerca de 3160px de estouro,
que nenhuma troca de tipografia produz. A tela, a altura de linha e o
harness estão todos intocados por esta feature. O reparo é de quem for dono
de `/resources`, na 060.

## 2. Achado que fica em aberto: a borda dos chips tingidos

Ao buscar a borda exata do controle destrutivo apareceu uma convenção do
board mais ampla que esta feature. O board borda todo chip tingido com um
**meio-tom**, nunca a cor cheia do papel:

| Chip do artboard | fundo | texto | borda |
|---|---|---|---|
| perigo | `#2a1616` | `#ef7070` | `#5c2525` |
| sucesso | `#12271f` | `#3ad195` | `#12694a` · `#2a5c44` · `#1d3a2d` |

O console borda no brilho cheio do papel (`border-danger`), nos cinco
papéis — inclusive no controle destrutivo que esta feature acabou de
corrigir, cuja borda ficou em `#ef7070` e não no `#5c2525` do board.

**Não foi corrigido aqui, de propósito.** Exige cinco tokens novos e
contradiz o FR-017, que fixa a borda como a cor do próprio papel e que o
acceptance asserta. É mudança de spec mais mudança de tabela de tokens, não
uma edição de três classes — o tamanho disso é decisão do operador. Fica
como pendência nomeada para este slot ou para a 060, e não como um desvio
escondido.
