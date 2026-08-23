# Feature Specification: Provider out-of-the-box — lista dinâmica, probe honesto, estado espelhado

**Feature Branch**: `feat/v6-010-provider-out-of-the-box`

**Created**: 2026-08-16

**Status**: Draft

**Input**: Briefing [../briefings/010.md](../briefings/010.md) + [../briefings/COMUM.md](../briefings/COMUM.md).
"Configurar o provider vira o fluxo que o operador conhece de outras aplicações:
colar a chave → a lista de modelos carrega da API do vendor → escolher →
verificar → pronto."

**Referência visual (DoD)**: [../mockups/settings-v6.html#m1](../mockups/settings-v6.html#m1)
(Models & providers com a verificação como estado de primeira classe) e
[../mockups/settings-v6.html#m5](../mockups/settings-v6.html#m5) (passo Verify do
setup). Ambas as âncoras são normativas em layout, hierarquia, agrupamento e
vocabulário — pixels não.

**Diagnóstico que a motiva**: [../DIAGNOSTICO.md](../DIAGNOSTICO.md) §2 (P0-1) e §7
(decisões 5 e 6 do operador).

## Fatos verificados que esta spec assume (2026-08-16, não re-derivar)

- O probe de tool calling vive em `core/llm/preflight.py:168` (`_tool_call_check`)
  e o cliente Gemini monta `functionCallingConfig: {mode: "AUTO"}` em
  `core/llm/providers/gemini.py:193` — modo em que o modelo pode legitimamente
  responder em texto.
- Reproduzido no CT254 com o env do serviço: `gemini-2.5-flash` →
  `[degraded] tool calling — the model answered without calling the tool`, e o
  `PreflightReport.ok` continua verdadeiro. O console é quem trava.
- A lista de modelos é estática em `core/llm/onboarding/gemini.py:28-33` — seis
  nomes.
- `GET https://generativelanguage.googleapis.com/v1beta/models` com a chave do
  deployment listou **37 modelos** com `generateContent` em 2026-08-16,
  incluindo `gemini-3.5-flash`, `gemini-3.6-flash` e `gemini-3.7-flash`.
- A listagem roda no gateway, com a credencial do vault, pelo credential proxy.
  Nunca no browser.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A lista de modelos vem do endpoint que serve os modelos (Priority: P1)

Um operador cola a chave do provider e abre o seletor de modelo. O que aparece é
o que aquele endpoint serve hoje, com o nome que o vendor dá a cada modelo — não
um catálogo que este build guardou há duas gerações.

**Why this priority**: é a diferença entre um produto configurável e um produto
em que a escolha certa não está na lista. O deployment corrente ganhou
`gemini-3.7-flash` sem que o console soubesse que ele existe.

**Independent Test**: com a chave armazenada, abrir Models & providers e
confirmar que a lista oferecida é a da API, curada para modelos de texto
generativos, e que `Reload models` a recarrega.

**Acceptance Scenarios**:

1. **Given** um provider com credencial armazenada, **When** a tela de modelos
   abre, **Then** o seletor lista os modelos que o endpoint serve, cada um pelo
   nome de exibição que a API devolve.
2. **Given** a listagem já feita há menos que o TTL, **When** a tela abre de
   novo, **Then** nenhuma nova chamada sai para o vendor.
3. **Given** a lista em cache, **When** o operador aciona `Reload models`,
   **Then** a listagem é refeita ignorando o cache.
4. **Given** um endpoint de listagem que responde erro, **When** a tela abre,
   **Then** ela mostra a lista estática do registry, **rotulada como estática**,
   e diz que não conseguiu perguntar ao endpoint.
5. **Given** a lista da API, **When** ela é curada, **Then** modelos de imagem,
   áudio/TTS, robótica, música e embedding ficam fora, e os aliases `-latest`
   ficam dentro.

---

### User Story 2 - A verificação força a chamada, então o veredito é verdade (Priority: P1)

Um operador roda a verificação e o resultado descreve o que o modelo fez quando
não teve escolha: com a chamada de ferramenta forçada, um modelo que ainda assim
responde em texto está reprovado, e não meramente "degradado".

**Why this priority**: hoje o setup nunca fecha. O probe pede a chamada em modo
`AUTO`, o modelo responde em prosa dentro do que aquele modo permite, o backend
registra `degraded`, e o console traduz `degraded` como `Failing`. O operador vê
uma reprovação que o backend não emitiu, sobre um modelo que talvez funcione.

**Independent Test**: capturar o request do probe e confirmar a forçagem; rodar
o probe contra um duplo que responde texto e confirmar `failed`; rodar contra um
descriptor com `supports_tools=false` e confirmar `degraded`.

**Acceptance Scenarios**:

1. **Given** o probe de tool calling, **When** ele monta o request para Gemini,
   **Then** o payload carrega `functionCallingConfig.mode: "ANY"`.
2. **Given** o probe de tool calling, **When** ele monta o request para os demais
   providers, **Then** o payload carrega o equivalente de `tool_choice` que
   obriga a chamada naquele wire.
3. **Given** uma invocação comum (não o probe), **When** ela monta o request,
   **Then** a forçagem não aparece — o modo continua o de antes.
4. **Given** a chamada forçada, **When** a resposta não traz tool call,
   **Then** o check é `failed`.
5. **Given** um descriptor que declara `supports_tools=false`, **When** o probe
   corre, **Then** o check é `degraded` e nenhuma chamada é gasta.
6. **Given** uma verificação que reprova por modelo, **When** o veredito é
   montado, **Then** os modelos alternativos vêm da listagem curada.

---

### User Story 3 - A tela Models & providers mostra o estado que o backend produziu (Priority: P1)

A tela M1 abre com um card de estado no topo: nome do provider, o chip do
resultado da última verificação, e a ação de verificar de novo. Quando algo não
passou, o erro tem hierarquia — o quê, a consequência, a saída.

**Why this priority**: é onde o operador vai quando o setup o manda escolher
outro modelo. Hoje ele encontra um parágrafo de três linhas sem hierarquia,
`google_gemini` cru no texto de erro e "Set at Set at:".

**Independent Test**: abrir `/settings/models-providers` com uma verificação
degradada registrada e confirmar chip, hierarquia do erro, linha de herança
única e papéis avançados colapsados.

**Acceptance Scenarios**:

1. **Given** uma verificação degradada registrada, **When** a tela abre,
   **Then** o card de topo mostra o nome de exibição do provider, o chip
   `Degraded` e a ação `Check again`.
2. **Given** o mesmo estado, **When** o bloco de erro é lido, **Then** ele traz
   um chip nomeando o check, uma frase de consequência e um link com verbo.
3. **Given** qualquer estado, **When** a tela é lida inteira, **Then** o
   identificador cru do provider não aparece em nenhum texto visível.
4. **Given** a linha de herança, **When** ela é lida, **Then** "Set at" aparece
   uma vez só, com a ação de voltar a herdar ao lado.
5. **Given** os papéis avançados, **When** a tela abre, **Then** eles ocupam uma
   linha colapsada que diz quantos são e que herdam o padrão.

---

### User Story 4 - O passo Verify do setup não prende quem está degradado (Priority: P1)

No passo Verify do wizard, cada dependência é uma linha com chip, nome de
exibição e o tempo que levou para responder. O rodapé conta os degradados, e
`Continue` só é segurado por uma falha de verdade.

**Why this priority**: os dois incidentes do dashboard estão mortos há cinco
dias e o setup não fecha. O backend já não bloqueia; era a UI que prendia.

**Independent Test**: rodar o passo com um provider degradado e duas integrações
verificadas, e confirmar que `Continue` está liberado; trocar o degradado por um
`failed` e confirmar que passa a segurar.

**Acceptance Scenarios**:

1. **Given** o passo Verify, **When** ele lista as dependências, **Then** cada
   uma é uma linha com chip, nome de exibição e a latência da resposta.
2. **Given** um provider degradado e nenhum falhando, **When** o rodapé é lido,
   **Then** ele diz quantos checks estão degradados e que nenhum está falhando.
3. **Given** esse mesmo estado, **When** o operador olha `Continue`, **Then** a
   ação está liberada.
4. **Given** um check `failed`, **When** o operador olha `Continue`, **Then** a
   ação está segurada e a linha que a segura está identificada.
5. **Given** as linhas do passo, **When** os nomes são lidos, **Then** são nomes
   de exibição — nenhum identificador cru de integração.

### Edge Cases

- **Chave inválida**: a listagem volta 401. A tela mostra o estado da credencial
  e a saída (rever a chave), não uma lista vazia sem explicação.
- **Listagem vazia depois da curadoria**: trata-se como listagem indisponível —
  cai na lista estática rotulada, e diz por quê.
- **Modelo configurado que o endpoint não oferece mais**: o valor efetivo
  continua visível e selecionado, marcado como não oferecido pelo endpoint
  agora; nada é apagado por baixo do operador.
- **Provider sem endpoint de listagem** (local, por exemplo): a ausência é
  declarada pelo próprio provider e a tela cai no estático rotulado, sem ramo
  especial por vendor.
- **Listagem lenta**: há um limite de espera declarado; estourado, o
  comportamento é o do fallback, e a tela não fica presa.
- **Troca de modelo com verificação em curso**: um resultado que chegou depois
  da troca não é atribuído ao modelo novo.
- **Duas sessões**: o cache da lista é do deployment por provider, não do
  browser; um `Reload models` de uma sessão serve a outra.
- **Verificação sem credencial**: o check de credencial reprova primeiro e a
  tela não manda trocar de modelo — o problema não é o modelo.

## Requirements *(mandatory)*

### Listagem dinâmica de modelos

- **FR-001**: O produto DEVE obter a lista de modelos de um provider perguntando
  ao endpoint daquele provider.
- **FR-002**: A listagem DEVE usar a credencial armazenada no vault.
- **FR-003**: A chamada de listagem DEVE sair pelo credential proxy.
- **FR-004**: A listagem NÃO DEVE ser feita a partir do browser.
- **FR-005**: A listagem DEVE ser um contrato por provider, com uma
  implementação por provider e nenhum ramo por vendor nas superfícies.
- **FR-006**: `google_gemini` DEVE ser a primeira implementação desse contrato.
- **FR-007**: Um provider que não sabe listar DEVE declarar isso, e essa
  declaração DEVE ser indistinguível de uma falha de listagem para quem consome.
- **FR-008**: A lista devolvida DEVE ser curada para modelos de texto
  generativos.
- **FR-009**: A curadoria DEVE excluir modelos de imagem.
- **FR-010**: A curadoria DEVE excluir modelos de áudio e fala.
- **FR-011**: A curadoria DEVE excluir modelos de robótica.
- **FR-012**: A curadoria DEVE excluir modelos de música.
- **FR-013**: A curadoria DEVE excluir modelos de embedding.
- **FR-014**: A curadoria DEVE manter os aliases `-latest`.
- **FR-015**: A curadoria NÃO DEVE usar suporte a tool calling como critério —
  essa capacidade é estabelecida pela verificação, não pela lista.
- **FR-016**: Cada modelo listado DEVE trazer o nome de exibição que a API
  devolve.
- **FR-017**: A lista DEVE ser cacheada por deployment e provider.
- **FR-018**: O tempo de vida do cache DEVE ser uma constante nomeada em um só
  módulo dono, nunca um literal no ponto de uso.
- **FR-019**: O operador DEVE poder recarregar a lista sob demanda, ignorando o
  cache.
- **FR-020**: Quando a listagem falhar, o produto DEVE cair para a lista
  declarada estaticamente.
- **FR-021**: O fallback DEVE ser rotulado como estático na tela.
- **FR-022**: O registry estático NÃO DEVE ser a fonte da lista quando a
  listagem responde; ele permanece como enriquecimento (preço, janela de
  contexto) e como fallback.
- **FR-023**: A espera pela listagem DEVE ter limite declarado como constante
  nomeada.

### Probe honesto

- **FR-024**: O probe de tool calling DEVE obrigar o modelo a chamar a
  ferramenta.
- **FR-025**: Para Gemini, essa obrigação DEVE ser `functionCallingConfig.mode:
  "ANY"` no request do probe.
- **FR-026**: Para os demais providers, essa obrigação DEVE ser o equivalente de
  `tool_choice` do wire correspondente.
- **FR-027**: A obrigação DEVE ser uma propriedade do pedido, não do adaptador,
  para que uma invocação comum continue com o comportamento de hoje.
- **FR-028**: Com a chamada obrigada, uma resposta sem tool call DEVE produzir o
  status `failed`.
- **FR-029**: Um descriptor que declara não suportar ferramentas DEVE continuar
  produzindo `degraded`, sem gastar chamada.
- **FR-030**: Toda mensagem do produto que afirme que o endpoint não pôde ser
  perguntado quais outros modelos serve DEVE deixar de ser emitida quando a
  listagem está disponível.
- **FR-031**: Os modelos alternativos citados numa reprovação DEVEM vir da
  listagem curada.

### Estado espelhado, sem tradução

- **FR-032**: A resposta de verificação servida às telas DEVE carregar o
  resultado de cada check individualmente.
- **FR-033**: Cada resultado DEVE carregar o nome do check.
- **FR-034**: Cada resultado DEVE carregar o status que o preflight produziu.
- **FR-035**: Cada resultado DEVE carregar o detalhe que o preflight escreveu.
- **FR-036**: Cada resultado DEVE carregar quanto tempo aquele check levou.
- **FR-037**: O vocabulário de estado do produto DEVE conter cinco palavras:
  Not connected, Stored, Verified, Degraded, Failing (e o par pt-BR: Não
  conectada, Armazenada, Verificada, Degradada, Falhando).
- **FR-038**: Nenhuma tela DEVE renderizar um estado degradado com a palavra de
  falha.
- **FR-039**: Nenhuma tela DEVE inventar uma sexta palavra de estado.
- **FR-040**: Um estado degradado NÃO DEVE bloquear o operador.
- **FR-041**: Um estado degradado DEVE declarar a consequência de continuar.
- **FR-042**: Um estado degradado DEVE oferecer uma saída redigida com verbo.
- **FR-043**: Um estado falho DEVE bloquear o operador.

### Tela Models & providers (âncora `#m1`)

- **FR-044**: A tela DEVE abrir com um card de estado no topo.
- **FR-045**: O card DEVE mostrar o nome de exibição do provider.
- **FR-046**: O card DEVE mostrar o chip do resultado da última verificação.
- **FR-047**: O card DEVE oferecer a ação de verificar de novo.
- **FR-048**: O bloco de erro DEVE nomear o check que não passou num chip.
- **FR-049**: O bloco de erro DEVE declarar a consequência numa frase.
- **FR-050**: O bloco de erro DEVE oferecer a saída como link com verbo.
- **FR-051**: O identificador cru do provider NÃO DEVE aparecer em texto visível
  desta tela.
- **FR-052**: A linha de herança DEVE dizer "Set at" uma única vez.
- **FR-053**: A ação de voltar a herdar o padrão DEVE ficar ao lado da linha de
  herança.
- **FR-054**: Os papéis avançados DEVEM ocupar uma linha colapsada.
- **FR-055**: Essa linha DEVE declarar quantos papéis são e que herdam o padrão
  do investigator.
- **FR-056**: O seletor de modelo DEVE mostrar o nome de exibição do modelo.
- **FR-057**: Salvar e verificar DEVE continuar sendo a ação primária, e testar
  sem salvar a secundária.

### Passo Verify do setup (âncora `#m5`)

- **FR-058**: O passo DEVE mostrar uma linha por dependência verificável.
- **FR-059**: Cada linha DEVE trazer o chip do estado.
- **FR-060**: Cada linha DEVE trazer o nome de exibição da dependência.
- **FR-061**: Cada linha DEVE trazer o tempo que a dependência levou para
  responder.
- **FR-062**: O rodapé DEVE dizer quantos checks estão degradados.
- **FR-063**: O rodapé DEVE dizer que nenhum está falhando, quando nenhum está.
- **FR-064**: A contagem do rodapé DEVE concordar em número com o que conta.
- **FR-065**: `Continue` DEVE ficar liberado quando só há degradados.
- **FR-066**: `Continue` DEVE ficar segurado quando há uma falha.
- **FR-067**: Quando `Continue` está segurado, a linha responsável DEVE estar
  identificada.

### Segurança

- **FR-068**: Nenhuma resposta servida ao browser DEVE conter a credencial do
  provider.
- **FR-069**: Nenhum log emitido pela listagem DEVE conter a credencial.
- **FR-070**: Nenhum trace ou relatório DEVE conter a credencial.
- **FR-071**: A listagem DEVE exigir a mesma autorização que ler configuração.

### Fronteiras (o que esta feature não faz)

- **FR-072**: A contagem única de passos do setup ("Step 5 of 7" × "N steps
  left") pertence à feature 020 e NÃO DEVE ser reimplementada aqui; esta feature
  consome a contagem que a 020 estabelece e não introduz uma segunda.
- **FR-073**: A varredura geral de vocabulário cru fora destas duas telas
  pertence à 030 e NÃO DEVE ser antecipada aqui.
- **FR-074**: O corte do catálogo de integrações pertence à 001 e é
  pré-requisito desta feature, não escopo dela.

### Key Entities

- **Modelo oferecido**: identificador, nome de exibição, origem (endpoint ou
  lista estática), e o que o registry sabe sobre ele (preço, janela) quando sabe.
- **Resultado de check**: nome, status (passou · degradado · falhou), detalhe,
  duração.
- **Veredito de verificação**: provider, modelo exercitado, se satisfaz o
  contrato, limitação, remédio, alternativas, e os resultados de check que o
  compõem.
- **Lista em cache**: provider, momento da coleta, validade, origem.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Depois de colada a chave, escolher e verificar um modelo custa no
  máximo **3 ações** do operador.
- **SC-002**: A lista oferecida para `google_gemini` contém `gemini-3.7-flash` e
  **zero** modelos de imagem, áudio, robótica, música ou embedding — medido
  contra a fixture dos 37 nomes reais colhidos em 2026-08-16.
- **SC-003**: Com a chave real no CT254, escolher `gemini-3.7-flash`, verificar,
  e o passo Verify fechar **sem nenhuma ocorrência de "Failing"** para um estado
  que o backend reportou como degradado.
- **SC-004**: Zero ocorrências, no HTML servido das duas telas, das strings
  `google_gemini`, `Set at Set at` e `could not be asked what else it serves`.
- **SC-005**: 100% dos checks que o preflight produz aparecem na tela com o
  mesmo status que o backend emitiu — nenhum estado inventado, nenhum omitido.
- **SC-006**: Um modelo que responde sem chamar a ferramenta sob chamada
  obrigada é reprovado (`failed`) em 100% das execuções do teste do probe;
  um descriptor sem suporte declarado produz `degraded` em 100%.
- **SC-007**: A credencial do provider não aparece em nenhum payload servido ao
  browser nem em nenhuma linha de log da listagem — asserção executável.
- **SC-008**: Com a listagem indisponível, a tela continua utilizável e declara
  que a lista é a estática, em 100% das execuções do teste de fallback.
- **SC-009**: Duas aberturas da tela dentro do TTL produzem **uma** chamada ao
  endpoint de listagem; um `Reload models` produz exatamente mais uma.
- **SC-010**: O passo Verify com um degradado e nenhum falhando permite
  continuar; com um falhando, não permite — nas duas direções, medido.

## Assumptions

- O deployment tem uma credencial de provider armazenada no vault; a spec não
  cobre o fluxo de armazenar a chave, que já existe.
- A rota de verificação continua sendo acionada por gesto do operador, porque
  gasta tokens. A listagem não gasta tokens e por isso pode acompanhar a
  renderização da tela, sob cache.
- O registry de modelos continua sendo a fonte de preço e janela de contexto.
- Os papéis de modelo (investigator e os sete avançados) permanecem como estão;
  esta feature não muda quantos são nem o que fazem.
- O vocabulário de estado ganha `Degraded`/`Degradada` como palavra canônica;
  as outras quatro já existem.

## Dependencies

- **001** (escopo validável): o conjunto de integrações que o passo Verify lista
  é o pós-corte.
- **020**: dona da contagem única do setup — esta feature muda o *conteúdo* do
  passo Verify, não a contagem.
- **060** depende desta: sem provider verificado, não há investigação para o
  primeiro incidente.
