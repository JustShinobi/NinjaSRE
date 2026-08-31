# Controle — Decisões estruturadas

Estado abaixo verificado contra o código atual desta worktree
(`wt/v8-040-decisoes-estruturadas`, cortada de `feat/000-fundacao-visual` em
`a54174c0`, com o reparo de composição `c6764a94` já presente). Cada linha
carrega o `file:line` que a sustenta. CodeGraph estava com `auto-sync`
desligado durante toda a implementação (lock de arquivo preso por outro
processo); todo achado abaixo foi confirmado por leitura direta do arquivo no
disco, nunca só pela resposta do CodeGraph.

## T004 — `file:line` cravados antes de qualquer edição

**(a) Rota do gateway.** `gateway/http/routes/approvals.py`. `GET /v1/approvals`
→ `list_approvals:204`; `GET /v1/approvals/{approval_id}` → `get_approval:228`;
`POST /v1/approvals/{approval_id}/rollback` → `record_rollback:243`;
`POST /v1/approvals/{approval_id}/decision` → `decide_approval:279`. O próprio
docstring do módulo (`approvals.py:1-30`) já documenta que `decide_approval`
chama `ApprovalStore.decide` diretamente, nunca `ApprovalService`/`ProposalQueue`.

**(b) Raiz de composição do gate de remediação.** Reconfirmado, não
redescoberto — o plano já a crava e a leitura do código concorda byte a byte:

- `compose_remediation()` — `gateway/http/remediation.py:177`.
- Chamada por `gateway/http/lifespan.py:117` (`await compose_remediation(state,
  org_id=organisation_id(), proxy_url=...)`), logo depois de
  `compose_control_plane` e antes de `compose_memory` — comentário do próprio
  módulo em `lifespan.py:98-111` explica a ordem.
- `compose_remediation()` monta `RequestBuilder` (`platform/remediation/request.py:217-224`)
  com `approvals=ApprovalService(...)` (`gateway/http/remediation.py:209-215`) e
  atribui o resultado a `state.remediation` (`gateway/http/remediation.py:258`)
  — um `RemediationDesk` (`gateway/http/remediation.py:94-143`) com o campo
  público `requests: RequestBuilder`.
- **O mecanismo real de fila é `RequestBuilder.queue()`**
  (`platform/remediation/request.py:238-291`), que chama
  `ApprovalService.queue(change_type=ChangeType.REMEDIATION, ...)`
  (`platform/approvals/service.py:197-269`) — este sim é o `ApprovalService`
  que persiste via `uow.approvals.create_request`/`store_rollback_plan`
  (`platform/approvals/service.py:250-252`).
- **A re-proposta desta feature chama `state.remediation.requests.queue(action)`
  diretamente** — não `RemediationGate.decide()`/`.execute_approved()`. A
  chamada por `RemediationGate` (`platform/remediation/gating.py:409-419`,
  `_through_approval`) existe para o caminho *autônomo/de decisão dentro de
  uma run*, que pode aguardar (`self.waiter.wait(...)`) ou até **executar
  autonomamente** (`_autonomous`/`_by_policy`, `gating.py:360-407`) conforme a
  política do deployment — um handler HTTP de repropor não pode bloquear
  esperando uma decisão, e sobretudo não pode arriscar execução autônoma numa
  ação que deveria ser só uma nova proposta pendente (propose-only, FR
  correspondente). Chamar `RequestBuilder.queue()` sem passar por
  `RemediationGate` é o que garante propose-only por construção, e
  `tests/unit/gateway/http/test_approval_execution.py:113-119`
  (`_queued`/`desk.requests.queue(_action())`) já usa exatamente este padrão
  para fixtures de teste — não é um atalho inventado por esta feature.
- **Confirmado, não**: `platform/proposals/service.py:167` (`propose`, dentro
  da classe cujo `decided` está em `service.py:224`) — essa fila serve
  `AgentProposal` (config/conhecimento/detector), e é uma classe TOTALMENTE
  diferente de `platform.knowledge.proposals.ProposalQueue`
  (`platform/knowledge/proposals.py:265`, propostas de conhecimento). Nenhuma
  das duas participa da remediação; ambas continuam fora do escopo de escrita
  desta feature, e a aba Changes (US5) lê `platform/proposals/service.py`'s
  `decided()` só para leitura (histórico), como o plano já previa.

**(c) Modelo/tabela do store de aprovações — decisão binária: NÃO precisa de
migração.**

- `platform/persistence/ports/approval_store.py:25-36` — `ApprovalState`
  (`StrEnum`): hoje `PENDING`, `APPROVED`, `REJECTED`, `EXPIRED`. Sem
  `DISCARDED`.
