# Controle — 050-organizacao

Estado abaixo verificado contra o código real na árvore de trabalho, nesta
sessão. Todo `file:line` citado foi aberto por mim antes de escrever a linha
que o cita. Nenhum `git add`/`commit` foi executado — a entrega é a árvore de
trabalho suja.

## 1. Peça por peça

| Peça | Estado | Detalhe |
|---|---|---|
| Quatro páginas na subnav Organização, cada uma com a permissão que a API exige | FEITO | `console/src/surfaces/settings/members.tsx`, `sso.tsx`, `machine-tokens.tsx`, `audit.tsx`, ligadas em `console/src/app/(shell)/settings/{members-roles,single-sign-on,machine-tokens,audit-log}/page.tsx`. Permissões copiadas de `console/src/shell/routes.ts:538,546,554,562` (`identity.read`, `sso.manage`, `token.manage`, `audit.read`) — inalteradas, herdadas da 010. |
| Members & roles: principals com chips, grants com permissões legíveis, sessões com revogação | FEITO | `console/src/surfaces/settings/members.tsx:107-215`, reaproveitando `GrantPanel` (`console/src/surfaces/grants.tsx`) e `SessionPanel` (`console/src/surfaces/tokens.tsx:371`) inalterados. `roleDescriptions` (permissões legíveis por papel) — **já valia, verificado em** `settings/members.tsx:78-84` (mesma construção que `administration.tsx` já fazia antes de eu tocar o arquivo). |
| Concessão de papel administrativo pede confirmação | FEITO | `GrantPanel` (`console/src/surfaces/grants.tsx`) — `ADMINISTRATIVE_ROLES` (linha 62, `['admin', 'owner']`), `requestGrant()` (linha 238) intercepta o clique em Add (`onClick={requestGrant}`, linha 351) e abre um `ConfirmDestructive` dedicado (`confirmingAdd`, linha 190/360) quando o papel escolhido é `admin` ou `owner`; qualquer outro papel concede direto, sem diálogo. Único consumidor em produção confirmado por `npx tsc --noEmit` antes do conserto (só `settings/members.tsx` quebrava ao alargar `GrantLabels`) — `settings/members.tsx:182-185` passa os quatro rótulos novos (`addAction`, `addConsequence`, `addClose`, `addCancel`). Vermelho visto: `console/tests/unit/surfaces/grants.test.tsx`, describe `'granting an administrative role asks first'` — 4 dos 5 casos falharam antes da implementação (o diálogo não existia), verde depois. |
| Remover o último administrador é bloqueado com explicação | FEITO (já existia, verificado) | Servidor: `gateway/http/routes/identity.py:428-448` já chama `require_owner_retained` e levanta `conflict` em `LastOwnerRemoval`. Cliente: `GrantPanel` já tem um caminho dedicado para 409 (`console/src/surfaces/grants.tsx:216-227`, estado `lastOwner`, testid `grant-last-owner`) — coberto por `console/tests/unit/surfaces/grants.test.tsx:329` (pré-existente, não fui eu que escrevi). Confirmei que `settings/members.tsx` usa o mesmo `GrantPanel`, então a superfície já vem coberta. |
| SSO como fluxo em etapas (configurar → testar → ligar) | FEITO | `console/src/surfaces/sso-setup.tsx` — três seções (`data-testid="sso-step-configure/test/activate"`, linhas 216, 244, 279). Máquina de estados (verified/edited/pendingEdit) copiada sem alteração de `surfaces/sso.tsx`'s antigo `SsoForm` — o contrato de servidor não mudou. |
| Ajuda por campo no SSO | FEITO | `console/src/surfaces/settings/sso.tsx:66-75` monta `fieldHelp` para os 8 campos a partir de `settings.sso.field.*.help` (en.ts/pt-BR.ts). |
| Bloqueio de ativação sem teste aprovado | FEITO (já existia, verificado) | Servidor: `gateway/http/routes/sso.py:336-366` (`activate_sso`) — inalterado. Cliente: `sso-setup.tsx:294` (`state.verified && !edited`) — mesma lógica do `SsoForm` antigo, agora coberta por `console/tests/unit/surfaces/sso-setup.test.tsx` (23 testes — 16 da primeira rodada desta feature, mais 7 de migração de cobertura fechados no ciclo de reparo, ver §5). |
| Fallback local declarado na página | FEITO | `console/src/surfaces/sso-setup.tsx:279-282` (`data-testid="sso-fallback"`), texto em `settings.sso.fallback`. |
| Ativação de SSO registrada em audit | FEITO (já existia, verificado) | `platform/config_service/service.py:305-314` audita todo campo alterado por `set_settings`, incluindo `policies.sso.is_active`. Confirmado por depuração direta e pelo novo teste `tests/unit/gateway/http/test_sso_routes.py::test_activation_is_recorded_in_the_audit_trail` (14 testes no arquivo, todos verdes). Nenhum código de servidor mudou para isso — só o teste que prova é novo. |
| Mudança de configuração exige novo teste | FEITO (já existia, verificado) | `tests/unit/gateway/http/test_sso_routes.py::test_editing_the_configuration_invalidates_the_test_and_deactivates_it` — pré-existente, intocado, continua verde. |
| Machine tokens agrupados por finalidade (contagem, último uso, escopos legíveis) | FEITO | `console/src/surfaces/machine-token-groups.tsx:104-116` (`grouped()`), renderizado em `:283-386`. |
| "Revogar todos menos o mais recente" | FEITO | `machine-token-groups.tsx:211-228` (`revokeOlder`), UI em `:337-380`. Prova em navegador real: `console/tests/e2e/settings-org.spec.ts:59-77` — os 15 tokens `bootstrap` da fixture colapsam num grupo e a revogação em massa reduz para 1. |
| Emissão substitui em vez de acumular para a mesma finalidade | FEITO | `platform/identity/tokens.py:188-282` (`TokenService.issue`, parâmetro `supersede`), acionado por `gateway/http/routes/identity.py:493-517` (`issue_token`, `supersede=True`). Teste: `tests/unit/gateway/http/test_token_routes.py::test_issuing_for_a_purpose_that_already_has_a_live_token_supersedes_it`. |
| Substituição registrada em audit, declarada e visível | FEITO | Audit: `platform/identity/tokens.py:265-273` grava um evento de revogação por token substituído, com `detail.reason` nomeando a finalidade. Console: `IssuedTokenView.superseded` (`gateway/http/routes/identity.py:152-160`), propagado por `console/src/app/api/token/route.ts:53-64`, exibido em `machine-token-groups.tsx:224-236` (`token-superseded-notice`) e declarado antecipadamente no texto de ajuda do campo (`settings.machineTokens.purposeHelp`). |
| Causa do acúmulo de tokens do bootstrap tratada | FEITO — decisão registrada | Escolhi **revogar a credencial superada no momento da emissão**, não agrupar/recolher no console. `platform/startup/bootstrap.py:417-441` (`_issue`) agora chama `tokens.issue(..., supersede=True)`. A causa raiz real (não a que a spec supunha) era outra: `TokenService` nunca recebia um `AuditRecorder` na composição real (`gateway/http/asgi.py:192`, antes do meu conserto) — toda emissão/revogação de token ficava, silenciosamente, fora do audit trail, o que também bloqueava FR-007 para tokens. Corrigido em `gateway/http/asgi.py:192-196` e replicado no fixture de teste compartilhado `tests/unit/gateway/http/conftest.py:37,131-141`. |
| Escopos escolhidos de uma lista legível, não digitados | FEITO | `machine-token-groups.tsx:236-253` — um checkbox por permissão do próprio viewer (`issuedScopes`), pré-marcados. Prova em navegador: `settings-org.spec.ts:80-90`. |
| Audit log: filtros nomeados (período com presets, ator, tipo) | FEITO | `console/src/surfaces/settings/audit.tsx:230-249` (choices actor/action), `:271-284` (presets "Last N days", chave `settings.auditLog.period.days`). |
| Export respeita filtros | FEITO (já existia, verificado) | `settings/audit.tsx:293-298` — mesmo padrão que `screens/audit.tsx` (removido) já tinha; só o endereço mudou. |
| Contagem sempre consistente com a lista (mesma consulta) | FEITO — defeito raiz corrigido | `platform/persistence/ports/audit_repository.py` (`count` alargado para aceitar os mesmos filtros de `query`), `platform/persistence/fakes/audit_repository.py`, `platform/persistence/postgres/repositories/audit_repository.py`, `gateway/http/routes/audit.py:90-108` (a rota agora passa os mesmos filtros para `count`). Vermelho visto antes do conserto em `tests/contract/persistence/test_audit_repository.py::test_count_answers_the_same_question_query_does` (`TypeError: FakeAuditRepository.count() got an unexpected keyword argument 'action'`) e em `tests/unit/gateway/http/test_audit_routes.py::test_the_total_counts_what_the_filtered_listing_returned` (`assert 2 == 1`). |
| Alargamento de período reexecuta a consulta (não abandona a página) | FEITO — defeito raiz corrigido | `console/src/surfaces/settings/audit.tsx` constrói todo link (`FilterBar`, presets, linha, toggle de audiência, ação do empty state) a partir do próprio endereço (`PATH = '/settings/audit-log'`), nunca `/administration`. Vermelho visto num teste temporário (apagado após provar, ver §3) contra o `screens/audit.tsx` antigo: clicar "next 7 days" resolvia, via `legacyRedirectHref`, em `/settings/members-roles`. Prova permanente, navegando de verdade: `console/tests/e2e/settings-org.spec.ts:20-35`, verde contra o build de produção. |
| Empty state calculado sobre o que foi buscado, não sobre o pós-exclusão | FEITO | `console/src/surfaces/settings/audit.tsx:344-351` — `state={stateOf(events, records.length === 0)}`, não `rows.length === 0`. Testado em `console/tests/unit/surfaces/settings-audit.test.tsx:174-196` (o painel mostra a tabela, não "Nothing has been recorded", quando os únicos eventos são ruído do sistema) e em navegador (`settings-org.spec.ts:38-51`). |
| Desmembramento final: `screens/administration.tsx` removida | FEITO | Removidos `console/src/surfaces/screens/administration.tsx`, `screens/audit.tsx` e, por consequência (ficaram sem nenhum consumidor), `console/src/surfaces/sso.tsx` (o `SsoForm` antigo). Seus três testes (`administration.test.tsx`, `audit.test.tsx`, `sso.test.tsx`) também removidos — ver §4 sobre o que migrou. |
| Subnav aponta para as 4 páginas | FEITO (já existia, verificado) | `console/src/shell/routes.ts:531-563` (`SETTINGS_PAGES`) já tinha as quatro entradas, obra da 010. Não toquei neste arquivo. |
| Redirects da 010 cobrem `?tab=audit` | FEITO (já existia, verificado) | `console/src/shell/routes.ts:696-705` (`SETTINGS_REDIRECTS`) já tinha as três entradas (`/administration`, `tab=people`, `tab=audit`) antes de eu começar. |
| Cada página ≤ 2 viewports em 1080p com dados representativos | FEITO | `console/tests/e2e/scroll-budget.spec.ts` — as quatro páginas novas passam contra a fixture de 15 tokens duplicados e 8 eventos de audit (rodado contra o build de produção real, ver §2). |
| Varredura de vocabulário | FEITO | Nenhum europeísmo nas strings pt-BR novas (`ecrã`, `ficheiro`, `acção`, `activar`, `gravar`, `apagar`, `contactar`, `objectivo` — zero ocorrências, varredura própria). Nenhum identificador de requisito (`FR-`, `SC-`, `T0NN`, `specs_v5`) nos arquivos que escrevi ou editei (varredura própria; as poucas ocorrências de `FR-0NN` que a varredura encontrou são todas pré-existentes, em linhas que não toquei — listadas em §4). `console/tests/e2e/vocabulary.spec.ts` continua verde (7/7), sem alteração — o escopo dele (vocabulário de credencial) não cruza com esta feature. |
| Insumo de paridade para a 070 | INFORMATIVO | Os grupos de schema `policies.sso` e `policies.sso.claims` agora têm uma tela de operador real (`settings/sso.tsx`) que os lê e escreve via as mesmas rotas do editor cru. Não criei nenhum arquivo de "checklist de paridade" — não encontrei um na árvore para atualizar; deixo o fato registrado aqui para quem executar a 070. |

