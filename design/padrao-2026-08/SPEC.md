# NinjaSRE — nova linguagem visual (spec dos artboards)

Evolução da marca atual (verde NinjaSRE, dark-first), não uma marca nova.
Grounded em `console/src/design/tokens.ts`.

## Fontes (Google Fonts, com fallback)
```html
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
```
- Display/números/headings: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif
- Corpo/UI: 'IBM Plex Sans', system-ui, sans-serif
- IDs, dados, payloads: 'IBM Plex Mono', ui-monospace, monospace

## Paleta DARK (tema principal)
- bg página (sunken): #0a100e
- surface (cards): #101815
- raised (elevado/hover-card): #16211d
- hover: #1c2925
- border: #223029 · border-strong: #35493f
- text: #e9f0ec · muted: #9fb2aa · faint: #6d7f77
- accent: #3ad195 · on-accent: #062018 · accent-bg: #12271f
- glow accent: rgba(58,209,149,.14) (radial, discreto)
- info: #6cb8e0 · info-bg: #12242c
- warning: #e0a84e · warning-bg: #2a2214
- danger: #ef7070 · danger-bg: #2a1616
- neutral: #a3b2ac · neutral-bg: #0d1311

## Paleta LIGHT
- bg página: #f2f6f4 · surface: #ffffff · raised: #ffffff
- border: #dde5e1 · strong: #9fb0a8
- text: #17211d · muted: #55645e
- accent: #0a7452 · on-accent: #fff · accent-bg: #e2f2ec
- info: #0a5f8f/#e4eff5 · warning: #8a5a12/#f7efdd · danger: #a51f1f/#f9e9e9
- sombras: 0 1px 2px rgba(17,22,28,.06) e 0 8px 24px rgba(17,22,28,.08)

## Geometria
- radii: chip 6, controle 8, card 12, painel/modal 16
- sidebar 232px, topbar 60px, gutter 24, gap cards 16
- corpo 14px/1.5; meta 12.5px; micro 11px; h1 26px SG 600; números display 30–34px SG 700

## Formas de status (MANTER — são intencionais, redundância p/ daltonismo)
- Losango ◆ = em execução (running/investigating)
- Círculo ● = resolvido/ok
- Quadrado ■ = crítico
- Triângulo ▲ = aprovação/atenção
Desenhar refinadas: 10px, cantos levemente arredondados, com animação sutil quando "live".

## Ícones
Inline SVG stroke 1.6, grid 20px, round caps, um estilo só. Nunca emoji.

## Motion (representar nos mocks; especificar em notas)
- pulse-live: anel expandindo 2s ease-out infinito no dot "Ao vivo"
- slide-in: novo item de lista entra com translateY(-4px)+fade 240ms
- progress shimmer nas barras de estágio ativas
- hover de card: elevação + borda accent 160ms

## Componentes-chave
- **Chip de status**: shape+label, fundo *-bg, borda 1px da cor, radius 999
- **Card de run**: título humano (objetivo!), barra de 6 estágios com segmento ativo animado, tempo decorrido, modelo/custo
- **KPI tile**: rótulo, número display SG, sparkline SVG 90×28, delta chip
- **Decisão**: cartão estruturado — o que/por quê/evidência/plano/reversão — JSON só atrás de <details> "payload bruto"
- **IDs**: sempre Plex Mono, truncados com tooltip, nunca título de nada

## Copy
UI em pt-BR (o console já tem i18n pt-BR). Dados reais (RedisExporterDown,
nomes de hosts) ficam como são. Sem lorem ipsum.
