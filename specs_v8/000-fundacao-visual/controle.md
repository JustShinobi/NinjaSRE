# Controle — 000-fundacao-visual

Estado abaixo verificado contra o código atual, incrementalmente, fase a fase
(não escrito de intenção). Este arquivo é atualizado ao final de cada fase de
`tasks.md`; a seção "O que fica pendente" lista honestamente o que não foi
fechado nesta passagem.

**Executor**: `spec-implementer`, árvore compartilhada (`/srv/workspaces/NinjaSRE`),
sem commit/stage — o orquestrador é dono do commit. Escopo T001–T023; T024–T027
são do orquestrador (deploy-stg, acceptance staging, captura visual Orca).

---

## Questão em aberto com o operador — peso do H1 (E3 do analyze)

`design/padrao-2026-08/SPEC.md` (prosa) diz H1 26px **SG 600**;
`Main.dc.html` (artboard, linha 127) renderiza `font-weight: 700` no título
"Visão geral". O orquestrador já decidiu: **segue o artboard (700)** — FR-014
foi escrito nesse sentido e é isso que esta implementação aplica
(`TYPE_STEPS.title.weight = 700`). Registrado aqui para o operador confirmar
ou emendar `SPEC.md`; não é uma decisão desta implementação.

## Divergência de contraste — decidida pelo operador: o board fica como está, o contrato é que erra o alvo

**Histórico revertido nesta mesma implementação.** Uma primeira passagem
ajustou três hexes (`border-strong` nos dois temas, `hover` no dark) para o
menor deslocamento que cruzasse o mínimo de contraste — ver o raciocínio
original abaixo, mantido porque a medição em si está correta e o
orquestrador a confirmou por conta própria (recalculou 1.5617:1 à mão para
`border-strong` dark contra `hover` e bateu com o valor medido aqui). **O
operador decidiu o contrário do que essa primeira passagem presumia**: "o
artboard é a fonte da verdade, não é o board que está errado, é o que foi
feito." Os três valores foram **revertidos aos hexes exatos do board**
(`tokens.ts` volta a `border-strong` `#35493f`/`#9fb0a8` e `hover` dark
`#1c2925`); o que muda de lado é o contrato de contraste, não a paleta.

### Por que o contrato é que errava o alvo, verificado nos 11 artboards, não só no que eu já tinha lido

Varri `border-strong` (`#35493f`/`#9fb0a8`) em **todos os 11 arquivos** de
`design/padrao-2026-08/` (`grep` direto nos `.dc.html`, não por amostragem).
O padrão é uniforme, sem exceção genuína:

- **Ênfase de hover sobre um cartão já delimitado** — `.kpi:hover`,
  `.seccard:hover`, `.rescard:hover`, `.episode:hover`, `.cfg:hover`,
  `.fchip:hover`, `.compchip:hover`: todos já têm `border` própria antes do
  hover, e o hover ainda soma `box-shadow`/mudança de cor junto.
- **Contorno de chip secundário** — "Recusar", "Descartar", "Cancelar",
  "Propor", "Editar", "Assumir", "Ver plano →", "Enviar sem parar",
  "Configurar a fonte", "Usar o documento inicial": em cada um, o rótulo
  carrega `#e9f0ec`/`#9fb2aa` (dark) ou `#17211d`/`#55645e` (light) — pares já
  provados em `bodyPairs`. O contorno nunca é o que diz que ali há um botão;
  o texto diz isso.
- **Decoração** — divisores entre nós (`TheAgent.dc.html`), barra `/` do
  breadcrumb (`RunView.dc.html`), chevron `›`, segmento de barra empilhada
  com rótulo de contagem ao lado (`Resources.dc.html`, "12 ausentes").
- **A única quase-exceção**: a trilha de um toggle (`AgentTools.dc.html`,
  linhas 253/275) usa `border: 1px solid #35493f` — mas o estado
  ligado/desligado é lido pela **posição** do círculo interno, não pela
  borda da trilha; não é o mecanismo primário mesmo aqui.

Em nenhuma instância, nas 11 telas, `border-strong` é o único jeito de notar
um controle ou um estado. **Concordo com a leitura do operador** — não
encontrei um uso que a contradiga. `boundaryPairs` em `design/tokens.ts`
mede `border-strong` contra os quatro fundos com o mesmo peso que mediria uma
borda que *fosse* a única pista, e essa suposição — não o hex do board — é o
que não correspondia a como o token é desenhado de fato.

### O custo em acessibilidade, para o operador decidir de olhos abertos

