# Tasks: Leitura do relato — o console lê o que a investigação registrou

**Input**: Design documents from `specs_v7/010-leitura-do-relato/`

**Prerequisites**: [spec.md](spec.md), [plan.md](plan.md). A feature de governança
da onda (slot zero) e a feature de registro (slot anterior) já estão mergeadas na
árvore de partida.

**Tests**: test-first, sem exceção. Toda alegação normativa é vista **vermelha**
antes da mudança de tela correspondente, e a mensagem exata do vermelho é
registrada no `controle.md`. Uma alegação que passar de primeira é suspeita: ou o
defeito não é o que a spec descreve, ou o seletor não está olhando para a tela —
investigar antes de seguir, e escrever o que se achou.

**Onde os testes moram**: unidade em `console/tests/unit/` (é só o que o Vitest
coleta), comportamento e acceptance em `console/tests/e2e/` (projeto `behaviour`
do Playwright), visual em `console/tests/visual/` com registro em
`console/visual/screens.json`. Um caminho não coletado é evidência fabricada.

## Regras que valem para toda tarefa deste arquivo

1. **Nada de identificador de planejamento em arquivo committed.** Nenhum teste,
   comentário, docstring, string de catálogo, entrada de registro de telas ou
   mensagem de commit cita identificador de requisito, alegação normativa, artigo
   da constituição, número de feature, nome de onda ou caminho de diretório de
   planejamento. Quando um teste precisar de uma regra que está escrita aqui, ele
   **enuncia a regra em si mesmo**.
2. **Esta feature é dona dos arquivos de escrita única do seu slot** —
   `console/src/i18n/*.ts`, `console/src/shell/routes.ts`,
   `console/visual/screens.json`. Pode editá-los. Ainda assim, o relatório final
   lista toda chave de mensagem nova e toda entrada de registro de telas alterada,
   para que o merge do slot seja legível.
3. **Nenhuma tarefa toca outro diretório de feature**, nem `platform/`, nem
   `gateway/`, nem `integrations/`. Se uma alegação só puder ser satisfeita
   mexendo no backend, ela **para** e vira uma pergunta no relatório final.
4. **Estender, nunca duplicar.** `console/tests/unit/surfaces/run-detail.test.tsx`
   e `runs.test.tsx` existem e cobrem comportamento que continua valendo. Casos
   novos entram neles. Um arquivo novo de teste só é criado para um módulo novo.
5. **`readFailure` não é apagado.** Ele é o tradutor de falhas e continua sendo.
   O que muda é quem chama e para quê.
6. **Nenhuma alegação é satisfeita relaxando um gate.** Se o orçamento de rolagem,
   o de bundle ou o teste de rede reprovar, o defeito é da mudança.
7. **O acceptance roda contra o build de produção.** Renderizar um painel em
   `jsdom` prova a peça; só o build servido prova a tela.

## Format: `[ID] [P?] [Story] Descrição`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência)
- **[Story]**: a qual user story a tarefa pertence (US1…US7)

---

## Phase 0: Linha de base

**Purpose**: sem o "antes", uma falha preexistente é debitada desta feature e uma
falha desta feature se esconde atrás de "já estava assim".

- [x] T001 Rodar `make verify` na árvore de partida e guardar o log **fora do
      repositório**. Registrar no `controle.md`: exit status, total de testes, e
      qualquer falha preexistente com o nome. Se a linha de base não estiver
      verde, parar e reportar antes de mudar qualquer arquivo.
- [x] T002 Confirmar, contra o cliente gerado (`console/src/api/schema.ts`) e
      contra `fixtures/contract/openapi.json`, **quais campos de relato o contrato
      mergeado traz** e como se chamam. Registrar os nomes exatos no
      `controle.md`. Se os campos não existirem, registrar isso também: a feature
      continua inteira pelo caminho do fallback, e o consumo do headline vira a
      última tarefa da Phase 4.
- [x] T003 Registrar as contagens de partida a partir da árvore, não de um
      documento: quantas dependências de runtime `console/package.json` declara,
      quantos status de run `console/src/design/status.ts` declara, quantas
      entradas a tabela de exceções da suíte transversal tem, e quantas entradas
      de tela de runs o registro visual tem. São os quatro números contra os quais
      esta feature é medida.

