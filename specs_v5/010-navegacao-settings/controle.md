# Controle — Navegação híbrida e shell de Settings

Estado abaixo verificado contra o código atual da árvore de trabalho (HEAD
`2f4a842`, working tree suja com as mudanças desta feature). Cada linha cita
o `file:line` que a sustenta. Nada aqui foi escrito a partir de intenção —
onde eu não tinha uma verificação (teste rodado, ou leitura direta do
arquivo final), digo isso explicitamente.

**Gate central já medido pelo orquestrador nesta árvore, com estes números,
que uso como referência**: `pnpm exec vitest run` → 1985 passed, 127
arquivos, 0 failed (baseline da onda: 1967/127 — **+18 testes**);
`pnpm exec tsc --noEmit` → limpo; `uv run pytest tests/contract/console/` →
42 passed; `uv run python -m tools.spec_validation browser --test
console/tests/e2e/settings-nav.spec.ts` → 11 passed (projeto `behaviour`,
backing `mock`); `uv run python -m tools.spec_validation visual` → 9
passed, 27 pendentes de aceitação de baseline (ver §5).

---

## 1. Ledger — Functional Requirements

| FR | Estado | Detalhe |
|---|---|---|
| FR-001 — sidebar com exatamente Integrations + Settings no grupo Settings | FEITO | `console/src/shell/routes.ts:220-350`: `first-run`, `signals`, `autonomy`, `configuration`, `administration` ganharam `visible: () => false` incondicional; `integrations` (:248-257) e o novo `settings` (:264-273) são os dois únicos que sobram visíveis nesse grupo. Verificado em `console/tests/e2e/settings-nav.spec.ts:34-48` (e2e, verde) e `console/tests/unit/shell/chrome.test.tsx:64-78` (unit, verde, com a query escopada a `p` para não colidir com o rótulo "Settings" do próprio nav-entry). |
| FR-002 — subnav com Organization/Agent/Data e as 9 páginas nomeadas | FEITO | `routes.ts:477` (`SETTINGS_GROUPS`), `routes.ts:513-597` (`SETTINGS_PAGES`, as 9 entradas, ids/paths/grupos/labels). Verificado em `console/tests/unit/shell/routes.test.ts` (describe `'the Settings subnav manifest'`, teste `'puts every page in the group the mockup assigns it, in the mockup order'`) e em `settings-nav.spec.ts:70-91`. |
| FR-003 — cada página declara a permissão do gateway, copiada por nome | FEITO para 4 das 9 (rota real conferida); inferida (sem rota dedicada ainda) para as outras 5 | Ver tabela completa em §2. As 4 com rota real (`members-roles`, `single-sign-on`, `machine-tokens`, `audit-log`) são conferidas 1:1 contra `ROUTE_TABLE` em `tests/contract/console/test_console_shell.py:233-252` (`SETTINGS_PAGE_ROUTE` + `test_a_settings_page_takes_the_permission_the_gateway_requires_of_its_data`). As outras 5 (`models-providers`, `autonomy-guardrails`, `notifications`, `alert-intake`, `schedules-destinations`) usam uma permissão real do enum (`config.write` ou `config.read`, nunca inventada) copiada do domínio mais próximo que já existe (a área `autonomy` para as duas primeiras, a área `signals` para as duas últimas) — não há hoje uma rota do gateway dedicada a essas 5 para conferir 1:1, então o teste que as cobre é o genérico `test_every_declared_permission_is_one_the_platform_has` (`tests/contract/console/test_console_shell.py:139-143`, existente, inalterado), que só prova que a string é um `Permission` real, não que é a rota certa. Isto é uma inferência minha, não um fato verificado contra uma rota — nomeado explicitamente para 040/050/060 confirmarem ou corrigirem. |
| FR-004 — grupo sem página alcançável é omitido por inteiro | FEITO | `routes.ts:641-647` (`settingsGroupsFor`, mesma construção de `groupsFor`). Verificado em `routes.test.ts`, teste `'drops a whole subnav group when nothing in it is permitted, the same rule groupsFor follows'`. |
| FR-005 — toda rota antiga redireciona para a nova, incluindo variantes de `?tab=` | FEITO, com duas exceções deliberadas e nomeadas (ver §3) | `routes.ts:678-687` (`SETTINGS_REDIRECTS`) + `console/src/shell/legacy-redirect.ts:14-34` (`legacyRedirectHref`, preserva query além de `tab`) + os três route files reescritos (`console/src/app/(shell)/autonomy/page.tsx`, `.../administration/page.tsx`, `.../signals/page.tsx`). Verificado tanto em unit (`console/tests/unit/shell/route-files.test.tsx`, describe `'a retired route file'`, :123-167) quanto em e2e (`settings-nav.spec.ts:151-204`, 7 testes, todos verdes contra um browser real). |
| FR-006 — wizard sai da sidebar, vive em rota própria, regra de visibilidade migra para os pontos de entrada | FEITO | `routes.ts:220-237` (`first-run` com `visible: () => false` incondicional, comentário explica a troca). `console/src/app/(shell)/first-run/page.tsx:23-34`: com checklist completo redireciona para `/`; incompleto, renderiza o wizard sem mudança. O "convite" nos pontos de entrada é `SetupHero` (`console/src/surfaces/setup-hero.tsx`) — **este componente já existia antes desta feature e eu não o toquei**; verifiquei que ele já lê `outstanding(setup)` de forma independente do mecanismo `Area.visible`, então continua funcionando sem qualquer mudança minha. Verificado ponta a ponta em `console/tests/first-day/first-day.spec.ts:238-253` (e2e, `--scenario empty`, verde) e a metade "redireciona quando completo" em `route-files.test.tsx`, describe `'the first-run route, both ways'` (unit, verde). |
| FR-007 — paleta e busca global indexam as páginas de Settings por nome de exibição | **NÃO INICIADO** | Conferi o arquivo inteiro `console/src/shell/commands.ts` (209 linhas) linha por linha: `commandsFor` (:167-188) só compõe `navigationCommands` (baseado em `AREAS`, :61-74), `runCommands` e `actionCommands`. Não existe nenhuma função que leia `SETTINGS_PAGES`/`visibleSettingsPages` e produza `Command`s. `console/src/shell/palette.tsx` não foi tocado. Isto é a pendência mais importante desta entrega — ver §4. |
| FR-008 — breadcrumb e título refletem Settings → grupo → página via `trailFor` | FEITO para 8 das 9 páginas; gap nomeado para 1 (ver §4) | `console/src/shell/area.tsx:134-161` (`SettingsPageHeader`, monta a trilha com `trailFor(areaFor('settings'), [{grupo}, {página}, ...nested])`, reaproveitando `trailFor` de `routes.ts:445-462` sem alterá-lo). Usado pelas 6 páginas EmptyState em `console/src/app/(shell)/settings/{single-sign-on,machine-tokens,models-providers,notifications,alert-intake,schedules-destinations}/page.tsx` (via `NotBuiltSettingsPage`, `console/src/surfaces/screens/settings-not-built.tsx:29-47`) e por `.../members-roles/page.tsx` e `.../audit-log/page.tsx` diretamente. A exceção é `autonomy-guardrails`: `console/src/surfaces/screens/autonomy.tsx:262-267` continua chamando `<AreaHeader area={areaFor('autonomy')} .../>` (o comentário nessas linhas explica a decisão e diz explicitamente "`controle.md` records it") — a página mostra o cabeçalho "Autonomy" antigo, não a trilha "Settings → Agent → Autonomy & guardrails". Decisão deliberada, não descoberta tarde: dividir `AutonomyScreen` (603 linhas) em cabeçalho+corpo para trocar só o cabeçalho tinha risco desproporcional ao orçamento desta feature, e a tela é reaproveitada inteira e sem modificação pelas suítes que já a testam. |
| FR-009 — manifesto de rotas continua sendo a única resposta a "que rotas existem" | FEITO | `SETTINGS_PAGES` (`routes.ts:513-597`) segue o mesmo contrato de comentário que `AREAS` — `id: '...'` logo após a chave, sem comentário antes — então `declared_areas()` (`tests/contract/console/test_console_shell.py:75-99`, não tocada) já enxerga as 9 páginas automaticamente, sem eu precisar duplicar o parser. `test_the_console_declares_the_nine_settings_pages_the_subnav_needs` (`test_console_shell.py:161-174`) prova que as 10 entradas (9 páginas + o hub) são visíveis a esse parser. |

