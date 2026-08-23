# Controle — 030 First steps (o funil)

> Verificado por confronto em 2026-08-13, em duas passagens. A primeira
> corrigiu F6 parcialmente e deixou o critério de aceite 6 aberto sem o
> dizer; a segunda, pedida pelo coordenador, fechou os quatro itens que
> ficaram por fazer. Ver `relatorio-confronto.md` para a evidência linha a
> linha de cada veredito — nenhuma linha aqui foi aceite pelo hash do commit
> sozinho, e a segunda passagem está documentada separadamente da primeira,
> não fundida nela.

| Item | Estado | Detalhe |
|---|---|---|
| F1. `nodeId=''` no passo do modelo | **FEITO** (`bf5f055`, confirmado) | `viewerNode()` em `surfaces/tree.tsx:130-137`: team da sessão, ou raiz da árvore de `/v1/config`. Confirmado por leitura do código; nenhuma mudança necessária. |
| F2. Patch achatado recusado pelo schema | **FEITO** (`bf5f055`, confirmado) | `patchOf()` monta o documento aninhado; `errors` do preview aparecem em `model-result` e mantêm o save travado; couriers `/api/config` e `/api/preview` sempre devolvem `reason` textual. Confirmado; nenhuma mudança necessária. Os couriers `/api/credential` e `/api/estate` já extraem a sua própria razão textual corretamente. |
| F3. `modelChosen` lia chave achatada | **FEITO** (`bf5f055`, confirmado) | Leitura aninhada (`valueAt`) derivada da mesma constante da escrita. Confirmado; nenhuma mudança necessária. |
| F4. Verify testava o modelo default do registry | **FEITO** (`b169eae`, confirmado) | `_configured_model` resolve `models.investigator` na raiz da árvore do chamador; o modelo efetivamente testado é gravado por `record_check`. Confirmado ponta a ponta; nenhuma mudança necessária. |
| F5. Resultado de check não persiste | **FEITO** (`4cd17cb`, confirmado) | `VerificationLedger` gravado por `record_check`, lido por `recorded_checks`/`integration_health`, por sua vez lidos por `list_providers`, `show_provider` e `/v1/setup/checklist`. Confirmado ponta a ponta; nenhuma mudança necessária. |
| F6. Runtime do investigador fora do mapa | **FEITO** (`b1ee01e`, `621e132`, + esta confrontação, duas passagens) | O checklist da *plataforma* e o self-check já eram reais. **Primeira passagem** corrigiu três lacunas nunca revistas desde `b1ee01e`: a tela do assistente nunca referenciava o quinto passo (corrigido: bloco explicando o runtime em falta no último passo, sem nomear a variável de ambiente); a tradução de falha `failure.investigator.action` mandava "termine a escolha do modelo" e apontava para um passo já concluído (corrigido: aponta para `/first-run` sem step fixo e nomeia a dependência real); o mock que serve e fotografa esta tela continuava com os quatro passos antigos (corrigido: quinto passo adicionado, três fixtures reconstruídos). **A primeira passagem fechou o item como PARCIAL sem construir o segundo ramo do critério de aceite 6** ("o produto diz, antes do clique, o que falta") — o botão "+ Investigate" continuava sem aviso algum antes do clique, o mesmo defeito que o critério proíbe, nomeado no próprio relatório da primeira passagem sem a conclusão de que isso deixava o item incompleto. **Segunda passagem** (pedida pelo coordenador) construiu esse ramo: `SetupState` ganhou `runtimeComposed`, passado ao `InvestigateDrawer`, que agora desabilita "Start it" e explica o motivo antes do clique — lendo a mesma frase do catálogo (`failure.investigator.action`) que a tradução reativa já usava, para as duas superfícies não poderem discordar sobre o mesmo runtime em falta. Teste-primeiro nas duas passagens, confirmados vermelhos — ver relatório. **Continua fora de escopo, e nunca foi exigido**: compor o runtime automaticamente em produção — o primeiro ramo do critério, marcado "preferível" mas não obrigatório dado o "ou" do próprio critério, e nenhum pacote fora de `tests/` chama `build_pipeline`. |

## Itens de UX da primeira revisão (mesma spec)

