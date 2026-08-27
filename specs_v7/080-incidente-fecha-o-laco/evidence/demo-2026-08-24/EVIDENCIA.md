# A demo, executada — 2026-08-24

Contra staging real (`stg-ninjasre.lan.kyo.ninja`) e o hipervisor Proxmox real
do cluster HAL9000. Contêiner CT122 (`redis`, nó `pve01`) parado com
autorização explícita do operador, fora por **18 minutos**, religado.

## A linha do tempo

| | o que | quando (UTC) |
|---|---|---|
| — | `pct stop 122` | 10:26:29 |
| E1 | `ProxmoxGuestStopped` ativa | 10:27:34 |
| E1 | dispara, cumprido o `for: 2m` | 10:29:34 |
| E2 | `POST /webhooks/alertmanager` → **202** | 10:29:45 |
| E3 | incidente `inc_05328c58ca88676b` aberto | 10:29:45 |
| E4 | investigação `d393d5d0…` gravada | 10:29:45 |
| E5 | investigação conclui, 5 passos, 23s | 10:30:08 |
| — | `pct start 122` | 10:44:47 |
| E10 | incidente fecha sozinho | 10:50:06 |

Nenhum alerta foi emitido à mão. Cada passo depois do `pct stop` aconteceu
porque o anterior aconteceu.

## Estações cumpridas

**E1 — o alerta dispara sozinho.** `activeAt` 10:27:34, disparo 10:29:34,
nomeando `redis` e `lxc/122`.

**E2 — a entrega chega.** `202`, autenticada. A tela do incidente diz por quem:
*"the delivery was authenticated by alertmanager-delivery"*.

**E3 — o incidente abre com identidade endereçável.**
`/incidents/inc_05328c58ca88676b` — curto, estável, sem `%3A`, `%40` ou `%2B`.
Nenhum painel diz que não pôde preencher. O chip diz o estado real
(*Investigation running*), não *Unknown*. `Proposed action` diz *"Nothing
proposed yet"* com a frase inteira, que é o estado correto naquele instante.

**E4 — a investigação gravou.** 13 eventos, 5 turnos, 44.746 tokens, com o
custo repartido por turno.

**E5 — o relato é legível.** A manchete é uma frase:

> Proxmox LXC container redis on node pve01 stopped unexpectedly causing
> service and exporter outages

Não é identificador, não é markdown cru, e **nomeia o nó certo**.

**E6 — as ferramentas condizem.** Cada chamada pareada com seu resultado e um
estado honesto:

| capacidade | resultado |
|---|---|
| `prometheus_active_alerts` | SUCCEEDED |
| `proxmox_guest_tasks` | FAILED — *proxmox answered 501: Method 'GET /nodes/pve01/lxc/122/status/tasks' not implemented* |
| `changes_in_window` | FAILED — *No change source is configured for this deployment, so whether anything changed before this incident is unknown rather than answered.* |
| `assess_evidence_sufficiency` | SUCCEEDED |

As duas falhas trazem a mensagem real do upstream, verbatim. A segunda recusa
afirmar um negativo — *"unknown rather than answered"* —, que é a disciplina
que esta onda inteira persegue.

**E10 — o incidente reflete o desfecho.** Fechou sozinho às 10:50:06:

    state:         resolved
    close_reason:  ProxmoxGuestStopped was resolved upstream
    self_resolved: true

O produto **não reivindica** ter consertado nada. Registra que a causa sumiu a
montante e que a resolução não foi dele. Foi um humano quem religou, e o
registro diz isso.

## Estações NÃO exercidas, e por quê

**E7, E8, E9 — propor, aprovar, executar.** Não aconteceram, e a razão não é
falha de ambiente nem de tela.

O catálogo inteiro deste deployment tem **três** capacidades de escrita:

    integrations/alertmanager/tools/acknowledge_incident.py   WRITE_REVERSIBLE
    integrations/pushover/tools/post_message.py               WRITE_REVERSIBLE
    integrations/telegram/tools/post_message.py               WRITE_REVERSIBLE

