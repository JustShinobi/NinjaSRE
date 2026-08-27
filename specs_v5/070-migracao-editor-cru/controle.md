# Controle — Aposentadoria do editor de configuração cru

Estado verificado contra o código em `eb8c6f1`, depois do `make verify` sair 0
e do `spec-verifier` rodar em contexto limpo e voltar **PASS**.

**Este arquivo foi reescrito pelo orquestrador em 2026-08-16.** A versão
anterior descrevia "a Parte 1 de 3" e parou ali: o worker que a escreveu
morreu, e os quatro que vieram depois também. Ela ficou dizendo 40 campos com
dona e 74 sem, números que a própria feature superou horas depois. O
verificador independente apontou isso como o achado processual dele, com razão
— um controle que descreve um checkpoint vermelho enquanto a árvore está verde
é pior que nenhum, porque é lido como evidência.

**Quem escreveu o quê.** Cinco `spec-implementer` morreram nesta feature (três
tetos de turno, um limite de conta, mais um teto) e **nenhum entregou
relatório**. Todo estado registrado aqui foi medido pelo orquestrador no disco
depois de cada parada. Repartição real:

- **Workers:** o mapa em três categorias, o alvo `check-config-parity`, o
  `AdvancedConfigSection`, a mudança do `resolution-preview` e do
  `provenanceLabel` para `design/`, as seções de Autonomy, Alert intake,
  Knowledge, SSO, Integrations e Capabilities, a tabela de redirecionamento, a
  varredura de CTAs e todo o i18n.
- **Orquestrador:** a correção da premissa dos arrays (§3), a devolução dos 43
  campos que um worker declarou como tendo dona antes de construir as telas
  (§4), a seção do agente, o suporte a múltiplos prefixos no componente
  compartilhado, a remoção inteira do editor, os nove testes que a remoção
  quebrou, os três testes de navegador, e a revisão e aceitação dos seis
  baselines.

## 1. Ledger

| Peça | Estado | Detalhe |
|---|---|---|
| Mapa de paridade completo, grupo → tela dona | FEITO | `console/src/shell/config-ownership.ts`, três categorias: **105 com dona**, **2 de máquina**, **9 sem controle**. Total 116 = o schema inteiro (`declared_fields()`). Sem sobreposição, sem caminho que o schema não declare. |
| Verificação automática falha quando um campo não tem dona | FEITO | `tests/contract/console/test_console_config_ownership.py`. A invariante que autoriza a remoção é `test_no_field_the_raw_editor_can_reach_is_left_with_no_control`, e ela nasceu **vermelha** nomeando 61 campos. Verde hoje. |
| Guard check no gate padrão | FEITO | Alvo `check-config-parity` no `Makefile`, ligado ao `verify`. Envolve a suíte de contrato em vez de reimplementar a caminhada pelo schema, com a razão dita no próprio comentário: uma segunda implementação de "percorra o schema, percorra o mapa" é um segundo lugar para os dois divergirem. |
| Prévia de resolução como componente compartilhado | FEITO (em substância) | `console/src/design/resolution-preview.tsx`, movido de `surfaces/settings/`, com os 11 testes intactos — o diff entre o arquivo velho e o novo tem **uma** linha, o caminho do import. A prévia em si é a do `ConfigEditor`, que **já existia** (`preview.tsx:566-585`, e o botão de salvar só aparece com prévia atual, `:718-732`). Verificada, não reconstruída. |
| Origem do valor efetivo em toda tela dona | FEITO (já valia, verificado) | `FieldRow` já imprimia `Set at: <nó>` / `usingDefault` / `inherited` (`preview.tsx:810-824`), e a `EffectiveFieldsTable` mostra valor e origem mesmo para quem não pode escrever. |
| Seções avançadas recolhidas nas telas donas | FEITO | **12 seções em 7 páginas**, todas pelo `console/src/surfaces/advanced-config-section.tsx`: `screens/agent.tsx` ×2 (agents, capabilities), `screens/knowledge.tsx` ×4, `screens/integrations.tsx` ×1, `settings/schedules-destinations.tsx` ×2, `settings/alert-intake.tsx` ×1, `settings/autonomy.tsx` ×1, `settings/sso.tsx` ×1. Recolhidas por padrão via `<details>` sem `open`, sem script de cliente. |
| Editor cru removido | FEITO | `console/src/surfaces/screens/configuration.tsx` apagada. Nenhuma referência a `screens/configuration` ou `ConfigurationScreen` sobrou na árvore. |
| `/configuration` redireciona por seção | FEITO | `console/src/shell/configuration-redirect.ts` deriva a tabela **do mapa**, não de uma segunda lista. O encaminhamento é no navegador porque o grupo vinha no fragmento da URL e fragmento nunca chega ao servidor — `console/src/app/(shell)/configuration/page.tsx`. |
| Nenhum CTA, rota ou tela expõe o editor genérico | FEITO | Varredura em `console/src/`; os CTAs foram repontados para a dona do assunto (ex.: "Connect it" agora vai para `/integrations`, que é onde se conecta integração). Provado em navegador: `tests/e2e/settings-nav.spec.ts` (o redirecionamento e o bookmark de seção) e `tests/e2e/surfaces.spec.ts`. |
| Valor inválido gravado por fora aparece com aviso | **NÃO FEITO** | Ver §5. |

