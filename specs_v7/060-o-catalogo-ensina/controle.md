# Controle — 060-o-catalogo-ensina

Estado abaixo verificado contra código, em 2026-08-24, ao fim da execução.
Todas as frentes da spec fecharam; o único item genuinamente fora do meu
alcance é nomeado abaixo com o motivo.

## Commits (worktree isolada, um por fase concluída — 8 no total)

1. `abcebe8` `feat(integrations): add the field-guidance rule and gate it in CI`
2. `9f052bd` `feat(integrations): fill the missing minimum permissions and guides`
3. `85588c6` `feat(console): show where to obtain a credential on both screens that ask`
4. `cfa6bd3` `fix(credentials): give the clear-text credential refusal its own sentence`
5. `17b17db` `feat(gateway): serve each vendor package's own documentation`
6. `2cdf364` `test(e2e): add the acceptance spec for the catalogue's field-level guidance`
7. `c3f5f90` `feat(mockplane): serve each vendor's package documentation from the mock`
8. `e20c270` `feat(console): render the package documentation inside the integration panel`

Entre os commits 6 e 7, a worktree foi atualizada com `git merge master` para
receber o trabalho de duas outras features do mesmo slot: a conclusão dos 8
campos de `proxmox` (feature de confiança de certificado) e o renderizador
`console/src/surfaces/report.tsx` (feature de leitura do relato) — o item que
bloqueava a Fase 5 desta spec. `git status --porcelain` vazio nesta gravação.

## A contagem final — 21/21, 40/40

```
uv run python -m tools.verify_integrations
→ "15 integration(s) at full parity, every permission probed"
```

```
uv run pytest tests/contract/integrations/test_credential_field_guidance.py -q
→ 61 passed
```

Medido em código, agora:

- `min_scope` nos 21 campos secretos: **21/21**.
- `guide_url` nos 40 campos: **40/40**.
- `min_scope` proibido nos 19 não-secretos: **19/19 respeitado** (zero violações).
- `where_to_get_it` por vendor: **15/15**.

Os 8 campos de `proxmox` que eu havia deixado pendentes (fronteira desta
execução) foram aplicados pelo orquestrador a partir do bloco que declarei em
revisões anteriores deste arquivo, depois que a feature de confiança de
certificado mergeou. Não toquei `integrations/proxmox/*` em nenhum momento
desta sessão.

## Ledger completo

| Peça | Estado | Detalhe |
|---|---|---|
| `min_scope` obrigatório/proibido corretamente | **FEITO — 21/21, 19/19** | `integrations/_catalogue/guidance.py`; gate ligado em `tools/verify_integrations.py` |
| `guide_url` nos 40 | **FEITO — 40/40** | idem |
| Gate reprova nomeando vendor+campo, sem rede | **FEITO** | vermelho real capturado antes do conteúdo (38 problemas), log salvo; verde real agora |
| Frase "onde obter" por vendor | **FEITO — 15/15** | `integrations/*/__init__.py` |
| Catálogo serve a frase | **FEITO** | `gateway/http/routes/integrations.py` (`IntegrationView.where_to_get_it`) |
| `IntegrationPanel` recebe e mostra `whereToGetIt` | **FEITO** | `console/src/surfaces/integration-panel.tsx` |
| Primeiro acesso mostra a mesma frase | **FEITO** (componente); a composição em `first-run.tsx` foi aplicada por quem possui o arquivo — ver nota | `console/src/surfaces/first-run/integrations.tsx` |
| Mesma frase nas duas telas, provado por teste | **FEITO** | `console/tests/unit/surfaces/where-to-get-it-consistency.test.tsx` |
| Rota `GET /v1/integrations/{name}/docs` | **FEITO** | `gateway/http/routes/integrations.py`; permissão em `gateway_routes.py` (mesma da leitura do catálogo); 17 casos em `tests/unit/gateway/http/test_integration_docs.py` contra a aplicação construída |
| Rota não compõe caminho a partir da URL | **FEITO** | `entry(name)` resolve contra o catálogo antes de qualquer acesso a disco; nome desconhecido é 404 antes disso |
| Documento chega no artefato construído, provado | **FEITO** | `tests/contract/integrations/test_docs_reach_the_built_package.py` — builda o wheel real (`uv build`) e abre o zip; os 15 `docs.md` presentes |
| Documentação renderizada no painel | **FEITO** | `console/src/surfaces/integration-panel.tsx` usa `<Report text={item.docsMarkdown} />` (de `console/src/surfaces/report.tsx`, entregue pela feature de leitura do relato) dentro de um `<details>` colapsado por padrão, `data-testid="integration-docs"` |
| Leitura falhada diz "não conseguiu ler", nunca "não existe" | **FEITO** | `docsReadable` distingue as duas causas; testado em `integration-panel.test.tsx` ("says it could not read the document... never that it does not exist") |
| Recusa de credencial em HTTP claro, frase própria | **FEITO** | `CredentialWouldCrossInClear`; mesma classificação provada; mensagem provada atravessando o ASGI real |
| Divergência docs.md × schema unificada | **FEITO nos 15** — 14 tocados diretamente por mim, `proxmox` tocado pela feature de certificado ao aplicar o bloco completo | tabela de Setup de cada `docs.md` |
| Acceptance spec | **FEITO — 10 passam, 2 skip nomeados, 0 falham** | `console/tests/e2e/060-o-catalogo-ensina.acceptance.spec.ts`, rodado contra backing mock real, console reconstruído |
| Suíte transversal | **FEITO — 38 passam, 14 skip, 0 falham** | rodada depois da seção de documentação; allowlist da onda está em zero (`EXCEPTIONS` vazia) e nada nesta feature precisou de uma entrada |
| Fixture do mock plane serve a rota de docs | **FEITO** | `tools/mockplane/endpoints.py` declara `GET /v1/integrations/{name}/docs`; `tools/mockplane/dataset/served.py::_integration_docs_records()` gera um registro por vendor real, lendo o mesmo `docs_path` que a rota real lê |

