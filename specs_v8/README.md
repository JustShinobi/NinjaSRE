# specs_v8 — O console vira o board, e o board vira verdade ao vivo

Onda proposta em 2026-08-27 a partir de uma auditoria de uso real do staging
(`stg-ninjasre.lan.kyo.ninja`, via Orca browser, fluxo completo de investigação
executado pela UI) somada ao board de design aprovado pelo operador como
**definitivo**: [`design/padrao-2026-08/`](../design/padrao-2026-08/) — 11
artboards, `SPEC.md` (linguagem visual), `PLANO.md` (mapa existe×falta) e
`DIVERGENCIAS.md` (convenções que este padrão derruba, registradas).

Estado: **material de partida com specs geradas** — este README fixa as
decisões e o recorte; as features abaixo carregam spec/plan/tasks na forma da
casa. Pressupõe a v7 entregue (recorder composto, headline/report no contrato,
identidade endereçável, gates de decisão compostos).

## As decisões que governam a onda

1. **O board é o contrato, não a inspiração.** Cada tela entregue é comparada
   contra o artboard correspondente de `design/padrao-2026-08/` — layout,
   tokens de cor, tipografia, ícones, formas de status, motion. Desvio não
   registrado em `DIVERGENCIAS.md` é defeito, mesmo que "melhore": a onda
   anterior de design morreu de desvios que pareciam inofensivos. O caminho
   para divergir existe e é um só: registro + aprovação do operador.
2. **A spec diz o que executa.** Regra anti-vagueza, a pedido do operador:
   todo requisito funcional nomeia o alvo (`arquivo`, rota, componente,
   tabela) e o comportamento observável com valor concreto — a cor pelo token,
   o texto pela string, o evento pelo nome, a contagem pelo número. Requisito
   que um verifier não consegue reprovar lendo a tela, o banco ou o código não
   entra na spec. "Melhorar a apresentação" não é requisito; "o título do run
   é o objetivo digitado, nunca `interactive investigation` nem hash" é.
3. **Vivo é push, não polling.** Um canal SSE com escopo de deployment
   (runs, incidentes, decisões) alimenta Painel e listas; o `AutoRefresh`
   por timer vira fallback declarado quando o stream cai. O indicador de
   frescor continua um por página (chip "Ao vivo"), nunca um por painel.
4. **Título é humano do primeiro evento ao último.** O objetivo digitado é o
   título provisório do run; o headline da entrega (v7) o substitui ao
   completar; run disparado por alerta chama-se pelo alerta e pelo recurso.
   Hash como título é ban transversal.
5. **JSON nunca é interface.** Transcript narrado por tipo de evento; payload
   bruto existe atrás de um toggle/`<details>`, nunca como conteúdo primário.
   O cartão de decisão expõe plano, reversão, evidência com fonte, raio de
   alcance e risco **por campo** — o documento da ação já carrega tudo isso.
6. **Beco sem saída é defeito.** Decisão expirada tem "Propor de novo,
   agora" (nova leitura do ambiente → nova proposta); o badge da sidebar
   conta só o acionável; toda tela vazia diz o que fazer a seguir.
7. **Validação é no staging, com os olhos.** Todo slot termina com
   `make deploy-stg` + acceptance contra o staging real **e captura visual
   via Orca browser das telas alteradas, nos dois temas**, comparada ao
   artboard e comitada como evidência — protocolo em
   [EXECUCAO.md](EXECUCAO.md) §3. Sem evidência visual, o slot não fecha.
8. **Sem artboard, sem reforma.** Tela ou aba que não tem artboard em
   `design/padrao-2026-08/` recebe da onda exatamente o que a 000 dá de
   graça — tokens, fontes, ícones, chips e shell compartilhados — e **nada
   estrutural**: um implementer sem parâmetro visual não inventa layout,
   não "melhora" e não reorganiza. Reformar uma tela exige, antes, o
   artboard desenhado, aprovado pelo operador e comitado no board; o gate
   visual numa tela sem artboard valida só o vocabulário (tokens/chips/
   ícones corretos), nunca layout. Toda aba que esta onda reforma tem
   artboard — os de Investigações (lista), Ferramentas, Autonomia,
   Contexto do time, Documentos e Topologia entraram no board por esta
   regra. Settings e Integrações ficam fora da onda: fundação só.
9. **Herdado da v7, continua normativo:** acceptance spec e2e confirmado
   vermelho antes da implementação; Artigo XIV (mecanismo composto num root
   servido, ou declarado dormente, ou não é entrega); single-write com dono
   por slot; i18n en + pt-BR para toda string nova; fontes self-hosted —
   nenhuma request a terceiros sai de página do console.

