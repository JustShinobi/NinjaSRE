# Tasks: Identidade endereçável — o que a interface chama pelo nome, a rota atende pelo nome

**Input**: Design documents from `specs_v7/020-identidade-enderecavel/`

**Prerequisites**: spec.md, plan.md. A feature de regras e governança da onda
roda antes desta, mas nada aqui depende de decisão dela — só da precedência de
slot (a suíte transversal estendida e o modo de validação contra staging
nascem lá).

**Tests**: acceptance-first. O acceptance spec das dezesseis alegações
normativas aterrissa **antes** de qualquer implementação e é confirmado
vermelho, com a mensagem real de cada uma registrada. Um endereço consertado e
validado só depois do fato não distingue "consertei" de "o teste não olha".

## Regras que valem para toda tarefa deste arquivo

1. **Nada de identificador de planejamento em arquivo committed.** Nenhum
   teste, comentário, docstring, mensagem de commit, documento gerado ou string
   de UI cita identificador de requisito, número de artigo, número de feature
   ou caminho de diretório de planejamento. A substância vai no arquivo; a
   referência fica na spec.
2. **A chave interna não muda.** Nenhuma tarefa reescreve `incident_id`, nem a
   derivação `incident_key`, nem a correlação, nem a referência da timeline. Se
   uma tarefa parecer exigir isso, ela passou do alvo.
3. **O diff em `incident-detail.tsx` fica em identidade e leitura.** Título,
   cabeçalho da leitura falhada, e a supressão da afirmação negativa. O
   vocabulário dos chips, a sub-linha de meta, o painel de proposta e o de
   evidência são de outra feature da onda e não são tocados aqui.
4. **Arquivo gerado é regenerado, nunca editado à mão.** Documento de API,
   cliente TS e dataset simulado saem dos seus geradores; o gate de desvio é o
   que prova que saíram.
5. **Esta feature é a dona dos arquivos de escrita única no slot** —
   `console/src/i18n/*.ts`, `console/src/shell/routes.ts`,
   `console/visual/screens.json`. Ela pode editá-los. Nenhuma tarefa toca
   diretório de outra feature.
6. **Gate não é afrouxado para a mudança passar.** Se a suíte visual ou a
   transversal reprovar, o defeito é da mudança.

---

## Phase 0: Linha de base

- [x] T001 Rodar `make verify` na árvore intacta e guardar o log **fora do
      repositório**. Registrar, do próprio log: exit code, contagem de testes
      que passam e quais falham. Se a linha de base não estiver verde, parar e
      reportar antes de escrever qualquer coisa. **Sem este log, uma falha
      preexistente é debitada desta feature e uma falha desta feature se
      esconde atrás de "já estava assim".**
- [ ] T002 Capturar o estado do banco de staging **antes** de qualquer
      migração, e guardar fora do repositório: `SELECT count(*) FROM
      incidents;` e `SELECT incident_id, correlation_key, title, opened_at FROM
      incidents ORDER BY opened_at DESC LIMIT 10;`. Esses dois números e essa
      amostra são o "antes" contra o qual a migração é medida — total
      inalterado e chave interna intacta.
- [x] T003 Registrar a contagem atual da suíte de cenários sintéticos e o
      resultado dela. É o "antes" da medição que a regra de test-first exige de
      toda mudança que possa afetar investigação. "Sem efeito" é resposta
      aceitável ao final; "não medido" não é.

## Phase 1: Acceptance e contratos primeiro, confirmados vermelhos

Toda tarefa desta fase escreve teste contra a árvore atual e **tem de falhar**,
exceto as duas marcadas como caracterização. O vermelho de cada uma é capturado
com a mensagem real.

- [x] T004 Escrever `console/tests/e2e/identidade-enderecavel.acceptance.spec.ts`
      codificando as dezesseis alegações normativas da spec, uma asserção por
      alegação, no viewport 1920×1080. Marcar como staging-safe as doze que a
      spec declara, na convenção que a feature de governança estabelecer para
      isso — leitura pura, nenhuma escrita, nenhum dado destruído. Confirmar
      vermelho e registrar a mensagem real de cada alegação que falha.
- [x] T005 [P] Teste de unidade em `console/tests/unit/` para o decode de
      borda: um parâmetro contendo `:`, `@`, `+`, `/` encodado e `%` solto
      atravessa a borda e o cliente de API, e o endereço final carrega o valor
      original encodado **exatamente uma vez**. Comparar contra
      `encodeURIComponent` do valor literal. Confirmar vermelho: hoje o valor
      chega encodado à borda e é encodado de novo.
