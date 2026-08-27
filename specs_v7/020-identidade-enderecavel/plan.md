# Implementation Plan: Identidade endereçável — o que a interface chama pelo nome, a rota atende pelo nome

**Branch**: `feat/v7-020-identidade-enderecavel` | **Date**: 2026-08-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v7/020-identidade-enderecavel/spec.md`

**Referência visual (DoD)**: nenhum mockup. A referência são as **alegações
normativas** da spec, codificadas em
`console/tests/e2e/identidade-enderecavel.acceptance.spec.ts` e confirmadas
vermelhas antes da implementação. Viewport normativo de medição: 1920×1080.

## Summary

Três defeitos com uma causa comum — o produto usa como endereço uma chave que
não foi feita para ser endereço — e um quarto que é o mesmo princípio um nível
acima.

1. O incidente ganha uma **forma pública** do identificador: curta, sem
   caractere reservado, derivada deterministicamente da chave interna e
   materializada numa coluna com unicidade por organização. A chave interna
   continua sendo a chave primária e continua resolvendo na rota.
2. O parâmetro de rota dinâmica passa a ser **decodificado uma vez, na borda**,
   por um helper compartilhado; `bind()` continua encodando uma vez. A
   invariante fica escrita nos dois lados.
3. O **título do incidente é o título do incidente**, no H1 e na aba, e uma
   leitura falhada passa a dizer que falhou em vez de imprimir o endereço como
   nome e afirmar que não há investigação.
4. `/investigations` e `/setup` respondem por **redirect**, pela mesma mecânica
   de rota aposentada que Settings já usa.

O que **não** muda: a chave interna, a correlação, a timeline, o vocabulário
dos chips, a sub-linha de meta, e qualquer coisa que a feature par do slot
toque.

## Technical Context

**Language/Version**: TypeScript (console Next 16.3.0) e Python 3.12 (gateway,
persistência, migração)

**Primary Dependencies**: `console/src/lib/api.ts`,
`console/src/app/(shell)/**` (rotas dinâmicas e as duas rotas novas de
redirect), `console/src/shell/routes.ts`, `console/src/shell/legacy-redirect.ts`,
`console/src/shell/search.ts`, `console/src/surfaces/screens/incident-detail.tsx`,
`console/src/surfaces/screens/incidents.tsx`,
`console/src/surfaces/screens/dashboard.tsx`,
`console/src/surfaces/screens/run-detail.tsx`,
`gateway/http/routes/incidents.py`,
`platform/persistence/ports/incident_store.py`,
`platform/persistence/postgres/repositories/incident_store.py`,
`platform/persistence/postgres/models.py`,
`platform/persistence/fakes/incident_store.py`,
`platform/incidents/lifecycle.py`, `platform/incidents/service.py`,
`platform/startup/demo/seeder.py`,
`platform/persistence/migrations/versions/`

**Storage**: PostgreSQL. Uma coluna nova na tabela `incidents` mais um índice
único por `(org_id, public_id)`, numa revisão de migração reversível. Nenhuma
outra tabela é tocada.

**Testing**: pytest (contrato da rota de incidente, contrato do store,
propriedade da derivação, migração ida-e-volta); vitest
(`console/tests/unit/`) para o decode de borda, o cliente de API e o cabeçalho
do detalhe; Playwright (`console/tests/e2e/`) para o acceptance da feature,
rodado local contra o dataset e contra o staging na marcação staging-safe;
suíte visual como regressão.

**Target Platform**: gateway Python + console web, servidos no k3s de staging
(`stg-ninjasre.lan.kyo.ninja`; ingress `/ → web`, `/webhooks → app`)

**Project Type**: correção de fronteira — contrato, persistência e console na
mesma feature, porque a forma pública nasce no store e morre na URL

**Performance Goals**: a resolução por forma pública é uma leitura indexada,
com o mesmo custo da resolução pela chave primária. Nenhuma varredura de tabela
em caminho de leitura de tela.

**Constraints**: `make verify` verde tendo partido de verde; migração
reversível; nenhum incidente do staging perdido nem inacessível; nenhum arquivo
do diretório de outra feature tocado; o diff em `incident-detail.tsx` contido a
identidade e leitura, porque outra feature da onda o redefine depois.

**Scale/Scope**: uma tabela, uma coluna, uma revisão de migração; quatro
superfícies de console que geram href de incidente; cinco rotas dinâmicas do
console; duas rotas novas de redirect; um campo novo no contrato de incidente,
com documento de API e cliente TS regenerados.

## Constitution Check

*GATE: precisa passar antes da execução. Reconferir ao final.*

Checagem contra a constituição **como ela estará depois da feature de regras e
governança** — versão 2.2.0, incluindo a cláusula nova "composed or it is not
shipped".

| Artigo | Como este plano satisfaz |
|---|---|
| I — Evidência sobre asserção | É o coração da feature. Uma leitura que falha deixa de virar afirmação: o cabeçalho diz que não leu, e nenhum chip afirma o negativo. O contrário — imprimir o endereço como nome e declarar "No investigation" — é exatamente a asserção sem evidência que o artigo proíbe. As alegações normativas são verificadas contra o staging real, não contra o harness. |
| II — Autonomia limitada | Não toca laço, orçamento nem limite. |
| III — Leitura por padrão | Nada de novo escreve. A migração é a única escrita, ela é de esquema, e é reversível. As rotas de redirect são navegação. |
| IV — Segredo nunca chega ao agente | Não toca o proxy de credencial. A forma pública é derivada de uma chave que já é pública dentro da organização e não carrega segredo nenhum — mas a derivação é um digest, não um encoding, então nem o instante de abertura nem o fingerprint do alerta ficam legíveis na URL, que é uma redução de superfície e não um aumento. |
| V — Um runtime canônico | Não toca runtime. |
| VI — Neutralidade de provedor | Não toca abstração de provedor. |
| VII — Aprendizado é medido | Não toca mecanismo de aprendizado. |
| VIII — Arquitetura em camadas | A derivação vive na porta de persistência, junto de `incident_key`, que é onde a chave interna já é derivada — nenhum tier novo, nenhuma dependência nova entre tiers. O console continua falando com o gateway só pelo cliente gerado. A checagem de contratos de import roda no fecho. |
| IX — Capacidades declaradas | Nenhuma capacidade nova. |
| X — O operador é dono dos dados | Nada sai do host. A migração acrescenta uma coluna e não apaga nem reescreve nenhum incidente; a reversão devolve o esquema anterior com todos os incidentes intactos. |
| XI — Datastore único | **Cláusula 2**: o acesso continua pela porta `IncidentStore`; o método novo de lookup é declarado na porta e implementado nas duas adaptações (Postgres e fake), sem SQL fora da camada de persistência. **Cláusula 3**: a migração é reversível, e o `downgrade` é exercitado por teste, não presumido. |
| XII — Test-first, rastreado | **Cláusula 1**: o acceptance e os testes de contrato aterrissam vermelhos antes de qualquer implementação, com a mensagem real registrada. **Cláusula 2**: a lista de incidentes e o comportamento de `bind()` para valores sem reservado são caracterizados antes da mudança e ficam verdes por ela. **Cláusula 3**: a feature não altera investigação; o efeito sobre a suíte de cenários sintéticos é **medido e reportado** mesmo assim — "sem efeito" é a resposta esperada e "não medido" não é aceitável. **Cláusula 4**: o contrato da rota de incidente ganha teste para as duas grafias de identificador. |
| XIII — Idioma e atribuição | Código, comentários e mensagens de commit em inglês. Texto de UI pelo catálogo i18n, em `en` e `pt-BR` — esta feature é a dona dos arquivos de i18n no seu slot. Nenhum arquivo committed cita identificador de requisito, número de artigo, número de feature ou caminho de planejamento. |
| XIV (2.2.0) — Composto ou não foi entregue | Ver a seção abaixo. |

### Qual composition root constrói isto

A exigência de 2.2.0 é responder, com `file:line`, quem constrói o mecanismo
novo no caminho de serving. A resposta honesta aqui tem duas partes, e a
segunda é a que importa:

**Não há objeto novo para construir.** A forma pública é (a) uma função pura na
porta de persistência, ao lado de `incident_key`
(`platform/persistence/ports/incident_store.py:306`), (b) um campo do
`Incident` (`:187`), e (c) um método novo na porta `IncidentStore`,
implementado por `PostgresIncidentStore`
(`platform/persistence/postgres/repositories/incident_store.py:50`) e por
`FakeIncidentStore` (`platform/persistence/fakes/incident_store.py:27`). Um
mecanismo que é campo e método de coisas já construídas não tem raiz de
composição própria.

**O caminho de serving que o exercita, cravado:**

- Escrita: `IncidentLifecycle.raise_incident`
  (`platform/incidents/lifecycle.py:89`) é o único lugar que constrói um
  `Incident` novo em produção — ele passa a derivar a forma pública junto com a
  chave interna, na linha `:102`. O caminho de alerta chega ali por
  `platform/incidents/ingestion.py:86` via
  `platform/observation/bridge/alerts.py:189`, disparado pelo webhook em
  `gateway/webhooks/router.py`.
- Leitura: `GET /v1/incidents/{incident_id}`
  (`gateway/http/routes/incidents.py:399`) → `IncidentService.detail`
  (`platform/incidents/service.py:90`) → `uow.incidents` →
  `PostgresUnitOfWork.incidents` (`platform/persistence/postgres/gateway.py:165`).
  É esse fio que passa a resolver as duas grafias.
- O `Incident` também é construído pelo semeador de demonstração
  (`platform/startup/demo/seeder.py:568`), que não é caminho de serving mas
  quebra o build se ficar sem o campo.

**Prova exigida no DoD, e ela não é "teste verde no harness":** um incidente
real do staging, aberto pelo console a partir da lista, com a forma pública na
URL e os painéis cheios — mais as consultas de banco enumeradas na spec. A
peça é provada pelo pytest; a composição é provada pelo staging.

### Complexity Tracking

Nenhuma violação a justificar. A feature acrescenta um campo, um método de
porta e uma coluna; em troca remove três grafias divergentes de endereço, uma
dupla codificação e um fallback que imprime identificador como nome.

## Project Structure

### Documentation (this feature)

```text
specs_v7/020-identidade-enderecavel/
├── spec.md
├── plan.md                    # este arquivo
├── tasks.md
├── checklists/requirements.md
├── controle.md                # do implementer, não deste plano
└── evidence/                  # capturas do staging, criadas na validação
```

### Source Code (repository root)

```text
platform/persistence/ports/incident_store.py          # derivação + campo + método da porta
platform/persistence/postgres/models.py               # coluna e índice único
platform/persistence/postgres/repositories/incident_store.py  # lookup e mapeamento de linha
platform/persistence/fakes/incident_store.py          # o mesmo lookup, em memória
platform/persistence/migrations/versions/0015_*.py    # coluna, backfill, índice; reversível
platform/incidents/lifecycle.py                       # deriva ao abrir
platform/incidents/service.py                         # resolve as duas grafias
platform/startup/demo/seeder.py                       # o campo no semeador
gateway/http/routes/incidents.py                      # o campo no contrato de leitura
fixtures/contract/openapi.json                        # regenerado
fixtures/scenarios/*/incidents*.json                  # regenerados com a forma pública
console/src/api/schema.ts                             # regenerado do documento
console/src/lib/api.ts                                # a invariante, escrita
console/src/shell/route-params.ts                     # novo: o decode de borda
console/src/shell/routes.ts                           # tabela de redirects generalizada
console/src/shell/legacy-redirect.ts                  # acompanha o rename
console/src/shell/search.ts                           # href pela forma pública
console/src/app/(shell)/incidents/[incidentId]/page.tsx   # decode + título da aba
console/src/app/(shell)/runs/[runId]/page.tsx             # decode
console/src/app/(shell)/integrations/[name]/page.tsx      # decode
console/src/app/api/stream/[runId]/route.ts               # decode
console/src/app/(shell)/investigations/page.tsx           # novo: redirect
console/src/app/(shell)/setup/page.tsx                    # novo: redirect
console/src/surfaces/screens/incident-detail.tsx      # título, cabeçalho da leitura falhada
console/src/surfaces/screens/incidents.tsx            # href pela forma pública
console/src/surfaces/screens/dashboard.tsx            # href pela forma pública
console/src/surfaces/screens/run-detail.tsx           # href pela forma pública
console/src/i18n/en.ts, console/src/i18n/pt-BR.ts     # chaves novas (dona no slot)
console/visual/screens.json                           # se a resolução do id mudar (dona no slot)
tests/contract/…                                      # rota e store
tests/unit/platform/persistence/…                     # derivação e migração
console/tests/unit/…                                  # decode, cliente, cabeçalho
console/tests/e2e/identidade-enderecavel.acceptance.spec.ts   # novo
```

**Structure Decision**: nenhuma estrutura nova. Um arquivo novo no console
(`route-params.ts`), duas páginas de redirect, uma revisão de migração. Todo o
resto é modificação de arquivo existente.

### Propriedade de escrita única

Esta feature é a **dona** de `console/src/i18n/*.ts`,
`console/src/shell/routes.ts` e `console/visual/screens.json` no seu slot. A
feature par é backend e não os toca. Nenhuma tarefa desta feature escreve em
diretório de outra feature.

## Decisões de design

### 1. A forma pública é `inc_` seguido de 16 caracteres hexadecimais minúsculos

Exemplo: `inc_9f2c4a1b8e7d3506`. Vinte caracteres, todos fora do conjunto
reservado de uma URL.

**Como é derivada.** `public_id = "inc_" + sha256(incident_id)[:16]`, na mesma
porta onde `incident_key` vive, como função pura. Dezesseis hexadecimais são
sessenta e quatro bits, que é a mesma medida que `_bounded` já usa no
repositório (`_KEY_DIGEST_CHARS`) e pela mesma razão declarada lá: colisão
deixa de ser algo que acontece, e o identificador continua curto.

**Por que derivada e não sorteada.** Um identificador aleatório obrigaria a
migração a inventar um valor por linha, e um incidente escrito por um nó que
ainda não migrou ficaria sem endereço até alguém o gerar. Derivada, a migração
e o código chegam ao mesmo valor por construção — e é isso que faz "o incidente
do staging continua abrível" ser uma propriedade em vez de uma esperança.

**Por que coluna e não só função.** A função dá o caminho de ida; o que a tela
precisa é o de volta, de forma pública para linha. Sem coluna, resolver um
endereço seria varrer os incidentes da organização recomputando digest — uma
leitura de tela virando varredura de tabela. A coluna é o índice materializado
de uma função determinística, e o índice único por `(org_id, public_id)` é o
que transforma uma colisão em falha de escrita em vez de "abriu o incidente
errado".

**Por que o prefixo.** Ele distingue o endereço de um incidente do de um run
(trinta e dois hexadecimais) na leitura, e dá à borda uma forma reconhecível:
um pedido cujo parâmetro casa `inc_[0-9a-f]{16}` é resolvido pela coluna, e
qualquer outra coisa pela chave primária. Isso torna a resolução das duas
grafias uma decisão de forma, e não uma tentativa em cascata que faz duas
consultas para todo pedido.

**O que foi recusado.** *Encoding estável da chave composta* — base64url do id
inteiro passa de noventa caracteres e continua sendo uma segunda codificação
para alguém errar; ela resolve o escape e não resolve o comprimento nem a
divergência de grafias. *Um contador sequencial por organização* — legível e
curto, mas exige um gerador transacional, vaza volume de incidentes, e não é
derivável, então a migração voltaria a ter de inventar valores. *Trocar a
chave primária pela forma curta* — arrastaria a timeline, a correlação e toda
a história do staging, e é uma feature de persistência, não desta.

**Ponto aberto para o operador**: se o prefixo `inc_` não agradar, a
alternativa é a forma nua de dezesseis hexadecimais. A troca custa uma linha de
derivação e uma linha de regex na borda, e nada mais — mas custa uma migração
nova se for feita depois de a primeira rodar no staging.

### 2. A migração dá forma pública a tudo que já existe, e é reversível

Uma revisão nova, a próxima da série (`0015`), em três passos dentro da mesma
revisão:

1. Acrescenta a coluna, anulável.
2. Preenche cada linha com a derivação aplicada ao `incident_id` daquela linha,
   em lote. O backfill usa a **mesma função** que o código usa — ele a importa,
   não a reimplementa. Uma segunda implementação do digest dentro da migração
   seria a maneira exata de o valor gravado divergir do valor computado.
3. Cria o índice único por `(org_id, public_id)` e torna a coluna obrigatória.

O `downgrade` derruba o índice e a coluna. Nenhum incidente é apagado, nenhuma
outra coluna é tocada, e a chave interna não muda — o que significa que a
reversão devolve exatamente o esquema anterior com os dados anteriores. A ida e
a volta são exercitadas por teste contra PostgreSQL real, não presumidas.

**A propriedade que amarra as duas metades**: um teste afirma que, para um
`incident_id` qualquer, o valor que a migração grava e o valor que o código
deriva são o mesmo. Sem esse teste, a concordância é uma coincidência de
revisão de código.

### 3. O decode acontece uma vez, na borda, num lugar só

Um helper novo — `console/src/shell/route-params.ts` — com uma função que
recebe o que o roteador entregou e devolve o valor literal. Toda rota dinâmica
do console passa por ela: incidente, run, integração, e a rota de stream.

`bind()` (`console/src/lib/api.ts:66`) **não muda de comportamento**: ele
continua aplicando `encodeURIComponent` uma vez. O que muda é que o valor que
chega até ele já é literal. A invariante — decodificado uma vez na borda,
encodado uma vez no cliente — fica escrita na documentação de `bind` em
substância, porque o próximo a adicionar uma rota dinâmica precisa encontrar a
regra onde ela morde.

**O caso do `%` solto.** `decodeURIComponent('100%')` lança `URIError`. O
helper devolve o valor recebido quando a decodificação lança, porque a
alternativa é uma rota derrubando a renderização inteira por causa de um
endereço malformado que deveria terminar em "não existe esse incidente".

**Por que não decodificar dentro de `bind()`.** Porque `bind` é chamado com
valores que **não** vieram de um parâmetro de rota — um `resource_id` montado
em código, um `run_id` lido de um payload. Decodificar ali corromperia um valor
que legitimamente contém `%`. O decode pertence à fronteira por onde o valor
percent-encoded entra, e essa fronteira é a página.

**O teste que prova.** Um parâmetro contendo `:`, `@`, `+`, `/` encodado e `%`
solto, atravessando borda e cliente, com o endereço final comparado contra o
`encodeURIComponent` do valor original. É o teste que a spec exige e é ele que
impede a regressão de voltar por uma rota nova.

### 4. O título é o título, e uma leitura falhada diz que falhou

Duas mudanças em `incident-detail.tsx` e uma na página:

- O H1 passa a ser `incident.title`. O fallback `|| incidentId` sai. Quando a
  leitura sucedeu e o título é vazio, o cabeçalho mostra a ausência declarada
  que o console já usa para isso — nunca o identificador.
- Quando a leitura falhou, o cabeçalho renderiza uma frase de leitura falhada,
  vinda do catálogo, e **o chip de investigação não é renderizado**. A ausência
  é o que a casa prefere a uma mentira, e é também o menor diff possível: a
  feature de uma-fonte-por-fato substitui essa ausência pelo chip de estado
  desconhecido, e não terá de desfazer nada que esta escreveu.
- A aba deixa de ser `documentTitle(incidentId, …)`. `generateMetadata` passa a
  ler o incidente pelo mesmo caminho que a página, através de um leitor
  memoizado por requisição — o padrão que `surfaceContext` já usa para o viewer
  (`console/src/surfaces/context.ts:59`) — para que a leitura aconteça uma vez
  e as duas superfícies nomeiem a mesma coisa. Quando a leitura falha, a aba
  cai no nome do deployment, nunca no identificador.

**O que esta feature deliberadamente não toca em `incident-detail.tsx`**: o
vocabulário dos chips de estado, a sub-linha de meta, o painel de proposta e o
de evidência. Outra feature da onda redefine os chips; colidir de propósito ali
custaria um merge inteiro por nada.

### 5. Os redirects reusam a mecânica que já existe, e a tabela perde o nome errado

A tabela de redirects (`SETTINGS_REDIRECTS` em `console/src/shell/routes.ts:698`)
deixa de se chamar por Settings e passa a se chamar pelo que é: redirects de
rota aposentada. Ela ganha duas linhas — `/investigations` → `/runs` e
`/setup` → `/first-run` — e `legacyRedirectHref` continua exatamente como
está, preservando toda a consulta menos `tab`. Duas páginas novas fazem o
redirect, no mesmo formato de `signals/page.tsx`.

Renomear em vez de abrir uma segunda tabela: duas tabelas de redirect é o
começo de dois lugares onde procurar por que um endereço vai parar noutro. Esta
feature é a dona de `routes.ts` no seu slot, então o rename cabe aqui sem
disputa.

**Redirect temporário, não permanente.** O redirect é o de 307, o mesmo que as
rotas de Settings já usam, e não o permanente. Um 308 fica gravado no
navegador de quem o recebeu, e a onda ainda está movendo telas de lugar — um
redirect permanente emitido no meio de uma onda é uma decisão difícil de
desfazer numa máquina que não é nossa.

### 6. O contrato ganha um campo, e os artefatos gerados acompanham

`IncidentSummaryView` (`gateway/http/routes/incidents.py:64`) ganha a forma
pública ao lado do `incident_id`. Ela **acrescenta**, não substitui: a chave
interna continua no payload porque o detalhe da timeline a referencia e porque
um operador depurando precisa dela. O que o console passa a usar para montar
href é só a forma pública.

Mudança de shape significa: documento de API committed regenerado, cliente TS
regenerado do documento, dataset simulado reconstruído. Os três têm gate
próprio no repositório, e é por isso que a ordem é gerar-depois-verificar em
vez de editar à mão.

### 7. A ordem é acceptance-primeiro, e o vermelho é registrado

O acceptance spec com as dezesseis alegações aterrissa antes de qualquer
implementação e é confirmado vermelho, com a mensagem real de cada uma. É o
único jeito de esta feature ter um vermelho honesto: um endereço consertado e
validado depois do fato não distingue "consertei" de "o teste não olha" — que é
precisamente como a lista de incidentes chegou a ter três grafias diferentes
para o mesmo link sem ninguém notar.

A linha de base — `make verify` na árvore intacta, com o log guardado fora do
repositório, e as contagens de incidentes no banco de staging antes da migração
— é capturada antes da primeira escrita. Sem ela, uma falha preexistente é
debitada desta feature e uma falha desta feature se esconde atrás de "já estava
assim".
