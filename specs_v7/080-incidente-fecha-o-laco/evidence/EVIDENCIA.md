# Evidência consolidada — o incidente fecha o laço

> **Este arquivo é o gabarito, e ele aterrissou antes da demo.** O formato dos
> campos foi fixado antes de alguém saber o que ia acontecer, que é a única
> razão pela qual eles valem alguma coisa agora que estão preenchidos.
>
> **Preenchido pelo orquestrador em 2026-08-25**, contra o cluster e o banco de
> staging, a partir da execução de 2026-08-24. Onde um campo cita um arquivo,
> o arquivo tem a saída literal; onde um campo diz "não exercida", a razão está
> escrita ao lado e nunca é omissão.
>
> A execução narrada em prosa está em `demo-2026-08-24/EVIDENCIA.md` e em
> `laco-de-leitura-2026-08-24/EVIDENCIA.md`. Este arquivo é a forma tabular
> combinada de antemão, e onde os dois divergirem **este** é o que foi medido
> por último.

**Veredito da demo, em uma frase:** o laço fecha do alerta ao incidente fechado
— dispara sozinho, entrega autenticada, investigação que grava turnos e chamadas
lidas do banco, relato com manchete que é frase, incidente que registra o
desfecho sem reivindicar o conserto — e **para antes de agir**, porque a ação
que consertaria aquele incidente foi cortada da oferta de ferramentas por
diferença de idioma entre o alerta e o catálogo, não por falta de mecanismo.

---

## 1. A versão que a demo mediu

| Fato | Valor |
|---|---|
| Commit da árvore da onda | `master`, 233 commits desde a base `abbc418`, árvore limpa e nenhuma worktree de agente com commit pendente |
| Features mergeadas | as dez, todas em `master` — vereditos por feature em `../../CONFRONTO.md` |
| `make verify` antes de publicar | **verde, medido peça a peça** e não como um comando só: estáticos exit 0; `tests/unit`+`architecture` 8288 passed / 1 skipped; contract+security+chaos+corpus+synthetic+e2e 4001 passed / 29 skipped; `tests/contract/console` 483 passed; benchmarks 37; vitest 2802 em 170 arquivos; console e2e 335+20. Detalhe em `demo-2026-08-24/EVIDENCIA.md` |
| Digests publicados por `make deploy-stg` | exit 0, componentes `app proxy web`, **sem `COMPONENTS=`** — a publicação anterior levara só `app` e `web` e deixara o proxy de credencial trinta horas atrasado |
| Estado do Argo no instante da demo | `Synced/Healthy`, commit GitOps `83d7ef9b8bde` |
| Pods de pé | `app`, `proxy` e `web` em `1/1 Running`, os três subiram juntos e os três antigos saíram |
| `/health/ready` do `app` | conferido à parte do Argo, porque `Synced + Healthy` diz que o cluster é o que o Git pediu e não que a aplicação responde |
| A URL pública respondendo | `GET /` → **HTTP 307** para `/sign-in` em 0,03s; `POST /api/session` devolveu sessão; `select count(*)` do estate → **100 recursos**, sobreviveram ao deploy |

**Ressalva que fica com a versão**: o `make verify` acima é o da árvore
publicada. A árvore de fechamento ganhou depois dele o commit que grava
`selection_rationale` (`ee68164`), e o portão foi rodado de novo por causa
disso — o resultado está em §9.

Uma evidência que não aponta uma versão prova algo sobre um sistema que não se
sabe qual era. As duas linhas do Argo e do serviço são conferidas
**separadamente**: reconciliar Git não é responder HTTP.

---

## 2. Aptidão do ambiente — conferido, nunca alterado

