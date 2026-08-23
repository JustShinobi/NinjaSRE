# specs_v7 — Recomendação do Fable (antes da geração das specs)

Escrita em 2026-08-23, a pedido do operador, para ser lida pela sessão que
gerar as specs. Contexto completo: [DIAGNOSTICO.md](DIAGNOSTICO.md),
[REGRAS.md](REGRAS.md), [README.md](README.md).

## A tese

O projeto tem a governança de um produto de 200k linhas e a experiência de um
protótipo — e isso é o diagnóstico, não um insulto. O gate da v6 passou com
12.036 testes verdes no mesmo instante em que o staging tinha `tool_calls=0`,
markdown cru como título e detalhe de incidente que não abre. **O aparato de
verificação mede peças com rigor excepcional e não mede o produto nunca.** O
laço que justifica o produto — alerta → investigação legível → ação aprovada —
jamais fechou uma vez.

"Tudo escrito, nada composto" (5 ocorrências) não é azar; é subproduto do
método: ondas + implementers escopados + test-first produzem peças que
satisfazem sua spec, e **o fio não é o trabalho de ninguém**. A emenda
"composed or it is not shipped" (REGRAS.md §3) ataca o sintoma. A mudança de
fundo: uma onda termina quando um humano assiste o laço fechar no staging e o
banco confirma — não quando as features passam.

## Recomendações concretas

1. **Dividir a onda em duas, com o laço no meio e não no fim.**
   - **v7a — "o produto conta o que fez e age"**: 000, 001, 010, 040 + uma
     080 *reduzida* ao laço mínimo (um alerta → investigação legível →
     proposta aprovada em propose-only). O laço fecha na metade do caminho.
   - **v7b — "um estranho consegue instalar e confiar"**: 020, 030, 050, 060,
     070, ops-1/2/3, e o cenário completo com o Proxmox povoando o estate.
   - Se ficar uma onda só: o laço mínimo vira marco do meio; nada de deixar a
     integração para a última feature — é o desenho que produziu as ondas
     anteriores.

2. **Responder a pergunta de audiência antes de pagar por 050 e 060.**
   Primeiro-admin e catálogo-que-ensina servem um operador hipotético que não
   é o atual. "Produto para outros" e "melhor agente SRE para esta infra" são
   ambos legítimos, mas ordenam a v7b de formas opostas. O backlog zera nas
   duas; a ordem muda.

3. **Depois da 010, uma sessão só lendo investigações.** O produto é o texto
   que produz e nenhuma spec pergunta "o root cause estava certo?". Staging:
   11–21s por run, Gemini Flash, 2 trace events. Quando o registro existir, a
   pergunta é editorial: este relato salvaria alguém às 3h? O Artigo VII é o
   menos exercitado da constituição e é a alma do preâmbulo — "proves it is
   getting better" é hoje a frase mais distante da realidade no repositório.

4. **O gate de onda passa a incluir a demo.** Evidência de composição no
   confronto (coluna "quem constrói isso em produção?", REGRAS.md §3) + o laço
   assistido no staging com contagens do banco anexadas. `make verify` verde
   deixa de ser sinônimo de pronto.

## O que não tocar

- Stubs de remediação fail-closed, credential proxy, single datastore,
  contratos de import — núcleo certo e maduro.
- A cultura de escrita: `backlog.md` é o melhor documento do repositório
  (problemas como desfechos julgáveis). Os empty-states honestos do console
  idem.

## Duas faxinas baratas

- Matar o console legado (`surfaces/console` + deployment `console` no chart);
  o `AGENTS.md` descreve a superfície errada.
- Tirar `_research/` do índice do CodeGraph — polui toda busca e, com regras
  de atribuição estritas, é vazamento de proveniência esperando acontecer.

## Em uma frase

Uma fábrica impecável de peças verificadas com a linha de montagem desligada:
a v7 é a onda em que a linha liga — o mais cedo possível dentro dela.
