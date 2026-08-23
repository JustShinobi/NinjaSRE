# Specification Quality Checklist: Identidade endereçável

**Purpose**: Validar completude e qualidade da especificação antes do planejamento
**Created**: 2026-08-23
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] Sem detalhe de implementação (linguagem, framework, API) na spec — a
      forma concreta do identificador, o nome da coluna e a camada do decode
      vivem no plano, que é onde a decisão pertence
- [x] Focada em valor para o operador e na decisão de produto
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

- [x] A spec tem seção **"Alegações normativas"** no lugar do mockup, porque
      esta é uma feature de rework e não de tela nova
- [x] Cada alegação é uma frase curta e individualmente testável — uma vírgula
      é fronteira de requisito, e nenhuma alegação carrega duas obrigações
- [x] O arquivo do acceptance spec está nomeado, e mora onde o runner do
      console coleta (`console/tests/e2e/`)
- [x] O tasks.md faz do vermelho confirmado um **portão** numerado, antes do
      qual nenhuma implementação começa
- [x] As alegações staging-safe estão marcadas uma a uma, e são só leitura
- [x] O viewport normativo de medição está declarado (1920×1080)

## Verificações específicas desta feature

- [x] A forma pública do identificador é **decidida no plano**, com a
      alternativa recusada e a razão de cada recusa escritas — não deixada para
      a implementação resolver por acidente
- [x] A estratégia de migração está decidida e é reversível, e a reversibilidade
      tem tarefa de teste própria, não uma afirmação
- [x] A concordância entre o valor que a migração grava e o valor que o código
      deriva tem teste próprio — sem ele, ela é coincidência de revisão de código
- [x] O destino da chave interna está decidido explicitamente: continua sendo a
      chave primária, continua resolvendo na rota, e para de ser emitida
- [x] Está declarado por que a permanência da chave interna **não** é dívida de
      compatibilidade com prazo de morte
- [x] O decode único tem teste com caracteres reservados nomeados (`:`, `@`,
      `+`, `/` encodado) e com o caso do `%` solto que lança
- [x] A camada do decode está decidida (a borda da página, num helper
      compartilhado) e a razão de **não** ser dentro do cliente de API está
      escrita
- [x] O fix do decode está declarado como valendo para toda rota dinâmica, e as
      rotas dinâmicas foram enumeradas a partir da árvore, com tarefa de
      varredura para provar que a enumeração é completa
- [x] O título do incidente vem de `incident.title`, e "o id nunca é título"
      está como requisito negativo explícito para o H1 **e** para a aba
- [x] O comportamento com leitura falhada está especificado sem invadir o
      vocabulário de chips que outra feature da onda define — a página omite em
      vez de afirmar
- [x] A fronteira com a feature de uma-fonte-por-fato está escrita nos dois
      lados: em Out of Scope e como requisito negativo sobre o diff
- [x] Os dois redirects estão nomeados com origem e destino, e reusam a
      mecânica que já existe em vez de inventar uma segunda
- [x] As quatro superfícies que geram href de incidente foram levantadas do
      código, com `file:line`, e não de memória
- [x] O efeito de fronteira está previsto: documento de API, cliente TS gerado e
      dataset simulado regenerados na mesma feature
- [x] As consultas SQL de evidência em staging estão enumeradas na spec, com o
      que cada uma precisa devolver
- [x] O plano declara qual composition root constrói o mecanismo, com
      `file:line`, e responde honestamente que não há objeto novo a construir —
      nomeando em troca o caminho de serving que o exercita
- [x] A prova de composição no DoD é o staging, não o harness
- [x] A propriedade dos arquivos de escrita única no slot está declarada, e esta
      feature é a dona
- [x] A interseção com a feature par do slot foi verificada e é nula

## Notas

- **Não há mockup e não devia haver.** Todas as telas tocadas já existem; a
  onda decidiu que rework de console traz alegações normativas no lugar de
  mockup, e o cabeçalho da spec diz isso em vez de fabricar uma referência
  visual vazia.
- **Uma alegação do briefing foi estreitada de propósito.** O briefing pede
  "zero painéis 'could not be filled'". A spec restringe a alegação aos painéis
  cuja dependência é a rota de detalhe de incidente, porque a sub-linha de meta
  se alimenta de uma leitura do estate que falha por outra razão inteiramente —
  o estate está vazio enquanto a integração Proxmox está degradada, o que é
  escopo de outra feature da onda. Alegar o número absoluto tornaria o
  acceptance vermelho por um defeito que esta feature não pode consertar.
- **Um ponto pré-existente foi observado e não corrigido**, por estar fora do
  escopo declarado: as rotas de fechamento e de supressão de incidente recebem
  o identificador como parâmetro de caminho tanto quanto a de detalhe. O
  tasks.md tem tarefa para **decidir** o que fazer com elas — resolver as duas
  grafias também, ou registrar por escrito que continuam só pela chave interna
  — em vez de deixar a decisão acontecer por omissão. Uma tela que abre por um
  identificador e escreve por outro é a próxima divergência de grafia esperando
  acontecer.
- **A escolha do prefixo é o único ponto genuinamente aberto ao operador.** O
  plano decide `inc_` seguido de dezesseis hexadecimais e diz o que custa
  trocar: uma linha de derivação e uma de gramática na borda antes de a
  migração rodar no staging, uma migração nova depois disso.
