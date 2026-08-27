# Análise do controle — 001 Shell (pós-implementação)

## Resultado

O controle original marcava como concluídos alguns fluxos que os testes não
reproduziam com o contrato real da API. As divergências encontradas foram
corrigidas e o DoD da spec agora está verificável no código e nos testes.

| Item | Estado final | Evidência do código |
|---|---|---|
| 1. Tour | **Concluído.** A dispensa continua sendo persistida no deployment; o tour agora também pode ser reaberto explicitamente pelo menu da conta e pela palette, com fechamento por **X**. O replay ignora dispensa/setup apenas quando o parâmetro explícito está presente. | [`tutorial-setting.ts`](../../console/src/surfaces/first-run/tutorial-setting.ts:24), [`tutorial.tsx`](../../console/src/surfaces/first-run/tutorial.tsx:43), [`dashboard.tsx`](../../console/src/surfaces/screens/dashboard.tsx:73), [`topbar.tsx`](../../console/src/shell/topbar.tsx:228), [`commands.ts`](../../console/src/shell/commands.ts:152) |
| 2. CTA final | **Confirmado.** O último slide grava a dispensa e navega para `/first-run`. | [`tutorial.tsx`](../../console/src/surfaces/first-run/tutorial.tsx:145) |
| 3. Busca global | **Concluído com o contrato real.** Recursos usam `display_name`, e o resultado navega para a tela existente com `/resources?selected=id`; a busca por incidente/run e o filtro de permissões permanecem ativos. | [`search.ts`](../../console/src/shell/search.ts:89), [`resources.tsx`](../../console/src/surfaces/screens/resources.tsx:268), [`search.test.ts`](../../console/tests/unit/shell/search.test.ts:48), [`search-route.test.ts`](../../console/tests/unit/shell/search-route.test.ts:70) |
| 4. Erro técnico cru | **Concluído.** Summaries de runs recentes e encontrados também passam por `readFailure` antes de virar hint da palette; exceções conhecidas e desconhecidas não expõem marcador nem variável de ambiente. | [`commands.ts`](../../console/src/shell/commands.ts:77), [`commands.ts`](../../console/src/shell/commands.ts:161), [`search.test.ts`](../../console/tests/unit/shell/search.test.ts:230) |
| 5. Modal instável | **Confirmado.** Card com largura estável, corpo com altura fixa/rolagem e drawer do Investigate corrigido. | [`tutorial.tsx`](../../console/src/surfaces/first-run/tutorial.tsx:85), [`investigate.tsx`](../../console/src/live/investigate.tsx:98) |
| 6. Idioma | **Confirmado.** Seletor persistente, fallback por prefixo e catálogo pt-BR completo continuam cobertos. | [`messages.ts`](../../console/src/i18n/messages.ts:80), [`topbar.tsx`](../../console/src/shell/topbar.tsx:237) |
| 7. Pluralização/microtextos | **Concluído.** Além da pluralização existente, o badge de Runs agora comunica que o número representa execuções falhadas; os demais badges têm rótulos semânticos próprios. | [`sidebar.tsx`](../../console/src/shell/sidebar.tsx:51), [`en.ts`](../../console/src/i18n/en.ts:59), [`chrome.test.tsx`](../../console/tests/unit/shell/chrome.test.tsx:170) |
| 8. Rótulos da topbar | **Confirmado no código atual.** Não existe switcher de organização interativo para corrigir: o nome do deployment é um `<span>`, o account/avatar já tem nome acessível e tema/densidade têm tooltip. Nenhum controle sem nome foi reproduzido. | [`topbar.tsx`](../../console/src/shell/topbar.tsx:132), [`topbar.tsx`](../../console/src/shell/topbar.tsx:207), [`chrome.test.tsx`](../../console/tests/unit/shell/chrome.test.tsx:312) |
| 9. Stop automation | **Concluído.** A confirmação informa o efeito, autoria/data continuam sendo mostradas depois da resposta do deployment, e o diálogo agora tem link explícito para a postura em Autonomy. | [`stop.tsx`](../../console/src/shell/stop.tsx:161), [`stop.tsx`](../../console/src/shell/stop.tsx:173), [`stop.test.tsx`](../../console/tests/unit/shell/stop.test.tsx:87) |
| 10. Guardian footer | **Confirmado.** Link para `/autonomy` e tooltip explicativo permanecem implementados. | [`sidebar.tsx`](../../console/src/shell/sidebar.tsx:171), [`chrome.test.tsx`](../../console/tests/unit/shell/chrome.test.tsx:137) |

## Casos que evitam falso positivo

- Os fixtures da busca agora usam `display_name`, que é o campo devolvido por
  [`ResourceSummaryView`](../../gateway/http/routes/estate.py:83), em vez de
  validar o campo inexistente `name`.
- O teste de navegação valida a URL que a aplicação realmente atende:
  `/resources?selected=r1`; não há página `/resources/[id]`.
- Há testes separados para summaries crus em runs recentes e em runs
  encontrados pela busca.
- O replay do tour é testado em dashboard já configurado e com dispensa
  persistida, não apenas no primeiro acesso.

## Validação do DoD

- Suíte completa do console: **118 arquivos, 1.899 testes**.
- TypeScript estrito: `pnpm exec tsc --noEmit` — aprovado.
- ESLint: `pnpm exec eslint .` — aprovado.
- Formatação: `pnpm exec prettier --check src tests` — aprovada.
- Literais CSS: `node scripts/check-css-literals.mjs` — aprovado.
- `git diff --check` — aprovado.

Conclusão: não há pendência funcional identificada neste controle. O item 8
permanece uma confirmação da auditoria — não foi criado um switcher de
organização que a implementação atual não possui — e os itens 1, 3, 4, 7 e 9,
que tinham divergências reais, foram corrigidos e cobertos por testes.
