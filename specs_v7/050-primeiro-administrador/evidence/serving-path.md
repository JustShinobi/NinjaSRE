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