| # | Item | Conferido? | Saída / onde |
|---|---|---|---|
| A1 | Identificador da organização | **sim** | `default` — única organização em `agent_runs`, relida do banco em 2026-08-25 |
| A2 | Provedor de modelo **Verified**, chave vinda do cofre | **sim** | Google Gemini ●Verified, modelo Gemini Flash Latest, `Set at: default`. Foi este provider que conduziu as investigações da demo e as sete do laço de leitura. `demo-2026-08-24/antes-01-modelos.png` |
| A3 | Proxmox conectado, confiança de certificado declarada | **sim** | `POST .../proxmox/verify/report` → `ok: True, "Proxmox accepted the token."` E mais forte: contra o deployment publicado, declarar o fingerprint errado passou a devolver `ok: False` **na chamada seguinte, sem reiniciar nada**, nomeando os dois fingerprints; restaurar o correto voltou a `ok: True` na hora. Antes, as duas transições exigiam `rollout restart` |
| A4 | `/resources` lista recursos reais; contagem de `estate_resources` | **sim** | **100 recursos**, medido no deploy e reconferido em 2026-08-25. Sobreviveram ao deploy |
| A5 | Token do Proxmox com gerência de energia (`VM.PowerMgmt` em `/vms`) — **não alterado** | **sim, e nada foi alterado** | Respondido pelo lado do hipervisor, porque o handle guardado (`proxmox/-@v1`) não carrega identidade — o principal está dentro do segredo cifrado, que é o cofre se comportando como deve. No log do `pveproxy`, na janela da varredura: 98 chamadas de `root@pam!infra` (84 leituras de nó, HA, configuração de cluster) e 136 de `prometheus@pve`. ACLs do datacenter: `root@pam!infra` → `Administrator`, `propagate 1`, que inclui `VM.PowerMgmt`. **O deployment tinha privilégio para religar o convidado** |
| A6 | Vítima confirmada pelo operador | **sim** | CT122 (`redis`, nó `pve01`), autorização explícita do operador, janela combinada |
| A7 | Vítima `running` | **sim** | `pct status` reconferido na abertura da janela, porque o estado podia ter mudado desde a checagem anterior |
| A8 | Regra de alerta que cobre a vítima, ativa; expressão e `for` | **sim, e o diagnóstico que a motivou estava incompleto** | `ProxmoxGuestStopped`, `for: 2m`, sobre `pve_up` de convidado, exigindo que o convidado estivesse rodando na última meia hora — o que a distingue dos dezesseis convidados deliberadamente parados neste cluster. Verificada silenciosa contra as séries vivas antes de carregar. **Mas ela não era precondição**: quatro regras já cobriam a CT122 pelo lado do serviço e as quatro dispararam antes dela |
| A9 | Rota do Alertmanager casa a severidade emitida | **sim** | `severity=critical` roteada; a entrega chegou com `202` |
| A10 | Webhook recusa entrega sem credencial | **sim** | Duas sondas contra `POST /webhooks/alertmanager` com corpo válido: sem `Authorization` → **401**; `Bearer` inventado → **401**. Corpo idêntico nos dois, `{"error":{"type":"unverified",...}}` — **a mensagem não distingue credencial ausente de errada, e isso é correto**: distinguir seria um oráculo. Conferido depois: nenhum incidente aberto no intervalo das sondas |
| A11 | Alertas já disparando agora (matéria-prima do laço de leitura) | **sim** | Escolhido e registrado no runbook do laço de leitura, com a razão |
| A12 | Balcão de remediação: `desk_composed` ou `desk_skipped` + `missing` | **sim — `desk_composed`** | O balcão compôs **20 capacidades**; o portão se registra por run em `pre_tool_use`; o teto de ferramentas é 40 e só 4 foram usadas, logo **nada foi cortado por orçamento** |

Nenhum item ficou não conferido, então nenhuma estação foi bloqueada por
aptidão. As estações que não correram, correram por outra razão, e ela está
em §4 e §7.

Um item não conferido **não bloqueia por si**: ele bloqueia a estação que
depende dele, e isso fica escrito na linha da estação.

---

## 3. O que o staging media antes da demo — o vermelho registrado

O gabarito só prova alguma coisa se as consultas devolverem os valores de
partida **antes** da demo. Uma consulta que já devolvesse verde antes não
estaria medindo o laço.

**Rodado a seco em 2026-08-25**, contra o run pré-onda
`c2af8f73fa484061b483c6a4e9148131`, concluído em 2026-08-22 23:51:38Z —
quarenta e uma horas antes de a primeira feature desta onda ser publicada.

Isto foi feito **depois** da demo, e não antes, e vale a pena dizer por quê em
vez de esconder: duas passagens anteriores registraram esta seção como
impossível, com o argumento de que o deploy já estava vivo havia mais de um dia
e uma consulta hoje devolveria "o total de hoje rotulado de antes". **O
argumento confunde o instante com o sujeito.** O "antes" desta seção não é um
relógio: é um run que rodou antes de o gravador existir. Nada foi preenchido
retroativamente, então o que um run velho não gravou ele continua não tendo
gravado, e o retrato permanece tirável enquanto aquele run estiver na tabela.

| Consulta | Valor de partida esperado (medido em 2026-08-23) | Valor medido a seco | Confere? |
|---|---|---|---|
| `run_turns` para um run pré-onda | `0` | **0** | **sim** |
| `tool_calls` para um run pré-onda | `0` | **0** | **sim** |
| `evidence` para um run pré-onda | `0` | **0** | **sim** |
| custo por turno, para um run pré-onda | nenhum turno gravado, logo nenhum custo | **0 linhas** | **sim** |
| `trace_events` (total da instância) | `73`, para 37 runs concluídos | **2** para aquele run; **3.626** na instância hoje | **parcialmente** — o total "antes" é a única linha desta seção irrecuperável, porque o total de hoje soma os runs da própria onda. Os 2 daquele run batem com a média de 73÷37 |
| `agent_runs.headline` de um run pré-onda | ausente — a manchete não existia | **vazia**; e 20 de 20 runs de 22/08 sem sentença | **sim** |
| `agent_runs.summary` de um run pré-onda | começa com `###` | **`### Findings & Root Cause Analysis`** | **sim** |
| `approvals` de remediação | nenhuma linha, para nenhum run | **0 linhas** | **sim** |
| `rollback_plans` | nenhuma linha | **não coletada** — a consulta exige `--approval`, que não existe. O coletor escreveu isso no arquivo em vez de devolver zero: *"a station without evidence is not a station that passed"* | **honesto**, não verde |
| `remediation_outcomes` | nenhuma linha | **0 linhas** | **sim** |
| `episodes` | nenhuma linha para um run | **0 linhas** | **sim** |
| `estate_resources` | estate vazio | **100 recursos** | **NÃO — e é a linha mais importante desta tabela** |

