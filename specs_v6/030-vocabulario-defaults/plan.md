# Implementation Plan: Vocabulário sem cru e defaults seguros de token

**Branch**: `feat/v6-030-vocabulario-defaults` | **Date**: 2026-08-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v6/030-vocabulario-defaults/spec.md`

**Referência visual (DoD)**: `specs_v6/mockups/settings-v6.html#m2` (títulos humanos no lugar dos grupos `policies.*`) e `#m3` (delivery token nomeado, com rotação). Members & roles e Machine tokens não têm mockup v6: valem as regras transversais da v5 (`specs_v5/mockups/settings-v5.html`, Parte 3) e o mockup-1 da v5.

## Summary

Três obras que compartilham uma raiz — o produto exibindo o que a máquina
respondeu no lugar do que a pessoa precisa ler — e uma que compartilha só o
lugar.

1. **Dez vazamentos de vocabulário**, cada um cravado em `file:line` pelo
   diagnóstico, resolvidos onde o valor é escolhido e não onde ele é pintado. A
   maioria é uma chip recebendo um valor de transporte
   (`console/src/components/status.tsx` renderiza `presented.label` sob a classe
   `uppercase`, então `service_account` chega à tela como `SERVICE_ACCOUNT`); o
   conserto é dar à chip um rótulo já resolvido, não um `toLowerCase` no meio do
   caminho.
2. **O default de escopos**, que hoje é uma linha
   (`console/src/surfaces/machine-token-groups.tsx:148`,
   `useState(new Set(issuedScopes))`) e vira conjunto vazio mais templates de
   finalidade — com a garantia equivalente no servidor, porque uma tela que
   manda menos não é uma promessa de que o servidor concede menos.
3. **A ação primária de Members & roles**, cuja forma depende de um fato que
   ainda não está estabelecido: o que o gateway já sabe fazer. A primeira tarefa
   do tasks.md é essa descoberta, e ela decide entre superficiar uma operação
   existente e criar uma rota com contrato e segurança próprios.

## Technical Context

**Language/Version**: TypeScript (console, React Server Components); Python 3.12 (gateway e `platform/identity/`)

**Primary Dependencies**: `console/src/surfaces/settings/{members,machine-tokens,autonomy,notifications,alert-intake}.tsx`, `console/src/surfaces/{machine-token-groups,tokens,grants,advanced-config-section}.tsx`, `console/src/components/status.tsx`, `console/src/design/status.ts`, `console/src/surfaces/first-run/plan.ts`, `console/src/i18n/{en,pt-BR}.ts`, `platform/identity/tokens.py`, `gateway/http/routes/identity.py`

**Storage**: N/A — nenhum modelo novo. A criação de pessoa, se exigir rota nova, escreve pelo port de identidade que já existe (`upsert_user`), nunca com SQL direto.

**Testing**: Playwright behaviour (`console/tests/e2e/`), vitest (`console/tests/unit/`), pytest contract e unit (`tests/contract/`, `tests/unit/platform/identity/`), visual (`console/tests/visual/` + `console/visual/screens.json`)

**Target Platform**: Console web + gateway HTTP

**Project Type**: Web, com duas garantias de servidor (default de escopos; criação de principal se o gateway ainda não a tiver)

**Performance Goals**: N/A — nenhuma leitura nova por linha. O nome legível de um recurso do estate sai do dado que a tela já leu, não de uma consulta por sugestão.

**Constraints**: `console/src/i18n/*.ts` são arquivos de escrita única na onda (README da v6) — esta feature os toca por inteiro no seu turno e não em paralelo com outra; `console/visual/screens.json` idem. O teto de escopos por emissor é preservado. Nenhum identificador desaparece do sistema: sai da face principal e continua no audit/API (FR-011).

**Scale/Scope**: 5 telas de console tocadas, 1 componente de chip, 1 formulário de emissão, 1 ação primária nova, 2 catálogos de i18n, 1 garantia de servidor no mínimo

## Constitution Check

Constituição em `.specify/memory/constitution.md`, versão 2.1.0. Artigo a artigo:

- **Art. I (evidência sobre asserção)** — sem efeito sobre conclusões do agente.
  A regra que mais se aproxima é a cláusula 4: quando o produto não consegue
  determinar algo, ele diz. Aplicada nas bordas do FR-008 e do FR-009 — um
  recurso sem nome resolvível e uma sessão sem origem conhecida mostram o que se
  sabe, nunca um rótulo inventado nem um espaço em branco.