- `platform/persistence/postgres/models.py:563-585` — `class Approval(Base)`,
  `__tablename__ = "approvals"`. A coluna `state: Mapped[str] =
  mapped_column(String(32), nullable=False)` — **string livre até 32
  caracteres, não é um enum nativo do Postgres nem tem `CHECK`**. `"discarded"`
  (9 caracteres) cabe sem alteração de schema. `arguments: Mapped[dict[str,
  Any]] = _json()` (`_json()` = `JSONB`, `models.py:86-88`) — campo JSON já
  existente onde o vínculo de origem da re-proposta (`origin_approval_id`) cabe
  como chave nova, sem migração.
- **Decisão**: adicionar `ApprovalState.DISCARDED = "discarded"` ao enum
  (`is_decided` já vale `True` automaticamente, por já ser `!= PENDING`);
  adicionar `discard()` ao protocolo `ApprovalStore`
  (`platform/persistence/ports/approval_store.py`), à implementação Postgres
  (`platform/persistence/postgres/repositories/approval_store.py`) e ao fake
  (`platform/persistence/fakes/approval_store.py:23-189`, único fake
  encontrado); o vínculo de origem da re-proposta viaja dentro de
  `arguments["origin_approval_id"]`, escrito via `amend_request()` (método já
  existente no protocolo, `approval_store.py:120-137`) logo depois de
  `RequestBuilder.queue()` devolver o novo `change_id`. **Nenhuma migração
  Alembic nesta feature** — não há parent revision a registrar.

**(d) SQL literal de contagem de linhas (T002/DoD).**

```sql
select state, count(*) from approvals group by state;
select count(*) from approvals;
```

Contra a coluna `state` (`String(32)`) e a tabela `approvals`
(`platform/persistence/postgres/models.py:566`), sem filtro de `org_id` — o
que o líder já mediu no T002 é exatamente essa consulta, rodada dentro do pod
`app` contra `NINJASRE_DATABASE_URL`. Nenhuma linha some em nenhum passo desta
feature: repropor cria uma linha nova; descartar e expirar fazem
`UPDATE ... SET state = ...`, nunca `DELETE`. A prova de "nada é apagado" é a
mesma consulta rodada antes e depois, com a contagem total inalterada e a
contagem por estado se movendo apenas de `pending` para `expired`/`discarded`/
`approved`/`rejected` — nunca diminuindo o total.

## T002 — o "antes" do staging (tarefa do líder, não desta feature)

Medido pelo líder dentro do cluster (mensagem recebida durante a implementação
desta feature, endereçada explicitamente a mim para leitura antes de eu
fechar T004):

```
state      count
approved   3
pending    1
```

4 linhas no total; nenhuma `expired`. A linha `pending` (`0c778cff-b06`,
`requested_at` 2026-08-27 03:37:05, `expires_at` 2026-08-27 03:52:05) já
passou da própria janela há três dias e **segue armazenada como `pending`** —
o badge da sidebar contava essa linha como acionável (mostrava 1), exatamente
o defeito do fato 4 da spec, agora com números reais por trás.

**Achado de composição confirmado em código, não só inferido do dado**:
varri toda a árvore por chamadores de `ApprovalStore.expire_due`/
`ApprovalService.expire_due` fora de teste. Os únicos chamadores de produção
encontrados são dentro de `platform/approvals/service.py:371-392`
(`ApprovalService.expire_due`, que por sua vez chama
`uow.approvals.expire_due`) — **e nenhuma rota, nenhum job agendado
(`platform/scheduler/`) e nenhum composition root chama
`ApprovalService.expire_due()` nem `uow.approvals.expire_due()` em produção**.
`RemediationGate._require_unexpired`'s docstring
(`platform/approvals/service.py:405-419`) já admite isso: "a deployment that
has not scheduled that sweep would otherwise leave every lapsed change
answerable for ever". Isto é um Artigo XIV real e pré-existente — o mecanismo
existe, tem teste próprio, e nunca foi composto num root que serve — e é
território desta feature: FR-006 (bucket `state=expired` real) e a regra de
tarefa 4 ("expirar... marca[m] estado") o exigem. **A correção**: `GET
/v1/approvals` (`list_approvals`, `gateway/http/routes/approvals.py:204`),
que já é chamado tanto pela tela quanto por `console/src/shell/load.ts:132`
(`readAttention`, a mesma leitura que alimenta o badge), passa a chamar
`uow.approvals.expire_due(now)` dentro da própria transação, antes de listar.
Isso fecha a lacuna do Artigo XIV: o mecanismo passa a ser composto num root
que de fato serve, e o badge — que já filtra por `state === 'pending'`
(`load.ts:134`, sem checar `expires_at`) — passa a contar certo **sem
nenhuma mudança no próprio filtro do lado do console**, porque o campo que ele
lê passa a ser verdadeiro.

