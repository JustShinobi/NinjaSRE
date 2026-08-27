# Controle — Decisão composta

**O estado abaixo foi verificado contra o código atual**, na worktree
`/srv/workspaces/NinjaSRE/.claude/worktrees/agent-ad2b3b198c83bd6f6`
(ramo `worktree-agent-ad2b3b198c83bd6f6`), partindo de `928c342`.

Nota de execução: a worktree nasceu apontada para o **primeiro commit do
repositório**, não para `master`. Foi reapontada com `git reset --hard master`
antes de qualquer trabalho; sem isso a feature teria sido escrita contra uma
árvore com um único arquivo.

**Fase 9 fechada em 2026-08-24, numa segunda worktree** (mesmo defeito de
nascença, mesma correção) — T067–T071 reconferidos contra `master` como ele
está hoje, e a razão nomeada de S01–S03 continuarem sem marcar: seção 10.

---

## 1. O par ANTES / DEPOIS — a prova da feature

### ANTES (varredura na árvore intacta)

`RemediationGate(` — **nenhuma ocorrência de produção**:

| Ocorrência | O que é |
|---|---|
| `tests/synthetic/test_first_investigation.py:238` | cenário sintético |
| `tests/unit/platform/remediation/test_gating.py:154` | teste de unidade |
| `tests/unit/platform/remediation/test_no_unapproved_write.py:82` | teste de unidade |
| `tests/contract/autonomy/test_the_gate_obeys_the_policy.py:205` e `:379` | teste de contrato |

`AutonomyGate(` — **uma construção de produção, sem caminho a partir de uma
investigação**:

| Ocorrência | O que é |
|---|---|
| `platform/autonomy/service.py:153` (`AutonomyService.gate`) | produção, mas só alcançada por `gateway/http/routes/autonomy.py:289` — as rotas que **explicam** a postura e desenham o outlook. Nunca pelo caminho de uma investigação |
| `tools/mockplane/dataset/served.py:3087` | plano de dados de mentira |
| 24 ocorrências sob `tests/` | testes |

`build_pipeline(` — nenhum chamador de produção: `tests/harness/runner.py:262`,
`tests/harness/investigator.py:193` e cinco testes.

`TeamCatalogueResolver` — **nunca instanciado**: um exemplo de docstring, um
re-export e uma entrada de `__all__`.

### DEPOIS

`RemediationGate(` — construído em **`gateway/http/remediation.py:130`**, dentro
de `RemediationDesk.gate_for`, com dois chamadores de produção:

| Chamador de produção | Quando |
|---|---|
| `gateway/runtime/investigator.py:375` | por investigação, registrado no `pre_tool_use` do laço |
| `gateway/http/routes/approvals.py:380` | por decisão de aprovação |

O balcão que os dois leem é construído em
`gateway/http/remediation.py:172 compose_remediation`, chamado em
**`gateway/http/lifespan.py:92`**.

`AutonomyGate(` — continua sendo construído em `platform/autonomy/service.py:153`,
e passa a ser **alcançado a partir de uma investigação**:
`gateway/http/remediation.py:287` (`service.gate(policies)`) →
`gateway/http/remediation.py:241` (`autonomy_of=`) →
`gateway/http/remediation.py:137` (`resolve_autonomy=`) →
`platform/remediation/gating.py:306`, resolvido **no momento em que uma escrita
é decidida**, não no boot.

`TeamCatalogueResolver` — instanciado em
**`gateway/runtime/investigator.py:419`**, pela entrada nova sem estado
(`capabilities/registry/planning.py:for_availability`).

`zero_integration_outcome` — **uma implementação, dois chamadores**:
`core/pipeline/stages/resolve_integrations.py:69` (o estágio) e
`gateway/runtime/investigator.py:433` (o caminho de serving).

`build_pipeline` — continua sem chamador de serving, e agora **declara isso de
si mesmo nomeando o harness de avaliação** (`core/pipeline/build.py`).

---

## 2. Quem constrói cada mecanismo, e o que reprova se o fio for cortado

Cada linha foi confirmada **cortando o fio à mão e rodando os testes**, não por
inspeção.

