# Controle — 034 Proposed changes

Confrontado em 2026-08-14. Ver `relatorio-confronto.md` para a evidência
completa, `file:line` a `file:line`, e os gates realmente executados.

| Item | Estado | Detalhe |
|---|---|---|
| 1. `/v1/proposals` não responde | **FEITO** (`bc26d76`) | Reconfirmado nesta confrontação, rodando os testes em vez de confiar na contagem. Causa-raiz continua correta como descrita: as filas recusavam credencial org-wide sem team (400); `_queue` (`gateway/http/routes/proposals.py:116`) e os dois `ProposalQueue._scoped` (`platform/proposals/service.py:313`, `platform/knowledge/proposals.py:383`) agora tratam escopo sem team como "toda a organização" na leitura, e o applier de knowledge é reconstruído por proposta, escopado ao team dela (`KnowledgeApplierByProposalTeam`, `gateway/http/routes/proposals.py:146`), preservando o invariante de escrita. `tests/unit/gateway/http/test_proposal_routes.py`: 8/8 verdes (rodado, não lido). Critério "teste de contrato cobrindo a rota" está satisfeito nesse arquivo — este repositório não tem `tests/contract/` para rotas do gateway; a cobertura de rota aqui é sempre um teste que sobe o `create_app` real sob `tests/unit/gateway/http/`, o mesmo padrão que outras rotas já usam. |
| 2. Nome (Proposed changes vs /proposals) | NÃO INICIADO (Onda 4) | **Errado nas duas metades.** O cruzamento com Approvals e a frase de vazio compartilhada com Knowledge (as duas coisas que o item pede) já estavam prontas — feitas por `a53a009`, onda anterior, antes desta confrontação existir. O que faltava, e nenhuma onda tinha visto: o único painel desta tela tinha seu próprio, terceiro nome do conceito — `proposals.title` dizia "Changes the agent has proposed" / "Mudanças propostas pelo agente" bem abaixo de um cabeçalho que já diz "Proposed changes" / "Mudanças propostas". Corrigido aqui, com teste confirmado vermelho antes (`proposals.test.tsx:87-98`), espelhando o mesmo ajuste que a própria `a53a009` já tinha feito para Runs/Investigations no mesmo commit. |
| 3. Empty state explicando de onde nasce uma proposta | NÃO INICIADO ("texto existe no i18n; reescrita pendente") | **Errado.** Já estava inteiramente construído por `a53a009`: `proposals.tsx:93-103` lê o checklist de setup, resolve `setupCause` e passa por `emptyBecause` — o mesmo mecanismo que oito outras telas já compartilham — explicando tanto de onde nasce uma proposta quanto em que estado do deployment isso é possível. Os dois testes existentes que fixam os dois ramos foram executados (não lidos) contra a árvore sem nenhuma mudança e passaram. Nada foi corrigido aqui porque nada estava quebrado. |

## O que esta confrontação mudou

Um único arquivo de catálogo, duas línguas: `proposals.title` (o título do
painel único desta tela) passou de uma terceira redação do conceito para o
mesmo nome que o menu e o título da página já usam — "Proposed changes" /
"Mudanças propostas" — em vez de "Changes the agent has proposed" / "Mudanças
propostas pelo agente". Teste novo em `proposals.test.tsx`, confirmado
vermelho antes da correção.

De passagem, corrigida no único arquivo tocado por esta confrontação: o
próprio docstring de `proposals.test.tsx` citava "(spec 034, item 2)" e
"(spec 034, item 3)" em comentário — o que o `CLAUDE.md` deste repositório
proíbe em código e teste commitados. As três citações do bloco (as duas já
existentes e a nova que eu mesmo ia escrever do mesmo jeito) foram reescritas
para dizer a substância sem número de spec nenhum. O mesmo padrão existe,
preexistente, em vários outros arquivos que esta spec não alcança
(`screens.test.tsx`, `contrast.test.ts`, `src/live/reducer.ts` — `SC-001`,
`SC-006`, `SC-007`, `FR-005`) — nomeado no relatório, não tocado, porque não
é superfície desta spec.

## Rastreado e deliberadamente não tocado

- `knowledge.proposals.title` ("Proposed by an agent"): legenda local do
  painel de Knowledge para a mesma fila filtrada — não é o nome da tela
  `/proposals`, e a relação explícita entre os dois já foi fechada pela
  confrontação 024 Knowledge (aceita), que reescreveu a frase-guia do
  painel, não o título. Não é superfície desta spec.
- O mesmíssimo defeito, uma tela adiante: `approvals.tsx:304`'s painel diz
  "Waiting on a decision" sob um cabeçalho que já diz "Actions awaiting
  approval" — achado novo, não nomeado nem pela spec 013 nem pela 034;
  pertence a quem confrontar a 013 de novo, ou a uma varredura de nomes.
- `console/src/surfaces/proposal.tsx` (`ProposalRow`) e
  `console/src/surfaces/decision.tsx`, oferecidos como pontos de partida
  prováveis: confirmados, pelos próprios importadores, como exclusivos da
  tela Approvals — nenhum dos dois é alcançado por `proposals.tsx`, cujo
  componente de revisão é `proposal-review.tsx`. A colisão de namespace no
  catálogo (`proposal.title` vs `proposals.title`, dois conceitos
  diferentes) é real, mas pertence à superfície de Approvals.
- `OrgNav`/`tree.tsx`: esta tela não tem árvore de organização nem
  breadcrumb — é uma fila plana, sem painel de organização para colapsar.

## Gates não aceitos, deixados para o coordenador

`make console-visual`: `proposals-1440-light` difere (658 pixels, 0,01 da
imagem) — consequência direta e esperada da mudança de texto do painel;
diff inspecionado, nada mais na tela mudou. Não aceito aqui, por instrução
padrão. `uv run python -m pytest tests/contract/console/` reflete o mesmo
achado em `test_the_untouched_baselines_still_match` (1 falha conhecida,
297 verdes).

Ver `relatorio-confronto.md` para a evidência completa, linha por linha, e
os testes que confirmaram o item 2 vermelho antes de corrigido.
