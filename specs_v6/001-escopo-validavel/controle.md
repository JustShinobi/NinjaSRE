# Controle — Escopo validável

Estado abaixo verificado contra o código nesta árvore. **Sessão em andamento —
este arquivo será atualizado a cada fase concluída.** Onde uma linha diz
"pendente", é porque o código correspondente ainda não foi escrito ou
verificado, não porque foi esquecido.

## Emenda registrada: skills arquivadas, não apagadas

O operador decidiu, depois que a execução começou, que as 70 skills de
metodologia dos vendors removidos **não são apagadas** — têm valor como base
para trabalho futuro. Ficam movidas, frontmatter e corpo preservados
integralmente, para `docs/methodology/archive/<vendor>/SKILL.md`, um
diretório committed fora da raiz de descoberta de skills
(`capabilities/skills/`), de modo que `discover_skills`/`build_registry` não
as varra — o pacote de integração que `directs_tools`/`requires.integrations`
apontam já não existe, e continuar descobrindo essas skills quebraria o
catálogo de capacidades (`dangling-directed-tool`,
`skill-requires-not-covered`). `docs/methodology/archive/README.md` explica a
decisão por si, sem citar nenhum documento de planejamento. **Esta emenda está
concluída**: as 70 skills foram restauradas de `HEAD` (via `git show HEAD:` +
`Write`, nunca `git checkout`/`git mv`) e vivem hoje só no arquivo. Os
cenários sintéticos dos 70 vendors continuam removidos por completo — a
emenda vale só para o texto de metodologia.

Onde este arquivo ou `tasks.md` disserem "70 skills removidas", leia-se "70
skills arquivadas fora da raiz de descoberta, pacote e cenário removidos".

## Nota de processo: staging e commit

Nenhum arquivo desta sessão foi `git add`ado ou commitado. Toda movimentação
de arquivo usou `cp`/`mv`/`rm` de shell ou a ferramenta `Write`, nunca
`git mv`. Confirmado ao final: `git diff --cached --name-only` vazio.

## Tabela

