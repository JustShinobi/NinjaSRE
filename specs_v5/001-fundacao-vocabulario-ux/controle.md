# Controle — 001-fundação-vocabulário-ux

Estado abaixo verificado contra o código atual em `HEAD 6fb1525` mais as mudanças
desta entrega, em `2026-08-14`. Cada linha cita `file:line` que pode ser aberto.
Gates citados como rodados foram de fato executados nesta sessão; o texto de
erro de qualquer um que falhou está reproduzido nas seções abaixo.

## Ledger — Requisitos Funcionais

| Peça | Estado | Detalhe |
|---|---|---|
| FR-001, cláusula "vocabulário canônico de quatro estados + Unknown" | FEITO | `console/src/design/status.ts:120-166` — `CREDENTIAL_STATUSES` (`not_connected, stored, verified, failing, unknown`) e `credentialStatus()`, reconciliando as duas vocabulárias de backend (`HealthStatus`, `SETUP_READINESS`) num só conjunto. |
| FR-001, cláusula "definido em um único módulo" | FEITO | Mesmo módulo acima. Console apenas — ver "Fora do escopo" abaixo para CLI/notificações. |
| FR-001, cláusula "consumido por console, CLI, notificações" | PARCIAL — console feito; CLI e notificações fora do escopo desta entrega | Ver "O que fica pendente". |
| FR-002, "exatamente um componente visual (chip)" | FEITO | `console/src/components/status.tsx:189` — `StatusChip`, único ponto que traduz qualquer grafia crua para uma das cinco palavras e desenha o chip. Registrado na galeria em `console/src/gallery/registry.tsx` (entrada `StatusChip`, 5 variantes). |
| FR-002, "texto livre de estado é proibido" | FEITO nas três telas do escopo (integrations, first-run, administration) | Ver T005/T006 abaixo. `catalogue.integrations.filter.state.unknown` corrigido de "Unchecked" para "Stored" (`console/src/i18n/en.ts`, chave próxima de `catalogue.integrations.filter.state.*`). |
| FR-003, "todo id de catálogo tem nome de exibição e categoria" (integrações) | FEITO | `integrations/_catalogue/entry.py:80-104` — `IntegrationProfile.display_name`, obrigatório, com invariante de construção. Todas as 85 pacotes de vendor atualizados (ver lista de arquivos). |
| FR-003, mesmo, para providers de modelo | FEITO (verificado, já existia parcialmente) | `core/llm/onboarding/__init__.py:56-77` já declarava `display_name`; adicionei a invariante de construção (`__post_init__`, linha 71) que faltava. |
| FR-003, "a interface DEVE usar o nome de exibição em títulos, listas e labels" | FEITO nas duas telas tocadas (Integrations, o painel "What is set up so far" do first-run) | `console/src/surfaces/integration-card.tsx` (prop `displayName`, usada na `<span className="text-strong">`), `console/src/surfaces/screens/first-run.tsx` (`established` array carrega `displayName`, resolvido a partir de `offers`/`providerRecords` já buscados pela própria tela). |
| FR-004, "sem display_name reprova em guard check, não degrada em runtime" | FEITO | Invariante de construção: `integrations/_catalogue/entry.py:100-104` (`IntegrationProfile.__post_init__`) e `core/llm/onboarding/__init__.py:71-76` (`ProviderOnboarding.__post_init__`) — ambas levantam `ValueError` antes que o catálogo exista para ser lido. Guard adicional (`make check-display-names`) cobre a mesma invariante como confirmação isolada e rápida: `tools/check_display_names.py:29`, alvo `Makefile:294`, ligado a `verify` (`Makefile:23`, `Makefile:378-379`). |
| FR-005, "todo CTA declara destino preciso (rota + âncora/filtro) e verbo" | FEITO o mecanismo; migrados 3 usos existentes | `console/src/design/empty-state.ts:15-49` — `CtaTarget`/`resolveCta()`. Usos: `console/src/surfaces/emptiness.ts:52` (`setupCause` → `/first-run`), `:69` (`watchingCause` → `/signals?tab=observation`), `console/src/surfaces/setup-hero.tsx:59` (empty do painel → `/first-run`). |
| FR-005, "nunca aponta para um editor genérico" | PARCIAL — não regride, não avança em geral | Ver "O que fica pendente": 23 CTAs em 9 arquivos ainda apontam para `/configuration` (o editor cru). Nenhum deles é dos dois exemplos motivadores da spec (Autonomy, Destinations) que eu tenha alterado incorretamente — eles continuam exatamente como estavam, porque não existe hoje um destino melhor para a maioria (a tela substituta é o trabalho de 040/050/060/070). |
| FR-006, "referência recolhida por padrão ou em página dedicada" | FEITO o mecanismo; sem uso de prova numa tela | `console/src/design/reference.tsx:29` — `Reference`, recolhido por padrão (testado). Não conectado a uma tela real — ver "O que fica pendente". |
| FR-007, "contagens de progresso servidas por fonte única, sem recomputação local" | FEITO, com uma decisão documentada abaixo | `console/src/surfaces/first-run/plan.ts:187-199` — `outstanding()` agora lê `setup.steps` (o array que `GET /v1/setup/checklist` de fato serve) em vez de filtrar o `WIZARD_STEPS` do próprio console contra `stepDone()`. Decisão de design abaixo. |
| FR-008, "~2 viewports em 1080p" | FEITO o instrumento de medição | `console/tests/e2e/scroll-budget.spec.ts` — mede as 6 telas do grupo Settings a 1920×1080. Ver limitação do dataset abaixo (SC-004). |
| FR-009, "todo texto novo entra pelo catálogo de i18n" | FEITO | Toda string nova está em `console/src/i18n/en.ts` e `pt-BR.ts`. `pnpm exec eslint` (regra `no-untranslated-strings`) e a suíte de i18n (`tests/unit/i18n/catalogue.test.ts`) verdes — ver gates. |
| FR-010, "contrato de CTA e orçamento de rolagem verificáveis por teste" | FEITO | Inventário: `tests/contract/console/test_console_success_criteria.py:231` (`test_every_typed_cta_targets_a_route_the_manifest_declares`). Orçamento: `console/tests/e2e/scroll-budget.spec.ts`. |
| FR-011, "ajuda mora no campo, não em subtítulo de prosa" | Fora do escopo desta entrega — mecanismo já existia | Ver "O que fica pendente". |

