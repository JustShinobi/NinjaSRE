# 060 — O agente visível e ajustável

**Depende de:** 058. **Relacionada:** 050 (a tela que faria isto hoje devolve 500).

Um operador precisa poder responder três perguntas sobre o agente antes de
confiar nele com um cluster: **o que ele é, o que ele pode fazer, e o que ele vai
fazer sozinho.**

Hoje o console não responde nenhuma das três.

## O que já existe do lado do backend

**Muito mais do que eu supunha na primeira redação.** `AgentsConfig`
(`platform/config_service/schema/agents.py`) já modela a topologia inteira como
configuração:

| Campo | O que é |
|---|---|
| `subagents: tuple[SubAgentConfig, ...]` | cada um com `name`, `description`, `system_prompt`, `capabilities`, `max_iterations`, `model_role`, `enabled` |
| `prompts: PromptOverrides` | prompt por papel, caindo de volta no distribuído |
| `max_iterations`, `max_parallel_subagents`, `max_subagent_depth`, `tool_budget` | orçamentos, **limitados acima pelas constantes** — uma equipe pode baixar, nunca subir |
| `ModelsConfig` | oito papéis (`investigator`, `subagent`, `intake`, `diagnose`, `extraction`, `embedding`, `selection`, `summarisation`), cada um com provider e modelo próprios |

O módulo já registrou a decisão: *"sub-agent topology is configuration"* — quais
especialistas existem para uma equipe é a diferença entre o deployment de um time
de plataforma e o de um time de segurança, e não vale uma mudança de código.

Ou seja: **esta spec não modela nada novo. Ela desenha o editor de um schema que
já existe** — o que a torna consideravelmente mais barata do que parecia.

Ao lado disso:

- `GET /v1/capabilities` — as capacidades registradas;
- `capabilities/registry/` e `capabilities/tools/` — o catálogo de ferramentas,
  separado entre `remediation/` (que muda coisas) e `system/` (que consulta);
- `GET /v1/config/{node_id}/catalogue` — o catálogo de ajustes daquele nó, com
  tipo, faixa e padrão;
- `GET /v1/config/{node_id}/guardian` — os guardrails em vigor;
- toda a família `/v1/autonomy/policy/{node_id}` — política, limites, dry-run,
  overrides e `explain`;
- `capabilities/protocols/mcp/` — servidores MCP como fonte de ferramenta.

O material está todo lá. Falta a superfície que o torna legível.

## Escopo

### A. O que ele é — o fluxo da investigação, desenhado

Uma tela que mostra o pipeline como ele realmente é: o que planeja, o que
investiga em paralelo, o que sintetiza, o que escreve. Não como diagrama
decorativo, e sim ligado ao que está configurado — quais etapas estão
habilitadas, e o que cada uma consulta.

Isto é o que transforma "a IA investigou" em "estas quatro coisas foram
consultadas, nesta ordem, e a síntese pesou assim". A diferença entre confiar e
verificar.

O grafo é hierárquico e vale desenhá-lo assim: um orquestrador no topo,
sub-orquestradores, e os especialistas embaixo — com estado (habilitado, ponto de
entrada) marcado no próprio nó e clique para configurar. Uma visão em texto
estruturado ao lado da visual, para quem prefere editar o documento, e modelos
prontos para quem está começando.

**Uma decisão que não se copia:** superfícies parecidas costumam mostrar o modelo
fixado por etapa. Aqui não. Neutralidade de provider é artigo da constituição
deste projeto, e uma tela que exibe um identificador de modelo de um fornecedor
específico ao lado de cada etapa é uma tela que assume o que o deployment
escolheu. O que se mostra é o papel; o modelo é uma configuração resolvida, com
proveniência, como qualquer outra.

### B. O que ele pode fazer — ferramentas, com a distinção que importa

O catálogo de ferramentas, agrupado pela única distinção que muda o risco: **as
que leem e as que escrevem.** `capabilities/tools/` já separa `system/` de
`remediation/`, e essa separação precisa ser a organização visual, não um
detalhe de implementação.

Para cada ferramenta: o que faz, qual integração ela exige, e se essa integração
está configurada. Uma ferramenta cuja integração falta é a explicação para uma
investigação que não chegou a lugar nenhum, e hoje essa explicação não está em
lugar nenhum.

Servidores MCP entram na mesma lista, com sua origem indicada — uma ferramenta
que veio de fora do deployment é uma ferramenta com outra procedência, e o
operador merece ver isso.

### C. O que ele vai fazer sozinho

Já é escopo da 058 como editor. Aqui é a leitura: dado o estado atual da política,
**o que aconteceria** com um alerta de cada classe. O `explain` e o `preview` da
API de autonomia existem exatamente para responder isso, e nenhuma superfície os
chama.

Uma frase por classe de ação, no formato "isto seria proposto / isto seria
executado / isto seria recusado por limite", é mais útil do que a política em
formato bruto.

### D. Ligar com o catálogo do nó

O `GET /v1/config/{node_id}/catalogue` é a fonte de "o que dá para ajustar aqui",
com tipo e faixa. É a mesma rota que hoje derruba a tela `/catalogue` com 500
(spec 050). Consertada, ela vira a base tanto do editor de configuração (058)
quanto desta tela — o que se pode ajustar e o que aquilo significa são a mesma
informação vista de dois ângulos.

## Por que isto não é cosmético

Na validação inicial a plataforma entra observando, com dry-run ligado (055). O
material que decide se ela pode agir é o registro do que ela *teria* feito. Essa
decisão é tomada olhando uma tela, e se a tela não existir a decisão será tomada
por intuição ou não será tomada.

## Fora de escopo

- Editar a definição do pipeline pela UI. Quais etapas existem é decisão de
  arquitetura, não de configuração.
- Registrar ferramenta nova pela UI.
- Playground de prompt.

## Aceitação

1. Uma tela mostra as etapas da investigação e quais estão habilitadas, sem exibir
   identificador de modelo de nenhum fornecedor como se fosse fixo.
2. O catálogo de ferramentas separa visivelmente leitura de escrita, e marca cada
   ferramenta cuja integração não está configurada.
3. Ferramentas vindas de servidores MCP são identificáveis como tal.
4. A tela de autonomia responde, em texto, o que aconteceria com cada classe de
   ação sob a política atual, usando `explain`/`preview`.
5. Um operador consegue responder "o que esta coisa vai fazer sozinha" sem sair do
   console e sem ler YAML.
