# specs_v7 — Confronto

O que a onda de fato entregou, medido pelo orquestrador contra a árvore e
contra o staging real — não copiado do relatório de quem implementou.

Uma coluna nova nesta onda, exigida pela `REGRAS.md` §3: **quem constrói isso
em produção?** Uma peça que só um teste constrói não é entrega.

---

## S0 — 000-regras-e-governanca · **PASS** · 2026-08-23

Solo, na árvore compartilhada (não em worktree: a feature emenda
`.specify/memory/constitution.md` e o `CLAUDE.md` local, que não existem
dentro de uma worktree).

### Gates, rodados pelo orquestrador

| Gate | Comando | Resultado |
|---|---|---|
| Fronteira | `make verify` | **exit 0 — 12223 passed / 27 skipped** |
| Linha de base pré-feature | `make verify` na árvore intacta | exit 0 — 12210 passed / 27 skipped |
| Transversal, determinístico | `spec_validation browser --test console/tests/e2e/transversal-rules.spec.ts` | 35 passed / 17 skipped |
| Transversal, staging real | idem `--backing staging --evidence-dir <dir>` | exit 0 — 10 passed / 10 skipped |
| Evidência | mesmo run | 10 capturas full-page em `evidence/` |
| Credencial no log | comparação embutida do shell | ausente |

O delta de **+13** (12210 → 12223) reconcilia exatamente: 6 funções novas em
`test_console_e2e.py`, 4 em `test_spec_validation.py`, e 3 casos
parametrizados que o cenário `now-violations` gera sozinho em testes já
parametrizados sobre os nomes de cenário.

### O que foi entregue, e quem o constrói em produção

| Entrega | Quem constrói em produção |
|---|---|
| Constituição 2.0.0 → **2.2.0**: cláusula de paridade no artigo de capacidades, e artigo novo *composto ou não foi entregue* | Documento local. Governa Constitution Checks; não tem caminho de serving por natureza |
| ADR novo *composed or it is not shipped*, self-contained | Documento committed |
| ADR de paridade total → `Superseded`, **uma linha alterada** | Documento committed |
| Índice de ADRs e traceability do roadmap fechando ambos em 16, mesmo conjunto | Documentos committed |
| Cinco regras transversais novas (markdown cru, id como nome, dois placeholders, controle de run vivo, afirmação negativa) | `make verify` → `console_gate all` → suíte de navegador. Roda em toda fronteira de feature |
| Detectores puros, separados da varredura | `bans.test.ts`, coletado pelo runner de unidade do console, dentro do gate padrão |
| Backing **`staging`** na validação de navegador | Chamado pelo orquestrador no fim de cada slot. Não sobe nada; troca usuário+senha por token e captura evidência no mesmo run |

### O número que os slots seguintes precisam fazer cair

**10 entradas de allowlist.** Nove previstas pelo diagnóstico, e uma
descoberta durante o portão: o feed de atividade recente do dashboard lê o
`summary` bruto de cada run pelo mesmo mecanismo não filtrado que a lista de
runs e o detalhe do run já tinham entrada — o mesmo defeito, lido uma terceira
vez. Foi mantida como décima entrada em vez de o cenário ser maquiado para
escondê-la.

Cada entrada nomeia rota, regra, a substância do que a tela faz hoje, e o que
a remove dito como trabalho — nunca como número de feature.

### Os dois defeitos que a validação pegou depois do "pronto"

**1 — `--evidence-dir` não chegava em quem captura** (achado pelo
orquestrador). A flag chegava ao Playwright só como `--output=`, enquanto a
captura é feita por um `afterEach` que lê a variável de ambiente. Quem
chamasse pela opção documentada recebia **zero capturas com exit 0**, e o
`.last-run.json` depositado pelo `--output` fazia a pasta parecer preenchida.
É a forma de falha que a própria feature condena: seleciona zero e reporta
sucesso. Corrigido exportando a variável no ambiente do subprocesso e
removendo o `--output` inteiramente.

**2 — a feature violava, no código que entregava, a regra que ela escreve**
(achado pelo verifier). Cinco linhas de um teste committed citavam número de
tarefa e um papel do fluxo de trabalho — arquivo committed dependendo de
arquivo que não vai no clone. Reescritas em substância. Junto: o `controle.md`
citava um número ao lado de um comando que não o reproduzia (o número estava
certo; faltava um terceiro arquivo na citação).

### Dívida registrada

O aperto do detector de id composto — que removeu um falso positivo em leitura
de relógio — abriu um falso negativo estreito: um composto de segmentos todos
numéricos não é pego. Sem alcance no domínio hoje, e agora **travado por teste
permanente** que declara o furo como escolha e continua exigindo que um id
composto real seja acusado. Severidade baixa.

