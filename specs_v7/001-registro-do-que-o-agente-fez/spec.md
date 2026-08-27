# Feature Specification: Registro do que o agente fez — se rodou, está escrito

**Feature Branch**: `feat/v7-001-registro-do-que-o-agente-fez`

**Created**: 2026-08-23

**Status**: Draft

**Input**: User description: "Uma investigação que fez N tool calls deixa N tool
calls no store — com o que cada uma devolveu, o custo por turno e o que foi
tocado — lido de volta depois de reload. E o relato vira dois fatos: headline
(uma sentença) e report (documento markdown)."

**Referência visual (DoD)**: nenhuma. Esta feature é **backend-only** e **não
tem tela própria**. Toda a superfície que lê o registro — markdown renderizado,
título/aba/coluna vindos do headline, transcript, painel de custo, "What this
investigation touched", supressão do controle de run vivo num run terminado — é
da **010-leitura-do-relato**. Por isso **não há acceptance spec Playwright nem
seção de "Alegações normativas" aqui**: não há tela para medir. O que substitui
a evidência de tela é a **evidência de banco no staging**, enumerada como
consultas exatas na seção "Evidência exigida" abaixo.

## Onde o produto está hoje

Verificado em 2026-08-23 contra o staging real e contra a árvore:

- 37 investigações `completed` no banco, e `run_turns = 0`, `tool_calls = 0`,
  `evidence = 0`. Só `trace_events = 73` — aproximadamente dois por run, o
  começo e o fim. A narrativa sobrevive; a mecânica não.
- Todo `agent_runs.summary` recente começa com `###`: o documento markdown
  inteiro do modelo está gravado no campo que o contrato oferece como se fosse
  uma sentença.
- O contrato (`gateway/http/routes/investigations.py:35-60`) carrega
  `summary: str | None` e nada mais. Não existe headline separado de report.
- O `RunRecorder` (`platform/runs/recorder.py`) sabe escrever turno, chamada e
  evidência, com guardrail e truncação na entrada. O único chamador de
  `record_turn`/`record_call` fora de teste é o semeador de demonstração.
- O caminho de serving compõe `ReActInvestigationRunner`
  (`gateway/runtime/investigator.py`), que constrói um `ReActLoop` por
  investigação com `investigation_hooks()` — um registro de hooks que contém
  **um** hook, a guarda de janela do incidente. Nenhum hook escreve no store.
- O docstring de `start_investigation` (`gateway/http/orchestration.py:42-62`)
  já nomeia o seam e já avisa: "só um dos dois deve estar ligado por vez, ou a
  entrada seria registrada duas vezes".
- O docstring de `core/agent/hooks/builtin/tracing.py` afirma que "os registros
  de turno são o trace durável e são escritos conforme o run acontece". No
  caminho de serving isso é falso hoje, e essa é a distância exata que esta
  feature fecha.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Uma investigação que rodou deixa o que fez escrito (Priority: P1)

Um operador abre uma investigação que terminou há uma hora, num processo que
foi reiniciado desde então, e encontra a mesma quantidade de turnos e de
chamadas de capacidade que a investigação realmente fez, com o que cada chamada
devolveu e a evidência que produziu. Nada disso vem do processo que rodou a
investigação; tudo vem do store.

**Why this priority**: é a decisão que governa a onda. Um produto que executa e
não consegue contar o que fez entrega uma conclusão sem trabalho — e a
conclusão sem trabalho é exatamente o que um operador às 3 da manhã não pode
verificar nem contestar.

**Independent Test**: rodar uma investigação, derrubar e subir o processo, pedir
o replay do run e conferir que ele traz turnos, chamadas e evidência; conferir
as mesmas contagens direto no banco.

**Acceptance Scenarios**:

1. **Given** uma investigação que fez N chamadas de capacidade, **When** o
   replay do run é pedido depois de um reinício do processo, **Then** ele
   devolve N chamadas, cada uma com o nome da capacidade, o desfecho, os
   argumentos e o resultado.
2. **Given** a mesma investigação, **When** as contagens são lidas direto do
   banco, **Then** turnos, chamadas e evidência daquele run são maiores que
   zero e batem com o que o replay devolveu.
