# controle.md — 030-uma-fonte-por-fato

**RASCUNHO INCREMENTAL.** Escrito e atualizado ao longo da execução, não ao
final — ver a instrução do orquestrador. O estado abaixo foi verificado contra
o código no momento em que cada linha foi escrita; releia a seção "Progresso"
para saber até onde vai a verificação mais recente.

## Achado de ambiente, resolvido antes de qualquer trabalho de feature

A worktree designada para este slot (`worktree-agent-a7dc60493889a27e7`) foi
provisionada no commit raiz do repositório (`c789c2d`, "Add initial README"),
não na ponta da `master` (`928c342`, pós-merge S0+S1). `git log --oneline`
mostrava um commit só; `console/`, `gateway/`, `platform/` etc. não existiam no
disco. A worktree irmã do par deste slot (`worktree-agent-ad2b3b198c83bd6f6`)
estava corretamente na ponta de `928c342`.

Corrigido com `git reset --hard 928c342...` na própria branch da worktree
(`worktree-agent-a7dc60493889a27e7`) — sem trabalho real para perder, era só o
commit-raiz compartilhado por todo o histórico. Reportar isso ao orquestrador:
é um defeito de provisionamento, não uma decisão de conteúdo.

## Ledger (linha a linha) — estado até agora

Convenção de Estado: FEITO | FEITO (já existia, verificado) | PARCIAL |
NÃO INICIADO | Fora do escopo desta spec.

| Peça | Estado | Detalhe |
|---|---|---|
| T001 baseline `make verify` | FEITO (em validação) | Rodando; log em `/tmp/.../scratchpad/030/verify-before.log`. Chegou a 97%+ sem falha visível até aqui — número final e comparação vêm no fechamento da Phase 0. |
| T002 baseline latência | NÃO INICIADO | Depende do build de produção do console — sequenciado após a instrumentação (T005-T007) por eficiência, já que a mesma infraestrutura de contagem serve para medir "chegou requisição" nas duas frentes. |
| T003 estado de partida (telas com causa de vazio, vocabulário de prontidão, rotas dinâmicas) | PARCIAL | Confirmado por leitura de código: prontidão hoje tem 3 valores (`SETUP_READINESS_ABSENT/CONFIGURED/VERIFIED`, `config/constants/first_run.py:192-200`); nenhuma `page.tsx` sob `(shell)/` declara `dynamic` própria — só `console/src/app/(shell)/layout.tsx:31` declara `export const dynamic = 'force-dynamic'`. Contagem exata de telas com `setupCause` e lista completa de rotas ainda não tabulada em `evidence/`. |
| T004 diagnóstico da camada de cache real | NÃO INICIADO | Depende de T005-T007 (instrumentação) para ser medido honestamente, não hipotetizado. |
| T005 contador de requisições no mockplane | **FEITO** | `tools/mockplane/server.py`: `CONTROL_PATH_PREFIX`, `REQUEST_COUNTS_PATH`, `MockPlane._counts`, `request_counts()`, `_record_request()`, `_serve_control()`, resolvido antes de `match_request`. Teste unitário em `tests/unit/tools/mockplane/test_server.py` (8 casos novos). Vermelho confirmado via `git stash` da implementação (todos os 8 falharam por `AttributeError`/404 reais), depois `git stash pop` e verde: 45/45 passed. |
| T006 harness exporta endereço do backing | **FEITO** | `config/constants/console.py`: `NINJASRE_CONSOLE_BACKING_URL_ENV`. `tools/console_e2e.py`: `playwright(..., backing_url=...)` e `run()` passam o endereço do mock (nunca do compose, que não tem a rota de controle). Testes em `tests/unit/tools/test_console_e2e.py` (4 casos novos), vermelho real confirmado (`TypeError: unexpected keyword argument`, `assert None == '...'`) antes da implementação; 16/16 passed depois. |
| T007 gate de build reprova rota pré-renderizada | NÃO INICIADO (próximo) | |
| T008 acceptance spec da feature | NÃO INICIADO | Depende de T005-007 para os blocos que perguntam ao contador. |
| T009 ban transversal (negativa sobre painel em erro) | NÃO INICIADO | |
| T010-T020 unitários que fixam a verdade antes da mudança | NÃO INICIADO | |
| Phase 2 (verdade de estado do provider) | NÃO INICIADO | |
| Phase 2b (vocabulário de estado de run) | NÃO INICIADO | |
| Phase 3 (resolução de handle) | NÃO INICIADO | |
| Phase 4 (console) | NÃO INICIADO | |
| Phase 5 (staging) | NÃO INICIADO — é do orquestrador | |

