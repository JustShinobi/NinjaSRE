# Controle — 080-incidente-fecha-o-laco

**O estado abaixo foi verificado contra o código atual da árvore mergeada**, na
worktree `agent-a639a9cf04385754f`, partindo de `4f438f7` (ponta de `master`).

Nota de execução: a worktree nasceu apontada para o **commit raiz** do
repositório (`c789c2d`, "Add initial README") — sexta ocorrência do mesmo
defeito de provisionamento nesta onda. Reapontada com `git reset --hard master`
antes de qualquer trabalho.

## Segunda auditoria — 2026-08-24, `tasks.md` confrontado caixa por caixa

O texto acima é da sessão de 2026-08-23 e continua correto sobre o que ela
verificou. Esta segunda passagem, na worktree `agent-a93e02cefd3bb41b0`
(mesmo defeito de provisionamento — **sétima ocorrência** — corrigido do
mesmo jeito, `git reset --hard master`, ponta em `10a329c`), existiu porque
`tasks.md` continuava com **0 de 92 caixas marcadas** apesar de tudo isto
estar registrado em prosa: as caixas nunca refletiam o ledger abaixo.

**O que esta auditoria fez.** Reabriu os 92 itens um a um contra o código, os
testes e — descoberta desta passagem — três commits que chegaram **depois**
de `aeb0dd6` (o último que a sessão de 23/08 conhecia), escritos por
`kyo@kyo.ninja` (o operador, não um agente) em 24/08: `9f25679` (este mesmo
arquivo), `397cff9` (a coluna do confronto ganhou a seção "S2 a S5" e
`specs_v7/010-leitura-do-relato/` ganhou dez screenshots reais contra
staging) e `9f87ac6` (o coletor **rodou de verdade** contra o banco de
staging e gravou oito arquivos reais em `evidence/`). Isso muda o que é
verificável: partes do laço de leitura (User Story 2) já têm evidência real,
embora o laço inteiro — a janela, a aprovação, a execução — continue em
branco. O detalhe de cada item está no ledger abaixo e em
`specs_v7/080-incidente-fecha-o-laco/relatorio-confronto.md`.

**O que mudou em `tasks.md`**: 32 caixas marcadas, cada uma com o `file:line`
ou o teste que a prova nesta seção. As outras 60 continuam abertas, cada uma
com uma linha dizendo por quê — nenhuma em branco. Nenhuma delas foi marcada
por leitura ao vivo de staging, cluster ou navegador: esta auditoria não
tocou nenhum dos três, por instrução — o operador está executando
`runbooks/navegador.md` à mão, e o passo destrutivo (`pct stop 122` na CT122)
é dele, uma vez, olhando.

### Atualização, mesmo dia: o laço fechou de verdade

Enquanto esta auditoria trabalhava, o operador executou o roteiro do laço
inteiro contra staging real e o hipervisor Proxmox real do cluster HAL9000.
A evidência aterrissou em `evidence/demo-2026-08-24/` — um `EVIDENCIA.md`
narrativo (151 linhas), `achados.md` (69 linhas, um rascunho anterior dos
mesmos quatro achados), `marco-zero.txt` (os três instantes que ancoram a
linha do tempo) e onze screenshots reais — na árvore compartilhada, não
nesta worktree; lida em `/srv/workspaces/NinjaSRE/specs_v7/...` porque um
`git reset --hard master` não a traria (ela não foi mergeada em `master`
por este caminho, e operações git contra a árvore compartilhada são
recusadas para uma worktree isolada). Onze screenshots foram abertos e
lidos, não só listados; dois varredura de segredo (padrão estrutural + os
dois valores reais de `.env` comparados por `grep -qF`, nunca impressos)
rodaram contra os três arquivos de texto novos — limpos.

**O que isso prova, e como.** CT122 parou às 10:26:29Z, confirmado sete
segundos depois; `ProxmoxGuestStopped` ficou ativa às 10:27:34, disparou às
10:29:34 (`for: 2m` cumprido); o webhook devolveu `202` autenticado às
10:29:45; o incidente `inc_05328c58ca88676b` abriu na mesma hora; a
investigação `d393d5d0…` gravou 13 eventos, 5 turnos, 44.746 tokens em 23s,
com uma manchete que é frase completa e nomeia o nó certo (`pve01`) — vista
diretamente no screenshot `e5-01-relato.png`, não só relatada. As quatro
chamadas de ferramenta são honestas: duas falharam com a mensagem real do
upstream verbatim (`proxmox_guest_tasks` → `501` do Proxmox; `changes_in_window`
→ "no change source is configured"), e nenhuma afirma um negativo que não
mediu. O contêiner foi religado à mão às 10:44:47Z, e o incidente **se
fechou sozinho** às 10:50:06 com `state: resolved`, `self_resolved: true` e
um `close_reason` que nomeia a causa real — o produto não reivindica ter
consertado o que um humano consertou.

**E7, E8 e E9 não aconteceram, e a razão está provada, não presumida.** Todo
o catálogo tem exatamente três capacidades de escrita —
`alertmanager_acknowledge_incident`, `pushover_post_message`,
`telegram_post_message` — e as três são aviso, não ação sobre
infraestrutura. Nenhuma capacidade liga um convidado, reinicia um serviço ou
muda estado de sistema. O balcão compôs 20 capacidades e o portão se
registra por run (`gateway/runtime/investigator.py:375`); o teto de
ferramentas é 40 e só 4 foram usadas — nada foi cortado por orçamento. **A
investigação estava certa em não propor nada**, porque não havia o que
propor. Isto é o desfecho `REPROVOU (produto)` da tarefa T053 e não um
`NÃO EXERCIDA` por falta de ambiente — a diferença que a tabela abaixo
preserva.

**Quatro achados de produto, reais, sem dona atribuída ainda:**

1. O título do incidente é `ProxmoxGuestStopped` — o nome do alerta —, não a
   frase que a própria investigação produziu como manchete. Visto nos dois
   screenshots `e3-02-incidente.png` e `e10-01-incidente-fechado.png`.
2. O cabeçalho do incidente diz `node pve02`; três linhas abaixo, na mesma
   tela, o corpo do alerta diz `node=pve01` — o correto, porque a CT122 roda
   no `pve01` e `192.168.68.159` é só onde o `pve-exporter` está hospedado.
   O cabeçalho lê `instance` (quem raspou a métrica) e o apresenta como o nó
   do sujeito. Visto nos mesmos dois screenshots; a própria investigação
   (`e5-01-relato.png`) nomeia `pve01` corretamente na mesma execução.
3. Todo convidado descoberto tem `native_id` no formato
   `lxc/HAL9000/unknown/122` — o segmento do nó é literalmente `unknown`,
   embora o exportador carregue `node=pve01`. Causa provável do achado 2.
4. O custo aparece de duas formas: o painel do incidente diz `Not recorded`;
   a tela do run mostra `$0.00` com a repartição real por turno — as duas
   descrevendo o mesmo run. Visto em `e3-02-incidente.png` (painel) e
   `e5-01-relato.png` (tela do run).

Um começo de rastreio, não uma auditoria completa: `IncidentSubject` e
`Incident` (`platform/persistence/ports/incident_store.py:148,188`) mostram
que `title` é um campo dedicado, distinto de qualquer manchete de
investigação — consistente com o achado 1 nascer de onde um incidente por
alerta é aberto (`platform/incidents/detection.py` ou `ingestion.py`, os dois
chamadores reais de `IncidentSubject` fora de teste), mas esta auditoria não
abriu esses dois arquivos para confirmar a linha exata. Nomear a dona de
cada achado fica para quem decide o ciclo de reparo, com o contexto completo
da onda à vista — inclusive porque os achados 3 e 4 apontam para tiers
diferentes (descoberta do Proxmox; gravação/leitura de custo) que esta
auditoria não teria como avaliar sem repetir o mesmo trabalho de rastreio
para cada um.

**O candidato a achado da primeira passagem não se repetiu.** A chamada
`prometheus_metric_statistics` (que devolveu `400` por parâmetro `start`
vazio na investigação `RestoreDrillStale`) não apareceu nas quatro chamadas
desta investigação nova. Continua aberto e sem dona — não corrigido, não
descartado, apenas não reproduzido desta vez.

**Uma imprecisão real no próprio roteiro**, registrada honestamente pelo
operador em `EVIDENCIA.md`: `ssh root@192.168.68.159 'ssh pve01 "pct stop
122"'` não resolve `pve01` a partir do host de entrada; o endereço que
funciona é `192.168.68.149`. A primeira tentativa falhou sem parar nada —
achado do próprio processo da demo, não do produto, e não desta auditoria
(o roteiro `laco-inteiro.md` §1/§6 desta feature ainda escreve `ssh pve01`;
corrigir o roteiro é reparo de texto desta própria feature e fica nomeado em
"O que fica pendente" abaixo, não corrigido nesta passagem porque a
substância factual mais importante — que o comando certo existe e foi usado
— já está registrada por quem executou).