O que o líder deve medir no fim do slot, e contra quais números: os mesmos
`select state, count(*) ...`/`select count(*) ...` acima, comparados a este
"antes" — o total de linhas nunca deve cair abaixo de 4 (+1 depois da
re-proposta do AN-08), a contagem de `expired` deve ir de 0 para 1 assim que
`GET /v1/approvals` for chamado uma vez contra o pod atualizado (sem esperar
nenhum job), e o badge deve ir de 1 para 0 nesse mesmo instante — e depois
voltar a 1 quando a re-proposta criar a pendente nova.

## T003 — linha de base da suíte sintética

`uv run pytest tests/synthetic -q` → **267 passed, 0 failed, EXIT=0** (log em
`/tmp/.../scratchpad/t003-synthetic-before.log`, fora do repositório).

## T001 — linha de base completa

`make verify` na árvore intacta (antes de qualquer edição desta feature) →
**13077 passed, 31 skipped, 0 failed, EXIT=0** — bate exatamente com o
checkpoint que o `progress.json` já registrava para o S1 fechado. Log completo
fora do repositório.

## T005 — acceptance confirmado vermelho, com a mensagem real de cada alegação

`console/tests/e2e/decisoes-estruturadas.acceptance.spec.ts`, escrito com uma
asserção por AN-01…AN-14, viewport 1440×1040. Rodado contra o mock
(`uv run python -m tools.console_e2e run --backing mock -- tests/e2e/decisoes-estruturadas.acceptance.spec.ts`),
**antes de qualquer edição de implementação**: `8 failed, 6 skipped, 1 passed,
EXIT=1`.

| Alegação | Resultado | Mensagem real |
|---|---|---|
| AN-01 | FAIL | `expect(locator).toBeVisible() failed` — `getByTestId('decision-card')` não existe |
| AN-02 | FAIL | idem — depende do cartão existir |
| AN-03 | FAIL | idem — `decision-risk` não existe |
| AN-04 | FAIL | idem — nenhuma das seis seções nomeadas existe |
| AN-05 | FAIL | idem — `raw-payload` não existe |
| AN-09 | FAIL | `expect(received).toBe(expected)` — badge real (sidebar hoje soma pendentes+propostas sem checar janela) contra `pendingCount=0` (nenhum `decision-card` novo) |
| AN-10 | FAIL | `decided-list` não existe |
| AN-11 | FAIL | `evidence-item` não existe |
| AN-06 | SKIP | `cardInState(page, 'pending')` não encontra `decision-card`, então pula com razão nomeada |
| AN-07 | SKIP | idem, para `state="expired"` |
| AN-08 | SKIP | idem |
| AN-12 | SKIP (esperado) | painel de Mudanças hoje não está vazio no dataset populated — condição de dado, não defeito; reavaliado depois de T031 |
| AN-13 | SKIP | precisa de `--scenario degraded` (`fixtures/manifest.json` ganhou a entrada `{"slug": "approvals", "status": 500}` para tornar isto testável); sob `populated` a alegação não é exercitável e o teste diz isso em vez de fingir verde |
| Edge case (muitas pendentes) | SKIP | menos de duas pendentes no dataset atual |
| AN-14 | **PASS** | correto por enquanto — nenhuma chave nova é referenciada ainda; deixa de ser um "verde vazio" assim que a Fase 3 referenciar as chaves declaradas no relatório final, e nesse ponto será vermelho de novo até o merge aplicar as chaves (ver seção "i18n" abaixo) |

Achado corrigido durante a escrita do próprio spec, antes de qualquer
implementação: minha primeira tentativa de AN-09 comparava dois seletores
inventados (`nav-count`+`data-nav="decisions"`, que não existe) e por isso
lia 0 dos dois lados — "verde" sem medir nada, a classe exata de defeito que
esta onda já achou duas vezes. Corrigido para o seletor real
(`nav-entry[data-area="decisions"] nav-count`, `sidebar.tsx:195-220`, que
**omite o `<span>` inteiro quando a contagem é zero** — absent, não um chip
"0") antes de aceitar a leitura.

## T012, T013 — testes vitest do console (Fase 1)

**T012** — `console/tests/unit/surfaces/decision-card.test.tsx`, contra um
`DecisionCard` (`@/surfaces/proposal`) ainda inexistente. Confirmado vermelho
de verdade: `12 failed`, todos com `Element type is invalid... You likely
forgot to export your component` — o componente nem existe. Cobre as seis
seções, os dois ramos de decisão (`DecisionControls` com interação aberta,
`IncidentDecisionControls` sem — os dois compostos sem edição, só o entorno
muda), o rodapé expirado, o desfecho decidido, campo ausente, e o medidor de
risco.

