# Controle — 038 Audit

| Item | Estado | Detalhe |
|---|---|---|
| 1. Ruído de máquina afoga ação humana | **FEITO** — controle anterior dizia NÃO INICIADO e estava errado | Rajadas idênticas consecutivas já colapsavam numa linha só com contagem (`groupBursts`), e o principal `default` já era excluído da leitura padrão, com um link dizendo quantos eventos ele esconde. Os testes já existentes (7, entre os blocos "a burst of identical polling" e "a human action buried in polling noise") passaram sem alteração. A sugestão de tratar `credential.resolve` como um contador em vez de um evento por chamada foi considerada e descartada — é uma mudança do lado da escrita, fora desta tela, e a leitura padrão já resolve o problema que ela descreve. Ver `relatorio-confronto.md`. |
| 2. Sem período, sem paginação | **FEITO** — controle anterior dizia NÃO INICIADO; o mecanismo já existia, mas a tela inteira estava quebrada | O filtro de período (7/30 dias + "Any") e a virtualização da lista longa (`RowList`, o mecanismo documentado do próprio `console/AGENTS.md` para "a long list is windowed") já existiam e já eram testados. Mas `EVENT_LIMIT` da tela pedia `500` eventos ao gateway, e o limite real do backend (`MAX_QUERY_PAGE_SIZE`) é `200` — o repositório *recusa* qualquer pedido acima disso em vez de encurtar silenciosamente, então **toda carga real desta tela devolvia 400 Bad Request**. Corrigido aqui, com teste vermelho primeiro: `EVENT_LIMIT` agora é `200`. Ver `relatorio-confronto.md`. |
| 3. Filtros de única opção | **FEITO** — controle anterior dizia NÃO INICIADO e estava errado | Um filtro com um único valor já é removido da barra de filtros por inteiro, testado para os dois casos (ausente e presente). Ver `relatorio-confronto.md`. |
| 4. Vazamento "SORT, SMALLEST FIRST" | **FEITO** — controle anterior dizia NÃO INICIADO e estava errado | Já corrigido para o console inteiro por `rows.tsx`'s `sortAction` — o mesmo defeito que a auditoria de 020 Resources já encontrou corrigido. Confirmado que as duas colunas ordenáveis desta tela usam o mecanismo compartilhado, sem override. Ver `relatorio-confronto.md`. |
| 5. Slugs por extenso | **FEITO** — metade já existia, e a outra metade escondia um defeito pior do que o item descreve | A coluna de ação já soletra o slug por extenso (`humanize`), testado. A coluna de desfecho estava genuinamente quebrada: o texto já soletrado era passado para o `Badge` compartilhado, cuja tabela de vocabulário (`DECLARED`, em `status.ts`) é sensível a maiúsculas e só reconhece o valor cru — então **todo desfecho de todo evento de auditoria (allowed, denied ou failed) desenhava como um chip cinza genérico**, perdendo a cor que distingue uma negação de uma permissão. Agravado por `DECLARED` nunca ter tido entradas para `allowed`/`denied`, e pelos dados do mock servirem `"succeeded"`, um valor que o enum real `AuditOutcome` nunca declarou. Corrigido nos três lugares que precisavam mudar juntos, com teste vermelho primeiro em cada um: a tela (`audit.tsx`, valor cru), o vocabulário compartilhado (`status.ts`, duas entradas novas) e os dados do mock (`served.py`). A ideia mais ambiciosa de uma frase por ação ("resolveu a credencial X para chamar Y") foi considerada e descartada — precisaria de um catálogo de tradução aberto que não existe, e nada nos critérios de aceite pede por ela. Ver `relatorio-confronto.md`. |

## Nota da auditoria de 2026-08-14

O ponto de partida desta auditoria já vinha nomeado pela auditoria de 036
Administration: `AUDIT_EVENTS`'s `actor_kind` servia `"person"`/`"machine"`
contra o `ActorKind` real (`platform/persistence/ports/audit_repository.py`),
que só declara `"user"`/`"token"`/`"agent"`/`"system"`. Verificado
diretamente, e corrigido da mesma forma que 036 corrigiu a divergência
idêntica em `PrincipalKind`: vocabulário corrigido no único lugar em que é
declarado (`tools/mockplane/dataset/served.py`), todo cenário commitado
reconstruído, e um novo teste de contrato
(`test_every_actor_kind_is_one_the_backend_actually_declares`) prendendo o
vocabulário contra o enum real. O console foi checado e não decide nada a
partir da string literal `'person'`/`'machine'` em lugar nenhum — `actor_kind`
nem é lido por `audit.tsx` — então não havia uma segunda metade do lado do
console para corrigir.

