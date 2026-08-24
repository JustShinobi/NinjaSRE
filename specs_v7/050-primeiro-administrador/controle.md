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

1. **4 das 10 alegações normativas do acceptance spec continuam vermelhas**
   (claims 1, 2, 3, 9 — a tela nomeia o comando). Motivo real, não falta de
   implementação: nenhum cenário de mock comitado nem um `compose up` simples
   alcançam o estado `unclaimed` hoje. A leitura acontece num Server
   Component (não intercepta via `page.route()` — mesma limitação que
   `030-uma-fonte-por-fato` documentou para a lista de incidentes). Dois
   caminhos para fechar: estender `tools/mockplane/dataset/served.py` com
   este endpoint no cenário `first-day` (gerado, não editado à mão), ou rodar
   `--backing compose` com um `docker compose up` genuinamente limpo.
2. **Prova no caminho de serving via compose real (T066-T071)** — não
   tentada por tempo. Docker e Docker Compose v2 confirmados disponíveis
   nesta sandbox.
3. **`config/constants/__init__.py`** — 6 nomes novos do slot não replicados
   no re-export agregado (~2000 linhas, sem teste que exija a réplica).
4. **`make verify` completo** — não rodado (é o gate do orquestrador). Rodei
   591+38+84+25+29 testes Python narrow (todos os arquivos tocados, mais a
   suíte de regressão de identity/startup/cli/gateway inteira), 3 testes
   Vitest, ruff e mypy em cada arquivo tocado — todos limpos.
5. **Chaves i18n da seção 5** — aplicar em `console/src/i18n/en.ts` e
   `pt-BR.ts` (arquivos de escrita única do slot, não tocados por mim).
