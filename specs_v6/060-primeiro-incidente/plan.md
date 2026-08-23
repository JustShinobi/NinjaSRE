# Implementation Plan: O primeiro incidente ponta a ponta

**Branch**: `feat/v6-060-primeiro-incidente` | **Date**: 2026-08-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v6/060-primeiro-incidente/spec.md`

**Referência visual (DoD)**: `specs_v6/mockups/settings-v6.html#m6`

## Summary

Um alerta do Alertmanager da stack de monitoring atravessa o produto inteiro:
entrega autenticada por delivery token, incidente aberto, investigação executada
por um runtime que este deployment passa a ter, e uma timeline em `/incidents/[id]`
que mostra recebimento, hipóteses, evidências com a consulta real, diagnóstico e
entrega — terminando num painel de ação proposta que declara blast radius e postura
e espera decisão.

O trabalho tem três naturezas e o plano as mantém separadas:

1. **Produto que falta existir** — a composição de um runtime de investigação (hoje
   o único implementador do contrato é o recusador), os registros de raciocínio na
   timeline (hoje só há registros de ciclo de vida) e a página do incidente
   redesenhada para o M6.
2. **Infra que precisa ser mexida** — o receiver novo no Alertmanager da stack e o
   runtime publicado no CT254. Entram como fases operacionais com verificação pelo
   próprio produto e rollback escrito **antes** da mudança.
3. **Cenários que precisam ser reexecutáveis** — T1 sintético e T2 falha real
   controlada, como roteiros com pré-condições, comandos, evidência esperada e
   reversão.

## Technical Context

**Language/Version**: Python 3.12 (gateway, core, platform) e TypeScript (console)

**Primary Dependencies**: entrega já existente em `gateway/webhooks/` (roteador,
dedup, idempotência, ledger, perfil do Alertmanager); contrato de investigação em
`gateway/http/services.py` e a resposta única de `gateway/http/runtime.py`; loop
canônico em `core/agent/react_loop.py` e o pipeline em `core/pipeline/`; porta de
incidentes em `platform/persistence/ports/incident_store.py`; aprovações e plano de
reversão em `gateway/http/routes/approvals.py` e a decisão em
`gateway/http/routes/interactions.py`; tela em
`console/src/surfaces/screens/incident-detail.tsx`

**Storage**: PostgreSQL, alcançado só por porta de repositório; tipos novos de passo
de timeline exigem migração reversível

**Testing**: pytest (contrato e unidade), Playwright projeto `behaviour`
(`console/tests/e2e/`), vitest (`console/tests/unit/`), Playwright projeto `visual`
para a baseline da página do incidente

**Target Platform**: deployment self-hosted; validação no CT254 (`192.168.68.74`)
com o Alertmanager da stack em `10.20.20.37`

**Project Type**: Web (console + gateway) com trabalho operacional de deployment

**Performance Goals**: nenhum novo; a investigação herda os limites do loop canônico

**Constraints**: propose-only de ponta a ponta; o valor do delivery token nunca
entra em trace, timeline ou tela; nenhuma superfície pode afirmar runtime presente
sem que o objeto composto o confirme; a página do incidente cabe em dois viewports
de 1080p

**Scale/Scope**: uma página de console redesenhada, cinco tipos novos de registro de
timeline, uma composição de runtime, um receiver de Alertmanager, dois roteiros de
cenário

## Constitution Check

Constituição em `.specify/memory/constitution.md`, versão 2.1.0. Cada artigo, e
como este plano o satisfaz.

- **Art. I — Evidência sobre asserção**: é o eixo da feature. Cada evidência registra
  a consulta executada e o resultado (FR-019), o diagnóstico referencia as evidências
  que o sustentam (FR-020), e uma conclusão sem lastro é registrada como hipótese e
  não como diagnóstico (FR-021). O cartão de ação proposta não aparece quando não há
  evidência — propor remediação sobre nada é o pior desfecho desta tela.
- **Art. II — Autonomia limitada**: a composição usa o loop canônico com os limites
  que ele já carrega (teto de iterações, orçamento de contexto, teto de payload de
  schema, cache de chamadas repetidas, corte por estagnação). Nenhum limite novo
  nasce no site de chamada: se a fábrica precisar de um, ele vira constante nomeada
  em `config/constants/`, e `check-constants` prova.
