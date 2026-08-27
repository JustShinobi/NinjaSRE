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

## 3. O gate visual (decisão 7 — sem desvio negativo)

O que a onda anterior de design não teve: um portão que compara **o que o
staging serve** com **o que o board manda**, antes de fechar o slot. O
protocolo, por slot, depois do deploy e do acceptance:

1. Para cada tela alterada no slot, na URL real
   (`https://stg-ninjasre.lan.kyo.ninja/<rota>`), via Orca browser:
   - tema escuro: `goto` → `wait --load networkidle` → `full-screenshot`;
   - alternar para o claro pelo botão de tema da topbar (nunca por
     `data-theme` injetado — o botão é parte do que se valida) → capturar;
   - guardar como `<feature>/evidence/visual/<rota>-{dark,light}.png`.
2. Abrir o artboard correspondente (`design/padrao-2026-08/<Nome>.dc.html`)
   e comparar lado a lado. A comparação é estrutural, não pixel-a-pixel:
   layout e hierarquia, tokens de cor aplicados, tipografia (as três
   famílias), ícones do set novo, formas de status, chips com contorno,
   motion presente onde o artboard anota (pulse do "Ao vivo", slide-in de
   item novo, shimmer de estágio ativo — capturadas em screenshot como
   presença do elemento; o movimento em si é asserido pelo acceptance).
3. Veredito escrito em `<feature>/evidence/visual/VEREDITO.md`: uma linha
   por tela×tema — CONFORME, ou o desvio nomeado. **Qualquer desvio = FAIL
   do slot**, com dois destinos possíveis e nenhum terceiro: corrigir o
   código, ou registrar em `design/padrao-2026-08/DIVERGENCIAS.md` com
   aprovação explícita do operador. Desvio "que melhora" segue o mesmo
   caminho: a onda anterior morreu disso.
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
ciclos de reparo; `make verify` nos checkpoints e no fim; evidência antes de
avançar; confronto final da onda com a coluna "quem constrói isso em
produção?". Paralelizar muda quando as coisas rodam, nunca o que precisa
passar.
