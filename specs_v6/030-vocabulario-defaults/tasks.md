# Tasks: Vocabulário sem cru e defaults seguros de token

**Input**: Design documents from `specs_v6/030-vocabulario-defaults/`

**Prerequisites**: plan.md, spec.md, e a **020 entregue** — a suíte transversal
(`console/tests/e2e/transversal-rules.spec.ts`) e o seu mecanismo de exceção por
rota nascem lá; esta feature é a primeira a remover exceções dela.

**Tests**: test-first. O teste da tarefa entra antes da implementação e o
**vermelho é confirmado e registrado** no `controle.md` com a mensagem de falha
observada. Um teste que nunca falhou não provou nada.

**Regra de escrita nos arquivos committed**: nenhum teste, comentário, docstring
ou mensagem de commit desta feature cita identificador de requisito, artigo da
constituição, número de feature ou caminho de planejamento. A substância vai no
arquivo; a referência fica nesta spec.

**Convenções**: `[P]` = paralelizável (arquivos distintos, sem dependência).
`[US1]`/`[US2]`/`[US3]` = a história que a tarefa serve.

---

## Fase 1: Descoberta e insumos

- [x] **T001** **Descoberta — o que o gateway já sabe fazer sobre criar pessoa.**
      Levantar, com evidência em `file:line`, se existe caminho HTTP para criar
      um principal com senha local: percorrer `gateway/http/routes/identity.py`
      (hoje `GET /identity/principals` devolve `UserList`; não há criação
      aparente), `platform/identity/local_accounts.py` (a conta local é
      configurada por ambiente e o `_ensure_principal` faz `upsert_user`), o port
      de identidade (`upsert_user`, `upsert_role_binding`) e o cliente do console
      (`surfaces/console/client.py`). Produzir um veredito de uma linha —
      **"existe rota"** ou **"não existe rota"** — com os caminhos que o
      sustentam, e registrá-lo no `controle.md`. **Bloqueia T025**; nenhum
      desenho de endpoint antes deste veredito.
- [x] **T002** [P] **Descoberta — o que o servidor faz hoje com uma emissão sem
      escopos.** Chamar a emissão de token sem o campo de permissões e registrar
      o comportamento observado (token vazio? token com tudo? recusa?), contra
      `platform/identity/tokens.py`. O resultado decide se T012 é correção ou
      caracterização. Registrar no `controle.md`.
- [x] **T003** [P] **Fixtures.** Um principal do tipo conta de serviço e um do
      tipo pessoa, um inativo; um grupo de tokens com último uso e outro nunca
      usado; uma sugestão do estate cujo recurso tenha nome e localização
      resolvíveis e outra cujo recurso só tenha identificador; uma sessão ativa.
      Reaproveitar `fixtures/scenarios/` onde já houver, criar só o que faltar.

## Fase 2: Acceptance-first (abre a fase de testes)

- [x] **T004** **Acceptance spec, vermelho confirmado.** Escrever
      `console/tests/e2e/vocabulary-defaults.acceptance.spec.ts` (nome corrigido
      pelo operador antes desta rodada — sem o número da feature, que apontaria
      para `specs_v6/`, gitignored; **este arquivo ainda não existe nesta
      árvore** — ver `controle.md`) codificando as alegações normativas antes de
      qualquer tela mudar:
      - Machine tokens abre com **zero** caixas de escopo marcadas;
      - o template "Alert delivery" marca exatamente uma caixa, a de
        `webhook.deliver`, e nenhuma outra;
      - marcar um escopo destrutivo revela o aviso que nomeia o que ele permite;
      - os escopos aparecem em grupos nomeados, não numa faixa única;
      - Members & roles oferece a ação primária de criar pessoa a quem pode
        escrever em identidade, e não a oferece a quem não pode;
      - nenhuma das rotas cobertas exibe `SERVICE_ACCOUNT`, `HEALTHY`,
        `policies.`, `surfaces.`, `models.investigator`, `webhook.deliver` ou um
        identificador `res-` no texto visível;
      - a sessão ativa se identifica por dono e origem, não por um número solto.
      Rodar e **registrar o vermelho** de cada alegação. Viewport declarado no
      próprio spec quando a alegação medir espaço.

## Fase 3: US1 — Um token de máquina nasce sem poder nenhum (P1)

- [x] **T005** [US1] Teste de unidade do formulário de emissão
      (`console/tests/unit/surfaces/machine-token-groups.test.tsx`): montado com
      um emissor que possui todos os escopos, **nenhuma** caixa vem marcada.
      Vermelho confirmado contra `machine-token-groups.tsx:148`
      (`useState(new Set(issuedScopes))`).
- [x] **T006** [US1] Implementar o default vazio no formulário. T005 passa.
- [x] **T007** [US1] Teste de unidade dos templates de finalidade: "Alert
      delivery" seleciona exatamente `webhook.deliver`; "Read-only automation"
      seleciona só escopos de leitura; escolher um template não impede o ajuste
      manual em seguida. Vermelho confirmado.
