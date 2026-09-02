# Retomada do slot S1 — o que a execução ensinou, e onde ela parou

Este arquivo existe porque o `progress.json` guarda **estado** e os
`controle.md` guardam **prova**, mas nenhum dos dois guarda o que os
implementers aprenderam sobre *operar* este slot. Quem retomar — outro
agente, outro runtime — começa frio, e sem isto refaz descobertas que já
foram pagas.

Leia nesta ordem: `progress.json` (estado canônico, com o bloco `resume` e
os itens abertos), este arquivo, e então o `controle.md` da feature que for
retomar.

## 1. Onde cada feature parou

| | 010-canal-vivo | 030-run-view-narrado |
|---|---|---|
| Worktree | `/srv/workspaces/v8-s1-010` | `/srv/workspaces/v8-s1-030` |
| Ramo | `wt/v8-010-canal-vivo` | `wt/v8-030-run-view-narrado` |
| HEAD | `09935108`, árvore limpa | `1a58cda5`, árvore limpa |
| Base comum | `c01f8412` | `c01f8412` |
| Commits | 14 | 21 |
| Ledger | T010/T060/T070 abertos | 18 feitas, 6 encerradas, **0 abertas** |
| Estado | **incompleta** | **implementação completa, não verificada** |

**A interseção de arquivos entre os dois ramos é vazia** — conferido com
`git diff --name-only` dos dois lados. A disjunção que o `EXECUCAO.md`
declarou se sustentou na prática: o merge do slot não terá conflito para
resolver. E a 010 não declarou **nenhuma** chave i18n nova, então a
reconciliação de single-write no merge é vazia dos dois lados.

Nada foi mergeado na árvore compartilhada. O protocolo funde os dois diffs
juntos, no fim do slot, e só então roda gates de fronteira, deploy de
staging, gate visual e verifiers.

## 2. Operar as worktrees isoladas: três armadilhas medidas

**Não symlinke `.venv`.** Foi a primeira tentativa aqui. O `uv` detecta que
o diretório do projeto mudou e reinstala o pacote editável apontando para a
worktree — através do symlink, dentro da venv da árvore compartilhada.
Contamina as três de uma vez. Cada worktree precisa da sua:
`uv sync` dentro dela resolve em segundos, reaproveitando o cache.

**`console/node_modules` precisa ser cópia real**, não symlink: o
Turbopack rejeita o link. Uma `cp -a` da árvore compartilhada serve.

**Montar uma worktree irmã para comparar contra a base quebra o
`node_modules` da worktree original.** Aconteceu: a 030 criou uma irmã no
commit base para decidir se seis falhas eram regressão dela, e o
`pnpm install` de lá deixou 22 symlinks de topo da worktree original
pendurados apontando para a irmã — que depois foi removida. O sintoma é
`MODULE_NOT_FOUND` na recaptura de baseline. Conserta com
`pnpm install --frozen-lockfile --offline` dentro da worktree afetada
(segundos, tudo do store local, zero download).

**`console/.toolchain` pode ser symlink** para a árvore compartilhada — são
694 MB de node/pnpm pinados por digest, e ninguém escreve neles. Está em
`.git/info/exclude`, porque o ignore do repositório usa `.toolchain/` com
barra e não casa com um symlink.

## 3. O teto de turnos chega onde quer, não na fronteira de fase

Os dois implementers bateram no teto de 120 turnos **seis vezes** entre
eles, e nenhuma vez numa fronteira de fase. Duas dessas vezes havia
trabalho não commitado na worktree.

A regra que funcionou, e que deve entrar no despacho como condição de
entrada e não como lembrete: **comitar em qualquer ponto onde a árvore
faça sentido junta**, com `wip(...)` quando for meio pensamento. E dizer
por quê, numa forma que sobreviva ao otimismo do agente: assuma que você
vai bater no teto; trabalhe de modo que isso custe uma mensagem de
retomada, não um dia.

