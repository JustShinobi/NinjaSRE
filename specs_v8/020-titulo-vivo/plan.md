# Implementation Plan: Título vivo — o run chama-se pelo assunto desde o primeiro evento

**Branch**: `feat/v8-020-titulo-vivo` · **Spec**: [spec.md](spec.md) ·
**Slot**: S3, pareada com 050-painel-vivo (EXECUCAO.md §1)

## Summary

O objetivo digitado passa a ser gravado na linha do run e a coluna `headline`
passa a nascer preenchida — com o objetivo (run manual) ou com
"{alertname} on {recurso}" (run de alerta) — em vez de esperar a entrega. A
leitura para de inventar títulos ("interactive investigation",
"investigation triggered by <hex>") porque a função que os inventava é
removida, não contornada. A lista ganha o último estágio completado por run,
em uma consulta, para as barras de progresso do board.

Tudo aqui reusa mecanismo existente: `synthesize_headline` e
`resource_from_labels` (v7) para o provisório, a coluna `headline` (0015)
para o armazenamento, `STAGE_COMPLETED` (já gravado) para o estágio. O que a
feature cria: uma coluna (`objective`), um método de store
(`last_completed_stages`), dois campos de resposta, e três bans na
transversal.

## Technical Context

- Escrita: `platform/persistence/ports/run_trace_store.py` (dataclass + port),
  `platform/persistence/postgres/` (store), `platform/persistence/fakes/
  run_trace_store.py`, `platform/persistence/migrations/versions/0020_*.py`,
  `platform/runs/recorder.py`, `gateway/http/orchestration.py`,
  `gateway/http/routes/investigations.py`, `platform/scheduler/executor.py`
  (novo parâmetro), testes de contrato/unit correspondentes, e **um** arquivo
  de teste transversal em `console/tests/e2e/`.
- Não-escrita: nenhuma tela, nenhum componente, nenhum arquivo single-write
  do console (i18n, routes.ts, screens.json) — dona do slot é a 050.
- Artefatos regenerados: `fixtures/contract/openapi.json`,
  `console/src/api/schema.ts`.

## Constitution Check

*GATE: precisa passar antes da execução. Reconferir ao final.*

| Artigo | Como este plano satisfaz |
|---|---|
| I — Evidência sobre asserção | O título provisório deriva do objetivo/labels redigidos e o estágio deriva de `trace_events`; nenhuma tela inventa assunto ou progresso. |
| II — Autonomia limitada | Não cria ação nem altera a decisão do agente; só nomeia e lê runs. |
| III — Leitura por padrão | A única escrita nova é o objetivo sanitizado e o headline na criação do run; não há escrita implícita em leitura. |
| IV — Segredo nunca chega ao agente | Redaction acontece antes de headline, evento, prompt, trace, API e relatório; labels também são sanitizados e nenhum teste grava segredo. |
| V — Um runtime canônico | Não toca o runtime nem a produção de avaliações. |
| VI — Neutralidade de provedor | Usa apenas `synthesize_headline`; não importa SDK nem expõe provedor. |
| VII — Aprendizado é medido | Não altera mecanismos de aprendizado nem suas métricas. |
| VIII — Arquitetura em camadas | Persistência permanece nas portas/repositorios; recorder e gateway compõem o dado; console consome o cliente gerado. |
| IX — Capacidades declaradas | Nenhuma capacidade nova de agente. |
| X — O operador é dono dos dados | Não há transmissão externa; o objetivo persistido é sanitizado antes de qualquer writer. |
| XI — Datastore único | A coluna e a consulta usam o `RunTraceStore`, migração reversível e fake/Postgres em contrato. |
| XII — Test-first, rastreado | Contratos de headline, redaction, estágio e limite de consultas nascem vermelhos e deixam evidência. |
| XIII — Idioma e atribuição | Código e paths novos em inglês; títulos de UI usam o catálogo `en`/`pt-BR`; nenhum segredo é commitado. |
| XIV — Composto ou não foi entregue | `start_run`, listagem e detalhe são caminhos servidos pelo gateway; o acceptance mede o dado no staging. |

