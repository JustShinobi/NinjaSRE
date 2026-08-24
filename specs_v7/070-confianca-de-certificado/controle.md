# Controle — Confiança de certificado

**O estado abaixo foi verificado contra o código atual**, na worktree
`/srv/workspaces/NinjaSRE/.claude/worktrees/agent-a18065e27f0a770a3`
(ramo `worktree-agent-a18065e27f0a770a3`), partindo de `7d1aa28`.

Nota de execução: a worktree nasceu apontada para o **commit raiz do
repositório** ("Add initial README.md"), não para `master`. Foi reapontada com
`git reset --hard master` antes de qualquer trabalho — o mesmo defeito de
infraestrutura que a 040 registrou.

---

## Fase 0 — a linha de base (T001, T002)

### T001 — `make verify` na árvore intacta

**exit 2 — 7 failed / 12407 passed / 27 skipped, em 724,83s.**
Log fora do repositório, em
`/tmp/claude-999/-srv-workspaces-NinjaSRE/0197c7d7-.../scratchpad/logs/T001-baseline-verify.log`.

Não está verde, e as sete falhas são **preexistentes e fora do alcance desta
feature**. Nomeadas para que nenhuma seja debitada dela:

| Teste | Causa medida |
|---|---|
| `tests/architecture/test_removed_vendor_references.py::test_no_reference_surface_names_a_removed_vendor` | `docs/provenance-map.md` nomeia 18 vendors fora do escopo validado. O documento passou a ser committed pela mudança de governança da onda; o varredor agora o enxerga |
| `tests/architecture/test_no_committed_file_states_a_stale_catalogue_size.py::...` | `docs/provenance-map.md` e sete arquivos de `specs/` citam "~85 integrações" contra as 15 reais. Mesma causa: os documentos de planejamento passaram a ser committed |
| `tests/contract/console/test_console_gate.py` (2 casos) | precisam do console construído |
| `tests/contract/console/test_console_gate_configuration.py[dynamic-routes]` | idem |
| `tests/contract/console/test_console_visual_regression.py` (2 casos) | `console/.next/standalone/server.js is missing; run the build before capturing.` — a worktree não tem o build do console |

Nenhuma toca `platform/credentials/proxy`, `gateway/proxy`, `integrations/proxmox`
nem `platform/config_service`. Continuei em vez de parar, e isto está declarado
em vez de escondido.

**Contaminação a declarar:** o run cruzou o começo da Fase 1 — as edições da
fase e o `ruff format` do hook de commit correram durante os últimos minutos
dele. A medida que vale é a de T046, e a comparação é feita contra estes sete
nomes, não contra o número.

### T002 — o estado de partida do Proxmox no staging

**NÃO INICIADO — é do orquestrador.** A worktree não alcança cluster nem banco.
O que precisa ser lido antes de qualquer declaração de confiança está na
seção "O que o orquestrador precisa medir".

---

*(as fases seguintes são anexadas a este arquivo à medida que fecham)*

## Fase 1 — o vocabulário desce um tier (T003–T007)

| Peça | Estado | Detalhe |
|---|---|---|
| T003 — suíte de transporte do Proxmox verde antes | FEITO | `tests/unit/integrations/test_proxmox_transport.py` — **24 passed** |
| T004 — teste do vocabulário no tier do proxy | FEITO | `tests/unit/platform/credentials/test_certificate_trust.py`, 29 casos. **Vermelho:** `ModuleNotFoundError: No module named 'platform.credentials.proxy.trust'` |
| T005 — o vocabulário | FEITO | `platform/credentials/proxy/trust.py:120` `CertificateTrust`, `:71` `TrustAnchor` (4 formas), `:290` `TrustRegistry`. 29 passed |
| T006 — Proxmox declara sobre o comum | FEITO | `integrations/proxmox/certificates.py:46` `DEFAULT_TRUST`, `:51` `FINGERPRINT_IS_SHOWN_AT`. T003 rodou de novo, **24 passed, sem editar um caso** |
| T007 — contratos de import | FEITO | `make check-imports` — 7 kept, 0 broken. O tier do proxy não passou a importar `integrations/` |

Generalização em três pontos, como o plano pede: `fingerprints: tuple[str, ...]`
(`trust.py:134`), `addresses: tuple[str, ...]` (`trust.py:143`), e a prosa fala
do componente que aplica.

## Fase 2 — a recusa vira de primeira classe (T008–T011)

| Peça | Estado | Detalhe |
|---|---|---|
| T008/T009 — teste das razões e das três frases | FEITO | `tests/unit/platform/credentials/test_certificate_refusal.py`, 20 casos. **Vermelho:** `ImportError: cannot import name 'CertificateNameMismatch' from 'platform.credentials.proxy.errors'` |
| T010 — razão, três formas, status | FEITO | `platform/credentials/proxy/errors.py:37` `CERTIFICATE_UNTRUSTED`; `:264` `CertificateRefused`, `:281` `CertificateUntrusted`, `:297` `CertificatePinBroken`, `:329` `CertificateNameMismatch`. Status em `platform/credentials/proxy/app.py:60` — **412**, com a razão escrita ali |
| T011 — atravessa o motor sem ser reembalada | FEITO | `platform/credentials/proxy/engine.py:265` — o achatamento genérico não a captura; a única coisa acrescentada é o nome da integração, que o remetente não pode saber |
| (a mais) tradução para o cliente | FEITO | `integrations/_base/errors.py` — `IntegrationErrorReason.CERTIFICATE_UNTRUSTED`, categoria `UNAVAILABLE` e não `PERMISSION`. **Vermelho:** `AssertionError: Extra items in the right set: <ProxyErrorReason.CERTIFICATE_UNTRUSTED>` — o `.get()` de `_PROXY_REASONS` a rebaixaria para `REFUSED` em silêncio |

**Por que 412 e não 502.** Um certificado recusado não é "o vendor não
respondeu": o vendor respondeu, e uma pré-condição deste deployment está por
cumprir — ninguém declarou o que confiar naquele endereço. É a mesma classe de
`credential_not_configured`, e leva quem lê só o número para a configuração em
vez de para uma repetição que vai falhar igual para sempre.

## Fase 3 — a aplicação, no remetente (T012–T017)

| Peça | Estado | Detalhe |
|---|---|---|
| T012–T014 — contrato dos três modos, pin quebrado, nome que não confere | FEITO | `tests/contract/credentials/test_certificate_trust_at_the_egress.py`, 16 casos, contra um **servidor TLS local** com autoridade e folhas geradas no próprio teste. **Vermelho:** `TypeError: HttpOutboundSender.__init__() got an unexpected keyword argument 'trust'` |
| T015 — o padrão não afrouxou | **FEITO — e já estava verde** | `test_the_default_context_stays_as_strict_as_the_library_is` passou no run vermelho, antes da implementação: `CERT_REQUIRED`, `check_hostname`, `VERIFY_X509_STRICT` ligados. O afrouxamento acompanha certificado fornecido e nada além — `test_a_supplied_certificate_relaxes_conformance_and_nothing_more` |
| T016 — resolução de contexto por endereço | FEITO | `gateway/proxy/sender.py:124` `context_for_trust`, `:270` `HttpOutboundSender`, `:300` `_egress_for` (um contexto por endereço, construído uma vez), `:180` `_PinCheckingConnection.connect` |
| T017 — a decisão de forma que a pinagem exigiu | FEITO | abaixo |

### T017 — a decisão de forma, e por quê

**Pinar.** A biblioteca padrão não oferece o certificado do par por cima de
`urlopen`. O caminho: `_PinCheckingConnection` (`sender.py:180`) estende
`http.client.HTTPSConnection` e, **dentro de `connect()`**, lê
`sock.getpeercert(binary_form=True)`, calcula o SHA-256 e compara com o conjunto
declarado. `connect()` é o último instante antes de `request()` escrever bytes —
uma verificação em volta da resposta já teria mandado a credencial para quem
atendeu. É ligado por `_PinCheckingHandler` (`sender.py:197`), que troca a classe
de conexão que `do_open` instancia.

O contexto do modo pinado é `CERT_NONE`: **o pin substitui a verificação de
identidade em vez de acrescentar a ela**, que é exatamente o que faz do
fingerprint a forma que funciona para um cluster alcançado por IP. Um `CERT_NONE`
que só é alcançável por declaração e cuja conexão é recusada no `connect()` se o
digest não bater não é "então não verifica" — é uma âncora mais estreita.

