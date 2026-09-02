# Feature Specification: Fundação visual — a tabela de tokens vira o board, e o board vira o que o navegador desenha

**Feature Branch**: `feat/v8-000-fundacao-visual`

**Created**: 2026-08-27

**Status**: Draft

**Input**: User description: "O board `design/padrao-2026-08/` é o padrão
definitivo. Esta feature troca a fundação — tokens, tipografia self-hosted,
ícones, chip com contorno, motion, shell — sem tocar nenhuma tela de área. O
que ela entrega é a linguagem; as telas vêm nas features seguintes."

**Referência visual (DoD)**: `design/padrao-2026-08/Main.dc.html` (shell,
topbar, sidebar, chips), `design/padrao-2026-08/SPEC.md` (paleta, tipografia,
geometria, motion) e `design/padrao-2026-08/DIVERGENCIAS.md` (§1 contorno no
chip, §2 fontes). O acceptance
`console/tests/e2e/fundacao-visual.acceptance.spec.ts` codifica as alegações
normativas abaixo, confirmado **vermelho antes de qualquer implementação**.

**Viewport normativo de medição**: 1920×1080.

---

## Fatos verificados em 2026-08-27 (não re-derivar)

1. **A tabela de tokens é uma e tem três consumidores.**
   `console/src/design/tokens.ts` declara `COLOUR_ROLES` (26 papéis),
   `SPACING`, `RADII` (`{1:4, 2:6, 3:10, 4:14}`), `BORDER_WIDTHS`,
   `DURATIONS`, `TYPE_STEPS`, `SHELL`, `FONT_STACKS`, `DENSITY_METRICS` e
   `SHADOWS`. `console/src/design/css.ts` a renderiza como custom properties
   (`tokenStylesheet()`, com o guard
   `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) … }`
   e os blocos `[data-theme]` por último); o tema Tailwind em
   `console/src/app/globals.css` é o terceiro consumidor, preso à tabela por
   `console/tests/unit/design/css.test.ts` nas duas direções.
2. **O contraste é contrato executável.** `bodyPairs()`/`hoverPairs()`/
   `boundaryPairs()` (`console/src/design/tokens.ts:165-273`) enumeram todo
   par texto/fundo (mínimo 4.5:1) e toda fronteira (mínimo 3:1); a suíte de
   unidade reprova valor que não alcança. Uma paleta nova entra por essa
   porta ou não entra.
3. **As fontes hoje são do sistema.** `FONT_STACKS` declara duas famílias
   ("both from the operating system"); não existe `console/public/fonts/` nem
   `@font-face` em `globals.css`. Nenhuma página do console faz request
   externa — e isso é propriedade a preservar (DIVERGENCIAS.md §2).
4. **O chip é soft pill sem contorno.** `console/src/components/status.tsx`
   desenha `Badge`/`StatusChip`/`ResolvedChip`/`CheckChip` com `CHIP_SHAPE` +
   `ROLE_SKIN` (tint, sem borda da cor do papel); `ROLE_RING` existe mas só
   para as formas ocas (`HOLLOW_SHAPES = ['hollow-circle']`). As formas
   (`SHAPE_CLASS`: filled-circle, hollow-circle, dimmed-circle, square,
   rotated-square, triangle, dash) são o segundo portador de significado e
   **não mudam**.
5. **Os ícones são desenhados à mão em
   `console/src/design/icons.tsx`** (componente base `Glyph`, ~26 ícones;
   `PlusIcon:88`, `BookIcon:236`), consumidos por `topbar.tsx`, `routes.ts`
   (navegação) e telas. Tamanhos em `ICON_SIZES`
   (`console/src/design/css.ts:44`): `inline:13, nav:15, head:19, empty:20`.
6. **O shell atual**: topbar em `console/src/shell/topbar.tsx` (busca,
   `AutoRefresh`, tema em ciclo de três, densidade, sino, kill switch,
   Investigate, avatar `details`); navegação declarada em
   `console/src/shell/routes.ts`, grupos "Now / The environment / Settings".