**Correção que o operador pediu para refletir aqui também**: a spec e os
roteiros desta feature (não escritos por esta auditoria) afirmam que
"não existe regra que dispare quando um LXC qualquer para" e que por isso
uma regra nova seria necessária. Isso continua verdade como afirmação geral
— não existe uma regra genérica de "qualquer LXC parou" —, mas **não era a
precondição correta para a CT122 especificamente**: quatro regras
já cobrem o `redis` pelo lado do serviço —
`DatabaseTcpProbeFailed` (10:28:15), `GatusEndpointHealthcheckFailed`
(10:28:30), `InstanceDown` e `RedisExporterDown` (ambas 10:29:45) — e as
quatro dispararam **antes** da regra nova que o operador escreveu
(`ProxmoxGuestStopped`, commit `5cbeb0e` em `infra-cluster`). O alerta teria
chegado sem regra nova nenhuma; o que faltava era cobertura do convidado
*como convidado*, não cobertura alguma. A regra nova continua correta e
soma uma sexta linha de defesa (verificada contra as séries vivas antes de
carregar), só não era a precondição que o plano desta feature presumiu.
Visível na lista de incidentes (`e3-01-lista-incidentes.png`): `InstanceDown`
e `RedisExporterDown` aparecem como incidentes irmãos, 1 minuto atrás, ao
lado de `ProxmoxGuestStopped`.

**Uma imprecisão na cobertura desta própria feature, que esta auditoria
descobre e nomeia**: os onze screenshots existem, são genuinamente
full-page (alturas de até 2370px, muito além de um viewport), mas foram
capturados em **1280px de largura**, não os 1920px que `spec.md`
("Viewport normativo de medição e de screenshot: 1920×1080"), FR-023 e o
cabeçalho de `tasks.md` exigem — conferido lendo `file` sobre os onze
arquivos, não presumido. Isto é uma imprecisão do processo da demo (a
janela do navegador não foi ajustada para 1920 antes de capturar), não um
defeito de produto; nomeada aqui porque T070 não pode ser marcada feita
sem isso. A estação E2 também não tem screenshot dedicado — a evidência de
E2 é só a linha da tabela (`202`, autenticado), não uma foto de
`/settings/alert-intake`.

**Uma lacuna real da própria ferramenta desta feature, honestamente
nomeada**: nenhuma consulta do coletor rodou contra o `run`/`incident` desta
investigação nova (`d393d5d0…` / `inc_05328c58ca88676b`) — os oito arquivos
em `evidence/*.txt` continuam datados `09:11:29Z`, para a investigação de
leitura anterior (`RestoreDrillStale`). A evidência do laço inteiro é real e
convincente (screenshots + a prosa de `EVIDENCIA.md`), mas **não** é a
"consulta SQL exata e a saída literal" que FR-024 exige — é leitura de tela,
que é diferente. Recomendação, não ação desta auditoria (que não toca
staging): `uv run python -m tools.demo_evidence collect --org default --run
d393d5d0<completo> --incident inc_05328c58ca88676b --out
specs_v7/080-incidente-fecha-o-laco/evidence/demo-2026-08-24/consultas
--exec <o mesmo --exec dos roteiros>` fecharia essa lacuna em um comando.


## A fronteira desta execução, declarada antes do trabalho

- **Desta feature:** os três roteiros, o coletor de evidência com teste, a
  coluna nova do confronto, o backlog reescrito, e a suíte transversal
  determinística.
- **Do orquestrador:** toda evidência de ambiente real — cluster, Postgres de
  staging, Alertmanager, e a janela do laço inteiro com um humano aprovando.
  Esta worktree não alcança nenhum deles, e **não inventou um único número de
  staging**. A lista exata do que medir está na última seção, comando por
  comando.

## Commits, em ordem

| Commit | Conteúdo |
|---|---|
| `a0bfa74` | `docs(demo)` — os dois roteiros e o gabarito de evidência, antes da demo |
| `ca3c4be` | `feat(demo-evidence)` — o coletor: a consulta e a saída literal |
| `261c6d7` | `docs(wave)` — a coluna "quem constrói isso em produção?", lida do código |
| `1d4b68b` | `docs` — `backlog.md` reescrito em torno do que continua aberto |
| `4778f91` | `refactor(demo-evidence)` — cada instrução no seu próprio arquivo `.sql` |
| `8f0d756` | `feat(demo-evidence)` — contar os runs anteriores à coluna de manchete |
| `aeb0dd6` | `docs(demo)` — o roteiro de navegador, com o que cada tela deve dizer |

Três commits chegaram depois, do operador (`kyo@kyo.ninja`), fora desta
worktree — citados aqui porque mudam o que a segunda auditoria pôde marcar,
não porque são desta implementação:

| Commit | Conteúdo | Escopo |
|---|---|---|
| `9f25679` | `docs(demo)` — este arquivo, versão de 23/08 | só 080 |
| `397cff9` | `docs(wave)` — `CONFRONTO.md` ganha a seção "S2 a S5"; dez screenshots reais em `specs_v7/010-leitura-do-relato/evidence/` | onda inteira; nada em `evidence/` de 080 |
| `9f87ac6` | `feat(evidence)` — o coletor rodou contra staging de verdade; oito arquivos em `evidence/` reescritos com saída real; `scripts/deploy/stg-psql` novo | evidência de 080 (os oito `.txt`) + um script de deploy fora do diretório da feature |

---

## Ledger

Convenção: **FEITO** · **FEITO (já existia, verificado)** · **PARCIAL** ·
**NÃO INICIADO** · **Do orquestrador (ambiente real)**.

**A partir daqui o ledger é por tarefa, uma linha por número.** A versão de
23/08 agrupava faixas (`T007–T016`, `T037–T044`...); a segunda auditoria
abriu cada faixa porque, dentro de várias delas, o estado real não era mais
uniforme — a leitura do laço já tem evidência real para algumas estações e
não para outras dentro da mesma faixa antiga. Cada linha abaixo é a razão
que faltava ao lado da caixa, exatamente como pedido.

### Fase 1 — pré-voo (T001–T006)

**Três destas o próprio operador nomeou, em mensagem direta, e pediu para
ficarem honestamente abertas — registradas aqui como ele as descreveu, não
como suposição desta auditoria.**

| Tarefa | Estado | Detalhe |
|---|---|---|
| T001 confirmar merges + PASS, registrar commit da onda | **Do orquestrador — NÃO FEITO, dito por ele** | "A onda não está totalmente mergeada ainda. Vários worktrees continuam abertos." Não há árvore final para nomear o commit ainda |
| T002 `make verify` antes de publicar | **Do orquestrador — NÃO FEITO, dito por ele** | "`make verify` não está verde ainda. Quatro vermelhos separados estão sendo trabalhados agora." |
| T003 publicar com `make deploy-stg` **sem** `COMPONENTS=` | **Do orquestrador — NÃO FEITO como a tarefa pede, e é achado contra o preparo da demo, não contra o produto** | O operador publicou com `COMPONENTS="app web"` — mais estreito do que **esta própria tarefa** manda ("sem `COMPONENTS=`, porque a onda mudou app e console"). O proxy de credencial ficou em código de trinta horas atrás e custou uma hora de diagnóstico errado até ser notado. A tarefa dizia a coisa certa; não foi seguida. Ele fará o deploy completo antes de a onda fechar |
| T004 aguardar Argo `Synced + Healthy` | **Do orquestrador** | Não documentado no novo `evidence/demo-2026-08-24/`; nenhum texto ou screenshot de `kubectl get application`. O comportamento real do serviço ao longo de toda a demo (alerta → webhook → incidente → investigação, tudo respondendo) é indício forte de que o serviço estava servindo, mas não é o registro formal que a tarefa pede |
| T005 confirmar serviço respondendo, separado do Argo | **Do orquestrador** | Mesma razão de T004 — implícito no sucesso da demo inteira, não registrado à parte |
| T006 registrar digest + estado do Argo em `EVIDENCIA.md` | **Do orquestrador** | Não presente no novo `EVIDENCIA.md`, que é narrativo e não usa a estrutura §1 do gabarito original |

### Fase 2 — aptidão do ambiente (T007–T016)

**Reaberta depois de o laço inteiro ter rodado de verdade — a maioria virou
provável por screenshot real, aberto e lido nesta auditoria, não presumido
do texto do operador.**

