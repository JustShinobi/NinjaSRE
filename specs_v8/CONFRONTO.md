# specs_v8 — Confronto, checkpoints dos slots S1 e S2

Este arquivo diz **o que de fato foi entregue**, escrito pelo orquestrador a
partir da leitura independente dos verifiers — nunca do relatório de quem
implementou. Onde um verifier reprovou, o que está aqui é o resultado depois
do reparo e da re-verificação, com o defeito original preservado, porque um
confronto que só registra o estado final apaga a informação que tem valor.

Estado: **S0 e S1 fechados.** 000, 010 e 030 com PASS independente.

## 1. O que passou, e sob qual prova

| Feature | Veredito | Ciclos de reparo |
|---|---|---|
| 000-fundacao-visual | PASS | — (slot S0) |
| 010-canal-vivo | **PASS** | 1 de 2 permitidos |
| 030-run-view-narrado | **PASS** | 1 de 2 permitidos |

Portão final na árvore mergeada: `make verify` **exit real 0**, 13077
passados, 31 pulados, nenhuma falha. Os três componentes (`app`, `web`,
`proxy`) reconstruídos e redeployados no staging depois do reparo, rollout
conferido por deployment, rotas aquecidas antes de qualquer medição.

## 2. Os dois verifiers reprovaram primeiro, e é isso que dá valor ao PASS

Nenhuma das duas features passou de primeira. As duas reprovações foram
substantivas e nenhuma teria sido encontrada por quem implementou.

### 010 — FR-008 reprovado, com a prova de que a duplicação já custou algo

O verifier leu as duas classes inteiras e mostrou que `DeploymentConnection`
repetia os onze campos privados e os dez métodos de `RunConnection` com os
mesmos corpos — exatamente a "segunda implementação de reconexão" que FR-008
proíbe. O argumento que fechou a questão não foi de estilo: **a correção do
`#setState`, feita por esta própria feature, tinha sido aplicada só na
cópia.** `connection.ts:194-198` seguia com o defeito idêntico e sem
`onAttempt`, dormente apenas porque ninguém lê `RunConnection.attempts`
hoje. É precisamente a falha que um motor compartilhado existe para impedir,
já instalada na árvore.

O reparo extraiu `ReconnectingChannel<E>`; a re-verificação conferiu que o
diff da extração traz os corpos byte a byte, que sobrou uma implementação e
não duas com nome comum, e rodou a suíte inteira do console (3138 testes,
exit 0) em vez de acreditar no relatório.

### 030 — um teste que passava medindo nada

Seis testes marcados `@staging-safe` navegavam para ids do dataset mock. Cinco
falhavam; **o sexto passava**. A asserção da AN-01 conferia que o rail mostra
seis estágios em ordem, e no staging, com todos os painéis dizendo "did not
answer", o rail desenhava os seis assim mesmo — porque um run parado antes do
primeiro estágio é *especificado* para mostrá-los como futuros. O componente
estava certo; a asserção é que não distinguia um run real de uma leitura
totalmente falhada.

O verifier da re-verificação não argumentou que o reparo funcionou: reproduziu
os dois caminhos lado a lado no mesmo staging. Id morto — título caindo para o
id cru, quatro painéis com "did not answer", seis `stage-item` com
`data-state="future"`. Id descoberto — título real, zero ocorrências de "did
not answer", seis `stage-item` com `data-state="done"` e durações reais.

E conferiu os `test.skip` pelos dois lados: cada guarda é uma consulta ao DOM,
os skips disparam por um motivo real (o staging tem 50 runs, todos concluídos,
nenhum vivo e nenhum falho), e **os mesmos testes passam de verdade contra o
mock**, onde o dado existe. Mesmo caminho de código com dado diferente, não
uma segunda implementação a escrever depois.

## 3. Defeitos reais achados por rodar, não por ler

- **A rota do correio nunca serviu o caminho que o cliente pedia.** O arquivo
  estava em `api/events/route.ts` enquanto o cliente pedia
  `/api/events/stream`. Um bug de roteamento do Next.js, presente desde a
  criação do arquivo e contradizendo a própria mensagem do commit. Ele
  mascarava **dois** achados de harness que uma sessão inteira tinha tratado
  como problemas separados.