## O que fica pendente, nomeado, não escondido

Tudo que não está marcado FEITO acima. Este é um rascunho inicial gravado cedo
por instrução direta do orquestrador (robustez contra perda de relatório), não
o estado final da feature.

## Descobertas até aqui

- A prontidão hoje deriva de dois booleanos (crachá "configured"/"verified"
  simples) em `platform/startup/checklist.py::_readiness` — confirma a
  necessidade do quarto valor que a Phase 2 introduz.
- `gateway/http/integration_access.py::compose_integration_access` liga
  sempre `team_id=CREDENTIAL_ORG_WIDE_TEAM` — confirma o seam descrito na
  spec (US6) antes de qualquer mudança.
- `console/src/design/status.ts::RUN_STATUSES` = `queued, running, waiting,
  succeeded, failed, cancelled`; `platform/persistence/ports/run_trace_store.py::RunStatus`
  = `running, suspended, completed, cancelled, failed, interrupted` — confirma
  exatamente a assimetria que a Phase 2b existe para corrigir.
- `console/src/surfaces/screens/incident-detail.tsx` hoje **suprime** o chip
  de investigação quando a leitura falha (`investigationChip = readFailed ?
  null : ...`, linha ~202-221) — confirma a decisão herdada descrita no
  briefing: suprimido, não mentiroso, mas também não "diz que não sabe".

Continuo atualizando este arquivo ao final de cada fase.

---

## Atualização — instrumentação de contagem TERMINADA e verificada (prioridade do orquestrador)

**Commits feitos** (3, por camada, working tree limpo):
1. `dd2d241` feat(mockplane): count requests per route and session
2. `492c23d` feat(console-e2e): export the mock backing's address to Playwright
3. `5662186` feat(console-gate): fail the build when a shell route is prerendered

### T005/T006 — a instrumentação está de pé

`tools/mockplane/server.py` conta requisições por `"METHOD path"` e por
sessão, servidas em `/__mockplane__/requests` (resolvida antes de
`match_request`, nunca contada ela mesma). `tools/console_e2e.py` exporta o
endereço do backing para o processo do Playwright via
`NINJASRE_CONSOLE_BACKING_URL` (nova constante em
`config/constants/console.py`) — só para o backing `mock`, nunca para
`compose` (que não tem a rota de controle).

Prova: 8 + 4 = 12 testes unitários Python novos, vermelho real confirmado via
`git stash` da implementação (`AttributeError`, `TypeError`, `404`s reais)
antes de implementar, depois `git stash pop` e verde (45/45 e 16/16).

### T004 — medição real da camada de cache, contra o backing de mock local

Build de produção real feito (`pnpm run build`), servido localmente
(`console/.next/standalone/server.js`) contra um `mockplane serve` real na
porta 8997, dirigido por um Chromium real via Playwright (script descartável,
apagado depois — nunca commitado). Medido com o contador que acabou de ser
construído:

| Forma de chegar a `/incidents` | Requisição chegou ao backing? |
|---|---|
| Primeira visita | **sim** (delta 1) |
| Reload duro | **sim** (delta 1) |
| Navegação suave (menu, vindo de `/runs`) | **sim** (delta 1) |
| Navegação suave **repetida** (já visitada antes, dentro da mesma sessão — o caso que um cache de roteador no cliente responderia sem nova requisição) | **sim** (delta 1) |