As três são aviso ou reconhecimento. **Nenhuma capacidade, em lugar algum do
catálogo, atua sobre infraestrutura** — nada reinicia um serviço, liga um
convidado ou muda estado de sistema. As vinte capacidades do Proxmox são todas
de leitura; até `proxmox_guest_start_diagnosis` diagnostica uma partida que
falhou, não a executa.

A maquinaria em volta está inteira e funcionando: o balcão compôs 20
capacidades, o portão se registra por run em `pre_tool_use`
(`gateway/runtime/investigator.py:375`), o fluxo de aprovação existe, o teto de
ferramentas é 40 e só 4 foram usadas — logo nada foi cortado por orçamento.

**O agente se comportou corretamente: não tinha o que propor.** O laço fecha
até "entendi e registrei"; não fecha em "agi", porque o vocabulário de ação
está vazio.

## Achados de produto

### 1. O título do incidente é o nome do alerta, não uma frase

A tela mostra `ProxmoxGuestStopped`. O roteiro exige frase. A frase existe e o
próprio produto a produz — a manchete da investigação é uma frase correta e
completa —, mas o título do incidente não a recebe.

### 2. O cabeçalho do incidente atribui o incidente ao nó errado

O cabeçalho diz **`node pve02`**. Três linhas abaixo, na mesma tela, os rótulos
do alerta dizem **`node=pve01`**. E a investigação, na tela seguinte, também diz
`pve01`, corretamente.

A CT122 roda no `pve01`. `192.168.68.159` é o `pve02`, que é apenas onde o
`pve-exporter` está hospedado. O cabeçalho está lendo `instance` — o endereço de
quem *raspou* a métrica — e apresentando-o como o nó do sujeito.

Um operador que leia o cabeçalho abre sessão no nó errado. O produto tem o dado
certo em duas outras superfícies.

### 3. ~~A descoberta não resolve o nó do convidado~~ — **este achado estava errado**

Eu escrevi que todo `native_id` sai como `lxc/HAL9000/unknown/122` porque o
segmento do nó fica sem resolver, e apontei isso como provável causa do achado
anterior. **As duas coisas estão erradas.**

`integrations/proxmox/identity.py` diz o que aquele formato é:

    guest_identity  ->  {kind}/{cluster}/{created_at or "unknown"}/{vmid}
    node_identity   ->  node/{cluster}/{node}

O terceiro segmento é o **instante de criação**, não o nó, e `unknown` é o valor
documentado para quando o provedor não deu essa hora. O nó é excluído de
propósito: a identidade de um convidado tem de sobreviver a uma migração entre
nós, enquanto a de um nó é o próprio nome — renomear um nó não é uma operação,
é removê-lo do cluster e devolvê-lo.

Eu li um formato que não conhecia, vi uma palavra que parecia uma falta, e
construí uma causa em cima dela. Quem apurou foi um verificador que abriu o
arquivo em vez de repetir o que três leituras anteriores já vinham repetindo.

**O achado 2 continua de pé** — o cabeçalho nomeia o host do exportador, e isso
foi provado pelo contraste entre as duas travessias, não por esta dedução. O que
cai é a causa que lhe atribuí.

Fica no lugar um achado menor e real: o instante de criação **está** ausente em
todos os convidados descobertos. Pelo desenho da própria função, um convidado
que ganhe esse campo depois passa a ser "visivelmente uma identidade diferente",
o que significa que uma descoberta futura pode duplicar o que já existe.

### 4. O custo aparece de duas formas em duas telas

O painel do incidente diz `5 steps · 23s · Not recorded`. A tela do run diz
`Cost $0.00` com repartição por turno. As duas descrevem o mesmo run.

## Sobre a regra de alerta que escrevi

Antes de parar o contêiner procurei uma regra que o vigiasse e, não achando
nenhuma sobre `pve_up` de convidado, escrevi uma
(`ProxmoxGuestStopped`, commitada em `infra-cluster` como `5cbeb0e`).