- **Art. III — Somente leitura por padrão**: propose-only de ponta a ponta. A ação
  proposta declara blast radius e postura na tela (FR-048, FR-049), aprovar registra
  decisão e decisor antes de qualquer efeito (FR-055), o plano de reversão existe
  antes da execução (FR-056), e nada acima de leitura executa sem decisão registrada,
  nem durante o T2 (FR-059). A aprovação é por ação, e não se estende à seguinte.
- **Art. IV — Segredos não chegam ao agente**: o delivery token autentica a entrada e
  **nunca** é escrito no trace, na timeline ou na tela. A timeline nomeia o token
  pelo nome de exibição da credencial (FR-040), do mesmo modo que o mockup escreve
  "delivery token am-cluster"; o valor foi mostrado uma vez, na emissão (FR-002). As
  credenciais das integrações consultadas na investigação continuam entrando na
  borda de rede pelo proxy de credenciais, e a amostra do corpo entregue aparece
  mascarada (FR-006).
- **Art. V — Um runtime canônico**: a composição desta feature é a do loop de
  primeira classe, e é a única. Nenhum adaptador alternativo entra aqui, e nenhum
  número de benchmark passa a sair de outro lugar.
- **Art. VI — Neutralidade de provider**: a fábrica recebe o provider pela abstração;
  nenhum módulo fora de `core/llm/` importa SDK de vendor. Um deployment com modelo
  local continua compondo o mesmo runtime. Quando o provider degrada, a investigação
  reporta a degradação com a palavra canônica em vez de falhar em silêncio.
- **Art. VII — Aprendizado é medido ou não é alegado**: esta feature não adiciona
  mecanismo de aprendizado, e portanto não faz alegação de melhoria. O incidente fica
  registrado; o que se aprende com ele é outra feature.
- **Art. VIII — Arquitetura em camadas**: a composição do runtime é trabalho de ponto
  de entrada — ela escolhe provider, catálogo de capacidades e proxy de credenciais —
  e por isso vive no Tier 1, em `gateway/`. Colocá-la em `platform/` ou `core/`
  (Tier 3) exigiria importar `capabilities/` (Tier 2), que é para cima e é
  exatamente o que `import-linter` recusa. Os registros novos de timeline ficam no
  módulo que já é dono da timeline.
- **Art. IX — Capacidades são declaradas**: a remediação proposta é uma capacidade
  declarada, com nível de efeito acima de leitura, exigência de aprovação, schema
  limitado e metadados completos. As integrações que a investigação consulta são as
  do catálogo pós-corte, cada uma com os sete artefatos de paridade — nenhuma
  integração nova nasce aqui.
- **Art. X — O operador é dono dos dados**: nada sai do host. A entrega vem do
  Alertmanager do próprio operador, os destinos de relatório são os que ele
  configurou, e nenhuma parte desta feature consulta serviço externo por versão,
  licença ou telemetria.
- **Art. XI — Datastore único**: os registros novos de passo entram pela porta de
  incidentes; nenhum SQL fora da camada de persistência. Mudança de schema entra
  como migração reversível.
- **Art. XII — Test-first, com trace**: o acceptance spec do console nasce antes da
  tela e é confirmado vermelho; os testes de contrato da entrega e do detalhe de
  incidente nascem antes das rotas; o efeito no conjunto de cenários sintéticos é
  reportado — "sem efeito" é resposta aceitável, "não medido" não é. Os testes que
  inspecionam texto (as palavras exatas dos chips) são pareados com os que exercitam
  comportamento.
- **Art. XIII — Idioma e atribuição**: todo texto de produto em inglês, com o par
  pt-BR entrando junto no i18n. Nenhum arquivo committed referencia caminho de
  planejamento: os roteiros de cenário vivem no diretório desta feature, que não é
  committed, e nada committed aponta para eles. O que um arquivo committed precisar
  saber, ele afirma por conta própria.

**Veredito**: sem violações. A seção Complexity Tracking fica vazia.

## Project Structure

### Documentation (this feature)

```text
specs_v6/060-primeiro-incidente/
├── spec.md
├── plan.md                      # este arquivo
├── tasks.md
├── checklists/requirements.md
├── runbooks/                    # criado na fase de cenários
│   ├── t1-sintetico.md
│   └── t2-falha-real.md
└── controle.md                  # escrito pelo implementador, não aqui
```

