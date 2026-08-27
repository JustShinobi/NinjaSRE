# Feature Specification: Confiabilidade das telas — audit com linhas, valor presente, contagem única, SSO honesto

**Feature Branch**: `feat/v6-020-confiabilidade-telas`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "Toda tela de Settings diz a verdade ou não diz
nada. Os cinco defeitos P1 confirmados no diagnóstico — audit log com contador
cheio e corpo vazio, colunas Value vazias em Autonomy e Notifications, contagem
do setup divergente na mesma tela, SSO validando formulário virgem em
snake_case, e os dois defeitos de copy — mais a suíte transversal que
transforma as regras da v5/v6 em teste executável."

**Referência visual (DoD)**: [../mockups/settings-v6.html#m5](../mockups/settings-v6.html#m5)
(contagem única), [#m2](../mockups/settings-v6.html#m2) (coluna Value da tabela
de guardrails) e [#m1](../mockups/settings-v6.html#m1) ("Set at" com um só "Set
at"). Audit log e SSO não têm âncora própria na v6 — são governados pelas
regras transversais da v5 (`specs_v5/mockups/settings-v5.html`, Parte 3) e pelo
diagnóstico §2.

**Evidência**: [../DIAGNOSTICO.md](../DIAGNOSTICO.md) §2, defeitos P1-3 a P1-6 e
P2-8; aderência §3 (linhas "Uma só contagem no setup", "Reconciliar Audit 200 ×
nothing", "Rolagem é bug").

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Audit log que mostra o que afirma (Priority: P1)

Um administrador abre `/settings/audit-log` para descobrir quem mudou o quê, e
vê os eventos — não uma tabela de cabeçalhos com a promessa de 156.735 eventos
por cima.

**Why this priority**: É a única tela do produto inteiramente quebrada. Um
audit em que não se pode confiar é pior que nenhum: o operador conclui que nada
aconteceu, e o registro está lá. A v5 nomeou a correção ("reconciliar 200
events × Nothing recorded") e ela não aconteceu — voltou com outros números.

**Independent Test**: Contra o dataset representativo (200 eventos no fetch,
total muito maior), abrir a tela e contar as linhas: existem, e o número que a
tela afirma é o número que ela desenha. Alternar Any/7/30 dias muda o
resultado.

**Acceptance Scenarios**:

1. **Given** um período com eventos registrados, **When** `/settings/audit-log`
   abre, **Then** o corpo da tabela tem pelo menos uma linha, com quando, quem,
   ação, sujeito e desfecho preenchidos.
2. **Given** qualquer estado da tela, **When** ela afirma uma contagem de
   eventos, **Then** essa contagem descreve a mesma população que o corpo
   exibe — nunca uma população maior que a desenhada.
3. **Given** um fetch inteiramente composto de eventos do principal do próprio
   deployment, **When** a tela os esconde por padrão, **Then** ela diz que os
   escondeu e oferece exibi-los — a tabela nunca fica muda com o filtro
   implícito por trás.
4. **Given** o seletor de período, **When** o administrador escolhe Any, 7 ou
   30 dias, **Then** a consulta reexecuta com o novo intervalo, o resultado
   muda de acordo e o preset ativo fica indicado.
5. **Given** um resultado de fato truncado, **When** a tela declara o
   truncamento, **Then** o número exibido e o número total vêm da mesma
   consulta e o texto só aparece quando há truncamento real.

### User Story 2 - Uma só contagem do setup (Priority: P1)

Um operador no meio do setup lê uma frase sobre onde está e quanto falta, e
essa frase é a mesma no wizard, no painel de passos e no card do dashboard.

**Why this priority**: Hoje a mesma tela diz "Step 5 of 7" no header e "3 of 5
steps left" no painel — dois denominadores, duas populações, e nenhum dos dois
bate com os 2 pendentes que a própria lista desenha. É o defeito que a v5
mandou matar ("uma só contagem, calculada num lugar só") e que voltou. Um
operador que não sabe quanto falta não sabe se terminou.

**Independent Test**: Abrir `/first-run` e o dashboard no mesmo estado de
deployment e comparar as três exibições: total, índice e pendentes coincidem, e
os pendentes coincidem com quantos itens a lista desenha como não concluídos.

**Acceptance Scenarios**:

1. **Given** um deployment em setup, **When** `/first-run` abre, **Then**
   posição e pendentes aparecem derivados da mesma lista que desenha o stepper,
   na forma que o mockup fixa (`#m5`): posição, nome do passo e pendentes numa
   linha só.
2. **Given** o mesmo estado, **When** o card do dashboard exibe o progresso,
   **Then** ele cita a mesma tripla (total, índice, pendentes) que o wizard.
3. **Given** a lista de passos desenhada na tela, **When** o operador conta os
   itens marcados como não concluídos, **Then** esse número é exatamente o
   número de pendentes que a tela afirma.
4. **Given** qualquer superfície do produto que exiba progresso de setup,
   **When** ela o exibe, **Then** não introduz um segundo denominador.

### User Story 3 - SSO que não acusa antes de perguntar (Priority: P1)

Um administrador abre Single sign-on pela primeira vez e vê um formulário
vazio, não um bloco vermelho de oito erros sobre campos que ele ainda não teve
chance de preencher.

**Why this priority**: A tela mais perigosa do produto (um valor errado tranca
a organização) recebe o operador com oito acusações em `client_id is required`,
`jwks_uri is required` — em snake_case, enquanto os labels ao lado dizem
"Client id" e "Key set". O operador não distingue "você errou" de "ainda não
começou", e a primeira impressão da tela é a de um sistema quebrado.

**Independent Test**: Abrir `/settings/single-sign-on` num deployment sem SSO
configurado e verificar: nenhuma mensagem de erro, nenhum identificador cru na
mensagem de problema ou validação, e um resumo neutro dizendo que ainda não
foi configurado. (O texto de ajuda de um campo — "o `token_endpoint` do seu
provedor" — pode nomear a chave OIDC exata: isso ajuda quem está procurando
por ela na página de descoberta do próprio provedor, e não é a acusação que
este critério proíbe.) Depois submeter vazio e verificar que aí sim os
problemas aparecem, com os labels humanos.

**Acceptance Scenarios**:

1. **Given** um deployment sem SSO configurado, **When** a página abre e nada
   foi digitado, **Then** nenhum erro de campo é exibido, e o estado aparece
   como resumo neutro ("Not configured yet" / "Ainda não configurado").
2. **Given** o formulário virgem, **When** o administrador sai de um campo sem
   preenchê-lo (blur) ou submete, **Then** os problemas daquele campo aparecem
   — e só então.
3. **Given** um problema reportado pelo deployment, **When** ele é exibido,
   **Then** nomeia o campo pelo label humano do próprio formulário, nunca pela
   chave do payload.
4. **Given** um formulário já preenchido e salvo, **When** o administrador
   reabre a página, **Then** o que aparece é o estado real da configuração
   (verificada, não verificada, ativa), não uma lista de requisitos.

### User Story 4 - Tabela de configuração com valor (Priority: P2)

Um operador olha Guardrails ou Notifications e descobre o que está valendo —
"On · level strict", "2 hours" — em vez de uma coluna VALUE vazia com
"Deployment default" ao lado.

**Why this priority**: Doze linhas em duas telas informam a origem de um valor
que nunca mostram. O operador não descobre o valor efetivo de nada; a tela
existe e não informa. É a diferença entre uma tela de configuração e um
navegador de schema.

**Independent Test**: Abrir `/settings/autonomy-guardrails` e
`/settings/notifications` e verificar que nenhuma célula da coluna Value está
vazia, e que os valores conferem com o que o deployment de fato aplica.

**Acceptance Scenarios**:

1. **Given** a tabela de guardrails, **When** ela desenha uma linha, **Then** a
   coluna Value carrega o valor efetivo — o override quando existe, o default
   herdado quando não — formatado para leitura, como o mockup fixa (`#m2`):
   "Masking · On · level strict", "Approval expiry · 2 hours".
2. **Given** um valor booleano, de duração, numérico ou de enumeração, **When**
   ele é exibido, **Then** aparece na forma que uma pessoa lê (On/Off, horas,
   número, frase), nunca como literal do payload.
3. **Given** a origem do valor, **When** ela é exibida, **Then** ocupa a coluna
   Set at ("Deployment default"), separada do valor.
4. **Given** um campo que de fato não tem valor algum, **When** a linha é
   desenhada, **Then** a célula diz isso explicitamente ("Not set"), porque uma
   célula vazia é indistinguível de um defeito de render.

### User Story 5 - Copy que conta e não se repete (Priority: P3)

Um operador lê "1 token" e "Set at: deployment default" — não "1 tokens" nem
"Set at Set at: default".

**Why this priority**: São dois defeitos pequenos e visíveis que corroem a
confiança no resto: uma tela que erra o plural de um substantivo é uma tela que
o leitor passa a conferir.

**Independent Test**: Um grupo de tokens com exatamente um token exibe a forma
singular; a coluna de origem em models-providers exibe o rótulo uma única vez.

**Acceptance Scenarios**:

1. **Given** uma contagem exibida em texto, **When** ela vale um, **Then** o
   substantivo aparece no singular, nos dois idiomas.
2. **Given** uma coluna intitulada "Set at", **When** uma célula dela é
   desenhada, **Then** carrega apenas o nó de origem; o rótulo "Set at:" só
   aparece onde a linha é autônoma e não tem cabeçalho que já o diga (`#m1`).

### User Story 6 - As regras transversais viram teste (Priority: P1)

O time deixa de descobrir no confronto final que uma regra da onda foi violada:
uma suíte roda a cada fronteira de feature e diz qual rota violou qual regra.

**Why this priority**: Todo defeito desta feature é a reincidência de uma regra
que a v5 escreveu em prosa e ninguém pôde executar. Uma regra sem instrumento é
uma intenção. A suíte é o que impede a v6 de repetir a v5.

**Independent Test**: Introduzir deliberadamente uma violação de cada uma das
quatro regras numa rota conforme e verificar que a suíte reprova, nomeando a
rota e a regra; desfazer e verificar que volta a passar.

**Acceptance Scenarios**:

1. **Given** as rotas de Settings, **When** a suíte roda, **Then** verifica
   quatro regras: vocabulário banido no texto visível, orçamento de rolagem,
   contagem única entre superfícies, e nenhuma célula de valor vazia.
2. **Given** uma rota que ainda viola uma regra por pertencer a um redesenho
   que outra feature entrega, **When** a suíte roda, **Then** essa rota aparece
   como exceção anotada por rota — declarada, com o motivo substantivo escrito
   ali — e não como uma regra enfraquecida para todo mundo.
3. **Given** a feature que redesenha aquela rota, **When** ela entrega,
   **Then** remove a exceção daquela rota, e a suíte passa a cobrá-la.
4. **Given** a suíte como arquivo committed, **When** alguém a lê num clone
   limpo, **Then** ela é auto-suficiente: nenhuma referência a documento de
   planejamento, número de feature ou onda.

### Edge Cases

- **Audit sem nenhum evento no período**: a tela mostra o estado vazio com a
  ação de alargar o período, e não afirma contagem alguma. O estado vazio é
  decidido pela população que a tela de fato desenha, não pela que buscou.
- **Audit em que todo o fetch é do principal do deployment**: a tela não pode
  ficar muda; ou exibe as linhas, ou declara a exclusão com a saída para
  desfazê-la — o caso que produz o defeito atual.
- **Setup já concluído**: a contagem some em vez de exibir "0 of 5" — mas some
  nas três superfícies ao mesmo tempo, pela mesma decisão.
- **Lista de passos vinda incompleta do deployment**: se a fonte não pode ser
  lida, nenhuma superfície inventa um total; todas dizem que não sabem.
- **SSO parcialmente preenchido e salvo com erro**: os problemas do servidor
  aparecem ancorados nos campos que os causaram, e o resumo neutro dá lugar ao
  estado real.
- **Campo de configuração com valor legítimo vazio** (string em branco
  deliberada): a célula diz "Not set" ou o valor entre aspas, nunca nada.
- **Rota de Settings adicionada depois da suíte**: entra na lista de rotas
  varridas por construção (a suíte lê as rotas de Settings do produto), e não
  por alguém lembrar de acrescentá-la.

## Requirements *(mandatory)*

### Functional Requirements

**Audit log**

- **FR-001**: A tela de audit DEVE derivar qualquer contagem que exibe da mesma
  população de linhas que desenha; uma contagem que descreva uma população
  maior que a exibida é proibida.
- **FR-002**: Com eventos no período, `/settings/audit-log` DEVE desenhar pelo
  menos uma linha; cabeçalhos com corpo vazio ao lado de uma contagem positiva
  são o defeito que esta feature fecha.
- **FR-003**: A exclusão implícita de qualquer categoria de ator (hoje, o
  principal do próprio deployment) DEVE ser declarada na tela sempre que ela
  esconder linhas, com a ação que a desfaz.
- **FR-004**: O estado vazio da tela DEVE ser decidido pela população exibida,
  não pela população buscada.
- **FR-005**: Os presets de período (qualquer período, 7 dias, 30 dias) DEVEM
  reexecutar a consulta com o novo intervalo e indicar qual está ativo.
- **FR-006**: O aviso de truncamento DEVE aparecer apenas quando há
  truncamento, com ambos os números vindos da mesma consulta.

**Contagem do setup**

- **FR-007**: Uma única fonte DEVE derivar total, índice do passo atual e
  número de pendentes, a partir da mesma lista que desenha o stepper.
- **FR-008**: O header do wizard, o painel de passos e o card do dashboard
  DEVEM exibir a mesma tripla; nenhum deles calcula a sua.
- **FR-009**: O número de pendentes exibido DEVE ser igual ao número de itens
  que a própria lista desenha como não concluídos.
- **FR-010**: Nenhuma superfície DEVE introduzir um segundo denominador para o
  progresso de setup.
- **FR-011**: Quando a fonte não puder ser lida, nenhuma superfície DEVE exibir
  um total inferido.

**Single sign-on**

- **FR-012**: Um formulário sem interação DEVE ser exibido sem nenhum erro de
  campo.
- **FR-013**: Um erro de campo DEVE ser exibido apenas após interação com aquele
  campo (blur) ou após submissão.
- **FR-014**: Toda mensagem de problema DEVE nomear o campo pelo label humano do
  formulário; identificadores de payload não aparecem em mensagem de erro ou de
  validação. (O texto de ajuda de um campo pode nomear a chave técnica exata
  quando isso ajuda a preenchê-lo — nomear uma chave OIDC no texto de ajuda não
  é o mesmo que acusar alguém com ela numa mensagem de problema.)
- **FR-015**: O estado de uma configuração inexistente DEVE ser um resumo
  neutro ("Not configured yet" / "Ainda não configurado"), não uma lista de
  requisitos não atendidos.
- **FR-016**: Após submissão, os problemas devolvidos pelo deployment DEVEM ser
  exibidos ancorados nos campos que os causaram.

**Valor nas tabelas de configuração**

- **FR-017**: Toda linha de uma tabela de configuração DEVE renderizar, na
  coluna de valor, o valor efetivo: o override quando existe, o default herdado
  quando não.
- **FR-018**: O valor DEVE ser formatado por tipo para leitura humana —
  booleano como estado, duração como tempo, número como número, enumeração como
  frase — nunca como literal do payload.
- **FR-019**: A origem do valor DEVE ocupar a coluna de origem, separada do
  valor.
- **FR-020**: Um campo sem valor algum DEVE ser exibido com uma marca explícita
  de ausência; célula vazia é proibida.
- **FR-021**: O componente de tabela de configuração DEVE exigir um valor
  renderizável de quem o usa, de modo que a ausência seja um erro de quem
  monta a linha e não um espaço em branco na tela.

**Copy**

- **FR-022**: Toda contagem exibida em texto DEVE usar a forma singular ou
  plural do idioma, nos dois idiomas embarcados.
- **FR-023**: Um rótulo de coluna DEVE aparecer uma única vez: células sob uma
  coluna de origem carregam apenas o nó; o rótulo prefixado existe só onde a
  linha é autônoma.

**Suíte transversal**

- **FR-024**: O repositório DEVE conter uma suíte de comportamento que verifica,
  nas rotas de Settings, quatro regras: vocabulário banido, orçamento de
  rolagem, contagem única e coluna de valor preenchida.
- **FR-025**: A regra de vocabulário DEVE reprovar, no texto visível,
  identificadores de conta de serviço em caixa alta, estados de saúde crus,
  prefixos de caminho de configuração, nomes de rota de entrega e mensagens de
  campo obrigatório em snake_case.
- **FR-026**: A regra de rolagem DEVE medir a altura do documento renderizado
  contra um orçamento declarado em viewports, no viewport de 1920×1080
  explicitamente declarado pela própria suíte, lendo o orçamento e as dimensões
  das constantes nomeadas que já os definem.
- **FR-027**: A regra de contagem única DEVE comparar os números de progresso do
  setup entre todas as superfícies que os exibem.
- **FR-028**: A regra de valor DEVE reprovar qualquer célula vazia na coluna de
  valor de uma tabela de configuração.
- **FR-029**: A suíte DEVE oferecer exceção por rota, anotada com o motivo
  substantivo junto da própria rota, aplicável a uma rota e uma regra por vez —
  nunca ao relaxamento global de uma regra.
- **FR-030**: A exceção DEVE ser removível pela feature que redesenha a rota,
  sem tocar na regra.
- **FR-031**: A suíte DEVE ser auto-suficiente num clone limpo: nenhuma
  referência a documento de planejamento, número de feature, onda ou caminho
  não committed.

### Key Entities

- **Consulta de audit**: período, ator, ação, audiência → eventos exibidos +
  contagem (uma população só).
- **Progresso de setup**: lista de passos → (total, índice atual, pendentes),
  uma derivação consumida por três superfícies.
- **Campo de configuração**: caminho, tipo, valor efetivo, origem, editabilidade
  — o valor efetivo é obrigatório para desenhar a linha.
- **Estado de formulário**: virgem, tocado por campo, submetido — decide o que
  pode ser exibido como erro.
- **Regra transversal**: nome, rotas em que vale, exceções por rota com motivo.

## Success Criteria *(mandatory)*

- **SC-001**: Em `/settings/audit-log`, contra o dataset representativo (200
  eventos no fetch), o número de linhas desenhadas é maior que zero e a
  contagem afirmada na tela descreve exatamente a população desenhada — zero
  divergências.
- **SC-002**: Os três pontos que exibem progresso de setup (header do wizard,
  painel de passos, card do dashboard) citam a mesma tripla no mesmo estado de
  deployment — zero divergências, verificado por comparação automática.
- **SC-003**: `/settings/single-sign-on` sem configuração e sem interação exibe
  zero mensagens de erro e zero identificadores em snake_case em mensagem de
  erro ou de validação. (O texto de ajuda de um campo pode nomear a chave OIDC
  exata — isso não é uma mensagem de erro nem de validação, e nomear a chave
  ajuda quem está configurando a procurá-la na página do próprio provedor.)
- **SC-004**: Zero células vazias na coluna de valor em todas as rotas de
  Settings que desenham tabela de configuração.
- **SC-005**: Zero ocorrências dos termos banidos no texto visível das rotas de
  Settings, exceto rotas com exceção anotada.
- **SC-006**: Toda rota de Settings sem exceção anotada mede altura de documento
  dentro do orçamento de 2 viewports, medida em viewport de 1920×1080 declarado
  explicitamente pela suíte.
- **SC-007**: A suíte transversal reprova uma regressão deliberada de cada uma
  das quatro regras, nomeando rota e regra, e volta a passar quando a regressão
  é desfeita.
- **SC-008**: "1 tokens" e "Set at Set at:" não são reproduzíveis em nenhuma
  rota do produto.
- **SC-009**: Um clone limpo do repositório roda a suíte transversal sem
  nenhum arquivo de planejamento presente.

## Assumptions

- O gateway já devolve, em uma consulta, os eventos e o total do audit; a
  divergência atual é da tela, não do contrato. Se a reprodução mostrar o
  contrário, a correção da causa raiz cabe nesta feature e o teste que a
  provar entra antes.
- A lista de passos servida pelo deployment é a fonte legítima do progresso; a
  sequência de telas do console deixa de ser um segundo denominador e passa a
  ser uma apresentação da mesma lista. Isso reverte, deliberadamente, a decisão
  registrada hoje no código de que os dois números medem coisas diferentes.
- Os valores efetivos dos campos de configuração já são conhecidos pelo
  produto (override e default); o defeito é de apresentação.
- O redesenho da Autonomy em três abas e a redução da sua rolagem pertencem à
  feature 040; esta feature entrega os valores da tabela e registra a exceção
  de rolagem daquela rota.
- Vocabulário cru remanescente (chips, IDs, títulos de grupo) pertence à 030;
  esta feature cria a regra e a suíte, e anota as rotas que a 030 ainda vai
  limpar.

## Dependencies

- Nenhuma feature desta onda a precede (`progress.json`: `020` sem
  dependências).
- A 030 e a 040 dependem desta: a suíte transversal nasce aqui e passa a rodar
  em toda fronteira de feature a partir da 030, e cada uma remove as exceções
  das rotas que redesenha.
- Gates tocados: `make verify` (lint, format-check, typecheck, check-imports,
  check-constants, check-protocols, check-deps, suíte), Vitest
  (`console/tests/unit/`), Playwright projeto `behaviour`
  (`console/tests/e2e/`), Playwright projeto `visual`
  (`console/visual/screens.json` e as baselines das telas alteradas).
