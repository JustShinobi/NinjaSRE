# Implementation Plan: Investigação robusta, recorrência e postmortems

**Branch**: `feat/v9-000-investigacao-robusta` | **Date**: 2026-09-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from
`/specs_v9/000-investigacao-robusta/spec.md`

## Summary

Substituir a deduplicação volátil e a abertura não atômica de investigações por um intake
durável que distingue tentativas de entrega de ocorrências lógicas, explica cada correlação e
garante no PostgreSQL apenas um run ativo por incidente. Introduzir postmortems curados,
versionados e publicáveis a partir de incidentes ou investigações; somente revisões publicadas
entram no recall. Problemas recorrentes usam o mesmo pipeline ReAct canônico em modo de
validação curta, com evidência atual antes de qualquer recuperação semântica e escalada
automática ao fluxo completo diante de contradição. A mudança também corrige a identidade
cross-run de evidência, elimina chamadas a capabilities sabidamente indisponíveis, torna o
resultado diagnóstico explícito e mede custo e qualidade por fase e por ablação.

## Technical Context

**Language/Version**: Python 3.12+; TypeScript 5.9; React 19 / Next.js 16

**Primary Dependencies**: FastAPI 0.141+, Pydantic 2.13+, SQLAlchemy 2.0+, Alembic 1.19+,
pgvector; console com Next.js App Router, Tailwind CSS 4 e cliente OpenAPI gerado

**Storage**: único PostgreSQL existente, com pgvector e Apache AGE, acessado exclusivamente
pelos ports/repositórios de `platform/persistence/`; fakes equivalentes para testes

**Testing**: pytest (unit, contract, synthetic, architecture, security, chaos/e2e), harness de
ablação e scoring; Vitest e Playwright no console; contratos de persistência contra fake e
PostgreSQL

**Target Platform**: serviço Linux self-hosted em Kubernetes/k3s e console web responsivo;
staging em `stg-ninjasre.lan.kyo.ninja`

**Project Type**: plataforma web full-stack em monorepo, backend Python em camadas e console
TypeScript isolado por HTTP

**Performance Goals**: reduzir em pelo menos 80% tokens e 50% tool calls por recorrência
confirmada contra o baseline do fluxo completo; disponibilizar 95% das conclusões recorrentes
em até 60 segundos; impedir multiplicação de runs sob concorrência; reduzir em 95% as chamadas
a capabilities previamente indisponíveis; com 10.000 postmortems autorizados e páginas de até
50 itens, manter p95 de no máximo 500 ms no endpoint de consulta e p95 de no máximo um segundo
entre a ação do operador e a conclusão do carregamento no console

**Constraints**: evidência atual obrigatória antes de recall semântico; nenhuma publicação
automática; um runtime canônico; limites novos como constantes nomeadas; read-only por padrão;
nenhum segredo em prompt, trace ou postmortem; nenhuma query fora de persistence; isolamento
estrito de tenant/team; compatibilidade de migração e rollback; filtros da UI na URL

**Scale/Scope**: fluxo de webhooks/incidentes/runs, evidence/trace, knowledge/memory, API e
console; baseline observado de 180 incidentes, 789 investigações, 6.219 tool calls e 75 milhões
de tokens, com alertas individuais gerando mais de cem investigações

## Constitution Check

*GATE: aprovado antes da pesquisa e revalidado depois do design de dados e contratos.*

