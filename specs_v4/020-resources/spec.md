# 020 — Resources

A tela com mais dados reais e vários defeitos de leitura.

## Problemas

### 1. [quebrado] Clicar num recurso parece não fazer nada

Abrir um recurso (`?selected=...`) anexa o painel de detalhe **abaixo da
tabela de 100+ linhas**, fora da viewport, sem scroll automático. O operador
clica, nada muda na tela, e conclui que o clique quebrou. Correção: detalhe em
drawer/painel lateral, ou navegação para página própria, ou no mínimo
scroll-into-view. (Este é provavelmente um dos "tem coisas que não funcionam"
do feedback original.)

### 2. [quebrado] Painel de detalhe com chave de outro recurso

O detalhe do recurso `signoz` mostra em "Where its signals come from":
`up proxmox · name lxc/HAL9000/unknown/111` — HAL9000 é o *cluster*, 111 é um
vmid, e o segmento `unknown` sugere um campo não resolvido. Ou o painel está
mostrando o binding errado, ou a chave está malformada. Investigar e corrigir
o mapeamento; nunca renderizar `unknown` como parte de um identificador.

### 3. [bloqueia entendimento] Coluna morta: Utilisation

100% das linhas dizem "Not recorded". Uma coluna que nunca tem valor ensina o
operador a ignorar colunas. Enquanto a utilização não é coletada, a coluna
sai; quando existir para alguns, mostrar para os que têm.

### 4. [bloqueia entendimento] Vocabulários de saúde que não fecham

O header diz "103 watched · 79 healthy · 16 degraded"; as badges da tabela
dizem HEALTHY / UNHEALTHY / UNKNOWN; o dashboard diz "Degraded and unhealthy
24". Três vocabulários (healthy/degraded vs healthy/unhealthy/unknown) para o
mesmo eixo, com aritmética que só fecha depois de adivinhar que 24 = 16 + 8
unknown. Um único conjunto de estados, com os mesmos nomes no header, na
badge, no dashboard e no filtro.

### 5. [bloqueia entendimento] "(not in the inventory)" concatenado ao nome

Meia tabela tem o sufixo " (not in the inventory)" dentro da célula de nome —
poluição e, para quem não leu o conceito de inventário, ruído sem significado.
Virar badge própria com tooltip explicando o que é o inventário declarado e o
que fazer (adicionar ao inventário ou ignorar).

### 6. [bloqueia entendimento] "Unplaced" / "Ungraded"

Jargões de zona e criticidade ausentes, sem explicação nem ação. Tooltip +
link para onde se declara zona/criticidade.

### 7. [polimento] Sem busca por nome nem paginação

103 recursos numa tabela com scroll interno, filtros só por Zone/Criticality.
Falta o filtro mais óbvio: nome. (E a busca global também não encontra
recursos — spec 001.)

### 8. [polimento] "Worst first" órfão

Rótulo solto no canto sem alternativa visível de ordenação; e os headers de
coluna vazam "SORT, SMALLEST FIRST" (spec 012 item 4).

## Critérios de aceite

- Clicar num recurso mostra o detalhe imediatamente visível.
- O detalhe de um recurso só mostra chaves desse recurso, sem `unknown`.
- Nenhuma coluna 100% vazia; um único vocabulário de saúde em todo o produto.
- Existe filtro por nome.
