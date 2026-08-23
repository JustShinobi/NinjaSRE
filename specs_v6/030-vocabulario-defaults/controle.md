# Controle — Vocabulário sem cru e defaults seguros de token

**Este documento foi escrito no meio da execução, a pedido do orquestrador,
depois que a sessão parou no meio de uma edição.** Ele registra só o que o
código na árvore de trabalho prova agora — não o que as tarefas pretendiam
fazer. Branch `feat/v6-010-provider-out-of-the-box`, em cima de `b4a8153`.
Nada foi commitado nem staged por este trabalho.

**O maior buraco, dito primeiro**: o passo acceptance-first (T004) não foi
executado. `console/tests/e2e/vocabulary-defaults.acceptance.spec.ts` **não
existe**. Cinco telas de console já foram alteradas (`members.tsx`,
`machine-token-groups.tsx`, `status.tsx`, `first-run/model.tsx`,
`screens/first-run.tsx`) sem que o mockup tivesse virado teste primeiro, o
que a instrução da tarefa marca como não-negociável. Isso é uma inversão de
ordem real, não um detalhe — está registrado aqui sem eufemismo.

**Um efeito colateral, ainda pior**: a última edição em andamento
(`screens/first-run.tsx`) ficou pela metade. `ModelStepLabels.fieldLabels`
foi tornado obrigatório e o único call site real do produto
(`console/src/surfaces/screens/first-run.tsx:623`) não foi atualizado para
fornecer esse campo — só o import de `MODEL_PROVIDER_SETTING`/`MODEL_SETTING`
chegou a ser adicionado (linhas 20-21), o objeto `labels={{...}}` passado a
`<ModelStep>` continua sem `fieldLabels`. Isso é um `tsc` vermelho hoje e,
se o typecheck fosse contornado, um `TypeError` em runtime na tela real de
primeiro uso (`fieldLabels[path]` sobre `undefined`). **A tela de primeiro
uso está quebrada nesta árvore agora**, até essa linha ser completada.

## 1. T001 — descoberta: o gateway já sabe criar uma pessoa?

**Veredito: não existe rota.**

Evidência, por `file:line`:

- `gateway/http/routes/identity.py:303-311` — o único endpoint de leitura de
  principals é `GET /identity/principals` (`list_principals`). Não há
  `@identity_router.post("/principals"` nem qualquer rota de criação de
  principal em todo o arquivo — os únicos `POST` do roteador são
  `/grants` (`identity.py:393`, exige que o principal já exista —
  `if await uow.identity.get_user(...) is None: raise not_found(...)`,
  `identity.py:407-408`) e `/tokens` (`identity.py:498`, emite credencial
  para um principal já existente).
- `platform/identity/local_accounts.py:186` — `_ensure_principal` existe,
  mas cria exclusivamente o principal reservado da conta local
  (`LOCAL_ACCOUNT_PRINCIPAL_ID`), nunca um principal arbitrário escolhido
  por quem chama.
- `surfaces/console/client.py:340` (`principals()`, leitura) e `:352`
  (`create_token`, emissão de token) — o cliente do console não tem nenhum
  método de criação de principal porque a rota que ele chamaria não existe.

A capacidade de baixo nível existe na camada de persistência
(`IdentityRepository.upsert_user` + `upsert_role_binding`, já usada por
`platform/startup/bootstrap.py` e por `local_accounts.py`), mas nada na
camada HTTP a expõe para um principal arbitrário. US3 (T025-T028) exige rota
nova em `gateway/http/routes/identity.py`, sobre esse port já existente —
exatamente como o plano previu para o caso "não existe rota". **T025-T028
não foram iniciados.**

## 2. T002 — descoberta: o que o servidor faz hoje com uma emissão sem escopos

**Observado, com um teste real, não por leitura de código sozinha**: uma
emissão sem `permissions` declaradas resolve, na autenticação, para **todas
as permissões que o emissor detém** — não para nenhuma.

Como foi observado: escrevi
`tests/unit/platform/identity/test_a_token_issued_with_no_permissions_declared_authenticates_to_nothing`
em `tests/unit/platform/identity/test_tokens.py`, concedi `Role.OWNER` a um
usuário de teste, emiti um token sem passar `permissions=`, autentiquei com
o segredo emitido e afirmei que `authenticated.permissions.permissions_at(None)
== frozenset()`. Rodado antes de qualquer mudança de produção:

```
uv run pytest tests/unit/platform/identity/test_tokens.py -q -k "no_permissions_declared or explicit_permissions_carries or unscoped_token"
```

Vermelho observado (mensagem real, truncada pelo pytest):

```
E   AssertionError: assert frozenset({<P...write'>, ...}) == frozenset()
E   Extra items in the left set:
E   <Permission.REMEDIATION_APPROVE: 'remediation.approve'>
E   <Permission.WEBHOOK_DELIVER: 'webhook.deliver'>
E   <Permission.AUDIT_EXPORT: 'audit.export'>
E   <Permission.REMEDIATION_EXECUTE: 'remediation.execute'>
E   <Permission.INCIDENT_MANAGE: 'incident.manage'>...
```

Causa raiz, cravada em código: `platform/identity/tokens.py`'s `_scoped()`
lia `if not token.scopes: return held` — uma lista de escopos vazia sempre
lia como "sem teto", ou seja, tudo o que o dono do token detém *agora*,
resolvido dinamicamente a cada autenticação. Essa leitura é correta e
intencional para um token que representa a própria pessoa (a sessão do
navegador, `platform/identity/local_accounts.py:162`, e a credencial durável
pós-bootstrap, `platform/startup/bootstrap.py:322`) — mas o mesmo código era
usado, sem distinção nenhuma, pela rota de emissão de machine token
(`gateway/http/routes/identity.py:498-523`), que é exatamente onde
"nenhum escopo marcado" precisa significar "nenhum poder", não "todo poder".

O modelo de permissões em si já tinha o vocabulário certo para essa
distinção — `platform/identity/authorisation.py`'s `PermissionSet.ceiling`
já documenta `None` como "sem teto" e `frozenset()` como "detém nada" — só
faltava um sinal persistido em `ApiToken` para `_scoped()` saber qual dos
dois casos está vendo. Essa é a razão de existir o veredito abaixo: **T013 é
correção, não caracterização** — o comportamento atual divergia do que
FR-016 exige, e a segunda tarefa (T014) teve que mudar código de produção
para fechar a divergência, não apenas documentá-la.

## 3. Ledger por tarefa — só o que o código prova

| Tarefa | Estado | Detalhe |
|---|---|---|
| T001 | **FEITO** | Veredito registrado acima com `file:line`. Nenhum desenho de endpoint foi feito — a descoberta só decide a forma de T025-T028, que não começaram. |
| T002 | **FEITO** | Comportamento observado com teste real, seção 2 acima. |
| T003 (fixtures) | **NÃO INICIADO** | Nenhum arquivo em `fixtures/scenarios/` nem em `tools/mockplane/dataset/served.py` foi tocado. Levantamento feito (ver seção 5) mas nada escrito. |
| T004 (acceptance spec, vermelho) | **NÃO INICIADO** | `console/tests/e2e/vocabulary-defaults.acceptance.spec.ts` não existe. Nome amendado na seção 6 abaixo — o `tasks.md` também foi corrigido para citar o nome real. |
| T005/T006 (form abre sem escopo) | **NÃO INICIADO** | `machine-token-groups.tsx:156` continua `useState(new Set(issuedScopes))` — todos os escopos do emissor ainda vêm marcados por padrão. Nenhum teste escrito. |
| T007/T008 (templates de finalidade) | **NÃO INICIADO** | |
| T009/T010 (agrupamento por domínio) | **NÃO INICIADO** | |
| T011/T012 (aviso de escopo destrutivo) | **NÃO INICIADO** | |
| T013 (teste de contrato do servidor) | **PARCIAL, não marcado** | Dois dos três comportamentos que a tarefa pede têm teste novo e dedicado em `tests/unit/platform/identity/test_tokens.py`: "sem escopos → token sem escopo nenhum" (vermelho confirmado, seção 2) e "com escopos → exatamente aqueles" (`test_a_token_issued_with_explicit_permissions_carries_only_those` — este **já passava antes de qualquer mudança**, é caracterização, não correção, e está dito como tal). O terceiro — "o teto do emissor continua valendo" — não ganhou teste novo nesta sessão; o mecanismo que o impõe (`PermissionSet.narrowed_to` intersectando em vez de substituir) não foi alterado, mas não há uma asserção desta sessão que prove isso continua de pé. Não marcado em `tasks.md` por essa lacuna. |
| T014 (implementar a garantia) | **PARCIAL, não marcado — regressão conhecida e não corrigida** | Ver seção 4. `unscoped: bool` foi adicionado a `ApiToken` (`platform/persistence/ports/identity_repository.py`), `TokenService.issue()` e `_scoped()` (`platform/identity/tokens.py`), com `unscoped=True` explícito nos dois call sites que precisam continuar sem teto (`local_accounts.py:162`, `bootstrap.py:322`). A suíte de identidade, gateway/http e persistence-contract (435 + 422 testes, comandos na seção 7) passa. **Mas uma varredura completa da suíte Python encontrou uma regressão real e não corrigida**: `tests/unit/gateway/webhooks/test_delivery_permission.py::test_the_permission_is_grantable_through_the_token_route` falhou (`pytest -q -x`, seção 7) e a suíte parou aí — o que está depois desse ponto na coleção nunca rodou nesta sessão, então pode haver mais. A migração Alembic real para a coluna `unscoped` (Postgres) também não foi escrita — o campo existe no port e no fake, não no schema Postgres nem na migração; um deployment real rodando contra Postgres quebraria na primeira emissão de token até essa migração existir. |
| T015 (teste do chip) | **FEITO** | `console/tests/unit/components/status.test.tsx` — 7 testes novos (`PrincipalKindChip`, `AccountStateChip`, `TokenGroupStateChip`), vermelho confirmado antes de qualquer implementação (seção 7 tem o comando e a mensagem real). |
| T016 (implementar chip de tipo/estado de conta) | **FEITO, com um desvio do plano citado** | `console/src/components/status.tsx` ganhou `PrincipalKindChip`/`AccountStateChip`/`TokenGroupStateChip`; `console/src/surfaces/settings/members.tsx:139-141` usa os dois primeiros no lugar de `<Badge status={text(person,'kind')} />` / `<Badge status={... ? 'healthy':'disabled'} />`. **Desvio**: o plano da feature cita `console/src/design/status.ts` como arquivo tocado por esta tarefa; `design/status.ts` **não foi tocado** — julguei que tipo-de-principal e estado-de-conta não são vocabulário de "status" no sentido que aquele arquivo já cataloga (raw run/resource status → papel/forma), e resolvi tudo em `components/status.tsx` com rótulos escolhidos diretamente. Consequência real, não hipotética: `settings-members.test.tsx` (existente, 32 testes combinados com os dois arquivos vizinhos) continua verde sem alteração — mas esse arquivo nunca afirmava o texto cru `HEALTHY`/`SERVICE_ACCOUNT` para começo de conversa, então essa suíte não é prova de que o defeito visual sumiu da tela real; só a suíte de componente (T015) prova isso, e só até o nível de componente. |
| T017 (chip do grupo de token) | **PARCIAL, não marcado** | `machine-token-groups.tsx:350` foi trocado de `<Badge status="healthy" />` para `<TokenGroupStateChip locale={locale} everUsed={lastUsed !== ''} />`. `machine-token-groups.test.tsx` (32 testes combinados) continua passando, mas nenhum teste **novo e dedicado** foi escrito para esta troca especificamente — a prova de vermelho que existe é só a do componente genérico (T015), não uma prova no nível desta tela. Não marcado por essa lacuna, seguindo a mesma régua de T013. |
| T018 (preview do wizard) | **QUEBRADO — não marcado** | Ver o aviso no topo deste documento. Teste novo escrito e vermelho confirmado (`console/tests/unit/surfaces/first-run.test.tsx`, mensagem na seção 7). `console/src/surfaces/first-run/model.tsx` foi implementado (`changesOf()` agora recebe `fieldLabels` e traduz o path antes de montar a string; `ModelStepLabels.fieldLabels` ficou obrigatório). **Nunca rodei o teste de novo depois de implementar** — não tenho verde confirmado para ele nesta sessão. E o call site real (`screens/first-run.tsx`) ficou sem `fieldLabels`, então a tela quebra. |
| T019 (títulos policies.*/surfaces.*) | **NÃO INICIADO, mas achado real registrado** | Ver seção 5 — o vazamento não está onde o plano da feature diz. |
| T020 (Alert intake trust) | **NÃO INICIADO** | Achado registrado na seção 5. |
| T021 (evidência da sugestão do estate) | **NÃO INICIADO** | Achado registrado na seção 5. |
| T022 (identificação de sessão) | **NÃO INICIADO** | |
| T023 (ajuda do grant) | **NÃO INICIADO** | |
| T024 (grant lista papel legível) | **NÃO INICIADO** | |
| T025-T028 (US3, criar pessoa) | **NÃO INICIADO** | Depende de T001, que está feito; nada além da descoberta foi construído. |
| T029 (checagem bilíngue) | **NÃO INICIADO formalmente** | Toda chave nova que esta sessão introduziu (`principal.kind.person`, `principal.kind.serviceAccount`, `principal.state.active`, `principal.state.suspended`, `tokenGroup.state.inUse`, `firstRun.model.field.provider`, `firstRun.model.field.model`) tem par em `en.ts` e `pt-BR.ts` — conferido por leitura, não por uma checagem automatizada rodada. Nenhum comando de verificação de catálogo foi executado nesta sessão. |
| T030 (remover fixmes de vocabulário) | **NÃO INICIADO** | `console/tests/e2e/transversal-rules.spec.ts` não está no diff desta sessão — as sete exceções de `EXCEPTIONS` continuam todas de pé, incluindo as que os FRs desta feature deveriam fechar. |
| T031 (isenção do vocabulary.spec.ts) | **NÃO INICIADO** | Arquivo não tocado. |
| T032-T036 (polimento, gates, este documento) | **NÃO INICIADO** | Nenhum gate de `make verify` rodou. Nenhuma baseline visual foi aceita por mim nesta sessão — o orquestrador reportou um processo Playwright `visual --compare` em segundo plano que eu não tenho registro direto de ter iniciado deliberadamente; ele relatou que a baseline afetada (`console/visual/baselines/agent-1440-light.png`) ficou byte-idêntica ao HEAD, ou seja, nenhuma baseline foi de fato alterada. Não investiguei further por instrução explícita de não rodar mais nada. |

## 4. A regressão aberta de T014, em detalhe

`tests/unit/gateway/webhooks/test_delivery_permission.py::test_the_permission_is_grantable_through_the_token_route`
falhou na varredura completa (comando e contagem na seção 7). Não investiguei
a causa exata antes de ser instruído a parar — a hipótese mais provável, dado
o padrão já encontrado duas vezes nesta sessão (`tests/unit/gateway/http/conftest.py`
tinha o mesmo problema e foi corrigido, seção 7), é mais um call site de teste
que emite um token via `TokenService.issue()` sem `permissions=` e sem
`unscoped=True`, esperando implicitamente o comportamento antigo
("sem escopo declarado" = "tudo"). **Não corrigi este arquivo.** Quem retomar
este trabalho deve: (a) rodar esse teste isolado para ver a mensagem real,
(b) decidir se o token que ele emite representa uma pessoa (→ `unscoped=True`,
mesmo padrão do conftest já corrigido) ou um uso genuinamente restrito
(→ declarar `permissions=` explícitas), (c) então rodar a suíte completa de
novo, sem `-x`, para achar o que mais pode estar atrás desse primeiro
vermelho — a coleção nunca chegou lá nesta sessão.

## 5. Achados que mudam como alguém deve continuar

- **FR-005/FR-006 não vazam onde o plano da feature diz.** O plano cita
  `console/src/surfaces/advanced-config-section.tsx` como o arquivo do
  título da seção técnica. Esse componente já usa um título humano vindo de
  i18n (`autonomy.tsx:618`, `message(locale, 'settings.autonomy.advanced.title')`).
  O vazamento de verdade — `policies.masking`, `policies.guardrails`,
  `policies.approvals`, `policies.autonomy`, `surfaces.notification_policy`
  aparecendo cru — está em `console/src/surfaces/preview.tsx`, dentro de
  `ConfigEditor`: `field.section` (lido cru de `editable.ts:92`,
  `text(entry, 'section')`) é usado diretamente como texto do link do índice
  (`preview.tsx:645`) e como título do `<details><summary>` de cada grupo
  (`preview.tsx:673`), sem tradução nenhuma. Esse componente é compartilhado
  por toda página com seção avançada, não só Autonomy/Notifications — a
  correção certa é um resolvedor de rótulo humano ali, com fallback
  humanizado (no estilo de `humanize()` em `machine-token-groups.tsx`) para
  qualquer seção que o catálogo declarar amanhã e este código ainda não
  conhecer.

- **FR-007 (Alert intake)**: a frase crua vem de
  `console/src/surfaces/settings/alert-intake.tsx:477-479` —
  `{message(locale, 'ingress.verification')} {deliveryPermission}`, onde
  `ingress.verification` = `"Trusted by"` (`en.ts:1330`) e `deliveryPermission`
  é o valor cru `webhook.deliver` lido de `/v1/ingress/sources`. A mesma
  chave `ingress.verification` também é usada em `alert-intake.tsx:~408`
  para um propósito diferente e legítimo (a descrição de verificação por
  fonte) — **não pode ser trocada globalmente**, só o uso do bloco
  `delivery-token-group` (linhas 468-491). A tela hoje não lê
  `/identity/tokens`, então não sabe nomear o token de entrega existente —
  isso exige uma leitura nova nesta página (justificável: a spec só proíbe
  leitura nova para FR-008, não para FR-007) e cruzar por `scopes` contendo
  `webhook.deliver`. Não implementado.

- **FR-008 (sugestão do estate)**: o backend já serve um campo `because`
  (`platform/estate/suggestions.py:54`, `Suggestion.because`, já passado por
  `gateway/http/routes/integrations.py:340` em `SuggestionView`) — uma frase
  legível gerada pelo servidor, sem id cru, **exceto** no caso em que
  `resource.display_name` está vazio (`suggestions.py:98`,
  `resource.display_name or resource.resource_id!r` cai para o id cru
  exatamente nesse caso, que é justo a borda que a spec probe). O console
  hoje só lê `address` e `from_resource` de `suggested`
  (`console/src/surfaces/screens/integrations.tsx:157-166`), nunca
  `because`. Decisão de design que cheguei a tomar mas não implementei:
  acrescentar um campo `resource_label` explícito em `Suggestion`/`SuggestionView`
  (computado de `resource.display_name`, vazio quando não resolvível — nunca
  o id), e usá-lo na evidência, com o `from_resource` cru indo só para a URL
  do botão "Connect" como parâmetro de destino. Não implementado.

- **`fixtures/scenarios/populated` já tem a maior parte do que T003 pede**:
  um principal `service_account` (Scheduler) e três `user` já existem
  (`tools/mockplane/dataset/served.py:2407-2438`, `USERS`); um grupo de
  token "em uso" (`scheduler`, `last_used_at` preenchido) e um "nunca usado"
  (`bootstrap`, 15 linhas, todas com `last_used_at: null`) já coexistem no
  mesmo cenário. **Falta**: um principal inativo (nenhum dos quatro tem
  `is_active: false`) e uma sugestão do estate com recurso não resolvível —
  nenhuma das duas foi adicionada.

## 6. Correção ao `tasks.md`

T004 tratava o nome do acceptance spec como
`console/tests/e2e/030-vocabulario-defaults.acceptance.spec.ts`. Esse nome
citaria o número da feature num arquivo committed, que `specs_v6/` — o
diretório que dá esse número — é gitignored; um contribuidor que clona o
repositório não o teria. O nome real, decidido pelo operador antes desta
sessão começar, é `console/tests/e2e/vocabulary-defaults.acceptance.spec.ts`.
O `tasks.md` foi corrigido para citar esse nome (ver o próprio arquivo). O
arquivo em si **não existe** — nada do conteúdo normativo do mockup foi
codificado como teste, e nenhuma das cinco telas já alteradas nesta sessão
foi provada contra ele antes de mudar.

## 7. Todo comando rodado nesta sessão, com resultado real

Python:

```
uv run pytest tests/unit/platform/identity/test_tokens.py -q
```
Antes de qualquer mudança: `24 passed in 0.46s`.

```
uv run pytest tests/unit/platform/identity/test_tokens.py -q -k "no_permissions_declared or explicit_permissions_carries or unscoped_token"
```
Vermelho confirmado (2 de 3 falharam — mensagens na seção 2): `F.F` →
`2 failed, 1 passed, 24 deselected`.

Depois de implementar `unscoped` em `ApiToken`/`TokenService`/`_scoped`/
`local_accounts.py`/`bootstrap.py`:
```
uv run pytest tests/unit/platform/identity/test_tokens.py -q
```
`27 passed in 0.45s`.

```
uv run pytest tests/unit/platform/identity/ tests/unit/platform/startup/ tests/contract/persistence/test_identity_repository.py -q
```
`435 passed in 5.27s`.

```
uv run pytest tests/unit/gateway/http/test_identity_grant_routes.py tests/unit/gateway/webhooks/test_alertmanager_delivery_identity.py -q
```
Vermelho real, não relacionado ao meu código-fonte de produto mas à
infraestrutura de teste: `8 failed, 8 passed` — todo o pacote
`test_identity_grant_routes.py` (403 em vez de 201/200 esperado) porque
`tests/unit/gateway/http/conftest.py`'s `issue_token()` emitia o bearer de
teste sem `permissions=` e sem `unscoped=True`, contando implicitamente com
o comportamento antigo. Corrigido com `unscoped=True` nesse helper
(comentário no próprio arquivo explica por quê). Depois da correção:
```
uv run pytest tests/unit/gateway/http/ -q
```
`422 passed in 32.86s`.

```
timeout 580 uv run pytest -q -x --no-header -p no:cacheprovider
```
Rodado em segundo plano, terminou sozinho depois que a sessão já tinha
parado de trabalhar (notificação de conclusão chegou depois da instrução do
orquestrador para parar). Resultado real, capturado do output persistido:
`1 failed, 6302 passed, 25 skipped, 16 warnings in 553.67s (0:09:13)`, parado
em `tests/unit/gateway/webhooks/test_delivery_permission.py::test_the_permission_is_grantable_through_the_token_route`
por causa do `-x`. **Não corrigido. A coleção não terminou de rodar — o que
vem depois desse ponto nunca foi exercitado nesta sessão.**

Console (vitest, `pnpm exec vitest run <arquivo>` — nunca com `--coverage`,
então nenhum destes números é o gate; ver a nota da onda sobre essa
armadilha):

```
pnpm exec vitest run tests/unit/components/status.test.tsx
```
Antes: `12 passed`. Depois de escrever os 7 testes novos, antes de
implementar: `7 failed, 12 passed (19)` — mensagem real do primeiro erro:
`Error: Element type is invalid: expected a string (for built-in components)
or a class/function (for composite components) but got: undefined.` (import
de componente que ainda não existia). Depois de implementar
`PrincipalKindChip`/`AccountStateChip`/`TokenGroupStateChip`:
`19 passed`.

```
pnpm exec vitest run tests/unit/surfaces/settings-members.test.tsx tests/unit/surfaces/machine-token-groups.test.tsx tests/unit/surfaces/settings-machine-tokens.test.tsx
```
Depois de aplicar os chips em `members.tsx` e `machine-token-groups.tsx`:
`32 passed`. Nenhuma dessas suítes tinha, antes ou depois, uma asserção que
falhasse por causa do texto cru `HEALTHY`/`SERVICE_ACCOUNT` — elas não
provam a ausência do defeito na tela, só que nada que já existia quebrou.

```
pnpm exec vitest run tests/unit/surfaces/first-run.test.tsx -t "display name"
```
Vermelho confirmado antes de implementar — mensagem real:
```
Expected element to have text content: Investigation model
Received: would changemodels.investigator.model → claude-opus-5
```
**Não rodei este comando de novo depois de implementar `model.tsx`.** Não
tenho verde confirmado para este teste, e o call site real
(`screens/first-run.tsx`) está sem `fieldLabels`, então rodar a suíte inteira
de `first-run.test.tsx` agora provavelmente reprova em mais de um teste que
usa esse mesmo arquivo — não confirmado, porque não rodei.

Nenhum gate foi executado: nem `uv run python -m tools.console_gate
{typecheck,lint,test}`, nem `make lint`/`make typecheck`/`make verify`, nem
qualquer comando Playwright (`behaviour`, `first-day`, `visual`) partiu desta
sessão de forma que eu possa confirmar.

## 8. O que fica pendente, nomeado, não escondido

Tudo que não está marcado **FEITO** na tabela da seção 3, na ordem do
`tasks.md`: T003, T004 (o maior — nada foi provado contra o mockup antes de
mudar código), T005 a T012 (US1 inteira, incluindo o próprio default
perigoso do formulário — `machine-token-groups.tsx:156` continua marcando
todos os escopos), a lacuna de T013, a regressão aberta de T014, a lacuna de
T017, o `model.tsx`/`screens/first-run.tsx` quebrado de T018, T019 a T024
(o resto de US2 — títulos de seção, Alert intake, sugestão do estate, sessão,
grant), T025 a T028 (US3 inteira além da descoberta), T029 a T031, e todo o
Fase 7. Nenhum destes tem dono declarado fora desta própria feature — tudo
pertence a 030 e nada foi transferido para outra spec da onda.

---

## 9. Continuação — sessão 2, a partir do estado acima

**Esta seção foi escrita em cima do que as seções 1–8 registraram, sem
apagar nada delas.** Verificado contra o código real desta árvore agora,
branch `feat/v6-010-provider-out-of-the-box`, ainda em cima de `b4a8153`.
Nada commitado nem staged por este trabalho. Instrução do orquestrador, a
meio desta sessão: consertar as duas quebras que deixavam a árvore
VERMELHA, medir o raio de alcance, e então **parar** — sem tocar mais
nenhuma tela, sem iniciar T003 em diante. É o que este documento registra.

### 9.1 A árvore estava VERMELHA; as duas quebras, com sua causa e conserto

**Quebra 1 — typecheck.** A edição interrompida da sessão anterior (ver
topo deste documento) tinha deixado `ModelStepLabels.fieldLabels`
obrigatório sem que o único call site real
(`console/src/surfaces/screens/first-run.tsx`) fornecesse esse campo. O
vermelho real veio pré-capturado pelo orquestrador, verbatim:

```
src/surfaces/screens/first-run.tsx(20,3): error TS6133: 'MODEL_PROVIDER_SETTING' is declared but its value is never read.
src/surfaces/screens/first-run.tsx(21,3): error TS6133: 'MODEL_SETTING' is declared but its value is never read.
src/surfaces/screens/first-run.tsx(628,21): error TS2741: Property 'fieldLabels' is missing in type '{ known: string; ... }' but required in type 'ModelStepLabels'.
```

Eu não rodei o `typecheck` eu mesmo antes de editar nesta sessão — o
vermelho acima é o output real que o orquestrador colou, e eu o conferi
contra a leitura direta do código (`screens/first-run.tsx:628`, o objeto
`labels={{...}}` passado a `<ModelStep>` de fato não tinha `fieldLabels`)
antes de mexer. Dizendo isso sem eufemismo: não é "watched it fail" nesta
sessão; é evidência real de terminal, de terceiro, cruzada com a leitura do
código-fonte antes do conserto.

Conserto: adicionado o campo que faltava em
`console/src/surfaces/screens/first-run.tsx:644-650`, usando as chaves já
existentes em `en.ts:570-571`/`pt-BR.ts:128-129`
(`firstRun.model.field.provider`, `firstRun.model.field.model` —
adicionadas pela sessão anterior, já bilíngues antes desta sessão começar).
`MODEL_PROVIDER_SETTING`/`MODEL_SETTING` (importados na sessão anterior e
nunca usados) passaram a ser as chaves desse mapa, o que também fechou os
dois `TS6133`.

Verde confirmado por mim:

```
uv run python -m tools.console_gate typecheck
```
→ `$ tsc --noEmit`, `EXIT=0`, nenhum erro.

```
pnpm exec vitest run tests/unit/surfaces/first-run.test.tsx
```
→ `97 passed` (arquivo inteiro, não só o teste que nomeia o campo).

**Quebra 2 — `test_the_permission_is_grantable_through_the_token_route`.**
Vermelho real, visto por mim:

```
uv run pytest tests/unit/gateway/webhooks/test_delivery_permission.py -q
```
Antes do conserto (mensagem real, reproduzida):
```
AssertionError: {"error":{"type":"permission_denied","message":"This action needs 'token.manage' at 'payments'. ..."}}
assert 403 == 201
```

**A causa era o setup do teste andando de carona no defeito antigo, não um
bug desta sessão.** `tests/unit/gateway/webhooks/test_delivery_permission.py`
emitia o token "admin" com `machine_token(deployment, user_id="operator",
permissions=())`. Sob a semântica antiga, escopos vazios liam como "tudo o
que o dono detém agora", resolvido dinamicamente a cada autenticação; como o
teste concede `Role.ADMIN` ao `"operator"` **depois** de emitir o token, a
leitura antiga fazia esse token carregar `token.manage` no momento do uso,
mesmo sem tê-lo pedido explicitamente. Sob a semântica corrigida (o ponto
desta feature), escopos vazios não-`unscoped` leem como "nada" — daí o 403.

**O conserto expressa o que o teste sempre quis dizer, não relaxa a
semântica nova.** O helper `machine_token()` (`test_delivery_permission.py:90-119`)
ganhou um parâmetro `unscoped: bool = False`, repassado a
`TokenService.issue()`. O único call site que precisa da credencial
pessoal/sem-teto — o "admin" desta tarefa, que autentica através da rota
real `POST /identity/tokens` do jeito que um administrador logado
autenticaria — passou a pedir `unscoped=True` explicitamente
(`test_delivery_permission.py:231-238`), com um comentário explicando por
quê. As outras cinco chamadas de `machine_token()` no mesmo arquivo
(`alertmanager`, `reader`, etc.) continuam com o default `unscoped=False` —
elas testam exatamente a garantia de escopo estreito, e têm que continuar
estreitas.

Verde confirmado por mim, isolado:
```
uv run pytest tests/unit/gateway/webhooks/test_delivery_permission.py -q
```
→ `9 passed`.

### 9.2 Raio de alcance: suíte Python completa, sem `-x`, do início ao fim

A sessão anterior só tinha rodado com `-x` e nunca viu o fim da coleção. Eu
disparei duas rodadas completas sem `-x`:

1. Uma primeira, que **abortou** no meio (só 730 passaram) com
   `_pytest.outcomes.Exit: another run is already writing into the console
   checkout (process 1053069, .../console/.toolchain/tree-writing-suite.lock)`
   — colisão real com a rodada paralela do próprio orquestrador
   (`tests/unit/platform/identity tests/unit/gateway tests/contract`,
   iniciada por volta de 01:27). Não é um achado de produto; é duas suítes
   que escrevem fixture quebrada na mesma árvore ao mesmo tempo, e uma
   delas perde a corrida pelo lock.
2. Depois que os processos do orquestrador terminaram (confirmado por
   `ps` sem achar mais os PIDs), rodei de novo, sozinha, sem colisão:
   ```
   uv run pytest -q --no-header -p no:cacheprovider
   ```
   Resultado real, completo, do início ao fim:
   ```
   11736 passed, 25 skipped, 16 warnings in 615.38s (0:10:15)
   ```
   **Zero falhas em toda a suíte.** Nenhum outro teste, em nenhum pacote,
   dependia da semântica antiga de permissão. Isso fecha a pergunta que a
   sessão anterior deixou aberta ("pode haver mais atrás desse primeiro
   vermelho") — não há.

### 9.3 Os dois falsos-alarme do console-gate que o orquestrador mandou checar

O orquestrador reportou, de uma rodada própria e concorrente
(`tests/unit/platform/identity tests/unit/gateway tests/contract`,
528.83s): `3 failed` — o `test_the_permission_is_grantable_through_the_token_route`
já coberto acima, mais
`tests/contract/console/test_console_gate.py::test_the_same_check_passes_once_the_fixture_is_gone[format-check]`
e `[lint0]`.

**Os dois eram vermelho real no instante em que rodaram, e são colaterais
da edição interrompida — não um bug de produto.** Esse teste específico não
usa fixture nenhuma: ele roda o check de verdade contra a árvore como está
e exige `returncode == 0`. Conferido por mim:

```
uv run python -m tools.console_gate lint
```
→ `EXIT=0`, limpo (o mesmo `TS6133`/`TS2741` de `first-run.tsx`, uma vez
corrigido, também limpou o eslint — mesma causa raiz).

```
uv run python -m tools.console_gate format-check
```
→ vermelho real, visto por mim:
```
[warn] src/components/status.tsx
[warn] tests/unit/surfaces/first-run.test.tsx
[warn] Code style issues found in 2 files. Run Prettier with --write to fix.
console gate: format-check failed — formatting — see the output above
```
Exatamente os dois arquivos que a sessão anterior editou (chips novos em
`status.tsx`; o teste de `fieldLabels` em `first-run.test.tsx`) sem nunca
rodar Prettier. Conserto: `pnpm exec prettier --write` nesses dois arquivos
exatos, nada mais (diff é só formatação — indentação/quebra de linha;
nenhum comportamento mudou). Reconfirmado:
```
uv run python -m tools.console_gate format-check
```
→ `All matched files use Prettier code style!`, `EXIT=0`.

Depois de consertar os dois, rodei os seis casos do teste real,
isoladamente (sem concorrência com mais nada), para ter uma medição limpa:
```
NINJASRE_CONSOLE_TOOLCHAIN=required uv run pytest -q \
  tests/contract/console/test_console_gate.py::test_the_same_check_passes_once_the_fixture_is_gone
```
→ `6 passed in 142.87s` — `format-check` (5.73s), `lint0`/`lint1`/`lint2`
(25-26s cada), `typecheck` (5.99s), `test` (53.65s). **Todos os seis,
verdes.**

**A pergunta que o orquestrador deixou em aberto — por que `[typecheck]`
não tinha falhado enquanto o `tsc` real da árvore estava quebrado — foi
investigada, não deixada sem resposta.** Fui ler `tools/console_gate.py`:
`typecheck` roda `scripted(Check("typecheck", "typecheck", "types"),
toolchain)`, que é `pnpm run typecheck` sem escopo nenhum mais estreito — o
mesmíssimo comando que eu rodei manualmente (`$ tsc --noEmit`, projeto
inteiro), e `format-check`/`lint` seguem o mesmíssimo padrão (`prettier
--check .`, `eslint .`, ambos também projeto inteiro). **Isso descarta
estruturalmente a hipótese de "a fixture mascara o erro real da árvore"**:
não existe caminho de código onde `typecheck` enxergue um subconjunto de
arquivos diferente do que `lint`/`format-check` enxergam.

A explicação que sobra, e a que considero mais provável, é uma corrida de
edição concorrente: `SEEDED` declara `format-check`, depois `lint` (3x),
depois `typecheck`, nessa ordem, e a parametrização de
`test_the_same_check_passes_once_the_fixture_is_gone` segue essa ordem de
declaração. Cada subprocesso (`pnpm run <script>`) leva de 5 a 30+ segundos
para completar; a rodada do orquestrador durou 528.83s. É plausível que meu
conserto em `screens/first-run.tsx` (que fechou o erro de `tsc` real) tenha
aterrissado na árvore compartilhada bem na janela entre `lint0` terminar e
`typecheck` começar. **Não reproduzi essa corrida deliberadamente** (quebrar
a árvore de novo e correr dois processos ao mesmo tempo só para provar o
timing exato seria desproporcional); estou relatando a explicação
estrutural que descarta o "blind spot" com alta confiança, não um fato
forense provado por reconstrução. Nos termos exatos pedidos: **investigado,
não deixado sem checar**, e a conclusão é "provável corrida de edição
concorrente com a própria rodada do orquestrador", não "confirmado por
reprodução".

### 9.4 T013 fechado — o terceiro comportamento agora tem teste dedicado

A sessão anterior deixou nomeado que faltava uma asserção desta sessão
provando que "o teto do emissor continua valendo" através do caminho
completo de `TokenService` (o mecanismo em si — `PermissionSet.narrowed_to`
— já tinha teste próprio e mais antigo,
`tests/unit/platform/identity/test_authorisation.py:179`
`test_a_narrowed_set_holds_no_more_than_the_principal_does`, mas nada
exercitava isso especificamente através de `TokenService.issue()` +
`authenticate()`).

Escrevi
`tests/unit/platform/identity/test_tokens.py::test_a_request_beyond_the_owners_own_permissions_is_narrowed_not_granted`:
um usuário só `Role.VIEWER` pede explicitamente `Permission.ORG_DELETE` na
emissão; a asserção é que o token autenticado não carrega nada.

**Vermelho NÃO observado — dizendo isso sem eufemismo.** Rodei o teste
assim que o escrevi, antes de qualquer mudança adicional:
```
uv run pytest tests/unit/platform/identity/test_tokens.py -k "beyond_the_owners_own_permissions" -q
```
→ `1 passed, 27 deselected in 0.51s`, já na primeira execução. Isso é
**caracterização de comportamento pré-existente e correto**, não conserto —
o mecanismo (`_scoped()` chamando `held.narrowed_to(...)` quando
`token.unscoped` é falso) não foi tocado nesta sessão nem na anterior além
do que T014 já tinha implementado. O teste existe para fechar a lacuna de
prova que a sessão anterior nomeou, não porque algo estava quebrado.
Arquivo inteiro depois:
```
uv run pytest tests/unit/platform/identity/test_tokens.py -q
```
→ `28 passed in 0.57s`.

Com isso, os três comportamentos que T013 pede têm teste dedicado e
nomeado: (1) sem escopos → nada (vermelho confirmado pela sessão anterior,
T014), (2) escopos explícitos → exatamente aqueles (caracterização
pré-existente, sessão anterior), (3) pedir além do teto → narrado para nada
(caracterização, este teste, sessão atual). **T013 marcado em
`tasks.md`.**

### 9.5 T014 — o buraco real que a sessão anterior tinha nomeado mas não visto por inteiro: a coluna nunca chegou ao Postgres

`ApiToken.unscoped` (port, `platform/persistence/ports/identity_repository.py:85`)
e sua leitura em `platform/identity/tokens.py`'s `_scoped()` já existiam.
Mas **nada na camada Postgres lia ou escrevia esse campo**:
`platform/persistence/postgres/models.py`'s `ApiToken` (a tabela real) não
tinha a coluna, e
`platform/persistence/postgres/repositories/identity_repository.py`'s
`_to_token()` (usada por `tokens_for_user()` — o método que
`TokenService.authenticate()` chama para montar o `record` que vai para
`_scoped()`) e `store_token()` simplesmente não mencionavam `unscoped` em
nenhum dos dois sentidos.

**Por que isso tinha que virar coluna, e não algo derivado**: depois desta
feature, uma lista `scopes` vazia é ambígua entre dois significados reais e
ambos ainda necessários — "não pode nada" (o default novo, seguro) e "tanto
quanto o dono aguenta agora" (sessão de navegador, credencial durável
pós-bootstrap). Nada mais na linha permite decidir qual dos dois é o caso:
não o nome (`name` é escolhido por quem chama —
`gateway/http/routes/first_run.py:244` passa `name=body.name`, o corpo da
requisição, então nem o nome da credencial durável é fixo); só um sinal
gravado no momento da emissão resolve a ambiguidade, e é exatamente isso
que `unscoped` é.

**O que eu mudei, com `file:line`:**

- `platform/persistence/postgres/models.py:191` — nova coluna
  `unscoped: Mapped[bool] = mapped_column(Boolean, nullable=False,
  default=False)` na tabela `api_tokens`.
- `platform/persistence/postgres/repositories/identity_repository.py:53` —
  `_to_token()` agora lê `unscoped=row.unscoped`.
- `platform/persistence/postgres/repositories/identity_repository.py:148` —
  `store_token()` agora grava `unscoped=token.unscoped`.
- `platform/persistence/migrations/versions/0012_token_unscoped.py` (novo
  arquivo) — adiciona a coluna (`NOT NULL DEFAULT false`), seguido de um
  `UPDATE` que marca `unscoped = true` só nas linhas cujo `description`
  bate com uma das duas strings fixas que os únicos dois call sites de
  produção que pedem `unscoped=True` sempre escrevem — `"Issued by a local
  sign-in."` (`platform/identity/local_accounts.py`) e `"Established from
  the bootstrap credential at first run."`
  (`platform/startup/bootstrap.py`'s `establish_durable_credential`).
  **Por que `description` e não `name`**: o nome da credencial durável vem
  do corpo da requisição (`body.name` acima) — um operador pode escolher
  outro nome no primeiro uso — enquanto as duas descrições são strings
  fixas que nenhum caminho de chamada real sobrescreve. Casar por nome
  deixaria de fora qualquer deployment cujo administrador tenha renomeado a
  própria credencial no wizard.

**Por que `TokenResolution` (o objeto do caminho quente de
`authenticate()`, vindo de `resolve_token()`) não precisou de `unscoped`
próprio**: conferi `platform/identity/tokens.py`'s `authenticate()` —
`resolve_token()` só serve para localizar qual usuário/token (cache,
roteamento de tenant); a decisão de permissão de verdade busca o `ApiToken`
completo de novo via `tokens_for_user()` (que passa por `_to_token()`, já
consertado) antes de chamar `_scoped(record, permissions)`. Não sobrou
nenhum caminho de autenticação que leia `unscoped` de outro lugar que não
`_to_token()`.

**Validação real feita, e o que não foi possível fazer aqui:**

- A cadeia de migração foi validada de ponta a ponta — **a chamada
  terminou e devolveu resposta, não ficou pela metade**:
  ```
  uv run python -c "
  from platform.persistence.postgres.migrations import head_revision, alembic_config
  from alembic.script import ScriptDirectory
  print('head:', head_revision())
  scripts = ScriptDirectory.from_config(alembic_config())
  for rev in scripts.walk_revisions():
      print(rev.revision, '<-', rev.down_revision)
  "
  ```
  Saída real, completa:
  ```
  head: 0012_token_unscoped
  0012_token_unscoped <- 0011_verifications
  0011_verifications <- 0010_transit
  ... (cadeia inteira, sem lacuna) ...
  0001_initial <- None
  ```
  Uma cabeça só, sem lacuna, `0012` no topo. Essa checagem é só de arquivo
  — não abre conexão com banco nenhum.
- **Não rodei a migração contra um Postgres real** — não há um backend
  Postgres vivo neste sandbox.
  `tests/contract/persistence/test_operations.py` (que tem
  `test_migrations_roll_forward_and_back_over_seeded_data`) já pula aqui
  pelo mesmo motivo (`pytest.skip("Backups, migrations, and at-rest
  encryption are PostgreSQL's.")`) — não é um buraco novo que esta sessão
  abriu, é o mesmo limite que já existia para toda essa suíte.
- **Não rodei `mypy` nem `ruff` nos três arquivos Python que toquei nesta
  subseção** (`models.py`, `identity_repository.py` do Postgres, o novo
  arquivo de migração) — a instrução de parar chegou antes. Nomeando isso
  como pendência real, não escondendo.
- A suíte de identidade/persistência contra `FakePersistence` (que já
  carregava `unscoped` desde a sessão anterior) segue verde —
  `uv run pytest -q tests/contract/persistence/test_identity_repository.py
  tests/unit/platform/persistence/` → `92 passed` — mas essa rodada
  aconteceu **antes** de eu tocar a camada Postgres; não é evidência para
  as três mudanças desta subseção.

**Consequência operacional que a migração cria, dita sem eufemismo**: um
deployment em Postgres que já tenha emitido machine tokens com "nenhum
escopo escolhido" — exatamente o defeito que esta feature existe para
fechar — tem, hoje, tokens que fazem tudo o que o dono faz. Depois desta
migração, a `description` desses tokens não bate com nenhuma das duas
strings fixas, então eles recebem `unscoped=false`: passam a não fazer
nada. Isso é a correção pretendida (fechar o poder que nunca deveria ter
existido), mas é uma quebra visível operacionalmente — qualquer integração
que dependia desse token para de autenticar no instante em que a migração
roda, e precisa de um token reemitido com escopo explícito. Isso pertence
ao runbook de upgrade de um deployment real, mas fica registrado aqui
porque é quem rodar esta migração que precisa saber.

**T014 marcado em `tasks.md`** — a garantia (o campo, a leitura em
`_scoped`, os dois call sites que pedem `unscoped=True` explicitamente)
está implementada de ponta a ponta, inclusive na camada que faltava. A
ressalva sobre Postgres não exercitado ao vivo e sobre `mypy`/`ruff` não
rodados nesses três arquivos fica também na seção 10, abaixo — não
escondida.

### 9.6 T017 e T018, rejulgados

- **T017 continua PARCIAL, não marcado.** Nada nesta sessão escreveu um
  teste dedicado no nível da tela para `machine-token-groups.tsx`'s uso de
  `TokenGroupStateChip` — só o teste de componente (T015) prova o chip em
  isolamento. Sem mudança desde a sessão anterior.
- **T018 agora está FEITO, marcado.** A implementação
  (`console/src/surfaces/first-run/model.tsx`, sessão anterior) e o teste
  dedicado (`tests/unit/surfaces/first-run.test.tsx`, "names a changed
  field by its display name...", vermelho confirmado pela sessão anterior)
  já existiam; o que faltava era o call site real (`screens/first-run.tsx`),
  consertado nesta sessão (seção 9.1). Verde confirmado por mim: `97
  passed` no arquivo de teste inteiro, e `tsc --noEmit` limpo. A tela de
  primeiro uso deixou de estar quebrada.

### 9.7 O que esta sessão não tocou

Por instrução explícita do orquestrador — consertar as duas quebras, medir
o raio de alcance, e então parar sem mais edições de código nem mais
gates — **nenhuma tarefa de US1 (T003, T005 a T012), US2 (T017, T019 a
T024), US3 (T025 a T028) ou Fases 6/7 (T029 a T036) foi iniciada nesta
sessão**, incluindo o item mais crítico apontado pelo orquestrador:
`console/tests/e2e/vocabulary-defaults.acceptance.spec.ts` **continua não
existindo**. As cinco telas que a sessão anterior alterou sem prova
acceptance-first continuam exatamente como a seção 1 deste documento
descreve — nenhuma tela nova foi tocada por mim.

### 9.8 Todo comando desta sessão, com resultado real

```
uv run python -m tools.console_gate typecheck
```
Depois do conserto: `$ tsc --noEmit`, sem erro, `EXIT=0`.

```
pnpm exec vitest run tests/unit/surfaces/first-run.test.tsx
```
`97 passed`.

```
uv run pytest tests/unit/gateway/webhooks/test_delivery_permission.py -q
```
Antes do conserto (mensagem real, reproduzida): `403 == 201` em
`test_the_permission_is_grantable_through_the_token_route`. Depois: `9
passed`.

```
nohup uv run pytest -q --no-header -p no:cacheprovider > full_suite.log 2>&1 &
```
Abortou a meio caminho (`730 passed`) por colisão de lock com a rodada
concorrente do orquestrador (`console/.toolchain/tree-writing-suite.lock`,
processo 1053069). Não é achado de produto.

```
uv run pytest -q --no-header -p no:cacheprovider
```
(segunda tentativa, depois que os processos do orquestrador tinham
terminado, sem concorrência) → **`11736 passed, 25 skipped, 16 warnings in
615.38s (0:10:15)`. Zero falhas.**

```
uv run python -m tools.console_gate lint
```
`EXIT=0`, limpo.

```
uv run python -m tools.console_gate format-check
```
Antes: vermelho real — `[warn] src/components/status.tsx`, `[warn]
tests/unit/surfaces/first-run.test.tsx`, `console gate: format-check
failed`. Depois de `pnpm exec prettier --write src/components/status.tsx
tests/unit/surfaces/first-run.test.tsx`: `All matched files use Prettier
code style!`, `EXIT=0`.

```
NINJASRE_CONSOLE_TOOLCHAIN=required uv run pytest -q \
  tests/contract/console/test_console_gate.py::test_the_same_check_passes_once_the_fixture_is_gone
```
`6 passed in 142.87s` — os seis checks (`format-check`, `lint0`, `lint1`,
`lint2`, `typecheck`, `test`) confirmados verdes de forma isolada, sem
concorrência.

```
uv run pytest tests/unit/platform/identity/test_tokens.py -k "beyond_the_owners_own_permissions" -q
```
`1 passed` já na primeira execução — caracterização, vermelho nunca
observado, dito como tal.

```
uv run pytest tests/unit/platform/identity/test_tokens.py -q
```
`28 passed in 0.57s`.

```
uv run pytest -q tests/contract/persistence/test_identity_repository.py tests/unit/platform/persistence/
```
`92 passed` — antes de tocar a camada Postgres; não cobre `models.py`/
`identity_repository.py` (Postgres) nem a migração nova.

```
uv run python -c "... head_revision() ..."
```
Rodou até o fim e devolveu resposta real (não ficou pela metade): `head:
0012_token_unscoped`, cadeia completa sem lacunas.

Nenhum outro comando de gate ou de teste rodou nesta sessão depois da
instrução de parar. `mypy`/`ruff` não rodaram sobre `models.py`,
`identity_repository.py` (Postgres) nem sobre o arquivo de migração novo —
dito na seção 9.5, não escondido.

### 9.9 Ledger consolidado desta sessão

| Item | Estado | Detalhe |
|---|---|---|
| Typecheck (`fieldLabels`) | **FEITO** | `screens/first-run.tsx:644-650`; `tsc --noEmit` limpo; `first-run.test.tsx` 97 passed. |
| `test_the_permission_is_grantable_through_the_token_route` | **FEITO** | Setup andava de carona no defeito antigo; consertado com `unscoped=True` explícito no único call site que precisa dele (`test_delivery_permission.py:231-238`); os outros cinco call sites do mesmo helper continuam estreitos por default. 9 passed. |
| Raio de alcance da suíte Python | **FEITO** | `11736 passed, 25 skipped, 0 failed` em 615.38s, sem `-x`, sem concorrência. Nenhuma outra dependência da semântica antiga encontrada. |
| Console-gate `[format-check]`/`[lint0]` | **FEITO** | Colaterais da edição não formatada da sessão anterior; `prettier --write` nos dois arquivos exatos; os seis checks parametrizados confirmados verdes isoladamente. |
| Pergunta sobre `[typecheck]` não ter falhado | **Investigado** | Descartado estruturalmente como blind spot do instrumento (mesmo comando, mesmo escopo de projeto inteiro que lint/format-check); explicação mais provável é corrida de edição concorrente com a rodada do orquestrador — não reproduzida deliberadamente, dita como tal. |
| T013 | **FEITO, marcado em tasks.md** | Os três comportamentos têm teste dedicado; o terceiro (teto do emissor) ganhou teste nesta sessão, caracterização, vermelho nunca observado. |
| T014 | **FEITO, marcado em tasks.md** | Garantia completa incluindo a camada Postgres que faltava (`models.py:191`, `identity_repository.py:53,148`, migração `0012_token_unscoped.py`). Ressalva: não exercitado contra Postgres real (sem backend vivo neste sandbox); `mypy`/`ruff` não rodados nesses três arquivos. |
| T017 | **PARCIAL, não marcado** | Sem mudança — nenhum teste dedicado no nível da tela nesta sessão. |
| T018 | **FEITO, marcado em tasks.md** | Call site real consertado; teste dedicado e `tsc` verdes. |
| T003 a T012, T019 a T036 | **NÃO INICIADO** | Não tocados por instrução explícita de parar. Ver seção 10. |

## 10. O que fica pendente agora, nomeado, não escondido

Na ordem do `tasks.md`, o que continua sem começar ou parcial depois desta
sessão:

- **T003** (fixtures: principal inativo + sugestão do estate com recurso
  não resolvível) — não iniciado.
- **T004 — o maior buraco, ainda de pé.**
  `console/tests/e2e/vocabulary-defaults.acceptance.spec.ts` **continua não
  existindo**. Nenhuma prova acceptance-first cobre as cinco telas que já
  mudaram (`members.tsx`, `machine-token-groups.tsx`, `status.tsx`,
  `first-run/model.tsx`, `screens/first-run.tsx`). Isto tem que ser a
  primeira coisa que a próxima sessão faz, antes de tocar qualquer tela
  nova.
- **T005 a T012** — US1 inteira: o formulário de Machine tokens continua
  marcando todos os escopos do emissor por padrão
  (`machine-token-groups.tsx:156`), sem templates de finalidade, sem
  agrupamento por domínio, sem aviso de escopo destrutivo.
- **T017** — teste dedicado no nível de tela para o chip do grupo de token
  (ver seção 9.6).
- **T019 a T024** — resto de US2: títulos `policies.*`/`surfaces.*` (o
  vazamento real está em `console/src/surfaces/preview.tsx:645,673`, não em
  `advanced-config-section.tsx` como `plan.md` diz — achado da sessão
  anterior, ainda não corrigido), Alert intake, evidência da sugestão do
  estate (`platform/estate/suggestions.py:98` já serve `because`; console
  ainda não lê), identificação de sessão, ajuda do grant, grants com role
  legível.
- **T025 a T028** — US3 inteira além da descoberta (T001, que já apontou
  "não existe rota" — nenhuma rota de criação de principal foi desenhada).
- **T029 a T031** — checagem bilíngue formal, remoção dos `fixme` de
  vocabulário da suíte transversal (as sete exceções de `EXCEPTIONS`
  continuam todas de pé), isenção de `vocabulary.spec.ts`.
- **T032 a T036** — polimento, baselines visuais, `scroll-budget.spec.ts`,
  `make verify` completo, este próprio documento (mantido incrementalmente
  a partir de agora, não escrito de uma vez no fim).
- **`mypy`/`ruff` sobre os três arquivos Postgres tocados nesta sessão**
  (`platform/persistence/postgres/models.py`,
  `platform/persistence/postgres/repositories/identity_repository.py`, e
  `platform/persistence/migrations/versions/0012_token_unscoped.py`) —
  ainda não rodados; a instrução de parar chegou antes. É o primeiro gate
  que a próxima sessão deveria rodar, antes de qualquer coisa nova, porque
  é o menor risco de regressão silenciosa sobre trabalho já feito.

Nenhum destes tem dono fora da própria feature 030; nada foi transferido
para outra spec da onda.

---

## 11. Continuação — sessão 3: só T004, o acceptance spec

**Esta sessão teve escopo deliberadamente estreito, imposto pelo
orquestrador: só T004.** Nenhuma tela foi implementada, nenhum vocabulário
foi corrigido, o formulário de token não foi tocado em definitivo — as três
edições de produto descritas abaixo foram reversões temporárias, feitas,
observadas e desfeitas dentro desta mesma sessão, exclusivamente para provar
que os testes escritos aqui realmente pegam a regressão que dizem pegar.
Verificado contra o código real desta árvore agora, branch
`feat/v6-010-provider-out-of-the-box`, ainda em cima de `b4a8153`. Nada
commitado nem staged por este trabalho.

### 11.1 O arquivo

`console/tests/e2e/vocabulary-defaults.acceptance.spec.ts` **agora existe**
— 445 linhas, 14 testes em 7 `describe`, um por alegação normativa que a
tarefa listou. O maior buraco que as seções 1–10 registravam está fechado:
nenhuma tela nova foi tocada por esta sessão, e as cinco telas que sessões
anteriores já haviam alterado (`members.tsx`, `machine-token-groups.tsx`,
`status.tsx`, `first-run/model.tsx`, `screens/first-run.tsx`) agora têm, pela
primeira vez, prova formal contra o mockup — ainda que tardia, para duas
delas (T016/T018), e ainda que essa prova mostre, para uma terceira gaveta
inteira (US1, T005–T012), que nada foi implementado.

Gates rodados só sobre este arquivo, antes de qualquer execução do
Playwright: `pnpm exec tsc --noEmit -p tsconfig.json` (limpo), `pnpm exec
eslint tests/e2e/vocabulary-defaults.acceptance.spec.ts` (limpo) e `pnpm exec
prettier --check tests/e2e/vocabulary-defaults.acceptance.spec.ts` (`All
matched files use Prettier code style!`).

### 11.2 O vermelho de cada alegação, com a mensagem real

Comando de referência, rodado por último contra a árvore inteiramente
restaurada (nenhuma reversão temporária em pé):

```
uv run python -m tools.spec_validation browser \
  --feature specs_v6/030-vocabulario-defaults \
  --test console/tests/e2e/vocabulary-defaults.acceptance.spec.ts
```

Resultado real, completo: `9 failed, 3 skipped, 2 passed (24.3s)`.

**Nove alegações vermelhas hoje, sem precisar de reversão nenhuma — o
recurso simplesmente não existe:**

1. **Zero caixas marcadas** (`vocabulary-defaults.acceptance.spec.ts:48`) —
   `15 scope checkbox(es) start checked on a freshly opened form; the
   default must mark none, so a name typed and "Issue" clicked cannot emit
   more than the purpose asked for`. Contra `machine-token-groups.tsx:156`
   (`useState(new Set(issuedScopes))`), exatamente o defeito que T005/T006
   ainda não fecharam.
2. **Contador de escopos selecionados** (`:65`) — `no element on the issue
   form states how many scopes are currently selected`. Não existe
   `data-testid="scope-selected-count"` em lugar nenhum do código — contrato
   novo que T006 precisa satisfazer.
3. **Template "Alert delivery"** (`:85`) — `no "Alert delivery" purpose
   template control exists on the issue form`. T007/T008 não começaram;
   `machine-token-groups.tsx` não tem noção de template nenhuma.
4. **Agrupamento por domínio** (`:191`) — `15 scope checkboxes render in 0
   named domain group(s); a single flat band is not grouping`. T009/T010 não
   começaram; hoje é um `<fieldset>` único.
5. **Ação primária de criar pessoa** (`:215`) — `no primary create-person
   action exists on Members & roles`. T027/T028 não começaram;
   `members.tsx` não tem esse controle.
6. **`policies.*` como título** (`:269`) — `the schema path
   "policies.masking" is shown as a section title`. Confirma o achado da
   sessão anterior: o vazamento real é em `preview.tsx:645,673`
   (`ConfigEditor`), não em `advanced-config-section.tsx` como `plan.md` diz.
7. **`surfaces.notification_policy` como título** (`:294`) — `the schema
   path "surfaces.notification_policy" is shown as a section title`. Mesma
   causa raiz do item 6.
8. **`webhook.deliver` cru no Alert intake** (`:369`) — `the raw permission
   "webhook.deliver" is shown as the reason a source is trusted, instead of
   the delivery token that actually authenticates it`. Contra
   `alert-intake.tsx:477-479`, exatamente como a sessão anterior já havia
   apontado.
9. **Identificador cru do recurso do estate** (`:382`) — `the evidence
   "Found at http://thicket.example.invalid:9090, on resource
   vm-201-metrics" names the estate's raw resource id rather than a legible
   resource`. O exemplo da spec é `res-8f81848…`; o fixture real desta
   suíte usa outro esquema de id (`vm-201-metrics`, de
   `fixtures/scenarios/populated/integrations.json:46`) para o mesmo
   defeito — checado contra o identificador que este dataset realmente
   carrega, não contra um padrão que nunca bateria nele e não provaria nada.
   Contra `console/src/surfaces/screens/integrations.tsx:435-437`
   (`suggestionOf` só lê `address`/`from_resource` crus, nunca um rótulo
   legível).

**Duas alegações vermelhas só depois de reversão deliberada — o recurso já
existe e funciona; sem a reversão, o teste ficava verde e não provava nada:**

10. **`SERVICE_ACCOUNT`/`HEALTHY` em Members & roles** (`:241`). Reversão:
    `members.tsx` linhas 9 e 139-140 trocadas de volta para
    `<Badge status={text(person,'kind')} />` /
    `<Badge status={flag(person,'is_active') ? 'healthy':'disabled'} />`
    (o import de `AccountStateChip, PrincipalKindChip` trocado por `Badge`).
    Rodado com rebuild completo
    (`uv run python -m tools.spec_validation browser --feature
    specs_v6/030-vocabulario-defaults --test
    console/tests/e2e/vocabulary-defaults.acceptance.spec.ts`, sem
    `--scenario`): vermelho real, `the raw transport value SERVICE_ACCOUNT
    is shown instead of a display name`, `Expected substring: not
    "SERVICE_ACCOUNT"`. A mesma captura de `body.innerText()` desse teste
    (a asserção de `SERVICE_ACCOUNT` falha primeiro e interrompe o teste
    antes de chegar à asserção de `HEALTHY` na mesma função) já contém
    `HEALTHY` quatro vezes no texto capturado — conferido diretamente no log
    bruto, não inferido: a segunda asserção teria falhado do mesmo jeito se
    tivesse chegado a rodar. Depois: `members.tsx` restaurado byte a byte
    (`git diff` contra o `HEAD` mostra exatamente as mesmas linhas que a
    sessão 2 já tinha deixado — `PrincipalKindChip`/`AccountStateChip`, nada
    a mais, nada a menos) e `tsc --noEmit` limpo.
11. **`HEALTHY` no chip de grupo de token em Machine tokens** (`:257`).
    Reversão: `machine-token-groups.tsx` linha 8 e 350 trocadas de volta
    para `import { Badge }` / `<Badge status="healthy" />`. Mesma rodada
    completa: vermelho real, `the raw resource-health word HEALTHY
    describes a token group on this page`, `Expected substring: not
    "HEALTHY"`. Depois: restaurado byte a byte (mesma conferência por
    `git diff`), `tsc --noEmit` limpo.

**Três alegações não puderam ser observadas vermelhas nesta sandbox — ditas
sem eufemismo, com a causa raiz de cada uma, não escondidas atrás de um
`test.skip` mudo:**

12. **Aviso de escopo destrutivo** (`:127`, `describe` "a destructive scope
    warns before it is issued, and never blocks issuing"). **Skip
    observado, vermelho nunca.** Causa: nenhum dos três escopos destrutivos
    (`org.delete`, `owner.assign`, `impersonation.use`) está no conjunto de
    permissões do principal que QUALQUER cenário deste repositório serve.
    Conferido exaustivamente, arquivo por arquivo, não por amostragem:
    `fixtures/scenarios/populated/principal.json`,
    `fixtures/scenarios/first-run/principal.json` e
    `fixtures/scenarios/empty/principal.json` trazem os quinze mesmos
    quinze — a lista `OPERATOR_PERMISSIONS` de
    `tools/mockplane/dataset/served.py:71-90` — e `restricted/principal.json`
    traz os cinco de `VIEWER_PERMISSIONS` (`served.py:92-98`), ainda mais
    curta. `audit-flooded` e `incident-live` não têm `principal.json` próprio
    (herdam o de `populated`). Como `MachineTokenGroups` só renderiza uma
    caixa de escopo por entrada de `issuedScopes` (`viewer.permissions`,
    vindo de `/auth/me`), nenhuma caixa `Org Delete`/`Owner Assign`/
    `Impersonation Use` chega a existir no DOM em nenhum cenário — não há o
    que clicar. **Isto não é o mesmo defeito que os outros dois "achados já
    conhecidos" (T003, seção 5 acima) apontavam** — é uma lacuna nova, mais
    ampla: o principal rotulado `"roles": ["owner"]` em todo fixture nunca
    carrega o conjunto que `/identity/roles` já anuncia como o de "owner"
    (`fixtures/scenarios/populated/roles.json`, trinta permissões, incluindo
    as três destrutivas, `identity.write`, `webhook.deliver`, `sso.manage`,
    `audit.export`, `credential.*`, `estate.*`, `incident.*`,
    `knowledge.write`, `report.read`) — o rótulo do papel e o poder que o
    fixture realmente concede divergem, para todo cenário, não só para este.
    Dito no próprio teste (`vocabulary-defaults.acceptance.spec.ts:154-159`)
    e aqui: a asserção está escrita certa e vai rodar (não pular) no
    instante em que algum cenário conceder um dos três escopos ao seu
    principal — não é a asserção que está errada, é o fixture que nunca
    chega a alimentá-la.
13. **Preview do wizard não nomeia o campo cru** (`:311`). **Skip
    observado sob `populated` (o cenário exigido pelo comando oficial:
    `!new URL(page.url()).pathname.endsWith('/first-run')`, porque um
    deployment com o setup já completo redireciona `/first-run` para fora
    antes de qualquer step renderizar) — mas também nunca vermelho sob
    `--scenario first-run`, o cenário dedicado a um setup incompleto, onde a
    tela realmente chega a renderizar.** Investigado a fundo, não deixado
    como "deu skip e pronto": rodei a suíte inteira contra
    `--scenario first-run` duas vezes — primeiro com o código real (T018 já
    implementado), a alegação passou (`✓`); depois com uma reversão
    deliberada em `screens/first-run.tsx` (`fieldLabels: {}` no lugar do
    mapa real, imports `MODEL_PROVIDER_SETTING`/`MODEL_SETTING` removidos
    temporariamente do bloco de import), rebuild completo, mesma alegação —
    **continuou passando** (`✓` de novo), o que não deveria acontecer se a
    asserção estivesse testando o que diz testar. Para não relatar isso como
    "misterioso", instrumentei o teste com um dump de depuração
    (`expect(text,'DEBUG DUMP').toBe('__DEBUG__')`, descartado depois) e vi
    o conteúdo real do preview: `"Saving this would resolve to:
    investigation.max_loops → 16, investigation.reasoning_effort → high"` —
    nada sobre `models.investigator`, em nenhum dos dois estados do código.
    Causa raiz, cravada no fixture: `/api/preview` responde, em **todo**
    cenário deste repositório, com o mesmíssimo corpo fixo, independente do
    patch pedido — conferido diretamente:
    `fixtures/scenarios/populated/config-preview.json` e
    `fixtures/scenarios/first-run/config-preview.json` têm, byte a byte, a
    mesma lista `changes` (`investigation.max_loops`,
    `investigation.reasoning_effort`), a mesma usada pelo preview de
    Autonomy & guardrails — nunca um `path` de `models.investigator.*`. O
    mock não reage ao corpo da requisição; é uma resposta capturada,
    estática, por endpoint. **Isso não é um problema desta asserção — é uma
    limitação estrutural do plano mock para este endpoint especificamente**,
    e por isso o comportamento que T018 corrigiu está coberto onde ele pode
    de fato variar: o teste de componente
    `console/tests/unit/surfaces/first-run.test.tsx` (mocka a resposta do
    preview; a sessão anterior já confirmou vermelho-depois-verde nele,
    seção 9.1 acima). O teste aqui foi reescrito
    (`vocabulary-defaults.acceptance.spec.ts:311-364`) para verificar o que
    a rota pode honestamente provar — que o mecanismo de preview existe e
    responde — e para se auto-guardar, nomeando esta causa exata, no lugar
    de fingir uma alegação que nenhum cenário jamais vai fazer variar.
    `screens/first-run.tsx` foi restaurado byte a byte depois (`git diff`
    conferido — só a wiring de `fieldLabels` que a sessão 2 já tinha
    deixado, nada a mais).
14. **Sessão ativa identificada por quem/onde** (`:414`). **Skip
    observado, vermelho nunca.** Causa, cravada em código e em todo
    fixture: `tools/mockplane/dataset/served.py:2668` grava o nome da
    sessão do navegador como `"console"` — mas
    `console/src/surfaces/token-identity.ts:33`'s `CONSOLE_SESSION_NAME`
    (o valor que `isConsoleSession` de fato compara) é `'Console sign-in'`.
    Nenhum dos dois bate. Busca exaustiva confirma que nenhum
    `fixtures/scenarios/*/tokens.json` deste repositório usa a string
    `"Console sign-in"` — só `populated/tokens.json:12` chega perto, com o
    valor errado (`"console"`). Consequência: o token que deveria
    representar a sessão do navegador é lido como um machine token comum
    (`SessionPanel` nunca recebe nada; nenhum `data-testid="session-group"`
    chega a existir), em **todo** cenário — não é um problema de qual
    cenário este comando pediu, é a mesma string errada em todo lugar. Isto
    é uma lacuna nova, não nomeada nas seções 1–10 deste documento nem na
    própria seção 5 (que já listava dois buracos de fixture diferentes) —
    o `SessionPanel` de `/settings/members-roles` nunca teve, em nenhuma
    sessão anterior desta feature, uma linha real para uma suíte e2e
    exercitar.

### 11.3 O achado que muda como a próxima sessão deve ler qualquer fixture desta suíte

Os itens 12 e 14 acima não são a mesma lacuna que a seção 5 já registrava
(um principal inativo faltando, uma sugestão sem nome resolvível faltando).
São dois achados novos, mais estruturais:

- **O principal "owner" de todo fixture não carrega o poder que
  `/identity/roles` diz que "owner" carrega.** `served.py`'s
  `OPERATOR_PERMISSIONS` (quinze entradas, linhas 71-90) é uma lista
  escolhida à mão, curada para um "operador" plausível — não o resultado de
  `permissions_for(Role.OWNER)` como `role_records()` (mesmo arquivo, usado
  por `/identity/roles`) de fato calcula. A consequência prática: **nenhum
  teste e2e deste repositório, escrito por qualquer feature, consegue hoje
  exercitar `identity.write`, `webhook.deliver`, `org.delete`,
  `owner.assign`, `impersonation.use`, `sso.manage`, `audit.export`,
  `credential.read`/`write`, `estate.read`/`manage`, `incident.read`/
  `manage`, `knowledge.write` ou `report.read` como concedidos ao viewer
  assinado** — todo `may(viewer, ...)` para essas doze permissões é `false`
  em toda sessão `behaviour` hoje. Isso bloqueia, além dos dois testes desta
  sessão, qualquer verificação futura de T012 (aviso destrutivo) e do lado
  "concedido" de T028 (ação de criar pessoa) contra o cenário `populated`
  por construção — quem implementar essas tarefas vai precisar resolver
  isto primeiro, e não é trabalho desta sessão (T003 é quem toca fixtures;
  eu não toquei nenhum arquivo de fixture).
- **O nome do token de sessão do navegador está errado no fixture desde
  antes desta feature.** `served.py:2668` nunca foi atualizado quando
  `CONSOLE_SESSION_NAME` virou `'Console sign-in'`
  (`token-identity.ts:33`) — não sei quando essa renomeação aconteceu, só
  que o fixture nunca a seguiu. Consequência: o painel "Active sessions" de
  Members & roles está, e sempre esteve nesta árvore, vazio em todo teste
  e2e — não porque não há sessão para mostrar, mas porque a única sessão do
  fixture é classificada errado.

Nenhum dos dois foi corrigido por mim — ambos vivem em
`tools/mockplane/dataset/served.py`, que T003 desta mesma feature toca, mas
cuja correção aqui descrita (permissões do "owner", nome da sessão) vai
além do que T003 já havia levantado. Nomeado aqui para quem pegar T003,
T012 ou T028 em seguida não descobrir isso do zero.

### 11.4 Um teste existente que vai quebrar quando T005/T006 forem feitas — achado, não corrigido

`console/tests/e2e/settings-org.spec.ts:80-91` ("issuing a token offers
scopes to choose rather than a blank slate") afirma hoje
`await expect(scopes.first()).toBeChecked();` — ou seja, um teste **já
commitado** codifica o default inseguro atual (caixa pré-marcada) como o
comportamento correto. Quando T006 implementar o default vazio que esta
mesma feature exige, essa asserção específica vai passar a falhar. Não é
meu escopo tocar esse arquivo (T004 é só o acceptance spec novo), mas quem
fizer T005/T006 precisa saber que esse teste também vai precisar de ajuste
— senão a suíte fica vermelha por um motivo que parece uma regressão e é,
na verdade, a correção pretendida.

### 11.5 tasks.md — não marcado

**T004 não foi marcado em `tasks.md`.** A instrução desta sessão foi
explícita: só marcar se o arquivo existe *e* toda alegação nele foi
observada vermelha. Onze das catorze alegações (nove sem reversão, duas só
com reversão deliberada) foram — com mensagem real citada acima. Três não
foram: cada uma tem investigação própria, causa raiz cravada em código ou
em fixture, e um `test.skip` que nomeia exatamente por quê, em vez de um
skip mudo. Como a condição é "toda alegação", e três não bateram nela por
mais bem fundamentadas que as três explicações estejam, a caixa fica sem
marcar — dito aqui em vez de decidido por mim.

### 11.6 O que fica pendente depois desta sessão, nomeado, não escondido

Tudo que a seção 10 já listava continua exatamente como estava — nenhuma
tela nova foi tocada, T003 e T005 em diante continuam sem começar. O que
esta sessão acrescenta à lista:

- **O gap de permissões dos fixtures** (seção 11.3, primeiro item) — quem
  fizer T003, T011/T012 ou T025-T028 precisa resolver isto antes de esperar
  ver as caixas de escopo destrutivo, o template "Alert delivery" com seu
  próprio escopo, ou a ação de criar pessoa concedida a alguém realmente
  exercitáveis contra `behaviour`.
- **O nome errado do token de sessão do navegador** (seção 11.3, segundo
  item) — bloqueia qualquer prova e2e sobre o painel "Active sessions" até
  ser corrigido em `tools/mockplane/dataset/served.py`.
- **`settings-org.spec.ts:80-91`** (seção 11.4) vai quebrar quando T006 for
  feita; precisa de ajuste na mesma tarefa, não depois.
- **`console/tests/e2e/vocabulary-defaults.acceptance.spec.ts` em si** —
  onze alegações vermelhas prontas para T005–T012, T019–T021, T027/T028
  fazerem passar; três alegações (aviso destrutivo, preview do wizard,
  sessão) que vão continuar de skip até os dois achados acima serem
  corrigidos — a alegação do preview do wizard (item 13) especificamente
  nunca vai deixar de pular via este arquivo até o mock responder
  `/api/preview` de forma sensível ao patch, o que é uma mudança bem maior
  que um fixture — quem chegar lá deve saber que a prova real dessa
  alegação já existe, no teste de componente citado, e não precisa ser
  reinventada aqui.

Nenhum destes tem dono fora da própria feature 030 e da suíte que
`tools/mockplane/dataset/served.py` alimenta; nada foi transferido para
outra spec da onda.

---

## 12. Continuação — sessão 4: só T003 e os dois defeitos estruturais de fixture

**Escopo desta sessão, imposto pelo orquestrador**: fechar T003 propriamente
dito (seção 5 e 11.3 acima já tinham levantado o que faltava) e os dois
achados estruturais da seção 11.3 — as permissões curadas à mão do "owner" e
o nome errado da sessão do navegador — **e nada além disso**. Nenhuma tela,
nenhum vocabulário, nenhum formulário de token, nenhuma rota de criação de
pessoa foi tocado. Verificado contra o código real desta árvore agora,
branch `feat/v6-010-provider-out-of-the-box`, ainda em cima de `b4a8153`.
Nada commitado nem staged por este trabalho — o único arquivo Python tocado é
`tools/mockplane/dataset/served.py`; os únicos outros arquivos tocados são as
sete fixtures que `python -m tools.mockplane build` reescreveu a partir dele,
mais este documento e o `tasks.md`.

### 12.1 O que foi adicionado, e por quê

**T003 propriamente dito** — as duas lacunas que a seção 5 e o item 5 do
`tasks.md` nomeavam:

- **Um principal inativo.** `tools/mockplane/dataset/served.py:64`
  (`FORMER: Final = "user-departed"`) e `served.py:2453-2459` (a entrada em
  `USERS`, `"kind": "user"`, `"is_active": False`) — uma pessoa que já teve
  acesso e não tem mais. Reflete em
  `fixtures/scenarios/populated/principals.json` depois do rebuild.
- **Uma sugestão do estate cujo recurso só tem identificador.** A sugestão
  que já existia (`metrics-store`, `served.py:1760-1794`, achada e verificada
  como "resolvível" já na sessão anterior — o `because` nomeia um recurso com
  rótulo, "a guest labelled prometheus") ficou como está. O que faltava era o
  outro lado do mesmo `because` que `platform/estate/suggestions.py:98`
  produz: o *fallback* para `resource.resource_id!r` quando
  `resource.display_name` está vazio. Implementado em
  `served.py:1702-1750` (`integration_records()`): em vez de inventar uma
  quarta integração fictícia — o que teria mudado a própria narrativa do
  docstring da função ("dois conectados e verificados, um conectado e
  falhando, um só sugerido") — anexei a sugestão a uma das integrações
  *reais*, não instaladas, que a função já camada por baixo das três
  fictícias (`integration_catalogue(configured=frozenset())`,
  `served.py:1723-1725`). Escolhida `redis` (`served.py:1728`), por nome,
  determinística: `entry["suggested"]` recebe um endereço, um
  `from_resource` sem nome nenhum por trás (`"ct-9042"`, um id que não
  aparece em `estate-resources.json` — confirmado, `from_resource` não é uma
  referência que `tools/mockplane/verify/referential.py` verifica, então essa
  liberdade é real, não um buraco de cobertura) e um `because` na mesma forma
  exata que o fallback real produz: `"this estate holds a container called
  'ct-9042' at 10.20.0.187, which is..."` — aspas simples ao redor do id,
  como `!r` do Python produz, não um nome. Reflete em
  `fixtures/scenarios/populated/integrations.json` depois do rebuild.

**Os dois achados estruturais da seção 11.3** — nomeados lá, não corrigidos
até agora:

- **O "owner" de todo fixture não carregava o que `/identity/roles` diz que
  um owner carrega.** `served.py:82-89` — `OPERATOR_PERMISSIONS` e
  `VIEWER_PERMISSIONS` deixaram de ser tuplas literais escolhidas à mão e
  passaram a `tuple(sorted(permission.value for permission in
  permissions_for(Role.OWNER)))` / `permissions_for(Role.VIEWER)` — o mesmo
  mecanismo que `role_records()` (`served.py`, inalterado) já usava para
  servir `/identity/roles`. Antes: quinze permissões coladas à mão. Depois:
  as trinta e uma que `permissions_for(Role.OWNER)` de fato computa — as
  quinze antigas mais `report.read`, `estate.read`, `estate.manage`,
  `incident.read`, `incident.manage`, `webhook.deliver`, `knowledge.write`,
  `credential.read`, `credential.write`, `identity.write`, `sso.manage`,
  `impersonation.use`, `audit.export`, `org.manage`, `org.delete`,
  `owner.assign` — dezesseis a mais, conferidas uma a uma contra o catálogo
  em `platform/identity/permissions.py` antes de escrever este parágrafo.
  Reflete em `fixtures/scenarios/populated/principal.json`,
  `fixtures/scenarios/empty/principal.json`,
  `fixtures/scenarios/first-run/principal.json` e
  `fixtures/scenarios/restricted/principal.json` (o viewer) depois do
  rebuild.
- **O token da sessão do navegador estava classificado errado.**
  `served.py:2688-2700` — o `"name"` do `tok-0001` (dentro de
  `identity_records()`) era `"console"`; virou `"Console sign-in"`, a string
  exata que `console/src/surfaces/token-identity.ts:33`'s
  `CONSOLE_SESSION_NAME` compara. Comentário deixado na própria linha
  explicando o predicado, para não se repetir o mesmo desencontro na próxima
  vez que esse nome mudar de um lado só. Reflete em
  `fixtures/scenarios/populated/tokens.json` depois do rebuild.

Nada mais foi tocado em `USERS`, `GRANTS` ou nas fixtures — o grupo de
tokens em uso (`scheduler`) e nunca usado (`bootstrap`, quinze linhas) já
existiam e não precisaram de nada novo, como a seção 5 já registrava.

### 12.2 Rebuild e a suíte de contrato de fixtures

```
uv run python -m tools.mockplane build
```
→ `wrote 227 files across 6 scenarios`. Sete arquivos saíram do `git status`
como modificados — exatamente os que os quatro achados acima tocam, nenhum a
mais: `fixtures/scenarios/empty/principal.json`,
`fixtures/scenarios/first-run/principal.json`,
`fixtures/scenarios/populated/integrations.json`,
`fixtures/scenarios/populated/principal.json`,
`fixtures/scenarios/populated/principals.json`,
`fixtures/scenarios/populated/tokens.json`,
`fixtures/scenarios/restricted/principal.json`. Nenhum arquivo sob
`fixtures/scenarios/` foi editado à mão — todos os sete vieram deste
comando.

```
uv run pytest -q tests/contract/fixtures
```
→ **`107 passed in 10.54s`** — inclui o teste de rebuild byte-idêntico
(`test_rebuilding_the_dataset_reproduces_what_is_committed`), a coerência
entre cenários, e a validação de cada fixture contra o documento OpenAPI
gerado, para os seis cenários.

```
uv run pytest -q tests/unit/tools/mockplane/
```
→ **`183 passed in 3.63s`**.

```
uv run ruff format tools/mockplane/dataset/served.py
```
→ `1 file reformatted` (só a formatação do bloco novo — indentação e quebra
de linha; nenhum comportamento mudou).

```
uv run ruff check tools/mockplane/dataset/served.py
```
→ `All checks passed!`

```
uv run mypy tools/mockplane/dataset/served.py
```
→ `Success: no issues found in 1 source file`.

```
make check-imports
```
→ `Contracts: 7 kept, 0 broken.`

```
make check-constants
```
→ limpo (nenhum output de erro; `tools/check_constants.py` retornou `0`).

### 12.3 A medição pedida: os três projetos do Playwright, com o delta real

**`first-day`** (cenário `first-run`):
```
uv run python -m tools.console_e2e run --project first-day --scenario first-run
```
→ **`15 passed (9.4s)`, `EXIT=0`. Nada mudou.** `first_run_records()` também
lê `identity_records()` e portanto também herda o `principal` recalculado, e
nada nesse cenário quebrou.

**`behaviour`** (cenário `populated`):
```
uv run python -m tools.console_e2e run --project behaviour
```
→ **`168 passed, 12 failed, 21 skipped (1.5m)`, `EXIT=1`.**

As doze falhas, uma a uma — nenhuma escondida atrás de uma média:

1. **Nove são o vermelho que a sessão 3 já tinha documentado e observado,
   inalterado por esta sessão**, em
   `vocabulary-defaults.acceptance.spec.ts` — as linhas 48, 65, 85, 191, 215,
   269, 294, 369 e 382 (contador de escopo zerado, contador numérico,
   template "Alert delivery", agrupamento por domínio, ação de criar pessoa,
   títulos `policies.*`/`surfaces.*` em duas telas, `webhook.deliver` cru no
   Alert intake, e a evidência de `vm-201-metrics` na sugestão de
   `metrics-store`). Todas continuam vermelhas pela mesma causa que a seção
   11.2 já cravou — nenhuma delas depende de fixture; todas dependem de
   telas que T005–T012, T019–T021 ou T027/T028 ainda não construíram. A
   linha 382 merece uma nota: o teste itera **todas** as evidências de
   sugestão da página, e agora há duas (`metrics-store` e a `redis` nova
   desta sessão) — a nova não contém `vm-201-metrics`, então não é ela quem
   reprova a asserção; é a mesma `metrics-store` de sempre, do jeito que já
   era antes desta sessão.
2. **Duas são a consequência direta, prevista antes de eu tocar qualquer
   arquivo, dos dois achados estruturais desta sessão** — os dois testes que
   a sessão 3 tinha deixado em `test.skip` nomeado, por fixture insuficiente:
   - `vocabulary-defaults.acceptance.spec.ts:127` ("a destructive scope warns
     before it is issued..."). Antes: pulava, porque nenhum principal servido
     tinha `org.delete`/`owner.assign`/`impersonation.use`. Agora o operador
     tem os três (seção 12.1) — o `test.skip(target === undefined, ...)` não
     dispara mais, a caixa `Org Delete` (ou uma das outras duas) existe no
     DOM, e o teste tenta clicar e checar um aviso que **T012 ainda não
     construiu**. Falha real, mensagem real:
     ```
     Error: checking scope-org.delete produced no warning naming what it permits
     Locator:  getByTestId('destructive-scope-warning')
     Expected: 1
     Received: 0
     ```
     (`scope-org.delete` porque é a primeira das três caixas que o DOM
     oferece; a asserção em si — `console/tests/e2e/vocabulary-defaults.acceptance.spec.ts:178`
     — não muda por qual das três é encontrada primeiro. Não é meu defeito;
     é T012, fora do escopo desta sessão).
   - `vocabulary-defaults.acceptance.spec.ts:414` ("a session group names an
     origin..."). Antes: pulava, porque nenhum fixture nomeava sua sessão
     `"Console sign-in"`. Agora `served.py:2700` nomeia — `session-group`
     renderiza (`rendered = 1`, não `0`), o skip não dispara, e a asserção
     seguinte reprova porque **T022 ainda não construiu** `session-origin`:
     ```
     Error: no session on this page states where it came from — only who
     holds it and a count
     Locator:  getByTestId('session-group').first().getByTestId('session-origin')
     Expected: 1
     Received: 0
     ```
   Nenhuma das duas é um defeito desta sessão — são exatamente o
   "desbloqueado por construção" que a instrução original já nomeava. As
   fixtures agora servem o dado certo; as telas que consomem esse dado ainda
   não existem, e não são meu escopo.
3. **Uma é nova, fora de `vocabulary-defaults.acceptance.spec.ts`, e é
   inteiramente causada pelo achado das permissões** —
   `tests/e2e/settings-nav.spec.ts:68` ("shows the subnav, grouped by
   intention, with the first reachable page already open"). Mensagem real:
   ```
     Locator: getByTestId('settings-subnav').locator('[data-testid="settings-nav-entry"]')
     - Expected  - 0
     + Received  + 1
       Array [
         "Members & roles",
     +   "Single sign-on",
         "Machine tokens",
         ...
   ```
   Causa, cravada em código antes mesmo de rodar o teste:
   `console/src/shell/routes.ts:548` declara `permission: 'sso.manage'` para
   a página "Single sign-on"; `settingsGroupsFor()`
   (`console/src/shell/routes.ts:661`) filtra a subnav de toda página
   `/settings/*` por essa permissão (`visibleSettingsPages`); o operador
   nunca tinha `sso.manage` antes desta sessão, então "Single sign-on"
   estava ausente da subnav — não desabilitada, ausente, exatamente a regra
   que `console/src/shell/sidebar.tsx`'s próprio comentário descreve para a
   navegação principal e que a subnav de Settings segue igual. Este teste
   **não pertence a esta feature nem a `tasks.md`** — é um teste já
   committed de uma feature anterior que fixava a lista antiga de sete
   páginas visíveis como se fosse a lista completa. Não é meu escopo tocá-lo
   (T003 é fixtures, não telas nem specs de outras features), mas fica
   nomeado aqui porque é uma consequência real e vai continuar vermelho até
   alguém acrescentar `'Single sign-on'` na lista esperada dessa linha 93 do
   próprio arquivo.

**`visual`** (via `make console-visual`, dentro do container fixado):
```
uv run python -m tools.console_gate visual
```
→ **`4 failed, 26 passed (25.6s)`, `EXIT=1`, gate: `visual failed`.**

Quatro baselines já aceitas divergem — nenhuma tocada, nenhuma aceita,
nenhum `console-visual-accept` rodado:

| Baseline | Pixels diferentes | Causa |
|---|---|---|
| `single-sign-on-1440-light` | 3014 (0.01) | A subnav de Settings ganhou a entrada "Single sign-on" — a mesma causa de `settings-nav.spec.ts` acima, agora visível em pixel. |
| `models-providers-1440-light` | 3015 (0.01) | Mesma causa — a subnav é compartilhada por toda página `/settings/*`. |
| `notifications-1440-light` | 3021 (0.01) | Mesma causa. |
| `machine-tokens-1440-light` | 27329 (0.02); a imagem inteira mudou de 963px para 900px de altura | **Duas causas somadas**: a mesma entrada nova na subnav, **mais** o token `tok-0001` (agora nomeado `"Console sign-in"`) sumindo da lista de Machine tokens — `settings/machine-tokens.tsx:75-77` já filtrava por `isConsoleSession`, e antes essa checagem nunca reconhecia esse token como sessão (o nome não batia), então ele aparecia ali como se fosse mais um token de máquina chamado "console". Agora é reconhecido e sai da lista — uma linha a menos, página mais baixa. |

As outras vinte e seis baselines registradas — `agent-*`, `decisions-*`,
`gallery-*` (seis variações), `incident-1440-light`, `resources-*` (duas),
`run-detail-*` (duas), `shell-*` (quatro), `sign-in-1440-light` — **ficaram
byte-idênticas**. Isso descarta, com medição e não com suposição, dois
riscos que eu tinha levantado antes de mudar qualquer coisa: o botão
"Impersonate" novo em `console/src/shell/topbar.tsx:223` (`may(viewer,
'impersonation.use')`, agora verdadeiro) fica dentro de um `<details>`
fechado por padrão e não aparece em nenhuma captura; e o controle que
`detector-controls.tsx:147` (`incident.manage`, agora verdadeiro) passou a
renderizar não cai em nenhuma rota com baseline aceita hoje.

**Nenhuma baseline foi aceita, sobrescrita ou tocada por mim.** Os quatro
diffs (`test-results/screens-*-matches-its-baseline-visual/*-diff.png`) e os
próprios PNGs capturados ficaram em `console/test-results/` — não commitado,
não staged, e fora de `console/visual/baselines/`, que continua byte a byte
o que já estava commitado (`git status --porcelain console/visual/` não
lista nada).

### 12.4 Isto é maior que esta fatia?

**Não no sentido de "a correção da fixture ficou incompleta ou é maior do
que parece"** — os quatro itens do parágrafo 12.1 estão prontos, provados
por `file:line`, e a suíte de contrato de fixtures (107 testes) mais o
rebuild byte-idêntico confirmam que o gerador continua a única rota e que
nada foi editado à mão sob `fixtures/scenarios/`.

**Sim, no sentido em que a própria instrução já antecipava**: corrigir o
que o "owner" de fato detém tem um raio de alcance real, medido agora em vez
de suposto, e ele ultrapassa esta fatia em três frentes concretas, nenhuma
delas fixture:

1. **Quatro baselines visuais já aceitas precisam de decisão do operador** —
   aceitar as quatro capturas novas (revisando cada uma, não em lote) ou
   reverter a correção das permissões. Isso não é meu para decidir nem para
   executar.
2. **Um teste já committed de outra feature (`settings-nav.spec.ts:68`)
   ficou vermelho** por uma asserção que fixava a lista antiga de páginas de
   Settings como completa. Conserto mecânico (uma linha), mas o arquivo não
   é meu — não pertence a `tasks.md` desta feature.
3. **Duas alegações do próprio acceptance spec desta feature** (linhas 127 e
   414) trocaram de "pula, porque a fixture não alimenta" para "reprova,
   porque a tela ainda não existe" — o resultado correto e esperado do ponto
   de vista de teste-primeiro, mas um estado a mais que quem fizer T012 e
   T022 vai encontrar (e deveria esperar encontrar, porque agora são as
   fixtures certas provando a lacuna certa).

Nenhum dos três é "fixtures ainda por fazer" — os quatro itens que este
T003 e os dois achados estruturais pediam estão feitos. É o raio de alcance
*de fora* da fixture que ficou maior do que uma correção isolada, e por
construção: um "owner" que finalmente detém o que `/identity/roles` sempre
disse que um owner detém deixa de ser um segredo que nenhuma tela jamais
precisou encarar. Reportado com os números acima para o operador decidir,
como a instrução pediu — não decidido, não revertido, não escondido.

### 12.5 O que fica pendente, nomeado, não escondido

- **As quatro baselines visuais** (seção 12.3) — decisão do operador:
  aceitar (`make console-visual-accept`, revisão manual de cada PNG antes de
  commitar) ou reverter a correção de `OPERATOR_PERMISSIONS`. Não fiz
  nenhuma das duas.
- **`console/tests/e2e/settings-nav.spec.ts:93-99`** — a lista esperada da
  subnav de Settings precisa de `'Single sign-on'` entre `'Members & roles'`
  e `'Machine tokens'`. Não é T003; não toquei.
- **As duas alegações de `vocabulary-defaults.acceptance.spec.ts` que agora
  reprovam em vez de pular** (linhas 127 e 414) — corretas assim; fecham
  quando T012 e T022, respectivamente, forem implementadas. Não é T003; não
  toquei.
- **Tudo que a seção 10 já listava e este trabalho não tocou** — T004 (o
  acceptance spec em si, cujo próprio julgamento de "marcado" pertence a
  quem o escreveu, não a esta sessão — ver nota abaixo), T005 a T012, T017,
  T019 a T028, T029 a T036. Nenhum deles foi tocado por esta sessão.

**Uma nota sobre T004, sem marcar nada por conta própria**: com os dois
achados fechados, treze das catorze alegações de
`vocabulary-defaults.acceptance.spec.ts` agora rodam e são observadas
vermelhas (nove sem depender de fixture, mais as duas que trocaram de skip
para fail acima, mais as duas que só ficavam vermelhas com reversão
deliberada, já registradas na seção 11.2) — só a do preview do wizard
(linha 311) continua de skip, pela limitação estrutural do mock já
documentada (`/api/preview` responde fixo, independente do patch, em todo
cenário). Se isso muda o julgamento de T004 é decisão de quem escreveu esse
critério — não mudei a caixa em `tasks.md`.

### 12.6 Todo comando desta sessão, com resultado real

```
uv run ruff format tools/mockplane/dataset/served.py
```
`1 file reformatted`.

```
uv run ruff check tools/mockplane/dataset/served.py
```
`All checks passed!`

```
uv run mypy tools/mockplane/dataset/served.py
```
`Success: no issues found in 1 source file`.

```
uv run python -m tools.mockplane build
```
`wrote 227 files across 6 scenarios`.

```
uv run pytest -q tests/contract/fixtures
```
`107 passed in 10.54s`.

```
uv run pytest -q tests/unit/tools/mockplane/
```
`183 passed in 3.63s`.

```
make check-imports
```
`Contracts: 7 kept, 0 broken.`

```
make check-constants
```
Limpo, sem saída de erro.

```
uv run python -m tools.console_e2e run --project behaviour
```
`168 passed, 12 failed, 21 skipped (1.5m)`, `EXIT=1` — detalhado na seção
12.3.

```
uv run python -m tools.console_e2e run --project first-day --scenario first-run
```
`15 passed (9.4s)`, `EXIT=0`.

```
uv run python -m tools.console_gate visual
```
`4 failed, 26 passed (25.6s)`, `EXIT=1` — detalhado na seção 12.3. Nenhuma
baseline aceita nem sobrescrita.

Verificado ao final: `docker ps -a` sem contêineres residuais; `ps aux` sem
processo de Playwright, uvicorn ou servidor Node do console residual;
`git status --porcelain` só lista os arquivos nomeados nas seções 12.1 e
12.2, mais os que já estavam modificados/staged antes desta sessão começar
(inalterados por mim, conferido linha a linha contra a lista da seção 1).

---

## 13. Continuação — sessão 5: T005 a T012, a metade console de US1

**Escopo desta sessão, imposto pelo orquestrador**: só T005 a T012 — o
formulário de emissão de Machine tokens (default vazio, contador, templates
de finalidade, agrupamento por domínio, aviso de escopo destrutivo) — mais o
ajuste, na mesma tarefa, de um teste committed que protegia o default
inseguro (`settings-org.spec.ts`). T017, T019 a T024 (resto de US2), T025 a
T028 (US3), e tudo a partir de T029 **não foram tocados**. Nenhuma baseline
visual foi aceita, sobrescrita ou tocada. Verificado contra o código real
desta árvore agora, branch `feat/v6-010-provider-out-of-the-box`, ainda em
cima de `b4a8153`. Nada commitado nem staged por este trabalho — as duas
renomeações já staged antes desta sessão (`010-provider-out-of-the-box` →
`provider-out-of-the-box`, `020-confiabilidade-telas` →
`screen-truthfulness`) continuam exatamente como estavam, não tocadas.

### 13.1 O chão em que esta sessão pisou

Antes de qualquer edição: `console/tests/e2e/vocabulary-defaults.acceptance.spec.ts`
já existia (sessão 3), e as fixtures já tinham sido corrigidas (sessão 4) —
o `owner` de todo cenário carrega hoje as 31 permissões que
`permissions_for(Role.OWNER)` de fato computa, `org.delete`, `owner.assign` e
`impersonation.use` incluídas. Isso é o que torna T011/T012 prováveis pela
primeira vez nesta feature: antes da sessão 4, nenhuma caixa de escopo
destrutivo jamais existia no DOM sob nenhum cenário servido.

### 13.2 T005/T006 — o formulário abre sem poder nenhum, e diz quantos estão marcados

**Defeito, antes desta sessão**: `console/src/surfaces/machine-token-groups.tsx:156`
fazia `useState<ReadonlySet<string>>(new Set(issuedScopes))` — todo escopo do
emissor vinha pré-marcado.

**Teste novo, vermelho confirmado antes de qualquer implementação** — comando
e mensagem real na seção 13.9. Cinco `it()` novos ou reescritos em
`console/tests/unit/surfaces/machine-token-groups.test.tsx`:

- `:275` "offers every one of the viewer's own permissions as a scope to
  choose, none of them checked" — substitui o teste antigo que afirmava o
  oposto (`toBeChecked()`), com o nome corrigido para dizer a verdade nova.
- `:289` "issues only the scopes explicitly checked by hand" — reescrito para
  marcar explicitamente em vez de desmarcar a partir de um estado pré-marcado.
- `:309` "checking a scope and then unchecking it leaves it out again" —
  idem, reescrito.
- `:331` "states the selected-scope count as zero when the form first opens".
- `:344` "updates the selected-scope count as boxes are checked and
  unchecked".

**Implementado**: `machine-token-groups.tsx:254`,
`useState<ReadonlySet<string>>(new Set<string>())`; o contador em
`machine-token-groups.tsx:384-394` (`data-testid="scope-selected-count"`,
`formatCount` com as chaves novas `settings.machineTokens.scopesSelected(.one)`).
Verde confirmado: seção 13.9.

### 13.3 T007/T008 — templates de finalidade como constantes nomeadas

**Teste novo, vermelho confirmado**: cinco `it()` em
`machine-token-groups.test.tsx:396-485`, `describe('a purpose template marks
only what it promises', ...)` — "Alert delivery" marca exatamente
`webhook.deliver` (`:397`); "Read-only automation" marca só escopos de
leitura (`:415`); a seleção de um template continua ajustável à mão depois
(`:433`); um template substitui, não soma, uma seleção manual anterior
(`:451`, além do que a tarefa pedia — escrito para deixar essa direção
provada, não só suposta); um template fora do teto do emissor aparece
desabilitado, dizendo por quê (`:469`).

**Implementado**, `machine-token-groups.tsx`:

- `PurposeTemplate` (interface, `:57-70`) e `PURPOSE_TEMPLATES` (constante
  nomeada, `:79-94`) — dois templates: `alert-delivery` (escopo fixo,
  `ALERT_DELIVERY_SCOPE = 'webhook.deliver'`, `:52`) e
  `read-only-automation` (escopo dinâmico: todo escopo do emissor cujo verbo,
  a parte depois do ponto, é `read` — `:91-92`). Nenhum literal de escopo
  disperso no ponto de uso: os dois `scopesFor` são a única leitura de nomes
  de escopo do arquivo inteiro fora de `DESTRUCTIVE_SCOPES`.
- **Decisão de design, registrada aqui para quem continuar**: "Read-only
  automation" não é uma lista fixa de todo escopo `.read` do catálogo — é
  `issuedScopes.filter(...)`, ou seja, deriva do que o emissor já detém. Isso
  torna esse template estruturalmente incapaz de ultrapassar o teto (FR-017
  nunca se aplica a ele por construção, só a "Alert delivery"), e evita
  exatamente o problema que a Assumption da spec nomeia para o agrupamento
  por domínio — um catálogo paralelo de escopos de leitura que este arquivo
  teria que manter em dia toda vez que `platform/identity/permissions.py`
  ganhar uma permissão nova.
- Botão de template (`:398-426`), `data-testid={`scope-template-${id}`}`;
  frase de propósito sempre visível; razão do desabilitado
  (`data-testid={`scope-template-${id}-reason`}`) só quando desabilitado.
  `applyTemplate` (`:357-359`) substitui o conjunto inteiro
  (`setScopes(new Set(template.scopesFor(issuedScopes)))`), nunca soma —
  exatamente o que FR-013 ("marca X e nada mais") exige.

Chaves i18n novas, inglês e português no mesmo passo (seção 13.7 confere o
par completo): `settings.machineTokens.template.alertDelivery.{name,purpose}`,
`settings.machineTokens.template.readOnlyAutomation.{name,purpose}`,
`settings.machineTokens.template.disabled`.

### 13.4 T009/T010 — agrupamento por domínio, derivado do nome do escopo

**Teste novo, vermelho confirmado**: três `it()`,
`machine-token-groups.test.tsx:487-539`, `describe('scopes render grouped by
domain', ...)` — mais de um grupo nomeado quando os escopos abrangem mais de
um domínio (`:488`); todo escopo oferecido cai em exatamente um grupo,
contado por `getAllByRole('checkbox')` somado por grupo (`:501`); o nome do
grupo é legível, não a palavra crua do domínio (`:526`).

**Implementado**: `domainOf` (`machine-token-groups.tsx:171-174`) — o texto
antes do primeiro ponto do escopo; `groupedByDomain` (`:190-202`) — um grupo
por domínio, na ordem de primeira aparição; render em `:428-451`,
`<fieldset data-testid="scope-group">` por grupo, `<legend>` com
`humanize(group.domain)`.

**Decisão de design, e a tensão que ela resolve**: a Key Entity da spec cita
"organização, identidade, investigação, configuração, entrega" como exemplo
dos nomes de domínio — mas essas cinco palavras não são, literalmente, o
texto antes do ponto de nenhuma permissão real (`webhook.deliver` tem domínio
`webhook`, não `entrega`/`delivery`; `org.delete` tem domínio `org`, não
`organização`). Mapear cada uma das ~20 permissões reais para um desses cinco
baldes exigiria uma tabela de tradução domínio→balde mantida à mão — que é
exatamente o "catálogo paralelo a manter" que a seção Assumptions da spec
proíbe explicitamente ("O agrupamento de escopos por domínio deriva do
próprio nome do escopo, sem catálogo paralelo a manter"). Segui a Assumption
como a regra que manda, não o exemplo ilustrativo: o domínio é
mecanicamente `scope.split('.')[0]`, o mesmo segmento que
`platform/identity/permissions.py`'s `Permission.domain` já declara ser "o
que uma consulta de audit agrupa por" — então um `owner` real (31 permissões)
vê algo entre quinze e vinte grupos, não cinco. Nenhum teste que escrevi ou
que já existia fixa um número exato de grupos ou os nomes "organização" /
"entrega" especificamente; a alegação real do acceptance spec
(`vocabulary-defaults.acceptance.spec.ts:191-209`) só verifica `groupCount >
1`, que este desenho satisfaz com folga.

### 13.5 T011/T012 — o aviso de escopo destrutivo

**Teste novo, vermelho confirmado**: três `it()`,
`machine-token-groups.test.tsx:541-597`, `describe('a destructive scope warns
before it is issued, and never blocks issuing', ...)` — marcar `Org Delete`
nomeia o que ele permite, desmarcar retira o aviso (`:542`); `Impersonation
Use` tem sua própria consequência nomeada, não uma mensagem genérica
(`:564`); marcar um escopo destrutivo nunca desabilita o botão Issue
(`:581` — este terceiro passou já na primeira execução, porque o botão Issue
só depende de `name.trim()`, nunca dos escopos marcados; caracterização, não
correção, dito sem eufemismo na seção 13.9).

**Implementado**: `DESTRUCTIVE_SCOPES` (constante nomeada,
`machine-token-groups.tsx:101-105`) — `org.delete`, `owner.assign`,
`impersonation.use`, cada um apontando para uma chave i18n com o que aquele
escopo permite. `checkedDestructiveScopes` (`:362-364`) filtra por
`Object.entries` (não por indexação crua em `scopes`, que sob
`noUncheckedIndexedAccess: true` devolveria `MessageKey | undefined` e
pediria um `as` — `Object.entries` já tipa o segundo elemento da tupla como
`MessageKey`, sem cast). Render em `:453-461`, um `<p
data-testid="destructive-scope-warning">` por escopo destrutivo marcado — se
dois estiverem marcados ao mesmo tempo, dois blocos existem, cada um por seu
próprio nome (não testado aqui por não ser o que a alegação do acceptance
spec exercita, mas é o comportamento real do código, dito para quem olhar).

Chaves i18n novas:
`settings.machineTokens.destructiveScope.{orgDelete,ownerAssign,impersonationUse}`.
Os nomes das caixas em si (`Org Delete`, `Owner Assign`, `Impersonation Use`)
continuam vindos de `humanize()`, sem tradução — mesma convenção
pré-existente de todo rótulo de escopo neste formulário; o texto do aviso
cita esses mesmos nomes em inglês mesmo no catálogo pt-BR, deliberadamente,
para que o aviso continue nomeando exatamente a caixa que está ao lado dele.

### 13.6 O teste committed que protegia o default inseguro, corrigido nesta mesma tarefa

`console/tests/e2e/settings-org.spec.ts:80-91` afirmava
`await expect(scopes.first()).toBeChecked();` sob o nome "issuing a token
offers scopes to choose rather than a blank slate" — um teste já committed
codificando o defeito como comportamento correto, exatamente o caso que a
instrução desta tarefa nomeou de antemão. Renomeado para "issuing a token
offers scopes to choose, none of them pre-selected"; assertiva trocada para
`.not.toBeChecked()`; comentário reescrito para explicar a troca em vez de
deixar uma frase presa ao comportamento antigo. Verde confirmado isolado
(seção 13.9) — os 7 testes do arquivo inteiro passam, incluindo este.

### 13.7 A prosa desatualizada do acceptance spec, corrigida junto com a alegação que ela descrevia

`console/tests/e2e/vocabulary-defaults.acceptance.spec.ts` já continha, desde
a sessão 3, a alegação do aviso de escopo destrutivo (linha 127) com um
`test.skip` guardado por comentário que dizia, no bloco da doc do módulo
(linhas 32-38 de antes) e no comentário junto ao próprio `test.skip`
(linhas 144-160 de antes): "nenhum cenário servido concede
`org.delete`/`owner.assign`/`impersonation.use` a ninguém — a alegação nunca
roda de verdade em nenhum cenário". Isso era verdade quando escrito (sessão
3, antes da sessão 4 corrigir as fixtures) e passou a ser falso depois da
sessão 4 — mas ninguém tinha atualizado a prosa, porque ninguém tinha voltado
a essa alegação especificamente até agora. Segui o mesmo princípio já
aplicado em `settings-nav.spec.ts` (achado de sessão anterior a esta) e em
`settings-org.spec.ts` (seção 13.6 acima): quando o sentido de uma asserção
muda, a prosa ao redor muda junto. Reescrevi:

- O parágrafo da doc do módulo (`vocabulary-defaults.acceptance.spec.ts:32-38`
  antes da edição) — não mais "não pode ser exercitada sob nenhum cenário",
  e sim "continua se auto-pulando para qualquer cenário cujo principal não
  detenha nenhuma das três — mas roda de verdade sob um cenário logado como
  owner".
- O comentário e a mensagem do `test.skip` junto ao loop que procura a
  primeira caixa destrutiva presente (linhas 144-160 antes da edição) — a
  mesma correção, com o `file:line` do fixture que agora concede as
  permissões (`served.py`'s `OPERATOR_PERMISSIONS`, computado por
  `permissions_for(Role.OWNER)`).

**Não toquei nada além disso neste arquivo.** A alegação da sessão ativa
(linha 414, "an active session identifies itself...") também trocou de skip
para vermelho real pela mesma correção de fixture da sessão 4, mas essa é
propriedade de T022, fora do escopo desta tarefa — deixada exatamente como
estava, vermelha, sem prosa tocada, por instrução explícita.

### 13.8 O acceptance spec inteiro, rodado com a ferramenta da onda — o antes e o depois

Comando (idêntico ao que a instrução pediu):

```
uv run python -m tools.spec_validation browser \
  --feature specs_v6/030-vocabulario-defaults \
  --test console/tests/e2e/vocabulary-defaults.acceptance.spec.ts
```

**Antes desta sessão** (sessão 4, seção 12.3, via `console_e2e run --project
behaviour` cobrindo a suíte inteira, não só este arquivo): das 12 falhas
totais daquela rodada, 9 eram deste arquivo direto (linhas 48, 65, 85, 191,
215, 269, 294, 369, 382) e 2 vieram de skip para fail pela correção da
fixture (127, 414) — 11 vermelhas neste arquivo, de 14 alegações, 1 sempre-skip
estrutural (preview do wizard).

**Depois desta sessão**, isolado (só este arquivo):
`6 failed, 1 skipped, 7 passed (19.3s)`.

As 7 que passam agora — nenhuma inferida, todas nomeadas pela ausência na
lista de falhas:

1. `:48` zero caixas marcadas — **T006**.
2. `:65` contador de escopos em zero — **T006**.
3. `:85` template "Alert delivery" marca só `webhook.deliver` — **T008**
   (o `webhook.deliver` do `owner` está dentro do teto desde sempre; a
   metade que antes só rodava sob reversão deliberada agora roda de verdade).
4. `:127` aviso de escopo destrutivo — **T012**. Esta é a que a instrução
   desta tarefa nomeou como minha.
5. `:191` agrupamento por domínio, mais de um grupo — **T010**.
6. `:241` `SERVICE_ACCOUNT`/`HEALTHY` em Members & roles — já corrigido por
   sessão anterior (T016), confirmado de novo aqui, não é trabalho desta
   sessão.
7. `:257` `HEALTHY` no chip de grupo de token — já corrigido por sessão
   anterior (T017 parcial mas funcional), confirmado de novo aqui.

As 6 que continuam falhando — todas fora do escopo desta tarefa, nomeadas,
não escondidas:

- `:215` ação de criar pessoa — **T027/T028**, US3.
- `:269` títulos `policies.*` em Autonomy — **T019**, US2.
- `:294` título `surfaces.notification_policy` em Notifications — **T019**.
- `:369` `webhook.deliver` cru em Alert intake — **T020**.
- `:382` `vm-201-metrics` cru na evidência do estate — **T021**.
- `:414` sessão sem origem — **T022**, deixada vermelha por instrução
  explícita.

A 1 que continua de skip — estrutural, não fixture: `:311`, preview do
wizard, pula sob `populated` (o cenário que este comando usa por padrão)
porque `/first-run` redireciona para fora assim que o setup já está
completo; sob `--scenario first-run` ela já passa (T018, sessão anterior) —
não reexecutei com `--scenario first-run` porque nada nesta sessão tocou
`first-run/`.

### 13.9 Todo comando desta sessão, com resultado real

```
pnpm exec vitest run tests/unit/surfaces/machine-token-groups.test.tsx
```
Antes de implementar T006/T008/T010/T012 (depois de escrever todos os testes
novos e reescritos de uma vez): **`15 failed | 20 passed (35)`** — os quinze
nomes exatos que falharam estão listados na seção 13.2-13.5 acima, um a um,
por `describe`/`it`. Mensagem real de uma falha representativa
(`destructive-scope-warning`, ausente do DOM):
```
TestingLibraryElementError: Unable to find an element by: [data-testid="destructive-scope-warning"]
```
Depois de implementar tudo: **`35 passed (35)`**.

```
uv run python -m tools.console_gate typecheck
```
`$ tsc --noEmit`, `EXIT=0`.

```
uv run python -m tools.console_gate lint
```
`$ eslint . && node scripts/check-css-literals.mjs`, `EXIT=0`.

```
uv run python -m tools.console_gate format-check
```
Primeira vez: vermelho real — `[warn] src/surfaces/machine-token-groups.tsx`,
`[warn] tests/unit/surfaces/machine-token-groups.test.tsx`, `EXIT=1`. Depois
de `pnpm exec prettier --write` nesses dois arquivos exatos (diff só de
formatação — nada de comportamento mudou, reconferido pelos testes depois):
`All matched files use Prettier code style!`, `EXIT=0`.

```
uv run python -m tools.console_gate test
```
(`vitest run --coverage`, o gate real — não o `vitest run --pool=forks` sem
cobertura que a instrução desta tarefa avisou não valer como prova):
**`Test Files 141 passed (141)`, `Tests 2322 passed (2322)`**, `EXIT=0`.
Cobertura: `Statements 94.34%`, `Branches 90.32%`, `Functions 92.06%`,
`Lines 96.33%` — o gate não reprovou por limiar, então esses números já
estão acima do que ele exige.

```
uv run python -m tools.console_e2e run --project behaviour tests/e2e/settings-org.spec.ts
```
`7 passed (3.2s)` — inclui o teste reescrito da seção 13.6, verde.

```
uv run python -m tools.spec_validation browser \
  --feature specs_v6/030-vocabulario-defaults \
  --test console/tests/e2e/vocabulary-defaults.acceptance.spec.ts
```
`6 failed, 1 skipped, 7 passed (19.3s)` — detalhado por linha na seção 13.8.

```
uv run python -m tools.console_e2e run --project behaviour "tests/e2e/scroll-budget.spec.ts" -g "settings/machine-tokens"
```
`1 passed (1.0s)` — `/settings/machine-tokens` continua dentro do orçamento
de 2 viewports de 1080p mesmo depois de T005-T012 adicionarem templates,
agrupamento por domínio e o contador (ver ressalva na seção 13.11).

```
uv run python -m tools.console_gate visual
```
`4 failed, 26 passed (25.6s)`, `EXIT=1` — as mesmas quatro baselines que a
sessão 4 já reportava (`single-sign-on-1440-light`, `models-providers-1440-light`,
`notifications-1440-light`, `machine-tokens-1440-light`), nenhuma aceita,
sobrescrita ou tocada por mim. As três primeiras: diffs idênticos aos da
sessão 4 (3014/3015/3021 pixels), confirmando que nada desta sessão as
tocou. A quarta, `machine-tokens-1440-light`, **moveu mais**, como a
instrução já esperava: a sessão 4 media a imagem capturada em 1440×900 (mais
baixa que a baseline de 963, porque uma linha de token sumiu da lista); esta
sessão mede a imagem capturada em **1440×1729** (mais alta que a baseline,
porque o formulário ganhou o contador, dois botões de template com suas
frases, e escopos agora em vários `<fieldset>` em vez de uma faixa única) —
`34408 pixels (ratio 0.02)` diferentes, contra `27329` antes. `git status
--porcelain console/visual/` não lista nada: a baseline em si continua
byte a byte o que já estava commitado.

```
uv run pytest -q --no-header -p no:cacheprovider tests/contract/persistence/test_identity_repository.py
```
`14 passed in 0.05s` — isolado, depois de uma primeira tentativa que juntava
esse arquivo com `tests/unit/gateway/` na mesma linha de comando ter
colidido em `ImportError: cannot import name 'PRIMARY_ORG' from 'conftest'`.
**Não é uma regressão desta sessão nem de nenhuma anterior**: é uma colisão
de nome de módulo entre dois `conftest.py` distintos (um em
`tests/contract/persistence/`, outro em `tests/unit/gateway/http/`) que só
aparece quando os dois diretórios são coletados juntos numa única invocação
do pytest sem `__init__.py`; isolado, o pacote de persistência nunca teve
esse problema. Nenhum arquivo Python foi tocado por mim nesta sessão — achado
registrado para quem rodar comandos parecidos no futuro, não uma correção
que esta sessão fez.

```
uv run pytest -q --no-header -p no:cacheprovider tests/contract/fixtures tests/unit/platform/identity/ tests/unit/gateway/
```
`900 passed, 12 warnings in 88.05s` — os doze avisos são
`PytestWarning` pré-existentes sobre `@pytest.mark.asyncio` em função
síncrona (`tests/unit/gateway/webhooks/test_delivery_permission.py`), não
introduzidos nem tocados por esta sessão.

```
make check-constants
```
Limpo, `uv run python tools/check_constants.py` sem saída de erro.

```
make check-imports
```
`Contracts: 7 kept, 0 broken.`

Verificado ao final: `docker ps -a` sem contêineres residuais; `ps aux` sem
processo de Playwright, uvicorn ou servidor Node do console residual;
`git status --porcelain` lista exatamente os arquivos desta sessão (seção
13.10) mais os que já estavam modificados/staged antes dela começar,
inalterados por mim.

### 13.10 Arquivos tocados nesta sessão

- `console/src/surfaces/machine-token-groups.tsx` — T006, T008, T010, T012.
- `console/tests/unit/surfaces/machine-token-groups.test.tsx` — T005, T007,
  T009, T011, mais a reescrita dos dois testes que assumiam o default antigo.
- `console/src/i18n/en.ts` — dez chaves novas, `settings.machineTokens.*`
  (contador, dois templates com nome+propósito, razão de desabilitado, três
  avisos de escopo destrutivo).
- `console/src/i18n/pt-BR.ts` — as mesmas dez chaves, par completo no mesmo
  passo.
- `console/tests/e2e/settings-org.spec.ts` — o teste da seção 13.6, corrigido.
- `console/tests/e2e/vocabulary-defaults.acceptance.spec.ts` — só a prosa da
  alegação do aviso destrutivo (seção 13.7), nada além disso.
- `specs_v6/030-vocabulario-defaults/tasks.md` — T005 a T012 marcados.
- Este documento.

Nenhum outro arquivo committed ou não-committed foi tocado por esta sessão.
As duas renomeações já staged (`010-provider-out-of-the-box.acceptance.spec.ts`
→ `provider-out-of-the-box.acceptance.spec.ts`,
`020-confiabilidade-telas.acceptance.spec.ts` →
`screen-truthfulness.acceptance.spec.ts`) continuam exatamente como estavam
— conferido por `git status --porcelain`, ainda `R ` sem marca adicional de
modificação.

### 13.11 O que fica pendente, nomeado, não escondido

- **As quatro baselines visuais** — decisão do operador, como a sessão 4 já
  registrava; `machine-tokens-1440-light` moveu mais nesta sessão (seção
  13.9), o que já era esperado. Não aceitei, não sobrescrevi, não rodei
  `console-visual-accept`.
- **`console/tests/e2e/settings-nav.spec.ts:93-99`** — pendência nomeada pela
  sessão 4, não tocada aqui (não é T005-T012).
- **T017** (teste dedicado no nível de tela para o chip do grupo de token) —
  continua parcial, sem mudança nesta sessão.
- **T019 a T028** (resto de US2, e US3 inteira) — não tocados, por instrução
  explícita desta tarefa.
- **T029 a T036** — não tocados.
- **Uma ressalva sobre o orçamento de rolagem que T034 vai herdar**: o
  formulário de Machine tokens cresceu bastante em altura com T005-T012 (a
  captura visual foi de ~900px para 1729px de altura em 1440 de largura —
  seção 13.9). Medido nesta sessão, só como diagnóstico, contra a viewport e
  o orçamento reais que `scroll-budget.spec.ts` declara
  (1920×1080, 2 viewports = 2160px): `/settings/machine-tokens` **ainda
  passa**, `1 passed` (seção 13.9). Não é uma pendência que esta sessão
  deixa quebrada — é uma margem que ficou mais estreita, e que T034 (fora do
  meu escopo) é quem tem que reconferir quando Members & roles e Machine
  tokens estiverem com todo o resto de US2/US3 em cima também, porque o
  orçamento é sobre a página inteira, não sobre uma fatia isolada.
- **A alegação do preview do wizard** (`vocabulary-defaults.acceptance.spec.ts:311`)
  continua de skip sob o cenário `populated` que o comando padrão usa — isso
  não é novo desta sessão nem foi tocado por ela; só citado aqui para quem
  ler o resultado de `spec_validation browser` sem o contexto das sessões
  anteriores.

Nenhum destes tem dono fora da própria feature 030; nada foi transferido
para outra spec da onda.

---

## 14. Continuação — sessão 6: T017 e T019/T020 fechados; T021 a T024 só desenhados; a sessão foi interrompida a meio de T020 e recuperada

**Escopo desta sessão, imposto pelo orquestrador**: só o resto de US2 —
T017 e T019 a T024. T005-T016, T018, T025 em diante não foram tocados.
Verificado contra o código real desta árvore agora, branch
`feat/v6-010-provider-out-of-the-box`, ainda em cima de `b4a8153`. Nada
commitado nem staged por este trabalho — a renomeação de dois acceptance
specs já staged antes desta sessão continua exatamente como estava
(conferido por `git diff --cached --stat`, só as duas renomeações, 0
inserções/deleções).

**Dito sem eufemismo, porque é o fato mais importante desta seção**: esta
sessão tentou as seis tarefas de uma vez, entrou fundo demais em exploração
(T017, T019, T020, T021, T022, T023, T024, nessa ordem) e foi interrompida
pelo orquestrador a meio da implementação de T020 — exatamente o padrão que
as duas sessões anteriores "que tentaram carregar tudo" já tinham sofrido.
A árvore ficou vermelha em exatamente um erro real, capturado pelo
orquestrador antes de eu rodar qualquer gate eu mesma:

```
src/surfaces/settings/alert-intake.tsx(203,10): error TS6133: 'deliveryTokenNamed' is declared but its value is never read.
```

Causa: eu tinha acabado de inserir a função `deliveryTokenNamed` (só a
declaração) e a mensagem do orquestrador chegou antes da próxima edição, que
seria ligá-la ao `Promise.all` de leituras, à variável `deliveryTokenName` e
ao JSX do `delivery-token-group`. **Segui a instrução do orquestrador
exatamente como pedida**: terminei essa única edição interrompida — nada
novo — e parei. As três edições que faltavam (o `optionalRead('/identity/tokens', ...)`
no `Promise.all`, o cálculo de `deliveryTokenName`, e o JSX do grupo) foram
completadas nesta ordem, sem tocar em T021 a T024, que continuam exatamente
como a exploração desta sessão as deixou: desenhadas, nenhuma linha de
código escrita.

### 14.1 Ledger desta sessão, por tarefa

| Tarefa | Estado | Detalhe |
|---|---|---|
| T017 | **FEITO** | Teste dedicado no nível de tela escrito e rodado — **nunca ficou vermelho** (dito sem eufemismo, seção 14.2). A implementação (`TokenGroupStateChip` em `machine-token-groups.tsx:524`) já existia de sessão anterior; este teste só prova, no nível da tela, o que antes só o teste de componente (T015) provava. |
| T019 | **FEITO** | Vermelho confirmado (3 casos, seção 14.2), depois implementado em `console/src/surfaces/preview.tsx`. Ver seção 14.3 — o achado mais importante desta fatia. **Desvio do texto de `tasks.md`**: a tarefa nomeia `console/src/surfaces/advanced-config-section.tsx` como o arquivo do título; a correção real está em `preview.tsx`, como as sessões 3/4/5 já tinham cravado (seção 5, 9.6, 11.2, 13.8 deste documento) — `advanced-config-section.tsx` só ganhou uma linha (`locale={locale}` no `<ConfigEditor>` que já tinha, `advanced-config-section.tsx:194`), não o resolvedor em si. |
| T020 | **FEITO** | Vermelho confirmado (5 de 7 casos, seção 14.2; os outros 2 são ditos como nunca-vermelhos, sem eufemismo), depois implementado em `console/src/surfaces/settings/alert-intake.tsx`. Ver seção 14.4. |
| T021 | **NÃO INICIADO** | Nenhum arquivo tocado. Desenho completo, pronto para a próxima sessão — seção 14.5. |
| T022 | **NÃO INICIADO** | Nenhum arquivo tocado. Desenho completo — seção 14.6. |
| T023 | **NÃO INICIADO** | Nenhum arquivo tocado. Desenho completo, com um achado crítico (um teste já committed que codifica o defeito que esta tarefa precisa remover) — seção 14.7. |
| T024 | **NÃO INICIADO** | Nenhum arquivo tocado. Desenho completo — seção 14.8. |

### 14.2 Vermelho observado, comando por comando

**T017** — `console/tests/unit/surfaces/machine-token-groups.test.tsx:710-741`,
`describe('the group state chip names what the group has done, never a
resource health word', ...)`, dois `it()`. Rodado assim que escrito, antes
de qualquer mudança de produção:

```
pnpm exec vitest run tests/unit/surfaces/machine-token-groups.test.tsx -t "state chip"
```

→ `Tests  2 passed | 35 skipped (37)` — **vermelho nunca observado, dito sem
eufemismo**. Caracterização: o comportamento que este teste prova
(`TokenGroupStateChip` no lugar de `<Badge status="healthy">`) já tinha sido
implementado numa sessão anterior (T016/seção 9.6); só faltava o teste no
nível desta tela especificamente, e agora existe.

**T019** — `console/tests/unit/surfaces/config-editor.test.tsx:452-500`,
`describe('a section titles itself for a person, never by its own schema
path', ...)`, três `it()`. Rodado antes de tocar `preview.tsx`:

```
pnpm exec vitest run tests/unit/surfaces/config-editor.test.tsx -t "titles itself"
```

→ `3 failed | 45 skipped (48)`. As três mensagens reais:

1. `shows a human title for a known technical section, not the schema path`:
   ```
   AssertionError: expected <span …(1)></span> to be null
   - Expected: null
   + Received: <span class="font-mono text-meta text-strong"> policies.masking </span>
   ```
2. `shows a human title for every other section this feature names`:
   ```
   AssertionError: expected 'Find a fieldpolicies.guardrails (1)po…' not to contain 'policies.guardrails'
   ```
3. `still reads as words, not a path, for a section this catalogue has never met`:
   mesma forma do item 1, com `policies.unheard_of_thing` no lugar de
   `policies.masking`.

Depois de implementar (seção 14.3): `48 passed (48)` no arquivo inteiro.

**T020** — `console/tests/unit/surfaces/settings-alert-intake.test.tsx:389-527`,
`describe('the delivery token control', ...)`, reescrito e ampliado para
sete `it()`. Rodado antes de tocar `alert-intake.tsx` (só a assinatura da
função `deliveryTokenNamed` existia em produção, não usada em lugar
nenhum):

```
pnpm exec vitest run tests/unit/surfaces/settings-alert-intake.test.tsx -t "delivery token"
```

→ `5 failed | 2 passed (7)`. As cinco mensagens reais:

1. `never names the raw delivery permission, before or after a token authenticates it`:
   ```
   Expected element not to have text content: webhook.deliver
   Received: Trusted by webhook.deliverIssue a delivery token
   ```
2. `says nothing has authenticated deliveries yet, when no token carries the permission`:
   ```
   Expected element to have text content: /no delivery token/i
   Received: Trusted by webhook.deliverIssue a delivery token
   ```
3. `names the delivery token once one has actually authenticated deliveries with it`:
   ```
   Expected element to have text content: am-cluster
   Received: Trusted by webhook.deliverIssue a delivery token
   ```
4. `offers to rotate, not to issue a second one, once a delivery token already exists`:
   ```
   Expected element to have text content: Rotate
   Received: Issue a delivery token
   ```
5. `picks the most recently issued token when more than one carries the permission`:
   ```
   Expected element to have text content: am-cluster-new
   Received: Trusted by webhook.deliverIssue a delivery token
   ```

**Os dois que passaram sem nunca ficar vermelhos, ditos sem eufemismo**:
`sits beside what it is scoped to, rather than orphaned below the rows`
(estrutural — só confirma que `delivery-token-group` contém
`data-testid="delivery-token"`, o que já era verdade antes desta sessão) e
`never counts a revoked token as the one authenticating deliveries` (passou
de forma vazia: antes da implementação a tela não lia `/identity/tokens` de
jeito nenhum, então nenhum token revogado podia aparecer por construção —
não é prova de que a exclusão de revogados funciona, só depois da
implementação essa asserção passou a testar algo real). Depois de
implementar: `7 passed (7)` no bloco inteiro; `37 passed (37)` no arquivo.

### 14.3 O achado sobre `ConfigEditor` em `preview.tsx` — a descoberta de maior alcance desta fatia

**O vazamento nunca esteve em `advanced-config-section.tsx`**, como
`tasks.md` (T019) e o `plan.md` original diziam — isso já tinha sido cravado
por sessões anteriores (seção 5, 9.6, 11.2, 13.8 acima) e esta sessão só
terminou de fechar o que ficou registrado. `AdvancedConfigSection` já usa um
título humano no seu próprio `<summary>` (`title` vem de i18n, passado por
quem chama — ex.: `settings.autonomy.advanced.title`). O vazamento real
estava **dentro** do `ConfigEditor` que essa seção monta por baixo
(`console/src/surfaces/preview.tsx`): `sectioned()` agrupa os campos por
`field.section` (o caminho pontuado que `platform/config_service/fields.py`
grava como o pai imediato de cada folha do schema — confirmado lendo
`_walk()` naquele arquivo, `platform/config_service/fields.py:222-264`), e
esse mesmo `section` cru era usado, sem tradução nenhuma, como texto do link
do índice (`preview.tsx`, dentro do `<nav data-testid="section-toc">`) e
como título do `<summary>` de cada grupo (`<details data-testid="config-section">`).
Como `ConfigEditor` é compartilhado por **toda** página com seção avançada —
não só Autonomy e Notifications — esse vazamento existia (e agora está
corrigido) em qualquer seção que qualquer uma dessas páginas monte:
`sso.tsx`, `agent.tsx` (duas seções), `integrations.tsx`, `knowledge.tsx`
(quatro seções), `schedules-destinations.tsx` (duas), `alert-intake.tsx`,
além de `autonomy.tsx` e `notifications.tsx`, que chamam `<ConfigEditor>`
diretamente, sem passar por `AdvancedConfigSection`.

**O que foi implementado, com `file:line`:**

- `console/src/surfaces/preview.tsx:346-353` — `SECTION_TITLE`, um mapa
  `Readonly<Record<string, MessageKey>>` só com os cinco caminhos que
  FR-005/FR-006 nomeiam (`policies.masking`, `policies.guardrails`,
  `policies.approvals`, `policies.autonomy`, `surfaces.notification_policy`).
  **Decisão deliberada de não tentar ser exaustivo**: o universo de valores
  possíveis de `section` é qualquer objeto aninhado que `RootConfig` (o
  schema Pydantic da configuração) declarar agora ou no futuro — mapear
  todos seria um catálogo paralelo que este arquivo teria que manter em dia
  para sempre, exatamente o padrão que a Assumption da spec já proíbe para o
  agrupamento de escopos (US1). Só os cinco que esta feature nomeia
  explicitamente entraram no mapa.
- `console/src/surfaces/preview.tsx:355-361` — `humanize()`, uma terceira
  cópia da mesma função já duplicada em `machine-token-groups.tsx:162` e
  `settings/audit.tsx:114` (nenhuma delas importa de um módulo compartilhado
  — não criei um quarto lugar para isso, segui o padrão já estabelecido).
- `console/src/surfaces/preview.tsx:363-374` — `sectionTitle(section, locale)`:
  procura `section` no mapa; se não achar, pega o **último segmento**
  pontuado (`section.split('.').pop()`) e humaniza — é isto que garante que
  uma seção que o schema declarar amanhã, que este mapa não conhece, ainda
  lê como palavras (`"policies.something_new"` → `"Something New"`) em vez
  do caminho cru. **Não traduzido para pt-BR no caso de fallback** — mesma
  convenção já usada para nomes de escopo em `machine-token-groups.tsx`
  (`humanize()` ali também nunca passa por `message()`), documentada nesta
  função.
- `console/src/surfaces/preview.tsx:172-178` — `ConfigEditorProps` ganhou
  `readonly locale: Locale;`, obrigatório (não `?`).
- `console/src/surfaces/preview.tsx:553-558` — `ConfigEditor` desestrutura
  `locale` agora.
- `console/src/surfaces/preview.tsx:698` e `:728` — os dois pontos que
  imprimiam `section` cru agora chamam `sectionTitle(section, locale)`. A
  classe `font-mono` do `<summary>` (linha 728, antes um `<span
  className="font-mono text-meta text-strong">`) foi removida — fazia
  sentido para um caminho técnico, não para um título humano; a classe atual
  é só `text-meta text-strong`, igual ao título que
  `AdvancedConfigSection`'s próprio `<summary>` já usa.
- `data-section={section}` **continua cru**, sem tocar — é o atributo
  técnico que FR-011 exige continuar recuperável, e é por ele que todo teste
  de seção existente (`config-editor.test.tsx`, `settings-alert-intake.test.tsx`
  etc.) já navegava, não pelo texto visível. Confirmado que nenhum teste
  existente dependia do texto cru como conteúdo visível (só de
  `data-section`) — ver seção 14.2.

**Os três call sites reais, todos threading `locale`** — conferido por
`grep -rn "<ConfigEditor" console/src`, exatamente três resultados, os três
tocados:

- `console/src/surfaces/advanced-config-section.tsx:194` — `locale={locale}`
  acrescentado (a prop já existia no escopo, vinda do próprio
  `AdvancedConfigSectionProps.locale` que todo chamador já fornece — por
  isso um único ponto aqui cobre as sete páginas que usam
  `AdvancedConfigSection`, sem tocar nenhuma delas individualmente).
- `console/src/surfaces/settings/autonomy.tsx:571` — `locale={locale}`
  acrescentado ao `<ConfigEditor>` que essa página já monta direto (a seção
  de guardrails, fora do `AdvancedConfigSection`).
- `console/src/surfaces/settings/notifications.tsx:151` — idem.

**Prova de que nada ficou faltando** (o mesmo tipo de buraco que a sessão 2
deste documento já tinha registrado para `fieldLabels`, e que o orquestrador
citou nominalmente nesta sessão como o risco a evitar):
`uv run python -m tools.console_gate typecheck` → `EXIT=0`. Como `locale`
é obrigatório em `ConfigEditorProps` e o `tsc` do projeto inteiro passou
limpo, **não existe call site de produção sem a prop** — o compilador teria
recusado. Os dois testes que instanciam `<ConfigEditor>` direto
(`config-editor.test.tsx:132-136`, `object-list.test.tsx:190-193`) também
ganharam `locale="en"` nos seus helpers `editor()`, um ponto cada.

### 14.4 T020 — Alert intake, o que foi implementado

`console/src/surfaces/settings/alert-intake.tsx`:

- `:203-215` — `deliveryTokenNamed(records, permission)`: filtra por não ser
  sessão de navegador (`!isConsoleSession({name: text(record,'name')})`,
  mesmo predicado que `settings/machine-tokens.tsx` já usa para o mesmo
  fim), não revogado, e `scopes` contendo `permission`; ordena por
  `created_at` decrescente; devolve o `name` do primeiro ou `undefined`.
- `:275-282` — sexta leitura no `Promise.all` de `content()`:
  `optionalRead('/identity/tokens', () => read('/identity/tokens', init))`.
  **Decisão**: `optionalRead`, não `panelRead` — uma falha aqui degrada para
  "ainda não autenticado" (o mesmo estado de um deployment que nunca emitiu
  o token) em vez de derrubar o painel inteiro "What arrives", porque quem
  está autenticando a entrega é um detalhe deste grupo, não a razão de a
  lista de receivers falhar. Mesmo padrão que `receivers`
  (`/v1/ingress/sources`) já seguia nesta função antes desta sessão.
- `:305-308` — `deliveryTokenName`, calculado só quando `deliveryPermission
  !== ''`.
- `:511-545` (bloco `data-testid="delivery-token-group"`) — a frase de
  confiança agora é `message(locale, 'ingress.delivery.unauthenticated')`
  quando `deliveryTokenName === undefined`, ou
  `message(locale,'ingress.delivery.authenticated')` seguido do nome em
  `<code data-testid="delivery-token-name">` quando não. O botão de
  `DeliveryToken` (componente reaproveitado sem alteração,
  `console/src/surfaces/ingress.tsx`, não tocado) recebe `labels.issue`/
  `labels.issuing` trocados entre `ingress.token.issue`/`issuing` e
  `ingress.token.rotate`/`rotating` conforme o mesmo booleano.
- **`ingress.verification` (linha ~408, a descrição de verificação por
  fonte) não foi tocada** — confirmado por `grep`, só uma ocorrência
  restante no arquivo, e é essa; o comentário novo em `en.ts` ao lado da
  chave documenta por que as duas não podem ser trocadas juntas (achado já
  cravado pela sessão anterior, seção 5 acima).

Chaves i18n novas (as quatro, inglês e português no mesmo passo):
`ingress.delivery.authenticated`, `ingress.delivery.unauthenticated`,
`ingress.token.rotate`, `ingress.token.rotating` — conferidas por `git diff`
linha a linha nesta seção do documento, seção 14.9 abaixo.

**O que não ganhou teste dedicado, nomeado**: nenhum teste prova o caso em
que a sessão do navegador (`Console sign-in`) carrega `webhook.deliver` nos
seus próprios `scopes` armazenados — o filtro `isConsoleSession` existe
(defesa, mesmo padrão de `machine-tokens.tsx`) mas não há uma asserção desta
sessão que force esse caminho especificamente. Não é uma lacuna de
implementação — é uma lacuna de prova, nomeada aqui em vez de escondida.

### 14.5 Desenho pronto para T021 (evidência da sugestão do estate) — não implementado

**Achado confirmado, não só suposto**: o backend já serve `Suggestion.because`
(`platform/estate/suggestions.py:44-63`, passado por
`gateway/http/routes/integrations.py:336-341` em `SuggestionView`) — uma
frase legível, sem id cru, **exceto** quando `resource.display_name` está
vazio, caso em que `suggestions.py:96-100` cai para
`resource.display_name or resource.resource_id!r` (o id, entre aspas
simples, dentro da frase). O console hoje (`console/src/surfaces/screens/integrations.tsx:157-166`)
só lê `address`/`from_resource` de `suggested`, nunca `because`, e é
`from_resource` cru que a evidência interpola
(`integrations.tsx:435-438`, chave `catalogue.integrations.suggested.evidence`,
`'Found at {address}, on resource {resource}'` em `en.ts:1381-1382` antes
desta sessão).

**Por que usar `because` diretamente não resolve**: no caso resolvível
(`metrics-store`, fixture) `because` já é perfeitamente legível ("a guest
labelled prometheus is reachable on the metrics port" —
`fixtures/scenarios/populated/integrations.json`, gerado de
`tools/mockplane/dataset/served.py:1799-1803`). No caso **não resolvível**
(`redis`, a fixture que a sessão 4 acrescentou de propósito,
`served.py:1742-1750`), `because` embute o id cru entre aspas simples
(`"'ct-9042'"`) — exatamente o defeito que FR-008 proíbe, só que dentro de
uma frase em vez de sozinho. Confirmado: o `Resource.kind` (`platform/persistence/ports/estate_repository.py:191`,
campo obrigatório, nunca vazio) e `Resource.display_name`
(`:194`, `str = ""`, pode ser vazio) são os dois fatos que decidem qual
frase mostrar.

**O desenho, pronto para implementar**:

1. **Backend** — acrescentar dois campos a `Suggestion`
   (`platform/estate/suggestions.py:43-64`) e a `SuggestionView`
   (`gateway/http/routes/integrations.py:88-98`): `resource_label: str`
   (= `resource.display_name`, vazio quando não resolvível — **nunca** cai
   para o id, ao contrário de `because`) e `resource_kind: str`
   (= `resource.kind`, sempre presente). Atualizar `to_record()`
   (`suggestions.py:57-64`) e o único call site que constrói
   `SuggestionView(...)` (`gateway/http/routes/integrations.py:337-341`,
   passar `resource_label=suggested[entry.name].resource_label,
   resource_kind=suggested[entry.name].resource_kind`) e
   `suggest_integrations()` (`suggestions.py:92-101`, adicionar
   `resource_label=resource.display_name, resource_kind=resource.kind` ao
   `Suggestion(...)`).
2. **Fixture** — `tools/mockplane/dataset/served.py`: acrescentar
   `"resource_label"`/`"resource_kind"` aos dois dicionários
   `suggested` já escritos à mão (`:1742-1750`, redis —
   `resource_label: ""`, `resource_kind: "container"`, porque o `because`
   ali já diz "a container called 'ct-9042'"; `:1799-1803`, metrics-store —
   `resource_label: "prometheus"`, `resource_kind: "guest"`, porque o
   `because` ali já diz "a guest labelled prometheus"). Depois,
   `uv run python -m tools.mockplane build` para regerar as fixtures, e
   `uv run pytest -q tests/contract/fixtures` para confirmar o rebuild
   byte-idêntico e a validação contra o OpenAPI gerado.
3. **Console** — `integrations.tsx:157-166` (`suggestionOf`) e
   `CatalogueItem.suggested` (`:117`) ganham `resourceLabel`/`resourceKind`.
   A evidência (`:433-439`) passa a montar a frase com `resourceLabel`
   quando não vazio, e um fallback novo (chave nova,
   `catalogue.integrations.suggested.evidence.unresolved`, algo como "Found
   at {address}, on a {kind}" — sem id nenhum) quando vazio, honrando o
   Edge Case da spec ("a sugestão mostra o que conseguiu resolver —
   endereço, tipo — e o identificador só no destino do link"). O `from_resource`
   cru **não é removido da API nem do DOM** — a decisão desta sessão (não
   implementada, só decidida) foi mantê-lo como `data-resource` no `<li
   data-testid="suggested-integration">`, satisfazendo FR-011 pelo caminho
   "atributo de dado da própria marcação" em vez de tentar embutir o id como
   parâmetro de query no link de Connect (`detailHref`, `integrations.tsx:313-314`) —
   essa segunda rota existe e seria mais literal ao texto de FR-008 ("o
   identificador DEVE ficar no destino do link"), mas exigiria estender
   `detailHref`/o sistema de `url-state.ts` com um parâmetro que a rota de
   destino nunca lê, e o risco de mexer nesse mecanismo compartilhado sem
   testá-lo a fundo pareceu maior que o ganho — fica nomeado para quem
   decidir diferente.
4. **Testes que precisam existir, ainda não escritos**: um novo caso em
   `tests/unit/platform/estate/test_integration_suggestions.py` (o arquivo
   já existe, 147 linhas, todos os `resource()` de teste hoje têm
   `display_name` preenchido — falta um caso com `display_name=""` provando
   `resource_label == ""` e `resource_kind` presente) e um caso equivalente
   em `console/tests/unit/surfaces/integrations.test.tsx` (existe,
   não lido a fundo nesta sessão — vermelho não confirmado, nomeado como
   pendência).

### 14.6 Desenho pronto para T022 (identificação de sessão) — não implementado

**Achado confirmado**: `TokenView` (`gateway/http/routes/identity.py:120-130`,
o schema de `/identity/tokens`) **não tem campo nenhum de origem/dispositivo** —
só `token_id, user_id, name, description, team_node_id, scopes, created_at,
expires_at, last_used_at, revoked`. Isso não é uma lacuna desta sessão nem
uma escolha errada de alguém — é o estado real do backend hoje, e é
exatamente o que o Edge Case da spec já antecipa ("Sessão sem dispositivo ou
origem conhecidos: identifica-se por quem é dona e desde quando"). **Não há
"dispositivo"/"origem" para mostrar hoje, em nenhum cenário** — o único fato
adicional que já existe e ainda não é mostrado é `created_at`.

`console/src/surfaces/tokens.tsx`'s `SessionPanel`
(`:371-482`) agrupa sessões por `principalId` (`grouped()`, `:344-359`) e
hoje mostra, por grupo: nome (`principalLabel`), contagem
(`group.sessions.length`) e `group.sessions[0]?.expires`. **Não existe
nenhum `data-testid="session-origin"`** — é exatamente a lacuna que a
alegação `:414` do acceptance spec cobra (`vocabulary-defaults.acceptance.spec.ts:411-442`),
hoje vermelha de verdade (não skip) desde que a sessão 4 corrigiu o nome do
token de sessão no fixture (`served.py:2700`, `"Console sign-in"`).

**O desenho, pronto para implementar**:

1. `console/src/surfaces/tokens.tsx`: `SessionEntry` (`:313-318`) ganha
   `readonly origin: string;` (já formatado como tempo relativo, mesmo
   padrão de `expires` — a tela é client component e não tem `locale` para
   formatar ela mesma). `SessionLabels` (`:320-330`) ganha `readonly origin: string;`
   (cabeçalho de coluna, ao lado de `person`/`expires` no
   `data-testid="session-columns"`, `:404-413`). O `<li data-testid="session-group">`
   (`:415-472`) ganha um `<span data-testid="session-origin">{group.sessions[0]?.origin ?? ''}</span>`,
   mesma convenção de "usa o primeiro do grupo" que `expires` já segue.
2. `console/src/surfaces/settings/members.tsx:104-109` (`liveSessions`):
   acrescentar `origin: timestamp(locale, text(token, 'created_at'), now, zone).relative`
   ao objeto mapeado, e `origin: message(locale, 'admin.column.origin')` (ou
   chave equivalente — não decidida) nos `labels` passados a `SessionPanel`
   (`:200-213`).
3. Chaves i18n novas: um rótulo de coluna curto (sugestão: `admin.column.origin`
   = "Started" / "Início", ecoando o Edge Case "desde quando").
4. `console/tests/unit/surfaces/tokens.test.tsx:375-394` (`SESSIONS`, três
   entradas) e `:363-373` (`SESSION_LABELS`) precisam de `origin` — sem
   isso o `SessionEntry`/`SessionLabels` novos quebram o typecheck deste
   arquivo. Testes novos, ainda não escritos: um provando que
   `session-origin` existe e mostra o valor de `origin`, outro provando o
   cabeçalho de coluna novo.

**Não implementado. Vermelho nunca confirmado — nomeado, não escondido.**

### 14.7 Desenho pronto para T023 (resumo humano do grant) — não implementado, com achado crítico

**Achado crítico, o mais importante desta seção**: `console/tests/unit/surfaces/grants.test.tsx:496-523`,
`describe('what a role means, at the point it is chosen', ...)`, **já
codifica o defeito que esta tarefa precisa remover** como comportamento
correto — `DESCRIPTIONS = { viewer: 'investigation.read, report.read', ... }`
e `expect(screen.getByText(DESCRIPTIONS.viewer)).toBeInTheDocument()`. É o
mesmo padrão que `settings-org.spec.ts` (US1, já corrigido na sessão 5) e
`machine-token-groups.test.tsx`'s testes antigos de escopo pré-marcado já
tinham — um teste committed testando o defeito como se fosse a
especificação. **Quem implementar T023 tem que reescrever este bloco**, não
só acrescentar ao lado.

**Origem do dado cru**: `console/src/surfaces/settings/members.tsx:85-90` —
```
const roleDescriptions = Object.fromEntries(
  roleCatalogue.map((role) => [
    text(role, 'name'),
    list(role, 'permissions').map(String).join(', '),
  ]),
);
```
Passado a `GrantPanelProps.roleDescriptions?: Readonly<Record<string, string>>`
(`console/src/surfaces/grants.tsx:112`), usado como `description` do
`<Select>` de papel (`grants.tsx:330-332`) — exatamente "uma linha de ids
separados por vírgula" que o FR-010/Acceptance Scenario 8 da US2 proíbe.

**O desenho, pronto para implementar**:

1. Trocar o tipo: `roleDescriptions?: Readonly<Record<string, RoleDescription>>`
   onde `RoleDescription = { readonly summary: string; readonly
   permissions: readonly string[] }`.
2. Em `members.tsx`, computar `summary` **sem** um catálogo novo — mesma
   régua que a Assumption da spec já impõe ao agrupamento de escopos (US1):
   derivar do próprio nome da permissão, nunca de uma tabela papel→frase
   escrita à mão. Desenho concreto: contar domínios distintos (mesmo
   `permission.split('.')[0]` que `platform/identity/permissions.py`'s
   `Permission.domain` já declara, e que `machine-token-groups.tsx`'s
   `domainOf`/`groupedByDomain` já usa) e produzir uma frase curta e
   **limitada em tamanho independente de quantas permissões o papel tenha**
   (o Edge Case da spec pede exatamente isso: "não vira uma lista longa
   disfarçada") — ex.: `formatCount(locale, domainCount, 'admin.grant.role.summary.one', 'admin.grant.role.summary')`,
   algo como "Reaches {count} configuration domain(s)" / "Alcança {count}
   domínio(s) de configuração". A lista completa e crua de permissões
   (`list(role,'permissions').map(String)`) continua existindo, mas só como
   o segundo campo (`permissions`), não mais interpolada na frase.
3. Em `grants.tsx`, `<Select description={roleDescriptions?.[role]?.summary}>`
   no lugar do valor cru; e um `<details data-testid="role-permissions">`
   novo, ao lado do seletor, com `<summary>` (rótulo i18n novo, algo como
   "See every permission" / "Ver cada permissão") e
   `roleDescriptions?.[role]?.permissions.join(', ')` dentro — a "lista
   completa disponível ao expandir" que o Acceptance Scenario 8 pede,
   fechada por padrão.
4. Reescrever `grants.test.tsx:496-523`: `DESCRIPTIONS` passa a ser
   `Readonly<Record<string, RoleDescription>>`; os três `it()` existentes
   precisam provar o resumo (não o texto cru) e a lista completa atrás da
   expansão; um quarto `it()` novo, provando que o resumo não cresce sem
   limite para um papel com dezenas de permissões (o `owner` real tem 31,
   per sessão 4 — usar esse número como caso de teste é honesto com o que o
   catálogo real produz).

**Não implementado. Vermelho nunca confirmado — nomeado, não escondido.**

### 14.8 Desenho pronto para T024 (papel legível no grant listado) — não implementado

**Reconsiderado a fundo antes de desenhar**: à primeira vista, `<Badge
status={row.role} />` (`grants.tsx:285`) e o `<Select options={roles.map((name)
=> ({value: name, label: name}))}>` (`grants.tsx:324`) já mostram a **mesma**
string crua (ex.: `"owner"`) — não parecia haver vocabulário divergente para
corrigir. Investigado: `statusPresentation('owner')`
(`console/src/design/status.ts:282-294`) cai no ramo "status desconhecido"
(`DECLARED['owner']` é `undefined` — nenhum dos `RUN_STATUSES`/
`RESOURCE_STATUSES`/`ATTENTION_STATUSES` inclui nomes de papel) e devolve
`{role: 'neutral', shape: 'hollow-circle', label: 'owner', known: false}` —
o texto renderizado é o mesmo `"owner"` cru, só com `text-transform:
uppercase` via CSS (a classe `uppercase` de `Badge`, não uma transformação
no texto em si).

**A leitura que ficou, depois de reconsiderar**: o defeito de FR-019 não é
"os dois discordam hoje" (não discordam) — é que a linha listada usa
`Badge`, um componente cujo próprio contrato (`console/src/components/status.tsx:90-96`,
"o texto do status como a API o reportou... certo para o status de uma run
ou a saúde de um recurso") **não é vocabulário de papel**. É o mesmo erro de
categoria que T016 já corrigiu para tipo de principal e estado de conta —
usar `Badge` (feito para status de transporte) onde o valor não é um status.
"Pelo mesmo vocabulário do seletor que o concede" (FR-019) lido literalmente:
o seletor mostra a `<option>` sem chip nenhum, sem cor, sem `uppercase` —
texto puro. A linha listada deveria mostrar exatamente isso, não um chip de
status emprestado.

**O desenho, pronto para implementar**:

1. `grants.tsx:285`: trocar `<Badge status={row.role} />` por um `<span>`
   de texto simples (sem `data-role`, sem `ShapeMark`, sem `uppercase`) —
   mesma string, mesmo caso, que a `<option>` do seletor já usa.
2. Teste novo em `grants.test.tsx` (a `describe('who a grant belongs to, at
   a glance', ...)` existente, `:470-494`, é o lugar natural): provar que o
   texto do papel na linha listada é idêntico ao `value`/`label` da opção
   correspondente no seletor (ex.: `screen.getByLabelText(LABELS.role)`'s
   `<option value="owner">` vs. o texto da linha), e que a linha **não**
   carrega `data-role` (a marca que `Badge`/`ResolvedChip` deixam,
   `console/src/components/status.tsx:101,206,247` — provando que não é
   mais um chip de status).

**Não implementado. Vermelho nunca confirmado — nomeado, não escondido.**

### 14.9 A suíte transversal — nenhuma exceção tocada

**`console/tests/e2e/transversal-rules.spec.ts` não foi tocado nesta
sessão** — nem lido, nem editado. As exceções que T019/T020 desbloqueiam de
verdade (títulos `policies.`/`surfaces.` e o jargão `webhook.deliver` de
Alert intake, se estiverem nomeadas nessa tabela) **continuam de pé**, não
removidas — dito para não ser confundido com "removido e esquecido de
registrar". Quem continuar (a próxima sessão de T021-T024, ou uma dedicada a
fechar US2) precisa rodar essa suíte e decidir, exceção por exceção, se a
rota que ela cobre já ficou limpa o suficiente para a exceção cair — o
prompt desta sessão pedia exatamente isso ("delete sua entrada de exceção")
e não foi feito por falta de tempo dentro do escopo desta tentativa, não por
esquecimento.

### 14.10 Gates rodados nesta sessão, com resultado real

```
uv run python -m tools.console_gate typecheck
```
→ `$ tsc --noEmit`, `EXIT=0`. Rodado duas vezes: uma para confirmar a edição
interrompida estava mesmo fechada (pedido explícito do orquestrador), outra
depois do conserto de lint (seção abaixo) para reconfirmar.

```
uv run python -m tools.console_gate lint
```
→ vermelho real na primeira vez:
```
tests/unit/surfaces/config-editor.test.tsx
  475:18  error  Unnecessary conditional, expected left-hand side of `??` operator to be possibly null or undefined  @typescript-eslint/no-unnecessary-condition
```
Causa: `const body = document.body.textContent ?? '';` num teste que esta
sessão escreveu (seção 14.2) — o `?? ''` era redundante para o jeito como o
projeto tipa `document.body.textContent` aqui. Conserto: removido o `?? ''`
(`config-editor.test.tsx:475`, agora `const body = document.body.textContent;`).
Depois: `EXIT=0`, limpo.

```
uv run python -m tools.console_gate format-check
```
→ vermelho real na primeira vez: `[warn] src/i18n/en.ts`, `[warn]
src/i18n/pt-BR.ts`, `[warn] src/surfaces/preview.tsx` — os três arquivos que
esta sessão editou via substituição de texto direta (não pela ferramenta de
edição), sem nunca rodar Prettier. Conserto: `pnpm exec prettier --write
src/i18n/en.ts src/i18n/pt-BR.ts src/surfaces/preview.tsx`, só esses três,
nada mais — diff é só formatação, reconferido pelos testes depois. Depois:
`All matched files use Prettier code style!`, `EXIT=0`.

```
pnpm exec vitest run \
  tests/unit/surfaces/machine-token-groups.test.tsx \
  tests/unit/surfaces/config-editor.test.tsx \
  tests/unit/surfaces/object-list.test.tsx \
  tests/unit/surfaces/advanced-config-section.test.tsx \
  tests/unit/surfaces/settings-alert-intake.test.tsx \
  tests/unit/surfaces/settings/autonomy.test.tsx \
  tests/unit/surfaces/settings/notifications.test.tsx
```
→ **`Test Files  7 passed (7)`, `Tests  175 passed (175)`** — rodado por
último, depois do conserto de lint e formatação, confirmando que nada
quebrou. **Este é `vitest run` sem `--coverage`, não o gate real** — a
mesma armadilha que a instrução desta tarefa já avisava. `uv run python -m
tools.console_gate test` (o gate com limiar de cobertura) **não foi rodado
nesta sessão** — o pedido do orquestrador foi "a suíte de unidade do console
para os arquivos tocados", interpretado literalmente como os sete arquivos
acima, não a suíte inteira. Fica nomeado como gate pendente para quem
continuar, antes de declarar T019/T020 prontos para T032 (o gate completo
de US2).

**Não rodados nesta sessão, por instrução explícita de escopo estreito**:
`uv run python -m tools.spec_validation browser --feature
specs_v6/030-vocabulario-defaults --test
console/tests/e2e/vocabulary-defaults.acceptance.spec.ts` (o acceptance spec
inteiro — eu esperaria que as alegações `:269` e `:294` (policies./surfaces.
como título) e talvez `:369` (webhook.deliver cru) tivessem passado a
`passed` depois desta sessão, mas **não confirmei rodando** — dito como
suposição, não como fato); `console/tests/e2e/transversal-rules.spec.ts`;
`uv run python -m tools.console_e2e run --project behaviour`; `uv run python
-m tools.console_gate visual` (e, por instrução explícita e repetida do
orquestrador, **nenhuma baseline visual foi aceita, sobrescrita ou tocada**
— `git status --porcelain console/visual/` confirmado vazio ao final).

Verificado ao final: `docker ps -a` sem contêineres; `ps aux` sem processo
de Playwright, `vitest --watch`, uvicorn ou servidor Node do console
residual.

### 14.11 Arquivos tocados nesta sessão

- `console/src/surfaces/preview.tsx` — T019 (seção 14.3).
- `console/src/surfaces/advanced-config-section.tsx` — T019, uma linha
  (`locale={locale}`).
- `console/src/surfaces/settings/autonomy.tsx` — T019, uma linha.
- `console/src/surfaces/settings/notifications.tsx` — T019, uma linha.
- `console/src/surfaces/settings/alert-intake.tsx` — T020 (seção 14.4).
- `console/src/i18n/en.ts` — nove chaves novas (`configuration.section.*`
  ×5, `ingress.delivery.*`/`ingress.token.rotate*` ×4), conferidas linha a
  linha contra `pt-BR.ts` nesta sessão (seção 14.4/14.3 acima).
- `console/src/i18n/pt-BR.ts` — as mesmas nove chaves, par completo no
  mesmo passo, vocabulário brasileiro conferido (Aprovações, Autonomia,
  Rotacionar, Autenticado — nenhum termo europeu).
- `console/tests/unit/surfaces/machine-token-groups.test.tsx` — T017, dois
  `it()` novos (`:710-741`).
- `console/tests/unit/surfaces/config-editor.test.tsx` — T019, três `it()`
  novos (`:452-500`) e o helper `editor()` ganhou `locale="en"`; um ajuste
  de lint (`:475`) sem mudança de comportamento.
- `console/tests/unit/surfaces/object-list.test.tsx` — só o helper
  `editor()` ganhou `locale="en"`, nenhum teste novo.
- `console/tests/unit/surfaces/settings-alert-intake.test.tsx` — T020, um
  `describe` reescrito e ampliado de um para sete `it()` (`:389-527`), mais
  o helper `serveWithADeliveryTokenNamed` (novo).

**Nenhum outro arquivo committed ou não-committed foi tocado por esta
sessão** — conferido por `git status --porcelain` no início e no fim, e por
`git diff --cached --stat` (só as duas renomeações já staged antes desta
sessão, inalteradas).

### 14.12 O que fica pendente, nomeado, não escondido

- **T021, T022, T023, T024** — nenhuma linha de código escrita; desenho
  completo para as quatro, seções 14.5 a 14.8 acima. T023 carrega um achado
  crítico (um teste committed codificando o defeito) que quem continuar
  precisa ler antes de tocar `grants.tsx`.
- **A suíte transversal** (`transversal-rules.spec.ts`) — não lida, nenhuma
  exceção removida, mesmo as que T019/T020 provavelmente já desbloqueiam.
- **O acceptance spec inteiro** (`vocabulary-defaults.acceptance.spec.ts`) —
  não rodado depois de T019/T020; o efeito esperado (algumas alegações de
  `:269`/`:294`/`:369` passando a verde) não foi confirmado.
- **`uv run python -m tools.console_gate test`** (cobertura) — não rodado;
  só os sete arquivos tocados foram rodados via `vitest run` puro.
- **T020**: nenhum teste cobre o caso em que a própria sessão do navegador
  carregaria `webhook.deliver` nos seus `scopes` armazenados — o filtro
  existe, a prova não (seção 14.4, fim).
- **T021**: nenhum arquivo Python nem de fixture tocado — o desenho inclui
  mudança de schema (`SuggestionView`) que precisa de
  `tests/contract/fixtures` rodando depois, não feito.
- Tudo que as seções 1-13 já listavam como pendente e que esta sessão não
  tinha escopo para tocar (T001-T016, T018 já fechados; T025 em diante)
  continua exatamente como estava.

Nenhum destes tem dono fora da própria feature 030; nada foi transferido
para outra spec da onda.

## 15. Continuação — sessão 7: T021 implementado, verificado camada por camada

**Escopo desta seção: só T021 (evidência da sugestão do estate).** T022-T028 e
demais tarefas continuam exatamente no estado que a seção 14 deixou —
conferido de novo ao final (15.7), não só assumido.

### 15.1 Veredito

**T021 — FEITO.** `resource_label`/`resource_kind` percorrem as três camadas
(domínio → rota HTTP → console) fielmente ao desenho da seção 14.5, a
alegação do acceptance spec que cobre o caso `vm-201-metrics` foi confirmada
vermelha e depois verde pelo mesmo comando, e o caso não resolvível
(`redis`/`ct-9042`) foi verificado ponta a ponta — fixture, função de
evidência e teste unitário — sem que o id cru sobre em lugar nenhum do texto
renderizado.

### 15.2 A ledger de T021, cláusula por cláusula

| Cláusula | Estado | Detalhe |
|---|---|---|
| FR-008, "NÃO DEVEM exibir o identificador cru do recurso... no texto da evidência" | FEITO | `console/src/surfaces/screens/integrations.tsx:184-196` (`evidenceOf`) nunca interpola `fromResource`/`from_resource` na sentença, em nenhum dos dois ramos. Prova pela fixture real: `resource_label`/`resource_kind` de `redis` e `metrics-store` em `fixtures/scenarios/populated/integrations.json` (seção 15.6). |
| FR-008, "A evidência DEVE nomear o recurso de forma legível — nome do serviço e localização" | FEITO (caso resolvível) | Ramo `resourceLabel !== ''` de `evidenceOf` usa `resource_label` (`platform/estate/suggestions.py:111`, = `resource.display_name`) em vez do `from_resource` cru. |
| FR-008, "no padrão 'grafana, CT 133'" | FEITO, com desvio de forma nomeado | A chave `catalogue.integrations.suggested.evidence` (pré-existente, não recriada nesta sessão) usa "Found at {address}, on resource {resource}" em vez do padrão `nome, localização` citado literalmente na especificação; o desenho da seção 14.5 já decidiu não reescrever essa frase, só trocar o que alimenta `{resource}` — decisão herdada, não desta sessão. |
| FR-008, "o identificador DEVE ficar no destino do link" | PARCIAL, desvio já documentado na seção 14.5 e mantido | O identificador cru fica em `data-resource` no `<li data-testid="suggested-integration">` (`integrations.tsx:461`), não na URL do link Connect (`detailHref`, que nunca carregou o id do recurso, só o nome da integração). A seção 14.5 já registrou essa escolha e a razão (risco de estender `url-state.ts` sem testar a fundo); esta sessão implementou exatamente essa decisão, não uma nova. |
| FR-011, identificador recuperável em contexto técnico | FEITO | `data-resource` no `<li>` (`integrations.tsx:461`) e o campo `from_resource` continua servido sem alteração pela API (`SuggestionView.from_resource`, `gateway/http/routes/integrations.py:97` — campo pré-existente, não tocado). |
| Edge case "recurso sem nome resolvível: mostra endereço, tipo... nunca um rótulo vazio" | FEITO | Ramo `resourceLabel === ''` de `evidenceOf` usa a chave nova `catalogue.integrations.suggested.evidence.unresolved` (`en.ts:1404-1405`, `pt-BR.ts:1202-1203`), que só tem placeholders `{address}`/`{kind}` — nenhum caminho para um texto vazio nem para o id. Prova ponta a ponta na seção 15.6. |
| "En e pt-BR nascem juntos" | FEITO | `en.ts:1404-1405` e `pt-BR.ts:1202-1203` adicionados na mesma sessão; `pnpm exec vitest run tests/unit/i18n/catalogue.test.ts` — 11 passed (seção 15.5). |

### 15.3 As mudanças, por camada, com `file:line`

**Domínio (`platform/estate/suggestions.py`)**
- `Suggestion` ganha `resource_label: str` (`:60`) e `resource_kind: str`
  (`:63`), com docstring explicando que `resource_label` nunca cai para o id
  — ao contrário de `because`.
- `to_record()` serializa os dois campos novos (`:72-73`).
- `suggest_integrations()` popula os dois campos na construção
  (`:111-112`): `resource_label=resource.display_name,
  resource_kind=resource.kind`.

**Rota HTTP (`gateway/http/routes/integrations.py`)**
- `SuggestionView` ganha `resource_label: str` (`:103`) e `resource_kind: str`
  (`:105`).
- O único call site que constrói `SuggestionView(...)` (dentro de
  `list_integrations`) passa os dois campos adiante (`:348-349`).

**Fixture (`tools/mockplane/dataset/served.py`)**
- Bloco `redis` (caso não resolvível, dentro de `integration_records()`):
  `"resource_label": ""` (`:1753`), `"resource_kind": "container"`
  (`:1754`) — consistente com o `because` já existente ("a container called
  'ct-9042'").
- Bloco `metrics-store` (caso resolvível): `"resource_label": "prometheus"`
  (`:1810`), `"resource_kind": "guest"` (`:1811`) — consistente com o
  `because` já existente ("a guest labelled prometheus").
- Regenerado por ferramenta, nunca por edição manual de JSON:
  `uv run python -m tools.mockplane contract` (openapi) e
  `uv run python -m tools.mockplane build` (fixtures) — resultados na 15.5,
  efeito colateral do rebuild nomeado por completo na 15.8.

**Console (`console/src/surfaces/screens/integrations.tsx`)**
- `CatalogueItem['suggested']` ganha `resourceLabel`/`resourceKind`
  (`:120-121`).
- `suggestionOf()` lê os dois campos novos do payload (`:162-174`).
- Função nova `evidenceOf(locale, suggestion)` (`:176-196`): escolhe entre a
  chave resolvida e a nova chave `.unresolved` conforme `resourceLabel` está
  vazio ou não; nunca interpola `fromResource`.
- JSX: o `<span data-testid="suggestion-evidence">` passa a chamar
  `evidenceOf(locale, item.suggested)` (`:469`, antes interpolava
  `item.suggested?.fromResource` diretamente); o `<li
  data-testid="suggested-integration">` ganha
  `data-resource={item.suggested?.fromResource ?? ''}` (`:461`).

**i18n**
- `catalogue.integrations.suggested.evidence.unresolved` nova em
  `console/src/i18n/en.ts:1404-1405` ("Found at {address}, on a {kind}") e
  `console/src/i18n/pt-BR.ts:1202-1203` ("Encontrado em {address}, em um
  recurso do tipo {kind}" — fugi da tradução literal "on a" para evitar
  concordância de gênero sobre um substantivo (`kind`) que chega cru do
  backend e não tem gênero conhecido). A chave `.suggested.evidence`
  pré-existente foi mantida como estava nos dois locales; só o que alimenta
  `{resource}` mudou, no console.

**Testes**
- `tests/unit/platform/estate/test_integration_suggestions.py` —
  `resource()` ganhou parâmetro `display_name: str | None = None`
  (default preserva o comportamento anterior); classe nova
  `TestTheResourceLabelAndKind` com dois casos (`:130-159`).
- `tests/unit/gateway/http/test_catalogue_ordering_and_gaps.py` — um teste
  novo, `test_a_suggestion_carries_the_resources_label_and_kind` (`:118-127`),
  batendo na rota HTTP de ponta a ponta (não só a função de domínio).
- `console/tests/unit/surfaces/integrations.test.tsx` — helper `integration()`
  ganhou `resourceKind`/`resourceLabel` no tipo do parâmetro `suggested`; o
  teste pré-existente "shows the evidence..." (`:369-387`) teve sua asserção
  ajustada (comparava contra o id cru `monitoring`, agora compara contra o
  rótulo legível `observability-01`); três testes novos (`:389-436`).

### 15.4 Os vermelhos confirmados, comando por comando, com a mensagem observada

**Backend, antes de tocar `suggestions.py`/`integrations.py`** — comando
`uv run pytest -q tests/unit/platform/estate/test_integration_suggestions.py
tests/unit/gateway/http/test_catalogue_ordering_and_gaps.py`, resultado
`3 failed, 18 passed`:

1. `TestTheResourceLabelAndKind::test_a_resolvable_resource_carries_its_own_label_and_kind`
   (`test_integration_suggestions.py:138`):
   ```
   AttributeError: 'Suggestion' object has no attribute 'resource_label'
   ```
2. `TestTheResourceLabelAndKind::test_a_resource_with_no_display_name_carries_an_empty_label_never_the_id`
   (`:156`): a mesma `AttributeError: 'Suggestion' object has no attribute
   'resource_label'`.
3. `test_a_suggestion_carries_the_resources_label_and_kind`
   (`test_catalogue_ordering_and_gaps.py:126`):
   ```
   KeyError: 'resource_label'
   ```

**Drift do OpenAPI committed, antes de rodar `mockplane contract`** — comando
`uv run pytest -q
tests/unit/tools/mockplane/test_verification.py::test_the_committed_document_is_what_the_application_generates`,
`1 failed`:
```
AssertionError: the committed OpenAPI document has drifted from the routes;
run 'python -m tools.mockplane contract' and rebuild the fixtures
```

**Fixtures contra o documento, antes de tocar `served.py`/rodar
`mockplane build`** — comando `uv run pytest -q
"tests/contract/fixtures/test_dataset_contract.py::test_every_fixture_validates_against_the_api_document"`,
`6 failed, 2 passed` (falharam `populated`, `degraded`, `incident-live`,
`restricted`, `audit-flooded`, `scale`; passaram `first-run`/`empty`, que não
carregam sugestão nenhuma):
```
AssertionError: GET /v1/integrations : /integrations/0/suggested: object
matches none of the 2 declared shapes
GET /v1/integrations : /integrations/15/suggested: object matches none of
the 2 declared shapes
```
Confirma exatamente o aviso da tarefa: um `Suggestion`/`SuggestionView` que
ganha campo novo invalida as seis fixtures que herdam de `populated`, de uma
vez — não é permitido corrigir isso por edição manual de um único arquivo
JSON.

**Console, o teste pré-existente, depois que a implementação do console já
existia** (a implementação já estava escrita quando rodei o teste pela
primeira vez após editá-la; o vermelho abaixo prova que a asserção antiga do
teste não bate com o novo comportamento, e foi ajustada em seguida) —
comando `pnpm exec vitest run tests/unit/surfaces/integrations.test.tsx`,
`1 failed, 25 passed`:
```
shows the evidence the API already computed, and a connect action
Expected element to have text content: monitoring
Received: Found at 192.168.68.159:3000, on a
```

**Console, os três testes novos — vermelho confirmado retirando a
implementação, não só inferido.** Técnica: `git stash push --keep-index --
console/src/surfaces/screens/integrations.tsx console/src/i18n/en.ts
console/src/i18n/pt-BR.ts` (devolve exatamente esses três arquivos ao estado
antes desta sessão, deixando os arquivos de teste como estavam — já
editados), rodei `pnpm exec vitest run tests/unit/surfaces/integrations.test.tsx`,
depois `git stash pop`. Resultado do vitest contra a implementação antiga:
`4 failed, 25 passed`:

1. `shows the evidence the API already computed, and a connect action`:
   ```
   Expected element to have text content: observability-01
   Received: Found at 192.168.68.159:3000, on resource monitoring
   ```
2. `never names the resource by its raw identifier, in the evidence or the link`:
   ```
   Expected element not to have text content: monitoring
   Received: Found at 192.168.68.159:3000, on resource monitoring
   ```
3. `keeps the raw resource identifier recoverable as a data attribute`:
   ```
   Expected the element to have attribute: data-resource="monitoring"
   Received: null
   ```
4. `names a resource address and kind, never a blank label, when the estate
   never resolved a name`:
   ```
   Expected element to have text content: container
   Received: Found at 10.20.0.187:6379, on resource ct-9042
   ```

**Como confirmei que o `git stash pop` restaurou tudo, e não só que o texto
do comando disse que sim**: depois do pop, `git status --porcelain` mostrou
os mesmos três arquivos de volta em `modified` (não em `deleted`/ausentes);
rodei de novo `pnpm exec vitest run tests/unit/surfaces/integrations.test.tsx`
e obtive `29 passed` (seção 15.5); e mais tarde, já com o resto da sessão
completo, `uv run python -m tools.console_gate typecheck`, `lint`,
`format-check` e `test` (2336 testes, toda a suíte do console, não só este
arquivo) todos limpos — se o pop tivesse restaurado algo pela metade, o
typecheck ou a suíte inteira teriam acusado.

**Acceptance e2e, a alegação já escrita antes desta sessão** — comando
`uv run python -m tools.spec_validation browser --feature
specs_v6/030-vocabulario-defaults --test
console/tests/e2e/vocabulary-defaults.acceptance.spec.ts`, rodado **antes de
qualquer edição desta sessão**: `3 failed, 1 skipped, 10 passed`. O teste de
`:380` ("a suggested integration never shows the estate's raw resource
identifier as its evidence"):
```
Error: the evidence "Found at http://thicket.example.invalid:9090, on
resource vm-201-metrics" names the estate's raw resource id rather than a
legible resource

expect(received).not.toContain(expected) // indexOf

Expected substring: not "vm-201-metrics"
Received string:        "Found at http://thicket.example.invalid:9090, on
resource vm-201-metrics"
```
(Os outros dois vermelhos desse mesmo comando, `create-person` e
`session-origin`, pertencem a T025 e T022 — nomeados na 15.7, não tocados.)

### 15.5 Os verdes, comando por comando

- `uv run pytest -q tests/unit/platform/estate/test_integration_suggestions.py
  tests/unit/gateway/http/test_catalogue_ordering_and_gaps.py` → `21 passed`.
- `uv run python -m tools.mockplane contract` → `wrote
  /srv/workspaces/NinjaSRE/fixtures/contract/openapi.json`; reconferido por
  `uv run pytest -q
  tests/unit/tools/mockplane/test_verification.py::test_the_committed_document_is_what_the_application_generates`
  → `1 passed`.
- `uv run python -m tools.mockplane build` → `wrote 227 files across 6
  scenarios`; reconferido por `uv run pytest -q tests/contract/fixtures/
  tests/unit/tools/mockplane/` → `290 passed` (inclui
  `test_rebuilding_the_dataset_reproduces_what_is_committed`, o teste
  byte-idêntico, e a validação de fixture contra o documento nos oito
  cenários).
- `pnpm exec vitest run tests/unit/surfaces/integrations.test.tsx` → `29
  passed` (depois do ajuste de lint da 15.9, reconfirmado outra vez, mesmo
  resultado).
- `pnpm exec vitest run tests/unit/i18n/catalogue.test.ts` → `11 passed`.
- `uv run pytest -q tests/unit/platform/estate/
  tests/unit/gateway/http/test_catalogue_ordering_and_gaps.py
  tests/contract/fixtures/ tests/unit/tools/mockplane/` → `452 passed`.
- `uv run pytest -q tests/contract/fixtures tests/unit/gateway/http` → `530
  passed` — mesmo comando e mesma contagem que o orquestrador já tinha
  verificado por conta própria; reconferido depois do ajuste de lint no
  arquivo de teste do console (que não toca Python) para fechar o círculo.
- `uv run python -m tools.console_gate typecheck` → limpo.
- `uv run python -m tools.console_gate lint` → limpo (depois do ajuste da
  15.9).
- `uv run python -m tools.console_gate format-check` → `Checking
  formatting... All matched files use Prettier code style!`.
- `uv run python -m tools.console_gate test` → `Test Files 141 passed (141)`,
  `Tests 2336 passed (2336)`; cobertura `Statements 94.34% / Branches 90.31%
  / Functions 92.1% / Lines 96.34%`; confirmado `EXIT=0` numa segunda
  execução independente.
- `uv run python -m tools.spec_validation browser --feature
  specs_v6/030-vocabulario-defaults --test
  console/tests/e2e/vocabulary-defaults.acceptance.spec.ts`, **depois** da
  implementação: `2 failed, 1 skipped, 11 passed` — o teste de `:380` agora:
  ```
  ✓  13 [behaviour] › tests/e2e/vocabulary-defaults.acceptance.spec.ts:380:3
  › no covered route prints a transport identifier where a reader expects a
  name › a suggested integration never shows the estate's raw resource
  identifier as its evidence (371ms)
  ```
  Os dois vermelhos restantes (`create-person` em `:213`, `session-origin`
  em `:412`) têm a mensagem **idêntica**, caractere a caractere, à execução
  de antes — nada mudou para eles.

### 15.6 O caso não resolvível (`redis`/`ct-9042`) — prova de que não sobra id nenhum

A pergunta do orquestrador é exatamente o ponto do campo `resource_label`
vazio em vez de um default: aqui está a cadeia completa, não só a garantia de
que o teste unitário passa.

1. **A fixture, depois do rebuild**, lida diretamente do JSON committed
   (`fixtures/scenarios/populated/integrations.json`, entrada `redis`):
   ```
   {'address': 'http://zephyr.example.invalid:6379',
    'because': "this estate holds a container called 'ct-9042' at
    198.51.100.197, which is where redis was found rather than where anyone
    guessed it would be",
    'from_resource': 'ct-9042',
    'resource_kind': 'container',
    'resource_label': ''}
   ```
   `resource_label` está vazio — não é um valor de fallback, é a string
   vazia mesma. A mesma entrada tem `health: 'unconfigured'` e `category:
   'database'`, então ela renderiza na seção Suggested de `/integrations`
   sem filtro nenhum — não é um caso hipotético, é alcançável na tela real.
2. **`evidenceOf`** (`integrations.tsx:184-196`) testa `resourceLabel ===
   ''` e, quando verdadeiro, chama `message(locale,
   'catalogue.integrations.suggested.evidence.unresolved', { address, kind
   })` — essa chave (`en.ts:1404-1405`: `'Found at {address}, on a {kind}'`)
   não tem placeholder `{resource}`/`{fromResource}` nenhum; não existe
   caminho de código que injete o id cru nessa sentença.
3. **Prova em teste**, `console/tests/unit/surfaces/integrations.test.tsx:411-436`
   ("names a resource address and kind, never a blank label, when the
   estate never resolved a name"): alimenta o componente com uma sugestão no
   mesmo formato exato da fixture `redis` (`resourceLabel` omitido,
   `resourceKind: 'container'`) e afirma que a evidência contém o endereço e
   "container", e **não** contém `'ct-9042'` — vermelho antes (seção 15.4,
   item 4), verde depois (seção 15.5).
4. **O que este teste não prova sozinho**: o acceptance spec e2e
   (`vocabulary-defaults.acceptance.spec.ts:380-406`) itera sobre todo
   `suggestion-evidence` renderizado e afirma que nenhum contém
   `'vm-201-metrics'` — a entrada `redis` também passa por esse laço (e
   passa, trivialmente, já que sua evidência nunca continha esse texto), mas
   o spec nunca afirma nada sobre `'ct-9042'` por nome. Não dirigi um
   navegador contra a linha do `redis` especificamente para conferir esse
   texto; a prova do caso não resolvível descansa nos itens 1-3 acima, não
   numa observação de navegador daquela linha em particular — registrando o
   limite exato da prova em vez de deixar implícito que o e2e cobriu os dois
   casos.
5. **O identificador não desaparece do produto** — ele sai da frase e vira
   `data-resource="ct-9042"` no `<li data-testid="suggested-integration">`
   (`integrations.tsx:461`), satisfazendo FR-011. Essa é a decisão já
   registrada na seção 14.5 (usar atributo de dado em vez de estender o link
   Connect), implementada nesta sessão, não redecidida.

### 15.7 O que não foi tocado — confirmado, não só assumido

- **Members & roles (T022-T024)** e **criação de pessoa (T025-T028)**: nenhum
  arquivo de `members.tsx`, `grants.tsx`, `tokens.tsx` ou rota de identidade
  foi tocado por esta sessão. O e2e de antes e depois desta sessão prova isso
  por comportamento, não só por `git status`: os dois vermelhos que sobram
  (`create-person` em `:213`, `session-origin` em `:412`) têm a mensagem
  idêntica nas duas execuções (seção 15.4 e 15.5) — se esta sessão tivesse
  mudado algo que os afeta, a mensagem ou a contagem de elementos teria
  mudado, e não mudou.
- **Efeito indireto verificado, não ignorado**: o rebuild mandatório da 15.8
  corrigiu o nome do token de sessão do navegador na fixture (`"console"` →
  `"Console sign-in"`), que é exatamente o valor que o comentário do teste
  T022 (`vocabulary-defaults.acceptance.spec.ts:417-434`) cita como a
  correção que falta para aquele teste sair do `test.skip()`. Conferido: o
  teste **não** entrou no ramo de skip nem antes nem depois (`rendered` já
  era `> 0` nas duas execuções — o `session-group` já era encontrado por
  algum outro caminho, independente do nome do token) e falhou na mesma
  asserção (`session-origin` ausente) com a mesma contagem (`14 × locator
  resolved to 0 elements`) nas duas vezes. Ou seja: o rebuild não mudou o
  resultado desse teste — nem para melhor nem para pior — mas é um fato que
  vale registrar para quem pegar T022 em seguida, porque a fixture que o
  comentário do teste pede como pré-requisito já existe agora.
- **Nenhum baseline visual tocado**: `git status --porcelain console/visual/`
  vazio, conferido depois de toda a sessão.
- **Nenhum processo em segundo plano deixado rodando**: `ps aux | grep -iE
  "uvicorn|next-server|playwright|mockplane"` sem resultado, e nenhum
  listener em `8423`/`8424` depois das duas execuções do e2e (o harness do
  `tools.console_e2e` derruba o servidor mock e o console sozinho ao fim de
  cada corrida — confirmado no log de ambas: "Shutting down / Application
  shutdown complete. / Finished server process").
- **A renomeação staged de dois acceptance specs** (`010-provider-...` →
  `provider-out-of-the-box...`, `020-confiabilidade-...` →
  `screen-truthfulness...`) segue exatamente como estava — não fiz `git add`
  nem `git restore` nela.

### 15.8 Efeito colateral do rebuild mandatório — nomeado por completo, não escondido

`uv run python -m tools.mockplane build` regenerou 8 arquivos de fixture, não
só o `populated/integrations.json` que é a substância de T021. Os outros
seis:

```
fixtures/scenarios/empty/principal.json
fixtures/scenarios/first-run/principal.json
fixtures/scenarios/populated/principal.json
fixtures/scenarios/populated/principals.json
fixtures/scenarios/populated/tokens.json
fixtures/scenarios/restricted/principal.json
```

carregam permissões novas nos papéis (`org.delete`, `owner.assign`,
`impersonation.use`, `estate.manage`, `estate.read`, `identity.write`,
`incident.manage`, `incident.read`, `knowledge.write`, `report.read`,
`sso.manage`, `webhook.deliver`, `audit.export`, `credential.read`,
`credential.write`), um principal novo (`Jordan Vance`/`user-departed`) e a
renomeação do token de sessão do navegador (`"console"` → `"Console
sign-in"`). **Nada disso é substância de T021 e nada foi editado à mão**:
é o resultado determinístico de `tools.mockplane.dataset.build.write_all()`
lido do `served.py` que já estava commitado nesta árvore antes desta sessão
começar (confirmado por `grep` em `served.py` antes de tocar nele: "Jordan
Vance", "user-departed" e `"name": "Console sign-in"` já estavam lá).
`git log --oneline -3 -- tools/mockplane/dataset/served.py
platform/identity/permissions.py` mostra um commit ancestral,
`9340c1e "fix: regenerate the dataset and the API contract that had drifted
from their sources"`, seguido de dois commits que voltaram a tocar essas
fontes (`039efe9`, `a4651c6`) sem rodar o rebuild de novo — ou seja, esse
drift já existia antes de eu tocar em `served.py`, e `mockplane build` não
tem como regenerar seletivamente um único arquivo de um único cenário: é
tudo ou nada.

Decisão tomada: manter o resultado do rebuild como está, em vez de reverter
os seis arquivos à mão de volta ao estado desatualizado — reverter seria uma
edição manual de fixture, exatamente o que a instrução desta tarefa proíbe, e
deixaria `test_rebuilding_the_dataset_reproduces_what_is_committed` vermelho
de novo por um motivo que não é meu. Verificado que isso não é uma regressão:
a suíte inteira de fixtures (`tests/contract/fixtures/` +
`tests/unit/tools/mockplane/`, 290 testes), a suíte ampla que o orquestrador
já tinha rodado (`tests/contract/fixtures tests/unit/gateway/http`, 530
testes) e a suíte inteira do console gate (2336 testes) passam depois do
rebuild — nenhuma delas prendia numa asserção que dependesse dos valores
antigos. O efeito sobre o teste e2e de T022 está registrado à parte, na 15.7.

### 15.9 Gates rodados nesta sessão, comando exato e resultado real

1. `uv run python -m tools.console_gate typecheck` → limpo.
2. `uv run python -m tools.console_gate lint` → **vermelho na primeira
   corrida**: `@typescript-eslint/no-unnecessary-condition` em
   `integrations.test.tsx:437` (`expect(evidence.textContent?.trim())`, uma
   asserção redundante com as duas `toHaveTextContent` anteriores no mesmo
   teste). Corrigido removendo a linha redundante — a informação que ela
   checava (texto não vazio) já está provada pelas duas asserções positivas
   ao lado. Segunda corrida: limpo.
3. `uv run python -m tools.console_gate format-check` → limpo.
4. `uv run python -m tools.console_gate test` → `Test Files 141 passed
   (141)`, `Tests 2336 passed (2336)`, cobertura 94.34%/90.31%/92.1%/96.34%
   (statements/branches/functions/lines), `EXIT=0` confirmado numa segunda
   execução isolada.
5. `uv run ruff check platform/estate/suggestions.py
   gateway/http/routes/integrations.py tools/mockplane/dataset/served.py
   tests/unit/platform/estate/test_integration_suggestions.py
   tests/unit/gateway/http/test_catalogue_ordering_and_gaps.py` → `All
   checks passed!`.
6. `uv run ruff format --check` nos mesmos cinco arquivos → `5 files already
   formatted`.
7. `uv run mypy` nos mesmos cinco arquivos (duas invocações) → `Success: no
   issues found in 2 source files` e depois `in 3 source files`.
8. `uv run pytest -q tests/unit/platform/estate/
   tests/unit/gateway/http/test_catalogue_ordering_and_gaps.py
   tests/contract/fixtures/ tests/unit/tools/mockplane/` → `452 passed`.
9. `uv run pytest -q tests/contract/fixtures tests/unit/gateway/http` → `530
   passed`.
10. `make check-constants` → `EXIT=0`.
11. `make check-imports` → `Contracts: 7 kept, 0 broken.`, `EXIT=0`.
12. `make check-console-boundary` → `EXIT=0`.
13. `uv run python -m tools.spec_validation browser --feature
    specs_v6/030-vocabulario-defaults --test
    console/tests/e2e/vocabulary-defaults.acceptance.spec.ts` — rodado duas
    vezes (antes: `3 failed, 1 skipped, 10 passed`; depois: `2 failed, 1
    skipped, 11 passed`). Detalhe na 15.4/15.5.

**Não rodado**: `make lint`/`make typecheck` no repositório inteiro (as
corridas focadas de `ruff`/`mypy`/`import-linter`/`console_gate` acima cobrem
todo arquivo que esta sessão tocou; o pedido do orquestrador de fechar o
registro chegou no meio da verificação, e as corridas amplas de
`pytest`/`console_gate test` já dão a cobertura equivalente para o que
mudou). `make verify` — reservado ao orquestrador, como a instrução desta
tarefa pede. `console-visual-accept`/`console-e2e` completo — fora de
escopo; confirmado em vez disso que nenhum baseline visual mudou (15.7).

### 15.10 Arquivos tocados nesta sessão — só estes, nada mais

Código e testes:
- `platform/estate/suggestions.py`
- `gateway/http/routes/integrations.py`
- `tools/mockplane/dataset/served.py`
- `tests/unit/platform/estate/test_integration_suggestions.py`
- `tests/unit/gateway/http/test_catalogue_ordering_and_gaps.py`
- `console/src/surfaces/screens/integrations.tsx`
- `console/src/i18n/en.ts`
- `console/src/i18n/pt-BR.ts`
- `console/tests/unit/surfaces/integrations.test.tsx`

Fixture, gerado por ferramenta (nunca editado à mão):
- `fixtures/contract/openapi.json`
- `fixtures/scenarios/populated/integrations.json` (substância de T021)
- `fixtures/scenarios/empty/principal.json`,
  `fixtures/scenarios/first-run/principal.json`,
  `fixtures/scenarios/populated/principal.json`,
  `fixtures/scenarios/populated/principals.json`,
  `fixtures/scenarios/populated/tokens.json`,
  `fixtures/scenarios/restricted/principal.json` (efeito colateral do
  rebuild, seção 15.8)

**Nenhum outro arquivo do repositório foi tocado por esta sessão** —
conferido por `git status --porcelain | sort` ao final, cruzado item a item
contra a lista de arquivos que já estavam modificados por sessões anteriores
(impressa pelo próprio orquestrador depois do `git stash pop`): todo arquivo
fora da lista acima já aparecia modificado antes desta sessão tocar em
qualquer coisa, e nada foi `git add`/`git restore`/`git commit` por este
trabalho.

### 15.11 O que fica pendente, nomeado, não escondido

- O desvio de FR-008 ("o identificador DEVE ficar no destino do link", ponto
  15.2) — decisão já tomada na seção 14.5 pela sessão anterior, implementada
  fielmente aqui; quem quiser a leitura mais literal da especificação
  (id como parâmetro de query em `detailHref`) precisa estender
  `url-state.ts`, nomeado ali como trabalho maior, não feito.
- T022 (identificação de sessão) segue não implementado; o achado da 15.7
  (a fixture que o comentário do próprio teste pede já existe agora) é uma
  informação nova para quem pegar essa tarefa, não uma implementação parcial
  dela.
- T023, T024, T025-T028: inalterados, seções 14.6-14.8 continuam a única
  fonte sobre eles.
- A suíte transversal (`transversal-rules.spec.ts`) não foi lida nem tocada
  nesta sessão.

## 16. Continuação — sessão 8: T022, T023 e T024 fechados (Members & roles), mais a varredura de identificadores de requisito pedida pelo orquestrador

Dispatch explicitamente restrito a três tarefas de um componente só — T022,
T023, T024, todas em `console/src/surfaces/tokens.tsx`,
`console/src/surfaces/grants.tsx` e `console/src/surfaces/settings/members.tsx`.
T025 em diante não foi tocado. Os desenhos das seções 14.6-14.8 (sessão 6)
foram implementados como escritos, não redesenhados.

### 16.1 Veredito

| Tarefa | Estado | Detalhe |
|---|---|---|
| T022 — identificação de sessão | **FEITO** | `tokens.tsx:313-340,421,438-440`, `members.tsx:122-130,224-227`, `en.ts:1510`, `pt-BR.ts:1293`. Alegação de sessão do acceptance spec verde (16.6). |
| T023 — resumo humano do grant | **FEITO** | `grants.tsx:81-82,103-130,342-354,379-392`, `members.tsx:84-107,190-193`, `en.ts:1483-1485`, `pt-BR.ts:1268-1270`. Bloco `grants.test.tsx:496-523` original reescrito por inteiro (16.3). |
| T024 — papel legível no grant listado | **FEITO** | `grants.tsx:299-305` (span simples no lugar de `<Badge>`), import de `Badge` removido. Teste novo em `grants.test.tsx:497-511`. |

### 16.2 T022 — identificação de sessão, o vermelho e o verde

**Vermelho de unidade, confirmado antes de tocar `tokens.tsx`/`members.tsx`.**
Escrevi dois `it()` novos em `describe('active sessions, grouped by who
holds them', ...)` (`tokens.test.tsx`, hoje linhas 413-431) e um campo
`origin` nos fixtures `SESSION_LABELS`/`SESSIONS` do mesmo bloco, com
`tokens.tsx`/`members.tsx` ainda exatamente como a sessão 7 os deixou (nenhum
campo `origin`). `pnpm exec vitest run tests/unit/surfaces/tokens.test.tsx
--pool=forks`:

```
FAIL tests/unit/surfaces/tokens.test.tsx > active sessions, grouped by who holds them > names the origin the group's first session started from, not a bare number
TestingLibraryElementError: Unable to find an element by: [data-testid="session-origin"]
 ❯ tests/unit/surfaces/tokens.test.tsx:418:28

FAIL tests/unit/surfaces/tokens.test.tsx > active sessions, grouped by who holds them > names a column for the origin, beside who holds the session
Error: expect(element).toHaveTextContent()
Expected element to have text content:
  Started
Received:
  PrincipalExpires
 ❯ tests/unit/surfaces/tokens.test.tsx:427:51
```

Nenhuma técnica de stash foi necessária aqui: o campo `origin` simplesmente
não existia em `SessionEntry`/`SessionLabels` no ponto em que os testes
foram escritos, então o vermelho é direto.

**Vermelho de aceite, confirmado com o mesmo comando que o orquestrador
citou**, antes de qualquer edição:

```
uv run python -m tools.spec_validation browser --feature specs_v6/030-vocabulario-defaults \
  --test console/tests/e2e/vocabulary-defaults.acceptance.spec.ts
```
Resultado: **2 failed, 1 skipped, 11 passed** — exatamente o número que a
tarefa citou. A falha da sessão:

```
Error: no session on this page states where it came from — only who holds it and a count
expect(locator).toHaveCount(expected) failed
Locator:  getByTestId('session-group').first().getByTestId('session-origin')
Expected: 1
Received: 0
```
(A outra falha, `create-person`, pertence a T025-T028 e não foi tocada.)

**O que foi implementado**, seguindo a seção 14.6 ao pé da letra:

- `SessionEntry.origin: string` e `SessionLabels.origin: string`
  (`tokens.tsx:313-327,329-340`) — o mesmo campo já formatado como tempo
  relativo que `expires` usa.
- Cabeçalho de coluna novo em `data-testid="session-columns"`
  (`tokens.tsx:421`) e `<span data-testid="session-origin">` por grupo
  (`tokens.tsx:438-440`), lendo `group.sessions[0]?.origin ?? ''` — a mesma
  convenção "usa o primeiro do grupo" que `expires` já seguia.
- `members.tsx:126-130`: `origin: timestamp(locale, text(token,
  'created_at'), now, zone).relative` — o único fato adicional que o
  backend já tinha (`TokenView.created_at`, `gateway/http/routes/identity.py`)
  e ainda não aparecia. Não há dispositivo/origem de verdade para mostrar
  hoje, em nenhum cenário — confirmado de novo (a sessão 6 já tinha
  verificado o schema `TokenView`, `gateway/http/routes/identity.py:120-130`,
  sem campo de dispositivo/rede).
- `members.tsx:227`: `origin: message(locale, 'admin.column.origin')` nos
  labels passados a `SessionPanel`.
- `admin.column.origin` = "Started" / "Início" (`en.ts:1510`,
  `pt-BR.ts:1293`).

**Verde, depois da implementação**, mesmo comando do orquestrador (desta vez
combinado com `scroll-budget.spec.ts` num único build para economizar um
ciclo — ver 16.7):

```
uv run python -m tools.spec_validation browser --feature specs_v6/030-vocabulario-defaults \
  --test console/tests/e2e/vocabulary-defaults.acceptance.spec.ts \
  --test console/tests/e2e/scroll-budget.spec.ts
```
```
✓  25 [behaviour] › tests/e2e/vocabulary-defaults.acceptance.spec.ts:412:3 › an active session
   identifies itself by who holds it and from where › a session group names an origin or
   device, not just a name and a raw count (256ms)
...
1 failed   (create-person, T025-T028, intocado, corretamente ainda vermelho)
1 skipped  (wizard preview, dependente de dado de fixture, sem relação com esta fatia)
23 passed
```
A alegação de sessão foi de vermelho a verde nesta sessão. A prova real é o
`✓` acima, não uma leitura de código.

### 16.3 T023 — resumo humano do grant, o achado crítico e o bloco reescrito

**O achado da seção 14.7 se confirmou por inteiro.**
`console/tests/unit/surfaces/grants.test.tsx:496-523` (antes de qualquer
edição desta sessão) tinha, literalmente:

```ts
describe('what a role means, at the point it is chosen', () => {
  const DESCRIPTIONS = {
    viewer: 'investigation.read, report.read',
    operator: 'config.write, credential.write',
    owner: 'org.delete, owner.assign',
  };

  it('describes the role currently selected, not just its name', () => {
    panel({ roleDescriptions: DESCRIPTIONS });
    expect(screen.getByText(DESCRIPTIONS.viewer)).toBeInTheDocument();
  });
  ...
```
Ou seja: o teste committed afirmava que a linha crua de ids separados por
vírgula era o comportamento correto — exatamente o defeito que esta tarefa
existe para remover.

**O bloco inteiro foi reescrito**, não só as expectativas — o comentário
acima dele também, para declarar a verdade nova em vez de descrever o
defeito como intencional (`grants.test.tsx:515-521` agora):
> "The defect this whole block used to assert as correct: a raw,
> comma-separated permission-id line (…) shown as the form's own help text.
> What a role permits is a human summary here instead, with the full
> permission list behind an expansion — `roleDescriptions` now carries both,
> not one string doing duty for two different readers."

O que o bloco reescrito afirma agora (`grants.test.tsx:515-598`, 5 `it()`,
contra 3 antes):
1. `describes the role currently selected by a human summary, not the raw
   permission list` — o texto de ajuda do campo (localizado por
   `aria-describedby`, não a tela inteira) mostra o resumo e não contém
   `investigation.read`.
2. `updates the summary when a different role is chosen` — troca de papel
   troca o resumo.
3. `keeps the full permission list available, closed by default, behind an
   expansion` — `role-permissions` existe, começa fechado (`not
   toHaveAttribute('open')`), e contém a lista crua completa — ainda na
   árvore, só escondida visualmente, mesma convenção que `TokenPanel`'s
   `revoked-tokens` já usa.
4. `describes nothing, and offers no expansion, for a role this console was
   given no catalogue for` — o caso sem catálogo (herdado do original,
   mantido).
5. `does not let the summary grow with the role — 31 permissions read the
   same one sentence as 2` — novo, pedido pela seção 14.7 item 4: fixture
   com 31 permissões (o número real do papel `owner`, citado pela sessão 4),
   provando que o resumo renderizado não contém nenhuma das permissões cruas
   e que seu tamanho fica muito abaixo do que a lista crua ocuparia.

**Vermelho confirmado antes de tocar `grants.tsx`**, mesmo comando
(`pnpm exec vitest run tests/unit/surfaces/grants.test.tsx --pool=forks`),
com `grants.tsx` ainda como a sessão 7 o deixou (`roleDescriptions?:
Readonly<Record<string, string>>`):

```
FAIL … who a grant belongs to, at a glance > names the role with the same word the selector that grants it offers, not a status chip
TestingLibraryElementError: Unable to find an element by: [data-testid="grant-role"]
(o DOM mostrado pelo erro era o <span data-role="neutral" data-known="false" ...>owner</span> do Badge antigo)

FAIL … what a role means, at the point it is chosen > describes the role currently selected by a human summary, not the raw permission list
FAIL … what a role means, at the point it is chosen > updates the summary when a different role is chosen
FAIL … what a role means, at the point it is chosen > keeps the full permission list available, closed by default, behind an expansion
FAIL … what a role means, at the point it is chosen > does not let the summary grow with the role — 31 permissions read the same one sentence as 2
Error: Objects are not valid as a React child (found: object with keys {summary, permissions}). If you meant to render a collection of children, use an array instead.

Test Files  1 failed (1)
     Tests  5 failed | 30 passed (35)
```
Sem stash: `grants.tsx` simplesmente ainda não sabia interpretar
`RoleDescription`, porque eu não tinha editado o arquivo ainda.

**O que foi implementado**, seguindo 14.7:

- `RoleDescription` novo, exportado (`grants.tsx:103-113`):
  `{ summary: string; permissions: readonly string[] }`.
- `GrantPanelProps.roleDescriptions?: Readonly<Record<string,
  RoleDescription>>` (`grants.tsx:127`, era `Record<string, string>`).
- `GrantLabels.rolePermissions: string` novo (`grants.tsx:81-82`) — o rótulo
  do `<summary>` da expansão.
- `Select` do papel usa `roleDescriptions[role].summary`
  (`grants.tsx:342-354`), não mais a string crua.
- `<details data-testid="role-permissions">` novo, ao lado do formulário,
  fechado por padrão, com `roleDescriptions[role].permissions.join(', ')`
  dentro (`grants.tsx:379-392`).
- `members.tsx:84-107`: `roleDescriptions` deixou de ser
  `permissions.join(', ')` e passou a computar, por papel, o número de
  domínios distintos (`permission.split('.')[0]`, mesma régua que
  `machine-token-groups.tsx`'s `domainOf` já usa, reimplementada aqui em
  vez de importada — a função não era exportada) e produzir
  `formatCount(locale, domains.size, 'admin.grant.role.summary.one',
  'admin.grant.role.summary')`. A lista crua de permissões continua
  existindo, só como o segundo campo (`permissions`), não mais interpolada
  na frase.
- `members.tsx:193`: `rolePermissions: message(locale,
  'admin.grant.rolePermissions')` nos labels do `GrantPanel`.
- Chaves novas: `admin.grant.role.summary.one` = "Reaches {count}
  permission domain", `admin.grant.role.summary` = "Reaches {count}
  permission domains", `admin.grant.rolePermissions` = "See every
  permission" (`en.ts:1483-1485`); pt-BR "Alcança {count} domínio/domínios
  de permissão" e "Ver cada permissão" (`pt-BR.ts:1268-1270`).

### 16.4 T024 — papel legível no grant listado

Seguindo 14.8: `<Badge status={row.role} />` (que renderizava o papel com
`uppercase`, `data-role`, `data-known` e a marca visual de chip de status —
contrato que `console/src/components/status.tsx:90-96` reserva para status
de transporte, não para papel) foi trocado por
`<span data-testid="grant-role" className="text-meta">{row.role}</span>`
(`grants.tsx:299-305`) — mesma string, mesmo caso, que a `<option>` do
seletor de papel já usa. O import de `Badge` foi removido de `grants.tsx`
(era o único uso no arquivo).

Teste novo em `describe('who a grant belongs to, at a glance', ...)`
(`grants.test.tsx:497-511`): prova que o texto da linha é `'owner'`, que a
linha **não** carrega `data-role`, e que o texto é idêntico ao da `<option
value="owner">` correspondente no seletor. O vermelho está registrado junto
com o de T023 acima (mesma rodada de `vitest run`, mesmo arquivo) — o erro
específico foi `Unable to find an element by: [data-testid="grant-role"]`,
com o DOM do erro mostrando o `<Badge>` antigo ainda de pé.

### 16.5 Dois bugs nos meus próprios testes, achados e corrigidos — caracterização do meu erro, não do produto

Depois de implementar `grants.tsx`/`members.tsx`, rodei `vitest run` de
novo e dois testes que eu tinha acabado de escrever falharam — não por
defeito de produto, por desenho errado do teste:

1. `describes the role currently selected by a human summary, not the raw
   permission list` falhou com
   `AssertionError: expected <p class="text-meta text-muted pt-1">investigation.read, report.read</p> to be null`
   — a asserção original (`screen.queryByText(/investigation\.read/)).toBeNull()`,
   varredura da tela inteira) contradizia o próprio desenho: a lista crua
   **deve** continuar na árvore, só escondida atrás da expansão. Corrigido
   trocando a asserção para o elemento de ajuda do campo especificamente
   (via `aria-describedby`), deixando a prova de que a lista crua mora
   atrás da expansão para o teste seguinte, que já existia para isso.
2. `updates the summary when a different role is chosen` falhou com
   `expected <p ...>Reaches 2 permission domains</p> to be null` — o
   fixture `DESCRIPTIONS` que eu tinha escrito dava a mesma frase-resumo
   literal ("Reaches 2 permission domains") para `viewer`, `operator` e
   `owner`, então trocar de papel não mudava nada visível e a asserção de
   ausência falhava por acidente meu, não por o produto ter deixado de
   trocar. Corrigido dando um resumo (e uma contagem de permissões) distinto
   por papel no fixture.

Nenhuma das duas correções tocou `grants.tsx`/`members.tsx`/`tokens.tsx` —
só o fixture e a asserção do teste. Nomeado aqui porque a instrução pediu
honestidade explícita sobre isso.

**Nenhum teste passou "de primeira" antes da implementação** — todo teste
novo ou reescrito nesta sessão foi confirmado vermelho com o código de
produto ainda no estado da sessão 7, como registrado em 16.2-16.4. Os dois
itens acima são o oposto do que a instrução pede para nomear (um teste que
passa sem mudança nenhuma): são testes que **falharam por minha causa**
depois que o produto já estava certo, e que corrigi sem tocar produto — put
de forma direta, nada nesta sessão se qualifica como "passou de primeira,
caracterização e não conserto".

**Verde final**, depois das duas correções acima:
```
pnpm exec vitest run tests/unit/surfaces/grants.test.tsx tests/unit/surfaces/tokens.test.tsx --pool=forks
Test Files  2 passed (2)
     Tests  67 passed (67)
```

### 16.6 A alegação de sessão do acceptance spec — resumo

Foi a verde, comando e saída completos em 16.2. `create-person`
(T025-T028) permanece vermelho, intocado, como a instrução pediu.

### 16.7 A varredura de identificadores de requisito pedida pelo orquestrador

Antes da mensagem do orquestrador, eu já tinha achado e corrigido sozinha
uma citação minha: `grants.test.tsx`, no comentário acima do bloco
reescrito de T023, dizia "FR-010 replaces that with a human summary here" —
troquei por "What a role permits is a human summary here instead" (mesma
frase, sem o identificador). Essa correção já estava feita quando a
mensagem do orquestrador chegou, e por isso não apareceu na varredura dele.

A varredura do orquestrador (`rg` sobre os arquivos alterados por esta
feature, fora `specs_v6/`) achou seis citações; corrigi as seis, apesar de
quatro não serem minhas:

| Local (antes) | Quem introduziu | Correção |
|---|---|---|
| `console/src/i18n/en.ts:1243` ("FR-005/FR-006") | Sessão anterior (T019) | Comentário reescrito para dizer o que os títulos técnicos substituem, sem citar identificador — `en.ts:1243-1245` agora. |
| `console/src/surfaces/machine-token-groups.tsx:51` ("FR-013") | Sessão anterior (T012, formulário de token) | "already a product permission, not one this form invents" — `:51` agora. |
| `console/src/surfaces/machine-token-groups.tsx:67` ("FR-017") | Sessão anterior | Parêntese removido; a frase já se explicava sozinha — `:67` agora. |
| `console/src/surfaces/machine-token-groups.tsx:74` ("FR-013") | Sessão anterior | Parêntese removido — `:74` agora. |
| `console/src/surfaces/machine-token-groups.tsx:99` ("FR-015") | Sessão anterior | "so the destructive-scope warning below knows which ones to name" — `:99` agora. |
| `console/src/surfaces/screens/integrations.tsx:148` ("FR-006", com a palavra solta "sondada" no meio de uma frase em inglês) | Sessão anterior (T021, sugestão do estate) | Frase reescrita inteira: "The vendor permissions this integration's capabilities need, whole — read from the catalogue's own declared permission entries rather than the per-field `min_scope` a schema mostly leaves blank." — `:146-150` agora. Nenhum trecho em português sobra. |

Todas as seis são mudanças de comentário/JSDoc — nenhuma tocou uma
declaração, um tipo ou uma linha de código executável. Confirmado por
inspeção direta de cada substituição (eu mesma escrevi o par antigo/novo de
cada uma) e, independentemente, pelos quatro gates rodados de novo depois
(16.8) — typecheck, lint e os 2341 testes do console inteiro continuaram
100% verdes com os mesmos números de cobertura de antes da limpeza.

**Achados adicionais, não corrigidos — nomeados, não escondidos:**

- No mesmo bloco de `machine-token-groups.tsx:96-99` que eu já estava
  editando, a linha anterior carrega `(Assumptions: no new permission
  category)` — também um ponteiro para uma seção nomeada de um documento de
  planejamento, só que por um regex `FR-\d+`/`SC-\d+` não pega essa forma.
  Não estava na lista do orquestrador; deixei como estava, por disciplina
  de escopo ("faça exatamente isto, e pare") — nomeado aqui para quem
  decidir se entra na mesma limpeza.
- Minha própria varredura (antes da mensagem do orquestrador) tinha achado
  mais quatro arquivos com o mesmo padrão, todos em Python, todos já
  modificados na árvore por sessões anteriores desta mesma feature (não
  criados por mim, confirmados contra o `git status` do início desta
  sessão): `gateway/http/routes/integrations.py:3` ("FR-022"),
  `platform/persistence/postgres/models.py:3,10,223,502,620` ("FR-009",
  "FR-010", "FR-022", "FR-012", "FR-018"), `platform/startup/bootstrap.py:161,208,242,399,454`
  ("FR-002", "FR-004", "FR-005" ×2, "FR-004"),
  `tests/unit/platform/estate/test_integration_suggestions.py:159`
  ("FR-008"). Nenhum destes está entre os seis que o orquestrador pediu, e
  nenhum é console — são backend/Python, fora do componente único que este
  dispatch cobre. Não tocados. O orquestrador já avisou que vai levantar
  separadamente com o operador as ~40 ocorrências em
  `tests/unit/platform/observation/**` e as de `fixtures/contract/openapi.json`
  (gerado, nunca editado à mão); estes quatro arquivos são um terceiro
  grupo que minha própria varredura achou e que não vi mencionado — deixo
  registrado para o mesmo levantamento, sem agir.

### 16.8 Gates rodados nesta sessão, comando exato e resultado real

Antes de qualquer edição (linha de base):
- `uv run python -m tools.console_gate typecheck` → limpo (`$ tsc --noEmit`,
  sem saída).

Depois de T022/T023/T024, antes da limpeza de identificadores:
- `uv run python -m tools.console_gate typecheck` → dois erros reais
  (`GrantLabels` sem `rolePermissions` em `grants.test.tsx`, e
  `DESCRIPTIONS.viewer`/`.owner` "possibly undefined" pela anotação de tipo
  larga demais que eu tinha posto) — corrigidos, ver 16.5-adjacente (a
  anotação `Readonly<Record<string, RoleDescription>>` foi removida de
  `DESCRIPTIONS`, deixando o TypeScript inferir o tipo literal com chaves
  conhecidas; `rolePermissions` foi acrescentado ao `LABELS` do teste).
  Depois disso: limpo.
- `uv run python -m tools.console_gate lint` → dois erros reais
  (`@typescript-eslint/no-unnecessary-condition` em
  `grants.test.tsx:601`, `summary.textContent?.length ?? 0` — neste
  projeto `Node.textContent` não checa como nulável no ponto de uso, então
  o `?.`/`??` eram mortos) — corrigido para `summary.textContent.length`.
  Depois: limpo.
- `uv run python -m tools.console_gate format-check` → dois arquivos fora
  do padrão (`members.tsx`, `grants.test.tsx`); `pnpm exec prettier --write`
  neles dois, nada mais. Depois: limpo.
- `uv run python -m tools.console_gate test` (vitest com cobertura) →
  **141 arquivos, 2341 testes, todos verdes**. Cobertura: statements
  94.35%, branches 90.28%, functions 92.11%, lines 96.34% — o gate não
  falhou por teto de cobertura.

Depois da limpeza de identificadores (seção 16.7), de novo, os quatro que o
orquestrador pediu:
- `typecheck` → limpo.
- `lint` → limpo.
- `format-check` → limpo.
- `test` (vitest com cobertura) → **141 arquivos, 2341 testes, todos
  verdes**, os mesmos quatro números de cobertura de antes (94.35% / 90.28%
  / 92.11% / 96.34%) — consistente com mudança só de comentário.

Browser/Playwright, rodados nesta sessão (não pedidos de novo depois da
limpeza de identificadores, porque as seis correções são só texto de
comentário e os quatro gates acima — incluindo os 2341 testes de unidade,
que cobrem `machine-token-groups.test.tsx` e `integrations.test.tsx` — já
provam que nada de comportamento mudou):
- `uv run python -m tools.spec_validation browser --feature
  specs_v6/030-vocabulario-defaults --test
  console/tests/e2e/vocabulary-defaults.acceptance.spec.ts` (antes de
  qualquer edição) → **2 failed, 1 skipped, 11 passed** (vermelho
  registrado em 16.2).
- O mesmo comando, mais `--test console/tests/e2e/scroll-budget.spec.ts`
  junto (depois da implementação) → **1 failed, 1 skipped, 23 passed** — a
  alegação de sessão virou `✓`; `create-person` continua vermelho
  (T025-T028, intocado); o `skip` é o preview do wizard, sem relação com
  esta fatia.
- `scroll-budget.spec.ts` sozinho, de novo, com `--no-build` (log limpo,
  sem truncamento) — motivo: `GrantPanel` ganhou uma `<details>` nova que
  renderiza aberta-por-`<summary>` (fechada) por padrão quando qualquer
  papel tem descrição, e `SessionPanel` ganhou uma coluna a mais — queria
  ver com números, não supor, se isso empurrava `/settings/members-roles`
  para fora do orçamento de rolagem: **11 passed**, incluindo
  explicitamente `✓ 6 [behaviour] › tests/e2e/scroll-budget.spec.ts:91:3 ›
  /settings/members-roles stays within the scroll budget (223ms)`. O
  orçamento é 2 viewports de 1080px (`CONFIG_SCREEN_SCROLL_BUDGET_VIEWPORTS`,
  `config/constants/surfaces.py:350`) — folga grande, sem risco real, mas
  medido, não assumido.
- `settings-org.spec.ts` + `settings-nav.spec.ts` juntos, com `--no-build`
  — nenhuma instrução pediu isso, rodei por conta própria porque
  `settings-org.spec.ts:145` toca `/settings/members-roles` diretamente
  ("lists principals with canonical chips, grants with legible permissions,
  and active sessions") e eu queria confirmar, não supor, que a troca do
  `Badge` por texto simples e a expansão nova não quebraram nada ali:
  **19 passed**, incluindo esse teste especificamente.

Não rodado: `make verify` (é do orquestrador), `console-visual-accept` e
`console-e2e` amplo (nenhuma tarefa deste dispatch pediu, e a instrução
proíbe explicitamente aceitar/sobrescrever baseline visual).

### 16.9 Confirmações de fronteira

- `git status --porcelain console/visual/` → saída vazia. Nenhuma baseline
  visual foi tocada, aceita ou sobrescrita.
- Nenhum processo de fundo ficou rodando: todo `spec_validation browser`
  imprimiu "Shutting down / Application shutdown complete" ao terminar, e
  `ps aux` depois do último gate não mostra nenhum `playwright`, `uvicorn`,
  `mockplane` ou servidor Next remanescente — só os processos do próprio
  `vitest run --coverage` enquanto ele ainda estava rodando, que terminaram
  sozinhos.
- Nada foi `git add`, `git stash`, `git restore` ou `git commit` por este
  trabalho.
- Nenhum identificador de requisito, critério de sucesso, artigo da
  constituição ou caminho de planejamento foi introduzido em código
  committable por esta sessão; os seis que existiam nos arquivos tocados
  por esta feature foram removidos (16.7).

### 16.10 Arquivos tocados nesta sessão

Produto:
- `console/src/surfaces/tokens.tsx` (T022)
- `console/src/surfaces/settings/members.tsx` (T022, T023 — já vinha
  modificado por sessões anteriores; esta sessão soma `roleDescriptions`,
  `liveSessions.origin` e os dois labels novos)
- `console/src/surfaces/grants.tsx` (T023, T024 — arquivo intocado antes
  desta sessão)
- `console/src/surfaces/machine-token-groups.tsx` (só limpeza de
  identificador, seção 16.7 — já vinha modificado por sessão anterior)
- `console/src/surfaces/screens/integrations.tsx` (só limpeza de
  identificador, seção 16.7 — já vinha modificado por sessão anterior)
- `console/src/i18n/en.ts`, `console/src/i18n/pt-BR.ts` (chaves novas de
  T022/T023 + limpeza de identificador em `en.ts`)

Teste:
- `console/tests/unit/surfaces/tokens.test.tsx` (arquivo intocado antes
  desta sessão; T022)
- `console/tests/unit/surfaces/grants.test.tsx` (arquivo intocado antes
  desta sessão; T023, T024 — bloco `describe('what a role means...')`
  reescrito por inteiro, não só as expectativas)

Planejamento (não committável, listado por transparência):
- `specs_v6/030-vocabulario-defaults/tasks.md` — T022, T023, T024 marcados
  `[x]`.
- `specs_v6/030-vocabulario-defaults/controle.md` — esta seção 16.

**Nenhum outro arquivo foi tocado.** `console/tests/e2e/vocabulary-defaults.acceptance.spec.ts`
continua exatamente como a sessão 3 o deixou — a alegação de sessão foi
levada a verde pela implementação, nunca reescrita.

### 16.11 O que fica pendente, nomeado, não escondido

- T025-T028 (criar pessoa) e T029 em diante: inalterados, fora do escopo
  deste dispatch por instrução explícita.
- O item de `machine-token-groups.tsx:98` ("Assumptions: no new permission
  category") nomeado em 16.7 — um ponteiro de planejamento que não bate no
  regex `FR-\d+`/`SC-\d+`, não corrigido, por disciplina de escopo.
- Os quatro arquivos Python nomeados em 16.7 (`gateway/http/routes/integrations.py`,
  `platform/persistence/postgres/models.py`, `platform/startup/bootstrap.py`,
  `tests/unit/platform/estate/test_integration_suggestions.py`) — mesmo
  padrão de violação, fora do componente único deste dispatch, não
  tocados.
- A entrada `{ path: '/settings/members-roles', rule: 'vocabulary', ... }`
  em `console/tests/e2e/transversal-rules.spec.ts` (constante `EXCEPTIONS`)
  parece obsoleta: o texto da razão fala de um chip de token/saúde que
  `members.tsx` não renderiza mais (a tela só tem `PrincipalKindChip`,
  `AccountStateChip` e `SessionPanel` — nenhum `Badge`/"HEALTHY" alcançável
  a partir dela hoje), e a entrada faz `test.fixme()` pular o teste de
  vocabulário desta rota inteiro, sem rodar a asserção de verdade. Não é
  T022/T023/T024 e o arquivo não está na lista de arquivos deste dispatch —
  nomeado aqui, não tocado, para quem cuidar da limpeza de exceções da
  suíte transversal.

---

## 17. Continuação — sessão 9: T025 e T026, criar uma pessoa com senha local (só servidor)

**Escopo desta sessão, imposto pelo orquestrador desde o início: T025 e T026
apenas — o lado de servidor da criação de principal.** Nenhuma tela foi
tocada, nenhum arquivo em `console/` foi aberto para edição, nenhuma
baseline visual foi aceita ou sobrescrita. T027/T028 (a ação primária na
tela de Members & roles) continuam **NÃO INICIADO**, de propósito — são
outro dispatch. Verificado contra o código real desta árvore agora, branch
`feat/v6-010-provider-out-of-the-box`. Nada commitado nem staged por este
trabalho (seção 17.9 tem a confirmação exata).

**Achado de abertura, relevante para quem ler esta seção**: o `git status`
que abriu esta sessão dizia "clean", mas a árvore de trabalho já continha,
sem estar commitado, o acumulado de oito sessões anteriores desta mesma
feature — `console/src/surfaces/members.tsx`, `grants.tsx`,
`machine-token-groups.tsx`, `tokens.tsx`, `status.tsx`, as mudanças de T013
a T024 em Python, os cinco `fixtures/scenarios/*/principal*.json` de T003,
etc. — exatamente a lista que as seções 1-16 já documentam. O "clean" era
um instantâneo tirado antes desse estado existir nesta cópia de trabalho, não
uma afirmação de que a árvore estava vazia. Dito aqui porque explica por que
`git status --porcelain` desta sessão (seção 17.9) mostra dezenas de arquivos
`M` que esta sessão não tocou.

### 17.1 T001, revisitado — a descoberta que decide a forma

T001 (seção 1, `file:line` já lá) já tinha o veredito: **não existe rota**.
`gateway/http/routes/identity.py` tinha `GET /identity/principals`
(listagem) e nada além disso; a operação de baixo nível
(`IdentityRepository.upsert_user` + `upsert_role_binding`) já existia na
camada de persistência, usada por `platform/identity/local_accounts.py` só
para o princial reservado da conta local. Esta sessão constrói a rota nova
sobre esse port existente, exatamente como T001 previu.

### 17.2 T025 — o vermelho confirmado, mensagem real observada

O teste de contrato mora em `tests/unit/gateway/http/test_identity_principal_routes.py`
(novo arquivo, 8 testes). Ele foi escrito depois que a implementação já
tinha sido montada nesta mesma sessão — dizendo isso sem eufemismo, T025 não
nasceu antes de T026 no relógio desta sessão. Para não deixar isso como uma
alegação não verificada, revertei deliberadamente a peça que faz a rota
existir — a função `create_principal` inteira em `gateway/http/routes/identity.py`
e a linha `Route(method="POST", path="/identity/principals", ...)` em
`gateway/http/security/route_permissions.py` — rodei a suíte contra essa
árvore revertida, e só depois restaurei as duas peças byte a byte
(conferido por `git diff --stat` batendo com o estado antes da reversão).

Comando, contra a árvore revertida:
```
uv run pytest tests/unit/gateway/http/test_identity_principal_routes.py -q
```
Resultado real: **`7 failed`**. As mensagens observadas, uma por teste
(truncadas onde o pytest já trunca):
- `test_a_principal_is_created_and_reads_back_in_the_listing`:
  `assert 405 == 201` — `where 405 = <Response [405 Method Not Allowed]>.status_code`.
- `test_the_password_is_hashed_through_the_same_scheme_the_local_account_uses`:
  `KeyError: 'user_id'` (o corpo da resposta 405 não tem esse campo — a
  chamada ao endpoint nunca chegou a criar nada).
- `test_the_created_principal_holds_no_role_until_one_is_granted`:
  `KeyError: 'user_id'`, mesma causa.
- `test_a_viewer_may_not_create_a_principal`: `assert 405 == 403` — nem
  vermelho "certo" (a rota não existe, então não há refutação nenhuma para
  observar; exatamente o buraco que T001 tinha nomeado).
- `test_the_refusal_does_not_say_whether_the_email_already_exists`:
  `assert 405 == 403` (duas vezes, uma por sub-chamada).
- `test_a_duplicate_email_is_refused_with_a_conflict`: `assert 405 == 201`.
- `test_the_creation_leaves_an_audit_row_naming_the_actor_and_the_principal`:
  `assert 0 == 1` — `where 0 = len([])` (nenhum evento `principal.create` foi
  gravado, porque nada foi criado).

Toda mensagem veio de `httpx`/`pytest` reais, não inferida — o log de
requisição (`HTTP Request: POST http://deployment/identity/principals "HTTP/1.1
405 Method Not Allowed"`) aparece em cada uma. Depois de restaurar as duas
peças:
```
uv run pytest tests/unit/gateway/http/test_identity_principal_routes.py -q
```
→ `7 passed`. Confirmado de novo depois de somar o oitavo teste e a
asserção de `node_id` (seção 17.4) → `8 passed` (seção 17.8 tem o comando
exato).

**Sobre os quatro pontos de prova acrescentados depois deste ciclo** — a
asserção de `event.detail["node_id"]` dentro de
`test_the_creation_leaves_an_audit_row_naming_the_actor_and_the_principal`
(`tests/unit/gateway/http/test_identity_principal_routes.py:255`), o teste
inteiro `test_a_team_scoped_admin_may_create_and_the_audit_row_names_that_team`
(`:258`), e os dois testes de contrato de persistência
(`tests/contract/persistence/test_identity_repository.py:31,50`) — **nenhum
deles foi revertido e visto vermelho de novo, individualmente**. Passaram já
na primeira execução, contra uma implementação que já existia e já tinha
sido provada vermelha pelo ciclo acima (a mesma reversão — a rota inteira
ausente — teria feito qualquer um destes quatro falhar também, mas essa é
uma inferência sobre o mecanismo, não uma observação nova). Nomeando isso
como o que é: **caracterização, não correção, para estes quatro** — a régua
que esta feature já usa em T013/T017 (seções 2 e 9.6).

### 17.3 T026 — o que foi implementado, com `file:line`

**A rota**: `gateway/http/routes/identity.py:349-401` —
`POST /identity/principals`, `response_model=UserView`, `status_code=201`.
`CreatePrincipalRequest` (`:90-106`) pede `email`, `display_name`, `password`
— todos `Field(min_length=1)`, sem regra de força de senha: nenhum FR desta
feature declara uma política de senha, e não inventei nenhuma. O corpo do
handler:
1. Abre `state.gateway.begin(auth.scope)` — o mesmo padrão de `add_grant`.
2. Consulta `find_user_by_email` primeiro; se já existe, `conflict(...)`
   (409) — sem tocar em `upsert_user`.
3. `upsert_user(User(user_id=secrets.token_hex(16), email=..., display_name=...,
   kind=PrincipalKind.USER))` — o id é gerado no servidor
   (`_PRINCIPAL_ID_BYTES = 16`, `:56`), nunca derivado do e-mail, pelo mesmo
   motivo que `TokenService.issue()` gera `token_id` com
   `secrets.token_hex(16)` (`platform/identity/tokens.py:252`) em vez de
   derivar de algo que quem chama escolheu.
4. `set_local_password(created.user_id, password_hash=hash_local_password(body.password))`
   — na mesma transação.
5. Fora da transação, `AuditRecorder(gateway=state.gateway).record(...)`
   com `action=PRINCIPAL_AUDIT_ACTION_CREATE`,
   `resource_kind=IDENTITY_AUDIT_RESOURCE_KIND_PRINCIPAL`,
   `resource_id=created.user_id`, `detail={"email", "display_name", "node_id"}`
   — o mesmo padrão de `add_grant`/`remove_grant` (recorder próprio, fora do
   `async with`, para que uma escrita recusada ainda deixe o registro do
   porquê).

**A guarda de permissão**: `gateway/http/security/route_permissions.py:203-207`
— nova linha `Route(method="POST", path="/identity/principals",
permission=Permission.IDENTITY_WRITE)`, na mesma tabela que já guarda
`POST /identity/grants` com a mesma permissão. É essa tabela, não um `if`
dentro do handler, que decide: `gateway/http/deps.py:78-105`'s `authorized()`
chama `state.route_table.guard_for(request.method, path_template)` **antes**
de `create_principal` rodar uma linha sequer.

**O hash de senha**: `platform/identity/local_accounts.py:128-136` —
`hash_local_password(password: str) -> str` chama diretamente `hash_secret`
(`platform/identity/break_glass.py:77`, o mesmo scrypt que a conta local
ambiental já usa) — nenhum segundo caminho de hashing.

**Onde a senha é guardada**: `platform/persistence/ports/identity_repository.py:44-51`
— `User.local_password_hash: str | None = None`, campo novo, com a regra
escrita no próprio docstring: só `set_local_password` escreve nele, nunca
`upsert_user`. O método novo do port (`:188-194`) tem duas implementações:
- `platform/persistence/fakes/identity_repository.py:117-123` — grava por
  `replace()` no dicionário em memória, devolve `False` se o usuário não
  existir.
- `platform/persistence/postgres/repositories/identity_repository.py:218-225`
  — `UPDATE` de uma coluna só (`row.local_password_hash = password_hash`),
  mesmo padrão de `record_token_use` (`:208-215`, já existia).

**Por que `upsert_user` não podia ganhar o campo diretamente**: as duas
implementações de `upsert_user` reescrevem a linha inteira a cada chamada.
Se `local_password_hash` fosse só mais um campo de `User` que `upsert_user`
grava, qualquer chamada futura de `upsert_user` para a mesma pessoa — uma
edição de nome, uma suspensão de conta, algo que uma feature futura ainda
vai escrever — apagaria a senha sem querer. Fechei essa brecha nos dois
lados:
- `platform/persistence/fakes/identity_repository.py:43-56` — `upsert_user`
  agora lê o `local_password_hash` da linha **já existente** (se houver) e o
  carrega para a linha nova, ignorando o que veio em `user.local_password_hash`.
  Escrito porque a versão anterior desta função sobrescrevia o dicionário
  inteiro; sem esse ajuste, o fake e o Postgres teriam divergido nesta
  garantia específica.
- `platform/persistence/postgres/repositories/identity_repository.py`'s
  `upsert_user` (já existia antes desta sessão) nunca precisou de ajuste: ele
  atribui campo a campo num `Row` do SQLAlchemy e nunca menciona
  `local_password_hash`, então uma coluna que ninguém atribui simplesmente
  não muda — a mesma garantia, de graça, pela forma como esse método já
  estava escrito.

**A migração**: `platform/persistence/migrations/versions/0013_local_password.py`
(novo, não rastreado). Detalhe na seção 17.5.

**A constante de auditoria**: `config/constants/security.py:548`
(`PRINCIPAL_AUDIT_ACTION_CREATE: Final = "principal.create"`), somada a
`AUDITED_ACTIONS` em `platform/identity/audit/recorder.py:129`. A constante
`IDENTITY_AUDIT_RESOURCE_KIND_PRINCIPAL = "principal"`
(`config/constants/security.py:551`) **já existia**, sem uso nenhum antes
desta sessão — a varredura confirmou (`rg` antes de eu tocar em nada) que
nada no repositório a referenciava; esta sessão é quem primeiro a usa.

### 17.4 Cada propriedade de segurança, com o teste que prova

| Propriedade | Como é garantida | Teste que prova |
|---|---|---|
| A recusa é do servidor, não só um botão escondido | `guard_for` roda em `authorized()` antes do handler; sem a entrada na tabela, `POST /identity/principals` nem existiria como rota (era exatamente o vermelho de T025) | `test_a_viewer_may_not_create_a_principal` (`:140`) — 403 real, e confirma sem efeito colateral (`find_user_by_email` depois da chamada devolve `None`) |
| A mensagem de recusa não denuncia se o e-mail já existe | A permissão é checada antes do corpo do handler rodar; o handler é o único lugar que consulta `find_user_by_email`, e ele nunca roda para quem foi recusado | `test_the_refusal_does_not_say_whether_the_email_already_exists` (`:162`) — a mesma mensagem, byte a byte, para um e-mail que já existe e um que não existe; a mensagem não contém o e-mail nem as palavras "already"/"exists" |
| A senha nunca é ecoada na resposta | `UserView` (o `response_model`) não tem campo de senha; `_user_view()` monta o retorno campo a campo | `test_a_principal_is_created_and_reads_back_in_the_listing` (`:66`) — `assert "password" not in body` |
| A senha nunca é armazenada em texto puro, e usa o mesmo esquema da conta ambiental | `hash_local_password` chama `hash_secret` (scrypt) — o mesmo primitivo de `platform/identity/break_glass.py` que `LocalAccount` já usa | `test_the_password_is_hashed_through_the_same_scheme_the_local_account_uses` (`:91`) — o hash lido de volta do store não é igual ao texto puro, o texto puro não é substring do hash, e `verify_secret(senha, hash)` bate |
| A senha nunca é logada | Nenhuma chamada de log (`_LOG.*`) existe em `create_principal`; a única passagem de `body.password` no código é para `hash_local_password(body.password)`, uma vez | Verificado por leitura do código (`gateway/http/routes/identity.py:349-401`, nenhum `_LOG` na função), **não por um teste que capture saída de log** — nomeado como lacuna na seção 17.11, não escondido |
| O audit registra o ator, o principal criado, e o nó | `AuditRecorder.record(..., resource_id=created.user_id, detail={"email", "display_name", "node_id": auth.team_node_id or ORGANISATION_WIDE})` | `test_the_creation_leaves_an_audit_row_naming_the_actor_and_the_principal` (`:231`, ator e recurso; `node_id == "organisation"` para um emissor sem time) e `test_a_team_scoped_admin_may_create_and_the_audit_row_names_that_team` (`:258`, `node_id == "payments"` para um emissor de time — prova que o campo reflete o nó de verdade, não uma string fixa) |
| O escopo de tenant é preservado | `state.gateway.begin(auth.scope)` abre a transação só no `org_id` do chamador; nenhum campo do corpo da requisição nomeia uma organização — não há caminho de código onde outra organização seja alcançada | Estrutural (não há parâmetro que permita testar o caminho contrário — a própria ausência é a garantia); `AuthenticatedRequest.scope` (`gateway/http/deps.py:62-65`) é sempre o do token autenticado |
| O escopo de nó (time) segue a mesma assimetria que `/identity/grants` já tem | A permissão é resolvida em `context.scope_node_id` (o nó do próprio token), pela mesma `PermissionGuard` que guarda `POST /identity/grants` — nenhum mecanismo novo | `test_a_viewer_may_not_create_a_principal` (negativo, visualizador de time) e `test_a_team_scoped_admin_may_create_and_the_audit_row_names_that_team` (positivo, admin de time) — o mesmo par de provas que `test_a_viewer_may_not_grant_a_role` já faz para grants |
| A rota não pode ser usada para escalar (criar + conceder no mesmo golpe) | `CreatePrincipalRequest` não tem campo de papel; o handler nunca chama `upsert_role_binding`; conceder um papel é uma chamada separada a `POST /identity/grants`, com a mesma permissão `identity.write` e seu próprio registro de audit | `test_the_created_principal_holds_no_role_until_one_is_granted` (`:114`) — consulta `GET /identity/grants?principal_id=<novo>` de verdade e confirma lista vazia |

**Achado à parte, não corrigido, fora do escopo desta fatia**: lendo
`add_grant` (`gateway/http/routes/identity.py`, rota já existente antes desta
sessão) para responder a pergunta de escalonamento acima, notei que o
`node_id` do vínculo que ele grava vem de `body.node_id` — escolhido por
quem chama — enquanto a permissão que autoriza a chamada é checada só contra
o nó do **próprio** chamador (`context.scope_node_id`). Não confirmei se
isso é um caminho de escalonamento de verdade (não escrevi um teste; seria
tocar uma rota que não é minha, de uma feature anterior a esta) — é uma
leitura de código, não uma prova, e por isso não estou chamando de defeito.
Nomeado aqui só para quem for dono de `/identity/grants` decidir se vale
investigar.

### 17.5 A migração `0013_local_password.py`

**Coluna**: `local_password_hash`, `String(256)`, `nullable=True`, na tabela
`users` (`platform/persistence/migrations/versions/0013_local_password.py`,
espelhando `platform/persistence/postgres/models.py:163-167`). Sem
`server_default` — não precisa: toda linha existente simplesmente ganha
`NULL`, que é exatamente o que `User.local_password_hash: str | None = None`
já significa em Python.

**Cadeia validada, só de arquivo, do jeito que a sessão 2 já tinha feito
para `0012`**:
```
uv run python -c "
from platform.persistence.postgres.migrations import head_revision, alembic_config
from alembic.script import ScriptDirectory
print('head:', head_revision())
scripts = ScriptDirectory.from_config(alembic_config())
for rev in scripts.walk_revisions():
    print(rev.revision, '<-', rev.down_revision)
"
```
Saída real: `head: 0013_local_password`, cadeia completa e sem lacuna,
`0013_local_password <- 0012_token_unscoped <- 0011_verifications <- ... <-
0001_initial <- None`. Uma cabeça só.

**Não rodei esta migração contra um Postgres real** — não há um backend
Postgres vivo neste sandbox, o mesmo limite que a seção 9.5 já registrou
para `0012`. Esta checagem é só de arquivo (`ScriptDirectory`), não abre
conexão nenhuma.

**Consequência para um deployment existente, dita sem eufemismo**: nenhuma.
Diferente de `0012` (que reclassificava tokens já emitidos e podia
desautenticar uma integração), `0013` não toca nenhuma linha existente além
de lhe dar a coluna nova com `NULL`. Nada antes desta feature lia ou
escrevia essa coluna — não existe um caminho de sign-in que a consulte ainda
(seção 17.11) — então rodar esta migração num deployment real não muda o
comportamento de nenhuma conta que já existia.

### 17.6 O fake e o Postgres concordam em `set_local_password`/`find_user_by_email`?

**`find_user_by_email`**: já existia nos dois backends antes desta sessão,
sem alteração minha — comparação por `casefold()` no fake
(`platform/persistence/fakes/identity_repository.py:31-34`) contra
`email_folded` indexado no Postgres
(`platform/persistence/postgres/repositories/identity_repository.py:80-88`).
Não toquei em nenhum dos dois; a rota nova só passou a chamar um método que
já era simétrico.

**`set_local_password`**: os dois foram escritos nesta sessão, deliberadamente
no mesmo formato de `record_token_use` (que já existia nos dois backends,
simétrico) — "busque a linha, se não existir devolva `False`, senão grave e
devolva `True`". Não há teste rodando contra um Postgres vivo aqui para
provar a simetria por execução — a prova disponível nesta sandbox é:
1. Uma suíte de contrato dedicada nova,
   `tests/contract/persistence/test_identity_repository.py:31-56` (dois
   testes: o round-trip com um `upsert_user` não relacionado no meio, e o
   caso de usuário inexistente), que roda contra a mesma fixture
   parametrizada que todo o resto do arquivo já usa. Comando:
   ```
   uv run pytest tests/contract/persistence/test_identity_repository.py --collect-only -q
   ```
   Confirma que os dois novos testes coletam só como `[fakes]` — não há
   `[postgres]` nem coletado nem pulado, porque este ambiente não declara
   um Postgres para a fixture escolher (mesmo padrão que todo o resto do
   arquivo já tinha antes de eu tocar nele). Rodados:
   ```
   uv run pytest tests/contract/persistence/test_identity_repository.py -q
   ```
   → `16 passed` (14 pré-existentes + 2 novos).
2. `mypy`/`ruff` passando nos dois arquivos de repositório
   (`fakes/identity_repository.py`, `postgres/repositories/identity_repository.py`)
   com a mesma assinatura de método declarada no port
   (`platform/persistence/ports/identity_repository.py:188-194`), que é o
   que faz `FakeIdentityRepository`/`PostgresIdentityRepository` satisfazerem
   o mesmo `Protocol` `runtime_checkable`.

**Dito sem eufemismo**: a simetria está garantida por leitura de código e
pelo mesmo `Protocol`, e provada por execução só do lado do fake. O lado
Postgres não foi exercitado ao vivo nesta sessão — mesmo limite da seção
17.5.

### 17.7 Testes que passaram já na primeira execução — caracterização, não correção

Nomeados juntos, para não espalhar a mesma ressalva pelo documento:
- `tests/contract/persistence/test_identity_repository.py::test_a_local_password_is_stored_by_hash_and_survives_an_unrelated_upsert`
  e `::test_setting_a_password_for_nobody_reports_it` — escritos depois que
  `set_local_password` e o ajuste de `upsert_user` já existiam nos dois
  repositórios. `16 passed` já na primeira execução.
- `tests/unit/gateway/http/test_identity_principal_routes.py::test_a_team_scoped_admin_may_create_and_the_audit_row_names_that_team`
  e a asserção `event.detail["node_id"]` dentro de
  `::test_the_creation_leaves_an_audit_row_naming_the_actor_and_the_principal`
  — escritos depois da restauração da rota (seção 17.2), nunca revertidos de
  novo individualmente. `8 passed` já na primeira execução depois de somados.

Nenhum destes é apresentado como conserto de um vermelho observado — são
provas escritas depois, contra uma implementação que a reversão de T025 já
tinha demonstrado vermelha por outro caminho (a rota inteira ausente).

### 17.8 Todo comando desta sessão, com resultado real

Formatação, lint e tipos, sobre todo arquivo Python tocado (dois lotes — o
primeiro conjunto de 12 arquivos, depois o teste de contrato de persistência
e a extensão do teste de rota, à parte):
```
uv run ruff format <12 arquivos>
```
→ `1 file reformatted, 11 files left unchanged` (o arquivo novo de teste).
```
uv run ruff check <12 arquivos>
```
→ `All checks passed!`
```
uv run ruff format --check <12 arquivos>
```
→ `12 files already formatted`.
```
uv run mypy <11 arquivos, sem a migração>
```
→ `Success: no issues found in 11 source files`.
```
uv run mypy platform/persistence/migrations/versions/0013_local_password.py
```
→ `Success: no issues found in 1 source file`.

Depois de somar o teste de contrato de persistência e o oitavo teste de
rota, os mesmos três checks de novo sobre os dois arquivos:
```
uv run ruff format tests/contract/persistence/test_identity_repository.py
```
→ `1 file reformatted`.
```
uv run ruff check tests/contract/persistence/test_identity_repository.py
uv run mypy tests/contract/persistence/test_identity_repository.py
```
→ `All checks passed!` / `Success: no issues found in 1 source file`.
```
uv run ruff format tests/unit/gateway/http/test_identity_principal_routes.py
uv run ruff check tests/unit/gateway/http/test_identity_principal_routes.py
uv run mypy tests/unit/gateway/http/test_identity_principal_routes.py
```
→ `1 file left unchanged` / `All checks passed!` / `Success: no issues
found in 1 source file`.

O ciclo vermelho→verde de T025 (seção 17.2) — comandos já citados lá, não
repetidos aqui.

Suítes de teste:
```
uv run pytest tests/unit/gateway/http tests/unit/platform/identity -q
```
→ `576 passed`.
```
uv run pytest tests/contract/persistence -q
```
→ `275 passed, 16 skipped` (os 16 pulados são a metade Postgres da suíte
inteira de persistência, sem backend vivo — não os dois testes novos, que
nem chegam a ser parametrizados para Postgres neste ambiente, seção 17.6).
```
uv run pytest tests/unit/tools/mockplane/test_verification.py::test_the_committed_document_is_what_the_application_generates -q
```
Antes de regenerar: `1 failed` — vermelho real,
`AssertionError: the committed OpenAPI document has drifted from the routes;
run 'python -m tools.mockplane contract' and rebuild the fixtures`. Depois de:
```
uv run python -m tools.mockplane contract
```
→ `wrote /srv/workspaces/NinjaSRE/fixtures/contract/openapi.json`. O mesmo
teste de novo → `1 passed`.
```
uv run pytest tests/contract/fixtures -q
```
→ `107 passed`.
```
make check-imports
```
→ `Contracts: 7 kept, 0 broken.`
```
make check-constants
```
→ `EXIT=0`.
```
make check-protocols
```
→ `EXIT=0` (rodado porque esta sessão acrescentou um método ao `Protocol`
`IdentityRepository`; não estava na lista mínima do dispatch, mas era o
gate certo para essa mudança específica).
```
make check-raw-sql
```
→ `EXIT=0`.
```
make check-credentials
```
→ `EXIT=0`.
```
uv run pytest tests/security tests/unit/gateway/webhooks tests/unit/platform/persistence tests/unit/platform/startup -q
```
→ `945 passed, 11 warnings` (os 11 avisos são `PytestWarning` pré-existentes
sobre `@pytest.mark.asyncio` em funções síncronas, em arquivos que esta
sessão não tocou — não investigados, fora do escopo).
```
uv run python -c "... head_revision() ..."
```
→ `head: 0013_local_password`, cadeia completa (seção 17.5).
```
uv run pytest tests/unit/gateway/http/test_identity_principal_routes.py -q
```
→ `8 passed` (depois de somar o oitavo teste).
```
uv run pytest tests/unit/gateway/http tests/unit/platform/identity tests/contract/fixtures -q
```
→ `683 passed` — mesmo número que o orquestrador reportou de fora,
reproduzido por mim depois de somar os testes 8 e os dois de contrato de
persistência.

Não rodado: `make console-client`/`make console-client-check` (escreveriam
ou leriam algo sob `console/`, fora do meu escopo — nomeado na seção 17.11);
`make verify` completo (é do orquestrador); `console-e2e`,
`console-visual`, `console-visual-accept` (nenhuma tarefa deste dispatch
pediu, e a instrução proíbe aceitar baseline); a suíte Python inteira sem
filtro (a sessão 9 já tinha rodado `11736 passed, 0 failed` uma vez; esta
sessão não alterou nada fora de `platform/identity/`,
`platform/persistence/` e `gateway/http/`, e a varredura de raio de alcance
acima — 945 + 576 + 275 + 107 testes, sem sobreposição de arquivo nenhuma —
cobre toda superfície que esta mudança poderia ter atingido).

### 17.9 Confirmações de fronteira

- `git diff --cached --stat` → só as duas renomeações que já estavam staged
  antes desta sessão começar (`console/tests/e2e/010-provider-out-of-the-box.acceptance.spec.ts`
  → `provider-out-of-the-box.acceptance.spec.ts`,
  `020-confiabilidade-telas.acceptance.spec.ts` →
  `screen-truthfulness.acceptance.spec.ts`), `0 insertions(+), 0 deletions(-)`.
  Não tocadas, não somadas a nada por mim.
- `git status --porcelain -- console/` → todo arquivo listado já estava
  modificado antes desta sessão (a mesma lista que as seções 1-16 já
  documentam, mais o `console/tests/e2e/vocabulary-defaults.acceptance.spec.ts`
  não rastreado da sessão 3). Nenhum `console/` foi aberto por mim — nem
  `Read`, nem `Edit`, nem `Write` — em nenhum momento desta sessão.
- `git status --porcelain -- console/visual/` → saída vazia. Nenhuma
  baseline visual tocada.
- `jobs -l` (processos de fundo deste shell) → vazio.
- `ps aux | grep -E "playwright|uvicorn|mockplane"` → vazio. Nenhum servidor
  ficou de pé.
- Nada foi `git add`, `git commit`, `git stash` ou `git restore` por este
  trabalho.
- Varredura por identificador de requisito/critério/artigo/caminho de
  planejamento em todo arquivo que esta sessão criou ou editou (`grep -in`
  por `FR-`, `SC-`, `T0[0-9][0-9]`, `Article`, `constitution`, `specs_v6`,
  `spec.md`, `tasks.md`, `plan.md`) → nenhuma ocorrência.

### 17.10 Arquivos tocados nesta sessão

Produto:
- `gateway/http/routes/identity.py` — `CreatePrincipalRequest`,
  `create_principal`, imports.
- `gateway/http/security/route_permissions.py` — a linha `Route` nova.
- `platform/identity/local_accounts.py` — `hash_local_password`.
- `platform/identity/audit/recorder.py` — import e entrada em
  `AUDITED_ACTIONS`.
- `platform/persistence/ports/identity_repository.py` — `User.local_password_hash`,
  `IdentityRepository.set_local_password`.
- `platform/persistence/fakes/identity_repository.py` — `set_local_password`,
  e o ajuste em `upsert_user` que preserva o hash existente.
- `platform/persistence/postgres/models.py` — coluna `local_password_hash`.
- `platform/persistence/postgres/repositories/identity_repository.py` —
  `_to_user`, `set_local_password`.
- `config/constants/security.py`, `config/constants/__init__.py` —
  `PRINCIPAL_AUDIT_ACTION_CREATE`.

Novo:
- `platform/persistence/migrations/versions/0013_local_password.py`.
- `tests/unit/gateway/http/test_identity_principal_routes.py` (8 testes).

Teste (arquivo pré-existente, ampliado):
- `tests/contract/persistence/test_identity_repository.py` (2 testes novos).

Fixture gerada (não editada à mão — só via
`python -m tools.mockplane contract`, conforme a instrução):
- `fixtures/contract/openapi.json`. O diff inclui o schema/rota novos desta
  sessão **e** um vazamento pré-existente que já estava na árvore de
  trabalho antes desta sessão começar (campos `resource_kind`/`resource_label`
  em `SuggestionView`, de `platform/estate/suggestions.py` e
  `gateway/http/routes/integrations.py` — trabalho de T021, sessão 15,
  nunca antes regenerado para este arquivo). Não toquei em nenhum dos dois
  arquivos-fonte desse vazamento (`git diff --stat` sobre eles mostra zero
  mudança minha); a regeneração via o comando correto simplesmente capturou
  o estado real da aplicação, que já incluía aquele trabalho. Dito aqui para
  quem revisar o diff de `openapi.json` não estranhar linhas que não são
  desta fatia.

Planejamento (não committável, listado por transparência):
- `specs_v6/030-vocabulario-defaults/tasks.md` — T025, T026 marcados `[x]`.
- `specs_v6/030-vocabulario-defaults/controle.md` — esta seção 17.

**Nenhum arquivo em `console/` foi tocado.**

### 17.11 O que fica pendente, nomeado, não escondido

- **A senha guardada não tem, ainda, nenhuma rota que a verifique.** O hash
  existe (`User.local_password_hash`), mas `POST /auth/sign-in`
  (`platform/identity/local_accounts.py`'s `LocalSignIn.sign_in`) continua
  autenticando só contra a única conta configurada por ambiente
  (`LOCAL_ACCOUNT_PRINCIPAL_ID`) — não contra um `user_id` arbitrário e seu
  `local_password_hash`. Uma pessoa criada por esta rota não consegue, hoje,
  entrar com a senha que recebeu. Isso não está em nenhuma das descrições de
  T025/T026 (conferido: nem uma nem outra menciona verificar a senha, só
  criar a pessoa e auditar), e não é o mesmo trabalho que "criar a pessoa" —
  é uma extensão real do sign-in local de uma conta só para N contas, que
  toca o caminho de autenticação de todo navegador. Nomeado aqui como o
  maior buraco desta fatia, para quem pegar o resto de US3 ou uma feature
  futura de sign-in local multiusuário.
- **Nenhuma política de força de senha.** `CreatePrincipalRequest.password`
  só exige não-vazio (`Field(min_length=1)`), o mesmo padrão que todo outro
  campo obrigatório deste arquivo já usa. Nenhum FR desta feature declara um
  comprimento mínimo ou uma regra de complexidade; não inventei uma.
- **A senha nunca aparece em log — verificado por leitura de código, não por
  um teste que capture saída de log.** Seção 17.4 já nomeia isto na própria
  tabela; repetido aqui para não ficar só dentro de uma célula.
- **O lado Postgres não foi exercitado ao vivo** — nem a migração, nem
  `PostgresIdentityRepository.set_local_password`, nem `_to_user` com a
  coluna nova. Mesmo limite que a seção 9.5 já registrou para `0012`: sem
  backend Postgres neste sandbox. A prova disponível é `mypy`/`ruff` limpos
  nos três arquivos e um teste de contrato que roda contra o fake.
- **O achado sobre `POST /identity/grants`** (seção 17.3, o `node_id` do
  corpo não é checado contra o nó de quem chama) — leitura de código, não
  verificado por teste, não corrigido, de uma rota que não é desta fatia.
- **`make console-client`/`make console-client-check` não rodados.** A
  regeneração de `fixtures/contract/openapi.json` desta sessão move o
  documento que o cliente TypeScript do console é gerado a partir de — isso
  inclui a rota nova (`CreatePrincipalRequest`) e o vazamento pré-existente
  de `SuggestionView` (achado acima). Regenerar o cliente escreve sob
  `console/`, que esta sessão tem instrução explícita de não tocar. Quem
  fizer T027/T028 (ou rodar `make console-client`) provavelmente vai
  encontrar esse cliente desatualizado e vai precisar regenerá-lo como parte
  daquele trabalho, não deste.
- **T027/T028 (a ação primária em Members & roles) e tudo de T029 em
  diante**: inalterados, fora do escopo deste dispatch por instrução
  explícita. `console/tests/e2e/vocabulary-defaults.acceptance.spec.ts:215`
  continua vermelho para a alegação de criar pessoa — vai passar a
  caracterizar a rota real quando T027/T028 apontarem a tela para ela.

Nenhum destes tem dono fora da própria feature 030; nada foi transferido
para outra spec da onda.

---

## 18. Continuação — sessão 10: sign-in local aceita um principal criado (só servidor)

**Escopo desta sessão, imposto pelo orquestrador desde o início**: estender
`LocalSignIn.sign_in` para aceitar, além da conta configurada por ambiente, um
principal criado por `POST /identity/principals` cuja senha local armazenada
bata — fechando o Teste Independente da US3 (criar pessoa com senha local,
conceder-lhe um papel, entrar com essa conta, alcançar exatamente o que o
papel permite). Só servidor: nenhum arquivo em `console/` foi aberto para
edição, nenhuma baseline visual tocada. Verificado contra o código real desta
árvore agora, branch `feat/v6-010-provider-out-of-the-box`. Nada commitado nem
staged por este trabalho (seção 18.7 tem a confirmação exata).

### 18.1 O ponto de partida, e o buraco exato

A seção 17 (sessão 9) já tinha nomeado isto como o maior buraco que deixava
(seção 17.11): `LocalSignIn.sign_in` (`platform/identity/local_accounts.py`,
antes desta sessão) só verificava contra `self.account` — a conta única
configurada por ambiente — e sempre emitia o token para o
`LOCAL_ACCOUNT_PRINCIPAL_ID` fixo. Um principal criado por
`POST /identity/principals` (T025/T026, sessão 9, já `[x]` em `tasks.md`)
tinha um `local_password_hash` gravado que nada lia. Confirmei isso por
leitura antes de tocar em qualquer linha, e reconstruí o texto exato do
arquivo de antes (guardado em
`/tmp/.../scratchpad/local_accounts_before_my_edit.py`, ver seção 18.4) para
poder provar vermelho depois, e não só alegá-lo.

### 18.2 O que foi construído, com `file:line`

Só `platform/identity/local_accounts.py` mudou do lado de produção — nenhum
outro arquivo de `platform/`, `gateway/` ou `config/` foi tocado nesta sessão,
porque tudo que a extensão precisava (a rota de criação, o hash da senha, a
coluna, o port `find_user_by_email`/`set_local_password` nos dois backends)
já existia da sessão 9.

- `sign_in` (`:169-235`) agora verifica **duas** fontes de identidade a cada
  chamada, sempre as duas, nunca uma condicionada ao resultado da outra: a
  conta de ambiente (`self.account.verify(username, password)`) e um
  principal criado, resolvido por `_resolve_created_principal` (`:239-258`,
  novo). Se a conta de ambiente bateu, `_ensure_principal` roda (como sempre
  rodou) e o token é emitido para `LOCAL_ACCOUNT_PRINCIPAL_ID`. Senão, se
  `_resolve_created_principal` achou alguém, o token é emitido para aquele
  `user_id`. Senão, a mesma recusa de sempre — mesma exceção
  (`LocalSignInRejected`), mesma mensagem (`"the credential was not
  accepted"`).
- `_resolve_created_principal` (`:239-258`, novo) busca por e-mail
  (`uow.identity.find_user_by_email`, já existente e simétrico nos dois
  backends desde a sessão 9) e verifica a senha com `verify_secret`
  **sempre** — contra o hash armazenado quando `find_user_by_email` achou
  alguém com um, contra `_NO_SUCH_LOCAL_PASSWORD_HASH` (`:148-155`, novo)
  quando não. Ver seção 18.3.
- `_NO_SUCH_LOCAL_PASSWORD_HASH` (`:148-155`, novo, nível de módulo) — um
  hash scrypt válido de um texto fixo (`"no stored local password is ever
  this value"`) que nenhuma senha real jamais produz, calculado uma vez na
  importação do módulo (mesmo custo de scrypt que qualquer verificação real,
  pago uma vez no boot do processo, não por requisição).
- `_ensure_principal` (`:260-285`) **não mudou de comportamento** — só ganhou
  uma frase no docstring dizendo que roda exclusivamente quando a conta de
  ambiente bateu, e que não pode tocar um principal criado.
- `_context` (`:287-288`) passou a receber `user_id: str` em vez de fechar
  sobre `LOCAL_ACCOUNT_PRINCIPAL_ID`; `_record` (`:290-319`) ganhou um
  parâmetro `actor_id: str = LOCAL_ACCOUNT_PRINCIPAL_ID` — o mesmo valor de
  sempre nos dois ramos de recusa (nenhuma mudança de comportamento ali), e o
  `matched_user_id` de verdade no ramo de sucesso.
- Docstring do módulo (topo do arquivo) ganhou um parágrafo novo explicando a
  segunda fonte de identidade e a decisão de "nenhuma porta nova" (seção
  18.5).
- `__all__` (fim do arquivo) ganhou `UnsafeDefaultPassword` — achado à parte,
  não desta feature: esse nome já era importado por
  `tests/unit/platform/identity/test_local_accounts.py` desde antes desta
  sessão (`from platform.identity.local_accounts import (..., 
  UnsafeDefaultPassword)`), mas nunca esteve na lista de exportação do
  módulo — o que `mypy --strict` (que desliga `implicit_reexport`) recusa com
  `error: Module "platform.identity.local_accounts" does not explicitly
  export attribute "UnsafeDefaultPassword"`. Um arquivo que esta sessão é
  obrigada a manter limpo sob `mypy` topou com isso; corrigi porque é uma
  linha, obviamente certa, no mesmo arquivo que esta feature já edita — não
  uma varredura nova em arquivos que não são meus.

Do lado de teste:

- `tests/unit/platform/identity/test_local_accounts.py` — 8 testes novos
  (`:235-386` aproximadamente) mais um helper `_seed_created_principal`, e
  imports ampliados (`hash_local_password`, `Role`, `permissions_for`,
  `PrincipalKind`, `RoleBinding`, `User`, o módulo `local_accounts_module`
  para espionar `verify_secret`, `_real_verify_secret` de `break_glass`
  diretamente para o mesmo fim).
- `tests/contract/deployment/test_local_account_sign_in.py` — 1 teste novo
  (`:167-217`), de ponta a ponta pela aplicação ASGI real: assina como o
  administrador, cria uma pessoa, concede `viewer`, assina como a pessoa,
  lê `/auth/me`.

### 18.3 Tempo constante — o raciocínio, por escrito, como a tarefa pediu

O risco nomeado pela tarefa: "uma consulta que retorna cedo para um e-mail
desconhecido devolve, com um cronômetro, exatamente a resposta que a
mensagem de erro recusa dar." Se `_resolve_created_principal` pulasse a
comparação scrypt quando `find_user_by_email` não achasse ninguém, um
atacante mediria a diferença entre "e-mail desconhecido" (rápido) e "e-mail
conhecido, senha errada" (lento, porque scrypt é deliberadamente caro) — e
teria, por tempo, a mesma resposta que a mensagem uniforme de recusa se
recusa a dar.

A correção: a chamada a `verify_secret` **nunca é condicional à existência do
candidato**. `stored_hash or _NO_SUCH_LOCAL_PASSWORD_HASH` sempre produz um
hash scrypt válido para comparar — o de verdade quando existe, o fixo quando
não — e só **depois** de pagar esse custo é que a função decide, por
`candidate is None or stored_hash is None or not matches`, se devolve
`None`. O mesmo padrão que `LocalAccount.verify` já usa para o par
usuário/senha da conta de ambiente (`hmac.compare_digest` e `verify_secret`
sempre os dois, nunca um condicionado ao outro) — estendido para a segunda
fonte de identidade.

Não escrevi um teste de relógio de parede — não existe um na suíte para
`LocalAccount.verify` também, e medir tempo de parede em CI é uma fonte
conhecida de instabilidade, não a convenção que este repositório já usa em
lugar nenhum para essa garantia. Em vez disso, escrevi
`test_the_number_of_passphrase_comparisons_does_not_depend_on_whether_the_email_is_known`
(`tests/unit/platform/identity/test_local_accounts.py:332-366`): substitui
`local_accounts_module.verify_secret` por um espião que conta chamadas
(via `monkeypatch.setattr(local_accounts_module, "verify_secret", ...)`,
que não aciona o mesmo aviso de re-exportação porque o nome do atributo é
uma string, não um acesso `.verify_secret` tipado) e confirma que uma
tentativa com e-mail desconhecido e uma com e-mail conhecido e senha errada
pagam **exatamente** duas chamadas cada uma — uma para a conta de ambiente,
uma para o candidato. É uma prova do mecanismo (a comparação sempre roda),
não uma medição de nanossegundos, e é isso que a tarefa pediu ao dizer
"handle that and explain how".

### 18.4 Vermelho confirmado, com a mensagem real observada

**Método**: antes de escrever qualquer teste novo, salvei uma cópia exata do
`local_accounts.py` já corrigido
(`/tmp/claude-999/.../scratchpad/local_accounts_new.py`). Para provar
vermelho, reconstruí — de memória exata da minha própria primeira leitura do
arquivo nesta sessão, byte a byte, meu próprio `diff` confirmou que a
primeira linha de divergência era exatamente onde minha primeira edição
começou — o conteúdo do arquivo **como estava antes de eu tocar nele**
(`/tmp/claude-999/.../scratchpad/local_accounts_before_my_edit.py`), troquei
o arquivo real por essa versão, rodei os testes novos, e só então troquei de
volta.

**Um erro cometido e corrigido nesta sessão, dito sem eufemismo**: minha
primeira tentativa de "voltar ao estado anterior" foi
`git show HEAD:platform/identity/local_accounts.py > ...` — e isso estava
errado, porque `HEAD` (`b4a8153`) é várias sessões não commitadas *atrás* do
estado real da árvore de trabalho (a própria seção 17 documenta isso: nada
das sessões 1-9 foi commitado). Esse comando apagou não só a minha edição mas
também `hash_local_password` e todo o resto que a sessão 9 tinha escrito,
e a suíte falhou por `ImportError` em vez de pelo vermelho que eu queria
provar. Percebido imediatamente pelo próprio erro de import, revertido no
mesmo instante com a cópia de segurança (`local_accounts_new.py`), sem que
nenhuma edição real fosse perdida — mas fica registrado aqui porque é
exatamente o tipo de armadilha que este repositório já documentou em memória
de sessão (a árvore de trabalho carrega múltiplas sessões não commitadas; um
`git show HEAD:`/`git checkout --` aqui não volta "para antes da minha
sessão", volta para muito antes disso). Dali em diante usei só a
reconstrução manual do arquivo, nunca mais `git` para isso.

Comando, com a versão pré-edição em vigor:
```
uv run pytest tests/unit/platform/identity/test_local_accounts.py -q \
  -k "created_principal or every_way_a_created or number_of_passphrase"
```
Resultado real: **`4 failed, 4 passed, 11 deselected in 3.26s`**. As quatro
falhas, com a mensagem real:
- `test_a_created_principal_signs_in_as_themself_not_the_local_administrator`:
  `platform.identity.errors.LocalSignInRejected: the credential was not
  accepted` — a senha certa da Grace, recusada, porque o código antigo nunca
  olha para um principal criado.
- `test_a_created_principal_reaches_exactly_what_their_role_grants`: mesma
  exceção, mesma mensagem.
- `test_the_number_of_passphrase_comparisons_does_not_depend_on_whether_the_email_is_known`:
  `assert 1 == 2` — o código antigo faz **uma** chamada a `verify_secret`
  para um e-mail desconhecido (só a da conta de ambiente) em vez de duas;
  exatamente o canal de tempo que a seção 18.3 descreve, agora capturado por
  um teste.
- `test_a_created_principals_sign_in_is_audited_under_their_own_identity`:
  mesma exceção `LocalSignInRejected`.

As outras quatro (`test_every_way_a_created_principals_sign_in_can_fail_says_the_same_thing`,
3 casos parametrizados, e
`test_a_deployment_with_no_local_account_still_refuses_a_created_principal`)
passaram já no código antigo — **caracterização, não correção, dito sem
eufemismo**. O código antigo recusa *qualquer* credencial de um principal
criado, então "recusa com a mesma mensagem" e "nenhuma porta nova" já
valiam, de forma vazia, antes desta sessão. Continuam nomeados como
propriedades importantes porque, depois desta sessão, a recusa deixou de ser
universal (agora existe um caminho de sucesso) — e são esses quatro testes
que garantem que os casos que ainda devem recusar continuam recusando, do
jeito certo, agora que existe um jeito de não recusar.

Depois de restaurar o arquivo corrigido:
```
uv run pytest tests/unit/platform/identity/test_local_accounts.py -q
```
→ `19 passed in 6.82s`.

O mesmo método para o teste de contrato. Com a versão pré-edição em vigor:
```
uv run pytest tests/contract/deployment/test_local_account_sign_in.py -q \
  -k "reaches_exactly_their_role"
```
Resultado real:
```
AssertionError: {"error":{"type":"unauthorized","message":"the credential was not accepted","correlation_id":"f30232a3ded6410d9fb634258e82251b"}}
assert 401 == 200
```
`1 failed, 5 deselected in 2.60s`. Depois de restaurar:
```
uv run pytest tests/contract/deployment/test_local_account_sign_in.py -q
```
→ `6 passed in 5.77s`.

### 18.5 "Nenhuma porta nova" — a decisão, e por quê

A tarefa pediu explicitamente para decidir e justificar: um deployment que
já tem principals criados deveria passar a aceitá-los depois desta mudança?

**Decisão**: o portão continua sendo `self.account is not None` — nada além
disso. Se `self.account is None` (o deployment nunca configurou
`NINJASRE_LOCAL_ACCOUNT_PASSWORD_HASH`), `sign_in` recusa **todo mundo** no
mesmo primeiro `if`, antes de qualquer consulta a `find_user_by_email` —
exatamente como antes desta sessão, código intocado
(`platform/identity/local_accounts.py:190-199`). Um principal criado com
senha local em um deployment que só usa um provedor de identidade externo
continua sem conseguir entrar por aqui, porque o portão nunca foi aberto para
ninguém naquele deployment.

Mas, uma vez que `self.account is not None` — o deployment **já** decidiu
que sign-in local é uma porta que ele quer —, um principal criado antes desta
sessão (pela rota T025/T026, que não depende de `self.account` de forma
nenhuma) passa a poder entrar assim que este código é implantado, sem
precisar ser recriado. Julguei isso correto e não uma porta nova: é a mesma
porta, que agora também funciona para quem a criação já tinha cadastrado —
e é exatamente o comportamento que o Teste Independente da US3 pede. A
alternativa — só aceitar principals criados *depois* deste deploy — não tem
como ser expressa nos dados existentes (nada registra "quando" no sentido que
importaria) e não serviria a ninguém.

Provado por `test_a_deployment_with_no_local_account_still_refuses_a_created_principal`
(`tests/unit/platform/identity/test_local_accounts.py:317-329` — a Grace
existe, com a senha certa, e `account=None` mesmo assim recusa) e, pelo lado
contrário, por
`test_a_created_principal_signs_in_as_themself_not_the_local_administrator`
e pelo teste de contrato (a Grace foi criada **antes** de tentar entrar, pela
rota já existente, exatamente como um deployment real que rodou T025/T026
antes desta sessão faria).

### 18.6 Cada propriedade da tarefa, com o teste que prova

| Propriedade | Como é garantida | Teste que prova |
|---|---|---|
| Uma recusa, uma mensagem, para toda forma de estar errado | O único caminho de recusa por credencial (`else` final de `sign_in`) é o mesmo `LocalSignInRejected`/`"the credential was not accepted"` de sempre, para as duas fontes | `test_every_refusal_says_the_same_thing` (existente, verde inalterado, seção 18.7) + `test_every_way_a_created_principals_sign_in_can_fail_says_the_same_thing` (novo, 3 casos — senha errada de um principal real, e-mail que ninguém criou, principal sem senha armazenada; caracterização, seção 18.4) + `test_a_refusal_gives_away_nothing_about_which_half_was_wrong` (contrato, existente, verde inalterado) |
| Tempo constante | `_resolve_created_principal` sempre chama `verify_secret`, contra o hash real ou contra `_NO_SUCH_LOCAL_PASSWORD_HASH`, nunca condicionado a `find_user_by_email` ter achado alguém (seção 18.3) | `test_the_number_of_passphrase_comparisons_does_not_depend_on_whether_the_email_is_known` — vermelho confirmado (`assert 1 == 2`), verde depois (`calls["unknown"] == calls["known"] == 2`) |
| Nenhuma porta nova | `self.account is None` continua recusando **antes** de qualquer consulta a principal — o portão é esse campo, não esta feature (seção 18.5) | `test_a_deployment_with_no_local_account_refuses_rather_than_letting_anybody_in` (existente, verde inalterado) + `test_a_deployment_with_no_local_account_still_refuses_a_created_principal` (novo, caracterização) |
| `_ensure_principal` é só da conta de ambiente | Só chamado no ramo `account_matches`; nunca no ramo do principal criado | `test_a_created_principal_signs_in_as_themself_not_the_local_administrator` (novo, vermelho confirmado — afirma `LOCAL_ACCOUNT_PRINCIPAL_ID` ausente de `list_users()` depois do sign-in da Grace) + `test_signing_in_twice_reuses_the_account_rather_than_making_a_second_one` (existente, verde inalterado, conta de ambiente) |
| O token é da pessoa: `unscoped=True`, resolve ao que ela detém agora, nunca ao administrador local | `tokens.issue(user_id=matched_user_id, unscoped=True, ...)`, `matched_user_id` nunca é `LOCAL_ACCOUNT_PRINCIPAL_ID` no ramo do principal criado | `test_a_created_principal_signs_in_as_themself_not_the_local_administrator` + `test_a_created_principal_reaches_exactly_what_their_role_grants` (novo, vermelho confirmado, permissões == `permissions_for(Role.VIEWER)` exatamente) + `test_a_person_created_with_a_local_password_signs_in_and_reaches_exactly_their_role` (contrato, novo, vermelho confirmado — round-trip HTTP completo: cria, concede, assina, `GET /auth/me`) |
| O audit registra a tentativa de todo jeito, nomeando quem, sem a senha em forma nenhuma | `_record(..., actor_id=matched_user_id, ...)` no sucesso; `detail={"username": ..., "outcome": ...}` sempre, nunca a senha, nos dois ramos | `test_a_created_principals_sign_in_is_audited_under_their_own_identity` (novo, vermelho confirmado — `event.actor_id == "grace"`, não `local-admin`) |

Nenhuma política de força de senha, bloqueio por tentativas ou limite de
taxa foi inventada — nenhum FR desta feature pede uma, e a tarefa pediu
explicitamente para nomear isso em vez de construir. Nomeado aqui: se algum
dia for necessário, é uma decisão de segurança nova, de outra fatia.

### 18.7 Todo comando desta sessão, com resultado real

```
uv run ruff format --check platform/identity/local_accounts.py
uv run ruff check platform/identity/local_accounts.py
uv run mypy platform/identity/local_accounts.py
```
→ `1 file already formatted` / `All checks passed!` / `Success: no issues
found in 1 source file` (logo depois da implementação, antes de qualquer
teste novo).

```
uv run pytest tests/unit/platform/identity/test_local_accounts.py -q
uv run pytest tests/contract/deployment/test_local_account_sign_in.py -q
```
Antes de escrever qualquer teste novo, com a implementação já no lugar:
`11 passed in 3.06s` / `5 passed in 3.63s` — as suítes que já existiam
continuam verdes sem alteração nenhuma nelas.

Depois de escrever os 8 testes novos de `test_local_accounts.py`:
```
uv run pytest tests/unit/platform/identity/test_local_accounts.py -q
```
→ `19 passed in 6.79s`.

Ciclo vermelho→verde completo, comandos e mensagens reais na seção 18.4.

```
uv run ruff format --check platform/identity/local_accounts.py \
  tests/unit/platform/identity/test_local_accounts.py \
  tests/contract/deployment/test_local_account_sign_in.py
uv run ruff check platform/identity/local_accounts.py \
  tests/unit/platform/identity/test_local_accounts.py \
  tests/contract/deployment/test_local_account_sign_in.py
uv run mypy platform/identity/local_accounts.py \
  tests/unit/platform/identity/test_local_accounts.py \
  tests/contract/deployment/test_local_account_sign_in.py
```
Na primeira rodada sobre o teste de contrato: `ruff format --check` achou uma
linha não formatada (`reached = await signed_out.get(...)` quebrada errado);
corrigida com `uv run ruff format tests/contract/deployment/test_local_account_sign_in.py`
(diff só de formatação). `mypy` achou dois erros reais na primeira rodada
sobre `test_local_accounts.py`:
```
tests/unit/platform/identity/test_local_accounts.py:37:1: error: Module "platform.identity.local_accounts" does not explicitly export attribute "UnsafeDefaultPassword"  [attr-defined]
tests/unit/platform/identity/test_local_accounts.py:344:26: error: Module "platform.identity.local_accounts" does not explicitly export attribute "verify_secret"  [attr-defined]
```
O primeiro é pré-existente (import de antes desta sessão, nunca antes checado
por `mypy` — confirmado por leitura de `__all__` antes de eu tocar nele,
seção 18.2), corrigido acrescentando `UnsafeDefaultPassword` a `__all__` de
`local_accounts.py`. O segundo era meu — troquei o acesso
`local_accounts_module.verify_secret` (um atributo de módulo sujeito à mesma
checagem) por um import direto de `platform.identity.break_glass.verify_secret`
para o único fim de recompor o comportamento real dentro do espião; os dois
`monkeypatch.setattr(local_accounts_module, "verify_secret", ...)` (que
passam o nome como string, não como acesso de atributo) não precisaram
mudar. Depois das duas correções, os três comandos acima:
`3 files already formatted` / `All checks passed!` / `Success: no issues
found in 3 source files`.

```
uv run pytest tests/unit/platform/identity/test_local_accounts.py \
  tests/contract/deployment/test_local_account_sign_in.py -q
```
→ `25 passed in 11.60s`.

```
uv run pytest tests/unit/platform/identity -q
```
→ `154 passed in 8.00s`.

```
uv run pytest tests/unit/gateway/http -q
```
→ `431 passed in 41.10s`.

```
uv run pytest tests/security -q
```
→ `524 passed in 4.00s`.

```
uv run pytest tests/contract/fixtures -q
```
→ `107 passed in 12.39s` — o mesmo número que a sessão 9 já tinha
registrado; o documento OpenAPI não precisou de regeneração porque nenhuma
rota, corpo de requisição ou resposta HTTP mudou nesta sessão (só
`platform/identity/local_accounts.py`, que não é superfície HTTP).

```
uv run pytest tests/contract/deployment/test_first_run_sign_in.py -q
```
→ `4 passed in 1.43s` — sanidade extra: o irmão documentado deste arquivo de
teste, para confirmar que a credencial durável pós-bootstrap (o outro
chamador de `unscoped=True`) continua alheia a esta mudança.

```
make check-imports
```
→ `Contracts: 7 kept, 0 broken.`

```
make check-constants
make check-raw-sql
make check-credentials
make check-protocols
```
→ `EXIT=0` nos quatro (nenhuma constante nova fora de `config/constants/`,
nenhum SQL cru, nenhuma credencial direta, e `check-protocols` — não pedido
pela lista mínima da tarefa, rodado por sanidade porque `IdentityRepository`
é um `Protocol` e esta sessão lê métodos dele, mesmo sem acrescentar
nenhum).

**Achado sobre como rodar os cinco caminhos da lista mínima juntos**: passar
`tests/unit/platform/identity tests/unit/gateway/http
tests/contract/deployment/test_local_account_sign_in.py tests/security
tests/contract/fixtures` ao `pytest` numa única invocação aborta a coleta com
`ImportError: cannot import name 'ORG' from 'conftest'` — dois `conftest.py`
sem `__init__.py` (um em `tests/unit/gateway/http/`, outro em
`tests/security/`) colidem de nome quando o `pytest` os importa juntos nessa
combinação específica de caminhos. Não é uma regressão de produto: os cinco
caminhos, rodados **em invocações separadas** (o método que esta sessão usou
do início ao fim, cada resultado citado acima), passam inteiros, sem exceção.
Não investiguei a causa raiz da colisão em si (é infraestrutura de teste
pré-existente, não tocada por esta sessão) nem tentei corrigi-la — nomeado
aqui só para quem for rodar esta lista de gates de novo não se assustar com
o `ImportError` e saiba rodar os cinco separadamente.

Não rodado: `make verify` completo (é do orquestrador); qualquer coisa sob
`console/` (`console_gate`, Playwright) — nenhum arquivo de console foi
tocado, e a instrução da tarefa proíbe; a suíte Python inteira sem filtro
(a sessão 9 já tinha confirmado `11736 passed, 0 failed` uma vez, e o raio de
alcance desta sessão — `tests/unit/platform/identity`, `tests/unit/gateway/http`,
`tests/security`, `tests/contract/fixtures`, `tests/contract/deployment/`
inteiro — cobre com folga a única superfície que esta mudança poderia ter
atingido, `platform/identity/local_accounts.py`); a migração `0013` contra um
Postgres real (mesmo limite que as seções 9.5/17.5 já registraram — sem
backend Postgres vivo neste sandbox, e esta sessão não tocou nenhum arquivo
Postgres).

### 18.8 Confirmações de fronteira

- `git status --porcelain -- console/` → só arquivos já modificados por
  sessões anteriores (`status.tsx`, `en.ts`, `pt-BR.ts`,
  `advanced-config-section.tsx`, `first-run/model.tsx`). Nenhum aberto por
  mim — nem `Read`, nem `Edit`, nem `Write`, em nenhum momento desta sessão.
- `git diff --cached --stat` → só as duas renomeações que já estavam staged
  antes desta sessão começar
  (`console/tests/e2e/010-provider-out-of-the-box.acceptance.spec.ts` →
  `provider-out-of-the-box.acceptance.spec.ts`,
  `020-confiabilidade-telas.acceptance.spec.ts` →
  `screen-truthfulness.acceptance.spec.ts`), `0 insertions(+), 0
  deletions(-)`. Não tocadas, não somadas a nada por mim.
- `git status --porcelain` sobre os três arquivos que toquei → `M` sem letra
  na coluna de índice nos três (`platform/identity/local_accounts.py`,
  `tests/unit/platform/identity/test_local_accounts.py`,
  `tests/contract/deployment/test_local_account_sign_in.py`) — modificados,
  nada staged.
- `jobs -l` → vazio. Nenhum processo de fundo ficou de pé.
- Nada foi `git add`, `git commit`, `git stash` ou `git restore` por este
  trabalho — a única operação `git` desta sessão além de leitura foi o
  `git show HEAD:` acidental da seção 18.4, revertido no mesmo instante por
  cópia de arquivo, nunca por `git checkout`/`git restore`/`git stash`.

### 18.9 Arquivos tocados nesta sessão

Produto:
- `platform/identity/local_accounts.py` — `sign_in`, `_resolve_created_principal`
  (novo), `_NO_SUCH_LOCAL_PASSWORD_HASH` (novo), `_context`, `_record`,
  docstring do módulo, `__all__`. `122` linhas de diff (`+106/-16`
  aproximado — ver `git diff --stat`).

Teste (arquivos pré-existentes, ampliados):
- `tests/unit/platform/identity/test_local_accounts.py` — 8 testes novos, 1
  helper novo (`_seed_created_principal`), imports ampliados.
- `tests/contract/deployment/test_local_account_sign_in.py` — 1 teste novo,
  de ponta a ponta pela aplicação ASGI real.

Planejamento (não committável, listado por transparência):
- `specs_v6/030-vocabulario-defaults/controle.md` — esta seção 18.

**`tasks.md` não foi tocado.** Nenhuma linha de T025-T028 descreve
literalmente "sign-in aceita um principal criado" — T025/T026 (criação) já
estavam `[x]` desde a sessão 9, e cobrem só a criação; T027/T028 são a ação
primária na tela, fora do escopo desta sessão por instrução explícita
("Backend only. Do not touch the console."). Este trabalho foi pedido pelo
orquestrador além do que `tasks.md` enumera, fechando o buraco que a própria
seção 17.11 já tinha nomeado. Não marquei nenhuma caixa porque nenhuma
representa exatamente isto.

**Nenhum arquivo em `console/` foi tocado. Nenhuma baseline visual foi
aceita, tocada ou sobrescrita.**

### 18.10 O que fica pendente, nomeado, não escondido

- **T027/T028** (a ação primária em Members & roles, e tudo de T029 em
  diante) — inalterados, fora do escopo deste dispatch por instrução
  explícita. Quem pegar T027/T028 agora tem uma rota de sign-in que
  realmente autentica a pessoa criada — o que faltava antes desta sessão.
- **O lado Postgres não foi exercitado ao vivo nesta sessão** — não toquei
  nenhum arquivo Postgres, e o limite já registrado nas seções 9.5/17.5
  (sem backend Postgres neste sandbox) continua de pé, sem mudança.
- **Nenhuma política de força de senha, bloqueio ou limite de taxa** —
  intencionalmente não construída; nomeada na seção 18.6, não escondida.
- **O achado sobre `POST /identity/grants`** (seção 17.3, o `node_id` do
  corpo não é checado contra o nó de quem chama) — não é desta fatia, não
  investigado nem tocado por mim.
- **A varredura formal de identificador de requisito/critério/artigo** não
  foi repetida nesta sessão sobre os três arquivos que toquei — fiz uma
  leitura própria do que escrevi (nomes de teste, docstrings, comentários) e
  não usei nenhum `FR-`, `T0NN`, `SC-`, nome de artigo da constituição, nem
  caminho de `specs_v6/` em nenhum dos três arquivos.

Nenhum destes tem dono fora da própria feature 030; nada foi transferido
para outra spec da onda.

---

## 19. Continuação — sessão 11: T027 e T028, a ação primária de criar pessoa em Members & roles (só console)

**Escopo desta sessão, imposto pelo orquestrador desde o início: T027 e T028
apenas — a ação primária na tela de Members & roles.** Nenhum arquivo do lado
de servidor foi tocado (as seções 17 e 18 já entregam `POST
/identity/principals` e o sign-in local que aceita um principal criado, e
foram lidas antes de qualquer edição). Nenhuma baseline visual foi aceita ou
sobrescrita. Nada de T029 em diante foi tocado. Verificado contra o código
real desta árvore agora, branch `feat/v6-010-provider-out-of-the-box`. Nada
commitado nem staged por este trabalho (seção 19.10 tem a confirmação exata).

### 19.1 O ponto de partida

Members & roles (`console/src/surfaces/settings/members.tsx`) tinha três
painéis — Principals (uma lista), Grants (lista + formulário de atribuir,
via `GrantPanel`) e Active sessions (lista) — e nenhuma ação de criar pessoa
em lugar nenhum. `console/tests/e2e/vocabulary-defaults.acceptance.spec.ts:210-234`
já carregava a alegação, escrita na sessão 3, esperando um elemento
`getByTestId('create-person')` em `/settings/members-roles`.

### 19.2 T027 — o vermelho confirmado, duas peças

**Peça 1 — a alegação de aceite já escrita, rodada antes de qualquer edição.**
Comando:
```
uv run python -m tools.spec_validation browser --feature specs_v6/030-vocabulario-defaults \
  --test console/tests/e2e/vocabulary-defaults.acceptance.spec.ts
```
Resultado real, contra a árvore como a sessão 10 a deixou: **`1 failed, 1
skipped, 12 passed`**. A falha, mensagem observada na íntegra:
```
Error: no primary create-person action exists on Members & roles
expect(locator).toHaveCount(expected) failed
Locator:  getByTestId('create-person')
Expected: 1
Received: 0
Timeout:  5000ms
```
As outras seis alegações do arquivo já estavam verdes (o trabalho das sessões
5-16), e o único pulado é o auto-skip do aviso de escopo destrutivo, nomeado
no próprio comentário do arquivo — nenhum dos dois é desta fatia.

**Peça 2 — a metade que o navegador não consegue provar (ver seção 19.6),
escrita nesta sessão.** `console/tests/unit/surfaces/principals.test.tsx`
(novo) foi escrito importando `PrincipalsPanel` de `@/surfaces/principals` —
um módulo que ainda não existia. Comando:
```
cd console && pnpm exec vitest run --pool=forks tests/unit/surfaces/principals.test.tsx
```
Resultado real: **`Test Files 1 failed (1)`**, mensagem observada:
```
Error: Failed to resolve import "@/surfaces/principals" from
"tests/unit/surfaces/principals.test.tsx". Does the file exist?
```
Onze casos neste arquivo, nenhum executado ainda (a falha é na resolução do
módulo, antes de qualquer teste rodar).

### 19.3 T028 — o que foi implementado, com `file:line`

**Novo componente cliente**: `console/src/surfaces/principals.tsx` —
`PrincipalsPanel` (`:106`), a lista de principals que antes vivia inline em
`members.tsx` **e**, só quando `canWrite`, o formulário de criar pessoa. Três
campos (`Input`, mesma família de `grants.tsx`/`machine-token-groups.tsx`):
nome de exibição, e-mail, e uma senha com `type="password"` +
`autoComplete="off"` (`:198-199`) — o mesmo par que `credential.tsx` já usa
para um campo secreto, aplicado aqui a uma senha que o administrador digita
em vez de colar. O botão (`data-testid="create-person"`, `:206`) é
`variant="primary"`, `state="disabled"` enquanto um dos três campos está vazio
(pós-`trim()`) e `state="loading"` durante o envio — o mesmo padrão de
`add-grant`/`issue-token`.

**Absence, not disabled**: `{!canWrite ? null : (...)}` (`:177`) — nenhum dos
três campos nem o botão existem no DOM para quem não tem `identity.write`; a
lista continua visível (só leitura precisa de `identity.read`, que é a
permissão da própria rota `/settings/members-roles` em `routes.ts`, não
tocada).

**A pessoa criada entra na lista com o vocabulário certo, porque é o mesmo
código que desenha as outras.** `create()` (`:123-156`) envia
`{email, display_name, password}` para `PRINCIPAL_ENDPOINT` (`/api/principals`,
`:34`), e a resposta é convertida no mesmo formato `PrincipalRow` (`:37-46`)
que `members.tsx` já usa para cada pessoa existente — depois anexada
(`setAdded`) à lista, nunca substituindo-a. `PrincipalKindChip` e
`AccountStateChip` (importados de `@/components/status`, já com o
vocabulário certo desde a Fase 4 desta feature) são os únicos lugares onde
`kind`/`is_active` viram texto, para uma linha que o painel já tinha ou uma
que acabou de criar — a prova disso é
`principals.test.tsx`'s `'the created person appears in the list, in the
same vocabulary as every other row'` (verde, seção 19.9).

**Nada que este formulário envia é ecoado de volta.** `password` é limpo
(`setPassword('')`) assim que a requisição resolve, sucesso ou não (`:132`);
a resposta do servidor (`UserView`) nunca carrega um campo de senha para
começo de conversa (seção 17.3 já documentou isso do lado do servidor). Prova:
`principals.test.tsx`'s `'never sends the password back to the browser for
anyone to read'` e `'clears every field, including the password, after a
successful creation'`.

**O novo courier**: `console/src/app/api/principals/route.ts` (novo) —
`POST` (`:36`), irmão de `../grants/route.ts` e `../token/route.ts`: lê o
cookie de sessão (`SESSION_COOKIE`), recusa sem sessão (401) ou com um campo
vazio (400) antes de tocar a rede, encaminha para
`${apiOrigin()}/identity/principals` (`:51`) com o `Bearer` do cookie, e
devolve `{ok, reachable, reason, answer}` — `reasonOf` (`:30`) lê a recusa no
mesmo formato `{"error": {"message": ...}}` que `/identity/grants` já usa,
copiado de `grants/route.ts` porque é o mesmo formato de erro que
`gateway/http/routes/identity.py`'s `conflict()`/`bad_request()` produzem
para as duas rotas.

**`members.tsx`**: `PrincipalsPanel` substitui a antiga `<ul>` inline
(`:151-173`); a constante que antes se chamava `GRANTS` (só usada para
`GrantPanel`) foi renomeada para `IDENTITY_WRITE` (`:64`) porque agora guarda
dois escritos deste mesmo painel — atribuir um papel e criar uma pessoa — e
os dois usos (`:159`, `:194`) foram atualizados. Nenhuma outra tela lia essa
constante (não exportada), então o rename é local e sem efeito colateral.

**i18n, os dois catálogos no mesmo passo**: seis chaves novas,
`admin.principals.create.{displayName,email,password,passwordHelp,action,creating}`
— `console/src/i18n/en.ts:1466-1471`, `console/src/i18n/pt-BR.ts:1252-1258`
(vocabulário brasileiro: "Nome de exibição", "E-mail", "Senha inicial", "A
senha com que esta pessoa entra localmente.", "Criar pessoa", "Criando…" —
nunca "A criar…"/"activar"). `failed`/`unreachable` reaproveitam
`admin.tokens.failed`/`admin.tokens.unreachable`, os mesmos que
`GrantPanel`/`SessionPanel` já usam neste arquivo — nenhuma chave nova
duplicando a mesma frase.

Depois de T028, T027 passa — os dois vermelhos da seção 19.2 estão verdes
(seção 19.9).

### 19.4 Por que não foi preciso regenerar o cliente TypeScript

A seção 17.11 tinha nomeado `console/src/api/schema.ts` desatualizado
(`"/identity/principals": { ...; post?: never; ... }`, conferido antes de
tocar em qualquer coisa) como um provável bloqueio para quem pegasse
T027/T028. Não foi: **todo escrito nesta tela já passa por um courier
próprio em `src/app/api/*/route.ts`, nunca pelo cliente tipado
(`@/lib/api`'s `ask`)** — o próprio docstring de `ask()` explica por quê
(`src/lib/api.ts`): ele lê a credencial de `context.credential`, algo que só
um componente de servidor tem; um componente de cliente (como
`PrincipalsPanel`, que precisa de estado e de um clique) nunca tem acesso a
essa credencial, porque ela vive num cookie `HttpOnly`. `GrantPanel` e
`MachineTokenGroups` já resolviam isso com um courier próprio
(`/api/grants`, `/api/token`) — o mesmo desenho, aplicado a
`/api/principals`. `schema.ts` continua sem a rota nova, e isso não é um
problema desta fatia: nada aqui o lê. Não rodei `make console-client` nem
`make console-client-check` — nenhum dos dois precisa mudar para este
trabalho, e a instrução da tarefa não pediu.

### 19.5 Desenho da tela — decisões sem mockup próprio, e por quê

`spec.md` já diz que Members & roles não tem mockup v6 próprio; a norma são
as regras transversais da v5 (`specs_v5/mockups/settings-v5.html`, Parte 3) e
o mockup-1 da v5 (navegação do shell, não o conteúdo desta tela) — conferido
por leitura: nenhuma menção a "criar pessoa"/"add person" existe em nenhum
dos dois. As decisões de forma vieram de precedente já existente na própria
tela, não de invenção:
- **Formulário sempre visível quando `canWrite`, não um modal/drawer.** É a
  forma que `GrantPanel`'s "Grant this role" e `MachineTokenGroups`'s "Issue
  a token" já usam nesta mesma tela; um modal existe neste código só para
  confirmação destrutiva (`ConfirmDestructive`), nunca para coleta de dados —
  inventar um segundo padrão de interação para uma terceira ação de criação
  na mesma página teria sido a inconsistência, não a norma.
- **Lista antes do formulário**, espelhando a ordem de `GrantPanel`.
- **Ajuda no campo**: a frase sob o campo de senha (`passwordHelp`), não um
  subtítulo de prosa sob o título do painel — a regra "Ajuda mora no campo"
  da Parte 3.
- **Nenhuma confirmação destrutiva**: criar uma pessoa não tira poder de
  ninguém; `ConfirmDestructive` é para remoção/atribuição administrativa, não
  para isto.

### 19.6 A metade não exercitável no navegador — o que foi usado, e por quê

`vocabulary-defaults.acceptance.spec.ts:218-227`'s próprio comentário já
nomeia o buraco: toda fixture deste repositório dá ao principal assinado uma
permissão fixa, e a suíte não tem como assinar como alguém sem
`identity.write` neste arquivo. Conferido de novo agora: `signIn()`
(`console/tests/e2e/session.ts`) só planta o cookie de sessão; quem decide as
permissões é `tools/mockplane/dataset/served.py:82-84`'s `OPERATOR_PERMISSIONS`,
derivado de `permissions_for(Role.OWNER)` — a correção da fatia 2 desta
feature — então **hoje** o navegador só consegue provar a metade
concedida (o teste da seção 19.2 confirma isso: a ação existe para o
viewer que o Playwright assina como). A metade recusada (cenário 3 do
`spec.md`: "um visualizador sem permissão... a ação não é oferecida") não tem
sessão de navegador para exercitá-la sem editar uma fixture à mão — proibido
pela instrução.

**Escolha**: um teste de unidade com um viewer construído, em
`console/tests/unit/surfaces/principals.test.tsx`'s `describe('presence,
decided by identity.write', ...)` — `PrincipalsPanel` recebe `canWrite`
diretamente como prop booleana (não deriva de um viewer inteiro dentro do
componente), então um teste que passa `canWrite={false}` já é, por
construção, o viewer sem `identity.write`: `may(viewer, IDENTITY_WRITE)`
(`members.tsx:159`) é a única ponte entre um viewer real e essa prop, e essa
função (`console/src/session/viewer.ts:101-103`) já tem sua própria cobertura
de teste, não desta fatia. Testar `canWrite` diretamente prova a mesma coisa
que testar um viewer sem a permissão provaria, com menos aparato — o mesmo
raciocínio que `grants.test.tsx`'s `describe('presence, decided by
identity.write', ...)` já usa para `GrantPanel`, um padrão que esta fatia só
repetiu.

### 19.7 O gate de cobertura, fechado com um teste escrito depois — dito sem eufemismo

A primeira rodada de `uv run python -m tools.console_gate test` depois de
T028 (antes desta subseção) falhou:
```
ERROR: Coverage for branches (89.99%) does not meet global threshold (90%)
```
Todos os 2352 testes passavam; só o piso de branches (4560/5067) ficou
0,01 ponto abaixo do teto de 90%. `console/src/app/api/principals/route.ts`
era o arquivo novo com zero cobertura própria — nenhum teste de unidade o
exercitava ainda, só a suíte Playwright (que não conta para esta métrica).
Segui o padrão já existente no repositório para este exato problema
(`console/tests/unit/surfaces/token-route.test.tsx`,
`grants`/`token`/`sso`/`delivery-token` já têm um irmão assim) e escrevi
`console/tests/unit/surfaces/principals-route.test.tsx` (novo, 8 casos):
importa `POST` de `@/app/api/principals/route` e o chama com um
`NextRequest` construído de verdade, cobrindo sessão ausente, cada campo
faltando isoladamente, rede inalcançável, uma recusa nomeada (409) e uma sem
razão (403).

**Dito sem eufemismo**: este arquivo de teste foi escrito depois que
`route.ts` já existia e já tinha sido implementado — não é vermelho
test-first, é a caracterização que fecha a lacuna de cobertura que a
implementação abriu. Rodado uma vez, direto: `8 passed` (seção 19.9).

Depois dele, `uv run python -m tools.console_gate test` inteiro:
`branches 90.32% (4577/5067)`, acima do teto. O ganho (4560→4577, dezessete
ramos) veio quase todo deste arquivo — `principals.test.tsx` (o de T027) já
cobria a maior parte de `principals.tsx` desde o início.

### 19.8 Ledger — cada cláusula do `spec.md` contra o código

| Cláusula (US3, `spec.md`) | Estado | Prova |
|---|---|---|
| Cenário 1: quem tem `identity.write` vê a ação primária, nomeada pelo que faz | FEITO | `create-person` presente, rótulo "Create person"/"Criar pessoa" (`principals.tsx:206`, `en.ts:1470`, `pt-BR.ts:1257`); acceptance `vocabulary-defaults.acceptance.spec.ts:213` verde |
| Cenário 2, metade "a pessoa aparece na lista com o vocabulário certo" | FEITO | `principals.test.tsx`'s `'the created person appears in the list, in the same vocabulary as every other row'`, verde |
| Cenário 2, metade "a criação fica registrada no audit" | FEITO (já existia, verificado) | Servidor: `gateway/http/routes/identity.py:389-400`, provado por `test_the_creation_leaves_an_audit_row_naming_the_actor_and_the_principal` (seção 17.2/17.4) — nada novo desta sessão, só confirmado que o courier não interfere (não toca audit, só encaminha) |
| Cenário 3: sem `identity.write`, a ação não é oferecida | FEITO, provado por unidade (não por navegador) | `principals.test.tsx`'s `'offers no create-person control without identity.write'` — razão do desvio na seção 19.6 |
| FR-018, "fluxo local, com senha inicial" | FEITO (já existia, verificado) | `POST /identity/principals` pede senha, seção 17.3 |
| FR-018, vocabulário de FR-001/FR-002 na linha criada | FEITO | Mesma tabela acima |
| FR-019 (grant nomeado de forma legível) | Fora do escopo desta sessão | Já fechado na Fase 4 (seções 13-16), não tocado aqui |
| SC-005 (criar pessoa sem documentação externa, sem variável de ambiente, sem reiniciar) | FEITO | A tela oferece os três campos e o botão; nenhum passo fora do navegador |
| SC-007 (Members & roles dentro de 2 viewports) | **Não verificado nesta sessão** | `scroll-budget.spec.ts` é T034, Fase 7 — fora da instrução ("não tocar nada de T029 em diante"); ver seção 19.12 |

### 19.9 Todo comando desta sessão, com resultado real

Os dois vermelhos (seção 19.2) já têm seus comandos e saídas citados ali,
não repetidos aqui.

```
cd console && pnpm exec vitest run --pool=forks tests/unit/surfaces/principals.test.tsx
```
Depois de `principals.tsx` existir: `Test Files 1 passed (1)`, `Tests 11
passed (11)`.

```
uv run python -m tools.console_gate typecheck
```
→ `tsc --noEmit`, sem saída (limpo).

```
uv run python -m tools.console_gate lint
```
→ `eslint . && node scripts/check-css-literals.mjs`, sem saída (limpo).

```
uv run python -m tools.console_gate format-check
```
Primeira rodada: `[warn]` em 4 arquivos (`pt-BR.ts`, `principals.tsx`,
`members.tsx`, `principals.test.tsx`) — só formatação (quebra de linha),
corrigido com `pnpm exec prettier --write` nos mesmos quatro arquivos.
Segunda rodada: `All matched files use Prettier code style!`.

```
cd console && pnpm exec vitest run --pool=forks tests/unit/surfaces/principals.test.tsx \
  tests/unit/surfaces/grants.test.tsx tests/unit/surfaces/machine-token-groups.test.tsx tests/unit/i18n
```
→ `Test Files 5 passed (5)`, `Tests 107 passed (107)` — a suíte de i18n
confirma que as seis chaves novas existem nos dois catálogos.

```
uv run python -m tools.console_gate test
```
Primeira rodada (antes de `principals-route.test.tsx`): `2352 passed`, depois
`ERROR: Coverage for branches (89.99%) does not meet global threshold (90%)`
— tratado na seção 19.7. Depois de somar o arquivo de rota:
```
cd console && pnpm exec vitest run --pool=forks tests/unit/surfaces/principals-route.test.tsx
```
→ `Test Files 1 passed (1)`, `Tests 8 passed (8)`. E de novo o gate inteiro:
```
uv run python -m tools.console_gate test
```
→ `Test Files 143 passed (143)`, `Tests 2360 passed (2360)`,
`Statements 94.35% / Branches 90.32% / Functions 92.01% / Lines 96.38%` — sem
erro, o piso de 90% valendo para as quatro métricas.

Repeti `typecheck`/`lint`/`test` uma última vez depois de um ajuste cosmético
(`data-testid="principals-panel"` no `<div>` raiz de `PrincipalsPanel`, para
o mesmo padrão que `grant-panel`/`machine-token-groups` já têm) — mesmos
resultados limpos, `143 passed`/`2360 passed`, cobertura inalterada
(`90.32%` de branches).

```
uv run python -m tools.spec_validation browser --feature specs_v6/030-vocabulario-defaults \
  --test console/tests/e2e/vocabulary-defaults.acceptance.spec.ts
```
Rodado pela última vez depois desse mesmo ajuste: **`13 passed, 1 skipped`**
— o arquivo inteiro verde, incluindo o teste 6
(`a primary create-person action exists for a viewer who may write identity`,
217-231ms conforme a rodada). O pulado (teste 11, preview do wizard) é o
auto-skip já documentado no próprio arquivo, de outra alegação desta mesma
feature, fechada em sessão anterior — não desta fatia.

### 19.10 Confirmações de fronteira

- `git status --porcelain -- console/visual/` → vazio nas duas checagens
  (antes e depois desta sessão). Nenhuma baseline visual tocada, aceita ou
  sobrescrita.
- `git diff --cached --stat` → só as duas renomeações que já estavam staged
  antes desta sessão começar, `0 insertions(+), 0 deletions(-)` — não
  tocadas, não somadas a nada por mim.
- `git status --porcelain` fora de `console/` → nenhuma linha nova; todo
  arquivo Python/config/fixture listado já vinha de sessões anteriores desta
  mesma feature (a lista que as seções 1-18 já documentam). Nenhum arquivo do
  lado de servidor foi aberto por esta sessão — nem `Read`, nem `Edit`, nem
  `Write`.
- `jobs -l` → vazio. `ps aux | grep -E "playwright|uvicorn|next-server|mockplane"`
  → vazio. Nenhum processo de fundo ficou de pé depois de qualquer rodada.
- Nada foi `git add`, `git commit`, `git stash` ou `git restore` por este
  trabalho. Nenhum `git show HEAD:...` foi usado para reconstruir estado —
  os dois vermelhos desta sessão vieram de o módulo/elemento genuinamente não
  existir ainda, não de uma reversão de arquivo.
- Varredura por identificador de requisito/critério/artigo/caminho de
  planejamento (`grep -inE 'FR-[0-9]|SC-[0-9]|\bT0[0-9]{2}\b|Article
  [IVXLC]|constitution|specs_v6|spec\.md|tasks\.md|plan\.md'`) sobre os seis
  arquivos que esta sessão criou ou editou em `console/` → nenhuma ocorrência
  (`grep` saiu com código 1).

### 19.11 Arquivos tocados nesta sessão

Novo:
- `console/src/surfaces/principals.tsx` — `PrincipalsPanel`, `PrincipalRow`,
  `PrincipalsLabels`, `PRINCIPAL_ENDPOINT`.
- `console/src/app/api/principals/route.ts` — `POST`, `reasonOf`.
- `console/tests/unit/surfaces/principals.test.tsx` — 11 casos (T027,
  vermelho confirmado antes da implementação).
- `console/tests/unit/surfaces/principals-route.test.tsx` — 8 casos
  (caracterização escrita depois, fechando o gate de cobertura — seção 19.7).

Produto (pré-existente, editado):
- `console/src/surfaces/settings/members.tsx` — import de `PrincipalsPanel`,
  rename `GRANTS`→`IDENTITY_WRITE`, painel de Principals reescrito para usar
  o componente novo.
- `console/src/i18n/en.ts`, `console/src/i18n/pt-BR.ts` — seis chaves
  `admin.principals.create.*`, nos dois catálogos no mesmo passo.

Teste (arquivo pré-existente desta feature, não tocado — só rodado):
- `console/tests/e2e/vocabulary-defaults.acceptance.spec.ts` — o vermelho
  desta sessão era o teste 6 já ali; nenhuma linha deste arquivo foi editada.

Planejamento (não committável, listado por transparência):
- `specs_v6/030-vocabulario-defaults/tasks.md` — T027, T028 marcados `[x]`.
- `specs_v6/030-vocabulario-defaults/controle.md` — esta seção 19.

**Nenhum arquivo fora de `console/` foi tocado.**

### 19.12 O que fica pendente, nomeado, não escondido

- **SC-007 (orçamento de rolagem de Members & roles) não foi verificado
  nesta sessão.** `console/tests/e2e/scroll-budget.spec.ts:78` já cobre
  `/settings/members-roles`, mas rodá-lo é T034 (Fase 7), e a instrução desta
  sessão proibiu tocar qualquer coisa de T029 em diante. A tela ganhou um
  terceiro formulário inline (três campos + botão) na mesma página que já
  tinha o de `GrantPanel` — é plausível que o orçamento de 2 viewports
  aperte. Fica nomeado para quem pegar T034.
- **A baseline visual de Members & roles está desatualizada, de propósito
  não tocada.** A tela mudou de forma (a lista de principals virou
  `PrincipalsPanel`, com um formulário nunca antes desenhado). Nenhuma
  captura foi feita nem aceita — `git status --porcelain -- console/visual/`
  confirma vazio (seção 19.10). T033 (Fase 7) é quem decide a baseline nova,
  deliberadamente, depois que as telas desta feature estiverem fechadas —
  a própria instrução deste dispatch já nomeava isso como esperado.
- **`transversal-rules.spec.ts` e `vocabulary.spec.ts` não foram rodados
  nesta sessão.** Suas isenções de vocabulário para `/settings/members-roles`
  são T030/T031 (Fase 6), fora do escopo deste dispatch. Não tenho razão para
  crer que meu texto novo ("Display name", "Email", "Initial password",
  "Create person" e as versões pt-BR) viole algum ban existente — é
  vocabulário simples, sem identificador cru — mas não rodei a suíte para
  confirmar, por instrução explícita de não tocar T029 em diante.
- **A metade recusada do cenário 3 (viewer sem `identity.write`) é provada
  por um teste de unidade com `canWrite` construído, não por uma sessão de
  navegador real.** Razão completa na seção 19.6: nenhuma fixture deste
  repositório assina alguém sem essa permissão, e a instrução proibiu editar
  fixture à mão para criar uma.
- **`console/tests/unit/surfaces/principals-route.test.tsx` não é
  test-first.** Escrito depois de `route.ts` já implementado, para fechar o
  gate de cobertura de branches (seção 19.7) — nomeado sem eufemismo, não
  apresentado como um vermelho que motivou a implementação.
- **O lado Postgres da criação de principal e do sign-in local continua não
  exercitado ao vivo** — não é desta sessão (nada de servidor foi tocado);
  mesmo limite já registrado nas seções 9.5/17.5/17.6.
- **O achado sobre `POST /identity/grants`** (o `node_id` do corpo não é
  checado contra o nó de quem chama, seção 17.3) — não investigado, não
  corrigido, não é desta fatia.
- **Um deployment genuinamente vazio (zero principals) esconderia a própria
  ação de criar a primeira pessoa.** `Panel`'s `state === 'empty'`
  (`console/src/surfaces/panel.tsx:173-187`) não renderiza `children` —
  `PrincipalsPanel`, formulário incluso, ficaria por trás do estado vazio
  genérico. Na prática isto é inatingível por quem vê a tela (o próprio
  viewer autenticado é sempre um principal na listagem, então a lista nunca
  está vazia para alguém logado), e é o mesmo comportamento que `GrantPanel`
  já tinha antes desta sessão para o painel de Grants — não é uma regressão
  desta fatia, é um limite estrutural de `Panel` que já existia. Nomeado
  porque não escrevi um teste que prove a inatingibilidade formalmente; é um
  argumento por leitura de código, não uma prova.

Nenhum destes tem dono fora da própria feature 030; nada foi transferido
para outra spec da onda.

---

## 20. Continuação — sessão 12: T029, T030, T031, T032 e T034 — a língua e a prova transversal

**Escopo desta sessão, imposto pelo orquestrador desde o início: T029, T030,
T031, T032 e T034 — não T033 (baselines visuais, decisão do operador), não
T035 (`make verify` completo) e não T036 (consolidação final do
`controle.md`).** Nenhuma baseline visual foi tocada, aceita ou sobrescrita;
`console/visual/screens.json` não foi aberto. Nenhum arquivo de aplicação
(`console/src/**`, `platform/**`, `gateway/**`) foi editado — só dois arquivos
de teste Playwright (`transversal-rules.spec.ts`, `vocabulary.spec.ts`) e este
`controle.md`/`tasks.md`. Branch `feat/v6-010-provider-out-of-the-box`; a
rename staged de dois acceptance specs já presente no início da sessão
(`010-provider-out-of-the-box.acceptance.spec.ts` →
`provider-out-of-the-box.acceptance.spec.ts`,
`020-confiabilidade-telas.acceptance.spec.ts` →
`screen-truthfulness.acceptance.spec.ts`) não foi tocada — confirmado abaixo
(20.9). Nenhum `git show HEAD:...`, `git checkout`, `git stash` ou
`git restore` foi usado; as duas edições de teste foram feitas por
substituição de faixa de linhas exata (script Python de escopo local, não
commitado), com backup prévio em `/tmp/.../scratchpad/backup/` antes de tocar
qualquer arquivo.

### 20.1 T029 — checagem bilíngue

**Verificado, nenhuma mudança necessária — FEITO.** Como o `git diff` desta
árvore mostra o acumulado das onze sessões anteriores (não só a última), a
verificação foi feita contra o diff completo de
`console/src/i18n/en.ts` (76 linhas inseridas, 0 removidas) e
`console/src/i18n/pt-BR.ts` (49 linhas inseridas, 0 removidas) — todas as
chaves que as Fases 3 a 5 introduziram ou alteraram, lidas lado a lado.

**Prova mecânica.** `console/tests/unit/i18n/catalogue.test.ts`'s
`'carries every key in every locale, and names any that is missing'`
(usa `missingKeys()`, `console/src/i18n/messages.ts:38-43`, que compara cada
locale contra todo `Object.keys(EN)`) mais `format.test.ts` — rodados frescos
nesta sessão, não reaproveitados de uma sessão anterior:
```
cd console && pnpm exec vitest run --pool=forks tests/unit/i18n
```
Resultado: `Test Files 2 passed (2)`, `Tests 24 passed (24)`. Isso prova que
nenhuma chave de `en.ts` está ausente de `pt-BR.ts`. A direção contrária
(uma chave em `pt-BR.ts` sem par em `en.ts`) é fechada pelo próprio tipo —
`PT_BR: Partial<Record<MessageKey, string>>` — que `tsc --noEmit` rejeitaria
por excesso de propriedade se existisse; `uv run python -m tools.console_gate
typecheck` (seção 20.6) roda limpo.

**Prova manual — 37 chaves novas, lidas uma a uma no diff, com o par
en/pt-BR conferido:** `firstRun.model.field.{provider,model}`
(`en.ts:568-570`/`pt-BR.ts:127-128`); `configuration.section.{policiesMasking,
policiesGuardrails,policiesApprovals,policiesAutonomy,notificationPolicy}`
(`en.ts:1243-1247`/`pt-BR.ts:1098-1102`); `ingress.delivery.{authenticated,
unauthenticated}` e `ingress.token.{rotate,rotating}`
(`en.ts:1347-1352`/`pt-BR.ts:1145-1150`);
`catalogue.integrations.suggested.evidence.unresolved`
(`en.ts:1403-1404`/`pt-BR.ts:1199-1202`); `principal.kind.{person,
serviceAccount}`, `principal.state.{active,suspended}` e
`tokenGroup.state.inUse` (`en.ts:1453-1459`/`pt-BR.ts:1244-1248`);
`admin.principals.create.{displayName,email,password,passwordHelp,action,
creating}` (`en.ts:1465-1470`/`pt-BR.ts:1252-1257`);
`admin.grant.role.summary{.one,}` e `admin.grant.rolePermissions`
(`en.ts:1489-1494`/`pt-BR.ts:1272-1277`); `admin.column.origin`
(`en.ts:1519`/`pt-BR.ts:1300`); `settings.machineTokens.scopesSelected{.one,}`,
`settings.machineTokens.template.{alertDelivery.name,alertDelivery.purpose,
readOnlyAutomation.name,readOnlyAutomation.purpose,disabled}` e
`settings.machineTokens.destructiveScope.{orgDelete,ownerAssign,
impersonationUse}` (`en.ts:1973-1990`/`pt-BR.ts:1816-1833`).

**Vocabulário brasileiro, verificado, nada de europeu.** Nenhuma ocorrência de
`ecrã`, `ficheiro`, `acção`, `activar`, `objectivo` ou `contactar` no diff de
`pt-BR.ts` (varredura manual, linha a linha, das 49 inseridas). As formas
usadas seguem a convenção da onda: "Pessoa"/"Conta de serviço"
(`principal.kind.*`), "Ativa"/"Suspensa" (`principal.state.*`, nunca
"Activa"), "Criar pessoa"/"Criando…" (`admin.principals.create.action`/
`.creating`, nunca "A criar…"), "Nome de exibição", "Senha inicial", "A senha
com que esta pessoa entra localmente." (`admin.principals.create.*`),
"Rotacionar"/"Rotacionando…" (`ingress.token.rotate`/`.rotating`),
"Autenticado com o token de entrega" (`ingress.delivery.authenticated`).

**Um formulário novo, conferido linha a linha, sem string crua.**
`console/src/surfaces/principals.tsx` (sessão 11, não desta sessão) e
`console/src/app/api/principals/route.ts` foram relidos por inteiro nesta
sessão para confirmar que nenhum texto visível ao usuário escapa de
`message()` — confirmado: os únicos literais no primeiro são atributos
técnicos (`data-testid`, `name`, `type="password"`, classes CSS); o segundo
não renderiza nada (é uma rota de API, sem JSX).

**Um achado, registrado, fora do escopo desta tarefa.** O rótulo de coluna
pré-existente `admin.column.scopes` (`en.ts` "Scopes" /
`pt-BR.ts:1299` "Âmbitos", **não tocado por esta feature** — ausente dos
dois diffs acima) usa "Âmbitos", uma escolha mais europeia que brasileira;
todo o texto novo desta feature que fala do mesmo conceito
(`settings.machineTokens.scopesSelected*`,
`settings.machineTokens.template.disabled`) usa "escopo(s)", a forma
brasileira já padrão no resto do produto (ex.: nenhuma outra tela deste
catálogo usa "âmbito"). A inconsistência é pré-existente — `admin.column.
scopes` não está no diff de nenhuma das doze sessões desta feature — e fica
nomeada aqui para quem cuidar do vocabulário da tela de Machine tokens no
futuro, não corrigida agora por não ser desta fatia.

**Um desenho pré-existente, verificado como consistente, não uma lacuna.**
Os títulos de grupo de domínio em Machine tokens
(`machine-token-groups.tsx:206`, `humanize(group.domain)`) e os nomes de
escopo dentro de cada grupo (`humanize(scope)`, mesma função,
`machine-token-groups.tsx:167-170`) não passam por `message()` — são
derivados em runtime do próprio nome técnico do escopo (`webhook.deliver` →
"Webhook" / "Deliver"), o mesmo padrão que os nomes de escopo individuais já
seguiam antes desta feature tocar o arquivo. Não é uma chave i18n faltando:
é a mesma escolha de design que `preview.tsx:344-349`'s `sectionTitle()`
(T019, sessão 6) já documenta em seu próprio comentário para uma seção que o
catálogo ainda não nomeou — humanizar em vez de exigir uma chave por escopo
que a API pode declarar amanhã. Confirmado por leitura, não alterado.

### 20.2 T030 — remoção das exceções de vocabulário da suíte transversal

**FEITO.** `console/tests/e2e/transversal-rules.spec.ts` — 0 inserções, 40
remoções (`git diff --numstat`). As cinco exceções nomeadas pelo despacho como
dívida desta feature foram removidas de `EXCEPTIONS`
(`transversal-rules.spec.ts:141-154`, estado final):

| Rota removida de `EXCEPTIONS` | Razão que a exception carregava | Por que fecha agora |
|---|---|---|
| `/settings/members-roles` (`vocabulary`) | chip de pessoa/token ainda mostrava `HEALTHY` cru | `AccountStateChip`/`PrincipalKindChip` (T015/T016, fechados na sessão 1) e `PrincipalsPanel` (sessão 11) — nenhum `Badge`/"HEALTHY" alcançável nesta rota hoje |
| `/settings/machine-tokens` (`vocabulary`) | mesmo chip de grupo de token, mesmo call site | `TokenGroupStateChip` (T017, implementado na sessão 1, teste dedicado e fechamento na sessão 6, seção 14) — mesma correção, rota irmã |
| `/settings/autonomy-guardrails` (`vocabulary`) | seção crua titulada `policies.autonomy` | `sectionTitle()`/`SECTION_TITLE` em `preview.tsx` (T019, fechado na sessão 6, seção 14) |
| `/settings/notifications` (`vocabulary`) | seção crua titulada `surfaces.notification_policy` | mesmo mecanismo, mesma tarefa e sessão |
| `/settings/alert-intake` (`vocabulary`) | trust nomeado por `webhook.deliver` cru | `deliveryTokenNamed()`/frase de trust (T020, fechado na sessão 6, seção 14) |

**Mantidas, por instrução explícita — natureza diferente ou rota fora desta
feature:** `/settings/alert-intake` + `scroll-budget` (orçamento de rolagem,
não vocabulário) e `/settings/schedules-destinations` + `vocabulary` (chip
`HEALTHY` de **schedule**, não de pessoa/token — tela que esta feature nunca
tocou; não está em nenhum arquivo do diff das doze sessões e não é uma das
cinco nomeadas pelo despacho).

**A entrada de `/settings/members-roles` estava mesmo obsoleta — confirmado,
não assumido.** A sessão 8 (seção 16.11) já suspeitava disso por leitura de
código (`members.tsx` não renderizava mais nenhum `Badge`). Esta sessão
confirmou rodando o teste de verdade: com a exceção removida, o
`test.fixme()` da linha 260 deixa de disparar para esta rota e a asserção
roda pra valer — resultado real, comando na seção 20.7: **passou**
(`✓ 12 [behaviour] › tests/e2e/transversal-rules.spec.ts:219:5 ›
/settings/members-roles › carries no banned vocabulary in its visible text`).

**Suíte inteira, rodada de verdade contra o build de produção (seção 20.5),
sem nenhuma das cinco.** 29 testes no arquivo (9 rotas × 3 regras + 2 testes
de progresso de setup): **21 passaram de verdade, 8 pularam por
`test.skip`/`test.fixme` legítimo** (7 rotas de scroll-budget já medidas por
`scroll-budget.spec.ts` via `SCROLL_BUDGET_MEASURED_ELSEWHERE`, e a única
`vocabulary` fixme restante, `/settings/schedules-destinations`), **0
falharam.** Nenhuma das nove regras de vocabulário (uma por rota) falhou —
inclusive as cinco que antes eram puladas por exceção.

### 20.3 T031 — fechamento da isenção de `HEALTHY` em Administration

**FEITO.** `console/tests/e2e/vocabulary.spec.ts` — 22 inserções, 5 remoções.
Duas mudanças, ambas no mesmo arquivo:

1. **O docstring do arquivo** (`vocabulary.spec.ts:15-29`, estado final)
   deixou de citar "a person's own active/inactive state on Administration"
   como razão para checar `FORBIDDEN_WORDS` só em regiões, e passou a
   explicar que Administration agora é checada por inteiro, exatamente como
   as frases — porque nada legítimo ali imprime mais essas palavras.
2. **O teste** `'the administration area never shows a forbidden phrase'`
   (nome antigo) virou `'the administration area never shows a forbidden
   phrase or word'` (`vocabulary.spec.ts:120-138`, estado final) — ganhou um
   segundo laço, sobre `FORBIDDEN_WORDS`, aplicado ao `body` inteiro da
   página, no mesmo padrão página-inteira que as frases já usavam. `/administration`
   redireta para `/settings/members-roles`
   (`console/src/shell/routes.ts:700-701`, `SETTINGS_REDIRECTS`), confirmado
   por leitura antes de editar — é literalmente a mesma tela que T030 acima
   provou não render mais `HEALTHY`.

**Rodado de verdade contra o build de produção:** `Tests 7 passed (7)` no
arquivo inteiro, `0 failed`, incluindo
`✓ 60 [behaviour] › tests/e2e/vocabulary.spec.ts:120:1 › the administration
area never shows a forbidden phrase or word`.

### 20.4 T032 — o acceptance spec, inteiro, contra um build de produção

**FEITO. Build usado, exatamente:** o `.next/standalone` que
`uv run python -m tools.spec_validation browser --feature
specs_v6/030-vocabulario-defaults --test <4 arquivos>` construiu por padrão
(`build=True`, `run_browser_validation` → `build_console()` →
`console_gate.one("build")` → script `"build"` de `console/package.json`:
`next build && node scripts/prepare-standalone.mjs`) — a build de produção
real do Next.js (minificada, Server Components compilados), não `next dev`.
Confirmado pelo timestamp do artefato:
```
stat -c '%y %n' console/.next/standalone/server.js
```
`2026-08-18 08:28:04` — depois do início desta sessão (a build anterior, de
`08:11`, era da sessão 11) e depois das minhas duas edições de teste em
T030/T031 (que não exigiam rebuild, mas a build rodou de qualquer forma por
ser a primeira invocação com `build=True` desta sessão). Servido por
`tools/console_e2e.py`'s `console()` (`node server.js` do próprio
`standalone`), contra o backing `mock` (padrão), cenário `populated`
(`DEFAULT_FIXTURE_SCENARIO`, `config/constants/fixtures.py:91`).

**Resultado, `console/tests/e2e/vocabulary-defaults.acceptance.spec.ts`
sozinho dentro da rodada combinada: 13 passed, 1 skipped, 0 failed.** O
pulado é
`✓/− 51 [behaviour] › ... › no covered route prints a transport identifier
where a reader expects a name › the wizard preview never names a changed
field by its raw schema path` — **não** o mesmo teste que a sessão 11 havia
descrito como "o auto-skip" (lá, o aviso de escopo destrutivo). Nesta rodada
o teste de escopo destrutivo (linha 127) **rodou de verdade e passou**
(`✓ 44 ... a destructive scope warns before it is issued...`); quem pulou foi
o teste do preview do wizard, pela **primeira** das suas três condições de
auto-skip (`vocabulary-defaults.acceptance.spec.ts:318-323`): o dataset
`populated` — o cenário padrão — tem o setup já completo
(`fixtures/scenarios/populated/setup-checklist.json:5`, `"complete": true`),
então `/first-run?step=model` redireciona embora antes de qualquer etapa
renderizar, e o teste pula por essa razão nomeada, não chega nem a testar as
outras duas condições (nenhum provedor configurado; preview cujo texto não
menciona `models.investigator`). Confirmado por leitura do fixture, não só
inferido do comportamento — este skip é legítimo, documentado no próprio
arquivo, e não é uma regressão desta sessão nem das anteriores; a
divergência com a descrição da sessão 11 é apenas isso, uma divergência de
descrição, não de comportamento (as duas condições de skip convivem no mesmo
arquivo e o cenário padrão sempre dispara a primeira antes que a segunda
tenha chance).

### 20.5 T034 — o orçamento de rolagem, medido

**FEITO, medido, não assumido.** `console/tests/e2e/scroll-budget.spec.ts`
inteiro, contra o mesmo build de produção: **11 passed, 0 failed** (as onze
rotas de `SCREENS`, `scroll-budget.spec.ts:70-88`).

**As duas telas desta feature, com o número exato — script de medição
descartável, não commitado, rodado contra o build já de pé e apagado depois
de usar** (`console/tests/e2e/_scratch-scroll-measure.spec.ts`, criado,
rodado com
`uv run python -m tools.spec_validation browser --feature
specs_v6/030-vocabulario-defaults --test
console/tests/e2e/_scratch-scroll-measure.spec.ts --no-build`, e apagado com
`rm` logo em seguida — confirmado ausente, seção 20.9). Viewport
1920×1080, orçamento = 1080 × 2.0 = **2160px**
(`config/constants/surfaces.py:344-350`,
`CONFIG_SCREEN_VIEWPORT_{WIDTH,HEIGHT}_PX`,
`CONFIG_SCREEN_SCROLL_BUDGET_VIEWPORTS`), mesma constante que
`scroll-budget.spec.ts` e `transversal-rules.spec.ts` já leem — nada
inventado para a medição.

| Rota | `document.documentElement.scrollHeight` medido | Orçamento | Margem |
|---|---|---|---|
| `/settings/members-roles` | **1080px** | 2160px | 1080px (50,0%) — ver nota |
| `/settings/machine-tokens` | **1729px** | 2160px | 431px (20,0%) |

**Nota sobre o número de `/settings/members-roles`:** 1080px é exatamente a
altura do viewport, o piso que `document.documentElement.scrollHeight` nunca
fica abaixo dele mesmo quando o conteúdo real é mais curto que um viewport
inteiro (é como o navegador calcula essa propriedade — o maior entre a altura
do conteúdo e a altura do viewport). Duas outras rotas medidas na mesma
rodada, sem relação de layout entre si (`/settings/configuration`,
`/settings/audit-log`), também deram exatamente 1080px — o que é consistente
com "conteúdo mais curto que um viewport" nas três, não uma coincidência de
três alturas de conteúdo idênticas. Não medi a altura "verdadeira" abaixo do
piso (não é possível por esta via) — o fato medido e citado na tabela é
`scrollHeight`, que é a mesma grandeza que `scroll-budget.spec.ts` e
`transversal-rules.spec.ts` comparam contra o orçamento, então é a medida
que importa para a regra em si: a tela cabe, com folga, mesmo depois do
segundo formulário inline (criar pessoa) que a sessão 11 acrescentou.

**Machine tokens confirma a margem estreita que a sessão 5 já havia
registrado, antes do formulário de criar pessoa existir.** A seção 13.9/13.11
(sessão 5, logo depois de T005-T012 acrescentarem templates, agrupamento por
domínio e o contador) já tinha rodado
`console_e2e run --project behaviour "tests/e2e/scroll-budget.spec.ts" -g
"settings/machine-tokens"` (`1 passed`) e citado, só como diagnóstico e a
outra largura (1440px, da captura visual, não da viewport real do
orçamento), uma altura de **1729px** — nomeando explicitamente que T034 é
quem teria que reconferir contra a viewport real (1920×1080) depois que o
resto de US2/US3 estivesse em cima. O número desta sessão, medido contra a
viewport real (1920px de largura) que o orçamento de fato usa, é
**exatamente o mesmo, 1729px** — uma coincidência de largura (1440 vs. 1920)
que faz sentido porque o formulário de emissão de token e a lista de grupos
não mudam de forma entre essas duas larguras (sem coluna que reflua
diferente), e um bom sinal de que a altura da tela não se moveu entre a
sessão 5 e agora. O formulário de criar pessoa (sessão 11) mudou
`/settings/members-roles`, não `/settings/machine-tokens` — nada entre a
sessão 5 e esta tocou `machine-token-groups.tsx` de novo, então a margem
continuar idêntica é o resultado esperado, agora confirmado por medição
direta contra a viewport real, não só por diagnóstico. Ainda dentro do
orçamento, com 431px de folga — estreita, mas não estourada. Nenhuma das
duas telas está sobre o orçamento; nada foi ajustado no orçamento em si, e
nada precisou ser, porque nenhuma das duas o ultrapassa.

### 20.6 Gates rodados nesta sessão, com resultado real

```
uv run python -m tools.console_gate typecheck
```
→ `tsc --noEmit`, sem saída (limpo).

```
uv run python -m tools.console_gate lint
```
→ `eslint . && node scripts/check-css-literals.mjs`, sem saída (limpo).

```
uv run python -m tools.console_gate format-check
```
→ `prettier --check .`: `All matched files use Prettier code style!`.

```
timeout 580 uv run python -m tools.console_gate test
```
→ `Test Files 143 passed (143)`, `Tests 2360 passed (2360)`,
`Statements 94.35% (6202/6573) / Branches 90.32% (4577/5067) / Functions
92.01% (1913/2079) / Lines 96.38% (5729/5944)` — idêntico ao final da sessão
11 (nenhum arquivo de `console/src` foi tocado nesta sessão, então nem os
números de cobertura tinham razão para mudar).

```
cd console && pnpm exec vitest run --pool=forks tests/unit/i18n
```
→ `Test Files 2 passed (2)`, `Tests 24 passed (24)` (T029, seção 20.1).

```
uv run python -m tools.spec_validation browser \
  --feature specs_v6/030-vocabulario-defaults \
  --test console/tests/e2e/transversal-rules.spec.ts \
  --test console/tests/e2e/vocabulary.spec.ts \
  --test console/tests/e2e/scroll-budget.spec.ts \
  --test console/tests/e2e/vocabulary-defaults.acceptance.spec.ts
```
Primeira rodada (build fresca, `build=True` por padrão): build concluída às
`08:28:04` (confirmado por `stat`, seção 20.4), suíte rodada em seguida.
Segunda rodada, idêntica, com `--no-build` (reaproveitando a mesma build,
válido porque nada em `console/src` mudou entre as duas): **`52 passed, 9
skipped, 0 failed`**, `exit 0` — log completo salvo em
`/tmp/.../scratchpad/run1.log` (749 linhas) para conferência. Quebra por
arquivo: `scroll-budget.spec.ts` 11/11 passou; `transversal-rules.spec.ts`
21 passou + 8 pulou (test.skip/fixme legítimos) + 0 falhou, dos 29 testes;
`vocabulary-defaults.acceptance.spec.ts` 13 passou + 1 pulou + 0 falhou, dos
14; `vocabulary.spec.ts` 7/7 passou. Nenhum `✘` em nenhuma das duas rodadas.

```
uv run python -m tools.spec_validation browser \
  --feature specs_v6/030-vocabulario-defaults \
  --test console/tests/e2e/_scratch-scroll-measure.spec.ts --no-build
```
`11 passed (4.2s)`, `SCROLL_HEIGHT` impresso por rota (seção 20.5). Arquivo
apagado logo depois (`rm`), confirmado ausente (seção 20.9).

**Não rodados nesta sessão, por instrução explícita, cada um com a razão:**
`make verify` completo (T035, orquestrador); `console-visual-accept` ou
qualquer comparação/captura de baseline visual (T033, decisão do operador);
`pytest` sobre pacotes Python (nenhum arquivo Python foi tocado nesta sessão
— só dois specs Playwright e este `controle.md`/`tasks.md`, então não havia
blast radius Python a cobrir).

### 20.7 Ledger — as cinco tarefas desta sessão

| Tarefa | Estado | Detalhe |
|---|---|---|
| T029 (checagem bilíngue) | **FEITO** | 37 chaves novas conferidas uma a uma, par en/pt-BR presente nas duas, vocabulário brasileiro correto; prova mecânica `tests/unit/i18n` (24 passed) + `tsc --noEmit` limpo. Seção 20.1. |
| T030 (remover exceções de vocabulário da suíte transversal) | **FEITO** | 5 exceções removidas de `transversal-rules.spec.ts:141-154`; as 2 restantes (scroll-budget de alert-intake, vocabulary de schedules-destinations) são de rota/natureza fora desta feature e ficaram. Suíte inteira rodada contra build de produção: 21 passou, 8 pulou legitimamente, 0 falhou. Seção 20.2. |
| T031 (fechar isenção de HEALTHY em Administration) | **FEITO** | `vocabulary.spec.ts:120-138` — `FORBIDDEN_WORDS` agora checado página-inteira em `/administration`, docstring corrigido. 7/7 passou. Seção 20.3. |
| T032 (acceptance spec contra build de produção) | **FEITO** | Build de produção real (`next build`, standalone, `08:28:04`), servido por `tools/console_e2e.py`. 13 passed, 1 skipped (self-skip legítimo e verificado, não o mesmo descrito pela sessão 11). Seção 20.4. |
| T034 (orçamento de rolagem) | **FEITO** | `scroll-budget.spec.ts` 11/11. Medido: members-roles 1080px, machine-tokens 1729px, ambos sob o orçamento de 2160px. Seção 20.5. |

### 20.8 O que fica pendente, nomeado, não escondido

- **A inconsistência `admin.column.scopes` ("Âmbitos") vs. o "escopo"
  brasileiro que todo o texto novo desta feature usa** — pré-existente, fora
  do diff desta feature em todas as doze sessões, nomeada na seção 20.1, não
  corrigida.
- **T033 (baselines visuais) continua nomeado e pendente**, exatamente como
  a sessão 11 deixou (seção 19.12): a tela de Members & roles mudou de face
  duas vezes (chips na Fase 4, formulário de criar pessoa na sessão 11) e
  nenhuma captura foi feita. Fora do escopo desta sessão por instrução
  explícita — decisão do operador.
- **T035 (`make verify` completo) e T036 (consolidação final deste
  documento)** — não desta sessão, do orquestrador.
- **A regressão de T014 aberta na sessão 1** (`tests/unit/gateway/webhooks/
  test_delivery_permission.py::test_the_permission_is_grantable_through_the_token_route`,
  seção 4) e a migração Alembic real da coluna `unscoped` — nenhuma das duas
  foi tocada nesta sessão (nenhum arquivo Python foi aberto); seguem
  pendentes de sessões anteriores, não desta fatia.
- **A metade recusada do cenário 3 de US3** (viewer sem `identity.write`,
  seção 19.6) continua provada só por teste de unidade, não por sessão de
  navegador real — mesmo limite já registrado, não desta sessão.
- Nenhum item novo foi descoberto nesta sessão que não estivesse já nomeado
  em sessões anteriores, além da inconsistência de `admin.column.scopes`
  acima.

### 20.9 Confirmações de fronteira

- `git status --porcelain -- console/visual/` → vazio, antes e depois desta
  sessão. Nenhuma baseline tocada.
- `console/tests/e2e/_scratch-scroll-measure.spec.ts` — criado, usado,
  apagado; `ls` confirma ausência (`No such file or directory`) e
  `git status --porcelain -- console/tests/e2e/` no fim desta sessão lista
  só os dois arquivos editados (`transversal-rules.spec.ts`,
  `vocabulary.spec.ts`) mais o que já vinha de sessões anteriores
  (`settings-nav.spec.ts`, `settings-org.spec.ts` modificados,
  `vocabulary-defaults.acceptance.spec.ts` untracked, as duas renomeações
  staged) — nada extra.
- `git diff --cached --stat` → só as duas renomeações que já estavam staged
  antes desta sessão começar, não tocadas, não somadas a nada por mim.
- Nenhum arquivo fora de `console/tests/e2e/` e
  `specs_v6/030-vocabulario-defaults/` foi aberto nesta sessão (nem `Read`,
  nem `Edit`, nem `Write`) — confirmado pela lista de ferramentas usadas
  nesta sessão, revisada contra este relato.
- `jobs -l` → vazio. `ps aux | grep -E "playwright|node .*server\.js|mockplane"`
  → vazio, depois de cada rodada. Nenhum processo de fundo ficou de pé.
- Nada foi `git add`, `git commit`, `git stash` ou `git restore` por este
  trabalho. As duas edições de teste foram feitas por substituição de faixa
  de linhas exata contra o arquivo lido primeiro, nunca por
  `git show HEAD:...` nem por reversão de qualquer tipo.
- Varredura por identificador de requisito/critério/artigo/caminho de
  planejamento (`grep -inE 'FR-[0-9]|SC-[0-9]|\bT0[0-9]{2}\b|Article
  [IVXLC]|constitution|specs_v6|spec\.md|tasks\.md|plan\.md'`) sobre o diff
  dos dois arquivos editados nesta sessão → nenhuma ocorrência (`grep` saiu
  com código 1).

### 20.10 Arquivos tocados nesta sessão

Teste (pré-existente, editado):
- `console/tests/e2e/transversal-rules.spec.ts` — `EXCEPTIONS` reduzida de
  sete para duas entradas (T030). 0 inserções, 40 remoções.
- `console/tests/e2e/vocabulary.spec.ts` — docstring corrigido, teste da
  área de Administration estendido para checar `FORBIDDEN_WORDS` (T031). 22
  inserções, 5 remoções.

Descartável, criado e apagado dentro desta mesma sessão (não fica no
working tree):
- `console/tests/e2e/_scratch-scroll-measure.spec.ts` — medição de
  `scrollHeight` para T034, apagado logo em seguida.

Planejamento (não committável, listado por transparência):
- `specs_v6/030-vocabulario-defaults/tasks.md` — T029, T030, T031, T032,
  T034 marcados `[x]`.
- `specs_v6/030-vocabulario-defaults/controle.md` — esta seção 20.

**Nenhum arquivo fora de `console/tests/e2e/` foi tocado.** Nenhum arquivo
de `console/src`, `platform`, `gateway`, `config/constants`, `fixtures` ou
`tools` foi aberto ou editado nesta sessão.

## 21. Continuação — sessão 13: reparo do defeito achado na revisão de baseline visual do operador (contagem de sessão sem rótulo)

Estado abaixo verificado contra o código atual, nesta árvore de trabalho —
não contra `HEAD` (`HEAD` está onze sessões não commitadas atrás desta
árvore; ver seção anterior e o aviso de fronteira que abriu esta sessão).

### 21.1 O defeito, confirmado antes de tocar em código

O operador revisou a captura de `administration-1440-light` (rota
`/settings/members-roles`, `console/visual/screens.json:5-8`, status
`"pending"`) e rejeitou-a: `SessionPanel`
(`console/src/surfaces/tokens.tsx`) desenhava um número solto sem rótulo
entre o nome da pessoa e a origem —

```
Principal        Started                    Expires
Avery Lockhart   1        40 days ago       in 325 days
```

Evidência do rejeite preservada em
`specs_v6/030-vocabulario-defaults/evidence/baseline-review/administration-1440-light-REJECTED-bare-session-count.png`
(aberta e conferida — mostra exatamente isso: um "1" solto entre o nome e o
"40 days ago").

Conferido contra a spec antes de escrever qualquer linha: FR-009
(`specs_v6/030-vocabulario-defaults/spec.md:189-192`) proíbe identificar uma
sessão por "um número solto (hoje '59')" e exige "quem é dona e por
origem/dispositivo quando o deployment souber"; o Edge Case da mesma spec
(`:140-141`) e o cenário de aceitação 7 (`:91-92`) repetem a mesma regra
com as mesmas palavras — "não por um número solto". O número que estava no
ar (`group.sessions.length`, uma contagem de quantas sessões aquela pessoa
segura) não é o identificador técnico da sessão (`tokenId`) que o Edge Case
trata como aceitável em contexto técnico — é um segundo número solto,
diferente do primeiro, e cai sob a mesma proibição por forma, não por
origem: nenhum inteiro sem rótulo pode sentar ao lado do nome.

`specs_v6/030-vocabulario-defaults/tasks.md:144-148`, T022 (`[x]` desde
sessão anterior) já dizia "o
identificador técnico sai da face principal e permanece em contexto
técnico" — a caixa estava marcada, mas o código não cumpria a própria frase
da tarefa até este reparo.

### 21.2 O que estava errado, com as duas metades do defeito

`console/src/surfaces/tokens.tsx`, `SessionPanel` (antes do reparo,
`:415-441` da árvore no início desta sessão):

1. **A contagem solta** (`:433-436`): `<span
   className="text-meta text-muted tabular-nums">{group.sessions.length}</span>`
   — sem `data-testid`, sem rótulo, sem chave de i18n. `origin` (adicionado
   em sessão anterior) foi colocado ao lado dela, não no lugar dela.
2. **O cabeçalho e a linha não correspondiam** (a "outra metade da
   alegação" pedida pela orientação desta sessão): `session-columns`
   (`:416-423`, antes) declarava três `<span>` de nível superior — Pessoa
   (sem margem automática), Origem (sem margem automática, colada em
   Pessoa), Expira (`ml-auto`, empurrada sozinha para a direita) — enquanto
   a linha (`:427-443`, antes) agrupava Origem+Expira dentro de um único
   `<span className="ml-auto ...">` empurrado inteiro para a direita. Na
   tela: o rótulo "Started" do cabeçalho ficava perto de "Principal", mas o
   valor de origem da linha ficava colado no "Expires", do outro lado. Duas
   causas independentes de "o leitor não sabe qual valor é qual" — a
   contagem inserida entre nome e o grupo direito, e o cabeçalho não
   espelhando o agrupamento da linha —, cada uma isolada e provada em
   vermelho separadamente (seção 21.4).

### 21.3 O reparo

`console/src/surfaces/tokens.tsx`:

- Removido o `<span>` da contagem solta. Conferido depois, por `grep`:
  `group.sessions.length` não aparece mais em lugar nenhum do arquivo — a
  única leitura de `.length` era exatamente esse `<span>`. O que sobra de
  `group.sessions` é `.map((session) => session.tokenId)` em `endAll`
  (`:392`, para montar a lista de ids a revogar — lógica, não face) e
  `group.sessions[0]` para ler `origin`/`expires` do primeiro da lista
  (`:438`, `:441`, já existia antes desta sessão).
- `session-columns` reagrupado para espelhar exatamente a linha e o mesmo
  idioma que `TokenPanel`/`token-columns` já usa neste arquivo
  (`:271-275`): `<span className="truncate">{labels.person}</span>` sozinho,
  seguido de um único `<span className="ml-auto flex flex-wrap items-center gap-2">`
  contendo `{labels.origin}` e `{labels.expires}` juntos — o mesmo par que a
  linha agrupa. Cabeçalho e linha agora têm o mesmo número de filhos de
  topo (2, antes eram 3 no cabeçalho e 3 na linha, por coincidência
  numérica — não por correspondência real; seção 21.4 explica por que essa
  coincidência escondia o defeito de uma das duas asserções fortalecidas).
- Docstring de `SessionPanel` corrigido: "grouping is what keeps that a
  number beside a name" mentia sobre o próprio código depois do reparo;
  passou a "grouping is what keeps that one row per person".
- Nenhuma chave de i18n nova, nenhuma string nova — a contagem não tinha
  chave (era um número JS puro), então removê-la não deixa nada para
  traduzir. `en.ts`/`pt-BR.ts` não tocados nesta sessão.
- Optei por **remover** a contagem, não rotulá-la (a orientação desta
  sessão deixava as duas opções abertas): nem FR-009, nem o cenário 7, nem
  o Edge Case pedem que o número de sessões de uma pessoa apareça em lugar
  nenhum — só exigem "quem" e "de onde/desde quando", já cobertos por
  `principalLabel` e `origin`. Rotular ("3 sessions") exigiria uma chave de
  i18n nova em pt-BR e en não pedida por nenhuma linha do ledger, para
  reparo que a própria instrução descreveu como estreito.

### 21.4 Vermelho antes, com a mensagem observada — as duas asserções fortalecidas

Antes de tocar em `tokens.tsx`, as duas asserções abaixo foram escritas
contra a árvore ainda com o defeito, rodadas, e o vermelho foi conferido
com o texto exato — só depois disso o código-fonte foi reparado e as
mesmas asserções rodadas de novo até verde. (O reparo foi desfeito por
`Edit` e reaplicado por `Edit` para essa checagem — nunca por `git
checkout`/`git restore`/`git show HEAD:...`, proibidos nesta sessão.)

**Unitário**, `console/tests/unit/surfaces/tokens.test.tsx`:

- `"names the origin the group's first session started from, not a bare
  number"` (`:413`) — o próprio título já prometia "not a bare number"
  desde sessão anterior, mas o corpo nunca checava isso, exatamente a forma
  de defeito citada pela orientação desta sessão. Estendido (`:422-435`)
  para checar, elemento por elemento, que nenhum filho de topo de
  `session-group` é um inteiro solto — checado valor a valor, não por
  substring no texto concatenado da linha, porque os valores reais
  (`"in 4 hours"`) também carregam dígitos.
  **Vermelho observado**: `AssertionError: expected '2' not to match /^\d+$/`
  em `tokens.test.tsx:433` (grupo de Ana, duas sessões).
- `'names a column for the origin, beside who holds the session'`
  (`:438-459`, estendido) — passou a checar que o slot de topo que carrega
  o valor de `session-origin` na linha é o **mesmo índice** do slot que
  carrega o rótulo `labels.origin` no cabeçalho — a "outra metade da
  alegação". **Vermelho observado**: `AssertionError: expected 2 to be 1 //
  Object.is equality` em `tokens.test.tsx:459` (índice do valor de origem
  na linha, 2, contra índice do rótulo no cabeçalho, 1 — a contagem solta
  empurrando tudo um slot adiante).

**Aceitação (browser real, build de produção)**,
`console/tests/e2e/vocabulary-defaults.acceptance.spec.ts:412-473`, teste
`'a session group names an origin or device, not just a name and a raw
count'` (título mantido, corpo estendido) — mesma forma de defeito que o
título já prometia e o corpo não cobria. Acrescentado: checagem de que o
primeiro valor da linha nomeia quem (`:446-447`), e checagem valor-a-valor
de cada linha renderizada contra a contagem de colunas do cabeçalho e
contra o padrão de inteiro solto (`:454-471`), via
`Locator.evaluateAll`/`Element.children` — mesma técnica do teste
unitário, contra o DOM real do browser em vez de jsdom.
**Vermelho observado, rodada real via**
`uv run python -m tools.spec_validation browser --feature specs_v6/030-vocabulario-defaults --test console/tests/e2e/vocabulary-defaults.acceptance.spec.ts`:

```
Error: session row 0 draws a bare, unlabelled number ("1") beside the person

expect(received).not.toMatch(expected)

Expected pattern: not /^\d+$/
Received string:      "1"
```

— o mesmo "1" solto da captura rejeitada pelo operador, agora provado por
um teste que falha por isso, não só por título que promete e corpo que não
confere. A checagem de contagem-de-colunas (`values.length === columnCount`)
não gerou vermelho sozinha — cabeçalho e linha tinham coincidentemente 3
filhos de topo cada, antes do reparo, por razões diferentes (seção 21.2);
o vermelho real veio da checagem valor-a-valor, registrada acima. Ambas as
checagens ficam no arquivo: uma prova o defeito relatado, a outra é guarda
de regressão para a correspondência de colunas daqui para frente.

Depois do reparo em `tokens.tsx`, as três suítes acima foram rodadas de
novo e todas passaram (seção 21.5).

### 21.5 Gates rodados nesta sessão, com resultado real

```
cd console && pnpm exec vitest run tests/unit/surfaces/tokens.test.tsx
```
→ Antes do reparo (fonte revertido): `2 failed | 6 passed | 24 skipped
(32)`, as duas falhas acima. Depois do reparo, ainda com as guardas
`?.`/`?? ''` que o lint reprovaria a seguir: `Test Files 1 passed (1)`,
`Tests 32 passed (32)`. Rodado uma terceira vez depois do ajuste de lint:
mesmo resultado, `32 passed (32)`.

```
uv run python -m tools.spec_validation browser --feature specs_v6/030-vocabulario-defaults --test console/tests/e2e/vocabulary-defaults.acceptance.spec.ts
```
→ Rodada 1 (antes de qualquer edição, linha de base): `13 passed`, `1
skipped` — o pulo é o teste 11 (preview do wizard), não o de sessão; o
teste de sessão (14) já era exercitado de verdade pelos dados da fixture
(não pulava). Rodada 2 (fonte revertido para o estado com defeito, com a
asserção de sessão já fortalecida, só para conferir o vermelho): `1 failed`
(teste 14, mensagem acima), `1 skipped`, `12 passed`. Rodada 3 (fonte
reparado outra vez, testes ainda com as guardas `?.`/`?? ''` que o lint
reprovaria a seguir): `13 passed`, `1 skipped`. Rodada 4 (depois do ajuste
de lint na seção 21.5 abaixo, confirmação final): `13 passed`, `1 skipped`
de novo — mesmo número da linha de base, nas duas últimas rodadas.

```
uv run python -m tools.console_gate typecheck
```
→ `tsc --noEmit`, sem saída (limpo). Rodado duas vezes (antes e depois dos
ajustes de lint abaixo), limpo nas duas.

```
uv run python -m tools.console_gate lint
```
→ Primeira rodada: **6 erros**: `@typescript-eslint/no-unnecessary-condition`
(4, em `?.`/`?? ''` sobre `Element.textContent` — o TypeScript 5.9.3 deste
projeto tipa o getter de `textContent` em `Element` como `string` não-nulo,
não `string | null` como o `Node` genérico; `node_modules/typescript/lib/lib.dom.d.ts:3232-3234`
confirma) e `@typescript-eslint/restrict-template-expressions` (2, `number`
interpolado direto em template literal, ambos o mesmo `index` de
`rowValues.entries()`). Corrigido removendo as guardas redundantes e
envolvendo as duas interpolações do índice em `String(...)`.
Segunda rodada: `eslint . && node scripts/check-css-literals.mjs`, sem
saída (limpo).

```
uv run python -m tools.console_gate format-check
```
→ `prettier --check .`: `All matched files use Prettier code style!`.

```
timeout 590 uv run python -m tools.console_gate test
```
→ `Test Files 143 passed (143)`, `Tests 2360 passed (2360)`, `exit 0`.
Cobertura: `Statements 94.35% (6202/6573) / Branches 90.32% (4577/5067) /
Functions 92.01% (1913/2079) / Lines 96.38% (5729/5944)` — idêntica à
reportada no fim da sessão 12 (seção 20.6), como esperado: nenhum arquivo
fora de `SessionPanel` e seus dois testes foi tocado, e a suíte inteira
continua passando.

**Não rodado nesta sessão**: `make verify` completo (do orquestrador);
`console-visual-accept` ou qualquer captura/aceite de baseline (proibido
pela fronteira desta sessão — a captura de `administration-1440-light`
segue tarefa do operador, agora refletindo os dois reparos — origem e
contagem — juntos, nenhum dos dois ainda capturado: `screens.json:7`
continua com `"status": "pending"`); `pytest` sobre pacotes Python (nenhum
arquivo Python foi aberto nesta sessão).

### 21.6 Ledger desta sessão

| Peça | Estado | Detalhe |
|---|---|---|
| Remover o número de sessões solto e sem rótulo ao lado do nome | **FEITO** | `console/src/surfaces/tokens.tsx` — `<span>{group.sessions.length}</span>` removido de `SessionPanel`; nenhum `.length` de `group.sessions` sobra no arquivo (conferido por `grep`). |
| Cabeçalho (`session-columns`) e linha (`session-group`) correspondendo slot a slot | **FEITO** | `tokens.tsx` — `session-columns` reagrupado para `Pessoa` sozinha + `ml-auto` com `Origem`+`Expira` juntos, espelhando a linha e o idioma já usado por `token-columns` no mesmo arquivo. Provado por índice de slot em `tokens.test.tsx:449-459`. |
| Asserção unitária fortalecida e vermelho confirmado | **FEITO** | `tokens.test.tsx:413-459`, dois testes estendidos; vermelho observado antes do reparo (seção 21.4), verde depois (32/32). |
| Asserção de aceitação fortalecida e vermelho confirmado | **FEITO** | `vocabulary-defaults.acceptance.spec.ts:412-473`; vermelho observado contra build de produção real (seção 21.4), verde depois (13 passed, 1 skipped — mesma linha de base). |
| Docstring de `SessionPanel` corrigido para não descrever um número que não existe mais | **FEITO** | `tokens.tsx:376`. |
| Gates (`typecheck`, `lint`, `format-check`, `test`) | **FEITO** | Seção 21.5; `lint` exigiu duas rodadas (seis erros de TypeScript 5.9 sobre nulidade de `textContent`, corrigidos), as outras três limpas na primeira. |

### 21.7 O que fica pendente, nomeado, não escondido

- **A captura de `administration-1440-light` continua pendente** —
  `screens.json:7`, `"status": "pending"`, não tocado nesta sessão por
  proibição explícita da fronteira. Agora reflete dois reparos empilhados
  desde a última tentativa rejeitada (origem adicionada em sessão anterior;
  contagem solta removida e cabeçalho realinhado nesta sessão) — nenhum dos
  dois ainda tem captura aceita. Tarefa do operador, nomeada por ele mesmo
  na orientação desta sessão.
- **T033 (baselines visuais em geral)** — mesmo pendente já registrado nas
  seções 19.12/20.8, inalterado por esta sessão.
- Todo o restante já nomeado como pendente nas seções 1-20 (a inconsistência
  `admin.column.scopes`, a regressão de T014, a migração Alembic real da
  coluna `unscoped`, T035/T036 do orquestrador) segue exatamente como
  estava — nenhum arquivo relacionado a esses itens foi aberto nesta
  sessão.
- Nenhum item novo descoberto nesta sessão além do que está registrado
  acima.

### 21.8 Confirmações de fronteira

- `git status --porcelain -- console/visual/` → só as quatro baselines já
  aceitas pelo operador antes desta sessão começar (`machine-tokens`,
  `models-providers`, `notifications`, `single-sign-on`, todas
  `1440-light`); `administration-1440-light.png` não aparece — está
  idêntico ao commit `c3f0595` (conferido por `git log`/`git status
  --ignored`), exatamente como o operador descreveu ("já revertida").
  `console/visual/screens.json` sem diff nenhum (`git diff` vazio).
- `git diff --cached --stat` → só as duas renomeações que já estavam
  staged antes desta sessão começar (`010-provider-out-of-the-box...` →
  `provider-out-of-the-box...`, `020-confiabilidade-telas...` →
  `screen-truthfulness...`), não tocadas, não somadas a nada por mim.
- Nenhum arquivo fora de `console/src/surfaces/tokens.tsx`,
  `console/tests/unit/surfaces/tokens.test.tsx`,
  `console/tests/e2e/vocabulary-defaults.acceptance.spec.ts` e
  `specs_v6/030-vocabulario-defaults/controle.md` foi aberto ou editado
  nesta sessão.
- `jobs -l` → vazio. `ps aux | grep -E "playwright|node .*server\.js|mockplane|next-server"`
  → vazio, depois de cada rodada. Nenhum processo de fundo ficou de pé.
- Nada foi `git add`, `git commit`, `git stash` ou `git restore` por este
  trabalho. A reversão temporária de `tokens.tsx` para conferir o vermelho
  (seção 21.4) foi feita e desfeita por `Edit`, substituindo a faixa exata
  de linhas contra o arquivo já lido — nunca por comando `git`.
- Varredura por identificador de requisito/critério/artigo/caminho de
  planejamento (`grep -inE 'FR-[0-9]|SC-[0-9]|\bT0[0-9]{2}\b|Article
  [IVXLC]|constitution|specs_v6|spec\.md|tasks\.md|plan\.md'`) sobre o diff
  dos dois arquivos rastreados e sobre o conteúdo inteiro do arquivo novo
  (`vocabulary-defaults.acceptance.spec.ts`, que por ser untracked não
  aparece em `git diff`) → nenhuma ocorrência nos três (`grep` saiu com
  código 1 nas três checagens).
- `tasks.md` — nenhuma caixa nova marcada. T022 já estava `[x]` de sessão
  anterior; este reparo faz a frase da própria tarefa ("o identificador
  técnico sai da face principal") passar a ser verdade, mas não é uma
  tarefa nova do ledger.

### 21.9 Arquivos tocados nesta sessão

Fonte:
- `console/src/surfaces/tokens.tsx` — três mudanças em `SessionPanel`:
  remoção do `<span>` de contagem solta, reagrupamento de
  `session-columns`, correção da docstring. `+18/-5` conforme `git diff
  --numstat` (23 linhas tocadas ao todo).

Teste (pré-existente, editado):
- `console/tests/unit/surfaces/tokens.test.tsx` — import de `within`
  acrescentado; dois testes estendidos com as checagens de "nenhum número
  solto" e "cabeçalho e linha correspondem por slot". `+55/-1` conforme
  `git diff --numstat` (56 linhas tocadas ao todo).
- `console/tests/e2e/vocabulary-defaults.acceptance.spec.ts` (untracked
  desde sessão anterior — arquivo inteiro, não só o diff desta sessão,
  segue fora do controle de versão) — teste de sessão estendido com as
  mesmas duas checagens, adaptadas para `Locator.evaluateAll` contra o DOM
  do browser real.

Planejamento (não committável, listado por transparência):
- `specs_v6/030-vocabulario-defaults/controle.md` — esta seção 21.

**Nenhum arquivo fora dessa lista foi aberto ou editado nesta sessão.**
Nenhuma baseline visual, nenhum `screens.json`, nenhum arquivo de
`platform`, `gateway`, `config/constants`, `fixtures` ou `tools` foi
tocado.

---

## 22. Consolidação final — os dois vereditos, o vermelho observado tarefa por tarefa, o que não foi test-first, e os gates

Esta seção não substitui nem apaga as 21 anteriores — reúne, num só lugar, o
que um leitor precisaria juntar manualmente se tivesse que abrir todas elas.
Verificado agora, contra a árvore de trabalho real: `git status --porcelain`
vazio, a feature commitada em `554fc54` (69 arquivos, +4306/-291) mais três
commits de fechamento — `c730bfb` (as cinco baselines que as telas
reformuladas mudaram, incluindo a de Members & roles que a seção 21 reparou),
`b7b4401` (o cliente TypeScript regenerado, porque `schema.ts` é gerado do
documento OpenAPI committed e o documento ganhou a rota de T026) e `6f5246f`
(um locator de outra feature reancorado ao heading, porque o título humano
que T019 deu às seções de configuração passou a repetir a palavra
"Guardrails" em dois lugares da mesma tela e um `getByText` que antes era
único deixou de ser). Nenhum desses três últimos commits tem seção própria
nas 21 anteriores — não foram sessões deste agente, e o texto abaixo não
inventa uma narrativa de vermelho/verde para eles que este documento não tem
como provar; cada um é citado pelo que a própria mensagem de commit e o
`git show` provam, nada além disso. `tasks.md`: 34 de 36 marcadas ao escrever
este parágrafo — só T004 e este próprio T036.

### 22.1 Os dois vereditos de descoberta

- **T001 — não existe rota.** `gateway/http/routes/identity.py` só tinha
  `GET /identity/principals` (listagem); nenhum `POST` de criação de
  principal existia em lugar nenhum do arquivo — os dois únicos `POST` do
  roteador eram `/grants` (exige que o principal já exista) e `/tokens`
  (emite credencial para um principal já existente). A capacidade de baixo
  nível já existia (`IdentityRepository.upsert_user`/`upsert_role_binding`,
  já usada por `platform/startup/bootstrap.py` e por
  `platform/identity/local_accounts.py` só para o principal reservado da
  conta local), mas nada na camada HTTP a expunha para um principal
  arbitrário. Evidência completa, com `file:line`, na seção 1. Esse veredito
  decidiu a forma de T025/T026: rota nova sobre o port existente — o que a
  seção 17 construiu.
- **T002 — observado com um teste real, não por leitura de código sozinha.**
  Uma emissão de token sem `permissions` declaradas resolvia, na
  autenticação, para **todas** as permissões que o emissor detém — nunca
  para nenhuma. Provado escrevendo e rodando
  `test_a_token_issued_with_no_permissions_declared_authenticates_to_nothing`
  **antes** de qualquer mudança de produção; vermelho real
  (`assert frozenset({...}) == frozenset()`, o lado esquerdo carregando
  `webhook.deliver`, `audit.export`, `remediation.execute` e outras). Causa:
  `_scoped()` lia uma lista de escopos vazia como "sem teto" de forma
  incondicional — correto para uma sessão de navegador ou a credencial
  durável pós-bootstrap, errado para uma emissão de machine token, que é
  exatamente onde "nenhum escopo marcado" precisa significar "nenhum poder".
  Evidência completa na seção 2. Esse veredito decidiu que T013 era
  **correção**, não caracterização — a razão de T014 ter mudado código de
  produção (`unscoped: bool` em `ApiToken`, seções 2 e 9.4-9.5).

### 22.2 O vermelho observado, tarefa por tarefa

Resumo por tarefa; a mensagem completa e o comando exato estão na seção
citada, não repetidos aqui.

| Tarefa(s) | Onde o vermelho foi visto | Mensagem observada (resumida) | Seção |
|---|---|---|---|
| T005/T006 (default vazio, contador) | unidade (lote de 15 falhas) + aceite | aceite: "15 scope checkbox(es) start checked..."; "no element on the issue form states how many scopes are currently selected" | 13.2, 13.9; 11.2 itens 1-2 |
| T007/T008 (templates de finalidade) | unidade + aceite | aceite: "no 'Alert delivery' purpose template control exists on the issue form" | 13.3; 11.2 item 3 |
| T009/T010 (agrupamento por domínio) | unidade + aceite | aceite: "15 scope checkboxes render in 0 named domain group(s); a single flat band is not grouping" | 13.4; 11.2 item 4 |
| T011/T012 (aviso de escopo destrutivo) | unidade + aceite (real só depois de T003 corrigir o fixture) | unidade: `Unable to find an element by: [data-testid="destructive-scope-warning"]`; aceite: "checking scope-org.delete produced no warning naming what it permits, Expected: 1, Received: 0" | 13.5, 13.9; 12.3 item 2 |
| T013/T014 (defaults seguros de escopo) | contrato de servidor (`test_tokens.py`) | `AssertionError: assert frozenset({...}) == frozenset()` | 2 |
| T015/T016 (chip pessoa/estado de conta) | unidade + aceite (só sob reversão deliberada — ver 22.4.3) | unidade: `Error: Element type is invalid...` (componente ainda não existia); aceite: "the raw transport value SERVICE_ACCOUNT is shown instead of a display name" | 7; 11.2 item 10 |
| T017 (chip do grupo de token) | só aceite, e só sob reversão deliberada — nunca vermelho por natureza (ver 22.4.1) | aceite: "the raw resource-health word HEALTHY describes a token group on this page" | 11.2 item 11; 14.2 |
| T018 (preview do wizard nomeia o campo) | unidade de componente (`first-run.test.tsx`) | "Expected element to have text content: Investigation model / Received: would changemodels.investigator.model → claude-opus-5" | 7 (seção 9.1 fecha o call site que faltava) |
| T019 (títulos `policies.*`/`surfaces.*`) | unidade (`config-editor.test.tsx`) + aceite | unidade: `expected <span>policies.masking</span> to be null`; aceite: "the schema path 'policies.masking' is shown as a section title" | 14.2; 11.2 itens 6-7 |
| T020 (trust em Alert intake) | unidade (5 de 7 casos) + aceite | unidade: "Expected element not to have text content: webhook.deliver / Received: Trusted by webhook.deliver..."; aceite: item 8 | 14.2; 11.2 item 8 |
| T021 (evidência da sugestão do estate) | unidade backend + unidade console (retirando a implementação via `git stash`) + aceite | backend: `AttributeError: 'Suggestion' object has no attribute 'resource_label'`; console: "Expected element to have text content: observability-01 / Received: Found at..., on resource monitoring"; aceite: item 9 | 15.4 |
| T022 (identificação de sessão) | unidade (`tokens.test.tsx`) + aceite (real só depois de T003); reforçado na sessão 13 | unidade: `Unable to find an element by: [data-testid="session-origin"]`; aceite: "no session on this page states where it came from"; sessão 13: "session row 0 draws a bare, unlabelled number ('1') beside the person" | 16.2; 12.3 item 2; 21.4 |
| T023/T024 (resumo do grant, papel legível) | unidade (`grants.test.tsx`) | "Objects are not valid as a React child (found: object with keys {summary, permissions})"; `Unable to find an element by: [data-testid="grant-role"]` | 16.3-16.4 |
| T025/T026 (criar pessoa, servidor) | contrato (`test_identity_principal_routes.py`), vermelho provado por reversão deliberada — ver 22.4.3 | 7 de 8 testes: `assert 405 == 201`, `assert 405 == 403`, `assert 0 == 1` | 17.2 |
| Sign-in local aceita a pessoa criada (sessão 10, parte de US3) | unidade (`test_local_accounts.py`) + contrato (`test_local_account_sign_in.py`) | `LocalSignInRejected: the credential was not accepted`; `assert 1 == 2` (canal de tempo); `assert 401 == 200` | 18.4 |
| T027/T028 (ação primária em Members & roles) | aceite (alegação já escrita desde a sessão 3) + unidade (módulo novo) | "Error: no primary create-person action exists on Members & roles"; `Failed to resolve import "@/surfaces/principals"` | 19.2 |

### 22.3 T004 — o acceptance spec: histórico completo e o veredito

**O arquivo existe**: `console/tests/e2e/vocabulary-defaults.acceptance.spec.ts`,
474 linhas, 14 `test()` distribuídos em 7 `describe`, um por alegação
normativa listada na própria tarefa. Escrito na sessão 3 (seção 11),
**depois** que cinco telas já tinham mudado nas sessões 1-2 — um desvio de
ordem real, admitido sem eufemismo no topo deste documento desde a primeira
sessão e nunca apagado.

**O histórico das 14 alegações, da sessão 3 até hoje:**

- **11 foram vermelhas na primeira rodada da sessão 3** (comando
  `uv run python -m tools.spec_validation browser --feature
  specs_v6/030-vocabulario-defaults --test
  console/tests/e2e/vocabulary-defaults.acceptance.spec.ts`, resultado
  `9 failed, 3 skipped, 2 passed`): 9 sem precisar de nenhuma reversão
  (linhas 48, 65, 85, 191, 215, 269, 294, 369, 382 — seção 11.2) e 2 só depois
  de reverter deliberadamente `members.tsx`/`machine-token-groups.tsx` de
  volta a `<Badge>`, porque T015-T017 já estavam implementadas desde a sessão
  1 e sem a reversão o teste ficava verde sem provar nada (linhas 241, 257 —
  seção 11.2, itens 10-11; restaurado byte a byte depois, conferido por
  `git diff`).
- **3 não puderam ser observadas vermelhas naquela primeira rodada** — nem
  natural, nem sob reversão — e cada uma ganhou um `test.skip` nomeado, com a
  causa raiz cravada em código ou fixture, em vez de um skip mudo (seção
  11.2, itens 12-14): o aviso de escopo destrutivo (linha 127, nenhum
  cenário servido dava a nenhum principal `org.delete`/`owner.assign`/
  `impersonation.use`), o preview do wizard (linha 311/309) e a
  identificação de sessão (linha 414/412, o token da sessão do navegador
  nomeado `"console"` no fixture contra `"Console sign-in"` que o código
  compara).
- **Sessão 4 (T003) corrigiu os dois achados estruturais de fixture** — o
  "owner" passou a carregar as 31 permissões que `permissions_for(Role.OWNER)`
  de fato computa (as três destrutivas incluídas) e o token de sessão do
  navegador passou a se chamar `"Console sign-in"`. Rodando a suíte de novo,
  **2 das 3 alegações travadas viraram vermelho real** (seção 12.3, item 2):
  o aviso destrutivo (`Error: checking scope-org.delete produced no warning
  naming what it permits, Expected: 1, Received: 0`) e a sessão (`Error: no
  session on this page states where it came from — only who holds it and a
  count`) — porque a fixture passou a alimentar o DOM que a asserção precisa
  encontrar, e as telas (T012, T022) ainda não existiam para satisfazê-la.
  Isso deixou **13 das 14 alegações capazes de ir vermelhas por este
  arquivo**, uma de cada vez, à medida que cada tarefa correspondente as
  implementou (sessões 5-11, tabela da seção 22.2 acima).
- **A terceira (linha 311/309, preview do wizard) foi investigada a fundo,
  não deixada como um skip que ninguém tentou forçar.** A sessão 3
  reexecutou a suíte contra `--scenario first-run` (o único cenário em que a
  tela chega a renderizar) duas vezes: uma com o código real (T018 já
  implementado, ✓), outra com uma reversão deliberada de
  `screens/first-run.tsx` (`fieldLabels: {}` no lugar do mapa real) — e a
  alegação **continuou passando** nas duas, o que não deveria acontecer se
  estivesse testando o que diz testar. Instrumentado com um dump de depuração,
  a causa raiz apareceu: `/api/preview` responde, em **todo** cenário deste
  repositório, com o mesmíssimo corpo fixo
  (`investigation.max_loops`/`investigation.reasoning_effort`),
  independente do patch pedido — nunca um `path` de `models.investigator.*`,
  confirmado byte a byte contra `config-preview.json` de cada cenário. Esta
  não é uma lacuna que uma correção de fixture ou de tela fecha; é uma
  limitação estrutural do plano mock para este endpoint especificamente.
- **A prova real do comportamento que T018 corrigiu vive em outro teste, e
  ela foi vermelha de verdade.** `console/tests/unit/surfaces/first-run.test.tsx`
  (que mocka a resposta do preview em vez de pedir a um fixture que não pode
  variar) foi vermelho, mensagem observada e registrada na seção 7:
  `Expected element to have text content: Investigation model / Received:
  would changemodels.investigator.model → claude-opus-5`. Reconfirmado
  **agora**, nesta sessão de consolidação, rodado de novo do zero:
  `pnpm exec vitest run --pool=forks tests/unit/surfaces/first-run.test.tsx
  -t "display name"` → `Test Files 1 passed (1)`, `Tests 2 passed | 95
  skipped (97)`.

**O estado hoje, confirmado ao vivo nesta mesma sessão** (não só citado de
uma sessão anterior): `uv run python -m tools.spec_validation browser
--feature specs_v6/030-vocabulario-defaults --test
console/tests/e2e/vocabulary-defaults.acceptance.spec.ts` →
**`13 passed, 1 skipped`**, construído contra uma build de produção nova
desta rodada, servidor limpo ao final (`Shutting down / Application shutdown
complete`), nenhum processo residual, árvore ainda `git status --porcelain`
vazia depois. O único skip é o teste 11, o preview do wizard — a mesma linha
309, pela primeira das suas três condições de auto-skip
(`vocabulary-defaults.acceptance.spec.ts:319-323`, o cenário padrão já tem o
setup completo e `/first-run` redireciona antes de qualquer step renderizar).
Confirmado por leitura direta do arquivo hoje: as três condições de
auto-skip e o comentário que as explica (linhas 314-323, 339-351) seguem
exatamente como a sessão 3 as escreveu; nada nas sessões seguintes nem nos
três commits de fechamento tocou este bloco.

**Veredito: T004 marcado.** Toda alegação do arquivo foi, em algum ponto do
histórico desta feature, observada falhando com uma mensagem real —
11 vermelhas por natureza através deste próprio arquivo, 2 vermelhas por
reversão deliberada e honestamente registrada como tal (seção 22.4.3), e a
14ª, a única que continua pulando, foi investigada até a raiz estrutural
(o mock não reage ao patch em nenhum cenário servido, sob nenhuma condição
que esta sessão ou a sessão 3 conseguiram forçar) e tem sua prova real —
vermelho e depois verde, com mensagem — num teste de componente dedicado,
citado pelo nome no próprio comentário do arquivo (linhas 346-349). Isso é
exatamente o caso que a regra original desta tarefa antecipava como
aceitável quando disse "toda alegação foi observada vermelha": uma alegação
cuja prova mora, de forma nomeada e rastreável, num teste irmão, não atrás
de um skip mudo. `tasks.md` foi corrigido de acordo (T004 agora `[x]`).

### 22.4 Toda tarefa que não foi test-first, sem eufemismo

#### 22.4.1 Testes que passaram já na primeira execução — nunca vermelhos

Quinze, ao todo, cada um já nomeado como tal na sua própria sessão; reunidos
aqui para que um leitor veja, num só lugar, exatamente quais alegações
descansam sobre um teste que nunca falhou:

1. `test_a_token_issued_with_explicit_permissions_carries_only_those`
   (T013) — já passava antes de qualquer mudança desta feature (seção 2,
   linha 119 da tabela original).
2. `test_a_request_beyond_the_owners_own_permissions_is_narrowed_not_granted`
   (T013) — `1 passed` já na primeira execução; o mecanismo que prova
   (`PermissionSet.narrowed_to`) não foi tocado nesta feature (seção 9.4).
3. A terceira asserção de T011 ("marcar um escopo destrutivo nunca desabilita
   o Issue") — passou já na primeira execução porque o botão só depende de
   `name.trim()`, nunca dos escopos marcados (seção 13.5).
4-5. As duas `it()` de T017 (`describe('the group state chip names what the
   group has done...')`) — `Tests 2 passed | 35 skipped (37)`, vermelho nunca
   observado; a implementação que provam já existia de uma sessão anterior
   (T016) (seção 14.2).
6. T020's "sits beside what it is scoped to, rather than orphaned below the
   rows" — estrutural, verdadeira antes e depois (seção 14.2).
7. T020's "never counts a revoked token as the one authenticating
   deliveries" — passou de forma vazia: antes da implementação a tela não
   lia `/identity/tokens`, então nenhum token revogado podia aparecer por
   construção; não é prova de que a exclusão funciona, só passou a testar
   algo real depois de implementar (seção 14.2).
8. A asserção de `node_id` dentro de
   `test_the_creation_leaves_an_audit_row_naming_the_actor_and_the_principal`
   (T025) — nunca revertida e vista vermelha individualmente (seção 17.2).
9. `test_a_team_scoped_admin_may_create_and_the_audit_row_names_that_team`
   (T025) — mesma nota (seção 17.7).
10. `test_a_local_password_is_stored_by_hash_and_survives_an_unrelated_upsert`
    (T026, `test_identity_repository.py`) — `16 passed` já na primeira
    execução, escrito depois que `set_local_password` já existia nos dois
    repositórios (seção 17.7).
11. `test_setting_a_password_for_nobody_reports_it` (T026) — mesma nota
    (seção 17.7).
12-14. As três variações de
    `test_every_way_a_created_principals_sign_in_can_fail_says_the_same_thing`
    (sign-in local, sessão 10) — passaram já no código antigo, porque o
    código antigo recusava *qualquer* credencial de um principal criado
    (seção 18.4).
15. `test_a_deployment_with_no_local_account_still_refuses_a_created_principal`
    (sessão 10) — mesma nota (seção 18.4).

#### 22.4.2 Um teste escrito depois da implementação, para fechar um piso de cobertura

`console/tests/unit/surfaces/principals-route.test.tsx` (8 casos) — a
primeira rodada de `uv run python -m tools.console_gate test` depois de T028
reprovou por `ERROR: Coverage for branches (89.99%) does not meet global
threshold (90%)`, com `console/src/app/api/principals/route.ts` (o courier
novo) em zero cobertura própria. Este arquivo foi escrito depois de
`route.ts` já existir e já estar em produção, seguindo o mesmo padrão que o
repositório já usa para este exato problema em rotas irmãs
(`token-route.test.tsx` etc.). Dito na própria sessão sem eufemismo: "não é
vermelho test-first, é a caracterização que fecha a lacuna de cobertura que a
implementação abriu" (seção 19.7).

#### 22.4.3 Vermelho provado só por reversão deliberada — não test-first por ordem de relógio, mas não "nunca falhou"

Categoria distinta das duas acima: aqui o vermelho **foi** observado, com
mensagem real — só que a ordem cronológica real foi implementação primeiro,
teste depois, e a única forma honesta de provar que o teste discrimina foi
reverter o código de propósito, rodar, ver vermelho, e restaurar byte a byte
(conferido por `git diff` em cada caso, nunca por `git checkout`/`git show
HEAD:` em nenhuma delas). Reunidas aqui para não ficarem escondidas atrás da
palavra "vermelho confirmado" nas suas próprias seções:

- **As duas alegações de chip do acceptance spec** (linhas 241 e 257 de
  `vocabulary-defaults.acceptance.spec.ts` — "SERVICE_ACCOUNT/HEALTHY em
  Members & roles" e "HEALTHY no chip de grupo de token"). Escritas na sessão
  3, depois que T015-T017 já tinham sido implementadas na sessão 1.
  `members.tsx`/`machine-token-groups.tsx` foram revertidos de volta a
  `<Badge>`, a suíte rodou vermelha de verdade (`the raw transport value
  SERVICE_ACCOUNT is shown instead of a display name`; `the raw
  resource-health word HEALTHY describes a token group on this page`), e os
  dois arquivos foram restaurados depois (seção 11.2, itens 10-11).
- **O teste de contrato de T025** (`test_identity_principal_routes.py`, 7 de
  8 casos). Escrito na mesma sessão em que a rota já tinha sido montada — "T025
  não nasceu antes de T026 no relógio desta sessão", dito sem eufemismo na
  própria seção 17.2. A prova: reverter `create_principal` e a linha de
  permissão em `route_permissions.py`, rodar a suíte contra a árvore
  revertida (`7 failed` — `assert 405 == 201`, `assert 405 == 403`,
  `assert 0 == 1`), depois restaurar as duas peças e confirmar `7 passed`
  (seção 17.2).

#### 22.4.4 Uma observação desta sessão, não autodeclarada em nenhuma sessão anterior

`console/tests/e2e/settings-org.spec.ts:80-91` — a asserção existente que
codificava o default inseguro (`toBeChecked()`) foi invertida para
`.not.toBeChecked()` na sessão 5, junto com T005/T006 (seção 13.6). Nenhuma
sessão registra ter revertido este arquivo especificamente para observar sua
própria linha reprovando sob o código antigo — o "verde confirmado" citado
ali descansa no lote de 15 falhas já observado em
`machine-token-groups.test.tsx` para o mesmo defeito, não numa reversão
isolada deste arquivo. Não é um defeito de produto (o comportamento que a
asserção prova hoje é o correto, e é o mesmo que a suíte de unidade já
provou vermelho-depois-verde) — é uma lacuna de proveniência: esta linha
específica nunca teve seu próprio vermelho citado. Achado nesta sessão de
consolidação, não repetido em nenhuma das 21 seções anteriores.

### 22.5 O que ficou de fora, nomeado, e por quê

- **As duas migrações Alembic desta feature (`0012_token_unscoped`,
  `0013_local_password`) nunca foram exercitadas contra um Postgres real.**
  Este sandbox não tem um backend Postgres vivo — a mesma limitação que
  `tests/contract/persistence/test_operations.py` já documenta para toda a
  suíte, não uma lacuna nova. Validadas só por leitura da cadeia de revisão
  (`ScriptDirectory`, sem lacuna, uma cabeça só) e por `mypy`/`ruff` limpos
  nos arquivos Postgres tocados (seções 9.5, 17.5, 17.6).
- **A senha local nunca é logada — verificado por leitura de código, não por
  um teste que capture saída de log.** Nenhuma chamada de `_LOG.*` existe em
  `create_principal`; a única passagem de `body.password` é para
  `hash_local_password(body.password)`, uma vez (seção 17.4).
- **Nenhuma política de força de senha, bloqueio por tentativas ou limite de
  taxa foi inventada** para o sign-in local nem para a criação de principal —
  nenhum FR desta feature pede uma (seções 17.11, 18.6).
- **A metade recusada do Cenário 3 de US3** (um viewer sem `identity.write`
  não vê a ação de criar pessoa) é provada só por um teste de unidade com
  `canWrite={false}` construído diretamente, não por uma sessão de navegador
  real — nenhum cenário de fixture deste repositório assina como um viewer
  sem essa permissão, e editar um fixture à mão para criar um foi
  explicitamente vetado no escopo daquela sessão (seção 19.6).
- **Um deployment genuinamente vazio (zero principals) esconderia a própria
  ação de criar a primeira pessoa** atrás do estado vazio genérico de
  `Panel` — argumentado por leitura de código (o próprio viewer autenticado
  sempre aparece na própria listagem, então essa lista nunca fica vazia para
  quem está logado; o mesmo limite já valia para `GrantPanel` antes desta
  feature), não provado por um teste dedicado (seção 19.12).
- **O achado sobre `POST /identity/grants`**: o `node_id` do vínculo vem do
  corpo da requisição, escolhido por quem chama, enquanto a permissão que
  autoriza a chamada é checada só contra o nó do próprio chamador — um
  possível caminho de escalonamento, não confirmado por teste, não
  corrigido, de uma rota que já existia antes desta feature e não é dela
  (seção 17.3).
- **A inconsistência `admin.column.scopes` ("Âmbitos") contra "escopo"**, o
  vocabulário brasileiro que todo texto novo desta feature usa para o mesmo
  conceito — pré-existente, fora do diff das treze sessões, nomeada mas não
  corrigida (seção 20.1).
- **FR-008, "o identificador DEVE ficar no destino do link"** foi satisfeito
  por um caminho diferente do literal: o id cru do recurso fica em
  `data-resource` no `<li>`, não como parâmetro do link "Connect" — decisão
  registrada explicitamente (estender `url-state.ts` sem testá-lo a fundo
  pareceu mais arriscado que o ganho), não uma omissão (seções 14.5, 15.2).
- **`console/tests/e2e/settings-nav.spec.ts:93-99`** precisou de
  `'Single sign-on'` na lista esperada da subnav depois que T003 corrigiu as
  permissões do "owner" — o vermelho foi observado e citado (seção 12.3,
  item 3: `Array ["Members & roles", + "Single sign-on", "Machine tokens",
  ...]`), mas nenhuma sessão registrada narra ter aplicado o conserto; ele
  está presente na árvore hoje (conferido por leitura direta do arquivo
  nesta sessão de consolidação), então foi absorvido em algum ponto entre a
  sessão 4 e o commit `554fc54` sem uma seção própria — nomeado aqui como a
  única lacuna de continuidade narrativa encontrada nesta auditoria, não
  como um resultado incerto.
- **Todo o restante já nomeado, seção por seção, nas 1-21** — a inconsistência
  de vocabulário citada acima, o fato de `data-section` continuar cru de
  propósito (FR-011), e as observações de fronteira de cada sessão —
  permanece exatamente como cada sessão o deixou; nada disso foi reaberto
  por esta consolidação.

### 22.6 Os gates, com resultado real, terminando no `make verify` verde

- **Console, unidade com cobertura** (`uv run python -m tools.console_gate
  test`), última medição registrada (sessão 13, seção 21.5, idêntica à
  sessão 12): `Test Files 143 passed (143)`, `Tests 2360 passed (2360)`,
  cobertura `Statements 94.35% (6202/6573) / Branches 90.32% (4577/5067) /
  Functions 92.01% (1913/2079) / Lines 96.38% (5729/5944)` — acima do piso
  de 90% nas quatro métricas.
- **Console, `typecheck`/`lint`/`format-check`** — limpos na última rodada de
  cada sessão que tocou console (seções 9.1, 13.9, 14.10, 15.5, 16.8, 19.9,
  20.6, 21.5); a sessão 13 precisou de duas rodadas de `lint` (seis erros
  reais de nulidade sob TypeScript 5.9.3, corrigidos) antes de fechar limpo.
- **Playwright — suíte combinada de fechamento** (sessão 12, seção 20.6,
  contra build de produção real): `transversal-rules.spec.ts` +
  `vocabulary.spec.ts` + `scroll-budget.spec.ts` +
  `vocabulary-defaults.acceptance.spec.ts` juntos → **`52 passed, 9 skipped,
  0 failed`**. Quebra: `scroll-budget.spec.ts` 11/11; `transversal-rules.spec.ts`
  21 passou + 8 pulou legitimamente (7 de orçamento de rolagem já medido em
  outro arquivo, 1 de vocabulário fora desta feature) + 0 falhou;
  `vocabulary-defaults.acceptance.spec.ts` 13 passou + 1 pulou + 0 falhou;
  `vocabulary.spec.ts` 7/7.
- **`vocabulary-defaults.acceptance.spec.ts`, reconfirmado ao vivo nesta
  sessão de consolidação** (não só citado): `13 passed, 1 skipped`, seção
  22.3 acima.
- **Python, suíte completa sem `-x`** — última medição isolada e completa
  registrada (sessão 2, seção 9.2): `11736 passed, 25 skipped, 0 failed em
  615.38s`. Comandos de raio de alcance por pacote tocado, em cada sessão
  seguinte, sempre verdes (seções 9.8, 12.6, 13.9, 15.5, 17.8, 18.7) — nenhum
  deles rodou a coleção inteira de novo isoladamente depois da sessão 2, mas
  cada mudança de produção teve sua vizinhança de teste (identity, gateway,
  persistence, fixtures, security, webhooks) confirmada verde depois de
  cada sessão.
- **`make check-imports`, `make check-constants`, `make check-protocols`,
  `make check-raw-sql`, `make check-credentials`** — todos limpos onde
  rodados (seções 4, 9, 12.2, 12.6, 17.8).
- **Baselines visuais**: quatro capturas afetadas pela correção de
  permissões de T003 (`single-sign-on`, `models-providers`, `notifications`,
  `machine-tokens`, todas `1440-light`) mais a de Members & roles
  (`administration-1440-light`, rejeitada uma vez pelo operador por um
  número de sessão solto sem rótulo — seção 21.1 — e reparada antes da
  segunda captura) foram aceitas fora das sessões que este documento narra
  linha a linha, no commit `c730bfb`. A mensagem do próprio commit confirma
  a mesma história que a seção 21 já registrava: "Every gate was green and
  the acceptance suite passed thirteen of thirteen while that was on screen,
  because the assertion checked that the origin field existed and never
  that the number was gone. Looking at the image is what caught it." — a
  captura, não o teste, foi o que pegou esse defeito especificamente; a
  seção 21.4 é onde a asserção foi depois fortalecida para também pegá-lo.
- **`make verify` completo, o gate final** — `11761 passed, 25 skipped, 16
  warnings in 663.87s`, sem erro de `make`. Como `verify` executa seus
  pré-requisitos em sequência e para no primeiro que falhar, e `test`
  (`pytest`) é o último da lista depois de `console-check`
  (`python -m tools.console_gate all` = `format-check`, `lint`, `typecheck`,
  `test` com cobertura) e de toda a bateria `check-*` — `check-config-parity`,
  `check-display-names`, `check-vendor-sdks`, `check-literals`,
  `check-console-boundary`, `check-integrations`, `check-integration-docs`,
  `check-env-example`, `check-docs`, `check-doc-examples` incluídos — o fato
  de `test` ter terminado e reportado esse número confirma que todos os
  gates anteriores da lista também passaram nesta mesma rodada, não só os
  que as sessões individuais mediram em separado.
- **Não rodado por este agente nesta sessão de consolidação**: `make verify`
  completo (já rodado pelo orquestrador, resultado acima citado e não
  reproduzido de novo — reproduzi só a peça que a tarefa desta sessão pedia
  para julgar, o acceptance spec e seu substituto de componente, seção 22.3);
  `console-visual`/`console-visual-accept` (decisão de baseline não é desta
  sessão, e as que faltavam já foram aceitas no commit `c730bfb`);
  `console-e2e` amplo (a suíte combinada da sessão 12 já cobre as quatro
  specs relevantes desta feature).

## 23. Reparo pontual — a exceção de vocabulário de `/settings/schedules-destinations`, achada pelo verificador independente

Estado abaixo verificado contra o código atual desta árvore de trabalho — cada
linha citada foi aberta, não assumida a partir do que uma sessão anterior
registrou.

### 23.1 O defeito, e a correção à seção 20.2

O verificador independente devolveu **FAIL** neste único ponto: o critério de
sucesso desta feature exige a suíte transversal rodando nas nove páginas de
Settings **sem nenhuma exceção de vocabulário restante**, e
`transversal-rules.spec.ts:148-153` ainda carregava uma para
`/settings/schedules-destinations` — o chip do próprio agendamento em
`console/src/surfaces/schedules.tsx:684` renderizava
`<Badge status={schedule.enabled ? 'healthy' : 'disabled'} />`, o mesmo
anti-padrão `Badge status="healthy"` que esta feature já havia removido dos
dois sites irmãos (pessoa em `principals.tsx`, grupo de token em
`machine-token-groups.tsx`).

**A seção 20.2 estava errada ao classificar esta exceção como "de natureza
diferente" e encerrar o assunto nisso.** A frase "natureza diferente —
chip `HEALTHY` de **schedule**, não de pessoa/token — tela que esta feature
nunca tocou" descreve corretamente que o mecanismo é outro (nenhuma das
tarefas T015/T016/T017 desta feature alcança `schedules.tsx`), mas erra ao
tratar isso como motivo para deixar a exceção em pé: nenhuma outra
especificação da wave é dona deste chip. O verificador confirmou isso
varrendo toda `specs_v6/` por menção a `/settings/schedules-destinations` —
só uma outra feature cita a rota, e seus requisitos cobrem sobreposição de
nome de seção e o vocabulário de status de **credencial**, nunca o chip da
própria linha do agendamento. Deixar a exceção em pé era estreitar o
critério de sucesso para caber no que já tinha sido construído, e por isso
o reparo é desta sessão, não de uma feature futura.

### 23.2 O vermelho, confirmado antes de tocar em `schedules.tsx`

Antes de qualquer mudança de produção, a exceção foi removida de
`EXCEPTIONS` em `transversal-rules.spec.ts` (só ela — a exceção de
`scroll-budget` de `/settings/alert-intake`, de outra regra, ficou intacta)
e a suíte inteira do arquivo foi rodada contra o build parado (`--no-build`,
build da sessão anterior, sem nenhuma mudança em `console/src` até este
ponto):

```
uv run python -m tools.spec_validation browser \
  --feature specs_v6/030-vocabulario-defaults \
  --test console/tests/e2e/transversal-rules.spec.ts --no-build
```

Resultado real, mensagem observada:

```
✘  25 [behaviour] › tests/e2e/transversal-rules.spec.ts:212:5 ›
   /settings/schedules-destinations › carries no banned vocabulary in its
   visible text (269ms)

Error: "HEALTHY" is banned vocabulary, visible on /settings/schedules-destinations

expect(received).toBeNull()

Received: ["HEALTHY"]

  223 |         found,
  224 |         `"${found?.[0] ?? ''}" is banned vocabulary, visible on ${route.path}`,
> 225 |       ).toBeNull();

1 failed
  [behaviour] › tests/e2e/transversal-rules.spec.ts:212:5 › /settings/schedules-destinations › carries no banned vocabulary in its visible text
7 skipped
21 passed (7.3s)
```

Esse vermelho é a prova de que a exceção escondia um defeito vivo, não um já
tratado — exatamente a palavra `HEALTHY`, exatamente na rota nomeada,
nenhuma outra rota afetada.

### 23.3 O reparo

Um componente novo, pequeno e nomeado, seguindo exatamente a forma que
`AccountStateChip` e `TokenGroupStateChip` já usam (booleano de domínio →
papel semântico + forma + rótulo traduzido, nunca a palavra crua da API):

- **`console/src/components/status.tsx:361-390`** — `ScheduleStateChipProps`
  e `ScheduleStateChip`, exportados. Recebe `locale` e `enabled: boolean`
  (o campo `enabled` que `/v1/schedules` já reporta), devolve `success`/
  `filled-circle` quando ligado e `neutral`/`dash` quando desligado, com o
  rótulo vindo de `message(locale, enabled ? 'schedule.state.enabled' :
  'schedule.state.disabled')` — nunca a palavra `healthy` da vocabulário de
  saúde de recurso, que `Badge` usaria crua.
- **`console/src/i18n/en.ts:1460-1463`** — `'schedule.state.enabled':
  'Enabled'`, `'schedule.state.disabled': 'Disabled'`, ao lado de
  `tokenGroup.state.inUse`.
- **`console/src/i18n/pt-BR.ts:1249-1250`** — `'schedule.state.enabled':
  'Ativado'`, `'schedule.state.disabled': 'Desativado'` — o mesmo par que já
  existia em `configuration.value.on`/`configuration.value.off`
  (`pt-BR.ts:1107-1108`) para um booleano ligado/desligado, e a mesma raiz do
  verbo que este próprio arquivo já usa para as ações do agendamento
  (`schedules.enable`: `'Ativar'`, `schedules.disable`: `'Desativar'`,
  `pt-BR.ts:770-773`) — nunca *activar*.
- **`console/src/surfaces/schedules.tsx:8`** — troca do `import { Badge }` por
  `import { ScheduleStateChip }`; era o único uso de `Badge` neste arquivo,
  então a importação antiga foi removida por inteiro, não deixada ociosa.
- **`console/src/surfaces/schedules.tsx:684`** — troca de
  `<Badge status={schedule.enabled ? 'healthy' : 'disabled'} />` por
  `<ScheduleStateChip locale={locale} enabled={schedule.enabled} />`. `locale`
  já era prop desestruturada de `Schedules` (`schedules.tsx:362`, usada
  algumas linhas abaixo por `timestamp(locale, ...)`), então nenhuma outra
  prop precisou subir — nem `ScheduleLabels`
  (`schedules.tsx:213-295`) nem a construção de `labels` em
  `settings/schedules-destinations.tsx:220-276` foram tocadas, porque o novo
  chip lê `locale` direto, exatamente como `AccountStateChip` e
  `TokenGroupStateChip` já fazem nos dois sites irmãos.
- **`console/tests/e2e/transversal-rules.spec.ts:141-146`** — a entrada de
  `/settings/schedules-destinations` + `vocabulary` removida de `EXCEPTIONS`;
  só a entrada de `/settings/alert-intake` + `scroll-budget` (outra regra,
  não tocada por esta sessão) permanece.

Nenhum outro site de renderização do agendamento existia para atualizar: o
único `<Badge .../schedule.enabled` de todo `console/src` era este.

### 23.4 Verde confirmado, contra o comando prescrito, duas vezes

Primeiro, o build de produção foi refeito (mudança em `console/src`) e as
três specs pedidas rodaram juntas:

```
uv run python -m tools.spec_validation browser \
  --feature specs_v6/030-vocabulario-defaults \
  --test console/tests/e2e/transversal-rules.spec.ts \
  --test console/tests/e2e/vocabulary.spec.ts \
  --test console/tests/e2e/vocabulary-defaults.acceptance.spec.ts
```

Resultado real: **42 passed, 8 skipped, 0 failed (11.7s)**, `exit 0`. A linha
que antes falhava agora passa:

```
✓  25 [behaviour] › tests/e2e/transversal-rules.spec.ts:212:5 ›
   /settings/schedules-destinations › carries no banned vocabulary in its
   visible text (243ms)
```

e a mesma rota de single sign-on, que carrega o padrão `Badge
status={state.active ? 'healthy' : 'disabled'}` em `sso-setup.tsx:243` (ver
23.7), também passou sem exceção:
`✓ 4 [behaviour] › .../transversal-rules.spec.ts:212:5 › /settings/single-sign-on › carries no banned vocabulary in its visible text`.

Repetido uma segunda vez contra o mesmo build (`--no-build`, para isolar o
resultado do comando exato de gate em si, sem depender do build ainda estar
quente na primeira chamada): **mesmo resultado, 42 passed, 8 skipped
(12.3s)**, `echo $? → 0`.

Os 8 pulados são os mesmos de antes do reparo (7 rotas de `scroll-budget` já
medidas por `scroll-budget.spec.ts` via `SCROLL_BUDGET_MEASURED_ELSEWHERE`, e
um `test.fixme` legítimo dentro de `vocabulary-defaults.acceptance.spec.ts`
sem relação com este reparo) — nenhum deles é a exceção que foi removida.

### 23.5 Nenhuma outra rota carrega exceção de vocabulário — confirmado

```
grep -n "rule: 'vocabulary'" console/tests/e2e/transversal-rules.spec.ts
```

devolve zero ocorrências: `EXCEPTIONS` (`transversal-rules.spec.ts:141-146`)
hoje contém só a entrada de `scroll-budget` de `/settings/alert-intake`, de
outra regra. As nove rotas de Settings rodam a regra de vocabulário sem
nenhum `test.fixme`.

### 23.6 Achado relacionado, nomeado e não tocado — fora do escopo desta sessão

O mesmo padrão `<Badge status={x ? 'healthy' : 'disabled'} />` continua em
dois outros lugares, achados ao varrer `console/src` por ocorrências
irmãs antes de fechar esta sessão:

- **`console/src/surfaces/sso-setup.tsx:243`** —
  `<Badge status={state.active ? 'healthy' : 'disabled'} />` na página
  `/settings/single-sign-on`, uma das nove páginas de Settings. Hoje isso
  **não** faz a suíte transversal falhar porque, no cenário de fixture usado
  por `--backing mock`, `state.active` é `false` para esta organização — o
  chip renderiza `disabled`, não `healthy`, e o `stateLabel` visível ao lado
  (`sso-setup.tsx:231-236`) já é um dos rótulos traduzidos (`labels.active`/
  `labels.verified`/`labels.notConfigured`/`labels.notVerified`), nunca a
  palavra crua. O `Badge` cru é redundante com esse rótulo e mostraria
  `HEALTHY` no instante em que uma organização com SSO ativo passasse por
  este teste — mas isso é uma segunda instância do mesmo anti-padrão, não
  parte do defeito que este despacho nomeou, e nenhuma especificação da wave
  citou este site. Não tocado.
- **`console/src/surfaces/screens/detectors.tsx:184`** —
  `status={flag(record, 'enabled') ? 'healthy' : 'disabled'}`, mas este
  arquivo não está ligado a nenhuma rota hoje (`grep -rn "screens/detectors"
  console/src` não devolve nenhum import) — não é uma das nove páginas de
  Settings, não é alcançado por `transversal-rules.spec.ts`, e é código morto
  do ponto de vista de roteamento atual. Não tocado.

Nomeado aqui para não ficar escondido, e nenhuma das duas alterações foi
feita: o despacho desta sessão é "console apenas, um componente", e o
critério de sucesso que o motivou (a suíte transversal, sem exceção
restante) já está satisfeito sem tocar em nenhum dos dois — nenhum dos dois
está listado em `EXCEPTIONS`, e nenhum dos dois faz a suíte falhar hoje.

### 23.7 Gates rodados nesta sessão, com resultado real

- `uv run python -m tools.console_gate format-check` — limpo:
  `Checking formatting... All matched files use Prettier code style!`
- `uv run python -m tools.console_gate lint` — limpo, sem saída de violação
  (`eslint . && node scripts/check-css-literals.mjs`, nenhum literal de cor
  introduzido pelo `ScheduleStateChip`, que usa só `ROLE_SKIN`/`ROLE_FILL`
  já declarados).
- `uv run python -m tools.console_gate typecheck` — limpo, `tsc --noEmit`
  sem erro.
- `uv run python -m tools.console_gate test` — **`Test Files 143 passed
  (143)`, `Tests 2360 passed (2360)`**, cobertura `Statements 94.35%
  (6203/6574)`, `Branches 90.33% (4581/5071)`, `Functions 92.01%
  (1914/2080)`, `Lines 96.38% (5730/5945)` — acima do piso de 90% nas
  quatro métricas, e o numerador subiu em 1 statement/linha em relação à
  última medição registrada (seção 22.6: `6202/6573`) porque
  `ScheduleStateChip` é código novo — coberto pelo teste já existente
  `schedules.test.tsx` (`describe('the schedule listing', ...)`, que já
  renderiza um agendamento ligado e um desligado), sem precisar de um teste
  novo.
- `uv run python -m tools.spec_validation browser --feature
  specs_v6/030-vocabulario-defaults --test
  console/tests/e2e/transversal-rules.spec.ts --test
  console/tests/e2e/vocabulary.spec.ts --test
  console/tests/e2e/vocabulary-defaults.acceptance.spec.ts` — resultado na
  seção 23.4: **42 passed, 8 skipped, 0 failed**, rodado duas vezes
  (com build e depois `--no-build` contra o mesmo build), mesmo resultado
  as duas vezes.
- **Não rodado nesta sessão**: `make verify` completo (fora do escopo deste
  reparo pontual — pertence ao orquestrador); `console-visual`/
  `console-visual-accept`/`console-e2e` amplo (o despacho pediu
  explicitamente para não aceitar, sobrescrever ou atualizar nenhuma
  baseline visual, e nenhum comando desta sessão foi capaz de escrever uma —
  só o projeto `behaviour` do Playwright foi usado, nunca `visual`;
  `git status --porcelain -- console/visual` continua vazio depois de tudo,
  e `console/visual/screens.json` continua com `"status": "pending"` para as
  duas entradas de `/settings/schedules-destinations`,
  `signals-schedules-1440-light` e `signals-destinations-1440-light`,
  `screens.json:373-391`, inalterado); `scroll-budget.spec.ts` isolado (fora
  da lista de specs que o despacho pediu, e a exceção de `scroll-budget` que
  sobrou em `EXCEPTIONS` não foi tocada por esta sessão).

### 23.8 Arquivos tocados nesta sessão

- `console/src/components/status.tsx` — `ScheduleStateChipProps` +
  `ScheduleStateChip` adicionados (linhas 361-390).
- `console/src/surfaces/schedules.tsx` — import trocado (linha 8) e uso do
  chip trocado (linha 684).
- `console/src/i18n/en.ts` — duas chaves novas (linhas 1460-1463).
- `console/src/i18n/pt-BR.ts` — duas chaves novas (linhas 1249-1250).
- `console/tests/e2e/transversal-rules.spec.ts` — uma entrada removida de
  `EXCEPTIONS` (era linhas 147-153 antes do reparo; o arquivo hoje tem 7
  linhas a menos).

Nenhum arquivo fora de `console/` foi tocado. Nenhuma baseline visual foi
tocada. Nada foi adicionado ao stage do git — a árvore de trabalho fica só
com os cinco arquivos acima modificados, para o operador revisar e
commitar.

### 23.9 Ledger desta sessão

| Peça | Estado | Detalhe |
|---|---|---|
| Chip do próprio agendamento nunca mostra `HEALTHY` | **FEITO** | `ScheduleStateChip` (`console/src/components/status.tsx:361-390`), usado em `console/src/surfaces/schedules.tsx:684`; vermelho confirmado antes (seção 23.2) e verde confirmado depois (seção 23.4) contra o comando de gate prescrito. |
| Exceção de vocabulário de `/settings/schedules-destinations` removida da suíte transversal | **FEITO** | `console/tests/e2e/transversal-rules.spec.ts:141-146`; zero ocorrências de `rule: 'vocabulary'` restantes no arquivo (seção 23.5). |
| Suíte transversal roda nas nove páginas de Settings sem nenhuma exceção de vocabulário | **FEITO** | Seção 23.4 — `42 passed, 8 skipped, 0 failed`, reproduzido duas vezes. |
| Vocabulário bilíngue, ativar/desativar em pt-BR | **FEITO** | `console/src/i18n/pt-BR.ts:1249-1250` — `Ativado`/`Desativado`, nunca *Activado*; mesma raiz de `schedules.enable`/`schedules.disable` (`pt-BR.ts:770-773`). |
| `sso-setup.tsx:243` e `screens/detectors.tsx:184` — mesmo anti-padrão, dormente | **Fora do escopo desta spec** | Nomeado na seção 23.6; nenhuma especificação da wave cita nenhum dos dois sites, e a suíte transversal já roda verde sem tocar em nenhum deles. Não é uma linha do ledger desta feature — é uma observação para quando (se) uma feature futura tocar essas telas. |


### 23.10 Continuação — o achado da seção 23.6 fechado por instrução do orquestrador

O orquestrador leu a seção 23.6 e pediu explicitamente o fechamento de
`console/src/surfaces/sso-setup.tsx:243`, com uma condição que muda a
classificação: a suíte transversal só passa nesta rota **porque o dado do
cenário de fixture nunca exercita o ramo `state.active === true`** — não
porque o defeito não exista. `console/src/surfaces/screens/detectors.tsx:184`
fica exatamente como estava (não roteado, fora do escopo, instrução explícita
de não tocar).

**Dito sem rodeio, como pedido: este segundo reparo não era exigido pelo
critério de sucesso desta feature** (que já estava satisfeito — seção 23.4,
suíte transversal inteira verde, nenhuma exceção restante). Ele fecha um
defeito latente que a varredura desta própria sessão achou e nomeou —
exatamente o tipo de "tela passa porque o dado não a exercitou" que esta
wave já vem encontrando repetidamente em outras features, e que a seção
23.6 já tinha documentado como dormente, não como inexistente.

### 23.11 A palavra, e por que não é "Enabled"/"Disabled"

O chip antigo (`<Badge status={state.active ? 'healthy' : 'disabled'} />`)
só distinguia dois estados — o mesmo booleano `state.active` que já decide o
primeiro ramo da sentença vizinha (`stateLabel`,
`sso-setup.tsx:232-238`). Manter o chip amarrado a esse mesmo booleano (em
vez de expandi-lo para os quatro estados que a sentença ao lado já cobre —
ativo, testado mas não ativado, não testado, não configurado) é o reparo
mínimo e fiel: a sentença já nomeia essa granularidade mais fina, palavra por
palavra, no mesmo lugar, e duplicá-la no chip seria uma segunda fonte da
mesma informação, não uma correção.

Lida a tela ao redor (`admin.sso.active` = "Active. People sign in through
this provider." / "Ativo. As pessoas entram por este provider." —
`en.ts:1542`, `pt-BR.ts:1321` — e o botão de ativação já fala em "the way
in"/"a forma de entrar"), a palavra que este produto já usa para o estado
verdadeiro é **"Active"/"Ativo"**, não "Enabled"/"Ativado" — vocabulário de
agendamento, não de login único. O oposto curto e simétrico, coerente com o
mesmo adjetivo (não com um particípio de um verbo "ativar/desativar" que
esta tela não usa dessa forma — o botão de ativação chama-se "Make this the
way in"/"Tornar esta a forma de entrar", não "Ativar"), é
**"Inactive"/"Inativo"**.

### 23.12 O reparo

- **`console/src/components/status.tsx:393-422`** — `SsoStateChipProps` +
  `SsoStateChip`, no mesmo formato de `ScheduleStateChip`/`AccountStateChip`/
  `TokenGroupStateChip`: `locale` + `active: boolean` → papel/forma
  resolvidos + rótulo via `message()`, nunca a palavra crua.
- **`console/src/i18n/en.ts:1464-1468`** — `'sso.state.active': 'Active'`,
  `'sso.state.inactive': 'Inactive'`.
- **`console/src/i18n/pt-BR.ts:1251-1252`** — `'sso.state.active': 'Ativo'`,
  `'sso.state.inactive': 'Inativo'`.
- **`console/src/surfaces/sso-setup.tsx`** — `import { Badge }` (linha 8)
  trocado por `import { SsoStateChip }`; `SsoSetupProps` ganhou
  `readonly locale: Locale;` (linha 70, com `import type { Locale } from
  '@/i18n/messages';` novo na linha 9), `SsoSetupFlow` passou a
  desestruturar `locale` (linha 112), e a linha 246 (era 243) trocou
  `<Badge status={state.active ? 'healthy' : 'disabled'} />` por
  `<SsoStateChip locale={locale} active={state.active} />`. Era o único uso
  de `Badge` neste arquivo.
- **`console/src/surfaces/settings/sso.tsx:124`** — `locale={locale}`
  adicionado à chamada de `<SsoSetupFlow>`; `locale` já estava desestruturado
  do `context` na linha 80 desta função, usado nas linhas ao redor
  (`message(locale, 'admin.sso.title')` etc.) — nada mais mudou.

Adicionar `locale` a `SsoSetupProps` é uma mudança mais larga do que a de
`ScheduleStateChip` (que reaproveitou um `locale` que `SchedulesProps` já
carregava): aqui o prop não existia, e virou obrigatório para seguir a mesma
convenção que toda outra `*Props` desta base já segue (`SchedulesProps`,
`AccountStateChipProps`, `TokenGroupStateChipProps`, `StatusChipProps` —
`locale` sempre obrigatório, nunca com valor padrão escondido). Isso por sua
vez obrigou a acrescentar `locale="en"` às 31 chamadas de `<SsoSetupFlow>`
em `console/tests/unit/surfaces/sso-setup.test.tsx` (30 já existentes + a
nova desta sessão) — mudança mecânica, feita por script, cada uma na mesma
indentação da linha `labels={LABELS}` que já existia ao lado.

### 23.13 O vermelho, confirmado antes de qualquer mudança de produção — a peça que faltava

A suíte E2E não prova nada aqui: o backing `mock` mantém `state.active`
falso para esta organização, então o cenário nunca alcança o ramo com o
defeito (exatamente o que o orquestrador apontou). A prova tinha que vir de
um teste que decide o próprio estado inicial — um teste de unidade.

Antes de tocar em qualquer arquivo de produção, um teste novo foi
acrescentado ao fim de `sso-setup.test.tsx` (`describe('vocabulary', ...)`),
renderizando `<SsoSetupFlow ... isActive={true} verified={true} .../>`
(o `Badge` cru ainda em uso) e afirmando que o texto visível do fluxo não
contém a palavra crua:

```
cd console && pnpm exec vitest run tests/unit/surfaces/sso-setup.test.tsx \
  -t "never shows the raw resource-health word"
```

Resultado real, mensagem observada:

```
FAIL  tests/unit/surfaces/sso-setup.test.tsx > vocabulary > never shows the
raw resource-health word once this provider is the way in
AssertionError: expected 'healthyActive. People sign in through…' not to
match /healthy/i

+ Received:
"healthyActive. People sign in through this provider.Configure…"

 ❯ tests/unit/surfaces/sso-setup.test.tsx:763:40
Tests  1 failed | 30 skipped (31)
```

A palavra crua `healthy` sai literalmente como o primeiro texto do fluxo —
antes até da sentença "Active. People sign in through this provider." que já
existia ao lado. Esse é o vermelho que prova que o defeito é real e
alcançável, não hipotético: com o dado certo (`isActive={true}`), o `Badge`
antigo já falhava; só nenhum teste, até esta sessão, tinha os dois — o dado
certo e a asserção certa — juntos.

### 23.14 Verde confirmado, e o vermelho não descartado — fortalecido

Depois do reparo (seção 23.12), o mesmo teste foi reforçado com duas
asserções positivas — o chip nomeado mostrando "Active" quando
`isActive={true}`, e "Inactive" quando `isActive={false}` — e o arquivo
inteiro rodou:

```
cd console && pnpm exec vitest run tests/unit/surfaces/sso-setup.test.tsx
```

Resultado real: **`Test Files 1 passed (1)`, `Tests 32 passed (32)`** (30
testes já existentes + 2 novos). `settings-sso.test.tsx` (o teste da página
que constrói `SsoSetupLabels` e agora também passa `locale`) e
`tests/unit/i18n/catalogue.test.ts` (cobertura bilíngue) rodados juntos em
seguida: **`Test Files 2 passed (2)`, `Tests 20 passed (20)`**.

Depois, contra um build de produção refeito (a mudança alcança
`console/src/surfaces/settings/sso.tsx`, uma tela real), a suíte prescrita
das três specs foi rodada de novo por inteiro:

```
uv run python -m tools.spec_validation browser \
  --feature specs_v6/030-vocabulario-defaults \
  --test console/tests/e2e/transversal-rules.spec.ts \
  --test console/tests/e2e/vocabulary.spec.ts \
  --test console/tests/e2e/vocabulary-defaults.acceptance.spec.ts
```

Resultado real: **`42 passed, 8 skipped, 0 failed`**, `exit 0` — idêntico ao
da seção 23.4, confirmando que passar a exigir `locale` em `SsoSetupProps`
não quebrou a tela real. As duas rotas relevantes, nomeadas:

```
✓  4 [behaviour] › transversal-rules.spec.ts:212:5 › /settings/single-sign-on › carries no banned vocabulary in its visible text (231ms)
✓ 25 [behaviour] › transversal-rules.spec.ts:212:5 › /settings/schedules-destinations › carries no banned vocabulary in its visible text (229ms)
```

Nenhuma falha em nenhum lugar do log.

### 23.15 Gates rodados nesta continuação, com resultado real

- `uv run python -m tools.console_gate typecheck` — limpo, `tsc --noEmit`
  sem erro (confirma que `locale` obrigatório em `SsoSetupProps` está
  correto em toda chamada, produção e teste).
- `uv run python -m tools.console_gate format-check` — limpo.
- `uv run python -m tools.console_gate lint` — **uma rodada pegou um erro
  real**: `@typescript-eslint/no-unnecessary-condition` em
  `sso-setup.test.tsx:794`, porque `flow.textContent ?? ''` era um
  fallback que este código-base não usa (toda outra leitura de
  `.textContent` nos testes desta árvore — `first-run.test.tsx`,
  `node-scope.test.tsx`, `agent.test.tsx` — lê o valor direto, sem `?? ''`).
  Corrigido removendo o fallback (`expect(flow.textContent).not.toMatch(...)`),
  segunda rodada limpa.
- `uv run python -m tools.console_gate test` — **`Test Files 143 passed
  (143)`, `Tests 2362 passed (2362)`** (2360 + 2 novos), cobertura
  `Statements 94.35% (6204/6575)`, `Branches 90.34% (4585/5075)`,
  `Functions 92.02% (1915/2081)`, `Lines 96.38% (5731/5946)` — acima do piso
  nas quatro métricas, sem queda em relação à seção 23.7.
- `spec_validation browser` (as três specs, build refeito) — seção 23.14:
  **42 passed, 8 skipped, 0 failed**, `exit 0`.
- **Não rodado nesta continuação**, pelas mesmas razões da seção 23.7:
  `make verify` completo; `console-visual`/`console-visual-accept`/
  `console-e2e` amplo (nenhum comando desta sessão escreve uma baseline —
  `git status --porcelain -- console/visual` continua vazio depois de tudo).

### 23.16 Arquivos tocados nesta continuação

- `console/src/components/status.tsx` — `SsoStateChipProps` + `SsoStateChip`
  adicionados (linhas 393-422).
- `console/src/surfaces/sso-setup.tsx` — import trocado, `locale` acrescentado
  a `SsoSetupProps` e à desestruturação, uso do chip trocado.
- `console/src/surfaces/settings/sso.tsx` — `locale={locale}` acrescentado à
  chamada de `SsoSetupFlow`.
- `console/src/i18n/en.ts` — duas chaves novas (linhas 1464-1468, incluindo
  comentário).
- `console/src/i18n/pt-BR.ts` — duas chaves novas (linhas 1251-1252).
- `console/tests/unit/surfaces/sso-setup.test.tsx` — `locale="en"`
  acrescentado às 31 chamadas de `<SsoSetupFlow>`; um novo bloco
  `describe('vocabulary', ...)` com duas asserções (estado ativo e estado
  inativo).

Nenhum arquivo fora de `console/` foi tocado. Nenhuma baseline visual foi
tocada. Nada foi adicionado ao stage do git.

### 23.17 Correção à seção 23.6 e à linha de ledger da seção 23.9

A seção 23.6 nomeou `sso-setup.tsx:243` como "achado relacionado, não
tocado" e a tabela da seção 23.9 classificou a linha combinada
`sso-setup.tsx:243` e `screens/detectors.tsx:184` como **Fora do escopo
desta spec**. Isso valia até aqui; a partir desta continuação,
**`sso-setup.tsx:243` está fechado** (seção 23.12) e a classificação
correta para ele é **FEITO**, não mais fora do escopo — a linha antiga não
foi editada (a seção 23.9 fica como o registro do que era verdade quando foi
escrita); a linha abaixo é o que vale agora.

`screens/detectors.tsx:184` continua exatamente como a seção 23.6 descreveu:
não roteado, fora do escopo, e o orquestrador pediu explicitamente para não
tocar.

### 23.18 Ledger desta continuação

| Peça | Estado | Detalhe |
|---|---|---|
| Chip do próprio SSO nunca mostra `HEALTHY`, no estado ativo | **FEITO** | `SsoStateChip` (`console/src/components/status.tsx:393-422`), usado em `console/src/surfaces/sso-setup.tsx:246`; vermelho confirmado por unidade antes (seção 23.13, mensagem observada citada) e verde confirmado depois, por unidade e por navegador contra build de produção (seção 23.14). Não exigido pelo critério de sucesso desta feature — fecha um achado da própria varredura desta sessão (seção 23.10). |
| Palavras do chip são as do próprio SSO, não copiadas do agendamento | **FEITO** | "Active"/"Inactive" (`en.ts:1464-1468`), "Ativo"/"Inativo" (`pt-BR.ts:1251-1252`) — raciocínio na seção 23.11; a sentença de estado mais fina ao lado (`admin.sso.active`/`verified`/`notVerified`/`notConfigured`) não foi duplicada nem alterada. |
| `console/src/surfaces/screens/detectors.tsx:184` | **Fora do escopo desta spec** | Instrução explícita do orquestrador de não tocar; não roteado (seção 23.6), problema de código morto e não desta feature. |


---

## 24. Correção do orquestrador — a classificação de `detectors.tsx` estava errada

Escrito pelo orquestrador depois da segunda passada do `spec-verifier`, que
foi conferir a alegação em vez de aceitá-la.

As seções 23.6, 23.10, 23.17 e 23.18 classificam
`console/src/surfaces/screens/detectors.tsx:184` como **não roteado**, "código
morto", e por isso fora de escopo. **A classificação é factualmente errada.**

O arquivo é alcançável e o produto aponta para ele:

- `console/src/app/(shell)/signals/page.tsx:24-34` — página real; com
  `searchParams.tab === 'observation'` renderiza `SignalsScreen`.
- `console/src/surfaces/screens/signals.tsx:6,22-31` — importa `ObservationTab`
  `from './detectors'` e a chama incondicionalmente.
- `console/src/shell/routes.ts:283-289` — o próprio comentário da área diz que
  `/signals?tab=observation` continua renderizando essa tela.
- `console/src/surfaces/emptiness.ts:69` — um empty-state do produto linka para
  `{ route: '/signals', query: { tab: 'observation' } }`.
- `fixtures/scenarios/populated/detectors.json` — os catorze detectores têm
  `enabled: true`. Não é ramo dormente como o do SSO: é o render **padrão**.

Por que a varredura da sessão de reparo não viu: ela usou
`grep -rn "screens/detectors" console/src`, e o import real é o caminho
relativo `from './detectors'`, que essa string não casa. Falso negativo de uma
checagem inadequada — a mesma família de defeito que esta feature vinha
catalogando.

**Isto não reprova a feature.** `/signals` não é uma das nove páginas de
Settings, e todo critério desta spec é escrito contra esse conjunto. A
classificação correta não é "código morto" e sim **"roteado, alcançável,
linkado pelo produto, e fora do escopo declarado desta feature"** — defeito
real, sem dono, que precisa de tarefa própria.
