# Controle — 080-incidente-fecha-o-laco

**O estado abaixo foi verificado contra o código atual da árvore mergeada**, na
worktree `agent-a639a9cf04385754f`, partindo de `4f438f7` (ponta de `master`).

Nota de execução: a worktree nasceu apontada para o **commit raiz** do
repositório (`c789c2d`, "Add initial README") — sexta ocorrência do mesmo
defeito de provisionamento nesta onda. Reapontada com `git reset --hard master`
antes de qualquer trabalho.

## A fronteira desta execução, declarada antes do trabalho

- **Desta feature:** os três roteiros, o coletor de evidência com teste, a
  coluna nova do confronto, o backlog reescrito, e a suíte transversal
  determinística.
- **Do orquestrador:** toda evidência de ambiente real — cluster, Postgres de
  staging, Alertmanager, e a janela do laço inteiro com um humano aprovando.
  Esta worktree não alcança nenhum deles, e **não inventou um único número de
  staging**. A lista exata do que medir está na última seção, comando por
  comando.

## Commits, em ordem

| Commit | Conteúdo |
|---|---|
| `a0bfa74` | `docs(demo)` — os dois roteiros e o gabarito de evidência, antes da demo |
| `ca3c4be` | `feat(demo-evidence)` — o coletor: a consulta e a saída literal |
| `261c6d7` | `docs(wave)` — a coluna "quem constrói isso em produção?", lida do código |
| `1d4b68b` | `docs` — `backlog.md` reescrito em torno do que continua aberto |
| `4778f91` | `refactor(demo-evidence)` — cada instrução no seu próprio arquivo `.sql` |
| `8f0d756` | `feat(demo-evidence)` — contar os runs anteriores à coluna de manchete |
| `aeb0dd6` | `docs(demo)` — o roteiro de navegador, com o que cada tela deve dizer |

---

## Ledger

Convenção: **FEITO** · **FEITO (já existia, verificado)** · **PARCIAL** ·
**NÃO INICIADO** · **Do orquestrador (ambiente real)**.

### Fase 1–2 — pré-voo e aptidão do ambiente (T001–T016)

| Peça | Estado | Detalhe |
|---|---|---|
| T001–T006 — publicar, Argo, serviço respondendo | **Do orquestrador** | Feito por ele durante esta sessão: as nove features mergeadas, `Synced/Healthy`, rotas aquecidas |
| T007–T016 — aptidão do ambiente | **Do orquestrador** | Cada item tem comando na última seção. A worktree não alcança cluster nem banco |

### Fase 3 — os roteiros e o gabarito (T017–T026, T033)

| Peça | Estado | Detalhe |
|---|---|---|
| T017 roteiro do laço de leitura | **FEITO** | `runbooks/laco-de-leitura.md` — pré-condições, E1–E7, URLs reais, sem escrita e sem janela |
| T018 roteiro do laço inteiro | **FEITO** | `runbooks/laco-inteiro.md` — o que ele não é, a vítima com as duas condições, o estado inicial, o passo destrutivo, E1–E10 |
| T019 tabela de estações | **FEITO** | `laco-de-leitura.md` §3; `laco-inteiro.md` §4 |
| T020 classificação de desfechos, antes da execução | **FEITO** | `laco-de-leitura.md` §4; `laco-inteiro.md` §5 — ambiente × produto, com a dona nomeada e a regra que separa os dois |
| T021 reversão manual **antes** do passo destrutivo | **FEITO** | `laco-inteiro.md` **§1**, antes de §6 |
| T022 aprovação humana, pela interface | **FEITO** | `laco-inteiro.md` §6 passo 10 e cabeçalho |
| T023 não aprovar antes de conferir E4–E7 | **FEITO** | `laco-inteiro.md` §6 passo 9, com a razão |
| T024 rejeição em ocorrência diferente | **FEITO** | `laco-inteiro.md` §7 |
| T025 esqueleto de `EVIDENCIA.md`, em branco | **FEITO** | `evidence/EVIDENCIA.md` — 8 seções, todo campo vazio, com o aviso de que é gabarito |
| T026 varredura de segredo nos roteiros | **FEITO** | Varredura por padrão nos três arquivos: nenhuma ocorrência |
| T033 comando do coletor no cabeçalho | **FEITO** | `laco-de-leitura.md` §1; `laco-inteiro.md` §0; `navegador.md` §15 |
| (a mais) roteiro de navegador | **FEITO** | `runbooks/navegador.md` — onde clicar e o que a tela deve dizer, na cópia real do catálogo |

