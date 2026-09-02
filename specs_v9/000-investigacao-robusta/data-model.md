# Modelo de dados — investigação robusta e postmortems

## Visão geral

O modelo separa quatro conceitos que hoje se confundem:

```text
DeliveryAttempt ──resolve──> IncidentOccurrence ──correlaciona──> Incident
                                  │                                  │
                                  └── CorrelationDecision             ├── DispatchClaim
                                                                     └── InvestigationRun ──> Evidence
                                                                               │
Incident / InvestigationRun / Evidence ──origem──> PostmortemRevision <── publicação
                                                        │
                                                        └── KnowledgeAssociation / Feedback
```

Uma tentativa registra a entrega. Uma ocorrência nunca é apagada por ser repetida. Um incidente
representa a continuidade operacional. Um run representa trabalho executado. Um postmortem
representa conhecimento curado e versionado.

## Entidades de incidentes e correlação

### DeliveryAttempt

Registro append-only de cada tentativa de entrega recebida, inclusive retries.

| Campo | Tipo lógico | Regras |
|---|---|---|
| `attempt_id` | UUID | Identidade da travessia |
| `org_id` / `team_id` | UUID | Escopo obrigatório |
| `source` | string | Integração/origem |
| `transport_key` | string | Chave idempotente do transporte, quando fornecida |
| `payload_digest` | string | Digest após normalização/redaction |
| `occurrence_id` | UUID anulável | Preenchido ao resolver o evento lógico |
| `received_at` | timestamp | Horário da travessia |
| `disposition` | enum | `accepted`, `retry`, `rejected`, `quarantined` |
| `reason_code` | string anulável | Explicação estável |

Uma restrição única pode deduplicar a mesma tentativa técnica quando a origem fornece uma chave
de transporte; isso não elimina a auditoria das demais tentativas nem define a ocorrência.

### IncidentOccurrence

Registro imutável de um sinal normalizado recebido pelo sistema.

| Campo | Tipo lógico | Regras |
|---|---|---|
| `occurrence_id` | UUID | Identidade pública estável |
| `org_id` | UUID | Obrigatório; parte de toda chave e filtro |
| `team_id` | UUID | Escopo de autorização |
| `incident_id` | UUID anulável | Preenchido após correlação |
| `source` | string | Nome da integração/origem |
| `provider_event_id` | string anulável | Identificador lógico fornecido pela origem |
| `logical_event_key` | string | ID do provedor ou fallback versionado |
| `correlation_key` | string | Chave canônica usada para localizar incidente vivo |
| `material_signature` | string | Hash versionado apenas de fatos materialmente relevantes |
| `subject_refs` | JSON tipado | Recursos/serviços normalizados, sem segredo |
| `facts` | JSON tipado | Campos normalizados permitidos pelo schema |
| `observed_at` | timestamp | Horário do evento na origem |
| `received_at` | timestamp | Horário durável de ingestão |
| `schema_version` | integer | Versão do normalizador/assinatura |

**Restrições e índices**:

- chave única `(org_id, source, logical_event_key)` para o evento lógico;
- índice `(org_id, correlation_key, observed_at desc)`;
- índice `(org_id, material_signature, observed_at desc)`;
- `incident_id` referencia um incidente da mesma organização.

### CorrelationDecision

Registro append-only que explica a decisão tomada para uma ocorrência.

| Campo | Tipo lógico | Regras |
|---|---|---|
| `decision_id` | UUID | Identidade do evento decisório |
| `org_id` | UUID | Isolamento de tenant |
| `occurrence_id` | UUID | Obrigatório e único para a versão da decisão |
| `classification` | enum | `active_repeat`, `known_recurrence`, `ambiguous`, `material_change`, `new_problem` |
| `incident_id` | UUID | Incidente escolhido/criado |
| `active_run_id` | UUID anulável | Run reutilizado no momento da decisão |
| `postmortem_revision_ids` | UUID[] | Candidatos estruturados considerados |
| `matched_facts` | JSON tipado | Critérios satisfeitos |
| `conflicting_facts` | JSON tipado | Critérios contraditos |
| `rationale_code` | string | Código estável para métrica e teste |
| `ruleset_version` | integer | Versão do classificador determinístico |
| `decided_at` | timestamp | Horário da decisão |

