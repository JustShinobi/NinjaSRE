# CONFRONTO — specs_v6

Registro do que cada feature da onda entregou, com os comandos reais, o
veredito independente e os riscos que sobraram. Escrito pelo orquestrador
depois do `spec-verifier`, nunca a partir do relato do implementador.

Regra desta onda: a aderência ao mockup é validada **em cada fronteira de
feature**, pela suíte transversal, não num confronto final. Este documento
acumula o resultado dessas fronteiras.

---

## 001-escopo-validavel — PASS

Catálogo cortado de 85 para 15 integrações; paridade total por integração
embarcada; ADR e gates ajustados. As 70 skills de metodologia dos vendors
removidos foram **arquivadas**, não apagadas — fora da raiz de descoberta,
porque `capabilities/skills/` é a própria raiz que `discover_skills` percorre.

Commit `6d1ede6`.

## 010-provider-out-of-the-box — PASS

Lista dinâmica de modelos vinda da API do vendor, probe com tool-calling
forçado, estados espelhados (passed · degraded · failed) sem tradução.

Commits `039efe9` + `091d134`. O segundo existe porque o primeiro carregou
junto `console/tests/unit/seeded.test.ts`, o arquivo transitório que um teste
de gate insere para provar que uma suíte vermelha reprova o build — encenado
por acidente ao adicionar o diretório `console/` em vez de caminhos de arquivo.

Pendente do operador: T043, o DoD ao vivo contra o CT254, inalcançável deste
checkout.

## 020-confiabilidade-telas — PASS

**Gate**: `make verify` exit 0 — 11733 passed, 25 skipped, 643.99s.
`behaviour` 167, `first-day` 15, `visual` 30/30, console unit 2301 com os
quatro thresholds de cobertura (branches 90.29%), `tests/contract/fixtures/`
107/0.

**Browser**: `populated` 23 passed/14 skipped; `audit-flooded` 8 passed/0
failed (a alegação de exclusão roda de verdade, não vazia); `first-run` 21
passed/2 esperadas-inaplicáveis.

**Commits**: `a4651c6` (45 arquivos, +6931/−549) e `b4a8153` (as três
baselines aceitas, isoladas).

**Veredito**: `spec-verifier` em segunda passada. A primeira reprovou com dois
achados P1, ambos reparados por decisão do operador:

- a lista desenhada não era a lista contada — o painel e o card desenhavam sete
  entradas de `WIZARD_STEPS` enquanto o número de pendentes contava os cinco
  itens de `setup.steps`. As três superfícies concordavam entre si só porque
  chamavam a mesma função. Corrigido desenhando `setup.steps`, com a asserção
  que faltava — linhas desenhadas contra número afirmado — em dois testes de
  unidade e dois de browser;
- o SC-003 era empiricamente falso: a ajuda de campo do SSO exibe três chaves
  OIDC em `snake_case` a todo carregamento. O operador manteve a copy e
  estreitou a alegação para copy de erro e validação.

**O que ficou nomeado como dívida, não corrigido aqui**: as exceções de
vocabulário por rota (`HEALTHY` nos chips de saúde, `policies.` e `surfaces.`
em títulos de grupo, jargão de entrega de webhook) pertencem à 030; o
orçamento de rolagem de `/settings/autonomy-guardrails` e `/settings/alert-intake`
pertence à 040. Cada uma é uma entrada da tabela `EXCEPTIONS` da suíte
transversal, com motivo substantivo, e some quando a feature dona corrigir a
rota.

**Risco que sobrou**: o campo Token endpoint do SSO desenha o literal
`[removed]`, placeholder do pipeline de masking. É **pré-existente** — está no
`sso.json` do HEAD anterior — mas a baseline aceita agora congela uma tela que
a feature descreve como virgem exibindo um valor de placeholder.

## 030-vocabulario-defaults — PASS

**Gate**: `make verify` exit 0 — 11761 passed, 25 skipped, 594.98s. Console
2362 testes em 143 arquivos com os quatro thresholds (branches 90.34%),
`visual` 31/31, `client-check` sem diff.

**Browser**: acceptance spec 13 passed / 1 skipped (o skip é a prévia do
wizard, cuja prova real é um teste de componente citado no próprio arquivo);
suíte transversal + vocabulário + acceptance juntas 42 passed / 8 skipped / 0
failed, rodadas duas vezes contra build de produção.

**Commits**: `554fc54` (69 arquivos, +4306/−291), `c730bfb` (cinco baselines),
`b7b4401` (cliente do console regenerado), `6f5246f` (locator ancorado no
heading), `bdb8336` (os dois chips de vocabulário).

