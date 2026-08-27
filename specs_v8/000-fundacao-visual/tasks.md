# Tasks: Fundação visual — a tabela de tokens vira o board, e o board vira o que o navegador desenha

**Input**: Design documents from `specs_v8/000-fundacao-visual/`

**Prerequisites**: spec.md, plan.md. Nenhuma feature antes desta; é o S0
da onda e roda solo na árvore compartilhada.

**Tests**: acceptance-first. O acceptance spec das dezesseis alegações
normativas aterrissa **antes** de qualquer implementação e é confirmado
vermelho, com a mensagem real de cada uma registrada. Uma paleta trocada e
validada só depois do fato não distingue "ficou como o board" de "o teste
não olha".

**Marcação**: `[x]` é feita; `[ ]` é pendente; `[~]` é **encerrada sem
execução** — com a razão na própria linha e onde a obrigação foi cumprida
por outro caminho. Um `[~]` nunca é um `[x]` envergonhado.

## Regras que valem para toda tarefa deste arquivo

1. **Nada de identificador de planejamento em arquivo committed.** A
   substância vai no arquivo; a referência fica na spec.
2. **O board manda.** Valor visual divergente do
   `design/padrao-2026-08/` sem registro em `DIVERGENCIAS.md` é defeito —
   inclusive divergência "que melhora". Quem discordar do board para,
   escreve, e pergunta; não implementa a própria opinião.
3. **Cor entra por token.** Nenhuma tarefa escreve hex em componente;
   quem precisar de um valor que a tabela não tem, acrescenta o token com
   seu par de contraste.
4. **As formas de status não mudam de geometria.** Se uma tarefa parecer
   exigir isso, ela passou do alvo.
5. **Nomes de export não mudam.** Ícones, tokens e componentes mantêm
   assinatura; esta feature revaloriza e redesenha, não renomeia.
6. **Nenhuma tela de área é editada.** `surfaces/screens/*` fica intacto;
   o que o shell importa é a fronteira.
7. **Gate não é afrouxado para a mudança passar.** Suíte de contraste,
   paridade Tailwind↔tokens, transversal e visual: reprova é defeito da
   mudança.

---

## Phase 0: Linha de base

- [ ] T001 Rodar `make verify` na árvore intacta e guardar o log **fora
      do repositório**; registrar exit code e contagem de testes. Linha de
      base não-verde: parar e reportar antes de escrever qualquer coisa.
- [ ] T002 Registrar a lista de requests do load de `/` no staging atual
      (Playwright, `page.on('request')`) e guardar fora do repositório —
      é o "antes" da propriedade zero-egress, que deve ser idêntica no
      "depois".
- [ ] T003 Registrar contagem e resultado da suíte de cenários sintéticos
      ("sem efeito" é a resposta esperada ao final; "não medido" não é
      aceitável).

## Phase 1: Acceptance primeiro, confirmado vermelho

- [ ] T004 Escrever
      `console/tests/e2e/fundacao-visual.acceptance.spec.ts` com uma
      asserção por alegação normativa da spec (16), viewport 1920×1080:
      computed styles dos tokens por tema (hex exatos), `font-family`
      computado de corpo/H1/identificador, lista de requests do load
      restrita à origem, borda 1px do chip na cor do papel, as sete
      formas presentes via `data-shape`, marca pulsante do chip live,
      `prefers-reduced-motion` zerando `animation-name` (via
      `page.emulateMedia`), medidas de sidebar/topbar, ordem dos
      controles da topbar, raios computados 6/8/12/16, paridade de nomes
      entre temas, troca de tema sem reload. Marcar as treze [staging] na
      convenção staging-safe existente. Confirmar vermelho e registrar a
      mensagem real de cada alegação que falha; registrar como
      caracterização as que já passam (a de requests e a de formas).
- [ ] T005 [P] Estender `console/tests/unit/design/tokens.test.ts` (ou o
      arquivo vizinho que hoje prova a paleta) com os valores-alvo: os
      hexes da spec por papel e tema, `RADII = {1:6, 2:8, 3:12, 4:16}`,
      `SHELL` 232/60, `FONT_STACKS.display` começando com "Space
      Grotesk". Confirmar vermelho.
- [ ] T006 [P] Teste de unidade novo para as primitivas de motion: o CSS
      publicado declara `pulse-live`, `slide-in` e `stage-shimmer`, cada
      uma lendo `var(--dur-…)`, e o bloco `prefers-reduced-motion` as
      zera. Confirmar vermelho.
- [ ] T007 [P] Teste de unidade para o contorno do chip: `ROLE_SKIN` de
      cada papel contém a classe de borda do próprio papel.
      Caracterizar junto que `SHAPE_CLASS` e `HOLLOW_SHAPES` estão
      byte-idênticos ao estado atual (paridade que deve passar antes e
      depois). Confirmar o vermelho da metade nova.

## Phase 2: A tabela

- [ ] T008 Aplicar em `console/src/design/tokens.ts` a paleta completa da
      spec (26 papéis × 2 temas, incluindo os `on-*` fixados por
      contraste), `RADII`, `SHADOWS`, `SHELL` e `TYPE_STEPS` (H1 26/700
      display; KPI 30/700 display; corpo 14/1.5; meta 12.5; micro 11).
      Rodar a suíte de contraste; se um par do board reprovar, **parar**:
      registrar par, valor medido e menor ajuste que passa, e levar ao
      operador (regra 2) — nunca ajustar em silêncio.
