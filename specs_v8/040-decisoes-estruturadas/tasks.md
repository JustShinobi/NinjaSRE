# Tasks: Decisões estruturadas — o cartão no lugar do JSON, e a expirada com saída

**Input**: Design documents from `specs_v8/040-decisoes-estruturadas/`

**Prerequisites**: spec.md, plan.md. A 000-fundacao-visual está mergeada (S0):
tokens, chip com contorno, formas, fontes e shell novos existem e estão
congelados. A par deste slot é a 060-telas-de-area, dona dos single-write.

**Tests**: acceptance-first. O acceptance das catorze alegações normativas
aterrissa **antes** de qualquer implementação e é confirmado vermelho, com a
mensagem real de cada uma registrada.

**Marcação**: `[x]` feita; `[ ]` pendente; `[~]` encerrada sem execução, com a
razão na própria linha. Um `[~]` nunca é um `[x]` envergonhado.

## Regras que valem para toda tarefa deste arquivo

1. **Nada de identificador de planejamento em arquivo committed.** A
   substância vai no arquivo; a referência fica na spec.
2. **A fundação visual está congelada.** Nenhuma tarefa edita
   `console/src/design/tokens.ts`, `icons.tsx`, `components/status.tsx` ou
   `console/public/fonts/`. Token ou ícone que faltar é declarado no
   relatório final, com o valor proposto.
3. **Single-write é da 060 neste slot.** Nenhuma tarefa edita
   `console/src/i18n/*.ts`, `console/src/shell/routes.ts` ou
   `console/visual/screens.json`. As chaves i18n (em `en` **e** `pt-BR`) e a
   linha nova do registro visual são declaradas no relatório final, e o
   código referencia as chaves. **Nenhuma tarefa edita
   `console/src/surfaces/screens/incident-decision-controls.tsx`** também —
   é importado por `approvals.tsx` (desta feature) e por
   `incident-detail.tsx` (060); o cartão novo o compõe como está.
4. **Nenhuma linha de aprovação é apagada.** Repropor, descartar e expirar
   marcam estado; uma tarefa que precise de `DELETE` passou do alvo.
5. **Arquivo gerado é regenerado, nunca editado à mão** — documento de API,
   cliente TS, dataset simulado.
6. **Gate não é afrouxado para a mudança passar.**
7. **Nenhuma edição antes de T004.** Os `file:line` de serving são cravados e
   registrados primeiro; editar um arquivo presumido é como a onda anterior
   perdeu janelas.

---

## Phase 0: Linha de base

- [ ] T001 Rodar `make verify` na árvore intacta e guardar o log fora do
      repositório: exit code, contagem, falhas. Se não estiver verde, parar e
      reportar antes de escrever qualquer coisa.
- [ ] T002 Capturar o "antes" no staging, fora do repositório:
      `GET /v1/approvals` completo (a expirada real), o badge renderizado da
      sidebar (screenshot), e a contagem de linhas da tabela de aprovações
      (SQL fixado em T004). São os números contra os quais SC-002/SC-003 e a
      regra "nada é apagado" são medidos.
- [ ] T003 Registrar a contagem e o resultado atuais da suíte de cenários
      sintéticos — o "antes" da medição exigida de toda mudança que possa
      afetar investigação. "Sem efeito" é resposta aceitável no fim; "não
      medido" não é.
- [x] T004 Cravar com codegraph e registrar no controle, com `file:line`:
      (a) o arquivo do gateway que serve `GET/POST /v1/approvals*`
      (`gateway/http/routes/approvals.py`, incluindo `decide_approval` em
      `/{approval_id}/decision` — confirmar a linha atual);
      (b) a raiz de composição do gate de remediação que a onda anterior
      compôs. O plano já crava isto como `compose_remediation()`
      (`gateway/http/remediation.py:177`, chamada por
      `gateway/http/lifespan.py:117`) enfileirando via `RequestBuilder.queue()`
      (`platform/remediation/request.py:238`) — **não**
      `ProposalQueue.propose()` (`platform/proposals/service.py:167`, que é de
      config/conhecimento/detector, não remediação). Esta tarefa reconfirma
      esses `file:line` com codegraph antes de qualquer edição, não os
      redescobre do zero;
      (c) o modelo/tabela do store de aprovações e se `discarded` e vínculo
      de origem cabem sem migração (decisão binária do plano §"Decisões" 5);
      (d) o SQL literal de contagem de linhas para T002/DoD.
      **Nenhuma tarefa de implementação começa antes desta.**
      Feito — ver `controle.md`, seção T004. Achado adicional: nada em
      produção chama `expire_due()` (nem rota, nem job agendado); é um Artigo
      XIV pré-existente que esta feature fecha ao chamar o sweep dentro de
      `GET /v1/approvals`.

