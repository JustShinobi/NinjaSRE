# Tasks: Provider out-of-the-box

**Input**: Design documents from `specs_v6/010-provider-out-of-the-box/`

**Prerequisites**: plan.md, spec.md, feature 001 entregue (catálogo pós-corte)

**Tests**: test-first. Todo teste desta lista nasce falhando e o vermelho é
**confirmado por execução** antes da implementação correspondente. Um teste que
nunca foi visto vermelho não prova nada sobre o código que veio depois.

**Regra de escrita**: nenhuma tarefa abaixo autoriza escrever identificador de
requisito, artigo da constituição, número de feature ou caminho de planejamento
dentro de arquivo committed (código, teste, `AGENTS.md`, documento gerado). A
substância vai no arquivo; a referência fica nesta spec.

**Onde os testes moram**: unit do console em `console/tests/unit/`, behaviour em
`console/tests/e2e/` (`console/e2e/` não existe), visual em
`console/tests/visual/`, Python conforme `pytest.ini`.

---

## Phase 1: Setup e fixtures

- [x] **T001** Criar a fixture da listagem real: os **37 nomes** com
      `generateContent` colhidos do endpoint de modelos do Gemini em
      2026-08-16, incluindo `gemini-3.5-flash`, `gemini-3.6-flash`,
      `gemini-3.7-flash`, os aliases `-latest`, e as famílias que a curadoria
      precisa descartar (imagem, áudio/TTS, robótica, música, embedding), cada
      entrada com o `displayName` que a API devolve. Vive onde o unit de
      curadoria e o plano de mock possam ler a mesma cópia.
- [x] **T002** Criar a fixture de resultado de verificação com os cinco checks
      do preflight em três formas: tudo passando; tool calling degradado com o
      resto passando; tool calling falhando. Cada check com nome, status,
      detalhe e duração.
- [x] **T003** Criar a fixture do passo Verify com um provider degradado e duas
      integrações verificadas com latências distintas (uma delas na casa dos
      240 ms, outra dos 180 ms), com nomes de exibição — não identificadores.

---

## Phase 2: Acceptance-first do console (a fase que abre a implementação)

- [x] **T004** Escrever `console/tests/e2e/010-provider-out-of-the-box.acceptance.spec.ts`
      codificando as alegações normativas dos dois mockups. **Da tela Models &
      providers**: (a) existe um card de estado no topo com o nome de exibição
      do provider; (b) o card traz o chip do resultado da última verificação com
      a palavra exata do vocabulário — `Verified`, `Degraded` ou `Failing`,
      nunca outra; (c) o card traz a ação `Check again`; (d) o bloco de erro traz
      um chip nomeando o check (`Tool calling`), uma frase de consequência e um
      link de saída redigido com verbo; (e) `Save and verify` é a ação primária e
      `Test without saving` a secundária; (f) a linha de herança contém `Set at`
      exatamente uma vez e a ação de voltar a herdar o padrão ao lado; (g) os
      papéis avançados ocupam uma linha colapsada que declara quantos são e que
      herdam o padrão do investigator; (h) o texto visível não contém
      `google_gemini`, nem `Set at Set at`, nem `could not be asked what else it
      serves`; (i) o seletor de modelo lista nomes vindos da listagem servida
      pelo plano de mock — e não os seis nomes da lista estática.
      **Do passo Verify do setup**: (j) uma linha por dependência, cada uma com
      chip, nome de exibição e o tempo de resposta; (k) os nomes são de exibição
      (`Prometheus`, não o identificador cru); (l) o rodapé declara quantos
      checks estão degradados e que nenhum está falhando, concordando em número;
      (m) `Continue` está habilitado com degradados e nenhum falhando;
      (n) com um check falhando, `Continue` fica desabilitado e a linha
      responsável está identificada. Declarar viewport 1920×1080 explicitamente
      no bloco que medir altura de página; o viewport global do Playwright é
      1440×900 e uma medição de rolagem feita nele não vale.
