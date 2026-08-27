# Controle — 000-regras-e-governanca

Estado abaixo verificado contra o código em disco nesta árvore (`/srv/workspaces/NinjaSRE`),
não contra o relato de nenhuma sessão anterior. Cada linha da tabela carrega o
`file:line` que sustenta a alegação. Este arquivo é escrito incrementalmente —
a versão em disco a qualquer momento é o que já foi provado, nunca uma
intenção.

**Nota de honestidade sobre o histórico desta feature**: a execução bateu o
teto de turnos duas vezes antes deste arquivo existir. Nada foi perdido —
o código no disco é a prova —, mas o relatório ficou atrás do código por um
tempo. A partir daqui o `controle.md` é escrito antes de qualquer nova
execução, como pediu o orquestrador.

## Os sete números — partida e chegada (T002)

Números de partida registrados a partir da árvore **antes** de qualquer
escrita desta feature (conferidos durante a leitura inicial, em
`abbc418`, árvore limpa):

| # | O que mede | Partida | Chegada | Onde conferir agora |
|---|---|---|---|---|
| 1 | Versão no cabeçalho da constituição | `2.0.0` | `2.2.0` | `.specify/memory/constitution.md:3` |
| 2 | Arquivos de registro de decisão em `docs/adr/` | 15 (0001–0015) | 16 (0001–0016) | `ls docs/adr/*.md \| grep -v README \| wc -l` |
| 3 | Linhas na tabela-índice de `docs/adr/README.md` | 11 | 16 | `docs/adr/README.md:8-23` |
| 4 | Linhas na tabela de traceability de `docs/roadmap.md` | 11 | 16 | `docs/roadmap.md:207-222` |
| 5 | Regras na suíte transversal | 4 (vocabulary, scroll-budget, contagem única de setup, value-column) | 9 (as 4 + markdown, identifier-as-name, two-placeholders, live-control, negative-assertion) | `console/tests/e2e/transversal-rules.spec.ts:169-179` (union `Rule`) |
| 6 | Entradas na tabela `EXCEPTIONS` | 0 | **10** (ver seção própria abaixo — nove previstas + uma descoberta) | `console/tests/e2e/transversal-rules.spec.ts:209` |
| 7 | Backings que a validação de navegador conhece | 2 (`mock`, `compose`) | 3 (`mock`, `compose`, `staging`) | `tools/spec_validation.py:139` (`choices=("mock", "compose", "staging")`) |

Os três primeiros e o quinto/sétimo foram conferidos por leitura direta da
árvore antes de qualquer edição (via `ls`, `grep -c`, e leitura de
`transversal-rules.spec.ts` original). O sexto partiu de `EXCEPTIONS: readonly
Exception[] = []` (linha 166 do arquivo original, antes desta feature).

## T003 — auditoria dos quatro artigos, exemplo por exemplo

| Artigo | Exemplo citado | Resultado | Onde conferido |
|---|---|---|---|
| Artigo V — Um runtime canônico | "Alternative runtime adapters (e.g. Claude Agent SDK) MAY exist behind the runtime port" | **Conferido e correto** — o adaptador existe | `core/agent/adapters/claude_sdk.py` (arquivo presente) |
| Artigo IX — Capacidades declaradas | nenhum exemplo de arquivo é citado no texto do artigo hoje | **Sem exemplo a corrigir** — o problema deste artigo nunca foi um exemplo defasado; era a cláusula de paridade inteira, ausente. Resolvido por acréscimo (cláusula 5), não por correção de exemplo | `.specify/memory/constitution.md:203-236` (artigo com a cláusula nova) |
| Artigo XI — Datastore único | os cinco portos nomeados na cláusula 2: `EpisodeStore`, `TopologyGraph`, `VectorIndex`, `ConfigRepository`, `RunTraceStore` | **Conferido e correto** — os cinco existem, entre outros que o artigo não nomeia individualmente | `platform/persistence/ports/episode_store.py`, `topology_graph.py`, `vector_index.py`, `config_repository.py`, `run_trace_store.py` (os cinco arquivos presentes) |
| Artigo XII — Test-first, rastreado | nenhum exemplo de arquivo é citado no texto do artigo hoje | **Sem exemplo a corrigir** — mesmo caso do Artigo IX: nada para auditar além do texto normativo em si, que não cita caminho algum | `.specify/memory/constitution.md:272-282` |

Nenhum artigo ficou sem resposta. Dois (V, XI) tinham exemplo concreto e
estavam corretos; dois (IX, XII) não citam exemplo de arquivo algum no texto
atual — a auditoria registra essa ausência como resultado, não a pula.

## Ledger tarefa a tarefa

