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

(preenchido depois que `make verify` — rodando em segundo plano desde o
início desta implementação — terminar; ver seção "Gates" abaixo.)

## Ledger de critérios (uma linha por obrigação atômica)

| Peça | Estado | Detalhe |
|---|---|---|
| T001 baseline `make verify` | Em andamento | rodado em segundo plano; log fora do repositório em `/tmp/claude-999/.../scratchpad/t001-make-verify.log` |
| T002 antes do staging | Feito pelo líder | ver seção acima |
| T003 baseline sintética | Pendente | depende de T001 terminar |
| T004(a) rota gateway | FEITO | `gateway/http/routes/approvals.py` |
| T004(b) raiz de composição | FEITO | ver acima |
| T004(c) migração | FEITO — decisão: nenhuma | ver acima |
| T004(d) SQL de contagem | FEITO | ver acima |

*(preenchido incrementalmente conforme as fases avançam — ver commits)*
