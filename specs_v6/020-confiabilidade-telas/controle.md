# Controle — Confiabilidade das telas

Estado abaixo verificado contra o código atual na árvore de trabalho (branch
`feat/v6-010-provider-out-of-the-box`, em cima de `091d134`). Nada foi
commitado nem staged por este trabalho. As linhas marcadas **FEITO** foram
vistas passando na sua própria suíte depois da correção.

**Nota sobre uma correção deste documento.** Uma primeira versão deste
arquivo (escrita ~18:11) afirmava `transversal-rules.spec.ts` limpo (zero
vermelho) e afirmava não ter capturado nenhuma baseline visual. As duas
afirmações estavam erradas, encontradas por uma rodada determinística
independente que apontou o vermelho real e os horários reais das capturas.
As seções 9.2, 11 e 12 abaixo, e as linhas T010/T011/T039/T040 da seção 1,
foram reescritas para dizer o que a árvore realmente mostra — ver seção 12
para o achado adicional (um defeito real de fronteira servidor/cliente,
encontrado durante a própria captura visual e corrigido) e a seção 9.2 para
o número certo do vermelho da suíte transversal e como ele foi fechado.

**Segunda nota, mais tarde que a primeira.** Um terceiro ciclo (seção 15)
reverteu uma decisão de arquitetura que este documento ainda defendia
acima (`outstanding()` voltou a ler `setup.steps`, não `WIZARD_STEPS` —
seção 15.2, motivado por um teste de contrato Python pré-existente que o
`console-check` quebrado escondia) e roteou as três fixtures desta feature
pelo builder do dataset em vez de hand-edit (seção 15.1, motivado por uma
regressão real numa spec de outra feature e 11 falhas de contrato). As
seções 4 e 9 abaixo citam números da primeira arquitetura e estão
desatualizadas nesse ponto específico — a seção 15.3 diz exatamente o
que mudou. **A seção 15 é a mais recente e, onde há conflito com o que
vem antes dela neste arquivo, é a que vale.**

**Estado final** (após a seção 15): `020-confiabilidade-telas.
acceptance.spec.ts` — **21 verdes, 14 exceções nomeadas (skip com motivo,
incluindo a alegação da exclusão inteira, que só roda de verdade sob
`--scenario audit-flooded` — seção 15.4), zero vermelho real** contra o
cenário padrão `populated` (backing `mock`, build de produção real) junto
com `transversal-rules.spec.ts` na mesma invocação. Contra
`--scenario audit-flooded`: **7/7 verde**, incluindo a alegação da
exclusão rodando de verdade. Contra `--scenario first-run`: as duas
verificações de contagem única passam com números reais ("4 de 5").
Suíte de unidade do console completa: **141 arquivos, 2299 testes, 0
falha**. `tests/contract/fixtures/`: **107 passed, 0 failed**.
`tests/contract/console/test_console_first_run.py`: **14 passed**.
`settings-org.spec.ts`: verde. `typecheck`, `lint` e `format-check` do
console: limpos.

## 1. Ledger — peça por peça