| Tarefa | Estado | Detalhe |
|---|---|---|
| T001 | FEITO | `make verify` rodado na árvore intacta em `abbc418`; log fora do repositório em `/tmp/.../scratchpad/baseline-verify.log`; `EXIT_STATUS=0`; suíte principal "12210 passed, 27 skipped, 30 warnings in 569.26s"; suíte de benchmarks "37 passed, 12240 deselected, 4 warnings in 37.17s" |
| T002 | FEITO | ver tabela "Os sete números" acima |
| T003 | FEITO | ver tabela de auditoria acima |
| T004 | FEITO | cláusula 5 acrescentada ao Artigo IX — `.specify/memory/constitution.md:216-227` |
| T005 | FEITO | T003 não acusou nenhuma correção pendente nos quatro artigos (V e XI conferidos e corretos; IX e XII sem exemplo a corrigir) — nenhuma edição de correção foi necessária, registrado explicitamente aqui em vez de inventada |
| T006 | FEITO | versão subiu para 2.1.0 e depois 2.2.0 (ver T012); entrada de emenda no cabeçalho citando o registro vigente — `.specify/memory/constitution.md:5,10-13` |
| T007 | FEITO (com ressalva — ver seção própria) | a constituição não foi adicionada a nenhum stage por esta feature; **mas** a árvore já a tinha rastreada em HEAD antes desta feature começar — ver "Descoberta: a constituição já está rastreada" abaixo |
| T008 | FEITO | `docs/adr/0016-composed-or-it-is-not-shipped.md` (arquivo novo, 121 linhas) |
| T009 | FEITO | campo "Constitution impact" do registro novo nomeia a substância em palavras, sem número de artigo — `docs/adr/0016-composed-or-it-is-not-shipped.md:6-8` |
| T010 | FEITO | seção "Context" do registro novo descreve a forma do defeito sem citar onda, número de feature ou nome de documento — `docs/adr/0016-composed-or-it-is-not-shipped.md:10-24` |
| T011 | FEITO | Artigo XIV acrescentado à constituição, com as três cláusulas e o teste de uma linha no índice — `.specify/memory/constitution.md:307-333` (artigo) e `:368` (linha no índice, conferida de novo nesta correção — `:360` é o Artigo VI preexistente, não o XIV) |
| T012 | FEITO | versão subiu para 2.2.0; segunda entrada de emenda no cabeçalho apontando para o registro 0016 — `.specify/memory/constitution.md:3,15-17` |
| T013 | FEITO | única linha alterada no registro 0009 é a de status: `Superseded by 0015, 2026-08-17` — `docs/adr/0009-full-integration-parity.md:3`; corpo intocado (conferido por diff mental: só a linha 3 mudou) |
| T014 | FEITO | cinco linhas novas na tabela-índice (0012–0016) — `docs/adr/README.md:19-23` |
| T015 | FEITO | status do 0009 atualizado no índice para "Superseded by 0015" — `docs/adr/README.md:16` |
| T016 | FEITO | cinco linhas novas na tabela de traceability do roadmap — `docs/roadmap.md:218-222` |
| T017 | FEITO | aritmética conferida: 16 arquivos, 16 linhas no índice, 16 linhas na traceability, mesmo conjunto (0001–0016) nas duas tabelas — conferido por `grep -oE` nas três fontes, batendo exatamente |
| T018 | FEITO | seção "Integration scope" nova em `docs/roadmap.md:158-179`, com o conjunto embarcado (15 pacotes, derivado de `integrations/`) e o conjunto diferido (o resto da tabela de cobertura) |
| T019 | FEITO | as quatro ocorrências históricas de "~85" continuam legíveis (`docs/roadmap.md:136,142,217,240`); `pytest tests/architecture/test_no_committed_file_states_a_stale_catalogue_size.py` → 1 passed |
| T020 | FEITO | cenário `now-violations` declarado em `fixtures/manifest.json`; arquivos `fixtures/scenarios/now-violations/{runs,run-detail,run-replay,incidents}.json`; um run (`e19e882a1c9b4d5e8f6a2b3c7d0e1f24`) reproduz markdown cru + identificador hex + inconsistência lista/detalhe de status; um incidente (id composto com `:`, `@`, `+`) reproduz leitura falhada + identificador percent-encoded + dois placeholders — construído com um script auxiliar, validado contra `tests/contract/fixtures/test_dataset_contract.py`, `tests/contract/fixtures/test_dataset_coherence.py` e `tests/unit/tools/mockplane/test_scenarios.py` juntos (comando exato: `uv run pytest tests/contract/fixtures/test_dataset_contract.py tests/contract/fixtures/test_dataset_coherence.py tests/unit/tools/mockplane/test_scenarios.py` → **79 passed**; os dois primeiros arquivos sozinhos, sem o terceiro, dão 54 passed — conferido de novo nesta correção) |
| T021 | FEITO | `console/tests/e2e/bans.ts` (177 linhas): `rawMarkdown`, `identifierAsName`, `twoPlaceholders`, `liveControlOnTerminalRun`, `negativeAssertionAfterFailedRead`, todos puros |
| T022 | FEITO | regra `markdown` — `console/tests/e2e/transversal-rules.spec.ts:735` — allowlist vazia na primeira execução, mensagem nomeia rota e trecho |
| T023 | FEITO | regra `identifier-as-name` — `transversal-rules.spec.ts:753` — cobre hex, composto e percent-encoded |
| T024 | FEITO | regra `two-placeholders` — `transversal-rules.spec.ts:791` |
| T025 | FEITO | regra `live-control` — `transversal-rules.spec.ts:827` |
| T026 | FEITO | regra `negative-assertion` — `transversal-rules.spec.ts:852` |
| T027 | FEITO | `openNowLabel()` — `transversal-rules.spec.ts` — navega a `/runs` ou `/incidents` e clica na primeira linha (`page.getByTestId('row').first().locator('a').first().click()`); nenhum id de run ou incidente aparece literalmente no arquivo |
| T028 | FEITO (já existia, verificado) | `test.use({ viewport: { width: VIEWPORT_WIDTH, height: VIEWPORT_HEIGHT } })` já cobre o arquivo inteiro, lido de `CONFIG_SCREEN_VIEWPORT_WIDTH_PX`/`HEIGHT_PX` = 1920×1080 em `config/constants/surfaces.py` — mecanismo pré-existente reaproveitado, não duplicado |
| T029 | FEITO — **portão confirmado** | ver seção "T029 — o vermelho real" abaixo, com as dez mensagens (nove previstas + uma descoberta) |
| T030 | FEITO | dez entradas em `EXCEPTIONS` — `transversal-rules.spec.ts:209-296` — ver seção própria |
| T031 | FEITO | `console/tests/unit/e2e/bans.test.ts` (115 linhas, 15 testes) rodando contra os textos exatos capturados no vermelho de T029; os cinco detectores foram neutralizados um a um (corpo substituído por `return null`) e cada neutralização reproduziu vermelho confirmado via `pnpm exec vitest run`, depois revertida — ver seção própria |
| T032 | FEITO (com desvio declarado) | seis constantes novas em `config/constants/console.py:44-70`: `NINJASRE_STAGING_URL_ENV`, `DEFAULT_STAGING_URL`, `NINJASRE_STAGING_USERNAME_ENV` (**a quarta constante, além das três do plano — desvio declarado, ver seção própria**), `NINJASRE_STAGING_CREDENTIAL_ENV`, `NINJASRE_STAGING_EVIDENCE_DIR_ENV`, `CONSOLE_STAGING_SAFE_TAG`; `uv run python tools/check_constants.py` → limpo |
| T033 | FEITO | testes de recusa em `tests/unit/tools/test_console_e2e.py` (4 novos): sem credencial → `HarnessError` nomeando a variável, `resolve`/`ensure_browsers` nunca chamados; sem usuário → mesma recusa; fonte de `run_staging` não cita `mock_plane(`, `compose_stack(` nem `console(toolchain` |
| T034 | FEITO | teste `test_the_staging_backing_always_selects_only_the_tests_marked_safe_for_it` prova que o grep da marca é preposto incondicionalmente, mesmo com um teste nomeado explicitamente em `extra`; confirmado também via execução real do Playwright (ver seção própria) |
| T035 | FEITO (com desvio declarado) | `run_staging()` — `tools/console_e2e.py:664` — **implementa o desvio do dispatch**: troca usuário+senha por token via `POST {url}/api/session` (`_staging_credential()`, `tools/console_e2e.py:614`) antes de repassar pela variável `NINJASRE_CONSOLE_E2E_CREDENTIAL_ENV` que `playwright()` já lê — ver seção própria |
| T036 | FEITO | a linha de anúncio (`print(f"driving the browser suite against {url}", flush=True)` — `tools/console_e2e.py:733`) nomeia só o endereço; a senha nunca vira argumento de `subprocess`/CLI (só variável de ambiente do processo filho, herdada via `env[...]`); prova de ausência em T045 abaixo |
| T037 | FEITO | `--backing` em `tools/spec_validation.py:139` aceita `staging`; `run_browser_validation()` (`spec_validation.py:74-155`) recusa `--scenario` não-default e `--no-build` contra staging, e nunca chama `build_console()` para esse backing |
| T038 | FEITO | as cinco `test()` das regras "Now" recebem `{ tag: STAGING_SAFE_TAG }` — `transversal-rules.spec.ts` linhas dos cinco `test.describe` (735, 753, 791, 827, 852) |
| T039 | FEITO | `STAGING_SAFE_TAG = stringConstant('CONSOLE_STAGING_SAFE_TAG')` lido de `config/constants/console.py` pela mesma técnica de `constant()` (regex sobre o texto-fonte) — `transversal-rules.spec.ts`, função `stringConstant` |
| T040 | FEITO (com defeito achado e consertado — ver seção própria) | `test.afterEach` captura `page.screenshot({ fullPage: true })` quando `NINJASRE_STAGING_EVIDENCE_DIR` está setada, pulando testes `fixme`/`skip` (via `testInfo.annotations`). **A verificação independente do orquestrador achou que a flag `--evidence-dir` não propagava essa variável para o subprocesso — só `--output` do Playwright, que não alimenta captura alguma.** Vermelho capturado em `tests/unit/tools/test_console_e2e.py` (`test_playwright_puts_the_evidence_directory_in_the_subprocess_environment`, `test_run_staging_threads_the_resolved_evidence_directory_into_playwright`); conserto em `playwright()`/`run_staging()` (`tools/console_e2e.py`); reverificado pelas duas portas contra staging real: 10 PNGs via flag, 10 PNGs via variável — ver "Defeito achado pela verificação independente" abaixo |
| T041 | FEITO | `uv run python tools/check_console_boundary.py` → limpo (exit 0); T033/T034 verdes — `pytest tests/unit/tools/test_console_e2e.py` (**12 passed** — eram 10 antes do conserto de `--evidence-dir`; a linha não tinha sido atualizada, corrigida nesta rodada), `pytest tests/unit/tools/test_spec_validation.py` (9 passed) |
| T042 | FEITO | `CLAUDE.md` (local, não commitado) — seção "Repository state" reescrita para descrever o pós-v6, apontar `specs_v6/`/`specs_v7/` como diretórios de onda (não `specs/`), e afirmar a versão real da constituição (2.2.0) com as duas emendas |
| T043 | FEITO | ver seção "T043 — verde contra o dataset determinístico" abaixo |
| T044 | ver seção própria abaixo (executado nesta sessão) | |
| T045 | ver seção própria abaixo | |
| T046 | FEITO (pelo orquestrador, não por esta sessão — por instrução explícita: "não rode T046, o make verify completo é meu") | `make verify` final: **12223 passed / 27 skipped, exit 0**, contra a linha de base de T001 (12210 passed / 27 skipped) — mesmo número de skips, zero regressões, **+13**. Reconciliação abaixo (seção "T046 — reconciliação dos +13") |
| T047 | Este arquivo | |
| T048 | ver seção própria ao final | texto de entrega, sem execução |