| Item | Estado | Detalhe |
|---|---|---|
| Duplicata "Google Gemini" / `google_gemini` no verify | **FEITO** (`abe6017`, confirmado) | `verifiable` e `established` em `first-run.tsx` subtraem o provider corrente da lista de integrações. Confirmado; nenhuma mudança necessária. |
| Modelo default do dropdown falha o próprio verify | **PARCIAL** (confirmado, sem mudança — deixado assim pelo coordenador) | O check já testa o modelo configurado (F4), mas o default do dropdown continua sendo o primeiro modelo do provider; marcar quais opções passam continua pendente. |
| "3 of 7 left" vs "4 of 7 done" | **FEITO** (primeira passagem) | `firstRun.progress` dizia "done", `dashboard.hero.remaining` dizia "steps left" — o mesmo facto, dois enquadramentos. Ambos dizem agora "N of 7 steps left", com o passo do assistente a usar o mesmo `outstanding(setup)` que o dashboard já usava. Teste-primeiro, confirmado vermelho. |
| Marcadores de progresso / estado final com CTA | **FEITO** (duas passagens) | "Você está aqui" resolvido na primeira passagem: o passo corrente na própria tela do assistente ganhou realce visual e o rótulo "You are here" / "Você está aqui" (o cartão do dashboard já tinha isto, de obra alheia a este item). **O estado final continuava não construído após a primeira passagem** — nomeado no relatório, não feito. Segunda passagem construiu-o: um bloco novo diz que a configuração está pronta e nomeia o único controlo que inicia uma investigação, assim que sobra apenas o último passo e nada o bloqueia — e é exatamente aí, quando o runtime é o que falta, que a frase do critério 6 aparece no lugar dele em vez de duplicá-la. |
| Nomes de passo poéticos | **FEITO** (segunda passagem) | A primeira passagem confirmou a queixa ainda viva e deixou-a `NÃO INICIADO` sem registar porquê. Segunda passagem: um mapa do passo para a tela de destino, para os dois passos que de facto entregam a uma tela real ("Continues on Resources" / "Continues on Detectors", lido do mesmo endereço `HANDOVER` que o link já usa) — escolha deliberada entre renomear os sete nomes (uma decisão de tom maior e mais subjetiva) e acrescentar o mapa (o que o coordenador ofereceu como segunda opção, e a que resolve "sem mapa para telas" sem tocar no tom). Os cinco passos que ficam neste mesmo assistente não ganham um destino — inventar um seria pior do que a ausência. |
| Espaço morto na coluna direita / erro numa linha vermelha crua | **PARCIAL** (segunda passagem) | A metade do espaço morto não foi tocada — é uma observação sobre uma grelha já existente antes desta confrontação, não uma correção, e continua registada como tal. A metade da linha vermelha crua foi corrigida nas superfícies do first-run: o resultado do passo do modelo, do formulário de credencial e a recusa do passo de estate deixaram de ser uma única linha distinguida só pela cor — cada uma é agora um aviso emoldurado com ícone, e `role="alert"` em vez de `role="status"` para uma falha genuína, a metade de acessibilidade de "crua" que a cor sozinha nunca alcançava. |

## Achados adicionais desta confrontação (não numerados na spec, nomeados e não corrigidos)

- **Fixture do mockplane desatualizada** (raiz do Gap 3 de F6, corrigida na
  primeira passagem): `checklist_record()` tinha os títulos dos quatro
  passos antigos divergentes da plataforma — deriva de antes do commit
  `b1ee01e`, não é causado por ele, e não foi corrigido porque não é parte
  do diagnóstico de F6. Fica nomeado para quem fizer a próxima passagem de
  higiene de fixtures.
- **Português europeu além de `failure.investigator`**: ao corrigir essa
  chave (nas duas passagens — o texto mudou de novo na segunda, para deixar
  de conter "choosing a model" verbatim, já que passou a ser lido também
  antes do clique), o bloco em redor (`notifications.*`, `failure.store.*`,
  `failure.migrations.*`) revelou os mesmos marcadores que 022 Detectors e
  024 Knowledge já tinham encontrado noutras telas — "de si", "à espera de",
  "está a correr", "base de dados". O mesmo padrão repete-se em
  `dashboard.attention.title`, `dashboard.attention.count` e
  `approvals.empty.heading`, nenhuma delas alcançada pelas telas desta spec.
  Não corrigido — nomeado para quem possuir essas telas.

## O que a primeira passagem deixou em falta, e o que isso ensina

A primeira passagem construiu três correções reais de F6 e depois fechou o
item como PARCIAL sem verificar se o que sobrava — o segundo ramo do
critério de aceite 6 — tinha ficado por fazer. O próprio relatório da
primeira passagem nomeou o sintoma exato ("um operador ainda pode clicar em
Investigate de qualquer lugar e só descobrir que falta o runtime depois da
tentativa") na sua secção "deliberadamente deixado por fazer", sem tirar a
conclusão de que isso tornava o item incompleto contra um critério cujo
primeiro ramo já tinha sido corretamente escopado para fora. A UX5 foi
marcada `NÃO INICIADO` sem nenhuma razão registada, quando a spec pedia
explicitamente uma de duas coisas. A UX4 nomeou a ausência do estado final
sem a construir. A UX6 nomeou a linha vermelha crua sem a corrigir. O
coordenador corrigiu esta confrontação antes de a aceitar; fica registado
aqui para que a próxima confrontação desta série leia "deixado por fazer"
como algo a verificar contra os critérios de aceite antes de fechar um item,
não apenas como um lugar para o anotar.

## Verificação em ambiente real

Console: 121 ficheiros, 1981 testes verdes (1957 antes desta spec, 1972 após
a primeira passagem, 1981 após a segunda). `tsc --noEmit` limpo. `make
console-build` seguido de `make console-visual`: 34 de 35 passaram nas duas
passagens; `first-run-1440-light` diferiu nas duas vezes, como esperado — a
tela mudou de facto em ambas — e as imagens de diferença foram inspecionadas
e mostram exatamente as mudanças pretendidas. Nenhuma baseline foi aceite
por este agente; ficam para o próximo `make console-visual-accept` revisto
por uma pessoa. Python: `tests/contract/fixtures/` e o novo
`tests/unit/tools/mockplane/test_served_checklist.py` — 107 verdes, ambas as
passagens. A falha pré-existente e conhecida,
`test_each_paginated_endpoint_declares_a_style_the_base_client_walks[google_gemini]`,
foi confirmada isolada e não tocada.
