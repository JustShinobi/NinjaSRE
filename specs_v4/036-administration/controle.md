# Controle — 036 Administration

| Item | Estado | Detalhe |
|---|---|---|
| 1. Lista de tokens é um despejo | **FEITO** — controle anterior dizia PARCIAL e estava errado nos três subpontos | Sessões e tokens de máquina já eram duas listas separadas (`SessionPanel`/`TokenPanel`, `isConsoleSession`), já agrupadas por pessoa com "encerrar todas", já com headers de coluna (`token-columns`/`session-columns`) e já com os revogados colapsados atrás de "{N} revoked". A investigação de por que cada page-load parecia emitir um token já tinha sido feita e corrigida pelo commit `bbd74a0` ("stop nav prefetch stampede"), que desligou o `prefetch` default do `<Link>` da sidebar — o próprio comentário do commit nomeia a causa ("a stampede the gateway's session handling was not built to absorb"). Os 76 testes de `tokens.test.tsx` já cobriam isso e passaram sem alteração. Ver `relatorio-confronto.md`. |
| 2. SSO grita erros antes de qualquer input | **FEITO** — controle anterior dizia NÃO INICIADO e estava errado | Já corrigido antes desta auditoria: `problems` do `SsoForm` começa vazio (`administration.tsx` passa `problems={[]}`, com um comentário próprio já nomeando o bug exato) e só é populado por um save ou teste real, nunca no carregamento. Os 21 testes de `sso.test.tsx` já passavam sem alteração. Ver `relatorio-confronto.md`. |
| 3. Grants e roles em slug | **FEITO** — metade já existia, metade corrigida em 2026-08-14 | A descrição de cada role no ponto de escolha (o select do formulário de grant) já existia, composta ao vivo a partir de `/identity/roles` — decisão correta e testada, não uma frase fixa, pela mesma razão que a spec 031 evita duplicar o catálogo de níveis do lado errado. O que faltava genuinamente: a própria lista de grants, e o diálogo de confirmação de remoção, ainda mostravam o `principal_id` cru — `bootstrap-administrator`, `local-admin`, as duas strings literais que a spec cita — em vez do nome. Corrigido com uma função `principalLabel` em `grants.tsx`, que resolve pela mesma lista `principals` já usada no seletor. Ver `relatorio-confronto.md`. |
| 4. "Bootstrap administrator — Not recorded" | **FEITO** — metade já existia, metade corrigida em 2026-08-14, mais uma correção depois da revisão do coordenador | Um trabalho anterior, não creditado no controle antigo, já tinha trocado "Not recorded" pelo `user_id` cru — melhor que "Not recorded" parecer bug, mas ainda um slug, não a frase que a própria spec sugere. Corrigido com `principalIdentity`, uma função exportada de `administration.tsx`, que agora diz "Conta de serviço criada no deploy, sem e-mail." (e o equivalente em inglês) para uma conta de serviço sem e-mail. A revisão do coordenador encontrou o resto do problema: o mock (`tools/mockplane`) nunca serviu `kind: "service_account"` — só `"person"`/`"machine"`, vocabulário que o backend real nunca emite — então o ramo que essa função testa nunca era exercitado por nada além do teste unitário direto. Corrigido nesta mesma auditoria: `served.py`/`build.py` agora servem `"user"`/`"service_account"`, todos os cenários commitados foram reconstruídos, e um novo teste de contrato prende o vocabulário contra o enum real. Ver `relatorio-confronto.md`. |
| 5. Issue a token sem escopo | **FEITO** — controle anterior dizia NÃO INICIADO e estava errado | Já corrigido antes desta auditoria: o formulário só pede "What it is for", e uma linha `token-issued-scopes` já diz qual é o escopo fixo que o token novo recebe (as próprias permissões de quem está emitindo) — confirmado contra `_scoped()` no backend, que dá a um token sem escopo exatamente as permissões do dono. Os 2 testes de `tokens.test.tsx` já cobriam isso. Ver `relatorio-confronto.md`. |

## Nota da auditoria de 2026-08-14

Ao corrigir os itens 3 e 4, uma leitura do bloco `admin.*` de `pt-BR.ts` (as
linhas que esses dois itens precisavam tocar) encontrou sete europeísmos
alcançáveis por esta tela, corrigidos junto: cinco instâncias da consoante
muda `Activ-` → `Ativ-` (mesma classe de `Objectivo`/`Activar` já corrigidos
em 022 Detectors — confirmado que `Ativ-` já é a grafia estabelecida em sete
outros pontos do catálogo, e que `Activ-` só sobrava aqui e em duas telas
diferentes); `Redireccionar` → `Redirecionar` (cc muda, mesma classe de
`direcção`/`direção`); `Equipa por omissão` → `Equipe padrão` (dois
europeísmos numa linha só — `equipa`/`equipe` e `por omissão`/`padrão`, os
dois já estabelecidos como `equipe`/`padrão` em todo o resto do catálogo);
`utilizador` → `usuário` (a única outra instância de `utilizador` no
catálogo inteiro fica na tela de Sign-in, fora deste escopo).

