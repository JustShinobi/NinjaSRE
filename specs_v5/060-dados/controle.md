# Controle — 060-dados

Estado verificado contra o código real na árvore de trabalho. Todo `file:line`
citado foi aberto antes de a linha que o cita ser escrita. Nenhum
`git add`/`commit` executado — a entrega é a árvore suja.

**Quem escreveu o quê.** O `spec-implementer` entregou a maior parte e morreu
duas vezes: teto de turno na primeira, limite de sessão da conta na segunda,
esta última no meio de uma frase. O orquestrador mediu a árvore em cada parada
e concluiu o que faltava — os dois specs Playwright, a frequência legível da
lista, o registro visual, a varredura de identificadores e este arquivo. As
linhas abaixo dizem qual das duas mãos fez cada item, porque "entregue" e "por
quem" são perguntas diferentes.

## 1. Peça por peça

| Peça | Estado | Detalhe |
|---|---|---|
| Duas páginas no grupo Data, com a permissão que a API exige | FEITO | `console/src/surfaces/settings/alert-intake.tsx` e `schedules-destinations.tsx`, ligadas em `console/src/app/(shell)/settings/{alert-intake,schedules-destinations}/page.tsx`. Permissão `config.read` — **já valia, verificado em** `console/src/shell/routes.ts:599-614`, obra da 010; o arquivo de rotas não foi tocado por esta feature. |
| Receptores como lista compacta: nome, endpoint copiável, chip de atividade | FEITO | `alert-intake.tsx:186-260`. Prova em navegador real: `console/tests/e2e/settings-data.spec.ts:39-55` (nada expandido na chegada) e `:90-106` (endereço copiável). |
| Formato, autenticação e teste no detalhe **recolhido** | FEITO | `Reference` (`console/src/design/reference.tsx`, componente da 001) em `alert-intake.tsx`. Unitário: `settings-alert-intake.test.tsx` — nenhum `reference-body`, `rule-simulator` ou `sample` no documento antes de ser pedido. Navegador: `settings-data.spec.ts:57-68` abre um detalhe e confirma que os outros seguem fechados. |
| Silêncio ≠ recusa de autenticação | **FEITO em parte; o resto já existia** — corrigido após verificação | **Já existia e foi migrado:** o bloco `recent_rejections` no papel `danger` com testid `rejections` estava byte a byte no `screens/data.tsx` removido (`git show HEAD:console/src/surfaces/screens/data.tsx`, linhas 193-204), e a fixture que o alimenta (a origem `grafana` recusada) já estava em `tools/mockplane/dataset/served.py` no HEAD — o diff deste arquivo **não adiciona nenhuma linha de recusa**, só a seção de destinos. **Novo de fato:** `<Badge status={text(source, 'last_outcome')} />` em `alert-intake.tsx:209`, que dá papel de cor ao desfecho da última entrega; antes "— accepted" e "— rejected" eram texto `muted` idêntico. O teste novo (`settings-alert-intake.test.tsx:202-217`) prova essa parte. A redação anterior desta linha creditava as três coisas como novas; duas não eram. |
| Guarda de endereço `http://` preservada | FEITO (já existia, migrada e agora testada em navegador) | `alert-intake.tsx:79-95` (`UNSAFE_SCHEME`, `schemeOf`) — mesma construção do `screens/data.tsx` removido. `settings-data.spec.ts:90-106` prova em build de produção que a página nunca imprime um endereço não cifrado. |
| Emissão de token de entrega contextual | **PARCIAL — decisão registrada** | O controle está na página de intake, agrupado com a permissão a que é escopado (`alert-intake.tsx:338-360`), e não numa tela de tokens separada. **Não é por receptor**, e não deve ser: `delivery_permission` vem do nível da coleção (`text(dataOf(receivers), 'delivery_permission')`), é uma permissão do deployment, e um token emitido por receptor sugeriria que o token é específico daquele receptor, o que é falso. A letra do requisito ("contextual ao receptor") não está cumprida; a substância ("a ação existe onde ela é usada") está. Fechar a letra exigiria um token por receptor que o servidor não modela. Mesma classe do FR-006 da 020 e da 040. |
| Simulação acessível do detalhe do receptor | FEITO — e melhor que antes | `alert-intake.tsx:302-320`: `RuleSimulator` agora vive **dentro do detalhe de cada receptor**, com `sources={[name]}` — antes era um simulador único no rodapé do painel com um seletor de origem. Ausente, não desabilitado, para quem não tem `config.write` (`may(viewer, WRITE)`). |
| Rastro "para onde foi" com conteúdo real | FEITO (já existia, migrado) | `Provenance` + `chainOf` em `alert-intake.tsx`, construídos do ledger que a página já leu, sem uma consulta por receptor. Unitário cobre as quatro perguntas (regra, time, run, e o caso "não há nada a rastrear"). |
| Regras de roteamento preservadas, com a catch-all sempre desenhada | FEITO (já existia, migrado) | `alert-intake.tsx`, testids `routing-rules` e `catch-all-rule`. Navegador: `settings-data.spec.ts:115-122`. |
| Presets de frequência gerando o cron, campo editável | FEITO | `cronFromPreset` (`console/src/surfaces/schedules.tsx:94-123`), seletor em `:642+`, com o campo de dia aparecendo só em `weekly`. Puro e testado sem navegador: `console/tests/unit/surfaces/schedule-presets.test.ts` (8 casos). Navegador: `settings-data.spec.ts:173-190` — escolher "weekly" produz `0 8 * * 1`, o campo segue editável, e trocar para "daily" produz `0 8 * * *`. |
| Prévia das próximas execuções no fuso | FEITO (já existia, verificado) | `requestCronPreview` (`schedules.tsx`) faz `POST` com `operation: 'preview'` e lê `answer.firings` — **a prévia é do servidor**, não de biblioteca local. O `plan.md` afirmava o contrário; a afirmação é falsa e o mecanismo existente é o correto, porque o servidor é dono da semântica de cron. **Não exercitável ponta a ponta contra o mock** — ver §4. |
| Validação inline com exemplo | FEITO (já existia, verificado) | A recusa do deployment é exibida exatamente como veio (`CronPreview` com `status: 'refused'`), e o texto de ajuda do campo cron traz o exemplo. Esta feature não inventou uma segunda opinião sobre sintaxe de cron. |
| Lista de agendas: **frequência legível** | FEITO — **feito pelo orquestrador, era a lacuna** | Estava por fazer: a lista mostrava só o cron cru (`labels.column.cron`), e a frase da FR-005 é uma enumeração cujo **primeiro** substantivo tinha ficado para trás enquanto os outros três foram entregues. `frequencyOfCron` (`schedules.tsx:164-192`) e `readableFrequency` (`:194-211`), renderizado em `:594-606` com testid `schedule-frequency`. **Vermelho visto**: `npx vitest run tests/unit/surfaces/schedule-presets.test.ts` → `TypeError: frequencyOfCron is not a function`, 5 casos falhando, antes da implementação. Verde depois: 13. Rendido, não só a função pura: `console/tests/unit/surfaces/schedules.test.tsx` (5 casos novos, inclusive "segue o rascunho enquanto está sendo editado" e "não diz nada sobre uma expressão que preset nenhum escreveria"). Navegador: `settings-data.spec.ts:160-171`. |
| Lista de agendas: próxima execução, estado, habilitar/desabilitar inline | FEITO (já existia, verificado) | Colunas `nextRun` e `enabled` e o `toggle-schedule` já estavam em `schedules.tsx` antes desta feature; cobertos por `schedules.test.tsx` pré-existente. |
| Destinos com estado da integração subjacente e degradação visível | FEITO | `schedules-destinations.tsx:263-300` — `destination-unusable` com a razão, e `destination-credential-link` apontando para o painel da credencial que resolveria. Navegador: `settings-data.spec.ts:135-146`. |
| **O defeito de CTA, fechado** | FEITO | O caminho em que o próprio deployment diz que nada pode entregar mensagem agora aterrissa em `/integrations?category=communication`: `resolveCta` é montado em `schedules-destinations.tsx:235-238` e consumido em `:256-261` (`href: catalogueCta.href`, linha 260). O `href: '/configuration'` que sobra em `:252` é o **outro** ramo — o empty state genérico de setup incompleto, que continua correto por §5. A categoria é `communication`: `chat` não existe no catálogo (`integrations/_catalogue/entry.py:53`). **Vermelho visto de verdade**: reintroduzi o `href: '/configuration'` na árvore, rodei, vi 2 dos 3 casos falharem (`expect(href).not.toContain('/configuration')` e o `toHaveURL`), e restaurei — arquivo conferido idêntico ao backup depois. Prova permanente: `console/tests/first-day/settings-data-empty.spec.ts`, 3 casos, contra build de produção. |
| Empty state pelo componente da 001 | FEITO | `EmptyState` via `PanelEmpty`; o corpo é a frase do próprio deployment (`NO_DELIVERY_CHANNEL_REASON`, `config/constants/transit.py:170-173`), que já dizia "no catálogo" enquanto o botão ia para o editor de schema. Texto e botão agora concordam — que era o defeito. |
| Sem `view=` no CTA | FEITO | `settings-data-empty.spec.ts:47` afirma a ausência. `view=` estreitaria para o que já está conectado ou sugerido, que num deployment sem nada é exatamente nada. |
| Altura ≤ 2 viewports (1080p) | FEITO — medido | Ambas as rotas adicionadas a `console/tests/e2e/scroll-budget.spec.ts:82-87` e **medidas**: passam. `/autonomy` falha a 2208px contra 2160px — **pré-existente**, os mesmos 48px já registrados como item aberto da 040, e esta feature não tocou naquele arquivo. |
| Dissolução: redirects de `?tab=` de Signals | FEITO (já valia, verificado) | `console/src/shell/routes.ts:701-704` já tinha as quatro entradas antes desta feature. |
| Dissolução: `screens/data.tsx` removida | FEITO | Removido, junto de `console/tests/unit/surfaces/{data,ingress}.test.tsx`. Auditoria de cobertura em §3. |
| Dissolução: `screens/signals.tsx` removida | **DELIBERADAMENTE NÃO** — ver §5 | A task pedia a remoção. Removê-la derrubaria a observação contínua, que não tem página de destino nesta onda. `signals.tsx` foi **reduzida** a servir só isso (`signals.tsx:22-31`), sem a moldura de abas que quatro abas justificavam e uma não. |
| Registro visual reconciliado | FEITO (parcial por decisão) | `console/visual/screens.json`: `signals-1440-light` → `/settings/alert-intake`; `signals-schedules-1440-light` e `signals-destinations-1440-light` → `/settings/schedules-destinations`. **`signals-observation-1440-light` intocada** — é `baselined` e o endereço dela continua existindo. As três seguem `pending`, com o `pending_because` reescrito para o motivo verdadeiro. Nenhum `.png` tocado; `make console-visual-accept` nunca rodado. Ver §5 sobre as duas entradas que agora nomeiam um endereço só. |
| Varredura de vocabulário e de identificadores | FEITO | Sete identificadores de requisito vazaram para arquivos commitáveis (`schedules.tsx`, `scroll-budget.spec.ts`, `alert-intake.tsx`, `settings-alert-intake.test.tsx` ×3, `schedule-presets.test.ts`) — um deles com uma frase em português copiada da spec. Todos reescritos com a substância. Varredura final nos arquivos da feature e nas linhas adicionadas do diff: limpa. Nenhum europeísmo nas strings pt-BR novas. |
| Insumo de paridade para a 070 | INFORMATIVO | Ver §5. |