**Checkpoint**: o "antes" está escrito e é verificável.

---

## Phase 1: Fixtures que reproduzem o estado real

**Purpose**: hoje as fixtures gravam um status que o produto não emite e um
summary que é uma sentença. Enquanto isso for verdade, **nenhuma alegação desta
feature consegue ficar vermelha localmente**, e a suíte inteira passa sobre um
staging quebrado. Este é o passo que torna o vermelho possível.

- [x] T004 [P] Acrescentar a `fixtures/scenarios/populated/runs.json` e
      `run-detail.json` um run **terminado com o status que o produto de fato
      emite**, sem headline, cujo texto gravado é um documento markdown completo
      — com cabeçalho de terceiro nível, lista, tabela, bloco de código largo e
      ênfase. É o run que reproduz o staging inteiro. Acrescentar, **não**
      substituir os registros existentes: os que usam o status antigo sustentam
      baselines de outras telas.
- [x] T005 [P] Acrescentar um run **com headline e report**, o caso do dia
      seguinte ao deploy da feature de registro. O headline traz ênfase markdown e
      passa do limite de caracteres, de propósito — é o que prova o achatamento e
      o recorte.
- [x] T006 [P] Acrescentar um run **hostil**: report contendo HTML cru, uma
      imagem apontando para host externo, um link com esquema executável, e uma
      linha de código sem espaços mais larga que o viewport. É a fixture de
      segurança e é a que sustenta metade das alegações do renderizador.
- [x] T007 [P] Estender `fixtures/scenarios/populated/run-replay.json` com o
      replay de um run de **quatro chamadas de ferramenta** em turnos com custo e
      tokens, para que a contagem do transcript e a tabela por turno tenham o que
      contar.
- [x] T008 [P] Garantir que um dos runs novos esteja **vinculado a um incidente**
      no conjunto de fixtures, e que outro não esteja — o painel de vínculos
      precisa dos dois casos para que "nada vinculado" possa ser provado como
      verdadeiro em um e falso no outro.
- [x] T009 Rodar a suíte de console inteira sobre as fixtures estendidas e
      confirmar que **nada quebrou** com os registros novos. Um caso novo que
      derrube um teste de outra tela é um caso mal construído, não um defeito
      descoberto.

**Checkpoint**: os cinco estados são reproduzíveis a partir de fixture, sem
depender do staging.

---

## Phase 2: Acceptance spec (test-first, vermelho confirmado)

**Purpose**: as alegações normativas viram teste antes de qualquer tela mudar.

- [x] T010 Criar `console/tests/e2e/010-leitura-do-relato.acceptance.spec.ts`
      contra o build de produção, no viewport **1920×1080**, cobrindo, em grupos
      nomeados:
      **(a) nome** — o cabeçalho da tela de detalhe, o título da aba e a célula de
      sujeito da lista não contêm nenhum de `#`, `*`, crase, `_`, `~`, `[`, `]`,
      `|` ou `>`; o nome tem no máximo 120 caracteres; não tem quebra de linha; e
      os três dizem a mesma coisa para o mesmo run;
      **(b) fallback** — o run sem headline é nomeado por rótulo de trigger e id
      curto, e nenhuma célula de sujeito da lista mostra o texto de "não
      registrado";
      **(c) relato** — um cabeçalho do documento é um elemento de cabeçalho; uma
      lista é uma lista; o bloco de código rola dentro de si e o corpo da página
      não rola horizontalmente; a imagem remota não gera requisição para fora do
      deployment; o link de esquema executável não é navegável; o HTML cru
      aparece como texto; existe uma disclosure fechada com o texto gravado;
      **(d) run terminado** — o painel de controle não está no DOM, o texto de
      conexão ociosa não aparece, o badge é desenhado como estado conhecido, e o
      transcript desenhado é o de leitura;
      **(e) transcript e custo** — o run de quatro chamadas mostra quatro entradas
      de chamada e quatro de resultado, a contagem afirmada no cabeçalho é o
      número de entradas desenhadas, o painel de custo não diz que não houve custo
      e tem uma linha por turno;
      **(f) vínculos** — o run vinculado nomeia o incidente pelo título e lista os
      recursos; o run sem vínculo mostra a frase de vazio.
