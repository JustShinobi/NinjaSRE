# Tasks: Iniciar investigação — o modal que começa do ambiente

**Input**: Design documents from `specs_v8/070-iniciar-investigacao/`

**Prerequisites**: spec.md, plan.md. Roda no S4, solo, depois de
000/010/020/030/040/050/060 mergeadas; dona dos single-write do slot.

**Tests**: acceptance-first. O acceptance das dezesseis alegações normativas
aterrissa **antes** de qualquer implementação e é confirmado vermelho, com a
mensagem real de cada uma registrada.

**Marcação**: `[x]` feita; `[ ]` pendente; `[~]` encerrada sem execução, com a
razão na própria linha. Um `[~]` nunca é um `[x]` envergonhado.

## Regras que valem para toda tarefa deste arquivo

1. **Nada de identificador de planejamento em arquivo committed.** Substância
   no arquivo; a referência fica na spec.
2. **O board é o critério.** Valor visual divergente do artboard sem registro
   em `design/padrao-2026-08/DIVERGENCIAS.md` é defeito — inclusive desvio
   "que melhora".
3. **Tokens, ícones, formas e motion são da fundação e estão congelados.** O
   que faltar é declarado no relatório final para o orquestrador aplicar;
   nenhuma tarefa os edita aqui.
4. **Nenhum literal de time, modelo, postura ou contagem de estágios no
   console.** Tudo do `preamble`; o teste de US2 procura e reprova.
5. **Arquivo gerado é regenerado, nunca editado à mão** (documento de API,
   cliente TS, dataset simulado).
6. **Esta feature é dona dos single-write no S4** (`console/src/i18n/*.ts`,
   `console/src/shell/routes.ts`, `console/visual/screens.json`).
7. **Gate não é afrouxado para a mudança passar.**
8. **Uma escrita real no staging, uma só**: o run da AN-06 no fechamento do
   slot. Nenhuma outra tarefa cria runs fora do harness local.

---

## Phase 0: Linha de base

- [ ] T001 Rodar `make verify` na árvore intacta e guardar o log **fora do
      repositório**: exit code, contagem, falhas. Se não estiver verde, parar
      e reportar antes de escrever qualquer coisa.
- [ ] T002 Capturar via Orca browser o estado **atual** do popover no staging
      (aberto, dois temas) para `evidence/visual/antes-{dark,light}.png` — o
      "antes" que o veredito final compara.

## Phase 1: Acceptance vermelho

- [ ] T003 Escrever `console/tests/e2e/iniciar-investigacao.acceptance.spec.ts`
      codificando AN-01…AN-16 (uma asserção nomeada por alegação; as
      staging-safe marcadas com a anotação que a suíte transversal já usa; a
      AN-06 marcada como a escrita única do slot). Rodar contra o harness
      local e **registrar o vermelho** com a mensagem real de cada alegação.
- [ ] T004 Escrever o teste de contrato da rota nova em
      `tests/contract/gateway/test_investigation_suggestions.py`: shape
      (`suggestions[]` estruturadas + `preamble` completo), cap de 3, ordem
      (recorrentes desc, lote, auditoria), truncamento determinístico do caso
      2 recorrentes + lote + auditoria, desempate do lote, resposta parcial
      com fonte indisponível, 401 sem sessão. Confirmar vermelho.

## Phase 2: A rota de sugestões (gateway)

- [ ] T005 Extrair a resolução de time de
      `gateway/http/orchestration.py:64-86` para função nomeada reutilizável
      no mesmo módulo, sem mudar comportamento; o início do run passa a
      chamá-la (teste existente segue verde).
- [ ] T006 Implementar `GET /v1/investigations/suggestions` em
      `gateway/http/routes/investigations.py`: compor assuntos recorrentes
      (mesma leitura da listagem de incidentes, janela 24h, 2+ disparos, top
      2), lote não saudável (estate: 3+ unhealthy no mesmo nó ou tipo) e
      auditoria de cluster (estate conhece cluster → gerar candidato); aplicar
      o cap de 3 após a ordenação normativa e o desempate lexicográfico do
      lote; montar
      `preamble` com a função de T005, o modelo configurado do runtime do
      investigador, a postura de autonomia vigente e a contagem de estágios
      lida da definição do pipeline. T004 verde.