- [x] **T008** [US1] Implementar os templates como constantes nomeadas no módulo
      que possui o formulário — nome, frase de propósito, conjunto de escopos.
      Nenhum literal de escopo espalhado pelo ponto de uso. T007 passa.
- [x] **T009** [US1] Teste de unidade do agrupamento por domínio: os escopos
      chegam à tela em grupos nomeados, derivados do próprio nome do escopo, e
      todo escopo do emissor cai em exatamente um grupo. Vermelho confirmado.
- [x] **T010** [US1] Implementar o agrupamento. T009 passa.
- [x] **T011** [US1] Teste de unidade do aviso de escopo destrutivo: marcar
      `Org Delete`, `Owner Assign` ou `Impersonation Use` revela um aviso que
      nomeia o que aquele escopo permite; desmarcar o retira; o aviso nunca
      desabilita a emissão. Vermelho confirmado.
- [x] **T012** [US1] Implementar o aviso, com o conjunto de escopos destrutivos
      como constante nomeada no módulo dono. T011 passa.
- [x] **T013** [US1] Teste de contrato no servidor (`tests/contract/…` ou
      `tests/unit/platform/identity/`, conforme o veredito de T002): uma emissão
      sem escopos declarados produz um token **sem escopo nenhum**; uma emissão
      com escopos produz exatamente aqueles; o teto do emissor continua valendo.
      Vermelho confirmado se o comportamento atual divergir; se já estiver
      correto, o teste é a caracterização que impede a regressão — e o
      `controle.md` diz explicitamente qual dos dois casos ocorreu.
- [x] **T014** [US1] Implementar a garantia em `platform/identity/tokens.py`, se
      T013 falhou. T013 passa.

## Fase 4: US2 — O produto fala uma língua só (P1)

Cada vazamento é um par teste→implementação. Os pares de arquivos distintos são
paralelizáveis entre si; os que tocam `members.tsx` são sequenciais.

- [x] **T015** [US2] Teste: a chip resolve o rótulo antes de renderizar — um tipo
      de principal `service_account` aparece como "Service account" e um estado
      de conta ativa como "Active"; um estado que o console nunca ouviu continua
      exibido, sem virar rótulo gritado. Vermelho confirmado contra
      `console/src/components/status.tsx` (renderiza `presented.label` sob a
      classe `uppercase`).
- [x] **T016** [US2] Implementar em `console/src/components/status.tsx` +
      `console/src/design/status.ts` o vocabulário de tipo de principal e de
      estado de conta, e aplicá-lo em `console/src/surfaces/settings/members.tsx`
      (linhas 139 e 140 de hoje). T015 passa.
- [x] **T017** [P] [US2] Teste e implementação do chip do grupo de token: o
      literal fixo `<Badge status="healthy" />`
      (`console/src/surfaces/machine-token-groups.tsx:337`) vira o fato que o
      painel já tem — "In use" quando há último uso registrado, "Never used"
      quando não há. Vermelho antes.
- [x] **T018** [P] [US2] Teste e implementação do preview do wizard: o campo
      aparece pelo nome de exibição, não como `models.investigator.model` /
      `models.investigator.provider` (`console/src/surfaces/first-run/plan.ts:94-95`,
      renderizado por `console/src/design/resolution-preview.tsx`). Vermelho antes.
- [x] **T019** [P] [US2] Teste e implementação dos títulos de seção técnica: o
      cabeçalho de `console/src/surfaces/advanced-config-section.tsx` deixa de
      receber um prefixo de schema como título nas telas de Autonomy
      (`policies.masking.`, `policies.guardrails.`, `policies.approvals.`,
      `policies.autonomy.`) e Notifications (`surfaces.notification_policy.`).
      **Só o título**: a estrutura dessas páginas pertence a outra feature da
      onda e não é tocada aqui. Vermelho antes.
- [x] **T020** [P] [US2] Teste e implementação do trust em Alert intake: no lugar
      de "Trusted by" + `webhook.deliver` (`console/src/i18n/en.ts:1312` e
      `console/src/app/api/delivery-token/route.ts:28`), a fonte nomeia o
      delivery token e oferece a rotação na própria tela. Vermelho antes.
- [x] **T021** [P] [US2] Teste e implementação da evidência da sugestão do
      estate: `catalogue.integrations.suggested.evidence` deixa de interpolar o
      identificador cru do recurso no texto e passa a nomeá-lo de forma legível
      (nome do serviço e localização); o identificador fica no destino do link.
      A borda do recurso sem nome resolvível é caso de teste. Vermelho antes.
- [x] **T022** [US2] Teste e implementação da identificação de sessão em
      `console/src/surfaces/tokens.tsx` (painel de sessões) e no mapeamento de
      `members.tsx`: dono e origem/dispositivo quando conhecidos; o identificador
      técnico sai da face principal e permanece em contexto técnico. Vermelho
      antes. Depende de T016 (mesmo arquivo).
