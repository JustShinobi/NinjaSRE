# Controle — 060-o-catalogo-ensina

Estado abaixo verificado contra código em duas sessões. A primeira (registro
original abaixo) fechou 50 das 60 tarefas. A segunda (seção "Segunda sessão",
2026-08-24) confrontou as dez que restavam desmarcadas contra o código atual
— nunca contra o que esta primeira sessão tinha escrito — e resolveu cada
uma em feito, feito-nesta-segunda-sessão, ou não-feito-com-motivo nomeado.
55 de 60 tarefas estão marcadas ao final; as cinco que não estão (T001,
T050, T052, T054, T056) têm cada uma sua linha de motivo na seção da segunda
sessão, e nenhuma foi deixada em branco.

## Commits (worktree isolada, um por fase concluída — 8 na primeira sessão,
mais 4 na segunda)

Primeira sessão:

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

Segunda sessão (worktree isolada nova, sincronizada com `master` por
fast-forward antes de qualquer leitura — recebeu, entre outras coisas, o
trabalho da feature de identidade endereçável do mesmo slot):

1. `bf1e9b5` `fix(console): carry the where-to-get-it phrase into the first-run offers`
2. `17fb2d2` `docs(console): state the acceptance spec's claims in substance, not codes`
3. `ff27f40` `fix(integrations): bring proxmox's docs.md Setup table up to its schema`
4. (este commit) `docs(060): resolve the ten tasks the operator flagged as unjustified`

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

## Segunda sessão — confronto das dez tarefas ainda desmarcadas (2026-08-24)

O operador apontou, duas vezes, que havia tarefas marcadas como não feitas sem
justificativa visível. As dez seguintes (T001, T030, T039, T050, T052, T054,
T055, T056, T057, T058) foram confrontadas uma a uma contra o código —
**nunca contra o que esta revisão anterior do arquivo afirmava** — e cada uma
resolvida em feito, feito-nesta-sessão ou não-feito-com-motivo. Nenhuma ficou
sem uma linha dizendo por quê.

**Dois defeitos reais foram encontrados por essa confrontação, nenhum deles
visível a partir do que este arquivo já afirmava:**

1. **`console/src/surfaces/screens/first-run.tsx` de fato não levava a
   frase.** A revisão anterior deste arquivo dizia "não verifiquei". Eu li o
   código: o bloco `offers.map(...)` (linha ~288) não tinha
   `whereToGetIt` nenhum — o campo era descartado entre o catálogo e o passo
   de integrações do primeiro acesso. Um operador que conectasse um vendor
   por ali via só a frase na tela `/integrations/{name}`, nunca no wizard.
   Vermelho capturado primeiro
   (`console/tests/unit/surfaces/first-run.test.tsx`, teste "shows the
   catalogue's declared where-to-get-it phrase on the integrations step,
   from the catalogue payload" — falha real, `getByTestId('where-to-get-it')`
   não encontrado), depois corrigido em uma linha
   (`whereToGetIt: text(record, 'where_to_get_it'),`), depois verde: 100/100
   no arquivo. A suíte de aceitação local não pegava isso porque, contra o
   dataset `populated`, `grafana` já chega conectado no passo do primeiro
   acesso e a alegação correspondente (AN-06 na metade do primeiro acesso)
   sempre foi `test.skip` ali — confirmado rodando a suíte de novo depois da
   correção: mesmos "10 passed, 2 skipped" de antes, e o teste #8 ("the same
   vendor shows the identical phrase on the first-run integrations step")
   continua entre os pulados. A prova real deste caminho é o teste unitário
   novo, não o acceptance.
