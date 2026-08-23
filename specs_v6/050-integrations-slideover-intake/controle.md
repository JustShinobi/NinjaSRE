# Controle — Integrações em slide-over e Alert intake enxuto

Estado abaixo verificado contra o código nesta árvore, HEAD `d8f4232` em
`feat/v6-scope-and-settings`, árvore limpa antes desta sessão. **Esta é a
fatia 0 de nove.** Só T001, T002 e T003 foram trabalhadas aqui — nenhuma tela
de console, nenhum acceptance spec, nenhuma rota de gateway foi tocada, por
instrução explícita do orquestrador. As fatias seguintes (acceptance-first em
diante) ainda não começaram.

## Tabela

| Peça | Estado | Detalhe |
|---|---|---|
| T001 — confirmar que a 001 aterrissou | FEITO | Ver seção "T001 — os dois números" abaixo. `vendor_packages()` = 15; `PROFILES` (fontes de intake) = 3. Pré-condição da feature confirmada de verdade, não assumida do relato do despacho. |
| T002 — estado de partida medido | FEITO | Ver seção "T002 — medições reais" abaixo. Três números medidos por navegador de verdade (Playwright, viewport 1920×1080), com o comando que os produziu. Dois deles contradizem a spec — registrado como achado, não ajustado para bater com o texto. |
| T003 — fixtures das duas telas | FEITO | Três estados de credencial adicionados ao catálogo real (`alertmanager`→verified, `loki`→stored/unverified, `ticketing`→failing) e um token com escopo de entrega adicionado a `identity_records()`. O lado do intake (uma fonte recebendo, duas caladas) **já existia** — verificado, não construído. Toda a mudança passou por `tools/mockplane/dataset/build.py`; nenhuma fixture foi editada à mão. Byte-identical rebuild, coerência entre cenários e contrato de API: 108/108 verdes. **Efeito colateral real e nomeado em `console/tests/unit/surfaces/settings-alert-intake.test.tsx` e em uma baseline visual — ver "O que fica pendente" abaixo.** |

## T001 — os dois números

Comando:

```
uv run python -c "
from gateway.webhooks.router import PROFILES
print(sorted(PROFILES.keys())); print(len(PROFILES))
from integrations._catalogue.discovery import vendor_packages
vp = vendor_packages()
print(vp); print(len(vp))
"
```

Saída real:

```
['alertmanager', 'generic', 'grafana']
3
('alertmanager', 'argocd', 'github', 'google_gemini', 'grafana', 'hermes',
 'kubernetes', 'loki', 'openobserve', 'prometheus', 'proxmox', 'pushover',
 'redis', 'signoz', 'telegram')
15
```

- **15 pacotes de vendor** em `integrations/` (confirmado por `vendor_packages()`,
  a mesma função que `integrations._catalogue.discovery.catalogue()` usa —
  não uma contagem de diretório paralela) e por `find integrations -maxdepth 1
  -mindepth 1 -type d ! -name "_*"`, que lista os mesmos 15 nomes.
- **3 fontes de intake** declaradas em `gateway/webhooks/router.py:PROFILES`
  (`alertmanager`, `generic`, `grafana`).

