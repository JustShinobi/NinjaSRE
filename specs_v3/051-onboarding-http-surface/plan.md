# Plano — 051 A superfície HTTP de onboarding

## Onde a lacuna realmente está, símbolo por símbolo

O fluxo (`surfaces/cli/wizard/flow.py::OnboardingFlow`) é agnóstico a transporte:
ele detém um `PlatformClient` (o protocolo em `surfaces/cli/client.py:180`) e
nunca se ramifica em transporte. `LocalPlatformClient` responde tudo
delegando para `LocalServices` (`self.services.check_provider`,
`.store_credential`, `.credential_schema`, `.diagnostics`, ao redor de
`client.py:875–899`). `RemoteClient` recusa cinco métodos por construção
(`client.py:1466–1511`): `list_providers`, `verify_provider`,
`credential_fields`, `store_integration_credential`, `diagnose`. Confirmado
contra o gateway:

| Método do cliente | Gateway hoje | Trabalho |
|---|---|---|
| `store_integration_credential` | nenhuma rota em lugar algum sob `gateway/http/routes/` | **construir** `PUT /v1/integrations/{name}/credential` |
| `list_providers` / `verify_provider` | nenhuma rota; descritores vivem apenas em `surfaces/cli/wizard/providers/` | **construir** família `/v1/providers`, **mover** os dados descritores para baixo de um tier |
| `credential_fields` | `GET /v1/config/{node_id}/integration-schemas` existe (`gateway/http/routes/config.py:379`) | **conectar** o cliente a ela |
| `diagnose` | `/v1/setup/diagnostics`, `/self-check`, `/checklist`, `/support-bundle` existem (`gateway/http/routes/first_run.py`) | **conectar** o cliente a elas |

## Escopo A — `PUT /v1/integrations/{name}/credential`

Handler em `gateway/http/routes/integrations.py`, ao lado de `verify_integration`,
que já mostra a composição: `discover()` →
`CredentialSchemaRegistry.from_schemas(descriptor.schema)` →
`Vault(gateway=state.gateway, schemas=schemas)`. A escrita é
`Vault.store(scope, handle, values)` (`platform/credentials/vault.py:183`),
que já valida contra o schema da integração, versiona na reescrita
(rotação é re-armazenar — correspondendo ao "sem verbo de rotação separado"
da spec), e retorna metadados de `CredentialVersion`, nunca valores.
**Nenhuma nova superfície de cofre é necessária**; a rota é uma visão fina,
como todo handler em `first_run.py`.

Propriedades de segurança, e onde cada uma é aplicada:

- **Resposta** é o mesmo status estilo `IntegrationVerification` que a rota
  verify retorna (re-execute `CredentialHealth.report` depois de armazenar)
  — nunca um eco. O modelo de resposta não tem campo onde um valor pudesse
  sentar, mesmo argumento de forma que `SetupOutcome`
  (`surfaces/cli/wizard/integrations/__init__.py:28`).
- **Log/auditoria** carregam apenas *nomes* de campo. A CLI já define o padrão
  em `cli.integration_credential_stored` (`fields=sorted(values)`); o handler
  do gateway registra da mesma forma, e a entrada de auditoria registra ator,
  integração, nomes de campo, e sequência de versão.
- **Permissão** é `credential.write`, um novo membro de `Permission`, declarado
  na tabela de rota ao lado do handler (`RouteTable.extended_with`,
  `gateway/http/security/route_permissions.py:120`) — a tabela recusa uma rota
  não declarada na fiação, que é o item de aceitação 5 já aplicado pelo
  maquinário de `tests/security/test_route_permissions.py`. Concedido a
  `owner` no catálogo de papéis; deliberadamente não implicado por
  `config.write`.
- **A rota de config fica selada.** Um teste dirige `PUT /v1/config/{node_id}`
  com um campo que um schema de integração marca como secreto e afirma recusa.
  Se o serviço de config não recusa hoje, esta feature adiciona a verificação
  na validação de `platform/config_service` — isso está em escopo, porque a
  spec faz disso a garantia desta rota.
- **Varredura de guardrail em testes**: o teste de aceitação armazena um
  segredo sentinela pela rota, executa uma leitura em forma de investigação de
  auditoria + logs + corpos de resposta, e afirma que o sentinela não aparece
  em lugar algum. Mesma forma que as preocupações de `make check-credentials`,
  mas comportamental.

## Escopo B — a superfície de provider

Três rotas em um novo `gateway/http/routes/providers.py`:

- `GET /v1/providers` — os nove descritores mais estado por deployment
  (configurado? verificado? qual modelo?), a mesma fusão que
  `LocalServices.providers()` já calcula.
- `GET /v1/providers/{id}` — um, com `fields` (nomes/labels/secreto/obrigatório
  — nunca valores), `guidance`, `where_to_get_it`, `models`, `default_model`,
  `local`.
- `POST /v1/providers/{id}/verify` — uma verificação ponta a ponta real. Isto é
  `LocalServices.check_provider` alcançado por HTTP; faz chamadas ao vivo (a
  docstring `providers verify` da CLI diz que custa tokens), então é um POST,
  nunca tocado por GET algum ou pela auto-verificação (a docstring do módulo
  `first_run.py` já registra essa decisão — este plano a mantém).

