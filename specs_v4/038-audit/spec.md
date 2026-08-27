# 038 — Audit

## Problemas

### 1. [bloqueia entendimento] Ruído de máquina afoga ação humana

A lista inteira é `default / credential.resolve / prometheus|proxmox /
ALLOWED`, gerada a cada poucos segundos pelo polling do próprio deployment.
Qualquer ação humana (grant, revoke, mudança de config) está enterrada sob
milhares de resoluções de credencial idênticas. O propósito declarado da tela
("Who did what") morre no primeiro scroll. Correções combináveis:

- **Agrupar rajadas**: n eventos idênticos consecutivos viram uma linha
  ("credential.resolve × 214, últimas 2 h").
- **Separar atores**: filtro default "pessoas" vs "sistema" (principal
  `default` é o sistema; sessões humanas têm principal próprio).
- Rever se `credential.resolve` de polling rotineiro precisa mesmo ser um
  evento de audit por chamada, ou um contador.

### 2. [bloqueia entendimento] Sem período, sem paginação visível

Filtros só de Principal/Action; nenhum recorte de data, nenhum "carregar
mais" aparente — com o volume do item 1, a tela fica inutilizável em dias.
Filtro de período + paginação/virtualização.

### 3. [polimento] Filtros populados só com o que existe

Principal: `Any/default`; Action: `Any/credential.resolve` — corretos hoje,
mas viram inúteis com um único valor (padrão das specs 011/023).

### 4. [polimento] Vazamento "SORT, SMALLEST FIRST" nos headers

Mesmo defeito das specs 012/020.

### 5. [polimento] Slugs por extenso

`credential.resolve`, `ALLOWED` — legendas curtas por ação ("resolveu a
credencial X para chamar Y") tornariam a tela legível para quem não conhece o
vocabulário interno. O detalhe por linha ("Open") existe — aproveitar o
espaço da linha para o resumo humano.

## Critérios de aceite

- Uma ação humana feita hoje é encontrável em < 10 s mesmo com polling ativo.
- Rajadas idênticas não geram uma linha por evento na leitura padrão.
- Existe filtro por período.