3. **Given** uma investigação interrompida no meio, **When** o run é lido
   depois, **Then** os turnos e as chamadas que já tinham acontecido estão
   gravados — o registro não espera o fim do run para existir.
4. **Given** uma investigação que não conseguiu chamar nenhuma capacidade,
   **When** o run é lido, **Then** ele tem os turnos que houve e nenhuma
   chamada, e isso é um registro verdadeiro, não um registro ausente.

---

### User Story 2 - O custo de uma investigação é um fato registrado (Priority: P1)

O operador vê, por turno, qual modelo respondeu, quantos tokens entraram e
saíram, e quanto aquilo custou. Quando o provedor não publica preço, o produto
diz que aquele turno não tem preço — nunca diz que custou zero.

**Why this priority**: sem custo por turno o produto não tem como responder
"quanto me custou investigar isto", que é a primeira pergunta de quem decide se
liga a autonomia. E um zero inventado é pior que um vazio: um total que parece
autoritativo e está errado é o que ninguém mais questiona.

**Independent Test**: rodar uma investigação contra o provedor configurado e
conferir que cada turno gravado nomeia o modelo, traz tokens de entrada e de
saída, e traz custo quando o provedor precifica.

**Acceptance Scenarios**:

1. **Given** uma investigação que tomou vários turnos, **When** o replay é
   pedido, **Then** cada turno nomeia o modelo que respondeu e traz seus tokens
   de entrada e de saída.
2. **Given** um turno atendido por um modelo com preço publicado, **When** o
   turno é lido, **Then** ele traz o custo daquele turno.
3. **Given** um turno atendido por um modelo sem preço publicado, **When** o
   turno é lido, **Then** ele se declara sem preço, e o total do run não conta
   aquele turno como zero.
4. **Given** um run inteiro, **When** o custo total é pedido, **Then** ele é a
   soma dos turnos precificados, e o run informa quantos turnos ficaram sem
   preço.

---

### User Story 3 - O relato é dois fatos: uma sentença e um documento (Priority: P1)

Quem lê uma investigação encontra uma sentença que serve de nome — cabe num
título, numa coluna de lista, numa notificação — e, separada dela, o documento
inteiro que o modelo escreveu. Os dois são campos distintos do contrato, e
nenhum consumidor precisa cortar um para obter o outro.

**Why this priority**: o defeito visível mais caro da rodada. `summary` carrega
os dois misturados, o console assume que é uma sentença, e o resultado é
markdown cru como H1, como título de aba e como coluna de lista. A separação é
de design, não de apresentação: nenhuma tela consegue inventar uma sentença a
partir de um documento sem mentir.

**Independent Test**: pedir uma investigação ao gateway e conferir que a
resposta traz a sentença e o documento em campos separados, e que a sentença
não é o começo do documento.

**Acceptance Scenarios**:

1. **Given** uma investigação concluída, **When** ela é pedida ao gateway,
   **Then** a resposta traz a sentença e o documento como dois campos
   distintos.
2. **Given** uma investigação cujo modelo entregou a sentença pedida, **When**
   ela é lida, **Then** a sentença é a que o modelo escreveu, e ela cabe em uma
   linha.
3. **Given** uma investigação cujo modelo não entregou sentença nenhuma,
   **When** ela é lida, **Then** o produto serve uma sentença derivada do
   sujeito da investigação, e **nunca** o começo do documento.
4. **Given** uma investigação de antes desta mudança, **When** ela é lida,
   **Then** ela traz o documento que sempre teve e uma sentença derivada — o
   histórico não fica com título vazio nem com markdown por título.
5. **Given** qualquer investigação, **When** a sentença é lida, **Then** ela
   não contém marcação de markdown.

---

### User Story 4 - A investigação diz a que incidente pertence e o que tocou (Priority: P2)

Abrindo uma investigação, o operador vê a qual incidente ela responde e quais
recursos ela efetivamente consultou durante o trabalho — lidos do que foi
registrado, não deduzidos de uma lista que o cliente varreu.