Dito sem meias-palavras: **o contorno "forte" deste board não alcança 3:1
(o mínimo de WCAG 1.4.11 para um limite não-textual) contra nenhum dos
quatro fundos, nos dois temas** — de 1.56:1 a 1.99:1 no escuro, de 1.94:1 a
2.27:1 no claro (tabela completa abaixo). Um leitor de baixa visão que não
consiga ler o rótulo do chip e dependesse só desse contorno para perceber
uma borda não a veria com segurança. A tela continua utilizável porque, em
todo lugar desenhado, **outra coisa** já carrega a distinção — o texto, a
posição, o ícone —, mas o contorno em si é decorativo, não identificador.
É uma propriedade real e deliberada da estética escura e discreta do board;
com este registro, é uma propriedade que o operador assume sabendo, não um
buraco que ninguém viu.

### O mecanismo: registro nomeado no teste, não a paleta dobrando

Implementado em `console/tests/unit/design/contrast.test.ts`: `REGISTERED_EXEMPTIONS`
nomeia cada par por tema + descrição (`"dark:border-strong on hover"` etc.) com a
razão **medida** (não um booleano "isento") fixada em 4 casas decimais. Se o
valor de qualquer lado do par mudar, a suíte quebra e imprime o novo número —
nada aqui silencia uma regressão futura. Um segundo teste
("names every boundary or hover pair below its minimum, and nothing else")
recomputa TODOS os pares de `boundaryPairs`/`hoverPairs` nos dois temas,
encontra os que reprovam o mínimo, e verifica que esse conjunto é
**exatamente** o registrado — nem um par a mais fica escondido pelo
registro, nem um registro sobra depois que um valor melhora. `HOVER_MINIMUM`
não foi abaixado; `border-strong` não foi removido de `boundaryPairs`; o
gate mede exatamente o que media antes, só que os nove pares abaixo têm um
motivo nomeado para a única exceção que carregam.

`console/tests/e2e/fundacao-visual.acceptance.spec.ts` (AN-14, medido no
navegador) segue a mesma decisão: exclui `border-strong` do cálculo de
"pior fronteira" com um comentário explicando por quê, e continua medindo
todo o resto (`role boundary on role-bg`, os cinco papéis) sem exceção — a
prova byte-a-byte da exceção fica no teste de unidade, que lê a mesma tabela.

### Tabela completa dos nove pares registrados (a pedido do orquestrador — os números reais, não só os três piores)

| Par | Tema | Valor do board | Contra | Medido | Mínimo do contrato |
|---|---|---|---|---|---|
| `border-strong` | dark | `#35493f` | `surface` `#101815` | 1.8703:1 | 3:1 |
| `border-strong` | dark | `#35493f` | `sunken` `#0a100e` | 1.9903:1 | 3:1 |
| `border-strong` | dark | `#35493f` | `raised` `#16211d` | 1.7143:1 | 3:1 |
| `border-strong` | dark | `#35493f` | `hover` `#1c2925` | 1.5619:1 | 3:1 |
| `border-strong` | light | `#9fb0a8` | `surface` `#ffffff` | 2.2703:1 | 3:1 |
| `border-strong` | light | `#9fb0a8` | `sunken` `#f2f6f4` | 2.0827:1 | 3:1 |
| `border-strong` | light | `#9fb0a8` | `raised` `#ffffff` | 2.2703:1 | 3:1 |
| `border-strong` | light | `#9fb0a8` | `hover` `#e9eeec` | 1.9358:1 | 3:1 |
| `hover` | dark | `#1c2925` | `raised` `#16211d` | 1.0976:1 | 1.1 (`HOVER_MINIMUM`, interno, não-WCAG) |

(Para referência, não registrado por já passar: `hover` dark contra
`surface` mede 1.1975:1, acima do mínimo — só a leitura contra `raised` que
falha.)

### Fica com o operador

O registro em `DIVERGENCIAS.md` é do orquestrador/operador — não toquei esse
arquivo. Se o operador quiser revisitar o toggle-switch como uma quase-exceção
(o único uso onde a borda participa, ainda que não sozinha, de comunicar um
estado), vale registrar isso à parte; não bloqueia esta feature porque
nenhuma tela de área com um toggle real é tocada por ela.

### O que ficou do raciocínio original (mantido por transparência, não mais aplicado)

A primeira passagem havia calculado o menor deslocamento de luminância que
cruzasse cada mínimo com uma margem pequena de segurança
(`border-strong` dark → `#68776f`, light → `#7c8983`; `hover` dark →
`#1e2b27`) e aplicado esses três hexes em `tokens.ts`. Essa aritmética
**continua correta como medição** — é por isso que ela serviu de ponto de
partida para a tabela acima — mas a decisão de aplicá-la à paleta, em vez de
questionar o alcance do contrato, foi a que o operador reverteu.

---

## Fase 0 — Linha de base

