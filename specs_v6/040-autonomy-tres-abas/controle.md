# Controle — Autonomy & guardrails em três abas

**Fatia 1 de N.** Este documento abre o controle desta feature. O estado
abaixo foi verificado contra o código atual da árvore de trabalho — cada
linha citada foi aberta e, onde fazia sentido, executada; nada foi copiado
de intenção. Branch `feat/v6-scope-and-settings`, em cima de `d7544ca`. Nada
foi commitado, staged, nem passou por `git add` nesta sessão.

**Escopo desta fatia**: só o bloqueador de fixture da User Story 6 e a
remedição de três números que `spec.md` afirma sobre o estado atual. Nenhum
arquivo de tela foi tocado — nenhuma aba, nenhum `console/src/surfaces/settings/autonomy.tsx`,
nenhuma captura visual. `tasks.md` continua com **todas** as caixas
desmarcadas: nada aqui corresponde a uma tarefa numerada de T001 a T045 —
esta fatia é o trabalho preparatório que o pré-flight do orquestrador pediu
antes de T001 começar. Por isso nenhuma caixa foi marcada.

## 1. Tabela de estado

| Peça | Estado | Detalhe |
|---|---|---|
| Fixture do override ativo (bloqueador User Story 6) | **FEITO** | `tools/mockplane/dataset/served.py:222-241` (constante `_ACTIVE_OVERRIDE`) e `:1542` (`"overrides": [dict(_ACTIVE_OVERRIDE)] if identifier == ORG_NODE else []`), regenerado via `uv run python -m tools.mockplane build` em `fixtures/scenarios/populated/autonomy-bounds.json`. Verificado por `uv run pytest -q tests/contract/fixtures` (107 passed) e por dois testes Playwright reais (`scroll-budget.spec.ts`, `transversal-rules.spec.ts`) contra o build servido. |
| Decisão de não tocar `autonomy-policy.json` | **FEITO (decisão registrada, não uma omissão)** | Ver §2.3. `_policy_document()` (`served.py:244`) é consumida por dois lugares — a própria `autonomy-policy` (`served.py:1514`) e `agent_records()` via `PolicySet.of_document(_policy_document(identifier))` (`served.py:2867`, alimentando `autonomy-outlook`/`autonomy-preview`, a tela `/agent`). Tocar o campo `overrides` ali sangraria para `/agent`, fora do escopo desta feature. O console só lê `overrides` de `bounds` (`console/src/surfaces/settings/autonomy.tsx:266`: `list(dataOf(bounds), 'overrides')`), nunca de `policy` — a decisão não deixa nenhuma alegação da spec sem suporte. |
| SC-001 remedido | **FEITO** | Ver §3.1. Real hoje (nesta árvore, já com o override do item acima): **2065px em 1920×1080 ≈ 1.91 viewports**, contra a alegação da spec de 2026px/2.3 viewports. Medido com um script descartável (apagado) e confirmado pelo teste committed `console/tests/e2e/scroll-budget.spec.ts:91` (`/autonomy stays within the scroll budget`), verde. |
| SC-002 remedido | **FEITO** | Ver §3.2. Real hoje: **0 células vazias** nas duas aparições da tabela de guardrails (tabela principal "Guardrails in effect": 6 linhas, 0 vazias; seção avançada recolhida `policies.autonomy.`: 4 linhas, 0 vazias), contra a alegação da spec de 12 vazias. Confirmado pelo teste committed `transversal-rules.spec.ts:248` para `/settings/autonomy-guardrails`, verde. |
| SC-008 remedido | **FEITO** | Ver §3.3. Confirmado por leitura direta: `EXCEPTIONS` em `transversal-rules.spec.ts:141-147` tem uma única entrada (`/settings/alert-intake` + `scroll-budget`); `/settings/autonomy-guardrails` não tem nenhuma exceção declarada em nenhuma das três regras. A regra de orçamento de rolagem da própria `transversal-rules.spec.ts` faz `test.skip` para esta rota (está em `SCROLL_BUDGET_MEASURED_ELSEWHERE`, linha 171) e delega a medição real a `scroll-budget.spec.ts`, que mede e passa. Nuance registrada em §3.3 para quem escrever o acceptance da feature. |
| Os dois sites de `Badge` com nível cru e o `dt` em mono do nome do override | **Fora do escopo desta spec** | Ver §4. Investigado e não corrigido, por instrução explícita. Nenhuma das 52 FRs cobre a tradução do valor renderizado por `<Badge status={level}/>`/`<Badge status={override.level}/>`; o ban de vocabulário da suíte transversal (FR-051) não pega essas strings — confirmado empiricamente, o teste de vocabulário passa hoje com o override do item 1 já renderizando `act_and_report` cru via Badge. Achado nomeado para o orquestrador decidir a quem atribuir. |

## 2. Parte 1 — o bloqueador de fixture, em detalhe

### 2.1 O que o override precisava ter, e de onde veio a forma

Antes de escrever qualquer coisa, li o que `OverrideEditor` e `autonomy.tsx`
realmente consomem, não o que parecia plausível:

- `console/src/surfaces/override-editor.tsx:70-79` — a interface
  `ActiveOverride`: `name`, `level`, `expiresIso`/`expiresRelative`/`expiresAbsolute`
  (derivados, não vindos do fixture), `reason`, `grantedBy` (`''` quando o
  deployment não informou). O componente renderiza cada campo condicionalmente
  — `reason`/`grantedBy` só aparecem se não vazios (`override-editor.tsx:347-356`)
  — então um override com todos os campos preenchidos é o que exercita mais
  do componente de uma vez.
- `console/src/surfaces/settings/autonomy.tsx:266-276` — a construção real:
  `const overrides = list(dataOf(bounds), 'overrides'); const activeOverrides = overrides.map((override) => ({ name: text(override, 'name'), level: text(override, 'level'), expiresIso: expires.iso, ..., reason: text(override, 'reason'), grantedBy: text(override, 'granted_by') }))`.
  A forma bruta que o fixture precisa declarar é, portanto,
  `{ name, level, expires_at, reason, granted_by }` — `snake_case`, exatamente
  os nomes que `text()` lê.
- `autonomy.tsx:700-720` (painel de resumo "Autonomy bounds", ao lado da
  aba) e `:690-760` (o próprio `<OverrideEditor>` no painel de override) são
  os dois lugares que consomem `activeOverrides` — ambos ficavam
  estruturalmente inalcançáveis com `overrides: []`, exatamente o "pattern C"
  que o pré-flight nomeou: um teste que passa porque o dado nunca chega no
  ramo é indistinguível de um teste que passa porque o código está certo.

### 2.2 A forma escolhida, e por quê

Adicionada em `tools/mockplane/dataset/served.py:222-241`, como constante
nomeada `_ACTIVE_OVERRIDE`, referenciada só para o nó `org-northwind`
(`ORG_NODE`) dentro do laço de `config_records()` (`served.py:1542`):

```python
"overrides": [dict(_ACTIVE_OVERRIDE)] if identifier == ORG_NODE else [],
```

- **Por que só um nó, não os cinco**: `resolveNode` (`console/src/surfaces/url-state.ts:116-128`)
  escolhe, na ausência de `?node=` na URL, o `team_node_id` do viewer —
  e o viewer padrão do dataset (`identity_records()`, `served.py:2613-2645`)
  tem `"team_node_id": ORG_NODE`. Ou seja, `org-northwind` é exatamente o nó
  que a rota abre em por padrão, sem precisar de query string — o alvo mais
  útil para qualquer teste futuro que não escolha nó explicitamente. Repetir
  o mesmo override, idêntico, nos cinco nós (organização, dois times, dois
  ambientes) leria como um fixture posando, não como um deployment real em
  operação — um override é concedido a alguém trabalhando um nó específico.
- **Os valores**: `name: "storage-capacity-response"` (identificador curto,
  o texto de ajuda do próprio campo diz "unique on this node" —
  `en.ts:1121-1122`); `level: "act_and_report"` (um dos três níveis que
  `OVERRIDE_LEVELS` oferece — `autonomy.tsx:67` —, uma elevação real a partir
  do default `propose_only`); `reason` com uma frase de auditoria plausível
  amarrada ao recurso `store-cove` que já é tema deste dataset (a janela de
  congelamento `nightly-backups` já o usa); `granted_by: "Morgan Thorne"`
  (o `display_name` de `REVIEWER`, `served.py:2444-2449` — um colega
  diferente de quem está olhando a tela, não o próprio viewer).
- **`expires_at`**: `"2026-09-01T12:00:00+00:00"`, um literal futuro, não
  `at()`. `at()` (`served.py:91-93`) só subtrai de `_CAPTURED`
  (`2026-08-07T09:41:00+00:00`) — um override ainda ativo precisa ler como
  um instante à frente de "agora", não como um deslocamento fixo de uma
  captura que já é passado. Depois do pipeline de deslocamento (ver §2.4), o
  valor commitado ficou `"2026-09-01T14:19:00+00:00"` — ainda
  confortavelmente no futuro tanto em relação a `FIXTURE_REFERENCE_INSTANT`
  quanto em relação a "hoje" real.

### 2.3 Por que `autonomy-policy.json` ficou com `overrides: []`

O pedido citava os dois arquivos como tendo `overrides = []`. Confirmei que
`_policy_document(node_id)` (`served.py:244-287`) é a única função que monta
o corpo de `autonomy-policy`, e que ela é chamada duas vezes:
`served.py:1514` (o próprio endpoint `autonomy-policy`) e `served.py:2867`,
dentro de `agent_records()`, para construir `PolicySet.of_document(...)` que
alimenta `autonomy-outlook`/`autonomy-preview` — o que a tela `/agent`
consome. Mudar o campo `overrides` de `_policy_document` teria efeito
colateral em `/agent`, uma tela que esta fatia não deve tocar ("no screen
files"). Confirmei também, por leitura de `autonomy.tsx:266`
(`list(dataOf(bounds), 'overrides')`), que o console **nunca** lê `overrides`
de `policy` — só de `bounds`. A decisão de deixar `autonomy-policy.json`
como estava é, portanto, deliberada e não deixa nenhuma alegação da spec sem
fixture: nada em `spec.md` pede que a tela leia override de `policy`.

### 2.4 Uma descoberta que vale a pena registrar para quem editar fixtures depois

`tools/mockplane/anonymise/pipeline.py:process()` desloca **todo** timestamp
ISO-8601 em qualquer lugar do corpo por um único offset —
`FIXTURE_REFERENCE_INSTANT` (`2026-08-07T12:00:00+00:00`,
`config/constants/fixtures.py:76`) menos `profile.CAPTURED_AT`
(`2026-08-07T09:41:00+00:00`) — determinístico, não o relógio real da
máquina. É por isso que `2026-09-01T12:00:00+00:00`, escrito à mão, saiu
como `2026-09-01T14:19:00+00:00` no arquivo commitado: um deslocamento fixo
de 2h19min, o mesmo para qualquer timestamp em qualquer lugar do dataset —
inclusive um literal escrito à mão, não só os produzidos por `at()`. Isso
importa porque **não** é um sinal de não-determinismo (`test_two_builds_of_one_scenario_are_byte_identical`
passou, confirmando) — é o mecanismo de "todo timestamp anda junto" descrito
no próprio docstring de `timeshift.py`. Um literal ISO escrito num fixture
não escapa do deslocamento só por não ter vindo de `at()`.

### 2.5 O que mudou em disco, e só isso

```
$ git diff --stat -- fixtures/ tools/mockplane/
 fixtures/scenarios/populated/autonomy-bounds.json | 10 +++++++++-
 tools/mockplane/dataset/served.py                 | 23 ++++++++++++++++++++++-
 2 files changed, 31 insertions(+), 2 deletions(-)
```

Só `populated/autonomy-bounds.json` mudou — `restricted/` (só
`principal.json`), `incident-live/` (só `run-stream.json`) e `degraded`
(sem diretório próprio, é `populated` mais uma declaração de falha) não têm
arquivo próprio de `autonomy-bounds`, então herdam a mudança de `populated`
na hora de servir, sem precisar de edição própria. `scale` é gerado por
`generate_scale()` (`tools/mockplane/dataset/scale.py`), uma rota totalmente
separada — não tocada, não deveria ser.

### 2.6 Comandos rodados, com resultado real

```
$ uv run python -m tools.mockplane build
wrote 227 files across 6 scenarios
```

```
$ uv run pytest -q tests/contract/fixtures
........................................................................ [ 67%]
...................................                                      [100%]
107 passed in 10.55s
```

Cobre, entre outros: `test_every_reference_in_every_scenario_resolves`
(`granted_by`/`name` não são chaves de referência declaradas —
`tools/mockplane/verify/referential.py:69-79` — então não precisam resolver
contra `principals`), `test_every_scenario_reads_as_a_coherent_history`,
`test_rebuilding_the_dataset_reproduces_what_is_committed`,
`test_two_builds_of_one_scenario_are_byte_identical`,
`test_the_committed_files_are_written_in_the_canonical_form`,
`test_nothing_real_survives_in_the_committed_tree` — todos verdes.

```
$ uv run ruff check tools/mockplane/dataset/served.py
All checks passed!
$ uv run ruff format --check tools/mockplane/dataset/served.py
1 file already formatted
$ uv run mypy tools/mockplane/dataset/served.py
Success: no issues found in 1 source file
```

## 3. Parte 2 — as três remedições

Medidas com um script Playwright descartável
(`console/tests/e2e/_scratch-slice1-measure.spec.ts`), rodado uma vez para
capturar os números brutos, depois apagado — não sobrou no repositório.
Cada número foi confirmado de novo por um teste **committed** real (não o
script descartável), contra o build padrão do console
(`.next/standalone/server.js`) e o cenário `populated` servido por
`tools.mockplane`, via:

```
uv run python -m tools.console_e2e run --backing mock --scenario populated \
  -- tests/e2e/scroll-budget.spec.ts tests/e2e/transversal-rules.spec.ts
```

(`tools/spec_validation.py` é um wrapper fino sobre esta mesma função —
`run_browser_validation` chama `tools.console_e2e.run`; usei a chamada
direta.) Resultado: **33 passed, 7 skipped, 0 failed (9.6-9.8s)**, `exit 0`,
em duas rodadas. Os 7 skipped são os esperados: a exceção de
`scroll-budget` de `/settings/alert-intake` mais as seis rotas em
`SCROLL_BUDGET_MEASURED_ELSEWHERE` (`/settings/autonomy-guardrails`
incluída).

### 3.1 SC-001 — altura de rolagem em 1920×1080

| | Alegação da spec ("hoje") | Medido agora, nesta árvore |
|---|---|---|
| Altura | 2026px | **2065px** |
| Viewports (÷1080) | 2.3 | **≈1.91** |

Linha de saída do script descartável:

```
SLICE1 height=2065
```

Confirmado pelo teste committed, verde:

```
✓ 4 [behaviour] › tests/e2e/scroll-budget.spec.ts:91:3 › /autonomy stays within the scroll budget (286ms)
```

(`/autonomy` é o endereço aposentado que redireciona para
`/settings/autonomy-guardrails` — o mesmo documento, confirmado pelo
comentário em `transversal-rules.spec.ts:168-171`.)

**Leitura honesta do número**: 2065px é **maior** que os 2026px que a spec
cita como "hoje", não menor — mesmo com a coluna Value já preenchida pela
020 e os títulos de seção já humanizados pela 030. A razão mais provável é
que esta própria fatia acabou de tornar o override real: antes desta sessão,
`overrides: []` significava que a linha `data-bound="override"` no painel
lateral "Autonomy bounds" (`autonomy.tsx:700-720`) nunca era desenhada para
nenhum nó — nenhum teste do repositório jamais tinha visto essa altura. O
número medido agora (2065px) é o estado real que as fatias seguintes vão
construir em cima, incluindo o conteúdo que a User Story 6 exige exibir.
Ainda está dentro do orçamento de página inteira vigente (2 viewports =
2160px em 1080p, `config/constants/surfaces.py:344-350`) — com folga de
95px, não zero. Isso não diz nada sobre o orçamento **por aba** (1.5
viewport = 1620px) que esta feature ainda vai criar: esse orçamento só
existe quando as abas existirem, e o conteúdo de cada aba será um subconjunto
desta página, não a página inteira.

### 3.2 SC-002 — células vazias na coluna Value

| | Alegação da spec ("hoje") | Medido agora, nesta árvore |
|---|---|---|
| Células vazias, tabela principal ("Guardrails in effect") | (12 no total, sem separar) | **0** de 6 linhas |
| Células vazias, seção avançada recolhida (`policies.autonomy.`) | (12 no total, sem separar) | **0** de 4 linhas |
| Total | 12 | **0** de 10 |

Linhas de saída do script descartável:

```
SLICE1 main-table rows=6 empty=0
SLICE1 advanced-table rows=4 empty=0
SLICE1 all-effective-field-rows-on-page=10
```

Confirmado pelo teste committed, verde:

```
✓ 29 [behaviour] › tests/e2e/transversal-rules.spec.ts:248:5 › /settings/autonomy-guardrails › draws no empty cell in a configuration table's Value column (316ms)
```

**Por que o número mudou de 12 para 0**: `EffectiveFieldsTable`
(`console/src/design/resolution-preview.tsx:286-304`) — o componente que
desenha as duas aparições da tabela desta rota (a principal, em
`autonomy.tsx:558-565`, e a de dentro de `AdvancedConfigSection`, em
`advanced-config-section.tsx:180-190`) — **lança uma exceção** se qualquer
linha chegar com `value` ou `origin` vazios (`resolution-preview.tsx:290-303`).
Não é mais possível a coluna Value ficar vazia nesta rota sem quebrar a
tela inteira; a 020 fechou essa porta estruturalmente, não célula por
célula. O número de 12 do `spec.md` descreve a tela de antes da 020 e da 030
— está definitivamente obsoleto, não só "provavelmente".

**Confirmação com a segunda tela também**, já que a alegação da spec fala em
"duas aparições" sem nomear qual página as tem hoje: a segunda aparição é a
seção `<details>` recolhida (`policies.autonomy.` — `autonomy.tsx:179,620-632`),
não uma segunda rota. `configurationValueCells()` em `transversal-rules.spec.ts:187-206`
já abre todo `<details>` antes de medir, exatamente por essa razão (documentada
ali: "Playwright `innerText()` returns '' inside a closed `<details>`").

### 3.3 SC-008 — suíte transversal sem exceção declarada

Confirmado por leitura direta, sem precisar rodar nada (mas rodado mesmo
assim, ver acima):

- `transversal-rules.spec.ts:141-147` — `EXCEPTIONS` tem **uma** entrada:
  `{ path: '/settings/alert-intake', rule: 'scroll-budget', reason: '...' }`.
  Nenhuma entrada para `/settings/autonomy-guardrails`, em nenhuma das três
  regras (`vocabulary`, `scroll-budget`, `value-column`).
- `transversal-rules.spec.ts:161-172` — `SCROLL_BUDGET_MEASURED_ELSEWHERE`
  inclui `/settings/autonomy-guardrails`, com o comentário explícito
  (`:135-140,168-171`) dizendo que a rota é medida pelo teste irmão
  (`scroll-budget.spec.ts`) via o endereço aposentado `/autonomy`, que
  redireciona para cá — e que uma segunda entrada em `EXCEPTIONS` para o
  mesmo par seria "código morto e inalcançável", não uma segunda afirmação
  do mesmo fato.

**A nuance que vale registrar para quem escrever o acceptance da feature
(T001)**: a regra de orçamento de rolagem da própria `transversal-rules.spec.ts`
faz `test.skip(...)` para esta rota (`:229-232`) — não é uma passagem, é uma
ausência de execução **naquele arquivo especificamente**, delegada para
`scroll-budget.spec.ts`. A letra do SC-008 ("suíte transversal roda nesta
rota com zero exceções declaradas... nenhum teste marcado para falhar ou
pular por causa dela") fica tecnicamente ambígua neste ponto: o teste **é**
marcado `test.skip` "por causa desta rota" (a rota está na chave do
`Set` que decide o skip), mas a razão documentada não é "esta rota viola a
regra" e sim "esta rota já é medida em outro lugar, contra a mesma
constante". As outras duas regras (`vocabulary`, `value-column`) rodam de
verdade nesta rota, dentro deste mesmo arquivo, e passam. Este slice não
resolve essa ambiguidade de leitura — só a nomeia, porque `spec.md` não
distingue "medido em outro arquivo" de "isento", e a instrução desta fatia
foi medir e relatar, não decidir. Quando as três abas existirem, o acceptance
da feature vai precisar decidir se mede o orçamento por aba dentro de si
mesmo (o que `tasks.md` T011 já prevê — estender `scroll-budget.spec.ts`
"por aba") ou se aceita a mesma delegação que a rota única usa hoje.

## 4. Os dois sites de `Badge`, investigados e não corrigidos

`autonomy.tsx:423` (`<Badge status={level}/>`, tabela de regras),
`autonomy.tsx:710` (`<Badge status={override.level}/>`, resumo do painel
lateral) e `override-editor.tsx:340` (`<Badge status={override.level}/>`,
lista de overrides ativos dentro do próprio editor) desenham o nível de
autonomia — `propose_only`, `act_on_low_risk`, `act_and_report`,
`act_silently` — verbatim, em letras maiúsculas (a classe `uppercase` de
`Badge`). Antes desta sessão, o site de `:710` e o de `override-editor.tsx:340`
eram estruturalmente inalcançáveis (mesmo bloqueador do item 1) — o override
que esta fatia adicionou faz `act_and_report` aparecer cru, pela primeira
vez, em qualquer teste deste repositório.

**Por que não é o defeito de palavra crua de saúde que a feature anterior
removeu**: `BANNED_VOCABULARY` em `transversal-rules.spec.ts:181-182` é
`/SERVICE_ACCOUNT|HEALTHY|policies\.|surfaces\.|models\.investigator|webhook\.deliver|_id is required/`
— não contém nenhum dos quatro slugs de nível. Confirmado empiricamente: a
suíte transversal passou (§3, `27 ✓ carries no banned vocabulary`) com o
override do item 1 já renderizado na página, `act_and_report` cru e tudo.

**Por que é, mesmo assim, uma inconsistência real**: `console/src/surfaces/postures.ts`
existe exatamente para isso — o próprio docstring do módulo diz "a badge
that printed an identifier where a state should be" era o defeito antigo, e
`postureLabel`/`postureLabels` já traduzem os quatro slugs
(`autonomy.level.propose_only` etc., já presentes em `en.ts:48-55`). Essa
tradução **já está** ligada ao seletor de Posture (`autonomy.tsx:64-67`, via
`LEVELS`) e ao campo Level do formulário de concessão de override
(`autonomy.tsx:756`, `levelLabels={postureLabels(locale, OVERRIDE_LEVELS)}`)
— só não está ligada aos três sites de `Badge` acima, na mesma página, para
o mesmo vocabulário. É o mesmo valor, traduzido num controle e cru no
Badge ao lado.

**Cobertura pela spec, verificada FR a FR**: nenhuma das 52 FRs nomeia como
o valor dentro de um `Badge`/chip de nível deve ser mostrado — FR-013 fala
só do seletor; FR-043 exige que o painel "mostre... nível", sem prescrever
o widget; FR-051 (suíte transversal sem exceção) não pega porque o ban de
vocabulário não inclui esses slugs, confirmado acima. O mockup M2
(`specs_v6/mockups/settings-v6.html:206-257`) mostra o vocabulário de
postura sempre em palavras humanas onde aparece — o subtítulo
("Posture now: propose-only") e o campo Level do painel ("Act within
bounds ▾") — mas não desenha nenhum dos três widgets específicos onde o
cru aparece hoje (a tabela de regras da aba Rules & windows e o estado "com
override ativo" do painel não estão no recorte estático do M2, que mostra
Posture sem override). O mockup sustenta a leitura de que o vocabulário
deveria ser humano em toda a tela, mas não prova que os três sites exatos
estão cobertos por um requisito escrito.

**Veredito**: achado real, consistente, de correção mecânica pequena (trocar
`status={level}` por algo que passe por `postureLabel(locale, level)` nos
três sites), mas **não coberto por nenhuma FR desta spec** e não pego pelo
gate de vocabulário. Não é meu para corrigir nesta fatia. Recomendo ao
orquestrador decidir a quem atribuir — o lugar mais natural é dentro das
fatias futuras de User Story 3 (a aba Guardrails, dona da tabela de regras)
e User Story 6 (o painel de override) desta mesma feature, já que os três
sites vivem exatamente onde essas histórias vão trabalhar de qualquer forma.

Sobre o `<dt className="font-mono">{override.name}</dt>` em `:708`: **não é
uma anomalia isolada**. `autonomy.tsx:673-696` mostra que o mesmo painel
desenha `name` de freeze (`:674-676`) e de budget (`:685-687`) com a mesma
classe `font-mono min-w-0 truncate` — os três tipos de "bound" (freeze,
budget, override) compartilham o estilo para o mesmo tipo de dado: um
identificador curto, escolhido por quem criou o registro, não uma frase.
`spec.md` não prescreve tipografia para o campo `name`. Não vejo isso como
defeito a nomear separadamente do achado do Badge acima.

## 5. O que fica pendente, nomeado, não escondido

- **Toda a feature além desta fatia**: T001 a T045 de `tasks.md`, nenhuma
  caixa marcada. Isso inclui o acceptance da feature
  (`console/tests/e2e/autonomy-tres-abas.acceptance.spec.ts` — sem o número
  da feature no nome, seguindo a decisão já registrada em
  `specs_v6/progress.json` para toda a onda —, ainda não criado), a
  constante de orçamento por aba em `config/constants/surfaces.py`, os dois
  módulos novos (`autonomy-tabs.ts`, `guardrail-values.ts`), a divisão em
  três abas, o painel de override, e tudo o mais.
- **Os três sites de `Badge` com nível cru** (`autonomy.tsx:423`, `:710`,
  `override-editor.tsx:340`) — investigados, não corrigidos, sem dono
  atribuído. Ver §4.
- **A ambiguidade de leitura do SC-008** sobre "medido em outro arquivo" vs.
  "isento" — nomeada em §3.3, não resolvida; quem escrever T001 precisa
  decidir como o acceptance da feature vai medir o orçamento por aba.
- **`autonomy-policy.json` continua com `overrides: []`** — decisão
  deliberada (§2.3), não uma omissão, mas registrada aqui para o caso de
  uma fatia futura precisar do valor ali também (nenhuma FR pede isso hoje).

## 6. Gates rodados

| Gate | Comando | Resultado |
|---|---|---|
| Contrato de fixtures | `uv run pytest -q tests/contract/fixtures` | 107 passed, 10.55s |
| Lint Python | `uv run ruff check tools/mockplane/dataset/served.py` | All checks passed! |
| Formato Python | `uv run ruff format --check tools/mockplane/dataset/served.py` | 1 file already formatted |
| Tipos Python | `uv run mypy tools/mockplane/dataset/served.py` | Success: no issues found in 1 source file |
| Unit (vitest), sanidade | `pnpm exec vitest run tests/unit/surfaces/settings/autonomy.test.tsx tests/unit/surfaces/override-editor.test.tsx --pool=forks` (de `console/`) | 2 files, 40 tests passed |
| Browser, os dois specs tocados pela remedição | `uv run python -m tools.console_e2e run --backing mock --scenario populated -- tests/e2e/scroll-budget.spec.ts tests/e2e/transversal-rules.spec.ts` | 33 passed, 7 skipped, 0 failed |

**Não rodado, e por quê**: `make verify` completo — fora de proporção para
uma fatia que muda um único módulo Python e um fixture; a instrução desta
fatia também pede para não rodar nada que reescreva baseline visual, e
`make verify` inclui esse gate. `console_gate typecheck`/`lint`/`test`
completos do console — nenhum arquivo de `console/src` mudou nesta fatia;
os dois arquivos de teste relevantes foram rodados isoladamente acima em
vez de repetir a suíte inteira. Nenhuma baseline visual foi capturada,
aceita ou sobrescrita.

## 7. Arquivos alterados

- `tools/mockplane/dataset/served.py` — a constante `_ACTIVE_OVERRIDE` e a
  referência condicional a ela em `config_records()`.
- `fixtures/scenarios/populated/autonomy-bounds.json` — regenerado por
  `python -m tools.mockplane build` a partir da mudança acima; nenhuma
  edição manual.
- `specs_v6/040-autonomy-tres-abas/controle.md` — este arquivo, criado.

Nenhum outro arquivo foi tocado. O script Playwright descartável
(`console/tests/e2e/_scratch-slice1-measure.spec.ts`) foi criado, usado uma
vez e apagado — não existe mais na árvore de trabalho.

---

# Fatia 2 — a constante de orçamento por aba, e o acceptance da feature vermelho

**Escopo desta fatia**: exatamente três tarefas, nesta ordem — T003 (a
constante de orçamento por aba), T001 (o acceptance da feature) e T002 (rodar
e registrar o vermelho). Nenhum arquivo de tela foi tocado — nenhuma aba
implementada, `autonomy.tsx` não foi editado, `autonomy-tabs.ts` e
`guardrail-values.ts` (T004/T005/T006/T007) não existem. A fatia 1 acima
segue como estava; esta seção só acrescenta.

Branch `feat/v6-scope-and-settings`, em cima do commit da fatia 1
(`779d834`). Nada foi commitado, staged, nem passou por `git add` nesta
sessão.

**Uma rodada de correção aconteceu depois da primeira versão desta fatia**,
pedida pelo orquestrador contra três das nove alegações — (f), (g) e (i).
Documentada em detalhe onde cada uma vive (§9.1 e §9.2 abaixo, seção "Correção"
dentro de cada alegação): as três primeiras versões passariam por motivo
errado assim que a implementação existisse, não porque o defeito real tivesse
sido corrigido. Este documento contém só a versão final, já corrigida — não
existe uma segunda tabela de vermelho paralela e contraditória em lugar
nenhum.

## 8. Tabela de estado — Fatia 2

| Peça | Estado | Detalhe |
|---|---|---|
| T003 — constante do orçamento por aba | **FEITO** | `config/constants/surfaces.py:358` — `CONFIG_SCREEN_TAB_SCROLL_BUDGET_VIEWPORTS: Final[float] = 1.5`, ao lado de `CONFIG_SCREEN_SCROLL_BUDGET_VIEWPORTS` (`:350`, o orçamento de página inteira) e dos dois constantes de viewport (`:344-345`). Incluída no `__all__` do módulo (`:393`) e replicada no re-export de `config/constants/__init__.py:1199` e `:1473`, no mesmo padrão de toda outra constante deste módulo. `make check-constants` verde (ver §10). |
| T001 — acceptance da feature | **FEITO** | `console/tests/e2e/autonomy-tabs.acceptance.spec.ts` (372 linhas, depois da correção de (f)/(g)/(i) — ver §9.1/§9.2), nove testes distintos, um por alegação (a)–(i). Ver §9 para a decisão de cada um. |
| T002 — vermelho registrado | **FEITO** | 8 testes vermelhos, 1 verde, `9 tests using 1 worker`, `populated` servido — saída final (pós-correção) completa em §9.2, correspondência alegação-a-alegação com a mensagem real observada. Rodado quatro vezes ao todo nesta fatia: antes da correção, logo depois de aplicar as três correções, com a injeção de prova de (g), e a versão final restaurada — as quatro concordam em 8 falhas/1 passa. |

## 9. T001 em detalhe — as nove alegações, e as decisões por trás de cada uma

### 9.1 Decisões que o teste precisou tomar sozinho

Nada em `console/src/` declara ainda o parâmetro de aba nem os identificadores
das três abas — isso é T004/T005, fora desta fatia. Para escrever um teste
executável eu precisei escolher uma forma concreta, e a escolha vira o alvo
que a fatia de implementação tem que satisfazer:

- **Identificadores de aba**: `posture`, `rules-windows`, `guardrails`
  (`autonomy-tabs.acceptance.spec.ts:71`), no mesmo parâmetro `?tab=` e no
  mesmo componente `TabLinks` (`console/src/components/navigation.tsx:138-163`,
  `data-testid="tab-links"`/`"tab-link"`, `data-tab`, `aria-current="page"`)
  que a tela Decisions já usa hoje (`console/src/surfaces/screens/decisions.tsx:28-62`,
  `DECISIONS_TABS`/`DECISIONS_FILTERS = ['tab']`). Não inventei um mecanismo
  novo — reaproveitei o único que já existe no produto para "seção de uma
  tela, endereçável".
- **Rótulos exatos das abas**: "Posture", "Rules & windows", "Guardrails" —
  texto literal do mockup (`specs_v6/mockups/settings-v6.html:213`,
  `<div class="tabs"><span class="on">Posture</span><span>Rules & windows</span><span>Guardrails</span></div>`).
- **Painel lateral do override**: `getByRole('dialog', { name: /temporary override/i })`
  (`autonomy-tabs.acceptance.spec.ts:319`). Não inventei um testid novo — `Drawer`
  (`console/src/components/overlay.tsx:171` e a `Overlay` de base em `:107-108`,
  `role="dialog"`, `aria-labelledby` apontando para o `<h2>{title}</h2>`) já é
  o único componente do design system feito exatamente para "manter o
  contexto visível atrás" (a doc do próprio módulo, `overlay.tsx:9-21`), que é
  a letra de FR-038. Uso o papel de acessibilidade + o nome acessível
  ("Temporary override", o rótulo que o mockup usa), não um testid
  fabricado.
- **Botão do cabeçalho**: `page.getByTestId('page-header').getByRole('button', { name: /temporary override/i })`
  — `SettingsPageHeader`/`AreaHeader` já aceitam um slot `actions` renderizado
  dentro do próprio `<header>` (`console/src/shell/area.tsx:134-171`,
  `console/src/components/layout.tsx:27-49`), então um botão de ação no
  cabeçalho é um padrão existente, não inventado.
- **Ausência do corpo do override, ancorada no testid do componente —
  correção**: a primeira versão usava `getByRole('heading', { name: 'Grant or
  revoke an override' })`, um texto que qualquer rename apaga sem que o
  defeito real (o painel montado permanentemente no corpo) tenha sido
  corrigido — `not.toBeVisible()` passa quando o elemento simplesmente não
  existe mais sob aquele nome. Trocado por `page.getByTestId('override-editor')`
  — `override-editor.tsx:235`, `<div data-testid="override-editor"
  className="flex flex-col gap-5">`, o elemento mais externo de todo o
  componente (form de concessão + lista de revogação juntos), estável a
  qualquer mudança de texto. Mantido como checagem de **visibilidade**, não
  de presença: se a implementação futura mantiver o mesmo componente montado
  dentro de um `Drawer` fechado (`display:none` em vez de desmontado), a
  presença no DOM continua verdadeira e só a visibilidade muda — testar
  presença teria dado falso vermelho permanente para uma tela já correta.
- **Seção de simulação, testid próprio — correção**: a primeira versão
  contava botões pelo rótulo (`getByRole('button', { name: /^(Explain one
  action|Simulate everything|...)/  })`) dentro de `autonomy-editor`, com
  duas falhas apontadas pelo orquestrador e confirmadas por leitura: (1) se o
  CTA sobrevivente ganhar um rótulo novo — plausível, já que a seção também
  ganha título próprio e uma frase do que responde — a contagem cai para 0 e
  o teste vira falso vermelho depois da implementação estar correta; (2) o
  teste nada dizia se um SEGUNDO botão primário aparecesse ao lado do
  escolhido. A correção usa `Button`'s `data-variant={variant}`
  (`console/src/components/action.tsx:88`) como seletor direto — insensível
  a rótulo — e escopa a `page.getByTestId('autonomy-simulation')`, não a
  `autonomy-editor`: o editor inteiro também contém o botão de salvar regra,
  ele mesmo `variant="primary"` legitimamente, então contar primários ali
  teria contado esse também. `autonomy-simulation` não existe ainda — é o
  contrato que esta correção define para a implementação satisfazer, nomeado
  aqui em vez de deixado para adivinhar depois.

### 9.2 As nove alegações — decisão, alegação testada, e o vermelho observado

Comando rodado:

```
uv run python -m tools.spec_validation browser \
  --feature specs_v6/040-autonomy-tres-abas \
  --test console/tests/e2e/autonomy-tabs.acceptance.spec.ts
```

Saída real, versão final depois da correção (`serving the 'populated'
scenario on http://127.0.0.1:8424`, `Running 9 tests using 1 worker`,
`8 failed`, `1 passed (31.9s)`, build de produção do Next.js rodado do zero —
não um cache stale). Esta é a última de quatro rodadas do arquivo nesta
fatia — antes da correção (o vermelho original, já superado, não repetido
aqui), logo depois de aplicar as três correções, com a injeção de prova de
(g) (ver a alegação (g) abaixo), e esta, a versão final restaurada; as
quatro concordam em 8 falhas/1 passa, nas mesmas 9 posições de teste.

**(a) três abas, nomeadas e em ordem** —
`autonomy-tabs.acceptance.spec.ts:82`. **VERMELHO**:
```
Error: expect(locator).toHaveCount(expected) failed
Locator: getByTestId('tab-links').getByTestId('tab-link')
Expected: 3
Received: 0
14 × locator resolved to 0 elements
```
Nem `tab-links` nem `tab-link` existem hoje — a tela não tem abas.

**(b) cada aba no seu endereço, URL reflete a ativa** —
`:95`. **VERMELHO**:
```
Error: expect(locator).toHaveAttribute(expected) failed
Locator: getByTestId('tab-links').getByTestId('tab-link').filter({ hasText: 'Guardrails' })
Expected: "page"
Error: element(s) not found
```

**(c) sem aba nomeada → Posture; nome desconhecido → Posture** —
`:114`. **VERMELHO**, mesma causa raiz de (b):
```
Error: expect(locator).toHaveAttribute(expected) failed
Locator: getByTestId('tab-links').getByTestId('tab-link').filter({ hasText: 'Posture' })
Error: element(s) not found
```

**(d) altura de cada aba ≤ orçamento, lido da constante nomeada** —
`:133`. **VERMELHO**, e com um número real:
```
Error: tab=posture is 2065px tall against a 1620px budget (1.5 viewports of 1080px)
Expected: <= 1620
Received: 2065
```
1620px = `CONFIG_SCREEN_VIEWPORT_HEIGHT_PX` (1080) ×
`CONFIG_SCREEN_TAB_SCROLL_BUDGET_VIEWPORTS` (1.5), os dois lidos da
constante — nada escrito no teste. 2065px bate exatamente com a medição já
registrada na Fatia 1 (§3.1) para a página inteira de hoje — coerente, porque
sem abas toda "aba" pedida por `?tab=` ainda renderiza a página inteira.

**(e) zero células vazias na coluna Value, nas duas aparições** —
`:256`. **VERDE já na primeira execução** — o único teste que passou. Isto é
**honesto, não um defeito do teste**: a instrução desta fatia já previa este
resultado, e a Fatia 1 (§3.2) já tinha medido e explicado por quê —
`EffectiveFieldsTable` (`console/src/design/resolution-preview.tsx:286-304`)
lança exceção se qualquer linha chegar com `value`/`origin` vazios, então a
propriedade está fechada estruturalmente desde a feature anterior. Não
escrevi a asserção contra "reduzir de 12 para 0" — teria passado sem provar
nada; escrevi como **verificação** de que a propriedade sobrevive ao corte em
abas (a instrução explícita de T018/`spec.md` SC-002), reaproveitando o
mesmo padrão de abrir todo `<details>` antes de ler
(`transversal-rules.spec.ts:187-206`, já citado na Fatia 1) que
`screen-truthfulness.acceptance.spec.ts:365-402` também já usa para esta
mesma rota.

**(f) override ausente do corpo; botão do cabeçalho abre painel lateral** —
`:291`. **Correção aplicada** (ver §9.1): a primeira versão testava
`getByRole('heading', { name: 'Grant or revoke an override' })`, um texto que
um simples rename do título apaga — `not.toBeVisible()` teria passado sem que
o painel tivesse saído do corpo, o "green vacuous" que o orquestrador nomeou.
Trocado por `page.getByTestId('override-editor')` (o elemento mais externo
de `override-editor.tsx:235`), checado por visibilidade. **VERMELHO**, na
primeira das três asserções da alegação — o teste para aí, então as duas
seguintes (botão do cabeçalho, o `dialog` abrindo) não chegaram a rodar
nesta rodada:
```
Error: expect(locator).not.toBeVisible() failed
Locator:  getByTestId('override-editor')
Expected: not visible
Received: visible
14 × locator resolved to <div class="flex flex-col gap-5" data-testid="override-editor">…</div>
```
Confirma exatamente o defeito nomeado pela spec: o painel de concessão/revogação
está montado e visível no corpo da página hoje, não atrás de um botão. E,
diferente da versão anterior, continua vermelho por esse motivo mesmo que o
título do painel mude de texto — só deixa de estar visível no corpo quando o
componente realmente sair de lá (para dentro de um `Drawer` fechado, por
exemplo).

**(g) nenhum parágrafo entre o título e o primeiro controle** —
`:153`. **Correção aplicada** — documentada aqui, e não em §9.1, porque o que
mudou foi a lógica da varredura, não um testid escolhido. O orquestrador
provou, por leitura de `decisions.tsx:53-63` (a forma exata
que `TabLinks` renderiza — um `<nav data-testid="tab-links">` como IRMÃO do
`page-header`, cheio de `<a>`), que a varredura original parava no primeiro
`<a>` encontrado — e o primeiro elemento depois do cabeçalho, uma vez que as
abas existirem, será exatamente o link da própria aba. A varredura antiga
teria devolvido `null` (nenhuma violação) na primeira iteração, passando com
os três parágrafos de `autonomy-glossary` intocados, ainda sentados abaixo da
tira de abas — vermelho hoje, verde falso amanhã, o formato de defeito mais
repetido da onda. **A correção**: a varredura agora pula todo bloco de chrome
conhecido em sequência — o cabeçalho, depois (quando existir)
`[data-testid="tab-links"]` inteiro — antes de procurar por parágrafo ou
controle real (`autonomy-tabs.acceptance.spec.ts:174-198`).

**Prova da correção, feita e depois desfeita** (a instrução era explícita: uma
asserção que só rodou contra o DOM de hoje não foi testada contra o DOM para
o qual foi escrita):

1. Rodei o arquivo tal como está — resultado abaixo (VERMELHO, mesmo motivo
   de sempre).
2. Editei temporariamente o teste para injetar, via `page.evaluate`, exatamente
   antes da varredura: `<nav data-testid="tab-links"><a href="#">Posture</a></nav>`,
   inserido como irmão do `page-header` com `insertAdjacentElement('afterend', ...)`
   — simulando o DOM do dia em que as abas existirem. Rodei de novo
   (`--no-build`, já que nenhum arquivo de `console/src` mudou): a alegação
   continuou VERMELHA, com a MESMA mensagem (o mesmo parágrafo de
   `autonomy-glossary` encontrado depois do `<nav>` injetado) — prova de que a
   varredura corrigida realmente pula o `<a>` de dentro do `tab-links`
   injetado e continua até achar o parágrafo real, em vez de parar no link e
   devolver `null`.
3. Removi a injeção (restaurada a partir de uma cópia limpa em
   `scratchpad/`, nunca `git checkout`), reformatei com prettier, rodei
   `tsc`/`eslint` de novo (ambos limpos) e rodei o arquivo inteiro mais uma
   vez para confirmar que o estado final bate com o do passo 1.

Saída do passo 1/3 (arquivo final, sem a injeção — idêntica nos dois momentos):
```
Error: expect(received).toBeNull()
Received: "a paragraph sits before the first control: \"A rule decides what this
deployment may do for one scope, from the whole deployment down to a single
resource — read in \""
```
Saída do passo 2 (COM a injeção do `tab-links` falso, prova de que a
correção realmente pula chrome e não só sorte de o chrome não existir ainda):
mensagem idêntica à de cima, byte a byte — o mesmo parágrafo de
`autonomy-glossary` (`autonomy.tsx:360-367`, catálogo `autonomy.glossary.rule`,
`en.ts:1158-1159`), agora encontrado depois de pular tanto o cabeçalho quanto
o `<nav>` injetado.

**(h) nenhum CTA cujo rótulo prometa destino diferente do que abre — o
rótulo "Look at the configuration" retirado desta rota** —
`:216`. **VERMELHO**:
```
Error: "autonomy.empty.action" (the "Look at the configuration" label) is
still referenced 4 time(s) in autonomy.tsx
Expected: 0
Received: 4
```
As quatro referências são os quatro `empty={{ ..., actionLabel: message(locale,
'autonomy.empty.action'), href: X }}` de `autonomy.tsx` — a tabela de regras
(`:376-381`, `href: ruleEditorHref`), o editor de postura (`:454-459`, mesmo
`ruleEditorHref`), o painel de bounds (`:641-646`, `href: boundsEditorHref`) e
o painel de override (`:746-751`, `href: overrideEditorHref`) — o mesmo
rótulo prometendo três destinos reais distintos (`#new-rule`, `#new-freeze`,
`#override-grant`, cada um caindo em `/settings` quando não há nó/permissão).
**Por que a alegação foi testada contra o código-fonte e não só contra a
tela renderizada, registrado com honestidade**: verifiquei antes de escrever
o teste que **nenhum nó do cenário `populated` consegue exercitar esse
estado vazio pela tela** — `_policy_document()`
(`tools/mockplane/dataset/served.py:244-295`) devolve as mesmas três regras
para QUALQUER `node_id`, e `config_records()`
(`tools/mockplane/dataset/served.py:1516-1546`) devolve o mesmo freeze
(`nightly-backups`) e o mesmo budget (`hourly`) para todo nó também — então
`rulesEmpty` e `boundsEmpty` (`autonomy.tsx:281-283`) são `false` para
qualquer nó válido deste dataset, sempre, e o painel de override nem usa a
flag de vazio (`stateOf(bounds, false)` em `autonomy.tsx:740` — o segundo
argumento é `false` literal, não `overrides.length === 0`). Uma asserção só
contra a tela renderizada ("o corpo não contém 'Look at the configuration'")
passaria HOJE por acidente de fixture, não porque o defeito foi corrigido —
exatamente a armadilha "alegação já verde" que esta fatia foi instruída a
evitar. O teste inclui as duas metades: uma verificação (documentada como
tal, linhas 199-213) de que o texto realmente não aparece na tela hoje — e
que, se essa premissa deixar de valer (por exemplo se um cenário futuro
adicionar um nó com regras vazias), a mensagem de falha diz isso
explicitamente — e a prova real, contra a fonte, no mesmo padrão que
`scroll-budget.spec.ts:35-47` e `transversal-rules.spec.ts:47-59` já usam
para ler `config/constants/surfaces.py`/`shell/routes.ts` como verdade em vez
de exercitar por um controle.

**(i) um só CTA primário na seção de simulação, e nenhum rótulo concorrente
sobrevive ao lado dele** — `:327`. **Correção aplicada** (ver §9.1): a
primeira versão contava, por RÓTULO, quantos dos três botões de hoje existiam
dentro de `autonomy-editor` e exigia exatamente 1 — o orquestrador apontou
dois problemas reais, confirmados por leitura antes de corrigir: (1) o CTA
sobrevivente é livre para ganhar um rótulo novo — a seção também vai ganhar
título próprio e uma frase do que responde —, e nesse caso a contagem por
rótulo cai para 0, um falso vermelho depois da implementação já estar
correta; (2) contar por rótulo nada dizia sobre um SEGUNDO botão primário
aparecer ao lado do escolhido. A correção é duas asserções dentro do mesmo
teste, escopadas a `page.getByTestId('autonomy-simulation')` — não a
`autonomy-editor`, que também contém o botão de salvar regra
(`autonomy-editor.tsx:791`, ele mesmo sem `variant` explícito hoje, mas um
candidato real a `variant="primary"` depois; contar ali teria contado esse
botão também): (1) exatamente um `button[data-variant="primary"]` dentro da
seção; (2) zero botões cujo nome acessível bate um dos rótulos de hoje
("Explain one action" / "Simulate everything" / "Stop simulating" / "What
would this decide differently?") que NÃO sejam o próprio primário — o
primário é livre para manter um desses rótulos, só não pode ter um irmão com
o mesmo.

`autonomy-simulation` não existe ainda, então o teste já para na primeira das
duas asserções — **VERMELHO**, pelo motivo certo (a seção não existe), não
por uma contagem de rótulo que a implementação poderia contornar sem
convergir nada:
```
Error: expect(locator).toBeVisible() failed
Locator: getByTestId('autonomy-simulation')
Expected: visible
Timeout: 5000ms
Error: element(s) not found
```
As duas asserções internas (contagem de primários, zero sobreviventes por
rótulo) ainda não chegaram a rodar — só rodam a partir do dia em que a seção
existir, e é nesse dia que elas passam a valer a pena: contam de verdade,
não confirmam por acidente. Isso é o contrato que esta correção entrega à
implementação, nomeado (`autonomy-simulation`) em vez de deixado para
adivinhar depois.

### 9.3 O que cada vermelho prova, e o que ainda não prova

Todo `expect` acima falhou pela razão que a alegação descreve — nenhum erro
de sintaxe de locator, nenhum timeout por rota fora do ar, nenhum "elemento
não encontrado" por eu ter escrito o testid errado. Os testids usados hoje
que já existem no código atual (`page-header`, `effective-field`,
`override-editor`) resolveram normalmente; os que ainda não existem
(`tab-links`, `tab-link`, `autonomy-simulation`) deram "elemento não
encontrado", que é o vermelho correto para uma aba e uma seção que ainda não
existem. T039 (fase de fechamento, fora desta fatia) é quem vai rodar este
mesmo arquivo depois da implementação e comparar alegação a alegação com
este vermelho.

**A lição da rodada de correção, registrada sem meias palavras**: as
primeiras versões de (f), (g) e (i) já estavam vermelhas hoje — passavam no
teste mais fácil de checar (rodar e ver falhar) — mas cada uma ia ficar
VERDE por acidente assim que a implementação chegasse perto de estar
correta, sem provar que o defeito real tinha sumido: (f) por um rename de
texto, (g) porque o primeiro `<a>` de uma tira de abas real ia interromper a
varredura antes de qualquer parágrafo, e (i) por um rótulo novo no CTA
sobrevivente. As três foram encontradas por revisão externa, não por mim —
"vermelho hoje" não é a mesma prova que "vermelho pelo motivo certo, e verde
só quando o motivo some", e é essa segunda prova que as três reescritas
buscam entregar.

## 10. Gates rodados nesta fatia

| Gate | Comando | Resultado |
|---|---|---|
| Constantes (Python) | `uv run python -m tools.check_constants config/constants/surfaces.py config/constants/__init__.py` | exit 0 |
| Lint Python | `uv run ruff check config/constants/surfaces.py config/constants/__init__.py` | All checks passed! |
| Formato Python | `uv run ruff format --check config/constants/surfaces.py config/constants/__init__.py` | 2 files already formatted |
| Tipos Python | `uv run mypy config/constants/surfaces.py config/constants/__init__.py` | Success: no issues found in 2 source files |
| Importação sanidade | `uv run python -c "from config.constants import CONFIG_SCREEN_TAB_SCROLL_BUDGET_VIEWPORTS; from config.constants.surfaces import CONFIG_SCREEN_TAB_SCROLL_BUDGET_VIEWPORTS as direct; print(...)"` | `1.5 1.5` |
| Prettier (TS) | `pnpm exec prettier --check tests/e2e/autonomy-tabs.acceptance.spec.ts` (de `console/`) | All matched files use Prettier code style! |
| Typecheck (TS) | `pnpm exec tsc --noEmit` (de `console/`, projeto inteiro — o arquivo novo está sob `**/*.ts` do `tsconfig.json`) | exit 0, nenhuma saída |
| Lint (TS/ESLint, type-aware) | `pnpm exec eslint tests/e2e/autonomy-tabs.acceptance.spec.ts` (de `console/`) | exit 0, nenhum problema |
| Acceptance (Playwright, `populated`) | `uv run python -m tools.spec_validation browser --feature specs_v6/040-autonomy-tres-abas --test console/tests/e2e/autonomy-tabs.acceptance.spec.ts` | `Running 9 tests using 1 worker` — 8 failed, 1 passed (31.9s), versão final — ver §9.2. Rodado 4 vezes ao todo nesta fatia (antes da correção, depois da correção, com a injeção de prova de (g) via `--no-build`, e a versão final restaurada); todas concordam em 8/1. |

**Um achado do lint que vale registrar**: `@typescript-eslint/no-unnecessary-condition`
recusou `(el.textContent ?? '').trim()` dentro do `page.evaluate` de (g),
dizendo que o `??` era desnecessário. Confirmei com `tsc --noEmit` que o
compilador, neste ponto exato do fluxo (depois de `if (el === undefined)
continue`), já enxerga `el.textContent` como não-nulo — removi o fallback
(`autonomy-tabs.acceptance.spec.ts:205`, `el.textContent.trim()`) e os dois
gates ficaram verdes. Não investiguei a fundo por que `Node.textContent`
(`string | null` no `lib.dom.d.ts` deste projeto, confirmado por leitura
direta do arquivo) se estreita para não-nulo aqui — só confirmei
empiricamente, com o próprio compilador, que a remoção é segura antes de
aplicá-la.

**Não rodado, e por quê**: `console_gate typecheck`/`lint`/`test` completos
(rodei `tsc --noEmit` e `eslint` diretamente sobre o projeto/arquivo, que é o
que esses alvos do gate fazem por baixo; não há evidência de que rodar o
wrapper `tools.console_gate` mudaria o resultado, e o arquivo tocado é um só).
`make verify`, `console-visual-accept`, `console-e2e` completo — fora do
escopo desta fatia por instrução explícita. Nenhum teste Python de domínio
(`tests/contract`, `tests/unit`) foi tocado ou precisou rodar — as duas
mudanças em `config/constants/` são estritamente aditivas (uma constante
nova, referenciada em lugar nenhum ainda) e os gates de constantes/lint/tipos
acima já cobrem sua correção.

## 11. O que fica pendente, nomeado, não escondido — Fatia 2

- **Toda a implementação além do acceptance**: T004 a T045. Em particular,
  T004/T005 (`autonomy-tabs.ts`) precisam adotar os identificadores de aba
  que este acceptance escolheu (`posture`, `rules-windows`, `guardrails`) —
  ou, se uma fatia futura escolher outros, este arquivo de teste precisa ser
  atualizado nesse mesmo commit, não depois.
- **A alegação (h) só está provada contra o código-fonte, não contra a tela
  renderizada** — nomeado e justificado em §9.2. Se um cenário futuro do
  `mockplane` passar a servir um nó com `rules`/`freezes`/`budgets` vazios
  para esta rota, a metade da asserção que lê o corpo da página
  (`autonomy-tabs.acceptance.spec.ts:228-234`) passa a ser a prova real, e a
  leitura de código-fonte pode ser removida — não fiz essa mudança de
  fixture aqui porque estava fora do escopo das três tarefas desta fatia.
- **Os dois sites de `Badge` com nível cru** (`autonomy.tsx:423`, `:710`,
  `override-editor.tsx:340`), nomeados na Fatia 1 §4 — continuam
  investigados e não corrigidos, sem dono atribuído nesta fatia também.
- **A ambiguidade de leitura do SC-008** (Fatia 1 §3.3) — continua não
  resolvida; T040 é quem decide.

## 12. Arquivos alterados — Fatia 2

- `config/constants/surfaces.py` — a constante `CONFIG_SCREEN_TAB_SCROLL_BUDGET_VIEWPORTS`
  e sua entrada em `__all__`.
- `config/constants/__init__.py` — o mesmo nome, re-exportado no mesmo padrão
  de toda outra constante de `surfaces.py`.
- `console/tests/e2e/autonomy-tabs.acceptance.spec.ts` — novo, 372 linhas
  (depois da correção de (f)/(g)/(i) pedida pelo orquestrador — ver §9.1/§9.2),
  nove testes.
- `specs_v6/040-autonomy-tres-abas/tasks.md` — caixas de T001, T002 e T003
  marcadas.
- `specs_v6/040-autonomy-tres-abas/controle.md` — esta seção, acrescentada.

Nenhum outro arquivo foi tocado. `console/src/surfaces/settings/autonomy.tsx`
foi lido extensivamente para embasar as asserções acima, mas não foi
editado.

---

# Fatia 3 — os dois módulos de fundação: `autonomy-tabs.ts` e `guardrail-values.ts`

**Escopo desta fatia**: exatamente quatro tarefas — T004, T005, T006, T007 —
a Fase 2 (Foundational) de `tasks.md`. Dois módulos TypeScript puros e os
testes de unidade que os provam, nada além disso. `console/src/surfaces/settings/autonomy.tsx`
**não foi tocado** — confirmado por `git status --porcelain` ao final da
fatia, que só lista `console/src/i18n/en.ts` e `console/src/i18n/pt-BR.ts`
como modificados e os quatro arquivos novos abaixo como não rastreados.
Nenhuma tela, nenhuma captura visual, nenhum teste Playwright novo. As
Fatias 1 (`779d834`) e 2 (`a35bc83`) já estavam commitadas no branch quando
esta fatia começou — confirmado por `git log --oneline`. Nada foi commitado,
staged, nem passou por `git add` nesta sessão.

## 13. Tabela de estado — Fatia 3

| Peça | Estado | Detalhe |
|---|---|---|
| T004 — teste (vitest) de `autonomy-tabs.ts` | **FEITO** | `console/tests/unit/surfaces/settings/autonomy-tabs.test.ts`, 18 testes, todos vermelhos na primeira rodada (`Failed to resolve import "@/surfaces/settings/autonomy-tabs"... Does the file exist?`) e todos verdes depois de T005. Ver §14. |
| T005 — implementar `autonomy-tabs.ts` | **FEITO** | `console/src/surfaces/settings/autonomy-tabs.ts` (134 linhas): `AUTONOMY_TABS`, `tabFrom`, `tabLabel`, `AUTONOMY_TAB_FILTERS`, `hrefForTab`, `AUTONOMY_TAB_FIELDS` (17 entradas) e `tabOwning`. Ver §15 para a alocação completa e a razão de cada caso não óbvio. |
| T006 — teste (vitest) de `guardrail-values.ts` | **FEITO** | `console/tests/unit/surfaces/settings/guardrail-values.test.ts`, 8 testes, todos vermelhos na primeira rodada (mesmo motivo — módulo inexistente) e todos verdes depois de T007. Ver §14. |
| T007 — implementar `guardrail-values.ts` | **FEITO** | `console/src/surfaces/settings/guardrail-values.ts` (87 linhas): `GUARDRAIL_FIELDS` (os seis escalares de guardrail) e `guardrailRows`, que delega a `effectiveRows` (`surfaces/effective-fields.ts`, já da 020) em vez de reimplementar a regra. Ver §16. |

## 14. Vermelho confirmado, depois verde — os dois arquivos

Comando (de `console/`), rodada 1, **antes** de qualquer um dos dois módulos
existir:

```
pnpm exec vitest run tests/unit/surfaces/settings/autonomy-tabs.test.ts tests/unit/surfaces/settings/guardrail-values.test.ts --pool=forks
```

Saída real — **2 suítes falharam, 0 testes coletados** (o vermelho correto
para um módulo ausente: nenhum teste chega a rodar, porque o import nem
resolve):

```
FAIL  tests/unit/surfaces/settings/autonomy-tabs.test.ts [ tests/unit/surfaces/settings/autonomy-tabs.test.ts ]
Error: Failed to resolve import "@/surfaces/settings/autonomy-tabs" from "tests/unit/surfaces/settings/autonomy-tabs.test.ts". Does the file exist?

FAIL  tests/unit/surfaces/settings/guardrail-values.test.ts [ tests/unit/surfaces/settings/guardrail-values.test.ts ]
Error: Failed to resolve import "@/surfaces/settings/guardrail-values" from "tests/unit/surfaces/settings/guardrail-values.test.ts". Does the file exist?

Test Files  2 failed (2)
     Tests  no tests
```

Depois de escrever os dois módulos (T005, T007), mesmo comando, mesma
rodada de testes, sem alterar um único `expect`:

```
Test Files  2 passed (2)
     Tests  26 passed (26)
```

18 testes em `autonomy-tabs.test.ts`, 8 em `guardrail-values.test.ts`.
Nenhuma asserção foi afrouxada entre o vermelho e o verde — o vermelho da
rodada 1 é "módulo não existe", o verde é "módulo existe e faz o que o
teste pede", não duas versões diferentes do mesmo teste.

**Honestidade sobre o que passou de primeira**: nenhuma asserção individual
passou "sem querer" contra um código que já existia — os dois módulos são
inteiramente novos nesta fatia, então não havia nada para "já valer" antes
de T005/T007. A ressalva do pré-flight sobre asserção estreita foi aplicada
mesmo assim, ver §14.1.

### 14.1 Onde a armadilha da asserção estreita foi checada deliberadamente

- `tabOwning('policies.nonexistent.field')` retorna `undefined`, não
  `'posture'` nem uma exceção — testado explicitamente
  (`autonomy-tabs.test.ts:132-135`) porque a alternativa óbvia (um `.find()`
  com fallback para a primeira aba, do mesmo jeito que `tabFrom` faz) teria
  tornado "campo órfão" indetectável por construção — exatamente o
  contrário do que T025 (fatia futura) precisa poder provar.
- O teste de `hrefForTab` que verifica ausência de nó
  (`autonomy-tabs.test.ts:89-94`) não checa só `toContain('tab=posture')`
  — ele também afirma `not.toContain('node=')`, para que a implementação
  não pudesse satisfazer o teste escrevendo `node=` vazio (`?node=&tab=posture`),
  o que teria sido tecnicamente "sem nó" só na leitura humana, não na string.
- `guardrailRows` foi testado com um catálogo **parcial** (faltando
  `policies.guardrails.ruleset`), não só com um catálogo vazio ou um
  catálogo completo — para provar que "ausente" é decidido por campo, não
  por chamada inteira (`guardrail-values.test.ts`, "marks one missing
  guardrail as not set while the rest of the table still resolves").
  Um teste só com catálogo vazio teria passado mesmo se a implementação
  quebrasse ao misturar campos presentes e ausentes na mesma chamada.
- O teste de origem (`guardrail-values.test.ts`, "keeps the origin a
  separate sentence from the value, in both directions") verifica os dois
  sentidos — um campo definido neste nó (`origin` = o nome do nó) e um
  herdado (`origin` = a frase de default) — e afirma `value !== origin` nos
  dois casos, não só que ambos são não vazios. A letra da tarefa era
  "a origem é texto separado do valor", que é uma afirmação sobre os dois
  serem *diferentes*, não só sobre nenhum ser vazio.

## 15. O mapa campo → aba (`AUTONOMY_TAB_FIELDS`) — a alocação completa e a razão de cada caso

Os 17 caminhos vêm de `console/src/shell/config-ownership.ts:95-123`
(`CONFIG_FIELD_OWNERS`, page `settings-autonomy-guardrails`), lidos
diretamente da fonte antes de escrever qualquer linha do mapa. Meu módulo
**não importa** `config-ownership.ts` — decisão deliberada, ver §15.4.

### 15.1 Posture (1 campo)

| Campo | Razão |
|---|---|
| `policies.autonomy.overrides` | O caso difícil, nomeado explicitamente pela instrução desta fatia. Um override é alcançável de forma idêntica a partir do cabeçalho de **qualquer** uma das três abas (User Story 6) — não mora dentro do corpo de nenhuma aba especificamente, então "qual aba possui este campo" não tem resposta por leitura de onde o JSX vai ficar, só por decisão. Escolhi Posture por eliminação e por afinidade temática: (1) Rules & windows responde "quando o deployment não pode agir sozinho" — um override é o oposto disso, uma elevação manual, não uma regra, congelamento ou teto; (2) Guardrails responde "o que sempre vale" — um override é definido por ser temporário, o oposto de "sempre"; (3) Posture responde "o que o deployment pode fazer sozinho", e um override **é exatamente** uma elevação temporária dessa mesma pergunta; (4) o subtítulo da tela (FR-045, "com override ativo, o subtítulo mostra a postura que vigora e declara que vem de um override com prazo") é a superfície que comunica o *efeito* do override, e esse subtítulo é conceitualmente parte da história que a aba Posture conta. |

### 15.2 Rules & windows (7 campos)

| Campo | Razão |
|---|---|
| `policies.autonomy.rules` | Nomeado explicitamente pela instrução ("rules/freezes/budgets/dry_run to rules-windows"). As regras propriamente ditas. |
| `policies.autonomy.freezes` | Idem — as janelas de congelamento, o "windows" do nome da aba. |
| `policies.autonomy.budgets` | Idem — os tetos de gasto. |
| `policies.autonomy.dry_run` | Idem — a chave de simulação, que a User Story 5 (seção de simulação desta mesma aba) governa. |
| `policies.autonomy.allow_unverifiable_actions` | Não nomeado explicitamente pela instrução — decidido por mim. Hoje vive em `AUTONOMY_ADVANCED_FIELD_LIST` (`autonomy.tsx:181-203`), o mesmo prefixo `policies.autonomy.` dos quatro campos acima, renderizado na mesma coluna da tela, logo abaixo do editor de regras. Semanticamente é uma restrição de **quando** uma regra pode decidir agir sozinha (se a ação não for verificável, não decide) — a mesma pergunta que "Rules & windows" responde ("quando ele não pode"), não uma pergunta sobre guardrails (que não dependem de regra alguma) nem sobre a postura em si. |
| `policies.autonomy.recurrence_threshold` | Não nomeado explicitamente — mesma razão do item acima: mesmo prefixo, mesmo bloco hoje, e é um freio sobre repetição de decisões de regra — quando uma ação repetida deixa de poder ser decidida sozinha. |
| `policies.autonomy.recurrence_window_seconds` | Idem — o "window" aqui é literal (uma janela de tempo para contar repetição), reforçando (não decidindo sozinho) o encaixe temático com o nome da aba. |

### 15.3 Guardrails (9 campos)

Nomeados em bloco pela instrução ("policies.guardrails.\* e policies.masking.\*
e policies.approvals.\* to guardrails"):

`policies.guardrails.disabled_rules`, `policies.guardrails.mode`,
`policies.guardrails.ruleset`, `policies.masking.custom_patterns`,
`policies.masking.enabled`, `policies.masking.level`,
`policies.approvals.autonomous_capabilities`,
`policies.approvals.expiry_hours`, `policies.approvals.threshold`.

Nenhum caso ambíguo aqui — os três prefixos mapeiam 1:1 para a pergunta
"o que sempre vale", nenhum deles é condicional a uma regra de autonomia.

### 15.4 Uma decisão que não é sobre o mapa, mas afeta como lê-lo: por que "posture level" não é um campo do mapa

A instrução mencionava "a postura em si" (posture level) como pertencendo à
aba Posture. Não existe, em `CONFIG_FIELD_OWNERS`, nenhum caminho como
`policies.autonomy.level` — a postura vigente é derivada de
`policies.autonomy.rules` (especificamente a regra de escopo `deployment`,
`FIRST_RULE` em `autonomy.tsx:92-103`), não um campo escalar próprio. Como
`rules` já está atribuído a `rules-windows` (item explícito da instrução),
não criei uma segunda entrada para "posture level" — não existe caminho de
schema correspondente a criar.

**Consequência nomeada, não escondida**: o futuro controle "seletor de
nível + salvar" da aba Posture (FR-013/FR-014, T014, fora desta fatia) vai
precisar gravar exatamente nessa mesma entrada de `rules` (a regra de
escopo `deployment`) que este mapa atribui inteiramente a Rules & windows.
Isso não é um defeito do mapa — a granularidade do mapa é por **caminho**,
não por entrada de array, e o mesmo padrão já existe hoje de forma sancionada:
a aba Posture vai mostrar um resumo somente-leitura dos guardrails
(FR-019/FR-020) sem ser dona deles. A diferença é que o controle de postura
da aba Posture não vai ser somente-leitura — vai *escrever* numa fatia do
mesmo campo que Rules & windows possui. Registro isso para quem construir
T014/T019: uma opção é a gravação de Posture ser uma operação
deliberadamente restrita à entrada de escopo `deployment` (não o editor
genérico de `rules`), o que a torna uma segunda *operação de escrita*, não
uma segunda leitura acidental do mesmo controle.

### 15.5 Por que `config-ownership.ts` não foi importado no teste

`AUTONOMY_TAB_FIELDS` foi conferido campo a campo por leitura direta de
`config-ownership.ts:95-123` antes de escrever o mapa, e o teste
`'claims exactly the seventeen paths...'` (`autonomy-tabs.test.ts:172-197`)
fixa essa lista à mão, com um comentário explícito dizendo que o
cross-check programático contra `config-ownership.ts` — capaz de falhar
**nomeando o campo**, que é a letra de FR-047 — é T025, não esta fatia. Não
importei `config-ownership.ts` no teste porque a instrução desta fatia é
explícita ("T025 (a later slice) tests that property, but you build the map
now, so build it so that test can be written") — antecipar essa asserção
aqui arriscaria duas versões divergentes do mesmo contrato em dois commits
diferentes. `tabOwning` já devolve `undefined` para um caminho não
reivindicado (não um valor-padrão), que é exatamente a propriedade que uma
futura verificação por nome precisa de mim para poder ser escrita.

## 16. `guardrail-values.ts` — o que o resolvedor faz, e o que ele delega

`guardrailRows(catalogue, locale)` **não reimplementa** a regra de valor
efetivo / origem — delega a `effectiveRows` (`surfaces/effective-fields.ts:63`,
já entregue pela 020), que já garante, estruturalmente, "override quando
gravado, default do schema quando não", e um marcador explícito de
"Not set" nunca uma string vazia. `EffectiveFieldsTable`
(`design/resolution-preview.tsx:286-304`) lança exceção se qualquer linha
chegar com `value`/`origin` em branco — a mesma trava que a Fatia 1 já
tinha registrado como o motivo estrutural de SC-002 estar em zero hoje.

O que este módulo adiciona, que `effectiveRows` sozinho não tem: **os seis
caminhos que são "guardrail" nesta tela, como dado, num único lugar**, para
que a leitura resumida de Posture (T017) e a tabela editável de Guardrails
(T019) leiam do mesmo array em vez de cada uma manter sua própria cópia —
exatamente a duplicação que o `plan.md` nomeia como o risco a evitar
("duas aparições, uma fonte de verdade").

**Os seis campos, e por que não são nove**: `GUARDRAIL_FIELDS` cobre só os
seis escalares (`masking.enabled`, `masking.level`, `guardrails.mode`,
`guardrails.ruleset`, `approvals.threshold`, `approvals.expiry_hours`) —
não os três campos-array do mesmo grupo (`masking.custom_patterns`,
`guardrails.disabled_rules`, `approvals.autonomous_capabilities`), que o
mapa de T005 também atribui à aba Guardrails, mas por outro controle. Isso
**preserva uma decisão que já existe** em `autonomy.tsx` hoje — o comentário
de `GUARDRAIL_FIELD_LIST` (`autonomy.tsx:136-142`) já diz que os campos-array
"são deixados fora deste resumo e continuam totalmente editáveis abaixo,
através do `ConfigEditor`" — porque o "valor efetivo" de uma lista seria o
próprio JSON despejado, não uma frase que alguém lê como estado de um
guardrail. Não é uma decisão nova desta fatia, é a mesma já tomada,
replicada no módulo novo porque `autonomy.tsx` não foi tocado.

**Duplicação temporária, nomeada**: `autonomy.tsx:143-172` ainda declara sua
própria cópia inline de `GUARDRAIL_FIELD_LIST`, com os mesmos seis caminhos
e as mesmas chaves de rótulo que `GUARDRAIL_FIELDS` agora também declara.
As duas listas **concordam** hoje (conferido campo a campo) mas são,
literalmente, duas declarações do mesmo dado até que T019 troque
`autonomy.tsx` para importar de `guardrail-values.ts` e apague a cópia
antiga — exatamente o "duas cópias da mesma regra" que o `plan.md` avisa
ser o ponto onde elas divergem. Registrado aqui para que T017/T019 não
percam de vista que a substituição, não só a adição, é parte do trabalho.

## 17. Comandos rodados, com resultado real

```
$ pnpm exec vitest run tests/unit/surfaces/settings/autonomy-tabs.test.ts tests/unit/surfaces/settings/guardrail-values.test.ts --pool=forks
Test Files  2 passed (2)
     Tests  26 passed (26)
```

Rodada rápida (`--pool=forks`), usada como loop interno — **não** aplica os
limiares de cobertura, conforme a nota explícita da instrução desta fatia
(confirmada contra `console/vitest.config.ts:33-44`: os limiares só entram
via `vitest run --coverage`, o alvo real do gate). O resultado que prova o
piso de cobertura é o próximo.

```
$ uv run python -m tools.console_gate test
$ vitest run --coverage
 Test Files  145 passed (145)
      Tests  2402 passed (2402)
 Statements   : 94.37% ( 6221/6592 )
 Branches     : 90.42% ( 4609/5097 )
 Functions    : 92.06% ( 1927/2093 )
 Lines        : 96.39% ( 5746/5961 )
```

`exit 0`, confirmado separadamente com `echo $?`. Suíte inteira do console (145 arquivos, incluindo os dois novos), piso de
90% respeitado nas quatro métricas — `Branches` é a mais próxima do piso
(90.42%), mas ainda verde; não investiguei se meus dois módulos
contribuíram para puxar essa métrica para cima ou para baixo, porque os
dois são majoritariamente dados (arrays de objetos) com poucos ramos de
verdade (`tabFrom`'s fallback, `hrefForTab`'s dois ternários, `tabOwning`'s
`?? undefined`), e todos os ramos de ambos os módulos são exercitados pelos
26 testes escritos (confirmado por leitura dos próprios testes, não por uma
ferramenta de cobertura por arquivo separada).

```
$ uv run python -m tools.console_gate typecheck
$ tsc --noEmit
```
exit 0, nenhuma saída (sucesso silencioso).

```
$ uv run python -m tools.console_gate lint
$ eslint . && node scripts/check-css-literals.mjs
```
exit 0, nenhuma saída.

```
$ pnpm exec prettier --check src/surfaces/settings/autonomy-tabs.ts src/surfaces/settings/guardrail-values.ts tests/unit/surfaces/settings/autonomy-tabs.test.ts tests/unit/surfaces/settings/guardrail-values.test.ts src/i18n/en.ts src/i18n/pt-BR.ts
```
Primeira rodada: 1 arquivo com formatação incorreta
(`tests/unit/surfaces/settings/autonomy-tabs.test.ts`) — corrigido com
`prettier --write` (reformatação automática de quebra de linha em duas
chamadas de `expect(...).toContain(...)` longas, nenhuma mudança de
comportamento). Segunda rodada, depois da correção: `All matched files use
Prettier code style!`.

```
$ pnpm exec eslint tests/unit/surfaces/settings/autonomy-tabs.test.ts tests/unit/surfaces/settings/guardrail-values.test.ts src/surfaces/settings/autonomy-tabs.ts src/surfaces/settings/guardrail-values.ts
```
exit 0, depois da correção do prettier acima (rodado de novo para
confirmar que a reformatação não introduziu problema de lint).

```
$ pnpm exec vitest run tests/unit/i18n/catalogue.test.ts --pool=forks
Test Files  1 passed (1)
     Tests  11 passed (11)
```
Rodado à parte para confirmar, isoladamente, que as três chaves novas
(`autonomy.tab.posture`, `autonomy.tab.rules-windows`,
`autonomy.tab.guardrails`) não quebraram a paridade dos catálogos — o teste
"carries every key in every locale, and names any that is missing" já
cobre isso, e já tinha passado dentro dos 2402 da rodada de cobertura
acima; esta é só a confirmação isolada, com o nome do teste citado.

**Não rodado, e por quê**: `make verify`, `console-visual-accept`,
`console-e2e` completo — fora do escopo desta fatia por instrução explícita
(o orquestrador é dono do `make verify`; nenhuma baseline visual foi
capturada, aceita ou sobrescrita). Nenhum teste Python (`pytest`,
`tests/contract`) foi tocado ou precisou rodar — as duas mudanças em
`console/src/i18n/*.ts` são estritamente aditivas (três chaves novas, cada
uma com par en/pt-BR) e não tocam `config/constants/`, então nenhum guard
Python (`check-constants`, `check-imports`, `check-console-boundary`) tem
superfície nova para verificar. Nenhum Playwright novo — o acceptance da
feature (`autonomy-tabs.acceptance.spec.ts`) já está escrito e vermelho
desde a Fatia 2 e continua vermelho (não rodado de novo nesta fatia,
porque nenhuma tela mudou — rodá-lo de novo não mudaria seu resultado e a
instrução desta fatia não pede essa confirmação).

## 18. O que fica pendente, nomeado, não escondido — Fatia 3

- **Toda a implementação de tela**: T008 a T045. Em particular:
  - T009 vai precisar reconciliar `AUTONOMY_TAB_FILTERS` (`['node', 'tab']`,
    este módulo) com `AUTONOMY_FILTERS` (`['node']`, ainda hoje em
    `autonomy.tsx`, não tocado) — os dois nomes coexistem sem colisão
    porque vivem em módulos diferentes, mas T010 é quem decide como
    `autonomy.tsx` passa a declarar `'tab'` entre os filtros que lê.
  - T009 também vai precisar de uma chave `autonomy.tabs` (o `aria-label`
    do `<nav>` da tira de abas, no mesmo padrão de `decisions.tabs`/
    `agent.tabs`/`knowledge.tabs`) — **não criada nesta fatia**, porque
    nenhuma das duas tarefas desta fatia consome essa chave; só as três
    chaves `autonomy.tab.<id>` (os rótulos de cada aba) foram criadas, que
    é o que `tabLabel` de fato usa.
  - T019 precisa **substituir**, não só complementar, a cópia inline de
    `GUARDRAIL_FIELD_LIST` em `autonomy.tsx` pela importação de
    `guardrail-values.ts` — ver §16, a duplicação temporária nomeada ali.
  - T014 precisa decidir como o controle de postura da aba Posture escreve
    numa fatia de `policies.autonomy.rules` sem se tornar uma segunda
    reivindicação de posse sobre um campo que este mapa atribui inteiro a
    Rules & windows — ver §15.4.
- **A alocação campo → aba não foi cross-checada por código contra
  `config-ownership.ts`** — decisão deliberada (§15.5), T025 é quem faz
  essa prova.
- **Os três sites de `Badge` com nível cru** (Fatia 1 §4) e **a
  ambiguidade de leitura do SC-008** (Fatia 1 §3.3) — seguem sem dono
  nesta fatia também, nomeados de novo para não se perderem entre fatias.

## 19. Arquivos alterados — Fatia 3

- `console/src/surfaces/settings/autonomy-tabs.ts` — novo. `AUTONOMY_TABS`,
  `AutonomyTab`, `AUTONOMY_TAB_FILTERS`, `tabFrom`, `tabLabel`,
  `hrefForTab`, `AutonomyTabField`, `AUTONOMY_TAB_FIELDS`, `tabOwning`.
- `console/src/surfaces/settings/guardrail-values.ts` — novo.
  `GuardrailFieldSpec`, `GUARDRAIL_FIELDS`, `guardrailRows`.
- `console/tests/unit/surfaces/settings/autonomy-tabs.test.ts` — novo, 18
  testes.
- `console/tests/unit/surfaces/settings/guardrail-values.test.ts` — novo, 8
  testes.
- `console/src/i18n/en.ts` — três chaves novas (`autonomy.tab.posture`,
  `autonomy.tab.rules-windows`, `autonomy.tab.guardrails`).
- `console/src/i18n/pt-BR.ts` — as mesmas três chaves, traduzidas
  ("Postura", "Regras e janelas", "Guardrails" — a última mantida em
  inglês, no mesmo padrão já em vigor nesta mesma tela para
  `settings.autonomy.guardrails.title` e para o próprio nome da página,
  `settings.page.autonomyGuardrails`, ambos "Guardrails"/"Autonomy &
  guardrails" sem tradução também em pt-BR).
- `specs_v6/040-autonomy-tres-abas/tasks.md` — caixas de T004, T005, T006 e
  T007 marcadas.
- `specs_v6/040-autonomy-tres-abas/controle.md` — esta seção, acrescentada.

Nenhum outro arquivo foi tocado. `console/src/surfaces/settings/autonomy.tsx`
não foi aberto para edição nesta fatia (foi lido, extensivamente, nas
fatias anteriores e de novo nesta para confirmar a forma de
`GUARDRAIL_FIELD_LIST`/`AUTONOMY_ADVANCED_FIELD_LIST` citada em §16, mas
nenhuma escrita ocorreu — confirmado por `git status --porcelain`, que não
lista o arquivo).

---

# Fatia 4 — o corte estrutural em três abas (T008–T011)

**Status desta seção: escrita sob interrupção deliberada do orquestrador**, a
meio de uma tarefa de medição que não chegou a rodar. Tudo abaixo é o que a
árvore de trabalho prova agora, não intenção. Branch
`feat/v6-scope-and-settings`, em cima das Fatias 1–3 já commitadas
(`779d834`, `a35bc83`, `a9aff13`). Nada foi commitado, staged, nem passou por
`git add` nesta sessão.

**Escopo desta fatia**: T008, T009, T010, T011 — Fase 3 / User Story 1. Não
foram tocados: T012 em diante (seletor de postura, remoção dos parágrafos,
CTA, resumo de guardrails em Posture pelo resolvedor de T007, edição inline,
convergência da simulação, painel lateral do override) — confirmado abaixo,
por achado, onde algum deles roça esta fatia.

## 20. Tabela de estado

| Peça | Estado | Detalhe |
|---|---|---|
| T008 — teste de tela das três abas | **FEITO** | `console/tests/unit/surfaces/settings/autonomy.test.tsx`, describe `'the three tabs, addressable and marked'` (inserido logo após `emptyPanels()`, antes do primeiro describe pré-existente). Vermelho genuíno confirmado contra a tela pré-abas (§21), verde contra a tela final (§22). Ver §20.1 para o que a asserção prova exatamente. |
| T009 — reorganização em três abas | **PARCIAL** | `console/src/surfaces/settings/autonomy.tsx`, reescrito por inteiro. A mecânica da aba (três branches `tab === 'x' ? … : null`, `TabLinks` como irmã direta do cabeçalho, filtros, hrefs) está pronta e verificada. **Mas**: o próprio texto de T009 em `tasks.md` diz "postura **e resumo de guardrails** em Posture" — e a aba Posture desta fatia não tem nenhum resumo de guardrails, só o `OverrideEditor`. Achado, não resolvido, registrado em detalhe no §23.1 — não marquei a caixa de T009 em `tasks.md` por causa disso. |
| T010 — parâmetro de aba entre os filtros | **FEITO** | `autonomy.tsx` não declara mais `AUTONOMY_FILTERS` — foi apagado. `readViewState(search, AUTONOMY_TAB_FILTERS)` (`AUTONOMY_TAB_FILTERS = ['node', 'tab']`, de `autonomy-tabs.ts`, já existia desde a Fatia 3). `hrefForTab(state, tab, nodeId)` grava o nó resolvido em todo link de aba — observado ao vivo no HTML renderizado durante `console_gate test` (`href="?node=org-northwind&tab=posture"` etc.) e provado pelas asserções de `href` do teste de T008. Ver §23.2 para quem importava `AUTONOMY_FILTERS` antes de eu apagá-lo. |
| T011 — orçamento por aba em `scroll-budget.spec.ts` | **FEITO, rodado contra build real, verde nas três abas** | `console/tests/e2e/scroll-budget.spec.ts`: `/autonomy` saiu do array `SCREENS` (medição de página inteira); um novo laço mede `/settings/autonomy-guardrails?tab=posture\|rules-windows\|guardrails` contra `CONFIG_SCREEN_TAB_SCROLL_BUDGET_VIEWPORTS` (1.5, já declarada desde a Fatia 2), lida pelo mesmo helper `constant()` que já existia no arquivo. Rodado de verdade (§22) depois que eu descobri e corrigi um build stale (§21.1) — as três asserções passaram. **A altura exata em pixels de cada aba não foi medida** — diga-se com todas as letras: o script descartável que mediria os números reais (`_scratch-slice4-measure.spec.ts`) foi criado e **não chegou a rodar** antes da interrupção. Ver §24.1. |

### 20.1 O que a asserção de T008 prova, exatamente

Três coisas, na mesma `it()`:
1. `screen.getAllByTestId('tab-link')` tem comprimento 3, e o texto de cada
   um, na ordem, é `'Posture'`, `'Rules & windows'`, `'Guardrails'`.
2. Cada um é uma tag `A` (`link.tagName === 'A'`) — não um botão. Isso é o
   que FR-003 pede: histórico do navegador real, não estado de cliente.
3. `href` de cada um contém `tab=<id>` (via `stringContaining`, não
   igualdade exata, porque `hrefForTab` também escreve `node=` quando o nó
   resolve — ver T010 acima); a aba pedida no render (`guardrails`, neste
   teste) carrega `aria-current="page"`, as outras duas não carregam o
   atributo (`not.toHaveAttribute`, não `toHaveAttribute(..., 'false')` —
   `TabLinks` escreve `aria-current={... : undefined}`, então o atributo
   fica ausente, não `"false"`).

## 21. O build stale — achado, e como percebi

Depois de escrever o código e ver os testes unitários passarem, rodei
`uv run python -m tools.console_e2e run --backing mock --scenario populated -- tests/e2e/scroll-budget.spec.ts tests/e2e/transversal-rules.spec.ts tests/e2e/autonomy-tabs.acceptance.spec.ts`
sem antes rodar um build novo. Resultado: **11 failed, 33 passed, 7 skipped**
— e as três alturas de aba vieram **todas em 2065px**, o número exato da
página inteira de antes das abas (Fatia 1, §3.1). A falha (a) do acceptance
("three tabs are present") dizia `tab-link` resolvendo a **0 elementos** — a
tira de abas nem existia no HTML servido.

### 21.1 A causa, confirmada por leitura de `tools/console_e2e.py`

`console()` (`tools/console_e2e.py:212-230`) só faz `subprocess.Popen` sobre
`console_root() / ".next" / "standalone" / "server.js"` — se o arquivo
existe, ele sobe esse binário como está; a função **não reconstrói nada**.
`"✓ Ready in 0ms"` no log era exatamente esse sintoma: não houve
compilação, só `next start` sobre um `.next` já parado no tempo — o build
commitado desde a Fatia 3 (`a9aff13`), que tinha `autonomy-tabs.ts` e
`guardrail-values.ts` mas não tocava `autonomy.tsx`. As Fatias 1 e 2
tinham rodado `make console-build`/equivalente antes de medir (Fatia 1,
§2.6, embora sem nomear o comando explicitamente) — eu não tinha, nesta
fatia, até tropeçar nisso.

**Correção**: `uv run python -m tools.console_gate build` (o alvo por trás
de `make console-build`), rodado do zero, terminou normalmente (manifesto de
rotas completo, incluindo `/settings/autonomy-guardrails`, sem erro). Depois
disso, o mesmo comando de `console_e2e run` foi repetido — resultado real,
em §22.

**Por que isso importa para quem rodar gates depois**: `tools.console_e2e
run`/`tools.spec_validation browser` **não** garantem um build fresco.
Rodar qualquer um deles sem `console_gate build`/`make console-build` logo
antes, depois de editar `console/src/**`, mede o binário antigo — um vermelho
ou um verde vindo desse jeito não prova nada sobre o código atual. Vale
registrar isso em algum lugar mais permanente (`AGENTS.md` do console, talvez)
se esta descoberta ainda não estiver lá — não fiz essa adição porque está
fora do escopo desta fatia de feature.

## 22. Comandos rodados nesta fatia, com resultado real

```
$ cd console && pnpm exec prettier --write src/surfaces/settings/autonomy.tsx src/i18n/en.ts src/i18n/pt-BR.ts
```
Reformatou os três arquivos (esperado, primeira formatação depois da escrita).

```
$ cd console && pnpm exec tsc --noEmit
```
Rodado repetidas vezes ao longo da fatia (depois de cada rodada de edição);
**sempre** saída vazia (sucesso) na versão final.

```
$ cd console && pnpm exec eslint <arquivos tocados, por rodada>
```
Sempre saída vazia na versão final.

```
$ uv run python -m tools.console_gate typecheck
```
`$ tsc --noEmit` — saída vazia.

```
$ uv run python -m tools.console_gate lint
```
`$ eslint . && node scripts/check-css-literals.mjs` — saída vazia.

```
$ uv run python -m tools.console_gate test
```
Rodado **duas vezes**. Primeira vez (depois de só T008/T009, antes das
correções colaterais de §23.3): **4 arquivos falharam, 7 testes falharam**,
de 145 arquivos / 2405 testes — `node-scope.test.tsx` (2),
`outage.test.tsx` (1), `behaviour.test.tsx` (3), `role-matrix.test.tsx` (1).
Segunda vez, depois das correções: **145 arquivos passaram, 2405 testes
passaram**, `exit 0` (confirmado explicitamente com `echo $?` no comando
final). Cobertura da rodada final:

```
Statements   : 94.37% ( 6222/6593 )
Branches     : 90.41% ( 4615/5104 )
Functions    : 92.07% ( 1928/2094 )
Lines        : 96.39% ( 5747/5962 )
```

Piso de 90% respeitado nas quatro métricas; `Branches` é a mais próxima
(90.41%, contra 90.42% no fim da Fatia 3 — variação de ruído de terceira
casa decimal, não uma queda real). Contagem de testes reconciliada à mão:
145 arquivos iguais; 2402 (fim da Fatia 3) + 4 (`autonomy.test.tsx`: T008
novo + três desdobramentos, ver §23.3) + 0 (`node-scope.test.tsx`: um caso
de loop saiu, um caso explícito entrou) + 0 (`outage.test.tsx`: mesmo
padrão) − 1 (`screens.test.tsx`: `'autonomy'` saiu do laço SC-001 sem
substituto) + 0 (`role-matrix.test.tsx`, `behaviour.test.tsx`: testes
existentes só ganharam `tab`, contagem igual) = **2405**. Bate exatamente.

```
$ uv run python -m tools.console_gate build
```
Terminou normalmente — manifesto de rotas do Next.js completo, incluindo
`/settings/autonomy-guardrails`, sem erro. Produziu
`.next/standalone/server.js` fresco.

```
$ uv run python -m tools.console_e2e run --backing mock --scenario populated \
  -- tests/e2e/scroll-budget.spec.ts tests/e2e/transversal-rules.spec.ts \
     tests/e2e/autonomy-tabs.acceptance.spec.ts
```
**Rodado duas vezes.** A primeira (§21) mediu um build stale — descartada,
não prova nada sobre este código. A segunda, contra o build fresco de
`console_gate build`: **4 failed, 40 passed, 7 skipped** (51 no total).//
As quatro falhas, todas em `autonomy-tabs.acceptance.spec.ts`:

- `:216` — alegação (h), CTA "Look at the configuration" ainda referenciado
  4× em `autonomy.tsx` — **esperado**, T016 é de uma fatia futura.
- `:256` — alegação (e), "no empty cell in the Value column, in either
  appearance" — mensagem real: `"the guardrails table drew no rows at
  all"`. **Não esperado por mim antes de rodar — ver §23.1, é o mesmo
  achado do resumo de guardrails ausente em Posture.** Esta alegação
  estava **verde** na Fatia 2 (a única das nove que já passava antes de
  qualquer aba existir); nesta fatia ela **regrediu para vermelho**, porque
  `ROUTE` sem `?tab=` abre em Posture e Posture, nesta implementação, não
  tem nenhuma linha `effective-field`.
- `:291` — alegação (f), override ainda visível no corpo — **esperado**,
  T036 é de uma fatia futura.
- `:327` — alegação (i), seção de simulação inexistente — **esperado**,
  T031 é de uma fatia futura.

As cinco alegações que **não** apareceram na lista de falhas — (a), (b),
(c), (d), (g) — passaram. Tenho confirmação direta, por linha de log com
`✓`, para (d) (`tests/e2e/scroll-budget.spec.ts... :133... each tab stays
within the per-tab scroll budget at 1920x1080 (500ms)`, achado com `grep`
no log salvo). Para (a), (b), (c) e (g) não tenho a linha de check
individual isolada no que já puxei para este contexto — a evidência é a
lista de falhas do Playwright, que é sempre exaustiva (lista **toda** falha
ao final), combinada com a contagem total (4 falhas + 40 passes + 7 skips =
51, batendo exatamente); não é uma suposição, mas é uma prova por
eliminação/aritmética, não uma linha de check vista diretamente — registro
a diferença para ser exato. O log completo desta segunda rodada está salvo
em `/tmp/claude-999/-srv-workspaces-NinjaSRE/e29a9bf0-2f14-4446-8c5f-6ffddf9509ba/scratchpad/t011-e2e-run-2.log`
(fora do repositório).

**Comparação com o vermelho registrado na Fatia 2** (8 failed / 1 passed,
9 no total, só (e) verde): agora são **4 failed / 5 passed**. Líquido: (a),
(b), (c), (d), (g) viraram verdes; (e) virou vermelha (regressão nomeada
acima); (f), (h), (i) continuam vermelhas, do jeito certo — pelo motivo que
a própria alegação descreve, não por engano de seletor. `8 − 5 + 1 = 4`,
bate.

**Não rodado**: o script descartável de medição de altura em pixel
(`_scratch-slice4-measure.spec.ts`) — criado, nunca executado. Ver §24.1.
`make verify` completo — fora do escopo desta fatia, o orquestrador é dono
dele. `console-visual-accept`/captura de baseline — não tocado, nenhuma
baseline foi capturada, aceita ou sobrescrita.

## 23. Achados desta fatia — o que fica nomeado, não escondido

### 23.1 O achado mais importante: Posture pode estar sem o resumo de guardrails que T009 pede

O despacho que abriu esta fatia dizia, na lista de distribuição:
"**Posture**: the posture reading and the guardrails summary region." E,
separadamente, na lista do que está explicitamente fora de escopo: "the
guardrails summary (T017)". As duas frases se tensionam: uma atribui o
resumo de guardrails a esta fatia (Posture), a outra o exclui
explicitamente (T017).

Escolhi a leitura da exclusão explícita — **Posture, nesta fatia, só tem o
`OverrideEditor`** (gated por `writable && nodeId !== ''`), nada mais. Minha
razão, no momento: a frase "Explicitly NOT in scope, however tempting..."
é o tipo de instrução que este próprio agente é orientado a pesar mais
que uma paráfrase de alto nível, e T017 (Fase 4, `tasks.md`) descreve
literalmente "Montar em Posture a leitura resumida dos guardrails... usando
o resolvedor de T007" — ou seja, o próprio plano atribui a **fonte de
dados** (via `guardrail-values.ts`, já pronta desde a Fatia 3) a uma fatia
futura.

**Mas, revendo `tasks.md` com mais cuidado ao escrever este ledger** — não
antes, é uma descoberta de agora — o texto literal de T009 diz "postura **e
resumo de guardrails** em Posture" (`tasks.md`, linha do próprio T009). Isso
é mais específico que a paráfrase do despacho, e mais plausível de uma
leitura: T009 poderia ter pretendido que eu **movesse/duplicasse** o bloco
`<EffectiveFieldsTable rows={guardrailRows} .../>` que já existia (com a
lista `GUARDRAIL_FIELD_LIST` inline que `autonomy.tsx` já tinha antes desta
fatia, não a de `guardrail-values.ts`) também para dentro de Posture — sem
o `ConfigEditor` (que ficaria só em Guardrails) — e que T017 mais tarde
trocaria essa cópia inline pela leitura de `guardrail-values.ts` (o mesmo
padrão que a Fatia 3, §16, já registrou para T019 fazer do lado de
Guardrails: "T019 precisa substituir, não só complementar, a cópia inline").
Essa leitura bateria com FR-020 ("essa leitura resumida NÃO DEVE duplicar a
**edição**" — que fala de duplicar o *controle de edição*, não a *tabela de
leitura*), e explicaria por que o despacho junta as duas frases na mesma
lista de distribuição de T009.

**Eu não sei qual das duas leituras é a certa, e não fiz a mudança sob
nenhuma delas** — a mensagem de interrupção chegou exatamente quando eu ia
medir, não implementar, e implementar uma mudança de conteúdo agora seria
desobedecer a instrução de parar. Registro as duas leituras, com a razão de
cada uma, para quem pegar esta fatia decidir com os dois lados na mesa —
inclusive o efeito prático: se a leitura "duplicar a tabela" vencer, a
altura de Posture medida em T011 (que hoje é só o `OverrideEditor`) muda, e
o orçamento de 1.5 viewport para essa aba precisa ser remedido depois da
mudança, não antes.

**Consequência já visível, não hipotética**: é exatamente esse buraco que
faz a alegação (e) do acceptance da feature regredir de verde para vermelho
(§22) — `ROUTE` sem `?tab=` abre em Posture, e Posture hoje não desenha
nenhuma linha `effective-field`. Se a leitura "duplicar a tabela" for a
certa, essa regressão desaparece sozinha quando for corrigida.

### 23.2 `AUTONOMY_FILTERS` — o que era, e o que virou

Antes desta fatia: `export const AUTONOMY_FILTERS: readonly FilterName[] =
['node'];`, declarada e usada **só dentro do próprio `autonomy.tsx`**
(`readViewState(search, AUTONOMY_FILTERS)`, uma linha abaixo). Confirmado
por `grep -rn "AUTONOMY_FILTERS" console/src console/tests` antes de tocar
o arquivo: **nenhum outro arquivo do console a importava** — nem tela, nem
teste. Por isso a decisão foi simples: apaguei a constante e o import de
`FilterName` que só existia para tipá-la, e troquei a chamada por
`readViewState(search, AUTONOMY_TAB_FILTERS)`, importando
`AUTONOMY_TAB_FILTERS` (`['node', 'tab']`) de `./autonomy-tabs` — o módulo
que a Fatia 3 já tinha construído exatamente para isso. Não é um re-export,
não é uma migração gradual: é a mesma constante de filtros que a tela já
lia, agora com um campo a mais, de um módulo dono diferente. `tsc --noEmit`
e `eslint` confirmaram que nada mais no projeto dependia do nome antigo.

### 23.3 As seis suítes de teste que a reorganização quebrou por tabela — cada uma, e por quê

Cortar uma tela em abas quebra qualquer teste que presumia "tudo está numa
página só". Encontrei e corrigi seis arquivos, todos side-effects diretos
de mover conteúdo para trás de `tab === 'x'`:

1. **`console/tests/unit/surfaces/settings/autonomy.test.tsx`** — o arquivo
   que T008 pede para estender. Toda asserção pré-existente que checava
   `autonomy-rule`, `autonomy-footer`, `bound`, `autonomy-stopped`,
   `config-editor` (a versão de Guardrails), `advanced-config-policies-autonomy`
   ou `way-back` ganhou `{ tab: 'rules-windows' }` ou `{ tab: 'guardrails' }`
   em `renderAutonomy(...)`, conforme o testid. Dois casos precisaram
   virar dois testes em vez de um, porque checavam simultaneamente algo de
   `rules-windows` **e** algo de `posture` no mesmo render, o que não é
   mais possível com uma única aba ativa por vez:
   - "leaves the editor and the override panel out for a viewer who may not
     write" → "leaves the editor out..." (tab `rules-windows`) +
     "leaves the override panel out, on its own tab..." (tab `posture`).
   - "shows exactly one empty panel and nothing that needs a node" (a
     descrição "a deployment with no organisation tree at all") → mesma
     divisão.
   - "a populated node > renders nothing as empty" ganhou uma segunda `it()`
     ("renders the override panel as not-empty either, on its own tab") só
     para não perder a cobertura do painel de Posture nesse cenário.
   O teste de "the guardrails section" que checava
   `getAllByTestId('config-editor')).toHaveLength(2)` (o de Guardrails e o
   da seção avançada de `policies.autonomy.*`, antes na mesma página) virou
   `toHaveLength(1)` — os dois `ConfigEditor` agora vivem em abas
   diferentes, e o comentário foi reescrito para dizer isso.
   Vermelho confirmado de verdade (não inferido) antes da correção:
   16 failed / 3 passed em 19 testes originais, rodando contra a tela nova
   sem o teste ainda ajustado — ver §21 (não, isso foi contra a tela
   restaurada corretamente, não o build stale do console_e2e; a
   restauração/prova de vermelho do T008 em si está descrita abaixo). Verde
   final: 23/23.
2. **`console/tests/unit/surfaces/screens.test.tsx`** — o sweep
   `SC-001: every screen, with no data, says what would be here` renderiza
   cada tela sem nenhum parâmetro de busca (não há mecanismo de query por
   tela nesse laço específico), então `autonomy` caía sempre em Posture.
   Antes desta fatia, Posture não existia — a página inteira sempre tinha
   um `way-back`. Agora Posture (sem override) não tem nenhum. Corrigido
   adicionando `'autonomy'` a `NEVER_EMPTY`, com um comentário nomeando a
   razão e apontando para quando isso deveria ser revisto (quando o
   conteúdo de Posture — T014 — existir). `decisions`/`agent`, os outros
   dois screens de múltiplas abas já cadastrados, **não** estão em
   `NEVER_EMPTY` — confirma que o padrão esperado é "a aba padrão tem seu
   próprio empty state", e Posture, nesta fatia, é a exceção porque seu
   conteúdo real ainda não foi construído.
3. **`console/tests/unit/surfaces/node-scope.test.tsx`** — `NODE_SCOPED =
   ['autonomy']` alimentava um laço genérico que verificava "pelo menos um
   painel, nenhum em erro, ao menos um vazio" sem nó nenhum. Sem nó, Posture
   não desenha painel nenhum (o `OverrideEditor` também está gated por
   `nodeId !== ''`). Troquei `NODE_SCOPED` para um array vazio (com
   comentário explicando por quê — o mesmo padrão que `agent` já usa,
   fora do laço, com seu próprio teste nomeado) e adicionei
   `'autonomy (rules & windows tab): renders rather than throwing when no
   node resolves'` explicitamente, com `{ tab: 'rules-windows' }`. Um
   segundo teste, fora desse laço ("autonomy: keeps its node when the tree
   it did not need is unreachable"), checava `autonomy-rule` — ganhou o
   mesmo `{ tab: 'rules-windows' }`.
4. **`console/tests/unit/surfaces/outage.test.tsx`** — o mesmo padrão do
   item 3, mas para o cenário "gateway fora do ar e sem nó". O `renderArea`
   local não aceitava um segundo argumento de query — adicionei um,
   opcional, compatível com as chamadas existentes. Criei um conjunto
   `NO_PANEL_WITH_NO_NODE = new Set(['autonomy'])` para tirar `autonomy` do
   laço genérico sobre `AREAS`, e um teste explícito
   `'/autonomy (rules & windows tab): still renders'` com
   `{ tab: 'rules-windows' }` logo depois.
5. **`console/tests/unit/surfaces/behaviour.test.tsx`** — os três testes do
   describe `'the autonomy screen'` (ordem de resolução das regras, o texto
   do rodapé, freeze+budget lado a lado) ganharam `{ tab: 'rules-windows' }`
   — sem isso, `renderArea('autonomy')` caía em Posture e nenhum dos três
   testids existia.
6. **`console/tests/unit/surfaces/role-matrix.test.tsx`** — "shows the most
   privileged role at least one of them" chamava
   `autonomy.render({ searchParams: Promise.resolve({}) })` e checava
   `config-editor`. Ganhou `{ tab: 'guardrails' }`; o comentário foi
   reescrito (dizia "this page now draws two" — não é mais verdade, os dois
   `ConfigEditor` estão em abas diferentes agora).

Todos os seis foram confirmados vermelhos pelo motivo certo antes da
correção (mensagens reais de `getByTestId`/`getAllByTestId` não encontrando
elemento, ou contagem errada — nunca um erro de sintaxe ou timeout de rota),
e verdes depois — a rodada final de `console_gate test` (§22) é a prova
agregada.

### 23.4 Achados para T040 — a suíte transversal, depois do corte em abas

Não toquei `console/tests/e2e/transversal-rules.spec.ts` — é
explicitamente reservado a T040 pelo despacho desta fatia. Dois achados
concretos, distintos, que T040 precisa de mim para decidir:

**(i) O comentário de `SCROLL_BUDGET_MEASURED_ELSEWHERE` ficou impreciso.**
O comentário (por volta das linhas 135-140 e 168-171, números de antes
desta fatia) diz que `/settings/autonomy-guardrails` é medido por
`scroll-budget.spec.ts` "via the retired `/autonomy` address, which
redirects here". Isso deixou de ser verdade: `/autonomy` saiu de
`SCREENS` nesta fatia (T011), e a rota agora é medida em
`scroll-budget.spec.ts` **três vezes**, por aba, no endereço canônico
(`/settings/autonomy-guardrails?tab=X`), nunca pelo endereço aposentado.
O `test.skip` continua correto **no resultado** (a rota é, de fato, medida
em outro arquivo), mas o texto que explica o mecanismo está desatualizado
e precisa ser reescrito quando T040 rodar.

**(ii) A regra `value-column` da suíte transversal, para esta rota, ficou
vazia por acidente — não zero-encontrado-zero-vazio, zero-testado.**
`configurationValueCells()` (em `transversal-rules.spec.ts`) abre
`page.goto(route.path)` sem `?tab=`, cai em Posture, lê
`page.getByTestId('effective-field')` — que, nesta implementação, não
existe em Posture. `values` fica `[]`; `values.findIndex(v => v === '')`
retorna `-1` sobre um array vazio, e a asserção passa **sem examinar
nenhuma célula**. Isso é o padrão "passa por acidente de fixture" que este
mesmo arquivo de instruções nomeia como defeito — só que aqui é "passa por
acidente de aba", não de fixture. Não é uma suposição: é a consequência
direta e verificável da minha própria distribuição de conteúdo (Guardrails
só na aba Guardrails), e bate com a contagem observada em §22 (a alegação
(e) do acceptance falhou dizendo exatamente `"the guardrails table drew no
rows at all"` no mesmo cenário). T040 decide se isso vira uma exceção
nomeada em `EXCEPTIONS`, se a regra passa a rodar por aba, ou outra coisa —
não decidi por eles.

Um terceiro achado, menor, na mesma família: a regra `vocabulary` para esta
rota também perdeu área de varredura (Posture tem muito menos texto visível
que a página inteira de antes), mas não fica vazia — ainda examina o texto
real do `OverrideEditor`. Não é um "passa vazio" como o item (ii); é só
menos superfície coberta. Registrado para completude, não como um achado do
mesmo peso.

### 23.5 O bug pré-existente do redirect `/autonomy`, encontrado, não corrigido

`console/src/app/(shell)/autonomy/page.tsx` (não tocado nesta fatia)
recebe `searchParams`, dá `await` nele e **descarta**: `redirect('/settings/autonomy-guardrails')`
sem nenhum parâmetro. Isso já existia antes desta feature — um link antigo
`/autonomy?node=X` já perdia o `node` no redirect. Com abas, o mesmo defeito
agora também engoliria um `?tab=X`, se alguém tivesse um link assim. Não
corrigi porque (a) não está no meu escopo nomeado, (b) já era um defeito
pré-existente, meu trabalho só o tornou um pouco mais visível. É por isso
que o T011 mede a rota pelo endereço canônico
(`/settings/autonomy-guardrails?tab=X`), não pelo endereço aposentado — o
mesmo motivo que fez a suíte de acceptance da Fatia 2 escolher `ROUTE =
'/settings/autonomy-guardrails'` desde o início.

### 23.6 A armadilha do wrapper — confirmado que não caí nela

Por instrução explícita do despacho, verifiquei isto com cuidado antes de
escrever: `<TabLinks>` está na árvore como **irmã direta** de
`<SettingsPageHeader>`, sem nenhuma `<div>` entre os dois —

```tsx
<SettingsPageHeader page={page} locale={locale} nested={...} />

<TabLinks
  label={message(locale, 'autonomy.tabs')}
  selected={tab}
  tabs={AUTONOMY_TABS.map((each) => ({ ... }))}
/>

<div className="mt-4">
  <SetupReturnBanner ... />
  {tab === 'rules-windows' ? (...) : null}
  {tab === 'guardrails' ? (...) : null}
  {tab === 'posture' && writable && nodeId !== '' ? (...) : null}
</div>
```

`TabLinks` (`components/navigation.tsx`) já desenha seu próprio
`<nav data-testid="tab-links">` — não precisei (nem quis) envolvê-la em
nada. O `<div className="mt-4">` só embrulha o conteúdo **depois** da tira
de abas, no mesmo padrão que `decisions.tsx` usa (`<div
className="mt-4">{content}</div>`), nunca a tira em si.

## 24. O que fica pendente, nomeado, não escondido

- **A altura real em pixels de cada aba não foi medida.** Digo isto sem
  estimar: **não sei os três números.** Sei que as três asserções de
  orçamento passaram de verdade contra um build fresco (§22, §11 acima),
  então sei que as três estão `≤ 1620px`, mas não sei o valor exato de
  nenhuma. Ver §24.1.
- **A ambiguidade do resumo de guardrails em Posture (§23.1)** — a
  descoberta mais importante desta fatia, não resolvida, com as duas
  leituras e suas consequências postas lado a lado. Quem pegar esta fatia
  precisa decidir antes de tocar T012–T017, porque a decisão muda o que
  T014/T017 encontram pela frente.
- **A regressão da alegação (e) do acceptance da feature** (§22, §23.1) —
  nomeada, não escondida: verde na Fatia 2, vermelha agora, mensagem real
  `"the guardrails table drew no rows at all"`. Some sozinha se a leitura
  "duplicar a tabela" do achado acima for a adotada; continua vermelha,
  esperando T017, se a outra leitura vencer.
- **Os dois achados de `transversal-rules.spec.ts` para T040 (§23.4)** —
  o comentário desatualizado de `SCROLL_BUDGET_MEASURED_ELSEWHERE` e a
  regra `value-column` passando vazia para esta rota.
- **O bug pré-existente do redirect `/autonomy` (§23.5)** — encontrado,
  não corrigido, fora do escopo nomeado.
- **Os três sites de `Badge` com nível cru** (Fatia 1, §4) — continuam sem
  dono, nomeados de novo só para não se perderem entre fatias.
- **Tudo que já estava fora de escopo por instrução explícita do
  despacho** — T014 (seletor de postura, empty state), T015 (remoção dos
  três parágrafos), T016 (retirada do CTA "Look at the configuration"),
  T017 (resumo de guardrails via `guardrail-values.ts`, com a ressalva do
  §23.1 sobre o que pode já estar implícito em T009), T020 (edição
  inline), T031 (convergência da simulação), T036 (painel lateral do
  override) — nenhum foi tocado.

### 24.1 O arquivo descartável que não chegou a rodar

`console/tests/e2e/_scratch-slice4-measure.spec.ts` **existe na árvore de
trabalho agora**, criado para imprimir a altura real de cada aba via
`console.log`, no mesmo padrão descartável que a Fatia 1 já usou (script
criado, rodado uma vez, apagado — não sobrevive no repositório). A
interrupção do orquestrador chegou exatamente antes de eu rodá-lo. Ele
**nunca rodou** — nenhum número saiu dele. Conteúdo exato, para quem for
terminá-lo ou apagá-lo:

```typescript
import { expect, test } from '@playwright/test';

import { signIn } from './session';

test.use({ viewport: { width: 1920, height: 1080 } });

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

for (const tab of ['posture', 'rules-windows', 'guardrails']) {
  test(`SLICE4 measure ${tab}`, async ({ page }) => {
    await page.goto(`/settings/autonomy-guardrails?tab=${tab}`);
    await expect(page.getByTestId('page-header')).toBeVisible();
    const height = await page.evaluate(() => document.documentElement.scrollHeight);
    console.log(`SLICE4 tab=${tab} height=${height}`);
  });
}
```

Duas ações possíveis para a próxima sessão, nenhuma delas tomada por mim:
rodá-lo uma vez com `uv run python -m tools.console_e2e run --backing mock
--scenario populated -- tests/e2e/_scratch-slice4-measure.spec.ts` (build
já está fresco, feito nesta fatia — mas confira `git status` em
`console/src` antes de confiar nisso, qualquer edição desde então invalida
o build) e depois apagá-lo; ou simplesmente apagá-lo sem rodar, já que os
três números "abaixo do orçamento" já estão provados pelo teste committed
(T011) — os números exatos são só uma curiosidade a mais para o ledger, não
uma prova que falta.

## 25. Arquivos alterados — Fatia 4

- `console/src/surfaces/settings/autonomy.tsx` — reescrito por inteiro: três
  branches de aba, `TabLinks` como irmã do cabeçalho, `AUTONOMY_FILTERS`
  removida em favor de `AUTONOMY_TAB_FILTERS`/`hrefForTab`/`tabFrom`/
  `tabLabel` de `./autonomy-tabs`. Ver §23.1 para a lacuna de conteúdo
  não resolvida.
- `console/src/i18n/en.ts` — chave nova `autonomy.tabs` (aria-label da tira
  de abas).
- `console/src/i18n/pt-BR.ts` — a mesma chave, traduzida.
- `console/tests/unit/surfaces/settings/autonomy.test.tsx` — describe novo
  de T008; toda asserção pré-existente relevante ganhou `tab`; três casos
  desdobrados em dois. Ver §23.3.1.
- `console/tests/unit/surfaces/screens.test.tsx` — `'autonomy'` somado a
  `NEVER_EMPTY`, comentário nomeando a razão. Ver §23.3.2.
- `console/tests/unit/surfaces/node-scope.test.tsx` — `NODE_SCOPED`
  esvaziado (comentário explicando), um teste explícito de `autonomy` no
  tab `rules-windows` somado; um teste existente ganhou `tab`. Ver §23.3.3.
- `console/tests/unit/surfaces/outage.test.tsx` — `renderArea` local ganhou
  um segundo parâmetro opcional; `NO_PANEL_WITH_NO_NODE` novo, exclui
  `autonomy` do laço genérico; um teste explícito somado. Ver §23.3.4.
- `console/tests/unit/surfaces/behaviour.test.tsx` — três testes do
  describe `'the autonomy screen'` ganharam `tab`. Ver §23.3.5.
- `console/tests/unit/surfaces/role-matrix.test.tsx` — um teste ganhou
  `tab`; comentário reescrito. Ver §23.3.6.
- `console/tests/e2e/scroll-budget.spec.ts` — `/autonomy` saiu de
  `SCREENS`; laço novo por aba contra `CONFIG_SCREEN_TAB_SCROLL_BUDGET_VIEWPORTS`.
- `console/tests/e2e/_scratch-slice4-measure.spec.ts` — **novo, não
  commitável, nunca rodado**. Ver §24.1.
- `specs_v6/040-autonomy-tres-abas/tasks.md` — caixas de T008, T010 e T011
  marcadas. **T009 não foi marcada** — ver §23.1 e a tabela do §20.
- `specs_v6/040-autonomy-tres-abas/controle.md` — esta seção, acrescentada.

Nenhum outro arquivo foi tocado. `console/tests/e2e/transversal-rules.spec.ts`
foi lido, não editado — reservado a T040, achados em §23.4.

---

# Fatia 4 — reparo (T008–T011, retomado após a interrupção)

**Esta seção não é uma fatia nova.** É o reparo, pedido explicitamente pelo
orquestrador, da Fatia 4 acima — mesmas tarefas (T008–T011), mesma User
Story 1. Nada do que está em §20–§25 foi reescrito; esta seção só acrescenta,
como a instrução pediu. Branch `feat/v6-scope-and-settings`, em cima das
Fatias 1–3 já commitadas (`779d834`, `a35bc83`, `a9aff13`). Nada foi
commitado, staged, nem passou por `git add` nesta sessão. A árvore já tinha o
trabalho da sessão anterior quando esta começou; nada foi revertido —
`console/tests/e2e/_scratch-slice4-measure.spec.ts` já tinha sido apagado
pelo próprio orquestrador antes deste despacho, confirmado por
`ls console/tests/e2e/` no início desta sessão.

## 26. Tabela de estado — reparo

| Peça | Estado | Detalhe |
|---|---|---|
| Defeito 1 — redistribuição (bound panels → Posture) | **FEITO** | Ver §28. `autonomy.tsx:689-812` (aba Posture agora com o painel "Autonomy bounds" + `OverrideEditor`); `autonomy.tsx:390-608` (aba Rules & windows sem o painel de bounds, grid de duas colunas removida). |
| Defeito 1 — o CTA do painel de bounds, cross-tab | **FEITO** | Ver §28.2. `autonomy.tsx:337-343` (`boundsEditorHref` agora usa `hrefForTab`), provado por um teste novo (`autonomy.test.tsx:813-833`, vermelho→verde real, ver §29.4 — não, ver §33.5). |
| Defeito 1 — kill switch e seção avançada, julgados | **FEITO** | Ver §28.3. Kill switch: move com o painel de bounds para Posture (estava aninhado nele, nunca foi um bloco separado). Seção avançada: fica em Rules & windows — já era essa a alocação do mapa `AUTONOMY_TAB_FIELDS` desde a Fatia 3, confirmada correta, não meramente herdada sem exame. |
| Defeito 2 — (g), por aba | **FEITO** | Ver §29.1. `autonomy-tabs.acceptance.spec.ts:180-244`. Vermelho em DUAS abas, não uma — ver §30, a descoberta nova. |
| Defeito 2 — (f), por aba | **FEITO** | Ver §29.2. `autonomy-tabs.acceptance.spec.ts:364-385` (loop) + `:386-406` (botão, inalterado). |
| Defeito 2 — (e), por aba | **FEITO** | Ver §29.3. `autonomy-tabs.acceptance.spec.ts:295-352`. Guardrails verde; Posture vermelho, nomeado. |
| Achado extra — (i) apontava para a aba errada | **FEITO, corrigido por conta própria** | Ver §29.4. Não fazia parte das três alegações nomeadas pelo despacho; encontrado e corrigido pela mesma razão de raiz. `autonomy-tabs.acceptance.spec.ts:409-419`. |
| Defeito 3 — redirect `/autonomy` | **Verificado, não corrigido (por instrução)** | Ver §31. Confirmado de novo: `console/src/app/(shell)/autonomy/page.tsx:10-17` ainda descarta `searchParams`. |
| Alturas remedidas | **FEITO** | Ver §32. **posture: 1080px, rules-windows: 1309px, guardrails: 1080px** — todas dentro do orçamento de 1620px. |
| T009 | **NÃO MARCADA — deliberadamente** | Ver §28.4. A redistribuição dos painéis de bounds está correta e completa; a metade "resumo de guardrails em Posture" do próprio texto de T009 continua pendente, atribuída a T017 pelo escopo explícito deste despacho. T009 como um todo não está feito enquanto essa metade não estiver. |

## 27. O que eu li antes de tocar qualquer coisa

Reli `spec.md` inteiro (FR-001 a FR-052, as seis User Stories, os Edge Cases),
`tasks.md` (T001–T045), o mockup `specs_v6/mockups/settings-v6.html#m2`
(linhas 206-257) e `autonomy-tabs.ts` (o mapa `AUTONOMY_TAB_FIELDS`,
`console/src/surfaces/settings/autonomy-tabs.ts:102-128`, já commitado desde
a Fatia 3) antes de decidir qualquer coisa sobre onde o painel de bounds
deveria ir. O raciocínio de cada decisão está em §28.

## 28. Defeito 1 — a redistribuição, resolvida

### 28.1 Onde cada bloco foi parar, e por quê

**O painel "Autonomy bounds" inteiro (stopped/kill-switch, freezes, budgets,
overrides) mudou de Rules & windows para Posture.** Antes: dentro da segunda
coluna de um grid de três colunas em `tab === 'rules-windows'`
(`autonomy.tsx`, antes desta sessão, linhas 618-730 — ver a citação exata no
despacho). Depois: `autonomy.tsx:689-812`, dentro de `tab === 'posture'`,
como o primeiro filho de um `<div className="flex flex-col gap-5">`, antes
do painel do `OverrideEditor`.

**A razão, por cima da instrução explícita do despacho** ("Move the bound
panels to Posture"): os três tipos de `bound` — congelamento, teto, override
— e o estado parado (`stopped`) respondem exatamente a pergunta que Posture
faz ("o que este deployment pode fazer sozinho, agora"), não a pergunta que
Rules & windows faz ("quando ele não pode", que é sobre a CONFIGURAÇÃO que
produz esse estado — o formulário de criar regra/congelamento/teto dentro de
`AutonomyEditor`, que **não** se moveu). A distinção que resolve a aparente
contradição com a letra de T009 ("congelamentos, tetos... em Rules & windows")
é a mesma que já existe no produto para guardrails (FR-019/FR-020): uma coisa
é a aba que **edita/cria** um campo (`AutonomyEditor`, que continua desenhando
os formulários de novo congelamento e novo teto em Rules & windows — nenhum
controle de criação se moveu), outra é a aba que **lê** o estado atual desse
mesmo campo em resumo (o painel de bounds, agora em Posture). O mapa de posse
de campo (`AUTONOMY_TAB_FIELDS`, `autonomy-tabs.ts:110,112`) continua
atribuindo `policies.autonomy.freezes`/`budgets` a `rules-windows` — e
continua correto, porque esse mapa é sobre onde um campo é **editável**
(FR-046, "alcançável... dentro de exatamente uma das três abas"), não sobre
onde toda leitura dele pode aparecer. Já havia precedente exatamente disso
no próprio comentário do mapa (`autonomy-tabs.ts:97-100`, sobre o resumo de
guardrails em Posture: "not a second owner of the path, only a second place a
slice of it is shown or changed").

**Simplificação de layout, consequência direta da mudança, não um redesenho**:
o grid de três colunas (`grid grid-cols-1 gap-5 lg:grid-cols-3` +
`lg:col-span-2 min-w-0`) que existia só para acomodar a segunda coluna
(painel de bounds) ficou sem razão de existir depois que essa coluna saiu —
uma coluna vazia de 1/3 da largura teria sobrado. Troquei por um único
`<div className="min-w-0">` (`autonomy.tsx:390-391`) envolvendo o mesmo
conteúdo que já estava lá (tabela de regras, rodapé, nota de dry-run, editor,
seção avançada) — nenhum controle mudou, só o wrapper que não tinha mais
função.

### 28.2 O CTA do painel de bounds, e um bug que a mudança teria introduzido silenciosamente

`boundsEditorHref` apontava para `'#new-freeze'` — uma âncora que só existe
dentro de `AutonomyEditor`. Antes desta sessão, o painel de bounds e
`AutonomyEditor` viviam na MESMA aba, então o link funcionava. Depois da
mudança, o painel de bounds passa a viver em Posture enquanto `#new-freeze`
continua só existindo em Rules & windows — um link que aponta para uma âncora
ausente da página renderizada, silenciosamente quebrado.

Corrigido em `autonomy.tsx:337-343`:

```tsx
const boundsEditorHref = canCreateHere
  ? `${hrefForTab(state, 'rules-windows', nodeId)}#new-freeze`
  : '/settings';
```

Isto não estava listado como uma das "Duas coisas erradas" do despacho — é
uma consequência que encontrei ao mover o bloco, da mesma família do link
`ruleEditorHref`/`overrideEditorHref` (que não precisaram de mudança, porque
seus alvos ficaram na mesma aba que seus próprios painéis). Não é possível
exercitar este estado através do cenário `populated` (nenhum nó tem
congelamentos/tetos/overrides vazios simultaneamente — achado já registrado
na Fatia 2, §9.2 (h)), mas é testável no nível de unidade sem tocar fixture
nenhuma: `autonomy.test.tsx:813-833`, um teste novo, provado vermelho antes
da correção (`href` continha `#new-freeze` sem `tab=rules-windows`) e verde
depois — ver §33.5.

### 28.3 O kill switch e a seção avançada, julgados pela pergunta que cada um responde

**Kill switch** (`KillSwitchControl`, `autonomy.tsx:722-726`): move com o
painel de bounds para Posture porque nunca foi um bloco à parte — sempre
esteve aninhado dentro do mesmo `<dl>`, na linha `stopped` (`autonomy.tsx:710-729`).
"Está tudo parado" é o caso extremo da pergunta de Posture ("o que este
deployment pode fazer sozinho" — a resposta, quando parado, é "nada"). Não
há campo de schema (`policies.*`) por trás de `stopped` — vem de
`/v1/autonomy/policy/{node}/bounds`, fora do mapa `AUTONOMY_TAB_FIELDS` de
17 entradas — então mover o controle não tensiona o contrato de paridade
(FR-046/047/048): não existe uma segunda posse em jogo.

**Seção avançada** (`AdvancedConfigSection`, os quatro escalares
`policies.autonomy.{allow_unverifiable_actions,dry_run,recurrence_threshold,
recurrence_window_seconds}`): fica em Rules & windows, **inalterada**
(`autonomy.tsx:568-583`). Julgada pela mesma pergunta: os quatro campos são
restrições sobre QUANDO uma regra pode decidir sozinha — verificação
(`allow_unverifiable_actions`), simulação (`dry_run`, explicitamente listado
por T009 como pertencente a Rules & windows), e o freio de repetição
(`recurrence_threshold`/`recurrence_window_seconds`) — a mesma pergunta que
Rules & windows já responde, não uma leitura de estado atual como o painel de
bounds. Isto **já era** a alocação do mapa `AUTONOMY_TAB_FIELDS`
(`autonomy-tabs.ts:109,111,113-114`) desde a Fatia 3 — não é uma decisão nova
desta sessão, é essa alocação existente, examinada e confirmada correta antes
de deixá-la como estava, não apenas herdada sem exame.

### 28.4 T009: por que continua sem marcar

O próprio texto de T009 (`tasks.md`, a linha da tarefa) diz "postura **e
resumo de guardrails** em Posture". A redistribuição desta sessão entrega a
primeira metade (a leitura de postura — bounds, kill switch, override) mas
**não** a segunda (o resumo de guardrails, Setting/Value/Set at, via
`guardrail-values.ts`) — essa é T017, explicitamente fora do escopo deste
despacho ("still no T017"). Como o despacho pediu para marcar T009 "somente
se a distribuição bater com o próprio texto" e uma parte nomeada do próprio
texto continua sem controle nenhum em Posture, deixei a caixa desmarcada.
Quem fizer T017 é quem fecha T009.

## 29. Defeito 2 — as quatro alegações corrigidas, uma a uma

Comando usado para toda a verificação desta seção (rebuilda por padrão):

```
uv run python -m tools.spec_validation browser \
  --feature specs_v6/040-autonomy-tres-abas \
  --test console/tests/e2e/autonomy-tabs.acceptance.spec.ts
```

Resultado final, contra o build fresco depois de todas as mudanças desta
sessão: **7 failed, 8 passed (15 no total)**. Reconciliação com o vermelho da
Fatia 4 original (4 failed / 5 passed em 9 alegações — §22 acima): as
alegações (g), (e) e (f) explodiram de 1 teste cada para respectivamente 3+1
(g cobre agora três abas mais o teste de CTA já existente), 2 (e), 4 (f, três
abas mais o botão) — a contagem total de testes cresceu de 9 para 15, não
porque a cobertura ficou mais fraca, mas porque cada alegação screen-wide
agora tem um teste por aba, nomeado.

### 29.1 (g) — por aba

`autonomy-tabs.acceptance.spec.ts:180-244`. A varredura em si **não mudou uma
linha** — só passou a rodar dentro de um laço `for (const tab of TAB_IDS)`,
navegando para `${ROUTE}?tab=${tab}` antes de cada rodada, com a mensagem de
falha prefixada por `tab=${tab}:` (linha 242). Três testes nomeados
`no paragraph sits between the title and the first control, tab=posture`
(idem para `rules-windows`, `guardrails`).

**Resultado real**: `tab=posture` passa. `tab=rules-windows` falha —
esperado, é o mesmo achado de sempre (`autonomy-glossary`,
`autonomy.tsx:454-462`, T015 não rodou). `tab=guardrails` **também falha** —
não esperado pelo despacho, que só previa vermelho em rules-windows. Ver §30,
a descoberta nova, para o porquê e o que fica pendente sobre ela.

### 29.2 (f) — por aba

`autonomy-tabs.acceptance.spec.ts:356-406`. Dividido em quatro testes: três
no laço (`the override editor does not occupy body space, tab=${tab}`,
linhas 364-385) checando só `not.toBeVisible()` de `override-editor`, mais o
teste do botão do cabeçalho/`dialog` (linhas 386-406, inalterado em conteúdo,
só separado da checagem de visibilidade).

**Resultado real**: `tab=rules-windows` e `tab=guardrails` passam (o
componente nem está montado nessas abas). `tab=posture` falha — esperado, o
painel continua no corpo até T036. O teste do botão falha — esperado, o
botão não existe até T036.

### 29.3 (e) — por aba

`autonomy-tabs.acceptance.spec.ts:283-352`. Fatorei a varredura "abrir todo
`<details>` e checar cada linha" numa função `assertNoEmptyValueCell(page)`
(linhas 285-312) — **sem** a asserção de contagem de linhas, porque as duas
alegações discordam sobre se zero linhas é o estado esperado hoje. Dois
testes chamam essa função depois de fazer sua própria checagem de contagem,
com sua própria mensagem:

- `tab=guardrails` (linhas 321-332): `rowCount` > 0, mensagem
  `"tab=guardrails: the guardrails table drew no rows at all"` se falhar —
  **passa**, exatamente como antes, provando que a coluna Value continua
  preenchida na aba que sempre teve a tabela.
- `tab=posture` (linhas 334-351): `rowCount` > 0, mensagem
  `"tab=posture: 0 guardrails-summary rows — Posture's read-only guardrails
  summary is not built yet (a later slice); this stays red until it is"` —
  **falha**, pela razão nomeada, não mais por "the guardrails table drew no
  rows at all" (uma mensagem que soaria como bug real, não como trabalho
  pendente e nomeado).

### 29.4 (i) — achado e corrigido por conta própria, não uma das três alegações do despacho

`autonomy-tabs.acceptance.spec.ts:408-419`. O despacho nomeou (g), (f), (e)
como "screen-wide" — checadas numa aba só, deveriam checar três. (i) é
diferente: FR-032/033/034 (User Story 5) descrevem uma seção que só pode
existir numa aba (Rules & windows, onde `AutonomyEditor` vive) — não é uma
alegação "de toda a tela testada numa aba só", é uma alegação de UMA aba só,
testada na aba ERRADA (`page.goto(ROUTE)`, sem `?tab=`, cai em Posture — a
aba onde `autonomy-simulation` nunca vai existir). O teste original passava
disfarçado de correto porque, hoje, `autonomy-simulation` não existe em
NENHUMA aba — o vermelho seria idêntico não importa qual aba fosse
verificada. No dia em que T031 construir a seção dentro de `AutonomyEditor`
(Rules & windows), este teste continuaria vermelho para sempre, olhando para
a aba errada — um falso vermelho permanente que ninguém saberia diagnosticar
sem reler este próprio arquivo.

**Corrigido** trocando `page.goto(ROUTE)` por
`page.goto(\`${ROUTE}?tab=rules-windows\`)` (linha 419), com um comentário
(linhas 409-418) documentando explicitamente que este achado não estava na
lista de três do despacho, foi encontrado ao reparar as outras três, e
corrigido pela mesma causa raiz — nomeado, não escondido. Vermelho continua
pela razão certa (`autonomy-simulation` não existe), confirmado no resultado
real (§29, a lista de 7 falhas inclui esta, na linha 409 do arquivo).

## 30. Descoberta nova: o parágrafo-lead da aba Guardrails também viola a varredura de (g)

`tab=guardrails` falhou com: `"a paragraph sits before the first control:
\"Masking, secret detection and approval — edited here, in the same document
a rule or a bound is.\""`. Este é `settings.autonomy.guardrails.lead`
(`console/src/i18n/en.ts:1907-1908`), renderizado em `autonomy.tsx:612-615`
(`<p className="text-meta text-muted max-w-prose">`), logo depois do `<h3>`
de título da aba e antes de qualquer `INPUT/SELECT/BUTTON/TEXTAREA/A`.

**Por que isso não apareceu antes**: o acceptance da Fatia 2 só testava
Posture (`ROUTE` sem `?tab=`) — nunca tinha visitado a aba Guardrails com
esta varredura específica. Este parágrafo já existia, verbatim, antes desta
sessão (eu não o escrevi, não o toquei) — só nunca tinha sido examinado por
este teste até eu estender (g) para as três abas, por instrução direta do
despacho.

**Não corrigi isto.** Duas razões: (1) o despacho lista T015 (remoção dos
parágrafos conceituais) como fora de escopo desta fatia — mesmo que este
parágrafo específico não seja um dos "três parágrafos de hoje" que FR-010
nomeia explicitamente ("os três parágrafos de hoje deixam de existir"), é a
mesma classe de conteúdo (prosa entre o título e o primeiro controle) e a
mesma tarefa (T019, dona da aba Guardrails, ou T015) que decidiria removê-lo
ou reescrevê-lo; (2) genuinamente não sei se isto é uma violação real de
FR-010 ou um falso positivo da minha própria varredura. A letra de FR-010 diz
"nenhum parágrafo conceitual" (geral), mas FR-033 (User Story 5) **exige**
exatamente este padrão para a seção de simulação — "uma linha que diz o que
ela responde" — o que sugere que uma frase curta de orientação de seção não é
o que FR-010 pretende banir, só a prosa de glossário abstrata que ficava
solta no topo da página inteira. Não decidi essa leitura sozinho; nomeio para
quem tocar T015/T019 decidir com as duas leituras na mesa. **Não afrouxei a
varredura para evitar este achado** — instrução explícita era "do not chase
green", e continuo sem, mesmo com um vermelho a mais do que o despacho
previu.

## 31. Defeito 3 — o redirect `/autonomy`, confirmado de novo

`console/src/app/(shell)/autonomy/page.tsx:10-17`:

```tsx
export default async function Page({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  await searchParams;
  redirect('/settings/autonomy-guardrails');
}
```

`searchParams` é aguardado e depois **descartado por completo** — o
`redirect()` não carrega nenhum parâmetro adiante. Confirmado por leitura
direta do arquivo, não por inferência; o arquivo não foi tocado nesta sessão
nem na anterior. Isto já era verdade antes desta feature (achado da Fatia 4
original, §23.5) e continua verdade agora — não corrigido, por instrução
explícita ("Do not fix it in this slice"), nomeado para T026/T027.

**`scroll-budget.spec.ts` já mede pelo endereço canônico, não pelo
redirect**: confirmado por leitura direta —
`console/tests/e2e/scroll-budget.spec.ts:113` declara
`AUTONOMY_ROUTE = '/settings/autonomy-guardrails'`, usado nas três iterações
do laço por aba (`:119-135`); nenhuma linha deste arquivo visita `/autonomy`.
Isto já era verdade desde a Fatia 4 original (T011) e permanece verdade — o
`/autonomy` aposentado nunca é exercitado por este teste. Fato para T040:
`transversal-rules.spec.ts` ainda cita o endereço aposentado no seu
comentário sobre `SCROLL_BUDGET_MEASURED_ELSEWHERE` (achado já nomeado na
Fatia 4 original, §23.4(i) — não tocado por mim, confirmado ainda presente
por leitura, arquivo não editado nesta sessão).

## 32. Alturas remedidas, com números reais

Medidas contra um build fresco (`uv run python -m tools.console_gate build`,
disparado automaticamente por `spec_validation browser`), usando o próprio
`scroll-budget.spec.ts` committed — não um script descartável. Adicionei uma
linha `console.log` temporária dentro do laço por aba, copiei o arquivo para
`scratchpad/` antes de editar, rodei uma vez, e restaurei o arquivo original
a partir da cópia (confirmado por `diff`, idêntico) — nenhum vestígio da
medição sobrou no arquivo committed.

| Aba | Altura hoje | Altura antes desta sessão (medida provisória do despacho) | Orçamento |
|---|---|---|---|
| Posture | **1080px** | 1080px | 1620px (folga de 540px) |
| Rules & windows | **1309px** | 1367px | 1620px (folga de 311px) |
| Guardrails | **1080px** | 1080px | 1620px (folga de 540px) |

Saída real:
```
SLICE4-REMEASURE tab=posture height=1080
SLICE4-REMEASURE tab=rules-windows height=1309
SLICE4-REMEASURE tab=guardrails height=1080
```

**Leitura honesta dos números**: Rules & windows caiu de 1367px para 1309px
(58px a menos) — consistente com a remoção do painel de bounds e do grid de
três colunas dessa aba. Posture e Guardrails mediram **exatamente** 1080px
nas duas rodadas (antes e depois), inclusive Posture tendo ganhado um painel
inteiro novo (bounds) sem mudar de altura — isso é suspeito demais para ser
coincidência de conteúdo: 1080px é exatamente `CONFIG_SCREEN_VIEWPORT_HEIGHT_PX`,
então a leitura mais provável é que existe um piso de altura mínima (`min-h-screen`
ou equivalente, em algum wrapper do shell) dominando o `scrollHeight` medido
nas duas abas mais curtas — o conteúdo real de cada uma provavelmente mede
menos que 1080px, mascarado pelo piso. Não investiguei a fundo de onde vem
esse piso (fora do escopo desta fatia), mas registro a suspeita para quem
precisar de uma medição de conteúdo real, não de página.

Todas as três seguem dentro do orçamento de 1.5 viewport (1620px), confirmado
pelas asserções reais de `scroll-budget.spec.ts:120-134` — passaram nesta
mesma rodada (ver §34).

## 33. Testes colaterais corrigidos (unit)

Rodei `autonomy.test.tsx` isoladamente logo depois da mudança de produção —
**4 falhas reais, pela razão certa** (elemento/testid não encontrado no local
onde o teste ainda esperava, depois da mudança de aba), não erro de sintaxe
nem timeout. As quatro, e a correção de cada uma:

1. **`no rule recorded, but a freeze window is > still shows only one empty
   panel, and the bounds panel keeps its real content`** — misturava uma
   checagem de Rules & windows (`emptyPanels()` = 1) com uma checagem do
   painel de bounds (agora em Posture) no mesmo render. Dividido em dois
   testes (`autonomy.test.tsx:362-380`): um por aba, cada um com seu próprio
   `serveAutonomy`, seguindo o mesmo padrão que a Fatia 4 original já tinha
   estabelecido para separações análogas.
2. **`automated writes are stopped`**, os dois testes (`:383-424`) — o kill
   switch move com o painel de bounds; troquei `{ tab: 'rules-windows' }` por
   `{ tab: 'posture' }` nos dois, com um comentário explicando o porquê
   (`:388-389`).
3. **`a populated node > renders nothing as empty on Rules & windows`**
   (`:427-435`) — a checagem do heading "Bounds and level overrides" saiu
   daqui (não pertence mais a esta aba) e foi para o teste irmão de Posture
   (`:436-451`), que ganhou também `getAllByTestId('bound').length).toBeGreaterThan(0)`
   — mais forte que a checagem anterior (`emptyPanels()).toHaveLength(0)`
   sozinha), porque agora prova conteúdo real, não só ausência de vazio.

Além das quatro correções, **duas adições deliberadas**, para não deixar a
varredura mais fraca do que estava:

4. **`suppresses the bounds panel on Posture too, rather than repeating the
   same "nothing recorded"`** (`:227-239`) — a Fatia 4 original tinha um
   teste (`:206-225`, inalterado) provando que o painel de bounds NÃO
   aparece em Rules & windows quando regras e bounds estão vazios ao mesmo
   tempo — mas, depois da minha mudança, essa ausência em Rules & windows
   virou estrutural (o painel simplesmente não está mais nessa aba,
   independente de qualquer estado), então a checagem original passa por
   um motivo mais fraco do que antes — não prova mais supressão, só ausência
   estrutural. A propriedade real que o docstring do arquivo promete
   (`autonomy.test.tsx:26-28`, "the bounds panel drops out of the page only
   when it would otherwise repeat that same 'nothing recorded'") só é
   testável, depois da mudança, na aba onde o painel realmente vive —
   Posture. Este teste novo prova exatamente isso: nó resolvido, regras E
   bounds vazios, o heading continua ausente — supressão real, não
   estrutural.
5. **`the bounds panel's empty state, now that the panel reads on a
   different tab than the freeze editor`** (`:813-833`) — prova a correção
   de §28.2 (o `href` cross-tab), vermelho antes (`href` continha
   `#new-freeze` sem `tab=rules-windows`) e verde depois, e confirma por
   `document.getElementById('new-freeze')` que a âncora bare realmente não
   existe na página de Posture — o teste que, faltando, deixaria o bug do
   §28.2 sem prova nenhuma.

`behaviour.test.tsx` — uma falha, pela razão certa (`getAllByTestId('bound')`
resolvendo a zero elementos em `rules-windows`): corrigida trocando
`{ tab: 'rules-windows' }` por `{ tab: 'posture' }`
(`behaviour.test.tsx:161-163`), com comentário. `role-matrix.test.tsx`,
`node-scope.test.tsx`, `outage.test.tsx` — rodados, **zero falhas**, conferido
por leitura prévia que nenhum dos três referencia o painel de bounds, o
heading "Bounds and level overrides" ou os testids `autonomy-stopped`/
`release-stop`/`engage-stop` — as adaptações que a Fatia 4 original já tinha
feito neles eram sobre a tabela de regras (`autonomy-rule`) e sobre o
`config-editor` de Guardrails, nenhuma delas afetada por esta mudança.

`screens.test.tsx` — zero falhas, mas o comentário de `NEVER_EMPTY`
(`:91-98` antes, `:91-99` depois) foi atualizado para nomear explicitamente
que o painel de bounds também está preso a um nó resolvido, e por isso
continua ausente no cenário `empty` (sem nó) mesmo depois de ter ganhado um
lugar em Posture — a propriedade que o comentário original afirmava
("Posture's own content... is a later slice") continua verdadeira, mas
agora por duas razões (seletor de postura ainda não existe, E painel de
bounds gated por nó) em vez de uma só; deixar o comentário como estava teria
ficado impreciso, não errado.

**Contagem final**: `autonomy.test.tsx` foi de 23 para 26 testes (+2 novos,
+1 da divisão em dois do teste de freeze). `console_gate test` completo:
145 arquivos, **2408 testes, todos verdes** (era 2405 ao fim da Fatia 4
original) — bate: 2405 + 2 (novos) + 1 (divisão) = 2408.

## 34. Gates rodados nesta sessão

| Gate | Comando | Resultado |
|---|---|---|
| Typecheck (TS) | `uv run python -m tools.console_gate typecheck` | `$ tsc --noEmit` — exit 0, sem saída |
| Lint (TS/ESLint) | `uv run python -m tools.console_gate lint` | `$ eslint . && node scripts/check-css-literals.mjs` — exit 0, sem saída |
| Unit (vitest, com cobertura) | `uv run python -m tools.console_gate test` | `$ vitest run --coverage` — **145 arquivos, 2408 testes, todos passaram**, exit 0 (confirmado duas vezes, a segunda depois da correção de formatação de `autonomy.test.tsx`) |
| Cobertura | (mesma rodada acima) | Statements 94.37%, **Branches 90.42%** (piso 90.00%, folga real mas fina), Functions 92.07%, Lines 96.39% — todas acima do piso, Branches subiu 0.01pp em relação ao fim da Fatia 4 original |
| Prettier | `pnpm exec prettier --check` nos 6 arquivos tocados | Uma rodada pegou `autonomy.test.tsx` sem formatar (esquecido depois da última edição) — corrigido com `--write`, segunda rodada: `All matched files use Prettier code style!` |
| Acceptance (Playwright, `populated`, build fresco) | `uv run python -m tools.spec_validation browser --feature specs_v6/040-autonomy-tres-abas --test .../autonomy-tabs.acceptance.spec.ts` | **7 failed, 8 passed (15)** — ver §29 para o detalhe alegação a alegação |
| Scroll budget (Playwright, build fresco) | `uv run python -m tools.spec_validation browser ... --test .../scroll-budget.spec.ts` | **13 passed, 0 failed** — as 10 telas de página inteira mais as 3 abas desta rota, todas dentro do orçamento |
| Combinado — acceptance + scroll-budget + transversal-rules (build fresco) | `uv run python -m tools.spec_validation browser --test A --test B --test C` (a flag `--test` é repetível, não aceita múltiplos caminhos separados por espaço) | **7 failed, 7 skipped, 43 passed (57)** — os mesmos 7 falhados de sempre, nenhuma falha nova entre os três arquivos juntos |
| Transversal-rules isolado (`--no-build`, build já fresco) | `uv run python -m tools.spec_validation browser --test .../transversal-rules.spec.ts --no-build` | **22 passed, 7 skipped, 0 failed** — confirma que o achado §23.4(ii) da Fatia 4 original (a regra `value-column` passa vazia nesta rota) continua exatamente como estava, não piorou nem foi mascarado |

**Não rodado, e por quê**: `make verify` completo — o orquestrador é dono
dele; nenhum arquivo Python foi tocado nesta sessão (só `console/src`,
`console/tests`, e `specs_v6/`), então nenhum gate Python tinha superfície
nova para verificar. `console-visual-accept`/captura de baseline — não
tocado, nenhuma baseline foi capturada, aceita ou sobrescrita.

## 35. O que fica pendente, nomeado, não escondido

- **T009 continua sem marcar** (§28.4) — a metade "resumo de guardrails em
  Posture" do próprio texto da tarefa é T017, fora do escopo deste despacho.
- **O parágrafo-lead da aba Guardrails também viola a varredura de (g)**
  (§30) — achado novo, não corrigido, com a ambiguidade de leitura nomeada
  (FR-010 geral vs. FR-033 sancionando exatamente esse padrão para a seção
  de simulação). Quem tocar T015 ou T019 precisa decidir com as duas leituras
  na mesa.
- **O piso de altura de 1080px em Posture e Guardrails** (§32) — suspeita
  registrada (provável `min-h-screen` no shell mascarando a altura real de
  conteúdo dessas duas abas), não investigada a fundo, fora do escopo desta
  fatia.
- **Tudo que já estava fora de escopo por instrução explícita do despacho,
  ainda fora**: T012–T017 (postura, empty state, resumo de guardrails),
  T018–T023 salvo o que T009/T011 já tocam, T020, T026–T027 (o redirect
  `/autonomy`, confirmado de novo em §31, não corrigido), T031 (convergência
  da simulação), T036 (painel lateral do override). Nenhum foi tocado.
- **Os três sites de `Badge` com nível cru** (Fatia 1, §4) — seguem sem dono,
  nomeados de novo para não se perderem.
- **A ambiguidade de leitura do SC-008** (Fatia 1, §3.3) e **os dois achados
  de `transversal-rules.spec.ts` para T040** (Fatia 4 original, §23.4) —
  seguem exatamente como estavam; `transversal-rules.spec.ts` não foi
  editado nesta sessão, só lido e re-confirmado (§31, §34).

## 36. Arquivos alterados nesta sessão

- `console/src/surfaces/settings/autonomy.tsx` — o painel "Autonomy bounds"
  (com o kill switch aninhado) movido de `tab === 'rules-windows'` para
  `tab === 'posture'`; o grid de três colunas em Rules & windows simplificado
  para um único wrapper; `boundsEditorHref` corrigido para apontar
  cross-tab via `hrefForTab`. Ver §28.
- `console/tests/unit/surfaces/settings/autonomy.test.tsx` — quatro testes
  existentes corrigidos (aba trocada ou teste dividido em dois), dois testes
  novos adicionados. Ver §33.
- `console/tests/unit/surfaces/behaviour.test.tsx` — um teste corrigido
  (aba trocada). Ver §33.
- `console/tests/unit/surfaces/screens.test.tsx` — comentário de
  `NEVER_EMPTY` atualizado para precisão, nenhuma mudança de lógica. Ver §33.
- `console/tests/e2e/autonomy-tabs.acceptance.spec.ts` — docstring do topo
  reescrita; (g) e (f) viraram laços de três abas; (e) virou dois testes,
  um por aba, com uma função compartilhada; (i) corrigida para apontar à aba
  certa, achado por conta própria. Ver §29, §30.
- `console/tests/e2e/scroll-budget.spec.ts` — **tocado temporariamente e
  restaurado**: uma linha `console.log` foi adicionada, usada para capturar
  as três alturas reais (§32), depois removida — confirmado por `diff`
  contra uma cópia feita em `scratchpad/` antes da edição, idêntico ao
  original. Nenhuma mudança sobrou no arquivo.
- `specs_v6/040-autonomy-tres-abas/controle.md` — esta seção, acrescentada.
  Nenhuma caixa de `tasks.md` foi marcada nesta sessão — T009 permanece
  deliberadamente desmarcada (§28.4); T008/T010/T011, já marcadas pela
  sessão anterior, continuam corretas e não foram tocadas.

Nenhum outro arquivo foi tocado.

---

# Fatia 5 — a aba Posture, de ponta a ponta (T012–T017)

**Escopo desta fatia**: exatamente seis tarefas — T012, T013, T014, T015, T016,
T017 — a Fase 4 (User Story 2) de `tasks.md`. Uma aba, Posture, de ponta a
ponta. Não tocadas, por instrução explícita: a tabela da própria aba
Guardrails (T019), a edição inline (T020), a seção de simulação (T031), o
painel lateral do override (T036), o redirect aposentado (T026/T027). O
estado abaixo foi verificado contra o código atual da árvore de trabalho —
cada linha citada foi aberta e, onde fazia sentido, executada. Branch
`feat/v6-scope-and-settings`, em cima das Fatias 1–4 já commitadas
(`779d834`, `a35bc83`, `a9aff13`, `6a7793d`). Nada foi commitado, staged, nem
passou por `git add` nesta sessão — confirmado por `git status --porcelain`
ao final, que lista só os arquivos abaixo.

## 37. Tabela de estado

| Peça | Estado | Detalhe |
|---|---|---|
| T012 — teste de tela do seletor | **FEITO** | `console/tests/unit/surfaces/settings/autonomy.test.tsx`, describe `'Posture: the level selector, and nothing before it'` (`:897-1004`, quatro testes). Subtítulo: `:898-921`. A varredura de zero-parágrafo replicada da acceptance está em `firstParagraphBeforeControl()`, `:865-895`; exercitada em Posture (`:923-929`) e em Rules & windows (`:931-957`). Seletor com nomes de exibição + Save: `:959-975`. FR-015 (nível sem nome, nunca omitido): `:977-1003`. |
| T013 — teste de tela do empty state | **FEITO, prova só de unidade** | Mesmo arquivo, describe `'Posture: the empty state, with no rule recorded'` (`:1006-1031`, dois testes): a frase (propose-only, default seguro, não erro, nomeia Rules & windows) e o `href` do link cross-tab (`:1007-1022`); e a prova de ausência quando uma regra existe (`:1024-1030`, `serveScenario('populated')`). **Esta alegação não tem nenhuma prova de navegador nesta feature** — `autonomy-tabs.acceptance.spec.ts` não tem alegação nenhuma sobre `autonomy-posture-empty` (a lista (a)-(i) do próprio arquivo não inclui a frase "no rule recorded"), e não poderia ter uma que passasse por motivo certo: o mesmo achado que a Fatia 2 já tinha registrado para (h) vale aqui — todo nó que `populated` resolve carrega pelo menos uma regra, então `rulesEmpty` nunca é verdadeiro num render de navegador deste cenário, e o cartão `autonomy-posture-empty` nunca apareceria na tela para um teste de navegador examinar. A prova inteira desta alegação é o teste de unidade acima, onde eu controlo `rules: []` diretamente via `serveAutonomy`. Nomeado aqui com todas as letras, não descoberto tarde: é exatamente o tipo de alegação que só pode ser provada onde os props são controláveis. |
| T014 — implementar a aba Posture | **FEITO** | `console/src/surfaces/posture-editor.tsx` (novo, `PostureEditor`) + `console/src/surfaces/settings/autonomy.tsx:737-782` (o cartão, gated `writable && nodeId !== ''`) e `:391-399` (o subtítulo). Ver §38 para a decisão de design do caminho de escrita. |
| T015 — remover os três parágrafos, reescrever no ponto de uso | **FEITO** | `autonomy-glossary` apagado. Os três conceitos reaparecem em `autonomy-rule-note` (`autonomy.tsx:610-616`, Rules & windows, depois do editor), `autonomy-bound-note` (`:911-915`, Posture, depois do painel de bounds — gated só por `showBounds`, sempre visível quando o nó resolve) e `autonomy-override-note` (`:994-999`, Posture, depois do editor de override — gated por `writable && nodeId !== ''`, junto do editor que comenta). Os dois catálogos no mesmo commit — nenhuma chave nova precisou ser criada para os três textos, que já existiam (`autonomy.glossary.rule/bound/override`); só o *local* de uso mudou. Ver §39 para o motivo de `autonomy-footer`/`autonomy-dry-run` também terem mudado de posição, sem o que (g) não fecharia. |
| T016 — o CTA que mentia | **FEITO** | `autonomy.empty.action` apagado dos dois catálogos (`en.ts`, `pt-BR.ts`) — não só deixado de referenciar. Três chaves novas, uma por destino: `autonomy.cta.createRule` (`autonomy.tsx:438,511`), `autonomy.cta.recordBound` (`:818`), `autonomy.cta.grantOverride` (`:931`). Confirmado por grep: zero ocorrências de `autonomy.empty.action` em `autonomy.tsx`, e pela própria alegação (h) do acceptance, verde (§40). |
| T017 — resumo de guardrails em Posture | **FEITO** | `autonomy.tsx:783-802`, `data-testid="posture-guardrails-summary"`, usando `guardrailRows` de `./guardrail-values` (renomeado `postureGuardrailRows` na importação — ver §38.3, a colisão de nome que isso evitou), não uma terceira cópia. Sem controle de edição. Confirmado pela alegação (e) `tab=posture` do acceptance, verde (§40). |
| T009 — a reorganização em três abas | **FEITO, marcada nesta fatia** | A metade que faltava ("resumo de guardrails em Posture") está feita agora (T017 acima); a outra metade (postura em Posture) também — o seletor é T014. Ver §38.4 para a leitura das duas instruções em tensão que a Fatia 4 tinha registrado (§23.1) sem decidir, e por que decidi pela leitura que exige as duas metades. |

## 38. A decisão de design: como a escrita de Posture compõe com a lista de regras que Rules & windows possui

### 38.1 O problema, exatamente como a Fatia 3 (§15.4) já o tinha nomeado

Não existe `policies.autonomy.level`. A postura vigente é o nível da regra de
escopo `deployment` dentro de `policies.autonomy.rules` — um caminho que o
mapa `AUTONOMY_TAB_FIELDS` (`autonomy-tabs.ts:102-128`) atribui inteiro a
Rules & windows. T014 pede um seletor com Save em Posture que, ao salvar,
tem que escrever nessa mesma entrada sem se tornar uma segunda posse do
campo — a pergunta que a Fatia 3 deixou para esta fatia decidir.

### 38.2 A decisão: uma operação de escrita restrita, não um segundo editor genérico

`console/src/surfaces/posture-editor.tsx` (`PostureEditor`, `rulesWithPosture`,
linhas 78-95) escreve exatamente uma linha do array `rules` — a que tem
`scope.kind === 'deployment'` — e carrega todas as outras (de qualquer
escopo: time, capacidade, recurso…) através, com seus registros inalterados
(`{...rule, level}` só na linha correspondente; as demais devolvidas
verbatim). Quando nenhuma regra de escopo `deployment` existe ainda, uma é
criada (`{ scope: { kind: 'deployment' }, level, risk_bound: riskBound }`),
espelhando `FIRST_RULE` (`autonomy.tsx:104-115`) — salvar a postura *é*
criar a primeira regra, a mesma leitura que `FIRST_RULE` já sustenta para o
editor completo.

`freezes`/`budgets` são carregados inalterados no mesmo payload
(`posture-editor.tsx:126-131`) — a mesma disciplina que o comentário de
`EditableBound` em `autonomy-editor.tsx:49-58` já documenta e que
`AutonomyEditor.document` (`autonomy-editor.tsx:387-397`) já pratica: uma
gravação que omitisse essas chaves apagaria, em silêncio, todo congelamento
e todo teto deste nó, porque o caminho de escrita trata uma chave ausente
como lista vazia. Confirmado por leitura de `console/src/app/api/autonomy/route.ts:37`
(`save: { path: '', method: 'PUT' }`) — um `PUT` com o documento completo,
não um PATCH parcial, então a disciplina de "carregar o resto inalterado"
não é opcional.

**Resultado**: dois controles diferentes (o seletor por-linha de
`AutonomyEditor`, em Rules & windows, e o seletor único de `PostureEditor`,
em Posture) podem escrever no mesmo array, cada um restrito à sua própria
fatia dele — o seletor de Rules & windows toca qualquer linha; o de Posture
só a de escopo `deployment`. Não há dois "donos" do campo — `AUTONOMY_TAB_FIELDS`
continua correto ao atribuir `policies.autonomy.rules` inteiro a
Rules & windows (FR-046/047/048, a paridade de campo), porque "editável em
mais de um controle" não é o mesmo que "possuído por mais de uma aba": o
próprio comentário do mapa já sancionava essa forma, mas para o resumo
*somente leitura* de guardrails; esta fatia estende a mesma forma a uma
*segunda operação de escrita*, restrita — a distinção que a Fatia 3 já tinha
antecipado como a saída ("uma opção é a gravação de Posture ser uma operação
deliberadamente restrita à entrada de escopo `deployment`... o que a torna
uma segunda operação de escrita, não uma segunda leitura acidental").

### 38.3 A segunda decisão: sem gate de preview

`AutonomyEditor.save()` exige que o documento exato prestes a ser enviado já
tenha sido pré-visualizado (`current = answer !== null && serialised ===
previewedDocument`, `autonomy-editor.tsx:404` e o botão `save-autonomy` só
aparece dentro do bloco `answer === null || !current ? null : (...)`). É uma
trava real, documentada no próprio docstring do arquivo como a razão de ser
do componente ("A confirmation dialogue would ask a question with no
evidence in front of it").

`PostureEditor.save()` **não tem essa trava** — chama `operation: 'save'`
direto, sem passar por `operation: 'preview'` primeiro. Decisão deliberada,
pelas razões abaixo, não uma omissão:

- **FR-014** ("A aba Posture DEVE oferecer uma ação explícita de salvar a
  postura") não menciona pré-visualização — ao contrário de FR-035, que
  exige exatamente essa trava, mas está no bloco de FRs "Aba Rules &
  windows" (FR-030 a FR-037), não no de "Aba Posture" (FR-013 a FR-020). A
  fronteira que a própria especificação desenha entre os dois blocos é o que
  decide: a trava é letra de Rules & windows, não de Posture.
- **O mockup** (`specs_v6/mockups/settings-v6.html`, M2) desenha só
  seletor+"Save posture" — nenhum botão de preview, nenhuma seção de
  explicação prévia — para o cartão inteiro. Isso é consistente com FR-014,
  não um acidente de recorte estático.
- **A API não exige a sequência** — confirmado por leitura de
  `console/src/app/api/autonomy/route.ts`: `save` é uma entrada própria da
  tabela fechada `OPERATIONS`, aceita isoladamente; o gate de preview em
  `AutonomyEditor` é inteiramente do lado do cliente (um `state` de React
  controlando se o botão aparece), não uma sequência que o servidor exige.
- **A própria tese da feature** é retirar fricção da decisão mais
  consequente da tela sem duas etapas — três parágrafos e um CTA que mentia
  viraram um seletor e um botão; reintroduzir um segundo passo de
  pré-visualização para exatamente este controle teria devolvido parte da
  fricção que a spec pede para tirar, para uma operação que já é
  estruturalmente mais estreita (só a linha de escopo `deployment`) que
  qualquer coisa que `AutonomyEditor` deixa alguém tocar.

**Risco nomeado, não escondido**: os dois controles escrevem no mesmo campo
com disciplinas de segurança diferentes — um exige ver o efeito simulado
antes de salvar, o outro não. Não vejo isso como uma inconsistência
acidental (a diferença de FR e a diferença de mockup são reais, não
inventadas por mim), mas registro para quem revisar depois: se a leitura
correta acabar sendo "toda gravação em `rules` deveria exigir preview",
`PostureEditor` precisaria ganhar o mesmo mecanismo — um `preview()` antes
de `save()`, na mesma forma que `AutonomyEditor` já tem, reutilizável quase
sem mudança porque o formato do documento já é idêntico.

### 38.4 A ambiguidade da Fatia 4 (§23.1), resolvida

A Fatia 4 registrou duas leituras possíveis do texto de T009 sem decidir
entre elas: "resumo de guardrails em Posture" poderia significar (a) que
T009 já deveria ter movido/duplicado a tabela de guardrails para Posture, ou
(b) que essa metade ficava explicitamente para T017. Nesta fatia, T017
construiu o resumo — então a pergunta que restava era só qual caixa marcar
quando isso acontecesse. Resposta: marco T009 agora, porque o próprio texto
da tarefa ("postura e resumo de guardrails em Posture") descreve um estado
final que só ficou verdadeiro quando as duas metades (T014 e T017)
existiram — a tarefa nunca foi "fazer metade e marcar", era "o estado
descrito" ficar verdadeiro. Isso não contradiz a decisão da Fatia 4 de não
marcar T009 então — naquele momento a caixa estava genuinamente incompleta.

## 39. Por que `autonomy-footer`/`autonomy-dry-run` mudaram de posição, e o que isso quase escondeu

Ao apagar `autonomy-glossary`, rodei a alegação (g) para `tab=rules-windows`
contra o build fresco e ela **continuou vermelha** — não pela ausência da
correção, mas por um motivo novo: `autonomy-footer` ("Absence of a rule
resolves to propose-only.", `autonomy.tsx`, antes desta fatia entre a
tabela de regras e `AutonomyEditor`) é um `<p>` que já sentava *antes* do
primeiro controle real (a tabela de regras não tem nenhum — só `<td>`s; o
primeiro `<SELECT>` só aparece dentro de `AutonomyEditor`, mais abaixo).
Isso estava mascarado desde sempre pelo próprio `autonomy-glossary`, cujo
parágrafo era sempre encontrado primeiro — apagar o mascarador expôs o
segundo bloqueador, exatamente o "verde por acidente, vermelho pelo motivo
errado quando o acidente some" que este projeto já viu antes (Fatia 2, a
correção de (g) contra o `<nav>` injetado).

**A correção**: `autonomy-footer` e `autonomy-dry-run` foram movidos para
depois do bloco `AutonomyEditor` (`autonomy.tsx:601-620`), não apagados —
`AutonomyEditor` (quando `writable && nodeId !== ''`) já garante um
`<SELECT>` real antes deles, e a walk retorna assim que encontra o primeiro
controle, então qualquer parágrafo depois dele deixa de importar para esta
regra. `autonomy-rule-note` (o texto do glossário reescrito) foi para o
mesmo lugar — "no controle onde é usado" lido aqui como "onde uma regra é
de fato editada", não "acima da tabela só de leitura", porque a tabela não
tem controle nenhum para a frase vir depois de.

**Achado nomeado, não escondido, encontrado pelo meu próprio teste**: ao
escrever o teste de "zero parágrafo em Rules & windows" com `EMPTY_POLICY`
(`rules: []`), a asserção falhou de novo — desta vez porque, com
`rulesEmpty` verdadeiro, o painel de regras entra em `state="empty"` e
`EmptyState` (`components/state.tsx:65-71`) desenha `heading`, depois
`body` (um `<p>`), depois a ação — nessa ordem, sempre, por construção do
próprio componente. Isso significa que a propriedade "nenhum parágrafo
antes do primeiro controle" **não vale hoje** em Rules & windows quando
`rulesEmpty` é verdadeiro — é uma propriedade de `EmptyState`, não algo que
esta fatia introduziu ou que FR-010 parece mirar (a letra fala de "parágrafo
conceitual", e o corpo de um empty state é exatamente a explicação exigida
do que falta, não prosa de glossário solta). Não corrigi isso — não é meu
para corrigir e não está coberto por nenhum gate real: o acceptance roda só
contra `populated`, onde `rulesEmpty` é falso para todo nó (a mesma
descoberta que a Fatia 2 já tinha registrado sobre a alegação (h)). Ajustei
meu próprio teste unitário para exercitar o cenário que o gate real
exercita (um nó com pelo menos uma regra), documentando o porquê no
comentário do teste (`autonomy.test.tsx:932-939`), em vez de forçar uma
alegação contra um ramo que ninguém pede para estar correto ainda.

## 40. O vermelho e o verde do acceptance da feature

Build fresco (`uv run python -m tools.console_gate build`), depois:

```
uv run python -m tools.spec_validation browser \
  --feature specs_v6/040-autonomy-tres-abas \
  --test console/tests/e2e/autonomy-tabs.acceptance.spec.ts \
  --test console/tests/e2e/scroll-budget.spec.ts \
  --test console/tests/e2e/transversal-rules.spec.ts \
  --no-build
```

Resultado: **4 failed, 7 skipped, 46 passed (57 total)**, rodado duas vezes
(a segunda para capturar a saída completa em
`scratchpad/slice5-run.log`), as duas rodadas concordam.

**Contra a baseline que o despacho registrou** (7 failed / 43 passed / 7
skipped): as três alegações nomeadas pelo despacho como minhas viraram
verdes —

- `tab=rules-windows` da alegação (g) ("no paragraph sits between the title
  and the first control") — verde.
- (h) "the retired 'Look at the configuration' CTA label is gone from this
  route" — verde.
- `tab=posture` da alegação (e) ("no empty cell in the Value column, in
  Posture's read-only guardrails summary") — verde.

As quatro que continuam vermelhas, e a quem pertencem, confirmado pela
mensagem real de cada uma (não por suposição):

1. `tab=guardrails` de (g) — `"a paragraph sits before the first control:
   \"Masking, secret detection and approval — edited here...\""` —
   `settings.autonomy.guardrails.lead`, nomeado por T019 em `tasks.md`
   ("Inclui remover o parágrafo de abertura da aba"). Não toquei.
2. `tab=posture` de (f) — `"the override editor is visible in the page
   body"` — o painel de override continua no corpo até T036. Não toquei.
3. "a header button opens the override in a side panel" — o botão não
   existe ainda, T036. Não toquei.
4. (i) — `"getByTestId('autonomy-simulation')... element(s) not found"` — a
   seção de simulação não existe ainda, T031. Não toquei.

`4 failed + 46 passed + 7 skipped = 57`; `7 - 3 = 4`, `43 + 3 = 46` — bate
exatamente com a aritmética esperada.

**Orçamento de rolagem por aba, dentro do mesmo run**: as três asserções de
`scroll-budget.spec.ts:120-134` (`tab=posture`, `tab=rules-windows`,
`tab=guardrails`) passaram. Alturas reais, medidas à parte (ver §41).

## 41. Alturas remedidas

Medidas com o mesmo método das fatias anteriores: uma linha `console.log`
temporária em `console/tests/e2e/scroll-budget.spec.ts` (cópia feita em
`scratchpad/` antes de editar, restaurada depois, `diff` confirmando
idêntico ao original — `git status --porcelain` para este arquivo, vazio,
ao final).

| Aba | Altura antes desta fatia (Fatia 4, repetida) | Altura agora | Orçamento |
|---|---|---|---|
| Posture | 1080px | **1458px** | 1620px (folga de 162px) |
| Rules & windows | 1309px | **1211px** | 1620px (folga de 409px) |
| Guardrails | 1080px | **1080px** (não tocada) | 1620px (folga de 540px) |

Saída real:
```
SLICE5-REMEASURE tab=posture height=1458
SLICE5-REMEASURE tab=rules-windows height=1211
SLICE5-REMEASURE tab=guardrails height=1080
```

**Leitura honesta**: Posture cresceu 378px — o cartão de postura e o resumo
de guardrails que esta fatia adicionou, mais o piso de altura de 1080px que
a Fatia 4 já suspeitava (§32) mas não sobrevive mais sozinho como explicação
única, porque agora há conteúdo real de sobra além dele. Rules & windows
encolheu 98px — a saída do bloco `autonomy-glossary` (3 parágrafos) supera a
entrada de `autonomy-rule-note` (1 parágrafo) e o reposicionamento de
`autonomy-footer`/`autonomy-dry-run`, que não mudam de tamanho, só de
lugar. As três seguem folgadas dentro de 1.5 viewport.

## 42. Testes colaterais — zero corrigidos, porque zero quebraram

`uv run python -m tools.console_gate test` (`vitest run --coverage`) rodado
duas vezes ao longo desta fatia, a última depois de todas as mudanças:
**145 arquivos, 2417 testes, todos passaram, exit 0**. Nenhum dos arquivos
que as Fatias 4/4-reparo tiveram que ajustar (`node-scope.test.tsx`,
`outage.test.tsx`, `role-matrix.test.tsx`, `behaviour.test.tsx`,
`screens.test.tsx`) precisou de qualquer mudança nesta fatia — confirmado
pela contagem cheia, não por suposição, e por `git status --porcelain` não
listar nenhum deles.

**`screens.test.tsx` — verificado, não tocado, por uma razão real, não por
falta de checagem**: a Fatia 4 tinha deixado `'autonomy'` em `NEVER_EMPTY`
com um comentário dizendo que valeria a pena revisitar "quando o conteúdo de
Posture (T014) existir". T014 existe agora — revisitei. A conclusão é que
`'autonomy'` continua corretamente excluído: o cenário `empty` que esse
sweep roda (`serveScenario('empty')`) não resolve nenhum nó, e tanto o
cartão de postura (`writable && nodeId !== ''`) quanto a tabela do resumo de
guardrails (`nodeId === '' ? null : ...`) ficam ausentes nesse estado — só o
título "Guardrails em vigor" sobra, sem tabela nenhuma, o mesmo padrão que a
aba Guardrails já tinha antes desta fatia para o mesmo cenário. Não editei o
comentário: ele já dizia "worth revisiting", não "will flip", e a revisita
confirma a exclusão, não a invalida. Não há nenhuma linha de teste falsa ali
para corrigir.

**Cobertura**: Statements 93.91%, **Branches 90.15%** (piso 90.00% —
folga real mas fina, como o despacho avisou que aconteceria), Functions
91.6%, Lines 95.9%. Todas as quatro acima do piso; `exit 0` confirmado
explicitamente.

## 43. Gates rodados nesta fatia

| Gate | Comando | Resultado |
|---|---|---|
| Typecheck (TS) | `uv run python -m tools.console_gate typecheck` | `$ tsc --noEmit` — exit 0, sem saída |
| Lint (TS/ESLint + CSS literals) | `uv run python -m tools.console_gate lint` | `$ eslint . && node scripts/check-css-literals.mjs` — exit 0, sem saída |
| Unit (vitest, com cobertura) | `uv run python -m tools.console_gate test` | **145 arquivos, 2417 testes, todos passaram**, exit 0 (confirmado com `echo $?` explícito) |
| Catálogo i18n, isolado | `pnpm exec vitest run tests/unit/i18n/catalogue.test.ts --pool=forks` | 1 arquivo, 11 testes, todos passaram — paridade das chaves novas e das removidas (`autonomy.empty.action`) confirmada nos dois catálogos |
| Prettier | `pnpm exec prettier --check` nos 6 arquivos tocados | Duas rodadas pegaram formatação a corrigir (`pt-BR.ts` — quebra de linha de uma string longa; `autonomy.test.tsx` — idem), `--write` aplicado, segunda checagem: `All matched files use Prettier code style!` |
| Build do console | `uv run python -m tools.console_gate build` | Manifesto de rotas completo, incluindo `/settings/autonomy-guardrails`, sem erro — `.next/standalone/server.js` fresco |
| Acceptance + scroll-budget + transversal-rules (Playwright, `populated`, build fresco) | `uv run python -m tools.spec_validation browser --feature specs_v6/040-autonomy-tres-abas --test .../autonomy-tabs.acceptance.spec.ts --test .../scroll-budget.spec.ts --test .../transversal-rules.spec.ts --no-build` | **4 failed, 7 skipped, 46 passed (57)** — rodado duas vezes, mesmo resultado; detalhe alegação a alegação em §40 |
| Alturas por aba | Medição descartável via `console.log` temporário em `scroll-budget.spec.ts`, restaurado depois (`diff` confirmando idêntico) | posture 1458px, rules-windows 1211px, guardrails 1080px — ver §41 |

**Não rodado, e por quê**: `make verify` completo, `console-visual-accept`,
`console-e2e` completo — o orquestrador é dono deles; nenhuma baseline
visual foi capturada, aceita ou sobrescrita. Nenhum gate Python
(`pytest`, `check-constants`, `check-imports`, `check-protocols`,
`check-deps`) — confirmado por `git status --porcelain`, nenhum arquivo
Python foi tocado nesta fatia (só `console/src`, `console/tests`,
`specs_v6/`), então nenhum desses gates tem superfície nova para verificar.

## 44. O que fica pendente, nomeado, não escondido

- **A trava de preview, ausente em `PostureEditor`** (§38.3) — decisão
  deliberada com razões escritas, mas nomeada como risco: se a leitura
  correta for "toda gravação em `rules` exige preview", este controle
  precisa ganhar o mesmo mecanismo que `AutonomyEditor` já tem.
- **O fluxo de gravação de `PostureEditor` não tem teste de interação
  automatizado** — a estrutura, os rótulos, as opções e o valor selecionado
  do controle estão testados (T012); o ciclo real de clicar Save, disparar o
  `fetch`, e reagir à resposta (`posture-saved`/`posture-failure`) não tem
  um teste próprio nesta fatia — o mesmo padrão de `AutonomyEditor`, que
  também não é testado neste arquivo (o próprio docstring do arquivo aponta
  para `autonomy-editor.test.tsx` para essa cobertura), mas não existe um
  `posture-editor.test.tsx` equivalente ainda. Nomeado, não escondido.
- **O parágrafo-lead da aba Guardrails continua quebrando (g) para
  `tab=guardrails`** (§40, item 1) — confirmado ainda vermelho, por
  instrução explícita não corrigido (T019).
- **A propriedade "zero parágrafo antes do controle" não vale em Rules &
  windows quando `rulesEmpty` é verdadeiro** (§39) — uma propriedade
  intrínseca de `EmptyState` (heading, depois body, depois ação, sempre
  nessa ordem), não algo que esta fatia introduziu; não exercitada pelo
  gate real (`populated` nunca tem `rulesEmpty` verdadeiro em nó nenhum) e
  não corrigida — nomeada para quem algum dia testar esse ramo.
- **(f)/(i)/(g)-guardrails continuam vermelhas** — T036, T031, T019
  respectivamente, confirmado pela mensagem exata de cada uma (§40), não
  tocadas.
- **A duplicação `GUARDRAIL_FIELD_LIST` (inline) vs. `GUARDRAIL_FIELDS`
  (`guardrail-values.ts`) continua** — minha nova tabela em Posture consome
  o módulo compartilhado (`postureGuardrailRows`, alias para evitar colisão
  de nome com a variável local `guardrailRows` que a aba Guardrails já
  tinha); a aba Guardrails em si continua com sua própria cópia inline,
  intocada — decisão deliberada de não entrar em "a tabela da própria aba
  Guardrails" (T019), com a mesma ressalva que a Fatia 3 (§16) já tinha
  registrado.
- **Os três sites de `Badge` com nível cru** (Fatia 1, §4) — seguem sem
  dono, nomeados de novo.
- **A ambiguidade de leitura do SC-008** (Fatia 1, §3.3) — segue não
  resolvida, T040 é quem decide.
- **O bug do redirect `/autonomy`** (Fatia 4, §23.5/§31) — confirmado ainda
  presente por leitura (`console/src/app/(shell)/autonomy/page.tsx` não foi
  tocado nesta fatia), não corrigido, T026/T027.

## 45. Arquivos alterados — Fatia 5

- `console/src/shell/area.tsx` — `SettingsPageHeaderProps` ganhou um
  `context?: string` opcional; `SettingsPageHeader` usa-o no lugar de
  `message(locale, page.context)` quando presente, com o mesmo default de
  antes quando ausente. Nenhum dos outros 9 chamadores passa a prop nova —
  confirmado por leitura antes de editar (`grep -rn "SettingsPageHeader"` já
  tinha sido rodado pela exploração inicial) e por `tsc`/`eslint` limpos
  depois.
- `console/src/surfaces/posture-editor.tsx` — novo. `PostureEditor`,
  `PostureRule`, `PostureEditorLabels`, `PostureEditorProps`,
  `rulesWithPosture`, `scopeKindOf`.
- `console/src/surfaces/settings/autonomy.tsx` — `postureLevel`/
  `selectableLevels` (derivados de `rules`), `subtitle` (passado a
  `SettingsPageHeader`), o cartão `posture-card` (T014), o resumo
  `posture-guardrails-summary` (T017), a remoção de `autonomy-glossary` e o
  reposicionamento de `autonomy-footer`/`autonomy-dry-run` mais o novo
  `autonomy-rule-note` (T015, Rules & windows), `autonomy-bound-note` e
  `autonomy-override-note` (T015, Posture), e as três chaves de CTA novas
  substituindo `autonomy.empty.action` nos quatro sites (T016). Ver §37-40.
- `console/src/i18n/en.ts` / `pt-BR.ts` — chaves novas: `autonomy.subtitle`,
  `autonomy.posture.title`, `autonomy.posture.save`,
  `autonomy.posture.empty.scopeLead`, `autonomy.posture.guardrails.title`,
  `autonomy.cta.createRule`, `autonomy.cta.recordBound`,
  `autonomy.cta.grantOverride` — nos dois catálogos, no mesmo commit.
  `autonomy.empty.action` apagada dos dois (não só deixada de referenciar).
- `console/tests/unit/surfaces/settings/autonomy.test.tsx` — o describe
  antigo `'the vocabulary this screen assumes an operator already has'`
  reescrito (três testes: ausência do glossário nas duas abas, presença de
  `autonomy-rule-note`, presença de `autonomy-bound-note`/
  `autonomy-override-note`); dois describes novos — `'Posture: the level
  selector, and nothing before it'` (quatro testes, T012) e `'Posture: the
  empty state, with no rule recorded'` (dois testes, T013); `within`
  importado de `@testing-library/react`; o helper `firstParagraphBeforeControl()`,
  replicando a varredura do acceptance.
- `specs_v6/040-autonomy-tres-abas/tasks.md` — T009, T012, T013, T014, T015,
  T016, T017 marcadas.
- `specs_v6/040-autonomy-tres-abas/controle.md` — esta seção, acrescentada.

Nenhum outro arquivo foi tocado. `console/tests/e2e/scroll-budget.spec.ts`
foi editado temporariamente para a medição do §41 e restaurado byte a byte
(`diff` contra a cópia em `scratchpad/`, idêntico; `git status --porcelain`
vazio para este arquivo ao final). `console/tests/e2e/autonomy-tabs.acceptance.spec.ts`
e `console/tests/e2e/transversal-rules.spec.ts` foram lidos e rodados, não
editados.

---

# Fatia 6 — a aba Guardrails, interrompida antes da confirmação final (T018–T023)

**Status desta seção: escrita sob interrupção deliberada do orquestrador**, a
meio da rodada final de verificação. Tudo abaixo é o que a árvore de trabalho
prova e o que eu de fato observei rodar — nada foi marcado em `tasks.md` que eu
não tenha visto passar num run que ainda vale. Branch
`feat/v6-scope-and-settings`, em cima das Fatias 1–5 já commitadas (`779d834`,
`a35bc83`, `a9aff13`, `6a7793d`, `1db71f6`). Nada foi commitado, staged, nem
passou por `git add` nesta sessão. Nenhum arquivo fora de `console/` e deste
`controle.md` foi tocado.

**Escopo desta fatia**: T018–T023 (Fase 5 / User Story 3 — a aba Guardrails).
Não tocados: a seção de simulação (T031), o painel lateral do override (T036),
o redirect de âncora (T026/T027), o contrato de paridade (T024/T025) — todos de
fatias futuras, confirmado por leitura antes de começar.

**Nenhuma caixa de T018 a T023 foi marcada em `tasks.md` nesta fatia.** Não
porque nada funcione — a implementação está feita e a maior parte tem teste
passando —, mas porque a interrupção caiu exatamente entre duas edições finais
de arquivos de teste e a rodada de confirmação que provaria o estado final de
cada um. A seção 6.7 abaixo lista, tarefa por tarefa, exatamente o que já está
provado e o que falta só *confirmar* (não implementar) na próxima sessão — o
trabalho que resta é rodar dois comandos, não escrever código.

## 6.1 O que foi implementado, arquivo por arquivo

### `console/src/surfaces/settings/guardrail-table.tsx` (novo, 299 linhas)

O componente `GuardrailTable` — a tabela da própria aba Guardrails, agora
editável na própria linha, em vez de uma tabela só-leitura mais um
`ConfigEditor` genérico separado embaixo. Decisão de design registrada no
próprio docstring do arquivo (linhas 8–37):

- Mantém o **mesmo contrato de DOM/testids** que `EffectiveFieldsTable`
  (`design/resolution-preview.tsx`) já usa —
  `data-testid="effective-fields"`/`"effective-field"`/`"effective-field-origin"`
  — deliberadamente, para que `transversal-rules.spec.ts`'s
  `configurationValueCells()` e o teste pré-existente de "shows masking,
  guardrail and approval fields..." (que já usava esses testids antes desta
  fatia) continuem enxergando as linhas sem qualquer mudança.
- Reproduz a **mesma garantia de lançar exceção** em valor/origem vazios
  (linhas 121–137) — a mesma condição, sobre o mesmo `rows` — em vez de
  contornar a garantia que `EffectiveFieldsTable` já tinha.
- Estado fechado (sem edição): a célula Value mostra **texto puro**
  (`row.value`), nunca só um controle — um `<Switch>`/`<Select>` sozinho não
  carrega texto que `innerText()` leia, e colocar um ali teria reintroduzido o
  próprio defeito P1-4 que esta feature existe para fechar. O botão "Edit"
  (`data-testid="guardrail-edit"`) é uma affordance **ao lado** do texto, não
  uma substituição dele, e só aparece quando `writable` é verdadeiro e o campo
  está no catálogo (`isEditable`, linha 100).
- Estado aberto (editando uma linha): usa `Control` (reexportado de
  `../preview`, ver §6.1 abaixo) — o **mesmo** despachante por tipo que
  `ConfigEditor` já usa (`Select` para conjunto fechado, `Switch` para
  booleano, `Input` para o resto) — não uma segunda implementação.
- **Gravação**: `POST /api/config` (linha ~160), o mesmo `SAVE_ENDPOINT` que
  `ConfigEditor` já usa — **não** `console/src/app/api/autonomy/route.ts`. Ver
  §6.3 para a evidência completa de por que esse é o caminho certo e por que a
  preocupação do despacho sobre "PUT de documento inteiro que apaga uma lista
  ausente" não se aplica aqui.
- Depois de um save bem-sucedido: `router.refresh()` (linha 187) — recarrega
  os dados do Server Component para que "Set at" passe a dizer "definido
  aqui" de verdade, em vez de um valor cliente que nunca foi confirmado pelo
  deployment.

### `console/src/surfaces/preview.tsx` (modificado)

Quatro identificadores que já existiam, privados, ganharam `export`:
`SAVE_ENDPOINT` (:46), `EDITABLE_TYPES` (:49), `typed` (:284, com um parágrafo
novo no docstring explicando por quê), `Control`/`ControlProps` (:938, :956,
idem). **Nenhuma lógica mudou** — é aditivo, e os quatro continuam sendo usados
exatamente como antes por `ConfigEditor`. A razão de exportar em vez de
duplicar: `guardrail-table.tsx` precisa do mesmo despacho de controle por tipo
e da mesma conversão de string-para-tipo-do-schema que `ConfigEditor` já tinha
resolvido — duplicar teria sido exatamente o "duas cópias da mesma regra" que
o `guardrail-values.ts` da Fatia 3 já registrou como o jeito de elas
divergirem.

### `console/src/surfaces/settings/autonomy.tsx` (modificado, líquido -19 linhas)

- **`GUARDRAIL_FIELD_LIST` apagado por inteiro** (era um bloco de ~37 linhas,
  cópia inline de seis campos). Confirmado por grep: zero ocorrências restantes
  do identificador no arquivo.
- **O alias `postureGuardrailRows` removido.** O import agora é
  `import { GUARDRAIL_FIELDS, guardrailRows } from './guardrail-values'` (:42)
  — um nome só, usado nos dois lugares (resumo de Posture, tabela da própria
  aba Guardrails), exatamente a pergunta que o despacho fez ("consider whether
  that alias is still earning its keep") — não estava, e saiu.
- **`guardrailEditable` redefinido** (:340–344): agora exclui os seis
  caminhos escalares que `GUARDRAIL_FIELDS` nomeia, mantendo só o que casa com
  os três prefixos de política **e não é um dos seis escalares** — na prática,
  os três campos-array (`masking.custom_patterns`,
  `guardrails.disabled_rules`, `approvals.autonomous_capabilities`) mais
  qualquer outro campo futuro sob esses prefixos que não seja um dos seis
  nomeados. Ver §6.2.
- **O parágrafo de abertura (`settings.autonomy.guardrails.lead`) saiu de
  antes da tabela** — a `<GuardrailTable>` (:627) ocupa o lugar onde a
  `<EffectiveFieldsTable>` só-leitura estava. A **mesma chave de i18n**, sem
  mudança de texto, agora é renderizada num `<p data-testid="guardrail-note">`
  (:700) **depois** do bloco inteiro (tabela + `ConfigEditor` estreito) —
  seguindo o mesmo padrão "frase depois do controle que ela explica" que a
  Fatia 5 já aplicou a `autonomy-rule-note`/`autonomy-bound-note`/
  `autonomy-override-note`. Não criei uma chave nova para isso — o texto não
  mudou, só o lugar.

### `console/src/i18n/en.ts` / `pt-BR.ts`

Duas chaves novas em cada um: `settings.autonomy.guardrails.edit` ("Edit" /
"Editar") e `settings.autonomy.guardrails.cancel` ("Cancel" / "Cancelar").
Nenhuma chave removida, nenhuma renomeada.

### `console/tests/unit/surfaces/settings/guardrail-table.test.tsx` (novo, 291 linhas, 11 testes)

Testa `GuardrailTable` isoladamente (sem subir `AutonomyScreen` inteira):
leitura (Setting/Value/Set at, os dois testes de exceção em valor/origem
vazios — o mesmo padrão que `resolution-preview.test.tsx:323-357` já usa para
`EffectiveFieldsTable`, espelhado aqui de propósito), quem ganha o botão Edit
(escritor/leitor/campo fora do catálogo), e o fluxo de edição completo:
abrir → mudar o `Switch` → Save → corpo exato do `POST /api/config` → 
`router.refresh()` chamado → Cancel sem gravação → recusa do deployment →
falha de rede → um `Select` para um conjunto fechado. Ver §6.4 para o estado
exato de confirmação de cada um.

### `console/tests/unit/surfaces/settings/autonomy.test.tsx` (modificado, +212 linhas líquidas)

- Mock de `next/navigation` movido para o topo do arquivo (linha 14, `const
  refresh = vi.fn()`), com o mesmo formato do "floor" em `tests/unit/setup.ts`
  mas com `refresh` como espião — necessário porque `GuardrailTable` (agora
  renderizada dentro de `AutonomyScreen`) chama `useRouter().refresh()` depois
  de um save.
- Testes existentes do describe `'the guardrails section'` (:547) estendidos:
  o primeiro teste (:548) ganhou checagem de rótulo na coluna Setting,
  checagem de que Value e Set at nunca são a mesma string em nenhuma das cinco
  linhas testadas, e uma checagem negativa — `document.body.textContent` não
  contém `policies.masking`/`policies.guardrails`/`policies.approvals` cru em
  lugar nenhum da página (FR-026/027, e a instrução explícita do despacho de
  provar ausência, não só presença de nome de exibição). O teste do leitor
  ganhou duas asserções de ausência (`guardrail-edit`, `guardrail-field-editor`).
- Dois testes novos no mesmo describe: "keeps the three array-shaped fields
  reachable..." (:707) — prova que `custom_patterns`/`disabled_rules`/
  `autonomous_capabilities` continuam com controle dentro do `config-editor`
  estreitado, que o `config-editor` tem **exatamente 3** campos (não mais 9) e
  que nenhum dos seis escalares está mais lá; e "states the fixed guardrails
  as facts..." (:810) — prova que os dois `guardrail-invariant` não têm
  `switch`/`button` dentro deles, e que `firstParagraphBeforeControl()` (o
  mesmo walk que o acceptance da feature roda, já usado pela Fatia 5) devolve
  `null` para `tab=guardrails`, com o `guardrail-note` reaparecendo depois da
  tabela na ordem do DOM.
- Um describe novo, `'a reader sees real content on every tab...'` (:837),
  com `it.each` sobre as três abas: para cada uma, nenhum de
  `autonomy-editor`/`posture-editor`/`override-editor`/`config-editor`/
  `guardrail-edit` aparece, e cada aba ainda mostra algo de verdade
  (`posture-guardrails-summary`+linhas em Posture, `autonomy-rule`s em Rules &
  windows, `effective-field`+os dois `guardrail-invariant` em Guardrails) —
  a checagem explícita, nas três abas e não só na minha, do formato de defeito
  que a Fatia 4 já tinha encontrado uma vez (Posture sem nada para um leitor).

## 6.2 Os três campos-array continuam alcançáveis — como, exatamente

`guardrailEditable` (`autonomy.tsx:340-344`) filtra o catálogo completo por
"começa com um dos três prefixos de guardrail" **e** "não é um dos seis
caminhos que `GUARDRAIL_FIELDS` nomeia". Como os seis escalares são
justamente os únicos com controle escalar (boolean/string/number/integer) e os
três array-shaped (`custom_patterns`, `disabled_rules`,
`autonomous_capabilities`) são os únicos do tipo `array` sob esses três
prefixos (confirmado por leitura de `tools/mockplane/dataset/served.py:1144-1207`
antes de escrever o filtro — nenhum campo `array` a mais existe sob esses três
prefixos hoje), o resultado é: **o `ConfigEditor` que sobra na aba Guardrails
recebe só os três campos-array**, continuando a desenhá-los como
`ObjectList` (o mesmo componente que já editava listas antes desta fatia — não
toquei nesse caminho).

Prova por teste: `autonomy.test.tsx:707-800` ("keeps the three array-shaped
fields reachable...") serve um catálogo com um escalar (`masking.enabled`)
mais os três arrays, renderiza `tab=guardrails`, e afirma que
`config-editor`'s `data-path`s incluem os três arrays, **não** incluem
`policies.masking.enabled`, e que o total é **exatamente 3** — não uma
contagem "pelo menos". Esse teste fazia parte da rodada de 40 que passou (ver
§6.5) e não foi editado depois.

## 6.3 A gravação inline — por que carrega os irmãos intactos, com evidência

**O despacho desta fatia citava `console/src/app/api/autonomy/route.ts` como o
caminho de escrita, com o aviso de que um PUT de documento inteiro apaga
qualquer chave ausente.** Antes de escrever `GuardrailTable`, li os dois
couriers de escrita do console (`console/src/app/api/config/route.ts` e
`console/src/app/api/autonomy/route.ts` inteiros) para decidir qual serve os
seis escalares de guardrail, porque a resposta muda a forma inteira do
componente. A leitura, com evidência:

- `guardrailFields`/`guardrailCatalogue` em `autonomy.tsx` vêm de
  `GET /v1/config/{node_id}/fields` — o **catálogo geral de configuração do
  deployment**, o mesmo que `AdvancedConfigSection` usa para Topology, Tools,
  Integrations, Knowledge e Notifications. `policies.masking`/
  `policies.guardrails`/`policies.approvals` são três grupos **dentro** desse
  documento geral — não fazem parte do documento de política de autonomia
  (`rules`/`freezes`/`budgets`/`overrides`/`dry_run`) que
  `console/src/app/api/autonomy/route.ts` grava.
- `console/src/app/api/autonomy/route.ts:36-37` — `OPERATIONS.save = { path:
  '', method: 'PUT' }`, endereçando `PUT /v1/autonomy/policy/{node_id}` — o
  documento inteiro de política de autonomia. **Este é o caminho que
  `PostureEditor`/`AutonomyEditor` usam**, e é onde a Fatia 5 teve que carregar
  `freezes`/`budgets` inalterados — mas não é o caminho de um guardrail.
- `console/src/app/api/config/route.ts:56-109` (`POST`, docstring nas linhas
  6-20) — o courier que `ConfigEditor` já usava antes desta fatia
  (`SAVE_ENDPOINT = '/api/config'`, `preview.tsx:46`). O corpo que ele
  encaminha para `PUT /v1/config/{node_id}` é `{patch, remove}` — **um patch
  nomeado, não um documento de substituição inteira**. O próprio docstring diz
  isso: "the pending change is posted... A handler that merged, defaulted or
  reordered anything would break that pairing" — o handler do lado do
  deployment é quem funde o patch contra o que já existe; não há "chave
  ausente" para apagar porque a chamada nunca pretende ser o documento
  inteiro.

`GuardrailTable.save()` (`guardrail-table.tsx:154-189`) chama exatamente esse
courier, com `patch: nestedPatch(field.path, typed(field, draft))` —
**um único caminho aninhado por chamada**, nunca um documento com os outros
cinco guardrails ou qualquer outro campo do deployment dentro. Não há
"irmãos" para carregar porque o corpo nunca os menciona — a garantia não é
"carreguei tudo e não mudei o resto", é "nunca mencionei o resto".

**Prova por teste, não só por leitura do código-fonte**: o teste principal de
`guardrail-table.test.tsx` (a descrição "opens on the field's current value,
sends only that one path...") afirma o corpo exato do `POST` com `toEqual`
(igualdade estrita, não `toMatchObject`):
```
{ nodeId: 'org-northwind', patch: { policies: { masking: { enabled: true } } }, remove: [] }
```
`toEqual` estrito significa que qualquer chave extra — outro guardrail, um
campo de outro grupo, um `freezes`/`budgets` residual — faria o teste falhar.
**Este teste específico fazia parte da rodada de 11 que passou e não foi
editado depois** (ver §6.5.2) — é o teste QUE NÃO teve a edição pendente de
re-confirmação, ao contrário do primeiro teste do mesmo describe.

**Correção explícita sobre o aviso do despacho**: o aviso sobre "PUT de
documento inteiro" é real e correto — só que descreve o courier de autonomia
(`policies.autonomy.*`, dono de `PostureEditor`/`AutonomyEditor`, já resolvido
pela Fatia 5), não o courier de configuração geral (`policies.masking.*`/
`policies.guardrails.*`/`policies.approvals.*`, dono desta fatia). Os dois
couriers coexistem no mesmo app Next.js por serem dois documentos diferentes
no backend. Não encontrei nenhuma trava do lado do servidor (mock ou real)
verificada nesta sessão — `tools/mockplane` não implementa `PUT
/v1/config/{node_id}` em lugar nenhum (confirmado por grep, zero ocorrências),
então nenhum teste Playwright/e2e deste repositório jamais exercita a
gravação real contra o mockplane; a prova inteira de "carrega os irmãos
intactos" é, e só pode ser nesta árvore, a asserção de corpo exato acima —
nomeado com honestidade, não escondido.

## 6.4 O que `guardrail-table.test.tsx` prova, teste a teste, e o estado de confirmação de cada um

Os 11 testes, na ordem do arquivo, **todos passaram numa única rodada**
(`pnpm exec vitest run tests/unit/surfaces/settings/guardrail-table.test.tsx
--pool=forks` → `Test Files 1 passed (1)`, `Tests 11 passed (11)`, ver §6.5.2
para o log exato) — **exceto o primeiro**, cujo corpo foi editado depois dessa
rodada para resolver um conflito real entre duas regras de lint (ver abaixo) e
**não foi rodado de novo**:

1. "draws Setting, Value and Set at for every row, and the two say different
   things" — **EDITADO DEPOIS DA ÚLTIMA RODADA VERDE, NÃO RE-CONFIRMADO.** A
   única mudança foi de forma, não de asserção: `within(rows[0] as
   HTMLElement)` virou `within(maskingRow)` com um `.find()` +
   `if (maskingRow === undefined) throw new Error(...)` explícito, porque
   `as HTMLElement` violava `@typescript-eslint/non-nullable-type-assertion-style`
   (queria `!`) e `rows[0]!` violava `@typescript-eslint/no-non-null-assertion`
   (proíbe `!`) — as duas regras se contradiziam para a forma antiga, e a
   nova forma (find + throw, o mesmo padrão que `rowFor()` já usa em
   `autonomy.test.tsx`) satisfaz as duas. `tsc --noEmit` e `eslint` **depois**
   dessa edição: limpos, confirmado. `vitest` **não** foi rodado depois dela —
   é a única lacuna real de confirmação neste arquivo.
2–11. Todos os outros dez (os dois de exceção em valor/origem vazios; os três
   de "quem ganha Edit"; e os cinco do describe de edição — abre no valor
   atual + envia só o caminho certo + `refresh()`; cancela sem gravar; recusa
   do deployment com o form ainda aberto; falha de rede; `Select` para
   conjunto fechado) — **não foram tocados depois da rodada verde.** O corpo
   de cada um é exatamente o que rodou e passou.

## 6.5 Comandos rodados, com resultado real — e os que faltam

### 6.5.1 Gates estáticos (rodados por último, depois de toda edição)

```
$ pnpm exec tsc --noEmit
```
Vazio (sucesso), confirmado como última ação antes da interrupção.

```
$ pnpm exec eslint tests/unit/surfaces/settings/autonomy.test.tsx tests/unit/surfaces/settings/guardrail-table.test.tsx
```
Vazio (sucesso), confirmado como penúltima ação antes da interrupção. Também
confirmado limpo, em rodadas anteriores desta fatia:
`src/surfaces/settings/guardrail-table.tsx`, `src/surfaces/settings/autonomy.tsx`,
`src/surfaces/preview.tsx`.

```
$ pnpm exec prettier --check <os seis arquivos de console/src e console/i18n tocados>
```
`All matched files use Prettier code style!` — confirmado depois de duas
rodadas de `--write` (uma para os três arquivos de `src`, uma para
`guardrail-table.test.tsx`).

```
$ node scripts/check-css-literals.mjs
```
Sem saída (sucesso) — rodado uma vez, contra a árvore já com
`guardrail-table.tsx` presente.

### 6.5.2 Vitest — rodadas isoladas, cada uma com o resultado real no momento em que rodou

```
$ pnpm exec vitest run tests/unit/surfaces/settings/autonomy.test.tsx --pool=forks
```
Rodado **quatro vezes** ao longo da fatia, sempre contra o arquivo como estava
naquele momento: 35 passed (logo depois do mock de `next/navigation`, antes de
qualquer teste novo) → 37 passed (depois de estender o primeiro teste do
describe de guardrails + os dois testes novos) → 40 passed (depois do describe
`it.each` do leitor nas três abas) — **esta é a última rodada deste arquivo
que de fato rodou**. Depois dela, o único toque neste arquivo foi remover o
import não usado de `userEvent` (uma linha, sem tocar corpo de teste algum) —
**não rodado de novo depois disso**, por instrução explícita de parar.

```
$ pnpm exec vitest run tests/unit/surfaces/settings/guardrail-table.test.tsx --pool=forks
```
Rodado **uma vez**: `Test Files 1 passed (1)`, `Tests 11 passed (11)`. Isso foi
**antes** da edição de lint no primeiro teste (§6.4, item 1) — **não rodado de
novo depois dela**.

### 6.5.3 O que nunca rodou nesta sessão — nomeado, não escondido

- **`uv run python -m tools.console_gate test` (cobertura completa) — NUNCA
  RODADO.** Não tenho os quatro números de cobertura que o despacho pediu
  explicitamente, e não vou inventar nem reportar um número de uma fatia
  anterior como se fosse deste código — a Fatia 5 fechou em Branches 90.15%
  contra o piso de 90.00%, com folga fina; este código adiciona bastante
  lógica nova com ramificação real (`active`/`editable`/`savedPath`/`failure`
  em `guardrail-table.tsx`, mais os `if` de filtro em `autonomy.tsx`), coberta
  pelos 11 testes dedicados — mas **não tenho o número real**. É o gate mais
  importante que falta rodar antes de marcar qualquer caixa.
- **`uv run python -m tools.console_gate typecheck`/`lint` (os alvos
  empacotados) — não rodados como wrapper.** Rodei os comandos que eles
  invocam por baixo diretamente (`tsc --noEmit`; `eslint . &&
  check-css-literals.mjs`, mas o `eslint .` foi escopado aos arquivos tocados,
  não ao projeto inteiro nesta última rodada — as rodadas anteriores tinham
  sido mais amplas e limpas).
- **O acceptance da feature
  (`console/tests/e2e/autonomy-tabs.acceptance.spec.ts`) — NUNCA RODADO NESTA
  SESSÃO.** Não sei, com evidência desta sessão, se `(g) tab=guardrails`
  ficou verde. A Fatia 5 (§40, item 1) registrou a mensagem exata do vermelho
  antes desta fatia: `"a paragraph sits before the first control:
  \"Masking, secret detection and approval — edited here...\""` — e meu teste
  de unidade (`autonomy.test.tsx:810-835`) roda **o mesmo walk**
  (`firstParagraphBeforeControl()`, espelhado do próprio acceptance) contra o
  jsdom e devolve `null` para `tab=guardrails`, o que é evidência forte de que
  a causa raiz foi removida — mas é uma evidência de unidade, não a prova que
  o despacho pediu como "o resultado mensurável desta tarefa". Rodar o
  acceptance exige um build fresco primeiro (`tools.spec_validation browser`,
  que reconstrói; `tools.console_e2e run` direto serviria o build parado no
  tempo da Fatia 5, sem `GuardrailTable` nem o parágrafo movido — a mesma
  armadilha que a Fatia 4 já documentou em §21).
- **Contagem de asserções do acceptance, alturas por aba remedidas — não
  medidas.** A altura de Guardrails ficou em 1080px na Fatia 5 (não tocada
  então); esta fatia mudou substancialmente o conteúdo da aba (parágrafo
  removido, botões "Edit" adicionados, `ConfigEditor` estreitado de 9 para 3
  campos — provavelmente menor, já que a UI multi-seção do editor genérico
  para 9 campos era mais alta que 3, mas isso é uma expectativa, não uma
  medida) — **não sei o número real agora.**
- **`pnpm exec vitest run tests/unit/i18n/catalogue.test.ts`** — não rodado
  isoladamente; as duas chaves novas (`settings.autonomy.guardrails.edit`/
  `.cancel`) foram adicionadas nos dois catálogos no mesmo commit lógico, mas
  a paridade não foi confirmada por teste nesta sessão.
- **`config-editor.test.tsx`, `resolution-preview.test.tsx`** — arquivos que
  cobrem `ConfigEditor`/`EffectiveFieldsTable`, cujo módulo (`preview.tsx`)
  ganhou quatro exports novos aditivos. Risco baixo (nada foi removido nem
  teve assinatura mudada), mas **não rodados nesta sessão** para confirmar.
- **`make verify`, `console_gate build`, `console-visual-accept`,
  `console-e2e`** — fora do escopo desta fatia por instrução, e nenhuma
  baseline visual foi tocada.

## 6.6 O que fica pendente, nomeado, não escondido

- **A rodada de confirmação final de `guardrail-table.test.tsx`** (§6.4, item
  1) — o único código sem confirmação de teste depois da última edição.
  Baixo risco (mudança mecânica, `tsc`/`eslint` limpos), mas não observado.
- **A rodada de confirmação de `autonomy.test.tsx`** depois da remoção do
  import `userEvent` — risco desprezível (uma linha de import, nenhum corpo de
  teste tocado), mas também não observada.
- **`uv run python -m tools.console_gate test`** — nunca rodado; os quatro
  números de cobertura reais desta árvore são desconhecidos.
- **O acceptance da feature, com build fresco** — nunca rodado; `(g)
  tab=guardrails` tem evidência de unidade forte a favor, mas não a prova que
  o despacho pediu.
- **Alturas por aba remedidas** — não medidas depois das mudanças desta
  fatia.
- **T024 (contrato de paridade Python,
  `tests/contract/console/test_console_config_ownership.py`)** — não rodado;
  é da fatia seguinte, mas como este trabalho reorganizou onde os seis
  escalares são editados, vale a pena essa fatia rodá-lo cedo.
- **Os três sites de `Badge` com nível cru** (`autonomy.tsx:423` e outros,
  nomeados desde a Fatia 1 §4) — a tabela de regras em Rules & windows
  continua desenhando `<Badge status={level}/>` cru; não é meu para corrigir
  nesta fatia (Guardrails não é dono desse site) e segue sem dono atribuído.
- **A ambiguidade de leitura do SC-008** (Fatia 1 §3.3) — segue não resolvida,
  T040 é quem decide.
- **O texto vazio de Posture para um leitor quando `rulesEmpty` é verdadeiro**
  — achado, não corrigido: `autonomy-posture-empty` (o parágrafo que explica
  o default seguro) está aninhado dentro do bloco `writable && nodeId !== ''`
  em `autonomy.tsx` (território da Fatia 5/T013, não desta fatia) — um leitor
  num nó sem regra nenhuma não veria essa explicação, só o resumo de
  guardrails e o painel de bounds. Não é alcançável por nenhum nó do cenário
  `populated` (todo nó tem pelo meno uma regra, o mesmo achado que a Fatia 2 já
  tinha registrado para a alegação (h)), então nenhum gate real o exercita.
  Não corrigi — é uma linha de outra fase já marcada FEITO, e a instrução desta
  fatia era T018–T023. Nomeado para quem decidir se vale a pena mover essa
  única linha.
- **T021 apoia-se em código pré-existente, não escrito nesta fatia** — o mapa
  `SECTION_TITLE` (`preview.tsx:347-353`, com as quatro entradas
  `policies.masking`/`guardrails`/`approvals`/`autonomy`, todas com nome de
  exibição real nos dois catálogos) já existia antes desta sessão. O trabalho
  desta fatia foi **verificar** que ele continua correto depois do corte
  (`ConfigEditor` sobrevivente, 3 campos) e **provar a ausência**, não a
  presença — a asserção negativa em `autonomy.test.tsx:548-660` (o teste
  estendido). Nenhuma linha de produção nova foi escrita para T021
  especificamente.

## 6.7 Estado de cada tarefa, T018–T023 — o que o código prova agora, e o que falta só confirmar

Nenhuma caixa marcada. Para cada uma, a evidência que já existe e o comando
exato que falta rodar antes de marcar:

- **T018** (Value nunca vazio, sobrevive ao corte, Value ≠ Set at) —
  implementado e testado em dois lugares: `guardrail-table.test.tsx` (describe
  "reading the table", 3 testes — 1 deles com a edição não re-confirmada de
  §6.4) e `autonomy.test.tsx:548-660` (estendido, parte da rodada de 40 que
  passou e não editada depois). **Falta**: re-rodar
  `guardrail-table.test.tsx` uma vez para fechar a lacuna do item 1.
- **T019** (consumir o resolvedor compartilhado; remover o parágrafo de
  abertura; três campos-array alcançáveis) — código completo (§6.1), testado
  na rodada de 40 (unedited desde então). **Falta o resultado mensurável que o
  próprio despacho nomeou**: rodar o acceptance
  (`autonomy-tabs.acceptance.spec.ts`) com build fresco e confirmar `(g)
  tab=guardrails` verde. Não fiz essa rodada.
- **T020** (edição inline na própria linha, origem diz "definido aqui") —
  componente completo, gravação provada por corpo exato de `POST` +
  `refresh()` (§6.3), no teste que **não** tem a lacuna de re-confirmação.
  **Falta**: a mesma rodada de `guardrail-table.test.tsx` que T018 precisa (é
  o mesmo arquivo), e idealmente uma prova de navegador — não escrita, porque
  `tools.mockplane` não implementa `PUT /v1/config/{node_id}` (§6.3), então
  não haveria cenário real para um Playwright exercitar contra.
- **T021** (nome de exibição, não caminho técnico, como título de seção) —
  verificado sobre mecanismo pré-existente (§6.6), com asserção negativa nova
  na rodada de 40. **Falta**: nada de código; só a re-confirmação geral.
- **T022** (guardrails fixados como fatos sem controle; nenhuma aba com editor
  genérico como conteúdo primário) — os dois testes novos
  (`autonomy.test.tsx:707`, `:810`) fazem parte da rodada de 40, não editados
  depois. **Falta**: nada de código; só a re-confirmação geral.
- **T023** (leitor vê valores/origens/regras nas três abas, sem formulário nem
  botão de override) — coberto por um describe dedicado com `it.each` sobre as
  três abas (`autonomy.test.tsx:837-861`), mais as duas asserções de ausência
  acrescentadas ao teste de leitor pré-existente de Guardrails. Parte da
  rodada de 40. **Falta**: nada de código; só a re-confirmação geral, mais o
  gate de cobertura para confirmar que os ramos de leitor em
  `guardrail-table.tsx` (`editable = false`) estão de fato exercitados —
  acredito que sim (é exatamente o que o teste "offers no Edit affordance...
  for a reader" prova), mas não tenho o número de branch coverage real.

**Recomendação objetiva para a próxima sessão, na ordem mais barata primeiro**:

1. `pnpm exec vitest run tests/unit/surfaces/settings/guardrail-table.test.tsx --pool=forks`
   — se `11 passed`, a lacuna do item 1 de §6.4 fecha.
2. `pnpm exec vitest run tests/unit/surfaces/settings/autonomy.test.tsx --pool=forks`
   — se `40 passed`, confirma que a remoção do import não quebrou nada (esperado).
3. `uv run python -m tools.console_gate test` — os quatro números reais de
   cobertura. Se abaixo do piso, os ramos mais prováveis de faltar são os de
   falha (`guardrail-save-failure`) e cancelamento, já cobertos por teste — o
   número vai dizer se `autonomy.tsx`'s próprio filtro `guardrailEditable` e
   os `if`/ternários de `GuardrailTable` estão todos exercitados.
4. Se 1–3 baterem, marcar T018, T020, T021, T022, T023 em `tasks.md`.
5. `uv run python -m tools.console_gate build` seguido de
   `uv run python -m tools.spec_validation browser --feature specs_v6/040-autonomy-tres-abas --test console/tests/e2e/autonomy-tabs.acceptance.spec.ts`
   — só então marcar T019, e registrar a contagem final de alegações e a
   altura remedida da aba Guardrails.

## 6.8 Arquivos alterados — Fatia 6

- `console/src/surfaces/settings/guardrail-table.tsx` — novo. `GuardrailTable`
  e seus tipos, mais os helpers privados `asText`/`initialDraft`/`nestedPatch`/
  `isEditable`.
- `console/src/surfaces/preview.tsx` — `SAVE_ENDPOINT`, `EDITABLE_TYPES`,
  `typed`, `Control`/`ControlProps` ganharam `export`; nenhuma outra mudança.
- `console/src/surfaces/settings/autonomy.tsx` — `GUARDRAIL_FIELD_LIST`
  apagado; import trocado para o resolvedor compartilhado sem alias;
  `guardrailEditable` redefinido para excluir os seis escalares; parágrafo de
  abertura movido para depois do bloco de conteúdo, como `guardrail-note`;
  `<GuardrailTable>` no lugar da antiga `<EffectiveFieldsTable>` só-leitura.
- `console/src/i18n/en.ts` / `pt-BR.ts` — duas chaves novas cada
  (`settings.autonomy.guardrails.edit`/`.cancel`).
- `console/tests/unit/surfaces/settings/guardrail-table.test.tsx` — novo, 291
  linhas, 11 testes (um com edição pós-rodada-verde não re-confirmada, ver
  §6.4).
- `console/tests/unit/surfaces/settings/autonomy.test.tsx` — mock de
  `next/navigation` movido para o topo com `refresh` espionável; describe
  `'the guardrails section'` estendido (3 asserções novas no primeiro teste, 2
  no teste do leitor) mais dois testes novos; um describe novo,
  `it.each`-based, sobre leitor nas três abas.
- `specs_v6/040-autonomy-tres-abas/controle.md` — esta seção, acrescentada.
- `specs_v6/040-autonomy-tres-abas/tasks.md` — **não tocado nesta fatia**;
  T018–T023 seguem `[ ]`.

Nenhum outro arquivo foi tocado. Nenhum arquivo Python, nenhum fixture,
nenhum `config/constants/`, nenhuma baseline visual.

## 6.9 Lacunas fechadas pelo orquestrador

A Fatia 6 parou no teto de turnos entre duas edições de teste e a rodada de
confirmação. A §6.7 deixou a receita exata; rodei-a inteira e é isto que os
comandos devolveram — nenhuma caixa foi marcada por leitura.

- `uv run python -m tools.console_gate typecheck` → exit 0.
- `uv run python -m tools.console_gate lint` → exit 0.
- `uv run python -m tools.console_gate test` → **2433 testes, todos verdes**.
  Cobertura: statements 93.95%, **branches 90.17%**, functions 91.66%, lines
  95.95%. A fatia testou os próprios ramos: branches subiu de 90.15% para
  90.17% mesmo com um componente novo de edição inline, que é a forma de código
  que mais cria ramos. Fecha a dúvida da §6.7 sobre os ramos de leitor
  (`editable = false`) de `guardrail-table.tsx`.
- `uv run python -m tools.spec_validation browser` (build fresco) sobre
  acceptance + scroll-budget + transversal → **3 falharam, 50 passaram, 7
  skipped**. `(g) tab=guardrails` **passou a verde** — o resultado mensurável
  que o despacho de T019 nomeou. Os três vermelhos restantes são
  `(f) tab=posture`, `(f)` o botão de cabeçalho (ambos T036) e `(i)` a seção de
  simulação (T031). Nenhum é desta fatia.
- Alturas remedidas em 1920×1080: posture **1458px**, rules-windows **1211px**,
  guardrails **1080px**, contra orçamento de 1620px.
- `uv run pytest tests/contract/console/test_console_config_ownership.py` →
  19 passed. A paridade campo → tela continua verde depois do corte.

T018–T023 marcados em `tasks.md` com base nestas rodadas.

**Uma observação sobre a altura da aba Guardrails**: 1080px é exatamente a
altura do viewport, e é o terceiro run seguido em que essa aba devolve o mesmo
número. A suspeita registrada na Fatia 4 §32 continua de pé — um piso do tipo
`min-h-screen` dominando `scrollHeight` nas abas curtas. Posture (1458) e
Rules & windows (1211) devolvem números reais, então o piso só afeta a aba
curta. Consequência prática: para a aba Guardrails, a medição prova que ela
cabe no orçamento, mas não distingue 600px de conteúdo de 1080px. Fica para
T040 decidir se a regra transversal passa a medir o elemento de conteúdo em
vez do documento.

**Limite de evidência de T020, herdado da §6.3**: a gravação inline está
provada por corpo exato de `POST` mais `refresh()`, no nível de unidade. Não há
prova de navegador porque `tools.mockplane` não implementa
`PUT /v1/config/{node_id}` — não existe cenário servido contra o qual um
Playwright pudesse exercitar a escrita. Registrado como limite conhecido, não
como cobertura ausente por descuido.

---

# Fatia 7 — paridade sem campo órfão (T024–T027)

**Escopo desta fatia**: exatamente T024, T025, T026 e T027 — a Fase 6 /
User Story 4 inteira. Não tocada: a seção de simulação (T031), o painel
lateral de override (T036), a fase de fechamento (T039–T045).

Branch `feat/v6-scope-and-settings`, em cima de `b065ff1` (a aba Guardrails,
Fatia 6). Nada foi commitado, staged, nem passou por `git add` nesta sessão.

## 46. Tabela de estado — Fatia 7

| Peça | Estado | Detalhe |
|---|---|---|
| T024 — contrato de paridade re-rodado | **FEITO** | `uv run pytest tests/contract/console/test_console_config_ownership.py -v` → **19 passed** (§47). `test_the_size_of_each_category_is_what_the_console_says_it_is` continua afirmando `len(no_control()) == 9` e passou — a contagem de campos sem controle não cresceu (FR-048). O contrato em si não cruza `AUTONOMY_TAB_FIELDS` contra `config-ownership.ts` — só T025 faz isso. |
| T025 — teste de paridade campo→aba, nomeando a falta | **FEITO** | `console/tests/unit/surfaces/settings/autonomy-tabs.test.ts` — novo describe `'AUTONOMY_TAB_FIELDS — parity against shell/config-ownership.ts'` (linhas 176–252), cross-check real contra `CONFIG_FIELD_OWNERS` importado de `@/shell/config-ownership`, não hand-typed. Prova de que a checagem nomeia o campo em duas frentes independentes: casos construídos dentro do próprio teste (§48) e uma sabotagem real e desfeita do mapa de produção (§48.3), ambas nomeando `policies.autonomy.overrides` no vermelho. 21 passed depois de restaurado. |
| T026 — teste vermelho: link aterrissa na aba dona | **FEITO** | `console/tests/unit/shell/configuration-redirect.test.ts` — a asserção de `#config-section-policies-autonomy` reescrita para exigir `?tab=rules-windows`, mais uma nova asserção para `#config-section-policies-guardrails` exigindo `?tab=guardrails`. Rodado contra `configuration-redirect.ts` intocado: **2 failed, 7 passed**, pela razão certa (§49.1). |
| T027 — `configuration-redirect.ts` compõe o destino com a aba dona | **FEITO** | `console/src/shell/configuration-redirect.ts:66-87` — `sectionDestinations()` agora chama `tabOwning(path)` (importado de `@/surfaces/settings/autonomy-tabs`, o mesmo mapa de T005) quando `page === 'settings-autonomy-guardrails'`, e anexa `?tab=<aba>` ao destino antes do `#anchor`. Nenhuma correspondência campo→aba escrita uma segunda vez. Depois da mudança: **9 passed** (§49.2). |

## 47. T024 em detalhe — o que já era verde, e o que ele não checa

```
$ uv run pytest tests/contract/console/test_console_config_ownership.py -v
...
test_the_parser_reads_every_list_rather_than_silently_finding_nothing PASSED
test_every_field_the_schema_declares_is_accounted_for PASSED
test_nothing_is_claimed_that_the_schema_does_not_declare PASSED
test_no_field_belongs_to_more_than_one_category PASSED
test_every_page_named_is_an_area_the_console_actually_has PASSED
test_a_machine_field_is_a_real_field_named_one_at_a_time[...] PASSED (×2)
test_a_no_control_field_is_a_real_field_named_one_at_a_time[...] PASSED (×9)
test_the_size_of_each_category_is_what_the_console_says_it_is PASSED
test_the_no_control_category_splits_the_way_its_docstring_says PASSED
test_no_field_the_raw_editor_can_reach_is_left_with_no_control PASSED
============================== 19 passed in 0.45s ==============================
```

Lido o docstring do arquivo antes de assumir qual número importa, como a
instrução pedia: `test_the_size_of_each_category_is_what_the_console_says_it_is`
é a "burndown" — afirma `owned() == 105`, `machine() == 2`, `no_control() == 9`
— e é exatamente essa última contagem que FR-048 pede que não cresça. Os nove
campos sem controle nomeados (`agents.operating_context.sections`,
`capabilities.disabled`, `capabilities.disabled_tags`, `capabilities.enabled`,
`capabilities.parameters`, `capabilities.protocol_classifications`,
`policies.sso.group_to_node`, `policies.sso.scopes`, `surfaces.enabled`) —
nenhum sob `policies.autonomy.`/`policies.guardrails.`/`policies.masking.`/
`policies.approvals.`, então o corte em abas desta feature não moveu nada
para essa lista nem tirou nada dela. `test_no_field_the_raw_editor_can_reach_is_left_with_no_control`
também passou — zero campos "pendentes" (alcançáveis pelo editor cru mas sem
controle) — confirmando que a contagem de 9 é inteiramente a metade
"permanente" (5 arrays + 4 objetos que a checagem de tipo nunca vai poder
controlar), não uma dívida desta tela.

O que o contrato **não** verifica, e por que isso é o T025: ele confirma que
cada um dos 17 campos de `settings-autonomy-guardrails` tem uma **página**
(`CONFIG_FIELD_OWNERS`), nunca uma **aba** dentro dela — `page-ownership` e
`tab-ownership` são checagens em arquivos diferentes, de propósito, porque só
a v6 introduziu abas.

## 48. T025 em detalhe — como o `config-ownership.ts` foi lido, e como a falha foi provada

### 48.1 Leitura: import direto, não regex

`CONFIG_FIELD_OWNERS` é uma constante `export const` de um módulo TypeScript
comum — confirmado por leitura antes de escrever qualquer teste. O teste
importa (`import { CONFIG_FIELD_OWNERS, type ConfigFieldOwner } from
'@/shell/config-ownership';`) em vez de reparsear o texto-fonte, ao contrário
do contrato Python (que precisa de regex porque lê TypeScript de fora do seu
próprio compilador, e cujo docstring documenta exatamente a armadilha do
formatter quebrando uma entrada de caminho longo em várias linhas — a mesma
razão pela qual eu conferi que havia um `export` antes de escolher a
abordagem). Um teste vitest roda dentro do mesmo toolchain TypeScript que o
módulo — não há razão para reparsear o que o compilador já entende
nativamente, e nenhuma das armadilhas de quebra de linha do parser Python se
aplica aqui.

### 48.2 A checagem em si, e por que ela vive no teste, não em `autonomy-tabs.ts`

`ownedByThisPage()` filtra `CONFIG_FIELD_OWNERS` por
`page === 'settings-autonomy-guardrails'`; `unclaimedOrMisclaimed(owned,
fields)` conta quantas vezes cada `path` de `owned` aparece em `fields` e
devolve os que aparecem zero ou mais de uma vez — **nomeados**, o próprio
array de retorno contém a string do campo, não uma contagem;
`claimedNotOwned` faz o inverso (uma aba reivindicando um campo que esta
página não possui). As três funções vivem dentro do `describe` do teste, não
exportadas de `autonomy-tabs.ts` — decisão deliberada, espelhando o próprio
contrato Python: `test_console_config_ownership.py` também mantém `owned()`/
`no_control()`/as comparações inteiramente no arquivo de teste, lendo dados
de produção (`CONFIG_FIELD_OWNERS`, `declared_fields()`) sem exportar a
lógica de comparação como API de produção. Nenhum outro consumidor no
console precisaria desta função — só um teste de build a usa — então
adicioná-la a `autonomy-tabs.ts` seria superfície de produção sem propósito
além do próprio teste.

### 48.3 Prova de que a checagem falha nomeando o campo — duas vezes, de duas formas

**Primeira prova — casos construídos dentro do teste**, exatamente como a
instrução pediu ("construct the missing case in the test rather than
trusting that it would work"):

- `'names the field when config-ownership.ts assigns this page one no tab
  claims yet'` — constrói `owned` com um campo extra
  (`policies.autonomy.a_future_field`) que `AUTONOMY_TAB_FIELDS` não conhece;
  `unclaimedOrMisclaimed` devolve exatamente `['policies.autonomy.a_future_field']`.
- `'names the field when a tab stops claiming a path config-ownership.ts
  still assigns'` — remove de uma cópia de `AUTONOMY_TAB_FIELDS` a entrada do
  primeiro campo realmente possuído por esta página; a checagem devolve
  exatamente aquele campo.
- `'names a path twice when two tabs both claim it'` — adiciona uma segunda
  entrada para um campo já reivindicado, sob outra aba; a checagem devolve o
  caminho duplicado.

Essas três rodaram verdes já na primeira escrita porque a lógica de
`unclaimedOrMisclaimed`/`claimedNotOwned` é curta o bastante para ter sido
escrita correta de primeira — mas cada uma só passa porque a função
realmente detecta o defeito construído, não porque o array vazio é o
resultado padrão de qualquer entrada.

**Segunda prova — sabotagem real do mapa de produção, desfeita em seguida**
(o padrão que a Fatia 6 já usou para a alegação (g) do acceptance, "prova da
correção, feita e depois desfeita", repetido aqui porque é o jeito mais
honesto de provar que a checagem pegaria uma perda real, não só uma
simulada):

1. Copiei `console/src/surfaces/settings/autonomy-tabs.ts` para
   `/tmp/claude-999/.../scratchpad/autonomy-tabs.ts.bak`.
2. Removi a linha `{ path: 'policies.autonomy.overrides', tab: 'posture' },`
   de `AUTONOMY_TAB_FIELDS` no arquivo real (não um teste, o módulo de
   produção).
3. Rodei `pnpm exec vitest run tests/unit/surfaces/settings/autonomy-tabs.test.ts --pool=forks`:
   **5 failed, 16 passed**. O teste que prova a propriedade real —
   `'claims every field config-ownership.ts assigns here, and none it does
   not'` — falhou nomeando exatamente o campo:
   ```
   AssertionError: expected [ 'policies.autonomy.overrides', …(1) ] to deeply equal [ 'policies.autonomy.a_future_field' ]
   - Expected
   + Received
     [
   +   "policies.autonomy.overrides",
       "policies.autonomy.a_future_field",
     ]
   ```
   (Os outros quatro vermelhos são colaterais esperados — os três testes de
   `tabOwning`/`AUTONOMY_TAB_FIELDS` que também citam `overrides`
   explicitamente, e um dos testes de casos construídos, cuja lista `owned`
   real agora também inclui o campo órfão pela mesma sabotagem. Não é ruído:
   é o resto da suíte reagindo corretamente à mesma perda.)
4. Restaurei o arquivo do backup em `scratchpad/` (nunca `git checkout`),
   confirmado por `diff` byte a byte contra o backup.
5. Rodei de novo: **21 passed**.

Este é o vermelho real, observado contra código de produção genuinamente
quebrado — não inferido.

## 49. T026 + T027 em detalhe — o link aterrissa na aba dona

### 49.1 O vermelho, contra `configuration-redirect.ts` intocado

Duas asserções reescritas/adicionadas em `configuration-redirect.test.ts`,
rodadas antes de qualquer mudança em `configuration-redirect.ts`:

```
FAIL > sends a section on a page cut into tabs to the tab that owns it, not just the page
Expected: "/settings/autonomy-guardrails?tab=rules-windows#config-section-policies-autonomy"
Received: "/settings/autonomy-guardrails#config-section-policies-autonomy"

FAIL > sends a section one single tab owns outright to that tab, not a fixed default
Expected: "/settings/autonomy-guardrails?tab=guardrails#config-section-policies-guardrails"
Received: "/settings/autonomy-guardrails#config-section-policies-guardrails"

Test Files  1 failed (1)
     Tests  2 failed | 7 passed (9)
```

### 49.2 A implementação, e o caso ambíguo que ela resolve sem decidir nada nova

`sectionDestinations()` (`configuration-redirect.ts:66-87`) já agrupava por
`anchor` pegando a primeira ocorrência de cada seção em
`[...CONFIG_FIELD_OWNERS, ...CONFIG_FIELDS_NO_CONTROL]` e ignorando as
seguintes (`if (table.has(anchor)) continue;`). Isso já resolvia, sem eu
precisar escrever uma segunda regra de desempate, o único caso em que uma
seção do editor aposentado se espalha por duas abas: `policies.autonomy`
tem oito campos, sete em Rules & windows e um (`overrides`) em Posture; a
ordem declarada em `CONFIG_FIELD_OWNERS` (confirmada por leitura antes de
escrever qualquer coisa) coloca `policies.autonomy.allow_unverifiable_actions`
antes de `policies.autonomy.overrides` — então o primeiro `path` que a
função encontra para esse anchor já é um campo de Rules & windows, e
`tabOwning(path)` devolve `'rules-windows'` sem qualquer caso especial. As
outras três seções desta página (`policies.guardrails`, `policies.masking`,
`policies.approvals`) não têm essa ambiguidade — todo campo de cada uma
pertence à mesma aba (Guardrails) — e é por isso que o segundo teste
(`#config-section-policies-guardrails`) prova algo que o primeiro sozinho
não provaria: que a aba realmente varia por seção, não que toda seção desta
página aterrissa na mesma aba por acidente de implementação.

Depois da mudança (`console/src/shell/configuration-redirect.ts` importa
`tabOwning` de `@/surfaces/settings/autonomy-tabs`, consultando o mesmo
mapa que T005 declarou, sem reescrever a correspondência campo→aba):

```
$ pnpm exec vitest run tests/unit/shell/configuration-redirect.test.ts --pool=forks
Test Files  1 passed (1)
     Tests  9 passed (9)
```

`shell/` já importava de `@/surfaces/*` em três outros arquivos
(`commands.ts`, `legacy-redirect.ts`, `load.ts`, confirmado por grep antes
de escrever o import) — não é uma direção de dependência nova nesta árvore.

## 50. O bug pré-existente do `/autonomy` — decisão: corrigido

### 50.1 A decisão, e por quê

`console/src/app/(shell)/autonomy/page.tsx` descartava `searchParams`
inteiro antes de redirecionar (`await searchParams; redirect('/settings/autonomy-guardrails');`)
— o comentário do próprio arquivo dizia "autonomy never had tabs to
preserve", uma frase que ficou falsa no instante em que T009 (Fatia 4) deu
abas ao destino. Decidi corrigir, não só nomear, por três razões:

1. **É barato e bem precedented**: `/administration/page.tsx` e
   `/signals/page.tsx` já preservam parâmetros via `legacyRedirectHref`
   (`console/src/shell/legacy-redirect.ts`) — o padrão já existe no mesmo
   arquivo-família, só não tinha sido aplicado aqui.
2. **`legacyRedirectHref` não serve sem adaptação**: ele descarta `tab`
   deliberadamente (seu próprio docstring: "`tab` was how the old screen
   picked which of its own panes to show" — uma pergunta que a nova
   página responde por ser um endereço diferente). Isso é certo para
   `/administration`/`/signals`, onde `tab` selecionava entre DESTINOS
   diferentes. É errado para `/autonomy`: esta rota sempre teve um único
   destino, `/autonomy` nunca teve abas próprias com um `tab` concorrente
   — então um `tab=` que chegue aqui hoje já significa exatamente o que o
   destino entende nativamente, e descartá-lo reabriria o mesmo problema
   nomeado para a âncora de seção (T026), por um caminho diferente.
3. **Ambos os filtros nomeados no despacho (`node` e `tab`) precisavam de
   prova**, não só um.

### 50.2 A implementação: preservar tudo, sem consultar a tabela de destinos múltiplos

`page.tsx` agora usa `searchFrom` (de `@/surfaces/context`, já importado
pelo arquivo pelo tipo `SearchParams`) para reconstruir a query inteira e
anexá-la ao único destino fixo, em vez de reusar `legacyRedirectHref`
(que excluiria `tab`) ou `settingsRedirectTarget` (desnecessário — esta
rota nunca teve mais de um destino para escolher entre).

### 50.3 Vermelho, depois verde

Teste estendido em `console/tests/unit/shell/route-files.test.tsx`,
convertendo o `it` único num `it.each` no mesmo formato já usado para
`/administration`/`/signals` logo abaixo:

```
FAIL > sends /autonomy{ node: 'org-northwind' } to its Settings address
Expected: "redirected to /settings/autonomy-guardrails?node=org-northwind"
Received: "redirected to /settings/autonomy-guardrails"

FAIL > sends /autonomy{ node: 'org-northwind', tab: 'guardrails' } to its Settings address
Expected: "redirected to /settings/autonomy-guardrails?node=org-northwind&tab=guardrails"
Received: "redirected to /settings/autonomy-guardrails"

Tests  2 failed | 2 passed | 29 skipped (33)
```

Depois da mudança em `page.tsx`:

```
$ pnpm exec vitest run tests/unit/shell/route-files.test.tsx --pool=forks
Test Files  1 passed (1)
     Tests  33 passed (33)
```

Nenhuma FR desta spec cobre `/autonomy` especificamente (FR-049 é sobre a
âncora de seção do editor aposentado, um arquivo diferente) — este é
trabalho fora do ledger de critérios da spec, feito porque o despacho
autorizou a decisão e a correção não deixa nenhuma alegação nova sem prova.

## 51. Achado, investigado, não corrigido

`console/tests/unit/surfaces/settings/autonomy-tabs.test.ts:69` (antes desta
fatia, da Fatia 3/T004) tem um `describe` cujo título cita
`'hrefForTab — scope-node preservation across a tab switch (FR-006)'` — uma
citação de identificador de requisito dentro de um arquivo committed, que a
convenção deste repositório proíbe em qualquer arquivo committed. Não é meu
para corrigir nesta fatia: pertence a T004, já commitado antes desta sessão
(fora das quatro tarefas T024–T027 do despacho), e tocar um arquivo fora do
escopo declarado por um achado avulso — por menor que a correção seja —
não é a disciplina que as fatias anteriores desta mesma feature seguiram.
Nomeado para quem tocar este arquivo depois, ou para o orquestrador decidir
separadamente.

## 52. Gates rodados — Fatia 7

| Gate | Comando | Resultado |
|---|---|---|
| Contrato de paridade (T024) | `uv run pytest tests/contract/console/test_console_config_ownership.py -v` | 19 passed, 0.45s |
| Vitest focado — mapa campo→aba | `pnpm exec vitest run tests/unit/surfaces/settings/autonomy-tabs.test.ts --pool=forks` | 21 passed |
| Vitest focado — redirect de âncora | `pnpm exec vitest run tests/unit/shell/configuration-redirect.test.ts --pool=forks` | 9 passed |
| Vitest focado — arquivos de rota aposentados | `pnpm exec vitest run tests/unit/shell/route-files.test.tsx --pool=forks` | 33 passed |
| Formato | `pnpm exec prettier --check` nos cinco arquivos tocados | All matched files use Prettier code style! |
| Tipos | `uv run python -m tools.console_gate typecheck` | exit 0, sem saída de erro |
| Lint | `uv run python -m tools.console_gate lint` | exit 0, sem saída de erro |
| Suíte completa + cobertura | `uv run python -m tools.console_gate test` | **146 arquivos, 2439 testes, todos verdes**. Cobertura: statements **93.94%**, branches **90.19%**, functions **91.66%**, lines **95.96%** — piso de branches 90.00%, folga de 0.19pp (subiu de 90.17% na Fatia 6 para 90.19%: os ramos novos desta fatia foram exercitados, não só tolerados). |

**Não rodado, e por quê**: `make verify`, `console-visual-accept`,
`console-e2e` — a instrução desta fatia pede explicitamente para não rodar
nenhum dos três; nada nesta fatia adiciona ou muda uma tela, então não havia
razão para uma corrida de navegador. `uv run pytest` completo — fora do
escopo; a única checagem Python nomeada pelo despacho é o contrato de
paridade, já rodado.

## 53. O que fica pendente, nomeado, não escondido

- **Toda a Fase 7 em diante**: T028–T045 de `tasks.md`, nenhuma caixa
  marcada por mim. US5 (Rules & windows / simulação, T028–T033), US6
  (painel lateral de override, T034–T038) e a fase de fechamento
  (T039–T045) — nada disso foi tocado.
- **Os três sites de `Badge` com nível de autonomia cru** (`autonomy.tsx:423`,
  `:710`, `override-editor.tsx:340`) — nomeados pela Fatia 1 (§4), ainda sem
  dono, ainda não corrigidos.
- **A citação de identificador de requisito em
  `autonomy-tabs.test.ts:69`** (`(FR-006)` no título de um `describe`) —
  achado nesta fatia, não corrigido, ver §51.
- **A altura da aba Guardrails presa em 1080px** — suspeita de um piso
  `min-h-screen` dominando `scrollHeight`, nomeada pela Fatia 4/6, não
  investigada por mim.
- A ambiguidade de leitura do SC-008 sobre "medido em outro arquivo" vs.
  "isento" (Fatia 1, §3.3) segue para T040.

## 54. Arquivos alterados — Fatia 7

- `console/src/shell/configuration-redirect.ts` — `sectionDestinations()`
  agora compõe `?tab=<aba>` para `settings-autonomy-guardrails`, consultando
  `tabOwning` de `@/surfaces/settings/autonomy-tabs`.
- `console/src/app/(shell)/autonomy/page.tsx` — preserva `searchParams`
  inteiro (via `searchFrom`) em vez de descartá-lo antes do redirect.
- `console/tests/unit/surfaces/settings/autonomy-tabs.test.ts` — o teste de
  inventário fixo à mão substituído por um cross-check real contra
  `CONFIG_FIELD_OWNERS`, com duas provas de que a checagem nomeia o campo
  que falta.
- `console/tests/unit/shell/configuration-redirect.test.ts` — a asserção de
  `policies.autonomy` exige agora a aba dona; nova asserção para
  `policies.guardrails`.
- `console/tests/unit/shell/route-files.test.tsx` — o teste de `/autonomy`
  convertido em `it.each`, provando `node` e `tab` preservados.
- `specs_v6/040-autonomy-tres-abas/controle.md` — esta seção.
- `specs_v6/040-autonomy-tres-abas/tasks.md` — T024, T025, T026, T027
  marcados.

Nenhum outro arquivo foi tocado. Nenhuma chave de i18n nova (nenhuma string
visível ao usuário nasceu nesta fatia). Nenhum arquivo Python de produção
tocado. Nenhuma baseline visual capturada, aceita ou sobrescrita.

---

# Fatia 8 — a simulação converge num só CTA primário

**Escopo desta fatia**: exatamente duas tarefas — T029 (o teste de tela da
simulação, vermelho primeiro) e T031 (unificar os três controles de
simulação num CTA primário em `console/src/surfaces/autonomy-editor.tsx`).
Nada de T028, T030, T032, T033 (o resto da User Story 5), nada do painel
lateral de override (T034–T038), nada da fase de fechamento (T039–T045).

Branch `feat/v6-scope-and-settings`, em cima de `a56e4f2` (o mesmo HEAD que
a Fatia 7 deixou). O estado abaixo foi verificado contra o código atual da
árvore de trabalho — cada linha citada foi aberta e, onde fazia sentido,
executada. Nada foi commitado, staged, nem passou por `git add` nesta
sessão; `git status --porcelain` no fim desta fatia lista só os seis
arquivos da tabela §63, nada mais.

## 55. Tabela de estado — Fatia 8

| Peça | Estado | Detalhe |
|---|---|---|
| T029 — teste de tela da simulação, vermelho primeiro | **FEITO** | `console/tests/unit/surfaces/settings/autonomy.test.tsx`, `describe('the simulation section, on Rules & windows', ...)` (duas alegações: título+descrição+CTA único, e a trava de FR-035). A primeira alegação foi confirmada vermelha contra o componente pré-Fatia-8 (`TestingLibraryElementError: Unable to find an element by: [data-testid="autonomy-simulation"]`) e verde depois de T031 — ver §57. |
| T031 — unificar os três controles num CTA primário | **FEITO** | `console/src/surfaces/autonomy-editor.tsx` — a seção `data-testid="autonomy-simulation"` (linha 690 em diante), um título (FR-032), uma frase do que ela responde (FR-033), um único `variant="primary"` (FR-034), com as duas variações subordinadas — ver §56 pela decisão e a razão de cada uma. Os dois catálogos de idioma atualizados no mesmo lote de edições — `console/src/i18n/en.ts` e `console/src/i18n/pt-BR.ts`. |
| A trava de FR-035 (salvar exige o efeito visto para a entrada corrente) | **FEITO (já existia, verificado depois do rework)** | A lógica (`current`, `edited`, o botão `save-autonomy` só renderizado dentro de `answer !== null && current`) não foi tocada — só a posição do JSX mudou. Provado por um teste de tela novo que edita, previne o save, roda o preview, confirma o save aparecer, edita de novo e confirma o save sumir — `autonomy.test.tsx`, `'still refuses to save the current rule until its simulated effect has been seen'`. Ver §57.2 para a honestidade sobre esse teste ter passado antes E depois do rework. |
| Alegação (i) do acceptance da feature | **FEITO — moveu de vermelho para verde** | `console/tests/e2e/autonomy-tabs.acceptance.spec.ts:409`. Antes: 15 testes, **3 falhando** (a minha mais as duas de T036). Depois: 15 testes, **2 falhando** (só as duas de T036, exatamente como o despacho pediu para deixar). Ver §58. |
| Altura da aba Rules & windows, remedida | **FEITO** | **1345px** em 1920×1080, contra 1211px antes desta fatia — cresceu 134px pelo título, a frase, o divisor e a linha de introdução do Explain, todos elementos novos. Ainda 275px abaixo do orçamento por aba (1620px). Posture (1458px) e Guardrails (1080px) — nenhuma tocada por esta fatia — mediram exatamente os mesmos números que o despacho já citava, confirmando que nada vazou para as outras duas abas. Ver §59. |
| Os quatro sites de `Badge` citados no despacho | **Não corrigidos, dois deles mudaram de linha** | `action.before`/`action.after`: de `:779`/`:780` para `:754`/`:755`. `explanation.decision`/`explanation.level`: de `:733`/`:734` para `:832`/`:833`. Conteúdo idêntico, só a posição mudou como consequência mecânica do reagrupamento do JSX. Ver §60. |

## 56. As três controles de hoje, e a decisão sobre as duas subordinadas

### 56.1 O que cada um realmente faz, antes de decidir onde ele vai

Antes de mexer em qualquer JSX, li o que os três controles fazem de fato —
não presumi que fossem três variações da mesma pergunta só porque a
descrição da User Story 5 os cita juntos:

- **`ask-autonomy-preview`** (rótulo hoje "What would this decide
  differently?", `autonomy-editor.tsx`) — roda o documento **editado**
  (regras, congelamentos e tetos com as mudanças ainda não salvas) contra o
  histórico real do nó e devolve quantas ações seriam decididas diferente e
  quais passariam a autônomas. É o único dos três que tranca o `save`: o
  botão `save-autonomy` só existe dentro de `answer !== null && current`
  (`current = answer !== null && serialised === previewedDocument`).
- **`toggle-dry-run`** (rótulo hoje "Simulate everything"/"Stop
  simulating") — **não é uma prévia**: é um `POST` imediato que liga ou
  desliga `policies.autonomy.dry_run` no próprio nó, um campo real e
  persistido (`AUTONOMY_TAB_FIELDS` da Fatia 3 já atribui esse campo a esta
  aba). Ligar isto muda o que o **motor de decisão real** do deployment faz
  a partir de agora, para qualquer ação, editada ou não — não é uma
  pergunta hipotética sobre o rascunho.
- **`ask-explain`** (rótulo hoje "Explain one action") — pede a decisão de
  **uma** ação hipotética (capability + resource), contra a política **já
  salva**, sem tocar no documento em edição. Não passa por `current`, não
  destrava nada, é uma pergunta mais estreita que "o que o meu rascunho
  mudaria".

Ou seja: os três respondem perguntas genuinamente diferentes — "o que o meu
rascunho mudaria" (preview), "o deployment inteiro deveria simular a partir
de agora" (dry-run) e "o que aconteceria com esta ação específica, hoje"
(explain). FR-034 não pede que elas virem a mesma pergunta — pede que
parem de competir como três botões de peso igual, sem contexto, e que haja
**um** CTA primário com as outras duas subordinadas a ele.

### 56.2 A decisão: um primário, dois subordinados, nenhum removido

**Primário**: `ask-autonomy-preview`, inalterado em comportamento — mantém
`variant="primary"`, mantém o rótulo de hoje (o teste do acceptance permite
isso explicitamente: "the surviving control is free to keep one of these
labels, just not have a sibling with the same one"). É o único que tranca
o save, então é o único que **precisa** ser primário — é o passo que FR-035
exige ter sido visto.

**Subordinado 1 — `toggle-dry-run`**: fica **ao lado** do primário, no
mesmo `<div className="flex flex-wrap items-center gap-3">`
(`autonomy-editor.tsx:711-732`), sem `variant` explícito (o padrão do
componente `Button` já é `'secondary'` — `components/action.tsx:86`).
Escolhido para ficar ao lado, não abaixo, porque é um clique só, sem campo
nenhum para preencher — a mesma "distância de esforço" do primário, só que
com peso visual menor. Renomeado (`autonomy.editor.dryRunOn`/`dryRunOff`,
de "Simulate everything"/"Stop simulating" para "Simulate every decision
across the deployment"/"Decide for real again") para deixar de prometer a
mesma pergunta que o primário — o rótulo antigo, ao lado de "What would
this decide differently?", lia como uma variação da mesma coisa; o novo
nomeia o que ele realmente faz (um interruptor por todo o deployment).

**Subordinado 2 — `ask-explain`**: movido para o **pé** da seção
(`autonomy-editor.tsx:800-833`), atrás de uma frase própria
(`labels.explainIntro`, "Or check a single hypothetical action instead:")
e separado por `border-t border-border pt-3` — a opção "um controle
secundário dentro da seção" que o despacho ofereceu, escolhida em vez de
escondê-lo atrás de um `<details>` fechado (a terceira opção, "algo que a
view de resultado oferece depois da primeira rodada"): o padrão de
`<details>` já existe no mesmo arquivo para as três seções de criação
(`new-rule`, `new-freeze`, `new-budget`), mas usar o mesmo padrão aqui
faria o "Explain" ficar indistinguível de "criar algo novo" — e esconder um
controle atrás de um clique extra sem necessidade não é o que "subordinado"
pede, é ocultação. Fica **abaixo**, não ao lado do primário, porque —
diferente do dry-run toggle — precisa de dois campos preenchidos
(capability, resource) antes de significar algo: o esforço de chegar até
ele já é maior, então a posição reflete isso.

### 56.3 Nada foi removido

FR-034 pede convergência, não redução: as três capacidades de hoje
continuam todas alcançáveis pelos mesmos testids
(`ask-autonomy-preview`, `toggle-dry-run`, `ask-explain`) com o mesmo
handler por trás de cada uma — só a hierarquia visual e os rótulos
mudaram. `console/tests/unit/surfaces/autonomy-editor.test.tsx` (462
linhas, comportamento do componente — preview, save, explain, dry-run,
criação de regra/congelamento/teto) não teve nenhuma asserção de
comportamento alterada, só a *fixture* `LABELS` ganhou três chaves novas
que a interface `AutonomyLabels` agora exige (`simulationTitle`,
`simulationDescription`, `explainIntro`) — as 58 asserções antigas desse
arquivo continuam testando exatamente o que testavam, e passam.

## 57. T029 em detalhe — vermelho confirmado, depois verde

### 57.1 A alegação nova: título, frase, CTA único

Revertido temporariamente `autonomy-editor.tsx` e `autonomy.tsx` para o
estado anterior a esta fatia (cópia de segurança em `scratchpad/`, nunca
`git checkout`), rodei:

```
pnpm exec vitest run tests/unit/surfaces/settings/autonomy.test.tsx -t "simulation section" --pool=forks
```

Resultado, contra o componente de antes:

```
FAIL  tests/unit/surfaces/settings/autonomy.test.tsx > the simulation section, on Rules & windows >
  has its own title, a line saying what it answers, and exactly one primary CTA, with none of the
  old competing labels surviving beside it
TestingLibraryElementError: Unable to find an element by: [data-testid="autonomy-simulation"]

 Test Files  1 failed (1)
      Tests  1 failed | 1 passed | 40 skipped (42)
```

Vermelho pelo motivo certo: a seção simplesmente não existe ainda. Restaurado
o rework (T031) a partir da cópia salva, mesmo comando:

```
 Test Files  2 passed (2)
      Tests  61 passed (61)
```

(61, não 42, porque a segunda rodada incluiu também
`autonomy-editor.test.tsx`, rodado junto para confirmar que o rework não
quebrou o componente — ver §56.3.)

### 57.2 A trava de FR-035: por que ela já estava verde, e por que isso é o resultado certo

O segundo teste desta `describe` — a trava de salvar-exige-preview — **já
passava contra o componente de antes de T031**, no mesmo vermelho
registrado acima (`1 failed | 1 passed`, o "1 passed" é este teste). Isso é
esperado e correto, não um teste vazio: T031 é um rework de **layout**, não
de lógica — `current`, `edited`, `answer`, `previewedDocument` não foram
tocados, só a posição do JSX que os lê. A instrução desta fatia foi "não
assuma que o rework preservou a trava — prove", então o valor deste teste
não é ter ficado vermelho (ele nunca deveria ficar, se o rework for só de
layout) — é continuar **verde depois** do rework, com a mesma asserção,
provando que reposicionar os botões não moveu nenhum deles para fora da
condição que os desenha. Rodei explicitamente as duas vezes (antes e depois
de T031, ambas capturadas acima) em vez de assumir que "passou uma vez"
bastava.

O teste, em `autonomy.test.tsx`: edita o nível da única regra do nó
(`within(row).getByLabelText('Level')`, escopado à linha `rule-editor`
para não colidir com o Select de mesmo rótulo "Level" que o formulário
"Create a rule" também declara — os dois usam o mesmo texto
`autonomy.editor.level`/`autonomy.editor.newRule.level` = "Level" no
catálogo real, uma ambiguidade pré-existente que não é desta fatia),
confirma que `save-autonomy` não existe e que `autonomy-preview-first`
aparece; clica `ask-autonomy-preview`; confirma que `save-autonomy`
aparece; edita o nível de novo; confirma que `save-autonomy` some de novo.
Isso exigiu estender o stub de fetch `serveAutonomy` (usado só por este
arquivo) com um ramo novo para `POST /api/autonomy` — `simulationAnswer`
opcional no `Stub`, que devolve `{ ok: true, answer }` quando fornecido e
404 quando não, preservando o comportamento de todo teste existente que
nunca preenche esse campo (`autonomy.test.tsx:135-183`).

## 58. A alegação (i) do acceptance da feature — antes e depois

Comando, contra o build real (`tools.spec_validation browser`, que
reconstrói primeiro):

```
uv run python -m tools.spec_validation browser \
  --feature specs_v6/040-autonomy-tres-abas \
  --test console/tests/e2e/autonomy-tabs.acceptance.spec.ts
```

**Antes** (árvore revertida para o estado pré-Fatia-8, mesma técnica de
cópia/restauração do §57.1): `Running 15 tests using 1 worker` — **3
failed, 12 passed**:

```
✘  11 › override is a rare action... › the override editor does not occupy body space, tab=posture
✘  14 › override is a rare action... › a header button opens the override in a side panel
✘  15 › the simulation section converges on one CTA › exactly one primary CTA carries the
      simulation section, and no competing label survives beside it
```

**Depois** (árvore restaurada com o rework de T031): mesmos 15 testes —
**2 failed, 13 passed**:

```
✓  15 › the simulation section converges on one CTA › exactly one primary CTA carries the
      simulation section, and no competing label survives beside it (286ms)
✘  11 › tab=posture (override ainda no corpo — T036, não desta fatia)
✘  14 › header button (não existe ainda — T036, não desta fatia)
```

A alegação (i) moveu de vermelho para verde; as duas de T036 continuam
vermelhas, exatamente como o despacho pediu. **Nota sobre os números que o
despacho citou** ("3 failed, 50 passed, 7 skipped"): rodando só este
arquivo, o total real é 15 testes, não 60 — `Running 15 tests using 1
worker`, confirmado nas duas rodadas acima. A contagem de falhas (3, depois
2) bate exatamente com o que o despacho descreve; a diferença nos números
de "passed"/"skipped" quase certamente vem de o despacho ter citado um
número agregado de uma corrida mais ampla (várias suítes de e2e juntas),
não uma medição deste arquivo isolado — não persegui isso mais a fundo, porque
o que importa para esta fatia (a contagem de falhas e quais alegações elas
são) bate exatamente.

## 59. Altura da aba Rules & windows, remedida

Medida com um script Playwright descartável
(`console/tests/e2e/_scratch-slice8-measure.spec.ts`), viewport 1920×1080
explícito (`test.use({ viewport: { width: 1920, height: 1080 } })` — a
suíte global roda a 1440×900, então sem esse override a medição não bate
com o orçamento declarado, o que aconteceu na minha primeira tentativa:
1657/1450/866px a 1440×900, descartados e remedidos corretamente), rodado
uma vez, depois apagado — não sobra na árvore
(`git status --porcelain -- console/tests/e2e/` vazio depois de `rm`).

| Aba | Antes desta fatia | Depois desta fatia |
|---|---|---|
| Posture | 1458px | **1458px** (não tocada) |
| Rules & windows | 1211px | **1345px** (+134px) |
| Guardrails | 1080px | **1080px** (não tocada) |

Confirmado pelo teste committed real (`scroll-budget.spec.ts`, os três
testes `?tab=<aba> stays within the per-tab scroll budget`), rodado contra
o mesmo build: **13 passed, 0 failed**. O crescimento de 134px em Rules &
windows é inteiramente o conteúdo novo (`<h3>`, a frase de descrição, o
divisor `border-t`, a linha de introdução do Explain) — segue 275px abaixo
do orçamento de 1620px (1.5 viewport). Posture e Guardrails baterem
exatamente os números que o despacho já citava confirma que nada desta
fatia vazou para as outras duas abas.

## 60. Os quatro sites de `Badge` citados no despacho

Não corrigidos — a instrução foi explícita. Dois mudaram de linha como
consequência **mecânica** do reagrupamento do JSX (o conteúdo de cada
`<Badge status={...} />` é byte-idêntico ao de antes, só a posição no
arquivo mudou):

| Site | Antes | Depois |
|---|---|---|
| `<Badge status={action.before} />` | `:779` | **`:754`** |
| `<Badge status={action.after} />` | `:780` | **`:755`** |
| `<Badge status={explanation.decision} />` | `:733` | **`:832`** |
| `<Badge status={explanation.level} />` | `:734` | **`:833`** |

Os dois primeiros subiram porque o bloco de resultado do preview (que os
contém) agora vem logo depois do CTA primário, perto do topo da seção; os
dois últimos desceram porque o bloco de explicação (que os contém) foi
para o pé da seção, junto do controle "Explain" que os produz. Nenhum dos
quatro teve o `status={...}` alterado — continuam desenhando o slug cru do
backend (`propose_only`, `act_and_report` etc.) sem passar por
`postureLabel`/`postureLabels` (`surfaces/postures.ts`), exatamente o
achado que a Fatia 1 nomeou e recomendou às fatias futuras de User Story 3
e User Story 6. Esta fatia não é nenhuma das duas — segue sem dono.

## 61. Gates rodados — Fatia 8

| Gate | Comando | Resultado |
|---|---|---|
| Vitest focado — os dois arquivos tocados | `pnpm exec vitest run tests/unit/surfaces/settings/autonomy.test.tsx tests/unit/surfaces/autonomy-editor.test.tsx --pool=forks` (de `console/`) | **2 files passed, 61 tests passed** |
| Tipos (TS) | `pnpm exec tsc --noEmit` (de `console/`, projeto inteiro) | exit 0, nenhuma saída |
| Lint (TS/ESLint + literais CSS) | `uv run python -m tools.console_gate lint` | exit 0 (`eslint . && node scripts/check-css-literals.mjs`, sem saída de erro) |
| Formato (Prettier) | `pnpm exec prettier --check` nos seis arquivos tocados | `All matched files use Prettier code style!` (depois de um `--write` em dois arquivos cuja indentação extra — um nível a mais dentro do novo wrapper — estourou o print-width; puramente cosmético, confirmado por `diff`) |
| Catálogo de idioma, paridade | `pnpm exec vitest run tests/unit/i18n/catalogue.test.ts --pool=forks` | **1 file passed, 11 tests passed** |
| Suíte completa + cobertura | `uv run python -m tools.console_gate test` | **146 arquivos, 2441 testes, todos verdes** (2439 antes desta fatia + 2 novos). Statements 93.94% (6297/6703), **Branches 90.2% (4690/5199)**, Functions 91.66% (1946/2123), Lines 95.96% (5820/6065) — piso de branches 90.00%, folga de ~0.20pp, leve alta em relação aos 90.19% da Fatia 7 (os ramos novos foram exercitados pelos dois testes novos, não só tolerados). |
| Acceptance da feature (Playwright, build real) | `uv run python -m tools.spec_validation browser --feature specs_v6/040-autonomy-tres-abas --test console/tests/e2e/autonomy-tabs.acceptance.spec.ts` | **15 tests: 2 failed (as duas de T036), 13 passed** — antes desta fatia: 3 failed, 12 passed. Ver §58. |
| `scroll-budget.spec.ts` (committed, real) | `uv run python -m tools.spec_validation browser --feature specs_v6/040-autonomy-tres-abas --test console/tests/e2e/scroll-budget.spec.ts --no-build` | **13 passed, 0 failed** |
| `transversal-rules.spec.ts` (committed, real) | `uv run python -m tools.spec_validation browser --feature specs_v6/040-autonomy-tres-abas --test console/tests/e2e/transversal-rules.spec.ts --no-build` | **22 passed, 7 skipped, 0 failed** — inclui o ban de vocabulário (os rótulos novos não usam nenhum slug cru) e a contagem única de verdade |

**Não rodado, e por quê**: `make verify`, `console-visual-accept`,
`console-e2e` completo — o despacho pede explicitamente para não rodar
nenhum dos três; nenhuma baseline visual foi capturada, aceita ou
sobrescrita nesta fatia. `pytest`/Python — nenhum arquivo Python foi
tocado nesta fatia (a constante de orçamento por aba já existe desde a
Fatia 2); `make check-constants` não tem superfície nova para verificar.

## 62. O que fica pendente, nomeado, não escondido — Fatia 8

- **T028, T030, T032, T033** (o resto da User Story 5) — não tocados. Em
  particular, T030 ("reorganizar os controles existentes de regra,
  congelamento e teto dentro da aba, sem alterar o contrato de escrita")
  segue **não feito**: os três `<details>` de criação (`new-rule`,
  `new-freeze`, `new-budget`) continuam exatamente onde estavam, esta fatia
  não os moveu.
- **T034–T045** — painel lateral de override e fase de fechamento, sem
  nenhuma caixa marcada por mim.
- **Os quatro sites de `Badge` com nível/decisão cru** — dois mudaram de
  linha (§60), nenhum corrigido, sem dono atribuído nesta fatia também.
- **A ambiguidade de leitura do SC-008** (Fatia 1 §3.3) — segue para T040,
  não tocada aqui.
- **A citação de `(FR-006)` no título de um `describe` em
  `autonomy-tabs.test.ts:69`** (achado da Fatia 7, §51) — não é meu, não
  toquei nesse arquivo.
- **A altura da aba Guardrails presa em 1080px** (suspeita de
  `min-h-screen`, Fatia 4/6) — não investigada por mim; confirmei apenas
  que o número não mudou com esta fatia.
- **A ambiguidade "Level"/"Level" entre o Select de uma regra existente e o
  Select do formulário "Create a rule"** (mesmo texto de catálogo,
  `autonomy.editor.level` e `autonomy.editor.newRule.level`) — descoberta
  ao escrever o teste de T029 (§57.2), contornada com `within(row)` em vez
  de corrigida. Não é um defeito que esta fatia foi instruída a corrigir —
  nomeado aqui porque um teste futuro que tente `getByLabelText('Level')`
  sem escopo vai falhar por ambiguidade, não por um defeito de produto.

## 63. Arquivos alterados — Fatia 8

- `console/src/surfaces/autonomy-editor.tsx` — a interface `AutonomyLabels`
  ganhou três campos (`simulationTitle`, `simulationDescription`,
  `explainIntro`); o JSX de retorno reagrupado numa seção
  `data-testid="autonomy-simulation"` com título, frase e um só CTA
  primário, as duas variações subordinadas (dry-run ao lado, explain no
  pé, atrás de um divisor). Nenhuma função de estado ou handler alterado.
- `console/src/surfaces/settings/autonomy.tsx` — três novas entradas no
  objeto `labels={{...}}` passado a `AutonomyEditor`
  (`simulationTitle`, `simulationDescription`, `explainIntro`), lidas do
  catálogo. Nenhuma outra linha tocada — confirmado que o segundo uso de
  `'autonomy.editor.level'` (o `PostureEditor` da aba Posture, agora em
  `:740`) é um bloco totalmente diferente, não tocado.
- `console/src/i18n/en.ts` — duas chaves novas
  (`autonomy.editor.simulation.title`, `autonomy.editor.simulation.description`),
  uma chave nova (`autonomy.editor.explainIntro`), e três chaves com valor
  alterado (`autonomy.editor.explain`: "Explain one action" → "Explain";
  `autonomy.editor.dryRunOn`/`dryRunOff`: "Simulate everything"/"Stop
  simulating" → "Simulate every decision across the deployment"/"Decide
  for real again").
- `console/src/i18n/pt-BR.ts` — as mesmas seis chaves, em pt-BR, no mesmo
  commit.
- `console/tests/unit/surfaces/autonomy-editor.test.tsx` — a fixture
  `LABELS` ganhou os três campos novos que a interface agora exige.
  Nenhuma asserção de comportamento alterada; as 58 asserções que já
  existiam continuam testando o mesmo contrato e passam.
- `console/tests/unit/surfaces/settings/autonomy.test.tsx` — import de
  `userEvent`; `serveAutonomy`/`Stub` ganharam o campo opcional
  `simulationAnswer` e o ramo `POST /api/autonomy`; novo
  `describe('the simulation section, on Rules & windows', ...)` com os
  dois testes de T029.
- `specs_v6/040-autonomy-tres-abas/tasks.md` — caixas de T029 e T031
  marcadas, só essas duas.
- `specs_v6/040-autonomy-tres-abas/controle.md` — esta seção.

Nenhum outro arquivo foi tocado. O script Playwright descartável
(`console/tests/e2e/_scratch-slice8-measure.spec.ts`) foi criado, usado
duas vezes (uma vez sem o viewport correto, remedida) e apagado — não
existe mais na árvore de trabalho.

---

# Fatia 9 — o override sai do corpo, entra atrás de um botão no cabeçalho

**Escopo desta fatia**: exatamente cinco tarefas — T034, T035, T036, T037,
T038, a User Story 6 inteira. Nada de T028/T030/T032/T033 (o resto da User
Story 5) nem da fase de fechamento (T039–T045).

Branch `feat/v6-scope-and-settings`, em cima de `a56e4f2` (o mesmo HEAD que a
Fatia 8 deixou). O estado abaixo foi verificado contra o código atual da
árvore de trabalho — cada linha citada foi aberta e, onde fazia sentido,
executada. Nada foi commitado, staged, nem passou por `git add` nesta sessão;
`git status --porcelain` ao final desta fatia lista só os seis arquivos da
tabela §71, mais os dois já modificados antes desta sessão começar
(`fixtures/scenarios/populated/autonomy-bounds.json`,
`tools/mockplane/dataset/served.py` — não tocados por mim, herdados do estado
em que a árvore já estava).

## 64. Tabela de estado — Fatia 9

| Peça | Estado | Detalhe |
|---|---|---|
| T034 — teste de tela, vermelho primeiro: nenhuma aba reserva espaço; botão no cabeçalho; abre painel com nome/nível/razão/duração; rótulo da razão declara o audit | **FEITO** | `console/tests/unit/surfaces/settings/autonomy.test.tsx:371-425` (`describe('the temporary override, behind a header button', ...)`, três testes) + o rótulo da razão mudou de "Reason" para "Reason — recorded in the audit trail" (`console/src/i18n/en.ts:1157`, pt-BR `console/src/i18n/pt-BR.ts:953`). Vermelho confirmado contra o código anterior a esta fatia — ver §66. |
| T035 — teste de tela dos dois estados, vermelho primeiro | **FEITO** | Os dois testes já existentes (`autonomy.test.tsx`, `describe('an active override on the bounds this node holds', ...)`) adaptados para abrir o painel primeiro, e o estado vazio fortalecido para checar a frase, não só a ausência de linha (`.toHaveTextContent(/no override is active/i)`). Ver §67 para qual prova sustenta qual estado. |
| T036 — montar `OverrideEditor` no painel lateral, contrato preservado | **FEITO** | `console/src/surfaces/override-panel.tsx` (novo, 65 linhas) — o componente cliente que possui o estado aberto/fechado; `autonomy.tsx:389-471` monta `<OverridePanel>` envolvendo o `<Panel><OverrideEditor/></Panel>` exatamente como existia antes, só realocado. `console/src/surfaces/override-editor.tsx` **não foi tocado** — zero linhas alteradas, confirmado por `git status --porcelain` não o listar. Ver §65. |
| T037 — conceder/revogar entram no audit com nome, nível, razão, expiração | **FEITO (comportamento já existia, verificado por teste novo)** | `tests/unit/gateway/http/test_autonomy_routes.py:566-631` — teste novo que passou **de primeira**, sem mudança de produção: `grant_override`/`revoke_override` (`platform/autonomy/service.py:178-236`) escrevem através do mesmo caminho genérico que qualquer troca de configuração usa (`ConfigService.set_settings` → `ConfigAuditor.events`), e uma lista é auditada como uma folha só (`platform/config_service/paths.py:68-84`, docstring "A list is a leaf"), então o evento carrega o override inteiro — nome, nível, razão, expiração — dentro de `detail["new_value"]`/`detail["previous_value"]`. Ver §68. |
| T038 — com override ativo, subtítulo mostra a postura em vigor, não o nível salvo | **FEITO** | `highestActiveLevel()` (`autonomy.tsx:88-101`) + a bifurcação do subtítulo (`autonomy.tsx:365-382`); chave nova `autonomy.subtitle.override` (`en.ts:1095-1099`, pt-BR `pt-BR.ts:900-901`). Teste novo em `autonomy.test.tsx:1300-1335`. Vermelho confirmado, ver §66. |

## 65. A decisão do limite cliente/servidor, e por quê

### 65.1 O que já existia, e o que faltava

`SettingsPageHeader` (`console/src/shell/area.tsx:117-168`) já aceita um slot
`actions?: ReactNode` desde antes desta fatia — passado direto para
`PageHeader` (`console/src/components/layout.tsx:27-49`), que o desenha dentro
do próprio `<header>` que carrega `data-testid="page-header"`
(`area.tsx:154`). Não precisei estender `SettingsPageHeader` nem `PageHeader`
— a extensão aditiva que o despacho previa já tinha sido feita por uma fatia
anterior desta mesma onda, para outro propósito (a subtítulo com `context`).
Confirmei isso por leitura antes de tocar em qualquer coisa — nenhuma tela de
Settings **usava** `actions` ainda (`grep actions={` em `console/src/surfaces/`
só encontrava `incident-detail.tsx`, `run-detail.tsx` e `resources.tsx`,
nenhum deles em Settings), então esta é a primeira vez que o slot é usado
neste grupo de telas, mas o mecanismo já era genérico.

O que faltava era o dono do estado "o painel está aberto" — `AutonomyScreen`
é um Server Component `async` (`autonomy.tsx:197`), e um botão que abre um
painel precisa de `useState`, que só existe do lado do cliente.

### 65.2 A forma escolhida: um componente novo, dono só do "aberto/fechado"

`console/src/surfaces/override-panel.tsx` (novo) — `'use client'`, um único
componente `OverridePanel` que recebe `label`, `closeLabel` e `children`, e
não sabe nada sobre o que está dentro do painel:

```tsx
export function OverridePanel({ label, closeLabel, children }: OverridePanelProps): ReactNode {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button data-testid="open-override-panel" onClick={() => { setOpen(true); }}>
        {label}
      </Button>
      <Drawer open={open} title={label} onClose={() => { setOpen(false); }} closeLabel={closeLabel}>
        <div className="flex flex-col gap-5">{children}</div>
      </Drawer>
    </>
  );
}
```

`Drawer` (`console/src/components/overlay.tsx:171`, via `Overlay` em `:47-127`)
foi usado sem alteração — é o único componente do design system para "manter o
contexto atrás visível" (o próprio docstring do módulo, `:9-21`), retorna
`null` quando fechado (`:103`), então o conteúdo do painel — incluindo
`OverrideEditor` — está genuinamente desmontado, não só escondido por CSS, o
que fecha a alegação "não ocupa espaço no corpo" de um jeito honesto e não só
visualmente.

**Por que um componente novo, e não estender `OverrideEditor` ou
`SettingsPageHeader`**: `OverrideEditor` é o formulário — misturar nele a
responsabilidade de "que botão abre isto" faria um componente de domínio saber
sobre cromo de layout, e T036 pedia explicitamente preservar o contrato dele
"exatamente". Estender `SettingsPageHeader` não fazia sentido porque o slot
`actions` já existe — o que faltava era só um consumidor. `OverridePanel` fica
em `console/src/surfaces/`, irmão de `override-editor.tsx` (não dentro de
`settings/`), porque é reutilizável em princípio por qualquer tela que precise
do mesmo padrão "botão raro no cabeçalho, painel lateral" — não é específico
desta tela, mesmo que hoje só `autonomy.tsx` o use.

`AutonomyScreen` monta o conteúdo do painel (o `<Panel><OverrideEditor/></Panel>`
que já existia, movido sem alteração de JSX interno) e passa como `children`
para `OverridePanel`, que por sua vez é passado como `actions` para
`SettingsPageHeader` (`autonomy.tsx:476`) — o servidor decide **o que** vai no
painel, o cliente decide só **quando** ele está visível. Isso é composição
Server→Client padrão do Next.js (um Server Component pode passar uma árvore já
renderizada, incluindo outros Client Components, como `children` de um Client
Component) — não inventei um mecanismo novo.

### 65.3 Por que o `Panel` (o de "Grant or revoke an override") foi preservado, não removido

A decisão mais discutível desta fatia: o bloco que já existia —
`<Panel title="Grant or revoke an override" state={stateOf(bounds, false)}
dependency={dependencyOf(bounds)} ...><OverrideEditor .../></Panel>` — foi
**realocado para dentro do Drawer sem nenhuma mudança**, em vez de removido em
favor de um layout mais raso (o mockup mostra só um título "Temporary
override" seguido direto pelos campos, sem um segundo `<h3>` "Grant or revoke
an override" no meio). Escolhi preservar porque T036 foi explícito — "moving
it must not change what it does" — e o `Panel` não é só um título redundante:
ele é quem desenha o estado de carregamento (skeleton) e de erro (com retry)
se a leitura de `bounds` falhar, o que `OverrideEditor` sozinho não faz. Trocar
por um layout mais raso teria removido essa cobertura de erro sem que nenhuma
tarefa desta fatia pedisse isso. O resultado visual é um painel com dois
títulos empilhados ("Temporary override" do `Drawer`, "Grant or revoke an
override" do `Panel` logo abaixo) — nomeio isso como uma pequena
redundância deliberada, não uma omissão; ver §72.

## 66. T034/T035/T038 — vermelho confirmado, depois verde

Como as mudanças de implementação e de teste desta fatia foram feitas juntas
(a exploração do problema exigiu ler `Panel`/`Drawer`/`SettingsPageHeader`/
`ConfigAuditor` antes de decidir a forma do teste), a disciplina de
vermelho-antes-de-verde foi cumprida por um caminho equivalente: em vez de
escrever o teste primeiro literalmente, **reverti temporariamente**
`autonomy.tsx` para o estado anterior a esta fatia (`git show
HEAD:console/src/surfaces/settings/autonomy.tsx`, escrito num arquivo do
scratchpad — nunca `git checkout` nem `git show > console/...` direto no
caminho rastreado — e copiado por cima do arquivo de trabalho com `cp`, uma
cópia de arquivo comum, não um comando git) e rodei a suíte completa do
arquivo de teste **já com todas as mudanças de teste desta fatia aplicadas**:

```
$ pnpm exec vitest run tests/unit/surfaces/settings/autonomy.test.tsx --pool=forks
 Test Files  1 failed (1)
      Tests  5 failed | 43 passed (48)
```

As cinco alegações vermelhas, cada uma pelo motivo certo:

1. `an active override on the bounds this node holds › is shown to a writer with its own revoke button...` — `TestingLibraryElementError: Unable to find an accessible element with the role "button" and name /temporary override/i` (o botão do cabeçalho não existia).
2. `an active override on the bounds this node holds › says there is nothing to revoke...` — mesma causa.
3. `the temporary override, behind a header button › reserves no body space for it, tab=posture` — `override-editor` visível no corpo (os outros dois `tab=rules-windows`/`tab=guardrails` já passavam antes desta fatia, porque o editor nunca morou lá — consistente com a nota do próprio acceptance spec).
4. `the temporary override, behind a header button › opens from a button inside the page header...` — mesmo motivo do item 1.
5. `Posture: the level selector, and nothing before it › shows the posture an active override actually puts in force...` — `header` continha "Propose only" (o nível salvo) em vez de "Act and report" (o nível do override), porque o subtítulo ainda não olhava para `activeOverrides`.

Restaurei a implementação desta fatia (`cp` de volta, a partir da cópia salva
no scratchpad antes da reversão) e rodei de novo:

```
$ pnpm exec vitest run tests/unit/surfaces/settings/autonomy.test.tsx --pool=forks
 Test Files  1 passed (1)
      Tests  48 passed (48)
```

48, não 43+5: as cinco alegações vermelhas viraram verdes, nenhuma outra
quebrou.

## 67. T035 em detalhe — qual prova sustenta qual estado

**Estado vazio** (`autonomy.test.tsx:445-461` — "says there is nothing to
revoke for a node with none active"): provado só no nível de unidade, com
`serveAutonomy({ bounds: EMPTY_BOUNDS })` — nenhum nó do dataset real
(`populated`) tem zero overrides ativos no nó padrão (`org-northwind` carrega
o override que a Fatia 1 fixou), e o acceptance spec da feature não testa o
**conteúdo** do painel (só a ausência do editor no corpo e a existência do
diálogo) — então este estado nunca é exercitado pelo navegador nesta feature,
só pelo teste de unidade, que controla os dados via stub e não depende de qual
nó real tem o quê.

**Estado ativo** (`autonomy.test.tsx:426-444` — "is shown to a writer with its
own revoke button"): provado duplamente. No nível de unidade, com um override
fabricado no stub (`overrides: [{ name: 'incident-widen', ... }]`) — controla
os quatro campos exatamente. No nível de navegador, **indiretamente**: o
acceptance spec da feature (`autonomy-tabs.acceptance.spec.ts:386-403`) abre o
painel no nó padrão do dataset `populated` (`org-northwind`, que carrega
`_ACTIVE_OVERRIDE` desde a Fatia 1) e confirma que o diálogo abre — mas não lê
nome/nível/razão/expiração de dentro dele, então a prova real do
**conteúdo** do estado ativo é só a de unidade. Registro isso como um limite
conhecido, não escondido: o acceptance spec já existia antes desta fatia
(escrito na Fatia 2) e definia exatamente essas duas asserções para a
alegação (f); estender essas asserções para checar conteúdo do painel não
era parte das cinco tarefas desta fatia, e o despacho foi explícito que o
arquivo de acceptance já era o contrato a satisfazer, não a estender.

## 68. T037 em detalhe — o que o caminho de escrita já gravava, antes de escrever o teste

Antes de escrever qualquer asserção, li a cadeia completa:
`gateway/http/routes/autonomy.py:470-511` (`grant_override`) e `:514-537`
(`revoke_override`) chamam `AutonomyService.grant_override`/`revoke_override`
(`platform/autonomy/service.py:178-236`), que terminam ambos em `self.save(...)`
(`:84-106`), que chama `ConfigService.set_settings`
(`platform/config_service/service.py:261-315`). Nenhuma das duas rotas de
override escreve seu próprio evento de auditoria — as duas passam pelo mesmo
caminho genérico que qualquer troca de `policies.*` usa.

`set_settings` termina com `record(self._gateway, self._scope,
self._auditor.events(self._auditor.changes(node_id, document.settings,
proposed), actor_id=actor_id, actor_kind=actor_kind))`
(`service.py:306-314`). `ConfigAuditor.changes()` (`platform/config_service/audit.py:94-105`)
usa `paths.leaves()` (`platform/config_service/paths.py:68-84`) para achar
todo campo que mudou — e o docstring de `leaves()` é explícito: **"A list is a
leaf"**. `policies.autonomy.overrides` é uma lista, então ela é auditada
**inteira**, como um só campo (`field: "policies.autonomy.overrides"`), não um
evento por item nem um evento por sub-campo (`name`, `level`, etc. não viram
chaves próprias do evento). `ConfigAuditor.events()` (`:107-137`) grava
`detail = {"field": ..., "previous_value": ..., "new_value": ..., **atribuição}`
— o valor anterior e o novo são a lista inteira, filtrada por
`self.filtered()` (que só mexe em strings que batem um guardrail, preservando
a estrutura de resto).

**Conclusão, verificada antes de escrever o teste**: o registro de auditoria
de um `grant`/`revoke` de override **já continha** nome, nível, razão e
expiração — só que dentro de `detail["new_value"]`/`detail["previous_value"]`
(uma lista de dicionários), não como campos de primeiro nível do evento. Isso
é exatamente o que FR-044 pede ("entram no registro de auditoria com nome,
nível, razão e expiração") sem prescrever a forma exata do evento — e é
exatamente por isso que o despacho pediu para "estabelecer o que o caminho já
grava antes de escrever um teste que afirma uma forma que ninguém produz": uma
asserção contra `detail["name"]`/`detail["level"]` de primeiro nível teria
sido a forma errada, e teria ficado vermelha para sempre por um motivo que não
é o defeito que a FR descreve.

O teste (`tests/unit/gateway/http/test_autonomy_routes.py:566-631`) concede um
override via HTTP real, lê o `state.gateway` da mesma fixture `deployment` que
todo outro teste deste arquivo já usa, consulta `uow.audit.query(resource_id=
TEAM_PAYMENTS, limit=50)`, filtra por `detail["field"] ==
"policies.autonomy.overrides"`, confirma **exatamente um** evento novo, e lê
`name`/`level`/`reason`/`expires_at` de dentro da entrada correspondente em
`new_value`. Repete a mesma verificação para a revogação, contra
`previous_value`, e confirma que `new_value` fica `[]` depois.

**Honestidade sobre o vermelho**: rodei o teste contra o código de produção
**sem alterar nada** — passou de primeira:

```
$ uv run pytest -q tests/unit/gateway/http/test_autonomy_routes.py -k audit_trail
1 passed in 0.13s
```

Isto não é um teste vazio: ele lê o banco de auditoria real (`FakePersistence`,
a mesma implementação que os outros 22 testes deste arquivo já exercitam) e
faria uma asserção falhar com uma mensagem legível (`assert len(grant_events)
== 1, [event.detail for event in after_grant]`) se o campo, a contagem ou os
valores estivessem errados — não é uma tautologia. É o mesmo padrão que a
Fatia 1 já registrou para SC-002: uma propriedade que uma feature anterior já
fechou estruturalmente, provada agora por um teste que não existia antes,
sem produção nova porque nenhuma era necessária. Não fiz o exercício de
quebrar deliberadamente o código para confirmar que o teste discrimina,
por orçamento de turnos — a leitura da cadeia de chamadas acima (§68) é a
prova de que a asserção é real, não um acidente de dados vazios: se
`changed_paths` não detectasse a mudança, ou se `filtered()` reescrevesse a
lista, `len(grant_events) == 1` e os valores lidos teriam falhado.

## 69. As duas alegações (f), e a contagem do acceptance da feature

Comando, contra um build de produção reconstruído do zero:

```
uv run python -m tools.spec_validation browser \
  --feature specs_v6/040-autonomy-tres-abas \
  --test console/tests/e2e/autonomy-tabs.acceptance.spec.ts
```

Resultado: **15 tests using 1 worker — 15 passed (4.9s)**, zero falhas.
Antes desta fatia (fim da Fatia 8): 2 failed, 13 passed. As duas que viravam
vermelhas são exatamente as que este despacho nomeou:

```
✓  11 › override is a rare action... › the override editor does not occupy body space, tab=posture (208ms)
✓  12 › ... tab=rules-windows (216ms)
✓  13 › ... tab=guardrails (216ms)
✓  14 › a header button opens the override in a side panel (286ms)
```

(11–13 já eram verdes em `rules-windows`/`guardrails` desde antes — só
`tab=posture` mudou de vermelho para verde; 14 é a que estava vermelha por
inteiro.) As nove alegações (a)–(i) da feature estão todas verdes agora —
T039 (fase de fechamento, fora desta fatia) é quem formaliza essa comparação
contra o vermelho registrado em T002.

## 70. Alturas das três abas, remedidas

Medidas com um script Playwright descartável
(`console/tests/e2e/_scratch-slice9-measure.spec.ts`), viewport 1920×1080
explícito, rodado uma vez contra o build já compilado (`--no-build`) e
apagado depois — `git status --porcelain -- console/tests/e2e/` vazio ao
final.

| Aba | Antes desta fatia (fim da Fatia 8) | Depois desta fatia |
|---|---|---|
| Posture | 1458px | **1080px** (−378px) |
| Rules & windows | 1345px | **1345px** (não tocada) |
| Guardrails | 1080px | **1080px** (não tocada) |

Confirmado pelo teste committed real (`scroll-budget.spec.ts`, os três testes
`?tab=<aba> stays within the per-tab scroll budget`): **13 passed, 0 failed**.
`transversal-rules.spec.ts`: **22 passed, 7 skipped, 0 failed** — sem
mudança na contagem de exceções (nenhuma nova, `/settings/autonomy-guardrails`
continua sem exceção declarada nas três regras).

**Achado, nomeado e não perseguido**: Posture caiu para **exatamente**
1080px — o mesmo número, byte a byte, que a Fatia 8 já registrava para
Guardrails com a suspeita "presa em 1080px (suspeita de `min-h-screen`)",
não investigada até agora. Duas abas batendo o mesmo número redondo depois de
mudanças de conteúdo completamente diferentes (uma perdeu ~378px de conteúdo,
a outra não foi tocada) é mais evidência para a mesma suspeita — algum
wrapper força uma altura mínima de um viewport nas abas que sobra, mascarando
a altura de conteúdo real abaixo dela. Não investiguei a causa raiz: está
dentro do orçamento (1080 < 1620px), nenhuma tarefa desta fatia pede a
investigação, e o achado já estava nomeado por uma fatia anterior — só
acrescento a segunda ocorrência à mesma nota, para quem for investigar depois
ter dois pontos de dado em vez de um.

## 71. Um leitor sem escrita ainda vê conteúdo nas três abas

Verificado, não assumido — a instrução do despacho foi explícita sobre isso.
`describe('a reader sees real content on every tab', ...)` (`autonomy.test.tsx:998-1030`,
não tocada em sua lógica, só estendida com uma asserção nova) continua verde
para as três abas com o cenário `populated` e o principal `READER`
(`config.read` só). Em Posture especificamente: o painel de override nunca
apareceu para um leitor antes desta fatia (`writable && nodeId !== ''` já
gatava o `Panel` antigo), então removê-lo do corpo não muda nada do que um
leitor via ali — ele continua vendo `posture-guardrails-summary` e as linhas
`effective-field` (ambos incondicionais a `writable`). A asserção nova que
acrescentei ao mesmo teste (`autonomy.test.tsx:1008-1013`) confirma
adicionalmente que **nenhum botão** "Temporary override" aparece para esse
principal, em nenhuma das três abas — FR-050 lida à letra ("não receber...
o botão de override"), não só a ausência do formulário.

## 72. Os quatro sites de `Badge` com nível cru, ainda não corrigidos

Não tocados — fora do escopo desta fatia, como nas fatias anteriores.
Localizações atuais, depois do rearranjo desta fatia:

| Site | Linha antes (Fatia 8) | Linha agora |
|---|---|---|
| `<Badge status={level} />` (tabela de regras) | `:754`/`:755`* | `autonomy.tsx:551` |
| `<Badge status={override.level} />` (resumo do painel Bounds) | — | `autonomy.tsx:980` |
| `<Badge status={override.level} />` (lista de revogação, dentro do editor) | `override-editor.tsx:340` | `override-editor.tsx:340` (não mudou — arquivo não tocado) |

(*a tabela de regras não é um dos quatro sites que a Fatia 8 rastreou —
aquela fatia rastreou os quatro sites da seção de simulação, não este; a
linha de referência aqui é a da própria Fatia 1, `autonomy.tsx:423` na
numeração daquele momento.) Nenhum dos dois sites em `autonomy.tsx` teve o
`status={...}` alterado — continuam desenhando o slug cru
(`act_and_report` etc.), pela mesma razão nomeada desde a Fatia 1: nenhuma FR
desta spec prescreve o widget do nível dentro de um Badge, e o achado segue
sem dono atribuído.

**Uma redundância nova, nomeada aqui e não corrigida**: o painel agora mostra
dois títulos em sequência — "Temporary override" (o `<h2>` do `Drawer`) e
"Grant or revoke an override" (o `<h3>` do `Panel` logo abaixo, preservado
por T036 — ver §65.3). O mockup mostra só um título seguido direto pela
descrição e pelos campos. Decisão registrada: preservar o `Panel` porque ele
também carrega o tratamento de carregamento/erro que `OverrideEditor` sozinho
não tem, e nenhuma tarefa desta fatia pedia removê-lo — mas o título duplo é
um achado visual real que uma fatia futura (ou o mesmo trabalho que resolver
o vocabulário de `Badge` acima) pode decidir resolver, por exemplo tornando o
`Panel` `bare` ou removendo seu próprio título quando usado dentro de um
`Drawer` que já tem um.

## 73. O que fica pendente, nomeado, não escondido — Fatia 9

- **T028, T030, T032, T033** (o resto da User Story 5) — não tocados nesta
  fatia, seguem como a Fatia 8 os deixou.
- **T039–T045** (fase de fechamento) — sem nenhuma caixa marcada por mim.
- **Os quatro sites de `Badge` com nível/decisão cru** — ver §72, sem dono
  atribuído ainda.
- **O título duplo dentro do painel** ("Temporary override" +
  "Grant or revoke an override") — nomeado em §65.3 e §72, decisão
  deliberada de preservar o `Panel` por causa do tratamento de erro/loading,
  não uma correção pendente urgente, mas um achado visual real.
- **A suspeita de `min-h-screen` presa em 1080px**, agora em duas abas —
  nomeada em §70, não investigada, dentro do orçamento.
- **O conteúdo do estado "override ativo" só é provado por navegador
  indiretamente** (o diálogo abre; o acceptance spec da feature não lê nome/
  nível/razão/expiração de dentro dele) — nomeado em §67, não uma lacuna
  desta fatia (o acceptance spec já existia, escrito na Fatia 2, e não fazia
  parte do escopo desta fatia estendê-lo).
- **A ambiguidade de leitura do SC-008** (Fatia 1 §3.3) — segue para T040,
  não tocada aqui.
- **A citação de `(FR-006)` em `autonomy-tabs.test.ts:69`** (achado da
  Fatia 7) — não é meu, não toquei nesse arquivo.

## 74. Gates rodados — Fatia 9

| Gate | Comando | Resultado |
|---|---|---|
| Typecheck (TS), projeto inteiro | `pnpm exec tsc --noEmit` (de `console/`) | exit 0, nenhuma saída — rodado duas vezes (antes e depois do `prettier --write`) |
| Lint (TS/ESLint + literais CSS) | `uv run python -m tools.console_gate lint` | exit 0, `eslint . && node scripts/check-css-literals.mjs` sem erro |
| Formato (Prettier) | `pnpm exec prettier --check` nos cinco arquivos TS/TSX tocados | 1 arquivo (`autonomy.tsx`) precisou de `--write` (reflow cosmético — colapso de `labels={panelLabels(\n...\n)}` numa linha, entre outros); confirmado limpo depois |
| Vitest focado | `pnpm exec vitest run tests/unit/surfaces/settings/autonomy.test.tsx tests/unit/surfaces/override-editor.test.tsx tests/unit/surfaces/autonomy-editor.test.tsx tests/unit/i18n/catalogue.test.ts --pool=forks` (de `console/`) | **4 files passed, 99 tests passed** |
| Suíte completa do console + cobertura | `uv run python -m tools.console_gate test` | **146 arquivos, 2447 testes, todos verdes** (2441 antes desta fatia + 6 novos). Statements 93.92% (6306/6714), **Branches 90.17% (4690/5201)**, Functions 91.63% (1950/2128), Lines 95.93% (5828/6075) — piso de branches 90.00%, folga de 0.17pp, `exit 0` confirmado explicitamente |
| Acceptance da feature (Playwright, build real) | `uv run python -m tools.spec_validation browser --feature specs_v6/040-autonomy-tres-abas --test console/tests/e2e/autonomy-tabs.acceptance.spec.ts` | **15 tests: 15 passed, 0 failed** (antes: 2 failed, 13 passed) |
| `scroll-budget.spec.ts` (committed, real, `--no-build`) | idem, trocando o `--test` | **13 passed, 0 failed** |
| `transversal-rules.spec.ts` (committed, real, `--no-build`) | idem | **22 passed, 7 skipped, 0 failed** |
| Python — o teste novo de auditoria, isolado | `uv run pytest -q tests/unit/gateway/http/test_autonomy_routes.py -k audit_trail` | **1 passed** (sem mudança de produção) |
| Python — o arquivo inteiro | `uv run pytest -q tests/unit/gateway/http/test_autonomy_routes.py` | **23 passed** |
| Lint/formato/tipos Python, o arquivo tocado | `uv run ruff check` + `uv run ruff format --check` + `uv run mypy tests/unit/gateway/http/test_autonomy_routes.py` | todos limpos (`ruff format` precisou de um `--write`, reflow cosmético de três list comprehensions; confirmado limpo e reconfirmado com o arquivo inteiro rodando 23 passed depois) |

**Não rodado, e por quê**: `make verify`, `console-visual-accept`,
`console-e2e` completo — o despacho pede explicitamente para não rodar
nenhum dos três; nenhuma baseline visual foi capturada, aceita ou
sobrescrita nesta fatia. `make check-constants`/`check-imports`/
`check-protocols`/`check-deps` — nenhuma constante nova, nenhum limite de
import cruzado (o único arquivo Python tocado é um teste, e o único import
novo em TS é `Drawer`/`Button`, já aprovados no mesmo pacote `components/`).
`tests/contract/fixtures` — nenhum arquivo de fixture tocado nesta fatia.

## 75. Arquivos alterados — Fatia 9

- `console/src/surfaces/override-panel.tsx` — **novo**, 65 linhas. O
  componente cliente `OverridePanel`: um botão no cabeçalho, um `Drawer`,
  o estado aberto/fechado, nada mais.
- `console/src/surfaces/settings/autonomy.tsx` — import de `OverridePanel`
  (`:33`); a função `highestActiveLevel` (`:88-101`); a bifurcação do
  subtítulo por override ativo (`:365-382`); a construção de `overridePanel`
  como `const` (`:389-471`), envolvendo o `Panel`/`OverrideEditor` que antes
  vivia inline na aba Posture; `actions={overridePanel}` em
  `<SettingsPageHeader>` (`:476`); o bloco antigo (`Panel` + `OverrideEditor`
  + o parágrafo `autonomy-override-note`) removido do corpo da aba Posture.
  `console/src/surfaces/override-editor.tsx` **não foi tocado** — zero linhas.
- `console/src/i18n/en.ts` — chave nova `autonomy.subtitle.override`
  (`:1095-1099`); chaves novas `autonomy.override.temporary.title`/`.close`
  (`:1144-1148`); valor alterado de `autonomy.override.grant.reason`
  ("Reason" → "Reason — recorded in the audit trail", `:1157`).
- `console/src/i18n/pt-BR.ts` — as mesmas chaves, em pt-BR, no mesmo lote
  de edições.
- `console/tests/unit/surfaces/settings/autonomy.test.tsx` — novo
  `describe('the temporary override, behind a header button', ...)`
  (`:371-425`, três testes); os dois testes de
  `describe('an active override on the bounds this node holds', ...)`
  adaptados para abrir o painel antes de checar o conteúdo, e o estado vazio
  fortalecido para checar a frase; o teste
  `'defines a bound and an override on Posture...'` reduzido para checar só
  o bound (o override moveu para dentro do novo describe); a asserção de
  ausência do botão acrescentada a
  `describe('a reader sees real content on every tab', ...)`; um teste novo
  em `describe('Posture: the level selector, and nothing before it', ...)`
  (`:1300-1335`) para o subtítulo com override ativo.
- `tests/unit/gateway/http/test_autonomy_routes.py` — um teste novo,
  `test_granting_and_revoking_an_override_write_the_audit_trail`
  (`:566-631`), sem nenhuma mudança de produção.
- `specs_v6/040-autonomy-tres-abas/tasks.md` — caixas de T034 a T038
  marcadas, só essas cinco.
- `specs_v6/040-autonomy-tres-abas/controle.md` — esta seção.

Nenhum outro arquivo foi tocado. O script Playwright descartável
(`console/tests/e2e/_scratch-slice9-measure.spec.ts`) foi criado, usado uma
vez e apagado — não existe mais na árvore de trabalho, confirmado por
`git status --porcelain -- console/tests/e2e/`.

---

# Fatia 10 — o resto da User Story 5: criação, ordem de resolução, rolagem e o empty state de Rules (T028, T030, T032, T033)

**Escopo desta fatia**: exatamente quatro tarefas — T028, T030, T032 e T033,
o restante da User Story 5. Nada de T029/T031 (já feitos, Fatia 8) nem da
fase de fechamento (T039–T045).

Branch `feat/v6-scope-and-settings`, em cima de `d7544ca` (o mesmo HEAD que a
Fatia 9 deixou — nenhum commit aconteceu entre as duas fatias). O estado
abaixo foi verificado contra o código atual da árvore de trabalho — cada
linha citada foi aberta e, onde fazia sentido, executada. Nada foi
commitado, staged, nem passou por `git add` nesta sessão; `git status
--porcelain` ao final desta fatia lista só os quatro arquivos da tabela §80,
mais os dois já modificados antes desta sessão começar
(`fixtures/scenarios/populated/autonomy-bounds.json`,
`tools/mockplane/dataset/served.py` — não tocados por mim, herdados do
estado em que a árvore já estava, confirmado por `git status --porcelain`
não os listar em nenhum diff meu).

## 76. Tabela de estado — Fatia 10

| Peça | Estado | Detalhe |
|---|---|---|
| T028 — teste de tela, falhando primeiro: a aba traz criação de regra, de janela de congelamento e de teto, e a lista de regras em ordem de resolução | **FEITO** | Dois `describe` novos em `console/tests/unit/surfaces/settings/autonomy.test.tsx`: presença dos três controles (`:624-639`) e ordem de resolução com fixture deliberadamente fora de ordem (`:644-712`). Vermelho genuíno reproduzido por reversão temporária do mecanismo sob teste, não simulado — ver §77. |
| T030 — reorganizar regra/congelamento/teto sem alterar o contrato de escrita, carregando congelamentos e tetos inalterados em toda gravação de regra | **FEITO (verificação — nada para reorganizar; a lacuna real era um teste faltando, fechada)** | A distribuição já existente (regras → criar regra → freeze windows → budgets → simulação) já bate a única fonte normativa que fala da aba — a prosa do mockup, `settings-v6.html:250-251` — e nenhuma FR pede uma ordem diferente. O que faltava era a prova simétrica: `autonomy-editor.test.tsx` já provava que um freeze sobrevive a uma gravação que só mudou o nível de uma regra; **não havia o mesmo teste para budgets**. Fechado em `autonomy-editor.test.tsx:417-434`. Ver §78. |
| T032 — a lista de regras vira a região que rola, para que um nó com muitas regras não estoure o orçamento da aba; teste com fixture de nó carregado | **FEITO** | Duas listas de regras existem na aba (a tabela somente-leitura e a lista de editores por linha dentro de `AutonomyEditor`) e ambas cresceriam sem limite com o nó — as duas foram limitadas. `autonomy.tsx:511-518` (`data-testid="rules-scroll"`, `max-h-96 overflow-auto`); `autonomy-editor.tsx:473-480` (`data-testid="rule-editor-list"`, `max-h-96 overflow-y-auto`). Provado por teste de unidade com props/fixture de 40 regras em cada nível — nunca por navegador, ver a limitação nomeada no despacho e confirmada abaixo, §79. |
| T033 — CTA do empty state de Rules nomeia a ação e cria a primeira regra ali mesmo | **FEITO (verificação — já valia; a prova ficou mais rígida)** | O rótulo já era "Create the first rule" (`en.ts:1194`) e o `href` já era `#new-rule`, uma âncora na mesma página (`autonomy.tsx:340`, `canCreateHere`/`ruleEditorHref`). O que faltava provar é que o alvo é o controle **funcional**, não só um id que existe em algum lugar — fechado por um teste novo (`autonomy.test.tsx:1327-1341`) que abre o alvo e exige que `add-rule` esteja dentro dele. Ver §79.1. |

## 77. T028 em detalhe — as duas alegações, cada uma provada vermelha pelo motivo certo

### 77.1 O que já existia, e o que faltava

Antes de escrever qualquer coisa, li a aba inteira (`autonomy.tsx:496-726`,
`autonomy-editor.tsx:265-846`). Os três controles de criação
(`new-rule`/`new-freeze`/`new-budget`) já existiam desde o corte em abas
(Fatia 4) e nunca tinham sido verificados **juntos**, no nível de tela — só
individualmente, de passagem, em testes sobre outra coisa (o `href` do
empty state, por exemplo). A ordenação por especificidade
(`specificityOf`, `autonomy.tsx:159-162`, e o `.sort()` em `:257-259`)
também já existia, mas o único teste que exercitava a tabela com os sete
tipos de escopo (`'the rules table, over every scope kind...'`,
`:562-621`) enviava a fixture **já em ordem de resolução** — um `.sort()`
ausente ou quebrado teria produzido exatamente a mesma saída, então esse
teste não discriminava a propriedade que FR-031 pede.

### 77.2 A alegação de presença — vermelho reproduzido, não simulado

Depois de escrever `console/tests/unit/surfaces/settings/autonomy.test.tsx:624-639`,
rodei-o contra o código já correto (passou de primeira, como esperado — os
três controles já existiam). Para confirmar que o teste realmente
discrimina, renomeei temporariamente `data-testid="new-budget"` para
`"new-budget-x"` em `autonomy-editor.tsx` (edição feita e desfeita pelo
próprio Edit tool, nunca `git checkout`):

```
$ pnpm exec vitest run tests/unit/surfaces/settings/autonomy.test.tsx -t "brings all three creation controls" --pool=forks
 FAIL  ... > brings all three creation controls onto Rules & windows
 TestingLibraryElementError: Unable to find an element by: [data-testid="new-budget"]
 Tests  1 failed | 51 skipped (52)
```

Revertido o rename, o mesmo comando volta a passar (52 selecionados, 1
executado, verde). Vermelho pelo motivo certo: o controle de fato ausente,
não um erro de digitação no teste.

### 77.3 A alegação de ordem — vermelho reproduzido desativando o `.sort()`

Fixture em `autonomy.test.tsx:644-712`: sete regras, uma por tipo de
escopo, enviadas **na ordem inversa** da resolução
(`capability_resource` primeiro, `deployment` por último) — o oposto
exato do que um `.sort()` ausente produziria por acidente, então a saída
só bate a esperada se a ordenação realmente rodar. A asserção lê a
**primeira célula** de cada `<tr>` (`row.querySelector('td')?.textContent`),
não o texto da linha inteira — `toHaveTextContent('capability')` bateria
também em `capability_resource` por substring, e essa ambiguidade
específica é o tipo de alegação vazia que este despacho pede para evitar.

Removi temporariamente o `.sort(...)` de `autonomy.tsx:257-259` (troquei por
`const rules = [...list(dataOf(policy), 'rules')];` com um `void
specificityOf;` para não sobrar import não usado durante o teste) e rodei:

```
$ pnpm exec vitest run tests/unit/surfaces/settings/autonomy.test.tsx -t "renders least-specific first" --pool=forks
AssertionError: expected [ 'capability_resource', …(6) ] to deeply equal [ 'deployment', 'team', …(5) ]
 Tests  1 failed | 51 skipped (52)
```

A ordem recebida foi exatamente a ordem de chegada da fixture (a inversa da
esperada) — a prova mais direta possível de que a asserção depende do
`.sort()` e não de uma coincidência da fixture. Restaurado o `.sort()`
original, o mesmo comando volta a passar.

## 78. T030 em detalhe — por que é verificação, e o que a verificação prova

### 78.1 Por que não há nada para reorganizar

O mockup (`specs_v6/mockups/settings-v6.html`, âncora `m2`) não desenha a
aba Rules & windows — só a Posture, com o painel de override aberto como
slideover (confirmado lendo `settings-v6.html:205-257` inteiro). A única
frase normativa sobre o conteúdo desta aba é a legenda do próprio mockup:
"o que não pode sozinho (Rules & windows: regras, freeze windows, budgets,
simulação)" (`settings-v6.html:250-251`) — regras, depois freeze windows,
depois budgets, depois simulação, nessa ordem. A ordem real no DOM hoje
(tabela de regras → editor por linha → `new-rule` → `new-freeze` →
`new-budget` → simulação, `autonomy.tsx:499-723` e
`autonomy-editor.tsx:471-846`) já bate essa sequência. Nenhuma FR (`FR-030`
a `FR-037`, `spec.md:311-322`) pede uma disposição diferente. Não movi
nenhum bloco de JSX nesta fatia — confirmado que os únicos diffs em
`autonomy.tsx`/`autonomy-editor.tsx` são os wrappers de rolagem de T032,
nada de reordenação.

### 78.2 A propriedade que a tarefa nomeia, com a lacuna real que ela tinha

`autonomy-editor.tsx:393-403` monta o documento de toda gravação —
`rules`, `freezes` e `budgets` sempre presentes, os dois últimos carregados
como `[...freezes.map((each) => each.record), ...addedFreezes]` e
`[...budgets.map((each) => each.record), ...addedBudgets]`
respectivamente — o mesmo padrão que `PostureEditor.save()`
(`posture-editor.tsx:121-130`) já usa e que o despacho cita como
precedente. `autonomy-editor.test.tsx` já tinha, desde antes desta fatia,
`'carries an existing freeze through a save that only changed a rule
level, rather than wiping it'` (linha 390 antes desta fatia) — mas
**nenhum teste espelhado para budgets**. Essa assimetria é a lacuna real
de T030: a mesma linha de código (`:402`) já fazia a coisa certa para
budgets, só não tinha sido verificada isoladamente.

Fechei com `autonomy-editor.test.tsx:417-434`
(`'carries an existing budget through a save that only changed a rule
level, rather than wiping it'`), espelhando exatamente a estrutura do
teste de freeze, com um `BUDGETS` fixture novo
(`autonomy-editor.test.tsx:383-388`, ao lado de `FREEZES`).

**Vermelho reproduzido**: troquei temporariamente
`budgets: [...budgets.map((each) => each.record), ...addedBudgets],`
(`autonomy-editor.tsx:402`) por `budgets: [...addedBudgets],` — a mesma
classe de defeito que uma gravação sem a lista completa produziria — e
rodei:

```
$ pnpm exec vitest run tests/unit/surfaces/autonomy-editor.test.tsx -t "carries an existing budget" --pool=forks
AssertionError: expected [] to deeply equal [ { name: 'restart-cap', …(2) } ]
 Tests  1 failed | 20 skipped (21)
```

O budget existente desaparece exatamente como no defeito real que a nota
do despacho descreve (um `PUT` sem a chave completa é lido como lista
vazia). Restaurada a linha original, o teste volta a passar.

## 79. T032 em detalhe — as duas listas, a decisão de limitar as duas, e o limite conhecido da prova

### 79.1 Por que duas listas, e por que ambas

A aba tem duas apresentações independentes das mesmas regras: a tabela
somente-leitura dentro do painel "Rules" (`autonomy.tsx:499-564`,
`data-testid="autonomy-rule"` por linha) e a lista de editores por linha
dentro de `AutonomyEditor` (`autonomy-editor.tsx:471-501`,
`data-testid="rule-editor"` por linha) — a segunda existe porque mudar o
nível de uma regra precisa de um `<Select>`, e a primeira porque um leitor
sem escrita (que nunca vê `AutonomyEditor`, gate `writable &&
nodeId !== ''`) ainda precisa ver as regras. As duas crescem linearmente
com o número de regras do nó — limitar só uma deixaria a outra sozinha
capaz de estourar o orçamento de 1620px com um nó suficientemente
carregado, então limitei as duas com o mesmo padrão já usado em
`operating-context.tsx:392` (`max-h-96 overflow-y-auto`, uma escala do
Tailwind, não um literal):

- `autonomy.tsx:511-518` — o `<div className="w-full overflow-x-auto">`
  que envolvia a tabela virou
  `<div data-testid="rules-scroll" className="w-full max-h-96 overflow-auto">`
  (`overflow-auto` cobre as duas direções — a rolagem horizontal que já
  existia para linhas largas continua, e ganha a vertical).
- `autonomy-editor.tsx:473-480` — o `<div className="flex flex-col
  gap-3">` que envolvia `allRules.map(...)` ganhou
  `data-testid="rule-editor-list"` e `max-h-96 overflow-y-auto`.

Não toquei a duplicação em si (as duas listas mostrarem a mesma regra de
duas formas) — nenhuma FR pede consolidá-las, e fazer isso seria um
redesenho maior que este despacho não pediu; nomeio como achado, não como
pendência, em §81.

### 79.2 Os dois testes, e por que nenhum pôde ser um teste de navegador

O despacho já nomeia o motivo: `fixtures/scenarios/populated/*.json` é
gerado por `tools/mockplane/dataset/build.py` e não pode ser editado à
mão, e o projeto `behaviour` do Playwright serve um único cenário para
toda a corrida (`console/playwright.config.ts`) — não há como um teste de
navegador desta feature escolher um nó com quarenta regras sem tocar em
arquivo que não é meu para tocar. Os dois testes desta fatia são,
portanto, deliberadamente de unidade:

- `autonomy.test.tsx:714-745` — renderiza a tela inteira com um `policy`
  stub carregando 40 regras (`serveAutonomy`), confirma as 40 linhas
  `autonomy-rule` presentes, confirma que `rules-scroll` carrega as classes
  de rolagem, confirma que **todas** as 40 linhas são descendentes de
  `rules-scroll` (`toContainElement`), e confirma que `autonomy-simulation`
  **não** é descendente dele — nem por `toContainElement` nem por
  `scrollRegion.contains(simulation)`, a checagem dupla que o despacho
  pede para não aceitar "tem a classe" como prova de "só a lista rola".
- `autonomy-editor.test.tsx:467-511` — o mesmo desenho, direto no
  componente, com 40 `EditableRule` como prop `rules` (a frase do despacho,
  "hands the component many rules as props", bate literalmente esta
  forma). Confirma `rule-editor-list` como a caixa, as 40 linhas dentro
  dela, e que `new-rule`/`new-freeze`/`new-budget`/`autonomy-simulation`
  **não** estão.

**Honestidade sobre a ordem vermelho→verde**: os dois testes nasceram
depois da implementação (escrevi o `data-testid` e as classes de rolagem
antes de rodar o teste pela primeira vez), porque o desenho — quais duas
listas, qual testid, qual classe — exigiu ler a árvore inteira primeiro, o
mesmo padrão que a Fatia 9 já registrou para T034/T035/T038. A disciplina
de vermelho-antes-de-verde foi cumprida pelo caminho equivalente que esta
feature já usa: reverti cada wrapper para o estado anterior a esta fatia
(edições feitas e desfeitas pelo Edit tool, nunca `git checkout`/`git show
> arquivo`) e confirmei vermelho pelo motivo certo antes de restaurar:

```
$ pnpm exec vitest run tests/unit/surfaces/settings/autonomy.test.tsx -t "bounds only the rules list" --pool=forks
TestingLibraryElementError: Unable to find an element by: [data-testid="rules-scroll"]
 Tests  1 failed | 51 skipped (52)

$ pnpm exec vitest run tests/unit/surfaces/autonomy-editor.test.tsx -t "bounds the per-row editor list" --pool=forks
TestingLibraryElementError: Unable to find an element by: [data-testid="rule-editor-list"]
 Tests  1 failed | 20 skipped (21)
```

Restaurados os dois wrappers, ambos voltam a passar — confirmado abaixo,
§80.

### 79.3 O que a rolagem não muda: alturas remedidas

`max-h-96` (384px) só tem efeito quando o conteúdo excede essa altura. O
cenário `populated` (o que `scroll-budget.spec.ts` mede) não carrega
regras suficientes para atingir esse limite em nenhuma das duas listas —
confirmado por remedição real, viewport 1920×1080, script Playwright
descartável (`console/tests/e2e/_scratch-slice10-measure.spec.ts`, criado,
rodado uma vez, apagado em seguida — `git status --porcelain -- console/tests/e2e/`
vazio ao final):

| Aba | Fatia 9 | Fatia 10 |
|---|---|---|
| Posture | 1080px | **1080px** (sem mudança) |
| Rules & windows | 1345px | **1345px** (sem mudança) |
| Guardrails | 1080px | **1080px** (sem mudança) |

Confirmado também pelo teste committed real: `scroll-budget.spec.ts`, os
três testes `?tab=<aba> stays within the per-tab scroll budget`, **13
passed, 0 failed** — nenhuma regressão pelos wrappers novos.

## 80. Gates rodados — Fatia 10

| Gate | Comando | Resultado |
|---|---|---|
| Vitest focado — os dois arquivos de teste tocados + catálogo | `pnpm exec vitest run tests/unit/surfaces/settings/autonomy.test.tsx tests/unit/surfaces/autonomy-editor.test.tsx tests/unit/i18n/catalogue.test.ts --pool=forks` (de `console/`) | **3 files passed, 84 tests passed** (52 + 21 + 11) |
| Tipos (TS), projeto inteiro | `pnpm exec tsc --noEmit` (de `console/`) | exit 0, nenhuma saída |
| Lint (TS/ESLint + literais CSS) | `uv run python -m tools.console_gate lint` | exit 0, `eslint . && node scripts/check-css-literals.mjs` sem erro |
| Formato (Prettier) | `pnpm exec prettier --check` nos quatro arquivos tocados | os dois arquivos de teste precisaram de `--write` (reflow de linhas longas geradas pelas novas fixtures); confirmado limpo depois |
| Suíte completa do console + cobertura | `uv run python -m tools.console_gate test` | **146 arquivos, 2453 testes, todos verdes** (2447 antes desta fatia + 6 novos). Statements 93.92% (6306/6714), **Branches 90.17% (4690/5201)**, Functions 91.63% (1950/2128), Lines 95.93% (5828/6075) — piso de branches 90.00%, folga de 0.17pp, `exit 0` confirmado explicitamente. **Achado nomeado**: os quatro números batem, dígito a dígito, os que a Fatia 9 já relatava — investigado, não é execução obsoleta (confirmei os `data-testid` novos presentes no arquivo-fonte antes de rodar, e os cinco ciclos vermelho→verde de §77-79 já provam que o gate executa o código atual). A explicação mais provável: nenhuma das mudanças desta fatia introduziu função, branch condicional ou — sob o provedor `v8` de cobertura, mais grosso que o `istanbul`/babel — uma nova linha individualmente contável dentro de um elemento JSX já coberto (atributos como `data-testid="..."` numa linha própria, dentro de um elemento cujo componente-pai já era 100% exercitado, não necessariamente ganham sua própria entrada rastreável). Não persegui mais fundo — os cinco reversos temporários de §77-79 já são a prova direta de que cada teste novo depende do código que afirma testar. |
| Acceptance da feature (Playwright, build real) | `uv run python -m tools.spec_validation browser --feature specs_v6/040-autonomy-tres-abas --test console/tests/e2e/autonomy-tabs.acceptance.spec.ts` | **15 tests: 15 passed, 0 failed** — sem mudança em relação à Fatia 9 |
| `scroll-budget.spec.ts` (committed, real, `--no-build`) | idem, trocando o `--test` | **13 passed, 0 failed** |
| `transversal-rules.spec.ts` (committed, real, `--no-build`) | idem | **22 passed, 7 skipped, 0 failed** — sem mudança na contagem de exceções |

**Não rodado, e por quê**: `make verify`, `console-visual-accept`,
`console-e2e` completo — o despacho pede explicitamente para não rodar
nenhum dos três; nenhuma baseline visual foi capturada, aceita ou
sobrescrita nesta fatia. `pytest`/Python — nenhum arquivo Python foi
tocado nesta fatia (confirmado por `git status --porcelain`, só quatro
arquivos TS/TSX). `make check-constants`/`check-imports`/
`check-protocols`/`check-deps` — nenhuma constante nova, nenhum limite de
import cruzado; as duas classes novas (`max-h-96`, `overflow-y-auto`/
`overflow-auto`) são escala do Tailwind, não literais, e
`check-css-literals.mjs` (dentro do gate de lint acima) já cobre isso.
`tests/contract/fixtures` — nenhum arquivo de fixture tocado nesta fatia.

## 81. O que fica pendente, nomeado, não escondido — Fatia 10

- **T039–T045** (fase de fechamento) — sem nenhuma caixa marcada por mim;
  são explicitamente fora do escopo deste despacho.
- **A duplicação entre a tabela somente-leitura e a lista de editores por
  linha** (§79.1) — as duas mostram a mesma regra (escopo + matcher) de
  duas formas diferentes na mesma aba, e ambas agora rolam
  independentemente em vez de uma delas ser removida ou consolidada com a
  outra. Nenhuma FR desta spec pede consolidação; nomeio como achado de
  design porque um nó com muitas regras agora tem duas caixas de rolagem
  independentes na mesma aba, o que é correto em relação ao orçamento mas
  não necessariamente a forma mais simples.
- **`new-budget` não tem `id`, só `data-testid`** (`autonomy-editor.tsx:650`)
  — ao contrário de `new-rule` e `new-freeze`, que têm os dois
  (`:516-517`, `:595-596`). Nenhuma âncora `#new-budget` é usada em lugar
  nenhum desta feature, então isso não bloqueia nada que as FRs desta spec
  pedem — nomeio porque é uma pequena inconsistência real, encontrada
  lendo o arquivo, não corrigida porque nenhuma tarefa deste despacho pede
  um link para lá.
- **Os quatro sites de `Badge` com nível/decisão cru** (achado desde a
  Fatia 1, não desta fatia) — as linhas mudaram mecanicamente pelos
  wrappers de rolagem: `autonomy.tsx:557` (era `551`) e `:986` (era `980`)
  para os dois sites nesta tela; `autonomy-editor.tsx:762`/`763` (eram
  `754`/`755`) e `:840`/`841` (eram `832`/`833`) para os dois na seção de
  simulação; `override-editor.tsx:340`, não tocado por mim, sem mudança de
  linha. Nenhum `status={...}` foi alterado — mesmo achado, mesma decisão
  de não corrigir localmente, herdada de todas as fatias anteriores.
- **A duplicidade "Level"/"Level" entre o Select de uma regra existente e o
  do formulário "Create a rule"** (achado da Fatia 8, §57.2) — não tocada
  aqui; meus testes novos que precisavam de um rótulo "Level" único
  usaram fixtures com uma só regra (`ONE_RULE`/`RULES`, já existentes) ou
  não interagiram com o formulário de criação, então não esbarraram nela.
- **A ambiguidade de leitura do SC-008** (Fatia 1, §3.3) — segue para
  T040, não tocada aqui.

## 82. Arquivos alterados — Fatia 10

- `console/src/surfaces/settings/autonomy.tsx` — o `<div>` que envolve a
  tabela somente-leitura de regras ganhou `data-testid="rules-scroll"` e
  as classes `max-h-96 overflow-auto` (`:511-518`); nenhuma outra linha
  tocada (o rename temporário do `.sort()` para provar T028 foi desfeito
  antes de qualquer gate).
- `console/src/surfaces/autonomy-editor.tsx` — o `<div>` que envolve
  `allRules.map(...)` ganhou `data-testid="rule-editor-list"` e as classes
  `max-h-96 overflow-y-auto` (`:473-480`); nenhuma outra linha tocada (os
  quatro reverts temporários para provar T028/T030/T033 foram todos
  desfeitos antes de qualquer gate).
- `console/tests/unit/surfaces/settings/autonomy.test.tsx` — três
  `describe` novos entre "the rules table, over every scope kind..." e
  "the simulation section..." (`:624-745`: presença dos três controles de
  criação, ordem de resolução com fixture invertida, rolagem com 40
  regras); um `it` novo em "the loop into the raw editor"
  (`:1327-1341`: o alvo do CTA do empty state é o controle funcional, não
  só um id).
- `console/tests/unit/surfaces/autonomy-editor.test.tsx` — `BUDGETS`
  fixture nova (`:383-388`); um `it` novo espelhando o teste de freeze já
  existente, para budgets (`:417-434`); um `describe` novo com 40 regras
  como prop, provando a lista de editores como região de rolagem
  (`:467-511`).
- `specs_v6/040-autonomy-tres-abas/tasks.md` — caixas de T028, T030, T032
  e T033 marcadas, só essas quatro.
- `specs_v6/040-autonomy-tres-abas/controle.md` — esta seção.

Nenhum outro arquivo foi tocado. O script Playwright descartável
(`console/tests/e2e/_scratch-slice10-measure.spec.ts`) foi criado, usado
uma vez e apagado — não existe mais na árvore de trabalho, confirmado por
`git status --porcelain -- console/tests/e2e/`.

## 83. Tabela de estado — Fatia 11

**Fatia 11 de N — despacho de reparo.** As 45 tarefas de implementação
(T001–T038) já estavam feitas e commitadas, o acceptance da feature em
15/15. O orquestrador capturou screenshots das três abas e achou dois
defeitos reais que nenhum gate pega. Esta fatia corrige exatamente os dois,
nada além disso. Nenhuma caixa de `tasks.md` foi marcada — nenhuma das duas
correções corresponde a uma tarefa numerada; são reparos sobre trabalho já
marcado como feito.

| Peça | Estado | Detalhe |
|---|---|---|
| Defeito 1 — subtítulo citava a frase inteira do `<Select>`, com ponto final duplicado | **FEITO** | `console/src/surfaces/postures.ts:34-53` (`NAMED` + `postureName`), `console/src/i18n/en.ts:56-62`, `console/src/i18n/pt-BR.ts:46-52`, `console/src/surfaces/settings/autonomy.tsx:37,378,382`. Vermelho confirmado antes do fix — ver §84. |
| Defeito 2 — editor genérico vazio na aba Guardrails, dizendo "nenhum campo corresponde" com a busca vazia | **FEITO** | `console/src/surfaces/settings/autonomy.tsx:769-783` (condição `guardrailEditable.length > 0`). Vermelho confirmado antes do fix, reproduzindo o texto exato do defeito — ver §85. |
| Verificação: por que a lista chega vazia | **FEITO** | Não é "os três campos-array estão presentes mas o editor não consegue desenhá-los", como a hipótese do despacho supunha — é que o catálogo servido nunca declara os três caminhos. Ver §85 e §86. |
| Efeito colateral necessário: dois testes pré-existentes que davam o defeito 2 por correto | **FEITO** | `console/tests/unit/surfaces/settings/autonomy.test.tsx:957-961` e `console/tests/unit/surfaces/role-matrix.test.tsx:111-128`. Ver §87. |
| Pergunta "os três campos-array são editáveis hoje, em algum lugar" | **Investigado e respondido: não, em lugar nenhum** | Ver §86. Não construí editor novo, por instrução explícita. |
| `postures.test.ts` — três testes novos para `postureName`, vermelho confirmado, depois verde | **FEITO** | `console/tests/unit/surfaces/postures.test.ts:48-71`. |
| `autonomy.test.tsx` — dois testes novos para a condição do defeito 2, vermelho confirmado, depois verde | **FEITO** | `console/tests/unit/surfaces/settings/autonomy.test.tsx:1094-1163` (ausente quando vazio) e `:1169-1263` (ainda presente quando não vazio). |
| Gates | **FEITO** | typecheck, lint, prettier --check, test (coverage), acceptance da feature (15/15, browser real), visual (31/31, browser real). Ver §88. |

## 84. Defeito 1 em detalhe — o nome curto, e por que essas quatro palavras

### 84.1 A causa, confirmada por leitura

`autonomy.tsx` (antes da correção, linhas 375-383) construía o subtítulo das
três abas assim:

```tsx
: overriddenLevel === null
  ? message(locale, 'autonomy.subtitle', {
      node: nodeId,
      posture: postureLabel(locale, postureLevel),
    })
  : message(locale, 'autonomy.subtitle.override', {
      node: nodeId,
      posture: postureLabel(locale, overriddenLevel),
    });
```

`postureLabel` (`postures.ts:29-32`, inalterado) devolve a frase longa
escrita para a opção do `<Select>` — "Act and report — runs on its own and
tells somebody afterwards, whatever the risk." — com o próprio ponto final
embutido. Interpolada em `'…Posture now: {posture}, from a temporary
override'` (`en.ts`, chave `autonomy.subtitle.override`), o resultado é
literalmente "whatever the risk., from a temporary override" — dois sinais
de pontuação de duas frases diferentes colados. O mockup
(`specs_v6/mockups/settings-v6.html`, seção M2, `<p class="pagesub">Node:
deployment · Posture now: <span>propose-only</span></p>`) mostra um nome
curto no cabeçalho, nunca a frase descritiva.

### 84.2 A correção

`postures.ts:34-53` ganhou uma segunda tabela e uma segunda função, no
mesmo espírito de `DESCRIBED`/`postureLabel` — inclusive o mesmo
fallback-para-slug, pelo mesmo motivo (os níveis vêm do deployment, não
deste console):

```ts
const NAMED: Readonly<Record<string, MessageKey>> = {
  propose_only: 'autonomy.level.propose_only.short',
  act_on_low_risk: 'autonomy.level.act_on_low_risk.short',
  act_and_report: 'autonomy.level.act_and_report.short',
  act_silently: 'autonomy.level.act_silently.short',
};

export function postureName(locale: Locale, level: string): string {
  const key = NAMED[level];
  return key === undefined ? level : message(locale, key);
}
```

`autonomy.tsx:37` importa `postureName` (e deixou de importar `postureLabel`,
que passou a não ter mais nenhuma chamada direta neste arquivo — só
`postureLabels`, a plural, que ainda monta as opções do `<Select>`, chama
`postureLabel` internamente dentro de `postures.ts`; o TypeScript acusou o
import órfão como erro `TS6133` no primeiro rebuild, corrigido removendo-o).
`autonomy.tsx:378` e `:382` — os dois pontos onde o subtítulo é montado —
agora chamam `postureName` em vez de `postureLabel`. O `<Select>`
(`postureLabels`, chamado em `:416`, `:594`, `:846`) não foi tocado —
continua com as frases longas.

### 84.3 Os quatro nomes curtos escolhidos, e por que essa forma

**Inglês** (`en.ts:59-62`): "Propose only", "Act on low risk", "Act and
report", "Act silently". **Português** (`pt-BR.ts:49-52`): "Apenas propor",
"Agir em baixo risco", "Agir e reportar", "Agir em silêncio".

Não são texto novo inventado: são, literalmente, o prefixo de cada frase já
existente em `DESCRIBED`, antes do travessão — a mesma primeira cláusula que
já estava revisada e publicada nas duas línguas. `postureLabel('en',
'act_and_report')` já começa com "Act and report — …"; `postureName` devolve
só esse começo. Testei essa relação diretamente:
`postures.test.ts:50-58` afirma que `postureLabel(...)` **contém**
`postureName(...)` como substring — não é uma segunda vocabulário paralela,
é o título da própria frase.

Considerei manter o nome curto como o slug hifenizado ("propose-only", em
minúsculas), porque é exatamente o que o mockup mostra literalmente na M2:
`Posture now: propose-only`. Descartei essa forma depois de checar o
vocabulário irmão mais próximo dentro da mesma feature —
`autonomy.scope.*` (`en.ts:1213-1219`, `pt-BR.ts:1005-1011`), os nomes dos
tipos de escopo de uma regra, que vêm do mesmo tipo de slug do deployment
(`deployment`, `team`, `resource_kind`, …) e são traduzidos por completo em
pt-BR ("The whole deployment" → "O deployment inteiro", não um slug
hifenizado mantido igual nas duas línguas). E o teste que já existia para
`postureLabel` (`postures.test.ts`, "translates rather than carrying
English into another locale") já afirmava que `postureLabel('pt-BR',
'propose_only') !== postureLabel('en', 'propose_only')` para exatamente
esse vocabulário — a mesma garantia que escrevi para `postureName`
(`postures.test.ts:65-69`). Um slug hifenizado idêntico nas duas línguas
teria contrariado esse precedente direto, dentro do mesmo arquivo. O texto
do mockup, tratei como ilustrativo de "nome curto, não a frase" — não como
a grafia literal a copiar — porque é a única leitura compatível com o
resto do vocabulário desta mesma tela.

### 84.4 Vermelho confirmado, depois verde

Escrevi a implementação antes do teste por engano; percebi antes de rodar
qualquer coisa e corrigi a ordem: removi temporariamente o bloco `NAMED`/
`postureName` de `postures.ts` (cópia de segurança em
`/tmp/.../scratchpad/postures.ts.with-fix`), rodei
`pnpm exec vitest run tests/unit/surfaces/postures.test.ts` e vi

```
TypeError: postureName is not a function
 ❯ tests/unit/surfaces/postures.test.ts:50:19
```

nos três testes novos (`postures.test.ts:49-70`), com os 5 testes antigos
ainda verdes. Restaurei a implementação e os 8 passaram.

Para o subtítulo em si, adicionei duas asserções às duas suítes que já
existiam para ele (`autonomy.test.tsx:1588` e `:1614`) e rodei-as **antes**
de tocar `autonomy.tsx`. A primeira (`:1611`,
`expect(header).not.toHaveTextContent('runs on its own')`) falhou assim:

```
Expected element not to have text content: runs on its own
Received: …Node: org-northwind · Posture now: Act and report — runs on
its own and tells somebody afterwards, whatever the risk.Temporary override
```

A segunda (`:1656-1657`, a mesma asserção mais
`expect(header.textContent).not.toMatch(/\.\s*,/)`) falhou mostrando o
texto exato do defeito relatado:

```
Received: …Posture now: Act and report — runs on its own and tells
somebody afterwards, whatever the risk., from a temporary overrideTemporary
override
```

— o `"risk., from"` citado no despacho, ao vivo. Depois da correção em
`autonomy.tsx`, as duas passam; o arquivo inteiro
(`autonomy.test.tsx`, 54 testes nesse momento) ficou verde.

## 85. Defeito 2 em detalhe — o editor vazio, e a causa real (não a hipótese)

### 85.1 O que o despacho supôs, e o que eu confirmei

O despacho hipotetizou: os três campos-array continuam no catálogo, o
editor genérico só desenha tipos escalares, então eles "chegam" mas não
podem ser desenhados, e por isso a lista fica vazia. Pedi para verificar
antes de aceitar isso — e não é bem isso que acontece.

Li `guardrailEditable` (`autonomy.tsx:353-360`, inalterado):

```tsx
const guardrailEditable = guardrailCatalogue.filter(
  (entry) =>
    GUARDRAIL_PREFIXES.some((prefix) => entry.path.startsWith(prefix)) &&
    !GUARDRAIL_FIELDS.some((scalar) => scalar.path === entry.path),
);
```

`guardrailCatalogue` vem de `editableFields(dataOf(guardrailFields))`
(`editable.ts:86-112`), que só transforma em `EditableField` o que o
catálogo servido em `/v1/config/{node_id}/fields` já contém — não inventa
entradas. Fui direto na fonte que este console roda contra nos gates e no
e2e: `tools/mockplane/dataset/served.py`. `_CONFIG_FIELDS_DEFAULTED`
(`served.py:1144-1201`) declara **exatamente seis** caminhos sob os três
prefixos de guardrail (`policies.masking.enabled`, `policies.masking.level`,
`policies.guardrails.mode`, `policies.guardrails.ruleset`,
`policies.approvals.threshold`, `policies.approvals.expiry_hours`) — os
mesmos seis que `GUARDRAIL_FIELDS` (`guardrail-values.ts:44-65`) já desenha
na tabela embutida. `custom_patterns`, `disabled_rules` e
`autonomous_capabilities` **não aparecem em lugar nenhum** de `served.py`.
Ou seja: `guardrailCatalogue` já chega com só esses seis; o filtro de
exclusão de `guardrailEditable` os tira todos os seis; a lista final não é
"três campos que o editor não sabe desenhar" — é zero campos, porque o
catálogo servido nunca ofereceu um sétimo.

Confirmei que isso não é só uma lacuna do mock: mesmo contra o esquema real
(`platform/config_service/fields.py`), esses três campos são
`ConfiguredStrList = Annotated[tuple[str, ...], …]`
(`platform/config_service/schema/types.py:67`) — um array de strings puras,
não de objetos. A função `_entry_fields`, em `fields.py`, só preenche
`item_fields` quando o item do array é um objeto (`_descends`, `fields.py:
289-297`, exige `type == 'object' and properties`); para um array de
strings, `item_fields` fica `()` sempre, pelo próprio comentário do campo
(`fields.py:103-110`: "Empty for every other field, including an array of
strings"). Do lado do console, `isObjectList` (`preview.tsx:248-249`) exige
`type === 'array' && itemFields.length > 0`, e `EDITABLE_TYPES`
(`preview.tsx:49`) nunca inclui `'array'`. Então, mesmo se um deployment
real declarasse esses três campos no catálogo, o editor genérico não teria
como desenhar um controle para eles — só a linha inerte
`field-not-editable` (`preview.tsx:867-871`, rótulo "not editable"), nunca
o estado "nenhum campo corresponde a esta busca". A tela vazia com a busca
sem nada digitado só acontece porque a lista de campos que chega ao
`ConfigEditor` está genuinamente vazia — zero entradas, não três entradas
não-desenháveis.

### 85.2 A correção

`autonomy.tsx:769-783`:

```tsx
{/* Absent, not an empty result: a search box for a field list
    with nothing left to offer states something false to every
    reader. … */}
{writable && nodeId !== '' && guardrailEditable.length > 0 ? (
  <ConfigEditor
    nodeId={nodeId}
    fields={guardrailEditable}
    …
```

Uma condição a mais, não uma remoção — o `<ConfigEditor>` continua ali,
pronto para desenhar o dia em que um sétimo campo com prefixo de guardrail
existir no catálogo (por exemplo se o backend um dia passar a declarar um
oitavo campo escalar sob `policies.masking.`/`policies.guardrails.`/
`policies.approvals.` que `GUARDRAIL_FIELDS` ainda não absorveu).

### 85.3 Vermelho confirmado, depois verde

Escrevi dois testes novos em `autonomy.test.tsx` **antes** de tocar
`autonomy.tsx` e rodei os dois contra o código ainda com o defeito.

O primeiro (`:1094-1163`, fixture com exatamente os seis campos escalares,
nada mais) falhou mostrando literalmente a tela do despacho:

```
No field matches this search.
<input … name="config-field-search" type="search" value="" />
```

— busca vazia, "nenhum campo corresponde". O segundo (`:1169-1263`, os
mesmos seis campos mais um sétimo — `policies.masking.custom_patterns`,
tipo array com `item_fields` para renderizar como `ObjectList`) **já
passava antes da correção** — prova de que o caso não-vazio já funcionava,
então a correção certa era mesmo uma condição, não uma reescrita. Depois da
correção, os dois passam; a suíte completa de `autonomy.test.tsx` (56
testes) ficou verde.

## 86. A pergunta sobre os três campos-array — investigada, não corrigida

**Não, hoje não é possível editar `policies.masking.custom_patterns`,
`policies.guardrails.disabled_rules` nem
`policies.approvals.autonomous_capabilities` em lugar nenhum do console.**
Não construí controle novo para eles — instrução explícita do despacho.
Evidência, ponto a ponto:

1. **Não estão na tabela embutida.** `GUARDRAIL_FIELDS`
   (`guardrail-values.ts:44-65`) lista só os seis escalares. O comentário
   do próprio módulo (`guardrail-values.ts:26-31`) afirma que os três "stay
   reachable through their own editable list controls, not this summary" —
   procurei esse controle e não encontrei nenhum em `console/src`. Um
   `rg` por `custom_patterns|disabled_rules|autonomous_capabilities` em
   `console/src` só encontra três acertos, e nenhum é um controle: dois são
   entradas de roteamento/propriedade (`shell/config-ownership.ts:96,118,121`
   e `surfaces/settings/autonomy-tabs.ts:119,122,125` — dizem qual página
   é "dona" do campo, não desenham nada) e o terceiro é o próprio comentário
   citado acima.
2. **Não são desenháveis pelo editor genérico, em princípio, em nenhum
   backend real.** Ver §85.1 — `item_fields` vazio por construção para um
   `tuple[str, ...]`, então `isObjectList` é sempre falso e `EDITABLE_TYPES`
   nunca inclui `'array'`. O máximo que o editor genérico faria com eles,
   se algum dia aparecessem no catálogo, é uma linha inerte
   "not editable" — nunca um controle funcional.
3. **Nem chegam ao catálogo servido hoje.** `served.py` não declara os três
   caminhos (§85.1) — nas fixtures que este recurso roda contra em gate e
   e2e, eles não alcançam o console nem como linha inerte.
4. **`config-ownership.ts` afirma o contrário, sem prova.**
   `CONFIG_FIELD_OWNERS` (`console/src/shell/config-ownership.ts:96`,
   `:118`, `:121`) lista os três sob `settings-autonomy-guardrails`, como se um controle
   existisse hoje. O contrato Python que deveria travar essa alegação
   (`tests/contract/console/test_console_config_ownership.py`) define
   `reachable_fields()` (linhas 98-117) exatamente para excluir um array
   sem `item_fields` — mas só usa essa função para checar `no_control()`
   contra ela (`test_the_no_control_category_splits_the_way_its_docstring_
   says`, `test_no_field_the_raw_editor_can_reach_is_left_with_no_control`),
   nunca `owned()`. Um campo mal-classificado em `CONFIG_FIELD_OWNERS` não
   é pego por nenhum teste do arquivo — rodei a suíte inteira
   (`pytest tests/contract/console/test_console_config_ownership.py`, ver
   §88) e ela passa hoje, com os três campos mal-classificados dentro dela.
   Pelo próprio critério que o docstring do arquivo declara (linha ~21:
   "a field the raw editor **cannot reach either** — an object, or an array
   the schema describes no entry shape for"), os três pertencem à categoria
   (a) de `CONFIG_FIELDS_NO_CONTROL`, ao lado dos 9 que já estão lá — não
   a `CONFIG_FIELD_OWNERS`. Não toquei esse arquivo: é uma decisão sobre o
   contrato inteiro, fora do que este despacho pediu.
5. **O único lugar da árvore que os desenha como editáveis é um teste que
   inventa uma forma que nenhum backend produz.** `autonomy.test.tsx`,
   `'keeps the three array-shaped fields reachable through the generic
   editor…'` (linha ~989, não tocada) monta à mão um `item_fields` de um
   campo (`rule_id`, `capability`, …) para cada um dos três — uma forma que
   nem o mock (`served.py`, que nem declara os três) nem o esquema real
   (`fields.py`, que sempre devolve `item_fields=()` para uma string-lista)
   jamais produzem. O teste continua verde depois da minha correção (o
   `fields.length` dele é 3, não zero, então a condição nova não muda nada
   ali) — mas é uma fixture que discorda do backend que deveria dublar,
   exatamente a classe de defeito que este projeto pede para vigiar.

Nomeando o achado, não escondendo: hoje, sem um editor de lista para um
array de strings — que este despacho pediu explicitamente para não
construir — esses três campos não têm onde ser editados. Quem decidir
construir esse editor também deveria corrigir a alegação em
`config-ownership.ts` (mover os três de `CONFIG_FIELD_OWNERS` para
`CONFIG_FIELDS_NO_CONTROL`, ou construir o controle e mantê-los onde estão)
e a fixture do teste citado no item 5, para não seguir testando uma forma
que o backend nunca envia.

## 87. Efeito colateral necessário — dois testes que já davam o defeito por certo

Corrigir o defeito 2 quebrou dois testes que existiam antes desta fatia e
que, sem perceber, já tinham o próprio defeito codificado como
comportamento esperado. Os dois foram corrigidos como consequência direta
e necessária da correção — não é escopo novo, é o mesmo defeito 2
aparecendo em cobertura que já existia.

**`autonomy.test.tsx:830-966`** ("shows masking, guardrail and approval
fields with their effective value and origin") serve exatamente os seis
campos escalares — nem um a mais — e a asserção antiga (linha 961,
`expect(screen.getAllByTestId('config-editor')).toHaveLength(1)`) esperava
que o editor aparecesse mesmo vazio. É o defeito 2, ao vivo, num teste que
passava. Troquei para
`expect(screen.queryByTestId('config-editor')).not.toBeInTheDocument()`
(`:957-961`) e corrigi o comentário, que dizia "One editor on this tab" —
não é mais verdade.

**`role-matrix.test.tsx`** ("shows the most privileged role at least one of
them", a segunda ponta da matriz de papéis — a que prova que a matriz não
passa vazia por nada nunca renderizar) usava `serveScenario('populated')`
— a fixture real e commitada, não uma inventada por mim — e renderizava a
aba Guardrails esperando `config-editor` presente. `served.py` é a mesma
fonte por trás de `populated`; os mesmos seis campos, nada mais — então
esse `config-editor` também ficaria genuinamente ausente depois da correção.
Reapontei o teste para a aba Rules & windows (`:111-128`), cuja
`AdvancedConfigSection` (`advanced-config-section.tsx:150-197`) desenha o
mesmo `<ConfigEditor>` **sem nenhuma condição de vazio** — e os quatro
campos que ela cobre (`policies.autonomy.allow_unverifiable_actions`,
`dry_run`, `recurrence_threshold`, `recurrence_window_seconds`) estão
sempre declarados em `served.py:1275-1306`. Um alvo estável para "existe
pelo menos um", que não depende da pergunta que o defeito 2 resolve.

**Observação, não corrigida**: `AdvancedConfigSection`
(`advanced-config-section.tsx:188-196`) tem exatamente a mesma forma
desprotegida que `autonomy.tsx` tinha antes desta fatia — `writable &&
nodeId !== '' ? <ConfigEditor fields={editable} … /> : null`, sem checar
`editable.length > 0`. Hoje isso não se manifesta em lugar nenhum (os
quatro campos de Rules & windows sempre existem no catálogo), mas é a
mesma forma latente do defeito 2, num componente compartilhado por outras
páginas (Notifications, Schedules & destinations, …). Não toquei —
está fora dos dois defeitos nomeados neste despacho.

## 88. Gates rodados — Fatia 11

- `pnpm exec vitest run tests/unit/surfaces/postures.test.ts` — vermelho
  confirmado (3 falhas, `TypeError: postureName is not a function`), depois
  verde (8/8).
- `pnpm exec vitest run tests/unit/surfaces/settings/autonomy.test.tsx` —
  vermelho confirmado nas quatro asserções novas (duas de subtítulo, duas
  do editor vazio/não-vazio), depois verde (56/56 ao final da fatia).
- `pnpm exec vitest run tests/unit/surfaces/role-matrix.test.tsx` — 7/7,
  verde depois do realvo para `rules-windows`.
- `uv run python -m tools.console_gate typecheck` — limpo (`tsc --noEmit`,
  sem saída). Pegou um erro real no meio do caminho (`TS6133`, import
  órfão de `postureLabel`), corrigido antes deste resultado final.
- `uv run python -m tools.console_gate lint` — limpo (`eslint .` +
  `check-css-literals.mjs`, sem saída). Pegou um erro real
  (`@typescript-eslint/no-unnecessary-condition` num `?? ''` desnecessário
  que eu tinha escrito), corrigido antes deste resultado final.
- `pnpm exec prettier --check` nos sete arquivos tocados — "All matched
  files use Prettier code style!".
- `uv run python -m tools.console_gate test` (`vitest run --coverage`) —
  **146 arquivos de teste, 2458 testes, todos verdes** (linha de base:
  2453; os 5 a mais são os três de `postures.test.ts` e os dois de
  `autonomy.test.tsx`). Cobertura final:
  - Statements: 93.92% (6309/6717)
  - Branches: **90.18%** (4693/5204) — acima do piso de 90.00%, e acima da
    linha de base de 90.17% medida antes desta fatia. Os dois ramos que as
    correções acrescentam (`NAMED[level] === undefined` em `postureName`, e
    `guardrailEditable.length > 0` em `autonomy.tsx`) estão os dois
    exercitados nas duas direções pelos testes novos.
  - Functions: 91.63% (1951/2129)
  - Lines: 95.93% (5831/6078)
  - `echo $?` depois da chamada: `0`.
- `uv run python -m tools.spec_validation browser --feature
  specs_v6/040-autonomy-tres-abas --test
  console/tests/e2e/autonomy-tabs.acceptance.spec.ts` — rebuild real,
  backend mock real, **15 passed (4.9s)**, nenhuma falha.
- `uv run python -m tools.console_gate visual` — container Docker real,
  imagem pinada, **31 passed (20.0s)**. `autonomy-1440-light` (a única tela
  registrada em `console/visual/screens.json` na rota
  `/settings/autonomy-guardrails`) tem `"status": "pending"` — confirmei
  em `console/tests/visual/screens.spec.ts:52`
  (`.filter((each) => each.status === 'baselined')`) que uma tela pendente
  fica fora da comparação ativa; por isso o texto novo do subtítulo (que
  aparece nessa tela, já que ela captura a aba Posture por padrão) não
  arrisca nenhuma das 31. `agent-autonomy-1440-light` (a outra tela cujo
  nome menciona autonomy, rota `/agent?tab=autonomy`) não chama
  `postureLabel`/`postureName` em nenhum momento — passou, como esperado,
  sem relação com esta fatia.
- `uv run pytest -q tests/contract/console/` — **tentado, não concluído**:
  colidiu com o lock `console/.toolchain/tree-writing-suite.lock` de um
  processo concorrente (pid 2005179) já escrevendo na mesma árvore do
  console — outra sessão está ativa neste mesmo worktree agora (também
  visível em `git log`: três commits novos, `aa50f89`/`2b2766e`/`d8b1bad`,
  aterrissaram durante esta sessão, e `console/tests/e2e/
  transversal-rules.spec.ts` está modificado e não-commitado por ela, não
  por mim). Não tentei de novo — nenhum arquivo que toquei é lido por
  `test_console_config_ownership.py` ou `test_console_shell.py` (os dois
  únicos contratos Python que citam `config-ownership.ts`/`routes.ts`), e
  já tinha lido `test_console_config_ownership.py` inteiro para o §86.
  Risco julgado baixo, mas não é uma confirmação — nomeando como não
  rodado, com o motivo.
- `make verify`, `console-e2e` completo (a suíte inteira, não só o
  acceptance desta feature), `console-visual-accept` — não rodados,
  por instrução: pertencem ao orquestrador, e o segundo reescreveria
  baselines, o que este despacho proíbe fora de uma tarefa que o nomeie.
  `scroll-budget.spec.ts` e o resto de `transversal-rules.spec.ts` também
  não foram re-executados por inteiro — conferi por leitura (`rg` por
  `config-editor|search-empty|Posture now|runs on its own|postureLabel|
  act_and_report` nos dois arquivos) que nenhum dos dois cita qualquer
  elemento que as duas correções tocam, e `transversal-rules.spec.ts` está
  em edição pela sessão concorrente agora — rodá-lo correria o risco de
  medir um estado que nem é o dela nem é o meu.

## 89. O que fica pendente, nomeado, não escondido — Fatia 11

- **Os três campos-array não são editáveis em lugar nenhum do console.**
  Ver §86 — investigado a fundo, não corrigido, por instrução explícita
  deste despacho. Quem construir o editor de lista para eles também precisa
  corrigir `config-ownership.ts` (os três estão em `CONFIG_FIELD_OWNERS`
  sem prova) e a fixture de `autonomy.test.tsx:989` (que inventa uma forma
  de `item_fields` que nenhum backend produz para um array de strings).
- **`AdvancedConfigSection` tem a mesma forma desprotegida que o defeito 2
  corrigiu em `autonomy.tsx`.** Ver §87, observação final. Não se manifesta
  hoje (os quatro campos de Rules & windows sempre existem no catálogo),
  mas é o mesmo padrão, latente, num componente que várias páginas
  compartilham. Fora do escopo dos dois defeitos nomeados aqui.
- **`config-ownership.ts`'s próprio comentário de cabeçalho está com a
  contagem errada** para o grupo `settings-autonomy-guardrails`: diz
  "thirteen scalars, plus the four array-shaped ones" mas a lista real tem
  dez escalares e sete campos-array (contei os dezessete itens um por um,
  §86, item 4). Não corrigi — é uma inconsistência textual pré-existente,
  não uma das duas alegações que este despacho pediu para caçar.
- **`tests/contract/console/` não foi confirmado nesta sessão** por
  colisão com uma sessão concorrente ativa no mesmo worktree. Ver §88.
- Os quatro sites de `Badge` com nível cru (já registrados nas Fatias 8-9)
  seguem fora do escopo — não tocados, como o despacho pediu
  explicitamente.

## 90. Arquivos alterados — Fatia 11

- `console/src/surfaces/postures.ts` — `NAMED` (novo, `:34-46`) e
  `postureName` (novo, `:48-53`).
- `console/src/i18n/en.ts` — quatro chaves novas, `autonomy.level.*.short`
  (`:56-62`).
- `console/src/i18n/pt-BR.ts` — as mesmas quatro chaves, traduzidas
  (`:46-52`).
- `console/src/surfaces/settings/autonomy.tsx` — import trocado (`:37`,
  `postureLabel` saiu, `postureName` entrou); as duas chamadas do subtítulo
  trocadas para `postureName` (`:378`, `:382`); a condição do
  `<ConfigEditor>` de guardrails ganhou `&& guardrailEditable.length > 0`
  mais um comentário (`:769-783`).
- `console/tests/unit/surfaces/postures.test.ts` — import atualizado, novo
  `describe('what a posture is called, in short', …)` com três testes
  (`:48-71`).
- `console/tests/unit/surfaces/settings/autonomy.test.tsx` — comentário e
  asserção corrigidos numa suíte existente (`:957-961`); dois testes novos
  para a condição do editor vazio/não-vazio (`:1094-1263`); duas asserções
  novas em cada uma das duas suítes existentes do subtítulo (`:1588-1613`,
  `:1614-1658`), com um comentário corrigido na primeira.
- `console/tests/unit/surfaces/role-matrix.test.tsx` — o teste "shows the
  most privileged role at least one of them" reapontado de `tab:
  'guardrails'` para `tab: 'rules-windows'`, com o comentário reescrito
  para explicar por quê (`:108-128`).

Nenhum outro arquivo foi tocado. `console/tests/e2e/transversal-rules.spec.ts`
aparece modificado em `git status` mas não faz parte desta fatia — é
trabalho em andamento de uma sessão concorrente no mesmo worktree,
confirmado por `git log` (três commits novos aterrissaram durante esta
sessão) e pelo conteúdo do próprio arquivo, que não citei nem li em
detalhe. Nenhum arquivo foi staged, nenhum commit foi feito.

---

# Fecho — Fase 9 (T039–T045)

**45 de 45 tarefas marcadas.** Cada linha abaixo foi executada pelo orquestrador
e é a saída real do comando, não uma leitura.

## T039 — acceptance verde, comparado com o vermelho de T002

`autonomy-tabs.acceptance.spec.ts`: **15 passed, 0 failed**, build fresco via
`tools.spec_validation browser`. As nove alegações que T002 registrou vermelhas
(oito falhando, uma verde por já ser verdade) estão todas verdes, e cada uma
virou verde numa fatia nomeada: (a)(b)(c)(d) na fatia 4, (g) na 5 e na 6,
(h) na 5, (e) na 5 e na 6, (f) na 9, (i) na 8.

Duas alegações precisaram ser **reescritas** no caminho, e o motivo importa: (g),
(e), (f) e (i) afirmavam propriedades da tela inteira mas visitavam só a aba que
um endereço sem `?tab=` abre. O corte em abas transforma essa forma num defeito
ativo — a alegação passa a ser satisfeita movendo conteúdo para outra aba. (g)
chegou a ficar verde exatamente assim, com os três parágrafos intactos noutra
aba. As quatro percorrem as três abas e nomeiam qual falhou.

## T040 — suíte transversal na rota, e a ambiguidade resolvida

`transversal-rules.spec.ts`: **22 passed, 7 skipped, 0 failed**. Não havia
exceção a remover — `EXCEPTIONS` só guarda `/settings/alert-intake`. A rota roda
os bans de vocabulário e a contagem única de verdade.

A ambiguidade que a spec deixou aberta está resolvida e o comentário que a
justificava, corrigido: a rota está em `SCROLL_BUDGET_MEASURED_ELSEWHERE`, mas o
comentário dizia que era alcançada pelo endereço aposentado `/autonomy`. Falso
desde T011 — `scroll-budget.spec.ts` mede a rota **direto, por aba**, contra o
orçamento por aba, que é mais estrito que a regra transversal aplicaria. A
delegação entrega a rota a um instrumento mais rígido, não mais frouxo.

Registrado no mesmo comentário o que a medição **não** vê: o shell carrega
`min-h-screen`, então `scrollHeight` nunca reporta menos que um viewport. Uma aba
em exatamente 1080px está provada como não exigindo rolagem nenhuma, que é o que
um orçamento de rolagem pergunta; a altura do conteúdo abaixo dessa linha
simplesmente não é medida por este instrumento, e não precisa ser.

## T041 — paridade dos catálogos

`tests/unit/i18n/catalogue.test.ts`: **11 passed**. Toda chave nova nasceu nos
dois idiomas.

## T042 e T043 — o registro e as baselines

A entrada única `autonomy-1440-light` (pendente por altura acima do orçamento e
campos descobertos, ambos resolvidos) virou **três**, uma por aba, seguindo o
padrão que `/decisions` e `/agent` já usam. As três estão `baselined`, com
razão de aceitação escrita **depois** de eu olhar cada captura.

O baseline órfão que a divisão deixou foi removido; a checagem do registro o
nomeou por arquivo, que é como foi encontrado.

Seis baselines mudaram: as três novas, mais `agent-autonomy`, `agent-tools` e
`decisions`, que renderizam o vocabulário reescrito. `console_visual compare`
depois: **34 passed**.

**Armadilha de instrumento descoberta aqui**: `tools.console_visual` **não
reconstrói o build**. Uma comparação devolveu 34 verdes contra código obsoleto,
e o `accept` anterior capturou imagens que não refletiam o código. Corrigido
rodando `console_gate build` antes de `accept`, e as capturas revisadas são as
do código atual. Uma comparação visual que passa contra build velho é
indistinguível de uma que passa porque a tela está certa.

## T044 — o gate completo

`make verify`: **11875 passed, 25 skipped, 16 warnings em 590.46s**, exit 0.

Inclui lint, formato, tipos, contratos de importação (7/7), constantes,
protocolos, dependências, as 15 integrações com paridade total, os 29 exemplos
documentados, o gate do console inteiro (cobertura: statements 93.96%, branches
90.24% contra piso de 90.00%, functions 91.71%, lines 95.96%), as três suítes
Playwright e a visual.

**Duas tentativas anteriores não deram veredito e não foram falhas de teste**:
`Error 143` (SIGTERM) por limite de tempo do orquestrador. A primeira tentativa,
sim, falhou de verdade — dois testes em `settings-agent.spec.ts`, um spec que
nenhuma fatia rodou porque a validação por fatia cobria três specs e não o
projeto inteiro. Corrigido, e é a lição a carregar: rodar a suíte, não uma
seleção dela.

## T045 — o que este documento declara

Só o que os comandos acima provam. As onze seções de fatia acima trazem cada
vermelho observado com a mensagem, cada alegação que repousa em teste de unidade
em vez de navegador, e cada achado nomeado e não corrigido.

## O que fica aberto, nomeado, e não é bloqueio

- **14 campos** que o contrato de paridade estendido nomeia como não servidos
  pelo dataset de teste — integrações, observação, surfaces, transit. Numa lista
  de burndown explícita: passam hoje, e um décimo quinto entrando falha por nome.
- **Dois campos sem controle**, honestamente declarados: `guardrails.disabled_rules`
  e `approvals.autonomous_capabilities`, listas de string simples. Dar controle
  exige mudar o schema ou ensinar o walker a desenhar listas de string, o que
  viraria alcançabilidade para cinco campos irmãos de uma vez.
- **A camada `destructive` continua sem exercício** na fixture: nenhum dos cinco
  tools do dataset destrói nada, e nenhum foi inventado para preencher.
- **`approvals.tsx` interpola o slug cru** numa frase de empty state, protegido
  por um teste que assere o slug — a forma "teste que assere o defeito".
- **Na aba Rules & windows**: o painel de regras ainda intitulado como se
  salvasse uma postura, e as mesmas três regras na tabela e nos seletores.
- **`Badge status="active"`** em `screens/agent.tsx` — literal codificado, não
  slug de vocabulário; forma de defeito diferente.
