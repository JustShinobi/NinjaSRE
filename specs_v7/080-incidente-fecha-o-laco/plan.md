# Implementation Plan: O incidente fecha o laço

**Branch**: `feat/v7-080-incidente-fecha-o-laco` | **Date**: 2026-08-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v7/080-incidente-fecha-o-laco/spec.md`

**Slot**: S5, sozinha, com 000, 001, 010, 020, 030, 040, 050, 060 e 070 mergeadas,
publicadas em staging e verificadas.

## Summary

Um contêiner descartável e observado é parado à mão numa janela combinada. O
alerta dispara sozinho, entra pelo webhook autenticado, abre um incidente com
título legível sobre um sujeito que o estate resolve, dispara uma investigação
que grava o que fez, produz um relato que se lê, oferece ao modelo só as
ferramentas que este deployment de fato conectou, propõe religar o convidado com
plano de reversão ao lado, espera — e só executa depois que uma pessoa aprova,
olhando. No fim, o desfecho, o episódio e a timeline estão gravados e o incidente
mostra o que aconteceu.

Essa é a feature inteira. O que ela **constrói** é cola:

1. **Dois roteiros** — o laço de leitura (reexecutável, sem escrita) e o laço
   inteiro (janela combinada, aprovação humana, uma execução).
2. **Um coletor de evidência** — o script que tira as consultas do banco de
   staging com a saída literal, e que arruma as screenshots por estação.
3. **Três documentos** — a evidência consolidada da demo, a coluna nova do
   confronto da onda, e o `backlog.md` reescrito.

Nada mais. Toda linha de comportamento que esta feature toca é comportamento que
outra feature entregou, e um defeito encontrado aqui volta para a dona.

## Technical Context

**Language/Version**: Python 3.12 (coletor de evidência, consultas), Markdown (os
roteiros e os documentos), TypeScript apenas na medida em que os acceptance das
features donas são reexecutados

**Primary Dependencies**: `make deploy-stg` (`scripts/deploy/stg`) para publicar;
o modo de aceitação contra staging que a 000 entrega, para apontar os specs
Playwright existentes à URL real; `psql` a partir do host de infraestrutura para
as contagens; o Alertmanager da stack como fonte de alerta

**Storage**: nenhuma escrita nova. As tabelas lidas são `agent_runs`,
`run_turns`, `tool_calls`, `evidence`, `trace_events`, `approvals`,
`rollback_plans`, `remediation_outcomes`, `episodes`, `incidents`,
`incident_timeline`, `estate_resources`, `audit_events`. Toda consulta é
`SELECT`, escopada por organização.

**Testing**: esta feature não adiciona teste unitário de produto. O que ela roda
é: os acceptance das features donas contra staging (só os seguros em ambiente
compartilhado), a suíte transversal contra staging, e `make verify` completo ao
fim. O coletor de evidência tem teste próprio de unidade — ele monta consultas e
escreve arquivos, e um coletor que escreve o arquivo errado corrompe a única
prova que a onda tem.

**Target Platform**: staging k3s `k3s-stg-ninjasre`, `https://stg-ninjasre.lan.kyo.ninja`,
banco `ninjasre-stg-db` em `10.20.20.54`, alcançados a partir do host de
infraestrutura Proxmox

**Project Type**: integração e demonstração; sem produto novo

**Performance Goals**: nenhum

**Constraints**: propose-only intacto; nenhum segredo em roteiro, evidência ou
screenshot; nenhum arquivo de produto alterado; nenhuma mudança de
infraestrutura; nenhuma tela nova; screenshots em 1920×1080; o passo destrutivo
digitado por uma pessoa

**Scale/Scope**: dez estações, dois roteiros, um coletor, três documentos, uma
janela

## Constitution Check

Constituição em `.specify/memory/constitution.md`, na versão que a 000 deixa —
**2.2.0**, com a emenda "composed or it is not shipped". Cada artigo, e como este
plano o satisfaz.

- **Art. I — Evidência sobre asserção**: é a feature inteira. Cada estação exige
  a evidência antes do veredito, cada alegação de gravação exige a consulta com a
  saída literal, e "vi funcionar" não é aceito em lugar nenhum. A cláusula de que
  um resultado de ferramenta que não entrou no trace não aconteceu é exatamente o
  que a estação E4 mede.
- **Art. II — Autonomia limitada**: nada muda nos limites do loop. A demo os
  exercita como estão.
- **Art. III — Somente leitura por padrão**: a única escrita da demo é uma ação
  reversível de alcance mínimo, aprovada por uma pessoa, com plano de reversão
  registrado antes. A recusa de chamada direta às capacidades de remediação
  continua valendo e nenhuma tarefa a contorna. A demo também exercita a
  rejeição, porque um caminho de aprovação que nunca recusou não foi exercitado.
