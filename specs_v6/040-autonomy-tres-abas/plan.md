# Implementation Plan: Autonomy & guardrails em três abas

**Branch**: `feat/v6-040-autonomy-tres-abas` | **Date**: 2026-08-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v6/040-autonomy-tres-abas/spec.md`

**Referência visual (DoD)**: `specs_v6/mockups/settings-v6.html#m2`

## Summary

A tela `/settings/autonomy-guardrails` é hoje uma página só com sete
preocupações empilhadas (postura, regras, congelamentos, tetos, override,
simulação, guardrails, mais um navegador de schema por baixo) e mede 2.3
viewports. Esta feature a divide em três abas endereçáveis pela URL — Posture,
Rules & windows, Guardrails —, cada uma dentro de 1.5 viewport em 1080p.

Nada de domínio muda: os mesmos campos, a mesma API de configuração
hierárquica, a mesma semântica de resolução e a mesma simulação. O que muda é
a distribuição, a hierarquia visual e o preenchimento da coluna de valor, que
hoje está vazia. O override sai do corpo permanente e vira painel lateral
aberto por botão no cabeçalho. O mapa de paridade campo → tela continua sendo
a rede de segurança: a reorganização é exatamente o movimento em que um campo
se perde, e o contrato existente falha por nome quando isso acontece.

## Technical Context

**Language/Version**: TypeScript (console, React Server Components); Python 3.12
apenas para a constante de orçamento e os contratos que a leem

**Primary Dependencies**: a tela existente `console/src/surfaces/settings/autonomy.tsx`
e os componentes que ela já monta (editor de regras/congelamentos/tetos, editor
de override, editor de configuração prefixado); o padrão de aba por parâmetro
de URL já usado em outras telas; o componente de tabela de configuração com
coluna de valor preenchida entregue pela 020; o mapa de paridade e o seu
contrato

**Storage**: N/A — os valores continuam no serviço de configuração existente

**Testing**: Playwright behaviour (acceptance da feature + suíte transversal +
orçamento de rolagem), vitest unit (resolvedor de valores efetivos por aba,
resolução do parâmetro de aba, destino do deep link), pytest contract (mapa de
paridade), captura visual deliberada

**Target Platform**: Console web

**Project Type**: Web — uma rota reorganizada, sem superfície nova de servidor

**Performance Goals**: nenhum novo; a tela continua sendo renderizada no
servidor e as abas são endereços, não estado de cliente

**Constraints**: 1.5 viewport por aba em 1920×1080; coluna de valor nunca
vazia; paridade de schema verde; nenhuma exceção na suíte transversal para esta
rota; comportamento de segurança vigente preservado (propose-only na ausência
de regra, override com nome/razão/expiração no audit, simulação vista antes de
salvar)

**Scale/Scope**: 1 rota, 3 abas, os campos de política que o mapa de paridade
atribui a esta tela, 1 painel lateral

## Constitution Check

*GATE: passa antes do desenho e é reconferido ao fim.*

- **Art. I (Evidência sobre asserção)** — Cada valor mostrado na coluna de
  valor é o valor efetivo que o serviço de configuração resolve, com a origem
  ao lado. A tela não afirma nada que não tenha lido. O que ela não conseguir
  resolver diz que não conseguiu, em vez de renderizar célula vazia — que é
  precisamente o defeito de hoje. **Satisfeito.**
- **Art. II (Autonomia limitada)** — O orçamento de 1.5 viewport por aba nasce
  como constante nomeada no módulo que já é dono das constantes de superfície,
  ao lado das que definem o viewport de medição e o orçamento de 2 viewports.
  Nenhum limite novo em literal de tela nem de teste. Os limites de autonomia
  que a tela edita continuam declarados em configuração. **Satisfeito.**
- **Art. III (Read-only por default)** — O default propose-only na ausência de
  regra deixa de ser subentendido e passa a ser afirmado em texto na aba
  Posture. Override continua exigindo nome, nível, razão e expiração, e continua
  caindo no audit ao ser concedido e ao ser revogado. Mover o formulário para um
  painel não afrouxa nenhuma dessas exigências. **Satisfeito.**
- **Art. IV (Segredos nunca chegam ao agente)** — Nenhum segredo transita por
  esta tela; ela edita política, não credencial. **Não aplicável, sem
  violação.**
- **Art. V (Um runtime canônico)** — Feature de console; não introduz nem
  seleciona runtime. **Não aplicável.**
- **Art. VI (Neutralidade de provider)** — Nenhum vendor é tocado.
  **Não aplicável.**
- **Art. VII (Aprendizado é medido)** — Nenhum mecanismo de aprendizado é
  introduzido ou alterado. **Não aplicável.**
- **Art. VIII (Arquitetura em camadas)** — Todo o código fica na superfície do
  console e na sua camada de shell; a constante de orçamento fica no pacote de
  configuração, que é folha. Nenhuma importação nova cruza camada.
  `check-imports` continua verde. **Satisfeito.**
- **Art. IX (Capacidades declaradas)** — Nenhuma capacidade nova, nenhuma
  integração tocada. **Não aplicável.**
- **Art. X (O operador é dono dos seus dados)** — Nenhuma telemetria, nenhuma
  chamada externa. **Satisfeito por ausência.**