## 2. Gates — números reais, medidos pelo orquestrador

| Gate | Resultado |
|---|---|
| `make verify` (composto) | **EXIT=0** |
| `pytest` (dentro do verify) | **14096 passaram, 25 pulados, 0 falharam**, 626s |
| `npx vitest run` | **2230 passaram em 139 arquivos** |
| `playwright` | comportamento **134** (+1 pulado por desenho), first-day **10**, visual **30** |
| `make check-config-parity` | **19 passaram, EXIT=0** |
| `npx tsc --noEmit` / `eslint .` / `prettier --check .` | EXIT=0 nos três |
| paridade i18n | en 1404 = pt-BR 1404, sem órfão, sem europeísmo nas linhas novas |

O verificador reproduziu de forma independente: `tests/contract/console/`
**339 passaram, 0 falharam**; `test_console_config_ownership.py` 19;
`test_console_shell.py` 36; `tsc --noEmit` EXIT=0. Ele **não** re-rodou o
`make verify` completo, o `vitest` completo nem as suítes Playwright — foi
instruído a gastar os turnos na leitura, e disse isso no relatório dele.

## 3. A premissa que estava errada, e era a que machucava

O mapa afirmava — e a primeira versão do briefing repetiu — que array e objeto
"não são editáveis em lugar nenhum". **Falso.** `preview.tsx:239`:
`isObjectList` é `type === 'array' && itemFields.length > 0`, e um array cujo
schema descreve a forma da entrada é desenhado como `ObjectList`, com
adicionar, remover e reordenar. **Dezoito campos** satisfazem isso, entre eles
`transit.destinations`, `surfaces.channels` e `policies.observation.detectors`.

O editor alcançava **104 campos, não 86**. Quatorze dos dezoito não tinham tela
humana nenhuma: apagar o editor teria destruído a única superfície de edição
deles — a regressão de capacidade que o mapa existe para impedir, chegando pelo
mecanismo escrito para detectá-la.

O teste passou a ler `reachable_fields()` = os quatro tipos escalares **mais**
array com `item_fields`. O verificador leu o `FieldRow` inteiro
(`preview.tsx:761-870`) e confirmou que não há terceiro caminho de renderização:
`lockedBy` → `isObjectList` → `EDITABLE_TYPES` → `field-not-editable`. A
definição em Python e o componente em TSX concordam exatamente.

## 4. O erro que quase passou

Um worker moveu os 47 campos pendentes para `CONFIG_FIELD_OWNERS` **no começo**
e morreu antes de construir quatro das cinco telas. O portão de paridade ficaria
**verde sobre telas que não existiam**. Só o `tsc` pegou, porque um import ficou
sem uso. O orquestrador devolveu os 43, corrigiu todas as contagens e rodou de
novo para ver o vermelho voltar.

A regra que isso deixou: **um caminho sai de "sem controle" na mesma mudança que
torna o controle real** — nunca em lote, nunca adiantado.

## 5. O que fica pendente, com dono

