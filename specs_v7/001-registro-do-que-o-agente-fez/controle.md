# Controle — 001-registro-do-que-o-agente-fez

Estado verificado contra o código mergeado em `master`, não contra intenção.

**Como este arquivo foi escrito.** A feature rodou numa worktree isolada, onde
`specs_v7/` não existe (está no `.git/info/exclude`). O implementer entregou
este texto no relatório final e o orquestrador o gravou aqui após o merge do
slot. Os `file:line` abaixo apontam para a árvore principal.

Verificação independente: **PASS**, por `spec-verifier` em contexto limpo,
sobre o código mergeado.

## Peça | Estado | Detalhe

| Peça | Estado | Detalhe |
|---|---|---|
| Custo ausente nunca vira zero | FEITO | `platform/runs/recorder.py` — `RecordedTurn.cost: float \| None`; `record_turn` omite a chave quando não há custo |
| Leitura do custo ausente | FEITO | `platform/runs/replay.py` — `ReplayedRun.total_cost` soma só o precificado; `unpriced_turn_count` novo |
| Adaptador de gravação | FEITO | `platform/runs/recording.py` — `RunTraceRecordingHook` grava turno, chamadas e evidência numa unidade de trabalho por escrita |
| Registro de hooks aceita o gravador | FEITO | `core/pipeline/build.py:44` — `investigation_hooks(recorder=None)` registra em `ON_TURN_END` só quando recebe um |
| O runner compõe o gravador | FEITO | `gateway/runtime/investigator.py` — `attach_recording()`, `can_record`, `_recording_hook_for()` |
| **Composition root anexa o gravador** | **FEITO** | `gateway/http/asgi.py:172` — `investigator_of(...)`, ponto único de anexo, chamado por `build_deployment` (mesmo arquivo, boot) e por `gateway/http/runtime.py:42` `recompose_investigator` |
| O fio é testado | FEITO | `tests/architecture/test_serving_composes_the_recorder.py` chama a `investigator_of` **real** e afirma `can_record` — `_recording` só é escrito dentro de `attach_recording`, chamada só dentro de `investigator_of` |
| Comportamento, não só forma | FEITO | `tests/unit/gateway/runtime/test_investigation_trace_recording.py` roda uma investigação real e lê turnos e chamadas **de volta do store** |
| Um só escritor de recibo de alerta | FEITO | `gateway/runtime/recording.py` deletado inteiro; único call site em `gateway/http/orchestration.py`, provado por `tests/architecture/test_one_alert_receipt_writer.py`, que **caminha a AST** e não casa texto |
| Pipeline por estágios declara dormência | FEITO | `core/pipeline/build.py:85-92` — nomeia o caminho de produção que o ligaria |
| Sentença e documento | FEITO | `platform/runs/headline.py` — `synthesize_headline(*, alert_name, resource, objective)` **não pode** ler o documento: a assinatura não o recebe |
| Extração no fechamento real | FEITO | `gateway/http/orchestration.py:128` — no `finally` de `_drive`, cobrindo concluído, cancelado e falho |
| Contrato com `headline` e `report` | FEITO | `gateway/http/routes/investigations.py` — `summary` mantido e documentado como substituído |
| Coluna `headline` | FEITO | Migração `0015_run_headline`, reversível; porta, modelo, repositório e fake |
| Vínculo de incidente | FEITO | `IncidentStore.find_by_run` — porta, fake e Postgres com índice GIN (migração `0016_incident_run_ids_index`) |
| Recursos tocados | FEITO | `platform/runs/replay.py:274` — `touched_resources_of()`, heurística declarada sobre nomes de argumento |
| Contrato HTTP e cliente TS | FEITO | Regenerados **pelo orquestrador**, uma vez, a partir do código mergeado |

## A pergunta da régua

*Quem constrói o gravador em produção, e o teste pega se alguém desligar?*

`investigator_of` (`gateway/http/asgi.py:172`) é o ponto único. Só anexa quando
o runner que a configuração nomeia é o canônico. Seus dois únicos chamadores
são as duas composition roots reais — o boot e a recomposição após mudança de
configuração.

Se a chamada a `attach_recording` for removida, `can_record` fica falso e os
quatro testes daquele arquivo de arquitetura falham. O implementer confirmou
comentando a chamada à mão; o verificador confirmou o mesmo traçando a cadeia
de escrita de `_recording`.

## Evidência em staging — a tese, provada no ambiente real

As migrações subiram no deployment real (`0014 → 0015 → 0016`), aplicadas na
inicialização do processo e confirmadas no log do serviço.

