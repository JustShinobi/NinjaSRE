# make verify — histórico real das cinco rodadas (T013)

Cada `EXIT=` abaixo foi lido do próprio arquivo de log salvo fora do
repositório — as três primeiras vezes com `tail`, as duas últimas esperando
de propósito com `until grep -q "^EXIT=" ...; do sleep 5; done` antes de ler,
porque as notificações de segundo plano desta sessão relataram "exit code 0"
três vezes seguidas para rodadas que na verdade saíram 2.

| Rodada | Passo que reprovou | Causa real | EXIT |
|---|---|---|---|
| 1 | `format-check` (ruff) | 3 arquivos .py não formatados: `gateway/http/routes/investigations.py`, `tests/contract/runs/test_live_title_contract.py`, `tests/unit/platform/runs/test_recorder.py` | 2 |
| 2 | `typecheck` (mypy) | `gateway/http/routes/investigations.py:143: error: Returning Any from function declared to return "Mapping[str, str]"  [no-any-return]` — `stages_of` retornava direto o resultado de uma chamada sobre `uow: Any` | 2 |
| 3 | `console-static` (prettier) | `transversal-rules.spec.ts` e `bans.test.ts`, editados por script Python/sed, não seguiam o estilo Prettier | 2 |
| 4 | — nenhum | verde de ponta a ponta: suíte principal 13136 passed/31 skipped, benchmark 38 passed | 0 |
| 5 | — nenhum | depois de fechar a lacuna de cobertura de `GET /v1/runs`: suíte principal 13137 passed/31 skipped (mais um teste), benchmark 38 passed | 0 |

Cada correção foi feita nos arquivos exatos que a mensagem de erro nomeou —
nunca `ruff format .`/`prettier --write .` sobre o repositório inteiro.

Logs completos (fora do repositório, como T001 pede):
`/tmp/claude-999/-srv-workspaces-NinjaSRE/ec6dd9db-b857-442a-ad52-779c42f3a2c8/scratchpad/evidence/`
(`baseline-make-verify.log`, `final-make-verify.log` [rodada 1],
`final-make-verify-2.log` [rodada 2], `final-make-verify-3.log` [rodada 3],
`final-make-verify-4.log` [rodada 4, verde], `final-make-verify-5.log`
[rodada 5, verde, estado final]).