### Fora do escopo, deliberadamente

O passe editorial das onze linhas preexistentes do índice de ADRs, e os corpos
de registros já aceitos que citam número de artigo. Registro aceito é imutável.

### Achado de governança — decisão do operador, em aberto

`.specify/memory/constitution.md` **está rastreada e commitada**, contra a
regra da casa que a declara local-only. O histórico: um commit a estabeleceu,
um segundo a destrackeou deliberadamente, e um terceiro — o mesmo commit largo
que esta onda já responsabiliza por sobrescrever governança com estado velho
de arquivos alheios — a reintroduziu sem menção. O padrão de exclusão existe,
mas exclusão não destrackeia arquivo já rastreado.

Não corrigido: muda o conjunto de arquivos rastreados, e é decisão do
operador. É também o segundo dano documentado do mesmo commit, o que reforça
a regra de merge desta onda — um hunk que reverte conteúdo em arquivo fora do
escopo declarado é sinal de árvore defasada, nunca algo a mergear.

### Lições de execução

O implementer bateu o teto de turnos **três vezes** nesta feature. A estratégia
de modelo da onda presume tarefas mecânicas com `file:line`; as desta feature
não eram — auditar artigos exemplo por exemplo, capturar cinco vermelhos
reais e implementar um backing novo é julgamento. Para features dessa forma,
fatiar o dispatch por fase em vez de por feature.

Duas armadilhas operacionais que custaram tempo e vão custar de novo:
escrever o log do run **dentro** do diretório de evidência invalida o
resultado, porque a ferramenta limpa o diretório; e conferir vazamento de
segredo com um `grep` que recebe o segredo como argumento sempre dá falso
positivo, porque o próprio `grep` nasce com ele em `argv`.

---

## S1 — 001-registro-do-que-o-agente-fez ∥ 020-identidade-enderecavel · 2026-08-23

Primeiro slot paralelo: duas worktrees isoladas, propriedade disjunta
declarada, merge e regeneração de artefatos pelo orquestrador.

### Gates, na árvore mergeada

| Gate | Resultado |
|---|---|
| `make verify` | **exit 0 — 12278 passed / 27 skipped** |
| Transversal, determinística | 37 passed / 15 skipped |
| Acceptance da 020 | 15 / 15 |
| Transversal, **staging real** | exit 0 — 12 passed / 8 skipped, 12 capturas |
| Deploy | `app` + `web`, Argo `Synced/Healthy` |

### O número da onda: allowlist 10 → 8

Caíram duas, ambas de `/incidents/{id}`: **identificador como nome** e
**afirmação negativa**. A terceira daquela mesma rota — dois placeholders —
continua vermelha, porque depende de uma leitura de painel que falha e não do
formato do identificador.

Essa assimetria é a prova de que o cenário violador não foi enfraquecido. Se as
três tivessem saído juntas, o dataset teria sido maquiado em vez de o produto
ter sido consertado.

A 001 **não** derrubou nenhuma, e isso está correto: as entradas descrevem o que
a tela imprime; ela é backend e apenas produz `headline` e `report`. Quem
consome é a feature de leitura do relato. O orquestrador havia atribuído cinco
entradas a ela; o implementer mediu, discordou com evidência, e estava certo.

### A tese da onda, provada no ambiente real

A linha de base era `run_turns=0`, `tool_calls=0`, `evidence=0` com 37
investigações concluídas — tabelas que existiam e eram decorativas.

Lido do banco de staging depois do deploy: **5 turnos, 4 chamadas de
ferramenta, 1 evidência**, de um único run. O processo subiu às 21:03:41Z e os
turnos foram gravados entre 21:23:23Z e 21:23:39Z — vinte minutos depois,
portanto pelo código deste slot.

A investigação não foi disparada para a prova: veio de um alerta real pelo
caminho de produção. É a única forma de evidência que o artigo novo da
constituição aceita — o harness prova a peça, nunca a composição.

O mesmo run mostra a segunda entrega: `headline` é uma sentença sem marcação
sobre drills de restore em três VMs; `summary` continua começando com `###`. A
separação entre a sentença e o documento existe no deployment, não só no
harness.

### Quem constrói isso em produção?

| Entrega | Quem constrói em produção |
|---|---|
| Gravador de trace | `investigator_of` (`gateway/http/asgi.py`), ponto único, chamado pelo boot e pela recomposição. Desligar o fio reprova quatro testes de arquitetura |
| Um só escritor de recibo de alerta | O segundo caminho foi deletado; um teste caminha a AST e reprova um segundo call site |
| Manchete no fechamento | `gateway/http/orchestration.py`, no `finally` que cobre concluído, cancelado e falho |
| Endereço público do incidente | Derivado ao abrir o incidente; backfill por migração — **zero endereços vazios** no banco de staging |
| Decodificação única na borda | `console/src/shell/route-params.ts`, nas quatro rotas dinâmicas reais |

