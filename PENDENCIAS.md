# Pendências até sexta — o que falta para o artboard

Escrito em 2026-08-26. O DoD é aderência ao artboard (`NinjaSRE Concept Board`),
e o fluxo de decidir a ação dentro da investigação é parte dele.

## Em curso — quatro worktrees, posse de arquivo disjunta

| Lane | O que entrega | Arquivos que possui |
|---|---|---|
| A | Re-ranqueamento de capabilities **por turno**; parar de oferecer capability sem backing | `gateway/runtime/investigator.py`, `core/pipeline/`, `capabilities/registry/planning.py` |
| B | Replay passa a servir o **resultado** de cada chamada; regenera documento e client | `gateway/http/routes/runs.py`, `platform/runs/`, `fixtures/`, `console/src/api/schema.ts` |
| C | Seções do card: "Worth remembering", bloco de headline com chips, subtítulo, fonte do alerta, agrupamento por assunto | `console/src/surfaces/run-card.tsx`, `screens/runs.tsx`, `i18n/` |
| D | Três superfícies que ainda mentem: leitores de boot, classificação de erro, binding por nó | `platform/startup/`, `core/capability/registered.py`, `gateway/http/serve.py` |

## Depois de A e B — acopladas, não paralelizáveis

- **Estágio por turno no trace.** O pipeline de 6 estágios agora roda em produção,
  mas o recorder é hook do laço: intake e diagnose não deixam registro de turno.
  Sem isso o rastro não pode ser agrupado pelos 6 estágios, que é o
  "26 events across 6 stages" do quadro 1.
- **Seção "In order"** no card — depende de B servir o resultado das chamadas.
- **"What it reaches"** nos três sub-blocos (Already firing / Standing on it /
  Who feels it) — nenhum endpoint serve isso hoje.

## Riscos aceitos que continuam em aberto

Vieram da composição do pipeline no caminho de serviço e estão no staging agora:

1. **O intake pode encerrar uma corrida como ruído.** Uma chamada de modelo
   classifica o alerta e, acima do limiar, a investigação não acontece. Um
   classificador ruim descarta alerta real. Zero ocorrências observadas até agora.
2. **O diagnóstico é calculado e descartado.** O `DiagnoseStage` roda, custa uma
   chamada, e escreve num `PipelineRun` que ninguém persiste.
3. **O custo gravado subestima o real.** Intake e diagnose não deixam registro
   de turno, então os tokens da corrida ficam abaixo do que ela gastou.

## Vermelhos pré-existentes — confirmados anteriores a este trabalho

Verificados em `805e7943` e `f404215f`, não introduzidos aqui:

- `tests/contract/autonomy/test_the_gate_obeys_the_policy.py::test_with_nothing_configured_the_gate_asks_a_person`
- `tests/contract/fixtures/test_dataset_contract.py` (7 cenários)
- `tests/contract/fixtures/test_dataset_coherence.py`
- `tests/contract/observability/test_generated_documentation.py` (2)

## Não construir sem dado que os sustente

O artboard mostra, e nenhum endpoint serve: os níveis `soon` / `later` sob
"What to do". Derivá-los da prosa do relatório seria o console tendo opinião
própria sobre a investigação.