7. **O gate visual roda numa imagem pinada.** `tools/console_visual.py`
   (`compare`/`accept`, `--network none`); telas registradas em
   `console/visual/screens.json`; o gate de cobertura **já estava vermelho
   antes desta onda** (registrado na memória da onda de design anterior).
8. **O board fixa os valores.** `design/padrao-2026-08/SPEC.md`: paleta dark
   (página `#0a100e`, cards `#101815`, elevado `#16211d`, hover `#1c2925`,
   bordas `#223029`/`#35493f`, texto `#e9f0ec`/`#9fb2aa`, accent `#3ad195`
   sobre `#062018`, accent-bg `#12271f`, info `#6cb8e0`/`#12242c`, warning
   `#e0a84e`/`#2a2214`, danger `#ef7070`/`#2a1616`); paleta light (página
   `#f2f6f4`, cards `#ffffff`, hover `#e9eeec`, bordas `#dde5e1`/`#9fb0a8`,
   texto `#17211d`/`#55645e`, accent `#0a7452` sobre `#ffffff`, accent-bg
   `#e2f2ec`, info `#0a5f8f`/`#e4eff5`, warning `#8a5a12`/`#f7efdd`, danger
   `#a51f1f`/`#f9e9e9`); raios chip 6 / controle 8 / card 12 / painel 16;
   sidebar 232px, topbar 60px; famílias Space Grotesk (display), IBM Plex
   Sans (corpo), IBM Plex Mono (dados); motion pulse-live 2s, slide-in
   240ms, shimmer 1.6s.

---

## Alegações normativas

Frases curtas, individualmente testáveis; uma vírgula é fronteira de
requisito. O acceptance spec codifica cada uma; as marcadas **[staging]**
são staging-safe (leitura pura) e rodam também contra
`https://stg-ninjasre.lan.kyo.ninja` depois do deploy do slot.

- **AN-01** No tema escuro, `--sunken` resolve para `#0a100e`, `--surface`
  para `#101815`, `--accent` para `#3ad195`. **[staging]**
- **AN-02** No tema claro, `--sunken` resolve para `#f2f6f4`, `--accent`
  para `#0a7452`. **[staging]**
- **AN-03** O `font-family` computado do corpo começa com "IBM Plex Sans".
  **[staging]**
- **AN-04** O `font-family` computado do H1 de qualquer página começa com
  "Space Grotesk". **[staging]**
- **AN-05** O `font-family` computado de um identificador (`inc_…`,
  `run_…`) começa com "IBM Plex Mono". **[staging]**
- **AN-06** Nenhum load de página do console dispara request para host
  externo — incluindo `fonts.googleapis.com` e `fonts.gstatic.com`.
  **[staging]**
- **AN-07** Todo chip de status carrega borda de 1px na cor do próprio
  papel semântico. **[staging]**
- **AN-08** As sete formas de status continuam desenhadas e distintas:
  círculo cheio, círculo oco, círculo esmaecido, quadrado, quadrado
  rotacionado, triângulo, traço. **[staging]**
- **AN-09** O chip "Ao vivo" carrega a marca pulsante quando o stream está
  conectado. **[staging]**
- **AN-10** Com `prefers-reduced-motion: reduce`, nenhuma animação de
  pulso, slide-in ou shimmer roda.
- **AN-11** A sidebar tem 232px, três grupos nomeados e o rodapé do
  guardião com a marca de estado. **[staging]**
- **AN-12** A topbar tem 60px e mantém, na ordem do board: busca, chip de
  frescor, tema, densidade, sino, parada de automação, Investigar, avatar.
  **[staging]**
- **AN-13** Os raios computados são 6px no chip retangular, 8px no
  controle, 12px no card, 16px no painel. **[staging]**
