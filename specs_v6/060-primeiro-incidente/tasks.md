# Tasks: O primeiro incidente ponta a ponta

**Input**: Design documents from `specs_v6/060-primeiro-incidente/`

**Prerequisites**: plan.md, spec.md; feature 001 (catálogo pós-corte e intake
enxuto), 010 (provider verificado com tool-calling forçado e estado espelhado),
050 (Alert intake com a cadeia visível, onde o delivery token é emitido)

**Tests**: test-first. O acceptance spec do console e os testes de contrato nascem
antes da implementação e são **confirmados vermelhos** antes de qualquer código de
produção. Um vermelho não visto é um teste que não prova nada.

**Backing do acceptance spec**: `console/tests/e2e/060-primeiro-incidente.acceptance.spec.ts`
roda no projeto `behaviour` do Playwright com **backing `compose`** — gateway real
contra banco real, trazido pelo harness Python de e2e do console
(`--backing compose`), não pelo plano de dados simulado. A tela desta feature
mostra passos, custo e duração produzidos por uma investigação de verdade, e um
mock provaria apenas que o mock foi escrito com os campos certos.

**Viewport**: o Playwright roda em 1440×900 por padrão; a medição de orçamento de
rolagem declara 1920×1080 no próprio teste.

---

## Fase 1: Setup e fixtures

- [x] T001 Fixture do corpo de notificação agrupada do Alertmanager tal como a stack
      envia — um caso `firing` com vários alertas no grupo, um caso `resolved` do
      mesmo grupo, e uma reentrega idêntica do `firing`. Rótulos apontando um
      serviço real do cluster; nenhum segredo no arquivo.
      **FEITO**: `tests/contract/alerts/fixtures_alertmanager_delivery.py`.
      Verificado por script ad-hoc contra `gateway/webhooks/sources/alertmanager.py`
      e `core/domain/alerts/normalisation.py` — a retentativa deriva o mesmo
      `event_id`, a resolução deriva um diferente. Nenhum teste de contrato o
      consome ainda (isso é T005, fora desta fatia).
- [ ] T002 Fixture de incidente investigado: um incidente com os cinco tipos de
      passo (recebimento, hipóteses, evidência, diagnóstico, entrega), contagem de
      passos, duração e custo, e uma ação proposta aguardando decisão. É o dado que
      o acceptance spec lê e o que a baseline visual captura.
      **PARCIAL — o bloqueio por T020 está removido, o trabalho não está feito.**
      T020 já declara os cinco tipos (verificado, ver abaixo). Escrito, mas NÃO
      exercitado nem rebuilt:
      `tools/mockplane/capture/projection.py` ganhou `_investigated()` (aponta o
      primeiro incidente para `run-0005`, que já existe em
      `tools/mockplane/dataset/served.py` como `awaiting_approval` com a proposta
      `apr-0001` de religar um job de backup — mesma matéria do detector
      `backup-job-disabled`), e `_timeline()`/`_investigation_timeline()` novos
      que anexam `run_started` + os cinco passos de raciocínio (evidência com
      `query`/`result` reais, citando os dois jobs desativados que
      `observations` já carrega) ao PRIMEIRO incidente de `estate()` — o mesmo
      que `platform/startup/demo/seeder.py:_seed_incidents` semeia (é o único
      que recebe timeline). `ast.parse` confirma sintaxe válida; NADA além disso
      foi verificado. `python -m tools.mockplane build` NÃO rodou.
      `fixtures/scenarios/` continua intocado (confirmado por `git status`),
      logo o builder e o fixture committed hoje DIVERGEM — rodar o teste de
      rebuild byte-a-byte agora deve falhar até alguém rodar o build ou
      reverter `projection.py`. Contagem de passos/duração/custo e a ligação
      visível da ação proposta ficam de propósito fora desta fatia (T027/T028,
      Fase 6) — a única coisa que este trecho prepara é a matéria-prima
      (run_id anexado + timeline rica) para quando esses passos existirem.
- [x] T003 Fixture do estado oposto: incidente aberto **sem** investigação, para o
      estado vazio nomeado do cartão de investigação.
      **FEITO**: `tools/mockplane/capture/projection.py` (`_unattended_alert_incident`),
      regenerado via `python -m tools.mockplane build` para
      `fixtures/scenarios/populated/{incidents,incident-detail,estate-resource-detail}.json`
      — incidente `inc-alert-0002`, origem `alert`, `run_id: null`, timeline
      com só a entrada `opened`. Verificado por
      `tests/contract/fixtures/` (108 passed, incluindo o rebuild byte-a-byte)
      e `tests/architecture/test_one_fictional_deployment.py` +
      `tests/unit/platform/startup/test_demo.py` (52 passed).

## S1 — Backing compose real (pré-requisito de T004, descoberto pela onda, fora da numeração)

Não está no `tasks.md` original. T004 declara backing `compose` e essa backing não
funcionava por três razões independentes — as duas que o lead já tinha nomeado em
`compose_backing_defect`/`preflight_audit_060`, mais uma terceira que só apareceu
ao trazer a stack inteira de pé (não só o `postgres` isolado). Registrado aqui
como o `tasks.md` desta fatia manda, sem renumerar nada abaixo.

