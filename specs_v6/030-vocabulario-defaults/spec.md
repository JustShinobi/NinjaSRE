# Feature Specification: Vocabulário sem cru e defaults seguros de token

**Feature Branch**: `feat/v6-030-vocabulario-defaults`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "A regra da v5 — display name obrigatório, id cru só em contexto técnico — aplicada de verdade em todo o produto, mais defaults seguros onde hoje são perigosos: um token de máquina novo nasce com 27 de 27 escopos marcados, incluindo Org Delete, Owner Assign e Impersonation Use. Members & roles ganha a ação primária que nunca teve."

**Referência visual (DoD)**: [../mockups/settings-v6.html#m2](../mockups/settings-v6.html#m2) (grupos `policies.*` deixam de ser título de seção; o nome técnico do campo aparece só no audit e na API) e [#m3](../mockups/settings-v6.html#m3) (o trust deixa de ser `webhook.deliver` e vira "delivery token `am-cluster`", nomeado e com rotação na própria tela). As telas Members & roles e Machine tokens não têm mockup próprio na v6: para elas as normas são as regras transversais da v5 (`specs_v5/mockups/settings-v5.html`, Parte 3) e o mockup-1 da v5, que continuam normativas por referência.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Um token de máquina nasce sem poder nenhum (Priority: P1)

Um administrador emite um token para uma finalidade — entregar alertas, ler
métricas — e o token sai da tela carregando só o que essa finalidade exige.
Nada mais é concedido por inércia.

**Why this priority**: É o único defeito desta feature que produz dano real e
silencioso. Hoje o formulário abre com os 27 escopos do visualizador marcados;
um administrador que digita um nome e clica em "Issue" emite uma credencial com
`Org Delete`, `Owner Assign` e `Impersonation Use` — poder para apagar a
organização e para agir como qualquer pessoa — para um trabalho que precisava de
um escopo. A credencial some da tela depois de exibida uma vez e continua
existindo.

**Independent Test**: Abrir Machine tokens com um visualizador `owner`, conferir
que nenhum escopo está marcado, escolher o template "Alert delivery", emitir, e
verificar que o token emitido carrega `webhook.deliver` e nada além disso.

**Acceptance Scenarios**:

1. **Given** o formulário de emissão de Machine tokens aberto por um `owner`,
   **When** ele abre, **Then** nenhuma das caixas de escopo está marcada, e o
   contador de escopos selecionados diz zero.
2. **Given** o formulário virgem, **When** o administrador escolhe o template
   "Alert delivery", **Then** exatamente `webhook.deliver` fica marcado, e o
   template diz em uma frase para que serve.
3. **Given** o formulário, **When** o administrador marca um escopo destrutivo
   (`Org Delete`, `Owner Assign`, `Impersonation Use`), **Then** um aviso nomeia
   o que aquele escopo permite antes da emissão, e a emissão segue possível.
4. **Given** uma emissão sem escopo explícito nenhum, **When** ela chega ao
   deployment, **Then** o token emitido não carrega escopo nenhum — a ausência
   de escolha nunca é lida como "tudo".
5. **Given** os escopos exibidos, **When** o formulário abre, **Then** eles
   aparecem agrupados por domínio (organização, identidade, investigação,
   configuração, entrega) e não como uma faixa única de 27 caixas.

---

### User Story 2 - O produto fala uma língua só (Priority: P1)

Um operador percorre as nove páginas de Settings, o catálogo de integrações e o
wizard de primeiro uso sem encontrar um identificador de máquina apresentado
como se fosse texto para gente.

**Why this priority**: A regra é da v5 e foi declarada entregue; o diagnóstico a
encontrou violada em pelo menos sete lugares. Cada violação obriga o operador a
traduzir o produto na cabeça, e algumas mentem — "healthy" descrevendo uma
pessoa, um número de linha de token apresentado como se fosse a sessão. É P1
junto com US1 porque a suíte transversal só perde as exceções de vocabulário
quando esta história inteira estiver de pé.

**Independent Test**: Rodar a suíte transversal da 020 com os `fixme` de
vocabulário removidos, contra as rotas de Settings, `/integrations` e
`/first-run`, e ver verde.

**Acceptance Scenarios**:

1. **Given** Members & roles, **When** a lista de pessoas renderiza, **Then**
   nenhuma chip diz `SERVICE_ACCOUNT` nem `HEALTHY`; uma conta de serviço se
   apresenta como "Service account" e uma conta em uso como "Active".
2. **Given** Machine tokens, **When** um grupo de tokens renderiza, **Then** o
   chip do grupo descreve o token e não a saúde de um recurso — "In use" ou
   "Never used", conforme o último uso registrado.
3. **Given** Autonomy & guardrails e Notifications, **When** as seções técnicas
   renderizam, **Then** nenhum título de seção é um caminho de schema
   (`policies.masking`, `surfaces.notification_policy`); o caminho continua
   legível no audit e na API.
4. **Given** o wizard de primeiro uso, **When** o preview de resolução mostra o
   que será gravado, **Then** o campo aparece pelo nome de exibição e não como
   `models.investigator.model`.
5. **Given** Alert intake, **When** a fonte mostra por que confia em quem
   entrega, **Then** ela nomeia o delivery token e oferece a rotação, em vez de
   dizer "Trusted by webhook.deliver".
6. **Given** o catálogo de integrações com sugestões vindas do estate, **When**
   uma sugestão renderiza, **Then** ela nomeia o recurso de forma legível
   ("grafana, CT 133"); o identificador `res-…` fica no destino do link.
7. **Given** Members & roles com sessões ativas, **When** elas renderizam,
   **Then** cada sessão se identifica por quem e de onde, não por um número
   solto como "59".
8. **Given** o formulário de grant, **When** um papel é escolhido, **Then** o
   que ele permite aparece como resumo humano, com o detalhe das permissões
   disponível ao expandir — não como uma linha de ids separados por vírgula.

---

### User Story 3 - Criar uma pessoa sem sair da tela de pessoas (Priority: P2)

Um administrador de um deployment local cria uma conta para um colega
diretamente em Members & roles, define a senha inicial e concede o papel — sem
editar variáveis de ambiente nem reiniciar o serviço.

**Why this priority**: A tela chama-se Members & roles e não tem ação primária
nenhuma; ela lista pessoas que alguém criou por outro caminho. Depende do que o
deployment já sabe fazer, por isso vem depois das duas P1: se o gateway não
tiver a operação, esta história cria a rota, e isso é trabalho de servidor com
teste de contrato e de segurança próprios.

**Independent Test**: A partir de Members & roles, criar uma pessoa com senha
local, conceder-lhe um papel, entrar com essa conta e ver que ela alcança
exatamente o que o papel permite.

**Acceptance Scenarios**:

1. **Given** Members & roles aberta por quem tem permissão de escrita em
   identidade, **When** ela abre, **Then** existe uma ação primária de criar
   pessoa, nomeada pelo que faz.
2. **Given** a ação de criar pessoa, **When** o administrador a completa,
   **Then** a pessoa aparece na lista com o mesmo vocabulário de chips das
   demais, e a criação fica registrada no audit.
3. **Given** um visualizador sem permissão de escrita em identidade, **When** a
   tela abre, **Then** a ação não é oferecida — a tela não convida para o que
   vai recusar.

### Edge Cases

- **Escopo que o visualizador não possui**: o teto continua sendo o que quem
  emite já carrega. Um template de finalidade que peça um escopo fora desse teto
  é oferecido desabilitado, dizendo por quê, em vez de emitir um token menor do
  que o rótulo promete.
- **Emissão pela API sem campo de escopos**: um cliente que omite o campo recebe
  um token sem escopos, não um token com tudo. O comportamento é o mesmo do
  formulário e é dele que sai o teste de contrato.
- **Recurso do estate sem nome resolvível**: a sugestão mostra o que conseguiu
  resolver (endereço, tipo) e o identificador só no destino do link — nunca um
  rótulo vazio.
- **Sessão sem dispositivo ou origem conhecidos**: identifica-se por quem é dona
  e desde quando; o número técnico da sessão fica em contexto técnico.
- **Papel com dezenas de permissões**: o resumo humano não vira uma lista longa
  disfarçada; ele diz o que o papel permite em uma frase, e a lista completa
  mora atrás da expansão.
- **Estado que o console nunca ouviu**: uma chip continua exibindo o que o
  deployment respondeu, em vez de apagar o dado — mas sem transformar um valor
  de máquina em rótulo gritado.
- **Locale sem a chave nova**: nenhuma string desta feature entra em uma língua
  só; en e pt-BR nascem juntos.

## Requirements *(mandatory)*

### Functional Requirements

#### Vocabulário: cada vazamento, com a tela e a string

- **FR-001**: O chip de tipo de principal em `/settings/members-roles` NÃO DEVE
  exibir o valor de transporte `service_account` (renderizado hoje em caixa alta
  como `SERVICE_ACCOUNT`). Uma conta de serviço DEVE ser apresentada como
  "Service account" / "Conta de serviço"; uma pessoa, como "Person" / "Pessoa".
- **FR-002**: O chip de estado de pessoa em `/settings/members-roles` NÃO DEVE
  exibir `HEALTHY` nem `DISABLED`. O estado de uma conta DEVE usar vocabulário
  de conta — "Active" / "Ativa" e "Suspended" / "Suspensa". Saúde é vocabulário
  de recurso e não se aplica a gente.
- **FR-003**: O chip do grupo de tokens em `/settings/machine-tokens` NÃO DEVE
  exibir `HEALTHY`. Um grupo DEVE declarar o estado que o domínio tem: "In use"
  / "Em uso" quando há último uso registrado, "Never used" / "Nunca usado"
  quando não há.
- **FR-004**: O preview de resolução do wizard de primeiro uso (`/first-run`)
  NÃO DEVE exibir `models.investigator.model` nem `models.investigator.provider`
  como rótulo de campo. O preview DEVE nomear o campo pelo nome de exibição
  ("Investigation model" / "Modelo de investigação").
- **FR-005**: As seções de configuração técnica de `/settings/autonomy-guardrails`
  NÃO DEVEM usar caminhos de schema como título — `policies.masking`,
  `policies.guardrails`, `policies.approvals`, `policies.autonomy`. Cada seção
  DEVE ter um título humano, conforme [#m2](../mockups/settings-v6.html#m2).
- **FR-006**: A seção de configuração técnica de `/settings/notifications` NÃO
  DEVE usar `surfaces.notification_policy` como título, e DEVE ter um título
  humano pela mesma regra do FR-005.
- **FR-007**: `/settings/alert-intake` NÃO DEVE exibir "Trusted by
  webhook.deliver". A fonte DEVE nomear o delivery token que autentica a entrega
  e oferecer a rotação ali mesmo — "Authenticated with delivery token
  `<nome>` · rotate", conforme [#m3](../mockups/settings-v6.html#m3).
- **FR-008**: As sugestões vindas do estate em `/integrations` NÃO DEVEM exibir o
  identificador cru do recurso (`res-8f81848…`) no texto da evidência. A
  evidência DEVE nomear o recurso de forma legível — nome do serviço e
  localização, no padrão "grafana, CT 133" — e o identificador DEVE ficar no
  destino do link.
- **FR-009**: As sessões ativas em `/settings/members-roles` NÃO DEVEM ser
  identificadas por um número solto (hoje "59"). Cada sessão DEVE se identificar
  por quem é dona e por origem/dispositivo quando o deployment souber; o
  identificador técnico da sessão fica em contexto técnico (atributo, tooltip
  ou audit).
- **FR-010**: A ajuda do formulário de grant em `/settings/members-roles` NÃO
  DEVE ser a lista crua de permissões do papel (`approval.read, config.read, …`).
  O papel escolhido DEVE ser descrito por um resumo humano, com a lista completa
  disponível ao expandir.
- **FR-011**: Todo identificador que sair da face principal de uma tela por força
  dos FR-001 a FR-010 DEVE continuar recuperável em contexto técnico — audit,
  resposta da API, atributo de dado da própria marcação — para que a tela deixe
  de gritar o identificador sem que o operador perca a capacidade de casá-lo com
  o que a máquina responde.

#### Defaults seguros de machine token

- **FR-012**: O formulário de emissão em `/settings/machine-tokens` DEVE abrir
  com nenhum escopo marcado. O default atual — todos os escopos que o
  visualizador possui, 27 de 27 para um `owner`, incluindo `Org Delete`,
  `Owner Assign` e `Impersonation Use` — deixa de existir.
- **FR-013**: O formulário DEVE oferecer templates de finalidade que marcam o
  conjunto mínimo de escopos daquele uso. "Alert delivery" marca `webhook.deliver`
  e nada mais; "Read-only automation" marca apenas escopos de leitura. Cada
  template DEVE dizer em uma frase para que serve, e escolher um template nunca
  impede o ajuste manual depois.
- **FR-014**: Os escopos DEVEM ser exibidos agrupados por domínio, com o nome de
  cada grupo legível, em vez de uma faixa única de caixas.
- **FR-015**: Selecionar um escopo destrutivo DEVE produzir um aviso que nomeia
  o que aquele escopo permite, no momento da seleção e antes da emissão. O aviso
  informa e não bloqueia: quem precisa emitir, emite.
- **FR-016**: O deployment DEVE emitir um token com exatamente os escopos
  pedidos. Uma emissão que não declare escopos DEVE produzir um token sem escopo
  nenhum — a ausência de declaração nunca é lida como concessão total, e essa
  garantia é do servidor, não da tela.
- **FR-017**: O teto existente DEVE ser preservado: nenhum token nasce com
  escopo que quem o emitiu não possui. Um template cujo conjunto ultrapasse esse
  teto DEVE ser oferecido desabilitado, com a razão dita.

#### Members & roles com ação primária

- **FR-018**: `/settings/members-roles` DEVE oferecer a ação primária de criar
  uma pessoa no deployment — o fluxo local, com senha inicial — a quem tem
  permissão de escrita em identidade, e não oferecê-la a quem não tem. A criação
  DEVE ficar registrada no audit e a pessoa criada DEVE aparecer na lista com o
  vocabulário dos FR-001 e FR-002.
- **FR-019**: Cada grant listado DEVE nomear o papel de forma legível, pelo mesmo
  vocabulário do seletor que o concede.

#### Língua e prova

- **FR-020**: Toda string introduzida ou alterada por esta feature DEVE existir
  em inglês e em português do Brasil, no mesmo passo. O catálogo pt-BR usa o
  vocabulário brasileiro — tela, arquivo, ação, salvar, excluir, ativar.
- **FR-021**: As exceções de vocabulário anotadas na suíte transversal — os
  `fixme` por rota que a 020 introduziu para as rotas que ainda violavam —
  DEVEM ser removidas por esta feature nas rotas que ela cobre, e a suíte DEVE
  passar sem elas.

### Key Entities

- **Principal**: pessoa ou conta de serviço; tipo e estado, ambos apresentados
  por nome de exibição.
- **Grupo de escopos**: um domínio (organização, identidade, investigação,
  configuração, entrega) e os escopos que ele reúne, com o nome legível de cada
  um e a marca de destrutivo.
- **Template de finalidade**: um nome, uma frase de propósito, e o conjunto
  mínimo de escopos que ele marca.
- **Sugestão do estate**: a integração sugerida, o recurso que a motivou (nome
  legível e localização) e o identificador desse recurso, usado como destino.
- **Sessão**: a quem pertence, de onde veio, quando expira; o identificador
  técnico fica em contexto técnico.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Nas nove páginas de Settings, em `/integrations` e no wizard de
  primeiro uso, nenhum texto visível contém um identificador de máquina
  apresentado como rótulo — verificado pela suíte transversal rodando sem
  nenhuma exceção de vocabulário.
- **SC-002**: Um token emitido pelo formulário sem escolha explícita de escopos
  carrega zero escopos; a emissão que hoje produz 27 de 27 não é reproduzível.
- **SC-003**: Nenhum token nasce com `Org Delete`, `Owner Assign` ou
  `Impersonation Use` sem que quem o emitiu tenha marcado aquele escopo e visto
  o aviso.
- **SC-004**: Emitir um token de entrega de alerta leva três gestos — escolher o
  template, nomear, emitir — e o token resultante carrega exatamente um escopo.
- **SC-005**: Um administrador cria uma pessoa a partir de Members & roles sem
  documentação externa e sem tocar em variáveis de ambiente ou reiniciar o
  serviço.
- **SC-006**: Toda chave de mensagem introduzida por esta feature existe nos dois
  catálogos; nenhuma língua fica para trás.
- **SC-007**: Members & roles e Machine tokens continuam dentro de 2 viewports em
  1080p com dados representativos, depois do agrupamento de escopos e da ação
  primária nova.

## Assumptions

- O modelo de papéis e permissões não muda. Muda o que a tela mostra, o que o
  formulário marca por padrão e o que o servidor concede quando nada é pedido.
- Os escopos destrutivos são os que já existem como permissões do produto; esta
  feature os marca como destrutivos para efeito de aviso, sem criar categoria
  nova de permissão.
- O agrupamento de escopos por domínio deriva do próprio nome do escopo, sem
  catálogo paralelo a manter.
- A criação de pessoa usa o mecanismo de conta local que o deployment já tem. Se
  o gateway ainda não expuser essa operação, ela é criada nesta feature — o
  tasks.md abre com a tarefa de descoberta que decide isso antes de qualquer
  desenho de rota.
- A resolução do nome legível de um recurso do estate usa os dados que o
  deployment já responde sobre aquele recurso; nada novo é coletado.

## Dependencies

- **020** — a suíte transversal (`console/tests/e2e/transversal-rules.spec.ts`)
  nasce lá, com os bans de vocabulário e o mecanismo de exceção por rota. Esta
  feature é a primeira a remover exceções dessa suíte (FR-021).
- **010** — o vocabulário de erro do provider (`google_gemini` em texto de erro,
  também listado no diagnóstico como P2-7) pertence ao fluxo do provider e não
  entra aqui.
- **040** — o rework estrutural de Autonomy & guardrails (três abas, ≤1.5
  viewport, fim do schema-browser como face principal) é dela. Aqui morre só o
  vocabulário: os títulos de seção deixam de ser caminhos de schema (FR-005),
  a estrutura da página continua a que estiver lá.
- **001** — o corte do catálogo muda quais sugestões do estate existem; o FR-008
  vale para as sugestões que sobreviverem ao corte.

## Fora de escopo

- Reorganizar Autonomy & guardrails ou Notifications além dos títulos (é da 040).
- Mudar o modelo de permissões, criar escopos novos ou alterar o teto de emissão.
- Aposentar o slide-over de integrações ou mexer no catálogo (001 e 050).
- Corrigir a copy do provider e o estado de verificação (010).
