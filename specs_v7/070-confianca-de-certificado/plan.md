# Implementation Plan: Confiança de certificado

**Branch**: `feat/v7-070-confianca-de-certificado` | **Date**: 2026-08-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v7/070-confianca-de-certificado/spec.md`

**Referência visual (DoD)**: nenhuma tela nova — ver o cabeçalho da spec. O
console recebe campos declarados no painel de integração e a frase certa na
recusa; não há mockup nem acceptance spec Playwright próprio.

## Summary

Ligar `CertificateTrust` — o mecanismo que já existe, com as três formas
documentadas — do schema da integração até o egress do proxy de credencial, que
é onde o handshake TLS acontece e portanto o único lugar onde a decisão tem
efeito. Como o efeito é enfraquecer, redirecionar ou fortalecer verificação de
certificado, o trabalho é uma mudança de fronteira de segurança: o plano decide
quem pode, para que endereço vale, o que fica registrado e o que acontece quando
o certificado muda, **antes** de decidir onde o campo mora.

Quatro peças, nesta ordem de dependência:

1. **O vocabulário desce um tier.** O tipo de confiança passa a viver ao lado do
   proxy, e o pacote Proxmox continua sendo quem o declara — exatamente o
   arranjo que a regra de injeção já tem hoje (`InjectionRule` mora no proxy, o
   pacote do vendor a declara).
2. **O carregador é o mesmo do endereço.** A declaração viaja pela árvore de
   configuração, ao lado do `base_url` da entrada de integração, é escrita pela
   mesma rota que escreve o endereço, e é relida pelo mesmo ciclo periódico que
   reconstrói a allow-list.
3. **A aplicação é no remetente.** O remetente do proxy deixa de ter **um**
   contexto TLS e passa a resolver o contexto por endereço a partir do registro
   de confiança que a composição lhe entregou.
4. **A recusa vira de primeira classe.** Uma razão de erro própria, três frases
   distinguíveis, e a linha do remetente que hoje achata `ssl.SSLError` em
   "upstream inalcançável" deixa de ser onde as duas se confundem.

## Technical Context

**Language/Version**: Python 3.12+ (proxy, integrações, gateway); TypeScript
(console, um painel)

**Primary Dependencies**: biblioteca padrão. `ssl` e `urllib` já são o que o
remetente usa, e a razão declarada para isso — a menor árvore de dependências do
deployment mora no processo que guarda os segredos — vale ainda mais para o
componente que passa a decidir o que confiar. Nenhuma dependência nova.

**Storage**: sem migração. A declaração é um documento na árvore de
configuração, que já é JSONB versionado com proveniência; a auditoria usa a
tabela de eventos que já existe.

**Testing**: pytest — contrato do proxy para as três formas mais o pin quebrado,
unit da validação do documento, unit da resolução do contexto por endereço,
contrato da rota de escrita e da permissão, arquitetura para a unicidade do
lugar que pode não verificar. Vitest para o painel. Sem Playwright novo.

**Target Platform**: backend Python; staging k3s com o Proxmox real do homelab.

**Project Type**: mudança de fronteira de segurança, atravessando três tiers.

**Performance Goals**: N/A no caminho de chamada. Uma exigência de forma: o
contexto TLS por endereço é construído uma vez e reaproveitado, não por
requisição — construir um contexto por chamada é custo de handshake que a
feature não precisa pagar.

**Constraints**: `platform/` não importa `integrations/`. O tipo tem de descer
ou ser duplicado, e duplicar um tipo de segurança é como as duas metades passam
a discordar. O proxy não pode ficar sem servir enquanto a configuração está
ilegível. Nenhum segredo em log ou auditoria.

**Scale/Scope**: um vendor declarando (Proxmox), um carregador genérico, um
lugar aplicando.

## Constitution Check

*GATE: precisa passar antes da execução. Reconferir ao final.*

Contra a constituição **como ela estará depois da 000** (2.2.0).

| Artigo | Como este plano satisfaz |
|---|---|
| I — Evidência sobre asserção | A prova não é teste verde: é o Proxmox real do staging saindo de Degraded, o estate deixando de estar vazio, e as consultas de banco escritas na spec. O pin quebrado é provado provocando-o, não descrevendo-o. |
| II — Autonomia limitada | Não toca laço, orçamento nem limite de autonomia. |
| III — Leitura por padrão | Nada nesta feature escreve no hipervisor. A validação de staging é descoberta, que é leitura. |
| IV — Segredo nunca chega ao agente | **É o artigo em jogo.** A feature move a fronteira, e o teste é se ela a move para melhor. Nenhum segredo passa a viajar: um certificado público não é segredo, uma chave privada é recusada nominalmente, e o token continua entrando só na injeção do proxy. O que muda é que o proxy passa a poder verificar *menos*, num caminho que exige permissão dedicada, razão e registro — e em **um** lugar, com teste de arquitetura provando que é um só. Nenhuma capacidade lê nem escreve a declaração. |
| V — Um runtime canônico | Não toca runtime. |
| VI — Neutralidade de provedor | Não toca provedor de modelo. |
| VII — Aprendizado é medido | Não toca aprendizado. |
| VIII — Arquitetura em camadas | O tipo de confiança desce para o tier do proxy pelo mesmo motivo que a regra de injeção mora lá: o proxy precisa do vocabulário e não pode importar o vendor. O pacote Proxmox continua declarando. A composição no tier do gateway é quem junta os dois, que é o que aquele tier existe para fazer. As checagens de contrato de import são gate. |
| IX — Capacidades declaradas | Nenhuma capacidade nova, e uma proibição a mais: nenhuma capacidade toca confiança. O pacote Proxmox mantém sua paridade — sua documentação passa a descrever o caminho de configuração além da forma programática. |
| X — O operador é dono dos dados | A declaração é do operador, fica no deployment dele, e é legível e removível por ele. Nada sai do host. |
| XI — Datastore único | Sem tabela nova e sem migração. Configuração e auditoria são as portas que já existem. |
| XII — Test-first, rastreado | O vermelho de cada uma das quatro peças aterrissa antes da implementação e é registrado. O contrato do proxy para os três modos é o primeiro a existir. |
| XIII — Idioma e atribuição | Todo arquivo committed em inglês, sem identificador de planejamento, sem número de artigo, sem nome de projeto de origem. |
| XIV — Composto ou não foi entregue (2.2.0) | Declarado abaixo, com nome de arquivo e função. |

### Qual composition root constrói isto

Uma só, e ela é curta:

- **`gateway/proxy/composition.py::build_proxy_engine`** constrói o remetente.
  Hoje ele chama `HttpOutboundSender()` sem argumento, e o remetente monta seu
  único contexto a partir do ambiente. Depois desta feature ele recebe o
  registro de confiança, e é a única maneira de o remetente conseguir um.
- **`gateway/proxy/__main__.py::_watch_configured_hosts`** é o ciclo que já
  reconstrói a allow-list a partir da árvore de configuração. Ele passa a
  reconstruir também a confiança, com a mesma semântica de reconstruir em vez de
  acumular. `build_proxy_app` → `build_proxy_engine` é o caminho que o processo
  do proxy (`python -m gateway.proxy`, o pod `proxy` do staging) percorre no
  arranque; este ciclo é o que mantém a coisa viva depois.
- **`gateway/http/routes/integrations.py`**, na rota que já grava a credencial e
  o endereço, é onde a declaração é escrita, com a permissão checada e o evento
  de auditoria emitido.

A prova de composição não é teste de unidade: é uma chamada real através do
proxy do staging chegando ao Proxmox real, e a auditoria do banco de staging
mostrando a aceitação. Nenhuma tarefa de comportamento fecha com "verde no
harness".

### Complexity Tracking

Uma coisa fica mais complexa e vale a sentença: o remetente deixa de ter um
contexto e passa a ter uma resolução por endereço. É complexidade real e é o
preço de a confiança ser por endereço em vez de por processo. A alternativa —
um contexto por processo, configurado por ambiente — é o que existe hoje, e é
exatamente o que não consegue expressar "confio neste nó e em nenhum outro".

## Project Structure

### Documentation (this feature)

```text
specs_v7/070-confianca-de-certificado/
├── spec.md
├── plan.md                    # este arquivo
├── tasks.md
├── controle.md                # do implementer, não deste plano
└── checklists/requirements.md
```

### Source Code (repository root)

```text
platform/credentials/proxy/trust.py          # novo: o vocabulário, no tier do proxy
platform/credentials/proxy/errors.py         # razão de erro nova + as três frases
platform/credentials/proxy/audit.py          # dois escalares a mais no registro fixo
platform/credentials/proxy/engine.py         # a razão nova atravessa sem virar outra coisa
platform/config_service/schema/integrations.py   # a seção de confiança na entrada
platform/identity/permissions.py             # a permissão dedicada e seu papel
integrations/proxmox/certificates.py         # passa a declarar sobre o vocabulário comum
integrations/proxmox/verifier.py             # o braço novo da tabela de mensagens
integrations/proxmox/docs.md                 # o caminho de configuração, além do programático
gateway/proxy/sender.py                      # resolução de contexto por endereço
gateway/proxy/hosts.py                       # a confiança lida da configuração, como o host
gateway/proxy/composition.py                 # o registro entregue ao remetente
gateway/proxy/__main__.py                    # o ciclo reconstrói host e confiança
gateway/http/integration_endpoints.py        # escrita da declaração + o campo na cópia da entrada
gateway/http/routes/integrations.py          # permissão, escrita, auditoria
gateway/http/deep_verification.py            # a linha que relata a forma em vigor
config/constants/security.py                 # ação de auditoria e tipo de recurso
console/src/surfaces/integration-panel.tsx   # campos declarados + a frase da recusa
tests/…                                      # ver tasks.md
```

**Structure Decision**: nenhum diretório novo. Um módulo novo no proxy, e o
resto são pontos existentes recebendo o dado que já deveriam ter.

## As decisões de fronteira

Cada uma é uma escolha entre alternativas reais, e o rationale é o que faz a
escolha sobreviver a quem vier depois.

### 1. Quem pode aceitar um certificado não verificado — permissão dedicada

**Decisão**: uma permissão nova, `integration.trust_unverified`, distinta de
`integration.manage`. Declarar fingerprint pinado ou fornecer certificado exige
apenas `integration.manage`, como escrever o endereço já exige. Aceitar não
verificado exige a permissão nova, concedida ao papel administrativo e acima —
**não** ao papel que opera integrações.

**Rationale**. Pinar e fornecer não enfraquecem nada: eles *redirecionam* a
verificação para uma âncora mais estreita que o repositório do sistema, o que é
estritamente mais forte para um host que emite o próprio certificado. Exigir
permissão de administrador para isso empurraria o operador para o caminho pior
justamente porque o melhor dá trabalho. Já não verificar é a única operação do
produto que reduz uma garantia de segurança sem nada em troca além de
conveniência, e ela merece um portão que não seja o mesmo que se abre para
digitar um endereço.

**Alternativa recusada**: reutilizar `config.write`. Ela existe e é ampla; quem
a tem edita a árvore inteira. Aceitar não verificado sem que a auditoria consiga
distinguir "editou configuração" de "renunciou à verificação de um endereço" é
perder a única distinção que interessa numa revisão.

**Consequência de forma**: o verbo `trust_unverified` não é um verbo de leitura,
então a derivação existente já a trata como escrita. Isso é a propriedade a
conferir num teste, não a assumir.

### 2. Por vendor ou por endereço — por endereço

**Decisão**: a confiança vale para os endereços que a declaração nomeia. Ela é
escrita na entrada de integração — que é onde o endereço já mora — e o que ela
autoriza é aquele endereço, não o vendor.

**Rationale**. O certificado é apresentado por um host. Uma aceitação por vendor
cobriria silenciosamente um endereço acrescentado meses depois, por outra pessoa,
sem que ninguém decidisse nada — que é precisamente a falha que a reconstrução
periódica da allow-list já foi escrita para evitar ("uma permissão que sobreviveu
à decisão que a concedeu"). Fazer a confiança seguir uma regra mais frouxa que a
allow-list, no mesmo documento e no mesmo ciclo, seria incoerente com o
componente que a aplica.

**Consequência que precisa estar escrita**: um certificado de autoridade
fornecido **cobre** todo endereço cuja cadeia ele valide, e num cluster isso é o
cluster inteiro. Isso não contradiz a regra: quem forneceu a autoridade decidiu
confiar no que ela emite, e é essa a razão de o PEM ser a forma recomendada para
cluster e o fingerprint ser a forma recomendada para nó único.

**Consequência operacional**: trocar o endereço invalida a declaração feita para
o anterior. Sem isso, "aceitei não verificar o meu laboratório" viraria "aceito
não verificar o que quer que esteja neste campo amanhã".

### 3. O que a auditoria grava

Na escrita, um evento com: o principal autenticado, o instante do servidor, a
integração, os endereços, a forma (`system-trust-store` · `pinned-fingerprint` ·
`supplied-certificate` · `unverified`), os fingerprints quando há, e a razão
quando há. Nunca o PEM: um certificado inteiro numa trilha de auditoria é volume
que não prova nada que o fingerprint não prove, e o fingerprint é o que o
operador compara com o que o nó mostra.

No uso, a linha que a resolução de credencial já escreve ganha dois escalares: a
forma em vigor e o fingerprint quando a forma é pinada. Continuam sendo campos
declarados num registro fechado — não há caminho para um ponto de chamada
acrescentar um campo, e essa é a propriedade que impede um corpo de requisição
de escorrer para a tabela.

Na recusa, a mesma linha, com desfecho negado, a razão nova, e o fingerprint
**observado**. Uma recusa é auditada tão alto quanto um sucesso pelo mesmo
motivo de sempre: é o evento que alguém precisa encontrar.

### 4. Pin quebrado

Recusa nomeando os dois fingerprints, e mais nada acontece. Sem degradação para
o repositório do sistema, sem degradação para não verificado, sem adoção
automática do novo. A mensagem carrega o observado para o operador **comparar**
com o que o nó mostra na interface do próprio Proxmox; adotá-lo é uma escrita
nova, com a mesma permissão e o mesmo registro da primeira.

### 5. Proxmox-first ou carrier genérico — genérico no carregador, Proxmox na declaração

**Decisão**: o vocabulário, o campo de configuração, a resolução de contexto e a
razão de erro são genéricos — valem para qualquer integração com endereço. A
declaração, a documentação, a mensagem de verificação e o painel são do Proxmox,
e **nenhum outro pacote de integração é alterado nesta feature**.

**Rationale**. A fronteira é do proxy, não do Proxmox: o remetente é um só e
atende todos os vendors. Um carregador específico do Proxmox seria um segundo
carregador na primeira vez que outro appliance self-hosted aparecesse, e dois
caminhos para enfraquecer verificação é o que esta feature existe para não
deixar acontecer. Ao mesmo tempo, habilitar catálogo inteiro é entregar
superfície que ninguém validou. O genérico custa quase nada aqui porque o
carregador já é genérico — é a mesma entrada de configuração que carrega
`base_url` para todo mundo.

**Como isso não vira sobre-entrega**: o critério de pronto é o Proxmox real
conectando. Nenhum outro pacote ganha campo, texto ou teste.

### 6. Onde o tipo mora

**Decisão**: `platform/credentials/proxy/trust.py` passa a conter o tipo, e
`integrations/proxmox/certificates.py` continua exportando o nome que hoje
exporta, com o padrão do Proxmox e a prosa que explica por que o padrão é o
seguro. Nada que importa `integrations.proxmox` hoje quebra, e os testes de
transporte que já existem continuam valendo.

**Rationale**. O tier do proxy não pode importar o tier das integrações; o tipo
tem de descer ou ser duplicado. É exatamente a situação da regra de injeção, e a
resposta já está escrita naquele módulo: o vocabulário mora no proxy, a
declaração mora no vendor, e a composição junta. Duplicar um tipo de segurança é
como as duas metades acabam discordando sobre o que "verificado" significa.

### 7. As três mensagens, e por que são três

Certificado não confiado, pin quebrado e nome que não confere levam a três ações
diferentes do operador: declarar confiança, comparar com o nó, e corrigir o
endereço (ou pinar em vez de fornecer). Achatá-las em uma é reproduzir em escala
menor o defeito que a feature corrige. E nenhuma das três pode virar a de rede
fora — o achatamento de hoje acontece numa linha só, onde o remetente captura
`ssl.SSLError` junto com `URLError` e `OSError` e ergue "upstream inalcançável"
para todas.

A quarta mensagem, a de rede, fica **exatamente** como está.

## Riscos, e o que fazer com cada um

- **Nome de host que não confere no staging.** O certificado do Proxmox nomeia o
  nó; se a integração estiver apontada para um endereço IP, o PEM valida a cadeia
  e falha o nome. É a terceira mensagem, e é provável que apareça no primeiro
  teste real. O fingerprint pinado não sofre disso porque o pin substitui a
  identidade. **Ação**: tentar o fingerprint primeiro no staging, e tratar a
  mensagem de nome como caminho esperado e testado, não como surpresa.
- **Pinagem com a biblioteca padrão.** Verificar fingerprint exige olhar o
  certificado do par depois do handshake, o que a interface de alto nível não
  oferece diretamente. É trabalho conhecido e local ao remetente, e é o único
  ponto da feature com risco de implementação. **Ação**: é a primeira coisa a
  provar com teste, contra um servidor TLS local com certificado gerado no
  próprio teste — sem rede, sem fixture binária no repositório. Se o caminho se
  mostrar feio, a decisão de forma é registrada no `controle.md`, nunca resolvida
  com "então não verifica".
- **A cópia da entrada de configuração descarta campo que não conhece.** A função
  que reescreve a lista de integrações copia um conjunto fixo de campos; um campo
  novo que não entre nessa lista é apagado no primeiro salvamento de endereço.
  **Ação**: é uma tarefa explícita e tem teste próprio — gravar confiança, depois
  gravar endereço, e conferir que a confiança sobreviveu.
- **Reconstruir a allow-list e a confiança em ciclos diferentes.** Duas verdades
  derivadas do mesmo documento por dois caminhos é como elas discordam.
  **Ação**: um ciclo só, uma leitura só, os dois reconstruídos juntos.
- **Alargar sem querer o afrouxamento de conformidade.** O afrouxamento que hoje
  acompanha um bundle nomeado tem escopo declarado e razão escrita. Ele acompanha
  o certificado fornecido pela configuração e nada mais — em particular não
  acompanha o repositório do sistema. **Ação**: teste que prova que o contexto
  padrão continua tão estrito quanto a biblioteca é.
- **Sandbox.** Não muda nada. **Ação**: um teste que prova que não mudou, porque
  "não mexemos" não é evidência.

## Sequência

1. Vocabulário no tier do proxy, com o Proxmox continuando a declarar (vermelho
   dos testes de transporte existentes: têm de continuar verdes sem alteração).
2. Razão de erro e as três frases, com o contrato do proxy vermelho.
3. Resolução de contexto por endereço no remetente, com contrato dos três modos
   e do pin quebrado vermelho, contra servidor TLS local.
4. Seção de confiança no documento de configuração, com a validação vermelha.
5. Permissão dedicada, com o contrato da rota vermelho.
6. Escrita, auditoria e sobrevivência do campo, com teste vermelho.
7. Composição: registro entregue ao remetente, ciclo reconstruindo os dois.
8. Verificador e painel: as frases certas onde o operador lê.
9. Documentação do pacote, teste de arquitetura da unicidade, `make verify`.
10. Staging: declarar, verificar, povoar, quebrar o pin de propósito, consultar o
    banco.
