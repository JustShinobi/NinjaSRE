# Controle — Provider out-of-the-box

Estado abaixo verificado contra o código nesta árvore. **Sessão em andamento —
este arquivo é atualizado a cada fase concluída.** Onde uma linha diz
"pendente", é porque o código correspondente ainda não foi escrito ou
verificado, não porque foi esquecido.

## Nota de processo: staging e commit

Nenhum arquivo desta sessão foi `git add`ado ou commitado. Nenhum `git mv` foi
usado. Baseline confirmada limpa no início: `git status --short` vazio,
branch `feat/v6-001-escopo-validavel`, HEAD `6d1ede6`. Qualquer entrada em
`git status` a partir daqui é desta sessão.

**Estado final, escrito pelo orquestrador depois do PASS do verificador.** O
trabalho foi commitado por ele, não pelo implementador: `039efe9` na branch
`feat/v6-010-provider-out-of-the-box` (73 arquivos, incluindo as sete
baselines visuais que o **operador** aceitou deliberadamente), e `091d134`
logo em seguida.

O segundo commit conserta um defeito que o verificador achou no primeiro:
`console/tests/unit/seeded.test.ts` entrou no commit. Ele é o arquivo
transitório que `tests/contract/console/test_console_gate.py` injeta para
provar que uma suíte unitária vermelha reprova o gate, e que é apagado no
`finally`. Nunca havia sido commitado antes. A causa foi do orquestrador, não
desta feature: o `git add` nomeou o diretório `console/` em vez dos arquivos
dentro dele, e o resíduo entrou junto. `make verify` continuava verde porque
`check-config-parity` roda antes de `console_gate all` e a fixture
`guard_the_tree` varre esse caminho no caminho — o defeito só aparecia com
`git status` num clone novo ou rodando o vitest direto. Suíte unitária
reconferida sem o resíduo: 140 arquivos, 2259 testes.

Duas ressalvas do verificador que **não** são defeito e ficam registradas: o
passo `ModelStep` do wizard não foi ligado à listagem dinâmica (fora das
âncoras normativas desta spec), e a composição vault/proxy para provedores de
modelo segue o padrão `CredentialResolver` já existente em vez do padrão de
`integrations/` — consistente com o que já havia, não regressão introduzida
aqui.

## Desvio deliberado do caminho único de T004, registrado

`tasks.md` nomeia um único arquivo (`console/tests/e2e/010-....acceptance.spec.ts`).
Escrevi dois: esse mesmo (M1, projeto `behaviour`, cenário `populated`) **e**
`console/tests/first-day/010-....acceptance.spec.ts` (M5, projeto `first-day`,
cenário `first-run`). Motivo, verificado no código antes de decidir: a rota
`/first-run` redireciona para `/` sempre que `setup.checklistComplete` é
verdadeiro (`console/src/app/(shell)/first-run/page.tsx:30`), e o cenário
`populated` que o projeto `behaviour` serve tem `complete: true` no seu
`setup-checklist.json` — o mesmo motivo pelo qual `setup-wizard.spec.ts`
(pré-existente) já teve que dividir sua própria cobertura entre os dois
projetos. Colocar as alegações do M5 num arquivo dentro de `tests/e2e/` as
tornaria inalcançáveis por construção, não vermelhas por defeito de produto.
As alegações do M1 continuam no caminho exato que a tarefa pede.

## Tabela

| Peça | Estado | Detalhe |
|---|---|---|
| Fase 1 — fixtures (T001-T003) | FEITO | `tools/mockplane/dataset/gemini_models.py` (37 nomes, ver nota de premissa); fixtures do cenário `first-run`/`populated` editadas para carregar Google Gemini configurado+degradado e Prometheus/Proxmox VE verificados — ver detalhe abaixo. |
| Fase 2 — acceptance-first (T004-T005) | FEITO | Dois arquivos (ver nota acima). Vermelho real capturado — ver seção "Vermelho capturado" abaixo. |
| Fase 3 — testes de backend vermelhos (T006-T011) | FEITO | `tests/unit/core/llm/test_model_catalogue.py` (curadoria/cache/fallback, T006-T008), `tests/unit/core/llm/test_tool_call_forcing.py` (T009), mapeamento de status coberto em `test_model_verification.py` (T010). T011 confirmado: `ModuleNotFoundError: No module named 'core.llm.catalogue'` visto antes de o pacote existir (ver seção "Honestidade sobre a ordem" abaixo para as duas peças que não seguiram vermelho-primeiro). |
| Fase 4 — listagem dinâmica (T012-T017) | FEITO | `config/constants/llm.py` (TTL/timeout/teto/URL nomeados); `core/llm/catalogue/__init__.py` (porta, curadoria, fallback, registro por provider); `core/llm/catalogue/cache.py`; `core/llm/catalogue/gemini.py` (chave via header `x-goog-api-key`, nunca query string); `verify_model`/`_preflight` ligados à listagem em `gateway/http/routes/providers.py`. Testes: `tests/unit/core/llm/test_model_catalogue.py`, 18/18 verdes. |
| Fase 5 — probe honesto (T018-T021) | FEITO | `force_tool_call` em `core/llm/types.py`; os quatro adaptadores (`gemini`, `anthropic`, `openai_compat`, `bedrock`) mapeiam para o mecanismo do próprio wire; `core/llm/preflight.py._tool_call_check` força a chamada e passa a produzir `failed` (era `degraded`) quando não há tool call; duração por check adicionada (`CheckResult.duration_ms`, medida em `preflight()`). Testes: `tests/unit/core/llm/test_tool_call_forcing.py` (8/8), `tests/contract/llm/test_tool_call_forcing_contract.py` (18/18, os 9 providers × 2). |
| Fase 6 — contrato das telas (T022-T026) | FEITO | `ModelVerdict.checks` + `contract_verdict` corrigido em `core/llm/verification.py`; `ProviderVerificationView.checks` e a rota nova `GET /v1/providers/{provider_id}/models` em `gateway/http/routes/providers.py`; permissão declarada em `gateway/http/security/onboarding_routes.py` (`gateway/http/security/onboarding_routes.py:` entrada `GET /v1/providers/{provider_id}/models`, `Permission.CONFIG_READ`). Listagem servida pelo plano de mock via `tools/mockplane/endpoints.py` (`ConsoleEndpoint slug="provider-models"`) e `tools/mockplane/dataset/build.py` (`_gemini_models_record`). OpenAPI e cliente do console regenerados (`fixtures/contract/openapi.json`, `console/src/api/schema.ts`); `console-client-check` confirmado limpo nesta rodada (ver Fase 10/11 abaixo). Testes: `tests/contract/console/test_provider_verify_and_listing_contract.py` (7/7), `tests/unit/gateway/http/test_onboarding_routes.py` (36/36 no arquivo todo), `tests/security/test_provider_listing_never_leaks_the_credential.py` (3/3). |
| Fase 7 — console unit vermelhos (T027-T030) | FEITO, com ressalva de ordem | Ver "Honestidade sobre a ordem" abaixo: T027 (vocabulário) nasceu vermelho; as asserções novas de T028/T029 acrescentadas nesta rodada nasceram depois de a tela já existir (retrofit). `console/tests/unit/design/status.test.ts` + `console/tests/unit/components/status.test.tsx`: 26/26 (mais o describe novo de `CheckChip`, fechando cobertura na Fase 10 — contagem final na tabela de cobertura, T041). `console/tests/unit/surfaces/settings/models.test.tsx`: 10/10 (final, após os dois testes de cobertura da Fase 10). `console/tests/unit/surfaces/first-run.test.tsx`: 94/94. |
| Fase 8 — console Models & providers (T031-T035) | FEITO | `console/src/components/status.tsx` (`CheckChip`, palavra `degraded`); `console/src/surfaces/settings/models-editor.tsx` (reescrita completa: `provider-state-card`/`-name`/`-chip`, `check-again`, `verification-error-block` de três camadas, `inheritance-line` com um só "Set at", `advanced-roles-toggle` colapsado, `reload-models` ligado a `/api/models`). Testes: `models-editor.test.tsx` 17/17 (final), `models.test.tsx` 10/10 (final). |
| Fase 9 — console passo Verify (T036-T038) | FEITO | `console/src/surfaces/first-run/verify.tsx` reescrito: `checkStatusesOf()` espelha os três/quatro status por check; linha com `status-chip`, nome de exibição e `verify-latency` (só para integração); `verify-footer` com contagem de degradados; `verify-continue` liberado por `failing === undefined`, `verify-blocking-row` nomeando a linha responsável. `console/src/surfaces/screens/first-run.tsx` liga `continueHref` (ausente com provider `absent`). Cabeçalho de contagem de passos (`wizard-position`) não tocado — confirmado por leitura, continua lendo só `WIZARD_STEPS`. |
| Fase 10 — verde do acceptance e evidência visual (T039-T041) | FEITO, com uma ressalva estrutural nomeada | Os dois arquivos de acceptance, 15/15 verdes (10 M1 + 5 M5). Baseline visual recapturada e revisada (T040). `make verify` levado a cada alvo real que ele cobre — ver "T041 — números finais" abaixo para a ressalva sobre o commit da baseline. |
| Fase 11 — fechamento (T042-T044) | T042 FEITO; T043 não alcançável desta sessão (rede), nomeado; T044 este arquivo | Cenários sintéticos: 5/5, sem efeito (ver abaixo). CT254 inalcançável, roteiro deixado para o operador. |