- **Art. II (autonomia limitada)** — nenhum laço, orçamento ou teto novo. Os
  conjuntos que esta feature introduz (escopos destrutivos, templates de
  finalidade, agrupamento por domínio) são constantes nomeadas no módulo dono do
  formulário de emissão, nunca literais no ponto de uso (cláusula 6).
- **Art. III (read-only por padrão)** — o artigo governa ação em produção, e o
  default de 27 de 27 escopos é a versão de identidade do mesmo risco. FR-012 e
  FR-016 movem a concessão para o lado seguro; FR-015 põe o aviso no ponto da
  decisão, na superfície que o humano já está usando. Criar pessoa (FR-018) é
  escrita consequente: pede permissão e fica no audit.
- **Art. IV (segredos nunca alcançam o agente)** — o segredo do token continua
  exibido uma vez e nunca relido; nada nesta feature acrescenta superfície que
  ecoe credencial. O aviso do FR-015 nomeia o escopo, jamais o segredo.
- **Art. V (um runtime canônico)** — não tocado.
- **Art. VI (neutralidade de provider)** — não tocado. O vocabulário de erro do
  provider é da 010, declarado fora de escopo na spec.
- **Art. VII (aprendizado medido)** — não tocado; nenhum mecanismo de memória.
- **Art. VIII (arquitetura em camadas)** — a garantia de escopos mora em
  `platform/identity/`, que é quem possui a emissão, e não na rota que a chama
  nem no proxy do console (cláusula 3). Se a criação de pessoa exigir rota, ela
  entra em `gateway/http/routes/identity.py` — tier 1 chamando tier 3, na
  direção permitida. `check-imports` roda no gate.
- **Art. IX (capacidades declaradas)** — nenhuma capacidade ou integração nova; a
  paridade de integrações não muda. O FR-008 mexe no texto de uma sugestão, não
  no que a integração declara.
- **Art. X (o operador é dono dos seus dados)** — nada sai do host. Nenhuma
  telemetria, nenhuma retenção nova; a criação de pessoa grava no banco do
  operador como todo o resto.
- **Art. XI (datastore único)** — se houver escrita nova de identidade, ela passa
  pelo port de identidade existente. Nenhum SQL fora da camada de persistência.
- **Art. XII (test-first, com traço)** — cada FR chega com o teste antes da
  implementação e o vermelho confirmado, registrado no `controle.md`. O default
  de escopos ganha teste dos dois lados (formulário e servidor), porque uma tela
  que manda menos não prova que o servidor concede menos — é exatamente o caso
  da cláusula 4, um contrato que alguém pode quebrar do outro lado. A cláusula 5
  vale para os testes de vocabulário: a suíte transversal inspeciona texto
  renderizado no navegador, não fonte, e por isso mede o que promete.
- **Art. XIII (língua e atribuição)** — todo código, string de produto e mensagem
  de commit em inglês; o catálogo pt-BR é conteúdo de produto, não tradução do
  código. Nenhum arquivo committed passa a depender de arquivo não committed:
  nem a suíte transversal, nem o acceptance spec, nem qualquer teste referencia
  esta spec, o mockup ou a onda.

**Veredito**: sem violações. Complexity Tracking vazio.

## Project Structure

### Documentation (this feature)

```text
specs_v6/030-vocabulario-defaults/
├── spec.md
├── plan.md              # este arquivo
├── tasks.md
├── controle.md          # escrito pela última tarefa do tasks.md
└── checklists/requirements.md
```

### Source Code (repository root)