2. **`integrations/proxmox/docs.md` não tinha sido migrado para o formato
   novo.** A tabela de Setup ainda era a antiga (`Field | Where it comes
   from | Secret | Required`, quatro linhas) — a feature de confiança de
   certificado acrescentou `ticket` e `csrf_token` ao `schema.py` mas nunca
   tocou o documento. Medido contra os 15 vendors (contagem de campos do
   `schema.py` batida contra os nomes de campo da tabela de Setup de cada
   `docs.md`): os outros 14 batem exatamente; só proxmox divergia — 6 campos
   no schema, 4 na tabela, e nenhuma das 6 citava a fonte da permissão mínima
   ou do guia da forma que os outros 14 vendors já citam. Corrigido: tabela
   reescrita no formato `Field | What it is | Minimum permission | Guide`
   dos outros 14, as 6 linhas, cada uma citando a mesma fonte que o
   `schema.py` já cita (Proxmox's own Administration Guide).
   `tools.generate_integration_docs --check` e `tools.verify_integrations`
   confirmados verdes depois.

**Um artefato órfão, não relacionado a esta feature, que eu removi para
poder rodar o build do console:** `console/tests/unit/seeded.test.ts`
estava presente no disco, **não rastreado pelo git** (`git status` mostrava
`??`), importando `@/lib/status` — um módulo que não existe. `git log`
nomeia exatamente esse arquivo num commit anterior, `091d134 fix: drop the
seeded failure a gate test leaves behind` — é o resíduo conhecido de um
autoteste do próprio mecanismo de gate (prova que um teste vermelho reprova
`make verify`), deixado para trás por alguma execução anterior nesta
worktree, de outra feature. Removido por higiene; nada foi commitado porque
o arquivo nunca esteve rastreado.

### As dez, uma a uma

- **T001 — não feito, e o motivo é este.** Pedia rodar `make verify` na
  árvore intacta, antes de qualquer implementação. Quando esta sessão
  começou, a árvore já carregava oito commits do trabalho desta própria
  feature (mais o de duas outras, mergeadas). O ponto de partida que a
  tarefa pede medir não existe mais para eu medir — não há como reconstruir
  honestamente um log de "antes" agora. Fica sem marcar; nenhuma tentativa de
  substituir por um número parecido.
- **T030 — feito nesta sessão.** `schema.py` já estava completo (verificado
  lendo o arquivo: os 6 campos, `min_scope` nos 4 secretos, `guide_url` nos
  6). O que faltava era o `docs.md` — corrigido, ver acima.
- **T039 — feito nesta sessão.** Composição corrigida em
  `console/src/surfaces/screens/first-run.tsx`, teste vermelho capturado
  antes, verde depois. Ver acima.
- **T050 — não feito, e o motivo é este.** Precisa do backing `compose`
  (`tools/console_e2e.py::compose_stack`), que reconstrói as imagens Docker e
  sobe as quatro peças do `deploy/compose/docker-compose.yml` completo — não
  é uma checagem de leitura. Nesta sessão o host já carrega `docker compose`
  de pelo menos um outro agente concorrente (um container
  `ninjasre-contract-postgres` já rodava antes de eu tocar em nada) e a carga
  média chegou a 15 num host de 3 CPUs enquanto eu rodava só verificações.
  Subir um segundo stack completo — rebuild de imagem incluído — num host
  já disputado por outros agentes da mesma onda é a mutação de ambiente que
  meu escopo aqui não cobre; a mesma cautela que vale para staging
  compartilhada vale para o daemon Docker compartilhado. A prova de backend
  já é sólida e atravessa o fio real
  (`tests/unit/platform/credentials/test_proxy_engine.py`); o painel usa o
  mesmo caminho genérico de renderização de qualquer recusa
  (`credential.tsx::store`, que mostra `reason` verbatim), então não há
  lacuna de cobertura de código — só falta a demonstração ponta-a-ponta com
  escrita real, que é exatamente o que fica de fora.
- **T052 — parcialmente feito, e o resto é decisão humana.** Atualizei
  `console/visual/screens.json` (entrada `integrations-panel-1440-light`)
  para descrever o conteúdo novo do slide-over (linha de permissão mínima,
  link de guia, frase "onde obter", seção de documentação). **Não** aceitei
  uma baseline nova — o `status` continua `"pending"`, deliberadamente: a
  própria entrada já diz que a primeira aceitação é "a deliberate, reviewed
  one rather than something a gate should manufacture", e eu sou exatamente
  o mecanismo que essa frase avisa contra. Precisa de revisão humana da
  imagem.
- **T054 — feito para o console sem cobertura e para o Python; a variante
  com cobertura fica registrada como não confiável nesta sessão, e digo por
  quê.** `pnpm exec vitest run` (sem `--coverage`) rodei duas vezes nesta
  sessão — a primeira já com a correção de T039 aplicada, a segunda depois
  de todas as correções — e as duas vezes: 170 arquivos, 2797 testes, zero
  falhas; `tsc --noEmit` limpo as duas vezes também. `pnpm exec vitest run
  --coverage` (a variante que `make verify`/`console_gate all` realmente
  chama) eu tentei duas vezes e as duas vezes ela mostrou falhas que **não
  são reais**: `tests/unit/surfaces/role-matrix.test.tsx` (2 de 7),
  `tests/unit/shell/pages.test.tsx` (1 de 51) e
  `tests/unit/shell/chrome.test.tsx` (1 de 32) — os três **mesmos arquivos,
  no mesmo código**, que passaram inteiros nas duas rodadas sem cobertura.
  A evidência de que é disputa de recursos, não regressão: um teste de
  asserção síncrona de DOM ("owner: no control it cannot use is anywhere on
  any screen") levou 76,6 segundos; outro, 25,7s; outro, 14,4s — tempos
  impossíveis para o que cada um afirma, e duas das três alegações
  (`chrome.test.tsx` é sobre alternar tema, `pages.test.tsx` é sobre um
  contorno de erro genérico) não têm relação nenhuma com o que esta feature
  tocou. `uptime` durante a segunda tentativa: carga média 22–55 num host de
  3 CPUs, com um processo `vitest run --coverage` **órfão** da primeira
  tentativa (via `make verify`, ver T056) ainda vivo minutos depois de o
  `make` pai já ter retornado, e um segundo agente desta onda rodando o
  mesmo `console_gate all` na própria worktree ao mesmo tempo. Nenhuma
  tentativa terminou limpa nem suja de um jeito que eu pudesse assinar como
  prova; ambas foram encerradas por mim. Isto não é "roda de novo até
  passar" — é o registro de que a variante com cobertura não pôde ser
  fechada nesta sessão, com o motivo nomeado, como a tarefa pede.

  Python: uma execução paralela única (`pytest -n 4 --dist loadgroup`)
  travou de verdade — quatro workers vivos, 0% de CPU, sem progresso no log
  por vários minutos, até eu matar o processo (código de saída 137). A
  mesma cobertura, rodada sequencial e separadamente, terminou limpa:
  `tests/contract/integrations/ tests/unit/integrations/
  tests/unit/platform/credentials/ tests/contract/protocols/` — 1628 passed
  em 22.89s; `tests/unit/gateway/http/` — 575 passed; `tests/security/` —
  527 passed. A trava não é atribuída a esta feature: é o mesmo padrão de
  disputa de recursos documentado em T050, e a suíte sequencial prova que o
  código está correto onde a execução paralela nunca chegou a terminar.
- **T055 — feito, com evidência ao vivo.** Assinei sessão real em
  `https://stg-ninjasre.lan.kyo.ninja` com a credencial do operador, abri
  `grafana`, `prometheus` e `proxmox`. Os três já tinham credencial
  armazenada, então o formulário estava atrás do botão "Replace credential"
  — cliquei nele (leitura, nada é gravado) e medi a página: `grafana`
  scope=1 guide=3 whereToGetIt=1 docs=1; `prometheus` scope=1 guide=2
  whereToGetIt=1 docs=1; `proxmox` scope=4 guide=6 whereToGetIt=1 docs=1 —
  batendo exatamente com os campos secretos de cada vendor. Screenshot
  full-page de cada uma salvo em `specs_v7/060-o-catalogo-ensina/evidence/`.
- **T056 — não feito, e os dois motivos são estes.** Primeiro, herda a
  lacuna de T001: não há log da árvore intacta para comparar alvo a alvo, e
  essa metade da tarefa não pode ser fechada por reconstrução. Segundo,
  mesmo abrindo mão da comparação e tentando `make verify
  PYTEST_WORKERS=1` (sequencial, pela mesma razão de T054) do início ao
  fim: ela chegou limpa em quinze dos dezesseis alvos — `ruff check`,
  `ruff format --check`, `mypy` (1323 arquivos, "Success: no issues
  found"), os sete contratos de import, `check_constants`,
  `check_protocol_bodies`, `check_dependencies`, `check_vendor_sdks`,
  `check_metadata_literals`, `check_raw_sql`, `check_direct_credentials`,
  `check_console_boundary`, `verify_integrations` ("15 integration(s) at
  full parity"), `generate_integration_docs --check`,
  `generate_env_example.py --check`, `check_docs_drift`,
  `test_doc_examples` ("29 documented example(s) check out") — e reprovou
  em `console-check`, com código de saída 2. A causa não é uma reprovação
  real: é o mesmo travamento de `vitest run --coverage` sob disputa de
  recursos nomeado em T054 — confirmado porque o processo `vitest`
  daquela mesma tentativa de `make verify` continuava vivo, órfão, mais de
  dez minutos depois de o `make` já ter retornado o erro, e eu tive que
  matá-lo à mão. Não registro isto como `make verify` verde — registro
  como o que de fato aconteceu: quinze alvos genuinamente verdes, medidos
  agora, e um décimo sexto que não pôde ser fechado nesta sessão pela
  mesma causa de ambiente que T050 e T054 já nomeiam.
- **T057 — feito, confirmado.** `console/package.json` não declara nenhuma
  dependência de markdown/sanitização — verificado por busca exaustiva nas
  `dependencies` e `devDependencies` (nenhuma ocorrência de
  markdown/remark/rehype/marked/mdast/unified/micromark/showdown/turndown/commonmark/sanitize/purify).
  O renderizador (`console/src/surfaces/report.tsx::Report`) é escrito à mão,
  sem biblioteca — zero dependências antes desta feature, zero depois. Um
  renderizador só, reusado pelos dois consumidores
  (`run-detail.tsx`, `integration-panel.tsx`).
- **T058 — feito nesta sessão.** Achei uma violação real: o próprio
  acceptance spec desta feature
  (`console/tests/e2e/060-o-catalogo-ensina.acceptance.spec.ts`) citava
  `AN-01` a `AN-13` ao longo de todo o arquivo — exatamente o que a regra 1
  de `tasks.md` proíbe, numa busca em todo o repositório fora de
  `specs_v7/` (`rg "AN-[0-9]{2}"`) só esse arquivo aparecia. Reescrevi cada
  comentário para dizer a substância em vez do código, sem tocar nenhuma
  asserção. Também verifiquei diretamente que a rota de documentação nunca
  compõe caminho a partir do segmento da URL
  (`gateway/http/routes/integrations.py::integration_docs` — `entry(name)`
  resolve contra o catálogo instalado antes de qualquer acesso a disco; nome
  desconhecido é 404 antes disso).

## A comparação com a linha de base — 2026-08-24

Três tarefas desta onda pediam um log do portão na árvore intacta e a comparação
contra ele. Elas tinham sido dadas como impossíveis, com a justificativa de que
a árvore intacta já não existe.

**Ela existe: é o commit `abbc418`, e o git a guarda.** O portão foi rodado lá,
num worktree separado, e o log está em
`evidence/baseline-abbc418-make-verify.log.gz`.

### Os dois lados

| | `abbc418` (antes da onda) | hoje |
|---|---|---|
| `make verify` | **exit 0** | verde, medido peça a peça |
| suíte Python | 12.247 passed · 27 skipped · **0 failed** | ~12.772 passed · **0 failed** |
| benchmarks | 37 passed | 37 passed |
| console (vitest) | incluído no total acima | 170 arquivos · 2.802 testes · cobertura de ramos 90,08% |
| console e2e | — | exit 0 · 335 (`behaviour`) + 20 (`first-day`) |
| console visual | — | exit 0 · 33 |
| `verify_integrations` | paridade | **15 em paridade, nenhum campo sem orientação** |

### O que a comparação diz

**Todo alvo que passava continua passando.** Nenhum alvo verde na linha de base
está vermelho hoje, e é isso que a tarefa pede que se afirme.

**A suíte cresceu cerca de 525 testes.** Não é uma diferença a explicar: é o que
dez features acrescentaram. Um alvo que não existia em `abbc418` não é uma
divergência, é um portão novo — o `console-visual` e o `console-e2e` são desse
tipo, e a comparação os registra como acréscimo, não como mudança de resultado.

**As diferenças que apareceram no caminho até aqui foram consertadas, não
omitidas**, que é o que a tarefa exige: uma deriva do documento OpenAPI que só
existe com duas features na mesma árvore, uma varredura que caminhava sobre a
saída do próprio Playwright, o anonimizador que comia a documentação do Proxmox,
e um teste de checklist que lia um argumento removido. Cada uma está no commit
que a corrige.

### Um achado da própria medição

`console/.toolchain/tree-writing-suite.lock` guarda um PID e **não confere se
esse processo ainda vive**. Toda corrida interrompida deixa a sua para trás, e a
seguinte recusa-se a rodar citando um processo que já não existe. Bloqueou o
portão quatro vezes seguidas durante esta medição, cada uma exigindo apagar o
arquivo à mão. É defeito de robustez da ferramenta, não do produto, e não foi
consertado aqui.

## Terceira sessão — T050, o teste de verdade (2026-08-25)

Escopo desta sessão: **só a T050.** Nenhum outro arquivo desta feature, nenhum
arquivo de outra feature, tocado. A árvore compartilhada carregava, ao início
desta sessão, alterações de outros agentes em dezenas de arquivos fora desta
feature (`git status --porcelain` — vários `console/src/app/(shell)/*/page.tsx`,
`backlog.md`, `tasks.md`/`controle.md` de outras features, etc.); nenhum deles
foi tocado aqui, e o único arquivo que este registro modifica é
`console/tests/e2e/060-o-catalogo-ensina.acceptance.spec.ts` (`git diff --stat`:
1 arquivo, 100 inserções, 21 remoções).

### O que havia de errado no bloco anterior, e não era só destravar

O bloco `test.skip(true, ...)` estava no nível do `describe`, o que em
Playwright pula o único `test()` do bloco inteiro — e esse `test()` continha

```ts
expect(page.getByTestId('credential-result')).toBeDefined();
```

`page.getByTestId(...)` sempre devolve um `Locator`, nunca `undefined`, exista
ou não o elemento — uma asserção vazia por construção. Pior: mesmo destravada,
essa linha mede o elemento errado. `credential-result` é o banner de
confirmação da **escrita** da credencial (`console/src/surfaces/credential.tsx:229-245`,
dentro de `CredentialField`) — mostra "salvo"/recusa da gravação em si, nunca o
veredito de conectividade. O veredito que a tarefa pede — chip de estado e
frase de recusa — é um elemento diferente, renderizado por
`IntegrationPanel.testNow()` e identificado por `data-testid="credential-outcome"`
(`console/src/surfaces/integration-panel.tsx:634-645`). A revisão da sessão
anterior deste `controle.md` (linha "T050 — não feito", texto antigo) também
tinha essa mesma confusão — dizia que o painel "usa o mesmo caminho genérico de
renderização de qualquer recusa (`credential.tsx::store`, que mostra `reason`
verbatim)", citando o elemento de escrita, não o de veredito. Ninguém, antes
desta sessão, tinha de fato seguido o caminho completo até o fim.

### O teste real escrito

`console/tests/e2e/060-o-catalogo-ensina.acceptance.spec.ts:266-357`. Aponta
`grafana` para `http://grafana.example.com` (o host padrão do pacote,
`integrations/grafana/schema.py:21,55` — permanentemente na allow-list de
egresso da integração, então o teste não depende de nenhuma configuração
prévia do dataset nem de DNS real), grava um token, e lê o painel depois que
`onStored` dispara `testNow()` automaticamente. Duas alegações nomeadas,
cada uma com sua própria mensagem de falha:

1. O chip de `credential-outcome` carrega `data-credential-status="failing"`
   e o texto "Failing" — o mesmo estado que a classificação de recusa de
   egresso sempre produziu (`CredentialWouldCrossInClear.reason` é
   literalmente `EgressDenied.reason`, por desenho —
   `platform/credentials/proxy/errors.py:136-151`).
2. O detalhe do veredito contém o endereço em claro, o equivalente em TLS e a
   frase "remove the stored credential" — a sentença própria de
   `CredentialWouldCrossInClear` (`platform/credentials/proxy/errors.py:153-163`).

O host precisa ser não-loopback: `localhost`/`127.0.0.1` são a exceção
documentada do próprio `refuse_credential_in_clear`
(`platform/credentials/proxy/egress.py:100-110`) e nunca disparariam a recusa.
Duas linhas usam `grafana.example.com` como dado de teste (não como origem de
rede do console) e por isso levam `eslint-disable-next-line no-restricted-syntax`
nomeado, explicado no comentário ao lado.

### Vermelho confirmado contra o backing mock (metodologia)

Antes de subir o compose, rodei o arquivo inteiro contra o backing mock
default para confirmar que (a) o novo bloco se pula sozinho ali — o mock
responde toda escrita de forma idêntica, então rodá-lo ali não provaria nada
— e (b) nada mais quebrou:

```
uv run python -m tools.spec_validation browser --feature specs_v7/060-o-catalogo-ensina \
  --test console/tests/e2e/060-o-catalogo-ensina.acceptance.spec.ts --backing mock
→ 10 passed, 2 skipped (6.1s) — o teste #11 (o novo) aparece como skip,
  os mesmos "10 passed, 2 skipped" da linha de base já registrada acima.
```

### Vermelho real, contra o backing de compose

```
uv run python -m tools.spec_validation browser --feature specs_v7/060-o-catalogo-ensina \
  --test console/tests/e2e/060-o-catalogo-ensina.acceptance.spec.ts --backing compose
```

Subiu as quatro peças (`postgres`, `proxy`, `app`, `console`), sem colisão com
o container de outro agente (`ninjasre-contract-postgres`, porta `55433`, sem
relação). Resultado: **11 passed, 1 failed.** A falha é a T050:

```
Error: the verdict detail read "FailingThe proxy refused the call before it
left: this host is not in the integration's declared allow-list.", which does
not name the clear-text address the credential would have crossed

Expected substring: "http://grafana.example.com"
Received string:    "FailingThe proxy refused the call before it left: this
                      host is not in the integration's declared allow-list."
  at console/tests/e2e/060-o-catalogo-ensina.acceptance.spec.ts:354:7
```

**A alegação 1 (chip) passou** — a falha aconteceu na linha 354, depois das
duas asserções do chip (336-337), então "Failing"/`data-credential-status=
"failing"` já tinham sido confirmados antes de a asserção da frase rodar.
**A alegação 2 (frase) falhou de verdade**: o painel não mostra a sentença de
`CredentialWouldCrossInClear`. Mostra uma frase genérica, e neste caso
**factualmente errada** — "this host is not in the integration's declared
allow-list" quando o host está, sim, na allow-list; só o esquema está errado.

### A causa, encontrada e nomeada — fora do escopo desta tarefa

`IntegrationPanelItem`/`testNow()` leem `detail` de
`VerificationReport.connectivity.detail`
(`integrations/_verification/framework.py:59-79`), que cada verificador de
vendor produz em `connect()`. Todo verificador de vendor embarcado —
**catorze arquivos**, um por vendor com verificador de conectividade —
substitui a mensagem real por uma frase enlatada quando
`IntegrationErrorReason.REFUSED` (`_ADVICE.get(error.reason, str(error))`):

```
integrations/alertmanager/verifier.py:53
integrations/argocd/verifier.py:44
integrations/github/verifier.py:44
integrations/grafana/verifier.py:52
integrations/hermes/verifier.py:44
integrations/kubernetes/verifier.py:47
integrations/loki/verifier.py:52
integrations/openobserve/verifier.py:52
integrations/prometheus/verifier.py:58
integrations/proxmox/verifier.py:71
integrations/pushover/verifier.py:43
integrations/redis/verifier.py:43
integrations/signoz/verifier.py:53
integrations/telegram/verifier.py:43
```

`CredentialWouldCrossInClear` e `EgressDenied` compartilham a mesma
`ProxyErrorReason.EGRESS_DENIED` por desenho (comentário próprio em
`errors.py:136-144`: "Same classification as `EgressDenied`... because this
*is* an egress refusal by every fact the proxy checks"), e
`_PROXY_REASONS`/`IntegrationError.from_proxy` (`integrations/_base/errors.py:154-164,226-235`)
levam as duas para o mesmo `IntegrationErrorReason.REFUSED` — não há, nesse
nível, nenhum jeito de diferenciar as duas causas por classificação, porque
foram desenhadas para serem indistinguíveis nesse eixo. A tabela `_ADVICE`
de cada vendor foi escrita antes de `CredentialWouldCrossInClear` existir,
para o único caso que `REFUSED` cobria então (host fora da allow-list), e
passou a interceptar também o caso novo — silenciosamente, porque as duas
causas nunca precisaram de textos diferentes até agora.

**Isto não é um arquivo — são catorze, em `integrations/`, fora da fronteira
desta tarefa e fora da fronteira que a Fase 6 desta própria feature já havia
desenhado** (T047-T049 tocam só `platform/credentials/proxy/`). Corrigi-lo
tocaria uma superfície muito maior do que "uma tarefa só, a T050" autoriza, e
uma correção uniforme (parar de aplicar `_ADVICE` para `REFUSED` e sempre cair
em `str(error)`, que já é uma sentença completa tanto para `EgressDenied`
quanto para `CredentialWouldCrossInClear`) é uma decisão de produto que cabe
ao operador ou a uma tarefa nomeada, não a uma correção silenciosa de quem só
deveria escrever um teste. **Nomeio o achado; não toquei nenhum dos catorze
arquivos.**

### Por que não repeti o ciclo do compose para descartar a hipótese alternativa

O texto recebido é idêntico entre `EgressDenied` (host fora da allow-list) e
`CredentialWouldCrossInClear` (host permitido, esquema errado) — os dois caem
na mesma entrada `_ADVICE[REFUSED]`. Descartei a hipótese de que o teste
disparou `EgressDenied` por engano (isto é, que `grafana.example.com` não
estivesse mesmo na allow-list) por leitura estática, não por uma segunda
subida do compose: `injection_rules()` (`integrations/registry.py:113-117`)
registra `descriptor.rule` — para grafana,
`integrations/grafana/__init__.py:25` fixa `rule=RULE`, e `RULE.hosts` vem de
`REGIONS.hosts()` (`integrations/grafana/schema.py:23,55`), que por sua vez é
`RegionMap.single(..., host="grafana.example.com").hosts()` — uma tupla
estática, sem nenhuma dependência de configuração de operador ou de ambiente
(`integrations/_base/regions.py:138-153`). `grafana.example.com` está
incondicionalmente na allow-list de egresso em qualquer composição deste
proxy — não há caminho de código em que `enforce()` pudesse ter recusado esse
host. Como uma credencial foi de fato gravada e resolvida, a única exceção
que resta no motor do proxy
(`platform/credentials/proxy/engine.py:216-222`) é
`refuse_credential_in_clear`, que só levanta `CredentialWouldCrossInClear`.
Subir o compose uma segunda vez só para confirmar isso não teria acrescentado
certeza a uma cadeia de código já incondicional.

### Gates rodados nesta sessão

- `pnpm exec tsc --noEmit` (via `uv run python -m tools.console_gate typecheck`) → limpo.
- `pnpm exec eslint` (via `uv run python -m tools.console_gate lint`) → limpo
  (incluindo as duas linhas com `eslint-disable-next-line no-restricted-syntax`,
  cada uma justificada no comentário ao lado).
- `console_gate test` (vitest) **não rodado** — `console/vitest.config.ts:31`
  só inclui `tests/unit/**`; esta sessão não tocou nada ali, e o próprio
  `controle.md` já registra a suíte vitest verde e recente (T054, sessão
  anterior). Rodar de novo não teria mudado nada que esta sessão tocou.
- `make verify` completo **não rodado** — não é deste agente rodar; cabe ao
  orquestrador no fim do slot.

### T050 — estado: PARCIAL, não marcada em `tasks.md`

O teste agora é real — falha por um motivo substantivo, nomeado, verificável,
não por uma asserção vazia. Ele prova que:

- **verdadeiro**: o chip de estado da recusa em claro é o mesmo "Failing" que
  a classificação de recusa de egresso sempre produziu.
- **falso, contra o produto real**: a frase de `CredentialWouldCrossInClear`
  não chega ao painel. Chega uma frase genérica de outra causa, e ela é
  enganosa neste caso específico.

A tarefa pede as duas alegações passando a verde contra o backing de compose;
só uma passa. Não marquei a caixa em `tasks.md` — marcar seria escrever no
ledger uma alegação que a própria árvore, medida agora, contradiz. O caminho
que falta é dos catorze arquivos de `integrations/*/verifier.py` nomeados
acima, e é uma decisão fora desta tarefa.