### Source Code (repository root)

```text
gateway/runtime/                            # composição do runtime canônico (Tier 1)
gateway/http/asgi.py                        # passa a resolver a fábrica de primeira parte
gateway/webhooks/router.py                  # entrega: recusa, duplicata, resolução
gateway/webhooks/sources/alertmanager.py    # perfil da fonte (já correto; confirmado por teste)
gateway/http/routes/incidents.py            # detalhe com passos, custo e duração
gateway/http/routes/ingress.py              # emissão do delivery token de entrega
platform/persistence/ports/incident_store.py     # tipos novos de passo de timeline
platform/persistence/postgres/...                # migração reversível dos tipos novos
console/src/surfaces/screens/incident-detail.tsx # a página do M6
console/src/i18n/en.ts
console/src/i18n/pt-BR.ts
console/visual/screens.json                      # registro da tela e baseline
tests/contract/console/                          # console contra a API que consome
tests/contract/alerts/                           # entrega do Alertmanager
tests/contract/remediation/                      # ação proposta e decisão
tests/unit/                                      # registro de passos, dedup, resolução
console/tests/e2e/060-primeiro-incidente.acceptance.spec.ts
console/tests/unit/
```

**Structure Decision**: web com dois lados. O backend ganha a composição do runtime
(Tier 1, em `gateway/`), os registros de raciocínio na timeline (porta de
incidentes) e a exposição de passos, custo e duração no detalhe do incidente. O
console reescreve `/incidents/[id]` contra o M6. Os arquivos de escrita única da
onda (`console/src/i18n/*.ts`, `console/visual/screens.json`) são tocados aqui como
última feature da sequência.

## Decisões de design

- **A fábrica de runtime é de primeira parte e não pede código ao operador.** Hoje a
  configuração aponta para `módulo:fábrica` e não existe fábrica nenhuma no
  repositório — o operador teria que escrever uma. A feature entrega uma, composta a
  partir do provider verificado, do catálogo de capacidades e do proxy de
  credenciais, e o deployment passa a apontar para ela.
- **A resposta "tem runtime?" continua vindo do objeto composto.** Uma checagem que
  lesse a configuração diria "sim" para uma fábrica que falhou ao importar. Essa
  indireção já existe e é preservada deliberadamente; os testes a fixam.
- **A timeline ganha tipos, não uma segunda timeline.** Recebimento, hipóteses,
  evidência, diagnóstico e entrega entram como tipos novos de passo ao lado dos de
  ciclo de vida, na mesma ordem cronológica. Uma lista paralela de "passos da
  investigação" seria a fonte dupla que a onda inteira existe para matar.
- **A evidência carrega a consulta.** O passo de evidência guarda o texto da consulta
  executada e o resultado obtido, não uma frase sobre eles. É o que permite a tela
  do M6 desenhar o bloco monoespaçado sob cada evidência, e é o Artigo I em forma de
  dado.
- **O custo e a duração são lidos, não recalculados.** O cabeçalho do cartão de
  investigação mostra o que o run contabilizou. Quando um dos dois não existe, ele
  some do cabeçalho em vez de aparecer como zero.
- **O receiver novo convive com o existente.** A rota do Alertmanager espelha o
  alerta para o NinjaSRE sem tirar a entrega do antecessor. Uma migração que
  desligasse o receiver atual transformaria uma validação em um corte de
  observabilidade.
- **Os roteiros de cenário não são committed.** Eles vivem no diretório desta
  feature. Nenhum arquivo committed aponta para eles, e a evidência de execução vai
  para o `controle.md` da feature.
- **T2 nunca vira um comando automatizado.** O passo destrutivo é digitado por uma
  pessoa numa janela combinada. Um script que derruba contêiner por conta própria
  seria a contradição exata da postura que a feature existe para demonstrar.

## Fases operacionais de infra

Estas fases mexem em máquinas fora do repositório. Cada uma declara pré-condição,
ação, **verificação pelo próprio produto** e **rollback escrito antes da mudança**.
Nenhuma delas começa antes de a anterior verificar.

### Fase O-A — Rota de rede da zona de infraestrutura até o gateway