## Ledger — Cenários de aceitação (User Stories 1–5)

| Cenário | Estado | Detalhe |
|---|---|---|
| US1 · credencial recém-gravada → "Stored" | FEITO | `credentialStatus('configured')` e `credentialStatus('unknown')` → `'stored'` (`console/src/design/status.ts:150-160`). Confirmado por `console/tests/unit/design/status.test.ts` ("maps every raw spelling…") e por `console/tests/e2e/vocabulary.spec.ts`. |
| US1 · verificação que passou → "Verified" | FEITO | `credentialStatus('healthy')`/`'verified'` → `'verified'`. Mesmos testes. |
| US1 · verificação que falhou → "Failing" + diagnóstico | FEITO (o chip); o diagnóstico (`verdict.detail`) já existia e foi preservado | `console/src/surfaces/first-run/verify.tsx:148-175`. |
| US2 · `azure_monitor` → "Azure Monitor" / "Observability", id não aparece | FEITO para o padrão geral (todas as 85 integrações têm `display_name`); não verifiquei linha a linha os 85 nomes contra a marca real de cada vendor além de revisão própria | `integrations/azure_monitor/__init__.py` — `display_name="Azure Monitor"`. Ver observação sobre nomes abaixo. |
| US2 · id cru em contexto técnico, em mono | FEITO (já existia) | `data-integration={name}` continua a levar o id cru (`console/src/surfaces/integration-card.tsx`), nunca o display name. |
| US3 · Destinations sem chat → catálogo filtrado | Fora do escopo desta spec | Ver "O que fica pendente" — tela "Destinations" pertence a 060. |
| US3 · correção leva ao campo, não à raiz da tela | Fora do escopo desta spec | Mecanismo (`resolveCta` com `anchor`) pronto; nenhuma tela de verificação de modelo existe ainda para aplicá-lo (isso é 040). |
| US4 · intake de alertas mostra payload sob demanda | Fora do escopo desta spec | Tela de intake é 060. |
| US4 · catálogo linka para página de referência sobre "não cobertos" | PARCIAL — mecanismo pronto (`Reference`), não conectado | Ver "O que fica pendente": o bloco "known gaps" de `console/src/surfaces/screens/integrations.tsx:153-187` continua fora de fluxo apenas por já estar no rodapé, não recolhido. |
| US5 · mesma contagem em dashboard, Setup e empty states | FEITO | Todos os quatro consumidores (`dashboard.tsx`, `first-run.tsx`, `setup-hero.tsx`, `emptiness.ts`) chamam a mesma `outstanding()`, testado por `console/tests/unit/surfaces/first-run-plan.test.ts` ("counts what the deployment itself reports…") e pela varredura e2e. |