**T013** — dois casos novos em `console/tests/unit/shell/load.test.ts`
(mesmo arquivo que já cobre `loadAttention`/`countsFrom`, para não duplicar o
setup de fixture). **Não pude confirmá-los vermelhos — e digo isso nestes
termos, não finjo que estavam.** Os dois passaram de primeira, sem nenhuma
mudança de código: `readAttention` (`console/src/shell/load.ts:134`) já
filtra por `text(record, 'state') !== 'pending'`, sem olhar `expires_at` — o
que já é exatamente "só pendente conta" **desde que o campo `state` que
chega do servidor seja verdadeiro**. A lacuna real de FR-020 nunca esteve no
cliente; está inteira no servidor (nada chama `expire_due()` hoje — achado
do T004/T002 acima). Deixo os dois testes como caracterização: provam que o
filtro do lado do console já está certo, e continuam verdes depois de T015
fechar o lado do servidor — se algum dia regredirem, é o `load.ts` que
quebrou, não a integração dos dois lados.

## T015-T021 — servidor: fase 2 completa e verde

Todos os 31 testes das cinco suítes novas mais `test_approval_execution.py`
(pré-existente, decidir por interação continua intocado) passam juntos, com
`mypy --strict` e `ruff` limpos em todo o conjunto tocado.

**Achado real, encontrado e corrigido**: minha primeira versão de
`repropose_approval` abria `async with state.gateway.begin(auth.scope) as
uow:` e, **dentro** desse bloco, chamava `desk.requests.queue(action)` — que
por sua vez chama `ApprovalService.queue()`
(`platform/approvals/service.py:250`), que abre **outro**
`self.gateway.begin(self.scope)` no mesmo `gateway`. `FakePersistence.begin`
usa `asyncio.Lock()`, que não é reentrante — o resultado não era um erro, era
um **deadlock silencioso**: a suíte travava sem mensagem nenhuma até o
`timeout` do shell matar o processo. Corrigido para três transações
sequenciais, nunca aninhadas (ler + checar idempotência; enfileirar fora de
qualquer `begin`; amender o vínculo de origem). Registrado aqui porque é
exatamente a classe de defeito que só aparece rodando, nunca lendo — e porque
qualquer outra rota que algum dia componha uma escrita através de
`RequestBuilder`/`ApprovalService` **dentro** de uma transação já aberta
tropeça na mesma coisa.

**Duas rotas esquecidas na tabela de permissões.** `POST
.../repropose` e `POST .../discard` devolviam `UndeclaredRoute` (500) até eu
registrá-las em `gateway/http/security/console_routes.py`, com
`Permission.APPROVAL_REVIEW` — a mesma permissão que já governa decidir,
porque repropor/descartar são o mesmo ato de administrar a fila.

**Compatibilidade com a 060, verificada, não presumida.**
`console/src/surfaces/screens/incident-detail.tsx:312` já lê
`ApprovalView.blast_radius_count` (campo antigo, achatado). Nada nesta
feature remove ou renomeia esse campo — todo campo novo é aditivo. Confirmado
por grep antes de tocar o modelo, não depois.

**Race de re-proposta concorrente — limitação conhecida, não resolvida.** A
checagem de idempotência (T008/FR-017) lê `list_pending` numa transação e só
grava o vínculo de origem em outra, três passos depois, sem lock entre as
duas — duas chamadas verdadeiramente simultâneas ao mesmo `repropose` **podem**
as duas passarem pela checagem e produzir duas pendentes para a mesma origem.
Fechar isso de verdade pediria uma constraint única no banco (migração,
fora do escopo decidido em T004c) ou um mecanismo de exclusão que não existe
hoje. Dado que propose-only nunca aplica nada sozinho, o pior caso é um
humano vendo duas pendentes e descartando uma — não uma escrita dupla. Não
resolvido nesta feature; registrado para quem revisar.

**Migração — decisão confirmada, nenhuma.** `state` é `String(32)` sem
`CHECK` (`platform/persistence/postgres/models.py:582`); `"discarded"` cabe.
`arguments` já é `JSONB`; `origin_approval_id` vive lá
(`_ORIGIN_APPROVAL_ID_KEY`, `gateway/http/routes/approvals.py`). Nenhuma
revisão Alembic nesta feature — nada para o líder cravar contra a feature
par.

## FR-021 — "aplicada e verificada", e um método corrigido no processo

`applied_and_verified: bool` em `ApprovalView`, verdadeiro só quando
`request.state is APPROVED` e `uow.remediation.get(action.action_id)` devolve
um `RemediationOutcome` com `state is VerificationState.VERIFIED`
(`platform/persistence/ports/remediation_ledger.py`). Recusada/descartada
nunca perguntam ao ledger — não há obrigação de verificação para uma ação
que nunca rodou, e perguntar mesmo assim devolveria "sem obrigação", um fato
diferente de "ainda não verificada".