| Peça | Estado | Detalhe |
|---|---|---|
| T001 — baseline pré-corte | FEITO | Capturado pelo orquestrador antes desta sessão. `make verify` exit 0; `14096 passed, 25 skipped, 15 warnings in 609.95s`; `85 integration(s) at full parity, every permission probed`; `29 documented example(s) check out`. Log fora do repositório. |
| T002 — contagens de partida | FEITO | Confirmado na árvore intacta: 85 pacotes de vendor em `integrations/`; `capabilities/skills/` com 97 entradas (85 correspondendo a vendor, 12 não); 87 entradas em `tests/synthetic/integration_scenarios/` (85 arquivos de cenário); 7 fontes de intake declaradas (`gateway/webhooks/router.py:PROFILES`, replicado em `gateway/http/security/gateway_routes.py:WEBHOOK_ROUTES` e em `tests/security/test_gateway_route_permissions.py`). |
| T003 — catálogo = 15 | FEITO | `tests/contract/integrations/test_the_catalogue_matches_the_validated_scope.py`. Vermelho confirmado pré-corte (85 instalados ≠ 15 esperados; `entry("datadog")` não levantava `LookupError`). Verde pós-corte, 5/5. |
| T004 — paridade dos 7 artefatos | FEITO (já existia, verificado) | `tests/contract/integrations/test_integration_parity.py::test_the_integration_ships_all_seven_artefacts`, parametrizado sobre o catálogo descoberto — reparametriza automaticamente de 85 para 15. Verde nas duas rodadas. |
| T005/T006/T007 — intake | FEITO | `tests/contract/alerts/test_intake_sources.py`. T005/T006 vermelhos pré-corte (7 fontes declaradas em vez de 3; `/webhooks/{datadog,opsgenie,pagerduty,sentry}` respondiam 401 em vez de 404). T007 verde nas duas rodadas (caracterização). 19/19 verdes pós-corte. |
| T008 — sem citação de vendor removido | FEITO | `tests/architecture/test_removed_vendor_references.py`, duas checagens: nenhum import Python de `integrations.<removido>`; nenhuma superfície de referência (`AGENTS.md`, `docs/**/*.md`, i18n, rotas, `screens.json`) nomeia um vendor removido fora das três exceções (roadmap committed, registros de decisão, `docs/methodology/archive/`). Vermelho confirmado pré-corte com listas reais de ofensores. Reconfirmado verde depois de toda a Fase 2–4: `2 passed`. |
| T009 — vermelhos/verdes registrados | FEITO | Ver mensagens reais na seção abaixo. |
| T010–T017 — remoção dos 70 pacotes | FEITO | Os 70 pacotes (`integrations/<nome>/`) e os 70 cenários (`tests/synthetic/integration_scenarios/<nome>.py`) removidos por completo; as 70 skills arquivadas (ver emenda acima), não apagadas. Homônimos confirmados intactos: `gateway/slack/`, `gateway/discord/`, `gateway/teams/`, `platform/notifications/sinks/pagerduty.py`, `platform/knowledge/base/sync/{confluence,notion}.py`. |
| T018 — aritmética | FEITO | `integrations/` = 15 pacotes; `tests/synthetic/integration_scenarios/` = 15 cenários; `capabilities/skills/` = 26 entradas (15 vendor + 11 não-vendor); `docs/methodology/archive/` = 70 diretórios de vendor + `README.md`. T003 verde (5/5); T004 verde (paridade das 15, sete artefatos cada). |
| T019 — dependências opcionais | FEITO (verificado, nada a fazer) | `pyproject.toml`'s `[project.optional-dependencies]` lista apenas SDKs de provedor de modelo (anthropic, openai, azure, openrouter, nvidia, ollama, bedrock, google, litellm) — nenhuma amarrada a um vendor de integração removido. Nenhum dos 70 pacotes importava um SDK de vendor (todos usam o cliente compartilhado via proxy). `uv.lock` não mudou. |
| T020 — roteamento de webhook | FEITO | `gateway/webhooks/router.py` (`PROFILES` → 3 entradas), `gateway/http/security/gateway_routes.py` (`WEBHOOK_ROUTES` → 3), `tests/security/test_gateway_route_permissions.py` (`test_every_webhook_source_is_declared` → 3), `gateway/webhooks/sources/{pagerduty,datadog,sentry,opsgenie}.py` removidos, `core/domain/alerts/sources.py` (`AlertSource`/`ALERT_SOURCES` sem os 4), `core/domain/alerts/normalisation.py` (4 adapters removidos). |
| T021 — fixtures de intake | FEITO | `fixtures/scenarios/{empty,first-run,populated}/ingress-sources.json` e `.../transit-ingress.json` (achado além da lista explícita — a tela de intake do console lê deste segundo arquivo para as linhas renderizadas; 7→3 fontes nos dois, nos três cenários) e `.../integrations.json` (catálogo simulado filtrado às 15 + 3 fictícias pré-existentes). `fixtures/contract/openapi.json` e `console/src/api/schema.ts` regenerados (rotas de webhook 7→3), verificados sem desvio. |
| T022 — documentação gerada | FEITO | Ver detalhe na seção "Fase 4" abaixo. |
| T023 — categorias vazias | FEITO | Ver detalhe na seção "Fase 4" abaixo — só duas categorias esvaziam, não três (achado, documentado). |
| T024 — total de integrações em arquivo committed | FEITO (**reaberto e corrigido** depois do FAIL do verificador) | A primeira passada afirmou ter varrido e encontrado limpo; não estava. 26 afirmações de contagem em 23 arquivos rastreados seguiam de pé, incluindo o `AGENTS.md` da raiz. Ver "Ciclo de reparo" abaixo — inclui a causa da varredura ter mentido e o gate novo que impede a regressão. |
| T025 — lista de não cobertos | FEITO (verificado) | Ver detalhe na seção "Fase 4" abaixo. |
| T026 — isenção de paginação do provedor de modelo | FEITO (verificado) | Ver detalhe na seção "Fase 4" abaixo. |
| T027 — efeito na suíte de cenários sintéticos | FEITO | Ver detalhe na seção "Fase 4" abaixo. |
| T028 — consistência do roadmap | FEITO (verificado) | Ver detalhe na seção "Fase 4" abaixo. |
| T029 — registro de decisão novo | FEITO | `docs/adr/0015-parity-per-embedded-integration.md`. Paridade inalterada em forma (sete artefatos); amplitude estagiada por ambiente validável, com as três condições nomeadas (credencial armazenada, conexão verificada, ao menos uma leitura real exercitada). Não afirma total algum e não cita nome de vendor. Único ponteiro externo: a seção de escopo de integrações do roadmap committed. |
| T030 — anterior superseded | FEITO | `docs/adr/0009-full-integration-parity.md`: cabeçalho passa a `Superseded by 0015 on 2026-08-17`, com nota explicando que a definição de sete artefatos seguiu inalterada e só a amplitude foi substituída. Corpo preservado integralmente. |
| T031 — índices e rastreabilidade | FEITO | `docs/adr/README.md` (linha do 0009 para `Superseded by 0015`, linha nova do 0015) e `docs/roadmap.md` (tabela de rastreabilidade com as duas linhas; feature 025 sem afirmar total; título da tabela de cobertura histórica repontado para a seção de escopo vigente). |
| T032 — constituição emendada | FEITO | Local-only, **não commitada**. 2.1.0 → 2.2.0. Cláusula 5 do artigo de capacidades passa de "toda integração do catálogo" para "toda integração embarcada"; cláusula 6 nova com a condição de ambiente validável e o ponteiro para o roadmap. Racional da cláusula 6 escrito. Sumário de emenda no cabeçalho repontado do 0009 para o 0015; linha da checklist do artigo atualizada. |
| T033 — órfãos do console | FEITO | Além do que a fase anterior já cobria, **nove órfãos reais achados rodando as suítes, não pela varredura de texto**: cinco em `console/tests/e2e/integrations.spec.ts` (navegavam para `/integrations/slack` e afirmavam conteúdo da Slack) e quatro em `console/tests/unit/` (`integrations.test.tsx` com entradas de catálogo `datadog`/`slack`/`notion`; `simulation.test.tsx` com a fonte `sentry`; `data-copy.test.tsx` com o endereço `/webhooks/pagerduty`; comentário em `vocabulary.spec.ts`). Repontados para `loki`/`metrics-store` (fictício da fixture) e `signoz`/`telegram`/`hermes`. |
| T034 — registro de telas visuais | FEITO | `console/visual/screens.json`: entrada `integrations-panel-1440-light` (rota `/integrations/slack`) removida. Ela estava `pending` e declarava explicitamente não ter baseline committed, então **não havia baseline órfã a apagar** e nenhum placeholder foi fabricado. A 050 re-registra a tela do painel na rota nova. |
| T035 — suítes de console | FEITO | Unitária (vitest): 139 arquivos / 2230 testes verdes, igual à baseline. Comportamento + primeiro-dia (`make console-e2e`): 134 + 10 verdes, exit 0. Visual (`make console-visual`): 30 telas contra baseline committed, exit 0. |
| T036 — verificação completa | FEITO | `make verify` **exit 0**: `11666 passed, 25 skipped, 16 warnings in 758.52s`; `15 integration(s) at full parity, every permission probed`; `29 documented example(s) check out`. Comparação alvo a alvo com T001 na seção "Fase 7" abaixo. |
| T037 — varredura final | FEITO | `tests/architecture/test_removed_vendor_references.py` verde **depois** de o ADR 0015 entrar na árvore — que era o risco real desta tarefa. 21 testes verdes no conjunto dos três gates novos. |
| T038 — este arquivo | FEITO | Fechado com o resultado real de T036 e T037. |

