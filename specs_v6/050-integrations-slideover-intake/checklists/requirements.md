# Specification Quality Checklist: Integrações em slide-over e Alert intake enxuto

**Purpose**: Validar a completude e a qualidade da especificação antes do
planejamento
**Created**: 2026-08-16
**Feature**: [spec.md](../spec.md)

**Review Ownership**: esta checklist é um artefato de revisão de qualidade de
requisitos, de propriedade do revisor. Marcar `[x]` só quando o critério de
qualidade estiver satisfeito — não significa que a implementação está pronta.

## Content Quality

- [x] Sem detalhe de implementação (linguagem, framework, API) nos requisitos
- [x] Focada no valor para o operador e na necessidade que a origina
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

## Aderência ao mockup

- [x] Cada requisito de tela cita a âncora do mockup a que responde (`#m3`, `#m4`)
- [x] Cada alegação normativa anotada nos mockups virou um requisito próprio —
      uma vírgula do mockup é fronteira de requisito
- [x] As palavras exatas dos chips estão nos requisitos, não parafraseadas
      ("Receiving", "Ready — nothing arrived yet")
- [x] A ordem das seções do catálogo é requisito, não sugestão
- [x] O orçamento de rolagem tem viewport declarado (1080p) nos critérios que o
      medem

## Vocabulário e contagens

- [x] O vocabulário canônico de estado é citado por extenso e nenhum estado é
      traduzido para outra palavra
- [x] Nenhum requisito fixa um total de catálogo como literal; as contagens são
      derivadas do que a API devolve
- [x] Os números desenhados no mockup estão declarados como retrato de uma data,
      não como constante
- [x] O requisito de contagem única proíbe explicitamente dois números
      divergentes na mesma tela

## Segurança da especificação

- [x] Nenhum requisito reexibe um segredo guardado
- [x] O conteúdo copiável que carrega credencial tem regra explícita sobre o
      valor do segredo, com a única exceção nomeada e justificada
- [x] Nenhum segredo em URL ou em deep-link
- [x] A ação destrutiva exige confirmação que nomeia o alvo

## Feature Readiness

- [x] Todo requisito funcional tem critério de aceitação claro
- [x] As histórias cobrem os fluxos primários das duas telas
- [x] A feature atinge os resultados mensuráveis declarados em Success Criteria
- [x] Os gates tocados estão listados na spec, e não deixados para descobrir
      durante a implementação
- [x] A dependência declarada (001) está nomeada com a consequência de não a ter

## Notas

- As decisões de escopo desta onda — corte para 15 integrações, intake em três
  fontes, slide-over como padrão normativo, acceptance-first por feature de
  console — foram tomadas pelo operador em 2026-08-16 e registradas no README da
  onda. Por isso nenhum marcador [NEEDS CLARIFICATION] restou.
- Rotas citadas (`/integrations`, `/settings/alert-intake`) são endereços
  visíveis ao operador, não detalhe de implementação.
- O endereço `http://10.20.20.37:9093` aparece na spec como exemplo do que o
  estate descobre, e o requisito correspondente exige que ele venha da
  descoberta — não que ele seja escrito na tela.
- Um ponto ficou deliberadamente resolvido em vez de deixado em aberto: o valor
  do delivery token dentro do YAML copiado. Reexibir um segredo guardado é
  proibido, então o bloco traz um marcador; a exceção é o gesto de emissão, em
  que o valor acabou de nascer e já está na tela. Se a revisão discordar dessa
  leitura, é o requisito de conteúdo do bloco que muda, não a regra do segredo.
- `/settings/schedules-destinations` é tocada por esta feature apesar de não ser
  uma das suas duas telas: sem desfazer a sobreposição de nomes das duas seções
  avançadas, o nó de destino da cadeia não tem para onde apontar sem sinônimo.
  O escopo dessa incursão está limitado aos dois títulos.