## Phase 1: Acceptance e contratos primeiro, confirmados vermelhos

- [ ] T005 Escrever
      `console/tests/e2e/decisoes-estruturadas.acceptance.spec.ts` com uma
      asserção por alegação normativa (AN-01…AN-14), viewport 1440×1040,
      staging-safe marcadas conforme a spec (AN-08 propose-only). Confirmar
      vermelho e registrar a mensagem real de cada alegação.
- [ ] T006 [P] Contrato pytest da listagem: `GET /v1/approvals` devolve, por
      decisão, cada campo do shape do plano (nomes literais), com ausência
      declarada e nunca chave omitida; `state=pending` (default) exclui
      expiradas e decididas; `state=expired` devolve somente expiradas;
      `state=decided` devolve approved/rejected/discarded mais recentes
      primeiro com `decided_by`/`verdict`. Confirmar vermelho.
- [ ] T007 [P] Contrato pytest do detalhe: `GET /v1/approvals/{id}` carrega o
      mesmo shape mais `raw` com o documento integral; o `title` do detalhe é
      idêntico ao da listagem para o mesmo id. Confirmar vermelho.
- [ ] T008 [P] Contrato pytest da re-proposta: em expirada → `201` com
      pendente nova ligada à origem; segunda chamada → `409` devolvendo a
      mesma pendente; origem irrecuperável → `422` com causa nomeada; em
      pendente → recusa. Confirmar vermelho (a rota não existe).
- [ ] T009 [P] Contrato pytest do descarte: expirada → `discarded` com autor
      registrado, some de `state=pending`, aparece em `state=decided`;
      contagem de linhas da tabela inalterada. Confirmar vermelho.
- [ ] T010 [P] Unidade pytest da derivação de título: capacidade+alvo →
      sentença; sem verbo conhecido → `summary`; nunca string vazia, nunca o
      nome cru da capacidade, nunca id. Casos: o payload real do staging
      (fato 2 da spec) e um documento mínimo. Confirmar vermelho.
- [ ] T011 [P] Unidade pytest do score: a tabela do plano (base por
      `side_effect_level`, +1 por raio, teto 5) — incluindo o caso real do
      staging (escrita reversível, `depth:3` → 3). Confirmar vermelho.
- [ ] T012 [P] Unidade vitest do cartão: pendente renderiza as seis seções
      nomeadas; expirada renderiza rodapé com os dois controles e sem
      Aprovar; decidida renderiza desfecho; campo ausente vira ausência
      declarada; nenhum JSON fora de `<details>`. **Um caso com interação
      aberta (renderiza `DecisionControls`) e um caso sem (renderiza
      `IncidentDecisionControls`)** — o segundo é o único que o staging
      exercita hoje (plano, Riscos), e um teste só contra o primeiro não o
      cobriria. Confirmar vermelho.
- [ ] T013 [P] Unidade vitest do badge: só pendentes não expiradas contam;
      expirada sozinha → zero/ausente. Confirmar vermelho.
- [ ] T014 [P] Caracterização (deve passar antes e depois): decidir por
      `POST /v1/interactions/{id}/approve|reject` continua com o
      comportamento atual — a feature não muda o mecanismo de decidir.

## Phase 2: Servidor

- [ ] T015 Projeção por campo na listagem e no detalhe de aprovações
      (arquivo de T004a), com as derivações de T016/T017 e ausência
      declarada; `state=` e ordenações do plano. Verde em T006/T007.
- [ ] T016 Derivação de título humano numa função única do lado servidor,
      usada pelas duas projeções. Verde em T010.
- [ ] T017 Derivação de score de risco (tabela do plano), servida como
      `risk{class, score, scale}`. Verde em T011.
- [ ] T018 `POST /v1/approvals/{approval_id}/repropose` chamando o mecanismo
      de proposta composto (raiz de T004b) com leitura atual; vínculo de
      origem; idempotência; recusas nomeadas. Verde em T008.
- [ ] T019 `POST /v1/approvals/{approval_id}/discard` como transição
      registrada. Verde em T009.
- [ ] T020 Se T004c decidiu migração: revisão reversível (estado
      `discarded` / vínculo de origem), downgrade exercitado por teste, sem
      tocar nenhuma outra tabela. Se decidiu que não precisa: `[~]` com a
      razão e onde o estado vive.
