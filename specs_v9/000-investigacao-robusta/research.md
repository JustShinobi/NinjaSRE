# Pesquisa técnica — investigação robusta, recorrência e postmortems

## Escopo da pesquisa

Este documento registra as decisões de arquitetura necessárias para implementar a
[especificação](spec.md) sem criar um segundo runtime, sem antecipar conhecimento
especulativo ao agente e sem ampliar as fronteiras de armazenamento do projeto. As decisões
partem do comportamento observado em staging e do código atual de incidentes, webhooks,
memória, knowledge base, persistência e console.

## Decisão 1 — Persistir cada ocorrência antes de decidir se ela cria trabalho

**Decisão**: introduzir `DeliveryAttempt`, `IncidentOccurrence` e `CorrelationDecision` como
registros duráveis. Uma tentativa representa cada travessia HTTP; uma ocorrência representa o
evento lógico; uma decisão registra como esse evento foi correlacionado. Quando o provedor
oferece um ID estável, a identidade lógica usa `(org_id, source, provider_event_id)`. Sem ID, um
fallback versionado combina payload normalizado, fingerprint e janela definida em constante.
Alertas legitimamente repetidos geram novas ocorrências mesmo quando se ligam ao mesmo
incidente; retries da mesma ocorrência geram novas tentativas auditáveis, não novo trabalho.

**Motivação**: hoje o webhook usa índices em memória para idempotência e deduplicação. O
estado desaparece em reinícios, não coordena múltiplas réplicas e não deixa evidência
auditável de por que uma nova investigação foi ou não aberta.

**Alternativas rejeitadas**:

- aumentar apenas a janela do cache em memória: reduz sintomas, mas não oferece consistência
  entre réplicas nem histórico;
- descartar eventos repetidos: apaga a frequência real e impede medir reincidência;
- modelar cada repetição como novo incidente: perpetua a explosão de incidentes e execuções.
- usar `received_at` na identidade lógica: cada retry pareceria um evento novo;
- usar ID vazio quando a origem não o fornece: eventos diferentes colidiriam globalmente.

## Decisão 2 — Separar ocorrência, incidente e investigação ativa

**Decisão**: manter no incidente o histórico imutável de `run_ids`, acrescentar
`active_run_id` e reivindicá-lo atomicamente na mesma unidade de trabalho que cria o run. Um
`DispatchClaim` durável registra owner, estado, versão e lease; o reaper recupera claims
abandonados após crash. A restrição de apenas um run ativo deve ser garantida no banco, não por
uma leitura seguida de escrita. A finalização, cancelamento, expiração e recuperação de um run
limpam a reivindicação e reconciliam o estado do incidente.

**Motivação**: o roteador atual pode criar um run diretamente depois de consultas não
atômicas. Em concorrência, duas entregas podem observar ausência de trabalho e iniciar duas
investigações. Também há incidentes em `investigating` sem run efetivamente ativo.

**Alternativas rejeitadas**:

- usar `run_ids` como indicador de atividade: a lista contém histórico e impediria uma nova
  investigação legítima depois de uma execução encerrada;
- mutex no processo: não funciona entre pods e perde o estado após reinício;
- criar o run e corrigir duplicatas depois: já incorre em custo, produz traços conflitantes e
  pode executar ações antes da reconciliação.
- claim sem lease: um pod morto bloquearia trabalho futuro indefinidamente.

## Decisão 3 — Tornar a criação do incidente concorrente e idempotente sem duplicar regras

**Decisão**: `IncidentLifecycle` continua sendo o único construtor canônico. O port de
persistência recebe uma operação de `claim_open_incident` que tenta gravar o incidente e, sob
uma restrição única parcial para correlações ainda vivas, retorna o registro vencedor quando
outro já existe. A ocorrência é então anexada ao vencedor e a decisão fica registrada.