### Fase 4 — o coletor (T027–T032)

| Peça | Estado | Detalhe |
|---|---|---|
| T027 `tools/demo_evidence/` | **FEITO** | `queries.py`, `collector.py`, `__main__.py`, `__init__.py`, `sql/` — 23 instruções em 8 estações |
| T028 as consultas mínimas | **FEITO, com três correções ao esboço** | ver "Correções à `tasks.md`" |
| T029 arquivo por estação, consulta + saída literal | **FEITO** | `collector.py::collect` e `file_name_for`; marcadores `--- output ---` / `--- end of output ---`; a saída é escrita byte a byte |
| T030 recusa de tudo que não seja `SELECT` | **FEITO** | `collector.py::only_select` — recusa `DELETE`/`UPDATE`/`INSERT`/`DROP`/`TRUNCATE`, recusa `WITH … DELETE … RETURNING`, e recusa duas instruções numa |
| T031 teste de unidade, vermelho antes | **FEITO** | `tests/unit/tools/test_demo_evidence.py` — **31 casos** |
| T032 nenhuma credencial impressa ou gravada | **FEITO** | nenhuma instrução nomeia `credentials`, `api_tokens`, `token_hash`, `local_password_hash`; travado por teste, e o comando de conexão nunca entra no arquivo de evidência |

### Fase 12 — o confronto ganha a coluna (T079–T083)

| Peça | Estado | Detalhe |
|---|---|---|
| T080 a coluna fixa | **FEITO** | `specs_v7/CONFRONTO.md`, seção "Quem constrói isso em produção?" |
| T081 preenchida para os mecanismos exigidos | **FEITO — 17 linhas** | recorder, gate de remediação, gate de autonomia, resolvedor de integrações do time, confiança de certificado até o egress, e mais doze |
| T082 dormentes declarados | **FEITO — 3** | pipeline por estágios, `DecisionWaiter`, leitura de sinal na execução. Nenhuma célula aponta um teste |
| T083 fecha citando a demo | **FEITO** | com o caminho da evidência e o veredito honesto: **não executado** |
| T079 seção por feature com veredito do verifier | **NÃO FEITO — e é do orquestrador** | O cabeçalho do próprio `CONFRONTO.md` diz que ele é medido pelo orquestrador e **não copiado do relatório de quem implementou**. Escrever vereditos de verifier que não medi seria exatamente o que aquele cabeçalho proíbe |

### Fase 13 — o backlog reescrito (T084–T088)

| Peça | Estado | Detalhe |
|---|---|---|
| T084 tabela de destino no confronto | **FEITO — 11 de 11** | `CONFRONTO.md`, "Backlog anterior → destino". Zero itens sem destino |
| T085 `backlog.md` reescrito | **FEITO — 14 itens** | 8 saíram com evidência; 4 vieram do anterior sem fechar; os demais são desta onda |
| T086 redação conferida | **FEITO** | varredura por `FR-`, `SC-`, `specs_v*`, `Article`, número de feature, caminho de planejamento: **nenhuma ocorrência**. `test_removed_vendor_references` e `test_no_committed_file_states_a_stale_catalogue_size` verdes |
| T087 forma preservada | **FEITO** | cada item: o que acontece hoje, por que não é trivial quando não é, e o desfecho pelo qual seria julgado |
| T088 nenhum item removido sem evidência | **FEITO** | conferido linha a linha na tabela de destino |

### Fases 5–11 — a demo

| Peça | Estado | Detalhe |
|---|---|---|
| T034–T036 o vermelho a seco contra o staging | **Do orquestrador** | O gabarito está de pé e as consultas foram provadas executáveis (ver abaixo); rodá-las contra o staging pré-demo é dele |
| T037–T044 laço de leitura executado | **Do orquestrador** | `runbooks/laco-de-leitura.md` |
| T045–T060 a janela | **Do orquestrador** | `runbooks/laco-inteiro.md` e `runbooks/navegador.md` |
| T061–T063 a rejeição | **Do orquestrador** | `navegador.md` passo 14 |
| T064–T068 tarefas operacionais | **Do orquestrador** | comandos na última seção |
| T069–T074 evidência consolidada | **Do orquestrador** | o gabarito está pronto para receber |
| T075–T078 achados | **Do orquestrador** | a seção existe em branco em `EVIDENCIA.md` |

