# Gate visual — 010-canal-vivo (slot S1)

Revisor: modelo, via Orca Browser, contra `https://stg-ninjasre.lan.kyo.ninja`
com o build deste slot (`app`, `web` e `proxy` todos redeployados; digests
conferidos contra o que o `deploy-stg` empurrou). Artboard de referência:
`design/padrao-2026-08/Main.dc.html`.

Tema trocado **pelo botão da topbar**, nunca por `data-theme` injetado — o
botão é parte do que se valida. Ele cicla, então cada captura foi tirada
depois de ler `getComputedStyle(document.body).backgroundColor` e confirmar
`rgb(10, 16, 14)` (escuro) ou `rgb(242, 246, 244)` (claro).

| Tela × tema | Veredito |
|---|---|
| Painel `/` escuro | **CONFORME** no escopo desta feature |
| Painel `/` claro | **CONFORME** no escopo desta feature |

## O que esta feature tinha para provar, e o que a tela mostra

O escopo visual da 010 é um só: **o indicador de frescor, um por frame**, na
topbar. Ele está lá, com o ponto e o rótulo "Live", ao lado do botão de tema
— exatamente onde o artboard desenha "Ao vivo", e apenas uma vez na página.
A regra que a DIVERGENCIAS §3 preserva do `topbar.tsx` ("um indicador único
de frescor por página, nunca um por painel") se sustenta na tela servida.

O chip também foi observado em **outro estado** durante a mesma sessão: na
rota `/runs/{id}` ele lia "Refreshing". Isso não é desvio — é o mapa
`ConnectionState → Freshness` funcionando, e é a prova de que o rótulo não
está pregado em "Live".

## Diferenças que existem, e por que nenhuma é desvio desta feature

O Painel servido difere do artboard em três pontos reais. Nenhum é da 010, e
registrá-los aqui é o que impede que a próxima feature os herde sem dono:

1. **Os stat tiles não têm sparkline.** O artboard desenha uma linha de
   tendência sob cada figura; a tela mostra figura + linha de contexto.
2. **"What keeps happening" não desenha a faixa de disparos.** O artboard
   põe barrinhas verticais por assunto; a tela escreve "N firings".
3. **Não existe painel "Atividade ao vivo" com chip `stream`.** A coluna
   direita serve "Recent activity" + "Quick actions".

Os três são o Painel, não o canal — e o Painel é a **050-painel-vivo**, que
ainda não rodou (slot S3). Atribuir pelo que a tela *consome* e não pelo que
a feature *produz* é a regra da onda; atribuí-los à 010 seria transformar o
gate numa lista de dívidas de outra feature.

Uma quarta diferença é **de dado, não de desenho**: o artboard mostra duas
investigações em voo com barra de estágio, e o staging diz "Nothing is being
investigated right now" com 0 runs in flight, porque nenhum run vivo existia
no momento da captura.

A UI em inglês contra um board em pt-BR **não é desvio**: está registrada em
`design/padrao-2026-08/DIVERGENCIAS.md` §6, que diz que o console é i18n e
que as strings do board entram como pt-BR e ganham par em inglês.

## Evidência

- `painel-dark.png`, `painel-light.png` — captura full-page pelo Orca Browser.
- O artboard capturado para comparação lado a lado ficou fora de `evidence/`
  por ser derivado de um arquivo já versionado em `design/padrao-2026-08/`.