## 2. Gates — números reais, medidos pelo orquestrador

| Gate | Resultado |
|---|---|
| `npx tsc --noEmit` | **EXIT=0** |
| `npx eslint .` | **EXIT=0** |
| `npx prettier --check .` | **EXIT=0** |
| `npx vitest run` | **2205 passed, 138 arquivos** (baseline da onda: 2176/137) |
| `spec_validation browser --test tests/e2e/settings-data.spec.ts` | **12 passed**, build de produção real |
| `spec_validation browser --project first-day --scenario first-run --test tests/first-day/settings-data-empty.spec.ts` | **3 passed**; vermelho confirmado revertendo o conserto |
| `spec_validation browser --test tests/e2e/scroll-budget.spec.ts` | **10 passed, 1 failed** — a falha é `/autonomy`, pré-existente (§4) |
| `pytest tests/contract/console/` | **308 passed** (visual-regression excluído) — ver §2.1 e §2.2 |
| `make verify` | **NÃO RODADO** como alvo composto — devido no fim da onda. Enquanto a divergência visual estiver aberta ele sai 2 antes do pytest. |

### 2.1 Um vermelho que foi meu, e o conserto

A primeira rodada de `pytest tests/contract/console/` deu **4 failed, 304
passed**, todas em `test_console_gate.py`. Eram minhas, dos dois specs
Playwright que eu tinha acabado de escrever: formatação prettier, e um `eslint`
recusando o literal `'http://'` no meu teste — a regra "sem origem de terceiros
na fonte do console", exatamente a propriedade que o teste existia para provar.
Reescrito com a mesma construção por partes que a própria tela usa. Depois:
`test_console_gate.py` **16 passed**.