**Motivação**: `open_for()` seguido de `upsert()` não fecha a janela de corrida. Levar a
garantia ao port mantém SQL dentro de `platform/persistence/` e permite o mesmo contrato nos
fakes e no PostgreSQL.

**Alternativa rejeitada**: criar um segundo serviço de construção para webhooks. Isso
divergiria da regra de um único caminho canônico e faria estados diferentes conforme a origem.

## Decisão 4 — Classificar recorrência em duas etapas, com evidência atual obrigatória

**Decisão**: usar duas formas de correlação, cada uma no momento correto:

1. antes de criar trabalho, somente regras determinísticas e dados estruturados publicados
   classificam a ocorrência como repetição ativa, candidata conhecida, ambígua, mudança
   material ou novo problema;
2. depois de existir ao menos uma observação atual, a recuperação semântica de postmortems e
   episódios pode ampliar ou refutar a hipótese, sempre deixando consulta, candidatos e
   influência no trace.

Uma candidata conhecida entra no pipeline canônico em modo `recurrence_validation`. Esse modo
coleta evidência atual, valida critérios e encerra cedo quando a confirmação é suficiente. Se
houver contradição, baixa confiança ou mudança material, o mesmo pipeline amplia o plano para
`full_investigation`.

O score é normalizado entre zero e um e existe somente no segundo momento: o classificador
anterior ao run não o recebe. Sem contradição, uma candidata só é claramente superior
quando alcança pelo menos 0,80 e abre margem de pelo menos 0,10 sobre a segunda colocada. Empate,
margem menor ou ausência de qualquer fato discriminante obrigatório mantém o caso ambíguo. Os
dois thresholds e a ordenação determinística de empate são constantes versionadas; alterá-los
exige nova execução do corpus rotulado.

Uma repetição enquanto o incidente está vivo liga-se ao incidente/run atual. Uma recorrência
depois do encerramento cria novo incidente relacionado ao anterior e ao postmortem; o sistema
não reabre nem reescreve o histórico fechado.

**Motivação**: a constituição exige recall dirigido pelo agente após evidência concreta e
proíbe pré-injeção especulativa. Ao mesmo tempo, igualdade exata de assinatura e critérios
publicados são fatos determinísticos adequados para decidir se vale abrir um run.

**Alternativas rejeitadas**:

- injetar os postmortems mais semelhantes no prompt inicial: cria viés de ancoragem, gasta
  contexto e viola o requisito de recall após evidência;
- responder a uma recorrência sem executar o pipeline: formaria um segundo runtime sem as
  garantias de trace e citação;
- sempre repetir a investigação completa: preserva qualidade, mas não alcança eficiência nem
  demonstra aprendizagem operacional.

## Decisão 5 — Modelar postmortem curado como domínio editorial próprio

**Decisão**: criar `platform/knowledge/postmortems/` com serviço, estados, revisões,
associações e feedback próprios. O objeto é distinto de um documento genérico ingerido pela
knowledge base. Um postmortem possui rascunho, revisões imutáveis e estados `draft`,
`published`, `superseded` e `archived`. Apenas a revisão publicada e vigente participa de
novas correlações.

**Motivação**: a extração atual de campos de documentos externos não oferece autoria,
publicação, supersessão, proveniência de incidentes/runs, critérios de recorrência nem
correções auditáveis.

**Alternativas rejeitadas**:

- adicionar somente uma etiqueta `postmortem` em `KnowledgeDocument`: não expressa o ciclo de
  vida nem impede o uso de rascunhos;
- editar o conteúdo publicado no lugar: apaga a base usada por decisões históricas;
- publicar automaticamente ao encerrar uma investigação: transforma inferências não
  revisadas em conhecimento institucional.

## Decisão 6 — Gerar rascunhos a partir do trace sem exigir uma chamada de LLM