**Achado de processo, não de produto.** Meu primeiro script de edição fazia
três substituições em memória com um `assert` cada, escrevendo o arquivo só
no final. O terceiro `assert` falhou (indentação) e a exceção interrompeu o
script **antes** do `f.write()` — o que significa que as duas primeiras
substituições, ambas bem-sucedidas em memória, nunca chegaram ao disco. Um
segundo script, corrigindo só o terceiro ponto, aplicou-se contra o arquivo
original (sem as duas primeiras mudanças) e criou um `git add` cujo diff
citava `_applied_and_verified` sem defini-la em lugar nenhum — `ruff` pegou
antes do líder, que preferiu não comitar a comitar um `HEAD` que não linta.
Refeito com uma verificação em disco (`grep`) depois de cada escrita
individual, não mais em lote.

## Ledger de critérios (uma linha por obrigação atômica)

| Peça | Estado | Detalhe |
|---|---|---|
| T001 baseline `make verify` | FEITO | 13077 passed, 31 skipped, 0 failed, EXIT=0 — ver seção acima |
| T002 antes do staging | Feito pelo líder | ver seção acima; números: 3 approved, 1 pending (na verdade já expirada por relógio) |
| T003 baseline sintética | FEITO | 267 passed, 0 failed, EXIT=0 — ver seção acima |
| T004(a) rota gateway | FEITO | `gateway/http/routes/approvals.py` |
| T004(b) raiz de composição | FEITO | ver acima |
| T004(c) migração | FEITO — decisão: nenhuma | ver acima |
| T004(d) SQL de contagem | FEITO | ver acima |
| T005 acceptance vermelho | FEITO | `console/tests/e2e/decisoes-estruturadas.acceptance.spec.ts` — 8 failed, 6 skipped, 1 passed (AN-14, honesto — nenhuma chave nova referenciada ainda), EXIT=1 |

*(preenchido incrementalmente conforme as fases avançam — ver commits)*

## T006-T011, T014 — contratos pytest, vermelhos com mensagem real (exceto T014)

Todos em `tests/unit/gateway/http/`, seguindo o padrão de fixtures de
`test_approval_execution.py` (`deployment`/`client`/`issue_token`, um
`RemediationDesk` composto por `compose_remediation`, aprovação enfileirada
via `desk.requests.queue(...)` — nunca `RemediationGate.decide()`).

| Arquivo | Tarefas | Resultado antes da implementação |
|---|---|---|
| `test_approvals_field_contract.py` | T006, T007 | 6 failed, 1 passed — `assert not missing` acusa os 15 campos novos ausentes; `KeyError: 'title'` na comparação lista×detalhe |
| `test_approvals_repropose.py` | T008 | 5 failed — todo POST `/repropose` devolve `404 Not Found` (rota não existe) |
| `test_approvals_discard.py` | T009 | 2 failed — todo POST `/discard` devolve `404 Not Found` |
| `test_approval_title_and_risk.py` | T010, T011 | `ImportError: cannot import name '_risk_of' from 'gateway.http.routes.approvals'` — nem a função existe ainda |
| `test_approval_interaction_decision_unaffected.py` | T014 | **2 passed** — caracterização confirmada verde na linha de base, antes de qualquer edição. Precisou semear um `AgentRun` de verdade (`uow.run_traces.start_run`) além da entrada no `FakeInvestigationRunner`, porque `gateway/http/routes/tenancy.py::visible` checa o time do run contra o do chamador — sem isso a rota devolvia 404 por "não visível", não pela ausência de mecanismo. |

`test_state_expired_returns_only_truly_lapsed_rows` e o teste de descarte
usam `uow.approvals.expire_due(<relógio bem no futuro>)` diretamente — o
mesmo mecanismo que T015 vai chamar dentro de `list_approvals` — para
produzir uma linha genuinamente expirada, em vez de mexer no estado interno
do fake (que o próprio docstring de `FakePersistence.state` desaconselha:
"Writing through this bypasses the transaction machinery").


## T022-T028 — console: a tela reescrita, herdada e fechada nesta sessão

Retomando uma sessão anterior perdida (transcript não recuperável, trabalho
preservado só pelos commits): ao assumir, `DecisionCard` (seis seções,
medidor de risco, `<details>` de payload bruto), o rodapé de expirada
(`ExpiredFooterControls`) e o `ApprovalsTab` reescrito já estavam commitados
e corretos em substância (T022, verificado por leitura linha a linha antes
de qualquer edição, não redescoberto). O que faltava, fechado agora:

- **T023, a causa nomeada.** O rodapé de expirada mostrava sempre a mesma
  frase genérica ("The deployment did not answer...") em qualquer falha —
  rede fora do ar ou uma recusa nomeada do backend (422/409) liam
  identicamente. `ExpiredFooterControls` agora lê `detail` do corpo da
  resposta quando existe e mostra a causa real; a frase genérica sobra só
  para quando a chamada nunca chegou a responder. Vermelho confirmado contra
  a versão anterior do componente antes do reparo
  (`console/tests/unit/surfaces/expired-footer.test.tsx`, 3 testes, o de
  causa nomeada falhando com a frase genérica no lugar da causa).
