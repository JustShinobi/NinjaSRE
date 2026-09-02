# Veredito visual — 050 Painel vivo, slot S3

Orca Browser contra o staging, geração de pods 21:24:01Z confirmada por
listagem (nenhuma sobra da anterior), nove rotas aquecidas autenticadas,
locale pt-BR pelo cookie `ninjasre_locale`. Cada tema nomeado pelo valor
**medido** de `data-theme`.

| Tela | Tema | Veredito |
|---|---|---|
| `/` | dark | **CONFORME**, com 20 desvios registrados |
| `/` | light | **CONFORME**, com 20 desvios registrados |

## Por que este CONFORME vale mais que os três anteriores

Os três primeiros vieram de comparação **reativa**: alguém reparava numa
diferença, ela era corrigida, e a tela era declarada conforme. O operador
achava mais, de olho, nas três vezes. A tela não era o defeito; o método era.

Este vem de uma varredura **elemento a elemento**, escrita antes de qualquer
código mudar: dez seções, 38 itens, cada um com o que o board especifica, o que
o console renderiza e a decisão. A tabela está fora do repositório, e foi por
isso que sobreviveu ao agente que a produziu bater no teto de turnos.

O placar dela:

| Decisão | Itens |
|---|---|
| Conformar | 8 |
| Registrar em `DIVERGENCIAS.md` | 20 |
| Reportar (outra feature) | 7 |
| Dado vivo, não divergência | 3 |

**Vinte a registrar contra oito a conformar** é o número que explica as três
rodadas anteriores. A maior parte das diferenças não era drift — era decisão
que o console tomou e nunca escreveu. Sem registro, cada uma volta a parecer
defeito novo para quem olhar depois, que foi exatamente o que aconteceu.

## O defeito que três rodadas não viram

**A atividade ao vivo desenhava três formas onde a AN-13 nomeia quatro.**
`icon-inline` tem 14px e o menor raio da escala congelada é 6, então
`rounded-1` numa caixa de 14px deixa 2px de aresta reta por lado: o losango da
investigação e o quadrado do incidente **renderizavam como círculos**,
idênticos ao da resolução. O `status.tsx` desenha essas mesmas formas sem
raio; o feed as havia redeclarado com um.

O teste lia `data-kind` e nunca a geometria, então ficou verde o tempo todo.
Vermelho confirmado antes do conserto: `Expected: 2, Received: 1`.

Vale dizer como isto foi achado: **o operador viu a olho** que a atividade ao
vivo estava diferente. O gate visual tinha lido o docstring do componente, que
descreve quatro formas corretamente, e acreditado nele. A documentação estava
certa e a tela não.

## Conferido nesta captura, nos dois temas

- Quatro formas distintas no feed: losango na investigação iniciada, círculo na
  causa encontrada — visivelmente diferentes agora.
- Segunda linha de metadado por entrada: `há 5 minutos · investigação · 1m 9s`,
  `há 6 minutos · Alerta`, `há 1 hora · Manual`. O ator não é servido pela API,
  então onde o board diz `manual · você` sai só o gatilho — **nomeado, não
  inventado**.
- Ícone no chip "Parar a automação", losango na banda de execução, substantivos
  nos contadores (`investigações em voo`, `incidentes acompanhados`), "O agente"
  na barra lateral, números de KPI coloridos, razão 3:2 nas duas colunas (`lg:grid-cols-5` com `col-span-3` e
  `col-span-2`) — a do board, que é uma vez e meia.
- Zero ocorrências de `res-[0-9a-f]{8}` e de hex ≥16.

## O que continua diferente do board, de propósito

`DIVERGENCIAS.md` §9–§32. As visíveis nesta captura: o chip diz `Resolved` e
não `resolvido` (§12 — vocabulário da fundação, o mesmo chip está em
`/incidents`, `/runs` e `/decisions`, então não é mudança que o Painel faça
sozinho); o feed não desenha trilho vertical (§9); o chip `stream` é recusado
sob a regra de um indicador de frescor por página (§10); e o contador da barra
lateral não conta incidentes que o agente já pegou (§13 — decisão do commit
`d019dd77`, cuja razão é que um produto que investiga sem você não deve contar
o próprio trabalho como o seu backlog).

## Onde o dado difere do artboard, e isso não é desvio

O board desenha 7 assuntos; o staging tem 3. A coluna da esquerda termina bem
antes da direita e sobra vazio. É o dado, não a composição.

## Evidência

| Arquivo | Do que é evidência |
|---|---|
| `dashboard-dark.png` | a tela conformada, escuro |
| `dashboard-light.png` | a tela conformada, claro |
| `dashboard-{dark,light}-live-run.png` | **só** AN-01/AN-02/AN-03 — cartão vivo e seis segmentos |
| `ARTBOARD-DashboardLight.png` | o termo de comparação |

As duas com cartão vivo são de 16:48, **anteriores a todos os consertos**:
mostram o título antigo e o id cru. Não valem como evidência de SC-007 nem de
AN-11. Ficam porque são a única evidência do cartão vivo, e porque registram o
"antes". Não foram recapturadas porque o §4 do `EXECUCAO.md` dá um run por
slot e ele já foi gasto.

## Contestações a este veredito, e o que a medição disse

Um verifier independente reprovou este gate com dois achados. Um se sustenta,
o outro não, e ambos ficam registrados porque um veredito que só guarda o que
lhe convém não é evidência.

**Refutado — a barra lateral da captura clara não está escura.** O achado dizia
que `dashboard-light.png` desenha a barra no `surface` do tema escuro
(`#101815`), contradizendo o board e as evidências da 000 e da 060. Amostrado
pixel a pixel nos dois arquivos:

| Arquivo | Barra lateral |
|---|---|
| `dashboard-light.png` | `(255, 255, 255)` |
| `dashboard-dark.png` | `(16, 24, 21)` = `#101815` |

A cor apontada existe — na captura **escura**. A clara está branca, conforme.

**Procede — a razão das colunas estava errada nesta página.** O texto dizia
2:1; o código é `lg:grid-cols-5` com `col-span-3` e `col-span-2`, isto é 3:2.
O número veio da rodada anterior, quando era mesmo 2-de-3, e não foi
reconferido depois que o próprio conserto (`577d4733`) mudou a proporção.
Corrigido acima. É a segunda vez que este arquivo afirma mais do que a
evidência sustenta, e as duas foram pegas por leitura independente.