## 2. As nove páginas — rota, permissão, o que renderiza agora

Herança para 040/050/060.

| Página | Grupo | Rota nova | Permissão (copiada do gateway, por nome) | O que renderiza nesta fase | `file:line` |
|---|---|---|---|---|---|
| Members & roles | Organization | `/settings/members-roles` | `identity.read` — igual a `GET /identity/principals` (`gateway/http/security/route_permissions.py:202`) | **Tela atual equivalente**: `PeopleTab` de `administration.tsx`, exportado e reaproveitado sem alteração de lógica, sob o cabeçalho próprio de Settings | `console/src/app/(shell)/settings/members-roles/page.tsx`; export em `console/src/surfaces/screens/administration.tsx:91` |
| Single sign-on | Organization | `/settings/single-sign-on` | `sso.manage` — igual a `GET/PUT /identity/sso` (`route_permissions.py:220-221`) | **EmptyState declarado** — nenhuma tela hoje é dedicada a SSO (só um painel dentro de `PeopleTab`) | `console/src/app/(shell)/settings/single-sign-on/page.tsx` |
| Machine tokens | Organization | `/settings/machine-tokens` | `token.manage` — igual a `GET/POST /identity/tokens` (`route_permissions.py:189-190`) | **EmptyState declarado** — mesma razão | `console/src/app/(shell)/settings/machine-tokens/page.tsx` |
| Audit log | Organization | `/settings/audit-log` | `audit.read` — igual a `GET /audit/events` (`route_permissions.py:236`) | **Tela atual equivalente**: `AuditTab` de `audit.tsx`, já exportado antes desta feature, reaproveitado sem alteração, sob cabeçalho próprio | `console/src/app/(shell)/settings/audit-log/page.tsx` |
| Models & providers | Agent | `/settings/models-providers` | `config.write` — **inferida**, sem rota dedicada; nenhuma tela hoje lê ou escreve "modelo escolhido" fora do editor cru e do wizard | **EmptyState declarado** | `console/src/app/(shell)/settings/models-providers/page.tsx` |
| Autonomy & guardrails | Agent | `/settings/autonomy-guardrails` | `config.write` — igual à área `autonomy` atual (`routes.ts:307`) | **Tela atual equivalente**: `AutonomyScreen` inteira, sem modificação de lógica (só o cabeçalho é a exceção do FR-008, ver acima) | `console/src/app/(shell)/settings/autonomy-guardrails/page.tsx` |
| Notifications | Agent | `/settings/notifications` | `config.write` — **inferida**, sem rota dedicada; nenhuma tela no console lê ou escreve política de notificação hoje | **EmptyState declarado** | `console/src/app/(shell)/settings/notifications/page.tsx` |
| Alert intake | Data | `/settings/alert-intake` | `config.read` — copiada da área `signals` atual (`routes.ts:293`); `GET /v1/transit/ingress` também usa `config.read` (`gateway/http/security/gateway_routes.py:209`) | **EmptyState declarado** — decisão explícita do orquestrador de não reaproveitar `IntakeTab` ainda (ver §3 sobre o efeito colateral nos testes) | `console/src/app/(shell)/settings/alert-intake/page.tsx` |
| Schedules & destinations | Data | `/settings/schedules-destinations` | `config.read` — mesma razão; `GET /v1/transit/destinations` também usa `config.read` (`gateway_routes.py:212`) | **EmptyState declarado** — mesma decisão, não reaproveita `DestinationsTab`/`SchedulesTab` | `console/src/app/(shell)/settings/schedules-destinations/page.tsx` |