### 2.2 Uma segunda falha, também minha, e também não um defeito

A rodada seguinte deu **1 failed, 307 passed**, em
`test_a_seeded_failure_fails_its_check_and_says_where[lint0]`. Causa: eu tinha
posto `tests/contract/console/` para rodar em segundo plano e, sem esperar,
iniciei uma segunda rodada em primeiro plano. `test_console_gate.py` **semeia
arquivos de falha na árvore de trabalho e os remove depois**; duas rodadas
simultâneas disputam os mesmos arquivos. Rodado sozinho, sem nada em paralelo:
**16 passed**. Total real: **308 passed**.

É a quarta vez nesta onda que uma suíte que escreve na árvore, rodada em
paralelo com outra coisa, produz uma falha fantasma. A regra existia, estava
escrita, e mesmo assim foi eu quem a quebrou — registrado aqui porque a versão
útil dessa regra não é "não rode em paralelo", é "não inicie a segunda rodada
sem confirmar que a primeira terminou".

### 2.3 O que a verificação independente corrigiu

Veredito: **PASS**, com três achados, nenhum deles no produto. Dois eram meus,
neste arquivo, e estão corrigidos acima:

1. **Citação errada no conserto do CTA.** Eu tinha citado
   `schedules-destinations.tsx:227-230, 248-253`. As linhas haviam deslocado
   oito posições quando inseri os rótulos de `frequencyText` acima daquela
   região, e uma das faixas que citei era o **ramo oposto**, o que ainda aponta
   para `/configuration` de propósito. Comportamento sempre esteve certo — o
   teste de reprodução prova; a citação é que apontava para o lugar errado.
   Lição: reler o `file:line` **depois** da última edição do arquivo, não antes.
