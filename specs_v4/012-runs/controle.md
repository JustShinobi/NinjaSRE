# Controle — 012 Runs / Investigations

| Item | Estado | Detalhe |
|---|---|---|
| 1. Nome (Runs vs Investigations) | **FEITO** (`a53a009`) | Resolvido no catálogo inteiro, não só aqui: sidebar, título, breadcrumb e palette diziam Runs ou Investigations conforme a superfície. "Run" é a palavra da implementação. Feito uma vez no i18n, o que também fecha o item de vocabulário transversal da 090. |
| 2. ID hex como identidade da linha | **FEITO** (`a53a009`) | O assunto virou a coluna 1; o hex caiu para 8 caracteres como metadado. A coluna de assunto é deliberadamente **não ordenável**: o campo por baixo é o resumo cru do deployment, portanto ordenar por ela ordenaria por texto de exceção e não pelo assunto traduzido que a coluna mostra. |
| 3. Subject = stack de erro | **FEITO** (`d71c01a`) | Caiu de graça com a camada de tradução: a coluna de assunto da lista passa por `readFailure`, portanto uma exceção nunca é o texto da linha. |
| 4. Vazamento "SORT, SMALLEST FIRST" | **FEITO** (`a53a009`, em `rows.tsx`) | Não era desta tela — mora na lista compartilhada, e por isso três specs (012, 020, 038) reportavam o mesmo sem que nenhuma pudesse consertar. |
| 5. "Trigger: interactive" | **FEITO** (`a53a009`) | Slugs mapeados no render para o vocabulário do operador. |
| 6. Cabeçalho de lista no detalhe | **FEITO** (`a53a009`) | O detalhe ganhou título próprio (o assunto) e subtítulo com os seus metadados. |
| 7. Mesmo erro 3× na tela | **FEITO** (lote 6) | Ver a nota abaixo: o item 7 e o 9 eram **o mesmo defeito**. |
| 8. Título da aba = hex | **FEITO** | A aba carrega o assunto, lido pela mesma tradução que a tela usa. |
| 9. Coluna direita de empty states | **FEITO** (lote 6) | Ver a nota abaixo. |

## Lote 6 — os itens 7 e 9 eram uma linha

A tela já calculava `said = readFailure(...)` e passava `said.title` como `summary`
para `eventsFromReplay`. Duas consequências, e ninguém tinha ligado uma à outra:

1. O transcript ganhava uma entrada `"report"` fabricada com a mesma manchete que
   o painel de resumo logo acima já mostrava — a terceira repetição do item 7.
2. Como `eventsFromReplay` só omite o report quando o `summary` é vazio,
   `events.length` **nunca** era `0` num run que falhou antes de começar. E é
   disso que depende a bandeira `failedBeforeStart`, que os painéis de custo e de
   links já consultavam para colapsar numa linha. **O item 9 já estava
   implementado, com os comentários descrevendo o desenho pedido, e era código
   inalcançável.**

A correção passa o `summary` só quando ele é uma frase escrita por uma pessoa —
`said.technical` é não-vazio exatamente quando `readFailure` reconheceu uma
exceção. Uma exceção deixa de virar entrada de transcript, e o colapso de uma
linha volta a ligar.

**Decisão registada:** não se usou `emptiness.ts` aqui. Aquele módulo existe para
causa de deployment, com estado cheio e CTA; o item 9 pede o oposto — uma linha,
sem CTA, porque a razão de as duas secções estarem vazias é o run, e isso já foi
dito uma vez no topo da página.

4 testes novos em `console/tests/unit/surfaces/run-detail.test.tsx`, confirmados
vermelhos antes: o texto cru aparece exatamente uma vez, o transcript não fabrica
report, e os dois painéis ficam `ready` numa linha sem `way-back`.

**A spec 012 está fechada.**