- [ ] T009 Atualizar o tema Tailwind em `console/src/app/globals.css`
      para os tokens/valores novos até `css.test.ts` passar nas duas
      direções; `ICON_SIZES` para 14/18/20/24 em `css.ts`, com
      `--family-display` emitida.
- [ ] T010 Registrar no controle a tabela final 26×2 com a origem de cada
      valor (board `SPEC.md` / decisão de contraste), como a spec exige.

## Phase 3: Fontes

- [ ] T011 Obter os oito woff2 (SG 500/600/700; Plex Sans 400/500/600;
      Plex Mono 400/500), subset latin, e comitá-los em
      `console/public/fonts/` com `OFL.txt`. Registrar no controle a
      origem e o tamanho de cada arquivo; soma ≤ ~500KB.
- [ ] T012 Declarar os `@font-face` em `globals.css`
      (`font-display: swap`, `src: url('/fonts/…') format('woff2')`) e
      atualizar `FONT_STACKS` (display novo; sans e mono com as famílias
      na frente dos fallbacks atuais).
- [ ] T013 Acrescentar em `console/src/app/layout.tsx` o preload de
      display-700, sans-400, sans-500 e mono-400
      (`<link rel="preload" as="font" type="font/woff2" crossOrigin>`).

## Phase 4: Chip, ícones, motion

- [ ] T014 `console/src/components/status.tsx`: `ROLE_SKIN` soma
      `border-{papel}` ao tint de cada um dos cinco papéis; nada mais
      muda no arquivo.
- [ ] T015 Redesenhar os ícones de `console/src/design/icons.tsx` no
      traço 1.6 round/round grid-20 do board, copiando os desenhos dos
      artboards onde existem (navegação completa, busca, sino, mais,
      parar, tema, chevrons, check, close, copy, info, alerta) e seguindo
      o estilo nos demais; exports e assinaturas intactos (o teste de
      paridade de T007 continua verde).
- [ ] T016 Declarar em `globals.css` os keyframes e classes `pulse-live`,
      `slide-in` e `stage-shimmer` com durações via `--dur-*`
      (`DURATIONS` ganha `pulse: 2000`, `slide: 240`, `shimmer: 1600`) e
      o bloco único de `prefers-reduced-motion` zerando as três.
- [ ] T017 `console/src/live/auto-refresh.tsx`: a marca do estado live
      passa a usar `pulse-live`; os outros três estados ficam como estão.

## Phase 5: Shell

- [ ] T018 `console/src/shell/topbar.tsx`: altura pelo token de shell
      (60px), logotipo do board (shuriken accent + "Ninja"/"SRE" em
      display), busca limitada a 420px; ordem dos controles conferida
      contra o artboard — sem controle novo, sem controle removido.
- [ ] T019 Sidebar: largura pelo token (232px), rótulos dos três grupos
      pelo catálogo i18n (chaves novas em `en.ts` e `pt-BR.ts`:
      "Now/Agora", "The environment/Ambiente",
      "Configuration/Configuração"), item ativo com `accent-bg` + texto
      `accent` + barra interna 2px, rodapé do guardião com `StatusDot`
      pulsante no estado ativo.
- [ ] T020 Varredura de hex literal da paleta antiga em `console/src/`
      (`#0a7452`, `#3ad195` antigos etc. fora de `tokens.ts`): qualquer
      ocorrência vira token ou é reportada; a varredura e o resultado
      entram no controle.

## Phase 6: Fecho local

- [ ] T021 Acceptance da feature verde no harness local; as duas tarefas
      de caracterização (requests, formas) verdes antes e depois.
- [ ] T022 Recapturar as baselines
      (`python -m tools.console_visual accept`), revisar o diff de PNGs
      tela a tela contra o board (é a revisão, não um carimbo) e comitar
      no mesmo diff; cobertura vermelha herdada do gate registrada no
      controle como herdada.
- [ ] T023 `make verify` completo, verde, partindo do verde de T001;
      contagem dos cenários sintéticos comparada com T003 ("sem efeito"
      confirmado).

## Phase 7: Staging e evidência visual (fecho do slot, com o orquestrador)

- [ ] T024 `make deploy-stg COMPONENTS=web`; aguardar Argo
      Synced+Healthy.
- [ ] T025 Rodar as treze alegações [staging] contra
      `https://stg-ninjasre.lan.kyo.ninja` via
      `tools/spec_validation browser --backing staging`.
- [ ] T026 Capturar via Orca browser, no staging real: `/` nos dois temas
      (alternando pelo botão da topbar, nunca por atributo injetado),
      full-screenshot, salvos em
      `specs_v8/000-fundacao-visual/evidence/visual/shell-dark.png` e
      `shell-light.png`.
- [ ] T027 Escrever `evidence/visual/VEREDITO.md`: uma linha por
      tela×tema contra `Main.dc.html` — CONFORME ou o desvio nomeado
      (diferença de dado vivo explicitada como aceitável). Qualquer
      desvio de desenho: corrigir ou levar a `DIVERGENCIAS.md` com o
      operador; o slot não fecha com desvio pendente.
