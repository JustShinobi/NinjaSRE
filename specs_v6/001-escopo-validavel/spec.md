# Feature Specification: Escopo validável — o catálogo cai para o que o ambiente valida

**Feature Branch**: `feat/v6-001-escopo-validavel`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "O produto só oferece o que o ambiente do operador consegue validar. Catálogo de integrações de 85 para 15; remoção real dos pacotes das outras 70; intake de alertas reduzido a alertmanager, grafana e generic; todo gate, contagem e documento que hoje afirma 85 ajustado; ADR novo supersedendo o de paridade total e emenda correspondente da constituição."

**Referência visual (DoD)**: nenhuma. Esta feature **não tem tela própria**. A
superfície de console do catálogo pós-corte (grid sem paginação, detalhe em
slide-over) é da 050, e o passo de Alert intake é da 050 também. Aqui o console
só é tocado para que nada fique órfão — rota, fixture, baseline ou contagem
apontando para vendor que deixou de existir. Por isso **não há acceptance spec
Playwright nesta feature**: não há alegação de mockup para codificar.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - O catálogo só oferece o que este ambiente valida (Priority: P1)

Um operador abre o catálogo de integrações e encontra 15 vendors, todos eles
conectáveis contra a infraestrutura que ele opera de fato. Nenhum card promete
um sistema que este deployment não tem como alcançar, verificar nem exercitar.

**Why this priority**: é a decisão que governa a onda. 85 integrações
produziram superfície morta: 70 vendors sem ambiente que os valide, cada um
carregando sete artefatos que nenhum teste consegue manter honestos. Um card que
não pode ser verificado é pior que um card ausente — ele é escolhido com base na
presença e falha às 3 da manhã.

**Independent Test**: pedir o catálogo ao gateway e conferir que a resposta traz
exatamente os 15 vendors nomeados nesta spec, cada um com paridade completa.

**Acceptance Scenarios**:

1. **Given** um deployment com a árvore pós-corte, **When** o catálogo é
   pedido, **Then** ele lista exatamente 15 integrações e nenhuma outra.
2. **Given** o catálogo pós-corte, **When** a paridade de cada item é
   consultada, **Then** as 15 estão completas e nenhuma reporta artefato
   faltando.
3. **Given** um nome de vendor removido, **When** ele é pedido ao catálogo,
   **Then** a resposta é uma ausência nomeada, não um item degradado.

---

### User Story 2 - O intake aceita só as fontes que este ambiente entrega (Priority: P1)

O produto recebe alerta de `alertmanager`, de `grafana` e de uma fonte
`generic`. As quatro fontes que existiam por catálogo e não por ambiente —
Datadog, Opsgenie, PagerDuty e Sentry — deixam de existir no backend.

**Why this priority**: o Alertmanager da stack de monitoring é quem vai entregar
o primeiro incidente real (feature 060). Manter quatro rotas de intake que
ninguém pode exercitar é a mesma superfície morta do catálogo, com a agravante
de serem rotas públicas autenticadas.

**Independent Test**: exercitar as três rotas mantidas e as quatro removidas,
conferindo que as primeiras seguem aceitando a carga que aceitavam e que as
segundas deixaram de existir como endereço.

**Acceptance Scenarios**:

1. **Given** a árvore pós-corte, **When** um alerta chega pela fonte
   `alertmanager`, **Then** ele é aceito exatamente como antes do corte.
2. **Given** a árvore pós-corte, **When** o endereço de uma das quatro fontes
   removidas é chamado, **Then** o produto responde que aquele endereço não
   existe, e não um erro de autenticação nem de servidor.
3. **Given** a enumeração de fontes de alerta do domínio, **When** ela é
   consultada, **Then** ela declara três fontes e nenhuma das quatro removidas.

---

### User Story 3 - Todo número que o repositório afirma é o número real (Priority: P1)

Nenhum gate, teste, documento gerado ou texto de produto continua afirmando 85,
84 ou "todas as ~85". A contagem que aparece em qualquer lugar é derivada do
catálogo ou é 15, e é verdadeira.