| Mecanismo | Quem o constrói em produção | Fio cortado | Testes que reprovam |
|---|---|---|---|
| `RemediationGate` no laço | `gateway/runtime/investigator.py:375` | remover o `register(hooks)` | **7 de 10** em `tests/unit/gateway/runtime/test_remediation_per_run.py` |
| O balcão, na root assíncrona | `gateway/http/lifespan.py:92` | remover a chamada a `compose_remediation` | **3** em `tests/unit/gateway/http/test_remediation_composition.py` (composição, ordem depois do runner, ordem depois das ligações) |
| O balcão chega ao runner | `gateway/http/remediation.py` (`attach_remediation`) | remover o anexo | **1 + 7** (`..._read_one_desk` mais a suíte por run inteira) |
| `AutonomyGate` na decisão | `gateway/http/remediation.py:287` → `:241` → `:137` | remover `resolve_autonomy=` | **3**: `test_the_gate_for_a_run_resolves_this_deployments_posture`, `test_a_deployment_that_configured_no_posture_resolves_to_proposing`, `test_the_refusal_says_the_policy_decided` |
| `TeamCatalogueResolver` na seleção | `gateway/runtime/investigator.py:419` | trocar por um catálogo não estreitado | **5 de 8** em `tests/unit/gateway/runtime/test_tool_selection.py` |
| `build_pipeline` dormente | ninguém, declaradamente | tirar o nome do harness da declaração | **1** em `tests/architecture/test_one_investigation_orchestration.py` |

Antes de acrescentar dois testes, cortar o resolvedor de autonomia reprovava
**um** teste só. Um é fino demais para um mecanismo cuja ausência é o defeito
inteiro, então dois testes novos foram escritos a partir do compositor real —
não de um portão que o próprio teste constrói — e o corte passou a reprovar
três.

---

## 3. Tabela de entrega