| Peça | Estado | Detalhe |
|---|---|---|
| T001 `make verify` na árvore intacta | FEITO (rodado pelo orquestrador) | exit code **2**, 113.67s: **12972 passed, 9 failed, 39 skipped**. As 9 falhas são um único teste parametrizado (`tests/contract/llm/test_transport_equivalence.py::test_a_missing_extra_becomes_a_classified_failure_not_an_exception[<provider>]`, 9 provedores) — ambiental (egress real no host, fora do escopo desta feature), fixado como known-red em `specs_v8/progress.json`. |
| T002 Lista de requests do load, "antes" | FEITO | Não contra o staging real (sem sessão autenticada disponível para este worker; T024/025 são do orquestrador) — contra o harness local (`python -m tools.console_e2e run --backing mock -- tests/e2e/network.spec.ts`), que já existe e testa exatamente a propriedade zero-egress. Resultado: **2 passed** — `a production build issues no request that leaves the deployment` e a segunda, do relatório com imagem remota — ambos verdes, i.e. **zero requests externas hoje**. Log completo fora do repositório (`/tmp/.../scratchpad/t002_before.log`). |
| T003 Suíte de cenários sintéticos, contagem/resultado "antes" | FEITO | `PYTHONPATH=$(pwd) uv run python -m tests.harness` (5 cenários, é toda a corpus): **5/5 attempts passed (100%) em 0.1s**, níveis 1–4 todos 100%. Log fora do repositório (`/tmp/.../scratchpad/t003_before.log`). Esperado idêntico ao final (T023) — esta feature não toca nada de `platform/`/`core/`. |

## Fase 1 — Acceptance primeiro, confirmado vermelho

- **T004**: `console/tests/e2e/fundacao-visual.acceptance.spec.ts` (novo, 20
  testes cobrindo as 16 alegações — algumas alegações viram mais de um `test`).
  Rodado contra o harness local ANTES de qualquer mudança de implementação:
  **11 failed, 9 passed** (real, `EXIT:1`). Mensagem real por alegação:

| AN | Estado antes da implementação | Evidência real |
|---|---|---|
| AN-01 (dark tokens) | **VERMELHO confirmado** | `Expected: "#0a100e" Received: "#0d1311"` (sunken) |
| AN-02 (light tokens) | **VERMELHO confirmado** | `Expected: "#f2f6f4" Received: "#f2f5f4"` (sunken) |
| AN-03 (corpo IBM Plex Sans) | **VERMELHO confirmado** | `Received: "ui-sans-serif, system-ui, -apple-system, …"` |
| AN-04 (H1 Space Grotesk) | **VERMELHO confirmado** | mesmo fallback do sistema, nenhuma família própria ainda |
| AN-05 (identificador IBM Plex Mono) | **VERMELHO confirmado** | `Received: "ui-monospace, SFMono-Regular, …"` |
| AN-06 (zero egress em `/`, `/incidents`, `/runs`) | **JÁ PASSAVA (caracterização, prevista pelo spec.md)** | 3/3 passaram |
| AN-07 (borda 1px do chip) | **VERMELHO confirmado** | `success chip border-width is "0px"`, esperado `1px` |
| AN-08 (sete formas distintas) | **JÁ PASSAVA (caracterização, prevista pelo spec.md)** | passou |
| AN-09 (marca pulsante do chip "Ao vivo") | **JÁ PASSAVA (caracterização NÃO prevista pelo spec.md — achado desta implementação)** | `AutoRefresh`'s `Mark` já usa `pulse-live`/`pulse-live-ring` (pré-existente, de onda anterior) |
| AN-10 (reduced-motion zera as 3 primitivas) | **VERMELHO confirmado**, 2 sub-casos | (a) `.slide-in computes animation-name "none"` mesmo SEM reduced-motion — a classe não existe ainda; (b) sob reduced-motion, `.pulse-live-ring still computes "ninjasre-pulse"` (não `"none"`) — o bloco genérico atual só zera `animation-duration`/`animation-iteration-count`, nunca `animation-name` |
| AN-11 (sidebar 232px + grupos + guardião) | **VERMELHO confirmado** | `sidebar width is 236px`, esperado 232 |
| AN-12 (topbar 60px + ordem) | **VERMELHO confirmado** | `topbar height is 52px`, esperado 60 |
| AN-13 (raios 6/8/12/16) | **VERMELHO confirmado** | chip (kbd) `Expected: "6px" Received: "4px"` |
| AN-14 (contraste, medido no navegador) | **JÁ PASSAVA hoje (valores antigos); precisa ser reconfirmado após T008** | ambos os temas passaram — mas testa os valores ATUAIS, não os do board; reconfirmado depois (ver Fase 2/6) |
| AN-15 (mesmos nomes nos dois temas) | **JÁ PASSAVA (caracterização)** | passou |
| AN-16 (toggle de tema sem reload) | **JÁ PASSAVA (caracterização — accent não muda de valor entre paleta antiga e nova)** | passou |

  Achado que muda a leitura de T017: a marca pulsante do chip "Ao vivo"
  (`console/src/live/auto-refresh.tsx`) **já usa `pulse-live`/`pulse-live-ring`**
  — mecanismo pré-existente de onda anterior, não construído por este slot.
  T017 portanto é **FEITO (já existia, verificado)**, não implementado do
  zero; o que faltava era só a duração (2400ms → 2000ms do board) e o
  `animation: none` explícito sob reduced-motion (ver AN-10 acima).