- **AN-14** Todo par texto/fundo da tabela de tokens alcança 4.5:1 e toda
  fronteira alcança 3:1, nos dois temas.
- **AN-15** O tema claro e o escuro declaram exatamente os mesmos nomes de
  token.
- **AN-16** Alternar o tema pelo botão da topbar troca `--accent` entre
  `#3ad195` e `#0a7452` sem reload. **[staging]**

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A paleta do board nos dois temas (Priority: P1)

Um operador abre qualquer tela do console e vê a paleta do board: página
quase-preta esverdeada com cards elevados no escuro, branco com verde
profundo no claro. Alterna o tema pelo botão e a troca é imediata e
completa — nenhum token fica para trás.

**Why this priority**: todo o resto da onda assenta nesses valores; uma
tela nova validada contra tokens velhos é retrabalho garantido.

**Independent Test**: abrir `/` no staging, ler
`getComputedStyle(document.documentElement)` para `--sunken`, `--surface`,
`--accent` nos dois temas e comparar com os hexes do board.

**Acceptance Scenarios**:

1. **Given** o tema escuro, **When** qualquer página renderiza, **Then**
   os tokens resolvem para os hexes da paleta dark do board (AN-01).
2. **Given** o tema claro, **When** a mesma página renderiza, **Then** os
   tokens resolvem para os hexes da paleta light (AN-02).
3. **Given** qualquer tema, **When** a tabela de contraste é avaliada,
   **Then** todo par alcança seu mínimo (AN-14).
4. **Given** o botão de tema, **When** o operador alterna, **Then** a
   troca acontece sem reload (AN-16).

---

### User Story 2 - As três famílias, sem sair de casa (Priority: P1)

O console fala Space Grotesk nos títulos e números, IBM Plex Sans no corpo
e IBM Plex Mono nos identificadores — servidas pelo próprio deployment,
sem nenhuma request a terceiro.

**Why this priority**: a tipografia é o que mais visivelmente separa o
board do console atual; e a propriedade "nenhuma request externa" é
inegociável (fato 3, DIVERGENCIAS.md §2).

**Independent Test**: carregar `/` com o network inspector do Playwright e
conferir (a) `font-family` computado dos três papéis, (b) zero requests
fora da origem.

**Acceptance Scenarios**:

1. **Given** qualquer página, **When** ela renderiza, **Then** corpo, H1 e
   identificadores computam as três famílias (AN-03..05).
2. **Given** o load completo de uma página, **When** as requests são
   listadas, **Then** nenhuma sai da origem do console (AN-06).
3. **Given** as fontes ainda não baixadas, **When** a página pinta,
   **Then** os fallbacks declarados seguram o texto (`font-display: swap`).

---

### User Story 3 - Chips com contorno, formas intactas (Priority: P1)

Todo chip de status ganha o contorno de 1px na cor do estado, sobre o
mesmo tint; as sete formas continuam exatamente as que eram.

**Why this priority**: o chip aparece em todas as telas; é a mudança de
maior alcance por linha de código, e é a divergência §1 registrada — feita
aqui, nenhuma feature de tela precisa reabri-la.

**Independent Test**: renderizar `Badge`, `StatusChip`, `ResolvedChip` e o
chip de frescor e medir `border-width`/`border-color` computados.

**Acceptance Scenarios**:

1. **Given** um chip de qualquer papel, **When** ele renderiza, **Then**
   carrega borda 1px na cor do papel (AN-07).
2. **Given** as sete formas, **When** renderizadas, **Then** cada uma
   mantém sua geometria (AN-08).
3. **Given** um leitor de tela, **When** encontra uma marca sozinha,
   **Then** ela continua nomeada como hoje (`role="img"`, `aria-label`).

---

### User Story 4 - Motion com propósito, e desligável (Priority: P2)