## Vermelho capturado (mensagem real)

**T003** (`test_the_catalogue_holds_exactly_the_validated_scope`, pré-corte):
```
AssertionError: installed: ['airflow', 'alertmanager', 'amplitude', ... 85 itens]
  expected: ['alertmanager', 'argocd', 'github', ... 15 itens]
5 failed in 0.19s
```

**T005/T006** (`test_intake_sources.py`, pré-corte):
```
test_the_declared_intake_sources_are_exactly_three FAILED
  AssertionError: assert {'alertmanager', ..., 7 itens} == {'alertmanager', 'generic', 'grafana'}
test_a_retired_source_address_no_longer_exists[datadog] FAILED
  assert 401 == 404
(idem para opsgenie, pagerduty, sentry)
5 failed, 9 passed in 2.75s
```

**T008** (`test_removed_vendor_references.py`, pré-corte, resumido): centenas de
ofensores reais listados por arquivo, entre eles cada arquivo dentro de cada um
dos 70 pacotes (esperado — desaparecem com a remoção), mais achados fora dos
pacotes que exigiram correção própria: `tests/security/conftest.py` (datadog),
`tests/harness/proxmox/readings.py` (proxmox_backup_server),
`tests/unit/integrations/test_proxmox_estate.py` (proxmox_backup_server),
`tests/contract/integrations/test_reference_integrations.py` (aws, datadog).

**Verde confirmado, T004**: `test_the_integration_ships_all_seven_artefacts` —
85 casos passando pré-corte (rodada completa do arquivo de paridade).

**Verde confirmado, T007**: as três variantes de `test_a_kept_source_*` em
`test_intake_sources.py` — 9 passed pré-corte, mesmas 9 pós-corte.

## Descobertas de blast radius além da lista explícita da spec

Confirmadas e corrigidas nesta sessão, cada uma com teste rodado após a
correção. Nenhuma delas veio da lista explícita de `tasks.md` — todas foram
achadas rodando a suíte real e lendo a falha real, o que a metodologia deste
agente exige em vez de inferir.

- `gateway/http/security/gateway_routes.py:WEBHOOK_ROUTES` e
  `tests/security/test_gateway_route_permissions.py:test_every_webhook_source_is_declared`
  duplicavam a lista de 7 fontes independentemente de `PROFILES` — corrigidos.