## T029 — o vermelho real, capturado antes de qualquer allowlist

Rodado com `console/tests/e2e/transversal-rules.spec.ts` completo, allowlist
(`EXCEPTIONS`) **vazia**, contra o cenário `now-violations` servido localmente
(`python -m tools.mockplane serve --scenario now-violations` + console
standalone apontado para ele). Comando:
`node_modules/.bin/playwright test --project=behaviour tests/e2e/transversal-rules.spec.ts --grep "markdown cru|identificador como nome|dois placeholders|controle de run vivo|afirmação negativa"`.

Resultado: **10 failed, 10 passed** (as dez rotas/regras não-violadas do grupo
"Now" continuaram passando de verdade — nenhuma allowlist ainda existia para
afrouxar nada).

As dez mensagens reais (nove previstas na spec + uma descoberta, marcada):

1. **`/runs/{id}` × markdown**: `/runs/{id} shows raw markdown: "d5e8f6a2b3c7d0e1f24\n### Incident Findings &"`
2. **`/runs` × markdown**: `/runs shows raw markdown: "N, SMALLEST FIRST··\n### Incident Findings &"`
3. **`/` × markdown** — **descoberta, não prevista pela spec original**: `/ shows raw markdown: "anager\n15 hours ago\n### Incident Findings &"`
4. **`/runs` × identifier-as-name**: `/runs shows an identifier standing in for a name: "e19e882a"` (a coluna INVESTIGATION truncada)
5. **`/runs/{id}` × identifier-as-name**: `/runs/{id} shows an identifier standing in for a name: "e19e882a1c9b4d5e8f6a2b3c7d0e1f24"`
6. **`/incidents/{id}` × identifier-as-name**: `/incidents/{id} shows an identifier standing in for a name: "alert%3Aalertmanager%3Ac046a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0%402026-08-22T23%3A43%3A23.303208%2B00%3A00"`
7. **`/runs` × two-placeholders**: `/runs: "Not recorded" appears 2 times in "Not recorded\nOpen RUNNING Alert run-0003 16 days ago Not recorded"`
8. **`/incidents/{id}` × two-placeholders**: `/incidents/{id}: "Not recorded" appears 2 times in "Not recorded · this deployment's own detectors · started · zone Unplaced · Not recorded"`
9. **`/runs/{id}` × live-control**: `/runs/{id}: the list showed status "SUCCEEDED" and the run's own page still offered "Stop this investigation\n(destructive)"`
10. **`/incidents/{id}` × negative-assertion**: `/incidents/{id}: "No investigation" is asserted on a page where the read behind it failed`

