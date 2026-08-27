# Specification Quality Checklist: Uma fonte por fato

**Purpose**: Validar completude e qualidade da especificação antes do planejamento
**Created**: 2026-08-23
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] Sem detalhe de implementação (linguagem, framework, API) nos requisitos
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
- [x] Nenhum detalhe de implementação vazou para os requisitos

## Forma da casa (onda v7)

- [x] A seção **"Alegações normativas"** existe, com frases curtas e
      individualmente testáveis, derivadas do diagnóstico da onda
- [x] Cada alegação está marcada como **staging-safe** ou não, com o motivo
      implícito na própria mecânica (leitura pura × escrita × contador)
- [x] O acceptance spec da feature está nomeado e a spec exige o **vermelho
      confirmado antes da tela**
- [x] O viewport normativo de medição (**1920×1080**) está declarado na spec que
      mede
- [x] A ausência de mockup está declarada no cabeçalho, com a razão (rework de
      telas existentes, não tela nova)
- [x] A propriedade dos arquivos de escrita única no slot está declarada
- [x] O DoD enumera as **consultas de banco exatas** que provam o que a feature
      alega, com a ressalva de que nome de tabela é conferido na execução
- [x] O plano declara **qual composition root constrói** cada mecanismo novo, e
      o tasks.md tem tarefa de composição com prova no caminho de serving
- [x] Nenhuma tarefa instrui escrever identificador de requisito, artigo da
      constituição, número de feature ou caminho de planejamento em arquivo
      committed

## Verificações específicas desta feature

- [x] Cada um dos quatro fatos tem **um dono nomeado**, e a tabela do começo da
      spec diz quem hoje cita outra coisa
- [x] O dono de "verificada" está corrigido em relação ao briefing (o registro
      de verificação, não o vault), com a correção declarada como premissa e
      justificada
- [x] O dono de "guardada" continua sendo o vault, e a spec diz isso
      explicitamente para que a correção acima não seja lida como troca de fonte
- [x] A distinção entre **estado do passo** (feito / não feito) e **prontidão**
      (ausente / guardada / verificada / falhando) está declarada
- [x] O quarto valor de prontidão está justificado, e o custo dele — mais uma
      opção num contrato que várias superfícies leem — está no rastreamento de
      complexidade do plano em vez de escondido
- [x] O vocabulário herdado de credencial é citado sem ser alterado, e a spec
      diz que "Degraded" não é redefinida aqui
- [x] A regra de quando a causa de setup **pode** ser dita está enunciada como
      regra, não como lista de telas
- [x] Cada tela que perde a causa de setup ganha uma causa própria, e a que não
      ganhar mantém as suas palavras — decidido, não deixado por omissão
- [x] O estado desconhecido está definido como **terceiro valor de toda leitura
      de estado**, e não como caso particular do chip de incidente
- [x] O estado desconhecido é obrigado a **nomear a dependência**, porque sem
      isso ele é honesto e inútil
- [x] A mecânica do teste que prova que a lista bate no gateway está **definida
      no plano**, com a alternativa considerada (assertion de log) e o motivo da
      recusa
- [x] São duas mecânicas e não uma, porque são duas alegações diferentes —
      requisição chegou × operador vê o presente — mais o gate de build como
      terceira, que prova que não volta
- [x] O custo de latência do dinamismo tem medição antes e depois, com o
      orçamento contra o qual julgar já existindo no repositório
- [x] A decisão de latência foi tomada **antes** da medição, para que a medição
      não a justifique depois, e "página congelada" está excluída como saída
- [x] A direção do seam de time está **decidida** com recomendação e rationale,
      e as duas alternativas rejeitadas estão nomeadas com o motivo
- [x] O caso ambíguo (dois times com credencial para o mesmo vendor) está
      decidido, registrado e visível, em vez de resolvido por sorteio
- [x] O invariante testável do seam está enunciado — o handle que a verificação
      resolve é o handle que o binding resolve
- [x] O seam da chave do modelo foi conferido **contra o código real** e não
      contra o backlog: o caminho vault-primeiro já existe e é composto, e a
      spec diz que a feature verifica isso e fecha só a metade que falta