- **O chip nunca alcançava `stale`**, porque o mapa `reconnecting → refreshing`
  era incondicional e a soma dos backoffs passa de 30 s.
- **`onState` engolia falhas repetidas**: `#setState` descarta uma chamada que
  não muda a string de estado, então a segunda e a terceira falha consecutiva
  não disparavam nada.
- **Uma corrida no mockplane**, achada reproduzindo e não raciocinando: a US3
  abre duas páginas na mesma sessão, e o laço de stream da página fechada
  continua rodando porque a shell ASGI nunca recebe `receive` — o zumbi comia
  o "drop" destinado à conexão viva. Um contador foi trocado por uma janela de
  relógio, que leitores concorrentes respondem igual.
- **O `tool_returned` narrado como kind desconhecido** em todo run encerrado. O
  teste de funil único não pegou porque construía os dois lados de uma fixture
  com forma de stream e nunca chamava `eventsFromReplay`. Foi achado abrindo
  uma captura e lendo.
- **Uma fixture editada à mão.** A 030 acrescentou estágios e eventos ao JSON
  sem ensinar o gerador; o teste de reprodutibilidade só pegou quando as duas
  features estavam na mesma árvore. O reparo levou o dado para o gerador — e
  revelou que `total_events` do run-0004 discordava do próprio conteúdo desde
  a edição manual.
- **Dois módulos de teste com o mesmo basename**, invisível em worktree porque
  os diretórios rodavam em invocações separadas.

## 4. Quem constrói isso em produção?

A coluna que a onda exige, e as respostas honestas.

| Mecanismo | Construído a partir de um root que serve? |
|---|---|
| `DeploymentEventBroker` + taps de run e de incidente | **Sim** — root real, com teste estrutural provando que só um módulo o constrói |
| Endpoint `GET /v1/events/stream` | **Sim** — medido contra o staging, 10 min 31 s de conexão viva |
| `_EventPublishingApprovalStore` (FR-006/FR-007) | **Sim** — composto em `asgi.py:244` |
| `InteractionClosure` / `ClosurePublisher` | **Não. Não existe root de composição.** Ver §5 |

## 5. Lacunas de entrega, sem eufemismo

**FR-006 — `interaction_id` nunca é populado.** O campo está no allowlist do
escopo de decisão e nada nesta onda tem fonte para preenchê-lo, porque a fonte
seria o `InteractionClosure` que não é construído em lugar nenhum de produção.
O substituto entregue funciona e está ligado a um root que serve, então o
Artigo XIV está satisfeito *para o que foi de fato entregue* — mas o campo é
uma promessa não cumprida, e fica registrada aqui e não em rodapé.

**A US3 tem um mecanismo não explicado.** Um duplicado confirmado no nível da
API — `curl` devolvendo o mesmo `run_id` duas vezes — nunca virou duas linhas
renderizadas, e ninguém sabe por quê. A hipótese do orquestrador (React
colapsa chaves duplicadas) foi **refutada** pelo verifier: chaves duplicadas
avisam, mas cada elemento continua ganhando seu próprio fiber e seu próprio nó
no DOM. Consequência que importa: a asserção da US3 *pode* falhar para o caso
que ela nomeia, e passa hoje só porque os caminhos de escrita não produzem
duplicata — não porque algo reconcilie por id.

**AN-06 e AN-12 continuam provados só contra o mock.** São claims
incondicionalmente sobre um run vivo, e o staging não tem nenhum. Estão sem a
marca `@staging-safe` e comentadas no arquivo. Não é lacuna do reparo; é o
limite honesto da feature.

**A 010 não tem acceptance que rode em staging.** O spec é mock-only por
construção — sem marca `@staging-safe`, e a US3 depende de uma rota de
controle que só o mockplane tem. O T062 não tinha como rodar, e por isso o
slot nunca criou o run vivo que a própria EXECUCAO.md prevê. Consequência em
cadeia: os claims de run vivo da 030 ficaram sem ambiente.

## 6. Herdado, com dono a definir

Nada aqui é regressão do S1, e cada item foi atribuído por prova e não por
suposição.