### Fase 14 — fechamento

| Peça | Estado | Detalhe |
|---|---|---|
| T089 `make verify` completo | **NÃO RODADO — do orquestrador**, por instrução dele. Rodei os gates de tier equivalentes; ver "Gates" |
| T090 nenhum arquivo de produto alterado | **FEITO — conferido** | O diff desta feature toca **apenas** `tools/demo_evidence/`, `tests/unit/tools/test_demo_evidence.py`, `backlog.md`, `specs_v7/CONFRONTO.md` e o diretório da própria feature. Nada em `gateway/`, `platform/`, `core/`, `capabilities/`, `integrations/`, `config/` ou `console/` |
| T091 este arquivo | **FEITO** | |

---

## O vermelho, com a mensagem real

O único código que esta feature escreve é o coletor, e ele nasceu vermelho:

```
tests/unit/tools/test_demo_evidence.py:24: in <module>
    from tools.demo_evidence import (
E   ModuleNotFoundError: No module named 'tools.demo_evidence'
=========================== short test summary info ============================
ERROR tests/unit/tools/test_demo_evidence.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
```

Depois da implementação: **31 passed em 0,10s**.

**O análogo do test-first para o resto da feature é o gabarito antes da
execução**, e ele foi respeitado: os roteiros e `EVIDENCIA.md` aterrissaram em
`a0bfa74`, com todo campo em branco, antes de qualquer passo da demo.

---

## As 23 consultas rodaram contra um PostgreSQL real, com o schema de verdade

O maior risco deste coletor é uma consulta que não roda, descoberta às onze da
noite com a janela aberta e o contêiner parado. Medido em vez de suposto:

1. `docker run ninjasre-postgres-test:16` — a mesma imagem que a suíte de
   contrato de persistência usa, com pgvector e AGE;
2. `alembic upgrade head` com o `alembic.ini` do repositório — **o schema é o
   que as migrações produzem**, não um `create_all` aproximado;
3. o coletor, com todos os parâmetros preenchidos, através de um `psql` real
   com `ON_ERROR_STOP=1`.

**Resultado: 8 arquivos, zero ocorrências de "could not run this query".** As
23 instruções executaram.

O caminho de falha foi conferido **separadamente**, porque zero falhas só vale
alguma coisa se as falhas fossem visíveis: `SELECT no_such_column FROM
run_turns` faz o `psql` sair com código 3, o que levanta em `ShellFreeRunner` e
vira um bloco de recusa no arquivo. Os zeros são reais, não invisibilidade.

Contêiner removido; nada ficou de pé.

---

## Correções à `tasks.md`, medidas contra o schema

A `tasks.md` esboça as consultas. Três coisas nela não sobreviveriam ao schema
real, e uma quarta correção veio da onda:

1. **`SELECT index, … FROM run_turns`** — `index` precisa de aspas (`"index"`).
2. **`remediation_outcomes`** tem muito mais que `capability, resource_id,
   state, due_at`: `verdict`, `rollback`, `autonomous`, `executed_at`, `run_id`,
   `incident_id`. **`autonomous` é o campo que responde à alegação de que nada
   agiu sem decisão humana**, e virou consulta própria (`E8/nothing-executed-unattended`).
3. **`incidents` ganhou `public_id`** nesta onda. Toda consulta de incidente
   resolve **as duas grafias** — endereço curto e id interno — porque o que o
   operador tem na mão é o que está na URL.
4. **O vocabulário não é digitado.** `APPROVAL_AUDIT_RESOURCE_KIND_REQUEST`
   (`config/constants/security.py:737`), `REMEDIATION_AUDIT_RESOURCE_KIND`
   (`:813`) e `ApprovalState.REJECTED`
   (`platform/persistence/ports/approval_store.py:25`) chegam à instrução como
   parâmetro, resolvidos dos módulos que os declaram. Uma consulta não pode
   continuar perguntando por uma palavra que o produto deixou de usar — ela
   rodaria perfeitamente e devolveria nada, que se lê como evidência de
   ausência. Travado por teste.

### E1, E2 e E6 não têm consulta, e isso é deliberado

