# Specification Quality Checklist: O catálogo ensina

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

- [x] A spec traz uma seção "Alegações normativas" com frases curtas,
      individualmente testáveis
- [x] Cada alegação carrega uma obrigação só — nenhuma vírgula é fronteira de
      requisito escondida
- [x] Está declarado quais alegações são seguras contra ambiente compartilhado e
      quais não são, com o motivo
- [x] O viewport normativo de medição está declarado (1920×1080)
- [x] Está declarado que não há mockup próprio, e por quê (as duas superfícies já
      existem e já foram desenhadas)

## Verificações específicas desta feature

- [x] Os 40 campos estão enumerados um a um, por vendor, derivados dos schemas
      reais em `integrations/*/schema.py` — não copiados de um documento
- [x] A aritmética fecha: 40 = 21 secretos + 8 públicos + 11 endereços
- [x] A aritmética do estado atual fecha e bate com o backlog: 12 campos com
      permissão mínima (28 sem), 11 com guia (29 sem)
- [x] A releitura de "28 de 40" para "9 dos 21 secretos" está declarada como
      **decisão**, com o motivo e a alternativa recusada — não deixada para a
      implementação resolver por acidente
- [x] Está decidido explicitamente que campo de endereço e campo de configuração
      pública **não podem** declarar permissão mínima, e isso é um requisito com
      gate, não uma observação
- [x] A decisão de o gate validar presença e forma do guia, e nunca
      alcançabilidade, está registrada na spec com o motivo
- [x] Está decidido onde o gate novo entra (dentro da verificação de integrações
      que já existe) e por que não num alvo próprio
- [x] A forma da falha do gate está especificada: nomeia vendor e campo, diz o
      custo da ausência, coleta tudo antes de falhar
- [x] Está declarado que a documentação servida vem de arquivo committed dentro
      do pacote, e que nenhum arquivo committed passa a depender de arquivo fora
      do repositório
- [x] Está declarado que a rota de documentação não compõe caminho de arquivo a
      partir do valor recebido na URL
- [x] Está declarado que o risco de o documento não chegar na imagem construída é
      real e tem prova exigida
- [x] A proibição de um segundo renderizador de markdown é um requisito, e tem um
      critério de sucesso que a mede
- [x] A recusa em HTTP claro separa explicitamente o que muda (o texto) do que não
      muda (a classificação e o comportamento)
- [x] Está declarado que a frase da recusa é escrita num lugar só e espelhada,
      nunca copiada por superfície
- [x] Está declarado o caso do vendor sem site de documentação de fornecedor, com
      a decisão tomada e marcada para confirmação do operador
- [x] Está declarado que conteúdo por vendor é pesquisa com fonte citada, e que um
      valor verossímil é pior que um campo em branco

## Notes

- As contagens desta spec foram derivadas dos schemas reais em 2026-08-23 por
  varredura da árvore, e conferem com as do backlog (28 sem permissão mínima, 29
  sem guia). A tarefa T002 as reconfere antes de qualquer escrita, porque uma
  contagem derivada num dia e usada como autoridade noutro é a forma como uma
  spec começa a mentir.
- Nomes de pacote e de campo (`proxmox.api_token`, `openobserve.username`)
  aparecem na spec como identificadores do produto, não como caminho de arquivo.
  A enumeração por nome foi pedida no briefing, porque uma lista derivada em tempo
  de implementação é uma lista que ninguém revisou.
- **Uma divergência deliberada em relação ao briefing.** Ele pede "preencher todos
  os campos dos 15 vendors" a partir de "28/40 sem `min_scope`". A spec preenche
  os 40 de guia e só os 21 secretos de permissão mínima, e **proíbe** permissão
  mínima nos outros 19. O motivo está na spec: preencher os 19 exigiria inventar
  uma permissão para um endereço e para um nome de namespace, que é exatamente o
  que a declaração de campo proíbe em texto. "40/40 orientados" continua sendo o
  número do DoD, com o significado declarado.
- A frase "onde obter" por vendor é uma declaração **nova** — nenhum vendor a tem
  hoje, e o backlog só nota que o painel não a passa. A spec resolve o defeito
  literal criando a declaração que faltava, na mesma forma que os provedores de
  modelo já usam, em vez de deixar a tela mostrar um lugar vazio.
- Um ponto de inconsistência preexistente foi observado e **não** corrigido aqui,
  por estar fora do escopo declarado: a tabela de campos de cada `docs.md`
  duplica o schema e nada impede as duas de divergirem. As tarefas por vendor
  atualizam as duas metades juntas; um gate de divergência entre elas está
  registrado em "Out of Scope".
- Duas perguntas ficam para o operador e estão nomeadas na spec e nas tarefas: o
  destino do guia de `hermes`, e o que fazer com um vendor cuja documentação não
  responder qual é a permissão mínima verdadeira — a tarefa para e registra a
  pergunta em vez de escrever um valor plausível.