- [x] T006 [P] Teste de unidade em `console/tests/unit/`: um parâmetro sem
      nenhum caractere reservado sai idêntico ao que entrou. **Caracterização**
      — deve passar antes e continuar passando depois. É o que distingue
      "consertei a codificação" de "quebrei os ids simples".
- [x] T007 [P] Teste de unidade em `console/tests/unit/` para o cabeçalho do
      detalhe de incidente: com a leitura bem-sucedida o H1 é o título; com o
      título vazio o H1 é a ausência declarada; com a leitura falhada o
      cabeçalho não contém o identificador, diz que não conseguiu ler, e nenhum
      chip afirma que não existe investigação. Confirmar vermelho.
- [x] T008 [P] Teste de contrato em `tests/contract/` para a rota de detalhe de
      incidente: pedir pela forma pública e pela chave interna devolve o mesmo
      incidente; uma forma pública que não existe é respondida como ausência
      nomeada e não como erro de servidor. Confirmar vermelho: a forma pública
      ainda não existe.
- [x] T009 [P] Teste de contrato em `tests/contract/` para o contrato de
      leitura de incidente: toda descrição de incidente — listagem e detalhe —
      carrega a forma pública, e ela não contém nenhum caractere que exija
      escape numa URL. Confirmar vermelho.
- [x] T010 [P] Teste de contrato do store de incidentes em
      `tests/contract/persistence/`: o lookup por forma pública devolve o mesmo
      registro que o lookup pela chave interna, nas duas implementações da
      porta. Confirmar vermelho: o método não existe.
- [x] T011 [P] Teste de propriedade da derivação em
      `tests/unit/platform/persistence/`: a derivação é determinística sobre a
      mesma chave interna; duas chaves internas distintas dão formas públicas
      distintas; a forma produzida casa a gramática declarada e não contém
      caractere reservado. Confirmar vermelho.
- [x] T012 [P] Teste em `console/tests/unit/`: as quatro superfícies que geram
      href de incidente — lista, dashboard, busca e detalhe de run — produzem
      **o mesmo endereço** para o mesmo incidente, e nenhum deles contém
      caractere que precise de escape. Confirmar vermelho: hoje há três grafias.
- [x] T013 [P] Teste em `console/tests/unit/shell/` para a tabela de redirects:
      `/investigations` resolve para `/runs`, `/setup` resolve para
      `/first-run`, e a consulta do pedido é preservada. Confirmar vermelho.
- [x] T014 [P] Teste de caracterização em `console/tests/unit/`: a lista de
      incidentes continua renderizando as mesmas linhas, com o mesmo título,
      severidade e estado, depois de a fonte do href mudar. **Deve passar antes
      e continuar passando depois.**
- [x] T015 **Portão.** Confirmar e registrar o vermelho de T004, T005, T007,
      T008, T009, T010, T011, T012 e T013 com a mensagem real de cada um, e o
      verde de T006 e T014. Nenhuma implementação começa antes disto.

## Phase 2: A forma pública nasce na porta de persistência

- [x] T016 Acrescentar a derivação em
      `platform/persistence/ports/incident_store.py`, ao lado de
      `incident_key`: uma função pura que recebe a chave interna e devolve a
      forma pública, prefixada e com dezesseis hexadecimais de digest. O
      docstring explica por que é derivada e não sorteada, e por que o
      comprimento é o que é — em substância, sem citar documento de
      planejamento. T011 passa a verde.
- [x] T017 Acrescentar o campo da forma pública ao `Incident` na mesma porta, e
      declarar na porta `IncidentStore` o método de lookup por forma pública.
- [x] T018 [P] Implementar o lookup em `platform/persistence/fakes/incident_store.py`.
- [x] T019 [P] Implementar o lookup em
      `platform/persistence/postgres/repositories/incident_store.py`, sobre a
      coluna nova, e incluir a coluna no mapeamento de linha nos dois sentidos.
      O acesso continua pela porta; nenhum SQL sai da camada de persistência.
- [x] T020 Declarar a coluna e o índice único por `(org_id, public_id)` em
      `platform/persistence/postgres/models.py`. A unicidade é o que transforma
      uma colisão em falha de escrita em vez de "abriu o incidente errado".