O que prova essas três é um roteador de alertas, uma tela de intake e um
transcript — nenhum deles é linha deste banco. Inventar uma consulta para elas
seria medir a coisa adjacente e chamar de resposta, que é o defeito que esta
onda existe para não repetir. Está escrito em `queries.py`, ao lado de
`STATIONS`.

---

## Gates rodados, resultado real

| Gate | Comando | Resultado |
|---|---|---|
| Teste do coletor | `pytest tests/unit/tools/test_demo_evidence.py` | **31 passed** |
| Ferramentas + arquitetura | `pytest tests/unit/tools tests/architecture` | **734 passed** |
| Lint (repositório) | `ruff check .` | **All checks passed** |
| Formatação (repositório) | `ruff format --check .` | limpo |
| Tipos | `mypy tools/demo_evidence tests/unit/tools/test_demo_evidence.py` | **Success: no issues found** |
| Constantes | `python tools/check_constants.py` | exit 0 |
| SQL fora da persistência | `python tools/check_raw_sql.py` | exit 0 |
| Credencial direta | `python tools/check_direct_credentials.py` | exit 0 |
| Deriva de documentação | `python -m tools.check_docs_drift` | exit 0 |
| Exemplos documentados | `python -m tools.test_doc_examples` | **29 documented example(s) check out** |
| Paridade do catálogo | `python -m tools.verify_integrations` | **15 integration(s) at full parity, every permission probed** |
| Contratos de import | hook de commit, em todos os commits | Passed |
| **Suíte transversal, determinística** | `spec_validation browser --feature specs_v7/080-… --test console/tests/e2e/transversal-rules.spec.ts` | **exit 0 — 45 passed, 7 skipped** |

Sobre a transversal: `EXCEPTIONS` em `transversal-rules.spec.ts:226` está
**vazia**, conferido lendo a linha. Não há rede: qualquer regressão de tela
apareceria como falha nova. Não apareceu. Os 7 pulados são o conjunto
preexistente de delegação de orçamento de rolagem, medido em
`scroll-budget.spec.ts`, e não têm relação com allowlist.

**Não rodado:** `make verify` completo (é do orquestrador, na árvore mergeada),
e qualquer coisa contra staging real.

---

## Um gate que falhou, e era meu

`tests/unit/tools/test_check_raw_sql.py::test_the_repository_writes_no_query_outside_the_storage_tree`
falhou com **22 violações**, todas em `tools/demo_evidence/queries.py`:

```
E   AssertionError: assert [Violation(pa...iteral'), ...] == []
E     Left contains 22 more items, first extra item:
E     Violation(path=…/tools/demo_evidence/queries.py, line=75,
E               detail='SELECT public_id, title, state, severity, origin, origin_id,…',
E               rule='sql-literal')
```

O detalhe que importa: **o CLI do guarda passava e o teste não.**
`tools/check_raw_sql.py` exclui `tools/` dos seus roots padrão, e o teste varre
a árvore inteira. O teste é o mais estrito dos dois, e é o que `make verify`
também roda.

Havia a tentação de argumentar — o plano desta feature declara, com todas as
letras, que o coletor é instrumento de verificação e não caminho de produto — e
argumentar teria sido afrouxar um guarda para caber o meu código. A instrução
foi obedecida: **cada instrução foi para o seu próprio arquivo `.sql`**, em
`tools/demo_evidence/sql/`, e o módulo Python lê o arquivo. O guarda ficou
intacto, e o SQL ficou melhor — um arquivo se cola numa sessão e se compara
num diff sem as aspas no caminho.

---

## Descobertas que mudam como ler a árvore daqui em diante

**(a) Três `file:line` dos controles anteriores já estavam defasados.** A 040
declarou `compose_remediation` em `gateway/http/lifespan.py:92`; a 070 declarou
`compose_control_plane` em `:98` e `compose_remediation` em `:107`. Na árvore
mergeada eles estão em **`:100`** e **`:105`**. Cada merge empurrou as linhas.
A coluna do confronto foi preenchida **lendo o código**, não copiando relatório,
e é por isso que ela está certa.

**(b) Aprovar sem plano de reversão devolve `400`, não `500` nem sucesso.**
`gateway/http/routes/approvals.py:317-322` — `RecordNotFound` é alcançado
apenas ao aprovar sem plano gravado, e vira `bad_request`. A ordem "o plano de
reversão está registrado antes da execução" **não depende de ninguém lembrar
dela**: é estrutural.