**Sobre a décima entrada (item 3).** Não estava na tabela de nove pares da
spec. Foi descoberta ao rodar a regra `markdown` varrendo as quatro rotas
estáticas do grupo "Now" — o dashboard (`/`) lê o mesmo `/v1/runs` sem filtro
e aplica `readFailure(summary)` ao construir seu feed de atividade recente
(`console/src/surfaces/screens/dashboard.tsx:213-227`), exatamente o mesmo
mecanismo sem renderizador de markdown que `/runs` e `/runs/{id}` já
carregavam entrada. **Decisão registrada aqui**: mantida como décima entrada
de allowlist em vez de forçada a desaparecer manipulando o cenário (adicionar
oito itens mais recentes que a violadora só para empurrá-la para fora da
janela do feed seria maquiagem do dataset contra a regra, o oposto do que
T029 pede). O número de partida da feature, portanto, é **dez**, não nove —
ver "Desvios declarados" abaixo.

## T030 — as dez entradas de allowlist

Escritas em `console/tests/e2e/transversal-rules.spec.ts:209-296`, uma por
par rota×regra, cada uma nomeando a rota, a regra, a razão em substância e o
que a remove — nunca por número de feature. Confirmado verde contra
`now-violations` após escritas (10 skipped via `test.fixme`, as outras 10
combinações continuaram genuinamente passando).

## T031 — determinismo dos detectores

`console/tests/unit/e2e/bans.test.ts`, 15 testes, todos contra texto **literal**
capturado no vermelho de T029 (não paráfrase). `pnpm exec vitest run
tests/unit/e2e/bans.test.ts` → 15 passed.

Neutralização confirmada um detector por vez (corpo trocado por `return null`
como primeira linha, rodado, revertido):

- `rawMarkdown` neutralizado → `AssertionError: expected null not to be null` no teste "accuses the exact report..."
- `identifierAsName` neutralizado → 3 falhas (hex truncado, hex completo, percent-encoded)
- `twoPlaceholders` neutralizado → `AssertionError: expected null not to be null` no teste do subtítulo de cinco slots
- `liveControlOnTerminalRun` neutralizado → `AssertionError: expected null not to be null` no teste do run settled com controle
- `negativeAssertionAfterFailedRead` neutralizado → `AssertionError: expected null not to be null` no teste do chip "No investigation"

Arquivo restaurado ao estado limpo depois de cada neutralização; diff contra
a versão limpa confirmado idêntico (`diff` sem saída) antes de prosseguir.

## T043 — verde contra o dataset determinístico

Reexecutado nesta sessão, servidor mock apontado para `populated` (o dataset
padrão da árvore), mesmo comando completo (`transversal-rules.spec.ts`
inteiro, sem `--grep`):

```
52 tests total
35 passed, 17 skipped, 0 failed
```

Os 17 pulados: 7 pré-existentes de `scroll-budget` (medidos em
`scroll-budget.spec.ts`, listados em `SCROLL_BUDGET_MEASURED_ELSEWHERE`) +
10 das entradas novas de `EXCEPTIONS`. **Nenhuma falha inesperada** — as
quarenta e duas combinações rota×regra sem entrada de allowlist passaram de
verdade contra o dataset determinístico, incluindo as cinco regras novas nas
rotas não nomeadas nas dez entradas.

**Número de entradas de allowlist ao fim: 10.** É o número que o próximo
slot da onda precisa fazer cair — nove delas nomeadas desde a preparação
desta spec, mais a do dashboard descoberta durante T029.

## Desvios declarados

**T032 — quarta constante.** O plano original de constantes previa três
nomes de variável (endereço, credencial, diretório de evidência). Uma quarta,
`NINJASRE_STAGING_USERNAME_ENV`, foi necessária porque a credencial de
staging é uma senha de conta, não um token — trocar uma senha por sessão
exige um nome de usuário, e não há outro tier onde esse nome de variável
poderia legitimamente viver. Declarada no mesmo arquivo, mesmo tier,
`config/constants/console.py:51`, exatamente o caminho que o guarda de
constantes já teria reprovado se ela estivesse em qualquer outro lugar —
`uv run python tools/check_constants.py` confirma limpo com a variável
presente.