**A linha do estate é o achado que esta seção existe para pegar.** T035 manda
parar quando uma consulta já devolve verde antes da demo, porque então ela está
medindo outra coisa. Esta devolve. A razão não é defeito: o estate foi povoado
por um slot anterior desta mesma onda, semanas depois de o valor de partida ter
sido escrito. Ela mede corretamente — só não mede *esta demo*. Fica registrada
como precondição atendida (§2, A4) e **não** como evidência do laço.

Saída literal, estação por estação, em `consultas/000-partida.txt` e nos oito
arquivos de `consultas/000-partida/`.

E o contraste, com o mesmo coletor e as mesmas consultas, contra o run da demo
`d393d5d0916c404b854337a270fa825d` (`consultas/laco-inteiro/`):

| | run pré-onda | run da demo |
|---|---|---|
| `run_turns` | 0 | **5** |
| `tool_calls` | 0 | **4** |
| `evidence` | 0 | **0** |
| `trace_events` | 2 | **13** |
| manchete | vazia | **uma frase**: *"Proxmox LXC container redis on node pve01 stopped unexpectedly causing service and exporter outages"* |

**Duas coisas a não arredondar neste contraste.** A primeira: `evidence`
continua em zero para o run da demo. A tabela não está morta — 24 linhas
existem na instância, de `loki`, `prometheus`, `proxmox`, `grafana`,
`alertmanager` e `reasoning` —, mas elas cobrem 7 dos 203 runs que gravam
turnos, e **as 24 têm `cited = false`**, sem exceção. Nada é jamais marcado
como citado. A segunda: a manchete não é um caso isolado. Por dia, runs sem
sentença — 20 de 20 em 22/08, 125 de 142 em 23/08, **1 de 139** em 24/08,
**0 de 47** em 25/08. A correção está viva em produção e mede-se sozinha.

---

## 4. As estações

O laço de leitura exercita E1 a E7. O laço inteiro continua em E8, E9 e E10.

Cada estação carrega: **o que se esperava ver**, **a evidência que se viu**, a
**consulta com a saída literal**, o **veredito** e o **instante**.

Vereditos possíveis: `PASSOU` · `REPROVOU (produto)` · `REPROVOU (ambiente)` ·
`NÃO EXERCIDA` — este último com a razão nomeada, nunca "aprovada por omissão".

### E1 — o alerta dispara sozinho

- **Expectativa:** dentro do `for` da regra mais o `group_wait` da rota, o
  alerta fica ativo sem ninguém o ter emitido.
- **Evidência (tela):** — (estação sem tela: o alerta é lido no Alertmanager)
- **Consulta / comando e saída literal:** `activeAt` 10:27:34, disparo 10:29:34 cumprido o `for: 2m`, nomeando `redis` e `lxc/122`. Ninguém emitiu nada: o `pct stop 122` foi às 10:26:29 e cada passo depois dele aconteceu porque o anterior aconteceu
- **Veredito:** **PASSOU**
- **Instante:** 2026-08-24 10:29:34Z
- **Ressalva registrada:** quatro regras do lado do serviço — `DatabaseTcpProbeFailed` (10:28:15), `GatusEndpointHealthcheckFailed` (10:28:30), `InstanceDown` e `RedisExporterDown` (10:29:45) — já cobriam a CT122 e **dispararam antes** da regra escrita para esta demo. A estação passa; a afirmação de que nada vigiava o contêiner era palpite com roupa de achado

### E2 — a entrega chega autenticada

- **Expectativa:** a entrega registrada com origem, horário e resultado; a mesma
  rota recusa quem chega sem credencial.
- **Evidência (tela):** `telas/incident-detail.png` (a entrega, na mesma tela do incidente)
- **Consulta / comando e saída literal:** `POST /webhooks/alertmanager` → **202**, autenticada. A tela do incidente diz por quem: *"the delivery was authenticated by alertmanager-delivery"*, e a timeline grava isso como evento `alert_received` (`consultas/laco-inteiro/E10-*`). A metade da recusa: sem `Authorization` → **401**; `Bearer` inventado → **401**; corpo idêntico nos dois, e nenhum incidente aberto no intervalo das sondas
- **Veredito:** **PASSOU** — as duas metades, aceitação e recusa
- **Instante:** 2026-08-24 10:29:45Z