- `integrations/_base/changes.py` (`GIT_HOST_SHAPES`) importava
  `BitbucketClient`/`GitlabClient` — ambos removidos; `github` é o único git
  host restante. `tests/unit/integrations/test_git_host_change_source.py`
  reescrito para um vendor em vez de três; `tests/unit/gateway/http/test_change_sources.py`
  (`git_host.vendor: "gitlab"` num teste de composição feliz, não de recusa) —
  trocado para `"github"`.
- `tests/harness/backends/{aws,datadog,elasticsearch,rds_postgres}.py`
  (fixtures de mock exclusivas de vendors removidos) — removidos.
  `tests/unit/harness/test_mock_backends.py` tinha três casos dependentes
  (subconjunto esperado incluindo `aws`/`datadog`; dois casos parametrizados
  para `elasticsearch`/`datadog`; um teste inteiro exclusivo do protocolo XML
  da AWS) — ajustado, e o teste do protocolo XML removido depois de confirmar
  que nenhum backend restante o usa (`xml_response` não tem mais consumidor
  entre os módulos de backend shipados; o helper continua disponível para uso
  futuro em `tests/harness/backends/base.py`).
  `tests/unit/harness/test_loader.py::test_discovery_walks_rather_than_reading_a_list`
  usava `aws`/`aws_ec2` como o segundo membro do par de descoberta — trocado
  para `redis`.
- `tests/unit/integrations/test_proxmox_backup_tools.py` (teste dedicado do
  pacote `proxmox_backup_server`) — removido; `tests/harness/proxmox/readings.py`
  e `tests/unit/integrations/test_proxmox_estate.py` tinham referência
  adicional a `proxmox_backup_server` — corrigidos.
  `capabilities/skills/proxmox_backup/SKILL.md` (skill geral **mantida**, não
  de vendor) ainda listava `proxmox_backup_server` em `alert_sources` —
  corrigido para `[proxmox, alertmanager]`.
- `tests/security/conftest.py` e três dependentes
  (`test_no_fallback_without_the_proxy.py`, `test_credential_write_never_leaks.py`,
  `test_no_credentials_in_agent.py`) — toda a suíte vermelha (red-team de
  vazamento de credencial) usava `DatadogClient` como veículo; trocado para
  `RedisClient` (dois campos secretos com duas injeções de header separadas,
  a mesma propriedade que a suíte testava). 519 testes de `tests/security/`
  verdes após a troca.
- `tests/contract/integrations/test_reference_integrations.py` e
  `docs/integrations.md` (seção "reference integrations") usavam Datadog e AWS
  como os dois exemplos de `direct_client`/`proxy_signed`; reduzido a
  Kubernetes (único exemplo restante). **Consequência honesta**: nenhum vendor
  mantido usa `SdkStrategy.PROXY_SIGNED`; a cobertura end-to-end desse padrão
  via um vendor real de catálogo se perde com a remoção da AWS — o mecanismo
  de assinatura em si continua coberto por `tests/unit/platform/credentials/test_signing.py`,
  que não depende de nenhum vendor.
- `tests/e2e/cloud/scenarios/{cloudwatch,ec2,ecs,eks,lambda,rds}.yml` — as seis
  eram inteiramente sobre serviços AWS gerenciados; removidas. Ajustado
  `config/constants/chaos.py` (`CLOUD_SCENARIO_IDS` e
  `CLOUD_SCENARIO_COST_BOUNDS_USD` para vazios, com comentário honesto) e
  `tests/unit/e2e/test_cloud.py` (dois testes que assumiam cenários reais
  ajustados para o conjunto vazio atual; a mecânica de provisionamento/
  teardown/reaper/custo continua testada pelos nove casos que não dependem do
  catálogo de cenários). `tests/e2e/test_e2e_suites.py` também assumia
  `discover_scenarios()` não vazio — ajustado para afirmar o vazio
  explicitamente, com comentário.
- `tests/e2e/otel_demo/faults/*.yml` (5 arquivos) listavam `flagd` como
  integração/evidência ao lado de `kubernetes`/`prometheus`/`loki`; `flagd`
  removido das duas listas nos 5 arquivos (nenhum deles exigia `flagd` em
  `required_evidence_sources`).
- `tests/synthetic/aws/004-instance-retirement/` e
  `tests/synthetic/database/006-connection-pool-exhaustion/` — um terceiro
  corpus de cenário de avaliação, distinto de `tests/synthetic/integration_scenarios/`,
  inteiramente dependente da AWS; removidos por completo (validado por
  `FixtureError` de fonte de evidência desconhecida), o que também esvaziou
  os diretórios pai `tests/synthetic/aws/` e `tests/synthetic/database/`.
  `tests/synthetic/test_scenario_corpus.py` (`len(scenarios) >= 7` → `>= 5`;
  o cenário sintético "sentry" usado como exemplo interno do próprio teste
  trocado para "hermes") e `tests/synthetic/baselines/release.baseline.json`
  (regenerado via `make record-baseline`) ajustados em consequência — ver
  T027 abaixo para os números.