- [x] T021 Derivar a forma pública ao abrir o incidente, em
      `IncidentLifecycle.raise_incident` (`platform/incidents/lifecycle.py`),
      junto da derivação da chave interna. É o único construtor de `Incident`
      no caminho de serving.
- [x] T022 [P] Acrescentar o campo ao semeador de demonstração
      (`platform/startup/demo/seeder.py`), que constrói `Incident` fora do
      caminho de serving e quebra o build sem ele. T010 passa a verde.

## Phase 3: A migração, ida e volta

- [x] T023 Escrever a revisão nova de migração em
      `platform/persistence/migrations/versions/`, com o próximo número livre
      da série, em três passos numa revisão só: acrescentar a coluna anulável;
      preencher cada linha com a derivação aplicada ao `incident_id` daquela
      linha; criar o índice único e tornar a coluna obrigatória. O backfill
      **importa** a função de derivação — uma segunda implementação do digest
      dentro da migração é exatamente como o valor gravado passa a divergir do
      valor computado.
- [x] T024 Escrever o `downgrade`: derruba o índice e a coluna, e nada mais.
      Nenhum incidente apagado, nenhuma outra coluna tocada, chave interna
      intacta.
- [ ] T025 Teste da migração contra PostgreSQL real: com incidentes gravados
      antes, aplicar a revisão e conferir que toda linha ganhou forma pública,
      que nenhuma se repete dentro da organização, que o total de linhas não
      mudou e que nenhum `incident_id` mudou. Depois reverter e conferir que o
      esquema volta ao anterior com todos os incidentes ainda lá. **A volta é
      exercitada, não presumida.**
- [ ] T026 Teste que amarra as duas metades: para uma chave interna qualquer, o
      valor que a migração grava e o valor que a função do código deriva são o
      mesmo. Sem este teste, a concordância é coincidência de revisão de código.

## Phase 4: O contrato, e os artefatos que saem dele

- [x] T027 Acrescentar a forma pública ao contrato de leitura de incidente em
      `gateway/http/routes/incidents.py`, ao lado da chave interna. Ela
      **acrescenta**: a chave interna continua no payload porque a timeline a
      referencia e porque um operador depurando precisa dela. T009 passa a
      verde.
- [x] T028 Fazer a rota de detalhe resolver as duas grafias: um parâmetro que
      casa a gramática da forma pública vai pela coluna, qualquer outro pela
      chave primária. Uma decisão de forma, não uma tentativa em cascata que
      faria duas consultas para todo pedido. T008 passa a verde.
- [x] T029 Decidir e implementar o mesmo para as rotas de fechamento e de
      supressão de incidente, ou registrar explicitamente que elas continuam só
      pela chave interna e por quê. Uma tela que abre por um identificador e
      escreve por outro é a próxima divergência de grafia esperando acontecer.
- [x] T030 Regenerar o documento de API committed e conferir que o gate de
      desvio passa. Não editar o documento à mão.
- [x] T031 Regenerar o cliente de API do console a partir do documento e
      conferir que a checagem de cliente passa. Não editar o cliente à mão.
- [x] T032 Reconstruir o dataset simulado para que todo incidente que ele
      descreve carregue a forma pública, e conferir que a validação de fixtures
      contra o documento passa.

## Phase 5: O decode acontece uma vez, na borda

- [x] T033 Criar `console/src/shell/route-params.ts` com a função de borda: ela
      recebe o que o roteador entregou e devolve o valor literal; quando a
      decodificação lança, devolve o valor recebido, porque a alternativa é uma
      rota derrubando a renderização por causa de um endereço malformado que
      deveria terminar em "não existe isso".
- [x] T034 [P] Passar o parâmetro pela borda em
      `console/src/app/(shell)/incidents/[incidentId]/page.tsx`.
- [x] T035 [P] Passar o parâmetro pela borda em
      `console/src/app/(shell)/runs/[runId]/page.tsx`.
- [x] T036 [P] Passar o parâmetro pela borda em
      `console/src/app/(shell)/integrations/[name]/page.tsx`.
- [x] T037 [P] Passar o parâmetro pela borda em
      `console/src/app/api/stream/[runId]/route.ts`.