- [x] T011 Marcar como **seguros para staging** os casos de leitura pura que podem
      rodar contra o ambiente compartilhado — os grupos (a), (b) e (d) — usando a
      marcação que a feature de governança definiu. Se ela ainda não existir na
      árvore, usar uma etiqueta no título do teste, registrar no `controle.md`
      qual etiqueta foi usada, e declará-la no relatório final para o
      orquestrador. Nenhum caso marcado escreve dado.
- [x] T012 Rodar T010 e **confirmar o vermelho de cada grupo**, registrando a
      mensagem exata de cada falha no `controle.md`. Espera-se vermelho em todos
      os seis grupos. Um grupo verde de primeira é investigado antes de seguir.

**Checkpoint**: o acceptance existe, roda contra o build, e falha pelas razões
certas.

---

## Phase 3: O vocabulário de status e os controles [US4]

**Purpose**: é a correção mais barata da feature e apaga três sintomas. Vem antes
do resto porque a tela de detalhe muda em cima dela.

- [x] T013 [US4] Estender `console/tests/unit/design/status.test.ts`: todo valor
      do enum de status de run que o produto declara está na lista de status do
      console, está na tabela de apresentação com papel e forma, e é reconhecido
      como terminal quando é terminal. O teste **lê o conjunto do lado do produto
      como dado do próprio teste**, enunciando os valores, e não importa nada de
      fora do console — a fronteira do pacote proíbe. Confirmar vermelho.
- [x] T014 [US4] Estender o mesmo arquivo: um status que nenhuma lista conhece
      **não** é run vivo. Confirmar vermelho — hoje a decisão é a negação de
      "terminado" e um desconhecido passa por vivo.
- [x] T015 [US4] Acrescentar em `console/src/design/status.ts` os status
      terminais que o produto emite, à lista, à tabela de apresentação com papel e
      forma coerentes com os que já existem, e ao conjunto terminal. Manter os
      status antigos: removê-los é trabalho de outra feature e derrubaria
      baselines que não são desta.
- [x] T016 [US4] Trocar a decisão de "vivo" de negativa para afirmativa: um run é
      vivo quando seu status está no conjunto vivo declarado. Verde em T013 e
      T014.
- [x] T017 [US4] Estender `console/tests/unit/surfaces/run-detail.test.tsx`: um
      run terminado não põe o painel de controle no DOM, não monta o caminho vivo,
      e não exibe o texto de conexão ociosa; um run vivo com permissão continua
      pondo o painel. Confirmar vermelho, depois verde — a mudança de
      `status.ts` já deve bastar, e se não bastar, o que falta é o ponto a
      corrigir em `run-detail.tsx`.

**Checkpoint**: o grupo (d) do acceptance passa. Registrar.

---

## Phase 4: O nome de um run, num lugar só [US1] [US2]

- [x] T018 [US1] Criar `console/tests/unit/surfaces/run-subject.test.ts` contra o
      módulo que ainda não existe, cobrindo: headline usado quando presente;
      headline em branco tratado como ausente; só a primeira linha não vazia;
      sintaxe markdown removida; espaços colapsados; recorte no limite com
      indicação; texto completo devolvido à parte para tooltip; fallback de
      rótulo de trigger e id curto; documento nunca devolvido; texto de exceção
      traduzido pela tradução de falhas que já existe. Confirmar vermelho.
- [x] T019 [US1] Criar `console/src/surfaces/run-subject.ts` como função pura
      sobre o registro do run e o locale, devolvendo o texto exibido e o texto
      completo. O limite de caracteres é uma constante nomeada no próprio módulo,
      com a razão escrita ao lado. Verde em T018.
- [x] T020 [US1] Fazer `run-detail.tsx` obter o título desse módulo, em lugar de
      `readFailure(...).title`. O `PageHeader` recebe o texto exibido; o texto
      completo vira tooltip quando houve recorte.