O texto do EmptyState (`console/src/surfaces/screens/settings-not-built.tsx:29-44`) nomeia o próprio grupo ("this page is part of the {group} rework, which has not shipped yet") e volta para `/settings`, nunca para o editor cru.

## 3. Tabela de redirecionamento

| Rota antiga | Variante | Destino | `file:line` |
|---|---|---|---|
| `/autonomy` | qualquer | `/settings/autonomy-guardrails` | `console/src/app/(shell)/autonomy/page.tsx:16` |
| `/administration` | nenhuma, ou `?tab=people` | `/settings/members-roles` | `routes.ts:680-681`; `administration/page.tsx:18` |
| `/administration` | `?tab=audit` | `/settings/audit-log` (demais filtros preservados — `actor`, `action`, `audience`, `since`) | `routes.ts:682`; `legacy-redirect.ts:14-34` |
| `/signals` | nenhuma, ou `?tab=intake` | `/settings/alert-intake` | `routes.ts:683-684`; `signals/page.tsx:33` |
| `/signals` | `?tab=destinations` ou `?tab=schedules` | `/settings/schedules-destinations` | `routes.ts:685-686` |
| `/first-run` | — | **Condicional, fora da tabela**: checklist completo → `/`; incompleto → wizard renderiza sem redirecionar | `first-run/page.tsx:28-33` (lê `loadSetup` diretamente, não usa `SETTINGS_REDIRECTS` porque depende de dado, não só de path+tab) |