- [x] T038 Escrever a invariante na documentação de `bind` em
      `console/src/lib/api.ts`: decodificado uma vez na borda, encodado uma vez
      aqui. `bind` **não muda de comportamento** — ele é chamado também com
      valores que nunca foram um parâmetro de rota, e decodificar ali
      corromperia um valor que legitimamente contém `%`. T005 passa a verde;
      T006 continua verde.
- [x] T039 Varrer `console/src/app/` por qualquer outra rota dinâmica e
      confirmar que não sobrou nenhuma sem a borda. A lista das quatro acima é
      a que foi levantada; a varredura é o que prova que é a lista inteira.

## Phase 6: O título é o título

- [x] T040 Trocar o H1 do detalhe de incidente pelo título do incidente em
      `console/src/surfaces/screens/incident-detail.tsx`, removendo o fallback
      para o identificador. Com a leitura bem-sucedida e o título vazio, mostrar
      a ausência declarada que o console já usa — nunca o identificador.
- [x] T041 Com a leitura falhada, renderizar no cabeçalho a frase de leitura
      falhada vinda do catálogo e **não renderizar** o chip de investigação. A
      ausência é o menor diff possível e é o que a feature de uma-fonte-por-fato
      substitui depois pelo chip de estado desconhecido, sem ter de desfazer
      nada daqui. T007 passa a verde.
- [x] T042 Fazer o título da aba nomear o incidente, em
      `console/src/app/(shell)/incidents/[incidentId]/page.tsx`: a leitura passa
      por um leitor memoizado por requisição — o mesmo padrão que
      `console/src/surfaces/context.ts` já usa para o viewer — de modo que a
      leitura aconteça uma vez e a aba e o H1 nomeiem a mesma coisa. Com a
      leitura falhada, a aba cai no nome do deployment, nunca no identificador.
- [x] T043 Conferir que nada mais em `incident-detail.tsx` mudou: vocabulário
      dos chips de estado, sub-linha de meta, painel de proposta e painel de
      evidência intactos. O diff desta feature naquele arquivo é identidade e
      leitura.

## Phase 7: Um endereço, quatro superfícies

- [x] T044 [P] Gerar o href pela forma pública em
      `console/src/surfaces/screens/incidents.tsx`.
- [x] T045 [P] Gerar o href pela forma pública em
      `console/src/surfaces/screens/dashboard.tsx`, nos dois pontos que hoje o
      montam.
- [x] T046 [P] Gerar o href pela forma pública em `console/src/shell/search.ts`.
- [x] T047 [P] Gerar o href pela forma pública em
      `console/src/surfaces/screens/run-detail.tsx`.
- [x] T048 Conferir que as quatro produzem o mesmo endereço para o mesmo
      incidente, e que nenhuma delas encoda nada — porque não há o que encodar.
      T012 passa a verde; T014 continua verde.

## Phase 8: As rotas respondem pelos nomes

- [x] T049 Generalizar a tabela de redirects em `console/src/shell/routes.ts`:
      ela deixa de se chamar por Settings, em nome e em comentário, e passa a se
      chamar pelo que é. Duas tabelas de redirect seria o começo de dois lugares
      onde procurar por que um endereço vai parar noutro.
- [x] T050 Acrescentar as duas linhas: `/investigations` → `/runs` e `/setup` →
      `/first-run`. T013 passa a verde.
- [x] T051 Ajustar `console/src/shell/legacy-redirect.ts` e os dois chamadores
      existentes ao nome novo, sem mudar comportamento nenhum — a consulta
      continua sendo preservada menos `tab`.
- [x] T052 [P] Criar `console/src/app/(shell)/investigations/page.tsx` no
      mesmo formato de `signals/page.tsx`, com redirect temporário e não
      permanente. Um redirect permanente fica gravado no navegador de quem o
      recebeu, e a onda ainda está movendo telas de lugar.
- [x] T053 [P] Criar `console/src/app/(shell)/setup/page.tsx`, idem.

## Phase 9: Catálogo, dataset e registro visual

- [x] T054 Acrescentar as chaves de mensagem novas — a frase de leitura falhada
      do incidente e o que mais as fases 6 e 8 exigirem — a
      `console/src/i18n/en.ts` e a `console/src/i18n/pt-BR.ts`. Esta feature é a
      dona dos arquivos de i18n no slot; as chaves e os textos entram também no
      relatório final, para o merge do slot.
