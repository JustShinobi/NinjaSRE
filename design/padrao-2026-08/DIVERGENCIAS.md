# Divergências registradas

O operador decidiu (2026-08-27) que este board é o padrão e que convenções do
projeto que digam o contrário devem ser **registradas e ignoradas**. Este é o
registro. Cada item nomeia a convenção anterior, onde ela vive (ou viveu), e o
que vale agora.

## 1. Chip de status volta a ter contorno

O board `console-redesign/StatusStyle.html` (removido; recuperável no git)
escolhia "B · Soft pill — a tint, **no stroke**". O padrão novo desenha chips
com tint **e** borda de 1px na própria cor do estado. O contorno sutil sobre
fundos elevados é parte do que faz o novo tema vender; a crítica original era
ao *box dentro de box* com glyph bordado, que continua banido. As formas de
status como segundo portador de significado permanecem.

## 2. Tipografia deixa de ser "do sistema"

`console/src/design/tokens.ts` declara "The two families, both from the
operating system". O padrão novo usa **Space Grotesk** (display/números),
**IBM Plex Sans** (corpo) e **IBM Plex Mono** (ids/dados). Os artboards
referenciam Google Fonts por `<link>`; a implementação deve **self-hostear**
os woff2 no repositório (`console/public/fonts/`) — nenhuma request a
terceiros sai de uma página do console em produção. O README antigo desta
pasta prometia boards "sem rede"; os artboards degradam para os fallbacks
declarados quando offline, e a promessa forte de no-network passa para o
produto, não para os mockups.

## 3. O polling deliberado dá lugar a SSE

`console/src/live/auto-refresh.tsx` documenta com orgulho um refresh por
timer que "não encurta o intervalo sob falha" — filosofia construída em cima
de `router.refresh()`. O padrão novo exige eventos empurrados (SSE) para
Painel, listas e run view; o timer vira fallback quando o stream cai. A regra
que **sobrevive** do comentário em `topbar.tsx` é o indicador único de
frescor por página (o chip "Ao vivo") — um por frame, nunca um por painel.

## 4. Baselines visuais ficam todos obsoletos

`console/visual/screens.json` e os baselines em `console/visual/` descrevem o
console anterior. Aplicar o padrão exige re-baseline completo do gate visual
(que já estava vermelho de cobertura antes deste board). Nenhuma comparação
contra baseline antigo é evidência de drift.

## 5. A paleta servida em `surfaces/console/theme.py` é de outra era

O `stylesheet()` server-side carrega o azul `#0b5cab` de uma superfície
anterior ao console React. Qualquer tela ainda servida por ele diverge do
padrão e deve migrar para os tokens novos ao ser tocada.

## 6. UI bilíngue, board em pt-BR

O board desenha a UI em pt-BR. O console é i18n (en, pt-BR) via `message()`;
a implementação continua i18n — as strings do board entram como pt-BR e
ganham par em inglês. Não é conflito, é nota: ninguém deve hardcodar as
strings do mockup.