**Decisão**: ações em incidente e investigação constroem deterministicamente um rascunho com
os fatos já persistidos: resumo, impacto, timeline, achados, citações, resolução e lacunas. O
serviço marca campos ausentes ou inferidos como `review_required`. Enriquecimento assistido
pode ser adicionado depois, mas não é pré-condição do fluxo nem pode publicar sozinho.

**Motivação**: o caminho precisa ser barato, reproduzível e fiel ao trace. Também deve funcionar
com nenhum provedor configurado.

**Alternativa rejeitada**: pedir a um modelo para recontar todo o incidente. Além do custo,
isso pode introduzir afirmações não sustentadas e duplicar o material já estruturado.

## Decisão 7 — Estender a busca de knowledge, sem criar uma ferramenta redundante

**Decisão**: o `KnowledgeService` passa a expor resultados tipados de postmortem e o mecanismo
de busca existente inclui um namespace dedicado `postmortems`. A capability de busca de
knowledge continua sendo a superfície do agente; ela retorna a categoria do resultado,
revisão, critérios, score e referência. Consultas, resultados escolhidos e influência são
registrados em uma associação durável.

**Motivação**: uma nova capability de “buscar postmortem” duplicaria seleção, permissões,
orçamento de schema e telemetria. A extensão mantém uma única forma de consultar conhecimento
e permite filtrar só revisões publicadas.

**Alternativa rejeitada**: consultar postmortems silenciosamente dentro do prompt builder. A
consulta deixaria de ser uma decisão visível do agente e não poderia ser isolada por ablação.

## Decisão 8 — Corrigir a identidade de evidência antes de permitir citações em postmortems

**Decisão**: a identidade persistida de evidência passa a ser
`(org_id, run_id, evidence_id)`. Todas as APIs internas de resolução e citação carregam o
`run_id`; referências de postmortem usam a mesma chave composta. A migração preserva cada linha
no run atualmente armazenado, detecta referências históricas irrecuperáveis e as marca como
não resolvidas, sem fabricar observações.

O downgrade deve reescrever identificadores locais que colidiriam ao remover `run_id` da chave
e atualizar referências na mesma transação antes de restaurar o formato antigo.

**Motivação**: `evidence_id` é local ao run, mas hoje participa de uma chave por organização e
pode sobrescrever evidência de outra execução. Uma base de conhecimento que cite essa chave
propagaria a corrupção para decisões futuras.

**Alternativas rejeitadas**:

- gerar IDs globais apenas daqui para frente: não corrige as APIs que continuam aceitando uma
  chave ambígua;
- copiar evidência para o postmortem: perde a relação com o trace original;
- tentar reconstruir observações sobrescritas: não existe fonte confiável para fazê-lo.

## Decisão 9 — Filtrar capacidades indisponíveis antes da seleção e lembrar falhas no run

**Decisão**: cada run recebe um snapshot auditável de disponibilidade construído com
configuração, permissões e verificação efetiva das integrações. Capacidades sabidamente
indisponíveis não entram no catálogo oferecido ao agente. Uma falha determinística de
indisponibilidade gera cache negativo limitado ao run, impedindo repetição sem ocultar uma
mudança em execuções futuras.

**Motivação**: staging registrou alto volume de chamadas que só informavam indisponibilidade.
A filtragem deve acontecer antes de gastar tokens na escolha da ferramenta, mas precisa
continuar explicável no trace.

**Alternativas rejeitadas**:

- ensinar o modelo por prompt a não repetir: não é uma garantia e ainda apresenta schemas
  inúteis;
- manter cache negativo entre runs: uma integração pode ser reparada entre ocorrências;
- tratar qualquer erro como indisponibilidade: esconderia falhas transitórias ou bugs reais.

## Decisão 10 — Reutilizar os limites do runtime e atribuir custo por fase

**Decisão**: preservar os limites, cache de chamadas idênticas, breaker de estagnação e budget
de contexto já existentes. Acrescentar limites nomeados para validação de recorrência em
`config/constants/`, nunca números mágicos no pipeline. O trace e as métricas agregam tokens,
chamadas e duração por fase: intake, evidence anchor, recall, recurrence validation, full
investigation e synthesis.