| Artigo | Gate de design | Pré-Phase 0 | Pós-Phase 1 |
|---|---|---|---|
| I — Evidence Over Assertion | Recorrência nunca é confirmada sem evidência atual citada; postmortem referencia `(run_id, evidence_id)` e claims sem referência não publicam | PASS | PASS |
| II — Bounded Autonomy | Modo curto reutiliza os ceilings existentes e adiciona somente constantes nomeadas em `config/constants/` | PASS | PASS |
| III — Read-Only by Default | Recall/classificação são leitura; draft/feedback exigem `knowledge.write` e publicação/invalidação exigem `knowledge.curate`; nenhum novo caminho de ação externa | PASS | PASS |
| IV — Secrets Never Reach the Agent | Payload é normalizado/digerido; postmortem e índice vetorial passam por secret guard; integrações continuam pelo credential proxy | PASS | PASS |
| V — One Canonical Runtime | `recurrence_validation` é modo do pipeline ReAct existente, não adapter/runtime paralelo | PASS | PASS |
| VI — Provider Neutrality | Rascunho determinístico não exige LLM; todo uso opcional continua por `core.llm.get_llm(role)` | PASS | PASS |
| VII — Learning Is Measured | Dois eixos de ablação isolam postmortem e caminho curto; recall semântico ocorre só após evidence anchor e fica no trace | PASS | PASS |
| VIII — Layered Architecture | Domínio em `platform`, pipeline em `core`, transports em `gateway`, console apenas via REST; imports respeitam tiers | PASS | PASS |
| IX — Capabilities Are Declared | Busca existente é estendida com resultado tipado; side effects/permissões continuam declarados e catálogo é filtrado por disponibilidade | PASS | PASS |
| X — Operator Owns Their Data | Dados e embeddings ficam no PostgreSQL do operador, com exportação, retenção e nenhuma telemetria externa | PASS | PASS |
| XI — Single Datastore | Ocorrências, decisões, postmortems, associações e métricas usam ports do mesmo Postgres | PASS | PASS |
| XII — Test-First, Trace-Backed | Cada fatia começa por testes de comportamento/contrato; decisões, recall, escalada e custo entram no trace | PASS | PASS |
| XIII — Language and Attribution | Código/identificadores em inglês; textos de produto/spec em pt-BR; fontes e autores preservados | PASS | PASS |
| XIV — Composed or It Is Not Shipped | Plano cobre schema, ports/fakes/Postgres, serviços, runtime, REST, permissão, cliente gerado, fixtures, console e E2E | PASS | PASS |

Não há violação constitucional planejada nem `NEEDS CLARIFICATION` remanescente. A tensão do
Artigo VII é resolvida por uma regra verificável, não por uma asserção: FR-013 separa os dois
momentos da classificação e proíbe score de similaridade no primeiro. Antes do run existem
apenas chaves exatas, mudança material e critérios estruturados de revisões publicadas — o
suficiente para rotear, insuficiente para concluir. O score de associação, a margem e todo
recall semântico pertencem ao momento posterior ao evidence anchor, o que mantém o recall
dirigido pelo agente e nunca pré-injetado sobre um alerta.

## Project Structure

### Documentation (this feature)

```text
specs_v9/000-investigacao-robusta/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── investigation-lifecycle.md
│   └── postmortems.openapi.yaml
└── tasks.md                         # criado somente por /speckit-tasks
```

### Source Code (repository root)