### Quatro recursos compartilhados que o protocolo do slot não previa

O `EXECUCAO.md` nomeia três arquivos de escrita única e resolve os artefatos
gerados por regeneração. O S1 provou que a lista está incompleta:

1. **Números de revisão de migração.** As duas features criaram migrações com o
   mesmo número, ambas descendendo do mesmo pai — histórico ramificado, duas
   cabeças, nada conseguia migrar, e o boot do ambiente falhava. Um número de
   revisão é recurso de escrita única tanto quanto um arquivo de traduções.
2. **O modelo de persistência**, que guarda o modelo de toda tabela: qualquer
   par de features que acrescente coluna colide ali.
3. **Os cenários de fixture.** Deu disjunto por coincidência de domínio — uma
   mexeu nos arquivos de run, a outra nos de incidente —, não por desenho.
4. **A própria suíte transversal**: as duas precisam editá-la, porque cada uma
   derruba as próprias entradas de allowlist. Automergeia, e sai desformatada.

A regra que faltava, e que vale do S2 em diante: **todo arquivo ou recurso que
ambos os lados podem editar precisa de um passo de reconciliação declarado no
merge** — dono, regeneração, renumeração ou formatação. Nenhum dos quatro tinha.

### Defeitos que só a árvore mergeada revelou

Cinco falhas no primeiro `make verify` pós-merge, nenhuma visível de dentro de
uma worktree: duas eram as próprias worktrees ainda no disco, sendo varridas
como um segundo deployment fictício; uma era a ramificação das migrações; uma
era um teste de identidade estrutural que precisava aprender que o endereço é
derivado do identificador — dois incidentes que podem ter identificadores
distintos podem ter endereços distintos, e endereço compartilhado é que seria o
defeito; e uma era um dataset editado à mão em vez de gerado.

### Defeitos de infraestrutura encontrados por usá-la

- **O script de deploy estava sem bit de execução**, no disco e no índice, com
  os dois irmãos tendo o seu. O alvo de deploy estava quebrado para qualquer
  clone e ninguém sabia, porque ninguém o havia rodado.
- **O diretório de evidência relativo apontava para o lugar errado.** O
  navegador roda com o pacote do console como diretório de trabalho, então um
  caminho relativo à raiz caía um nível abaixo — sem erro, porque gravar uma
  captura em algum lugar não falha. O chamador lia um diretório vazio e concluía
  que nada fora capturado. Terceira vez nesta onda que a mesma família de
  defeito aparece: silêncio com aparência de sucesso.

### A lacuna do ciclo de staging

`Synced + Healthy` significa "o cluster é o que o Git pediu", **não** "a
aplicação respondeu". A aceitação rodou quatro minutos após o deploy, pegou o
console frio — 37,7s no primeiro acesso, timeout de 30s — e produziu uma página
cujos links apareciam vazios. Custou uma investigação camada por camada até o
banco para concluir que estava tudo certo e a página estava fria; refeita,
passou.

O ciclo precisa de um passo de aquecimento entre o Argo e a aceitação.

### Evidência de ambiente real não é tarefa da feature

Os implementers rodam em worktree, que não alcança cluster nem banco. Cobrar
deles contagem no Postgres é cobrar o impossível — e foi por isso que as
tarefas de evidência das duas features ficaram desmarcadas até o orquestrador
colhê-las. Do S2 em diante, essa etapa é declaradamente do orquestrador, no fim
do slot.

### Custo de execução

Onze retomadas por teto de turnos entre as três features da onda até aqui, e
quatro ciclos de reparo. A feature que commitava por fase transformava cada teto
num recado de retomada; a que acumulava vinte arquivos transformava cada teto em
risco de perda total. **Commit por fase passa a ser condição de entrada no
dispatch**, não lembrete depois do fato.

### O achado que muda a validação de staging da onda inteira

O verificador da identidade endereçável notou que três capturas de staging
mostravam a **lista**, não a página de detalhe que deveriam mostrar. A causa:
todo leitor desta suíte **conta** em vez de afirmar, e uma contagem não tem
espera automática. Contra um plano simulado que responde instantaneamente, a
tela de detalhe já está lá quando o clique retorna; contra um deployment real,
não está — então as regras mediam a lista de onde vieram e não achavam nada de
que reclamar. **Duas regras reportaram sucesso tendo medido nada.** Quarta vez
nesta onda que a mesma família aparece: silêncio com aparência de sucesso.

Corrigido: o auxiliar de navegação agora espera a rota mudar e o cabeçalho da
página aparecer antes de qualquer leitura.

