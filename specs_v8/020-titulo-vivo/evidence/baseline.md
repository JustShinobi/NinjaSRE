# T001 — linha de base, com a contaminação explicada

Log completo (26630 linhas, propositalmente fora do repositório):
`/tmp/claude-999/-srv-workspaces-NinjaSRE/ec6dd9db-b857-442a-ad52-779c42f3a2c8/scratchpad/evidence/baseline-make-verify.log`

## Resultado bruto

```
FAILED tests/unit/platform/persistence/test_port_conformance.py::test_every_tenant_scoped_fake_satisfies_its_port[run_traces]
===== 1 failed, 13111 passed, 31 skipped, 32 warnings in 120.20s (0:02:00) =====
make: *** [Makefile:93: test] Error 1
EXIT=2
```

Lido do próprio log, não de notificação — `EXIT=2`, não 0.

## Por que não é linha de base confiável

O `make verify` rodou em segundo plano enquanto a pesquisa inicial ainda
acontecia; a primeira edição desta sessão (adicionar `last_completed_stages`
ao protocolo `RunTraceStore` em
`platform/persistence/ports/run_trace_store.py`) pousou no disco antes do
`FakeRunTraceStore` ganhar o método correspondente. `pytest` importa os
módulos na coleta; essa corrida específica produz exatamente essa falha
específica — um teste de conformidade porta↔fake que checa se o fake tem
todo método que o protocolo declara.

Confirmado sem tocar a árvore de trabalho: `git show
f02bf942:platform/persistence/ports/run_trace_store.py` não tem
`last_completed_stages`, e nem o fake nem o Postgres tinham naquele commit —
os três estavam mutuamente consistentes. A linha de base real, no commit de
partida (`f02bf942`), era verde para este teste.

`make verify` completo será rodado de novo antes de T013 ser marcado feito.