Também: `curl -I` no `/incidents` local mostra
`Cache-Control: private, no-cache, no-store, max-age=0, must-revalidate` — o
cabeçalho mais estrito possível contra qualquer cache intermediário.

E a saída do build de produção (`pnpm run build`, tabela de rotas que o
Next.js imprime) mostra **todas** as rotas sob `(shell)` como `ƒ (Dynamic —
server-rendered on demand)`, nenhuma como `○ (Static)` — confirmado também
pelo gate novo (`tools/console_gate.py dynamic-routes`), que lê
`.next/prerender-manifest.json` (o manifesto real do build, seu formato
confirmado por inspeção antes de escrever o check) e **passa hoje, sem nada
para corrigir**.

**Conclusão honesta, registrada como achado e não maquiada**: contra o
backing de mock local, com o build atual desta árvore, **não** encontrei o
defeito "lista congelada" que o diagnóstico da onda nomeou. As rotas já são
dinâmicas (build + medição ao vivo concordam), o cabeçalho HTTP já recusa
cache, e toda forma de navegação testada localmente produz uma requisição
real. Isso não invalida a observação do orquestrador em staging (zero
requisições a `/v1/incidents` e `/v1/runs` lá) — meu ambiente local não tem
o que o staging tem na frente do console (proxy reverso / ingress / CDN), e
essa é exatamente a camada que este worktree não alcança e não pode testar.
**Minha melhor hipótese, não verificada**: um cache de borda (reverse proxy
ou CDN) na frente do pod do console em staging, ignorando o
`Cache-Control: no-store` que a aplicação já envia — o que seria um defeito
de infraestrutura de deployment, não do código React/Next.js em si. Preciso
que o orquestrador confirme isso contra staging real (curl -I direto no pod
vs. através do proxy de borda, comparando os cabeçalhos que cada um devolve).

