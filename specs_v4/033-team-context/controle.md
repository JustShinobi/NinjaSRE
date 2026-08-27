# Controle — 033 Team context

Confrontado em 2026-08-14. Ver `relatorio-confronto.md` para a evidência
completa, `file:line` a `file:line`, e os gates realmente executados.

| Item | Estado | Detalhe |
|---|---|---|
| 1. Links corridos sem pontuação | **FEITO** (`bf5f055`) | Reconfirmado na confrontação de 2026-08-14: `operating-context.tsx:240-244` separa as duas frases-link com `" · "`, e cada uma já tem verbo próprio ("Runbooks live in Knowledge" / "Procedures live in Autonomy"), não é um substantivo nu. Teste que reproduz o texto colado (`operating-context.test.tsx:174-191`) foi executado de novo e passou sem alteração. |
| 2. Editor não se explica ("Start from this", exemplo de seção) | **FEITO** (confrontação 2026-08-14) | Três partes, ver nota abaixo. |
| 3. Orçamento sem consequência explicada | **FEITO** (confrontação 2026-08-14) | Nova linha, sempre visível, abaixo do contador de tokens: "What goes over budget is refused, not truncated." / "O que ultrapassa o orçamento é recusado, não truncado." Teste confirmado vermelho antes da correção. |
| 4. Coluna Organisation desperdiçada | **FEITO nas duas telas que a própria spec nomeia** — controle anterior dizia NÃO INICIADO e estava errado sobre Team context; ver nota abaixo sobre Configuration | Team context: já corrigido antes desta auditoria — com um único nó, o painel já colapsava para uma trilha em vez da árvore; os dois testes que provam isso já existiam e passaram sem alteração. Configuration: `configuration.tsx:184` ainda desenhava `OrgTree` sem condição nenhuma até esta confrontação — corrigido aqui, com teste confirmado vermelho antes, reaproveitando a mesma lógica de Team context por uma função só (`OrgNav`, `tree.tsx:179-203`) em vez de duplicá-la. |

## Item 2 — três sintomas, três estados diferentes por baixo do mesmo "NÃO INICIADO"