| Tarefa | Estado | Detalhe |
|---|---|---|
| T007 identificador da organização | **FEITO** | `org=default`, usado com sucesso em toda consulta já coletada (ambas as investigações, a antiga e a nova) |
| T008 provider Verified, chave do cofre | **FEITO** | `evidence/demo-2026-08-24/antes-01-modelos.png`, aberto e lido nesta auditoria: "Google Gemini · **Verified**". A origem-do-cofre não aparece como texto na tela (é fato de composição, já confirmado em `gateway/http/lifespan.py:74` `compose_provider_credentials` na auditoria de 23/08) |
| T009 Proxmox conectado, confiança declarada, `/resources` real | **FEITO** | `evidence/demo-2026-08-24/antes-02-integracoes.png`: "Proxmox VE · **Verified**". `evidence/demo-2026-08-24/antes-03-recursos.png`: "100 watched · 71 healthy · 0 degraded · 14 unhealthy" — resolve a preocupação da primeira passagem desta auditoria (a leitura de banco das 09:11Z tinha pego o estate ainda vazio; o sync aconteceu depois). O fingerprint pinado especificamente não aparece nestes dois screenshots (fica atrás de "Manage") — não visto por esta auditoria, só relatado |
| T010 privilégio do token do Proxmox | **NÃO FEITO por esta auditoria — a alegação do operador não está no registro escrito** | O operador relatou em mensagem que o token é `root@pam!infra` com `Administrator`. Varredura de `EVIDENCIA.md` e `achados.md` por `root@pam`, `Administrator` e `VM.PowerMgmt`: **zero ocorrências**. O próprio operador instruiu "não tome esta mensagem como fonte, tome o arquivo" — aplicado aqui de volta a ele mesmo: sem o fato no arquivo, a caixa não é marcada |
| T011 operador confirma a vítima na abertura da janela | **FEITO** | `EVIDENCIA.md:4-5`: "Contêiner CT122 (`redis`, nó `pve01`) parado com **autorização explícita do operador**" |
| T012 vítima `running`, conferido | **FEITO** | Não por `pct status` direto, mas pela própria investigação: `evidence/demo-2026-08-24/e5-01-relato.png` — "The LXC container `redis` (`lxc/122`) hosted on node `pve01` **transitioned from running** (`pve_up == 1`) to a stopped state (`pve_up == 0`)", lido com base em métrica real, não em suposição |
| T013 regra de alerta ativa + rota casando severidade | **FEITO** | `evidence/demo-2026-08-24/e3-01-lista-incidentes.png` mostra `ProxmoxGuestStopped`, `RedisExporterDown`, `InstanceDown`, `GatusEndpointHea…`, `DatabaseTcpProbe…`, todas **CRITICAL**, abertas em minutos. Ver a correção do próprio operador sobre qual regra era a precondição, na seção de descobertas acima |
| T014 webhook recusa sem credencial | **PARCIAL, não fechável** | O lado de aceitação está provado ao vivo: `202`, autenticado (`EVIDENCIA.md:14,29-30`). A sonda específica de recusa (sem credencial) não está registrada nesta rodada |
| T015 escolher o alerta já ativo do laço de leitura, e por quê | **Do orquestrador** | Inalterado — é sobre o laço de **leitura** (`RestoreDrillStale`), um cenário diferente do laço inteiro que rodou agora |
| T016 registrar a tabela de aptidão em `EVIDENCIA.md` §2 | **Do orquestrador** | O novo `EVIDENCIA.md` é narrativo; não tem a tabela de doze linhas do gabarito original, embora cubra a maioria dos mesmos fatos em prosa |

### Fase 3 — os roteiros e o gabarito (T017–T026, T033)

| Peça | Estado | Detalhe |
|---|---|---|
| T017 roteiro do laço de leitura | **FEITO** | `runbooks/laco-de-leitura.md` — pré-condições, E1–E7, URLs reais, sem escrita e sem janela |
| T018 roteiro do laço inteiro | **FEITO** | `runbooks/laco-inteiro.md` — o que ele não é, a vítima com as duas condições, o estado inicial, o passo destrutivo, E1–E10 |
| T019 tabela de estações | **FEITO** | `laco-de-leitura.md` §3; `laco-inteiro.md` §4 |
| T020 classificação de desfechos, antes da execução | **FEITO** | `laco-de-leitura.md` §4; `laco-inteiro.md` §5 — ambiente × produto, com a dona nomeada e a regra que separa os dois |
| T021 reversão manual **antes** do passo destrutivo | **FEITO** | `laco-inteiro.md` **§1**, antes de §6 |
| T022 aprovação humana, pela interface | **FEITO** | `laco-inteiro.md` §6 passo 10 e cabeçalho |
| T023 não aprovar antes de conferir E4–E7 | **FEITO** | `laco-inteiro.md` §6 passo 9, com a razão |
| T024 rejeição em ocorrência diferente | **FEITO** | `laco-inteiro.md` §7 |
| T025 esqueleto de `EVIDENCIA.md`, em branco | **FEITO** | `evidence/EVIDENCIA.md` — 8 seções, todo campo vazio, com o aviso de que é gabarito |
| T026 varredura de segredo nos roteiros | **FEITO** | Varredura por padrão nos três arquivos: nenhuma ocorrência |
| T033 comando do coletor no cabeçalho | **FEITO** | `laco-de-leitura.md` §1; `laco-inteiro.md` §0; `navegador.md` §15 |
| (a mais) roteiro de navegador | **FEITO** | `runbooks/navegador.md` — onde clicar e o que a tela deve dizer, na cópia real do catálogo |

### Fase 4 — o coletor (T027–T032)

| Peça | Estado | Detalhe |
|---|---|---|
| T027 `tools/demo_evidence/` | **FEITO** | `queries.py`, `collector.py`, `__main__.py`, `__init__.py`, `sql/` — 23 instruções em 8 estações |
| T028 as consultas mínimas | **FEITO, com três correções ao esboço** | ver "Correções à `tasks.md`" |
| T029 arquivo por estação, consulta + saída literal | **FEITO** | `collector.py::collect` e `file_name_for`; marcadores `--- output ---` / `--- end of output ---`; a saída é escrita byte a byte |
| T030 recusa de tudo que não seja `SELECT` | **FEITO** | `collector.py::only_select` — recusa `DELETE`/`UPDATE`/`INSERT`/`DROP`/`TRUNCATE`, recusa `WITH … DELETE … RETURNING`, e recusa duas instruções numa |
| T031 teste de unidade, vermelho antes | **FEITO** | `tests/unit/tools/test_demo_evidence.py` — **31 casos** |
| T032 nenhuma credencial impressa ou gravada | **FEITO** | nenhuma instrução nomeia `credentials`, `api_tokens`, `token_hash`, `local_password_hash`; travado por teste, e o comando de conexão nunca entra no arquivo de evidência |

### Fase 12 — o confronto ganha a coluna (T079–T083)

| Peça | Estado | Detalhe |
|---|---|---|
| T080 a coluna fixa | **FEITO** | `specs_v7/CONFRONTO.md`, seção "Quem constrói isso em produção?" |
| T081 preenchida para os mecanismos exigidos | **FEITO — 17 linhas** | recorder, gate de remediação, gate de autonomia, resolvedor de integrações do time, confiança de certificado até o egress, e mais doze |
| T082 dormentes declarados | **FEITO — 3** | pipeline por estágios, `DecisionWaiter`, leitura de sinal na execução. Nenhuma célula aponta um teste |
| T083 fecha citando a demo | **FEITO** | com o caminho da evidência e o veredito honesto: **não executado** |
| T079 seção por feature com veredito do verifier | **NÃO FEITO — e é do orquestrador** | O cabeçalho do próprio `CONFRONTO.md` diz que ele é medido pelo orquestrador e **não copiado do relatório de quem implementou**. Escrever vereditos de verifier que não medi seria exatamente o que aquele cabeçalho proíbe |

### Fase 13 — o backlog reescrito (T084–T088)

| Peça | Estado | Detalhe |
|---|---|---|
| T084 tabela de destino no confronto | **FEITO — 11 de 11** | `CONFRONTO.md`, "Backlog anterior → destino". Zero itens sem destino |
| T085 `backlog.md` reescrito | **FEITO — 14 itens** | 8 saíram com evidência; 4 vieram do anterior sem fechar; os demais são desta onda |
| T086 redação conferida | **FEITO** | varredura por `FR-`, `SC-`, `specs_v*`, `Article`, número de feature, caminho de planejamento: **nenhuma ocorrência**. `test_removed_vendor_references` e `test_no_committed_file_states_a_stale_catalogue_size` verdes |
| T087 forma preservada | **FEITO** | cada item: o que acontece hoje, por que não é trivial quando não é, e o desfecho pelo qual seria julgado |
| T088 nenhum item removido sem evidência | **FEITO** | conferido linha a linha na tabela de destino |

### Fase 5 — o vermelho a seco (T034–T036)

