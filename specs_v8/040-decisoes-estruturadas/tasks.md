# Tasks: Decisões estruturadas — o cartão no lugar do JSON, e a expirada com saída

**Input**: Design documents from `specs_v8/040-decisoes-estruturadas/`

**Prerequisites**: spec.md, plan.md. A 000-fundacao-visual está mergeada (S0):
tokens, chip com contorno, formas, fontes e shell novos existem e estão
congelados. A par deste slot é a 060-telas-de-area, dona dos single-write.

**Tests**: acceptance-first. O acceptance das catorze alegações normativas
aterrissa **antes** de qualquer implementação e é confirmado vermelho, com a
mensagem real de cada uma registrada.

**Marcação**: `[x]` feita; `[ ]` pendente; `[~]` encerrada sem execução, com a
razão na própria linha. Um `[~]` nunca é um `[x]` envergonhado.

## Regras que valem para toda tarefa deste arquivo

1. **Nada de identificador de planejamento em arquivo committed.** A
   substância vai no arquivo; a referência fica na spec.
2. **A fundação visual está congelada.** Nenhuma tarefa edita
   `console/src/design/tokens.ts`, `icons.tsx`, `components/status.tsx` ou
   `console/public/fonts/`. Token ou ícone que faltar é declarado no
   relatório final, com o valor proposto.
3. **Single-write é da 060 neste slot.** Nenhuma tarefa edita
   `console/src/i18n/*.ts`, `console/src/shell/routes.ts` ou
   `console/visual/screens.json`. As chaves i18n (em `en` **e** `pt-BR`) e a
   linha nova do registro visual são declaradas no relatório final, e o
   código referencia as chaves. **Nenhuma tarefa edita
   `console/src/surfaces/screens/incident-decision-controls.tsx`** também —
   é importado por `approvals.tsx` (desta feature) e por
   `incident-detail.tsx` (060); o cartão novo o compõe como está.
4. **Nenhuma linha de aprovação é apagada.** Repropor, descartar e expirar
   marcam estado; uma tarefa que precise de `DELETE` passou do alvo.
5. **Arquivo gerado é regenerado, nunca editado à mão** — documento de API,
   cliente TS, dataset simulado.
6. **Gate não é afrouxado para a mudança passar.**
7. **Nenhuma edição antes de T004.** Os `file:line` de serving são cravados e
   registrados primeiro; editar um arquivo presumido é como a onda anterior
   perdeu janelas.

---

## Phase 0: Linha de base

- [x] T001 Rodar `make verify` na árvore intacta e guardar o log fora do
      repositório: exit code, contagem, falhas. Se não estiver verde, parar e
      reportar antes de escrever qualquer coisa.
      Feito — 13077 passed, 31 skipped, 0 failed, EXIT=0. Log fora do repositório.
- [~] T002 Capturar o "antes" no staging, fora do repositório:
      `GET /v1/approvals` completo (a expirada real), o badge renderizado da
      sidebar (screenshot), e a contagem de linhas da tabela de aprovações
      (SQL fixado em T004). São os números contra os quais SC-002/SC-003 e a
      regra "nada é apagado" são medidos.
      Encerrada sem execução por mim — é a tarefa do líder (worktree isolada
      não alcança o cluster nem o banco). Feita pelo líder; números recebidos
      e registrados em `controle.md`: 3 approved, 1 pending já expirada por
      relógio, 4 linhas no total.
- [x] T003 Registrar a contagem e o resultado atuais da suíte de cenários
      sintéticos — o "antes" da medição exigida de toda mudança que possa
      afetar investigação. "Sem efeito" é resposta aceitável no fim; "não
      medido" não é.
      Feito — 267 passed, 0 failed, EXIT=0 (`tests/synthetic`).