| Peça | Estado | Detalhe |
|---|---|---|
| Linha de base (`make verify` na árvore intacta) | FEITO | 3 failed / 12275 passed / 27 skipped. As três eram de ambiente: `console/.next/standalone/server.js` não existia. Depois de `make console-build`, as três passam → linha de base efetiva **verde, 12278 passed** |
| Contagens de partida, lidas da árvore | FEITO | 105 capacidades (80 ferramentas + 25 skills); read 44, read_sensitive 12, write_reversible 15, write_irreversible 6, destructive 3; 24 escrevem; 24 declaram exigir aprovação, todas com razão e plano/planejador; 20 componentes de remediação |
| Suíte sintética antes | FEITO | 5/5 (100%) |
| Inventário dos dois portões antes | FEITO | Seção 1 |
| Teste de caracterização da recusa direta | FEITO (nasce verde) | `tests/contract/remediation/test_the_direct_call_still_refuses.py` — 43 passed |
| Vermelhos da Fase 1 confirmados | FEITO | Seção 4 |
| Campo de estado do balcão | FEITO | `gateway/http/state.py` (`remediation: Any = None`, com o comentário do que a ausência significa) |
| Módulo compositor novo | FEITO | `gateway/http/remediation.py` |
| Registro de componentes no compositor | FEITO (com ressalva) | `gateway/http/remediation.py:180`; `known_signals` é `None` — ver seção 6 |
| Gerador de plano e construtor de pedido | FEITO | `gateway/http/remediation.py:206–214` |
| Executor com o interruptor do processo | FEITO | `gateway/http/remediation.py:216–232`; `kill_switch=state.kill_switch` |
| Isolamento de execução | FEITO | `gateway/http/remediation.py:_isolation` / `_sandbox_for`, perfil de `resolve_profile()` |
| Política de portamento | FEITO | `GatingPolicy.of_policy(DEFAULT_POLICY)`; silêncio → tudo acima de leitura sensível |
| Construtor do portão de autonomia | FEITO | `gateway/http/remediation.py:259 _autonomy_of` |
| Chamada na root assíncrona, na ordem certa | FEITO | `gateway/http/lifespan.py:92`, depois de acesso a integrações, credenciais de provedor e reconstrução do runner, com o comentário explicando por quê |
| Campo do balcão no runner | FEITO | `gateway/runtime/investigator.py` (`attach_remediation`, `remediation`) |
| Contexto de run e portão por investigação | FEITO | `gateway/runtime/investigator.py:_run_context`, `:375` |
| Ordem do hook depois dos guardrails | FEITO (já existia, verificado) | `platform/remediation/gating.py:88` (`HOOK_ORDER = -50`) — não tocado |
| Nada compartilha portão entre runs | FEITO | dois testes concorrentes, requisitante e run distintos |
| Proposta gravada com ação, recurso, raio e plano | FEITO | `test_a_write_inside_an_investigation_becomes_a_stored_proposal`, `test_the_proposal_carries_the_plan_that_would_undo_it` |
| Propose-only não altera nada e nomeia a política | FEITO | `test_nothing_is_changed_while_the_deployment_only_proposes`, `test_the_refusal_says_the_policy_decided` |
| Entrada pública "esta aprovação foi concedida" | FEITO | `platform/remediation/gating.py:execute_approved` — reconfere interruptor e travas, desce pelo `_execute` que já existia |
| Ação reconstruída do que o pedido guardou | FEITO | `gateway/http/routes/approvals.py:_approved_action`, sobre `RemediationAction.of_payload` (já existia) |
| Rota de decisão leva adiante pelo portão | FEITO | `gateway/http/routes/approvals.py:380`, depois da gravação; docstring da rota reescrita |
| Rejeição e interruptor não executam | FEITO | `test_rejecting_carries_nothing_out_and_keeps_the_reason`, `test_the_switch_engaged_after_the_decision_refuses_the_execution` |
| Registro diz se foi autônoma ou aprovada | PARCIAL | o identificador da aprovação está na **trilha de auditoria** (`test_the_recorded_outcome_names_the_approval_that_authorised_it`) e `autonomous=False` no registro de resultados. `RemediationOutcome` não tem campo `approval_id` — ver seção 6 |
| Executor continua com um chamador só | FEITO (já existia, verificado) | `tests/architecture/test_one_path_to_execution.py` — 63 passed, com a segunda entrada já existindo |
| Entrada sem estado do resolvedor | FEITO | `capabilities/registry/planning.py:for_availability`; `resolve(state)` delega |
| Resolvedor instanciado no serving | FEITO | `gateway/runtime/investigator.py:419` |
| Configuração ilegível → postura estrita | FEITO | `gateway/runtime/investigator.py:_availability`, com o motivo no log |
| Estreitamento por nível de efeito colateral | FEITO | `gateway/runtime/investigator.py:_can_carry` |
| Estreitamento pelas integrações do time | FEITO | `_select_tools`, com as exclusões registradas |
| Corte no teto por último | FEITO | `_select_tools`; o teste força a ordem e afirma a própria pré-condição |
| Resposta de zero integrações, uma implementação | FEITO | `zero_integration_outcome(resolved, alert_source=…)`, dois chamadores |
| Docstring da seleção atualizada | FEITO | `gateway/runtime/investigator.py:_select_tools` |
| Balcão de perguntas por run | FEITO | `_LiveRun.handoff`, `_handoff_for` |
| Pergunta declarada substituída pela do run | FEITO | `_select_tools`, por nome |
| Listagem, busca e resposta reais | FEITO | `tests/unit/gateway/runtime/test_run_interactions.py` — 7 passed |
| Primeira resposta vence, segunda informa quem | FEITO | `test_the_first_answer_wins_and_the_second_is_told_who_answered` |
| Identificador desconhecido × já respondido | FEITO | `test_an_identifier_nobody_raised_is_told_apart_from_one_already_answered` |
| Docstring do investigador atualizada | FEITO | `gateway/runtime/investigator.py` — a afirmação de que nada vincula o balcão deixou de existir |
| Pipeline declara dormência nomeando o construtor | FEITO | `core/pipeline/build.py` |
| Efeito medido sobre a suíte sintética | FEITO | 5/5 antes, 5/5 depois, cenário a cenário — **sem efeito**, e medido |
| Verificação completa ao final | FEITO | `make verify` → **exit 0 — 12386 passed / 27 skipped em 491,62s**. Contra a linha de base efetiva de 12278: **+108**, e os 108 reconciliam exatamente com as funções de teste dos nove arquivos novos (43 + 11 + 10 + 8 + 9 + 5 + 6 + 6 + 10) |
| Nenhum arquivo de escrita única do console tocado | FEITO | Nenhuma edição em `console/` |
| Pergunta que pede credencial recusada; janela expirada | NÃO INICIADO | ver seção 5 |
| Cenário sintético ponta a ponta (`tests/synthetic/`) | FEITO | `tests/synthetic/test_the_proposal_and_the_act.py` — 10 testes, um incidente contado uma vez: catálogo estreitado pela configuração lida da árvore, proposta com o desfazer, nada movido, aprovação pela rota, carga escalada, resultado e obrigação gravados |
| Pergunta que pede credencial recusada | FEITO | `test_a_question_asking_for_a_credential_never_reaches_a_person`, através do balcão composto |
| Pergunta não respondida dentro da janela | PARCIAL | a janela é afirmada (`test_the_desk_a_run_gets_carries_the_shipped_window`) e não exercitada: encurtá-la pede um seam que esta composição não tem, e o comportamento na expiração pertence ao balcão e é coberto lá |
| Contagens no banco de staging | Fora do escopo desta worktree | ver seção 7 |

---

