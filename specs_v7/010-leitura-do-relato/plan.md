# Implementation Plan: Leitura do relato — o console lê o que a investigação registrou

**Branch**: `feat/v7-010-leitura-do-relato` | **Date**: 2026-08-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v7/010-leitura-do-relato/spec.md`

**Referência visual (DoD)**: nenhuma. A onda substituiu o mockup normativo pela
seção "Alegações normativas" da spec, codificada em
`console/tests/e2e/010-leitura-do-relato.acceptance.spec.ts` e confirmada vermelha
antes da primeira mudança de tela. Viewport normativo de medição: **1920×1080**.

## Summary

Duas telas de console — a lista de investigações e o detalhe de uma — passam a ler
o registro em vez de improvisar sobre ele. Cinco mudanças, e cada uma tem um dono
único no código:

1. **Um só lugar decide o nome de um run** (`console/src/surfaces/run-subject.ts`,
   novo), consumido pelas três superfícies que hoje repetem o mesmo cálculo
   errado. Headline quando existe, tradução de falha quando o texto é exceção, e
   `<trigger> · <id curto>` quando não há nem um nem outro.
2. **Um renderizador de markdown** (`console/src/surfaces/report.tsx`, novo) que
   desenha o report como leitura. Dependência nova, escolhida pela propriedade de
   nunca produzir uma string de HTML — a justificativa está abaixo, e ela é a
   decisão mais cara desta feature.
3. **O vocabulário de status do console passa a nomear os status que o produto
   emite** (`console/src/design/status.ts`). É a correção de uma linha e meia que
   apaga três sintomas de uma vez: badge desconhecido, "Paused in the background"
   em run terminado, e painel de controle oferecendo parar o que já parou.
4. **Transcript, custo e vínculos deixam de ser costurados na tela**
   (`run-detail.tsx`): a injeção do relato no corpo do replay sai, e o painel de
   vínculos passa a ler o que o registro carrega.
5. **A allowlist transversal encolhe** (`console/tests/e2e/transversal-rules.spec.ts`):
   as duas rotas de runs saem da tabela de exceções e passam por mérito.

Nada aqui grava. Nada aqui toca backend. A feature é console puro, o que é
exatamente por que ela é o par paralelo de uma feature de composition roots no
mesmo slot.

## Technical Context

**Language/Version**: TypeScript 5.9, React 19.2, Next 16.3 (App Router,
componentes de servidor). Node 24.19 e pnpm 11.20, ambos pinados.

**Primary Dependencies**: as três existentes (`next`, `react`, `react-dom`) mais
**uma nova de runtime**: um renderizador de markdown para React. Ver "A escolha do
renderizador" abaixo.

**Storage**: N/A. Leitura pura sobre a API REST.

**Testing**: Vitest em `console/tests/unit/` (estendendo
`tests/unit/surfaces/run-detail.test.tsx` e `tests/unit/surfaces/runs.test.tsx`,
e novos `run-subject.test.ts` e `report.test.tsx`); Playwright em
`console/tests/e2e/` (acceptance da feature + transversal); suíte visual em
`console/tests/visual/` com registro em `console/visual/screens.json`; contract
tests Python de superfície de console em `tests/contract/console/`.

**Target Platform**: navegador contra o console servido pelo build de produção;
validação final contra o staging k3s.

**Project Type**: rework de duas telas de um aplicativo web, com uma dependência
nova e uma correção de vocabulário compartilhado.

**Performance Goals**: o orçamento de rolagem e o de primeira pintura que o
console já declara continuam valendo. O renderizador roda no servidor, então o
bundle de cliente não deve crescer — isso é uma alegação a medir, não a supor.

**Constraints**: nenhuma requisição a host fora do deployment (regra do console,
com teste próprio); nenhum literal de design; toda string de UI vem do catálogo;
`dangerouslySetInnerHTML` permanece exclusivo de `src/app/layout.tsx`.

**Scale/Scope**: duas telas, uma rota de metadata, um módulo novo de nome, um
módulo novo de renderização, um arquivo de vocabulário de status, cinco arquivos
de fixture, um registro de telas, dois arquivos de teste estendidos e três novos.

## Constitution Check

*GATE: precisa passar antes da execução. Reconferir ao final.*

Constituição na versão que a feature de governança desta onda deixa em vigor
(**2.2.0**, com a cláusula "composed or it is not shipped"). Artigo a artigo:

| Artigo | Como este plano satisfaz |
|---|---|
| I — Evidência sobre asserção | É o eixo. A tela para de afirmar o que não leu: "No cost recorded" passa a exigir zero turnos, "Nothing linked yet" passa a exigir leitura bem-sucedida sem vínculo, e a contagem do transcript passa a ser o número de entradas desenhadas. O vermelho de cada alegação é capturado com a mensagem real antes da correção. |
| II — Autonomia limitada | Não toca laço, orçamento nem limite. O limite de caracteres do nome de um run é apresentação, e nasce como constante nomeada no console, não como número solto no site de uso. |
| III — Leitura por padrão | A feature é leitura pura. E ela **reduz** superfície de escrita: o painel que oferece parar e assumir uma investigação deixa de aparecer sobre runs que não podem receber nenhum dos dois. |
| IV — Segredo nunca chega ao agente | Não toca credencial. O relato renderizado é servido pelo componente de servidor com a credencial já resolvida; nada novo alcança o navegador. |
| V — Um runtime canônico | Não toca runtime. O transcript continua tendo **um** componente para as duas origens (replay e stream) — a mudança é parar de alimentar o replay com um campo que o deployment não devolve, o que aproxima os dois leitores em vez de afastá-los. |
| VI — Neutralidade de provedor | O painel de custo continua listando por modelo, sem privilegiar nenhum. Nenhum identificador de vendor entra em código de tela. |
| VII — Aprendizado é medido | Não toca mecanismo de aprendizado. |
| VIII — Arquitetura em camadas | O console é peer dos tiers Python e fala só HTTP. `make check-console-boundary` continua sendo o gate. A dependência nova é de renderização, e não alcança nenhum tier. |
| IX — Capacidades declaradas | Não toca catálogo de capacidades. |
| X — O operador é dono dos dados | **Morde aqui, e é a razão da escolha de renderizador.** Nenhum asset sai do deployment: imagem remota do relato não vira requisição, fonte externa não é carregada, e `tests/e2e/network.spec.ts` é o gate que prova. |
| XI — Datastore único | Não toca persistência. |
| XII — Test-first, rastreado | O acceptance nasce vermelho e o vermelho de cada alegação é registrado. Os dois arquivos de teste unitário existentes são **estendidos**; nenhum caso é duplicado num arquivo novo. |
| XIII — Idioma e atribuição | Todo arquivo committed em inglês, incluindo o texto novo do catálogo. As strings novas entram no catálogo `en` e, como esta feature toca o catálogo, também no `pt-BR`. Nenhum arquivo committed cita identificador de requisito, artigo, número de feature nem caminho de planejamento. |
| XIV — Composto ou não foi entregue | O mecanismo novo desta feature é de renderização, e o **composition root que o constrói é o próprio componente de servidor da rota**: `console/src/app/(shell)/runs/[runId]/page.tsx` → `RunDetailScreen` → o painel do relato. Não há fábrica, registro nem injeção envolvida, e por isso a prova de composição é o caminho de serving em si: o acceptance roda contra o **build de produção** (`make console-e2e`), e depois contra o staging real. Um teste unitário que renderiza o painel em isolamento não fecha nenhuma tarefa desta feature. |

### Complexity Tracking

| Violação | Por que é necessária | Alternativa mais simples recusada porque |
|---|---|---|
| Uma dependência de runtime nova no console, que hoje tem exatamente três | O relato é o produto e chega em markdown. Sem renderizador, ou o operador lê fonte, ou o console ganha um parser próprio | Um parser próprio é a alternativa e foi recusada abaixo, com razão: o texto é adversarial-adjacente e a falha de um parser caseiro é silenciosa |

## A escolha do renderizador

Esta é a decisão que o resto da feature herda, e ela é de segurança antes de ser
de conveniência: **o texto vem de um modelo que leu saídas de ferramentas**, e uma
saída de ferramenta pode conter qualquer coisa que um alerta, um log ou uma
resposta de API carregue.

### O que foi decidido

**`react-markdown`, com `remark-gfm` para tabela e lista de tarefas.** Duas
dependências de runtime, resolvidas na maior versão compatível com React 19 e
travadas em `pnpm-lock.yaml`.

**A propriedade que decidiu**: `react-markdown` não produz string de HTML em
momento nenhum. Ele constrói uma árvore de elementos React a partir da árvore
sintática, o que significa que o console nunca chama `dangerouslySetInnerHTML`
sobre texto de terceiro — e "nunca chama" é uma propriedade estrutural que um
teste de repositório verifica lendo a árvore, ao passo que "chama e sanitiza" é
uma lista de negação que precisa estar completa para valer alguma coisa.

**O que fica desligado, deliberadamente**:

- **`rehype-raw` não é instalado.** É o plugin que faz HTML cru do documento
  virar elemento. Sem ele, `<script>` num relato é o texto `<script>`. Uma tarefa
  do `tasks.md` afirma a ausência dele no manifesto, para que uma feature futura
  não o adicione "para melhorar a renderização".
- **Nenhum plugin de highlight de sintaxe.** Ele traria uma gramática por
  linguagem e um peso que a tela não precisa. Bloco de código é monoespaçado,
  com rolagem própria, e isso é tudo.

**O que é configurado explicitamente**:

- **Mapa de componentes fechado.** Só os elementos que o relato precisa —
  parágrafo, os seis cabeçalhos, ênfase, forte, código inline, bloco de código,
  as duas listas e o item, citação, tabela e suas partes, regra horizontal,
  link. Um nó fora do mapa é desenhado como seu próprio texto.
- **`img` mapeado para um componente que desenha o texto alternativo**, nunca um
  elemento de imagem. É o que faz "nenhum asset sai do deployment" ser verdade
  por construção e não por configuração de rede.
- **Transformação de URL própria**, aceitando `http`, `https` e `mailto` e
  recusando todo o resto. Link recusado vira texto, com o endereço visível — o
  operador precisa saber que havia um link ali.
- **Bloco de código e tabela dentro de um container com rolagem horizontal
  própria**, que é o que mantém o corpo da página sem rolagem lateral em
  1920×1080.
- **O painel inteiro com altura máxima e rolagem própria**, para que o orçamento
  de rolagem da página continue medindo a página.

**Onde ele roda**: no componente de servidor da tela. `react-markdown` não usa
estado nem efeito, então renderiza em RSC e o custo do parser não entra no bundle
de cliente. Isso é uma alegação e vira medição: se a versão resolvida exigir
`'use client'`, o plano cai no renderizador próprio descrito abaixo, e a razão
fica escrita.

### As alternativas, e por que não

**`marked` + `DOMPurify`.** É o caminho mais comum e é o que foi recusado com
mais convicção. `marked` produz uma string de HTML, o que obriga a
`dangerouslySetInnerHTML` numa superfície — perdendo a propriedade estrutural
inteira. E `DOMPurify` precisa de um DOM: no servidor, isso significa `jsdom` em
produção, uma dependência pesada rodando sobre texto hostil no processo que serve
o console. Trocar uma garantia estrutural por uma lista de negação **e** por uma
dependência a mais no caminho de serving é o pior negócio das três opções.

**`markdown-it` + sanitizador.** Mesmo problema de forma: string de HTML na
saída.

**Um renderizador próprio, sem dependência.** É a opção que o `AGENTS.md` do
console pediria por reflexo — o pacote recusa dependências por princípio, e a
auditoria de acessibilidade está lá dentro justamente por isso. Foi considerada e
recusada por uma razão específica: as coisas que o console escreve em vez de
importar são regras que **ele mesmo define** (o que é um token, o que é uma
violação de acessibilidade, como um cursor de stream avança). CommonMark não é
uma regra do console; é uma gramática externa com casos de borda que ninguém
adivinha, e o modo de falha de um parser incompleto sobre texto hostil é uma
renderização errada que passa em toda revisão. A dependência é a opção
conservadora aqui, e é assim que ela deve ser justificada no ADR-espírito do
pacote.

### O custo que a escolha impõe, e como ele é pago

- **Manifesto e lockfile.** `make console-lockfile` falha se um não descrever o
  outro. Tarefa explícita.
- **Orçamento de bundle.** `make console-budget` mede a folha compilada e o
  conjunto de ícones. A expectativa é que nada mude, porque nada disso é CSS nem
  ícone; a medição é tarefa, não suposição.
- **Rede.** `tests/e2e/network.spec.ts` já falha em qualquer host que o operador
  não roda. O mapa de `img` é o que garante que ele continue passando com um
  relato que referencia imagem.
- **Instalação sem rede.** O provisionamento do console baixa o toolchain com
  digest committed, mas `pnpm install` de um pacote novo precisa alcançar o
  registro uma vez. Se a máquina de execução estiver isolada, a tarefa para e
  reporta — não improvisa um vendoring.

## Project Structure

### Documentation (this feature)

```text
specs_v7/010-leitura-do-relato/
├── spec.md
├── plan.md                  # este arquivo
├── tasks.md
├── checklists/requirements.md
├── controle.md              # do implementer, não deste plano
└── evidence/                # screenshots full-page 1920×1080, criados na execução
```

### Source Code (repository root)

```text
console/package.json                                  # duas dependências novas
console/pnpm-lock.yaml                                # resolvido junto
console/src/surfaces/run-subject.ts                   # NOVO — o nome de um run, um lugar só
console/src/surfaces/report.tsx                       # NOVO — o relato como leitura
console/src/surfaces/screens/run-detail.tsx           # título, painel do relato, controles, vínculos
console/src/surfaces/screens/runs.tsx                 # coluna de sujeito
console/src/app/(shell)/runs/[runId]/page.tsx         # título da aba
console/src/surfaces/failures.ts                      # docstring: deixa de ser fonte de nome
console/src/surfaces/transcript.ts                    # nada de estrutura; só se a injeção exigir
console/src/design/status.ts                          # status que o produto emite; terminal
console/src/i18n/en.ts                                # strings novas (dona do arquivo no slot)
console/src/i18n/pt-BR.ts                             # as mesmas strings
console/visual/screens.json                           # registro das telas (dona no slot)
console/visual/baselines/                             # baselines recapturadas e aceitas
console/tests/unit/surfaces/run-subject.test.ts       # NOVO
console/tests/unit/surfaces/report.test.tsx           # NOVO
console/tests/unit/surfaces/run-detail.test.tsx       # ESTENDIDO
console/tests/unit/surfaces/runs.test.tsx             # ESTENDIDO
console/tests/unit/design/status.test.ts              # ESTENDIDO
console/tests/e2e/010-leitura-do-relato.acceptance.spec.ts   # NOVO
console/tests/e2e/transversal-rules.spec.ts           # allowlist encolhida
fixtures/scenarios/populated/runs.json                # runs novos
fixtures/scenarios/populated/run-detail.json          # detalhes dos runs novos
fixtures/scenarios/populated/run-replay.json          # replay com quatro chamadas
fixtures/scenarios/populated/incidents.json           # vínculo do run novo, se necessário
tests/contract/console/                               # contrato de superfície, se a forma mudar
```

**Structure Decision**: nenhuma estrutura nova. Dois módulos entram em
`src/surfaces/`, que é onde módulos de superfície moram, e nada sai de lá. O
renderizador é um módulo de superfície e não um componente do design system,
porque ele desenha *conteúdo de terceiro* e não um primitivo — pôr markdown em
`src/components/` faria a galeria ter que declarar uma variante para cada nó da
gramática.

## Decisões de design

- **O nome de um run é uma função pura, num arquivo só.** Três superfícies
  calculavam a mesma coisa em três lugares e por isso erravam juntas. A função
  recebe o registro do run e o locale e devolve o texto e o texto completo para
  tooltip. Um teste de superfície afirma que as três superfícies a chamam.

- **O console não confia que o headline seja texto simples.** Ele veio de um
  modelo a quem se pediu uma sentença, e um modelo a quem se pede uma sentença
  às vezes devolve uma sentença em negrito. O achatamento — primeira linha,
  sintaxe removida, espaços colapsados, recorte no limite — é do console, e é o
  que faz a alegação "nenhum caractere de sintaxe no título" valer
  independentemente do que o backend gravou.

- **O fallback é composição, não ausência.** `<rótulo do trigger> · <id curto>`
  em vez de "Not recorded". A razão é a mesma pela qual a lista já demoveu o id a
  metadado: "Alert · e19e882a" identifica; "Not recorded" nega. E o par é sempre
  computável, o que significa que nenhuma célula fica vazia por dado ausente.

- **O painel do relato não repete o headline.** O cabeçalho da página já o diz. A
  tela hoje faz três repetições da mesma string e o comentário no próprio código
  reclama disso. O painel mostra o report; quando não há report, ele mostra o
  headline, porque um painel vazio ao lado de um título cheio é pior que uma
  repetição.

- **A disclosure do texto cru existe, fechada.** Ela é a honestidade do
  renderizador: o mapa de componentes é fechado, então algo do documento pode não
  ser desenhado, e o operador precisa de um caminho para o original — inclusive
  para colar num ticket. Só aparece quando há report.

- **O vocabulário de status é corrigido no console, e é uma correção de fonte.**
  A lista de status de run do console foi escrita contra uma palavra que o
  produto não emite. A correção acrescenta `completed` e `partial` à lista, à
  tabela de apresentação e ao conjunto terminal; `succeeded` **fica**, porque as
  fixtures e as baselines a usam e removê-la é trabalho de outra feature. Um
  teste afirma que todo valor do enum do domínio está declarado — a fonte da
  verdade é o enum, e o teste é o que impede a lista de voltar a divergir.

- **Status desconhecido não é run vivo.** Hoje a decisão é `!isSettled(status)`,
  que trata todo desconhecido como vivo e por isso oferece "Stop" sobre ele. A
  decisão passa a ser afirmativa: um run é vivo quando o status está no conjunto
  vivo declarado. Desconhecido não está em conjunto nenhum, e a tela não oferece
  controle sobre o que não entende.

- **A injeção do relato no corpo do replay sai.** Ela existia porque o replay não
  tinha relato e a tela queria fechar o transcript com uma conclusão. Agora o
  relato tem painel próprio, e a entrada injetada é uma terceira cópia com
  identidade fabricada. `eventsFromReplay` **mantém** a capacidade de emitir a
  entrada de relato, porque o stream vivo ainda a produz; o que sai é a tela
  alimentando-a.

- **Os vínculos leem o registro primeiro e a correlação depois.** O painel passa
  a listar os recursos que o registro do run carrega. A busca na lista de
  incidentes continua sendo como o incidente de origem é achado, até que o
  registro o carregue diretamente. E a distinção que faltava fica explícita: o
  painel só afirma "nada vinculado" depois de uma leitura bem-sucedida.

- **A linha-meta omite o slot vazio.** O subtítulo do detalhe já filtra vazios; a
  lista não. A regra passa a ser a mesma nos dois: um slot sem fato sai da linha,
  em vez de virar placeholder ao lado de outro placeholder.

- **A allowlist encolhe por remoção de linha, e a prova é a suíte passando.**
  Remover a entrada não prova nada sozinho — é a suíte rodando sobre as duas
  rotas, sem `fixme` e sem `skip`, que prova. A tarefa é uma só e o critério é
  esse.

- **As fixtures ganham casos, não reescrevem os antigos.** Cinco casos entram: um
  run terminado com o status que o produto emite, um run sem headline com
  documento markdown, um run com headline e report, um run com quatro chamadas e
  turnos com custo, e um report com conteúdo hostil. Reescrever os runs
  existentes moveria baselines de telas que não são desta feature.

- **A baseline visual é recapturada porque a tela mudou de verdade.** Duas telas,
  no viewport normativo, e a razão de aceitação escrita no registro nomeia o que
  a imagem passa a proteger: um título que é uma sentença, um documento desenhado
  como documento, e a ausência do painel de controle num run terminado.
