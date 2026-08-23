# Dossiê de confronto — onda specs_v5

Registro do orquestrador (Opus 5) sobre a execução da onda `specs_v5` por
subagents `spec-implementer` (Sonnet 5, effort max).

**Regra deste arquivo**: nada aqui é copiado do relatório do subagent. Toda
linha é o que **eu** abri, rodei ou li na árvore depois que o subagent
terminou. Onde o relatório do subagent e a árvore discordam, a discordância
fica escrita, com as duas versões.

Legenda de veredito:

| Veredito | Significado |
|---|---|
| **CONFIRMADO** | Abri o `file:line` / rodei o teste; a alegação se sustenta. |
| **CONFIRMADO (já existia)** | Verdadeiro na árvore, mas não é obra desta spec. |
| **PARCIAL** | Parte da obrigação está na árvore, parte não. |
| **REFUTADO** | O subagent alegou e a árvore não sustenta. |
| **NÃO ALEGADO / PENDENTE** | Obrigação do ledger que ninguém fechou. |

---

## 0. Baseline da árvore, antes de qualquer subagent

Colhido em 2026-08-14, antes da primeira delegação.

- **HEAD**: `6fb1525` — *chore: untrack the constitution, join the rest of spec-kit's local scaffolding*
- **Branch**: `master`
- **Working tree**: apenas ` M .gitignore` (a linha `/specs_v5/`, adicionada
  para manter a onda fora do repositório, coerente com `specs_v2..v4`).
- **`make verify`**: _(resultado registrado abaixo, seção 0.1)_

### 0.1 Resultado do `make verify` de baseline — **VERMELHO**

`make verify` completo, 2026-08-14, árvore em `6fb1525` com nada além de
` M .gitignore`. Log: `scratchpad/gates/baseline-verify.log`.

Passou tudo até o pytest:

- `lint`, `format-check`, `typecheck`
- `check-imports` — 1672 arquivos, 7921 dependências, **7 contratos mantidos, 0 quebrados**
- `check-constants`, `check-protocols`, `check-deps`, `check-vendor-sdks`,
  `check-literals`, `check-raw-sql`, `check-credentials`, `check-console-boundary`
- `verify-integrations` — **85 integrações em paridade total**, toda permissão sondada
- `check-integration-docs`, `check-env-example`, `check-docs`, `check-doc-examples` (29 exemplos)
- `console-check` completo: prettier, eslint + css-literals, `tsc --noEmit`,
  **1945 testes vitest em 125 arquivos**, cobertura 95.34% stmts / 90.91% branches /
  93.05% funcs / 97.57% linhas (piso 90), client-check, budget, `next build`,
  e2e `behaviour`, `first-day` e `visual` (baselines batendo)

E então **`make test` reprovou**: `3 failed, 14031 passed, 25 skipped` em 9m21s.

**As três falhas são anteriores à onda. Nenhuma tem relação com specs_v5.**
Ficam registradas aqui porque, sem este baseline, a primeira validação as teria
debitado do subagent.

| # | Teste | Causa raiz |
|---|---|---|
| 1 | `tests/contract/integrations/test_integration_parity.py::test_each_paginated_endpoint_declares_a_style_the_base_client_walks[google_gemini]` | O contrato exige que toda integração declare um estilo de paginação. `google_gemini` é a única de categoria `MODEL_PROVIDER` e seu cliente expõe só `ping()` — não há segunda página para pedir. O teste é anterior à existência dessa categoria. |
| 2 | `tests/unit/tools/test_console_smoke.py::test_a_route_that_does_not_answer_200_is_named` | O teste quebrava `/catalogue`, rota que **deixou de existir** no commit `c3f0595` ("fold nineteen destinations into thirteen"). O walk nunca a visitava, então o stub não respondia a ninguém e a asserção comparava vazio com vazio. |
| 3 | `tests/unit/tools/test_console_smoke.py::test_the_command_refuses_the_deploy_when_a_route_is_broken` | Mesma causa: `/catalogue` quebrada, walk não visita, comando não recusa, `assert 0 == 1`. |

### 0.2 Correção das três, antes de qualquer delegação

Decisão do operador em 2026-08-14: resolver antes de iniciar a onda. Feito.

**Falha 1** — `tests/contract/integrations/test_integration_parity.py`.
Um provedor de modelo está no catálogo para que sua chave seja alcançável pelo
proxy de credencial, não porque tem API para percorrer. Inventar um endpoint
paginado para satisfazer a regra seria uma declaração sobre uma API que ninguém
chama. A isenção é por categoria e **se auto-policia**: `vendor_endpoints()`
subtrai o que o cliente-base dá e o `ping`, e a isenção só vale enquanto sobrar
zero. No dia em que um provedor ganhar uma chamada que devolve lista, o teste
falha e ele declara estilo como qualquer outro vendor.

**Falhas 2 e 3** — `tests/unit/tools/test_console_smoke.py`. Trocar `/catalogue`
por `/integrations` (a rota que a absorveu) conserta as duas, mas não conserta a
classe: um teste que nomeia rota por string volta a apodrecer no próximo
rearranjo. Então o stub ganhou `Console.breaks(*paths)`, que **recusa** um
caminho fora de `SHELL_PATHS` com a mensagem dizendo o que o walk visita.
Verificado: `breaks('/catalogue')` levanta; `breaks('/autonomy')` passa.

Arquivos tocados por esta correção (fora do escopo de qualquer spec da onda):

- `tests/contract/integrations/test_integration_parity.py` — `BASE_CLIENT_COROUTINES`,
  `REACHABILITY_CHECK`, `vendor_endpoints()`, e a isenção no teste de paginação.
- `tests/unit/tools/test_console_smoke.py` — `Console.breaks()` e os dois testes.

Gates rodados sobre a correção: `pytest` dos dois arquivos (**93 passed**),
`ruff check` (limpo), `ruff format --check` (formatado), `mypy` (sem problemas).
Confirmação do pytest completo: seção 0.3.

### 0.3 Baseline verde — o número contra o qual a onda é medida

`uv run pytest` completo, depois das três correções, na mesma árvore:

```
========== 14034 passed, 25 skipped, 15 warnings in 551.92s (0:09:11) ==========
EXIT=0
```

Log: `scratchpad/gates/baseline-pytest-fixed.log`. **14034 = 14031 + as três**,
que é exatamente o esperado e nenhuma a mais: a correção não mudou contagem de
teste em lugar nenhum além dos dois arquivos tocados.

O resto do `make verify` (lint, format-check, typecheck, 7 contratos de import,
todos os guard checks, 85 integrações, `console-check` inteiro) permanece o de
§0.1 — verde, e não foi tocado por esta correção, que mexeu só em dois arquivos
de teste Python.

**O número contra o qual toda feature desta onda é medida:**

| Gate | Baseline |
|---|---|
| `pytest` | 14034 passed, 0 failed, 25 skipped |
| vitest (`console-test`) | 1945 passed, 125 arquivos, cobertura 95.34/90.91/93.05/97.57 |
| `check-imports` | 7 contratos mantidos, 0 quebrados |
| `verify-integrations` | 85 em paridade total |
| Playwright | `behaviour` + `first-day` + `visual` verdes, baselines batendo |

---

## 0.4 Correções feitas nas próprias specs, antes de delegar

Auditoria dos 50 caminhos que as specs da onda citam, conferidos contra a
árvore. Decisão do operador em 2026-08-14: "então arruma as specs" — corrigir a
spec, não só avisar o subagent.

**Classe 1 — testes em caminho que runner nenhum coleta.** Sistêmico, nas oito
features. Um teste ali não roda, e um teste que não roda é evidência
fabricada — exatamente o defeito que o `spec-implementer` foi escrito para não
cometer.

| Antes | Depois | Fato da árvore |
|---|---|---|
| `console/e2e/*.spec.ts` (8×) | `console/tests/e2e/` | `console/e2e/` não existe; Playwright tem `testDir: 'tests'`, projeto `behaviour` em `tests/e2e` |
| `console/src/design/status.test.ts` | `console/tests/unit/design/status.test.ts` | vitest coleta só `tests/unit/**/*.test.ts(x)` |
| `console/src/design/empty-state.test.tsx` | `console/tests/unit/design/empty-state.test.tsx` | idem |
| `console/src/shell/routes.test.ts` | `console/tests/unit/shell/routes.test.ts` | idem |

Registrado também em `specs_v5/README.md`, seção "Onde os testes moram", porque
o subagent lê o README antes da própria spec.

**Classe 2 — instruções que mandavam construir o que já existe, ou construir
onde a arquitetura proíbe.**

| Spec | O que dizia | O que a árvore diz |
|---|---|---|
| 001 / T002 | "criar teste falhando" | `console/tests/unit/design/status.test.ts` **já existe** — estender, não substituir |
| 001 / T014 | teste do `Reference` sem caminho nenhum | agora nomeia `console/tests/unit/design/reference.test.tsx` |
| 001 / T018 | "≤ 2 viewports em 1080p" | viewport global do Playwright é `1440×900` fixo; o spec tem de declarar `1920×1080` a partir da constante de T001, senão a onda inteira mede errado e passa |
| 001 / T008-T009 | "registro de exibição", local não fixado | mora em `IntegrationProfile` (`integrations/_catalogue/entry.py:80`), no pacote do vendor. Mapa central quebra o desenho declarado em prosa no módulo: "adicionar uma integração edita zero arquivos existentes". `__post_init__` (`entry.py:100`) já levanta para `summary` vazio — é onde `display_name` vazio deve morrer |
| 001 / T017 | "remover contagens locais" | a recomputação tem endereço: `console/src/surfaces/first-run/plan.ts:188` |
| 020 / T001 | "fixture com 84 itens" | a árvore tem **85**; o total vem de `catalogue()`, nunca do literal |
| 030 / T003 | "criar `first-run/steps.ts`" | `first-run/plan.ts` **já é** o modelo de passos: `WIZARD_STEPS` (plan.ts:24) tem exatamente os sete do mockup-4, `planFor` (plan.ts:222) resolve feito/atual/href. Criar `steps.ts` produziria a fonte dupla que a feature existe para matar |

Os demais caminhos ausentes são arquivos a criar (`empty-state.tsx`,
`settings/sso.tsx`, `settings/schedules.tsx`, …) — ausência legítima.

## Ordem de execução adotada

O README declara as dependências; a execução é **sequencial**, uma feature por
vez, e não em paralelo, apesar de o README permitir paralelismo entre 020/030 e
entre 040/050/060. Motivo registrado para confronto: as features desta onda
compartilham arquivos de escrita única — `console/src/i18n/en.ts`,
`console/src/i18n/pt-BR.ts`, `console/src/shell/routes.ts`,
`console/visual/screens.json` — e dois subagents editando o mesmo arquivo na
mesma árvore de trabalho perdem escrita um do outro sem aviso. Sequencial
também é o único modo em que cada validação minha mede uma feature de cada vez.

| Ordem | Spec | Depende de | Estado |
|---|---|---|---|
| 1 | 001-fundacao-vocabulario-ux | — | **entregue e confrontada** — §1 |
| 2–8 | 010 … 070 | — | fora do escopo desta sessão; o operador executa com outra configuração |

---

# 1. 001-fundacao-vocabulario-ux — confronto

Subagent: `spec-implementer` (Sonnet 5, effort max), 774k tokens, 463 chamadas
de ferramenta, 1h54. Briefing entregue: `briefings/COMUM.md` + `briefings/001.md`.
Relatório do subagent: `001-fundacao-vocabulario-ux/controle.md`.