**Why this priority**: um gate que conta errado passa a mentir no momento exato
em que ele existe para não deixar mentir. A paridade é enforçada, não revisada —
se ela iterar uma lista que não corresponde à árvore, ela deixa de ser uma
propriedade do catálogo e vira decoração.

**Independent Test**: rodar a verificação completa do repositório partindo de
verde e conferir que ela continua verde com o catálogo em 15, e que cada
afirmação de contagem em arquivo committed corresponde à árvore.

**Acceptance Scenarios**:

1. **Given** a árvore pós-corte, **When** a verificação de integrações roda,
   **Then** ela reporta 15 integrações em paridade total.
2. **Given** a árvore pós-corte, **When** a checagem de documentação gerada de
   integrações roda, **Then** ela não acusa desvio.
3. **Given** qualquer arquivo committed, **When** ele afirma um total de
   integrações, **Then** o total afirmado é 15 ou é derivado do catálogo em
   tempo de execução.

---

### User Story 4 - A regra escrita acompanha o produto (Priority: P2)

A decisão de paridade deixa de ser "todas as ~85" e passa a ser "toda integração
embarcada, e a amplitude é estagiada por ambiente validável". A decisão vive num
registro de decisão arquitetural novo, que supersede o anterior, e o artigo
correspondente da constituição é emendado no mesmo sentido.

**Why this priority**: o corte sem a emenda deixa o repositório em contradição
formal — a norma exige paridade sobre 85 integrações que não existem mais, e
todo plano futuro reprova a checagem contra ela. É P2 e não P1 porque a
contradição é de documento, não de comportamento.

**Independent Test**: ler o registro de decisão novo e o artigo emendado e
conferir que ambos descrevem a mesma regra que o gate enforça, sem citar um
total fixo.

**Acceptance Scenarios**:

1. **Given** o registro de decisão anterior sobre paridade, **When** o novo é
   aceito, **Then** o anterior consta como superseded, com data e ponteiro para
   o sucessor.
2. **Given** o registro novo, **When** ele é lido, **Then** ele mantém a
   paridade em sete artefatos e altera apenas a amplitude, apontando a seção de
   escopo de integrações do roadmap committed.
3. **Given** a constituição local, **When** o artigo de capacidades é lido,
   **Then** a cláusula de paridade fala de integração embarcada e não de um
   total, e a versão do documento subiu com sumário de emenda.

---

### User Story 5 - Nada fica órfão no console (Priority: P2)

Nenhuma rota, fixture, registro de tela ou baseline visual do console aponta
para um vendor que deixou de existir. As suítes de console que já passavam
continuam passando.

**Why this priority**: a tela do catálogo é da 050, mas o corte acontece aqui.
Um registro de tela apontando para um vendor removido transforma o gate visual
da próxima feature numa falha que ninguém escreveu.

**Independent Test**: rodar as suítes de console existentes e conferir que
nenhuma referência a vendor removido sobra em rota, fixture ou registro de tela.

**Acceptance Scenarios**:

1. **Given** a árvore pós-corte, **When** as suítes de console existentes
   rodam, **Then** todas passam.
2. **Given** o registro de telas visuais, **When** ele é lido, **Then** nenhuma
   entrada aponta para rota de vendor removido.
3. **Given** um baseline visual cuja tela deixou de existir com o corte,
   **When** o gate visual roda, **Then** não há baseline órfã e nenhum
   placeholder fabricado ocupou o lugar de uma captura.

### Edge Cases

- **Credencial já gravada para um vendor removido.** O deployment em produção
  pode ter credencial no vault de um vendor que sai. O catálogo não a lista e o
  boot não trava por causa dela; a credencial órfã é ignorada. Esta feature não
  faz migração nem limpeza de vault — a decisão é registrada e a limpeza fica
  fora de escopo.
- **Categoria de documentação que esvazia.** Três categorias perdem todos os
  seus vendors (integração contínua, plataforma de dados e ticketing). A
  documentação gerada não pode ficar com página de categoria vazia nem com
  entrada de índice apontando para nada.
- **Vendor removido cujo nome também é um destino de notificação.** Slack,
  Microsoft Teams, Discord e PagerDuty existem como destinos de notificação, em
  namespace próprio, e como superfícies de chat. Isso é outro componente: o
  corte remove o pacote de integração e **não** remove o destino nem a
  superfície de chat.