**`_PinRefused` não é `OSError`** (`sender.py:167`), de propósito: `urllib`
embrulha `OSError` em `URLError`, e a recusa precisa chegar carregando os dois
fingerprints em vez de virar mais uma coisa inalcançável.

**Nomear o certificado custa um segundo handshake** (`sender.py:400`
`_observed_fingerprint`, `:425` `_certificate_names`). A biblioteca padrão não dá
acesso a um certificado cuja verificação falhou. **Os dois handshakes de
diagnóstico não escrevem um byte** — não há requisição neles para injetar
credencial — e o de nome-que-não-confere **continua verificando a cadeia**,
desligando só a checagem que falhou. A alternativa era uma mensagem que diz "não
confiado" e não nomeia nada, que é a forma de mensagem que esta feature existe
para remover.

**Códigos 62 e 64** (`sender.py:89`), e não a mensagem: `X509_V_ERR_HOSTNAME_MISMATCH`
e `X509_V_ERR_IP_ADDRESS_MISMATCH` são ABI do OpenSSL; a mensagem é prosa que
muda de versão.

## Fase 5 — quem pode (T021–T023, parcial)

| Peça | Estado | Detalhe |
|---|---|---|
| T021 — teste da permissão dedicada | FEITO | `tests/unit/platform/identity/test_trust_unverified_permission.py`, 10 casos. **Vermelho:** `AttributeError: type object 'Permission' has no attribute 'INTEGRATION_TRUST_UNVERIFIED'` |
| T022 — a permissão e o papel | FEITO | `platform/identity/permissions.py:81` `INTEGRATION_TRUST_UNVERIFIED`, com a distinção escrita ali; concedida no incremento de `Role.ADMIN` (`:196`). Classificada como escrita **pela derivação por verbo**, não por segunda lista — conferido, não assumido |
| Artefato gerado | FEITO | `fixtures/contract/roles.json` regenerado por `python -m tools.console_roles write` (não editado à mão). **Recurso compartilhado — declarado** |
| T023 — portão da rota | PARCIAL | ver Fase 6 |

## O VÍNCULO DO PLANO DE CONTROLE — a decisão do operador, feita

Fora do `tasks.md` desta feature: a 040 mediu que **sem plano de controle
vinculado o balcão de remediação não compõe**, e o operador decidiu que o
vínculo é desta feature.

### Quem constrói o vínculo em produção

| Peça | `file:line` |
|---|---|
| O composer | `gateway/http/control_plane.py:64` `compose_control_plane` |
| A chamada de produção | `gateway/http/lifespan.py:98` — **antes** de `compose_remediation` (`:107`), porque o balcão pergunta se existe um plano antes de compor |
| O vínculo em si | `gateway/http/control_plane.py:118` `control_plane.bind(bound)` |
| O que é vinculado | `ProxmoxControlPlane(client=ProxmoxWriteClient(transport=HttpProxyTransport(...), context=RequestContext(...), endpoints=..., trust=...), declarations=DECLARATIONS)` — as 13 escritas de hipervisor declaradas |

### Qual teste reprova se o fio for cortado — **confirmado cortando à mão**

`tests/unit/gateway/http/test_control_plane_composition.py`, 13 casos.

**Corte 1 — a chamada em `lifespan.py` removida:**

```
FAILED test_the_process_that_serves_binds_it_and_binds_it_before_the_desk
E   AssertionError: nothing in the process that serves binds a control plane.
    Without it compose_remediation writes desk_skipped, no approval is ever
    queued, and the deployment proposes nothing for a reason no policy chose.
E   assert 'compose_control_plane' in ['get_logger', 'tuple',
    'recompose_investigator', 'compose_deep_verifier', 'list',
    'compose_integration_access', ...]
```

O teste **caminha a AST** de `gateway/http/lifespan.py` em vez de casar texto, e
afirma também a **ordem** — `compose_control_plane` antes de
`compose_remediation`. Um fio renomeado, comentado ou movido para trás de um
ramo que nunca roda reprova aqui.

**Corte 2 — `control_plane.bind(bound)` removido do composer:**

```
FAILED test_a_configured_cluster_becomes_a_bound_control_plane
E   AssertionError: assert None is ProxmoxControlPlane(client=..., declarations={...})
E    +  where None = control_plane.current()

FAILED test_binding_it_is_what_lets_the_desk_compose
E   AssertionError: assert ('a control p...s available',) == ()
E     Left contains one more item: 'a control plane, so there is nothing for a
       write to change; an operator configures one before remediation is available'
```

O segundo é o elo da onda: chama a **composição real** `compose_remediation` e
exige que ela componha um balcão.

### A postura, escrita e não presumida

Vincular **não autoriza nada**. O portão continua resolvendo a postura do
deployment no instante em que uma escrita é decidida, a aprovação é gravada
`pending`, e executar é uma segunda entrada por uma rota que uma pessoa aperta.
Dito no cabeçalho de `gateway/http/control_plane.py:24-28` e em
`gateway/http/lifespan.py:92-97`.

**Nada ali segura credencial e nada ali pode:** o cliente de escrita alcança o
cluster pelo proxy de credencial como toda chamada autenticada, e um deployment
sem proxy **não vincula nada** em vez de construir um cliente que teria de
segurar o segredo — `test_the_bound_plane_reaches_the_cluster_only_through_the_proxy`
e `test_the_bound_plane_holds_no_credential`.

**Fail-closed em cinco caminhos**, cada um com teste: sem proxy, configuração
ilegível, integração ausente, integração desligada, endereço vazio. Nenhum deles
vincula, e cada um escreve a linha que diz qual.

### Sobre o vizinho: hook que levanta não bloqueia

Registrado e **não dependido**. A recusa por certificado desta feature está no
**caminho de egress** — `gateway/proxy/sender.py:180`
`_PinCheckingConnection.connect`, dentro do `connect()` da conexão, antes de
`request()` escrever um byte. Não é hook, não é observador, e não há caminho em
volta dela: o contexto vem do registro que a composição entrega e o remetente
não consegue um por outro caminho.

## Fase 7 — composição: a confiança chega ao processo que abre o socket (T031–T035)

| Peça | Estado | Detalhe |
|---|---|---|
| T031 — teste da composição | FEITO | `tests/unit/gateway/proxy/test_trust_composition.py`, 14 casos. **Vermelho:** `ImportError: cannot import name 'refresh_configured_trust' from 'gateway.proxy.hosts'` |
| T032 — o registro entregue ao remetente | FEITO | `gateway/proxy/composition.py:38` — **um** `TrustRegistry`, entregue a `HttpOutboundSender(trust=trust)` e a `ProxyEngine(trust=trust)`. Dois registros seriam duas respostas, e no dia em que divergissem uma linha de auditoria nomearia uma âncora que a conexão não usou |
| T033 — teste da leitura da configuração | FEITO | mesmo arquivo: forma declarada sai da árvore; entrada desligada, sem endereço, ou que não parseia não contribui; **uma declaração malformada não custa às outras a sua** |
| T034 — leitura e ciclo | FEITO | `gateway/proxy/hosts.py:104` `trust_from_configuration`, `:145` `refresh_configured_trust`; `gateway/proxy/__main__.py` — `_configured_egress` faz **uma leitura** que produz host e confiança, aplicada no arranque e no ciclo de 60s |
| T035 — resiliência | **FEITO — verde sem mudança** | configuração ilegível deixa em vigor o que está em vigor e registra; o `except ... continue` do ciclo já fazia isso e o teste agora trava a propriedade caminhando a AST |

Cache invalidado por geração: `TrustRegistry.replace_all` incrementa
`generation`, e `HttpOutboundSender._egress_for` (`sender.py:300`) descarta os
contextos quando ela muda. Sem isso um contexto em cache sobreviveria à
declaração que o autorizou — a mesma falha, uma camada abaixo.

## Fase 8 — onde o operador lê (T036–T038)