- **Art. IV — Segredos não chegam ao agente**: nenhum roteiro transcreve segredo;
  nenhuma screenshot pode conter credencial, e a tarefa de revisão da evidência
  existe por causa disso. As credenciais continuam entrando na borda pelo proxy.
- **Art. V — Um runtime canônico**: a demo roda contra o runtime que a onda
  compôs. Nenhum caminho alternativo é criado para fazer a demo passar — um
  atalho para a demo seria a mentira que esta feature existe para tornar
  impossível.
- **Art. VI — Neutralidade de provider**: a demo usa o provider que o deployment
  tem verificado; o roteiro não nomeia vendor como pré-requisito de mecanismo.
- **Art. VII — Aprendizado é medido ou não é alegado**: esta feature não adiciona
  mecanismo de aprendizado. Ela **verifica** que o episódio da investigação foi
  gravado — que é registro, não alegação de melhoria. O julgamento editorial de
  eficácia fica declarado fora de escopo.
- **Art. VIII — Arquitetura em camadas**: o coletor de evidência é ferramenta de
  repositório, vive sob `tools/`, e não é importado por nenhum tier. Não há
  código de produto nesta feature, logo não há contrato de import a mover.
- **Art. IX — Capacidades são declaradas**: a capacidade exercitada já existe
  declarada, com nível de efeito, exigência de aprovação, razão e planejador de
  rollback. Nenhuma capacidade nova nasce aqui e nenhum metadado é afrouxado.
- **Art. X — O operador é dono dos dados**: a demo roda no cluster do próprio
  operador, contra o Alertmanager dele, e nada sai do host. A evidência fica no
  diretório da feature, que não é committed.
- **Art. XI — Datastore único**: as consultas de evidência são leitura direta ao
  banco de staging **como instrumento de verificação**, não como caminho de
  produto — nenhum código de produto ganha SQL fora da camada de persistência, e
  o coletor não é importado por nenhum tier. Nenhuma migração.
- **Art. XII — Test-first, com trace**: o análogo aqui é o **gabarito antes da
  execução**. O roteiro e a tabela de evidência esperada aterrissam **antes** da
  demo, e a execução a seco do coletor contra o staging pré-demo é o vermelho
  registrado: as consultas rodam e devolvem os valores de partida (`0`, `0`, `0`,
  nenhuma proposta), que é a prova de que elas medem a coisa certa. Uma consulta
  que já devolvesse verde antes da demo não estaria medindo o laço.
- **Art. XIII — Idioma e atribuição**: o `backlog.md` reescrito é committed, e
  por isso não cita caminho de planejamento, número de feature, identificador de
  requisito, artigo de constituição, nem nome de projeto de origem. Ele afirma a
  substância. Os roteiros e a evidência vivem no diretório desta feature, que não
  é committed, e nada committed aponta para eles.

**Composição (regra 2.2.0)**: esta feature **não entrega mecanismo novo**, e por
isso não declara composition root própria. O que ela faz com a regra é o inverso:
ela é a auditoria dela. A coluna "quem constrói isso em produção?" do confronto é
o artefato pelo qual a regra passa a existir na prática, e a demo é a evidência
de caminho de serving que a regra exige de todas as outras features da onda.

**Veredito**: sem violações. A seção Complexity Tracking fica vazia.

## Project Structure

### Documentation (this feature)

```text
specs_v7/080-incidente-fecha-o-laco/
├── spec.md
├── plan.md                       # este arquivo
├── tasks.md
├── checklists/requirements.md
├── runbooks/
│   ├── laco-de-leitura.md        # reexecutável, sem escrita, sem janela
│   └── laco-inteiro.md           # janela combinada, aprovação humana
├── evidence/
│   ├── EVIDENCIA.md              # o documento consolidado, estação por estação
│   ├── consultas/                # SQL + saída literal, um arquivo por estação
│   └── telas/                    # screenshots full-page 1920×1080
└── controle.md                   # escrito pelo implementador, não aqui
```

### Repository (o que esta feature escreve fora do próprio diretório)

```text
tools/demo_evidence/              # o coletor: consultas nomeadas, saída literal
tests/unit/tools/                 # teste do coletor
backlog.md                        # reescrito na última tarefa
specs_v7/CONFRONTO.md             # a coluna nova, preenchida
```

**Structure Decision**: nada em `gateway/`, `platform/`, `core/`,
`capabilities/`, `integrations/`, `config/` ou `console/`. Se uma tarefa desta
feature precisar tocar um desses diretórios, a tarefa está errada: o que ela
encontrou é reparo de outra feature.

## Decisões de design

### A remediação é religar um convidado do Proxmox, e a vítima é a `redis` (CT122)