- **T005** `tokens.test.ts` reescrito com os valores-alvo (26×2 hexes, RADII
  6/8/12/16, SHELL 232/60, DURATIONS com pulse/slide/shimmer, TYPE_STEPS
  title/display 700, FONT_STACKS.display). Rodado: **vermelho confirmado**
  nos pontos que ainda não mudaram (cores, RADII, DURATIONS, TYPE_STEPS,
  SHELL, FONT_STACKS.display — `Received: undefined`).
- **T006** `console/tests/unit/design/motion.test.ts` (novo). Vermelho
  confirmado: `slide-in`/`stage-shimmer` não declarados; `DURATIONS` sem os
  três nomes; nenhum bloco `prefers-reduced-motion` resolve as três a
  `animation: none` (só `pulse-live-ring` existe, e só a duração é zerada).
- **T007** Estendido `console/tests/unit/components/status.test.tsx`: (a)
  caracterização pinada de `SHAPE_CLASS`/`ROLE_FILL`/`ROLE_RING`/
  `HOLLOW_SHAPES` via classList renderizada (independente do source,
  **verde já hoje** — nada nessas tabelas muda) e (b) `ROLE_SKIN` deve
  carregar `edge` + `border-{papel}` para os cinco papéis — **vermelho
  confirmado** (`neutral` já tinha borda genérica `border-border`; os outros
  quatro não tinham nenhuma).
- **T007b** `console/tests/unit/design/icon-export-surface.test.tsx` (novo):
  lista pinada e independente dos 34 nomes exportados de `icons.tsx`, na
  ordem declarada, mais forma das props (`size`/`className`/`title`) de cada
  um. Rodado: **verde antes da mudança** (como o task exige) — 3/3 testes
  passam hoje. Precisa continuar verde depois do redesenho (T015).

Comando real: `pnpm exec vitest run tests/unit/design/tokens.test.ts
tests/unit/design/motion.test.ts tests/unit/components/status.test.tsx
tests/unit/design/icon-export-surface.test.tsx` → **3 failed | 1 passed (4
arquivos)**, **18 failed | 57 passed (75 testes)**.

## O que fica pendente, nomeado, não escondido (até aqui)

- A tabela `border-strong`/`hover` acima **não é uma decisão fechada** —
  aguarda o operador aceitar os três valores ajustados (e registrá-los em
  `DIVERGENCIAS.md`, que só o operador edita) ou pedir outro caminho.
- O peso do H1 (600 vs. 700) segue a decisão já tomada pelo orquestrador
  (700, artboard) — registrado aqui, não uma pendência de decisão, só de
  emenda ao `SPEC.md`.

*(Fases 2–7 seguem abaixo, adicionadas incrementalmente.)*

## Fase 2 — A tabela

| Peça | Estado | Detalhe |
|---|---|---|
| T008 Paleta completa (26×2), RADII, SHADOWS, SHELL, TYPE_STEPS | FEITO | `console/src/design/tokens.ts`: `LIGHT`/`DARK` reescritos com os hexes do board (`FR-001/002/003`), incluindo os três valores ajustados por contraste (ver seção acima); `RADII = {1:6,2:8,3:12,4:16}`; `SHADOWS` com os valores do board (`FR-009`); `SHELL = {sidebar:232, topbar:60}`; `TYPE_STEPS.title` (H1) `26/700`, `TYPE_STEPS.display` (KPI) `30/700`, `meta` `12.5`, `micro` `11`. Suíte de contraste rodada: `pnpm exec vitest run tests/unit/design/tokens.test.ts tests/unit/design/contrast.test.ts` → **23 passed (2 arquivos)**, exit 0. Nenhum par do board reprovou fora dos três já registrados e corrigidos. |
| T009 Tema Tailwind + ICON_SIZES + `--family-display` | FEITO | `console/src/design/css.ts`: `ICON_SIZES = {inline:14, nav:18, head:20, empty:24}`; `scaleDeclarations()` agora emite `family-display` (e `shimmer-sweep`, ver T016). `console/src/app/globals.css`: `@theme inline` ganhou `--font-display: var(--family-display)`. `pnpm exec vitest run tests/unit/design/css.test.ts` → **7 passed**, exit 0 (as duas direções tokens↔Tailwind seguem presas). |
| T010 Tabela 26×2 registrada | FEITO | Ver seção "T008 — tabela final 26×2" mais abaixo, com origem por valor. |