- **A isenção de provedor de modelo na suíte de paridade.** `google_gemini` é a
  única integração de categoria provedor de modelo e é isenta da regra de
  paginação porque seu cliente é uma checagem de alcance. Ela fica entre as 15,
  então a isenção continua carregando peso e continua se auto-policiando — o
  corte não pode fazê-la desaparecer por acidente nem alargá-la.
- **A lista de vendors não cobertos.** As 70 removidas **não** entram nessa
  lista. Ela responde "nunca foi construído, e por quê"; a intenção das
  removidas vive no roadmap committed. Sem isso, a página de referência da 050
  vira um despejo de 79 itens.
- **Uma integração mantida que perde um artefato no meio do corte.** Se a
  remoção derrubar por engano um artefato de uma das 15 — uma skill, um cenário
  —, a paridade reprova nomeando a integração e o artefato. É o comportamento
  desejado e o gate não é afrouxado para deixar o corte passar.
- **Dependência de SDK de vendor removido.** Uma dependência opcional que só
  existia para um pacote removido não pode continuar declarada.

## Requirements *(mandatory)*

### As 15 mantidas

`proxmox`, `prometheus`, `alertmanager`, `grafana`, `loki`, `openobserve`,
`signoz`, `redis`, `kubernetes`, `argocd`, `google_gemini`, `pushover`,
`hermes`, `github`, `telegram`.

### As 70 removidas

Derivadas do conteúdo de `integrations/` menos as 15 acima e menos os não-vendor
(`_base`, `_catalogue`, `_verification`, `registry.py`, `__init__.py`,
`AGENTS.md`, `__pycache__`). A árvore tem 85 pacotes de vendor; removem-se
exatamente estes 70:

`airflow`, `amplitude`, `aws`, `aws_cloudtrail`, `aws_ec2`,
`aws_ecs`, `aws_eks`, `aws_elb`, `aws_lambda`, `aws_rds`, `aws_s3`, `azure`,
`azure_monitor`, `azure_sql`, `better_stack`, `bigquery`, `bitbucket`,
`blameless`, `clickhouse`, `clickup`, `confluence`, `coralogix`, `dagster`,
`datadog`, `discord`, `docker`, `elasticsearch`, `firehydrant`, `flagd`, `flink`, `gcp`,
`gitlab`, `google_docs`, `groundcover`, `honeycomb`, `incident_io`, `jaeger`,
`jenkins`, `jira`, `kafka`, `linear`, `microsoft_teams`, `mongodb_atlas`,
`new_relic`, `notion`, `opensearch`, `opsgenie`, `pagerduty`, `posthog`,
`prefect`, `proxmox_backup_server`, `rabbitmq`, `railway`, `rocket_chat`,
`sentry`, `servicenow`, `slack`, `snowflake`, `sourcegraph`, `spark`, `splunk`,
`supabase`, `tempo`, `temporal`, `trello`, `twilio`, `vercel`, `victorialogs`,
`victoriametrics`, `whatsapp`.

### Functional Requirements

#### Remoção dos pacotes

- **FR-001**: O catálogo servido DEVE conter exatamente as 15 integrações
  nomeadas acima.
- **FR-002**: Os 70 pacotes de vendor nomeados acima DEVEM sair da árvore, com
  todo o seu conteúdo.
- **FR-003**: A skill de metodologia de cada vendor removido DEVE sair junto do
  pacote.
- **FR-004**: O cenário sintético de cada vendor removido DEVE sair junto do
  pacote.
- **FR-005**: A documentação por integração de cada vendor removido DEVE sair
  junto do pacote.
- **FR-006**: As fixtures que existiam apenas para exercitar um vendor removido
  DEVEM sair junto do pacote.
- **FR-007**: Nenhuma dependência opcional declarada que exista somente para um
  vendor removido DEVE permanecer declarada.
- **FR-008**: Nenhum arquivo committed DEVE citar um vendor removido, exceto o
  roadmap committed e o registro de decisão novo.
- **FR-009**: A remoção NÃO DEVE tocar o destino de notificação homônimo de um
  vendor removido, que é outro componente.