2. **Novidade superestimada no chip de recusa.** Ver a linha corrigida em §1.
3. Uma asserção sem substituto, registrada em §4.

O verificador também declarou um efeito colateral próprio: rodou
`tools.mockplane build` para confirmar que a fixture de destinos foi gerada e
não editada à mão (foi — saiu byte a byte igual), o que reescreveu
`fixtures/scenarios/populated/tokens.json` por não-determinismo de relógio
naquele gerador, e restaurou o arquivo. Conferi: `tokens.json` está limpo e a
árvore segue com os mesmos 29 caminhos.

## 3. Auditoria das deleções — a aritmética conferida

Dois arquivos de teste removidos, e um total que sobe não é prova de que nada
se perdeu (a 050 escondeu uma regressão real exatamente assim). Contados um a
um:

| | Casos |
|---|---|
| Removidos: `data.test.tsx` | 31 |
| Removidos: `ingress.test.tsx` | 6 |
| **Total removido** | **37** |
| Novo: `settings-alert-intake.test.tsx` | 27 |
| Novo: `settings-schedules-destinations.test.tsx` | 15 |
| Novo: `schedule-presets.test.ts` | 13 |
| **Total novo** | **55** |

As seis propriedades de `ingress.test.tsx` foram conferidas nominalmente contra
a nova suíte: listar todo receptor, o endereço inteiro e não um caminho a
montar, o corpo que cada um interpreta, como a entrega é confiada, o deployment
sem nada conectado, e "não desenha endereço colável quando o deployment não
responde por ele" — esta última é a guarda de `http://`, que a nova suíte cobre
em dois casos dedicados. `DeliveryToken` continua coberto por
`console/tests/unit/surfaces/delivery-token.test.tsx`, arquivo **pré-existente
e não modificado** (confirmado por `git ls-files`), que não fazia parte de
nenhum dos dois removidos.