**Duas rotas deliberadamente NÃO redirecionam:**

- **`/configuration`** — a spec pede isso com todas as letras (US2, cenário 3: "continua servindo o editor atual" até a 070). `routes.ts:311-315` (comentário) e `configuration/page.tsx` (arquivo não tocado).
- **`/signals?tab=observation`** — nenhuma das nove páginas de Settings substitui "continuous observation" (o mockup só lista Alert intake e Schedules & destinations no grupo Data); `emptiness.ts`'s `watchingCause` (`console/src/surfaces/emptiness.ts:64-71`, não tocado) continua apontando para exatamente este endereço com `query: {tab: 'observation'}`. Redirecionar essa variante quebraria essa CTA, mandando quem clica "nada está observando" para uma página que fala de outra coisa. `signals/page.tsx:30-32`.

**Descoberta importante, não antecipada no início**: redirecionar `/signals?tab=intake` e `?tab=destinations` — exigido literalmente pela FR-005/US2 cenário 2 — torna inalcançável por navegação a funcionalidade real e testada que vivia lá (simulação de payload de webhook, trava de salvar após editar, reenvio de entrega falha, cadeia de proveniência). Não é um efeito que eu tenha escondido: **6 testes e2e pré-existentes em `console/tests/e2e/surfaces.spec.ts` foram marcados `test.describe.skip` (bloco `'retired by the hybrid navigation, pending the Data pages'`, a partir da linha 190 do arquivo final), não apagados**, com o motivo escrito no próprio arquivo (linhas 175-189, ver também §4 item 0 sobre uma referência a `specs_v5/010` que ficou nesse comentário). O código por trás (`IntakeTab`/`DestinationsTab` em `console/src/surfaces/screens/data.tsx`) não foi tocado e continua coberto por `console/tests/unit/surfaces/data.test.tsx` e `ingress.test.tsx` — só o endereço que um navegador alcança sumiu, até a 060 dar um lar de verdade a essas duas páginas. **Isto é o achado mais significativo desta entrega fora do próprio FR-007** e deveria pesar na sequência da onda.

## 4. O que fica pendente, nomeado, não escondido

