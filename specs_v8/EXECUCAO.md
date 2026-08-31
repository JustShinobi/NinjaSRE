# specs_v8 — Protocolo de execução: pares paralelos, staging e o gate visual

Herda o protocolo da v7 (`specs_v7/EXECUCAO.md`) integralmente — worktrees
isoladas por implementer, single-write com dono por slot, merge pelo
orquestrador com gates de fronteira, artefatos gerados regenerados e nunca
mergeados, arquivos fora do índice só na árvore compartilhada, staging um só
com deploy no fim do slot. Este arquivo declara o que muda: os pares desta
onda, o dono dos single-write, e o **gate visual com Orca browser** que a
decisão 7 do README exige. É também o opt-in que a skill `spec-wave` requer
para paralelizar.

## 1. Os pares

Regra de formação mantida: um lado backend-pesado × um lado console-pesado,
propriedade disjunta de arquivos.

| Slot | Executa | Racional da disjunção |
|---|---|---|
| S0 | **000** (solo) | tokens, ícones, chips, fontes, shell, baselines: arquivos que toda feature de console lê depois |
| S1 | **010 ∥ 030** | 010 é gateway (endpoint SSE, eventos), chart (proxy) e `console/src/live/`; 030 é console de run (`run-detail`, transcript, i18n de kinds) sobre o stream **por run que já existe**. Interseção: nenhuma — 030 não toca `live/`, 010 não toca surfaces |
| S2 | **040 ∥ 060** | 040 é rotas de decisão no gateway + `platform/approvals`/remediation (repropor) + tela Decisions; 060 é console das quatro telas de área + suas agregações de leitura (`incidents`, `resources`, `knowledge`, `agent`). Interseção: nenhuma |
| S3 | **020 ∥ 050** | 020 é `platform/runs` + `gateway/runtime` (título, estágio corrente) sem console; 050 é o Painel + endpoint de overview/timeline-por-assunto. Interseção: nenhuma — e o acceptance do slot já valida o Painel exibindo os títulos da 020 |
| S4 | **070** (+ janela de reparos) | modal de investigar + endpoint de sugestões; pequeno de propósito: o slot absorve pendências dos verifiers |
| S5 | **confronto visual + demo** (solo, orquestrador) | as 7 telas × 2 temas contra os artboards, e a demo da onda |

## 2. Single-write, por slot

`console/src/i18n/*.ts`, `console/src/shell/routes.ts`,
`console/visual/screens.json` são single-write no nível da onda. A 000
estabelece o baseline; o dono efetivo de cada escrita é o slot abaixo:

| Slot | Dono |
|---|---|
| S1 | 030 (010 declara chaves no relatório; orquestrador aplica no merge) |
| S2 | 060 (040 idem) |
| S3 | 050 (020 é backend; não os toca) |
| S4 | 070 |

`console/src/design/tokens.ts`, `icons.tsx`, `components/status.tsx` e
`console/public/fonts/` são da **000** e ficam congelados depois do S0: outra
feature que precisar de um token ou ícone novo declara no relatório e o
orquestrador aplica — a fundação não deriva por acréscimo silencioso.

**Nomear três arquivos do console não basta.** O S3 provou o que faltava na
lista: as duas features numeraram a migração **0020** a partir do mesmo pai
`0019`, cada uma na sua worktree, sem nunca se verem — histórico bifurcado
com duas cabeças, que numa onda anterior deixou o ambiente sem subir. Um
**número de revisão de migração é recurso single-write**, e o
`platform/persistence/postgres/models.py` também é, porque guarda o modelo de
toda tabela e duas features que acrescentem coluna colidem nele.

A regra de desempate, aplicada no S3: **vence quem declarou o número no
`tasks.md` antes do despacho**; a outra renumera para o seguinte e mantém o
`down_revision` no pai antigo, para que a worktree isolada continue verde — a
revisão vizinha não existe lá e não pode existir antes do merge. **O
orquestrador re-aponta o pai no merge**, e a feature que renumerou registra
essa pendência no relatório final. `fixtures/scenarios/**` e a própria suíte
transversal seguem a mesma disciplina.

## 3. O gate visual via Orca Browser (decisão 7 — sem desvio negativo)

O que a onda anterior de design não teve: um portão que compara **o que o
staging serve** com **o que o board manda**, antes de fechar o slot. O review
visual é feito pelo modelo no Orca Browser, usando a capacidade `orca-cli` do
runtime atual. Playwright não faz análise visual; seus screenshots e traces são
somente artefatos de diagnóstico dos testes automatizados.

Os testes Playwright continuam obrigatórios para comportamento automatizado:
acceptance specs, regras transversais, fluxos funcionais e cenários
determinísticos. Eles não produzem o veredito de aparência e não substituem o
review visual.

