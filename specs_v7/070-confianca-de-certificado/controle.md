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