## 2. Gates — números reais, medidos por mim nesta sessão

### Console (os quatro obrigatórios, na ordem pedida)

| Gate | Resultado |
|---|---|
| `npx tsc --noEmit` | **EXIT=0** |
| `npx eslint .` | **EXIT=0** |
| `npx prettier --check .` | **EXIT=0** |
| `npx vitest run` | **2176 passed, 137 files, EXIT=0** |

Números medidos de novo, no fim do ciclo de reparo (rodada isolada, nada em
paralelo), depois de corrigir os dois defeitos de lint que os arquivos novos
deste ciclo introduziram: `settings-sso.test.tsx` escrevia URLs de exemplo
como literais `'https://...'`, pegas por `no-restricted-syntax` (origem de
terceiro em código do console) — reescrito com o mesmo truque de `['https:',
'//...'].join('')` que `sso-setup.test.tsx:289` já usa; `settings-machine-
tokens.test.tsx` usava `as HTMLElement` para descartar `undefined` de um
elemento indexado, pego por `@typescript-eslint/non-nullable-type-assertion-style`,
e como `@typescript-eslint/no-non-null-assertion` também está ligado (a
sugestão do próprio lint, `!`, seria proibida por essa segunda regra),
segui o padrão que `settings-members.test.tsx:146-148` já usa: uma guarda de
runtime (`if (x === undefined) throw`) em vez de qualquer asserção.