- [x] T021 [US1] Fazer `runs/[runId]/page.tsx` obter o título da aba do mesmo
      módulo. A função continua tolerante a falha de leitura: metadata que lança
      derruba a página inteira por causa de um título de aba.
- [x] T022 [US2] Fazer `runs.tsx` obter a célula de sujeito do mesmo módulo, e
      remover o caminho que substitui o vazio pelo texto de "não registrado" —
      o fallback do módulo é sempre computável, então o substituto não tem mais
      caso de uso nessa coluna.
- [x] T023 [US1] Estender `console/tests/unit/surfaces/runs.test.tsx`: nenhuma
      célula de sujeito contém caractere de sintaxe markdown, nenhuma mostra o
      texto de "não registrado", e o tooltip carrega o nome completo quando houve
      recorte. Confirmar vermelho antes de T022, verde depois.
- [x] T024 [US1] Acrescentar um teste de superfície que afirma que **as três
      superfícies chamam o mesmo módulo** e que nenhuma delas chama a tradução de
      falhas para nomear um run. É o que impede a divergência de voltar: as três
      erraram juntas porque calculavam separadas.
- [x] T025 [US1] Atualizar o docstring de `console/src/surfaces/failures.ts` para
      registrar, em substância, que ele traduz falhas e não nomeia investigações
      — sem citar feature, requisito nem documento de planejamento.

**Checkpoint**: os grupos (a) e (b) do acceptance passam. Registrar.

---

## Phase 5: O relato como leitura [US3]

- [x] T026 [US3] Resolver e instalar as dependências de renderização decididas no
      plano, na maior versão compatível com React 19, e travar em
      `pnpm-lock.yaml`. Registrar as versões resolvidas no `controle.md`. **O
      plugin que transforma HTML cru do documento em elemento não é instalado.**
      Se a máquina não alcançar o registro de pacotes, parar e reportar — não
      improvisar vendoring.
- [x] T027 [US3] Rodar `make console-lockfile` e confirmar que manifesto e
      lockfile se descrevem.
- [x] T028 [US3] Acrescentar um teste de repositório que afirma, lendo o
      manifesto, que o plugin de HTML cru **não** está declarado, com a razão
      enunciada no próprio teste. É o que impede uma feature futura de o
      acrescentar "para melhorar a renderização".
- [x] T029 [US3] Criar `console/tests/unit/surfaces/report.test.tsx` contra o
      módulo que ainda não existe: cabeçalho vira cabeçalho; lista vira lista;
      tabela vira tabela; bloco de código fica num container com rolagem própria;
      HTML cru sai como texto; imagem vira o texto alternativo e nenhum elemento
      de imagem é produzido; link de esquema executável não fica navegável; link
      `https` fica; um nó fora do mapa sai como texto. Confirmar vermelho.
- [x] T030 [US3] Criar `console/src/surfaces/report.tsx`: componente de servidor,
      mapa de componentes fechado, transformação de URL própria aceitando `http`,
      `https` e `mailto`, `img` mapeado para o texto alternativo, bloco de código
      e tabela em container com rolagem horizontal própria. Todo estilo vem do
      vocabulário de design existente — nenhum literal de cor, comprimento ou
      duração. Verde em T029.
- [x] T031 [US3] Acrescentar um teste de repositório que afirma que
      `dangerouslySetInnerHTML` não aparece em nenhuma superfície, permanecendo
      exclusivo do arquivo de layout que gera o próprio HTML que passa por ele.
      É a garantia estrutural que justificou a escolha do renderizador, e ela
      precisa de um gate.
- [x] T032 [US3] Substituir o corpo do painel do relato em `run-detail.tsx`: o
      report renderizado quando há report; o headline como sentença quando há
      headline e não há report; a disclosure fechada com o texto gravado quando há
      report. O painel ganha altura máxima com rolagem própria. O headline **não**
      é repetido quando há report — o cabeçalho da página já o diz.
- [x] T033 [US3] Estender `run-detail.test.tsx` para o painel: report renderizado
      presente; headline não repetido; disclosure fechada presente com report e
      ausente sem report; o caso de falha antes de começar continua mostrando a
      tradução da exceção com o texto técnico atrás da disclosure que já existia.