```text
config/constants/
├── investigation.py                # ceilings do modo de recorrência e lease/reaper
└── knowledge.py                    # bounds de busca/matching/postmortem

core/
├── agent/                           # trace e contabilização por fase no runtime canônico
└── pipeline/
    ├── ports.py                     # contratos de catalogue/knowledge enriquecidos
    └── stages/
        ├── intake/                  # triagem que recebe a decisão durável e deixa de deduplicar
        ├── gather_evidence.py       # evidence anchor antes de recall
        ├── plan_evidence.py         # plano curto ou completo no mesmo pipeline
        └── [recurrence stage]       # validação e escalada, módulo dono do comportamento

platform/
├── evaluation/
│   ├── __init__.py                 # fronteira pública do domínio de avaliação
│   └── service.py                  # avaliação reproduzível e persistência do veredicto
├── incidents/
│   ├── ingestion.py                # tentativa, ocorrência e intake canônico
│   ├── correlation.py              # classificação determinística/material change
│   ├── lifecycle.py                # único construtor e transições de incidente
│   ├── dispatch.py                 # claim durável, join/start e recovery
│   ├── joining.py                  # projeção de reuso de run ativo
│   └── [models/errors/services]     # resultados fechados e invariantes
├── knowledge/
│   ├── service.py                  # composição da busca existente
│   ├── policy.py                   # switches independentes de ablação
│   └── postmortems/
│       ├── models.py               # envelope, revisão, fontes, refs, associação, feedback
│       ├── service.py              # state machine e autorização de domínio
│       ├── drafts.py               # projeção determinística de incident/run
│       ├── matching.py             # critérios publicados e candidatos explicáveis
│       └── search.py               # namespace publicado e filtros
├── memory/
│   ├── [episode projections]       # visão canônica por assinatura sem apagar episódios
│   └── strategy/                   # vigência, fontes e obsolescência explicável
├── runs/                            # outcome diagnóstico e reconciliação terminal
├── identity/permissions.py          # knowledge.curate e roles explícitos
└── persistence/
    ├── ports/
    │   ├── __init__.py             # exporta os ports públicos
    │   ├── incident_store.py       # delivery/occurrence/decision/dispatch claim
    │   ├── postmortem_store.py     # novo port especializado
    │   ├── run_trace_store.py      # chave composta de evidence/phase metrics
    │   ├── learning_evaluation_store.py # resultados versionados de ablação
    │   └── transaction.py          # composição dos stores na mesma UoW
    ├── fakes/                       # mesma semântica observável dos ports
    ├── postgres/
    │   ├── models.py               # tabelas e constraints
    │   └── repositories/           # SQL restrito a persistence
    └── migrations/versions/        # evidence, intake/claim e postmortem

capabilities/tools/system/knowledge_search/
├── results.py                       # resultados tipados de postmortem
├── tool.py                          # schema público sem capability redundante
└── binding.py                       # ligação ao KnowledgeService e trace

gateway/
├── webhooks/
│   ├── router.py                   # delega ao intake durável
│   ├── idempotency.py              # deixa de ser autoridade de serving
│   └── dedup.py                    # deixa de ser autoridade de serving
├── http/
│   ├── evaluation_job.py           # runner composto da avaliação agendada
│   ├── scheduled_work.py           # registra o job real de avaliação
│   ├── orchestration.py            # start/reconcile em uma UoW
│   ├── routes/
│   │   ├── incidents.py            # link/ação de draft e lifecycle truth
│   │   ├── investigations.py       # link/ação de draft e outcome
│   │   └── knowledge.py            # CRUD editorial/feedback/listagem
│   └── security/route_permissions.py # read/write/curate por operação
└── runtime/investigator.py          # bindings, availability snapshot e políticas

console/src/
├── app/api/                         # courier routes fechadas para mutações
├── api/                             # cliente OpenAPI regenerado
├── surfaces/screens/
│   ├── knowledge.tsx               # nova tab Postmortem e URL state
│   ├── incident-detail.tsx         # criar/ver postmortem relacionado
│   ├── run-detail.tsx              # criar/ver postmortem relacionado
│   └── [postmortem screens]         # lista, detalhe, edição, publicação e feedback
└── [i18n, fixtures e componentes]

fixtures/contract/openapi.json       # contrato regenerado consumido por console/mockplane

tests/
├── architecture/                    # único lifecycle/orchestration e boundaries
├── contract/
│   ├── persistence/                 # fake/Postgres, tenant, concorrência e migração
│   └── console/                     # shape público de incident/run/postmortem
├── security/                        # permissão e secret/tenant isolation
├── synthetic/                       # recorrência, contradição, mudança e ablações
├── benchmarks/                      # latency p95 de busca/listagem com 10k postmortems
├── usability/                       # protocolo reproduzível de primeira utilização
├── unit/
│   ├── core/pipeline/               # modos, anchor, recall e escalada
│   ├── platform/incidents/          # correlação, claim e reconciliação
│   ├── platform/knowledge/          # lifecycle, draft, matching e feedback
│   └── gateway/                     # endpoints, idempotência e composição
└── e2e/                             # fluxo editorial e correlação no produto composto
```

**Structure Decision**: manter os packages e tiers existentes. Incidentes são donos de
entrega/ocorrência/correlação/exclusão mútua; knowledge é dono do postmortem e de sua
recuperação; core é dono do comportamento do pipeline; persistence é o único dono de SQL;
gateway apenas compõe e transporta; console só consome REST. Um `PostmortemStore` separado é
justificado por estado editorial, revisões e associações, mas continua sendo um port exposto
pelo mesmo `PersistenceGateway`, não um datastore novo.

## Design e fluxo de implementação

### Phase 0 — Pesquisa concluída

As decisões, justificativas e alternativas estão em [research.md](research.md). Os pontos de
maior impacto são:

- tentativa de entrega, ocorrência lógica e decisão são fatos duráveis distintos;
- `active_run_id` e criação do run são reivindicados atomicamente por claim com lease;
- recorrência depois de encerramento cria novo incidente relacionado, sem reabrir histórico;
- postmortem é entidade curada distinta de documento genérico;
- recall semântico permanece dirigido pelo agente depois do evidence anchor;
- validação curta e investigação completa usam o mesmo runtime;
- evidence refs tornam-se compostas por run antes de alimentar conhecimento;
- disponibilidade é filtrada antes da seleção, com cache negativo apenas no run;
- ablações independentes provam conhecimento e eficiência.