Decisões posteriores de recuperação semântica não sobrescrevem esta linha; elas entram como
`KnowledgeAssociation`, preservando a diferença entre roteamento determinístico e recall do
agente.

### DispatchClaim

Coordena, entre réplicas e reinícios, quem pode iniciar trabalho para uma ocorrência/incidente.

| Campo | Tipo lógico | Regras |
|---|---|---|
| `claim_id` | UUID | Identidade |
| `org_id` | UUID | Isolamento |
| `dispatch_key` | string | Único enquanto o trabalho é exclusivo |
| `occurrence_id` / `incident_id` | UUID | Contexto obrigatório |
| `run_id` | UUID anulável | Preenchido pelo vencedor |
| `state` | enum | `claimed`, `started`, `reused`, `released`, `failed` |
| `owner_id` | string | Pod/worker que detém o lease |
| `lease_expires_at` | timestamp | Recuperável pelo reaper |
| `version` | integer | Controle otimista |
| `reason_code` | string | Resultado auditável |
| `created_at` / `updated_at` | timestamp | Auditoria |

Somente um claim não expirado vence por `dispatch_key`. A criação do run e a transição para
`started` pertencem à mesma unidade de trabalho. Claim expirado pode ser recuperado; run já
persistido é reutilizado, nunca duplicado.

### Incident (alterações)

| Campo novo/alterado | Tipo lógico | Regras |
|---|---|---|
| `active_run_id` | UUID anulável | No máximo um; aponta apenas para run não terminal |
| `run_ids` | UUID[] | Histórico append-only; não representa atividade |
| `occurrence_count` | integer | Derivado ou materializado de forma transacional |
| `last_occurrence_at` | timestamp | Atualizado em cada ocorrência correlacionada |
| `last_material_signature` | string | Base para detectar mudança material |

A projeção pública de estado deriva `open`, `awaiting_decision`, `investigating`,
`monitoring_recurrence` e `resolved` de fatos persistidos; ela não usa presença histórica de
`run_ids` como sinônimo de atividade.

**Invariantes**:

- no máximo um incidente não terminal por `(org_id, correlation_key)`;
- `active_run_id`, quando preenchido, também aparece em `run_ids`;
- incidente `investigating` exige um `active_run_id` não terminal;
- finalizar, cancelar, expirar ou recuperar o run limpa `active_run_id` atomicamente;
- histórico de runs e ocorrências não é removido ao resolver o incidente.
- repetição de incidente vivo reutiliza o incidente; recorrência depois do fechamento cria um
  novo incidente com relação explícita ao anterior, sem reabri-lo.

### InvestigationRun (alterações)

| Campo novo | Tipo lógico | Regras |
|---|---|---|
| `mode` | enum | `full_investigation` ou `recurrence_validation` |
| `diagnostic_outcome` | enum | `root_cause_found`, `known_recurrence_confirmed`, `inconclusive`, `evidence_insufficient`, `no_signal`, `failed` |
| `termination_kind` | enum | `completed`, `interrupted`, `blocked`, `cancelled`, `expired` |
| `production_status` | enum | `recovered`, `degraded`, `unknown` |
| `recurrence_candidate_id` | UUID anulável | Revisão de postmortem inicialmente validada |
| `availability_snapshot` | JSON tipado | Integrações/capacidades disponíveis e motivo das exclusões |
| `phase_metrics` | JSON tipado | Tokens, chamadas e duração por fase |
| `evidence_coverage` | decimal | Cobertura das afirmações citáveis |
| `applied_limits` | JSON tipado | Valor efetivo de cada ceiling que valeu para este run — turnos, tokens, chamadas, contexto histórico, tentativas sem nova evidência e janela de validação curta — com o nome da constante de origem |
| `finished_reason` | string anulável | Razão estável, não apenas texto livre |

**Transições de modo**:

```text
recurrence_validation --contradição/ambiguidade/limite insuficiente--> full_investigation
full_investigation --------------------------------------------------> terminal
recurrence_validation --evidência confirma critérios---------------> terminal
```

