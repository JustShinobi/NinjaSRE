# Plano — 057 Código e deploy como sinal

## O que existe, verificado

- O catálogo já fala para hosts de código: `integrations/gitlab/` tem
  `tools/recent_changes.py`, `tools/change_statistics.py`, e
  `GitlabClient.list_commits`; `integrations/argocd/` tem ferramentas de failed-runs e
  pipeline; `github` e `bitbucket` estão no catálogo. Então "que commits aterrisaram em uma janela"
  é respondível por vendor hoje — o que falta é um **conceito de mudança
  neutro a provider** que a investigação pode consultar, e a fonte **infra-apply**
  que diz o que realmente tocou o cluster.
- O enriquecimento de 053 já ingere `services.yaml` e mapeia componentes →
  workloads; a metade path → component é uma regra sobre o layout do repositório
  (`services/monitoring/…` → componente `monitoring`).
- A tela de run renderiza uma timeline; D3 §2 fixa onde o overlay de mudança
  vai (o ruler do footer).

## Escopo A — a fonte de mudança

Um novo conceito de domínio: `platform/changes/` (tier 3) com um protocolo
`ChangeSource` — um método, com forma de janela: *o que foi alterado entre
T−N e T*, cada mudança carregando identificador, autor, instante, mensagem,
caminhos tocados, e (quando derivável) o componente. Mesmo padrão protocolo-em-plataforma,
implementações-abaixo que estate discovery (precedente 038 deviations §9:
tier 3 nomeia o contrato, tier 2 o satisfaz).

Duas implementações:

1. **`infra_apply`** — a mais valiosa, construída primeiro e sozinha
   suficiente (a spec diz assim). Lê o registro de apply
   (`.infra-state/` + o git log de revisões aplicadas) do mesmo
   transporte read-only path-or-URL que 053/056 estabeleceram. Um apply é
   uma mudança que *tocou o cluster*; um commit que ninguém aplicou é registrado
   como tal — a distinção applied/committed é um campo na mudança,
   não duas fontes discordando.
2. **Git host** — um adaptador fino sobre as chamadas `list_commits`-shaped
   dos clientes de integração existentes, para o caso comum além deste cluster.
   Qual vendor a respalda é configuração; a fonte é neutra.

Ambas são capacidades somente-leitura com metadados completos (Artigo IX); o agent
recebe uma ferramenta tipada — `changes_in_window(resource, window)` — que consulta
as fontes e retorna mudanças *já correlacionadas* (Escopo B), então o modelo
nunca re-deriva a regra path→resource.

## Escopo B — correlação através do recurso, com força reportada

`platform/changes/correlation.py`, pura:

- caminho tocado → componente (regra de layout-repositório, dirigida por dados da
  lista de componentes ingerida, não hard-coded);
- componente → workloads (mapeamento de enriquecimento de 053);
- workload → o recurso sob investigação.

O resultado é um `CorrelatedChange` carregando **força como uma enumeração
fechada**: `MANAGES_RESOURCE` (path→component→este workload),
`TOUCHES_SHARED_POLICY` (ex. `policies/firewall/` e o firewall profile do
recurso), `WINDOW_ONLY` (mesma janela, sem link de recurso). O
relatório renderiza a força; uma mudança `WINDOW_ONLY` é rotulada como coincidência
temporal em tantas palavras (aceitação 3). O exemplo de firewall da
spec é um caso de fixture.

**O negativo é first-class**: um resultado vazio dentro da janela é
retornado como uma entrada de evidência explícita "nenhuma mudança tocou este
recurso nas últimas N horas" — uma afirmação com uma fonte (as fontes consultadas
e sua cobertura), não uma ausência (aceitação 4, e o "quando o
sistema não consegue determinar algo, o diz" do Artigo I.4 invertido: aqui ele *pode*
determinar um negativo e deve dizê-lo com a mesma confiança).

## Escopo C — onde aparece

- **Evidência**: os resultados de `changes_in_window` entram no trace como
  qualquer resultado de ferramenta; o relatório pode então carregar a frase da spec
  ("às 14:19 o componente `monitoring` foi aplicado…") com o identificador de mudança como
  a citação.
- **O footer da tela de run**: a timeline ganha o overlay de mudança — deploys
  como marcas no mesmo ruler que a janela de erro (D3 §2). Console lê as
  mudanças correlacionadas da evidência do run; sem nova rota além de expor
  o resultado da ferramenta no detalhe do run, que o trace já faz.
- **Detalhe do recurso**: painel "mudanças recentes que tocaram isto", do
  mesma correlação, completando o quarteto de detalhe de D3 §3 (sinais 054,
  documentos 056, investigações existentes, mudanças aqui).

## Decisões que a spec deixou abertas

1. **N (a janela padrão)** é uma constante nomeada
   (`config/constants/changes.py`), padrão para 24 horas para a
   afirmação negativa e uma janela first-look mais curta para a frase do relatório —
   ambas configuráveis via a árvore de 058 depois.
2. **Sem conteúdo de diff é lido** — correlação é sobre caminhos e instantes
   apenas (fora de escopo da spec, feito estrutural: o registro de mudança não tem
   campo diff, então julgar mérito não pode se introduzir).
3. **Higiene de segredo**: mensagens de commit e caminhos passam o mesmo screening
   de guardrail que a ingestão de 056 antes de armazenamento ou entrada de trace — um token
   colado em uma mensagem de commit é o óbvio caminho de vazamento, e o
   teste de varredura o cobre (aceitação 5).

## O que esta feature NÃO faz

- Sem revert (remediação, após histórico de política de autonomy existir).
- Sem repositórios de aplicação — o protocolo está pronto para eles; apenas as
  duas fontes acima são construídas.
- Sem sinal de status de CI (ferramentas argocd existem para isso; não fiado aqui).

## Verificação de constituição

- **I** — cada correlação carrega sua força e sua cadeia de caminho; a
  afirmação negativa nomeia o que foi consultado.
- **II** — limites de janela e caps de mudança por-janela são constantes nomeadas.
- **III/IX** — uma capacidade somente-leitura com metadados declarados; nada
  writes.
- **VI** — no vendor dependency above the integration tier; `infra_apply`
  works with zero cloud access.
- **VII** — a synthetic scenario ("error at T, apply at T−13min on the
  managing component") with the correlation ablatable; scenario-suite delta
  reported.
- **VIII/XI** — protocol tier 3, sources tier 2, storage (if changes are
  cached at all — decision: they are queried live, not stored, so no new
  port) untouched.
- **XII** — fixtures from the real repository's commit-message and
  apply-record shapes.