**Veredito**: `spec-verifier` em segunda passada. A primeira **reprovou**, e a
reprovação foi de leitura, não de teste vermelho: o critério exige a suíte
transversal rodando nas nove páginas **sem nenhuma exceção de vocabulário**, e
sobrava a de `/settings/schedules-destinations`. O ledger classificava como "de
outra natureza"; o verificador testou essa classificação varrendo todas as
specs da onda atrás do dono do conserto, não achou nenhum, e concluiu que "fora
de escopo" queria dizer "ninguém vai fazer".

O reparo fechou os dois chips (`ScheduleStateChip`, `SsoStateChip`) e **o
segundo saiu da varredura da própria sessão de reparo**: o SSO carregava o mesmo
`HEALTHY` e nunca reprovava porque o fixture tem provedor inativo. A prova de
que o defeito era real é um teste unitário que renderiza o estado ativo —
`expected "healthyActive. People sign in through…" not to match /healthy/i`.

**O que a segunda passada derrubou**: a alegação de que
`console/src/surfaces/screens/detectors.tsx:184` seria código morto. É roteado
por `/signals?tab=observation`, o produto linka para lá de um empty-state, e os
catorze detectores do fixture estão `enabled: true` — a tela imprime `healthy`
em toda linha, hoje. O grep que sustentava o "não roteado" dava falso negativo
porque o import é relativo. Corrigido na seção 24 do `controle.md`; **não
reprova a feature** porque `/signals` não é uma das nove páginas, mas é defeito
vivo sem dono.

**Três defeitos desta feature eram invisíveis pela mesma razão**: o dado nunca
chegava no ramo. O painel de sessões esteve sempre vazio em todo teste e2e
desta árvore (nome do token de sessão no fixture); doze permissões nunca
puderam ser exercitadas por nenhum teste e2e do repositório (o `owner` do
fixture tinha quinze permissões curadas à mão em vez das trinta e uma do
catálogo); o `HEALTHY` do SSO era inalcançável. Um teste que passa porque o
fixture não exercita o caminho é indistinguível de um teste que passa porque o
código está certo.

**Quatro testes committed afirmavam defeitos como comportamento correto** e
foram reescritos — um deles protegia explicitamente o default de vinte e sete
escopos pré-marcados que esta feature existe para eliminar.

**Riscos que sobraram**: o defeito vivo de `/signals?tab=observation`, sem dono;
`console/src/surfaces/tokens.tsx:169` e `screens/agent.tsx:483,1026` achados por
grep e não rastreados até o fim; `make test-postgres` não rodado, com duas
migrações novas (`0012_token_unscoped`, `0013_local_password`) exercitadas só
contra o fake; e a asserção invertida de `settings-org.spec.ts`, correta hoje
mas sem registro de um vermelho isolado da própria linha.

---

## Cinco buracos de instrumento, todos da mesma forma

Custaram nove ciclos de reparo na 020 e valem para toda feature seguinte: **a
ferramenta usada para conferir o trabalho não enxergava o que estava errado.**

1. `npx vitest run --pool=forks` não aplica os thresholds de cobertura que o
   gate aplica com `vitest run --coverage`.
2. `innerText()` do Playwright devolve `''` para qualquer coisa dentro de um
   `<details>` fechado — asserção sobre tabela de configuração precisa abrir as
   seções recolhidas primeiro, ou reporta vermelho falso.
3. `verify` sequencia `test` **depois** de `console-check`: uma falha de console
   mascara a suíte Python inteira. Onze falhas de contrato de fixture ficaram
   invisíveis por três ciclos.
4. Asserção mais estreita que a alegação que ela codifica — a forma exata dos
   dois achados P1.
5. Rodar só o projeto `behaviour` do Playwright. `first-day` e `visual` também
   estão no gate; uma feature que mexe no fluxo de primeiro dia toca o segundo
   por definição.

## Duas regras de fixture que a onda aprendeu caro

- `fixtures/scenarios/` é **gerado** por `tools/mockplane/dataset/build.py`, a
  única rota, guardada por um teste de rebuild byte a byte, um de coerência
  entre cenários e um de contrato contra o documento da API. Nunca editar uma
  fixture à mão: `degraded`, `restricted`, `incident-live` e `scale` derivam de
  `populated`, então uma edição manual reprova cinco cenários. Um cenário pode
  ser parcial — `restricted` e `incident-live` têm um arquivo cada.
- O projeto `behaviour` do Playwright serve **um** cenário por execução. Um
  spec em `tests/e2e/` não escolhe o próprio: ele se protege e pula com motivo
  nomeado quando o dataset servido não é o que ele precisa.

## Conflito de convenção, aberto

`CLAUDE.md` proíbe citar número de feature em arquivo committed; o skill do
spec-wave manda nomear a acceptance spec como
`console/tests/e2e/<feature-slug>.acceptance.spec.ts`. A 010 já commitou
`010-provider-out-of-the-box.acceptance.spec.ts` e a 020 seguiu o precedente.
As duas regras não podem valer ao mesmo tempo — decidir antes da 030 criar a
terceira ocorrência.