| Peça | Estado | Detalhe |
|---|---|---|
| T036 — teste do braço novo | FEITO | `tests/unit/integrations/test_proxmox_certificate_verdict.py`, 8 casos. **6 já passavam** antes da implementação: a mensagem do proxy já chegava ao painel pelo fallback `str(error)`. **Vermelho nos 2 restantes:** `AssertionError: assert 'Certificates' in '10.20.20.9 presented a certificate...'` e `assert <CERTIFICATE_UNTRUSTED> in {...}` |
| T037 — o braço | FEITO | `integrations/proxmox/verifier.py` — `_ADVICE[CERTIFICATE_UNTRUSTED]` **acrescentado** à frase do proxy, não substituído: substituir perderia os dois fingerprints, que são o valor inteiro da mensagem. `_detail_for` decide, e `_ADVICE_FOLLOWS_THE_REFUSAL` diz quais razões acrescentam |
| T038 — a linha da verificação profunda | FEITO | `gateway/http/deep_verification.py` — `trust_line_for` + campo `certificate_trust`; 8 casos em `tests/unit/gateway/http/test_deep_verification_reports_trust.py` |

## Fase 6 — a escrita, o portão e o registro (T023–T027)

| Peça | Estado | Detalhe |
|---|---|---|
| T023 — portão da rota | FEITO | `gateway/http/integration_endpoints.py` `StampedTrust.refuse_unless_permitted` — `integration.manage` sempre, `integration.trust_unverified` **só na forma insegura**. Verificado **antes** de o documento ser tocado, então uma recusa não deixa escrita parcial |
| T024 — o campo sobrevive ao salvamento seguinte | FEITO | `test_the_declaration_survives_the_next_address_write`. **Vermelho:** `ImportError: cannot import name 'configured_trust'`. `_entry_records` passou a copiar `trust` — sem isso a declaração seria apagada no primeiro salvamento de endereço |
| T025 — a escrita | FEITO | `record_certificate_trust`, upsert na entrada, lista inteira reescrita, no nó da organização |
| T026/T027 — auditoria da escrita | FEITO | `trust_audit_detail` — conjunto fixo de escalares; ação e tipo de recurso em `config/constants/security.py` (`INTEGRATION_TRUST_AUDIT_ACTION` / `..._RESOURCE_KIND`). Asserção negativa: nenhum cabeçalho de certificado, nenhuma chave privada, nenhum token |
| T028/T029 — escalares na linha de resolução | FEITO | `platform/credentials/proxy/audit.py` — `trust_anchor` sempre, `fingerprint` quando há; preenchidos em `engine.py`, e numa recusa o fingerprint é o **observado** |
| A rota | FEITO | `PUT /v1/integrations/{name}/trust` em `gateway/http/routes/integrations.py`; linha da tabela em `gateway/http/security/onboarding_routes.py` com `INTEGRATION_MANAGE` |
| T012 — identidade do corpo ignorada | FEITO | `stamped_trust` descarta `unverified_accepted_by`/`_at` do corpo **antes** de validar e carimba o principal autenticado e o instante do servidor |

**Não existe booleano em lugar nenhum do caminho.** O corpo da requisição tem
`fingerprints`, `certificate_pem` e `unverified_reason` — a forma insegura é
alcançada escrevendo *por quê*, e é isso que a torna uma decisão em vez de uma
caixa de seleção. Uma razão presente e em branco é recusada nomeando a razão.

---

## O que fica pendente, nomeado, não escondido

| Item | Estado | Dono |
|---|---|---|
| **T042–T045** — testes de arquitetura (um lugar só pode não verificar; nenhum schema tem booleano; nenhuma capacidade lê confiança; política de rede do sandbox) | **NÃO INICIADO.** Escrevi o arquivo e **o descartei sem commitar** por não ter rodado: um teste não verificado no build é pior que um teste ausente. As propriedades estão implementadas (`context_for_trust` é o único construtor, a seção é fechada), mas **não estão travadas por teste** | próxima sessão |
| **T039/T040** — painel do console | **NÃO INICIADO.** A fronteira do console foi cedida por colisão com a 030; nenhum arquivo sob `console/` foi tocado | a decidir |
| **T041** — `integrations/proxmox/docs.md` com o caminho de configuração | **NÃO INICIADO** | próxima sessão |
| **T046** — `make verify` inteiro comparado com T001 | **NÃO RODADO** | próxima sessão |
| **T002, T047–T053** — evidência de staging | **NÃO INICIADO — do orquestrador.** A worktree não alcança cluster nem banco | orquestrador |
| T030 — teste da invalidação por troca de endereço | **PARCIAL.** A propriedade está implementada e coberta de lado (`test_the_declaration_survives_the_next_address_write` prova que a declaração passa a cobrir o endereço novo, e `trust_from_configuration` só nomeia o endereço atual), mas não há teste que prove a recusa ao endereço novo até nova decisão | próxima sessão |

### Correção à spec, medida

A spec assume que **"sandbox não fala com o proxy"**. Não é o caso: a
`NetworkPolicy` do perfil Kubernetes (`platform/sandbox/profiles/kubernetes/pod_spec.py:257`)
nega todo egress e então **permite exatamente três coisas** — DNS, o proxy de
credencial na porta declarada, e o listener Envoy do próprio pod. É estreito, é
anterior a esta feature, e **esta feature não o alterou**. O teste de T045 deve
afirmar essas três regras, não a ausência do proxy.

### Recursos compartilhados tocados — declarados

| Recurso | O que fiz |
|---|---|
| `fixtures/contract/roles.json` | **regenerado** por `python -m tools.console_roles write` (permissão nova) |
| `fixtures/contract/openapi.json` | **regenerado** por `python -m tools.mockplane contract` (rota nova) |
| `console/src/i18n/*.ts`, `console/src/shell/routes.ts`, `console/visual/screens.json` | **não tocados** |
| `fixtures/scenarios/**` | **não tocados** |
| `console/tests/e2e/transversal-rules.spec.ts` | **não tocado** |
| Números de revisão de migração | **nenhuma migração criada** — sem tabela nova, sem coluna nova |
| `platform/persistence/postgres/models.py` | **não tocado** |

### Chaves de i18n que precisei e não pude escrever

**Nenhuma.** Nenhum arquivo sob `console/` foi tocado. Quando o painel for
feito, as chaves serão declaradas então.

### O que o orquestrador precisa medir no ambiente real

1. `select kind, subject, outcome, checked_at, detail from verifications where subject='proxmox';` — o "antes".
2. `select count(*) from estate_resources where source='proxmox' and absent_since is null;` — o "antes" e o "depois".
3. **Declarar o fingerprint primeiro**, por `PUT /v1/integrations/proxmox/trust` com `{"fingerprints":["<o do nó>"]}`. O certificado do Proxmox nomeia o nó; se a integração estiver apontada para IP, o PEM falha a verificação de nome — e essa é a terceira mensagem, caminho esperado e testado.
4. `select occurred_at, actor_kind, actor_id, outcome, detail from audit_events where resource_kind='integration' and resource_id='proxmox' order by occurred_at desc limit 10;`
5. **Quebrar o pin de propósito** e capturar a mensagem: tem de conter os dois fingerprints e **não** conter "Neither the credential proxy nor any configured Proxmox node answered".
6. `select count(*) from audit_events where detail::text like '%BEGIN CERTIFICATE%' or detail::text like '%PRIVATE KEY%' or detail::text like '%PVEAPIToken%';` — esperado 0.
7. **Do vínculo do plano de controle:** no log do processo depois do boot, `remediation.control_plane_bound` (com `integration`, `endpoints`, `trust`, `capabilities=13`) e em seguida `remediation.desk_composed`. Se aparecer `remediation.control_plane_skipped`, a razão está na linha. E então `select count(*) from approvals where arguments->>'change_type'='remediation';` — o número que a 040 previu como zero.

---

# Segunda janela — Fases 9, T041 e o painel

Retomada sobre `master` já mergeado (o vínculo do plano de controle está lá).
Rebaseada depois sobre `897db31`, que trouxe a allowlist transversal a zero.

## Fase 9 — as garantias que precisam de teste próprio (T042–T045)

`tests/architecture/test_one_place_can_stop_verifying.py`, **10 casos, 10 passed**.
Escrito de novo e **rodado** — na primeira janela eu o descartei sem commitar
por não ter rodado, e isso estava certo.