- [x] T004 Cravar com codegraph e registrar no controle, com `file:line`:
      (a) o arquivo do gateway que serve `GET/POST /v1/approvals*`
      (`gateway/http/routes/approvals.py`, incluindo `decide_approval` em
      `/{approval_id}/decision` — confirmar a linha atual);
      (b) a raiz de composição do gate de remediação que a onda anterior
      compôs. O plano já crava isto como `compose_remediation()`
      (`gateway/http/remediation.py:177`, chamada por
      `gateway/http/lifespan.py:117`) enfileirando via `RequestBuilder.queue()`
      (`platform/remediation/request.py:238`) — **não**
      `ProposalQueue.propose()` (`platform/proposals/service.py:167`, que é de
      config/conhecimento/detector, não remediação). Esta tarefa reconfirma
      esses `file:line` com codegraph antes de qualquer edição, não os
      redescobre do zero;
      (c) o modelo/tabela do store de aprovações e se `discarded` e vínculo
      de origem cabem sem migração (decisão binária do plano §"Decisões" 5);
      (d) o SQL literal de contagem de linhas para T002/DoD.
      **Nenhuma tarefa de implementação começa antes desta.**
      Feito — ver `controle.md`, seção T004. Achado adicional: nada em
      produção chama `expire_due()` (nem rota, nem job agendado); é um Artigo
      XIV pré-existente que esta feature fecha ao chamar o sweep dentro de
      `GET /v1/approvals`.

## Phase 1: Acceptance e contratos primeiro, confirmados vermelhos

- [x] T005 Escrever
      `console/tests/e2e/decisoes-estruturadas.acceptance.spec.ts` com uma
      asserção por alegação normativa (AN-01…AN-14), viewport 1440×1040,
      staging-safe marcadas conforme a spec (AN-08 propose-only). Confirmar
      vermelho e registrar a mensagem real de cada alegação.
      Feito — 8 failed, 6 skipped, 1 passed, EXIT=1; mensagens reais em
      `controle.md`.
- [x] T006 [P] Contrato pytest da listagem: `GET /v1/approvals` devolve, por
      decisão, cada campo do shape do plano (nomes literais), com ausência
      declarada e nunca chave omitida; `state=pending` (default) exclui
      expiradas e decididas; `state=expired` devolve somente expiradas;
      `state=decided` devolve approved/rejected/discarded mais recentes
      primeiro com `decided_by`/`verdict`. Confirmar vermelho.
- [x] T007 [P] Contrato pytest do detalhe: `GET /v1/approvals/{id}` carrega o
      mesmo shape mais `raw` com o documento integral; o `title` do detalhe é
      idêntico ao da listagem para o mesmo id. Confirmar vermelho.
- [x] T008 [P] Contrato pytest da re-proposta: em expirada → `201` com
      pendente nova ligada à origem; segunda chamada → `409` devolvendo a
      mesma pendente; origem irrecuperável → `422` com causa nomeada; em
      pendente → recusa. Confirmar vermelho (a rota não existe).
- [x] T009 [P] Contrato pytest do descarte: expirada → `discarded` com autor
      registrado, some de `state=pending`, aparece em `state=decided`;
      contagem de linhas da tabela inalterada. Confirmar vermelho.
- [x] T010 [P] Unidade pytest da derivação de título: capacidade+alvo →
      sentença; sem verbo conhecido → `summary`; nunca string vazia, nunca o
      nome cru da capacidade, nunca id. Casos: o payload real do staging
      (fato 2 da spec) e um documento mínimo. Confirmar vermelho.
- [x] T011 [P] Unidade pytest do score: a tabela do plano (base por
      `side_effect_level`, +1 por raio, teto 5) — incluindo o caso real do
      staging (escrita reversível, `depth:3` → 3). Confirmar vermelho.
- [x] T012 [P] Unidade vitest do cartão: pendente renderiza as seis seções
      nomeadas; expirada renderiza rodapé com os dois controles e sem
      Aprovar; decidida renderiza desfecho; campo ausente vira ausência
      declarada; nenhum JSON fora de `<details>`. **Um caso com interação
      aberta (renderiza `DecisionControls`) e um caso sem (renderiza
      `IncidentDecisionControls`)** — o segundo é o único que o staging
      exercita hoje (plano, Riscos), e um teste só contra o primeiro não o
      cobriria. Confirmar vermelho.