### E3 — o incidente abre com título legível e sujeito resolvido

- **Expectativa:** título que é uma frase; sujeito que o estate resolve; zero
  painéis "não foi possível preencher"; nenhum `%3A`, `%40` ou `%2B` na URL.
- **Evidência (tela):** `telas/incidents-list.png`, `telas/incident-detail.png`
- **Consulta / saída literal:** `consultas/E3-*`
- **Veredito:** **REPROVOU (produto)** — duas das quatro sub-alegações caem
- **Instante:** 2026-08-24 10:29:45Z
- **O que passou:** o incidente abre em `/incidents/inc_05328c58ca88676b` — curto, opaco, estável, **sem `%3A`, `%40` ou `%2B`**. Nenhum painel diz que não pôde preencher. O chip diz o estado real (*Investigation running*), não *Unknown*, e `Proposed action` diz *"Nothing proposed yet"* com a frase inteira, que era o estado correto naquele instante
- **O que reprovou:** o **título** é `ProxmoxGuestStopped` — o nome do alerta, não uma frase — enquanto o próprio produto produz a frase certa na tela seguinte. E o **sujeito gravado está errado**
- **A correção que o SQL literal trouxe, e que a prosa não tinha:** o achado anterior dizia que *o cabeçalho* lê `instance` e mostra o host do exportador. É mais fundo. A consulta de sujeito devolve, literalmente:

      resource_id  res-47555daca81efa67dacce16fb42c898e
      kind         node
      native_id    node/HAL9000/pve02
      display_name pve02

  O incidente de um **convidado** parado (`redis`, `lxc/122`, no `pve01`) tem como sujeito gravado o **nó** `pve02`, que é apenas onde o `pve-exporter` está hospedado. O casamento foi por endereço (`matched_on: address`, `target_label: instance`, `target: 192.168.68.159`), e é aí que o erro nasce. A tela não está lendo o rótulo errado: ela está exibindo fielmente um sujeito que a borda resolveu errado. **Dona e conserto mudam de lugar por causa disto** — é o casador de alerta para recurso, não o componente de cabeçalho

### E4 — a investigação grava turnos, chamadas, evidência e custo

- **Expectativa:** N chamadas na tela ⇔ N chamadas no banco; o que cada uma
  devolveu; custo por turno; lido **depois de um reload**.
- **Evidência (tela):** `telas/run-detail.png`
- **Consulta / saída literal:** `consultas/E4-*`
- **Valor de partida ao lado:** `run_turns=0`, `tool_calls=0`, `evidence=0`
- **Veredito:** **PASSOU, com uma lacuna nomeada**
- **Instante:** 2026-08-24 10:29:45Z → 10:30:08Z; consultas relidas em 2026-08-25
- **Medido, depois de reload, do banco e não do processo:** `run_turns` **5**, `tool_calls` **4**, `trace_events` **13**, custo repartido turno a turno (44.746 tokens no total). Contra `0 / 0 / 0 / 2` no run pré-onda
- **A lacuna:** `evidence` = **0** para este run. A tabela não está morta — 24 linhas na instância, de `loki`, `prometheus`, `proxmox`, `grafana`, `alertmanager` e `reasoning` — mas cobrem 7 de 203 runs, e **as 24 têm `cited = false`**. Nada é jamais marcado como citado. A estação passa pelo que ela mede (a investigação grava, e grava no store); a lacuna vira achado

### E5 — o relato é legível: sentença e documento renderizado

- **Expectativa:** o título é uma sentença; o relato é documento desenhado como
  documento; nenhum caractere de sintaxe markdown aparece como texto.
- **Evidência (tela):** `telas/run-detail.png` (o relato, na mesma tela do run)
- **Consulta / saída literal:** `consultas/E5-sentenca.txt`
- **Valor de partida ao lado:** todo `summary` recente começava com `###`
- **Veredito:** **PASSOU**
- **Instante:** 2026-08-24 10:30:08Z
- **A sentença, literal:** *"Proxmox LXC container redis on node pve01 stopped unexpectedly causing service and exporter outages"* — não é identificador, não é markdown cru, e **nomeia o nó certo**, que é justamente o que o sujeito gravado errou
- **Separação provada:** a manchete é campo próprio; o documento abre com `### Summary of Findings` e é renderizado como documento, que é o desenho e não o defeito. O defeito que a onda fechou era a manchete carregar markdown, não o relatório ter
- **E não é caso isolado:** runs sem sentença por dia — 20/20 em 22/08, 125/142 em 23/08, **1/139** em 24/08, **0/47** em 25/08

### E6 — as ferramentas condizem com as integrações configuradas

- **Expectativa:** nenhuma capacidade de vendor que este deployment não
  conectou; nenhuma capacidade de remediação oferecida só para devolver recusa.