A capacidade é **`proxmox_start_guest`**. Ela satisfaz as quatro condições que
uma remediação de demo precisa satisfazer ao mesmo tempo:

- **É reversível** — declarada `WRITE_REVERSIBLE`, com o desligamento como
  reversão declarada, e não como improviso.
- **Tem alcance mínimo** — um convidado, num nó, sem efeito sobre vizinhos.
- **Exige aprovação** — declara `requires_approval` com razão escrita ("um
  convidado que estava parado é um convidado que alguém parou por um motivo"),
  que é exatamente o texto que a demo precisa mostrar na tela.
- **Fecha o laço causal** — a mesma ação que o operador faria à mão é a que o
  produto propõe, o que torna o sucesso verificável por um sinal (`o convidado
  está rodando`) em vez de por uma frase.

A vítima é a `redis` (CT122, pve01, `10.20.20.52`) porque a validação anterior já
pagou o preço de descobrir que **descartável não basta**: não existe regra que
dispare quando um LXC qualquer para. `dockge`, `streamlink-webui` e `bazarr` são
descartáveis e invisíveis — pará-las não dispara nada, e o roteiro morreria na
primeira estação sem que isso fosse defeito do produto. A `redis` é alvo de
scrape do job `redis-exporter`, o que faz `InstanceDown` e `RedisExporterDown`
dispararem com `for: 2m` e `severity: critical` — que é o rótulo que a rota do
Alertmanager casa para chegar até aqui.

**Duas coisas precisam ser confirmadas antes de qualquer passo destrutivo**, e as
duas são tarefa, não suposição: que a CT122 continua fora de uso e autorizada em
2026-08-23, e que o token do Proxmox que este deployment guarda tem
`VM.PowerMgmt` em `/vms`. Se o token for de leitura, a estação E9 falha por
privilégio — e conceder escrita ao token do produto é decisão do operador sobre
fronteira de segurança, não coisa que esta feature resolve por conta própria.

**Candidata alternativa, se a `redis` for recusada**: qualquer alvo de scrape ou
sonda real cujo serviço o operador declare dispensável por dez minutos. O roteiro
é escrito com a identidade da vítima como parâmetro conferido no primeiro passo,
justamente para que uma troca de vítima não exija reescrever o roteiro.

### Dois roteiros, porque eles provam coisas diferentes

O **laço de leitura** prova repetibilidade: qualquer pessoa, a qualquer hora, sem
janela, sem escrita, sem operador. Ele é o que um verificador independente
executa para conferir a onda depois que todo mundo foi dormir.

O **laço inteiro** prova a coisa que nenhuma automação pode provar por
construção: que uma pessoa olhou uma proposta e decidiu. Uma aprovação feita por
chamada de API é uma aprovação que o produto poderia ter dado a si mesmo, e a
frase "aprovação humana" perderia o sentido no exato momento em que ela passa a
importar.

Os dois compartilham as estações E1 a E7. O laço inteiro continua em E8, E9 e
E10.

### Flakiness de ambiente é classificada antes, nunca depois

Cada estação declara seus desfechos de ambiente **antes** da execução. Isso é
deliberado e é a única defesa contra a leitura que corrói uma demo: rodar,
falhar, e decidir na hora que a falha "foi do ambiente". Um desfecho classificado
depois do fato é uma desculpa; um classificado antes é um critério.

A regra que separa os dois: **se a mesma execução repetida amanhã, sem mudar uma
linha de código, tem chance razoável de passar, é ambiente.** Se ela vai falhar
igual até alguém mudar código, é produto — e tem dona.

### Esta feature encontra defeitos e não os conserta

O reflexo natural, ao ver a estação E5 imprimir markdown cru às onze da noite, é
consertar — são três linhas. É exatamente esse reflexo que produziu cinco
mecanismos escritos e não compostos: o conserto rápido entra sem teste, sem
verifier, sem dono, e a feature que deveria tê-lo entregue continua marcada PASS.

Então: achado vira registro, com estação e dona nomeadas. O orquestrador decide
se gasta um ciclo de reparo. Se decidir que sim, a dona repara, e **a estação é
reexecutada e a evidência substituída** — nunca acumulada como se as duas
capturas fossem verdadeiras ao mesmo tempo.

### A evidência é um artefato de leitura, não um despejo

Um diretório com trinta PNGs e um arquivo de log não é evidência: é matéria-prima
para alguém montar evidência depois, o que ninguém faz. O documento consolidado
é a entrega — estação, expectativa, o que se viu, o link para a screenshot, a
consulta, a saída literal, o veredito, o instante. Ele também registra o digest
publicado e o estado do Argo, porque uma evidência que não aponta uma versão
prova algo sobre um sistema que não se sabe qual era.

### As consultas do banco medem contraste, não valor absoluto

Cada consulta é apresentada com o valor de partida ao lado do valor medido. "3
tool calls" é um número; "0 → 3 tool calls, para este run, lidos depois de
reload" é uma prova. Os valores de partida já estão medidos e são citados na
spec, o que também dá ao coletor um teste de sanidade: se a execução a seco
**antes** da demo não devolver os valores de partida, a consulta está medindo
outra coisa.

### O backlog reescrito é um arquivo committed, e isso decide como ele fala

`backlog.md` é versionado. Quem clona o repositório não tem a onda, não tem os
briefings, não tem esta spec e não tem número de feature nenhum. Então o item
fechado sai, e o item que fica é descrito como o próprio arquivo já descreve: o
que acontece hoje, por que não é trivial, e o desfecho pelo qual seria julgado. A
evidência de fechamento de cada item removido fica no confronto da onda, que não
é committed — e o backlog não aponta para lá, porque um arquivo committed não
pode depender de um que não é.

### O confronto ganha a coluna, e a coluna é preenchida por leitura de código

`file:line` da composition root de serving se obtém lendo o código, não
perguntando à feature. O caminho mais barato é o índice de símbolos do
repositório: para cada mecanismo, quem o constrói, e se o único construtor é um
teste, a resposta é **dormant** com a referência do que o ligaria. Uma célula
apontando um contract test é pior que uma célula vazia, porque parece resposta.

## Fases operacionais

Estas fases tocam o cluster e o estate. Cada uma declara pré-condição, ação,
**verificação** e **reversão escrita antes da ação**. Nenhuma começa antes de a
anterior verificar.

### Fase O-A — O staging é a ponta da onda

- **Pré-condição**: todas as features da onda mergeadas e verificadas.
- **Ação**: `make deploy-stg` com os componentes que mudaram.
- **Verificação**: o Argo reporta `Synced + Healthy` **e** o serviço responde na
  URL pública. As duas coisas, separadamente — reconciliar Git não é responder
  HTTP, e um digest inexistente no registry reconcilia lindamente.
- **Reversão**: republicar o digest anterior pelo mesmo caminho.
- **Se reprovar**: a demo não começa. É ambiente, e é reexecutável.

### Fase O-B — O ambiente está apto a fechar o laço

- **Pré-condição**: O-A verificada.
- **Ação**: nenhuma alteração. Conferir: provider Verified; Proxmox conectado e
  o estate povoado; o token do Proxmox com o privilégio de gerência de energia;
  a vítima `running`; a regra de alerta que a cobre ativa; a rota do Alertmanager
  casando a severidade; o webhook aceitando entrega autenticada.
- **Verificação**: cada item conferido é registrado com o comando e a saída.
- **Reversão**: nada a reverter.
- **Se reprovar por privilégio de token**: a demo executa o laço de leitura e a
  estação E9 fica **não exercida**, com a decisão pendente do operador registrada
  — nunca marcada como aprovada por omissão.

### Fase O-C — O gabarito roda a seco contra o staging pré-demo

- **Pré-condição**: O-B verificada.
- **Ação**: rodar o coletor de evidência contra o staging **antes** da demo.
- **Verificação**: as consultas devolvem os valores de partida esperados. É o
  vermelho registrado desta feature.
- **Reversão**: nada — é leitura.

### Fase O-D — A janela do laço inteiro

- **Pré-condição**: O-C verificada; operador presente; vítima confirmada por ele
  na abertura da janela; hora anotada.
- **Ação**: parar a vítima, à mão, uma vez. Nada mais é digitado até a estação E7.
- **Verificação**: as dez estações, na ordem, com a evidência de cada uma.
- **Reversão**: religar o convidado à mão. Vale a qualquer instante, não depende
  do produto, e não espera por ele. Se a ação proposta for aprovada, o efeito é a
  mesma religada; se for rejeitada, ou se qualquer coisa parecer errada, religue
  sem esperar.
- **Limite**: uma vítima por vez, uma janela por vez. Nenhum segundo recurso é
  derrubado para "testar de novo" sem nova combinação.

### Fase O-E — As tarefas operacionais, verificadas e não executadas

- **Pré-condição**: nenhuma.
- **Ação**: conferir a evidência de cada uma — resolução de nome de dentro dos
  contêineres de monitoração, sincronização do segredo gerenciado, provider do
  gateway de modelos Verified.
- **Verificação**: a saída de cada conferência, anexada.
- **Reversão**: nada — nenhuma mudança é feita. O que não estiver feito entra no
  backlog novo com o estado real.

## Complexity Tracking

Sem violações da constituição a justificar. Tabela intencionalmente vazia.
