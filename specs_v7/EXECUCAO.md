# specs_v7 — Protocolo de execução: pares paralelos e validação em staging

Escrito em 2026-08-23 a partir de três decisões do operador: (1) o produto é
**para outros**, com primeira validação na infra atual; (2) a onda executa
**2 features em paralelo** (cada uma custa ~3h; o par corta o tempo de parede
quase pela metade); (3) validação visível acontece **no staging real** via
`make deploy-stg` + Playwright, não só no harness local.

Este arquivo é o que a cláusula de opt-in da skill `spec-wave` exige: a
declaração explícita de worktrees isoladas e propriedade disjunta de arquivos.
Sem este arquivo, a skill continua sequencial.

---

## 1. O plano de pares

Regra de formação: **um lado backend-pesado × um lado console-pesado**, nunca
dois lados disputando os mesmos arquivos. 000 e 080 rodam sozinhas — a
primeira porque muda as regras que todo o resto lê, a última porque é a
integração e a demo.

| Slot | Executa | Racional da disjunção |
|---|---|---|
| S0 | **000** (solo) | governança + suíte transversal: arquivos que todos leem |
| S1 | **001 ∥ 020** | 001 é `platform/runs` + `gateway/runtime` + contrato de runs; 020 é console (rotas, ids, `api.ts`) + `gateway/http/routes/incidents.py`. Interseção: nenhuma |
| S2 | **010 ∥ 040** | 010 é console puro (run-detail, runs list, renderer de markdown); 040 é composition roots, `platform/autonomy`, `platform/remediation`, `capabilities` selection. Interseção: nenhuma |
| S3 | **030 ∥ 070** | 030 é verdade-de-estado (console + rotas de setup/providers); 070 é `platform/credentials/proxy` + `integrations/proxmox` (toque de console: uma mensagem no painel — cedida à 030 se colidir) |
| S4 | **050 ∥ 060** | 050 é identidade (CLI, `platform/identity`, sign-in/first-run); 060 é catálogo (`integrations/*` metadata, `IntegrationPanel`, rota de docs). Áreas de console distintas |
| S5 | **080** (solo) | fecha o laço no staging com tudo mergeado |

Tempo de parede estimado: 6 slots × ~3h ≈ **18h de trabalho de agente**, contra
~30h da fila sequencial.

## 2. Mecânica dos worktrees

- O orquestrador cria **duas worktrees por slot** a partir do mesmo commit-base
  (Agent tool com `isolation: worktree`, um `spec-implementer` por feature).
- Cada implementer trabalha **e commita localmente na sua worktree** — o
  isolamento exige commits para o merge; a regra "não commitar" da casa segue
  valendo para a árvore compartilhada e para push, que continuam sendo do
  operador.
- No fim do slot o orquestrador: mergeia os dois diffs na árvore da onda,
  resolve os append-only (abaixo), roda os gates de fronteira, e só então abre
  o slot seguinte. Worktrees são descartadas após o merge.

### Arquivos de escrita única (o veneno conhecido da v6)

`console/src/i18n/*.ts`, `console/src/shell/routes.ts`,
`console/visual/screens.json` têm **um dono por slot**:

| Slot | Dono dos single-write |
|---|---|
| S1 | 020 (001 é backend; não os toca) |
| S2 | 010 (040 é backend; não os toca) |
| S3 | 030 (070 entrega strings novas como bloco no relatório final; o orquestrador aplica no merge) |
| S4 | 060 (050 idem: strings entregues como bloco, aplicadas no merge) |

No S4 há um segundo arquivo disputado além dos single-write:
`console/src/surfaces/screens/first-run.tsx` — **dono: 050** (a feature é
centrada no first-run/sign-in). As duas edições que a 060 precisa nele (bloco
das ofertas e chamada de `IntegrationsStep`) são declaradas no relatório final
da 060 e aplicadas pelo orquestrador no merge do slot, como as chaves i18n.

O não-dono que precisar de uma chave i18n/rota **não edita o arquivo**: declara
a chave e o texto no seu relatório e referencia a chave no código. O merge do
slot aplica. Um implementer que editar single-write sem ser dono devolve o
trabalho para reparo — mesmo tratamento de um FAIL do verifier.

### Artefatos gerados: regenerados no merge, nunca mergeados

`fixtures/contract/openapi.json` e `console/src/api/schema.ts` não têm dono —
cada lado do par regenera o seu para trabalhar, e no merge do slot o
orquestrador **descarta as duas versões e regenera uma vez** a partir do
código mergeado. Mergear os dois textualmente produz um documento que nenhum
código gera.

### Arquivos fora do índice não viajam em worktree