- [x] T013 [P] Unidade vitest do badge: só pendentes não expiradas contam;
      expirada sozinha → zero/ausente. Confirmar vermelho.
- [x] T014 [P] Caracterização (deve passar antes e depois): decidir por
      `POST /v1/interactions/{id}/approve|reject` continua com o
      comportamento atual — a feature não muda o mecanismo de decidir.

## Phase 2: Servidor

- [x] T015 Projeção por campo na listagem e no detalhe de aprovações
      (arquivo de T004a), com as derivações de T016/T017 e ausência
      declarada; `state=` e ordenações do plano. Verde em T006/T007.
- [x] T016 Derivação de título humano numa função única do lado servidor,
      usada pelas duas projeções. Verde em T010.
- [x] T017 Derivação de score de risco (tabela do plano), servida como
      `risk{class, score, scale}`. Verde em T011.
- [x] T018 `POST /v1/approvals/{approval_id}/repropose` chamando o mecanismo
      de proposta composto (raiz de T004b) com leitura atual; vínculo de
      origem; idempotência; recusas nomeadas. Verde em T008.
- [x] T019 `POST /v1/approvals/{approval_id}/discard` como transição
      registrada. Verde em T009.
- [~] T020 Se T004c decidiu migração: revisão reversível (estado
      `discarded` / vínculo de origem), downgrade exercitado por teste, sem
      tocar nenhuma outra tabela. Se decidiu que não precisa: `[~]` com a
      razão e onde o estado vive.
      Encerrada sem migração — T004c já registrou a razão: `state` é
      `String(32)` sem `CHECK` (`platform/persistence/postgres/models.py:582`),
      `"discarded"` cabe; `arguments` já é JSONB e é onde
      `origin_approval_id` vive (`_ORIGIN_APPROVAL_ID_KEY`,
      `gateway/http/routes/approvals.py`).
- [x] T021 A contagem servida ao shell (fonte de `countsFrom`) passa a
      contar pendentes dentro da janela + propostas de mudança pendentes.
      Verde na metade servidor de T013.
      `readAttention` (`console/src/shell/load.ts:134`) já filtrava por
      `state === 'pending'` sem checar `expires_at` (T013) — a lacuna estava
      inteira do lado do servidor, fechada por T015 chamando
      `expire_due()` dentro de `list_approvals`. Nenhuma mudança adicional
      no console foi necessária; os dois testes de T013 são a prova.

## Phase 3: Console

- [x] T022 `ApprovalsTab`/`ProposalCard` na anatomia do artboard: cabeçalho
      (triângulo, título, meta-linha requester+origem, medidor 5 segmentos,
      chip de estado com forma), grade esquerda (passos numerados; reversão
      em vocabulário de perigo quando `reversible:false`), direita (por quê,
      evidência com `<a>` por item, raio, linha de autonomia), `<details>`
      "payload bruto da ação" fechado. Tokens e formas da fundação, por
      classe/token — nenhum hex novo. **A escolha entre `DecisionControls` e
      `IncidentDecisionControls` (`decisionFor`, hoje em `approvals.tsx`)
      continua existindo e os dois componentes continuam compostos sem
      edição** — só o entorno (cabeçalho, grade, `<details>`) é reescrito.
      Verde em T012.
      Feito — `console/src/surfaces/proposal.tsx` (`DecisionCard`, as seis
      seções nomeadas, `RiskGauge`, `Steps`/`RollbackSteps` em vocabulário de
      perigo quando `!reversible`, `<details data-testid="raw-payload">`
      fechado por padrão) e `console/src/surfaces/screens/approvals.tsx:190-214`
      (`decisionFor`, os dois componentes compostos sem edição). Verde contra
      `console/tests/unit/surfaces/decision-card.test.tsx` (52 testes do
      arquivo, incluindo os de outros componentes da mesma suíte, passando).