A transição para `full_investigation` é monotônica durante o run: o pipeline não volta ao modo
curto para mascarar custo ou descartar evidência já coletada.

`technical_status`, `termination_kind`, `diagnostic_outcome` e `production_status` são dimensões
separadas. `completed` informa apenas que o processo terminou; não implica causa encontrada nem
produção recuperada.

## Entidades de postmortem

### Postmortem

Envelope editorial e identidade estável do conhecimento.

| Campo | Tipo lógico | Regras |
|---|---|---|
| `postmortem_id` | UUID | Identidade pública |
| `org_id` | UUID | Isolamento obrigatório |
| `team_id` | UUID | Escopo de leitura/escrita |
| `title` | string | Obrigatório antes de publicar |
| `status` | enum | `draft`, `published`, `superseded`, `archived` |
| `outcome` | enum | `rooted`, `known_recurrence`, `inconclusive` |
| `current_revision_id` | UUID | Revisão exibida atualmente |
| `published_revision_id` | UUID anulável | Revisão elegível para recall |
| `superseded_by_id` | UUID anulável | Postmortem sucessor, mesma organização |
| `created_by` | actor ref | Usuário responsável |
| `created_at` | timestamp | Imutável |
| `updated_at` | timestamp | Última alteração do envelope |
| `published_by` / `published_at` | actor/timestamp anulável | Auditoria da publicação |
| `status_reason` | string anulável | Obrigatório em supersessão/arquivamento |

### PostmortemRevision

Conteúdo imutável. Editar um rascunho cria nova revisão e move `current_revision_id`.

| Campo | Tipo lógico | Regras |
|---|---|---|
| `revision_id` | UUID | Identidade da versão |
| `postmortem_id` | UUID | Mesmo tenant do envelope |
| `revision_number` | integer | Monotônico e único por postmortem |
| `revision_state` | enum | `draft` ou `published`; uma revisão publicada é imutável |
| `summary` | text | Síntese factual |
| `impact` | JSON tipado | Janela, escopo, severidade e afetados |
| `symptoms` | JSON tipado | Sinais observáveis usados na correlação |
| `timeline` | JSON tipado | Eventos com horário e referência de origem |
| `root_cause` | text anulável | Ausente em resultado inconclusivo |
| `contributing_factors` | JSON tipado | Fatores sustentados por evidência |
| `resolution` | JSON tipado | Ações tomadas e resultado |
| `corrective_actions` | JSON tipado | Ações, responsável, prazo e estado |
| `detection_gaps` | JSON tipado | Lacunas e ações propostas |
| `recurrence_criteria` | JSON tipado | Campos exatos, tolerâncias e exceções |
| `component_keys` | string[] | Chaves normalizadas de serviço/recurso |
| `content_hash` | string | Detecta duplicata e vincula índice vetorial |
| `review_required_fields` | string[] | Lacunas/inferências do rascunho automático |
| `change_reason` | string | Obrigatório a partir da segunda revisão |
| `authored_by` / `authored_at` | actor/timestamp | Auditoria imutável |

**Validação para publicação**:

- título, resumo, impacto, sintomas, timeline e resolução válidos;
- raiz obrigatória somente quando `outcome=rooted`;
- ao menos uma fonte e toda afirmação material citável;
- critérios de recorrência estruturados ou justificativa explícita de não aplicabilidade;
- nenhum campo `review_required` bloqueante;
- conteúdo passa pelas mesmas políticas de segredo da knowledge base.

### PostmortemSourceLink

Liga a revisão aos artefatos usados para construí-la.

| Campo | Tipo lógico | Regras |
|---|---|---|
| `revision_id` | UUID | Parte da chave |
| `source_type` | enum | `incident`, `run`, `occurrence`, `episode`, `document` |
| `source_id` | UUID/string | Parte da chave e resolvido no mesmo tenant |
| `relation` | enum | `primary`, `supporting`, `related` |
| `added_by` / `added_at` | actor/timestamp | Auditoria |

### PostmortemEvidenceRef