## Ledger — Edge cases

| Edge case | Estado | Detalhe |
|---|---|---|
| Estado desconhecido (gateway inacessível) → chip "Unknown" com tooltip, nunca inventa um dos quatro | FEITO | `console/src/components/status.tsx:189-211` — `credentialStatus()` nunca retorna um dos quatro por adivinhação; qualquer grafia não reconhecida degrada para `'unknown'`, e o chip carrega `title` com `status.credential.unknown.explain` só nesse caso. |
| Item de catálogo sem display name → build falha, não fallback silencioso | FEITO | Ver FR-004 acima. |
| CTA cujo alvo o viewer não pode abrir → CTA não aparece | FEITO o mecanismo (`ResolvedCta.permission`); não conectado a uma checagem de visibilidade em nenhuma tela ainda | `console/src/design/empty-state.ts:24-27,45-49` — `resolveCta()` devolve a permissão da área (`routes.ts`); nenhum dos três usos migrados (T012) precisa condicionar por permissão hoje porque cada um já está atrás do próprio gate de área. Nenhuma tela usa esse campo para *esconder* um CTA ainda — nomeado para 020/030 usarem. |

## Ledger — Critérios de sucesso

| SC | Estado | Detalhe |
|---|---|---|
| SC-001 · zero vocabulário fora do canônico | FEITO nas telas varridas (integrations, first-run, administration) | `console/tests/e2e/vocabulary.spec.ts`, 6 testes, verde — vermelho genuíno confirmado antes (ver gates). Não varre as outras 10 áreas do produto (fora do escopo — essas telas não mostram estado de credencial hoje). |
| SC-002 · zero snake_case em título/label | FEITO no catálogo de integrações | `console/tests/e2e/vocabulary.spec.ts:113` — `no integration card titles itself with a raw snake_case id`. Não varri as outras telas (agent.tsx, tokens.tsx etc.) que também podem mostrar ids de provider/role — fora do escopo desta rodada (nenhuma delas tem defeito equivalente identificado; ver observação abaixo). |
| SC-003 · 100% dos CTAs com destino auditado | PARCIAL | `tests/contract/console/test_console_success_criteria.py:231` audita os CTAs que passam por `resolveCta` (3 hoje). Os ~23 `href: '/configuration'` restantes (grep abaixo) não passam pelo mecanismo tipado e não são auditados por ele — continuam como estavam antes desta entrega. |
| SC-004 · nenhuma tela > 2 viewports com dados representativos (84 integrações, 15 tokens, 200 eventos) | MEDIDO, mas não nas condições representativas | `console/tests/e2e/scroll-budget.spec.ts` roda contra o dataset mock, que tem 3 integrações e nenhum histórico de audit — bem abaixo de "representativo". As 6 telas medem dentro do orçamento *nesse* dataset. Ver "O que fica pendente". |
| SC-005 · mesma contagem em 3 estados do deployment | FEITO | O teste de contrato (`test_the_progress_count_is_not_recomputed_from_the_console_s_own_wizard_steps`, `tests/contract/console/test_console_first_run.py:181`) mais os testes unitários de `outstanding()` cobrem estado zero, parcial e completo. |

## Ledger — Tasks (T001–T019)