Com o conserto, duas regras passaram a **falhar** contra o staging — e a falha é
verdadeira. Investigando:

- o banco tem endereço público em todo incidente, **zero vazios**;
- a API devolve o campo;
- o console implantado **contém** o campo no seu próprio pacote compilado;
- e a lista de incidentes desenha **dezenove links todos vazios**.

Carregar `/incidents` e `/runs` no staging produz **zero requisições** a
`/v1/incidents` e `/v1/runs` — o serviço registra as suas requisições, e não há
nenhuma. As duas listas são servidas inteiras do cache de rota do Next, sem
tocar a API.

Este é exatamente o defeito que o diagnóstico da onda registrou como evidência
de partida e atribuiu à feature de fonte-por-fato: *listas dinâmicas, fim do
cache de rota congelado*. **Não é regressão deste slot** — é um defeito
pré-existente que só ficou visível porque o campo novo aparece vazio na página
velha.

A consequência é de planejamento, não de código: **enquanto o console servir
listas congeladas, nenhuma tela de lista pode ser validada contra o staging.**
O que foi medido lá até agora, nas telas de lista, foi uma página que não
consultou o produto. Isso alcança o checkpoint do laço mínimo declarado para o
fim do slot seguinte, que exige um alerta real virando investigação legível no
ambiente real — com listas congeladas, esse checkpoint não tem como passar.

---

# Quem constrói isso em produção? — a coluna da onda

> **Como esta tabela foi preenchida.** Cada `file:line` foi obtido **lendo o
> código da árvore mergeada**, nesta sessão, e não copiado dos `controle.md`.
> Isso não é zelo: três `file:line` que os controles das features 040 e 070
> declararam já estavam **defasados** quando esta tabela foi escrita —
> `compose_remediation` migrou de `lifespan.py:92` (declarado pela 040) para
> `:98` e depois para `:105`, e `compose_control_plane` de `:98` (declarado
> pela 070) para `:100`, porque cada merge do slot seguinte empurrou as linhas.
> Um `file:line` copiado de um relatório envelhece; um lido, não.
>
> **Uma célula que aponta um teste é pior que uma célula vazia**, porque parece
> resposta. Um mecanismo cuja única construção é de teste aparece aqui
> declarado **dormente**, com a referência do que o ligaria.