- **Art. XI (Datastore único)** — Nenhum acesso direto a storage; a tela fala
  com o serviço de configuração pelas rotas que já usa. **Satisfeito.**
- **Art. XII (Test-first, lastreado em traço)** — O acceptance da feature nasce
  antes da tela e é confirmado vermelho; cada aba, o orçamento, a coluna de
  valor, o painel de override e a paridade têm teste próprio antes da
  implementação correspondente. A regra de que um teste prova o que mede vale
  aqui de forma literal: a medição de altura lê o documento renderizado, não o
  mockup. **Satisfeito.**
- **Art. XIII (Idioma e atribuição)** — Todo texto de produto em inglês, com o
  par pt-BR no mesmo commit. Nenhum arquivo committed desta feature aponta para
  documento de planejamento, mockup ou spec: o que precisa ser sabido é
  reafirmado no próprio arquivo. **Satisfeito.**

Sem violações a registrar. A seção de Complexity Tracking fica vazia por isso.

## Project Structure

### Documentation (this feature)

```text
specs_v6/040-autonomy-tres-abas/
├── spec.md
├── plan.md              # este arquivo
├── tasks.md
├── controle.md          # escrito ao fim da execução, não agora
└── checklists/requirements.md
```

### Source Code (repository root)

```text
config/constants/surfaces.py                          # orçamento por aba, constante nomeada
console/src/surfaces/settings/autonomy.tsx            # reorganizada em três abas
console/src/surfaces/settings/autonomy-tabs.ts        # novo: as três abas e a resolução do parâmetro
console/src/surfaces/settings/guardrail-values.ts     # novo: valor efetivo + origem por guardrail
console/src/surfaces/autonomy-editor.tsx              # simulação unificada num CTA primário
console/src/surfaces/override-editor.tsx              # passa a ser montado em painel lateral
console/src/shell/configuration-redirect.ts           # deep link de seção passa a nomear a aba
console/src/shell/config-ownership.ts                 # mapa de paridade, mantido verde
console/src/i18n/en.ts                                # escrita única na onda
console/src/i18n/pt-BR.ts                             # escrita única na onda
console/visual/screens.json                           # escrita única na onda; entrada desta rota sai de pendente

console/tests/e2e/040-autonomy-tres-abas.acceptance.spec.ts   # novo, primeiro e vermelho
console/tests/e2e/scroll-budget.spec.ts                       # ganha a medição por aba
console/tests/unit/surfaces/settings/autonomy.test.tsx        # existente: ganha abas, valores, permissões
console/tests/unit/shell/configuration-redirect.test.ts       # destino com aba
tests/contract/console/test_console_config_ownership.py       # paridade, mantida verde
```

**Structure Decision**: uma rota existente reorganizada, sem pacote novo. Os
dois módulos novos do console (resolução de aba e valores de guardrail) existem
para que a decisão "qual aba possui este campo" e a decisão "qual é o valor
efetivo deste guardrail" sejam testáveis por unidade, sem subir a tela inteira
— e para que a aba dona de cada campo seja um dado, não uma consequência de
onde o JSX calhou de ficar.

## Decisões de design

- **Aba é endereço, não estado de cliente.** As três abas são links com o
  parâmetro de aba na URL, exatamente como as outras telas do produto o fazem.
  Isso dá histórico, link compartilhável e renderização no servidor de graça, e
  é o que torna o acceptance capaz de medir cada aba isoladamente.
- **A aba dona de um campo é declarada, não inferida.** O módulo de abas mapeia
  cada campo de política à aba que o apresenta. É esse mapa que o deep link de
  seção consulta para escolher a aba, e é ele que o teste percorre para provar
  que nenhum campo ficou sem aba. Sem ele, "o campo está em alguma aba" seria
  uma afirmação sobre JSX.
- **A coluna de valor é preenchida por um resolvedor, não por formatação
  ad-hoc.** Um módulo pequeno traduz o par (campo, valor resolvido) na frase
  que a célula mostra — "On · level strict", "Enforcing — matches are blocked",
  "2 hours". Ele é unitário, e é o que impede a célula vazia de voltar por uma
  ramificação esquecida.
- **A leitura resumida em Posture e a tabela editável em Guardrails compartilham
  o resolvedor.** Duas aparições, uma fonte de verdade para o texto do valor:
  é a única forma de a coluna nunca ficar vazia nas duas.
- **Override é montado num painel, não reescrito.** O componente de override
  atual já pede nome, nível, razão e duração e já registra no audit. Ele muda
  de lugar e ganha o estado "nenhum override ativo" em texto; não muda de
  contrato.
- **A simulação vira um fluxo.** Os três controles de hoje passam a ser um CTA
  primário com as variações subordinadas a ele, e a seção ganha título e uma
  linha explicando o que ela responde. A trava que exige ter visto o efeito
  antes de salvar é preservada — ela é a razão de a simulação existir.
- **O orçamento por aba é medido, não desenhado.** O acceptance declara o
  viewport de 1920×1080 no próprio arquivo (a suíte global roda em 1440×900) e
  lê a altura do documento renderizado por aba, comparando com a constante
  nomeada.
- **A entrada de captura visual desta rota está pendente exatamente por altura
  e campos descobertos.** Esta feature resolve as duas coisas, então a captura
  deliberada de baseline faz parte do fim dela, não de uma feature futura.

## Complexity Tracking

Sem violações de constituição a justificar.