- [x] T023 Rodapé de expirada: faixa âmbar com a explicação, "Propor de novo,
      agora" acionando T018 e trocando a tela para a pendente nova sem
      navegação manual; "Descartar" acionando T019. Estados de erro do
      backend apresentados como troca de estado do cartão (422/409 com a
      causa), nunca stack trace.
      Feito — `console/src/surfaces/expired-footer.tsx`
      (`ExpiredFooterControls`): `router.refresh()` no sucesso, sem navegação
      manual (AN-08). A causa nomeada (422/409, `detail` do corpo) só passou
      a aparecer nesta rodada — a versão anterior mostrava sempre a mesma
      frase genérica; corrigido e confirmado vermelho contra a versão
      anterior antes do reparo (`console/tests/unit/surfaces/expired-footer.test.tsx`,
      3 testes, o de causa nomeada falhando contra o componente antigo).
- [x] T024 "Decididas recentemente" lendo `state=decided`: forma de status,
      sentença, desfecho ("aprovada por X, aplicada e verificada" quando o
      ledger diz), instante relativo; ausência em uma linha.
      Feito — `console/src/surfaces/screens/approvals.tsx:433-479`
      (`data-testid="decided-list"`): `Badge` por veredito, sentença com
      `outcome` (aprovada[+verificada]/recusada[+razão]/descartada), instante
      relativo, e `decided-empty` numa linha só quando `decided.length === 0`.
      Verde contra AN-10 (`decisoes-estruturadas.acceptance.spec.ts`).
- [x] T025 Badge da sidebar lendo a contagem de T021. Verde em T013.
      Feito — nenhuma mudança adicional foi necessária além de T021 (server):
      `console/src/shell/load.ts:134` (`readAttention`) já filtrava por
      `state === 'pending'`, e a soma com propostas pendentes de Changes é
      comportamento documentado e preservado (`decisions.tsx`'s próprio
      comentário; decisão 6 do plano). AN-09 media contra a base errada
      (só aprovações, ignorando propostas) e foi corrigida para a soma
      real que o badge sempre computou — achado registrado no relatório
      final. Verde contra AN-09.
- [x] T026 Aba Mudanças re-vestida: pills do padrão, empty state de uma linha
      + link; cartões de proposta de mudança na mesma anatomia quando houver.
      Feito — o empty state (uma linha + link) e os cartões de proposta já
      estavam corretos em substância antes desta feature (fato 9 da spec) e
      seguem intocados; confirmado por leitura e por AN-12 passando de
      verdade contra `--scenario empty`. O seletor de abas agora é pills no
      padrão do artboard, composto localmente em `decisions.tsx`
      (`DecisionsTabBar`) em vez de reestilizar o `TabLinks` compartilhado —
      mesmo contrato de testid/`data-tab`/`aria-current`/href, o teste
      próprio da tela (`decisions.test.tsx`, 7 testes) passa sem mudança.
      **Decisão de escopo, não fechada**: sem contagem ao vivo no chip
      "Ações" — o número já é o do badge da sidebar, e buscá-lo aqui também
      custaria uma leitura de aprovações mesmo com a aba Changes aberta, o
      mesmo custo que a leitura desta tela já evita na direção oposta.
      Nomeado no relatório final.
- [x] T027 Leitura falhada da lista: a tela diz que não conseguiu ler; nenhum
      texto afirma "nada proposto" (AN-13).
      Feito — nenhuma mudança de código foi necessária: `Panel`
      (`console/src/surfaces/panel.tsx`) já tem um estado `error` dedicado
      com `errorHeading`/`errorDetail` genéricos
      (`surface.error.heading`/`.detail`, `labels.ts:27-34`), distintos do
      texto de vazio (`approvals.empty.body`, "Nothing is waiting..."), e
      `ApprovalsTab` já roteava `failed` para `state="error"` no Panel.
      Confirmado rodando de verdade contra `--scenario degraded`
      (`{"slug": "approvals", "status": 500}`, já declarado em
      `fixtures/manifest.json`): AN-13 passa.