**T035 — troca de senha por token, não repasse direto.** A tarefa, como
escrita, presumia que a credencial de staging já era algo que a variável
`NINJASRE_CONSOLE_E2E_CREDENTIAL` pudesse receber diretamente. Não é: é uma
senha de conta. `run_staging()` (`tools/console_e2e.py:664`) chama
`_staging_credential(url, username, password)`
(`tools/console_e2e.py:614`), que faz `POST {url}/api/session`
form-encoded com `username`, `password` e `returnTo=/runs` — a mesma
requisição que o formulário de login de uma pessoa faz — intercepta o
`Set-Cookie` do redirecionamento 303 sem segui-lo (`_NoRedirect`,
`tools/console_e2e.py:597`), extrai o token e só **esse** token é repassado
para `playwright()` pela variável já existente. A senha nunca chega à
variável de ambiente que o navegador lê; é gasta uma vez, na troca, e
descartada. Verificado contra o harness local (mock + console standalone,
credenciais de desenvolvimento `admin`/`ninjasre`) antes de qualquer uso
contra staging real — a troca produziu um cookie de sessão válido com
`Max-Age=43200` (batendo com `CONSOLE_SESSION_LIFETIME_SECONDS`).

**A décima entrada de allowlist** (dashboard × markdown) — ver seção T029
acima. Não é um desvio de execução; é uma descoberta que a spec não previu,
registrada em vez de escondida.

## Descoberta: a constituição já está rastreada em HEAD (afeta T007)

T007, como escrita, pede para conferir que a constituição "continua fora de
qualquer commit... o caminho da constituição não aparece em nada que esta
feature esteja preparando para commitar". Essa checagem, tomada
literalmente, passa: esta feature nunca deu `git add` nem `git stage` no
arquivo.

**Mas a pergunta certa é mais funda, e a resposta é não.** Medido nesta
sessão:

```
git ls-files --error-unmatch .specify/memory/constitution.md   → resolve (arquivo rastreado)
git cat-file -e HEAD:.specify/memory/constitution.md            → resolve (existe em HEAD)
git status --short .specify/memory/constitution.md              → " M .specify/memory/constitution.md"
```

O histórico do arquivo (`git log --oneline --follow`) conta a história
inteira:

1. `a2cee20` — "docs: establish the constitution, architecture, and decision
   records" — commit original, a constituição entra rastreada.
2. `6fb1525` — "chore: untrack the constitution, join the rest of spec-kit's
   local scaffolding" — remove as 312 linhas do índice do git deliberadamente,
   movendo o arquivo para o mesmo tratamento do resto de `.specify/`.
3. `19431fc` — "feat(platform): standardize delivery descriptor, reusable
   workflows, and staging K3s gitops" — um commit largo, de outro assunto,
   que **reintroduz as 312 linhas no índice**, sem que nada em sua mensagem
   mencione a constituição.

`.git/info/exclude` já tem, na linha da entrada `/.specify/`, um comentário
que antecipa exatamente esta situação: "constitution.md stays tracked
regardless: it was committed before this entry existed, and exclude patterns
never hide already-tracked files." A exclusão impede que um arquivo **novo**
sob `.specify/` seja rastreado; não desfaz o rastreamento de um arquivo que
já estava no índice antes da entrada existir — e é isso que `19431fc`
reintroduziu, silenciosamente, ao dar `git add` num escopo amplo demais.

**Não corrigido.** Por instrução explícita: `git rm --cached` muda o conjunto
de arquivos rastreados do repositório, e essa é uma decisão do operador, não
desta feature. O que esta feature faz é medir e registrar — aqui e na lista
de pendências abaixo — em vez de tratar a checagem de T007 como satisfeita
pela leitura mais rasa.

**Consequência prática para quem rodar `git status` depois desta feature**:
a constituição vai aparecer como `M` (modificada), não como arquivo novo
não-rastreado — porque já não era não-rastreada para começar. Isso não muda
a regra desta casa (a constituição nunca entra em commit desta feature, e
não entrou); muda o que uma pessoa vê quando confere.


## O que fica pendente, nomeado, não escondido

- **T044/T045 (staging real)**: **concluído** — ver seção "T044/T045 —
  resultado real contra staging" acima, com o log e as dez capturas em
  `specs_v7/000-regras-e-governanca/evidence/`.
- **T046 (verificação completa comparada)**: **concluído**, pelo orquestrador
  — 12223 passed / 27 skipped, exit 0, +13 sobre a linha de base. Ver seção
  "T046 — reconciliação dos +13" para os treze nomeados um a um.
- **T048 (remoção do deployment legado)**: texto de entrega ainda não
  escrito neste arquivo — ver seção própria ao final quando presente.
- **Passe editorial das onze linhas preexistentes do índice de ADRs**: as
  onze linhas que já existiam antes desta feature citam número de artigo
  (ex.: "IX, XII"); as cinco que esta feature escreveu nomeiam substância.
  A divergência é deliberada (ver "Decisões de design" da spec) e não foi
  normalizada — normalizar as onze é passe editorial próprio, fora do
  escopo desta feature, e um registro aceito é imutável.