Um padrão maior — e deliberadamente não tocado — foi encontrado no mesmo
bloco: `admin.tokens.revokeCancel`'s "Deixar a funcionar" usa a mesma
construção de continuidade europeia ("deixar a + infinitivo") que aparece em
pelo menos mais sete pontos do catálogo, espalhados por pelo menos cinco
outras telas (`stop.cancel`'s "Deixar a correr" na topbar é o par direto do
mesmo idioma de UI; o resto está em Dashboard, Approvals e na tela de
falhas). Corrigir só a instância desta tela arriscava criar uma
inconsistência com `stop.cancel`, que usa exatamente a mesma frase para o
mesmo tipo de controle — nomeado no relatório, não corrigido, para quem
varrer esse padrão no catálogo inteiro.

Como pedido explicitamente, procurei nesta tela e em `platform/identity/`
pelo defeito que a auditoria de 035 Agent encontrou (uma tabela de tradução
declarada, documentada como o que transforma identificador em palavra, e
deixada vazia). Não existe aqui — `roleDescriptions` já é composto ao vivo, e
nenhum outro mapa declarado-mas-vazio foi encontrado. O defeito real desta
tela era outro: um fallback que caía para o identificador cru em vez de cair
para nada, corrigido nos itens 3 e 4 acima.

Uma descoberta foi nomeada mas deliberadamente não tocada: `platform/identity/sessions.py`
tem um `SessionStore` de sessão por cookie assinado, mecanismo diferente do
que esta tela de fato lê — rastreado e confirmado irrelevante para a
pergunta de emissão do item 1.

## Nota da revisão do coordenador

A primeira versão desta auditoria tinha encontrado a divergência de
vocabulário do mock (`fixtures/scenarios/*/principals.json` usando
`kind: "person"`/`"machine"`, contra o `PrincipalKind` real do backend —
`platform/persistence/ports/identity_repository.py:26-30` — que só declara
`"user"`/`"service_account"`) e a tinha deixado para `tools/mockplane`, como
se fosse só uma inconsistência de nomenclatura fora do escopo desta tela. O
coordenador apontou o que essa leitura perdeu: o ramo de `principalIdentity`
que decide a frase da conta de serviço testa exatamente `kind ===
'service_account'`, e nenhum mock jamais servia esse valor — então o item 4
estava corrigido apenas no teste unitário direto, nunca no dado que qualquer
suíte orientada a fixture, ou um operador olhando o deployment de
demonstração, realmente vê. Corrigido nesta mesma auditoria, não deixado para
depois: `tools/mockplane/dataset/served.py` (`USERS`, `identity_records()`)
e `tools/mockplane/dataset/build.py` (`empty_records()`) agora servem
`"user"`/`"service_account"`, lidos de uma fonte só em vez de repetidos como
um segundo literal; todo cenário commitado foi reconstruído com
`uv run python -m tools.mockplane build`; um novo teste de contrato
(`tests/contract/fixtures/test_dataset_contract.py::test_every_principal_kind_is_one_the_backend_actually_declares`)
prende o vocabulário contra o enum real, confirmado vermelho antes da
correção (28 registros errados nos sete cenários declarados) e verde depois.
Verificado, como pedido: nem o console nem o próprio código do mock decidem
algo a partir da string literal `'person'`/`'machine'` em lugar nenhum — os
dezesseis arquivos de teste do console que citam `kind: 'person'` são stubs
próprios de cada arquivo, e `Viewer` (`console/src/session/viewer.ts`) nem
lê esse campo — então nada mais precisou mudar. Uma segunda divergência
idêntica foi encontrada de passagem e **não** corrigida aqui, porque pertence
a outra tela: `AUDIT_EVENTS`'s `actor_kind` também usa `"person"`/`"machine"`
contra o `ActorKind` real (que é `"user"`/`"token"`/`"agent"`/`"system"`) —
alimenta `/audit/events`, que é a spec 038, não esta.

Ver `relatorio-confronto.md` para a evidência completa, linha por linha, e os
testes que confirmaram cada item vermelho antes de corrigido.
