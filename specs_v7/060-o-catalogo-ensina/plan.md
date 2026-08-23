# Implementation Plan: O catálogo ensina — todo campo diz o que criar e o que marcar

**Branch**: `feat/v7-060-o-catalogo-ensina` | **Date**: 2026-08-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v7/060-o-catalogo-ensina/spec.md`

**Referência visual (DoD)**: nenhum mockup novo. As alegações normativas da spec
são o contrato visual, codificadas em
`console/tests/e2e/catalogue-teaches.acceptance.spec.ts`, confirmado vermelho
antes da implementação. Medição em **1920×1080**. A tela visual já registrada do
slide-over (`/integrations/alertmanager`) muda de conteúdo e sua baseline é
reaceita deliberadamente.

## Summary

Quatro trabalhos, um por metade do defeito, mais o gate que impede a regressão.

1. **Conteúdo.** Os 40 campos de credencial dos 15 vendors embarcados passam a
   carregar a orientação que o seu tipo admite: permissão mínima nos 21 secretos,
   guia nos 40. Nove permissões mínimas e 29 guias são pesquisa real na
   documentação de cada fornecedor, com a fonte citada no documento do pacote.
2. **Gate.** A verificação de integrações — a mesma que já reprova nomeando
   vendor e artefato — ganha uma regra que reprova nomeando vendor e campo.
   Presença e forma; nunca alcançabilidade.
3. **Duas telas, uma frase.** Cada vendor declara no seu pacote a frase "onde
   obter", o catálogo servido a carrega, e as duas telas que pedem credencial —
   o slide-over da integração e o passo do primeiro acesso — a mostram lendo a
   mesma declaração.
4. **Documentação servida.** O documento que cada pacote já carrega ganha um
   endereço no gateway e uma seção no slide-over, renderizada pelo renderizador
   de markdown que o slot anterior já introduziu.

E, junto, a metade de texto do outro item do backlog: a recusa de mandar
credencial por conexão não cifrada passa a ter frase própria — o esquema e as
duas saídas — sem mudar classificação nem comportamento.

**O que esta feature não é**: não é uma mudança de mecanismo. Toda a tubulação
existe e está ligada. `CredentialField` já declara `min_scope` e `guide_url`;
`CredentialFieldView` no gateway já os serve; `fieldsOf` no console já os mapeia;
`CredentialField` (o componente) já renderiza a linha de escopo e o link de guia
quando existem; `refuse_credential_in_clear` já recusa. O que falta é conteúdo,
uma frase por vendor, um endereço, uma seção de tela, uma classe de erro e um
gate. Isso é o que torna a feature grande em número de tarefas e pequena em
risco.

## Technical Context

**Language/Version**: Python 3.12 (schemas de vendor, catálogo, rota de
documentação, proxy de credencial, gate); TypeScript (console — slide-over,
passo do primeiro acesso, catálogo de mensagens)

**Primary Dependencies**: `integrations/<vendor>/schema.py` (os 15),
`integrations/<vendor>/docs.md` (os 15), `integrations/_base/schema.py`
(helpers `secret`/`public`/`endpoint`), `integrations/_catalogue/entry.py`
(`IntegrationProfile`), `integrations/_catalogue/validation.py` (o relatório de
paridade, que já sabe onde o documento de cada pacote está),
`gateway/http/routes/integrations.py`, `gateway/http/security/gateway_routes.py`,
`platform/credentials/proxy/errors.py`, `platform/credentials/proxy/egress.py`,
`tools/verify_integrations.py`, `console/src/surfaces/integration-panel.tsx`,
`console/src/surfaces/screens/integrations.tsx`,
`console/src/surfaces/first-run/integrations.tsx`,
`console/src/surfaces/screens/first-run.tsx`, `console/src/i18n/*.ts`

**Storage**: N/A. Nada é gravado por esta feature. Nenhuma migração.

**Testing**: pytest (contrato do catálogo, contrato da rota de documentação,
unidade do gate, unidade da recusa em claro, segurança de permissão de rota);
vitest (`console/tests/unit/surfaces/`); Playwright
(`console/tests/e2e/catalogue-teaches.acceptance.spec.ts` + transversal);
aceitação visual (`console/visual/screens.json`)

**Target Platform**: gateway Python + console web, com aceitação também contra o
staging k3s

**Project Type**: preenchimento de catálogo + um endereço novo + um gate novo

**Performance Goals**: a abertura do slide-over ganha uma leitura a mais (a
documentação do pacote). É uma leitura de arquivo local dentro do processo do
gateway, feita só quando um painel está aberto, e nunca na listagem do catálogo.

**Constraints**: presença e forma do guia, nunca alcançabilidade — a verificação
não pode adquirir dependência de rede. O renderizador de markdown é o que já
existe; um segundo é proibido. Nenhum arquivo committed cita identificador de
planejamento. A rota de documentação não pode compor caminho de arquivo a partir
de entrada de URL.

**Scale/Scope**: 15 vendors, 40 campos, 9 permissões mínimas e 29 guias a
pesquisar, 15 documentos de pacote tocados, 1 endereço novo, 1 classe de erro
nova, 1 regra de gate nova, 2 telas tocadas.

## Constitution Check

*GATE: precisa passar antes da execução. Reconferir ao final.*

Conferido contra a constituição **como ela estará depois da feature de
governança** (2.2.0, que inclui a cláusula "composto ou não foi entregue").

| Artigo | Como este plano satisfaz |
|---|---|
| I — Evidência sobre asserção | A tabela dos 40 campos da spec foi derivada dos schemas reais em 2026-08-23, não copiada de um documento. Cada permissão mínima nova sai da documentação do próprio fornecedor e a fonte fica citada no documento do pacote — a alegação vem com a evidência anexa. O gate transforma "está preenchido" numa propriedade verificada. |
| II — Autonomia limitada | Não toca laço, orçamento nem limite. |
| III — Leitura por padrão | Não toca semântica de escrita nem de aprovação. A rota nova é leitura, e exige a mesma permissão que a leitura do catálogo. |
| IV — Segredo nunca chega ao agente | A declaração de campo continua não tendo lugar onde um valor caiba: acrescentamos texto sobre o campo, nunca sobre o valor. A recusa em claro **fortalece** o artigo, tornando acionável a única recusa que existe para impedir credencial na rede sem cifra — e a frase, como todas as do proxy, não cita valor. |
| V — Um runtime canônico | Nenhuma superfície nova. A documentação é servida pelo gateway que já serve o catálogo e renderizada pelo console que já renderiza o painel. |
| VI — Neutralidade de provedor | Não toca abstração de provedor. `google_gemini` é tratado como qualquer outro vendor do catálogo. |
| VII — Aprendizado é medido | Não toca mecanismo de aprendizado. |
| VIII — Arquitetura em camadas | A frase "onde obter" e a orientação por campo são declaradas no tier dos pacotes de vendor e lidas para cima pelo gateway; nada desce. A rota de documentação lê o caminho que o relatório de paridade já resolve, então o gateway não passa a conhecer o layout do diretório de pacotes. |
| IX — Capacidades declaradas e paridade | É o artigo mais próximo. A paridade dos sete artefatos não muda de forma nem de alcance; o gate novo é uma segunda propriedade do mesmo catálogo, sobre o schema em vez do sistema de arquivos, e mora no mesmo lugar. Nenhuma integração é acrescentada nem removida. |
| X — O operador é dono dos dados | Nada sai do host. Os endereços de guia são links que o operador escolhe abrir; nada é buscado por conta própria, nem em build nem em runtime. |
| XI — Datastore único | Não toca porta de persistência. |
| XII — Test-first, rastreado | O acceptance vermelho aterrissa antes da tela. O gate ganha seu vermelho contra a árvore atual (28 campos sem permissão, 29 sem guia) antes de qualquer conteúdo ser escrito. Cada teste de contrato é confirmado vermelho e o vermelho é registrado. |
| XIII — Idioma e atribuição | Todo arquivo committed em inglês; texto de UI pelo catálogo de mensagens, en e pt-BR juntos, porque esta feature é dona do catálogo no seu slot. **XIII.4 por substância**: a rota serve o documento que vive no pacote, dentro do repositório — nenhum arquivo committed passa a depender de arquivo não committed. Nenhum teste lê arquivo fora do repositório. |
| XIV — Composto ou não foi entregue | Ver abaixo. |

### Composto ou não foi entregue

Quatro mecanismos, quatro respostas para "quem constrói isso em produção?":

| Mecanismo | Composition root | Prova exigida |
|---|---|---|
| Rota de documentação | `gateway/http/app.py:91` já monta `integrations.router`, e o endereço novo é um método desse mesmo router — composto no ato de ser escrito | Um teste que pede o endereço **à aplicação construída**, nunca ao router isolado |
| Permissão da rota | `gateway/http/security/gateway_routes.py` — o endereço é declarado ali com a mesma permissão da leitura do catálogo | O teste de permissões de rota do gateway, que enumera os endereços e reprova um não declarado |
| Recusa em claro com frase própria | `platform/credentials/proxy/egress.py::refuse_credential_in_clear`, chamada por `platform/credentials/proxy/engine.py` no caminho de encaminhamento, que a aplicação do proxy já monta | Um teste que faz a chamada atravessar o motor do proxy e lê a frase do outro lado, e não só a construção da exceção |
| Gate de orientação | `tools/verify_integrations.py`, alcançado por `make check-integrations`, que já está dentro de `make verify` | Apagar uma declaração e ver `make check-integrations` reprovar nomeando vendor e campo |

Nenhum símbolo novo é construído apenas por teste. "Testes verdes no harness" não
fecha nenhuma tarefa desta feature: o gate fecha com `make verify`, a rota fecha
com a aplicação construída, e as telas fecham com o acceptance contra o staging.

### Complexity Tracking

Nenhuma violação a justificar. A feature não acrescenta camada, superfície,
dependência nem alvo de build: o gate entra num tool que já existe, a rota entra
num router que já existe, o conteúdo entra em declarações que já existem, e a
renderização reutiliza o renderizador que o slot anterior já pagou.

## Project Structure

### Documentation (this feature)

```text
specs_v7/060-o-catalogo-ensina/
├── spec.md
├── plan.md              # este arquivo
├── tasks.md
├── controle.md          # do implementer, não deste plano
└── checklists/requirements.md
```

### Source Code (repository root)

```text
integrations/<15 vendors>/schema.py         # min_scope, guide_url por campo
integrations/<15 vendors>/docs.md           # fonte citada; tabela de Setup em dia
integrations/<15 vendors>/__init__.py       # PROFILE ganha a frase "onde obter"
integrations/_catalogue/entry.py            # IntegrationProfile: o campo novo
integrations/_catalogue/guidance.py         # a regra: o que cada tipo de campo exige
tools/verify_integrations.py                # a regra vira problema reportado
gateway/http/routes/integrations.py         # where_to_get_it na view; endereço de documentação
gateway/http/security/gateway_routes.py     # permissão do endereço novo
gateway/http/catalogue_readers.py           # o mesmo campo, no leitor que já existe
platform/credentials/proxy/errors.py        # a recusa em claro como classe própria
platform/credentials/proxy/egress.py        # passa a levantá-la
console/src/surfaces/integration-panel.tsx  # whereToGetIt; seção de documentação
console/src/surfaces/screens/integrations.tsx  # lê a frase e a documentação
console/src/surfaces/first-run/integrations.tsx # whereToGetIt na oferta
console/src/surfaces/screens/first-run.tsx  # a oferta carrega a frase
console/src/i18n/en.ts, pt-BR.ts            # chaves da seção de documentação
console/visual/screens.json                 # o slide-over mudou de conteúdo
tests/contract/integrations/                # orientação por campo; frase por vendor
tests/contract/gateway/                     # o endereço de documentação
tests/unit/platform/credentials/            # a recusa em claro
tests/security/                             # permissão do endereço novo
console/tests/unit/surfaces/                # painel e passo do primeiro acesso
console/tests/e2e/catalogue-teaches.acceptance.spec.ts
pyproject.toml                              # inclusão de docs.md no pacote construído
```

**Structure Decision**: um módulo novo, `integrations/_catalogue/guidance.py`, e
nenhuma estrutura nova além dele. Ele existe porque a regra "campo secreto exige
permissão mínima, campo de endereço a proíbe, todo campo exige guia" é lida por
três coisas — o gate, o teste de contrato e a mensagem de falha — e escrita três
vezes ela diverge. Fica ao lado de `validation.py`, que é onde a outra propriedade
do catálogo já mora, e pelo mesmo motivo.

## Decisões de design

- **A orientação é por tipo de campo, não por campo.** A leitura crua do backlog
  ("28 de 40 sem permissão mínima") levaria a inventar uma permissão para um
  endereço e para um nome de namespace. A declaração de campo já diz, em texto,
  que um escopo adivinhado é pior que um branco. Então: permissão mínima
  obrigatória nos 21 secretos, **proibida** nos 19 restantes, guia obrigatório
  nos 40. O sistema de tipos já carrega metade dessa regra — o construtor de
  campo de endereço nem aceita permissão mínima — e o gate carrega a outra
  metade. A alternativa (40/40 permissões) foi considerada e recusada: ela
  transforma o gate num produtor de texto inventado, que é exatamente o defeito
  que ele deveria impedir.

- **O gate entra na verificação de integrações, não num alvo próprio.** Ela já é
  o lugar onde "o catálogo está completo" é decidido, já reprova nomeando vendor
  e artefato com o custo da ausência escrito na mensagem, já coleta todos os
  problemas antes de falhar, e já roda como módulo porque precisa importar os
  pacotes — que é exatamente o que ler um schema exige. Um alvo próprio repetiria
  a dança do `sys.path`, acrescentaria uma linha a `make verify` e criaria um
  segundo lugar que responde a mesma pergunta. A regra nova é um `rule` a mais no
  relatório de problemas, ao lado de paridade e de sondagem de permissão.

- **A pesquisa por vendor é uma tarefa por vendor, e a fonte é citada.** Quinze
  tarefas independentes, cada uma com um fornecedor para ler. Nenhuma delas pode
  copiar de outra: `loki` e `grafana` são da mesma casa e têm modelos de
  permissão diferentes; `alertmanager` e `prometheus` não têm modelo de permissão
  nenhum e a resposta honesta para eles é sobre o proxy reverso à frente. A fonte
  entra no documento do pacote, que é committed, então a próxima pessoa a mexer
  não repete a pesquisa nem confia numa memória.

- **Alcançabilidade fica fora, e a decisão é registrada onde é lida.** O gate
  checa que o guia existe e que é um endereço absoluto. Não abre conexão. Uma
  verificação que abre conexão faz o repositório reprovar quando um fornecedor
  reorganiza o site, transforma todo `make verify` numa dependência de rede, e
  falha em ambiente sem egresso — três modos de falha para pegar um problema que
  não é do contribuidor que a disparou. A razão fica escrita no módulo da regra,
  em substância, para quem for tentado a acrescentá-la depois.

- **A frase "onde obter" é declarada no perfil do vendor.** É o mesmo lugar de
  onde o display name e o resumo já saem, o mesmo formato que os provedores de
  modelo já usam para a mesma informação, e mantém a propriedade que o catálogo
  inteiro existe para manter: acrescentar um vendor é um pacote e zero edições em
  arquivo central. A alternativa — derivar a frase do guia do campo principal —
  foi recusada: um endereço não é uma sentença, e "qual é o campo principal" é
  uma pergunta que nenhum schema responde.

- **A rota de documentação devolve um documento, não um corpo de texto.** Todo
  endereço deste gateway responde JSON, o leitor do console parseia JSON, e o
  contrato gerado descreve JSON. Devolver `text/markdown` exigiria um segundo
  caminho de leitura no console e um caso especial no contrato, para economizar
  um envelope. Então: nome, nome de exibição, e o markdown como campo.

- **A rota nunca compõe um caminho a partir da URL.** O nome recebido é resolvido
  contra o catálogo; o caminho do documento vem do relatório de paridade, que já
  o conhece e já garantiu que ele existe para as 15. Um nome desconhecido é uma
  ausência nomeada antes de qualquer acesso a disco. É o que impede que um
  segmento de URL vire travessia de diretório, e é também por que a rota não
  precisa validar o nome com uma expressão regular que alguém teria de manter.

- **A documentação chega ao painel como propriedade, não como fetch do cliente.**
  A tela do catálogo já é renderizada no servidor e já lê o catálogo por
  requisição; ler mais um documento quando — e só quando — um painel está aberto
  é uma leitura a mais no mesmo lugar. Um fetch do cliente exigiria um
  encaminhador novo no console e faria a seção piscar depois que o painel abriu.

- **A frase da recusa em claro é escrita uma vez, no proxy.** Uma classe de erro
  própria, ao lado da recusa de lista de egresso, com a **mesma classificação** —
  o estado que o console deriva não muda, que é a regra de estado espelhado e
  nunca traduzido. O que muda é a mensagem, e ela atravessa o fio pelo registro
  de erro que o transporte já reconstrói, então nenhuma superfície ganha uma
  cópia da sentença. Escrevê-la no console seria a segunda cópia; escrevê-la no
  gateway seria a terceira.

- **Reutilizar o renderizador é uma proibição, não uma preferência.** Um segundo
  renderizador de markdown é uma segunda política de sanitização, e a que
  divergir é a que estará na tela que ninguém revisou. A tarefa localiza o que o
  slot anterior mergeou e um teste afirma que o `console/package.json` declara
  exatamente um.

- **O empacotamento é uma tarefa, não uma suposição.** A rota lê um arquivo de
  dentro do pacote Python. Se a construção da imagem não incluir `docs.md`, tudo
  passa localmente e a rota responde ausência em produção — a forma exata de
  falha que esta onda existe para parar de repetir. A prova é feita contra o
  artefato construído.

## Coordenação de slot

- Esta feature é **dona dos arquivos de escrita única** no seu slot: catálogo de
  mensagens, registro de rotas e registro de telas visuais. A feature parceira
  (identidade) entrega suas chaves como bloco no relatório final e o merge as
  aplica.
- Registro de rotas do console: **não é tocado**. A documentação é lida dentro do
  endereço de integração que já existe; nenhum endereço novo de console nasce.
- O único arquivo com risco real de conflito é o que compõe os passos do primeiro
  acesso, que a feature parceira também toca. Esta feature se limita, nele, ao
  bloco que monta as ofertas de integração e à chamada do passo de integrações —
  duas edições localizadas, declaradas no relatório final para o merge.
- Aceitação contra o staging roda no fim do slot, depois do merge dos dois lados,
  com `make deploy-stg`. Só as alegações de leitura vão para lá.
