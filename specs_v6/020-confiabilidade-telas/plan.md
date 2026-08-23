# Implementation Plan: Confiabilidade das telas

**Branch**: `feat/v6-020-confiabilidade-telas` | **Date**: 2026-08-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v6/020-confiabilidade-telas/spec.md`

**Referência visual (DoD)**: `specs_v6/mockups/settings-v6.html#m5` (contagem
única), `#m2` (coluna Value de guardrails), `#m1` ("Set at" uma vez só)

## Summary

Cinco defeitos P1 confirmados ao vivo, cada um com a causa localizada no
console, mais o instrumento que impede a reincidência. O eixo comum é o mesmo:
uma tela afirma um fato que ela própria não sustenta — uma contagem sem linhas,
uma origem sem valor, um denominador sem população, um erro sem pergunta feita.
A correção é sempre a mesma forma: a afirmação passa a ser derivada da coisa
exibida, e não calculada em paralelo a ela.

A sexta entrega é uma suíte de comportamento committed que converte as quatro
regras transversais da onda em teste executável, com exceção anotada por rota
para o que outras features ainda vão redesenhar.

## Technical Context

**Language/Version**: TypeScript (console, Next.js App Router); nenhum trabalho
de gateway previsto — se a reprodução do audit apontar o contrato, entra Python
3.12

**Primary Dependencies**:

- `console/src/surfaces/settings/audit.tsx` — a contagem em `records.length` e
  o corpo em `groups`/`visible` são duas populações; a exclusão do principal
  `default` (constante local, linha 74) filtra o corpo e não a contagem, e o
  estado vazio do painel é decidido por `records.length === 0` (linha 349), de
  modo que um fetch inteiramente do próprio deployment desenha cabeçalhos, zero
  linhas e "Showing 200 of 156,735" por cima
- `console/src/surfaces/first-run/plan.ts` — `outstanding()` (linha 199) conta
  sobre `setup.steps`; `WIZARD_STEPS` é a segunda lista
- `console/src/surfaces/screens/first-run.tsx` — posição em
  `WIZARD_STEPS.length` (linha 386) ao lado de progresso em
  `setup.steps.length` (linha 408), com um comentário no próprio arquivo
  declarando a divergência intencional
- `console/src/surfaces/setup-hero.tsx` — a terceira exibição (linha 64)
- `console/src/surfaces/sso-setup.tsx` — `state.problems` renderizado como
  bloco vermelho sempre que não vazio (linhas 190-200), com os problemas vindos
  do servidor via `console/src/surfaces/settings/sso.tsx` (linha 136), antes de
  qualquer interação
- `console/src/surfaces/preview.tsx` — o `ConfigEditor` usado por
  `settings/autonomy.tsx` e `settings/notifications.tsx`: a célula de valor
  desenha `current` (o override), e a linha de origem prefixa
  `configuration.editor.setAt` ("Set at:") mesmo sob a coluna
  `configuration.column.provenance` ("Set at") — as duas metades do defeito de
  valor e do defeito de copy no mesmo lugar
- `console/src/surfaces/machine-token-groups.tsx` — contagens montadas por
  `labels.count.replace('{count}', …)` (linhas 309, 342, 476), contornando
  `formatCount` (`console/src/i18n/format.ts:38`), que já escolhe singular ou
  plural
- `config/constants/surfaces.py` — `CONFIG_SCREEN_VIEWPORT_WIDTH_PX` (1920),
  `CONFIG_SCREEN_VIEWPORT_HEIGHT_PX` (1080),
  `CONFIG_SCREEN_SCROLL_BUDGET_VIEWPORTS` (2.0): o orçamento já é constante
  nomeada, e a suíte transversal lê dali

**Storage**: N/A — nenhuma mudança de modelo ou de persistência

**Testing**: Vitest (`console/tests/unit/`), Playwright projeto `behaviour`
(`console/tests/e2e/`), Playwright projeto `visual` (baselines das telas
alteradas)

**Target Platform**: Console web

**Project Type**: Web (console); correção de comportamento de apresentação

**Performance Goals**: N/A — nenhuma mudança de volume de dados ou de consulta

**Constraints**: viewport de medição de rolagem é 1920×1080, declarado pela
própria suíte (o viewport global do Playwright é 1440×900); a suíte é arquivo
committed e não pode citar planejamento

**Scale/Scope**: 6 rotas tocadas (`/settings/audit-log`, `/first-run`,
dashboard, `/settings/single-sign-on`, `/settings/autonomy-guardrails`,
`/settings/notifications`, `/settings/machine-tokens`,
`/settings/models-providers`); 2 arquivos de teste novos

## Constitution Check