## 1.1 O que eu abri e rodei, e o que encontrei

Nada abaixo vem do relatório dele. Tudo é o que eu abri ou rodei depois.

| O que ele alegou | Como eu conferi | Veredito |
|---|---|---|
| Guard `check-display-names` reprova um id sem nome | Apaguei o `display_name` de `integrations/alertmanager/__init__.py` e rodei o guard | **CONFIRMADO** — exit 1, mensagem nomeando `alertmanager`; restaurei o arquivo |
| A invariante mata na construção, antes do guard | `integrations/_catalogue/entry.py:121-126` | **CONFIRMADO** — `__post_init__` levanta `ValueError` com a consequência escrita |
| Guard ligado ao `make verify` | `Makefile:23`, `:294`, `:382` | **CONFIRMADO** |
| Os dois specs e2e novos rodam | `pnpm exec playwright test --list --project=behaviour` | **CONFIRMADO** — 12 testes novos coletados, `Total: 85 tests in 10 files` (baseline: 8 arquivos) |
| `scroll-budget` mede 1080p, não herda 1440×900 | `console/tests/e2e/scroll-budget.spec.ts:38-54` | **CONFIRMADO** — `constant()` lê `config/constants/surfaces.py` **do disco** e levanta se a declaração sumir; `test.use({viewport})` com 1920×1080 |
| `outstanding()` lê `setup.steps` | `console/src/surfaces/first-run/plan.ts:199` | **CONFIRMADO** — e os 5 consumidores (`emptiness`, `setup-hero`, `first-run`, `dashboard`, o próprio módulo) chamam a mesma função |
| `resolveCta` recusa rota fora do manifesto | `console/src/design/empty-state.ts:37-52` | **CONFIRMADO** — `areaByPath` + `throw`, não um `href` livre |
| `EmptyState` já exigia verbo (já existia) | `console/src/components/state.tsx:49-64` | **CONFIRMADO (já existia)** — levanta para `body` e para `action.label` em branco |
| 85 vendors com `display_name` | Amostra dos 85 | **CONFIRMADO** — estilização de marca certa nos casos difíceis: `incident.io`, `flagd`, `groundcover`, `Rocket.Chat`, `Argo CD`, `VictoriaMetrics` |
| Suíte Python verde fora da divergência visual | `uv run pytest` completo, eu mesmo | **CONFIRMADO** — `1 failed, 14043 passed, 25 skipped`; a única falha é a visual |
| Benchmark de masking foi flake de carga | Mesma rodada | **CONFIRMADO** — passou |
| 8 baselines visuais divergem | `tools.console_visual compare`, eu mesmo | **CONFIRMADO** — as mesmas 8, e **28 outras telas idênticas**, que é a prova de que a migração não vazou |

## 1.2 O que eu encontrei que ele não reportou

**Violação da regra de identificadores de requisito.** O arquivo novo
`tests/contract/console/test_console_display_registry.py:3` abria com
"FR-003's rule is one sentence" — identificador que aponta para um documento
que quem clona o repositório não tem, e que o briefing proibia explicitamente.
Único caso em toda a entrega (varri os 8 arquivos criados). **Corrigido por
mim**: a frase seguinte já dizia a substância, então o identificador saiu sem
custo.

**Português europeu no catálogo pt-BR** — `activo`, `contacta`, `contactar`,
`acção`, `Actividade`, `Detectores activos` (`console/src/i18n/pt-BR.ts:323,
373, 378, 436, 475, 496`). **Não é desta entrega**: o diff dele adiciona 10
linhas e remove 8, e nenhuma das adicionadas contém europeísmo. É defeito
pré-existente, sobrevivente do commit `0c4f35e`, que corrigiu só os verbos de
salvar e excluir. Fica nomeado aqui para uma correção à parte.

## 1.3 A decisão que era minha, não dele

Os 8 baselines visuais. Ele **corretamente se recusou** a rodar
`console-visual-accept` — nenhuma task dele pedia, e um gate que fabrica a
própria evidência é o defeito que o agente existe para não cometer.

