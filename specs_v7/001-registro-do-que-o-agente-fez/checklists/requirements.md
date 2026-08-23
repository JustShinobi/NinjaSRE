# Specification Quality Checklist: Registro do que o agente fez

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

- [x] A ausência de tela própria e de acceptance spec Playwright está declarada
      no cabeçalho, com o apontamento para a feature que tem a tela
- [x] O que substitui a evidência de tela — as consultas de banco no staging —
      está enumerado como SQL executável, com as tabelas nomeadas pelos nomes
      reais e o escopo de organização presente em cada uma
- [x] Cada requisito é atômico: uma vírgula é fronteira de requisito, e nenhum
      FR- carrega duas obrigações separadas por vírgula
- [x] A decisão sobre os nomes dos campos do contrato está tomada na spec, e não
      deixada para o implementer descobrir
- [x] A decisão sobre qual caminho grava — e qual deixa de existir — está tomada
      explicitamente, com o "deixa de existir" separado de "fica desligado"
- [x] A regra que proíbe derivar a sentença do documento aparece como requisito
      próprio, e não só como observação
- [x] O tratamento do custo ausente aparece como requisito próprio, com a
      proibição explícita do zero fabricado
- [x] O destino do campo `summary` está decidido explicitamente, com a condição
      de saída nomeada, em vez de deixado para o corte resolver por acidente
- [x] O caso do run anterior a esta mudança está coberto por cenário, por
      requisito e por critério de sucesso
- [x] A reversibilidade da migração aparece como requisito, e o critério de
      sucesso exige o ciclo de ida e volta contra dados, não só a escrita da
      função de volta
- [x] O efeito sobre a suíte de cenários sintéticos aparece como requisito e
      como critério de sucesso, com "não medido" recusado
- [x] O que a feature **não** faz está enumerado, com a feature de destino
      nomeada para cada item que tem uma

## Notes

- **Três decisões que o briefing deixava em aberto foram tomadas nesta spec**, e
  estão marcadas como decisão e não como descoberta:
  1. **Nomes dos campos**: sentença e documento entram no contrato como
     `headline` e `report`. `headline` já é a palavra que o produto usa nos
     prompts — resumo de achado de sub-agente, título de entrada ruidosa, título
     de alerta duplicado. Inventar um sinônimo criaria duas palavras para um
     conceito.
  2. **Onde o documento mora**: continua em `agent_runs.summary`. A coluna nova é
     a da sentença. Renomear uma coluna com dados reais seria uma migração de
     conteúdo pelo nome.
  3. **Qual caminho grava**: o laço canônico, através de um adaptador registrado
     como hook. O pipeline por estágios não ganha chamador de produção nesta
     feature, e a spec diz isso em voz alta para que a feature que compõe a
     metade que age não descubra dois produtores de evento pelo mesmo run.
- O recibo do alerta fica com o caminho que já o escreve dentro da transação que
  reserva a identidade do run; o caminho concorrente sai da árvore. Foi decidido
  aqui porque ligar o recorder é ligar exatamente o segundo lugar contra o qual o
  código já avisa.
- **Um ponto de fronteira preexistente foi observado e não é resolvido por esta
  spec**: o documento de contrato HTTP e o cliente TypeScript gerado não têm dono
  declarado no protocolo de escrita única do slot, e a outra feature do slot pode
  tocá-los. A regra que o plano adota — regenerar dos dois lados e regenerar uma
  vez só no merge — é uma instrução ao orquestrador, não uma mudança de código, e
  está registrada como tal.
- A causa do badge que aparece num run terminado foi apurada durante a redação:
  ele é rótulo de estado de conexão ao vivo, não de estado do run, e o produto já
  fecha o run com status terminal e evento de fim. A apuração é entregue à
  feature que renderiza a tela; esta feature apenas garante que o fato de
  backend continua verdadeiro. Fica registrado aqui porque o briefing pedia que a
  causa fosse cravada, e cravá-la significou descobrir que o conserto não é
  daqui.
- Não restou marcador de clarificação porque as decisões de recorte desta onda já
  estavam registradas nos documentos de partida, e as três acima foram tomadas
  com base em código lido, não em preferência.