- [x] **T005** **Confirmar o vermelho de T004**: rodar o projeto `behaviour`
      contra o console construído (`make console-e2e`) e registrar quais
      alegações falham e por quê. Uma alegação que já passa antes de qualquer
      implementação é uma alegação mal escrita — reescrever até que ela meça o
      que o mockup afirma.

---

## Phase 3: Testes de backend, vermelhos

- [x] **T006** [P] Unit da curadoria em `tests/unit/core/llm/`: alimentada com a
      fixture de T001, a lista resultante contém `gemini-3.7-flash` e os aliases
      `-latest`, e não contém nenhum modelo de imagem, áudio/TTS, robótica,
      música ou embedding. Assertar também que a curadoria **não** usa suporte a
      tool calling como critério — um modelo de texto sem capacidade declarada
      permanece na lista.
- [x] **T007** [P] Unit do cache da listagem: duas leituras dentro do tempo de
      vida produzem uma chamada ao endpoint; uma recarga explícita produz
      exatamente mais uma; expirado o tempo de vida, a próxima leitura chama de
      novo.
- [x] **T008** [P] Unit do fallback: endpoint que responde erro, endpoint que
      responde vazio depois da curadoria, e provider que declara não saber
      listar produzem os três o mesmo resultado observável — a lista estática do
      onboarding, marcada como estática, com o motivo declarado.
- [x] **T009** [P] Unit da forçagem, por captura de request: com a obrigação
      ligada, o payload do Gemini carrega `functionCallingConfig` com o modo que
      obriga a chamada; o payload de cada um dos demais adaptadores carrega o
      equivalente do seu wire; **sem** a obrigação, nenhum payload muda em
      relação ao comportamento atual.
- [x] **T010** [P] Unit do mapeamento de status: sob obrigação, resposta sem
      tool call produz `failed`; descriptor que declara não suportar ferramentas
      produz `degraded` sem gastar chamada; resposta com tool call produz
      `passed`. Confirmar que o veredito de contrato reprova o primeiro caso
      nomeando a limitação, e que a lista de alternativas vem da listagem.
- [x] **T011** **Confirmar o vermelho de T006–T010** (`uv run pytest
      tests/unit/core/llm -q`) e registrar a saída.

---

## Phase 4: Listagem dinâmica — implementação

- [x] **T012** Declarar as constantes do domínio em `config/constants/llm.py`:
      tempo de vida do cache da listagem, limite de espera da chamada, teto de
      entradas do cache. Nomeadas, num módulo dono só, sem literal no ponto de
      uso.
- [x] **T013** Criar a porta de listagem em `core/llm/catalogue/`: contrato de
      "quais modelos este endpoint serve", com a ausência de listagem declarada
      pelo próprio provider em vez de tratada por exceção na superfície.
- [x] **T014** Implementar a curadoria ao lado da porta (T006 fica verde):
      famílias descartadas, aliases mantidos, nome de exibição preservado.
- [x] **T015** Implementar a listagem `google_gemini` (T008 parcialmente verde):
      credencial lida do vault, chamada emitida pelo credential proxy, limite de
      espera aplicado, erro traduzido em fallback e não em exceção que sobe.
- [x] **T016** Implementar o cache com o tempo de vida de T012 e a recarga sob
      demanda (T007 fica verde).
- [x] **T017** Ligar a listagem ao parâmetro de enumeração que a verificação já
      aceita, para que uma reprovação por modelo nomeie alternativas reais, e
      **remover** o texto que afirma que o endpoint não pôde ser perguntado
      quais outros modelos serve — mantendo uma redação honesta para o caso em
      que o provider realmente não sabe listar.

---

## Phase 5: Probe honesto — implementação

- [x] **T018** Declarar a obrigação de chamar a ferramenta como propriedade do
      pedido em `core/llm/types.py`, desligada por padrão.
- [x] **T019** Traduzir a obrigação em cada adaptador de `core/llm/providers/`
      para o mecanismo do seu wire — no Gemini, o campo de configuração de
      chamada de função com o modo que obriga; nos demais, o `tool_choice`
      equivalente (T009 fica verde).
