# 032 — Configuration

O schema inteiro do deployment renderizado como um formulário único. É a tela
que mais claramente mostra a máquina por dentro — no mau sentido.

*Auditada em duas passadas: leitura completa do texto renderizado e teste de
interação (colapso de seções, expansão da configuração efetiva, edição de
campo, preview e diff — sem salvar).*

## O que funciona e deve ser preservado

- **O fluxo preview→diff→save.** Editar um campo, clicar "Preview this change"
  e receber a tabela SETTING / NOW / AFTER SAVING antes de o botão Save
  existir é o comportamento certo para configuração com herança. A fundação é
  boa; os problemas abaixo são de acesso a ela.
- **Seções são colapsáveis** e a configuração efetiva **expande para JSON
  formatado** legível.
- Campos definidos mostram valor e proveniência com "Remove this override".

## Problemas

### 1. [bloqueia entendimento] Docstrings internas vazam para a UI

Os textos de ajuda dos campos são as docstrings do schema, verbatim,
incluindo:

- Referências a especificações internas: *"Off by default, which is
  **FR-008**"*, *"Article III says..."*, *"the thing Article II rules out"*.
- Caminhos de código: *"(``platform/config_service/merge.py``)"*, com crases
  de reST não renderizadas (visível também em `agents.operating_context`,
  `policies.sso`, `surfaces.notification_policy`).
- Ensaios de 8+ linhas por seção, escritos para o revisor do schema, não para
  quem preenche o formulário.

Além de inutilizável como ajuda, contraria a própria regra do repositório de
não citar FR/artigos em artefatos entregues. **Correção:** o schema ganha dois
textos por campo — `help` (1–3 linhas, para a UI) e a docstring longa (para o
código). A UI só mostra `help`; o racional pode viver atrás de um "saiba
mais".

### 2. [bloqueia entendimento] Tudo expandido, salvar mora a quilômetros

~30 seções e ~120 campos numa coluna única. As seções colapsam, mas vêm todas
**expandidas por padrão** (e o estado não persiste entre visitas); não há
sumário lateral, âncoras nem busca de campo. O "Preview this change" fica no
fim absoluto da página: o fluxo real de edição é *editar no meio → rolar tudo
→ preview → save*. Correções: seções colapsadas por padrão (ou memorizadas),
sumário lateral fixo, busca por nome de campo, e barra sticky de
preview/save que aparece quando há edição pendente.

### 3. [bloqueia entendimento] Campo não definido esconde o default efetivo

"Set at nothing yet" sob ~80 campos, e no diff do preview a coluna NOW vem
**vazia** para um campo não definido — quando o que vale hoje é o default do
deployment. O operador nunca vê o valor efetivo de um campo que não
customizou (a tela The agent tem o mesmo defeito com os budgets "0"). Padrão
por campo: "usando o padrão: `<valor>`" + origem + ação de override.

### 4. [bloqueia entendimento] Proveniência "Set at default" é ambígua

O nó raiz se chama `default`, então a proveniência "Set at default" lê-se
como "é o valor padrão" — o oposto do que significa (há um override, gravado
no nó `default`, removível). Junto com "Set at nothing yet", as duas frases
formam um vocabulário de proveniência que exige engenharia reversa. Propor:
"padrão do deployment" / "definido em: <nome do nó>" — e nunca batizar um nó
de "default".

### 5. [polimento] Configuração efetiva: colapso críptico e badge UNKNOWN

As linhas colapsadas mostram JSON truncado numa linha; expandido fica bom.
O badge "UNKNOWN" na coluna SET AT não é explicado em lugar nenhum (é o
provider da proveniência que não sabe o nó de origem?). Resolver a origem ou
remover o badge.

### 6. [polimento] Rótulos gerados

"EVALUATED 1 / EVALUATED 2" como títulos das entradas de integração ativas
(o campo Name mostra o valor certo — `proxmox` — mas o título do card é o
slug de avaliação); toggles "Enabled" sem objeto quando lidos isolados.

### 7. [estrutural] Esta tela compete com as telas dedicadas

Autonomy, Team context, Data (transit/destinos), Detectors (observation),
Administration (SSO) têm, cada uma, sua seção duplicada aqui — dois caminhos
de escrita com UX diferentes para o mesmo dado. A spec 090 propõe:
Configuration é a vista avançada (todas as chaves, proveniência, raw
override); seções com tela própria linkam para a tela própria.

## Critérios de aceite

- Nenhum FR/artigo/caminho de arquivo/reST visível na UI.
- Chegar a qualquer campo por sumário ou busca em < 5 s.
- Todo campo não definido mostra o default efetivo que está valendo.
- Editar qualquer campo torna preview/save alcançáveis sem rolar a página.
- A proveniência distingue, sem ambiguidade, "padrão" de "definido no nó X".
