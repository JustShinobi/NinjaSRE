# Specification Quality Checklist: Primeiro administrador

**Purpose**: Validar completude e qualidade da especificação antes do planejamento
**Created**: 2026-08-23
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] Sem detalhe de implementação (linguagem, framework, API) nos requisitos
- [x] Focada em valor para o operador e na decisão de produto
- [x] Escrita para quem decide, não só para quem implementa
- [x] Todas as seções obrigatórias preenchidas

## Requirement Completeness

- [x] Nenhum marcador [NEEDS CLARIFICATION] restante — o que ficou em aberto é
      questão para o operador, listada no relatório, não requisito por decidir
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

- [x] **A spec decide o mecanismo**, não o descreve como escolha em aberto: um
      híbrido de duas das três formas que o backlog analisou, com a terceira
      recusada por escrito
- [x] A rationale confronta os **três** critérios do backlog, um a um: quem não
      leu nada entra; a janela fecha de vez, inclusive sob réplicas
      concorrentes; deployment com identity provider não ganha segunda porta
- [x] A recusa da tela de first-run que cria conta está justificada pelo que ela
      permite afirmar depois — nenhuma rota não autenticada cria administrador
- [x] O seam credencial↔sign-in vira **um fato só**, e há um cenário de
      aceitação que só passa se os dois lados terminarem no mesmo lugar
- [x] As três invariantes do módulo de conta local estão preservadas **por
      substância** e cada uma tem requisito próprio: a porta não abre sozinha,
      criar principal não abre porta, a passphrase embarcada continua recusada
      fora de demonstração declarada
- [x] A generalização da porta (de "o campo está configurado" para "há abertura
      registrada") está justificada, e a alternativa que a quebraria — inferir
      abertura de "existe usuário com passphrase" — está considerada e recusada
      no plano
- [x] O custo do caminho de recusa está declarado como requisito, para que a
      mudança não introduza um oráculo de tempo por acidente
- [x] A concorrência tem requisito, cenário, teste próprio contra banco real, e
      árbitro nomeado — e o árbitro é o mesmo tipo de exclusão que o boot já usa
- [x] A migração de e-mail é **reversível**, e o que a reversão faz quando os
      dados não permitem está decidido explicitamente em vez de deixado para o
      implementer
- [x] A mensagem de colisão de e-mail é requisito de produto, com proibição
      explícita de nome de índice, nome de constraint e texto de driver
- [x] Rotação de passphrase e segundo administrador têm resposta, e é a mesma
      resposta do primeiro administrador
- [x] O DoD é verificável num deployment limpo por compose, e a evidência é
      transcrição de terminal, não teste verde
- [x] A conta local que o staging já usa está protegida por requisito e por
      critério de sucesso — a feature não pode trancar o operador atual
- [x] Cada requisito é atômico: uma vírgula é fronteira de requisito, e nenhum
      requisito carrega duas obrigações separadas por vírgula
- [x] As alegações normativas são frases curtas individualmente testáveis, e a
      spec declara quais são staging-safe e por quê
- [x] O viewport normativo de medição está declarado
- [x] A não-propriedade dos arquivos de escrita única do slot está declarada no
      cabeçalho e virou regra no `tasks.md`
- [x] Nenhuma tarefa instrui escrever identificador de requisito, número de
      artigo, número de feature ou caminho de planejamento em arquivo committed

## Questões para o operador

Nenhuma bloqueia a execução. Todas são decisões que a spec tomou por padrão e
que o operador pode reverter sem reescrever a feature.

1. **O aviso na tela revela que o deployment está sem dono.** A spec aceita
   essa revelação: ela não dá forma de entrar, porque abrir a porta exige shell
   no host ou o arquivo de credencial. A alternativa é restringir o aviso — a
   loopback, ou a uma janela de tempo depois do primeiro start. Padrão adotado:
   mostrar sempre no estado sem administrador.
2. **O destino das sessões vivas quando uma passphrase é rotacionada.** A spec
   exige que a decisão esteja declarada e seja o que acontece; ela não escolhe
   entre "revoga as sessões daquele administrador" e "deixa expirarem".
   Recomendação: revogar, porque rotacionar uma passphrase normalmente é
   resposta a suspeita.
3. **O que acontece com o sign-in local depois de o identity provider ser
   ativado num deployment que já tem administradores locais.** A spec proíbe
   apagá-los e exige que a regra esteja declarada no produto. Recomendação:
   fechar o sign-in local enquanto o identity provider estiver ativo, mantendo
   as contas — reversível desativando o provedor, e sem segunda porta enquanto
   ele está de pé.
4. **`ninjasre setup admin` num deployment com identity provider ativo não tem
   override.** A saída para quem ficou de fora é o caminho de emergência que o
   produto já tem. Se o operador quiser um override, ele é uma decisão de
   segurança própria e não cabe nesta feature.

## Notes

- As decisões de mecanismo foram tomadas nesta spec, a partir da análise que o
  `backlog.md` da raiz já tinha feito. O briefing pediu explicitamente que a
  spec **decidisse**, e por isso nenhum marcador de clarificação restou.
- A segunda superfície de console, com sign-in próprio, foi observada e **não**
  é decidida aqui: o estatuto dela é questão de governança levantada na
  auditoria de regras desta onda. A spec só exige que ela não afirme o contrário
  do console canônico.
- Um ponto preexistente foi observado e não corrigido, por estar fora do escopo:
  o bloco impresso no boot também promete que a credencial "can do exactly two
  things", enumeração que continua verdadeira mas que passa a conviver com um
  terceiro caminho — o comando. A spec exige que o bloco nomeie o comando e que
  pare de afirmar o que é falso, e não reescreve o resto do texto.