O espelho do `controle.md` fora do repositório — em
`/tmp/claude-999/-srv-workspaces-NinjaSRE/06510f59-f4a1-41e0-8b90-2554e9cacfc7/scratchpad/controle-0{1,3}0.md`
— também se pagou: ele é escrito a cada commit, então um relatório final
que volte vazio não leva o ledger junto.

## 4. 010-canal-vivo — o que falta, com o contexto que já foi adquirido

O backend está inteiro e verde: broker, os dois taps de escrita compostos
no root real, endpoint com contrato verde (11 testes), contrato e cliente
TS regenerados pelo caminho de geração, mockplane servindo o canal, cliente
e `AutoRefresh` rebaixado a fallback, rota de proxy Next.js.

Falta: o vermelho por corte de fio da T010, os gates estreitos da T060, e
o diagnóstico de dois achados de harness. **Este é o valor deste arquivo**
— as hipóteses abaixo já custaram turnos e não estão em lugar nenhum que um
agente frio leia por acaso.

### 4.1 A T010 nasceu fora de ordem, e a compensação está pela metade

A acceptance spec foi escrita **depois** do cliente existir. O desvio está
declarado no controle e nas tarefas, sem eufemismo. A compensação pedida
foi o corte de fio à mão: desligar o mecanismo de cada user story, rodar,
ver o vermelho pela razão certa, restaurar, citar a linha real.

Esse exercício **não foi concluído**. O que foi feito no lugar, e que vale
bastante: a spec foi rodada de verdade contra `python -m tools.mockplane
serve`, e isso achou **três bugs reais**, todos corrigidos na origem e
nenhum contornado no teste:

1. **O chip nunca alcançava `stale`.** `BACKOFF_MS` somado por
   `MAX_RECONNECTIONS` passa de 30 s, e o mapa `reconnecting → refreshing`
   era incondicional. Agora `freshnessFromConnection` consulta `attempts`,
   reusando `STALE_AFTER_FAILURES` (`auto-refresh.tsx:76-88`, `7e583605`).
2. **`onState` não reportava cada tentativa.** O `#setState` de
   `connection.ts` descarta uma chamada que não muda a string de estado, de
   modo que a segunda, terceira, n-ésima falha consecutiva não disparava
   nada. Resolvido com `onAttempt` em `DeploymentConnectionOptions`
   (`deployment.ts:130`, chamado sem condição em `#failed()`), ligado ao
   `AutoRefresh`.
3. **O mockplane nunca fazia flush dos cabeçalhos com a conexão quieta.**
   Confirmado com `curl -N -i` manual: zero bytes por vários segundos com o
   uvicorn já tendo respondido 200. Resolvido com um frame de comentário
   logo após os cabeçalhos e heartbeats periódicos (`1195afdf`).

Isso prova que a spec mede comportamento real. Não substitui o corte de fio,
que continua devendo.

### 4.2 Achado aberto: a contagem de `guardian-flight` não sobe (US1)

A primeira asserção da US1 (`data-state="live"`) passa. A segunda — a
contagem subir depois de iniciar uma investigação pela gaveta, na segunda
página — nunca foi observada subindo no harness local.

Hipótese formada e **não confirmada**: o registro do fixture de
`investigation-start` no mockplane pode não marcar `status` como
`"running"`, e o Guardian filtra por
`record => text(record, 'status') === 'running'`. Nenhuma investigação foi
feita depois de formular isso. É por aí que se começa.

### 4.3 Achado aberto: a recuperação após `unroute()` não fecha em 30 s (US2/US3)

Depois de `page.unroute('**/api/events/stream')`, instrumentação temporária
mostrou a `DeploymentConnection` seguindo corretamente seu laço de
retentativa — tentativas subindo 4, 5, 6, 7, 8+, com o backoff no tempo
certo —, mas o `fetch()` subjacente continuava falhando. O contador de hits
do próprio handler do Playwright ficou parado em 3, o que prova que o
Playwright já **não** estava mais interceptando e mesmo assim a conexão não
conseguia suceder.