| Mecanismo | Onda | Quem o constrói no caminho de serving |
|---|---|---|
| **Gravador de trace da investigação** | 001 | `gateway/http/asgi.py:172` `investigator_of`, que chama `runner.attach_recording(...)` em `asgi.py:211`. Ponto **único**: os dois chamadores são as duas roots reais — `gateway/http/asgi.py:240` (boot, dentro de `build_deployment`) e `gateway/http/runtime.py:64` (`recompose_investigator`, chamado de `gateway/http/lifespan.py:81` quando a configuração muda) |
| **Manchete extraída no fechamento real** | 001 | `gateway/http/orchestration.py:128` `headline_for(...)`, dentro do `finally` que abre em `:124` — cobre concluído, cancelado e falho; o valor é gravado em `:139` |
| **Endereço público do incidente** | 020 | `platform/incidents/lifecycle.py:105` — `public_id=public_incident_id(new_incident_id)`, derivado no instante em que o incidente abre |
| **Decodificação única na borda** | 020 | `console/src/shell/route-params.ts:26` `routeParam`, aplicada nas rotas dinâmicas reais do console |
| **Prontidão do provedor, uma fonte só** | 030 | `platform/startup/checklist.py:254` `readiness_of(*, configured, checked)` — a **mesma** função que `gateway/http/routes/providers.py:293` usa para montar a linha da listagem. Uma função, dois consumidores; não duas implementações que combinaram de concordar |
| **Chave do modelo vinda do cofre, não do ambiente** | 030 | `gateway/http/provider_credentials.py` `compose_provider_credentials`, chamado em `gateway/http/lifespan.py:74`. Substitui o `EnvironmentCredentialResolver` que `core.llm` traz por padrão; o ambiente continua embaixo, como segunda escolha |
| **Renderizador do relato** | 010 | `console/src/surfaces/report.tsx`, montado por `console/src/surfaces/screens/run-detail.tsx:226` e reaproveitado por `console/src/surfaces/integration-panel.tsx:591` |
| **Balcão de remediação** | 040 | `gateway/http/remediation.py:172` `compose_remediation`, chamado em **`gateway/http/lifespan.py:105`** — depois do acesso a integrações, das credenciais de provedor, da recomposição do runner e do plano de controle |
| **Portão de remediação, por investigação** | 040 | `gateway/http/remediation.py:130` `RemediationGate(...)` dentro de `RemediationDesk.gate_for`; registrado no laço em **`gateway/runtime/investigator.py:375`** (`.register(hooks)`). O balcão chega ao runner por `gateway/http/remediation.py:248` (`attach_remediation`) |
| **Portão de autonomia, na hora da decisão** | 040 | `gateway/http/remediation.py:287` `service.gate(policies)` → `:241` (`autonomy_of=`) → `:137` (`resolve_autonomy=`). Resolvido **no instante em que uma escrita é decidida**, não no boot — um portão construído no boot carregaria a postura de quando o processo subiu |
| **Resolvedor de integrações do time** | 040 | `gateway/runtime/investigator.py:419` — `TeamCatalogueResolver(self.registry).for_availability(...)`, na seleção de ferramentas de cada run |
| **Vínculo do plano de controle** | 070 | `gateway/http/control_plane.py:64` `compose_control_plane`, chamado em **`gateway/http/lifespan.py:100`** — **antes** de `compose_remediation` (`:105`), porque o balcão pergunta se existe um plano antes de compor. O vínculo em si é `gateway/http/control_plane.py:116` `control_plane.bind(bound)` |
| **Confiança de certificado até o egress do proxy** | 070 | Um `TrustRegistry` construído em `gateway/proxy/composition.py:45` e entregue ao remetente (`:49`) **e** ao motor (`:52`) — um só, porque dois registros seriam duas respostas. A leitura da configuração é `gateway/proxy/hosts.py:98` `trust_from_configuration` e `:138` `refresh_configured_trust`, aplicadas no arranque e no ciclo por `gateway/proxy/__main__.py:66` `_configured_egress` (chamado em `:142` e `:193`) |
| **A pinagem, no instante antes do primeiro byte** | 070 | `gateway/proxy/sender.py:172` `_PinCheckingConnection`, com a verificação dentro de `connect()` em `:182`. É o último instante antes de `request()` escrever — uma checagem em volta da resposta já teria mandado a credencial para quem atendeu. O único construtor de contexto que pode não verificar é `gateway/proxy/sender.py:124` `context_for_trust`, e isso está travado por `tests/architecture/test_one_place_can_stop_verifying.py` |
| **Primeiro administrador** | 050 | `platform/identity/enrolment.py` `enrol_local_administrator`, com **dois** chamadores de produção: `surfaces/cli/commands/setup.py:306` `admin` (o comando canônico) e `platform/startup/bootstrap.py:357`, dentro de `establish_durable_credential` (`:315`) — a troca da credencial de bootstrap |
| **Orientação de campo do catálogo** | 060 | `gateway/http/routes/integrations.py:494` — `where_to_get_it=entry.profile.where_to_get_it` na view do catálogo; a documentação de cada pacote é servida por `GET /{name}/docs` (`:429`) |
| **Coletor de evidência da demo** | 080 | **Não é mecanismo de produto e não tem composition root**: é ferramenta de repositório (`tools/demo_evidence/`), invocada por uma pessoa, e nenhum tier a importa |

## Declarados dormentes — e o que os ligaria

| Mecanismo | Estado | O que o ligaria |
|---|---|---|
| **Pipeline por estágios** (`build_pipeline`) | **DORMENTE.** Nenhum chamador de serving | `core/pipeline/build.py:70` declara isso de si mesmo e **nomeia o chamador real que existe**: o harness que roda o corpus de cenários (`:90`). O caminho de serving constrói o laço diretamente. Ligá-lo é dar ao harness a opção de dirigir o investigador de serving, ou dar ao serving a opção de usar o pipeline — trabalho com dono fora desta onda |
| **`DecisionWaiter`** (espera de decisão dentro do laço) | **DORMENTE, por decisão do plano.** O portão compõe com `waiter=None`, e executar é sempre uma segunda entrada | Implementar o esperador. Está dito no módulo, não escondido. Enquanto não existir, a aprovação é o que ela deveria ser de qualquer forma: uma pessoa, numa segunda requisição |
| **Leitura de sinal na hora da execução** | **DORMENTE, com a razão medida.** `gateway/http/remediation.py:322` `_UnreadSignals` declara não ler nada e registra `remediation.signals_unread` por ação | Uma fonte de métricas viva. O gravador de obrigações pede a leitura de dentro da própria unidade de trabalho, então uma implementação sobre o `PersistenceGateway` reentra numa transação já aberta — contra a persistência em memória isso é *deadlock*, medido |

## Backlog anterior → destino, item por item

Nenhum item sem destino. Cada linha diz o que fecha o item, ou por que ele
continua no arquivo novo. **Onde a evidência é de ambiente, ela é do
orquestrador e está marcada como tal** — quem escreveu esta tabela não alcança
cluster nem banco.