**A linha de base da onda era `run_turns=0`, `tool_calls=0`, `evidence=0` com
37 investigações concluídas.** Lido do banco de staging depois do deploy deste
slot, por um único run:

| Tabela | Antes | Depois |
|---|---|---|
| `run_turns` | 0 | **5** (índices 1 a 5, do mesmo run) |
| `tool_calls` | 0 | **4** |
| `evidence` | 0 | **1** |

O processo subiu às 21:03:41Z; os turnos foram gravados entre 21:23:23Z e
21:23:39Z — **vinte minutos depois**, portanto pelo código deste slot. A
investigação não foi disparada por ninguém para a prova: veio de um alerta real
chegando pelo caminho de produção, que é a única forma de evidência que o
artigo novo da constituição aceita.

O mesmo run mostra a segunda entrega funcionando:

- `headline`: *"Weekly restore drill jobs for VMs 103, 115, and 140 on pve02
  exceeded their maximum execution window without successful completion"* — uma
  sentença, sem marcação;
- `summary`: começa com `### Findings and Evidence` — o documento continua
  sendo documento.

A separação entre a sentença e o documento existe no ambiente real, não apenas
no harness.

## O que fica pendente, nomeado, não escondido

1. **Contagens de partida do banco (o "antes") nunca foram capturadas** desta
   worktree, que não alcançava o banco. O "antes" usado acima é o do diagnóstico
   da onda, não uma medição desta feature. O "depois" é medido. Ver "Reconfronto
   (2026-08-24)" abaixo: o banco de staging é alcançável — `scripts/deploy/stg-psql`
   é o caminho — e uma sessão seguinte confirmou isso. A lacuna não é de acesso;
   é a janela do "antes" já ter fechado, o que nenhum acesso a mais consertaria.
2. **Migração contra PostgreSQL real**: o implementer não a exercitou (sem
   Docker no ambiente dele). O verificador independente **fechou esta lacuna**:
   rodou a cadeia inteira contra PostgreSQL 16 com pgvector e AGE, subindo até
   a cabeça, descendo até a base e subindo de novo, sem erro.
3. **Sub-agentes não ganham trace próprio.** A feature garante apenas que o run
   pai não absorve os turnos do filho. Fechar isso é escopo maior que o mandato.
4. **`resume()` não escreve o desfecho de volta ao trace** — lacuna
   pré-existente, nomeada no próprio docstring, não fechada aqui.
5. **Duplicação latente**: o prompt de entrega escreve o marcador da sentença
   como literal em vez de interpolar a constante que já existe. Consistentes
   hoje; divergem no dia em que uma mudar.
6. **Nenhuma entrada de allowlist transversal caiu por esta feature**, e isso
   está correto: as entradas descrevem o que a **tela** imprime, e esta feature
   é backend — ela produz `headline` e `report`, mas quem os consome é a feature
   de leitura do relato. A conta cai no slot seguinte. O orquestrador tinha
   atribuído cinco entradas a esta feature; o implementer mediu, discordou com
   evidência, e estava certo.

## Achado de integração, consertado pelo orquestrador no merge

Esta feature e a do outro lado do slot criaram migrações **com o mesmo número**,
ambas descendendo do mesmo pai — histórico ramificado, duas cabeças, e nada
conseguia migrar. A do outro lado foi re-parenteada; a cadeia voltou a ser
linear. Um número de revisão é recurso de escrita única entre features
paralelas, e o protocolo do slot não previa isso.

## Reconfronto (2026-08-24) — a única tarefa não marcada

`tasks.md` chegou a esta rodada com 53 de 54 tarefas marcadas — a auditoria
desta sessão é sobre a única que não está, **T003**: "Registrar as contagens
de partida direto do banco de staging, não de um documento: turnos, chamadas,
evidência e eventos de trace, no total e para os runs completed da última
hora. É o 'antes' que a evidência de fechamento compara." A caixa continua
vazia porque a tarefa continua genuinamente não feita — não por falta de
tentativa desta vez.