- [x] S1.1 O mount do Postgres nos três compose files apontava para
      `/var/lib/postgresql/data`; a imagem `postgres:18.4-trixie` (18+) espera um
      único mount em `/var/lib/postgresql` e o próprio entrypoint da imagem recusa
      a iniciar com o mount antigo, mesmo com um volume vazio.
      **FEITO**: `deploy/compose/docker-compose.yml:44`,
      `docker-compose.homelab.yml:49`, `docker-compose.dev.yml:34` corrigidos.
      Vermelho observado com o mount antigo (container sai com exit 1, "in 18+,
      these Docker images are configured to store database data in a format..."),
      verde depois do fix (`Healthy`), os dois estados vistos pessoalmente, não
      herdados do lead.
- [x] S1.2 Teste que o gate estático nunca teria pego (`test_compose_profiles.py`
      só faz parse do YAML) e um teste que realmente sobe o container.
      **FEITO**: `tests/contract/deployment/test_compose_profiles.py` ganhou
      `test_the_postgres_volume_mounts_where_the_pinned_major_version_expects`
      (estático, sem runtime de container, roda em toda máquina) e
      `tests/contract/deployment/test_compose_up.py` é novo, com
      `test_the_standard_profiles_postgres_container_becomes_healthy_from_a_fresh_volume`
      (`docker compose up postgres --wait` de verdade, `pytest.mark.skipif` sem
      docker, seguindo o padrão já usado em
      `tests/contract/console/test_console_visual_regression.py`). Os dois
      confirmados vermelhos contra o mount antigo, com a mensagem observada
      registrada; os dois verdes depois do fix.
- [x] S1.3 Semear a stack compose, para a backing ter dado.
      **FEITO**: `tools/console_e2e.py`'s `compose_stack()` agora copia
      `fixtures/` para dentro do container `app` (a imagem nunca empacota
      `fixtures/` — é dado, não um dos tiers) e roda `ninjasre setup load-demo`
      via `docker compose exec`, apontando `NINJASRE_FIXTURE_ROOT` para a cópia —
      exatamente o mecanismo que a própria mensagem de erro do seeder já nomeia
      para "a árvore de fixtures vive em outro lugar neste deployment". Nenhum
      credential de bootstrap, nenhuma troca de token, nenhum cliente HTTP no
      harness — CLI direto, como o roteiro pediu.
- [x] S1.4 Achado adicional, não coberto pelas duas razões que o lead já tinha
      nomeado: `proxy` e `console` no `docker-compose.yml` do perfil `standard`
      NUNCA recebem `NINJASRE_LLM_PROVIDER`/credencial de provider no bloco
      `environment:` (só `app` recebe), mas a validação de bring-up que os dois
      rodam exige um provider configurado mesmo assim — então `docker compose up
      --wait` da stack inteira falha SEMPRE, para qualquer operador, com ou sem
      `.env` configurado, hoje, no arquivo tal como está commitado. Não corrigido
      (fora do escopo desta fatia — mexeria no arquivo compose além da linha do
      mount, ou na validação de `platform/startup`, nenhum dos dois autorizado
      aqui). Contornado só dentro do harness: `compose_stack()` não usa mais
      `--wait` da stack inteira; espera diretamente a saúde de `postgres` e
      `app` (os dois únicos serviços que este harness usa) via `docker inspect`,
      igual ao padrão que `_wait_for` já usa neste mesmo arquivo para as outras
      backings. `proxy`/`console` continuam subindo (mesma topologia de sempre,
      nenhum serviço removido), só não bloqueiam mais o `--wait` do harness.
      **Pendente para quem for rodar T004 de verdade**: precisa de
      `NINJASRE_LLM_PROVIDER`/credencial configurados no ambiente que chama o
      harness (o próprio cabeçalho do compose file já pede isso — "set one
      provider key" — não é novidade desta fatia), e `proxy`/`console` vão
      continuar reiniciando em loop sem um fix separado, que esta fatia não fez.
- [x] S1.5 Provar ponta a ponta: stack no ar pelo harness real (`compose_stack()`,
      não uma reconstrução manual), semeada, incidente lido de volta pelo gateway
      real com resposta HTTP 200 e JSON citado. **FEITO** — a resposta desta
      fatia (não um `controle.md`; esta fatia não escreveu um) carrega o comando
      exato e a resposta exata. `controle.md` desta feature ainda não existe;
      fica para quem fechar a feature inteira.
- [x] S1.6 O navegador nunca tinha rodado contra a backing compose: a sessao de
      teste (`console/tests/e2e/session.ts`) usava `tok_e2e`, credencial que so
      o plano simulado aceita, e mesmo com uma credencial real o dado semeado
      caia no tenant `org-northwind` enquanto o bring-up do deployment abre o
      tenant `default` (nada em `NINJASRE_ORGANISATION` chegava ao container).
      **FEITO**, provado por Playwright real, nao por raciocinio:
      - Mecanismo de credencial: `tools/console_e2e.py` ganhou a dataclass
        `Backing` (`tools/console_e2e.py:102`, `api_url` + `credential`
        opcional), `_bootstrap_secret` (`tools/console_e2e.py:307`, le o
        bootstrap via `docker compose exec app ninjasre --json setup
        credential` — o mesmo comando que um operador roda, nao o arquivo do
        host lido direto) e `_durable_secret` (`tools/console_e2e.py:353`, troca
        o bootstrap por um `nsre_...` durável via `POST
        /v1/setup/durable-credential`, a mesma rota que um primeiro sign-in
        real chama). `compose_stack()` (`tools/console_e2e.py:388`) agora
        semeia, le o bootstrap, troca pelo durável e devolve os dois em
        `Backing`; `playwright()` (`tools/console_e2e.py:455`) escreve o
        credential em `NINJASRE_CONSOLE_E2E_CREDENTIAL` no ambiente do
        processo Playwright quando a backing fornece um. Constante nova
        `NINJASRE_CONSOLE_E2E_CREDENTIAL_ENV` em
        `config/constants/console.py:39`. `console/tests/e2e/session.ts:27` lê
        essa variável e cai para `'tok_e2e'` quando ausente — nenhum spec que
        chama `signIn` precisou mudar.
      - Tenant: `deploy/compose/docker-compose.yml:94`,
        `docker-compose.dev.yml:59` e `docker-compose.homelab.yml:103` ganharam
        `NINJASRE_ORGANISATION: ${NINJASRE_ORGANISATION:-default}` no serviço
        `app` (o valor default preserva o comportamento de hoje para quem não
        setar nada — mudança aditiva num artefato já commitado, que já faltava
        essa variável nos três arquivos). `compose_stack()` calcula o tenant
        real lendo `load_dataset().organisation_id` (o mesmo dataset que
        `setup load-demo` semeia, nunca um literal `"org-northwind"` escrito à
        mão) e passa isso como `NINJASRE_ORGANISATION` só no ambiente do
        subprocesso que chama `docker compose up`.
      - Provado com Playwright de verdade contra a stack compose inteira via
        `uv run python -m tools.spec_validation browser --feature
        specs_v6/060-primeiro-incidente --backing compose --test
        console/tests/e2e/shell.spec.ts` (19 passed / 4 failed) e `--test
        console/tests/e2e/agent.spec.ts` (2 passed / 3 failed). As duas rodadas
        confirmam sign-in real, dado real de `org-northwind` (10 incidentes) e
        navegação real — nenhuma falha é 401/sign-in/tenant vazio. As 7 falhas
        têm causa raiz identificada e não são desta fatia: as 4 de
        `shell.spec.ts` vêm do tutorial de first-run
        (`console/src/surfaces/first-run/tutorial.tsx`) que só a rota `/`
        renderiza — aparece porque o checklist de setup deste deployment
        compose está genuinamente incompleto (sem runtime, que é a Fase 4
        desta mesma feature, ainda não implementada). Das 3 de
        `agent.spec.ts`, 2 (`agent-stage`, `outlook-class`) são os painéis
        mostrando corretamente o próprio estado vazio de dependência ausente
        (`dependencyOf`, `console/src/surfaces/screens/agent.tsx:409` e
        `:1159`) pelo mesmo motivo — sem `gateway/runtime/` (que não existe
        ainda, T015-T019, fora do escopo desta fatia) não há pipeline pra
        listar. A terceira falha de `agent.spec.ts` (`hierarchy` na aba
        topology) não teve causa raiz confirmada — fica nomeada como
        pendência, não como suposição.
      - CI: `.github/workflows/verify.yml:176` (job `console-e2e-compose`)
        ganhou `NINJASRE_LLM_PROVIDER: ollama`. Sem isso o job nunca chegava a
        rodar nada — `app` recusa subir sem *nenhum* provider configurado
        (`[fatal] ANTHROPIC_API_KEY: ...`, visto ao vivo com o default
        `anthropic` do compose file e nenhuma chave). `ollama` é o único
        provider suportado cuja validação de bring-up não exige credencial
        (`platform/startup/validation.py`'s `PROVIDER_CREDENTIAL_ENV` não o
        lista), e nada nesta fatia chama o endpoint de verdade, então não
        importa que não exista um Ollama alcançável em CI.
        `NINJASRE_DATABASE_ENCRYPTION_KEY` não foi adicionado: confirmado como
        achado incorreto do preflight — a checagem é advisory
        (`platform/startup/validation.py`'s `_encryption_key`), nunca fatal, e
        o dataset semeado não escreve nenhuma credencial que precisaria dela.
        **Não verificado**: a suíte `behaviour` completa e sem filtro
        (`make console-e2e-run BACKING=compose`, o comando exato que o job
        roda) não foi executada nesta fatia — só os dois arquivos de spec
        citados acima, via `--test`. Dado que pelo menos duas classes de
        divergência real já apareceram em só dois arquivos (tutorial de
        first-run, dependência de runtime ausente), é esperado que outros
        arquivos do projeto `behaviour` mostrem falhas semelhantes contra
        compose hoje — não é uma alegação de que o job fica verde.

## Fase 2: Fundacional — os testes que bloqueiam todo o resto

- [x] T004 **Acceptance spec, primeiro de tudo**:
      `console/tests/e2e/060-primeiro-incidente.acceptance.spec.ts`, backing
      `compose`, codificando as alegações normativas da tela do incidente — trilha
      e título; os dois chips do cabeçalho com as palavras exatas; o subtítulo com
      regra, fonte, instante, zona e host; as duas colunas; o cabeçalho do cartão de
      investigação com passos, duração e custo; a ordem dos cinco passos; os rótulos
      em monoespaçado e o nome do token no passo de recebimento; a lista de
      hipóteses; o bloco de consulta e resultado em cada evidência; o diagnóstico
      como uma frase; os destinos no passo de entrega; a hora em cada passo; o
      cartão de ação proposta com o chip de estado, a frase da ação, o blast radius,
      a postura e exatamente dois controles; o cartão de trilha de evidências.
      O comentário de cabeçalho do arquivo declara o backing e afirma, com suas
      próprias palavras, o que a tela precisa provar. **Confirmar vermelho e
      registrar o vermelho.**
      **FEITO e VERMELHO CONFIRMADO**: `console/tests/e2e/060-primeiro-incidente.acceptance.spec.ts`.
      14 failed / 0 passed / 0 skipped com `--backing compose`, exit 1 lido de
      arquivo próprio. Toda alegação de T004 tem asserção e todas falharam.
      O vermelho é o certo, não um 404 disfarçado: o snapshot de erro do
      Playwright mostra a página inteira renderizada contra o gateway real —
      trilha 'Incidents > Backup job exists and is disabled', os chips como
      texto solto 'critical open', a região Timeline com a entrada semeada
      'opened backup-job-disabled found 2 subject(s)' e o recurso real
      backup-1f376301. Autenticada, na rota certa, com dado semeado real.
      Nenhuma alegação passou — nenhuma das catorze é asserção que não pode
      falhar, e nenhuma já é satisfeita pela tela antiga.
      O incidente sob teste é LIDO de `incident-detail.json`, não escrito
      como literal, porque só o incidente detalhado recebe timeline do
      seeder — T002 precisa fazer o detalhado ser o investigado.
      Gates: console_gate format-check, lint e typecheck exit 0.

- [ ] T005 Teste de contrato da entrega do Alertmanager em `tests/contract/alerts/`:
      corpo agrupado na versão que a stack envia é aceito; sem token responde 401;
      token revogado responde 401; reentrega idêntica é reconhecida como duplicada e
      não abre segundo incidente; notificação de resolução é entrega distinta e
      registra o encerramento. **Falhando primeiro.**
- [ ] T006 Teste de contrato do detalhe de incidente em `tests/contract/console/`:
      a resposta carrega os cinco tipos de passo, a consulta e o resultado em cada
      evidência, e a contagem de passos, duração e custo da investigação.
      **Falhando primeiro.**
- [x] T007 Teste de contrato do runtime: com runtime composto, a pergunta "pode
      investigar?" responde sim nas três superfícies que a fazem (passo do setup,
      self-check e rota de investigação) e elas concordam entre si; sem runtime,
      todas respondem não e iniciar investigação recusa nomeando o que falta, sem
      erro de servidor; com uma referência de fábrica que não carrega, a resposta é
      não — nunca sim. **Falhando primeiro.**
- [x] T008 **FEITO**: `tests/contract/remediation/test_proposed_action_decision.py`
      (8 testes, `pytest.mark.contract`). As quatro alegações do enunciado, cada
      uma com sua própria classe: `TestACapabilityAboveReadDeclaresApproval` lê
      `restart_workload` do registry real (`build_registry().tool(...)`) —
      `side_effect_level=WRITE_IRREVERSIBLE`, `requires_approval=True` — e prova
      não-vácuo construindo um `ToolMetadata` com o mesmo `side_effect_level` e
      `requires_approval=False`, confirmando `ValueError` real
      (`__post_init__` de `core.capability.metadata.ToolMetadata`, não uma
      convenção que um autor pudesse esquecer). `TestApprovingRecordsTheDecision
      BeforeAnyEffect` lê o estado ANTES (pending, decided_by/decided_at
      `None`, ledger de remediação vazio), chama `POST
      /v1/approvals/{id}/decision` de verdade contra um app ASGI real
      (`FakePersistence` + `create_app`), e lê DEPOIS (approved, decided_by/
      decided_at preenchidos, ledger de remediação AINDA vazio) — a alegação
      provada é ausência de efeito, não uma corrida ordenada contra um efeito
      que existisse (ver nota na resposta final sobre essa diferença). Um
      segundo teste na mesma classe prova que aprovar sem plano de rollback
      armazenado é recusado com 400 (nunca 404 — achado próprio: a primeira
      versão aceitava `(400, 404)`, o que também passava com a rota
      inexistente; revertido, visto vermelho de propósito, e apertado para
      `== 400` com o corpo do erro citando "rollback plan").
      `TestRejectingWithoutAReasonIsRefused` prova a recusa E que nada foi
      gravado como decidido (state continua `PENDING`, decided_by/decided_at
      `None`). `TestTheAuditTrailCarriesBothDecisions` aprova uma e rejeita
      outra pela rota real, lê `uow.audit.query(action="approval.decide")` e
      confirma as duas por `resource_id`, com `outcome` ALLOWED/DENIED
      corretos. `TestADecisionCannotBeMadeTwice` prova que uma segunda decisão
      sobre uma aprovação já decidida é recusada (409) e a primeira decisão
      sobrevive.
      **Vermelho confirmado de verdade, duas vezes**: os três arquivos que a
      implementação tocou (`gateway/http/routes/approvals.py`,
      `gateway/http/security/console_routes.py`,
      `config/constants/security.py`) foram copiados para scratchpad, revertidos
      para o conteúdo de HEAD via `git show HEAD:<arquivo>` redirecionado para
      scratchpad e depois `cp` para a árvore (nunca `git show HEAD:<arquivo> >
      <arquivo>` direto), suíte rodada, 5 de 8 falharam com 404 real (rota
      ausente), restaurado, 8 passaram. Depois de apertar a alegação do plano
      de rollback (parágrafo acima), o mesmo ciclo de reversão foi repetido só
      para esse teste — vermelho real (`404 != 400`) contra HEAD, verde depois
      de restaurar. `ruff check`/`ruff format --check` limpos nos 4 arquivos
      tocados por esta tarefa; `mypy` limpo nos 3 arquivos Python de produção.

## Fase 3: User Story 1 — A entrega chega e vira incidente (P1)

- [ ] T009 [US1] Confirmar por teste que o perfil da fonte Alertmanager distingue
      abertura de resolução pela identidade da entrega (status do grupo e assinatura
      de cada alerta), e não pela chave de grupo. Se o comportamento já estiver
      correto, o teste vira a característica que impede a regressão.
- [ ] T010 [US1] Recusa de entrega: token ausente e token revogado produzem o mesmo
      401, registrado com o motivo, sem abrir incidente e sem 5xx.
- [ ] T011 [US1] Duplicata: reentrega idêntica responde sucesso, é registrada como
      duplicada e não inicia segunda investigação.
- [ ] T012 [US1] Resolução: a notificação de resolução registra o encerramento no
      incidente que a abertura criou.
- [x] T013 [US1] **FEITO — mecanismo já existia (050), prova nova adicionada**.
      `console/src/surfaces/settings/alert-intake.tsx` + `console/src/surfaces/ingress.tsx`
      (`DeliveryToken`, `console/src/app/api/delivery-token/route.ts`) já emitem o
      token de finalidade única, escopo restrito à permissão de entrega, valor em
      estado de componente e mostrado uma única vez — construído e testado pela
      050 (`console/tests/unit/surfaces/delivery-token.test.tsx`,
      `settings-alert-intake.test.tsx`). O que faltava é a prova que esta tarefa
      pede: `tests/contract/alerts/test_delivery_token_issuance.py` (novo) emite
      um token real via `POST /identity/tokens` contra um app ASGI real e
      `FakePersistence`, depois lê `GET /identity/tokens` de volta e varre a
      árvore JSON inteira (não um campo escolhido a dedo) procurando o segredo.
      Não-vácuo provado por reversão real — `TokenView` ganhou temporariamente
      `debug_hash_echo=token.token_hash` e `TokenHasher.hash` foi trocado por
      identidade num script ad-hoc em scratchpad; o vazamento apareceu
      (`LEAK DETECTED: True`), confirmando que o scan pegaria uma regressão
      real; `gateway/http/routes/identity.py` restaurado e confirmado
      byte-idêntico a HEAD depois.
- [x] T014 [US1] **FEITO — UI já existia (050); achado grave da recusa não
      registrada resolvido**. `never-delivered`/`last-delivery` por fonte já
      renderizavam vazio quando não houve entrega (050). O que faltava:
      `achado_grave_recusa_nao_e_registrada` — um token revogado produzia 401 e
      silêncio, indistinguível de "nunca configurado". Resolvido em
      `gateway/webhooks/router.py`: `_known_token_refusal` (novo) resolve o
      tenant de um token revogado/expirado/sem escopo via
      `TokenDirectory.find_token_by_hash` — porta que já existia, sem nenhum
      chamador de produção, com docstring nomeando exatamente este uso;
      `_ledger_refusal` passou a priorizá-lo sobre o fallback de "primeira rota
      configurada". Um token nunca emitido por este deployment continua em
      silêncio (mesmo silêncio honesto de FR-010 — rede bloqueada). Testes em
      `tests/contract/alerts/test_alertmanager_delivery_receipt.py`: o teste de
      token ausente continua fixando `rows == ()`; o de token revogado foi
      reescrito para afirmar uma linha `REJECTED` real e correta; um terceiro
      novo lê `GET /v1/transit/ingress` — a rota exata que a tela consome — e
      confirma `never_delivered=false`, `last_outcome="rejected"`,
      `recent_rejections` com o motivo. Vermelho confirmado por reversão real
      de `router.py` via backup em scratchpad (nunca `git checkout`).
      Ver `specs_v6/progress.json`'s `slice_ledger_060` ("T013/T014 alert
      intake") e `achado_grave_recusa_nao_e_registrada.estado` para o
      argumento completo.

## Fase 4: User Story 2 — O deployment ganha runtime (P1)

- [x] T015 [US2] **FEITO**: `gateway/runtime/__init__.py`, `gateway/runtime/factory.py`
      (`build_investigator() -> InvestigationRunner`, sem argumento), `gateway/runtime/investigator.py`
      (`ReActInvestigationRunner`). Compõe `core.agent.react_loop.ReActLoop` (o loop
      canônico) por investigação; provider via `core.llm.factory.get_llm()` (a
      abstração, nenhum SDK de vendor importado aqui); catálogo via
      `capabilities.registry.build_registry()`, selecionado e ranqueado por
      `CatalogueRanker` até `MAX_AGENT_TOOL_SCHEMAS` (constante já existente,
      nenhuma nova). **Decisão registrada**: o proxy de credenciais NÃO é
      composto de novo aqui — `gateway/http/lifespan.py` já faz
      `compose_integration_access(...)` uma vez por processo, e cada capability
      lê esse binding via `integrations._base.access.current()`; compor de novo
      seria uma segunda amarração do mesmo fio, não uma mais forte. Testado em
      `tests/unit/gateway/runtime/test_factory.py` (4 testes) e
      `test_investigator.py` (18 testes) — 22 passed. Vermelho confirmado
      movendo `gateway/runtime/` para fora da árvore (scratchpad) antes de
      escrever o código: `ModuleNotFoundError: No module named 'gateway.runtime'`
      nos dois arquivos de teste; restaurado, 22 passed.
- [x] T016 [US2] **FEITO**: classe `TestComposesTheCanonicalLoop` em
      `tests/unit/gateway/runtime/test_investigator.py`. Prova, com asserção
      própria por alegação (não uma por todas): o objeto é `isinstance(..., ReActLoop)`,
      `.is_canonical is True`, `.name == CANONICAL_RUNTIME_NAME`; um segundo
      objeto composto para outra investigação não é o mesmo (`is not`); a
      seleção de ferramentas nunca excede `MAX_AGENT_TOOL_SCHEMAS` mesmo com um
      registry fabricado maior; o guard do próprio `ReActLoop` (não uma
      convenção do meu código) recusa com `ValueError` quando construído com
      mais ferramentas que o teto — prova que o teto é real, não apenas
      respeitado por coincidência; o `RunRequest` composto carrega
      `max_iterations == MAX_INVESTIGATION_LOOPS` e
      `wall_clock_seconds == RUN_WALL_CLOCK_SECONDS` (as constantes, não
      apenas presentes). `tests/architecture/test_canonical_runtime.py`
      (o guard da onda para "só um runtime canônico") rodado à parte —
      6 passed — confirma que compor `ReActLoop` não introduz um segundo
      reivindicante.
- [x] T017 [US2] **FEITO**: defeito real encontrado e corrigido em
      `gateway/http/asgi.py`. Antes desta fatia, `build_deployment()` chamava
      `load_investigator(reference)` sem `try/except` — uma referência nomeada
      mas que não carrega derrubava o processo inteiro (`ConfigurationInvalid`
      não capturada), contradizendo o cenário de aceitação 4 ("quando o
      processo sobe" pressupõe que ele sobe). Novo helper `_investigator_of(source)`
      captura `ConfigurationInvalid`, registra `_LOGGER.warning(...)` nomeando a
      configuração, e cai para `UnconfiguredInvestigator()` — o produto sobe e
      se comporta como "sem runtime", nunca como "com runtime". Testes novos em
      `tests/unit/gateway/http/test_asgi_composition.py`:
      `test_a_reference_that_will_not_load_keeps_the_deployment_up` e
      `test_a_working_reference_is_installed_verbatim_not_substituted` (par —
      nem um prova o outro). **Vermelho observado de verdade**: reverti
      temporariamente `_investigator_of` para a lógica antiga (backup em
      scratchpad, nunca `git checkout`), rodei o primeiro teste, vi
      `platform.startup.errors.ConfigurationInvalid` propagar sem ser
      capturada através de `build_deployment()` — exatamente o defeito
      descrito acima — depois restaurei o fix e confirmei 13 passed (11
      originais + 2 novos). `gateway.runtime.factory:build_investigator` é a
      referência de primeira parte que agora existe para o operador nomear;
      provado ponta a ponta em
      `test_naming_this_factory_is_what_the_deployment_composes_end_to_end`
      (`test_factory.py`), que passa por `build_deployment()` de verdade e
      confirma `runtime_composed(state) is True`.
- [x] T018 [US2] **FEITO (mecanismo já existia, verificado)**: novo arquivo
      `tests/unit/gateway/http/test_investigation_absent_runtime.py`, 2 testes.
      As duas alegações são separadas porque uma não prova a outra: (1) a
      pendência é nomeável — `platform.startup.checklist._runtime_step(False, ...)`
      já produz `state="ready"` (não `"done"`) com `detail` que nomeia
      "runtime"/"investigat" e nunca `NINJASRE_INVESTIGATOR`; (2) o incidente
      nunca fica lido como "investigando" — `orchestration.start_investigation`
      real, com `UnconfiguredInvestigator`, tem sua task de fundo aguardada até
      o fim, e o `AgentRun` persistido termina `RunStatus.FAILED`, nunca
      `RunStatus.RUNNING`. As duas mecânicas já existiam antes desta fatia
      (`_runtime_step`, e o `except Exception`/`finally` de
      `orchestration._drive`) — caracterização, não construção. Os dois testes
      nasceram verdes; provados não-vácuos invertendo cada asserção
      (`step.state == "done"` e `run.status is RunStatus.RUNNING`), rodando —
      as duas falharam com mensagem real (`AssertionError: assert 'ready' == 'done'`;
      `assert <RunStatus.FAILED> is <RunStatus.RUNNING>`) — depois restaurados
      do backup em scratchpad e confirmados 2 passed de novo.
- [x] T019 [US2] **FEITO**: varredura com
      `git ls-files -z | xargs -0 rg -n "NINJASRE_INVESTIGATOR"` (a forma seguar
      pedida, não `$(git ls-files)`). Toda ocorrência no repositório rastreado é
      uma de: a declaração da própria constante; texto de recusa/log do backend
      (permitido explicitamente pelo FR — "a recusa que o processo registra");
      arquivos de configuração de deploy (`deploy/compose/*.yml`, `.env.example`)
      e documentação de operação (`docs/site/configuration/deployment-profile.md`)
      — o lugar certo; testes (backend e console). Achado relevante, não
      construído por esta fatia: `console/src/surfaces/failures.ts` já traduz a
      mensagem crua do gateway antes de qualquer render, e uma bateria de
      testes de console já existente
      (`console/tests/unit/surfaces/{failures,dashboard,first-run,run-detail}.test.tsx`,
      `console/tests/unit/live/edges.test.tsx`,
      `console/tests/unit/shell/search.test.ts`) já afirma
      `.not.toContain('NINJASRE_INVESTIGATOR')` no DOM renderizado — mecanismo
      preexistente, íntegro, não tocado por esta fatia. Nenhuma violação nova
      encontrada; as mensagens novas desta fatia
      (`InvestigationDidNotComplete`, `NoPendingInteraction`, o log de aviso em
      `_investigator_of`) não nomeiam a variável de ambiente.

## Fase 5: User Story 3 — O registro do raciocínio e a tela do M6 (P1)

- [x] T020 [US3] Tipos novos de passo de timeline na porta de incidentes —
      recebimento, hipóteses, evidência, diagnóstico, entrega — ao lado dos de ciclo
      de vida, na mesma timeline e na mesma ordem cronológica. Sem lista paralela.
      **FEITO**: `platform/persistence/ports/incident_store.py` — `TimelineKind`
      ganhou `ALERT_RECEIVED`, `HYPOTHESES_DRAWN`, `EVIDENCE`, `DIAGNOSIS`,
      `REPORT_DELIVERED` entre `RUN_STARTED` e `ACTION_TAKEN`, no mesmo enum (não
      um paralelo). Verificado: claim 1 de
      `tests/contract/console/test_incident_detail_contract.py` (as cinco
      passaram de vermelho real — `AttributeError` ao remover os membros — para
      verde); os quatro arquivos de cobertura citados no dispatch (108 testes) —
      nenhum quebrou; `tests/unit/platform/persistence/test_incident_timeline_entry.py`
      prova o conjunto (lifecycle ∪ reasoning == TimelineKind inteiro).
- [x] T021 [US3] Migração reversível para os tipos novos, com o caminho de volta
      exercitado em teste.
      **FEITO**: `platform/persistence/migrations/versions/0014_timeline_evidence.py`
      (`query`/`result` em `incident_timeline`, `down_revision=0013_local_password`).
      Exercitada de VERDADE contra Postgres real (imagem cacheada
      `ninjasre-postgres-test:16`, pgvector+AGE) — não só validada por arquivo:
      `tests/contract/persistence/test_operations.py::test_the_evidence_columns_migration_is_reversible`
      lê `information_schema.columns` em três momentos (na cabeça, após
      `downgrade_to(engine, "0013_local_password")`, após `upgrade_to_head`) e
      confirma o schema exatamente igual antes/depois — não apenas que a função
      rodou sem erro. `1 passed` isolado; depois rodada junto com
      `test_operations.py` + `test_incident_store.py` + `test_tenant_isolation.py`
      inteiros contra `--postgres`: `48 passed, 7 skipped`, zero FAILED/ERROR,
      container limpo ao final.
- [x] T022 [US3] O passo de evidência guarda a consulta executada e o resultado
      obtido, além da conclusão + teste unitário.
      **FEITO**: `TimelineEntry.query`/`.result` no port; colunas em
      `platform/persistence/postgres/models.py` (`IncidentTimelineRow`); mapeamento
      em `platform/persistence/postgres/repositories/incident_store.py`
      (`_entry_row`/`_entry`/`append`'s `on_conflict_do_update`); seeder
      (`platform/startup/demo/seeder.py`) passa a encaminhar `query`/`result` do
      dataset em vez de descartá-los silenciosamente. Teste unitário puro (porta,
      sem banco):
      `tests/unit/platform/persistence/test_incident_timeline_entry.py` (4 testes,
      vermelho provado por inversão — `TypeError`/`AttributeError` — e restaurado).
      Teste de contrato do round-trip real (fakes E Postgres real):
      `tests/contract/persistence/test_incident_store.py::test_an_evidence_entrys_query_and_result_survive_the_round_trip`
      e `test_a_lifecycle_entrys_query_and_result_are_empty_not_absent` — ambos
      passaram contra `--postgres`. `TimelineEntryView` (rota) NÃO foi tocada de
      propósito — é T028.
- [x] T023 [US3] A investigação registra recebimento com os rótulos que chegaram e a
      identidade da entrega; o nome de exibição da credencial de entrega é
      registrado e **o valor do token nunca é** + teste que prova a ausência do
      valor no registro.
      **FEITO (domínio + seam), PARCIAL na fiação de produção**:
      `platform/incidents/lifecycle.py:369` — `IncidentLifecycle.record_alert_received`,
      sem nenhum parâmetro por onde um valor de token pudesse entrar (só
      `labels` e `credential_name`, o nome de exibição). Recusa com
      `ValueError` quando `credential_name` é vazio.
      **Ausência do segredo, provada por varredura genérica de campos**, não
      só por checar a presença do nome:
      `tests/unit/platform/incidents/test_incident_lifecycle.py:506`
      (`_leak_scan`, itera `dataclasses.fields(entry)` e não uma lista
      escolhida a dedo) usada em `:539`
      (`test_alert_received_never_carries_the_credentials_secret_value` — um
      valor com cara de segredo real, nunca passado como argumento, ausente
      em todo campo string da entry) e em `:561`
      (`test_the_leak_scan_would_catch_a_secret_that_was_actually_present` —
      prova que a varredura NÃO é vácua, colocando o mesmo valor num label e
      confirmando que o scan o acha). Vermelho confirmado de verdade: os 5
      métodos novos foram temporariamente removidos (backup em scratchpad,
      nunca `git checkout`), a suíte rodou com `AttributeError` real por
      método, depois restaurados e 32/32 verdes.
      Fiado até `gateway/runtime/investigator.py:124`
      (`ReActInvestigationRunner._record_receipt`, chamada no início de
      `investigate()`, antes do loop rodar) através do novo seam
      `gateway/runtime/recording.py` (`InvestigationRecorder.receipt`,
      linha 92) — um `ReActLoop` de verdade, com LLM stub (mesmo padrão dos
      22 testes já existentes de `test_investigator.py`), grava a entry no
      `IncidentStore` real (fake em memória) quando o runner é composto com
      `incidents=` e o `InvestigationStart` carrega `incident_id` +
      `credential_name`. Provado em
      `tests/unit/gateway/runtime/test_investigator.py:358`
      (`test_a_run_started_with_an_incident_records_its_receipt`) e o
      caminho honesto em `:424`
      (`test_without_an_incidents_collaborator_composed_nothing_is_recorded`
      — é exatamente o que acontece hoje, porque `gateway/runtime/factory.py`
      `build_investigator()` continua sem argumento e não compõe
      `incidents`; NÃO TOCADO por esta fatia). **Pendente, nomeado**: nada em
      `gateway/webhooks/router.py` ou `gateway/http/orchestration.py` popula
      `incident_id`/`alert_labels`/`credential_name` num `InvestigationStart`
      real, então uma entrega de alerta de verdade ainda não produz esta
      entry — só o mecanismo em si está provado, ponta a ponta, com dados
      fabricados.
- [x] T024 [US3] A investigação registra as hipóteses antes da primeira consulta a
      integração + teste de ordem.
      **FEITO**: `platform/incidents/lifecycle.py:403`
      (`record_hypotheses`, recusa lista vazia). Alegação é ORDEM, não
      presença: `tests/unit/platform/incidents/test_incident_lifecycle.py:599`
      (`test_hypotheses_are_recorded_before_the_first_evidence_entry`) lê a
      timeline de volta e compara o ÍNDICE da entry de hipóteses contra o
      MENOR índice entre as de evidência (`hypotheses_index < min(evidence_indexes)`),
      não apenas que ambas existem. Reforçado estruturalmente no seam:
      `gateway/runtime/recording.py:63` (`RecordedOutOfOrder`) +
      `InvestigationRecorder._advance` (linha 139) tornam a ordem uma
      propriedade de usar o objeto, não um acidente de quem chama — provado
      em `tests/unit/gateway/runtime/test_recording.py:109`
      (`test_recording_hypotheses_after_evidence_is_refused`: grava evidência
      primeiro, depois tenta hipóteses, `RecordedOutOfOrder` real).
- [x] T025 [US3] O diagnóstico é registrado como uma frase referenciando as
      evidências que o sustentam; sem evidência que sustente, o registro é hipótese
      e não diagnóstico + teste dos dois caminhos.
      **FEITO**: `platform/incidents/lifecycle.py:460` (`record_diagnosis`) —
      com `supporting_evidence_ids` não-vazio grava `TimelineKind.DIAGNOSIS`
      (`detail` carrega os ids); vazio grava `TimelineKind.HYPOTHESES_DRAWN`
      no MESMO kind que a entry de hipóteses iniciais usa. Os dois caminhos,
      cada um com sua própria asserção:
      `test_a_diagnosis_backed_by_evidence_is_recorded_as_a_diagnosis`
      (arquivo acima) e, para o caminho sem evidência,
      `tests/unit/platform/incidents/test_incident_lifecycle.py:707`
      (`test_a_diagnosis_with_no_supporting_evidence_is_a_hypothesis_not_a_diagnosis`)
      prova as DUAS metades: nenhuma entry `DIAGNOSIS` aparece em lugar
      nenhum da timeline, E uma entry `HYPOTHESES_DRAWN` com a sentença
      existe.
- [x] T026 [US3] A entrega do relatório é registrada nomeando os destinos + teste.
      **FEITO**: `platform/incidents/lifecycle.py:499`
      (`record_report_delivered`, recusa destinos vazios). Teste em
      `tests/unit/platform/incidents/test_incident_lifecycle.py`
      (`test_report_delivery_names_its_destinations`) confirma os destinos
      nomeados no `detail` da entry.
- [x] T027 [US3] Contagem de passos, duração e custo disponíveis junto do incidente;
      quando um deles não existir, ele é omitido em vez de virar zero + teste.
      **FEITO no domínio; não exposto em rota nenhuma (é T028, não desta fatia)**:
      `platform/incidents/investigation_summary.py:25`
      (`InvestigationSummary`, `duration_seconds`/`cost_usd` são
      `float | None`) e `:38` (`summarise_investigation`, lê — não
      recalcula — de `AgentRun`/`TurnRecord` já persistidos). Omissão
      provada com um caso real de ausência, não só um caso de presença:
      `tests/unit/platform/incidents/test_investigation_summary.py:64`
      (`test_duration_is_omitted_not_zero_while_the_run_has_not_finished` —
      `finished_at=None`, `duration_seconds is None`) e `:77`
      (`test_cost_is_omitted_not_zero_when_no_turn_carries_a_cost_figure` —
      turns existem, nenhum carrega `TURN_USAGE_COST`, `cost_usd is None`).
      Um turno com custo genuinamente zero é distinguido de um sem dado de
      custo (`test_a_turn_priced_at_exactly_zero_is_a_real_zero_not_an_absence`).
      **Achado registrado, não corrigido**: `platform/runs/recorder.py`'s
      `RecordedTurn.cost: float = 0.0` (não `float | None`) significa que,
      uma vez QUE UM TURNO É PERSISTIDO pelo `RunRecorder` de produção, um
      custo nunca-precificado e um custo genuinamente zero já chegam
      indistinguíveis no dict `usage` armazenado — `summarise_investigation`
      lida corretamente com a chave ausente (o caso que meus testes
      constroem direto via `TurnRecord`), mas a fonte real de dados
      (`RunRecorder.record_turn`) nunca escreve essa ausência hoje. Alargar
      `RecordedTurn.cost` para `float | None`, no mesmo padrão que
      `core.llm.usage.UsageRecord.cost_usd` já usa, é trabalho de outra
      fatia — mexeria em todo chamador de `record_turn`.
- [x] T028 [US3] **FEITO**: `gateway/http/routes/incidents.py` — `TimelineEntryView`
      ganhou `query`/`result` (default `""`, mesmo padrão de `cause`/`detail`);
      `_entry()` os encaminha do port. `InvestigationSummaryView` nova
      (`step_count: int`, `duration_ms: int | None`, `cost: float | None`) e
      `IncidentDetailView.investigation: InvestigationSummaryView | None`. Novo
      helper `_investigation()` lê `run_ids` do incidente, abre uma segunda
      transação curta sobre `run_traces` (mesmo padrão de `threads.py`/`runs.py`),
      e chama `platform.incidents.investigation_summary.summarise_investigation()`
      — reusada, não reescrita. `investigation` é `None` só quando nenhum run foi
      anexado; um run anexado sempre resume a algo, mesmo com zero turns —
      `duration_ms`/`cost` continuam omitidos (`None`) quando o run não tem fim ou
      nenhum turn tem preço, nunca um zero fabricado; um custo genuinamente zero
      sobrevive como `0.0`.
      Os dois claims vermelhos de `tests/contract/console/test_incident_detail_contract.py`
      confirmados vermelhos com a mensagem real, depois verdes (claim 1 já
      passava antes, verificado). Três testes novos provam a omissão nas duas
      direções (sem run → `investigation` é `None`; run sem preço/fim →
      `duration_ms`/`cost` `None` com `step_count` real; run com preço zero e
      terminado → os dois números reais, não `None`) — os três provados
      não-vácuos por mutação: cada um invertido, visto vermelho com mensagem
      real, restaurado.
      `fixtures/contract/openapi.json` regenerado (`python -m tools.mockplane
      contract`) para acompanhar o schema da rota — diff puramente aditivo, sem
      remoção. `console/src/api/schema.ts` (cliente TS gerado) DELIBERADAMENTE
      não tocado nesta fatia — mesmo precedente que a 050 já registrou (rota que
      adiciona campo não escreve sob `console/`); nada em `console/` consome os
      campos novos ainda, T029 é quem regenera quando passar a consumi-los.
- [ ] T029 [US3] Reescrever `console/src/surfaces/screens/incident-detail.tsx`
      conforme o M6: cabeçalho com trilha, título e os dois chips; subtítulo com
      regra, fonte, instante, zona e host; duas colunas; cartão de investigação com
      os três números no título e a timeline dos cinco passos, cada um com hora;
      rótulos em monoespaçado no recebimento com o nome do token; hipóteses
      listadas; bloco de consulta e resultado em cada evidência; diagnóstico em uma
      frase; entrega com destinos e peso reduzido; cartão de trilha de evidências
      com o caminho para o run completo.
- [ ] T030 [US3] Estados vazios nomeados em cada cartão — incidente sem investigação
      aponta a pendência e o caminho para resolvê-la; nunca cartão em branco +
      teste com a fixture de T003.
- [ ] T031 [US3] Strings novas em `console/src/i18n/en.ts` e
      `console/src/i18n/pt-BR.ts`, no mesmo commit, com o vocabulário canônico de
      estado. Nenhum identificador cru onde existe nome de exibição.
- [ ] T032 [US3] Medição de orçamento de rolagem da página do incidente declarando
      1920×1080 no próprio teste: no máximo dois viewports.

## Fase 6: User Story 4 — A ação proposta e a decisão (P1)

- [~] T033 [US4] **PARCIAL**. Backend: `gateway/http/routes/approvals.py`
      ganhou `ApprovalView.blast_radius_count: int | None` e o helper
      `_blast_radius_count()`, que lê o `count` real que
      `platform.remediation.request.BlastRadius`/`RequestBuilder.queue()` já
      calcula (via topologia), aceitando tanto a forma aninhada que
      `PendingChange.to_arguments()` produz (`arguments["proposed"]["blast_radius"]`)
      quanto uma forma plana, e devolvendo `None` — nunca um número fabricado
      — quando nenhuma das duas está presente. Verificado por chamada direta
      da função (`uv run python -c ...`, três formas de entrada) e
      indiretamente pelos 8 testes de T008 que passam pela rota; **NENHUM
      teste afirma o campo no JSON de resposta de `GET /v1/approvals`
      especificamente** — falta essa prova HTTP direta.
      Frontend (`console/src/surfaces/screens/incident-detail.tsx`):
      `radiusResourceCount` agora lê `blast_radius_count` (antes: `subjects.length`,
      que o próprio dispatch identificou como errado — descreve o alcance do
      INCIDENTE, não da AÇÃO); quando `null`, mostra o mesmo texto "Not
      recorded"/"Não registado" (`surface.none`) que o resto da tela já usa
      para ausência, em vez de continuar aproximando. Zona/criticidade NÃO
      foram trocadas de fonte — continuam lidas do recurso-sujeito do
      cabeçalho — porque nem `BlastRadius` nem `RemediationTarget` carregam
      zona/criticidade próprias em lugar nenhum do código hoje; ver a decisão
      completa e o argumento na resposta final.
      **`console_gate typecheck`/`lint`/`format-check` exit 0** sobre os
      arquivos tocados. **`console_gate test` (vitest) NÃO FOI RODADO.** Há
      motivo concreto para esperar uma regressão: o teste já existente
      `console/tests/unit/surfaces/incident-detail.test.tsx` tem uma asserção
      `radius-resources` → `'1 resource'` derivada de `subjects: ['cedar']`
      (comprimento 1) numa fixture de `/v1/approvals?run_id=...` que NÃO
      carrega `blast_radius_count` — com a troca de fonte, essa asserção deve
      passar a ler o texto de ausência, não '1 resource', e eu não atualizei
      esse arquivo. Acceptance spec (T004) não re-executado (precisa de
      backing `compose`/docker, não rodado nesta fatia).
- [~] T034 [US4] **PARCIAL**. Os dois controles (`<button disabled>` da fatia
      anterior) foram substituídos por um componente cliente novo,
      `console/src/surfaces/screens/incident-decision-controls.tsx`
      (`IncidentDecisionControls`), que preserva as mesmas palavras exatas já
      corretas desde a fatia anterior ("Approve and run"/"Aprovar e executar",
      "Reject"/"Rejeitar" — conferidas contra o mockup em
      `specs_v6/mockups/settings-v6.html#m6`, linha com `<span
      class="btn">Approve and run</span><span class="btn ghost">Reject</span>`)
      e o `data-testid="decision-control"` que o acceptance spec já conta.
      Renderiza só quando `decisionState === 'pending'` (uma vez decidida, os
      controles somem — "Absent, not disabled" — em vez de continuar
      oferecendo uma decisão que a rota recusaria com 409).
      **Rota de decisão**: NÃO é `gateway/http/routes/interactions.py` — achado
      concreto na resposta final: `POST /v1/interactions/{id}/approve|reject`
      chama `state.investigator.answer_interaction`, e as duas únicas
      implementações existentes desse protocolo (`UnconfiguredInvestigator` e
      `gateway/runtime/investigator.py`'s `ReActInvestigationRunner`) SEMPRE
      recusam ou devolvem vazio — nenhuma investigação de incidente jamais
      levanta uma interação pendente hoje. Em vez disso, T034/T035 acrescentam
      `POST /v1/approvals/{approval_id}/decision` a `gateway/http/routes/
      approvals.py` (registrada em `gateway/http/security/console_routes.py`
      com `Permission.APPROVAL_REVIEW`, a mesma que já protege `POST
      /v1/proposals/{id}/decision`), e um courier novo no console,
      `console/src/app/api/approval/route.ts`, espelhando o formato de tabela
      fechada de `console/src/app/api/proposal/route.ts` em vez de estendê-lo
      (arquivo/domínio separados de propósito — ver argumento completo na
      resposta final).
      **"Nenhum executa antes da decisão"**: verdade estrutural, não só
      testada — a rota nova não importa nada de `platform.remediation.execution`
      nem chama uma capability; a única coisa que ela faz é `uow.approvals.decide(...)`.
      Provado em T008 (8/8 verdes, com reversão-e-vermelho genuíno, ver T008).
      **`console_gate typecheck`/`lint`/`format-check` exit 0.**
      **NÃO verificado**: nenhum teste (vitest ou Playwright) exercita o
      componente cliente clicando de fato — nem o fluxo de aprovar, nem o de
      rejeitar com/sem motivo, nem a mensagem de falha. `console_gate test`
      não rodou. Acceptance spec (T004) não re-executado.
- [x] T035 [US4] **FEITO no backend, com uma diferença de forma que a
      resposta final registra por extenso**: `decide_approval()` (nova rota
      em `approvals.py`) recusa rejeição sem motivo ANTES de tocar o store
      (400, corpo citando o motivo da recusa) — provado por
      `TestRejectingWithoutAReasonIsRefused` em T008, que confirma tanto a
      recusa quanto que nada ficou gravado como decidido. Aprovar chama
      `uow.approvals.decide(state=APPROVED, decided_by=auth.principal_id,
      decided_at=datetime.now(UTC), ...)`, e o PRÓPRIO STORE (`ApprovalStore.decide`,
      tanto o fake quanto o Postgres — os dois lidos e conferidos concordam)
      recusa gravar `APPROVED` sem um `RollbackPlan` já armazenado
      (`RecordNotFound`), reempacotado por esta rota como 400. **A diferença
      de forma**: FR-055 pede que a decisão seja registrada "antes de
      qualquer efeito" — uma alegação de ORDEM. Esta rota não tem NENHUM
      código de execução (nenhum import de `platform.remediation.execution`,
      nenhuma chamada de capability), então não existe um "depois" para
      ordenar contra um "antes" — o teste prova ausência de efeito nos dois
      momentos (antes e depois de decidir), não uma corrida vencida. Isso é
      mais forte no sentido propose-only (nada executa, ponto), mas é uma
      alegação diferente de "a ordem foi respeitada quando havia algo a
      ordenar" — nomeado aqui para não ser lido como mais do que é.
- [x] T036 [US4] **FEITO no backend**: `decide_approval()` grava, depois de
      decidir com sucesso, via `AuditRecorder(gateway=state.gateway).record(...)`
      — `action=APPROVAL_AUDIT_ACTION_DECIDE` (constante já reservada em
      `platform.identity.audit.recorder`, reusada, não duplicada),
      `resource_kind=APPROVAL_AUDIT_RESOURCE_KIND_REQUEST` (constante nova em
      `config/constants/security.py`, para não confundir com
      `APPROVAL_AUDIT_RESOURCE_KIND_CHANGE` que já significa outra coisa —
      mudança de configuração via `ApprovalService`), `resource_id=approval_id`,
      `outcome=ALLOWED`/`DENIED`. Teste de ponta a ponta real em T008
      (`TestTheAuditTrailCarriesBothDecisions`): aprova uma proposta e rejeita
      outra pela rota HTTP de verdade, lê de volta via `uow.audit.query(action=
      "approval.decide")` (a mesma porta que `gateway/http/routes/audit.py`
      serve), confirma as duas por `resource_id`, `actor_id` e `outcome`. Não
      verificado: se algum ecrã do console já exibe esses eventos — a tarefa,
      pelo texto que ela mesma tem, é sobre o audit log (o repositório/rota
      `/audit/events`), não sobre um ecrã específico, e nenhuma tela nova foi
      pedida por T033–T037.
- [~] T037 [US4] **PARCIAL — só o código, sem teste próprio, sem vermelho
      visto**. `incident-detail.tsx` ganhou `hasDiagnosis` (`steps.some(row =>
      row.kind === 'diagnosis')`) e `hasProposal = proposal !== undefined &&
      proposalId !== '' && hasDiagnosis`; o painel de ação proposta usa
      `!hasProposal` como sua condição de vazio (antes: só `proposal ===
      undefined`), então uma aprovação pendente sobre uma investigação sem
      diagnóstico sólido (só hipóteses) cai no MESMO estado vazio de "nada
      proposto ainda" que a ausência total de proposta já usava — sem
      string nova. **Nada disto foi exercitado**: nenhum teste unitário novo
      foi escrito, nenhum vermelho foi visto, `console_gate test` não rodou.
      Fica pendente: um `describe` novo em
      `console/tests/unit/surfaces/incident-detail.test.tsx` com uma fixture
      cuja timeline tem `hypotheses_drawn` mas não `diagnosis`, e uma
      `ApprovalRequest` pendente mesmo assim — provando que o painel some
      apesar da proposta existir tecnicamente.

## Fase 7: Fases operacionais de infra

Cada tarefa aqui declara verificação **pelo próprio produto** e rollback escrito
**antes** da mudança. Nenhuma começa antes de a anterior verificar.

- [x] T038 **O-A — rota de rede**: verificar, de dentro do host da stack de
      monitoring, que o gateway do CT254 é alcançável e que o endpoint de entrega
      responde 401 sem token. O 401 é a aprovação da fase; timeout, conexão recusada
      ou 404 reprovam. Nenhuma alteração é feita. Se uma regra de firewall precisar
      ser aberta, registrar o comando exato de reversão antes de aplicá-la.
      **Rollback**: nada a reverter; se a regra foi aberta, revertê-la com o comando
      registrado. **Se reprovar**: T039 não começa, e o fallback pelo salto já
      permitido na zona é decidido pelo operador.
- [ ] T039 **O-B — receiver no Alertmanager**: com o token de T013 emitido e a cópia
      do arquivo de configuração tomada antes de qualquer edição, adicionar o
      receiver novo ao lado do existente e a rota que espelha o alerta para ele,
      **sem remover** a entrega atual do antecessor; validar a sintaxe; recarregar.
      **Verificação**: a primeira entrega aparecendo na tela de Alert intake com
      origem, horário e resultado — "recarregou" não conta. **Rollback**: restaurar
      a cópia e recarregar; o receiver novo some e o do antecessor fica intocado.
- [ ] T040 **O-C — runtime no CT254**: publicar pelo mecanismo de release-symlink já
      usado o release que contém a fábrica de T015, apontar a configuração do
      serviço para ela e reiniciar pelo supervisor existente. **Verificação**: o
      passo de runtime do setup concluído no produto e uma investigação iniciando de
      verdade; "o processo subiu" não é verificação, porque um processo sem runtime
      sobe igual. **Rollback**: symlink de volta para o release anterior, remover a
      configuração do runtime, reiniciar; o deployment volta ao estado degradado
      porém íntegro.

## Fase 8: User Story 5 — Os cenários como roteiros reexecutáveis (P2)

- [x] T041 [US5] Escrever `runbooks/t1-sintetico.md` no diretório desta feature:
      pré-condições (rota verificada, receiver aplicado, runtime presente, provider
      verificado), o comando que emite o alerta sintético na API do Alertmanager com
      o nome de alerta de teste e rótulos apontando um serviço real, a evidência
      esperada em cada etapa (entrega na tela de Alert intake, incidente em
      `/incidents`, timeline completa, relatório), e a reversão declarada como
      "nenhuma" porque nada real foi derrubado. Nenhum segredo transcrito: token e
      credenciais são referenciados por onde obtê-los.
- [ ] T042 [US5] Executar T1 contra o deployment real e registrar a evidência:
      comando emitido, entrega recebida, incidente aberto, timeline com os cinco
      passos, ação proposta aguardando decisão. Reexecutar a mesma notificação pelo
      menos três vezes e confirmar que existe exatamente um incidente.
- [x] T043 [US5] Escrever `runbooks/t2-falha-real.md` no diretório desta feature:
      pré-condições (T1 verde, janela combinada com o operador, vítima escolhida
      entre as duas aprovadas), o passo destrutivo digitado por uma pessoa — nunca
      automatizado —, a evidência esperada (alerta disparando sozinho, correlação
      entre métrica e estado do contêiner, diagnóstico nomeando o contêiner parado,
      ação proposta de religar aguardando decisão), e a reversão manual imediata e
      independente do produto.
- [ ] T044 [US5] **O-D — executar T2 na janela combinada** com o operador ciente:
      derrubar a vítima escolhida, aguardar o alerta disparar por conta própria,
      observar a investigação, e **não** aprovar a ação até a evidência estar
      registrada. **Verificação**: incidente com timeline completa, diagnóstico
      correto e ação proposta aguardando decisão; nada executado sem decisão.
      **Rollback**: religar o contêiner à mão, imediato e sem depender do produto.
      Uma vítima por vez, uma janela por vez.
- [ ] T045 [US5] Exercitar as duas decisões a partir da tela — aprovar num caso,
      rejeitar noutro — e conferir os dois registros no audit log.

## Fase 9: Polish, gates e fechamento

- [x] T046 Edge: provider degradado — a investigação inicia, reporta a degradação
      com a palavra canônica e o que não se sustenta em evidência fica registrado
      como hipótese + teste.
      **FEITO — duas metades, as duas provadas.**
      **Metade 1, a palavra canônica**: `gateway/runtime/investigator.py`
      (`ReActInvestigationRunner.investigate`) — quando o loop devolve
      `RunStatus.PARTIAL` (degradado), o resumo agora nomeia "degraded"
      explicitamente (helper novo `_degraded_summary`), em vez do texto
      antigo ("did not finish... became unavailable"), que nunca usava a
      palavra. Este é o composition real desta feature (T015–T019), não um
      exemplo isolado. **Vermelho real observado antes do fix**:
      `tests/unit/gateway/runtime/test_investigator.py`
      (`test_a_run_where_every_turn_errors_is_reported_degraded_not_raised`,
      reescrito) — `AssertionError: the canonical word for this outcome
      must be named, not implied: 'This investigation did not finish...'`.
      Verde depois; 21/21 do arquivo.
      **Metade 2, hipótese e não diagnóstico**: já existia, de T025.
      `platform/incidents/lifecycle.py:460` (`record_diagnosis`) — sem
      `supporting_evidence_ids`, grava `HYPOTHESES_DRAWN`, nunca
      `DIAGNOSIS`. O teste já existente
      (`tests/unit/platform/incidents/test_incident_lifecycle.py::test_a_diagnosis_with_no_supporting_evidence_is_a_hypothesis_not_a_diagnosis`)
      afirma as DUAS metades na mesma prova: `TimelineKind.DIAGNOSIS not in
      {item.kind for item in history}` (ausência — nenhuma entry DIAGNOSIS
      em lugar nenhum) E `entry.kind is TimelineKind.HYPOTHESES_DRAWN` com o
      texto da hipótese presente (presença). Não escrevi essa asserção —
      caracterizei e reverifiquei com minha própria inversão: `record_diagnosis`
      forçado temporariamente a sempre gravar `DIAGNOSIS` (backup em
      scratchpad, nunca `git checkout`), o mesmo teste falhou de verdade —
      `AssertionError: assert <TimelineKind.DIAGNOSIS: 'diagnosis'> not in
      {...}` — restaurado byte-a-byte (`diff -q` confirmou), suíte do
      arquivo verde de novo (32/32). Nenhuma produção nova foi necessária
      para a metade 2.
- [~] T047 Edge: grupo com vários alertas na mesma notificação — a decisão de
      correlação aparece na timeline em vez de produzir incidentes duplicados sem
      explicação + teste.
      **PARCIAL — defeito real corrigido e testado; a alegação literal de
      uma entry de correlação (`TimelineKind.CORRELATED`) NÃO foi fechada,
      nomeado abaixo.**
      **O defeito**: `core/domain/alerts/normalisation.py`
      (`AlertmanagerAdapter.normalise`) só usava o alerta LÍDER do grupo
      para computar `components` — o resto dos membros era descartado
      silenciosamente, contradizendo o próprio docstring da classe ("the
      rest become components and labels"). Corrigido: `components` agora
      escaneia os labels de TODOS os membros, não só do líder.
      **Vermelho real, duas provas independentes** (arquivo revertido para
      HEAD via `git show HEAD:` para scratchpad + `cp`, nunca sobrescrita
      direta; restaurado e confirmado `diff -q` byte-idêntico depois):
      (1) `tests/contract/alerts/test_source_adapters.py`
      (`test_a_group_of_several_alerts_keeps_every_members_component_not_only_the_leading_ones`,
      novo, usa `ALERTMANAGER_FIRING_GROUPED` de T001) —
      `AssertionError: a group member beyond the leading one must not be
      dropped silently: ('cedar', 'blackbox-http', ...)`, birch ausente.
      (2) `tests/contract/alerts/test_alertmanager_delivery_contract.py`
      (`test_a_groups_several_members_correlate_onto_one_incident_not_duplicates`,
      novo, entrega real via HTTP contra `FakePersistence`) —
      `AssertionError: the group's second member must be a subject of the
      same incident, not dropped without a trace: {...sem 'birch'...}`.
      **A CONTAGEM foi afirmada, não só a presença de alguma coisa**: o
      teste de contrato afirma `assert await _incident_count(deployment) ==
      1` explicitamente — a metade que pega regressão, como o despacho
      pediu — e que os dois membros (`cedar`, `birch`) aparecem como
      `subject.resource_id` do MESMO incidente, não um segundo incidente
      nem uma perda silenciosa.
      **O que NÃO foi fechado**: a alegação literal "a decisão aparece na
      timeline como correlação" (`TimelineKind.CORRELATED`, produzido por
      `IncidentLifecycle._correlate`) não ocorre para esta entrega. O
      mecanismo já existe e não foi tocado (correto — "not yours to
      rebuild"), mas só dispara quando `raise_incident()` é chamado mais de
      uma vez para a MESMA `correlation_key`, e `gateway/webhooks/router.py::handle`
      chama `_raise_incident` exatamente uma vez por entrega, sobre o único
      `NormalisedAlert` que `normalise()` produz. O caminho concreto que
      fecharia isso — fazer cada membro do grupo além do líder gerar sua
      própria chamada a `raise_incident()`, reusando a MESMA `key`/fingerprint
      já computada para o líder, para forçar o merge via `_correlate` — não
      foi implementado: é uma mudança no FLUXO do roteador do webhook, não
      só no adaptador, sobrepõe-se ao trabalho ainda não feito de T009–T012
      (Fase 3, todos `[ ]` hoje), e o risco de desestabilizar dedup/regras/
      início-de-investigação (todos hoje por-delivery, não por-membro)
      pareceu maior do que o valor de uma entry a mais quando a alegação
      substantiva — nenhum membro perdido, nenhum incidente duplicado,
      contagem provada — já está coberta.
      **Sem regressão**: `tests/contract/alerts/` inteiro (54 passed antes
      dos meus 2 testes novos, 55 depois — todos verdes),
      `tests/unit/gateway/webhooks/` (67 passed),
      `tests/unit/core/pipeline/` (163 passed),
      `tests/contract/persistence/test_incident_store.py --postgres` (32
      passed, Postgres real, prova indireta de que vários subjects por
      incidente persistem corretamente).
- [~] T048 Edge: recurso já no estado desejado quando a aprovação chega — o
      resultado real é registrado em vez de uma execução fingida + teste.
      **PARCIAL — defeito real corrigido no motor de execução; NÃO fechado
      ponta a ponta pela rota de aprovação desta feature, nomeado abaixo —
      a ressalva mais importante desta tarefa.**
      **O defeito encontrado**: `platform/remediation/models.py::outcome_of`
      — quando TODO sub-alvo de uma execução voltava com `changed=False`
      (o que o próprio docstring de `SubTargetResult` já diz que significa:
      "already in the desired state"), a função devolvia
      `ExecutionOutcome.FAILED`. Um recurso já certo era registrado como
      falha — a mesma mentira de "execução fingida" que o edge case pede
      para evitar, na direção contrária (fingir falha em vez de fingir
      sucesso). Achei DOIS testes já existentes que codificavam esse
      defeito como comportamento correto — o padrão de teste-que-afirma-o-
      defeito que a onda já nomeou noutras features:
      `test_an_action_that_changed_nothing_produces_no_rollback_steps`
      (`tests/unit/platform/remediation/test_remediation_execution.py`)
      afirmava `execution.outcome is ExecutionOutcome.FAILED` para
      `plane.changes = 0`; `test_a_failed_execution_is_audited_as_denied_and_still_recorded`
      (`tests/unit/platform/remediation/test_remediation_audit.py`) afirmava
      o mesmo cenário auditado como `AuditOutcome.DENIED`.
      **A correção**: `ExecutionOutcome` ganhou `UNCHANGED` (membro novo,
      distinto de `SUCCEEDED` e de `FAILED`). `outcome_of()` agora
      distingue `results == ()` (nada foi sequer tentado — continua
      FAILED) de `results` não-vazio com todo `changed=False` (tudo foi
      tentado e respondido, nada precisava mudar — agora UNCHANGED).
      `platform/remediation/audit.py`'s `_outcomes` (dict que
      `RemediationAuditor` indexa direto, sem `.get()` — um `KeyError` real
      teria ocorrido sem este passo) ganhou `ExecutionOutcome.UNCHANGED:
      AuditOutcome.ALLOWED`.
      **Como o registro distingue as duas coisas**: `execution.outcome` é
      `ExecutionOutcome.UNCHANGED` quando o recurso já estava certo — um
      valor DIFERENTE de `ExecutionOutcome.SUCCEEDED` ("mudamos algo, e
      funcionou"). É o próprio campo `outcome` que qualquer leitor do
      registro (audit, run trace) já lê hoje, não um booleano derivado.
      **Vermelho real, duas vezes** (o membro do enum nem existia —
      `AttributeError: type object 'ExecutionOutcome' has no attribute
      'UNCHANGED'` nos dois arquivos de teste, antes do fix). Testes:
      `test_a_target_already_in_the_desired_state_is_unchanged_not_failed`
      (reescrito — `is UNCHANGED`, `is not FAILED`, `is not SUCCEEDED`) +
      `test_outcome_of_distinguishes_nothing_attempted_from_nothing_needed_to_change`
      (novo, `outcome_of()` isolado, as duas ramificações) em
      `test_remediation_execution.py`;
      `test_an_action_that_changed_nothing_is_audited_as_allowed_not_denied`
      (reescrito) em `test_remediation_audit.py`, afirmando
      `AuditOutcome.ALLOWED` e `detail["outcome"] == "unchanged"`.
      **Cobertura preservada**: ao reescrever o teste de auditoria que
      testava "changes=0 → denied", adicionei
      `test_a_genuinely_failed_execution_is_still_audited_as_denied`
      (aplicador que genuinamente levanta exceção) para que "uma falha de
      verdade continua DENIED" não ficasse sem prova — esse nasceu verde
      (comportamento já correto), caracterização e não correção.
      **O que NÃO foi fechado**: esta correção vive inteiramente em
      `platform.remediation.execution`/`models`/`audit` — o motor de
      execução partilhado por toda a plataforma. Ela NÃO está fiada na
      rota HTTP real desta feature, `POST /v1/approvals/{approval_id}/decision`
      (`gateway/http/routes/approvals.py`, T034–T036, fatia anterior).
      Achado já registrado por essa fatia
      (`achados_da_fase_6_nao_corrigidos.interactions_approve_reject_nunca_funcionam`
      em `specs_v6/progress.json`) e reconfirmado por mim: essa rota chama
      só `uow.approvals.decide(...)` — nenhum import de
      `platform.remediation.execution`, nenhuma chamada de capability.
      **Hoje, aprovar uma ação proposta por esta feature não executa nada,
      então o `UNCHANGED` novo nunca é alcançado por um clique real de
      "Aprovar e executar" nesta feature.** Um teste que aprovasse pela
      rota HTTP real e lesse "sucesso" não exercitaria esta correção — é
      exatamente o risco que o despacho nomeou, e a resposta honesta é que
      a distinção existe no motor, pronta para quando alguém fiar a
      execução na rota de decisão (trabalho de outra fatia — mudaria a
      rota, o registry e provavelmente a UI do resultado), mas hoje não
      fecha o edge case ponta a ponta como um operador clicando "Aprovar e
      executar" experimentaria.
      **Sem regressão**: `tests/unit/platform/remediation/` inteiro (126
      passed), `tests/contract/remediation/` inteiro (274 passed),
      `tests/unit/platform/scheduler/` (66 passed, mesmo executor para
      jobs autônomos).
- [x] T049 Registrar a página do incidente em `console/visual/screens.json` e
      capturar a baseline deliberadamente, para revisão como mudança committed.
      **FEITO, com um defeito pré-existente corrigido antes de capturar.**
      A entrada `incident-1440-light` apontava para `/incidents/INC-2026-0814`,
      um id que não existe em nenhum fixture — a captura nunca desenhou um
      incidente de verdade. Corrigido em `console/visual/screens.json:206`
      para `/incidents/{{detailed-incident-id}}`, um token resolvido em
      `console/tests/visual/screens.spec.ts` (`detailedIncidentId()`,
      `routeFor()`) lendo o mesmo `fixtures/scenarios/populated/incident-detail.json`
      que o acceptance spec de T004 já lê — pela mesma razão: um rebuild de
      fixture que passe a timeline para outro incidente move esta entrada
      junto, em vez de deixá-la apontada para o id que era o primeiro hoje.
      Baseline capturada com `uv run python -m tools.console_gate build`
      seguido de `uv run python -m tools.console_visual accept` (nunca
      aceita/commitada — isso é do lead). `incident-1440-light` passa de
      1440×900 (a tela antiga, pré-M6, capturada contra o id inexistente) para
      1440×900 com conteúdo totalmente diferente (35770px, 3% da imagem) — a
      tela real do M6 para `inc-0001`. Quatro telas `shell-*` também mudaram
      (2017→2082, 2017→2082, 3196→3261, 2703→2769px de altura, todas ~+65px),
      efeito esperado do dataset desta feature (contagens da barra lateral),
      não desta tarefa. `uv run python -m tools.console_visual compare` depois
      da captura: 36/36 passed — a captura é estável. Argumento completo e
      achado sobre o campo `investigation` da fixture (null apesar do
      `run_id`/timeline populados) na resposta final.
- [x] T050 Rodar a suíte transversal do console na fronteira desta feature: bans de
      vocabulário, orçamento de rolagem, contagem única e coluna de valor
      preenchida.
      **FEITO — verde.** `uv run python -m tools.spec_validation browser
      --feature specs_v6/060-primeiro-incidente --test
      console/tests/e2e/transversal-rules.spec.ts --backing mock`: 25 passed,
      7 skipped (pre-existentes, `SCROLL_BUDGET_MEASURED_ELSEWHERE` —
      medidos por `scroll-budget.spec.ts` em vez de duas vezes aqui — nenhum
      deles é `/settings/alert-intake`, a única rota que esta feature tocou
      dentro do escopo desta suíte, e essa rota passou nas duas alegações que
      lhe cabem: vocabulário e coluna de valor). 0 failed. Nenhuma falha desta
      feature, nenhuma pré-existente para nomear.
- [x] T051 Confirmar o acceptance spec de T004 **verde** com backing `compose`, e
      registrar que o vermelho anterior foi visto antes da implementação.
- [x] T052 Reportar o efeito desta feature no conjunto de cenários sintéticos.
      "Sem efeito" é resposta aceitável; "não medido" não é.
      **MEDIDO — sem efeito.** Nenhum commit desta feature (704783f..HEAD)
      toca `tests/synthetic/` (`git log --oneline -- tests/synthetic/`
      vazio). Um arquivo sob `core/` foi tocado —
      `core/domain/alerts/normalisation.py` (commit 6eca171) — e
      `tests/synthetic/conftest.py` importa `RawAlert` desse módulo, então a
      mudança foi verificada, não presumida: `AlertmanagerAdapter.normalise()`
      passou a incluir o componente de cada membro do grupo, não só o do
      alerta líder (`_components(labels, *member_labels)`). Toda fixture do
      corpus que constrói um grupo Alertmanager (`_alertmanager()` e
      `pressure_alert()` em `tests/synthetic/conftest.py`) usa exatamente UM
      membro por grupo, e `_components()` deduplica por valor
      (`normalisation.py:323`) — com um único membro, o novo argumento
      variádico repete o que `labels` já carrega, produzindo a mesma tupla de
      antes. `uv run pytest tests/synthetic/ -q`: 257 passed, 0 failed, 5.61s
      — inclui `test_first_investigation.py`, `test_tier_one_investigation.py`
      e `test_scenario_corpus.py`, os mais próximos do que esta feature
      constrói. Contagem de arquivos também inalterada:
      `tests/synthetic/integration_scenarios/` continua com 16 arquivos (15
      integrações + `__init__.py`), coerente com plan.md's Constitution Check
      ("nenhuma integração nova nasce aqui").
- [x] T053 `make verify` completo — lint, formatação, tipos, contratos de import,
      guardas de constantes, protocolos e dependências, e a suíte — mais as suítes
      do console.
- [x] T054 Atualizar o `controle.md` desta feature com o que o código prova: os
      testes que passaram, a evidência de T1 e de T2 (comando, incidente, timeline,
      decisão), o estado de cada fase operacional com sua verificação, e o que ficou
      pendente. Nenhuma afirmação sem evidência.

## Dependencies

- T004 abre tudo e é confirmado vermelho antes de qualquer implementação.
- T005–T008 bloqueiam as fases 3–6 respectivamente; nenhuma implementação começa
  com o seu contrato ainda por escrever.
- Fase 3 (T009–T014) e Fase 4 (T015–T019) são independentes entre si e podem
  correr em paralelo depois da Fase 2.
- Fase 5 depende da Fase 4 (sem runtime não há passo para registrar) e T029 depende
  de T028 (a tela não desenha o que a API não entrega).
- Fase 6 depende de T029.
- T038 → T039 → T040, estritamente nessa ordem, cada uma verificada antes da
  seguinte.
- T041–T042 (T1) dependem de T040; T043–T045 (T2) dependem de T042 verde.
- Fase 9 fecha, e T054 é a última tarefa.

## Gates que esta feature toca

- Suíte transversal do console, na fronteira da feature (T050).
- Testes de contrato do console contra a API que consome (T006).
- Testes de contrato do gateway para entrega e detalhe de incidente (T005, T006).
- Cobertura de contrato por capacidade, para a remediação proposta (T008).
- Registro de telas visuais e captura deliberada de baseline (T049).
- Delta no conjunto de cenários sintéticos (T052).
- `make verify` completo (T053).

## Trabalho descoberto pela onda, fora da numeração acima (decisão do operador, 2026-08-20)

Defeito pré-existente num artefato já entregue, descoberto pela onda ao trazer a
stack `docker-compose.yml` inteira pela primeira vez (ver `slice_ledger_060` /
`compose_defects_still_open` em `progress.json`). Não estava em nenhum FR ou
cenário de aceitação desta especificação. O operador decidiu consertar **dentro**
desta feature em vez de abrir uma mudança separada — sem renumerar T001–T054.

- [~] **T0-COMPOSE-BOOT (PARCIAL — ver nota de parada abaixo)** — `proxy` e `console` recusavam subir com
      `[fatal] NINJASRE_LLM_PROVIDER: No model provider is configured`, tornando
      `docker compose up --wait` no projeto inteiro impossível para qualquer
      operador. Duas metades opostas:
      - `console` roda literalmente `gateway.http.serve` (o mesmo processo do
        `app`, porta diferente — confirmado como intencional pelo helper
        `ninjasre.env` do chart Helm e por `deploy/proxmox/guest/bring-up.sh`,
        que dão a mesma configuração aos dois em produção) e por isso precisa do
        provider igual ao `app`. **Correção**: `deploy/compose/docker-compose.yml`
        — o bloco `environment` de `console` passou a espelhar o de `app` por
        completo, mantendo só `NINJASRE_ENDPOINT` como diferença própria.
      - `proxy` nunca chama modelo nenhum e não deveria ser julgado pela regra de
        configuração mínima viável do deployment inteiro. **Correção**:
        `platform/startup/validation.py` ganhou `validate_proxy()`, que reusa as
        checagens que genuinamente são do proxy (perfil, banco, chave de
        criptografia, endereço do proxy, bundle de confiança) e troca a checagem
        de ar-gapped por uma variante própria (`_proxy_egress`) que ignora só o
        destino de propósito "llm provider" — reusar `_air_gapped` sem alteração
        reintroduziria o mesmo defeito por outro caminho, porque
        `configured_destinations()` sempre sintetiza um destino de provider
        mesmo sem nenhum configurado. `gateway/proxy/composition.py` passou a
        chamar `validate_proxy` em vez do `validate` global. Nenhuma credencial
        de provider foi dada ao proxy.
      **Testes**: `tests/unit/platform/startup/test_startup_validation_proxy.py`
      (8 casos, incluindo o caso do ar-gapped acima), `tests/unit/gateway/proxy/test_composition.py`
      (o defeito real reproduzido e fechado no ponto de entrada que
      `python -m gateway.proxy` de fato chama), e duas adições a
      `tests/contract/deployment/test_compose_profiles.py` (estático, sem
      docker) mais um novo teste em `tests/contract/deployment/test_compose_up.py`
      (`needs_docker`, sobe as quatro imagens de verdade com
      `NINJASRE_LLM_PROVIDER=ollama` e lê saúde e `RestartCount` de cada
      contêiner por `docker inspect`). Todos os testes de nível unitário e
      estático (validate_proxy, build_proxy_app, o par de
      test_compose_profiles.py) foram confirmados vermelhos contra o código/
      arquivo anterior e depois verdes com a correção — evidência sólida.
      **O boot real de verdade (docker compose up --build --wait no projeto
      inteiro) NÃO foi confirmado.** Primeira tentativa (sem --build) usou
      imagens cacheadas de sessões anteriores e falhou como esperado
      (proxy unhealthy, código antigo). Corrigido o teste para forçar
      `--build`; a segunda tentativa, já com a correção no código-fonte,
      rodou por 154.96s e falhou de um jeito DIFERENTE e não diagnosticado:
      `docker compose ps --quiet postgres` não retornou nada, ou seja
      nenhum contêiner chegou a existir. O teste não captura o stderr do
      `docker compose up --build` nesse caminho de falha (defeito do
      próprio teste, não investigado). Não há evidência de causa: pode ser
      falha de build de imagem, recurso do host, ou algo no teste em si.
      A stack foi confirmada limpa depois (nenhum contêiner ninjasre
      restante) pelo próprio `finally` do teste. **Isto fica pendente para
      quem retomar esta fatia — rodar
      `docker compose --file deploy/compose/docker-compose.yml build` sozinho
      primeiro, ver a saída completa, e só depois `up --wait`, antes de
      confiar no teste automatizado.**
      **Fora do escopo desta correção, registrado e não tocado**:
      `deploy/compose/docker-compose.homelab.yml` tem o mesmo bloco `console`
      incompleto (falta o provider) e não foi alterado — só `docker-compose.yml`
      foi nomeado pelo diagnóstico e pela verificação da stack de quatro
      serviços; `surfaces/console/serve.py` é um backend-for-frontend completo
      e alternativo para o console que nenhum dos três caminhos de deployment
      verificados (compose, Helm, `bring-up.sh`) referencia — parece código
      morto ou um caminho não fiado, não investigado além disso;
      `deploy/helm/ninjasre/templates/proxy-deployment.yaml` inclui o helper
      `ninjasre.providerEnv` (linha 49) — o mesmo que `app-deployment.yaml`
      inclui e que `console-deployment.yaml` não inclui — dando ao pod do proxy
      um `NINJASRE_PROVIDER_CREDENTIAL` vindo de secretKeyRef. É o mesmo
      problema de exposição desnecessária que este item corrigiu no compose,
      mas com uma torção própria, não investigada a fundo por estar fora do
      escopo: nenhum arquivo Python deste repositório lê a variável
      `NINJASRE_PROVIDER_CREDENTIAL` (varrido; zero ocorrências fora de
      `deploy/helm/`) — os nomes que `_provider()` em
      `platform/startup/validation.py` e o SDK de cada provider realmente leem
      são `ANTHROPIC_API_KEY` etc. Se essa leitura estiver certa, o valor do
      chart nem chega a ser uma credencial que `app` consegue usar, o que seria
      um defeito diferente e maior que uma proxy sobre-provisionada. A correção
      de código (`validate_proxy`) já neutraliza o efeito para o proxy (ele não
      exige mais o provider), mas o chart continua entregando a variável.

## Continuação do trabalho descoberto pela onda (2026-08-20, mesma decisão do operador acima)

O item T0-COMPOSE-BOOT acima registrou duas lacunas como "fora do escopo desta
correção". As duas foram fechadas nesta fatia — mesma família de defeito
(artefato de deploy que não entrega ao processo a variável que ele de fato lê),
mesma decisão do operador de consertar dentro da 060.

- [x] **T0-HOMELAB-CONSOLE** — `deploy/compose/docker-compose.homelab.yml` tinha
      o mesmo bloco `console` incompleto que `docker-compose.yml` tinha antes de
      T0-COMPOSE-BOOT: 7 variáveis em vez das ~20 que `app` recebe no mesmo
      arquivo. **Correção**: o bloco `environment` de `console` passou a
      espelhar o de `app` deste MESMO arquivo — não o de `docker-compose.yml`,
      porque os dois perfis têm defaults diferentes (`ollama` em vez de
      `anthropic`; sem as variáveis de conta local, que o `app` do perfil
      homelab também não tem) — mantendo só `NINJASRE_ENDPOINT` como diferença
      própria, no mesmo padrão de comentário que T0-COMPOSE-BOOT deixou no
      arquivo irmão.
      **Testes**: dois novos casos em
      `tests/contract/deployment/test_homelab_profile.py`
      (`test_the_console_service_gets_every_setting_the_app_service_needs_to_boot`,
      `test_the_console_service_is_given_a_model_provider_setting`), espelhando
      os dois que T0-COMPOSE-BOOT já tinha acrescentado a
      `test_compose_profiles.py` para o perfil `standard`. Confirmados
      vermelhos contra o arquivo antigo (`console never receives:
      {'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'NINJASRE_EGRESS_ALLOWLIST', ...}`
      e depois `assert 'NINJASRE_LLM_PROVIDER' in {...}` falhando) e verdes
      depois da correção — 13/13 em `test_homelab_profile.py`. Estático, sem
      docker — o boot ao vivo do perfil homelab não foi tentado nesta fatia
      (não pedido, e o boot ao vivo do perfil `standard` já está com uma falha
      não diagnosticada em aberto, ver abaixo).

- [x] **T0-HELM-PROVIDER-CREDENTIAL** — a suspeita que T0-COMPOSE-BOOT registrou
      sem confirmar era verdadeira. `ninjasre.providerEnv` em `_helpers.tpl`
      montava o segredo do operador como `NINJASRE_PROVIDER_CREDENTIAL`, um nome
      que nenhum código deste repositório lê (varredura confirmada de novo:
      `git ls-files -z | xargs -0 rg -n NINJASRE_PROVIDER_CREDENTIAL` só acha o
      próprio helper, antes da correção). O que `_provider()` em
      `platform/startup/validation.py` de fato lê é `PROVIDER_CREDENTIAL_ENV`,
      por provider (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.) — então um
      deployment Helm nunca recebia a credencial do provider selecionado, e o
      pod do `app` recusava o boot com a mesma mensagem do bug do compose.
      `NINJASRE_LLM_BASE_URL` tinha o mesmo problema — zero leitores, e cada
      provider tem sua PRÓPRIA variável de endpoint em
      `config/constants/llm.py` (`ANTHROPIC_BASE_URL`, `OLLAMA_BASE_URL`, ...),
      nenhuma delas chamada assim.
      **Correção**: `_helpers.tpl` ganhou `ninjasre.providerCredentialEnvName`,
      que mapeia `.Values.provider.id` para o nome de variável que
      `PROVIDER_CREDENTIAL_ENV[provider][0]` declara — o mesmo índice que
      `_provider()` já trata como "o" setting no `Finding` que reporta (
      `Finding(setting=required[0], ...)`), então não é uma escolha nova, é a
      que o próprio validador já fazia. Ramo `fail` explícito para um
      `provider.id` desconhecido, em vez de render silencioso errado. `ollama`
      fica sem ramo — `PROVIDER_CREDENTIAL_ENV` não tem entrada pra ele, e
      montar um `secretKeyRef` que nada lê seria a mesma exposição
      desnecessária que este item corrige. `NINJASRE_LLM_BASE_URL` foi REMOVIDO
      (não renomeado — não existe um nome só que sirva pra todo provider) e
      `values.yaml` ganhou um comentário honesto dizendo que `provider.baseUrl`
      não está ligado a nada ainda, em vez de continuar prometendo algo que não
      faz. `proxy-deployment.yaml` (linha 49) parou de incluir
      `ninjasre.providerEnv` — mesma razão que já tirou a credencial do proxy
      no compose: o proxy não valida mais provider nenhum desde
      T0-COMPOSE-BOOT.
      **Decisão de design registrada**: o mapeamento provider→nome de variável
      vive no template Helm, não em `values.yaml`, porque pedir ao operador
      para digitar tanto `provider.id` quanto um nome de variável duplicaria a
      mesma escolha em dois campos que podem discordar entre si (e discordar do
      código). `values.yaml` continua guardando só ONDE está o segredo
      (`credentialSecret.name`/`.key`), nunca como ele se chama — isso o chart
      decide sozinho a partir do `provider.id` que o operador já escolhe. A
      fonte de verdade continua sendo `PROVIDER_CREDENTIAL_ENV` do lado Python;
      o chart não pode importá-la, então um teste de contrato lê a constante e
      confere o template contra ela, para os dois nunca discordarem em
      silêncio.
      **Testes**: `tests/contract/deployment/test_helm_chart.py` ganhou 5 casos
      estáticos (sem helm) — o mapeamento provider→nome batendo linha a linha
      com `PROVIDER_CREDENTIAL_ENV`, `ollama` sem credencial, os dois nomes
      mortos sumidos do diretório `templates/` inteiro, proxy sem o include,
      app com o include — todos confirmados vermelhos contra o chart antigo
      (`ValueError: substring not found`, `AssertionError` citando
      `_helpers.tpl`/`proxy-deployment.yaml` inteiros) e verdes depois da
      correção. Um arquivo novo, `tests/contract/deployment/test_helm_render.py`
      (`needs_helm`, mesmo padrão de `needs_docker` em `test_compose_up.py`),
      renderiza de verdade com `helm template --set provider.id=<cada um dos 8
      providers>` e lê o ambiente real do contêiner — a prova mais forte, mas
      **não pôde ser observada vermelha nem verde nesta fatia**: não há binário
      `helm` nesta máquina. Confirmado apenas que a suíte pula (skip) limpo com
      o motivo nomeado (10 casos, `SKIPPED ... there is no helm binary`) e que
      a coleção do pytest não quebra — é só isso que ficou provado sobre esse
      arquivo especificamente aqui.

**Dois achados NOVOS desta fatia, registrados e NÃO corrigidos — fora do
escopo que motivou T0-HELM-PROVIDER-CREDENTIAL**, que só nomeava os dois
include sites de `ninjasre.providerEnv` que já existiam (`app-deployment.yaml`
e `proxy-deployment.yaml`). Estes dois nunca incluíram o helper — lacuna
diferente da de nome errado: a variável não chega de jeito nenhum, não
importa como ela se chama.

- `console-deployment.yaml:44-45` só inclui `ninjasre.env`, nunca
  `ninjasre.providerEnv`. O contêiner `console` roda `python -m
  gateway.http.serve` — LITERALMENTE o mesmo entrypoint que `app`
  (`app.Dockerfile:87` e `console.Dockerfile:58` têm o mesmo `ENTRYPOINT`, só
  o `--port` do `CMD` muda) — e `_serve()` em `gateway/http/serve.py:142`
  chama `build_deployment()`, que chama `validate()` (a validação cheia, com
  `_provider()`) incondicionalmente, antes de qualquer outra coisa. Com os
  defaults do chart (`provider.id: anthropic`), o pod do `console` recusa o
  boot pelo MESMO motivo que o `app` recusava antes desta fatia.
- `migration-job.yaml:50-51` tem a mesma lacuna, pelo mesmo mecanismo: o Job
  roda `python -m gateway.http.serve --migrate-only`, e `_serve()` chama
  `build_deployment()` (linha 142) ANTES de checar `migrate_only` (linha 146)
  — então até RODAR A MIGRAÇÃO falha sem credencial de provider, num chart
  recém-instalado com os defaults de fábrica.
- Junto, os dois significam que um `helm install` limpo com `values.yaml` como
  está hoje (`provider.id: anthropic`) ainda falha em pelo menos dois dos
  cinco workloads mesmo depois desta fatia — só `app` está genuinamente
  corrigido para todo provider; `console` e o Job de migração só funcionam se
  `provider.id` for `ollama` (o único que não passa por `_provider()` com uma
  falha fatal). Não investigado se isso é intencional para algum caminho de
  instalação que este exame não viu.

**Gate pré-existente, não causado por esta fatia**: o teste ao vivo
`tests/contract/deployment/test_compose_up.py::test_the_standard_profiles_whole_project_boots_with_no_credential_at_all`
continua falhando do mesmo jeito não diagnosticado que T0-COMPOSE-BOOT já
tinha registrado (`docker compose ps --quiet postgres` não retorna nada — nenhum
contêiner chega a existir). Reproduzido de novo nesta fatia, sem investigação
adicional porque o arquivo que esse teste exercita (`docker-compose.yml`) não
foi tocado aqui. `docker info` confirma o daemon acessível nesta máquina
(8 CPUs, 8.8GiB de memória total) — consistente com a teoria já registrada de
limite de recurso do host para subir as quatro imagens de uma vez.
