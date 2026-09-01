# Polimento visual e UX — plano de execução corrida

Origem: varredura visual de 2026-09-01 no Orca Browser contra o staging
(`stg-ninjasre.lan.kyo.ninja`, dois temas), tela a tela contra os artboards
desta pasta. Este documento é um **plano de execução direta** — sem spec-kit,
sem gate por feature: o agente executa os blocos em ordem, um commit por
bloco, e fecha com uma passada visual única nos dois temas.

## Regras da execução

- **Um bloco = um commit** (conventional commit, imperativo, inglês). Blocos
  são ordenados por dependência; dentro de um bloco a ordem é livre.
- **Verificação por bloco é leve**: os testes que tocam os arquivos editados
  (`npx vitest run <caminhos>` no `console/`, `npx tsc --noEmit`) e mais
  nada. `make verify` completo roda duas vezes: depois do bloco 2 e no fim.
- **Gate visual só no fim**: um `deploy-stg` e uma passada Orca Browser nos
  dois temas sobre as telas tocadas. Nada de re-baseline por bloco.
- **Toda string nova nasce nos dois idiomas** (`console/src/i18n/en.ts` +
  `pt-BR.ts`). O inglês é a fonte; o pt-BR usa o vocabulário do board.
- **Nenhum bloco desfaz divergência registrada** (DIVERGENCIAS.md §1–§32):
  trilho, contagens da navegação, avatar azul, indicador único de frescor e
  os demais continuam decididos. Na dúvida entre plano e registro, o
  registro ganha.
- Testes existentes que codificam strings/estruturas antigas **são
  atualizados no mesmo bloco** que muda a string/estrutura — nunca
  enfraquecidos, só apontados para o novo alvo.
- O Painel fica fora (varrido em 2026-08-31); `attention.tsx`,
  `kpi-tiles.tsx`, `activity-feed.tsx` só são tocados se um bloco de
  fundação (bloco 2) mudar algo que eles consomem.

---

## Bloco 1 — o vocabulário do stream (destrava o RunView inteiro)

**Problema, verificado**: `STREAM_KINDS` em
`console/src/surfaces/transcript.ts:132` mapeia `turn_started`,
`tool_called`, `tool_succeeded`, `observation_recorded`, `run_completed` —
mas o deployment emite `turn_completed`, `capability_called`,
`evidence_observed`, `stage_completed`, `run_finished`. Resultado no
staging: as ~51 entradas de um run vivo narram "Chegou um evento de tipo não
reconhecido: X", todas rotuladas "Raciocínio".

1. Antes de editar, confirmar o vocabulário completo emitido: ler os kinds
   em `fixtures/scenarios/populated/` e no caminho de escrita do mockplane,
   e conferir contra o que o stream do staging mostrou
   (`stage_completed`, `turn_completed`, `evidence_observed`,
   `capability_called`, `run_finished` — e o que mais os fixtures tiverem).
2. **Teste primeiro**: novo teste em
   `console/tests/unit/surfaces/transcript-narration.test.ts` que percorre o
   vocabulário dos fixtures e exige que cada kind resolva para uma narração
   que não seja `transcript.narration.unknown`. Confirmar vermelho.
3. Corrigir `STREAM_KINDS` e `NARRATION_LEAD` para o vocabulário real.
   Manter os nomes antigos como sinônimos (não custam nada e protegem
   replay antigo). Mapear: `turn_completed→reasoning`,
   `capability_called→call` (+ resultado quando o payload disser),
   `evidence_observed→evidence`, `run_finished→report`;
   `stage_completed` ganha narração própria ("Estágio concluído — <nome>"),
   papel neutro.
4. Frases de narração novas nos dois idiomas para cada kind novo.
5. Rodar o teste (verde), `tsc --noEmit`, commit
   (`fix(console): narrate the stream vocabulary the deployment actually emits`).