**Why this priority**: P2 porque é a terceira coisa que a tela mostra, não a
primeira. Mas é a diferença entre "esta investigação olhou o storage do nó 2" e
"nada vinculado" — e hoje o console encontra o incidente varrendo `/v1/incidents`
por um `run_id`, o que é uma leitura limitada por página que falha em silêncio
no run mais antigo.

**Independent Test**: rodar uma investigação por alerta, pedir o run, e conferir
que a resposta nomeia o incidente de origem e os recursos que as chamadas
tocaram, sem que o cliente precise pedir outra lista.

**Acceptance Scenarios**:

1. **Given** uma investigação iniciada por um alerta, **When** o run é lido,
   **Then** a resposta nomeia o incidente ao qual o run está vinculado.
2. **Given** uma investigação que consultou recursos nomeados, **When** o run é
   lido, **Then** a resposta lista esses recursos.
3. **Given** uma investigação iniciada por um operador, sem incidente, **When**
   o run é lido, **Then** a resposta diz que não há incidente vinculado, e isso
   é diferente de uma leitura que falhou.

---

### User Story 5 - Um só lugar escreve (Priority: P1)

Cada fato de uma investigação é escrito por exatamente um caminho. Uma entrada
de linha do tempo não aparece duas vezes porque dois colaboradores compostos
resolveram gravá-la.

**Why this priority**: o próprio docstring de `start_investigation` avisa disso,
e esta feature liga justamente o segundo lugar. Ligar o recorder sem decidir
quem escreve o recibo é como a duplicação entra.

**Independent Test**: rodar uma investigação por alerta e conferir que a linha
do tempo do incidente tem exatamente um recibo, e que o log de eventos do run
não tem evento repetido.

**Acceptance Scenarios**:

1. **Given** uma investigação disparada por alerta, **When** a linha do tempo do
   incidente é lida, **Then** há exatamente uma entrada de recibo.
2. **Given** a mesma investigação, **When** o log de eventos do run é lido,
   **Then** nenhum evento aparece duas vezes.
3. **Given** a árvore ao final desta feature, **When** se pergunta quem grava o
   trace de uma investigação em produção, **Then** existe uma resposta e ela é
   única.

### Edge Cases

- **Run que falha antes do primeiro turno.** Nada de turno para gravar. O run
  fecha com o status e o motivo, e a ausência de turnos é o registro correto —
  não um registro faltando.
- **Run cancelado no meio de uma chamada.** O laço só para entre iterações, por
  design. A chamada em voo termina e é gravada; o cancelamento é o evento
  seguinte. Um resultado que aconteceu e não foi escrito é a única coisa que uma
  sessão retomável não sobrevive.
- **Processo que morre com o run em andamento.** O que já foi gravado fica. O
  run é marcado interrompido por quem o encontrar, e "ninguém sabe até onde isto
  chegou" continua sendo um fato distinto de "falhou".
- **Chamada cujo resultado é enorme.** A truncação acontece antes do limite do
  store e deixa marca. Um trace que estourou o limite do banco é um trace
  perdido depois de o run já ter pago o custo de produzi-lo.
- **Segredo num argumento ou num resultado.** O scan de guardrail roda no
  caminho de escrita, antes da persistência, e a redação é o que é gravado.
  Não pode existir caminho do chamador até o store que pule isso.
- **Modelo que devolve a sentença com marcação, ou com três parágrafos.** A
  sentença é normalizada: uma linha, sem marcação, cortada num limite
  declarado. Um modelo que ignorou a instrução não vira um título de três
  parágrafos.
- **Modelo que devolve sentença idêntica à primeira linha do documento.** É
  aceitável — o que é proibido é o produto *derivar* a sentença do documento
  quando o modelo não a deu.
- **Run sem alerta e sem incidente.** A sentença cai para o objetivo declarado
  pelo operador, e o vínculo de incidente é explicitamente ausente.
- **Sub-agente.** Um sub-agente é um run aninhado, com turnos e chamadas
  próprios ligados ao pai. Esta feature não altera essa forma; ela precisa não
  quebrá-la, e o registro do pai não absorve os turnos do filho.
- **Run antigo, de antes desta mudança.** Continua legível: documento onde
  sempre esteve, sentença derivada na leitura, e nenhum turno inventado para
  preencher a tela.

