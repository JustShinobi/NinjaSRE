# D1 — Linguagem visual

## O que já existe, e é bom

O console **já tem um sistema de design real**, e a maior parte deste documento
é sobre não estragá-lo. O que está em `console/src/design/tokens.ts` e
`console/src/app/globals.css`:

- **Cor por papel, não por valor.** `surface`, `sunken`, `raised`, `text`,
  `muted`, `accent`, `on-accent`, `accent-bg`, `border`, `border-strong`, mais
  `success` / `warning` / `danger` / `info` / `neutral`, cada um com seu par
  `on-` e `-bg`. Nenhum componente conhece um hexadecimal.
- **Escala de espaçamento explícita, sem base.** Sete degraus declarados, e
  nenhum multiplicador — então `p-5` é utilitário real e `p-9` não gera CSS
  nenhum. Um valor fora da escala falha por não existir, o que chega antes e vale
  mais que uma regra de lint.
- **Quatro raios, duas elevações.** A nota no código está certa: profundidade
  além de dois níveis lê como decoração.
- **Tipografia como degraus completos** — cada passo carrega tamanho, entrelinha,
  peso e tracking juntos, então não há como usar meio degrau.
- **Densidade tokenizada** (`density-gap`, `density-row`, `density-control`).
- **Duas famílias, ambas do sistema. Nenhuma fonte é buscada.**
- **Contraste verificado por teste**, com os pares declarados e checados nos dois
  temas.
- **Um teste que compara os nomes nas duas direções**: utilitário apontando para
  token inexistente falha, e token que nenhum utilitário expõe falha também —
  porque um token que um componente não alcança é um token que alguém contorna
  com um literal.

Isso é mais disciplina do que a maioria dos produtos tem. **O problema do console
não é a linguagem visual; é que ela só foi aplicada a telas de leitura.**

## Paleta

| Papel | Claro | Escuro |
|---|---|---|
| `surface` | `#ffffff` | `#0d1117` |
| `sunken` | `#f5f7f8` | `#0a0e13` |
| `text` | `#11161c` | `#e9eef4` |
| `muted` | `#59626d` | `#9aa5b1` |
| `accent` | `#0f6f5c` | `#4fd6b0` |
| `accent-bg` | `#e7f3f0` | `#0e2b25` |
| `border` | `#d5dade` | `#242c36` |
| `border-strong` | `#78828d` | `#8b96a3` |

O acento é um verde-azulado profundo no claro e menta no escuro. Ele é a única
cor de identidade; tudo o mais é neutro ou semântico.

## O que acrescentar

### 1. Estado é cor semântica, e cor semântica nunca é o acento

O acento é interação: o que se pode clicar, o que está selecionado, a marca.
Estado de sistema é `success` / `warning` / `danger` / `info` / `neutral`.

Hoje isso se confunde porque o acento é verde e `success` também é verde. Numa
tela cheia de estado — que é o que este produto é — um botão primário e um
recurso saudável não podem ter a mesma cor. **`success` recebe um verde distinto
do acento**, com contraste verificado contra os três fundos.

### 2. Cor nunca é o único portador

Toda linha de estado carrega cor **e** forma: um marcador, um ícone, um rótulo.
Um operador daltônico e uma captura de tela em escala de cinza têm o mesmo
problema, e a solução é a mesma.

### 3. Um degrau de densidade a mais

Os tokens de densidade existem; falta usá-los. Duas densidades declaradas:

- **confortável** — leitura, configuração, primeiro uso;
- **compacta** — listas longas: recursos, runs, auditoria, eventos de entrega.

Um estate de 57 recursos numa tabela confortável é rolagem sem fim. É preferência
do operador, guardada por deployment.

### 4. Movimento tem uma função só

Transições existem para explicar mudança de estado, nunca para enfeitar. Duas
durações — rápida para retorno de controle, média para entrada e saída de painel
— e nada além disso. Tudo respeita `prefers-reduced-motion`, e "respeita"
significa não animar, não animar mais devagar.

Existe uma exceção justificada: **a investigação em andamento**. Ali o movimento
é informação — mostra que algo está acontecendo agora, e é a diferença entre uma
tela viva e uma travada.

### 5. Monoespaçado carrega significado

Identificador, endereço, VMID, nome de campo, trecho de log e chave de
configuração vão em mono. É o que separa *o que a máquina disse* de *o que nós
dissemos sobre isso*, e num produto de investigação essa fronteira é o produto.

## Regras que não se quebram

1. **Nenhum literal de cor num componente.** O teste já cobre; ele fica.
2. **Nenhum valor fora da escala de espaçamento.** Já é impossível; continua.
3. **Contraste verificado nos dois temas** para todo par novo, inclusive os da
   marca.
4. **O tema é do operador**, e o padrão segue o sistema. Uma tela de incidente às
   03:00 é lida no escuro, e isso não é preferência estética.
5. **Nada busca recurso externo** — nem fonte, nem ícone, nem imagem. É requisito
   de deployment, não gosto.
