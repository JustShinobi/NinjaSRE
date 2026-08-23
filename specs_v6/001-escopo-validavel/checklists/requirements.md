# Specification Quality Checklist: Escopo validável

**Purpose**: Validar completude e qualidade da especificação antes do planejamento
**Created**: 2026-08-16
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

- [x] A lista das 15 mantidas é a do README da onda, sem acréscimo nem omissão
- [x] A lista das 70 removidas foi derivada do conteúdo real de `integrations/`,
      não copiada de um documento — 85 pacotes de vendor menos as 15 mantidas
- [x] As 15 mantidas existem todas na árvore (conferido: nenhuma faltando)
- [x] A soma fecha: 85 = 15 + 70
- [x] Cada requisito é atômico — uma vírgula é fronteira de requisito, e
      nenhum FR- carrega duas obrigações separadas por vírgula
- [x] A fronteira entre pacote de integração e componente homônimo (destino de
      notificação, superfície de chat) está declarada como premissa e como FR
- [x] O destino do contrato de paginação da categoria provedor de modelo está
      decidido explicitamente, e não deixado para o corte resolver por acidente
- [x] O destino das 70 removidas em relação à lista de vendors não cobertos
      está decidido explicitamente
- [x] A ausência de tela própria e de acceptance spec Playwright está declarada
      no cabeçalho, com o apontamento para a feature que tem a tela

## Notes

- As decisões de escopo desta onda foram tomadas pelo operador em 2026-08-16 e
  estão registradas no README da onda e no diagnóstico — por isso nenhum
  marcador [NEEDS CLARIFICATION] restou.
- Esta é a única feature da onda sem referência visual de DoD. A regra de
  acceptance-first vale para feature de console; esta não tem tela, e o
  cabeçalho da spec diz isso em vez de fabricar um acceptance spec vazio.
- Nomes de pacote (`aws_ec2`, `google_gemini`) aparecem na spec como
  identificadores do produto, não como caminho de arquivo. A enumeração por
  nome foi pedida explicitamente no briefing, porque uma lista derivada em
  tempo de implementação é uma lista que ninguém revisou.
- Um ponto de inconsistência preexistente foi observado e **não** corrigido
  aqui, por estar fora do escopo declarado: a lista de vendors não cobertos e a
  lista de "desejados e não construídos" do roadmap se sobrepõem parcialmente e
  divergem no resto. A feature preserva as duas como estão e só impede que as
  70 removidas entrem na primeira.