Rastrear a correção certa (lendo `platform/credentials/proxy/audit.py` e mais
onze pontos que constroem um `AuditEvent` real) encontrou uma **segunda
divergência de vocabulário, independente, na mesma tabela**: todo `outcome`
dos oito eventos do mock lia `"succeeded"` (sete registros) — uma palavra que
o enum real `AuditOutcome` nunca declarou (só tem `"allowed"`/`"denied"`/
`"failed"`). Corrigido da mesma forma, com um segundo novo teste de contrato
(`test_every_audit_outcome_is_one_the_backend_actually_declares`).

Essa segunda divergência não era cosmética: investigar por que a coluna de
desfecho da tela parecia sem estilo revelou os dois achados mais sérios desta
auditoria, ambos piores do que o próprio texto da spec nomeia.

**Item 2 — a tela inteira estava quebrada, não só sem paginação visível.**
`EVENT_LIMIT` pedia `500` eventos ao gateway; o limite real
(`MAX_QUERY_PAGE_SIZE`) é `200`, e o repositório *recusa* — não encurta — um
pedido acima disso (`BoundExceeded`, mapeado para HTTP 400 pelo gateway). Uma
suíte de teste de persistência já existente, anterior a esta auditoria,
já provava esse comportamento (`tests/contract/persistence/
test_audit_repository.py`). Ou seja: contra qualquer deployment real, ou
contra o fake em memória que os testes Python usam, **toda carga desta tela
falhava com 400** — não era uma questão de "sem carregar mais", era a tela
inteira não carregando. Corrigido com teste vermelho primeiro: um novo teste
em `audit.test.tsx` captura o endereço real pedido ao gateway e prende
`limit ≤ 200`; rodado contra o código sem a correção, falhou (`500` não é
`≤ 200`); depois da correção (`EVENT_LIMIT = 200`), passa. O filtro de período
e a virtualização da lista (`RowList`, documentada em `console/AGENTS.md` como
o mecanismo deste console para "a long list") já estavam corretos e não
precisaram de nada — inclusive tornam desnecessária uma paginação "carregar
mais" própria, que iria contra a arquitetura já documentada deste console.

**Item 5 — todo desfecho desenhava com a cor errada.** A tela passava o
texto já soletrado por extenso (`humanize`) para o `Badge` compartilhado, cuja
tabela de vocabulário (`DECLARED`, em `console/src/design/status.ts`) é
sensível a maiúsculas e só reconhece o valor cru que toda outra tela já passa
sem transformar (confirmado lendo `resources.tsx`, `runs.tsx`,
`incidents.tsx` ×2 e `memory.tsx` — nenhuma delas soletra antes de uma célula
de status). Combinado com `DECLARED` nunca ter tido entradas para `allowed`/
`denied`, e com o dado do mock (corrigido acima) antes servir `"succeeded"` —
um valor inválido —, todo desfecho de todo evento de auditoria desenhava como
o chip cinza genérico reservado para "um estado que este console nunca ouviu
falar", nunca como a cor verde (permitido) ou vermelha (negado/falhou) que o
design system existe para garantir. Corrigido nos três lugares que precisavam
mudar juntos, cada um com teste vermelho primeiro: a tela (`audit.tsx`, agora
passa o valor cru), o vocabulário compartilhado (`status.ts`, `allowed`/
`denied` adicionados, com um teste próprio em `status.test.ts` confirmado
vermelho por reversão temporária) e os dados do mock. A régua de
`spec.md`/`036` sobre "uma correção verificada só isoladamente, nunca no dado
que qualquer suíte orientada a fixture de fato lê" foi aplicada aqui de
propósito: os dois vocabulários (`actor_kind` e `outcome`) e a correção de
renderização foram todos verificados juntos contra o cenário `populated`
commitado, não só contra um fixture de teste unitário construído à mão — o
diff do `make console-visual` confirma isso diretamente.

Três correções pequenas de português brasileiro foram feitas no próprio bloco
`audit.*` de `pt-BR.ts`: `Acção` → `Ação` (×2) e `acções` → `ações` — a
grafia europeia só sobrava aqui e em três outras chaves de telas diferentes
(`transcript.kind.guardrail`, `dashboard.quickActions.title`/
`palette.group.actions`, `proposal.title`), nomeadas mas não tocadas. Dois
padrões mais largos, espalhados por várias telas, foram encontrados no mesmo
bloco e deliberadamente não tocados: `registado`/`registrado` (nove instâncias
europeias contra cinco brasileiras, um idioma de título de empty-state
repetido em pelo menos seis telas — corrigir só a cópia desta tela a deixaria
em desacordo com várias irmãs que hoje concordam entre si); e a construção de
continuidade `estar a + infinitivo` ("está a ver"), a mesma que a auditoria de
036 Administration já rastreou em pelo menos oito instâncias espalhadas por
cinco outras telas e decidiu deliberadamente não varrer, nem para a própria
instância dela — a mesma razão se aplica aqui sem precisar ser rederivada.

Ver `relatorio-confronto.md` para a evidência completa, arquivo e linha, e os
testes que confirmaram cada item vermelho antes de corrigido.