**(c) A rota de decisão devolve sucesso mesmo quando a execução falha**, de
propósito e com a razão escrita no docstring: uma falha em agir é um fato sobre
o deployment, e transformá-la em erro diria ao revisor que a decisão dele não
foi registrada quando foi. **Consequência prática para quem observa: a tela
dizendo "Approved" não é evidência de que a ação rodou.** Quem responde isso é
`remediation.approval_carried_out` no log. Está escrito no roteiro de navegador,
porque é a leitura errada mais fácil de fazer no dia.

**(d) Rejeitar sem motivo é impedido por um controle desabilitado, não por uma
mensagem de erro.** `console/src/surfaces/screens/incident-decision-controls.tsx`
— o botão **Reject** fica `disabled` enquanto o campo *Reason* estiver vazio, e
ao lado aparece "A reason is required to reject.". Quem esperar um erro depois
do clique vai concluir que a tela está quebrada.

**(e) A ordem no servidor, para a estação E8.** Decisão gravada e transação
fechada (`approvals.py:303-325`) → evento de auditoria (`:326`, com
`action = approval.decide`, `outcome = allowed` para aprovar e `denied` para
rejeitar) → **só então** `_carry_out` (`:339`). A alegação "a decisão é
registrada antes de qualquer efeito" é verificável linha a linha.

**(f) Hipótese, não veredito, sobre as duas regras transversais que falham
contra o staging.** A fixture só tem runs com manchete; o staging tem 37 runs
de antes de a coluna existir, com manchete vazia e `summary` começando com
`###`. A suíte abre o **primeiro run da lista** — provavelmente um run velho — e
mede o caminho de fallback. A consulta `E5/headline-coverage` foi acrescentada
ao coletor exatamente para transformar isso em número. **O run da demo é novo e
recebe manchete no fechamento**, então E5 deve passar para ele; se falhar **para
o run da demo**, aí é defeito de produto com dona.

**(g) Quatro capacidades somem quando o balcão compõe.**
`alertmanager_acknowledge_incident`, `propose_knowledge`,
`pushover_post_message`, `telegram_post_message` declaram nível acima de leitura
sensível e não têm componentes de remediação. Com o balcão composto elas deixam
de ser oferecidas a um turno — o filtro fazendo o que deve. É **mudança de
comportamento visível**, e entrou no backlog novo em vez de virar surpresa.

---

## O que fica pendente, nomeado, não escondido

| Item | Estado | Dono |
|---|---|---|
| **Toda a demo** — Fases 5 a 11: o vermelho a seco, o laço de leitura, a janela, a rejeição, a evidência consolidada, os achados | **NÃO EXECUTADO.** Os três roteiros, o gabarito e o coletor estão de pé; o que falta é rodar contra o ambiente real | orquestrador |
| **T079 — seção por feature no confronto**, com o veredito de cada verifier | **NÃO FEITO, deliberadamente.** O cabeçalho do `CONFRONTO.md` declara que ele é medido pelo orquestrador e não copiado de relatório; escrever vereditos que não medi violaria isso | orquestrador |
| **T089 — `make verify` completo** | **NÃO RODADO**, por instrução | orquestrador |
| **Screenshots** (`evidence/telas/`) | **Diretório criado, vazio.** Nenhuma captura é possível desta worktree | orquestrador |
| **As três tarefas operacionais** — resolução de nomes, sincronização de segredo gerenciado, chave do gateway de modelos | **NÃO VERIFICADAS.** Entraram no backlog novo descritas pelo desfecho que as julga, sem afirmar se estão feitas — porque eu não posso medir. Se estiverem feitas, o item sai com a evidência | orquestrador |
| **A coluna do confronto para features futuras** | as 17 linhas cobrem o que esta onda entregou; um mecanismo novo precisa de linha nova | próxima onda |

---

# O QUE O ORQUESTRADOR PRECISA MEDIR NO AMBIENTE REAL

Comando por comando. Esta é a seção que decide se o laço fechou.

## 0. O parâmetro que tudo mais depende

Toda consulta é escopada por organização. Sem este valor nada roda:

```sh
ssh root@192.168.68.159 "kubectl exec -i -n k3s-stg-ninjasre deploy/app -- sh -c 'psql -X -q -v ON_ERROR_STOP=1 \"\$NINJASRE_DATABASE_URL\"'" <<'SQL'
SELECT org_id, name FROM organisations;
SQL
```

