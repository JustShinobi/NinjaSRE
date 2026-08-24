# specs_v7 — O que uma onda custa

Medido durante a execução, não estimado depois. Serve para dimensionar as
próximas: quantos agentes cabem numa janela, quanto uma feature custa, e onde
o dinheiro vaza.

## Por feature

Tokens são o total do agente somando todas as retomadas. "Tetos" é quantas
vezes o implementer bateu o limite de turnos e precisou ser retomado.

| Feature | Modelo | Tokens | Chamadas | Tempo | Tetos | Commits |
|---|---|---|---|---|---|---|
| 000 governança | Sonnet | ~839k | ~1.000 | 1h38 | **5** | — (árvore compartilhada) |
| 001 registro | Sonnet | ~793k | 361 | 1h14 | 3 | 17 |
| 020 identidade | Sonnet | ~909k | 712 | 1h40 | **5** | 19 |
| 030 fonte-por-fato | Sonnet | ~655k | 389 | 1h10 | 3 | 10 |
| 030 resto | Sonnet | ~594k | 373 | 56m | 4 | 3 |
| 040 decisão composta | **Opus** | ~523k | 373 | 2h07 | 3 | 12 |
| Reparo de fixtures | Sonnet | ~245k | 85 | 17m | 0 | — |
| **Verificações** | | | | | | |
| verifier 000 | Sonnet | ~308k | 117 | 24m | — | — |
| verifier 001 | Sonnet | ~309k | 80 | 14m | — | — |
| verifier 020 | Sonnet | ~265k | 118 | 19m | — | — |

**Total medido até o meio da onda: ~5,4 milhões de tokens** para 5 features
implementadas e 3 verificadas — sem contar as quatro que ainda rodavam quando
esta tabela foi escrita.

## A correção que a medição impôs

A tabela acima conta tokens de agente, e por isso é enganosa sobre o que uma
janela aguenta. Medido nesta onda: numa janela em que os quatro agentes
gastaram **478 mil tokens**, a janela foi a **33%** — mas a onda inteira já
tinha gasto **8,2 milhões** em tokens de agente. As duas contas não fecham com
um preço único por token, e não deviam: **um token não custa o mesmo que
outro.**

Os implementadores rodam o modelo mais barato. O orquestrador roda o modelo
caro com esforço de raciocínio alto, e cada turno dele reenvia o contexto
inteiro da conversa — que cresce a onda toda. Cinco agentes em paralelo custam
menos que uma tarde de turnos do orquestrador comentando o que eles fazem.

Duas consequências práticas, e a segunda foi aprendida errando:

- **A variável de controle não é quantos agentes rodam em paralelo. É quantos
  turnos o orquestrador dá.** Despachar é barato; narrar o progresso é caro.
- **Um vigia que acorda o orquestrador é um custo, não uma economia.** O
  desta onda re-emitia a cada dois minutos porque deduplicava pela linha
  inteira, que incluía a contagem regressiva — e cada despertar custava um
  turno cheio do modelo caro. O medidor passou a custar mais que o medido.

Agrupar notificações — três agentes voltando viram um turno, não três — vale
mais que qualquer decisão sobre paralelismo.

## O que os números dizem

**Uma feature custa entre 500k e 900k tokens**, e a variação não acompanha o
tamanho da spec: acompanha quanto julgamento ela exige. A governança e a
identidade endereçável, que pedem auditoria exemplo por exemplo e decisões de
forma, custaram mais que a decisão composta — que tinha o escopo mais difícil e
foi a mais barata das grandes, porque a spec dela era mecânica o bastante para
o agente executar em vez de deliberar.

**Uma verificação custa cerca de um terço de uma implementação** — 265k a 309k
contra 500k–900k. É barato para o que devolve: as três verificações desta onda
acharam um defeito que passou por dois gates, uma regra que passava sem medir
nada, e uma atribuição errada de escopo que teria custado um slot inteiro.

**Opus não custou mais que Sonnet aqui.** A feature de fronteira com Opus gastou
523k contra os 655k–909k das de Sonnet. O modelo mais caro por token resolveu
com menos idas e voltas.

**O teto de turnos é o maior imposto da onda.** Vinte e três tetos entre sete
execuções. Cada um custa uma retomada, e uma retomada custa contexto recarregado
mais o risco de perder o que não foi commitado — que aconteceu, com uma feature
segurando vinte arquivos e outra dezenove.

## O que fazer diferente na próxima

**Fatiar o dispatch por fase, não por feature.** Cinco tetos numa feature
significam que ela foi despachada como uma tarefa e executada como cinco. Uma
spec de 69 requisitos não cabe num agente; despachar as frentes uma a uma
gastaria o mesmo em tokens e nada em retomadas.

**Exigir commit e registro por fase como condição de entrada.** As duas features
que fizeram isso desde o início transformaram cada teto num recado de retomada.
As que não fizeram transformaram cada teto em risco de perda total. A diferença
não está nos tokens — está no que sobra depois deles.

**Rodar a verificação sempre.** É o terço mais barato do orçamento e é onde os
defeitos que sobrevivem aos gates aparecem.

**Medir a inclinação, não o percentual.** Oitenta por cento com quatro horas
até o reset e oitenta por cento com quatro minutos são fatos diferentes, e só
duas amostras os distinguem. `tools/sample_rate_limit.py` grava uma amostra por
vez em `consumo.jsonl`; `--report` devolve a taxa por hora e responde a única
pergunta que importa — **esta pace chega ao teto antes de a janela resetar?**

## Onde o orçamento vazou

Não em trabalho de feature. Em investigação causada por medição errada:

- uma conclusão de onda inteira — "o console serve páginas congeladas" —
  construída sobre o log do pod errado, escrita no confronto e usada para
  re-planejar um slot antes de alguém conferir o caminho ponta a ponta;
- uma corrida de aceitação quatro minutos após o deploy, contra um console
  ainda frio, que produziu uma página de links quebrados e uma hora de
  investigação de um defeito inexistente;
- quatro defeitos da família "reporta sucesso medindo nada", cada um custando
  uma rodada de reparo depois de a feature já ter sido dada como pronta.

Nenhum desses custos aparece numa estimativa de escopo. Todos aparecem no
relógio.