0. **Identificadores proibidos que sobraram em arquivo commitado — quatro, não dois.** O orquestrador já achou e me avisou de dois em `console/src/shell/routes.ts`: `"feature 030 rebuilds it as a wizard"` (linha 223, comentário da área `first-run`) e `` "`EmptyState` feature 001 built" `` (linha 502, comentário de `SETTINGS_PAGES`). Ao reler os arquivos que o `prettier` reformatou eu achei **mais dois, que também são meus**: `console/tests/e2e/surfaces.spec.ts:175` — `` "the hybrid navigation (`specs_v5/010`) redirects..." `` — e `console/tests/first-day/first-day.spec.ts:241` — `` "The hybrid navigation (`specs_v5/010`) retired..." ``. Os quatro citam número de feature ou caminho de `specs_v5/`, proibido em arquivo commitado (ninguém que clona o repositório tem esses documentos). **Não conserto agora** — a regra desta rodada final proíbe tocar código; fica para quando o gate soltar os arquivos, com a substância dita sem o número: "a hybrid navigation" em vez de "specs_v5/010", "the wizard rebuild" em vez de "feature 030", "the EmptyState feature 001 built" → "the EmptyState this shell already carries".
1. **FR-007 / T012 / o edge case de busca global — NÃO INICIADO.** `console/src/shell/commands.ts` e `console/src/shell/palette.tsx` não foram tocados nesta entrega; a paleta de comandos (Ctrl+K) não oferece nenhuma das 9 páginas de Settings por nome. Pertence a esta mesma spec (010) — é uma task numerada dela, não de 040/050/060 — mas não coube no tempo desta rodada. A implementação é pequena e localizada (uma função `settingsPageCommands(viewer, locale)` análoga a `navigationCommands`, composta dentro de `commandsFor`), mas não a escrevi: a regra desta rodada final foi não tocar código.
2. **FR-008, Autonomy & guardrails — breadcrumb parcial.** Documentado em §1. Pertence a esta spec; fica para quem tocar `autonomy.tsx` de novo (070, provavelmente, quando a tela for reconstruída de qualquer forma).
3. **T013 — sem teste unitário dedicado para `SettingsPageHeader`.** O mecanismo funciona (provado indiretamente por e2e e pelos testes já existentes de `trailFor`/`AreaHeader` em `console/tests/unit/shell/edges.test.ts`), mas não escrevi um `console/tests/unit/shell/*.test.tsx` que renderize `SettingsPageHeader` isoladamente e afirme sobre a trilha "Settings → Agent → X". Pendência desta spec.
4. **Edge case "viewport estreito, sem 2ª barra horizontal" — não verificado especificamente para Settings.** Implementado (`settings-subnav.tsx:39-45` — a rail, escondida com `hidden md:flex` — e `:82-115` — o `<select>` que a substitui com `md:hidden`, mesmo padrão responsivo do `Sidebar`), mas não escrevi um teste e2e equivalente a `shell.spec.ts`'s `'does not run off the side of a 320-pixel viewport'` visitando uma página `/settings/*`. Pendência desta spec.
5. **US1 cenário 2 / FR-004 — matriz completa por papel não escrita para `SETTINGS_PAGES`.** Existe para `AREAS` (`console/tests/unit/shell/role-matrix.test.tsx`, todo papel × toda área), mas para as 9 páginas de Settings só escrevi verificações pontuais (`routes.test.ts`, 2-3 viewers específicos) — mais fraco que o padrão já estabelecido para áreas. Real, comprovado apenas pela e2e contra o viewer real da `populated` (ver item 7). Pendência desta spec.
6. **SC-001 — não é literalmente um estudo de usabilidade.** Provado estruturalmente (1 clique Settings + 1 clique subnav = 2 cliques, `settings-nav.spec.ts:95-124`), não como as "dez tarefas com um operador novo" que o Independent Test da US1 descreve — isso não é automatizável por um agente e a spec não pede que seja.
7. **Incoerência herdada em `fixtures/scenarios/populated/principal.json`, agora visível.** O principal `role: owner` desse fixture concede `identity.read`, `token.manage` e `audit.read` (mesmo incremento de `Role.ADMIN`, `platform/identity/permissions.py:186-197`) mas **não** concede `sso.manage`, que está no mesmo incremento. Nenhuma atribuição real de papel produz esse conjunto. Isto é anterior a esta feature — a 010 só o tornou visível porque agora "Single sign-on" é uma entrada própria da subnav em vez de um painel condicional dentro de uma tela maior. Hoje, com esse fixture, a subnav mostra 8 das 9 páginas para esse principal (falta só Single sign-on). Comentado em `console/tests/e2e/settings-nav.spec.ts:76-78` e `:104`, com o teste de `:133-140` provando que a página em si existe e é honesta ao ser aberta direto. Não é pendência desta spec (não é meu fixture para corrigir), mas nomeio para quem for revisar `fixtures/scenarios/*/principal.json` depois.
8. **Um teste e2e de `first-day` que eu não consegui atribuir com confiança.** `console/tests/first-day/first-day.spec.ts:91` (`'the guided run walks provider to verification without leaving the shell'`) falha consistentemente (não é flake — rodei duas vezes) num timeout esperando `getByTestId('integration-offer').first().locator('input[type="password"]')` em `/first-run?step=integrations`, **depois** que o teste já percorreu com sucesso os passos provider/credential/model/integrations/verify/estate/alerts e um `PUT /v1/integrations/anthropic/credential` real. Não toquei em nenhuma lógica de `FirstRunScreen` nem no passo "integrations" — só a página wrapper (`first-run/page.tsx`) ganhou uma checagem condicional ANTES de chamar `FirstRunScreen`, que os outros 4 testes de `first-day` (incluindo os que atravessam vários passos do wizard) provam não interferir. Não sei se isto é uma flakiness do `--backing mock` para esse round-trip específico ou algo real. **Não reparei porque a regra desta rodada final proíbe tocar código**; nomeio para o orquestrador reproduzir e decidir.
9. **`test_the_untouched_baselines_still_match` e os 3 testes de `test_console_gate.py` que vi falhar numa rodada minha anterior.** Rodei `pytest tests/contract/console/ tests/architecture/` uma vez (antes da regra de não rodar comandos) e vi 5 falhas: 3 em `test_console_gate.py::test_the_same_check_passes_once_the_fixture_is_gone` (variantes `format-check`/`lint1`/`lint2`), `test_console_visual_regression.py::test_the_untouched_baselines_still_match`, e `test_one_fictional_deployment.py::test_exactly_one_fictional_deployment_exists_in_the_repository`. A última cita arquivos em `console/playwright-report/data/*.md` — artefatos de relatório do Playwright que minhas próprias rodadas de e2e deixaram na árvore, não código-fonte. A de baseline visual é consistente com os "27 pendentes de aceitação" que o orquestrador já mediu e explicou (§5) — não uma regressão nova. As 3 de `test_console_gate.py` rodam `eslint`/`prettier` de verdade como subprocesso; não sei se colidiram com alguma outra execução concorrente na mesma árvore. **Não voltei a rodar para confirmar** porque a regra desta rodada final proíbe. Meus próprios `uv run python -m tools.console_gate lint` e `... typecheck` e `... test`, rodados isoladamente antes dessa lista de 5, saíram limpos (lint: `0 problems`; typecheck: `tsc --noEmit` sem saída; test: 127 arquivos, 1985 testes, cobertura 94.44/90.57/91.46/96.52 — todos acima do piso de 90). Não reivindico as 5 falhas como resolvidas nem como minhas — nomeio como não investigadas a fundo.