| Tarefa | Estado | Detalhe |
|---|---|---|
| T034 coletor a seco com parâmetros de um run pré-onda → `evidence/consultas/000-partida.txt` | **Do orquestrador** | Nem o diretório `evidence/consultas/` nem o arquivo existem. O que existe é diferente por natureza: uma coleta real, mas com parâmetros de um run **novo** (o da leitura), não de um run **pré-onda** — ver T043 |
| T035 conferir que as consultas devolvem os valores de partida | **Do orquestrador** | Consequência de T034 não ter ocorrido como pedido. Os valores "antes da onda" que aparecem nos oito arquivos reais são o texto fixo de `queries.py` (`baseline=`), citado ao lado do valor medido — não uma segunda leitura independente contra um run velho |
| T036 registrar o vermelho em `EVIDENCIA.md` §3 | **Do orquestrador** | Tabela inteira sem a coluna "Valor medido a seco" preenchida |

### Fase 6 — o laço de leitura (T037–T044)

| Tarefa | Estado | Detalhe |
|---|---|---|
| T037 executar `laco-de-leitura.md` do começo ao fim | **Do orquestrador** | A cadeia de banco (alerta → incidente → investigação → proposta) rodou de verdade para `run=0c9c0d5ce453458d9e115af98763ade4`, `incident=inc_d4b0bf515a6a7e1e` — mas os passos de tela do roteiro (telas, comparação de repetição, registro em `EVIDENCIA.md`) não têm evidência anexada |
| T038 screenshots E2/E3 | **Do orquestrador** | `evidence/telas/` não existe |
| T039 screenshot E4 | **Do orquestrador** | Sem screenshot. A alegação por trás dela **está** provada por banco: `evidence/E4-...txt` — 5 `run_turns`, 4 `tool_calls`, 1 `evidence`, 12 `trace_events`, todos > 0 (partida: 0, 0, 0, para 37 runs) |
| T040 screenshot E5 | **Do orquestrador** | Sem screenshot. Provado por banco: `evidence/E5-...txt` — `headline` é uma sentença ("Weekly restore drill jobs on pve02 exceeded their maximum allowable execution window without a successful run"), `summary` continua abrindo com `### Investigation Report` |
| T041 ferramentas condizentes, tela + log | **Do orquestrador** | Nenhum artefato — nem screenshot, nem saída do `grep` do log de seleção de ferramentas |
| T042 screenshots E7 (`/decisions` + painel) | **Do orquestrador** | Sem screenshot. `evidence/E7-...txt` mostra **0 linhas** em `approvals` para este run — desfecho aceitável e declarado pelo próprio roteiro (investigação sem evidência suficiente para propor); o run vira cenário de leitura, não laço fechado |
| T043 rodar o coletor para este run, anexar saídas por estação | **FEITO** | Os oito arquivos em `evidence/*.txt` (E3, E4, E5, E7, E8, E9, E10, R), datados `2026-08-24T09:11:29Z`, com consulta e saída literal para `run=0c9c0d5c…`/`incident=inc_d4b0bf…`. Ressalva: gravados em `evidence/` diretamente, não em `evidence/consultas/` como os roteiros documentam no `--out` — desvio de local, não de substância; a saída é real e literal |
| T044 repetir e comparar (ou nomear a variação) | **Do orquestrador** | Uma coleta, um instante só; nenhuma segunda passagem registrada |

### Fase 7 — a janela, o laço inteiro (T045–T060)

**Rodou de verdade em 24/08, enquanto esta auditoria trabalhava.** As linhas
abaixo citam `evidence/demo-2026-08-24/`, não mais os arquivos antigos em
`evidence/*.txt` (que continuam sendo sobre a investigação de leitura
anterior — ver a lacuna nomeada na atualização acima).

| Tarefa | Estado | Detalhe |
|---|---|---|
| T045 abrir a janela, confirmação da vítima | **FEITO** | `EVIDENCIA.md:4-5`, autorização explícita registrada; `marco-zero.txt` ancora os instantes |
| T046 o passo destrutivo, digitado uma vez | **FEITO** | `marco-zero.txt`: `pct stop 122` às 10:26:29Z, confirmado 10:26:36Z. A primeira tentativa (endereço errado no roteiro) falhou sem parar nada — evidência extra de que foi digitado à mão, não roteirizado |
| T047 E1 — o alerta dispara sozinho | **FEITO** | `EVIDENCIA.md:12-13`: `activeAt` 10:27:34, disparo 10:29:34 (`for: 2m` cumprido); "Nenhum alerta foi emitido à mão" |
| T048 E2 — entrega autenticada | **FEITO** | `EVIDENCIA.md:14,29-30`: `202` às 10:29:45, "the delivery was authenticated by alertmanager-delivery". Sem screenshot dedicado de `/settings/alert-intake` — a evidência é textual/linha do tempo |
| T049 E3 — incidente abre legível, sujeito resolvido | **NÃO FEITO — a alegação normativa não se sustenta inteira, contra dois achados reais** | Abriu, é endereçável (`inc_05328c58ca88676b`), sem painel irrecuperável, chip correto (`Investigating`, não `Unknown`) — visto em `e3-02-incidente.png`. Mas o **título** é `ProxmoxGuestStopped` (não uma frase — Achado 1) e o **cabeçalho** atribui `node pve02` quando o convidado roda em `pve01` (Achado 2). Duas das quatro sub-alegações do próprio T049 falham, e são achados de produto nomeados, não falha desta estação em si |
| T050 E4 — investigação grava | **FEITO, com uma lacuna nomeada** | `e5-01-relato.png`: 13 eventos, 5 turnos, 44.746 tokens, 4 chamadas de ferramenta com o resultado real de cada. O coletor **não** rodou contra este `run_id`/`incident_id` — ver a lacuna na atualização acima; a contagem vem da tela, não de uma consulta SQL literal |
| T051 E5 — relato legível | **FEITO** | Manchete: "Proxmox LXC container redis on node pve01 stopped unexpectedly causing service and exporter outages" — frase completa, sem markdown, **nomeia o nó certo** (contraste direto com o Achado 2, no mesmo run) |
| T052 E6 — ferramentas condizentes | **FEITO** | Tabela de 4 chamadas em `EVIDENCIA.md:48-56`, cada uma com o resultado real, incluindo dois `501`/mensagem de configuração ausente verbatim do upstream. Nenhuma capacidade de vendor não conectado foi oferecida. Não conferida a metade de log (`tool_selection`/`integrations_unresolved`) |
| T053 E7 — proposta aguardando | **NÃO FEITO — não exercida, e a razão é do produto, não do ambiente** | O catálogo inteiro tem só três capacidades de escrita (`alertmanager_acknowledge_incident`, `pushover_post_message`, `telegram_post_message`), todas aviso — nenhuma atua sobre infraestrutura. O balcão compôs 20 capacidades, o portão registrou por run, o teto de 40 ferramentas não foi tocado (só 4 usadas): nada foi cortado por orçamento. **O agente estava certo em não propor nada** — é o desfecho `REPROVOU (produto)`/declarado, não `NÃO EXERCIDA` por ambiente |
| T054 conferir E4–E7 antes de aprovar | **NÃO FEITO** | Não se aplica: sem proposta, não há o que confirmar antes de aprovar |
| T055 E8 — operador aprova pela interface | **NÃO FEITO — não exercida, mesma razão de T053** | Sem proposta, não há decisão para tomar |
| T056 E9 — execução pelo gate | **NÃO FEITO — não exercida, mesma razão de T053** | Sem aprovação, não há execução |
| T057 E10 — incidente reflete o desfecho | **FEITO, por um caminho que a tarefa não previu** | Não pela execução (não houve). O incidente **se fechou sozinho**: `EVIDENCIA.md:62-70` — `state: resolved`, `close_reason: "ProxmoxGuestStopped was resolved upstream"`, `self_resolved: true`. O produto não reivindica ter consertado o que o operador consertou à mão — visto em `e10-01-incidente-fechado.png` (`Resolved`, chip trocado de `Investigating`) |
| T058 conferir que o alerta resolveu e fechou o incidente | **FEITO** | Mesmo texto de T057: a resolução e o fechamento são o mesmo evento, no mesmo incidente que abriu |
| T059 reversão: confirmar `running` | **FEITO** | `marco-zero.txt`: religada às 10:44:47Z, à mão — porque não havia caminho de produto que a religasse |
| T060 fechar a janela, registrar instante + resumo | **FEITO, em substância** | O próprio `EVIDENCIA.md` é esse resumo; não há uma linha "janela fechada às HH:MM" separada do último evento (E10, 10:50:06) |

### Fase 8 — a rejeição (T061–T063)

**Observação estrutural que a demo de 24/08 expõe, e que vale registrar para
quem tentar esta fase em seguida**: as únicas três capacidades de escrita do
catálogo inteiro são notificação (`alertmanager_acknowledge_incident`,
`pushover_post_message`, `telegram_post_message`) — nenhuma atua sobre
infraestrutura. Se nenhuma remediação de infraestrutura é jamais proposta (o
que T053 acabou de provar para este cenário), a "ocorrência diferente"
que FR-019 pede para a rejeição só pode nascer de uma dessas três, não de um
segundo CT122. Não exercida nesta rodada; nomeada aqui para a próxima.