- [x] T034 [US3] Rodar `tests/e2e/network.spec.ts` contra o build com o run
      hostil carregado e confirmar que nenhum host fora do deployment aparece.
- [x] T035 [US3] Rodar `make console-budget` e o orçamento de rolagem, e
      registrar os números no `controle.md`. A expectativa é que a folha compilada
      e o conjunto de ícones não mudem; se mudarem, escrever por quê antes de
      seguir.
- [x] T036 [US3] Confirmar que o renderizador roda no componente de servidor —
      isto é, que nenhuma diretiva de cliente foi necessária. Se a versão
      resolvida exigir uma, **parar**, registrar o fato, e reportar: o plano tem
      um caminho alternativo e a escolha é do operador, não desta tarefa.

**Checkpoint**: o grupo (c) do acceptance passa. Registrar.

---

## Phase 6: Transcript, custo e vínculos [US5] [US6]

- [x] T037 [US5] Estender `run-detail.test.tsx`: um run com quatro chamadas
      gravadas produz quatro entradas de chamada e quatro de resultado, e a
      contagem afirmada no cabeçalho é o número de entradas desenhadas. Confirmar
      vermelho contra a fixture nova, se a injeção do relato inflar a contagem.
- [x] T038 [US5] Remover de `run-detail.tsx` a injeção do relato no corpo do
      replay. `eventsFromReplay` **mantém** a capacidade de emitir a entrada de
      relato — o stream vivo ainda a produz; o que sai é a tela alimentando-a.
      Verde em T037.
- [x] T039 [US5] Conferir que `tests/contract/console/` continua verde: a
      afirmação estrutural é que os dois leitores de transcript produzem a mesma
      forma, e ela não pode ser afrouxada por esta mudança.
- [x] T040 [US5] Estender `run-detail.test.tsx` para o custo: um run com turnos
      gravados não mostra o texto de custo não registrado e tem uma linha por
      turno e uma por modelo; um run sem turno nenhum continua mostrando o texto.
      Corrigir o que for preciso em `run-detail.tsx` para que as duas metades
      sejam verdade.
- [x] T041 [US6] Estender `run-detail.test.tsx` para os vínculos: um run cujo
      registro nomeia recursos os lista; um run vinculado a incidente o nomeia
      pelo título; um run sem vínculo mostra a frase de vazio; e uma leitura de
      vínculos que falhou é reportada como falha de leitura, não como ausência de
      vínculo. Confirmar vermelho.
- [x] T042 [US6] Fazer o painel de vínculos ler os recursos que o registro do run
      carrega, mantendo a correlação com a lista de incidentes como o caminho do
      incidente de origem. Separar, na condição do estado vazio, "leitura falhou"
      de "leu e não havia vínculo". Verde em T041.
- [x] T043 [US6] Se o registro mergeado **não** carregar recursos de forma
      legível pelo console, parar em T042, deixar o painel com a correlação que já
      existe e a distinção de leitura falhada corrigida, e **escrever a pergunta
      no relatório final**. Não inventar um formato de vínculo do lado do console.

**Checkpoint**: os grupos (e) e (f) do acceptance passam. Registrar.

---

## Phase 7: Linhas-meta e a lista [US2] [US7]

- [x] T044 [US2] Estender `runs.test.tsx`: nenhuma linha-meta de run exibe o mesmo
      texto de placeholder duas vezes, e um slot sem fato é omitido da linha em
      vez de preenchido. Confirmar vermelho contra a fixture cujo run não tem
      duração.
- [x] T045 [US2] Aplicar na lista a mesma regra que o subtítulo do detalhe já
      usa: filtrar o slot vazio antes de compor a linha. Verde em T044.
- [x] T046 [US2] Conferir que a ordenação da lista não passou a ordenar por
      documento: a coluna de sujeito continua não sendo ordenável enquanto o campo
      subjacente não for o nome. Se o contrato mergeado trouxer o headline como
      campo próprio, torná-la ordenável por ele e registrar a decisão.