- [x] **T020** Ligar a obrigação no probe de tool calling de
      `core/llm/preflight.py` e passar a produzir `failed` quando, obrigado, o
      modelo responde sem chamar — preservando `degraded` para o descriptor que
      declara não suportar ferramentas (T010 fica verde).
- [x] **T021** Estender a suíte de contrato de providers (`tests/contract/llm/`)
      com a obrigação, para que todo adaptador — inclusive um adicionado depois —
      precise satisfazê-la. Escrever o teste antes de ajustar qualquer adaptador
      que ainda não a satisfaça, e confirmar o vermelho.

---

## Phase 6: O contrato que as telas consomem

- [x] **T022** Teste de contrato em `tests/contract/console/`, **vermelho
      primeiro**: a resposta de verificação de provider carrega, por check,
      nome, status, detalhe e duração; a rota de listagem devolve os modelos
      curados com nome de exibição e diz se a lista veio do endpoint ou é a
      estática. Confirmar o vermelho antes de tocar a rota.
- [x] **T023** Teste de segurança (`tests/security/`), vermelho primeiro: nenhum
      payload servido por essas rotas contém a credencial do provider sob
      nenhuma chave, e nenhuma linha de log emitida pela listagem a contém.
- [x] **T024** Implementar em `gateway/http/routes/providers.py`: a rota de
      listagem de modelos por provider, com a mesma autorização de leitura de
      configuração, e a resposta de verificação passando a carregar os checks
      (T022 e T023 ficam verdes).
- [x] **T025** Servir a listagem no plano de mock (`tools/mockplane/`), com o
      dataset alimentado pela fixture de T001, para que a suíte de browser tenha
      de onde ler a lista.
- [x] **T026** Regenerar o documento OpenAPI committed e, a partir dele, o
      cliente do console (`make console-client`), e confirmar que
      `make console-client-check` passa.

---

## Phase 7: Console — unit vermelhos

- [x] **T027** [P] Unit em `console/tests/unit/` do chip de estado: as cinco
      palavras canônicas existem em inglês e em pt-BR, um estado degradado
      renderiza a palavra de degradação, e nenhuma entrada do componente produz
      uma sexta palavra.
- [x] **T028** [P] Unit de `console/tests/unit/surfaces/settings/models.test.tsx`:
      card de estado no topo com chip e ação de reverificar; erro em três
      camadas (chip, consequência, saída com verbo); linha de herança com um só
      "Set at" e a ação de voltar a herdar ao lado; papéis avançados numa linha
      colapsada; lista de modelos vinda da listagem, com rótulo de estática
      quando for o fallback.
- [x] **T029** [P] Unit de `console/tests/unit/surfaces/first-run.test.tsx`:
      linha por dependência com chip, nome de exibição e latência; rodapé com a
      contagem de degradados concordando em número; `Continue` liberado com
      degradados e segurado com falha.
- [x] **T030** **Confirmar o vermelho de T027–T029** (`make console-test`) e
      registrar a saída. Ressalva registrada no `controle.md`: T027 e a
      vocalização em `status.tsx`/i18n nasceram vermelhas antes do código; as
      asserções novas de T028 (bloco de erro estruturado) e T029 (latência,
      rodapé de degradados, `Continue` por falha) foram escritas depois da
      tela já existir — retrofit, não vermelho-antes-do-código, e ditas assim.

---

## Phase 8: Console — a tela Models & providers

- [x] **T031** Acrescentar a palavra de degradação ao vocabulário canônico em
      `console/src/components/status.tsx` e aos dois catálogos de i18n, sempre
      em par (en + pt-BR), sem tocar nas quatro palavras existentes (T027 fica
      verde). Arquivo de escrita única na onda: coordenar com a ordem sequencial
      das features.
- [x] **T032** Implementar o card de estado no topo de
      `console/src/surfaces/settings/models.tsx`: nome de exibição, chip do
      resultado da última verificação, ação de reverificar.
