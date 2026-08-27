# Design

A referência de design deste console. Uma pasta, um padrão: o board em
`padrao-2026-08/` é **normativo** — as telas do produto devem ficar como ele
desenha, e o que falta no backend para isso ser verdade se implementa
(o plano está em `padrao-2026-08/PLANO.md`).

Decisão do operador em 2026-08-27: este board substitui todos os anteriores.
Os boards antigos (concept-board, console-audit, console-redesign,
dezenove-telas, proposta-interface, settings-v5/v6) foram removidos nesta data
para que não exista segunda referência com que comparar — o erro que esta
pasta existe para impedir é um leitor "corrigindo" o console de volta para um
mockup aposentado. A história deles permanece no git, e o que deles sobrevive
está absorvido no padrão ou registrado em
`padrao-2026-08/DIVERGENCIAS.md`.

## O board

| Diretório | O que decide | Desenhado |
|---|---|---|
| `padrao-2026-08/` | **Tudo.** Linguagem visual (tokens, tipografia, ícones, motion), as sete telas do console nos dois temas, o fluxo de investigação ao vivo, o cartão de Decisões — e as abas e listas que a onda reforma (Investigações-lista, Ferramentas, Autonomia, Contexto do time, Documentos, Topologia), 17 artboards ao todo. Regra da onda v8: **sem artboard, sem reforma** — tela que não está aqui recebe só a fundação (tokens/ícones/chips/shell) e mantém a estrutura até ganhar artboard aprovado. | 2026-08-27 |

Cada `*.dc.html` é um artboard; abra no navegador. `canvas.json` traz o
layout e as notas ao lado de cada tela — as notas carregam o porquê e a
lista do que o backend precisa entregar. `SPEC.md` é a linguagem visual em
prosa (paleta, tipos, formas de status, motion). O board também está
publicado como Artifact (canvas editável); o commit aqui é a cópia que o
`grep` alcança.

Os artboards referenciam Google Fonts por `<link>`; sem rede eles renderizam
nos fallbacks do sistema. Na implementação as fontes são self-hosted — ver
DIVERGENCIAS.md.

## As formas de status continuam

A redundância forma+cor sobrevive de todos os boards anteriores e é
deliberada (cerca de um homem em doze não separa as cores):
losango = em execução · círculo = resolvido/ok · quadrado = crítico ·
triângulo = aprovação/atenção · anel = pendente/desconhecido ·
traço = ausente.

## Comitar isto é o ponto

Uma decisão de design que ninguém encontra é uma decisão re-litigada. A regra
do repositório é que tudo exceto credencial pode ser comitado, e estas páginas
não carregam credencial. Nada em `console/` linka para cá e nada aqui é
gerado: são referências que uma pessoa lê. Os baselines do gate visual em
`console/visual/` seguem sendo o que o gate compara — e precisam de
re-baseline completo conforme o padrão for aplicado (PLANO.md, etapa A).