- [x] T055 Conferir que `console/visual/screens.json` continua resolvendo o
      endereço do detalhe de incidente a partir do dataset. O registro já usa um
      marcador que a suíte visual resolve da captura; se a resolução passar a
      precisar da forma pública em vez da chave interna, ajustar
      `console/tests/visual/screens.spec.ts` no mesmo passo.
- [x] T056 Rodar a suíte visual e reconciliar. Uma baseline que morrer com a
      mudança é apagada deliberadamente; nenhuma é substituída por captura
      fabricada, e nenhuma é aceita sem alguém olhar a imagem.

## Phase 10: Validação em staging

Esta fase acontece depois do merge do slot, no ciclo que o protocolo de
execução da onda define. O orquestrador é quem publica; as tarefas abaixo são o
que esta feature precisa provar lá.

- [ ] T057 Aplicar a migração no banco de staging e rodar as cinco consultas de
      evidência que a spec enumera: cobertura (nenhuma linha sem forma pública),
      unicidade (nenhuma repetida por organização), total inalterado contra
      T002, chave interna intacta contra a amostra de T002, e concordância entre
      o valor gravado e o valor que a função do código deriva para a mesma
      linha.
- [ ] T058 Rodar contra `https://stg-ninjasre.lan.kyo.ninja` as doze alegações
      staging-safe do acceptance, no viewport 1920×1080, e registrar o verde de
      cada uma.
- [ ] T059 Navegar lista → detalhe de um incidente **real** de alerta no
      staging e capturar a evidência: a URL na barra de endereços, o H1, e os
      painéis. A captura vai para `evidence/` desta feature. **É esta captura,
      não o pytest, que prova a composição no caminho de serving** — o harness
      prova a peça.
- [x] T060 Confirmar no staging que `/investigations` termina em `/runs` e que
      `/setup` termina em `/first-run`, com captura de cada um.
- [x] T061 Rodar a suíte transversal contra o staging e confirmar que nenhum
      dos bans novos da onda é violado pelas telas que esta feature tocou.

## Phase 11: Fechamento

- [x] T062 Rodar `make verify` e comparar, alvo por alvo, com o log de T001.
      Todo alvo que passava continua passando. Qualquer diferença é explicada ou
      corrigida, nunca omitida.
- [x] T063 Medir e registrar o efeito sobre a suíte de cenários sintéticos
      contra o "antes" de T003. "Sem efeito" é a resposta esperada; "não
      medido" não é aceitável.
- [x] T064 Varrer o console por qualquer geração de endereço de incidente que
      tenha escapado das quatro superfícies conhecidas, e por qualquer uso
      remanescente do identificador como nome ou título em tela.
- [x] T065 Atualizar o `controle.md` desta feature com o que o código prova: o
      vermelho capturado de cada teste da Fase 1 com a mensagem real, as cinco
      consultas de staging com o resultado de cada uma, o antes e o depois das
      contagens de T002, o efeito medido sobre os cenários sintéticos, a forma
      pública escolhida com a decisão registrada, e toda ressalva de honestidade
      — inclusive qualquer teste cujo vermelho não foi visto antes da
      implementação, e por quê.

## Dependencies

- T001 → T002 → T003 → toda a Fase 1. A linha de base precede qualquer escrita.
- T015 é portão: nenhuma implementação começa antes do vermelho confirmado.
- T016 → T017 → {T018, T019, T020} → T021 → T022. A derivação precede tudo que
  a usa.
- Fase 3 depende de T016 (o backfill importa a derivação) e de T020 (a coluna
  precisa estar declarada); T025 e T026 dependem de T023 e T024.
- T027 e T028 dependem da Fase 2; T029 depende de T028; T030 depende de T027 e
  T029; T031 depende de T030; T032 depende de T031.
- Fase 5 é independente das Fases 2 a 4 e pode correr em paralelo com elas.
  T034..T037 dependem de T033; T038 depende de T033; T039 depende de T034..T037.
- Fase 6 depende de T031 (o cliente precisa conhecer o campo) e da Fase 5
  (T034); T043 depende de T040..T042.
- Fase 7 depende de T031; T048 depende de T044..T047.
- Fase 8 é independente de tudo o mais e pode correr a qualquer momento depois
  de T015. T050 e T051 dependem de T049; T052 e T053 dependem de T050.
- Fase 9 depende das Fases 6, 7 e 8; T056 depende de T055.
- Fase 10 depende de tudo o que precede e do merge do slot.
- T062 depende de tudo; T063 depende de T003 e de T062; T065 é a última.