## 4. Os vermelhos, com a mensagem real

| Teste | Mensagem do vermelho |
|---|---|
| composição do balcão (3 arquivos) | `ModuleNotFoundError: No module named 'gateway.http.remediation'` |
| resolvedor de catálogo | `AttributeError: 'TeamCatalogueResolver' object has no attribute 'for_availability'. Did you mean: 'availability'?` |
| interações por run (6 testes) | `TimeoutError` / `asyncio.exceptions.CancelledError` — a pergunta nunca aparece, porque nada vincula um balcão |
| caminho duplicado | `AssertionError: the dormancy note in core/pipeline/build.py does not name what does construct the pipeline.` |
| aprovação executa pelo portão | `AssertionError: a person approved the change and nothing was carried out. The proposal is a note nobody can answer.` |
| recusa direta (T005) | **verde de nascença**, 43 passed — declarado no próprio arquivo como a rede |
| executor com um chamador só (T022) | **verde**, 63 passed, antes e depois |

Ressalva de honestidade: o vermelho do resolvedor de catálogo, na primeira
tentativa, foi `AttributeError: type object 'EvidenceSource' has no attribute
'METRICS'` — defeito do próprio teste, não a ausência que ele existe para
acusar. Foi corrigido e o vermelho verdadeiro foi capturado depois; o commit que
corrige diz isso.

---

## 5. O que fica pendente, nomeado, não escondido

1. **Pergunta não respondida dentro da janela.** A metade da credencial está
   fechada; a da expiração fica afirmada e não exercitada — encurtar a janela
   pede um seam que esta composição não tem, e o que acontece na expiração
   pertence a `core/agent/handoff.py` e é coberto lá. **Dono: esta spec, se
   alguém quiser o seam.**
2. **Leitura de sinal na hora da execução.** A obrigação de verificar é gravada,
   e os valores "antes" saem vazios: o gravador de obrigações pede a leitura de
   dentro da própria unidade de trabalho, então uma implementação sobre o
   `PersistenceGateway` reentra numa transação já aberta — contra a persistência
   em memória isso é *deadlock* (medido: a suíte pendurou até o timeout), e
   contra a real é uma segunda conexão. O compositor passa um leitor que declara
   não ter nenhum. O que cabe ali é uma fonte de métricas viva, que esta
   composition root não constrói. **Dono: trabalho posterior de laço fechado.**
3. **`approval_id` no registro de resultados.** `RemediationOutcome` não tem esse
   campo; o identificador da aprovação viaja no `ExecutionRecord` e na trilha de
   auditoria, e é lá que o teste o afirma. Acrescentar a coluna é mudança de
   modelo de persistência e de migração — **recurso compartilhado do slot** —
   e ficou fora deliberadamente.
4. **Esperador de decisão dentro do laço.** `DecisionWaiter` continua sem
   implementação, por decisão do plano: o portão compõe com `waiter=None` e a
   execução é sempre uma segunda entrada. Dito no módulo, não escondido.
5. **Plano de controle genérico.** As sete capacidades transversais só têm
   ligação de plano de controle onde alguém a vincula; o compositor **não**
   inventa uma. Consequência medida e declarada: sem plano de controle ligado o
   balcão **não** é composto, e `unmet_for_remediation` nomeia isso — ver
   seção 6.

---

## 6. Descobertas que mudam como ler a árvore daqui em diante

**(a) Sem plano de controle ligado, o balcão não compõe — e isso alcança o
staging.** `capabilities/tools/remediation/control_plane.py` guarda um vínculo
de processo e **nada neste repositório o vincula**. Sem ele, `RequestBuilder`
lê um instantâneo declaradamente ilegível, `PlanFactory` não deriva plano, e a
chamada é recusada por falta de plano — *nenhuma aprovação seria enfileirada*.
Compor um balcão nessa condição seria compor um balcão que só sabe recusar, então
`compose_remediation` não compõe e escreve a linha que nomeia o que falta.

Consequência direta para o DoD: **a contagem de aprovações de remediação no
staging vai dar zero** enquanto nada vincular um plano de controle. O caminho
mais curto é vincular `ProxmoxControlPlane`
(`capabilities/tools/remediation/proxmox/plane.py:124`) a partir do cliente que
`compose_discovery_sources` já constrói — treze capacidades de hipervisor têm
componentes registrados. Isso **não** foi feito aqui: é uma decisão sobre o
agente propor escritas contra o hipervisor real do operador, e ela é do
operador, não minha. Está nomeada porque sem ela o S02 não fecha.