| Peça | Estado | Detalhe |
|---|---|---|
| T042 — um lugar só pode não verificar | FEITO | `test_only_the_proxy_sender_can_build_a_context_that_does_not_verify`. Varre os sete pacotes entregues por `CERT_NONE` e `_create_unverified_context`; o conjunto tem de ser exatamente `{gateway/proxy/sender.py}` |
| T042b — nome desligado só onde a cadeia não está | FEITO | `check_hostname = False` ⊆ o mesmo arquivo. Legítimo duas vezes: pin (substitui a identidade) e o handshake de diagnóstico que lê os nomes (ainda verifica a cadeia) |
| T042c — alcançável só por declaração | FEITO | AST: todo `CERT_NONE` do arquivo está dentro de `context_for_trust` |
| T043 — nenhum booleano desliga verificação | FEITO | três superfícies checadas por onde alguém escreve: seções de configuração (recursivo a partir de `ConfigSection`), schemas de credencial das 15 integrações, e o corpo de `TrustWriteRequest` |
| T043b — o único booleano do vocabulário | FEITO | `CertificateTrust(verify=False)` levanta; com só razão levanta; com só identidade levanta. O campo existe para **expressar** a forma, e não pode ser virado |
| T044 — nenhuma capacidade toca confiança | FEITO | varredura de `capabilities/` + nenhuma declara `integration.trust_unverified` como requisito |
| T045 — a política de rede do sandbox | FEITO | manifesto construído de verdade: 3 regras de egress, ingress vazio, DNS e o proxy presentes |

### A régua, cortando o fio à mão

Plantei um segundo `CERT_NONE` em `integrations/proxmox/client.py` e rodei:

```
E   AssertionError: certificate verification may be weakened in exactly one
    place, and it is gateway/proxy/sender.py. Found:
    {'gateway/proxy/sender.py': [154], 'integrations/proxmox/client.py': [985]}.
E   Extra items in the left set: 'integrations/proxmox/client.py'
```

A regra morde e **nomeia o arquivo**. Restaurado, 10 passed.

### Correção de escopo medida, não presumida

A varredura por nome de campo pegou quatro ocorrências e **duas eram falso
positivo**, então o conjunto de nomes foi estreitado em vez de o teste ser
afrouxado:

- `platform/knowledge/topology/models.py:194,274 unverified: bool` — fato de
  topologia que a descoberta ainda não confirmou. Nada de TLS.
- `surfaces/cli/wizard/integrations/__init__.py:83 verify: bool = True` — *rodar
  a verificação depois de guardar*, não *pular verificação de TLS*.

`unverified` saiu da lista de nomes. Uma regra que grita onde não deve é uma
regra que alguém afrouxa em vez de obedecer.

## T041 — a documentação

`integrations/proxmox/docs.md`, seção 4 reescrita. Além das três formas
programáticas que já documentava: qual forma serve nó único e qual serve
cluster, a rota (`PUT /v1/integrations/proxmox/trust`) com os corpos JSON, a
tabela de qual permissão cada forma exige **e por quê**, o que a auditoria
grava, que a confiança é por endereço e não por vendor, o que acontece quando o
certificado do nó muda, e as três recusas contra a de rede.

O bloco Python existente ficou **byte a byte igual**: `make verify` executa os
exemplos documentados, e o caminho de configuração entrou como JSON/HTTP para
não acrescentar exemplo executável. Gates: `test_doc_examples` 29 ok,
`generate_integration_docs --check` exit 0, `check_docs_drift` exit 0.

## O painel do console — o achado que o encolheu

Fui medir antes de construir, e **FR-036 já valia com zero mudança de console**.
A cadeia inteira:

`ProxmoxVerifier.connect` → `_detail_for` → `Connectivity.detail` →
`console/src/app/api/verify/route.ts:160` (`said = vendor.detail`, e "a resposta
do vendor vence onde há uma") → `reason` → `integration-panel.tsx:253-256`, que
renderiza `verdict.detail` **verbatim**.

Ou seja: a frase da recusa que de fato aconteceu — com os fingerprints — já
chega à tela. **E é assim que tem de ser**: só o servidor sabe qual certificado
foi apresentado e qual era esperado; uma frase fixa no catálogo ou perderia os
dois fatos ou os parafrasearia em algo que o operador não consegue comparar com
o que o nó mostra.

Travado por `console/tests/unit/surfaces/integration-panel-certificate.test.tsx`,
**5 casos, 5 passed**: as três recusas de certificado passam inteiras, e a frase
de host silencioso continua aparecendo sem mencionar fingerprint.

Sem componente novo, sem chave de i18n, sem tocar arquivo de escrita única.

## Transversal, com a allowlist em zero

```
uv run python -m tools.spec_validation browser \
  --feature specs_v7/070-confianca-de-certificado \
  --test console/tests/e2e/transversal-rules.spec.ts
```

**exit 0 — 45 passed, 7 skipped.** `EXCEPTIONS` está vazia, então isto é rede
nenhuma: qualquer regressão de tela apareceria como falha nova. Não apareceu.

Console também: `prettier --check` limpo no meu arquivo (o gate roda
format-check agora), `tsc --noEmit` sem diagnóstico para ele.

---

## O que fica pendente ao fim desta janela

| Item | Estado | Dono |
|---|---|---|
| **T039/T040 — o formulário de confiança no painel** | **NÃO FEITO, e nomeado.** Abre escopo: precisa de um courier `/api/...` novo para `PUT /v1/integrations/{name}/trust`, um grupo de campos no painel, o portão de permissão para a forma insegura, chaves de i18n nos **dois** catálogos, e teste. Não cabe como "pequeno". **A parte que importava — a frase da recusa — já está entregue e travada por teste.** O que falta é declarar a confiança *pela tela* em vez de pela API | próxima feature |
| **T030** — teste da invalidação por troca de endereço | **PARCIAL.** A propriedade está implementada e coberta de lado; falta o teste que prova a recusa ao endereço novo até nova decisão | próxima sessão |
| **T046 — `make verify` inteiro** | **NÃO RODADO — do orquestrador**, por instrução dele nesta janela | orquestrador |
| **T002, T047–T053 — evidência de staging** | **NÃO INICIADO — do orquestrador** | orquestrador |

## Coerência com o bloco de catálogo mergeado — conferida

`ticket` e `csrf_token` declaram, em `integrations/proxmox/schema.py:126-149`,
"o mesmo acesso do login que foi trocado por eles — material de sessão que o
proxy escreve, nunca um escopo que um operador define". **Coerente com o que
esta feature faz**, e nada a mudar: os dois escalares que acrescentei à linha de
resolução (`trust_anchor`, `fingerprint`) não enumeram campo de credencial
nenhum, e `trust_audit_detail` é um conjunto fixo que não tem como carregar
material de sessão.

## Chaves de i18n que precisei e não pude escrever

**Nenhuma.** Nenhum arquivo de catálogo tocado, e por desenho: a frase da recusa
é do servidor.

---

# Terceira janela — o formulário de confiança no painel (T039, T040)

Retomada sobre `master` já mergeado, worktree `.claude/worktrees/agent-a7b534f2ce83afd7c`,
partindo de `be87b53`. Este era o único item da feature nomeado como não feito
nas duas janelas anteriores.

## O que a tela ganhou

Nada de tela nova, nenhum mockup — a spec já dizia isso (`Referência visual
(DoD)`). O que muda é o painel da integração
(`console/src/surfaces/integration-panel.tsx`): um grupo "Certificate trust"
com dois campos sempre visíveis para quem tem `integration.manage`
(fingerprints pinados, um por linha; autoridade em PEM) e um terceiro campo —
a razão — visível só para quem tem `integration.trust_unverified`.
Independente de `showForm`/`connected`: um pin pode precisar ser declarado ou
reparado numa integração cuja credencial já está guardada, então o grupo não
fica escondido atrás de "Replace credential".

| Peça | Estado | Detalhe |
|---|---|---|
| T039 — teste do painel, vermelho primeiro | FEITO | `console/tests/unit/surfaces/integration-panel-trust-form.test.tsx`, 12 casos. **Vermelho genuíno, reproduzido depois do fato**: implementação isolada com `git stash push -u` (só nos arquivos de implementação; os testes ficaram de fora do stash), suíte rodada contra o painel antigo — **10 failed / 2 passed** de 12; `trust-route.test.ts` **falhou ao carregar o módulo**: `Error: Failed to resolve import "@/app/api/trust/route". Does the file exist?`. Os 2 que passaram vazios são os dois de ausência ("does not show accepting unverified as available without the permission", "sees no certificate trust group at all") — não distinguem "ausente porque não existe nada ainda" de "ausente porque o gate funcionou", e ficam nomeados aqui por isso. Implementação restaurada com `git stash pop` logo em seguida, antes de qualquer outro trabalho |
| T040 — implementação, sem componente novo | FEITO | `integration-panel.tsx` — grupo `data-testid="certificate-trust"`, campos pelos controles já existentes (`Textarea` de `@/components/form`), courier novo `console/src/app/api/trust/route.ts` (`TRUST_ENDPOINT = '/api/trust'`), permissão lida via prop `mayTrustUnverified` computada em `console/src/surfaces/screens/integrations.tsx:248` (`may(viewer, 'integration.trust_unverified')`) |
| O portão, no cliente | FEITO | o subgrupo `trust-unverified` (reason field) só é renderizado quando `mayTrustUnverified` é `true` — "absent, not disabled", `integration-panel.tsx:718` |
| O portão, no servidor (o que decide de fato) | **FEITO — já existia, verificado nesta janela** | `gateway/http/integration_endpoints.py:153` `StampedTrust.refuse_unless_permitted`, chamado em `gateway/http/routes/integrations.py:875` **antes** de qualquer escrita no documento. `tests/unit/gateway/http/test_certificate_trust_write.py` rodado nesta janela — **15 passed**; `test_accepting_unverified_without_the_dedicated_permission_is_refused` prova a recusa, com `Permission.INTEGRATION_TRUST_UNVERIFIED.value` presente na mensagem de `PermissionDenied` |
| O portão, na volta ao cliente | FEITO | o courier lê `error.message` do envelope real que o gateway produz (`{"error":{"message":...}}`, confirmado contra `platform/identity/errors.py:53` `PermissionDenied.__str__` e `tests/contract/console/test_incident_public_id_contract.py:167`), com `detail` como rede de segurança. Coberto em `trust-route.test.ts` ("forwards a permission refusal in the gateway's own words, naming the permission") e em `integration-panel-trust-form.test.tsx` ("shows the server's own reason, naming the missing permission, unchanged") |
| Fechar o laço | FEITO | uma declaração aceita chama `testNow(name)` de novo (`integration-panel.tsx:391`), o mesmo courier `/api/verify` que "Test again" já usa — declarar e ver Verified é um clique, não dois. Coberto por "re-tests the connection once a declaration is accepted, closing the loop in one click" |

## Achado: a mensagem de erro real do backend não é `{"detail": ...}`

Os couriers mais antigos (`credential/route.ts`, `verify/route.ts`) leem
`Reflect.get(Object(written), 'detail')` para extrair o corpo de erro.
Conferido contra `gateway/http/errors.py:113` `_envelope` — todo handler
instalado por `install_error_handlers` (`ApiProblem`, `PermissionDenied`,
`RequestValidationError`, e até `StarletteHTTPException`) produz
`{"error": {"type", "message", "correlation_id"}}`, nunca `{"detail": ...}`
sozinho. `test_incident_public_id_contract.py:167` confirma isso contra o app
real (`response.json()["error"]["message"]`). O courier novo (`trust/route.ts`)
lê `error.message` primeiro e cai para `detail` só como rede de segurança.
**Não mudei os couriers antigos** — não é escopo desta tarefa, e um deles
(`credential/route.ts`) tem os próprios testes travando o comportamento atual
com corpos `{"detail": ...}` fabricados; nomeado aqui para quem for mexer
neles a seguir, porque parece ser o mesmo tipo de fixture-concorda-com-o-código-
e-os-dois-discordam-do-backend que a casa já persegue noutro lugar.

## Achado: a baseline visual do painel está desatualizada, e não a toquei

`console/visual/screens.json` declara `integrations-panel-1440-light` em
`/integrations/alertmanager` — exatamente o painel onde o grupo novo agora
aparece para qualquer viewer com `integration.manage`. A captura commitada é
de antes desta mudança. **Não rodei `make console-visual-accept` nem toquei
nenhum PNG em `console/visual/baselines/`** — a regra contra evidência
manufaturada é explícita e nenhuma tarefa deste arquivo a nomeia. A baseline
precisa ser recapturada deliberadamente por quem possuir esse gate a seguir.
Nesta worktree o gate de conteúdo já não roda por outro motivo preexistente
(`console/.next/standalone/server.js is missing; run the build before
capturing`), então não há como observar o diff de pixel a partir daqui — só
nomear que ele existirá.

## As chaves de i18n que criei — dono desde esta tarefa, ambos os catálogos

Quatorze chaves novas, sob `catalogue.integrations.panel.trust.*`, em
`console/src/i18n/en.ts` e `console/src/i18n/pt-BR.ts`:

| Chave | EN | pt-BR |
|---|---|---|
| `...trust.heading` | Certificate trust | Confiança de certificado |
| `...trust.intro` | What this deployment accepts from the certificate this address presents. Declared for this address only — moving the address starts over. | O que este deployment aceita do certificado que este endereço apresenta. Declarado para este endereço apenas — trocar o endereço reinicia a decisão. |
| `...trust.fingerprintsLabel` | Pinned fingerprints | Fingerprints pinados |
| `...trust.fingerprintsHelp` | One SHA-256 fingerprint per line, copied from the node's own interface. A cluster lists one fingerprint per node in the same declaration. | Um fingerprint SHA-256 por linha, copiado da própria interface do nó. Um cluster lista um fingerprint por nó na mesma declaração. |
| `...trust.certificateLabel` | Certificate authority (PEM) | Autoridade do certificado (PEM) |
| `...trust.certificateHelp` | The authority the cluster minted for itself. Covers every node whose certificate chains to it — the form a cluster usually wants. | A autoridade que o cluster mintou para si mesmo. Cobre todo nó cujo certificado encadeia até ela — a forma que um cluster costuma preferir. |
| `...trust.submit` | Declare trust | Declarar confiança |
| `...trust.sending` | Declaring… | Declarando… |
| `...trust.saved` | Declared. Testing the connection now. | Declarado. Testando a conexão agora. |
| `...trust.refused` | The deployment refused it: | O deployment recusou: |
| `...trust.unreachable` | The deployment could not be reached. | Não foi possível alcançar o deployment. |
| `...trust.unverifiedHeading` | Accept without verifying | Aceitar sem verificar |
| `...trust.unverifiedReasonLabel` | Why | Por quê |
| `...trust.unverifiedReasonHelp` | Recorded with your name and the moment you accept, because giving up certificate verification is a decision, not a setting. | Registrado com seu nome e o instante da aceitação, porque abrir mão da verificação de certificado é uma decisão, não um ajuste. |

`tests/unit/i18n/` — 24 passed depois das duas edições, catálogo sem lacuna.

## Recursos compartilhados tocados nesta janela — declarados

| Recurso | O que fiz |
|---|---|
| `console/src/i18n/en.ts`, `console/src/i18n/pt-BR.ts` | **Editados** — dono desde esta tarefa, por instrução do orquestrador |
| `console/src/shell/routes.ts` | **Não tocado** — nenhuma rota nova; o painel já existia em `/integrations/[name]` |
| `console/visual/screens.json` | **Não tocado** — ver achado acima |
| Quatro arquivos de teste pré-existentes | `integration-panel.test.tsx`, `integration-panel-certificate.test.tsx`, `where-to-get-it-consistency.test.tsx`, `integration-direction.test.tsx` — cada um ganhou o bloco `trust: {...}` no seu `LABELS`, porque `IntegrationPanelLabels.trust` é campo obrigatório agora. `mayTrustUnverified` ficou **opcional, default `false`**, exatamente para não precisar tocar as dezenas de chamadas `<IntegrationPanel writable .../>` desses mesmos arquivos, que não têm opinião sobre essa permissão |

## Gates rodados nesta janela

| Gate | Comando | Resultado |
|---|---|---|
| Vermelho genuíno | `pnpm exec vitest run` dos dois arquivos novos, contra a implementação isolada por `git stash` | 10 failed / 2 passed, mais 1 arquivo que não carregou — mensagens na tabela acima |
| Vitest, os dois arquivos novos | `pnpm exec vitest run tests/unit/surfaces/integration-panel-trust-form.test.tsx tests/unit/surfaces/trust-route.test.ts` | **27 passed** — 26 do vermelho genuíno (tabela acima) mais 1 acrescentado depois ("does not let whitespace in the reason field stand in for a written one"), **verificado só verde**: a propriedade que ele trava já valia na implementação quando o caso foi escrito, então este caso específico não tem vermelho próprio — dito aqui em vez de contado junto com os outros doze |
| Vitest, os quatro arquivos pré-existentes tocados | mesmo comando, os quatro caminhos | **44 passed** |
| Vitest, `IntegrationsScreen` (a fiação) | `tests/unit/surfaces/integrations.test.tsx` | **41 passed** |
| Vitest, catálogo i18n | `tests/unit/i18n/` | **24 passed** |
| `console_gate typecheck` | `uv run python -m tools.console_gate typecheck` | **exit 0** |
| `console_gate lint` | `uv run python -m tools.console_gate lint` | exit 1 na primeira rodada — `@typescript-eslint/no-base-to-string` (`input.toString()` num tipo `Request \| URL`) e `no-unnecessary-type-assertion`, os dois no meu arquivo de teste. Corrigido (extração de URL por `instanceof URL`/`.url`; cast removido) → **exit 0** |
| Backend, o portão de permissão | `uv run pytest tests/unit/gateway/http/test_certificate_trust_write.py -v` | **15 passed** |
| Transversal, na fronteira do slot | `uv run python -m tools.spec_validation browser --feature specs_v7/070-confianca-de-certificado --test console/tests/e2e/transversal-rules.spec.ts` | **exit 0 — 45 passed, 7 skipped**, nenhuma falha nova |

Soma dos casos vitest tocados nesta janela: 27 + 44 + 41 + 24 = **136 passed**,
mais os 15 do backend e os 45 da transversal.

## O que ainda fica pendente depois desta janela

| Item | Estado | Dono |
|---|---|---|
| Baseline visual `integrations-panel-1440-light` | **desatualizada, nomeada, não tocada** — ver achado acima | quem possuir `make console-visual-accept` a seguir |
| **T030** — teste da invalidação por troca de endereço | PARCIAL, sem mudança nesta janela | próxima sessão |
| **T046 — `make verify` inteiro** | NÃO RODADO — do orquestrador | orquestrador |
| **T002, T047–T053 — evidência de staging** | NÃO INICIADO — do orquestrador | orquestrador |
| `console_gate test` (suíte vitest inteira do console) | NÃO RODADO por inteiro nesta janela — rodei os arquivos afetados e adjacentes (136 casos, todos verdes) em vez da suíte inteira, por custo de turno | orquestrador, se quiser a suíte inteira antes do merge |


---

# Quarta janela — o defeito de confiança viva, e o critério de pronto em staging

Retomada sobre `master` já mergeado (as três janelas anteriores estão nele),
worktree `.claude/worktrees/agent-a1534a5c1f5e20b21`, partindo de `10a329c`. A
worktree nasceu apontada para o commit raiz — o mesmo defeito de infraestrutura
que a 040 e a primeira janela desta feature já haviam registrado — e foi
reapontada com `git reset --hard master` antes de qualquer trabalho.

O gatilho desta janela foi uma validação real, feita pelo operador contra o
staging (`specs_v7/070-confianca-de-certificado/evidence/staging-2026-08-24.md`)
e não repetida aqui — a instrução foi explícita: **não escrever no staging**.

## O defeito: uma declaração escrita não decidia a próxima chamada

Medido nos dois sentidos contra o Proxmox real: declarar o pin errado deixava
`ok: True` (a chamada seguia passando); declarar o pin certo deixava
`ok: False` (a chamada seguia recusando) — em ambos os casos, sem reiniciar o
processo do proxy. Só a recomposição do processo aplicava a declaração.

Uma segunda instância do mesmo formato apareceu enquanto o operador rodava o
runbook da demonstração: o log de arranque do gateway mostra
`remediation.control_plane_bound` com `trust: system-trust-store` às 09:09,
e o pin foi declarado às 09:43 — mais de uma hora depois, sem o processo
reiniciar, o vínculo do plano de controle continuava reportando a âncora de
antes da declaração.

### Por que — lido no código, não hipotetizado

Duas composições independentes, cada uma congelando um valor de confiança no
momento em que rodou, sem nada que a fizesse rodar de novo por causa de uma
escrita:

1. **`platform/credentials/proxy/engine.py::forward`** consulta
   `self._trust` (`TrustRegistry`), que `gateway/proxy/composition.py:45`
   constrói vazio e `gateway/proxy/__main__.py` só preenche no arranque
   (`_serve`) e a cada 60 segundos (`_watch_configured_hosts`,
   `HOST_REFRESH_SECONDS = 60`). A escrita acontece em
   `gateway/http/routes/integrations.py` — **um processo diferente** do que
   serve `forward` em qualquer deployment `standard`/`enterprise` — e nada
   nela jamais tocava esse registro. A promessa que o próprio docstring da
   rota fazia ("a proxy applies it at the next cycle, without a restart")
   dependia inteiramente do ciclo de 60 segundos rodar sem falhar nunca.

2. **`gateway/http/control_plane.py::compose_control_plane`** é chamada
   **exatamente uma vez**, em `gateway/http/lifespan.py`, antes de
   `compose_remediation`. Ela lê a configuração, constrói um
   `ProxmoxWriteClient(trust=_trust_of(entry))` — um **valor congelado**, não
   um registro — e vincula (`control_plane.bind`). Não existe, em lugar
   nenhum, um segundo lugar que a chame de novo. Confirmado por varredura
   (`rg '\.trust\b' capabilities/tools/remediation gateway/http`): o campo
   `.trust` do cliente vinculado não é lido por mais ninguém além da própria
   linha de log que o imprime uma vez, no arranque — a própria docstring de
   `_trust_of` já dizia isto: "the decision is applied at the proxy's egress
   and never here — nothing in this module opens a socket." Ou seja, este
   segundo lugar **não aplica** verificação nenhuma (a aplicação real
   continua inteiramente em `gateway/proxy/sender.py`, e T042 continua
   valendo — ver Fase 9), mas ele **relata** uma âncora que para de ser
   verdade e nunca se corrige sozinho.

### O que eu procurei e não encontrei

Reli `_watch_configured_hosts` várias vezes para achar por que o ciclo de 60
segundos, que existe e está corretamente ligado ao mesmo objeto que o
remetente usa (`gateway/proxy/composition.py:45`, um único `TrustRegistry`
para os dois), pareceria nunca aplicar nada em staging. Não encontrei um bug
que explicasse "nunca, indefinidamente" a partir da leitura — `ConfigService`
constrói um resolvedor com cache vazio a cada chamada
(`platform/config_service/service.py:163`), então não há cache
interprocessos a suspeitar; `InjectionRuleRegistry.register` sobrescreve em
vez de levantar em registro duplicado, então religar as regras herdadas a
cada ciclo não é a causa. O que encontrei foi uma **classe** de defeito real,
independente da causa exata em staging: o corpo do ciclo, além da leitura,
**não estava protegido**. Uma exceção em `refresh_configured_hosts` ou em
`refresh_configured_trust` — de qualquer causa, presente ou futura — escapa
do `while True` sem ser capturada, e uma `asyncio.Task` que levanta uma
exceção não recebe uma segunda iteração: ela termina, em silêncio, com só um
aviso de "exception never retrieved" que ninguém observa. De fora do
processo, um ciclo morto é **indistinguível** de "isto precisa de um
reinício" — exatamente o sintoma medido. Corrigido (ver abaixo) e travado por
teste que reproduz exatamente essa forma de falha.

Nomeado porque é honesto nomear: não posso confirmar, a partir desta árvore,
se foi esta exceção silenciosa que aconteceu no pod validado ou se o pod
simplesmente rodava uma imagem anterior à composição da Fase 7. As duas
explicações são consistentes com o que foi medido, e a correção fecha a
classe de falha nas duas.

## O teste vermelho, e a mensagem exata

`tests/contract/credentials/test_certificate_trust_at_the_egress.py` — três
testes novos, escolhidos para expressar a propriedade nos termos do produto
("uma declaração escrita através do endpoint de confiança decide a próxima
chamada, sem reinício") e não da implementação. Vermelho confirmado **antes**
de qualquer correção, isolando a implementação com `git stash push -u` (só os
arquivos de produção; os testes ficaram de fora do stash) e restaurando com
`git stash pop` logo em seguida:

```
test_a_declaration_reaching_the_refresh_route_governs_the_very_next_call
  AttributeError: 'ProxyApp' object has no attribute 'set_trust_refresh'

test_an_address_nobody_declared_still_refuses_after_a_refresh
  AttributeError: 'ProxyApp' object has no attribute 'set_trust_refresh'
```

O terceiro (`test_a_refresh_request_against_an_app_with_no_hook_wired_is_refused_by_name`)
já passava antes da correção — **nomeado, não escondido**: sem rota nova
nenhuma, o `404` de fallback que `ProxyApp.__call__` já dava para qualquer
caminho não reconhecido cobria por acidente o mesmo caminho que a rota nova
ocupa agora. Ele deixou de ser coincidência no momento em que
`PROXY_TRUST_REFRESH_PATH` ganhou seu próprio ramo de despacho
(`platform/credentials/proxy/app.py:204`) — a partir daí, é este teste
especificamente que impede uma regressão onde o gancho não vinculado responda
200 por engano em vez de recusar por nome.

Confirmar vermelho custou uma segunda rodada: a primeira versão do terceiro
teste reusava a fixture `misnamed_node` como "endereço não declarado", mas
`named_node` e `misnamed_node` respondem ambos em `127.0.0.1` — só a porta
muda, e `TrustRegistry`/`host_of` descartam a porta de propósito
(`platform/credentials/proxy/trust.py:107`). O teste passou, mas pela razão
errada (`CertificatePinBroken`, pin que não bate, em vez de
`CertificateUntrusted`, endereço não declarado). Reescrito para declarar o
pin sob um endereço fictício diferente e testar contra `named_node` — a forma
que o próprio arquivo já usa em `test_one_node_changing_its_certificate_leaves_the_others_reachable`
para lidar com a mesma limitação das fixtures.

Um quarto teste, em `tests/unit/gateway/proxy/test_configured_hosts.py`
(`test_a_failure_partway_through_one_cycle_does_not_kill_the_loop`), trava a
correção de robustez do ciclo. Vermelho confirmado do mesmo jeito
(`git stash` só de `gateway/proxy/__main__.py`), com a mensagem exata:

```
RuntimeError: a transient failure mid-cycle, after the read already succeeded
    at gateway/proxy/__main__.py:198: refresh_configured_trust(app.engine.trust, trusted)
```

— ou seja, a exceção escapava exatamente da linha que ficava fora do
`try`/`except` antes da correção.

## A correção, e por que esta forma

Das três formas que a tarefa autorizava — reler a cada chamada, invalidar na
escrita, ou versionar — escolhi **invalidar na escrita**, com o ciclo
periódico como rede de segurança que nunca piora:

1. **`platform/credentials/proxy/app.py:174` `ProxyApp.set_trust_refresh`** —
   um gancho opcional (`None` por padrão), e **`:204`** um terceiro caminho
   ASGI, `PROXY_TRUST_REFRESH_PATH` (`config/constants/security.py:85`,
   `/internal/trust-refresh`). Sem corpo, sem credencial, sem abrir conexão
   com vendor nenhum: ele só dispara a mesma leitura que o ciclo de 60
   segundos já roda, mais cedo. Recusa por nome (**404**, `:249`) quando
   nenhuma composição vinculou o gancho — responder 200 para um refresh que
   não rodou seria o mesmo tipo de evidência manufaturada que esta casa já
   persegue numa camada acima.

2. **`gateway/proxy/__main__.py:110` `_refresh_trust_now`** — a mesma leitura
   (`_configured_egress`) e o mesmo `refresh_configured_trust` que o ciclo já
   usa, chamados sob demanda. `_serve` (`:151`) vincula o gancho ao mesmo
   `app`/`store` que já tinha em mãos, antes de qualquer outra coisa rodar.
   **Rejeitei** dar a `platform/credentials/proxy` acesso direto à
   configuração (o que tornaria a leitura possível por chamada, sem depender
   de gancho nenhum): isso cruzaria a fronteira de camada que já separa o
   mecanismo (`platform/credentials/proxy`, sem saber o que é um `ConfigNode`)
   de quem lê a árvore (`gateway/proxy`), e pagaria uma leitura de banco por
   chamada num caminho que os 462 `credential.resolve` do T049 mostram ser
   quente.

3. **`gateway/http/routes/integrations.py:854` `_refresh_credential_proxy_trust`**
   — depois da escrita e da auditoria (nunca antes: uma tentativa de avisar o
   proxy não pode virar razão para recusar uma declaração já validada), um
   `POST` de melhor esforço para o caminho novo, em `urllib.request` numa
   thread (`asyncio.to_thread`, `:965`) — a mesma técnica que
   `HttpProxyTransport` já usa para falar com este mesmo proxy, pelo mesmo
   motivo declarado no módulo dele: a lista de dependências deste deployment
   é curta e auditada de propósito, e não ganha um cliente HTTP assíncrono
   por isto. Toda falha — proxy inalcançável, tempo esgotado, um proxy mais
   velho que ainda não serve este caminho — é **engolida e registrada**
   (`integration.trust_refresh_not_confirmed`), nunca propagada: o ciclo de
   60 segundos continua sendo a garantia que já existia, e esta chamada só
   tenta adiantá-la. **Rejeitei** um sinalizador via Postgres
   (`LISTEN`/`NOTIFY`) — resolveria o mesmo problema com latência ainda menor,
   mas exigiria uma conexão persistente e sua própria reconexão dentro do
   processo do proxy, investimento maior do que esta correção pede.

4. **`gateway/http/control_plane.py`** — **não precisou mudar uma linha**. O
   defeito ali é que `compose_control_plane` só roda uma vez; a correção é
   rodá-la de novo, com a mesma função, no mesmo processo que já serve a
   escrita — `gateway/http/routes/integrations.py:967`, logo depois do
   `POST` de melhor esforço, também tolerante a falha (a recomposição nunca
   pode transformar uma escrita já persistida numa resposta de erro). Nenhum
   registro vivo novo, nenhum tipo novo: a mesma composição, chamada de novo,
   porque os dois lados — a escrita e o vínculo — sempre viveram no mesmo
   processo (`gateway/http`), diferente do proxy.

5. **Robustez do ciclo** (`gateway/proxy/__main__.py:198`
   `_watch_configured_hosts`) — o corpo inteiro do ciclo, não só a leitura,
   passou para dentro do `try`/`except` que já existia. Sem mudar o que é
   lido, aplicado, ou decidido: só onde a rede de segurança termina.

Nenhuma das cinco peças abre uma segunda verificação de certificado, nenhuma
introduz um booleano, e nenhuma toca `gateway/proxy/sender.py` — T042 (Fase 9)
continua garantindo que só ele constrói um contexto que não verifica, e a
suíte confirma isso sem alteração.

## Gates rodados nesta janela

| Gate | Comando | Resultado |
|---|---|---|
| Vermelho genuíno, os três testes de contrato | `git stash` de produção, `pytest -k "refresh_route or refused_by_name or nobody_declared_still_refuses"` | 2 failed (`AttributeError`), 1 passed (por acidente, nomeado acima) |
| Verde, arquivo de contrato inteiro | `pytest tests/contract/credentials/test_certificate_trust_at_the_egress.py -v` | **19 passed**, os 16 anteriores sem edição nenhuma |
| Vermelho genuíno, robustez do ciclo | `git stash` de `gateway/proxy/__main__.py`, `pytest -k failure_partway` | 1 failed — `RuntimeError` na linha exata fora do `try` antigo |
| Verde, arquivo de hosts inteiro | `pytest tests/unit/gateway/proxy/test_configured_hosts.py -v` | **15 passed**, os 14 anteriores sem edição nenhuma |
| Regressão, tudo que este defeito toca | `pytest tests/contract/credentials/ tests/unit/gateway/proxy/ tests/unit/platform/credentials/ tests/unit/gateway/http/test_certificate_trust_write.py tests/unit/gateway/http/test_control_plane_composition.py tests/architecture/test_one_place_can_stop_verifying.py` | **292 passed** |
| `make check-imports` | | 7 kept, 0 broken |
| `make check-constants` | | exit 0 |
| `make check-deps` | | exit 0 |
| `make check-protocols` | | exit 0 |
| `ruff check` / `ruff format --check` | nos sete arquivos tocados | limpo nos dois |
| `make typecheck` (mypy, árvore inteira) | | **Success: no issues found in 1323 source files** |
| `make verify` inteiro | ver T046 abaixo | ver T046 abaixo |

## Fase 10 — o critério de pronto em staging (T047–T052), conferido contra a evidência

Read-only, como a fase manda: nada nesta janela escreveu no hipervisor nem no
staging. `T002`, `T047` e a linha de base já estavam marcadas antes desta
janela; as cinco abaixo, o operador executou pessoalmente contra o Proxmox
real e registrou em
`specs_v7/070-confianca-de-certificado/evidence/staging-2026-08-24.md`
("a evidência"), que esta janela leu e não repetiu.

| Peça | Estado | Detalhe |
|---|---|---|
| T002 — estado de partida | **FEITO (achado, não rotulado como T002)** | a evidência, seção "O que estava bloqueando" (`evidência:7-18`): veredito da integração recusando, mensagem exata *"Neither the credential proxy nor any configured Proxmox node answered."*, e a contagem implícita de `estate_resources` é a mesma "zero" que T049 cita como o "antes" |
| T047 — declarar o fingerprint primeiro | FEITO | já marcado antes desta janela; a evidência confirma que o caminho do fingerprint funcionou (não precisou da terceira mensagem) |
| T048 — verificar a integração | **FEITO, com uma lacuna nomeada** | evidência:20-29: veredito `ok: True` e mensagem `"Proxmox accepted the token."`, ambos verbatim. **A captura de tela do painel não está entre os artefatos** — o diretório `evidence/` só contém o arquivo `.md`, sem imagem. Registrado aqui em vez de marcado como coberto por inteiro: a captura é a única das três coisas que o item pede que a evidência escrita não carrega |
| T049 — a descoberta povoou o estate | FEITO | evidência:31-47: 108 recursos, `complete: True` em 87 chamadas; `select count(*)...` foi de zero (T002) para **100**; o sujeito da demonstração da 080 (CT122 `redis`) está visível nomeado |
| T050 — a aceitação registrada | FEITO | evidência:49-73: o principal autenticado é `local-admin` (não o agente), o instante `2026-08-24 09:43:22`, a forma `pinned-fingerprint`, os endereços `["192.168.68.159"]`; a razão está corretamente ausente (só a forma `unverified` a exige); cada um dos 462 `credential.resolve` carrega o fingerprint contra o qual verificou |
| T051 — o pin quebrado de propósito | FEITO | evidência:75-90: fingerprint de 64 zeros declarado, chamada provocada, a mensagem contém **os dois** fingerprints (esperado e observado, no formato com dois-pontos que a interface do hipervisor mostra), não contém a frase de nó que não respondeu, e afirma explicitamente as duas coisas que não aconteceram ("nothing fell back to the system trust store and nothing stopped verifying"). Pin correto restaurado e `ok: True` confirmado depois |
| T052 — nada sensível vazou | **FEITO no banco, lacuna nomeada nos logs do pod** | evidência:92-97: a consulta a `audit_events` por `BEGIN CERTIFICATE`/`PRIVATE KEY`/`PVEAPIToken` retornou **0**, exatamente como o item pede. **"Repetir a varredura nos logs do pod do proxy" não está registrado na evidência** — a segunda metade do item, distinta da primeira por vírgula, não tem o mesmo verbatim que a primeira |

As duas lacunas nomeadas (a captura de tela de T048, a varredura de log de
T052) não mudam o veredito de nenhuma das duas tarefas — o fato de segurança
que cada uma existe para provar está coberto pelo resto do que a evidência
registra — mas ficam nomeadas em vez de presumidas, porque marcar as duas
tarefas como inteiramente cobertas sem dizer isso seria exatamente o defeito
que esta casa já registrou uma vez: uma caixa marcada por uma claúsula que
ninguém checou.

As sete falhas pré-existentes de T001 (documentos de planejamento passando a
ser committed, e o console sem build nesta worktree) não mudaram de forma:
continuam fora do alcance de `platform/credentials/proxy`, `gateway/proxy`,
`integrations/proxmox` e `platform/config_service`, e T046 (abaixo) mede
contra elas pelo nome, não pelo número.

## T053 — o relatório final

### As chaves de i18n e os textos em inglês, como bloco

**Nenhuma chave nova nesta janela.** A correção inteira é de backend/proxy —
nenhum arquivo sob `console/` foi tocado. As catorze chaves que a terceira
janela já criou, sob `catalogue.integrations.panel.trust.*` em
`console/src/i18n/en.ts` e `console/src/i18n/pt-BR.ts`, continuam sendo as
únicas que esta feature introduziu; a tabela completa está na seção da
terceira janela acima e não muda aqui.

### A permissão nova, e a quem foi concedida

`Permission.INTEGRATION_TRUST_UNVERIFIED` (`platform/identity/permissions.py:81`).
Distinta de `INTEGRATION_MANAGE`: pinar um fingerprint ou fornecer uma
autoridade **não** exige esta permissão — apenas `INTEGRATION_MANAGE`, porque
as duas formas *estreitam* a âncora em vez de abri-la. Aceitar sem verificar
**exige as duas**: `INTEGRATION_MANAGE` sempre, e
`INTEGRATION_TRUST_UNVERIFIED` só quando a forma é `unverified`
(`gateway/http/integration_endpoints.py:153` `StampedTrust.refuse_unless_permitted`).
Concedida ao conjunto do papel `Role.ADMIN` e acima
(`platform/identity/permissions.py:196`) — nenhum papel que só opera
integrações a possui, de propósito: abrir mão de verificação de certificado é
uma decisão administrativa, não uma tarefa operacional do dia a dia.

### As decisões de forma que a implementação exigiu

**Da fase de aplicação (primeira janela).** A pinagem usa `CERT_NONE` dentro
de `_PinCheckingConnection.connect` (`gateway/proxy/sender.py:180`), porque a
biblioteca padrão não expõe o certificado do par por cima de `urlopen` — o
pin substitui a verificação de identidade em vez de somar-se a ela, e a
recusa acontece antes de `request()` escrever um byte. Nomear o certificado
observado numa recusa custa um segundo handshake de diagnóstico, que não
escreve nada e continua verificando a cadeia quando o problema é só o nome.
Detalhado por inteiro na seção da primeira janela (T017).

**Desta janela.** Entre reler a cada chamada, invalidar na escrita, ou
versionar, escolhi invalidar na escrita, com o ciclo periódico de 60 segundos
como rede de segurança que nunca piora — nunca melhor que "sem reinício",
nunca pior do que já era. O gancho novo (`ProxyApp.set_trust_refresh`) é
opcional e recusa por nome (404) quando nada o vincula, em vez de responder
sucesso por um refresh que não rodou. A chamada de `gateway/http` para o
proxy é de melhor esforço, depois da escrita e da auditoria, nunca antes —
uma tentativa de avisar o proxy não pode transformar uma declaração já válida
numa recusa. E a recomposição do plano de controle reusa a função existente
verbatim, porque o defeito ali nunca foi a lógica — foi só rodá-la de novo.
Detalhado por inteiro na seção desta janela, acima.

### O que ficou como pergunta para o operador

1. **A causa exata, em staging, do "nunca sem reiniciar".** Duas explicações
   são consistentes com o que foi medido — uma exceção silenciosa matando o
   ciclo (agora impossível, travada por teste) ou uma imagem do proxy
   anterior à composição da Fase 7 — e não há como distinguir as duas a
   partir desta árvore. A correção fecha as duas classes de qualquer forma,
   mas o operador é quem pode olhar o histórico de deploy do pod e dizer qual
   foi.

2. **Se o novo caminho `/internal/trust-refresh` precisa de alguma coisa além
   da fronteira de rede que já protege `/internal/forward` e
   `/internal/health`.** Ele não carrega credencial, não abre conexão com
   vendor, e só dispara uma releitura que o ciclo já faz sozinho — tratei-o
   como pertencente ao mesmo modelo de confiança dos outros dois caminhos
   internos. Se algum deployment expõe a porta do proxy além da política de
   rede que os dois já pressupõem, isso já seria verdade para
   `/internal/forward` primeiro, e é uma decisão de política que não me cabe
   fechar sozinho.

3. **Se o mesmo padrão — recompor o plano de controle depois de uma escrita —
   deve se estender a outras escritas da mesma integração**, como trocar o
   endereço pela rota normal (`PUT /v1/integrations/{name}`, fora desta
   feature). Essa escrita também deixa `compose_control_plane` com um
   endereço congelado desatualizado, e a mesma correção serviria — mas é uma
   rota que esta feature não possui, e nomeá-la aqui é a forma de não
   escondê-la nem de resolvê-la sem que o dono da rota decida.

4. **A baseline visual `integrations-panel-1440-light`**, já nomeada pela
   terceira janela como desatualizada e não tocada — continua assim; esta
   janela não mexeu em console e não tinha como recapturá-la.

5. **T030** (teste da invalidação por troca de endereço) segue **PARCIAL**,
   como a segunda e a terceira janela já registraram — sem mudança nesta
   janela, que não tocou esse caminho.