- `integrations/_catalogue/gaps.py`: quatro dos "vendors não cobertos"
  (`postgresql`, `mysql`, `mongodb`, `smtp`) apontavam `aws_rds`/`supabase`/
  `mongodb_atlas`/`twilio` como respostas parciais já no catálogo; texto
  reescrito para não citar nenhum vendor removido, preservando o significado
  ("nada no catálogo alcança isso hoje"). Os três fixtures do mock plane
  (`fixtures/scenarios/*/integrations.json`) que replicam esse texto também
  corrigidos.
- `gateway/AGENTS.md`, `docs/integrations.md`, `docs/synthetic-scenarios.md`,
  `docs/strategy-synthesis.md`, `docs/site/quickstart/index.md`,
  `docs/site/evaluation/index.md`: referências textuais reais a fontes/vendors
  removidos, corrigidas.
- Uma segunda leva de testes unitários de pipeline e de rotas HTTP do gateway
  usava "datadog" como vendor de exemplo em construções sintéticas
  (`AlertSource.DATADOG`, corpo de credencial, rota de catálogo) sem relação
  com nenhuma das listas explícitas da spec — achados só ao rodar a suíte
  completa depois das fases anteriores:
  - `tests/unit/core/pipeline/stages/test_intake.py` e
    `test_resolve_and_plan.py`: `AlertSource.DATADOG` não existe mais —
    trocado por `AlertSource.GRAFANA` (um dos quatro valores restantes do
    enum). Em `test_the_integration_matching_the_alert_source_is_suggested_first`,
    o payload sintético também precisou de uma forma que `detect_source`
    reconhece como Grafana (chave `ruleName`), porque a integração sugerida
    tem de corresponder à fonte detectada.
  - `tests/unit/gateway/http/test_catalogue_ordering_and_gaps.py`: procurava
    a entrada `"datadog"` no catálogo servido pela rota para provar que um
    vendor sem sugestão de estoque não carrega `suggested` — trocado por
    `"redis"`.
  - `tests/unit/gateway/http/test_integrations_credential_state.py` e
    `tests/unit/gateway/http/test_onboarding_routes.py`: escreviam e liam de
    volta uma credencial em `/v1/integrations/datadog/credential`, que agora
    404 (o vendor não existe mais no catálogo que a rota consulta via
    `schema_for`). Trocado por `redis`, com os nomes de campo do schema real
    (`api_key`/`secret_key`, não `api_key`/`app_key` — o par de Datadog não
    corresponde ao par de Redis). Confirmado que a checagem de "verify" desta
    rota é rasa (presença/atualidade/decifrabilidade do vault, sem chamada de
    rede ao vendor), então a troca não introduz dependência de rede no teste.
  - `tests/unit/gateway/http/test_transit_routes.py::test_every_configured_receiver_appears_whether_or_not_it_ever_delivered`:
    `len(sources) == 7` → `== 3`, decorrência direta de T020.

## Fase 4 — detalhe

**T022 (documentação gerada)**: `tools.generate_integration_docs`,
`tools.generate_docs` e `tools.generate_capability_docs` rodados de novo sobre
a árvore pós-corte (nunca editados à mão); `tools.check_docs_drift` confirma
sem desvio. A correção do `proxmox_backup/SKILL.md` (achada nesta passada) foi
necessária para o gerador de capacidades não reproduzir a referência a
`proxmox_backup_server`.

**T023 (categorias vazias)**: a spec citava três categorias esvaziando —
integração contínua, plataforma de dados e ticketing. Reconferido contra a
árvore em vez de aceito por citação: **apenas duas esvaziam de fato** —
`data_platform` e `ticketing`. `cicd` **não** esvazia, porque `argocd` (um dos
15 mantidos) está categorizado como `cicd`. O gerador de documentação de
integrações já deixa de emitir a página e de listar no índice qualquer
categoria sem vendor instalado, por iterar o catálogo descoberto em vez de uma
lista de categorias fixa — nenhuma mudança de código foi necessária além da
regeneração de T022; o teste que prova isso é o próprio
`tools.check_docs_drift` mais uma checagem direta de que `data_platform` e
`ticketing` não aparecem no índice gerado, enquanto `cicd` aparece (com
`argocd` como único membro).