- [ ] T007 Adicionar `suggestions()` em `surfaces/console/client.py` e cobrir
      no teste de cliente existente.
- [ ] T008 Regenerar `fixtures/contract/openapi.json` e
      `console/src/api/schema.ts` dos geradores; gate de desvio verde.
- [ ] T009 Servir sugestões e preamble no dataset do mockplane (cenário
      padrão: 2 recorrentes reais do dataset + auditoria; um cenário sem
      sugestão nenhuma para a US-edge), com o registro de endpoints do mock
      cobrindo a rota nova.

## Phase 3: O modal (console)

- [ ] T010 Variante modal centrada em `console/src/components/overlay.tsx`
      (overlay página inteira + contêiner 640px/raio 16/borda e sombra do
      artboard, foco preso, Esc/clique-fora, retorno de foco, entrada 240ms
      atrás de `prefers-reduced-motion`), coberta em
      `console/tests/unit/components/overlay.test.tsx`.
- [ ] T011 Courier `console/src/app/api/investigations/suggestions/route.ts`
      no padrão do courier de verificação: repassa a sessão, nunca computa.
- [ ] T012 Reescrever `console/src/live/investigate.tsx` como o modal do
      artboard: cabeçalho com ícone e título, campo com halo accent e linha de
      apoio + atalho, seção de sugestões (frase composta por i18n dos campos
      estruturados, forma de status por tipo, clique preenche, ausência real
      quando vazia, chegada tardia com slide-in), rodapé factual do preamble
      com ausência declarada na falha, Cancelar/Investigar, Ctrl+Enter,
      desabilitado até resposta no envio, `context.origin` quando o texto
      enviado é o da sugestão. `POST /v1/investigations` inalterado via
      `act`. Preservar caveat de integrações e desabilitado de runtime.
- [ ] T013 Atualizar `console/src/shell/shell.tsx` para montar o modal (props
      iguais) e reescrever os testes que montavam o drawer
      (`console/tests/unit/live/edges.test.tsx`, `live-run.test.tsx`).
- [ ] T014 Chaves i18n novas em `console/src/i18n/en.ts` e `pt-BR.ts` — o
      pt-BR do artboard é normativo; nenhuma chave órfã nas duas línguas
      (gate de i18n verde).

## Phase 4: Visual

- [ ] T015 Registrar o estado "modal de investigar aberto" em
      `console/visual/screens.json` e capturar baselines na imagem pinada
      (`python -m tools.console_visual accept`), revisando o diff de PNGs
      como parte do commit.
- [ ] T016 Acceptance completo verde no harness local (AN-01…AN-16 menos as
      só-staging), suíte `make verify` verde.

## Phase 5: Fechamento do slot (EXECUCAO.md §3–§4)

- [ ] T017 `make deploy-stg COMPONENTS="app web"`; aguardar Argo
      Synced+Healthy.
- [ ] T018 Acceptance staging-safe contra
      `https://stg-ninjasre.lan.kyo.ninja` via `tools/spec_validation browser
      --backing staging`, incluindo a AN-06 — o run único do slot, iniciado
      pelo modal com uma sugestão real.
- [ ] T019 Captura Orca do modal aberto nos dois temas →
      `evidence/visual/modal-{dark,light}.png`; escrever
      `evidence/visual/VEREDITO.md` linha a linha contra
      `design/padrao-2026-08/StartInvestigation.dc.html`, separando desvio de
      desenho (FAIL) de diferença de dado (aceitável, dita).
- [ ] T020 Anotar no relatório final: chaves i18n aplicadas, tokens/ícones
      que faltaram à fundação (se algum), contagem do banco: o run da AN-06
      existe, com `context.origin` gravado.

---

## Dependencies & Execution Order

- T001→T002 (base) → T003–T004 (vermelho) → T005–T009 (gateway) e
  T010–T011 em paralelo → T012–T014 (modal) → T015–T016 (visual/local) →
  T017–T020 (staging, nesta ordem).
- T012 depende de T006 no harness real, mas desenvolve contra T009 (mock) —
  o que permite console e gateway andarem na mesma janela sem se esperar.