## 5. O que o orquestrador já apurou e que fica registrado aqui

- **`console/src/lib/swatch.tsx`, removido pelo orquestrador.** O orquestrador me avisou que removeu esse arquivo por conter três violações deliberadas do design system (cor crua `#0f6f5c`, `p-9` fora da escala, `transition: all 250ms`) dentro de `src/`, e o atribuiu a mim. **Não reconheço este arquivo como meu**: não criei nada em `console/src/lib/` nesta feature — todo o meu trabalho está listado em §7 e §8, e nenhuma dessas entradas é `lib/swatch.tsx` ou qualquer coisa parecida. Não tenho no meu próprio histórico desta sessão nenhuma chamada de escrita para esse caminho. Não estou contestando que o arquivo existiu na árvore nem a remoção — só não confirmo a autoria. Possível explicação: outra sessão trabalhando em paralelo na mesma árvore compartilhada (a onda tem várias specs rodando; `CLAUDE.md` do usuário já registra "concurrent editing in console/ tree" como um padrão conhecido deste repositório). Se havia um motivo real para ele existir — fixture de violação para algum guard de design system — não fui eu quem o escreveu com essa intenção.
- **Os 27 baselines visuais divergentes são esperados, não uma falha minha, e a aceitação não é minha decisão.** A sidebar mudou em toda tela que a desenha (grupo Settings reduzido a 2 entradas), então toda captura que a contém difere do baseline commitado. O orquestrador conferiu `administration-1440-light` e confirmou que a diferença é exatamente a migração esperada (sidebar reduzida, subnav Organization/Agent/Data, trilha `Settings › Organization › Members & roles`, `/administration` redirecionado). Eu não rodei `console-visual-accept` nem qualquer coisa equivalente — os 27 continuam pendentes de aceitação humana.
- **Um baseline (`console/visual/baselines/administration-1440-light.png`) ficou corrompido (9.298 bytes contra 151.336 no HEAD, um retângulo preto sólido) por uma captura interrompida quando o processo anterior foi encerrado no teto de turno.** O orquestrador já restaurou esse arquivo do HEAD com `git checkout --`. Eu não o toquei nesta rodada nem vou recapturá-lo.

## 6. Onde eu não vi o vermelho antes da implementação — por item, sem inventar confirmação