| Tarefa | Estado | Detalhe |
|---|---|---|
| T061 rejeitar sem motivo, em ocorrência diferente | **Do orquestrador** | `evidence/R-...txt`: 0 linhas em `approvals` com `state='rejected'`. Nenhuma proposta de nenhum tipo apareceu na demo de 24/08 para rejeitar |
| T062 rejeitar com motivo | **Do orquestrador** | Mesma razão de T061 |
| T063 conferir as duas decisões na auditoria | **Do orquestrador** | `evidence/R-...txt`, consulta `both-decisions-in-the-audit`: 0 linhas |

### Fase 9 — tarefas operacionais (T064–T068)

| Tarefa | Estado | Detalhe |
|---|---|---|
| T064 resolução de nomes, de dentro de cada contêiner | **Do orquestrador** | Leitura via `ssh`/`getent hosts`; não executada por esta auditoria. `backlog.md` ("Three monitoring containers point at a resolver that no longer exists") carrega o estado mais recente conhecido: ainda não resolvida |
| T065 sincronização do segredo gerenciado | **Do orquestrador** | Leitura via `kubectl get infisicalsecret -A`; não executada. `backlog.md` ("The managed-secret operator in the cluster cannot authenticate") carrega o estado mais recente conhecido: ainda não |
| T066 chave do gateway de modelos, Verified | **Do orquestrador** | Leitura de console; não executada. `backlog.md` ("One model gateway has no key, so its provider never verifies") carrega o estado mais recente conhecido: ainda não |
| T067 escrever a entrada de cada uma não concluída no backlog novo | **FEITO** | As três estão em `backlog.md`, cada uma com "o que acontece hoje" e "como deveria ser julgado"; nenhuma foi omitida (ver T085) |
| T068 marcar estações não exercidas por tarefa operacional pendente | **NÃO FEITO — e a premissa da tarefa não se confirmou** | E7/E8/E9 realmente ficaram não exercidas (`EVIDENCIA.md`, "Estações NÃO exercidas, e por quê"), mas por nenhuma das três tarefas operacionais desta fase — a razão é que o catálogo não tem capacidade de escrita sobre infraestrutura, um fato de produto, não um DNS/segredo/chave pendente |

### Fase 10 — a evidência consolidada (T069–T074)

| Tarefa | Estado | Detalhe |
|---|---|---|
| T069 preencher `EVIDENCIA.md` estação por estação | **FEITO, em documento próprio** | `evidence/demo-2026-08-24/EVIDENCIA.md` amarra, por estação, expectativa/evidência/veredito em prosa — não usa os campos literais do gabarito original em `evidence/EVIDENCIA.md` (que continua em branco, intocado), mas cumpre o mesmo propósito: nenhuma alegação sem a evidência ao lado |
| T070 confirmar screenshot full-page 1920×1080 em toda estação-tela | **NÃO FEITO — largura errada, conferida por esta auditoria** | Onze screenshots reais existem, genuinamente full-page (alturas até 2370px). `file` sobre os onze: todos **1280px de largura**, não 1920px. E2 não tem screenshot dedicado |
| T071 confirmar consulta + saída literal em toda estação-gravação | **NÃO FEITO — lacuna nomeada** | O coletor nunca rodou contra `run=d393d5d0…`/`incident=inc_05328c58ca88676b`. A evidência do laço inteiro é screenshot + prosa, real e verificada por esta auditoria, mas não é "a consulta SQL exata e a saída literal" que FR-024 pede |
| T072 varredura de credencial em texto e screenshot | **FEITO** | Texto: os oito `.txt` antigos **e** os três arquivos novos (`EVIDENCIA.md`, `achados.md`, `marco-zero.txt`) varridos contra um arquivo de padrões e contra os dois valores reais de `.env` (nunca impressos) — zero ocorrências em ambas as rodadas. Screenshots: os onze abertos e lidos diretamente nesta auditoria — nenhum mostra token, senha ou credencial |
| T073 rodar acceptance das donas + transversal contra staging | **Do orquestrador** | Ainda não rodado por esta auditoria; a rodada de 23/08 (45 passed, 7 skipped) segue sendo o último registro |
| T074 veredito de uma frase + veredito por estação no topo de `EVIDENCIA.md` | **NÃO FEITO — dois terços presentes, um falta** | Presente em prosa: "Estações cumpridas" e "Estações NÃO exercidas, e por quê" cobrem o veredito por estação. Ausente: uma frase única de veredito geral no topo do documento |

### Fase 11 — os achados (T075–T078)

| Tarefa | Estado | Detalhe |
|---|---|---|
| T075 listar achados em `EVIDENCIA.md` §6 | **FEITO, em documento próprio** | `evidence/demo-2026-08-24/EVIDENCIA.md`, seção "Achados de produto": quatro achados numerados, cada um com descrição e evidência — não a tabela `# / Descrição / Estação / Classificação / Dona / Destino` do gabarito original, mas a mesma substância. Nenhum dos quatro tem dona atribuída ainda |
| T076 entregar achados de produto ao orquestrador, sem consertar | **FEITO** | Os quatro achados chegaram a esta auditoria por mensagem direta do operador, com instrução explícita de reconciliar sem consertar — nenhum arquivo de produto foi tocado (reconfirmado no fim desta atualização) |
| T077 redigir entrada de backlog para achado sem dono | **NÃO FEITO** | Nomear a dona de cada um dos quatro (ou declarar genuinamente sem dono) é decisão do orquestrador, com o contexto da onda inteira — não desta auditoria, que rastreou só um começo de pista para os achados 1/2 (`platform/persistence/ports/incident_store.py:148,188` — ver a atualização acima) e não abriu o resto do código para confirmar |
| T078 reexecutar e substituir evidência após reparo aceito | **Do orquestrador** | Nenhum reparo ocorreu ainda |

### Fase 14 — fechamento (T089–T092)

| Tarefa | Estado | Detalhe |
|---|---|---|
| T089 `make verify` completo, exit code + testes + duração | **Do orquestrador — dito por ele, não presumido**: "quatro vermelhos separados estão sendo trabalhados agora" | Não rodado por esta auditoria: é a árvore inteira, reservado ao orquestrador. Esta auditoria rodou os gates da própria superfície tocada — ver "Verificação" no relatório — todos verdes |
| T090 nenhum arquivo de produto alterado | **FEITO — reconferido depois desta atualização também** | `git diff --stat a0bfa74~1 aeb0dd6` fora da lista declarada: zero arquivos. Os commits desta auditoria (a rodada de 23/08 e esta atualização) tocam apenas `tasks.md`, este arquivo e `relatorio-confronto.md` |
| T091 este arquivo | **FEITO** | Atualizado nesta mesma passagem para refletir o laço fechado de verdade |
| T092 reportar ao orquestrador | **FEITO** | Entregue como a resposta final desta auditoria, reconciliada com a evidência real do laço inteiro |

---

## O vermelho, com a mensagem real

O único código que esta feature escreve é o coletor, e ele nasceu vermelho:

```
tests/unit/tools/test_demo_evidence.py:24: in <module>
    from tools.demo_evidence import (
E   ModuleNotFoundError: No module named 'tools.demo_evidence'
=========================== short test summary info ============================
ERROR tests/unit/tools/test_demo_evidence.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
```

Depois da implementação: **31 passed em 0,10s**.

**O análogo do test-first para o resto da feature é o gabarito antes da
execução**, e ele foi respeitado: os roteiros e `EVIDENCIA.md` aterrissaram em
`a0bfa74`, com todo campo em branco, antes de qualquer passo da demo.

---

## As 23 consultas rodaram contra um PostgreSQL real, com o schema de verdade

O maior risco deste coletor é uma consulta que não roda, descoberta às onze da
noite com a janela aberta e o contêiner parado. Medido em vez de suposto:

1. `docker run ninjasre-postgres-test:16` — a mesma imagem que a suíte de
   contrato de persistência usa, com pgvector e AGE;
2. `alembic upgrade head` com o `alembic.ini` do repositório — **o schema é o
   que as migrações produzem**, não um `create_all` aproximado;
3. o coletor, com todos os parâmetros preenchidos, através de um `psql` real
   com `ON_ERROR_STOP=1`.

**Resultado: 8 arquivos, zero ocorrências de "could not run this query".** As
23 instruções executaram.

O caminho de falha foi conferido **separadamente**, porque zero falhas só vale
alguma coisa se as falhas fossem visíveis: `SELECT no_such_column FROM
run_turns` faz o `psql` sair com código 3, o que levanta em `ShellFreeRunner` e
vira um bloco de recusa no arquivo. Os zeros são reais, não invisibilidade.

Contêiner removido; nada ficou de pé.

---

## Correções à `tasks.md`, medidas contra o schema

A `tasks.md` esboça as consultas. Três coisas nela não sobreviveriam ao schema
real, e uma quarta correção veio da onda:

1. **`SELECT index, … FROM run_turns`** — `index` precisa de aspas (`"index"`).
2. **`remediation_outcomes`** tem muito mais que `capability, resource_id,
   state, due_at`: `verdict`, `rollback`, `autonomous`, `executed_at`, `run_id`,
   `incident_id`. **`autonomous` é o campo que responde à alegação de que nada
   agiu sem decisão humana**, e virou consulta própria (`E8/nothing-executed-unattended`).
3. **`incidents` ganhou `public_id`** nesta onda. Toda consulta de incidente
   resolve **as duas grafias** — endereço curto e id interno — porque o que o
   operador tem na mão é o que está na URL.
4. **O vocabulário não é digitado.** `APPROVAL_AUDIT_RESOURCE_KIND_REQUEST`
   (`config/constants/security.py:737`), `REMEDIATION_AUDIT_RESOURCE_KIND`
   (`:813`) e `ApprovalState.REJECTED`
   (`platform/persistence/ports/approval_store.py:25`) chegam à instrução como
   parâmetro, resolvidos dos módulos que os declaram. Uma consulta não pode
   continuar perguntando por uma palavra que o produto deixou de usar — ela
   rodaria perfeitamente e devolveria nada, que se lê como evidência de
   ausência. Travado por teste.

### E1, E2 e E6 não têm consulta, e isso é deliberado

O que prova essas três é um roteador de alertas, uma tela de intake e um
transcript — nenhum deles é linha deste banco. Inventar uma consulta para elas
seria medir a coisa adjacente e chamar de resposta, que é o defeito que esta
onda existe para não repetir. Está escrito em `queries.py`, ao lado de
`STATIONS`.

---

## Gates rodados, resultado real

| Gate | Comando | Resultado |
|---|---|---|
| Teste do coletor | `pytest tests/unit/tools/test_demo_evidence.py` | **31 passed** |
| Ferramentas + arquitetura | `pytest tests/unit/tools tests/architecture` | **734 passed** |
| Lint (repositório) | `ruff check .` | **All checks passed** |
| Formatação (repositório) | `ruff format --check .` | limpo |
| Tipos | `mypy tools/demo_evidence tests/unit/tools/test_demo_evidence.py` | **Success: no issues found** |
| Constantes | `python tools/check_constants.py` | exit 0 |
| SQL fora da persistência | `python tools/check_raw_sql.py` | exit 0 |
| Credencial direta | `python tools/check_direct_credentials.py` | exit 0 |
| Deriva de documentação | `python -m tools.check_docs_drift` | exit 0 |
| Exemplos documentados | `python -m tools.test_doc_examples` | **29 documented example(s) check out** |
| Paridade do catálogo | `python -m tools.verify_integrations` | **15 integration(s) at full parity, every permission probed** |
| Contratos de import | hook de commit, em todos os commits | Passed |
| **Suíte transversal, determinística** | `spec_validation browser --feature specs_v7/080-… --test console/tests/e2e/transversal-rules.spec.ts` | **exit 0 — 45 passed, 7 skipped** |

Sobre a transversal: `EXCEPTIONS` em `transversal-rules.spec.ts:226` está
**vazia**, conferido lendo a linha. Não há rede: qualquer regressão de tela
apareceria como falha nova. Não apareceu. Os 7 pulados são o conjunto
preexistente de delegação de orçamento de rolagem, medido em
`scroll-budget.spec.ts`, e não têm relação com allowlist.

**Não rodado:** `make verify` completo (é do orquestrador, na árvore mergeada),
e qualquer coisa contra staging real.

**Reconferido pela segunda auditoria (2026-08-24), na árvore `master` atual
(`10a329c`, que já inclui as sete features restantes da onda mergeadas):**
`pytest tests/unit/tools/test_demo_evidence.py` → **31 passed**;
`pytest tests/unit/tools tests/architecture` → **734 passed**;
`ruff check`, `ruff format --check` e `mypy` sobre `tools/demo_evidence` e o
teste → limpos; `check_constants.py`, `check_direct_credentials.py`,
`check_docs_drift`, `test_doc_examples` (29 exemplos), `verify_integrations`
(15 integrações em paridade total) → todos exit 0, números idênticos aos de
23/08. A suíte transversal contra staging **não** foi rerodada por esta
auditoria — é a mesma decisão de não iniciar rede nova contra o alvo que o
operador está usando ao vivo, e o resultado de 23/08 (45 passed, 7 skipped,
`EXCEPTIONS` vazia) segue sendo o último medido.

---

## Um gate que falhou, e era meu

`tests/unit/tools/test_check_raw_sql.py::test_the_repository_writes_no_query_outside_the_storage_tree`
falhou com **22 violações**, todas em `tools/demo_evidence/queries.py`:

```
E   AssertionError: assert [Violation(pa...iteral'), ...] == []
E     Left contains 22 more items, first extra item:
E     Violation(path=…/tools/demo_evidence/queries.py, line=75,
E               detail='SELECT public_id, title, state, severity, origin, origin_id,…',
E               rule='sql-literal')
```

O detalhe que importa: **o CLI do guarda passava e o teste não.**
`tools/check_raw_sql.py` exclui `tools/` dos seus roots padrão, e o teste varre
a árvore inteira. O teste é o mais estrito dos dois, e é o que `make verify`
também roda.

Havia a tentação de argumentar — o plano desta feature declara, com todas as
letras, que o coletor é instrumento de verificação e não caminho de produto — e
argumentar teria sido afrouxar um guarda para caber o meu código. A instrução
foi obedecida: **cada instrução foi para o seu próprio arquivo `.sql`**, em
`tools/demo_evidence/sql/`, e o módulo Python lê o arquivo. O guarda ficou
intacto, e o SQL ficou melhor — um arquivo se cola numa sessão e se compara
num diff sem as aspas no caminho.

---

## Descobertas que mudam como ler a árvore daqui em diante

**(a) Três `file:line` dos controles anteriores já estavam defasados.** A 040
declarou `compose_remediation` em `gateway/http/lifespan.py:92`; a 070 declarou
`compose_control_plane` em `:98` e `compose_remediation` em `:107`. Na árvore
mergeada eles estão em **`:100`** e **`:105`**. Cada merge empurrou as linhas.
A coluna do confronto foi preenchida **lendo o código**, não copiando relatório,
e é por isso que ela está certa.

**(b) Aprovar sem plano de reversão devolve `400`, não `500` nem sucesso.**
`gateway/http/routes/approvals.py:317-322` — `RecordNotFound` é alcançado
apenas ao aprovar sem plano gravado, e vira `bad_request`. A ordem "o plano de
reversão está registrado antes da execução" **não depende de ninguém lembrar
dela**: é estrutural.

**(c) A rota de decisão devolve sucesso mesmo quando a execução falha**, de
propósito e com a razão escrita no docstring: uma falha em agir é um fato sobre
o deployment, e transformá-la em erro diria ao revisor que a decisão dele não
foi registrada quando foi. **Consequência prática para quem observa: a tela
dizendo "Approved" não é evidência de que a ação rodou.** Quem responde isso é
`remediation.approval_carried_out` no log. Está escrito no roteiro de navegador,
porque é a leitura errada mais fácil de fazer no dia.

**(d) Rejeitar sem motivo é impedido por um controle desabilitado, não por uma
mensagem de erro.** `console/src/surfaces/screens/incident-decision-controls.tsx`
— o botão **Reject** fica `disabled` enquanto o campo *Reason* estiver vazio, e
ao lado aparece "A reason is required to reject.". Quem esperar um erro depois
do clique vai concluir que a tela está quebrada.

**(e) A ordem no servidor, para a estação E8.** Decisão gravada e transação
fechada (`approvals.py:303-325`) → evento de auditoria (`:326`, com
`action = approval.decide`, `outcome = allowed` para aprovar e `denied` para
rejeitar) → **só então** `_carry_out` (`:339`). A alegação "a decisão é
registrada antes de qualquer efeito" é verificável linha a linha.

**(f) Hipótese, não veredito, sobre as duas regras transversais que falham
contra o staging.** A fixture só tem runs com manchete; o staging tem 37 runs
de antes de a coluna existir, com manchete vazia e `summary` começando com
`###`. A suíte abre o **primeiro run da lista** — provavelmente um run velho — e
mede o caminho de fallback. A consulta `E5/headline-coverage` foi acrescentada
ao coletor exatamente para transformar isso em número. **O run da demo é novo e
recebe manchete no fechamento**, então E5 deve passar para ele; se falhar **para
o run da demo**, aí é defeito de produto com dona.

**(g) Quatro capacidades somem quando o balcão compõe.**
`alertmanager_acknowledge_incident`, `propose_knowledge`,
`pushover_post_message`, `telegram_post_message` declaram nível acima de leitura
sensível e não têm componentes de remediação. Com o balcão composto elas deixam
de ser oferecidas a um turno — o filtro fazendo o que deve. É **mudança de
comportamento visível**, e entrou no backlog novo em vez de virar surpresa.