| Task | Estado | Detalhe |
|---|---|---|
| T001 | FEITO | `config/constants/surfaces.py:311-352` — `CREDENTIAL_STATUSES` e as 5 chaves individuais; `CONFIG_SCREEN_VIEWPORT_WIDTH_PX`/`HEIGHT_PX`/`CONFIG_SCREEN_SCROLL_BUDGET_VIEWPORTS`. Exportado via `config/constants/__init__.py`. |
| T002 | FEITO — vermelho visto | `console/tests/unit/design/status.test.ts` (bloco "the credential and verification vocabulary", 6 casos nas linhas ~101-159). Rodei `pnpm exec vitest run tests/unit/design/status.test.ts` antes de implementar: 6 falhas genuínas (`credentialStatus is not a function`, roles errados). Depois: 18/18 verde. |
| T003 | FEITO | `console/src/design/status.ts:106-166` (vocabulário + `credentialStatus`), `console/src/components/status.tsx:160-211` (`StatusChip`). |
| T004 | FEITO | `console/src/i18n/en.ts` (bloco "The credential and verification vocabulary", antes de `surface.loading`) e equivalente em `pt-BR.ts`. |
| T005 | FEITO — vermelho visto genuinamente | `console/tests/e2e/vocabulary.spec.ts`. Vermelho confirmado revertendo via `git stash` os 6 arquivos-fonte da correção, rodando `python -m tools.console_e2e run --backing mock -- tests/e2e/vocabulary.spec.ts` (2 testes falharam, achando "UNCONFIGURED", "it answered"×2, "stored, unchecked", "Nobody has checked this one."×3), depois `git stash pop` e `make console-build` + nova rodada: 5/5 verde. |
| T006 | FEITO | `console/src/surfaces/integration-card.tsx` (Badge→StatusChip), `console/src/surfaces/first-run/verify.tsx` (StatusChip substitui StatusDot+frases livres, `VerifyStepLabels` perde `passed/failed/unchecked`), `console/src/surfaces/screens/first-run.tsx` (painel "established"), `console/src/i18n/en.ts`/`pt-BR.ts` (chaves `firstRun.verify.*`/`firstRun.established.*` removidas ou reescritas, `catalogue.integrations.filter.state.unknown` corrigida). |
| T007 | FEITO — vermelho visto | `tests/contract/console/test_console_display_registry.py`, 3 testes. Rodado antes da implementação: 1 passou (catálogo já tinha `display_name` por causa da ordem das minhas próprias edições — ver nota), 2 falharam genuinamente (`IntegrationView` sem o campo). Depois: 3/3 verde. |
| T008 | FEITO | `integrations/_catalogue/entry.py` (`IntegrationProfile.display_name`, `CatalogueEntry.display_name`, `to_record()`), as 85 `integrations/*/__init__.py`, `gateway/http/routes/integrations.py:120,257`, `fixtures/contract/openapi.json` e `console/src/api/schema.ts` regenerados via `make console-client`. |
| T009 | FEITO | Invariantes: `integrations/_catalogue/entry.py:100-104`, `core/llm/onboarding/__init__.py:71-76`. Guard: `tools/check_display_names.py`, alvo `check-display-names` no `Makefile:294`, em `verify`. |
| T010 | FEITO nas telas tocadas | `console/src/surfaces/screens/integrations.tsx:126` (`displayName` da API), `console/src/surfaces/integration-card.tsx`, `console/src/surfaces/screens/first-run.tsx` (painel established). Varredura: `console/tests/e2e/vocabulary.spec.ts:113`. |
| T011 | FEITO — vermelho visto | `console/tests/unit/design/empty-state.test.tsx`, 6 casos. Vermelho: módulo inexistente (`Failed to resolve import`). Depois: 6/6 verde. |
| T012 | PARCIAL | Implementado `console/src/design/empty-state.ts`; migrados 3 sites (`emptiness.ts` ×2, `setup-hero.tsx` ×1). Não migrei os ~23 `href: '/configuration'` restantes — ver "O que fica pendente". |
| T013 | FEITO | `tests/contract/console/test_console_success_criteria.py:231`. |
| T014 | FEITO — vermelho visto | `console/tests/unit/design/reference.test.tsx`, 4 casos. Vermelho: módulo inexistente. Depois: 4/4 verde. |
| T015 | PARCIAL | `console/src/design/reference.tsx` implementado e testado; nenhum uso de prova numa tela real — ver "O que fica pendente" (conflito descoberto com teste comportamental existente). |
| T016 | FEITO — vermelho visto | `tests/contract/console/test_console_first_run.py:181`. Rodado antes da mudança em `plan.ts`: falhou genuinamente (`'WIZARD_STEPS' is contained here`). Depois: verde. |
| T017 | FEITO, com decisão documentada abaixo | `console/src/surfaces/first-run/plan.ts:187-199`. |
| T018 | FEITO | `console/tests/e2e/scroll-budget.spec.ts`, 6/6 verde contra o dataset mock. |
| T019 | Este arquivo, mais os gates na seção seguinte. | — |

## A decisão de T017: de onde vem a contagem

A task oferecia duas opções e pedia para eu escolher e documentar. Escolhi
**"o console deriva de `steps` em um lugar"**, não "o gateway passa a servir
a contagem", pelos seguintes motivos:

1. `SetupChecklist` (`platform/startup/checklist.py:154-156`) já tem uma
   propriedade `outstanding` (uma tupla dos passos não feitos), mas ela nunca
   foi exposta em `ChecklistView`/`to_record()`. Servi-la exigiria regenerar
   o documento OpenAPI committed e o cliente TypeScript gerado — uma mudança
   de contrato de API que nenhuma task deste arquivo pede e que eu não quis
   fazer sem uma razão específica.