| Campo | Tipo lógico | Regras |
|---|---|---|
| `revision_id` | UUID | Revisão citante |
| `run_id` | UUID | Parte da identidade da evidência |
| `evidence_id` | string | Identificador local ao run |
| `claim_path` | string | Campo/afirmação sustentada |
| `excerpt_digest` | string | Detecção de drift sem copiar conteúdo sensível |

A FK lógica/física aponta para `Evidence(org_id, run_id, evidence_id)`.

### KnowledgeAssociation

Registra quando um postmortem foi considerado por uma ocorrência ou run.

| Campo | Tipo lógico | Regras |
|---|---|---|
| `association_id` | UUID | Identidade |
| `org_id` | UUID | Isolamento |
| `postmortem_id` / `revision_id` | UUID | Revisão efetivamente considerada |
| `occurrence_id` | UUID anulável | Contexto de roteamento |
| `run_id` | UUID anulável | Contexto de investigação |
| `match_kind` | enum | `exact`, `semantic`, `weak` |
| `query_digest` | string anulável | Consulta redigida/digestível |
| `score` | decimal anulável | Score do mecanismo, nunca prova isolada |
| `matched_facts` / `conflicting_facts` | JSON tipado | Explicação estruturada |
| `decision` | enum | `candidate`, `confirmed`, `rejected`, `ignored` |
| `influence` | enum | `none`, `guided_plan`, `short_path`, `escalated` |
| `created_at` | timestamp | Imutável |

### AssociationFeedback

Feedback append-only do operador; não apaga a decisão histórica.

| Campo | Tipo lógico | Regras |
|---|---|---|
| `feedback_id` | UUID | Identidade |
| `association_id` | UUID | Associação avaliada |
| `rating` | enum | `useful`, `incorrect`, `outdated` |
| `reason` | string | Obrigatório para incorreto/desatualizado |
| `actor_id` | UUID/string | Autor autorizado |
| `created_at` | timestamp | Imutável |

Feedback `incorrect` ou `outdated` não arquiva automaticamente o postmortem; ele entra na fila
de revisão e deixa de elevar confiança sem confirmação humana.

`KnowledgeAssociation` faz parte do protocolo `PostmortemStore`. Criação, leitura e agregação
possuem o mesmo contrato parametrizado para fake e PostgreSQL e são acessadas pelo serviço apenas
pela `UnitOfWork`; nenhuma implementação concreta é importada pelo domínio.

## Evidência e trace

### Evidence (alteração de identidade)

**Chave anterior**: `(org_id, evidence_id)`.

**Nova chave**: `(org_id, run_id, evidence_id)`.

Todas as operações de leitura, citação e integridade exigem as três dimensões. Tool calls
continuam referenciando seus IDs locais, mas o `run_id` do próprio call faz parte da resolução.
Referências que não possam ser resolvidas após a migração são registradas como violações de
integridade; claims dependentes são rebaixadas para hipótese ou ficam bloqueadas para
publicação.

### TracePhaseMetric

Pode ser persistido como estrutura tipada no run ou como linhas agregáveis, conforme a
implementação do port, mas o contrato lógico é:

| Campo | Tipo lógico | Regras |
|---|---|---|
| `run_id` | UUID | |
| `phase` | enum | |
| `input_tokens` / `output_tokens` | integer não negativo **anulável** | `null` quando o provedor não reporta uso |
| `tool_calls` / `failed_tool_calls` | integer não negativo | Contados pelo próprio runtime, sempre conhecidos |
| `duration_ms` | integer não negativo | Medido pelo próprio runtime, sempre conhecido |
| `context_peak_tokens` | integer não negativo **anulável** | `null` quando a contagem de tokens não está disponível |

Fases mínimas: `intake`, `evidence_anchor`, `recall`, `recurrence_validation`,
`full_investigation`, `synthesis`.

Os campos anuláveis existem porque zero e desconhecido são fatos diferentes, e FR-025
proíbe representar o segundo como o primeiro. Um provedor que não reporta uso produz
`null`, que as superfícies renderizam como “desconhecido”; um turno que realmente não
consumiu tokens produz `0`. As contagens que o próprio runtime observa — chamadas e
duração — não têm o caso desconhecido e permanecem obrigatórias.