**(h) O laço de leitura já rodou de verdade, entre o controle de 23/08 e esta
auditoria — descoberto lendo `git log`, não relatado por ninguém.** Três
commits do operador (`kyo@kyo.ninja`), datados 24/08, chegaram depois de
`aeb0dd6`: `9f87ac6` reescreveu os oito arquivos de `evidence/` com saída real
do coletor contra o Postgres de staging, para o alerta `RestoreDrillStale`
(`incident=inc_d4b0bf515a6a7e1e`, `run=0c9c0d5ce453458d9e115af98763ade4`). A
metade de leitura do laço (E1 a E7) tem prova de banco: `run_turns=5`,
`tool_calls=4`, `evidence=1`, `trace_events=12`, todos maiores que zero contra
uma partida de zero; a manchete é uma sentença enquanto o `summary` continua
abrindo com `###`; e a proposta devolve **zero linhas para este run**, o que o
próprio roteiro declara como desfecho aceitável — a investigação não achou
evidência suficiente para propor, e o run vira cenário de leitura. **Isto
resolve a hipótese (f)**: a manchete deste run específico, novo, passa —
exatamente o que (f) previu antes de haver dado real para conferir. Nenhuma
screenshot existe ainda, e `EVIDENCIA.md` continua com todo campo em branco: a
prova de banco chegou antes da prova de tela, não depois — e as duas são
exigidas, não uma no lugar da outra.

**(i) A frase "não executado" no `CONFRONTO.md` está um passo atrás da
árvore.** A seção "A demo, e o que ela ainda deve" (`specs_v7/CONFRONTO.md:353-362`
na árvore atual) afirma que "quem escreveu os roteiros roda em worktree isolada e não
alcança cluster, banco nem Alertmanager" — verdade sobre a worktree de 23/08,
não mais sobre o estado do banco depois de `9f87ac6`. Não corrigido por esta
auditoria: aquele arquivo declara, na própria abertura, que é medido pelo
orquestrador e não copiado de relatório de quem implementou — a mesma regra
que já levou T079 a ficar como dele. Registrado aqui para que ele saiba
que a frase precisa de uma segunda passada quando fechar o confronto.

**(j) Uma chamada de ferramenta devolveu `400` do Prometheus por parâmetro
vazio — candidato a achado de produto, sem dono atribuído por esta
auditoria.** Em `evidence/E4-...txt`, `prometheus_metric_statistics` (a quarta
chamada do run de leitura) falhou com `invalid parameter "start": cannot parse
"" to a valid timestamp`. `search_knowledge_base` e `logs_for_resource`
falharam por ausência de configuração (base de conhecimento e fonte de log não
configuradas neste deployment) — desfecho de ambiente, coerente com o backlog
já registrado. A falha do Prometheus é diferente: parece um parâmetro de
início construído vazio em vez de omitido ou calculado, o que aponta para o
código que monta a chamada, não para configuração ausente. Não investigado
mais fundo por esta auditoria — julgar ambiente-versus-produto e nomear a
dona é o trabalho de T075, que é do orquestrador, com a demo inteira à vista.

---

## O que fica pendente, nomeado, não escondido

**Reescrita depois de o laço inteiro ter rodado de verdade em 24/08.** A
maior parte da tabela anterior (versão de mais cedo hoje) descrevia o laço
inteiro como não executado — isso deixou de ser verdade enquanto esta
auditoria trabalhava, e a tabela abaixo é a versão atual.

| Item | Estado | Dono |
|---|---|---|
| **O laço fechou uma vez, com um humano assistindo** — a pergunta que fecha a onda (§5 da última seção) | **SIM até a investigação e o auto-fechamento; NÃO até proposta/aprovação/execução, porque não há o que propor.** `E8/nothing-executed-unattended` não foi reconferido por consulta nova, mas por construção não pode ter mudado (nada foi aprovado) | ninguém — é o veredito, não uma pendência |
| **T049 — dois achados de produto bloqueiam a alegação normativa de E3** | Título não é frase (Achado 1); cabeçalho atribui nó errado (Achado 2). Reais, confirmados por screenshot nesta auditoria, sem dona atribuída | orquestrador |
| **T071/FR-024 — sem SQL literal para o run do laço inteiro** | O coletor nunca rodou contra `run=d393d5d0…`/`incident=inc_05328c58…`. Um comando fecharia isso — ver a lacuna nomeada na atualização acima | quem tiver acesso a staging (operador ou próxima sessão) |
| **T070/FR-023 — screenshots a 1280px, não 1920px** | Onze capturas reais, genuinamente full-page, largura errada. E2 sem screenshot dedicado | quem recapturar |
| **A rejeição** — Fase 8, e a candidata de ocorrência que a demo revelou | Não exercida; só as três capacidades de notificação jamais chegam a propor algo, então a "ocorrência diferente" de FR-019 precisa nascer de uma delas | orquestrador |
| **Os quatro achados de produto, sem dona** | Listados em `evidence/demo-2026-08-24/EVIDENCIA.md`; um começo de pista para 1 e 2 (`incident_store.py:148,188`), nada para 3 e 4. Atribuir dona e decidir o ciclo de reparo é do orquestrador | orquestrador |
| **O candidato da primeira passagem** (`prometheus_metric_statistics` → `400`) | Não se repetiu nesta investigação; continua aberto e sem dona | orquestrador |
| **T079 — seção por feature no confronto**, com o veredito de cada verifier | **NÃO FEITO, deliberadamente.** O cabeçalho do `CONFRONTO.md` declara que ele é medido pelo orquestrador e não copiado de relatório | orquestrador |
| **T001–T003 — a onda ainda não fechou** | Dito pelo próprio operador: merges pendentes, `make verify` com quatro vermelhos, o deploy da demo mais estreito do que a própria T003 manda (achado contra o preparo, com reparo prometido antes do fechamento) | orquestrador |
| **T089 — `make verify` completo** | **NÃO RODADO**, consequência direta do item acima | orquestrador |
| **A imprecisão de `pve01` em `laco-inteiro.md`** | `ssh root@192.168.68.159 'ssh pve01 "..."'` não resolve; o endereço real é `192.168.68.149`. Reparo de texto desta própria feature, nomeado e não corrigido nesta passagem | próxima passagem desta feature |
| **As três tarefas operacionais** — resolução de nomes, sincronização de segredo gerenciado, chave do gateway de modelos | **NÃO VERIFICADAS por leitura nova.** `backlog.md` carrega o estado mais recente conhecido — nenhuma resolvida | orquestrador |
| **A frase "não executado" em `specs_v7/CONFRONTO.md`** (seção "A demo, e o que ela ainda deve") | **Mais desatualizada ainda agora** — o laço inteiro rodou de verdade e fechou sozinho. Não corrigida por esta auditoria, mesma razão de T079 | orquestrador |
| **A coluna do confronto para features futuras** | as 17 linhas cobrem o que esta onda entregou; um mecanismo novo precisa de linha nova | próxima onda |

---

# O QUE O ORQUESTRADOR PRECISA MEDIR NO AMBIENTE REAL

Comando por comando. Esta é a seção que decide se o laço fechou.

## 0. O parâmetro que tudo mais depende

Toda consulta é escopada por organização. Sem este valor nada roda:

```sh
ssh root@192.168.68.159 "kubectl exec -i -n k3s-stg-ninjasre deploy/app -- sh -c 'psql -X -q -v ON_ERROR_STOP=1 \"\$NINJASRE_DATABASE_URL\"'" <<'SQL'
SELECT org_id, name FROM organisations;
SQL
```

Guarde como `<ORG_ID>`.

## 1. As consultas — todas, por um comando só

**Ver o SQL sem tocar em banco nenhum:**

```sh
uv run python -m tools.demo_evidence plan --org <ORG_ID> --run <RUN_ID> --incident <INCIDENT_ID>
```

**Executar e gravar a saída literal, um arquivo por estação:**

```sh
uv run python -m tools.demo_evidence collect \
  --org <ORG_ID> --run <RUN_ID> --incident <INCIDENT_ID> \
  --approval <APPROVAL_ID> --resource <RESOURCE_ID> \
  --out specs_v7/080-incidente-fecha-o-laco/evidence/consultas \
  --exec "ssh root@192.168.68.159 kubectl exec -i -n k3s-stg-ninjasre deploy/app -- sh -c 'psql -X -q -v ON_ERROR_STOP=1 \"\$NINJASRE_DATABASE_URL\"'"
```

`--exec` é dividido em argumentos por `shlex` e executado diretamente: nenhum
shell **desta** máquina o vê. O único shell envolvido é o `sh -c` de dentro do
pod, que resolve a variável com a string de conexão. O SQL viaja pela **entrada
padrão**, então não aparece numa listagem de processos, e nenhuma senha entra no
arquivo de evidência.