## Índice e ordem de execução

| Feature | Domínio | Depende de |
|---|---|---|
| 000-fundacao-visual | Os tokens do `SPEC.md` em `console/src/design/tokens.ts` (2 temas), Space Grotesk + IBM Plex self-hosted (`console/public/fonts/` + `@font-face`), set novo de ícones stroke-1.6 em `icons.tsx`, chip com contorno em `components/status.tsx`, primitivas de motion (pulse-live, slide-in, shimmer; `prefers-reduced-motion`), shell (sidebar agrupada + topbar) conforme `Main.dc.html`, re-baseline visual completo | — |
| 010-canal-vivo | Endpoint SSE de escopo deployment no gateway (eventos: run iniciado/estágio/completado, incidente aberto/fechado, decisão proposta/expirada/decidida; cursor de retomada; auth de sessão), config de proxy/Traefik no chart para SSE, store cliente em `console/src/live/` com `AutoRefresh` rebaixado a fallback | 000 |
| 020-titulo-vivo | Objetivo digitado persistido e servido como título desde `run_started`; headline substitui ao completar; run por alerta intitulado "alerta em recurso"; estágio corrente por run servido na lista; ban transversal de hash-como-título | 000 |
| 030-run-view-narrado | `/runs/<id>` conforme `RunView.dc.html`: pipeline de 6 estágios no topo com estágio ativo, transcript narrado por kind (i18n) com toggle Narrado/Bruto, "Descobertas até agora" e "O que tocou" alimentados durante o run, custo por turno (dados da v7-001) | 000 |
| 040-decisoes-estruturadas | `/decisions` conforme `Decisions.dc.html`: API expõe a ação por campo (plano/rollback/evidência com refs/raio/risco/autonomia), endpoint de repropor para expirada, histórico de decididas com desfecho, badge só-acionáveis | 000 |
| 050-painel-vivo | `/` conforme `Main.dc.html`: banda "Em execução agora" com barras de estágio via SSE, banda de aprovação com Aprovar/Recusar inline (endpoints da 040), KPIs com sparkline, "O que insiste em acontecer" com mini-timeline de disparos por assunto (via `groupBySubject` compartilhado — reconciliado com a 060, sem endpoint novo), "Atividade ao vivo" como linha do tempo | 010, 020, 040 |
| 060-telas-de-area | `/incidents`, `/resources`, `/knowledge`, `/agent` conforme seus artboards: timeline por assunto no incidente expandido, nunca id cru como subtítulo; barra de saúde segmentada + agrupamento por nó + síntese dos unhealthy; episódios com filtros por componente agrupado; pipeline "metrô" e cards-resumo | 000 |
| 070-iniciar-investigacao | Modal central conforme `StartInvestigation.dc.html`: sugestões derivadas do estado (assuntos recorrentes, quedas em lote), Ctrl+Enter, rodapé dizendo time/modelo/estágios/política | 000, 010 |

```
S0: 000 → S1: 010 ∥ 030 → S2: 040 ∥ 060 → S3: 020 ∥ 050 → S4: 070 (+ reparos) → S5: sweep visual final + demo
```

O S5 é o confronto da onda: as 7 telas × 2 temas capturadas no staging via
Orca browser, lado a lado com os artboards, mais a demo — uma investigação
iniciada pela UI aparecendo no Painel **sem reload**, com título humano,
narrada, e uma decisão aprovada a partir do cartão estruturado.

## Evidências de partida (auditadas em 2026-08-27, pela UI)

- `console/src/live/auto-refresh.tsx` re-renderiza a rota por timer
  (`router.refresh()`); um run iniciado só apareceu no Painel após navegação.
  No run view, o stream por run existente oscilou para "Reconnecting".
- Run iniciado pela UI com objetivo "Procure anomalias no cluster proxmos"
  intitulou-se "interactive investigation" do início ao fim; o objetivo não
  aparece em lugar nenhum. Runs por alerta: "investigation triggered by
  bc7bdbd452fae…".
- `/decisions` imprime o documento da ação inteiro (~40 linhas de JSON) no
  campo Target; a proposta expirada instrui "ask for it again" sem nenhum
  controle para isso; o badge da sidebar conta essa expirada como pendente.
- Ids crus como subtítulo em `/incidents` (`res-7a73b8aa…`); incidente
  expandido mostra N linhas idênticas sem link; filtro de Knowledge lista
  `container:lxc/122` e `guest:lxc/122` como componentes distintos.
- A investigação em si completou em 2m43s com root cause correto e relatório
  forte (3 storages CIFS inalcançáveis, 60/70 guests sem backup, 0 réplicas)
  — o produto faz bem e mostra mal; esta onda fecha essa distância.
