# Controle — 060-o-catalogo-ensina

Estado abaixo verificado contra código, em 2026-08-24. Sessão pausada em
limite limpo (janela de orçamento) com tudo commitado — sem trabalho solto.

## Commits (worktree isolada, um por fase concluída, 6 no total)

1. `abcebe8` `feat(integrations): add the field-guidance rule and gate it in CI`
2. `9f052bd` `feat(integrations): fill the missing minimum permissions and guides`
3. `85588c6` `feat(console): show where to obtain a credential on both screens that ask`
4. `cfa6bd3` `fix(credentials): give the clear-text credential refusal its own sentence`
5. `17b17db` `feat(gateway): serve each vendor package's own documentation`
6. `2cdf364` `test(e2e): add the acceptance spec for the catalogue's field-level guidance`

`git status --porcelain` vazio no momento desta pausa — nada solto.

## A contagem final, reproduzível

```
uv run python3 -c "
from integrations._catalogue.discovery import catalogue
entries = catalogue()
total=secret=with_scope=guided=0
for e in entries:
    for f in e.descriptor.schema.fields:
        total+=1
        if f.is_secret:
            secret+=1
            if f.min_scope.strip(): with_scope+=1
        if f.guide_url.strip(): guided+=1
print(total, secret, with_scope, guided)
"
```

Resultado real (medido às 2026-08-24, contra o código, não grep de texto):

- **`min_scope` nos secretos: 18 de 21.**
- **`guide_url` nos 40: 35 de 40.**
- **`min_scope` proibido nos 19 não-secretos: 19/19 respeitado (zero violações).**
- **`where_to_get_it` por vendor: 14 de 15.**

**O que falta, exatamente, e por quê**: os 3 `min_scope` e os 5 `guide_url`
que faltam são todos os mesmos oito campos de `integrations/proxmox/schema.py`
— `password`, `ticket`, `csrf_token` (min_scope) e `endpoint`, `username`,
`password`, `ticket`, `csrf_token` (guide_url) — mais o `where_to_get_it` do
perfil do vendor. `proxmox` não foi tocado porque é fronteira desta execução:
a feature de confiança de certificado está em voo no mesmo slot sobre os
mesmos arquivos, e o orquestrador pediu explicitamente para não tocá-los.
Todo o conteúdo já foi pesquisado (documentação oficial do Proxmox, capítulo
PVEUM) e está pronto abaixo para aplicação no merge — não é trabalho que
falta fazer, é trabalho que não pode ser commitado por mim nesta árvore.

Uma mensagem do orquestrador durante a sessão relatou 20/38; não bateu com a
medição em código acima (18/35), que é reproduzível com o comando acima.
Reconferido duas vezes, mesmo resultado as duas vezes.

## Bloco para aplicar em `integrations/proxmox/schema.py` no merge

```python
endpoint(
    "endpoint",
    ...,  # texto existente
    guide_url="https://pve.proxmox.com/pve-docs/",
),
secret(
    "api_token",
    ...,  # inalterado, já completo
),
public(
    "username",
    ...,  # texto existente
    guide_url="https://pve.proxmox.com/pve-docs/chapter-pveum.html",
),
secret(
    "password",
    ...,  # texto existente
    min_scope=(
        "Sys.Audit on /, VM.Audit on /vms and Datastore.Audit on /storage — "
        "granted together by the PVEAuditor role on /, for the login name "
        "this password authenticates"
    ),
    guide_url="https://pve.proxmox.com/pve-docs/chapter-pveum.html",
),
secret(
    "ticket",
    ...,  # texto existente
    min_scope=(
        "the same access as the login (username and password) that was "
        "exchanged for it — session material the proxy writes, never a "
        "scope an operator sets"
    ),
    guide_url="https://pve.proxmox.com/pve-docs/chapter-pveum.html",
),
secret(
    "csrf_token",
    ...,  # texto existente
    min_scope="the same as the ticket it accompanies — session material, not an operator-set scope",
    guide_url="https://pve.proxmox.com/pve-docs/chapter-pveum.html",
),
```

E em `integrations/proxmox/__init__.py`, no `PROFILE`, depois de `pagination=PAGINATION,`:

```python
where_to_get_it=(
    "Generate an API token from Proxmox's own Datacenter → Permissions → API "
    "Tokens, with the PVEAuditor role — or, where a token cannot be issued, "
    "authenticate with a login that holds it."
),
```