| Item do backlog anterior | Destino | Evidência |
|---|---|---|
| **A deployment should produce its own first administrator** | **Fechado** — 050 | `surfaces/cli/commands/setup.py:306` `admin`; `platform/identity/enrolment.py::enrol_local_administrator` com dois chamadores de produção; o convite do boot nomeia o comando |
| **A deployment cannot hold two service accounts** | **Fechado** — 050 | `platform/persistence/postgres/models.py:173` — `email_folded: Mapped[str \| None]`, e o comentário em `:160-165` explica por que o índice único ordinário basta: o PostgreSQL nunca trata dois `NULL` como colisão |
| **The screen has room the packages have not filled** | **Fechado** — 060 | Medido nesta sessão: `uv run python -m tools.verify_integrations` → **"15 integration(s) at full parity, every permission probed"** |
| **Four seams between what is configured and what runs** | **Três fechados, um declarado dormente** — 040 e 030 | (1) estreitamento por integrações configuradas e (2) `TeamCatalogueResolver` instanciado: `gateway/runtime/investigator.py:419`; (3) pipeline: **declarado dormente** nomeando o harness (`core/pipeline/build.py:70,90`), que é o que a regra nova aceita como resposta; (4) chave do modelo: **fechada** por `compose_provider_credentials` em `gateway/http/lifespan.py:74` |
| **A vendor with a self-signed certificate cannot be connected** | **Fechado** — 070 | O vocabulário desceu para o tier do proxy (`platform/credentials/proxy/trust.py`), a aplicação está no egress (`gateway/proxy/sender.py:182`), e a recusa tem três frases distintas com o fingerprint observado |
| **The alert router had no way to reach this deployment, twice over** | **Metade de produto fechada; a metade operacional continua** | A parte de produto — o webhook e o intake — está de pé. Os contêineres de monitoração apontando para um resolvedor morto **não são código deste repositório**: continuam no backlog novo, e a evidência de fechamento é do orquestrador |
| **Two seams the deep verify opened rather than closed** | **Um fechado, um continua** | Fechado: a recusa de credencial em HTTP claro ganhou frase própria (`CredentialWouldCrossInClear`, 060). **Continua, e foi medido nesta sessão**: `gateway/http/integration_access.py:64` liga `team_id=CREDENTIAL_ORG_WIDE_TEAM` para as ferramentas, e `gateway/http/routes/integrations.py:650` passa `_team_of(auth)` para a verificação profunda — os dois lados ainda resolvem diferente |
| **An investigation that ran leaves the run detail empty** | **Fechado** — 001 e 010 | O gravador é anexado em `gateway/http/asgi.py:211` por `investigator_of`; provado no ambiente real (5 turnos, 4 chamadas, 1 evidência, vinte minutos depois do deploy) |
| **The half of the product that acts is not composed** | **Fechado** — 040 e 070 | `gateway/http/lifespan.py:100` e `:105`: o plano de controle é vinculado e o balcão compõe. Uma das duas linhas — `remediation.desk_composed` ou `remediation.desk_skipped` com a lista `missing` — sempre aparece depois do boot |
| **The Infisical operator in the cluster cannot authenticate** | **Operacional, fora deste repositório** | Continua no backlog novo. Evidência de fechamento é do orquestrador |
| **The model gateway needs a key that exists nowhere** | **Operacional, fora deste repositório** | Continua no backlog novo. Evidência de fechamento é do orquestrador |

## A demo, e o que ela ainda deve

O roteiro de leitura, o roteiro do laço inteiro, o gabarito de evidência e o
coletor estão em `specs_v7/080-incidente-fecha-o-laco/`. A evidência
consolidada vive em
`specs_v7/080-incidente-fecha-o-laco/evidence/EVIDENCIA.md`.

**Veredito quando esta seção foi escrita: não executado.** Todo campo do
gabarito estava em branco, e era o estado honesto: quem escreveu os roteiros
roda em worktree isolada e não alcança cluster, banco nem Alertmanager. O
gabarito aterrissou **antes** da execução, que é a única ordem em que ele prova
alguma coisa.

> **Isto foi superado.** A demo rodou em 2026-08-24 contra o hipervisor real,
> e o registro está em "A demo, executada", mais abaixo neste arquivo, com a
> evidência em `evidence/demo-2026-08-24/`. O parágrafo acima fica como estava
> porque apagá-lo esconderia a ordem em que as coisas aconteceram — o gabarito
> antes da execução —, que é o que lhe dá valor. Um documento que se reescreve
> para parecer que sempre soube não serve para confrontar coisa nenhuma.

---

## S2 a S5 — as sete features restantes · 2026-08-24