- **FR-010**: A remoção NÃO DEVE tocar a superfície de chat homônima de um
  vendor removido, que é outro componente.
- **FR-011**: As 15 mantidas DEVEM permanecer em paridade completa nos sete
  artefatos, cada uma.

#### Intake de alertas

- **FR-012**: As fontes de intake DEVEM se reduzir a `alertmanager`, `grafana` e
  `generic`.
- **FR-013**: A enumeração de fontes de alerta do domínio NÃO DEVE declarar
  Datadog, Opsgenie, PagerDuty nem Sentry.
- **FR-014**: Os endereços de intake das quatro fontes removidas DEVEM deixar de
  existir.
- **FR-015**: Um pedido a um endereço de intake removido DEVE ser respondido
  como endereço inexistente, e não como falha de autenticação nem de servidor.
- **FR-016**: O comportamento das três fontes mantidas NÃO DEVE mudar com este
  corte.
- **FR-017**: As fixtures de intake que descrevem fontes removidas DEVEM ser
  ajustadas para as três mantidas.

#### Gates, contagens e documentação

- **FR-018**: A suíte de paridade de integrações DEVE iterar o catálogo real e
  passar com 15.
- **FR-019**: A verificação de integrações DEVE reportar 15 integrações em
  paridade total.
- **FR-020**: A checagem de documentação gerada de integrações DEVE passar sem
  acusar desvio, depois de a documentação ser regenerada.
- **FR-021**: A documentação gerada NÃO DEVE conter página de categoria sem
  nenhum vendor.
- **FR-022**: O índice da documentação gerada NÃO DEVE apontar para página de
  categoria removida.
- **FR-023**: Toda afirmação de total de integrações em arquivo committed DEVE
  passar a dizer 15 ou passar a ser derivada do catálogo.
- **FR-024**: A isenção de paginação da categoria provedor de modelo DEVE
  permanecer intacta e continuar se auto-policiando.
- **FR-025**: A lista de vendors não cobertos NÃO DEVE receber os 70 removidos.
- **FR-026**: A verificação completa do repositório DEVE ficar verde ao final,
  tendo partido de verde.

#### Registro de decisão e constituição

- **FR-027**: Um registro de decisão arquitetural novo DEVE declarar a paridade
  por integração embarcada.
- **FR-028**: Esse registro DEVE declarar a amplitude como estagiada por
  ambiente validável.
- **FR-029**: Esse registro DEVE apontar a seção de escopo de integrações do
  roadmap committed como o lugar onde a amplitude corrente é lida.
- **FR-030**: Esse registro NÃO DEVE afirmar um total de integrações.
- **FR-031**: O registro de decisão anterior sobre paridade DEVE passar a
  constar como superseded, com data e ponteiro para o sucessor.
- **FR-032**: O índice de registros de decisão DEVE refletir o novo registro e o
  novo estado do anterior.
- **FR-033**: A cláusula de paridade do artigo de capacidades da constituição
  DEVE passar a falar de integração embarcada.
- **FR-034**: Essa cláusula NÃO DEVE citar um total de integrações.
- **FR-035**: A versão da constituição DEVE subir com sumário de emenda,
  conforme a regra de versionamento do próprio documento.

#### Console sem órfãos

- **FR-036**: Nenhuma rota do console DEVE apontar para vendor removido.
- **FR-037**: Nenhuma fixture do console DEVE nomear vendor removido.
- **FR-038**: Nenhum registro de tela visual DEVE apontar para rota de vendor
  removido.
- **FR-039**: Um baseline visual cuja tela morre com o corte DEVE ser removido
  deliberadamente, e não substituído por captura fabricada.
- **FR-040**: As suítes de console existentes DEVEM continuar passando.

#### Consistência do roadmap

- **FR-041**: A lista de escopo embarcado do roadmap committed DEVE nomear
  exatamente as 15 mantidas.
- **FR-042**: A lista de escopo diferido do roadmap committed DEVE cobrir os 70
  removidos.
- **FR-043**: O roadmap committed NÃO DEVE ser reescrito por esta feature além
  do necessário para satisfazer as duas checagens acima.

### Key Entities

