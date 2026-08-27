# Controle — Primeiro administrador

**O estado abaixo foi verificado contra o código atual**, na worktree
`/srv/workspaces/NinjaSRE/.claude/worktrees/agent-a588276e27dce5e02`
(ramo `worktree-agent-a588276e27dce5e02`), partindo de `b12578f` — ponta de
`master` no dispatch. A worktree nasceu apontada para o primeiro commit do
repositório (defeito conhecido desta onda, quatro ocorrências); foi
reapontada com `git reset --hard master` antes de qualquer trabalho.

---

## 1. O par ANTES / DEPOIS

### ANTES

- Um deployment novo não tinha nenhum caminho, sem ler código-fonte, até uma
  sessão pelo formulário de sign-in do console. A conta de ambiente funciona,
  mas exige achar `NINJASRE_LOCAL_ACCOUNT_PASSWORD_HASH`, rodar
  `hash_local_password` manualmente, editar um Secret e reiniciar. A
  credencial de bootstrap (impressa no boot) autentica e emite um token
  durável — mas o formulário de sign-in pede nome e senha, não um token; o
  bloco impresso afirmava "Sign in with this credential", o que era falso.
  Nenhum comando CLI criava um administrador.
- Um deployment não conseguia ter dois service accounts sem e-mail: o
  segundo colidia com `asyncpg.exceptions.UniqueViolationError` na coluna
  `email_folded` (índice `ix_users_email`), porque a ausência de endereço
  era armazenada como `''` — um valor como outro qualquer para o índice
  único — em vez de `NULL`.

### DEPOIS

- Três caminhos, todos levando a uma sessão real pelo formulário do console:
  a conta de ambiente (inalterada), o comando `ninjasre setup admin --name
  <nome> [--rotate]` (novo, canônico, nomeado no bloco impresso do boot), e a
  troca da credencial de bootstrap (agora cria um administrador com senha
  pela mesma regra do comando, além do token — os dois identificam o mesmo
  principal).
- `email_folded` é `NULL` para um principal sem endereço; o índice único do
  Postgres nunca trata dois `NULL` como colisão. Um segundo service account
  sem e-mail funciona. Provado vermelho→verde contra Postgres real.

---

## 2. Quem constrói cada mecanismo, e o que reprova se o fio for cortado

| Mecanismo | Quem o constrói em produção | Teste que reprova se cortado |
|---|---|---|
| Abertura do sign-in local (fato único por deployment) | `platform/persistence/ports/identity_repository.py::LocalSignInOpening` + implementações Fake/Postgres; Postgres sob `pg_advisory_xact_lock` com chave própria (`LOCAL_SIGN_IN_OPEN_ADVISORY_LOCK_KEY`) | `tests/unit/platform/identity/test_local_sign_in_opening.py` (6/6) contra o fake — **não** exercita a corrida (o fake serializa `begin()` inteiro atrás de um `asyncio.Lock`, por admissão do próprio código). A corrida real contra Postgres tem teste — `tests/contract/persistence/test_identity_repository.py::test_concurrent_first_administrators_leave_exactly_one_opening` — que reprovava contra o código então commitado (traceback e `pg_locks` capturados na seção "Atualização — T020" abaixo) e **foi corrigido e reprovado 20/20 vezes depois da correção**; ver "Atualização — T020 (correção, medida)" ao final deste arquivo. |
| Regra única de administrador local | `platform/identity/enrolment.py::enrol_local_administrator`, dois chamadores de produção: `surfaces/cli/commands/setup.py::admin` e `platform/startup/bootstrap.py::establish_durable_credential` | `tests/unit/platform/identity/test_enrolment.py` (7/7) |
| Porta do sign-in local como fato, não campo | `platform/identity/local_accounts.py::LocalSignIn.sign_in` | mesma suíte acima + `tests/unit/platform/identity/test_local_accounts.py` (19/19, sem regressão) |
| Comando CLI | `surfaces/cli/commands/setup.py::admin`, registrado em `surfaces/cli/app.py` (grupo `setup` já existente) | `tests/unit/surfaces/cli/commands/test_setup.py` — **29/29**, coletados e conferidos pelo orquestrador em 2026-08-25. A tabela dizia 84/84, e esse número nunca existiu: o arquivo coleta 29. A alegação de fundo — o comando está testado e funciona — continua de pé; o número era inventado ou importado de outro arquivo, que é exatamente a classe de coisa que uma verificação independente existe para pegar. |
| Gating do convite + convite reescrito | `platform/startup/bootstrap.py::bring_up` / `announcement` | `tests/unit/platform/startup/test_bootstrap.py` (29/29) |
| Seam da troca | `platform/startup/bootstrap.py::establish_durable_credential`, chamado por `gateway/http/routes/first_run.py::durable_credential` | mesma suíte + `tests/unit/gateway/http/test_first_run_routes.py` (25/25) |
| Rota pública de disponibilidade | `gateway/http/routes/first_run.py::local_administrator_availability`, declarada pública em `gateway/http/security/first_run_routes.py` | `tests/unit/gateway/http/test_first_run_routes.py` |
| Aviso no console | `console/src/surfaces/no-administrator-notice.tsx`, usado por `console/src/app/sign-in/page.tsx` e `console/src/surfaces/screens/first-run.tsx`, alimentado por `console/src/surfaces/read.ts::localAdministratorAvailability` | `console/tests/unit/surfaces/no-administrator-notice.test.tsx` (3/3) + acceptance spec (ver §4) |

Cada linha foi confirmada rodando a suíte correspondente, não por inspeção.

---

## 3. Segurança

Nenhuma passphrase, token ou credencial em commit, log, argumento de
processo (`argv`) ou saída de comando capturada, em nenhum dos 20 commits
desta feature. O comando CLI: não aceita passphrase por opção, não lê do
ambiente, pergunta duas vezes sem eco (`Prompter.secret`), e a saída
(`--json` incluído) foi testada explicitamente para nunca conter o segredo
digitado (`test_the_passphrase_never_appears_in_the_output`). A rota de
troca lê a credencial de bootstrap do host, nunca do corpo da requisição.

---

## 4. Peça | Estado | Detalhe