`integrations/proxmox/docs.md` também precisa da mesma unificação de tabela
Setup que os outros 14 vendors já receberam (remover colunas Secret/Required,
citar `schema.py` como fonte, preencher Minimum permission/Guide para os 5
campos acima). Não feito — mesma fronteira.

## Ledger completo

| Peça | Estado | Detalhe |
|---|---|---|
| `min_scope` obrigatório/proibido corretamente | **PARCIAL — 18/21, 19/19 corretos** | `integrations/_catalogue/guidance.py`; gate ligado em `tools/verify_integrations.py` |
| `guide_url` nos 40 | **PARCIAL — 35/40** | idem |
| Gate reprova nomeando vendor+campo, sem rede | **FEITO** | mesmo módulo; vermelho real capturado (38 problemas) antes do conteúdo, log salvo |
| Frase "onde obter" por vendor | **PARCIAL — 14/15** | `integrations/*/__init__.py` |
| Catálogo serve a frase | **FEITO** | `gateway/http/routes/integrations.py` |
| `IntegrationPanel` recebe e mostra `whereToGetIt` | **FEITO** | `console/src/surfaces/integration-panel.tsx` |
| Primeiro acesso mostra a mesma frase (componente) | **FEITO** | `console/src/surfaces/first-run/integrations.tsx` |
| Mesma frase nas duas telas, provado por teste | **FEITO** | `console/tests/unit/surfaces/where-to-get-it-consistency.test.tsx` |
| `console/src/surfaces/screens/first-run.tsx` (composição) | **NÃO APLICADO, declarado** | arquivo de outra feature no slot; uma linha a acrescentar no `offers.map(...)`: `whereToGetIt: text(record, 'where_to_get_it'),` |
| Rota `GET /v1/integrations/{name}/docs` | **FEITO** | `gateway/http/routes/integrations.py`; permissão em `gateway_routes.py`; 17 casos em `tests/unit/gateway/http/test_integration_docs.py`, todos os 15 vendors |
| Documento chega no artefato construído, provado | **FEITO** | `tests/contract/integrations/test_docs_reach_the_built_package.py` — builda o wheel real e abre o zip |
| Seção de documentação renderizada no painel | **BLOQUEADO, nomeado** | renderizador de markdown inexistente no repositório inteiro (busca em todas as branches, `node_modules`, `package.json`) |
| Recusa de credencial em HTTP claro, frase própria | **FEITO** | `CredentialWouldCrossInClear` em `platform/credentials/proxy/errors.py`; mesma classificação provada; mensagem provada atravessando o ASGI real |
| Divergência docs.md × schema unificada | **FEITO nos 14 tocados**; proxmox pendente (mesma fronteira) | Setup table de cada `docs.md` |
| Acceptance spec | **FEITO — 7 passaram, 3 skip nomeados, 0 falharam** | `console/tests/e2e/060-o-catalogo-ensina.acceptance.spec.ts`, rodado contra backing mock real |
| Fixture do mock plane regenerada | **FEITO** | `tools/mockplane/dataset/served.py` ganhou `where_to_get_it`; `python -m tools.mockplane build` rodado; só `fixtures/scenarios/populated/integrations.json` mudou |

## Vermelhos reais capturados (amostra; lista completa na revisão anterior deste arquivo)

- Gate de orientação, árvore intacta: 38 problemas (29 guide + 9 scope).
  Log: `/tmp/claude-999/.../scratchpad/logs/gate-red.log`.
- Permissão da rota de docs: `UndeclaredRoute: GET /v1/integrations/{name}/docs
  is not declared in the route table` — capturado via `git stash`/`pop` real,
  não inferido.
- Recusa em claro, mensagem antes (herdada, errada): `'acme-monitoring' may not
  reach 'http://...'. Its declared hosts are ...`. Depois (própria, real,
  testada através do ASGI): `'acme-monitoring' would send a stored credential
  to http://..., and http is never encrypted. Point '...' at https://...
  instead, or remove the stored credential and connect it by address only.`

## Gates rodados nesta sessão (parciais — não um `make verify` limpo final)

- `uv run mypy platform gateway integrations tools` — limpo.
- `uv run ruff check`/`format --check` nos arquivos tocados — limpo.
- Suítes focadas: `tests/contract/integrations/`, `tests/unit/integrations/`,
  `tests/unit/platform/credentials/`, `tests/contract/protocols/`,
  `tests/security/`, `tests/unit/gateway/http/` — todas verdes exceto os 4
  casos de `proxmox` esperados e nomeados.
- Console: `console_gate typecheck`, `console_gate lint`, vitest dos arquivos
  tocados (136 casos) — todos verdes.
