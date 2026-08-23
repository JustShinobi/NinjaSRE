# 025 — Catalogue

A página mais pesada do console: numa única rota, sem busca nem âncoras, estão
**233 tools** agrupadas por domínio, **~100 skills** como lista de prosa, **85
formulários de credencial** (um por integração, cada um com campos de senha) e
seções-ensaio "Not covered, and why". O comentário de design em
`console/src/shell/routes.ts` define o catálogo como algo "lido com muito mais
frequência do que alterado" — mas a página embute exatamente a parte de
alteração (credenciais) no meio da leitura.

## Problemas

### 1. [bloqueia entendimento] Quatro telas numa rota

Catálogo de tools (leitura), catálogo de skills (leitura), setup de
integrações (escrita, sensível) e racional de arquitetura (documentação) — na
mesma página. Cada público chega com uma pergunta diferente e todos recebem a
página inteira. Separação proposta (detalhada na spec 090):

- **Catalogue** — só leitura: tools e skills, com busca e filtros.
- **Integrations** (nova tela, grupo Settings) — as 85 integrações como cards
  com estado (configurada/saudável/bloqueada), formulário de credencial
  por card, botão de teste, e filtro "só as que eu uso".
- Os ensaios "Not covered, and why" viram página de documentação linkada.

### 2. [bloqueia entendimento] Sem busca, sem âncoras, sem sumário

233 linhas de tools em 17 domínios exigem Ctrl+F do navegador. Mínimo: campo
de filtro por nome/domínio + navegação por âncora de domínio + contagem
("14 de 233 habilitadas").

### 3. [bloqueia entendimento] "Blocked by needs the X integration"

Gramática quebrada e cor de aviso para o que é, na prática, o estado normal de
95% das linhas (integração não configurada ≠ problema). Reescrever: "Requer a
integração X" com link para configurá-la; reservar cor de alerta para
integração configurada que *falha*.

### 4. [bloqueia entendimento] 85 formulários de credencial idênticos e sempre abertos

Todos expandidos, todos com "Every required field needs a value" visível antes
de qualquer interação, sem indicação de quais integrações já têm credencial
armazenada (todas dizem UNKNOWN). O operador com 3 integrações reais precisa
rolar por 82 formulários irrelevantes. Cards colapsados com estado real
(armazenada + verificada / armazenada + falhou / ausente) e formulário só ao
expandir.

### 5. [polimento] Skills como parede de prosa

~100 skills listadas como "slug Skills — frase" sem agrupamento, busca ou
relação com as tools do domínio. Agrupar por domínio junto às tools
correspondentes, ou tabela com filtro.

### 6. [polimento] Badge UNKNOWN sem explicação

Cada integração carrega UNKNOWN/HEALTHY sem legenda nem ação ("Check it" está
só no First steps). O teste de credencial deveria estar aqui também.

## Critérios de aceite

- Encontrar uma tool pelo nome leva < 5 s (busca na página).
- Credenciais não aparecem na rota de catálogo (ou, na correção mínima, ficam
  colapsadas com estado real por integração).
- Nenhum texto "Blocked by needs the".
- O estado de cada integração (ausente/armazenada/verificada/falhando) é
  legível sem expandir nada.