Guarde como `<ORG_ID>`.

## 1. As consultas — todas, por um comando só

**Ver o SQL sem tocar em banco nenhum:**

```sh
uv run python -m tools.demo_evidence plan --org <ORG_ID> --run <RUN_ID> --incident <INCIDENT_ID>
```

**Executar e gravar a saída literal, um arquivo por estação:**

```sh
uv run python -m tools.demo_evidence collect \
  --org <ORG_ID> --run <RUN_ID> --incident <INCIDENT_ID> \
  --approval <APPROVAL_ID> --resource <RESOURCE_ID> \
  --out specs_v7/080-incidente-fecha-o-laco/evidence/consultas \
  --exec "ssh root@192.168.68.159 kubectl exec -i -n k3s-stg-ninjasre deploy/app -- sh -c 'psql -X -q -v ON_ERROR_STOP=1 \"\$NINJASRE_DATABASE_URL\"'"
```

`--exec` é dividido em argumentos por `shlex` e executado diretamente: nenhum
shell **desta** máquina o vê. O único shell envolvido é o `sh -c` de dentro do
pod, que resolve a variável com a string de conexão. O SQL viaja pela **entrada
padrão**, então não aparece numa listagem de processos, e nenhuma senha entra no
arquivo de evidência.

Sem `--approval` e sem `--resource`, as consultas que precisam deles saem
marcadas `NOT COLLECTED` nomeando qual faltou — **nada é perguntado ao banco**.
Isso é o esperado nas primeiras passagens.

**Rode duas vezes: antes da demo e depois.** A primeira é o vermelho — os
valores de partida — e sem ela a segunda não tem contraste.

### O que cada consulta responde, e o valor de partida

| Estação / consulta | O que decide | Partida |
|---|---|---|
| `E3/incident` | o incidente existe, é endereçável, e tem título em vez de id | detalhe irrecuperável |
| `E3/estate` | `count(*)` de `estate_resources` presentes | **0** |
| `E3/subject` | o recurso que o incidente aponta está no estate | nenhuma linha |
| `E4/turns` | `count(*)` de `run_turns` para o run | **0**, em 37 runs concluídos |
| `E4/tool-calls` | `count(*)` de `tool_calls` | **0** |
| `E4/evidence` | `count(*)` de `evidence` | **0** |
| `E4/trace-events` | `count(*)` de `trace_events` para o run | 73 no total da instância |
| `E4/cost-per-turn` | `usage` turno a turno; sem preço é **vazio**, não zero | nenhum turno |
| `E4/what-each-call-returned` | o que cada chamada devolveu, na ordem gravada | nenhuma linha |
| `E5/sentence-and-document` | a manchete **não** abre com sintaxe markdown e o documento ainda abre | todo `summary` recente começava com `###` |
| `E5/headline-coverage` | quantos runs são anteriores à coluna — **a leitura que explica as duas regras transversais** | todos |
| `E7/proposal` | exatamente uma proposta para o run, estado `pending` | nenhuma linha, para nenhum run |
| `E7/rollback-plan` | o desfazer gravado, e gravado antes | nenhuma linha |
| `E7/every-remediation-proposal` | quantas propostas de remediação o deployment já enfileirou | **0** |
| `E8/decision` | estado, decisor, instante e motivo | nenhuma linha |
| `E8/audit-of-the-decision` | a decisão na auditoria, com autor, ação, assunto e resultado | nenhuma linha |
| `E8/nothing-executed-unattended` | **tem de ser 0 no fim**: execuções sem decisão humana | 0 |
| `E9/outcome` | o desfecho para o recurso — falha nomeada também é desfecho | nenhuma linha |
| `E9/episode` | o episódio gravado para o run | nenhuma linha |
| `E10/timeline` | a entrada da ação na linha do tempo do incidente | nenhuma entrada de ação |
| `E10/incident-after` | o incidente carrega o desfecho, o run e a ação | parado no diagnóstico |
| `R/rejections` | a rejeição gravada com o motivo | nenhuma linha |
| `R/both-decisions-in-the-audit` | as duas decisões: `allowed` e `denied` | nenhuma linha |

## 2. O que procurar no log do processo

**A pergunta mais importante — este deployment sabe agir?**

