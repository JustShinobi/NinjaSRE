# specs_v4 — Auditoria de UI/UX do console

> **Controle de execução:** [CONTROLE.md](CONTROLE.md) — status agregado por
> spec, desvios e motivos. Cada diretório de spec tem um `controle.md` com o
> status item a item.

Auditoria feita em 2026-08-12 navegando a aplicação real
(`https://ninjasre--3101.preview.lan.kyo.ninja/`, admin, deployment com Proxmox +
Prometheus + Gemini configurados e investigador ainda não configurado), tela a
tela, com screenshots, leitura do texto renderizado e testes de interação.

O sintoma que motivou a auditoria, nas palavras do operador: **"o usuário entra
e não sabe o que fazer, como configurar, e tem coisas que não funcionam."** A
auditoria confirma o sintoma e o decompõe em causas por tela.

## Como ler

Uma spec por entrada do sidebar, mais uma para o shell (topbar, busca, tour,
i18n) e uma de reorganização de escopo. Cada spec lista os problemas na ordem
de gravidade, com um escopo de correção proposto.

Severidade usada nas specs:

- **[quebrado]** — não funciona; erro visível, dado errado ou ação sem efeito.
- **[bloqueia entendimento]** — funciona, mas o operador não consegue descobrir
  o que fazer a partir da tela.
- **[polimento]** — texto, layout, consistência.

## Índice

| Spec | Tela | Estado geral |
|---|---|---|
| [001](001-shell-navegacao-e-busca/spec.md) | Shell: topbar, busca, tour, notificações, i18n | 2 quebrados, vários graves |
| [010](010-dashboard/spec.md) | Dashboard (Overview) | grave |
| [011](011-incidents/spec.md) | Incidents | leve |
| [012](012-runs/spec.md) | Runs / Investigations | grave |
| [013](013-approvals/spec.md) | Approvals | leve |
| [020](020-resources/spec.md) | Resources | grave |
| [021](021-topology/spec.md) | Topology | médio |
| [022](022-detectors/spec.md) | Detectors | grave |
| [023](023-memory/spec.md) | Memory | leve |
| [024](024-knowledge/spec.md) | Knowledge | leve |
| [025](025-catalogue/spec.md) | Catalogue | crítico |
| [030](030-first-steps/spec.md) | First steps | **crítico — funil inconcluível, 6 defeitos com causa-raiz** |
| [031](031-autonomy/spec.md) | Autonomy | grave |
| [032](032-configuration/spec.md) | Configuration | crítico |
| [033](033-team-context/spec.md) | Team context | médio |
| [034](034-proposals/spec.md) | Proposed changes | quebrado |
| [035](035-agent/spec.md) | The agent | leve |
| [036](036-administration/spec.md) | Administration | grave |
| [037](037-data/spec.md) | Data | médio |
| [038](038-audit/spec.md) | Audit | grave |
| [090](090-reorganizacao-de-menus-e-escopo/spec.md) | Reorganização de menus e escopo | proposta |

## O achado central da segunda revisão (2026-08-12)

O ciclo de valor — setup → alerta → investigação → diagnóstico → decisão —
**não fecha de ponta a ponta por seis defeitos independentes**, todos
reproduzidos ao vivo e com causa-raiz no código. O checklist do first-run é
inconcluível (nodeId vazio, patch achatado recusado pelo schema, conclusão
lida por chave achatada, verify testando o modelo errado, checks que não
persistem) e, por baixo de tudo, o runtime do investigador é uma env var de
composição que nenhuma tela cobre — mesmo com tudo configurado, investigações
falham. A cadeia completa, com arquivos e linhas, está na
[spec 030](030-first-steps/spec.md). **Esse é o item número um do plano de
correção.**

## Os cinco problemas que mais explicam o sintoma

1. **O tour de onboarding nunca morre.** Nem "Skip" nem concluí-lo persiste a
   dispensa: toda visita ao Overview reabre "1 of 5". A configuração
   `surfaces.console.tutorial_dismissed` existe exatamente para isso e não é
   gravada. (spec 001)
2. **A primeira coisa que o operador lê é um stack de erro.** O item "needs
   you" do dashboard, o run failed, e a notificação do sino mostram, todos, o
   texto cru `InvestigatorNotConfigured: ... Set NINJASRE_INVESTIGATOR to
   'module:factory' ...` — uma mensagem para quem fez o deploy, não para quem
   usa o console, repetida em quatro lugares. (specs 010, 012, 001)
3. **A busca global não busca.** O placeholder promete "Search resources, runs,
   incidents"; digitar o nome de um recurso existente devolve "Nothing matches
   that". Só navega entre páginas. (spec 001)
4. **As telas de configuração expõem o interior da máquina.** Configuration é o
   schema inteiro num formulário só, com docstrings internas (números de FR,
   artigos da constituição, caminhos de arquivo) vazando para a UI; Catalogue
   mistura 233 tools, ~100 skills e 85 formulários de credencial numa página
   sem busca. (specs 032, 025)
5. **18 itens de menu para ~6 tarefas reais.** Approvals e Proposed changes são
   dois inboxes quase sinônimos; Memory, Knowledge e Topology são três telas
   para "o que o agente sabe"; Detectors e Data são duas metades de "como
   sinais entram". A spec 090 propõe a fusão defensável de cada grupo.

## Referência de forma

O dashboard de `demo.opensre.in/team/` foi apontado pelo operador como
alinhado ao esperado: sidebar de 5 itens, hero com ações concretas
("Investigate Now" por cenário), KPIs de valor (total de runs, taxa de sucesso,
MTTD), atividade recente em prosa legível, quick actions com descrição. As
specs 010 e 090 usam essa forma como norte — não para copiar, mas como régua de
densidade e de orientação a ação.