```text
console/src/components/status.tsx                  # chip: rótulo resolvido, não valor de transporte
console/src/design/status.ts                       # vocabulário de conta e de token
console/src/surfaces/settings/members.tsx          # FR-001, FR-002, FR-009, FR-010, FR-018, FR-019
console/src/surfaces/machine-token-groups.tsx      # FR-003, FR-012..FR-015, FR-017
console/src/surfaces/tokens.tsx                    # FR-009 (painel de sessões)
console/src/surfaces/grants.tsx                    # FR-010, FR-019
console/src/surfaces/advanced-config-section.tsx   # FR-005, FR-006 (título da seção)
console/src/surfaces/settings/autonomy.tsx         # FR-005 (só o título; estrutura é da 040)
console/src/surfaces/settings/notifications.tsx    # FR-006
console/src/surfaces/settings/alert-intake.tsx     # FR-007
console/src/surfaces/integration-catalogue.tsx     # FR-008
console/src/surfaces/first-run/plan.ts             # FR-004
console/src/design/resolution-preview.tsx          # FR-004 (preview do wizard)
console/src/i18n/{en,pt-BR}.ts                     # FR-020 — escrita única na onda
platform/identity/tokens.py                        # FR-016, FR-017 (garantia de servidor)
gateway/http/routes/identity.py                    # FR-018, se a descoberta exigir rota nova
console/tests/e2e/030-vocabulario-defaults.acceptance.spec.ts
console/tests/e2e/transversal-rules.spec.ts        # FR-021 — remoção dos fixme de vocabulário
console/tests/e2e/vocabulary.spec.ts               # a ressalva de HEALTHY em Administration cai
console/tests/unit/surfaces/…                      # chips, formulário de emissão, grants
tests/contract/… + tests/unit/platform/identity/   # default de escopos; criação de pessoa
console/visual/screens.json                        # baselines de members-roles e machine-tokens
```

**Structure Decision**: web application com dois pontos de servidor. Nenhum
módulo novo no console — cada FR é resolvido no módulo que já possui a decisão,
por Art. VIII cláusula 3. A única criação de arquivo garantida é o acceptance
spec; a criação de rota é condicional à descoberta.

## Decisões de design

- **A chip resolve o rótulo antes de renderizar, e não depois.** Hoje o `Badge`
  recebe o valor da API e o pinta em caixa alta; qualquer conserto local
  reaparece na próxima tela que passar um valor cru. O rótulo passa a ser
  escolhido por quem sabe o que aquele valor significa naquele domínio — tipo de
  principal, estado de conta, estado de token — e a chip continua sabendo exibir
  um estado que nunca ouviu, porque um deployment à frente do console não é
  falha (comportamento existente que fica preservado, com teste).
- **"Healthy" some de dois lugares por dois motivos diferentes.** Em pessoas é um
  erro de domínio: saúde não descreve gente. Em grupo de token é um literal
  fixo — `<Badge status="healthy" />` — que não descreve nada, e por isso vira o
  fato que o painel já tem em mãos: houve último uso ou não houve.
- **O default de escopos é dois testes, não um.** O formulário deixa de
  pré-marcar; o servidor deixa de aceitar "sem escopos" como "todos" se for isso
  que ele faz hoje. A segunda metade só é escrita depois que um teste de contrato
  mostrar o comportamento atual — pode já estar correto, e nesse caso o teste
  vira a prova de que continua.
- **Templates de finalidade são dados, não fluxo.** Um template é um nome, uma
  frase e um conjunto de escopos; escolher um marca as caixas e não tranca nada.
  Nenhum modo separado, nenhum passo a mais para quem quer escolher à mão.
- **Autonomy e Notifications recebem só o título.** O que muda é a string do
  cabeçalho de seção que hoje é um prefixo de schema. A estrutura das páginas —
  abas, orçamento de rolagem, tabela com valores — é da 040 e da 020; mexer nela
  aqui seria refazer o trabalho delas com menos contexto.
- **A ação de criar pessoa começa por uma pergunta, não por um desenho.** O
  deployment tem conta local configurada por ambiente e um port de identidade com
  `upsert_user`; se existe caminho HTTP para criar principal, ele é superficiado.
  Se não existe, a rota nasce aqui com teste de contrato e teste de segurança —
  criar principal é escrita privilegiada e a permissão é verificada no servidor,
  não só escondendo o botão.

## Gates que esta feature toca

- `make verify` inteiro: `lint`, `format-check`, `typecheck`, `check-imports`,
  `check-constants`, `check-protocols`, `check-deps` e a suíte Python.
- Vitest (`console/tests/unit/`) e Playwright behaviour (`console/tests/e2e/`),
  incluindo a suíte transversal da 020 com as exceções de vocabulário removidas.
- Suíte visual: `console/visual/screens.json` mais captura deliberada de baseline
  para `/settings/members-roles` e `/settings/machine-tokens`, que mudam de face.
- `console/tests/e2e/scroll-budget.spec.ts` — as duas telas tocadas continuam
  dentro do orçamento (SC-007).
- Sem efeito sobre `check-integration-docs`, `test_contract_coverage` ou a suíte
  de paridade: nenhuma integração, capacidade ou contrato de tier muda.

## Complexity Tracking

Sem violações constitucionais a justificar.