O chip "Ao vivo" pulsa quando o stream está de pé; um item novo entra com
slide-in de 240ms; uma barra de estágio ativo carrega shimmer. Quem pediu
`prefers-reduced-motion` não vê nada disso se mover.

**Why this priority**: é o que faz o produto parecer vivo — mas as
features de tela só podem usar primitivas que existirem aqui.

**Independent Test**: montar as três primitivas numa página de teste,
medir `animation-name` computado com e sem
`prefers-reduced-motion: reduce`.

**Acceptance Scenarios**:

1. **Given** o chip de frescor no estado live, **When** renderiza,
   **Then** carrega a marca pulsante (AN-09).
2. **Given** `prefers-reduced-motion: reduce`, **When** qualquer primitiva
   renderiza, **Then** nenhuma animação roda (AN-10).

---

### User Story 5 - O shell do board (Priority: P2)

A sidebar de 232px com os grupos e o rodapé do guardião, a topbar de 60px
com a ordem de controles do board, os ícones do set novo.

**Why this priority**: o shell aparece em toda tela; entregá-lo aqui dá às
features de tela um quadro já correto para preencher.

**Independent Test**: abrir qualquer tela no staging e comparar sidebar e
topbar com `Main.dc.html` (largura, grupos, ordem de controles, ícones).

**Acceptance Scenarios**:

1. **Given** qualquer tela, **When** renderiza, **Then** sidebar e topbar
   medem e ordenam como o board (AN-11, AN-12).
2. **Given** o item ativo da navegação, **When** renderiza, **Then**
   carrega o fundo `accent-bg`, o texto `accent` e a barra interna de 2px.

### Edge Cases

- **Um par da paleta nova abaixo do mínimo de contraste.** O contrato do
  fato 2 reprova. O valor do board não é editado silenciosamente: o
  implementer para, registra o par e o valor mínimo que passaria, e o
  operador decide na revisão — a divergência, se aceita, entra em
  `DIVERGENCIAS.md`. (Verificação prévia: os pares principais do board
  passam com folga; o risco real são os `*-bg` do tema claro.)
- **Fonte que não carregou** (primeiro paint, cache frio): os fallbacks de
  cada stack seguram o texto sem colapso de layout; `font-display: swap`.
- **`data-theme` ausente + sistema escuro**: o guard existente
  (`:root:not([data-theme="light"])`) continua valendo com os valores
  novos — comportamento já testado em `css.test.ts`, não muda.
- **Densidade compacta**: `DENSITY_METRICS` continua funcionando; o board
  não redefine densidade, então os dois modos apenas herdam os tokens
  novos.
- **O gate visual estava vermelho antes.** O re-baseline desta feature
  zera a régua: `accept` recaptura tudo, a revisão é o commit dos PNGs, e
  a cobertura vermelha pré-existente é registrada no controle — não
  debitada desta feature, mas também não escondida por ela.
- **Ícone usado por tela que esta feature não toca**: todo ícone mantém
  nome e assinatura (`IconProps`); só o desenho interno muda. Nenhum
  import quebra.

## Requirements *(mandatory)*

### Paleta

- **FR-001**: `console/src/design/tokens.ts` DEVE declarar, no tema dark:
  `sunken #0a100e`, `surface #101815`, `raised #16211d`, `hover #1c2925`,
  `border #223029`, `border-strong #35493f`, `text #e9f0ec`,
  `muted #9fb2aa`, `accent #3ad195`, `on-accent #062018`,
  `accent-bg #12271f`, `info #6cb8e0`, `info-bg #12242c`,
  `warning #e0a84e`, `warning-bg #2a2214`, `danger #ef7070`,
  `danger-bg #2a1616`, `neutral #a3b2aa`, `neutral-bg #0d1311`.