- [ ] T021 A contagem servida ao shell (fonte de `countsFrom`) passa a
      contar pendentes dentro da janela + propostas de mudança pendentes.
      Verde na metade servidor de T013.

## Phase 3: Console

- [ ] T022 `ApprovalsTab`/`ProposalCard` na anatomia do artboard: cabeçalho
      (triângulo, título, meta-linha requester+origem, medidor 5 segmentos,
      chip de estado com forma), grade esquerda (passos numerados; reversão
      em vocabulário de perigo quando `reversible:false`), direita (por quê,
      evidência com `<a>` por item, raio, linha de autonomia), `<details>`
      "payload bruto da ação" fechado. Tokens e formas da fundação, por
      classe/token — nenhum hex novo. **A escolha entre `DecisionControls` e
      `IncidentDecisionControls` (`decisionFor`, hoje em `approvals.tsx`)
      continua existindo e os dois componentes continuam compostos sem
      edição** — só o entorno (cabeçalho, grade, `<details>`) é reescrito.
      Verde em T012.
- [ ] T023 Rodapé de expirada: faixa âmbar com a explicação, "Propor de novo,
      agora" acionando T018 e trocando a tela para a pendente nova sem
      navegação manual; "Descartar" acionando T019. Estados de erro do
      backend apresentados como troca de estado do cartão (422/409 com a
      causa), nunca stack trace.
- [ ] T024 "Decididas recentemente" lendo `state=decided`: forma de status,
      sentença, desfecho ("aprovada por X, aplicada e verificada" quando o
      ledger diz), instante relativo; ausência em uma linha.
- [ ] T025 Badge da sidebar lendo a contagem de T021. Verde em T013.
- [ ] T026 Aba Mudanças re-vestida: pills do padrão, empty state de uma linha
      + link; cartões de proposta de mudança na mesma anatomia quando houver.
- [ ] T027 Leitura falhada da lista: a tela diz que não conseguiu ler; nenhum
      texto afirma "nada proposto" (AN-13).
- [ ] T028 Fila com múltiplas pendentes: primeira expandida, demais como
      linhas de uma sentença com risco e idade (edge case da spec).
- [ ] T029 Declarar no relatório final: todas as chaves i18n novas com texto
      `en` e `pt-BR`; a atualização do registro visual (tela de decisões nos
      estados pendente e expirada). **Não editar os arquivos** — regra 3.

## Phase 4: Artefatos gerados e dataset

- [ ] T030 Regenerar o documento de API committed e o cliente TS a partir do
      código; o gate de desvio prova que saíram dos geradores.
- [ ] T031 Dataset simulado servindo decisões nos três estados com os campos
      novos (incluindo uma expirada com origem viva e uma com origem morta),
      para a suíte de console e o registro visual.
- [ ] T032 Suíte visual local: capturas das decisões pendente e expirada nos
      dois temas contra as baselines novas (as baselines entram pelo dono do
      registro no merge; os specs desta feature ficam prontos para elas).

## Phase 5: Fecho da feature (o merge do slot fecha o resto)

- [ ] T033 Acceptance local verde por inteiro; as mensagens do vermelho
      inicial arquivadas no controle.
- [ ] T034 Medir de novo a suíte sintética e reportar contra T003 ("sem
      efeito" esperado).
- [ ] T035 `make verify` verde; gates de formato do domínio tocado rodados
      antes de cada commit (o pre-commit não cobre TypeScript).
- [ ] T036 Relatório final para o orquestrador: chaves i18n (T029), linha do
      registro visual, `file:line` de T004, decisão de migração de T020,
      tokens/ícones que faltaram (se algum), e o roteiro de staging para o
      fim do slot — deploy-stg `COMPONENTS="app web"`, acceptance @staging
      (AN-08 propose-only contra a expirada real), consultas da spec
      ("Consultas de evidência em staging" 1–4), captura Orca dos dois temas
      e `evidence/visual/VEREDITO.md` conforme EXECUCAO.md §3.

## Dependencies & Execution Order

- T001–T004 antes de tudo; T004 bloqueia toda implementação.
- Phase 1 inteira antes de qualquer tarefa de Phase 2/3 — vermelho
  confirmado é pré-condição, não formalidade.
- Dentro da Phase 2: T016/T017 antes de T015 (a projeção usa as derivações);
  T018 depende de T004b; T020 antes de T018/T019 se houver migração.
- Phase 3 depende da Phase 2 (a tela lê o contrato novo); T025 depende de
  T021.
- Phase 4 depois de 2 e 3; Phase 5 por último. O gate visual e o deploy são
  do orquestrador no fim do slot — esta feature entrega tudo pronto para
  eles em T036.
