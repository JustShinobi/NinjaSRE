# Veredito visual — Telas de área, slot S2

Capturado no staging real depois do deploy de todos os componentes e do
aquecimento das rotas. Cada captura teve o tema conferido duas vezes: a escolha
declarada pelo controle e a cor de fundo medida. O controle é tri-estado
(claro → escuro → sistema), então um clique não é "o outro tema" — vindo do
escuro ele cai em sistema, que renderiza claro e parece sucesso. As capturas
"antes", em `antes/`, foram tomadas contra a implantação anterior e servem de
par de comparação.

| Tela × tema | Veredito |
|---|---|
| `/incidents` escuro | **DESVIO** — subtítulo continua sendo identificador, não frase |
| `/incidents` claro | idem |
| `/resources` escuro | **DESVIO** — a grade não é limitada; a tela tem 3230 px |
| `/resources` claro | idem |
| `/knowledge` escuro | **DESVIO** — desfecho sem chip e fora do vocabulário de status |
| `/knowledge` claro | idem |
| `/agent` escuro | **DESVIO** — primeira aba chamada "Topology" onde o board diz "Pipeline"; a linha de metrô não desenha o trilho |
| `/agent` claro | idem |

## O que conforma, e é muito

**Incidentes.** Os `<select>` viraram controles segmentados (Estado, Severidade,
Visão) como o artboard manda. A linha-resumo "30 assuntos · 50 disparos · 3
críticos em investigação" está no canto certo. Agrupa por assunto, chips de
severidade e de estado com forma além de cor, contagem de disparos, tempo
relativo, marcas por linha, e a faixa âmbar de cobertura de detector no rodapé
com sua ação. Os críticos vêm primeiro.

**Recursos.** Barra de saúde segmentada com a legenda de quatro estados, chips
de tipo com contagem, a faixa vermelha de síntese em lote — "8 contêineres não
saudáveis desde 20 h atrás, todos em pve01, mesma janela" com "investigar em
lote →" — seções por nó com contagem de não saudáveis, cartões em grade com os
não saudáveis primeiro dentro da seção, e a faixa âmbar de zona/criticidade no
fim. É o artboard.

**Conhecimento.** Aprendido é a aba de entrada. Filtro de componente agrupado
mais o segmentado de desfecho. Os cartões de episódio têm a forma do artboard:
frase como título — nunca um id —, resumo, chips de componente, "abrir
investigação →" e tempo relativo. O painel "O que o agente aprendeu com isso"
lê a fila de propostas, à direita, como desenhado.

**O agente.** Os seis estágios estão todos lá, cada um com ícone, o papel de
modelo anotado ("sem modelo", "modelo: intake", "determinístico"…), nome e a
microcópia de uma frase — o conteúdo do artboard, item por item. Os três cartões
de resumo também: Ferramentas com "63 de 80 habilitadas", barras por domínio e
os chips de nível de efeito; Autonomia com os cinco níveis e um controle Propor
em cada; Contexto do time com o orçamento de tokens.

## Os desvios, um a um

**1. Incidentes: o subtítulo ainda é um identificador.** O board desenha
`redis em lxc/122 · pve01 · recorrente desde ontem · res-7a73…` — a frase
humana primeiro, o id truncado no fim, como detalhe. A tela mostra
`res-dde476d5…` sozinho na maioria das linhas. O código encurta identificadores
opacos em vez de os imprimir inteiros, o que é melhor do que era, mas encurtar
um id não é substituí-lo por um nome. Onde o alerta traz rótulos, a linha fica
legível; onde só traz o id do recurso, não.

**2. Recursos: a grade não é limitada.** O artboard mostra alguns cartões por
nó e um "ver os 58 recursos de pve01 →". A tela imprime todos — 59 cartões só
em pve01 — e por isso tem 3230 px de altura. Isto é a mesma coisa que a dívida
herdada de baseline não capturável: a captura não cabe em janela nenhuma
justamente porque a grade não termina. Trocar a tabela pela grade não fechou
essa dívida; limitar a grade fecharia.

**3. Conhecimento: o desfecho do episódio não usa o vocabulário de status.**
Nenhum elemento da página carrega `data-role` — conferido no ambiente real, não
deduzido —, então o ponto de desfecho é desenhado por conta própria e não pelo
componente compartilhado. O artboard desenha um chip âmbar "inconclusivo" à
direita de cada episódio, além do ponto vazado. A tela não tem o chip, e o ponto
não carrega o papel.

Nota honesta: a forma `inconclusive` foi acrescentada ao mapa de status durante
o merge deste slot, exatamente para desenhar âmbar e vazado como o board manda.
Ela está correta e **não tem efeito aqui**, porque esta tela não consome esse
mapa. Aplicar não é o mesmo que verificar.

**4. O agente: a primeira aba tem outro nome, e a linha não tem trilho.** O
board nomeia as abas Pipeline / Ferramentas / Autonomia / Contexto do time; a
tela chama a primeira de "Topology". E a "linha de metrô" do artboard são seis
ícones circulados ligados por um trilho horizontal, com o estágio corrente
ampliado; a tela desenha seis colunas de texto com ícones pequenos e nenhum
trilho entre elas. O chip "N investigações em voo" não aparece, mas isso é dado
— o staging não tem nenhum run em execução, medido: 682 completos, 11
interrompidos, zero rodando.

## Diferenças que não são desvio

- **Dado.** Contagens, nomes e tempos do staging não são os do artboard.
- **Idioma.** O board é pt-BR, a sessão capturada estava em inglês.
- **O conteúdo antigo abaixo do herói em `/agent`** — estágios em detalhe,
  especialistas, modelos por papel, orçamento — foi mantido de propósito: a
  própria tarefa desta feature pede a listagem detalhada preservada e
  re-vestida abaixo da visão nova.
- **As cinco sub-abas não reformadas** (Documentos, Topologia, Ferramentas,
  Autonomia, Contexto do time) foram cortadas com razão declarada. São medidas
  só pelo vocabulário compartilhado, nunca contra os artboards próprios delas,
  que esta rodada deliberadamente não construiu.