- **FR-002**: E no tema light: `sunken #f2f6f4`, `surface #ffffff`,
  `raised #ffffff`, `hover #e9eeec`, `border #dde5e1`,
  `border-strong #9fb0a8`, `text #17211d`, `muted #55645e`,
  `accent #0a7452`, `on-accent #ffffff`, `accent-bg #e2f2ec`,
  `info #0a5f8f`, `info-bg #e4eff5`, `warning #8a5a12`,
  `warning-bg #f7efdd`, `danger #a51f1f`, `danger-bg #f9e9e9`,
  `neutral #55645e`, `neutral-bg #f2f5f4`.
- **FR-003**: `success` DEVE seguir a família do accent nos dois temas
  (dark `#3ad195`, light `#0a7452`), como o board desenha resolvido/ok.
- **FR-004**: Os papéis `on-*` que o board não nomeia DEVEM usar a decisão
  desta spec: no tema dark, `on-info #062018`, `on-warning #17211d`,
  `on-danger #2a1616`, `on-neutral #0d1311`; no tema light, `on-info #ffffff`,
  `on-warning #ffffff`, `on-danger #ffffff`, `on-neutral #ffffff`.
  `on-accent` permanece `#062018` no dark e `#ffffff` no light. Como o
  FR-003 iguala `success` ao `accent` nos dois temas, `on-success` e
  `success-bg` DEVEM ser o mesmo par do accent — dark `on-success #062018`
  e `success-bg #12271f`, light `on-success #ffffff` e `success-bg #e2f2ec`
  — e não uma decisão nova do implementador. A tabela final completa
  (26 papéis × 2 temas) DEVE constar do controle e passar o contrato de
  contraste.
- **FR-005**: Todo par de `bodyPairs` DEVE alcançar 4.5:1 e todo par de
  `boundaryPairs` DEVE alcançar 3:1, nos dois temas, com a suíte de
  unidade existente verde.
- **FR-006**: Os dois temas DEVEM declarar exatamente os mesmos nomes de
  token (`declaredNames('light')` igual a `declaredNames('dark')`).
- **FR-007**: Nenhum componente do console DEVE carregar hex literal da
  paleta antiga após a troca; cor entra por token ou não entra.

### Geometria e elevação

- **FR-008**: `RADII` DEVE passar a `{1: 6, 2: 8, 3: 12, 4: 16}`.
- **FR-009**: `SHADOWS` DEVE ganhar os valores do board — dark
  `1: 0 1px 2px rgba(0,0,0,.4)`, `2: 0 8px 24px rgba(0,0,0,.35)`; light
  `1: 0 1px 2px rgba(17,22,28,.06)`, `2: 0 8px 24px rgba(17,22,28,.08)`.
- **FR-010**: `SHELL` DEVE fixar sidebar em 232px e topbar em 60px.

### Tipografia self-hosted

- **FR-011**: `console/public/fonts/` DEVE conter os woff2 (subset latin)
  de Space Grotesk 500/600/700, IBM Plex Sans 400/500/600 e IBM Plex Mono
  400/500, com licenças (OFL) ao lado.
- **FR-012**: `globals.css` DEVE declarar um `@font-face` por peso, com
  `font-display: swap`, apontando para `/fonts/…`.
- **FR-013**: `FONT_STACKS` DEVE ganhar a família `display` e passar a:
  `display: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif`;
  `sans: 'IBM Plex Sans', system-ui, sans-serif`;
  `mono: 'IBM Plex Mono', ui-monospace, SFMono-Regular, monospace` — e
  `css.ts` DEVE emitir `--family-display` junto das duas existentes.
- **FR-014**: `TYPE_STEPS` DEVE mapear títulos de página e números de
  display para a família display (H1 26px/700; números de KPI 30px/700),
  corpo 14px/1.5, meta 12.5px, micro 11px.
- **FR-015**: Nenhuma request de página do console DEVE sair da origem —
  o acceptance mede a lista de requests do load.
- **FR-016**: O HTML DEVE fazer preload dos woff2 dos pesos usados acima
  da dobra (display 700, sans 400/500, mono 400).

### Chips e formas

