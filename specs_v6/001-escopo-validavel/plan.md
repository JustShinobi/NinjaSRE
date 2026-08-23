# Implementation Plan: Escopo validável — o catálogo cai para o que o ambiente valida

**Branch**: `feat/v6-001-escopo-validavel` | **Date**: 2026-08-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v6/001-escopo-validavel/spec.md`

**Referência visual (DoD)**: nenhuma. Feature sem tela própria — ver o cabeçalho
da spec. A superfície de console do catálogo é da 050.

## Summary

Remoção de 70 dos 85 pacotes de vendor de `integrations/`, com os satélites que
a paridade exige (skill de metodologia, cenário sintético, documentação por
integração, fixtures), redução das fontes de intake de sete para três, e
reacerto de todo gate, contagem e documento que hoje afirma 85. A regra escrita
acompanha: um registro de decisão arquitetural novo supersede o de paridade
total, e a cláusula de paridade da constituição local passa a condicionar a
amplitude do catálogo a haver ambiente que valide.

A forma da paridade **não muda**. Continuam sendo sete artefatos, continuam
sendo enforçados por gate, e continuam valendo para toda integração embarcada.
O que muda é quantas integrações são embarcadas, e por qual critério.

## Technical Context

**Language/Version**: Python 3.12 (catálogo, gateway, gates, testes); TypeScript
(console, tocado apenas para não deixar órfão)

**Primary Dependencies**: `integrations/_catalogue/` (descoberta e validação de
paridade), `integrations/_verification/`, `gateway/webhooks/router.py`,
`core/domain/alerts/sources.py`, `tools/verify_integrations.py`,
`tools/generate_integration_docs.py`, `tools/check_docs_drift.py`

**Storage**: N/A. Nenhuma migração de dados; credencial órfã de vendor removido
permanece no vault e é ignorada pelo catálogo.

**Testing**: pytest (contrato de catálogo, contrato de intake, paridade,
cenários sintéticos); vitest e Playwright do console apenas como regressão do
que já passava. Sem acceptance spec nova — não há mockup nesta feature.

**Target Platform**: backend Python + console web

**Project Type**: corte de escopo transversal ao repositório

**Performance Goals**: N/A. O ganho é de superfície, não de latência.

**Constraints**: a verificação completa do repositório precisa terminar verde
tendo partido de verde, e a comparação entre as duas rodadas é a evidência. A
remoção não pode afrouxar nenhum gate para passar.

**Scale/Scope**: 85 pacotes de vendor → 15. 70 skills de metodologia e 70
cenários sintéticos saem junto. Sete fontes de intake → três.

## Constitution Check

*GATE: precisa passar antes da execução. Reconferir ao final.*

Esta feature **emenda a constituição**, então a checagem tem duas partes: a
conformidade do trabalho com os artigos vigentes, e a emenda em si.

| Artigo | Como este plano satisfaz |
|---|---|
| I — Evidência sobre asserção | O critério do corte não é gosto: é o inventário do cluster levantado em 2026-08-16, que nomeia o que roda e o que não roda. Cada vendor mantido tem um lugar no ambiente; cada removido não tem. A rodada de verificação anterior ao corte é capturada para que "continuou verde" seja uma comparação e não uma alegação. |
| II — Autonomia limitada | Não toca laço, orçamento nem limite. |
| III — Leitura por padrão | Não toca semântica de escrita nem de aprovação. Nenhum vendor removido tinha capacidade de escrita que sobrevivesse ao pacote. |
| IV — Segredo nunca chega ao agente | Não toca o proxy de credencial. A credencial órfã de vendor removido continua atrás do proxy e deixa de ter cliente que a peça — a superfície de exposição diminui. |
| V — Um runtime canônico | Não toca runtime. |
| VI — Neutralidade de provedor | O único provedor de modelo embarcado passa a ser um só. **Isso não é uma decisão de neutralidade**: a neutralidade é uma propriedade da abstração de provedor, que fica intacta, e o catálogo de provedores é outra lista. O plano não remove nenhum adaptador de provedor. |
| VII — Aprendizado é medido | Não toca mecanismo de aprendizado. |
| VIII — Arquitetura em camadas | A remoção só apaga pacotes de um tier e as referências a eles. As checagens de contrato de import rodam na verificação final e são o gate de que nenhuma camada ficou apontando para o vazio. |
| IX — Capacidades declaradas | **É o artigo emendado.** Ver a seção seguinte. A cláusula dos sete artefatos permanece e continua enforçada; as 15 mantidas precisam estar completas ao final, e o gate reprova nomeando integração e artefato se o corte derrubar algo de uma delas. |
| X — O operador é dono dos dados | Nada sai do host. Nenhum dado do operador é apagado — credencial gravada permanece. |
| XI — Datastore único | Não toca porta de persistência. |
| XII — Test-first, rastreado | **Cláusula 3 é a que morde aqui**: remover 70 cenários sintéticos é uma mudança que afeta investigação, e o efeito sobre a suíte de cenários tem de ser *reportado*, não presumido. O plano exige a contagem antes e depois e a lista do que saiu. "Sem efeito" seria uma resposta aceitável; "não medido" não é. As demais cláusulas: cada gate reacertado ganha seu vermelho antes do corte. |
| XIII — Idioma e atribuição | Todo arquivo committed em inglês. O registro de decisão novo é autocontido: quem clonar o repositório consegue lê-lo inteiro sem abrir nenhum documento que não esteja no repositório. |

### A emenda

**O que está errado hoje.** O registro de decisão vigente sobre paridade decide
"todas as ~85 integrações em paridade total na v1" e trata amplitude como
inegociável, listando explicitamente "~20 curadas, o resto migrado" entre as
alternativas rejeitadas. A cláusula de paridade da constituição absorveu essa
decisão. Se o catálogo cair para 15 sem tocar nesses dois textos, a norma passa
a exigir paridade sobre um conjunto que não existe, e qualquer plano futuro
reprova a checagem contra ela por um motivo que já foi decidido.

**O que muda, exatamente.** A paridade continua sendo sete artefatos e continua
valendo para toda integração embarcada. O que passa a ser normativo é a
condição de entrada: uma integração só é embarcada quando existe ambiente capaz
de validá-la ponta a ponta — credencial armazenada, conexão verificada e ao
menos uma leitura real exercitada. Amplitude vira consequência do ambiente, não
meta independente.

**Como a emenda é feita.** A regra de governança do próprio documento exige um
registro de decisão arquitetural declarando driver, alternativas e
consequências, mais um aumento de versão. Então:

1. Um registro novo é escrito e aceito, e o anterior passa a superseded com data
   e ponteiro para o sucessor. O índice de registros reflete os dois estados.
2. A cláusula de paridade da constituição local recebe a condição de ambiente
   validável, e o cabeçalho do documento registra a emenda em sumário.
3. O ponteiro que o cabeçalho da constituição hoje faz ao registro de decisão
   superseded passa a apontar o sucessor.

**Qual aumento de versão.** MINOR. A regra de versionamento pede MAJOR para
remover ou reverter um artigo, MINOR para acrescentar um ou expandir
materialmente uma cláusula, PATCH para redação. Nada é removido nem revertido: a
obrigação de paridade permanece com a mesma força e o mesmo alcance sobre o que
está no catálogo. O que se acrescenta é uma condição de entrada que antes não
era normativa. Isso é expansão material de cláusula, logo MINOR — a versão sai
de 2.1.0 para 2.2.0.

A leitura alternativa é que restringir o catálogo *reduz* o alcance da norma e
pediria MAJOR. Ela foi considerada e recusada: o alcance da cláusula é "toda
integração do catálogo", e essa quantificação não muda de forma. O que muda é a
população sobre a qual ela quantifica, que sempre foi variável — o catálogo já
cresceu e encolheu sem emenda.

**Onde a regra fica legível para quem clona.** A constituição é local-only. O
registro de decisão novo é committed e é onde a decisão vive para o público, e
por isso ele precisa se sustentar sozinho, sem exigir do leitor um documento que
não veio no clone. A seção de escopo de integrações do roadmap committed é o
lugar onde a amplitude corrente é lida, e o registro aponta para ela.

### Complexity Tracking

Nenhuma violação a justificar. A feature reduz complexidade: menos pacotes,
menos rotas, menos fixtures, menos superfície que um gate precisa segurar.

## Project Structure

### Documentation (this feature)

```text
specs_v6/001-escopo-validavel/
├── spec.md
├── plan.md              # este arquivo
├── tasks.md
├── controle.md          # do implementer, não deste plano
└── checklists/requirements.md
```

### Source Code (repository root)

```text
integrations/<70 pacotes>/                      # removidos inteiros
capabilities/skills/<70>/                       # skill de metodologia de cada removido
tests/synthetic/integration_scenarios/<70>.py   # cenário sintético de cada removido
integrations/AGENTS.md                          # contagem
gateway/webhooks/router.py                      # sete fontes de intake → três
core/domain/alerts/sources.py                   # enumeração de fonte
gateway/http/routes/integrations.py             # catálogo servido; lista de não cobertos intacta
tests/contract/integrations/                    # paridade e garantias de catálogo, sobre 15
tests/contract/                                 # contrato de intake
docs/integrations-catalogue.md                  # regenerado
docs/site/integrations/                         # regenerado; categorias que esvaziam
docs/adr/0015-*.md                              # registro novo
docs/adr/0009-full-integration-parity.md        # passa a superseded
docs/adr/README.md                              # índice
docs/roadmap.md                                 # só validado, não reescrito
docs/vision.md                                  # contagem
console/src/shell/routes.ts                     # comentário com contagem
console/src/gallery/registry.tsx                # número exibido
console/visual/screens.json                     # entrada apontando para vendor removido
console/tests/                                  # regressão do que já passava
fixtures/scenarios/                             # fixtures que nomeiam vendor removido
pyproject.toml                                  # dependência opcional de vendor removido
```

**Structure Decision**: nenhuma estrutura nova. O trabalho é subtração
distribuída por tiers já existentes, mais dois documentos novos (o registro de
decisão e a emenda da constituição local).

## Decisões de design

- **A ordem é gate-primeiro, remoção-depois.** Os testes que afirmam "o catálogo
  tem exatamente estas 15" e "as fontes de intake são estas três" entram antes
  de qualquer pacote sair, e são confirmados vermelhos contra a árvore de 85.
  É o único jeito de esta feature ter um vermelho honesto: uma remoção validada
  só depois do fato não distingue "removi certo" de "o teste não olha".

- **A rodada de verificação anterior ao corte é artefato.** O log é capturado
  antes da primeira remoção. Sem ele, uma falha preexistente é debitada do
  corte, e uma falha causada pelo corte se esconde atrás de "já estava assim".

- **A remoção é por vendor, em um passo por vendor, não em uma varredura.** Cada
  pacote sai com seus quatro satélites juntos. Uma varredura por padrão de nome
  apagaria `redis` ao mirar `redis_server`, e `proxmox` ao mirar
  `proxmox_backup_server`. Os nomes das 15 mantidas são prefixo ou substring de
  nomes removidos em pelo menos três casos, e essa é a armadilha concreta desta
  feature.

- **A fronteira entre pacote de integração e componente homônimo é explícita.**
  Slack, Microsoft Teams, Discord e PagerDuty existem como destino de
  notificação e como superfície de chat, em módulos próprios, e não são o pacote
  de integração de mesmo nome. Esses módulos permanecem. Uma varredura por nome
  de vendor que não conheça essa fronteira derruba capacidade que o operador
  usa, e é o segundo modo de falha desta feature.

- **A isenção de paginação da categoria provedor de modelo fica como está.** Ela
  existe porque o cliente de um provedor é uma checagem de alcance e não tem
  segunda página para pedir; ela se auto-policia, exigindo que o cliente não
  exponha nada além disso. O provedor mantido é justamente o que a exercita, e o
  corte não pode fazer a isenção deixar de ser exercitada nem alargá-la.

- **A lista de vendors não cobertos não recebe as 70.** Ela responde "nunca foi
  construído, e por quê". A intenção das removidas vive no roadmap committed.
  Misturar as duas transforma a página de referência da 050 num despejo e apaga
  a distinção entre "não existe" e "existiu e foi diferido por falta de
  ambiente".

- **Documentação gerada é regenerada, nunca editada à mão.** As páginas de
  catálogo e de categoria saem do gerador; a checagem de desvio é o que prova
  que saíram. Três categorias esvaziam por completo e o gerador precisa deixar
  de emitir a página e de listá-la no índice.

- **O console é tocado só onde ficaria órfão.** Uma entrada do registro de telas
  visuais aponta hoje para a rota de detalhe de um vendor que sai. Ela é
  repontada para um vendor mantido ou removida — e se um baseline morrer junto,
  ele é apagado deliberadamente, nunca substituído por captura fabricada.

- **O registro de decisão novo se sustenta sozinho.** Ele enuncia a regra em
  substância. Não pede ao leitor que abra a constituição, o roadmap de
  planejamento nem qualquer documento fora do repositório — o único ponteiro
  externo que ele faz é para a seção de escopo do roadmap committed, que veio no
  clone.
