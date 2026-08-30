# specs_v8 — Confronto, checkpoint do slot S1

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
