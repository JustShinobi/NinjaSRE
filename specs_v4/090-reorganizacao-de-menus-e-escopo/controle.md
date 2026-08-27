# Controle — 090 Reorganização de menus e escopo

Confrontado em `relatorio-confronto.md` (nesta mesma pasta). Todo estado
abaixo foi verificado contra o código atual — não contra o que uma linha
desta tabela dizia antes da auditoria. Nenhuma pendência descrita abaixo foi
apagada silenciosamente.

| Peça | Estado | Detalhe |
|---|---|---|
| Sidebar 18 → 13 áreas | **FEITO** | `routes.ts` declara as treze áreas; confirmado por build de produção real (`make console-build`), que lista exatamente as treze rotas esperadas. Nota: o próprio título da seção em spec.md diz "18 → 10", mas a lista que ele mesmo enumera logo abaixo tem 13 itens — a lista é o que foi implementado; a inconsistência é do texto da spec, não do código. |
| Transversal 1: camada de tradução de erros | **FEITO (herdado)** | Já existia antes desta spec (specs 001/010/012). Verificado que nenhuma tela nova ou reescrita desta spec introduziu um caminho de erro cru — todas passam pela cadeia `panelRead`/`Panel` já existente. |
| Transversal 2: vocabulário único | **FEITO (herdado)** | Já existia antes desta spec. Toda chave i18n nova desta spec foi conferida nos dois idiomas e não repete um literal interno. Um defeito exatamente da classe que este item existe para pegar foi achado e corrigido durante a redação: `decisions.tab.changes` chegou a ser rascunhado como "Changes proposed", as duas palavras do título já existente "Proposed changes" invertidas — corrigido para "Changes"/"Mudanças". |
| Transversal 3: empty states com causa local | **FEITO (herdado)** | Cada função de aba movida manteve seu próprio `emptyBecause`/`setupCause` intacto; só o chamador mudou. `IntegrationsScreen` (tela nova) herda o empty state estático que `catalogue.tsx` já tinha para o mesmo painel — não é regressão desta spec. |
| Transversal 4: dashboard orientado a ação | **Fora do escopo desta spec** | `dashboard.tsx` só teve dois hrefs redirecionados para `/decisions`; a estrutura em si (hero/KPIs/atividade/quick actions) é da spec 010, já confrontada. |
| Transversal 5: telas próprias como único caminho de escrita | **FEITO (herdado)** | Os formulários de escrita movidos (RuleSimulator, formulário de credencial) não foram duplicados, só reendereçados. `configuration.tsx` não foi tocado por esta spec. |
| Fusão Decisions (Approvals+Proposals) | **FEITO** | Abas Ações/Mudanças propostas, badge somado no menu (`countsFrom` em `shell/load.ts`), 9 redirecionamentos incluindo o caso `/approvals/{id}` → `?selected=`. Permissão inalterada (`approval.read`). |
| Fusão Knowledge (Memory+Knowledge+Topology) | **FEITO** | Abas Aprendido/Documentos/Topologia, na ordem exata da spec. Documentos continua padrão (decisão registrada e defensável: é o que `/knowledge` já mostrava). Trade-off revelado: a saudação "nome da organização na raiz" da antiga Topology foi simplificada para o id cru do nó — perda pequena, registrada no relatório. |
| The agent absorve Catalogue(leitura)+Team context | **FEITO** | Quarta aba "Team", autocontida. Busca de tools/skills do Catalogue movida para dentro da aba Tools existente, sem substituir os painéis de risco. `catalogue.tsx` apagado, sem importador restante. |
| Integrations extraída do Catalogue | **FEITO — um gap achado e corrigido nesta auditoria** | A extração em si já existia num rascunho anterior desta sessão, mas sem o filtro que a própria spec.md pede ("...e filtro"). Nem a tela antiga (`catalogue.tsx`, conferido via `git show HEAD`) nem o primeiro rascunho tinham essa peça. Filtro por estado construído agora, com teste vermelho confirmado (3 de 4 falharam antes da implementação, rodado de verdade) antes de ficar verde. Permissão `integration.manage`, batendo com o que o gateway exige em `GET /v1/integrations`. |
| Fusão Signals (Detectors+Data) | **FEITO** | Abas Entrada/Observação contínua/Agendas/Destinos, ordem exata da spec. O filtro de permissão da aba Agendas (`schedule.manage`) foi verificado vermelho-depois-verde de propósito durante a implementação. |
| Administration+Audit | **FEITO** | Audit como aba de Administration. A "menor convicção" que a spec cita sobre a permissão foi conferida contra o modelo de papéis real: `identity.read` já concede `audit.read` no mesmo papel (`Role.ADMIN`), então a fusão não esconde a aba de ninguém que já via People. |
| O que NÃO fundir | **FEITO (confirmado)** | Incidents/Investigations, Autonomy/Configuration e Resources/Knowledge continuam três pares de áreas distintas em `routes.ts` — nenhuma das seis fusões tocou nelas. |

## Uma descoberta que muda como rodar os próprios gates desta spec daqui pra frente

`tests/contract/console/test_console_gate.py` chama de verdade `python -m
tools.console_gate e2e` — o mesmo comando de `make console-e2e` — num
subprocesso real. Isso tem um efeito colateral não documentado: quando
`console/visual/screens.json` declara uma tela sem baseline commitado, esse
comando escreve um PNG de qualquer jeito. Confirmado por hash SHA256 que os
onze PNGs escritos para as telas novas desta spec eram idênticos entre si em
sete rotas diferentes — não são capturas reais, são um efeito colateral que
passaria despercebido no `test_console_visual_coverage.py` (que só confere
se o arquivo existe, não o que tem dentro). Apagados as duas vezes que
apareceram, nesta auditoria. `make console-visual` e `make console-e2e`
não foram rodados diretamente por isso — ver `relatorio-confronto.md`,
Verificação item 15, para a evidência completa.

## O que fica pendente, nomeado, não escondido

- **As onze baselines visuais que faltam** (`decisions-1440-light`,
  `decisions-changes-1440-light`, `integrations-1440-light`,
  `signals-1440-light` + 3 variantes de aba, `knowledge-learned-1440-light`,
  `knowledge-topology-1440-light`, `agent-team-1440-light`,
  `administration-audit-1440-light`) — já registradas em `screens.json` com
  a razão de aceite completa; faltam apenas a captura real, via `make
  console-visual-accept` numa máquina onde isso seja seguro.
- **`make console-e2e`**, pelo motivo acima.
- Nenhum reaudite catálogo-inteiro dos cinco itens transversais foi feito —
  só o que esta spec mudou foi conferido contra eles. Reabrir o que as specs
  020–038 já confrontaram para esses cinco itens não é escopo desta.

## Mapa das ondas (histórico — a sequência não foi seguida onda a onda; tudo
## foi implementado e confrontado numa única auditoria)

1. ~~Funil F1–F4 + quebrados (tour, proposals, resource detail)~~ executada
   antes desta auditoria, fora do escopo de 090.
2. F5 + F6 + tradução de erros + busca global + duplicata do verify — fora
   do escopo de 090, já confrontado noutras specs.
3. Integrations extraída + empty states com causa local — **feito nesta
   auditoria** (Integrations, incluindo o filtro).
4. Sidebar novo + fusões + vocabulário único — **feito nesta auditoria**
   (as seis fusões, o vocabulário conferido no que esta spec tocou).
5. Dashboard novo + Configuration navegável + telas administrativas — fora
   do escopo de 090 (dashboard é spec 010; Configuration não foi tocada).
