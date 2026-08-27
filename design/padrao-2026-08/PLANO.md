# Plano — do board ao produto

O board desta pasta é normativo. Este plano diz o que precisa existir para
cada coisa desenhada ser verdade em produção, em que ordem, e o que já existe.
A execução segue a forma da casa: cada etapa vira feature de onda spec-kit
(spec → plan → tasks, test-first, verificação independente), com estes
artboards como mockup normativo — exatamente o que o README da specs_v7 já
previa ("a geração… com os mockups normativos onde a feature é de console").
As decisões 1–5 da specs_v7 (headline+report, tudo registrado, uma fonte por
fato, identidade endereçável, agir fail-closed) são pré-requisitos assumidos
aqui, não re-decididos.

## O que o board mostra × o que existe

| Elemento do board | Existe hoje | Falta |
|---|---|---|
| Run novo desliza no Painel sem F5 | Stream **por run** (`surfaces/console/stream.py`, `console/src/live/`) | Canal SSE **do deployment** (runs, incidentes, decisões) e consumo nas listas |
| Título humano do run ("Procurar anomalias…") | Prompt digitado chega ao backend e se perde; headline só no fim (v7 decisão 1) | Persistir objetivo como título provisório; headline da entrega o substitui; hash nunca é título |
| Barra de 6 estágios por run | `stage_completed` já flui no stream por run | Agregar estágio corrente por run e servir na lista/Painel |
| Transcript narrado + payload atrás de toggle | `STREAM_KINDS` já classifica eventos (`transcript.ts`) | Frase narrada por kind (i18n), toggle Narrado/Bruto, `<details>` para payload |
| Custo por turno durante o run | Tabelas `run_turns`/`tool_calls`/`evidence` existem; v7 diz que o recorder não está composto | Compor recorder no caminho de produção (v7 decisão 2) |
| Cartão de decisão estruturado | O payload da ação **já carrega** steps, rollback, evidence com refs, blast_radius, risk (visto no staging) | Expor por campo na API do console; a tela nunca vê o JSON inteiro |
| "Propor de novo, agora" em expirada | Expirada é beco sem saída; o texto manda "pedir de novo" sem botão | Endpoint de repropor (nova leitura do ambiente → nova proposta); badge da sidebar conta só acionáveis |
| Histórico "Decididas recentemente" | Decisões têm registro | Listar decididas com desfecho e verificação |
| Mini-linha do tempo de disparos por assunto | Firings existem por incidente | Agregação de timeline por assunto (Incidents e Painel) |
| Saúde segmentada + agrupamento por nó em Recursos | Contagens existem | Agregação por nó/tipo; síntese dos unhealthy ("14 em pve02 há 2 h") |
| Sugestões no modal Investigar | — | Sugestões derivadas do estado (assuntos recorrentes, quedas em lote) |
| Episódios com filtros humanos em Conhecimento | Episódios existem; filtro lista ids crus duplicados | Componentes agrupados por tipo, sem duplicata guest/container |
| Pipeline "metrô" em O agente | Conteúdo existe em prosa | Só front |
| Aprovar/Recusar no Painel | Aprovação existe em Decisões | Ação inline (mesmo endpoint), com o cartão completo a um clique |

## Etapas, em ordem de dependência

**A. Fundação visual** — `console/src/design/`: tokens novos (paleta do
`SPEC.md`, dois temas), fontes self-hosted (woff2, ver DIVERGENCIAS.md §2),
set de ícones stroke 1.6 substituindo os glyphs feios, chip com contorno,
primitivas de motion (pulse-live, slide-in, shimmer de estágio; respeitar
`prefers-reduced-motion`), densidade. Re-baseline do gate visual fecha a
etapa. Nada de tela nova aqui — só a linguagem, aplicada ao shell
(sidebar/topbar).

**B. Canal vivo do deployment (SSE)** — gateway: endpoint de stream com
escopo deployment publicando run_started/stage/completed, incidente
aberto/fechado, decisão proposta/expirada/decidida; cursor para retomada;
autenticação da sessão do console. Console: store por página consumindo o
canal, `AutoRefresh` vira fallback (indicador único "Ao vivo" permanece —
DIVERGENCIAS.md §3). Atenção ao proxy: SSE atravessa Traefik no staging —
desligar buffering/timeout na rota do stream.

**C. Identidade do run** — objetivo digitado persistido e servido como
título desde o primeiro evento; headline da entrega (v7) substitui ao
completar; runs por alerta ganham título "Alerta X em recurso Y". Remove
hash-como-título de todas as listas.

**D. Run view narrado** — a tela `RunView.dc.html`: pipeline de estágios no
topo, transcript narrado (frase por kind, i18n), toggle Narrado/Bruto,
"Descobertas até agora" e "O que tocou" alimentados durante o run (depende de
B e do recorder composto), custo por turno.

**E. Decisões estruturadas** — a tela `Decisions.dc.html`: API expõe a ação
por campo (plano/rollback/evidência com link para a fonte/raio/risco/
autonomia), payload bruto atrás de `<details>`; endpoint repropor; histórico
de decididas; aprovar/recusar inline no Painel (`Main.dc.html`).

**F. As telas de área** — Incidents (timeline por assunto, nunca id cru como
subtítulo), Resources (barra segmentada, agrupamento por nó, síntese),
Knowledge (filtros humanos, painel "o que aprendeu"), TheAgent (pipeline
metrô, cards-resumo). Fan-out natural: uma feature por tela, subagente por
tela, todas sobre A.

**G. Iniciar investigação** — modal central com sugestões do estado do
ambiente; Ctrl+Enter; diz time/modelo/estágios antes de rodar.

Ordem: **A → B ‖ C → D ‖ E → F ‖ G.** B e C não dependem entre si; D precisa
de B (stream) e C (título); E só de A; F e G só de A (F usa B onde houver
vivo). Cada etapa entrega valor sozinha e nenhuma quebra a anterior.

## Método

- Gerar as specs na forma da casa (spec-kit) por etapa; os artboards desta
  pasta são o mockup normativo citável de cada spec de console.
- Test-first com o vermelho confirmado; DoD estilo v7: a contagem no banco
  bate com a contagem na tela; para SSE, o evento chega sem reload (teste
  e2e Playwright com run disparado de verdade).
- Artigo XIV (nada dormente): cada mecanismo novo de backend nasce composto
  no root de composição servido — o SSE não é entregue enquanto o Painel não
  o consome.
- Verificação visual nos dois temas por tela, contra estes artboards.
