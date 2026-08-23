# Feature Specification: Integrações em slide-over e Alert intake enxuto

**Feature Branch**: `feat/v6-050-integrations-slideover-intake`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "As duas superfícies que sobraram do corte ficam do
tamanho da realidade. Catálogo de 15 sem paginação, com o detalhe em slide-over
sobre o catálogo e deep-link preservado; Alert intake com três fontes, a URL e o
YAML do receiver prontos para colar, o trust legível e a cadeia intake → regra →
ação → destino desenhada em uma linha."

**Referência visual (DoD)**:
[../mockups/settings-v6.html#m4](../mockups/settings-v6.html#m4) — catálogo em
três seções, contagem no topo, busca, slide-over de credencial — e
[#m3](../mockups/settings-v6.html#m3) — três fontes de intake, estado por fonte,
YAML do receiver, cadeia de quatro nós. As regras transversais da v5
(`specs_v5/mockups/settings-v5.html`, Parte 3) continuam normativas por
referência.

**Rotas tocadas**: `/integrations`, `/integrations/<name>`,
`/integrations/not-covered`, `/settings/alert-intake` e — só para desfazer a
sobreposição de nomes que fecha a cadeia — `/settings/schedules-destinations`.

**Dependência**: 001 (o catálogo já cortado para 15 integrações; as fontes de
intake do backend já reduzidas a `alertmanager`, `grafana` e `generic`).

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ver o catálogo inteiro numa rolagem curta (Priority: P1)

O operador abre Integrations e encontra tudo o que o produto oferece em três
seções — o que está conectado, o que o próprio ambiente sugere, o que resta —
sem trocar de página e sem rolar duas telas.

**Why this priority**: Hoje o catálogo é paginado ("Page 1 of 4" sobre 85
itens). Depois do corte da 001 são 15, e paginar 15 é esconder onze deles atrás
de um controle que existia para outro problema. A régua "rolagem é bug" volta a
valer para esta tela.

**Independent Test**: Abrir `/integrations` com o catálogo pós-corte inteiro,
medir a altura da página em 1080p e procurar um controle de paginação.

**Acceptance Scenarios**:

1. **Given** o catálogo pós-corte, **When** o operador abre `/integrations`,
   **Then** as seções aparecem nesta ordem — Connected, Suggested by your
   estate, Available — e nenhum controle de página existe na tela.
2. **Given** três integrações conectadas e três sugeridas, **When** a tela abre,
   **Then** o topo traz uma contagem única no formato "N integrations · M
   connected · K suggested", com os três números derivados do que a API
   devolveu.
3. **Given** o operador digita o nome de uma capacidade na busca, **When** o
   filtro roda, **Then** os itens que casam permanecem dentro das suas seções e
   a ordem das seções não muda.
4. **Given** nenhuma sugestão do estate, **When** a tela abre, **Then** a seção
   Suggested não aparece e a contagem do topo perde o seu terceiro termo em vez
   de exibir zero.

---

### User Story 2 - Abrir o detalhe sem perder o lugar (Priority: P1)

Clicar numa integração abre um painel sobreposto ao catálogo. O operador
continua vendo onde estava, e fechar devolve exatamente a mesma vista.

**Why this priority**: É o defeito nomeado do diagnóstico. O detalhe é hoje um
painel no rodapé de uma página de 2.141px: clicar numa integração joga o
operador para o fim do documento, e o deep-link `/integrations/prometheus`
aterrissa no fundo. O padrão de slide-over foi fixado como normativo na v5 e a
implementação não o cumpriu.

**Independent Test**: Medir a posição de rolagem antes de abrir, com o painel
aberto e depois de fechar; abrir o deep-link direto e medir onde a página
aterrissa.

**Acceptance Scenarios**:

1. **Given** o catálogo rolado até a seção Available, **When** o operador clica
   numa integração, **Then** o painel aparece sobreposto ao catálogo e a posição
   de rolagem não muda.
2. **Given** o painel aberto, **When** o operador fecha pelo botão, por Escape
   ou navegando para trás, **Then** o catálogo volta à mesma posição e aos
   mesmos filtros.
3. **Given** o endereço `/integrations/alertmanager` colado direto na barra,
   **When** a página carrega, **Then** o catálogo aparece com o painel daquela
   integração aberto e a rolagem no topo do catálogo.
4. **Given** um nome que não existe mais no catálogo, **When** o endereço é
   aberto, **Then** o painel diz que a integração não está disponível e oferece
   voltar ao catálogo e ver a lista do roadmap.

---

### User Story 3 - Uma integração já verificada mostra o que dá para fazer (Priority: P1)

Abrir o detalhe de uma integração que já funciona não apresenta um formulário
vazio: apresenta o estado da credencial guardada e as três ações que fazem
sentido sobre ela.

**Why this priority**: Hoje uma integração verificada abre com o campo Token em
branco e "Save and test" desabilitado. A tela parece quebrada exatamente onde o
produto está saudável, e não oferece nenhum caminho — nem testar de novo, nem
trocar a credencial, nem desconectar.

**Independent Test**: Abrir o painel de uma integração verificada e listar o que
a tela diz sobre a credencial e quais ações ela oferece.

**Acceptance Scenarios**:

1. **Given** uma integração com credencial guardada, **When** o painel abre,
   **Then** nenhum campo de credencial vazio com ação desabilitada aparece; o
   painel afirma que a credencial está guardada no vault.
2. **Given** o mesmo painel, **When** o operador o percorre, **Then** encontra
   "Test again", "Replace credential" e "Disconnect" como ações nomeadas.
3. **Given** "Test again" acionado, **When** a verificação retorna, **Then** o
   resultado aparece como chip do vocabulário canônico com o diagnóstico ao
   lado.
4. **Given** "Replace credential" acionado, **When** o formulário aparece,
   **Then** é o mesmo formulário write-only da conexão, com "Save and test" como
   ação primária única.
5. **Given** "Disconnect" acionado, **When** a confirmação aparece, **Then** ela
   nomeia a integração e o que será removido antes de qualquer escrita.

---

### User Story 4 - Ver as três fontes de intake e o estado real de cada uma (Priority: P1)

Alert intake mostra as três fontes que o produto realmente aceita, com a que
está recebendo aberta e as caladas em uma linha cada.

**Why this priority**: Hoje são sete cartões idênticos dizendo a mesma coisa
("Nothing has ever arrived"), sobre fontes que a 001 já removeu do backend. A
tela ocupa 2,1 viewports para não informar nada.

**Independent Test**: Abrir `/settings/alert-intake`, contar as fontes, medir a
altura da página em 1080p e ler o chip de cada fonte.

**Acceptance Scenarios**:

1. **Given** o backend pós-corte, **When** a tela abre, **Then** existem
   exatamente três fontes — Alertmanager, Grafana e Generic webhook — e nenhuma
   outra.
2. **Given** uma fonte com entregas nos últimos dias, **When** a tela abre,
   **Then** ela aparece expandida, com o chip "Receiving", a última entrega em
   tempo relativo e o volume da semana.
3. **Given** uma fonte sem nenhuma entrega, **When** a tela abre, **Then** ela
   ocupa uma linha só, com o chip "Ready — nothing arrived yet".
4. **Given** qualquer fonte, **When** o operador a examina, **Then** o formato
   esperado e o envio de teste estão recolhidos sob "Format & test".

---

### User Story 5 - Colar o receiver do Alertmanager num gesto (Priority: P1)

A distância entre a tela de intake e o alerta chegando é um copy-paste: a URL
completa, o YAML do receiver pronto, e o trust dito em português de gente.

**Why this priority**: O webhook do deployment recusa qualquer POST sem delivery
token, e a tela chama esse mecanismo de "Trusted by webhook.deliver" — um nome
de permissão cru que não diz ao operador o que fazer. O caminho entre "existe um
endpoint" e "o Alertmanager do cluster entrega nele" é hoje inteiramente
conhecimento tácito.

**Independent Test**: Copiar o YAML da tela, colá-lo na configuração de um
Alertmanager e verificar se a entrega chega.

**Acceptance Scenarios**:

1. **Given** a fonte Alertmanager, **When** o operador a examina, **Then** vê a
   URL completa do deployment com "Copy URL" ao lado.
2. **Given** a mesma fonte, **When** o operador aciona "Copy Alertmanager
   receiver YAML", **Then** o que vai para a área de transferência é um bloco
   `webhook_configs` colável, contendo a URL deste deployment e o header de
   autorização nomeando o delivery token em uso.
3. **Given** qualquer fonte, **When** o operador lê a linha de confiança,
   **Then** ela diz "Authenticated with delivery token `<nome>`" e oferece
   "rotate".
4. **Given** "rotate" acionado, **When** a navegação acontece, **Then** o
   operador aterrissa em Machine tokens já filtrada para os tokens de entrega.
5. **Given** nenhum delivery token emitido, **When** a tela abre, **Then** a
   linha de confiança diz isso e a ação oferecida é emitir o token, não copiar
   um YAML que não autentica.

---

### User Story 6 - Ver o que acontece com um alerta que chega (Priority: P2)

Numa linha só, a tela desenha a cadeia: o que entra, a regra que decide, a ação
que roda, o destino do resultado — e cada nó leva à tela que o possui.

**Why this priority**: A relação entre intake, regras e destinos hoje é deduzida
percorrendo três telas. Duas delas chamam a mesma coisa por nomes sobrepostos
("Advanced: routing rules and delivery destinations" e "Advanced: chat channels,
report destinations and notification sinks"), o que impede fechar a cadeia sem
sinônimos.

**Independent Test**: Abrir `/settings/alert-intake`, contar os nós da cadeia e
clicar em cada um.

**Acceptance Scenarios**:

1. **Given** o deployment configurado, **When** a tela abre, **Then** a cadeia
   aparece em uma linha com quatro nós: entrada, regra, ação e destino.
2. **Given** a cadeia, **When** o operador lê cada nó, **Then** cada um traz o
   valor efetivo deste deployment, não um exemplo.
3. **Given** a cadeia, **When** o operador clica num nó, **Then** aterrissa na
   tela que possui aquele ajuste.
4. **Given** nenhuma regra configurada, **When** a tela abre, **Then** o nó da
   regra diz que não há regra e oferece criá-la — a cadeia não desaparece.
5. **Given** as seções avançadas de schedules-destinations, **When** o operador
   as lê, **Then** os dois nomes não compartilham nenhum substantivo, e o nó de
   destino da cadeia aterrissa naquela cujo nome corresponde.

---

### User Story 7 - Saber o que saiu, e por quê (Priority: P3)

O corte é auditável de dentro do produto: um link no rodapé do catálogo leva à
lista das integrações que foram para o roadmap e ao critério que as tirou.

**Why this priority**: O operador que procura um vendor removido precisa de uma
resposta, não de um catálogo silencioso. Fora do fluxo, porque é uma pergunta
rara.

**Independent Test**: Rolar o catálogo até o fim, seguir o link e conferir se a
lista e o critério estão lá.

**Acceptance Scenarios**:

1. **Given** o catálogo, **When** o operador chega ao rodapé, **Then** encontra
   "N integrations moved to the roadmap · see the list and why", com N calculado.
2. **Given** o link seguido, **When** a página de referência abre, **Then** ela
   lista as integrações removidas e diz o critério que as removeu.
3. **Given** o rodapé de Alert intake, **When** o operador o lê, **Then** as
   fontes de intake retiradas são nomeadas com a mesma explicação.
4. **Given** uma busca sem resultado no catálogo, **When** o grid esvazia,
   **Then** o empty state oferece limpar a busca e o mesmo link de referência.

---

### Edge Cases

- **Nenhuma integração conectada**: a seção Connected não é renderizada vazia; a
  contagem do topo continua correta e a seção Available carrega o catálogo
  inteiro.
- **Estate não conhece o endereço do serviço**: o campo de endereço fica sem
  placeholder. A tela nunca inventa um endereço nem repete o de outro
  deployment.
- **Credencial guardada e nunca verificada**: o painel mostra o estado
  "Armazenada" e oferece "Test again" — não trata ausência de verificação como
  falha.
- **Integração falhando**: permanece na seção Connected com chip crítico e
  diagnóstico; uma credencial ruim não devolve a integração ao catálogo.
- **Sugestão do estate para integração já conectada**: não aparece como
  sugestão.
- **Deep-link para integração removida pelo corte**: o painel diz que ela não
  está disponível e aponta o roadmap; não é uma página de erro.
- **Gateway indisponível ao abrir qualquer das duas telas**: o painel declara a
  dependência que falhou, com o nome dela; não renderiza lista vazia como se o
  deployment estivesse limpo.
- **Viewer sem permissão de gerenciar integração**: o formulário e as ações de
  escrita ficam ausentes com a razão dita, não presentes e desabilitados.
- **Mais de um delivery token válido**: a linha de confiança nomeia o que a
  fonte usa, não "um token".
- **Delivery token emitido no mesmo gesto**: o YAML copiado pode carregar o
  valor recém-emitido, que é a única vez em que ele existe fora do vault; em
  qualquer outro momento o YAML traz o header com o nome do token e um marcador
  explícito no lugar do segredo.
- **Fonte com rejeições recentes**: as rejeições continuam visíveis na fonte,
  sem transformar "chegou e foi recusado" em "nada chegou".
- **Nenhum destino configurado**: o nó de destino diz isso e leva à tela que o
  configura.

---

## Requirements *(mandatory)*

### Functional Requirements — catálogo (#m4)

- **FR-001**: A página `/integrations` DEVE apresentar as seções nesta ordem:
  Connected, Suggested by your estate, Available.
- **FR-002**: Uma seção sem itens NÃO DEVE ser renderizada.
- **FR-003**: O catálogo NÃO DEVE paginar: nenhum controle de página, nenhuma
  contagem "Page N of M", e todo item do catálogo presente na primeira carga.
- **FR-004**: O topo DEVE trazer uma contagem única com o total de integrações,
  o número de conectadas e o número de sugeridas.
- **FR-005**: Os três números DEVEM ser derivados do payload recebido; nenhum
  deles é literal em código, teste ou fixture.
- **FR-006**: Quando não há sugestões, a contagem DEVE omitir o terceiro termo
  em vez de exibir zero.
- **FR-007**: Nenhum outro número na mesma tela pode contradizer essa contagem.
- **FR-008**: A tela DEVE oferecer busca por nome de exibição e por capacidade.
- **FR-009**: A busca DEVE filtrar dentro das seções, preservando a ordem delas.
- **FR-010**: A altura de `/integrations`, com o catálogo pós-corte inteiro, NÃO
  DEVE exceder 2 viewports em 1080p.
- **FR-011**: Cada item DEVE exibir nome de exibição e um resumo de uma linha.
- **FR-012**: Nenhum identificador cru de integração ou de recurso DEVE aparecer
  no rosto de um card.
- **FR-013**: Cada card da seção Suggested DEVE nomear o serviço descoberto e o
  container em que ele foi encontrado.
- **FR-014**: O identificador do recurso descoberto PODE viajar no link do card,
  nunca no seu texto.
- **FR-015**: O rodapé do catálogo DEVE trazer a contagem das integrações
  movidas para o roadmap e um link para a lista.
- **FR-016**: Essa contagem DEVE ser derivada do que a API devolve, não escrita
  à mão.
- **FR-017**: O link DEVE levar a uma página de referência fora do fluxo,
  contendo a lista das removidas e o critério que as removeu.
- **FR-018**: O empty state da busca sem resultado DEVE oferecer limpar a busca
  e o mesmo link de referência.

### Functional Requirements — slide-over de detalhe (#m4)

- **FR-019**: O detalhe de uma integração DEVE ser apresentado sobreposto ao
  catálogo, e não como um bloco no fluxo do documento abaixo dele.
- **FR-020**: Abrir o detalhe NÃO DEVE alterar a posição de rolagem do catálogo.
- **FR-021**: A rota `/integrations/<name>` DEVE continuar existindo e DEVE
  renderizar o catálogo com o painel daquela integração aberto.
- **FR-022**: Aberto por deep-link, o catálogo DEVE aterrissar no seu topo, e
  nunca no rodapé da página.
- **FR-023**: Fechar o painel — pelo controle de fechar, por Escape, ou saindo
  da rota — DEVE devolver o catálogo à posição de rolagem anterior.
- **FR-024**: Fechar o painel DEVE preservar os filtros e a busca ativos.
- **FR-025**: O painel DEVE trazer no topo o nome de exibição da integração e o
  chip de estado do vocabulário canônico.
- **FR-026**: O painel DEVE listar as permissões requeridas pela integração.
- **FR-027**: Cada campo de credencial DEVE trazer uma instrução própria
  dizendo o que o valor é e quando ele é necessário.
- **FR-028**: Quando o estate conhece o endereço do serviço, o campo de endereço
  DEVE trazê-lo como placeholder.
- **FR-029**: Esse endereço DEVE vir da descoberta do estate servida pela API,
  nunca de uma constante na tela.
- **FR-030**: "Save and test" DEVE ser a ação primária única do formulário, com
  o cancelamento ao lado dela.
- **FR-031**: A nota de segurança DEVE permanecer, dizendo que o valor é
  guardado no vault, nunca reexibido, e que o teste faz uma requisição real.
- **FR-032**: Nenhum valor de credencial guardado DEVE ser reexibido pelo
  painel, em campo, em atributo do DOM ou na resposta da API.
- **FR-033**: Nenhum segredo DEVE viajar na URL do deep-link.

### Functional Requirements — integração já conectada

- **FR-034**: Para uma integração com credencial guardada, o painel NÃO DEVE
  apresentar um campo de credencial vazio acompanhado de ação desabilitada.
- **FR-035**: O painel DEVE afirmar que a credencial está guardada no vault.
- **FR-036**: O painel DEVE oferecer "Test again".
- **FR-037**: O painel DEVE oferecer "Replace credential".
- **FR-038**: O painel DEVE oferecer "Disconnect".
- **FR-039**: "Replace credential" DEVE revelar o mesmo formulário write-only da
  conexão.
- **FR-040**: "Disconnect" DEVE exigir uma confirmação que nomeia a integração e
  o que será removido.
- **FR-041**: O resultado de "Test again" DEVE ser exibido com o chip do
  vocabulário canônico e o diagnóstico que o acompanha.
- **FR-042**: Uma credencial guardada e nunca verificada DEVE ser exibida como
  armazenada, nunca como falhando.

### Functional Requirements — Alert intake (#m3)

- **FR-043**: `/settings/alert-intake` DEVE listar exatamente três fontes:
  Alertmanager, Grafana e Generic webhook.
- **FR-044**: Nenhuma fonte removida pelo corte DEVE aparecer na tela.
- **FR-045**: Uma fonte com entregas recentes DEVE ser renderizada expandida.
- **FR-046**: Essa fonte DEVE trazer o chip "Receiving".
- **FR-047**: Essa fonte DEVE informar a última entrega em tempo relativo.
- **FR-048**: Essa fonte DEVE informar o volume de entregas da semana.
- **FR-049**: Uma fonte sem nenhuma entrega DEVE ser renderizada em uma linha
  só.
- **FR-050**: Essa fonte DEVE trazer o chip "Ready — nothing arrived yet".
- **FR-051**: Cada fonte DEVE exibir a URL completa de entrega deste deployment,
  com esquema, host e caminho.
- **FR-052**: Cada fonte DEVE oferecer "Copy URL".
- **FR-053**: A fonte Alertmanager DEVE oferecer "Copy Alertmanager receiver
  YAML".
- **FR-054**: O conteúdo copiado DEVE ser um bloco `webhook_configs` colável na
  configuração de um Alertmanager.
- **FR-055**: Esse bloco DEVE conter a URL de entrega deste deployment.
- **FR-056**: Esse bloco DEVE conter o header de autorização que o webhook
  exige, nomeando o delivery token em uso.
- **FR-057**: O bloco DEVE ser derivado da configuração do deployment, e não
  montado por concatenação de literais na tela.
- **FR-058**: O bloco NÃO DEVE conter o valor de um segredo já guardado; quando
  o token não acaba de ser emitido, o lugar do valor é um marcador explícito.
- **FR-059**: A linha de confiança DEVE dizer que a entrega é autenticada por um
  delivery token e nomear esse token.
- **FR-060**: Nenhuma tela DEVE exibir um nome de permissão cru como o mecanismo
  de confiança.
- **FR-061**: A linha de confiança DEVE oferecer rotacionar o token.
- **FR-062**: Rotacionar DEVE levar a Machine tokens já filtrada para os tokens
  de entrega.
- **FR-063**: Sem nenhum delivery token emitido, a linha DEVE dizer isso e
  oferecer a emissão como ação.
- **FR-064**: O formato esperado e o envio de teste DEVEM permanecer por fonte,
  recolhidos por padrão sob "Format & test".
- **FR-065**: As rejeições recentes de uma fonte DEVEM continuar visíveis nela.
- **FR-066**: O rodapé DEVE nomear as fontes de intake movidas para o roadmap e
  a razão.
- **FR-067**: A altura de `/settings/alert-intake` NÃO DEVE exceder 2 viewports
  em 1080p.

### Functional Requirements — cadeia visível (#m3)

- **FR-068**: A tela DEVE desenhar a cadeia em uma linha com quatro nós:
  entrada, regra, ação e destino.
- **FR-069**: Cada nó DEVE exibir o valor efetivo deste deployment.
- **FR-070**: Nenhum nó DEVE exibir um exemplo ou um valor de amostra quando o
  valor real existe.
- **FR-071**: Cada nó DEVE navegar para a tela que possui aquele ajuste.
- **FR-072**: Um nó sem valor configurado DEVE dizer que não há e oferecer a
  ação que o configura; a cadeia continua com quatro nós.
- **FR-073**: As duas seções avançadas de `/settings/schedules-destinations`
  NÃO DEVEM ter nomes sobrepostos.
- **FR-074**: Os dois nomes NÃO DEVEM compartilhar nenhum substantivo entre si,
  seja por renomeação ou por fusão numa seção só.
- **FR-075**: O nó de destino da cadeia DEVE aterrissar na seção cujo nome
  corresponde ao que ele promete.

### Functional Requirements — transversais

- **FR-076**: As duas telas DEVEM usar o vocabulário canônico de estado — Not
  connected, Stored, Verified, Degraded, Failing — sem traduzir nenhum deles
  para outra palavra.
- **FR-077**: Toda string nova DEVE existir em inglês e em pt-BR.
- **FR-078**: Nenhum texto de produto DEVE ser adicionado fora da camada de
  i18n.

### Key Entities

- **Item de catálogo**: nome, nome de exibição, categoria, resumo, capacidades,
  estado de saúde, diagnóstico, campos de credencial (cada um com rótulo,
  instrução e escopo mínimo), permissões requeridas, sugestão do estate
  opcional.
- **Sugestão do estate**: integração, endereço descoberto, recurso de origem
  (nome de serviço e container para exibição, identificador para o link).
- **Fonte de intake**: nome, caminho de entrega, formato esperado, última
  entrega, volume recente, rejeições recentes, delivery token em uso.
- **Delivery token**: nome, finalidade, estado, endereço de rotação.
- **Nó da cadeia**: papel (entrada, regra, ação, destino), valor efetivo, tela
  dona, ação quando não configurado.

---

## Success Criteria *(mandatory)*

- **SC-001**: `/integrations`, com o catálogo pós-corte inteiro, cabe em no
  máximo 2 viewports a 1080p e não apresenta nenhum controle de paginação (hoje:
  paginado em quatro páginas).
- **SC-002**: Abrir o detalhe a partir de um card não muda a posição de rolagem
  do catálogo, e fechar devolve a mesma posição — medido, não afirmado.
- **SC-003**: O deep-link `/integrations/<name>` aterrissa com o painel aberto e
  a rolagem no topo do catálogo (hoje: no rodapé de uma página de 2.141px).
- **SC-004**: O painel de uma integração verificada oferece três ações nomeadas
  e nenhum campo de credencial vazio acompanhado de ação desabilitada.
- **SC-005**: `/settings/alert-intake` apresenta exatamente três fontes (hoje:
  sete cartões idênticos).
- **SC-006**: `/settings/alert-intake` cabe em no máximo 2 viewports a 1080p
  (hoje: 2,1).
- **SC-007**: O YAML copiado da tela, aplicado à configuração de um Alertmanager
  apontando este deployment, produz uma entrega aceita; o mesmo POST sem o
  header de autorização é recusado.
- **SC-008**: Nenhuma das duas telas exibe um nome de permissão cru como
  mecanismo de confiança.
- **SC-009**: A cadeia tem quatro nós e cada um navega para a tela que possui o
  ajuste correspondente.
- **SC-010**: Os dois nomes de seção avançada de schedules-destinations não
  compartilham nenhum substantivo.
- **SC-011**: A suíte transversal passa nas duas rotas desta feature.
- **SC-012**: Todo estado exibido nas duas telas é idêntico ao servido pela API,
  sem texto de estado duplicado ou divergente.

---

## Assumptions

- A 001 já entregou: catálogo de 15 integrações, fontes de intake reduzidas a
  `alertmanager`, `grafana` e `generic`, e a limpeza de rotas, fixtures e
  baselines órfãos das integrações removidas.
- Os números desenhados no mockup ("13 integrations · 3 connected · 3
  suggested", "72 integrations moved to the roadmap") são o retrato do desenho
  de 2026-08-16, feito antes de GitHub e Telegram entrarem na lista. A tela
  calcula; nenhum teste e nenhuma fixture escreve o total.
- O payload de `/v1/integrations` já serve categoria, resumo, saúde, sugestão do
  estate, campos de credencial e permissões. Os acréscimos previstos são o
  endereço descoberto para uso como placeholder e a distinção explícita entre
  credencial guardada e credencial verificada.
- As leituras de intake continuam vindo das rotas que a tela já consome; o
  acréscimo é o receiver YAML e o volume por janela.
- O delivery token é emitido em Machine tokens. O default seguro de escopos de
  token é assunto da 030 e não é redefinido aqui; esta feature apenas filtra a
  tela para a finalidade de entrega.
- Logos continuam sendo iniciais estilizadas; nada de marca de vendor.

## Dependencies

- **001** — catálogo cortado para 15 e fontes de intake reduzidas no backend.
  Sem ela, a tela de catálogo continua com 85 itens e o intake com sete fontes,
  e nenhum critério de rolagem desta spec é alcançável.
- Componentes já existentes que esta feature consome sem reescrever: o chip de
  estado canônico, a confirmação destrutiva que nomeia o alvo, o empty state, a
  captura de rolagem dos links do catálogo.

## Gates tocados

- `make verify` — suíte Python, lint, format-check, typecheck, check-imports e
  os guard checks.
- `make console-check` — format-check, lockfile, lint, typecheck, unit, budget,
  client-check e build do console.
- `make console-visual` — as duas rotas têm baseline registrada e as duas mudam;
  a recaptura é deliberada, por `make console-visual-accept`, com revisão.
- `check-display-names` — nomes de exibição obrigatórios para o que a tela
  mostra.
- `check-integration-docs` e `check-integrations` — o catálogo continua íntegro
  depois de a tela parar de paginar.
- `check-config-parity` — os campos de configuração que a cadeia lê continuam
  tendo dono declarado.
- `check-doc-examples` — comandos e caminhos citados em documentação committed
  continuam existindo.
- `tests/architecture/test_contract_coverage.py` — a cobertura de contrato do
  console contra a API que ele consome.
- Playwright `behaviour`, incluindo a suíte transversal, rodada nas duas rotas.
