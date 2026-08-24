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
| Abertura do sign-in local (fato único por deployment) | `platform/persistence/ports/identity_repository.py::LocalSignInOpening` + implementações Fake/Postgres; Postgres sob `pg_advisory_lock` com chave própria (`LOCAL_SIGN_IN_OPEN_ADVISORY_LOCK_KEY`) | `tests/unit/platform/identity/test_local_sign_in_opening.py` (6/6) |
| Regra única de administrador local | `platform/identity/enrolment.py::enrol_local_administrator`, dois chamadores de produção: `surfaces/cli/commands/setup.py::admin` e `platform/startup/bootstrap.py::establish_durable_credential` | `tests/unit/platform/identity/test_enrolment.py` (7/7) |
| Porta do sign-in local como fato, não campo | `platform/identity/local_accounts.py::LocalSignIn.sign_in` | mesma suíte acima + `tests/unit/platform/identity/test_local_accounts.py` (19/19, sem regressão) |
| Comando CLI | `surfaces/cli/commands/setup.py::admin`, registrado em `surfaces/cli/app.py` (grupo `setup` já existente) | `tests/unit/surfaces/cli/commands/test_setup.py` (84/84) |
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
| Implementação Postgres | FEITO | `platform/persistence/postgres/repositories/identity_repository.py:` `open_local_sign_in` sob advisory lock |
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
2. **Prova no caminho de serving via compose real (T066-T071)** — ainda não
   tentada. Fora do escopo desta atualização, que tratou apenas do gate
   automatizado (mock plane); segue pendente de um agente com esse recorte.
3. **`config/constants/__init__.py`** — 6 nomes novos do slot não replicados
   no re-export agregado (~2000 linhas, sem teste que exija a réplica).
4. **`make verify` completo** — ver "Atualização" abaixo pelo resultado real,
   lido do próprio comando.
5. **Chaves i18n da seção 5** — aplicar em `console/src/i18n/en.ts` e
   `pt-BR.ts` (arquivos de escrita única do slot, não tocados por mim).

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
metade Python que já tinha passado): em andamento — ver o parágrafo seguinte pelo achado que decide o que essa
segunda rodada vale.

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

**T075**: marcada apenas quando a linha acima confirmar `exit 0`, ou deixada
sem marcar com a causa exata nomeada — nunca por inferência.
