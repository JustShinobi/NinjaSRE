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
