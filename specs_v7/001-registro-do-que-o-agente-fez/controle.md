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
   da onda, não uma medição desta feature. O "depois" é medido.
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

## Reconciliação de `tasks.md`

Os marcadores de `tasks.md` **não foram marcados pelo implementer**: ele rodou
em worktree, onde este diretório não existe. Foram reconciliados pelo
orquestrador contra o relatório e o código, e as tarefas de evidência em
staging (a investigação de prova e as contagens) ficaram **desmarcadas** de
propósito — ver pendência 1.