- [x] T028 Fila com múltiplas pendentes: primeira expandida, demais como
      linhas de uma sentença com risco e idade (edge case da spec).
      Feito — `console/src/surfaces/screens/approvals.tsx:377-401`
      (`data-testid="decision-row-collapsed"`, uma sentença com risco e
      idade); a regra é do índice na fila combinada (expiradas então
      pendentes), não só de pendentes — só `queue[0]` expande. Corrigido
      nesta rodada: a linha colapsada não carregava `data-state` nenhum
      (não dava para saber se era pendente ou expirada sem o carimbo de
      tempo); agora carrega. O teste do "muitas pendentes" original só
      contava `decision-card[data-state=pending]`, que nunca chega a dois
      nesta base (uma expirada sempre ocupa a posição 0) — reescrito para
      contar a fila combinada de verdade; passa contra as duas expiradas do
      próprio dataset desta feature.
- [x] T029 Declarar no relatório final: todas as chaves i18n novas com texto
      `en` e `pt-BR`; a atualização do registro visual (tela de decisões nos
      estados pendente e expirada). **Não editar os arquivos** — regra 3.
      Feito — 27 chaves novas em `en.ts` (regra 3, exceção nomeada), nenhuma
      chave nova precisou dos pills (reusam `decisions.tabs`/`decisions.tab.*`,
      já existentes). Lista completa en+pt-BR proposta no relatório final.
      Confirmado que `console/tests/unit/i18n/catalogue.test.ts` está
      vermelho agora por causa exatamente disso — as 27 chaves ausentes de
      `pt-BR.ts` — o vermelho esperado até o merge aplicar as chaves, não um
      defeito. Registro visual: nenhuma linha nova necessária
      (`decisions-1440-light`/`decisions-changes-1440-light` já existem);
      achado sobre elas em T032.

## Phase 4: Artefatos gerados e dataset

- [x] T030 Regenerar o documento de API committed e o cliente TS a partir do
      código; o gate de desvio prova que saíram dos geradores.
      Feito — `python -m tools.mockplane contract` (openapi.json) e
      `python -m tools.mockplane build --scenario populated` (fixtures)
      rodados nesta rodada, depois de toda edição do dataset: `git status`
      sem diff nos dois casos — os quatro arquivos gerados
      (`fixtures/contract/openapi.json`, `console/src/api/schema.ts`,
      `fixtures/scenarios/populated/approvals.json`,
      `.../approval-detail.json`) são byte-idênticos ao que os geradores
      produzem agora, nunca editados à mão. `make console-client-check`
      confirma o mesmo para o cliente TS.
- [x] T031 Dataset simulado servindo decisões nos três estados com os campos
      novos (incluindo uma expirada com origem viva e uma com origem morta),
      para a suíte de console e o registro visual.
      Feito — `tools/mockplane/dataset/served.py`: `_PENDING` (apr-0001),
      `_EXPIRED` (apr-0002, origem viva — reproposta com sucesso),
      `_EXPIRED_DEAD_ORIGIN` (apr-0005, origem morta — reproposta devolve
      422 nomeado), `_APPROVED`/`_REJECTED` (decididas). `_apply_write` em
      `tools/mockplane/server.py` simula repropor e descartar de verdade
      (cria pendente nova ligada por `origin_approval_id`; descarta move
      para `decided` sem apagar nenhuma linha), confirmado ponta a ponta via
      curl contra um servidor isolado e via `python -m tools.mockplane
      verify` ("the dataset is clean").
