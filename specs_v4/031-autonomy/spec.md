# 031 — Autonomy

A tela que controla a coisa mais delicada do produto (o que o agente faz
sozinho) e a que mais pressupõe conhecimento prévio.

## Problemas

### 1. [quebrado] Heading "Bounds no level overrides"

Texto de painel visivelmente quebrado (falta conjunção — "Bounds **and**
level overrides" — ou é interpolação falhada). Corrigir a string nos dois
catálogos de i18n.

### 2. [bloqueia entendimento] Três painéis, o mesmo vazio

"Rules, in resolution order", "Save this posture" e "Bounds..." mostram o
mesmo "No policy recorded ... Look at the configuration" três vezes. Quando
não há política, a página deveria ter **um** estado: "Tudo resolve para
propose-only (o padrão seguro). Crie a primeira regra" — com o formulário de
regra aqui, não um link genérico para a árvore de Configuration.

### 3. [bloqueia entendimento] A tela não explica o próprio modelo

Nada define o que é uma *rule*, um *bound*, um *override*, nem o que os três
níveis (`propose_only`, `act_on_low_risk`, `act_and_report`) permitem
concretamente. O operador que precisa decidir "deixo o agente reiniciar um
container sozinho?" não encontra aqui o vocabulário para expressar isso. Uma
introdução de três linhas + descrição por nível no select (não slugs).

### 4. [bloqueia entendimento] Revogar override exige digitar o nome de cabeça

"Revoke an override — Name of the override [input]" sem lista dos overrides
ativos. A lista deve existir com botão de revogar por item; o campo livre só
faz sentido quando houver override que a lista não mostre (não há).

### 5. [bloqueia entendimento] Relação com o "Stop automation" da topbar

O botão global de parada e esta tela controlam o mesmo eixo e não se
referenciam. Se parar/retomar é uma *freeze* de política, ela deveria aparecer
aqui como estado ("Automação parada por X desde Y — retomar").

### 6. [polimento] "Grant an override" com campos crus

Name (de quê? convenção?), Seconds (optional) sem unidade amigável (usar
presets: 1h/8h/24h/custom), Reason sem dica de que aparece no audit.

## Critérios de aceite

- Nenhum heading quebrado; um único empty state quando não há política.
- Os três níveis têm descrição legível no ponto de escolha.
- Overrides ativos são listados e revogáveis por clique.
- O estado do botão global de automação é visível nesta tela.