## Requirements *(mandatory)*

### Registro do que aconteceu

- **FR-001**: Toda investigação executada pelo caminho de serving DEVE gravar um
  registro de turno por iteração do laço.
- **FR-002**: Toda chamada de capacidade que uma investigação fizer DEVE virar
  um registro de chamada, vinculado ao turno em que aconteceu.
- **FR-003**: Um registro de chamada DEVE carregar o nome da capacidade, o
  desfecho, os argumentos com que foi chamada e o resultado que devolveu.
- **FR-004**: Uma chamada que falhou DEVE ser gravada com o desfecho de falha e
  com a classificação do erro, não omitida.
- **FR-005**: Uma chamada recusada por política DEVE ser gravada como recusada,
  e não como ausente nem como falha.
- **FR-006**: Toda observação que uma investigação produzir DEVE virar um
  registro de evidência do run.
- **FR-007**: Um registro de evidência DEVE ser vinculável à chamada que o
  produziu.
- **FR-008**: Os registros DEVEM ser escritos enquanto o run acontece, e não ao
  final dele.
- **FR-009**: Um run interrompido DEVE conservar tudo que já havia sido gravado
  até a interrupção.
- **FR-010**: A escrita de um registro NÃO DEVE poder pular a redação de
  guardrail nem a truncação que o recorder já aplica.
- **FR-011**: A falha ao gravar um registro NÃO DEVE derrubar a investigação;
  ela DEVE ser registrada como falha de gravação.
- **FR-012**: O registro de um sub-agente DEVE continuar sendo um run aninhado
  próprio, com o vínculo ao run pai.

### Custo e tokens

- **FR-013**: Cada registro de turno DEVE nomear o modelo que atendeu aquele
  turno.
- **FR-014**: Cada registro de turno DEVE carregar os tokens de entrada e os de
  saída daquele turno.
- **FR-015**: Cada registro de turno DEVE carregar a duração daquele turno.
- **FR-016**: Um turno cujo provedor publica preço DEVE carregar o custo daquele
  turno.
- **FR-017**: Um turno cujo provedor não publica preço DEVE ser gravado **sem
  custo**, e NÃO DEVE ser gravado com custo zero.
- **FR-018**: O total de custo de um run DEVE somar apenas os turnos
  precificados.
- **FR-019**: A leitura de um run DEVE informar quantos turnos ficaram sem
  preço.
- **FR-020**: O registro de turno DEVE carregar as capacidades que estavam em
  oferta naquele turno.
- **FR-021**: O registro de turno DEVE carregar a razão pela qual aquelas
  capacidades foram as oferecidas.

### O relato como dois fatos

- **FR-022**: O contrato de uma investigação DEVE carregar uma sentença de
  relato e um documento de relato como campos distintos.
- **FR-023**: A sentença DEVE ser uma linha só.
- **FR-024**: A sentença NÃO DEVE conter marcação de markdown.
- **FR-025**: A sentença DEVE ter tamanho máximo declarado, e um valor maior
  DEVE ser cortado na fronteira de palavra.
- **FR-026**: O documento DEVE carregar o texto do modelo sem alteração de
  conteúdo.
- **FR-027**: O prompt de entrega DEVE pedir ao modelo a sentença além do
  documento.
- **FR-028**: Quando o modelo não devolver a sentença, o produto DEVE sintetizar
  uma de forma determinística.
- **FR-029**: A sentença sintetizada DEVE derivar do sujeito da investigação — o
  nome do alerta e o recurso, quando existirem, e o objetivo declarado quando
  não existirem.
- **FR-030**: A sentença sintetizada NÃO DEVE derivar do corpo do documento.
- **FR-031**: A leitura de um run anterior a esta mudança DEVE devolver o
  documento que ele sempre teve.
- **FR-032**: A leitura de um run anterior a esta mudança DEVE devolver uma
  sentença sintetizada, e nunca uma sentença vazia.
- **FR-033**: O campo `summary` do contrato DEVE continuar existindo nesta
  feature, servindo o mesmo texto do documento, para que nenhuma superfície
  fique sem leitura entre esta feature e a que reescreve as telas.
