# Implementation Plan: Uma fonte por fato

**Branch**: `feat/v7-030-uma-fonte-por-fato` | **Date**: 2026-08-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v7/030-uma-fonte-por-fato/spec.md`

**Referência visual (DoD)**: nenhuma imagem — ver o cabeçalho da spec. O
normativo é a seção "Alegações normativas" da spec, codificada em
`console/tests/e2e/030-uma-fonte-por-fato.acceptance.spec.ts` e confirmada
vermelha antes da implementação. Medição a **1920×1080**.

## Summary

Cinco correções e dois seams, todos da mesma forma: **um fato, um dono, e
nenhuma superfície afirmando o negativo de uma leitura que falhou.**

1. O checklist de setup passa a ler o registro de verificação — a mesma fonte
   que a listagem de providers já lê — em vez de derivar "verificada" da
   presença de uma credencial. O vocabulário de prontidão ganha o quarto valor
   que faltava para um check que **falhou** não se disfarçar de "guardada".
2. A causa de vazio deixa de afirmar causalidade que o gating real não tem. Ela
   só pode ser dita quando o passo que de fato bloqueia está pendente, e nunca
   num deployment que já concluiu uma investigação.
3. O chip de investigação do detalhe de incidente ganha o quarto estado —
   desconhecido — e o caminho de derivação passa a ser único, para que a
   próxima tela não repita a decisão.
4. Toda rota de lista e de detalhe declara-se dinâmica no próprio arquivo, um
   gate de build reprova qualquer rota do shell pré-renderizada, e dois testes
   provam a propriedade de dois ângulos: contagem de requisições no backing, e
   um fato novo aparecendo em um reload.
5. A resolução do handle de credencial passa a ser um caminho único, usado pela
   verificação e pelo binding de ferramentas, para que verificado verde
   signifique alcançável pela investigação. O lease de credencial de provider de
   modelo usa a mesma resolução.
6. O vocabulário de estado de run passa a ter um dono. As fixtures deixam de
   servir palavras que o produto nunca emite, o console deixa de declarar
   palavras que nunca vai receber, e um gate impede que qualquer das duas coisas
   volte. É a mesma regra da feature aplicada ao aparato que a testa — e é a
   razão de a suíte ter passado verde sobre um staging quebrado.

O que **não** muda: o contrato de relato, a identidade de incidente, os portões
de ação, o fail-closed dos stubs de remediação, e o modelo de permissões.

## Technical Context

**Language/Version**: Python 3.12 (gateway, platform, composition roots);
TypeScript / React 19.2.8 no console, Next 16.3.0

**Primary Dependencies**:
`platform/startup/checklist.py`, `gateway/http/routes/first_run.py`,
`gateway/http/routes/providers.py`, `gateway/http/verifications.py`,
`platform/persistence/ports/verification_ledger.py`,
`gateway/http/provider_credentials.py`, `gateway/http/integration_access.py`,
`gateway/http/routes/integrations.py`, `platform/credentials/proxy/llm.py`,
`platform/credentials/vault.py`, `config/constants/first_run.py`;
`console/src/surfaces/emptiness.ts`, `console/src/surfaces/first-run/plan.ts`,
`console/src/surfaces/read.ts`,
`console/src/surfaces/screens/incident-detail.tsx`,
`console/src/app/(shell)/**/page.tsx`, `console/src/i18n/*.ts`,
`tools/mockplane/server.py`, `tools/console_e2e.py`, `tools/console_gate.py`;
`platform/persistence/ports/run_trace_store.py` (a enumeração dona do estado de
run), `gateway/http/routes/investigations.py` (`summary_of`, que a serve
verbatim), `console/src/design/status.ts`, `fixtures/scenarios/populated/*`,
`tools/mockplane/dataset/scale.py`

**Storage**: sem migração. Tudo o que esta feature lê já está gravado — o
registro de verificação e os handles do vault. A única gravação nova é a linha
de log da composição, que não é dado.

**Testing**: pytest (checklist lendo o registro, resolução de handle, quarto
valor de prontidão); vitest (`console/tests/unit/`) para a derivação de causa,
chip e contagens; Playwright (`console/tests/e2e/`) para o acceptance da
feature e para a transversal; gate de build para as rotas pré-renderizadas.

**Target Platform**: gateway Python + console web, servidos no k3s de staging

**Performance Goals**: as rotas tocadas continuam dentro de
`CONSOLE_FIRST_PAINT_BUDGET_MS` e `CONSOLE_ROUTE_TRANSITION_BUDGET_MS`, que já
existem e já são medidos. Nenhum orçamento novo é criado, e nenhum é afrouxado.

**Constraints**: `make verify` parte de verde e termina verde; nenhum valor de
credencial em log, teste, fixture ou mensagem; nenhum acceptance que escreve
roda contra staging.

**Scale/Scope**: 9 telas usam a causa de vazio; 4 estados de prontidão contra 3
hoje; ~20 rotas sob o shell mais 3 rotas de detalhe; 2 composition roots
tocadas.

## Constitution Check

*GATE: precisa passar antes da execução. Reconferir ao final.* Conferido contra
a constituição **como ela estará depois da feature de governança da onda
(2.2.0)** — inclui a emenda "composed or it is not shipped".

| Artigo | Como este plano satisfaz |
|---|---|
| I — Evidência sobre asserção | É literalmente o assunto da feature. Nenhuma tela passa a afirmar o que não foi lido: o estado desconhecido existe para isso, e a causa de vazio deixa de afirmar uma causalidade que ninguém mediu. A rodada de `make verify` anterior é capturada para que "continuou verde" seja comparação. |
| II — Autonomia limitada | Não toca laço, orçamento nem limite. |
| III — Leitura por padrão | Não toca semântica de escrita nem de aprovação. Nenhuma capacidade nova. |
| IV — Segredo nunca chega ao agente | **Morde aqui e é o risco principal.** A resolução de handle e o lease de provider tocam o caminho de credencial. Nada nesta feature lê um valor: a resolução responde *qual handle*, o registro nomeia *de onde veio*, e o gate que reprova `reveal` fora do pacote de proxy continua valendo sem exceção nova. |
| V — Um runtime canônico | Não cria segunda superfície nem segundo runtime. Ao contrário: substitui duas derivações do mesmo fato por uma. |
| VI — Neutralidade de provedor | A ordem vault-antes-de-ambiente vale para todo provider suportado, sem caso especial para nenhum. |
| VII — Aprendizado é medido | Não toca mecanismo de aprendizado. |
| VIII — Arquitetura em camadas | O checklist é tier 3 e não pode alcançar o catálogo nem o registro de verificação por si — a rota continua sendo quem lê e injeta, exatamente como já faz para integrações. O gate de imports é o que prova. |
| IX — Capacidades declaradas | Não altera capacidade nem metadado. A resolução de handle muda **qual credencial** uma ferramenta alcança, nunca o que ela pode fazer. |
| X — O operador é dono dos dados | Nada sai do host. Nenhum dado é apagado; nenhuma credencial é migrada de handle. |
| XI — Datastore único | Nenhuma porta nova, nenhuma migração. |
| XII — Test-first, rastreado | Acceptance vermelho antes da tela, com o vermelho registrado; teste unitário do checklist antes da mudança; gate de build escrito e confirmado reprovando antes da correção das rotas. |
| XIII — Idioma e atribuição | Código, comentário e commit em inglês. Texto de UI pelo catálogo, en e pt-BR. Nenhum arquivo committed cita identificador de requisito, número de artigo, número de feature ou caminho de planejamento. |
| XIV — Composed or it is not shipped | Ver a seção seguinte. |

### Composição — quem constrói isto em produção

A emenda exige que todo mecanismo mergeado seja alcançável a partir de uma
composition root de serving. Esta feature entrega três mecanismos e cada um tem
a sua declarada:

| Mecanismo | Composition root | Prova no caminho de serving |
|---|---|---|
| Checklist lendo o registro de verificação | a rota `GET /v1/setup/checklist` (`gateway/http/routes/first_run.py`), que já é quem lê o catálogo e a saúde e injeta no builder | acceptance contra staging: `/first-run` mostra Verified para o provider cujo registro passou |
| Resolução de credencial de provider vault-primeiro | `compose_provider_credentials`, chamada do lifespan do gateway e re-chamada pela rota que grava credencial | log de boot do pod de staging nomeando origem por provider, mais uma investigação que alcança o provider |
| Resolução única de handle de credencial | o mesmo lifespan, no ponto onde `compose_integration_access` liga o binding, mais a rota de verificação que passa a chamar a mesma função | consulta ao banco de staging comparando o handle do registro de verificação com o handle que o binding reporta |

**Nenhuma tarefa desta feature fecha com "teste verde no harness".** Cada uma
das três acima só fecha com a evidência do caminho de serving na coluna da
direita.

### Complexity Tracking

Uma violação a declarar, e ela é deliberada: **o vocabulário de prontidão sai de
três valores para quatro**. É superfície nova num contrato que várias
superfícies leem (console, CLI). A alternativa — manter três e deixar um check
que falhou aparecer como "guardada" — foi recusada porque é exatamente a classe
de mentira que a feature existe para eliminar, e porque a mesma omissão já
afeta as integrações no mesmo documento. O custo é contido: um valor a mais numa
enumeração já servida, com uma tarefa própria para varrer quem a lê.

Fora isso, a feature reduz complexidade: uma derivação de causa em vez de nove
cópias implícitas, um caminho de derivação de chip em vez de um por tela, uma
resolução de handle em vez de duas.

## Project Structure

### Documentation (this feature)

```text
specs_v7/030-uma-fonte-por-fato/
├── spec.md
├── plan.md              # este arquivo
├── tasks.md
├── checklists/requirements.md
├── controle.md          # do implementer, não deste plano
└── evidence/            # screenshots e saídas de consulta do slot
```

### Source Code (repository root)

```text
config/constants/first_run.py                     # o quarto valor de prontidão
platform/startup/checklist.py                     # readiness do provider vem do registro
gateway/http/routes/first_run.py                  # injeta o registro de provider no builder
gateway/http/verifications.py                     # leitura por tipo, já existente, reusada
gateway/http/routes/providers.py                  # passa a usar a resolução única de handle
gateway/http/routes/integrations.py               # idem, na verificação e no deep verify
gateway/http/credential_handles.py                # NOVO: a resolução única de handle
gateway/http/integration_access.py                # binding usa a resolução única
gateway/http/provider_credentials.py              # lease usa a resolução única
gateway/http/lifespan.py                          # ordem de composição, se mudar
console/src/surfaces/emptiness.ts                 # causa só quando o gating existe
console/src/surfaces/first-run/plan.ts            # quarto valor, contagens
console/src/surfaces/read.ts                      # derivação de estado com desconhecido
console/src/surfaces/screens/incident-detail.tsx  # chip de quatro estados
console/src/surfaces/screens/{decisions,knowledge,...}.tsx  # causa própria
console/src/app/(shell)/**/page.tsx               # declaração de dinamismo por rota
console/src/i18n/en.ts, console/src/i18n/pt-BR.ts # dono no slot
console/src/shell/routes.ts                       # dono no slot (se preciso)
console/visual/screens.json                       # dono no slot (se preciso)
console/tests/e2e/030-uma-fonte-por-fato.acceptance.spec.ts   # NOVO
console/tests/e2e/transversal-rules.spec.ts       # ban novo
console/tests/unit/surfaces/                      # causa, chip, contagens
tools/mockplane/server.py                         # contador de requisições + rota de controle
tools/console_e2e.py                              # expõe o endereço do backing ao Playwright
tools/console_gate.py                             # check novo: nenhuma rota do shell pré-renderizada
tools/check_run_status_vocabulary.py              # NOVO: fixtures e console contra a enumeração
tools/mockplane/dataset/scale.py                  # gerador tira os estados da enumeração
console/src/design/status.ts                      # vocabulário = o que o gateway serve
fixtures/scenarios/populated/{runs,run-detail,run-stream,run-threads,run-replay}.json
fixtures/scenarios/incident-live/run-stream.json
console/visual/baselines/                         # recapturas deliberadas
tests/unit/platform/startup/test_checklist.py     # checklist lendo o registro
tests/unit/gateway/http/                          # resolução de handle, ambiguidade
tests/architecture/                               # o gate de vocabulário como teste
```

**Structure Decision**: um módulo novo (`gateway/http/credential_handles.py`) e
nada mais de estrutura. Ele existe porque a resolução de handle passa a ter três
chamadores em dois arquivos, e a regra que a feature inteira defende — um fato,
um dono — se aplica ao próprio código: duas cópias da resolução são duas
respostas para a mesma pergunta.

---

## Decisões de design

### 1. O dono de "verificada" é o registro de verificação, não o vault

O briefing diz "o vault". O vault responde por **guardada**, e não tem como
responder por verificada: ele guarda metadado de credencial, não veredito de
check. Quem já responde por verificada é `VerificationLedger`, com o tipo
`model_provider`, escrito pela rota de verify e lido pela listagem de providers.

Então a correção não é escolher entre duas fontes: é **fazer o checklist ler a
fonte que já existe**. A rota `GET /v1/setup/checklist` já lê o registro para as
integrações (é assim que `verified_integrations` é montado); ela passa a ler
também o registro de provider e a injetá-lo no builder, pelo mesmo caminho e
pela mesma razão de camada.

Consequência agradável: o checklist continua **não fazendo chamada ao endpoint
do provider**, que é a propriedade que o próprio módulo protege com o injetor
`verify_model`. Ler um registro é grátis; verificar não é.

### 2. O quarto valor de prontidão

Hoje a prontidão tem três valores e é derivada de dois booleanos. Um check
registrado que **falhou** cai em "guardada", que é a mesma palavra de "ninguém
verificou" — dois estados com ações opostas sob um nome só. A prontidão ganha o
quarto valor, e ele é derivado assim:

- registro passou → verificada
- registro falhou → falhando
- sem registro e credencial presente → guardada
- sem credencial → ausente

Vale para provider e para integração, no mesmo documento, pela mesma função.
Blast radius a varrer numa tarefa própria: o console (first-run, dashboard,
integrações) e o `doctor` do CLI, que ramifica sobre esse mesmo campo.

### 3. Quando a causa de setup pode ser dita

Regra: **a causa de setup só é dita quando o passo que de fato bloqueia aquela
tela está pendente.** Não "quando faltam N passos".

Operacionalmente, a causa passa a receber qual dependência a tela precisa, e a
verificar aquele passo:

- telas alimentadas por investigação (decisões, conhecimento, propostas,
  topologia, memória) dependem do passo de **primeira investigação** — e a
  presença de uma investigação concluída já é um passo feito, o que fecha o caso
  do staging por construção;
- telas alimentadas por detecção contínua já têm a causa de observação, que é
  mais específica e é checada antes;
- telas de configuração dependem do passo que as alimenta e de nenhum outro.

E a sentença passa a **nomear o passo**, não a contagem. Uma contagem é um
número que o operador não pode agir sobre; um título de passo é um link.

Quando a causa de setup não se aplica, cada tela precisa de uma causa própria e
acionável — não do texto genérico de mecanismo. Elas são escritas nesta feature
e vão para o catálogo de mensagens em en e pt-BR. Para `/decisions`: nenhuma
proposta porque nenhuma investigação concluiu com remediação a propor. Para
`/knowledge`: nenhum episódio porque nenhuma investigação terminou de forma que
produzisse um.

### 4. O chip de quatro estados, derivado uma vez só

O chip hoje deriva de `hasInvestigation`, que vem de `field(body, ...)` sobre o
`dataOf` de uma leitura que pode ter falhado — e `dataOf` de uma leitura falha é
`undefined`, indistinguível de "o campo não veio". Daí "No investigation" para
uma leitura que nunca aconteceu.

A correção é derivar o chip do `PanelData` inteiro e não do corpo: erro →
desconhecido; sucesso → os três estados de sempre. Como isso vale para qualquer
chip do gênero, a derivação vira um caminho único ao lado de `stateOf` em
`surfaces/read.ts`, e a regra transversal ganha o ban correspondente para que a
próxima tela não repita a decisão.

O estado desconhecido **nomeia a dependência** — `dependencyOf` já a devolve.
Sem o nome, "desconhecido" é honesto e inútil.

### 5. Dinamismo: o que provamos, e como

**A causa nomeada no diagnóstico é uma hipótese, e o plano trata como tal.** O
segmento do shell já declara `dynamic = 'force-dynamic'` desde antes do build
que foi observado, e a página de incidentes já espera `searchParams` — as duas
coisas, sozinhas, tiram uma rota do Full Route Cache. Então uma de três é
verdade, e elas pedem remédios diferentes:

- a rota foi servida de outra camada (cache de roteador no cliente, numa
  navegação suave em vez de um reload; ou um cache de resposta na borda);
- a requisição saiu e não apareceu no log que foi olhado (o console fala com o
  serviço interno, e o log inspecionado era o do pod que serve o webhook);
- a herança do `force-dynamic` do layout não vale para o segmento filho neste
  build.

A primeira tarefa do dinamismo é **medir qual**, com a instrumentação do item
seguinte, e registrar a resposta. O remédio escolhido depende dela; a
propriedade exigida e os testes, não.

**Mecânica do teste — duas, porque são duas alegações diferentes:**

**(a) Contador no backing — prova que a requisição chegou.** O plano de mock
ganha um contador por rota e por sessão, e uma rota de controle fora do espaço
de caminhos do gateway (`/__mockplane__/requests`) que o devolve. O harness
(`tools/console_e2e.py`) passa a exportar o endereço do backing para o processo
do Playwright, como já exporta a URL do console e a credencial. O acceptance
lê o contador, faz um load novo de página (`page.goto`, não navegação suave),
lê de novo, e afirma que subiu. É cego à camada de cache: qualquer coisa que
sirva a página sem falar com o gateway reprova.

Foi escolhida em vez de assertion de log no harness porque um log é um formato
que ninguém contratou: ele muda de forma e o teste passa a medir o formato. Um
contador é um número, e a rota de controle é do próprio backing — nada disso
existe no binário de produção.

**(b) Fato novo em um reload — prova que o operador vê o presente.** Escreve um
incidente pela sessão do backing, recarrega uma vez, e afirma que ele está na
lista. É a alegação que o operador de fato faz, e ela pega cache de dados que a
(a) não pegaria.

**(c) Gate de build — prova que não volta.** A saída do build de produção diz,
por rota, se ela foi pré-renderizada. Um check novo no gate do console lê o
manifesto que o build emite e reprova se qualquer rota sob o shell constar como
estática. Ele mora onde o build existe — pendurado no alvo de build, não no
`verify` puro, que não constrói — e é declarado como "pula por política" quando
não há build, do mesmo jeito que os dois checks que precisam de infraestrutura
já fazem. A tarefa confirma o nome exato do arquivo de manifesto contra a saída
real antes de afirmar sobre ele.

Nenhuma das três roda contra staging: (a) e (b) precisam do backing, (c) é de
build. A alegação que roda lá é a de conteúdo coerente, e a spec marca isso.

### 6. O custo de latência do dinamismo: medido e decidido

Declarar dinâmico troca HTML pré-computado por HTML por requisição. O custo é
real e o produto já tem os números contra os quais julgá-lo:
`CONSOLE_FIRST_PAINT_BUDGET_MS` (2000 ms) e
`CONSOLE_ROUTE_TRANSITION_BUDGET_MS` (1200 ms), ambos já medidos pela suíte de
orçamento do console.

**A medição**: `/incidents`, `/runs` e `/incidents/{id}`, a 1920×1080, contra o
backing de mock, 20 loads por rota, p50 e p95 de primeira pintura, **antes e
depois** da mudança. Os dois conjuntos vão para a evidência do slot.

**A decisão, tomada antes de medir para que a medição não a justifique depois**:

- p95 dentro do orçamento → aceito, sem cache de dados. É o caso esperado: as
  leituras já são por requisição (`cache: 'no-store'`), então o que a rota
  estática economizava era a renderização e não a ida ao gateway.
- p95 fora do orçamento → cache de **dados** curto por requisição, com a janela
  declarada em constante e um teto de poucos segundos, e a alegação de "um fato
  novo em um reload" continua tendo de passar. Se ela não passar com a janela
  escolhida, a janela está errada.
- Página congelada **nunca** é a saída. Um orçamento que só fecha servindo o
  passado é um orçamento errado, e nesse caso a tarefa reporta em vez de
  afrouxar.

### 7. O seam de time: **as ferramentas resolvem como o time dono da credencial**

Este é o ponto onde a feature decide, e a decisão é:

> A verificação continua resolvendo como o time do caller. O binding de
> ferramentas e o lease de provider passam a resolver como **o time que detém a
> credencial daquela integração**, descoberto do próprio vault, com o handle
> org-wide como recurso quando ninguém a detém por time — ou quando mais de um
> time a detém.

**Por que nessa direção.** O vault já cai de time para organização e **não** cai
de organização para time. Resolver como a organização é estritamente mais cego:
nunca enxerga uma credencial de time. Resolver como o time é estritamente mais
capaz: enxerga a do time e, na falta dela, a da organização. Das duas maneiras
de fazer os dois lados concordarem, só uma preserva os dois casos que hoje
funcionam.

**Por que não o contrário.** Baixar o deep verify para org-wide faria a
verificação parar de conseguir testar uma credencial de time — desfazendo
exatamente o que o deep verify consertou — e trocaria uma tela que mente numa
direção por outra que mente na outra.

**Por que não simplesmente fazer o vault cair de organização para qualquer
time.** Porque isso deixaria a credencial de um time ser gasta pela investigação
de outro sem ninguém ter escolhido isso. Num produto cujo desenho inteiro de
credencial é handle por time, essa é a forma de um vazamento entre times, e o
ganho de conveniência não paga.

**A ambiguidade é decidida, não sorteada.** Dois times com credencial para o
mesmo vendor é um caso real. O processo não escolhe: ele liga o handle
org-wide, registra a ambiguidade nomeando a integração, e a superfície de
integrações diz que mais de um time detém aquela credencial. Falha visível em
vez de falha silenciosa — e é o único caso em que "verificado verde e invisível"
pode sobreviver, agora com uma frase que explica por quê.

**O invariante que fica testado**: para toda integração, o handle que o caminho
de verificação resolve é o handle que o binding de ferramentas resolve. Uma
função responde a pergunta, três chamadores a usam, e o teste percorre o
catálogo configurado comparando os dois.

### 8. A chave do modelo: verificar o que já existe antes de escrever o que já está escrito

O caminho vault-primeiro-ambiente-depois **existe** e é chamado no boot; o
backlog descreve o estado anterior a isso. Então a tarefa aqui não é escrever de
novo: é

1. confirmar que continua composto no caminho de serving, com evidência de log
   no staging, e não só com teste no harness;
2. fechar a metade que falta — o lease é tirado com o handle org-wide, então
   uma chave gravada sob um time não é vista pelo processo. Passa a usar a
   resolução única da decisão 7;
3. registrar a origem por provider (vault ou ambiente) e o time, nomes apenas,
   nunca valor.

O ponto três é o que transforma a alegação em algo auditável sem revelar
segredo, e é o que a evidência de staging cita.

### 9. O vocabulário de estado de run: aceito, com a fonte corrigida

O orquestrador da onda pediu que esta feature tomasse conta do vocabulário de
estado de run, a partir de um achado de duas outras gerações. **Aceito** — é
literalmente o assunto da feature, aplicado ao aparato que a testa, e é a
explicação de por que os outros defeitos sobreviveram a tantas rodadas verdes.

O achado foi conferido contra o código e é maior do que veio descrito. Há
**três** vocabulários para um fato, e um quarto nas fixtures:

| Onde | Valores |
|---|---|
| Enumeração do runtime (como um run terminou dentro do laço) | `completed`, `partial`, `cancelled`, `failed` |
| Enumeração do store — **a que o gateway serve verbatim** | `running`, `suspended`, `completed`, `cancelled`, `failed`, `interrupted` |
| Vocabulário declarado pelo console | `queued`, `running`, `waiting`, `succeeded`, `failed`, `cancelled` |
| O que as fixtures de fato servem | `running`, `succeeded`, `failed`, `cancelled`, `awaiting_approval` |

**A fonte é a do store**, não a do runtime que o pedido nomeou: a rota que serve
um run passa `run.status.value` direto, sem tradução, e é essa palavra que chega
ao console. Corrigir contra a enumeração do runtime deixaria `running`,
`suspended` e `interrupted` de fora e criaria um quinto vocabulário.

O saldo do desalinhamento: as fixtures inventam **dois** valores (`succeeded` e
`awaiting_approval`, e não só o primeiro), e o console declara **três** que
nunca vai receber (`queued`, `waiting`, `succeeded`) enquanto lhe faltam três
que vai (`suspended`, `interrupted`, `completed` — este último acrescentado no
slot anterior). Por isso o gate checa nas **duas** direções: valor a mais é uma
tela que ninguém verá, valor a menos é um run real caindo no ramo de fallback.

De onde veio `succeeded`: a enumeração de estado de **tool call** tem esse
valor. A fixture tomou emprestada a palavra do fato vizinho. A migração varre
estado de run e não pode encostar em estado de tool call — dois fatos que
compartilham uma palavra é exatamente o tipo de armadilha que uma varredura por
texto cai.

**Forma do gate**: um check de repositório que lê a enumeração do domínio como
dado — nunca uma lista literal repetida no próprio check, que seria um quinto
vocabulário —, coleta todo estado de run servido por fixture e o vocabulário
declarado pelo console, e reprova nomeando arquivo e valor. Ele entra na família
dos checks que já rodam em `make verify`, porque não precisa de build nem de
infraestrutura.

**As baselines visuais caem aqui, e isso é o resultado certo.** Estado muda cor,
forma e rótulo, então migrar `succeeded` move capturas. A baseline anterior
registrava uma tela que o produto não produz; recapturá-la é corrigir o
registro, não perder cobertura. Cada recaptura é um passo deliberado e revisável
no diff — nenhuma é apagada para o gate passar, e nenhuma é substituída por
captura fabricada.

**O que esta feature não faz**: unificar a enumeração do runtime com a do store.
São dois fatos ("como o laço terminou" e "onde o run está") que hoje se
sobrepõem em quatro palavras, e resolver isso é uma decisão do dono do contrato
de runs, não uma correção de passagem. Fica registrada como observação no
relatório final.

### 10. Ordem de execução, e por que ela é essa

Gate primeiro, tela depois, em três frentes que não se cruzam:

1. **Backend da verdade de estado** (checklist, quarto valor, resolução de
   handle) — porque o console lê o que ele serve, e corrigir a tela contra um
   documento errado seria corrigir duas vezes.
2. **Instrumentação do backing e gate de build** — porque a frente de dinamismo
   não tem teste honesto sem elas, e porque o gate precisa reprovar **antes** da
   correção das rotas para que o verde signifique alguma coisa.
3. **Console** — causa, chip, rotas, contagens, i18n.

E, atravessando as três, o **vocabulário de estado de run**: o gate primeiro,
confirmado reprovando contra as fixtures atuais; depois a migração das fixtures;
depois a purga do vocabulário do console, que só pode acontecer quando nenhuma
fixture usar mais o valor inventado; e as baselines por último, uma a uma.

A medição de latência acontece duas vezes: uma linha de base antes de tocar as
rotas, e a comparação depois.

### 11. Escrita única, e o que esta feature não toca

Esta feature é a **dona** de `console/src/i18n/*.ts`,
`console/src/shell/routes.ts` e `console/visual/screens.json` no seu slot. A
feature par entrega as chaves de que precisar como bloco no relatório final e o
merge do slot aplica. Nenhuma tarefa daqui toca o diretório de outra feature, e
nenhuma edita arquivo de outra feature.
