# Implementation Plan: Decisão composta — a metade do produto que age passa a existir

**Branch**: `feat/v7-040-decisao-composta` | **Date**: 2026-08-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v7/040-decisao-composta/spec.md`

**Referência visual (DoD)**: nenhuma. Backend puro, sem tela própria — ver o
cabeçalho da spec. Não é dona de arquivo de escrita única no seu slot e não os
edita.

## Summary

Nada nesta feature é escrito do zero. O inventário está medido: oitenta
capacidades registradas, das quais vinte e quatro escrevem — quinze
reversíveis, seis irreversíveis, três destrutivas — e vinte e quatro declaram
que precisam de aprovação, com razão e plano de reversão ao lado. Os dois
portões existem: `RemediationGate` (`platform/remediation/gating.py:187`) e
`AutonomyGate` (`platform/autonomy/decision.py:168`). O executor, o construtor
de pedido, o gerador de plano, o registro de resultados, as tabelas e as rotas
permissionadas também. **O que não existe é o fio**: uma varredura por
construção dos dois portões devolve só teste, contract test e plano de dados de
mentira.

Esta feature liga o fio, em três lugares nomeados abaixo, e não afrouxa nada.
Junto vêm as três coisas que caem do mesmo seam: a seleção de ferramentas passa
a filtrar por nível de efeito colateral e pelas integrações que o time
conectou; o balcão de perguntas passa a existir por run; e o caminho de
orquestração duplicado — o pipeline de seis estágios ao lado do laço ReAct —
ganha um dono declarado e o outro passa a dizer de si mesmo que não serve
produção.

O padrão continua sendo propor. O interruptor de emergência continua mandando.
Os cotos que recusam a chamada direta continuam recusando, com a mesma frase, e
nenhuma tarefa deste plano os toca.

## Technical Context

**Language/Version**: Python 3.12. Nenhum TypeScript.

**Primary Dependencies**: `platform/remediation/` (portão, executor, construtor
de pedido, gerador de plano, registro de resultados, obrigações de
verificação), `platform/autonomy/` (portão de política, resolução, limites,
serviço), `platform/approvals/` (serviço de aprovação, appliers, política de
segurança), `platform/sandbox/` (perfil de isolamento e provisionador),
`capabilities/tools/remediation/` (os componentes das capacidades embarcadas),
`capabilities/registry/` (registro, resolução por disponibilidade, ranqueador),
`core/agent/` (laço, registro de hooks, balcão de perguntas), `gateway/http/`
(a composition root assíncrona e as rotas), `gateway/runtime/` (o investigador
de serving).

**Storage**: nenhuma migração. As três tabelas que esta feature passa a povoar
já existem — `approvals`, `rollback_plans` e `remediation_outcomes` — e a
última tem os índices que a leitura de eficácia usa. Nada é apagado, nada é
migrado.

**Testing**: pytest. Unit onde a peça é isolável, contract onde a garantia é
estrutural (a recusa direta, o portão como caminho único), e cenário sintético
para a investigação ponta a ponta. Sem Playwright — não há tela.

**Target Platform**: backend Python servido pelo gateway.

**Project Type**: composição. O trabalho é ligar peças existentes numa
composition root e narrar honestamente o que fica dormente.

**Performance Goals**: nenhuma meta de latência. Duas restrições de custo, e
ambas são de correção: a política de autonomia é resolvida por decisão de
portão e não por chamada de ferramenta, e o registro de capacidades é
construído uma vez por processo.

**Constraints**: a verificação completa do repositório precisa terminar verde
tendo partido de verde; nenhuma recusa fail-closed pode ser removida ou
afrouxada para um teste passar; o que roda contra o ambiente compartilhado para
na proposta.

**Scale/Scope**: três composition roots tocadas, uma nova, e um caminho de
orquestração declarado dormente.

## Constitution Check

*GATE: precisa passar antes da execução. Reconferir ao final.*

A checagem é feita contra a constituição **como ela fica depois da feature de
governança desta onda** — a que escreve a emenda pendente e acrescenta a regra
de composição.

| Artigo | Como este plano satisfaz |
|---|---|
| I — Evidência sobre asserção | Cada afirmação de "isto não está composto" foi conferida na árvore antes de virar tarefa, e o baseline da suíte é capturado antes da primeira linha. A prova de que a feature funcionou é contagem no armazenamento depois de uma investigação, não teste verde no harness. |
| II — Autonomia limitada | Não mexe em teto de iteração, relógio de parede nem orçamento de contexto. O portão de autonomia é o mecanismo do artigo passando a existir, com o padrão sem configuração resolvendo para propor e o interruptor recusando em qualquer nível. |
| III — Leitura por padrão | **É o artigo que esta feature implementa.** As cinco cláusulas: o nível de efeito colateral já é declarado; a aprovação passa a acontecer na superfície que a pessoa já usa; o plano de reversão é gravado antes da execução, na mesma unidade de trabalho do pedido; a aprovação é por ação e não generaliza — o portão não guarda memória de decisão anterior, e é por isso que ele não cacheia nada; a lista de permissão continua opcional, por tipo de ação, revogável pelo interruptor e auditada. Nada aqui alarga autonomia. |
| IV — Segredo nunca chega ao agente | Nada nesta feature carrega credencial. O plano de controle alcança o vendor pelo proxy como qualquer outra chamada autenticada, e o que o port passa é a ação e o estado desejado. A pergunta que pede credencial continua recusada antes de aparecer para qualquer pessoa. |
| V — Um runtime canônico | **É o artigo que decide o caminho duplicado.** O laço ReAct é o runtime canônico e é o que o caminho de serving já dirige. O pipeline de seis estágios não é um segundo runtime — ele orquestra um — mas é um segundo caminho de orquestração, e esta feature declara qual serve produção e faz o outro dizer de si mesmo que não serve. Ver a seção própria. |
| VI — Neutralidade de provedor | Não toca a abstração de provedor. |
| VII — Aprendizado é medido | A obrigação de verificar se a remediação funcionou é gravada quando a execução muda alguma coisa, que é o que impede "apertei o botão" de ser confundido com "resolveu". O veredito continua sendo dado pelo trabalho de laço fechado que já existe, depois do período de acomodação — esta feature não alcança veredito dentro do run. |
| VIII — Arquitetura em camadas | Nenhum tier novo e nenhuma inversão. O módulo de composição novo mora no tier mais alto, que é onde é legal ver `platform/`, `capabilities/` e `integrations/` ao mesmo tempo — a mesma posição que os outros compositores da mesma família ocupam. As checagens de contrato de import rodam na verificação final. |
| IX — Capacidades declaradas | Nenhuma capacidade nova. O que muda é quais das declaradas são oferecidas a um turno, e o critério passa a incluir o que este deployment consegue levar adiante. |
| X — O operador é dono dos dados | Nada sai do host. Nada é apagado. |
| XI — Datastore único | Nenhum armazenamento novo. As três tabelas usadas já existem, e o pedido e o plano continuam sendo escritos numa unidade de trabalho só. |
| XII — Test-first, rastreado | Cada comportamento novo ganha o seu vermelho antes da implementação, confirmado e registrado. A cláusula que morde aqui é a do efeito sobre a suíte de cenários: a feature muda quais ferramentas uma investigação recebe, o que é exatamente uma mudança que pode alterar trajetória, então a contagem antes e depois é obrigatória e "sem efeito" só vale se tiver sido medido. |
| XIII — Idioma e atribuição | Todo arquivo committed em inglês, sem identificador de planejamento, sem número de artigo, sem número de feature. |
| **Composição** (regra nova da onda) | **É o artigo que esta feature existe para satisfazer.** As três composition roots estão nomeadas abaixo com arquivo e linha; o caminho que não serve produção declara de si mesmo que está dormente e nomeia o que o constrói; e o DoD é evidência do caminho de serving — contagem no armazenamento depois de uma investigação — e não suíte verde. |

### Complexity Tracking

Uma violação a justificar, e ela é de superfície e não de comportamento: esta
feature acrescenta um objeto composto ao estado do gateway e um caminho de
execução na rota que decide uma aprovação. A alternativa — não acrescentar
nada e deixar a aprovação só registrar — é o estado atual, no qual a metade que
age não existe. A complexidade acrescentada é a mínima que faz o laço fechar:
um compositor, um campo de estado, um método público no portão e um ramo na
rota de decisão.

## As composition roots, declaradas

Três roots, com a ordem em que cada uma sabe o que a próxima precisa. É o que
a regra nova exige e é o que faltou nas cinco vezes anteriores.

### 1. A root síncrona, que só conhece o ambiente — **não muda**

```
gateway/http/serve.py            (entrypoint do contêiner)
  → gateway/http/asgi.py:191     build_deployment
      → gateway/http/asgi.py:168 investigator_of
          → gateway/http/asgi.py:75  load_investigator
              → gateway/runtime/factory.py:40  build_investigator
                  → gateway/runtime/investigator.py:80  ReActInvestigationRunner