**O movimento que torna isto possível sem violação de tier**: o gateway
(tier 1) pode importar de qualquer lugar abaixo, mas os descritores vivem
atualmente em outro pacote tier-1 (`surfaces/`), e pacotes tier-1 não devem
importar um ao outro. Então `ProviderOnboarding`, os nove módulos descritores,
e o percurso `_discover`/`onboarding_for`/`all_onboardings` se movem de
`surfaces/cli/wizard/providers/` para **`core/llm/onboarding/`** — ao lado dos
adaptadores de provider que descrevem, tier 3, importável por ambos surfaces e
gateway. `CredentialFieldSpec` (atualmente `surfaces/cli/models`) se move com
ele (re-exportado por `surfaces/cli/models` para seus ~7 sites de chamada da
CLI, e por Artigo VIII.4 o encaminhamento é *não* mantido: call sites são
migrados e o caminho de módulo antigo deletado na mesma mudança). A CLI
continua funcionando porque `all_onboardings()` tem 7 chamadores, todos dentro
de `surfaces/cli/wizard/` — uma atualização mecânica de import coberta por
`tests/unit/surfaces/cli/wizard/test_onboarding_flow.py`.

Credenciais de provider pegam a rota do Escopo A com o id de provider como o
nome da integração — exatamente o que `OnboardingFlow.enter_provider_credential`
já faz via `setup_many(client, (onboarding.provider_id,), …)`. Nenhum
segundo caminho de credencial existe ou é adicionado.

`RemoteClient.list_providers` / `verify_provider` são então implementados
sobre as novas rotas, suas recusas deletadas.

## Escopo C — as duas correções de fiação

- `RemoteClient.credential_fields` → `GET
  /v1/config/{node_id}/integration-schemas`. O nó: `Endpoint` não carrega
  nó, então o cliente resolve seu próprio nó do jeito que o console faz —
  do principal autenticado (`/auth/me` → `team_node_id`), caindo para trás
  para a raiz da árvore de config via `GET /v1/config`. Essa resolução vive
  em um helper privado em `RemoteClient`, porque o trabalho da CLI de 058
  também precisará dela.
- `RemoteClient.diagnose` → compor `GET /v1/setup/self-check` +
  `/v1/setup/diagnostics` (404 = "sem falha de bring-up", que é uma
  resposta saudável, não um erro — `first_run.py:137` documenta isso) +
  `/checklist` na forma `DiagnosticReport` que `ninjasre doctor` renderiza.

## Escopo D — a checklist como o estado compartilhado de first-run

`build_checklist` (`platform/startup/checklist.py`) já verifica provider,
credencial, fonte e passos de investigação contra suas dependências — os
testes unitários enumeram exatamente a semântica que a spec pede (passo
provider pergunta ao endpoint; passo source é feito quando o estate detém
algo; passo investigation quando um terminou). Extensão necessária:

- distinguir **sem provider / provider configurado mas não verificado / pronto**
  (aceitação 4) — um refinamento `state` mais detalhe no passo provider;
- adicionar detalhe por integração: quais são configuradas, verificadas, ou
  meramente declaradas — de `catalogue(health=ledger)`, que
  `gateway/http/routes/integrations.py` já lê.

A visão (`ChecklistView`) ganha os campos de detalhe; o console (052) e
`doctor` ambos leem esta uma rota, que é a "uma fonte" que a spec exige.

## Decisões que a spec deixou abertas

1. **Destino descritore é `core/llm/onboarding/`**, não `config/`.
   Config é tier 4 e não importa nada, mas descritores carregam dados livres
   de comportamento referenciando specs de campo de credencial; `core/llm/`
   já é proprietário de "o que é um provider" (adaptadores, a ordem
   `SUPPORTED_PROVIDERS` vem de `config/constants/llm`). Um décimo provider
   permanece "um módulo mais uma linha de constants".
2. **Respostas de verificação carregam `verified: bool` + `detail: str`** na
   forma exata `ProviderStatus.to_record()` que a CLI renderiza, então as
   duas superfícies não podem expressar o mesmo resultado diferentemente.
3. **`PUT` não `POST` para a escrita de credencial** — armazenar é
   substituição idempotente, rotação incluída; a sequência de versão no
   cofre é o histórico.
4. **Nenhuma rota de releitura de credencial de espécie alguma** — não
   mascarada, não parcial. A resposta de status é `configured` / `state` /
   timestamps.

## O que esta feature NÃO faz

- Sem UI de console — 052 renderiza estas rotas.
- Sem passo de estate/discovery — 053.
- Sem superfície de SSO (`/identity/sso` manipulação é 058), sem mudança nas
  regras de injeção de proxy, sem escopo de credencial multi-tenant além de
  `TenantScope`.
- Sem mudança ao que verificação *significa* para integrações de
  observabilidade (dados de janela recente, clock skew) — isso é
  aprofundamento de `verify_integration` de 054.

## Verificação de constituição

- **III** — a escrita de credencial é uma ação humana numa superfície,
  auditada; não uma capacidade de agent. Sem metadados de capacidade envolvidos.
- **IV** — o caminho do valor é corpo de requisição → `Vault.store` → armazém
  criptografado. Nunca alcança config, ambiente, logs, detalhe de auditoria,
  ou resposta alguma. O teste de varredura é a prova; `make check-credentials`
  continua mantendo a metade estática.
- **VI** — todos os nove providers andam o mesmo caminho descritor/verify; o
  provider local verifica contra o endpoint do operador como qualquer outro.
- **VIII** — o movimento descritor vai *abaixo* dos tiers; sem import nova
  para cima. `make check-imports` prova isso.
- **XII** — testes de rota primeiro, testes de refusal-deletion primeiro
  (`tests/contract/cli/test_remote_client_speaks_the_api.py` é a casa
  existente para o contrato remote-client).
- **I, II, V, VII, X, XI, XIII** — não afetado / trivialmente satisfeito
  (armazenamento via ports `PersistenceGateway` apenas; inglês; nada sai do
  host).
