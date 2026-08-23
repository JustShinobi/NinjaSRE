# Controle — 011 Incidents

| Item | Estado | Detalhe |
|---|---|---|
| 1. O vazio não explica o vazio | **FEITO** (onda 3) | O ecrã lê `/v1/detectors` (falha suave: um erro lê-se como "não se sabe", não como "nenhum detector ligado") ao lado de `readSetupState`, e compõe `firstCause(watchingCause, setupCause)`. A causa de observação ganha à do setup por ser a mais específica: um deployment pode ter o checklist fechado e continuar sem detector nenhum, e aí "termine a configuração" seria conselho para algo já feito. Quando nenhuma das duas se aplica, fica o texto que já existia — que aí sim tranquiliza. |
| 2. Filtros que filtram nada | **FEITO** (onda 3) | Um controlo de estado ou severidade que só tem "Any" para oferecer sai da barra em vez de ser renderizado morto. |
| 3. CTA duplicado na árvore de acessibilidade | **FEITO** (onda 3, global) | O `EmptyStateAction` usa `href` para navegação e `onSelect` para ações, sem duplicar elementos. O `Panel` e o helper de páginas inexistentes renderizam um único controlo. Resolve o mesmo item em 013 e 023. |
| 4. Preview do que um incidente será | **FEITO** (onda 4) | O empty state oferece “Ver um incidente de exemplo” e leva a um preview local, explicitamente estático, com estado, gravidade, detector, assunto e evidência. Não cria nem altera um incidente real. |

10 testes de incidents, incluindo as regressões da onda 4, confirmados vermelhos antes da implementação das correções.