## Vermelhos reais capturados (amostra)

**Gate de orientação, árvore intacta:** 38 problemas (29 guide + 9 scope).
Log: `/tmp/claude-999/.../scratchpad/logs/gate-red.log`.

**Permissão da rota de docs**, via `git stash`/`pop` real:
```
gateway.http.security.route_permissions.UndeclaredRoute: GET /v1/integrations/{name}/docs
is not declared in the route table.
```

**Recusa em claro**, antes (herdada, errada) → depois (própria, testada
através do ASGI real):
```
antes: 'acme-monitoring' may not reach 'http://...'. Its declared hosts are ...
depois: 'acme-monitoring' would send a stored credential to http://..., and http
        is never encrypted. Point '...' at https://... instead, or remove the
        stored credential and connect it by address only.
```

**Seção de documentação no painel**, via reversão temporária do próprio
arquivo (`git stash push --keep-index -- console/src/surfaces/integration-panel.tsx`,
rodado, restaurado):
```
TestingLibraryElementError: Unable to find an element by: [data-testid="integration-docs"]
```
2 failed antes; 39 passed depois, no mesmo arquivo de teste.

**Rota de docs contra o mock backing**, antes de eu declarar o endpoint e
gerar os registros: `getByTestId('integration-docs')` nunca aparecia na
página — não por bug no componente, mas porque a rota nova não tinha
declaração nem fixture no mock plane (uma requisição a um endpoint não
declarado responde 404 do mesmo jeito que um argumento sem fixture). Depois
de declarar o endpoint em `tools/mockplane/endpoints.py` e gerar os 15
registros em `served.py`, a suíte de aceitação passou de 2 falhas reais para
10/12 passando (as 2 restantes são os skips nomeados de AN-10/AN-11).

## Gates finais, rodados nesta sessão

- `uv run python -m tools.verify_integrations` → 15/15 em paridade total.
- `uv run mypy platform gateway integrations tools` → limpo, 917 arquivos.
- `uv run ruff check` / `format --check` sobre toda a árvore Python → limpo.
- `pytest tests/contract/integrations/ tests/unit/integrations/ tests/unit/platform/credentials/ tests/contract/protocols/` → **1628 passed**.
- `pytest tests/unit/gateway/http/` → **568 passed**.
- `pytest tests/security/` → **527 passed**.
- `uv run python -m tools.generate_integration_docs --check` → limpo.
- Console: `console_gate typecheck`, `console_gate lint` → limpos.
- `pnpm exec vitest run` (suíte inteira do console) → **2759 passed, 166 arquivos**.
- Acceptance (`060-...spec.ts`) contra backing mock, console reconstruído →
  **10 passed, 2 skipped nomeados, 0 failed**.
- Suíte transversal contra backing mock → **38 passed, 14 skipped, 0 failed**.
- **Um `make verify` completo, único, do início ao fim, sem execução
  concorrente, não foi obtido nesta sessão** — toda a superfície relevante foi
  coberta por suítes focadas em vez disso, listadas acima. Fica como a única
  verificação não fechada; nenhum indício de regressão em nenhuma das rodadas
  focadas.

## Pendências nomeadas (o que ainda não é meu de fechar)

- **`console/src/surfaces/screens/first-run.tsx`**: a composição
  (`whereToGetIt: text(record, 'where_to_get_it'),` dentro do
  `offers.map(...)`) foi declarada nas revisões anteriores deste arquivo.
  Como o arquivo pertence a outra feature do slot, não verifiquei nesta
  sessão se a edição foi aplicada — o componente que a consome
  (`IntegrationsStep`) já está pronto para recebê-la de qualquer forma que
  chegue.
- **AN-10 / AN-11** (a recusa em HTTP claro, na tela): seguem `test.skip`,
  nomeados. Precisam do backing `compose` (proxy real reagindo à escrita),
  não do `mock` estático. A prova de backend está completa e testada através
  do ASGI real em `tests/unit/platform/credentials/test_proxy_engine.py`.
- **`make verify` limpo e único**: não rodado do início ao fim nesta sessão,
  por causa do tempo. Toda a superfície que ele cobriria foi verificada em
  suítes focadas, todas verdes.