Contra `.specify/memory/constitution.md` 2.1.0.

- **Art. I (evidência sobre afirmação)**: é o artigo que esta feature aplica à
  interface. Uma tela que afirma 156.735 eventos e não mostra nenhum está
  fazendo exatamente o que a cláusula 4 proíbe — prosa confiante sobre
  evidência fina. Toda contagem passa a ser derivada da população exibida, e
  onde a tela não sabe, ela diz que não sabe (FR-011).
- **Art. II (autonomia limitada)**: o orçamento de rolagem e as dimensões do
  viewport de medição já são constantes nomeadas em `config/constants/
  surfaces.py`; a suíte transversal as lê em vez de repetir os números —
  nenhuma constante nova de guardrail nasce em call site.
- **Art. III (read-only por padrão)**: nenhuma ação nova sobre produção.
  Nenhuma correção aqui remove confirmação de operação consequente.
- **Art. IV (segredos)**: nenhuma superfície nova ecoa segredo. O SSO passa a
  exibir *menos* texto no estado virgem, não mais; os campos exibidos continuam
  os mesmos.
- **Art. V (runtime canônico)**: N/A — nenhuma mudança de runtime.
- **Art. VI (neutralidade de provider)**: N/A — nenhuma dependência de vendor.
- **Art. VII (aprendizado medido)**: N/A — nenhum mecanismo de memória tocado.
- **Art. VIII (arquitetura em camadas)**: trabalho confinado a `console/`; a
  leitura das constantes de orçamento pela suíte é leitura de `config/`, o tier
  folha, que é a direção permitida. O comportamento de cada correção fica no
  módulo dono — a derivação do progresso em `first-run/plan.ts`, a formatação
  de valor no componente de tabela de configuração — e não no arquivo
  compartilhado mais próximo.
- **Art. IX (capacidades declaradas)**: N/A — nenhuma capacidade ou integração
  tocada.
- **Art. X (o operador é dono dos dados)**: nada sai do host; a suíte roda
  local e em CI, sem serviço externo.
- **Art. XI (datastore único)**: N/A — nenhum acesso a storage.
- **Art. XII (test-first, trace-backed)**: cada um dos cinco defeitos entra
  como teste de reprodução vermelho antes da correção, e o vermelho é
  confirmado e registrado. O acceptance spec da feature é escrito antes das
  correções. Cláusula 5 respeitada: as regras transversais que inspecionam
  texto renderizado são testes de comportamento contra o build real, não
  varredura de código-fonte. Efeito na suíte sintética: nenhum — a feature não
  toca investigação (declarado, não omitido).
- **Art. XIII (idioma e atribuição)**: código, testes e strings de produto em
  inglês, com pt-BR pareado no i18n. Cláusula 4 é a restrição de projeto da
  suíte transversal: ela é committed e enuncia as próprias regras no próprio
  arquivo — nenhum link para spec, briefing, onda ou número de feature, e as
  exceções por rota trazem o motivo escrito por extenso em vez de apontar para
  a feature que as remove.

Nenhuma violação a registrar em Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs_v6/020-confiabilidade-telas/
├── spec.md
├── plan.md              # este arquivo
├── tasks.md
├── checklists/requirements.md
└── controle.md          # escrito pelo implementador, não aqui
```

### Source Code (repository root)

```text
console/src/surfaces/settings/audit.tsx          # uma população para corpo e contagem
console/src/surfaces/first-run/plan.ts           # a fonte única do progresso
console/src/surfaces/screens/first-run.tsx       # header e painel passam a consumir a fonte
console/src/surfaces/setup-hero.tsx              # card do dashboard, mesma fonte
console/src/surfaces/sso-setup.tsx               # estado de formulário: virgem/tocado/submetido
console/src/surfaces/settings/sso.tsx            # resumo neutro em vez de lista de requisitos
console/src/surfaces/preview.tsx                 # valor efetivo obrigatório; origem sem prefixo duplo
console/src/surfaces/machine-token-groups.tsx    # contagens via formatCount
console/src/i18n/{en,pt-BR}.ts                   # chaves de plural, "Not set", resumo neutro
console/visual/screens.json                      # telas alteradas + baselines

console/tests/unit/surfaces/…                    # unidade: derivação do progresso, formatação
                                                 # de valor, estado de formulário