- Acceptance e2e (`060-...spec.ts`) e transversal (`transversal-rules.spec.ts`)
  contra backing mock real — 7/10 e 38/52 passaram, resto skip nomeado, 0 falha.
- **Um `make verify` completo rodou em paralelo desde o início da sessão e
  terminou misturado com edições em andamento** (7 failed, 12407 passed) — não
  é uma medição limpa de antes nem de depois. Dois dos sete conferidos
  isoladamente já: `test_no_committed_file_states_a_catalogue_size_that_is_not_the_real_one`
  é pré-existente e não relacionado (specs de ondas anteriores citando "85
  integrations", nunca tocadas por mim); `test_the_suggested_address_is_derived_...`
  passa isoladamente (129 provável artefato de corrida do `make verify`
  paralelo). **Os outros quatro (dois de visual regression, um de
  console_gate self-test, um de makefile-target) não foram reconferidos
  isoladamente antes da pausa — pendente na retomada.** A visual regression é
  esperada de verdade: o slide-over mudou de conteúdo (T052 já previa isso) e
  a baseline commitada precisa ser reaceita deliberadamente, como imagem — não
  feito ainda.
- **Um `make verify` limpo, isolado, do início ao fim, não foi obtido nesta
  sessão** — pendência a fechar na retomada.

## Reconferido isoladamente (atualização desta pausa)

- `test_no_committed_file_states_a_catalogue_size_that_is_not_the_real_one`:
  **pré-existente, não relacionado.** Cita "85 integrations" em
  `specs_v3/`, `specs_v4/`, `specs_v5/`, `specs_v6/`, `docs/provenance-map.md`
  — arquivos de ondas anteriores, nenhum tocado por mim.
- `test_the_suggested_address_is_derived_from_discovery_never_a_literal_in_the_route`:
  **passa isolado** (1 passed). Artefato de corrida do `make verify` paralelo.
- `test_a_seeded_pixel_change_fails_the_run_and_emits_a_diff` e
  `test_the_untouched_baselines_still_match`: **passam isolados** (2 passed,
  57s). Mesmo artefato de corrida — meu `console-build`/`console_visual`
  concorrente com o `make verify` de fundo.
- `test_a_seeded_end_to_end_failure_fails_the_gate`: **passa isolado** (1
  passed, 149s). Mesma causa.
- `console_gate visual` rodado direto: **36/36 passam** contra as baselines
  committed. Nenhuma das 36 telas registradas e já baselined foi afetada.

**Achado real, não uma falha**: `console/visual/screens.json` já registra
`integrations-panel-1440-light` (rota `/integrations/alertmanager`) com
`"status": "pending"` — adicionado por outra feature (linguagem da própria
entrada aponta para o corte de vendors, provavelmente 050), preparado mas
nunca capturado. `python -m tools.console_visual accept` **não o captura**
— entradas `"pending"` são deliberadamente excluídas dos dois fluxos
(`compare` e `accept`) da própria ferramenta, exatamente para impedir uma
baseline fabricada. Capturá-la de verdade exige mudar `"status"` para
`"baselined"` em `screens.json`, que é arquivo de escrita única de outra
feature (030) nesta onda — não posso commitá-lo. Meu conteúdo (guide_url em
`alertmanager.endpoint`, min_scope já existente em `alertmanager.token`)
afeta o que essa tela mostraria quando capturada. Deixo nomeado para quem
possui `screens.json`.

Nenhuma das 7 falhas do `make verify` misturado sobrevive à reconferência
isolada — 6 eram artefato de corrida, 1 é pré-existente e alheia. **Ainda
falta**: um `make verify` limpo, único, do início ao fim, sem execução
concorrente — não obtido nesta sessão.

## Pendências nomeadas para a retomada

1. Aplicar o bloco `proxmox` acima (schema + init + docs.md) no merge, ou eu
   mesmo na retomada se a fronteira mudar.
2. Rodar `make verify` limpo do início ao fim, sem edição concorrente, e
   comparar alvo por alvo com a linha de base — único gate ainda não obtido
   limpo.
3. `integrations-panel-1440-light`: capturar deliberadamente e revisar como
   imagem quando `screens.json` puder ser editado (não sou o dono).
4. Editar `console/src/surfaces/screens/first-run.tsx`: uma linha,
   `whereToGetIt: text(record, 'where_to_get_it'),` no `offers.map(...)` —
   arquivo de outra feature no slot, declarado, não aplicado.
5. Seção de documentação no painel — bloqueada até o renderizador de markdown
   existir (outra feature, outro slot).
