# 030 — First steps: o funil de onboarding não fecha

> **Estado (2026-08-12, fim do dia):** F1–F4 corrigidos no working tree com
> test-first (console: nó raiz como fallback, patch aninhado, leitura aninhada
> do `modelChosen`, erros do preview exibidos, couriers com `reason` sempre
> textual; gateway: verify testa o modelo configurado). O tour (spec 001) e o
> `/v1/proposals` (spec 034) também foram corrigidos. **F5 e F6 permanecem
> abertos** — F5 exige um store de verificação que hoje não existe
> (`integration_health` nunca é composto; ver "Design do F5" abaixo), e F6 é a
> decisão de escopo sobre compor o runtime a partir da configuração.

A tela mais importante do produto em pré-alfa — e, após a segunda revisão
(com teste de ponta a ponta: preview, save via API, verify e disparo de
investigação real), a conclusão é dura: **o checklist é inconcluível e o
ciclo de valor não fecha por seis defeitos independentes**, todos
reproduzidos e com causa-raiz localizada no código.

## A cadeia do funil (reproduzida em 2026-08-12)

### F1. [quebrado] O passo "Choose a model" envia `nodeId=''`

A sessão do admin local não tem `team_node_id`, então `viewer.teamNodeId`
resolve para `''` (`console/src/session/viewer.ts`) e
`first-run.tsx` passa esse vazio ao `ModelStep`
(`console/src/surfaces/screens/first-run.tsx:116,461`). Os couriers
`/api/preview` e `/api/config` rejeitam `nodeId === ''` com **400 e corpo
`{}`** — que a UI renderiza como **"The deployment refused:"** sem nada
depois. Como o Save é deliberadamente bloqueado até um preview bem-sucedido
(`first-run/model.tsx`), o passo trava aqui para sempre.

É a mesma classe de defeito da spec_v3 050 (chamar sem resolver o nó): a
correção é o first-run cair para o nó raiz da árvore quando a sessão não
declara um — o padrão que `/configuration` já usa.

### F2. [quebrado] O patch usa chaves achatadas que o schema recusa

Com o nó correto (`default`), o preview responde
`errors: [{message: "is not a configuration field"}]` para
`models.investigator.provider` e `.model` — as constantes de
`first-run/plan.ts:71-72` são **chaves pontilhadas literais**, e o
config service espera **estrutura aninhada**
(`{models: {investigator: {provider, model}}}`, verificado: o formato
aninhado passa com `accepted: true` e o write persiste). Dois agravantes:

- O `ModelStep` **ignora o campo `errors` do preview** (`changesOf` só lê
  `changes`) — então, corrigido F1, o preview mostraria "mudaria X → Y"
  enquanto o save recusaria as mesmas chaves.
- O write devolve a recusa num formato que o courier não traduz
  (`detail` não-string → `reason: ""`), então **toda** recusa do gateway
  chega à UI como erro vazio.

### F3. [quebrado] O passo nunca é reconhecido como concluído

`readSetup` decide `modelChosen` com
`field(values, 'models.investigator.model')`
(`first-run/plan.ts:203`), e `field()` é um `Reflect.get` **plano**
(`surfaces/read.ts:136`) sobre um documento **aninhado**. Verificado ao
vivo: com `models.investigator.model = gemini-2.5-flash` salvo e visível na
configuração efetiva, o checklist continua listando "Choose a model" como
pendente. Mesmo consertando F1/F2, o funil não avança.

### F4. [quebrado] O verify testa o modelo errado

`POST /v1/model-providers/{id}/verify` → `verify_model` → `preflight()` sem
`model_id` → `resolve_binding` usa o **default do registry**
(`gemini-pro-latest`), nunca o modelo configurado
(`gateway/http/routes/providers.py:230`, `core/llm/preflight.py:267`).
Verificado ao vivo: com `gemini-2.5-flash` salvo, o check continua
respondendo *"'gemini-pro-latest' did not call the tool"* e recomendando
"choose a model that supports tool calling" — **o operador que obedece à
recomendação recebe o mesmo erro para sempre**. O check precisa ler o
modelo do ConfigService (ou aceitar `model_id` no request e o console
enviá-lo).