- **Valor inválido gravado por API aparecendo com aviso de validação na tela
  dona** — não construído. Era a única task de polimento da spec e não foi
  feita; o `ConfigEditor` mostra a recusa do deployment ao salvar, mas não
  marca um valor já gravado que o schema hoje rejeitaria. Dono: quem retomar.
- **Duas asserções de navegador perdidas, nomeadas em vez de silenciadas.**
  (a) O teste do preview deixou de afirmar `getByTestId('gated')` ao ser
  repontado, porque nenhum campo alcançável pela seção do agente é ao mesmo
  tempo real no schema e gated na fixture; a propriedade segue coberta em
  unitário (`tests/unit/surfaces/config-editor.test.tsx`, `approvalGated`).
  (b) `behaviour.test.tsx` perdeu "reads a configuration node the address
  names", que afirmava `config-value` e `provenance` — testids exclusivos da
  tela apagada. Ambas foram achadas pelo verificador; a segunda eu já tinha
  rastreado, a primeira não tinha nomeado.
- **Não existe mais uma tabela única com todos os valores resolvidos.** O
  editor cru tinha essa visão de "percorrer tudo num lugar só" e nenhuma tela
  a substitui — por desenho, já que a decisão da onda é uma dona por assunto.
  Nenhum requisito pedia essa tabela, mas é uma mudança de capacidade e está
  dita aqui em vez de descoberta depois.
- **O catálogo de campos do mock plane está velho.**
  `fixtures/scenarios/populated/config-fields.json` serve `approval.required_above`,
  `investigation.max_loops`, `retention.audit_days` — o verificador conferiu os
  quatro contra `declared_fields()` e **nenhum existe no schema**. Só
  `agents.max_iterations` e `agents.tool_budget` batem dos dois lados, então o
  `ConfigEditor` dentro das seções avançadas só é exercitado contra campos reais
  na do agente. Antecede a 070 e nem 040/050/060 regeneraram. Dono: quem mantém
  `tools/mockplane/`.
- **T003** (teste de que o console consome o mapa pela API) — declarado não
  construído: o mapa responde "qual tela do console edita este campo", e nenhum
  módulo Python pode conhecer id de tela sem inverter a tabela de tiers.
- **T007** (aviso dentro do editor para grupos migrados) — perdeu o sujeito
  quando o operador decidiu que o editor morre nesta feature.
- **SC-001 e SC-003 equivalentes** (critérios de usabilidade humana) — não
  reivindicados, como nas features anteriores da onda.

## 6. A área `configuration` continua declarada, e é deliberado

O orquestrador tinha instruído o worker a **remover** a área de `routes.ts`.
O repositório já tinha resposta própria: `/autonomy`, `/administration` e
`/signals` mantêm a entrada com `visible: () => false` e redirecionam, e
`test_the_deploy_walk_covers_exactly_the_areas_the_console_declares` exige que
`SHELL_PATHS` bata **exatamente** com as áreas declaradas. Seguir o padrão do
repositório venceu seguir a própria instrução. O verificador confirmou que essa
foi a escolha certa e que o teste passa.

## 7. Baselines visuais

Seis divergiram, todos páginas que ganharam seção avançada visível: `agent`,
`agent-tools`, `knowledge` ×3, `single-sign-on`. Foram **revisados como imagem,
um a um**, dentro da imagem de captura fixada, antes de aceitar: em todos, a
seção nova recolhida e a altura que ela acrescenta são as únicas diferenças, com
cada painel acima inalterado pixel a pixel. Os outros 24 voltaram
**byte-idênticos**, o que é a prova de que não houve deriva de ambiente junto.
Cada `accepted.reason` no `screens.json` registra o que esta leva cobriu.

Um `.png` commitado foi **apagado**: `configuration-1440-light.png`, junto da
entrada dele no `screens.json`, porque a tela que ele fotografava deixou de
existir. Nenhum outro foi tocado. O verificador conferiu:
`git diff 0ae8369..HEAD --stat -- '*.png'` dá exatamente 7 arquivos, 1 remoção e
6 modificações.

## 8. Commits

- `e249ca3` — a feature.
- `3ca449b` — a suíte de navegador repontada para as telas que substituíram o editor.
- `eb8c6f1` — os seis baselines revisados e aceitos.
