# Tarefas — 051 A superfície HTTP de onboarding

Ordenadas; cada tarefa é um commit; test-first, teste falhando confirmado
antes da implementação.

## Fase 1 — a escrita de credencial

- **T-001** Teste de contrato falhando: `PUT /v1/integrations/{name}/credential`
  com um corpo válido retorna um documento de status sem valor ecoado; um corpo
  fora do schema é recusado nomeando o *campo*, não o valor; uma integração
  desconhecida é 404. Adicione a expectativa de permissão `credential.write`
  à suite de permissão de rota (`padrão tests/security/test_route_permissions.py`).
- **T-002** Implementar: `Permission.CREDENTIAL_WRITE`, concessão de papel owner,
  linha de rota via `RouteTable.extended_with`, handler em
  `gateway/http/routes/integrations.py` chamando `Vault.store` depois
  `CredentialHealth.report`. T-001 verde.
- **T-003** Teste falhando: o trilho de auditoria para uma escrita de credencial
  registra ator, integração, nomes de campo, e sequência — e uma varredura
  sobre detalhe de auditoria, logs capturados, e corpo de resposta encontra
  nenhum valor sentinela. Depois implemente a emissão de auditoria.
- **T-004** Teste falhando: `PUT /v1/config/{node_id}` recusa um campo que um
  schema de integração marca como secreto. Implemente a recusa na validação do
  serviço de config se ausente.
- **T-005** `RemoteClient.store_integration_credential` implementado sobre a
  rota nova; sua recusa deletada. Teste primeiro em
  `tests/contract/cli/test_remote_client_speaks_the_api.py`: o método faz o
  `PUT` e o secreto aparece no corpo de requisição e em nenhum outro lugar
  (sem query, sem log, sem texto de exceção).

## Fase 2 — a superfície de provider

- **T-006** Teste de caracterização falhando para o movimento: `all_onboardings()`
  da *nova* localização retorna nove descritores em ordem `SUPPORTED_PROVIDERS`.
  Mova `ProviderOnboarding`, os nove módulos, e o percurso de descoberta para
  `core/llm/onboarding/`; mova `CredentialFieldSpec` com ele; migre cada site
  de import de `surfaces/cli/`; delete os módulos antigos no mesmo commit
  (Artigo VIII.4). Suite Wizard fica verde.
- **T-007** Testes de contrato falhando: `GET /v1/providers` lista nove com
  estado configurado/verificado; `GET /v1/providers/{id}` retorna fields
  (nomes, sem valores), guidance, models; id desconhecido é 404. Implemente
  `gateway/http/routes/providers.py` + linhas de tabela de rota.
- **T-008** Teste falhando: `POST /v1/providers/{id}/verify` alcança a mesma
  verificação ponta a ponta que `LocalServices.check_provider` executa, e
  retorna `verified` + `detail` de uma requisição real (test-doubled na porta
  LLM). Implemente.
- **T-009** `RemoteClient.list_providers` / `verify_provider` sobre as novas
  rotas; recusas deletadas; testes de contrato primeiro.

## Fase 3 — as correções de fiação

- **T-010** Teste primeiro: `RemoteClient.credential_fields` resolve o nó do
  chamador (principal's `team_node_id`, senão raiz de config) e lê
  `/v1/config/{node_id}/integration-schemas`; recusa deletada.
- **T-011** Teste primeiro: `RemoteClient.diagnose` compõe
  `/v1/setup/self-check` + `/diagnostics` (404 ⇒ "sem falha", não um erro)
  + `/checklist` em uma forma `DiagnosticReport`; recusa deletada. `ninjasre
  --endpoint … doctor` retorna um relatório.

## Fase 4 — a extensão de checklist

- **T-012** Testes falhando em `tests/unit/platform/startup/test_checklist.py`:
  o passo provider distingue ausente / configurado-não verificado / verificado;
  a checklist carrega detalhe configurado/verificado/declarado por integração.
  Implemente em `build_checklist` e `ChecklistView`.

## Fase 5 — o fluxo, ponta a ponta

- **T-013** Teste ponta a ponta falhando: `OnboardingFlow.run()` dirigido através
  de um `RemoteClient` contra um gateway em processo completa todos os quatro
  passos e termina com um provider verificado — o teste que prova que as
  recusas se foram como um conjunto, não uma por uma. Inclui a varredura de
  aceitação-2: o secreto entrado no prompt não aparece em resposta capturada
  alguma, linha de log, ou detalhe de auditoria.
- **T-014** `make docs` / regeneração de catálogo se as novas rotas ou
  permissão emergem em referências geradas; `make verify` verde.

## Definição de pronto

1. `ninjasre --endpoint <url> --token <t> onboard` completa o fluxo de quatro
   passos contra um deployment remoto, terminando com um provider verificado —
   T-013 no gate, e uma vez manualmente contra o container de validação
   (registrado em deviations com a transcrição).
2. Uma credencial armazenada pela rota nova é usável por uma investigação e
   greppable em lugar algum: varredura de T-003/T-013 falha se o sentinela
   aparece em qualquer corpo de resposta capturado, linha de log, ou detalhe
   de auditoria.
3. `ninjasre --endpoint <url> doctor` imprime um relatório, não uma recusa
   (T-011).
4. `GET /v1/setup/checklist` retorna três estados de deployment distinguíveis —
   sem provider, provider não verificado, pronto (T-012).
5. Cada rota nova tem uma linha na tabela de permissão de rota; fiação de uma
   rota não declarada ainda lança (`comportamento RouteTable.guard_for`, já
   mantido pela suite de segurança — T-001/T-007 estendem suas expectativas).

## Dependências em outras features specs_v3

Nenhuma inbound. **052, 053, 054, 058 e 062 todas consomem esta feature**: 052
precisa de cada rota aqui; 053/054 precisam da escrita de credencial e fiação
de integration-schemas; 058 reutiliza padrão de `credential.write` para suas
próprias permissões; 062 lê a mesma emissão de machine-token que as rotas aqui
deixam intactas.
