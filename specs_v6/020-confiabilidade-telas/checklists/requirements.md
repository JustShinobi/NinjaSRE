# Specification Quality Checklist: Confiabilidade das telas

**Purpose**: Validar a completude e a qualidade da especificação antes do
planejamento e da implementação
**Created**: 2026-08-16
**Feature**: [spec.md](../spec.md)

**Review Ownership**: artefato de revisão de qualidade de requisitos. Um item
só é marcado `[x]` quando o revisor determina que o critério está satisfeito —
`[x]` não significa que a implementação existe.

## Content Quality

- [x] Sem detalhe de implementação nas user stories e nos cenários de aceitação
- [x] Focada em valor para o operador e no que a tela deve dizer
- [x] Legível por quem não vai escrever o código
- [x] Todas as seções obrigatórias preenchidas
- [ ] Sem detalhe de implementação em nenhuma seção — **não marcado de
      propósito**: a seção Dependencies lista gates e caminhos de teste porque
      as regras de escrita desta onda exigem que cada spec declare os gates que
      toca. É um desvio consciente do formato genérico, não um descuido.

## Requirement Completeness

- [x] Nenhum marcador [NEEDS CLARIFICATION] restante
- [x] Requisitos testáveis e sem ambiguidade
- [x] Requisitos atômicos — cada FR carrega uma obrigação; onde o briefing
      trazia uma vírgula, virou requisito separado
- [x] Critérios de sucesso mensuráveis (contagens, zero-divergências, medida de
      altura com viewport declarado)
- [x] Critérios de sucesso independentes de tecnologia
- [x] Todos os cenários de aceitação definidos
- [x] Edge cases identificados, incluindo os dois que produzem o defeito atual
      (fetch inteiramente do principal do deployment; setup já concluído)
- [x] Escopo delimitado: valores da tabela sim, redesenho da autonomia não;
      regra de vocabulário sim, limpeza do vocabulário cru não
- [x] Dependências e premissas identificadas

## Feature Readiness

- [x] Todo requisito funcional tem critério de aceitação correspondente
- [x] As user stories cobrem os cinco defeitos do briefing e o instrumento
- [x] A feature atende aos critérios mensuráveis declarados
- [x] Cada defeito fechado cita a evidência do diagnóstico

## Riscos específicos desta feature (revisar antes de implementar)

- [x] **A reversão está declarada.** A correção da contagem única reverte uma
      decisão registrada hoje em comentário no código, que defende dois
      denominadores como medidas legítimas de coisas diferentes. A spec e o
      plano dizem isso explicitamente, e a tarefa manda remover o comentário
      junto com o comportamento — em vez de deixar no arquivo uma justificativa
      para algo que deixou de existir.
- [x] **A causa do audit é hipótese até o teste falar.** A leitura do código
      aponta a exclusão implícita de ator como a razão de o corpo esvaziar
      enquanto a contagem permanece cheia. A spec não trava essa explicação: os
      requisitos são sobre o comportamento observável, e a tarefa de reprodução
      é que decide se a causa é da tela ou do contrato.
- [ ] **Sobreposição com suítes existentes.** `vocabulary.spec.ts` e
      `scroll-budget.spec.ts` já cobrem parte de duas das quatro regras. O
      plano manda remover a asserção duplicada da suíte nova onde a
      sobreposição for exata — **decisão a confirmar na implementação**, com o
      resultado registrado no controle.
- [ ] **Nome do arquivo de acceptance.** O arquivo committed
      `console/tests/e2e/020-confiabilidade-telas.acceptance.spec.ts` carrega o
      número da feature no nome, o que a convenção desta onda determina e a
      regra de arquivos committed desaconselha. O conteúdo do arquivo não cita
      onda, spec nem número — **tensão conhecida, resolvida a favor da
      convenção da onda**, registrada aqui para não ser redescoberta.

## Notes

- As decisões de escopo desta onda (corte do catálogo, provider como fluxo,
  mockup virando teste antes da tela, o primeiro incidente no cluster real)
  foram tomadas pelo operador em 2026-08-16 e registradas no README da onda —
  por isso nenhum marcador [NEEDS CLARIFICATION] restou.
- Audit log e Single sign-on não têm âncora própria no mockup da v6; são
  governados pelas regras transversais da v5 e pelo diagnóstico. A spec diz
  isso em vez de citar uma âncora que não existe.
- Rotas citadas (`/settings/audit-log`, `/first-run`) são endereços visíveis ao
  operador, não detalhe de implementação.
- `controle.md` não é gerado aqui: quem o escreve é o implementador, com o que
  o código provar.