**As 53 peças marcadas FEITO foram reamostradas contra o código atual nesta
sessão, não aceitas do relatório anterior.** `RunRecorder.record_turn`
(`platform/runs/recorder.py:332-368`) confirma, lendo o corpo da função, que a
chave de custo só entra no `usage` quando `turn.cost is not None`
(linhas 349-350) — nunca um `0.0` de substituição. `synthesize_headline`
(`platform/runs/headline.py:106-127`) confirma pela própria assinatura
(`*, alert_name: str = "", resource: str = "", objective: str = ""`) que não
existe parâmetro por onde um documento chegaria. `ReplayedRun.total_cost` e
`.unpriced_turn_count` (`platform/runs/replay.py:144-156`) confirmam a soma
parcial e a contagem de turnos sem preço. `touched_resources_of`
(`platform/runs/replay.py:274-293`) confirma que a lista vem dos argumentos
gravados nas chamadas, nunca dos sujeitos declarados no alerta.
`gateway/runtime/recording.py` confirmado ausente da árvore (`test -f`
retorna código de saída de "não existe"). As migrações `0015_run_headline` e
`0016_incident_run_ids_index` confirmadas presentes, com a cadeia
`0013 → 0014 → 0015 → 0016` linear (um `revision`/`down_revision` por
arquivo, sem ramificação). O contrato
(`gateway/http/routes/investigations.py:46,49,53`) confirmado com `headline`,
`report` e `summary` como três campos distintos, o último documentado como
substituído. As suítes `tests/architecture/test_serving_composes_the_recorder.py`
e `tests/architecture/test_one_alert_receipt_writer.py`,
`tests/unit/gateway/runtime/test_investigation_trace_recording.py` (8 testes),
`tests/contract/runs/` (15 testes, as quatro suítes de contrato) e
`tests/unit/platform/runs/{test_headline,test_replay,test_recorder}.py`
(35 testes) rodaram limpas, isoladas do resto da árvore para evitar uma
colisão de nome de módulo `conftest` entre `tests/unit/platform/runs/` e
`tests/contract/runs/` que só aparece quando os dois são passados juntos numa
única invocação do pytest — artefato de invocação, não do código; cada
diretório roda limpo sozinho, e é assim que a suíte completa também os separa.
Nenhuma das 53 peças foi encontrada regredida.

**T003, resolução definitiva: continua sem poder ser feita — por uma razão só,
e ela é suficiente sozinha.**

**Correção.** Uma versão anterior desta seção, escrita mais cedo na mesma
sessão, dizia que o bloqueio era de acesso: que nenhuma sessão deste slot
tinha credencial de banco. Isso é falso e foi apontado pelo coordenador antes
de endurecer no registro. O banco de staging **é** alcançável: o repositório
carrega `scripts/deploy/stg-psql` (committed em `9f87ac6`), que lê
`NINJASRE_DATABASE_URL` do pod em execução a cada chamada — via `kubectl exec
-n k3s-stg-ninjasre deploy/app -- printenv NINJASRE_DATABASE_URL` — nunca
grava a credencial em lugar nenhum porque nunca precisa, e encaminha o que
sobra para `psql`. Uma sessão com acesso ao host de infraestrutura o usa
normalmente contra `ninjasre-stg-db`. É o caminho a seguir da próxima vez que
uma tarefa como esta aparecer, em vez de redescobrir que "não dá" quando dá.

**A razão real é a janela, não o acesso.** O "antes" que T003 pede já não
existe para ser lido, mesmo com o banco alcançável. As migrações
`0014 → 0015 → 0016` já estão vivas em staging e o recorder já vinha gravando
havia mais de um dia quando esta rodada de auditoria começou — a própria
seção "Evidência em staging" acima mede um run específico saindo de zero para
`run_turns=5, tool_calls=4, evidence=1`, num deploy que já aconteceu. Rodar a
consulta hoje devolveria o total de **hoje**, não o total de antes do deploy;
rotular isso de "antes" seria uma evidência fabricada — exatamente o que esta
feature existe para recusar em outro contexto (o custo ausente que não pode
virar zero).

Não há tarefa de código para fechar essa lacuna, e não há acesso que a feche
tampouco: é uma medição cuja janela passou antes que qualquer sessão de
auditoria existisse para olhar para ela. **Decisão que cabe a um humano ou ao
orquestrador**: aceitar o "antes" já registrado na própria spec (seção "Onde o
produto está hoje": 37 investigações `completed`, `run_turns=0`,
`tool_calls=0`, `evidence=0`, `trace_events=73`, verificado em 2026-08-23
contra o staging real) como o "antes" válido — é uma medição direta de banco,
só que feita um dia antes de T003 ter sido escrita como tarefa própria, e o
banco de hoje não tem mais como reproduzi-la, por mais acesso que a próxima
sessão tenha.

## Reconciliação de `tasks.md`

Os marcadores de `tasks.md` **não foram marcados pelo implementer**: ele rodou
em worktree, onde este diretório não existe. Foram reconciliados pelo
orquestrador contra o relatório e o código, e as tarefas de evidência em
staging (a investigação de prova e as contagens) ficaram **desmarcadas** de
propósito — ver pendência 1.