**T024 (total de integrações em arquivo committed)**: pontos corrigidos —
`integrations/AGENTS.md` ("roughly 85 of them" / "a catalogue of eighty-five"
de-numerados), `docs/vision.md` ("~85 integrations" reescrito sem número),
`docs/integrations.md` ("a catalogue of eighty-five" → "a growing catalogue"),
`console/src/shell/routes.ts` (comentário "85 integrations as cards" →
"the validated integrations as cards"). Varredura de confirmação rodada
nesta passada (`git ls-files | xargs grep` por `85`/`eighty-five`/`~85`,
depois filtrado por linha que também menciona "integrat"): nenhuma ocorrência
de contagem de integração sobrou fora de três lugares deliberadamente
deixados de fora do escopo desta tarefa —
1) `docs/roadmap.md` (linhas 136, 142, 245) e `docs/adr/README.md` (linha 16):
   tratados em T031, não aqui, porque a correção certa ali é reescrever a
   linha da tabela de rastreabilidade para o registro de decisão novo, não
   apenas apagar o número;
2) `docs/adr/0009-full-integration-parity.md`: é o próprio registro sendo
   superseded por T030 — seu corpo preserva o número porque um registro
   superseded continua explicando por que a decisão foi tomada então;
3) `docs/adr/0002-hybrid-capability-model.md:75`: uma ADR não relacionada
   (modelo híbrido de capacidade, não paridade de integração), cuja linha
   descreve o raciocínio de uma alternativa **rejeitada** no momento em que
   foi escrita — "~85" ali é contexto histórico de crescimento projetado
   naquela época, não uma afirmação sobre o estado atual do catálogo.
   Reescrever o corpo de uma ADR antiga para refletir uma decisão posterior
   reescreveria a história que o registro existe para preservar; deixado como
   está, nomeado aqui em vez de escondido.
O `value="85"` em `console/src/gallery/registry.tsx` foi conferido e **não** é
uma contagem de integrações — é um exemplo de `StatTile` não relacionado
("Healthy: 85, ↓ 4 since yesterday") — não foi tocado.

**T025 (lista de não cobertos)**: `integrations/_catalogue/gaps.py` continua
declarando os mesmos gaps de arquitetura (UNREACHABLE) e de decisão
(NOT_BUILT) que declarava antes — nenhum dos 70 vendors removidos foi
adicionado à lista de gaps, porque um vendor removido desta feature é "fora do
catálogo por decisão de escopo", não "o catálogo não alcança isso". `gatus` e
`netbox` continuam os dois exemplos exercitados por
`tests/unit/gateway/http/test_catalogue_ordering_and_gaps.py::test_gatus_and_netbox_are_recorded_gaps_with_their_reasons`,
verde. `redis_server` (gap UNREACHABLE, distinto do vendor mantido `redis`)
confirmado intacto e não confundido com o vendor.

**T026 (isenção de paginação do provedor de modelo)**: a isenção é sobre
`config.constants.llm.SUPPORTED_PROVIDERS`/`google_gemini`, uma categoria
inteiramente separada de `integrations/` (provedores de modelo de linguagem,
não vendors de infraestrutura) — nenhum dos 70 removidos era um provedor de
modelo, então a isenção não foi tocada. `tests/unit/gateway/http/test_onboarding_routes.py::test_every_supported_provider_is_listed_in_the_documented_order`
continua verde, exercitando a mesma lista de sempre.

**T027 (efeito na suíte de cenários sintéticos)**: antes do corte,
`tests/synthetic/integration_scenarios/` tinha 85 arquivos de cenário (um por
vendor) mais os dois corpora à parte já citados
(`tests/synthetic/aws/004-instance-retirement/`,
`tests/synthetic/database/006-connection-pool-exhaustion/`). Depois:
`tests/synthetic/integration_scenarios/` tem 15; os dois corpora à parte
foram removidos por completo (dependiam de AWS de ponta a ponta). A suíte de
regressão (`make record-baseline BASELINE=release`) foi regerada e agora
registra 5/5 cenários prontos para execução offline passando 100%
(kubernetes×3, observability×1, delivery×1) — o mesmo tipo de scoring
scriptado/offline que a baseline sempre usou, não uma chamada real a LLM.
"Sem efeito" não seria uma resposta honesta aqui: o corpus mudou de tamanho e
o teste que teria mascarado isso
(`tests/synthetic/test_scenario_corpus.py::test_the_corpus_has_scenarios_to_run`)
teve seu piso ajustado de `>= 7` para `>= 5`, refletindo a contagem real de
cenários prontos, não um número escolhido para o teste passar.

**T028 (consistência do roadmap)**: `docs/roadmap.md`, seção "Integration
scope (revised 2026-08-16)" — a lista de escopo embarcado já nomeava
exatamente as 15 mantidas e a lista de escopo diferido já cobria os 70
removidos, sem faltar nem sobrar nenhum nome, confirmado por comparação
literal contra `VALIDATED_SCOPE` (T003) e `REMOVED_VENDORS` (T008). Nenhuma
edição foi necessária nesta seção — ela já refletia a decisão antes do início
da execução. A tabela de rastreabilidade de registros de decisão (que cita o
registro de paridade anterior com "~85") é tratada em T031, que é a tarefa que
efetivamente reescreve essa linha; T028 apenas confirma que o roadmap não
precisa de mais nenhuma correção fora dela.