## Bloco 2 — rótulos para enumeração conhecida (fundação, uma vez)

**Problema**: `Propose`, `Active`, `Running`, `Expired`, `Completed`,
`Succeeded`, `Investigating`, `Resolved`, `Critical` aparecem crus num
console pt-BR. O §12 protege a palavra *desconhecida* do deployment; estas
são enumerações que o produto conhece. O próprio §12 aponta o conserto:
rótulo por estado conhecido, palavra crua como degradação, na fundação.

1. Em `console/src/components/status.tsx` (`Badge`): antes de imprimir a
   palavra crua, procurar `status.<valor-normalizado>` no i18n; existir →
   rótulo traduzido; não existir → comportamento atual (papel neutro,
   palavra crua). O contrato do §12 fica intacto por construção.
2. Popular o mapa com os estados que o staging exibe hoje: `running`,
   `completed`, `failed`, `succeeded`, `expired`, `investigating`,
   `resolved`, `remediating`, `open`, `awaiting_human`, `critical`,
   `medium`, `active`, `propose`/`proposed`. pt-BR pelo board: `rodando`,
   `completada`, `falhou`, `sucedeu`, `expirada`, `investigando`,
   `resolvido`, `remediando`, `aberto`, `esperando alguém`, `crítico`,
   `médio`, `ativa`, `propor`.
3. "era critical" em Incidentes (`screens/incidents.tsx` /
   `incident-group-list.tsx`): a frase composta usa o mesmo mapa → "foi
   crítico".
4. Atualizar os testes de `status`/`incidents` que asseram a palavra crua.
5. `make verify` completo aqui (o mapa toca muitas telas). Commit
   (`feat(console): label known status enumerations, raw word as fallback`).

## Bloco 3 — O agente > Pipeline: uma história só, e viva

**Arquivo**: `console/src/surfaces/screens/agent.tsx` (+ i18n).

1. **Matar a duplicação**: remover a seção "As etapas que uma investigação
   executa" (diagrama "Orquestrador" + caixas + prosa) inteira. A prosa por
   estágio (descrição + "Consulta:" + papel de modelo) migra para dentro do
   metrô: cada estágio vira `<details>`/expansível — clicar no círculo abre
   o detalhe daquele estágio abaixo da banda. Remover `agent.stages.title`
   e as chaves órfãs do i18n.
2. **Traduzir o metrô**: nomes de estágio e descrições ganham par pt-BR
   (board: Resolver integrações, Triagem, Planejar evidência, Coletar
   evidência, Diagnosticar, Entregar). Labels mono viram
   `1 · sem modelo` / `2 · modelo: intake` (numeração + papel, pt-BR).
3. **Estado vivo**: consumir o canal vivo que a 050 já consome no Painel
   (runs em voo por estágio). Com investigação em voo: estágio corrente com
   anel `pulse-live-ring` (a primitiva existe em `globals.css`), rótulo
   "rodando agora" no label mono, linha preenchida até o estágio, chip
   "N investigações em voo" no canto do painel. Sem voo: banda em repouso
   como está. `prefers-reduced-motion` já é respeitado pela primitiva.
4. **Cards-resumo** (Ferramentas/Autonomia/Contexto do time) ao pé do board
   `TheAgent.dc.html`:
   - Autonomia: linhas com veredito "Propor" (bloco 2 já traduz), mini
     barra por classe, rodapé "Nenhuma classe roda sozinha…", link
     "ajustar política →".
   - Contexto do time: barra de progresso do orçamento (não texto solto),
     nota "o que passa do orçamento é recusado, nunca truncado", chips
     `→ Investigador` `→ Subagente`, link "escrever fatos do ambiente →".
   - Ferramentas: já perto do board; conferir chips do rodapé e link
     "catálogo completo →".
