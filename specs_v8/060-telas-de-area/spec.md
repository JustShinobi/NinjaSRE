# Feature Specification: Telas de área — Incidentes, Recursos, Conhecimento e O agente viram o board

**Feature Branch**: `feat/v8-060-telas-de-area`

**Created**: 2026-08-27

**Status**: Draft

**Input**: User description: "As quatro telas de área conforme seus artboards:
timeline por assunto no incidente expandido, nunca id cru como subtítulo;
barra de saúde segmentada + agrupamento por nó + síntese dos unhealthy;
episódios com filtros por componente agrupado; pipeline metrô e cards-resumo.
O board é o contrato — desvio não registrado é defeito."

**Referência visual (DoD)**: quatro artboards normativos, um por tela —
`design/padrao-2026-08/Incidents.dc.html`,
`design/padrao-2026-08/Resources.dc.html`,
`design/padrao-2026-08/Knowledge.dc.html`,
`design/padrao-2026-08/TheAgent.dc.html` — sobre a fundação visual da 000
(tokens, ícones, chips com contorno, formas de status, shell). O que o
artboard desenha com dado de exemplo, a tela desenha com o dado real da mesma
FORMA; diferença de dado é aceitável, diferença de desenho não (README da
onda, decisão 1). O acceptance é por tela, red-first, e o fechamento do slot
inclui o gate visual de `specs_v8/EXECUCAO.md` §3 nos dois temas.

**Viewport normativo de medição**: 1920×1080 (os artboards são 1440 de
largura; o layout é fluido a partir da fundação da 000).

**Evidência**: auditoria de uso real no staging em 2026-08-27 (README da
onda, "Evidências de partida") — ids crus como subtítulo, N linhas idênticas
no incidente expandido, tabela chapada em Recursos, filtro de Conhecimento
com componentes duplicados, prosa longa em O agente.

---

## Fatos verificados em 2026-08-27 (não re-derivar)

Cada item está cravado em código desta árvore ou foi visto no staging pela
UI. A spec os trata como fatos.

1. **O agrupamento por assunto já existe e já carrega tudo que a linha
   expandida precisa.** `groupBySubject`
   (`console/src/surfaces/incident-groups.ts:118`) devolve `IncidentGroup`
   com `key` (correlation key), `title`, `subjects`, `detector`, `count`,
   `severity` (a pior), `state` (do disparo vivo mais novo), `live`,
   `lastAt`, `firstAt` e `occurrences` — e cada `IncidentOccurrence` (`:28`)
   carrega `incident_id`, `public_id`, `summary`, `state`, `severity`,
   `opened_at` (ISO 8601) e `run_id`. A mini-linha-do-tempo de disparos e o
   link para a investigação **não precisam de endpoint novo**: são
   `occurrences` desenhadas num eixo de tempo.
2. **A listagem de incidentes já serve título legível e id público.**
   `IncidentSummaryView.title` (`gateway/http/routes/incidents.py:68`) chega
   preenchido ("RestoreDrillStale"), e `public_id` existe desde a v7-020. O
   id interno (`res-…`/`alert:…`) continua servido e continua não sendo
   título — o defeito atual é a tela usá-lo como subtítulo.
3. **A tela de Recursos existe em**
   `console/src/surfaces/screens/resources.tsx` (`ResourcesScreen`, `:166`,
   páginada por `console/src/app/(shell)/resources/page.tsx`) e já lê
   inventário com nome, tipo, estado e visto-por-último (a tela do staging
   mostra exatamente esses quatro). Zona e criticidade já têm leitura
   (`zoneOf`/`criticalityOf` referenciados pela tela). O inventário vem do
   estate (`platform/persistence/ports/estate_repository.py`, `EstateQuery`
   `:295`); a saúde tem histórico
   (`platform/observation/sources/estate_health.py` existe e é testada).