**O exemplo concreto já estava lá, estruturalmente.** A frase
`teamContext.factNotInstruction` — que já carrega o exemplo "Container
metrics come from the host, by vmid" — é renderizada sem condição nenhuma,
no topo do editor, antes de qualquer seção (`operating-context.tsx:240-241`).
Isso vale tanto para quando não há nada escrito e nada derivado (o painel
mostra o próprio estado vazio composto, `team-context.tsx:128-144`, já
testado) quanto para o caso que nenhum teste cobria — um editor que
*renderiza*, com zero seções explícitas, porque existe um documento inicial
derivado do parque da instalação. Um novo teste
(`team-context.test.tsx:139-156`) fixa esse segundo caso e passou de
primeira, contra o código como já estava — verificação, não correção.
Considerei e rejeitei pôr esse texto como `placeholder` HTML literal, como o
próprio texto do problema sugere entre parênteses: o comentário de
`form.tsx:12-15` proíbe isso explicitamente ("not a placeholder, which
disappears the moment somebody types"), e o critério de aceite pede
visibilidade, que a frase já dá, sem essa troca.

**"Start from this" genuinely não explicava nada, e foi corrigido.** A
frase melhor já existia, escrita e traduzida nos dois catálogos
(`teamContext.template.lead`), e nunca tinha sido lida por componente
nenhum — confirmado lendo `OperatingContextLabels` e o objeto `labels` de
`team-context.tsx` por inteiro antes de mexer. Renomeado para "Use the
starting document" / "Usar o documento inicial"
(`en.ts:1087`/`pt-BR.ts:923`), e a frase que já existia agora é o `title`
do próprio botão (`operating-context.tsx:337-350`). Teste confirmado
vermelho antes da correção, em dois níveis: no componente
(`operating-context.test.tsx:368-375`) e na tela real
(`team-context.test.tsx:164-172`).

**Os dois botões desabilitados sem explicação — o nomeado pela spec e o
irmão que ninguém tinha citado.** "Show me the prompt"
(`ask-context-preview`) nunca teve `title`, texto ou qualquer explicação de
por que ficava desabilitado. Ao checar, como instruído, o que mais vive na
mesma condicional do mesmo arquivo, "Add a section" (`add-section`) tinha
exatamente o mesmo defeito, sem estar registado em lugar nenhum. Os dois
agora explicam por quê, só enquanto desabilitados
(`operating-context.tsx:158-162,323-336,354-370`), usando o mesmo padrão de
`title` condicional que `simulation.tsx:151-159` já estabelece neste
console. Quatro testes novos, dois deles confirmados vermelhos antes da
correção (os outros dois passaram triviais contra o código antigo, porque
nunca existiu `title` nenhum a comparar — registados como tal, não como
prova do defeito).

## O levantamento de português do Brasil, no bloco inteiro de `teamContext.*`

Treze correções, não só as cinco citadas no briefing desta confrontação —
`nav.teamContext`, `page.teamContext.title`, `page.teamContext.context` e
dez chaves dentro do próprio bloco `teamContext.*`:

- `equipa` → `equipe`, duas vezes (`nav.teamContext`,
  `page.teamContext.title`) — as duas já nomeadas no briefing.
- `Factos`/`factos` → `Fatos`/`fatos`, três vezes
  (`page.teamContext.context`, `teamContext.sections.lead`,
  `teamContext.factNotInstruction`) — mesma classe de `Objectivo`→`Objetivo`;
  as três ocorrências desta grafia em todo `pt-BR.ts` estavam dentro deste
  bloco.
- `...no ecrã de Configuração...` → `na tela de Configuração...` — o único
  `ecrã` do catálogo inteiro.
- `"...um contentor vêm do anfitrião..."` → `"...um container vêm do
  host..."` — não é grafia, é vocabulário: `resources.column.source.hint`
  já descreve o mesmo fato sobre a mesma plataforma mantendo "container" e
  "host" em inglês; esta frase, a que o próprio enunciado do problema cita
  como bom exemplo, traduzia os dois literalmente. Inconsistência interna à
  própria frase-exemplo.
- `Secção`/`secção` → `Seção`/`seção`, quatro vezes — todas as ocorrências
  desta grafia em `pt-BR.ts` estavam neste bloco.
- `O texto exacto...` → `O texto exato...` — única ocorrência no catálogo.
- `A montar…` → `Montando…` — o progressivo europeu, seis linhas abaixo de
  `A guardar…` no mesmo bloco, não citado no briefing mas do mesmo padrão.
- `A guardar…` → `Guardando…` — a instância já nomeada no briefing.
- `Não foi possível contactar o deployment.` → `contatar` — a instância já
  nomeada no briefing; confirmada contra o mesmo par já correto uma tela
  antes, `detectors.control.unreachable` ("contatar").

Rastreados e deliberadamente não tocados, por pertencerem a outras telas:
`schedules.caption`/`schedules.empty.body`'s `equipa` (duas ocorrências
novas, não citadas antes); `signIn.context`'s `contacta` (nova, não citada
antes) e `signIn.unreachable`'s `contactar` (já nomeada por 032
Configuration). `Guardar`/`Guardado` como verbo foi mantido — escolha
lexical válida nos dois dialetos, o mesmo julgamento que 022 Detectors, 031
Autonomy e 032 Configuration já registraram para a palavra idêntica; não é
a troca `Guardar`→`Salvar` de catálogo inteiro, reservada para depois.

## Item 4 — correção depois de revisão do coordenador: o parêntese é desta spec, não de outra

A primeira passagem desta confrontação leu o parêntese do item 4 ("Vale
igual para Configuration e Autonomy, que têm o mesmo painel") como uma nota
lateral sobre o contrato de outra spec, e deixou `configuration.tsx:184`
sem corrigir, com o argumento de que nem 031 nem 032 nomeiam o problema no
próprio `spec.md`. Isso estava errado sobre de quem é a frase: ela é a
última linha do próprio item 4 *desta* spec (`specs_v4/033-team-context/spec.md:34`),
não um comentário sobre o contrato de outra — e quem lê a spec 033 espera o
item 4 fechado nas telas que ela mesma nomeia.

Corrigido depois da revisão: a lógica de colapso — árvore com mais de um
nó, trilha com um só — foi extraída para uma função só, `OrgNav`
(`tree.tsx:179-203`), e as duas telas (`team-context.tsx`,
`configuration.tsx`) passaram a chamá-la, em vez de cada uma manter sua
própria cópia dos mesmos dois ramos. Um teste novo
(`console/tests/unit/surfaces/configuration-tree.test.tsx`) foi escrito e
confirmado vermelho contra `configuration.tsx` antes da correção — o
colapso que ele agora prova não existia nesta tela um instante antes.
Autonomy foi reconfirmada, não corrigida: `autonomy.tsx` não importa
`OrgTree` nem nada de `tree.tsx`, então essa metade do parêntese já era
verdadeira e não precisava de mudança nenhuma — Autonomy simplesmente não
tem este painel, sob nome nenhum.

Ver `relatorio-confronto.md` para a evidência completa, linha por linha, e
os testes que confirmaram cada item vermelho antes de corrigido.