### Phase 1A — Fundação de persistência e integridade

Começar pela caracterização do comportamento atual e por testes de port. Alterar a chave de
evidence para `(org_id, run_id, evidence_id)` antes de aceitar citações de postmortem. A
migração precisa de upgrade e downgrade testados, relatório de refs irrecuperáveis e nenhuma
reconstrução inventada. Em seguida, adicionar delivery attempt, occurrence, decision, dispatch
claim, a constraint parcial única de incidente vivo e `active_run_id` anulável.

Antes de criar a constraint única, a migração identifica incidentes vivos duplicados, escolhe
um vencedor determinístico, move associações sem apagar histórico e encerra/consolida os demais
com razão auditável. Os fakes devem reproduzir idempotência, conflito otimista e claim; um fake
que apenas serializa felizmente não atende aos contratos concorrentes.

### Phase 1B — Intake durável e um único run ativo

Fazer `IncidentLifecycle` continuar como único construtor e mover a vitória concorrente para o
port `claim_open_incident`. O intake grava cada tentativa HTTP e resolve/obtém a ocorrência
lógica. Quando o provedor oferece ID estável, a identidade é `(source, provider_event_id)`;
quando não oferece, um fallback versionado usa payload normalizado, fingerprint e janela
definida — nunca `event_id` vazio ou `received_at` como identidade lógica.

Depois, o serviço classifica, liga/cria incidente e chama o dispatcher. A criação do run,
`run_ids`, `active_run_id` e claim acontecem na mesma UoW; o background só é agendado após o
commit vencedor. O claim guarda owner, versão, estado e lease. Reaper/retry recuperam claim
expirado sem criar run órfão. Os limites de dispatch deixam de ser autoridade apenas em memória
ou ficam explicitamente como throttle local best-effort sobre o claim durável.

A deduplicação do gateway não é a única a cair. O stage de intake do pipeline
(`core/pipeline/stages/intake/`) mantém seu próprio `IncidentIndex`, fingerprint e janela, e
hoje decide por conta própria se um alerta abre ou anexa um incidente — uma terceira
autoridade, viva no serving path porque `build_pipeline` é construído por
`gateway/runtime/investigator.py`. Ela passa a receber a `CorrelationDecision` durável já
tomada e a classificação do intake deixa de poder contradizê-la: o stage anota e explica, o
intake decide. Uma triagem que recebe um incidente com ocorrências ou runs anexados não pode
rotulá-lo como novo.

Retries retornam o resultado persistido e ainda deixam tentativas auditáveis. Novos eventos
equivalentes preservam a ocorrência, mas se juntam ao run ativo. Uma recorrência depois que o
incidente foi encerrado cria novo incidente ligado ao postmortem/incidente anterior. Finalização
e reaper reconciliam estados presos. Os índices em memória podem permanecer temporariamente
como otimização não autoritativa durante rollout, sendo removidos do caminho decisório depois.

### Phase 1C — Domínio editorial de postmortem

Implementar o modelo de [data-model.md](data-model.md) com revisões imutáveis e transições
fechadas. O gerador de draft projeta somente dados persistidos, cita as evidências pelo par
run/evidence e marca lacunas. Publicação valida completude, referências, segredo e estado; só
então atualiza o índice vetorial `postmortems`. Nova revisão de um publicado não substitui a
revisão vigente até publicação explícita. Supersessão/arquivamento removem candidatos futuros,
preservando decisões históricas.

O mecanismo existente de proposals pode sugerir drafts para assinaturas repetidas e bem
evidenciadas, mostrando fatos do agrupamento e opções de anexar fontes, revisar/superseder ou
confirmar problema distinto. Proposta nunca cria conhecimento publicado nem concede permissão
de curadoria ao agente.

A extração já existente de documentos de postmortem continua sendo metadado de corpus externo;
ela pode oferecer fonte para um draft, mas nunca equivale a um postmortem curado publicado.

### Phase 1D — Recuperação, recorrência e token efficiency

O classificador anterior ao run considera apenas chaves exatas, mudança material e critérios
estruturados de revisões publicadas. Quando um run é necessário, uma candidata conhecida abre o
pipeline canônico em `recurrence_validation`. A primeira fase coleta evidence anchor. Só depois
o agente pode consultar knowledge; o trace guarda consulta, candidates, refs escolhidas e
influência. Confirmação exige critérios e evidência atuais; contradição, insuficiência ou baixa
confiança escalonam o mesmo run ao plano completo.