- **FR-017**: `ROLE_SKIN` em `status.tsx` DEVE somar `border` de 1px na
  cor do papel ao tint existente, para os cinco papéis.
- **FR-018**: `SHAPE_CLASS` NÃO DEVE mudar de geometria; as sete formas
  continuam as mesmas classes de desenho.
- **FR-019**: O contraste da borda do chip sobre o `*-bg` do papel DEVE
  alcançar 3:1 (o par já existe em `boundaryPairs`).
- **FR-020**: `ICON_SIZES` DEVE passar a `{inline: 14, nav: 18, head: 20,
  empty: 24}`.

### Ícones

- **FR-021**: Todo ícone de `icons.tsx` DEVE ser redesenhado no estilo do
  board: stroke 1.6, `stroke-linecap="round"`,
  `stroke-linejoin="round"`, grid 20, sem fill exceto onde o board usa
  (marca do logo, pontos de menu).
- **FR-022**: Nome e assinatura de todo ícone exportado DEVEM permanecer;
  nenhum consumidor muda de import.
- **FR-023**: Os desenhos DEVEM seguir os do board onde o board os mostra
  (grade do painel, relógio de incidentes, lupa de investigações, escudo
  de decisões, servidor de recursos, livro de conhecimento, pulso do
  agente, plugue de integrações, engrenagem de ajustes, sino, lupa da
  busca, mais, correr/parar).

### Motion

- **FR-024**: `globals.css` DEVE declarar as três primitivas do board:
  `pulse-live` (anel expandindo, 2s ease-out infinito), `slide-in`
  (translateY(-4px)+fade, 240ms ease-out), `stage-shimmer` (gradiente
  deslizando, 1.6s linear infinito) — nomes de classe utilitária
  documentados no próprio arquivo.
- **FR-025**: `DURATIONS` DEVE registrar os três tempos; os keyframes
  DEVEM ler os tempos por `var(--dur-…)`.
- **FR-026**: Sob `prefers-reduced-motion: reduce`, as três primitivas
  DEVEM resolver para `animation: none`.
- **FR-027**: O `Mark` do `AutoRefresh` (estado live) DEVE usar
  `pulse-live`.

### Shell

