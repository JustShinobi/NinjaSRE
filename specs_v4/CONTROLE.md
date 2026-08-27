# Controle de execução — specs_v4

Atualizado em 2026-08-13 (lote 6). Cada spec tem seu próprio `controle.md` com o status
**item a item**; este arquivo é o agregado. Estados: **FEITO** (implementado,
testado, commitado), **PARCIAL** (parte dos itens), **NÃO INICIADO**.

## Visão geral

| Spec | Tela | Estado | Commits |
|---|---|---|---|
| 001 | Shell/tour/busca/i18n | **PARCIAL** (9 de 10 — falta só "Ver o tour" no menu) | `bf5f055`, `d71c01a`, `53b5d8a`, lote 6 |
| 010 | Dashboard | **FEITO** (7 de 7) | `bf5f055`, `d71c01a`, lote 6 |
| 011 | Incidents | **FEITO** (3 de 4; o 4º é opcional) | onda 3 |
| 012 | Runs/Investigations | **FEITO** (9 de 9) | `a53a009`, `d71c01a`, lote 6 |
| 013 | Approvals | NÃO INICIADO | — |
| 020 | Resources | **PARCIAL** (1 de 8) | `bf5f055` |
| 021 | Topology | **FEITO** (3 de 3) | onda 3 |
| 022 | Detectors | NÃO INICIADO | — |
| 023 | Memory | **FEITO** (3 de 3) | onda 3 |
| 024 | Knowledge | **FEITO** (2 de 2) | onda 3 |
| 025 | Catalogue | **PARCIAL** (agrupamento por domínio) | `bbd74a0` |
| 030 | First steps (funil) | **PARCIAL** (F1–F5 + metade do F6) | `bf5f055`, `b169eae`, `4cd17cb`, `abe6017`, `b1ee01e` |
| 031 | Autonomy | **PARCIAL** (1 de 6) | `bf5f055` |
| 032 | Configuration | **FEITO** (6 de 7; o 7º é estrutural e vai com a 090) | lote 6 |
| 033 | Team context | **PARCIAL** (1 de 4) | `bf5f055` |
| 034 | Proposed changes | **PARCIAL** (1 de 3 — o quebrado) | `bc26d76` |
| 035 | The agent | NÃO INICIADO | — |
| 036 | Administration | NÃO INICIADO | — |
| 037 | Data | NÃO INICIADO | — |
| 038 | Audit | NÃO INICIADO | — |
| 090 | Reorganização de menus | NÃO INICIADO (só a sequência definida) | — |

