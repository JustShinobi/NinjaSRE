# Controle — Decisão composta

**O estado abaixo foi verificado contra o código atual**, na worktree
`/srv/workspaces/NinjaSRE/.claude/worktrees/agent-ad2b3b198c83bd6f6`
(ramo `worktree-agent-ad2b3b198c83bd6f6`), partindo de `928c342`.

Nota de execução: a worktree nasceu apontada para o **primeiro commit do
repositório**, não para `master`. Foi reapontada com `git reset --hard master`
antes de qualquer trabalho; sem isso a feature teria sido escrita contra uma
árvore com um único arquivo.

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