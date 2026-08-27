# Implementation Plan: Fundação visual — a tabela de tokens vira o board, e o board vira o que o navegador desenha

**Branch**: `feat/v8-000-fundacao-visual` | **Date**: 2026-08-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v8/000-fundacao-visual/spec.md`

**Referência visual (DoD)**: `design/padrao-2026-08/Main.dc.html` e
`design/padrao-2026-08/SPEC.md`, codificados em
`console/tests/e2e/fundacao-visual.acceptance.spec.ts`, confirmado vermelho
antes da implementação. Viewport normativo: 1920×1080.

## Summary

Uma feature, quatro trocas na fundação e nenhuma tela:

1. **Os valores da tabela de tokens** viram os do board — paleta dos dois
   temas, raios 6/8/12/16, sombras, shell 232/60 — pela porta que já
   existe (`tokens.ts` → `css.ts` → `globals.css`), com o contrato de
   contraste decidindo o que o board não nomeia.
2. **Três famílias tipográficas self-hosted** (Space Grotesk, IBM Plex
   Sans, IBM Plex Mono) entram como woff2 no repositório com `@font-face`
   e preload; `FONT_STACKS` ganha `display`; nenhuma request sai da
   origem.
3. **Chip ganha contorno, ícone ganha desenho**: `ROLE_SKIN` soma a borda
   1px do papel; os ~26 ícones de `icons.tsx` são redesenhados no traço
   1.6 do board sem mudar nome nem assinatura; formas de status intactas.
4. **Motion vira vocabulário**: `pulse-live`, `slide-in`, `stage-shimmer`
   como keyframes+classes em `globals.css` com durações tokenizadas e
   `prefers-reduced-motion` os desligando; o shell (sidebar/topbar)
   adota grupos, medidas, logotipo e item-ativo do board.

Fecho: re-baseline visual completo e o gate do slot (deploy-stg + capturas
Orca browser × 2 temas + VEREDITO.md).

O que **não** muda: nenhuma tela de área, nenhuma rota, nenhum dado,
nenhum endpoint, o vocabulário das formas, os nomes de token existentes.

## Technical Context

**Language/Version**: TypeScript (console Next 16.3.0). Nenhum Python.

**Primary Dependencies**: `console/src/design/tokens.ts`,
`console/src/design/css.ts`, `console/src/design/icons.tsx`,
`console/src/components/status.tsx`, `console/src/app/globals.css`,
`console/src/app/layout.tsx` (preload), `console/public/fonts/` (novo),
`console/src/shell/topbar.tsx`, `console/src/shell/routes.ts` e o
componente de navegação que consome seus grupos,
`console/src/live/auto-refresh.tsx` (só a marca pulsante),
`console/src/i18n/en.ts`, `console/src/i18n/pt-BR.ts`,
`console/visual/` (baselines), `console/tests/unit/design/*`,
`console/tests/e2e/fundacao-visual.acceptance.spec.ts` (novo)

**Storage**: nenhum.

**Testing**: vitest para a tabela (contraste, paridade de nomes,
Tailwind↔tokens nas duas direções — suítes existentes, que passam a
provar os valores novos); Playwright para o acceptance (computed styles,
requests, motion, shell); suíte visual da imagem pinada para regressão de
tudo que o resto do console desenha.

**Target Platform**: console web servido no k3s de staging
(`stg-ninjasre.lan.kyo.ninja`).

**Project Type**: fundação de front-end — uma tabela, seus três
consumidores e os componentes folha que todos os outros compõem.

**Performance Goals**: fontes ≤ ~500KB somadas (subset latin, woff2);
preload só do que pinta acima da dobra; nenhuma animação que dispare
layout (só `transform`/`opacity`).

**Constraints**: `make verify` verde partindo de verde; zero requests
externas (o acceptance mede); os arquivos desta feature congelam após o
S0 (EXECUCAO.md §2) — o que faltar depois entra por relatório à
orquestração; diff proibido em `surfaces/screens/*` fora do que o shell
importa.

**Scale/Scope**: 26 papéis × 2 temas revalorados; 4 raios; 8 woff2;
~26 ícones redesenhados; 3 keyframes; 2 arquivos de shell; ~40 PNGs de
baseline recapturados.

## Constitution Check

*GATE: precisa passar antes da execução. Reconferir ao final.*

| Artigo | Como este plano satisfaz |
|---|---|
| I — Evidência sobre asserção | O DoD é medido: computed styles contra hexes do board, lista de requests vazia de terceiros, contraste por função executável, capturas do staging real com veredito linha a linha. |
| II — Autonomia limitada | Não toca laço, orçamento nem limite. |
| III — Leitura por padrão | Nada novo escreve; a feature é toda apresentação. |
| IV — Segredo nunca chega ao agente | Não toca credencial. Fontes self-hosted removem o único vetor de request externa que o board sugeria (DIVERGENCIAS.md §2). |
| V — Um runtime canônico | Não toca runtime. |
| VI — Neutralidade de provedor | Não toca provedor. |
| VII — Aprendizado é medido | Não toca aprendizado. |
| VIII — Arquitetura em camadas | Tudo dentro de `console/`; a tabela continua a fonte única e os consumidores continuam três, presos por teste. Nenhum import novo entre tiers. |
| IX — Capacidades declaradas | Nenhuma capacidade nova. |
| X — O operador é dono dos dados | Nada sai do host — inclusive as fontes, que passam a vir dele. |
| XI — Datastore único | Não toca persistência. |
| XII — Test-first, rastreado | Acceptance e unidades aterrissam vermelhos antes (a suíte de contraste fica vermelha no instante em que a paleta muda sem os ajustes de `on-*` — esse vermelho é registrado); caracterização: paridade de nomes entre temas e assinaturas dos ícones passam antes e depois. Efeito sobre cenários sintéticos: nenhum esperado, medido mesmo assim. |
| XIII — Idioma e atribuição | Código e comentários em inglês; UI por catálogo i18n em `en` e `pt-BR`; nenhum identificador de planejamento em arquivo committed. |
| XIV — Composto ou não foi entregue | Ver abaixo. |

### Qual composition root constrói isto

Não há objeto novo de backend; o "root" de uma fundação visual é o layout
que injeta o stylesheet e as páginas que compõem os componentes:

- `tokenStylesheet()` (`console/src/design/css.ts:154`) já é chamado no
  caminho de render do layout — os valores novos entram por ele, sem fio
  novo a ligar.
- `@font-face` e keyframes entram por `console/src/app/globals.css`, que o
  layout raiz já importa; o preload entra no próprio
  `console/src/app/layout.tsx`.
- Chip, formas e ícones já são compostos por todas as telas servidas; a
  mudança viaja pelos imports existentes.

**Prova exigida no DoD**: não é "teste verde no harness" — é o shell do
staging real, capturado nos dois temas, batendo com `Main.dc.html`
(EXECUCAO.md §3), mais a lista de requests do load vazia de terceiros no
mesmo ambiente.

### Complexity Tracking

Nenhuma violação a justificar. A feature muda valores por portas que já
existem; o único vocabulário novo (`family-display`, três primitivas de
motion, contorno no chip) é o mínimo que o board exige, e cada um chega
com seu teste.

## Project Structure

### Documentation (this feature)

```text
specs_v8/000-fundacao-visual/
├── spec.md
├── plan.md                    # este arquivo
├── tasks.md
├── controle.md                # do implementer, não deste plano
└── evidence/
    └── visual/                # capturas Orca browser + VEREDITO.md
```

### Source Code (repository root)

```text
console/public/fonts/                       # novo: 8 woff2 + OFL.txt
console/src/app/layout.tsx                  # preload dos woff2 de primeira pintura
console/src/app/globals.css                 # @font-face, keyframes, tema Tailwind atualizado
console/src/design/tokens.ts                # paleta, RADII, SHADOWS, SHELL, FONT_STACKS, TYPE_STEPS, DURATIONS
console/src/design/css.ts                   # --family-display; ICON_SIZES novos
console/src/design/icons.tsx                # redesenho traço 1.6, mesmas exports
console/src/components/status.tsx           # ROLE_SKIN com borda do papel
console/src/live/auto-refresh.tsx           # Mark live → pulse-live
console/src/shell/topbar.tsx                # medidas/ordem/logotipo do board
console/src/shell/routes.ts                 # single-write do slot indicado em EXECUCAO.md
console/src/i18n/en.ts, pt-BR.ts            # single-write do slot indicado em EXECUCAO.md
console/visual/**/*.png                     # baselines recapturadas
console/tests/unit/design/*                 # provam os valores novos
console/tests/e2e/fundacao-visual.acceptance.spec.ts   # novo
```

**Structure Decision**: nenhum diretório novo além de `public/fonts/`.
Nenhum componente novo — o board é alcançado revalorando e redesenhando o
que existe, que é o que mantém o diff auditável.

### Propriedade de escrita única

S0 roda solo para os arquivos de fundação: `tokens.ts`, `css.ts`,
`icons.tsx`, `status.tsx`, `globals.css` e `public/fonts/`. Depois do merge
do S0 eles congelam (EXECUCAO.md §2). Os single-write de catálogo e registro
(`i18n/*.ts`, `routes.ts`, `screens.json`) têm dono por slot conforme a tabela
de `EXECUCAO.md §2`; S0 fornece o baseline, mas não retém a propriedade
exclusiva desses arquivos.

## Decisões de design

### 1. O board entra pela tabela, nunca por cima dela

Os hexes do board não aparecem em componente nenhum: entram em
`tokens.ts` e chegam ao navegador pelo `tokenStylesheet()` existente. O
que o board chama de "bg página/cards/elevado/hover" mapeia para
`sunken/surface/raised/hover` — a tradução completa está em FR-001/002, e
os papéis que o board não nomeia (`on-warning`, `on-danger`, `on-info`,
`on-neutral`, `on-success`, `success-bg`) são fixados pelo contrato de
contraste com a tabela final registrada no controle (FR-004).

**Recusado**: um "tema v8" paralelo com fallback para o antigo. Duas
tabelas é o defeito que `css.ts` documenta na primeira linha; a onda
inteira validaria contra a cópia errada.

### 2. Fontes por arquivo no repositório, subset latin, e o preload mínimo

Oito woff2 (SG 500/600/700, Plex Sans 400/500/600, Plex Mono 400/500) em
`console/public/fonts/`, com o OFL ao lado — obtidos uma vez (subset
latin, ~30-60KB cada) e comitados; o build não baixa nada e o runtime
serve da própria origem. `@font-face` com `font-display: swap` em
`globals.css`; preload no layout só de display-700, sans-400/500 e
mono-400 (o que pinta acima da dobra); os demais pesos chegam quando o
navegador os pedir.

**Recusado**: `next/font/google` — baixa no build, e um build hermético
que depende do Google é a request externa mudada de lugar. **Recusado**:
link direto a `fonts.googleapis.com` — viola a propriedade zero-egress
que o console já tem e o gate visual (`--network none`) reprovaria.

### 3. O contorno do chip é um acréscimo ao `ROLE_SKIN`, não um chip novo

`ROLE_SKIN[role]` passa de `tint` para `tint + border-{role}`; a
espessura vem de `BORDER_WIDTHS` via a classe `edge` que o chip já
carrega. `CHIP_SHAPE` (geometria) não muda; `SHAPE_CLASS`, `ROLE_FILL`,
`ROLE_RING` e `HOLLOW_SHAPES` não mudam. Assim todos os chips — `Badge`,
`StatusChip`, `ResolvedChip`, `CheckChip`, o chip de frescor — ganham o
contorno num diff de cinco linhas, e nenhum consumidor é tocado.

**Recusado**: um `variant="outlined"` opcional — o board não tem chip sem
contorno; um opcional é uma bifurcação que alguém escolheria errado.

### 4. Ícones: mesmo contrato, outro traço

Cada ícone mantém nome, props e viewBox; muda o desenho interno para o
traço 1.6 round/round do board, copiando os paths dos artboards onde o
board desenha o mesmo conceito (FR-023) e seguindo o estilo onde não
desenha. `IconSize`/`Glyph` continuam o mecanismo; `ICON_SIZES` sobe para
14/18/20/24 porque o board desenha a navegação em 18 e os vazios em 24.

**Recusado**: uma biblioteca de ícones de terceiro — é dependência nova,
estilo de outra marca, e os artboards já carregam os desenhos.

### 5. Motion como três utilitários, desligáveis por media query

Keyframes e classes em `globals.css` (o lugar onde Tailwind já é
configurado), durações em `DURATIONS` emitidas como `--dur-*` e lidas
pelos keyframes — mudar o tempo é mudar a tabela. Um bloco único
`@media (prefers-reduced-motion: reduce)` zera as três. O único consumo
nesta feature é a marca live do `AutoRefresh` (FR-027); slide-in e
shimmer ficam disponíveis para 010/030/050, que os assere em seus
próprios acceptance.

**Recusado**: animar via biblioteca JS — três animações CSS não pagam uma
dependência, e `prefers-reduced-motion` em CSS desliga tudo num lugar só.

### 6. O shell muda de pele sem mudar de esqueleto

`topbar.tsx` mantém todos os controles e a ordem (que o board preserva);
o que muda é medida (60px), o logotipo (FR-031) e os tokens que ele já
lê. A sidebar ganha os rótulos de grupo pelo catálogo e o tratamento de
item ativo do board (FR-029). Nenhuma entrada de navegação entra ou sai
— "demais abas" são das features de tela.

**Recusado**: reescrever a navegação para bater pixel-perfeito com o
artboard inteiro — o artboard mostra badges de contagem (incidentes "4",
decisões "1") que dependem de dados que a 010/040 ligam; desenhá-los sem
o dado seria placeholder, e placeholder é o que esta onda veio matar.

### 7. Re-baseline no mesmo diff que muda os tokens

`python -m tools.console_visual accept` roda ao final, e os PNGs entram
no mesmo merge — nunca um estado intermediário em que o gate compara o
console novo com o board velho. A cobertura vermelha pré-existente do
gate é registrada no controle como herdada, não resolvida em silêncio.

### 8. A ordem é acceptance-primeiro, e o vermelho é registrado

O acceptance aterrissa antes de qualquer valor mudar e é confirmado
vermelho alegação por alegação (as AN-01/02 falham porque os tokens ainda
são os antigos; AN-06 passa hoje e é caracterização — registrada como
tal). A linha de base (`make verify` verde na árvore intacta, log fora do
repositório) é capturada antes da primeira escrita.