**Motivação**: o problema não exige um novo loop; exige melhor roteamento, catálogo menor e
mensuração que demonstre onde a economia aconteceu.

**Alternativa rejeitada**: criar um agente “rápido” separado. Isso violaria o runtime canônico
e tornaria os scores incomparáveis.

## Decisão 11 — Isolar aprendizagem e roteamento em duas ablações

**Decisão**: acrescentar dois eixos independentes ao harness, preservando os eixos existentes
de leitura de memória e estratégia:

- `postmortems`: mantém o corpus, mas desliga busca, matching e orientação por postmortem;
- `recurrence_path`: mantém a recuperação disponível, mas força o pipeline completo.

Os cenários comparam qualidade, cobertura de evidência, conclusão, tokens, chamadas, latência,
duplicidade de runs e precisão da classificação. Regressão de qualidade ou economia sem
confirmação impede a alegação de melhoria.

Comparações usam a mesma versão de cenário/corpus, runtime, provider/modelo, limites e período.
A célula de baseline desliga `postmortems` e `recurrence_path` para o mesmo cenário. O corpus
possui no mínimo 200 cenários rotulados antes da execução, com pelo menos 100 recorrências de
relevância conhecida e 100 negativos; reporta `recall@3`, falsa confirmação e empates.

O resultado vira `LearningEvaluation` pelo port incluído na `UnitOfWork`, com implementações fake
e PostgreSQL sob o mesmo contrato. O produtor do runtime canônico é composto como job
`learning.evaluation` no scheduler real do gateway e a rota de métricas lê o mesmo store; assim a
persistência não existe apenas no harness de testes.

**Motivação**: uma única chave “knowledge on/off” não separa o valor do conhecimento do valor
do caminho curto.

**Alternativa rejeitada**: medir somente redução de tokens. Um sistema barato que confirma o
problema errado não aprendeu.

## Decisão 12 — Evoluir API e console pelo contrato versionado existente

**Decisão**: adicionar endpoints REST sob `/v1/knowledge/postmortems`, mais ações de criação de
rascunho em incidentes e investigações. O console recebe a aba `Postmortem` em Knowledge e
ações nos detalhes correspondentes. Toda escrita passa pelas courier routes fechadas do
console: criação, revisão e feedback usam `knowledge.write`; publicação, supersessão e archive
usam a permissão explícita `knowledge.curate`; leituras usam `knowledge.read`. OpenAPI, cliente
gerado, fixtures/mockplane, i18n, tabela de permissões e testes evoluem juntos.

**Motivação**: esse é o caminho composto já usado pelo produto. Implementar somente backend ou
somente tela deixaria a feature inacessível ou não verificável.

**Alternativas rejeitadas**:

- usar Server Actions diretamente contra o backend: cria uma segunda superfície de transporte;
- reutilizar endpoints genéricos de documento: não representa transições editoriais;
- esconder filtros apenas em estado React: quebra deep link, refresh e histórico do browser.

## Decisão 13 — Tratar “concluído” como resultado diagnóstico explícito

**Decisão**: um run encerrado registra um resultado diagnóstico explícito — por exemplo,
`root_cause_found`, `known_recurrence_confirmed`, `inconclusive`, `no_signal` ou `failed` — e
os campos de cobertura do trace. A ausência de turnos, ferramentas ou episódio nunca é
contabilizada silenciosamente como sucesso. Incidente e run exibem o estado operacional e o
resultado diagnóstico como dimensões diferentes.

**Motivação**: staging contém execuções encerradas sem trabalho observável e incidentes presos
em investigação. Um único status “completed” mistura término de processo com qualidade do
diagnóstico.

**Alternativa rejeitada**: inferir qualidade apenas pela existência de um resumo. Texto pode
existir sem evidência, e a inferência impediria métricas confiáveis.