- **Integração embarcada**: um vendor presente no catálogo, com os sete
  artefatos completos e um ambiente que consegue validá-lo — credencial
  armazenada, conexão verificada e ao menos uma leitura real exercitada.
- **Integração diferida**: um vendor cuja intenção fica registrada no roadmap e
  cujo código sai da árvore. Volta pela mesma porta por onde saiu: um ambiente
  que o valide, mais o seu cenário sintético.
- **Fonte de intake**: a origem declarada de um alerta que chega ao produto,
  reduzida a `alertmanager`, `grafana` e `generic`.
- **Vendor não coberto**: um sistema que o catálogo nunca cobriu, com causa,
  razão e o que mudaria a decisão. Conjunto disjunto das integrações diferidas.

## Success Criteria *(mandatory)*

- **SC-001**: O catálogo servido responde com exatamente 15 integrações, e os 15
  nomes são os desta spec.
- **SC-002**: A verificação de integrações reporta 15 em paridade total e
  nenhuma incompleta.
- **SC-003**: A árvore perde exatamente 70 pacotes de vendor, 70 skills de
  metodologia e 70 cenários sintéticos.
- **SC-004**: Uma varredura por qualquer um dos 70 nomes removidos em arquivo
  committed retorna ocorrências apenas no roadmap committed e no registro de
  decisão novo.
- **SC-005**: Os endereços de intake das quatro fontes removidas respondem como
  inexistentes; os das três mantidas respondem exatamente o que respondiam antes
  do corte.
- **SC-006**: A verificação completa do repositório passa integralmente, e o
  resultado é comparado contra a mesma verificação rodada antes do corte.
- **SC-007**: As suítes de console — unitária, de comportamento, de primeiro dia
  e visual — passam sem baseline órfã e sem placeholder fabricado.
- **SC-008**: A constituição e o registro de decisão novo descrevem a mesma
  regra que o gate enforça, e nenhum dos dois cita um total de integrações.

## Assumptions

- **O corte é de pacotes de integração, não de funcionalidade homônima.**
  Destinos de notificação e superfícies de chat que compartilham nome com um
  vendor removido são componentes distintos e permanecem. Sem essa fronteira, o
  corte derrubaria capacidades que o operador usa.
- **`kubernetes` e `argocd` entram sem validação de rede imediata.** Ambos
  vivem no cluster k3s do estate (Argo CD via GitOps de produção); são mantidos
  por decisão do operador, e esta spec não os condiciona a uma prova de alcance
  nem os trata como caso especial. `docker` foi removido pela mesma decisão:
  ferramenta local, não um alvo de troubleshoot remoto.
- **A cobertura "cada integração com cenário" passa a valer sobre 15.** A regra
  não muda de forma, só de conjunto.
- **A lista de vendors não cobertos mantém o significado que já tem.** Ela
  responde por sistemas nunca construídos. As integrações diferidas são um
  conjunto à parte, no roadmap.
- **Esta feature não faz migração de dados.** Credencial gravada para vendor
  removido fica órfã no vault, sem quebrar o boot, e sua limpeza é trabalho
  posterior.
- **A constituição é local-only.** A emenda existe no disco desta máquina e não
  é embarcada no repositório; o registro de decisão novo, sim, é committed e é
  onde a regra fica legível para quem clonar.

## Dependencies

- Nenhuma feature anterior. Esta é a raiz da onda.
- A seção de escopo de integrações do roadmap committed já existe; esta feature
  a valida, não a escreve.
- Bloqueia a 010 (o provedor de modelo mantido é o alvo do fluxo), a 050 (a tela
  do catálogo assume 15 e a tela de Alert intake assume três fontes) e a 060 (o
  primeiro incidente entra pela fonte `alertmanager`).

## Out of Scope

- Qualquer tela. O catálogo em grid, o slide-over de detalhe e a tela de Alert
  intake são da 050.
- A lista dinâmica de modelos do provedor e a verificação com tool-calling
  forçado, que são da 010.
- A limpeza de credenciais órfãs no vault.
- A criação das integrações que o roadmap marca como desejadas e não
  construídas.
- Qualquer alargamento da isenção de paginação para outras categorias.