- **FR-034**: A descrição do campo `summary` no contrato DEVE declará-lo
  substituído pelos dois campos novos.

### Vínculos

- **FR-035**: A leitura de um run DEVE dizer a que incidente ele pertence,
  quando pertence a algum.
- **FR-036**: A leitura de um run sem incidente DEVE dizer explicitamente que
  não há incidente, de forma distinguível de uma leitura que falhou.
- **FR-037**: A leitura de um run DEVE listar os recursos que suas chamadas
  tocaram.
- **FR-038**: A lista de recursos tocados DEVE derivar do que foi registrado, e
  não dos sujeitos declarados no alerta.
- **FR-039**: A leitura de um run NÃO DEVE exigir que o cliente varra uma lista
  paginada de incidentes para descobrir o vínculo.

### Um só escritor

- **FR-040**: Exatamente um caminho DEVE gravar o recibo do alerta na linha do
  tempo do incidente.
- **FR-041**: O caminho que não for o escolhido DEVE deixar de existir nesta
  mesma mudança, e não ficar desligado por configuração.
- **FR-042**: Exatamente um caminho DEVE gravar o trace de uma investigação.
- **FR-043**: O caminho de pipeline por estágios NÃO DEVE ganhar chamador de
  produção nesta feature.

### Composição

- **FR-044**: O recorder DEVE ser alcançável a partir da composition root que
  serve o produto, e não apenas de testes.
- **FR-045**: A composição DEVE valer tanto para a investigação disparada por
  operador quanto para a disparada por alerta.
- **FR-046**: A composição DEVE sobreviver à reconstrução do investigador que
  acontece depois que a configuração é lida.
- **FR-047**: Um deployment que não nomeia runtime de investigação DEVE
  continuar subindo, sem recorder e sem erro.
- **FR-048**: Deve existir um teste que reprove se o caminho de serving deixar
  de compor o recorder.

### Migração e contrato de fronteira

- **FR-049**: Toda coluna nova DEVE vir por migração com caminho de volta.
- **FR-050**: A migração NÃO DEVE reescrever o conteúdo de nenhuma linha
  existente.
- **FR-051**: O documento de contrato HTTP committed DEVE ser regenerado com os
  campos novos.
- **FR-052**: O cliente TypeScript gerado DEVE ser regenerado a partir desse
  documento, na mesma feature.
- **FR-053**: As fixtures do plano de dados simulado DEVEM passar a trazer os
  campos novos.
- **FR-054**: A checagem de desvio entre documento e cliente gerado DEVE passar.

### Evidência

- **FR-055**: O efeito desta mudança sobre a suíte de cenários sintéticos DEVE
  ser medido e reportado.
- **FR-056**: As contagens de turnos, chamadas e evidência no banco de staging,
  depois de uma investigação disparada por alerta real, DEVEM ser capturadas
  como evidência.
- **FR-057**: A verificação completa do repositório DEVE ficar verde ao final,
  tendo partido de verde.

### Key Entities

- **Turno**: uma iteração do laço — o que foi pedido ao modelo, o que voltou,
  quanto custou, quanto demorou, e quais capacidades estavam em oferta.
  Ordenado por índice, nunca por relógio: dois turnos podem dividir um
  milissegundo, não podem dividir uma posição.
- **Chamada de capacidade**: uma invocação, com o nome, os argumentos, o
  resultado, o desfecho e o tempo. Pertence a um turno.
- **Evidência**: uma observação que o sistema fez, citável numa conclusão.
  Gravada separada do turno de propósito: o transcript é o que o modelo disse, a
  evidência é o que o sistema observou, e só a segunda sustenta uma conclusão.
- **Sentença de relato (headline)**: uma linha, sem marcação, que serve de nome
  para a investigação. Pedida ao modelo; sintetizada do sujeito quando ele não a
  der.
- **Documento de relato (report)**: o texto que o modelo escreveu, íntegro,
  destinado a ser lido como documento e não como título.
- **Vínculo**: o incidente de origem de um run e os recursos que suas chamadas
  tocaram.

## Success Criteria *(mandatory)*