A constituição (`.specify/`), os documentos da onda (`specs_v7/`) e qualquer
coisa em `.git/info/exclude` **não existem dentro de uma worktree** — um
implementer que "editar" um desses lá está editando o nada, e o slot perde a
mudança em silêncio. Edição desses arquivos é sempre na árvore compartilhada,
pelo orquestrador ou por slot solo (000, 080).

### O merge não carrega estado velho de arquivos alheios

Precedente real: `6d1ede6` escreveu a governança da v6 (status do ADR 0009,
índice, seção do roadmap) e `19431fc` — um commit largo de outro assunto — a
sobrescreveu com o estado antigo desses arquivos. No merge de cada slot o
orquestrador confere o diff **contra a base do slot** e recusa qualquer hunk
que toque arquivo fora do escopo declarado das duas features; um hunk que
*reverte* conteúdo existente em arquivo alheio é o sinal de árvore defasada,
nunca algo a mergear.

## 3. Validação em staging (a resposta ao "por que não podemos ter esse fluxo?")

Podemos — com duas restrições que o próprio fluxo respeita:

1. **Staging é um só.** Deploy acontece **no fim do slot**, com os dois diffs
   mergeados — nunca duas worktrees competindo pelo mesmo ambiente. O
   orquestrador é o único que roda `make deploy-stg` (com `COMPONENTS=` para
   estreitar: `web` num slot só de console, `app web` num slot misto).
2. **O que roda contra staging é a aceitação, não a suíte inteira.** A suíte
   determinística assume o mock backing; contra staging rodam os acceptance
   specs da feature e a transversal, apontados para a URL real.

O ciclo por slot fica:

```
implementers terminam → merge do slot → gates locais (Python/console estreitos)
→ make deploy-stg COMPONENTS=<o que mudou>
→ aguardar Argo Synced+Healthy (o script já cuida do digest no GitOps)
→ acceptance + transversal contra https://stg-ninjasre.lan.kyo.ninja
→ screenshots full-page por tela retocada → <feature>/evidence/
→ contagens no banco quando a feature alega gravação (001: tool_calls>0 etc.)
→ verifier de cada feature → PASS → próximo slot
```

**Checkpoint do laço mínimo (fim do S2).** Com 001+010+040 mergeadas, o
orquestrador roda a demo que a RECOMENDACAO.md pede — um alerta real →
investigação legível no staging → proposta aparecendo em Decisions — e anexa a
evidência antes de abrir o S3. É o marco do meio: se ele não passa, os slots
seguintes esperam, porque são polimento sobre um laço que não fecha.

### O que falta para isso existir (entra como tarefa da 000)

`tools/spec_validation browser` hoje só conhece `mock` e `compose` — ele sobe
o ambiente. Adicionar **`--backing staging`**: não sobe nada; recebe
`NINJASRE_STAGING_URL` (default `https://stg-ninjasre.lan.kyo.ninja`) e uma
credencial de operador (`NINJASRE_STAGING_CREDENTIAL`, lida do ambiente, nunca
gravada); roda os specs marcados como seguros contra ambiente compartilhado
(`@staging`-safe: leitura e fluxos de proposta — nunca destruição de dados).
Screenshot de evidência sai do mesmo run. É uma tarefa pequena e destrava o
fluxo para a onda inteira.

### O que o deploy-stg não substitui

O pipeline de entrega (verificação de fonte, SBOM, scan) continua sendo o
caminho de release. O `deploy-stg` é o loop dos vinte minutos — o script diz
isso no próprio cabeçalho — e é exatamente o que a validação de onda precisa.

## 4. Gates que não mudam

Tudo da skill continua valendo dentro de cada feature: acceptance-first
confirmado vermelho, `spec-implementer` com effort máximo, verifier
independente em contexto limpo, no máximo dois ciclos de reparo, `make verify`
nos checkpoints declarados e no fim, evidência antes de avançar, e o confronto
final com a coluna nova "quem constrói isso em produção?" (REGRAS.md §3).
Paralelizar muda **quando** as coisas rodam, nunca **o que** precisa passar.

## 5. Decisão de audiência (registrada)

O produto é **para outros**; a primeira validação de eficácia é na infra
atual, que tem serviços de sobra para exercitar investigações reais — e mais
podem ser adicionados. Consequências práticas:

- 050 (primeiro admin) e 060 (catálogo que ensina) ficam na onda com
  prioridade plena — são features de produto, não conveniências.
- O julgamento editorial da RECOMENDACAO.md (§3 — "o root cause estava
  certo?") ganha um alvo concreto: os serviços reais do cluster
  (RestoreDrillStale, InstanceDown, BlackboxProbeFailed…) são o corpus de
  validação de eficácia, e novos cenários podem ser fabricados neles.