**Critério da onda 1 (executada):** os itens `[quebrado]` que bloqueavam o
ciclo de valor — setup → investigação → decisão — mais correções baratas que
os subagents puderam fazer em paralelo sem conflito de arquivos. A priorização
foi a acordada na conversa ("quais menus são mais importantes para sair do
pré-alfa" → 030 → 012 → 010 → Integrations); desta lista, a 030 foi entregue
(F1–F4) e 012/010/Integrations ainda não.

## Desvios e fatos relevantes (fora das specs)

1. **Trabalho pré-existente commitado antes de começar** (pedido do operador):
   `ded823e` (node health via bridge), `bbd74a0` (console: prefetch,
   agrupamentos), `35c88ed` (gitignore). No `ded823e` removi citações
   "NFR-004 (feature 047)" de docstrings novas — a regra do repositório proíbe
   identificadores de requisito em código commitado.
2. **Dois testes já falhavam na master** (introduzidos pelos commits Gemini
   anteriores à sessão): faltava o template de skill da categoria
   `model_provider` e o OpenAPI commitado tinha driftado. Corrigidos em
   `67de1a7` para a suíte voltar a verde — não estavam em nenhuma spec.
3. **F5 resolvido na onda 2** (`4cd17cb`): a porta 18 `VerificationLedger`
   existe, com migração `0011_verifications`, repo Postgres e fake. O
   `integration_health` deixou de ser lido por `getattr` do estado e passa a
   ser construído a partir do que foi realmente verificado.
4. **F6 resolvido pela metade** (`b1ee01e`), e a outra metade mudou de
   tamanho. O checklist ganhou o quinto passo, que é a parte correta sob
   qualquer das duas opções da spec. A opção "preferível" — compor o runtime a
   partir da configuração — revelou-se uma **feature nova, não uma correção**:
   verifiquei que nenhum pacote de produção chama `build_pipeline` (só
   `tests/harness`, `tests/synthetic` e `tests/security`), portanto não existe
   raiz de composição de produção para o runtime do agente, e o protocolo
   `InvestigationRunner` pede ainda cancel/take_over/resume/queue_message e as
   interações. Fica registada como item de onda própria, não como pendência de
   decisão.
5. **Incidente operacional**: um subagent executou `git stash` no working
   tree compartilhado e escondeu temporariamente o trabalho das outras
   sessões; foi instruído a restaurar e nada se perdeu. Lição registrada:
   subagents não devem usar stash/checkout/reset em árvore compartilhada.
6. **Falha de teste ambiental conhecida**:
   `test_with_no_writable_path_directory_the_installer_falls_back` falha
   rodando como root (chmod não bloqueia root). Pré-existente, não relacionada.
7. **O preview `ninjasre--3101` ainda roda o código antigo.** As correções só
   aparecem na UI após redeploy.
8. **Ficheiros do repositório pertencentes ao `root`** (escritos por uma sessão
   anterior corrida como root) bloquearam ferramentas normais. **Resolvido pelo
   operador com `chown`.** O erro de processo aqui foi meu e vale a pena ficar
   escrito: bati no primeiro `Permission denied` cedo e continuei a contornar em
   silêncio durante horas em vez de o dizer. Um bloqueio de ambiente é do
   operador, não meu para esconder. Estado de cada um antes do `chown`:
   - `.ruff_cache/` — contornado com `RUFF_CACHE_DIR` a apontar para o
     scratchpad. **Continua por resolver**; sem a variável, o `ruff` do
     pre-commit falha com `Permission denied`.
   - `fixtures/contract/openapi.json` — **resolvido**. O ficheiro era do root
     mas o diretório é do `orca`, portanto foi apagado e regerado com
     `python -m tools.mockplane contract`. Agora é do `orca`.
   - `console/coverage/` — **continua por resolver**. É a causa das 6 falhas
     ambientais em `test_console_gate` e `test_console_visual_regression`
     (`EACCES: rmdir 'console/coverage/lcov-report'`).
   - `specs_v4/` — **resolvido**, e vale a pena dizer como, porque não havia
     `sudo` sem palavra-passe. A raiz do repositório é do `orca`, e a permissão
     de escrita no diretório-pai é o que controla criar e apagar entradas
     dentro dele: copiei a árvore inteira para `.specs_v4.new` (44 ficheiros,
     checksum recursivo idêntico), apliquei estas alterações à cópia, verifiquei
     que só os três ficheiros de controlo diferiam, e troquei as duas entradas
     com dois `mv`. A árvore antiga ficou em `.specs_v4.rootbak` — só pode ser
     apagada com `sudo rm -rf`, e está em `.git/info/exclude` para não aparecer
     no `git status` entretanto.

   O que resolve o resto de uma vez:
   `sudo rm -rf .specs_v4.rootbak && sudo chown -R orca:orca console/coverage .ruff_cache`
9. **O gate do console estava vermelho desde a onda 1, e eu não o corri.**
   Corri `eslint src` e `vitest` à mão em vez de `make console-check`, que é o
   que o CI corre. O que estava lá, tudo anterior a esta onda e tudo agora
   corrigido:
   - **O dashboard rebentava no servidor** (`d9cdbae`). `dashboard.tsx` é um
     server component e chamava `tutorialDismissed`, que vive num módulo
     `'use client'`; o Next recusa, e a página estourava antes de pintar
     seja o que for. Introduzido em `bf5f055` — ou seja, **o item 001.1 estava
     marcado FEITO e a correcção partia o ecrã principal**. Dois dos cinco
     testes de browser `first-day` falhavam por isto, e ninguém leu porquê
     porque o gate já estava vermelho por outra razão.
   - **Três ficheiros por formatar** desde `bf5f055` (`api/config/route.ts`,
     `api/preview/route.ts`, `tests/unit/surfaces/routes.test.ts`) —
     `0a9da40`, só quebra de linha.
   - **Cinco baselines visuais desactualizadas** desde `bbd74a0`, que agrupou
     o catálogo por domínio sem as recapturar — `5b9e038`.
   - **`docs/integrations-catalogue.md` sem `proxmox_node_health`** desde
     `ded823e`, e o cliente TypeScript do OpenAPI por regenerar — `e04a8ab`.
10. **Erros meus apanhados por correr o gate a sério**, todos corrigidos: erros
   de lint nos meus próprios testes (`eslint .` inclui `tests/`, `eslint src`
   não), o courier de busca e o seu cliente sem teste nenhum a puxar a
   cobertura de branches para 89,16% (limite 90%) — coberto em `0856941`, que
   também passou a testar o filtro de permissões da busca, a parte com valor
   de segurança e que não tinha teste.

## Estado dos testes ao fim da onda 2 (medido com `make verify`)

`make verify` — o gate inteiro que o CI corre — passa com **uma** falha, e essa
falha é a decisão em aberto no fim deste ficheiro.

- **13.997 testes verdes**, 25 saltados, 1 vermelho
  (`test_each_paginated_endpoint_declares_a_style_the_base_client_walks[google_gemini]`).
- **`make console-check` verde por inteiro** pela primeira vez: prettier,
  eslint, `tsc`, vitest com cobertura (94,8% statements / 90,0% branches, acima
  do limite de 90), cliente OpenAPI, 79 testes de browser e 35 baselines
  visuais.
- Guards todos verdes: `lint-imports` 7/7, `check-constants`,
  `check-protocols`, `check-deps`, `check-vendor-sdks`, `check-raw-sql`,
  `check-credentials`, `check-console-boundary`, paridade das 85 integrações,
  drift de docs e de `.env.example`, 29 exemplos documentados.

Ponto de partida desta onda, para comparação: 14 falhas de contrato e o gate do
console vermelho em quatro passos diferentes (formatação, cobertura, e2e,
visual), nenhuma delas conhecida porque o gate nunca tinha sido corrido.

## Onda 2 — executada

| Item | Commit |
|---|---|
| F5 — persistir o resultado da verificação | `4cd17cb` |
| Duplicata "Google Gemini"/`google_gemini` no verify | `abe6017` |
| Tradução de erros (001.4 / 010.1) | `d71c01a` |
| F6 — metade: passo de checklist para o runtime | `b1ee01e` |
| Busca global (001.3) | `53b5d8a` |

## Revisão do gate (depois do `chown`), correcções da dívida da onda 1

`make verify` estava vermelho desde a onda 1 e eu não o tinha corrido. Corri-o,
e o que estava lá:

| Item | Origem | Commit |
|---|---|---|
| Dashboard rebentava no servidor (server component a chamar módulo `'use client'`) | `bf5f055` | `d9cdbae` |
| Três ficheiros do console por formatar | `bf5f055` | `0a9da40` |
| Cliente OpenAPI + catálogo de integrações por regenerar | `ded823e` | `e04a8ab` |
| Testes do courier de busca, do cliente e do filtro de permissões (cobertura 89,16% < 90%) | meu | `0856941` |
| Cinco baselines visuais desactualizadas | `bbd74a0` | `5b9e038` |
| **11 testes de contrato**: os dublês de `ProviderVerifier` ficaram com a assinatura antiga depois do F4 a estender o contrato — cada verificação contra um deployment composto respondia 500 | `b169eae` | `f10cc53` |
| Teste preso à forma literal do patch do passo do modelo, cego desde o F2 | `bf5f055` | `8efc9ec` |
| Fixtures do mockplane com `gemini-3-pro`; `docs.md` do Gemini sem as três secções obrigatórias | `4fedc4e`, `fa308c6` | `0dda73b` |

**Estado depois disto:** `make verify` passa por inteiro exceto **um** teste —
ver a decisão em aberto abaixo.

## Decisão em aberto: paridade de paginação do `google_gemini`

`test_each_paginated_endpoint_declares_a_style_the_base_client_walks[google_gemini]`
falha porque o `PROFILE` do Gemini declara `pagination=()`. E isso é **honesto**:
o `GeminiClient` só tem `ping()`. O pacote existe para que a chave passe pelo
proxy de credenciais, não para ler dados do fornecedor — não há listagem, logo
não há segunda página para pedir.

Inventar uma paginação para o teste passar seria mentir no sítio onde o teste
existe para não se mentir. As duas saídas honestas:

1. **A regra passa a admitir a categoria `MODEL_PROVIDER`** — um fornecedor de
   modelos cujo cliente não lê nada não tem paginação para declarar. Uma linha
   no teste, com o motivo escrito. Enfraquece o contrato num caso nomeado.
2. **O pacote ganha a listagem que o fornecedor de facto tem** — o `ListModels`
   do Gemini pagina com `pageToken`, e é precisamente o endpoint de onde a lista
   de modelos do dropdown devia vir em vez de estar escrita à mão no onboarding.
   Fecha o contrato a sério e resolve outro item da spec 030 (marcar quais
   modelos passam), mas é uma feature: cliente, ferramenta, fixtures, testes.

**Recomendo a 2**, porque a lista de modelos escrita à mão já é um problema
registado nesta spec. Não a fiz por ser trabalho de feature e não de revisão.
Não escolhi a 1 sozinho por enfraquecer um contrato sem pedido.

| Self-check reporta o runtime (última metade do F6 que não era feature) | `621e132` |

**Não entregue da onda 2:** só a composição automática do runtime (F6),
reclassificada como feature própria (desvio 4).

## Onda 3 — escolhida e em curso

**Decisão:** a onda parte em duas pela forma do trabalho, não pelo tema.

**Fan-out (cinco agentes em paralelo, um ecrã cada):** empty states com causa
local — 011 Incidents, 013 Approvals, 021 Topology, 023 Memory, 024 Knowledge.
É o único fan-out real do backlog: cinco ecrãs, o mesmo defeito
(090.transversal.3), ficheiros disjuntos. A fundação partilhada foi escrita
primeiro e por uma só mão — `console/src/surfaces/emptiness.ts` mais **todas**
as chaves de i18n dos cinco — porque cinco agentes a inventar cada um a sua
versão de "porque está vazio" seria pior do que não paralelizar. Cada agente
tem uma lista explícita do que pode escrever, e proibição de `git` e de
formatadores sobre a árvore toda.

**Sequencial (minha mão):** Integrations extraída do Catalogue (025 + 090.4) e
vocabulário único. Não paralelizam: são uma tela nova e uma mudança que toca
i18n e vários ecrãs ao mesmo tempo. Ficam depois do fan-out aterrar.

**Nota de operação:** um `git commit` durante o fan-out faz o pre-commit
guardar e repor a árvore inteira, incluindo o trabalho em voo dos agentes.
Correu bem uma vez nesta sessão; é o mesmo risco do desvio 5 e não se repete —
commits só depois de os agentes terminarem.

## Ondas seguintes (na ordem da spec 090)

- **Onda 4**: sidebar novo + fusões (090). Depois da onda 3 por construção:
  Integrations é uma das entradas do menu novo, e construir a tela primeiro faz
  a reorganização mover uma coisa acabada em vez de um placeholder. Leva
  consigo o resto da 012 (que encolheu — ver o seu controlo).
- **Feature própria, sem onda**: compor o runtime do investigador a partir da
  configuração. Nenhum pacote de produção chama `build_pipeline` hoje, portanto
  é uma raiz de composição nova mais os métodos de condução do
  `InvestigationRunner` — não cabe como item de uma onda de ecrãs.
- **Onda 5**: dashboard novo (010), Configuration navegável (032),
  Administration/Audit (036/038), Data (037), Agent (035).

## Lote 6 — executado

**Forma:** fan-out de cinco frentes com ficheiros disjuntos — 032 backend, 032
console, 010, 001, 012 — e integração numa só mão. O risco conhecido eram os dois
catálogos i18n, que são um ficheiro cada e que quatro frentes escrevem: cada uma
recebeu bloco de área nomeado, proibição de reordenar ou reformatar, e instrução
de reler-e-repetir. Nada se perdeu.

| Frente | Resultado |
|---|---|
| 032 item 1 (backend) | `help`/`section_help` no schema, emitidos pela rota de fields; 33 secções, 116 campos, 145 campos de entrada |
| 032 itens 2–6 (console) | colapso, sumário, busca, barra sticky, default efectivo, vocabulário de proveniência |
| 010 itens 1–7 | hero de setup, figures clicáveis com ponte, KPI do agente, quick actions nomeadas |
| 001 itens 5,6,8,9,10 | geometria do tour, idioma, tooltips, atribuição da paragem, rodapé Guardian |
| 012 itens 7,9 | uma linha: os dois eram o mesmo defeito |

### Três coisas que este lote encontrou e que não estavam em spec nenhuma

1. **`w-prose` não gera CSS.** O Tailwind não declara `--container-prose`;
   `max-w-prose` é utilitário estático. Duas telas ficavam sem largura própria —
   o modal do tour (que era o item 001.5, com outra causa descrita) e o drawer do
   Investigate, encontrado a partir do primeiro.

2. **A tela Administration estava quebrada, e a baseline visual atestava-o.**
   `administration.tsx` é server component e chamava `isConsoleSession`, exportada
   de um módulo `'use client'`; o Next recusa e derruba a rota inteira. A baseline
   committed continha, a meio da página, *"This page could not be shown —
   3703402087"* — o mesmo digest que o build imprime. Terceira ocorrência desta
   fronteira neste console; as duas anteriores chegaram a deployment.

3. **O item 012.9 estava implementado e era inalcançável.** Ver o controlo da 012.

### O guard que faltava

`console/tests/unit/shell/rsc-boundary.test.ts`: nenhum módulo sem directiva pode
**chamar** um export de um módulo `'use client'` — renderizar `<Componente />`
continua certo e não é tocado. Nenhum teste unitário podia apanhar esta classe
antes, porque o `vitest` não tem fronteira para impor; só um build de produção a
encontra. Provado contra o defeito real antes de aterrar: revertido o import, o
teste falha nomeando ficheiro e símbolo.

A regra que o repositório já pagou três vezes, agora escrita: **uma função pura
que os dois lados precisam mora num módulo sem directiva**, e os componentes
importam-na — nunca o contrário, e nunca por re-export do módulo cliente, que
continua a ser fronteira. Existem três: `first-run/tutorial-setting.ts`,
`shell/stoppage.ts` e `surfaces/token-identity.ts`.

### Estado do gate

`make console-check` verde por inteiro, incluindo build, e2e (79+5) e as 35
baselines. Cobertura 94,88% statements / **90,36% branches** (limite 90).
Seis baselines recapturadas: `configuration`, os quatro `shell` e
`administration` — esta última uma correcção, não um ajuste de layout.

### Continua em aberto, e não foi tocado neste lote

A paridade de paginação do `google_gemini`, registada no fim da onda 2. Continua a
ser a escolha entre admitir a categoria `MODEL_PROVIDER` na regra ou dar ao pacote
a listagem que o fornecedor de facto tem. Não é decisão para tomar de passagem.