4. **O que a listagem de Recursos NÃO mostra hoje**: o nó Proxmox que
   hospeda o recurso e desde quando um não-saudável está não-saudável. O
   staging em 2026-08-27 mostrava 14 não saudáveis idênticos ("Unhealthy ·
   3 minutes ago") sem nó e sem duração — e a investigação real desta mesma
   sessão provou que o discovery Proxmox conhece o nó de cada guest.
5. **As abas de Conhecimento são** `['learned', 'documents', 'topology']`
   (`console/src/surfaces/screens/knowledge.tsx:226`) e `tabFrom` (`:231`)
   devolve **`documents`** quando a URL não nomeia aba — o board abre em
   Aprendido.
6. **O filtro de componente do Aprendido lista o mesmo componente duas
   vezes** — visto no staging: `container:lxc/122` e `guest:lxc/122` como
   opções distintas, entre 20+ ids crus sem agrupamento.
7. **As rotas da tela O agente estão cravadas** em
   `console/src/surfaces/screens/agent.tsx:200-248`: `/v1/agent/pipeline`
   (estágios com `name`, `model_role`, `dispatches_subagents`),
   `/v1/capabilities`, `/v1/config/{node_id}/catalogue`,
   `/v1/autonomy/policy/{node_id}/outlook` e o replay via
   `/v1/autonomy/policy/{node_id}/preview` (`currentPolicyReplay`, `:182`).
   As abas são `['topology', 'tools', 'autonomy', 'team']` (`:88`).
8. **Os seis estágios reais** vêm de `/v1/agent/pipeline` na ordem resolve →
   intake → plan → gather → diagnose → deliver (comentário em
   `agent.tsx:397-399`), com `humaniseIdentifier` já usado para a forma
   legível (`:405`).
9. **Tabs têm componente pronto**: `Tabs`/`TabLinks`
   (`console/src/components/navigation.tsx:58,152`) com roving focus e
   seleção pela URL — as pills do board são um reskin da 000 sobre esse
   componente, não um componente novo.
10. **No staging (2026-08-27)**: a aba Tools lista 80 capacidades (63
    habilitadas) com domínios (Skills 25, Cloud control plane 24,
    Remediation 20, Methodology 7, Logstore 6, Communication 4, …) e efeitos
    colaterais por capacidade ("Reads", "Writes, reversible", "Writes,
    irreversible", "Destructive", "sensitive"); a aba Autonomy responde as
    cinco classes (Trivial, Low, Moderate, High, Dangerous) todas resolvendo
    para propor; Team context mostra "Prompt budget 0 of 1200 tokens".

## O que esta feature NÃO faz (fronteiras com as irmãs)

- **Título humano de run** é da 020; aqui nenhuma tela inventa título.
- **O Painel** ("o que insiste em acontecer") é da 050 — ele reutiliza o
  mesmo `groupBySubject` do fato 1; esta feature não toca
  `console/src/surfaces/screens/dashboard.tsx`.
- **Rotas de decisão** são da 040; o badge da sidebar e Decisões não são
  daqui.
- **O canal SSE** é da 010. As quatro telas desta feature são leitura
  server-rendered como hoje; o realce "rodando agora" do pipeline metrô lê o
  que a listagem de runs **já** serve (status `running`) e, quando o campo
  de estágio corrente da 020 existir (slot S3), passa a acender o nó certo —
  o cenário disso fica marcado como cross-feature e valida no S3.
- **Tokens, ícones, chips, formas, shell** são da 000 e chegam prontos; esta
  feature só os usa. Um token ou ícone que falte é declarado no relatório
  (EXECUCAO §2), nunca criado aqui.

---

## Alegações normativas

Frases curtas, individualmente testáveis. As marcadas **[staging]** são
staging-safe (leitura pura) e rodam também contra
`https://stg-ninjasre.lan.kyo.ninja`. Cada tela tem seu acceptance spec e o
codifica.

### Incidentes (`/incidents` — `Incidents.dc.html`)

- **AN-I1** A lista agrupada mostra uma linha por assunto, com o nome do
  detector como título (ex.: "RedisExporterDown"). **[staging]**
- **AN-I2** Nenhum subtítulo de linha começa com identificador de recurso; o
  subtítulo nomeia o recurso pela forma humana e o id aparece por último,
  truncado, em fonte mono (ex.: `redis em lxc/122 · pve01 · res-7a73…`).
  **[staging]**
- **AN-I3** Os filtros Estado, Severidade e Visão são segmented controls
  (grupos de botões com opção ativa destacada), não `<select>` nativos.
  **[staging]**
- **AN-I4** A linha do resumo diz assuntos, disparos e críticos em
  investigação com os números da própria listagem (ex.: "17 assuntos · 50
  disparos · 4 críticos em investigação"). **[staging]**
- **AN-I5** Expandir uma linha com mais de um disparo mostra a faixa
  "Disparos nas últimas 24 h": um eixo horizontal com um ponto por
  `occurrence` dentro da janela, posicionado por `opened_at`, círculo para
  resolvido e losango para o disparo em investigação. **[staging]**
- **AN-I6** A expansão de um assunto cujo disparo mais novo tem `run_id`
  mostra o link "investigação em andamento →" (quando vivo) apontando para
  `/runs/<run_id>`, e o bloco "Última causa encontrada:" com o headline do
  run resolvido mais recente quando algum existe. **[staging]**
- **AN-I7** A expansão nunca renderiza duas linhas idênticas: cada
  occurrence aparece uma vez, no eixo de tempo, nunca como lista textual
  repetida N vezes.
- **AN-I8** Cada linha carrega a strip de recorrência (barras verticais, uma
  por occurrence, opacidade crescente para o mais recente), o chip de
  severidade com quadrado, o chip de estado com a forma do estado, `N×` em
  mono e o tempo relativo do disparo mais novo. **[staging]**
- **AN-I9** O rodapé mostra o cartão âmbar "N achados degradados estão sem
  detector ligado" com o N vindo da mesma fonte que o Painel já usa para
  esse número, e o CTA "Ligar detector →" levando à configuração de
  detectores. Zero achados sem detector → o cartão não existe. **[staging]**

### Recursos (`/resources` — `Resources.dc.html`)

- **AN-R1** O cabeçalho mostra a barra de saúde segmentada: um segmento por
  estado (saudável, desconhecido, não saudável, ausente) com largura
  proporcional à contagem, e a legenda clicável com as quatro contagens.
  **[staging]**
- **AN-R2** Cada item da legenda filtra a lista ao ser clicado, e o filtro
  fica na URL (a tela recarregada mantém o filtro). **[staging]**
- **AN-R3** O filtro por tipo é uma linha de chips com contagem por tipo
  (Contêiner, VM, Nó, Datastore, Backup), não um `<select>`; a busca por
  nome é um campo compacto (não um input de largura total). **[staging]**
- **AN-R4** A lista agrupa por nó: uma seção por nó Proxmox, com cabeçalho
  nome do nó + chip de saúde da seção + contagem de recursos. Recurso sem nó
  conhecido agrupa sob "sem nó declarado". **[staging]**
- **AN-R5** Recursos são cards em grade (não linhas de tabela), cada um com
  ícone do tipo, nome, tipo por extenso, visto-por-último, e a marca de
  estado com forma (quadrado vermelho não saudável / círculo verde
  saudável); não saudável carrega borda avermelhada e "há quanto tempo fora".
  **[staging]**
- **AN-R6** Não saudáveis vêm antes de saudáveis dentro de cada seção, e a
  seção com não saudáveis vem antes das saudáveis. **[staging]**
- **AN-R7** Havendo 3 ou mais não saudáveis com o mesmo nó, a síntese
  aparece acima das seções: "N não saudáveis há mais de X — todos
  <tipo> em <nó>, mesma janela de início", com X derivado do
  `unhealthy_since` mais antigo do grupo, e o link "investigar em lote →"
  abrindo o modal de investigar com objetivo pré-preenchido nomeando o grupo.
- **AN-R8** O aviso de zona/criticidade é um cartão fino âmbar no rodapé com
  "declarar agora →", não uma frase no meio do cabeçalho da lista; ele some
  quando existe ao menos uma zona ou criticidade declarada. **[staging]**
- **AN-R9** A resposta da listagem carrega, por recurso, o nó que o hospeda
  e, para não saudável, desde quando — e a tela lê esses campos da resposta,
  nunca os calcula localmente.

### Conhecimento (`/knowledge` — `Knowledge.dc.html`)

- **AN-C1** As abas são pills na ordem Aprendido, Documentos, Topologia, com
  ícone; `/knowledge` sem aba na URL abre em Aprendido; deep links
  existentes (`?tab=documents`, `?tab=topology`) seguem abrindo suas abas.
  **[staging]**
- **AN-C2** O filtro de componente agrupa por tipo (serviço, nó, guest,
  cluster) e resume ("agrupado por tipo: 8 serviços · 3 nós · 5 guests · 1
  cluster"); nenhum componente aparece duas vezes por ter sido visto como
  `container:` e como `guest:` — as duas grafias do mesmo identificador
  resolvem para uma opção só. **[staging]**
- **AN-C3** Cada episódio é um card: título-frase, sub-linha com a classe do
  episódio e o detalhe mono, chip de resultado com forma (círculo cheio
  verde = resolvido, anel âmbar = inconclusivo), chips de componente
  clicáveis (aplicam o filtro), tempo relativo e "abrir investigação →" para
  `/runs/<run_id>` quando o episódio referencia um run. **[staging]**
- **AN-C4** O painel lateral "O que o agente aprendeu com isso" lista as
  propostas de conhecimento pendentes de revisão (as que investigações
  propuseram e ninguém decidiu), cada uma com o texto proposto, a origem, e
  o CTA "promover a documento" levando à fila de revisão existente; sem
  proposta pendente, o painel diz isso e aponta a fila. **[staging]**
- **AN-C7** As abas Documentos e Topologia são reformadas conforme seus
  artboards — `design/padrao-2026-08/KnowledgeDocuments.dc.html` (empty
  state de uma frase com CTA duplo, revisão de propostas de agente na
  própria aba, configuração avançada como grid de cards) e
  `KnowledgeTopology.dc.html` (grafo com seletor de vizinhança e rail de
  detalhe do nó; o empty state vira uma linha) — acrescentados ao board em
  2026-08-27 pela decisão 8 da onda. **[staging]**
- **AN-C5** A faixa inferior mostra dois cards-prévia: Documentos (contagem
  de documentos ingeridos, ou "nada ingerido ainda") e Topologia (contagem
  de nós que a topologia registrou, ou "nada observado ainda"), cada um com
  seu link. **[staging]**
- **AN-C6** Nenhuma parede de prosa: nenhum empty state desta tela excede
  duas frases, e todo empty state termina com uma ação.

### O agente (`/agent` — `TheAgent.dc.html`)

- **AN-A1** A aba Pipeline abre com a linha de metrô: seis nós circulares
  conectados por um trilho, na ordem que `/v1/agent/pipeline` serve, cada nó
  com ícone, número + regime em mono (ex.: "1 · sem modelo", "2 · modelo:
  intake", "3 · determinístico" — derivado de `model_role` vazio ou
  preenchido), nome legível e uma frase de microcopy. **[staging]**
- **AN-A2** Nenhuma descrição de estágio excede uma frase na linha de metrô;
  a prosa longa atual não é renderizada nessa visão. **[staging]**
- **AN-A3** Com ao menos um run `running`, o card do pipeline mostra o chip
  "N investigações em voo" com o N da listagem de runs; com o campo de
  estágio corrente disponível (entregue pela feature de título vivo), o nó
  do estágio corrente ganha o realce de ativo — sem o campo, nenhum nó é
  realçado e nada quebra. *(realce validado no slot S3)*
- **AN-A4** Abaixo do metrô há três cards-resumo — Ferramentas, Autonomia,
  Contexto do time — cada um lendo a rota que sua aba já lê. **[staging]**
- **AN-A5** O card Ferramentas diz "X de Y habilitadas" (contagens de
  `/v1/capabilities` + catálogo do nó), desenha mini-barras por domínio
  (top 6 por contagem, largura proporcional) e os chips de efeito colateral
  com contagem — leitura, escrita reversível, e destrutiva em vermelho com
  ícone de alerta. **[staging]**
- **AN-A6** O card Autonomia mostra a escada das cinco classes na ordem
  servida por `/v1/autonomy/policy/{node}/outlook`, cada uma com o chip da
  decisão resolvida ("Propor" em todas hoje), a classe mais perigosa com
  tratamento âmbar, e uma frase-síntese; as explicações "Why:" completas não
  aparecem neste card. **[staging]**
- **AN-A7** O card Contexto do time mostra a barra de orçamento de prompt
  com "N de M tokens" reais da leitura da aba Team, e o estado vazio ("Nenhum
  fato escrito ainda") em no máximo duas frases com o CTA "escrever fatos do
  ambiente →". **[staging]**
- **AN-A8** As abas Ferramentas, Autonomia e Contexto do time são
  reformadas conforme seus próprios artboards —
  `design/padrao-2026-08/AgentTools.dc.html` (rail de domínios com
  contagens + grade de cards de capacidade com chip de efeito colateral e
  toggle, no lugar da tabela de 80 linhas),
  `AgentAutonomy.dc.html` (a escada das cinco classes com uma frase por
  classe e veredito em chip, no lugar dos cinco parágrafos "Why") e
  `AgentTeam.dc.html` (editor de seções com orçamento de prompt na rail) —
  acrescentados ao board em 2026-08-27 pela decisão 8 da onda (sem
  artboard, sem reforma); os cards do Pipeline linkam cada um para sua
  aba. **[staging]**

### Transversais às quatro telas

- **AN-T1** Nenhuma das quatro telas renderiza `<select>` nativo como
  controle de filtro primário. **[staging]**
- **AN-T2** Nenhum texto visível nas quatro telas casa
  `/^(res-[0-9a-f]{8}|[0-9a-f]{16,})/` como início de título ou subtítulo —
  identificadores aparecem apenas em fonte mono, truncados, depois da forma
  humana. **[staging]**
- **AN-T3** Todas as strings novas existem em `en` e `pt-BR` via `message()`
  — nenhuma string de UI hardcoded no componente.
- **AN-T4** As quatro telas passam o gate visual de EXECUCAO §3 nos dois
  temas contra seus artboards, com veredito linha a linha em
  `evidence/visual/VEREDITO.md`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Incidentes conta a história de cada assunto (Priority: P1)

Um operador abre `/incidents`, vê sete assuntos em vez de cinquenta linhas,
expande RedisExporterDown e entende em dez segundos: oito disparos desde
ontem no eixo de tempo, sete resolvidos, um em investigação agora, e a
última causa encontrada foi uma parada administrativa do contêiner.

**Why this priority**: é a tela de triagem; o defeito atual (oito linhas
idênticas sem link) transforma o histórico em ruído e esconde o único fato
que importa — que o mesmo assunto insiste.

**Independent Test**: no staging, abrir `/incidents`, expandir o primeiro
assunto com `count > 1`, e conferir: eixo de tempo com um ponto por
occurrence, link para a investigação viva, bloco de última causa, e nenhum
subtítulo começando com `res-`.

**Acceptance Scenarios**:

1. **Given** a listagem agrupada com um assunto de 8 occurrences, **When** o
   operador expande a linha, **Then** a faixa de 24 h mostra um ponto por
   occurrence dentro da janela, posicionado por `opened_at`.
2. **Given** um assunto cujo disparo mais novo está em investigação com
   `run_id`, **When** a linha é expandida, **Then** "investigação em
   andamento →" aponta para `/runs/<run_id>`.
3. **Given** um assunto com ao menos um disparo resolvido por investigação,
   **When** a linha é expandida, **Then** "Última causa encontrada:" mostra
   o headline desse run.
4. **Given** qualquer linha da lista, **When** ela renderiza, **Then** o
   subtítulo nomeia recurso e nó em forma humana e o id interno aparece por
   último, truncado, em mono.
5. **Given** os filtros da tela, **When** o operador escolhe "Crítico" no
   segmented control de severidade, **Then** a URL carrega o filtro e a
   lista mostra só os assuntos com severidade crítica.

---

### User Story 2 - Recursos responde "onde dói" de relance (Priority: P1)

Um operador abre `/resources` durante uma degradação em lote e a tela já
respondeu: a barra segmentada mostra a proporção doente, a síntese diz "14
não saudáveis há mais de 2 h — todos contêineres em pve02", e um clique abre
uma investigação sobre exatamente esse grupo.

**Why this priority**: hoje os 14 não saudáveis são 14 linhas idênticas sem
nó nem duração — a tela sabia do problema em lote e não o disse. É a
diferença entre inventário e triagem.

**Independent Test**: no staging (que tem 14 não saudáveis reais em pve02),
abrir `/resources` e conferir barra segmentada com as quatro contagens,
seção pve02 antes de pve01, cards com borda avermelhada e duração, e a
síntese no topo.

**Acceptance Scenarios**:

1. **Given** o inventário com as contagens 71/14/14/12, **When** a tela
   abre, **Then** a barra segmentada tem quatro segmentos proporcionais e a
   legenda com as quatro contagens.
2. **Given** a legenda, **When** o operador clica em "não saudáveis",
   **Then** a lista filtra para os não saudáveis e a URL carrega o filtro.
3. **Given** recursos hospedados em dois nós, **When** a lista renderiza,
   **Then** existe uma seção por nó com cabeçalho nome + chip de saúde +
   contagem, e a seção com não saudáveis vem primeiro.
4. **Given** 14 não saudáveis no mesmo nó com `unhealthy_since` na mesma
   janela, **When** a tela abre, **Then** a síntese os descreve com nó, tipo
   e duração, e "investigar em lote →" abre o modal com objetivo
   pré-preenchido nomeando o grupo.
5. **Given** um deployment sem zona/criticidade declarada, **When** a tela
   abre, **Then** o aviso é um cartão fino no rodapé com "declarar agora →" —
   e não existe quando há declaração.

---

### User Story 3 - Conhecimento mostra o que ficou e o que está por decidir (Priority: P2)

Um operador abre `/knowledge` e cai em Aprendido: quatro episódios como
cartões legíveis, filtráveis por componente sem duplicata, e ao lado as
lições que investigações propuseram e que esperam uma pessoa promover a
documento.

**Why this priority**: é a tela da memória do produto — vende o diferencial
(o agente aprende) — mas depende dos dados existirem; P2 porque não bloqueia
triagem.

**Independent Test**: no staging, abrir `/knowledge`, conferir a aba
Aprendido ativa por padrão, episódios como cards com forma+cor no resultado,
filtro de componente agrupado sem `container:`/`guest:` duplicados, e o
painel lateral refletindo a fila de propostas real (com proposta ou com o
estado vazio de duas frases).

**Acceptance Scenarios**:

1. **Given** `/knowledge` sem query, **When** a tela abre, **Then** a aba
   ativa é Aprendido; **Given** `?tab=documents`, **Then** Documentos.
2. **Given** episódios cujos componentes incluem `container:lxc/122` e
   `guest:lxc/122`, **When** o filtro de componente abre, **Then** `lxc/122`
   aparece uma única vez, sob o grupo guests.
3. **Given** um episódio com `run_id`, **When** o card renderiza, **Then**
   "abrir investigação →" aponta para `/runs/<run_id>`.
4. **Given** propostas de conhecimento pendentes, **When** a tela abre,
   **Then** o painel lateral lista cada proposta com origem e "promover a
   documento" levando à fila de revisão; **Given** nenhuma pendente, **Then**
   o painel diz isso em até duas frases com link para a fila.
5. **Given** a faixa inferior, **When** renderiza, **Then** Documentos e
   Topologia mostram contagem real ou o estado vazio de uma frase, cada um
   com link.

---

### User Story 4 - O agente se apresenta em uma tela (Priority: P2)

Alguém avaliando o produto abre `/agent` e entende em trinta segundos o que
ele é: seis estágios numa linha de metrô com uma frase cada, e três cartões
dizendo o que ele pode chamar, o que faz sem pedir (nada — propõe), e que
contexto o time deu.

**Why this priority**: é a tela que vende a arquitetura; depois das telas de
operação porque quem opera já a conhece.

**Independent Test**: no staging, abrir `/agent`, conferir a linha de metrô
com os seis estágios servidos por `/v1/agent/pipeline`, os três cards com
números reais (63 de 80; cinco classes → Propor; 0 de 1200 tokens), e as
outras três abas ainda completas.

**Acceptance Scenarios**:

1. **Given** `/v1/agent/pipeline` servindo seis estágios, **When** a aba
   Pipeline abre, **Then** a linha de metrô mostra os seis na ordem servida,
   cada nó com ícone, regime em mono, nome legível e uma frase.
2. **Given** o catálogo do nó com 80 capacidades e 63 habilitadas, **When**
   o card Ferramentas renderiza, **Then** diz "63 de 80 habilitadas", as
   mini-barras dos 6 maiores domínios, e os chips de efeito colateral com
   contagem, destrutiva em vermelho.
3. **Given** o outlook de autonomia com cinco classes resolvendo a propor,
   **When** o card Autonomia renderiza, **Then** as cinco linhas mostram
   "Propor", a mais perigosa em âmbar, e nenhuma explicação "Why:" completa.
4. **Given** runs com status `running` na listagem, **When** a aba Pipeline
   abre, **Then** o chip diz "N investigações em voo" com o N da listagem.
5. **Given** as abas Ferramentas/Autonomia/Contexto, **When** abertas,
   **Then** seguem servindo o conteúdo completo de hoje, no skin da 000.

### Edge Cases

- Assunto com um único disparo: sem faixa de 24 h (nada a plotar além do
  próprio ponto); a linha continua expandível para o bloco de causa/link.
- Occurrence fora da janela de 24 h: a faixa mostra os dentro da janela e
  diz "e mais N antes de ontem" — nunca esconde silenciosamente.
- Recurso `absent` (12 no staging): entra na barra e na legenda; nos grupos
  aparece na seção do último nó conhecido, marcado ausente com traço.
- Todos os nós saudáveis: nenhuma síntese; seções em ordem alfabética.
- Episódio sem `run_id` (registro antigo): card sem o link, nunca link
  quebrado.
- `/v1/agent/pipeline` vazio ou falho: o card do metrô usa o empty/failure
  state do `Panel` existente — nunca seis nós inventados.
- Filtro na URL apontando componente que deixou de existir: filtro mostrado
  como ativo com resultado vazio honesto + "limpar filtro".
- Tema claro: as quatro telas usam os tokens claros da 000; nenhum hex de
  tema escuro hardcoded em componente (o gate visual pega).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001** `console/src/surfaces/screens/incidents.tsx` renderiza a lista
  agrupada conforme `Incidents.dc.html`: linha por `IncidentGroup` com marca
  de severidade (quadrado, `danger`), título = `group.title`, subtítulo =
  forma humana dos `subjects` + nó quando conhecido + id mono truncado por
  último; strip de recorrência (SVG, uma barra por occurrence, opacidade
  crescente), chips severidade/estado, `N×` mono, tempo relativo de
  `lastAt`. Nada disso pede endpoint novo (fato 1).
- **FR-002** A expansão da linha renderiza a faixa "Disparos nas últimas
  24 h" a partir de `group.occurrences`: eixo horizontal com rótulos de
  borda (início da janela, "agora"), ponto por occurrence posicionado
  proporcionalmente por `opened_at`, círculo `success` para terminal e
  losango `accent` para em investigação, tooltip com hora e estado.
- **FR-003** A expansão mostra: link "investigação em andamento →" para
  `/runs/<run_id>` quando o disparo falante (`group.state` não terminal) tem
  `run_id`; e o bloco "Última causa encontrada:" com o headline do run da
  occurrence terminal mais recente que tem `run_id` — headline lido da
  listagem de runs que o console já consome, resolvido no server component
  (uma leitura para a página, não uma por linha).
- **FR-004** Os filtros de `/incidents` viram segmented controls (Estado:
  Qualquer/Investigando/Resolvido; Severidade: Qualquer/Crítico; Visão: Por
  assunto/Cada disparo) mantendo o estado na URL como hoje; "Cada disparo"
  mantém a visão plana atual re-skinada.
- **FR-005** O cartão de detector do rodapé lê a mesma contagem de "achados
  degradados sem detector" que o Painel de hoje exibe (mesma fonte, decisão
  3 da v7 — uma fonte por fato) e linka para a tela de configuração de
  detectores; contagem zero remove o cartão.
- **FR-006** A resposta da listagem de recursos passa a carregar, por
  recurso: `node` (o nó que o hospeda, do discovery Proxmox já registrado no
  estate) e `unhealthy_since` (ISO 8601, da transição registrada no
  histórico de saúde do estate; ausente para saudável). Campos novos no
  contrato, documento de API e cliente TS regenerados; a rota exata e o
  símbolo do handler são cravados na Fase 0 das tasks a partir do que
  `ResourcesScreen` já consome.
- **FR-007** `console/src/surfaces/screens/resources.tsx` renderiza conforme
  `Resources.dc.html`: barra de saúde segmentada + legenda clicável
  (filtros na URL), busca compacta de 280px, chips de tipo com contagem,
  seções por `node` (não saudáveis primeiro), cards em grade
  `repeat(4, minmax(0,1fr))` com ícone por tipo, marca de estado com forma,
  visto-por-último e duração de não-saudável.
- **FR-008** A síntese dos não saudáveis é computada na tela a partir da
  resposta (grupo = mesmo `node` + mesmo tipo + `unhealthy_since` dentro de
  uma janela de 30 min), renderizada quando o grupo tem 3+, com "investigar
  em lote →" abrindo o modal de investigar com objetivo pré-preenchido "O
  que derrubou N <tipo> em <nó> desde <hora>?" (o modal é da 070; até lá o
  link leva ao fluxo de investigar atual com o mesmo texto).
- **FR-009** O aviso de zona/criticidade move para o rodapé como cartão
  âmbar fino com "declarar agora →", presente só quando nenhuma zona nem
  criticidade existe (leitura que a tela já faz — `zoneOf`/`criticalityOf`).
- **FR-010** `/knowledge` abre em Aprendido: a ordem das pills é
  learned/documents/topology e `tabFrom` (fato 5) passa a devolver
  `learned` no default; deep links com `?tab=` preservados.
- **FR-011** O filtro de componente do Aprendido agrupa por tipo com
  contagem e normaliza duplicatas: componentes `container:<id>` e
  `guest:<id>` com o mesmo `<id>` resolvem para uma opção única sob guests
  (tabela de normalização com testes unitários; a forma exibida é o `<id>`
  humano, a query preserva o valor canônico).
- **FR-012** Cada episódio renderiza como card conforme `Knowledge.dc.html`:
  título-frase, sub-linha classe + detalhe mono, chip de resultado
  (círculo verde resolvido / anel âmbar inconclusivo — formas da 000), chips
  de componente que aplicam o filtro, tempo relativo, e "abrir investigação
  →" quando o episódio tem run associado.
- **FR-013** O painel "O que o agente aprendeu com isso" lista as propostas
  de conhecimento pendentes (a fila que `propose_knowledge` alimenta e que a
  tela de propostas já lê — rota cravada na Fase 0), cada card com o texto,
  a origem (run/episódio) e "promover a documento" para a fila de revisão;
  vazio honesto de duas frases com link quando não há pendência.
- **FR-014** A faixa inferior de `/knowledge` mostra os dois cards-prévia
  com contagens reais (documentos ingeridos; nós da topologia) lidas das
  mesmas rotas que as abas Documentos e Topologia já leem, com empty de uma
  frase.
- **FR-015** A aba Pipeline de `/agent` renderiza a linha de metrô conforme
  `TheAgent.dc.html` a partir de `/v1/agent/pipeline`: seis nós na ordem
  servida, ícone por estágio, regime derivado ("sem modelo" quando
  `model_role` vazio; "modelo: <role>" quando não; "determinístico" para o
  estágio de plano), nome via `humaniseIdentifier`, uma frase de microcopy
  i18n por estágio; a prosa longa some desta visão (permanece acessível na
  listagem detalhada abaixo do fold, como hoje, re-skinada).
- **FR-016** O chip "N investigações em voo" conta runs `running` da
  listagem de runs; o realce de nó ativo lê o campo de estágio corrente
  quando presente na resposta e não renderiza realce quando ausente
  (compatível antes e depois da 020).
- **FR-017** Os três cards-resumo leem: Ferramentas de `/v1/capabilities` +
  `/v1/config/{node}/catalogue` (contagens por domínio e por efeito
  colateral, X de Y habilitadas); Autonomia de
  `/v1/autonomy/policy/{node}/outlook` (classes e decisão resolvida);
  Contexto do time da leitura que `TeamTab` já faz (orçamento N de M).
  Cada card linka sua aba.
- **FR-018** Toda string nova entra em `console/src/i18n/` nas duas línguas;
  esta feature é dona dos single-write no slot S2 (EXECUCAO §2) e registra
  em `console/visual/screens.json` as variantes novas de captura das quatro
  telas.
- **FR-019** Quatro acceptance specs red-first, um por tela:
  `console/tests/e2e/incidents-by-subject.acceptance.spec.ts`,
  `console/tests/e2e/resources-by-node.acceptance.spec.ts`,
  `console/tests/e2e/learned-knowledge.acceptance.spec.ts`,
  `console/tests/e2e/agent-pipeline.acceptance.spec.ts`, codificando as
  alegações normativas de sua tela (as `[staging]` marcadas staging-safe).

### Key Entities

- **IncidentGroup / IncidentOccurrence**: já existem
  (`incident-groups.ts:28,42`); ganham consumo novo (faixa de 24 h, strip),
  nenhum campo novo.
- **Recurso do estate (contrato)**: ganha `node: string` e
  `unhealthy_since: string | null` na resposta da listagem; nenhum campo
  removido.
- **Componente normalizado (Conhecimento)**: `{tipo, id, formaExibida,
  valorCanonico}` — derivado, sem persistência.
- **Proposta de conhecimento pendente**: entidade existente da fila de
  revisão; aqui só lida.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001** No staging, `/incidents` mostra ≤ um terço das linhas da visão
  plana (assuntos vs disparos: 17 vs 50 na amostra de partida) e a expansão
  do assunto mais recorrente exibe todos os seus disparos num único eixo.
- **SC-002** Zero ocorrências, nas quatro telas, de subtítulo ou título
  começando com identificador (`res-…`/hex) — verificado pelo acceptance e
  pela transversal.
- **SC-003** `/resources` responde "o que está doente, onde, desde quando"
  sem interação: barra, seções por nó e síntese visíveis no primeiro paint
  (dados da mesma resposta; nenhuma segunda requisição para a síntese).
- **SC-004** O filtro de componente de Conhecimento no staging lista cada
  identificador uma única vez (hoje: `lxc/122` duas vezes), com os grupos e
  contagens visíveis.
- **SC-005** As oito capturas (4 telas × 2 temas) do gate visual têm
  VEREDITO.md com todas as linhas CONFORME, ou desvio registrado em
  `design/padrao-2026-08/DIVERGENCIAS.md` com aprovação do operador — nenhum
  terceiro estado.
- **SC-006** As quatro specs de acceptance passam contra o staging na
  marcação staging-safe ao fim do slot, partindo de vermelho confirmado no
  início.

## Assumptions

- A 000 (fundação visual) está mergeada quando este slot abre: tokens,
  ícones, chips com contorno, formas e shell prontos; esta feature não cria
  nenhum token/ícone (falta → declarada no relatório, EXECUCAO §2).
- O headline de run existe no contrato de runs (v7-001) e a listagem de
  incidentes serve `public_id`/`title` (v7-020) — usados, não reimplementados.
- O discovery Proxmox registra o nó de cada guest no estate (comprovado pela
  investigação real de 2026-08-27, que listou guests por nó); expor
  `node`/`unhealthy_since` é leitura de dado que o backend já tem, não
  coleta nova.
- O modal de investigar da 070 chega depois (S4); até lá o "investigar em
  lote" usa o fluxo de investigar atual com objetivo pré-preenchido — o
  href não muda quando a 070 chegar.
- Playwright/dataset local cobrem as quatro telas com dados que exercitam
  agrupamento (o dataset simulado já carrega incidentes recorrentes e
  recursos; ajustes de dataset são regenerados, nunca editados à mão).