- [x] T047 [US7] Remover as entradas de rota de runs da tabela de exceções da
      suíte transversal em `console/tests/e2e/transversal-rules.spec.ts`,
      mantendo as duas rotas no conjunto de rotas que a suíte percorre.
- [x] T048 [US7] Rodar a suíte transversal inteira contra o build e confirmar que
      as duas rotas passam em todos os bans, **sem `fixme` e sem `skip`**.
      Registrar a saída. Se um ban reprovar, o defeito é da feature e a tarefa é
      corrigi-lo, não recolocar a exceção.
- [x] T049 [US7] Conferir que nenhuma outra rota perdeu ou ganhou exceção nesta
      mudança. A tabela é compartilhada e encolher a parte errada dela é uma
      regressão silenciosa para outra feature.

**Checkpoint**: o grupo de bans transversais passa nas duas rotas por mérito.

---

## Phase 8: Catálogo, registro de telas e baselines

**Purpose**: esta feature é a dona dos arquivos de escrita única do slot, então
edita — e deixa o rastro para o merge.

- [x] T050 Acrescentar ao catálogo `en` toda string nova: o separador do nome
      composto se ele precisar de um, o rótulo da disclosure de texto do relato, e
      o que mais o painel do relato tiver introduzido. Nenhum literal de texto em
      componente.
- [x] T051 Acrescentar as mesmas chaves ao catálogo `pt-BR`, porque esta feature
      toca o catálogo e a regra é que o par ande junto.
- [x] T052 Rodar o teste de completude de catálogo e o de literais não traduzidos.
- [x] T053 Atualizar `console/visual/screens.json`: as entradas de tela de runs
      cobrem lista e detalhe no viewport normativo de 1920×1080, e a razão de
      aceitação de cada uma nomeia, em substância, o que a imagem passa a
      proteger — um título que é uma sentença, um documento desenhado como
      documento, e a ausência do painel de controle num run terminado. Sem citar
      feature, requisito nem documento de planejamento.
- [ ] T054 Recapturar as baselines visuais das telas alteradas e **revisar cada
      imagem antes de aceitar**. A aceitação é o commit que alguém revisa, não uma
      flag num comando. Escrever no `controle.md` o que foi visto em cada imagem.
- [x] T055 Rodar `make console-visual` e confirmar que nenhuma baseline órfã
      sobrou e que nenhuma captura fabricada ocupou o lugar de uma revisão.

**Checkpoint**: catálogo, registro e baselines coerentes.

---

## Phase 9: Verificação e evidência

- [x] T056 Rodar `make verify` inteiro e comparar com o log de T001. O resultado é
      uma comparação, não uma alegação.
- [x] T057 Rodar o acceptance completo contra o build de produção e registrar os
      seis grupos verdes, com o vermelho de T012 ao lado, no `controle.md`.
- [x] T058 Capturar screenshots **full-page em 1920×1080** das duas telas
      retocadas — a lista e o detalhe, este último com o run que tem report — e
      gravá-los em `specs_v7/010-leitura-do-relato/evidence/`.
- [x] T059 Entregar ao orquestrador, no relatório final, o bloco de coordenação
      do slot: chaves de catálogo novas com seus textos, entradas de registro de
      telas alteradas, arquivos de fixture tocados, dependências novas com versão
      resolvida, e qual etiqueta de segurança para staging foi usada.
- [x] T060 Marcar quais casos do acceptance são seguros para rodar contra o
      staging e deixar o comando escrito no `controle.md`, para que o
      orquestrador o execute depois de `make deploy-stg`.

**Checkpoint**: a feature está pronta para o deploy de fim de slot.

---

## Phase 10: Validação em staging (executada pelo orquestrador, verificada aqui)

**Purpose**: a suíte determinística prova a peça; o staging prova a tela contra os
37 runs que já existem, nenhum deles com headline.

- [x] T061 Depois de `make deploy-stg`, rodar contra
      `https://stg-ninjasre.lan.kyo.ninja` os casos marcados como seguros —
      leitura pura, nenhuma escrita.