## 4. Itens abertos e impossibilidades declaradas

- **A prévia de cron não é exercitável ponta a ponta contra o mock.** O gateway
  implementa `POST /v1/schedules/preview` (`gateway/http/routes/schedules.py:125`),
  mas o mock plane não tem registro para ela: durante a rodada do navegador a
  chamada respondeu **404** duas vezes, e nenhuma fixture carrega `firings`.
  **Pré-existente** — o mecanismo de prévia já estava na árvore antes desta
  feature. Coberto no nível de componente. Dono: quem mantém `tools/mockplane/`.
  Mesma classe das duas impossibilidades declaradas pela 030.
- **`/autonomy` excede o orçamento de rolagem em 48px** (2208 contra 2160).
  Pré-existente, já registrado como item aberto da 040, e nenhum arquivo daquela
  tela foi tocado aqui.
- **Declarar um destino** e **enviar mensagem de teste**: fora de escopo por
  decisão do operador (2026-08-16). Não existe rota de escrita para destinos —
  um destino é `transit.destinations`, configuração — e não existe endpoint de
  teste de envio em lugar nenhum. Donos: a 070, para o primeiro; um trabalho de
  gateway ainda não agendado, para o segundo.
- **SC-001** (menos de 5 minutos conectando um Alertmanager real) e **SC-003**
  (menos de 1 minuto criando uma agenda com preset) são critérios de
  usabilidade humana. **Não são verificáveis por agente e não são
  reivindicados.** A estrutura que os torna possíveis está entregue e testada.
- **Token de entrega por receptor**: ver a linha PARCIAL em §1.
- O caso de borda "agenda cujo objetivo referencia capacidade que o deployment
  não tem" não tem teste dedicado e não foi construído. Não reivindicado.
- **Uma asserção perdida na migração**, achada pelo verificador e não por mim:
  o `detectors.test.tsx` removido tinha `'explains what the section is for'`,
  sobre o texto de `schedules.caption`. Não há equivalente na suíte nova. A
  copy continua sendo renderizada (`schedules-destinations.tsx:129-131`), então
  nada regrediu em comportamento — mas a auditoria de §3, que confirmou
  propriedade por propriedade as seis de `ingress.test.tsx`, não cobriu as de
  `detectors.test.tsx` com o mesmo rigor. É uma lacuna da minha auditoria, não
  do produto.

## 5. Duas decisões que contrariam a letra das tasks

**`screens/signals.tsx` não foi removida.** A task pedia. A própria `spec.md`
desta feature diz, nas Assumptions, que a observação contínua fica fora; a 010
deixou `/signals?tab=observation` deliberadamente fora da tabela de redirects
(`routes.ts:686-694`) e o arquivo de rota trata esse caso explicitamente
(`console/src/app/(shell)/signals/page.tsx:29-32`); e
`signals-observation-1440-light` é a única das quatro entradas visuais de
signals com baseline aceito. Remover o arquivo derrubaria a observação contínua
e quebraria um baseline aceito, para satisfazer uma task que contradiz o
documento que a gerou. A remoção final é da 070, quando a observação tiver
destino.

**As duas entradas visuais de schedules/destinations agora nomeiam o mesmo
endereço.** É a consequência honesta de duas abas terem virado uma página. Não
apaguei nenhuma: apagar orfana o PNG commitado e
`test_no_baseline_belongs_to_a_screen_nobody_registered` fica vermelho.
Consolidá-las em uma entrada é uma decisão que pertence à revisão que aceitar
esses pixels, não a esta feature. Registrado no `pending_because` das duas.

**Insumo para a 070.** Os grupos de schema que estas páginas passam a ter tela
de operador para *ler*: `transit.rules`, `transit.destinations` (leitura e
estado; a escrita continua no editor cru) e as agendas via `/v1/schedules`. O
editor cru continua sendo o único lugar onde uma regra de roteamento ou um
destino é **declarado** — e é por isso que o CTA de regras em
`alert-intake.tsx` continua apontando para `/configuration` de propósito: até a
070, é lá que a ação acontece, e mandar para o catálogo seria mentir. Não
existe arquivo de checklist de paridade na árvore para atualizar; fica
registrado aqui.