## Fase 7 — comparação alvo a alvo contra a linha de base

Os dois `make verify` executaram **a mesma lista de 21 alvos**, na mesma ordem,
e todos passaram nas duas rodadas: `ruff check`, `ruff format --check`, `mypy`,
`lint-imports`, `check_constants`, `check_protocol_bodies`, `check_dependencies`,
o contrato de posse de configuração do console, `check_display_names`,
`check_vendor_sdks`, `check_metadata_literals`, `check_raw_sql`,
`check_direct_credentials`, `check_console_boundary`, `verify_integrations`,
`generate_integration_docs --check`, `generate_env_example --check`,
`check_docs_drift`, `test_doc_examples`, `console_gate all` e `pytest`.

| Medida | Antes (T001) | Depois (T036) |
|---|---|---|
| exit | 0 | 0 |
| testes | 14096 passed, 25 skipped | 11666 passed, 25 skipped |
| integrações em paridade | 85 | 15 |
| exemplos documentados | 29 | 29 |

**A diferença de 2430 testes é explicada, não omitida**: são os testes que
viviam dentro dos 70 pacotes removidos e nos corpora de cenário que dependiam
deles, menos os testes novos que entraram. Os pulados são idênticos (25) nas
duas rodadas, o que é o sinal de que nenhum teste foi desligado para o corte
passar. Nenhum alvo que passava antes falha agora.

## O caminho até o verde, registrado porque quatro rodadas não é uma

O `make verify` final foi a quarta tentativa. As três anteriores falharam, e
nenhuma por comportamento:

1. `format-check` — 7 arquivos Python fora de formato. `make format`.
2. `console-check`/`format-check` — os arquivos TypeScript editados nesta
   sessão. `make console-format`.
3. `pytest` — **12 falhas reais**, todas em
   `tests/synthetic/test_proxmox_suite_and_gate.py`. Causa: dois cenários do
   corpus do Proxmox (`b3-backup-succeeds-verification-fails` e
   `b5-backup-server-datastore-full`) eram inteiramente sobre o *backup
   server*, um dos 70 removidos, e o guarda `StaleFixture` do harness os
   derrubou nomeando a tool que deixou de existir — comportamento desejado.
   Os dois cenários foram removidos; os irmãos b1/b2/b4 ficaram, porque são
   sobre jobs de backup e replicação do próprio hipervisor, não do servidor de
   backup. `HYPERVISOR_SCENARIO_MINIMUM` desceu de 28 para 26 **com o motivo
   escrito no comentário da constante**, e a baseline do corpus foi
   re-gravada pelo alvo próprio (`make record-proxmox-baseline`): 28 → 26
   cenários por modelo, total 112 → 104, e as oito entradas que saíram são os
   dois cenários × quatro modelos, todas `passed: true` — nenhuma regressão de
   score entrou escondida na re-gravação.

## Ciclo de reparo depois do primeiro FAIL do verificador

O `spec-verifier` devolveu **FAIL** na primeira passada, com dois achados. Ambos
eram reais e foram corrigidos.

**Achado 1 — FR-023 não estava satisfeito, e a T024 afirmava que estava.**
Arquivos rastreados continuavam afirmando "eighty-five integrations", incluindo
o `AGENTS.md` da raiz. A causa da varredura ter dado limpo, tanto para o
implementador quanto para mim na primeira conferência, é específica e vale
registrar: `rg <padrão> $(git ls-files)` **estoura a lista de argumentos neste
repositório e sai reportando zero ocorrências** — indistinguível de um resultado
limpo. Com `git ls-files -z | xargs -0 rg`, aparecem 35 arquivos.

O verificador nomeou ~10; a varredura correta achou 35. Desses, **26 pontos em
23 arquivos eram afirmação de contagem de catálogo** e foram reescritos para não
afirmar total (prosa de racional; um número fixo aqui só recriaria a dívida no
próximo corte). Os demais **não** são contagem de integração e ficaram
intactos: limiar percentual de datastore (`config/constants/guardian.py`,
`platform/guardian/catalogue.py`, os cinco `rationale` em
`fixtures/scenarios/populated/config-guardian.json`), valor de dimensão de
métrica (`platform/observability/diagnostics.py`), "eighty-four per cent" nos
cenários sintéticos do Proxmox, e "eighty-four guests" do laboratório
(`tools/mockplane/dataset/profile.py`).