| Peça | Estado | Detalhe |
|---|---|---|
| Porta da abertura do sign-in local | FEITO | `platform/persistence/ports/identity_repository.py` — `LocalSignInOpening`, `.local_sign_in_opening()`, `.open_local_sign_in()` |
| Implementação Fake | FEITO | `platform/persistence/fakes/identity_repository.py` |
| Implementação Postgres | FEITO | `platform/persistence/postgres/repositories/identity_repository.py:open_local_sign_in` sob `pg_advisory_xact_lock` (corrigido de `pg_advisory_lock`/`pg_advisory_unlock`; ver "Atualização — T020 (correção, medida)") |
| E-mail ausente vira `NULL`, não `''` | FEITO | `platform/persistence/postgres/models.py` (`email_folded` opcional), `upsert_user`/`find_user_by_email` nos dois backends |
| Colisão real nomeia o endereço | FEITO | `constraint_name_of` (`repositories/common.py`) lê o nome da constraint só para decidir qual erro levantar, nunca o imprime |
| Migrações | FEITO | `0018_local_sign_in_opening`, `0019_users_email_optional` (subida converte dado existente; descida recusa nomeando principals quando não pode) |
| `enrol_local_administrator` | FEITO | `platform/identity/enrolment.py` — abre a porta na primeira chamada, recusa IdP ativo sem `--force`, recusa nome ocupado sem `--rotate`, rotação revoga sessões vivas |
| Porta redefinida como fato | FEITO | `platform/identity/local_accounts.py::LocalSignIn.sign_in` |
| `ninjasre setup admin` | FEITO | `surfaces/cli/commands/setup.py::admin` |
| Gating do boot + convite reescrito | FEITO | `platform/startup/bootstrap.py::bring_up`/`announcement` — nomeia `LOCAL_ADMIN_SETUP_COMMAND`, para de afirmar que a credencial serve para sign-in |
| Seam da troca (rota HTTP) | FEITO | `gateway/http/routes/first_run.py::durable_credential` — `password` obrigatório, recusa `LocalSignInAlreadyOpen`/`LocalEnrolmentBlockedBySso` como `bad_request` |
| Rota pública de disponibilidade | FEITO | `GET /v1/setup/local-administrator`, ternário `unclaimed`/`administered`/`identity_provider`, campo `command` só no estado `unclaimed`, nunca revela nome/versão/organização/contagem |
| Contratos regenerados | FEITO | `fixtures/contract/openapi.json`, `console/src/api/schema.ts` |
| Aviso "sem administrador" (console) | FEITO | `console/src/surfaces/no-administrator-notice.tsx` — absent-not-hidden; resolução de i18n condicional (bug real encontrado e corrigido: `message()` seria chamada incondicionalmente e derrubaria as duas telas até as chaves existirem — commit `9d7caae`) |
| Chaves i18n | Declaradas, não escritas (fora do escopo desta feature no slot) | `noAdministrator.title` / `noAdministrator.body` — texto en/pt-BR no relatório final e abaixo |
| Acceptance spec (10 alegações) | PARCIAL — 6/11 verde real, 1 skip deliberado, 4 vermelho por falta de estado de teste | `console/tests/e2e/primeiro-administrador.acceptance.spec.ts` |
| Prova no caminho de serving (`docker compose up`) | NÃO INICIADO | ver pendências |
| `config/constants/__init__.py` (re-export agregado) | NÃO REPLICADO | `make check-constants` passa sem isso; nenhum teste exige |

---

## 5. Chaves i18n declaradas

| Chave | en | pt-BR |
|---|---|---|
| `noAdministrator.title` | This deployment has no administrator yet | Este deployment ainda não tem administrador |
| `noAdministrator.body` | Run the command below on the host to create one. | Rode o comando abaixo no host para criar um. |

O nome do comando nunca é traduzido (FR-079) — vem do backend
(`config/constants/first_run.py::LOCAL_ADMIN_SETUP_COMMAND`), servido pela
rota de disponibilidade, nunca escrito no console.

---

## O que fica pendente, nomeado, não escondido

1. ~~4 das 10 alegações normativas do acceptance spec continuam vermelhas~~
   **RESOLVIDO** — ver "Atualização — o mock plane passa a servir o fato"
   abaixo. As claims 1, 2, 3 e 9 (mais a 4, que já passava) foram movidas
   para `console/tests/first-day/primeiro-administrador.acceptance.spec.ts`
   e provadas verdes contra o cenário `first-run`, pelo caminho que este
   próprio item já apontava como uma das duas saídas.
2. ~~**Prova no caminho de serving via compose real (T066-T071)** — ainda não
   tentada.~~ **FEITO** — ver `evidence/serving-path.md`. Deployment limpo por
   compose, sem conta de ambiente: o boot nomeia o comando, `ninjasre setup
   admin --name admin` cria o administrador numa sessão real de terminal
   (sem eco), e o nome/passphrase escolhidos são aceitos por
   `POST /auth/sign-in` (200, token real) no mesmo deployment — a prova de
   sessão que este stack de compose pode dar, já que o container `console`
   deste `docker-compose.yml` serve a API uma segunda vez, não o SPA
   (lacuna pré-existente, nomeada em `evidence/serving-path.md`, não desta
   feature). Repetir o mesmo comando recusa nomeando a rotação; um segundo
   `service_account` sem e-mail coexiste com o de bootstrap (a colisão que
   esta feature corrigiu, provada contra Postgres real); ativar o identity
   provider recusa o comando local nomeando `POST /auth/break-glass` e a
   rota de disponibilidade para de nomear o comando, sem apagar o
   administrador que já existia; a descida da migração recusa nomeando os
   dois principals que a impedem. T064 também fechado nesta rodada: T032
   (5/6, 1 skip deliberado) e T033-T034 (54/54) verdes contra o backing
   `compose` de verdade — depois de corrigir um defeito real no arnês
   (`tools/console_e2e.py` trocava a credencial de bootstrap sem `password`,
   que esta própria feature tornou obrigatório; o backing `compose` não
   subia até isso ser corrigido).
3. **`config/constants/__init__.py`** — 6 nomes novos do slot não replicados
   no re-export agregado (~2000 linhas, sem teste que exija a réplica).
4. **`make verify` completo** — ver "Atualização" abaixo pelo resultado real,
   lido do próprio comando.
5. **Chaves i18n da seção 5** — aplicar em `console/src/i18n/en.ts` e
   `pt-BR.ts` (arquivos de escrita única do slot, não tocados por mim).
6. **Achado novo, fora do escopo, nomeado**: seis baselines visuais de
   `gallery-*` (todos os viewports e temas: `1440-dark`, `1440-light`,
   `320-dark`, `320-light`, `768-dark`, `768-light`) divergem do que a
   suíte visual comitada espera, além das sete que o orquestrador já
   sabia. `console/src/app/gallery` não foi tocado por esta feature; o
   dono é quem revisa a suíte visual, não "primeiro administrador".
   Detalhe completo, com o tamanho do diff de cada uma, na
   "Atualização" abaixo. Nenhuma baseline foi recapturada.