- **Sete falhas da suíte transversal** em `/runs/{id}` e `/incidents/{id}`,
  mais seis falhas e2e pré-existentes. Todas dirigem `getByTestId('row')`
  contra telas que renderizam por `RunCard`. Prova: `data-testid="row"` não
  existe em `runs.tsx` nem na base nem no HEAD, e o S1 não tocou
  `incidents.tsx` nem a suíte transversal. **Dono: quem reformou `/runs` e
  `/incidents`.**
- **O painel de custo e tokens** desenha uma tabela onde o artboard desenha uma
  figura de display com barras por turno. `c01f8412` já traz a mesma tabela
  byte a byte; a 030 só mudou o estado do painel. **Herdado, anterior a esta
  onda** — e continua devendo um dos dois destinos: corrigir, ou registrar em
  `DIVERGENCIAS.md` com aprovação explícita.
- **Três diferenças do Painel** contra o artboard — sem sparkline nos tiles,
  sem faixa de disparos, sem painel de atividade ao vivo. **Dono: 050**.
- **`resources-1440-light` e `resources-320-light`** seguem sem baseline
  capturável. **Dono: quem pegar `/resources` na 060.**

## 7. O que o S1 deixa para quem vier

- **O staging não tem run vivo nem run falho.** Enquanto não tiver, os skips
  nomeados da 030 continuam pulando e os claims de liveness ficam sem prova
  real. Criar esse run é a primeira coisa que destrava evidência de verdade.
- **Um endurecimento opcional que vale a pena**: fazer a AN-01 asserir que os
  seis `stage-item` não estão *todos* em `data-state="future"`. O verifier
  passou sem isso, mas fecha em definitivo a classe de defeito que esta onda
  encontrou duas vezes — o teste que relata sucesso sem medir nada.
- **A notificação de tarefa em segundo plano mente sobre o exit code.** Relatou
  exit 0 para execuções que saíram 2, três vezes num só dia. Todo status
  registrado neste arquivo foi lido do log.


---

# Slot S2 — decisões estruturadas ∥ telas de área

## 1. O que passou, e sob qual prova

| | 040-decisoes-estruturadas | 060-telas-de-area |
|---|---|---|
| Verifier independente | **PASS** | **PASS** |
| Ledger | 33 feitas, 3 encerradas, 1 aberta | 31+ feitas, 6 encerradas, 0 abertas |
| Acceptance (mock) | 13 passaram, 3 pulados | 61 passaram, 8 pulados |
| Gate visual (Orca, 2 rodadas) | CONFORME | CONFORME, 8 de 8 |
| `make verify` na árvore mergeada | exit 0, 13112 passando | idem |

Os dois verifiers reproduziram tudo por conta própria, dos logs e não das
notificações, e **cada um fez o próprio corte de fio** em vez de ler sobre o do
implementer. O da 040 renomeou o caso de escrita da decisão no mock e viu o
vermelho real; o da 060 rodou a alegação estrutural contra os seis cenários
construídos, um a um.

## 2. A reparação central, medida no ambiente real

Nada nesta implantação jamais chamou a varredura de expiração do store de
aprovações. Uma proposta vencida **três dias antes** ainda contava como
pendente e ainda alimentava o badge de "coisas esperando por você".

Medido antes do slot e depois, de dentro do cluster:

| | antes | depois |
|---|---|---|
| pendentes | 1 | **0** |
| expiradas | 0 | **1** |
| total | 4 | 4 |
| badge | 1 | **0** |

A linha varrida é a que venceu em 27/08 e carrega `decided_at` de 31/08
01:39:20 — o instante em que a primeira leitura da lista aconteceu. E o
verifier achou a prova que faltava: um teste de ordenação **sem relação
nenhuma** passou a falhar no momento em que a varredura começou a rodar, porque
a fixture dele tinha vencimento numa data passada fixa. Isso demonstra que a
varredura roda contra o relógio real, não dentro do cenário do próprio teste.

Depois disso a proposta expirada foi reproposta pela tela — a única escrita
propose-only que o protocolo permite: total 4 → 5, uma pendente nova carregando
`origin_approval_id`, e a expirada continua expirada. Nada é apagado; todo
desfecho é um estado.

## 3. Defeitos achados por rodar, não por ler

Cinco defeitos desta onda compartilham uma forma: **relatar sucesso medindo
nada.** Três apareceram neste slot, e nenhum foi achado lendo código.

