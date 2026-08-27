# Feature Specification: Identidade endereçável — o que a interface chama pelo nome, a rota atende pelo nome

**Feature Branch**: `feat/v7-020-identidade-enderecavel`

**Created**: 2026-08-23

**Status**: Draft

**Input**: User description: "O detalhe de todo incidente ingerido por alerta
está irrecuperável. Id de incidente opaco e curto nas URLs, decode único na
borda (fim da dupla codificação), título do incidente = `incident.title`,
redirects `/investigations`→`/runs` e `/setup`→`/first-run`, e nenhum id
composto cheio de `:`/`@`/`+` de volta numa URL ou num título."

**Referência visual (DoD)**: nenhum mockup. Esta é uma feature de **rework** de
telas que já existem — detalhe de incidente, lista de incidentes, busca — e a
onda decidiu que rework de console traz **alegações normativas** no lugar de
mockup. A seção "Alegações normativas" abaixo é a referência de DoD, e
`console/tests/e2e/identidade-enderecavel.acceptance.spec.ts` a codifica,
confirmado **vermelho antes de qualquer implementação**.

**Viewport normativo de medição**: 1920×1080.

**Evidência**: diagnóstico da onda §2, defeito P0-2 ("o detalhe de todo
incidente ingerido por alerta está irrecuperável") e defeito P1-7 ("rotas
fantasmas e nomes que não se encontram"); tabela §1, linhas `/incidents/{id}`,
`/investigations`, `/setup`.

---

## Fatos verificados em 2026-08-23 (não re-derivar)

Cada item foi confirmado no banco de staging, na tela em Full HD, ou cravado em
código. A spec os trata como fatos.

1. **O id de incidente no banco é composto e cheio de reservados.** Literal:
   `alert:alertmanager:<sha256>@2026-08-22T23:43:23.303208+00:00`.
2. **Como ele nasce**: `incident_key(correlation_key, opened_at)`
   (`platform/persistence/ports/incident_store.py:306`) devolve
   `correlation_key + "@" + opened_at.isoformat()`, encurtado por `_bounded`
   (`:287`) quando passa da largura da coluna. O `correlation_key` de um alerta
   é `alert:<source>:<fingerprint>`, montado por `correlation.for_alert` e
   chamado de `platform/incidents/ingestion.py:87`. O único construtor é
   `IncidentLifecycle.raise_incident` (`platform/incidents/lifecycle.py:102`).
3. **A rota do gateway responde para as duas grafias.** Sondada de dentro do
   pod: `GET /v1/incidents/<id cru>` e `GET /v1/incidents/<id encodado>`
   respondem **400 por falta de bearer token** — ou seja, o roteamento está
   correto e o problema não é do gateway. O que falha é a leitura do console:
   durante os loads da página nenhuma linha entra no access log do `app`.
4. **O Next entrega `params.incidentId` ainda percent-encoded.** A página usa o
   valor cru como título e como parâmetro
   (`console/src/app/(shell)/incidents/[incidentId]/page.tsx`).
5. **`bind()` re-encoda.** `console/src/lib/api.ts:66-76` aplica
   `encodeURIComponent` sobre um valor que já vinha encodado — dupla
   codificação; o id que chegaria ao gateway não é o do banco.
6. **A lista de incidentes gera href sem encodar**:
   `console/src/surfaces/screens/incidents.tsx:168` e
   `console/src/surfaces/screens/dashboard.tsx:169,208` fazem
   `` href={`/incidents/${id}`} `` com o id cru; a busca
   (`console/src/shell/search.ts:136`) encoda; `run-detail.tsx:472` não. Três
   grafias para o mesmo endereço.
7. **O título cai no id.** `incident-detail.tsx:166` faz
   `text(incident,'title') || incidentId`, e a aba usa
   `documentTitle(incidentId, ...)` — quando a leitura falha, o H1 e a aba
   imprimem o id percent-encoded.
8. **A lista já tem o título legível.** `IncidentSummaryView.title`
   (`gateway/http/routes/incidents.py:68`) chega preenchido: "RestoreDrillStale".
9. **Os painéis que quebram** são os servidos por `/v1/incidents/{incident_id}`
   — "Investigation" e "Evidence trail" — porque `panelRead`
   (`console/src/surfaces/read.ts:44`) transforma a recusa em
   `{status:'error'}` e o `Panel` desenha "This panel could not be filled".
10. **`/investigations` e `/setup` respondem "There is no such page"** — o
    catch-all `console/src/app/(shell)/[...unmatched]/page.tsx` chama
    `notFound()`. O padrão de redirect já existe:
    `legacyRedirectHref` (`console/src/shell/legacy-redirect.ts:14`) sobre
    `SETTINGS_REDIRECTS` (`console/src/shell/routes.ts:698`), usado por
    `signals/page.tsx` e `administration/page.tsx`.
11. **A tabela de incidentes é `incidents`, com chave `(org_id, incident_id)`**
    (`platform/persistence/postgres/repositories/incident_store.py:53-66`); a
    última revisão de migração é `0014_timeline_evidence`.
12. **O registro de telas visuais já resolve o id do detalhe da captura**:
    `console/visual/screens.json` usa `{{detailed-incident-id}}` e
    `console/tests/visual/screens.spec.ts` o resolve do próprio dataset.

---

## Alegações normativas

Frases curtas, individualmente testáveis. Uma vírgula é fronteira de requisito.
O acceptance spec desta feature codifica cada uma; as marcadas **[staging]**
são staging-safe (leitura pura, nenhuma escrita) e também rodam contra
`https://stg-ninjasre.lan.kyo.ninja`.

- **AN-01** Abrir um incidente de alerta real a partir da lista mostra o título
  do incidente como H1. **[staging]**
- **AN-02** O H1 do detalhe de incidente nunca é um identificador. **[staging]**
- **AN-03** O título da aba do detalhe de incidente nunca é um identificador.
  **[staging]**
- **AN-04** Nenhuma URL que o console gera para um incidente contém `%3A`,
  `%40` ou `%2B`. **[staging]**
- **AN-05** Nenhuma URL que o console gera para um incidente contém `:`, `@` ou
  `+` literais. **[staging]**
- **AN-06** O painel "Investigation" do detalhe de um incidente real não está
  em estado de falha de dependência. **[staging]**
- **AN-07** O painel "Evidence trail" do detalhe de um incidente real não está
  em estado de falha de dependência. **[staging]**
- **AN-08** A timeline do detalhe renderiza as entradas que o gateway devolve
  para aquele incidente. **[staging]**
- **AN-09** `/investigations` não termina em "There is no such page".
  **[staging]**
- **AN-10** `/setup` não termina em "There is no such page". **[staging]**
- **AN-11** `/investigations` termina em `/runs`. **[staging]**
- **AN-12** `/setup` termina em `/first-run`. **[staging]**
- **AN-13** Um resultado de busca por incidente aponta para o mesmo endereço
  que a linha da lista aponta.
- **AN-14** O link de incidente no detalhe de um run aponta para o mesmo
  endereço que a linha da lista aponta.
- **AN-15** Quando a leitura do incidente falha, a página não afirma o negativo
  sobre a investigação.
- **AN-16** Quando a leitura do incidente falha, o cabeçalho diz que não
  conseguiu ler, e não inventa um nome.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - O detalhe de um incidente de alerta abre (Priority: P1)

Um operador vê `RestoreDrillStale` na lista de incidentes, clica na linha, e
chega numa página que mostra o incidente: o título dele, o estado dele, a
timeline dele. Não uma página com o endereço impresso como nome e dois painéis
dizendo que não conseguiram ser preenchidos.

**Why this priority**: é o defeito P0 desta feature, e ele atinge **todo**
incidente ingerido por alerta — que é todo incidente real deste deployment. Um
produto que recebe alerta e não deixa abrir o incidente correspondente não tem
o laço fechado em lugar nenhum: a lista vira o fim da linha.

**Independent Test**: no staging, abrir `/incidents`, clicar na primeira linha,
e conferir três coisas na página que abre — o H1 é o título do incidente, a
URL não carrega caractere reservado, e nenhum painel está em falha de
dependência de `/v1/incidents/{incident_id}`.

**Acceptance Scenarios**:

1. **Given** um incidente aberto por alerta do Alertmanager, **When** o
   operador clica na linha dele na lista, **Then** a página de detalhe abre com
   o título do incidente como H1.
2. **Given** essa mesma página, **When** o operador olha a barra de endereços,
   **Then** ela não contém `%3A`, `%40`, `%2B`, `:`, `@` nem `+`.
3. **Given** essa mesma página, **When** os painéis renderizam, **Then** nenhum
   deles está no estado de dependência falhada de `/v1/incidents/{incident_id}`.
4. **Given** essa mesma página, **When** o gateway devolveu entradas de
   timeline para aquele incidente, **Then** a página desenha uma entrada por
   entrada devolvida.
5. **Given** essa mesma página, **When** a aba do navegador é lida, **Then** o
   título dela nomeia o incidente e não o identificador dele.

---

### User Story 2 - O endereço de um incidente é curto e legível (Priority: P1)

Um operador copia a URL de um incidente e cola no chat do time. O que ele cola
é curto, não tem escape nenhum, e quem clicar chega no mesmo incidente.

**Why this priority**: a forma pública do id é o que torna o defeito P0
impossível de voltar. Enquanto o endereço carregar `:`, `@` e `+`, cada
superfície nova que gerar um link volta a decidir sozinha se encoda, e duas
delas vão decidir diferente — que é literalmente o estado de hoje, com três
grafias para o mesmo endereço.

**Independent Test**: pedir a lista de incidentes ao gateway, pegar a forma
pública de qualquer incidente, e conferir que ela é composta só de caracteres
que uma URL não precisa escapar, e que pedir o detalhe por ela devolve o mesmo
incidente que pedir pela chave interna.

**Acceptance Scenarios**:

1. **Given** qualquer incidente, **When** o gateway o descreve numa listagem,
   **Then** a descrição carrega uma forma pública do identificador.
2. **Given** essa forma pública, **When** ela é inspecionada, **Then** ela é
   composta apenas de caracteres que não precisam de escape numa URL.
3. **Given** essa forma pública, **When** o detalhe é pedido por ela, **Then**
   o gateway devolve o mesmo incidente que a chave interna devolve.
4. **Given** dois incidentes distintos, **When** as formas públicas dos dois
   são comparadas, **Then** elas são distintas.
5. **Given** um incidente que já existia antes desta mudança, **When** ele é
   lido depois dela, **Then** ele tem forma pública e continua abrível.
6. **Given** uma forma pública que não corresponde a nenhum incidente, **When**
   o detalhe é pedido por ela, **Then** a resposta é uma ausência nomeada, e não
   um erro de servidor.

---

### User Story 3 - Um parâmetro de rota é decodificado uma vez, na borda (Priority: P1)

Qualquer rota dinâmica do console — incidente, run, integração — decodifica o
parâmetro que o roteador entrega exatamente uma vez, num lugar só, e o cliente
de API o encoda exatamente uma vez ao montar o endereço.

**Why this priority**: a forma pública curta resolve o incidente; ela não
resolve o **defeito**. O defeito é a dupla codificação, e ele vale para toda
rota dinâmica: um id de run, um nome de integração com espaço, um id de recurso
`proxmox:node:pve02`. Consertar só o incidente deixaria a armadilha armada para
a próxima rota que alguém adicionar.

**Independent Test**: dar a uma rota dinâmica um parâmetro com caractere
reservado, e conferir que o endereço que o cliente de API monta carrega esse
parâmetro encodado uma vez — nem zero, nem duas.

**Acceptance Scenarios**:

1. **Given** um parâmetro de rota contendo `:`, `@` e `+`, **When** a página o
   entrega ao cliente de API, **Then** o endereço montado contém esse parâmetro
   encodado exatamente uma vez.
2. **Given** um parâmetro de rota contendo `%`, **When** a página o processa,
   **Then** a página não falha e o valor original chega ao cliente de API.
3. **Given** um parâmetro de rota sem nenhum caractere reservado, **When** a
   página o processa, **Then** o valor sai idêntico ao que entrou.
4. **Given** um parâmetro de rota contendo `/` encodado, **When** o endereço é
   montado, **Then** a barra continua encodada e não vira separador de segmento.
5. **Given** cada rota dinâmica do console, **When** ela é lida, **Then** ela
   passa o parâmetro pela mesma decodificação de borda.

---

### User Story 4 - Uma leitura que falhou não vira uma afirmação (Priority: P1)

Quando o console não consegue ler um incidente, a página diz que não conseguiu
ler. Ela não imprime o endereço como se fosse o nome, e não afirma que não
existe investigação.

**Why this priority**: é o que separa "quebrou" de "mentiu". Hoje a página
falha e, no mesmo movimento, contradiz a lista — chip "No investigation" no
detalhe contra chip INVESTIGATING na linha. A honestidade da leitura falhada é
requisito desta feature; o **vocabulário** do estado desconhecido é da feature
de uma-fonte-por-fato.

**Independent Test**: forçar a leitura do detalhe a falhar e conferir que o
cabeçalho não carrega identificador nenhum e que nenhum chip afirma ausência de
investigação.

**Acceptance Scenarios**:

1. **Given** uma leitura de detalhe que falhou, **When** o cabeçalho renderiza,
   **Then** ele não contém o identificador do incidente.
2. **Given** uma leitura de detalhe que falhou, **When** o cabeçalho renderiza,
   **Then** ele diz que o incidente não pôde ser lido.
3. **Given** uma leitura de detalhe que falhou, **When** os chips renderizam,
   **Then** nenhum deles afirma que não há investigação.
4. **Given** uma leitura de detalhe que falhou, **When** a aba é lida, **Then**
   o título dela não contém o identificador do incidente.
5. **Given** uma leitura de detalhe bem-sucedida cujo incidente tem título
   vazio, **When** o cabeçalho renderiza, **Then** ele mostra uma ausência
   declarada e não o identificador.

---

### User Story 5 - As rotas respondem pelos nomes que o produto usa (Priority: P2)

Quem digita `/investigations` — o nome que a barra lateral e a busca usam —
chega em `/runs`. Quem digita `/setup` chega em `/first-run`.

**Why this priority**: é o mesmo princípio da feature, aplicado ao nível da
área em vez do registro: o que a interface chama pelo nome, a rota atende pelo
nome. É P2 porque quem chega ali por navegação nunca vê o 404 — só quem digita,
compartilha um link antigo ou segue a memória do vocabulário do produto.

**Independent Test**: pedir os dois endereços e conferir onde a navegação
termina.

**Acceptance Scenarios**:

1. **Given** um operador autenticado, **When** ele pede `/investigations`,
   **Then** a navegação termina em `/runs`.
2. **Given** um operador autenticado, **When** ele pede `/setup`, **Then** a
   navegação termina em `/first-run`.
3. **Given** um pedido a `/investigations` com parâmetros de consulta, **When**
   o redirect acontece, **Then** os parâmetros chegam ao destino.
4. **Given** qualquer um dos dois endereços, **When** o redirect acontece,
   **Then** a tela de destino é a tela normal do produto, sem aviso de erro.

### Edge Cases

- **Duas formas públicas iguais para incidentes diferentes.** A derivação é uma
  função de digest: uma colisão é aritmeticamente desprezível, e mesmo assim
  não pode virar "o operador abriu o incidente errado". A unicidade é garantida
  pelo armazenamento, e uma colisão falha na escrita em vez de resolver silen-
  ciosamente para a primeira linha encontrada.
- **Incidente do staging aberto antes desta mudança.** Ele já existe no banco
  sem forma pública. A migração precisa dar uma a ele, e ela precisa ser a
  mesma que o código derivaria hoje — senão o mesmo incidente teria dois
  endereços conforme quem o escreveu.
- **A chave interna colada na URL.** Um operador que estava depurando pelo
  banco vai colar `alert:alertmanager:...@...` na barra. A rota do gateway
  continua resolvendo essa grafia; o console continua abrindo a página. O que
  o produto **não** faz é voltar a emitir essa grafia em link nenhum.
- **Parâmetro de rota com `%` solto.** `decodeURIComponent('100%')` lança. A
  borda precisa devolver o valor original nesse caso em vez de derrubar a
  página com um erro de servidor.
- **Incidente sem título.** `IncidentRaise.title` já tem fallback no backend
  (`alert_name or summary or "an alert from <source>"`), então título vazio é
  improvável — mas a página não pode responder a ele caindo no identificador.
- **O detalhe de incidente será tocado de novo, depois desta feature.** Os
  chips derivados de leitura bem-sucedida e o chip "estado desconhecido" são de
  outra feature da onda. Esta mantém o diff em identidade e leitura: título,
  cabeçalho da leitura falhada, e a supressão da afirmação negativa. Ela não
  redefine o vocabulário dos chips nem mexe na sub-linha de meta.
- **O sujeito do incidente não resolve no estate.** A leitura de
  `/v1/estate/resources/{resource_id}` falha hoje porque o estate está vazio
  (integração Proxmox degradada). Isso alimenta a sub-linha de meta, não o
  estado de um painel, e é de outras features da onda. As alegações desta
  feature falam apenas dos painéis cuja dependência é `/v1/incidents/{id}`.
- **O dataset de fixtures e as baselines visuais.** A forma pública nasce nos
  dados; o dataset simulado precisa carregá-la, senão a suíte de console passa
  a exercitar um contrato que o gateway não serve mais.

## Requirements *(mandatory)*

### Identidade pública do incidente

- **FR-001**: Todo incidente DEVE ter uma forma pública do identificador,
  distinta da chave interna.
- **FR-002**: A forma pública DEVE ser composta apenas de caracteres que não
  exigem escape num segmento de URL.
- **FR-003**: A forma pública DEVE ser curta o bastante para caber numa linha
  de tabela sem truncamento.
- **FR-004**: A forma pública DEVE ser derivada de forma determinística da
  chave interna do incidente.
- **FR-005**: A forma pública de dois incidentes distintos DEVE ser distinta.
- **FR-006**: O armazenamento DEVE garantir a unicidade da forma pública dentro
  de uma organização.
- **FR-007**: Uma colisão de forma pública DEVE falhar na escrita, e NÃO DEVE
  resolver para a primeira linha encontrada.
- **FR-008**: A descrição de um incidente numa listagem DEVE carregar a forma
  pública.
- **FR-009**: A descrição de um incidente num detalhe DEVE carregar a forma
  pública.
- **FR-010**: A rota de detalhe de incidente DEVE resolver a forma pública.
- **FR-011**: A rota de detalhe de incidente DEVE continuar resolvendo a chave
  interna.
- **FR-012**: Uma forma pública que não corresponde a incidente nenhum DEVE ser
  respondida como ausência nomeada.

### Codificação única na borda

- **FR-013**: Um parâmetro de rota dinâmica DEVE ser decodificado exatamente
  uma vez, antes de qualquer uso.
- **FR-014**: A decodificação de borda DEVE viver num lugar só, compartilhado
  por todas as rotas dinâmicas do console.
- **FR-015**: Toda rota dinâmica do console DEVE passar seu parâmetro por essa
  decodificação.
- **FR-016**: O cliente de API DEVE continuar encodando o parâmetro exatamente
  uma vez ao montar o endereço.
- **FR-017**: Um parâmetro cuja decodificação é inválida DEVE ser tratado como
  o valor literal recebido, e NÃO DEVE derrubar a renderização.
- **FR-018**: A invariante "decodificado uma vez na borda, encodado uma vez no
  cliente" DEVE estar declarada no cliente de API, em substância.
- **FR-019**: Um teste DEVE exercitar a invariante com um parâmetro contendo
  caracteres reservados.

### Título e leitura honesta

- **FR-020**: O H1 do detalhe de incidente DEVE ser o título do incidente.
- **FR-021**: O H1 do detalhe de incidente NÃO DEVE ser um identificador, em
  nenhuma circunstância.
- **FR-022**: O título da aba do detalhe de incidente DEVE nomear o incidente.
- **FR-023**: O título da aba do detalhe de incidente NÃO DEVE ser um
  identificador, em nenhuma circunstância.
- **FR-024**: Quando a leitura do incidente falha, o cabeçalho DEVE dizer que o
  incidente não pôde ser lido.
- **FR-025**: Quando a leitura do incidente falha, nenhum chip DEVE afirmar que
  não existe investigação.
- **FR-026**: Quando a leitura do incidente sucede e o título é vazio, o
  cabeçalho DEVE mostrar uma ausência declarada.

### Rotas que respondem pelos nomes

- **FR-027**: `/investigations` DEVE redirecionar para `/runs`.
- **FR-028**: `/setup` DEVE redirecionar para `/first-run`.
- **FR-029**: Os dois redirects DEVEM preservar os parâmetros de consulta do
  pedido.
- **FR-030**: Os dois redirects DEVEM reusar o mecanismo de redirect de rota
  aposentada que já existe.
- **FR-031**: Nenhum dos dois endereços DEVE terminar na tela de página
  inexistente.
- **FR-032**: A tabela de redirects DEVE deixar de ser específica de Settings,
  em nome e em comentário, uma vez que passa a carregar redirects de área.

### Links e busca

- **FR-033**: O link de uma linha da lista de incidentes DEVE usar a forma
  pública.
- **FR-034**: O link de um item de incidente no painel do dashboard DEVE usar a
  forma pública.
- **FR-035**: O link de um resultado de busca por incidente DEVE usar a forma
  pública.
- **FR-036**: O link de incidente no detalhe de um run DEVE usar a forma
  pública.
- **FR-037**: Nenhum endereço de incidente gerado pelo console DEVE conter
  caractere que precise de escape.
- **FR-038**: As quatro superfícies acima DEVEM gerar o mesmo endereço para o
  mesmo incidente.

### Painéis do detalhe

- **FR-039**: Com a forma pública em uso, os painéis servidos pela rota de
  detalhe de incidente DEVEM sair do estado de dependência falhada para um
  incidente que existe.
- **FR-040**: A timeline DEVE renderizar uma entrada por entrada devolvida pelo
  gateway.
- **FR-041**: Esta feature NÃO DEVE alterar o vocabulário dos chips do detalhe
  de incidente além do exigido por FR-025.
- **FR-042**: Esta feature NÃO DEVE alterar a sub-linha de meta do detalhe de
  incidente.

### Contrato e artefatos gerados

- **FR-043**: O documento de API committed DEVE refletir a forma pública no
  contrato de incidente.
- **FR-044**: O cliente de API gerado DEVE ser regenerado a partir do documento
  atualizado.
- **FR-045**: O dataset simulado DEVE servir a forma pública em todo incidente
  que ele descreve.
- **FR-046**: O registro de telas visuais DEVE continuar resolvendo o endereço
  do detalhe de incidente a partir do dataset.

### Migração

- **FR-047**: Uma migração DEVE dar forma pública a todo incidente já
  armazenado.
- **FR-048**: A forma pública atribuída pela migração DEVE ser idêntica à que o
  código derivaria para o mesmo incidente.
- **FR-049**: A migração DEVE ser reversível.
- **FR-050**: A reversão da migração NÃO DEVE apagar nenhum incidente.
- **FR-051**: Um incidente existente no staging DEVE continuar abrível depois
  da migração.
- **FR-052**: A migração NÃO DEVE alterar a chave interna de nenhum incidente.

### Key Entities

- **Chave interna do incidente** — `alert:<source>:<fingerprint>@<instante>`,
  derivada da causa e do momento da abertura. Continua sendo a chave primária,
  o que a correlação usa e o que a timeline referencia. Não muda.
- **Forma pública do incidente** — o identificador que aparece em URL, em link
  e em qualquer lugar que uma pessoa possa copiar. Curto, sem caractere
  reservado, derivado da chave interna, único por organização.
- **Parâmetro de rota** — o que o roteador do console entrega a uma página
  dinâmica, ainda percent-encoded. Decodificado uma vez na borda, e daí em
  diante é o valor literal.
- **Rota aposentada** — um endereço que o produto já não serve mas cujo nome as
  pessoas ainda usam. Responde com redirect para o endereço vivo, preservando o
  que o pedido carregava.

## Success Criteria *(mandatory)*

- **SC-001**: Um incidente real de alerta, aberto a partir da lista no staging,
  mostra o título do incidente como H1.
- **SC-002**: Nenhuma URL de incidente gerada pelo console contém `%3A`, `%40`,
  `%2B`, `:`, `@` ou `+`.
- **SC-003**: Nenhum painel do detalhe de um incidente real está em estado de
  dependência falhada de `/v1/incidents/{incident_id}` no staging.
- **SC-004**: A timeline do detalhe de um incidente real desenha o mesmo número
  de entradas que o gateway devolve para ele.
- **SC-005**: Pedir o detalhe pela forma pública e pela chave interna devolve o
  mesmo incidente.
- **SC-006**: Todo incidente do banco de staging tem forma pública depois da
  migração, e nenhuma se repete.
- **SC-007**: A forma pública de um incidente do staging, computada pela
  função do código, é igual à que a migração gravou.
- **SC-008**: Um parâmetro de rota com caracteres reservados chega ao gateway
  como o valor original, encodado uma vez.
- **SC-009**: `/investigations` termina em `/runs` e `/setup` termina em
  `/first-run`, os dois no staging.
- **SC-010**: Com a leitura de detalhe falhada, o cabeçalho não contém o
  identificador e nenhum chip afirma ausência de investigação.
- **SC-011**: O acceptance spec desta feature foi confirmado vermelho antes da
  implementação, com a mensagem real de cada alegação registrada.
- **SC-012**: `make verify` termina verde, tendo partido de verde.

## Consultas de evidência em staging

Esta feature não alega gravação nova de comportamento do agente, mas alega
**migração de dados**. As consultas abaixo são o que prova, no banco
`ninjasre-stg-db` em `10.20.20.54`, e entram no DoD:

1. Cobertura da migração — precisa devolver `0`:
   `SELECT count(*) FROM incidents WHERE public_id IS NULL OR public_id = '';`
2. Unicidade dentro da organização — precisa devolver `0` linhas:
   `SELECT org_id, public_id, count(*) FROM incidents GROUP BY org_id, public_id HAVING count(*) > 1;`
3. Total inalterado — o número antes da migração e o depois são iguais:
   `SELECT count(*) FROM incidents;`
4. Chave interna intacta — a amostra de `incident_id` capturada antes da
   migração é idêntica à de depois:
   `SELECT incident_id, public_id FROM incidents ORDER BY opened_at DESC LIMIT 10;`
5. Concordância entre migração e código — a forma pública de cada linha da
   amostra acima, recomputada pela função do código a partir do `incident_id`
   dela, é igual à coluna gravada.

O nome exato da coluna é decidido no plano; as consultas acima assumem
`public_id` e são reescritas se o plano decidir outro nome.

## Assumptions

- **A chave interna não muda.** Ela é a chave primária, a referência da
  timeline e o que a correlação usa para não abrir um segundo incidente para a
  mesma causa. Mudá-la seria uma feature de persistência, não de identidade
  endereçável, e arrastaria a timeline junto.
- **A forma pública é derivada, não sorteada.** Um identificador aleatório
  exigiria que a migração inventasse um valor por linha e tornaria impossível
  reconciliar um incidente escrito por um nó antigo com um escrito por um nó
  novo. Derivada, a migração e o código concordam por construção.
- **A chave interna continua sendo endereço válido, e isso não é compat
  débito.** Não é um endereço aposentado com prazo de morte: é a chave primária
  da linha, e um operador depurando pelo banco precisa poder colá-la. O que
  morre é o produto **emitir** essa grafia — nenhum link volta a carregá-la.
- **O console é o único cliente de URL de incidente hoje.** A CLI fala com o
  gateway pela chave, o chat ainda não gera link de incidente. Portanto a
  mudança de forma pública não quebra um consumidor externo.
- **O decode de borda é necessário mesmo com a forma pública curta.** A forma
  pública não tem reservado nenhum, então o incidente não precisaria dele; as
  outras rotas dinâmicas precisam, e a chave interna colada na URL também.
- **Nenhuma tela nova.** Todas as telas tocadas já existem; por isso não há
  mockup e a referência de DoD são as alegações normativas.
- **Esta feature é a dona dos arquivos de escrita única no seu slot.** O par
  dela na execução paralela é backend e não os toca.

## Dependencies

- Depende da feature de regras e governança da onda apenas por precedência de
  slot: a suíte transversal estendida e o modo de validação contra staging
  nascem lá. Nada nesta spec depende de decisão daquela.
- **Interseção nula com a feature par do slot** (registro do que o agente fez).
  Aquela é `platform/runs`, `gateway/runtime` e o contrato de runs; esta é
  console, `gateway/http/routes/incidents.py` e o armazenamento de incidentes.
  Nenhum arquivo em comum.
- Bloqueia a feature de fim de onda (o incidente que fecha o laço): sem
  endereço que abra, não há cenário ponta a ponta que termine numa timeline.
- **É pré-requisito da feature de uma-fonte-por-fato** na parte de chips do
  incidente: aquela deriva o chip de uma leitura bem-sucedida, e a leitura só
  passa a suceder aqui.

## Out of Scope

- **Os chips do detalhe de incidente e o estado "desconhecido".** Esta feature
  apenas impede a afirmação negativa sobre leitura falhada. O vocabulário do
  desconhecido, e sua aplicação nas outras superfícies, é da feature de
  uma-fonte-por-fato.
- **A sub-linha de meta do detalhe** ("Not recorded · ... · zone Unplaced · Not
  recorded") — placeholder atrás de placeholder é defeito próprio, de outra
  feature.
- **A identidade dos runs.** O nome de um run passa a ser o headline, e isso é
  das features de registro e de leitura do relato. Esta feature não toca a
  coluna INVESTIGATION nem o breadcrumb do run.
- **O cache de rota inteira das listas.** `/incidents` renderizar do Full Route
  Cache é defeito próprio, da feature de uma-fonte-por-fato.
- **O estate vazio e a integração Proxmox degradada**, que é o que deixa zone e
  host sem valor na sub-linha. É da feature de confiança de certificado.
- **Renderização de markdown, headline e report.** Outras features da onda.
- **Qualquer redirect além dos dois nomeados.** A tabela ganha duas linhas, não
  uma varredura por rota antiga.
- **Migração de dados de qualquer outra tabela.**