## Estados e transições de postmortem

```text
draft --publish(validado)--> published --supersede--> superseded
  │                              │
  └────────archive───────────────┴────────archive──> archived
published --criar revisão draft--> published (revisão publicada anterior segue vigente)
published + draft validado --publish--> published (nova revisão passa a vigente)
```

Regras:

- somente `published` participa de novas consultas/correlações;
- ao editar um publicado, a revisão anterior continua vigente até a nova publicação;
- `superseded` exige sucessor e deixa de aparecer como candidato, mas continua resolvível por
  decisões históricas;
- `archived` exige motivo e não pode voltar a ser publicado; uma correção cria novo postmortem;
- transições são idempotentes por chave de comando e auditadas.

## Migração e backfill

1. Criar tabelas de tentativa, ocorrência, decisão e claim, enums e índices sem mudar o serving
   path.
2. Migrar a chave de evidência e executar relatório de integridade por tenant.
3. Adicionar `active_run_id` anulável e preencher somente quando existir exatamente um run
   comprovadamente não terminal; demais incidentes são reconciliados para estado verdadeiro.
4. Criar ocorrências sintéticas de migração apenas como marcadores de origem histórica, sem
   alegar payload/horário que não existe. Elas não participam de métricas de deduplicação.
5. Ativar gravação paralela de ocorrências/decisões e comparar com o roteamento legado.
6. Ativar a reivindicação atômica e remover índices em memória do caminho autoritativo.
7. Indexar somente postmortems publicados criados após revisão humana; documentos externos
   existentes podem originar rascunhos, nunca publicação automática.

O downgrade preserva dados em tabelas novas até o último passo. Para a chave de evidência,
colisões recebem identificadores namespaced e todas as referências são reescritas na mesma
transação antes de restaurar a chave antiga.

## Isolamento, retenção e segurança

- todo port recebe `org_id`; acesso por `team_id` segue as permissões já existentes;
- nenhum índice vetorial cruza organizações;
- payloads, queries e trechos passam por redaction/secret guard antes da persistência;
- postmortems respeitam exportação, retenção e exclusão controladas pelo operador;
- histórico de revisão, decisão e feedback é auditável e não depende de telemetria externa;
- exclusão de uma fonte aplica a política de retenção ao postmortem sem silenciosamente
  preservar segredo em chunks ou embeddings.

## Projeções de memória e avaliação

### EpisodeSignatureView

Projeção reconstruível, não substituta dos episódios originais.

| Campo | Tipo lógico | Regras |
|---|---|---|
| `org_id` / `team_id` | UUID | Isolamento |
| `signature` | string | Assinatura canônica versionada |
| `episode_count` | integer | Quantidade sem apagar episódios |
| `first_seen_at` / `last_seen_at` | timestamp | Intervalo observado |
| `outcome_distribution` | JSON tipado | Variações de desfecho |
| `run_ids` / `episode_ids` | UUID[] | Links completos às origens |
| `representative_postmortem_id` | UUID anulável | Apenas se publicado/vigente |

### InvestigationStrategy (alterações)

Estratégias passam a carregar `source_episode_ids`, `source_postmortem_revision_ids`,
`effective_from`, `effective_until`, `status` (`active`, `stale`, `superseded`) e
`obsolescence_reason`. Guidance filtra estratégias não ativas, mas o trace histórico mantém a
versão consultada.

### LearningEvaluation

Registra cenário/corpus, switches de ablação, baseline, período, runtime/provider, métricas de
qualidade/evidência/custo e veredicto. Ausência de usage é `unknown`, nunca zero. O registro
permite expor economia por postmortem sem transformar telemetria externa em dependência.

O store participa da `UnitOfWork` e dos gateways fake/PostgreSQL. A identidade inclui versão do
corpus, cenário, runtime/provider/modelo, configuração de limites e período, impedindo comparação
entre coortes incompatíveis. O job `learning.evaluation` do scheduler do gateway constrói o
serviço produtor; consultas de métricas usam os mesmos registros persistidos.
