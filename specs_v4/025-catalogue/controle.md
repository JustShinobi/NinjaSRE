# Controle — 025 Catalogue

Verificado por confronto em 2026-08-13. Ver `relatorio-confronto.md` para a
evidência completa (arquivo, linha e teste) por trás de cada linha.

| Item | Estado | Detalhe |
|---|---|---|
| 1. Quatro telas numa rota (extrair Integrations) | **PARCIAL** | A separação estrutural continua não feita — ainda uma rota, dois painéis, sem tela `/integrations` própria e sem página de documentação para "Not covered, and why"; é de fato a peça central da onda 3, como já apontado aqui. Mas o critério de aceite tem uma cláusula alternativa ("ou, na correção mínima, ficam colapsadas com estado real por integração") e essa alternativa está satisfeita pelos itens 4 e 6 abaixo. |
| 2. Sem busca/âncoras/sumário | **FEITO** | Corrigido em `console/src/surfaces/capability-browser.tsx` (novo componente client): campo de busca por nome/domínio, navegação por âncora de domínio, contagem "N of M enabled" ("N de M habilitadas" em pt-BR) computada sobre o catálogo inteiro. Teste novo confirmado vermelho antes da implementação (`catalogue.test.tsx`, bloco "finding a tool by name or domain"). |
| 3. "Blocked by needs the X integration" | **FEITO** | Causa raiz: `platform/config_service/catalogue.py`'s `refusal_for` já produz a frase completa "needs the X integration", e o console concatenava "Blocked by " na frente sem saber disso. Corrigido só no console, reaproveitando o padrão que `agent.tsx`'s `ToolGroup` já usava (preferir `requiredIntegrations` estruturado em vez do texto livre), com um link "Connect it"/"Conectar" para a Configuration do nó. Nada em `platform/config_service/catalogue.py` foi tocado. Teste confirmado vermelho contra a string ANTES do fix (precisou reverter também `catalogue.blocked` em en.ts para provar o vermelho de verdade, não só o componente). |
| 4. 85 formulários de credencial abertos | **FEITO** | Resolvido sem esperar a extração de Integrations, pela cláusula de correção mínima do próprio critério de aceite. Novo componente `console/src/surfaces/integration-card.tsx`: card colapsado por padrão, formulário e verificação só aparecem ao expandir. Teste confirmado vermelho (nenhum toggle existia, todos os formulários apareciam sempre). |
| 5. Skills como parede de prosa | **FEITO** (pela alternativa "tabela com filtro") | Skills agora têm uma seção própria com um único cabeçalho "Skills (N)" em vez do prefixo "Skills — " repetido em cada linha, e são filtráveis pela mesma busca do item 2. A OUTRA alternativa do problema ("agrupar por domínio junto às tools") não foi feita — `gateway/http/routes/capabilities.py`'s `SkillView` não expõe `domain` para skills, só `name`/`description`; isso exigiria uma mudança de backend não feita nesta passada. Nomeado, não corrigido. |
| 6. Badge UNKNOWN sem explicação | **FEITO** | O diagnóstico anterior ("Depende do F5 — store de verificação") estava certo. Corrigido de ponta a ponta: novo `HealthStatus.UNCONFIGURED` (`integrations/_catalogue/entry.py`), novo parâmetro `configured` em `catalogue()` (`integrations/_catalogue/discovery.py`), e `gateway/http/routes/integrations.py` agora junta a leitura em massa do vault que `gateway/http/configured.py` já fazia para o estate — sem precisar regenerar `openapi.json` nem o cliente gerado, porque `health` já era `str` livre. No console, cada card mostra o estado real (ausente/armazenada/verificada/falhando) com uma legenda fixa por estado, sem precisar expandir nada, e reaproveita o `VerifyStep` do First Steps para o teste de credencial "aqui também". |

## Critérios de aceite — estado

- Encontrar uma tool pelo nome leva < 5 s (busca na página) — **FEITO** (item 2).
- Credenciais não aparecem na rota de catálogo, ou colapsadas com estado real — **FEITO na correção mínima** (itens 4 e 6); a extração completa da rota (item 1) continua não feita.
- Nenhum texto "Blocked by needs the" — **FEITO** (item 3), verificado com teste que reproduziu o texto quebrado antes do fix e confirmou sua ausência depois.
- Estado de cada integração legível sem expandir — **FEITO** (item 6).

## Notas para a próxima confrontação desta tela

- `make console-visual` não reconstrói o console sozinho — `scripts/visual.mjs`
  serve `.next/standalone/server.js` já compilado. Rode `make console-build`
  antes, ou um "passou" pode só significar que o build está desatualizado
  (foi exatamente o que aconteceu aqui: 35/35 na primeira rodada, contra um
  build de antes desta sessão; 33/35 depois de reconstruir, com a diferença
  real em `catalogue-1440-light` e, à parte, uma diferença pré-existente e
  não relacionada em `knowledge-1440-light` — ver `relatorio-confronto.md`).
- A baseline `knowledge-1440-light` está desatualizada em relação ao `en.ts`
  atual (falta a frase que a confrontação 024 já adicionou a
  `knowledge.proposals.lead`). Não é desta tela; deixado para quem
  recapturar as baselines.
- `SkillView` (`gateway/http/routes/capabilities.py`) não expõe `domain`
  para uma skill — só para uma tool. Enquanto isso não mudar, a alternativa
  "agrupar skills por domínio" do item 5 não é possível sem uma mudança de
  backend.
- `tests/architecture/test_one_fictional_deployment.py`'s
  `test_exactly_one_fictional_deployment_exists_in_the_repository` pode
  falhar transitoriamente se `console/playwright-report/` ou
  `console/test-results/` (ambos no `.gitignore`) estiverem no disco quando
  a suíte de arquitetura rodar — o verificador não os exclui. Limpe-os antes
  de rodar `tests/architecture/` depois de `make console-visual`.