**(b) Quatro capacidades acima de leitura sensível vivem fora do pacote de
remediação** e não têm componentes: `alertmanager_acknowledge_incident`,
`propose_knowledge`, `pushover_post_message`, `telegram_post_message`. Com o
balcão composto, elas deixam de ser oferecidas a um turno — que é exatamente o
que a spec pede, e é uma **mudança de comportamento visível**: o agente perde
as capacidades de notificação e de proposta de conhecimento num deployment que
compõe o balcão. Se isso não for desejado, o conserto é registrar componentes
para elas ou rebaixar o nível declarado, não afrouxar o filtro.

**(c) Um hook que levanta exceção não bloqueia a chamada.** Durante a
implementação, um `pre_tool_use` que falhou apareceu como
`agent.hook_failed` e a chamada seguiu. A rede continua sendo a recusa no corpo
da capacidade — por isso ela não pode ser afrouxada — mas vale saber que o
portão **falha aberto** se o corpo dele levantar.

**(d) A permissão da rota de decisão não mudou.** Continua `approval.review`
(`gateway/http/security/console_routes.py:75`). O comentário ao lado dizia que a
rota "nunca executa"; agora executa, e a permissão foi mantida deliberadamente
porque mudá-la obrigaria a editar `console/src/shell/routes.ts`, que **não é
desta feature neste slot**. Se o operador quiser `remediation.execute` ali, é
uma linha em cada um dos dois arquivos.

**(e) `fixtures/contract/openapi.json` foi regenerado** (`python -m
tools.mockplane contract`) por causa de uma linha: a descrição publicada da
rota de decisão, que é a docstring. `console/src/api/schema.ts` **não** foi
regenerado — é arquivo de console e nenhum tipo mudou.

**(f) A worktree nasceu no commit errado.** Ver o cabeçalho.

---

## 7. O que o orquestrador precisa medir no ambiente real

A worktree não alcança cluster nem banco. Para fechar o DoD:

1. `select count(*) from approvals where arguments->>'change_type' = 'remediation';`
   — **vai dar zero** enquanto nada vincular um plano de controle (seção 6a).
   Medir mesmo assim, porque o número é a evidência de que a causa é essa e não
   outra.
2. `select count(*) from rollback_plans;` — idem.
3. `select count(*) from approvals where arguments->>'change_type' = 'remediation' and state <> 'pending';` — tem de ser **zero**.
4. `select count(*) from remediation_outcomes;` — tem de ser **zero** no staging.
5. No log do processo, depois do boot: `remediation.desk_composed` (com
   `capabilities` e `profile`) **ou** `remediation.desk_skipped` com a lista
   `missing`. Uma dessas duas linhas sempre aparece, e qual delas é a resposta
   direta a "este deployment sabe agir?".

---

## 8. Chaves de catálogo de mensagens

**Nenhuma.** Esta feature não precisou de nenhuma string de UI nova e não tocou
`console/src/i18n/*.ts`, `console/src/shell/routes.ts` nem
`console/visual/screens.json`.


---

## 9. Fase 8 — o cenário ponta a ponta, e o que ele mede

`tests/synthetic/test_the_proposal_and_the_act.py`, 10 testes, um incidente
contado uma vez: catálogo estreitado pela configuração **lida da árvore** (não
declarada ao runner), proposta com o desfazer carregando a contagem de réplicas
lida antes, nada movido, aprovação pela rota que um botão de console chama, a
carga escalada só então, e o resultado mais a obrigação gravados.

Cortando cada fio à mão, com o cenário no lugar:

| Fio cortado | Reprova |
|---|---|
| `_carry_out` na rota de decisão | **3 de 10** |
| `register(hooks)` do portão por run | **6 de 10** |
| `TeamCatalogueResolver` na seleção | **1 de 10** (o que mede o estreitamento) |

### A medida que o coordenador pediu, e o que ela diz

| Medida | Antes | Depois |
|---|---|---|
| `make test-synthetic` (o corpus, via `tests.harness`) | 5/5 (100%) | **5/5 (100%)** |
| `pytest -m synthetic` (a suíte marcada, dentro do `make verify`) | 253 passed | **263 passed** |

**O corpus continua 5/5 e continua sem exercitar o caminho novo — e isso não é o
cenário falhando em medir, é o corpus e o cenário serem duas coisas.**
`make test-synthetic` roda `python -m tests.harness` sobre `tests/corpus/`, e
esse harness constrói o próprio laço e o próprio catálogo; ele nunca chama
`ReActInvestigationRunner._select_tools`. Um cenário novo em `tests/synthetic/`
é um teste pytest e **não entra naquela contagem por construção**. O número que
se move é o da suíte marcada: 253 → 263.