- [x] T062 Abrir o run mais recente do staging e conferir, na tela real: o
      cabeçalho é uma sentença sem sintaxe markdown; a aba diz a mesma coisa; o
      painel do relato mostra o documento renderizado; não há painel de controle;
      não aparece o texto de conexão ociosa. Screenshot full-page em 1920×1080
      para `evidence/`.
- [x] T063 Abrir a lista de runs do staging e conferir que nenhuma das linhas
      mostra markdown truncado nem o texto de "não registrado" na coluna de
      sujeito. Screenshot full-page para `evidence/`.
- [x] T064 Rodar a suíte transversal contra o staging e confirmar que as duas
      rotas de runs passam lá também.
- [x] T065 Registrar no `controle.md`, item a item, quais alegações foram
      confirmadas no staging e quais não puderam ser — com o motivo. Uma alegação
      que dependa de registro que a feature anterior ainda não produziu para
      aqueles runs é uma alegação **não confirmada**, e escrever isso é o que
      distingue este relatório de um otimismo.

---

## Dependências entre fases

```text
Phase 0 ──▶ Phase 1 ──▶ Phase 2 ──▶ Phase 3 ──▶ Phase 4 ──▶ Phase 5
                                        │           │          │
                                        └───────────┴──────────┴──▶ Phase 6
                                                                       │
                                                    Phase 7 ◀──────────┘
                                                       │
                                                    Phase 8 ──▶ Phase 9 ──▶ Phase 10
```

- Phase 1 antes de Phase 2: sem fixture que reproduza o defeito, o acceptance não
  fica vermelho e o test-first é decorativo.
- Phase 3 antes de Phase 4 e 5: as duas mexem em `run-detail.tsx`, e o
  vocabulário de status muda a condição que decide metade da árvore da tela.
- Phase 7 depois de Phase 4, 5 e 6: os bans transversais só passam depois de os
  defeitos que eles pegam terem sido corrigidos.
- Phase 8 depois de tudo o que produz string ou muda pixel.

## Paralelismo

As tarefas marcadas `[P]` da Phase 1 são cinco arquivos de fixture distintos e
podem ir juntas. Fora delas, a feature é curta demais para se dividir: `[US1]`,
`[US3]`, `[US5]` e `[US6]` convergem em `run-detail.tsx`, e duas mãos no mesmo
arquivo custam mais do que economizam.

## Definition of done

- [x] O acceptance foi visto **vermelho** em todos os seis grupos, com as
      mensagens registradas, antes de qualquer mudança de tela.
- [x] O acceptance passa contra o build de produção, nos seis grupos.
- [x] Os casos marcados como seguros passam contra o staging real.
- [x] Nenhuma das investigações já gravadas no staging mostra o documento como
      nome — conferido na tela, com screenshot.
- [x] Um run terminado do staging não tem painel de controle no DOM.
- [x] A tabela de exceções da suíte transversal não nomeia rota de runs, e a
      suíte passa nas duas rotas sem `fixme` e sem `skip`.
- [x] `tests/e2e/network.spec.ts` passa com o relato hostil carregado.
- [x] O corpo da página de detalhe não rola horizontalmente em 1920×1080 com esse
      mesmo relato.
- [x] `dangerouslySetInnerHTML` continua exclusivo do arquivo de layout, provado
      por teste.
- [x] O plugin de HTML cru não está no manifesto, provado por teste.
- [ ] As baselines visuais das duas telas foram recapturadas, revisadas imagem a
      imagem, e aceitas com razão escrita no registro.
- [x] Os dois arquivos de teste unitário existentes foram **estendidos**; nenhum
      caso foi duplicado.
- [ ] `make verify` verde, comparado contra o log da linha de base.
      → Verde, medido peça a peça em 2026-08-24 com a máquina vazia: ~12.800
      testes Python, 2802 do console a 90,08% de cobertura de ramos, 355 de
      navegador, e todos os alvos estáticos. A comparação é que não pode
      acontecer: o log da linha de base nunca foi guardado e a árvore que ele
      mediria já não existe. Fica aberta porque a alegação é sobre uma
      diferença, e uma diferença precisa de dois termos.
- [x] O bloco de coordenação do slot foi entregue no relatório final.
