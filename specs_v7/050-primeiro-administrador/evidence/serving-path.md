# Prova no caminho de serving — compose real

Deployment único, levantado por `deploy/compose/docker-compose.yml`, usado do
início ao fim de T066 a T070 (mesmo `postgres-data`, nunca recriado entre
tarefas). Trazido com:

```
NINJASRE_LLM_PROVIDER=ollama
NINJASRE_DATABASE_ENCRYPTION_KEY=<gerada para esta sessão, descartada com o stack>
docker compose --file deploy/compose/docker-compose.yml up -d --build
```

Sem `NINJASRE_LOCAL_ACCOUNT_PASSWORD_HASH`, sem `--project` de demonstração,
sem seed — a árvore que um operador vê ao clonar o repositório e seguir a
receita do próprio cabeçalho do arquivo.

## T066 — primeiro start, o comando, a sessão

Transcrição completa do primeiro boot do container `app` (a árvore inteira,
sem edição): `evidence/t066-clean-boot.log`. O que ele mostra:

- `{"event": "deployment.local_account_absent", ...}` — confirmando que não
  havia conta de ambiente.
- O bloco impresso nomeia exatamente um comando: `ninjasre setup admin
  --name admin`, e não afirma que a credencial de bootstrap serve para o
  formulário de sign-in ("Exchange the credential below for that
  administrator instead, through the setup API — it does not sign you in by
  itself").

Comando executado dentro do próprio container do compose,
`docker compose exec -it app ninjasre setup admin --name admin` — sessão
real de terminal (via pty, não um pipe), transcrição em
`evidence/t066-setup-admin-session.log`:

```
Passphrase for 'admin':
Confirm passphrase:
...
✓ 'admin' created. Sign in at the console with that name and the passphrase you just entered.
```

A passphrase digitada não aparece em nenhum ponto da transcrição — sem eco,
nas duas perguntas, exatamente como T015 exige.

**A sessão**: o nome e a passphrase escolhidos no prompt foram entregues à
rota real de sign-in do gateway (`POST /auth/sign-in`, a mesma que o
formulário do console chama), contra o `app` publicado em
`127.0.0.1:8420` — resposta real:

```
HTTP 200
{"token":"nsre_...","expires_at":"2026-08-25T06:41:13...","principal_id":"3466ef95dc9b6e21ee163a94fffed42d"}
```

Prova o critério de aceite: "o nome e a passphrase escolhidos são aceitos
pelo sign-in logo em seguida" — o mesmo fato que
`tests/contract/deployment/test_first_run_sign_in.py` prova no harness, agora
confirmado contra o backend real e o Postgres real deste deployment.

**O que este compose genuinamente não mostra**: uma captura de tela do
console autenticado. O container `console` deste `docker-compose.yml`
executa `python -m gateway.http.serve --port 8421` — a mesma composição do
gateway que `app` roda, não o servidor Next.js standalone
(`console/.next/standalone/server.js`, o que `tools/console_e2e.py::console()`
roda separadamente para os testes de navegador). Confirmado, não deduzido:
`GET /health/live` no container `console` devolve `{"live":true}` — a mesma
forma exata da checagem de saúde do `app`, não o texto puro `"live"` que
`surfaces/console/serve.py::ConsoleServer` (o outro renderizador do
repositório, com sign-in por token) devolveria; `GET /` devolve 404 no
formato de erro padrão do gateway (`{"error":{"type":"http_error",...}}`),
sem nenhum HTML, nenhum asset estático, nenhuma menção a Next.js ou a
build parado em nenhuma linha do log de boot do container. Isto é uma
lacuna pré-existente na composição do container `console` do compose —
ele serve a API uma segunda vez, na porta 8421, e não o SPA que
`console/tests/e2e/` dirige contra o harness `tools/console_e2e.py`. Não é
desta feature (que é dona da regra de identidade, não da imagem/composição
do console) e não foi tocada por mim. A sessão autenticada foi provada pela
rota que a estabelece de fato (`POST /auth/sign-in`, 200, token real), não
por uma captura de tela que este stack não tem como produzir.

## T067 — repetir o caminho que criou o administrador

**Achado sobre o método, nomeado**: a segunda sessão interativa via
`docker compose exec -it app ninjasre setup admin --name admin`, dirigida
pelo mesmo mecanismo de pty que capturou T066 com sucesso, trava de forma
determinística logo após a primeira pergunta (`Passphrase for 'admin':`,
resposta entregue e ecoada) e nunca alcança `Confirm passphrase:` — três
tentativas, com até 110s de paciência, mesmo resultado exato nas três. O
próprio comando funciona: a mesma invocação sem pty (`-T`) recusa
instantaneamente por falta de terminal interativo, como esperado, e a regra
de negócio (abaixo) responde em milissegundos quando chamada diretamente.
É um defeito do meu arnês de teste (dois pty aninhados via `docker compose
exec -it`, provavelmente por causa das muitas sessões que este mesmo
container já viu numa hora de depuração), não do produto — mas fica
nomeado, não escondido: a captura de T067 não é uma segunda transcrição de
terminal ponta-a-ponta.

**O que prova a mesma coisa, contra o mesmo Postgres real deste
deployment**: chamada direta a `enrol_local_administrator` — a mesma regra
que `surfaces/cli/commands/setup.py::admin` chama depois dos dois prompts,
com o mesmo `store_factory()`, rodando dentro do container via
`docker compose exec -T app python3 /tmp/t067_repeat_probe.py`:

```
REFUSED (LocalAdministratorNameTaken): 'admin' already signs in to this
deployment. To replace that passphrase instead of creating a new
administrator, run the same command again with rotation requested
explicitly.
```

Frase de gente: nomeia o que aconteceu ("'admin' already signs in") e o que
fazer (rotação explícita), sem nome de índice, de constraint ou texto do
driver. É o texto exato que `LocalAdministratorNameTaken` carrega
(`platform/identity/errors.py`), o mesmo que
`tests/unit/platform/identity/test_enrolment.py` prova vermelho→verde no
harness — confirmado aqui contra o Postgres real, não o fake.

## T068 — um segundo service account sem e-mail

**Esclarecimento de vocabulário, contra o schema real**: `email` em `users` é
`NOT NULL` — um principal criado por `ninjasre setup admin --name <outro>`
guarda o próprio `name` em `email` (confirmado: um segundo administrador
`svc-second`, criado com sucesso pelo mesmo mecanismo de T013, ficou com
`email='svc-second'`, não vazio). Quem tem `email=''`/`email_folded=NULL` de
verdade é `kind='service_account'` — o formato do próprio principal de
bootstrap (`bootstrap-administrator`, criado uma vez por
`_ensure_bootstrap_principal`). É esse o "service account sem e-mail" que a
User Story 5 e o SC-006 descrevem, e é o que T017-T019 provam no nível de
repositório.

Criado um segundo, pelo mesmo formato exato de `_ensure_bootstrap_principal`
(`User(user_id=..., email="", display_name=..., kind=SERVICE_ACCOUNT)`),
via `uow.identity.upsert_user`, contra o Postgres real deste deployment:

```
CREATED: user_id='second-service-account' email='' kind=<PrincipalKind.SERVICE_ACCOUNT: 'service_account'>
```

Consulta direta ao banco depois da escrita — os dois coexistem:

```
             user_id              |      kind       | email_q | email_folded_q
-----------------------------------+-----------------+---------+----------------
 bootstrap-administrator          | service_account | ''      | NULL
 second-service-account           | service_account | ''      | NULL
```

Antes desta feature isto morria em `asyncpg.exceptions.UniqueViolationError`
na coluna `email_folded` (registrado no `controle.md` da feature). Hoje os
dois `email_folded` são `NULL`, e o índice único do Postgres nunca trata dois
`NULL` como colisão — confirmado, não inferido, contra o mesmo `ix_users_email`
que causava o defeito.