- **T001** (chaves i18n): não vi um vermelho isolado para este item. Adicionei as chaves em `en.ts` e `pt-BR.ts` na mesma passada; o teste que teria acusado uma chave pt-BR ausente (`tests/unit/i18n/catalogue.test.ts`, pré-existente, não tocado) nunca rodou contra um estado em que só uma das duas catalogações tivesse a chave nova.
- **T004, os testes que eu mesmo escrevi** (`test_the_console_declares_the_nine_settings_pages_the_subnav_needs` e as 4 variantes de `test_a_settings_page_takes_the_permission_the_gateway_requires_of_its_data`): não os vi vermelhos antes de existirem — foram escritos depois que a T003 já estava implementada na árvore, e passaram já na primeira execução. O vermelho que **eu genuinamente vi e confirmei rodando** foi o do teste pré-existente `test_the_deploy_walk_covers_exactly_the_areas_the_console_declares`, que falhou como consequência direta e não planejada da T003 (`1 failed, 30 passed` na minha execução), antes de eu escrever o ajuste que o torna verde de novo.
- **T008** (reduzir `sidebar.tsx`): não há vermelho para este item porque não há mudança de código neste arquivo — a redução é inteiramente uma consequência de `routes.ts`'s `visible` mais a lógica pré-existente de `groupsFor`. O vermelho que eu vi foi indireto: os testes que dependiam da composição ANTIGA da sidebar (`chrome.test.tsx`, `role-matrix.test.tsx`, `shell.spec.ts`) quebraram como efeito colateral de `routes.ts`, e eu os corrigi depois de rodá-los e ver a falha real.
- **T011** (first-run sai da sidebar, redireciona quando completo): implementei a lógica condicional em `first-run/page.tsx` diretamente, sem escrever antes um teste que a exigisse. O vermelho que eu vi foi **depois** da implementação: rodar a suíte já existente (`route-files.test.tsx`, `tests/unit/surfaces/role-matrix.test.tsx`, `tests/unit/surfaces/screens.test.tsx`) revelou 3+ falhas causadas por essa mudança, que investiguei (conferindo `fixtures/scenarios/populated/setup-checklist.json` tem `"complete": true`) antes de decidir que o código estava certo e eram as suposições dos testes antigos que precisavam mudar. Os testes dedicados que provam as duas pernas do comportamento (`route-files.test.tsx`, describe `'the first-run route, both ways'`) foram escritos depois, para confirmar, não antes, para exigir.
- **T012**: não aplicável — não há implementação, então não há vermelho a reportar; é `NÃO INICIADO`, listado em §4.
- **T005, T009, T010, T002**: nestes eu vi o vermelho genuinamente, antes da implementação que os fecha, confirmado rodando o comando real (não inferido): T002 (`pnpm exec vitest run tests/unit/shell/routes.test.ts` → 20 failed antes de estender `routes.ts`), T009 (mesmas 20 falhas — as 5 do describe do redirect estavam no mesmo lote), T010 (`route-files.test.tsx`'s `'a retired route file'` → "Number of calls: 0" antes de reescrever os três route files), T005 (`tools.spec_validation browser` → 2 de 11 falhando na primeira execução real contra navegador).

## 7. Arquivos criados

```
console/src/shell/settings-subnav.tsx
console/src/shell/legacy-redirect.ts
console/src/surfaces/screens/settings-not-built.tsx
console/src/app/(shell)/settings/layout.tsx
console/src/app/(shell)/settings/page.tsx
console/src/app/(shell)/settings/members-roles/page.tsx
console/src/app/(shell)/settings/single-sign-on/page.tsx
console/src/app/(shell)/settings/machine-tokens/page.tsx
console/src/app/(shell)/settings/audit-log/page.tsx
console/src/app/(shell)/settings/models-providers/page.tsx
console/src/app/(shell)/settings/autonomy-guardrails/page.tsx
console/src/app/(shell)/settings/notifications/page.tsx
console/src/app/(shell)/settings/alert-intake/page.tsx
console/src/app/(shell)/settings/schedules-destinations/page.tsx
console/tests/e2e/settings-nav.spec.ts
```

## 8. Arquivos modificados

```
console/src/shell/routes.ts                              — SettingsPage, SETTINGS_PAGES, redirect table, visible:false em 5 áreas
console/src/shell/area.tsx                                — SettingsPageHeader, settingsPageMetadata
console/src/i18n/en.ts                                    — chaves do hub, grupos e 9 páginas
console/src/i18n/pt-BR.ts                                 — idem, pt-BR brasileiro; nomes de página/grupo em inglês (decisão da spec)
console/src/app/(shell)/autonomy/page.tsx                 — vira redirect
console/src/app/(shell)/administration/page.tsx           — vira redirect (tab-aware)
console/src/app/(shell)/signals/page.tsx                  — redirect exceto ?tab=observation
console/src/app/(shell)/first-run/page.tsx                — redirect condicional ao checklist
console/src/surfaces/screens/administration.tsx           — PeopleTab exportado (só isso; corpo inalterado)
console/src/surfaces/screens/autonomy.tsx                 — comentário explicando o gap do FR-008; sem mudança de comportamento
console/tests/unit/shell/routes.test.ts                   — estendido (T002/T009)
console/tests/unit/shell/role-matrix.test.tsx              — exclusão nomeada das áreas aposentadas da sidebar
console/tests/unit/shell/route-files.test.tsx              — bijeção ajustada, describe de redirects e de first-run
console/tests/unit/shell/chrome.test.tsx                   — 3 asserções que citavam 'administration'/'signals' realinhadas
console/tests/unit/shell/palette.test.tsx                  — 4 buscas por 'signals' trocadas por 'knowledge'
console/tests/unit/shell/shell.test.tsx                    — 1 busca por 'signals' trocada por 'knowledge'
console/tests/unit/support/screens.ts                      — signals/autonomy/administration via adaptador (screen function direta, não mais a rota)
console/tests/unit/surfaces/autonomy.test.tsx               — renderiza AutonomyScreen direto, não mais via page.tsx (que agora redireciona)
console/tests/unit/surfaces/outage.test.tsx                 — exclui 'settings' (sem tela); acrescenta describe para as 3 páginas Settings que reusam tela aposentada
console/tests/unit/surfaces/role-matrix.test.tsx             — exclui first-run (redireciona sob o cenário 'populated' que este arquivo serve)
console/tests/unit/surfaces/screens.test.tsx                 — idem, 2 describes
console/tests/e2e/shell.spec.ts                              — AREAS reduzido, busca de paleta realinhada
console/tests/e2e/surfaces.spec.ts                           — 6 testes de /signals?tab=intake|destinations movidos para test.describe.skip, nomeado (ver §3)
console/tests/first-day/first-day.spec.ts                    — 1 teste realinhado ao SetupHero em vez do nav-entry antigo
tests/contract/console/test_console_shell.py                 — SETTINGS_PAGE_ROUTE, 5 testes novos, exclusão de 'settings*' no deploy-walk
```

## 9. Gates rodados, e seu resultado real

| Gate | Resultado | Quando/como |
|---|---|---|
| `pnpm exec vitest run` (console inteiro) | **1985 passed, 127 arquivos, 0 failed** | Medido pelo orquestrador nesta árvore, depois das minhas correções finais. Eu mesmo tinha rodado o equivalente antes (127 arquivos, 1985 testes) e visto o mesmo resultado. |
| `pnpm exec tsc --noEmit` | **limpo** | Medido pelo orquestrador; eu também rodei antes e obtive saída vazia. |
| `uv run python -m tools.console_gate lint` | **limpo** (`0 problems`, após eu corrigir um `require-await` em `settings-not-built.tsx`) | Rodado por mim. |
| `uv run python -m tools.console_gate typecheck` | **limpo** | Rodado por mim. |
| `uv run python -m tools.console_gate test` (com cobertura) | **127 arquivos, 1985 passed**; cobertura 94.44/90.57/91.46/96.52 (piso 90) | Rodado por mim. |
| `uv run pytest tests/contract/console/test_console_shell.py` | **36 passed** (31 originais + 5 novos) | Rodado por mim, isolado. |
| `uv run pytest tests/contract/console/` (arquivo inteiro) | **42 passed** | Medido pelo orquestrador. |
| `make check-imports` | **7 contratos mantidos, 0 quebrados**, 1672 arquivos | Rodado por mim. |
| `make check-constants` | **limpo** | Rodado por mim. |
| `make check-console-boundary` | **limpo** | Rodado por mim. |
| `uv run python -m tools.spec_validation browser --test tests/e2e/settings-nav.spec.ts` | **11 passed** | Rodado por mim (2 execuções — a primeira pegou o vermelho real do `sso.manage`, corrigi o teste, a segunda saiu verde) e confirmado pelo orquestrador. |
| `uv run python -m tools.spec_validation browser --test tests/e2e/shell.spec.ts` | **23 passed** | Rodado por mim, depois de realinhar `AREAS` e a busca de paleta. |
| `uv run python -m tools.spec_validation browser` (agent/budgets/gallery/network/proposals/scroll-budget/surfaces/vocabulary) | **48 passed, 6 skipped** (os 6 nomeados no §3) | Rodado por mim. |
| `uv run python -m tools.spec_validation browser --project first-day --scenario empty` | **4 passed, 1 failed** (o teste nomeado no §4, item 8) | Rodado por mim, duas vezes (a segunda para descartar flake — falhou igual as duas vezes). |
| `uv run python -m tools.spec_validation visual` | **9 passed, 27 pendentes de aceitação de baseline** | Medido pelo orquestrador (ver §5) — eu não rodei o gate visual nem `console-visual-accept`. |
| `pytest tests/contract/console/ tests/architecture/` (a dupla junta) | **5 failed, 480 passed** numa execução minha isolada | Ver §4, item 9 — não investigado a fundo, não reproduzido de novo. |
| `make verify` completo | **Não rodado por mim** | É gate do orquestrador (`AGENTS.md` raiz, seção "Codex Spec-Wave Adapter": "Run focused gates after each feature, make verify at wave checkpoints"); a regra final desta rodada também proibiu explicitamente rodar comandos. |
| `make test-postgres`, `make chaos-*`, `make preflight` | **Não rodados** | Fora do escopo desta feature (nenhuma mudança em `platform/persistence/` ou runtime de agente). |
