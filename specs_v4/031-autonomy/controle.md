# Controle — 031 Autonomy

| Item | Estado | Detalhe |
|---|---|---|
| 1. Heading "Bounds no level overrides" | **FEITO** (`bf5f055`) | en: "Bounds and level overrides"; pt-BR: "Limites e exceções de nível" (seguindo o vocabulário que o catálogo pt-BR já usa para override). Reconfirmado na auditoria de 2026-08-14: os dois catálogos ainda trazem o texto correto (`en.ts:972`, `pt-BR.ts:856`), testado por três cenários em `autonomy.test.tsx`. Ver `relatorio-confronto.md`. |
| 2. Três painéis com o mesmo vazio | **FEITO** — controle anterior dizia NÃO INICIADO e estava errado | Já corrigido antes desta auditoria: o painel de Bounds só some da página quando repetiria o mesmo "nada registrado" das Rules (`showBounds`, `autonomy.tsx:228`); o editor da regra fica sempre visível logo abaixo, já pré-preenchido com a primeira regra, nunca vazio. Os testes que provam isso já existiam em `autonomy.test.tsx` e passaram sem alteração. Uma tentativa de trocar a ação do único estado vazio restante ("Look at the configuration" → "Create the first rule", âncora na própria página) foi revertida por quebrar um invariante existente e testado em `first-run.test.tsx` ("gives every empty state an action that names a place this console has"), que exige que toda ação de estado vazio aponte para uma área registrada do console, nunca uma âncora de página. O critério de aceite ("um único empty state quando não há política") já valia antes e continua valendo. Ver `relatorio-confronto.md`. |
| 3. Tela não explica o próprio modelo | **FEITO** — metade já existia, metade construída em 2026-08-14 | As descrições dos quatro níveis no `<Select>` (o critério de aceite fala em "três", mas o produto já tem um quarto, `act_silently`, coberto pelo mesmo mecanismo) já existiam em `postures.ts`, como frases completas, não slugs — isso já satisfazia o critério de aceite. A introdução de três linhas definindo rule/bound/override, que a spec também pede, estava genuinamente ausente e foi adicionada (`data-testid="autonomy-glossary"`, novas chaves `autonomy.glossary.*`). Ver `relatorio-confronto.md`. |
| 4. Revogar override sem lista | **FEITO** — corrigido em 2026-08-14 | O campo livre "Name of the override" foi removido inteiramente. Os overrides ativos deste nó agora aparecem numa lista (`data-testid="active-override"`), cada um com seu próprio botão "Revoke" (`data-testid="revoke-override"`) — nada para digitar. Um nó sem override ativo mostra uma frase dizendo isso em vez de uma lista vazia. Ver `relatorio-confronto.md`. |
| 5. Relação com "Stop automation" | **FEITO** — controle anterior dizia NÃO INICIADO e estava errado | Já corrigido antes desta auditoria: a linha "Automated writes stopped" no painel de Bounds já renderiza o mesmo `KillSwitchControl` da topbar (`autonomy.tsx:442-446`), com a frase completa do próprio deployment (quem parou, quando) e o botão de retomar para quem tem permissão. Os dois testes que provam isso já existiam em `autonomy.test.tsx` e passaram sem alteração. Ver `relatorio-confronto.md`. |
| 6. Campos crus do Grant | **FEITO** — corrigido em 2026-08-14 | "Name" e "Reason" ganharam uma dica abaixo do campo (o que o identificador significa e que aparece na trilha de auditoria; que o motivo é registrado na auditoria). "Seconds (optional)" virou um select "Duration" com os presets exatos que a spec pede — padrão do deployment (2h), 1h, 8h, 24h (o teto do próprio deployment) — e "Duração personalizada…", que só então revela o campo numérico. Ver `relatorio-confronto.md`. |

## Nota da auditoria de 2026-08-14

Ao corrigir os itens 4 e 6, uma leitura do bloco `autonomy.*` de `pt-BR.ts` (as
linhas que esses dois itens precisavam tocar) encontrou seis europeísmos
alcançáveis por esta tela, corrigidos junto: `Selector` → `Seletor` (consoante
muda, mesma classe de `Objectivo`/`Activar` já corrigidos em 022 Detectors);
`autónomo`/`autónomas` → `autônomo`/`autônomas`, três vezes (o mesmo
desvio agudo/circunflexo de `sinónimo`/`sinônimo`); `registada` → `registrada`,
duas vezes, no próprio estado vazio da tela.

Dois vizinhos foram deliberadamente mantidos: `autonomy.editor.save`/
`.saving`/`.saved`'s "Guardar" é escolha lexical válida nos dois dialetos —
mesmo julgamento que 022 Detectors já registrou para a palavra idêntica, não
um europeísmo — e `autonomy.preview.*` (que também tem "histórico registado")
não é lido por nenhum código do console, chave morta, não tocada.

Um padrão maior da mesma grafia "registada" (europeia) foi encontrado
espalhado por pelo menos seis outras telas (Topology, Runs, Incidents,
Memory, Audit, Agent) — fora do escopo desta spec, nomeado no relatório para
quem confrontar essas telas.

`platform/guardian/resolution.py`, citado como ponto de partida provável, foi
verificado e confirmado irrelevante para esta tela — resolve o catálogo de
detectores embarcado (feature diferente, já documentado por 022 Detectors),
não o `platform/autonomy/` que esta tela de fato lê e escreve.

Ver `relatorio-confronto.md` para a evidência completa, linha por linha, e os
testes que confirmaram cada item vermelho antes de corrigido.