A lacuna real que fica registrada: **o corpus de 5 cenários não cobre a
composição de serving.** Fechá-la de verdade seria dar ao harness a opção de
dirigir o investigador de serving em vez do próprio laço — trabalho de
instrumento, com dono fora desta feature, e maior do que a Fase 8 pedia.

---

## 10. Fase 9 — fechamento, reconferido numa segunda worktree (2026-08-24)

O `tasks.md` tinha 67 de 75 tarefas marcadas: T067–T071 e S01–S03 sem marcar,
sem uma linha dizendo por quê — exatamente o que motivou esta passagem. Esta
seção fecha T067–T071 e nomeia, com evidência, por que S01–S03 continuam sem
marcar. Nada foi implementado aqui: as cinco tarefas de fechamento são
rodar/comparar/registrar sobre um código que já existia; nenhum teste nasceu
vermelho.

Worktree desta passagem:
`/srv/workspaces/NinjaSRE/.claude/worktrees/agent-a927bb24f92594c3c`, ramo
`worktree-agent-a927bb24f92594c3c`. Nasceu apontada para o mesmo commit que o
cabeçalho deste arquivo descreve — o primeiro commit do repositório — e foi
reapontada com `git reset --hard master` antes de qualquer leitura, pela mesma
razão. Em `master` (`10a329c` no momento desta passagem) o merge desta
feature (`be39049`, trazendo `worktree-agent-ad2b3b198c83bd6f6` até `12b13dd`)
já estava presente, ao lado de commits de outras features da onda que
chegaram depois — entre eles `07f1dae` (`070-confianca-de-certificado`), que
muda o que a seção 6(a) afirmava (ver abaixo).

### T067 — suíte sintética, reconferida

- `uv run pytest -m synthetic -q` → **263 passed, 12541 deselected** — igual
  ao "depois" que a seção 9 já registra (253 → 263): **sem mudança**, mesmo
  depois de `07f1dae` e dos demais commits chegados desde a medição original.
- `make test-synthetic` (o corpus via `python -m tests.harness`) → **5/5
  (100%)** — igual ao antes e ao depois já registrados; o corpus continua sem
  tocar `ReActInvestigationRunner._select_tools`, pela razão que a seção 9 já
  dá.
- Efeito reportado: **nenhum sobre o corpus; +10 sobre a suíte marcada**,
  ambos medidos — "sem efeito" só depois desta comparação, como o `tasks.md`
  exige.

### T068 — verificação completa, reconferida

Rodada em partes, porque `make verify` sozinho excede o teto de uma chamada
de shell.

**Estático (Python)** — `make lint format-check typecheck check-imports
check-constants check-protocols check-deps check-vendor-sdks check-literals
check-raw-sql check-credentials check-console-boundary check-integrations
check-integration-docs check-env-example check-docs check-doc-examples` →
limpo nos quinze alvos: ruff, `ruff format --check` (2391 arquivos), mypy
(1323 arquivos-fonte), os sete contratos do `import-linter`, e cada
`tools/check_*`.

**Suíte Python (`make test`)** → **2 failed, 12720 passed, 45 skipped em
200,24s** — não reproduz literalmente o "exit 0 — 12386 passed" que a tabela
da seção 3 registrava. As duas falhas foram isoladas e **nenhuma nasce em
código desta feature**:

1. `tests/contract/fixtures/test_dataset_coherence.py::test_rebuilding_the_dataset_reproduces_what_is_committed`
   — `fixtures/scenarios/populated/capabilities.json` grava
   `"domain": "kelp.example.invalid"` para a entrada `estate.storage_pressure`;
   `tools.mockplane.dataset.build.write_all` reconstrói a mesma entrada com
   `"domain": "rushes.example.invalid"`. `"rushes"` é o literal que
   `tools/mockplane/dataset/served.py:226` usa hoje para o servidor MCP de
   exemplo; `"kelp"` não aparece em lugar nenhum da árvore atual — foi
   renomeado e o fixture não foi regenerado. O último commit a tocar esse
   arquivo foi `c3f5f90 feat(mockplane): serve each vendor's package
   documentation from the mock`, sem relação com portões de remediação ou de
   autonomia; o diff do merge desta feature (`be39049`) nunca tocou
   `fixtures/scenarios/`.