- **Evidência (tela):** — (sem captura dedicada: a rota do agente não está no varrimento transversal; a evidência desta estação é a gravação do run)
- **Consulta / comando e saída literal:** `demo-2026-08-24/T041-ferramentas-oferecidas.md`, com o registro do próprio run: `ranked 60, offered 40, cut by the ceiling 20`, cada candidata com o seu escore
- **Veredito:** **REPROVOU (produto)** — e a causa levou três explicações erradas antes de ser medida
- **Instante:** 2026-08-24 10:29:45Z; causa medida em 2026-08-24 17:19
- **O que condiz:** cada chamada aparece pareada com o seu resultado e um estado honesto — `prometheus_active_alerts` SUCCEEDED; `proxmox_guest_tasks` FAILED com o `501 Method 'GET /nodes/pve01/lxc/122/status/tasks' not implemented` **verbatim** do hipervisor; `changes_in_window` FAILED dizendo que *"whether anything changed before this incident is unknown rather than answered"*, recusando-se a afirmar um negativo; `assess_evidence_sufficiency` SUCCEEDED
- **O que não condiz:** o seletor ofereceu sete maneiras de parar, desligar, suspender, reiniciar, retomar, migrar e relocar um convidado — e cortou a única que **liga** um, num incidente cujo conteúdo era um convidado que parou
- **A causa, medida com o escorador do próprio produto:** ele ordena por sobreposição de termos entre o resumo do incidente e os casos de uso do catálogo, que são declarados em inglês. A descrição da regra de alerta estava em português. Uma frase, duas línguas:

      pt   proxmox_start_guest 0,0000   →  63ª de 60 candidatas  →  cortada
      en   proxmox_start_guest 0,7407   →  13ª                   →  oferecida

  **Uma variável.** O idioma em que o operador escreve o alerta decide se o deployment recebe a ação que conserta o incidente. Quando todas pontuam zero, o desempate é por nome, e entrar na oferta passa a depender da posição no alfabeto — foi exatamente o que a gravação mostrou: vinte capacidades cortadas, todas com escore zero, em ordem alfabética. **O produto não recusa e não avisa**: entrega quarenta ferramentas escolhidas pelo alfabeto e segue como se tivesse escolhido
- **Duas explicações anteriores, retiradas:** que o catálogo tinha três capacidades de escrita, todas aviso (tem **24**, sendo **20** de remediação); e que o balcão ou o teto de orçamento tinham cortado a ação (o teto é 40 e só 4 foram usadas). A regra de alerta foi corrigida para inglês pelo operador; **o lado do produto é decisão de escopo com dona**
- **E nada disto era visível antes:** o campo de justificativa da seleção estava vazio, e a resposta era inalcançável. Foi a instrumentação que este mesmo trabalho produziu que mostrou que o erro era de quem conduzia a demo

### E7 — a proposta com plano de reversão aguarda decisão

- **Expectativa:** exatamente uma proposta para o run da demo, com plano de
  reversão, alcance de um recurso, postura declarada, e o chip aguardando
  decisão. **Nada executa sem o operador.**
- **Evidência (tela):** `telas/decisions.png`
- **Consulta / saída literal:** `consultas/E7-*`
- **Valor de partida ao lado:** zero propostas; `/decisions` eternamente vazio
- **Veredito:** **NÃO EXERCIDA** — e a razão é de produto, não de ambiente nem de tela
- **Instante:** —
- **Medido:** `approvals` **0 linhas**, `remediation_proposals` **0**, `rollback_plans` não coletável por falta de `--approval` (o coletor escreveu isso, em vez de devolver zero). `consultas/laco-inteiro/E7-*`
- **Por que não houve o que propor:** ver E6. A capacidade que consertaria aquele incidente foi cortada da oferta por escore zero de idioma. **O agente estava certo em não propor nada** — não tinha com o quê
- **A outra metade da alegação está provada, e mais forte do que a tarefa pede:** não é que o plano de reversão acompanhe a proposta quando existe — **uma aprovação sem plano armazenado é recusada**, com o erro dizendo por quê: uma ação cujo desfazer ninguém consegue escrever é mais arriscada do que parecia quando foi proposta, e a hora de notar isso é antes de ela rodar

### E8 — o humano aprova, e a decisão é registrada antes de qualquer efeito

- **Expectativa:** estado, decisor, instante e motivo em `approvals`; o evento
  correspondente na auditoria; o plano de reversão **já registrado antes**.
- **Evidência (tela):** — (estação não exercida)
- **Consulta / saída literal:** `consultas/E8-*`
- **Veredito:** **NÃO EXERCIDA** — sem proposta, não há decisão para tomar
- **Instante:** —
- **Medido:** `consultas/laco-inteiro/E8-*` — nenhuma linha de decisão, e a consulta de auditoria correspondente vazia

### E9 — a execução acontece pelo gate