- **FR-028**: A sidebar DEVE medir 232px, com os três grupos da navegação
  rotulados pelo catálogo i18n (en: "Now / The environment /
  Configuration"; pt-BR: "Agora / Ambiente / Configuração") e o rodapé do
  guardião ("Guardião ativo · só propõe" / "Guardian active ·
  propose-only") com `StatusDot` pulsante quando ativo.
- **FR-029**: O item ativo DEVE renderizar fundo `accent-bg`, texto
  `accent` e barra interna de 2px (`box-shadow: inset 2px 0 0` no token
  accent), como `Main.dc.html` desenha "Painel".
- **FR-030**: A topbar DEVE manter os controles existentes na ordem do
  board: busca (máx. 420px), chip de frescor, tema, densidade, sino com
  contador, parada de automação, Investigar (primário), avatar — nenhum
  controle removido, nenhum adicionado.
- **FR-031**: O logotipo DEVE ser o do board (`Main.dc.html`): a marca
  shuriken em accent com o miolo vazado, "Ninja" em texto e "SRE" em
  accent, família display.

### Artefatos e gates

- **FR-032**: O tema Tailwind em `globals.css` DEVE ser atualizado junto
  da tabela; `css.test.ts` verde nas duas direções.
- **FR-033**: As baselines visuais DEVEM ser recapturadas
  (`python -m tools.console_visual accept`) e comitadas; o diff de PNGs é
  a revisão.
- **FR-034**: Strings novas DEVEM entrar no catálogo i18n em `en` e
  `pt-BR`; nenhuma string de UI hardcoded.
- **FR-035**: Esta feature NÃO DEVE tocar telas de área (`surfaces/screens/*`
  além do que o shell exige), rotas, dados ou gateway — fundação apenas.

### Key Entities

- **Token** — um nome de papel (`accent`, `sunken`, `corner-2`) com um
  valor por tema, declarado na tabela única e emitido como custom
  property. A fronteira desta feature: valores mudam, nomes só ganham
  (`family-display`), nenhum nome morre.
- **Primitiva de motion** — um par keyframes+classe utilitária com
  duração tokenizada e desligamento por media query. Três nesta onda.
- **Forma de status** — geometria portadora de significado, intocada;
  ganha contorno quando dentro de chip.

## Success Criteria *(mandatory)*

- **SC-001**: As 16 alegações normativas passam no harness local; as 13
  marcadas [staging] passam contra `https://stg-ninjasre.lan.kyo.ninja`
  depois do deploy do slot.
- **SC-002**: O acceptance foi confirmado vermelho antes da implementação,
  com a mensagem real de cada alegação registrada.
- **SC-003**: `make verify` verde tendo partido de verde; nenhum gate
  afrouxado.
- **SC-004**: Zero requests a host externo no load de `/`, `/incidents` e
  `/runs`, medido pelo acceptance nos dois ambientes.
- **SC-005**: Evidência visual do slot: capturas Orca browser do shell nos
  dois temas em `specs_v8/000-fundacao-visual/evidence/visual/`, com
  `VEREDITO.md` linha a linha CONFORME contra `Main.dc.html` (protocolo
  EXECUCAO.md §3).
- **SC-006**: Baselines visuais recapturadas e comitadas na mesma entrega
  que muda os tokens — nenhum commit intermediário com gate visual
  reprovando por design.
- **SC-007**: A tabela completa 26×2 do FR-004 está no controle da
  feature, com cada valor rastreável ao board ou à decisão de contraste.

## Assumptions

- **O board manda nos valores; a tabela manda nos nomes.** O board não
  conhece os 26 papéis — a tradução (fato 8 → FR-001/002) é desta spec, e
  papéis que o board não nomeia seguem o contrato de contraste (FR-004).
- **Nenhuma tela de área é validada aqui.** As telas herdarão os tokens e
  parecerão "quase o board" até suas features chegarem; o gate visual
  desta feature olha o shell e os componentes, não o miolo das páginas.
- **Os woff2 entram no repositório.** 8 arquivos × ~30-60KB, licença
  OFL; o peso no clone é aceito em troca de zero dependência externa.
- **A imagem pinada do gate visual rasteriza as fontes novas** — elas vêm
  no bundle, não do sistema, então a captura é estável por construção.
- **Esta feature é dona de `tokens.ts`, `css.ts`, `icons.tsx`,
  `status.tsx`, `globals.css` e `public/fonts/`;** esses arquivos congelam
  depois do S0. Os single-write (`i18n/*.ts`, `routes.ts` e
  `screens.json`) seguem o mapa por slot de `EXECUCAO.md §2`, e não são
  propriedade exclusiva desta feature.

## Dependencies

- Nenhuma feature antes dela; é o S0 da onda.
- Toda feature de console da onda depende dela: 010 (chip de frescor),
  020 (—), 030/040/050/060/070 (tokens, chips, ícones, motion, shell).
- `tools/spec_validation browser --backing staging` (entregue pela v7)
  é pré-existente e usado no fechamento do slot.

## Out of Scope

- Qualquer tela de área (Painel, Incidentes, Runs, Decisões, Recursos,
  Conhecimento, O agente) — features 030–070.
- O canal SSE e qualquer mudança no `AutoRefresh` além da marca pulsante
  — feature 010.
- Títulos de run — feature 020.
- Remoção do `stylesheet()` server-side de `surfaces/console/theme.py`
  (paleta azul legada; DIVERGENCIAS.md §5) — fica como está até a tela
  que ele serve ser tocada.
- Densidade nova, breakpoints novos, dark/light além dos dois temas.