Isso muda a Phase 4c: T048 ("declarar dinamismo por rota, sem depender de
herança") ainda vale como blindagem defensiva — já vou aplicar, porque
FR-029/030/031 pedem isso categoricamente, não condicionalmente ao
diagnóstico — mas não é isso que vai mudar o comportamento observado em
staging, porque o comportamento já está correto até onde este worktree
alcança.

### O teste que prova, e o que pedir ao orquestrador para observar

O teste (a nascer no acceptance spec, próxima tarefa): carregar `/incidents`
localmente contra o mock, ler `/__mockplane__/requests` antes e depois, e
afirmar que subiu — exatamente o desenho do plano, agora com a
instrumentação por trás dele pronta e comprovada.

**O que o orquestrador precisa observar em staging, que eu não alcanço**:
`curl -I https://stg-ninjasre.lan.kyo.ninja/incidents` (e comparar com o que
o pod do console devolve direto, sem o proxy de borda no meio) — se o
`Cache-Control` chegar diferente do que a aplicação envia, a camada de
borda é a causa, e o remédio é infraestrutura de deploy, não código desta
feature.

Retomando o `tasks.md` na ordem: T008 (acceptance spec, vermelho antes de
qualquer tela) é a próxima parada.

---

## Atualização — acceptance spec (T008) escrito, vermelho confirmado, commitado

**Commit 4**: `94a8823` test(e2e): add the acceptance spec for one source per fact

`console/tests/e2e/030-uma-fonte-por-fato.acceptance.spec.ts` — 19 blocos de
teste reais (`test()`), cobrindo as alegações navegáveis; 6 alegações não
codificadas aqui (nomeadas no cabeçalho do arquivo, com o motivo: gate de
build, log de boot, auditoria de banco — nenhuma alcançável por um browser).

**Rodado de verdade** contra mock+console locais construídos nesta sessão
(não é inferência): `NINJASRE_CONSOLE_BASE_URL=... NINJASRE_CONSOLE_BACKING_URL=... pnpm exec playwright test tests/e2e/030-uma-fonte-por-fato.acceptance.spec.ts --project=behaviour`.

**Resultado real, final**: **2 falharam, 8 pularam (motivo nomeado), 9
passaram.**

As 2 falhas reais, mensagem capturada:
1. `the chip reads Unknown rather than being absent or asserting None` —
   `Error: expected an "Unknown" investigation chip; the incident header
   showed: Open` — **este é o defeito central que o orquestrador nomeou
   como decisão herdada**: o chip de investigação some (não aparece nem
   como "Unknown") quando a leitura do detalhe falha.
2. `the Unknown chip names the dependency that failed...` — mesma causa raiz.

As 9 que passaram já seguravam a alegação sem eu ter tocado nada — por
exemplo, o segundo reload de `/incidents` bate no backing de novo (a versão
mais fraca, honesta, da alegação de "fato novo aparece em um recarregamento",
já que o backing de mock não tem endpoint de criação de incidente e
`page.route()` não intercepta o fetch do lado do servidor — documentado no
próprio arquivo).

As 8 puladas, cada uma com motivo: checklist já completo no dataset padrão
(então `/first-run` redireciona e não há linha para ler), nenhum provider
não-verificado no dataset, nenhum provider sem crendencial no dataset,
precisa do projeto `first-day` (setup incompleto).

**Nenhum identificador de planejamento no arquivo** — varredura própria
confirmou (fiz essa varredura E ACHEI DOIS `AN-0X` que eu mesmo tinha
deixado num comentário; corrigidos antes do commit).

Próximo: implementar a correção do chip (o que já está provado vermelho
acima) — é o item mais concreto e de maior valor que resta, e fecha 2 das
próprias falhas deste arquivo.

---

## Atualização — correção do chip + subtítulo, allowlist 8 → 7, provado contra build real

**Commits 5, 6, 7:**
- `8562dd7` feat(console): the investigation chip says Unknown, not nothing
- `66a8918` docs(030): commit the running controle.md for this feature
- `dc61443` fix(console): stop repeating one placeholder across an incident's whole subtitle

### O que mudou

1. **`console/src/surfaces/read.ts`**: nova função `existenceOf(data, present)`,
   ao lado de `stateOf`/`dependencyOf`/`dataOf` — devolve `{kind:'unknown',
   dependency}` quando a leitura falhou, `{kind:'present'}` /
   `{kind:'absent'}` quando teve sucesso. Testada (2 casos novos em
   `behaviour.test.tsx`, vermelho real confirmado antes — `TypeError:
   existenceOf is not a function` — depois verde, 36/36).
2. **`console/src/components/status.tsx`**: `ResolvedChip` ganhou `title?`
   opcional (mesma técnica que `StatusChip` já usa para o texto "Unknown").
3. **`console/src/surfaces/screens/incident-detail.tsx`**: o chip de
   investigação agora deriva de `existenceOf(detail, hasInvestigation)` — 4
   estados reais (`running`/`finished`/`none`/`unknown`), o chip nunca mais
   é `null`. Estado `unknown` nomeia a dependência (`/v1/incidents/{incident_id}`)
   no tooltip (`title`). **E**: o parágrafo de subtítulo inteiro
   (`data-testid="incident-subtitle"`) some quando a leitura falha, em vez
   de cair no mesmo placeholder genérico em 2+ campos ao mesmo tempo.
4. **`console/src/i18n/en.ts` e `pt-BR.ts`**: `incident.chip.investigation.unknown`
   e `.unknown.explain`, nos dois catálogos.
5. **`console/tests/unit/surfaces/incident-detail.test.tsx`**: o teste que
   antes travava a garantia "só 1 chip quando a leitura falha" (a decisão
   antiga) foi **reescrito** para travar a nova: 2 chips, o segundo diz
   "Unknown", nomeia a dependência no `title`; mais um teste novo travando
   que o subtítulo não renderiza mais nada. 9/9 passam.
6. **`console/tests/e2e/transversal-rules.spec.ts`**: removida a entrada de
   `EXCEPTIONS` para `/incidents/{id}` × `two-placeholders`; comentário
   explicativo do bloco atualizado (contava "oito entradas", agora "sete";
   a frase sobre `/incidents/{id}` agora diz que a rota não carrega
   nenhuma das três regras).

### Prova contra o produto de verdade, não inferência

Rebuild de produção real (`pnpm run build`, confirmado `ƒ Dynamic` em toda
rota, gate `dynamic-routes` verde), servido localmente contra mock real
(portas 8996/8997, como nas rodadas anteriores). Rodei:

- `pnpm exec playwright test tests/e2e/transversal-rules.spec.ts --project=behaviour`
  → **38 passed, 14 skipped, 0 failed**. Os 14 pulados: 7 são a delegação de
  scroll-budget para `scroll-budget.spec.ts` (não é allowlist), **7 são as
  entradas de allowlist restantes** (confirmado contando os `test.fixme`
  pulados um a um: 3 markdown em `/`,`/runs`,`/runs/{id}`; 2
  identifier-as-name em `/runs`,`/runs/{id}`; 1 two-placeholders em `/runs`;
  1 live-control em `/runs/{id}`) — **nenhuma delas tocada por mim**, todas
  continuam vermelhas pela própria causa original, não maquiadas.
- Os 4 testes de `/incidents/{id}` (markdown, identifier-as-name,
  two-placeholders, negative-assertion) **passam, e três deles já não têm
  mais `test.fixme` nenhum guardando a passagem** — rodam de verdade.
- `pnpm exec playwright test tests/e2e/030-uma-fonte-por-fato.acceptance.spec.ts`
  → **11 passed, 8 skipped (motivo nomeado cada um), 0 failed** — as 2
  falhas do chip que eu tinha capturado antes agora passam.
- `pnpm exec vitest run` (suíte inteira do console) → **159 arquivos, 2672
  testes, todos passando.**

### A conta da allowlist, exatamente como o orquestrador pediu

**Estava em 8. Está em 7. Caiu exatamente 1: `/incidents/{id}` ×
`two-placeholders`.**

Prova de que caiu por conserto e não por cenário enfraquecido:
- O cenário que a viola é o mesmo de sempre — um id de incidente que não
  existe no fixture, a leitura de detalhe recusada pelo mock com 404. Não
  toquei no fixture, no dataset, nem no mecanismo de falha.
- O que mudou foi o **produto**: o subtítulo inteiro deixou de renderizar
  quando a leitura falha, em vez de cair no mesmo fallback em duas ou mais
  posições. O teste antigo (`test.fixme`) foi trocado por uma execução real
  que passa porque o defeito não existe mais, não porque o teste ficou mais
  fraco — o `twoPlaceholders()` detector em si não mudou uma linha.
- As outras 2 regras que já tinham caído nessa mesma rota (S1: identifier-
  as-name e negative-assertion) continuam caídas, e a entrada que sobrava
  citava (incorretamente, eu descobri e corrigi o comentário) que o
  conserto delas removeria esta também — não removeu; corrigi a causa raiz
  de verdade agora.

### Instrumentação de contagem — reconfirmado nesta rodada também

Os mesmos servidores locais (build de produção + mock real) usados para o
teste acima também serviram para reconfirmar, nesta rodada, os blocos
`loading /incidents / /runs / an incident detail emits at least one
request` do acceptance spec — **passam, contagem sobe de verdade a cada
load**, contra o build mais recente (com as correções desta rodada).

Nada mudou na conclusão já reportada: localmente, com este build, as
listas **não** estão congeladas — o defeito observado em staging precisa
de uma causa que só existe lá (proxy/CDN de borda é a hipótese mais forte,
não verificada).