- **`identifierAsName` (`COMPOSITE_ID`) — apertado nesta rodada, não mais
  pendente**: o padrão original, `/[a-z0-9_-]+:[a-z0-9_-]+:[a-z0-9_-]+/i`,
  também casava uma hora do tipo `23:41:02` (três grupos alfanuméricos
  separados por dois-pontos), presente incidentalmente dentro do texto
  markdown do cenário violador ("Standby promotion log at 23:41:02"). Não
  produziu falso positivo real (a única rota onde o texto aparece já tinha
  entrada de allowlist pela razão certa, e `populated` já terminava 100%
  verde), mas era uma dívida latente numa regra que roda em toda fronteira
  de feature da onda. **Apertado**: `console/tests/e2e/bans.ts` agora exige
  ao menos um caractere não-numérico por segmento
  (`(?:(?=[a-z0-9_-]*[a-z_-])[a-z0-9_-]+:){2}(?=[a-z0-9_-]*[a-z_-])[a-z0-9_-]+`).
  Confirmado por três provas: (1) `pnpm exec vitest run
  tests/unit/e2e/bans.test.ts` — 15 passed, incluindo os casos do hex e do
  id composto percent-encoded, que continuam acusando; (2) `node -e` direto
  contra o regex — `23:41:02` não casa mais, isolado ou embutido na
  sentença original, e o id composto continua casando por inteiro; (3) a
  regra `identificador como nome` rerodada contra o cenário `now-violations`
  com a allowlist esvaziada **temporariamente só para esta verificação** (o
  arquivo `transversal-rules.spec.ts` foi restaurado ao estado com as dez
  entradas logo depois, conferido por `diff` sem saída) reproduziu
  **exatamente as três falhas originais, com as mesmas mensagens**:
  `/runs shows an identifier standing in for a name: "e19e882a"`,
  `/runs/{id} shows an identifier standing in for a name:
  "e19e882a1c9b4d5e8f6a2b3c7d0e1f24"`,
  `/incidents/{id} shows an identifier standing in for a name:
  "alert%3Aalertmanager%3Ac046...%2B00%3A00"`. Suíte completa rerrodada
  contra `populated` depois da restauração: 35 passed, 17 skipped, 0
  failed — idêntico ao resultado anterior ao aperto.

  **Falso negativo achado e travado por teste permanente.** A verificação
  independente foi além e checou a pergunta simétrica — se o aperto abriu
  um buraco novo — e achou um: `123:456:789` (três segmentos inteiramente
  numéricos) também deixa de ser pego, pela mesma exigência de "ao menos um
  caractere não-numérico por segmento". Medido contra o domínio: o único id
  composto por dois-pontos que qualquer tela "Now" mostra hoje é
  `alert:alertmanager:<hash>`, cujos dois primeiros segmentos são palavras
  por construção — a troca é assimétrica a favor da regra, não um regresso.
  Mas a prova de ambos os lados (o `23:41:02` que passa a ser absolvido, e
  o `123:456:789` que também passa a ser absolvido) só existia como estado
  transitório — a allowlist esvaziada e depois restaurada — que já não está
  em disco. Um lookahead removido num commit futuro não teria nenhum teste
  parando por causa disso.

  **Travado agora**: `console/tests/unit/e2e/bans.test.ts`, teste
  `'absolves an all-digit colon-joined triple as a declared choice, not an
  accident'`, dentro de `describe('identifierAsName')`. Cobre as duas
  metades do comportamento numa asserção só: (1) absolve `'23:41:02'`
  isolado, absolve o mesmo embutido em `'Standby promotion log at
  23:41:02'`, e absolve `'123:456:789'` — as três, comentadas no próprio
  teste como escolha declarada (o gap conhecido, deixado passar de
  propósito porque nenhum id composto do domínio hoje é inteiramente
  numérico, com uma linha dizendo que é aqui que a decisão seria revisitada
  se isso mudar) e não como acidente; (2) continua exigindo que
  `'alert:alertmanager:c046a1b2'` seja acusado, para que o teste não passe
  com o detector de id composto neutralizado. `pnpm exec vitest run
  tests/unit/e2e/bans.test.ts` → **16 passed** (era 15).

  **Vermelho confirmado pela mesma técnica de neutralização da T031**: o
  lookahead foi removido de `COMPOSITE_ID` (revertido para
  `/[a-z0-9_-]+:[a-z0-9_-]+:[a-z0-9_-]+/i`, o padrão original, sem exigência
  de caractere não-numérico), rodado, e revertido depois — arquivo
  restaurado, `diff` sem saída confirma. Mensagem real da falha:

  ```
  AssertionError: expected '23:41:02' to be null

  - Expected:
  null

  + Received:
  "23:41:02"

   ❯ tests/unit/e2e/bans.test.ts:73:42
       expect(identifierAsName('23:41:02')).toBeNull();
  ```

  Restaurado o arquivo, suíte de volta a **16 passed**.

## T044/T045 — resultado real contra staging

Executado nesta sessão contra `https://stg-ninjasre.lan.kyo.ninja` (o
endereço real, lido de `NINJASRE_STAGING_URL` no `.env` da raiz — não o
padrão codificado, que também aponta para o mesmo endereço). Comando:

```
uv run python -m tools.spec_validation browser \
  --feature specs_v7/000-regras-e-governanca \
  --backing staging \
  --evidence-dir specs_v7/000-regras-e-governanca/evidence
```

com `NINJASRE_STAGING_URL`, `NINJASRE_STAGING_USERNAME`,
`NINJASRE_STAGING_CREDENTIAL` exportados de `.env` via `set -a; . ./.env; set
+a` numa sub-shell, nunca ecoados.

**Resultado**: `exit_status=0`. `20 tests`, `10 passed`, `10 skipped` (as dez
combinações rota×regra com entrada de allowlist — as mesmas dez de T029/T030,
puladas por `test.fixme` independentemente do backing). **Nenhum teste
falhou** — as dez regras que rodaram de verdade contra o deployment real
passaram: staging, hoje, não viola nenhuma das cinco regras novas fora das
dez combinações já sabidas e faladas.

- **Nenhum plano de dados foi iniciado**: `run_staging()` nunca chama
  `mock_plane()` nem `compose_stack()` — confirmado estruturalmente em T033
  e, agora, também pela ausência de qualquer processo `mockplane` na lista
  de processos deste host durante e depois do run.