- **SC-001**: Depois de uma investigação real no staging, a contagem de turnos,
  de chamadas e de evidência daquele run no banco é maior que zero.
- **SC-002**: A contagem de chamadas no banco é igual à contagem de chamadas que
  o replay do run devolve.
- **SC-003**: O replay de um run lido depois de um reinício do processo é igual
  ao que um cliente observou ao vivo durante o run.
- **SC-004**: Todo turno gravado nomeia um modelo e traz tokens de entrada e de
  saída.
- **SC-005**: Um run atendido por modelo precificado traz custo maior que zero;
  um atendido por modelo sem preço traz o run declarando turnos sem preço em vez
  de custo zero.
- **SC-006**: Toda investigação concluída responde com sentença não vazia e
  documento não vazio, e a sentença é uma linha sem marcação.
- **SC-007**: Uma investigação anterior a esta mudança responde com sentença não
  vazia e com o documento que ela sempre teve.
- **SC-008**: Nenhuma sentença servida pelo produto é um prefixo do documento
  que ela acompanha, exceto quando o próprio modelo a escreveu assim.
- **SC-009**: A linha do tempo de um incidente investigado tem exatamente um
  recibo.
- **SC-010**: Uma busca na árvore por quem constrói o recorder em produção
  devolve uma composition root, com arquivo e linha.
- **SC-011**: A migração aplica e desaplica contra um banco com dados, e o
  conteúdo das linhas existentes é idêntico antes e depois do ciclo.
- **SC-012**: A checagem de desvio entre o documento de contrato e o cliente
  gerado passa.
- **SC-013**: A suíte de cenários sintéticos tem seu resultado antes e depois
  comparado, e a diferença é reportada.
- **SC-014**: A verificação completa do repositório passa integralmente,
  comparada contra a mesma verificação rodada antes desta feature.

## Evidência exigida (staging)

O ciclo de validação da onda roda ao fim do slot: o orquestrador faz o deploy,
dispara uma investigação a partir de um alerta real do Alertmanager, e coleta a
evidência. Esta feature alega gravação, então as consultas abaixo fazem parte do
DoD e são rodadas contra `ninjasre-stg-db` em `10.20.20.54`. `:run` é o
identificador do run recém-executado; `:org` é a organização do deployment.

```sql
-- 1. O run existe, terminou, e tem sentença e documento.
SELECT run_id, status, headline, left(summary, 60) AS report_head
FROM agent_runs
WHERE org_id = :org AND run_id = :run;

-- 2. As três tabelas que a tela lê deixaram de estar zeradas para este run.
SELECT
  (SELECT count(*) FROM run_turns  WHERE org_id = :org AND run_id = :run) AS turns,
  (SELECT count(*) FROM tool_calls WHERE org_id = :org AND run_id = :run) AS calls,
  (SELECT count(*) FROM evidence   WHERE org_id = :org AND run_id = :run) AS evidence,
  (SELECT count(*) FROM trace_events WHERE org_id = :org AND run_id = :run) AS events;

-- 3. Cada turno nomeia modelo e tokens; custo é ausente, nunca zero fabricado.
SELECT index,
       usage ->> 'model'             AS model,
       usage ->> 'prompt_tokens'     AS prompt_tokens,
       usage ->> 'completion_tokens' AS completion_tokens,
       usage ->  'cost'              AS cost
FROM run_turns
WHERE org_id = :org AND run_id = :run
ORDER BY index;

-- 4. Cada chamada tem nome, desfecho e corpo — e as que falharam continuam lá.
SELECT tool_name, status, error IS NOT NULL AS has_error,
       jsonb_array_length(coalesce(evidence_ids, '[]'::jsonb)) AS evidence_links
FROM tool_calls
WHERE org_id = :org AND run_id = :run
ORDER BY recorded_seq;

-- 5. O recibo do alerta foi gravado uma vez só.
SELECT kind, count(*)
FROM incident_timeline
WHERE org_id = :org
  AND incident_id = (SELECT incident_id FROM incidents
                     WHERE org_id = :org AND :run = ANY(run_ids))
GROUP BY kind
ORDER BY kind;

-- 6. Nenhum run recente volta a ter as três tabelas zeradas.
SELECT r.run_id,
       (SELECT count(*) FROM run_turns t WHERE t.org_id = r.org_id AND t.run_id = r.run_id) AS turns
FROM agent_runs r
WHERE r.org_id = :org AND r.status = 'completed'
  AND r.started_at > now() - interval '1 hour'
ORDER BY r.started_at DESC;
```