### F5. [quebrado] Resultado de verificação não persiste

Checks bem-sucedidos (prometheus e proxmox: "It answered", verde) voltam a
"Nobody has checked this one" ao recarregar a página, e o painel "What is
set up so far" diz "stored, unchecked" até durante a sessão em que o check
passou. O passo "Check that each of them works" não tem, portanto, como
ser marcado concluído. Persistir o resultado (com quem/quando) do lado do
deployment.

### F6. [bloqueia o produto] O runtime do investigador está fora do mapa

Mesmo com modelo configurado e credencial válida, disparar uma investigação
falha instantaneamente com `InvestigatorNotConfigured: Set
NINJASRE_INVESTIGATOR to 'module:factory'` — o runtime é composto por
**variável de ambiente do processo**, e:

- nenhum passo do checklist cobre "o runtime está composto";
- o self-check da tela não o reporta como pendência acionável;
- a UI promete que completar o checklist leva à primeira investigação, o
  que é falso neste deployment.

Decisão de escopo necessária: ou o deployment padrão **compõe o runtime
automaticamente** quando provider+modelo+credencial existem (preferível — a
informação de composição já está toda na configuração), ou "runtime
composto" vira um item explícito do checklist com a instrução de deploy, e
o botão Investigate fica desabilitado com o motivo enquanto faltar.

## Design do F5 (levantado, não implementado)

Não existe onde gravar um resultado de verificação: `GatewayState` não tem o
campo `integration_health` que `first_run.py:131` e `integrations.py:225` leem
por `getattr(..., None)` — na composição shipped é sempre `None`, então
"verified" nunca acende, por construção. O caminho completo:

1. **Port novo** (`platform/persistence/ports/`): `VerificationLedger` —
   resultado por integração/provider (verdict, detalhe, quem, quando), upsert
   e leitura por escopo.
2. **Migração + repo Postgres** (padrão de `0008_remediation_ledger`), fake
   para testes.
3. **Escrita**: `POST /v1/providers/{id}/verify` e
   `POST /v1/integrations/{name}/verify[/report]` gravam o resultado.
4. **Leitura**: `build_checklist` recebe `verified_integrations` do ledger;
   o painel "What is set up so far" e o Catalogue leem o mesmo registro.

## Problemas de UX que permanecem (da primeira revisão)

- Verify lista "Google Gemini" e "google_gemini" como itens duplicados.
- Modelo default do dropdown (`gemini-pro-latest`) falha o próprio verify;
  a lista não indica quais opções passam.
- "4 of 7 done" aqui vs "3 of 7 steps left" no dashboard.
- Marcadores de progresso quase idênticos para feito/pendente; sem "você
  está aqui"; sem estado final celebrando a conclusão com CTA de primeira
  investigação.
- Nomes de passo poéticos sem mapa para telas ("Give it an estate to
  watch").
- Coluna direita subaproveitada; erros sempre em uma linha vermelha crua.

## Critérios de aceite

1. Um admin recém-logado, sem `team_node_id`, completa **todos os sete
   passos** só pela UI, sem tocar em API ou terminal (F1–F5).
2. Preview e save do modelo usam o mesmo patch e o mesmo resultado; um
   preview com `errors` os exibe e não habilita o save.
3. Toda recusa do gateway chega à UI com o motivo textual (nunca
   "refused:" vazio).
4. O verify testa exatamente o modelo configurado e diz qual testou.
5. Resultado de check sobrevive a reload e aparece em "What is set up so
   far".
6. Com o checklist completo, "+ Investigate" produz um run que **executa**
   (ou o produto diz, antes do clique, o que falta no deployment).