- **Nenhum console foi servido localmente**: a linha "driving the browser
  suite against https://stg-ninjasre.lan.kyo.ninja" no log é o próprio
  endereço de staging — o navegador falou com o deployment real, não com
  `127.0.0.1`.
- **Nada foi construído**: o log não contém nenhuma linha de
  `console-build`/`next build`; `run_browser_validation()` pula
  `build_console()` inteiramente quando `backing == "staging"`
  (`tools/spec_validation.py:104-127`).
- **Diretório de evidência**: `specs_v7/000-regras-e-governanca/evidence/`
  contém dez capturas PNG de página inteira, uma por combinação rota×regra
  que rodou de verdade (nomeadas por `testInfo.titlePath`), do mesmo run —
  tamanhos entre 77KB e 1MB, condizentes com páginas reais renderizadas, não
  um placeholder. As dez combinações puladas não geraram captura (o guard em
  `test.afterEach` checa `testInfo.annotations` antes de fotografar — ver
  T040). **Produzidas pela flag `--evidence-dir` documentada em T037** — ver
  a subseção seguinte, que registra um defeito real nesse caminho, achado
  pela verificação independente do orquestrador, e o conserto.

### Defeito achado pela verificação independente, e o conserto

A primeira rodada de T044 (a que produziu a versão original deste arquivo)
tinha passado a credencial por `--evidence-dir`, mas a captura efetiva só
funcionou numa tentativa **anterior**, feita exportando
`NINJASRE_STAGING_EVIDENCE_DIR` diretamente no ambiente — e o texto daquela
versão não deixava essa diferença clara, o que por si só já era uma
imprecisão neste relatório. A verificação independente do orquestrador
mediu as duas portas separadamente, no mesmo comando, e achou o defeito
real por trás disso: `--evidence-dir` na linha de comando produzia **zero**
capturas, com `exit=0` e nenhuma mensagem — exatamente a forma de falha que
a T039 já nomeava para a marca de seleção, agora nas capturas.

**Causa**: `run_staging()` resolvia o diretório corretamente
(`tools/console_e2e.py`, variável `resolved_evidence_dir`), mas só o
repassava como `--output={dir}` — o diretório de artefatos do próprio
Playwright — nunca como a variável de ambiente
`NINJASRE_STAGING_EVIDENCE_DIR` que `console/tests/e2e/transversal-rules.spec.ts`'s
`afterEach` de fato lê (`process.env.NINJASRE_STAGING_EVIDENCE_DIR`). Quem
passava a variável direto no ambiente via export funcionava por
coincidência — `environment(toolchain)` faz `dict(os.environ)`, então uma
variável já exportada no processo chamador atravessa para o processo
filho sozinha. Quem usava a flag documentada não tinha essa coincidência a
seu favor. O `.last-run.json` que o próprio Playwright deposita em
`--output` fez o diretório parecer que tinha recebido alguma coisa mesmo
vazio de capturas — a causa de quase passar pela verificação.

**Vermelho capturado, antes do conserto** (`tests/unit/tools/test_console_e2e.py`):

- `test_playwright_puts_the_evidence_directory_in_the_subprocess_environment`:
  `TypeError: playwright() got an unexpected keyword argument 'evidence_dir'`
  — `playwright()` não tinha esse parâmetro.
- `test_run_staging_threads_the_resolved_evidence_directory_into_playwright`:
  `AssertionError: assert None == PosixPath('/tmp/evidence-example')` — o
  `playwright()` chamado por `run_staging()` nunca recebia o diretório por
  nenhum canal que o teste pudesse observar como o real.

**Conserto**: `playwright()` (`tools/console_e2e.py`) ganhou o parâmetro
`evidence_dir: Path | None`, que — quando presente — escreve
`env[NINJASRE_STAGING_EVIDENCE_DIR_ENV] = str(evidence_dir)` no ambiente do
subprocesso, usando a mesma constante que já nomeava a variável (nenhuma
segunda grafia introduzida). `run_staging()` passou a repassar
`evidence_dir=resolved_evidence_dir` para `playwright()` por esse parâmetro,
e a construção de `--output=` foi **removida inteiramente** — ela não
alimentava capturas, e o único efeito que tinha (depositar
`.last-run.json`) era o que disfarçava a falha.

**Reverificado pelas duas portas, contra o staging real, depois do
conserto**:

- `--evidence-dir <dir>` na linha de comando, variável de ambiente **não**
  exportada: `exit_status=0`, **10 PNGs**.
- `NINJASRE_STAGING_EVIDENCE_DIR=<dir>` no ambiente, sem a flag: `exit_status=0`,
  **10 PNGs**.

As dez capturas em `specs_v7/000-regras-e-governanca/evidence/` **nesta
versão do arquivo** vieram de uma rodada limpa, feita depois do conserto,
usando exclusivamente a flag `--evidence-dir` (a interface documentada em
T037) — sem a variável de ambiente setada no processo chamador. A senha
não apareceu em nenhum dos logs das três rodadas de reverificação
(checado com o método seguro — comparação embutida do shell, nunca
`grep -- "$SEGREDO"`, pela mesma razão registrada na nota metodológica
abaixo).