**Meu diagnóstico estava incompleto.** Quatro regras já cobriam a CT122 pelo
lado do serviço e dispararam *antes* da minha: `DatabaseTcpProbeFailed`
(10:28:15), `GatusEndpointHealthcheckFailed` (10:28:30), `InstanceDown` e
`RedisExporterDown` (10:29:45). O alerta teria chegado sem eu escrever nada; o
que faltava era cobertura do convidado *como convidado*, não cobertura alguma.

A regra continua correta — verificada silenciosa contra as séries vivas antes
de carregar, e exige que o convidado estivesse rodando na última meia hora, o
que a distingue dos dezesseis convidados deliberadamente parados neste cluster.
Mas ela não era a precondição que afirmei ser.

## Imprecisão no roteiro

`ssh root@192.168.68.159 'ssh pve01 "pct stop 122"'` não funciona: `pve01` não
resolve a partir do host de entrada. O endereço que funciona é
`192.168.68.149`. A primeira tentativa falhou sem parar nada.

## O privilégio do token, que faltava aqui

Esta seção existe porque um verificador recusou marcar a tarefa correspondente:
o fato tinha sido apurado e **não estava neste arquivo**, e ele aplicou de volta
a instrução de tomar o arquivo como fonte em vez da palavra de quem o escreveu.
Estava certo. Aqui está a apuração.

O handle guardado é `proxmox/-@v1` e não carrega identidade nenhuma: o
principal está dentro do segredo cifrado, que é o cofre se comportando como
deve. Então a pergunta foi respondida pelo lado do hipervisor, no log de acesso
do `pveproxy`, correlacionando principal com caminho na janela da varredura
(06:51 local = 09:51 UTC):

    136 chamadas  prometheus@pve    /cluster/status, /cluster/resources, /version
     98 chamadas  root@pam!infra    /nodes/pveN (84), /cluster/ha (6),
                                    /cluster/resources (3), /cluster/config (2)

O padrão de `root@pam!infra` — 84 leituras de nó mais HA e configuração de
cluster — é o da varredura de descoberta, que reportou **87 chamadas ao
provedor**. O `prometheus@pve` é o exportador raspando em intervalo regular.

As ACLs do datacenter:

    /  root@pam!infra   Administrator  propagate 1
    /  prometheus@pve   PVEAuditor     propagate 1

`Administrator` com propagação inclui `VM.PowerMgmt`. **O deployment tinha
privilégio para religar o convidado**, e portanto a estação E9 não deixou de
correr por falta de permissão — deixou de correr porque não há capacidade
alguma que ligue um convidado, que é o achado de escopo registrado acima.

## O viewport das capturas

As onze capturas são de página inteira, mas com **1280px de largura**, não os
1920×1080 que a especificação declara. O navegador embarcado usado nesta corrida
tem essa janela e ela não foi redimensionada antes de capturar.

Nada do que está afirmado neste documento depende da largura — nenhuma alegação
é sobre transbordo horizontal, quebra de coluna ou o que cabe acima da dobra.
Mas as capturas não substituem uma corrida a 1920 para as alegações que forem
sobre isso, e este parágrafo existe para que ninguém as tome como se
substituíssem.

## O ciclo de publicação, executado depois da demo

Esta seção existe porque as tarefas T001–T006 são passos do orquestrador, e o
orquestrador os executou **depois** de o verificador desta feature ter
entregado. Sem isto no arquivo, elas ficariam abertas por defasagem e não por
falta.

**T001 — a onda inteira mergeada.** As dez features estão em `master`, árvore
limpa, nenhuma worktree de agente com commit pendente. 233 commits desde a base
`abbc418`.

**T002 — o portão antes de publicar.** Verde, medido peça a peça porque tarefas
de fundo desta sessão morriam sempre no mesmo ponto e o primeiro plano corta em
dez minutos:

| peça | resultado |
|---|---|
| estáticos | exit 0 — lint, formato, mypy, 7 contratos de importação, constantes, protocolos, dependências, deriva de documentação |
| `tests/unit` + `tests/architecture` | 8288 passed, 1 skipped |
| `tests/contract` (sem console) + security + chaos + corpus + synthetic + e2e | 4001 passed, 29 skipped, exit 0 |
| `tests/contract/console` | 483 passed; única falha é `test_the_untouched_baselines_still_match` |
| benchmarks | 37 passed |
| console vitest | 170 arquivos, 2802 testes; 93,77% de sentenças, 90,08% de ramos |
| console build | verde |
| console e2e | exit 0 — 335 no projeto `behaviour`, 20 no `first-day` |
| console visual | 14 baselines divergentes, **nenhuma aceita** |
| `verify_integrations` | 15 integrações em paridade completa |

Duas falhas foram encontradas e consertadas no caminho: uma deriva do documento
OpenAPI que **só existe com duas features na mesma árvore** — nenhum portão
estático a pegava — e uma varredura que caminhava sobre a saída do próprio
Playwright.

**T003 — publicado sem `COMPONENTS=`.** `make deploy-stg`, exit 0, componentes
`app proxy web`. A tarefa exigia isso e estava certa: a publicação anterior
levara só `app` e `web`, deixando o proxy de credencial trinta horas atrasado.

Ela revelou um bloqueio real: o manifesto declarava **quatro** componentes e o
cluster roda três. O quarto, `console`, é a mesma roda que o `app` iniciada
noutro ponto de entrada — uma segunda cópia inteira da aplicação, não um
front-end — e a cópia que este cluster rodava tinha derivado dezoito horas
enquanto o `web` apontava para ela. Retirado do manifesto de staging, com a
compensação escrita no lugar: tráfego de navegador e de agente passam a dividir
um gateway.

**T004 — Argo reconciliou.** `Synced/Healthy`, commit GitOps `83d7ef9b8bde`.

**T005 — o serviço responde, confirmado à parte.** `Synced + Healthy` diz que o
cluster é o que o Git pediu, não que a aplicação funciona. Então:

    GET /                      -> HTTP 307 para /sign-in em 0,03s
    POST /api/session          -> sessão obtida
    POST .../proxmox/verify/report -> ok: True, "Proxmox accepted the token."
    select count(*) estate     -> 100 recursos, sobreviveram ao deploy

**T006 — o digest e o estado.** GitOps `83d7ef9b8bde`; os três pods subiram
juntos e os três antigos saíram; `app`, `proxy` e `web` em `1/1 Running`.

### E a correção da 070, provada contra o deployment novo

O defeito que esta demo encontrou era que uma declaração de confiança só valia
depois de reiniciar o processo. Contra o código publicado agora, **sem reiniciar
nada**:

| ação | resultado |
|---|---|
| declarar o fingerprint errado | `ok: False` na chamada seguinte, nomeando os dois fingerprints |
| restaurar o correto | `ok: True`, também imediato |

Antes, as duas transições exigiam um `rollout restart`. É a única estação da
demo cujo achado já está fechado e reverificado no ambiente real.

## T014 — o webhook recusa o que não se autentica

A metade que faltava. A aceitação já estava provada (`202`, na linha do tempo
acima); a recusa não tinha sido sondada, e um verificador recusou creditar a
tarefa por isso — corretamente, porque metade de uma alegação não é a alegação.

Duas sondas contra `POST /webhooks/alertmanager` em staging, com corpo de
alerta válido:

| o que foi enviado | resposta |
|---|---|
| sem cabeçalho `Authorization` | **401** |
| `Authorization: Bearer` com token inventado | **401** |

