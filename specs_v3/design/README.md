# specs_v3/design — a linguagem, a marca e as telas

Quatro documentos e um conjunto de arquivos de marca. Foram escritos depois de
percorrer visualmente uma implementação madura do mesmo problema, e depois de ler
o sistema de design que o console já tem.

| Documento | Sobre |
|---|---|
| [D1](D1-linguagem-visual.md) | Cor, espaço, tipo, densidade, movimento — e o que **não** mexer |
| [D2](D2-arquitetura-da-informacao.md) | Navegação, hierarquia, estados vazios, ações destrutivas |
| [D3](D3-telas.md) | As cinco telas que decidem o produto |
| [D4](D4-marca.md) | A marca, seus dois cortes, e o que foi recusado |
| [brand/](brand/) | `mark.svg`, `mark-small.svg`, `lockup.svg` |

## A premissa

**O console não precisa de um redesenho.** Ele já tem cor por papel, escala de
espaçamento sem base, degraus de tipo completos, duas elevações, densidade
tokenizada, contraste verificado por teste, e um teste que compara nomes de token
e utilitário nas duas direções. Isso é mais rigor do que a maioria dos produtos
tem.

O que ele precisa é que essa linguagem seja aplicada a **telas que decidem**, e
não só a telas que mostram. Hoje as quatorze são de leitura, sem um único
formulário — o que é honesto (o código diz: *"a form that posted nowhere would be
worse than a sentence saying where it will live"*) e é também a razão de um
operador entrar e não encontrar nada para fazer.

## As cinco decisões que mudam mais

1. **O painel aparece sempre, mesmo zerado.** Números honestos no primeiro dia
   valem mais que um formulário bloqueando a porta. Corrigiu a spec 052.
2. **Toda afirmação carrega origem, visível sem clique.** Configuração mostra de
   qual nível herdou; investigação mostra de qual consulta veio; entrega mostra
   por qual rota entrou. É a mesma disciplina em três lugares, e é o que separa
   evidência de alegação.
3. **Nada que decide comportamento salva sem mostrar o efeito.** Preview,
   dry-run, explain, simulação de rota — os quatro mecanismos já existem no
   backend; falta chamá-los antes do botão de salvar.
4. **Contadores onde há decisão humana esperando.** Aprovações e mudanças
   propostas. Fila escondida é fila que cresce.
5. **`success` deixa de ser a mesma cor do acento.** Num produto que é quase todo
   estado, botão primário e recurso saudável não podem ter a mesma cor.

## O que foi conscientemente não copiado

Da implementação que serviu de referência:

- **Modelo fixado por agente.** Aqui existem oito papéis de modelo, cada um com
  provider próprio. Mostrar `fornecedor-modelo-data` ao lado de cada etapa
  assumiria o que o deployment escolheu, e neutralidade de provider é artigo da
  constituição deste projeto.
- **Estrela de quatro pontas como marca.** É a que melhor lê a 16px e virou a
  forma padrão de "produto com IA". Ver D4.
- **Grupos de navegação por assunto** (Operate / Estate / Learn / Govern). D2
  agrupa por frequência de uso, porque é assim que alguém procura durante um
  incidente.
