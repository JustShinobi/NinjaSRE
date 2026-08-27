# Specification Quality Checklist: Leitura do relato

**Purpose**: Validar completude e qualidade da especificação antes do planejamento
**Created**: 2026-08-23
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] Sem detalhe de implementação (linguagem, framework, API)
- [x] Focada em valor para o operador e na decisão de negócio
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

## Acceptance-first (regra da onda)

- [x] A spec declara que não há mockup e que as alegações normativas ocupam o
      lugar dele
- [x] As alegações normativas são frases individualmente testáveis, e nenhuma
      carrega duas obrigações separadas por vírgula
- [x] A spec nomeia o arquivo de acceptance que as codifica
- [x] A spec exige o vermelho confirmado antes da mudança de tela
- [x] As alegações seguras para rodar contra ambiente compartilhado estão
      marcadas como tais, e nenhuma delas escreve dado
- [x] O viewport normativo de medição está declarado, e é 1920×1080
- [x] O que é medido nesse viewport está dito (rolagem, largura, recorte)

## Verificações específicas desta feature

- [x] A cadeia do defeito de markdown cru está cravada com `file:line` para as
      três superfícies que o consomem
- [x] O fallback para run sem headline está decidido explicitamente, e não
      deixado para a implementação resolver por acidente
- [x] A spec afirma que o documento **nunca** volta a ser o nome, inclusive no
      fallback
- [x] A separação entre "traduzir falha" e "nomear investigação" está declarada,
      e o módulo de tradução de falhas não é apagado
- [x] O contrato do slot anterior é tratado como premissa, com o comportamento da
      feature declarado para o caso de ele não estar lá
- [x] A causa mecânica do controle de run vivo aparecendo em run terminado está
      cravada em código, e não descrita como "sintoma a investigar"
- [x] A divergência entre o enum de status do produto e a lista do console está
      registrada como fato, com as duas referências
- [x] A spec registra que as fixtures usam um status que o produto não emite, e
      que é isso que mantém a suíte verde sobre um staging quebrado
- [x] A sanitização do relato é exigida como propriedade estrutural (árvore de
      elementos) e não só como filtragem
- [x] A regra "nenhum asset sai do deployment" está coberta por requisito próprio
      para imagem remota
- [x] O encolhimento da allowlist transversal é escopo declarado, com o critério
      de prova sendo a suíte passando e não a linha removida
- [x] A propriedade dos arquivos de escrita única no slot está declarada
- [x] A evidência visual exigida nomeia as telas, o viewport e o destino

## Notes

- Esta feature é rework de duas telas existentes, não tela nova, e por isso o
  briefing da onda dispensa mockup HTML próprio. As alegações normativas foram
  expandidas de cinco (o mínimo do briefing) para trinta e cinco, agrupadas por
  tema.
- Nenhum marcador [NEEDS CLARIFICATION] restou porque as decisões abertas do
  briefing — biblioteca de renderização, forma do fallback, destino da disclosure
  de texto cru, se o headline é repetido no painel — foram **decididas** aqui e no
  plano, com razão escrita, em vez de deixadas em aberto.
- Três pontos de coordenação com outras features da onda foram registrados como
  premissa em vez de requisito, porque não são desta feature resolver: o nome
  exato dos campos do contrato, a marcação de segurança para staging, e o formato
  em que os vínculos são gravados. Cada um tem, no `tasks.md`, uma tarefa que diz
  o que fazer se o pressuposto não se confirmar.
- Uma inconsistência preexistente foi observada e **não** corrigida aqui, por
  estar fora do escopo declarado: o conjunto de fixtures grava runs com um status
  que o enum do produto não emite. Esta feature acrescenta casos com o status
  real em vez de reescrever os existentes, porque a reescrita moveria baselines de
  telas que não são desta feature. A limpeza fica registrada como trabalho
  posterior.