- **Expectativa:** o convidado volta a rodar; o desfecho gravado em
  `remediation_outcomes`; o episódio em `episodes`; a entrada de ação na
  timeline. Uma **falha nomeada** também fecha o laço; o que não fecha é falha
  silenciosa.
- **Evidência (comando):** `pct status <VMID>`
- **Consulta / saída literal:** `consultas/E9-*`
- **Veredito:** **NÃO EXERCIDA** — sem aprovação, não há execução
- **Instante:** —
- **Medido, com o recurso como parâmetro:** `remediation_outcomes` **0 linhas**, `episodes` **0 linhas** (`consultas/laco-inteiro/E9-*`)
- **E não foi por falta de privilégio**, que era a outra hipótese: as ACLs do datacenter dão `Administrator` com propagação ao principal que o deployment usa, o que inclui `VM.PowerMgmt` (§2, A5). O convidado foi religado à mão às 10:44:47Z

### E10 — o incidente reflete o desfecho

- **Expectativa:** o incidente mostra o que aconteceu, em vez de continuar
  parado no diagnóstico.
- **Evidência (tela):** `telas/incident-detail.png`
- **Consulta / saída literal:** `consultas/E10-*`
- **Veredito:** **PASSOU**
- **Instante:** 2026-08-24 10:49:45Z (fechamento gravado); visto na tela às 10:50:06Z
- **Literal, do banco:**

      state          resolved
      close_reason   ProxmoxGuestStopped was resolved upstream
      self_resolved  t

  E a timeline com quatro entradas: `opened` (ator `alert-router`), `alert_received` (*"the delivery was authenticated by alertmanager-delivery"*), `run_started` e `closed`
- **O que vale mais que o verde:** o produto **não reivindica** ter consertado nada. Registra que a causa sumiu a montante e que a resolução não foi dele. Foi um humano quem religou, e o registro diz isso

### R — a rejeição, em ocorrência diferente

- **Expectativa:** rejeitar sem motivo é **recusado**; rejeitar com motivo é
  **registrado**; as duas decisões aparecem na auditoria com autor, ação,
  assunto e resultado.
- **Evidência (tela):** — (estação não exercida)
- **Consulta / saída literal:** `consultas/R-*`
- **Veredito:** **NÃO EXERCIDA** — não havia proposta de nenhum tipo para rejeitar
- **Instante:** —
- **Medido:** `consultas/laco-inteiro/R-*` — zero linhas em `approvals` com estado rejeitado, e a consulta das duas decisões na auditoria devolve zero
- **Destravou em 2026-08-24 17:19:** com a descrição da regra reescrita em inglês, a capacidade que conserta o incidente passa a ser oferecida em 13º em vez de cortada em 63º. Esta estação, mais E7, E8 e E9, deixaram de estar bloqueadas por escopo de produto e passaram a depender só de uma segunda janela com o operador

---

## 5. As tarefas operacionais — verificadas, não executadas

Nenhuma linha desta seção altera infraestrutura. Cada uma registra o estado
real, feito ou não. Uma não concluída **não reprova a demo por si**; ela marca
como **não exercida** a estação que dependia dela, e entra no backlog novo.

| Tarefa | Evidência exigida | Estado real | Saída |
|---|---|---|---|
| Resolução de nomes nos contêineres de monitoração | um nome do domínio do deployment resolvendo **de dentro de cada** contêiner | **feito em dois dos três** | `CT137 prometheus` → *connection timed out; no servers could be reached*; `CT136 prometheus-alertmanager` → `10.20.20.17`; `CT138 gatus` → `10.20.20.17`. **Qual dos três importa mais que a contagem**: quem entrega o webhook é o Alertmanager, e ele resolve — é por isso que a entrega funciona, com `202` e sete entregas ao mesmo incidente ao longo do dia. O Prometheus não precisa alcançar este deployment (ele raspa exportadores e avalia regras), então a falta não quebra nada hoje; é assimetria não declarada entre contêineres da mesma pilha, e custa uma tarde no dia em que alguém apontar um receptor a partir dele. Os dois que resolvem apontam `10.20.20.17`, o endereço de entrada que **preserva o IP de origem** — o certo dos dois |
| Sincronização do segredo gerenciado | um recurso de segredo gerenciado efetivamente sincronizando, **ou** a decisão registrada de conviver com o segredo escrito à mão | **parcialmente gerenciado, e sem decisão registrada** | Nenhum `InfisicalSecret`, `ExternalSecret` ou `SealedSecret` no namespace. Existem três segredos: `ninjasre-stg-db-conn` (`connection.crossplane.io/v1alpha1`, 4 chaves) provisionado pelo Crossplane e sincronizando; `ninjasre-encryption-key` e `ninjasre-local-account` (Opaque, 1 chave cada) escritos à mão. **Não havia decisão registrada em lugar nenhum de conviver com isso** — havia a ausência de qualquer registro, que é o que esta tarefa existe para acabar. Fica registrado aqui, e vai para o backlog com o estado real |
| Chave do gateway de modelos | o provedor correspondente aparecendo **Verified** no console | **feito** | Google Gemini ●Verified, Gemini Flash Latest, `Set at: default`. Foi este provider que conduziu as investigações da demo e as sete do laço de leitura. `demo-2026-08-24/antes-01-modelos.png` |