Hipótese formada e **não confirmada**: exaustão do pool HTTP do
Node/undici na rota de proxy (`console/src/app/api/events/route.ts`),
acumulando conexões obsoletas contra o mock sob reconexões rápidas
repetidas.

A investigação foi interrompida por decisão explícita de orçamento, não por
conclusão. As asserções de recuperação em US2/US3 continuam na spec **como
foram escritas** — a simplificação que se cogitou não foi feita. Quem
retomar deve **rodar a spec primeiro** para confirmar se o achado ainda
reproduz, antes de decidir entre corrigir a causa raiz e afrouxar a
asserção. Afrouxar sem reproduzir é a spec passando a mentir.

Nenhuma instrumentação de depuração ficou no código — conferido por grep e
por `git diff --stat` do arquivo contra o commit anterior.

### 4.4 Uma leitura mais frouxa de FR-008, declarada e pendente de juízo

`deployment.ts` **não** extraiu um motor genérico de `RunConnection`. Ele
reusa os *tipos* exportados (`StreamSource`, `StreamHandlers`,
`StreamHandle`, `Scheduler`, `Visibility`, `BACKOFF_MS`, `ConnectionState`)
e a *mesma* política de backoff e de pausa por visibilidade, como
implementação **paralela**. O implementer declarou isso como leitura mais
frouxa de FR-008 ("reutilizando … não uma segunda implementação de
reconexão") do que a extração completa teria sido, e pediu explicitamente
que não fosse escondido.

**Isso é para o verifier julgar, não para o próximo implementer decidir
sozinho.** Se for reprovado, a extração do motor compartilhado é o reparo.

### 4.5 O gap do FR-006, sem eufemismo

`InteractionClosure`/`ClosurePublisher` **não são construídos em nenhum
lugar de produção** — não existe root de composição que os ligue. Foi o que
o gate de análise levantou como risco e o implementer confirmou em código.
A escolha, correta, foi decorar o mesmo `ApprovalStore` que o FR-007
decora (`platform/persistence/deployment_taps.py:85`,
`_EventPublishingApprovalStore`), publicando a partir das escritas do store:
`create_request → decision_proposed`, `decide → decision_decided`,
`expire_due → decision_expired`.

Funciona — os três kinds saem corretos. Mas **`interaction_id` nunca é
populado por esta feature**: o allowlist do escopo de decisão inclui o
campo e nada aqui tem fonte para preenchê-lo, porque a fonte seria o
closure que não existe em produção. Isso vai para o `CONFRONTO.md` da onda,
não para rodapé.

### 4.6 Bloco Traefik (T061) — entregue como texto, do orquestrador aplicar

Está no fim do `controle.md` da 010. O ponto que importa: ele foi escrito
como *requisito traduzido para chaves prováveis*, e o GitOps é outro
repositório. Quem aplicar **deve conferir os nomes exatos de chave contra o
manifesto real da rota SSE por run**, que já atravessa esse mesmo Traefik
hoje, e manter os dois consistentes. Sem buffer no proxy, `flushinterval`
curto, e timeout do proxy com folga larga sobre os 10 minutos que o critério
exige — o gerador do lado do gateway é infinito, então o limite é do proxy.

## 5. 030-run-view-narrado — completa, com três coisas para carregar

Ledger fechado. O que vale saber:

**As seis falhas e2e foram decididas contra a base, não por inferência.**
A implementer montou uma worktree irmã em `c01f8412`, com build de produção
de verdade, e rodou as duas specs suspeitas lá: as mesmas seis falhas, nas
mesmas linhas, byte a byte. Todas dirigem `getByTestId('row')` /
`getByTestId('sort')` contra `/runs`, que renderiza por `RunCard` e nunca
pela tabela genérica que possui `data-testid="row"`. **Os testes já estavam
obsoletos antes desta feature existir.** Não são dela e não viram entrada
de allowlist: precisam de dono, e o dono é quem reformou `/runs`. Levar ao
confronto da onda.

**A barra de progresso de evidência não aparece em baseline nenhuma**,
porque nenhum cenário de `fixtures/scenarios/populated/` preenche
`evidence_assessed`. Em vez de deixar a correção provável só pela ausência,
foi escrito um teste que serve o registro com o campo preenchido e assere a
barra. Se alguém for mexer nos fixtures depois, é aqui que a cobertura mora.

**O bug do `tool_returned`** merece ser lembrado como método: o
`eventsFromReplay` soletra o desfecho de uma chamada como `tool_returned`, e
a tabela de narração só tinha o `tool_succeeded`/`tool_failed` do stream —
então todo resultado de capacidade em todo run encerrado narrava como kind
desconhecido. O teste de funil único não pegou porque construía os dois
lados de uma fixture com forma de stream e nunca chamava `eventsFromReplay`
de verdade. Foi achado **abrindo uma captura e lendo**. É para isso que a
captura serve.

Nota de revisão: a mensagem do commit `eacca5f9` (varredura pt-BR, 46
correções) tem uma frase truncada do rascunho. O conteúdo está correto e
verificado; a implementer sinalizou o defeito nela mesma em vez de
reescrever o commit.

## 6. Decisões do operador tomadas neste slot

1. **Ordem do transcript: conformar ao board — mais recente no topo.** O
   artboard desenha assim e diz numa legenda; o console era cronológico e
   asseria isso. A inversão foi feita, `live.spec.ts` acompanhou, e o raio
   foi verificado contra a base: nenhum consumidor regrediu.
2. **Varredura do português europeu no `pt-BR.ts`: agora, na 030**, porque
   ela é a dona do arquivo no slot e depois do merge a caneta muda de mão.
   46 correções em commit próprio, com `file:line` no controle.

E uma que não é do operador, mas fecha um item: os cinco desvios que a 030
achou contra o artboard — quatro foram conformados (rail de 340 px escopado
à tela, barra de progresso de evidência, slide-in na entrada nova do
transcript com asserção, chip menor no toggle) e um foi recusado como falso
desvio, porque FR-020 congela explicitamente a posição dos controles de
condução e um requisito explícito ganha do artboard.

## 7. O que o orquestrador reteve, e por quê

Uma worktree não alcança cluster nem banco. Estas tarefas **não** são do
implementer e foram tiradas do ledger dele com `[~]` e a razão na linha:

- **010**: T001 (captura "antes" no staging), T061 (aplicar Traefik +
  `make deploy-stg`), T062 (acceptance no staging, e o único run que o slot
  pode criar), T063 (gate visual Orca).
- **030**: T003 (captura "antes"), T020 (`make verify` completo), T021
  (acceptance no staging consumindo o run da 010), T022 (captura Orca das
  três rotas × dois temas contra os artboards), T023 (contagem de eventos
  na tela × contagem no trace do banco).

Três coisas para lembrar na hora de rodá-las:

- **O deploy leva todos os componentes**, não os que parecem ter mudado.
  Uma onda já perdeu uma hora concluindo que uma feature não funcionava
  porque o componente que carregava o comportamento medido tinha ficado
  para trás.
- **`Synced + Healthy` não quer dizer que a aplicação respondeu.** Aquecer
  as rotas antes do acceptance custa segundos e evita investigar um defeito
  que não existe.
- **A contagem no banco é lida de dentro do cluster, pelo orquestrador.**
  A 030 já disse o que medir: o número de eventos renderizados na tela do
  run do acceptance contra a contagem de eventos de trace daquele mesmo
  `run_id` no store.

## 8. Orçamento

O slot rodou com dois implementers em paralelo. Os dois juntos gastaram
cerca de 2,3 milhões de tokens de subagente; a janela semanal foi de 93%
para 99% durante a execução. O que custa não é despachar — é narrar: ler
dois relatórios juntos, numa volta só, em vez de comentar cada um.
`tools/sample_rate_limit.py` responde a única pergunta que importa, que é
se o ritmo atual chega ao teto antes da janela virar.