```

Ela é síncrona e conhece só o processo. Não tem handle de banco, não tem
escopo de tenant e não tem a configuração do time — e por isso **nada desta
feature é composto aqui**. É o mesmo motivo pelo qual o próprio investigador
diz, na sua docstring, que não consegue estreitar por integração: uma fábrica
sem argumento não segura um handle de persistência.

### 2. A root assíncrona, que tem loja que responde — **é onde o fio é ligado**

`gateway/http/lifespan.py:43` é a root que roda depois de a loja responder, e é
onde mora a família de compositores que esta feature imita:
`compose_integration_access` (linha 63), `compose_provider_credentials` (72),
`recompose_investigator` (79), `compose_deep_verifier` (83),
`compose_change_sources` (84), `compose_discovery_sources` (88),
`compose_signal_sources` (96), `compose_enrichment_plans_for` (104),
`compose_node_access` (109), `compose_log_sources` (116).

Módulo novo: **`gateway/http/remediation.py`**, com
`compose_remediation(state, *, org_id)`, modelado linha a linha em
`gateway/http/deep_verification.py:54` — mesma forma, mesmo tratamento do caso
"este deployment não tem como", mesma linha de log dizendo por que não compôs.

Chamada em `lifespan.py` **depois** de três coisas, e a ordem é a
especificação:

1. depois de `compose_integration_access`, porque o executor alcança o vendor
   pelo proxy que ela vincula;
2. depois de `compose_provider_credentials`, pelo mesmo motivo;
3. depois de `recompose_investigator` (linha 79), porque o compositor entrega o
   balcão de remediação **ao runner que existe naquele instante**, e o runner é
   reconstruído ali. Compor antes seria entregar ao objeto que foi jogado fora.

O que `compose_remediation` constrói, uma vez por processo:

| Peça | Origem | Nota |
|---|---|---|
| `ComponentRegistry` | `capabilities/tools/remediation/__init__.py:78 registry(known_signals=…)` | Os sinais conhecidos vêm das fontes de observação que a própria `lifespan` acabou de compor, para que uma capacidade que nomeia um sinal que ninguém produz falhe na composição e não na primeira execução. |
| `PlanFactory` | `platform/remediation/rollback/generator.py:69` | Despacho para o gerador da própria capacidade. |
| `RequestBuilder` | `platform/remediation/request.py:178` | Com `approvals=ApprovalService(...)`, `gateway=state.gateway`, escopo do tenant, e a consulta de eficácia sobre o registro de resultados. |
| `RemediationExecutor` | `platform/remediation/execution.py:228` | Com `kill_switch=state.kill_switch` (o do processo, `gateway/http/state.py:189` — nunca um novo), auditor sobre o gravador de auditoria, obrigações sobre o registro de resultados, e o aplicador de desfazer para o caso do meio-aplicado. |
| `SandboxIsolation` | `platform/remediation/execution.py:536` | Perfil lido de `platform/sandbox/selection.py:123 resolve_profile`, provisionador correspondente sob `platform/sandbox/profiles/`. Um deployment cujo perfil não provisiona não compõe o balcão, e a linha de log diz isso. |
| `GatingPolicy` | `platform/remediation/gating.py:99`, via `of_policy` (linha 110) | O padrão de silêncio é o estrito: uma organização que não declarou nada porta tudo acima de leitura sensível. |
| construtor de `AutonomyGate` | `platform/autonomy/service.py:151 AutonomyService.gate` | Não um portão pronto: um construtor. Ver "Por que o portão de autonomia é construído por decisão". |

O resultado fica em dois lugares, porque tem dois consumidores:
`state.remediation` (para a rota de aprovação) e o campo novo do runner (para o
laço). Um objeto só, referenciado duas vezes — não duas construções.

### 3. A root por investigação — **onde o portão encontra o run**

`gateway/runtime/investigator.py:226 _build_runtime` é a root por run. Hoje ela
constrói o laço com `investigation_hooks()` (`core/pipeline/build.py:43`), que
registra um único hook, o guarda de janela do incidente. Passa a construir,
por investigação:

- o `RunContext` (`platform/remediation/gating.py:127`) — quem pede, qual time,
  qual run, qual ambiente;
- o `RemediationGate` daquele run, registrado no registro de hooks por
  `register` (`gating.py:217`), que o prende em `pre_tool_use` na ordem −50,
  depois dos guardrails e antes de qualquer outro;
- o `HumanHandoff` daquele run (`core/agent/handoff.py:356`), com o seu próprio
  `InteractionRegistry`, guardado no `_LiveRun` (`investigator.py:68`) para que
  `pending_interactions`, `find_interaction` e `answer_interaction` passem a
  responder de verdade;
- a seleção de ferramentas estreitada, em `_select_tools`
  (`investigator.py:235`).

**Por run, e não por processo.** O contexto de run carrega o requisitante e o
time; um portão por processo carregaria o contexto do run que o construiu, e a
segunda investigação simultânea proporia mudanças atribuídas à primeira. O
mesmo vale para o balcão de perguntas, e ali é pior: uma resposta fecharia a
pergunta do incidente errado.

### 4. A root por decisão de aprovação — **onde a execução acontece**

`gateway/http/routes/approvals.py:256 decide_approval` grava a decisão e, hoje,
diz na própria docstring que nunca invoca a capacidade que a aprovação nomeia.
Passa a, quando o veredito é aprovar e a mudança é de remediação, levar a ação
adiante **através do portão** que `compose_remediation` deixou em
`state.remediation`.

A ordem é a que o applier de remediação já descreve
(`platform/remediation/execution.py:567`): aprovar, persistir, reavaliar,
executar. A gravação da decisão continua vindo primeiro — uma queda entre as
duas deixa uma aprovação registrada que não rodou, que um operador acha e
reexecuta, enquanto o inverso deixa uma mudança aplicada sem nada dizendo quem
autorizou, que é indistinguível de um comprometimento.

## Por que não há espera dentro do laço

`DecisionWaiter` (`platform/remediation/gating.py:144`) é um protocolo **sem
nenhuma implementação na árvore** — e este plano não escreve uma. O portão
compõe com `waiter=None`, e é uma escolha, não uma omissão:

- uma aprovação de produção é respondida em minutos ou horas, e uma iteração de
  laço suspensa por isso é uma investigação que estoura o relógio de parede
  segurando um modelo e um sandbox;
- em propose-only ninguém vai aprovar durante o run de qualquer maneira: a
  política diz propor, e o desfecho correto é a proposta enfileirada e a
  investigação continuando sem a ação — que é literalmente o que
  `_through_approval` (`gating.py:341`) faz quando não há esperador;
- a mensagem que o modelo recebe nesse caminho já é a certa: a ação espera por
  uma pessoa, com a explicação da política junto, e a investigação continua.

A consequência é que **execução é sempre uma segunda entrada**, e é por isso
que a root 4 existe. Uma implementação de esperador é trabalho posterior, e a
sua ausência fica dita no módulo em vez de escondida.

## Decisão: o caminho duplicado

**Canônico é o laço ReAct dirigido pelo investigador de serving.** O pipeline
de seis estágios (`core/pipeline/build.py:60 build_pipeline`) é declarado
**dormente**, com a declaração no próprio módulo nomeando o que o constrói: o
harness de avaliação (`tests/harness/runner.py:262` e
`tests/harness/investigator.py:193`), que é quem roda o corpus sintético.

Por quê, e não o contrário:

- O artigo do runtime canônico nomeia o laço ReAct, e o caminho de serving já o
  dirige. Migrar serving para o pipeline seria reescrever a entrada inteira de
  investigação no mesmo slot em que outra feature está mudando o que uma
  investigação relata. É uma feature própria, não um efeito colateral desta.
- O pipeline não é um segundo runtime — o seu estágio de coleta dirige um
  runtime. A duplicação é de orquestração, e a regra nova pede um dono, não uma
  fusão.
- O harness é um consumidor real e valioso: é o instrumento de medida do
  produto. "Dormente" aqui quer dizer "não está no caminho de serving", com o
  construtor nomeado — que é exatamente o que a regra pede — e não "morto".

**O que não é abandonado junto:** o desfecho de zero integrações que
`ResolveIntegrationsStage` monta é a melhor resposta escrita no repositório
para um time que não conectou nada, e ele é uma função de módulo pura —
`zero_integration_outcome` (`core/pipeline/stages/resolve_integrations.py:72`).
O caminho de serving passa a chamá-la; o estágio continua chamando a mesma.
Uma implementação, dois chamadores, e nenhuma chance de as duas respostas
divergirem.

## Decisão: qual dos dois caminhos de estreitamento é o canônico

**`TeamCatalogueResolver` (`capabilities/registry/planning.py:72`), instanciado
no caminho de serving.** É o resolvedor que lê o que o time configurou, e hoje
as suas únicas menções são um exemplo de docstring, um re-export e uma entrada
de `__all__` — a própria docstring do módulo mostra a linha que ninguém nunca
escreveu: `resolver = TeamCatalogueResolver(build_registry())`.

Uma costura precisa ser feita e é pequena: `resolve` recebe um `AgentState`, e
o investigador de serving não constrói um — ele tem um `InvestigationStart`.
O resolvedor ganha uma entrada sem estado que recebe a disponibilidade já
derivada e devolve o catálogo resolvido; `resolve(state)` passa a delegar nela.
Nada duplica: `resolve_for` (`capabilities/registry/catalogue.py:154`) continua
sendo a única implementação da resolução.

**De onde vem "o que o time conectou":** da configuração resolvida do nó do
time — a mesma lista que a visão de catálogo lê para dizer "14 disponíveis, 6
indisponíveis" (`platform/config_service/catalogue.py:173`). Uma fonte por
fato: o que a tela conta e o que a investigação recebe não podem discordar.

**Se a configuração do time não puder ser lida**, a ausência é lida como a
postura mais estrita — nenhuma integração — e o motivo vai para o registro.
Uma leitura falhada não vira permissão.

## Decisão: a capacidade de escrita do cenário ponta a ponta

**`scale_workload`** (`capabilities/tools/remediation/scale_workload/tool.py`).

Por quê: é a única capacidade transversal embarcada que é ao mesmo tempo
`write_reversible`, de classe de risco `low`, e com plano de reversão
**derivável** — o planejador devolve a contagem de réplicas lida antes da
mudança, então o desfazer é um número que foi observado e não uma intenção.
O raio de alcance é uma carga de trabalho.

As rejeitadas, e o motivo de cada uma:

| Capacidade | Por que não |
|---|---|
| `restart_workload` | Irreversível, e destrói o estado de processo que a investigação ainda pode precisar. |
| `clear_cache` | Irreversível e sem reversão derivável — ela existe justamente para exercitar o caminho da dispensa. Um cenário sobre ela estaria provando a dispensa, não a aprovação. |
| `cordon_drain_node` | Classe de risco alta, e o alvo é um nó do estate. |
| `rollback_deployment`, `update_resource_limits`, `toggle_feature_flag` | Classe de risco moderada; nenhuma vantagem sobre a escolhida. |
| As escritas de hipervisor | Agem sobre o estate, que é a infraestrutura que o operador opera de verdade. O cenário de teste não vai lá. |

**O alvo é o próprio deployment, nunca o estate**: uma carga de trabalho que
este deployment é dono, escalada entre dois valores em que ela já roda, e de
volta. E o cenário é exercitado num ambiente que este trabalho controla, com
plano de controle ligado — **não** contra o ambiente compartilhado.

**Contra staging, o que roda para na proposta.** O acceptance de staging é
leitura autenticada da lista de aprovações mais as contagens no banco, e uma
delas é uma contagem que precisa ser **zero**: nenhuma execução de remediação
no ambiente compartilhado. A aprovação de verdade é a demonstração assistida da
feature final da onda.

## Decisão: o balcão de perguntas é por run, não vinculado no processo

A capacidade declarada `ask_human`
(`capabilities/tools/system/ask_human/tool.py`) lê um balcão vinculado no
processo (`capabilities/tools/system/ask_human/binding.py`), e a própria
docstring desse módulo admite o custo: fidelidade de um run por processo. O
gateway dirige investigações concorrentes em segundo plano, então um vínculo de
processo é o mecanismo pelo qual a resposta de um incidente fecharia a pergunta
de outro.

`HumanHandoff.tool()` (`core/agent/handoff.py:598`) já devolve a mesma
declaração — mesmo nome, mesmo esquema, mesma frase sobre credenciais, por
construção (`core/agent/handoff.py:646`) — fechada sobre o balcão daquele run.
O caminho de serving substitui a declarada pela do run, por nome, na seleção de
ferramentas. O vínculo de processo continua existindo para as superfícies de um
run só, e o gateway não o usa.

## Decisão: como a seleção de ferramentas filtra, e em que ordem

Hoje `_select_tools` (`gateway/runtime/investigator.py:235`) ranqueia o
catálogo inteiro contra o alerta e corta no teto de esquemas. Passa a ser, nesta
ordem:

1. **Estreitar pelo que o time conectou** — o resolvedor acima. Sai uma lista e
   sai também o registro do que foi excluído e por qual requisito.
2. **Estreitar pelo que este deployment consegue levar adiante** — uma
   capacidade acima de leitura sensível só entra se o balcão de remediação está
   composto **e** o registro de componentes tem aquela capacidade. Sem as duas,
   ela sairia do turno com uma recusa, que é o turno perdido medido.
3. **Substituir a pergunta pela do run**, por nome.
4. **Ranquear** contra o que o alerta diz.
5. **Cortar** no teto de esquemas.

O corte é o último passo, e isso importa: cortar antes de estreitar gasta vagas
do orçamento com capacidades que seriam removidas em seguida.

**Se a lista estreitada ficar vazia**, a investigação termina com a resposta de
zero integrações — qual conectar, quantas capacidades destravaria, exemplos
delas, e a correspondente à fonte do alerta primeiro.

## Decisões de design

- **O teste vermelho nasce contra a árvore atual, não contra uma composta pela
  metade.** Cada asserção de composição — "existe um construtor que não é
  teste", "o hook está registrado no laço que serve", "uma capacidade de
  escrita não é oferecida a um deployment que não pode remediar" — é escrita e
  confirmada vermelha antes de a composição existir. Uma composição validada
  depois do fato não distingue "liguei certo" de "o teste não olha", que é
  exatamente a forma de falha que esta onda existe para pegar.

- **A recusa direta ganha um teste de caracterização antes de qualquer coisa
  ser composta, e ele tem de estar verde nas duas pontas.** É o único teste
  desta feature que nasce verde, e o motivo fica escrito: ele é a rede que pega
  a feature afrouxando a garantia enquanto a faz funcionar.

- **O portão é o caminho único, inclusive para a rota de aprovação.** A
  execução depois da aprovação não chama o executor: chama o portão, que
  reconfere o interruptor e as travas do laço fechado e desce pelo mesmo
  caminho de execução. Um segundo chamador do executor seria a segunda entrada
  que a docstring do portão diz não existir, e um teste estrutural é o que
  mantém isso verdadeiro.

- **O portão de autonomia é construído por decisão, não por processo.** A
  política vive na configuração e uma pessoa a muda pelas rotas que já existem;
  um portão construído no boot decidiria com a política de ontem. Construído
  pelo mesmo `AutonomyService.gate` que a explicação publicada usa, para que o
  que uma tela prevê e o que o portão faz não possam divergir — que é
  literalmente a promessa da docstring de `decide`.

- **O interruptor vem do estado do processo.** `gateway/http/state.py:189` já o
  segura, um por processo, pelo motivo que o próprio comentário dá: um
  interruptor construído por requisição é um interruptor que nunca está
  acionado quando alguém o lê. Nem o portão nem o executor constroem um.

- **Um deployment que não consegue remediar compõe menos, e diz.** Sem perfil
  de sandbox que provisione, sem plano de controle, ou sem componentes, o
  compositor não instala o balcão, escreve a linha de log que nomeia o que
  falta, e a seleção de ferramentas deixa de oferecer escrita. Isso não é
  degradação silenciosa: é a mesma disposição que o verificador profundo tem
  quando não há vínculo de vendor.

- **A tela não é tocada.** Nem componente, nem catálogo de mensagens, nem
  registro de telas. Se a implementação descobrir que precisa de uma chave
  nova, ela declara a chave e o texto no relatório final e a feature dona do
  slot aplica no merge.

- **O efeito sobre a suíte sintética é medido, não presumido.** Esta feature
  muda quais ferramentas uma investigação recebe. Isso é uma mudança de
  trajetória em potencial, e o baseline antes e depois é o que separa "sem
  efeito" de "não olhei".

## Project Structure

### Documentation (this feature)

```text
specs_v7/040-decisao-composta/
├── spec.md
├── plan.md              # este arquivo
├── tasks.md
├── controle.md          # do implementer, não deste plano
└── checklists/requirements.md
```

### Source Code (repository root)

```text
gateway/http/remediation.py                     # NOVO — o compositor do balcão
gateway/http/lifespan.py                        # a chamada, depois da reconstrução do runner
gateway/http/state.py                           # o campo que segura o balcão composto
gateway/http/routes/approvals.py                # levar a aprovação adiante pelo portão
gateway/runtime/investigator.py                 # portão por run, balcão de perguntas, seleção
gateway/runtime/factory.py                      # o campo novo do runner, se a assinatura pedir
platform/remediation/gating.py                  # a entrada pública de "esta aprovação foi dada"
capabilities/registry/planning.py               # a entrada sem estado do resolvedor
core/pipeline/build.py                          # a declaração de dormência, nomeando o construtor
core/pipeline/stages/resolve_integrations.py    # a resposta de zero integrações, agora com dois chamadores
tests/unit/gateway/http/                        # composição: o compositor, a rota, a ordem no lifespan
tests/unit/gateway/runtime/                     # por run: portão registrado, seleção, balcão
tests/unit/capabilities/registry/               # o resolvedor instanciado e o que ele exclui
tests/contract/remediation/                     # a recusa direta e o portão como caminho único
tests/synthetic/                                # a investigação que propõe, e a aprovação que executa
```

**Structure Decision**: um módulo novo, na família de compositores que já
existe, no tier que já é a composition root. Todo o resto é edição de arquivo
existente.