Conferi antes de aceitar: o diff de `integrations-1440-light` toca **só** a
faixa de estado dos três cards (chips no lugar de "UNCONFIGURED", "Verified —
the last check passed", "Failing — the last check found a problem"); o resto da
página está idêntico. O diff da galeria tem a assinatura de **inserção** — o
vermelho começa num ponto e segue até o fim, porque `StatusChip` entrou na
lista e empurrou o conteúdo abaixo — não de regressão.

Recapturado por mim com `make console-visual-accept`. Resultado: exatamente 8
PNGs alterados, nem um a mais, e `compare` 36/36.

## 1.4 O que fica pendente, herdado do controle e conferido por mim

Todos estes estão nomeados no `controle.md` dele, o que é o comportamento certo.
Nenhum é regressão; todos são escopo que a spec 001 não fecha sozinha.

- **FR-005/SC-003** — 23 CTAs em 9 arquivos ainda apontam para `/configuration`.
  Não migrados porque hoje não existe destino melhor; as telas humanas são
  020/030/040/050/060. `T012` ficou **PARCIAL** e desmarcado, honestamente.
- **FR-006/US4** — o bloco "known gaps" do catálogo não foi recolhido em
  `Reference`. Ele achou um conflito real: `console/tests/unit/surfaces/behaviour.test.tsx:216-234`
  consulta os itens sem expandir nada, e `Reference` não renderiza `children`
  quando recolhido. `T015` ficou **PARCIAL**. A 020 provavelmente reconstrói a
  tela inteira.
- **SC-004** — o orçamento de rolagem mede contra o dataset mock (3
  integrações), não contra "84 integrações, 15 tokens, 200 eventos". O
  instrumento existe e lê a altura real; ele vai flagar quando 020/050
  povoarem os fixtures na escala real.
- **FR-001** — o vocabulário é consumido só pelo console; CLI e notificações
  não foram varridos.
- **FR-011** — as 13 áreas do console têm subtítulo de prosa sob o título
  (`page.<area>.context`). Viola a letra do requisito e **antecede** esta
  entrega. Corrigir é mexer no cabeçalho de todas as telas do produto.

## 1.5 Veredito e commit

`make verify` completo, por mim, depois da recaptura dos baselines: **EXIT=0**.

| Gate | Baseline | Depois da 001 |
|---|---|---|
| `pytest` | 14034 passed, 0 failed | **14044 passed, 0 failed**, 25 skipped |
| vitest | 1945 em 125 arquivos | **1967 em 127 arquivos** |
| cobertura console | 95.34/90.91/93.05/97.57 | **95.36/90.92/93.09/97.58** (piso 90) |
| `check-imports` | 7 mantidos, 0 quebrados | idem |
| `verify-integrations` | 85 em paridade total | idem |
| Playwright behaviour | 73 | **85** (+12: os dois specs novos) |
| Playwright visual | 36 | **36**, com 8 baselines recapturados |

Commitado na branch `feat/v5-001-fundacao-vocabulario-ux`, por caminho
explícito, em três commits:

- `c03a18c` — `chore:` o `.gitignore` que mantém a onda fora do repositório
- `1e2cf04` — `fix:` as duas correções de baseline (§0.2)
- `41022c8` — `feat:` a feature, 139 arquivos

Fora do commit, por instrução do operador: `tools/spec_validation.py` e
`tests/unit/tools/test_spec_validation.py`, que são dele. Confirmado que a
árvore de trabalho não guarda mais nada além desses dois.

## 1.6 Duas descobertas dele que valem para quem vier depois

- **`fixtures/scenarios/*/integrations.json` são gerados, não escritos.** A
  fonte é `tools/mockplane/dataset/served.py` e `build.py`;
  `tests/contract/fixtures/test_dataset_coherence.py` existe para pegar edição
  manual, e pegou.
- **Fixtures com `steps: []` são um formato que o gateway real nunca produz.**
  Mudar `outstanding()` para ler `setup.steps` quebrou 7 testes em 6 arquivos
  não relacionados que fingiam esse formato. Ele corrigiu os 6 fixtures em vez
  de contornar.

---

# 2. 010-navegacao-settings — confronto

Subagent: `spec-implementer` (Sonnet 5, effort max). **Três paradas por teto**:
526k tokens/151 chamadas, depois 762k/276, depois 888k/314 — mais uma falha por
limite de conta no meio. Retomado por `SendMessage` a cada vez, com os achados
exatos. Briefing: `briefings/COMUM.md` + `briefings/010.md`.

## 2.0 O que o orquestrador fez com as próprias mãos

Registrado primeiro porque muda a leitura de tudo abaixo: parte desta entrega é
minha, não dele, e é confrontável no mesmo pé.

- **FR-007/T012 implementada por mim.** Ele reportou "NÃO INICIADO" e eu
  confirmei: nenhuma função derivava `Command`s de `SETTINGS_PAGES`,
  `palette.tsx` intocado. Test-first, vermelho visto (`no palette command
  reaches /settings/members-roles`). `settingsCommands`
  (`console/src/shell/commands.ts`), composta em `commandsFor`, mais dois
  testes. **Função nova em vez de alargar `navigationCommands`**: o teste
  pré-existente "offers every area the viewer may reach, and no other" define
  aquela função como sendo exatamente as áreas, e minha primeira tentativa —
  devolver áreas + páginas dali — quebrou esse teste. Redefinir contrato
  testado para caber código novo é como um teste deixa de significar o que diz.
- **Nove identificadores proibidos removidos**, em três varreduras sucessivas:
  o implementer achou 4, eu achei 3 que ele não viu (`shell.spec.ts:25`, dois em
  `test_console_shell.py`), e o `spec-verifier` achou 2 que **eu** não vi
  (`settings-not-built.tsx:13` "Feature 001's", `routes.ts:499` "040, 050 and
  060") — meu padrão de busca exigia "feature" minúsculo e a palavra literal.
  Junto: português vazado em comentário inglês (`routes.ts`, "a current tela
  equivalente") e duas referências a `controle.md`, arquivo commitado
  dependendo de não-commitado.
- **Formatação**: 10 arquivos reprovavam `prettier --check` e derrubavam o
  `make verify` antes dos testes.
- **`console/src/lib/swatch.tsx` retirado da árvore.** Não referenciado por
  nada, com três violações deliberadas do design system (cor crua, espaçamento
  fora da escala, duração crua) dentro de `src/`. **O implementer nega tê-lo
  criado**, e a árvore é compartilhada com outras sessões: mtime 22:20:22, numa
  janela em que ele constava como morto. **Não atribuído.** Guardado, não
  apagado.
- **Baseline preto restaurado duas vezes — e a causa não é de ninguém desta
  onda.** `console/visual/baselines/administration-1440-light.png`, 9.298 bytes
  contra 151.336 no HEAD, retângulo preto das mesmas dimensões. Culpei o worker
  primeiro, e estava **errado**.

  A causa é `tests/contract/console/test_console_visual_regression.py:109-126`.
  `test_a_seeded_pixel_change_fails_the_run_and_emits_a_diff` pega
  `committed_baselines()[0]` — que em ordem alfabética é **exatamente este
  arquivo** — grava `blank_like(original)` por cima, roda a comparação para
  provar que ela reprova, e restaura num `finally`. **Um pytest interrompido
  deixa o branco commitado na árvore.** É a única coisa no repositório que
  produz esse artefato preciso: mesmas dimensões, arquivo 16× menor.

  Duas hipóteses minhas foram descartadas por experimento antes de eu achar
  esta: restaurei e rodei `spec_validation visual` — o arquivo **sobreviveu**,
  então não é a ferramenta de comparação; e o `git status` mostra que nenhum
  subagent tocou em `console/visual/`. **Nem o implementer nem o verificador
  causaram isto**, e o registro anterior que dizia "foi uma captura do worker"
  fica retratado aqui.

  **Quem interrompia era eu.** Isolei depois: rodar só
  `test_console_visual_regression.py` até o fim deixa o arquivo **intacto** — o
  `finally` funciona. O que mata o `finally` é o processo levar SIGKILL antes
  dele, e foi o meu `timeout 300` numa rodada do diretório inteiro que fez isso:
  o teste semeador leva ~98s sozinho e não cabia no que sobrava do orçamento.

  Fragilidade herdada, real e sem dono: **qualquer** interrupção de pytest —
  `timeout`, Ctrl-C, OOM, runner de CI cancelado — deixa
  `administration-1440-light.png` em branco na árvore de quem estiver rodando,
  e o próximo `git status` mostra um baseline "modificado" que ninguém tocou.
  Vale um `try/finally` mais forte ou uma cópia temporária em vez de escrever
  por cima do arquivo commitado.

## 2.1 O que eu abri e rodei, e o que encontrei

| O que foi alegado | Como eu conferi | Veredito |
|---|---|---|
| Sidebar reduzida a Integrations + Settings | Abri a captura de `administration-1440-light` | **CONFIRMADO** — e a subnav Organization/Agent/Data, e a trilha `Settings › Organization › Members & roles` |
| `sidebar.tsx` não precisou mudar | `git status`: intocado; `groupsFor` lê `AREAS` | **CONFIRMADO** — a redução é `visible: () => false` em `routes.ts` mais lógica pré-existente |
| Nove páginas, mas a tela mostra oito | `fixtures/scenarios/populated/principal.json` vs `platform/identity/permissions.py:186-215` | **CONFIRMADO, e a fixture é que está errada** — ela concede `identity.read`, `token.manage` e `audit.read` sem `sso.manage`, e os quatro saem juntos no incremento de ADMIN (`_accumulate`). Conjunto que nenhuma atribuição real produz. **Anterior à 010**; a feature só a tornou visível, e tratou certo (ausente, não desabilitado) |
| 6 testes e2e marcados `skip` | Rodei o arquivo; conferi os cinco testids em `tests/unit/surfaces/` | **CONFIRMADO e legítimo** — endereço perdido, propriedade mantida; o verificador achou ainda `simulation.test.tsx` e `resend.test.tsx`, que nem o skip nem o `controle.md` citavam |
| `/signals?tab=observation` não redireciona | Abri a captura: renderiza Signals › Continuous observation | **CONFIRMADO** |
| Tabela de redirecionamento completa | `SETTINGS_REDIRECTS`, 8 entradas | **CONFIRMADO** — `/configuration` e `?tab=observation` deliberadamente fora |
| `first-day.spec.ts:91` falha (implementer ×2, verificador ×1) | Ver §2.2 | **REFUTADO — é artefato do harness, não do produto** |

## 2.2 A divergência que custou mais caro: `first-day.spec.ts:91`

O implementer relatou falha consistente. Eu **refutei com um `make verify` que
já estava obsoleto** — ele terminou às ~22:40 e o worker mexeu nos arquivos às
22:58. Reportar aquele verde como refutação foi erro meu, e o relato dele
estava certo. O `spec-verifier` reproduziu depois e deu **FAIL** na feature.

O que a árvore diz, depois de eu medir:

- `make verify` canônico: **first-day 5 passed**, três vezes (baseline em master
  limpo, meio da execução, e final).
- `spec_validation browser --project first-day --scenario empty`: **4/5**.
- `spec_validation browser --project first-day` sem cenário: **5/5 falham**.

O snapshot de falha do Playwright decide: a página **é** o wizard, no passo
certo — não houve redirect, que era a causa proposta pelo verificador. O que há
é `offers` vazio, e `IntegrationsStep` só mostra "Nothing in the catalogue
matches that" nesse caso. Nada no diff da 010 alimenta essa lista.

**Conclusão: `--scenario empty` do harness não reproduz o backing que o projeto
`first-day` realmente usa** — serve um catálogo vazio, e o teste não tem como
passar ali. É defeito da ferramenta de validação (`tools/spec_validation.py`,
commit `0955245`), não da feature. Fica registrado como pendência da ferramenta:
enquanto isso, **o resultado do harness para o projeto `first-day` não é
evidência confiável**, e o gate canônico é que vale.

## 2.3 `console/visual/screens.json` não foi reconciliado

`git status`: intocado. Ainda declara telas em rotas que a própria feature passou
a redirecionar. Abri as capturas:

- `first-run-1440-light` fotografa agora o **dashboard** (o cenário tem
  `setup-checklist.json` com `"complete": true`, e a rota redireciona com o
  checklist fechado, que é o cenário 2 da US3);
- `administration-1440-light` fotografa **Members & roles**;
- `signals`, `signals-schedules`, `signals-destinations` caem no estado "não
  construído" que a 060 substitui;
- `knowledge`, `configuration`, `signals-observation`: só a sidebar mudou.

**Aceitar `first-run` como está congelaria um baseline que não vigia mais nada**
— ele deixaria de falhar aconteça o que acontecer com o wizard. Isso é conserto
de registro, não decisão de baseline, e está **pendente**.

### Decisão do operador, 2026-08-14: **os 27 não são aceitos**

Consultado com a evidência acima (cinco capturas abertas e a classificação
entre "só a sidebar mudou" e "a rota agora redireciona"), o operador **recusou
a aceitação dos 27 baselines**. Nenhum `console-visual-accept` foi rodado, por
mim nem por subagent nenhum, em momento algum desta feature.

Consequências, para quem ler isto depois:

- `make verify` **permanece EXIT=2 na etapa visual**, e é o estado esperado da
  árvore — não é regressão a caçar. O pytest reprova junto em
  `test_the_untouched_baselines_still_match`, pela mesma causa e só por ela.
- Os 27 PNGs continuam **como estão no HEAD**. A árvore de trabalho não tem
  nenhum baseline modificado (`git status` limpo em `console/visual/`).
- A 010 fica **PASS condicional e não commitada**. O que destrava o verde é uma
  das duas: reconciliar `screens.json` com os redirects e então aceitar com
  revisão humana, ou aceitar deliberadamente sabendo que `first-run` deixa de
  vigiar o wizard.

### Reconciliação de `screens.json`, feita — sem aceitar nada

Decisão do operador na sequência: reconciliar o registro agora, mantendo os
baselines recusados. Feito, e **nenhum PNG foi tocado** — `git status` mostra
apenas `screens.json` modificado em `console/visual/`.

**Reapontadas** (a rota redireciona, mas o destino é a mesma tela sucessora, com
conteúdo real; o baseline segue divergente só pela sidebar):

| Tela | Antes | Depois |
|---|---|---|
| `administration-1440-light` | `/administration` | `/settings/members-roles` |
| `administration-audit-1440-light` | `/administration?tab=audit` | `/settings/audit-log` |
| `autonomy-1440-light` | `/autonomy` | `/settings/autonomy-guardrails` |

**Passadas a `pending`** (a rota deixou de mostrar o que o id promete, e não há
nada que valha fotografar até uma feature construir a tela). Ficam **registradas**
— apagar a entrada orfanaria o PNG, e
`test_no_baseline_belongs_to_a_screen_nobody_registered` reprova por isso — e
saem do conjunto de captura, porque `screens.spec.ts` filtra por `baselined`.
Cada uma leva um `pending_because` dizendo o porquê:

- `first-run-1440-light` — a rota só serve o wizard com o checklist aberto, e
  este conjunto captura um deployment com ele fechado; fotografá-la seria uma
  segunda cópia do dashboard com o nome do wizard, e **nunca mais falharia**.
- `signals-1440-light`, `signals-schedules-1440-light`,
  `signals-destinations-1440-light` — caem no estado "não construído"; as duas
  últimas capturariam exatamente a mesma tela.

Efeito medido: visual passa de **27 divergentes / 9 verdes** para
**23 divergentes / 9 verdes**, e `tests/contract/console/` continua todo verde
(o contrato de cobertura confere baseline commitado, registro de aceitação e
ausência de órfãos).

**Os 23 não foram corrigidos, e não são para ser.** A reconciliação mexeu no
registro, não nas imagens: nenhum `.png` foi tocado em nenhum momento desta
feature. Os 27 viraram 23 porque quatro entradas saíram do conjunto de captura,
não porque quatro divergências foram resolvidas.

### Decisão final do operador, 2026-08-15: **deixar em aberto**

Consultado de novo, com a diferença entre "registro" e "imagem" explicitada, o
operador optou por **não aceitar os baselines agora e deixar a divergência
aberta**. Decisão deliberada, não pendência esquecida — e o motivo se sustenta:
040, 050 e 060 vão construir as telas de verdade por trás de Members & roles,
Models & providers, Alert intake e companhia, e boa parte destes 23 baselines
muda outra vez quando isso acontecer. Aceitá-los agora seria pagar duas revisões
humanas pelo mesmo pixel.

Consequência permanente enquanto durar, e **não é defeito a investigar**:

- `make verify` **termina EXIT=2 na etapa visual**. Todas as etapas anteriores
  passam.
- `uv run pytest` termina com **1 falha**:
  `tests/contract/console/test_console_visual_regression.py::test_the_untouched_baselines_still_match`.
- Se aparecer uma **segunda** falha,
  `tests/architecture/test_one_fictional_deployment.py`, ela é artefato de
  `console/test-results/` e `console/playwright-report/` deixados por uma rodada
  de Playwright. `rm -rf` nos dois e ela passa. Não é regressão.

Quem for fechar isto depois: revise os diffs, rode `make console-visual-accept`,
e commite os PNGs como mudança revisada por gente. O registro já está
reconciliado, então nenhum dos 23 fotografa a tela errada — o que não era
verdade antes desta sessão.

## 2.4 Uma falha de pytest que era minha, não da feature

`test_exactly_one_fictional_deployment_exists_in_the_repository` reprovava por
causa de artefatos que as **minhas** rodadas visuais escreveram em
`console/test-results/` e `console/playwright-report/`. Apaguei: 9 passed.
Debitá-la do worker teria sido acusação falsa.

## 2.5 Estado dos gates

| Gate | Baseline da onda | Depois da 010 |
|---|---|---|
| `make verify` | EXIT=0 | **EXIT=2 — só a etapa visual** |
| pytest | 14048 passed, 0 failed | **14051 passed**, 1 failed (a divergência visual) |
| vitest | 1967 em 127 | **1987 em 127** (+20: 18 dele, 2 meus) |
| cobertura stmts | 95,36% | **94,44%** (piso 90) |
| `check-imports` | 7 mantidos, 0 quebrados | idem |
| `verify-integrations` | 85 em paridade | idem |
| Playwright behaviour | 85 passed | **82 passed, 6 skipped** (88 coletados) |
| Playwright first-day | 5 | **5** |
| Playwright visual | 36 | **9 passed, 27 divergentes** |

## 2.6 Veredito

**PASS condicional.** Todo requisito da spec está na árvore e provado por teste,
FR-007 incluída (por minha mão, depois que ele a reportou aberta). O único
vermelho do repositório inteiro é a divergência visual, que é decisão humana e
já foi levada ao operador.

**Não commitado**, por regra da onda. Pendências herdadas, com dono:

1. `console/visual/screens.json` reconciliado com os redirects — **antes** de
   aceitar qualquer baseline (§2.3).
2. `--scenario empty` do harness não reproduz o backing do `first-day` (§2.2).
3. `sso.manage` ausente de `fixtures/scenarios/populated/principal.json` (§2.1).
4. `/settings/autonomy-guardrails` mantém `AreaHeader`, sem a trilha completa —
   8 de 9 páginas com breadcrumb.
5. Os 6 e2e em `surfaces.spec.ts` voltam quando a 060 construir as telas de Data.

---

# 3. 020-integrations-catalogo — confronto

Subagent: `spec-implementer` (Sonnet 5, effort max). **Cinco paradas por teto**,
mais um ciclo de reparo: 483k tokens/148 chamadas, depois 647k/274, 813k/396,
116k/538, 394k/140 no reparo. Retomado por `SendMessage` a cada vez, com os
achados exatos e o estado da árvore relido por mim, nunca pela memória dele.
Briefing: `briefings/COMUM.md` + `briefings/020.md`.

Verificador independente (`spec-verifier`, contexto novo): **FAIL**, seis
achados. Depois do reparo, revalidado por mim.

## 3.0 O que o orquestrador fez com as próprias mãos

- **Corrigi o registro visual.** `integrations-panel-1440-light` entrou como
  `status: "baselined"` sem PNG commitado, o que reprova
  `test_a_baselined_screen_has_a_committed_baseline` **e** faz cada rodada
  cheia de gate regravar o PNG que falta. O worker disse ter apagado o
  placeholder; quando fui olhar, estava de volta — **341.620 bytes, 1440x2006**,
  recapturado pelo `make verify` seguinte dele. Captura real, não placeholder em
  branco, e por isso pior: parece legítima, e o próximo `git add` do diretório
  commita baseline que ninguém revisou. Apaguei o PNG e passei a entrada para
  `pending` + `pending_because` — o mecanismo que a 010 estabeleceu.
  Nenhum `.png` commitado foi tocado, por mim nem por ele.
- **Achei o consumidor quebrado que ninguém viu.** `first-run.tsx:242` lia
  `required_credentials` de um payload que deixara de ter a chave;
  `list()` sobre chave ausente devolve `[]`, então o formulário do primeiro dia
  ficava com **zero campos, em silêncio**. Devolvido com exigência de teste que
  visse o vermelho antes.
- **Decidi a questão FR-003/Suggested** que ele levantou em vez de consertar
  sozinho: FR-003 governa "cada item **do catálogo**", e a FR-001 enumera o
  catálogo como coisa distinta das seções Connected e Suggested. O conteúdo de
  Suggested é governado pelo AC2 da US1 — evidência e ação de conectar, que é o
  que ele renderiza. **Código certo, citação errada**; a citação foi corrigida.

## 3.1 Os dois defeitos de cláusula composta

O COMUM avisa que requisito com vírgula é fronteira de requisito, e que o achado
mais caro da onda é o parcialmente atendido marcado como feito. **Aconteceu duas
vezes nesta feature**, e as duas passaram pelo `controle.md` como `FEITO` com a
lacuna admitida só na prosa da célula.

1. **FR-002, "por nome de exibição, categoria e capacidade".** Achado por mim e,
   independentemente, pelo verificador. `rg capabilit` nos dois arquivos da tela
   = zero; o palheiro da busca era `displayName + category + summary`. O gateway
   servia `capabilities`; o cliente nunca lia.
2. **Edge case Failing, "chip crítico e diagnóstico".** Achado pelo verificador,
   não por mim. `healthDetail` era **campo morto**: declarado em
   `integrations.tsx:90`, atribuído em `:131`, e nunca lido em JSX nenhum — duas
   ocorrências no arquivo, ambas de escrita. Uma integração Failing mostrava o
   chip e nada mais.

Ambos consertados no ciclo de reparo, com o vermelho visto e citado. O teste da
capacidade busca `point_in_time_restore`, termo que **só** existe em
`capabilities` — isola a mudança em vez de passar por acidente.

## 3.2 O `controle.md` afirmava um fato que o disco contradizia

Dizia que no dataset real Connected tem 5 itens, "prometheus, proxmox, datadog,
chat, ticketing", citando `integrations.spec.ts:20-50` como prova. O verificador
leu a fixture: **88 total, 86 unconfigured, 1 healthy (`chat`), 1 degraded
(`ticketing`)**. Connected real é **{chat, ticketing}**. Os cinco nomes vinham da
fixture sintética dentro do próprio arquivo de vitest, e o spec e2e citado não
afirma nome de vendor nenhum — só contagens > 0. Mecanismo provado; a frase de
evidência era fabricada. Corrigida.

## 3.3 Três armadilhas de árvore compartilhada, que custaram rodadas

1. **`test_console_gate.py` semeia arquivos de falha na árvore viva** —
   `console/tests/unit/seeded.test.ts`, `console/tests/e2e/seeded.spec.ts`, com
   import de `@/lib/status` que não existe — e os remove num `finally`. Rodar
   esse módulo em paralelo com qualquer gate de build/e2e do console **quebra o
   outro**. Custou uma rodada minha e uma do verificador. Explica também parte do
   que a 010 registrou como "outra sessão escrevendo na árvore".
2. **Quase apaguei evidência.** Quando a fixture semeada reapareceu, conferi
   processos vivos antes de remover e achei o `pytest -q` do verificador ainda
   rodando, órfão do turno dele. Apagar teria reprovado
   `test_a_seeded_end_to_end_failure_fails_the_gate` e eu teria lido como
   regressão real.
3. **`make verify` nunca chega no pytest.** O alvo é `... console-check test`, e
   `console-check` reprova na etapa visual por decisão do operador. Enquanto os
   23 baselines ficarem abertos, **`make verify` não dá sinal nenhum sobre a
   suíte Python** — "todas as outras etapas verdes" vale só para as etapas
   *antes* do `console-check`. Quem quiser o número do pytest roda pytest.

## 3.4 O que o verificador não conferiu, e disse que não conferiu

Registrado porque é onde o risco residual mora: o teste de orçamento de tamanho
do dataset, `vocabulary.spec.ts` por browser, metade do arquivo de teste unitário
que cresceu para ~700 linhas, o diff de `behaviour.test.tsx`, a cifra literal de
1568px, e a comparação visual da feature. Ele listou cada um em vez de preencher
o ledger por completude — que é exatamente o comportamento que se pede.

## 3.5 Estado dos gates

| Gate | Baseline da onda | Depois da 020 |
|---|---|---|
| `make verify` | EXIT=2 (etapa visual) | **EXIT=2 — só a etapa visual** |
| vitest | 1987 em 127 | **2015 em 127** |
| Playwright behaviour | 82 passed, 6 skipped | **95 passed, 6 skipped** |
| Playwright first-day | 5 | **5** |
| Playwright visual | 23 divergentes / 9 | **23 divergentes / 9** |
| `check-imports` | 7 mantidos, 0 quebrados | idem |
| `verify-integrations` | 85 em paridade | idem |
| `tests/contract/console` (sem o módulo visual) | 303 passed | **306 passed, 0 failed** |
| `integrations.spec.ts` + `scroll-budget.spec.ts` | — | **18 passed** |

**SC-001, medido e não alegado**: `/integrations` fica dentro do orçamento de
rolagem contra as **88** entradas reais do catálogo. Antes desta feature o mesmo
teste passava contra três registros e não provava nada — o instrumento é da 001,
o significado é da 020.

## 3.6 O que fica pendente, com dono

1. **Rolagem não restaurada ao fechar o painel** (US3 AC3, T010). Medido:
   1092px antes de abrir, 0px depois de fechar. O teste mede e **não afirma** —
   honesto como estado interino, mas o requisito **não está atendido**.
2. **`min_scope` em branco em 133 de 134 campos obrigatórios** (só `slack.token`
   preenchido); `guide_url` em branco em todos os 182. Consequência direta da
   minha própria instrução de não inventar escopo de vendor: é o custo da regra,
   não falha do worker, e o preenchimento exige conhecimento real por vendor.
3. **`integrations-panel-1440-light` sem baseline**, agora `pending` — sai do
   conjunto de captura em vez de reprovar. Fecha com captura sob revisão humana.
4. **Três adaptadores** do mesmo campo declarado (`catalogue_readers`,
   `routes/config.py`, `routes/integrations.py`). Dois precedem a 020.
5. **O payload mudou de significado**: `required_credentials` (só os exigidos)
   deu lugar a `fields` (todos, cada um com o próprio `required`).

## 3.7 Veredito

**PASS condicional.** Todo requisito da spec tem mecanismo na árvore e prova por
teste que eu rodei, incluindo os dois defeitos de cláusula composta que o
`controle.md` marcava como feitos e não estavam. Nenhum vermelho no repositório
além do que o operador decidiu carregar em aberto.

Números finais, medidos por mim depois do ciclo de reparo:

- `uv run pytest -q`: **2 failed, 14054 passed, 25 skipped**. A única falha real
  é `test_the_untouched_baselines_still_match`, a divergência visual deliberada;
  a segunda é artefato de Playwright e passa **9/9** depois de
  `rm -rf console/test-results console/playwright-report` (confirmado).
- vitest **2015 em 127**; behaviour+scroll-budget **18 passed**;
  `tests/contract/console` **306 passed, 0 failed**; `verify-integrations`
  **85 em paridade**; `make verify` **EXIT=2 só na etapa visual**.

**Não commitado**, por regra da onda. Duas pendências exigem decisão do operador
antes de a onda seguir para a 030, e nenhuma delas é defeito escondido:

1. **Rolagem não restaurada ao fechar o painel** — o AC3 da US3 pede
   explicitamente "volta ao catálogo na mesma posição de rolagem". Medido:
   1092px antes de abrir, 0px depois de fechar. O teste mede e não afirma, de
   propósito. O requisito **não está atendido**; o conserto provável é guardar
   `window.scrollY` antes de abrir e restaurar depois de fechar, nos três pontos
   de entrada.
2. **`min_scope` preenchido em 1 de 134 campos obrigatórios** (`slack.token`),
   `guide_url` em nenhum. A FR-006 pede as três coisas por campo. Isto é
   consequência direta da minha própria instrução de **nunca inventar escopo de
   vendor**: preencher os outros 133 exige conhecimento real e verificável de 85
   vendors, um a um. A regra continua certa; o custo dela é esta pendência.

## 3.8 Ciclo de reparo 2 — as duas pendências, resolvidas por ordem do operador

Consultado com o veredito PASS condicional e as duas pendências nomeadas, o
operador respondeu **"resolva os 2 gaps"**. Feito. O segundo mudou de natureza
durante a investigação, e a mudança é o registro mais útil desta seção.

### O escopo mínimo nunca esteve faltando — eu é que não tinha procurado

Eu havia escrito, em 3.6 e 3.7, que preencher `min_scope` para 133 campos exigia
"conhecimento real e verificável de 85 vendors, um a um", e tratei isso como
custo inevitável da minha própria regra de nunca inventar permissão de vendor.
**Estava errado, e o erro era meu.**

`IntegrationProfile.permissions` (`integrations/_catalogue/entry.py:96`) já
declara, no pacote de cada vendor, tuplas de `RequiredPermission`
(`integrations/_verification/permissions.py:62-84`) com três campos:

- `name` — o nome que o **próprio vendor** dá à permissão;
- `grants` — o que ela concede (validado não-vazio na construção);
- `where` — **onde ela é concedida**, que é literalmente a instrução de obtenção.

Medido: **85 de 85 vendors declaram; 169 permissões; todas as 169 com `grants` e
`where`.** E não são declarações de fé — o `verify_integrations` reporta "every
permission probed": são sondadas contra o vendor de verdade.

O payload de `/v1/integrations` achatava tudo isso para **só os nomes**
(`entry.required_permissions` devolvia `tuple(permission.name for ...)`),
descartando exatamente os dois campos que tornam a informação acionável — o que o
docstring do próprio `RequiredPermission` prevê em tantas palavras: *"an operator
reading 'missing logs:FilterLogEvents' has to look it up"*.

O conserto foi **fiação, não pesquisa**: o payload passou a carregar a permissão
inteira e o painel a renderizar `name — grants · concedida em where`. A FR-006
passa de **1 vendor preenchido à mão para 85 com dado declarado e sondado**.

**A lição é contra mim.** A regra "nunca invente escopo de vendor" estava certa e
continua valendo. O que eu fiz de errado foi aceitar a consequência dela como
pendência inevitável e **escrever isso no dossiê como fato**, em vez de aplicar a
mim mesmo a regra que eu tinha escrito no briefing do worker: *ache o que já
existe antes de construir*. Uma pendência que eu declarei cara custava, na
verdade, uma consulta ao grafo.

### Rolagem

`console/src/surfaces/scroll-memory.ts` (novo) guarda e consome a posição, e
`integration-panel.tsx` restaura na desmontagem — o que cobre botão, Escape e
navegação por um caminho só. O módulo defende a própria escolha contra a regra
"estado de tela mora na URL", e a defesa se sustenta: posição de rolagem é estado
de **sessão**, não de tela — ninguém espera que um link `/integrations`
compartilhado caia no offset de outra pessoa —, então `sessionStorage` é a
prateleira certa e os filtros continuam na URL.

O teste deixou de medir e passou a **afirmar**: `toBeGreaterThan(scrolledTo - 20)`,
com tolerância justificada em comentário. Contra o comportamento antigo (0px),
falha.

### Gates depois do ciclo 2

| Gate | Resultado |
|---|---|
| `uv run pytest -q` | **2 failed, 14055 passed, 25 skipped** — as duas conhecidas |
| `test_one_fictional_deployment` isolado, sem artefatos | **9 passed** |
| vitest | **2016 em 127** |
| `tsc --noEmit` / `eslint src tests` | limpos |
| `integrations.spec.ts` + `scroll-budget.spec.ts` | **19 passed** |

## 3.9 Verificação final independente — **PASS**

`spec-verifier`, contexto novo, sobre os dois ciclos de reparo: **PASS**, com seis
registros, nenhum bloqueante. Reproduziu por conta própria as medições que
importam — 85/85 vendors, 169 permissões, 0 com `grants` vazio, 0 com `where`
vazio; vitest 2016/127; browser 19 passed; `test_console_surfaces` 29 passed;
3364 passed no conjunto de credenciais/integrações — e confirmou que
`integrations-panel-1440-light` **não** aparece entre os 23 divergentes,
enquanto `integrations-1440-light` aparece.

### O achado que sobe para o operador: a letra da FR-006

A FR-006 diz "**cada campo de credencial** DEVE ter label humana, instrução de
obtenção e permissão/escopo mínimo". Label e instrução **são** por campo
(`console/src/surfaces/credential.tsx:166-196`). A permissão **não é**: o painel
lista as permissões da integração (`integration-panel.tsx:184-208`), não do
campo. O verificador mediu o alcance: **61 de 85 vendors têm mais de um campo de
credencial**, e para esses o painel não diz qual permissão cobre qual campo.

Ele julgou a entrega defensável mas não literal, e — corretamente — recusou-se a
assinar sozinho uma decisão de escopo.

**Minha leitura, para o operador decidir:** não existe, em lugar nenhum da
árvore, um mapeamento declarado campo→permissão. `RequiredPermission.capabilities`
liga permissão a **capacidade**, nunca a campo. Construir a associação exigiria
**inventá-la** — exatamente o que a regra "nunca invente escopo de vendor"
proíbe, e a mesma regra que produziu 169 permissões reais em vez de 133
adivinhadas. Portanto a renderização por integração não é só defensável: é a
**única forma honesta** com o dado que existe. Fechar a letra exigiria a
declaração nova, por vendor, do que cada campo cobre — trabalho de vendor, não de
tela, e candidato a spec própria.

### Registros menores

- **Rolagem**: os três caminhos de fechamento (botão, Escape, navegação)
  convergem num `onClose` só e a restauração roda no cleanup do unmount — um
  caminho de código para os três, verificado por leitura. O teste e2e exercita
  **só o botão**. Lacuna de cobertura nomeada, não defeito.
- **`CatalogueEntry.required_permissions`**: a suposição de que a geração de docs
  a consumia estava errada — `tools/generate_integration_docs.py:81,85` lê
  `entry.profile.permissions` direto e nunca passou pela forma achatada. Nota de
  precisão, sem conserto.
- **`first-run.tsx` era mesmo consumidor do payload antigo**, contra o que o
  `controle.md` original afirmava ("nenhum encontrado"). Achado pelo orquestrador
  e consertado corretamente; registrado que a busca do worker não achou o que
  devia.

### O verificador caiu na armadilha #1 — e consertou certo

Rodou `test_console_visual_regression.py` em paralelo com o próprio `pytest -q`
de fundo e deixou `administration-1440-light.png` com 9.298 bytes no lugar dos
151.336 commitados — exatamente o mecanismo de PNG em branco que este dossiê já
documentava, agora provado a partir de um segundo módulo, não só do
`test_console_gate.py`. Conferiu `pgrep` limpo, restaurou com `git checkout` do
arquivo, confirmou com `cmp`, limpou os artefatos e **reportou**.

Conferido por mim depois: `git diff --stat console/visual/baselines/` **vazio**,
o PNG de volta aos 151.336 bytes, e só `screens.json` modificado em
`console/visual/`. A restauração é real.

**A regra da onda fica mais forte:** não é "não rode `test_console_gate.py` em
paralelo". É **nenhum módulo que escreve na árvore viva roda em paralelo com
qualquer outra coisa** — e nesta feature isso já mordeu três agentes diferentes,
incluindo o orquestrador.

## 3.10 As duas decisões do operador, e o commit

Consultado com o veredito PASS e a única pendência de escopo nomeada, o operador
decidiu as duas coisas que faltavam para a onda seguir.

### A letra da FR-006 — **assinada**

O operador assinou a leitura do orquestrador registrada em 3.9: renderizar a
permissão **por integração** é a única forma honesta com o dado que existe.

O que isso quer dizer, para quem ler depois e achar que encontrou um defeito:

- **label e instrução de obtenção são por campo** e estão entregues
  (`console/src/surfaces/credential.tsx:166-196`);
- **a permissão é por integração** (`integration-panel.tsx:184-208`), e 61 dos
  85 vendors têm mais de um campo de credencial;
- não existe, em lugar nenhum da árvore, mapeamento declarado campo→permissão.
  `RequiredPermission.capabilities` liga permissão a **capacidade**, nunca a
  campo. Construir a associação seria **inventá-la**.

O requisito está atendido em substância. Fechar a **letra** exigiria uma
declaração nova, por vendor, do que cada campo cobre — trabalho de vendor, não
de tela, e candidato a spec própria **fora desta onda**. Não é defeito para
reabrir aqui.

### O commit — **direto em master**

Commitado como **`058aa91`**: 44 arquivos, 8.175 inserções, 322 remoções. Hooks
de pre-commit passaram (ruff lint, ruff format, contratos de import, constantes).

Conferido por mim antes de commitar, porque nesta onda essas três coisas já
custaram rodadas:

- **nenhum PNG commitado tocado** — `console/visual/` carregava só
  `screens.json`;
- **nenhuma fixture `seeded.*` sobrando** de uma rodada morta de
  `test_console_gate.py`;
- **nenhum pytest vivo** (`pgrep`) que pudesse estar no meio de um `finally`.

Os 44 caminhos foram estagiados **explicitamente**, um a um. Nunca `git add -A`
nesta árvore: o diretório de trabalho carrega material de planejamento que não
pode ser commitado.

### O que isso libera

A 030 começa com a árvore **limpa** em `058aa91`, que é a primeira vez desde o
início da onda que uma feature parte de um estado sem trabalho não commitado de
outra por baixo. O diff da 030 é o diff da 030, e o verificador dela não vai
precisar separar dois conjuntos de mudanças à mão — que foi exatamente o custo
pago na 020.

## 4.0 O que o orquestrador levantou antes de delegar a 030

A `spec.md` da 030 foi escrita em 2026-08-14 contra a tela de first run
**anterior à 001**. A 001 já reconstruiu aquela tela como wizard. Entregar a
spec ao pé da letra construiria pela segunda vez metade do que já está no disco
— e um segundo modelo de passos é precisamente a fonte dupla que esta feature
existe para matar.

Levantei o delta antes de chamar o worker, e ele foi ao briefing com
`file:line`. O registro completo está em `specs_v5/briefings/030.md`.

### O que a 001 já entregou e a spec não sabe

`console/src/surfaces/first-run/plan.ts` **já é** o modelo de passos que a T003
manda criar: `WIZARD_STEPS` (`:24`), `stepDone` (`:152`), `outstanding` (`:199`),
`currentStep` (`:211`), `hrefFor` (`:221`), `planFor` (`:234`), `readSetup`
(`:255`). O stepper com link por passo está em `screens/first-run.tsx:371-423`;
a verificação com teste e retry por item, com `remedy` e `findings` do backend,
em `first-run/verify.tsx:139-199`; e `setup-hero.tsx` é o convite do dashboard,
que já consome a fonte única e já **some sozinho** quando não sobra nada
(`setup-hero.tsx:43`).

A navegação para trás da FR-001 também já existe, e não como modo: o passo atual
vem do endereço (`?step=`), então reabrir passo concluído é navegação, sobrevive
a reload e pode ser mandada para um colega.

### A contagem dupla, viva, no mesmo painel

**O defeito central da feature, e ele está no disco agora.** Um painel, duas
contagens, duas fontes, dois denominadores:

| Onde | O quê | Fonte |
|---|---|---|
| título, `first-run.tsx:322-325` | `checklistTitle(plan.filter(done).length, WIZARD_STEPS.length)` | tally **7-based, client-only** |
| corpo, `first-run.tsx:365-370` | `outstanding(setup)` sobre `setup.steps.length` | **fonte única**, servida pelo backend |

`setup.steps` **não tem sete elementos** — são os passos do checklist do
backend, outro vocabulário e outra cardinalidade. As duas linhas discordam por
construção. É literalmente o *"'2 of 7' e '3 outstanding' simultâneos"* que a
SC-002 nomeia como o estado a matar, e **ele sobreviveu à 001**.

O teste de contrato que deveria pegar isso existe e passa:
`tests/contract/console/test_console_first_run.py:181`. Ele inspeciona, por
regex, **só o corpo da função `outstanding`** — e o título escapa por estar em
outro arquivo. O próprio docstring do teste descreve a propriedade que o título
viola. É um bom exemplo de teste que prova o que mede e não o que promete.

### O que a 010 deixou explicitamente para a 030

`console/src/shell/routes.ts:686`, em tantas palavras:

> `/first-run` is not here: its redirect depends on whether the checklist is
> complete, a fact this table cannot hold, so its own route file reads it
> directly.

Ou seja: o redirect da FR-007 **não** entra em `SETTINGS_REDIRECTS`; mora em
`console/src/app/(shell)/first-run/page.tsx`. A 010 previu a fronteira e a
documentou no lugar onde o próximo worker olharia.

### Um link que hoje sobrevive por redirect

A 010 aposentou `/signals` (`routes.ts:701` manda para `/settings/alert-intake`),
mas `HANDOVER.alerts` (`first-run.tsx:79`) continua apontando para `/signals`.
O handover do último passo atravessa um redirect hoje. Funciona, e é o tipo de
coisa que a próxima limpeza quebra sem ninguém notar.

## 4.1 Veredito da 030 — **PASS**, e os dois defeitos que o verificador achou

`spec-verifier`, contexto novo, percorreu cada oração de cada requisito
(dividindo por vírgula, pela regra da própria onda) e devolveu **PASS**. As duas
orações que esta onda mais perde — a segunda da US2 AC4 ("com a pendência
anotada no dashboard") e a segunda da FR-003 ("a tela de destino oferece o
retorno **enquanto o setup estiver incompleto**") — estão as duas no código, com
teste que as exercita. Foi a primeira feature da onda em que o padrão de cláusula
composta **não** reincidiu.

Ele rastreou a segunda oração da US2 AC4 até o backend de verdade, não até a
fixture: `_provider_step` (`platform/startup/checklist.py:302-350`) só marca o
passo como `done` quando `verdict.satisfied`, então provider guardado e não
verificado continua pendente e o `SetupHero` o nomeia sozinho. É "já valia" com
prova, que é a única forma de "já valia" que vale.

### Achado 1 — dois identificadores de requisito em arquivo commitável

`first-run.tsx:769` e `first-run.test.tsx:1119` carregavam `FR-007` e `FR-006`
em comentário. A regra estava no `COMUM.md` e repetida no briefing da feature, e
foi violada mesmo assim.

**Rodei a minha própria varredura antes de aceitar a dele, e ela achou
exatamente os mesmos dois** — o que é a primeira vez na onda que a varredura do
orquestrador e a do verificador convergem no mesmo conjunto. Na 010 foram nove
em três varreduras. Reescritos para dizer a substância.

### Achado 2 — o guarda da contagem dupla não guardava

Este é o achado que valeu o verificador. O teste de contrato novo
(`test_the_checklist_heading_is_not_a_second_tally_beside_outstanding`) fatia o
texto-fonte de `checklistTitle(` até o próximo `;` e confere que `WIZARD_STEPS`
não aparece e `outstanding(` aparece. O código de hoje passa honestamente — mas

```ts
const total = WIZARD_STEPS.length;
checklistTitle(x, total);
```

passa igual, e reintroduz o bug inteiro.

**É o mesmo defeito do teste que ele foi escrito para complementar.** O
`test_the_progress_count_is_not_recomputed_...` (linha 181) mede o corpo de uma
função e deixou o título escapar — foi assim que a contagem dupla sobreviveu à
001. O conserto herdou a fraqueza do que consertava.

Fechado por mim com uma asserção do **cabeçalho renderizado**, em vitest, onde a
indireção não ajuda: um deployment que reporta todos os próprios passos
concluídos enquanto o tally dos sete discordaria. **Vi o vermelho de verdade** —
reverti a correção, rodei, vi falhar em `getByRole('heading', { name: 'Every
step is done' })`, e restaurei. Não inferi.

### Achado 3 — o `controle.md` afirmava algo que a tela não faz

A célula da SC-003 dizia que a tela de destino da correção "já é o passo com o
botão de re-teste pronto". Não é: aquele botão só renderiza quando
`here === 'verify'`. A propriedade se sustenta na leitura correta — voltando ao
`verify`, o re-teste é um clique — mas a frase induzia ao erro. Corrigida no
ledger, com o registro de que veio do verificador.

### As duas impossibilidades declaradas, conferidas contra o código

O implementador declarou duas pendências alegando limitação do plano de mock. As
duas se confirmam contra a fonte, não contra a palavra dele:

- `fixtures/scenarios/first-run/provider-verify.json` tem **um** registro com
  `"arguments": {}`, então todo `provider_id` cai na mesma resposta canônica —
  a falha específica "modelo sem tool calling" não é obtenível pelo navegador;
- `MockPlane._apply_write` (`tools/mockplane/server.py:428-478`) não tem `case`
  para `credential-write` nem `setup-checklist`, então um `PUT` ao vivo não move
  a leitura seguinte do checklist.

Pendências honestas, com dono nomeado.

## 4.2 Os sete europeísmos que a 001 não pegou

Varrendo `pt-BR.ts` por causa da 030, achei texto europeu que a varredura de
vocabulário da 001 deixou passar. **A minha primeira varredura achou cinco; a
segunda, mais ampla, achou sete** — a mesma escalada que a 010 viu, e a razão
pela qual "varri" nunca é uma afirmação de uma passada só.

| Era | Virou |
|---|---|
| `Esse utilizador e essa palavra-passe não foram aceites.` | `Esse usuário e essa senha não foram aceitos.` |
| `Não foi possível contactar a instalação.` | `Não foi possível contatar a instalação.` |
| `Seguinte` (paginação) | `Próximo` |
| `Salvaguarda — acção retida` | `Salvaguarda — ação retida` |
| `Interacção humana` | `Interação humana` |
| `Acção proposta — à espera da sua decisão` | `Ação proposta — aguardando a sua decisão` |
| `O texto como seria gravado` | `O texto como seria salvo` |

Conferi antes de mexer que nenhum teste nem nenhuma fonte dependia desses
textos. Nenhum deles é da 030; entraram no commit dela por decisão minha, porque
são uma linha cada e o arquivo já estava aberto.

## 4.3 Gates da 030, medidos por mim

| Gate | Resultado |
|---|---|
| vitest | **2043 em 128** (baseline da onda 2016/127) |
| `tsc --noEmit` | EXIT=0 |
| `uv run pytest -q`, isolado | **1 failed, 14057 passed, 25 skipped**, 610s |
| `tests/contract/console` | **308 passed** (baseline 306) |
| playwright `behaviour` | 98 passed, 6 skipped |
| `setup-wizard.spec.ts` | 2 passed |
| `first-day`, cenário `first-run` | 7 passed (5 antigos + 2 novos) |
| prettier | limpo |

A única falha em toda a árvore continua sendo
`test_the_untouched_baselines_still_match`, a divergência visual que o operador
decidiu carregar. Nenhum PNG foi tocado; `console/visual/` ficou limpo do começo
ao fim, conferido antes e depois de cada rodada de pytest.

**Commit `fbd0130`** em `master`: 16 arquivos, 1.039 inserções, 55 remoções.

---

# 5. 040-agente — confronto

## 5.0 O que o orquestrador levantou antes de delegar

A `spec.md` da 040 foi escrita em 2026-08-14, e — pela terceira vez seguida
nesta onda — descrevia telas que features anteriores já tinham trocado. O
`plan.md` mandava criar
`console/src/app/(shell)/settings/{models,autonomy,notifications}/`. Esses
diretórios não existem: a 010 criou `models-providers`,
`autonomy-guardrails` e `notifications`, e `/settings/autonomy-guardrails` já
renderizava a tela de autonomia inteira. Entregar a spec ao pé da letra teria
reconstruído o que já estava no disco.

O levantamento foi ao briefing (`specs_v5/briefings/040.md`) com `file:line`.
Três achados carregaram a feature:

**A tela antiga já entregava boa parte da FR-003.** Tabela de regras em ordem
de resolução, glossário, bounds, editor de nível com preview/explain/dry-run,
override com concessão e revogação, e um empty state que já semeava a primeira
regra. As US2 AC1 e AC5 **já valiam** — e o verificador confirmou depois que
foram preservadas, não recreditadas como trabalho novo.

**O defeito central era literal e tinha quatro ocorrências.**
`configurationHref` (`screens/autonomy.tsx:255-258`) resolvia para
`/configuration` e era o CTA de empty state de quatro painéis. Era o laço
Autonomy → Configuration que a SC-004 existe para matar. Avisei no briefing que
apagar o CTA sem construir o formulário satisfaria a letra e seria regressão.

**A FR-002 não era construível só no console, e o plano não sabia.** O plano
afirmava que o badge de tool calling vinha "do catálogo de providers,
capacidade já conhecida pelo gateway". Meia verdade:
`ModelDescriptor.supports_tools` existe (`core/llm/registry.py:65`), mas a rota
que o console lê servia `models=list(onboarding.models)` — nomes, sem
capacidade. O conserto tinha de ser na raiz, em `gateway/http/routes/`.

## 5.1 Quatro tetos de turno e uma morte por limite de sessão

O implementador parou quatro vezes por teto de turno e uma quinta por limite de
conta. Cada retomada carregou os achados exatos de volta. O padrão que se
repetiu nas cinco: **o gate do console (prettier/eslint/tsc) foi sempre a coisa
que ele anunciou e nunca alcançou.** Duas vezes eu mesmo rodei o `prettier` que
ele ia rodar; uma vez ele parou literalmente no meio da frase "agora o
equivalente em pt-BR", deixando 28 chaves em `en.ts` sem par — eu escrevi as 28,
no vocabulário que o arquivo já tinha adotado (`âmbito`, `exceção`,
`janela de congelamento`, `rótulo`).

A lição generaliza e vale para 050/060/070: **peça o gate antes do relatório,
não dentro dele.**

## 5.2 O erro de diagnóstico do orquestrador

Quando a notificação de limite de sessão chegou, concluí que o agente tinha
morrido. Amostrei mtime de **dois** arquivos por **quatro segundos** e chamei
aquilo de evidência. Um agente lendo, pensando ou rodando suíte não toca mtime
nenhum — eu tinha essa hipótese e a descartei rápido demais. O operador viu o
agente trabalhando e me corrigiu; o transcript confirmou turnos dez minutos
depois da notificação.

Consequência real: **editei `models-editor.test.tsx` com o worker vivo.** O
conserto estava certo pela razão certa — `models-editor.tsx:96-105` documenta
que `integrationsHref` não pode ser prop porque função não atravessa a fronteira
server/client — mas editar a árvore de quem está trabalhando nela é colisão, não
ajuda. Avisei o worker por mensagem com o quê e o porquê, para não haver
reversão silenciosa, e fiquei fora de `console/` até ele fechar.

A evidência certa para "o agente está vivo?" é o mtime do transcript dele, não o
da árvore.

## 5.3 Três defeitos que só o build real revelou

O implementador perseguiu a causa raiz entre tiers, e o mais instrutivo é o
primeiro:

1. **Função como prop de servidor para cliente** (`integrationsHref`). Passava
   em `tsc`, em `eslint` e nos **2091 testes vitest**, e quebrava só no build de
   produção. Foi o `console_e2e` contra o build standalone que pegou. O
   comentário no código já prescrevia a solução; o teste unitário não tem
   fronteira para impor, então nada ficou vermelho.
2. **`Promise.all` sobre nove leituras de provider** — uma falha derrubava o
   painel inteiro. Virou `Promise.allSettled`.
3. **`/api/config` e `/api/preview` descartavam `remove`**, quebrando em
   silêncio "devolver à herança". Vermelho visto antes do conserto, e o teste
   novo afirma o corpo que vai no fio, não só o setup.

## 5.4 Veredito — **PASS**

`spec-verifier`, contexto novo, com instrução explícita de inspecionar os
arquivos **não versionados** (um diff `master...HEAD` aqui não mostra nada) e de
testar justamente as afirmações confiantes do relatório. Quatro constatações,
nenhuma falsificando afirmação funcional.

O que ele confirmou de mais valioso, porque é onde uma migração costuma perder
cobertura sem ninguém ver: **a suíte migrada é superconjunto, não redução** —
os 15 `it()` originais preservados quase verbatim, mais 6 novos (335 → 518
linhas). E o tri-estado da FR-002 chega ao **texto renderizado**:
`models.test.tsx:231-255` renderiza `supports_tools: null` e afirma que o badge
nunca diz "não suporta".

A constatação mais severa dele era sobre **o meu próprio trabalho**: os ADRs
0012/0013/0014 e as duas edições de índice estavam na mesma árvore, sem linha
que os possuísse em 040. Ele rastreou por mtime que apareceram intercalados com
as edições da feature. Está certo, e a correção é de commit, não de código: são
trabalho do orquestrador a pedido do operador e pertencem a um commit próprio.

## 5.5 Gates, medidos por mim

| Gate | Resultado |
|---|---|
| `tsc --noEmit` | EXIT=0 |
| `eslint .` | EXIT=0 — os dez erros que estavam vermelhos, resolvidos |
| `prettier --check .` | limpo |
| `vitest run` | **2091 passed / 132 files** (base 2043/128) |
| paridade i18n | **1282 = 1282**, sem órfão dos dois lados, sem europeísmo |
| `lint-imports` | 7 contratos mantidos, 0 quebrados |
| `check_constants` | EXIT=0 |
| `pytest tests/contract/ tests/architecture/` | **5374 passed, 1 failed, 18 skipped**, 478s |
| `playwright behaviour`, `settings-agent.spec.ts` | **9 passed**, backing `mock`, build de produção real |
| comparação visual | 23 divergentes / 9 passando — **o mesmo split da 030** |
| `make verify` composto | **não rodado**; cada estágio rodado em separado. Devido no fim da onda |

A única falha do pytest é `test_the_untouched_baselines_still_match`, a
divergência deliberada. **A 040 não introduziu nenhuma regressão visual nova**:
`models-providers` e `notifications` não são telas registradas, e
`autonomy-1440-light` já divergia — como o briefing previu.

Uma segunda falha apareceu na rodada completa,
`test_exactly_one_fictional_deployment_exists_in_the_repository`, e era **minha**:
rodei o pytest em paralelo com a validação de browser do verificador, que estava
escrevendo `console/test-results`. Sozinho, depois de limpo: 9 passed.
**Terceira vez nesta onda** que rodar uma suíte que escreve na árvore viva em
paralelo produz falha fantasma. A regra merece ser escrita onde alguém a leia.

## 5.6 O que fica pendente, com dono

T004 (contrato de payload), T011 (edição concorrente), T015b (regra com recurso
inexistente), seletor de escopo por nó, três escalares de `policies.autonomy` e
dois campos lista-de-string inalcançáveis pelo `ConfigEditor` reaproveitado —
esses dois últimos são limitação herdada, não introduzida, e alimentam a 070.

E um conflito genuíno, exposto em vez de resolvido no escuro: a spec pede
"salvar sem verificar"; o mockup e o `tasks.md` dizem "Testar sem salvar". O
implementador seguiu o mockup como DoD e nomeou a discordância. O verificador
confirmou que existem exatamente dois controles e que nenhum terceiro foi
inventado. Fechar essa oração é decisão do operador.

**Não commitado.** A árvore carrega a feature; `HEAD` continua em `fbd0130`.

## 6.0 O que o orquestrador levantou antes de delegar a 050

A nota deixada pela 040 mandava verificar os dois defeitos do Audit antes de
construir qualquer conserto, porque as specs desta onda são rotineiramente
obsoletas contra telas que features posteriores já substituíram. Verifiquei.
Os dois existem — e um não está onde a spec diz.

### O defeito do período mudou de forma

Todo controle de navegação do `audit.tsx` tinha o caminho `/administration`
escrito na mão: a `FilterBar`, os presets de período, a aba "Any", o href de
cada linha, a `RowList` e a ação do empty state. Em `/settings/audit-log` a URL
não carrega `tab`, então o `hrefFor` emitia `/administration?since=…` sem tab, e
o `settingsRedirectTarget` casava com a entrada sem tab e mandava para
`/settings/members-roles`.

O "botão que não faz nada" da spec tinha virado **todo controle de filtro
abandonando a página**. Reproduzir a frase da spec teria consertado a coisa
errada.

### O defeito da contagem não era "duas consultas"

O plano pedia "contagem e lista da mesma consulta". Já eram o mesmo repositório
e a mesma janela. O que divergia era o **conjunto de filtros**: `query()`
recebia `actor_id`, `action`, `resource_kind` e `resource_id`; `count()` recebia
só `since` e `until`. A assinatura estreita era do próprio port, seguida pelas
duas implementações. Filtrar por ator e o aviso "showing N of TOTAL" reportava
um total sem relação com a lista.

E havia um **segundo contribuinte, no cliente**, para o sintoma exato que a spec
cita: a exclusão do principal do sistema acontecia no cliente, e o empty state
era calculado sobre o que sobrava dela, enquanto o toggle renderizava
`default — 200 events`. Consertar só o gateway teria deixado a contradição na
tela.

### Três alegações da spec que já não valiam

- **A guarda de último administrador não estava ausente.** `remove_grant` já
  chamava `require_owner_retained` e levantava `conflict` em
  `LastOwnerRemoval`. A task pedia para construí-la "se ausente"; o trabalho
  real era superficiar a recusa, que caía num `failed` genérico.
- **A causa do acúmulo de tokens não era o formulário de emissão.** O
  `bring_up` já reusava a credencial viva. A credencial de bootstrap vive uma
  hora, então um deployment reiniciado mais tarde emite outra — e a anterior
  **nunca era revogada, só expirava**. Lugar certo, gatilho errado.
- **O contrato de SSO no servidor já estava completo**: ativação recusada até
  passar teste contra os settings como estão, vínculo por digest dos próprios
  settings, `verified` derivado em vez de armazenado, e `problems` em linguagem
  de operador. A feature era reestruturação no console, não invariante nova.

## 6.1 Seis paradas, duas mortes por limite de conta

O implementador parou seis vezes: duas por limite de sessão da conta e quatro
por teto de turnos, sempre no meio de uma frase. A primeira morte não deixou
**nada** no disco — `git status --porcelain` retornava 0 linhas — e retomar sem
dizer isso teria feito o worker re-derivar um estado que não existia.

Cada resume carregou o estado medido por mim, não o que o worker lembrava.

**Uma quase-perda de baseline.** Numa das paradas ele havia anunciado que ia
rodar ruff e mypy em paralelo com um pytest em background, justificando que
ruff e mypy não escrevem na árvore. A justificativa erra o alvo: quem escreve é
o pytest, e `test_console_visual_regression.py` sobrescreve
`administration-1440-light.png` com um PNG em branco e restaura num `finally` —
e ele morreu no meio. O baseline sobreviveu (151336 bytes, `console/visual/`
limpo no git). Foi sorte, e foi dito nessas palavras.

## 6.2 O gate do console, exigido antes do relatório, funcionou

A lição que a 040 pagou foi aplicada: exigir `tsc`, `eslint`, `prettier` e
`vitest` **antes** do relatório, não dentro dele. Pela primeira vez na onda os
quatro números chegaram junto com a entrega e bateram exatamente com a minha
medição independente.

A mesma exigência produziu o achado que mais valeu: os testes behaviour não
existiam. Quatro tasks pediam Playwright explicitamente e o `plan.md` nomeava
`settings-org.spec.ts`; ele havia escrito vitest no lugar. Cobrado três vezes,
o arquivo foi criado — e na primeira execução revelou um defeito que `tsc`,
`eslint` e 2155 testes de unidade deixaram passar: `sso.tsx`, um componente de
servidor, chamava `SSO_FIELDS.map()` importando de um módulo `'use client'`.
Quebrava só contra o build de produção real. Mesma classe de defeito que a 5.3
já registrou.

## 6.3 Veredito — **FAIL**, reparado, depois **PASS**

O verificador reprovou no primeiro passe por um achado alto: concessão de papel
administrativo não pedia confirmação, embora a spec peça em US1 AC2 e em
FR-007. O implementador havia declarado a pendência honestamente, mas
justificado com "risco ao componente compartilhado".

**A justificativa não se sustentava, e foi derrubada com evidência.** O
`GrantPanel` tinha exatamente um consumidor em produção — o `members.tsx` que
ele mesmo escrevera na mesma sessão. O "compartilhado" era o `PeopleTab`, que
aquele diff removera. E o `ConfirmDestructive` já estava importado e em uso no
próprio arquivo, para a remoção de grant. A razão real era falta de tempo, e ele
reconheceu isso no ciclo de reparo.

O verificador também achou o que eu não teria pego: a §5 do `controle.md`
prestava contas de dois dos três arquivos de teste apagados e **nunca auditava o
`sso.test.tsx`**, o maior deles. A aritmética estava errada em dois dos três
(o `audit.test.tsx` tinha 12 testes, não 16; o `sso.test.tsx` tinha 17, não 10).
Eu havia nomeado 2 asserções perdidas; o rastreamento completo achou **7**.

Ciclo de reparo 1 fechou os quatro achados. Segundo passe do verificador:
**PASS**, sem regressão em nada aprovado antes.

## 6.4 Gates da 050, medidos por mim

| Gate | Resultado |
|---|---|
| `npx tsc --noEmit` | EXIT=0 |
| `npx eslint .` | EXIT=0 |
| `npx prettier --check .` | EXIT=0 |
| `npx vitest run` | **2176 passed, 137 files** (baseline da onda 2091/132) |
| `spec_validation browser --test tests/e2e/settings-org.spec.ts` | **6 passed**, build de produção real |
| Identificadores de requisito em linhas adicionadas | limpo — primeira feature da onda sem vazamento |
| Paridade i18n | en 1315 = pt-BR 1315, sem formas europeias novas |
| `console/src/design/tokens.ts` | intocado |
| `administration-1440-light.png` | 151336 bytes, íntegro; `console/visual/` limpo |

O verificador reproduziu todos por conta própria, mais `pytest` em
`tests/contract/persistence/test_audit_repository.py` (8), nas três suítes de
rota do gateway (20) e em `tests/unit/platform/{identity,startup}/` (418).

**A comparação visual não foi rodada, deliberadamente.** As duas telas
registradas desta feature estão entre os 32 baselines que divergem pela troca
de paleta em `e5a8c24`. Comparar reportaria um diff dominado por esse confundidor
já explicado. `make console-visual-accept` nunca foi rodado, por ninguém.

## 6.5 O que fica pendente, com dono

- **`/autonomy` estoura o orçamento de rolagem em 48px** — preexistente,
  confirmado por diff como intocado pela 050. Dono: quem mantém a tela da 040.
- **SC-002 (usabilidade do SSO sem documentação externa)** — estrutura
  construída e testada; a afirmação exige uma pessoa real, não um agente.
  Corretamente não reivindicado.
- **Teste de wording pt-BR da linha de conta de serviço** — a string está
  correta e coberta pela paridade do catálogo; o teste específico do arquivo
  apagado não foi recriado.
- **Insumo de paridade para a 070** (`policies.sso`, `policies.sso.claims`) —
  registrado em prosa no `controle.md`; não existe arquivo de checklist na
  árvore para atualizar.
- **Dois europeísmos preexistentes no `pt-BR.ts`** — `'signIn.username':
  'Utilizador'` e `'transcript.kind.objective': 'Objectivo'`, ambos já no
  `HEAD`, em namespaces que a 050 não toca. Reportados em vez de silenciados.

**Um bug preexistente corrigido de quebra:** o `TokenService` era construído sem
`AuditRecorder` no `asgi.py`, então **toda emissão e revogação de token era
silenciosamente não auditada**, independentemente do que qualquer chamador
pedisse. Achado ao perseguir a causa do acúmulo.

**Não commitado.** A árvore carrega a feature em 55 caminhos; `HEAD` continua em
`9ca2eab`.

**Commitado** como `af0bc2b` na `master` — 53 arquivos, 4745 inserções, 1390 remoções,
por instrução do operador. Hooks de pre-commit passaram. Antes de commitar,
`git branch --no-merged master` voltou vazio: nenhum branch carregava commit
ausente da `master`.

---

# 7. 060-dados — confronto

## 7.0 Veredito — **PASS**, e commitado

Verificada por `spec-verifier` em contexto limpo, **sem ciclo de reparo**. Três
achados, **nenhum no produto**: dois eram erro de citação ou de crédito no
`controle.md` — ambos meus, ambos corrigidos — e um era uma asserção perdida na
migração de suíte.

**Commitada** como `d91b51a` na `master` — 28 arquivos, 2341 inserções, 1200
remoções.

O detalhe completo dos três achados, do que o verificador confirmou de forma
independente, dos gates medidos e da lacuna que o orquestrador encontrou depois
da entrega (a frequência legível da **lista** de agendas, primeiro substantivo
de uma enumeração cujos outros três foram entregues) está no
`specs_v5/progress.json`, sob a chave `completed_060`, e no
`specs_v5/060-dados/controle.md`. Não é repetido aqui.

## 7.1 O que a onda ganhou depois da 060, e que este dossiê não registrava

Onze commits entre `af0bc2b` e `0ae8369` nunca entraram neste arquivo. Os que
mudam o estado da onda:

- **`f3327d0` — os 32 baselines visuais foram aceitos**, sob revisão humana,
  junto com o registro das telas que ninguém observava. A divergência que este
  dossiê carregou desde a 010 **está fechada**.
- **`d642ed7` — as ADRs 0012 e 0014 foram aceitas.** A 0014 é o que permite ao
  design de Settings entrar no repositório como referência permanente, em vez de
  viver num diretório de onda gitignored e evaporar com ela.
- **`33d839f` e `b7e7511`** mediram e depois consertaram os 48px de estouro de
  rolagem de `/autonomy`, item aberto que a 040 e a 060 carregavam.
- **`44583cb` e `943a5b9`** trouxeram `console/src/shell/config-ownership.ts` e
  seu teste de contrato — fundação da 070, e o assunto de todo o §8.
- **`0ae8369`** consertou a armadilha do baseline apagado por corrida
  interrompida, registrada neste dossiê desde a 010.

---

# 8. 070-migracao-editor-cru — confronto

## 8.0 O baseline está verde pela primeira vez na onda

Medido pelo orquestrador em 2026-08-16, em árvore limpa no `0ae8369`,
imediatamente antes de delegar:

| Gate | Resultado |
|---|---|
| `make verify` (composto) | **EXIT=0** |
| `pytest` | **14186 passaram, 0 falharam**, 25 pulados, 774s |
| `vitest` | **2205 passaram em 138 arquivos** |
| `playwright` | behaviour **130**, first-day **10**, visual **31** — todos verdes |

**As duas dívidas permanentes desta onda acabaram.** O `make verify` composto,
adiado desde a 040, roda limpo; e o gate visual, vermelho desde a troca de
paleta, passa. Daqui em diante, vermelho é da 070 até prova em contrário.

## 8.1 Sete afirmações que já não descrevem o repositório

Quinta feature seguida com spec estalada — depois da 030, 040, 050 e 060. O
confronto antes de delegar já se pagou cinco vezes.

### O mapa já existe, e **subdeclara a própria cobertura**

A T001 manda "declarar o mapa de paridade". Ele já está na árvore desde
`44583cb`. O que ele precisa é de **correção**, e a correção é o achado central
desta feature.

O mapa diz 15 campos com dona e 101 sem — total 116, que confere com
`declared_fields()`. Mas **24 dos 101 são editáveis hoje, numa tela Settings**:

- **16** — `models.<papel>.{provider,model}` para os oito papéis. O caminho é
  montado exatamente assim em `console/src/surfaces/settings/models-editor.tsx:93`.
  Dona: `settings-models-providers`.
- **8** — `policies.sso.{provider,issuer,client_id,authorisation_endpoint,
  token_endpoint,jwks_uri,redirect_uri,default_node_id}`, declarados em
  `console/src/surfaces/sso-fields.ts` e percorridos em
  `console/src/surfaces/settings/sso.tsx:48`. Dona: `settings-single-sign-on`.

A regra do próprio arquivo obriga a contá-los como donos: *"Ownership is about
where a **person** edits a value, not which HTTP route carries the write."* As
duas telas escrevem por endpoint próprio, e o arquivo já decidiu que isso é
detalhe de implementação da página.

### A aritmética real

| | |
|---|---|
| campos no schema | 116 |
| editáveis pelo editor cru (string/integer/number/boolean) | 86 |
| array/objeto — nunca editáveis, em lugar nenhum | 30 |
| com dona hoje (3 deles array) | 15 |
| **editáveis e sem dona** | **74** |
| dos 74, já editáveis numa tela | 24 |
| **realmente sem tela** | **50** |

O docstring afirma que a lista sem dona tem "26 arrays e 4 objetos". No schema
inteiro sim; na lista sem dona são **23 e 4**, porque três arrays já estão do
lado com dona.

### Não existe página Settings chamada "The agent" nem "Knowledge"

O plano aloca grupos a elas. A subnav tem **exatamente nove** páginas, e um
teste as congela. Mas `agent` (`routes.ts:211`) e `knowledge` (`routes.ts:193`)
**são áreas declaradas de verdade**, com rota própria. O plano é coerente; o que
está estreito é o mapa, cujo campo `page` só aceita id de página Settings.
**Decisão:** alargar para `declared_areas()`. A regra honesta sobrevive — dona
tem de ser página a que se consegue navegar.

### O mapa fica no console, e o plano diz o contrário

O plano manda o mapa viver junto ao schema, no backend, e a T003 pede teste de
que o console o consome pela API. **Não é construível sem inverter a tabela de
tiers**: o mapa responde "qual **tela do console** edita este campo", e nenhum
módulo Python pode conhecer id de tela. O que impede a lista paralela de mentir
é o teste de contrato, que lê os caminhos de `declared_fields()` e falha
nomeando o campo quando as duas discordam. T003 fica declarada como não
construída, com essa razão.

### `resolution-preview.tsx` já existe, noutro lugar

Está em `console/src/surfaces/settings/resolution-preview.tsx`, não onde o plano
diz. A T004 é mover, não promover — cuidando de não desfazer a extração das
funções puras para `settings/values.ts`, que a 040 fez porque um módulo
`'use client'` exportando o que um server component chama quebra **só** em build
de produção.

### Não existe alvo `check-config-parity`

A verificação existe como teste de contrato, e já roda dentro do `make verify`
pelo alvo `test`. O alvo nomeado não existe, e o vermelho dele já está lá.

### A T007 perde o sujeito

Ela constrói o aviso exibido **dentro** do editor cru para grupos já migrados.
Com o editor morrendo nesta feature, não sobra editor para carregar aviso. É a
única task que desaparece, e desaparece declarada.

## 8.2 As duas decisões do operador — assinadas 2026-08-16

**Primeira: as seções avançadas reusam o `ConfigEditor`, escopado por prefixo,
num `<details>` recolhido da página dona.** Não são 50 controles desenhados à
mão.

O padrão já está pronto e funcionando em
`console/src/surfaces/settings/notifications.tsx:78-180`: resolve o nó, lê
`/v1/config/{node_id}` e `.../fields`, **filtra por prefixo** em `:112-114`, e
renderiza a tabela de valor efetivo com origem mais o `ConfigEditor`.

É por isso que a prévia de resolução e a origem do valor **saem de graça**: o
`ConfigEditor` já exige prévia antes de salvar (`preview.tsx:566-585`, e o botão
de salvar só aparece com prévia atual, `:718-732`) e o `FieldRow` já imprime
`Set at: <nó>` / `usingDefault` / `inherited` (`:810-824`). Os dois requisitos
estão satisfeitos **pelo componente**; são para verificar, não para reconstruir.

A leitura de "nunca num editor genérico ressuscitado": o editor genérico é a
tela `/configuration`, aberta sobre o schema inteiro. Um `ConfigEditor` escopado
a um prefixo, dentro da página dona daquele grupo, é a seção avançada que a
própria frase autoriza.

**Segunda: o editor cru morre nesta feature.** Sem estágio transitório. O
burndown vai a zero, a paridade fica verde, `/configuration` redireciona por
seção, e `screens/configuration.tsx` sai da árvore com a rota e a área.

## 8.3 A alocação dos 50, com id de área real

| Prefixo | Editáveis | Dona |
|---|---|---|
| `policies.observation.*` | 22 | `settings-alert-intake` |
| `agents.*` | 9 | `agent` |
| `policies.{changes*,memory,strategy,knowledge}` | 8 | `knowledge` |
| `policies.sso.{claims.*,is_active,verified_digest}` | 6 | `settings-single-sign-on` |
| `policies.autonomy` (4 escalares) | 4 | `settings-autonomy-guardrails` |
| `surfaces.console.tutorial_dismissed` | 1 | campo de máquina, sem formulário |

Os array/objeto ganham dona nomeada também — a regra "nenhum resto" continua —
mas sem controle, e a razão declarada é o **tipo**, não o esquecimento. Isso
obrigou uma terceira categoria no mapa: com dona / campo de máquina / sem
controle por tipo. Com duas listas o burndown nunca chegaria a zero, porque
sempre sobrariam 30 campos que ninguém pode editar em lugar nenhum.

E a invariante que substitui o `len(unowned) == 101`: **nenhum campo de tipo
editável fora da categoria com dona**. Um número envelhece a cada tela; a
propriedade continua verdadeira depois da feature e falha se alguém acrescentar
um campo editável sem tela.

## 8.4 Duas armadilhas da remoção, medidas antes de delegar

- `console/visual/screens.json:85-86` registra `configuration-1440-light` contra
  `/configuration`, e o PNG correspondente foi **aceito sob revisão humana** em
  `f3327d0`. Tirar a entrada sem tirar o PNG derruba
  `test_no_baseline_belongs_to_a_screen_nobody_registered` — a 010 já tropeçou
  nisso. Os dois saem juntos, e por ser `.png` commitado sendo removido, tem de
  ser dito em voz alta no relatório.
- A área `configuration` sai de `routes.ts:318`, o que mexe na contagem de áreas
  que o teste de cobertura e a caminhada de deploy seguram. Além disso **~20
  arquivos** ainda nomeiam `/configuration`, incluindo um CTA deliberado em
  `schedules-destinations.tsx:252` e os 23 CTAs em 9 arquivos que a 001 deixou
  como item aberto.