5. As seções abaixo (Os especialistas, Em que cada papel roda, O que uma
   investigação pode gastar, A mesma topologia como documento) ficam, mas
   enxutas: "Em que cada papel roda" colapsa as sete linhas idênticas
   "sem escolha própria — segue o investigador" numa linha-resumo
   ("7 papéis seguem o investigador") com expansão para a lista completa;
   "A mesma topologia, como documento" vira `<details>` fechado.
6. Testes de `agent` atualizados; screenshot local rápido; commit
   (`refactor(console): one pipeline story on the agent screen, alive`).

## Bloco 4 — O agente > Autonomia: a escada do board

**Arquivo**: `agent.tsx` (aba `autonomy`) + i18n.

Refazer a aba sobre `AgentAutonomy.dc.html`:

1. Uma linha por classe: chip da classe colorido por severidade —
   `Trivial` (neutro), `Baixa` (neutro), `Moderada` (âmbar), `Alta`
   (âmbar forte), `Perigosa` (vermelho) — frase curta pt-BR, seta,
   veredito "Propor", nota à direita "nada roda sem uma pessoa decidir".
2. O parágrafo "Por quê" (que hoje se repete 5×) vai para expansão por
   linha (`<details>`), com borda de acento à esquerda e link
   "ver a regra que resolve isso →" apontando para
   Ajustes > Autonomia & guardrails.
3. Cabeçalho ganha o chip "Política atual: só propõe" (derivado do mesmo
   dado do rodapé "Guardião ativo · só propõe").
4. Rodapé: card "Mudar a política" — ícone, duas frases do board, nota
   "mudança de política é uma decisão registrada", botão
   "ajustar política →".
5. As frases por classe vêm do deployment em inglês; a linha curta usa a
   primeira sentença; o resto vive na expansão. Se o deployment um dia
   falar pt-BR, nada muda aqui.
6. Testes, commit (`refactor(console): the autonomy tab as the board's ladder`).

## Bloco 5 — O agente > Ferramentas: master-detail em vez de dump

**Arquivo**: `agent.tsx` (aba `tools`) + i18n.

A aba tem hoje ~12.500px: tabela com as 80 capacidades + duas seções de
prosa repetindo cada ferramenta. Adotar `AgentTools.dc.html`:

1. Banda de topo: "63 de 80 habilitadas" + barra de progresso + busca +
   chips de filtro por efeito (Todas / Lê / Escreve reversível / Escreve
   irreversível / Destrutiva N).
2. Coluna esquerda: domínios com contagem, **pt-BR** (Remediação, Plano de
   controle, Skills, Metodologia, Logstore, Comunicação, Métricas,
   Incidente, CI/CD, VCS, Banco de dados, Tracing, Mudanças, Provedor de
   modelo, Observabilidade, Topologia, Estate). O conjunto de domínios é do
   catálogo do produto — não é o caso aberto do §11.
3. Direita: cards da capacidade do domínio selecionado (nome mono, chip de
   efeito, estado Habilitada/Desligada; destrutiva com borda vermelha),
   limitados a 8 com "mostrando 8 de N · ver todas →".
4. A prosa por ferramenta vira o detalhe do card (expansão), e as duas
   seções corridas morrem.
5. Rodapé: "Efeitos colaterais vêm do catálogo, não do agente — o que é
   destrutivo pede aprovação sempre."
6. Seleção de domínio/filtro segue o padrão da casa: estado no endereço
   (`withFilter`/`hrefFor`, como as abas já fazem), não estado de cliente.
7. Testes, commit (`refactor(console): the tools tab as master-detail, not a dump`).

## Bloco 6 — O agente > Contexto do time: o layout do board

**Arquivo**: `agent.tsx` (aba `team`) + i18n.

Sobre `AgentTeam.dc.html`:

1. Duas colunas: à esquerda as seções do documento; à direita o rail com
   "Orçamento de prompt" (número grande + "de 1.200 tokens · N%" + barra +
   aviso "O que passa do orçamento é recusado, nunca truncado em
   silêncio"), "Enviado para" (chips Investigador/Subagente com ✓ + nota),
   botões "Usar o documento inicial" / "Mostrar o prompt final", e a nota
   "Salvo por deployment — cada investigação nova já nasce lendo isto."
2. O bloco de prosa "Escreva fatos, não instruções…" vira o exemplo visual
   do board: ✓ Fato: "…" / ✗ Instrução: ~~"…"~~ — duas linhas, não
   parágrafo.
3. Cada seção existente vira card com contagem de tokens e remoção;
   "+ Adicionar seção" é a área tracejada (o form atual de nome+botão migra
   para dentro dela).
4. Chips "Investigator/Subagent" → "Investigador/Subagente" (i18n).
5. O card "Organização" (seletor de nó) permanece — é funcionalidade que o
   board resolve com breadcrumb; manter como está é a decisão, registrada
   aqui: um seletor explícito serve melhor a árvore com mais de dois nós.
6. Testes, commit (`refactor(console): the team context tab in the board's layout`).

## Bloco 7 — o lançador "Investigar"

**Arquivo**: `console/src/live/investigate.tsx` + i18n.

Hoje: caixa ancorada no botão com label + textarea + "Iniciar". Adotar
`StartInvestigation.dc.html`:

1. Modal central com overlay (usar o `Modal`/`Overlay` que
   `ConfirmDestructive` já usa), ícone + título "Iniciar uma investigação",
   fechar no ✕ e no Esc.
2. Textarea com borda de acento no foco; embaixo, a linha "O objetivo diz
   do que a investigação trata — o agente decide o caminho" à esquerda e
   `Ctrl ↵ para iniciar` mono à direita. Ctrl+Enter dispara.
3. Bloco "OU COMECE DE ONDE O AMBIENTE ESTÁ": até três sugestões derivadas
   do que o console já carrega — assunto recorrente com mais disparos
   ("Por que X insiste em voltar? N disparos desde ontem"), queda em lote
   se houver banda vermelha em Recursos ("O que derrubou N contêineres em
   <nó>?"), e sempre "Auditar a saúde geral do cluster <nome>". Clicar
   preenche o objetivo. Sem dado para as duas primeiras, só a auditoria
   aparece — degradação honesta, sem inventar.
4. Rodapé: "Vai rodar com o time <X> · <modelo> · só propõe / 6 estágios ·
   você acompanha ao vivo, evento a evento" + Cancelar + **Investigar**
   (com ícone play; o rótulo "Iniciar" morre).
5. Testes do componente; commit
   (`refactor(console): the investigate launcher as the board draws it`).

## Bloco 8 — RunView

**Arquivos**: `console/src/surfaces/screens/runs.tsx`,
`transcript-view.tsx`, `run-band.tsx`.

1. **Eco do cabeçalho**: o painel "O que esta investigação encontrou"
   repete título+meta da página enquanto não há headline — sem achado, não
   desenhar o painel; com headline, ele volta como está.
2. **Custo zero mentiroso**: "0 Tokens · Passos 13" quando o recorder não
   compôs → quando tokens=0 e nenhum turno carrega custo, o painel diz
   "sem registro de custo para este run" (i18n) em vez do número. Zero real
   (turnos com custo zerado registrado) continua imprimindo 0 — a distinção
   que `summarise_investigation` já faz (omitted vs zero).
3. **Tempo por evento**: instante+duração à direita da linha em mono
   (`agora · 1,1s`), como o board; hoje ficam no meio do cabeçalho da
   entrada.
4. **Controle**: "Assumir" e "Interromper" sobem para o cabeçalho do run
   (botões ao lado do título, como o board); a caixa "Diga algo que esta
   investigação deveria saber…" + "Enviar sem interromper" desce para o pé
   do transcript. O painel lateral "Controle" desaparece.
5. **Tocados**: com dado, chips mono por recurso (`node:pve01`) e a legenda
   "só leitura até aqui · nenhuma escrita proposta ainda"; placeholder atual
   só quando não há nada.
6. **Anel no estágio corrente**: `pulse-live-ring` no círculo do estágio
   ativo da banda (mesma primitiva do bloco 3). Transição CSS no
   preenchimento da linha entre estágios (do salto seco para ~300ms ease).
7. Depois do bloco 1, olhar o transcript vivo de verdade e ajustar
   ícone/cor por kind se a variedade real pedir (hoje ninguém nunca viu o
   transcript sem o fallback).
8. Testes (`runs`, `transcript-view`), commit
   (`fix(console): run view control, cost honesty and stage motion`).

## Bloco 9 — Incidentes

**Arquivos**: `screens/incidents.tsx`, `incident-group-list.tsx`.

1. Contagem compacta: "Disparou uma vez"/"2 disparos" (quebra em duas
   linhas) → `1×`, `2×`, `8×` mono, coluna estreita.
2. Sparkline de disparos em coluna própria alinhada à direita antes dos
   chips, altura fixa — hoje cola no título com largura variável.
3. Primeiro assunto em estado crítico nasce expandido: "DISPAROS NAS
   ÚLTIMAS 24 H" + timeline + callout "Última causa encontrada: …" + link
   "investigação em andamento →" quando houver run vivo do assunto.
4. Cor de "investigando": unificar com o board (verde, trabalho em curso) —
   é o mapa do bloco 2 quem decide o papel; aplicar aqui.
5. Testes, commit (`fix(console): incident subjects read like the board's rows`).

## Bloco 10 — Recursos

**Arquivos**: `screens/resources.tsx`, `resources-grouping.ts`.

1. Meta do card numa linha com truncagem: `contêiner · visto há 3 min` —
   hoje quebra em três linhas.
2. "anteontem fora" → duração pelo formatador compartilhado (`2 d fora`);
   nunca advérbio de calendário no padrão `X fora`.
3. Card ganha ícone de tipo à esquerda do nome e ponto de status no canto
   superior direito; borda vermelha de não saudável continua.
4. Ordenação "Piores primeiro" (chip à direita dos filtros de tipo, estado
   no endereço).
5. Rótulos dos chips de tipo seguem §11 (palavra do estate) — **não**
   traduzir; só o chip ativo "Todos" já é i18n.
6. Testes, commit (`fix(console): resource cards carry their meta on one line`).

## Bloco 11 — Conhecimento

**Arquivos**: `screens/knowledge.tsx`, `component-normalisation.ts`.

1. Episódio: a chave de máquina sai do título — título é a frase humana; a
   linha meta carrega `workload_stopped · <alvo> · <resumo curto>` como o
   board. (O título hoje começa com "workload_stopped: …" — corte no
   primeiro `:` quando o prefixo for palavra de máquina conhecida do
   vocabulário de episódios, e mova-o para a meta.)
2. Chips de componente curtos: `display` do `normaliseComponents` já
   existe — usar nos chips do episódio (hoje imprimem o raw
   `service:runner-orchestrator`).
3. Filtros do cabeçalho: `inconclusive`/`resolved` crus → mapa do bloco 2.
4. "Ajustes avançados": os quatro accordions viram os cards-resumo do board
   (`KnowledgeDocuments.dc.html`) — título + linha de status ("nenhuma
   configurada", "guardando · 4 episódios") + link de ação. O conteúdo dos
   accordions vive atrás do link, não empilhado na página.
5. Investigar o corte horizontal visto na captura da aba Documentos
   (painéis ultrapassando a borda direita); se reproduzir, é
   `min-width`/overflow no grid — consertar no mesmo commit.
6. Testes, commit (`fix(console): knowledge episodes lead with the human title`).

## Bloco 12 — Decisões

**Arquivo**: `screens/decisions.tsx` (+ attention.tsx só se compartilhar o
card — conferir antes; o Painel não deve mudar de aparência).

1. Chip "Expired" → "expirada há X" âmbar vazado (mapa do bloco 2 + idade).
2. Passo do plano: preferir a frase humana do payload com a ferramenta mono
   em parêntese; quando só houver a assinatura crua
   (`proxmox_start_guest(kind='lxc'…)`), imprimi-la como código (mono,
   uma linha, truncada) — nunca como se fosse prosa.
3. Evidência que sustenta: clamp de 2 linhas por item com o "ver →" fixo à
   direita; o dump de log do Proxmox de cinco linhas vive no link, não no
   bullet.
4. "Decididas recentemente": forma de desfecho por linha (ponto verde
   aprovada/aplicada/verificada; quadrado vermelho recusada) — o
   vocabulário de formas da fundação, não texto puro.
5. Nota verde de reversibilidade: uma frase, uma moldura ("Escrita
   reversível — fica na fila e só aplica depois do seu sim.") — remover o
   travessão duplicado.
6. Testes, commit (`fix(console): decision cards say their state like the board`).

## Bloco 13 — Investigações (lista)

**Arquivo**: `screens/runs.tsx` (lista) ou o screen próprio da listagem.

1. Paginação: `← Anteriores 1 2 3 Próximas →` (board), página de ~20; a
   página atual no endereço. Morre a página única de 5.700px.
2. Forma colorida por desfecho no lugar do poço de ícone repetido: ponto
   verde completada, quadrado vermelho falhou, losango acento em voo — o
   ícone de documento igual em 49 linhas não distingue nada.
3. Wording: unificar "N de M com evidência" (board) entre o chip da lista e
   as "Descobertas" do RunView — hoje "afirmações sustentadas" numa e
   "alegações com evidência" noutra.
4. Filtros `completed`/`running` crus → mapa do bloco 2.
5. Testes, commit (`fix(console): the investigations list paginates and speaks one language`).

## Bloco 14 — Ajustes e Integrações

**Arquivos**: `shell/settings-subnav.tsx`, telas de settings,
`screens/integrations` (conferir nome), i18n.

1. Sub-navegação e títulos de Ajustes inteiros em pt-BR: Membros e papéis,
   Login único, Tokens de máquina, Trilha de auditoria, Modelos e
   provedores, Autonomia e guardrails, Notificações, Entrada de alertas,
   Agendas e destinos; grupos Organização / Agente / Dados. (As chaves
   `GROUP_LABEL`/labels já passam por i18n — é preencher o pt-BR que
   falta, não inventar mecanismo.)
2. Painel "Ativa" em Membros → "Sessões ativas".
3. "Default organisation" no breadcrumb de O agente → rótulo i18n
   "Organização padrão" quando o nó for o raiz criado pelo produto.
4. Integrações: descrições por integração têm par pt-BR no catálogo? Se a
   descrição vem do deployment, fica (é o §12); se vem do catálogo do
   console, traduzir. Selects nativos "Ligação/Categoria" → chips do padrão
   da casa; campo de busca no padrão das outras telas.
5. Testes, commit (`fix(console): settings and integrations speak the console's languages`).

## Fechamento

1. `make verify` completo.
2. `deploy-stg` e passada Orca Browser nos dois temas por todas as telas
   tocadas: `/agent` (4 abas), modal Investigar, um run vivo (disparar uma
   investigação manual para ver narração + anel + controle no cabeçalho),
   `/investigations`, `/incidents`, `/resources`, `/knowledge` (3 abas),
   `/decisions`, `/settings`, `/integrations`.
3. Divergências novas que a passada encontrar e que forem *decisão* (não
   defeito) entram em DIVERGENCIAS.md com o formato da casa; defeito se
   conserta na hora, num commit de ajuste único.
4. Re-baseline do gate visual (`console/visual/`) por último, uma vez —
   os baselines antigos descrevem o console de antes dos blocos.