- **Pré-condição**: nenhuma. É a primeira coisa que se faz, porque tudo depois
  depende dela.
- **Ação**: nenhuma alteração. Apenas verificar, de dentro do host da stack de
  monitoring (`10.20.20.37`), se `192.168.68.74:8420` é alcançável.
- **Verificação**: o endpoint de entrega responde **401** sem token. O 401 é o sinal
  correto: prova que a rota existe e que o trust está funcionando. Um timeout, uma
  conexão recusada ou um 404 reprovam a fase.
- **Rollback**: nada a reverter — nada foi mudado. Se for necessário abrir uma regra
  de firewall para que a rota exista, essa regra é registrada com o comando exato de
  reversão **antes** de ser aplicada, e a reversão é executada se a feature for
  abandonada.
- **Se reprovar**: a fase O-B não começa. O fallback documentado é entregar por um
  salto já permitido na zona (o mesmo caminho que hoje alcança o antecessor), e a
  decisão de qual caminho usar é do operador.

### Fase O-B — Receiver do NinjaSRE no Alertmanager da stack

- **Pré-condição**: O-A verificada; delivery token emitido na tela de Alert intake e
  guardado onde a stack guarda seus segredos.
- **Ação**: em
  `/root/infra-cluster/services/monitoring/stack/alertmanager/alertmanager.yml`,
  adicionar um receiver novo ao lado do existente do antecessor, com o cabeçalho de
  autorização carregando o delivery token e `send_resolved` declarado
  explicitamente; e adicionar a rota que espelha o alerta para ele **sem remover** a
  rota existente, de modo que o antecessor continue recebendo.
- **Verificação**: validação de sintaxe da configuração antes de recarregar;
  recarga; e então, no próprio produto, a primeira entrega aparecendo na tela de
  Alert intake com origem, horário e resultado. "O Alertmanager recarregou" não é
  verificação suficiente — a verificação é o produto ter recebido.
- **Rollback**: cópia do arquivo tomada **antes** da edição; reverter é restaurar a
  cópia e recarregar. O receiver novo desaparece e o do antecessor permanece
  intocado. O comando de restauração é escrito no roteiro antes de a edição
  acontecer.

### Fase O-C — Runtime de investigação no CT254

- **Pré-condição**: a fábrica de runtime existe no produto, com testes verdes; um
  release contendo-a foi publicado pelo mecanismo de release-symlink que o
  deployment já usa; provider verificado (dependência 010).
- **Ação**: publicar o release, apontar a configuração do serviço para a fábrica de
  primeira parte e reiniciar o serviço pelo supervisor que o deployment já usa.
- **Verificação**: **pelo produto**. O passo de runtime do setup fica concluído, e
  uma investigação iniciada a partir de um incidente real começa em vez de recusar.
  "O processo subiu" não é verificação: um processo sem runtime sobe exatamente
  igual, e foi isso que matou os dois incidentes que estão no dashboard.
- **Rollback**: apontar o symlink de release de volta para o release anterior e
  remover a configuração do runtime; reiniciar. O deployment volta ao comportamento
  de "sem runtime" — degradado, mas íntegro, com todas as demais telas funcionando.

### Fase O-D — Cenário T2 na janela combinada

- **Pré-condição**: T1 verde; O-C verificada; operador ciente e janela combinada;
  vítima escolhida entre `streamlink-webui` (CT139) e `bazarr` (CT103).
- **Ação**: parar o contêiner escolhido; aguardar o alerta disparar por conta
  própria; observar a investigação correlacionar métricas do Prometheus com o estado
  do contêiner no Proxmox.
- **Verificação**: incidente em `/incidents` com timeline completa, diagnóstico
  nomeando que o contêiner está parado, e ação proposta aguardando decisão. Nada
  executado sem decisão.
- **Rollback**: religar o contêiner. É manual, imediato e independente do produto —
  se a ação proposta for aprovada, o efeito é o mesmo religar; se for rejeitada, ou
  se a investigação travar, o operador religa à mão sem esperar por nada.
- **Limite**: uma vítima por vez, uma janela por vez. Nenhum segundo contêiner é
  derrubado para "testar de novo" sem nova combinação.

## Complexity Tracking

Sem violações da constituição a justificar. Tabela intencionalmente vazia.
