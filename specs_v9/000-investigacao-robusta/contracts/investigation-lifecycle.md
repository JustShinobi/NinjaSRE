# Contrato interno de ingestão, correlação e investigação

## Resultado da ingestão

O gateway registra a tentativa, normaliza e resolve uma ocorrência antes de iniciar trabalho. O
serviço retorna um resultado fechado; o transport adapter não repete as regras:

```text
OccurrenceIntakeResult
├── delivery_attempt_id
├── occurrence_id
├── incident_id
├── correlation_decision_id
├── classification
├── disposition: recorded | joined | investigation_claimed | no_investigation
├── active_run_id?
└── recurrence_candidate_revision_ids[]
```

Semântica:

- retry do mesmo evento lógico cria/associa uma tentativa auditável e retorna o mesmo resultado
  de ocorrência idempotente;
- nova entrega equivalente cria nova ocorrência, incrementa frequência e pode reutilizar o
  incidente/run;
- `investigation_claimed` só é retornado ao vencedor da reivindicação atômica;
- `joined` nunca agenda uma segunda tarefa de background;
- `known_recurrence` é candidata até ser confirmada por evidência atual no pipeline.

## Reivindicação atômica de run

O port de incidentes oferece uma operação conceitual:

```text
claim_active_run(incident_id, proposed_run_id, expected_version)
  -> claimed(proposed_run_id) | already_claimed(existing_run_id) | terminal_incident
```

No caminho vencedor, a criação do run, o append em `run_ids`, o preenchimento de
`active_run_id` e a mudança para `investigating` pertencem à mesma unidade de trabalho. No
caminho perdedor, nenhum run órfão é persistido.

O claim contém owner, versão e `lease_expires_at`. O reaper pode recuperá-lo após crash; se um
run já tiver sido persistido, a recuperação o reutiliza em vez de criar outro.

## Reconciliação terminal

Todo encerramento do run emite/persiste um resultado terminal com:

```text
RunTerminalResult
├── run_id
├── termination_kind
├── diagnostic_outcome
├── production_status
├── finished_reason
├── evidence_coverage
├── turn_count
├── tool_call_count
├── episode_id?
└── phase_metrics
```

O consumidor transacional:

1. conclui o run;
2. limpa `incident.active_run_id` se ainda aponta para esse run;
3. move o incidente para o estado coerente (`monitoring`, `open` ou `resolved` segundo as
   regras canônicas);
4. registra falha de integridade se um `completed` não tiver resultado diagnóstico explícito;
5. não transforma ausência de trace em sucesso.

Um reconciliador idempotente repara crashes entre execução e commit, inclusive runs expirados.

## Eventos de trace obrigatórios

| Evento | Campos mínimos |
|---|---|
| `occurrence.recorded` | occurrence, source, delivery digest, correlation/material keys |
| `correlation.decided` | classification, ruleset, matched/conflicting facts, candidates |
| `investigation.claimed` | incident, run, mode, claim result |
| `capabilities.snapshotted` | included/excluded capability IDs e reason codes |
| `knowledge.queried` | query digest, evidence anchor IDs, namespaces, limits |
| `postmortem.considered` | revision, match kind, score, matched/conflicting facts |
| `recurrence.validated` | criteria, evidence refs, decision e confiança |
| `investigation.escalated` | reason code, from/to mode |
| `investigation.finished` | diagnostic outcome, coverage e phase metrics |

Cada evento carrega `org_id`, `team_id`, `run_id` quando aplicável, timestamp e versão de
schema. Conteúdo sensível é redigido antes de chegar ao trace.

Tool calls preservam ainda `started_at`, `finished_at`, duração, entrada/resultado protegidos,
estado, cache/reuse status e evidence refs. Métrica indisponível é serializada como `unknown` ou
`null` conforme o contrato público, nunca como zero fabricado.

## Disponibilidade de capabilities

O snapshot usa estados explícitos:

```text
available | not_configured | verification_failed | permission_denied | temporarily_unhealthy
```

Somente `available` entra no catálogo oferecido ao modelo. Uma resposta determinística que
revele estado diferente atualiza o cache negativo do run e produz trace. Erros transitórios
continuam sujeitos às políticas normais de retry e não são convertidos em indisponibilidade
permanente.

## Compatibilidade

- o runtime ReAct canônico continua sendo o único executor e produtor de evaluation number;
- `recurrence_validation` é um modo e conjunto de limites do mesmo pipeline;
- adapters alternativos não recebem lógica exclusiva;
- integrações continuam autenticando pelo credential proxy;
- nenhum transport, serviço de knowledge ou classificador acessa SQL diretamente.