**T045 — busca pela credencial na saída completa**: a saída completa do
comando (`tools.spec_validation` inteiro, redirecionada para um arquivo de
log fora do repositório) foi buscada pela senha real lida de
`NINJASRE_STAGING_CREDENTIAL`, usando `grep -qF -- "$NINJASRE_STAGING_CREDENTIAL"`
contra o **arquivo de log**, nunca contra um processo — resultado:
**não encontrada**. A senha também nunca apareceu em nenhuma linha do log
(a única linha que nomeia algo do ambiente é "driving the browser suite
against https://stg-ninjasre.lan.kyo.ninja", que nomeia só o endereço).

**Uma nota metodológica, registrada porque quase virou um falso alarme**: a
primeira tentativa de também conferir a lista de processos do host
(`ps -eo args | grep -qF -- "$NINJASRE_STAGING_CREDENTIAL"`) reportou a senha
como presente. **Isso era um artefato do próprio método de checagem, não um
vazamento**: `grep -F -- "$VALOR"` faz o shell expandir `$VALOR` **antes** de
invocar `grep`, então o próprio processo `grep` nasce com a senha como seu
argumento de linha de comando — e é exatamente esse processo `grep`,
capturado no mesmo instante por `ps`, que o `grep` seguinte então encontra.
Refeita com um método que não gera processo nenhum com a senha em `argv`
(comparação de substring via `case` do próprio shell, embutida, contra um
snapshot de `ps -eo args` já capturado), a checagem deu `no` de verdade.
Confirmado também de forma direta: repetir a checagem falha (`grep -F --
"$VALOR"`) sozinha, sem staging rodando nada, também "encontra" a senha —
prova de que o efeito é do método de busca, não do processo sob teste. Fica
registrado como o jeito errado de procurar um segredo na lista de processos,
para quem for repetir esta validação: **nunca `grep -- "$SEGREDO"`; sempre
comparação embutida do shell contra um snapshot já capturado.**

## T046 — reconciliação dos +13

`make verify` final (rodado pelo orquestrador): **12223 passed / 27 skipped,
exit 0**. Linha de base de T001: **12210 passed / 27 skipped, exit 0**. Mesmo
número de skips, nenhuma regressão, diferença de **+13**, reconciliada aqui
um a um contra o diff real desta feature.

**Dez funções de teste novas, explícitas:**

`tests/unit/tools/test_console_e2e.py` (seis):
1. `test_the_staging_backing_refuses_without_a_credential_and_never_provisions_anything`
2. `test_the_staging_backing_refuses_without_a_username_and_never_provisions_anything`
3. `test_the_staging_backing_starts_no_data_plane_no_local_console_and_builds_nothing`
4. `test_the_staging_backing_always_selects_only_the_tests_marked_safe_for_it`
5. `test_playwright_puts_the_evidence_directory_in_the_subprocess_environment`
6. `test_run_staging_threads_the_resolved_evidence_directory_into_playwright`

`tests/unit/tools/test_spec_validation.py` (quatro):
7. `test_a_dry_run_against_staging_never_mentions_building`
8. `test_a_scenario_other_than_the_default_is_refused_against_staging`
9. `test_no_build_is_refused_against_staging_rather_than_ignored`
10. `test_staging_never_calls_build_console_even_though_build_defaults_true`

**Três casos parametrizados que o cenário `now-violations` gera sozinho**,
sem nenhuma função nova — o mesmo teste, uma combinação a mais, porque
`now-violations` entrou em `FIXTURE_SCENARIO_NAMES`
(`config/constants/fixtures.py`) e cada um destes já era parametrizado sobre
essa tupla (confirmado por `pytest --collect-only -q | grep now-violations`):

11. `tests/contract/fixtures/test_dataset_contract.py::test_every_fixture_validates_against_the_api_document[now-violations]`
12. `tests/contract/fixtures/test_dataset_coherence.py::test_every_reference_in_every_scenario_resolves[now-violations]`
13. `tests/contract/fixtures/test_dataset_coherence.py::test_every_scenario_reads_as_a_coherent_history[now-violations]`

Dez mais três: treze. Fecha exatamente com o `make verify` final. Nenhuma
contagem intermediária deste arquivo em qualquer versão anterior batia com
isso porque foi escrita antes do reparo do `--evidence-dir` (que acrescentou
os itens 5 e 6) — a reconciliação acima é contra o estado final do diff, não
contra um instantâneo no meio do trabalho.

## T048 — o deployment legado (texto de entrega, sem execução)

Esta feature não altera nada fora da árvore desta feature; a remoção abaixo
é um commit no repositório de GitOps, que o operador executa quando achar
apropriado.

**Repositório de GitOps**: `JustShinobi/k3s-gitops-prod` (declarado em
`.ci/application.yaml:44` desta árvore, campo `gitops.repository`).

**Caminho**: `clusters/prod/workloads/ninjasre-stg` (mesmo arquivo, campo
`gitops.stagingPath` — igual a `productionPath`, então é o único caminho que
existe para este ambiente hoje). O workload a remover, dentro desse caminho,
é o recurso Kustomize nomeado `console` — distinto do workload `web`, que é
o console real servido hoje (ver `.ci/application.yaml:14-21` — o componente
`console` builda `deploy/images/console.Dockerfile` para um workload também
chamado `console`, enquanto o componente `web`, linhas 25-34, builda
`deploy/images/web.Dockerfile` para o workload `web`; o próprio comentário
ao lado do componente `web` já registra a distinção: "The console a browser
loads. A separate component from `console`, which is the gateway it calls").

**Comando** (a executar no checkout do repositório de GitOps, não nesta
árvore):

```
git rm -r clusters/prod/workloads/ninjasre-stg/console  # ou o nome exato do
                                                           # diretório/arquivo
                                                           # Kustomize do
                                                           # workload console
git commit -m "chore: remove the legacy console workload from staging"
```

**Observação que fica registrada, não executada**: o componente `console`
também segue declarado em `.ci/application.yaml:14-21` **nesta árvore** —
ele é o que builda e publica a imagem que o workload legado do GitOps roda.
Removê-lo de lá sem remover esta declaração deixaria o pipeline de entrega
continuar construindo e publicando uma imagem para um workload que não
existe mais — as duas remoções pertencem à mesma decisão, uma em cada
repositório, e nenhuma das duas foi executada por esta feature.