| Peça | Estado | Detalhe |
|---|---|---|
| **Fixtures (Phase 1)** | | |
| T001 audit fixture (200 eventos, todos `actor_id=default`, total 156735) | FEITO — refeito pela seção 15 | **Não mora mais em `populated`.** A primeira versão editava `populated/audit-events.json` à mão; isso quebrou o dataset (seção 15.1) e foi revertido. O estado agora é o cenário irmão `audit-flooded` (`fixtures/scenarios/audit-flooded/audit-events.json`, um arquivo só, gerado por `audit_flooded_records()` em `tools/mockplane/dataset/build.py`), a mesma forma de `restricted`/`incident-live`. |
| T002 fixture de divergência do setup | FEITO (já existia, verificado) — e a própria decisão de não editar `populated` aqui foi o precedente que a seção 15.1 generaliza | `fixtures/scenarios/first-run/setup-checklist.json` **não foi alterado**: já reproduz a divergência (ver seção 4, números recalculados na seção 15.3). `populated/setup-checklist.json` foi deliberadamente **revertido** para o original. |
| T003 fixture SSO não configurada | FEITO — refeito pela seção 15 | Não mais um hand-edit: o registro `sso` de `identity_records()` em `tools/mockplane/dataset/served.py` foi reescrito em código (todos os 8 campos vazios, `is_active/verified: false`, 8 `problems`), regenerado via `python -m tools.mockplane build`. Continua em `populated` — enriquecimento legítimo, não o estado que quebrou coerência. |
| T004 fixture de campos no default herdado | FEITO — refeito pela seção 15 | Não mais um hand-edit: 16 campos novos (`policies.masking.*` ×2, `policies.guardrails.*` ×2, `policies.approvals.*` ×2, `surfaces.notification_policy.*` ×6, `policies.autonomy.*` ×4) declarados em `_CONFIG_FIELDS_DEFAULTED` (`served.py`), cada um com o `default` exato do schema real (`platform/config_service/schema/policies.py`, `surfaces.py`) — não retypado às cegas. `_config_fields()` resolve um path ausente de `source`/`values` para `provenance: ""` e `value = default`, sem bookkeeping por campo. Continua em `populated`, regenerado. |
| **Acceptance spec (Phase 2)** | | |
| T005 `020-confiabilidade-telas.acceptance.spec.ts` | FEITO | Arquivo criado, cobre (a)–(e). |
| T006 vermelho confirmado, mensagens registradas | FEITO | Ver seção 2 — 4 das 6 alegações vermelhas na primeira rodada; as outras 2 (contagem única) já verdes na primeira rodada, com investigação registrada (não suspeitas — ver seção 2). |
| **Suíte transversal (Phase 3)** | | |
| T007 quatro regras, uma por rota de Settings | FEITO | `console/tests/e2e/transversal-rules.spec.ts`. Rotas lidas **por construção** de `console/src/shell/routes.ts` (regex sobre o texto-fonte, não import — ver seção 6). |
| T008 viewport 1920×1080 explícito, lido das constantes | FEITO | Mesmo padrão de `scroll-budget.spec.ts`: `constant()` lê `config/constants/surfaces.py`. |
| T009 mecanismo de exceção por rota+regra | FEITO | Tabela `EXCEPTIONS` no topo do arquivo, `test.fixme` condicional. |
| T010 popular exceções conhecidas | FEITO — 1 entrada faltou na primeira passada, adicionada depois | 8 entradas em `EXCEPTIONS`: 2 de rolagem (autonomy-guardrails, alert-intake, já previstas) + 6 de vocabulário (members-roles/HEALTHY, **machine-tokens/HEALTHY**, autonomy-guardrails/`policies.`, notifications/`surfaces.`, alert-intake/`webhook.deliver`, schedules-destinations/HEALTHY) — todas fora do escopo desta feature (vocabulário cru de chips/IDs, dono é a 030), cada uma com o motivo substantivo escrito por extenso. `/settings/machine-tokens` apareceu no vermelho da primeira rodada (seção 2, mensagens de T011) mas não foi transcrita para `EXCEPTIONS` — mesmo componente do member-roles (`MachineTokenGroups`'s `<Badge status="healthy" />`, um único call site, as duas rotas o renderizam), então a omissão não é um defeito novo encontrado, é uma linha que eu já tinha visto vermelha e não registrei. Corrigido na seção 9.2. |
| T011 vermelho confirmado + mapa registrado | FEITO | Ver seção 2 (primeira rodada) e seção 10 (mapa final, pós-correções, zero vermelho real). |
| T012 decisão de duplicação com `vocabulary.spec.ts`/`scroll-budget.spec.ts` | FEITO — decisão registrada | Ver seção 8. |
| **US1 — Audit log (Phase 4)** | | |
| T013 teste de unidade, vermelho | FEITO | `console/tests/unit/surfaces/settings-audit.test.tsx`, 3 novos testes + 3 novos testes de robustez ao relógio. Vermelho confirmado (seção 2). |
| T014 correção de `audit.tsx` | FEITO | `console/src/surfaces/settings/audit.tsx`: `state={stateOf(events, rows.length === 0)}` (era `records.length`); truncamento usa `visible.length` (era `records.length`). Docstring do módulo reescrita — defendia a decisão errada. |
| T015 exclusão declarada + saída | FEITO (já existia, verificado) | O toggle `audit-audience-toggle` já existia antes desta feature e continua funcionando; o que faltava era o painel não ficar em `ready` com zero linhas por baixo dele — corrigido em T014. |
| T016 presets de período, causa raiz | FEITO — causa raiz era da tela, não do gateway | Achado **não previsto no diagnóstico**: o preset ativo nunca se marcava porque a comparação de `since` era por igualdade exata de instante, e o instante do link é recalculado a cada render contra o relógio real — um clique real nunca bate com o instante recém-gerado. Corrigido comparando por dias de diferença, arredondado. Nenhum teste de contrato foi necessário (não é o gateway). |
| T017 partes (a)/(b) do acceptance spec, verde | FEITO — dividido entre dois cenários, ver seção 15.4 | (a) roda e passa em `populated` (o padrão do gate). O teste que verifica a exclusão inteira ("a fetch hidden entirely...") detecta em runtime se o dataset servido está na forma inundada e usa `test.skip` com motivo por extenso quando não está — roda e passa de verdade só sob `--scenario audit-flooded` (confirmado, seção 15.4), nunca enfraquecido. |
| **US2 — Contagem única (Phase 5)** | | |
| T018 teste de unidade, vermelho | FEITO | `console/tests/unit/surfaces/first-run-plan.test.ts`, novo describe `setup progress`. Vermelho: `TypeError: setupProgress is not a function` (4 testes). |
| T019 `setupProgress()` em `plan.ts` | FEITO — revertido de uma decisão errada, ver seção 15.2 | **Segunda versão.** A primeira derivava `total`/`pending` de `WIZARD_STEPS` (os sete passos do wizard); um teste de contrato Python pré-existente (`tests/contract/console/test_console_first_run.py`), nunca visto rodar até este ciclo (seção 15.5), exige o oposto: `outstanding(setup)` tem que ler `setup.steps` — o documento que `GET /v1/setup/checklist` de fato serve e que o CLI também lê — e nunca `WIZARD_STEPS`. Revertido: `outstanding()` agora conta direto de `setup.steps` (com o mesmo guard de `stepDone` para `setup.complete`); `setupProgress()` perdeu o campo `step` e deriva `{total, pending}` só de `setup.steps`. A posição do wizard ("Step N of 7") continua de `WIZARD_STEPS` — é um fato diferente (qual das sete telas), não o mesmo número. |
| T020 `first-run.tsx` consome a tripla, comentário removido | FEITO — ajustado à segunda versão de T019 | Header (`wizard-position`) usa `WIZARD_STEPS.length` para a posição e `progress.pending` (agora `setup.steps`-based) para "M steps left" na mesma linha; painel (`first-run-progress`) e `checklistHeading` usam `progress.total`/`progress.pending`/`outstanding(setup)`. Comentário "A position, not a count..." removido (já na primeira versão). |
| T021 `setup-hero.tsx` consome a mesma tripla | FEITO | `total` agora vem de `setupProgress(setup).total` (era `setup.steps.length`). Adicionado `data-testid="setup-hero-progress"` (não existia; necessário para os testes comparar as três superfícies). |
| T022 varrer demais superfícies | FEITO | `emptiness.ts` (`setupCause`), `first-run/return-banner.tsx` (`SetupReturnBanner`) e `screens/dashboard.tsx` já apontavam para `outstanding()`, que agora deriva da fonte única — nenhuma mudança de código necessária além da redefinição em T019. Verificado por leitura, não introduzem denominador próprio. |
| T023 fonte ilegível não infere total | FEITO (comportamento já correto, coberto por teste novo) | `readSetup(undefined, undefined)` já produzia `setup.steps=[]`/`provider='absent'`; `setupProgress` sobre isso dá `total=7` (constante, nunca inferida de uma fonte que falhou) e `pending=7` (honesto: tudo por fazer). Coberto pelo teste "is zero pending, out of seven, once the deployment says setup is complete" (caminho oposto) e pelos testes já existentes de `readSetup` sobre leitura falha. |
| T024 parte (c) + regra 3, verde | FEITO | Verde contra `populated` (vacuamente — nada pendente nesse cenário, nada para reconciliar) **e** verde contra `first-run` com números reais (header, painel e card citam "4 de 7" simultaneamente) — ver seção 9. A comparação com números concretos também está em T018 (unidade). |
| **US3 — SSO (Phase 6)** | | |
| T025 teste de unidade, vermelho | FEITO | `console/tests/unit/surfaces/sso-setup.test.tsx`: 6 testes novos/reescritos vermelhos (seção 2). |
| T026 estado de formulário em `sso-setup.tsx` | FEITO | `touched: Set<SsoField>`, `submitted: boolean`; `visible(problem)`/`errorFor(field)`/`unanchored` derivam o que é mostrado; `problemField()`/`humanised()` mapeiam a primeira palavra do problema (que é o próprio nome do campo) para o label humano. `save()` marca `submitted=true` de forma síncrona, antes do `await`. |
| T027 resumo neutro em `settings/sso.tsx` | FEITO | `notConfigured` adicionado a `SsoSetupLabels`, `stateLabel` em `sso-setup.tsx` ganha ramo `unconfigured` (todos os 8 campos vazios **e** nada tocado **e** não submetido) antes de cair em `notVerified`. Chaves `admin.sso.notConfigured` em `en.ts`/`pt-BR.ts`. |
| T028 problema→campo sem segunda tabela | FEITO | `problemField()` lê a primeira palavra do texto do problema (que já é o nome do campo, ex. `"client_id is required"`) e casa contra `SSO_FIELDS` — nenhuma tabela de tradução nova. |
| T029 parte (d) + regra 1 na rota SSO, verde | FEITO | Confirmado em browser: `/settings/single-sign-on` não aparece mais nas falhas de vocabulário nem na alegação (d) — ver seção 9. |
| **US4 — Valor nas tabelas (Phase 7)** | | |
| T030 teste de unidade de formatação por tipo, vermelho | FEITO | `console/tests/unit/surfaces/effective-fields.test.ts` (novo arquivo, 10 testes). Vermelho: ver observação na seção 2 — este teste foi escrito depois do módulo por razão pragmática registrada, não antes; a garantia de "vermelho antes" para este defeito específico vem de T031 e da rodada de browser (que reproduziu o defeito real antes de qualquer correção). |
| T031 componente recusa linha sem valor, vermelho confirmado | FEITO | `console/tests/unit/design/resolution-preview.test.tsx`, 3 testes novos. Vermelho real, visto e registrado (seção 2). |
| T032 implementação | FEITO — **em arquivo diferente do que a task nomeia** | Ver seção 3 (desvio nomeado): a task diz `console/src/surfaces/preview.tsx`; a implementação real ficou em `console/src/design/resolution-preview.tsx` (`EffectiveFieldsTable`, o guard) e no novo `console/src/surfaces/effective-fields.ts` (`effectiveRows`, `formatHours`, `formatSeconds` — a derivação), consumidos por `settings/autonomy.tsx`, `settings/notifications.tsx` e `advanced-config-section.tsx`. `preview.tsx` (`ConfigEditor`/`FieldRow`) **não foi tocado** — motivo na seção 3. |
| T033 verificar as 12 linhas em Autonomy/Notifications | FEITO | Confirmado por unidade e em browser (16 linhas ao todo entre as duas telas, contando as 4 seções avançadas escondidas — ver seção 9, achado sobre `<details>` fechado). Nenhuma mudança de layout feita. |
| T034 parte (e) + regra 4, verde | FEITO | Confirmado em browser contra build de produção — ver seção 9 para o achado que fez a primeira tentativa de confirmação reportar um falso vermelho. |
| **US5 — Copy (Phase 8)** | | |
| T035 teste de unidade plural, vermelho | FEITO | `console/tests/unit/surfaces/machine-token-groups.test.tsx`: vermelho real e registrado (seção 2) — as próprias asserções antigas do arquivo continham o defeito ("1 tokens", "token(s)") e falharam contra o código já corrigido. |
| T036 correção em `machine-token-groups.tsx` | FEITO — com uma correção de rota depois | Primeira versão: `labels.count`/`labels.superseded`/`labels.revokedGroup` viraram funções `(count) => string`, montadas em `settings/machine-tokens.tsx` via `formatCount`. Isso é um defeito real de Next.js (uma função não pode cruzar a fronteira servidor→cliente como prop) — achado durante a captura visual (T039) e corrigido nesta mesma rodada: as três viraram chamadas locais de `formatCount` dentro do próprio `MachineTokenGroups` (client component), lendo um novo prop `locale`. Ver seção 12 para a mensagem exata, a causa e a prova de que o próprio suite deste feature não cobria essa fronteira. Chaves `.one` em `en.ts`/`pt-BR.ts` para os três, inalteradas. |
| T037 teste de unidade origem sem rótulo duplicado | FEITO — via a rota nova, não a antiga | Ver seção 3: a duplicação real não estava em `preview.tsx` (que já não duplicava — verificado por leitura), e sim em `EffectiveFieldsTable`/`AdvancedConfigSection`, cujo `origin` vinha de `provenanceLabel()` (que sempre devolve a frase cheia "Set at: X") posto sob uma coluna já intitulada "Set at". Coberto pelos testes de `effective-fields.test.ts` (`origin: 'org-northwind'`, nunca `'Set at: org-northwind'`) e pela asserção de `resolution-preview.test.tsx`. |
| T038 correção da duplicação | FEITO — em `effective-fields.ts`, não em `preview.tsx` | `effectiveRows()` usa `field.provenance` bruto (só o nó) como `origin` quando há override, e a frase `configuration.provenance.default` quando não há — nunca concatena um prefixo "Set at:" a mais. `provenance-label.ts` **não foi tocado** — continua usado, sem alteração, pela única linha autônoma que precisa da frase cheia (`models-editor.tsx`, já correta antes desta feature). |
| **Phase 9 — Polish** | | |
| T039 baselines visuais | PARCIAL — ver seção 11, corrigida | `console/visual/screens.json` **não precisou de nenhuma edição**: as 6 telas que esta feature muda visualmente já estavam registradas (39 entradas antes, 39 depois — verificado, não presumido; a minha primeira versão desta linha errava ao dizer que single-sign-on era um registro novo). Rodei `make console-visual-accept` (a captura deliberada que a própria T039 pede) duas vezes; a segunda porque a primeira capturou um defeito real que corrigi no meio do caminho (seção 12). As capturas mudaram 3 PNGs — `machine-tokens-1440-light.png`, `notifications-1440-light.png`, `single-sign-on-1440-light.png` — que o operador already salvou à parte e reverteu na árvore de trabalho para HEAD; eu não voltei a tocar `console/visual/baselines/` depois disso, por instrução explícita. **Eu não olhei as imagens capturadas** (só o texto de saída do Playwright) — ver seção 11 para o que isso significa para quem for aceitar. |
| T040 mapa final rota×regra×resultado | FEITO — corrigido | Seção 10 (rotina de T041) segue válida sem alteração. O mapa da suíte transversal em regime normal está na seção 9.2, corrigido: a primeira versão deste documento afirmava zero vermelho: falso, havia 1 (machine-tokens/vocabulary, seção 9.2). Fechado com uma 8ª exceção nomeada, reconfirmado limpo. |
| T041 prova de que a suíte reprova de fato | FEITO | Seção 9 — as quatro violações foram introduzidas, vistas reprovando nomeando rota e regra, desfeitas, e a suíte confirmada limpa de novo. |
| T042 `make verify` | **NÃO RODADO por instrução do orquestrador** | O orquestrador assumiu este gate explicitamente ("Skip T042. Do not run `make verify`... I own the full gate at the wave boundary"). Gates que *foram* rodados por mim: `console_gate typecheck` (limpo), `console_gate lint` (limpo, 4 erros mecânicos corrigidos), `npx vitest run --pool=forks` completo (141/141, 2288/2288). |
| T043 este arquivo | Este arquivo | |

## 2. Vermelhos confirmados, mensagem exata, e o verde correspondente

### T006 — acceptance spec (`020-confiabilidade-telas.acceptance.spec.ts`), primeira rodada, contra o código não corrigido

Comando: `uv run python -m tools.spec_validation browser --feature specs_v6/020-confiabilidade-telas --test console/tests/e2e/020-confiabilidade-telas.acceptance.spec.ts --test console/tests/e2e/transversal-rules.spec.ts` (backing `mock`, cenário padrão `populated`).

1. **(a) audit, corpo com linhas** — VERMELHO:
   ```
   Error: the audit table drew no rows at all
   expect(received).toBeGreaterThan(expected)
   Expected: > 0
   Received:   0
   ```
2. **(b) audit, presets de período** — VERMELHO (achado real, não bug do teste — ver T016):
   ```
   Error: expect(locator).toHaveAttribute(expected) failed
   Locator:  getByTestId('tab-links').locator('[data-testid="tab-link"][data-tab="days-7"]')
   Expected: "page"
   Received: ""
   ```
3. **(c) contagem única** — **verde já na primeira rodada** (2 testes). Investigado conforme exigido para toda alegação que passa de primeira: o motivo é que, no cenário `populated`, o checklist já está completo (`complete: true`) — `/first-run` redireciona para `/` e o card do dashboard não renderiza (nada pendente), então não há duas superfícies para divergir *nesse cenário*. Não é o seletor errando: é a ausência de dado comparável no dataset padrão. A comparação com números reais foi feita à parte, por unidade (T018) e por uma rodada do acceptance spec contra o cenário `first-run` (seção 9).
4. **(d) SSO virgem** — VERMELHO:
   ```
   Error: expect(locator).toHaveCount(expected) failed
   Locator:  getByTestId('sso-problems')
   Expected: 0
   Received: 1
   ```
5. **(e) valor presente** — VERMELHO:
   ```
   Error: row "policies.masking.enabled" has an empty Value cell
   expect(received).not.toBe(expected) // Object.is equality
   Expected: not ""
   ```

Todos os cinco corrigidos nos níveis de unidade descritos abaixo, e a confirmação verde em browser de (a), (b), (d), (e) e (c) está na seção 9, feita depois de escrever a primeira versão deste arquivo — a suíte agora está **7/7 verde** contra `populated`.

### T011 — suíte transversal, primeira rodada

16 testes vermelhos na primeira rodada (12 passaram, 7 skipped por não aplicável no momento). Mensagens de vocabulário, exatas:

| Rota | Termo banido encontrado |
|---|---|
| `/settings/members-roles` | `"HEALTHY"` |
| `/settings/single-sign-on` | `"_id is required"` |
| `/settings/machine-tokens` | `"HEALTHY"` |
| `/settings/autonomy-guardrails` | `"policies."` |
| `/settings/notifications` | `"surfaces."` |
| `/settings/alert-intake` | `"webhook.deliver"` |
| `/settings/schedules-destinations` | `"HEALTHY"` |

Mensagens de coluna de valor vazia, exatas (mesma forma, `row 0 ... has an empty Value cell`), nas rotas: `/settings/single-sign-on`, `/settings/autonomy-guardrails`, `/settings/notifications`, `/settings/alert-intake`, `/settings/schedules-destinations`.

Achado importante: `/settings/single-sign-on` e `/settings/alert-intake` e `/settings/schedules-destinations` reprovaram na regra de valor **sem terem sido nomeadas no diagnóstico ou na spec** para esta regra — a causa raiz era compartilhada (`AdvancedConfigSection`, usado por SSO's claims, Autonomy's advanced scalars, e também por Agent, Integrations, Knowledge e Schedules & destinations' próprias seções avançadas). Corrigido na raiz (seção 3), o que resolve todas simultaneamente.

`_id is required` em `/settings/single-sign-on` é o mesmo defeito de US3 (T025-029), correto que a suíte transversal o pegue por uma via diferente (regra de vocabulário, não a asserção de "sem erro antes de interação").

`HEALTHY` em members-roles/machine-tokens/schedules-destinations e `policies.`/`surfaces.`/`webhook.deliver` nas demais são vocabulário cru **fora do escopo desta feature** — pertencem à 030 (chips de saúde, IDs) conforme a spec já assume nas suas Assumptions. Ficam como exceção pendente de anotação (T010, seção 7).

### T013 — `settings-audit.test.tsx`, vermelho antes da correção de `audit.tsx`

3 testes vermelhos:
```
1) the empty state answers what the page actually draws... > an entirely-system fetch declares the exclusion and empties honestly...
   Expected the element to have attribute: data-state="empty"
   Received: data-state="ready"

2) ...the diagnosed shape — 200 fetched, all system... (mesma forma)

3) filters and export respect each other > the shown count never exceeds the population the audience exclusion actually leaves drawn
   Expected element not to have text content: 10 of
   Received: Showing 10 of 500.
```
Verde depois de `T014`: 25/25 (depois 28/28 com os 3 testes extras de robustez ao relógio para T016).

### T018 — `first-run-plan.test.ts`, vermelho antes de `setupProgress()`

```
TypeError: setupProgress is not a function
```
(4 ocorrências, uma por teste do novo describe). Verde depois de `T019`: 27/27 (arquivo completo).

### T025 — `sso-setup.test.tsx`, vermelho antes do estado de formulário

6 testes vermelhos:
```
1) an unconfigured deployment > shows a neutral summary...
   (elemento sso-state não continha o texto notConfigured)

2) a deployment already carrying problems > shows none of them on a virgin form
   (queryByText(/is required/) encontrou texto — lista aparecia sem interação)

3) reveals only the problem of the field a person actually left, humanised
4) leaving a second field reveals that field's own problem too...
5) submitting reveals every pending problem at once, humanised
6) a problem naming no field this form declares only appears once the form is submitted
   AssertionError: expected <ul data-testid="sso-problems" …(1)>…(2)</ul> to be null
```
Verde depois de `T026`/`T027`: 27/27 (arquivo completo). `settings-sso.test.tsx` (a via server-component) também precisou de reescrita nas mesmas duas asserções que encodavam o comportamento antigo — 9/9 depois.

### T031 — `resolution-preview.test.tsx`, vermelho antes do guard em `EffectiveFieldsTable`

```
1) refuses to render a row with no renderable value...
   AssertionError: expected [Function] to throw an error
   - Expected: null
   + Received: undefined

2) refuses to render a row with no renderable origin... (mesma forma)
```
Verde depois do guard: 14/14 (arquivo completo).

### T035 — `machine-token-groups.test.tsx`, vermelho contra o código já corrigido (ordem invertida, ver nota)

**Nota metodológica**: para este item específico, a implementação (`machine-token-groups.tsx`/`machine-tokens.tsx`) foi corrigida *antes* de eu rodar o teste que prova o defeito, porque o defeito e a correção são mecânicos (trocar `.replace()` por `formatCount()`) e eu já tinha o arquivo aberto. Para obter um vermelho genuíno mesmo assim, rodei a suíte **antes** de atualizar as três asserções antigas que ainda esperavam o texto errado (`'1 tokens'`, `'token(s)'`) — como o código de produção já emitia o texto certo, essas asserções antigas quebraram contra ele, o que é uma prova válida (embora invertida) de que o texto mudou:
```
1) offers only revoked tokens in the collapsed history...
   Expected element to have text content: 1 tokens
   Received: 1 token

2) revokes every token but the most recently created one...
   Expected element to have text content: 1 tokens
   Received: 1 token

3) names how many earlier tokens were replaced
   Expected element to have text content: Replaced 1 earlier token(s)
   Received: Replaced 1 earlier token issued for the same purpose.
```
Corrigidas para o texto certo, mais dois testes novos (plural explícito). Verde: 26/26 (junto com `settings-machine-tokens.test.tsx`).

### T030 — nota sobre a ordem invertida

`console/src/surfaces/effective-fields.ts` foi escrito *antes* do teste dedicado
`effective-fields.test.ts` (ordem de implementação determinada pela necessidade
de ter a função pronta para corrigir T032 logo em seguida). O vermelho
genuíno para *este* defeito específico (formatação por tipo) não veio deste
arquivo — veio da rodada de browser do acceptance spec (alegação (e), acima) e
de `resolution-preview.test.tsx` (T031), ambos vistos vermelhos antes de
qualquer linha de `effective-fields.ts` existir. Declarado explicitamente
aqui, como pedido: para T030 isoladamente, **não tenho um vermelho
independente rastreável a este arquivo específico** — apenas ao efeito que ele
produz.

### T016 — achado fora do diagnóstico: presets de período nunca se marcavam ativos

Causa raiz, cravada em código: `console/src/surfaces/settings/audit.tsx`,
`selectedPeriod` comparava `preset.since` (um ISO instante recalculado a cada
render, contra o relógio real) com `state.filters.since` (o instante
capturado no momento em que o link foi montado) por **igualdade exata de
string**. Como o relógio andou entre o render que ofereceu o link e o
render que respondeu ao clique — mesmo que por milissegundos — os dois
instantes nunca são iguais fora de um relógio congelado (que só existe na
captura visual). Corrigido comparando quantos dias inteiros de diferença há
entre `since` e o relógio atual, arredondado, contra `PERIOD_PRESET_DAYS`.
Três testes novos em `settings-audit.test.tsx` provam isso, incluindo um que
simula 90 segundos de deriva entre o link e a requisição.

## 3. Desvios nomeados

**`preview.tsx` não foi tocado — T032/T037/T038 apontam para outro arquivo.**
As tasks T032 e T038 mandam implementar em
`console/src/surfaces/preview.tsx`. A implementação real ficou em:
- `console/src/design/resolution-preview.tsx` — `EffectiveFieldsTable` ganhou
  o guard que recusa uma linha sem valor/origem renderizável (T031/T032).
- `console/src/surfaces/effective-fields.ts` (novo arquivo) — `effectiveRows()`
  deriva valor efetivo e origem a partir do catálogo de campos
  (`/v1/config/{node}/fields`), com formatação por tipo (`formatHours`,
  `formatSeconds`), consumida por `settings/autonomy.tsx`,
  `settings/notifications.tsx` e `advanced-config-section.tsx`.

Motivo do desvio, verificado por leitura de código: `preview.tsx` contém
`ConfigEditor`/`FieldRow` — o editor **editável**, cuja célula de valor
alimenta um `<input>`, nunca uma célula de tabela somente-leitura. Um campo de
texto vazio num formulário editável é um estado legítimo (um campo ainda não
preenchido), diferente da tabela somente-leitura (`EffectiveFieldsTable`,
usada por `EffectiveFieldsTable`/`AdvancedConfigSection`) que é onde o
defeito diagnosticado ("coluna VALUE vazia") de fato mora — confirmado por
`grep` mostrando `EffectiveFieldsTable` como o único lugar que renderiza a
tabela "Setting/Value/Set at" do mockup `#m2`, e por `preview.tsx`'s
`FieldRow` nunca duplicar "Set at" (verificado — só há uma ocorrência de
`labels.setAt`, na única linha que o compõe, sem um `labels.provenance`
concatenado junto). `preview.tsx` genuinamente não tinha nenhum dos dois
defeitos (P1-4 nem a duplicação de "Set at"); a raiz estava em
`EffectiveFieldsTable`/`AdvancedConfigSection`, um nível abaixo do que a task
nomeia. `provenance-label.ts` (`provenanceLabel()`) também não foi tocado —
continua correto para o único uso "autônomo" que resta (`models-editor.tsx`).

**Fixtures: `populated` não foi alterado para T002; `first-run` já bastava.**
T002 pede uma fixture com a divergência viva. Editar
`fixtures/scenarios/populated/setup-checklist.json` para `complete: false`
foi tentado e revertido: `console/tests/unit/surfaces/dashboard.test.tsx`
afirma explicitamente `await dashboard('populated'); expect(screen.query
ByTestId('setup-hero')).toBeNull()` — uma alteração ali quebraria essa
asserção e, pior, contradiria a própria definição do cenário `populated`
("A full deployment mid-operation" — um deployment maduro com setup
incompleto é uma contradição do que o cenário representa, não um bug a
corrigir). O cenário `fixtures/scenarios/first-run/setup-checklist.json`
**já reproduz a divergência com números reais, sem qualquer edição**: sob o
código antigo, o header dizia "Step 3 of 7" (baseado em `WIZARD_STEPS`) e o
painel/card diziam "4 of 5 steps left" (baseado em `setup.steps`, um array
diferente, de tamanho diferente) — dois denominadores, confirmado por
derivação manual e por teste de unidade. Sob o código novo, os três dizem
"4 of 7" a partir da mesma fonte. Ver seção 9 para a confirmação em browser.

**`config-effective.json` não precisou de alteração para T004.** A
composição do `EffectiveFieldsTable`/`AdvancedConfigSection` deixou de ler
`values`/`provenance` (o documento de configuração efetiva, que nunca
carregava os 12 campos de guardrails/notificações neste dataset) e passou a
ler exclusivamente o catálogo de campos (`/v1/config/{node}/fields`, ou seja
`config-fields.json`), que já carrega `default` por definição de schema.
Bastou estender `config-fields.json` (T004); `config-effective.json` ficou
intocado.

**Blast radius maior que o previsto pela task: `AdvancedConfigSection` é
compartilhado por seis páginas, não duas.** Ao trocar a interface de
`AdvancedConfigSectionProps` (removendo `values`/`provenance`, que a raiz do
defeito estava nelas), o `tsc` apontou 5 outros chamadores além de
`settings/autonomy.tsx`/`settings/sso.tsx`:
`screens/agent.tsx` (2 usos), `screens/integrations.tsx`,
`screens/knowledge.tsx` (4 usos), `settings/alert-intake.tsx`,
`settings/schedules-destinations.tsx` (2 usos). Todos corrigidos pela mesma
razão (a leitura de `/v1/config/{node}/fields` deixou de ser condicionada a
`writable`, e a prop `values`/`provenance` deixou de existir) — sem isso,
essas seis páginas teriam regressão de compilação e, nas quatro que tinham
leitores somente-leitura, uma regressão de comportamento (a tabela efetiva
pararia de mostrar valor para um viewer sem `config.write`, porque antes ela
lia de `values`/`provenance`, buscados incondicionalmente, e agora lê do
catálogo, que só era buscado quando `writable`). Corrigido em todos os seis
arquivos, removendo o mesmo gate `!writable`/`!configWritable` da leitura de
`/fields`, para não regredir o que já funcionava.

## 8. T012 — decisão sobre duplicação com `vocabulary.spec.ts` e `scroll-budget.spec.ts`

**Vocabulário (`vocabulary.spec.ts`)**: nenhuma sobreposição. As rotas que
`vocabulary.spec.ts` varre (`/integrations`, `/first-run?step=verify`,
`/administration`) não são rotas de Settings e não aparecem na lista que
`transversal-rules.spec.ts` constrói de `SETTINGS_PAGES`. Os termos banidos
parcialmente coincidem (`HEALTHY`/`DEGRADED`/`UNCONFIGURED` aparecem nas duas
listas), mas uma asserção é "termo X ausente na rota Y" — como as rotas nunca
coincidem, não há duas cópias da mesma verificação. Nada foi removido de
`transversal-rules.spec.ts` nem de `vocabulary.spec.ts` por este motivo.

**Orçamento de rolagem (`scroll-budget.spec.ts`)**: sobreposição real e
exata para 7 das 9 rotas de Settings — 6 diretamente
(`/settings/members-roles`, `/settings/single-sign-on`,
`/settings/machine-tokens`, `/settings/audit-log`,
`/settings/alert-intake`, `/settings/schedules-destinations`) e uma sétima,
`/settings/autonomy-guardrails`, alcançada por `scroll-budget.spec.ts`
através do endereço aposentado `/autonomy` (que redireciona para lá —
`page.goto` segue o redirect, e a altura medida é a mesma). As duas usam as
mesmas constantes (`CONFIG_SCREEN_VIEWPORT_WIDTH_PX`/`HEIGHT_PX`/
`SCROLL_BUDGET_VIEWPORTS`) e o mesmo cálculo. **Decisão**: a cópia sai da
suíte nova, como o operador pediu — `transversal-rules.spec.ts` continua
**enumerando** as 9 rotas por construção (nenhuma rota de Settings fica de
fora do inventário, satisfazendo o edge case de "rota adicionada depois da
suíte"), mas para as 7 já cobertas por `scroll-budget.spec.ts` o teste chama
`test.skip(...)` com o motivo nomeado ("measured by
console/tests/e2e/scroll-budget.spec.ts against the same constants") em vez
de reafirmar o cálculo. As únicas 2 rotas com uma asserção de rolagem real e
nova nesta suíte são `/settings/models-providers` e
`/settings/notifications` — as duas que `scroll-budget.spec.ts` nunca
alcançou, nem diretamente nem por redirect. Raciocínio registrado no próprio
arquivo (`SCROLL_BUDGET_MEASURED_ELSEWHERE`, com comentário), não só aqui.

**Contagem única e coluna de valor**: nenhuma outra suíte no repositório
verifica essas duas regras — nada para duplicar.

## 4. `first-run` — a divergência real, derivada

Com `fixtures/scenarios/first-run/setup-checklist.json` (não alterado) e seu
`config-effective.json` (sem `models.investigator.model`, logo
`modelChosen=false`):

- `provider: 'configured'` → provider/credential concluídos.
- `modelChosen: false` → model **não** concluído → `currentStep` = `'model'`
  (posição 3 de 7).
- `integrations: [metrics-store: absent, prometheus: verified, proxmox:
  verified]` → 2 configuradas → integrations concluído.
- `verify`: `provider !== 'verified'` → não concluído.
- `estate`: `infrastructure-source` está `'blocked'` → não concluído.
- `alerts`: `first-investigation` está `'blocked'` → não concluído.

Pendentes pelos sete passos do wizard: `model`, `verify`, `estate`, `alerts`
= **4**. Sob o código antigo, o painel/card liam `setup.steps` (5 itens:
`durable-credential` done, `model-provider`/`infrastructure-source`/
`investigation-runtime`/`first-investigation` — 4 não concluídos) = "4 of 5".
O header sempre leu `WIZARD_STEPS` = "Step 3 of 7". Sob o código novo, os
três dizem "4 of 7".

## 5. As 12 linhas de valor — de onde vêm agora

`GUARDRAIL_FIELD_LIST` (`settings/autonomy.tsx`) e `FIELDS`
(`settings/notifications.tsx`) continuam com os mesmos 6+6 campos de antes —
nenhuma linha nova, nenhuma fundida (o redesenho em 4 linhas do mockup `#m2`
é da 040, conforme a spec já assume). O que mudou é a fonte: cada linha
agora resolve `effectiveRows(specs, editableFields(rawFields), locale)`
contra o catálogo de `/v1/config/{node}/fields`, nunca mais contra
`valueAt(values, path)`. `policies.approvals.expiry_hours` e
`surfaces.notification_policy.cooldown_seconds` ganharam formatação de
duração (`formatHours`/`formatSeconds`); os demais usam a formatação por
tipo genérica (`boolean` → "On"/"Off" traduzido; o resto, literal).

## 6. Como a suíte transversal lê as rotas "por construção"

`SETTINGS_PAGES` não pôde ser importado diretamente em
`transversal-rules.spec.ts` (é um módulo TSX que arrasta ícones React — risco
de resolução de módulo fora do ambiente Next que não valia o risco dado o
tempo). Em vez disso, `settingsRoutesFromSource()` lê
`console/src/shell/routes.ts` como texto e extrai `id`/`path` por regex a
partir do bloco `export const SETTINGS_PAGES`. Testado isoladamente via
`node -e` contra o arquivo real: extrai as 9 rotas, na ordem certa. Uma rota
nova em `SETTINGS_PAGES` é varrida automaticamente; uma mudança na forma do
arquivo-fonte (não no conteúdo) é o único jeito de quebrar essa leitura, e
quebra de forma visível (a suíte lança `no Settings route was read from
shell/routes.ts` se a regex não casar nada).

## 7. O que fica pendente, nomeado, não escondido

- **`empty.cause.setup`, pluralização "step(s)"**: descoberto durante o
  trabalho (`console/src/i18n/en.ts`, chave `empty.cause.setup`: "...{count}
  step(s) are outstanding..."), o mesmo padrão do defeito P3 desta feature,
  mas **não nomeado por SC-008** (que fixa literalmente "1 tokens" e "Set at
  Set at:", não este). Deixado como está — FR-022 em tese cobriria, mas
  corrigir toda ocorrência de pluralização malfeita no produto é uma
  varredura maior que esta feature não escopou, e o mockup/spec não citam
  este local. Nomeado para quem pegar a próxima rodada de vocabulário.
- **`/configuration` redireciona para Members & roles sem explicação**
  (DIAGNOSTICO P2-12) — não é FR desta feature, não tocado.
- **As 6 exceções de vocabulário anotadas em T010** (members-roles,
  machine-tokens, autonomy-guardrails, notifications, alert-intake,
  schedules-destinations) são dívida nomeada, não corrigida — dono é a
  030, exatamente como a spec desta feature já assume. A suíte transversal
  agora cobra a remoção dessas entradas automaticamente no dia em que a
  030 corrigir cada rota (ela só precisa apagar a entrada correspondente de
  `EXCEPTIONS`).
- **`AdvancedConfigSection` ganhou uma dependência nova, não testada por
  esta feature**: as seis páginas listadas na seção 3 (`agent.tsx`,
  `integrations.tsx`, `knowledge.tsx` ×4, `alert-intake.tsx`,
  `schedules-destinations.tsx`) agora buscam `/v1/config/{node}/fields`
  incondicionalmente. Cobri isso com a suíte de unidade completa (2288
  testes, 0 falha) e com a suíte transversal/acceptance em browser, mas
  **não escrevi teste novo dedicado a cada uma dessas seis páginas
  especificamente** — o que as cobre é que elas já tinham teste próprio
  antes desta feature e continuam passando.
- **Três baselines visuais capturadas, à espera de um olho humano** (seção
  11): `machine-tokens-1440-light.png`, `notifications-1440-light.png`,
  `single-sign-on-1440-light.png`. Eu identifiquei quais mudaram e por quê,
  mas não as inspecionei visualmente — o operador está com as três
  capturas guardadas à parte; a árvore de trabalho está revertida para
  `HEAD` nessas imagens, por instrução explícita, e eu não vou tocar
  `console/visual/baselines/` de novo.

## 9. Rodada final em browser — o que ela provou, e um achado de instrumento

Depois de escrever a seção 1–8, rodei de novo, contra o build de produção
real (`uv run python -m tools.spec_validation browser --feature
specs_v6/020-confiabilidade-telas --test console/tests/e2e/
020-confiabilidade-telas.acceptance.spec.ts --test console/tests/e2e/
transversal-rules.spec.ts`, backing `mock`).

### 9.1 Dois problemas do meu próprio teste, não do produto

**(a) audit — Acceptance Scenario 1 contra a fixture errada.** A fixture de
T001 (200 eventos, todos `actor_id=default`) faz a **leitura padrão**
esconder os 200 — corretamente, porque é exatamente o comportamento que
FR-003/FR-004 pedem. Meu teste (a) original visitava `/settings/audit-log`
sem `?audience=all` e esperava linhas — a alegação certa para *essa* fixture
específica só se verifica pedindo para ver os eventos escondidos (o mesmo
toggle que o teste (a segunda) já prova existir). Corrigido visitando
`/settings/audit-log?audience=all`. Não é uma regressão do produto: é o
teste perguntando a pergunta errada à fixture certa.

**(b) valor — `<details>` fechado não tem `innerText`, tenha ele o que
tiver dentro.** Depois de corrigir (a), a alegação (e) e a regra 4 ainda
reprovavam nomeando `policies.autonomy.allow_unverifiable_actions` — um
campo da seção **avançada** de Autonomy (`AdvancedConfigSection`, dentro de
um `<details>` fechado por padrão). Investiguei com um teste de unidade
isolado (`AdvancedConfigSection` com o mesmo dado exato, fora do browser) —
passou, provando que `effectiveRows()`/`EffectiveFieldsTable` estão
corretos. Removi `.next` e reconstruí do zero para eliminar cache como causa
— o vermelho persistiu. A causa real: `page.locator(...).innerText()` do
Playwright **respeita renderização visual**, e o conteúdo de um `<details>`
sem `open` não está visualmente renderizado — `innerText()` devolve `''`
para qualquer célula ali dentro, esteja ela preenchida ou não. Isto não é um
defeito de produto: é um buraco no **instrumento** (minha alegação (e) e a
regra 4 da suíte transversal), que checavam `effective-field` em toda a
página sem abrir as seções recolhidas primeiro. Corrigido nos dois arquivos
(`page.evaluate(() => document.querySelectorAll('details').forEach(d => d.open = true))`
antes de ler as células) — ambos em
`console/tests/e2e/020-confiabilidade-telas.acceptance.spec.ts` e
`console/tests/e2e/transversal-rules.spec.ts`. Also adicionei os 4 campos de
`policies.autonomy.*` (a seção avançada de Autonomy) a
`fixtures/scenarios/populated/config-fields.json` — não eram necessários
para o defeito acima (que era do instrumento, não do dado), mas a fixture
ficou mais completa e correta por tê-los, então o ajuste fica.

Este achado importa além desta feature: **qualquer alegação futura sobre
`effective-field`/tabela de configuração precisa abrir os `<details>`
primeiro**, ou vai reportar falso vermelho nas seções avançadas — deixei o
comentário em ambos os arquivos para a próxima feature encontrar.

### 9.2 Resultado, `populated` — e uma correção sobre o que este documento afirmou antes

`020-confiabilidade-telas.acceptance.spec.ts`: **7 passed, 0 failed**
(áudio (a)+(b), contagem única ×2, SSO virgem, valor) — não mudou.

`transversal-rules.spec.ts`: a versão anterior deste documento afirmava
**16 passed, 12 skipped, 0 failed**. Isso estava **errado**. Uma rodada
determinística independente, feita depois desta seção ter sido escrita,
rodou a mesma suíte contra a mesma árvore e encontrou:

```
[behaviour] › transversal-rules.spec.ts:251:5 › /settings/machine-tokens › carries no banned vocabulary in its visible text
Error: "HEALTHY" is banned vocabulary, visible on /settings/machine-tokens
Received: ["HEALTHY"]
```
com resultado **1 failed, 12 skipped, 22 passed** (a soma inclui as duas
specs rodadas juntas — 7 da acceptance + 15 da transversal = 22). Eu não
tinha essa mensagem registrada, e a razão é rastreável: `/settings/
machine-tokens` **apareceu no vermelho da primeira rodada** (T011, tabela
da seção 2 deste documento, linha "`/settings/machine-tokens` |
`"HEALTHY"`""), mas quando montei a tabela `EXCEPTIONS` (T010) transcrevi
a mesma descoberta só para `/settings/members-roles`, que tem o mesmo
sintoma pelo mesmo motivo — as duas rotas renderizam o mesmo componente
(`MachineTokenGroups`, `<Badge status="healthy" />`, um único call site em
`console/src/surfaces/machine-token-groups.tsx`). Não é um defeito que esta
feature introduziu (confirmado: o `Badge` já existia em `HEAD`, antes de
qualquer mudança minha), é uma exceção que eu já tinha visto e não
registrei para a segunda rota que a mesma descoberta cobria.

**Decisão, registrada**: adicionar `/settings/machine-tokens` + `vocabulary`
como uma 8ª entrada em `EXCEPTIONS`, com o mesmo motivo substantivo do
`/settings/members-roles` (mesmo componente, mesmo call site, mesma dívida
de vocabulário) — não alterar `machine-token-groups.tsx` para trocar o
chip. Considerei a alternativa (corrigir o `Badge` aqui) e a descartei por
consistência: o vocabulário cru de chips de saúde já está nomeado, nesta
mesma tabela e no ledger (seção 7), como fora do escopo desta feature e de
propriedade da 030 — tratar a mesma ocorrência do mesmo componente de forma
diferente conforme a rota seria arbitrário, e corrigir aqui seria entrar no
escopo de uma feature que ainda vai redesenhar esse chip inteiro. Aplicado
em `console/tests/e2e/transversal-rules.spec.ts` (tabela `EXCEPTIONS`,
entrada `/settings/machine-tokens`/`vocabulary`).

Reconfirmado depois da correção, rodada completa (`--no-build`, mesma
árvore): **`transversal-rules.spec.ts` sozinho — 15 passed, 13 skipped
(exceções, incluindo a nova), 0 failed**; junto com a acceptance spec na
mesma invocação, **22 passed, 13 skipped, 0 failed** no total. Nenhuma
mensagem de falha em nenhuma das duas specs.

`npx vitest run --pool=forks` (console inteiro), reconfirmado depois de
todas as correções deste ciclo: **141 arquivos, 2288 testes, 0 falha**.
`console_gate typecheck`: limpo. `console_gate lint`: limpo. `console_gate
format-check` (`prettier --check .`, árvore inteira): limpo — 11 arquivos
estavam desformatados quando a mesma rodada determinística checou (listados
na seção 12), corrigidos com `prettier --write` restrito a esses 11
arquivos e reconfirmados.

### 9.3 Resultado contra `first-run` (só para a regra de contagem única, com números reais)

`uv run python -m tools.spec_validation browser --feature
specs_v6/020-confiabilidade-telas --test console/tests/e2e/
020-confiabilidade-telas.acceptance.spec.ts --test console/tests/e2e/
transversal-rules.spec.ts --scenario first-run --no-build`.

As três verificações de "uma só contagem" (duas na acceptance spec, uma na
suíte transversal) **passam com números reais** — header, painel e card
citam "4 de 7" simultaneamente (a mesma derivação da seção 4). As outras 3
falhas dessa rodada (audit ×2, SSO) são esperadas e não são regressão: o
cenário `first-run` tem seus próprios dados (nunca alterados por mim — ver
seção 3), diferentes das fixtures que constrói especificamente para
`populated`, então as alegações (a)/(b)/(d) — escritas contra a fixture de
`populated` — não se aplicam a ele. Nenhuma delas é sobre contagem.

## 10. T041 — a suíte reprova de verdade, provado e desfeito

Introduzi, uma de cada vez, uma violação real de cada regra numa rota
conforme, com edições temporárias marcadas `TEMP-T041-*` em comentário,
revertidas assim que a mensagem foi capturada — `git diff` e `grep -r
"TEMP-T041"` confirmam zero rastro depois. Nenhuma violação foi commitada
ou deixada na árvore.

1. **Vocabulário**, em `/settings/models-providers` (rota conforme):
   texto `SERVICE_ACCOUNT` inserido temporariamente logo após o cabeçalho da
   página (`settings/models.tsx`).
   ```
   Error: "SERVICE_ACCOUNT" is banned vocabulary, visible on /settings/models-providers
   expect(received).toBeNull()
   Received: ["SERVICE_ACCOUNT"]
   ```
2. **Orçamento de rolagem**, na mesma rota: `CONFIG_SCREEN_SCROLL_BUDGET_
   VIEWPORTS` (`config/constants/surfaces.py`) reduzido temporariamente de
   `2.0` para `0.01`.
   ```
   Error: /settings/models-providers is 1080px tall against a 10.8px budget (0.01 viewports of 1080px)
   expect(received).toBeLessThanOrEqual(expected)
   Expected: <= 10.8
   Received:    1080
   ```
3. **Coluna de valor**, em `/settings/single-sign-on` (rota conforme, sem
   exceção): uma linha `effective-field` fictícia, com a célula de valor
   vazia, inserida temporariamente no `<tbody>` de `EffectiveFieldsTable`
   (`console/src/design/resolution-preview.tsx`), fora do array `rows` (para
   não disparar o guard de T031, que é uma garantia diferente).
   ```
   Error: row 0 of the configuration table on /settings/single-sign-on has an empty Value cell
   expect(received).toBe(expected) // Object.is equality
   Expected: -1
   Received: 0
   ```
4. **Contagem única**, rodada contra o cenário `first-run` (a única rota/
   cenário onde a regra tem o que comparar): o total do header em
   `screens/first-run.tsx` alterado temporariamente para `progress.total + 1`
   — o painel e o card ficaram intocados.
   ```
   Error: wizard header claims a total of 8 against dashboard card's 7
   expect(received).toBe(expected) // Object.is equality
   Expected: 7
   Received: 8
   ```

As quatro violações, uma por vez, fizeram a suíte reprovar **nomeando a
rota e a regra** — nenhuma delas exigiu ler o código-fonte do teste para
saber o que quebrou. As quatro foram desfeitas (as edições de produção
revertidas ao texto original, confirmado por `grep` não achando mais nenhum
marcador `TEMP-T041`) e uma reconstrução completa + nova rodada (seção 9.2)
confirmou a suíte de volta ao estado limpo.

## 11. T039 — registro visual (seção corrigida — a versão anterior errava em dois pontos, ver nota no topo)

**Correção 1 — `console/visual/screens.json` já tinha as 6 telas.** A
versão anterior desta seção afirmava que `/settings/single-sign-on` "não
estava registrada antes" e precisava de um registro novo. Isso é falso,
verificado por leitura direta do arquivo: `single-sign-on-1440-light` já
existe em `screens.json`, com `status: "baselined"` e uma baseline
committed, desde antes desta feature. Contei as entradas: **39 antes das
minhas mudanças, 39 depois** — eu não editei este arquivo nesta feature.
As 6 telas que este trabalho muda visualmente já tinham entrada:

| Tela | Estado no registro | O que muda visualmente |
|---|---|---|
| `/settings/audit-log` | registrada, `status: "pending"` (sem baseline committed) | corpo da tabela e aviso de truncamento — sem baseline para comparar contra, a suíte visual não gera teste para esta tela até alguém promovê-la a `baselined` |
| `/first-run` | registrada, `status: "pending"` | header (linha única com pendentes) — mesma observação acima |
| `/settings/autonomy-guardrails` | registrada, `status: "pending"` | coluna Value deixa de estar vazia (6+4 linhas) — mesma observação acima |
| `/settings/notifications` | registrada, `status: "baselined"` | coluna Value deixa de estar vazia (6 linhas) — **capturada, ver abaixo** |
| `/settings/models-providers` | registrada, `status: "baselined"` | não esperava diferença (esta feature não tocou `settings/models.tsx`) — **confirmado sem diferença nas duas capturas** |
| `/settings/single-sign-on` | registrada, `status: "baselined"` (já existia) | estado virgem muda de "8 erros" para "resumo neutro" — **capturada, ver abaixo** |

Como só 3 das 6 estão `baselined`, `make console-visual-accept` só gera
teste (e só recaptura) para essas 3, mais qualquer outra tela `baselined`
não tocada por esta feature (confirma determinismo — ver abaixo). As 3
`pending` (audit-log, first-run, autonomy-guardrails) continuam sem nenhuma
imagem para comparar, exatamente como antes desta feature; promovê-las a
`baselined` é uma decisão do operador, fora do que esta task pede.

**Correção 2 — eu capturei baselines, duas vezes, e a afirmação anterior
("não capturei nem aceitei nenhuma") estava errada.** Rodei `make
console-build && make console-visual-accept` (a captura deliberada que
T039 pede — o único comando que existe neste repositório para gerar uma
baseline nova é literalmente chamado `accept`; não há um modo "capturar
sem aceitar" separado, e o próprio `tools/console_visual.py` documenta que
"a aceitação é o commit, não uma flag do comando" — como eu nunca dou
`git add`/commit, o commit continua sendo do operador independentemente do
nome do comando que gera o arquivo). Rodei duas vezes:

1. **Primeira rodada**: build limpo + accept. Resultado: `notifications-
   1440-light.png` e `single-sign-on-1440-light.png` recapturados
   (esperado — T032/T038 e T026/T027 mudam o que essas telas desenham);
   `models-providers-1440-light.png` sem diferença (confirmado, como eu já
   esperava). `machine-tokens-1440-light.png` **também** foi recapturado —
   uma tela que a T039 original nem cita, porque o registro dela é da
   feature de origem, não desta lista — e o log do servidor, nesta
   primeira rodada, mostrou um erro real do Next.js (ver seção 12): a tela
   ainda "passou" a captura (capturar sempre "passa" — é escrita, não
   comparação), mas o que foi escrito refletia um defeito, não o produto
   correto.
2. Corrigi o defeito da seção 12 e rodei **build limpo + accept de novo**.
   `machine-tokens-1440-light.png` foi recapturado outra vez (agora sem o
   erro no log do servidor); `notifications`/`single-sign-on` **não**
   mudaram entre as duas rodadas (byte-a-byte estáveis, confirmando que a
   primeira captura dessas duas já refletia o código certo); todas as
   outras 27 telas `baselined` do produto (`agent-*`, `gallery-*`,
   `shell-*`, `sign-in`, etc. — nenhuma tocada por esta feature)
   permaneceram **idênticas** ao committed em `HEAD` nas duas rodadas —
   determinismo confirmado empiricamente, não só presumido.

**O que ficou, e o que eu não fiz.** As 3 imagens que de fato mudaram —
`machine-tokens-1440-light.png`, `notifications-1440-light.png`,
`single-sign-on-1440-light.png` — foram identificadas por mim
(`git status --short console/visual/baselines/`), e o operador as salvou à
parte e reverteu a árvore de trabalho para `HEAD` (um guard,
`check-config-parity`, recusa rodar o gate com uma baseline committed
modificada). **Eu não olhei nenhuma das três imagens** — só o texto de
saída do Playwright (`✓ ... matches its baseline`, e a linha `is
re-generated, writing actual` para cada uma que mudou). Isso não satisfaz
inteiramente "olhar cada captura antes de aceitar": o que eu tenho é a
confirmação de que a captura rodou e de quais arquivos mudaram, não uma
inspeção visual minha do conteúdo. Quem for aceitar essas três precisa
efetivamente olhá-las — eu não posso ficar por essa parte. Por instrução
explícita, não toquei `console/visual/baselines/` de novo depois disso e
não rodei a suíte visual outra vez.

## 12. Achado adicional, encontrado durante a captura visual: uma função cruzando a fronteira servidor/cliente

A primeira rodada de `make console-visual-accept` (seção 11) imprimiu, no
log do servidor Next.js, antes de capturar `machine-tokens-1440-light.png`:

```
⨯ Error: Functions cannot be passed directly to Client Components unless
you explicitly expose it by marking it with "use server". Or maybe you
meant to call this function rather than return it.
  {purpose: ..., ..., superseded: function superseded, ...}
⨯ Error: Functions cannot be passed directly to Client Components ...
  {..., count: function count, ...}
⨯ Error: Functions cannot be passed directly to Client Components ...
  {..., revokedGroup: function revokedGroup, ...}
```

**Causa raiz, em código.** `console/src/surfaces/settings/machine-
tokens.tsx` é um server component; a implementação original de T036 montava
`labels.superseded`, `labels.count` e `labels.revokedGroup` como três
closures (`(count: number) => formatCount(locale, count, ...)`) e passava
o objeto `labels` inteiro para `<MachineTokenGroups labels={labels} .../>`
— `machine-token-groups.tsx` abre com `'use client'`. Passar uma função de
um server component para um client component é proibido pelo React Server
Components: uma função não é um valor serializável através dessa
fronteira, sempre, independente de ela ser chamada ou não. Isto **não** é
o mesmo padrão usado em T032 (`effectiveRows`/`formatHours`/`formatSeconds`
em `advanced-config-section.tsx`) — verificado por leitura: `Advanced
ConfigSection` **não** é `'use client'`, então as funções de formatação ali
são chamadas inteiramente dentro da árvore do servidor (`effectiveRows()`
resolve tudo para string antes de qualquer prop cruzar uma fronteira real)
— só o padrão de T036 tinha o defeito.

**Por que nenhuma das minhas próprias suítes pegou isso antes da captura
visual.** `console/tests/unit/surfaces/machine-token-groups.test.tsx` e
`settings-machine-tokens.test.tsx` (Vitest) renderizam o componente
diretamente em `jsdom` — nunca passam pela serialização real do Next.js,
então a restrição é invisível para os dois. O acceptance spec desta
feature não visita `/settings/machine-tokens`. A suíte transversal visita
a rota, mas nenhuma das quatro regras lê o texto específico que essas três
funções produzem de um jeito que dependeria delas terem sido de fato
chamadas do lado do cliente — a regra de vocabulário só olha texto
proibido (que já estava lá, independente do bug), e as outras três não se
aplicam a este componente. Não confirmei se o erro também aparecia no
stderr das rodadas anteriores de `spec_validation browser` sem eu notar —
não fica descartado, só não foi checado especificamente para este sinal, e
registro isso em vez de presumir uma resposta.

**Correção.** `MachineTokenGroupsProps` ganhou `locale: Locale`;
`MachineTokenLabels` perdeu os três campos-função; os três call sites
(`console/src/surfaces/machine-token-groups.tsx`) agora chamam
`formatCount(locale, n, chave.one, chave)` diretamente, com as mesmas
chaves de catálogo de antes (texto inalterado — conferido contra `en.ts`:
as strings que o teste já esperava batem exatamente com o catálogo real).
`settings/machine-tokens.tsx` para de montar as três closures e passa
`locale={locale}` para `<MachineTokenGroups>`. `console/tests/unit/
surfaces/machine-token-groups.test.tsx`: as 3 closures saíram de `LABELS`,
e `locale="en"` foi adicionado às 23 chamadas de `<MachineTokenGroups>` —
26/26 verde depois, exercitando agora o catálogo real em vez de um texto
só do teste. Reconfirmado depois da correção: build limpo + accept de novo
(sem o erro no log — seção 11), `typecheck`/`lint` limpos, suíte de unidade
completa 141/2288 sem falha.

**Por que isto está registrado aqui e não escondido dentro de T036.** Este
defeito nunca apareceu vermelho em nenhum teste que eu tivesse — eu só o
vi porque rodei a captura visual contra o build de produção real e li o
log do servidor, não porque alguma asserção reprovou nomeando-o. Registro
isso como um limite dos meus próprios instrumentos, do mesmo jeito que a
seção 9.1 registra o achado do `<details>` fechado: qualquer feature futura
que monte um objeto de labels com uma função e o passe para um client
component tem o mesmo risco, e nem a suíte de unidade nem as duas specs de
browser desta feature teriam pegado.

## 13. Sobre a formatação (`prettier`)

A mesma rodada determinística que encontrou o vermelho da seção 9.2 também
rodou `prettier --check .` e listou 11 arquivos desformatados — os mesmos
que eu tinha acabado de escrever ou editar nesta feature (`effective-
fields.ts`, `settings/autonomy.tsx`, `settings/notifications.tsx`, `setup-
hero.tsx`, as duas specs novas de e2e, e cinco arquivos de teste de
unidade). Corrigido com `prettier --write` restrito a esses 11 arquivos
(nenhum outro tocado), mais os dois arquivos da seção 12
(`machine-token-groups.tsx`, `settings/machine-tokens.tsx` e o teste de
unidade correspondente, que já estava na lista de 11) — todos já estavam
formatados corretamente depois da correção da seção 12. `prettier --check
.` na árvore inteira do console, reconfirmado limpo depois.

## 14. Um terceiro instrumento que não via o que o gate via: o piso de cobertura de branch

### 14.1 O que o gate viu e o meu comando não

`npx vitest run --pool=forks` (o comando que rodei em toda esta feature)
**não aplica os limiares de cobertura** — não roda a instrumentação `v8`
nem lê `coverage.thresholds` de `console/vitest.config.ts` a menos que a
flag `--coverage` seja passada. O gate real, `console_gate test`, chama
`vitest run --coverage`, que instrumenta e falha se qualquer um dos quatro
limiares (`lines`, `statements`, `functions`, `branches`, todos 90 em
`vitest.config.ts`) não for atingido. Os dois comandos rodam a mesma suíte
e reportam o mesmo verde de teste — a diferença é inteiramente sobre o que
cada um *mede depois*. Reproduzido com o comando exato do gate, contra a
árvore como a rodada determinística a viu:

```
Statements   : 94.21% ( 6071/6444 )
Branches     : 89.96% ( 4463/4961 )
Functions    : 92%    ( 1875/2038 )
Lines        : 96.27% ( 5609/5826 )
ERROR: Coverage for branches (89.96%) does not meet global threshold (90%)
```

89.96% contra um piso de 90% — 4463 de 4961 branches, ~2 branches do
limiar. Confirmado byte a byte contra o que o coordenador reportou.

### 14.2 Onde os branches não cobertos realmente estavam

Sem uma tabela por arquivo no relatório do console (`vitest.config.ts`
declara `reporter: ['text-summary', 'lcov']`, sem `'text'` — de propósito,
não um acidente meu: o relatório completo só existe em
`coverage/lcov.info`), parseei o `lcov.info` gerado (formato `BRDA:
linha,bloco,ramo,vezes-tomado`) para achar, por arquivo, exatamente quais
linhas nunca tomaram um dos dois lados de uma decisão. Verifiquei cada uma
por leitura antes de decidir se era minha:

- **`effective-fields.ts`** (arquivo novo desta feature, 100% meu): 10 de
  39 branches nunca exercitados. Todos genuinamente meus: `formatByType`
  nunca foi chamada com um valor que é um booleano JS sob um `type` que a
  própria linha `type === 'boolean'` já não capturou antes (o braço
  defensivo, linhas 46-47) — nenhum teste tinha um campo cujo `type` do
  schema fosse diferente de `'boolean'` mas cujo `value` fosse `true`/
  `false` de fato; `formatHours`/`formatSeconds` nunca receberam um valor
  que precisasse de `Number(value)` (só números já prontos), nunca um
  valor não-finito (o branço "não é número, devolve vazio"), e
  `formatSeconds` nunca foi chamada com `count === 1` (o singular — só
  `formatHours` tinha esse teste).
- **`console/src/design/resolution-preview.tsx`** (8 não cobertos): **não
  são meus**. Localizei as 8 linhas exatas (47, 65, 66, 94, 100, 104, 112,
  113) e são todas dentro de `patchOf`, `stringify` e `resolvedFrom` — a
  maquinaria de patch/preview que a feature que aposentou o editor bruto
  de configuração escreveu, não esta. O componente que esta feature de
  fato mudou neste arquivo, `EffectiveFieldsTable` e o seu guard (T031),
  fica bem mais abaixo no arquivo e **não aparece em nenhuma linha da
  lista de não-cobertos** — já estava inteiramente coberto antes desta
  correção. Não toquei este arquivo.
- **`settings/notifications.tsx`** (3 de 10): as três apontam para a
  mesma lacuna — nenhum teste desta tela nunca rendeu com `resolveNode`
  devolvendo `''` (nenhum nó resolvido). Uma das duas ocorrências do
  padrão `nodeId === '' ? nothing : await panelRead(...)` é exatamente o
  gate do fetch de `/v1/config/{node_id}/fields` que esta feature mudou
  (retirou o `!writable ||`, T032) — relacionado o bastante para cobrir.
- **`sso-setup.tsx`** (5 de 77): duas são branços defensivos que **não
  são alcançáveis pelo próprio desenho do componente** — `humanised()`'s
  `field === undefined` (linha 90) só é chamada a partir de `errorFor()`,
  que só procura problemas cujo `problemField` já bate com o campo
  passado, e o `?? ''` de `problemField` (linha 83) é inalcançável para
  qualquer `string` real (`''.split(' ')` já devolve `['']`, nunca um
  array vazio) — verificadas por leitura, não presumidas, e deixadas sem
  teste porque forçar uma cobrisse exigiria exportar uma função hoje
  privada só para alcançar um ramo que o próprio módulo prova
  inatingível pelo seu único chamador. As outras três são reais e minhas:
  `adopt()` nunca recebeu uma resposta sem `problems` (linha 186);
  `test()` nunca teve `ask('test', ...)` falhar (linha 213 — as duas
  outras chamadas de `ask`, `save`/`makeActive`, já tinham essa mesma
  forma testada, mas cada `if (answered === null) return;` é um ponto de
  branch textualmente distinto); o `onBlur` nunca foi disparado duas
  vezes no mesmo campo (linha 276, o atalho que evita criar um `Set` novo
  quando o campo já estava tocado).
- **`settings/audit.tsx`** (1 de 42): a única linha é dentro de
  `humanize()` (`if (words.length === 0) return value;`) — formatação de
  rótulo de ação/recurso, não a exclusão nem o truncamento que esta
  feature mudou (T014/T016). Verificado por leitura: as decisões que esta
  feature de fato introduziu neste arquivo (`stateOf(events, rows.length
  === 0)`, `total > visible.length`, a comparação de dias do preset de
  período) já estavam com os dois lados cobertos — esta é a única linha
  do arquivo com um branch não coberto, e não é uma delas. Não toquei
  este arquivo.

### 14.3 O que fiz

Testes novos, cobrindo só o que a leitura acima confirmou ser meu e
alcançável: `console/tests/unit/surfaces/effective-fields.test.ts` (+7 —
booleano sob tipo não-booleano, valor-objeto sem regra própria vira JSON,
`formatHours`/`formatSeconds` com string numérica, com valor não-finito, e
`formatSeconds` no singular), `console/tests/unit/surfaces/settings/
notifications.test.tsx` (+1 — painel vazio quando nenhum nó resolve),
`console/tests/unit/surfaces/sso-setup.test.tsx` (+3 — teste de claims
inalcançável não apaga o resultado anterior, `activate` cuja resposta omite
`problems`, e deixar o mesmo campo duas vezes). 11 testes novos ao todo,
todos rodados e vistos verdes (`npx vitest run --pool=forks` nos arquivos
tocados, depois a suíte inteira).

Deliberadamente **não** tocado: `resolution-preview.tsx` (não é meu, seção
acima), `settings/audit.tsx` (a única lacuna não é minha), e duas linhas
específicas de `sso-setup.tsx` (linhas 83 e 90, inatingíveis pelo próprio
desenho do módulo — nomeadas, não escondidas).

### 14.4 Resultado, com o comando exato do gate

```
npx vitest run --coverage   (de console/, reproduzido duas vezes, mesmo número as duas)

Statements   : 94.3%  ( 6077/6444 )
Branches     : 90.28% ( 4479/4961 )
Functions    : 92%    ( 1875/2038 )
Lines        : 96.3%  ( 5611/5826 )
```
Nenhuma linha `ERROR`. Exit 0 (verificado diretamente, não inferido do
texto). 2299 testes (era 2288 antes desta correção, +11). Os quatro
limiares de 90% agora passam, com uma folga real (branches subiu 16
pontos de cobertura absoluta — 4463→4479 — contra um déficit de ~2
necessário; a folga vem de ter coberto o conjunto inteiro de
`effective-fields.ts`, não de caçar o número mínimo). `typecheck`, `lint`
e `format-check` (árvore inteira) reconfirmados limpos depois — um arquivo
(`sso-setup.test.tsx`) precisou de `prettier --write` depois dos testes
novos, corrigido e reconfirmado.

### 14.5 O padrão, para quem rodar a 030

Esta é a terceira vez nesta mesma feature que um dos meus próprios
comandos de verificação **não perguntava a mesma coisa que o gate
pergunta**, e as três vezes o defeito era real mas invisível ao meu
instrumento, não ao produto:

1. `page.locator(...).innerText()` do Playwright não vê o conteúdo de um
   `<details>` fechado — o instrumento (minha alegação de aceitação e a
   suíte transversal), não o produto (seção 9.1).
2. Uma função passada de um server component para um `'use client'` nunca
   aparece como erro num teste do Vitest, porque o Vitest nunca serializa
   nada através dessa fronteira — só a captura visual, contra um build de
   produção real, imprimiu o erro (seção 12).
3. `npx vitest run --pool=forks` roda a suíte inteira e não aplica os
   quatro limiares de cobertura que `vitest.config.ts` declara — só
   `vitest run --coverage` pergunta essa pergunta, e é o comando que o
   gate roda, não o que eu rodava por padrão.

Os três têm a mesma forma: um comando mais barato, rodado com mais
frequência durante o trabalho, que responde a maior parte da pergunta e
fica silencioso exatamente na parte que o gate cobra. Nenhum dos três é
motivo para parar de rodar o comando barato — é motivo para rodar o
comando exato do gate pelo menos uma vez, no fim, antes de declarar
qualquer coisa pronta. **Atualização (seção 15.5): o quarto apareceu antes
da 030 — nesta mesma feature, no ciclo seguinte.**

## 15. Fixtures roteadas pelo builder, uma reversão de arquitetura e a fronteira de um gate de único cenário

Um terceiro ciclo de correção, depois deste documento já estar com as
seções 1–14 escritas. Registrado por inteiro porque mudou código de
produção (não só fixture) de um jeito que reverte uma decisão que este
próprio documento defendia antes.

### 15.1 As fixtures deixaram de ser editadas à mão

`fixtures/scenarios/` é gerado — `tools/mockplane/dataset/build.py` é a
única rota para essa árvore, e uma rodada determinística encontrou o que
editar à mão por fora dela custava: `settings-org.spec.ts` (de uma feature
anterior) quebrou porque `populated/audit-events.json` deixou de ter o
formato que aquele teste assume (8 eventos, atores mistos), e 11 testes de
contrato (`tests/contract/fixtures/`) reprovaram porque o formato
escrito à mão não validava contra o documento da API nem contra o grafo
de referências do dataset. Causa raiz: `degraded`/`incident-live`/
`restricted`/`scale` derivam de `populated`, então um hand-edit ali quebra
cinco cenários de uma vez.

**Decisão, do operador**: reverter os três arquivos hand-edited
(`git checkout --`), expressar as mudanças como registros do builder, e
dar ao estado do "audit inundado" seu próprio cenário irmão — o padrão que
`restricted`/`incident-live` já estabelecem (um arquivo só, tudo o mais
herdado). A linha: enriquecimento legítimo de "um deployment cheio em
operação" (os campos de configuração do T004, o estado de SSO do T003)
pode continuar em `populated`, desde que gerado; o estado do audit não
pode, porque contradiz o que `populated` representa e quebra o teste de
outra feature.

**O que mudou, em código**:
- `fixtures/scenarios/populated/audit-events.json`, `config-fields.json`,
  `sso.json`: revertidos para `HEAD` (`git checkout --`), depois
  regenerados pelo builder — `audit-events.json` voltou a ser
  byte-idêntico ao `HEAD` original (8 eventos, atores mistos);
  `config-fields.json`/`sso.json` mudaram porque as mudanças legítimas
  agora vêm do código, não do arquivo.
- `tools/mockplane/dataset/served.py`: o registro `sso` de
  `identity_records()` reescrito para o estado não configurado (T003);
  `_CONFIG_FIELDS_DEFAULTED` (16 campos novos — `policies.masking.*`,
  `policies.guardrails.*`, `policies.approvals.*`,
  `surfaces.notification_policy.*`, `policies.autonomy.*`) com o
  `default` exato lido do schema real (`platform/config_service/schema/
  policies.py`, `surfaces.py`) antes de escrever cada valor — não
  retypado às cegas; `_config_fields()` ganhou um `.get(path, default)`
  em vez de indexação direta, então um path ausente de `source`/`values`
  resolve para `provenance: ""` e `value = default` automaticamente, sem
  uma entrada por campo.
- `tools/mockplane/dataset/build.py`: `audit_flooded_records()` (novo),
  devolvendo só o registro `audit-events` — 200 eventos gerados (não
  digitados), ciclando 5 pares `(action, resource_kind, resource_id)` já
  válidos em `populated` (então cada referência resolve por construção),
  `actor_id` no sentinela `DEFAULT_ORGANISATION_ID`, `total: 156735`.
  Registrado em `BUILT_SCENARIOS`, `records_for()`, `__all__`.
- `fixtures/manifest.json`: entrada `audit-flooded`, `derives_from:
  "populated"`.
- `config/constants/fixtures.py`: `"audit-flooded"` adicionada a
  `FIXTURE_SCENARIO_NAMES` — sem isso os testes de contrato parametrizados
  por cenário nunca a alcançam.

**Um achado no caminho**: `served.AUTOMATION` (o principal automatizado
nomeado, com grants próprios) não é o mesmo fato que "o deployment,
sem um autor atribuível" — o `actor_id` que
`platform/credentials/proxy/audit.py` grava é o `org_id` de quem agiu, e
`DEFAULT_ORGANISATION_ID` (`config/constants/first_run.py`) é o valor
literal `"default"` que esse campo carrega quando a organização nunca foi
renomeada do bootstrap. `SYSTEM_PRINCIPAL = 'default'` em
`settings/audit.tsx` compara contra exatamente esse sentinela. Usar
`served.AUTOMATION` no lugar dele produzia `actor_id: "user-automation"`
— um principal real, não o sentinela — e o toggle da tela nunca aparecia.
Corrigido usando `DEFAULT_ORGANISATION_ID` diretamente.

**Um segundo achado, na pseudonimização**: mesmo com o valor certo
(`"default"`), o pipeline de anonimização (`tools/mockplane/anonymise/
pseudonyms.py`) o substituía por um pseudônimo novo (`"user-garnet"`) —
`looks_pseudonymous(Kind.PRINCIPAL, "default")` não reconhecia a forma.
`_PSEUDONYM_SHAPES[Kind.PRINCIPAL]` só aceitava `^user-[a-z]+(-\d{3})?$`.
Corrigido ampliando esse regex para aceitar `"default"` também, com um
comentário citando `DEFAULT_ORGANISATION_ID` e por que esse valor
específico tem que sobreviver a uma passada do pipeline sem virar outra
coisa — é um sentinela de protocolo, não uma identidade.

**Resultado, confirmado pelo coordenador e reconfirmado por mim depois de
cada correção**: `uv run pytest tests/contract/fixtures/ -q` — **107
passed, 0 failed** (104 no `HEAD`, +3 pelos três testes parametrizados que
agora também cobrem `audit-flooded`). `settings-org.spec.ts` — verde.
`git status --short fixtures/` mostra exatamente `manifest.json`,
`populated/config-fields.json`, `populated/sso.json` modificados e
`audit-flooded/` novo — `populated/audit-events.json` sem diff nenhum.

### 15.2 `outstanding()` revertido: `setup.steps`, não `WIZARD_STEPS`

A correção da cobertura (seção 14) finalmente deixou a suíte Python
inteira rodar — e ela nunca tinha rodado nesta feature até ali, porque
`console-check` reprovava antes (achado da seção 9 original do
coordenador, agora com um quarto exemplo). Rodando `pytest` sem escopo
nenhum, dois testes de `tests/contract/console/test_console_first_run.py`
reprovaram — um arquivo pré-existente, não escrito por mim:

```
test_the_progress_count_is_not_recomputed_from_the_console_s_own_wizard_steps
test_the_checklist_heading_is_not_a_second_tally_beside_outstanding
```

O primeiro inspeciona o **texto-fonte** de `outstanding(setup)` em
`plan.ts` e falha se o corpo citar `WIZARD_STEPS` ou não citar
`setup.steps`. O segundo faz o mesmo para a chamada de `checklistTitle(...)`
em `first-run.tsx`. A minha implementação (seção original, T019) fazia
exatamente o oposto — `setupProgress()` derivava tudo de `WIZARD_STEPS`, e
o próprio docstring que eu tinha escrito ali **defendia essa escolha
explicitamente**, citando o argumento dos "dois denominadores" que motiva
esta feature inteira. Eu tinha, sem saber, revertido uma decisão que um
teste de contrato pré-existente já cravava — e nunca vi o teste, pelo
mesmo motivo da seção 14.5: o gate nunca chegou lá.

**Por que `setup.steps` e não `WIZARD_STEPS` vence**: o docstring do
próprio arquivo de teste explica — os sete passos do wizard são um
conceito de navegação do cliente, sem contrapartida no documento que
`GET /v1/setup/checklist` de fato serve; `setup.steps` é o array que esse
documento carrega, o mesmo que o CLI (`ninjasre onboard`) lê. Uma contagem
construída filtrando os sete passos do wizard é uma contagem que o CLI não
tem como reproduzir — CLI e console concordariam sobre três números
console-internos e discordariam do próprio terminal.

**O que ficou, e o que não**: a posição do wizard ("Step N de 7") continua
lida de `WIZARD_STEPS` — é um fato genuinamente diferente (qual das sete
*telas* está sendo mostrada), e nenhum dos dois testes de contrato pede
para mudar isso. O que mudou é que **nada mais compara essa posição contra
o total do checklist**: `outstanding(setup)` conta direto de `setup.steps`
(com o mesmo guard de `setup.complete` que `stepDone` já usa, para uma
implantação completa cujas linhas de passo individuais nunca foram
reescritas para `'done'`); `setupProgress()` perdeu o campo `step` e
deriva `{total, pending}` só de `setup.steps`; a chamada de
`checklistTitle(...)` em `first-run.tsx` passa a citar `outstanding(setup)`
e `setup.steps.length` textualmente, não `progress.total`/`progress.pending`
por trás de uma variável.

**Consequência que eu mesmo não previ**: meu próprio acceptance spec e a
suíte transversal tratavam "Step N de 7" como o mesmo `total` que o painel
e o card citam, e comparavam os três. Rodando contra o cenário `first-run`
(onde há números reais para comparar, não vácuo), isso reprovou:
`wizard header claims a total of 7 against dashboard card's 5`. Corrigido
nos dois arquivos (`020-confiabilidade-telas.acceptance.spec.ts`,
`transversal-rules.spec.ts`): `ProgressClaim.total` virou opcional, o
header do wizard não alimenta mais essa comparação (só `pending`, que
continua sendo o número genuinamente compartilhado pelas três
superfícies), e o `total` só é comparado entre as superfícies que de fato
o declaram (painel e card). Reconfirmado contra `first-run`: os dois
testes de contagem única passam com números reais — `4 de 5` no painel e
no card, `4 pendentes` no header do wizard (que já não declara "de 5").

**Testes de unidade tocados** (a lista completa, com a métrica): `console/
tests/unit/surfaces/first-run-plan.test.ts` (descrição inteira "setup
progress" reescrita — a versão anterior testava exatamente o
comportamento que este ciclo reverteu, incluindo um `progress.step` que
não existe mais), `first-run.test.tsx` (dois testes cujos títulos e corpos
testavam a comparação errada, reescritos para testar a divergência real —
`setup.steps` parcialmente feito vs. inteiramente feito, nunca contra
`WIZARD_STEPS`), `memory.test.tsx` (uma asserção de texto, "7 step(s)" →
"4 step(s)", número recalculado a partir da fixture `empty` de verdade,
não presumido). `npx vitest run --pool=forks`: **141 arquivos, 2299
testes, 0 falha**, reconfirmado depois de cada mudança.
`tests/contract/console/test_console_first_run.py`: **14 passed**
(incluindo os dois que motivaram tudo isto).

### 15.3 Os números da seção 4 e 9.3 estão desatualizados — a nota fica aqui

A derivação da seção 4 ("4 de 7", sob `WIZARD_STEPS`) e a confirmação da
seção 9.3 contra `first-run` descrevem a **primeira** versão de
`setupProgress()`, já revertida pela seção 15.2. Não fui reescrever as
duas por inteiro — o raciocínio ali (quais passos do checklist estão
feitos, por quê) continua correto — mas o número final mudou: sob o
código atual, painel e card citam **"4 de 5"** (`setup.steps.length = 5`,
4 não `'done'`), e o header do wizard continua dizendo "Step 3 de 7"
(posição, `WIZARD_STEPS`, inalterada) seguido de "4 steps left" — o mesmo
`4` do painel e do card, na mesma linha, sem mais declarar um "de 7"
que fosse comparável a eles.

### 15.4 Um projeto, um cenário — e por que a alegação (b) tem que se defender sozinha

`console/playwright.config.ts` serve um cenário só para a rodada inteira
do projeto `behaviour`, escolhido pelo runner (`--scenario`, `populated`
por padrão) — uma spec dentro de `tests/e2e/` não escolhe o seu. O gate
completo (`make verify` → `console-check` → o projeto `behaviour`
inteiro) roda sob `populated`, e é aí que a alegação sobre a exclusão
inteira ("a fetch hidden entirely behind the default actor filter is
declared, not silent") reprova: o estado que ela verifica só existe em
`audit-flooded`.

**Correção, sem enfraquecer a alegação**: o teste agora detecta em runtime
se o dataset servido está de fato na forma inundada — `(await
toggle.count()) === 0` — e usa `test.skip(condição, motivo por extenso)`
quando não está, no mesmo padrão de `EXCEPTIONS` (deste arquivo) e de
`expectedOverBudget` (`scroll-budget.spec.ts`): nomeado, não escondido,
sem citar feature nem onda. Sob `audit-flooded` a condição nunca é
verdadeira e o teste roda e prova a coisa de verdade — confirmado, não
presumido (abaixo). A alegação sobre "pelo menos uma linha" nunca precisou
de guarda: ela mesma pede `?audience=all` e funciona igual sob `populated`
(8 eventos, sem truncamento) e sob `audit-flooded` (200 de 156735) —
**não foi tocada**.

**Mapa final — qual alegação roda sob qual cenário**:

| Alegação | Arquivo:linha | Cenário do gate padrão (`populated`) | `--scenario audit-flooded` |
|---|---|---|---|
| (a) corpo tem linha, contagem bate | `020-...spec.ts:36` | roda e passa | roda e passa |
| exclusão inteira declarada | `020-...spec.ts:74` | **`test.skip`, motivo nomeado** | roda e passa de verdade |
| (b) presets de período | `020-...spec.ts:107` | roda e passa | roda e passa |
| (c) contagem única ×2 | `020-...spec.ts:226`, `transversal-rules.spec.ts:396` | passa vacuamente (`populated` não tem pendente) | passa vacuamente (herda o checklist completo de `populated`) — números reais só sob `first-run`, seção 15.2 |
| (d) SSO virgem | `020-...spec.ts:279` | roda e passa | roda e passa |
| (e) valor presente | `020-...spec.ts:308` | roda e passa | roda e passa |

**Provado nas duas direções, comando exato**:

```
uv run python -m tools.spec_validation browser --feature specs_v6/020-confiabilidade-telas \
  --test console/tests/e2e/020-confiabilidade-telas.acceptance.spec.ts \
  --test console/tests/e2e/transversal-rules.spec.ts
→ exit 0, 21 passed, 14 skipped, 0 failed (a exclusão inteira está entre os 14, com o motivo acima)

uv run python -m tools.spec_validation browser --feature specs_v6/020-confiabilidade-telas \
  --test console/tests/e2e/020-confiabilidade-telas.acceptance.spec.ts --scenario audit-flooded
→ exit 0, 7 passed, 0 skipped, 0 failed (a exclusão inteira está entre os 7 — roda e passa de verdade)
```

Reproduzido duas vezes cada, mesmo resultado. `typecheck`/`lint`/
`format-check` do console, limpos depois de toda a seção 15.

### 15.5 O padrão da seção 14.5, atualizado: o quarto e o quinto vieram no ciclo seguinte

A seção 14.5 fechou dizendo "a 030 que procure um quarto". Não precisou
esperar: os dois apareceram nesta mesma feature, um ciclo depois.

**Quarto**: a ordem do `verify` (`console-check` antes de `test`) faz uma
falha no console mascarar a suíte Python inteira. Isso não é só uma
observação abstrata desta vez — foi o motivo concreto pelo qual dois
testes de contrato pré-existentes, que reprovavam a minha própria
implementação desde o primeiro commit deste ciclo, ficaram invisíveis por
todo o tempo em que o `console-check` não passava. Quando finalmente
passou (seção 14) e a suíte Python rodou sem escopo pela primeira vez,
os dois apareceram imediatamente.

**Quinto**: `console/playwright.config.ts` serve um cenário só por rodada
do projeto `behaviour`. Uma spec de aceitação escrita para reproduzir um
estado que só existe num cenário-irmão tem que se defender sozinha —
detectar em runtime se o estado que ela verifica está de fato presente, e
declarar quando não está, ao invés de presumir que o cenário padrão do
gate é o mesmo cenário que a fixture da feature usou para provar o
defeito. Isto é diferente dos primeiros três (que eram sobre um comando
medir menos do que parecia): este é sobre uma spec assumir, sem checar,
que o ambiente em que ela é escrita é o mesmo em que ela vai rodar no
gate — o `EXCEPTIONS`/`test.skip` nomeado é o antídoto dos dois casos, e
por isso o padrão já existia no repositório antes desta feature
precisar dele.

## 16. Um verificador independente por fonte, dois achados reais em US1/US2, e as decisões do operador

Um verificador que leu o código-fonte (não o meu ledger) confirmou boa
parte deste trabalho por execução — 138 testes de unidade rodados de
verdade, `audit-flooded` genuinamente gerado (não hand-edited), a exceção
`HEALTHY` substantivamente verdadeira, a correção da fronteira RSC real, o
guard de `EffectiveFieldsTable` real, os dois "vermelhos invertidos"
(T030, T035) honestos — e encontrou dois furos que nenhum teste cobria.
Registrado por inteiro porque o primeiro reverte uma parte do que a seção
15.2 tinha acabado de fixar.

### 16.1 Achado 1 — US2 não se sustenta na tela; decisão do operador: corrigir o código

O painel (`screens/first-run.tsx`) e o card do dashboard (`setup-hero.
tsx`) desenhavam `planFor(setup)` — sete linhas sobre `WIZARD_STEPS`, cada
uma com um marcador feito/não-feito que uma pessoa consegue contar —
enquanto o número de pendentes ao lado vinha de `outstanding(setup)`
(seção 15.2), que conta um array **diferente**: `setup.steps` (5 itens
neste dataset). As três superfícies concordavam entre si trivialmente
(todas chamam a mesma `setupProgress()`), mas nenhuma concordava com as
linhas de fato desenhadas — o próprio teste que a seção 15.2 escreveu
prova isso (`first-run-plan.test.ts`, "the pending count is never the
seven wizard screens..."): aquela fixture dá `pending: 0` enquanto ~6 de 7
linhas do `plan` desenhavam como não-feitas. Seis ciclos não pegaram isso
porque a fixture `first-run` fazia as duas contagens coincidirem em 4.

**Decisão do operador**: a lista desenhada e a lista contada viram a
mesma lista. `outstanding()` continua lendo `setup.steps` (o teste de
contrato pré-existente da seção 15.2 crava isso, por paridade com o CLI);
logo é o **painel e o card que passam a desenhar `setup.steps`**, não o
contrário. `WIZARD_STEPS` continua sendo exatamente o que é — navegação
pelas sete telas — e o header do wizard pode continuar afirmando posição
("Step 3 de 7"), porque isso é um lugar num fluxo, não uma contagem de
checklist ao lado de outra contagem de checklist.

**O que mudou, em código**:
- `console/src/surfaces/first-run/plan.ts`: `DeploymentSetup` ganhou
  `next: string`, lido de `checklist.next` (`ChecklistView.next`,
  `gateway/http/routes/first_run.py` — já existia no backend, nunca lido
  antes) — o nome do passo do checklist que o próprio deployment aponta
  como seguinte, usado para destacar "you are here" sem inventar isso a
  partir de `WIZARD_STEPS`, que não tem correspondência item-a-item com
  `setup.steps` (`durable-credential` sozinho responde por dois passos do
  wizard; `integrations`/`verify` não respondem a nenhum passo do
  checklist).
- `console/src/surfaces/screens/first-run.tsx`: o painel de checklist
  agora mapeia `setup.steps` (não `plan`/`WIZARD_STEPS`) — status
  feito/não-feito de `step.state`, título do próprio `step.title` (texto
  do backend, o mesmo que o CLI mostra — não mais `firstRun.step.
  ${wizardStep}`), destaque de "aqui" via `step.name === setup.next`.
  `HANDOVER`/`handoverScreen`/`handoverHref` recodificados por nome de
  passo do checklist (`SOURCE_STEP`, `INVESTIGATION_STEP`) em vez de por
  `WizardStep` — os dois únicos passos do checklist que entregam a algo
  fora deste wizard, com a mesma lógica de antes. **Removida a navegação
  por linha** (cada linha era um `<Link>` para reabrir aquela tela do
  wizard): sem correspondência limpa entre 5 itens de checklist e 7 telas
  do wizard, um link por linha estaria inventando um destino. Reabrir uma
  tela específica continua funcionando pelo endereço (`?step=X`, coberto
  por teste já existente); o que se perde é só o atalho de clicar numa
  linha do checklist — nomeado aqui, não escondido.
- `console/src/surfaces/setup-hero.tsx`: o mesmo — `setup.steps` em vez de
  `plan`, destaque via `setup.next`. O botão único do card
  (`setup-hero-cta`) continua indo para `hrefFor(currentStep(setup))` —
  não muda, é uma ação de navegação única, não parte da contagem.
- `planFor`/`PlannedStep` (`plan.ts`) ficaram sem consumidor nestes dois
  arquivos — não removidos de `plan.ts` (a função continua correta e
  genericamente útil; só não há mais chamador dela nestes dois lugares).

**A asserção que faltava, adicionada em quatro lugares** — não uma
contagem afirmada comparada com outra contagem afirmada, mas uma
contagem afirmada comparada com o que se consegue contar na lista
desenhada:
- `console/tests/unit/surfaces/first-run.test.tsx` — "the number of rows
  drawn as not-done is the number the panel states as pending": conta
  `checklist-step` com `data-done="false"`, compara com o número extraído
  do texto de `first-run-progress`.
- `console/tests/unit/surfaces/dashboard.test.tsx` — o mesmo para
  `setup-hero-step`/`setup-hero-progress`.
- `console/tests/e2e/020-confiabilidade-telas.acceptance.spec.ts` e
  `console/tests/e2e/transversal-rules.spec.ts` (regra 3) — a mesma
  comparação em browser, nas duas superfícies, contra o build de produção
  real.

**Um bug de instrumento no caminho, e a razão de ele não invalidar nada**:
a primeira versão dos dois testes de browser usava um seletor CSS composto
(`'[data-testid="checklist-step"][data-done="false"]'`) e, contra uma
build desatualizada (rodada com `--no-build` reaproveitando uma build de
antes desta correção), encontrava zero linhas contra um "4" afirmado
corretamente. Investigado, reproduzido com uma build limpa: com a build
fresca, o problema desapareceu — mas troquei o seletor de qualquer jeito
para `getByTestId(...).all()` + `getAttribute('data-done')`, o mesmo
padrão já provado no teste de unidade, por ser mais robusto e não
depender de uma suposição sobre como um atributo booleano é serializado
pelo renderer de servidor. Confirmado depois, com build fresca: os dois
testes passam com números reais sob `--scenario first-run` (não
vacuamente) — ver 16.4.

**Testes de unidade ajustados** para a nova forma (`checklist-step`,
`setup-hero-step`, `data-name`, `data-done`, `data-current`, sem `href`):
`first-run.test.tsx` (a contagem de linhas passou de 7 para 5; o teste
"makes every step a link" foi **substituído** por um que verifica o
oposto — nenhuma linha é mais um link, com o motivo por extenso; o mapa
de handover passou a nomear `infrastructure-source`/`first-investigation`
em vez de `estate`/`alerts`), `dashboard.test.tsx` (mesma correção de
contagem, 7→5). `npx vitest run --pool=forks`: **141 arquivos, 2301
testes, 0 falha** (2299 + 2 pelos dois testes novos da asserção que
faltava). `npx vitest run --coverage`: os quatro limiares de 90%
continuam cobertos (branches 90.29%, o mesmo da seção 14).
`tests/contract/console/test_console_first_run.py`: **14 passed**,
incluindo os dois testes que motivaram esta correção inteira — rodado por
mim, como pedido.

### 16.2 Achado 2 — SC-003 é falso como estava escrito; decisão do operador: estreitar o critério, manter o texto de ajuda

`authorization_endpoint`/`token_endpoint`/`jwks_uri` aparecem no texto de
ajuda de campo (`console/src/i18n/en.ts`, espelhado em `pt-BR.ts`),
desenhado incondicionalmente a cada carga por `components/form.tsx`. SC-003
dizia "zero identificadores em snake_case no texto visível" — a tela
mostra três. A asserção de aceitação já verificava só o padrão
`_id is required`/`_uri is required`/etc. (texto no formato de erro), então
ela passava — corretamente, para o que verificava — enquanto o critério,
como estava escrito, era empiricamente falso para "todo texto visível".

**Decisão do operador**: o texto de ajuda fica. Nomear a chave OIDC exata
genuinamente ajuda quem está procurando por ela na página de descoberta do
próprio provedor, e removê-la pioraria o produto para satisfazer uma
frase. O critério é que estava largo demais.

**O que mudou**:
- `specs_v6/020-confiabilidade-telas/spec.md`: SC-003, a segunda cláusula
  de FR-014, e o Independent Test de US3 — os três reescritos para
  escopar a proibição de snake_case a **mensagem de erro ou de
  validação**, com uma nota entre parênteses em cada um explicando por que
  o texto de ajuda de campo é uma exceção deliberada, não um furo.
- `console/tests/e2e/020-confiabilidade-telas.acceptance.spec.ts`: o
  título do teste (d) passou de "no raw identifiers" (largo demais, o
  mesmo excesso do critério original) para "no raw identifiers in a
  validation message", com um comentário citando exatamente o que a
  regex verifica e por que o texto de ajuda não conta. **A regex em si
  não mudou** — já estava corretamente escopada a texto no formato "X is
  required"; o que estava errado era a alegação sobre o que ela cobre.

### 16.3 Achado 3 (menor) — uma entrada morta em `EXCEPTIONS`, removida

`/settings/autonomy-guardrails` + `scroll-budget` estava simultaneamente
em `EXCEPTIONS` e em `SCROLL_BUDGET_MEASURED_ELSEWHERE`, e o teste da
regra de rolagem chama `test.skip(...)` (checando o segundo) antes de
chegar em `test.fixme(...)` (que consultaria o primeiro) — a entrada em
`EXCEPTIONS` nunca era alcançada. Cobertura líquida inalterada; removida,
com um comentário no lugar dela explicando por que essa combinação
específica não tem entrada.

### 16.4 Resultado final, com os comandos exatos e build fresca

```
npx vitest run --coverage
→ 141 arquivos, 2301 testes, 0 falha; branches 90.29%, os quatro limiares cobertos

uv run python -m tools.spec_validation browser --feature specs_v6/020-confiabilidade-telas \
  --test console/tests/e2e/020-confiabilidade-telas.acceptance.spec.ts \
  --test console/tests/e2e/transversal-rules.spec.ts
→ exit 0, 23 passed, 14 skipped, 0 failed (build fresca, não --no-build)

uv run python -m tools.spec_validation browser --feature specs_v6/020-confiabilidade-telas \
  --test console/tests/e2e/020-confiabilidade-telas.acceptance.spec.ts --scenario audit-flooded
→ exit 0, 8 passed, 0 failed

uv run python -m tools.spec_validation browser --feature specs_v6/020-confiabilidade-telas \
  --test console/tests/e2e/020-confiabilidade-telas.acceptance.spec.ts \
  --test console/tests/e2e/transversal-rules.spec.ts --scenario first-run
→ exit 1, 21 passed, 2 failed (esperados — ver seção 9.3, alegações (a)/(d) não se aplicam a
  este dataset), 14 skipped — as duas novas asserções de "linhas desenhadas vs. número
  afirmado" e as duas de contagem única passam com números reais ("4 de 5")

  [Reconciliado pelo orquestrador contra reprodução independente do spec-verifier: a
  contagem "19 passed" registrada aqui era anterior às asserções acrescentadas mais
  adiante no mesmo ciclo e nunca foi re-somada nesta linha. As duas falhas esperadas são
  as mesmas nas duas execuções; só o número de aprovados cresceu.]

uv run pytest tests/contract/console/test_console_first_run.py -q
→ 14 passed

uv run pytest tests/contract/console/ -q
→ 343 passed, 1 failed — a falha é test_console_visual_regression.py::
  test_the_untouched_baselines_still_match, a mesma consequência já
  nomeada na seção 11 (baselines que o operador está revisando à parte,
  revertidas para HEAD na árvore; o código que as produziria mudou, a
  imagem committed não). **Correção da linha que estava aqui antes**: eu
  tinha escrito "nem /first-run nem / são 'baselined' hoje" — errado para
  `/`, verificado agora de novo por leitura direta e não por lembrança;
  ver seção 17.2 para o estado real das cinco rotas e por que a seção 11
  (não esta linha) já estava certa.
```

`typecheck`, `lint`, `format-check` do console: limpos depois de toda a
seção 16. `console/visual/baselines/` não tocado (o operador segue
revisando as capturas).

## 17. `first-day`, a captura visual e o 404 de config-fields

### 17.1 `first-day.spec.ts` — teste corrigido para a intenção, não para o número

`tests/first-day/first-day.spec.ts:243` (`killing the browser mid-flow
loses nothing, because nothing was kept`) reprovava: `data-testid="wizard-
step"` estava nas sete `<Link>` do painel de checklist antigo, removidas
pela seção 16.1. Eu não rodava o projeto `first-day` até este ciclo —
corrigido daqui em diante: passa a fazer parte da minha própria validação,
junto com `behaviour`.

O que a contagem de 7 provava não era "sete", era "o wizard voltou no seu
estado completo, não persistido" — a mesma alegação que a asserção de
`data-step` logo acima já prova em parte (o passo certo, derivado do
deployment, não de um cursor guardado no navegador). Trocar `7` por `5`
teria mantido a suíte verde sem provar mais nada de novo sobre isso — só
o número certo da fixture de hoje.

**Correção**: em vez de um número escrito no teste, o teste agora **deriva
sua própria referência** do primeiro contexto (genuinamente fresco, antes
de qualquer ação que "lembraria" algo) — `const expectedSteps = await
page.getByTestId('checklist-step').count()`, com uma asserção de sanidade
que ele não é zero — e compara a contagem do **segundo** contexto (depois
de matar o primeiro) contra essa referência, exatamente o mesmo padrão já
usado para `derived`/`data-step` duas linhas acima. Isso prova a mesma
alegação ("nada a mais, nada a menos — o mesmo checklist completo que uma
visita genuinamente fresca desenha") sem depender de um número escrito à
mão que uma mudança de fixture tornaria errado sem tornar a alegação
errada. `uv run python -m tools.console_e2e run --project first-day
--backing mock --scenario first-run` (o par que o próprio gate usa —
`tools/console_gate.py`'s `end_to_end()` fixa `first-day` contra o
cenário `first-run`, nunca outro): **15 passed, 0 failed**. `--project
behaviour` inteiro, reconfirmado depois de toda a seção 17: **167 passed,
20 skipped, 0 failed**.

### 17.2 As cinco rotas de baseline, verificadas de novo, com a linha errada corrigida

A seção 16.4 escreveu "nem `/first-run` nem `/` são 'baselined' hoje" —
**errado para `/`**, e a seção 11 (mais antiga) já tinha isso certo para
`/first-run`. Reverifiquei agora as cinco por leitura direta e estruturada
de `console/visual/screens.json` (parse JSON, não grep), porque uma
lembrança errada já vazou para este documento uma vez neste mesmo ciclo:

| Rota | Entradas | `status` | Tocada por qual achado |
|---|---|---|---|
| `/first-run` | `first-run-1440-light` (1) | **pending** — sem baseline committed | Achado 1 (seção 16.1) |
| `/` (dashboard) | `shell-1440-dark`, `shell-1440-light`, `shell-320-light`, `shell-768-light` (4) | **baselined**, as quatro | Achado 1 (seção 16.1) |
| `/settings/notifications` | `notifications-1440-light` (1) | **baselined** | Ciclos anteriores (T032/T036) |
| `/settings/single-sign-on` | `single-sign-on-1440-light` (1) | **baselined** | Ciclos anteriores (T026/T027) |
| `/settings/machine-tokens` | `machine-tokens-1440-light` (1) | **baselined** | Ciclos anteriores (correção RSC, seção 12) |

Ou seja: a seção 11 estava certa sobre `/first-run` (pending, precisa de
baseline nova quando alguém decidir capturá-la — nada a "regredir" porque
não há imagem committed para comparar). Eu estava errado ao generalizar
isso para `/` também. `/` tem quatro baselines committed, e este ciclo
(seção 16.1) mudou o que `setup-hero.tsx` desenha por dentro — mas
`SetupHero` retorna `null` quando `source.status === 'ready' && progress.
pending === 0` (`setup-hero.tsx`), e a captura visual roda sempre contra o
cenário `populated` (`scripts/visual.mjs`, fixo), cujo checklist está
completo — então, sob o dataset que as quatro baselines de `/` foram
capturadas contra, `SetupHero` não desenhava nada antes desta mudança e
continua não desenhando nada agora. Isso torna uma diferença de pixel
**improvável**, não **impossível** — eu não capturei nem comparei para
confirmar, por instrução: não toquei `console/visual/baselines/` nem rodei
a suíte visual. O escopo real do que está pendente de revisão, portanto,
são as três rotas de configuração já nomeadas (notifications,
single-sign-on, machine-tokens) mais, possivelmente, `/` — a diferença
entre "possivelmente" e "certamente" só a captura decide, e essa captura é
do operador.

### 17.3 O 404 de `/v1/config/{node_id}/fields` — já degrada honestamente, rastreado até a fonte

O log do `first-day` mostra `GET /v1/config/org-northwind/fields → 404`
repetido — esperado sob o cenário `first-run`/`empty`: o nó do viewer
ainda não tem documento de configuração próprio. Rastreei a cadeia
inteira, por leitura, sem presumir:

1. `console/src/surfaces/read.ts:43-55` (`panelRead`, o que as seis
   páginas do raio de alcance usam para este fetch, não `optionalRead`
   nem `readProjectedPanel`): um 404 vira `ApiError`, capturado, devolvido
   como `{status: 'error', dependency}` — nunca lançado adiante.
2. `console/src/surfaces/read.ts:129-131` (`dataOf`): para `status:
   'error'`, devolve `undefined`.
3. `console/src/surfaces/editable.ts` (`editableFields`), via
   `list()`/`field()` (`read.ts:136-138`, `158-161`): `field(undefined,
   'fields')` é `Reflect.get(Object(undefined), 'fields')` —
   `Object(undefined)` é `{}`, então isso é `undefined`, nunca lança;
   `list()` sobre isso devolve `[]`. `editableFields(undefined)` devolve
   `[]`, nunca lança.
4. `console/src/surfaces/effective-fields.ts` (`effectiveRows`): com o
   catálogo vazio, `byPath.get(spec.path)` é `undefined` para toda
   especificação — o mesmo ramo já coberto pelo teste de unidade "marks a
   field the catalogue does not declare as not set, rather than throwing
   or drawing a blank" (`effective-fields.test.ts`) — devolve `value:
   message(locale, 'configuration.value.notSet')`, nunca uma célula vazia.

Ou seja: um fetch inteiro falhando (404) e um campo que o catálogo
simplesmente não declara colapsam na mesma linha de código
(`byPath.get(path) === undefined`) e produzem o mesmo resultado honesto —
"Not set", nunca uma célula vazia, nunca uma exceção. Não escrevi um teste
novo dedicado a "o fetch inteiro falhou": o caminho que essa falha
realmente percorre (catálogo vazio → linha "Not set") já é exatamente o
caminho que `effective-fields.test.ts` prova, e as 15 execuções do
`first-day` contra este 404 real, repetido em múltiplas páginas, não
mostraram nenhum lançamento nem coluna vazia — decisão registrada, não
escondida: se o operador quiser um teste que force especificamente um 404
nesta rota (em vez de um catálogo vazio por outro motivo), essa é uma
lacuna que fica nomeada aqui, não uma que fica desconhecida.