- **Um locator que nunca casava.** O teste de ordenação dentro da seção de
  recursos selecionava com `filter({ has })` um atributo que está no próprio
  elemento, nunca num descendente. Devolvia zero em qualquer ambiente e se
  auto-pulava alegando falta de dado — e o dado estava lá. Achado pela
  convergência; consertado e provado com corte de fio.
- **Um balde do mock contaminado.** Uma escrita de sessão num balde respondia
  por todos os outros do mesmo slug, e por causa disso uma alegação estava
  **verde pela razão errada**: o balde expirado ficava vazio, então o primeiro
  item da fila calhava de ser o novo pendente por acidente.
- **Uma query string que nunca chegava.** O caminho era montado só do
  `scope["path"]` do ASGI, que não carrega query string, então todo filtro por
  estado respondia silenciosamente do padrão. Confirmado com `curl` contra um
  mock isolado.
- **Fixtures mentindo sobre o domínio.** O mock servia desfechos de episódio
  `acknowledged` e `unresolved` — palavras que o backend real nunca emitiu.
- **Uma spec com a duplicação na origem errada.** O cartão de decisão nunca
  esteve errado: o construtor do payload escrevia a mesma frase em dois campos.
  O passo passou a carregar a operação que a ação já computava.

## 4. Quem constrói isso em produção?

| Mecanismo | Composto num root que serve? |
|---|---|
| Varredura de expiração dentro da listagem | **Sim** — medida contra o staging, pendente → expirada |
| Repropor via `RequestBuilder.queue()` | **Sim** — exercitado no staging, linha nova com vínculo de origem |
| Endpoint de decisão do store no mock | **Sim** — 85 de 85 endpoints cobertos, era 84 |
| Nome de recurso no subtítulo do incidente | **Sim** — de uma leitura que a tela já fazia |
| Grade de recursos limitada | **Sim** — 3230 px → 1795 px no staging |
| Chip de desfecho no vocabulário compartilhado | **Sim** — `data-role` presente onde não havia nenhum |
| Estações do pipeline nos três tratamentos | **Parcial** — desenhadas e testadas; só um delas é alcançável, ver §5 |

## 5. Lacunas de entrega, sem eufemismo

**O desfecho de um episódio é um booleano.** `MemoryEpisode.outcome` devolve
`RESOLVED` se uma flag está ligada e `INCONCLUSIVE` se não. A enumeração tem
quatro membros; uma investigação real jamais escreve os outros dois. E são
justamente os dois que um corpus de aprendizado mais precisa separar: falso
positivo é problema do detector, mitigação é conserto pela metade. O docstring
do próprio enum defende manter `inconclusive` com esse raciocínio, e o caminho
de escrita não o honra. As duas formas foram declaradas e registradas em
`DIVERGENCIAS.md` §8; só aparecem no inquilino da demonstração.

**Nada nomeia em que estágio um run que está rodando se encontra.**
`InvestigationSummary` carrega contagem de passos, duração e custo — nenhum
campo de estágio. Por isso as seis estações do pipeline desenham todas
"não alcançado". Os três tratamentos existem e são testados; falta um campo,
não um desenho. É a mesma degradação, pelo mesmo motivo, que a 030 já registrou
noutra tela.

**O reparo do cartão de decisão não é retroativo.** Um payload é documento
gravado. A aprovação expirada do staging guarda a duplicação com que nasceu, e
é justamente ela que a tela expande, porque a fila põe expiradas primeiro. Quem
olhar hoje vai ver a repetição no cartão de cima — não porque o defeito
persista, mas porque aquela linha é anterior à correção.

**A corrida de repropor concorrente continua aberta**, aceita e nomeada: a
checagem de idempotência e a gravação do vínculo são duas transações sem lock
entre elas. Como propose-only nunca aplica nada sozinho, o pior caso é um
humano ver duas pendentes e descartar uma.

**Cinco sub-abas não foram reformadas** — Documentos, Topologia, Ferramentas,
Autonomia, Contexto do time. Corte autorizado pela ordem que a própria feature
declarou, com razão na linha. Elas servem o conteúdo integral no vocabulário
compartilhado; falta a estrutura de cada artboard. Os cinco artboards existem,
então a onda continua devendo.