Escrito depois do fato, e a demora é ela mesma um achado: este arquivo parou no
S1 enquanto a onda avançava até o fim, e uma auditoria independente teve de
usar os `controle.md`, o `tasks.md` e o código como fonte porque os dois
documentos "de verdade" da onda estavam desatualizados. Um confronto escrito
tarde é melhor que nenhum e pior que um escrito no fechamento de cada slot.

### O placar

| | início | fim |
|---|---|---|
| Entradas de allowlist transversal | 10 | **0** |
| Integrações em paridade total | 15 declaradas, 28 e 29 campos vazios | **15/15, campos completos** |
| `run_turns` / `tool_calls` / `evidence` | 0 / 0 / 0, com 37 investigações | **gravando** |
| Cabeças de migração | 1 | 1, agora com 19 revisões |

### O que cada feature provou

| Feature | O que fechou | Quem constrói em produção |
|---|---|---|
| Leitura do relato | Manchete é sentença, documento é documento, transcript e custo reais | O console consome `headline`/`report`; o renderizador é um só, sanitizado |
| Identidade endereçável | Endereço curto e opaco, decodificado uma vez na borda | Derivado ao abrir o incidente; backfill por migração |
| Uma fonte por fato | Prontidão do provedor lida do ledger de verificação; causa de vazio por tela | A listagem e o checklist calculam pela mesma função — não podem discordar |
| Decisão composta | Os dois portões construídos na composition root | `RemediationDesk.gate_for`, com dois chamadores reais |
| Primeiro administrador | Caminhos de credencial de 0 para 3 sem ler código-fonte | `ninjasre setup admin`, e a troca da credencial de boot |
| Catálogo | `min_scope` 21/21 secretos, `guide_url` 40/40, docs servido por rota | O gate reprova campo sem guia, nomeando vendor e campo |
| Confiança de certificado | Fingerprint pinado até o egress; três mensagens distintas; formulário com portão de permissão | Recusa dentro do `connect()`, antes de um byte — não é hook, então não falha aberta |
| Incidente fecha o laço | Coletor de 23 consultas e três runbooks | Instrumento, não afirmação: a demo é executada, não descrita |

### O laço, medido no ambiente real

O coletor rodou contra o banco de staging: **23 consultas, zero falhas**.

- **Lê**: a investigação grava — `run_turns = 5` onde a linha de base da onda
  era zero em 37 investigações concluídas. A manchete é uma sentença limpa
  onde todo resumo recente abria com `###`.
- **Age**: as estações de proposta e de execução devolvem **zero linhas**. Não
  é defeito e está gravado como o "antes" correto: a metade que age só se
  exercita quando um alerta pede ação ou quando alguém roda a demo.

### O defeito que um sinal verde escondia

O deployment esteve em `CrashLoopBackOff` por treze reinícios enquanto o Argo
reportava `Synced/Healthy` — porque `Synced` diz que o cluster é o que o Git
pediu, não que a aplicação subiu. O pod anterior ao merge continuava servindo,
então tudo parecia bem.

A causa: uma migração escreve `NULL` numa coluna que ainda é `NOT NULL`, com o
`alter` **depois** do `update` em vez de antes. Só falha onde existe ao menos
uma linha com o valor vazio — o banco real tem exatamente uma, e o banco de
teste não tinha nenhuma. O erro no log é o destravamento seguinte, não a causa.

**Três medições desta onda mediram o alvo errado**: o log de um pod que não era
o certo, um `tee` que mascarou o código de saída de um gate, e o `Synced` acima.
As três produziram um número verde sobre a coisa errada. A pergunta que passa a
ser obrigatória antes de registrar qualquer medição: **de qual processo veio
este número?**

### O que fica aberto, nomeado

- **A demo não foi executada.** Runbooks, coletor e gabarito estão de pé; as
  estações de ação esperam a execução com um humano no meio.
- Baselines visuais das telas reformadas: recapturar e aceitar é revisão
  humana.
- Prova contra um stack de compose real, para o primeiro administrador.
- O seam de credencial de time segue aberto: as ferramentas resolvem org-wide
  enquanto a verificação profunda já recebe o time do chamador.
- Um envelope de erro que os couriers antigos não leem — o servidor responde
  `{"error":{"message":…}}` e eles procuram `detail`, então mostram refusal sem
  a frase.

### Quem constrói isso em produção?

A coluna que a auditoria de regras exigiu, respondida por feature na tabela
acima. Onde a resposta honesta era "ninguém ainda", ela foi escrita assim: o
pipeline por estágios declara-se dormente **nomeando o que o ligaria**, em vez
de fingir que está composto.

---

## A demo, executada · 2026-08-24

A 080 não era mais uma feature: era a pergunta se as outras nove somam alguma
coisa. Foi respondida contra o hipervisor real, com um contêiner de verdade
parado por dezoito minutos.

### O laço, do gatilho ao fecho