Scores de associação são normalizados entre zero e um e existem somente depois do evidence
anchor; o classificador anterior ao run não recebe score algum e não pode ser implementado
sobre o matcher semântico. Sem contradição material, confirmação exige score mínimo de 0,80 e
margem mínima de 0,10 sobre o segundo candidato; empate, margem menor, fato obrigatório
ausente ou contradição mantêm o caso ambíguo ou promovem investigação completa. Score mínimo, margem e ordenação de empate são constantes versionadas em
`config/constants/knowledge.py`; qualquer alteração exige reexecutar o corpus rotulado.

O snapshot de availability combina configuração, autorização e verificação real. Schemas de
capabilities indisponíveis não consomem seleção/contexto. Falhas determinísticas atualizam um
cache negativo no run; falhas transitórias seguem retry normal. Limites específicos do modo
curto ficam em `config/constants/`, e métricas de tokens/calls/duração são atribuídas às fases.
Cache hit de chamada idêntica entra no trace e no contexto do raciocínio como reutilização, não
como nova observação. O completion gate encerra coleta quando claims necessárias estão
suportadas e nenhum passo pendente pode mudar materialmente a conclusão.

Uma projeção canônica agrupa episódios repetidos por assinatura e mantém contagem, primeira e
última ocorrência, variações de resultado e links para todos os runs originais. Estratégias
derivadas ganham fontes, janela de vigência, estado e motivo de obsolescência; estratégias
stale não entram silenciosamente no guidance. Os eixos existentes `memory_read` e
`memory_strategy` permanecem independentes dos novos eixos de postmortem e caminho curto.

O outcome terminal é explícito e independente do estado técnico e da recuperação da produção.
As superfícies distinguem causa apoiada, inconclusivo, evidência insuficiente, interrompido,
bloqueado e produção recuperada. Um run sem turns, evidence ou resultado válido não entra como
investigação bem-sucedida. Episode creation e reconciliação expõem lacunas, em vez de
silenciosamente declará-las `completed`. A triagem recebe a decisão durável e o histórico real
do incidente, não reclassifica como novo um caso já anexado.

### Phase 1E — Contrato REST e produto composto

Implementar [postmortems.openapi.yaml](contracts/postmortems.openapi.yaml) no gateway canônico,
incluindo idempotency keys, ETags, tenant/team, transições e permissões. Incident e run details
ganham links de postmortem, `active_run_id`, outcome e cobertura; criar/revisar/feedback usam
`knowledge.write`, publicação/supersessão/archive usam a nova `knowledge.curate`, e leitura usa
`knowledge.read`.

Regenerar OpenAPI/client/fixtures no mesmo change. No console, adicionar `postmortem` à tab de
Knowledge, filtros e seleção em URL state, lista/detalhe/editor/revisão e ações nos detalhes de
incidente/run. Mutações passam pelas courier routes fechadas. Estados loading/empty/error,
403, 409 e 412 precisam ser projetados, assim como layout estreito e navegação por teclado.

### Phase 1F — Medição, rollout e rollback

Adicionar os eixos `postmortems` e `recurrence_path` ao harness, preservar os eixos existentes
de episódio/memória e estratégia, e executar o corpus nas células isoladas descritas no
[quickstart.md](quickstart.md). Métricas comparam qualidade, evidência, tokens, calls, latência,
duplicidade de runs, precisão de recorrência e falhas evitadas.

Cada célula comparada fixa versão do cenário/corpus, runtime, provider/modelo, configuração de
limites e período. O corpus possui no mínimo 200 cenários previamente rotulados, metade com
postmortem relevante conhecido e metade negativa, e reporta `recall@3`, falsas confirmações e a
ordenação determinística de empates. O baseline de uma recorrência é a célula do mesmo cenário
com `postmortems` e `recurrence_path` desligados, nunca uma mediana global sem coorte.

`LearningEvaluationStore` participa da mesma `UnitOfWork` nos gateways fake e PostgreSQL. Um
`EvaluationService` grava o resultado e é construído pelo runner `learning.evaluation`
registrado em `gateway/http/scheduled_work.py`; a rota de métricas lê os mesmos registros. Esse
caminho de scheduler é a evidência de composição exigida pelo Artigo XIV, enquanto o harness
continua sendo o produtor determinístico dos resultados do runtime canônico.

Rollout em staging usa etapas reversíveis:

1. migrations e leitura compatível;
2. shadow write de delivery/occurrence/decision e comparação com a rota legada;
3. claim atômico como autoridade, com métrica de conflitos e recuperação de lease;
4. postmortem editorial sem uso automático;
5. matching/recall em observação;
6. modo curto habilitado por política/feature flag local;
7. remoção do serving path legado depois dos critérios de estabilidade.

Rollback desliga matching e modo curto sem apagar dados. O rollback de schema usa downgrades
testados; diante de evidence IDs que colidiriam, deve recusar com segurança ou reescrever as
referências na mesma transação, nunca perder dados silenciosamente. Nenhum rollback reativa uma
revisão superseded/archived como candidata sem decisão explícita do operador.

## Estratégia de testes e gates

### Test-first por domínio

- **Persistência**: contratos fake/Postgres para tenant, tentativa/occurrence idempotente, claim
  concorrente/lease, revisões, feedback e chave de evidence; migrations upgrade/downgrade.
- **Incidentes**: retries, providers sem ID, repetições legítimas, material change, join,
  winner/loser do claim, crash pós-commit e reconciliação terminal.
- **Knowledge/Postmortem**: draft fiel ao trace, campos bloqueantes, publicação, nova revisão,
  supersessão, archive, search only published, feedback e secret guard.
- **Pipeline**: evidence anchor antecede recall, confirmação citada, contradição escala no mesmo
  run, thresholds/margem determinísticos, budgets nomeados, availability snapshot/cache negativo,
  contrato completo de cada tool call e outcome explícito.
- **API/segurança**: OpenAPI, idempotency, ETag, 403/404 sem tenant leak, permission matrix e
  route inventory.
- **Console**: URL state, campos obrigatórios da lista, ações, conflito editorial, permissões,
  estados e acessibilidade; benchmark com 10.000 postmortems e página máxima de 50 itens.
- **Synthetic/ablation**: recorrência confirmada, falso parecido, mudança material e problema
  novo; comparação das quatro células sem regressão de qualidade.
- **E2E/visual**: criar draft, revisar/publicar, localizar na nova aba, reutilizar no próximo
  incidente e fornecer feedback; Playwright determinístico e Orca Browser em staging.
- **Usabilidade**: primeira utilização moderada por pelo menos 10 operadores elegíveis, sem ajuda
  nem documentação, com tempo e desfecho anonimizados para validar SC-012.

### Gates de conclusão

```bash
make fast SCOPE=<área alterada>
make verify
make test-postgres
```

Além desses gates, executar sweeps, synthetic/ablation e E2E/chaos aplicáveis. Um teste sem a
infraestrutura exigida deve pular com mensagem explícita conforme a convenção do repositório;
staging fornece a evidência final do produto composto.

## Riscos e mitigação

| Risco | Mitigação planejada |
|---|---|
| Classificação antiga ancora investigação nova | recall semântico somente após anchor; mudança material e contradição forçam fluxo completo |
| Claim concorrente cria run órfão ou preso | criação/claim na mesma UoW, lease/reaper, background pós-commit e teste de barreira |
| Provider sem event ID produz falso merge/split | fallback versionado, fatos normalizados, janela nomeada e cenários por integração |
| Incidentes vivos duplicados impedem constraint | preflight de migração, consolidação auditável e nenhuma exclusão de histórico |
| Migração evidencia corrupção histórica | relatório por tenant, refs não resolvidas explícitas, claims rebaixadas e nenhuma reconstrução inventada |
| Postmortem incorreto contamina decisões futuras | publicação humana, revisão imutável, feedback, supersessão e trace da influência |
| Vector search retorna draft/stale/cross-tenant | namespace/filtros por revisão publicada vigente e tenant dentro do port |
| Economia aparente mascara pior diagnóstico | ablação com gates simultâneos de qualidade, cobertura e eficiência |
| Rollout troca semântica de webhook abruptamente | shadow write/compare, feature flag local e etapas reversíveis |
| UI e backend divergem | OpenAPI canônico, cliente e fixtures regenerados, contract/E2E no mesmo change |

## Complexity Tracking

Não há violações constitucionais a justificar. A feature adiciona um port especializado de
postmortem, mas não adiciona camada, runtime, datastore ou canal de transporte. A separação é
necessária porque ciclo editorial/revisões/associações têm invariantes diferentes dos
documentos genéricos e continuam compostos pelo `PersistenceGateway` existente.