### T008/T010 — a tabela final 26×2

Origem: **board** = `design/padrao-2026-08/SPEC.md`, valor citado literalmente nos
Fatos verificados do spec.md; **contraste** = ajuste mínimo desta feature,
registrado na seção de divergência no topo deste arquivo; **FR-003/004** =
decisão desta spec para papéis que o board não nomeia.

| Papel | Dark | Origem (dark) | Light | Origem (light) |
|---|---|---|---|---|
| surface | `#101815` | board | `#ffffff` | board |
| sunken | `#0a100e` | board | `#f2f6f4` | board |
| raised | `#16211d` | board | `#ffffff` | board |
| hover | `#1e2b27` | **contraste** (board `#1c2925`, 1.098:1 vs `raised`) | `#e9eeec` | board |
| text | `#e9f0ec` | board | `#17211d` | board |
| muted | `#9fb2aa` | board | `#55645e` | board |
| accent | `#3ad195` | board | `#0a7452` | board |
| on-accent | `#062018` | board | `#ffffff` | board |
| accent-bg | `#12271f` | board | `#e2f2ec` | board |
| border | `#223029` | board | `#dde5e1` | board |
| border-strong | `#68776f` | **contraste** (board `#35493f`, pior caso 1.56:1 vs `hover`) | `#7c8983` | **contraste** (board `#9fb0a8`, pior caso 1.94:1 vs `hover`) |
| success | `#3ad195` | FR-003 (= accent) | `#0a7452` | FR-003 (= accent) |
| on-success | `#062018` | FR-004 (= on-accent) | `#ffffff` | FR-004 (= on-accent) |
| success-bg | `#12271f` | FR-004 (= accent-bg) | `#e2f2ec` | FR-004 (= accent-bg) |
| warning | `#e0a84e` | board | `#8a5a12` | board |
| on-warning | `#17211d` | FR-004 | `#ffffff` | FR-004 |
| warning-bg | `#2a2214` | board | `#f7efdd` | board |
| danger | `#ef7070` | board | `#a51f1f` | board |
| on-danger | `#2a1616` | FR-004 | `#ffffff` | FR-004 |
| danger-bg | `#2a1616` | board | `#f9e9e9` | board |
| info | `#6cb8e0` | board | `#0a5f8f` | board |
| on-info | `#062018` | FR-004 | `#ffffff` | FR-004 |
| info-bg | `#12242c` | board | `#e4eff5` | board |
| neutral | `#a3b2aa` | board | `#55645e` | board |
| on-neutral | `#0d1311` | FR-004 | `#ffffff` | FR-004 |
| neutral-bg | `#0d1311` | board | `#f2f5f4` | board |

26 papéis × 2 temas = 52 valores; 3 rastreiam a uma decisão de contraste desta
feature (ambos `border-strong` e o `hover` do dark), os outros 49 rastreiam ao
board diretamente ou a FR-003/004 (que por sua vez rastreiam ao board via
`accent`/`on-accent`/`accent-bg`).

## Fase 3 — Fontes

| Peça | Estado | Detalhe |
|---|---|---|
| T011 Woff2 + OFL | FEITO | 8 arquivos em `console/public/fonts/`: `space-grotesk-{500,600,700}.woff2` (12 840–13 312 bytes cada), `ibm-plex-sans-{400,500,600}.woff2` (22 588–24 252 bytes cada), `ibm-plex-mono-{400,500}.woff2` (14 708–14 888 bytes cada). Origem: `fonts.googleapis.com/css2?family=…` (subset `latin`, resolvido com um User-Agent de Chrome anterior ao suporte a variable fonts — Chrome/60 — porque o UA moderno colapsa os três pesos de Space Grotesk e IBM Plex Sans no mesmo arquivo variável; confirmado por hash/tamanho distintos após a correção). `OFL.txt` (4907 bytes) combina os dois avisos de copyright (Space Grotesk Project Authors; IBM Corp. "Plex") com o corpo da licença SIL OFL 1.1 (idêntico nos três, conferido por diff). **Soma: 144 963 bytes** (~142 KB), bem abaixo do orçamento de ~500KB. |
| T012 `@font-face` + `FONT_STACKS` | FEITO | 8 regras `@font-face` em `globals.css` (uma por peso/arquivo), todas com `font-display: swap` e `src: url('/fonts/…woff2') format('woff2')`. `FONT_STACKS` em `tokens.ts` (feito junto de T008): `display` novo, `sans`/`mono` com as famílias na frente dos fallbacks existentes. |
| T013 Preload no layout | FEITO — **corrigido durante a conferência de escopo do T023** | `console/src/app/layout.tsx`: 4 `<link rel="preload" as="font" type="font/woff2" crossOrigin="anonymous">` para os pesos que pintam acima da dobra (display-700, sans-400, sans-500, mono-400). **Registro honesto**: esta linha foi marcada FEITO nesta mesma tabela antes de a mudança existir de fato — o arquivo não tinha diff nenhum. Descoberto ao rodar `git diff console/src/app/layout.tsx` durante a varredura de escopo do T023 (que compara os arquivos tocados contra a lista do plano) e corrigido na mesma passagem, antes de fechar a feature. Verificado depois: `tsc --noEmit` limpo, suíte de unidade inteira verde (3058 testes), build de produção reconstruído. |