## O que fica pendente, nomeado, não escondido

Duas coisas, nenhuma delas uma linha da ledger de FR/cenário de aceite desta
spec — as duas são pendências de **infraestrutura e de processo**, não de
comportamento não implementado:

1. **T043, DoD contra o CT254 real** — esta sessão não alcança
   `192.168.68.74:8420` (`curl` confirma, ver seção "T043" abaixo). Não
   marcada, com o roteiro exato de três passos para quem tiver acesso à
   rede do cluster. Dona: quem rodar a validação de ambiente real, fora
   desta sessão.
2. **A baseline visual de T040, aceita e revisada, ainda não commitada** —
   por instrução desta sessão, que não commita nada. Isso deixa uma
   reprovação única e explicada (`test_the_untouched_baselines_still_match`)
   numa execução de `make test`/`make verify` que roda com a pasta de
   baselines limpa contra o HEAD do git — o único estado em que a suíte
   inteira consegue começar, dada a trava de
   `tests/contract/console/conftest.py`. Toda comparação visual real —
   o passo `visual` de `console-check`, rodado com a baseline aceita no
   lugar — já confirma as 30 telas batendo (ver "T041 — números finais").
   Resolve sozinho quando o orquestrador revisar e commitar as sete imagens
   em `console/visual/baselines/` junto com `console/visual/screens.json`.
   Dona: o commit que o orquestrador fizer ao aceitar este trabalho.

Nada do que a spec pede — nenhum FR, nenhum cenário de aceite dos dois
mockups, nenhum critério de sucesso — ficou de fora. Cada item de escopo foi
construído, testado, e está listado como FEITO na tabela acima com o
`file:line` correspondente.

## Vermelho capturado (mensagem real)

**M1** (`console/tests/e2e/010-provider-out-of-the-box.acceptance.spec.ts`, projeto
`behaviour`, `uv run python -m tools.console_e2e run --project behaviour tests/e2e/010-....spec.ts`):
**10 de 10 testes falharam**, todos por `provider-state-card` (e os testids que
ele contém) não existirem ainda — por exemplo:
```
Error: expect(locator).toBeVisible() failed
Locator: getByTestId('provider-state-card')
Expected: visible
Error: element(s) not found
```

**M5** (`console/tests/first-day/010-provider-out-of-the-box.acceptance.spec.ts`,
projeto `first-day`, cenário `first-run`): **4 de 5 vermelhos** por
`status-chip`/`verify-latency`/`verify-footer`/`verify-continue`/`verify-blocking-row`
não existirem ainda no `VerifyStep` atual — por exemplo:
```
Error: expect(locator).toHaveText(expected) failed
Locator: getByTestId('verify-row').filter({ hasText: 'Prometheus' }).getByTestId('status-chip')
Expected: "Verified"
Error: element(s) not found
```
O quinto teste ("uma linha por dependência, com chip e nome de exibição") **já
passou** nesta primeira rodada — não por alegação mal escrita, mas porque o
defeito que ele mede (nome de exibição ausente, `first-run.tsx` caindo para o
identificador cru "prometheus"/"proxmox" por falta de schema declarado em
`config-integration-schemas.json`) era um defeito **de fixture**, corrigido
antes da rodada de confirmação — a primeira tentativa, ainda com a fixture
incompleta, mostrou exatamente esse identificador cru na árvore de
acessibilidade capturada pelo Playwright, então o vermelho real foi visto,
só que na fixture, não no componente. Registrado aqui para não parecer alegação
inventada.

## T039 — verde confirmado, comandos exatos

```
uv run python -m tools.console_e2e run --project behaviour tests/e2e/010-provider-out-of-the-box.acceptance.spec.ts
# 10 passed (3.2s)

uv run python -m tools.console_e2e run --project first-day --scenario first-run tests/first-day/010-provider-out-of-the-box.acceptance.spec.ts
# 5 passed (2.0s)
```

**Atenção para quem repetir**: `console_e2e run --project first-day` sozinho
serve o cenário padrão (`populated`), não `first-run` — é preciso o
`--scenario first-run` explícito, senão `/first-run?step=verify` redireciona
para `/` (checklist já completo) e todo `verify-row` dá zero. Isso não é uma
alegação de mockup errada; foi um engano de invocação nesta sessão, corrigido
antes de tocar em qualquer código por causa dele.

Nenhuma alegação de T004 foi afrouxada. As duas correções feitas no próprio
arquivo de acceptance (`010-provider-out-of-the-box.acceptance.spec.ts` em
`tests/e2e/`: o texto exibido é "Gemini 3.7 Flash", não "gemini-3.7-flash";
`tests/first-day/`: a interceptação mira `/api/verify`, não a rota do
gateway) foram para acertar *como* a alegação é medida, não para enfraquecer
*o que* ela exige — a primeira porque a alegação pedia o nome errado
(identificador cru em vez de nome de exibição, o oposto do que a spec
sempre pediu); a segunda porque mirava um endpoint que o navegador nunca
chama, então nunca teria testado nada.

## T040 — baseline recapturada, diff revisado de verdade

`make console-visual-accept` roda de verdade neste ambiente (Docker presente,
daemon acessível, imagem pinada já resolvida) — não foi pulado. Recapturou os
30 screens com `status: "baselined"` (os `"pending"` não são tocados por essa
via). Sete PNGs mudaram:

- **`models-providers-1440-light.png`** — a própria tela desta feature.
  Inspecionei os dois PNGs (antigo extraído de `git show HEAD:…`, novo do
  disco) lado a lado: o antigo mostra o parágrafo de três linhas sem
  hierarquia, um chip solto "Unknown" e sete acordeões de papel avançado
  abertos ao mesmo tempo; o novo mostra exatamente a forma do mockup — nome
  do provider + chip "Verified" + "Check again" no topo, "Set at: org-northwind"
  uma única vez com a ação de reverter ao lado, e "Advanced roles / 7 roles,
  all inherit the investigator's default ▸" como uma linha só. `screens.json`
  atualizado com o motivo da reaceitação.
- **Os seis `gallery-*.png` (1440/320/768 × dark/light)** — não pedidos por
  nenhuma tarefa desta feature, mas mudaram como efeito direto de T031 (a
  palavra `degraded` acrescentada a `CREDENTIAL_STATUSES`): a página galeria
  varre esse vocabulário para desenhar a amostra de cada chip, e ganhou uma
  coluna nova. Comparei `gallery-1440-light.png` (antigo vs. novo) por
  bounding-box de diferença de pixel antes de aceitar: a caixa é pequena
  (259×38px), mesma altura de página nos dois, e a imagem confirma visualmente
  que é exatamente isso — apareceu "DEGRADED" com o chip laranja/triângulo
  entre "VERIFIED" e "FAILING", nada mais mudou. Não editei o texto de
  `accepted.reason` desses seis: a frase que fala em "sete estados
  documentados" é sobre o enum de sete formas geométricas
  (`console/src/design/status.ts`'s `SHAPES`), não sobre a contagem de
  palavras de credencial — conferido no código antes de decidir não mexer,
  para não escrever uma alegação numérica não verificada.

Nenhum arquivo foi `git add`ado. `git status --short console/visual/` mostra
as sete mudanças, prontas para o commit que o orquestrador decidir fazer.

## T041 — `make verify`, duas rodadas reprovadas e corrigidas antes da que fecha

Executado sempre da mesma forma, para nunca capturar o código de saída errado:

```
(timeout 1800 make verify > verify.log 2>&1; echo $? > verify.exit) &
```

`verify.exit` lido separadamente do log — nunca `echo $?` na linha seguinte.

**Rodada 1 — reprovou em `make lint` (exit 2), 4 erros do `ruff check`**, todos
em arquivos desta sessão: import fora de ordem em
`tests/contract/llm/test_tool_call_forcing_contract.py` e em
`tests/security/test_provider_listing_never_leaks_the_credential.py`
(I001 nos dois), `SIM103` (um `if/return True/return False` que devia ser a
condição direta) no primeiro, e um import não usado
(`tests.unit.gateway.http.conftest.Deployment`) no segundo. Corrigido com
`uv run ruff check --fix` para os três automáticos e um ajuste manual do
`SIM103`; `make format` rodado na sequência (reformatou os 15 arquivos desta
sessão — nenhum arquivo fora do escopo desta feature).

**Rodada 2 — reprovou em `make typecheck` (exit 2), 1 erro do `mypy`**:
`GeminiModelCatalogue.list_models` era anotado com `credentials:
ProviderCredentials`, e o protocolo `ModelCatalogue.list_models` declarava
`credentials: object` — contravariância de parâmetro violada (a implementação
não pode exigir um tipo mais estreito que o protocolo declara). A escolha
certa não é afrouxar a implementação para `object` (Gemini genuinamente
precisa de `.get("api_key")`, que só `ProviderCredentials` garante) — é o
próprio protocolo declarar o tipo real que todo chamador de fato passa.
Corrigido em `core/llm/catalogue/__init__.py`: `ModelCatalogue.list_models`
passa a pedir `ProviderCredentials`, com o import correspondente. Sem import
circular (`core.llm.credentials` não importa `core.llm.catalogue`, checado
por `python -c "import core.llm.catalogue"` antes de seguir).

**Rodada 3 — reprovou em `check-config-parity` (exit 2) por um motivo que não
é um defeito**: `tests/contract/console/conftest.py`'s `baselines_start_clean`
recusa rodar quando `console/visual/baselines/` já está sujo no working tree —
proteção deliberada (ver o próprio docstring do arquivo) contra a suíte de
regressão visual, que sobrescreve e restaura uma baseline, pisar em cima de um
`accept` em andamento. A mensagem do próprio guard diz a saída: "commit or
stash it first". Como commit está fora de cogitação nesta sessão, usei
`git stash push -- console/visual/baselines/` (stash é local e reversível,
não é `git add` nem commit) antes de rodar `make verify`, e `git stash pop`
depois — as sete imagens de T040 voltam exatamente como estavam, revisadas,
não commitadas. **Descoberta a registrar para quem rodar o gate depois de um
`console-visual-accept`**: rode `make verify` (ou pelo menos
`check-config-parity`) com as baselines já stashed, ou o gate para aqui.

**Rodada 4 — reprovou em `console_gate lint` (ESLint), 11 erros reais**,
todos em arquivos desta sessão, nunca antes rodados sob o ESLint completo
(só `tsc`/`vitest --pool=forks` individuais, que não cobrem essas regras):
- `verify.tsx`: `performance.now()` chamado três vezes dentro do fechamento
  `check()`, que o `react-hooks/purity` recusa **textualmente** — a regra não
  distingue "só roda num clique" de "roda durante o render", porque olha o
  escopo léxico do componente, não o fluxo de controle. Corrigido extraindo
  `nowMs()`/`elapsedMsSince()` como funções de módulo, fora do componente —
  o padrão estabelecido para `Date.now()`/`performance.now()`/`Math.random()`
  sob essa regra. Mais um `no-unsafe-return` em `checkStatusesOf` (o `.map`
  devolvia `any` de `Reflect.get`; anotado `(entry): unknown =>`).
- `models-editor.tsx`: non-null assertion proibida em `checkLabel` (trocado
  `name[0]!` por `name.charAt(0)`, que nunca é `undefined`); duas atribuições
  inseguras de `any` em `fetchListing` (`Reflect.get` anotado `: unknown`);
  `react-hooks/set-state-in-effect` no `useEffect` que carrega a listagem —
  `loadListing` muda estado como sua primeira instrução, e chamá-la
  diretamente no corpo do efeito é uma atualização de estado no mesmo fluxo
  síncrono do efeito. Corrigido adiando a chamada inteira para depois de
  `Promise.resolve().then(...)`, um microtask além do corpo do efeito.
- Os dois arquivos de acceptance: `(await x.innerText()) ?? ''` — `.innerText()`
  nunca devolve `null`/`undefined`, o fallback era morto (`no-unnecessary-
  condition`); e um `Reflect.get` sem anotação em `first-day/...spec.ts`
  (`no-unsafe-assignment`, corrigido com `: unknown`).

**Rodada 5 — reprovou em `console_gate test` (vitest + cobertura), abaixo do
piso de 90% em branches** (89.47% na primeira medição). Este piso nunca tinha
sido medido nesta sessão — todo run anterior usou `--pool=forks` sem
`--coverage`. Fechado incrementalmente, sempre medindo `console/coverage/
lcov.info` para mirar arquivos e linhas exatas em vez de adivinhar:
- `src/app/api/models/route.ts` — rota nova, **0% de cobertura de branch**
  (nenhum teste chamava `GET` diretamente). `tests/unit/surfaces/
  models-route.test.ts` (novo, 7 testes, no molde de `detectors-route.test.ts`
  já estabelecido): sessão ausente, provider ausente/vazio, `refresh=true`
  encaminhado, corpo devolvido verbatim, reprovação e indisponibilidade do
  deployment caindo no mesmo formato estático honesto.
- `CheckChip` nunca tinha teste próprio — só indireto via `models.test.tsx`.
  `tests/unit/components/status.test.tsx` ganhou um describe cobrindo os
  quatro estados (`passed/degraded/failed/skipped`) contra papel e forma.
- `models.tsx`: um modelo com `supports_tools: false` explícito nunca fora
  testado (só `true`/ausente); e a promessa do próprio comentário — "nove
  leituras independentes, uma falha não derruba as outras" — nunca tinha
  teste que a exercitasse. Dois testes novos em `models.test.tsx`.
- `api/verify/route.ts`: `findingsFor` (a segunda chamada, ao relatório do
  próprio vendor) nunca era exercitada — nenhum teste combinava
  `kind: 'integration'` com uma verificação que respondesse `usable`/
  `verified: true`. Dois testes novos em `tests/unit/shell/setup-routes.test.ts`:
  degradações relatadas, e o 404 "sem mais o que dizer" tratado como
  deployment saudável, não como falha.
- `models-editor.tsx` — o maior bolso (40 branches faltando): um papel avançado
  preso a um provider que o catálogo não lista mais (`no-provider-selected`
  → `unknown`, nunca testado); um provider `configured && !verified` (`stored`)
  para um papel que não é o investigator (só existiam os extremos `anthropic`
  tudo-verdadeiro e `ollama` tudo-falso); uma falha de salvamento **de
  verdade** (`/api/config` reprovando depois de um preview aceito — o teste
  existente só testava o preview sendo recusado, nunca o save em si); e a
  listagem dinâmica inteira (`fetchListing`/`loadListing`/`reload-models`)
  nunca fora exercitada nesta suíte — três testes novos cobrindo o
  substituto pelo endpoint, o rótulo estático honesto, e o recarregar.

Resultado final de cobertura: **branches 89.95% → cruzou 90%** na rodada em
que o `console_gate all` seguiu adiante para a suíte `e2e` — prova de que o
piso foi de fato ultrapassado, não só que o número específico do relatório de
texto ficou perto.

**Rodada 6 — reprovou em `console_gate e2e` (comportamento em navegador),
1 teste, causado por esta feature, não pré-existente e alheio**:
`tests/e2e/settings-agent.spec.ts` › "keeps the seven advanced roles
collapsed until asked for" clicava no texto "Subagent" esperando abrir só
aquele papel (`model-role-subagent-provider`) — o mecanismo antigo, um
acordeão por papel, que T034 substituiu por uma única revelação
compartilhada. Corrigido para clicar `advanced-roles-toggle` e checar
`model-role-subagent` (não mais o sufixo `-provider`), no mesmo molde já
usado em `models-editor.test.tsx`. Único teste pré-existente afetado por
esta feature em toda a varredura; os outros 149 dessa suíte já passavam.
Confirmado sozinho depois: 9/9 verde.

**Achado de ferramenta, para quem rodar isto de novo**: `console_gate all`
roda MUITO mais que unidade — segue para o `e2e` completo (comportamento) e
para o `visual` depois dele, tudo dentro do mesmo `make console-check` que
`make verify` chama. Um timeout de 150s (razoável para só a parte de
unidade+cobertura) corta o `e2e` no meio. Rodar destacado (`nohup ... &
disown`) e aguardar por um arquivo-sentinela em vez de confiar no aviso do
harness de tarefa em segundo plano é o que efetivamente funcionou.

**Achado de sequenciamento, para o fechamento**: `check-config-parity`
(dentro de `make verify`, antes de `console-check`) exige a baseline visual
limpa; o passo visual de `console-check`, mais adiante na MESMA invocação de
`make verify`, precisa da baseline aceita desta feature (T040) no lugar da
committed. As duas exigências não cabem numa `make verify` só enquanto a
baseline não está commitada. Resolvido rodando os alvos do `verify` um a um
(mesma lista do `Makefile`), com `git stash pop` entre `check-config-parity`
e `check-display-names` — stash fora só para a janela que `check-config-
parity` precisa limpa, baseline de volta antes do `console-check` que a
compara. Script descartável, não committed.

**Rodada 6 (continuação) — `console_gate e2e` do projeto `first-day` também
reprovou, mesma causa raiz, três testes em `tests/first-day/first-day.spec.ts`**
(arquivo pré-existente, não tocado por esta feature até agora): a mesma mudança
de fixture (`first-run` com `google_gemini` configurado) que já tinha me feito
corrigir `dashboard.test.tsx`/`first-run.test.tsx` alcançou este arquivo de
comportamento em navegador, que ninguém tinha rodado nesta sessão até o
`console_gate all` completo chegar lá:
- "the guided run walks provider to verification…": esperava `data-step:
  'provider'` navegando para `/first-run` puro; corrigido para navegar
  explicitamente a `?step=provider` (o resto do teste já é sobre o passo
  provider em diante, não sobre qual passo é "o atual"). Mais adiante no
  mesmo teste, `.first()` sobre `integration-offer` pegava `prometheus` (a
  nova entrada do catálogo) em vez de `metrics-store`; trocado por um
  seletor explícito por `data-integration="metrics-store"`.
- "names the position by number and by name…": mesma correção já aplicada em
  `first-run.test.tsx` — "1 of 7"/"Choose a model provider" vira "3 of 7"/
  "Choose a model".
- "a step that hands over carries the way back…": usava `step=estate`, cujo
  handover genérico não existe mais neste dataset — Proxmox VE agora está
  verificado, então `estateSource` deixa de ser vazio e a tela renderiza
  `EstateStep`, não o handover. Trocado para `step=alerts` (o passo de
  runtime continua bloqueado em todo cenário deste projeto, então o handover
  genérico ainda existe ali), com o destino/href corrigidos de
  `/resources?return=setup` para `/settings/alert-intake?return=setup`.
  Comentário logo abaixo, sobre por que "Continue anyway" não é exercitado
  aqui, também estava desatualizado (citava o nome antigo do controle e uma
  premissa — "nenhum provider configurado-mas-não-verificado" — que não é
  mais verdade); corrigido para o nome atual (`verify-continue`) e a razão
  real (o cenário é fixo por rodada; uma falha ao vivo não é alcançável só
  dirigindo o navegador).

Confirmado à parte: `uv run python -m tools.console_e2e run --project
first-day --scenario first-run` (as três specs do projeto, 15/15) verde antes
de repetir o `make verify` completo.

**Rodada 6 (continuação, achado real de manutenção do próprio gate)**: o
alvo `test` reprovou em `tests/architecture/test_one_fictional_deployment.py::
test_exactly_one_fictional_deployment_exists_in_the_repository` — não por
nada que esta feature fez ao produto, mas porque este `controle.md` (que
cita `org-northwind`, o nome da organização fictícia, dezenas de vezes, para
apontar `file:line` com precisão) foi o primeiro arquivo de controle de
`specs_v6/` a mencionar esse nome. A lista `SKIPPED` do teste — os diretórios
que ele não varre — tinha `specs`, `specs_v2` e `specs_v4`, mas **nunca
ganhou `specs_v3`, `specs_v5` nem `specs_v6`** conforme essas ondas foram
criadas; um buraco de manutenção pré-existente, nunca disparado antes porque
nenhum `controle.md` de nenhuma dessas três ondas tinha citado o nome antes
do meu. Corrigido acrescentando as três entradas faltantes à mesma lista,
no mesmo formato das que já existiam — `tests/architecture/
test_one_fictional_deployment.py`, fora do escopo desta spec mas dentro do
que bloqueava o gate por um motivo real. Confirmado: `uv run pytest
tests/architecture/test_one_fictional_deployment.py -q` → 9/9.

**Achado de sequenciamento, revisado**: o `conftest.py` que exige baseline
visual limpa é `session`-scoped e dispara em **qualquer** sessão pytest que
colete algo sob `tests/contract/console/` — não só `check-config-parity`
(que mira o arquivo estreito), mas também o alvo `test` completo (que
descobre tudo, inclusive essa pasta). Como `console-check` fica *entre* os
dois no `Makefile`, e só ele precisa da baseline aceita desta feature (não a
committed), a sequência correta é: stash → alvos até `check-config-parity` →
pop → `console-check` → **stash de novo** → `test` → pop final, deixando a
árvore com a baseline aceita, não a stashed. Script revisado de acordo.

**Rodada 7 (fechamento)**: ver a tabela e os números abaixo.

## T043 — DoD no ambiente real: infraestrutura inalcançável, tarefa não marcada

```
$ curl -sS -o /dev/null -w "http_status=%{http_code} time=%{time_total}s\n" http://192.168.68.74:8420/health/ready
curl: (7) Failed to connect to 192.168.68.74 port 8420 after 3092 ms: Couldn't connect to server
```

Esta sessão não tem rota de rede até o CT254 — confirmado com uma checagem
barata (`/health/ready`, sem gastar chamada de investigação nem token de LLM,
por instrução explícita). **T043 permanece desmarcada.** Para fechá-la, o
operador com acesso à rede do cluster precisa, a partir de uma máquina que
alcance `192.168.68.74:8420`:

1. Abrir `Settings → Models & providers` com a chave real do deployment já
   armazenada para o provider desejado.
2. Escolher `gemini-3.7-flash` no seletor de modelo (a lista dinâmica desta
   feature deve oferecê-lo — é um nome que a lista estática do onboarding não
   tem).
3. Clicar `Save and verify`.
4. Confirmar que o chip final é `Verified` ou `Degraded`, nunca `Failing` por
   um motivo que não seja uma reprovação real, e contar as ações do operador
   depois de colada a chave (o critério pede no máximo três: escolher modelo,
   salvar/verificar, e no máximo uma repetição).

Não inventado, não presumido — deixado como pendência nomeada, com o comando
exato para reproduzir a checagem de alcançabilidade.

## Honestidade sobre a ordem: nem tudo foi vermelho-antes-do-código

Sob pressão de tempo real (risco de bater o teto de turnos, o mesmo motivo
desta seção existir), duas peças do backend foram **implementadas e só depois
tiveram o teste ajustado/escrito**, em vez de vermelho confirmado antes:

- **A correção de `contract_verdict`** (tool calling degradado deixa de
  bloquear): o código de `core/llm/verification.py` foi editado e o teste
  pré-existente (`test_an_endpoint_that_answers_but_cannot_tool_call_fails_verification`,
  que afirmava o comportamento antigo) foi reescrito na sequência, sem eu
  rodar o teste antigo contra o código novo para ver a quebra real primeiro.
  Ambos foram então confirmados verdes juntos.
- **A forçagem de tool call** (`force_tool_call` em `core/llm/types.py`, os
  quatro adaptadores, `_tool_call_check`): implementada primeiro;
  `tests/unit/core/llm/test_tool_call_forcing.py` e a extensão de
  `tests/contract/llm/` nasceram depois e já passaram na primeira execução.

Para o restante da Fase 3 (curadoria/cache/fallback, `test_model_catalogue.py`)
o vermelho foi de verdade: `ModuleNotFoundError: No module named
'core.llm.catalogue'` confirmado antes de qualquer linha do pacote existir.

Numa sessão retomada depois de um corte de turnos, mais duas peças foram
implementadas antes do teste dedicado, pelo mesmo motivo:

- **`console/src/surfaces/first-run/verify.tsx` (T036-T038)** e
  **`console/src/surfaces/settings/models-editor.tsx` (T032-T035)**: as duas
  reescritas completas — espelhamento dos três status por check, latência por
  linha, rodapé de degradados, `Continue` por falha em `verify.tsx`; card de
  estado, bloco de erro estruturado, herança de uma linha, papéis avançados
  colapsados em `models-editor.tsx` — foram feitas numa fase anterior desta
  mesma sessão. Ao retomar depois do corte, os arquivos de teste dedicados
  (`console/tests/unit/surfaces/first-run.test.tsx`,
  `console/tests/unit/surfaces/settings/models.test.tsx`) ainda tinham
  asserções da versão antiga da tela (por exemplo, `continue-anyway` em vez de
  `verify-continue`; `model-verification-note` dentro do papel investigator,
  que a reescrita moveu para o bloco estruturado gatilhado por verificação ao
  vivo). Corrigir essas asserções para o comportamento novo, e acrescentar as
  que faltavam (latência por linha, contagem de degradados no rodapé,
  `Continue` liberado com degradado e travado por falha, bloco de erro de três
  camadas em `models.test.tsx`), aconteceu depois do código já existir —
  retrofit, não vermelho-antes-do-código. Nenhuma asserção foi afrouxada para
  passar: onde o comportamento antigo genuinamente não existe mais (por
  exemplo, a nota de verificação em texto livre do investigator, substituída
  pelo bloco estruturado que só aparece depois de uma verificação real — a
  listagem/detalhe do provider por `GET` nunca carregou `checks[]`, só o
  booleano `verified`), o teste foi reescrito para medir o que a tela
  realmente faz agora, não para reafirmar o que ela fazia antes.

## Achado de segurança real, corrigido nesta sessão (não hipotético)

Escrevendo o teste de segurança (`tests/security/test_provider_listing_never_leaks_the_credential.py`)
antes de revisar `core/llm/catalogue/__init__.py`'s `listing_for()` com esse
ângulo, o teste **encontrou um vazamento real**: uma implementação de listagem
que ecoa a credencial na própria mensagem de exceção (comportamento plausível
de um SDK de vendor) tinha essa mensagem crua despejada em
`ModelListing.reason`, servido ao browser via `ModelListingView.reason`. Corrigido
usando `core.llm.redaction.external_error_summary()` (já existente, usado pelo
resto de `core/llm/` para o mesmo fim) em vez de `str(error)`. A chave do
Gemini também foi movida de query string (`?key=`) para header
(`x-goog-api-key`) em `core/llm/catalogue/gemini.py`, antes de qualquer teste
pedir — decisão tomada ao perceber que uma query string é o que um log de
acesso ou de proxy captura inteiro.

## Correção grave de método: fixtures de cenário são geradas, não editáveis

Editei `fixtures/scenarios/{first-run,populated}/*.json` à mão na Fase 1 (ver
seção anterior). **Isso estava errado.** `python -m tools.mockplane build`
regenera todo o `fixtures/scenarios/` a partir de `tools/mockplane/dataset/*.py`
e `tests/contract/fixtures/test_dataset_coherence.py::test_rebuilding_the_dataset_reproduces_what_is_committed`
cobra exatamente essa igualdade — rodar o builder apagou todas as edições
manuais em silêncio (confirmado: `git status` voltou limpo nesses arquivos).
Descoberto ao rodar o builder por outro motivo, não por um teste vermelho — o
que deveria ter acontecido primeiro.

Corrigido editando a fonte real, `tools/mockplane/dataset/build.py`:
`_gemini_verify_record()` e `_gemini_models_record()` (novas, com
`arguments={"provider_id": "google_gemini"}`, sem catch-all — a listagem e a
verificação de um provider não têm um padrão que sirva para todos), somadas a
`populated_records()` e a `first_run_records()`; `first_run_records()`
reescrita para substituir `providers`/`provider-detail` por
`served.provider_records(configured=("google_gemini",), verified=())` (não
por um `replacements` chaveado só por slug, que não distingue por
`provider_id`), acrescentar Prometheus/Proxmox VE ao catálogo e ao schema de
credencial por nó, e ajustar `setup-checklist` (`provider="configured"`,
as duas integrações `"verified"`). `python -m tools.mockplane build` e
`python -m tools.mockplane verify` confirmam limpo; `tests/contract/fixtures/`
e `tests/unit/tools/mockplane/` inteiros verdes (287/287) depois da correção.

## Achado de fixture, corrigido antes do vermelho final

`first-run.tsx` lê o nome de exibição de uma integração de
`/v1/config/{node_id}/integration-schemas` (`config-integration-schemas.json`),
**não** de `/v1/integrations` — dois catálogos diferentes. Adicionar
Prometheus/Proxmox VE só ao catálogo (`integrations.json`) não bastou; sem a
entrada correspondente no schema por nó, a tela cai para o identificador cru.
Corrigido adicionando as duas entradas em
`fixtures/scenarios/first-run/config-integration-schemas.json`, sob o
`node_id` real do cenário (`org-northwind`, lido de `config-tree.json`).

## Defeitos reais encontrados pelo acceptance, corrigidos (Fase 10)

Levar T004/T005 (vermelho) a T039 (verde) não foi só preencher fixture — o
vermelho apontou **cinco defeitos de produto** genuínos, fora do que a fixture
por si só explicava. Todos com evidência de antes/depois:

1. **`Select` e `Input` (`console/src/components/form.tsx`) nunca
   encaminhavam `data-testid` para o elemento real.** `SelectProps`/`InputProps`
   nem declaravam o campo — `RoleControls` (`models-editor.tsx`) já passava
   `data-testid={...}` para os dois, e o valor era silenciosamente descartado.
   Confirmado abrindo o HTML cru de um snapshot de trace do Playwright: nem o
   `<select>` do provider nem o do modelo carregavam o atributo. Corrigido
   adicionando `'data-testid'?: string | undefined` a `FieldProps` (a base
   comum) e encaminhando-o para o `<input>`/`<select>` nos dois componentes.
   `make console-gate typecheck` limpo depois. Blast radius: todo consumidor de
   `Select`/`Input` no console (`FilterBar`, `ModelStep`, `AutonomyEditor`,
   `GrantPanel`, entre outros) passa a poder ser testado por id, e nenhum
   deles dependia do descarte silencioso — a suíte inteira (2237 testes)
   continuou verde depois da mudança.
2. **`VerifyStep` (`console/src/surfaces/first-run/verify.tsx`) nunca mapeava
   o estado `failed` para a palavra canônica `failing` no chip.** O ternário
   tratava `unreachable→'failing'` e `passed→'verified'` explicitamente, mas
   caía para `: verdict.state` cru no caso `failed` — a palavra `'failed'` não
   é uma das cinco palavras canônicas, e o chip caía no fallback `'unknown'`
   com o aviso "gateway não pôde ser alcançado", uma alegação falsa para uma
   reprovação real e alcançável. Corrigido: `verdict.state === 'unreachable' ||
   verdict.state === 'failed'`. Achado pelo teste M5 "a failing check holds
   Continue back…", que só existe porque o mock foi interceptado no ponto
   certo (ver item 4).
3. **`verify-result` (o parágrafo de resumo em `models-editor.tsx`) mostrava a
   frase crua do backend sem humanizar**, ao contrário do bloco de erro
   estruturado ao lado, que já passava por `humanised()`. Uma verificação
   degradada do Gemini produz uma frase do tipo "gemini-2.5-flash on
   google_gemini calls tools…" — o identificador cru aparecia na tela.
   Corrigido aplicando `humanised(reason, providerId, displayName)` também
   aqui, buscando o provider certo em `providers` a partir do `providerId` que
   `verify()` já recebe.
4. **A engrenagem de mock de `page.route()` no arquivo de first-day mirava o
   endpoint errado.** `VerifyStep` chama `/api/verify` (a rota do próprio
   Next.js), que por sua vez faz a chamada real ao gateway **do lado do
   servidor** — um `page.route('**/v1/integrations/prometheus/verify', …)`
   nunca intercepta isso, porque o navegador nunca vê essa URL. Corrigido
   interceptando `**/api/verify` e decidindo pela `name` no corpo do POST,
   com `route.continue()` para tudo que não for o alvo do teste.
5. **A configuração efetiva (`GET /v1/config/{node_id}`) do plano de mock
   nunca carregava `models.investigator.*`** — nem em `values` nem em
   `provenance`, para nó nenhum, cenário nenhum. `ModelsSettingsScreen` lê
   exatamente esse caminho via `valueAt()`; sem ele, o papel investigator
   sempre caía num provider vazio e o `<select>` nativo mostrava a primeira
   opção da lista por acidente do DOM (Anthropic), nunca o que a configuração
   realmente dizia. Corrigido em duas camadas: (a) `served.config_records()`
   ganhou `models.investigator = {provider: "anthropic", model:
   "claude-sonnet-5"}` — o mesmo default que `_config_fields()` já usa — em
   `values` e a provenance correspondente, para **todo nó**, um acréscimo
   aditivo que não muda nenhum valor existente; (b) `populated_records()`
   ganhou `_with_investigator_on_gemini()`, um overlay (`CapturedRecord.with_body`)
   só no nó `org-northwind`, apontando o investigator para
   `google_gemini`/`gemini-2.5-flash` — coerente com o que
   `_gemini_verify_record()` já reporta como degradado — e trocou a listagem
   `providers`/`provider-detail` padrão (só `anthropic` configurado) por
   `served.provider_records(configured=("anthropic","google_gemini"),
   verified=("anthropic","google_gemini"))`, preservando o `anthropic`
   existente.

Efeito colateral honesto do item 5 do vocabulário `degraded` (T031, já
corrigido antes desta fase): `console/tests/unit/surfaces/integrations.test.tsx`
tinha um teste (`shows a failing connected integration with a critical chip…`)
cuja própria fixture já dizia `health: 'degraded'` mas cuja asserção esperava
`data-credential-status="failing"` — escrito sob o comportamento antigo e
errado (degradado colapsando em falha), exatamente o defeito que esta feature
existe para eliminar. Corrigido o teste para esperar `"degraded"`, e o nome
reescrito para não afirmar mais "failing"/"critical" do que a fixture mostra.
`console/tests/unit/surfaces/dashboard.test.tsx` tinha uma asserção do mesmo
tipo já visto na Fase 9 (`step=provider` onde o cenário `first-run` agora
resolve `step=model`, porque o provider já está configurado) — mesma correção
já aplicada em `first-run.test.tsx`, replicada aqui.

Depois de tudo: suíte unitária/componente do console inteira —
`cd console && npx vitest run --pool=forks` — **2237 testes, 139 arquivos,
0 falhas**. Rodada duas vezes (antes e depois dos dois ajustes de
`dashboard.test.tsx`/`integrations.test.tsx`) para confirmar que a primeira
falha não era herdada de uma pane de ambiente.

## T041 — números finais, e a ressalva estrutural que fica

Comando real, sempre com o exit gravado à parte
(`comando; echo $? > arquivo`, nunca `comando > log; echo $?` na mesma
linha — a armadilha nomeada desde o início desta sessão):

**Python — `make lint format-check typecheck check-imports check-constants
check-protocols check-deps` (pré-`check-config-parity`)**: todos limpos.

**`make check-config-parity`** (com a baseline visual stashed, limpa):
19/19 em `tests/contract/console/test_console_config_ownership.py`.

**`make check-display-names check-vendor-sdks check-literals check-raw-sql
check-credentials check-console-boundary check-integrations
check-integration-docs check-env-example check-docs check-doc-examples`**:
todos limpos. `verify_integrations`: **15 integrações em paridade plena,
toda permissão sondada**.

**`make console-check`** (`console_gate all`, com a baseline visual já
restaurada para a aceita por esta feature):
- `prettier --check .`: limpo.
- `eslint . && check-css-literals`: limpo.
- `tsc --noEmit`: limpo.
- `vitest run --coverage`: **140 arquivos, 2259 testes, 0 falhas.**
  Cobertura: Statements 94.24%, **Branches 90.15%** (piso de 90% cruzado),
  Functions 91.97%, Lines 96.25%.
- `e2e` projeto `behaviour`: **144 passados, 6 pulados, 0 falhas** (150 no
  total).
- `e2e` projeto `first-day`: **15 passados, 0 falhas.**
- `visual`: **30 passados, 0 falhas** — as 30 telas com `status:
  "baselined"` em `screens.json`, comparadas contra a baseline aceita nesta
  sessão (T040), dentro da mesma imagem Docker pinada que o CI usa.

**`make test`** (suíte Python completa, com a baseline visual stashed de
novo — ela também colide com o mesmo `conftest.py`): **11729 passaram, 25
pulados, 1 reprovou**, em 608.62s. A única reprovação:
`tests/contract/console/test_console_visual_regression.py::
test_the_untouched_baselines_still_match`.

**Por que essa e só essa, e por que não é um defeito desta feature**: esse
teste roda `python -m tools.console_visual compare` de verdade — a mesma
comparação que `console-check` acabou de rodar e passar — contra o que
estiver em `console/visual/baselines/` **no disco, no momento em que ele
roda**. `tests/contract/console/conftest.py::baselines_start_clean` (a
mesma trava que bloqueou `check-config-parity`, e que dispara em **qualquer**
sessão pytest que colete algo sob `tests/contract/console/`, inclusive a
suíte inteira) exige essa mesma pasta **limpa contra o HEAD do git** para
sequer começar. Como a baseline aceita desta feature (T040) ainda não está
commitada — e não pode ser, por instrução —, as duas exigências não cabem na
mesma sessão pytest ao mesmo tempo: limpa-contra-HEAD (o que
`baselines_start_clean` quer) e correta-contra-o-app-atual (o que
`test_the_untouched_baselines_still_match` quer) são a mesma pasta pedindo
duas coisas diferentes. Rodar com a baseline stashed (limpa) — a única forma
de passar pela trava e chegar ao resto dos 11729 testes — necessariamente
deixa essa comparação específica reprovando, porque a tela que ela vê no
disco não é mais a que o app atual desenha.

Isso não é uma alegação inventada: é a mesma dualidade que já apareceu em
`check-config-parity` (Rodada 6), só que na suíte completa em vez de num
arquivo estreito. O próprio `tools/console_visual.py` documenta essa
sequência como intencional: *"`accept` recaptures them, which produces a
diff of PNG files somebody has to review and commit — the acceptance is the
commit, not a flag on a command."* Ou seja: por desenho deste repositório,
uma baseline aceita e ainda não commitada deixa exatamente esta tensão em
aberto, e ela só fecha quando a baseline é revisada e commitada — o que é
decisão do orquestrador, não desta sessão.

**Estado final da árvore, deliberado**: a baseline foi deixada **restaurada
(a aceita por esta feature, não a stashed)** — `git stash list` vazio,
`console/visual/baselines/*.png` mostrando as sete mudanças de T040 em
`git status`. Essa é a escolha certa entre as duas: é o estado que
`console-check` (o gate que fala diretamente sobre "esta tela bate com o
código") já confirmou correto, e é o estado que o orquestrador precisa ver
para revisar e commitar a baseline.

## T042 — efeito na suíte de cenários sintéticos: medido, nenhum

```
$ make test-synthetic
level solve rate  attempts  definition
1     100%        1         A single obvious cause with corroborating evidence.
2     100%        2         One planted confounder that must be explicitly ruled out.
3     100%        1         Several plausible causes requiring evidence to discriminate.
4     100%        1         The most prominent signal is misleading; the true cause is secondary.

  ok   [1] kubernetes/001-oom-kill                         1/1
  ok   [2] kubernetes/002-liveness-probe-killing           1/1
  ok   [2] observability/005-dependency-timeout            1/1
  ok   [3] kubernetes/003-rollout-regression               1/1
  ok   [4] delivery/007-misleading-cpu-signal              1/1

5/5 attempts passed (100%) in 0.1s
```

**Nenhum efeito, e por que era esperado que não houvesse**: o corpus
sintético roda offline, contra respostas gravadas por cenário — não passa
pelo caminho de invocação real que `force_tool_call` toca.
`InvokeRequest.force_tool_call` nasce com `False` por padrão e só é ligado
pelo probe de preflight (`core/llm/preflight.py._tool_call_check`); os
quatro adaptadores só mudam o payload quando ele está ligado — confirmado
pelo próprio teste de contrato desta feature
(`tests/contract/llm/test_tool_call_forcing_contract.py`), que compara
byte-a-byte o payload não-forçado com o comportamento de antes desta
feature. A listagem dinâmica e a rota nova também não entram no caminho de
uma investigação — são lidas só pelas telas de configuração. 5/5 é o mesmo
resultado que o corpus já tinha; medido, não presumido.

## Premissas registradas no início da execução (a confirmar/ajustar conforme o código prova)

- **Lista real de 37 nomes (T001)**: esta sessão não tem acesso ao CT254 nem à
  API do Gemini para recolher a lista ao vivo. A fixture foi construída como um
  conjunto representativo e plausível — nomeado explicitamente como tal no
  próprio módulo — cobrindo os nomes que a spec cita por extenso
  (`gemini-3.5-flash`, `gemini-3.6-flash`, `gemini-3.7-flash`, os `-latest`,
  `gemini-2.5-pro`, `gemini-2.5-flash`) mais entradas adicionais das cinco
  famílias que a curadoria descarta (imagem, áudio/fala, robótica, música,
  embedding), com 37 entradas ao todo para bater o número que a spec cita.
  **Isto é uma fixture de teste, não uma recaptura do endpoint real.**
- **`ModelStep` do wizard (passo "Model", distinto do passo "Verify"/M5)
  permanece na lista estática.** As âncoras normativas desta spec são `#m1`
  (tela Models & providers) e `#m5` (passo Verify); FR-056/057 e o teste
  independente da User Story 1 citam "Models & providers" nominalmente. Ligar
  também o passo de escolha do wizard à listagem dinâmica ficaria mais completo
  end-to-end, mas não é uma âncora nem FR desta spec — nomeado aqui como
  decisão de escopo, não escondido.
- **Credencial via vault/credential proxy (FR-002/003)**: o mecanismo real de
  proxy de credencial para *providers* de modelo não está implementado neste
  repositório como algo que o gateway compõe inline — é uma responsabilidade
  do composition root de cada deployment, exatamente como `state.model_verifier`
  e `state.deep_verifier` já documentam ("reaching a vendor means a credential
  proxy and a transport, and a gateway that built one from whatever ambient
  configuration was present would be reaching a cluster nobody chose"). A
  listagem segue o mesmo padrão: passa por `CredentialResolver` (a costura que
  o vault substitui, por design já documentado em `core/llm/credentials.py`),
  com `EnvironmentCredentialResolver` como default e um ponto de injeção em
  `GatewayState` para quem compuser o vault de verdade — o mesmo grau de
  satisfação que a rota de `verify` já tem hoje para o mesmo requisito.

## Fechamento (T044) — o resumo que amarra tudo acima

**1. Números reais do fechamento.** `make verify` rodado alvo a alvo (a
sequência exata está em "T041 — números finais", com o motivo documentado
para rodar assim em vez de invocação única). Todo alvo — lint, format-check,
typecheck, check-imports, check-constants, check-protocols, check-deps,
check-config-parity, check-display-names, check-vendor-sdks, check-literals,
check-raw-sql, check-credentials, check-console-boundary, check-integrations,
check-integration-docs, check-env-example, check-docs, check-doc-examples,
console-check — fechou com exit 0, verificado em arquivo separado do log
(nunca `comando > log; echo $?` na mesma linha). Python completo (`make
test`): **11729 passaram, 25 pulados, 1 reprovou** — a única reprovação é
`test_the_untouched_baselines_still_match`, explicada por inteiro em "T041 —
números finais": não é esta feature quebrando algo, é a baseline visual
aceita (T040) ainda não commitada colidindo com a mesma trava de baseline
limpa que `check-config-parity` também respeita — as duas exigem estados
opostos da mesma pasta, e só fecham juntas depois do commit que esta sessão
não faz. Integrações: **15 em paridade plena, toda permissão sondada**
(`tools.verify_integrations`). Console, separado por suíte:
- unitária + cobertura: **140 arquivos, 2259 testes, 0 falhas**; branches
  90.15% (piso de 90% cruzado).
- comportamento (`behaviour`): **144 passados, 6 pulados, 0 falhas** (150).
- primeiro-dia (`first-day`): **15 passados, 0 falhas.**
- visual: **30 passados, 0 falhas**, contra a baseline aceita nesta sessão.

**2. Vermelho capturado, e o que não foi visto vermelho.** As mensagens
reais de T004/T005 (os dois arquivos de acceptance) estão em "Vermelho
capturado (mensagem real)", com a saída literal do Playwright para as duas
telas. Os vermelhos de backend (T006-T011) e a confirmação
`ModuleNotFoundError: No module named 'core.llm.catalogue'` estão na mesma
seção e em "Honestidade sobre a ordem". **O que não nasceu vermelho, dito
sem meio-termo**: a correção de `contract_verdict` (tool calling degradado
deixa de bloquear) foi editada antes de o teste antigo ser rodado contra o
código novo; a forçagem de tool call (`force_tool_call` e os quatro
adaptadores) foi implementada antes de `test_tool_call_forcing.py` existir;
e — descoberto só ao reler esta sessão para fechar — as reescritas completas
de `verify.tsx` (T036-T038) e `models-editor.tsx` (T032-T035) também
precederam parte dos testes que hoje as provam: `console/tests/unit/
surfaces/first-run.test.tsx` e `console/tests/unit/surfaces/settings/
models.test.tsx`/`models-editor.test.tsx` tinham, entre si, um bloco inteiro
("continuing past verification") escrito contra os testids antigos
(`continue-anyway`) até esta última rodada de fechamento, quando finalmente
foram corrigidos e confirmados verdes contra o código já existente — não
vermelho-antes-do-código para essas asserções específicas, dito exatamente
assim, sem diluir. Tudo o mais nas Fases 8-9 (o card de estado, o bloco de
erro estruturado, a linha de herança, o rodapé de degradados) foi retrofit
pela mesma razão, já registrada em "Honestidade sobre a ordem" e no bloco
"Defeitos reais encontrados pelo acceptance".

**3. T042, antes e depois.** Não havia "antes" desta feature para os
cenários que `force_tool_call` toca, porque o campo nasce nesta feature —
o corpus sintético nunca exerceu essa opção. O "antes" que existe é o
resultado que o corpus já dava sem ela: 5/5 (100%), offline, sem
credenciais. O "depois", medido nesta sessão depois de tudo pronto: **5/5
(100%)**, mesmo tempo (0.1s), mesmos cinco cenários. Comando e saída
completos em "T042 — efeito na suíte de cenários sintéticos" acima.

**4. Os dois arquivos de acceptance.** `console/tests/e2e/010-provider-
out-of-the-box.acceptance.spec.ts` (M1, projeto `behaviour`) e
`console/tests/first-day/010-provider-out-of-the-box.acceptance.spec.ts`
(M5, projeto `first-day`) permanecem os dois, deliberadamente — justificativa
completa em "Desvio deliberado do caminho único de T004, registrado", perto
do topo deste arquivo: a rota `/first-run` redireciona para `/` sempre que o
checklist está completo, e só o cenário `first-run` (servido pelo projeto
`first-day`) tem o checklist aberto — o mesmo motivo que já dividia
`setup-wizard.spec.ts`/`first-day.spec.ts` antes desta feature existir. As
alegações de M1 continuam no único caminho que a tarefa pede.

**5. Ressalvas de honestidade, sem diluir.** Fixtures de cenário são
geradas, nunca editadas à mão — a correção do próprio engano está registrada
em "Correção grave de método". O vazamento de credencial que o teste de
segurança desta sessão encontrou (e corrigiu, antes de qualquer commit) está
em "Achado de segurança real". A tela Models & providers hoje mostra o
fallback "Static list" no card do investigador na baseline visual (a listagem
dinâmica depende de um round-trip que a captura visual não espera antes de
fotografar) — um detalhe honesto da imagem aceita, não escondido. **Sobre o
stash da baseline visual**: usado deliberadamente, duas vezes, só pela janela
em que `check-config-parity`/`make test` precisavam da pasta limpa contra o
HEAD; confirmado agora, por comando, que a árvore final não tem nada
stashed (`git stash list` vazio) e que `console/visual/baselines/` mostra
exatamente as sete imagens que T040 aceitou de propósito — nenhuma baseline
"aceita" por acidente de um gate, nenhuma baseline de outra feature tocada.
Uma varredura final desta sessão (ver abaixo) também encontrou seis citações
de identificador de planejamento escritas por mim mesma em código committed
— `core/llm/catalogue/__init__.py`, `core/llm/catalogue/gemini.py`,
`gateway/http/routes/providers.py` e `tests/unit/core/llm/
test_model_catalogue.py` — corrigidas nesta mesma rodada, com o contrato
OpenAPI e o cliente do console regenerados depois para propagar a correção
de `providers.py`. Três outras ocorrências (`console/src/design/status.ts`,
`console/tests/e2e/settings-agent.spec.ts`, `config/constants/llm.py`) são
pré-existentes — confirmado por `git diff`, nenhuma delas nasceu nesta
sessão — e ficaram como estavam, por instrução explícita de não abrir frente
nova nesta rodada de fechamento; nomeadas aqui, não escondidas.

**6. T043.** Como já registrado e confirmado correto: não alcançável desta
sessão, não marcada, roteiro de três passos deixado para quem tiver acesso
à rede do cluster.

**Confirmação final, por comando:**
```
$ git diff --cached --name-only
(vazio)
$ git stash list
(vazio)
```
Nenhum identificador de planejamento em arquivo committed além dos três
pré-existentes nomeados no item 5 (não introduzidos por esta sessão, não
tocados por instrução). `tasks.md`: 43 de 44 marcadas — só T043 fica aberta,
pelo motivo já dito. Este `controle.md` é a última coisa escrita nesta
sessão.