- **T028, o `data-state` que faltava na linha colapsada.** A regra "só
  `queue[0]` expande" já estava certa, mas a linha colapsada
  (`decision-row-collapsed`) não carregava nenhum carimbo de estado — uma
  pendente e uma expirada colapsadas eram indistinguíveis sem abrir o
  carimbo de tempo. Corrigido (`data-state={state}` na própria linha); o
  teste original do "muitas pendentes" só contava
  `decision-card[data-state=pending]`, que nunca chega a dois nesta base
  porque uma expirada sempre ocupa a posição 0 — reescrito para contar a
  fila combinada de verdade (`decision-card` + `decision-row-collapsed`,
  qualquer estado), e passa contra as duas expiradas do próprio dataset
  desta feature.
- **T026, os pills.** Composto localmente em `decisions.tsx`
  (`DecisionsTabBar`), não como reescrita do `TabLinks` compartilhado —
  esse componente serve outras telas que esta feature não possui, e o
  padrão de pill é uma escolha visual desta tela, não uma mudança do que um
  "tab" é. Mesmo contrato de testid/`data-tab`/`aria-current`/`href` que
  `TabLinks` já dava; o teste próprio da tela
  (`console/tests/unit/surfaces/decisions.test.tsx`, 7 testes) não mudou e
  continua verde. **Decisão de escopo, registrada e não escondida**: o chip
  "Ações" no artboard carrega uma contagem; esta versão não a mostra. Buscar
  esse número aqui significaria ler aprovações mesmo com a aba Changes
  aberta — o mesmo custo que o comentário desta própria tela já recusa na
  direção oposta ("a reader looking at Actions should not wait on a
  Changes-proposed fetch nobody asked for"). O número já existe e é
  publicamente correto: o badge da sidebar.

## Dois defeitos reais no mock, achados rodando — não lendo

**O primeiro: a query string nunca chegava à busca por `state=`.**
`_query_arguments()` (commit anterior, resgatado pelo líder) já fazia o
parse certo, mas `MockPlane.__call__` construía `path` só a partir de
`scope["path"]` — que o ASGI nunca inclui a query string, por especificação,
exatamente como o próprio docstring da função já alertava. O resultado:
`?state=expired`, `?state=pending` e `?state=decided` respondiam todos com o
mesmo bucket default. Descoberto rodando `curl` direto contra um mock
isolado (não lendo os dois métodos lado a lado) — `?state=expired` devolvia
`apr-0001`, que é `state: "pending"`. Corrigido montando um `target` que
inclui a query string só para o caminho que efetivamente busca o fixture,
mantendo o `path` puro para o casamento de rota e para a contagem de
requisições (`request_counts()` tem teste próprio que espera chaves sem
query string).

**O segundo, achado só depois do primeiro estar corrigido: uma escrita de
sessão envenenava todo bucket que ainda não tinha a própria escrita.**
`_lookup` (o caminho que responde ao cliente) cai de um "match exato" perdido
para `written.written.get((slug, ""))` — um formato pensado para escritas
de um bucket só, como `approval-rollback`. A listagem nova de aprovações tem
três buckets (`state=pending`/`expired`/`decided`) sob o mesmo slug; o
primeiro repropor ou descartar de uma sessão escrevia só nos buckets que
tocava, e qualquer *outro* bucket sem escrita própria passava a responder
com esse mesmo bucket em vez do seu. Sintoma visto na tela: depois de um
repropor, `state=expired` devolvia a lista de pendentes (duplicada), e o
"Decididas recentemente" mostrava itens com `verdict: ""`. Achado com um
`process.stdout.write` temporário dentro de `ApprovalsTab` — e só depois de
perceber que `python -m tools.console_e2e` serve `.next/standalone/server.js`
pré-compilado, nunca um rebuild automático: a primeira tentativa de debug
não mostrou nada porque testava contra um build de antes da própria linha
de debug existir. `make console-build` rodado a cada mudança de
`console/src/**` daqui em diante nesta sessão, sempre confirmado pelo log
do build, nunca presumido. Corrigido dando a cada um dos quatro buckets sua
própria escrita de sessão (mesmo quando o conteúdo não muda) sempre que
qualquer um deles é tocado — fechando o fallback perigoso para este slug
sem alterar o mecanismo genérico, que outros slugs (`approval-rollback`
incluído) continuam usando como antes.

**Achado de processo, não só de produto**: o primeiro teste de AN-08 escrito
pela sessão anterior passava — mas pelo motivo errado. O bug do fallback
tinha esvaziado o bucket `expired`, então `queue[0]` virava a pendente nova
por acidente, não porque a reescrita da fila faz isso de propósito. Depois
do reparo do fallback, a mesma asserção (`.first()` deve ser `pending`)
passou a falhar honestamente: uma expirada nunca sai de `state=expired` só
por ser reproposta (só descartar muda seu estado), e a fila sempre expande
`queue[0]`, que é sempre uma expirada enquanto qualquer expirada existir.
AN-08 foi reescrito para verificar a alegação real — a decisão nova fica
visível na tela, por id, em qualquer das duas representações — em vez de
uma posição que a própria tela nunca prometeu. AN-09 tinha o mesmo defeito
de medição, por outro motivo: comparava o badge só contra aprovações
pendentes, mas o badge soma aprovações e propostas de mudança pendentes por
desenho documentado (`decisions.tsx`, decisão 6 do plano) — reescrito para
somar as duas filas antes de comparar.

## O dataset ganhou uma segunda expirada, com origem morta (T031, FR-016)

`_EXPIRED_DEAD_ORIGIN` (`apr-0005`) — reproposta devolve `422` nomeado via
um registro de fixture com correspondência exata no `approval_id` (o
registro genérico de sucesso, sem `approval_id` nos argumentos, responde a
qualquer outro id). Fica atrás na fila combinada (depois de `apr-0002`), por
desenho: a expirada que os testes de aceite exercitam continua a mesma,
sem depender da ordem de dois registros com o mesmo estado.

## T032 — achado para quem for recapturar o registro visual

`console/visual/screens.json` já tinha duas entradas para `/decisions`
(`decisions-1440-light`, `decisions-changes-1440-light`), ambas
`"status": "baselined"` contra o cartão antigo de 8 campos — a própria razão
registrada em uma delas descreve o defeito que esta feature fecha ("the
card grouped under 'Past its expiry' carries the same Approve control as
the live one"). As duas precisam de nova razão e nova captura no merge, não
só de aceitar a imagem nova.

**Os dois artboards mostram só o estado expirado como cartão herói** —
nenhum dos dois (`Decisions.dc.html`, `DecisionsLight.dc.html`) desenha uma
pendente como o cartão grande. Isso bate exatamente com o dataset desta
feature (a expirada sempre ocupa `queue[0]`) e não é coincidência forçada —
é o que os dois artboards de fato pedem. Capturar um herói *pendente* de
verdade exigiria um cenário sem nenhuma expirada, que hoje não existe; até
lá, a proteção visual do estado pendente é
`console/tests/unit/surfaces/decision-card.test.tsx` (`state: 'pending'`),
não uma baseline de imagem.

`make console-visual` (só leitura, nenhuma baseline gravada) rodado nesta
sessão: 33 telas falham contra sua própria baseline, `decisions` e
`decisions-changes` entre elas — mas a maioria das 33 (agent, incident,
knowledge, resources, shell, run-detail…) não tem nada a ver com esta
feature. É a dívida de baseline já conhecida da onda desde a
000-fundacao-visual, não algo que esta sessão introduziu.

## Chaves i18n novas — `en` aplicado, `pt-BR` proposto para o merge

27 chaves novas em `console/src/i18n/en.ts` (regra 3 do `tasks.md`, exceção
nomeada para esta feature — o tipo de chave derivado do `en` exige que a
chave exista para ser referenciada). Nenhuma chave nova para os pills — o
seletor de abas reusa `decisions.tabs`/`decisions.tab.actions`/
`decisions.tab.changes`, já existentes antes desta feature.
`console/tests/unit/i18n/catalogue.test.ts` está vermelho agora, nomeando
exatamente essas 27 chaves como ausentes de `pt-BR.ts` — vermelho esperado
até o merge aplicar as chaves (o relatório final ao orquestrador carrega a
lista completa com o texto `pt-BR` proposto), não um defeito desta feature.

## Ledger de critérios — atualizado

| Peça | Estado | Detalhe |
|---|---|---|
| T001-T021 | FEITO / Feito pelo líder / decisão nenhuma | ver seções acima |
| T022 | FEITO (já existia, verificado) | `console/src/surfaces/proposal.tsx`, `approvals.tsx:190-214` |
| T023 | FEITO | `expired-footer.tsx` — causa nomeada fechada nesta sessão |
| T024 | FEITO (já existia, verificado) | `approvals.tsx:433-479` |
| T025 | FEITO (já existia, verificado) | `shell/load.ts:134`; AN-09 corrigido, não o código |
| T026 | FEITO | `decisions.tsx` (`DecisionsTabBar`); sem contagem ao vivo, decisão registrada |
| T027 | FEITO (já existia, verificado) | `panel.tsx` + `labels.ts:27-34`; AN-13 passa contra `--scenario degraded` |
| T028 | FEITO | `approvals.tsx:377-401` + `data-state` na linha colapsada |
| T029 | FEITO | 27 chaves; lista `pt-BR` no relatório final |
| T030 | FEITO | `mockplane contract`/`build` sem diff; `console-client-check` limpo |
| T031 | FEITO | `_EXPIRED_DEAD_ORIGIN`, repropor/descartar simulados de ponta a ponta |
| T032 | Encerrada sem fechar | achados acima; `screens.json` não é meu para editar |
| T033 | FEITO | acceptance: 12 passed, 3 skipped (condição de dado), 0 failed |
| T034 | FEITO | sintética: 267 passed, idêntico a T003 |
| T035 | ver relatório final | `make verify` |
| T036 | este documento + relatório final | |

## Correção a uma alegação anterior — T015 "verde" era verde parcial

A seção "T015-T021 — servidor: fase 2 completa e verde" (acima) registra os
31 testes das cinco suítes novas mais `test_approval_execution.py` passando
— verdade, mas não era o quadro completo, e é preciso dizer isso em vez de
deixar a alegação como estava. `make verify` nunca chegou a rodar `pytest`
inteiro nesta feature até agora: sua cadeia de dependências para em
`console-static` no primeiro checkpoint vermelho (que sempre existiu, por
motivos diferentes, em cada tentativa desta sessão), e `test` — o alvo que
roda a suíte Python inteira — nunca é alcançado quando isso acontece. Rodei
`make test` direto, ignorando essa cadeia, e achei um regressão real de
T015: `tests/unit/gateway/http/test_console_support_routes.py::test_the_pending_queue_lists_the_longest_waiting_first`
falhava porque seu fixture (`_seed_approval`) grava `expires_at` a partir de
um `EPOCH` fixo (1 de maio de 2026) mais uma hora — no passado frente ao
relógio real de hoje. Antes de T015, `list_approvals` nunca olhava o
relógio; depois, `expire_due(datetime.now(UTC))` roda dentro da própria
transação antes de listar, e essa aprovação era varrida para `expired` no
instante em que o teste pedia `state=pending` — quebrando um teste que não
tem nada a ver com expiração, pelo mesmo motivo que fez o badge da sidebar
mentir em produção. Corrigido âncorando `expires_at` ao relógio real do
teste em vez do `EPOCH` fixo; `requested_at` continua `EPOCH` (nenhum outro
teste do arquivo depende do valor de `expires_at`, confirmado por leitura
de cada uso). Suíte completa depois do reparo:
`uv run pytest -n 4 --dist loadgroup -m "not benchmark" ...` → **13100
passed, 31 skipped, 0 failed** (era 13099 passed, 1 failed antes do reparo
— a diferença é exatamente essa uma linha, nada mais mudou); em seguida
`pytest -m benchmark` → **38 passed**. `make test` completo, EXIT=0.

**Não era instabilidade — era determinístico, e digo isto com prova, não
por impressão.** A falha original: `assert [entry["approval_id"] for entry
in response.json()["approvals"]] == ["ap-1"]` recebia `[]` — a aprovação
sumia da listagem `state=pending` porque seu `expires_at`
(`EPOCH + timedelta(hours=1)`, `EPOCH` fixo em 1 de maio de 2026) já tinha
passado frente ao relógio real de hoje (fim de agosto de 2026), e T015
agora varre para `expired` toda aprovação vencida antes de listar
`pending` — a mesma correção que fecha a mentira do badge da sidebar. Não
podia ser instabilidade: uma data fixa no passado só fica mais velha a
cada dia, nunca por acaso "acerta" de novo — falharia em toda execução, sem
exceção, a partir do dia em que `EPOCH` ficou para trás do relógio real, e
continuaria falhando para sempre sem este reparo. Corrigido no commit
`503ce94b`. Confirmado em duas camadas, não uma: rodei o arquivo isolado
(`pytest tests/unit/gateway/http/test_console_support_routes.py -q`) antes
de sequer tentar a suíte inteira de novo — 19 passed, EXIT=0 — e só depois
rodei `make test` completo, que fechou em 13100 passed/0 failed, uma linha
a mais que o total anterior (13099 passed + 1 failed), confirmando que
nada além dessa linha mudou de lado.

**Achado de processo, nomeado**: esta era a primeira vez, nesta feature
inteira, que `pytest` completo rodou depois de T015 ter composto
`expire_due()` dentro de `list_approvals`. `make verify` nunca chegou lá
antes — sua cadeia de dependências para no primeiro checkpoint vermelho de
`console-static`, que sempre havia um em cada tentativa desta sessão — e a
alegação "T015...verde" registrada mais acima no controle era verdadeira
só para as suítes tocadas diretamente, não para o repositório inteiro. Não
reescrevo essa seção: fica como estava, com esta correção ao lado dela.