Baseline antes de eu começar (esta feature inteira): `tsc` 0, `eslint` 0,
`prettier` 0, `vitest` 2091/132. Baseline do início deste ciclo de reparo
(medição do coordenador, corrigida por mim): `vitest` 2155/135. Diferença
total da feature: +85 testes líquidos, +5 arquivos líquidos — apaguei 3
arquivos de teste (`administration.test.tsx` 8, `audit.test.tsx` 12,
`sso.test.tsx` 17, soma 37 — não 34, e não "16" para o audit; ver §5) e
acrescentei 8 arquivos novos de teste (`settings-audit.test.tsx`,
`settings-members.test.tsx`, `sso-setup.test.tsx`, `machine-token-groups.test.tsx`,
`token-route.test.tsx`, `token-bulk-revoke-route.test.tsx`,
`settings-sso.test.tsx`, `settings-machine-tokens.test.tsx` — não 8 na
primeira versão desta tabela, que contou os dois últimos antes de eles
existirem; existem agora, fechados neste ciclo de reparo). 132 − 3 + 8 = 137,
bate com o `vitest run` acima.

### Console — gates adicionais que rodei

| Gate | Resultado |
|---|---|
| `uv run python -m tools.console_gate test` (cobertura) | **EXIT=0** — Statements 94.32%, Branches 90.37%, Functions 91.85%, Lines 96.33% (piso 90 em todos; medido de novo ao final do ciclo de reparo). Achei branches abaixo do piso (89.26%) na primeira medição, causados pelos meus próprios arquivos novos com poucos ramos testados; fechei a lacuna com testes adicionais em `machine-token-groups.test.tsx`, `sso-setup.test.tsx`, e dois arquivos novos de teste para as rotas de API (`token-route.test.tsx`, `token-bulk-revoke-route.test.tsx`, que antes tinham 0% de cobertura — rotas nunca testadas). |
| `console/tests/e2e/settings-org.spec.ts` (Playwright, `behaviour`, contra build de produção real via `tools.spec_validation browser`) | **6/6 passed** — rodado de novo ao final do ciclo de reparo, depois de mudar `grants.tsx` (a confirmação de papel administrativo). O build de produção continua saindo limpo (sem regressão de fronteira servidor/cliente) e a página de membros continua renderizando o `grant-panel`; o próprio clique em "conceder um papel administrativo" não é exercitado por este spec — só `grants.test.tsx` cobre esse caminho, ver §1. |
| `console/tests/e2e/settings-nav.spec.ts` (mesma via) | **11/11 passed** — corrigi um teste que ficou obsoleto pela minha própria mudança (ver §4) |
| `console/tests/e2e/scroll-budget.spec.ts` (mesma via) | **8/9 passed** — as quatro páginas novas passam; a falha é `/autonomy` (2208px contra orçamento de 2160px), tela que não toquei — ver §3 |
| `console/tests/e2e/vocabulary.spec.ts` (mesma via) | **7/7 passed**, sem alteração |