- [x] **T023** [US2] Teste e implementação da ajuda do grant: o papel escolhido é
      descrito por resumo humano, com a lista completa de permissões atrás de uma
      expansão, no lugar da linha de ids que hoje sai de
      `members.tsx:88` para o seletor de `console/src/surfaces/grants.tsx`.
      Vermelho antes. Depende de T016.
- [x] **T024** [US2] Cada grant listado nomeia o papel de forma legível, pelo
      mesmo vocabulário do seletor que o concede. Teste antes.

## Fase 5: US3 — Criar uma pessoa sem sair da tela de pessoas (P2)

A forma desta fase é decidida por **T001**.

- [x] **T025** [US3] Teste de contrato da criação de principal com senha local:
      quem tem permissão de escrita em identidade cria; quem não tem recebe
      recusa **do servidor**, não apenas um botão escondido; a criação aparece no
      audit. Vermelho confirmado. Se T001 disse "existe rota", este teste
      caracteriza a rota existente; se disse "não existe rota", ele é o vermelho
      que a rota nova vai apagar.
- [x] **T026** [US3] Implementar o lado do servidor conforme T025 — superficiar a
      operação existente ou criar a rota em `gateway/http/routes/identity.py`
      sobre o port de identidade, sem SQL fora da camada de persistência. T025
      passa.
- [x] **T027** [US3] Teste da ação primária na tela: Members & roles oferece
      criar pessoa a quem pode escrever em identidade e não oferece a quem não
      pode; a pessoa criada entra na lista com o vocabulário da Fase 4. Vermelho
      confirmado.
- [x] **T028** [US3] Implementar a ação primária em
      `console/src/surfaces/settings/members.tsx`. T027 passa.

## Fase 6: Língua e a suíte transversal

- [x] **T029** Toda string introduzida ou alterada nas fases 3 a 5 existe em
      `console/src/i18n/en.ts` **e** em `console/src/i18n/pt-BR.ts`, no mesmo
      passo, com o vocabulário brasileiro (tela, arquivo, ação, salvar, excluir,
      ativar). Verificação de que nenhuma chave nova ficou em uma língua só.
- [x] **T030** **Remover os `fixme` de vocabulário da suíte transversal.** Em
      `console/tests/e2e/transversal-rules.spec.ts`, retirar as exceções por rota
      que cobrem os bans de vocabulário nas rotas que esta feature entrega, e
      rodar a suíte inteira verde sem elas. As exceções de outras naturezas
      (orçamento de rolagem em rotas de features futuras) **permanecem** — só o
      vocabulário cai aqui.
- [x] **T031** Em `console/tests/e2e/vocabulary.spec.ts`, retirar a ressalva que
      hoje isenta a tela de pessoas do ban de `HEALTHY` (a suíte a documenta em
      comentário como estado ativo/inativo de uma pessoa). Depois da Fase 4 essa
      isenção não tem mais causa, e mantê-la é deixar o buraco por onde o defeito
      volta.

## Fase 7: Polimento e prova

- [x] **T032** Acceptance spec (T004) inteiro verde contra build de produção.
- [x] **T033** Baselines visuais: atualizar `console/visual/screens.json` para as
      telas que mudam de face (`/settings/members-roles`,
      `/settings/machine-tokens`) e capturar a baseline **deliberadamente**,
      conferindo a captura antes de aceitá-la.
- [x] **T034** `console/tests/e2e/scroll-budget.spec.ts` verde: as duas telas
      tocadas continuam dentro do orçamento depois do agrupamento de escopos e da
      ação primária nova.
- [x] **T035** `make verify` completo (lint, format-check, typecheck,
      check-imports, check-constants, check-protocols, check-deps, suíte), mais
      vitest e Playwright behaviour. Qualquer gate não rodado é dito por escrito,
      com a razão.
- [x] **T036** Escrever `specs_v6/030-vocabulario-defaults/controle.md`: os dois
      vereditos de descoberta (T001, T002), o vermelho observado de cada teste
      test-first com a mensagem de falha, o que ficou fora e por quê, os gates
      rodados com resultado, e qualquer tarefa que não tenha sido test-first —
      nomeada como tal, sem eufemismo.

## Dependencies

- **T001 → T025 → T026 → T027 → T028** (a descoberta decide a forma da US3).
- **T002 → T013 → T014** (a descoberta decide se T013 é correção ou
  caracterização).
- **T004** antes de qualquer implementação: é a fase de testes que abre.
- **T005→T006**, **T007→T008**, **T009→T010**, **T011→T012** dentro da US1;
  os quatro pares são sequenciais entre si por tocarem o mesmo módulo.
- **T016 → T022, T023** (mesmo arquivo, `members.tsx`).
- **T017, T018, T019, T020, T021** paralelizáveis entre si.
- **Fases 3, 4 e 5** → **T029** → **T030, T031**.
- **T036** por último, depois de T035.
