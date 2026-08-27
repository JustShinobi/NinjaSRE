# 010 — Dashboard (Overview)

A tela de entrada. Hoje ela mostra um stack de erro, quatro números e um vazio
no centro. A referência apontada pelo operador (demo.opensre.in/team) mostra o
que a mesma tela deveria fazer: dizer **o que fazer agora**.

## O que está hoje

- Faixa vermelha "1 items need you" cujo conteúdo é o texto integral de
  `InvestigatorNotConfigured` com nome de env var e instrução de deploy.
- Quatro cards numéricos (Resources watched 103 / Healthy 79 / Degraded and
  unhealthy 24 / Runs in the last day 1).
- "Recent activity" com um item: o mesmo stack de erro repetido.
- Coluna direita: checklist "Finish setting up (3 of 7 steps left)", "Quick
  actions" (três links de frase), "Estate health" (contagem por tipo de
  recurso), Guardian.
- Centro da página vazio abaixo de "Recent activity".

## Problemas

### 1. [bloqueia entendimento] O erro cru é a primeira leitura da página

O texto `InvestigatorNotConfigured: ... Set NINJASRE_INVESTIGATOR to
'module:factory' — a callable returning the runner...` é dirigido a quem faz
deploy, não a quem abriu o console — e o console *tem* uma tela que resolve
exatamente isso (First steps, passo "Choose a model"). A mensagem certa no
lugar da faixa é: **"O investigador ainda não está configurado — investigações
vão falhar até terminar a configuração"**, com botão para o passo pendente. O
stack cru fica atrás de um "detalhe técnico".

### 2. [bloqueia entendimento] Setup incompleto não é o hero da página

Com 3 de 7 passos faltando, o dashboard deveria ser dominado pelo caminho de
conclusão (como o hero "Watch OpenSRE Investigate" da referência domina a tela
de demo). Hoje o checklist é um card lateral com links pequenos, e o centro da
página está literalmente vazio. Proposta:

- **Enquanto o checklist não fecha:** hero central com os passos restantes, o
  próximo passo em destaque, e um botão único "Continuar configuração".
- **Depois que fecha:** o hero dá lugar a conteúdo de operação (ver item 4).

### 3. [bloqueia entendimento] Os números não contam uma história consistente

"Degraded and unhealthy 24" ao lado de "Incidents: nenhum" (e de badges
UNHEALTHY na tela Resources) sem nenhuma ponte entre os fatos. Um operador lê
"24 unhealthy, 16 open findings" e clica em Incidents: vazio. A relação
(finding ≠ incident; detector nenhum está ligado) existe no produto e não está
na tela. Cada card numérico precisa de: para onde clica (hoje o link "See the
list behind this figure" é invisível — só existe para leitor de tela) e, quando
o número é alarmante, o que o explica.

### 4. [bloqueia entendimento] Faltam os números que dizem se a coisa funciona

A referência mostra Total Runs / Success rate / MTTD. O equivalente aqui —
runs no período, taxa de sucesso, custo/tokens do período, tempo até
diagnóstico — existe nos dados (run list, cost per run) e não está na tela. O
quarteto atual é todo sobre o *estate*; nada é sobre o *agente*, que é o
produto.

### 5. [polimento] Quick actions vagas

"Load what your team already knows", "Tune what the agent may do", "See what it
has learned" — frases poéticas, destino incerto. A referência usa
título + descrição ("Agent Topology — View agent configuration"). Renomear
para o nome da tela de destino com uma linha de descrição.

### 6. [polimento] "Estate health" não é saúde

O card lista contagens por tipo (backup_job 4, container 72...) sem estado
nenhum — é um inventário, não saúde. Ou mostra saúde por tipo (n saudáveis / n
não), ou sai.

### 7. [polimento] "1 items need you", "OLDEST 15 HOURS AGO"

Plural fixo; e o selo "OLDEST 15 HOURS AGO" gritando em caps sem dizer por que
a idade importa.

## Critérios de aceite

- Com setup incompleto, a página é dominada pelo caminho de conclusão e nenhum
  stack de erro aparece verbatim.
- Todos os cards numéricos são clicáveis com affordance visível e levam à lista
  que os explica, já filtrada.
- Existe pelo menos um indicador do agente (runs/sucesso/custo) na página.
- Com setup completo e estate saudável, a página não fica vazia: mostra
  atividade recente e ações de partida (investigar, ver runs).
