# Implementation Plan: Regras e governança — as regras dizem a verdade antes de qualquer feature ser escrita contra elas

**Branch**: `feat/v7-000-regras-e-governanca` | **Date**: 2026-08-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v7/000-regras-e-governanca/spec.md`

**Referência visual (DoD)**: nenhuma. Feature sem tela própria — ver o cabeçalho
da spec. O que ela entrega em navegador são asserções nomeadas na suíte
transversal, e não uma tela nova.

**Slot**: S0, solo. Precede o merge de todas as outras features da onda.

## Summary

Três entregas, na ordem em que a onda precisa delas.

**Governança em dia.** A emenda que a orientação local afirma existir desde a
onda anterior é escrita de fato: o artigo de capacidades ganha a cláusula de
paridade na forma que o registro de decisão vigente descreve, e os quatro artigos
que a orientação acusa de exemplos defasados são auditados exemplo por exemplo. O
registro de paridade total passa a constar como revertido, os quatro registros
sem linha entram nas duas tabelas, e a orientação local passa a descrever o
repositório de hoje. Um ponteiro quebrado é consertado no caminho: o registro de
paridade vigente diz onde se lê a amplitude corrente do catálogo, e essa seção
não existe no roadmap.

**A emenda que fecha o buraco.** Um registro de decisão novo e committed decide
que um mecanismo mergeado é alcançável a partir de uma composition root de
serving ou se declara dormente, que um símbolo construído só por testes não é
entrega, e que o fechamento de toda feature carrega evidência do caminho de
serving. A mesma regra vira artigo da constituição local — artigo novo, não
cláusula acrescentada a um existente, pelas razões da seção "A emenda" abaixo.

**O ferramental que as outras assumem.** A suíte transversal passa a varrer as
telas do grupo "Now" com cinco regras novas, cada uma com allowlist explícita das
telas que hoje a violam, cada uma provada vermelha contra um dataset que reproduz
a tela violadora. E a validação de navegador ganha um backing que não sobe
ambiente nenhum: aponta para o staging real, com credencial de operador vinda do
ambiente, rodando só os testes declarados seguros para ambiente compartilhado.

Nada aqui muda comportamento de produto. O que muda é o que as regras dizem e o
que os gates medem.

## Technical Context

**Language/Version**: Python 3.12 (`tools/`, `config/constants/`); TypeScript
(suíte Playwright do console); Markdown (constituição local, registros de decisão,
roadmap, orientação local)

**Primary Dependencies**: `.specify/memory/constitution.md` (local-only),
`docs/adr/`, `docs/roadmap.md`, `CLAUDE.md` (local-only),
`console/tests/e2e/transversal-rules.spec.ts`, `console/src/shell/routes.ts`
(lido, nunca editado por esta feature), `fixtures/manifest.json`,
`fixtures/scenarios/`, `tools/spec_validation.py`, `tools/console_e2e.py`,
`config/constants/console.py`

**Storage**: N/A. Nenhuma migração, nenhum dado de operador tocado.

**Testing**: Playwright (`console/tests/e2e/`, projeto `behaviour`) para as regras
transversais; vitest (`console/tests/unit/`) para a prova determinística dos
detectores; pytest (`tests/unit/tools/`) para o backing novo e a recusa por
credencial ausente. Sem `acceptance.spec.ts` próprio — não há tela nova.

**Target Platform**: repositório e ferramental; o alvo de execução da validação
nova é o staging em k3s

**Project Type**: governança + ferramental transversal

**Performance Goals**: N/A. O único custo novo de tempo de parede é a varredura
das rotas de "Now", que é da ordem das varreduras que a suíte já faz.

**Constraints**: a verificação completa do repositório precisa terminar verde
tendo partido de verde, e a comparação entre as duas rodadas é a evidência. A
constituição não entra em commit. Nenhum arquivo committed cita número de artigo,
identificador de requisito, número de feature nem caminho de planejamento.
Nenhuma tarefa toca diretório de outra feature.

**Scale/Scope**: dois aumentos de versão da constituição; um registro de decisão
novo; cinco linhas em duas tabelas de índice; um documento de orientação local;
cinco regras transversais com nove entradas de allowlist; um cenário de dados
novo; um backing de validação novo com quatro constantes.

## Constitution Check

*GATE: precisa passar antes da execução. Reconferir ao final.*

A checagem é feita **contra a constituição como ela fica ao final desta feature**
— 2.2.0, com a cláusula de paridade no artigo de capacidades e o artigo novo de
composição. É a única leitura honesta: esta feature escreve as duas emendas, e
checar contra o texto de partida seria checá-la contra um documento que ela mesma
declara incompleto.

| Artigo | Como este plano satisfaz |
|---|---|
| I — Evidência sobre asserção | Cada afirmação de defeito desta feature está cravada em arquivo e linha na spec, conferida na árvore antes de a spec existir. O vermelho de cada regra nova é capturado com a mensagem real antes da allowlist; a rodada de verificação anterior à primeira escrita é artefato, para que "continuou verde" seja comparação. |
| II — Autonomia limitada | Não toca laço, orçamento, cap de esquema nem cache. |
| III — Leitura por padrão | Não toca semântica de aprovação nem de escrita. O backing novo é de leitura por construção: só rodam testes que leem, e a marca que os declara enuncia isso onde é declarada. |
| IV — Segredo nunca chega ao agente | **Morde aqui.** A credencial de operador do staging é lida do ambiente, nunca gravada, nunca impressa, nunca passada como argumento de processo — argumento de processo é legível por qualquer processo do host. A ausência da credencial é uma recusa nomeada, não um fallback. Um critério de sucesso é a busca pela credencial na saída completa do run não a encontrar. |
| V — Um runtime canônico | Não toca runtime. O artigo é um dos quatro auditados: o exemplo de adaptador alternativo que ele dá foi conferido contra a árvore e corresponde a um módulo que existe. |
| VI — Neutralidade de provedor | Não toca abstração de provedor. |
| VII — Aprendizado é medido | Não toca mecanismo de aprendizado. |
| VIII — Arquitetura em camadas | As constantes novas entram no tier folha, que é onde nome de variável de ambiente vive e onde o guarda de constantes exige que viva. A suíte de navegador lê a camada de constantes por leitura de texto, como já faz para o viewport normativo — não é import, e a checagem de fronteira do console continua verde. |
| IX — Capacidades declaradas | **É um dos artigos emendados.** Ganha a cláusula de paridade que hoje não existe nele. Nenhuma capacidade é adicionada nem alterada. |
| X — O operador é dono dos dados | Nada sai do host. A execução contra staging fala com o deployment do próprio operador, e só lê. |
| XI — Datastore único | Não toca porta de persistência. O artigo é um dos quatro auditados: os cinco portos que ele nomeia foram conferidos e existem. |
| XII — Test-first, rastreado | **Cláusula 1 é a que morde**: cada regra transversal nova aterrissa com o vermelho confirmado contra um dataset violador, antes da allowlist que a silencia nas rotas conhecidas. **Cláusula 3**: esta feature não afeta investigação — não toca prompt, capacidade, pipeline nem provedor —, e o efeito nulo sobre a suíte de cenários sintéticos é reportado como resultado medido, não presumido. |
| XIII — Idioma e atribuição | Todo arquivo committed em inglês. O registro de decisão novo se sustenta sozinho: enuncia a regra em substância e não pede nenhum documento fora do clone. **Cláusula 4 é a razão de uma decisão deste plano**: as linhas de tabela que esta feature escreve nomeiam o que a decisão governa em substância, e não por número de artigo, porque um número de artigo aponta para um documento que não vem no clone. |
| XIV — Composto ou não foi entregue | **É o artigo que esta feature escreve, e ela é a primeira a ser medida por ele.** Ver "Composition roots" abaixo: esta feature não toca nenhuma composition root de serving, e diz por que isso não é evasão. |

### A emenda

**O que está errado hoje.** A orientação local afirma que a constituição está em
2.1.0, emendada pelo registro de decisão que reverteu a paridade total, e depois
que foi emendada de novo para 2.2.0. O arquivo está em 2.0.0 e o artigo de
capacidades **não tem cláusula de paridade nenhuma** — nem a dos sete artefatos,
nem a de amplitude. O registro de decisão vigente diz que emenda "a cláusula de
paridade" daquele artigo; a cláusula não existe. Quem roda um Constitution Check
hoje o roda contra um texto que uma das duas fontes declara errado, e contra um
artigo que não contém a regra que o corpus inteiro trata como normativa.

**O que muda, exatamente — primeira emenda.** O artigo de capacidades **ganha**
uma cláusula: paridade é por integração embarcada, inalterada em forma — os sete
artefatos, todos, para toda integração do catálogo —, e a amplitude é estagiada
por ambiente capaz de validar a integração ponta a ponta (credencial armazenada,
conexão verificada, ao menos uma leitura real exercitada). Sem total afirmado. É
o que o registro vigente já decidiu; o que falta é o texto normativo dizer.

Junto, os quatro artigos que a orientação acusa de exemplos defasados são
auditados exemplo por exemplo. Dois deles já foram conferidos na preparação desta
spec e estão corretos — os cinco portos nomeados existem, o adaptador de runtime
alternativo existe. "Conferido e correto" é resultado aceitável; "não medido" não
é, e é por isso que a auditoria é tarefa e não observação.

**Qual aumento de versão — primeira emenda.** MINOR. A regra de versionamento
pede MAJOR para remover ou reverter artigo, MINOR para acrescentar um ou expandir
materialmente uma cláusula, PATCH para redação. Uma cláusula nova num artigo
existente é expansão material. 2.0.0 → 2.1.0.

**O que muda, exatamente — segunda emenda.** A regra de composição entra como
**artigo novo**, não como cláusula acrescentada ao artigo de test-first. A
alternativa foi considerada e recusada por uma razão que é a própria substância
da regra: o artigo de test-first é sobre a ordem em que testes e implementação
aterrissam, e foi exatamente a leitura "os testes estão verdes, logo está
entregue" que deixou cinco mecanismos passarem sem composição. Enfiar a regra ali
a apresenta como um corolário da disciplina de teste, quando ela existe
precisamente porque a disciplina de teste não a implica. Artigo próprio, com
teste de uma linha próprio no índice: *quem constrói isso em produção, e onde?*

**Qual aumento de versão — segunda emenda.** MINOR. Um artigo novo é o caso
explícito de MINOR na regra de versionamento. 2.1.0 → 2.2.0.

**Como as emendas são feitas.** A regra de governança do próprio documento exige,
para cada uma, um registro de decisão declarando driver, alternativas e
consequências, mais aumento de versão.

1. A primeira emenda tem o seu registro escrito e aceito desde a onda anterior;
   ela é a metade que faltou. Nenhum registro novo é escrito para ela — o
   cabeçalho da constituição passa a nomeá-lo.
2. A segunda emenda recebe registro novo, com o próximo número livre da série.
3. As duas entradas de emenda ficam no cabeçalho, em ordem, cada uma com data e
   sumário. Duas emendas em uma feature são duas linhas de histórico, não uma.

**Onde a regra fica legível para quem clona.** A constituição é local-only. O
registro de decisão novo é committed, é onde a regra de composição vive para o
público, e por isso ele se sustenta sozinho: enuncia a regra inteira em
substância, sem número de artigo, sem identificador de requisito e sem caminho de
planejamento. Um leitor que só tem o clone lê a regra por inteiro ali.

### Composition roots

A regra que esta feature escreve exige que toda feature declare qual composition
root constrói o que ela entrega. Esta é a primeira a responder, e a resposta é
particular:

**Esta feature não toca nenhuma composition root de serving.** Nenhuma. Ela não
entrega mecanismo de produto: entrega texto normativo, asserções de suíte e um
backing de validação. Os três mecanismos que ela entrega e onde cada um é
construído:

| Mecanismo | Quem o constrói | Como se prova |
|---|---|---|
| As cinco regras transversais | o projeto `behaviour` do Playwright do console, que já é o que o gate roda | a suíte roda no gate e as regras aparecem no relatório, nomeadas |
| Os detectores de cada regra | o teste determinístico do gate padrão, que os alimenta com o texto ofensor e com o texto limpo | falha se o detector deixar de acusar |
| O backing de staging | a linha de comando da validação de spec, que é a composition root de uma ferramenta de repositório | uma execução real contra o staging, com a evidência do run |

Declarar isso é o oposto de escapar da regra: um mecanismo cujo único caminho de
serving é uma linha de comando tem de dizer que é esse o caminho, e provar que
alguém a rodou. É o que o fechamento desta feature exige.

Uma consequência que vale registrar: como esta feature não constrói nada em
`gateway/` nem em `surfaces/`, ela não é o teste de fogo do artigo novo. As
features seguintes é que são — e por isso o artigo precisa estar escrito antes
delas, o que é a razão de esta rodar sozinha e primeiro.

### Complexity Tracking

Nenhuma violação a justificar. A única coisa que esta feature acrescenta à
superfície do repositório é um cenário de dados derivado, e ele existe para que o
vermelho dos bans seja reproduzível em qualquer máquina em vez de depender de um
ambiente compartilhado.

## Project Structure

### Documentation (this feature)

```text
specs_v7/000-regras-e-governanca/
├── spec.md
├── plan.md              # este arquivo
├── tasks.md
├── controle.md          # do implementer, não deste plano
├── evidence/            # capturas do run contra staging
└── checklists/requirements.md
```

### Source Code (repository root)

```text
.specify/memory/constitution.md                   # duas emendas; NUNCA commitada
CLAUDE.md                                         # estado do repositório; NUNCA commitado
docs/adr/0016-*.md                                # registro novo (committed)
docs/adr/0009-full-integration-parity.md          # só o status muda
docs/adr/README.md                                # linhas 0012–0016
docs/roadmap.md                                   # traceability + seção de escopo de integrações
console/tests/e2e/transversal-rules.spec.ts       # cinco regras novas + allowlist
console/tests/e2e/bans.ts                         # os detectores, isolados para poderem ser provados
console/tests/unit/e2e/bans.test.ts               # prova determinística dos detectores
fixtures/manifest.json                            # o cenário violador, declarado
fixtures/scenarios/<violador>/                    # só os endpoints que precisam mudar
config/constants/console.py                       # endereço, credencial, evidência, marca
tools/console_e2e.py                              # o backing que não sobe nada
tools/spec_validation.py                          # a opção nova e as recusas
tests/unit/tools/test_console_e2e.py              # backing novo: recusas e ausência de bring-up
tests/unit/tools/test_spec_validation.py          # a opção nova e os argumentos incompatíveis
```

**Structure Decision**: nenhuma estrutura nova. Um registro de decisão, um cenário
de dados derivado, um módulo de detectores ao lado da suíte que os usa, e quatro
constantes no tier que já é dono de nome de variável de ambiente.

**Arquivos de escrita única**: nenhum dos três arquivos com dono por slot
(`console/src/i18n/*.ts`, `console/src/shell/routes.ts`,
`console/visual/screens.json`) é editado por esta feature. `routes.ts` é **lido**
pela suíte transversal, que já o lê hoje, e continua sendo lido — a suíte varre o
que o manifesto declara, e é assim que uma rota nova do grupo "Now" entra na
varredura no dia em que aterrissa.

## Decisões de design

- **A ordem é gate-primeiro.** Cada regra transversal entra com a allowlist
  **vazia** e é rodada contra o dataset violador até acusar. Só depois de o
  vermelho estar capturado, com a mensagem real, as entradas de allowlist são
  escritas. Uma regra cuja allowlist nasceu junto com ela é uma regra que ninguém
  viu funcionar, e o modo de falha é silencioso: um seletor errado, um regex que
  não casa nada, e o gate fica verde por não olhar.

- **O dataset violador é committed, não improvisado.** Os `summary` do cenário
  cheio são sentenças limpas: contra a árvore de hoje, os cinco bans passam em
  todas as rotas. Um vermelho que só existe contra o staging é um vermelho que
  ninguém consegue reproduzir daqui a três meses, quando o staging já tiver sido
  consertado — e nesse dia ninguém saberá se a regra ainda tem dentes. O cenário
  deriva do cheio e carrega só os endpoints que precisam mudar: o documento
  markdown onde deveria haver uma sentença, o identificador composto onde deveria
  haver um nome, a linha-meta em fallback duplo, o run terminado com estado de
  run vivo, e a leitura falhada que sustenta uma afirmação negativa.

- **O detector é separado da varredura.** Cada regra tem um detector puro — texto
  entra, violação sai — que a suíte de navegador chama e que um teste
  determinístico do gate padrão alimenta com os textos exatos que o diagnóstico
  registrou no staging, mais os textos limpos equivalentes. É o que mantém a
  regra provada todo dia, e não só no dia em que alguém apontou a suíte para o
  cenário violador. A varredura fica com o que só o navegador sabe: quais rotas
  existem, e o que a página de fato desenhou.

- **A allowlist é uma dívida declarada, com número.** Nove entradas na partida,
  derivadas do diagnóstico. Cada uma nomeia rota, regra, a razão em substância e o
  que a remove — nunca um número de feature, porque o arquivo é committed e o
  número aponta para um diretório que ninguém clona. O fechamento reporta o
  número; um slot que o aumentar tem de explicar por quê.

- **As telas de detalhe são alcançadas pela lista, nunca por identificador
  digitado.** Um identificador literal num arquivo de teste é uma dependência de
  dataset disfarçada: ele quebra quando o cenário muda e mente quando o mesmo
  identificador existe com outro conteúdo. A varredura abre a lista, segue a
  primeira linha, e mede a tela onde chegou.

- **A declaração de "seguro para staging" é por teste e é fail-closed.** Por
  teste, porque a suíte transversal mede coisas que dependem dos dados do
  deployment e nem todas fazem sentido contra um ambiente vivo. Fail-closed,
  porque a lista do que roda contra staging é a interseção do que foi pedido com
  o que foi marcado — um teste não marcado não roda lá nem quando é nomeado. O
  significado da marca é enunciado onde ela é declarada: leitura e fluxo de
  proposta, nunca escrita nem destruição.

- **O backing de staging não sobe nada, e recusa alto.** Não inicia plano de
  dados, não serve console local, não constrói. Um argumento que só faz sentido
  para um backing que sobe ambiente — o cenário de dados, a reconstrução — é
  recusado em vez de ignorado, porque ignorar em silêncio é como se aprende que
  um flag funciona quando ele não faz nada. A credencial ausente é uma recusa
  nomeada antes de o navegador ser provisionado, não um erro de sessão quinze
  segundos depois.

- **A credencial nunca vira argumento.** Argumento de processo é legível por
  qualquer processo do host, e um endereço com credencial embutida acaba em log
  de proxy. Ela vem do ambiente e é repassada pela variável que a suíte de
  navegador já lê para o backing que precisa de credencial real — o caminho já
  existe, e reusá-lo é uma superfície a menos.

- **A marca tem um dono só.** A grafia da marca é declarada uma vez, na camada de
  constantes, e a suíte a lê do mesmo lugar de onde já lê o viewport normativo.
  Duas grafias de uma marca de seleção não falham: elas selecionam zero testes e
  reportam sucesso.

- **O status do registro revertido muda; o corpo não.** A regra do próprio índice
  diz que um registro é imutável depois de aceito e que reverter é escrever
  outro. Declarar o status é registrar o que outro registro já decidiu sobre
  este, e não reabrir a decisão. O corpo continua explicando por que foi tomada
  então, que é a única razão de um registro revertido continuar no repositório.

- **As linhas novas nomeiam a substância, não o número.** As cinco linhas que
  esta feature escreve nas duas tabelas dizem o que a decisão governa em
  palavras. As onze preexistentes ficam como estão: são espelho de registros
  aceitos e imutáveis, e normalizá-las é passe editorial próprio. A divergência é
  declarada aqui de propósito, para que a próxima pessoa não a leia como
  descuido.

- **O ponteiro quebrado é consertado onde ele aponta.** O registro de paridade
  vigente diz, em texto committed, que a amplitude corrente se lê numa seção do
  roadmap. A seção não existe. Escrevê-la é mais barato e mais honesto do que
  emendar um registro imutável, e o histórico de amplitude que o roadmap já
  guarda fica intacto — uma checagem de arquitetura já isenta o roadmap de citar
  um total antigo, com a razão escrita nela mesma.

- **A verificação anterior é artefato.** O log é capturado antes da primeira
  escrita, fora do repositório. Sem ele, uma falha preexistente é debitada desta
  feature e uma falha desta feature se esconde atrás de "já estava assim".
