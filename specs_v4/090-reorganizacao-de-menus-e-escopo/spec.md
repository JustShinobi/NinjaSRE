# 090 — Reorganização de menus e escopo

As specs 001–038 consertam telas. Esta propõe mudar o mapa. Pré-alfa, sem
usuários: o custo de mover rotas é zero e nunca mais será tão baixo.

## O diagnóstico em uma frase

O console tem **18 entradas de menu para ~6 tarefas reais**, e a divisão segue
a arquitetura interna (cada subsistema ganhou uma tela) em vez das perguntas
do operador. A referência apontada pelo operador (demo.opensre.in/team) faz o
inverso: 5 itens, cada um respondendo uma pergunta ("o que houve" / "o que o
agente fez" / "o que ele lembra" / "como ele é" / "o que ele pode usar").

## As tarefas reais

1. Ver o que precisa de mim agora e decidir (aprovar/negar).
2. Investigar algo / ver investigações passadas.
3. Ver a saúde do que é observado.
4. Entender o que o agente é, sabe e pode fazer.
5. Configurar entrada (alertas, agendas) e saída (destinos).
6. Administrar acesso e auditar.

## Sidebar proposto: 18 → 10

```
AGORA
  Overview
  Incidents
  Investigations            (hoje: Runs)
  Decisions          [n]    (fusão: Approvals + Proposed changes)

AMBIENTE
  Resources
  Knowledge                 (fusão: Memory + Knowledge + Topology, em abas)
  The agent                 (absorve leitura do Catalogue e Team context)

CONFIGURAÇÃO
  Setup                     (hoje: First steps; some ao completar)
  Integrations              (extraída do Catalogue: credenciais + saúde + teste)
  Signals                   (fusão: Detectors + Data: entrada, agendas, saída)
  Autonomy
  Configuration             (vista avançada, com proveniência)
  Administration            (com Audit como aba)
```

## Cada fusão, defendida

### Decisions ⇐ Approvals + Proposed changes

Hoje: dois inboxes de decisão humana, nomes quase sinônimos, em grupos
diferentes do menu, sem referência mútua. O racional registrado em
`routes.ts` ("perguntas diferentes, lidas em momentos diferentes") é correto
sobre as *perguntas* — e é exatamente o que abas resolvem sem custar uma
entrada de menu e a confusão de nomes. Uma tela "Decisions" com abas **Ações**
(pode o agente fazer isto agora) e **Mudanças propostas** (o deployment
deveria ser diferente), badge somada no menu. Quem lê uma fila vê que a outra
existe — que é justamente o que evita "a queue that grows until it is
discovered", o risco que o comentário original queria evitar.

### Knowledge ⇐ Memory + Knowledge + Topology

Três telas, uma pergunta: **o que o agente sabe sobre este ambiente?**
Episódios/estratégias (aprendido), documentos (ensinado), grafo (observado).
Todas as três hoje estão vazias com empty states que apontam umas para as
outras. Abas: Aprendido · Documentos · Topologia. Ganho colateral: os três
empty states viram um só, explicando o ciclo completo de conhecimento.

### The agent ⇐ + Catalogue (leitura) + Team context

"The agent" já tem abas Topology/Tools/Autonomy e é a melhor tela do console.
Proposta: ela vira a casa de **ler o agente** — estágios, tools e skills
disponíveis (o catálogo em modo leitura, com busca), roles/modelos efetivos,
budgets, e o contexto do time (que é, na prática, parte do prompt do agente —
o texto da própria tela Team context o define assim). Escrever continua nas
telas de escrita (Integrations, Autonomy, Configuration).

### Integrations ⇐ extraída do Catalogue

A parte de *escrita* do Catalogue atual: 85 integrações como cards com estado
real (ausente / armazenada / verificada / falhando), credencial, teste
("Check it" — hoje só existe no first-run), e filtro. É a tela que faltava: o
first-run aponta para cá, o Catalogue aponta para cá, o "Blocked by needs X"
de cada tool aponta para cá. Detalhe na spec 025.

### Signals ⇐ Detectors + Data

Duas metades do mesmo tubo: **o que entra** (webhooks, detectores, agendas) e
**o que sai** (destinos de relatório). Hoje Detectors está em "Environment" e
Data em "Settings", e o formulário de agendamento mora em Detectors por falta
de lugar melhor. Abas: Entrada (webhooks + roteamento + simulador) · Observação
contínua (detectores + guardian) · Agendas · Destinos.

### Administration + Audit

Audit é permissão de administrador (`audit.read`) e é lido no contexto de
"quem fez o quê" — a pergunta vizinha de "quem pode o quê". Aba dentro de
Administration. (Menor convicção desta lista; manter separado é aceitável se o
volume de uso provar o contrário.)

## O que NÃO fundir

- **Incidents vs Investigations** — conceitos distintos com ciclos de vida
  distintos (um incidente agrega investigações); a confusão atual se resolve
  com os empty states certos (spec 011), não com fusão.
- **Autonomy dentro de Configuration** — a decisão de autonomia merece a
  própria porta; é a mais consequente do produto.
- **Resources dentro de Knowledge** — saúde ao vivo ≠ conhecimento acumulado.

## Mudanças de escopo transversais

### 1. Camada de tradução de erros

Um mapa `código de erro → {título curto, ação, link}` no console. Nenhuma
exceção do gateway aparece verbatim (specs 001/010/012). O caso
`InvestigatorNotConfigured` é o piloto: aparece hoje em 4 superfícies.

### 2. Um vocabulário só

| interno (some da UI) | UI |
|---|---|
| run | investigação |
| interactive (trigger) | manual |
| propose_only / act_on_low_risk / act_and_report | com descrição por extenso |
| Unplaced / Ungraded | sem zona / sem criticidade (com ação) |
| healthy/degraded vs HEALTHY/UNHEALTHY/UNKNOWN | um único conjunto |
| "Set at nothing yet" | "usando o padrão: <valor>" |

### 3. Empty states com causa local

Padrão para todo empty state (specs 011/013/021/023): dizer por que *este
deployment* está vazio (setup incompleto, guardian desligado, endpoint fora)
e a próxima ação, nunca só a teoria geral da feature.

### 4. Dashboard orientado a ação

Detalhado na spec 010, na forma da referência: hero de setup enquanto
incompleto; depois, KPIs do agente (runs, sucesso, custo, MTTD), atividade em
prosa, quick actions com descrição.

### 5. Telas próprias como único caminho de escrita

Configuration mostra tudo com proveniência, mas seções com tela dedicada
(autonomia, SSO, observação, contexto) linkam para a tela dedicada em vez de
duplicar o formulário (spec 032, item 6).

## Sequência sugerida

1. **O funil primeiro** (spec 030, F1–F6): é o conjunto que separa "pré-alfa"
   de "algo funcional". Inclui a decisão de escopo do F6 — compor o runtime
   do investigador a partir da configuração em vez de exigir env var.
2. **Demais quebrados** (não dependem da reorganização): tour que não morre,
   `/v1/proposals`, heading de Autonomy, detalhe de Resources fora da
   viewport, courier que engole `detail` não-string do gateway.
3. **Tradução de erros + vocabulário** — barato, muda a primeira impressão
   inteira.
4. **Integrations extraída** — destrava first-run, Catalogue e os "Blocked by".
5. **Sidebar novo + fusões** — uma vez, cedo, enquanto não há usuários.
6. **Dashboard novo** — por último, porque consome os KPIs e estados que os
   itens anteriores criam.