**Nuance que o texto literal de T001 não nomeia e que vale registrar**: T001
diz "`GET /v1/integrations` lista 15 integrações". O payload real de
`GET /v1/integrations` no cenário `populated` lista **18**, não 15 — as 15
reais mais três entradas fictícias que o plano de mock já carrega deliberadamente
(`metrics-store`, `chat`, `ticketing`; ver `integration_records()` em
`tools/mockplane/dataset/served.py`, e o T021/T034 do `controle.md` da 001).
Isso **não é uma divergência a corrigir** — é o desenho da 001, confirmado no
próprio `controle.md` daquela feature ("catálogo simulado filtrado às 15 + 3
fictícias pré-existentes"). A pré-condição real que T001 protege — o corte da
001 aterrissou — está confirmada pelos dois números acima, medidos direto da
declaração (`vendor_packages()`, `PROFILES`), não pela contagem de itens do
mock. Onde uma tarefa futura desta feature disser "o catálogo pós-corte", ela
tem de dizer qual dos dois números quer dizer: 15 no pacote, 18 no fixture do
navegador.

## T002 — medições reais

Todas as três medições rodaram contra o **build já existente do console**
(`console/.next/standalone/server.js`, presente na árvore antes desta sessão)
e o cenário `populated` **sem nenhuma das mudanças de T003** — servido pelo
`tools.mockplane` a partir dos arquivos committed tal como estavam no início
da sessão. Um spec Playwright descartável foi escrito, rodado uma vez e
apagado (nunca commitado, nunca staged) — `git status` confirmado limpo antes
e depois.

Comando (viewport declarado explicitamente no próprio spec, 1920×1080 —
`CONFIG_SCREEN_VIEWPORT_WIDTH_PX`/`CONFIG_SCREEN_VIEWPORT_HEIGHT_PX` de
`config/constants/surfaces.py`):

```
uv run python -m tools.console_e2e run -- tests/e2e/_zzz-t002-measure.spec.ts
```

Saída real (as três asserções passaram; os números vêm de `console.log`, não
de uma mensagem de falha):

```
T002 /integrations height=1336
T002 /integrations paginationCount=0
T002 /integrations catalogueItemCount=14
T002 /settings/alert-intake height=1202
T002 /integrations/prometheus scrollY=683
```

- **Altura de `/integrations` a 1080p: 1336px.** Orçamento
  (`CONFIG_SCREEN_SCROLL_BUDGET_VIEWPORTS = 2.0` × 1080px = 2160px): dentro,
  com folga.
- **Controle de paginação: ausente, não apenas inócuo.** `paginationCount=0` —
  o elemento com `data-testid="pagination-landmark"`
  (`console/src/components/navigation.tsx`) não existe no DOM. Lendo
  `console/src/surfaces/integration-catalogue.tsx:183`: `{pages > 1 ? (
  <Pagination .../> ) : null}`. Com 18 itens e
  `INTEGRATIONS_CATALOGUE_PAGE_SIZE = 24` (`config/constants/surfaces.py:365`),
  `pages` computa 1, então a Paginação **nunca renderiza hoje** — não é "um
  controle que não faz nada visível", é um controle ausente por aritmética.
  A tarefa que remove a paginação (T013) ainda é real: a prop `pageSize` e a
  constante continuam na árvore, um número órfão esperando o catálogo crescer
  de novo para reaparecer silenciosamente.
- **`catalogueItemCount=14`**: contagem de `data-testid="catalogue-item"`, que
  só existe dentro do grid "Available" (`IntegrationCatalogueGrid`). Bate a
  aritmética do fixture pré-T003: 18 totais − 2 sugeridas (`metrics-store`,
  `redis`) − 2 conectadas (`chat` saudável, `ticketing` degradada) = 14. As
  seções Connected/Suggested usam outro marcador (não contadas aqui) —
  consistente com a leitura de `screens/integrations.tsx:253-258` (linha
  citada abaixo).
- **Altura de `/settings/alert-intake` a 1080p: 1202px.** **Achado que
  contradiz a spec**: FR-067/SC-006 dizem "hoje: 2,1 [viewports]" (2268px+).
  A medida real é 1202px ≈ **1,11 viewports**, folgadamente dentro do
  orçamento de 2. A spec está descrevendo o estado de **antes da 001** (sete
  fontes quase idênticas); a 001 já reduziu para três e o defeito de altura
  já não existe. Isso bate com o que `console/tests/e2e/scroll-budget.spec.ts`
  já assume: `/settings/alert-intake` está na lista `SCREENS` **sem**
  `expectedOverBudget` — o teste já espera que o orçamento seja cumprido, não
  que esteja estourado. Registrado como achado, não ajustado para bater com o
  texto da spec, como a instrução do despacho pediu.
- **Deep-link `/integrations/prometheus`: aterrissa em `scrollY=683`, não em
  0.** Esse é o defeito real que FR-022/SC-003 existem para corrigir — a
  posição não é o topo do catálogo. (Não é o "rodapé de uma página de
  2.141px" que a spec descreve — esse número é de antes do corte da 001, com
  85 itens; a página de hoje é bem mais curta — mas a propriedade que falha é
  a mesma: o deep-link não aterrissa no topo.) Nenhuma correção foi tentada
  aqui — geometria do `Overlay`/`Drawer` é da Fase 5 (T017-T019), fora desta
  fatia.

Arquivo descartável usado, apagado depois de rodar, nunca commitado nem
staged: `console/tests/e2e/_zzz-t002-measure.spec.ts` (confirmado por
`git status --short console/tests/e2e/` vazio antes e depois).

## T003 — o que foi mudado no gerador, e por quê

Único arquivo editado: `tools/mockplane/dataset/served.py`. Nenhuma fixture
foi tocada diretamente — tudo passou por
`uv run python -m tools.mockplane build`, que reescreveu 227 arquivos em 6
cenários e só **dois de fato mudaram de conteúdo**:
`fixtures/scenarios/populated/integrations.json` e
`fixtures/scenarios/populated/tokens.json`. Confirmado por `git diff --stat`
depois do build — nenhum outro cenário (`empty`, `first-run`, `restricted`,
`incident-live`, `audit-flooded`) foi tocado, porque nenhum deles constrói os
records `integrations` ou `tokens` a partir de `identity_records()`/
`integration_records()` (cada um constrói seu próprio subconjunto menor, ou
nem inclui esses slugs — verificado lendo `records_for()` e cada função
`*_records()` de `tools/mockplane/dataset/build.py`).

### 1. Token com escopo de entrega (`webhook.deliver`)

`tools/mockplane/dataset/served.py`, dentro de `identity_records()` — novo
token `tok-0003`, entre `tok-0002` (scheduler) e `*_bootstrap_tokens()`:

```python
{
    "token_id": "tok-0003",
    "name": "Alert delivery",
    "user_id": AUTOMATION,
    "team_node_id": PLATFORM_TEAM_NODE,
    "scopes": [Permission.WEBHOOK_DELIVER.value],
    "created_at": at(days=6, hours=4),
    "expires_at": None,
    "last_used_at": at(minutes=12),
    "revoked": False,
    "description": "Authenticates inbound Alertmanager webhook deliveries.",
},
```

Antes desta sessão, **nenhum** dos 17 tokens do cenário `populated` (2
nomeados + 15 de bootstrap) carregava `webhook.deliver` — confirmado lendo o
arquivo antes de editar. O escopo vem de `Permission.WEBHOOK_DELIVER.value`
(a mesma declaração que `ingress_records()` já lia para `delivery_permission`
— `platform/identity/permissions.py`), nunca do literal `"webhook.deliver"`
escrito à mão. `last_used_at=at(minutes=12)` é deliberadamente o mesmo
instante que `_TRANSIT_ACCEPTED_AT` (a entrega aceita do Alertmanager) —
mesmo token, não coincidência de horário. O nome "Alert delivery" é o mesmo
que o template de emissão do formulário já usa
(`settings.machineTokens.template.alertDelivery.name`), não inventado.

### 2. Um vendor real conectado e verificado — `alertmanager`

`integration_records()` chamava `integration_catalogue(configured=frozenset())`
— com o conjunto vazio, **todo** vendor real reporta `unconfigured`
(`integrations/_catalogue/discovery.py:catalogue()`, cláusula
`if configured is not None and name not in configured`). Passou a chamar:

```python
ledger = HealthLedger(clock=lambda: _CAPTURED)
ledger.record_success(_VERIFIED_INTEGRATION)  # "alertmanager"
real_entries = [
    _catalogue_integration_record(entry)
    for entry in integration_catalogue(
        health=ledger,
        configured=frozenset({_VERIFIED_INTEGRATION, _STORED_UNVERIFIED_INTEGRATION}),
    )
]
```

`alertmanager` foi a escolha deliberada, não arbitrária: é o vendor que a
própria intake, as regras e o receiver deste deployment já apontam
(`_LIVE_SOURCE = "alertmanager"` em `ingress_records()`/`transit_records()`,
a entrega aceita de verdade no ledger de trânsito), e é a rota que T044
(fase 11, fora desta fatia) precisa que esteja **verificada** para capturar o
painel de credencial conectado — não o formulário vazio. `health` e
`health_detail` vêm de `HealthLedger.record_success()`, a mesma função que
`gateway/http/routes/integrations.py` chama de verdade — nenhum valor
hand-typed. `health_detail` sai vazio (`""`), porque é isso que
`record_success` sempre produz — igual ao que o gateway real produziria.

### 3. Um vendor real guardado e nunca verificado — `loki`

Mesma chamada acima: `loki` entra em `configured` mas **não** recebe
`ledger.record_success()`/`record_failure()`. `catalogue()` resolve isso como
`HealthStatus.UNKNOWN` via `HealthLedger.status_of()` (não há registro para
`loki`, então cai no default `HealthRecord(status=UNKNOWN)`) — exatamente
"credencial guardada, nunca verificada". `screens/integrations.tsx:253-256`
já lê esse estado hoje: `// Connected is every health but 'unconfigured' —
'unknown' (stored, never checked) and 'degraded' (failing) both count.`
Escolhido em vez de `prometheus` (o outro vendor citado no despacho) de
propósito: `prometheus` é o alvo da medição de deep-link de T002, e ficou
intocado — antes e depois de T003 ele é exatamente `unconfigured`, então a
medição de scroll de T002 não muda de significado se refeita depois desta
fatia.

### 4. Um vendor "falhando" com chip crítico — `ticketing` (fictício)

Estado anterior: `"health": "degraded"`, `"health_detail": "the last
verification timed out"`. Isso renderiza como chip **Degraded**
(`console/src/design/status.ts`: `degraded: { role: 'warning', shape:
'triangle' }`) — um aviso, não o "chip crítico" que o edge case de US3 pede
("permanece na seção Connected com chip crítico e diagnóstico"). O vocabulário
canônico de credencial já declara uma palavra própria para isso — `failing`
— com role `danger`/shape `square`
(`console/src/design/status.ts` `DECLARED.failing`) e rótulo já traduzido nos
dois idiomas (`status.credential.failing` = "Failing" / "Falhando",
já existente em `console/src/i18n/{en,pt-BR}.ts` — não escrito por mim).
Mudado para:

```python
"health": "failing",
"health_detail": "the stored credential was rejected by the vendor",
```

**Nota de honestidade sobre esta escolha**: `HealthStatus`
(`integrations/_catalogue/entry.py`) é um `StrEnum` fechado com só quatro
membros — `HEALTHY`, `DEGRADED`, `UNKNOWN`, `UNCONFIGURED`. **Não existe**
`HealthStatus.FAILING`; nenhum caminho real do backend pode hoje produzir a
string `"failing"` para uma integração. Este valor só existe porque a entrada
`ticketing` é uma das três fictícias, hand-typed em `served.py` desde a 001 —
nunca passa pelo enum Python, exatamente como `"unconfigured"`/`"healthy"`/
`"degraded"` já não passavam antes de mim. Três fatos sustentam que isso é a
leitura certa, não um atalho:
1. O próprio docstring de `integration_records()`, escrito antes desta sessão,
   já narrava "one connected and **failing**" como o papel pretendido dessa
   entrada — a palavra já estava lá, só a string não batia com ela.
2. `console/src/design/status.ts`'s `CREDENTIAL_STATUS_ALIASES` já declara
   `failing: 'failing'` como mapeamento identidade — uma palavra que o
   vocabulário do console já espera receber de algum backend, mesmo que
   `HealthStatus` (Python) nunca a produza hoje.
3. FR-042 da própria spec já usa a palavra "falhando" por extenso ("nunca
   como falhando"), e o edge case de US3 pede "chip crítico" — que só o
   `danger`/`square` de `failing` entrega; `degraded` é `warning`/`triangle`.

Nenhum teste de contrato (`tests/contract/fixtures/`) restringe os valores
possíveis de `health` a um enum — `IntegrationView.health` em
`gateway/http/routes/integrations.py` é tipado como `str` livre, sem `enum`
declarado no schema OpenAPI, então isto **não** viola nenhum contrato hoje
verificável. Ainda assim, é uma decisão de design que a Fase 6 (T009, T022-
T026, dona da distinção completa de estado de credencial) deve revisar
deliberadamente — não apenas herdar. Se aquela fase decidir que "Failing" deve
nascer de uma extensão real de `HealthStatus` em vez de um literal do mock,
este valor é o primeiro lugar a ajustar.

**Verificado, não assumido** — leitura direta do resultado da própria função
depois da mudança:

```
metrics-store -> unconfigured | no credential is stored for this node
chat -> healthy | verified 3 hours ago
ticketing -> failing | the stored credential was rejected by the vendor
alertmanager -> healthy |
loki -> unknown |
```

Distribuição final de saúde no catálogo de 18 itens do cenário `populated`
(contada no JSON regenerado): `unconfigured: 14` (13 vendors reais +
`metrics-store`), `healthy: 2` (`chat`, `alertmanager`), `failing: 1`
(`ticketing`), `unknown: 1` (`loki`). `known_gaps` continua em 9 — intocado.

### 5. O lado do intake — já existia, verificado, não construído

T003 também pede "três fontes de intake com uma recebendo e duas caladas".
Lido direto do `transit-ingress.json`/`ingress-sources.json` **committed, sem
nenhuma mudança minha**:

```
alertmanager | never_delivered=False | last_outcome='accepted'  | counts={'accepted': 14, 'duplicate': 2} | rejections=0
generic      | never_delivered=True  | last_outcome=''          | counts={}                                | rejections=0
grafana      | never_delivered=False | last_outcome='rejected'  | counts={'rejected': 6}                   | rejections=1
window_hours = 24
```

`alertmanager` é a única expandida/"Receiving"; `generic` e `grafana` são as
duas que a tela vai desenhar em uma linha (`generic` por nunca ter entregado;
`grafana` por ter só rejeições, sem nenhuma aceita — o caso do edge case
"fonte com rejeições recentes", que a spec exige continuar visível em vez de
virar "nada chegou"). **Nada foi alterado aqui** — este estado já existia
antes desta sessão. Registrado como característica confirmada, não como
correção.

## Vermelho / verde confirmados nesta fatia

T001-T003 não são test-first no sentido do acceptance spec (essa é a Fase 2,
fora desta fatia) — são setup e fixtures. O que foi de fato confirmado,
vermelho-antes/verde-depois, é a suíte de contrato do dataset:

- **Antes** desta sessão: `tools/mockplane/dataset/served.py` sem o token de
  entrega e sem os três estados de credencial reais (confirmado por leitura
  direta do arquivo antes de editar — colado nas seções acima).
- **Depois**: `uv run python -m tools.mockplane build` — `wrote 227 files
  across 6 scenarios`; `git diff --stat` mostrando exatamente os dois
  arquivos esperados mudados.
- `uv run pytest tests/contract/fixtures/ -q` → **108 passed**, incluindo
  `test_two_builds_of_one_scenario_are_byte_identical`,
  `test_rebuilding_the_dataset_reproduces_what_is_committed`,
  `test_every_reference_in_every_scenario_resolves[...]`,
  `test_every_scenario_reads_as_a_coherent_history[...]`,
  `test_every_fixture_validates_against_the_api_document[...]` (todos os 6
  cenários), `test_every_actor_kind_is_one_the_backend_actually_declares`,
  `test_every_audit_outcome_is_one_the_backend_actually_declares`,
  `test_every_principal_kind_is_one_the_backend_actually_declares`,
  `test_every_side_effect_level_is_one_the_backend_actually_declares`.
- `uv run pytest tests/unit/tools/mockplane/ -q` → **183 passed** (inclui
  `test_every_declared_scenario_loads`, `test_generating_it_twice_gives_the_same_thing`,
  `test_serving_one_scenario_twice_is_byte_identical_timestamps_included`).
- `uv run ruff check tools/mockplane/dataset/served.py` → limpo.
- `uv run ruff format --check tools/mockplane/dataset/served.py` → já
  formatado.
- `uv run mypy tools/mockplane/dataset/served.py` → `Success: no issues
  found in 1 source file`.

## O que fica pendente, nomeado, não escondido

### Efeito colateral real e esperado da adição do token — para a próxima fatia que tocar `alert-intake.tsx`/Machine tokens

Adicionar um token real de escopo `webhook.deliver` ao cenário `populated`
**necessariamente** aparece em qualquer tela que leia `/identity/tokens` sem
filtrar por escopo — não havia como evitar isso e ainda assim fechar a lacuna
que o despacho pediu (FR-059/FR-062/FR-056 inalcançáveis por navegador). Dois
efeitos, medidos, não hipotéticos:

1. **`console/tests/unit/surfaces/settings-alert-intake.test.tsx` — 4 de 37
   testes agora vermelhos**, todos dentro de `describe('the delivery token
   control')`, todos porque a premissa deles era "o cenário `populated` não
   tem nenhum token com `webhook.deliver`" — premissa que era verdadeira até
   esta sessão e que T003 existe justamente para tornar falsa:
   - `:405-415` "says nothing has authenticated deliveries yet, when no
     token carries the permission" — esperava
     `/no delivery token/i`, recebe `Authenticated with delivery token Alert
     deliveryRotate`.
   - `:417-424` "names the delivery token once one has actually
     authenticated deliveries with it" — usa `serveWithADeliveryTokenNamed('am-cluster')`,
     que **soma** um token extra ao invés de partir de zero; esperava conter
     só `'am-cluster'`, recebe `'Alert delivery'` (o meu, criado
     `2026-08-01T08:00:00+00:00`, é mais recente que o injetado
     `2026-08-01T00:00:00+00:00` por 8 horas — então "o mais recente" agora é
     o meu, não o do teste).
   - `:437-484` "picks the most recently issued token when more than one
     carries the permission" — mesma causa: agora há três candidatos, não
     dois, e a ordenação por `created_at` muda o vencedor.
   - Um quarto teste ("never counts a revoked token…", por volta de `:505-522`)
     — mesma família.
   Confirmado rodando **a suíte inteira de verdade**, não uma amostra:
   `cd console && uv run python -m tools.console_gate test` → **2492 passed,
   4 failed, de 2496 totais** (nenhum teste foi criado ou removido — os
   mesmos 2496 de antes, quatro viraram vermelhos). Nenhum outro arquivo
   afetado — confirmado rodando `delivery-token.test.tsx` (a suíte do
   componente `DeliveryToken` isolado, 29 testes, com props próprias, não lê
   `populated`), `machine-token-groups.test.tsx` (20 testes, props próprias),
   `settings-machine-tokens.test.tsx` (4 testes) e `integrations.test.tsx`
   (29 testes) — todos verdes, intocados.
   **Achado que vale mais que o defeito**: o texto recebido —
   `Authenticated with delivery token Alert delivery` seguido de `Rotate` —
   bate palavra por palavra com o que FR-059/FR-061 pedem
   ("Authenticated with delivery token `<nome>`", com ação de rotação). O
   mecanismo de nomear o token e oferecer rotação **já existe e já
   funciona** em `console/src/surfaces/settings/alert-intake.tsx:511-549`
   (`deliveryTokenName`, `<DeliveryToken permission=... labels={{issue/rotate,
   issuing/rotating, shownOnce, failed, unreachable}} />`) — construído,
   pelo histórico do arquivo, na 030 (`git log`: último commit a tocar o
   teste é `554fc54`). O que faltava não era o mecanismo — era um dado real
   para ele ler. Vale a pena a Fase 8 (US5, T031-T035) partir dessa
   descoberta: o rótulo de `DeliveryToken` ("issue"/"rotate"/"shownOnce")
   sugere uma ação **inline** (emite/rotaciona no próprio card), não uma
   navegação — o que, se confirmado, é uma lacuna real contra FR-062
   ("Rotacionar DEVE levar a Machine tokens já filtrada"), não coberta por
   nenhum dos 37 testes deste arquivo (nenhum afirma o destino do link
   "Rotate"). Não fui além disso — não li `DeliveryToken` por inteiro nem seu
   handler de clique; é uma pista para quem entrar em T034, não uma conclusão.
2. **Baseline visual `console/visual/baselines/machine-tokens-1440-light.png`
   agora diverge.** `uv run python -m tools.console_gate visual` (dentro de
   `console/`) → **33 passed, 1 failed**: `machine-tokens-1440-light matches
   its baseline` — "Expected an image 1440px by 1729px, received 1440px by
   1890px. 5694 pixels (ratio 0.01...) are different." A tela
   `/settings/machine-tokens` lista todo token que não é sessão de
   navegador — o novo `tok-0003` vira uma linha nova, a página cresce 161px.
   **Nenhuma baseline foi recapturada nem aceita** — rodei só a comparação
   (`console_gate visual`, que não escreve nada), nunca
   `console-visual-accept`, exatamente como a instrução do despacho e a regra
   geral proíbem. Nenhuma outra das 34 telas registradas mudou — inclusive
   confirmando que não existe hoje nenhuma baseline para `/integrations` ou
   `/integrations/<vendor>` (a entrada antiga apontava para
   `/integrations/slack`, removida pela própria 001 — ver o `controle.md`
   dela, T034 — e T044 desta feature é quem a registra de novo).
   `/settings/machine-tokens` **não é uma rota desta feature** (as rotas de
   050 são `/integrations`, `/integrations/<name>`,
   `/integrations/not-covered`, `/settings/alert-intake`,
   `/settings/schedules-destinations`), então nem T045 nem T046 — como
   escritas hoje — nomeiam essa baseline. **Isto precisa de uma decisão do
   orquestrador**: ou T046 é ampliada para incluir
   `machine-tokens-1440-light` como uma quarta captura deliberada (a razão
   registrada diria que o card do novo token de entrega é o que mudou), ou
   alguém identifica isso como uma tarefa própria antes do `make verify`
   final da feature — sem isso, `make console-visual`/`make verify` ficam
   vermelhos por um motivo que nenhuma tarefa nomeada cobre.

Nenhum dos dois itens acima é meu para consertar nesta fatia — tocar
`console/src/surfaces/settings/alert-intake.tsx`, seus testes, ou aceitar uma
baseline visual são exatamente as três coisas que a instrução desta fatia
proibiu ("não toque uma tela de console... não toque o gateway... baselines
só com tarefa nomeada"). Registrado aqui para a próxima fatia herdar o fato,
não a surpresa.

### Não tocado, deliberadamente, com a razão

- **`_INTEGRATION_READINESS`** (`tools/mockplane/dataset/served.py:1957`),
  consumida só por `setup_records()`/`checklist_record()` — a lista de
  integrações do checklist de primeiro uso (`/first-run`, ou onde quer que o
  produto linke o checklist), tela **fora do escopo desta feature**. Ela
  continua listando só as três fictícias (`chat` verified, `metrics-store`
  absent, `ticketing` configured). Cogitei adicionar `alertmanager`/`loki`
  lá para manter as duas listas "de acordo", mas essa lista é ilustrativa por
  design (`source=True`/`runtime=True`/`investigated=True` são booleans
  passados à parte, não derivados de contar essa tupla) — não há nenhuma tela
  hoje que compare o total desse checklist com o total de `/v1/integrations`
  e reprove se divergirem. Deixado como está; se alguém achar uma tela que
  faça essa comparação, é uma descoberta nova, não um efeito desta fatia.
- **Nenhum evento de auditoria novo** para `tok-0003`. `tok-0001` (a sessão
  do console) também não tem evento de `token.create` correspondente — não é
  uma regra desta base de dados que todo token tenha um. Adicionar um só
  para o meu token seria inventar uma obrigação que não existe hoje, com
  risco de deslocar a ordenação (os `event_id` parecem crescer com a
  recência) sem nenhum ganho medido.
- **`prometheus` deixado exatamente como estava** (`unconfigured`), de
  propósito — ver a razão na seção 3 acima: é o alvo da medição de deep-link
  de T002, e mantê-lo intocado significa que a medição continua válida se
  alguém a refizer depois desta fatia.

## Descobertas que mudam como rodar os gates ou ler as fixtures daqui em diante

- **`GET /v1/integrations` no cenário `populated` sempre devolveu 18, nunca
  15** — mesmo antes desta sessão. Qualquer teste ou spec futuro desta
  feature que precise do número "15" tem de pedir explicitamente aos pacotes
  de vendor (`vendor_packages()`, ou o `.length` de uma lista filtrada por
  `parity`/origem), nunca ao payload cru do endpoint.
- **A Paginação de `/integrations` já não renderiza hoje** (`pages=1` com 18
  itens ≤ `INTEGRATIONS_CATALOGUE_PAGE_SIZE=24`) — um teste que afirme "o
  controle de paginação existe e não faz nada" está testando um estado que
  já não existe; o certo é afirmar a ausência do elemento, que é o que T012/
  T013 vão precisar codificar.
- **`/settings/alert-intake` já está dentro do orçamento de rolagem hoje**
  (1202px de 2160px) — a tarefa remanescente ali (T027-T030) é vocabulário e
  forma dos chips, não mais espaço.
- **Qualquer fatia futura que adicione um token ao cenário `populated` vai
  esbarrar no mesmo par de efeitos colaterais** (Machine tokens ganha uma
  linha; qualquer teste que afirme "populated não tem token de escopo X"
  fica peremptoriamente falso). Vale procurar deliberadamente por esse padrão
  antes de adicionar o próximo, em vez de descobrir depois.
- **A adição de estado de credencial ao catálogo real não quebrou nenhum
  teste** — só a adição do token quebrou algo. Os dois tipos de mudança têm
  raios de alcance muito diferentes nesta árvore, vale lembrar ao planejar a
  ordem de fatias futuras.

## Gates rodados nesta fatia (reais, não make verify)

| Gate | Comando | Resultado |
|---|---|---|
| Sintaxe do arquivo editado | `python -c "import ast; ast.parse(...)"` | OK |
| Lint Python | `uv run ruff check tools/mockplane/dataset/served.py` | limpo |
| Formatação Python | `uv run ruff format --check tools/mockplane/dataset/served.py` | já formatado |
| Tipagem Python | `uv run mypy tools/mockplane/dataset/served.py` | `Success: no issues found in 1 source file` |
| Contrato de fixtures | `uv run pytest tests/contract/fixtures/ -q` | **108 passed** |
| Suíte do mockplane | `uv run pytest tests/unit/tools/mockplane/ -q` | **183 passed** |
| Contrato do console (gate completo, via harness próprio) | `uv run pytest tests/contract/console -q` | **454 passed, 2 failed** — `test_console_gate.py::test_the_same_check_passes_once_the_fixture_is_gone[test]` e `test_console_visual_regression.py::test_the_untouched_baselines_still_match`; ambas são o mesmo efeito colateral nomeado acima, refletido pelo harness de contrato (não uma terceira causa nova) |
| Suíte unitária real do console, com cobertura | `cd console && uv run python -m tools.console_gate test` | **2492 passed, 4 failed** (de 2496) — os quatro nomeados acima |
| Visual, só comparação (nunca `accept`) | `cd console && uv run python -m tools.console_gate visual` | **33 passed, 1 failed** — `machine-tokens-1440-light`, nomeado acima |
| `make verify` | não rodado | do orquestrador, por instrução explícita desta fatia |

Nota sobre instrumento: o primeiro `pytest tests/contract/console` desta
sessão rodou com `| tail -50` e reportou código de saída 0 ao harness de
background mesmo tendo **2 falhas reais** — o mesmo efeito que o despacho
avisou sobre `make verify` embrulhado num pipe. Só a leitura do texto (não do
código de saída) revelou as duas falhas; os dois reruns seguintes rodaram sem
pipe e confirmaram a mesma contagem.

---

# Fatia 1 de nove — T004 e T005

Estado abaixo verificado contra o código nesta árvore, HEAD `8b446c1` em
`feat/v6-scope-and-settings`, árvore limpa antes desta sessão (confirmado por
`git status --short`). **Só T004 e T005 foram trabalhadas aqui**, por
instrução explícita do orquestrador — nenhuma tela de console, nenhum
componente, nenhuma rota de gateway, nenhuma string de i18n e nenhuma fixture
committed foram alteradas por esta fatia. A única exceção deliberada e
autorizada pelo próprio despacho é `console/tests/e2e/transversal-rules.spec.ts`
— um arquivo de teste, não uma tela — descrita na seção própria abaixo.

Commits vistos no branch entre o início desta sessão e agora (`d8f4232`,
`0216fa6`, `476ee1b`, `03b2bd8`, `a6c4136`) são do orquestrador, entre fatias —
não investigados, conforme instrução.

## T004 — o arquivo

`console/tests/e2e/050-integrations-slideover-intake.acceptance.spec.ts` (768
linhas, 24 testes em 9 `describe`), codificando exatamente os seis grupos que
`tasks.md` lista para T004 — Catálogo, Slide-over, Integração verificada,
Intake, YAML e confiança, Cadeia — e nada além deles. Nenhuma alegação de
outra parte da spec (placeholder de endereço descoberto pelo estate, rodapé de
Alert intake nomeando fontes removidas, "nenhuma sugestão", mais de um
delivery token) foi codificada aqui — pertencem a fases posteriores e estão
listadas em "O que fica pendente" abaixo.

### A ficha de cada alegação, com seu estado real

| # | Alegação (T004) | Teste (`file:line`) | Estado |
|---|---|---|---|
| 1 | As três seções aparecem na ordem Connected → Suggested by your estate → Available | `:91` "Connected, Suggested by your estate and…" | **VERMELHO** — "Available" não existe |
| 2 | Nenhum controle de paginação, nenhum "Page N of M" | `:145` "no pagination control renders…" | **VERDE, quebrado-e-restaurado para provar** (ver seção própria) |
| 3 | Contagem única no topo, com números derivados do payload e consistentes com o que a página lista | `:159` "the top of the page states one count…" | **VERDE, quebrado-e-restaurado para provar** |
| 4 | Busca por nome filtrando dentro de todas as seções, não só Available | `:194` "searching by an item's own name…" | **VERMELHO** — Connected/Suggested não respondem à busca hoje |
| 5 | Busca por capacidade filtrando dentro de todas as seções | `:227` "searching by a capability…" | **VERMELHO** — mesma causa |
| 6 | Rodapé com contagem de integrações movidas ao roadmap + link | `:271` "the footer names how many…" | **VERMELHO** — texto atual é "9 vendors not covered, and why", não "… moved to the roadmap …" |
| 7 | Altura de `/integrations` ≤2 viewports a 1080p | `:291` "the whole post-cut catalogue fits…" | **VERDE, quebrado-e-restaurado para provar** |
| 8 | Abrir um card não move a posição de rolagem | `:307` "opening a card does not move…" | **VERMELHO** — Δ378px medido (ver detalhe) |
| 9 | O painel fica sobreposto ao catálogo, não no rodapé do documento | `:341` "the panel overlaps the catalogue…" | **VERMELHO** — `position: static` medido |
| 10 | Deep-link aterrissa com a rolagem no topo do catálogo | `:382` "a deep link opens the panel…" | **VERMELHO** — scrollY=1209 medido |
| 11 | Fechar devolve rolagem e filtros | `:394` "closing the panel restores both…" | **VERDE, quebrado-e-restaurado para provar** |
| 12 | Nenhum campo de credencial vazio com ação desabilitada, numa integração conectada | `:440` "no empty credential field…" | **VERMELHO** — confirmado presente hoje |
| 13 | "Test again", "Replace credential", "Disconnect" nomeados | `:466` "offers Test again…" | **VERMELHO** — nenhum existe |
| 14 | Exatamente três fontes de intake | `:489` "exactly three sources…" | **VERDE, quebrado-e-restaurado para provar** |
| 15 | Chip "Receiving" na fonte que recebe; "Ready — nothing arrived yet" nas caladas | `:495` "the receiving source carries the exact…" | **VERMELHO** — nenhum dos dois textos existe hoje |
| 16 | Fonte recebendo mostra última entrega e volume da semana | `:515` "the receiving source is expanded…" | **VERMELHO** — "N this week" não existe hoje |
| 17 | Fonte calada em uma linha compacta | `:535` "a silent source renders as one compact line…" | **VERMELHO** — medido: as duas alturas são **idênticas**, 179.15625px, hoje |
| 18 | "Format & test" recolhido por padrão | `:561` "\"Format & test\" is collapsed by default" | **VERDE, quebrado-e-restaurado para provar** |
| 19 | Altura de `/settings/alert-intake` ≤2 viewports a 1080p | `:577` "the whole screen fits…" | **VERDE, quebrado-e-restaurado para provar** |
| 20 | YAML copiado contém a URL de entrega e o nome do delivery token | `:599` "the copied receiver YAML carries…" | **VERMELHO** — botão "Copy Alertmanager receiver YAML" não existe |
| 21 | Linha de confiança nomeia o token e oferece rotação | `:645` "the trust line names the delivery token…" | **VERDE, quebrado-e-restaurado para provar** |
| 22 | Nenhuma tela exibe o nome de permissão cru | `:663` "no source shows the raw permission name…" | **VERDE, quebrado-e-restaurado para provar** |
| 23 | Quatro nós na ordem entrada→regra→ação→destino, cada um com valor real | `:709` "four nodes render in order…" | **VERMELHO** — a cadeia não existe |
| 24 | O nó de destino navega para a seção correspondente | `:749` "the destination node navigates…" | **VERMELHO** — mesma causa |

Total: **15 vermelhas, 9 já verdes (todas as 9 quebradas-e-restauradas para
prova, nenhuma pulada)**. Nenhuma alegação foi descartada nem enfraquecida
para passar — quando uma medição saiu diferente do que eu esperava, o teste
foi corrigido para medir a coisa certa (duas correções reais, narradas
abaixo), não para concordar com o comportamento atual.

### Duas correções que o próprio processo de rodar T005 encontrou, antes de qualquer quebra-e-restaura

Nenhuma delas é um "defeito do produto" — são defeitos do meu primeiro
rascunho do teste, encontrados rodando de verdade e corrigidos antes de eu
poder confiar no vermelho/verde de qualquer alegação vizinha.

1. **`opening a card does not move the scroll position` — a alegação estava
   testando só metade da propriedade.** A primeira versão comparava
   `whileOpen > before - 20` — um limite de um lado só, que passa tanto
   "não moveu" quanto "moveu bastante para baixo" (exatamente o defeito que a
   spec descreve). Rodei contra o build real: **passou** no primeiro rascunho.
   Antes de aceitar isso como "já verde", troquei a rolagem de
   `window.scrollTo(0, document.documentElement.scrollHeight)` (o rodapé
   absoluto do documento, que por acaso já fica perto de onde o painel
   aparece — mascarando o salto) para `card.scrollIntoViewIfNeeded()` no
   último card da seção Available, e troquei a asserção para
   `Math.abs(whileOpen - before) < 20` (as duas direções). Resultado real, a
   partir daí: **vermelho** — `scroll moved from 831px to 1209px (Δ378px) the
   moment the panel opened`. A alegação nunca esteve "já verde" de verdade; o
   primeiro teste é que não media a coisa certa.
2. **`closing the panel restores…` tinha o mesmo limite de um lado só.**
   Corrigido para `Math.abs(scrollY - before) < 20` via `expect.poll`, pela
   mesma razão — aqui o resultado real permaneceu verde (ver quebra-e-restaura
   abaixo), mas a asserção original não teria pego um "restaurou longe demais
   na outra direção".
3. **`no source shows the raw permission name…`: o loop de abrir cada
   "Format & test" travava em 30s.** A primeira versão usava
   `page.getByTestId('reference').locator('button[aria-expanded="false"]')`
   com `count()` + `nth(index)` num loop — mas o próprio seletor
   (`aria-expanded="false"`) é o que cada clique muda, então a consulta viva
   reindexava os botões restantes a cada iteração e travava esperando um
   índice que nunca aparecia (confirmado: `.all()` **não** resolve isso —
   suas entradas ainda resolvem contra o mesmo seletor vivo). Corrigido para
   resolver um botão por `ingress-source` (um pai estável que não desaparece
   quando o seu próprio `aria-expanded` muda), via `page.getByTestId('ingress-
   source').all()` primeiro.

## T005 — a saída vermelha, exata

Comando final (build limpo, árvore restaurada, nenhuma quebra temporária
presente):

```
uv run python -m tools.console_e2e run -- tests/e2e/050-integrations-slideover-intake.acceptance.spec.ts
```

Resultado: **15 failed, 9 passed (55.4s)**. Rodado duas vezes de ponta a ponta
com o mesmo padrão exato de vermelho/verde (reprodutível, não um flake) — a
segunda vez é a que fica registrada abaixo, porque é a que rodou depois das
duas correções de teste descritas acima.

As 15 mensagens de falha reais (uma por alegação vermelha da tabela acima,
na mesma ordem):

```
1) Connected, Suggested by your estate and "Available" appear in that order
   Error: no leaf element reads exactly "Available" — the catalogue's third
   section has no heading of its own yet
   Expected: >= 0 · Received: -1

4) searching by an item's own name narrows every section, not only Available
   Error: typing "chat" was expected to narrow Connected from 4 to 1; it did not
   Expected: 1 · Received: 4

5) searching by a capability narrows every section, not only Available
   Error: Connected still renders while nothing in it matches "resource_pressure"
   expect(locator).toBeHidden() failed — Received: visible

6) the footer names how many integrations moved to the roadmap…
   Error: the footer link reads "9 vendors not covered, and why", not
   "… moved to the roadmap …"

8) opening a card does not move the scroll position
   Error: scroll moved from 831px to 1209px (Δ378px) the moment the panel opened
   Expected: < 20 · Received: 378

9) the panel overlaps the catalogue instead of sitting at the foot of the document
   Error: the panel's own computed position is "static"
   Expected: not "static"

10) a deep link opens the panel with the catalogue scrolled to its own top
    Error: the deep link landed at scrollY=1209, not at the catalogue's own top
    Expected: <= 20 · Received: 1209

12) no empty credential field is paired with a disabled action
    Error: alertmanager is connected and verified, yet the panel shows an
    empty credential field beside a disabled action
    Expected: false · Received: true

13) offers Test again, Replace credential and Disconnect, named
    Error: expect(locator).toBeVisible() failed
    Locator: getByRole('dialog').getByRole('button', { name: /^Test again$/ })
    Error: element(s) not found

15) the receiving source carries the exact "Receiving" chip; the silent ones
    carry "Ready — nothing arrived yet"
    Error: source "generic" does not carry the exact chip "Ready — nothing
    arrived yet" — element(s) not found

16) the receiving source is expanded with its last delivery and this week's volume
    Error: no "N this week" delivery volume is shown for the receiving source
    — element(s) not found

17) a silent source renders as one compact line, not the full card
    Error: a silent source is 179.15625px tall, the receiving one is
    179.15625px — expected the silent one to be a single compact line, well
    under half
    Expected: < 89.578125 · Received: 179.15625

20) the copied receiver YAML carries this deployment's own delivery URL and
    the delivery token's name
    Error: expect(locator).toBeVisible() failed
    Locator: …getByRole('button', { name: 'Copy Alertmanager receiver YAML' })
    Error: element(s) not found

23) four nodes render in order, each carrying a real, non-empty value
    Error: expect(locator).toHaveCount(expected) failed
    Locator: getByTestId('chain-node') · Expected: 4 · Received: 0

24) the destination node navigates to the section whose name matches what it promises
    Error: expect(locator).toBeVisible() failed
    Locator: locator('[data-testid="chain-node"][data-role="destination"]')
    Error: element(s) not found
```

Achado que vale mais que qualquer alegação isolada: **a alegação 17 mediu as
duas alturas como idênticas — 179.15625px, dígito por dígito** — confirmando
por medição real (não por leitura de código) que a tela de hoje desenha a
mesma estrutura completa para toda fonte, recebendo ou calada. Não é "falta
um estilo diferente"; é a mesma árvore de componentes renderizada duas vezes.

## Quebra-e-restaura das nove alegações que já vinham verdes

A regra da onda é explícita: uma alegação que já passa no primeiro rodar tem
de ser forçada a falhar, no vermelho observado, antes de contar como coberta.
Fiz isso para as nove — nenhuma foi aceita como "já verde" sem essa prova.

**Procedimento, para todas**: cada arquivo-fonte foi copiado para o
scratchpad (`cp` para
`/tmp/claude-999/.../scratchpad/backups/`) antes de qualquer edição — nunca
`git checkout`/`git stash`/`git restore`, exatamente como o despacho pediu.
Depois de cada rodada de quebra, o arquivo foi restaurado via `cp` de volta a
partir do backup, e `git status --short`/`git diff --stat` confirmaram
diff zero em cada um dos sete arquivos tocados, antes do rebuild final e antes
do T005 definitivo acima. O `console/.next/standalone/server.js` que serve os
testes é um build pré-compilado (`tools/console_e2e.py`: "the standalone
output, not the development server" — falha se o build não existir), então
qualquer quebra num arquivo `.tsx` exigiu `uv run python -m tools.console_gate
build` para valer; quebras em `config/constants/surfaces.py` (lido pelo
próprio teste via `readFileSync`, nunca importado pelo servidor Node) e na
fixture `transit-ingress.json` (relida pelo `mockplane` a cada boot que
`console_e2e run` já faz do zero) não precisaram de rebuild.

| # | Alegação | Arquivo quebrado | Quebra aplicada | Mensagem vermelha observada | Restaurado |
|---|---|---|---|---|---|
| 2 | Sem paginação | `console/src/surfaces/integration-catalogue.tsx:48` | `INTEGRATIONS_CATALOGUE_PAGE_SIZE` 24→1 | `Locator: getByRole('navigation', {name: /pagination/i})` · Expected: 0 · Received: 1 | sim, `diff` vazio |
| 3 | Contagem consistente | `console/src/surfaces/screens/integrations.tsx` (as duas chamadas de `message()` do resumo) | `connected: connected.length` → `+ 1` | `the header says 5 connected, but 4 connected-integration rows are drawn` | sim |
| 7 | Orçamento `/integrations` | `config/constants/surfaces.py:350` | `CONFIG_SCREEN_SCROLL_BUDGET_VIEWPORTS` 2.0→0.1 | `/integrations is 1080px tall against a 108px budget (0.1 viewports of 1080px)` | sim |
| 11 | Fechar restaura filtros | `console/src/surfaces/integration-panel.tsx` (`close()`) | `router.replace(closeHref, …)` → hardcoded `'/integrations'` | `expect(page).toHaveURL(/q=a\b/)` — Received: `"http://127.0.0.1:8423/integrations"` | sim |
| 14 | Exatamente 3 fontes | `fixtures/scenarios/populated/transit-ingress.json` | 4º `sources[]` fictício adicionado (`"source": "temp-break-and-restore"`) | `Locator: getByTestId('ingress-source')` · Expected: 3 · Received: 4 | sim |
| 18 | Format & test recolhido | `console/src/design/reference.tsx:35` | `useState(false)` → `useState(true)` | `Locator: getByTestId('reference').first()` · Expected attr "false" · Received "true" | sim |
| 19 | Orçamento `/settings/alert-intake` | `config/constants/surfaces.py:350` (mesma edição do #7) | mesma | `/settings/alert-intake is 2986px tall against a 108px budget (0.1 viewports of 1080px)` | sim |
| 21 | Trust line nomeia token | `console/src/surfaces/settings/alert-intake.tsx` (`deliveryTokenName`) | forçado para sempre `undefined` (mantendo a função real chamada, para não sobrar `noUnusedLocals`) | `Locator: getByTestId('delivery-token-trust')` — Received: `"No delivery token has authenticated this yet."` | sim |
| 22 | Sem permissão crua | `console/src/surfaces/settings/alert-intake.tsx` (dentro do `.map()` de fontes) | `<p data-testid="temp-raw-permission-leak">{deliveryPermission}</p>` adicionado | `the raw permission name "webhook.deliver" is visible somewhere on the screen` — corpo capturado contém literalmente `webhook.deliver` | sim |

**Nota de honestidade sobre a #22**: a primeira tentativa de quebra rodou
junto com a quebra da #18 (`reference.tsx` sempre expandido) no mesmo build —
e o teste continuou **verde**, porque o próprio loop de "abrir cada Format &
test" clica no botão de alternância; com a seção já aberta por causa da outra
quebra, o clique **fechava** em vez de abrir, escondendo de novo o vazamento
que eu tinha acabado de inserir. Não contei isso como "coberto" — revertive
só `reference.tsx` (mantendo o vazamento em `alert-intake.tsx`), rebuildei de
novo, e só então a #22 caiu para vermelho de verdade, com a mensagem acima.
Registrado porque é exatamente o tipo de falso-verde que a regra de
quebra-e-restaura existe para pegar, e quase escapou por eu ter empacotado
duas quebras independentes no mesmo build.

Depois das nove verificações, os sete arquivos (5 `.tsx`, 1 `.py`, 1 `.json`)
foram restaurados a partir do scratchpad e confirmados **byte-idênticos ao
HEAD** via `git diff --stat` (saída vazia para cada um) antes do rebuild final
e do T005 definitivo. `git status --short` no fim desta fatia mostra só os
dois arquivos que são o entregável dela.

## A decisão da suíte transversal

`/integrations` é um `Area` em `console/src/shell/routes.ts` (`AREAS`, linha
~250), não um `SettingsPage` (`SETTINGS_PAGES`, linha ~533) — tem entrada
própria de navegação de topo, não vive sob o subnav de Settings. Por isso
`transversal-rules.spec.ts` nunca o incluiu: seu `SETTINGS_ROUTES` é lido
estritamente de `SETTINGS_PAGES` (`shell/routes.ts`), por desenho ("a
truthful read of `SETTINGS_PAGES` alone").

**Decisão tomada: a suíte ganha `/integrations` explicitamente, sem alargar o
que `SETTINGS_ROUTES` significa.** Estruturalmente, `/integrations` é
elegível às três regras por rota: renderiza `page-header` do mesmo jeito que
uma tela de Settings (`AreaHeader`/`SettingsPageHeader` — os dois emitem
`data-testid="page-header"`, confirmado lendo `console/src/shell/area.tsx:60`
e `:154`), e carrega sua própria tabela de configuração ("Advanced: configured
vendors") com coluna Value, à qual a regra de valor-nunca-vazio já se aplica
igual a qualquer outra. SC-011 desta feature pede a suíte passando nas *duas*
rotas da feature; `/settings/alert-intake` já era coberta (é uma
`SETTINGS_PAGE`), `/integrations` não era — sem esta mudança SC-011 ficaria
só meio cumprido, e o despacho pediu decisão explícita, não adiamento.

Implementado em `console/tests/e2e/transversal-rules.spec.ts:132-139`: uma
constante nova, `NON_SETTINGS_ROUTES_HELD_TO_THE_SAME_RULES`, com um único
membro (`{id: 'integrations', path: '/integrations'}`), documentada com a
razão acima; `ROUTES_UNDER_THESE_RULES` (`:136`) é a concatenação de
`SETTINGS_ROUTES` com essa lista, e é ela — não mais `SETTINGS_ROUTES`
diretamente — que o loop das três regras por rota consome (`:239`, antes
`:219`). `SETTINGS_ROUTES` em si permanece intocado, ainda um espelho fiel de
`SETTINGS_PAGES`.

**Resultado real, rodando `transversal-rules.spec.ts` de ponta a ponta**:
`25 passed, 7 skipped` (0 falhas) — as três regras novas em `/integrations`
passam hoje (`carries no banned vocabulary`, `stays within the scroll
budget`, `draws no empty cell…`), e nenhuma rota preexistente mudou de
resultado. SC-011 está, portanto, **cumprido nas duas rotas**, não apenas
registrado como decisão — verificado rodando a suíte, não assumido.

**A segunda parte desta decisão**: a entrada de `EXCEPTIONS` para
`{/settings/alert-intake, scroll-budget, "the screen repeats seven near-
identical sources with nothing collapsed"}` foi **removida**
(`transversal-rules.spec.ts`, agora `const EXCEPTIONS: readonly Exception[] =
[]`, linha `166`, com o comentário explicando por quê). Ela já era código
morto antes desta fatia: `/settings/alert-intake` está em
`SCROLL_BUDGET_MEASURED_ELSEWHERE`, e o teste de orçamento consulta esse
conjunto com `test.skip` **antes** de chegar ao `test.fixme`/`exceptionFor`
que liaria essa entrada — ela nunca foi alcançada em nenhuma execução.
Confirmando por leitura de código, não é uma alegação nova provada: **apagar
código morto não é evidência de medição**, e não estou reportando isso como
"o orçamento de `/settings/alert-intake` foi corrigido" — quem mede esse
orçamento de verdade, hoje, é `scroll-budget.spec.ts` e a alegação #19 desta
mesma fatia (linha `577` do acceptance spec), ambos com número real medido
(1202px / 2986px-com-quebra-restaurada-de-volta-a-1202px).

## O que fica pendente, nomeado, não escondido

Tudo abaixo é trabalho de fases futuras (Fase 3 em diante em `tasks.md`), não
desta fatia — nomeado aqui para quem entrar na próxima não redescobrir o
óbvio:

- **As 15 alegações vermelhas** listadas na tabela de T004 são,
  respectivamente, o critério de aceite de T009-T011 (payload), T013-T016
  (US1), T018-T019 (US2), T024-T026 (US3), T028-T030 (US4), T032-T035 (US5) e
  T037-T039 (US6) — a correspondência exata está nos comentários de cada teste
  no próprio arquivo. Nenhuma implementação foi tentada aqui, por instrução
  explícita desta fatia.
- **Fora do escopo de T004 por decisão, não por esquecimento** — alegações
  reais da spec que os seis grupos de T004 não pedem e que portanto este
  arquivo não codifica: o placeholder do campo de endereço vindo da descoberta
  do estate (FR-028/029), o rodapé de Alert intake nomeando as fontes
  removidas (FR-066), "nenhuma sugestão do estate" (edge case, precisaria de
  um dataset que `populated` não tem — ver nota abaixo), "mais de um delivery
  token válido", a formatação exata do card de sugestão ("Found on X (CT
  Y)") — este último já teria uma frase diferente hoje ("Found at X, on
  resource Y", `catalogue.integrations.suggested.evidence`) mas não é uma das
  seis alegações de T004, então não foi testado nem alterado.
- **Nenhum self-guard/skip por dataset foi necessário.** Verifiquei
  explicitamente se algum dos seis grupos precisava de um estado que
  `populated` não carrega (a instrução do despacho citou "nenhuma sugestão
  alguma" como exemplo) — nenhum dos seis grupos de T004 toca esse edge case,
  então nenhum `test.skip` por ausência de estado foi necessário. Os dois
  `test.skip` que o arquivo tem (`:307`/`:394`, "opening a card…"/"closing the
  panel…") são por altura de página insuficiente para a medição fazer
  sentido, não por estado de dado ausente — e nem chegaram a disparar nesta
  execução (a página tem altura suficiente hoje).
- **`console/tests/unit/**`, `console_gate test` (unitário) e `console_gate
  visual` não foram rodados nesta fatia** — a instrução final desta fatia
  nomeia especificamente `format-check`, `lint` e `typecheck`; nenhum código
  de produção foi tocado (fora das quebras temporárias, todas restauradas),
  então não há razão para suspeitar de efeito no unitário, mas isso não foi
  confirmado por execução e não estou reportando como confirmado.
- **`make verify`, `console-e2e` completo (a suíte toda) e qualquer
  `console-visual-accept` não foram rodados** — do orquestrador, por
  instrução explícita.

## Gates rodados nesta fatia

| Gate | Comando | Resultado |
|---|---|---|
| Sintaxe da fixture editada e restaurada | `python3 -c "import json; json.load(...)"` | válido antes de restaurar |
| `git diff --stat` dos 7 arquivos quebrados-e-restaurados | `git diff --stat -- <cada um>` | vazio nos 7 — restauração byte-idêntica confirmada |
| Formatação do console | `uv run python -m tools.console_gate format-check` | **passou** (após `pnpm exec prettier --write` no arquivo novo — o primeiro rodar tinha achado 1 arquivo desformatado) |
| Lint do console | `uv run python -m tools.console_gate lint` | **passou** (após remover um `?.` desnecessário que o `@typescript-eslint/no-unnecessary-condition` acusou em `element.textContent?.trim()` — `textContent` não é nulável neste `tsconfig`, confirmado pelo próprio padrão já usado em `autonomy-tabs.acceptance.spec.ts`) |
| Typecheck do console | `uv run python -m tools.console_gate typecheck` | **passou**, `tsc --noEmit` sem erros |
| Acceptance spec desta feature (T005, definitivo) | `uv run python -m tools.console_e2e run -- tests/e2e/050-integrations-slideover-intake.acceptance.spec.ts` | **15 failed, 9 passed** — ver seção T005 acima |
| Suíte transversal (com `/integrations` incluída) | `uv run python -m tools.console_e2e run -- tests/e2e/transversal-rules.spec.ts` | **25 passed, 7 skipped**, 0 falhas |
| `console_gate test` (unitário) | não rodado | fora do escopo nomeado desta fatia (ver "O que fica pendente") |
| `console_gate visual` | não rodado | idem |
| `make verify` | não rodado | do orquestrador, por instrução explícita |

## Instrumento: nada rodou embrulhado em pipe

Todos os comandos acima que importam para o resultado (`console_e2e run`,
`console_gate format-check/lint/typecheck`) rodaram sem `| tail`/`| head`
nem `; echo`, com o código de saída lido diretamente (`echo "EXIT_CODE=$?"`
logo após cada um) e o texto completo salvo em arquivo no scratchpad antes de
qualquer grep — a mesma armadilha que o despacho descreveu para `make verify`
e que a fatia 0 encontrou em `pytest`. Nenhum gate foi lido só pelo código de
saída.

## Tarefas marcadas em `tasks.md`

T001, T002, T003 (fatia 0) e agora **T004 e T005** — marcadas `[x]` porque o
arquivo existe, roda, e a saída vermelha está colada acima, palavra por
palavra. T006 em diante permanecem `[ ]`: são das fases 3 em diante, fora
desta fatia.

---

# Fatia 2 de nove — T006 a T011

Estado abaixo verificado contra o código nesta árvore, HEAD `adc460c` em
`feat/v6-scope-and-settings`, árvore limpa antes desta sessão (confirmado por
`git status --short`). **Escopo: T006–T011, a Fase 3 (Foundational) —
metade do gateway desta feature.** Nenhuma tela de console, componente,
`screens.json` ou acceptance spec foi tocado, por instrução explícita do
despacho.

**O orquestrador interrompeu esta fatia antes do fim planejado do trabalho de
verificação**, com a instrução explícita de parar de implementar e escrever
este ledger — a instrução chegou enquanto uma suíte em background ainda
rodava. T006 a T011 estão **implementados e com evidência de
vermelho→verde própria**. A suíte inteira de `tests/contract/console/`
tinha sido iniciada antes da instrução de parada e terminou pouco depois; o
resultado (barato de ler, não trabalho novo) foi conferido antes de fechar
este ledger e está na seção própria abaixo, junto com o resto da rodada de
gates. `tests/security/`, o restante de `tests/unit/gateway/http/` e a
maioria dos guard checks da onda **não foram rodados** — ver "O que continua
sem rodar" para a lista exata. A tabela e as seções abaixo dizem exatamente o
que foi visto rodar, com que saída, e o que ficou sem rodar — nada foi
inferido.

## Tabela

| Peça | Estado | Detalhe |
|---|---|---|
| T006 — teste de contrato: distinção de estado de credencial | **FEITO** | `tests/contract/console/test_integration_credential_state_contract.py` (3 testes). **As três alegações passaram no primeiro rodar** — a distinção já existia (`HealthStatus.UNCONFIGURED`/`UNKNOWN`/`HEALTHY`, de 001) — e as três foram quebradas-e-restauradas para prova. Ver seção própria. |
| T007 — teste de contrato: endereço descoberto como placeholder, separado do identificador | **FEITO** | `tests/contract/console/test_integration_suggestion_placeholder_contract.py` (3 testes). **As três alegações passaram no primeiro rodar** — `SuggestionView` já carregava os cinco campos — e as três foram quebradas-e-restauradas. Ver seção própria. |
| T008 — teste de contrato: bloco do receiver Alertmanager, nunca com o valor de um segredo | **FEITO** | `tests/contract/console/test_ingress_receiver_yaml_contract.py` (5 testes). **Confirmado vermelho de verdade antes da implementação** — `ImportError` na coleta, mensagem exata abaixo — depois implementado (T010) e confirmado verde. |
| T009 — servir a distinção de estado + endereço descoberto em `integrations.py`; regenerar client | **FEITO (já existia, verificado)** | Nenhuma mudança de código foi necessária em `gateway/http/routes/integrations.py` — T006/T007 provam que os dois fatos já eram servidos antes desta fatia. O client foi regenerado e conferido (ver "Regeneração do client" abaixo), cobrindo T009 junto com T010/T011. |
| T010 — bloco de receiver do Alertmanager gerado e servido por `ingress.py` | **FEITO** | `gateway/webhooks/sources/alertmanager.py` (função `receiver_yaml`, nova) e `gateway/http/routes/ingress.py` (campo `receiver_yaml`, seletor `_delivery_token_name`, wiring). Test-first: 5 testes novos + 1 existente ampliado em `tests/unit/gateway/http/test_ingress_routes.py`, confirmados vermelhos antes da implementação, verdes depois. Ver seção própria. |
| T011 — volume de entregas da semana por fonte | **FEITO** | `config/constants/transit.py` (`TRANSIT_WEEKLY_VOLUME_WINDOW_HOURS`, nova) e `gateway/http/routes/transit.py` (campo `week_count`, segunda leitura de `uow.transit.activity`). Test-first: 5 testes novos em `tests/unit/gateway/http/test_transit_routes.py`, confirmados vermelhos antes da implementação (um deles corrigido depois de o vermelho revelar uma suposição errada minha — narrado abaixo), verdes depois. |

## Arquivos criados

- `tests/contract/console/test_integration_credential_state_contract.py` (T006)
- `tests/contract/console/test_integration_suggestion_placeholder_contract.py` (T007)
- `tests/contract/console/test_ingress_receiver_yaml_contract.py` (T008)

## Arquivos alterados

- `gateway/webhooks/sources/alertmanager.py` — nova função `receiver_yaml()` (T010)
- `gateway/http/routes/ingress.py` — campo `receiver_yaml`, função `_delivery_token_name()`, `list_ingress_sources` agora abre `uow` e lê tokens (T010)
- `gateway/http/routes/transit.py` — campo `week_count` em `IngressSourceStatusView`, segunda janela em `ingress_status()` (T011)
- `config/constants/transit.py` — nova constante `TRANSIT_WEEKLY_VOLUME_WINDOW_HOURS` (T011)
- `tests/unit/gateway/http/test_ingress_routes.py` — teste de conjunto fechado ampliado + 5 testes novos (T010)
- `tests/unit/gateway/http/test_transit_routes.py` — 5 testes novos (T011)
- `fixtures/contract/openapi.json` — regenerado via `python -m tools.mockplane contract` (+16 linhas: os dois campos novos)
- `console/src/api/schema.ts` — regenerado via `make console-client` (+7 linhas: os dois campos novos) — **o único arquivo sob `console/` tocado nesta fatia, e é gerado, não escrito à mão**

## T006 — a decisão, e a prova de que ela já estava tomada

O despacho pedia uma decisão explícita: "o payload declara isso explicitamente,
ou deixa o console inferir de uma ausência?" Investigando antes de escrever
qualquer teste (`integrations/_catalogue/discovery.py:catalogue()`,
`integrations/_catalogue/entry.py:HealthStatus`,
`tests/unit/gateway/http/test_integrations_credential_state.py` — já existente,
da 001, cobrindo a mesma distinção via HTTP real), a resposta encontrada foi:
**a distinção já é explícita**, por três valores de enum genuinamente
diferentes (`unconfigured`/`unknown`/`healthy`), nunca por uma ausência de
campo. `catalogue()` garante isso estruturalmente: um nome fora do conjunto
`configured` é sempre `UNCONFIGURED`; um nome dentro dele sem registro no
ledger é sempre `UNKNOWN` — nunca os dois colapsam.

Os três testes escritos (`tests/contract/console/test_integration_credential_state_contract.py`):

1. `test_an_absent_credential_and_a_stored_unverified_one_are_different_payload_values` — chama `catalogue()` de verdade três vezes (ausente / configurado-sem-ledger / configurado-e-verificado) e afirma três valores distintos.
2. `test_a_stored_unverified_credential_is_never_the_same_value_as_an_absent_one` — a mesma propriedade, isolada.
3. `test_the_served_catalogue_carries_a_verified_integration_and_a_stored_but_unverified_one` — lê `fixtures/scenarios/populated/integrations.json` via `tools.mockplane.scenarios.load("populated")` e confirma que `alertmanager`/`loki` (as fixtures desta feature, da fatia 0) carregam `healthy`/`unknown` respectivamente, e que ambos os valores pertencem ao enum `HealthStatus` real — fechando exatamente a classe de defeito "fixture concorda consigo mesma e discorda do backend" que o despacho descreve, para este campo especificamente (nenhum teste existente em `tests/contract/fixtures/` cobria `integrations[].health` dessa forma).

**Primeiro rodar**: `3 passed` — nenhuma vermelha. Registrado honestamente como
característica confirmada, não como trabalho novo, e provado por
quebra-e-restaura:

| Teste | Arquivo quebrado | Quebra | Mensagem vermelha observada | Restaurado |
|---|---|---|---|---|
| 1 | `integrations/_catalogue/discovery.py:188` | `HealthStatus.UNCONFIGURED` → `HealthStatus.UNKNOWN` no ramo "não configurado" | `three different credential states collapsed onto fewer than three payload values: {'unknown', 'healthy'}` | sim, `git diff --stat` vazio |
| 2 | `integrations/_catalogue/discovery.py:192` (depois de restaurar a quebra 1) | ramo "configurado" forçado sempre para `HealthStatus.UNCONFIGURED` | `assert 'unconfigured' != 'unconfigured'` (a asserção de desigualdade falhando por igualdade) | sim |
| 3 | `fixtures/scenarios/populated/integrations.json` (edição direta, restaurada de um backup em scratchpad — o mesmo padrão que a fatia 1 já usou para `transit-ingress.json`) | `loki.health`: `"unknown"` → `"unconfigured"` | `assert 'unconfigured' == 'unknown'` | sim, `git diff --stat` vazio |

Depois das três provas, os quatro arquivos tocados nesta seção
(`discovery.py`, a fixture, e — ver T007 abaixo — `integrations.py` e
`suggestions.py`, quebrados na mesma sessão) foram confirmados
**byte-idênticos ao HEAD** com um único `git diff --stat` agregado, vazio.
Rerun final: `6 passed` (T006+T007 juntos).

## T007 — a mesma leitura, para o endereço sugerido

Achado ao investigar antes de escrever: `SuggestionView`
(`gateway/http/routes/integrations.py:88-105`) já carrega `address`,
`from_resource` (o identificador), `resource_label` (o nome de exibição do
recurso — "o container"), `resource_kind` e `because` — os cinco campos que
FR-013/014/028/029 pedem. `platform/estate/suggestions.py:suggest_integrations`
já deriva `address` de `resource.attributes[ADDRESS_ATTRIBUTE]` mais a porta
default do vendor, nunca de um literal.

Três testes (`tests/contract/console/test_integration_suggestion_placeholder_contract.py`):

1. `test_suggestion_view_declares_the_address_the_label_and_the_identifier_as_separate_fields` — os cinco campos existem no schema.
2. `test_the_resource_identifier_and_its_display_label_are_genuinely_different_values` — chama `suggest_integrations()` de verdade com um `Resource` cujo `resource_id` (`"proxmox:ct:139"`) e `display_name` (`"prometheus-lxc"`) são deliberadamente diferentes, e confirma que `Suggestion.from_resource`/`resource_label` não colapsam.
3. `test_the_suggested_address_is_derived_from_discovery_never_a_literal_in_the_route` — `inspect.getsource(list_integrations)`, sem nenhum IPv4 literal, contendo `"suggested[entry.name].address"`.

**Primeiro rodar**: `3 passed` — de novo, nenhuma vermelha, característica
confirmada. Quebra-e-restaura:

| Teste | Arquivo quebrado | Quebra | Mensagem vermelha observada | Restaurado |
|---|---|---|---|---|
| 1 | `gateway/http/routes/integrations.py:103-105` | campo `resource_kind` removido de `SuggestionView` | `SuggestionView has no 'resource_kind' field` | sim |
| 3 (mesmo arquivo, mesma sessão de quebra) | `gateway/http/routes/integrations.py:343` | `address=suggested[entry.name].address,` → `address="10.20.20.99",` | `list_integrations names a literal address ['10.20.20.99']; ...` | sim |
| 2 | `platform/estate/suggestions.py` (linha do `resource_label=`) | `resource.display_name` → `resource.resource_id` | `assert 'proxmox:ct:139' == 'prometheus-lxc'` | sim |

Restaurado e confirmado (junto com T006, ver acima): `git diff --stat` vazio
nos quatro arquivos.

## T008 — o vermelho genuíno, e a implementação que o fechou

Diferente de T006/T007, este **não existia**: nada em `gateway/webhooks/sources/`
ou `gateway/http/routes/ingress.py` gerava um bloco de receiver antes desta
fatia. Cinco testes escritos primeiro
(`tests/contract/console/test_ingress_receiver_yaml_contract.py`):

1. `test_ingress_source_view_declares_a_receiver_yaml_field`
2. `test_the_generated_block_is_a_pasteable_webhook_configs_entry`
3. `test_the_block_names_the_delivery_token_in_use`
4. `test_the_credential_field_is_an_explicit_marker_never_a_value`
5. `test_the_generator_s_signature_carries_no_parameter_a_secret_could_travel_through`

**Vermelho confirmado, coleção inteira falhando**:

```
ImportError while importing test module '.../test_ingress_receiver_yaml_contract.py'.
tests/contract/console/test_ingress_receiver_yaml_contract.py:22: in <module>
    from gateway.webhooks.sources.alertmanager import receiver_yaml
E   ImportError: cannot import name 'receiver_yaml' from 'gateway.webhooks.sources.alertmanager'
```

### A implementação (T010)

**Onde a lógica de geração do YAML mora, e por quê**: `gateway/webhooks/sources/alertmanager.py`,
não em `ingress.py` nem em `gateway/webhooks/router.py`. É o módulo que já
declara o `PROFILE` do Alertmanager (`expects`, `verification`) — o único
lugar que já sabia "o que este vendor espera" antes desta fatia. A regra do
plano ("comportamento no arquivo compartilhado mais próximo" é o antipadrão)
apontou para o módulo mais específico possível, não para o mais genérico.

`receiver_yaml(*, url: str, token_name: str) -> str` (`alertmanager.py`,
função nova) — usa `yaml.safe_dump` (dependência já presente no repo, usada em
`platform/config_service/templates/engine.py` e outros) para montar
`{"webhook_configs": [{"url": ..., "http_config": {"authorization": {"type":
"Bearer", "credentials": <marcador>}}}]}`. O marcador é
`'paste the value of delivery token "{name}" here'.format(name=token_name)` —
uma sentença legível, nunca um valor. **A assinatura da função não tem
parâmetro nenhum por onde um segredo pudesse viajar** — só `url` e
`token_name` — e um teste (`test_the_generator_s_signature_carries_no_parameter...`)
fecha essa porta estruturalmente, não apenas por convenção.

**Seleção de "o token em uso"** (`gateway/http/routes/ingress.py`, função
nova `_delivery_token_name`) — espelha a lógica que já existe no console
(`alert-intake.tsx:203-216`, `deliveryTokenNamed`): filtra fora o token de
sessão do console (`platform.identity.local_accounts.CREDENTIAL_NAME`,
`"Console sign-in"` — **reaproveitado da declaração Python real, nunca
reescrito como literal**), filtra revogados, filtra por
`Permission.WEBHOOK_DELIVER.value in token.scopes`, e escolhe o mais
recente por `created_at`. Achado ao investigar antes de implementar: sem esse
filtro do token de sessão, um token "Console sign-in" (que herda a permissão
do papel do usuário, incluindo `WEBHOOK_DELIVER` se o papel for RESPONDER ou
acima) poderia ser nomeado por engano como "o token de entrega em uso" — um
bug real, não hipotético, que o teste `test_the_receiver_yaml_names_the_most_recently_issued_delivery_token`
não cobre diretamente (cobre "mais recente entre válidos", não "sessão
excluída") — **registrado como lacuna de cobertura, ver "O que fica
pendente"**.

`receiver_yaml` só é preenchido para a fonte `alertmanager` e só quando
`token_name` não é vazio; caso contrário é `None` (ausente, não um bloco
quebrado) — a mesma leitura "Absent, not disabled" que FR-063 pede para a
trust line.

**Teste-primeiro no nível de unidade, além do contrato**: `tests/unit/gateway/http/test_ingress_routes.py`
ganhou 5 testes novos (rodando contra um app ASGI real, emitindo um token de
verdade via `POST /identity/tokens` e lendo `GET /v1/ingress/sources` de
volta) e teve um teste existente ampliado
(`test_it_carries_no_field_a_credential_could_sit_in`, que afirma o conjunto
fechado de campos da resposta — quebraria de qualquer forma com o campo novo,
então foi atualizado deliberadamente, não por acidente).

**Vermelho confirmado antes de implementar** (`uv run pytest
tests/unit/gateway/http/test_ingress_routes.py`): **5 failed, 5 passed**
— os 5 testes pré-existentes intocados continuavam verdes; os 5 novos e o
1 ampliado falhavam com `KeyError: 'receiver_yaml'` (4×) e um `AssertionError`
de conjunto (`Extra items in the right set: 'receiver_yaml'`).

**Verde depois de implementar**: `tests/contract/console/test_ingress_receiver_yaml_contract.py`
+ `tests/unit/gateway/http/test_ingress_routes.py` juntos → **15 passed**.

## T011 — o volume da semana, e uma suposição minha corrigida pelo próprio vermelho

`gateway/http/routes/transit.py:ingress_status()` já lia uma janela de 24h
(`TRANSIT_ACTIVITY_WINDOW_HOURS`) para `counts`/`never_delivered`/
`last_delivery_at`. FR-048 pede o volume da **semana**, um número diferente —
constante nova `TRANSIT_WEEKLY_VOLUME_WINDOW_HOURS = 24 * 7` em
`config/constants/transit.py`, e uma **segunda chamada** a
`uow.transit.activity(direction=INGRESS, since=<7 dias atrás>)` dentro do
mesmo `async with uow`, alimentando o campo novo `week_count` (soma de
`SourceActivity.total`, todos os desfechos, não só aceitos).

5 testes novos em `tests/unit/gateway/http/test_transit_routes.py`. **Um
deles continha uma suposição errada minha, que o próprio vermelho revelou
antes de eu confiar nele**: a primeira versão de
`test_the_week_s_volume_includes_a_delivery_older_than_the_day_window` afirmava
`row["never_delivered"] is True` para uma entrega de 5 dias atrás — errado:
`SourceActivity.last_delivery` **propositalmente** alcança para fora da
janela (`platform/persistence/ports/transit_ledger.py:175-181`, docstring
explícita: "reaches outside the window on purpose"), então
`never_delivered` já era `False` para qualquer entrega histórica, janela
nenhuma — comportamento correto e pré-existente, não um bug. Rodei o teste
vermelho, li a falha (`assert False is True`), reconheci que a asserção
media a coisa errada, e a substituí por `row["counts"] == {}` (a janela de
24h de fato vazia) antes de aceitar qualquer vermelho como prova válida —
registrado aqui porque é exatamente o tipo de correção que a onda pede
narrada, não escondida.

**Vermelho confirmado** (`uv run pytest tests/unit/gateway/http/test_transit_routes.py -k week`,
depois da correção acima): **5 failed** — quatro por `KeyError: 'week_count'`,
um pela asserção de `counts`/`never_delivered` que eu tinha acabado de
corrigir (ainda vermelha, porque o campo não existia).

**Verde depois de implementar**: `tests/unit/gateway/http/test_transit_routes.py`
inteiro → **24 passed** (19 pré-existentes intocados + 5 novos).

## Regeneração do client (T009 + T010 + T011 juntos)

Feita **uma vez, ao final**, cobrindo as três tarefas — não uma vez por
tarefa, porque T009 não mudou nada em `integrations.py` e regenerar antes de
T010/T011 estarem prontos teria exigido uma segunda rodada de qualquer jeito.
Registrado aqui como desvio deliberado da ordem literal do texto de T009, não
como pulo de etapa.

1. `uv run python -m tools.mockplane contract` → `wrote
   /srv/workspaces/NinjaSRE/fixtures/contract/openapi.json` — diff real:
   **+16 linhas** (os dois campos novos, `week_count` e `receiver_yaml`).
2. `uv run pytest tests/contract/fixtures/ -q` → **108 passed** (mesma
   contagem da fatia 0 — nada regrediu ao trocar o documento).
3. `uv run python -m tools.console_toolchain run run client` →
   `openapi-typescript ... → src/api/schema.ts [223.5ms]`, saída limpa.
4. `git diff -- console/src/api/schema.ts` → **+7 linhas**, exatamente
   `week_count: number` (com `@default 0`) em `IngressSourceStatusView` e
   `receiver_yaml?: string | null` em `IngressSourceView` — nada além disso.
5. `uv run python -m tools.console_gate client-check` → **passou** (saída:
   o mesmo comando de geração rodando de novo e confirmando zero diff).

## Gates rodados nesta fatia (reais, com saída vista)

| Gate | Comando | Resultado |
|---|---|---|
| Lint Python, arquivos tocados | `uv run ruff check <9 arquivos>` | `All checks passed!` |
| Formatação Python, arquivos tocados | `uv run ruff format --check <9 arquivos>` | achou 2 arquivos desformatados (`gateway/http/routes/transit.py`, `test_integration_credential_state_contract.py`) na primeira rodada; `uv run ruff format` aplicado nos dois; segunda rodada de `--check` → **9 arquivos já formatados** |
| Tipagem Python, arquivos tocados | `uv run mypy <9 arquivos>` | `Success: no issues found in 9 source files` |
| Guard de constantes | `make check-constants` | passou, exit 0 |
| Contrato de fixtures | `uv run pytest tests/contract/fixtures/ -q` | **108 passed** |
| Suíte do mockplane | `uv run pytest tests/unit/tools/mockplane/ -q` | **183 passed** (bate com a fatia 0) |
| T006 (isolado) | `uv run pytest tests/contract/console/test_integration_credential_state_contract.py -v` | **3 passed** (depois das 2 quebras-e-restauras) |
| T007 (isolado) | `uv run pytest tests/contract/console/test_integration_suggestion_placeholder_contract.py -v` | **3 passed** (depois das 3 quebras-e-restauras) |
| T006+T007 juntos, final | `uv run pytest tests/contract/console/test_integration_credential_state_contract.py tests/contract/console/test_integration_suggestion_placeholder_contract.py -q` | **6 passed** |
| T008 + unidade de ingress, final | `uv run pytest tests/contract/console/test_ingress_receiver_yaml_contract.py tests/unit/gateway/http/test_ingress_routes.py -v` | **15 passed** |
| Unidade de transit, final | `uv run pytest tests/unit/gateway/http/test_transit_routes.py -v` | **24 passed** |
| Regeneração + checagem do client | ver seção própria acima | ambos passaram |
| Suíte inteira de `tests/contract/console/` | `uv run pytest tests/contract/console/ -q` (rodada em background, resultado lido depois de completar) | **466 passed, 1 failed** — a falha é `machine-tokens-1440-light`, o efeito colateral já nomeado pela fatia 0, não algo desta fatia; ver seção própria |

### Um rerun pós-formatação que bateu no meu próprio lock, não num defeito

Depois de rodar `ruff format`, tentei reconfirmar todos os 5 arquivos de
teste desta fatia numa única chamada (`test_ingress_routes.py`,
`test_transit_routes.py`, e os 3 novos de `tests/contract/console/`). O
resultado misturou duas coisas: **34 passed** de verdade
(`test_ingress_routes.py` + `test_transit_routes.py`, 10+24), seguido de
`_pytest.outcomes.Exit: another run is already writing into the console
checkout` — o lock de `tests/contract/console/conftest.py`, segurado pela
**minha própria** rodada em background da suíte inteira (`b9ye98n2e`), ainda
viva naquele momento. Não é um defeito descoberto — é contenção comigo mesmo,
e os 34 reais já tinham sido confirmados verdes individualmente nas linhas
acima antes disso.

## A suíte inteira de `tests/contract/console/` — iniciada em background, resultado chegou depois da instrução de parada, lido antes de fechar o ledger

`uv run pytest tests/contract/console/ -q` (id de tarefa em background
`b9ye98n2e`) foi iniciada para confirmar que os 3 arquivos novos convivem com
o resto do diretório (`test_console_gate.py`,
`test_console_visual_regression.py`, `test_console_shell.py`,
`test_console_is_an_api_client.py`, etc.) sem regressão. A instrução de parada
chegou enquanto ela ainda rodava (450s de execução real — splicing e limpeza
de `test_console_gate.py`/`test_console_visual_regression.py` são lentos por
natureza) e o arquivo de saída estava vazio nas duas vezes em que tentei
lê-lo antes disso. **A tarefa terminou logo depois, e o resultado — barato de
ler, não trabalho novo — foi conferido antes de fechar este ledger:**

```
1 failed, 466 passed in 450.50s (0:07:30)
FAILED tests/contract/console/test_console_visual_regression.py::test_the_untouched_baselines_still_match
```

**A única falha é a mesma já nomeada pela fatia 0**, não uma introduzida
aqui: `machine-tokens-1440-light` — "Expected an image 1440px by 1729px,
received 1440px by 1890px" — o efeito colateral documentado da fatia 0 de
adicionar o token `tok-0003` ("Alert delivery") ao cenário `populated`, que
faz `/settings/machine-tokens` crescer uma linha. A fatia 0 já registrou isso
em "O que fica pendente" e pediu uma decisão do orquestrador (ampliar T046
para recapturar essa baseline, ou tratá-la como tarefa própria); nada mudou
aqui além de confirmar, com a suíte inteira rodando de verdade, que **nenhuma
outra baseline e nenhum outro teste do diretório foi afetado por esta
fatia** — os outros 33 testes visuais passaram, e os 466 aprovados incluem os
11 dos meus 3 arquivos novos. `test_a_stale_committed_client_fails_the_build`
(que existe precisamente para pegar um client desatualizado) também passou,
confirmando de um segundo ângulo que a regeneração do client está correta.

**Consequência prática**: nenhuma linha nova fica pendente por causa desta
leitura — o pendente já estava nomeado pela fatia 0 e continua sendo dela,
não desta fatia.

Também confirmado, checando `git status` de novo depois da conclusão: o
arquivo `console/tests/e2e/seeded.spec.ts` que aparecia como resíduo não
rastreado enquanto a suíte ainda rodava **não existe mais** — o processo
completou normalmente (nunca foi morto) e seu próprio `finally: _sweep()`
limpou o resíduo, exatamente como o `conftest.py` daquele diretório promete.
A árvore de trabalho está limpa de qualquer coisa além dos arquivos desta
fatia; `git status --short` mostra só os 8 arquivos alterados e os 3 criados
listados em "Arquivos alterados"/"Arquivos criados" acima.

## O que continua sem rodar — nomeado, não escondido

- **`tests/security/`** — não rodado nesta fatia. T008/T010 tocam segurança
  (o bloco do receiver nunca carregando um segredo), e essa propriedade está
  coberta pelos meus próprios testes (`test_the_receiver_yaml_never_carries_a_credential_s_own_value`
  em `test_ingress_routes.py`, e os dois testes de T008 sobre a assinatura
  fechada e o marcador explícito) — mas a suíte `tests/security/` em si,
  que pode ter testes mais amplos sobre toda a árvore de rotas, não foi
  executada.
- **O restante de `tests/unit/gateway/http/`** (fora de
  `test_ingress_routes.py` e `test_transit_routes.py`) — não rodado. O raio
  de alcance das minhas mudanças é `ingress.py`/`transit.py`/
  `alertmanager.py`/`config/constants/transit.py`; nenhum outro arquivo de
  rota foi tocado, então o risco é baixo, mas isso não foi confirmado por
  execução.
- **`make lint`, `make typecheck`** (as versões completas, sobre a árvore
  inteira) — não rodados; só `ruff check`/`ruff format --check`/`mypy` **sobre
  os 9 arquivos tocados** foram rodados, como o despacho pediu explicitamente
  ("Run the gates your files touch").
- **`make check-imports`, `check-protocols`, `check-deps`,
  `check-config-parity`, `check-integrations`, `check-integration-docs`,
  `check-doc-examples`, `check-display-names`** — nenhum rodado. Nenhuma
  mudança desta fatia toca declaração de integração, schema de configuração,
  nome de exibição ou exemplo de documentação, então o risco esperado é
  baixo, mas "esperado baixo" não é "confirmado".
- **`tests/architecture/test_contract_coverage.py`** — não rodado
  isoladamente (só participou, se participou, da suíte de
  `tests/contract/console/` que não terminou de rodar).
- **`uv run python -m tools.console_gate typecheck/lint/test`** (gates do
  console) — não rodados. Nenhum arquivo TypeScript de produção foi tocado
  nesta fatia — só `console/src/api/schema.ts`, gerado, conferido por
  `client-check` — então não há razão específica para suspeitar de efeito
  ali, mas isso também não foi confirmado por execução.
- **`make verify`** — não rodado, por instrução explícita (do orquestrador).

## O que fica pendente, nomeado, não escondido

- **`tests/security/`** completo — não rodado nesta fatia (ver seção
  anterior). A suíte inteira de `tests/contract/console/` já foi confirmada
  (466 passed, 1 failed pré-existente e alheio a esta fatia — ver acima), o
  que restava de maior risco quando este ledger começou a ser escrito; isto
  não é mais um pendente.
- **Cobertura de teste para o filtro de token de sessão em
  `_delivery_token_name`**: nenhum teste desta fatia emite um token
  "Console sign-in" com escopo `WEBHOOK_DELIVER" e confirma que ele é
  excluído da seleção — a lógica existe (`token.name != CREDENTIAL_NAME`) e
  espelha o que o console já faz, mas a lacuna de cobertura é real e
  nomeada. Quem entrar em T031-T035 (US5) deveria considerar fechá-la, ou
  fechá-la aqui se uma fatia futura voltar a este arquivo.
- **`resource_kind` nunca é literalmente `"container"` garantido por
  contrato** — o teste de T007 usa `"container"` como exemplo no `Resource`
  sintético, mas nenhum teste desta fatia afirma que o estate real do
  HAL9000 sempre classifica um LXC como `"container"` (isso é um fato do
  dado, não do código, e está fora do que T007 pede).
- Todas as ressalvas de escopo já registradas pelas fatias 0 e 1 continuam
  valendo (baseline visual de `machine-tokens`, `_INTEGRATION_READINESS`
  não tocada, etc.) — nada delas foi revisitado nesta fatia.

## Tarefas marcadas em `tasks.md`

**T006, T007, T008, T009, T010, T011 — marcadas `[x]`.** Cada uma tem
implementação real no código, teste que rodou vermelho antes (ou já existia
verde e foi quebrado-e-restaurado para prova) e verde depois, com a saída
colada acima — não uma inferência de que "teria falhado". T012 em diante
permanecem `[ ]`: são das fases 4 em diante, fora desta fatia.

---

# Fatia 3 de nove — T017 e T018

Estado abaixo verificado contra o código nesta árvore, HEAD `6863331` em
`feat/v6-scope-and-settings`, árvore limpa antes desta sessão (confirmado por
`git status --short`). **Escopo: só T017 e T018** — o componente `Overlay`/
`Drawer` compartilhado, por instrução explícita do despacho. Nenhuma tela de
console, i18n, `screens.json`, gateway ou acceptance spec foi tocado. Os dois
arquivos de produção alterados são `console/src/components/overlay.tsx` (o
componente) e `console/src/surfaces/integration-panel.tsx` (a única fiação —
uma linha, `floating`, no `<Drawer>` que já existia); o terceiro arquivo
alterado é o teste, `console/tests/unit/components/overlay.test.tsx`.

## A correção do despacho, confirmada por leitura direta

`Drawer` tem **cinco** consumidores, não quatro — confirmado por
`codegraph_explore` e por grep direto (`grep -rn "Drawer\|Overlay"
console/src`), que devolveu exatamente estes cinco arquivos, nenhum a mais:

1. `console/src/surfaces/integration-panel.tsx` — desta feature.
2. `console/src/shell/shell.tsx`
3. `console/src/live/investigate.tsx`
4. `console/src/gallery/registry.tsx`
5. `console/src/surfaces/override-panel.tsx` — o que `plan.md`/T018 não
   nomeiam, porque não existia quando esta spec foi escrita (chegou na 040).

Os quatro que não são desta feature foram abertos e lidos por inteiro antes de
qualquer edição em `overlay.tsx` — não depois, e não só a partir da leitura de
`overlay.tsx` isolada, como o despacho exigiu.

## Como cada um dos quatro se comporta hoje

| # | Consumidor | `file:line` | Como envolve o `Drawer` | O que isso implica |
|---|---|---|---|---|
| 1 | `Shell` (drawer de navegação) | `console/src/shell/shell.tsx:306-330` | Envolve `<Drawer>` no próprio `<div className="fixed inset-y-0 left-0 z-10 flex w-sidebar max-w-full flex-col overflow-y-auto">`, âncora **esquerda**, largura própria (`w-sidebar`). Comentário no próprio arquivo, `:306-308`: *"Positioned by the shell rather than by the primitive: a drawer is a drawer because of where it sits, and the overlay component is the same panel wherever a screen decides to put it."* | Já resolveu "sobreposto, não no fluxo" por fora do componente, com uma âncora **oposta** à que esta feature precisa (esquerda, não direita). Um `fixed` novo dentro de `Overlay` aninharia dois `fixed` conflitantes e trocaria o lado da navegação. |
| 2 | `InvestigateDrawer` | `console/src/live/investigate.tsx:114-124` | Mesmo padrão: `<div className="fixed inset-y-0 right-0 z-10 flex w-full max-w-prose flex-col overflow-y-auto">` ao redor do `<Drawer>`. Comentário `:114-116` documenta um bug real que essa classe já corrigiu uma vez (`w-full max-w-prose`, nunca `w-prose`, "had no width of its own and collapsed"). | Segunda reimplementação independente da mesma geometria, por fora do componente — mesmo lado (direita) desta vez, mas ainda um `fixed` próprio que um `fixed` novo dentro de `Overlay` aninharia e duplicaria, em vez de substituir. |
| 3 | `registry.tsx` (galeria de componentes) | `console/src/gallery/registry.tsx:791-802` | Renderiza `<Drawer open title="Evidence" onClose={nothing} closeLabel="Close">` **nu**, sem nenhum wrapper, ao lado da entrada de `Modal` (`:780-787`, também nua) — uma entrada estática numa lista de demonstrações de componentes. | Depende de o `Drawer` continuar sendo um bloco comum no fluxo para caber na grade estática da galeria. Um `fixed` incondicional cobriria a página inteira no lugar da célula da grade. |
| 4 (a 5ª, a que a spec não conhece) | `OverridePanel` | `console/src/surfaces/override-panel.tsx:53-62`, consumido em `console/src/surfaces/settings/autonomy.tsx:390-395` | Também renderiza `<Drawer>` nu, sem wrapper — e o próprio `autonomy.tsx` também não envolve `<OverridePanel>` em nenhum `fixed` (confirmado lendo `:385-399`: o JSX cai direto no cabeçalho da tela). O comentário do próprio componente (`override-panel.tsx:9-21`) descreve a intenção — *"opened into a side panel that leaves everything else on the screen visible behind it"* — que hoje **não é entregue**: sem wrapper nenhum, este consumidor tem exatamente o mesmo defeito de bloco-no-fluxo que o painel de integração tinha antes desta fatia, nunca diagnosticado. | É um segundo chamador que **quer** a geometria nova, mas ligá-lo é decisão de quem dono da tela Autonomy (testes próprios, baseline visual própria) — não efeito colateral desta fatia. Registrado como achado, não corrigido aqui. |

## A decisão: sobreposição pedida pelo chamador, não comportamento único

**Decisão tomada, com os quatro abertos na tela**: a geometria de `Drawer` fica
atrás de uma prop opcional, `floating?: boolean`, com default `false` — quem
não pede continua recebendo exatamente o HTML/CSS de hoje, byte a byte. O
painel de integração (`IntegrationPanel`, o único consumidor desta feature) é
quem pede.

A evidência, não a intuição:

- Os consumidores #1 e #2 **já reimplementaram** a geometria fora do
  componente, cada um com sua própria âncora (esquerda vs. direita) e largura
  (`w-sidebar` vs. `w-full max-w-prose`). Um default incondicional aninharia um
  segundo `fixed` dentro do `fixed` de cada um — para o #1, com o lado
  **errado** (a navegação abriria à direita, não à esquerda); para o #2, um
  `fixed` duplicado e redundante que fica frágil no primeiro ajuste futuro de
  largura ou âncora.
- O consumidor #3 depende estruturalmente de o `Drawer` continuar em fluxo
  para caber na lista estática da galeria — um `fixed` teria coberto a página
  inteira no lugar da célula da grade, quebrando a demonstração, não só o
  estilo dela.
- O consumidor #4/5 (`OverridePanel`) já carrega hoje o mesmo defeito que esta
  feature está corrigindo, sem nenhum wrapper — prova de que "todo consumidor
  já se posiciona sozinho" também não é verdade; ligá-lo é trabalho de quem
  dono da tela que o usa, com seus próprios testes e sua própria baseline
  visual, nunca uma mudança de default que ele herdaria de graça.

Com dois dos quatro consumidores restantes dependendo estruturalmente de *não*
receber `fixed` de graça, a alternativa nomeada pelo despacho — opção pedida
pelo chamador — deixou de ser uma entre duas leituras plausíveis e passou a
ser a única que não quebra nada already-shipped.

### A implementação

`console/src/components/overlay.tsx`:

- `FLOATING_DRAWER_CLASS_NAME` (`:33-47`), uma constante de módulo com a
  geometria: `'fixed inset-y-0 right-0 z-10 w-full max-w-prose overflow-y-auto'`.
  Âncora à direita — confirmada contra o mockup normativo
  (`specs_v6/mockups/settings-v6.html:325`, `grid-template-columns:1fr 380px`,
  catálogo à esquerda / painel à direita) e contra o próprio `InvestigateDrawer`
  já existente, o único outro slide-over do console. `z-10` — o mesmo valor que
  todo outro elemento flutuante do console já usa (`shell.tsx`, `topbar.tsx`,
  `notifications.tsx`, `palette.tsx`, `stop.tsx`; confirmado por grep — `z-20`
  aparece uma única vez, em `first-run/tutorial.tsx`, reservado para o tour
  guiado que precisa ficar acima de qualquer outro flutuante — não havia razão
  para inventar um valor novo). `max-w-prose` — a mesma largura que `Modal`
  (`:154` — `className="max-w-prose"`) e o próprio `InvestigateDrawer` já usam
  para o mesmo tipo de painel; nenhum token de largura dedicado a "painel de
  detalhe" existe hoje além desses dois precedentes.
- `OverlayProps.floating?: boolean` (`:61-66`) e `Overlay`'s destructuring
  (`:77`, default `false`), aplicado no `<div role="dialog">`: um atributo
  `data-floating={floating ? 'true' : undefined}` (`:134`) e a classe
  condicional via `cx(base, floating && FLOATING_DRAWER_CLASS_NAME, className)`
  (`:135-139`) — quando `floating` é `false`, `cx` filtra o `false` e a string
  final é idêntica, caractere a caractere, à de antes desta fatia.
- `DrawerProps.floating?: boolean` (`:193-201`) e `Drawer` (`:205-225`),
  repassando para `Overlay` com o mesmo default `false`.
- `console/src/surfaces/integration-panel.tsx:157` — a única linha nova fora
  de `overlay.tsx`: `floating` acrescentado ao `<Drawer>` que já existia
  (`open`, `title`, `onClose`, `closeLabel` — nenhum outro ficou alterado).

Nenhum dos outros quatro `<Drawer>` da árvore foi tocado — `shell.tsx`,
`investigate.tsx`, `registry.tsx` e `override-panel.tsx` continuam chamando
`Drawer` exatamente como antes, sem a prop nova, e portanto continuam
recebendo exatamente o HTML de hoje.

## T017 — o teste, vermelho confirmado, depois quebra-e-restaura das partes que já vinham verdes

Arquivo: `console/tests/unit/components/overlay.test.tsx` (já existia, cobria
`Modal`, `Drawer` e `ConfirmDestructive` — estendido, não duplicado num arquivo
novo, para não fragmentar o "um componente, um arquivo de teste" que a árvore
já segue).

**Primeiro rodar, antes de qualquer implementação** (`cd console && pnpm exec
vitest run tests/unit/components/overlay.test.tsx`):

```
Test Files  1 failed (1)
     Tests  1 failed | 16 passed (17)

 FAIL  tests/unit/components/overlay.test.tsx > Drawer > the overlay geometry, once a caller asks for it > is taken out of the document flow and anchored above the page
Error: expect(element).toHaveClass("fixed")

Expected the element to have class:
  fixed
Received:
  bg-raised edge border-border rounded-4 shadow-2 p-5 flex flex-col gap-4 motion-overlay
```

Confirmado vermelho de verdade — a alegação de geometria (`toHaveClass('fixed')`
+ `toHaveAttribute('data-floating', 'true')`) não tinha como passar antes de
`floating` existir.

**As outras 16 passaram no primeiro rodar.** Cinco delas são alegações novas
que dependem do mecanismo compartilhado de `Overlay` (foco entra, foco fica
preso nas duas direções, Escape fecha, foco volta ao abridor — as quatro
propriedades que o comentário do próprio arquivo já nomeia — mais o guard-rail
"o default continua sem `fixed`"), escritas na variante `floating` do `Drawer`
especificamente para provar que a mudança de geometria não custaria nenhuma
delas. Como todas cinco passaram de cara — o mecanismo de foco é o mesmo,
`floating` sendo uma prop desconhecida antes da implementação é simplesmente
ignorada pelo React — cada uma foi quebrada-e-restaurada em `overlay.tsx`
antes de contar como coberta, exatamente o procedimento de "caracterização"
que as fatias 1 e 2 já usaram. Backup em scratchpad
(`overlay.tsx.pristine`, `md5sum` conferido antes/depois de cada restauração),
nunca `git checkout`/`stash`/`restore`.

| # | Alegação (variante `floating`) | Fonte quebrada | Quebra | Mensagem vermelha observada | Restaurado |
|---|---|---|---|---|---|
| 1 | "renders as a plain block... when nobody asks for the overlay" (o guard-rail do default) | `overlay.tsx`, classe base + `data-floating` | Adicionado `fixed` incondicional à classe base e `data-floating="true"` incondicional | `expect(element).not.toHaveClass("fixed")` → recebeu `fixed bg-raised edge border-border ...` | sim, `git diff --stat` vazio |
| 2 | "moves focus into itself when it opens" | `overlay.tsx:91`, `first?.focus()` | Trocado por `void first;` (foco nunca movido) | `<div role="dialog" ...> does not contain: <body />` — e quebrou também o teste homônimo de `Modal`, confirmando que é o mesmo mecanismo compartilhado | sim |
| 3 | "keeps focus inside, in both directions" | `overlay.tsx:102`, condição de entrada do handler de Tab | Trocado por `if (true) return;` (trava de Tab desligada) | `expected <body>...` ≠ `<button>Close</button>` — quebrou também o de `Modal` | sim |
| 4 | "dismisses on escape" (variante `floating`) | `overlay.tsx:98`, `event.key === 'Escape'` | Trocado por `event.key === 'NeverMatches'` | `expected "vi.fn()" to be called once, but got 0 times` — quebrou os três testes de Escape do arquivo (Modal, Drawer simples, Drawer `floating`) | sim |
| 5 | "gives focus back to whatever opened it, once it closes" | `overlay.tsx:122`, `opener.current.focus()` | Trocado por `void opener;` (retorno de foco desligado) | `expected <body>...</body> to be <button type="button">Open</button>` | sim |

Cada restauração foi seguida de `git diff --stat -- src/components/overlay.tsx`
vazio antes da próxima quebra — nunca duas quebras acumuladas no mesmo build,
a lição que a fatia 1 registrou depois de um falso-verde por sobreposição
acidental. Ao final das cinco, o arquivo foi restaurado uma última vez e
confirmado limpo antes de começar a implementação real.

**Nota de honestidade sobre o teste #5**: como nenhum teste anterior de
`Drawer` no arquivo já montava um `open`/`close` real controlado por estado
(o `Modal`'s teste homônimo só confirma que `onClose` foi chamado, nunca de
fato mede o foco de volta), este teste precisou de um componente-harness local
com `useState` — não havia um `Drawer` já aberto para fechar de verdade, e sem
abrir de verdade a partir de um elemento com foco, "focus volta para quem
abriu" não significa nada. Escrito porque o despacho nomeou explicitamente
esse risco ("A geometry change that silently costs the focus trap would pass
any test that only measured position").

**Rodar final, depois da implementação** (`pnpm exec vitest run
tests/unit/components/overlay.test.tsx`): **17 passed (17)**.

## Gates deste componente/arquivo

| Gate | Comando | Resultado |
|---|---|---|
| `overlay.test.tsx` isolado | `pnpm exec vitest run tests/unit/components/overlay.test.tsx` | **17 passed** |
| Os quatro consumidores não desta feature + toda `tests/unit/surfaces/` | `pnpm exec vitest run tests/unit/components/overlay.test.tsx tests/unit/surfaces/ tests/unit/shell/shell.test.tsx tests/unit/live/live-run.test.tsx tests/unit/live/edges.test.tsx tests/unit/gallery.test.tsx tests/unit/gallery-page.test.tsx` | **97 files, 1673 tests passed** — inclui `shell.test.tsx` (consumidor #1), `live-run.test.tsx`/`edges.test.tsx` (consumidor #2), `gallery.test.tsx`/`gallery-page.test.tsx` (consumidor #3), `override-editor.test.tsx` e `settings/autonomy.test.tsx` (consumidor #4/5, dentro de `tests/unit/surfaces/`) — nenhum regrediu |
| `console_gate typecheck` | `uv run python -m tools.console_gate typecheck` | **passou**, `tsc --noEmit` sem saída, exit 0 |
| `console_gate lint` | `uv run python -m tools.console_gate lint` | Primeira rodada: 2 erros reais (`@typescript-eslint/no-confusing-void-expression` nos dois `onClick` do harness de teste, arrow shorthand devolvendo `void`). Corrigido com chaves explícitas. Segunda rodada: **passou**, exit 0 |
| `console_gate format-check` | `uv run python -m tools.console_gate format-check` | **passou**, "All matched files use Prettier code style!", exit 0 |
| `console_gate test` (suíte inteira + cobertura) | `uv run python -m tools.console_gate test` | **147 files, 2502 passed** (2496 da fatia 0 + 6 testes novos deste arquivo — nenhum outro arquivo ganhou ou perdeu teste). Cobertura: Statements 93.96%, Branches 90.26%, Functions 91.71%, Lines 95.96% — todas acima do piso de 90%. Rodado duas vezes, sem pipe, `echo "EXIT_CODE=$?"` lido diretamente das duas vezes: **0** ambas |
| `make verify` | não rodado | do orquestrador, por instrução explícita desta fatia |

## O check que decide se esta fatia funcionou: o acceptance spec, antes e depois

**Antes** (número já estabelecido pelas fatias 1/2, não remedido do zero por
mim nesta sessão — a árvore de produção não mudou entre o fim da fatia 2 e o
início desta, então o número segue válido; reconstruir um build "antes" só
para reconfirmar seria desfazer minha própria implementação e refazê-la, sem
ganho): **15 failed, 9 passed**.

**Depois** (rebuild real via `uv run python -m tools.console_gate build`,
depois `uv run python -m tools.console_e2e run --
tests/e2e/050-integrations-slideover-intake.acceptance.spec.ts`, suíte inteira,
sem seleção de specs):

```
13 failed
11 passed (53.9s)
```

**Duas das três alegações de geometria foram para verde só com esta mudança,
como o despacho previu**:

- *"the panel overlaps the catalogue instead of sitting at the foot of the
  document"* (linha 341) — **verde**. As três submedidas passaram: o painel
  está `toBeInViewport()` sem rolar mais nada, `getComputedStyle(node).position`
  não é mais `"static"`, e o documento não cresce mais de 20px ao abrir.
- *"a deep link opens the panel with the catalogue scrolled to its own top"*
  (linha 382) — **verde**. `scrollY` no deep-link agora fica ≤20, contra 1209
  medido na fatia 1.

**A terceira melhorou muito, mas não fechou**: *"opening a card does not move
the scroll position"* (linha 307) — **ainda vermelha**, mas o número mudou de
forma real: `scroll moved from 831px to 1209px (Δ378px)` (fatia 1) →
`scroll moved from 831px to 757px (Δ74px)` (agora). Uma queda de 80% no
deslocamento, limiar é <20px.

**As nove alegações que já vinham verdes continuam verdes** — nenhuma das 13
que falham agora é uma das nove originais; conferido nome por nome contra a
tabela da fatia 1 (paginação ausente, contagem única, orçamento de
`/integrations`, fechar restaura rolagem+filtros, três fontes exatas, "Format
& test" recolhido, orçamento de `/settings/alert-intake`, trust line nomeia
token, sem permissão crua). 9 (já verdes) + 2 (novas) = 11 — bate com "11
passed" da saída acima.

### O resíduo de 74px, investigado e não fechado — nomeado para quem entrar em T019

A causa dominante do defeito original — `Overlay` focando o primeiro elemento
focável do painel via `first?.focus()`, e o navegador rolando a página inteira
para trazer esse elemento (então fora da tela, porque o painel era um bloco no
fim de um documento longo) para a viewport — está **eliminada**: com o painel
`fixed`, ele já está dentro da viewport do navegador independente de
`window.scrollY`, então focar um elemento dentro dele não pede mais rolagem
nenhuma ao documento externo. Isso explica os 304px que desapareceram (378→74)
e as duas alegações que foram a verde inteiras.

Os 74px restantes **não vêm de `overlay.tsx` nem de `integration-panel.tsx`** —
investiguei três hipóteses candidatas antes de parar, e descartei as três:

1. **O link do card já pede `scroll={false}`.** Lido em
   `console/src/surfaces/integration-catalogue.tsx:169-174`: o `<NextLink>` de
   cada `catalogue-item` já tem `scroll={false}` e `onClick={captureScrollPosition}`
   — o comportamento padrão do Next.js de rolar para o topo numa navegação já
   estava desligado antes desta fatia. Não é a causa.
2. **`captureScrollPosition`/`consumeScrollPosition`
   (`console/src/surfaces/scroll-memory.ts`) não tocam `window.scrollY`** —
   são `sessionStorage.setItem`/`getItem` puros, confirmado lendo o arquivo
   inteiro (17 linhas). Não é a causa.
3. **Não há `scroll-behavior: smooth` em nenhuma folha de estilo** — a única
   ocorrência de `scroll-behavior` em `console/src/app/globals.css:234` é
   dentro de `@media (prefers-reduced-motion: reduce)`, forçando `auto`
   (instante); não existe uma declaração base de `smooth` em lugar nenhum que
   uma medição "antes de assentar" pudesse estar capturando cedo demais. Não é
   a causa.

O candidato que sobra, e que não pude confirmar sem tocar uma tela (fora do
escopo desta fatia): `/integrations` e `/integrations/<name>` são duas rotas
Next.js **distintas** (`console/src/app/(shell)/integrations/page.tsx` e
`.../[name]/page.tsx`), cada uma chamando `IntegrationsScreen` de forma
independente (`console/src/surfaces/screens/integrations.tsx:220`, comentário
próprio: *"the plain `/integrations` route calls this the same way with no
name at all, so the two addresses render the identical catalogue and differ
only in whether the drawer is open"*) — o painel só entra na árvore por um
condicional (`:531`, `{name === undefined ? null : <IntegrationPanel .../>}`).
Uma navegação cliente entre as duas troca a página inteira por um novo payload
RSC; se qualquer parte do conteúdo acima do ponto de rolagem atual mudar de
altura entre as duas renderizações (mesmo por 1px, num rótulo, numa seção
condicional), o "scroll anchoring" nativo do navegador — que
`position: fixed` explicitamente não participa, mas que o **resto** da árvore
reconciliada participa — pode compensar deslocando `window.scrollY`. Não
confirmei essa hipótese com instrumentação ao vivo (exigiria um script de
depuração descartável a mais, e o achado já não seria meu para corrigir de
qualquer forma — mexer em `screens/integrations.tsx` ou
`integration-catalogue.tsx` está fora do que esta fatia autoriza). Registrado
como o candidato mais provável, com as três alternativas já descartadas, para
quem entrar em T019 não refazer a mesma investigação do zero.

## O que fica pendente, nomeado, não escondido

- **A alegação "opening a card does not move the scroll position" (linha 307
  do acceptance spec) continua vermelha**, Δ74px contra um limiar de 20px —
  ver investigação acima. T019 ("Verificar, no acceptance spec, que a rolagem
  não muda ao abrir...") é quem tem esse fechamento nomeado em `tasks.md`; não
  é T017/T018.
- **`OverridePanel` carrega hoje o mesmo defeito de bloco-no-fluxo que o
  painel de integração tinha antes desta fatia** — achado, não corrigido.
  `floating` está disponível para quem for revisar a tela Autonomy decidir se
  pede; ligá-lo é decisão de outra feature, com seus próprios testes e sua
  própria baseline visual (`console/visual/screens.json` não foi tocado aqui).
- **Nenhuma baseline visual foi tocada** — nem capturada, nem aceita. As
  únicas rotas desta feature em `screens.json` continuam apontando para onde
  a fatia 0 já registrou (`/integrations`/`/integrations/<vendor>` sem
  entrada própria ainda — isso é T044, fase 11, fora desta fatia).
- `make verify`, `console-e2e` completo com todas as specs, e qualquer
  `console-visual-accept` — não rodados, do orquestrador, por instrução
  explícita.
- Os pendentes já nomeados pelas fatias 0-2 (baseline de `machine-tokens`
  divergente, cobertura do filtro de token de sessão em
  `_delivery_token_name`, `_INTEGRATION_READINESS` intocada) continuam
  valendo e não foram revisitados aqui.

## Descobertas que valem para quem entrar em T019 (e adiante)

- **A causa dominante do defeito de rolagem já está corrigida.** Δ378→Δ74 é
  uma queda de 80%; o que resta é um efeito de reconciliação de página, não de
  geometria de overlay.
- **`FLOATING_DRAWER_CLASS_NAME` é o único lugar que decide âncora, largura e
  z-index do slide-over.** Se uma fatia futura precisar mudar qualquer um dos
  três, é ali — não em `integration-panel.tsx`, que só liga a prop.
- **`OverridePanel` é um segundo candidato real a `floating`**, descoberto
  por esta fatia, não hipotético — quem entrar na Autonomy deveria saber que
  o mecanismo já existe e está testado.
- **`overlay.test.tsx` agora cobre as quatro propriedades de teclado também
  para `Drawer`, não só para `Modal`** — antes desta fatia, "foco entra",
  "foco preso nas duas direções" e "foco volta ao abridor" só tinham teste
  para `Modal`; a lacuna era real (confirmada pela leitura do arquivo antes de
  editar, não assumida).

---

# Fatia 4 de nove — T012, T013, T014, T015, T016 e T041

Estado abaixo verificado contra o código nesta árvore, HEAD `0716386` em
`feat/v6-scope-and-settings`, árvore limpa antes desta sessão (confirmado por
`git status --short`). **Escopo: só T012–T016 (US1, o catálogo) e T041 (US7,
o rodapé/empty-state do catálogo)** — por instrução explícita do despacho. O
painel de credencial (`integration-panel.tsx`), a tela de intake
(`alert-intake.tsx`), a cadeia/`schedules-destinations.tsx` e qualquer
baseline visual não foram tocados. `HEAD` não mudou entre o início e o fim
desta sessão — nenhum commit do orquestrador chegou no meio do trabalho.

## Tabela

| Peça | Estado | Detalhe |
|---|---|---|
| T012 — teste de unidade: as três seções na ordem; seção vazia ausente; contagem perde o terceiro termo sem sugestões | **FEITO** | 8 testes novos em `console/tests/unit/surfaces/integrations.test.tsx`. Seis são vermelho→verde genuíno (ver "T012/T015 — vermelho confirmado" abaixo); dois já passavam contra o código anterior à fatia e foram provados por quebra-e-restaura (ver seção própria) — nenhum foi aceito como "coberto" sem essa prova. |
| T013 — remover a paginação do catálogo, constante junto com o único consumidor | **FEITO** | `INTEGRATIONS_CATALOGUE_PAGE_SIZE` apagada dos dois lados do espelhamento: `config/constants/surfaces.py` (constante + entrada em `__all__`) e `config/constants/__init__.py` (import + `__all__`), e do lado do console, `console/src/surfaces/integration-catalogue.tsx` (constante, `Pagination`, `withPage`, o estado `page`/`boundedPage`). Confirmado zero referências restantes em toda a árvore rastreada — ver "Verificação de órfãos" abaixo. |
| T014 — nomear a terceira seção Available; ajustar a contagem do topo | **FEITO** | `console/src/surfaces/integration-catalogue.tsx:261-277` — seção `data-testid="available-section"` com `<h2>` cujo texto é exatamente `catalogue.integrations.available.title` ("Available"/"Disponíveis", novo em `console/src/i18n/en.ts:1462` e `pt-BR.ts:1240`). A contagem do topo (`console/src/surfaces/screens/integrations.tsx:396-406`, inalterada) já cumpria FR-004/005/006/007 antes desta fatia — nenhuma mudança de string foi necessária; ver "A decisão sobre a contagem do topo" abaixo para a leitura completa, incluindo o porquê de eu não ter mexido no texto "integrations available". |
| T015 — busca por nome e capacidade, dentro de todas as seções, ordem preservada | **FEITO** | A peça central desta fatia. `IntegrationCatalogue` (`console/src/surfaces/integration-catalogue.tsx:94-296`) passou a ser o único dono do estado de busca, filtrando Connected, Suggested e Available com o mesmo predicado (`haystack`/`narrow`, `:80-91`) que antes só alcançava Available. Ver "A decisão de arquitetura" abaixo. |
| T016 — teste de orçamento de rolagem para `/integrations` | **FEITO (já existia, verificado)** | A alegação já vivia no acceptance spec (T004, fatia 1, `:291-299`) e já tinha sido provada vermelho→verde lá. Nesta fatia, medi de novo depois de mover a busca para o topo da página e adicionar o heading "Available": `/integrations` continua dentro do orçamento — ver números reais abaixo. Nenhum teste novo foi necessário; a régua já existia e eu a mantive passando. |
| T041 — rodapé com a contagem movida para o roadmap; empty state da busca sem resultado | **FEITO** | Texto do rodapé trocado nos dois idiomas (`en.ts:1490-1491`, `pt-BR.ts:1268-1269`) de "{count} vendors not covered, and why" para "{count} integrations moved to the roadmap · see the list and why" — a mesma frase que a Acceptance Scenario de US7 cita entre aspas. O empty state "nada corresponde em lugar nenhum" (FR-018) generalizado das três seções (`integration-catalogue.tsx:158-176`), com teste novo cobrindo as duas pontas (link e contagem) — ver seção própria. |

## A decisão de arquitetura: por que `IntegrationCatalogue` virou dono das três seções

Antes desta fatia, a busca vivia inteiramente dentro de `IntegrationCatalogueGrid`
— um componente cliente que só via os itens de Available. Connected e Suggested
eram desenhados pelo Server Component (`screens/integrations.tsx`), filtrados
só por `view`/`category` (URL), nunca por `q`. Fazer a busca alcançar as três
seções exigia que as três reagissem ao mesmo estado de busca sem um round-trip
por tecla — a `plan.md` desta feature é explícita sobre isso ("busca filtra no
cliente sem requisição por tecla, com os dados que a página já carregou").
`useSearchParams()`/Context não reduzem essa exigência: alguém ainda precisa
segurar o `useState` da consulta viva num componente cliente comum a todo
mundo que precisa reagir a ela.

A escolha: `screens/integrations.tsx` continua um Server Component puro —
busca os dados, aplica `view`/`category` exatamente como antes
(`visibleConnected`/`visibleSuggested`/`visibleCatalogueRest`, código
intocado, `:254-274`) — e entrega três arrays já enriquecidos
(`connectedItems`/`suggestedItems`/`gridItems`, `:342-374`) para um único
componente cliente novo, `IntegrationCatalogue`
(`integration-catalogue.tsx`), que segura o `query`, filtra os três arrays com
`useMemo` e desenha as três seções — Connected e Suggested migraram para
dentro dele, byte a byte a mesma marcação (`data-testid`, classes, textos)
que tinham em `screens/integrations.tsx`, só realocada. `StatusChip` e
`ScrollCapturingLink` migraram junto, porque um componente cliente pode
importar e renderizar qualquer um dos dois livremente — não há restrição de
"Client Component só renderiza Client Component"; a restrição real (que a
`plan.md` documentava) é que um Server Component não pode passar uma função
para um Client Component, e essa fronteira já era cruzada pelo próprio
`ScrollCapturingLink` antes desta fatia.

Efeito colateral deliberado, não pedido por nenhuma tarefa mas decorrente
direto da mudança: a caixa de busca subiu para o topo da página, acima de
Connected — antes ficava entre Suggested e Available, porque só filtrava
Available. Isso também aproxima o layout do mockup normativo
(`specs_v6/mockups/settings-v6.html:325-328`), que desenha a busca logo abaixo
do subtítulo, antes de "Connected". Nenhum teste (unitário ou do acceptance
spec) afirma a posição da busca, então não há vermelho/verde a reportar aqui
— é uma consequência estrutural registrada, não uma alegação testada.

Os links de cada card (Manage/Connect/o próprio card do grid) passaram a
usar a consulta **viva** (`liveQuery`, incluindo uma busca ainda não
sincronizada com a URL) para as três seções — antes, só o grid fazia isso;
Connected/Suggested usavam a `state` estática do servidor. É uma mudança de
comportamento real, pequena e na direção de mais consistência (fechar o
painel com uma busca em andamento agora preserva essa busca nos três
lugares, não só num), não testada explicitamente por nenhum teste existente
ou novo — nomeada aqui por honestidade, não escondida.

## A decisão sobre a contagem do topo — por que o texto não mudou

O mockup escreve "13 integrations · 3 connected · 3 suggested by your
estate"; a Acceptance Scenario 2 de US1 cita o formato entre aspas como "N
integrations · M connected · K suggested". O texto servido hoje é "{total}
integrations available · {connected} connected · {suggested} suggested"
(`en.ts:1456-1457`, inalterado) — difere pela palavra "available" inserida.

Não troquei essa string, por três razões, na ordem em que pesaram:

1. **O acceptance spec já mede isso, e escolheu não travar o texto.** O teste
   de T004 para essa alegação (`:159-192`) extrai números via regex
   (`/\d+/g`) e verifica a aritmética contra o que a página lista —
   nunca compara a string contra um literal. Quem escreveu esse teste (fatia
   1) leu a mesma spec que eu e decidiu, deliberadamente, que a palavra
   "available" não é uma alegação normativa — só os três números e a sua
   consistência são.
2. **Nenhuma checklist item exige palavra exata aqui.** A checklist de
   qualidade desta spec (`checklists/requirements.md`) só nomeia "palavras
   exatas dos chips" ("Receiving", "Ready — nothing arrived yet") como
   vocabulário travado — ambos de #m3, nenhum da contagem de #m4.
3. **FR-004 pede o conteúdo (total, conectadas, sugeridas), não a frase.**

Se essa leitura for revista, o ponto de troca é `en.ts:1456` e `pt-BR.ts:1234`
— um único par de linhas, nenhuma outra mudança necessária.

## T012/T015 — vermelho confirmado, seis alegações genuinamente novas

Antes de escrever qualquer teste, a implementação já estava pronta — uma
inversão da ordem que o método pede ("a falha aterrissa antes da
implementação"). Registrado aqui em vez de escondido: corrigi isso *depois*
de escrever os oito testes, não pulando a prova — fiz o backup em scratchpad
dos quatro arquivos de produção tocados
(`integration-catalogue.tsx`/`screens/integrations.tsx`/`en.ts`/`pt-BR.ts`),
restaurei os quatro para o conteúdo exato de HEAD (`git diff --stat` vazio
nos quatro, confirmado antes de rodar), e rodei a suíte inteira do arquivo de
teste contra o código **anterior a esta fatia**:

```
pnpm exec vitest run tests/unit/surfaces/integrations.test.tsx --pool=forks
```

Resultado: **37 testes, 6 falhando, 31 passando** — os 29 já existentes mais
dois dos oito novos (ver seção de quebra-e-restaura abaixo para esses dois).
As seis mensagens vermelhas reais:

```
draws Connected, then Suggested by your estate, then Available, with Available carrying its own heading
  TestingLibraryElementError: Unable to find an accessible element with the role "heading" and name "Available"

narrows Connected to the one matching row, and hides Suggested and Available when nothing in them matches
  (falha ao localizar connected-integration filtrado — Connected não reagia a `q` antes desta fatia)

narrows Suggested to the one matching row, and hides Connected and Available when nothing in them matches
  (mesma causa, do lado de Suggested)

keeps a match in every section inside its own section, in the same order, rather than merging or reordering them
  (mesma causa — Connected/Suggested nunca filtravam por `q`)

shows one empty state, offering to clear the search and the same roadmap link, when nothing matches anywhere
  (o empty state de busca-sem-resultado só existia para o grid; com Connected/
  Suggested sempre presentes e não reativos, "nada corresponde em lugar
  nenhum" nunca acontecia)

names the count as integrations moved to the roadmap, not a raw vendor tally
  expect(received).toMatch(expected) — recebido "9 vendors not covered, and why"
```

Depois de confirmar o vermelho, restaurei os quatro arquivos a partir do
backup em scratchpad (`cp`, nunca `git checkout`/`stash`/`restore`) e
confirmei via `md5sum` que bateram exatamente com o que eu tinha escrito —
depois rodei a suíte de novo: **37 passed**. As seis alegações acima são,
portanto, vermelho→verde genuíno, só que na ordem invertida (implementação
antes do teste, corrigida por essa reconstrução em vez de aceita como estava).
Registro isso sem diminuir: a primeira vez que escrevi "test-first" nesta
fatia não foi verdade, e a honestidade aqui é sobre isso, não sobre o
resultado final.

## Quebra-e-restaura das duas alegações que já vinham verdes

Duas das oito alegações novas passaram no primeiro rodar contra o código
**anterior** a esta fatia (a mesma rodada acima, "31 passando" incluía as
duas). Nenhuma foi aceita como coberta sem prova — cada uma foi quebrada no
código **desta fatia** (já restaurado) e a mensagem vermelha, colada abaixo.

| # | Alegação | Por que já passava contra o código anterior | Arquivo quebrado (nesta fatia) | Quebra | Mensagem vermelha observada | Restaurado |
|---|---|---|---|---|---|---|
| 1 | "never renders an empty Available section, when every integration is already Connected or Suggested" | O grid antigo (`IntegrationCatalogueGrid`) já escondia o `catalogue-grid` quando `shown.length === 0`, e nunca teve heading "Available" — a ausência do heading "Available" já era verdade, só que pelo motivo errado (o heading nunca existiu) | `console/src/surfaces/integration-catalogue.tsx:261` | `{matchingAvailable.length === 0 ? null : (` → `{false ? null : (` (seção Available sempre desenha) | `AssertionError: expected <section …> to be null` — a seção `available-section` completa (heading "Available" + `catalogue-grid` vazio) aparece no DOM | sim, `md5sum` idêntico ao antes da quebra |
| 2 | "drops the third term instead of showing zero, when nothing is suggested" | FR-006 já era cumprido antes desta fatia — o ternário `suggested.length > 0 ? ... : ...` em `screens/integrations.tsx` é código que a fatia 4 não tocou | `console/src/surfaces/screens/integrations.tsx` (o parágrafo `catalogue-summary`) | Ternário removido, sempre usa `catalogue.integrations.summary.suggested` | `AssertionError: expected '2 integrations available · 1 connecte…' not to match /suggested/i` — recebido `"2 integrations available · 1 connected · 0 suggested"`, exatamente o "zero em vez de omitir" que FR-006 proíbe | sim |

Depois de cada quebra, o arquivo foi restaurado a partir do backup do
scratchpad e o teste isolado voltou a passar antes de eu seguir para a
próxima quebra — nenhuma das duas quebras ficou acumulada com a outra no
mesmo build.

## T016 — o número, medido de novo depois da mudança

A alegação não é nova (fatia 1 já a tinha vermelho→verde, com a quebra da
constante de orçamento). O que esta fatia fez foi confirmar que reestruturar
a página — heading novo, busca realocada para o topo — não empurrou a altura
para fora do orçamento. Rodando o acceptance spec completo depois do rebuild:

```
✓ catalogue: scroll budget at 1920x1080 › the whole post-cut catalogue fits within 2 viewports (214ms)
```

Verde, sem quebra-e-restaura nova — a fatia 1 já provou que essa régua mede
altura de verdade (quebrando `CONFIG_SCREEN_SCROLL_BUDGET_VIEWPORTS` para
0.1 e vendo `1080px tall against a 108px budget`); refazer essa prova aqui
seria repetir trabalho já registrado, não gerar evidência nova. O número
real ficou dentro da folga generosa que a fatia 0 já tinha medido (1336px
contra 2160px de orçamento) — a mudança desta fatia (heading a mais, busca
realocada) não é grande o bastante para ameaçar essa folga, e a medição via
Playwright confirma isso sem eu precisar estimar.

## Verificação de órfãos — `INTEGRATIONS_CATALOGUE_PAGE_SIZE`

```
git ls-files -z | xargs -0 rg -n "INTEGRATIONS_CATALOGUE_PAGE_SIZE"
```

Antes da fatia: 4 ocorrências (`config/constants/surfaces.py:365` e
`:423` em `__all__`; `config/constants/__init__.py:1223` e `:1762` em
`__all__`; mais as duas do lado do console). Depois: **zero em toda a árvore
rastreada** — nenhum arquivo, de nenhum tier, ainda nomeia a constante. Não
encontrei nenhum teste de arquitetura que exija "toda constante tem um
consumidor" (procurei em `tests/architecture/`, só existe
`test_removed_vendor_references.py`, que não é isso), então a remoção não
arrisca um gate desse tipo. `make check-constants` (rodado diretamente via
`uv run python tools/check_constants.py`) continua limpo — ele valida nomes
de variável de ambiente, não a lista de constantes declaradas.

Nota de honestidade sobre o comentário que a constante levava: o docstring
de `INTEGRATIONS_CATALOGUE_PAGE_SIZE` no lado do console dizia "a contract
test holds this literal against [the Python constant]" — busquei esse teste
de contrato antes de remover qualquer coisa (`tests/contract/console/`,
grep por `page_size`/`PAGE_SIZE`/`pagination`) e **não encontrei nenhum**.
Ou esse teste nunca existiu, ou foi removido em algum momento sem o
comentário ser atualizado — de qualquer forma, não havia gate nenhum
prendendo os dois números um ao outro, e a remoção não quebrou nada que eu
pudesse localizar.

## O que fica pendente, nomeado, não escondido

- **A busca não filtra por nome bruto de integração (`data-integration`),
  só por nome de exibição, categoria, resumo e capacidades** — o mesmo
  predicado que o grid já usava antes desta fatia, agora aplicado às três
  seções. FR-008 pede busca "por nome de exibição e por capacidade"; o
  predicado herdado também inclui categoria e resumo, que já era assim antes
  — não reduzi nem ampliei esse conjunto, só o repliquei para Connected e
  Suggested.
- **Nenhuma baseline visual foi tocada** — nem capturada, nem aceita.
  `console/visual/screens.json` continua exatamente como a fatia 3 o deixou.
  T044 (fase 11) é quem repointa a entrada do painel de credencial.
- **O painel de credencial, a tela de intake, a cadeia e
  `schedules-destinations.tsx` não foram lidos além do necessário para
  confirmar que nada deles foi afetado** — não são meus para tocar nesta
  fatia, e as nove alegações vermelhas restantes do acceptance spec
  (`opening a card…`, `no empty credential field…`, `offers Test again…`,
  as três de intake, `the copied receiver YAML…`, as duas da cadeia)
  continuam exatamente onde a fatia 3 as deixou — nenhuma piorou, nenhuma
  mudou de mensagem, conferido nome a nome contra a saída desta fatia.
- **A posição da caixa de busca (subiu para o topo da página) não tem teste
  próprio** — é uma consequência estrutural da arquitetura que T015 exigiu,
  não uma alegação de nenhuma tarefa desta fatia; nomeada acima, não
  escondida.
- **Os links de card usando a consulta viva em vez da estática nas três
  seções** — mudança de comportamento real e pequena, não coberta por teste
  novo ou existente; nomeada acima.

## Os números do acceptance spec — antes e depois desta fatia

**Antes** (herdado da fatia 3, não remedido do zero — a árvore de produção
não mudou entre o fim da fatia 3 e o início desta): **13 failed, 11 passed**.

**Depois** (rebuild real via `uv run python -m tools.console_gate build`,
depois `uv run python -m tools.console_e2e run --
tests/e2e/050-integrations-slideover-intake.acceptance.spec.ts`, suíte
inteira, sem seleção de specs, sem pipe — `echo "EXIT_CODE=$?"` lido
diretamente):

```
9 failed
15 passed (42.2s)
```

As quatro alegações que foram a verde, nome a nome:

- `:91` "Connected, Suggested by your estate and "Available" appear in that order" — **verde**.
- `:194` "searching by an item's own name narrows every section, not only Available" — **verde**.
- `:227` "searching by a capability narrows every section, not only Available" — **verde**.
- `:271` "the footer names how many integrations moved to the roadmap, with a link to the list" — **verde**.

`:291` "the whole post-cut catalogue fits within 2 viewports" (T016) segue
**verde**, como já era.

**As onze que já vinham verdes continuam verdes** — conferido nome a nome
contra a lista da fatia 3 (`:145` sem paginação, `:159` contagem única,
`:291` orçamento de `/integrations`, `:341` painel sobreposto, `:382`
deep-link no topo, `:394` fechar restaura, `:489` exatamente três fontes,
`:561` Format & test recolhido, `:577` orçamento de alert-intake, `:645`
trust line nomeia token, `:663` sem permissão crua). 11 (já verdes) + 4
(novas) = 15 — bate com "15 passed" da saída acima. As nove que continuam
vermelhas (`:307` rolagem ao abrir, `:440` campo vazio com ação desabilitada,
`:466` três ações nomeadas, `:495`/`:515`/`:535` as três de intake, `:599`
YAML copiado, `:709`/`:749` as duas da cadeia) pertencem às fases 5, 6, 7, 8
e 9 — nenhuma delas é minha nesta fatia, e nenhuma piorou.

## Suíte transversal — verificação extra, não um dos quatro gates pedidos

Como esta fatia reestrutura `/integrations` de forma substancial (busca
realocada, heading novo, remoção de paginação), rodei
`tests/e2e/transversal-rules.spec.ts` (a suíte que a fatia 1 já ampliou para
incluir `/integrations` explicitamente) como conferência extra, não porque o
despacho a exigisse:

```
uv run python -m tools.console_e2e run -- tests/e2e/transversal-rules.spec.ts
```

Resultado: **25 passed, 7 skipped** — número idêntico ao que a fatia 3
registrou. Nenhuma regressão de vocabulário banido, orçamento de rolagem ou
coluna de valor vazia em `/integrations`.

## Gates rodados nesta fatia

| Gate | Comando | Resultado |
|---|---|---|
| `console_gate format-check` | `uv run python -m tools.console_gate format-check` | Primeira rodada: 2 arquivos desformatados (`integration-catalogue.tsx`, `screens/integrations.tsx`) — corrigido com `pnpm exec prettier --write`. Rodada seguinte, depois de adicionar os testes: mais 1 arquivo (`integrations.test.tsx`) — mesma correção. **Final: passou**, "All matched files use Prettier code style!" |
| `console_gate lint` | `uv run python -m tools.console_gate lint` | Primeira rodada nos dois arquivos de produção: passou. Depois de adicionar os testes: 2 erros reais (`@typescript-eslint/no-unnecessary-condition` em `summary.textContent ?? ''` e `link.textContent ?? ''` — `textContent` não é nulável neste `tsconfig`, o mesmo padrão que a fatia 1 já tinha encontrado). Corrigido removendo o `?? ''` desnecessário. **Final: passou**, exit 0 |
| `console_gate typecheck` | `uv run python -m tools.console_gate typecheck` | **Passou** em todas as rodadas, `tsc --noEmit` sem saída |
| `console_gate test` (suíte inteira + cobertura) | `uv run python -m tools.console_gate test` | **147 files, 2510 passed** (2502 da fatia 3 + 8 testes novos — nenhum outro arquivo ganhou ou perdeu teste). Cobertura: Statements 94.01%, Branches 90.26%, Functions 91.77%, Lines 96.01% — todas acima do piso de 90%. Rodado duas vezes (antes e depois da correção de lint), `echo "EXIT_CODE=$?"` lido diretamente das duas vezes: **0** ambas |
| Acceptance spec desta feature (não um dos quatro pedidos, mas o que decide se a fatia funcionou) | `uv run python -m tools.console_e2e run -- tests/e2e/050-integrations-slideover-intake.acceptance.spec.ts` | **9 failed, 15 passed** — ver seção própria acima |
| Suíte transversal (extra) | `uv run python -m tools.console_e2e run -- tests/e2e/transversal-rules.spec.ts` | **25 passed, 7 skipped**, idêntico à fatia 3 |
| Python: ruff lint dos dois arquivos tocados | `uv run ruff check config/constants/__init__.py config/constants/surfaces.py` | limpo |
| Python: ruff format-check dos dois arquivos tocados | `uv run ruff format --check config/constants/__init__.py config/constants/surfaces.py` | já formatados |
| Python: mypy dos dois arquivos tocados | `uv run mypy config/constants/__init__.py config/constants/surfaces.py` | `Success: no issues found in 2 source files` |
| `check-constants` | `uv run python tools/check_constants.py` | limpo, exit 0 |
| `make verify` | não rodado | do orquestrador, por instrução explícita desta fatia |

## Tarefas marcadas em `tasks.md`

T012, T013, T014, T015, T016 e T041 — marcadas `[x]`. Nenhuma outra tarefa
foi tocada; T017–T040, T042–T050 permanecem exatamente como a fatia 3 as
deixou.

---

# Fatia 5 de nove — T019 a T026 (ledger de resgate, escopo parcial)

Estado abaixo verificado contra o código nesta árvore, HEAD `d841bdd` em
`feat/v6-scope-and-settings`, árvore limpa antes desta sessão (confirmado por
`git status --short` no início). **Esta fatia foi interrompida pelo
orquestrador antes do fim planejado** — a instrução de parar chegou logo
depois de um ciclo de quebra-e-restaura dos três arquivos de backend do
Disconnect, com a restauração já confirmada por `md5sum` mas o teste de
confirmação ainda não lido. Este ledger é o resgate: registra o que está de
pé, testado e provado, o que foi desenhado mas não escrito, e o que não foi
tocado — nada foi inferido além do que os comandos abaixo realmente
mostraram.

**Escopo nomeado no despacho: T019–T026 (o painel de credencial).** Não
toquei a tela de intake (fatia 6), a cadeia ou `schedules-destinations`
(fatia 7), nem nenhuma baseline visual (fatia 8).

## Tabela — estado real de cada tarefa

| Tarefa | Estado | Detalhe |
|---|---|---|
| T019 — verificar que a rolagem não muda ao abrir, deep-link no topo, fechar devolve posição+filtros | **FEITO** | Causa raiz encontrada e confirmada por dois experimentos independentes; correção real implementada e verificada pelo próprio acceptance spec. Ver seção própria abaixo. Marcado `[x]` em `tasks.md`. |
| T020 — placeholder do endereço descoberto + instrução por campo | **NÃO INICIADO** | Investigado a fundo — a leitura literal da tarefa esbarra numa ambiguidade real de dados (nenhum vendor declara um campo de "endereço" no schema de credencial). Decisão de desenho registrada, seção própria abaixo, nenhuma linha de código escrita. |
| T021 — deep-link para integração ausente oferece voltar e ver o roadmap | **NÃO INICIADO** | Desenho decidido (falta uma prop `notCoveredHref` no painel e um segundo link), nenhuma linha de código escrita. |
| T022 — teste de unidade: credencial guardada não mostra campo vazio nem ação desabilitada, afirma vault | **NÃO INICIADO** | Arquivo de teste não criado. |
| T023 — teste de unidade: as três ações presentes e nomeadas; substituir revela o formulário | **NÃO INICIADO** | Mesma situação de T022. |
| T024 — implementar as três ações em `integration-panel.tsx` | **PARCIAL** | A metade que a própria tarefa nomeia — as três ações **em `integration-panel.tsx`** — **não foi escrita**. O que existe é a pré-condição de backend para uma delas ("Disconnect" precisa de algo para chamar): a rota `DELETE /v1/integrations/{name}/credential`, nova, implementada e provada vermelho→verde por si mesma (ver seção própria). Nenhuma tarefa desta fase pedia essa rota explicitamente — é uma decisão minha, justificada e registrada abaixo — e ela sozinha **não cumpre T024**, que é sobre o arquivo do console. |
| T025 — Disconnect exige confirmação nomeando a integração e o que será removido | **NÃO INICIADO** | Depende de T024 existir primeiro. A rota que a confirmação chamaria já existe (acima), a UI de confirmação, não. |
| T026 — teste de segurança: nenhum valor de credencial after guardar/testar de novo, em resposta ou DOM | **NÃO INICIADO** | Arquivo de teste não criado. |

**Números do acceptance spec, medidos de verdade, uma vez, depois da correção de T019:**

Antes desta fatia (herdado da fatia 4, confirmado pelo despacho): **9 failed, 15
passed**. Depois da correção de T019 (rebuild real via
`uv run python -m tools.console_gate build`, depois
`uv run python -m tools.console_e2e run --
tests/e2e/050-integrations-slideover-intake.acceptance.spec.ts`, suíte
inteira, sem seleção de specs):

```
8 failed
16 passed (41.0s)
```

As 8 que continuam vermelhas, nome a nome — conferido que são exatamente as 8
que já eram vermelhas na fatia 4 **menos** a de rolagem:
`:440` (campo vazio com ação desabilitada — minha, T022/T024), `:466` (três
ações nomeadas — minha, T024), `:495`/`:515`/`:535` (as três de intake — fatia
6), `:599` (YAML copiado — fatia 6), `:709`/`:749` (as duas da cadeia — fatia
7). Nenhuma das 16 que passam regrediu — conferido nome a nome contra a lista
da fatia 4 mais a nova (`:307`).

## T019 — a causa real do salto de 74px, confirmada por experimento, não por leitura de código

**A pergunta que a fatia 3 deixou em aberto**: depois de `floating` corrigir a
geometria do painel (Δ378px→Δ74px), o que restava do salto não vinha de
`overlay.tsx` nem de `integration-panel.tsx` — a fatia 3 suspeitou de uma
troca completa de árvore React entre `/integrations` e `/integrations/[name]`
(duas rotas Next.js distintas) possivelmente acionando o "scroll anchoring"
nativo do navegador, mas não confirmou, porque confirmar exigia um script de
diagnóstico que a fatia 3 não estava autorizada a escrever.

**Instrumentação real, descartável, nunca commitada nem staged**:
`console/tests/e2e/_zzz-t019-diagnose-scroll.spec.ts` — escrito, rodado várias
vezes, apagado ao final (`rm`), confirmado fora da árvore por
`git status --short console/tests/e2e/` vazio. Instalava um listener de
`scroll` e um `MutationObserver` na árvore inteira antes do clique, registrando
`window.scrollY` e `document.documentElement.scrollHeight` a cada mutação e a
cada evento de rolagem, com timestamps de `performance.now()`.

**O que a instrumentação mostrou, medição real:**

1. `document.documentElement.scrollHeight` **não muda** — 1582px antes do
   clique e 1582px depois de tudo assentar. Isso **descarta** a hipótese de
   "o conteúdo acima do ponto de rolagem cresceu ou encolheu de forma
   persistente" — não cresceu nem encolheu, no antes/depois.
2. O salto acontece como **um único evento de `scroll` discreto** (862px →
   788px, Δ=74px, batendo com o número que a fatia 3 já tinha medido), no
   mesmo instante em que o `MutationObserver` relata uma **substituição
   completa** dos filhos de `<head>`, `<body>` e
   `MAIN#main[data-testid=main]` — consistente com a troca de árvore inteira
   entre as duas rotas distintas, como a fatia 3 suspeitou.
3. **Hipótese "CSS scroll anchoring" testada diretamente e descartada**: apliquei
   `overflow-anchor: none` tanto via `element.style` quanto via
   `page.addStyleTag` no `<html>`, antes de qualquer rolagem — em ambos os
   casos o salto continuou **idêntico**, 862→788, byte a byte. Se fosse
   scroll anchoring nativo, desligar `overflow-anchor` teria de mudar alguma
   coisa. Não mudou nada. **Descartada com evidência direta, não por
   dedução.**
4. **Hipótese real, confirmada por experimento controlado**: apliquei
   `min-height: 4000px !important` em `html, body` antes do clique — o
   suficiente para que o documento nunca pudesse ficar mais curto que a
   posição de rolagem atual, não importa o que acontecesse com o conteúdo de
   `<main>` durante a troca. Com essa condição: **o salto desaparece por
   completo** — `BEFORE 1039 AFTER 1039`, sem nenhuma correção de código.
   Isso é a confirmação direta: **durante a troca de árvore completa entre as
   duas rotas, o documento fica momentaneamente mais curto que a posição de
   rolagem que o operador estava — o navegador limita (`clamp`)
   `window.scrollY` ao máximo possível naquele instante, e não desfaz esse
   limite quando o conteúdo volta à altura total.** Não é uma característica
   de "scroll anchoring" (já descartada); é o comportamento comum e chato de
   qualquer scroll container quando o conteúdo dele encolhe e volta a
   crescer sem que nada peça à página para rolar de volta.

**Por que isso nunca apareceu como diferença de altura na minha instrumentação
via `MutationObserver`**: o `MutationObserver` só relata depois que **todas**
as mutações de um lote síncrono já aconteceram — se a árvore antiga é
removida e a nova é inserida no mesmo ciclo sem o React ceder o controle no
meio, a "altura momentaneamente mais curta" nunca fica visível a um
observador assíncrono, só ao próprio mecanismo de clamp do navegador, que age
de forma síncrona durante o layout.

**A correção real, implementada e testada** (não a `min-height` artificial —
essa foi só para confirmar a hipótese, nunca chegou no código real):

- `console/src/surfaces/scroll-memory.ts` — reescrito. `captureScrollPosition`
  agora grava `{y, at}` (posição + timestamp) em vez de um número cru,
  serializado via `JSON.stringify`. Nova função `peekScrollPosition()`: lê
  **sem apagar** (ao contrário de `consumeScrollPosition`, que continua
  apagando), e **descarta qualquer valor com mais de 5000ms**
  (`SCROLL_MEMORY_MAX_AGE_MS`) — a guarda contra um perigo real que só
  apareceu ao desenhar a correção: sem essa idade máxima, um deep-link direto
  (`/integrations/alertmanager` colado na barra, carga inteira, `scrollY`
  nativamente 0) poderia herdar uma posição **antiga**, deixada no
  `sessionStorage` por uma aba que abriu o painel e nunca fechou (recarga
  dura, aba fechada sem clicar em "Close") — e ser empurrado para baixo em
  vez de aterrissar no topo, quebrando exatamente o FR-022 que T019
  também verifica. 5000ms é generoso para a navegação cliente mais lenta
  realista e curto demais para "o operador voltou a esta aba depois".
  `consumeScrollPosition` foi reescrita por cima de `peekScrollPosition`
  (mesma leitura, mais o `removeItem`), então as duas funções não podem
  divergir na lógica de parsing/idade.
- `console/src/surfaces/integration-panel.tsx:109-127` (aprox.) — o mesmo
  `useEffect` que já restaurava a rolagem no **unmount** ganhou uma correção
  no **mount**: `peekScrollPosition()` (nunca `consume`, porque o cleanup do
  mesmo efeito ainda precisa do valor na saída) e, se `window.scrollY`
  divergir do valor lembrado, `window.scrollTo(0, remembered)`. `peek`, não
  `consume`, é a decisão que faz as duas metades da mesma viagem (abrir e
  fechar) continuarem lendo o mesmo valor.

**Prova de que a correção funciona, com o mecanismo real, não com o
artifício de diagnóstico**: rebuild (`console_gate build`), instrumentação
reaplicada sem a `min-height`/`overflow-anchor` de teste: **`BEFORE 862 AFTER
862`** — nenhum salto. Depois, a prova que importa: o acceptance spec
completo, `:307` saiu da lista de vermelhas (ver números acima, 9→8
failed, 15→16 passed), e nenhuma das outras 8 alegações vermelhas nem das 15
verdes mudou de nome.

**O que este achado implica para quem entrar em T044/T046 (baselines
visuais, fatia 8)**: a captura de `/integrations/<vendor>` para
`screens.json` deve ser feita **depois** de um clique real que abre o painel
(não só um `page.goto` direto), porque é exatamente esse caminho que tinha o
defeito — um deep-link direto nunca teve o problema (a página já carrega do
zero em `scrollY=0`, nada para "clampar").

## T024/T025 (metade backend) — `DELETE /v1/integrations/{name}/credential`

**Por que fui além de um arquivo só, quando o texto da tarefa diz
"em `integration-panel.tsx`"**: antes de escrever a UI, chequei o que já
existe para "Disconnect" chamar. Não existe nada — nenhuma rota
`DELETE`/similar em `gateway/http/routes/integrations.py` (confirmado por
`grep -n "delete\|DELETE\|@router\." gateway/http/routes/integrations.py`
antes de qualquer edição: só `GET`, `POST .../verify`, `POST
.../verify/report`, `PUT .../credential`). Considerei as duas leituras —
construir a rota (Fase 3 não previu isso, o texto de T024 fala de um arquivo
só) contra deixar o botão sem efeito real — e decidi construir, porque
FR-038 ("o painel DEVE oferecer Disconnect") lido como "oferece um botão que
não desconecta nada de verdade" é uma implementação oca, e porque
`Vault.delete()` (`platform/credentials/vault.py:313`) já existe e já é
testado na camada de persistência — o trabalho que sobrava era só a rota, a
permissão e o registro de auditoria. **Registro isto como decisão minha, não
como algo que uma tarefa nomeada pediu** — se o próximo a entrar achar que
isso excedeu o escopo desta fatia, a rota está isolada, testada por si só e
fácil de reverter sem tocar o resto.

**Vermelho confirmado antes de qualquer implementação**, revertendo os três
arquivos por edição direta (nunca `git checkout`/`stash`/`restore` — reverti
exatamente as linhas que eu mesmo tinha acabado de escrever, depois restaurei
de uma cópia em scratchpad, `md5sum` conferido igual antes/depois):

```
uv run pytest tests/unit/gateway/http/test_integration_credential_delete.py -q
```

```
6 failed in 0.75s
```

com a rota ausente, cada teste batendo em `405 Method Not Allowed` (a rota
`PUT` continua lá; só `DELETE` não existe) — por exemplo:

```
tests/unit/gateway/http/test_integration_credential_delete.py:129: in test_an_unknown_integration_is_not_found
    assert response.status_code == 404
E   assert 405 == 404
```

**Depois de restaurar a implementação** (confirmado por `md5sum` idêntico à
cópia de scratchpad feita logo após escrever o código, nos três arquivos):

```
uv run pytest tests/unit/gateway/http/test_integration_credential_delete.py -q
```

```
6 passed in 0.36s
```

**Arquivos tocados**:

- `gateway/http/routes/integrations.py` — `CredentialDeleteView` (novo model,
  ao lado de `CredentialWriteView`) e `delete_credential`
  (`@router.delete("/{name}/credential")`, novo): usa `Vault.delete()`,
  registra `CREDENTIAL_AUDIT_ACTION_DELETE` via `AuditRecorder`, esquece
  qualquer verificação gravada (`forget_check`, os mesmos `_affected_kinds`
  que a escrita já usa) e devolve `{integration, versions_removed}` — nada
  por onde um valor pudesse passar. Idempotente: desconectar algo nunca
  configurado devolve `versions_removed=0` com `200`, não um erro — testado
  explicitamente (`test_disconnecting_something_never_configured_...`),
  porque um painel desatualizado que manda "Disconnect" duas vezes não deve
  encontrar um erro sobre um fato que já é verdade.
- `gateway/http/security/onboarding_routes.py` — nova linha na tabela de
  rotas: `DELETE /v1/integrations/{name}/credential`, mesma permissão que o
  `PUT` ao lado (`Permission.CREDENTIAL_WRITE`) — decisão registrada no
  próprio docstring do arquivo: quem pode guardar uma credencial é quem pode
  tirá-la, uma permissão mais estreita aqui seria uma segunda porta não
  documentada sobre o mesmo material.
- `platform/identity/audit/recorder.py` — nova constante
  `CREDENTIAL_AUDIT_ACTION_DELETE = "credential.delete"`, acrescentada a
  `AUDITED_ACTIONS`. Confirmado, antes de tocar o arquivo, que
  `tests/security/test_impersonation_audit.py` é o único lugar que itera essa
  tupla (`grep -rln "AUDITED_ACTIONS" tests/`) e que os testes parametrizados
  sobre ela (`test_every_audited_action_records_both_principals`,
  `test_every_audited_action_records_the_mandatory_fields`) são genéricos —
  testam a mecânica comum de `AuditContext`/`AuditRecorder`, não uma
  asserção por ação — e que `test_the_action_vocabulary_covers_every_class...`
  confere um subconjunto (`<=`), nunca um conjunto fechado, então acrescentar
  `credential.delete` ao domínio `credential` (que `credential.write` e
  `credential.rotate` já ocupam) não arrisca quebrar nenhum dos três.
  **Não rodei `tests/security/test_impersonation_audit.py` nesta sessão** —
  a leitura acima é análise do próprio arquivo de teste, não uma execução;
  fica para o próximo passo confirmar por execução.
- `tests/unit/gateway/http/test_integration_credential_delete.py` (novo, 170
  linhas) — 6 testes: remove todas as versões do vault de verdade
  (confirmado lendo `Vault.active()` depois), idempotente quando nada estava
  configurado, a resposta não carrega nenhum dos dois segredos de teste
  plantados nem em corpo cru, `404` para um nome que a fábrica de vendors não
  conhece, `403` para um token sem `credential.write`, e o evento de
  auditoria carrega `action=credential.delete` (nunca `credential.write`) com
  o ator e o `versions_removed` certos.

## O que fica pendente, nomeado, não escondido

### Trabalho de console ainda não escrito — T020, T021, T022, T023, a metade de T024, T025, T026

Nada abaixo tem uma linha de código escrita. São decisões de desenho
investigadas e registradas, para que quem continuar não repita a mesma
investigação do zero.

**T020 — o campo de endereço, a ambiguidade real encontrada**: FR-028 pede
"quando o estate conhece o endereço do serviço, o campo de endereço DEVE
trazê-lo como placeholder". Investiguei os cinco vendors auto-hospedados
plausíveis (`alertmanager`, `loki`, `prometheus`, `grafana`, e todo o resto
via `rg -n 'public\(|secret\(' integrations/*/schema.py`) e **nenhum dos 15
vendors declara um campo de endereço/URL/host no próprio `CredentialSchema`**
— todos só declaram `token` (secreto) e às vezes `tenant`/`org` (público). O
endereço de cada vendor é resolvido por fora do formulário de credencial
(`RULE`/`REGIONS`/allow-list de host), não por um campo que o operador
digita. A única "endereço descoberto" que existe de verdade no payload é
`item.suggested.address` (`SuggestionView`, já confirmado servido pela fatia
2) — e isso só existe para um item **ainda não conectado que o estate achou
rodando** (`suggested !== undefined`), nunca para um item já conectado.
Também confirmei que `Input`
(`console/src/components/form.tsx:140-177`) **não tem prop `placeholder`
nenhuma, por desenho deliberado** — o próprio comentário do arquivo (`:11-14`)
argumenta contra usar placeholder nativo como única instrução. Dado isso,
minha leitura (não implementada): a "placeholder" do FR-028 não é o atributo
HTML `placeholder`, é o sentido comum da palavra — um valor mostrado como
referência. Já existe precedente **idêntico** em
`console/src/surfaces/first-run/integrations.tsx:123`:
`{labels.foundHere} {offer.suggested.address}` (uma frase, não um atributo),
com o rótulo `firstRun.integrations.foundHere` = "Found in your estate at"
já traduzido nos dois idiomas. Meu plano, não escrito: acrescentar
`discoveredAddress: string` a `IntegrationPanelItem` (vindo de
`panelItem.suggested?.address ?? ''` em `screens/integrations.tsx`), uma
linha nova rotulada no mesmo padrão, renderizada só quando não-vazia, antes
de `<CredentialField>`, dentro do ramo `writable`. **Isto é uma decisão de
desenho, não uma leitura óbvia da spec** — vale alguém revisar antes de
implementar, exatamente como a fatia 0 pediu revisão deliberada da decisão
sobre `"failing"`.

**T021 — o link para o roadmap**: hoje
(`console/src/surfaces/integration-panel.tsx`, ramo `item === null`) só
existe um link, de volta ao catálogo (`labels.notFoundAction` →
`closeHref`). FR-021/edge case pedem também um link para a página de
referência do roadmap. `screens/integrations.tsx:332` já calcula
`notCoveredHref` — hoje só é usado no rodapé do catálogo, nunca passado para
`<IntegrationPanel>`. Plano, não escrito: nova prop `notCoveredHref: string`
em `IntegrationPanelProps`, nova label
`catalogue.integrations.panel.notFound.roadmap`, segundo `<NextLink>` ao
lado do existente.

**T022/T023/T026 — o que já existe de graça e o que falta escrever**:
confirmei, lendo `console/src/design/status.ts:129-164` por inteiro, que
`credentialStatus()`/`CREDENTIAL_STATUS_ALIASES` **já mapeia** o valor bruto
`"unknown"` (backend: guardada, nunca verificada) para o canônico `'stored'`
— não para `'unknown'` — então o `<StatusChip status={item.health}>` que já
existe no topo do painel (`integration-panel.tsx:179`) **já mostra "Stored"/
"Armazenada" para uma credencial guardada e não verificada, nunca
"Failing"**. FR-025 e a metade de FR-042 sobre o chip **já estão corretas
hoje, sem mudança nenhuma** — só falta um teste que prove isso (parte de
T022), não uma implementação. O que genuinamente falta escrever: (1) uma
frase explícita afirmando "guardada no vault" (FR-035 pede mais que o chip
de uma palavra); (2) os três botões — Test again (chama `testNow`, já
existe, só falta o botão), Replace credential (`useState` novo,
`replacing`, que troca a vista de estado+ações pela `<CredentialField>` já
existente), Disconnect (`useState` novo, abre `ConfirmDestructive` — já
importável de `@/components/overlay`, ver `console/src/components/overlay.tsx:247-268`,
com `target`/`action`/`consequence`/`labels`, chamando a rota `DELETE` que
já existe e já está testada, acima). Nenhum destes três tem uma linha
escrita ainda. Nenhum arquivo de teste (`console/tests/unit/surfaces/integration-panel.test.tsx`)
existe — confirmado por `ls console/tests/unit/surfaces/ | grep -i panel`
(só existe `panel.test.tsx`, do componente genérico `Panel`, não
`IntegrationPanel`) — precisa ser criado do zero. Modelo de mock de
`fetch`/`useRouter` já identificado:
`console/tests/unit/surfaces/delivery-token.test.tsx` (`vi.stubGlobal('fetch',
answering(status, body))`, `vi.unstubAllGlobals()` no `afterEach`); o mock
global de `useRouter` já existe em `console/tests/unit/setup.ts:12-26`
(no-op, serve para tudo que não afirma para onde o router navegou).

### Gates não rodados nesta fatia — nomeados, não escondidos

- `uv run ruff check` / `ruff format --check` / `uv run mypy` sobre os três
  arquivos Python tocados (`recorder.py`, `integrations.py`,
  `onboarding_routes.py`) e o teste novo — **não rodado**.
- `uv run pytest tests/unit/gateway/http/` inteiro (o raio de alcance real
  de tocar `integrations.py`/`onboarding_routes.py`/`recorder.py`) — **não
  rodado**, só o arquivo novo isolado.
- `tests/security/test_impersonation_audit.py` — **não rodado** (análise de
  código só, ver acima).
- `make console-client` / `make console-client-check` — **não rodado**. Isto
  é um risco real e nomeado: a rota nova muda o documento OpenAPI
  (`fixtures/contract/openapi.json` via `tools.mockplane contract`) e o
  client gerado (`console/src/api/schema.ts`) não foi regenerado. Qualquer
  gate de contrato que compare os dois (o padrão que a fatia 2 já seguiu
  para `receiver_yaml`/`week_count`) está **desatualizado agora** e pode
  acusar divergência até alguém rodar a regeneração.
- `uv run python -m tools.console_gate typecheck/lint/format-check/test` —
  **não rodado nesta fatia** (os únicos arquivos de console tocados,
  `scroll-memory.ts` e `integration-panel.tsx`, mudaram; nenhum gate de
  console foi confirmado sobre eles além do rebuild + acceptance spec, que
  passam pelo `tsc`/bundler implicitamente mas não são o mesmo que
  `console_gate lint`/`typecheck` isolados).
- `make check-imports`, `check-protocols`, `check-deps`,
  `check-config-parity` — **não rodados**.
- `make verify` — não rodado, do orquestrador, por instrução geral da onda.

### Não tocado, deliberadamente

- A tela de intake (`alert-intake.tsx`), a cadeia, `schedules-destinations.tsx`,
  qualquer `screens.json`/baseline visual — fora do escopo desta fatia,
  como o despacho nomeou.
- `CredentialField`'s ausência de um botão "Cancel" ao lado de "Save and
  test" (FR-030 pede "com o cancelamento ao lado dela") — não é uma tarefa
  nomeada em nenhum número desta fase (`tasks.md` T017-T021, T022-T026 não
  mencionam "cancel"), o acceptance spec não afirma isso, e o componente já
  existia antes desta feature sem esse botão. Registrado como gap
  pré-existente, não meu para inventar sem uma tarefa que peça.

## Gates rodados nesta fatia (reais)

| Gate | Comando | Resultado |
|---|---|---|
| Diagnóstico de rolagem (descartável, apagado) | script Playwright próprio, ver T019 acima | Confirmou a causa; apagado depois, `git status` limpo |
| Acceptance spec completo, depois da correção de T019 | `uv run python -m tools.console_e2e run -- tests/e2e/050-integrations-slideover-intake.acceptance.spec.ts` | **8 failed, 16 passed** (era 9 failed, 15 passed) |
| Suite nova de DELETE, vermelho | `uv run pytest tests/unit/gateway/http/test_integration_credential_delete.py -q` (com os três arquivos revertidos) | **6 failed** — `405 Method Not Allowed` em todos, ver mensagens acima |
| Suite nova de DELETE, verde | mesmo comando, implementação restaurada | **6 passed** |
| `console_gate build` | `uv run python -m tools.console_gate build` | rodado duas vezes (antes e depois da correção de T019), ambas concluídas sem erro, listando todas as rotas incluindo `/integrations` e `/integrations/[name]` |
| Sweep de artefatos de depuração | `grep` por `.only(`/`.skip(`/`debugger;`/`console.log(` nos 6 arquivos tocados + busca por `_zzz*`/`*.scratch.*` sob `console/tests` | limpo — nenhuma ocorrência |
| `make verify`, `console_gate typecheck/lint/format-check/test`, `ruff`/`mypy` Python, `tests/security/`, `console-client-check` | não rodados | ver lista de pendentes acima, com a razão de cada um |

## Arquivos tocados nesta fatia

- `console/src/surfaces/scroll-memory.ts` (T019 — reescrito)
- `console/src/surfaces/integration-panel.tsx` (T019 — efeito de mount
  acrescentado; nada de T020-T026 ainda)
- `gateway/http/routes/integrations.py` (T024/T025, metade backend —
  `CredentialDeleteView` + `delete_credential`)
- `gateway/http/security/onboarding_routes.py` (T024/T025, metade backend —
  entrada de permissão)
- `platform/identity/audit/recorder.py` (T024/T025, metade backend —
  `CREDENTIAL_AUDIT_ACTION_DELETE`)
- `tests/unit/gateway/http/test_integration_credential_delete.py` (novo)

Nenhum arquivo de i18n (`en.ts`/`pt-BR.ts`), nenhum arquivo de teste de
console novo, e nenhuma baseline visual foram tocados — o trabalho de T020 em
diante fica inteiramente para a próxima entrada nesta fatia.

---

# Fatia 5b de nove — T020 a T026 (retomada do ledger de resgate)

Estado abaixo verificado contra o código nesta árvore, HEAD `81334aa` em
`feat/v6-scope-and-settings`, árvore limpa antes desta sessão (confirmado por
`git status --short`). **Esta sessão também foi interrompida pelo
orquestrador antes do fim planejado** — a instrução de parar chegou no meio
de um ciclo de quebra-e-restaura, com a quebra já confirmada vermelha mas a
restauração ainda não executada. A seção seguinte documenta essa
interrupção e a restauração, porque é a coisa mais urgente deste ledger.

## Interrupção e restauração — o mais urgente primeiro

**O que estava quebrado no momento da interrupção**: `console/src/design/status.ts`,
linha 147, dentro de `CREDENTIAL_STATUS_ALIASES` — a linha
`unknown: 'stored',` (o mapeamento canônico "credencial guardada e nunca
verificada → estado 'stored', nunca 'failing'") tinha sido trocada para
`unknown: 'failing',`, deliberadamente, para provar que o teste
`security: no credential value ever reaches the DOM or an outbound response >
shows a credential that is stored but never verified as stored, never as
failing` (`console/tests/unit/surfaces/integration-panel.test.tsx:609`) mede
alguma coisa de verdade. O vermelho foi observado e confirmado — mensagem
real:

```
AssertionError: expected 'failing' to be 'stored' // Object.is equality
Expected: "stored"
Received: "failing"
 ❯ tests/unit/surfaces/integration-panel.test.tsx:624:58
```

A mensagem do orquestrador chegou logo depois dessa confirmação, antes de o
arquivo ser restaurado. **Restaurado imediatamente ao retomar, antes de
qualquer outra ação**: `cp` do backup em scratchpad
(`.../scratchpad/backups/status.ts.orig`, uma cópia tirada *antes* da quebra,
quando o arquivo já estava confirmado limpo por `git diff`) de volta para
`console/src/design/status.ts`. Verificação real, rodada e lida:

```
git diff --stat -- console/src/design/status.ts   → (saída vazia)
git diff -- console/src/design/status.ts          → (saída vazia)
grep -n "unknown: 'stored'" console/src/design/status.ts → 147:  unknown: 'stored',
```

Byte-idêntico ao HEAD, confirmado por diff vazio, não por suposição.

### Varredura por outras sobras

Depois da restauração acima, antes de escrever qualquer coisa nova:

```
git status --short
```
→ exatamente os 9 arquivos que este ledger reivindica como mudança
intencional (lista completa na seção "Arquivos tocados" abaixo) — nenhum
arquivo extra, nenhum arquivo quebrado.

```
md5sum console/src/surfaces/integration-panel.tsx \
       console/src/surfaces/screens/integrations.tsx \
       console/src/app/api/credential/route.ts
```
→ bate exatamente com os checksums tirados no momento em que a implementação
final desses três arquivos foi salva em scratchpad
(`a111f90d…`/`211c80d6…`/`413a6f99…`), confirmando que os três estão na sua
versão final correta, não numa quebra intermediária.

```
git diff --stat -- console/src/surfaces/credential.tsx console/src/design/status.ts
```
→ saída vazia para os dois — os dois arquivos que sofreram quebra-e-restaura
nesta sessão (além do `integration-panel.tsx`, que nunca ficou fora de scratchpad
entre suas próprias quebras) estão de volta a exatamente o que o HEAD já
tinha, sem nenhuma mudança líquida.

```
grep -rn "\.only(\|\.skip(\|debugger;\|console\.log(" <os 7 arquivos tocados por esta fatia>
```
→ nenhuma ocorrência.

```
find console/tests -iname "*_zzz*" -o -iname "*.scratch.*" -o -iname "*.tmp.*"
```
→ nada.

**Nenhuma outra quebra ficou aberta.** Das seis alegações "já verdes no
primeiro rodar" que esta fatia quebrou-e-restaurou (ver seção própria
abaixo), cinco foram completadas de ponta a ponta (quebrada, vermelho
observado, restaurada, verificada) antes da interrupção; a sexta nunca foi
sequer iniciada — nada dela ficou quebrado, ela simplesmente não foi tentada.
Nomeada como pendente na seção "O que fica pendente" abaixo, não escondida.

## Escopo desta fatia

T020–T026 (o painel de credencial), continuando o ledger de resgate da fatia
5. Não toquei a tela de intake, a cadeia, `schedules-destinations`, nem
nenhuma baseline visual — exatamente como o despacho nomeou.

## Tabela — estado real de cada tarefa

| Tarefa | Estado | Detalhe |
|---|---|---|
| T020 — placeholder do endereço descoberto + instrução por campo | **FEITO** | `IntegrationPanelItem.discoveredAddress` (`console/src/surfaces/integration-panel.tsx:81`), computado em `console/src/surfaces/screens/integrations.tsx:480` a partir de `panelItem.suggested?.address ?? ''` — nunca de uma constante. Renderizado como frase (`labels.foundHere` + endereço) em `integration-panel.tsx:332-338`, só quando não-vazio. A "instrução por campo" (FR-027) já existia antes desta fatia (`describe()` em `credential.tsx`) — verificado por teste, não construído. Ver seção própria "A decisão do campo de endereço" abaixo. |
| T021 — deep-link ausente oferece voltar e ver o roadmap | **FEITO** | Dois links no ramo `item === null`: `panel-not-found-back` (`closeHref`, `integration-panel.tsx:279`) e `panel-not-found-roadmap` (`notCoveredHref`, `integration-panel.tsx:285-286`), prop nova `notCoveredHref` passada de `screens/integrations.tsx:428/484` (a mesma variável que o rodapé do catálogo já calculava). |
| T022 — teste de unidade: credencial guardada não mostra campo vazio nem ação desabilitada, afirma vault | **FEITO** | `console/tests/unit/surfaces/integration-panel.test.tsx:118-208` (describe `a connected integration...`) — 6 testes, todos vermelho→verde confirmados (ver seção de vermelhos). Implementação: `showForm`/`connected` em `integration-panel.tsx:261-263`, nota `credential-stored-note` em `:365-371`. |
| T023 — teste de unidade: três ações presentes e nomeadas; substituir revela o formulário | **FEITO** | `integration-panel.test.tsx:230-345` (describes `Test again` e `Replace credential`) — 5 testes, vermelho→verde confirmados. |
| T024 — implementar as três ações em `integration-panel.tsx` | **FEITO** | Os três botões (`test-again`/`replace-credential`/`disconnect-credential`, `integration-panel.tsx:372-402`), ramificando por `credentialStatus(item.health) !== 'not_connected'` (a função canônica que a fatia 0 já declarava, nunca um literal novo). |
| T025 — Disconnect exige confirmação nomeando a integração e o que será removido | **FEITO** | `ConfirmDestructive` (`integration-panel.tsx:453-464`) — `target={item.displayName}`, `consequence={labels.disconnectConsequence}`. Nenhuma confirmação nova escrita; reusa exatamente o componente que o despacho apontou. Rota `DELETE /v1/integrations/{name}/credential` já existia, comprometida por fatia anterior (backend intocado nesta fatia, só reverificado); o lado do console (`console/src/app/api/credential/route.ts:128-159`, handler `DELETE` novo) e a chamada em `integration-panel.tsx:221-249` (`disconnect()`) são desta fatia. |
| T026 — teste de segurança: nenhum valor de credencial após guardar/testar de novo; guardada-nunca-verificada mostra armazenada, nunca falhando | **FEITO** | `integration-panel.test.tsx:535-628` — 3 testes. Os dois de segurança **plantam deliberadamente o segredo na resposta simulada** (um campo que o componente não lê) para provar que o componente não o ecoa cegamente, não só que meu mock nunca continha o segredo — ver detalhe na seção de quebra-e-restaura. |

**Ressalva que corta os sete "FEITO" acima**: cada um tem implementação real
e prova vermelho→verde de teste que eu mesmo observei (ver próximas seções).
O que **nenhum** deles tem ainda é a passagem pela cadeia completa de gates
desta fatia (`console_gate typecheck/lint/format-check/test`) rodada **depois**
de os dois arquivos de teste existirem, nem uma rodada do acceptance spec
desta sessão — ver "O que fica pendente" para o que isso significa
concretamente.

## A decisão do campo de endereço — a pergunta que esta fatia existia para responder

**Conclusão**: o placeholder de FR-028/029 é implementável, e foi implementado,
**sem nenhuma mudança de schema de backend** — porque o mecanismo que ele
precisa já existe e já é geral, mesmo que nenhum formulário de credencial
tenha um campo de endereço.

Passos da investigação, cada um verificado por leitura direta, não por
suposição:

1. **Nenhum vendor declara um campo de endereço no próprio `CredentialSchema`.**
   Confirmado de novo, pontualmente, em `integrations/alertmanager/schema.py:32`:
   o único campo é `secret("token", "Bearer token accepted by whatever fronts
   Alertmanager", min_length=8)`. A alegação mais ampla (nenhum dos 15) já
   tinha sido investigada pela fatia anterior; não refiz a varredura completa,
   só confirmei o caso que o mockup próprio mostra.
2. **O mockup (`#m4`, `specs_v6/mockups/settings-v6.html:354-359`) desenha um
   campo "Base URL" com `http://10.20.20.37:9093` preenchido**, no slide-over
   do próprio Alertmanager — mas essa é a leitura *ilustrativa* do mockup, não
   um contrato de schema: o Alertmanager real, lido no passo 1, não declara
   esse campo. O mockup é normativo para hierarquia e vocabulário, não para a
   forma exata de cada input, e a instrução do despacho já avisa isso.
3. **`Input` (`console/src/components/form.tsx:11-14`) não tem prop
   `placeholder`, por desenho deliberado** — o comentário do próprio arquivo
   argumenta que um placeholder HTML desaparece assim que alguém digita,
   levando a pergunta junto. Confirma que a leitura literal de FR-028 (um
   atributo HTML `placeholder`) não é a leitura que o resto do sistema já
   pratica.
4. **Existe precedente idêntico, já commitado**: `first-run/integrations.tsx:118-125`
   já renderiza `{labels.foundHere} {offer.suggested.address}` como frase —
   não como atributo — com o rótulo `firstRun.integrations.foundHere` já
   traduzido nos dois idiomas. Não é uma decisão nova desta fatia; é a
   aplicação do mesmo padrão a um segundo lugar da tela.
5. **A fonte do endereço é `IntegrationView.suggested` (`SuggestionView`),
   populada por `_suggestions()`/`suggest_integrations()`
   (`gateway/http/routes/integrations.py:259-280`,
   `platform/estate/suggestions.py:77-114`) — e essa função roda sobre **todo**
   `entry` do catálogo, conectado ou não.** Lido diretamente: `offers` (o mapa
   de nome→porta-padrão que decide se um vendor pode ser sugerido) vem de
   `entries = catalogue(...)` sem filtrar por `configured`, e
   `list_integrations` atribui `suggested=SuggestionView(...) if entry.name in
   suggested else None` **para toda entrada**, sem checar `entry.health`. Ou
   seja: estruturalmente, uma integração já conectada **pode** carregar
   `suggested.address` também, se o estate encontrar um recurso cujo
   nome/label bate com o vendor — o mecanismo nunca foi exclusivo de itens não
   conectados.
6. **Verificado empiricamente que o fixture `populated` atual não exercita essa
   combinação** — nenhuma das 15 entradas reais tem `suggested` preenchido
   hoje (só a fictícia `metrics-store` tem); `alertmanager` (a conectada) e
   `grafana` (a não conectada, usada nos meus testes de fiação) confirmam essa
   leitura via inspeção direta do JSON do fixture. Isso não invalida o
   mecanismo — só significa que o caminho "conectada + endereço descoberto"
   não tem cobertura de fixture hoje; meus testes de unidade cobrem esse
   caminho diretamente, no componente, sem depender do fixture.

**Decisão implementada**: `IntegrationPanelItem.discoveredAddress: string`
(nunca `undefined` — vazio é o caso comum), lido de
`panelItem.suggested?.address ?? ''` em `screens/integrations.tsx:480`,
renderizado como a mesma frase do first-run
(`labels.foundHere` = `message(locale, 'firstRun.integrations.foundHere')`,
reaproveitando a chave existente, nenhuma string nova para isto) só quando
não-vazio, só no ramo onde o formulário write-only está visível (conectar
pela primeira vez, ou "Replace credential"). Nenhuma linha de schema Python
tocada; nenhum campo de endereço inventado em nenhum schema de vendor.

## Vermelho confirmado, T020-T026

Comando usado para cada rodada (nunca embrulhado em pipe, lido por texto, não
por código de saída):

```
cd console && npx vitest run --pool=forks tests/unit/surfaces/integration-panel.test.tsx
cd console && npx vitest run --pool=forks tests/unit/surfaces/integrations.test.tsx
```

**Sequência real, nesta ordem** (a implementação já estava escrita quando os
testes foram escritos — ver nota de honestidade abaixo — então a prova de
vermelho genuíno foi obtida *depois*, por reversão deliberada e temporária dos
três arquivos de implementação para o conteúdo exato do HEAD, seguida de
restauração, nunca por `git checkout`/`stash`/`restore`):

1. Backup em scratchpad dos três arquivos implementados
   (`integration-panel.tsx`, `screens/integrations.tsx`, `route.ts`), checksums
   anotados.
2. Os três revertidos para o conteúdo exato lido no início da sessão (colado
   de volta via `Write`, não `git checkout`) — confirmado por
   `git diff --stat` **vazio** contra HEAD nos três, depois da reversão.
3. Rodada contra o código original:

```
tests/unit/surfaces/integration-panel.test.tsx → 19 failed | 6 passed (25)
tests/unit/surfaces/integrations.test.tsx (arquivo inteiro)
                                          → 3 failed | 38 passed (41)
```

As 19 vermelhas de `integration-panel.test.tsx` (nomes completos, cada uma
falhando por `getElementError` — elemento/role/testid ausente, nunca um erro
de sintaxe ou de tipo):

- does not render an empty credential field paired with a disabled action…
- affirms the credential is stored in the vault
- offers Test again, Replace credential and Disconnect, named
- shows the actions view for a credential stored but never verified…
- shows the actions view for a failing credential too…
- asks the same verify courier the initial connection uses…
- shows the result as the canonical chip, with its diagnostic beside it
- reveals the identical write-only form, with Save and test as the only primary action…
- offers a way back without saving
- returns to the connected-actions view once the replacement is saved
- requires a confirmation naming the integration and what will be removed…
- sends the DELETE only once the confirmation is confirmed…
- shows the write-only form once disconnecting succeeds…
- leaves the credential exactly as it was, when the confirmation is cancelled
- names why, when the deployment refuses the disconnect
- says the deployment could not be reached, when the request never lands
- shows it as a sentence ahead of the fields, when the estate found one
- says it is not available, and offers both a way back and the roadmap list
- never carries a credential value into the DOM when re-testing an already-connected integration

Mensagem exemplo, capturada por inteiro (a última da lista, "Test again" não
existe no componente original):

```
tests/unit/surfaces/integration-panel.test.tsx:601:34
await userEvent.click(screen.getByRole('button', { name: /^Test ag…
  → element(s) not found
```

As 3 vermelhas de `integrations.test.tsx` (fiação ponta a ponta, através de
`IntegrationsScreen` de verdade, não só do componente isolado):

```
offers both a way back to the catalogue and the roadmap list, for a name that does not resolve
shows the estate's own discovered address as a placeholder sentence, read from the payload the estate actually served
shows the connected-actions view rather than an empty form, for a verified integration
```

4. Implementação restaurada dos backups de scratchpad — checksums conferidos
   idênticos aos anotados no passo 1 (`a111f90d…`/`211c80d6…`/`413a6f99…`).
5. Rodada de novo:

```
2 arquivos, 66 passed (66) — 0 failed
```

Todas as 22 alegações vermelhas (19+3) confirmadas verdes depois da
implementação, pela mesma suíte, sem seleção.

**Nota de honestidade sobre a ordem**: a implementação foi escrita antes dos
testes nesta fatia — a mesma inversão que a fatia 4 cometeu e que o despacho
avisou custar tempo real. Custou: a reversão-execução-restauração acima é o
preço de recuperar prova genuína depois do fato, e ela é genuína — o vermelho
foi observado contra o código original de verdade, não inferido — mas a
sequência correta (teste primeiro, vermelho, depois implementação) não foi
seguida desta vez.

## Quebra-e-restaura das alegações já verdes no primeiro rodar

Seis alegações em `integration-panel.test.tsx` passaram mesmo contra o código
**original** (antes de qualquer implementação) — vacuamente, na maioria dos
casos, porque a coisa que elas afirmam ausente já era ausente por um motivo
diferente do que a alegação testa. A regra da onda exige quebrar cada uma
antes de aceitá-la como prova. Cinco das seis foram completadas; a sexta
ficou pendente quando a sessão foi interrompida (nomeada, não escondida).

| # | Alegação | Arquivo quebrado | Quebra aplicada | Vermelho observado | Restaurado |
|---|---|---|---|---|---|
| 1 | "still shows the write-only form directly for an integration with nothing stored" | `integration-panel.tsx:261` | `const connected = item !== null && credentialStatus(...) !== 'not_connected' && !disconnected;` → `const connected = item !== null;` | `getByTestId('credential')` — elemento não encontrado (o formulário nunca aparece, forçado sempre para a vista conectada) | sim, checksum conferido `a111f90d…` |
| 2 | "renders no placeholder sentence at all when the estate knows nothing" | `integration-panel.tsx:332` | `{item.discoveredAddress === '' ? null : (...)}` → `{false ? null : (...)}` | `expected <p>Found in your estate at </p> to be null` | sim |
| 2b | (mesma quebra, alegação de fiação) "shows no placeholder sentence at all for an integration the estate never found" (telegram) | mesma quebra acima | mesma | mesma mensagem, via `integrations.test.tsx:879` | sim, junto com #2 |
| 3 | "carries each field's own instruction, not only its label" | `console/src/surfaces/credential.tsx`, `describe()` | corpo trocado para `return '';` | `getByText('Only if something fronts it.')` — elemento não encontrado | sim, `git diff` vazio conferido |
| 4 | "clears the field the instant a store succeeds, and echoes nothing back…" | `credential.tsx`, `store()` | linha `setValues({})` removida | `expected 'ninja_am_9f2b7c1e0d3a' to be ''` | sim, `git diff` vazio conferido |
| 5 | "shows a credential that is stored but never verified as stored, never as failing" | `console/src/design/status.ts:147` | `unknown: 'stored'` → `unknown: 'failing'` | `expected 'failing' to be 'stored'` | **sim, mas só depois da interrupção — ver seção "Interrupção e restauração" acima** |
| 6 | "shows no credential form and no actions, only the reason" (viewer sem permissão) | — | **nunca tentada** | — | não aplicável — nada foi quebrado |

Os dois testes de segurança (T026) merecem nota própria: a primeira versão
que escrevi verificava só o corpo da própria requisição de escrita (que
**legitimamente** carrega o segredo — é assim que uma credencial chega ao
vault) — uma asserção errada, que eu mesmo corrigi antes de rodar qualquer
vermelho/verde. A versão final planta o segredo **na resposta simulada**, num
campo que o componente não tem razão nenhuma para ler
(`{ ok: true, ..., token: secret }`), e afirma que o DOM inteiro nunca o
contém — provando que o componente não devolve cegamente o que a resposta
carrega, não só que o meu mock nunca continha o segredo. Essa correção
aconteceu antes de qualquer rodada vermelho/verde, então não é uma
quebra-e-restaura — é a mesma disciplina que a fatia 1 já registrou para dois
dos seus próprios testes ("a alegação estava testando só metade da
propriedade").

## Arquivos tocados nesta fatia

- `console/src/surfaces/integration-panel.tsx` — reescrito por completo
  (T020-T026): `discoveredAddress`, `notCoveredHref`, `showForm`/`connected`,
  as três ações, `disconnect()`, `ConfirmDestructive`.
- `console/src/surfaces/screens/integrations.tsx` — fiação dos novos props e
  labels para `<IntegrationPanel>` (linhas 428, 480, 484, 499-527).
- `console/src/app/api/credential/route.ts` — handler `DELETE` novo
  (linhas 63-66, 128-159), mesmo courier e mesma garantia que o `POST` já
  documentava (nunca guarda, nunca loga, nunca devolve um valor).
- `console/src/i18n/en.ts` / `pt-BR.ts` — 6 chaves novas cada
  (`catalogue.integrations.panel.{storedInVault,testAgain,replaceCredential,
  cancel,disconnect,disconnect.consequence}`), mesma edição, os dois idiomas
  juntos. Reaproveitadas sem chave nova: `firstRun.integrations.foundHere`
  (T020) e `catalogue.notCovered.title` (T021).
- `console/tests/unit/surfaces/integration-panel.test.tsx` — **novo**, 25
  testes, o componente isolado.
- `console/tests/unit/surfaces/integrations.test.tsx` — 4 testes novos
  acrescentados ao describe `the credential panel, opened by a deep link`
  (fiação ponta a ponta via `IntegrationsScreen`).
- `fixtures/contract/openapi.json` — regenerado
  (`uv run python -m tools.mockplane contract`), +76 linhas, só a rota
  `DELETE /v1/integrations/{name}/credential` e o schema `CredentialDeleteView`
  — `git diff` conferido, nada mais mudou.
- `console/src/api/schema.ts` — regenerado (`make console-client`), +61/-1
  linhas, mesmo escopo.

**Não tocado por esta fatia** (já existia, comprometido por uma fatia
anterior, só reverificado): `gateway/http/routes/integrations.py`,
`gateway/http/security/onboarding_routes.py`,
`platform/identity/audit/recorder.py`,
`tests/unit/gateway/http/test_integration_credential_delete.py` — os quatro
já estavam fora de `git status` no início desta sessão (árvore limpa, HEAD
`81334aa`), confirmando que o orquestrador já tinha commitado o trabalho de
backend da fatia 5 entre sessões.

## Gates rodados nesta fatia, com resultado real

| Gate | Comando | Resultado | Quando, em relação à implementação |
|---|---|---|---|
| Lint Python (3 arquivos backend + teste) | `uv run ruff check gateway/http/routes/integrations.py gateway/http/security/onboarding_routes.py platform/identity/audit/recorder.py tests/unit/gateway/http/test_integration_credential_delete.py` | limpo | antes de qualquer mudança desta fatia (reverificação) |
| Formatação Python | `uv run ruff format --check` (mesmos 4 arquivos) | já formatado | idem |
| Tipagem Python | `uv run mypy` (os 3 arquivos backend) | `Success: no issues found in 3 source files` | idem |
| Suíte `tests/unit/gateway/http/` inteira | `uv run pytest tests/unit/gateway/http/ -q` | **448 passed** | idem — prova que o raio de alcance de tocar `integrations.py`/`onboarding_routes.py`/`recorder.py` continua íntegro |
| Suíte de segurança | `uv run pytest tests/security/test_impersonation_audit.py -q` | **72 passed** | idem |
| Regeneração do documento OpenAPI | `uv run python -m tools.mockplane contract` | `wrote fixtures/contract/openapi.json`, diff conferido (+76, só a rota nova) | antes da implementação do console |
| Regeneração do client | `make console-client` | `openapi-typescript … → schema.ts`, diff conferido (+61/-1) | idem |
| `console-client-check` | `make console-client-check` | **passou, exit 0** (lido por texto e por código, os dois concordam aqui) | idem |
| Contrato de fixtures | `uv run pytest tests/contract/fixtures/ -q` | **108 passed** | idem |
| Contrato do console (harness completo) | `uv run pytest tests/contract/console -q` (background, ~7min) | **466 passed, 1 failed** — `test_console_visual_regression.py::test_the_untouched_baselines_still_match`, a mesma divergência de `machine-tokens-1440-light` já nomeada e não-minha desde a fatia 0 (efeito colateral do token de entrega). Nenhuma outra falha. | **rodado antes de o painel novo existir** — valida a regeneração do client/OpenAPI e o backend, não a implementação do painel desta fatia |
| `console_gate typecheck` | `uv run python -m tools.console_gate typecheck` | limpo (`tsc --noEmit`, sem saída) | depois da implementação do painel, **antes** dos dois arquivos de teste existirem |
| `console_gate lint` | `uv run python -m tools.console_gate lint` | limpo (`eslint . && node scripts/check-css-literals.mjs`) | idem |
| `console_gate format-check` | `uv run python -m tools.console_gate format-check` | **pegou algo** — `en.ts`, `pt-BR.ts`, `screens/integrations.tsx` — corrigido com `pnpm format` (prettier --write, escopo `console/`), `git diff --stat` conferido só esses 3 arquivos, `format-check` limpo depois | idem — o instrumento avisado no despacho, 6 de 6 fatias agora |
| `npx vitest run --pool=forks` nos dois arquivos de teste | ver seção "Vermelho confirmado" acima | 19+3 vermelhos → 66 verdes | depois de os testes existirem, ciclo completo vermelho→verde |

## O que fica pendente, nomeado, não escondido

**Os quatro gates que o próprio despacho desta fatia pediu por nome —
`console_gate typecheck`, `lint`, `format-check` e `test` — não foram
rodados de novo depois de os dois arquivos de teste passarem a existir.**
`typecheck`/`lint`/`format-check` só foram confirmados contra a árvore *sem*
`integration-panel.test.tsx` e sem as 4 adições a `integrations.test.tsx` —
não há razão para esperar que um arquivo de teste escrito seguindo os
padrões já existentes do repositório quebre `tsc`/`eslint`/`prettier`, mas
isso é uma expectativa, não uma medição, e não deve ser lido como uma. E
**`console_gate test` (o gate real, com os limiares de cobertura) nunca
rodou nesta sessão** — só `npx vitest run --pool=forks`, que o próprio
despacho já avisa não ser equivalente. Isto é o primeiro item que quem
retomar esta fatia — ou o orquestrador — precisa fechar antes de dar a fatia
por encerrada.

**O acceptance spec (`tools.console_e2e run --
tests/e2e/050-integrations-slideover-intake.acceptance.spec.ts`) nunca rodou
nesta sessão.** O número herdado do ledger da fatia 5 ("8 failed, 16
passed", com `:440` e `:466` nomeadas como minhas) **não foi reverificado por
mim**. A evidência desta fatia — os 66 testes de unidade vermelho→verde,
cobrindo exatamente as duas alegações que `:440`/`:466` descrevem (campo
vazio com ação desabilitada ausente; as três ações nomeadas presentes) — é
forte indício de que as duas viram verdes, mas indício não é a mesma coisa
que ter rodado o navegador de verdade e lido a saída. Reportar "8 failed → 6
failed" aqui seria inferir, não medir — exatamos o erro que o despacho pede
para não cometer.

**Quebra-e-restaura pendente, uma alegação**: "shows no credential form and
no actions, only the reason" (`integration-panel.test.tsx:630`, viewer sem
`integration.manage`) passou no primeiro rodar contra o código original e
nunca foi quebrada para prova. A leitura de código sustenta que ela mede algo
real (o ramo `writable ? (...) : (<p data-testid="credential-read-only">)`
em `integration-panel.tsx` é estrutualmente idêntico ao que já existia antes
desta fatia, só realocado), mas "a leitura de código sustenta" não é a mesma
prova que as outras cinco receberam.

**Não tocado, deliberadamente, com a razão** (itens que já eram gaps
conhecidos, herdados, e que nenhuma tarefa de T020-T026 pede para fechar):

- `CredentialField` continua sem um botão "Cancel" ao lado de "Save and
  test" **na conexão original** (FR-030) — a fatia 5 já registrou isso como
  gap pré-existente, sem tarefa nomeada. Esta fatia adicionou um "Cancel"
  **só** para a própria alternância nova "Replace credential"
  (`data-testid="cancel-replace"`, `integration-panel.tsx`) — não tocou o
  formulário de primeira conexão, que continua sem essa saída.
- O texto em voo do botão "Test again" reaproveita `labels.testing` ("Saving
  and testing…") — uma frase pensada para o fluxo de salvar, levemente
  imprecisa para um reteste que não salva nada. Decisão consciente de não
  criar uma terceira string só para essa nuance, já que nenhuma tarefa ou
  alegação do acceptance spec pede um texto distinto aqui.
- `ConfirmDestructive`, usado dentro do `Drawer` `floating` do painel, herda
  o comportamento não-`floating` que **todo** outro consumidor do componente
  no repositório já tem — ele renderiza como bloco dentro do próprio drawer
  fixo, não como um modal centralizado sobre a tela inteira. Funcionalmente
  correto (a confirmação ainda bloqueia a escrita até ser confirmada), mas é
  uma nuance visual que quem revisar a baseline de `/integrations/<vendor>`
  na fatia 8 deve notar — não é meu para redesenhar sem uma tarefa que peça.
- Pela mesma razão, o Escape fechar os dois overlays ao mesmo tempo (o
  `Drawer` externo e o `Modal` de confirmação, cada um com seu próprio
  listener de teclado independente) não foi investigado a fundo nem
  corrigido — comportamento compartilhado por toda a biblioteca, fora do
  escopo desta fatia.
- Tela de intake, cadeia, `schedules-destinations`, baselines visuais — fora
  do escopo desta fatia, como o despacho nomeou (fatias 6, 7 e 8).
- `make check-imports`, `check-protocols`, `check-deps`,
  `check-config-parity`, `make verify` — não rodados, do orquestrador ou de
  T048, por instrução da onda.

## Descoberta que muda como ler este ledger daqui em diante

O mecanismo de "endereço descoberto" (`suggested.address`) é estruturalmente
disponível para **qualquer** integração, conectada ou não — não é exclusivo
do caminho "ainda não conectada" que a leitura ingênua da spec sugeriria.
Nenhum fixture hoje exercita "conectada + endereço descoberto" ao mesmo
tempo; se uma fatia futura precisar cobrir esse caso via Playwright (não só
via teste de unidade, como esta fatia fez), vai precisar de uma mudança de
fixture — o mecanismo do lado do console já suporta, o dado é que falta.

# Fatia 6 de nove — T027 a T035, T042

**Estado geral: interrompida pelo orquestrador antes do passo que mediria a
alegação central (`:535`) e antes de rodar o acceptance spec inteiro.** O
código, os testes de unidade e os gates baratos (typecheck/lint/format-check)
foram completados e verificados nesta sessão; a medição real em navegador e
`console_gate test` (com limiares de cobertura) não rodaram. Cada seção abaixo
diz exatamente o que foi visto, e o que não foi.

## Confirmação de que nada ficou aberto

Uma única quebra-e-restaura foi aberta nesta fatia (`CopyAction`, ver seção
própria) e foi **fechada e verificada antes da interrupção**: checksum
conferido idêntico ao estado pré-quebra
(`40343f99c12831bcfa5410e07800a615`, os dois lados), e a suíte
`data-copy.test.tsx` rodada de novo depois da restauração — 7 passed. Nenhuma
outra quebra deliberada foi aberta nesta sessão. `git status --short`, checado
no momento desta escrita, mostra exatamente os onze arquivos que este ledger
reivindica como mudança intencional (lista completa em "Arquivos tocados"
abaixo) — nenhum arquivo extra, nenhum arquivo a meio de uma quebra.

```
 M console/src/i18n/en.ts
 M console/src/i18n/pt-BR.ts
 M console/src/surfaces/screens/data-copy.tsx
 M console/src/surfaces/settings/alert-intake.tsx
 M console/tests/unit/surfaces/data-copy.test.tsx
 M console/tests/unit/surfaces/settings-alert-intake.test.tsx
 M fixtures/scenarios/empty/ingress-sources.json
 M fixtures/scenarios/first-run/ingress-sources.json
 M fixtures/scenarios/populated/ingress-sources.json
 M fixtures/scenarios/populated/transit-ingress.json
 M tools/mockplane/dataset/served.py
```

## Escopo desta fatia

T027–T035 (a tela de intake: três fontes, chips, volume da semana, URL, YAML
do receiver, linha de confiança) e T042 (rodapé de fontes retiradas). Não
toquei a cadeia (`chain-node`, T036–T040), `schedules-destinations.tsx`, o
catálogo, o painel de credencial, nem nenhuma baseline visual — exatamente
como o despacho nomeou. T030 tem uma ressalva própria abaixo: o teste que a
tarefa pede já existe no acceptance spec (herdado de uma fatia anterior), e eu
não o reexecutei.

## Tabela — estado real de cada tarefa

| Tarefa | Estado | Detalhe |
|---|---|---|
| T027 — teste de unidade, falhando primeiro | **FEITO** | `console/tests/unit/surfaces/settings-alert-intake.test.tsx:251-297` (describe "the Receiving chip, the week volume, and the compact silent row", 4 testes) + `:299-364` (describe "a silent source with a recent rejection", FR-065). Vermelho genuíno observado contra o código original (ver seção própria), depois verde. |
| T028 — reescrever a lista de fontes, strings novas | **FEITO** | `console/src/surfaces/settings/alert-intake.tsx:486-565` — chip "Receiving" (`:499`) separado do chip "Ready — nothing arrived yet" (`:494`, mesma `data-testid="never-delivered"` de antes, só o texto mudou), volume da semana (`:512-514`). Strings em `console/src/i18n/en.ts:176-197` e `pt-BR.ts` (mesmas chaves, linhas equivalentes). |
| T029 — Format & test recolhido por padrão, rejeições continuam visíveis | **FEITO** | Rejeições renderizadas incondicionalmente, **fora** do ramo `silent ?`, em `alert-intake.tsx:516-531` — não dependem de nada estar expandido. Format & test permanece `Reference` (já fechado por padrão desde antes desta fatia); para uma fonte calada, o endpoint entra **dentro** do `Reference` em vez de ficar solto (`:533-568`) — decisão explicada na seção "A correção de rota que o próprio jsdom obrigou" abaixo. |
| T030 — teste de orçamento de rolagem | **PARCIAL, não verificado por mim** | O teste já existe — `console/tests/e2e/050-integrations-slideover-intake.acceptance.spec.ts:577` ("the whole screen fits within 2 viewports"), escrito por uma fatia anterior (T004), e o despacho já contava esse teste como um dos 18 verdes antes de eu começar. Eu **não rodei o acceptance spec nesta sessão** (ver "A medição pedida" abaixo), então não posso afirmar que ele continua verde depois das minhas mudanças — só que nada no meu raciocínio estrutural aponta para um crescimento de altura (o volume da semana some da linha do `last-delivery`; a fonte calada ficou mais compacta, não mais alta). Inferência, não medição. |
| T031 — teste, falhando primeiro (URL + YAML) | **FEITO** | `settings-alert-intake.test.tsx:502-511` (rótulo "Copy URL") e `:513-586` (describe "the Alertmanager receiver YAML", 3 testes). Vermelho genuíno observado, depois verde. |
| T032 — URL por fonte + Copy Alertmanager receiver YAML, sem concatenar | **FEITO** | `alert-intake.tsx:349-393` — `receiverYaml = text(pasteRow, 'receiver_yaml')`, lido puro do payload de `/v1/ingress/sources`; `CopyAction` (`console/src/surfaces/screens/data-copy.tsx:59-91`, novo) copia essa string exata, nenhuma concatenação na tela. **Exigiu trabalho de fixture** não previsto no despacho como pendente: o gerador `receiver_yaml()` já existia (fatia 2), mas a fixture estática `fixtures/scenarios/populated/ingress-sources.json` nunca carregava o campo — ver seção "O que descobri sobre a fixture" abaixo. |
| T033 — linha de confiança sem permissão crua, com rotação | **FEITO (já existia, verificado por leitura — não por quebra-e-restaura)** | Confirmado presente em `alert-intake.tsx:610-650` (a mesma faixa que o despacho apontou, deslocada por esta fatia ter inserido código acima): `ingress.delivery.authenticated`, `data-testid="delivery-token-name"`, botão "Rotate"/"Issue a delivery token". Testes pré-existentes de uma fatia anterior (`describe('the delivery token control', ...)`, `settings-alert-intake.test.tsx:611-694`) continuam passando (47/47 no arquivo). **O que o despacho pediu e eu não fiz**: quebrar deliberadamente esse trecho, observar o teste cair, restaurar. Não fiz — fica nomeado em "O que fica pendente" abaixo, não escondido. |
| T034 — rotação leva a Machine tokens filtrada; sem token, oferece emitir | **NÃO VERIFICADO POR MIM NESTA SESSÃO** | A metade "sem token → oferece emitir" tem teste pré-existente e passando (`:627-640`, `:665-676`). A metade "rotacionar navega para Machine tokens filtrada para entrega" — o "teste do destino do CTA" que a tarefa pede por nome — **eu não localizei nem escrevi**. Não investiguei se esse teste já existe em outro arquivo (`machine-tokens.test.tsx`, talvez) porque a interrupção chegou antes. Estado real: desconhecido, não characterizado. |
| T035 — teste de segurança do bloco copiado | **PARCIAL** | `settings-alert-intake.test.tsx:530-552` prova que o conteúdo copiado contém o marcador (`'paste the value of delivery token'`) e não uma string de segredo — mas é uma prova estrutural herdada do gerador (`alertmanager.receiver_yaml()` não tem parâmetro por onde um segredo passaria — já provado por `tests/contract/console/test_ingress_receiver_yaml_contract.py`, que roda e passa, mas que eu não escrevi nesta fatia). Não escrevi um teste que planta deliberadamente um segredo em algum lugar do payload do console e prova que ele não vaza para o clipboard — o padrão que a fatia 5 já registrou para os testes de credencial (`integration-panel.test.tsx:535-628`) e que esta tarefa pede por analogia. Cobertura real, mas mais estreita do que a tarefa pede. |
| T042 — rodapé nomeando fontes retiradas | **FEITO** | `alert-intake.tsx:616-618` (`data-testid="ingress-retired"`), strings `data.ingress.retired` em `en.ts`/`pt-BR.ts`. Teste: `settings-alert-intake.test.tsx:757-767`. Texto estático (não derivado de payload) — decisão registrada na seção própria abaixo, porque a spec não exige derivação para este rodapé especificamente (diferente do rodapé do catálogo, FR-016) e não existe hoje nenhum endpoint que liste "fontes de intake retiradas" como um dado servido. |

## O vermelho confirmado, com as mensagens reais

Comando usado, sempre por texto, nunca por código de saída embrulhado em
pipe: `cd console && npx vitest run --pool=forks tests/unit/surfaces/settings-alert-intake.test.tsx`.

**Primeira rodada, contra o `alert-intake.tsx` ainda não tocado por esta
fatia** (só a fixture já tinha sido regenerada, o que não muda nada do lado
do componente): **9 failed, 38 passed**. As nove, por nome, cada uma com o
motivo real:

1. `a source that has never delivered > says so, rather than showing an empty row` — `expect(silent).toHaveTextContent('Ready — nothing arrived yet')` contra um componente que ainda dizia `'Nothing has ever arrived here'`.
2. `the Receiving chip... > carries the exact "Receiving" chip, distinct from the silent "Ready" one` — `getElementError`, `getByText('Receiving', {exact:true})` não encontrou nada.
3. `...> states the week volume beside the last delivery` — `toHaveTextContent('14 this week')` falhou; a linha `last-delivery` ainda não carregava o volume.
4. `...> keeps the endpoint and the disclosure closed for a silent source, reachable one press away` — `getByTestId('reference')`/`'silent-detail'` não existia ainda dentro da linha calada.
5. `a silent source with a recent rejection > still shows the rejection...` — caiu na mesma asserção do chip "Ready — nothing arrived yet" (item 1), antes mesmo de chegar à parte de rejeições.
6. `a webhook address safe to announce > names the action "Copy URL", not the raw-payload label it borrowed` — `toHaveTextContent('Copy URL')` falhou; o botão dizia `'Copy the raw payload'` (bug pré-existente, confirmado por leitura direta do código antes de escrever o teste — `alert-intake.tsx` usava `message(locale, 'surface.payload.copy')`, a chave errada, importada de um contexto de payload bruto que nada tem a ver com esta linha).
7. `the Alertmanager receiver YAML > offers "Copy Alertmanager receiver YAML" only on the Alertmanager row` — `getElementError`, o botão não existia.
8. `...> copies exactly the block the gateway served...` — mesma causa, botão ausente.
9. `the retired intake sources > names what moved to the roadmap, and why` — `getElementError`, `getByTestId('ingress-retired')` não existia.

Depois da implementação completa (T028/T029/T032/T033-reaproveitado/T042):
**47 passed, 0 failed**, mesmo arquivo, mesma suíte, sem seleção.

## Quebra-e-restaura — `CopyAction`

A única desta fatia, e completa. A implementação (`data-copy.tsx:59-91`) foi
escrita antes do teste — mesma inversão que outras fatias já registraram.
Sequência real:

1. Backup em scratchpad de `data-copy.tsx` já com `CopyAction` implementado; `md5sum` = `40343f99c12831bcfa5410e07800a615`.
2. Escrevi os três testes em `data-copy.test.tsx` (`describe('a copy action with nothing displayed', ...)`).
3. Removi o bloco `CopyAction` do arquivo (substituído por um comentário), deixando só `CopyValue`.
4. Rodei `npx vitest run --pool=forks tests/unit/surfaces/data-copy.test.tsx` → **3 failed, 4 passed**. Mensagem real: `Error: Element type is invalid: expected a string ... but got: undefined. You likely forgot to export your component...` — a importação `CopyAction` resolvendo para `undefined`, erro genuíno de componente ausente, não um erro de asserção cosmético.
5. Restaurei o arquivo do backup do scratchpad. `md5sum` depois da restauração: idêntico ao do passo 1.
6. Rodei de novo: **7 passed, 0 failed**.

## Quebra-e-restaura que o despacho pediu e **não foi feita** — T033/T034

O despacho, textualmente: *"Confirme lendo, depois trate-as como
caracterizações — quebre a fonte, observe a asserção falhar, restaure,
registre."*, sobre a linha de confiança do delivery token (T033) e a maior
parte de T034. Eu li o código e confirmei que ele existe e faz o que a
spec pede (`alert-intake.tsx:610-650`), e confirmei que os testes
pré-existentes que o exercitam continuam passando dentro da suíte completa —
mas **nunca quebrei deliberadamente esse trecho para observar o próprio
teste cair**. A diferença é real: "os testes passam hoje" e "eu vi esses
testes especificamente falharem quando a coisa que eles protegem foi
quebrada" são provas de força diferente, e só a segunda é a que esta onda
pede. Isto fica pendente, nomeado, não escondido — quem retomar esta fatia
faz exatamente os passos 1–6 acima, mas em `alert-intake.tsx:610-650` (por
exemplo, trocar `ingress.delivery.authenticated` por um literal e ver
`the delivery token control > names the delivery token once one has
actually authenticated deliveries with it` cair).

## A correção de rota que o próprio jsdom obrigou (relevante para quem ler o código)

O primeiro desenho desta fatia para a linha calada usava um `<details>`
nativo (`data-testid="silent-detail"`) para agrupar endpoint + formato/teste,
deixando `Provenance` de fora. Ao rodar o teste pré-existente `the receiver
list, compact by default > shows a name, an activity chip and a copyable
endpoint per receiver, with nothing expanded` (que verifica
`screen.queryByTestId('rule-simulator')).toBeNull()` **na página inteira**,
ele quebrou: um `<details>` sem o atributo `open` esconde o conteúdo
**visualmente**, num navegador de verdade, mas **não o remove do DOM** — e
`queryByTestId` enxerga o DOM, não o CSS computado. O `RuleSimulator` da
fonte calada (`generic`, desenhada primeiro) aparecia inteiro na consulta
global.

`Reference` (o componente que a tela já usa) não tem esse problema porque é
um componente cliente com `useState`: fechado, ele literalmente não renderiza
os filhos (`{expanded ? (<div data-testid="reference-body">{children}</div>) : null}`)
— fechado significa ausente do documento, não só escondido pelo navegador.
A correção foi reutilizar `Reference` também para a linha calada, só movendo
o endpoint para **dentro** dos seus filhos em vez de deixá-lo solto antes
dele (`alert-intake.tsx:533-568`). Isso resolveu o teste pré-existente e é a
razão de eu não ter uma `data-testid="silent-detail"` no código final — a
tela tem só `Reference`, em todo lugar, exatamente como antes desta fatia.

**Consequência para a medição pendente (`:535`)**: como os dois ramos agora
usam o mesmo componente `Reference` (mesmo botão fechado, mesma altura de
~60px estimada para título+resumo empilhados), a diferença de altura entre
uma linha calada e uma recebendo passou a depender inteiramente de **o que
fica fora do `Reference`**: a linha calada não tem nada fora dele além do
nome/chip e do `Provenance` fechado; a linha recebendo tem, além disso, o
bloco de endpoint+URL+botões (CopyValue, e agora também o botão de YAML só no
Alertmanager) sempre visível. Eu **acredito** que essa diferença estrutural
é suficiente para "bem abaixo da metade", mas — ver próxima seção — isso é
uma leitura de código, não uma medição, e é exatamente o tipo de coisa que já
foi contado errado nesta onda antes.

## A medição pedida — `:535`, antes e depois

**Antes**: 179.15625px para as duas linhas (número do despacho, não
remedido por mim).

**Depois: não medido.** Eu não rodei o acceptance spec Playwright nesta
sessão — a interrupção chegou enquanto eu ainda localizava o comando exato
(`tools/console_e2e.py`, que existe e tem um subcomando `run`, mas eu não
cheguei a executá-lo nem uma vez). `jsdom` (o motor por trás dos meus 47
testes de unidade) não implementa layout — `getBoundingClientRect()` nele
sempre devolve zeros — então não existe um número real que eu possa
reportar a partir da suíte vitest, nem aproximado. A única coisa que tenho é
a leitura estrutural da seção anterior, que é uma previsão, não uma
evidência, e é relatada como tal: **eu não sei se `:535` passa agora.** Pode
muito bem não passar — o `Reference` fechado, sozinho, pode já valer mais da
metade da altura da linha recebendo, e eu não tenho como saber sem medir.

## FR-065 — a fonte calada com rejeição recente

**Sim, verificado — por leitura de código e por teste.** As rejeições
(`alert-intake.tsx:516-531`, bloco `{rejections.length === 0 ? null : (<ul
data-testid="rejections">...)}`) estão **fora** do `{silent ? (...) :
(...)}` que decide o resto da linha (`:533` em diante) — são o mesmo bloco,
na mesma posição, para as duas fontes, e nunca dependem de `silent` nem de
nada estar expandido. Uma fonte com `never_delivered=true` e
`recent_rejections` não vazio mostraria as duas coisas ao mesmo tempo: o chip
"Ready — nothing arrived yet" (porque `silent` é verdadeiro) **e** a lista de
rejeições logo abaixo (porque `rejections.length > 0`), sem que uma apague a
outra.

Testado diretamente: `settings-alert-intake.test.tsx:299-364`, cenário
sintético (`serveSilentSourceWithARejection`, override de
`/v1/transit/ingress` que planta `never_delivered: true` **e**
`recent_rejections` não vazio na fonte `generic` — combinação que a fixture
real não produz hoje, porque `generic` nunca recebeu nada de nenhum tipo, e
que existe só para testar esta propriedade isoladamente). O teste
`still shows the rejection, without the row reading as though nothing
arrived` afirma as duas coisas juntas e **passou** na última rodada (47/47,
sem seleção). Nota honesta: o cenário real do fixture `populated` não
exercita essa combinação — `grafana` (a única fonte com rejeições) tem
`never_delivered: false`, então a propriedade só é provada pelo cenário
sintético do teste, não pelo Playwright contra o fixture committed.

## O que descobri sobre a fixture — trabalho não previsto no despacho

`fixtures/scenarios/populated/ingress-sources.json` (o que
`/v1/ingress/sources` devolve, servido estaticamente pelo mockplane, não
computado ao vivo) **nunca carregava `receiver_yaml`**, mesmo depois de a
fatia 2 ter dado ao `IngressSourceView` esse campo e à rota
`gateway/http/routes/ingress.py` a lógica para preenchê-lo. O gerador da
fatia 2 (`alertmanager.receiver_yaml()`) só é chamado pela rota de verdade,
que o `behaviour`/`vitest` não corre — os dois leem o JSON estático. Sem essa
correção, T032 não tinha o que consumir: o botão existiria, mas copiaria uma
string vazia.

**A correção não foi editar o JSON à mão.** `fixtures/scenarios/populated/`
é regenerado por `tools/mockplane/dataset/served.py` via
`python -m tools.mockplane build`, e um teste committed
(`tests/contract/fixtures/test_dataset_coherence.py::test_rebuilding_the_dataset_reproduces_what_is_committed`)
falha se o comprometido não bater byte a byte com o que o gerador produz.
Editei `served.py`:

- `ingress_records()` (`served.py:2215-2249`) ganhou um parâmetro
  `delivery_token_name: str = ""`, e só gera `receiver_yaml` para
  `alertmanager` quando esse nome não é vazio — espelhando a mesma regra da
  rota real (`gateway/http/routes/ingress.py`'s `if name ==
  _RECEIVER_YAML_SOURCE and token_name`). O default vazio importa: o cenário
  `empty`/`first-run` não tem nenhum delivery token (`tokens: []`,
  `build.py:267`), e gerar um `receiver_yaml` nomeando um token que não
  existe nesses cenários seria exatamente o tipo de "fixture concordando com
  o código e discordando do backend" que esta onda já nomeou como defeito
  recorrente. Só o chamador de `served_records()` (usado por
  populated/restricted/incident-live/audit-flooded, todos com o mesmo token
  `tok-0003 "Alert delivery"`) passa o nome (`served.py:3075`); a chamada
  direta em `empty_records()` (`build.py:315`) usa o default vazio.
- `transit_records()`'s `source_row()` (`served.py:2348-2383`) ganhou
  `week_count`, ausente antes (o campo existe no modelo Pydantic desde a
  fatia 2, mas nada preenchia um valor real — teria renderizado "0 this
  week" para uma fonte com 16 entregas reais, uma inconsistência visível).
  Valores escolhidos: 14 para `alertmanager` (o número que o próprio mockup
  desenha, `specs_v6/mockups/settings-v6.html` — "14 this week"), 6 para
  `grafana` (igual ao total de rejeições que já existe).
- Rodei `uv run python -m tools.mockplane build` (sem `--scenario`,
  reconstruindo os 6 `BUILT_SCENARIOS`) → `wrote 227 files across 6
  scenarios`, e o diff resultante tocou exatamente os 4 arquivos JSON
  listados em "Confirmação de que nada ficou aberto" acima — nada a mais.
- Rodei `uv run pytest tests/contract/fixtures/test_dataset_coherence.py
  tests/contract/fixtures/test_dataset_contract.py
  tests/contract/console/test_ingress_receiver_yaml_contract.py -q` →
  **56 passed**, incluindo o teste de reprodutibilidade byte a byte citado
  acima.
- `uv run ruff check`, `uv run ruff format --check` e `uv run mypy` em
  `tools/mockplane/dataset/served.py` → limpos os três.

## Gates rodados nesta fatia, com resultado real

| Gate | Comando | Resultado |
|---|---|---|
| Contrato de fixtures + receiver YAML | `uv run pytest tests/contract/fixtures/test_dataset_coherence.py tests/contract/fixtures/test_dataset_contract.py tests/contract/console/test_ingress_receiver_yaml_contract.py -q` | **56 passed** |
| Lint/format/tipo (só `served.py`) | `ruff check` / `ruff format --check` / `mypy` | limpos os três |
| `console_gate typecheck` | `uv run python -m tools.console_gate typecheck` | limpo (`tsc --noEmit`, sem saída) |
| `console_gate lint` | `uv run python -m tools.console_gate lint` | limpo (`eslint . && node scripts/check-css-literals.mjs`) |
| `console_gate format-check` | `uv run python -m tools.console_gate format-check` | **pegou algo na primeira rodada** — só `data-copy.tsx` — corrigido com `pnpm format` (prettier --write, escopo `console/`), confirmado que só o arquivo já modificado mudou (`git status --short console/` antes/depois idêntico em arquivos, `git diff --stat` mostrando só esse arquivo). Segunda rodada: limpo. O instrumento avisado no despacho, mais uma vez. |
| `npx vitest run --pool=forks` (arquivo único) | `tests/unit/surfaces/settings-alert-intake.test.tsx` | 9 vermelhos → **47 passed** |
| `npx vitest run --pool=forks` (arquivo único) | `tests/unit/surfaces/data-copy.test.tsx` | 3 vermelhos (quebra deliberada) → **7 passed** (restaurado) |
| `npx vitest run --pool=forks` (suíte inteira) | sem argumento de arquivo | **148 arquivos, 2552 testes, todos passed** — não é `console_gate test` (sem limiares de cobertura) e o próprio despacho avisa que os dois não são equivalentes |

**Não rodados nesta sessão, por instrução direta do orquestrador na
interrupção** (que pediu explicitamente para eu não gastar mais turnos
nisso, porque ele mesmo rodaria):

- `console_gate test` — o gate real, com os limiares de cobertura (o
  despacho avisa que a cobertura de branch está em 90.1% contra um piso de
  90%, e esta fatia adiciona branches novos — `silent ? ... : ...` em três
  lugares novos, `receiverYaml === '' ? ...`, etc. Não sei se o piso
  segura.).
- `console_gate format-check`/`lint`/`typecheck` **de novo, depois da última
  mudança** — a última coisa que toquei antes da interrupção foi a escrita
  deste ledger, que não muda nenhum arquivo de código; os três já estavam
  limpos na última vez que rodei, mas essa é uma leitura, não uma
  reconfirmação — o orquestrador disse que rodaria os quatro ele mesmo.
- O acceptance spec Playwright inteiro
  (`050-integrations-slideover-intake.acceptance.spec.ts`) — nunca rodou
  nesta sessão. Os números "6 failed / 18 passed" do despacho **não foram
  reverificados por mim**. Toda a evidência desta fatia sobre `:495`, `:515`
  e `:599` vem de testes de unidade que espelham deliberadamente as mesmas
  alegações (mesmas palavras exatas, mesma fonte, mesmo payload), não de
  rodar o navegador de verdade — e `:535` especificamente **não tem
  substituto de unidade possível**, como a seção de medição acima explica.

## O que fica pendente, nomeado, não escondido

1. **`:535` nunca foi medido.** É o item mais importante desta lista — a
   alegação central desta fatia não tem prova real, só uma leitura de
   código de que a estrutura mudou na direção certa. Quem retomar precisa
   rodar o Playwright e ler o número antes de declarar isto feito.
2. **O acceptance spec inteiro nunca rodou nesta sessão** — nem para
   confirmar `:495`/`:515`/`:599` verdes, nem para confirmar que os 18 que já
   passavam continuam passando (nada nesta fatia deveria tê-los quebrado —
   não toquei catálogo, painel, cadeia ou `schedules-destinations` — mas
   "não deveria" não é a mesma coisa que "foi visto").
3. **T033/T034 — quebra-e-restaura pedida pelo despacho, não feita.** Ver
   seção própria acima; os passos exatos para quem retomar estão descritos
   ali.
4. **T034 — o teste do destino do CTA de rotação ("leva a Machine tokens já
   filtrada") não foi localizado nem escrito.** Estado real desconhecido.
5. **T035 — cobertura mais estreita do que a tarefa pede.** Nenhum teste
   planta deliberadamente um segredo em algum lugar do payload do console
   para provar que ele não alcança o clipboard copiado — a prova atual é
   estrutural (o gerador não tem por onde um segredo passar), herdada de um
   teste de contrato de uma fatia anterior.
6. **`console_gate test` (cobertura) nunca rodou** — o piso de 90% de branch
   e os branches novos desta fatia nunca se encontraram.
7. **Fora do escopo desta fatia, como o despacho nomeou**: a cadeia
   (T036–T040), `schedules-destinations.tsx`, o catálogo, o painel de
   credencial, as baselines visuais. Nada disso foi tocado.

## `tasks.md` — o que foi marcado

Marquei **apenas** T027, T028, T029, T031, T032 e T042 — as seis tarefas com
implementação real e vermelho→verde observado por mim, na tabela acima. T030
fica **sem marcar** (o teste existe mas eu não o reexecutei). T033 fica **sem
marcar** apesar de a funcionalidade já existir, porque a tarefa, lida ao pé
da letra, é sobre confirmar por quebra-e-restaura, e essa confirmação não
aconteceu. T034 e T035 ficam sem marcar pelas razões já nomeadas.

---

# Fatia 6b de nove — T030, T033, T034, T035, e a alegação `:535`

Estado abaixo verificado contra o código nesta árvore, HEAD `b18dcf1` em
`feat/v6-scope-and-settings`, árvore limpa antes desta sessão (confirmado por
`git status --short`). **Escopo exatamente o que o despacho nomeou**: as
quatro tarefas que a fatia 6 deixou sem marcar, mais a alegação `:535` que a
fatia 6 moveu sem fechar. Não toquei a cadeia (T036-T040) nem
`schedules-destinations.tsx` — os dois vermelhos que sobram são da fatia 7,
confirmados abaixo, não investigados.

**Interrompida pelo orquestrador logo depois do `console_gate format-check`
— antes de `console_gate test` (cobertura) e antes de qualquer gate Python.**
Os quatro itens de implementação e seus testes estavam completos e
verificados por mim mesma (vitest direto e o acceptance spec real, os dois
sem embrulhar em pipe) no momento da interrupção; só a cobertura e os gates
Python ficaram para o orquestrador rodar, por instrução direta dele.

## Confirmação de que nada ficou aberto

Três quebras-e-restauras foram abertas nesta fatia; as três foram fechadas e
verificadas **antes** da mensagem de interrupção chegar:

1. `deliveryTokenNamed()` em `alert-intake.tsx` (T033) — restaurada,
   `md5sum` idêntico antes/depois (`f7a91c64c8765f77ff7ea8d47f82f614`).
2. O filtro de escopo em `machine-tokens.tsx` (T034, prova de que os testes
   novos pegam de verdade) — restaurada, `md5sum` idêntico
   (`3a795d5713b6d65a22dc9463c7eaa474`).
3. `receiverYaml` concatenando um campo plantado em `alert-intake.tsx` (T035)
   — restaurada, `md5sum` idêntico ao estado real pretendido
   (`04b603dff375155caca72407ca490d90`).

Varredura final, feita agora, nesta escrita: `grep -c "credential_value\|-broken"`
nos dois arquivos de origem tocados devolve `0` nos dois — nenhum marcador de
quebra deliberada sobrou no código real. `git status --short` mostra
exatamente sete arquivos, todos edição real e intencional, nenhum a meio de
uma quebra:

```
 M console/src/i18n/en.ts
 M console/src/i18n/pt-BR.ts
 M console/src/surfaces/settings/alert-intake.tsx
 M console/src/surfaces/settings/machine-tokens.tsx
 M console/tests/e2e/050-integrations-slideover-intake.acceptance.spec.ts
 M console/tests/unit/surfaces/settings-alert-intake.test.tsx
 M console/tests/unit/surfaces/settings-machine-tokens.test.tsx
```

Dois arquivos descartáveis de medição foram escritos e apagados durante a
sessão (`console/tests/e2e/_zzz-t535-measure.spec.ts`,
`console/tests/e2e/_zzz-t030-measure.spec.ts`) — nunca commitados, nunca
staged, confirmado por `git status --short console/tests/e2e/` limpo desses
dois nomes antes e depois de cada um.

## Tabela

| Peça | Estado | Detalhe |
|---|---|---|
| T034 — rotação leva a Machine tokens já filtrada | **FEITO** | Ver seção própria abaixo. `alert-intake.tsx:617-641` (o link), `machine-tokens.tsx:59-95,150-166` (o filtro que o destino precisava e não tinha). Provado seguindo o link de verdade num navegador real: `050-integrations-slideover-intake.acceptance.spec.ts:665-717`, **1 passed**, confirmado duas vezes. |
| `:535` — fonte calada em uma linha compacta | **FEITO — código corrigido, threshold intocado** | Ver seção própria. Medido de verdade: **102.375px** contra um limiar de 110.578125px (antes: 141.15625px). `alert-intake.tsx:498-517` (Provenance para dentro do cabeçalho) e `:567-580` (`summary=""`). |
| T035 — teste de segurança do bloco copiado | **FEITO** | `settings-alert-intake.test.tsx:588-641`. Planta um segredo, exercita o clique real de "Copy Alertmanager receiver YAML", lê o que foi de fato passado a `navigator.clipboard.writeText`, prova ausência do segredo e presença do marcador FR-058. Quebrado-e-restaurado para prova (era verde no primeiro run). |
| T033 — linha de confiança, caracterizada | **FEITO (já existia, agora com quebra-e-restaura real)** | `alert-intake.tsx:190-217` (`deliveryTokenNamed`), `:608-643` (a linha e a ação). Vermelho real observado e citado abaixo; restaurado, byte-idêntico. |
| T030 — orçamento de rolagem de `/settings/alert-intake` | **FEITO — característica confirmada, não correção** | Rodado de verdade contra o build parado: **1141px** (≈1.056 viewports) a 1080p, contra 2160px de orçamento — menor até que os 1202px que o T002 mediu antes desta feature começar. |

## T034 — FR-062, respondida de verdade

**O que "Rotate" fazia hoje, antes desta sessão — lido no componente, não no
href, porque não havia href nenhum para ler.** `console/src/surfaces/ingress.tsx`'s
`DeliveryToken` (a mesma função para "Issue" e para "Rotate") é um `<button>`
cujo `onClick` chama `issue()`, que faz `POST /api/delivery-token` e **mint a
um token novo, ali mesmo, mostrando o segredo uma vez num `<code
data-testid="delivery-secret">` na própria tela**. `alert-intake.tsx` só
trocava o *rótulo* do botão ("Issue a delivery token" → "Rotate") conforme
`deliveryTokenName` já existisse ou não — o mecanismo por trás dos dois
rótulos era **idêntico**: um mint inline, nunca uma navegação. Não existia
`href`, `<a>`, nem `<Link>` em lugar nenhum dessa faixa de código. FR-062
("Rotacionar DEVE levar a Machine tokens já filtrada") não estava apenas sem
prova — estava **falsa**: o rótulo prometia um destino que não existia.

**O que "Rotate" faz agora.** Quando já existe um delivery token
(`deliveryTokenName !== undefined`), o controle é uma navegação real (`<a>`,
via `Link` de `@/components/action` — o mesmo componente que `Provenance` já
usa para o link de "run") com `href="/settings/machine-tokens?scope=webhook.deliver"`,
rotulado "Rotate" (`alert-intake.tsx:629-641`, `rotateHref()` em `:227-235`).
Sem nenhum token emitido ainda (`deliveryTokenName === undefined`), o
controle continua **exatamente** o mint inline de antes (`ingress.token.issue`)
— FR-063 intocado, como o próprio despacho pediu.

`/settings/machine-tokens` **não filtrava nada antes desta sessão** —
`content()` lia `/identity/tokens` e desenhava todo token que não fosse
sessão de navegador, incondicionalmente. Sem essa metade, o link de Rotate
poderia ter o `href` certo e ainda assim não entregar nada — exatamente o
risco que o despacho nomeou ("o href conter um parâmetro de filtro" é mais
estreito que "a tela aterrissada mostrar tokens de entrega"). Adicionei:
`MACHINE_TOKENS_FILTERS: readonly FilterName[] = ['scope']`
(`machine-tokens.tsx:59`), lido via `readViewState` (o mesmo mecanismo de
estado-na-URL que toda tela filtrada deste console já usa), aplicado como um
segundo `.filter()` sobre os registros antes de agrupar (`:94-101`), com um
aviso visível (`data-testid="machine-tokens-filter"`, `:157-166`) nomeando o
escopo humanizado e oferecendo "Show all tokens" de volta.

**Segui o link de verdade, num navegador real, contra o build compilado —
não li o href e parei aí.** `050-integrations-slideover-intake.acceptance.spec.ts:665-717`,
teste novo "following 'Rotate' lands on Machine tokens, already narrowed to
delivery tokens":
1. Visita `/settings/machine-tokens` **sem filtro primeiro** e conta quantos
   `token-group` aparecem — para que "estreitou" seja uma comparação real, não
   uma suposição sobre quantos tokens o fixture carrega.
2. Visita Alert intake, lê o nome que a linha de confiança de fato nomeia.
3. Clica o link "Rotate" real.
4. Confirma a URL mudou para `/settings/machine-tokens?scope=...`.
5. Confirma que a lista resultante desenha **menos** grupos que a visita sem
   filtro.
6. Confirma que **todo** grupo mostrado carrega o escopo humanizado
   ("Webhook Deliver") no próprio texto.
7. Confirma que o token que a linha de confiança nomeou está genuinamente
   presente entre eles.

Resultado real, contra o servidor standalone reconstruído e o `mockplane` de
verdade: **1 passed (525-530ms)**, confirmado em duas rodadas completas do
arquivo inteiro.

**Um teste pré-existente, dos 21 que tinham de continuar verdes, mudou de
asserção — nomeado, não escondido.** O teste que já existia em `:645`
("the trust line names the delivery token and offers to rotate it")
verificava `page.getByRole('button', { name: /rotate/i })`. Como o controle
agora é corretamente uma navegação, o *role* de acessibilidade mudou de
`button` para `link` — troquei a consulta para `getByRole('link', ...)`.
A alegação que o teste protege ("a linha... oferece rotacioná-lo") continua
verdadeira, agora por um destino real em vez de um segundo mint; só a forma
de consultar o DOM mudou, porque o mecanismo por trás dela mudou de verdade.
Rodou de novo depois da mudança: **passed**.

## `:535` — o código estava errado, não o threshold

**Decisão**: o código. Abri `specs_v6/mockups/settings-v6.html#m3` e o card
calado (Grafana/Generic webhook) ali desenha exatamente nome, chip, um
espaçador e uma seta `▸` muda — nada mais, nem sequer uma dica textual de
"Format & test". Isso é **menos** do que o código (mesmo depois do conserto
parcial da fatia 6) desenhava: a linha de cabeçalho, **mais** uma linha de
`Provenance` sempre visível ("Where did this go? (0)"), **mais** uma caixa de
duas linhas ("Format & test" + a frase-resumo) do `Reference`. Como o mockup
pede algo **mais curto** do que o que existia, não mais alto, a cláusula do
despacho que autoriza afrouxar o threshold ("se o mockup mostrar algo mais
alto do que a asserção permite") não se aplica aqui — o convite era para
compactar o código, e foi isso que fiz. **O threshold da asserção nunca foi
tocado.**

Duas mudanças, as duas só no ramo `silent`, nada no ramo `receiving` nem nos
componentes compartilhados `Reference`/`Provenance` (que `first-run/verify.tsx`
e toda outra linha desta mesma tela também usam):
1. `Provenance` passou a renderizar dentro da própria linha de cabeçalho
   (junto ao nome e ao chip "Ready — nothing arrived yet"), em vez de numa
   linha própria abaixo — só para `silent` (`alert-intake.tsx:498-517`). O
   ramo `receiving` mantém `Provenance` na sua própria linha, porque o
   cabeçalho dele já carrega a informação de entrega.
2. `summary=""` no lugar da frase descritiva compartilhada, só no `Reference`
   do ramo `silent` (`alert-intake.tsx:567-580`) — o botão de duas linhas
   (título + resumo) vira uma linha só quando a segunda não tem texto. O
   `Reference` do ramo `receiving` continua com o resumo de sempre.

**Medido de verdade, via Playwright contra o servidor standalone reconstruído
— nunca inferido, nunca jsdom:**

| Momento | Altura da linha calada | Altura da linha recebendo | Limiar (metade da recebendo) | Resultado |
|---|---|---|---|---|
| Herdado da fatia 1 (as duas idênticas) | 179.15625px | 179.15625px | 89.578125px | VERMELHO |
| Como a fatia 6 deixou | 141.15625px | 221.15625px | 110.578125px | VERMELHO |
| Depois da mudança 1 (Provenance no cabeçalho) | 119.765625px | 221.15625px | 110.578125px | VERMELHO — medido pelo próprio acceptance spec rodando de verdade |
| Depois da mudança 2 (`summary=""`) | **102.375px** | 221.15625px | 110.578125px | **VERDE** |

Os números finais vieram de um spec descartável
(`console/tests/e2e/_zzz-t535-measure.spec.ts`, escrito, rodado uma vez,
apagado — nunca commitado nem staged) que mede exatamente o que a asserção
real mede, só com `console.log` em vez de comparar — e do próprio teste real
(`:535` no acceptance spec) passando duas vezes de ponta a ponta depois do
rebuild. A altura da linha recebendo nunca mudou (221.15625px em toda
medição) — a folga inteira veio de tornar a linha calada mais compacta,
nunca de inflar a outra.

## T035 — o teste, e o que ele afirma de verdade

Sim, escrevi o teste que planta o segredo. `settings-alert-intake.test.tsx:588-641`,
describe "security: no stored secret ever reaches the copied receiver block".
O que ele afirma, exatamente:
1. Planta uma string com cara de segredo (`ninja_wh_9f2b7c1e0d3a`) num campo
   (`credential_value`) da linha `alertmanager` de `/v1/ingress/sources` — um
   campo que `alert-intake.tsx` não tem nenhum caminho de código que leia para
   dentro de `receiverYaml`, espelhando o mesmo idioma que
   `integration-panel.test.tsx:520-593` já usa ("plantar onde o painel não tem
   razão nenhuma de ler").
2. Clica o botão real "Copy Alertmanager receiver YAML".
3. Captura o que foi de fato passado a `navigator.clipboard.writeText` (mock).
4. Afirma que o texto capturado **não** contém o segredo plantado, **contém**
   a frase-marcador do FR-058 ("paste the value of delivery token..."), e —
   além do idioma já estabelecido — varre todo elemento de `document.body`
   procurando o segredo também, não só o valor copiado.

Era verde no primeiro run (o código já lê só o campo certo). Segui a regra da
onda: quebrei de propósito (`receiverYaml` passou a concatenar
`text(pasteRow, 'credential_value')`), rodei o teste, vermelho real:

```
AssertionError: expected 'webhook_configs:\n- url: https://ninj…' not to contain 'ninja_wh_9f2b7c1e0d3a'
+ webhook_configs:
+ - url: https://ninjasre.example.invalid/webhooks/alertmanager
+   http_config:
+     authorization:
+       type: Bearer
+       credentials: paste the value of delivery token "Alert delivery" here
  ninja_wh_9f2b7c1e0d3a
```

Restaurado do backup em scratchpad; `md5sum` idêntico ao estado real
pretendido (`04b603dff375155caca72407ca490d90`) antes e depois; suíte inteira
do arquivo rodada de novo: **48 passed** (47 antes + este).

Também confirmei, lendo diretamente (não confiando na citação da fatia 6),
que `gateway/webhooks/sources/alertmanager.py:103`
(`receiver_yaml(*, url: str, token_name: str) -> str`) genuinamente não tem
terceiro parâmetro, e que
`tests/contract/console/test_ingress_receiver_yaml_contract.py:68-78`
(`test_the_generator_s_signature_carries_no_parameter_a_secret_could_travel_through`)
já **prega essa assinatura fechada** — pré-existente, não escrito por mim,
continua a prova estrutural mais forte, e não a toquei nem a dupliquei. Meu
teste novo é o complemento do lado do console que o despacho pediu: provar
que o *caminho de cópia da tela* não introduz um vazamento que a garantia do
backend não cobriria.

## T033 — caracterizada, com quebra-e-restaura real desta vez

Já funcionava (feature 030), exatamente como o despacho disse. Quebrei
`deliveryTokenNamed()` (`alert-intake.tsx:211` no momento da quebra) trocando
`.includes(permission)` por `.includes(`${permission}-broken`)` — o
cross-reference por escopo passa a nunca achar ninguém. Rodei `names the
delivery token once one has actually authenticated deliveries with it`
isolado. Vermelho real:

```
Expected element to have text content: am-cluster
Received: No delivery token has authenticated this yet.Issue a delivery token
```

Restaurado do backup em scratchpad tirado antes da quebra; `md5sum` idêntico
antes/depois (`f7a91c64c8765f77ff7ea8d47f82f614`); `git status --short`/
`git diff --stat` do arquivo vazios nesse ponto (foi o primeiro passo desta
sessão, antes de qualquer edição real minha). Segura — sem surpresa, sem
achado de "isto não funciona de verdade".

## T030 — característica confirmada, não correção

Rodei `050-integrations-slideover-intake.acceptance.spec.ts:577` ("the whole
screen fits within 2 viewports") de verdade, contra o servidor standalone
reconstruído, **depois** de todas as outras mudanças desta fatia terem
aterrissado — **passou**. Medi o número real via spec descartável (mesmo
padrão do `:535`, apagado depois, nunca staged): **1141px** a 1080p
(≈1.056 viewports), contra orçamento de 2160px/2.0 viewports. Isso é **menor**
que os 1202px que o T002 mediu antes desta feature começar — o conteúdo que a
fatia 6 acrescentou (volume da semana, botão do YAML) foi mais do que
compensado pela compactação que o conserto do `:535` trouxe às linhas
caladas. Caracterização, não correção: o orçamento nunca esteve realmente
ameaçado.

## Números da suíte de aceitação — antes e depois desta fatia

**Antes** (relatado pelo despacho, confirmado pela leitura do `controle.md`
da fatia 6): **21 passed, 3 failed** — os três vermelhos eram `:535` (meu) e
os dois nós da cadeia (fatia 7).

**Depois**, rodado de ponta a ponta duas vezes contra o build reconstruído,
sem pipe embrulhando a saída:

```
23 passed (18.3s)
2 failed
  ...the chain... four nodes render in order, each carrying a real, non-empty value
  ...the chain... the destination node navigates to the section whose name matches what it promises
```

**23 passed, 2 failed** — os dois vermelhos que sobram são exatamente os dois
nós da cadeia, intocados, da fatia 7. Os 21 que já passavam continuam
passando; `:535` fechou; o teste novo de T034 (`:665`) passa.

## Gates rodados nesta fatia — reais, o que vi de verdade e o que não vi

| Gate | Comando | Resultado visto por mim |
|---|---|---|
| Suíte de unidade, arquivo único | `npx vitest run --pool=forks tests/unit/surfaces/settings-alert-intake.test.tsx` | **48 passed** (sem seleção, arquivo inteiro) |
| Suíte de unidade, arquivo único | `npx vitest run --pool=forks tests/unit/surfaces/settings-machine-tokens.test.tsx` | **7 passed** (4 antigos + 3 novos) |
| Acceptance spec inteiro, sem pipe | `uv run python -m tools.console_e2e run -- tests/e2e/050-integrations-slideover-intake.acceptance.spec.ts` | **23 passed, 2 failed** (rodado duas vezes, mesma contagem) |
| `console_gate typecheck` | `uv run python -m tools.console_gate typecheck` | limpo (`tsc --noEmit`, sem saída) |
| `console_gate lint` | `uv run python -m tools.console_gate lint` | limpo (`eslint . && node scripts/check-css-literals.mjs`) |
| `console_gate format-check` | `uv run python -m tools.console_gate format-check` | limpo — "All matched files use Prettier code style!" (rodado só uma vez; não pegou nada desta vez, ao contrário do aviso do despacho para as fatias anteriores) |
| `console_gate build` | `uv run python -m tools.console_gate build` | rodado duas vezes (antes e depois do conserto de `:535`), os dois com `tsc` limpo embutido no build, sem erro |

**Não rodados nesta sessão, por instrução direta do orquestrador na
interrupção** (que disse que rodaria ele mesmo):

- `console_gate test` — o gate real de vitest, com os limiares de cobertura
  (piso de 90.1% de branch). As suítes que rodei diretamente (acima) não
  aplicam esse piso — o despacho já avisa que os dois não são equivalentes.
  Este slice adiciona branches novos (`scope === undefined ? ...`,
  `deliveryTokenName === undefined ? <DeliveryToken/> : <Link/>`, o
  `summary=""` do ramo silent) — não sei se o piso segura sem rodar o gate
  de verdade.
- Qualquer gate Python (`ruff`, `mypy`, `pytest`, `make lint`,
  `make typecheck`). **Nenhum arquivo Python foi tocado nesta fatia** — só
  li `gateway/webhooks/sources/alertmanager.py` e
  `tests/contract/console/test_ingress_receiver_yaml_contract.py` para o
  T035, nunca os editei. `git status --short` confirma zero arquivos fora de
  `console/` modificados. Não rodei esses testes de novo para confirmar que
  continuam passando — não deveriam ter sido afetados (arquivo intocado),
  mas "não deveria" não é "foi visto", e fica nomeado aqui em vez de
  assumido.
- `make verify` — do orquestrador, como em toda fatia.

## `tasks.md` — o que foi marcado

Marquei **T030, T033, T034 e T035** — as quatro tarefas que esta fatia
recebeu, cada uma com vermelho→verde observado por mim ou, para T030/T033,
com a caracterização (quebra-e-restaura real, ou execução real contra o
build) que a tarefa pedia. Nenhuma outra linha de `tasks.md` foi tocada.

## O que fica pendente, nomeado, não escondido

1. **`console_gate test` (cobertura) nunca rodou nesta sessão** — os branches
   novos desta fatia contra o piso de 90% nunca se encontraram por mim; é o
   orquestrador quem vai ver esse número primeiro.
2. **Nenhum gate Python foi re-executado**, apesar de eu ter lido (não
   editado) dois arquivos Python para o T035 — ver a razão acima.
3. **Fora do escopo desta fatia, como o despacho nomeou**: a cadeia
   (T036-T040) e `schedules-destinations.tsx` continuam vermelhas/intocadas —
   os dois nós da cadeia são exatamente os dois `failed` finais, confirmados,
   não investigados, da fatia 7.
4. **O banner de filtro em Machine tokens (`machine-tokens-filter`) é uma
   peça nova, fora de qualquer tarefa nomeada da 050** — não existe uma T-
   própria para "Machine tokens sabe filtrar por escopo" porque essa tela
   pertence a uma feature diferente (030/administração). Construí o mínimo
   necessário para que FR-062 fosse cumprível de verdade (sem ele, o link do
   Rotate teria o `href` certo e ainda assim aterrissaria numa lista
   completa, não filtrada) — mecanismo genérico por `scope` na URL, não
   amarrado a `webhook.deliver` especificamente, para não inventar uma regra
   de negócio que não existe. Se uma fatia futura de outra feature já possui
   ou planeja um filtro próprio para Machine tokens, vale reconciliar os
   dois em vez de manter duas implementações paralelas.

---

# Fatia 7 de nove — T036, T037, T038, T039, T040 — a cadeia visível

Estado abaixo verificado contra o código nesta árvore, HEAD `c5afb96` em
`feat/v6-scope-and-settings`, árvore limpa antes desta sessão (confirmado por
`git status --short` no início). Escopo exatamente o que o despacho nomeou: os
dois vermelhos que sobravam da suíte de aceitação (`:765` e `:805`), a
renomeação que os torna possíveis (T037) e o teste que trava essa propriedade
(T038), mais a suíte transversal (T040). Não toquei o catálogo, o painel de
integração, nem as baselines visuais — fora do escopo desta fatia, como o
despacho nomeou.

## Confirmação de que nada ficou aberto

Duas quebras-e-restauras foram abertas nesta fatia; as duas foram fechadas e
verificadas antes desta escrita:

1. `settings.schedulesDestinations.advanced.surfaces.title` em `en.ts` (T038) —
   restaurado do backup em scratchpad, `md5sum` idêntico antes/depois
   (`74c876bf1d0d4a5fbf65945b224e3f3a`).
2. Quatro pontos de `alert-intake.tsx` quebrados juntos (a ternária vazia do
   nó, `CHAIN_ROUTING_HREF`, o predicado de destino usável, e a independência
   do `Panel`) — restaurado do backup em scratchpad, `md5sum` idêntico
   antes/depois (`fd6f7b7ddea5b8adc87da713d302a344`), confirmado outra vez
   depois do `prettier --write` (que só mexeu em formatação, não em conteúdo
   lógico).

`git status --short` mostra exatamente cinco arquivos no fim da sessão, todos
edição real e intencional, nenhum a meio de uma quebra:

```
 M console/src/i18n/en.ts
 M console/src/i18n/pt-BR.ts
 M console/src/surfaces/settings/alert-intake.tsx
 M console/tests/unit/surfaces/settings-alert-intake.test.tsx
 M console/tests/unit/surfaces/settings-schedules-destinations.test.tsx
```

Nenhum arquivo Python foi tocado nesta fatia — a cadeia lê um endpoint que já
existia (`/v1/transit/destinations`, já consumido por
`schedules-destinations.tsx`) de um lugar novo, e a renomeação é só i18n.

## Tabela

| Peça | Estado | Detalhe |
|---|---|---|
| T036 — teste da cadeia, falhando primeiro | **FEITO (já existia da Fase 2, revermelhado nesta sessão por acidente de build, depois reconfirmado verde)** | O teste já estava escrito em `050-integrations-slideover-intake.acceptance.spec.ts:765` e `:805` desde a Fase 2 (T004/T005); a fatia 6b já o tinha confirmado vermelho (23 passed/2 failed) e o despacho reafirmou o mesmo número. Ver seção própria abaixo sobre a reconfirmação real desta sessão. |
| T037 — renomear as duas seções avançadas | **FEITO** | `console/src/i18n/en.ts:233` — `'Advanced: chat channels, report recipients and notification sinks'` (era `report destinations`). `console/src/i18n/pt-BR.ts` linha correspondente — `'destinatários de relatório'` (era `destinos de relatório`). A seção `transit` (linha 224 do en.ts) não foi tocada. Ver seção própria abaixo. |
| T038 — teste de unidade dos nomes | **FEITO** | `settings-schedules-destinations.test.tsx:381-427`, describe "the two advanced section names", teste "share no noun...". Afirma a propriedade (nenhuma palavra de conteúdo compartilhada), não a string. Vermelho real observado e citado abaixo; restaurado, byte-idêntico; verde de novo. |
| T039 — desenhar a cadeia | **FEITO** | `alert-intake.tsx:276-347` (`ChainNodeSpec`, `CHAIN_ROUTING_HREF`, `CHAIN_EMPTY_LABELS`, `handlingChain`), `:420` (`destinationRows`), `:738-767` (a marcação, quatro `chain-node`). Quatro nós reais, cada um um `<Link>` de verdade. Prova real via Playwright: `:765` e `:805` **passed** contra o build reconstruído. Ver seção própria abaixo. |
| T040 — suíte transversal | **FEITO** | `transversal-rules.spec.ts` rodado de ponta a ponta duas vezes: **25 passed, 7 skipped, 0 failed** — idêntico ao número que o despacho deu como base, nas duas rodadas, incluindo as três rotas desta feature (`/settings/alert-intake`, `/integrations`, `/settings/schedules-destinations`). |

## T037 — os dois nomes novos, e por que não compartilham substantivo nenhum

**Antes**, os dois títulos das seções avançadas de
`/settings/schedules-destinations`:

- `advanced.transit.title`: *"Advanced: routing rules and delivery
  destinations"* (cobre `transit.rules` e `transit.destinations`).
- `advanced.surfaces.title`: *"Advanced: chat channels, report destinations
  and notification sinks"* (cobre `surfaces.channels`,
  `surfaces.report_destinations`, `surfaces.notification_sinks`).

A palavra que os dois compartilhavam era exatamente **"destinations"** — o
nome do próprio nó que a cadeia precisa prometer e cumprir. Enquanto os dois
títulos tivessem essa palavra, um nó de destino não conseguiria dizer "vou
para a seção que fala de destinos" e aterrissar num lugar sem ambiguidade.

**Decisão**: renomear, não fundir. As duas seções cobrem assuntos
genuinamente distintos — roteamento e entrega de alerta (`transit`) contra
canais de chat, relatórios e notificações (`surfaces`) — e fundi-las
esconderia essa distinção sem necessidade. A cirurgia mínima: a seção
`transit` ficou **exatamente como estava** (ela é a dona de verdade de
`transit.destinations`, e é para lá que a cadeia aponta); só a seção
`surfaces` mudou, trocando "report **destinations**" por "report
**recipients**" — o mesmo campo (`surfaces.report_destinations`, cujo
**rótulo de campo** continua "Report destinations"/"Destinos de relatório",
intocado — a regra é sobre o nome da seção, não sobre o rótulo do campo
dentro dela), descrito por uma palavra diferente no título da seção.

**Depois**:

- `advanced.transit.title` (en): "Advanced: routing rules and delivery
  destinations" — substantivos: routing, rules, delivery, destinations.
- `advanced.surfaces.title` (en): "Advanced: chat channels, report
  **recipients** and notification sinks" — substantivos: chat, channels,
  report, recipients, notification, sinks. **Zero sobreposição.**
- pt-BR espelha a mesma troca: "Avançado: regras de roteamento e destinos de
  entrega" contra "Avançado: canais de chat, **destinatários** de relatório e
  alvos de notificação" — "destino" e "destinatário" são palavras diferentes
  (a segunda significa "para quem", não "para onde"), então o mesmo raciocínio
  vale nas duas línguas, cada uma verificada isoladamente por tokenização.

`"Advanced:"` é o prefixo estrutural que **toda** seção avançada deste console
carrega (a mesma convenção em `alert-intake.tsx`, `knowledge.tsx`,
`agent.tsx` etc.) — tratei-o como a moldura, não como parte do nome que a
regra compara, e o teste de T038 já exclui explicitamente palavras função
como essa (ver abaixo).

## T038 — o teste, e o vermelho real que ele produz

`settings-schedules-destinations.test.tsx:381-427`. O teste lê o `<summary>`
de dentro de cada `<details>` (`advanced-config-transit` e
`advanced-config-surfaces-destinations`, os mesmos testids que os testes
já existentes desta tela usam), tokeniza os dois títulos em palavras de
conteúdo (minúsculas, pontuação fora, uma lista curta de palavras função —
"advanced", "and", "the", "a", "an", "of", "or", "for" — descartada), e
afirma que a interseção dos dois conjuntos é vazia. **A asserção é sobre a
propriedade — nenhuma das duas strings literais aparece como valor
esperado no teste**, exatamente como o despacho pediu.

Era verde no primeiro run (T037 já tinha sido aplicado antes de eu escrever o
teste — essa ordem é a que `tasks.md` manda: "T037 → T038" nas Dependencies,
e o próprio despacho repete "T037 comes before the chain, not after it").
Para provar que o teste mede a propriedade de verdade, reverti só o `en.ts`
para o título antigo ("chat channels, report **destinations** and
notification sinks") e rodei de novo. Vermelho real:

```
AssertionError: both section names use: destinations ("Advanced: routing
rules and delivery destinations" / "Advanced: chat channels, report
destinations and notification sinks"): expected [ 'destinations' ] to
deeply equal []

- []
+ [
+   "destinations",
+ ]
```

A mensagem nomeia exatamente a palavra que o defeito compartilha — não é um
`toBe(false)` mudo. Restaurado do backup em scratchpad,
`md5sum` idêntico antes/depois; suíte inteira do arquivo rodada de novo:
**20 passed** (19 pré-existentes + este).

## T036/T039 — a cadeia, os quatro valores, e o que cada um promete

### O que cada nó mostra, e de onde vem

Nenhum endpoint novo. `content()` em `alert-intake.tsx` já lia `ingress`,
`rules`, `deliveries`, `receivers`, `tree`, `identity`; acrescentei **uma**
leitura, `panelRead('/v1/transit/destinations', ...)` (`alert-intake.tsx:361-372`),
o mesmo endpoint que `schedules-destinations.tsx` já consome para a sua
própria seção de destinos.

`handlingChain(ordered, ruleRows, destinationRows)` (`alert-intake.tsx:314-347`)
computa os quatro nós:

1. **intake** — a primeira fonte de `ordered` (a lista de fontes que o
   próprio `content()` já ordena, caladas primeiro) que **não** está calada
   (`!flag(source, 'never_delivered')`). No fixture `populated`: `alertmanager`
   (a única, junto com `grafana`, que já recebeu algo — `generic` está
   calada). Link: `/integrations` — o catálogo, de onde a integração do
   vendor é gerida.
2. **rule** — a primeira linha de `ruleRows`. O gateway garante (documentado
   no próprio `transit.py`: "the catch-all always present and last") que a
   regra catch-all vem sempre por último, então a primeira linha é sempre a
   regra que decide de verdade — uma regra explícita quando existe, o
   catch-all quando não. No fixture `populated`: `critical-to-platform`
   (a regra que casa `alertmanager`, exatamente como o despacho descreveu).
   Link: a seção `transit` de Schedules & destinations.
3. **action** — o campo `action` da mesma regra escolhida acima (não uma
   segunda leitura independente). No fixture `populated`: `investigate`.
   Mesmo link da regra — `action` é um campo *dentro* da mesma linha de
   `transit.rules`, não um ajuste à parte.
4. **destination** — a primeira linha de `destinationRows` cujo
   `unconfigurable_reason` é vazio (ou seja, a primeira que este deployment
   pode de fato usar). No fixture `populated`: `chat-incidents` (a outra,
   `oncall-teams`, tem `unconfigurable_reason` preenchido — "this deployment
   delivers over slack" — e é corretamente pulada; provado por um teste que
   inverte a ordem do array, ver abaixo). Mesmo link da regra e da ação — a
   mesma seção `transit` também é dona de `transit.destinations`.

### O link de verdade, não um href lido

`CHAIN_ROUTING_HREF = '/settings/schedules-destinations#' +
advancedConfigSectionId('transit.')` (`alert-intake.tsx:293`) — a mesma
função exportada que `schedules-destinations.tsx` já usa para dar `id` ao seu
próprio `<details>` da seção `transit`, chamada aqui com o mesmo argumento
literal (`'transit.'`), então o valor computado é garantidamente o mesmo:
`advanced-config-transit`. Não inventei uma segunda convenção de âncora.

**O que acontece de verdade, num navegador, ao seguir o nó de destino** — não
lido do `href`, seguido: `050-integrations-slideover-intake.acceptance.spec.ts:805`
navega para `/settings/alert-intake`, localiza
`[data-testid="chain-node"][data-role="destination"]`, encontra o link real
dentro dele (`destination.getByRole('link')`), **clica**, e confirma que a
URL final casa `/\/settings\/schedules-destinations/`. Passou contra o build
reconstruído. Isso prova a navegação real; o valor exato do `href`
(`/settings/schedules-destinations#advanced-config-transit`) é o que o meu
próprio teste de unidade (`settings-alert-intake.test.tsx:1081-1094`) afirma
literalmente, igual para os nós `rule`, `action` e `destination`, e
`/integrations` para o nó `intake` — os dois lados (navegação real +
`href` exato) juntos fecham a alegação sem depender só de ler o atributo.
Como a `<details id="advanced-config-transit">` já existe naquela página
(mecanismo pré-existente, intocado, coberto pelos testes já existentes de
`settings-schedules-destinations.test.tsx`), seguir o link aterrissa
exatamente na seção "Advanced: routing rules and delivery destinations" —
fechada por padrão (é um `<details>` sem `open`), mas rolada até ela.

### A cadeia nunca desaparece — a decisão de projeto que quase não tomei

**Descoberta desta fatia, guardada para quem tocar isto de novo**: o mockup
desenha o card "What happens to it" como se fosse só a cadeia — mas
`data.rules.title` (o título do painel que já lista as regras em
`routing-rule`/`catch-all-rule`) já é literalmente "What happens to it". A
tentação óbvia era desenhar a cadeia **dentro** desse mesmo `<Panel>`. Não
fiz isso: um `Panel` troca `children` inteiro por um `EmptyState` genérico
quando seu `state` vira `'empty'` ou `'error'` — e `ruleRows.length === 0`
(que aciona exatamente esse estado) é a mesma condição que decide se o nó de
regra da cadeia está "sem valor configurado". Se a cadeia vivesse dentro
desse `Panel`, um deployment sem nenhuma regra (ou uma leitura de regras que
falhasse) faria a cadeia **inteira** sumir — os quatro nós, não só o da
regra — exatamente o que FR-072 proíbe ("a cadeia não desaparece").
A cadeia (`alert-intake.tsx:738-767`) vive **fora** de qualquer `Panel`,
como um `<div>` próprio entre o painel "What arrives" e o painel "What
happens to it". Provado quebrando de propósito (ver abaixo): com a leitura de
`/v1/transit/rules` forçada a falhar, o painel de regras vai para
`data-state="error"` como sempre foi — e a cadeia continua com seus quatro
nós, o de regra e o de ação dizendo "No rule is configured yet"/"No action
runs yet".

### Os testes de unidade novos, e as quebras-e-restauras reais

`settings-alert-intake.test.tsx:1024-1143`, describe "the chain: intake,
rule, action and destination" — sete testes:

1. `:1025` — os quatro nós, na ordem, cada um com o valor literal do fixture
   `populated` (`alertmanager` / `critical-to-platform` / `investigate` /
   `chat-incidents`).
2. `:1043` — o nó de regra é uma substring do texto combinado das linhas
   `routing-rule`/`catch-all-rule` que o mesmo painel já desenha — o mesmo
   cross-reference que o acceptance spec faz, em miniatura.
3. `:1058` — inverte a ordem do array de `/v1/transit/destinations` (a
   inconfigurável primeiro) e confirma que a cadeia ainda escolhe
   `chat-incidents`, não `oncall-teams` — prova que o filtro por
   `unconfigurable_reason` roda de verdade, não que o código só pega a
   posição zero.
4. `:1081` — os quatro `href` exatos, um por papel.
5. `:1096` — `/v1/transit/rules` forçado a responder `{rules: []}` (200,
   não falha): os nós de regra e ação dizem "No rule is configured yet"/"No
   action runs yet", a cadeia continua com quatro nós, e o link do nó de
   regra continua sendo o mesmo `href` real.
6. `:1119` — cenário `empty` inteiro (as três fontes nunca entregaram, zero
   destinos declarados): nó de intake diz "No source has delivered yet", nó
   de destino diz "No destination is configured yet", **e** os nós de regra
   e ação continuam mostrando o catch-all de verdade (`catch-all` /
   `investigate`) — o catch-all é uma decisão real, nunca uma ausência.
7. `:1133` — `/v1/transit/rules` forçado a **falhar** (não 200 vazio,
   erro de rede de verdade, o mesmo mecanismo que um teste pré-existente já
   usa para o painel de regras): o painel de regras vai a `data-state="error"`
   (confirmado, 1 painel), e a cadeia continua com quatro nós — a prova
   direta da decisão de projeto acima.

**Quebra-e-restaura real, os cinco testes que ela prova**: fiz quatro
alterações simultâneas em `alert-intake.tsx` — (a) a ternária de valor vazio
do nó virou sempre `node.value` (nunca a mensagem "No X"); (b)
`CHAIN_ROUTING_HREF` ganhou um sufixo `-broken`; (c) o predicado de destino
usável virou `() => true` (pega sempre a primeira linha, ignorando
`unconfigurable_reason`); (d) a `<div>` da cadeia passou a só renderizar
quando `dependencyOf(rules) === ''`. Rodei o arquivo inteiro. Vermelho real,
exatamente os cinco testes que essas quatro propriedades sustentam, com os
outros dois (`:1025` e `:1043`) continuando verdes porque não tocam nenhuma
das quatro coisas quebradas:

```
× picks the first destination this deployment can actually deliver to, skipping one it cannot
× each node links to the screen that owns its setting
× still shows four nodes, naming what is missing, when the deployment has configured no rule
× still shows four nodes, naming what is missing, on a deployment that has configured nothing
× does not disappear when the routing-rules read itself fails

Tests  5 failed | 2 passed | 48 skipped (55)
```

Restaurado do backup em scratchpad, `md5sum` idêntico antes/depois
(`fd6f7b7ddea5b8adc87da713d302a344`); suíte inteira rodada de novo: **55
passed**.

**Os dois testes que ficaram de fora da quebra, nomeado sem esconder**:
`:1025` ("renders four nodes...") e `:1043` ("the rule node names a
rule...") não exercitam nenhuma das quatro propriedades que quebrei — os
dois só leem o caminho "populado, tudo presente", que nenhuma das quatro
quebras toca. Não escrevi uma quinta quebra dedicada a eles por orçamento de
tempo desta sessão; a alegação que eles protegem (os quatro valores corretos
no cenário populado) é a mesma que `050-integrations-slideover-intake.acceptance.spec.ts:765`
já prova, com vermelho documentado pela fatia 6b e reconfirmado nesta sessão
(ver próxima seção) — não é uma alegação sem nenhuma prova de vermelho, só
uma cujo vermelho não veio de uma quebra-e-restaura minha especificamente
sobre esses dois testes de unidade.

### O vermelho real desta sessão — um acidente de build que serviu de prova

Antes de reconstruir o console, rodei
`uv run python -m tools.console_e2e run -- tests/e2e/050-integrations-slideover-intake.acceptance.spec.ts`
pela primeira vez nesta sessão. Resultado: **23 passed, 2 failed** — os dois
falhos eram `:765` e `:805`, com o log de rede mostrando que
`/v1/transit/destinations` **nunca foi chamado** (a implementação já estava
no código-fonte, mas o servidor standalone servido pelo `console_e2e run`
ainda era o build antigo, de antes desta fatia). Vermelho real, texto exato:

`:765` (linha 772 do spec):

```
Error: expect(locator).toHaveCount(expected) failed
Locator:  getByTestId('chain-node')
Expected: 4
Received: 0
```

`:805` (linha 814 do spec):

```
Error: expect(locator).toBeVisible() failed
Locator: locator('[data-testid="chain-node"][data-role="destination"]')
Expected: visible
Error: element(s) not found
```

Isso bate, byte a byte na forma, com o que a fatia 6b já tinha documentado
("21 passed, 3 failed" nomeando os dois nós da cadeia entre os vermelhos) e
com o que o despacho desta fatia reafirmou ("23 passed / 2 failed"). Não foi
um vermelho que eu produzi de propósito antes de implementar — a
implementação já estava escrita quando rodei isso — mas é uma reconfirmação
de primeira mão, nesta sessão, do mesmo vermelho documentado, com a mesma
causa (a cadeia não existe) manifestando de um jeito que também expôs um
fato operacional novo (próxima seção).

**Descoberta operacional, para quem rodar isto depois**: `console_e2e run`
**não reconstrói o console a partir do código-fonte**. Ele serve o build
standalone que já existe em disco. Qualquer mudança em `console/src/**`
precisa de `uv run python -m tools.console_gate build` (ou equivalente)
**antes** de `console_e2e run`, ou a suíte testa código velho silenciosamente
— o sintoma é exatamente este: testes que deveriam estar verdes continuam
vermelhos com a mensagem antiga, e o log de rede é a única pista (uma
chamada que o código novo faz e que nunca aparece). Rodei `console_gate
build` duas vezes nesta fatia — uma depois de escrever o código, outra
depois do `prettier --write` reformatar `alert-intake.tsx` — e reconfirmei a
suíte inteira depois de cada uma.

### O verde final, depois do build reconstruído

Duas rodadas completas, sem pipe embrulhando a saída:

```
25 passed (7.8s)
```

incluindo, nomeados:

```
✓  24 › the chain: intake, rule, action and destination, in one line › four nodes render in order, each carrying a real, non-empty value (265ms)
✓  25 › the chain: intake, rule, action and destination, in one line › the destination node navigates to the section whose name matches what it promises (380ms)
```

**Antes desta fatia**: 23 passed, 2 failed (documentado pela fatia 6b,
reafirmado pelo despacho, e reconfirmado por mim nesta sessão contra o build
antigo, ver acima). **Depois**: **25 passed, 0 failed** — os 23 que já
passavam continuam passando; os dois vermelhos que sobravam fecharam.

## T040 — a suíte transversal, antes e depois

**Antes** (dito pelo despacho): 25 passed / 7 skipped / 0 failed.

**Depois**, rodado de ponta a ponta duas vezes contra o build reconstruído:

```
7 skipped
25 passed (7.1s)
```

— idêntico nas duas rodadas e idêntico ao número de partida. As três rotas
desta feature, uma por uma (`grep` no log de cada rodada):

```
✓ /settings/alert-intake › carries no banned vocabulary in its visible text
✓ /settings/alert-intake › draws no empty cell in a configuration table's Value column
✓ /settings/schedules-destinations › carries no banned vocabulary in its visible text
✓ /settings/schedules-destinations › draws no empty cell in a configuration table's Value column
✓ /integrations › carries no banned vocabulary in its visible text
✓ /integrations › stays within the scroll budget
✓ /integrations › draws no empty cell in a configuration table's Value column
```

`/settings/schedules-destinations` — a rota que a renomeação do T037 tocou —
está entre as verdes, sem vocabulário banido e sem regressão de orçamento de
rolagem. `ROUTES_UNDER_THESE_RULES` (`transversal-rules.spec.ts:136-139`) já
inclui as três rotas automaticamente (as duas de `/settings/*` vêm de
`SETTINGS_ROUTES`, lido do próprio `console/src/shell/routes.ts`;
`/integrations` está na lista explícita ao lado) — não precisei acrescentar
nada à enumeração de rotas.

## Gates rodados nesta fatia — reais, com resultado visto por mim

| Gate | Comando | Resultado |
|---|---|---|
| `console_gate typecheck` | `uv run python -m tools.console_gate typecheck` | limpo, duas vezes (antes e depois dos ajustes de lint) |
| `console_gate lint` | `uv run python -m tools.console_gate lint` | **pegou 4 erros reais** (`@typescript-eslint/no-unnecessary-condition` em três `?? ''`/`?.` desnecessários nos dois arquivos de teste novos — o próprio TypeScript deste projeto tipa `Element.textContent` como não-nulo aqui); corrigido, limpo na rodada seguinte |
| `console_gate format-check` | `uv run python -m tools.console_gate format-check` | **pegou 2 arquivos** (`alert-intake.tsx`, `settings-alert-intake.test.tsx`) — nono slice em nono, contando esta; corrigido com `prettier --write` nos dois arquivos nomeados (nenhum outro), limpo na rodada seguinte |
| `console_gate test` (cobertura) | `uv run python -m tools.console_gate test` | **2564 passed, 0 failed** (148 arquivos). Cobertura: **Statements 93.88%, Branches 90.11%, Functions 91.7%, Lines 95.9%** — acima do piso de 90% de branch, e **subiu** dos 90.08% de partida apesar do componente novo de quatro nós com ramos de estado vazio. Exit code confirmado `0` (rodado sem pipe, saída redirecionada a arquivo, `$?` lido diretamente — não confiei num pipe). |
| Acceptance spec inteiro | `uv run python -m tools.console_e2e run -- tests/e2e/050-integrations-slideover-intake.acceptance.spec.ts` | **25 passed, 0 failed** — rodado três vezes ao todo nesta fatia (a primeira, sem querer, contra o build velho, deu 23/2 — ver seção própria; as duas seguintes, contra o build reconstruído, deram 25/0 as duas) |
| Suíte transversal | `uv run python -m tools.console_e2e run -- tests/e2e/transversal-rules.spec.ts` | **25 passed, 7 skipped, 0 failed**, duas vezes |
| `tests/architecture/test_contract_coverage.py` | `uv run pytest tests/architecture/test_contract_coverage.py -q` | **11 passed** |
| `tests/contract/console/` (suíte inteira) | `uv run pytest tests/contract/console/ -q` | **466 passed, 1 failed**, terminou em segundo plano depois desta sessão já estar escrevendo o ledger (409s). O único vermelho — `test_console_visual_regression.py::test_the_untouched_baselines_still_match`, especificamente `machine-tokens-1440-light` — é **pré-existente e fora do alcance desta fatia**: `console/src/surfaces/settings/machine-tokens.tsx` foi tocado por último no commit `c5afb96` (o próprio HEAD de partida desta sessão, fatia 6b — o banner de filtro `machine-tokens-filter`), e `console/visual/baselines/machine-tokens-1440-light.png` foi commitado por último em `c730bfb`, **antes** dessa mudança — a baseline nunca foi recapturada depois de o filtro ser desenhado. Eu não toquei `machine-tokens.tsx` nem qualquer baseline nesta fatia; é exatamente o trabalho que a Fase 11 (T044-T046, `make console-visual-accept` com revisão) existe para fazer, na fatia 8. |

**Não rodados nesta fatia, por estarem fora do escopo que o despacho
nomeou**: `make verify` (do orquestrador, como sempre); `console-visual`/
`console-visual-accept` (Fase 11, T044-T046 — a fatia 8 de polimento e
baselines, não esta); qualquer gate Python além dos dois nomeados acima
(nenhum arquivo Python foi tocado — `check-constants`, `check-imports`,
`check-protocols`, `check-deps`, `ruff`, `mypy` não têm superfície nova para
verificar).

## `tasks.md` — o que foi marcado

Marquei **T036, T037, T038, T039 e T040** — as cinco tarefas que esta fatia
recebeu, cada uma com vermelho→verde real observado por mim (T037/T039 via
quebra-e-restaura + a suíte de aceitação reconstruída; T038 via
quebra-e-restaura própria; T040 via duas rodadas idênticas ao número de
partida). Nenhuma outra linha de `tasks.md` foi tocada.

## O que fica pendente, nomeado, não escondido

1. **Dois testes de unidade novos (`:1025`, `:1043` em
   `settings-alert-intake.test.tsx`) não têm quebra-e-restaura própria** —
   nomeado na seção de T036/T039 acima, com a razão exata (orçamento de tempo
   desta sessão) e o que os cobre em vez disso (o vermelho documentado e
   reconfirmado do acceptance spec, que exercita exatamente a mesma
   implementação).
2. **`machine-tokens-1440-light` não bate com a baseline commitada** —
   descoberto pela rodada de `tests/contract/console/` (terminou em segundo
   plano depois de o resto desta fatia estar fechado). **Não é um defeito
   desta fatia**: nem `machine-tokens.tsx` nem nenhuma baseline foram tocados
   por mim aqui. A causa, lida direto do histórico: `machine-tokens.tsx`
   mudou pela última vez em `c5afb96` (o próprio commit no HEAD de partida
   desta sessão — o banner de filtro que a fatia 6b acrescentou), e
   `machine-tokens-1440-light.png` foi commitado pela última vez em
   `c730bfb`, antes dessa mudança. A baseline ficou órfã do banner desde
   antes de esta fatia começar. Nomeado aqui para a fatia 8 (Fase 11,
   T044-T046) recapturar deliberadamente, com revisão — não é algo que uma
   fatia de implementação deva corrigir de passagem.
3. **Fora do escopo desta fatia, como o despacho nomeou**: T041-T042 (rodapé
   auditável, já feito em fatia anterior), T043-T050 (Fase 11 — i18n
   final, baselines visuais, `make verify`/`make console-check` completos,
   efeito no corpus sintético, o `controle.md` final consolidado) — a fatia
   8 de polimento e gates, não esta.
4. **A descoberta operacional sobre `console_e2e run` não reconstruir a
   partir do código-fonte** (seção própria acima) — registrada aqui para
   quem rodar os gates desta feature depois: sempre `console_gate build`
   antes de `console_e2e run`, depois de qualquer mudança em `console/src/**`.

---

# Fatia 8 de nove — T043, T044, T045, T047, T049 e T050 (polimento, baselines e gates)

Estado abaixo verificado contra o código nesta árvore, HEAD `d8dbe14` em
`feat/v6-scope-and-settings`, árvore limpa antes desta sessão (confirmado por
`git status --short` — nada estava staged, nada modificado). **Escopo: T043,
T044, T045, T047, T049 e T050**, por instrução explícita do despacho. **T046
(aceitar as baselines visuais) e T048 (`make verify`) não são desta fatia** —
nenhuma baseline foi recapturada ou aceita aqui (`console-visual-accept` e
`tools.console_visual accept` não foram chamados nenhuma vez), `make verify`
não foi rodado, e os dois seguem `[ ]` em `tasks.md`. A implementação em si
(fases 1–10, T001–T042) não foi tocada nesta fatia — nenhum arquivo em
`console/src/**`, `gateway/**` ou `config/constants/**` foi alterado. O único
arquivo committable alterado é `console/visual/screens.json`.

## Tabela

| Peça | Estado | Detalhe |
|---|---|---|
| T043 — en/pt-BR: toda string nova nos dois idiomas; vocabulário canônico de estado não traduzido para outra palavra | FEITO | Ver "T043 — a varredura" abaixo. 20 chaves novas desta feature, todas presentes e consumidas nos dois arquivos; nenhuma órfã; as duas chaves removidas (`data.ingress.never`, `ingress.token.rotating`) sem nenhuma referência residual na árvore inteira; o vocabulário canônico de credencial (Not connected/Stored/Verified/Degraded/Failing ↔ Não conectada/Armazenada/Verificada/Degradada/Falhando) só é desenhado via `StatusChip` nas telas tocadas; nenhum marcador de português europeu nas strings novas. |
| T044 — a entrada órfã do painel de credencial | FEITO | `console/visual/screens.json:227-238` — entrada nova `integrations-panel-1440-light`, rota `/integrations/alertmanager`, `"status": "pending"`. Não havia o que "repointar": a entrada antiga tinha sido **apagada inteira**, não deixada apontando para `/integrations/slack` — ver "T044 — o que a arqueologia do git mostrou" abaixo. |
| T045 — `make console-visual` e descrever o que mudou | FEITO | Ver "T045 — a comparação real" abaixo. `console_gate build` limpo (exit 0), depois `console_gate visual`: **34 telas rodaram, 33 passaram, 1 falhou** — `machine-tokens-1440-light`, exatamente a divergência que o despacho já nomeou. As rotas que esta feature reconstruiu não rodam no compare — nomeado com a causa exata abaixo, não escondido. |
| T046 — aceitar as baselines visuais | Fora do escopo desta fatia | Do operador. Lista do que precisa revisão em "O que o operador precisa revisar e aceitar" abaixo. |
| T047 — acceptance spec inteiro, verde confirmado | FEITO | Duas rodadas completas nesta sessão, contra o build reconstruído em T045: **25 passed, 0 failed** as duas vezes, exit 0 as duas vezes. Ver "T047 — o verde" abaixo. |
| T048 — `make verify` / `make console-check` | Fora do escopo desta fatia | Do orquestrador; não roda verde ainda porque `tests/contract/console/test_console_visual_regression.py::test_the_untouched_baselines_still_match` falha em `machine-tokens-1440-light` — o mesmo achado que T045 reproduz diretamente. Não rodei `make verify` nesta fatia. |
| T049 — efeito no corpus sintético, medido | FEITO | Ver "T049 — o corpus, medido de verdade" abaixo. Corpus geral: **5/5 (100%)**, e o gate mecânico contra a baseline `release` devolve `corpus_version` byte-idêntico ao gravado e **"no regression beyond tolerance"**. A trilha Proxmox (separada) também foi rodada por diligência extra, com o alcance da leitura nomeado com honestidade — não é um gate automático numa chamada simples, então não recebe o mesmo veredito mecânico. |
| T050 — `controle.md` e `tasks.md` alinhados ao código | FEITO | Esta seção, e os seis checkboxes marcados no fim. |

## T043 — a varredura

**Delimitação do diff desta feature.** Esta branch carrega várias features em
sequência (a onda é executada sobre uma árvore compartilhada). Os commits
desta feature são `8b446c1..d8dbe14` (dez commits, confirmados por
`git log --oneline -10` batendo exatamente com a lista de tarefas da fase 2
em diante; o commit anterior, `a56e4f2`, fecha a feature 040). O diff de i18n
foi tirado desse intervalo:

```
git diff --stat 8b446c1~1..d8dbe14 -- console/src/i18n/en.ts console/src/i18n/pt-BR.ts
 console/src/i18n/en.ts    | 49 ++++++++++++++++++++++++++++++++++++++++-------
 console/src/i18n/pt-BR.ts | 38 +++++++++++++++++++++++++++++-------
```

**Vinte chaves novas, as duas nos dois arquivos**, confirmadas por presença
**e** por consumo (nenhuma órfã) via
`git ls-files -z -- 'console/src' | xargs -0 rg -n "<padrão>"`:

| Chave | `en.ts` | `pt-BR.ts` | Consumida em |
|---|---|---|---|
| `data.ingress.receiving` | `:179` "Receiving" | `:1558` "Recebendo" | `settings/alert-intake.tsx:606` |
| `data.ingress.ready` | `:180` "Ready — nothing arrived yet" | `:1559` "Pronta — nada chegou ainda" | `settings/alert-intake.tsx:594` |
| `data.ingress.week` | `:184` | `:1561` | `settings/alert-intake.tsx:619` |
| `data.ingress.copyUrl` | `:185` | `:1562` | `settings/alert-intake.tsx:474` |
| `data.ingress.receiverYaml` | `:186` | `:1563` | `settings/alert-intake.tsx:485` |
| `data.ingress.retired` | `:200` | `:1573` | `settings/alert-intake.tsx:734` |
| `data.chain.label` | `:209` | `:1582` | `settings/alert-intake.tsx:746` |
| `data.chain.intake.empty` | `:210` | `:1583` | `settings/alert-intake.tsx:297` |
| `data.chain.rule.empty` | `:211` | `:1584` | `settings/alert-intake.tsx:298` |
| `data.chain.action.empty` | `:212` | `:1585` | `settings/alert-intake.tsx:299` |
| `data.chain.destination.empty` | `:213` | `:1586` | `settings/alert-intake.tsx:300` |
| `catalogue.integrations.available.title` | `:1480` | `:1238` | `integration-catalogue.tsx:264` |
| `catalogue.integrations.panel.storedInVault` | `:1522` | `:1280` | `screens/integrations.tsx:514` |
| `catalogue.integrations.panel.testAgain` | `:1524` | `:1282` | `screens/integrations.tsx:516` |
| `catalogue.integrations.panel.replaceCredential` | `:1525` | `:1283` | `screens/integrations.tsx:519` |
| `catalogue.integrations.panel.cancel` | `:1528` | `:1286` | `screens/integrations.tsx:521` |
| `catalogue.integrations.panel.disconnect` | `:1529` | `:1287` | `screens/integrations.tsx:522` |
| `catalogue.integrations.panel.disconnect.consequence` | `:1530` | `:1288` | `screens/integrations.tsx:525` |
| `settings.machineTokens.filteredBy` | `:2104` | `:1915` | `settings/machine-tokens.tsx:158` |
| `settings.machineTokens.clearFilter` | `:2105` | `:1916` | `settings/machine-tokens.tsx:165` |

Cada linha acima foi verificada por leitura direta, não só pelo diff. Além
das vinte, quatro chaves **existentes** tiveram o **valor** trocado nos dois
idiomas em paralelo (`catalogue.integrations.summary`,
`.summary.suggested`, `.footer.gaps`,
`settings.schedulesDestinations.advanced.surfaces.title`) — as quatro
mudaram nos dois arquivos, nenhuma ficou para trás.

**As duas chaves removidas não deixaram resíduo.** `data.ingress.never` e
`ingress.token.rotating` foram removidas dos dois arquivos no mesmo commit;
varredura pela forma seguro contra estouro de argumento (a instrução do
despacho, confirmada: `rg -n "padrão" $(git ls-files)` estoura e reporta
"nada encontrado" nesta árvore — não usei essa forma):

```
git ls-files -z | xargs -0 rg -n "ingress\.never|token\.rotating"
```

Zero ocorrências em toda a árvore rastreada (a saída do `xargs` foi lida
diretamente — vazia — não o código de saída agregado, que mistura os códigos
de cada lote).

**O vocabulário canônico de estado da credencial não foi traduzido para outra
palavra em nenhuma tela tocada.** As cinco palavras vivem em
`console/src/i18n/en.ts:408-412` / `pt-BR.ts:438-442`
(`status.credential.*`) e são desenhadas **exclusivamente** por `StatusChip`
(`console/src/components/status.tsx:191-220`), que resolve qualquer grafia de
backend para uma das cinco via `credentialStatus()`
(`console/src/design/status.ts:163-165`) antes de desenhar. Confirmado por
leitura direta que as duas telas do catálogo usam esse caminho e nenhum
outro:

- `integration-catalogue.tsx:203-206` — cada card usa `<StatusChip
  status={item.health} />`.
- `integration-panel.tsx:297` — o painel usa `<StatusChip
  status={item.health} />` para o estado da integração, e mais duas vezes
  (`:421`, mais abaixo) para o veredito de "Test again", sempre pelo mesmo
  componente.
- `screens/integrations.tsx:254-255` usa `item.health !== 'unconfigured'` só
  para **particionar** a lista (lógica, não texto renderizado) — o texto
  visível continua vindo do `StatusChip`.

`alert-intake.tsx:617` usa `<Badge status={text(source, 'last_outcome')} />`
— um vocabulário **diferente** (resultado de entrega por payload —
aceito/recusado —, não o estado da credencial), e `Badge` é o componente que
este projeto já reserva para mostrar a grafia crua do backend quando ela é o
próprio dado (não uma tradução de estado). Não é uma violação do vocabulário
de credencial porque não é o mesmo eixo.

**Achado registrado, não corrigido: "guardada" na prosa do painel, ao lado de
"Armazenada" no chip.** As duas strings novas
`catalogue.integrations.panel.storedInVault` e `.disconnect.consequence`
(pt-BR) usam "guardada" ("Esta credencial está guardada no vault.") em vez
de "armazenada", que é a palavra do chip (`status.credential.stored` =
"Armazenada"). Investiguei se isso era uma tradução nova e inconsistente
introduzida por esta feature — não é: a nota de segurança **pré-existente**
do mesmo painel (`panel.security`, não tocada por esta feature) já mistura as
duas deliberadamente na mesma frase — "Guardada no vault... armazenada e
funcionando são estados diferentes" — e o catálogo pt-BR inteiro usa
"guardada"/"guardado" como o verbo de prosa para "estar no vault" em pelo
menos doze outras chaves não tocadas por esta feature
(`credential.stored`, `credential.saved`, `firstRun.integrations.connected`,
`catalogue.credential.absent`, etc. — `pt-BR.ts:74,78,140-141,1213-1218`
entre outras), reservando "Armazenada" especificamente para o chip. Esta
feature replicou um padrão já estabelecido em vez de inventar um novo; não
tratei isso como defeito.

**Nenhum marcador de português europeu** nas strings novas — varredura por
`ecrã`, `ficheiro`, `acção`, `activ`, `objectiv`, `contactar`, `a criar`, `a
editar`, `a atualizar` sobre o diff completo do pt-BR.ts: zero ocorrências.

**Nenhuma tela exibe o nome de permissão cru como mecanismo de confiança**
(FR-060, já resolvida em fatia anterior, reconfirmada aqui): `git ls-files -z
| xargs -0 rg -n "webhook\.deliver"` retorna dezenas de ocorrências, e todas
são backend (`platform/identity/permissions.py`, fixtures, OpenAPI), testes
que **afirmam a ausência** (`vocabulary-defaults.acceptance.spec.ts:377`
`.not.toContain('webhook.deliver')`; o próprio acceptance desta feature,
`:755`, descreve a alegação negativa que testa) ou um comentário de código
em `alert-intake.tsx:197` explicando a decisão de design. Nenhuma ocorrência
é texto renderizado.

## T044 — o que a arqueologia do git mostrou

O texto de `tasks.md` previa duas hipóteses para a entrada órfã: "repointar"
uma entrada existente, **ou** "registrá-la de novo... caso a 001 a tenha
removido junto com o vendor". A segunda é a que aconteceu. `git log -p
--follow -- console/visual/screens.json` mostra:

- `058aa91` ("feat: make the integrations catalogue browsable and say what
  each credential buys") **acrescentou** a entrada `integrations-panel-1440-light`,
  rota `/integrations/slack`, `status: "pending"`.
- `6d1ede6` ("feat: ship only the integrations an environment can validate"
  — o commit do corte da 001) **apagou essa entrada inteira** no mesmo diff
  que remove o pacote do vendor Slack, junto com o resto do catálogo
  reduzido a 15. `git merge-base --is-ancestor 6d1ede6 HEAD` confirma que
  esse commit é ancestral do HEAD desta sessão.

Ou seja: **por toda esta feature, até esta fatia, `screens.json` não carregava
nenhuma entrada para o painel de credencial** — não uma apontando para o
endereço errado, mas nenhuma. Nada disso é visível olhando só o arquivo atual
(que não tem "slack" em lugar nenhum); só a arqueologia do histórico mostra
por quê. Registrei essa descoberta aqui porque muda a ação: não havia o que
"repointar" — a tarefa era registrar a entrada de novo, do zero, no endereço
sobrevivente.

A entrada nova (`console/visual/screens.json:227-238`):

```json
{
  "id": "integrations-panel-1440-light",
  "route": "/integrations/alertmanager",
  "status": "pending",
  "viewport": 1440,
  "theme": "light",
  "accepted": {
    "against": null,
    "reason": "The credential panel, registered again at a surviving integration after the vendor cut removed both `/integrations/slack` and this entry along with it: alertmanager, verified in the dataset on purpose, so the capture shows the connected state and its three actions — test again, replace credential, disconnect — rather than an empty form with a disabled button. The panel itself is reviewed as a slide-over overlaid on the catalogue, never a block in the document's flow. Reviewed against the credential-panel mockup for layout, hierarchy, grouping and vocabulary. No committed baseline exists yet — this is a new capture and the first acceptance is a deliberate, reviewed one rather than something a gate should manufacture."
  },
  "pending_because": "Registered so the screen is not forgotten, and deliberately left out of the capture set until a person accepts its first baseline. Carrying it as baselined instead would fail the committed-baseline contract on every run, and — worse — each full gate run would regenerate the missing PNG as a real-looking capture nobody reviewed, which is how an unreviewed baseline gets committed by the next person who stages this directory. It leaves pending the moment someone captures it under review."
}
```

**Por que `alertmanager` e não outra integração sobrevivente**: é a única
que o mockup normativo desenha (`specs_v6/mockups/settings-v6.html`, seção
#m4), e a fatia 0 desta feature já a deixou `verified` no dataset de
propósito — confirmado lendo `integration-panel.tsx:261-263` (`connected =
item !== null && credentialStatus(item.health) !== 'not_connected'`) e
`:363-404` (o ramo `!showForm`, que é o que uma integração conectada
renderiza: nota de vault, e os três botões nomeados — nenhum formulário
vazio). Uma vez aceita sob revisão, a captura vai proteger exatamente essa
composição — o painel sobreposto ao catálogo, sem campo de credencial vazio,
com as três ações nomeadas — em vez de repetir o formulário write-only que
qualquer integração desconectada já mostra.

**Por que a razão não repete literalmente "instrução por campo, uma ação
primária única" do texto original de `tasks.md`**: aquele texto descrevia a
entrada antiga, que apontava para uma integração **sem** credencial (o
formulário write-only, com instrução por campo e "Save and test" como ação
primária única). Como `alertmanager` está `verified`, o que a captura
realmente mostra é o outro ramo do mesmo componente — o estado conectado,
com três ações nomeadas, não um formulário. Escrevi a razão para descrever o
que a captura de fato vai mostrar, porque uma razão que descreve pixels que
não estão lá é pior guia para quem revisa do que nenhuma razão.

## T045 — a comparação real

**Build reconstruído antes de comparar** (a armadilha nomeada pelo
despacho — `console_visual compare` não reconstrói sozinho):

```
uv run python -m tools.console_gate build
EXIT_CODE=0
```

**Comparação**:

```
uv run python -m tools.console_gate visual
EXIT_CODE=1

Running 34 tests using 1 worker
  ✓ 1..31  (todas as telas já baselined, sem machine-tokens)
  ✘ 32     machine-tokens-1440-light matches its baseline (1.3s)
  ✓ 33     models-providers-1440-light matches its baseline
  ✓ 34     notifications-1440-light matches its baseline
  1 failed, 33 passed (21.1s)
console gate: visual failed — a screen differs from its baseline — see the diff artefacts
```

**A única falha, com números reais**: `Expected an image 1440px by 1729px,
received 1440px by 1890px. 5694 pixels (ratio 0.01 of all image pixels) are
different.` — a página ficou 161px mais alta.

Abri as duas imagens (`test-results/screens-machine-tokens-1440-light-matches-its-baseline-visual/machine-tokens-1440-light-{actual,expected}.png`,
artefatos locais, não committed) para descrever a diferença de verdade em vez
de repetir só o número de pixels: a captura **esperada** (baseline antiga)
vai direto do grupo "scheduler" para o grupo "bootstrap". A captura **atual**
tem um grupo inteiro a mais entre os dois — "Alert delivery", chip "In use",
"1 token", escopo "Webhook Deliver", "Last used: 12 minutes ago",
"Authenticates inbound Alertmanager webhook deliveries." Esse é exatamente o
token de entrega que a fatia 0 desta feature acrescentou ao dataset
compartilhado (T003, `identity_records()`), e é a causa visível dos 161px e
dos 5694 pixels — confirmado por leitura visual direta, não só pela
aritmética das dimensões. O banner de filtro que a fatia 6b acrescentou
(`data-testid="machine-tokens-filter"`, `settings.machineTokens.filteredBy`)
**não aparece em nenhuma das duas imagens** — ele só desenha quando a rota
chega com `?scope=…`, e esta baseline captura o endereço puro
`/settings/machine-tokens`, sem esse parâmetro. As duas mudanças tocaram o
mesmo commit (`c5afb96`) e o mesmo arquivo, mas só uma delas — o grupo de
token novo — produz diferença de pixel nesta captura específica; a outra é
real mas invisível aqui porque a rota que a baseline usa não a exercita.
Isso é exatamente o que o despacho já previu, com os números medidos que
faltavam.

**As rotas que esta feature reconstruiu não aparecem na lista acima —
nomeado, não escondido.** `console/tests/visual/screens.spec.ts:52` gera um
teste do Playwright **só** para `each.status === 'baselined'`:

```ts
for (const screen of registry().screens.filter((each) => each.status === 'baselined')) {
```

Cinco entradas relevantes a esta feature continuam `"status": "pending"` e
por isso **não rodam** em `console-visual` (nem passam, nem falham — não
existem como teste nesta suíte):

| id | rota | por quê está pending |
|---|---|---|
| `integrations-1440-light` | `/integrations` | reconstrução do catálogo desta feature; aguardando T046 |
| `integrations-panel-1440-light` | `/integrations/alertmanager` | registrada agora mesmo por T044; primeira captura, nunca existiu antes |
| `signals-1440-light` | `/settings/alert-intake` | reconstrução do intake desta feature; aguardando T046 |
| `signals-schedules-1440-light` | `/settings/schedules-destinations` | pendente **antes** desta feature (consolidação de duas entradas numa página só) — ver nota abaixo |
| `signals-destinations-1440-light` | `/settings/schedules-destinations` | mesma razão pré-existente que a linha acima |

Isso é uma correção factual ao enquadramento do despacho, não uma
contradição dele: o despacho descreveu essas duas rotas como "esperadas
para divergir" porque mudaram de propósito — e mudaram, extensivamente — mas
o mecanismo de `console-visual` (comparar) não as alcança enquanto
`status` for `"pending"`; só `console-visual-accept` (T046, não desta fatia)
as fotografa pela primeira vez. As duas frases são compatíveis: a mudança é
real e grande, e a comparação automática simplesmente não tem baseline nenhum
contra o qual testá-la — daí ela não poder "falhar" nem "passar" em
`console-visual`, só ficar pendente de revisão humana.

**Nota lateral sobre `/settings/schedules-destinations`**: as duas entradas
pendentes desse endereço já estavam pendentes antes desta feature (por causa
de uma consolidação de duas telas antigas numa página só, decisão que o
`pending_because` de cada uma já atribui à revisão, não a uma feature). Esta
feature tocou esse endereço uma vez (T037: renomeou "report destinations"
para "report recipients" numa seção avançada, provavelmente fechada por
padrão na captura). Não é uma das "duas rotas" que o despacho nomeia para
T046, e não tentei ampliar esse escopo — nomeado aqui só para quem revisar
essas duas entradas mais tarde não se surpreender com o texto mudado numa
seção avançada.

## T047 — o verde

Duas rodadas completas, contra o mesmo build que T045 acabou de reconstruir
(nenhum rebuild extra necessário — nada em `console/src/**` mudou entre
T045 e T047 nesta sessão):

```
uv run python -m tools.console_e2e run -- tests/e2e/050-integrations-slideover-intake.acceptance.spec.ts
Running 25 tests using 1 worker
25 passed (7.7s)
EXIT_CODE=0
```

```
(segunda rodada, mesmo comando)
Running 25 tests using 1 worker
25 passed (7.8s)
EXIT_CODE=0
```

27 ocorrências de "✓" no log bruto da primeira rodada — as 25 dos testes mais
duas de mensagens de inicialização do servidor (`✓ Ready`, `✓ Running
next.config`), não de testes; **zero** ocorrências de "✘" nas duas rodadas.
Bate exatamente com o que o despacho já tinha como confirmado pelo
orquestrador (25 passed / 0 failed) — reconfirmado aqui, nesta sessão, contra
código de verdade, não aceito de segunda mão.

A suíte transversal (`transversal-rules.spec.ts`) **não foi rerrodada** nesta
fatia — não está na lista de tarefas desta fatia (T040, fatia 7, já a rodou
duas vezes com 25 passed / 7 skipped / 0 failed), e nenhum arquivo capaz de
afetá-la foi tocado aqui (só `console/visual/screens.json`, que essa suíte
não lê). Reportado como não rodado, não como "verde por suposição".

## T049 — o corpus, medido de verdade

**Achando a ferramenta certa.** `make test-synthetic` (`python -m
tests.harness`) roda "o corpus, offline" — a suíte geral, sem credenciais,
sem tokens, contra transcritos gravados. `make evaluate` (`python -m
tests.harness.regression.ci --baseline release`) é a mesma suíte, pontuada
em cinco eixos e **comparada mecanicamente** contra uma baseline gravada —
também offline por padrão, conforme o próprio docstring do módulo
(`tests/harness/regression/ci.py:8-9`: "Offline by default, and that is what
makes the gate affordable enough to run at all"). Rodei os dois.

**O corpus geral, cru**:

```
PYTHONPATH="$(pwd)" uv run python -m tests.harness
EXIT_CODE=0

level  solve rate  attempts  definition
1      100%        1         A single obvious cause with corroborating evidence.
2      100%        2         One planted confounder that must be explicitly ruled out.
3      100%        1         Several plausible causes requiring evidence to discriminate.
4      100%        1         The most prominent signal is misleading; the true cause is secondary.

5/5 attempts passed (100%) in 0.1s
```

**O gate mecânico contra a baseline gravada `release`** — a medição que
realmente prova "sem efeito", porque compara contra um ponto gravado antes
desta feature existir, em vez de só reportar um número solto:

```
PYTHONPATH="$(pwd)" uv run python -m tests.harness.regression.ci --baseline release
EXIT_CODE=0

working tree
5/5 attempts passed (100%) in 0.1s
corpus 65b8979746902297

axis          pass rate   attempts  spread
accuracy      100%        5         ±0.00
evidence      100%        5         ±0.00
adversarial   100%        4         ±0.00
trajectory    100%        5         ±0.00
cost          100%        5         ±0.00

measured against release, running working tree
no regression beyond tolerance
```

O fingerprint `corpus 65b8979746902297` que este comando imprimiu **bate,
byte a byte**, com o `corpus_version` gravado dentro de
`tests/synthetic/baselines/release.baseline.json` (lido diretamente, não
tomado da palavra do comando):

```
python3 -c "import json; print(json.load(open('tests/synthetic/baselines/release.baseline.json'))['corpus_version'])"
65b8979746902297
```

Essa baseline foi gravada em `2026-08-17T04:23:42+00:00`, com a nota "Escopo
validável: catálogo reduzido a 15 integrações; cenários dependentes de
vendors removidos saíram do corpus" — ou seja, gravada **depois** do corte
da 001 e **antes** desta feature (050) existir. O mecanismo de
`tests/harness/regression/baseline.py` (`corpus_version`, comentado no
próprio arquivo: "a scenario added, retired, or re-keyed moves the version,
and the comparison refuses rather than reporting a fixture change as an
agent regression") **recusaria** a comparação se o corpus tivesse mudado de
forma — ele não recusou; comparou de verdade, achou os cinco eixos em 100%,
e disse "no regression beyond tolerance". Este é o resultado a registrar
para T049: **efeito medido, zero**, com prova mecânica (o fingerprint
idêntico) e não só a minha leitura do log.

**A trilha Proxmox, rodada por diligência extra — escopo da leitura nomeado
com honestidade.** `tests/synthetic/proxmox/` é uma corpus **separada**,
pontuada por um módulo próprio (`tests.harness.proxmox`, alvo `make
test-proxmox-scenarios`), não pelo `tests.harness`/`tests.harness.regression.ci`
usados acima — o próprio comentário do `Makefile:95-99` a chama de "the
hypervisor half" e diz que ela roda "from recorded API responses with no
cluster", o que a torna igualmente offline e barata de rodar aqui:

```
PYTHONPATH="$(pwd)" uv run python -m tests.harness.proxmox
EXIT_CODE=0
72/104 scored runs passed (69.2%) in 0.36s
  hosted-frontier/full: 26/26 (100.0%)
  hosted-frontier/no-memory: 23/26 (88.5%)
  self-hosted-compact/full: 15/26 (57.7%)
  self-hosted-compact/no-memory: 8/26 (30.8%)
```

Diferente da chamada acima, **esta não compara contra nenhuma baseline
gravada numa chamada simples** — conferido varrendo a saída inteira (312
linhas) por "baseline", "regress" e "gate": zero ocorrências. O que ela
reporta são pontuações de julgamento adversarial (o texto de cada "FAILED"
descreve uma armadilha de propósito — "took the bait on…" — em cenários que
avaliam se o agente resiste a uma ação arriscada, não um teste
passa/não-passa comum), então um número abaixo de 100% aqui não é por si só
evidência de regressão — é a forma como esta trilha específica já se
comporta. Não encontrei, nesta sessão, um ponto gravado para comparar esse
69,2% especificamente contra um "antes desta feature" — por isso **não**
estou registrando um veredito "sem regressão" para esta trilha do jeito que
registrei para o corpus geral acima. O que posso afirmar, com evidência: (1)
ela roda inteiramente offline, em 0,36s, sem chamada de rede — não é um
artefato de ambiente/credencial faltando; (2)

```
grep -rn "gateway\.http\.routes\|config\.constants\.surfaces\|integration-panel\|integration-catalogue" tests/harness --include="*.py" -l
```

não retorna nenhum arquivo — nenhum módulo de `tests/harness/` (onde tanto o
corpus geral quanto a trilha Proxmox moram) importa as rotas do gateway que
esta feature tocou, a constante de `config/constants/surfaces.py` que a
fatia 4 mexeu, ou os dois componentes do painel/catálogo pelo nome do
arquivo. Não é uma prova exaustiva de que nada nesta feature poderia afetar
a trilha Proxmox — é uma varredura por nome, restrita ao diretório do
harness, sobre os módulos que esta feature especificamente tocou. Registrado
como "rodei, e essa varredura por nome não encontra caminho para esta
feature afetar isto" — mais honesto do que forçar um "sem efeito, medido"
que eu não tenho um número anterior para comparar.

## Gates rodados nesta fatia — reais, com resultado visto por mim

| Gate | Comando | Resultado |
|---|---|---|
| `console_gate build` | `uv run python -m tools.console_gate build` | limpo, exit 0 |
| `console_gate visual` (compare) | `uv run python -m tools.console_gate visual` | **34 rodaram, 33 passaram, 1 falhou** — `machine-tokens-1440-light`, pré-existente, descrito em T045 acima |
| `console_gate format-check` | `uv run python -m tools.console_gate format-check` | limpo — "All matched files use Prettier code style!" (a única mudança de código, `screens.json`, já batia com o estilo do arquivo) |
| `console_gate lint` | `uv run python -m tools.console_gate lint` | limpo — `eslint . && check-css-literals.mjs` sem saída, exit 0 |
| `console_gate typecheck` | `uv run python -m tools.console_gate typecheck` | limpo — `tsc --noEmit` sem saída |
| Acceptance spec desta feature | `uv run python -m tools.console_e2e run -- tests/e2e/050-integrations-slideover-intake.acceptance.spec.ts` | **25 passed, 0 failed**, duas vezes |
| Dois contratos Python que leem `screens.json` | `uv run pytest tests/contract/console/test_console_design_system.py::test_every_design_reference_this_feature_owns_is_baselined tests/contract/console/test_console_design_system.py::test_the_gallery_is_captured_at_every_declared_width_in_both_themes -v` | **2 passed** em 0.03s |
| Corpus sintético geral | `PYTHONPATH="$(pwd)" uv run python -m tests.harness` | **5/5 attempts passed (100%)** |
| Gate mecânico do corpus contra a baseline `release` | `PYTHONPATH="$(pwd)" uv run python -m tests.harness.regression.ci --baseline release` | **"no regression beyond tolerance"** — `corpus 65b8979746902297`, idêntico ao `corpus_version` gravado |
| Trilha Proxmox (extra, sem gate automático numa chamada simples) | `PYTHONPATH="$(pwd)" uv run python -m tests.harness.proxmox` | 72/104 (69.2%) — não é um veredito de regressão; ver a leitura completa em T049 |

**Não rodados nesta fatia, por estarem fora do escopo que o despacho
nomeou ou por serem desproporcionais à mudança real**: `make verify` e
`console-check` (T048, do orquestrador); `make console-visual-accept` /
`tools.console_visual accept` (T046, do operador — a fronteira desta fatia,
nunca cruzada); a suíte transversal (`transversal-rules.spec.ts`, já
confirmada duas vezes pela fatia 7, nada aqui poderia tê-la afetado);
`console_gate test` (suíte de unidade + cobertura completa — a única mudança
de código desta fatia é um arquivo de dados que nenhum teste de unidade lê,
e os dois contratos Python que o leem diretamente foram rodados isolados,
acima); qualquer gate Python além dos dois contratos nomeados (nenhum arquivo
Python foi tocado nesta fatia — `check-constants`, `check-imports`,
`check-protocols`, `check-deps`, `ruff`, `mypy` não têm superfície nova para
verificar).

## O que o operador precisa revisar e aceitar

Nada disto foi feito nesta fatia — é a lista para T046:

1. **`machine-tokens-1440-light`** — stale, causa visualmente confirmada
   nesta fatia (o grupo de token "Alert delivery" que a fatia 0 acrescentou
   ao dataset compartilhado). Não é uma das duas rotas desta feature, mas o
   despacho pediu para nomear — nomeado.
2. **`/integrations` — duas entradas**: `integrations-1440-light` (o
   catálogo em si — sem paginação, busca no topo, seção "Available",
   rodapé novo) e a nova `integrations-panel-1440-light` (o painel de
   credencial sobre `alertmanager`, a primeira captura já registrada para
   este endereço — nunca existiu antes desta fatia). As duas precisam de
   captura deliberada e revisão de imagem.
3. **`/settings/alert-intake`** (`signals-1440-light`) — reconstrução
   substancial: três fontes reais, chips exatos, bloco YAML do Alertmanager,
   linha de confiança nomeando o token, cadeia de quatro nós.
4. **Nota lateral, não uma das duas rotas nomeadas**: as duas entradas de
   `/settings/schedules-destinations` (`signals-schedules-1440-light`,
   `signals-destinations-1440-light`) já estavam pendentes antes desta
   feature por uma consolidação que a revisão ainda deve fazer (duas
   entradas, um endereço só); esta feature acrescentou uma mudança de texto
   pequena (T037) numa seção avançada desse mesmo endereço. Nomeado para não
   surpreender quem revisar essas duas depois.

## T050 — este arquivo, e `tasks.md`

`tasks.md`: marquei **T043, T044, T045, T047, T049 e T050** como `[x]`.
**T046 e T048 permanecem `[ ]`** — não são desta fatia, por instrução
explícita. Nenhuma outra linha foi tocada.

## O que fica pendente, nomeado, não escondido

1. **T046 inteira** — as três capturas pendentes nomeadas acima, e a
   baseline `machine-tokens-1440-light`, esperando revisão humana e
   `console-visual-accept`. Não tentei antecipar nenhuma delas.
2. **T048 (`make verify`, `make console-check`)** — não roda verde até T046
   fechar; não rodei nenhum dos dois nesta fatia.
3. **A suíte transversal não foi rerrodada nesta fatia** — nomeado na seção
   de T047 acima; já confirmada duas vezes pela fatia 7, e nada nesta fatia
   poderia tê-la afetado (só `screens.json` mudou).
4. **`console_gate test` (suíte de unidade + cobertura) não foi rodado nesta
   fatia** — a única mudança de código desta fatia é `console/visual/screens.json`,
   um arquivo de dados que nenhum teste de unidade lê. O que protege essa
   mudança é a suíte visual (T045, já rodada) e os dois contratos Python que
   leem `screens.json` diretamente, que rodei isolados, sem lock parado
   (`console/.toolchain/tree-writing-suite.lock` conferido ausente antes):

   ```
   uv run pytest tests/contract/console/test_console_design_system.py::test_every_design_reference_this_feature_owns_is_baselined tests/contract/console/test_console_design_system.py::test_the_gallery_is_captured_at_every_declared_width_in_both_themes -v
   2 passed in 0.03s
   ```

   Nenhum dos dois lê a entrada nova (`test_every_design_reference...` olha só
   `mockups`; `test_the_gallery_is_captured...` filtra por `route ==
   "/gallery"`), e nenhum quebrou. Rodar a suíte de 2500+ testes de unidade
   inteira por uma mudança de dados que nenhum deles exercita pareceu
   desproporcional ao ganho de informação; nomeado aqui em vez de
   simplesmente omitido.
5. **A observação de honestidade sobre a fatia 4 (test-first invertido)** —
   já estava documentada com clareza na própria seção da fatia 4 ("T012/T015
   — vermelho confirmado, seis alegações genuinamente novas") antes desta
   fatia começar. Reli essa seção nesta sessão para confirmar que a
   inversão e a reconstrução retroativa da prova estão ditas em português
   claro, sem eufemismo — estão. Não precisei editá-la.