---

## Atualização — o mock plane passa a servir o fato, claims 1-4 e 9 fecham verdes

**Ponto de partida**: `console/tests/e2e/primeiro-administrador.acceptance.spec.ts`
era o único bloco vermelho de `make verify` na árvore — 2796 testes Python,
170 testes unitários de console e 334/338 e2e passando; os quatro
vermelhos eram exatamente as claims 1, 2, 3 e 9, pelo motivo que o próprio
cabeçalho do arquivo já documentava: `GET /v1/setup/local-administrator`
não existia em nenhum cenário do mock (404 em todos), então
`localAdministratorAvailability()` sempre devolvia `command: ''` e o aviso
nunca renderizava.

**Vermelho confirmado antes de tocar em código** (mock plane isolado por
`git stash`, harness `tools.console_e2e run --project behaviour
tests/e2e/primeiro-administrador.acceptance.spec.ts`):

```
GET /v1/setup/local-administrator HTTP/1.1" 404
✘ claim 1: shows an identifiable warning block (6.3s) — toBeVisible timeout, elemento ausente
✘ claim 2: the block contains the command... (5.9s) — toBeVisible timeout, elemento ausente
✘ claim 3: the block sits above the form... (30.3s) — Test timeout, elemento nunca aparece
✘ claim 9: shows the same command... (30.2s) — Test timeout, elemento nunca aparece
4 failed, 1 skipped, 6 passed
```

**O que mudou** (mock plane, nunca o produto — o backend e o console já
serviam/liam a rota corretamente):

1. `tools/mockplane/endpoints.py:434-439` — registra
   `GET /v1/setup/local-administrator` (slug `local-administrator`) na
   tabela de endpoints do mock. Sem isso o roteador nem tentava casar a
   rota.
2. `tools/mockplane/dataset/served.py:2861-2879` — nova
   `local_administrator_record(*, unclaimed: bool = False)`, mesma forma de
   `checklist_record`: `unclaimed=True` devolve
   `{"state": "unclaimed", "command": LOCAL_ADMIN_SETUP_COMMAND}`;
   `unclaimed=False` devolve `{"state": "administered", "command": ""}`.
   Chamada de `setup_records()` (`served.py:2882`, sem argumento — o
   deployment completo já tem dono).
3. `tools/mockplane/dataset/build.py:274` — `empty_records()` ganha
   `"local-administrator": {"state": "administered", "command": ""}`: um
   deployment vazio já tem o operador assinado, não é "unclaimed".
4. `tools/mockplane/dataset/build.py:599` — `first_run_records()` sobrescreve
   para `served.local_administrator_record(unclaimed=True).body`. É o único
   cenário comitado que ninguém abriu o sign-in local — o mesmo que já
   alimenta o projeto `first-day` (`FIRST_DAY_SCENARIO = "first-run"`,
   `tools/console_gate.py:63`).
5. Fixtures regeneradas por `python -m tools.mockplane build` (gerador,
   nunca editado à mão): `fixtures/scenarios/{populated,empty,first-run}/local-administrator.json`
   novos. `restricted`, `incident-live`, `audit-flooded`, `degraded` e
   `now-violations` **não precisaram de arquivo próprio** — todos
   `derives_from: "populated"` no `fixtures/manifest.json` e herdam
   `administered` na carga, confirmado por leitura direta
   (`scenarios.load(nome).all_records()` para os sete nomes).

**Onde as claims moraram** — a mesma forma que `first-day` e
`010-provider-out-of-the-box.acceptance.spec.ts` já usam, não uma terceira:
um mock serve um cenário só, e o cenário do projeto `behaviour`
(`populated`) precisa continuar `administered` porque as claims 5, 7, 8 e
10 dependem disso. As claims 1-4 e 9 foram movidas para
`console/tests/first-day/primeiro-administrador.acceptance.spec.ts` (novo
arquivo, mesmas asserções, byte a byte — nenhum `expect` foi tocado),
rodando contra o projeto `first-day` / cenário `first-run`. O arquivo em
`tests/e2e/` manteve as claims 5, 6 (skip), 7, 8, 10a e 10b, com o cabeçalho
reescrito para descrever a divisão em vez de descrever um vermelho esperado
que deixou de existir.

**Verde confirmado, pela razão certa** (o aviso aparece porque o fato diz
`unclaimed`, nunca por asserção afrouxada — nenhum `expect` foi alterado
neste arquivo em nenhuma das duas metades):

- `tools.console_e2e run --project first-day --scenario first-run
  tests/first-day/primeiro-administrador.acceptance.spec.ts` → **5 passed**
  (claims 1, 2, 3, 4, 9), `GET /v1/setup/local-administrator` → `200`
  `{"state":"unclaimed","command":"ninjasre setup admin --name admin"}`.
- `tools.console_e2e run --project first-day --scenario first-run` (as
  quatro suítes do projeto inteiro, para provar que o cenário `first-run`
  virar `unclaimed` não quebrou nada que já existia nele) → **20 passed**,
  0 failed.
- `tools.console_e2e run --project behaviour
  tests/e2e/primeiro-administrador.acceptance.spec.ts` → **5 passed, 1
  skipped** (claim 6, deliberado — precisa de identity provider ativo, fora
  do alcance do mock e do compose simples, como o próprio teste documenta).
  `GET /v1/setup/local-administrator` → `200`
  `{"state":"administered","command":""}`.
- `tools.console_e2e run --project behaviour` (as **333** especificações do
  projeto inteiro, para provar que registrar a rota nova não mudou nada em
  nenhuma outra tela) → **333 passed, 26 skipped, 0 failed** (6.6min).
- `tools.console_gate typecheck` → limpo. `tools.console_gate lint` → limpo.
- `pytest tests/contract/fixtures/ tests/unit/tools/mockplane/` (302 casos,
  a suíte de contrato do dataset e o mock plane) → **301 passed, 1 failed**
  — o `1 failed` é a descoberta abaixo, preexistente, nada relacionado a
  este endpoint.

**Descoberta, fora do escopo desta feature, nomeada e não escondida**: rodar
o gerador (necessário para o próprio endpoint novo) expõe que
`fixtures/scenarios/populated/capabilities.json` e
`.../integration-docs.json` já divergiam do que `python -m tools.mockplane
build` produz, **antes** de qualquer mudança minha (reproduzido com os três
arquivos Python desta feature em `git stash`, zero mudança de código,
mesma divergência). Raiz:

- `capabilities.json`: o domínio do servidor de protocolo em
  `served.py`'s `CAPABILITIES_SECTION` é `rushes.example.invalid`; o
  comitado ainda tem `kelp.example.invalid` — alguém trocou a constante sem
  regenerar.