2. `tests/contract/cli/test_onboarding_against_a_deployment.py::test_the_deployment_reads_as_ready_once_the_flow_has_run`
   — `TypeError: build_checklist() got an unexpected keyword argument
   'verify_model'`. A assinatura real de `build_checklist`
   (`platform/startup/checklist.py:175`) não declara esse parâmetro; o teste
   não foi atualizado depois de `2cdd288 feat(providers): serve one readiness
   word from the listing and the checklist` (com `75e4e8f` logo antes),
   também sem relação com esta feature. Nenhum dos dois arquivos aparece no
   diff de `be39049`.

Nenhuma das duas foi corrigida aqui: a superfície é de outra feature da onda,
cujos agentes estão ativos nesta mesma árvore agora, e consertar dataset de
mockplane ou a leitura de prontidão de provedor está fora do que estas cinco
tarefas de fechamento pedem. A leitura correta: a alegação "exit 0" foi
verdadeira **no commit em que foi medida**; não é mais reproduzível
literalmente em `master` porque duas features distintas, mergeadas depois,
deixaram uma trilha cada — nenhuma delas nesta.

**Console, estático** — `pnpm install --frozen-lockfile` (2,7s, store já
mirrorado), depois `lockfile`, `format-check`, `lint`, `typecheck`: **os
quatro limpos**, como esperado — o merge desta feature não editou nenhum
arquivo de `console/`.

**Console, `test` (vitest)** — a primeira tentativa, através do wrapper
`pnpm` que `tools/console_gate.py` chama, foi morta por um `timeout` de 115s e
imprimiu só `Not implemented: navigation to another Document` seguido do aviso
de ciclo de vida do próprio `pnpm` interpretando o `SIGTERM` como falha — o
que parecia um travamento e não era. Rodando `vitest` direto, com
`--reporter=verbose`, a suíte mostrou estar avançando de verdade (centenas de
`✓`, zero `✗`, cada teste na casa dos milissegundos); é grande, não presa.
Levada até o fim em segundo plano (`npx vitest run --reporter=dot
--no-coverage`, sem o wrapper `pnpm`): **170 arquivos de teste passaram (170),
2796 testes passaram (2796)**, `exit 0`, 381,45s. A frase do jsdom era um
aviso dentro de um teste que passou, não uma falha — a primeira leitura
("trava") estava errada, e esta reconfirma o gate como verde.

**Console, `build`/`e2e`/`visual`** — **não rodados.** `e2e` e `visual` são
Playwright contra baseline de captura de tela, cuja aceitação não é automática
por definição (é o próprio motivo que o mandato desta sessão reconhece como
legítimo para deixar algo sem rodar); `build` não foi necessário porque a
suíte Python de hoje não tem nenhuma falha ligada à ausência do artefato
`console/.next/standalone` — ao contrário da linha de base de T001, que
precisou dele para três testes que hoje passam sem ele (o compose de
implantação evidentemente já não depende de um build local nessa mesma
forma). Rodar os três exercitaria uma superfície que esta feature não toca,
com o mesmo risco de colidir com os agentes de console ativos agora.

### T069 — inventário refeito

`RemediationGate(`, hoje — idêntico ao "depois" da seção 1, nenhuma ocorrência
nova, nenhuma perdida:

| Ocorrência | O que é |
|---|---|
| `gateway/http/remediation.py:130` | **produção**, dentro de `RemediationDesk.gate_for` |
| `tests/unit/platform/remediation/test_gating.py:154` | teste de unidade |
| `tests/unit/platform/remediation/test_no_unapproved_write.py:82` | teste de unidade |
| `tests/synthetic/test_first_investigation.py:238` | cenário sintético |
| `tests/contract/autonomy/test_the_gate_obeys_the_policy.py:205` e `:379` | teste de contrato |

`AutonomyGate(`, hoje: produção em `platform/autonomy/service.py:153`
(inalterada), plano de dados de mentira em
`tools/mockplane/dataset/served.py:3321` (linha deslocada de `:3087` por
inserções anteriores no arquivo — mesma construção), e **28** ocorrências sob
`tests/` (a seção 1 registrava 24; a diferença é teste de autonomia chegado
depois por outra feature da onda — nada some, e a única ocorrência de
produção continua sendo uma e continua alcançável de uma investigação pela
cadeia que a seção 1 já documenta:
`gateway/http/remediation.py:287 → :241 → :137 →
platform/remediation/gating.py:306`).

Confirmado de novo: **ao menos uma ocorrência de produção de cada portão,
alcançável da composition root de serving** — o próprio SC-001.

### T070 — recusa direta, reconfirmada