**Nenhuma destas três alterou infraestrutura.** Cada uma conferiu evidência e
registrou o estado real, que era o combinado. Nenhuma estação da demo ficou
bloqueada por elas: a única com efeito sobre o laço seria a resolução de nomes,
e o contêiner que entrega resolve.

**Estações marcadas não exercidas por causa de uma destas: nenhuma.** As quatro que não correram — propor, aprovar, executar e rejeitar — não correram por escopo de produto, medido e nomeado em §4 (E6 e E7), e não por tarefa operacional pendente. Dizer o contrário seria debitar de uma tarefa de infraestrutura um efeito que ela não teve.

---

## 6. Achados

| # | Descrição | Estação | Classificação | Dona / "sem dono" | Destino |
|---|---|---|---|---|---|
| 1 | **A seleção de ferramentas depende do idioma e nada diz isso.** O escorador ordena por sobreposição de termos entre o resumo do incidente e casos de uso declarados em inglês. Um deployment cujos alertas estão na língua do operador pontua **todas** as capacidades em zero, o desempate vira ordem alfabética, e o produto entrega quarenta ferramentas escolhidas pelo alfabeto sem recusar nem avisar | E6 | produto | sem dona na onda | backlog novo — é o achado mais grave desta demo |
| 2 | **O sujeito gravado do incidente é o nó do exportador, não o convidado parado.** `res-47555…` = `node/HAL9000/pve02`, `kind: node`, para um incidente sobre `redis`/`lxc/122` no `pve01`. O casamento foi por endereço (`matched_on: address`, `target_label: instance`). A tela exibe fielmente um sujeito resolvido errado na borda | E3 | produto | sem dona na onda | backlog novo — **substitui** o achado anterior, que localizava o defeito no componente de cabeçalho |
| 3 | **O título do incidente é o nome do alerta**, `ProxmoxGuestStopped`, não uma frase — e o próprio produto produz a frase certa na tela seguinte | E3 | produto | sem dona na onda | backlog novo |
| 4 | **Nada é jamais marcado como citado.** `evidence` tem 24 linhas na instância, de fontes reais, cobrindo 7 de 203 runs que gravam turnos — e **as 24 têm `cited = false`** | E4 | produto | sem dona na onda | backlog novo |
| 5 | **O custo aparece de duas formas para o mesmo run**: `Not recorded` no painel do incidente, `$0.00` repartido por turno na tela do run | E4 / E10 | produto | sem dona na onda | backlog novo |
| 6 | **O instante de criação está ausente em todos os convidados descobertos.** Pelo desenho da função de identidade, um convidado que ganhe esse campo depois passa a ser visivelmente uma identidade diferente, e uma descoberta futura pode duplicar o que já existe | E3 | produto | sem dona na onda | backlog novo |
| 7 | **`prometheus_metric_statistics` devolve 400** com `start` vazio | — | produto | sem dona | visto antes da demo, **não reincidiu** nela; fica nomeado |
| 8 | **O Prometheus não resolve o nome do deployment**, enquanto Alertmanager e Gatus resolvem | §5 | ambiente | tarefa operacional | backlog novo, com o estado real |
| 9 | **Segredos parcialmente gerenciados, sem decisão registrada** | §5 | ambiente | tarefa operacional | backlog novo, com o estado real |
| 10 | **O componente `console` é um segundo gateway de API, não uma interface** — encontrado duas vezes, por caminhos que não se conhecem (no k3s e no compose). Quem serve a interface é o `web` | — | ambiente | anterior à onda | nomeado no confronto; **não** tocado no compose |

**Achados retirados, e por quê.** Dois foram escritos, medidos de novo e caíram:
que a descoberta não resolvia o nó do convidado (o terceiro segmento de
`lxc/HAL9000/unknown/122` é o **instante de criação**, e o nó é excluído de
propósito para que a identidade sobreviva a uma migração entre nós); e que o
catálogo estava vazio de ações (tem 24 capacidades de escrita, 20 delas de
remediação). Ficam registrados como retirados em vez de apagados, porque a
sequência de erros é ela mesma o achado: **três explicações erradas antes de
alguém medir**, e a que valeu veio da instrumentação que este trabalho produziu.

- **Achado de produto com dona:** entregue ao orquestrador com a estação e a
  evidência. **Não é consertado aqui.** A decisão de gastar um ciclo de reparo é
  dele.
- **Achado sem dona na onda:** vira entrada do backlog novo, na forma que o
  arquivo já pratica.