- [x] A causa nomeada no diagnóstico para as listas congeladas está tratada como
      **hipótese**, com a contradição de código registrada e uma tarefa de
      medição antes do remédio
- [x] O vocabulário de estado de run entrou como grupo próprio de requisitos, de
      alegações e de tarefas, e não diluído nos existentes
- [x] A fonte do estado de run foi **conferida no código** e corrigida em
      relação ao pedido: é a enumeração do store, que o gateway serve verbatim,
      e não a do runtime
- [x] O achado foi ampliado onde o código mostrou mais: são **dois** valores
      inventados nas fixtures, não um, e o console erra nas duas direções
- [x] A armadilha de `succeeded` como valor legítimo de **tool call** está
      declarada, com o requisito que impede a varredura de atravessá-la
- [x] O gate lê a enumeração como dado, e a spec proíbe explicitamente a lista
      literal repetida que criaria mais um vocabulário
- [x] O gate checa nas duas direções — valor a mais e valor a menos — e a razão
      de cada direção está escrita
- [x] As baselines visuais afetadas são tarefa deliberada, com a proibição de
      apagar e de fabricar declarada como requisito
- [x] A ordem rígida gate → migração → purga → baselines → gate verde está
      declarada, com o motivo (fora dela, o vermelho mede a ordem)
- [x] O que **não** é feito aqui — unificar as duas enumerações de estado de run
      — está registrado como observação, com o dono da decisão nomeado
- [x] O que esta feature **não** faz está enumerado por feature vizinha, para
      que o slot paralelo não colida

## Notes

- **Correção ao briefing, registrada.** O briefing pede que "o checklist de
  setup e o verify do provider leiam a mesma fonte (o vault)". O vault não
  responde por "verificada" — ele guarda metadado de credencial. Quem responde é
  o registro de verificação, que a listagem de providers já lê e que o checklist
  já lê para integrações. A spec adota essa fonte e diz por quê; o efeito
  observável pedido pelo briefing é o mesmo e é o que as alegações normativas
  exigem.

- **Correção ao backlog, registrada.** O item "The investigator's model key comes
  from the environment, not the vault" descreve um estado que o código já não
  tem: a composição vault-primeiro-ambiente-depois existe e é chamada no boot. O
  que sobrou do seam é a dimensão de time — o lease é tirado com o handle
  org-wide —, e é isso que esta feature fecha. A spec diz isso como premissa
  para que ninguém reescreva o que já está escrito.

- **Contradição no diagnóstico, registrada e não resolvida na spec.** O
  diagnóstico atribui `/incidents` renderizada sem requisição ao Full Route
  Cache. O segmento do shell já declara renderização dinâmica desde antes do
  build observado, e a página de incidentes já espera parâmetros de busca — as
  duas coisas tiram uma rota daquele cache. A spec exige a propriedade e os
  testes; o plano exige medir qual camada realmente serviu a página antes de
  escolher o remédio. Se a medição contradisser o diagnóstico, o achado é
  registrado como está.

- **Duas alegações não são staging-safe por natureza, não por conveniência.** A
  que conta requisições precisa de um contador que só o backing tem; a que exige
  um fato novo em um reload é uma escrita. Elas rodam contra o backing de mock e
  a spec marca isso, em vez de enfraquecê-las para caberem no ambiente
  compartilhado.

- **Coordenação da onda, aceita com a fonte corrigida.** O orquestrador pediu
  que esta feature tomasse conta do vocabulário de estado de run, apontando a
  enumeração do runtime como dona. A conferência no código mostrou que quem o
  gateway serve verbatim é a enumeração do **store** — a rota de investigações
  passa o valor sem tradução. Corrigir contra a do runtime deixaria três estados
  reais de fora e criaria mais um vocabulário. A spec adota a do store e
  registra por quê; o efeito observável pedido é o mesmo.

- **Três questões ficam para o operador** e estão listadas no relatório da
  geração, não escondidas aqui: o quarto valor de prontidão é aceito como
  ampliação de contrato; a ambiguidade de time resolve para org-wide com aviso
  em vez de para o primeiro time; e a causa de vazio passa a nomear um passo em
  vez de uma contagem, o que muda texto que já foi lido por alguém.
