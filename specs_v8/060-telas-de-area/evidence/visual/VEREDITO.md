# Veredito visual — Telas de área, slot S2

Duas rodadas. A primeira reprovou o slot com quatro desvios; esta é a segunda,
contra o staging já reimplantado com os reparos. As capturas "antes", em
`antes/`, são da implantação anterior e servem de par de comparação.

Cada captura teve o tema conferido duas vezes antes de valer: a escolha que o
próprio controle reporta e a cor de fundo medida. O controle é tri-estado
(claro → escuro → sistema), então um clique não é "o outro tema" — vindo do
escuro ele cai em sistema, que renderiza claro e parece sucesso.

| Tela × tema | Veredito |
|---|---|
| `/incidents` escuro | CONFORME |
| `/incidents` claro | CONFORME |
| `/resources` escuro | CONFORME |
| `/resources` claro | CONFORME |
| `/knowledge` escuro | CONFORME |
| `/knowledge` claro | CONFORME |
| `/agent` escuro | CONFORME |
| `/agent` claro | CONFORME |

## O que a primeira rodada reprovou, e o que fechou cada um

**Incidentes — o subtítulo era um identificador.** O board desenha a frase
humana primeiro e o id truncado no fim, como detalhe. A tela mostrava
`res-dde476d5…` sozinho. Os nomes existiam: cada id da amostra resolve na base
de estado — `runner-orchestrator`, `pve02`, `troubleshooting-lab`,
`alpine-postgresql`, `unbound`. Fechado usando uma leitura que a tela **já
fazia** para o cartão de cobertura de detector, sem requisição nova. Um assunto
que a base não conhece continua mostrando o id, em vez de inventar um nome.

**Recursos — a grade não terminava.** 59 cartões num nó só, página de 3230 px.
Fechado limitando como o board limita: duas linhas numa seção que tem algo não
saudável, uma onde não tem, e um "ver todos os N" por seção. O link é destino
de verdade — um filtro por nó com a mesma forma dos outros filtros da tela, sem
limite lá dentro, com volta —, não uma seta decorativa. A página caiu para
1795 px, e é isso que finalmente torna esta tela capturável: a dívida herdada
de baseline não era outra coisa senão esta.

**Conhecimento — o desfecho estava fora do vocabulário de status.** Nenhum
elemento da página carregava `data-role`. Fechado roteando o desfecho pelo
componente compartilhado e dando a ele o chip que o board desenha. Achado no
caminho, e maior que o desvio: as fixtures do mock serviam `acknowledged` e
`unresolved`, palavras que o backend real nunca emitiu.

**O agente — a aba tinha outro nome e a linha não tinha linha.** O nome era um
único valor de mensagem, não o slug da URL: renomear o slug teria movido um
contrato que ninguém pediu para mover. O trilho passou a ser desenhado, e numa
segunda passagem os seis estágios viraram estações — poços circulares com anel
de 2 px, nos mesmos valores que o board usa.

## Diferenças que não são desvio

- **As estações estão todas em "ainda não alcançado".** O board pinta as
  primeiras em accent e a corrente preenchida, porque desenha um run em
  andamento. O staging não tem nenhum — 682 completos, 11 interrompidos, zero
  rodando, medido. E nada no contrato nomeia em que estágio um run que está
  rodando se encontra, o que está declarado no controle com o precedente de
  outra feature desta onda. Os três tratamentos existem e são testados; falta
  um campo, não desenho.
- **Dado.** Contagens, nomes e tempos do staging não são os do artboard.
- **Idioma.** O board é pt-BR, a sessão capturada estava em inglês.
- **As cinco sub-abas não reformadas** (Documentos, Topologia, Ferramentas,
  Autonomia, Contexto do time) foram cortadas com razão declarada e são
  medidas só pelo vocabulário compartilhado, nunca contra os artboards
  próprios delas, que esta rodada deliberadamente não construiu.