### Qual composition root constrói isto

Nenhum mecanismo novo dormente: `start_run` é chamado no caminho servido por
`gateway/http/orchestration.py::start_investigation` (rotas + webhook), o
método novo de store é chamado por `list_investigations`/detalhe no mesmo
request path, e a migração roda no startup já composto. Artigo XIV satisfeito
por construção — cada linha nova tem chamador em rota servida, e o acceptance
contra staging o prova com a API real.

### Complexity Tracking

Sem abstração nova. Um campo, um método de consulta, parâmetros novos em
função existente. A tentação a recusar: um "TitleService" — o título é um
dado gravado e um fallback de leitura, não um serviço.

## Project Structure

```
specs_v8/020-titulo-vivo/
├── spec.md
├── plan.md
├── tasks.md
└── evidence/            # criado na execução: logs, contagens, respostas JSON
```

## Decisões de design

### 1. O provisório mora na mesma coluna que o definitivo

`headline` (0015) passa a ser escrita duas vezes: no `start_run` (síntese do
assunto sanitizado) e no `complete_run` (sentença da entrega, que
**sobrescreve**). O valor cru nunca participa de uma síntese ou writer.
Alternativa recusada: coluna `provisional_title` separada — obrigaria toda
leitura a escolher entre duas colunas para sempre, para preservar uma
distinção que não interessa a nenhuma tela (o board mostra "o nome do run",
único, que melhora ao completar).

### 2. A síntese roda no recorder, não na rota

`start_run` recebe `objective` + `alert_labels`, sanitiza ambos e computa o
provisório chamando `platform/runs/headline.py`. Se ficasse na rota, o webhook e o
scheduler teriam de repetir a chamada (três cópias do mesmo fallback — o
defeito da v6 que a v7 §3 nomeou). O recorder já é o único lugar que escreve
a linha; o título nasce onde a linha nasce.

### 3. `_fallback_objective` morre; o fallback de leitura é síntese sem assunto

Para linhas antigas (headline vazio, objective ausente) `summary_of` chama
`synthesize_headline(objective=run.objective)` → com tudo vazio devolve
"Investigation with no declared subject". Não se tenta reconstruir um título
a partir de `alert_id` na leitura: o hash não é assunto, e a A6 o proíbe.
Custo aceito: runs pré-migração ficam com título genérico até serem varridos
pela retenção — melhor genérico honesto que hex.

### 4. Estágio por run é `DISTINCT ON`, não N+1 nem coluna nova

`last_completed_stages(run_ids)` em uma consulta sobre `trace_events`
(`kind='stage_completed'`, maior sequência por run, nome do estágio no
payload). Alternativa recusada: coluna `current_stage` em `agent_runs`
atualizada a cada estágio — uma segunda fonte para um fato que o log de
eventos já registra (decisão 3 da v7: uma fonte por fato). O índice existente
de `trace_events` por run cobre o filtro; se o plano de consulta reprovar no
teste de contagem, criar índice parcial `(run_id, sequence DESC) WHERE
kind='stage_completed'` na mesma migração 0020.

### 5. `stage_index` é derivado no gateway, não gravado

A ordem 1–6 vem de `StageName` (`core/state/types.py:20`). Gravar o índice
duplicaria a ordem em dado persistido; se a ordem mudar um dia, o índice
derivado acompanha e o gravado mentiria.

020 é dona apenas dos campos sumários `last_completed_stage` e `stage_index`
na listagem e no resumo do detalhe. A 030 é dona da sequência detalhada
`stages[]`, duração e findings do replay; as duas features não criam duas
fontes para o mesmo campo.

### 6. A ordem é acceptance-primeiro, e o vermelho é registrado

O acceptance de contrato (A1–A7) aterrissa antes de qualquer implementação,
roda vermelho com as mensagens reais gravadas em `evidence/`, e só então a
implementação começa. No fim, o mesmo arquivo verde + SC1/SC2 medidos no
staging (curl + SELECT registrados em `evidence/`).