```sh
ssh root@192.168.68.159 "kubectl logs -n k3s-stg-ninjasre deploy/app --since=24h | grep -E 'remediation\.(control_plane_bound|control_plane_skipped|desk_composed|desk_skipped)'"
```

Uma destas duas **sempre** aparece depois do boot:

- `remediation.control_plane_bound` (`integration`, `endpoints`, `trust`,
  `capabilities=13`) e então `remediation.desk_composed` (`capabilities`,
  `profile=kubernetes`) ⇒ **compôs**;
- `remediation.desk_skipped` com a lista `missing` ⇒ **não compôs**, e a lista
  diz qual peça falta. Anexe a lista; E7–E9 ficam **não exercidas**.

**A execução aconteceu?**

```sh
ssh root@192.168.68.159 "kubectl logs -n k3s-stg-ninjasre deploy/app --since=1h | grep -E 'remediation\.approval_(carried_out|not_carried_out)'"
```

Esta é a leitura que a tela **não** dá: a rota devolve sucesso mesmo quando a
execução falha (descoberta (c) acima).

**As ferramentas foram estreitadas pelas integrações configuradas?**

```sh
ssh root@192.168.68.159 "kubectl logs -n k3s-stg-ninjasre deploy/app --since=2h | grep -E 'tool_selection|integrations_unresolved|zero_integration'"
```

**Duas linhas que explicam um número que parece errado:**

```sh
ssh root@192.168.68.159 "kubectl logs -n k3s-stg-ninjasre deploy/app --since=2h | grep -E 'remediation\.(signals_unread|posture_unreadable)'"
```

- `remediation.signals_unread` ⇒ a obrigação de verificar foi gravada com os
  valores "antes" vazios. É a dormência declarada, não um defeito novo.
- `remediation.posture_unreadable` ⇒ a postura não pôde ser lida e foi tratada
  como a mais estrita. Silêncio nunca vira permissão.

**O gravador foi anexado?**

```sh
ssh root@192.168.68.159 "kubectl logs -n k3s-stg-ninjasre deploy/app --since=24h | grep -E 'integrations\.access_(composed|skipped)|investigation'"
```

## 3. As rotas a visitar, e o que se deve ver

O passo a passo com onde clicar está em `runbooks/navegador.md`. Em resumo:

| Rota | O que se deve ver |
|---|---|
| `/settings/models-providers` | provedor **Verified** |
| `/integrations` | Proxmox conectado; qualquer recusa por certificado traz **dois fingerprints**, nunca "no node answered" |
| `/resources` | recursos reais, com nome |
| `/incidents` | o incidente novo, com título que é frase |
| `/incidents/{endereço}` | URL sem `%3A`/`%40`/`%2B`; zero painéis "não foi possível preencher"; painel **"Proposed action"** |
| `/runs/{runId}` | **depois de recarregar**: transcript com N chamadas, custo por turno, nenhum controle de run vivo num run terminado, relato renderizado |
| `/decisions` aba **Actions** | a proposta real; se vazio, "Nothing is waiting on a decision" |
| `/agent` | as capacidades que este deployment pode usar |
| `/administration` aba **Audit** | `approval.decide` com `allowed` e com `denied` |

Redirecionamentos a conferir de passagem: `/investigations` → `/runs`, e
`/setup` → `/first-run`.

## 4. As três tarefas operacionais — verificar, nunca executar

```sh
# resolução de nomes, de dentro de CADA contêiner de monitoração
ssh root@192.168.68.159 'ssh <contêiner> "getent hosts stg-ninjasre.lan.kyo.ninja"'

# sincronização do segredo gerenciado
ssh root@192.168.68.159 'kubectl get infisicalsecret -A'

# chave do gateway de modelos: o provedor correspondente Verified em
# /settings/models-providers
```

Uma tarefa não concluída **não reprova a demo por si**. Ela marca **não
exercida** a estação que dependia dela, e o item continua no backlog novo. Se
estiver concluída, o item sai do backlog **com a evidência nomeada**.

## 5. A pergunta que fecha a onda

Ao fim, uma frase em `evidence/EVIDENCIA.md` §7, e ela só pode ser escrita
depois de todas as consultas acima:

> O laço fechou uma vez, com um humano assistindo, e as dez estações têm
> evidência anexada?

Se `E8/nothing-executed-unattended` não devolver `0`, a resposta é **não**,
qualquer que seja o resto.