2. O console já recebe `setup.steps` (o array completo, com `state` por
   passo) na mesma leitura que hoje alimenta `stepDone`/`WIZARD_STEPS`. Somar
   quantos têm `state !== 'done'` não é uma heurística nova — é ler
   diretamente o mesmo documento que `GET /v1/setup/checklist` já serve, no
   lugar de filtrar contra `WIZARD_STEPS` (uma lista de sete passos que o
   backend nunca ouviu falar) combinada com regras client-only
   (`stepDone`, que também lê `provider`/`modelChosen`, esta última vinda de
   um endpoint *diferente*, `/v1/config/{node_id}`).
3. Isso satisfaz o espírito do FR-007 ("uma única fonte, sem recomputação
   local"): o número deixou de ser calculado sobre uma taxonomia que só o
   console conhece e passou a ser a contagem literal de um campo que o
   documento do backend já carrega — a mesma leitura que o CLI reconstruiria
   se fosse implementar a mesma soma.

**Efeito colateral descoberto e corrigido**: a mudança quebrou 7 testes em 6
arquivos (`approvals`, `detectors`, `incidents`, `memory`, `proposals`,
`topology` — nenhum deles telas que eu toquei) porque seus fixtures de
`/v1/setup/checklist` usavam `steps: []` ou nem declaravam `steps`, um
formato que o gateway real nunca produz (ele sempre serve os cinco passos de
`SETUP_STEP_ORDER`). Corrigi os seis fixtures para incluírem ao menos um
passo não concluído (ou, no caso de `memory.test.tsx`, ajustei a asserção de
"7 step(s)" para "4 step(s)", o número real do fixture de cenário `empty`
committed). Rodei a suíte vitest completa antes e depois: 1960/1967 → 7
falhas → todas corrigidas → 1967/1967.

## Nomes de exibição dos 85 vendors

Os 85 `display_name` foram escritos por mim, um por um, contra o conhecimento
que tenho de cada produto (ex.: `incident_io` → "incident.io", `flagd` →
"flagd" minúsculo, ambos preservando a estilização real da marca; `aws_ec2` →
"AWS EC2"). Não verifiquei cada um contra a documentação oficial do vendor —
é uma varredura de plausibilidade, não uma auditoria de marca. Se algum
estiver errado, é um `display_name="..."` de uma linha para corrigir em
`integrations/<vendor>/__init__.py`, sem tocar em mais nada (a invariante de
construção garante que não pode ficar em branco, mas não garante que o texto
está certo).

## O que fica pendente, nomeado, não escondido

- **FR-001, consumo por CLI e notificações.** O vocabulário canônico
  (`console/src/design/status.ts`) é consumido apenas pelo console. Não há
  hoje um lugar equivalente em `surfaces/cli/` ou nas rotas de notificação
  que renderize estado de credencial em texto livre — não encontrei um
  ponto onde o CLI mostra "it answered" ou similar — mas também não fiz uma
  varredura sistemática do CLI e das notificações para confirmar a ausência
  do problema, nem construí um módulo Python irmão do vocabulário. Quem
  tocar `surfaces/cli/` ou o pipeline de notificações para o estado de
  credencial deveria primeiro conferir se o mesmo problema existe lá.

- **FR-005/SC-003, os ~23 CTAs restantes que apontam para `/configuration`.**
  `grep -rn "href: '/configuration'" console/src/` encontra 23 ocorrências em
  9 arquivos: `team-context.tsx` (1), `configuration.tsx` (3, o próprio
  editor apontando pra si mesmo em painéis internos), `integrations.tsx`
  (1 — o empty state do painel principal, `catalogue.integrations.empty.action`),
  `data.tsx` (3), `dashboard.tsx` (1), `detectors.tsx` (1), `agent.tsx` (7),
  `resources.tsx` (5). Nenhum foi migrado para `resolveCta` nem redirecionado
  para outro lugar. Não fiz isso porque, hoje, `/configuration` é
  genuinamente o único destino que existe para a maioria dessas
  configurações — as telas humanas que deveriam substituí-lo são o trabalho
  de 020/030/040/050/060, e apontar para uma tela que não existe seria pior,
  não melhor. Nomeado aqui explicitamente para que uma spec futura que
  migre uma dessas telas saiba que o CTA precisa mudar junto.

- **FR-006/US4, o bloco "known gaps" do catálogo não está recolhido.**
  `console/src/surfaces/screens/integrations.tsx:153-187` continua
  renderizando a lista de vendors não cobertos por extenso, no rodapé da
  tela — exatamente o padrão que o Acceptance Scenario 2 da User Story 4
  pede para não fazer. Tentei envolvê-la em `Reference` e descobri um
  conflito real: `console/tests/unit/surfaces/behaviour.test.tsx:216-234`
  já testa esse bloco via `screen.getAllByTestId('known-gap')`, esperando os
  itens *imediatamente* no DOM — e `Reference` não renderiza os `children`
  quando recolhido (não é `display:none`, é ausência do nó). Migrar exigiria
  também reescrever esse teste para expandir o bloco antes de consultar, e eu
  preferi não fazer essa mudança sem ter orçamento para revisá-la com
  cuidado. `Reference` está pronto, testado isoladamente
  (`console/tests/unit/design/reference.test.tsx`), e pronto para 020 (que
  provavelmente reconstrói esta tela inteira) conectar.

- **SC-004, dataset representativo.** O dataset mock (`tools.mockplane`) tem
  3 integrações, não 84; nenhum evento de audit; poucos tokens. O
  `scroll-budget.spec.ts` mede o que existe, honestamente, e todas as 6 telas
  passam *nesse* dataset — o que não é o mesmo que provar SC-004 com dados
  representativos. Quando 020 (catálogo) e 050 (tokens/audit) povoarem o
  fixture com a escala real, é esperado que `/integrations` e possivelmente
  `/administration` comecem a estourar o orçamento — o teste vai flagar isso
  quando acontecer, porque ele lê a altura real do documento, não um número
  fixo.

- **FR-011, ajuda mora no campo.** Não construí nada novo para isso. O
  mecanismo já existe — `CredentialField`/`Input` já colocam a frase de ajuda
  sob o controle via a prop `description` (`console/src/surfaces/credential.tsx:52-58`,
  função `describe()`) — e nenhuma das 19 tasks pede a construção de um
  mecanismo equivalente para `field_help`/`section_help` do schema de
  configuração geral. Encontrei, e não toquei, um padrão pré-existente e
  disseminado que viola a letra do FR-011: **todas as 13 áreas do console**
  têm um subtítulo de prosa sob o título (`page.<area>.context` em
  `console/src/i18n/en.ts:74-95` e além, renderizado por `AreaHeader`) — não
  é uma regressão desta entrega, é como o produto já era. Corrigir isso é uma
  mudança no cabeçalho de todas as telas do produto, muito além de "aplicar
  onde a fundação já toca"; nomeio para o operador decidir se cabe em alguma
  spec futura ou é uma correção à parte.

- **Não fiz a varredura de snake_case (SC-002) fora do catálogo de
  integrações.** Não encontrei nenhuma instância clara de id cru em posição
  de título nas outras telas ao navegar o código (providers e roles já
  aparecem por `display_name`/palavra simples nos pontos que toquei), mas
  não escrevi um teste que prove a ausência em todo o produto — apenas em
  `/integrations`.

- **Arquivo inesperado na árvore.** `tools/spec_validation.py` e
  `tests/unit/tools/test_spec_validation.py` apareceram na árvore de
  trabalho (não rastreados) durante esta sessão; eu não os criei, não os
  editei, e o docstring deles cita literalmente o caminho desta feature e
  `console/tests/e2e/vocabulary.spec.ts` como exemplo de uso — parecem
  ferramenta de outra sessão/processo rodando concorrentemente na mesma
  árvore. Não toquei neles.

## Gates rodados, e o resultado real

Python:

- `uv run pytest -q` (suíte completa) — última rodada com número final
  observado: **14035 passed, 3 failed, 25 skipped**, feita **antes** da
  correção do gerador de fixtures (seção "Descoberta sobre o gerador de
  fixtures" abaixo). Das três falhas dessa rodada: uma é o benchmark de
  masking, que reproduzi isolado e passou limpo (ver linha abaixo); uma é a
  divergência visual esperada; a terceira,
  `test_rebuilding_the_dataset_reproduces_what_is_committed`, é exatamente o
  que a correção do gerador resolveu — reproduzi isso isoladamente depois da
  correção (`uv run pytest tests/contract/fixtures/test_dataset_coherence.py -q`,
  28/28 verde) e também rodei o pacote inteiro que cerca a mudança
  (`tests/unit/tools/mockplane/ tests/contract/fixtures/ tests/contract/console/`,
  588 casos, 587 passed e a única falha é de novo a divergência visual
  esperada). **Depois** da correção, iniciei uma rodada nova da suíte
  completa para ter um número final único; ela não terminou dentro da janela
  desta sessão (a suíte leva ~11 minutos e boa parte do tempo é gasto em
  subprocessos que `test_console_gate.py` spawna, não em CPU do processo
  pytest em si). Não tenho o número final único dessa última rodada — tenho
  a rodada anterior completa (14035/3/25) mais a confirmação isolada, dupla,
  de que a única causa nova das três falhas foi corrigida e re-verificada.
- `tests/benchmarks/test_masking_overhead.py::test_masking_stays_within_its_budget_on_a_ten_megabyte_payload`
  falhou uma vez na rodada completa (carga da máquina rodando lint/typecheck/
  vitest/Playwright em paralelo) e passou limpo quando rodado isolado
  (`uv run pytest tests/benchmarks/test_masking_overhead.py -q`, 4/4). Não é
  uma regressão desta entrega.
- `tests/contract/console/test_console_visual_regression.py::test_the_untouched_baselines_still_match`
  falha, esperado — ver "Descoberta sobre baselines visuais" abaixo. **Não
  rodei `console-visual-accept`.**
- `make lint` — verde (1 problema de ordenação de import auto-corrigido com
  `ruff check --fix` antes do resultado final).
- `make format-check` — verde (1 arquivo reformatado com `ruff format` antes
  do resultado final).
- `make typecheck` (mypy --strict) — verde, 1778 arquivos.
- `make check-imports` — verde, 7 contratos mantidos, 0 quebrados, 1672
  arquivos.
- `make check-constants` — verde.
- `make check-display-names` (novo) — verde.
- `make check-protocols` — verde.
- `make check-deps` — verde.
- `make check-console-boundary` — verde.
- `make check-vendor-sdks`, `make check-literals`, `make check-raw-sql`,
  `make check-credentials` — verdes (confirmados individualmente, sem saída
  além do eco do comando).
- `make check-integrations` (`verify_integrations`) — verde, **85
  integração(ões) em paridade total, toda permissão sondada**.
- `make check-integration-docs` — verde, sem drift.
- `make check-docs` — verde, sem drift.
- `make check-doc-examples` — verde, 29 exemplos conferem.
- `make check-env-example` — verde.
- `uv run python -m tools.mockplane verify` — verde, "the dataset is clean".
- `uv run pytest tests/contract/fixtures/test_dataset_coherence.py` — verde
  (28/28) **depois** da correção do gerador (ver descoberta abaixo).

Console:

- `pnpm exec vitest run` (suíte completa) — **1967 passed, 0 failed**, 127
  arquivos.
- `uv run python -m tools.console_gate test` (mesma suíte + cobertura) —
  cobertura 95.36/90.92/93.09/97.58 (piso 90) — verde.
- `pnpm exec tsc --noEmit` — verde.
- `pnpm exec eslint src tests` — verde.
- `pnpm exec prettier --check .` — verde.
- `uv run python -m tools.console_budget` — verde: stylesheet 24088/40960
  bytes (58%), ícones 10918/16384 bytes (66%).
- `uv run python -m tools.console_e2e run --backing mock -- tests/e2e/vocabulary.spec.ts` —
  vermelho genuíno confirmado (via `git stash` das correções) antes da
  implementação; **6/6 verde** depois.
- `uv run python -m tools.console_e2e run --backing mock -- tests/e2e/scroll-budget.spec.ts` —
  **6/6 verde** contra o dataset mock.
- `uv run python -m tools.console_visual compare` — **8 telas divergem do
  baseline committado**: `first-run-1440-light`, `integrations-1440-light`
  (consequência visível e esperada da migração de vocabulário — texto e
  chips mudaram de verdade) e `gallery-1440-dark`, `gallery-1440-light`,
  `gallery-320-dark`, `gallery-320-light`, `gallery-768-dark`,
  `gallery-768-light` (consequência de registrar `StatusChip` na galeria,
  conforme a regra "todo primitivo exportado tem de estar na galeria").
  **Não rodei `console-visual-accept`** — nenhuma task minha pede isso. Os 8
  baselines precisam ser recapturados e revisados por quem tem autoridade
  para commitar essa mudança.

Não rodei (fora do meu escopo, listado por nome, conforme a instrução):

- `make test-postgres` — nenhuma mudança em `platform/persistence/`.
- `make chaos-setup`/`chaos-run` — nenhuma mudança de infraestrutura de
  execução.
- `console-visual-accept`, `console-e2e-sweep` — não pedidos por nenhuma task.
- `make verify` completo de ponta a ponta como um só comando — rodei cada um
  dos seus componentes separadamente (listados acima) em vez do alvo
  agregado, porque o agregado inclui `console-check` que por sua vez roda
  `console-visual`, e eu queria ver o resultado de cada etapa isoladamente
  antes de deixar uma etapa expected-red (`console-visual`) esconder o
  resultado das outras.

## Descoberta sobre o gerador de fixtures

Ao editar `fixtures/scenarios/populated/integrations.json` e
`fixtures/scenarios/first-run/integrations.json` à mão para acrescentar
`display_name`, `tests/contract/fixtures/test_dataset_coherence.py::test_rebuilding_the_dataset_reproduces_what_is_committed`
pegou a divergência: esses arquivos não são escritos à mão, são gerados por
`python -m tools.mockplane build` a partir de `tools/mockplane/dataset/served.py`
e `tools/mockplane/dataset/build.py`. Revertive a edição manual, adicionei
`display_name` nos literais Python que constroem essas três entradas
sintéticas (`served.py`, duas ocorrências — a lista servida por
`integration_records()` — e `build.py`, uma ocorrência, o override do
cenário `first-run`), e rodei `python -m tools.mockplane build` de novo para
regenerar os `.json` committados a partir da fonte certa. Quem for editar um
fixture de `integrations.json` depois de mim: edite `served.py`/`build.py`,
nunca o `.json` diretamente — o teste de coerência existe exatamente para
pegar isso.

## Arquivos criados

- `console/src/design/empty-state.ts`
- `console/src/design/reference.tsx`
- `console/tests/unit/design/empty-state.test.tsx`
- `console/tests/unit/design/reference.test.tsx`
- `console/tests/e2e/vocabulary.spec.ts`
- `console/tests/e2e/scroll-budget.spec.ts`
- `tests/contract/console/test_console_display_registry.py`
- `tools/check_display_names.py`

## Arquivos alterados

- `config/constants/surfaces.py`, `config/constants/__init__.py`
- `Makefile`
- `console/src/design/status.ts`, `console/src/components/status.tsx`,
  `console/src/components/index.ts`, `console/src/gallery/registry.tsx`
- `console/src/i18n/en.ts`, `console/src/i18n/pt-BR.ts`
- `console/src/surfaces/emptiness.ts`, `console/src/surfaces/setup-hero.tsx`,
  `console/src/surfaces/labels.ts`, `console/src/surfaces/integration-card.tsx`
- `console/src/surfaces/first-run/plan.ts`, `console/src/surfaces/first-run/verify.tsx`
- `console/src/surfaces/screens/first-run.tsx`, `console/src/surfaces/screens/integrations.tsx`
- `console/tests/unit/design/status.test.ts`
- `console/tests/unit/surfaces/first-run.test.tsx`, `first-run-plan.test.ts`,
  `integrations.test.tsx`, `approvals.test.tsx`, `detectors.test.tsx`,
  `incidents.test.tsx`, `memory.test.tsx`, `proposals.test.tsx`,
  `topology.test.tsx`
- `integrations/_catalogue/entry.py`
- `integrations/<vendor>/__init__.py` para as 85 vendors (lista completa via
  `git status --short integrations/`)
- `core/llm/onboarding/__init__.py`
- `gateway/http/routes/integrations.py`
- `fixtures/contract/openapi.json`, `fixtures/scenarios/populated/integrations.json`,
  `fixtures/scenarios/first-run/integrations.json`
- `console/src/api/schema.ts` (gerado por `make console-client`)
- `tools/mockplane/dataset/served.py`, `tools/mockplane/dataset/build.py`
- `tests/contract/console/test_console_first_run.py`,
  `tests/contract/console/test_console_success_criteria.py`

## O que eu assumi, sem resposta explícita na spec/plano/mockup

- **Cores/formas dos três novos estados do chip.** O mockup só mostra três
  papéis em uso (`c-ok`/`c-off`/`c-bad` para Verificada/Não conectada/Falhou)
  e nunca mostra "Armazenada" com uma cor específica. Escolhi `info` (papel
  semântico "em andamento", nem sucesso nem problema) com a forma
  `dimmed-circle`, distinta de todas as outras formas neutras já declaradas.
- **`not_connected` reutiliza o papel/forma que `unconfigured` já tinha**
  (`neutral`/`dash`) — não inventei uma variação, porque semanticamente são
  o mesmo fato.
- **Nome do teste "administration"**: não encontrei nenhum chip de estado de
  credencial genuíno em `/administration` (os badges lá são sobre pessoa
  ativa/inativa e token revogado/ativo — um vocabulário diferente, fora do
  conjunto fechado desta spec). A varredura de frases proibidas ainda cobre
  essa tela (nenhuma delas aparece lá), mas não há chip para migrar.