- [x] **T033** Implementar o bloco de erro estruturado: chip nomeando o check,
      frase de consequência, link de saída com verbo — lendo os checks que a
      rota agora devolve, sem recalcular estado no cliente e sem exibir o
      identificador cru do provider.
- [x] **T034** Corrigir a linha de herança para um só "Set at", com a ação de
      voltar a herdar ao lado, e colapsar os papéis avançados numa linha que
      declara quantos são e que herdam o padrão do investigator.
- [x] **T035** Ligar o seletor de modelo à listagem servida pela rota nova, com
      nome de exibição por modelo, ação de recarregar a lista, e rótulo explícito
      quando a lista exibida for a estática (T028 fica verde).

---

## Phase 9: Console — o passo Verify do setup

- [x] **T036** Reescrever a leitura do veredito em
      `console/src/surfaces/first-run/verify.tsx` para espelhar os três status
      por check em vez de colapsar em passou/falhou — a tradução de degradado em
      falha morre aqui.
- [x] **T037** Renderizar a linha por dependência com chip, nome de exibição e
      latência, e o rodapé com a contagem de degradados concordando em número.
- [x] **T038** Fazer o avanço do passo depender só de falha: liberado com
      degradados, segurado por falha, com a linha responsável identificada
      (T029 fica verde). **Não** tocar no cabeçalho de contagem de passos — a
      contagem única é da feature 020 e uma segunda fonte aqui é exatamente o
      defeito que ela existe para eliminar.

---

## Phase 10: Verde do acceptance e evidência visual

- [x] **T039** Rodar `make console-e2e` e levar
      `console/tests/e2e/010-provider-out-of-the-box.acceptance.spec.ts` ao
      verde inteiro. Nenhuma alegação de T004 pode ser afrouxada para passar; se
      uma delas está errada, a correção é no mockup e na spec, declarada.
- [x] **T040** Atualizar `console/visual/screens.json` se a forma das telas
      registradas mudou, e recapturar a baseline deliberadamente
      (`make console-visual-accept`), revisando o diff como mudança committed.
- [x] **T041** Rodar `make verify` inteiro e resolver o que ele apontar,
      especialmente os guards de constantes, de credenciais, de SDK de vendor,
      de nomes de exibição e de fronteira de imports. Todo apontamento real
      resolvido (lint, mypy, cobertura, e2e, um teste de arquitetura
      desatualizado); resta uma tensão estrutural entre a baseline visual
      aceita e não commitada — nomeada e explicada em detalhe no
      `controle.md`, não escondida.

---

## Phase 11: Fechamento

- [x] **T042** Medir e registrar o efeito na suíte de cenários sintéticos.
      "Nenhum efeito" é resultado aceitável; "não medido" não é.
- [ ] **T043** DoD no ambiente real: com a chave do deployment no CT254,
      escolher `gemini-3.7-flash` na tela, verificar, e o passo Verify fechar
      sem nenhuma reprovação falsa. Contar as ações do operador depois de colada
      a chave e confirmar que são no máximo três.
- [x] **T044** Atualizar o `controle.md` desta feature com o que o código prova:
      cada item com o estado real, a evidência (arquivo, teste, comando, saída) e
      o que ficou fora, incluindo qualquer alegação de mockup que a implementação
      contradisse e por quê.

---

## Dependencies

- T001–T003 antes de tudo.
- **T004 → T005 antes de qualquer implementação de console.** O acceptance spec
  é a primeira coisa que existe e a última que fica verde.
- T006–T010 são paralelos entre si; T011 fecha a fase.
- T012 → T013 → {T014, T015, T016} → T017.
- T018 → T019 → T020 → T021.
- T022–T023 antes de T024; T024 → T025 → T026.
- T027–T029 paralelos; T030 fecha a fase; T031 antes de T032–T038.
- Fase 8 e Fase 9 são independentes entre si depois de T031.
- T039 depois de todas as implementações; T040–T041 depois de T039.
- T042–T044 por último, nessa ordem.