O protocolo visual, por slot, depois do deploy e do acceptance:

1. Para cada tela alterada no slot, na URL real
   (`https://stg-ninjasre.lan.kyo.ninja/<rota>`), via Orca Browser:
   - abrir a rota e aguardar a aplicação estabilizar;
   - tema escuro: inspecionar a tela e capturar pelo Orca Browser;
   - alternar para o claro pelo botão de tema da topbar (nunca por
     `data-theme` injetado — o botão é parte do que se valida) e capturar pelo
     Orca Browser;
   - guardar como `<feature>/evidence/visual/<rota>-{dark,light}.png`.
2. Abrir o artboard correspondente (`design/padrao-2026-08/<Nome>.dc.html`)
   e comparar lado a lado. A comparação é estrutural, não pixel-a-pixel:
   layout e hierarquia, tokens de cor aplicados, tipografia (as três
   famílias), ícones do set novo, formas de status, chips com contorno,
   motion presente onde o artboard anota (pulse do "Ao vivo", slide-in de
   item novo, shimmer de estágio ativo). O movimento em si é asserido pelo
   acceptance automatizado; a presença e composição visual são julgadas pelo
   modelo no Orca Browser.
3. Veredito escrito em `<feature>/evidence/visual/VEREDITO.md`: uma linha
   por tela×tema — CONFORME, ou o desvio nomeado. **Qualquer desvio = FAIL
   do slot**, com dois destinos possíveis e nenhum terceiro: corrigir o
   código, ou registrar em `design/padrao-2026-08/DIVERGENCIAS.md` com
   aprovação explícita do operador. Desvio "que melhora" segue o mesmo
   caminho: a onda anterior morreu disso. Se o Orca Browser não estiver
   disponível, o resultado visual é `UNVERIFIED`, nunca um PASS inferido dos
   testes Playwright.
4. Os dados vivos do staging diferem dos dados de exemplo do artboard — o
   veredito compara estrutura e vocabulário visual, e diz explicitamente
   quando uma diferença é de dado (aceitável) e não de desenho.

O sweep do S5 repete o protocolo para as 7 telas × 2 temas de uma vez, com
tudo mergeado, e é a evidência final do CONFRONTO da onda.

## 4. Staging e acceptance

Como na v7: o orquestrador é o único que roda `make deploy-stg`
(`COMPONENTS=web` em slot só de console, `app web` em misto), aguarda Argo
Synced+Healthy, e roda os acceptance specs da feature + a transversal contra
a URL real com `tools/spec_validation browser --backing staging` (entregue
pela v7-000; o runner recebe apenas uma sessão opaca emitida pelo credential
proxy, nunca o segredo. A sessão não entra no processo do agente, prompt,
argumentos de ferramenta, filesystem ou trace. Specs novos desta onda marcados
`@staging`-safe: leitura, fluxo de proposta, e **uma única criação de run por
slot**, quando necessária — nunca destruição de dados. Quando duas features
do mesmo slot precisam do run, a primeira tarefa do slot o cria e as demais
consomem o fixture de run compartilhado; nenhuma abre um segundo run.
SSE tem acceptance próprio: a asserção é "o evento chega sem reload", usando
o fixture do slot quando houver um run vivo.

Os donos dos fixtures de run são explícitos e não podem ser duplicados:

| Slot | Tarefa que cria o fixture UI | Tarefas que consomem o mesmo fixture |
|---|---|---|
| S1 | 010 T062 | 030 T021 (o T004 define o cenário) |
| S3 | 050 T034 | 020 T014 |
| S4 | 070 T018 | — |

O harness local pode criar dados próprios para testes isolados; essa exceção
não altera o orçamento de criação no staging.

## 5. Gates que não mudam

Acceptance-first confirmado vermelho; `spec-implementer` por feature em
worktree isolada; verifier independente em contexto limpo; no máximo dois
ciclos de reparo; Playwright somente para testes automatizados; review visual
LLM somente pelo Orca Browser; `make verify` nos checkpoints e no fim; evidência
antes de avançar; confronto final da onda com a coluna "quem constrói isso em
produção?". Paralelizar muda quando as coisas rodam, nunca o que precisa
passar.

## 6. Retomada

O que a execução de um slot ensina não cabe no `progress.json`, que guarda
estado, nem no `controle.md`, que guarda prova. Fica em
[RETOMADA-S1.md](RETOMADA-S1.md): as armadilhas de provisionar worktree
isolada, o comportamento do teto de turnos, os achados ainda abertos com as
hipóteses já formadas, e o que o orquestrador reteve por não caber numa
worktree. Quem retomar o slot — outro agente, outro runtime — lê o
`progress.json`, depois esse arquivo, depois o controle da feature.