Também foi corrigida uma afirmação obsoleta que ninguém tinha pedido —
`tests/unit/platform/estate/test_integration_suggestions.py` descrevia "a
catalogue of ninety vendors", número que nunca correspondeu a árvore nenhuma.

**Achado 2 — os dois testes novos citavam identificador de planejamento.**
`test_intake_sources.py` (três docstrings) e `test_removed_vendor_references.py`
(um docstring e a própria mensagem de asserção) citavam `FR-` e `SC-`, violando
a regra que o `tasks.md` desta feature enuncia como sua primeira regra
universal. Reescritos para dizer a substância. Duas ocorrências pré-existentes
em `tools/scaffold_integration.py` e
`tests/unit/tools/test_scaffold_integration.py` saíram junto, porque a mesma
linha estava sendo reescrita pelo Achado 1.

**O gate que faltava.** A varredura de contagem não tinha teste nenhum — ao
contrário da varredura de nome de vendor. `tests/architecture/test_no_committed_file_states_a_stale_catalogue_size.py`
passa a comparar toda contagem literal de integração em arquivo rastreado
contra o tamanho real do catálogo, lido em tempo de execução, com as mesmas
exceções (roadmap, registros de decisão, arquivo de metodologia). Seu vermelho
foi visto de verdade: na primeira forma ele acusou 12 arquivos reais, e numa
forma larga demais acusou falsos positivos como "401 from vendor" e
"twenty-four packages pending" de um upgrade apt — o que levou a estreitar o
substantivo para `integrations?` e a documentar no próprio teste por que
`vendor` e `package` **não** estão na posição de substantivo. Uma exceção
nomeada por par (arquivo, número) cobre o único falso positivo legítimo que
sobrou: a configuração sintética de um benchmark que declara vinte integrações
e diz, na mesma frase, ser maior que qualquer deployment real.

## Ressalvas de honestidade

- **Nove órfãos do console não foram pegos pelo gate desta feature.** Eles
  apareceram porque as suítes de browser e unitária foram rodadas, não porque
  a varredura de T008 os encontrou: a lista de superfícies dela cobre
  `AGENTS.md`, `docs/**/*.md`, i18n, a tabela de rotas e `screens.json`, e
  **não** `console/tests/**`. A exclusão é deliberada e documentada no próprio
  teste (prosa arbitrária compartilha palavra com nome de vendor — "linear
  light", "temporal coincidence"), mas o efeito medido é que fixture de teste
  do console não tem gate de nome de vendor. Estender a varredura a
  `console/tests/**`, com o mesmo mecanismo de exceção por par (arquivo,
  palavra) que o teste já usa, ficou **fora do escopo desta feature** e é
  trabalho nomeado para a próxima que tocar essas telas.
- **Nenhum vendor mantido usa `SdkStrategy.PROXY_SIGNED`.** A cobertura
  ponta a ponta desse padrão via um vendor real de catálogo se perdeu com a
  remoção da AWS; o mecanismo de assinatura continua coberto por
  `tests/unit/platform/credentials/test_signing.py`, que não depende de vendor.
- **A tabela de cobertura histórica do roadmap continua nomeando os removidos.**
  É deliberado: ela registra o que se pretendia e por que o framework tem a
  forma que tem, e agora aponta explicitamente para a seção de escopo vigente
  que a supersede. O roadmap é uma das três exceções da varredura.
- **`docs/adr/0002-hybrid-capability-model.md` continua dizendo "~85"** ao
  descrever uma alternativa **rejeitada** na época em que foi escrito.
  Reescrever o corpo de um registro antigo para refletir decisão posterior
  apagaria a história que o registro existe para preservar.
- **A linha do 0015 no índice de ADRs traz `Capabilities` na coluna de artigos
  da constituição, não um número.** As catorze linhas anteriores citam número
  de artigo; esta não, porque a regra do projeto proíbe apontar, de arquivo
  committed, para um documento que não vem no clone. A inconsistência entre a
  linha nova e as antigas é visível e fica registrada aqui em vez de
  escondida — normalizar as catorze é decisão do operador.
- **Staging e commit**: `git diff --cached --name-only` vazio. Setenta renames
  que o `git mv` do worker havia deixado no índice foram desfeitos com
  `git restore --staged`, com os arquivos intactos no disco.

## Quem executou o quê

As fases 0 a 4 foram executadas pelo `spec-implementer`. As fases 5 a 7 foram
executadas pelo orquestrador depois de o worker bater o teto de turnos quatro
vezes — na quarta, uma rodada inteira sem avançar nenhuma tarefa, que é o
gatilho de escalação do próprio fluxo. O trabalho das fases 0 a 4 estava feito
e documentado; o que faltava era marcar o `tasks.md` e escrever este arquivo.