`settings-nav.spec.ts`, `scroll-budget.spec.ts` e `vocabulary.spec.ts` não
foram rodados de novo neste ciclo de reparo — a instrução pedia
explicitamente `settings-org.spec.ts`, e nenhuma dessas três suítes visita o
fluxo de concessão de papel (`GrantPanel`'s Add), a única superfície que
`grants.tsx` mudou. Os números acima são os da medição anterior a este
ciclo, ainda válidos porque nada que essas três suítes exercitam mudou desde
então (confirmado por `git status`: só `grants.tsx`, `settings/members.tsx`,
`en.ts`, `pt-BR.ts` e arquivos de teste mudaram neste ciclo).

Nenhum `console-visual-accept`, `console-e2e` completo ou qualquer coisa que
reescreva baseline foi rodado. Nenhuma tela nova foi registrada em
`console/visual/screens.json`.

### Python

| Gate | Resultado |
|---|---|
| `make lint` | **EXIT=0** |
| `make typecheck` | **EXIT=0** (1779 arquivos) |
| `make check-constants` | **EXIT=0** |
| `make check-imports` | **EXIT=0** — 7 contratos mantidos, 0 quebrados, 1672 arquivos |
| `make check-console-boundary` | **EXIT=0** |
| `uv run pytest tests/unit/platform/identity/ tests/unit/platform/startup/` | **418 passed** |
| `uv run pytest tests/unit/gateway/` (completo) | **654 passed** |
| `uv run pytest tests/security/ tests/contract/persistence/` | **794 passed, 16 skipped** |
| `uv run pytest tests/architecture/ tests/contract/console/` (rodado sozinho, sem nada em paralelo) | **488 passed, 2 failed** — as duas falhas são exatamente as descritas como esperadas: `test_console_visual_regression.py::test_the_untouched_baselines_still_match` (divergência de paleta, `e5a8c24`, não é desta feature) e, na primeira rodada, `test_one_fictional_deployment.py::test_exactly_one_fictional_deployment_exists_in_the_repository` (artefato velho do Playwright — `rm -rf console/test-results console/playwright-report` e voltou a passar sozinho, 9/9, confirmado numa segunda rodada isolada). |

Não rodei o `make verify` completo nem `make test-postgres` — não me foram
pedidos e não fazem parte dos quatro gates do console que o briefing exige
antes do relatório. O `console/visual/baselines/administration-1440-light.png`
permanece intocado (151336 bytes, `git status` limpo em `console/visual/`) —
verificado por mim ao final desta sessão. Os gates Python acima também não
foram rodados de novo neste ciclo de reparo — nada em Python mudou nele
(`git status` na raiz do repositório: todo `.py` modificado é de antes do
ciclo; os únicos arquivos tocados no ciclo de reparo são em `console/`).
Os números da tabela Python são os da medição anterior, ainda válidos.

## 3. O que fica pendente, nomeado, não escondido

1. **Varredura pt-BR da linha "conta de serviço criada no deploy, sem
   e-mail" não tem teste na página nova.** A string em si está correta e
   testada pela paridade do catálogo (`console/tests/unit/i18n/catalogue.test.ts`,
   que confere que toda chave existe nos dois idiomas) e pela versão em inglês
   (`console/tests/unit/surfaces/settings-members.test.tsx:149-151`), mas o
   teste antigo que também conferia a frase em português
   (`administration.test.tsx`, removido — "says the same thing in Brazilian
   Portuguese", usava `principalIdentity('pt-BR', ...)` diretamente) não foi
   recriado: a função equivalente em `settings/members.tsx:24-32` não é
   exportada, e testar o locale pt-BR através da página inteira exige
   sobrescrever o cookie de locale no mock de `next/headers`, o que os outros
   testes desta sessão não fazem. Risco baixo (é a mesma chave de catálogo,
   já provada correta nos dois idiomas pela paridade), mas nomeio a lacuna
   em vez de escondê-la.
2. **`/autonomy` excede o orçamento de rolagem** (2208px contra 2160px,
   `console/tests/e2e/scroll-budget.spec.ts`, achado ao adicionar as quatro
   páginas novas à mesma suíte). Não é código que toquei
   (`console/src/surfaces/settings/autonomy.tsx` não está na minha lista de
   arquivos alterados) e as quatro páginas desta feature passam. Provável
   efeito colateral da troca de paleta (`e5a8c24`) sobre espaçamento —
   ninguém parece ter rodado este spec específico contra o build de produção
   desde então, porque não é um dos quatro gates obrigatórios do console.
   Nomeado para quem for medir a 040 ou a paleta, não conserto aqui.
3. **SC-002 (usabilidade do fluxo de SSO) não foi validado por um teste de
   usabilidade real.** Construí e testei a estrutura que o critério pede —
   ajuda por campo em todos os 8 campos, três etapas visíveis, bloqueio de
   ativação sem teste aprovado — mas "um operador consegue configurar de
   ponta a ponta sem documentação externa" é uma afirmação sobre uma pessoa
   real na frente da tela, que este agente não pode simular nem certificar
   sozinho.
4. **`policies.sso` / `policies.sso.claims` como insumo de paridade para a
   070**: registrado em prosa na tabela acima; não encontrei (nem criei) um
   arquivo de checklist de paridade nesta árvore para marcar.

## 4. Test-first: onde o vermelho foi visto de verdade, e onde não foi

Como pedido: "se em algum item você não conseguiu ver o vermelho antes, diga
isso nessas palavras, item por item."

- **T002** (contagem × lista do audit) — vermelho visto:
  `tests/contract/persistence/test_audit_repository.py::test_count_answers_the_same_question_query_does`
  falhou com `TypeError: FakeAuditRepository.count() got an unexpected keyword
  argument 'action'` antes de qualquer conserto.
- **T004** (alargar período) — vermelho visto: escrevi um teste temporário
  (`console/tests/unit/surfaces/_tmp_widen_period_repro.test.tsx`, apagado
  depois de provar) contra o `screens/audit.tsx` de então, e ele falhou
  primeiro por engano meu de asserção (comparação de string inteira em vez de
  pathname) e, corrigido esse engano, falhou pela razão certa: o alvo do
  clique resolvia para `/settings/members-roles?since=...`. A prova
  permanente, com vermelho visto de outro jeito (navegação real, não jsdom),
  é `console/tests/e2e/settings-org.spec.ts`, escrito depois da correção — para
  esse arquivo especificamente eu **não vi o vermelho antes**, porque só
  existe fazendo sentido contra a implementação corrigida; o vermelho da
  reprodução real foi o do teste temporário acima, contra o código antigo.
- **T006** (`settings/audit.tsx`) — vermelho visto:
  `console/tests/unit/surfaces/settings-audit.test.tsx` foi escrito e rodado
  antes de `console/src/surfaces/settings/audit.tsx` existir; falhou com
  `Failed to resolve import "@/surfaces/settings/audit"`.
- **T008** (`sso-setup.tsx`) — **não vi o vermelho antes**: construí
  `console/src/surfaces/sso-setup.tsx` e só depois escrevi
  `sso-setup.test.tsx`. Rodei o teste pela primeira vez já com a implementação
  pronta; 3 dos 16 casos falharam nessa primeira rodada (um bug real de sintaxe
  de teste — chaves `{}` interpretadas como sequência de tecla pelo
  `userEvent.type`, não um defeito do componente), corrigidos no próprio
  teste. Não é uma reprodução de defeito test-first, é cobertura escrita
  depois. Nomeio isso explicitamente como desvio do processo pedido.
- **T010** (audit da ativação de SSO) — não é vermelho-então-verde: escrevi
  o teste esperando que já passasse (porque a leitura de código indicava que
  `set_settings` já audita qualquer campo alterado), rodei, e ele falhou por
  um erro meu na ordenação do array (`activation[-1]` em vez de
  `activation[0]`, já que `query()` devolve mais recente primeiro) — corrigi o
  teste, não o código-fonte. Linha do ledger tratada como "já valia,
  verificada", não como conserto.
- **T011** (substituição de token) — vermelho visto:
  `tests/unit/gateway/http/test_token_routes.py` falhou com `KeyError:
  'superseded'` e duas asserções de `False` antes do conserto em
  `platform/identity/tokens.py` e `gateway/http/routes/identity.py`.
- **T013** (`machine-token-groups.tsx`) — **não vi o vermelho antes**, pela
  mesma razão do T008: construí o componente primeiro, o teste depois. Na
  primeira rodada contra a implementação já pronta, todos os 10 testes
  passaram de primeira — o que também significa que não há uma reprodução
  documentada de "assim que estava errado". A cobertura de ramos que faltava
  (achada só depois, pelo gate de cobertura) foi fechada com mais testes,
  também escritos depois da implementação correspondente já existir.
- **T014** (`settings/members.tsx`) — vermelho visto:
  `console/tests/unit/surfaces/settings-members.test.tsx` rodado antes de
  `console/src/surfaces/settings/members.tsx` existir; falhou com `Failed to
  resolve import "@/surfaces/settings/members"`.
- **T015** — não há vermelho a ver: a guarda de último administrador já
  existia e já era coberta por um teste que eu não escrevi
  (`grants.test.tsx:329`); a linha do ledger é "já valia, verificada em
  `identity.py:427-448`", nunca apresentada como conserto.
- **Cobertura de rota de API para token** (`console/tests/unit/surfaces/token-route.test.tsx`,
  `token-bulk-revoke-route.test.tsx`) — não é vermelho-então-verde: escritos
  depois de `console/src/app/api/token/route.ts` e
  `.../bulk-revoke/route.ts` já existirem prontos (a rota de bulk-revoke é
  desta sessão; a rota simples já existia e só ganhou o parâmetro
  `supersede`). Achados pelo gate de cobertura (`uv run python -m
  tools.console_gate test`), que apontou as duas rotas em 0% — nenhum teste
  as exercitava antes. Todos os casos passaram já na primeira rodada contra
  o código pronto; nenhum defeito foi achado por eles, só a lacuna de
  cobertura foi fechada.
- **Confirmação antes de conceder papel administrativo**
  (`console/tests/unit/surfaces/grants.test.tsx`, describe `'granting an
  administrative role asks first'`) — vermelho visto de verdade: rodei a
  suíte antes de tocar `grants.tsx` e 4 dos 5 casos novos falharam (o
  diálogo, o estado `confirmingAdd` e o `data-testid` do diálogo ainda não
  existiam); o quinto ("non-administrative role still grants immediately")
  já passava, porque só reafirma o comportamento antigo para um papel que
  não muda. Corrigido implementando `requestGrant()`/`ADMINISTRATIVE_ROLES`
  em `grants.tsx`, suíte inteira (32/32) verde depois.
- **Sete testes acrescentados a `sso-setup.test.tsx` no ciclo de reparo**
  ("draws one control per field...", "will not test an edit that has not
  been saved", "sends the claim set the operator pasted, parsed", "still
  names the failure when a failing test named no specific problem", "names
  the tested-but-not-active state on its own, before any interaction",
  "says an unreachable deployment could not be reached, not that it
  refused", "takes the verified answer from a save rather than keeping what
  was there") — **não vi o vermelho antes**, pela mesma razão do T008/T013:
  fecham uma lacuna de migração contra `sso-setup.tsx`, que já existia e já
  implementava corretamente cada uma dessas propriedades (herdadas, sem
  alteração, do `SsoForm` antigo que `sso.test.tsx` cobria). Rodei a suíte
  já com os sete casos escritos contra o componente pronto e todos os 23
  passaram de primeira — nenhuma reprodução de defeito, cobertura recuperada
  depois de eu ter apagado `sso.test.tsx` sem migrar essas sete propriedades
  na primeira passada desta feature. Uma delas muda de mecanismo em vez de
  só mudar de nome: o `SsoForm` antigo caía num rótulo genérico
  (`labels.failed`) quando um teste falhava sem listar nenhum problema
  específico; `sso-setup.tsx` (linha 282) sempre desenha o cabeçalho
  `labels.resultFailed` antes da lista de problemas, vazia ou não — o
  operador nunca fica sem mensagem nos dois casos, mas o texto exato mudou
  de propósito com o redesenho em três etapas, não por descuido. O teste
  novo confere o texto que o componente atual de fato mostra, não o antigo.
- **`settings-sso.test.tsx` e `settings-machine-tokens.test.tsx`** (páginas
  servidor `settings/sso.tsx` e `settings/machine-tokens.tsx`, simetria com
  `settings-audit.test.tsx`/`settings-members.test.tsx`) — mistura dos dois
  casos. `settings-sso.test.tsx` (5 testes): não vi o vermelho antes, mesma
  razão do T008 — a página já mapeava `/identity/sso` corretamente, os cinco
  passaram de primeira contra o código pronto. `settings-machine-tokens.test.tsx`
  (4 testes): vi vermelho, mas do meu próprio teste, não do componente — as
  duas primeiras versões de "shows the machine token..." e "carries the
  token's own scopes..." erraram a estrutura do DOM (assumi que descrição e
  escopos apareciam na própria `<li data-testid="token">`; na verdade vivem
  no `<li data-testid="token-group">` que a envolve, a lista individual só
  mostra validade e o botão de revogar). As duas falharam por
  `TestingLibraryElementError: Unable to find an element with the text`,
  reescrevi a asserção para o elemento certo, ficou verde. Não é uma
  reprodução de defeito do componente — é a mesma classe de "vermelho pela
  razão certa" que o T004 já registrou, aplicada à minha própria asserção em
  vez de à implementação.

## 5. O que migrou dos dois testes apagados, e o que não migrou

`administration.test.tsx`, `audit.test.tsx` e `sso.test.tsx` foram apagados
junto com os módulos que testavam. Recuperei o conteúdo original dos três via
`git show HEAD:...` para conferir, linha por linha, o que tem equivalente na
suíte nova e o que não tem. A primeira passada desta feature fez essa
comparação para `administration.test.tsx` e `audit.test.tsx` apenas;
`sso.test.tsx` (17 testes) tinha ficado de fora da comparação e de §5 por
inteiro — corrigido no ciclo de reparo, tabela abaixo.

### `administration.test.tsx` (8 testes)

| Teste original | Migrou para | Estado |
|---|---|---|
| "shows the email when the deployment recorded one" | `settings-members.test.tsx:149` (asserção `avery@x.test` dentro do teste "lists people...") | Migrado |
| "says what a service account is, in English, rather than leaving it blank" | `settings-members.test.tsx:150-153` | Migrado |
| "says the same thing in Brazilian Portuguese" | — | **Não migrado** — nomeado no §3, item 2 |
| "falls back to the raw id for a blank-email principal that is not a service account" | `settings-members.test.tsx:164-192` (teste dedicado) | Migrado |
| "names the area Administration, whichever tab is open" | — | Mecanismo removido de propósito (não há mais abas — cada assunto é uma página própria); não é uma perda de cobertura, é a própria mudança que a feature pede |
| "offers both tabs, People first" | — | Idem |
| "defaults to People" | — | Idem |
| "shows the audit trail on its own tab" | — | Idem — o conteúdo do audit trail em si está exaustivamente coberto em `settings-audit.test.tsx` |

### `audit.test.tsx` (12 testes)

| Teste original | Migrou para | Estado |
|---|---|---|
| "collapses consecutive identical events into one row with a count" | `settings-audit.test.tsx:245` | Migrado |
| "does not collapse events that are not actually identical" | `settings-audit.test.tsx:258-267` (adicionado nesta sessão, depois de eu notar a lacuna) | Migrado |
| "is findable in the reading a viewer lands on by default" | `settings-audit.test.tsx:260` | Migrado |
| "excludes the system principal from the default reading" | `settings-audit.test.tsx:277-285` (adicionado) | Migrado |
| "offers a link back to the system events it hid, and follows through" | `settings-audit.test.tsx:288-300` | Migrado |
| "does not offer the toggle once a specific principal is already chosen" | `settings-audit.test.tsx:302-310` (adicionado) | Migrado |
| "does not render Principal or Action when neither offers a real choice" | `settings-audit.test.tsx:245-250` (adicionado) | Migrado |
| "renders once there is a real choice to make" | `settings-audit.test.tsx:210-226` | Migrado |
| "offers presets, each pointing at a bounded window" | `settings-audit.test.tsx:119-130` + `199-207` (forma diferente: agora prova o endereço e a legibilidade do rótulo, propriedade mais forte que a original) | Migrado, em forma reforçada |
| "never asks the gateway for more events than its own page bound allows" | `settings-audit.test.tsx:252-263` (adicionado) | Migrado |
| "shows the action and the outcome as words rather than as machine slugs" | `settings-audit.test.tsx:301-308` (ação) + `310-317` (resultado, adicionado) | Migrado |
| "colours the outcome by the role the design system already has for it" | `settings-audit.test.tsx:319-328` (adicionado) | Migrado |

Todas as lacunas encontradas nesta comparação foram fechadas nesta mesma
sessão, exceto a wording em pt-BR do §3 item 1. `settings-audit.test.tsx`
terminou com 22 testes (15 escritos originalmente test-first contra o módulo
ainda inexistente, mais 7 de migração de cobertura, escritos depois, contra
comportamento que eu já sabia correto).

### `sso.test.tsx` (17 testes)

| Teste original | Migrou para | Estado |
|---|---|---|
| "offers no way to activate an untested provider" | `sso-setup.test.tsx:165` ("shows the not-tested state and no way to activate") | Migrado |
| "offers it once the deployment says a test passed on these settings" | `sso-setup.test.tsx:342` ("offers the control once verified is true") | Migrado |
| "takes it away again the moment a field is edited" | `sso-setup.test.tsx:370` ("an edit after a passing test hides the control again, with its own explanation") | Migrado |
| "will not test an edit that has not been saved" | `sso-setup.test.tsx:300` (mesmo nome) | **Não migrado na primeira passada — fechado no ciclo de reparo, mesmo nome, mesma asserção** |
| "takes the verified answer from the deployment rather than from the save" | `sso-setup.test.tsx:457` ("takes the verified answer from a save rather than keeping what was there") | **Não migrado na primeira passada — fechado no ciclo de reparo** |
| "sends the claim set the operator pasted, parsed" | `sso-setup.test.tsx:275` (mesmo nome) | **Não migrado na primeira passada (nenhum teste conferia o payload exato enviado) — fechado no ciclo de reparo** |
| "says where a passing test landed the user" | `sso-setup.test.tsx:183` ("shows what each claim resolved to on success") | Migrado, em forma reforçada (confere subject/email/team separadamente, não uma frase só) |
| "reports a failing test in the deployment's own words, and offers no activation" | `sso-setup.test.tsx:251` ("reports why a claim set failed, naming the missing claim") | Migrado — a asserção de que `activate-sso` some (`queryByTestId('activate-sso')).toBeNull()`) faltava neste teste; adicionada no ciclo de reparo |
| "activates and adopts what the deployment says it became" | `sso-setup.test.tsx:392` ("activating asks the deployment and adopts what it answers") | Migrado |
| "lists everything wrong with the configuration, not the first thing" | `sso-setup.test.tsx:487` ("lists every one of them at once") | Migrado |
| "draws one control per field the provider is described by" | `sso-setup.test.tsx:147` (mesmo nome) | **Não migrado na primeira passada — fechado no ciclo de reparo, mesmo nome, mesma asserção** |
| "says it could not be reached rather than that it refused" (contra `activate`) | `sso-setup.test.tsx:437` ("says an unreachable deployment could not be reached, not that it refused") | **Não migrado na primeira passada — a suíte nova só cobria o caminho "unreachable" para `save`, não para `activate`; fechado no ciclo de reparo** |
| "carries a refusal reason back in the deployment's own words" (contra `activate`) | `sso-setup.test.tsx:414` ("leaves the state alone when activation is refused") | Migrado |
| "refuses a claim set that is not a document, without asking anything" | `sso-setup.test.tsx:563` ("reports it as a failure rather than sending it") | Migrado |
| "falls back to its own words when a failing test named no problem" | `sso-setup.test.tsx:320` ("still names the failure when a failing test named no specific problem") | **Não migrado na primeira passada — fechado no ciclo de reparo, com mudança de mecanismo (ver §4): o rótulo genérico antigo (`labels.failed`) virou o cabeçalho `labels.resultFailed`, sempre desenhado, que o teste novo confere no lugar do antigo** |
| "says a test passed even where it mapped nowhere in particular" | `sso-setup.test.tsx:223` ("names the fallback team when the default was used") | Migrado |
| "shows the tested state where the deployment says tested but not active" | `sso-setup.test.tsx:356` ("names the tested-but-not-active state on its own, before any interaction") | Migrado — só existia implicitamente antes (linha 338, como efeito colateral de um teste sobre ativação recusada); ciclo de reparo acrescentou um teste dedicado à leitura inicial |

`sso-setup.test.tsx` terminou com 23 testes (16 da primeira passada desta
feature, mais 7 de migração de cobertura fechados no ciclo de reparo, todos
verdes já na primeira rodada contra `sso-setup.tsx` — que já implementava
corretamente as sete propriedades, herdadas sem alteração do `SsoForm`
antigo; ver §4 para o porquê disso não ser vermelho-então-verde).

## 6. Arquivos criados

- `console/src/surfaces/settings/audit.tsx`
- `console/src/surfaces/settings/members.tsx`
- `console/src/surfaces/settings/sso.tsx`
- `console/src/surfaces/settings/machine-tokens.tsx`
- `console/src/surfaces/sso-setup.tsx`
- `console/src/surfaces/sso-fields.ts`
- `console/src/surfaces/machine-token-groups.tsx`
- `console/src/app/api/token/bulk-revoke/route.ts`
- `console/tests/unit/surfaces/settings-audit.test.tsx`
- `console/tests/unit/surfaces/settings-members.test.tsx`
- `console/tests/unit/surfaces/sso-setup.test.tsx`
- `console/tests/unit/surfaces/machine-token-groups.test.tsx`
- `console/tests/unit/surfaces/token-route.test.tsx`
- `console/tests/unit/surfaces/token-bulk-revoke-route.test.tsx`
- `console/tests/unit/surfaces/settings-sso.test.tsx`
- `console/tests/unit/surfaces/settings-machine-tokens.test.tsx`
- `console/tests/e2e/settings-org.spec.ts`
- `tests/unit/gateway/http/test_audit_routes.py`
- `tests/unit/gateway/http/test_token_routes.py`

## 7. Arquivos modificados

- `console/src/app/(shell)/settings/{audit-log,machine-tokens,members-roles,single-sign-on}/page.tsx`
- `console/src/app/api/token/route.ts`
- `console/src/i18n/en.ts`, `console/src/i18n/pt-BR.ts`
- `console/tests/e2e/scroll-budget.spec.ts`, `settings-nav.spec.ts`
- `console/tests/unit/shell/route-files.test.tsx`
- `console/tests/unit/support/screens.ts`
- `console/tests/unit/surfaces/{behaviour,first-run,outage,screens}.test.tsx`
- `fixtures/scenarios/populated/tokens.json` (+15 tokens `bootstrap`)
- `gateway/http/asgi.py`, `gateway/http/routes/audit.py`, `gateway/http/routes/identity.py`
- `platform/identity/models.py`, `platform/identity/tokens.py`
- `platform/persistence/{ports,fakes}/audit_repository.py`,
  `platform/persistence/postgres/repositories/audit_repository.py`
- `platform/startup/bootstrap.py`
- `tests/contract/persistence/test_audit_repository.py`
- `tests/unit/gateway/http/conftest.py`, `test_sso_routes.py`

## 8. Arquivos removidos

- `console/src/surfaces/screens/administration.tsx`, `screens/audit.tsx`, `sso.tsx`
- `console/tests/unit/surfaces/administration.test.tsx`, `audit.test.tsx`, `sso.test.tsx`

## 9. Uma descoberta que vale para quem vier depois

`console/src/surfaces/settings/sso.tsx` (servidor) chamava `SSO_FIELDS.map(...)`
importando `SSO_FIELDS` de um módulo `'use client'`
(`console/src/surfaces/sso-setup.tsx`). Passou limpo em `tsc`, `eslint` e nos
2091 testes `vitest` — e quebrou só contra o build de produção real
(`next build` + servidor), com `TypeError: k.SSO_FIELDS.map is not a
function`, achado rodando `console/tests/e2e/settings-org.spec.ts` pela
primeira vez. É a mesma classe de defeito que a 040 já documentou
(`integrationsHref` como prop de servidor para cliente) — dessa vez num valor
exportado, não numa função — e o `tests/unit/shell/rsc-boundary.test.ts` que
existe para pegar isso **não pega**: o regex de `callsIt()` procura
`SSO_FIELDS(`, não `SSO_FIELDS.map(`. Consertei movendo `SSO_FIELDS`/`SsoField`
para `console/src/surfaces/sso-fields.ts`, um módulo sem diretiva — o mesmo
padrão que `token-identity.ts` já usa e documenta. Não estendi o guard de
teste para cobrir `.map(`/`.forEach(`/etc. — fica nomeado aqui para quem
tiver tempo de fazer esse guard mais rigoroso.