Além do banco, e no mesmo ciclo: `GET /v1/runs/{run}/replay` devolve os turnos
com custo, e `GET /v1/runs/{run}` devolve sentença e documento. Os dois são
leituras — **staging-safe**, e são os únicos exercícios desta feature contra o
ambiente compartilhado. Esta feature não roda nada que escreva em staging além
da própria investigação que o orquestrador dispara.

## Assumptions

- **O laço canônico é o caminho de produção.** `ReActInvestigationRunner`
  constrói um `ReActLoop` por investigação, e é ele que o deployment executa. O
  pipeline por estágios existe, é testado, e não tem chamador de produção — dar
  um a ele é decisão de outra feature, e esta spec não a toma.
- **O `RunRecorder` está certo e não precisa ser reescrito.** Ele já faz
  guardrail antes de persistir, truncação antes do limite do store, e log antes
  do broker. O que falta é ser chamado. Esta feature usa o que existe e só o
  estende onde o tipo impede dizer a verdade — o custo ausente.
- **O documento continua morando onde mora.** `agent_runs.summary` já guarda o
  texto do modelo, com 37 linhas de dados reais. Renomear a coluna seria uma
  migração de conteúdo sem ganho; a coluna nova é a da sentença.
- **A sentença é gerada, não extraída.** Pedir ao modelo é o caminho primário;
  sintetizar do sujeito é o fallback. Cortar o documento nunca é nem um nem
  outro — foi exatamente o que produziu `### Incident Findings...` como título.
- **`summary` sobrevive a esta feature por uma feature só.** Ela sai do contrato
  quando o último leitor sair, e o último leitor é do console, que é da 010.
  Mantê-lo aqui é o que evita um slot inteiro de console sem relato.
- **O staging tem Gemini verificado e alertas reais chegando.** A investigação
  de evidência é disparada por um alerta que o Alertmanager já entrega, não por
  um alerta fabricado.

## Dependencies

- Depende da **000** apenas por regra: o Constitution Check deste plano é feito
  contra a constituição como ela fica depois dela, incluindo a cláusula de que
  um mecanismo não composto não é entrega. Não há dependência de código.
- Não depende de nenhuma outra feature da onda. Roda no primeiro slot, em
  paralelo com a **020**, que é console e não toca nada daqui.
- **Bloqueia a 010**: toda a leitura do relato depende destes campos e destes
  registros existirem.
- **Bloqueia a 040**: a metade que age grava proposta, aprovação e execução no
  mesmo trace, e precisa que o trace esteja sendo escrito.
- **Bloqueia a 080**: o cenário ponta-a-ponta exige transcript gravado.

## Out of Scope

- **Qualquer tela.** Markdown renderizado, título vindo do headline, coluna de
  sujeito na lista, painel de custo, transcript, "What this investigation
  touched", supressão do controle de run vivo num run terminado: tudo é da 010.
- **A composição dos portões de remediação e autonomia.** É da 040, e esta
  feature deliberadamente não dá chamador de produção ao pipeline por estágios
  para não colidir com ela.
- **Filtrar as ferramentas oferecidas pelas integrações que o time configurou.**
  Mesmo seam, feature 040.
- **Id opaco de incidente e a dupla codificação na borda do console.** É da 020,
  que roda no mesmo slot e não compartilha arquivo com esta.
- **Remover `summary` do contrato.** Fica para quando o último leitor sair.
- **Backfill de sentença nas linhas existentes.** A sentença de um run antigo é
  sintetizada na leitura, não escrita no banco: sintetizar na escrita gravaria
  como fato do run algo que a leitura derivou.
- **Retenção e poda de trace.** A capacidade já existe; escrever mais trace não
  muda a política, e mudá-la aqui seria escopo alheio.