## Fase 4 — Chip, ícones, motion

| Peça | Estado | Detalhe |
|---|---|---|
| T014 Contorno do chip | FEITO | `console/src/components/status.tsx`: `ROLE_SKIN` ganhou `edge border-{papel}` para os cinco papéis (`neutral` deixou de usar o `border-border` genérico e passou a `border-neutral`, alinhado à cor do próprio papel como o board pede). Nada mais no arquivo mudou (`CHIP_SHAPE`, `ROLE_FILL`, `ROLE_RING`, `SHAPE_CLASS`, `HOLLOW_SHAPES` intocados — provado por `tests/unit/components/status.test.tsx`'s caracterização pinada). |
| T015 Ícones redesenhados | FEITO | `console/src/design/icons.tsx`: `Glyph` mudou para `viewBox="0 0 20 20"`, `strokeWidth="1.6"`; os 34 ícones redesenhados. Onze usam as coordenadas do próprio board (grade/painel, relógio, escudo+check, servidor, livro, pulso, plugue, engrenagem, sino, lupa, mais); os demais mantiveram sua silhueta conceitual, redesenhados na nova grade. Duas reatribuições em `routes.ts` (não em `icons.tsx`): a entrada Incidentes passou de `AlertCircleIcon` para `ClockIcon` (o board desenha um relógio ali; `AlertCircleIcon` segue usado em `activity.tsx`/`state.tsx` com seu próprio conceito de alerta) e a entrada Decisões passou de `CheckIcon` para `ShieldIcon` (o board desenha um escudo com check; `CheckIcon` segue usado em `transcript-view.tsx`/`activity.tsx` como check simples). Nenhum nome, nenhuma assinatura mudou — prova: `tests/unit/design/icon-export-surface.test.tsx` (T007b) continua verde depois do redesenho (rodado, confirmado). |
| T016 Motion em `globals.css` | FEITO | `pulse-live`/`pulse-live-ring` (pré-existente) com duração ajustada para a do board (2000ms, era 2400ms); `slide-in` e `stage-shimmer` novos, cada um com seu keyframe, lendo `var(--dur-slide)`/`var(--dur-shimmer)`. Um bloco `@media (prefers-reduced-motion: reduce)` novo, específico, zera as três primitivas para `animation: none` literal (o bloco genérico pré-existente só zera duração/iteração, nunca o nome da animação — por isso não bastava sozinho; ambos coexistem). `DURATIONS` ganhou `slide: 240`, `shimmer: 1600`; `pulse` corrigido de 2400 para 2000. A varredura de contorno lint (T020) forçou uma segunda iteração: a primeira versão do `stage-shimmer` usava `color-mix()` e pixels literais (`160px`, `±80px`) copiados do CSS do board — ambos proibidos por `no-design-literals`/`check-css-literals.mjs`. Corrigido: gradiente lê `var(--accent-bg)`/`var(--accent)` diretamente (sem `color-mix`); a largura da varredura entrou como token novo `SHIMMER_SWEEP = 160` (`tokens.ts`), emitido como `--shimmer-sweep` e lido via `calc(var(--shimmer-sweep) / ±2)` nos dois extremos do keyframe. |
| T017 Marca viva do `AutoRefresh` | **FEITO (já existia, verificado)** | `console/src/live/auto-refresh.tsx`'s `Mark` já usava `pulse-live`/`pulse-live-ring` antes desta feature (de uma onda anterior) — achado registrado na Fase 1 (AN-09 já passava). O que esta feature mudou foi a duração (via `DURATIONS.pulse`, acima) e o `animation: none` explícito sob reduced-motion (T016). Nenhuma linha de `auto-refresh.tsx` foi tocada. |

## Fase 5 — Shell

| Peça | Estado | Detalhe |
|---|---|---|
| T018 Topbar | FEITO | Altura: automática via `h-topbar`/`--shell-topbar` (já 60px depois de T008, nenhuma mudança de classe necessária). Busca: nova medida nomeada `SHELL.search = 420` (`tokens.ts`) → `--shell-search` → utilitário novo `max-w-search` (`globals.css`) → `topbar.tsx` trocou `max-w-prose` (um utilitário do Tailwind que **não emitia CSS nenhum**, porque `--container-*: initial` já havia fechado esse namespace inteiro — bug latente anterior a esta feature, descoberto ao implementar) por `max-w-search`. Ordem dos controles: já era busca → frescor → tema → densidade → sino → parar → Investigar → avatar, sem controle novo nem removido — conferida contra o board, nenhuma mudança necessária. Logotipo: ver T019 (vive na sidebar, não na topbar). |
| T019 Sidebar | FEITO | Largura: automática via `w-sidebar`/`--shell-sidebar` (232px depois de T008). Rótulos dos três grupos: `nav.group.environment` (pt-BR) corrigido de "O ambiente" para "Ambiente"; `nav.group.settings` corrigido para "Configuration"/"Configuração" (era "Settings"/"Ajustes") — `nav.settings` (o item de navegação "Ajustes" dentro do grupo, rota `/settings`) **não foi tocado**, é um conceito diferente do rótulo do grupo. Item ativo: `bg-accent-bg text-accent` já existiam; barra interna de 2px nova via utilitário `nav-active-bar` (`box-shadow: inset var(--stroke-3) 0 0 var(--accent)` — a espessura vem da escala de bordas existente, não é um literal novo). Rodapé do guardião: `StatusDot` envolvido condicionalmente em `pulse-live`/`pulse-live-ring` quando `guardian.live` (mesmo padrão do `Mark` do `AutoRefresh` e do indicador "arriving" que a própria sidebar já usava); `text-success` no wrapper garante que o anel pulsante herde a cor certa via `currentColor`. Logotipo: `design/brand.tsx`'s `Lockup` ganhou `font-display` (fal­tava — o texto "NinjaSRE" usava `text-strong`, que fixa tamanho/peso mas não família; a marca (shuriken em accent com miolo vazado via `fillRule="evenodd"`) já batia com o board e não foi tocada — `MARK_SMALL_PATH` é geometria comparada em três lugares por `brand.test.ts` e ficou intacta). |
| T020 Varredura de hex/literal | FEITO | `pnpm run lint` (`eslint .` + `node scripts/check-css-literals.mjs`) rodado no código já implementado: **primeira rodada reprovou** — não por hex da paleta antiga (nenhum encontrado em `console/src/`), mas por `color-mix()` e pixels literais (`160px`, `±80px`) que eu mesmo introduzi no primeiro rascunho de `stage-shimmer` (T016), mais três falsos-positivos do checker de CSS em texto de comentário (ele não distingue prosa dentro de `/* */` de declaração real — "2px"/"4px" em frases explicativas). Corrigido: `stage-shimmer` reescrito para só referenciar tokens (ver T016); comentários reescritos para não conter números com sufixo de unidade. **Segunda rodada: `pnpm run lint` exit code 0, zero achados** — nenhum hex da paleta antiga nem nova sobrevive fora de `tokens.ts`/`contrast.test.ts`/`tokens.test.ts` (que legitimamente os declaram). |

## Fase 6 — Fecho local

### Achado de método: o harness local serve um build pré-compilado, não o dev server

`tools/console_e2e.py`'s `console()` serve `.next/standalone/server.js` — o
build de produção — e **não reconstrói**; se o arquivo já existe (de uma
build anterior, de outra sessão ou desta mesma antes de qualquer mudança),
ele é servido tal como está. As duas primeiras tentativas de rodar o
acceptance **depois** da implementação bateram nos mesmos 11 vermelhos de
antes — não porque a implementação estivesse errada, mas porque o build
servido era anterior a ela. `uv run python -m tools.console_gate build`
(equivalente a `make console-build`) resolve; refeito duas vezes nesta
implementação (uma vez depois da primeira leva de mudanças, outra depois da
reversão do contraste) e o acceptance ficou genuinamente verde nas duas
vezes que rodou contra um build fresco. Registrado aqui porque quem rodar
este acceptance de novo — verifier, orquestrador — precisa saber que
`make console-build` (ou equivalente) vem antes, sempre que o source mudou
desde o último build.

| Peça | Estado | Detalhe |
|---|---|---|
| T021 Acceptance verde no harness local | FEITO | Depois de `uv run python -m tools.console_gate build` (build fresco) e um bug de seletor corrigido no próprio teste (`engage-stop, [data-testid="stop-banner"]` estava duplamente aninhado — corrigido para `engage-stop, stop-banner`, texto puro que o código já sabia envolver): `uv run python -m tools.console_e2e run --backing mock -- tests/e2e/fundacao-visual.acceptance.spec.ts` → **20 passed (10.4s), exit code 0, real** (verificado no log, não só na notificação — ver nota de disciplina abaixo). As 16 alegações, todas verdes; T017/AN-09 e as duas caracterizações (AN-06 requests, AN-08 formas) continuam verdes como estavam antes de qualquer mudança. `network.spec.ts` (a mesma caracterização de zero-egress, rodada separadamente): **2 passed, exit 0** — idêntico ao "antes" da Fase 0. |
| T022 Baselines recapturadas | Em andamento nesta mesma sessão — ver abaixo | `uv run python -m tools.console_visual accept` (imagem Docker pinada, `--network none`). |

### Nota de disciplina: a notificação do wrapper mentiu sobre o exit code, de novo

Pelo menos três vezes nesta implementação a notificação de conclusão de uma
tarefa em background relatou "exit code 0" para uma corrida que, no log
real, tinha terminado com `EXIT:1` (o primeiro acceptance pós-implementação,
antes do rebuild). Todo resultado registrado neste controle veio do `Read`
do arquivo de log real gravado pelo próprio comando (`echo "EXIT:$?" >>
log`), nunca do texto da notificação — a mesma disciplina que o
orquestrador já havia nomeado como o motivo de quase perder a linha de base
vermelha do T001.

### T022 — revisão tela a tela (não um carimbo)

`uv run python -m tools.console_visual accept` (imagem Docker pinada,
`--network none`): **36 de 38 capturas recapturadas com sucesso; 2
reprovaram antes mesmo do obturador — real, `EXIT:1`, não os "exit 0" que a
notificação de novo alegou** (mesma disciplina da nota acima).

**Revisão real, não carimbo** — abri como imagem sete capturas de naturezas
diferentes (`shell-1440-dark`, `shell-1440-light`, `gallery-1440-dark`,
`decisions-1440-light`, `run-detail-1440-dark`, `incident-1440-light`, e uma
passada rápida pela `gallery` inteira apesar da altura de 13661px): paleta
escura quase-preta esverdeada e clara branca-esverdeada batendo com o board
nos dois temas; sidebar com os três grupos corretos e o item ativo com fundo
+ texto + barra interna visíveis; ícones novos no traço fino (relógio nítido
em Incidentes, escudo em Decisões, lupa em Investigações); chips com contorno
visível ao redor do tint (Failure, Approval, Critical, Succeeded, Open,
Investigation finished); números de KPI e H1 visivelmente maiores/mais
pesados que o corpo do texto (a família display). Nada quebrado, nenhuma
imagem em branco, nenhum ícone ausente, nenhum artefato de fonte não
carregada.

**As 2 reprovações — `resources-1440-light` e `resources-320-light` — são
uma pré-existência desta tela, não desta feature.** A causa é estrutural,
não visual: `fitToInnerScrollers` (`console/tests/capture.ts`) reporta que
o elemento `row-list` da tela `/resources` excede em ~3160px o teto que o
harness consegue alcançar crescendo a janela — sintoma de uma altura FIXA
em CSS (não responsiva à janela; o harness tenta crescer 4 vezes e desiste
exatamente pela razão que o comentário do próprio arquivo nomeia: "a
container with a fixed pixel height will never be satisfied by a taller
window"). Como a etapa falha **antes** do obturador, os dois PNGs
(`resources-1440-light.png`, `resources-320-light.png`) **não foram
tocados** — `git status --short` confirma que não aparecem entre os
36 modificados. Razão para não atribuir a esta feature: a lista de recursos
tem a mesma contagem de linhas de sempre (`surfaces/screens/resources.tsx`
não foi tocado — FR-035), e cada linha usa `line-height` explícito (não o
métrica intrínseca da fonte), então a troca de família tipográfica não muda
a altura de linha o bastante para explicar 3160px de estouro — a mesma
lista já estourava um teto de altura fixo antes desta feature, com qualquer
fonte. **Registrado como herdado, não escondido**: os dois baselines
permanecem com o conteúdo pré-feature (ainda não recapturados); quem for
tocar `/resources` (a feature de telas de área da onda) herda o reparo do
`row-list`, não esta.

Todos os outros 26 registros de `console/visual/screens.json` continuam
`baselined` e recapturaram sem esse problema.