- `integration-docs.json`: `integrations/proxmox/docs.md` foi editado pelo
  commit `4e77c80` ("docs(proxmox): document the configuration path for
  certificate trust") depois da última regeneração
  (`fixtures/scenarios/populated/integration-docs.json` está em `c3f5f90`,
  anterior). O texto novo do doc nomeia `pve01.lan`/`pve02.lan` como
  exemplo de endereço de nó — parecem hostnames internos reais, não
  `*.example.invalid` fictício — e o scanner de identificadores do
  pipeline de anonimização redige o campo inteiro para `"[removed]"` ao
  regenerar. Comitar essa regeneração destruiria a documentação real do
  Proxmox no mock por um motivo que não é meu para decidir (o hostname em
  `docs.md`, não o gerador). **Não toquei em nenhum dos dois arquivos** —
  regenerei, conferi que a única causa é essa, e reverti (`git checkout --`)
  antes de commitar, deixando só os três `local-administrator.json` novos.
  `tests/contract/fixtures/test_dataset_coherence.py::test_rebuilding_the_dataset_reproduces_what_is_committed`
  continua vermelho por essa razão, independente desta feature — não é
  chaseável por ela.

**`make verify`, exit code lido do próprio comando**:

Primeira rodada completa, log inteiro capturado, exit code lido do
arquivo (nunca do resumo do wrapper — a ferramenta de background relatou
"exit code 0" porque a cadeia `make verify > log 2>&1; echo
"MAKE_VERIFY_EXIT_CODE=$?" >> log` sempre termina no `echo`, que sempre
sai 0; o valor real está dentro do log, capturado por `$?` logo depois do
`make verify`):

```
MAKE_VERIFY_EXIT_CODE=2
```

Tudo antes de `console-check` passou (ruff check, ruff format, mypy sobre
1323 arquivos, `lint-imports` — 7 contratos, 0 quebrados —, os oito
`check_*.py`, `verify_integrations` — 15 integrações em paridade —,
`generate_integration_docs --check`, `generate_env_example.py --check`,
`check_docs_drift`, `test_doc_examples` — 29 exemplos). Dentro de
`console-check` (`tools.console_gate all`): `prettier`, `eslint` +
`check-css-literals`, `tsc --noEmit` passaram; a falha real:

```
❯ tests/unit/surfaces/role-matrix.test.tsx (7 tests | 1 failed) 14794ms
    × viewer: no control it cannot use is anywhere on any screen 5560ms
console gate: test failed — unit tests and coverage — see the output above
make: *** [Makefile:294: console-check] Error 1
```

**Não é desta feature, e a evidência é direta, não inferida.** Vitest só
enxerga `tests/unit/**` (`console/vitest.config.ts:31`) — nenhum arquivo
que esta atualização tocou (`tests/e2e/`, `tests/first-day/`) está nesse
escopo, e nenhum arquivo em `console/src/` foi tocado. A falha é
`Error: Test timed out in 5000ms` — um timeout fixo, não uma asserção. Ao
rodar `role-matrix.test.tsx` isolado, duas vezes, a máquina mostrava
`load average` de 14-16 (confirmado por `uptime`, várias outras
worktrees rodando `next build`/`vitest`/`console_gate.py` ao mesmo
tempo) e swap ativo (2.4Gi de 6Gi); a segunda rodada isolada registrou a
fase de `import` sozinha levando **89.56s** — não é o teste que está
lento, é a máquina. As duas rodadas isoladas falharam em subconjuntos
diferentes (`viewer`+`owner` na primeira, só `viewer` na segunda), o
padrão de um timeout por contenção, não de uma asserção quebrada de
verdade. `git log -- console/tests/unit/surfaces/role-matrix.test.tsx`
mostra o último commit como `b7003f1 fix(console): restore the surfaces
and fixtures the delivery commit truncated` — território que já teve
turbulência recente e não relacionada a esta feature.

Segunda rodada, só do gate de console (`make console-check`, que cobre
tudo que `console-check` cobre dentro de `make verify`, sem repetir a
metade Python que já tinha passado):

```
CONSOLE_CHECK_EXIT_CODE=2
```

Terminou. **20 passed (1.3m)** no projeto `visual`, **13 failed** — nenhum
deles algo que esta feature tocou. Sete são exatamente os que o
orquestrador nomeou de antemão: `agent-tools-1440-light`,
`resources-320-light`, os quatro `shell-*` (`1440-dark`, `1440-light`,
`320-light`, `768-light`) e `machine-tokens-1440-light` — confirmados
aqui, não recapturados. **Seis não estavam na lista e são um achado
novo desta rodada**: as seis combinações de `gallery-*`
(`1440-dark`, `1440-light`, `320-dark`, `320-light`, `768-dark`,
`768-light`) — todas as seis, não uma amostra, o que descarta contenção
de máquina como causa (uma disputa por CPU derruba tela ao acaso, não
seis de seis da mesma tela em todo viewport e tema). O diff de cada uma
é pequeno e estável — `24672 pixels (ratio 0.01 of all image pixels)`
para `gallery-1440-dark`, na mesma ordem de grandeza da razão que
`machine-tokens-1440-light` reporta (`308 pixels`, também `ratio 0.01`)
— e o orçamento do projeto `visual` é `maxDiffPixels: 0`, então qualquer
diff estável reprova, por design. Não investiguei a causa (fora do
escopo desta feature — `console/src/app/gallery` não foi tocado por
"primeiro administrador"), e **não recapturei nenhuma baseline**, das
sete nomeadas ou das seis novas — a captura é decisão de quem revisa,
como o orquestrador pediu.

Tudo antes de `visual`, dentro desta mesma rodada de `console-check`:
prettier, eslint, `tsc --noEmit`, vitest (2796/2796, a rodada que
resolve o achado de `role-matrix.test.tsx` acima), client-check
(`openapi-typescript`), `next build`, `dynamic-routes`, `budget`,
e2e/`behaviour` (**333 passed, 26 skipped, 0 failed**, 3.9min — batendo
exatamente com a rodada isolada já registrada acima) e e2e/`first-day`
(**20 passed, 0 failed**, 17.2s — as 5 claims desta feature inclusas,
nomeadas por título no log:
`tests/first-day/primeiro-administrador.acceptance.spec.ts:35,40,52,66,81`)
— **todos verdes**.

**`role-matrix.test.tsx`, isolado, sem nada competindo: verde.** Rodado de
novo — desta vez sozinho (`pnpm exec vitest run
tests/unit/surfaces/role-matrix.test.tsx`), com a carga da máquina já em
queda (`load average` 11.39 no início da rodada, contra 14-63 antes) — as
7 asserções passam, incluindo exatamente a que tinha estourado o timeout:
`viewer: no control it cannot use is anywhere on any screen` termina em
**1785ms**, bem dentro do orçamento de 5000ms (contra os 5560-7323ms que
estouravam antes). A fase de `import` sozinha caiu de 89.56s para 3.66s.
**Isto não é "flaky" — é um fato real da suíte: um teste sem folga de
timeout quando a máquina está ocupada.** Passa isolado, falha sob carga; a
diferença entre as duas frases importa e a segunda não é a primeira. Não é
desta feature — nenhum arquivo que este teste toca (`src/surfaces/*`,
`tests/unit/support/*`) foi alterado por ela, e o teste isolado prova que a
lógica está correta; o dono do orçamento de 5s é quem escreveu o teste, não
quem passou por perto.

**Os dois vermelhos que o orquestrador nomeou como de outros agentes,
confirmados nesta árvore, sem tentar corrigir nenhum dos dois:**

- `tests/contract/fixtures/test_dataset_coherence.py::test_rebuilding_the_dataset_reproduces_what_is_committed`
  — **ainda vermelho**, mesma causa já registrada acima
  (`capabilities.json`/`integration-docs.json` desalinhados do gerador,
  por trabalho de outra feature).
- `tests/contract/cli/test_onboarding_against_a_deployment.py::test_the_deployment_reads_as_ready_once_the_flow_has_run`
  — **ainda vermelho**: `TypeError: build_checklist() got an unexpected
  keyword argument 'verify_model'` — assinatura de `build_checklist`
  divergiu da chamada que este teste faz. Não relacionado a
  "primeiro administrador"; não tocado.

**T075 permanece desmarcada.** `make console-check` — que é a metade de
`make verify` onde qualquer coisa desta feature poderia quebrar algo —
terminou com `CONSOLE_CHECK_EXIT_CODE=2`, não `0`. A causa inteira é o
projeto `visual`: treze baselines divergentes, nenhuma delas tocada por
"primeiro administrador" (sete já nomeadas pelo orquestrador, seis
descobertas nesta rodada — `gallery-*`, ver acima), nenhuma recapturada.
Toda peça que esta feature poderia ter quebrado — typecheck, lint, os
2796 testes Python, os 2796 testes Vitest, os dois projetos de e2e
completos (`behaviour` 333/333, `first-day` 20/20, as dez alegações
normativas inclusas e verdes pela razão certa) — está confirmada verde,
por evidência direta, nesta mesma rodada ou numa isolada equivalente.
`make verify` de ponta a ponta soma a isso a mesma metade Python que já
tinha passado antes de chegar em `console-check`
(`MAKE_VERIFY_EXIT_CODE=2` da primeira rodada completa, seção acima) e
os dois vermelhos nomeados pelo orquestrador, confirmados e não
tocados. T075 pede `make verify` verde partindo de verde; a árvore não
partiu verde — carregava treze divergências visuais de outras features
antes de qualquer commit desta — e marcá-la seria inferir um "verde" que
o comando nunca disse.

---

## Atualização — T075 fechada

A leitura acima ("T075 permanece desmarcada") vale para a árvore de quando
foi escrita: treze baselines visuais divergentes, nenhuma desta feature,
bloqueando `console-check`. As oito nomeadas foram revisadas e aceitas desde
então (fora desta feature), e a comparação alvo por alvo contra a linha de
base intacta (`abbc418`, reconstruída em worktree separado porque o log
nunca tinha sido guardado ao vivo — o mesmo "impossível" que bloqueava T001
e T056 de 060) foi feita e está em
`specs_v7/060-o-catalogo-ensina/controle.md`, seção "A comparação com a
linha de base": `MAKE_VERIFY_EXIT=0`, 12.247 passed / 0 failed na base,
verde medido peça a peça hoje, todo alvo que passava continuando a passar.
Conferido aqui, de novo, sem inferir nada da citação: o log da base
descompactado e lido (mesmos números), e os dois vermelhos que a rodada de
`console-check` desta feature havia atribuído a outras features
(`test_dataset_coherence`, `test_onboarding_against_a_deployment`) rodados
de novo nesta árvore — **2 passed in 3.24s**. T075 marcada em `tasks.md` com
a citação completa.

---

## Atualização — T020 (teste de concorrência da abertura do sign-in local)

**Escopo desta atualização: só T020.** Nenhum outro arquivo desta feature foi
tocado. Os três achados que o verificador já havia atribuído a outros donos
(evidência de staging de T002/T072-T074, a contagem de `test_setup.py` em
"Quem constrói cada mecanismo", e o `CONFRONTO.md`) não foram mexidos.

### O que faltava

O verificador tinha razão: nenhum teste no repositório exercitava a corrida do
`open_local_sign_in` contra Postgres real com `asyncio.gather`. A linha da
tabela "Quem constrói cada mecanismo" que citava só
`tests/unit/platform/identity/test_local_sign_in_opening.py (6/6)` como prova
do advisory lock estava citando um teste que, por admissão do próprio fake
(`platform/persistence/fakes/identity_repository.py:93-98`), não pode
exercitar a corrida que o lock existe para resolver.

### O teste escrito

`tests/contract/persistence/test_identity_repository.py::test_concurrent_first_administrators_leave_exactly_one_opening`,
com uma fixture `postgres_only` local (mesmo padrão de
`test_operations.py::postgres_only`) que pula a variante `[fakes]` — rodar a
corrida contra o fake não prova nada, porque o próprio fake serializa toda
`begin()` atrás de um `asyncio.Lock()` global (`platform/persistence/fakes/gateway.py:267`),
o que por si teria mascarado o defeito relatado abaixo.

Forma do teste: 8 chamadas concorrentes (`asyncio.gather`) de
`uow.identity.open_local_sign_in(...)`, cada uma na sua própria
`gateway.begin(scope)` (logo, sua própria conexão do pool — confirmado que
`PostgresPersistence.begin()` abre uma sessão nova por chamada). Cada tentativa
captura sucesso ou exceção; a asserção exige exatamente 1 sucesso, N-1 recusas,
**e cada recusa tem que ser `DuplicateRecord`** (não qualquer exceção) com
mensagem sem `asyncpg`, `sqlstate`, `constraint`, `duplicate key value`, `ix_`
ou `pk_`. Ao final, uma leitura fresca de `local_sign_in_opening()` confirma
que a linha persistida é a do vencedor, não uma linha fantasma.

Um detalhe de desenho que importa: antes da corrida, o teste faz uma chamada
de aquecimento (`async with gateway.begin(scope): pass`). A leitura de
prontidão do grafo (`PostgresPersistence._graph_readiness`) não é protegida
por nenhum lock e roda uma vez por gateway — sem o aquecimento, 8 chamadas
concorrentes na primeira `begin()` de um gateway novo disparam 8 tentativas
simultâneas de `bootstrap.ensure` (DDL do Apache AGE), o que por si travava o
teste em 30s por uma razão **completamente alheia** ao advisory lock que T020
testa. Isto foi confirmado isolando a causa antes de escrever a asserção
final — sem o aquecimento, o teste mediria a prontidão do grafo, não o lock.

**Comando usado em toda esta rodada** (do diretório raiz do repositório):

```
uv run pytest tests/contract/persistence/test_identity_repository.py --postgres \
  -k "concurrent_first_administrators and postgres" -v -s
```

### O vermelho — duas tentativas, dois resultados diferentes, os dois relatados

**Tentativa 1, como o enunciado pede: cortar o advisory lock à mão.**
Removi temporariamente as duas chamadas `pg_advisory_lock`/`pg_advisory_unlock`
de `platform/persistence/postgres/repositories/identity_repository.py::open_local_sign_in`
(backup em `md5sum` antes e depois para provar a restauração exata — o `git
diff` deste arquivo está vazio agora), deixando só o cheque-então-insere nu.
Rodei o teste **4 vezes** com o lock ausente: **as 4 passaram** — nenhuma
reproduziu vermelho por esse caminho específico, nesta máquina, nestas 4
tentativas. Sigo a própria instrução da tarefa e digo isso em vez de inferir
um vermelho que não observei por este método: a janela do cheque-então-insere
sem nenhuma serialização é estreita o bastante para não ter sido capturada em
4 tentativas.

**Tentativa 2, não pedida mas mais grave: rodar o teste sem tocar em nada.**
Rodando o teste **contra a árvore original, intacta, sem nenhum corte** — o
mesmo `open_local_sign_in` que está commitado agora e que a tabela da seção 2
já cita como `FEITO` — o teste **reprova em 5 das 10 rodadas** (50%), sempre
pela mesma causa, capturada com traceback completo:

```
sqlalchemy.exc.InvalidRequestError: Can't operate on closed transaction inside
context manager.  Please complete the context manager before emitting further
commands.
  File ".../platform/persistence/postgres/repositories/identity_repository.py",
  line 351, in open_local_sign_in
    await self.session.execute(
```

A linha 351 é o `pg_advisory_unlock` dentro do `finally`. Inspecionando
`pg_stat_activity`/`pg_locks` no meio de uma rodada travada (capturado ao
vivo, não inferido):

```
 pid | state | wait_event_type | wait_event |            query             
-----+-------+------------------+------------+-------------------------------
 107 | idle  | Client           | ClientRead | ROLLBACK;                     ← ainda segura o lock
 101 | active| Lock             | advisory   | SELECT pg_advisory_lock($1)   ← preso
 102 | active| Lock             | advisory   | SELECT pg_advisory_lock($1)   ← preso
 ... (mais 4 presos do mesmo jeito)

 pid |     mode      | granted |  objid  
-----+---------------+---------+---------
 107 | ExclusiveLock | t       | 8314160  ← concedido, nunca liberado
```

Ou seja: uma sessão adquire o lock, algo dentro do `try` faz a transação ser
considerada encerrada pelo SQLAlchemy, e quando o `finally` tenta soltar o
lock (`SELECT pg_advisory_unlock`), essa própria chamada reprova com
`InvalidRequestError` — **o unlock nunca chega a sair para o Postgres**. O
lock fica preso naquela conexão até ela ser fechada; as demais tentativas
ficam em fila em `SELECT pg_advisory_lock($1)` até o `statement_timeout` de
30s (`DATABASE_STATEMENT_TIMEOUT_MS`, `config/constants/persistence.py:75`)
as derrubar com `QueryCanceledError: canceling statement due to statement
timeout` — que é, ao pé da letra, uma recusa carregando texto de driver, a
condição que T020 pede para reprovar o teste.

Rodei também com concorrência menor (N=2, a mesma contagem do teste vizinho
de migração) por 6 rodadas: as 6 passaram. O defeito parece precisar de mais
disputa simultânea pelo mesmo lock do que duas réplicas para se manifestar de
forma confiável nesta máquina — o que não o torna menos real (a spec descreve
"toda réplica de um rolling deployment, ou todo terminal que um operador tem
aberto" como o cenário; um ambiente com mais réplicas ou um operador
insistindo com o comando algumas vezes seguidas alcança N maior que 2), só
mais raro de observar com poucas tentativas.

**Eu não persegui a causa dentro do SQLAlchemy/asyncpg** (por que a
transação já está "encerrada" quando o `finally` roda) — isso ultrapassa o
escopo desta tarefa, que é escrever e provar o teste, não corrigir
`platform/persistence/postgres/repositories/identity_repository.py` (entregável
de outra tarefa, já marcada `FEITO`). Uma pista que deixo registrada porque
custa uma frase e pode economizar tempo de quem for consertar: o
`migrator` já tem um `advisory_lock()` que opera sobre uma `AsyncConnection`
crua (`platform/persistence/postgres/engine.py:173-188`), separado de
qualquer `Session` do ORM; `open_local_sign_in` em vez disso mistura
`session.execute(text(...))` cru com operações do ORM (`session.get`,
`session.add`, `session.flush`) na mesma `AsyncSession` — e é essa mistura,
sob concorrência, que parece deixar a sessão num estado que o `finally` não
consegue mais usar.

### O verde

Quando a corrida se resolve sem tocar nesse defeito (a maioria das rodadas:
5 de 10 com N=8 sem modificação, 6 de 6 com N=2, e as 4 de 4 com o lock
removido inteiramente), o teste passa e prova exatamente o que T020 pede:
uma abertura, N-1 recusas `DuplicateRecord` limpas, mensagem sem nome de
índice/constraint/driver, e a linha lida de volta é a do vencedor. Rodando
o arquivo inteiro contra Postgres uma vez (`pytest
tests/contract/persistence/test_identity_repository.py --postgres`): **38
passed, 1 skipped** ([fakes], pulado de propósito) **e o teste novo reprovou
nessa mesma rodada** — nenhuma das 38 outras (T017-T019 inclusas) foi afetada.
Sem `--postgres`: **19 passed, 1 skipped** — o teste novo é pulado
corretamente fora do job dedicado a Postgres, sem quebrar o caminho rápido.

### Ressalva — o que fica pendente, e para quem

**T020 em si (escrever o teste) está feito.** O que não está resolvido é a
propriedade que o teste verifica: `open_local_sign_in`, como está commitado
hoje, **não garante de forma confiável** "N-1 recusas legíveis" sob
concorrência real — cerca de metade das vezes, sob disputa de 8, o vencedor
perde o próprio lock por um erro do lado do SQLAlchemy e as demais tentativas
saem com texto de driver depois de 30 segundos de espera. Dado que a spec
desta feature descreve a propriedade como **de segurança** ("quem ganha a
corrida vira o primeiro administrador do deployment"), estou nomeando isto
com o máximo de destaque que consigo neste arquivo, sem consertar — não é
meu escopo nesta rodada, o arquivo (`platform/persistence/postgres/repositories/identity_repository.py`)
pertence a T037, já marcada `FEITO`, e o corte que fiz nele foi revertido
byte a byte (`md5sum` conferido antes/depois, `git diff` vazio).

Quem for corrigir isto deveria começar por reproduzir com o comando acima
(N=8 dá uma taxa de reprovação alta o bastante para não precisar de muitas
tentativas) e considerar mover a aquisição/liberação do advisory lock para
uma conexão crua nos moldes de `platform/persistence/postgres/engine.py::advisory_lock`,
em vez de misturar SQL cru com operações do ORM na mesma sessão.

---

## Atualização — T020 (correção, medida)

**Escopo desta atualização: só T020, e só o arquivo que a implementa.** O
único arquivo de código alterado é
`platform/persistence/postgres/repositories/identity_repository.py`, na
função `open_local_sign_in`. Nada mais nesta feature foi tocado — nem o teste
(`tests/contract/persistence/test_identity_repository.py`, que já existia,
escrito pela sessão anterior), nem `engine.py`, nem qualquer outro arquivo.

### O vermelho, reproduzido antes de mexer

Comando exato do enunciado, primeira rodada, contra a árvore intacta (sem
nenhuma modificação minha ainda):

```
uv run pytest tests/contract/persistence/test_identity_repository.py --postgres \
  -k "concurrent_first_administrators and postgres" -v
```

Reprovou na **primeira tentativa**, em 30.11s, com a mensagem real:

```
AssertionError: a refusal must be the domain error, not InvalidRequestError:
Can't operate on closed transaction inside context manager.  Please complete
the context manager before emitting further commands.
assert 'InvalidRequestError' == 'DuplicateRecord'
```

Idêntico ao que a atualização anterior já havia capturado com `pg_locks` ao
vivo — não precisei de mais rodadas para confirmar que o defeito é real; a
taxa de ~50% relatada já bastava, e a primeira tentativa reproduziu.

### A causa, seguida até o fim

A pista da atualização anterior estava certa quanto ao sintoma (a mistura de
SQL cru do lock com operações do ORM na mesma sessão é o que faz o `finally`
levantar `InvalidRequestError` em vez de simplesmente reprovar limpo) mas eu
segui um passo além, para entender *por que* uma sessão que só está fazendo
`get → None → add → flush` — sem nenhum outro escritor visível nela mesma —
termina com a própria transação marcada encerrada pelo SQLAlchemy antes do
`finally` rodar.

A resposta está na ordem de duas coisas que `open_local_sign_in`, como
estava, fazia em momentos diferentes:

1. **Ela soltava o advisory lock (`pg_advisory_unlock`) assim que o próprio
   `flush()` retornava** — ou seja, assim que o INSERT foi *enviado* para o
   Postgres dentro da transação corrente, não quando essa transação
   *terminou*. `flush()` não é `commit()`: a linha existe no banco, mas
   ainda invisível para qualquer outra sessão em `READ COMMITTED`.
2. **Só bem depois é que a transação de fato termina** — porque
   `open_local_sign_in` é uma chamada no meio de uma unidade de trabalho
   maior que o chamador continua escrevendo depois que o método retorna:
   `platform/identity/enrolment.py::enrol_local_administrator` ainda busca o
   usuário pelo nome, concede o papel de dono e grava a senha, tudo na
   *mesma* sessão e transação, antes de finalmente confirmar.

Entre (1) e (2) há uma janela real. Um segundo chamador, que estava
bloqueado em `pg_advisory_lock`, destrava assim que (1) acontece — muito
antes de (2). O próprio `get()` desse segundo chamador não enxerga a linha
do primeiro (ainda não commitada) e ele segue para o seu próprio
`add`+`flush`. O INSERT dele, no nível do Postgres, então bloqueia
silenciosamente esperando a chave primária conflitante do primeiro chamador
se resolver — e quando o primeiro finalmente confirma (depois de todo o
trabalho extra de `enrol_local_administrator`), o `flush()` do segundo
acorda com um `IntegrityError` genuíno, não traduzido (esta função nunca
teve um `except IntegrityError`, diferente de `upsert_user`). É esse
`IntegrityError`, levantado dentro do `try`, que faz o SQLAlchemy marcar a
transação ambiente do *segundo* chamador como encerrada — e é a chamada de
`pg_advisory_unlock` desse mesmo `finally`, tentando operar numa sessão
cuja transação o próprio SQLAlchemy já considera fechada, que sai como
`InvalidRequestError`, mascarando o `IntegrityError` original. Como esse
unlock nunca chega a sair para o Postgres, o lock fica preso naquela conexão
— exatamente o `pg_locks` capturado na atualização anterior mostrava
(`ExclusiveLock`, `granted=t`, nunca liberado).

Isto explica, sem sobra, também a "Tentativa 1" registrada acima: com o
lock inteiramente removido, todas as 8 tentativas correm o `get()` quase ao
mesmo tempo, então quem perde a corrida do INSERT recebe o mesmo
`IntegrityError` cru — só que, sem `finally` nenhum tentando destravar nada,
não há um segundo erro mascarando o primeiro, e o teste (que exige
`DuplicateRecord`) reprovaria por um motivo diferente. As 4 rodadas sem
reprovar não contradizem isso: a janela do `get()` sem nenhuma serialização
é estreita, exatamente como a nota anterior já dizia.

### A correção, e por que não é a cópia literal do padrão do migrador

A pista apontava para `platform/persistence/postgres/engine.py::advisory_lock`
— o lock do migrador, numa `AsyncConnection` crua, separada de qualquer
`Session` do ORM, com `commit()` *antes* do `unlock` no mesmo `finally`.
Tentei essa forma primeiro, mentalmente, antes de escrever qualquer código:
copiá-la exigiria que `open_local_sign_in` confirmasse a própria transação
antes de destravar — exatamente o que fecharia a janela. Mas
`open_local_sign_in` **não é dona da transação em que roda**: como a seção
acima mostra, `enrol_local_administrator` continua escrevendo nela depois
que o método retorna (conceder o papel de dono, gravar a senha), e esse
resto do trabalho precisa desfazer *junto* com a abertura se falhar — por
exemplo, quando o nome pedido já existe e não foi pedida rotação. Se
`open_local_sign_in` confirmasse sua própria transação cedo (a única forma
de replicar o padrão do migrador aqui, já que ela não controla quando o
chamador termina a dele), a abertura ficaria permanentemente gravada mesmo
num caminho em que nenhum administrador chegou a ser criado — um
deployment com a porta marcada "aberta" e sem ninguém para entrar por ela,
sem mais nenhum jeito de reabri-la por essa via. Copiar o padrão ao pé da
letra teria trocado o defeito medido por um pior e sem teste que o
pegasse.

O que a correção faz em vez disso: `open_local_sign_in` passou a usar
`pg_advisory_xact_lock` no lugar do par `pg_advisory_lock`/`pg_advisory_unlock`
— o mesmo tipo de lock consultivo do Postgres que o migrador usa (não um
terceiro mecanismo de coordenação; nenhum `SELECT ... FOR UPDATE`, nenhum
lock fora do banco), só que na variante de escopo de *transação* em vez de
sessão. O Postgres libera esse lock sozinho, exatamente quando a transação
corrente confirma ou desfaz — sem chamada de liberação nenhuma, então não
sobra um `finally` para o SQLAlchemy poder estragar. E como o lock só solta
quando a transação inteira (abertura **e** o resto que
`enrol_local_administrator` faz depois) já terminou de um jeito ou de
outro, um segundo chamador só lê depois que o primeiro está de fato
resolvido: se o primeiro confirmou, o segundo enxerga a linha e recusa
limpo; se o primeiro desfez (nome ocupado, por exemplo), a linha não existe
e o segundo segue livre para ser quem abre a porta de verdade. A
atomicidade entre "abrir a porta" e "criar o administrador" fica
preservada — o problema que a cópia literal do padrão do migrador teria
introduzido.

O diff inteiro (função inteira, sem tocar em mais nada):

```
platform/persistence/postgres/repositories/identity_repository.py | 42 +++++++++++++-------
1 file changed
```

`pg_advisory_lock(:key)` → `pg_advisory_xact_lock(:key)`; o `try/finally`
com o `pg_advisory_unlock` foi removido inteiro, porque não há mais nada
para liberar explicitamente.

### A prova, por medição

**Vinte rodadas** do comando exato do enunciado, uma pytest por rodada
(cada uma reconstrói o container Docker do zero, por como a suíte já
funciona):

```
20 de 20 passaram — 1 passed, 39 deselected, em cada rodada, entre 0.86s e
1.98s de tempo total (a maioria abaixo de 1.3s).
```

Antes da correção: vermelho na 1ª de 1 tentativa, 30.11s (bloqueado em
`pg_advisory_lock` até o `statement_timeout`). Depois: verde 20/20, sob 2s
cada — a queda de tempo por si já é evidência de que a corrida deixou de
travar em vez de só "dar sorte" com o agendamento do `asyncio.gather`.

**`pg_locks`, consultado ao vivo, não por inferência.** Escrevi um script
isolado (fora do repositório, em `/tmp`, não commitado) que sobe o mesmo
container Docker que a suíte usa, roda a mesma corrida de 8 tentativas
simultâneas contra `open_local_sign_in`, e — **antes** de fechar qualquer
conexão ou derrubar o banco — consulta `pg_locks` numa conexão à parte.
Resultado de uma rodada real:

```
winners=1 losers=7
  loser: DuplicateRecord: A local sign-in opening already exists with id 'acme'.
  (× 7, mensagem idêntica, sem asyncpg/sqlstate/constraint/ix_/pk_)
advisory locks currently held (any key): 0
advisory locks on LOCAL_SIGN_IN_OPEN_ADVISORY_LOCK_KEY (8314160): 0
OK: no dangling advisory lock on the local-sign-in-opening key
stored opening: LocalSignInOpening(..., opened_via='race-attempt-0')
```

Zero locks `advisory` de qualquer chave sobraram depois da corrida — não só
a chave desta feature. Um teste verde com lock preso seria o mesmo defeito
adiado; este não é o caso.

**A suíte vizinha inteira, com `--postgres`**, sem tocar em nenhum outro
arquivo:

```
uv run pytest tests/contract/persistence/test_identity_repository.py \
  tests/contract/persistence/test_operations.py --postgres -q
47 passed, 9 skipped in 41.08s
```

Os 9 skips são os esperados (a variante `[fakes]` do teste de corrida, mais
os oito testes de `test_operations.py` que só fazem sentido contra Postgres
de verdade — dump/restore, migração, at-rest). Nenhuma reprovação nova,
nenhum skip inesperado. Sem `--postgres`, a suíte rápida de
`test_identity_repository.py` continua em `19 passed, 1 skipped` — o
caminho sem Postgres não foi afetado.

**Gates estáticos**, escopados ao único arquivo alterado (a suíte completa e
`make verify` são do orquestrador):

```
uv run ruff check platform/persistence/postgres/repositories/identity_repository.py
  → All checks passed!
uv run ruff format --check platform/persistence/postgres/repositories/identity_repository.py
  → 1 file already formatted
uv run mypy platform/persistence/postgres/repositories/identity_repository.py
  → Success: no issues found in 1 source file
```

### O que fica pendente, nomeado

**Nada, para T020.** O teste está marcado, a propriedade que ele mede está
corrigida e medida vinte vezes, e a checagem de `pg_locks` fecha
exatamente a ressalva que a atualização anterior deixou em aberto ("um
teste verde com lock preso é o mesmo defeito adiado").

Um ponto que vale nomear para quem ler esta seção depois: a correção altera
o *tipo de trava* que `open_local_sign_in` usa (de sessão para transação),
não a *chave* nem a *família* do mecanismo — continua sendo um advisory
lock do Postgres com `LOCAL_SIGN_IN_OPEN_ADVISORY_LOCK_KEY`, e continua
sendo o mesmo tipo de exclusão que o boot já usa para as migrações, só que
adaptado ao formato de transação única que este caminho de fato tem (o
migrador precisa do lock de sessão porque o Alembic confirma cada revisão
em sua própria transação e o lock tem que sobreviver entre elas; este
caminho não tem esse problema — é uma transação só). Não toquei em
`engine.py::advisory_lock` nem em nada do migrador: continuam exatamente
como estavam, fora do escopo deste defeito.
