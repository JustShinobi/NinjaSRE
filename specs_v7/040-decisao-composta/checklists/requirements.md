# Specification Quality Checklist: Decisão composta

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

## Verificações específicas desta feature

### Fail-closed

- [x] A permanência da recusa direta está escrita como requisito, e não apenas
      como premissa
- [x] A frase da recusa é declarada imutável
- [x] Existe um requisito explícito proibindo qualquer tarefa de remover,
      afrouxar ou contornar uma recusa
- [x] O caminho "sem plano de reversão derivável" está decidido — dispensa
      explícita registrada — e não deixado para a implementação resolver
- [x] O interruptor de emergência aparece em dois momentos distintos, decisão e
      execução, e não só num deles
- [x] Nenhum requisito alarga autonomia: nenhuma lista de permissão nova,
      nenhum padrão que passe a agir, nenhuma dispensa automática

### Composição

- [x] Cada mecanismo novo tem requisito dizendo que ele é construído numa
      composition root de serving, e não só que ele existe
- [x] O plano nomeia as roots com arquivo e linha, incluindo a ordem entre elas
- [x] O caminho duplicado tem destino decidido — um canônico, o outro declarando
      dormência com o construtor nomeado — e o destino é requisito, não nota
- [x] O critério de sucesso da composição é evidência do caminho de serving
      (contagem no armazenamento), não suíte verde
- [x] A concorrência entre runs está tratada como requisito, para o portão e
      para o balcão de perguntas

### Seleção de ferramentas

- [x] Os dois filtros — nível de efeito colateral e integrações configuradas —
      são requisitos separados, e não um só
- [x] A ordem entre estreitar e cortar no teto está declarada
- [x] A exclusão é observável: um requisito exige que a razão fique registrada
- [x] A resposta de zero integrações é atribuída a uma implementação única, com
      requisito próprio

### Fronteiras

- [x] A ausência de tela própria e de acceptance Playwright está declarada no
      cabeçalho, com o apontamento para de quem é a tela
- [x] A não-propriedade dos arquivos de escrita única no slot está declarada, e
      o caminho alternativo (declarar a chave no relatório) está dito
- [x] O que roda contra o ambiente compartilhado é nomeado, e o que não roda
      também
- [x] Existe uma contagem de staging cujo valor esperado é **zero**, para que
      "nada foi executado lá" seja verificável e não presumido
- [x] Cada requisito é atômico — uma vírgula é fronteira de requisito, e nenhum
      requisito funcional carrega duas obrigações separadas por vírgula

### Escolhas que a spec deliberadamente não faz

- [x] A capacidade de escrita do cenário é escolhida no plano, não na spec — a
      spec exige que ela seja reversível e de raio mínimo, e o plano nomeia qual
- [x] Qual dos dois caminhos de orquestração é o canônico é decidido no plano; a
      spec exige apenas que exatamente um esteja composto e o outro se declare

## Notes

- As decisões de recorte desta onda foram tomadas pelo operador em 2026-08-23 e
  estão registradas no material de partida da onda; por isso nenhum marcador
  [NEEDS CLARIFICATION] restou.
- Os números do inventário de capacidades (oitenta declaradas, vinte e quatro
  que escrevem, vinte e quatro exigindo aprovação) aparecem no plano como
  contexto medido e **não** viram asserção em arquivo committed: a tarefa de
  linha de base os relê da árvore, e é a árvore que manda.
- Uma inconsistência preexistente foi observada e **não** é corrigida aqui, por
  estar fora do escopo declarado: os hooks de guardrail não são registrados no
  laço que serve as investigações, embora o motor de guardrail esteja no estado
  do gateway. Esta feature registra o portão de remediação depois de onde os
  guardrails ficariam, e não os compõe. Está anotado como questão para o
  operador.
- Uma segunda ausência foi observada e é deliberadamente mantida: não existe
  implementação do esperador de decisão, e o plano compõe sem ele com o motivo
  escrito. Escrever um seria suspender uma iteração de laço pelo tempo de uma
  aprovação humana, que é uma decisão maior do que esta feature.
- A dependência entre esta feature e a que registra o que o agente fez é de
  legibilidade, não de mecanismo: a proposta é gravada de qualquer maneira, mas
  sem a outra feature ela aparece vinculada a um run que não conta o que fez.