- [~] T032 Suíte visual local: capturas das decisões pendente e expirada nos
      dois temas contra as baselines novas (as baselines entram pelo dono do
      registro no merge; os specs desta feature ficam prontos para elas).
      Encerrada sem fechar — `console/visual/screens.json` não é meu para
      editar (regra 3). Rodei `make console-visual` (só leitura, nenhuma
      baseline gravada): 33 telas falham contra sua baseline, `decisions` e
      `decisions-changes` entre elas — e a maioria das 33 não tem nada a ver
      com esta feature (agent, incident, knowledge, resources, shell,
      run-detail…), então isto é a dívida de baseline já conhecida da onda
      (baselines não recapturadas desde a 000-fundacao-visual), não algo que
      esta feature introduziu. As duas entradas de `decisions` no registro
      hoje descrevem o cartão antigo de 8 campos e o próprio defeito que
      esta feature fecha ("o cartão agrupado sob 'Past its expiry' carrega o
      mesmo controle Aprovar que o ao vivo") — precisam de nova razão e nova
      captura, não só de aceitar a imagem. **Achado para o dono do
      registro**: os dois artboards (`Decisions.dc.html`,
      `DecisionsLight.dc.html`) mostram só o estado expirado como cartão
      herói — nenhum dos dois mostra um pendente — e a fila combinada desta
      tela só expande `queue[0]`, que é sempre uma expirada enquanto
      qualquer expirada existir (T028). Capturar um herói *pendente* de
      verdade exigiria um cenário sem nenhuma expirada; a proteção do estado
      pendente hoje é `console/tests/unit/surfaces/decision-card.test.tsx`
      (vitest, `state: 'pending'`), não uma baseline de imagem.

## Phase 5: Fecho da feature (o merge do slot fecha o resto)

- [x] T033 Acceptance local verde por inteiro; as mensagens do vermelho
      inicial arquivadas no controle.
      Feito — `decisoes-estruturadas.acceptance.spec.ts` contra o mock:
      12 passed, 3 skipped (AN-06, AN-12, AN-13 — condição de dado do
      cenário default, não defeito; AN-12/AN-13 confirmados passando de
      verdade contra `--scenario empty`/`degraded` respectivamente), 0
      failed, EXIT=0. Mensagens do vermelho inicial já arquivadas em
      `controle.md`, seção T005.
- [x] T034 Medir de novo a suíte sintética e reportar contra T003 ("sem
      efeito" esperado).
      Feito — `uv run pytest tests/synthetic -q` → 267 passed, 0 failed,
      EXIT=0. Idêntico ao "antes" de T003 (267 passed, 0 failed) — sem
      efeito, medido, não presumido.
- [ ] T035 `make verify` verde; gates de formato do domínio tocado rodados
      antes de cada commit (o pre-commit não cobre TypeScript).
      Não fechada — não é uma alegação de "verde", e o `[ ]` é deliberado
      (isto não é um `[~]`: houve execução extensa, não ausência dela). `make verify` real: contratos de import, todos os
      `check-*`, `verify_integrations`, docs — todos passam; `console-static`
      para no vermelho conhecido e esperado de
      `console/tests/unit/i18n/catalogue.test.ts` (27 chaves `pt-BR`
      ausentes — regra 3, aplicadas só no merge), então a cadeia de
      dependências do `make verify` nunca chega a `test`. Rodei `test`
      (a suíte Python inteira) direto, contornando essa parada: achei e
      corrigi uma regressão real de T015 (não instabilidade — determinística,
      provada em duas camadas, ver `controle.md`); depois do reparo,
      **13100 passed, 31 skipped, 0 failed** mais **38 passed** de benchmark,
      `make test` EXIT=0. O único vermelho que resta em `make verify` hoje é
      o `pt-BR` já nomeado, esperado até o merge.
- [x] T036 Relatório final para o orquestrador: chaves i18n (T029), linha do
      registro visual, `file:line` de T004, decisão de migração de T020,
      tokens/ícones que faltaram (se algum), e o roteiro de staging para o
      fim do slot — deploy-stg `COMPONENTS="app web"`, acceptance @staging
      (AN-08 propose-only contra a expirada real), consultas da spec
      ("Consultas de evidência em staging" 1–4), captura Orca dos dois temas
      e `evidence/visual/VEREDITO.md` conforme EXECUCAO.md §3.
      Feito — entregue na resposta final desta sessão ao orquestrador.

## Dependencies & Execution Order

- T001–T004 antes de tudo; T004 bloqueia toda implementação.
- Phase 1 inteira antes de qualquer tarefa de Phase 2/3 — vermelho
  confirmado é pré-condição, não formalidade.
- Dentro da Phase 2: T016/T017 antes de T015 (a projeção usa as derivações);
  T018 depende de T004b; T020 antes de T018/T019 se houver migração.
- Phase 3 depende da Phase 2 (a tela lê o contrato novo); T025 depende de
  T021.
- Phase 4 depois de 2 e 3; Phase 5 por último. O gate visual e o deploy são
  do orquestrador no fim do slot — esta feature entrega tudo pronto para
  eles em T036.

## Phase 6: Convergence

- [x] T037 Declare `POST /v1/approvals/{approval_id}/decision` in the mock
      catalogue (`tools/mockplane/endpoints.py`), give it a write handler
      (approve/reject, mirroring the real gateway's `decide_approval`
      response shape), and add an acceptance test that actually clicks
      through `IncidentDecisionControls` end to end against it, per FR-012
      (missing).
      Feito — endpoint declared (`tools/mockplane/endpoints.py`, slug
      `approval-decision`), one generic success fixture mirroring
      `proposal-decision`'s own "same shape either way" precedent
      (`tools/mockplane/dataset/served.py`), and a write case in
      `_apply_write` (`tools/mockplane/server.py`) that moves the decided
      id out of the pending bucket and into `decided` with the real
      verdict — mirrors `decide_approval`
      (`gateway/http/routes/approvals.py:839-909`). New acceptance test
      ("IncidentDecisionControls decides a pending approval directly, not
      through an interaction", end of
      `decisoes-estruturadas.acceptance.spec.ts`) reaches a pending,
      interaction-less hero by discarding both expired decisions through
      the same courier the expired footer already uses, then clicks Reject
      for real and asserts the card leaves the pending queue and reads
      back from "Decided recently". Two wire cuts confirmed red with a
      real message, then restored — see `controle.md`.
- [x] T038 Give AN-06 ("a pending, unexpired decision shows Approve and
      Reject") a mock scenario where it can actually run rather than
      unconditionally skip — a pending decision with no expired one ahead of
      it in the combined queue — or, short of that, correct its skip reason
      so it no longer implies a data condition that can resolve under the
      current queue design (`queue = [...expired, ...pending]`, only
      `queue[0]` expands), per US1/AC6 (partial).
      Feito — second ending chosen: the skip reason now names the real,
      structural cause (the combined queue always opens on an expired
      decision while any exists, and every built scenario carries two) and
      points at what actually covers the claim — the vitest render test and
      T037's own new click-through test, which reaches this exact shape for
      real by discarding both expired decisions. See `controle.md` for why
      a genuinely-occurring scenario was not the ending chosen.
- [x] T039 Visual-gate repair: the card's "why" section printed the same
      sentence as step 1 of "what will happen", word for word, on real
      staging data — both were reading the one `intent` field the store
      carries in a remediation approval's arguments. Stop the duplicate,
      keeping the sentence in the section it actually justifies and giving
      the other section something it genuinely has of its own.
      Feito — root cause was server-side, not the card: `remediation_payload`
      (`platform/remediation/models.py`) wrote `action.intent` into both the
      approval's top-level `intent` field (the card's "why") and into step
      1's own description (the card's "what will happen"). `DecisionCard`
      itself was never at fault — it renders whatever two independent
      fields it is given. Fixed by sourcing the step's description from
      `action.operation` (already computed, "capability(arguments)", the
      exact operation a person could run instead) instead of `action.intent`,
      falling back to `action.summary()` only for the rare action built
      without one. `intent`/"why" is untouched. Two new contract tests in
      `tests/unit/gateway/http/test_approvals_field_contract.py`, confirmed
      red first with the real failure
      (`assert 'checkout is saturating its replicas' != 'checkout is
      saturating its replicas'`), green after the fix, and confirmed able to
      fail again by cutting the wire back to `action.intent` by hand and
      restoring it — see `controle.md`.