- **Depois de um reparo aceito:** a estação afetada é **reexecutada e a
  evidência substituída** — nunca acumulada como se as duas capturas fossem
  verdadeiras ao mesmo tempo.

---

## 7. Veredito

**Em uma frase:** o laço fecha do alerta ao incidente fechado — dispara sozinho, entrega autenticada, investigação que grava turnos e chamadas lidas do banco, relato com manchete que é frase, incidente que registra o desfecho sem reivindicar o conserto — e **para antes de agir**, porque a ação que consertaria aquele incidente foi cortada da oferta de ferramentas por diferença de idioma entre o alerta e o catálogo, não por falta de mecanismo.

| Estação | Veredito |
|---|---|
| E1 — o alerta dispara sozinho | **PASSOU** |
| E2 — a entrega chega autenticada | **PASSOU** (aceitação e recusa) |
| E3 — o incidente abre legível, sujeito resolvido | **REPROVOU (produto)** — título é o nome do alerta; sujeito gravado é o nó do exportador |
| E4 — a investigação grava | **PASSOU**, com `evidence = 0` como lacuna nomeada |
| E5 — o relato é legível | **PASSOU** |
| E6 — as ferramentas condizem | **REPROVOU (produto)** — a ação que conserta o incidente foi cortada por escore zero de idioma |
| E7 — a proposta aguarda decisão | **NÃO EXERCIDA** — nada a propor, por E6 |
| E8 — o humano aprova | **NÃO EXERCIDA** — sem proposta |
| E9 — a execução pelo gate | **NÃO EXERCIDA** — sem aprovação |
| E10 — o incidente reflete o desfecho | **PASSOU** |
| R — a rejeição | **NÃO EXERCIDA** — nada a rejeitar |

**Cinco passaram, duas reprovaram por produto, quatro não foram exercidas** — e
as quatro pela mesma causa única, agora medida e nomeada, não por omissão.

**O que mudou depois da demo:** a regra de alerta foi reescrita em inglês em
2026-08-24 17:19. Com isso, a capacidade que conserta aquele incidente passa de
63ª cortada para 13ª oferecida. **E7, E8, E9 e R deixaram de estar bloqueadas
por escopo de produto** e passaram a depender apenas de uma segunda janela com
o operador. Nenhuma delas foi arredondada para verde por isso.

**Estações não exercidas, com a razão:** E7, E8, E9 e R — quatro, e uma razão só. Não havia proposta para aguardar, aprovar, executar ou rejeitar, porque a capacidade que consertaria o incidente pontuou zero contra um alerta escrito em português e foi cortada em 63º lugar de 60 candidatas. Não é ambiente: a regra disparou, a entrega chegou, o balcão compôs vinte capacidades, o portão se registrou por run, e o teto de 40 não foi atingido (só 4 ferramentas usadas). Não é privilégio: o token do hipervisor carrega gerência de energia, conferido contra as ACLs. E não é omissão: **o agente estava certo em não propor nada**, porque não lhe foi oferecido com o quê.

Com a descrição da regra reescrita em inglês em 2026-08-24 17:19, a mesma capacidade passa a ser oferecida em 13º. As quatro estações deixaram de estar bloqueadas e passaram a depender de uma segunda janela com o operador.

---

## 8. A varredura de segredo — sem ela a evidência não é entregue

| Verificação | Resultado |
|---|---|
| Nenhum token, chave, senha ou credencial no texto deste arquivo | **limpo** — o que se aproxima de credencial aqui são nomes de principal (`root@pam!infra`, `prometheus@pve`) e de recurso de segredo (`ninjasre-encryption-key`), que são identificadores, não valores |
| Nenhum token, chave, senha ou credencial nos arquivos de `consultas/` | **limpo** — varrido em 2026-08-25 por padrão (`postgres://`, `password`, `Bearer`, `PRIVATE KEY`, `api_key`, `secret`), zero ocorrências. E por construção: o coletor não põe coluna que possa conter segredo em consulta nenhuma, e a string de conexão nunca entra na linha de comando — ela é lida do processo que a detém, do lado do cluster, a cada chamada |
| Nenhum token, chave, senha ou credencial **dentro das screenshots** | **limpo** — varredura visual das capturas, incluindo as recapturadas em 2026-08-25 |

**A varredura não foi feita com o segredo em `argv`.** Procurar um valor
concreto com ele na linha de comando o publica no primeiro `ps` que passar —
o processo que procura carrega aquilo que procura. A varredura é por padrão, e
a comparação, onde precisou existir, foi feita pelo próprio shell.

Uma screenshot com um valor de token é um vazamento tão real quanto um commit
com ele. E conferir vazamento com um `grep` que recebe o segredo como argumento
sempre dá falso positivo, porque o próprio `grep` nasce com ele em `argv` — use
um arquivo de padrões, ou a saída de um comando, nunca o valor na linha.