Corpo, idêntico nos dois:

    {"error":{"type":"unverified",
              "message":"this alertmanager webhook did not verify against any
                         configured route"}}

**A mensagem não distingue credencial ausente de credencial errada, e isso é
correto.** Uma mensagem diferente para cada caso diria a quem sonda qual das
duas coisas acertou, que é um oráculo.

Conferido depois: nenhum incidente foi aberto no intervalo das sondas. A recusa
é recusa, não um `401` decorativo sobre uma escrita que aconteceu assim mesmo.

## O portão visual, depois da revisão das baselines

O `test_the_untouched_baselines_still_match` que bloqueava o T002 **passa
agora**. Catorze baselines divergiam; seis foram revisadas imagem a imagem e as
diferenças rastreadas até a causa, duas regressões reais foram encontradas e
consertadas nesse exame, e oito foram aceitas depois disso.

    make console-visual   exit 0   — 33 passed
    make console-e2e      exit 0   — 335 (behaviour) + 20 (first-day)

As duas regressões que a revisão pegou, e que nenhum portão pegaria:

1. **Uma manchete virou rótulo.** Duas linhas do painel "16 items need you"
   mostravam `manual investigation` no lugar de uma frase, porque o sintetizador
   monta o objetivo a partir do gatilho quando a entrada não declara manchete, e
   um run disparado à mão carrega o objetivo que o operador escreveu — campo que
   este dataset não tem. Identificador onde vai frase é exatamente o que esta
   onda existe para remover.

2. **O nome da página truncava a 320px.** `Resources` virava `Resourc…`, sem
   nenhuma forma de ler o resto: o tooltip é deixado sem valor de propósito para
   um título comum, e um aparelho de toque não abre tooltip. Abaixo disso, as
   ações ficavam ao lado do título em qualquer largura, sobrando ao nome menos
   espaço que a própria palavra. O cabeçalho passou a empilhar abaixo da quebra
   e está inalterado acima dela.

Um defeito mais antigo foi encontrado no mesmo exame e **não** foi consertado:
a 320px a tabela de recursos ainda desenha sete colunas, com os rótulos do
cabeçalho sobrepostos em "RESOURKINDZONE" e cada célula cortada a uma letra e
reticências. É anterior a esta onda e não é o que estas baselines tratam.

## As três tarefas operacionais, medidas

Estavam abertas desde antes da onda, citadas no backlog como "estado
desconhecido". Agora não estão.

### T064 — resolução de nomes de dentro de cada contêiner de monitoração

    CT137  prometheus              ;; connection timed out; no servers could be reached
    CT136  prometheus-alertmanager 10.20.20.17   stg-ninjasre.lan.kyo.ninja
    CT138  gatus                   10.20.20.17   stg-ninjasre.lan.kyo.ninja

**Feito para dois dos três; o Prometheus não resolve.** E qual dos três importa
mais que a contagem: quem entrega o webhook é o **Alertmanager**, e ele resolve.
É por isso que a entrega funciona apesar disto — a demo mediu `202` e sete
entregas ao mesmo incidente ao longo do dia.

O Prometheus não precisa alcançar este deployment: ele raspa exportadores e
avalia regras. A falta ali não quebra nada hoje, mas é assimetria não declarada
entre contêineres da mesma pilha, e o dia em que alguém apontar um receptor a
partir do Prometheus ela custa uma tarde.

Os dois que resolvem apontam `10.20.20.17`, que é o endereço de entrada que
preserva o IP de origem — o certo dos dois.

### T065 — sincronização de segredos

Nenhum recurso de segredo gerenciado existe neste namespace: sem
`InfisicalSecret`, sem `ExternalSecret`, sem `SealedSecret`. Os três segredos
que existem:

    ninjasre-encryption-key   Opaque                              1 chave
    ninjasre-local-account    Opaque                              1 chave
    ninjasre-stg-db-conn      connection.crossplane.io/v1alpha1   4 chaves

**Estado real: parcialmente gerenciado.** A conexão do banco é provisionada
pelo Crossplane e sincroniza; a chave de cifra e a conta local são escritas à
mão. Não há decisão registrada em lugar nenhum de conviver com isso — havia a
ausência de qualquer registro, que é o que esta tarefa existe para acabar.

### T066 — a chave do gateway de modelos

    Google Gemini   ●Verified
    Provider        Google Gemini
    Model           Gemini Flash Latest
    Set at: default

Captura em `antes-01-modelos.png`. **Verified**, e foi esse provider que
conduziu as investigações da demo e as sete do laço de leitura.