Sem `--approval` e sem `--resource`, as consultas que precisam deles saem
marcadas `NOT COLLECTED` nomeando qual faltou — **nada é perguntado ao banco**.
Isso é o esperado nas primeiras passagens.

**Rode duas vezes: antes da demo e depois.** A primeira é o vermelho — os
valores de partida — e sem ela a segunda não tem contraste.

### O que cada consulta responde, e o valor de partida

| Estação / consulta | O que decide | Partida |
|---|---|---|
| `E3/incident` | o incidente existe, é endereçável, e tem título em vez de id | detalhe irrecuperável |
| `E3/estate` | `count(*)` de `estate_resources` presentes | **0** |
| `E3/subject` | o recurso que o incidente aponta está no estate | nenhuma linha |
| `E4/turns` | `count(*)` de `run_turns` para o run | **0**, em 37 runs concluídos |
| `E4/tool-calls` | `count(*)` de `tool_calls` | **0** |
| `E4/evidence` | `count(*)` de `evidence` | **0** |
| `E4/trace-events` | `count(*)` de `trace_events` para o run | 73 no total da instância |
| `E4/cost-per-turn` | `usage` turno a turno; sem preço é **vazio**, não zero | nenhum turno |
| `E4/what-each-call-returned` | o que cada chamada devolveu, na ordem gravada | nenhuma linha |
| `E5/sentence-and-document` | a manchete **não** abre com sintaxe markdown e o documento ainda abre | todo `summary` recente começava com `###` |
| `E5/headline-coverage` | quantos runs são anteriores à coluna — **a leitura que explica as duas regras transversais** | todos |
| `E7/proposal` | exatamente uma proposta para o run, estado `pending` | nenhuma linha, para nenhum run |
| `E7/rollback-plan` | o desfazer gravado, e gravado antes | nenhuma linha |
| `E7/every-remediation-proposal` | quantas propostas de remediação o deployment já enfileirou | **0** |
| `E8/decision` | estado, decisor, instante e motivo | nenhuma linha |
| `E8/audit-of-the-decision` | a decisão na auditoria, com autor, ação, assunto e resultado | nenhuma linha |
| `E8/nothing-executed-unattended` | **tem de ser 0 no fim**: execuções sem decisão humana | 0 |
| `E9/outcome` | o desfecho para o recurso — falha nomeada também é desfecho | nenhuma linha |
| `E9/episode` | o episódio gravado para o run | nenhuma linha |
| `E10/timeline` | a entrada da ação na linha do tempo do incidente | nenhuma entrada de ação |
| `E10/incident-after` | o incidente carrega o desfecho, o run e a ação | parado no diagnóstico |
| `R/rejections` | a rejeição gravada com o motivo | nenhuma linha |
| `R/both-decisions-in-the-audit` | as duas decisões: `allowed` e `denied` | nenhuma linha |

## 2. O que procurar no log do processo

**A pergunta mais importante — este deployment sabe agir?**

```sh
ssh root@192.168.68.159 "kubectl logs -n k3s-stg-ninjasre deploy/app --since=24h | grep -E 'remediation\.(control_plane_bound|control_plane_skipped|desk_composed|desk_skipped)'"
```

Uma destas duas **sempre** aparece depois do boot:

- `remediation.control_plane_bound` (`integration`, `endpoints`, `trust`,
  `capabilities=13`) e então `remediation.desk_composed` (`capabilities`,
  `profile=kubernetes`) ⇒ **compôs**;
- `remediation.desk_skipped` com a lista `missing` ⇒ **não compôs**, e a lista
  diz qual peça falta. Anexe a lista; E7–E9 ficam **não exercidas**.

**A execução aconteceu?**

```sh
ssh root@192.168.68.159 "kubectl logs -n k3s-stg-ninjasre deploy/app --since=1h | grep -E 'remediation\.approval_(carried_out|not_carried_out)'"
```

Esta é a leitura que a tela **não** dá: a rota devolve sucesso mesmo quando a
execução falha (descoberta (c) acima).

**As ferramentas foram estreitadas pelas integrações configuradas?**

```sh
ssh root@192.168.68.159 "kubectl logs -n k3s-stg-ninjasre deploy/app --since=2h | grep -E 'tool_selection|integrations_unresolved|zero_integration'"
```

**Duas linhas que explicam um número que parece errado:**

```sh
ssh root@192.168.68.159 "kubectl logs -n k3s-stg-ninjasre deploy/app --since=2h | grep -E 'remediation\.(signals_unread|posture_unreadable)'"
```

- `remediation.signals_unread` ⇒ a obrigação de verificar foi gravada com os
  valores "antes" vazios. É a dormência declarada, não um defeito novo.
- `remediation.posture_unreadable` ⇒ a postura não pôde ser lida e foi tratada
  como a mais estrita. Silêncio nunca vira permissão.

**O gravador foi anexado?**

```sh
ssh root@192.168.68.159 "kubectl logs -n k3s-stg-ninjasre deploy/app --since=24h | grep -E 'integrations\.access_(composed|skipped)|investigation'"
```

## 3. As rotas a visitar, e o que se deve ver

O passo a passo com onde clicar está em `runbooks/navegador.md`. Em resumo:

| Rota | O que se deve ver |
|---|---|
| `/settings/models-providers` | provedor **Verified** |
| `/integrations` | Proxmox conectado; qualquer recusa por certificado traz **dois fingerprints**, nunca "no node answered" |
| `/resources` | recursos reais, com nome |
| `/incidents` | o incidente novo, com título que é frase |
| `/incidents/{endereço}` | URL sem `%3A`/`%40`/`%2B`; zero painéis "não foi possível preencher"; painel **"Proposed action"** |
| `/runs/{runId}` | **depois de recarregar**: transcript com N chamadas, custo por turno, nenhum controle de run vivo num run terminado, relato renderizado |
| `/decisions` aba **Actions** | a proposta real; se vazio, "Nothing is waiting on a decision" |
| `/agent` | as capacidades que este deployment pode usar |
| `/administration` aba **Audit** | `approval.decide` com `allowed` e com `denied` |

Redirecionamentos a conferir de passagem: `/investigations` → `/runs`, e
`/setup` → `/first-run`.

## 4. As três tarefas operacionais — verificar, nunca executar

```sh
# resolução de nomes, de dentro de CADA contêiner de monitoração
ssh root@192.168.68.159 'ssh <contêiner> "getent hosts stg-ninjasre.lan.kyo.ninja"'

# sincronização do segredo gerenciado
ssh root@192.168.68.159 'kubectl get infisicalsecret -A'

# chave do gateway de modelos: o provedor correspondente Verified em
# /settings/models-providers
```

Uma tarefa não concluída **não reprova a demo por si**. Ela marca **não
exercida** a estação que dependia dela, e o item continua no backlog novo. Se
estiver concluída, o item sai do backlog **com a evidência nomeada**.

## 5. A pergunta que fecha a onda

Ao fim, uma frase em `evidence/EVIDENCIA.md` §7, e ela só pode ser escrita
depois de todas as consultas acima:

> O laço fechou uma vez, com um humano assistindo, e as dez estações têm
> evidência anexada?

Se `E8/nothing-executed-unattended` não devolver `0`, a resposta é **não**,
qualquer que seja o resto.

---

## Resposta a esta pergunta, depois da demo de 24/08

**Não inteiramente — e o "não" tem uma forma específica, não um "quase".** As
seis primeiras estações fecharam de verdade: o alerta disparou sozinho, a
entrega chegou autenticada, o incidente abriu, a investigação gravou o que
fez com honestidade (inclusive dois `FAILED` verbatim), o relato é legível e
nomeia o nó certo, as ferramentas condisseram com o que está conectado. A
décima também fechou, por um caminho que ninguém tinha escrito: o incidente
refletiu o desfecho — resolvido, com a causa nomeada, sem o produto
reivindicar o que um humano fez à mão.

As três do meio — propor, aprovar, executar — não aconteceram, e a evidência
prova que a razão é do produto: o catálogo inteiro não tem uma única
capacidade que aja sobre infraestrutura. `E8/nothing-executed-unattended`
não foi reconferido por consulta nova nesta rodada, mas não pode ter deixado
de ser `0` — nada foi decidido para executar.

Isto não é o `SIM` sem qualificação que a pergunta original esperava, e
também não é o `NÃO` que "o laço não fecha" descreveria. É um terceiro
resultado que a spec já previa por escrito, na estação E7: "a investigação
conclui sem evidência suficiente para propor... e isso é correto." A
correção é mais severa aqui — não faltou evidência, faltou capacidade —, mas
a forma do desfecho é a mesma que a spec já nomeou como aceitável. Fechar a
onda com essa resposta, ou tratar "propor uma remediação de infraestrutura"
como trabalho ainda em aberto, é decisão do orquestrador.
