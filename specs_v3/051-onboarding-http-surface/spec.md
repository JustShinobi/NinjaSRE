# 051 — A superfície HTTP de onboarding

**Bloqueia:** 052, 053, 054. Nada que um operador faça no navegador funciona
antes disto.

## O problema, com precisão

O `OnboardingFlow` precisa de cinco coisas do seu cliente. Por HTTP ele obtém
uma.

| Passo do fluxo | Chamada do cliente | HTTP hoje |
|---|---|---|
| escolher provider | `all_onboardings()` | dado local, não precisa de rota |
| informar credencial | `credential_fields(integration)` | recusado — rota existe, não usada |
| informar credencial | `store_integration_credential(...)` | **recusado — nenhuma rota** |
| escolher integrações | `list_integrations()` | `GET /v1/integrations` ✅ |
| verificar | `verify_integration(name)` | `POST /v1/integrations/{name}/verify` ✅ |
| verificar | `verify_provider(id)` | **recusado — nenhuma rota** |

Duas rotas precisam ser construídas. Duas recusas são erros de fiação sobre rotas
que já existem.

## Escopo

### A. Gravar uma credencial — a única coisa genuinamente nova

```
PUT /v1/integrations/{name}/credential
```

O corpo é um mapa plano de nome de campo para valor, validado contra o schema que
a própria integração declara. A resposta é um `IntegrationStatus` — nunca um eco
do que foi enviado.

Esta rota é a adição mais sensível do ponto de vista de segurança em toda a
specs_v3, e precisa ser construída sob as mesmas regras que o caminho da CLI já
segue:

- **O valor nunca aparece numa resposta, linha de log, detalhe de auditoria,
  mensagem de erro ou falha de validação.** *Nomes* de campo podem aparecer;
  valores não. O `SetupOutcome` já modela isso — `entered` e `skipped` carregam
  apenas nomes.
- **O valor vai para o cofre e para nenhum outro lugar.** Não para um nó de
  configuração, não para o ambiente do processo, não para um arquivo. O
  `PUT /v1/config/{node_id}` precisa continuar rejeitando qualquer campo que o
  schema de credencial marque como secreto, para que um segredo não possa entrar
  contrabandeado pela rota de configuração.
- **A permissão é `credential.write`**, que o papel owner já detém. É distinta de
  `config.write` de propósito: quem pode ajustar um limiar não é automaticamente
  quem pode trocar o token de API de um cluster.
- **A auditoria registra a escrita, a integração, os nomes dos campos e o ator.**
  Uma credencial trocada às 02:00 durante um incidente é um fato de que alguém
  vai precisar seis meses depois.
- **Rotação é a mesma rota.** Sem verbo separado de rotação; gravar de novo
  substitui, e a trilha de auditoria carrega a sequência.

Alternativa rejeitada: aceitar credenciais no
`POST /v1/integrations/{name}/verify` para não precisar de rota nova. Isso
confunde "verifique o que está guardado" com "guarde isto", e faz uma operação de
formato-leitura carregar um segredo.

### B. Uma superfície de provider

```
GET  /v1/providers                 os nove, cada um com seu descritor de onboarding
GET  /v1/providers/{id}            um, com campos, modelos, orientação
POST /v1/providers/{id}/verify     verificação ponta a ponta, devolve verified + detail
```

Os descritores já existem como dado em `surfaces/cli/wizard/providers/` — nove
módulos, cada um declarando seus `CredentialFieldSpec`, `guidance`,
`where_to_get_it`, `models`, `default_model`, e se roda localmente. Esta spec
**move esse dado para fora do pacote da CLI**, para que as duas superfícies leiam
uma cópia só. Um console que mantivesse sua própria lista de providers seria uma
segunda resposta para "o que este deployment pode usar", e a segunda resposta é a
que envelhece.

O `verify` precisa fazer uma requisição real e reportar o que voltou. "Deve
funcionar agora" não é a afirmação que está sendo feita.

A credencial do próprio provider passa pela mesma rota de credencial de qualquer
integração — a CLI já faz isso deliberadamente, e um segundo caminho para chaves
de provider seria um segundo lugar onde credenciais moram.

### C. Ligar as duas recusas que não precisam de rota nova

- `credential_fields` → `GET /v1/config/{node_id}/integration-schemas`, escopado
  ao nó em que o chamador está agindo. A mensagem de recusa hoje está correta
  sobre o formato ("reachable per node, not per client") e errada sobre a
  consequência: o cliente é capaz de resolver um nó.
- `diagnose` → `GET /v1/setup/diagnostics`, com `/v1/setup/self-check` e
  `/v1/setup/checklist` ao lado. Isso faz o `ninjasre doctor` funcionar contra um
  deployment remoto, o que hoje não acontece — ele falha com *"this deployment's
  API does not expose its own diagnostics"* enquanto a rota está lá.

### D. Um estado de primeiro uso que as duas superfícies leiam

```
GET /v1/setup/checklist    (existe — estender)
```

Estendido para responder, numa chamada: há provider configurado e verificado;
quais integrações estão configuradas, verificadas ou apenas declaradas; algum
estate foi descoberto; alguma investigação já rodou. O primeiro uso do console e
o `doctor` da CLI ramificam sobre isso, e duas implementações de "já estamos
configurados" discordariam justamente no dia em que importasse.

## Fora de escopo

- Configuração de SSO. As rotas `/identity/sso` existem; a superfície de console
  para elas é a 058.
- Qualquer mudança nas regras de injeção do proxy de credenciais.
- Escopo multi-tenant de credencial além do que o `TenantScope` já faz.

## Aceitação

1. `ninjasre --endpoint <url> --token <t> onboard` completa o fluxo de quatro
   passos contra um deployment remoto, terminando com um provider verificado.
2. Uma credencial gravada pela rota nova é utilizável por uma investigação e não
   aparece em nenhum detalhe de auditoria, corpo de resposta ou linha de log — um
   teste varre a saída capturada procurando o segredo e falha se ele estiver lá.
3. `ninjasre --endpoint <url> doctor` devolve um relatório em vez de uma recusa.
4. `GET /v1/setup/checklist` distingue um deployment sem provider de um com
   provider não verificado de um pronto.
5. Toda rota nova tem linha na tabela de permissões de rota, e a recusa em tempo
   de fiação para rota não declarada continua valendo.
