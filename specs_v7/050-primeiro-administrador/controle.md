# Controle — Primeiro administrador

**Estado verificado contra o código atual**, worktree
`/srv/workspaces/NinjaSRE/.claude/worktrees/agent-a588276e27dce5e02`
(ramo `worktree-agent-a588276e27dce5e02`), partindo de `b12578f`. **Parada
limpa a pedido do orquestrador** (janela de turnos em 87%): árvore de
trabalho limpa, 14 commits, nenhuma edição em andamento.

## Resposta em duas linhas (pedida pelo orquestrador)

**UniqueViolation do e-mail vazio: RESOLVIDO**, vermelho capturado contra
Postgres real e verde confirmado (6/6, 2 backends) — ver seção 1.
**Caminhos de credencial, antes vs. agora**: antes, 1 caminho funcional real
(a conta de ambiente) mais 1 caminho **quebrado de fato** (a credencial de
boot, que autenticava mas o formulário de sign-in não aceitava — o "seam").
Agora, **2 caminhos funcionais e unificados** na mesma regra
(`enrol_local_administrator`): o comando `ninjasre setup admin` (fechado,
testado, 84/84 verde) e a troca da credencial de boot (fechada em
`platform/startup/bootstrap.py`, 29/29 verde) — **mas a rota HTTP que expõe o
segundo caminho ainda não foi atualizada para o novo contrato** (ver "Gap
crítico" abaixo) — portanto, hoje, na árvore, só 1 dos 2 caminhos é
alcançável de ponta a ponta por fora (o CLI); o da troca está fechado na
camada de baixo mas desconectado na borda HTTP.

## Gap crítico — próximo passo exato, sem ambiguidade

`gateway/http/routes/first_run.py::durable_credential` (linha 227) **ainda
chama `establish_durable_credential` sem `password`**, que agora é obrigatório
(commit `20745f7`). **Isto quebra a rota `POST /v1/setup/durable-credential`
em runtime** (`TypeError: missing password`) até ser corrigido. Não há teste
no repositório hoje que bata nessa rota via ASGI real e teria pego isso — é
uma lacuna de cobertura que também fica registrada aqui. Conserto: adicionar
`password: str` a `DurableCredentialRequest` (mesmo arquivo, ~linha 91),
repassar `password=body.password` na chamada, e capturar
`LocalSignInAlreadyOpen`/`LocalEnrolmentBlockedBySso` como `bad_request`.
Depois, regenerar `fixtures/contract/openapi.json`
(`python -m tools.mockplane contract`) e `console/src/api/schema.ts`
(`pnpm run client` em `console/`).

## O que fechou inteiro (14 commits, árvore verde a cada um)

1. Camada de persistência (5 commits) — porta+Fake+Postgres+2 migrações.
2. `platform/identity/enrolment.py::enrol_local_administrator` — regra única.
   7/7 verde.
3. Porta do sign-in local redefinida como fato — 6/6 verde, vermelho antes.
4. `ninjasre setup admin` — comando CLI completo — 84/84 verde.
5. `platform/startup/bootstrap.py`: `bring_up` gateado (sem convite quando já
   administrado ou IdP ativo), `announcement` reescrito (nomeia o comando,
   para de afirmar que a credencial serve para sign-in),
   `establish_durable_credential` exige `password` e cria administrador pela
   MESMA regra do CLI (`user_id`/`display_name` explícitos, suportado desde
   `ad9aee4`). 29/29 verde em `test_bootstrap.py`.
6. `gateway/http/serve.py::_serve` atualizado para o `credential=None`.
7. Todos os outros call-sites de `establish_durable_credential`/`bring_up`
   varridos e corrigidos: `tests/security/test_bootstrap_credential_never_leaks.py`,
   `tests/unit/platform/startup/test_checklist.py` — verde.
   `tests/benchmarks/test_first_run_budgets.py` e
   `tests/contract/deployment/test_first_run_sign_in.py` não chamam
   `establish_durable_credential`, sem alteração necessária.

## O que fica pendente, nomeado

1. **Gap crítico acima** — rota HTTP da troca, prioridade máxima.
2. `tests/unit/gateway/http/test_first_run_routes.py` — ainda não conferido
   nesta varredura (parei antes de abrir o arquivo).
3. Console: rota pública de disponibilidade, bloco de aviso nas duas telas
   (sign-in + first-run), chaves i18n — não iniciado.
4. Prova no caminho de serving (compose real) — não tentada.
5. `config/constants/__init__.py` — 6 nomes novos não replicados no
   agregado; `make check-constants` passa sem isso (confirmado).
6. `make verify` de linha de base (T001) — disparado em background no início,
   nunca conferido até o fim.

## Segurança

Nenhuma passphrase em commit, log ou saída capturada em nenhum dos 14
commits.