## 6. Herdado, e o que mudou de estado

- **As falhas transversais de `/incidents/{id}` fecharam de verdade.** As
  quatro regras passam porque a lista agrupada liga cada assunto ao disparo
  mais recente — não por edição de allowlist, que as regras da feature proíbem.
  O array de exceções está vazio e o `git blame` põe esse estado 415 commits
  antes desta onda. **As quatro de `/runs/{id}` continuam vermelhas**, que é a
  assimetria exigida: as três juntas ficando verdes significaria cenário
  enfraquecido, não produto consertado.
- **As duas baselines de `/resources` sem captura possível** deixaram de ser
  impossíveis: a dívida não era outra coisa senão a grade sem fim.
- **O artboard do Agente diverge do próprio `SPEC.md`** num estilo inline: o
  board declara `neutral-bg: #0d1311` e aquela estação usa `#131c18`. O console
  segue a paleta declarada. É achado sobre o board, para o dono dele.

## 7. O que o S2 deixa para quem vier

- ~~**O staging agora tem uma proposta pendente de verdade**, criada pela UI, com
  vínculo de origem — a primeira coisa que o S1 registrou como faltando.~~
  **Não tem mais, e quem a tirou foi o reparo da própria 040.** Medido no
  fechamento do S3: `approvals` traz `expired 2, approved 3, pending 0`. A
  proposta que o S2 reservou para a demo do S5 — pedida em 27/08 às 03:37, com
  prazo às 03:52 — tem `decided_at` em 31/08 às 01:39, quatro dias depois do
  próprio prazo, que é o instante em que a listagem corrigida a leu pela
  primeira vez. É o `expire_due(now)` dentro da transação de listagem fazendo
  exatamente o que foi escrito para fazer, e a prova está no par de tempos: uma
  segunda aprovação, pedida hoje às 04:24 com prazo às 04:39, expirou às 04:46
  — sete minutos depois em vez de quatro dias.

  O reparo está certo e a consequência é real: **o S5 precisa gerar uma
  proposta nova**, porque a reservada expirou em vez de ser decidida, e a
  AN-07/AN-08 da 050 não têm o que decidir no staging. Registrado aqui, e não
  só no `progress.json`, pela razão que o parágrafo seguinte já dá.
  ~~Continua sem run vivo e sem run falho.~~ **Corrigido no S3, medindo em vez
  de repetir.** O staging tem run vivo o tempo todo: a primeira leitura pegou
  `33c9143f` com status `running` e headline vazio, a segunda — noventa
  segundos depois — já o tinha como `completed`, e o run completado mais novo
  tinha 1m44s de idade. São 699 runs de alerta em 704, e chega um a cada poucos
  minutos. O que o staging **não** tem é run **falho**: zero `failed` e zero
  `cancelled`; os onze não terminados são todos `interrupted`, de quatro a oito
  dias, sem título.

  A frase errada custou uma conclusão: o analyze da 020 leu "sem run vivo" e
  decidiu que a cláusula da SC2 sobre observar um alerta real nunca poderia ser
  forçada e só passaria por acaso. Era premissa, não medida. Deixar isto
  corrigido aqui vale mais do que o registro do S2 parecer consistente — um
  slot posterior raciocina em cima desta seção.
- **Um rollout "concluído" mente igual a `Synced + Healthy`.** A primeira
  leitura depois de um redeploy não achou o elemento novo porque uma réplica
  antiga ainda estava pronta e servindo, com o `kubectl rollout status` já
  dizendo que as três implantações tinham terminado. Conferir listando os pods.
- **Uma notificação de tarefa em segundo plano mentiu de três formas neste
  slot**: exit 0 para quem saiu 1, exit 0 para quem saiu 2, e "concluído" com o
  processo ainda rodando e o log ainda crescendo. Uma delas escondeu uma suíte
  que **não rodou teste nenhum**, barrada por um lock morto de uma execução
  anterior. Todo status deste arquivo foi lido de log.
- **Três sessões de implementer foram perdidas inteiras** e nenhuma custou
  nada, porque todas tinham commitado e escrito o controle. A regra de commitar
  em qualquer ponto coerente entrou como seguro contra teto de turno; o que ela
  de fato garante é que uma sessão perdida vira uma mensagem de retomada.
