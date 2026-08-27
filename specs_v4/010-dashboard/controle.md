# Controle — 010 Dashboard

| Item | Estado | Detalhe |
|---|---|---|
| 1. Erro cru como primeira leitura | **FEITO** (confirmado, não reescrito) | A camada `failures.ts` da 001.4 já cobria a faixa e o feed, e o stack cru não chega ao DOM desta tela. Uma falha reconhecida liga ao passo pendente do First steps, não ao run. Ganhou teste de regressão em vez de reescrita. |
| 2. Setup incompleto não é o hero | **FEITO** (lote 6) | `surfaces/setup-hero.tsx`: bloco central, os sete passos visíveis, o próximo destacado, um botão. Ausente — não encolhido — quando não falta nada. |
| 3. Números sem história consistente | **FEITO** (lote 6) | `Figure` ganhou seta visível (era `sr-only`); o card "Degraded and unhealthy" diz quantos detectores estão ligados para transformar um achado em incidente, que é a ponte que faltava entre "14 unhealthy" e "Incidents: nenhum". |
| 4. Faltam KPIs do agente | **FEITO com ressalva de dados** | Taxa de sucesso, calculada de `/v1/runs`. **Custo/tokens não está na lista**: só existe em `RunReplayView`/`TurnView`, um run de cada vez, portanto um KPI de custo no overview custaria um fetch por run. Não foi fabricado. |
| 5. Quick actions vagas | **FEITO** (lote 6) | `surfaces/quick-actions.tsx` reusa `page.<area>.title` e `.context` — o nome e a descrição que cada tela já tem no seu próprio cabeçalho — em vez de inventar uma segunda descrição que derivaria da primeira. |
| 6. "Estate health" não é saúde | **FEITO por remoção** | A spec autorizava as duas saídas. Saúde por tipo exigiria `/v1/estate/resources`, leitura materialmente mais pesada sem outro consumidor nesta tela. **Registado como a saída barata das duas**: "ou mostra saúde por tipo, ou sai" foi escrito esperando que alguém tentasse a primeira. |
| 7. "1 items need you" / caps | **FEITO** | Pluralização via `formatCount` (`bf5f055`); o selo deixou de gritar em caps e passou a `Waiting longest: {age}`, que diz o que mede. |

## O débito que o fan-out não podia fechar, e a integração fechou

O agente entregou o hero **e deixou o `ChecklistPanel` lateral no lugar**, porque
o componente parecia partilhado com testes que ele não podia editar. O raciocínio
estava certo e a conclusão ficou a meio: dois checklists na mesma tela enquanto o
setup está aberto é a página a discordar de si própria sobre onde olhar.

Verificado na integração: `ChecklistPanel` era usado **só** pela dashboard — os
testes em `first-run.test.tsx` renderizam a `DashboardScreen`, não a tela First
steps. Removido o uso; e com isso `ChecklistPanel` e `QuickActions` ficaram
mortos, mais 13 chaves de i18n órfãs nos dois catálogos. Apagados, pela mesma
regra do `postureOptions` do lote anterior: um componente que nada renderiza é um
componente que nada testa, e o leitor seguinte não distingue qual das duas versões
é a que embarca. O que restava do ficheiro — `NoProviderNotice` — mudou para
`first-run/no-provider.tsx`, porque um ficheiro chamado `checklist-panel.tsx` sem
checklist é uma mentira pequena.

Os dois testes que codificavam o desenho antigo passaram a afirmar a propriedade,
não a implementação: o plano aparece uma vez, o passo pendente está a um clique,
e ambos desaparecem quando o deployment está configurado.

**A baseline visual do shell foi recapturada** nos quatro viewports — o layout
mudou por decisão (hero, quinto figure, sem o card de estate).