Contêiner CT122 (`redis`, nó `pve01`) parado às **10:26:29Z** e religado às
**10:44:47Z**. Nada foi emitido à mão depois disso; cada passo aconteceu porque
o anterior aconteceu.

| | | UTC |
|---|---|---|
| E1 | o alerta dispara sozinho | 10:29:34 |
| E2 | a entrega chega, autenticada, `202` | 10:29:45 |
| E3 | incidente `inc_05328c58ca88676b` abre | 10:29:45 |
| E4 | a investigação grava 13 eventos | 10:29:45 |
| E5 | conclui em 23s, manchete legível | 10:30:08 |
| E10 | o incidente fecha sozinho | 10:50:06 |

**Nove das dez features aparecem nessa tabela.** A identidade endereçável da
020 é o `inc_…` sem percent-encoding. A gravação da 001 são os 13 eventos e a
repartição de custo por turno. O relato legível da 010 é a manchete que é uma
frase. A fonte-por-fato da 030 é o `501` do hipervisor mostrado verbatim em vez
de virar prosa. A confiança de certificado da 070 é o que faz a chamada chegar
ao hipervisor autoassinado. O catálogo da 060 é o painel que ofereceu
OpenObserve e SigNoz por tê-los achado nos recursos descobertos.

### O que o produto se recusou a fingir

Três recusas, e cada uma vale mais que um sucesso:

- `changes_in_window` respondeu que *"whether anything changed before this
  incident is **unknown rather than answered**"* — não inventou um "nada mudou";
- `proxmox_guest_tasks` mostrou o `501 Method not implemented` do hipervisor
  literal, sem traduzir para uma falha genérica;
- o incidente fechou com `close_reason: "ProxmoxGuestStopped was resolved
  upstream"` e `self_resolved: true`. **O produto não reivindicou o conserto.**
  Quem religou foi um humano, e o registro diz isso.

### Onde o laço para, e por quê

E7, E8 e E9 — propor, aprovar, executar — não correram. A razão não é ambiente
nem tela.

O catálogo inteiro tem **três** capacidades de escrita:
`alertmanager/acknowledge_incident`, `pushover/post_message`,
`telegram/post_message`. As três são aviso. **Nada, em lugar nenhum do
catálogo, atua sobre infraestrutura.** As vinte capacidades do Proxmox são de
leitura; até `proxmox_guest_start_diagnosis` diagnostica uma partida que
falhou, não a executa.

A maquinaria em volta está pronta e provada: o balcão compôs 20 capacidades, o
portão se registra por run em `pre_tool_use`, o teto de ferramentas é 40 e só 4
foram usadas — nada foi cortado por orçamento.

**O agente estava certo em não propor nada.** O laço fecha até *"entendi,
gravei e registrei o desfecho"*. Não fecha em *"agi"*, porque o vocabulário de
ação está vazio. Isso é escopo de produto por decidir, não defeito por
consertar, e é a coisa mais importante que esta onda descobriu sobre si mesma.

### Achados de produto, sem dono ainda

1. **O título do incidente é o nome do alerta**, `ProxmoxGuestStopped`, não uma
   frase — e o próprio produto produz a frase certa na tela seguinte.
2. **O cabeçalho do incidente diz `node pve02`; os rótulos na mesma tela dizem
   `node=pve01`.** O cabeçalho lê `instance` — o endereço de quem raspou a
   métrica — e o apresenta como o nó do sujeito. Um operador vai ao nó errado
   com o dado certo três linhas abaixo.
3. **A descoberta não resolve o nó do convidado**: todo `native_id` sai como
   `lxc/HAL9000/unknown/122`, embora o exportador carregue `node=pve01`.
   Provável causa do item 2.
4. **O custo aparece de duas formas para o mesmo run**: `Not recorded` no
   painel do incidente, `$0.00` repartido por turno na tela do run.
5. **`prometheus_metric_statistics` devolve 400** com `start` vazio — visto
   antes, não reincidiu na demo.

### Um erro meu, registrado como erro

Antes de parar o contêiner procurei uma regra que o vigiasse. Não achei nenhuma
sobre `pve_up` de convidado e concluí que *nada* o vigiava — escrevi uma regra
para preencher a lacuna.

Quatro regras já o cobriam pelo lado do serviço e **as quatro dispararam antes
da minha**. O alerta teria chegado sem eu escrever linha alguma.

A regra continua correta, e foi verificada silenciosa contra as séries vivas
antes de carregar. Mas eu afirmei mais do que havia medido: *"nenhuma regra
sobre a métrica do convidado"* era um achado; *"nada vigia este contêiner"* era
palpite com roupa de achado. É a mesma família de defeito que esta onda passou
a semana fechando nas telas, cometida no relatório de quem a conduzia.