`uv run pytest tests/contract/remediation/test_the_direct_call_still_refuses.py -q`
→ **43 passed**, mesma contagem da seção 3 e do dia da implementação. O
próprio arquivo declara que toda recusa sai como a mesma sentença
(`capabilities/tools/remediation/_base.py::UNGATED_REFUSAL`) com classe de
erro `PERMISSION_DENIED`; nem o teste nem `_base.py` mudaram desde o merge
desta feature. Fail-closed intacto.

### T071 — declaração para o merge do slot

**Nenhuma chave de catálogo de mensagens nova.** Confirmado de novo por diff:
`git diff f0b969e be39049 --stat -- console/src/i18n/
console/src/shell/routes.ts console/visual/screens.json` não devolve nenhuma
linha — os três arquivos de escrita única do console seguem intocados pelo
merge desta feature.

Uma correção à nota (e) da seção 6: `console/src/api/schema.ts` **foi**
regenerado pelo merge (12 linhas), ao contrário do que a nota original disse.
A mudança inteira é a descrição publicada da rota de decisão de aprovação — a
docstring nova de `gateway/http/routes/approvals.py`, propagada pelo OpenAPI
— e nenhuma interface, tipo ou campo mudou. `schema.ts` não é um dos três
arquivos de escrita única que esta feature está proibida de tocar: é gerado a
partir do contrato, e o contrato mudou porque a docstring da rota mudou
legitimamente. A frase "não foi regenerado" da nota (e) estava errada; a
distinção que importava — nenhum tipo mudou — estava certa.

### O que isto muda para a seção 6(a)

`07f1dae feat(remediation): bind the control plane a hypervisor write
actually reaches` (feature `070-confianca-de-certificado`, já em `master`
antes desta passagem) liga `ProxmoxControlPlane` a partir do mesmo cliente e
documento que `compose_discovery_sources` já usa —
`gateway/http/control_plane.py`, chamado em `gateway/http/lifespan.py:100`,
**antes** de `compose_remediation` em `:105`. O bloqueio que a seção 6(a)
nomeava — "sem plano de controle ligado, o balcão não compõe" — **deixa de
valer em código** a partir deste commit, para qualquer deployment com Proxmox
configurado e verificado, como o staging já está
(`specs_v7/070-confianca-de-certificado/evidence/staging-2026-08-24.md`).

Isto não fecha S01–S03 sozinho: o que essas três tarefas medem é o staging
*depois do ciclo de deploy do slot*, e se o processo hoje rodando em
produção já carrega este commit é pergunta que só o orquestrador responde (a
seção 7 original já dizia isso). O que muda é que a razão pela qual a
contagem provavelmente dava zero deixou de valer no código; se ainda der zero
depois do próximo deploy, a causa já não é esta.

### S01–S03 — por que seguem sem marcar

Não são tarefas do implementer no `tasks.md` original, e esta passagem não
muda isso — só confirma, com evidência, cada razão:

- **S01** exige disparar uma investigação real contra o staging
  compartilhado — uma escrita no ambiente que o mandato desta sessão proíbe
  explicitamente. Tentei a leitura autenticada de `/v1/approvals` que a spec
  descreve como prova: `POST $NINJASRE_STAGING_URL/v1/auth/sign-in`
  (a rota real é `gateway/http/routes/identity.py:288`, montada em
  `/v1/auth/sign-in`) devolve `307` para `/sign-in?from=%2Fv1%2Fauth%2F...`
  mesmo com `Accept: application/json` e `X-Requested-With: XMLHttpRequest` —
  a URL pública serve o console (Next.js), que intercepta a chamada antes de
  alcançar a API; a troca por sessão autenticada não é algo que dá para fazer
  por `curl` sem reproduzir o fluxo do navegador. Não existe
  `specs_v7/040-decisao-composta/evidence/` (ao contrário de `070`, que já
  tem `evidence/staging-2026-08-24.md`), o que confirma que o "checkpoint do
  laço mínimo" do fim do S2 que `specs_v7/EXECUCAO.md` §3 descreve — alerta
  real → investigação → proposta em Decisions, evidência anexada antes de
  abrir o S3 — ainda não rodou para esta feature.
- **S02 e S03** são contagens SQL contra o banco do staging. `.env` só
  carrega `NINJASRE_STAGING_URL`, `NINJASRE_STAGING_USERNAME` e
  `NINJASRE_STAGING_CREDENTIAL` — uma credencial HTTP, não uma de banco — e
  este ambiente não tem `kubectl` nem nenhum outro caminho até o cluster.
  Não é uma questão de permissão: não há caminho técnico daqui até o banco.
  São, como o próprio `tasks.md` já dizia, do orquestrador, depois do ciclo
  de deploy do slot.