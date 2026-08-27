# Specification Quality Checklist: Regras e governança

**Purpose**: Validar completude e qualidade da especificação antes do planejamento
**Created**: 2026-08-23
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] Sem detalhe de implementação (linguagem, framework, API) nos requisitos
- [x] Focada no valor para quem opera e para quem planeja a onda contra estas regras
- [x] Escrita para quem decide, não só para quem implementa
- [x] Todas as seções obrigatórias preenchidas

## Requirement Completeness

- [x] Nenhum marcador [NEEDS CLARIFICATION] restante
- [x] Requisitos testáveis e sem ambiguidade
- [x] Critérios de sucesso mensuráveis
- [x] Critérios de sucesso agnósticos de tecnologia
- [x] Todos os cenários de aceitação definidos
- [x] Casos de borda identificados
- [x] Escopo claramente delimitado
- [x] Dependências e premissas identificadas

## Feature Readiness

- [x] Todo requisito funcional tem critério de aceitação claro
- [x] Os cenários de usuário cobrem os fluxos primários
- [x] A feature atende os resultados mensuráveis dos critérios de sucesso
- [x] Nenhum detalhe de implementação vazou para a especificação

## Verificações específicas desta feature

- [x] Cada defeito de governança que a spec afirma foi conferido na árvore em
      2026-08-23 e está cravado em arquivo e linha, não copiado de documento
- [x] A descoberta que muda o desenho da emenda pendente está declarada: o artigo
      de capacidades **não tem cláusula de paridade nenhuma**, então a emenda
      acrescenta em vez de reescrever
- [x] Os dois exemplos que a auditoria de regras acusava de defasados foram
      conferidos e estão corretos; a spec registra isso como resultado da
      auditoria em vez de dispensá-la
- [x] Os dois aumentos de versão estão justificados um a um contra a regra de
      versionamento do próprio documento, e o destino da regra nova (artigo
      próprio, não cláusula no artigo de test-first) tem razão escrita
- [x] Nenhum requisito instrui escrever identificador de requisito, número de
      artigo, número de feature ou caminho de planejamento em arquivo committed
- [x] A allowlist de partida é enumerada — nove pares rota × regra —, cada um com
      a razão derivada do diagnóstico, e o número é um critério de sucesso
- [x] A mecânica do vermelho está definida e é reproduzível sem staging: um
      cenário de dados derivado do cenário cheio, committed, alterando só os
      endpoints que precisam mudar
- [x] Está declarado que **nenhuma tela viola os bans contra o dataset
      determinístico de hoje** — o que é a razão de o cenário violador existir e
      de a allowlist valer contra o ambiente real
- [x] Cada um dos cinco bans é uma alegação individualmente testável, sem duas
      obrigações numa vírgula
- [x] O viewport normativo de medição está declarado (1920×1080)
- [x] A superfície de segredo do backing novo está tratada como requisito, não
      como cuidado: leitura do ambiente, nunca gravada, nunca impressa, nunca em
      argumento de processo, com recusa nomeada na ausência
- [x] A declaração de "seguro para ambiente compartilhado" é fail-closed e por
      teste, e o significado da marca é enunciado onde ela é declarada
- [x] Está declarado que esta feature não toca nenhum arquivo de escrita única e
      que roda sozinha no slot S0
- [x] Está declarado que esta feature não toca nenhuma composition root de
      serving, com a razão pela qual isso não é evasão da regra que ela escreve
- [x] O que a feature encontrou e deliberadamente **não** conserta está em Out of
      Scope, com razão

## Notes

- **Descoberta que o briefing não previa, e que a spec absorve.** O registro de
  decisão vigente sobre paridade diz, em texto committed, que a amplitude corrente
  do catálogo se lê numa seção do roadmap. Essa seção não existe: o roadmap não
  tem nenhuma ocorrência de conjunto embarcado nem de conjunto diferido. É um
  ponteiro quebrado dentro do material committed, escrito pela decisão que governa
  o catálogo, e cai exatamente no mandato desta feature. Entrou como história P2 e
  como fase própria, tardia, para poder ser reportada separadamente se o slot
  apertar.
- **Duas coisas que a onda anterior deu por feitas e não estão na árvore.** A
  emenda da constituição e a reclassificação do registro de paridade total
  constam como concluídas no plano de tarefas daquela feature, e nenhuma das duas
  está no disco: a constituição segue em 2.0.0 sem cláusula de paridade, e o
  registro segue como aceito. O mesmo vale para o acerto do roadmap. Esta feature
  as escreve; **por que elas se perderam é pergunta para o operador**, e vale
  responder antes de a onda usar worktrees paralelas outra vez, porque a forma da
  perda é compatível com um merge de worktree que descartou o que não estava
  commitado.
- **Divergência deliberada no índice de registros.** As linhas que esta feature
  escreve nomeiam o que a decisão governa em palavras; as onze preexistentes
  citam número de artigo. A divergência é declarada no plano de propósito, para
  não ser lida como descuido. Normalizar as onze é passe editorial próprio e está
  em Out of Scope — e quatro corpos de registro já aceitos citam número de artigo
  do mesmo jeito, sendo imutáveis.
- **A allowlist é uma dívida, e a spec a trata como tal.** Nove entradas na
  partida. O número é critério de sucesso desta feature e insumo do confronto de
  cada slot seguinte. Uma entrada é ausência de teste declarada, nunca uma
  asserção afrouxada.
- **Sem `acceptance.spec.ts` próprio, e o cabeçalho diz por quê.** A regra de
  aceitação-antes-da-tela vale para feature de console. Esta não tem tela; o que
  ela entrega em navegador são as cinco asserções nomeadas da suíte transversal,
  que nascem vermelhas contra o cenário violador. Fabricar um acceptance vazio
  seria pior que não ter.
- **Duas decisões que o briefing deixava em aberto e a spec fecha**: a regra nova
  vira **artigo próprio** e não cláusula do artigo de test-first (razão no plano);
  e o vermelho dos bans é provado contra um **cenário de dados committed**, não
  contra o staging, porque um vermelho que só existe contra o staging deixa de
  ser reproduzível no dia em que o staging for consertado.