console/tests/e2e/020-confiabilidade-telas.acceptance.spec.ts   # as alegações desta feature
console/tests/e2e/transversal-rules.spec.ts                     # as quatro regras da onda
```

## Decisões de design

- **Audit — a contagem é derivada, não paralela.** Corpo e contagem passam a
  descrever a mesma população. A exclusão do principal do deployment continua
  sendo o default de leitura (é a decisão certa: o operador quer pessoas), mas
  deixa de poder esvaziar a tela em silêncio — quando ela esconde tudo, a tela
  diz isso e oferece a saída, e o estado vazio do painel passa a ser decidido
  pelo que sobrou, não pelo que chegou. A reprodução vem primeiro, com fixture
  no shape real (200 eventos, todos do principal `default`, total muito maior),
  porque se o contrato do gateway for parte da causa, é o teste que vai dizer.

- **Contagem — uma lista, três leitores.** A fonte única deriva `(total,
  índice, pendentes)` da mesma lista que desenha o stepper, e header, painel e
  card passam a consumir a tripla. **Isto reverte deliberadamente a decisão
  registrada hoje em `screens/first-run.tsx`**, cujo comentário defende que "as
  duas linhas podem citar números diferentes porque medem coisas diferentes".
  O mockup `#m5` é normativo em sentido contrário: uma linha, "Step 5 of 7 —
  check that each of them works · 2 steps left", derivada da mesma lista. A
  reversão é o ponto da feature, não um efeito colateral: dois denominadores
  corretos em separado somam uma tela que mente. O comentário sai junto com o
  código que ele defendia.

- **SSO — o formulário ganha estado.** Virgem, tocado por campo, submetido. Os
  problemas que o deployment devolve continuam sendo verdade sobre a
  configuração; deixam de ser exibidos como acusação a quem ainda não digitou.
  No estado virgem eles viram um resumo neutro; a partir do primeiro blur ou do
  submit, aparecem ancorados nos campos. A tradução de chave para label humano
  usa os labels que o próprio formulário já declara, e não uma segunda tabela.

- **Valor — o componente passa a exigir.** A correção não é preencher duas
  telas; é fazer o componente de tabela de configuração recusar uma linha sem
  valor renderizável, de modo que a próxima tela que o usar não possa repetir o
  defeito. Formatação por tipo mora com o componente. A origem fica na coluna
  de origem, e o rótulo prefixado só sobrevive onde a linha é autônoma — o que
  fecha "Set at Set at:" pela mesma mudança.

- **Copy — o defeito é a rota alternativa.** "1 tokens" existe porque a
  contagem foi montada por `replace('{count}', …)` em vez de passar por
  `formatCount`, que já resolve plural. A correção é fechar a rota alternativa
  nas três ocorrências, não corrigir uma string.

- **Suíte transversal — regra global, exceção local.** Quatro regras, rodadas
  sobre as rotas de Settings. Uma rota que ainda viola por pertencer a um
  redesenho futuro entra como exceção anotada *naquela rota e naquela regra*,
  com o motivo substantivo escrito ali (por exemplo: a tela de autonomia
  desenha 2,3 viewports porque ainda concentra sete assuntos numa página). A
  regra continua valendo para todas as outras rotas. O repositório já tem o
  precedente da forma em `console/tests/e2e/scroll-budget.spec.ts`
  (`expectedOverBudget`, com `test.fail`, nomeado em vez de escondido); a suíte
  nova segue o mesmo princípio com `test.fixme` por rota.

- **Relação com as suítes que já existem.** `vocabulary.spec.ts` e
  `scroll-budget.spec.ts` cobrem hoje um recorte próprio (o vocabulário de
  estado de credencial; o orçamento das telas de configuração). A suíte nova
  não as substitui nem as duplica: ela é o instrumento de fronteira de feature
  desta onda, com a lista de bans e o conjunto de rotas da v6, e reaproveita as
  constantes e o helper de sessão em vez de recriá-los. Se a sobreposição de
  uma asserção específica ficar exata, a asserção duplicada sai da suíte nova —
  duas cópias da mesma regra divergem.

## Gates que esta feature toca

- `make verify` completo: lint, format-check, typecheck, check-imports,
  check-constants, check-protocols, check-deps e a suíte.
- Vitest: novos testes de unidade em `console/tests/unit/`.
- Playwright `behaviour`: acceptance spec da feature + suíte transversal.
- Playwright `visual`: `console/visual/screens.json` e captura deliberada de
  baseline para as telas alteradas que já estão registradas — audit log
  (`/settings/audit-log`), first-run (`/first-run`), autonomy
  (`/settings/autonomy-guardrails`), notifications (`/settings/notifications`)
  e models-providers (`/settings/models-providers`). Single sign-on não está
  registrada hoje; entra no registro se a mudança de estado virgem merecer
  baseline.
- Nenhum gate Python é tocado, salvo se a reprodução do audit levar ao
  contrato do gateway — nesse caso, contrato em `tests/contract/`.
