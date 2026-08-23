# Plano — 052 Primeira execução no console

## O que já existe para construir em cima

Mais desta tela existe do que a primeira leitura da spec sugere:

- **O dashboard renderiza honestamente em zero.**
  `console/src/surfaces/screens/dashboard.tsx` já mostra seis painéis com
  estados vazios que nomeiam a próxima ação ("um deployment em que ninguém
  conectou nada é novo, não quebrado" — a docstring do próprio módulo). A
  metade "dashboard sempre visível" do modelo revisado é o comportamento
  atual; nada se redireciona hoje.
- **O console já escreve, de duas maneiras.** Ações não-secretas passam pelo
  padrão `act()` (`console/src/live/act.ts`) postando para as próprias rotas
  Next do console — `console/src/app/api/{run,answer,decision,preview,session}/
  route.ts` — que proxificam para o gateway com a credencial de sessão.
  Segredos deliberadamente não: `console/src/surfaces/credential.tsx`
  (`CredentialField`) é um campo somente-escrita cuja docstring descarta tanto
  renderizar um segredo armazenado quanto rotear um através do processo do console, e
  posta direto para `apiOrigin()`.
- **O gatilho "teste agora" existe.** `console/src/live/investigate.tsx`
  (`InvestigateDrawer`) inicia uma investigação de qualquer tela via
  `RUN_ENDPOINT`; a "descrever um incidente e ver a investigação rodar" da spec é esta
  gaveta mais uma linha de advertência visível.
- **O endpoint de checklist existe e 051 o estende** —
  `GET /v1/setup/checklist` (`gateway/http/routes/first_run.py:101`) com
  `state`, `detail`, `action` por passo, mais o estado de provider de 051 e
  detalhe por integração.
- **Disciplina de estado vazio existe**: a prop `empty` de `Panel` com
  heading/body/action, usada por todos os 14 screens.

O que não existe: forma alguma para setup de provider/model/integração, o
painel de checklist, o overlay de tutorial, e um lugar na navegação para
"primeiros passos".

## Documentos de design que esta feature obedece

- **D3 §1 (Painel)**: três faixas em ordem fixa; a faixa de atenção é a
  única que pode desaparecer; figuras zeradas visíveis; checklist na coluna
  direita; "investigar" sempre no header. A ordenação atenção-primeiro do
  dashboard atual já combina; a coluna de checklist e ação de header são o delta.
- **D2 navegação**: "Primeiros passos" aparece enquanto a checklist está aberta
  e deixa a nav quando fecha, permanecendo acessível em configurações.
- **D1**: todos os formulários novos usam os tokens existentes e densidade; inputs secretos são
  `type="password"`, `autocomplete="off"`; sem literals de cor novos — os
  testes de design-token já forçam isso.

## Escopo, mapeado para código

### 1. A área de primeiros passos

Uma nova entrada em `AREAS` (`console/src/shell/routes.ts`) — id `first-run`, path
`/first-run`, permissão `config.read` — **dentro do shell**, nunca um
alvo de redirecionamento. Sua regra de visibilidade é nova: `visibleAreas` atualmente filtra
apenas em permissão; ganha um hook `visible?(context)` por área então esta
área também pergunta "a checklist está completa". A regra D2 ("aparece e
desaparece") vive aqui. A tela em si é o wizard passo por passo.

**Decisão — o reagrupamento de navegação de três zonas D2 acontece nesta feature.**
Nenhuma outra spec a possui; esta é a feature que introduz o único item nav
cuja presença é condicional, e retrofitar o reagrupamento depois moveria
o grupo de cada tela duas vezes. `NAV_GROUPS` se torna `['now', 'environment',
'settings']` com a atribuição D2; as linhas de catálogo i18n mudam; os
testes sidebar/palette/deep-link que enumeram `AREAS` continuam passando porque
enumeram em vez de hard-code. Features 059–062 então encaixam seus itens
em `settings` sem tocar a estrutura.

### 2. Os passos do wizard

Um passo por tela, lista de passos visível, passos completados reabrindo. Cada
passo é um formulário postando para uma rota que 051 construiu:

| Passo | Lê | Escreve |
|---|---|---|
| provider | `GET /v1/providers` (display_name, local/hosted, guidance) | — |
| credential | `GET /v1/providers/{id}` field specs | `PUT /v1/integrations/{id}/credential` (direto ao API origin) |
| model | `models` / `default_model` do provider | `PUT /v1/config/{node_id}` (seção models) via o padrão proxy de preview-then-save existente |
| integrations | `GET /v1/integrations` catálogo + `GET /v1/config/{node_id}/integration-schemas` | rota de credencial por integração |
| verify | — | `POST /v1/providers/{id}/verify`, `POST /v1/integrations/{name}/verify` por coisa configurada, uma linha de resultado cada, retentável |
| estate / alerts | passos de checklist apontando para superfícies 053 / 055 | — (links; essas features possuem os formulários) |

Falha em uma integração continua para as outras e reporta ao final —
o espelho do console do contrato `setup_many`
(`surfaces/cli/wizard/integrations/__init__.py:115`), e uma falha de verify
nomeia o campo pulado quando essa é a causa (`SetupOutcome.skipped`
o carrega; as rotas de 051 o expõem).

**Decisão — como o navegador autentica a escrita de credencial direta.**
`CredentialField` já posta um formulário nativo para `apiOrigin()`, que só
autentica se o gateway aceita a sessão do console. Esta feature torna
aquela assunção explícita e real: as rotas de credencial aceitam o cookie
de sessão do console (CORS com escopo, permissão `credential.write` verificada contra
o principal da sessão), mantendo o segredo fora do processo do console.
A alternativa — proxificando através de uma rota Next — foi rejeitada porque
coloca o segredo em um segundo processo, que a própria doutrina de `credential.tsx`
e o Artigo IV ambos proíbem. `CredentialField` é rfiado da sua ação
placeholder (a rota verify) para a rota de credencial real, submissão se move
de post de formulário nativo para `fetch` então a resposta pode renderizar validação
por campo sem navegação de página, e o componente mantém suas propriedades
"nunca semeado, nunca ecoado".

### 3. Adições ao dashboard

- **Painel de checklist** na coluna direita: lê `/v1/setup/checklist`
  através de `panelRead`, renderiza cada passo com seu `state` e o
  passo pendente como um link em `/first-run` naquele passo. Desaparece quando
  `complete: true`.
- **Aviso de nenhum provider acionável**: quando a checklist diz nenhum provider, o
  dashboard mostra uma linha de aviso ligando para o wizard — dentro da página,
  nunca uma porta na frente.
- **Painel de ações rápidas**: três links (carregar conhecimento → `/knowledge`,
  configurar o agent → `/configuration` até que 060 aterrisse sua tela, ver
  memória → `/memory`).
- **Ação de investigação do header**: o gatilho `InvestigateDrawer` se move
  para/permanece na topbar do shell (`console/src/shell/topbar.tsx`) então fica
  em cada tela; a gaveta ganha a linha de advertência sobre integrações não-configuradas.

### 4. O overlay de tutorial

Um componente cliente descartável sobre o dashboard: indicador de progresso,
"Pular" visível, cinco slides (o que a plataforma faz, como investigação funciona,
o que conectar, ajustar o agent, testar antes de contar). **Decisão —
o estado de descarte é por-deployment, não por-navegador**: armazenado via
o caminho de escrita de config como uma pequena configuração de console-surface, porque a
regra de retomabilidade da spec ("o estado mora no deployment") se aplica ao tutorial tanto
quanto ao wizard; uma flag de localStorage mostraria o tutorial de novo a cada
máquina nova. Mostrado apenas enquanto a checklist está incompleta, então uma
flag obsoleta nunca pode prender um deployment configurado atrás de um overlay.

### 5. Retomabilidade e acordo entre superfícies

Nenhum estado de wizard no navegador. O passo atual é *derivado* da
checklist (`next` field), então matar o navegador e retornar resume
corretamente por construção, e `ninjasre onboard` contra o mesmo deployment
move a mesma checklist — aceitação 5 cai da fonte única de 051
em vez de ser construída aqui.

## O que esta feature NÃO faz

- Sem forma de onboarding de estate (053), sem ordenação de integração dirigida por
  observabilidade (054 adiciona "relevante primeiro"), sem instruções de ingresso
  de webhook (055, superficiado na tela de 062).
- Sem editor de configuração além da escrita de model do wizard (058).
- Sem rotas novas no gateway. Se um passo do wizard encontra uma rota faltando, isso é
  um defeito de 051, corrigido lá.
- Sem SSO, sem gerenciamento de token (058).

## Verificação de constituição

- **IV** — o caminho browser→gateway do segredo contorna o processo do console;
  o teste de varredura percorre HTML renderizado, payloads RSC, logs do processo
  do console e respostas pela sentinela. Inputs secretos são somente-escrita per
  contrato existente de `CredentialField`.
- **III** — tudo aqui é um humano preenchendo formulários; nada concede ao
  agent qualquer coisa.
- **VI** — nove providers renderizados com peso igual, local incluído, a partir
  dos descritores; sem ramificação específica de provider no wizard.
- **VIII** — console fala apenas HTTP para o gateway
  (`make check-console-boundary` se mantém).
- **XII** — testes de componente primeiro (vitest, `console/tests/unit/surfaces/`),
  teste de fluxo e2e em `console/tests/e2e/`.
- Outros não afetados.

## Raio de impacto

`routes.ts` (sign-in guard, role matrix, deep-link test, palette todos
o enumeram — se adaptam automaticamente mas seus snapshots se movem);
`dashboard.tsx` (baselines visuais re-capturadas); `topbar.tsx`; catálogos i18n
(`console/src/i18n/` — o teste de nome bidirecional forçará cobertura de
mensagem completa); `credential.tsx` (2 call sites em catalogue.tsx).
