# Implementation Plan: Provider out-of-the-box

**Branch**: `feat/v6-010-provider-out-of-the-box` | **Date**: 2026-08-16 |
**Spec**: [spec.md](spec.md)

**Input**: Feature specification from
`specs_v6/010-provider-out-of-the-box/spec.md`

**Referência visual (DoD)**: `specs_v6/mockups/settings-v6.html#m1` e `#m5`

## Summary

Três mudanças que se sustentam mutuamente e uma tela que passa a dizer a
verdade.

1. **Uma porta de listagem de modelos** em `core/llm/`, com uma implementação
   por provider, chamada no gateway com a credencial do vault pelo credential
   proxy. Curada para modelos de texto generativos, cacheada por deployment com
   TTL nomeado, recarregável sob demanda, com fallback declarado para a lista
   estática do onboarding quando o endpoint não responde.
2. **O probe passa a obrigar a chamada de ferramenta.** Obrigação declarada no
   pedido (não no adaptador), mapeada por wire — `functionCallingConfig.mode:
   "ANY"` no Gemini, o `tool_choice` equivalente nos demais. Sob obrigação,
   responder em texto é `failed`; `supports_tools=false` no descriptor continua
   `degraded` e não gasta chamada.
3. **O veredito de verificação passa a carregar os checks.** A rota de
   verificação devolve nome, status, detalhe e duração por check, em vez de um
   booleano. O console para de traduzir: renderiza os três status do preflight
   com o vocabulário único, e ganha `Degraded` como quinta palavra canônica.

Com isso, `#m1` e `#m5` deixam de ser desenhos: o card de estado, o erro em
hierarquia, a latência por linha e o `Continue` liberado por degradado passam a
ter dado por trás.

## Technical Context

**Language/Version**: Python 3.12 (core/gateway); TypeScript (console, Next.js)

**Primary Dependencies**:
- `core/llm/preflight.py` (`_tool_call_check`, `CheckResult`, `PreflightReport`)
- `core/llm/verification.py` (`contract_verdict`, `verify_model` — já tem o
  parâmetro `list_models`, hoje sem chamador; é ele que produz o texto falso
  "could not be asked what else it serves")
- `core/llm/providers/` (`gemini.py` e os demais adaptadores; `build_payload`)
- `core/llm/onboarding/` (`ProviderOnboarding.models` — vira fallback)
- `core/llm/registry.py` (preço, janela, `supports_tools`)
- `platform/credentials/proxy/` (egresso autenticado), `platform/credentials/vault.py`
- `gateway/http/routes/providers.py` (as três rotas de provider)
- `console/src/surfaces/settings/models.tsx` + `models-editor.tsx`
- `console/src/surfaces/first-run/verify.tsx`, `plan.ts`
- `console/src/components/status.tsx` (as cinco palavras), `console/src/i18n/*`
- `tools/mockplane/endpoints.py` (o plano de mock que a suíte de browser usa)

**Storage**: N/A de esquema novo. O cache da lista é em processo, no gateway,
com TTL; o registro de verificações continua no ledger existente
(`VerificationRecord`), que já guarda `model_id`.

**Testing**: pytest (unit + contract), vitest (console unit), Playwright
`behaviour` (`console/tests/e2e/`), Playwright `visual`

**Target Platform**: gateway self-hosted + console web

**Project Type**: Web (backend Python + frontend TypeScript)

**Performance Goals**: uma chamada de listagem por provider por TTL; a tela não
espera a listagem além do limite declarado.

**Constraints**: a credencial não sai do gateway; a forçagem de tool call vale
só no probe; o vocabulário de estado é fechado em cinco palavras; o passo Verify
não introduz uma segunda contagem de passos (fronteira da 020).

**Scale/Scope**: 1 porta nova + 1 implementação (google_gemini) + 8 adaptadores
tocados no ponto da forçagem; 1 rota nova + 1 rota estendida; 2 telas.

## Constitution Check

*GATE: passa antes do design e é reconferido depois.*

- **Art. I — Evidence Over Assertion**: a mudança central é justamente esta. A
  tela deixa de afirmar ("Failing") e passa a mostrar o que cada check encontrou,
  com o detalhe que o probe escreveu e a duração que ele mediu. O texto que
  afirma que o endpoint "não pôde ser perguntado" morre porque passa a ser
  falso: ele é perguntado.
- **Art. II — Bounded Autonomy**: TTL do cache, limite de espera da listagem e
  teto de entradas do cache são constantes nomeadas em `config/constants/llm.py`,
  não literais no ponto de uso (cláusula 6). Nenhum laço novo.
- **Art. III — Read-Only by Default**: nada aqui escreve em produção. A
  listagem é leitura; a verificação é uma chamada ao endpoint do próprio
  operador, disparada por gesto dele.
- **Art. IV — Secrets Never Reach the Agent**: a listagem roda no gateway, lê a
  credencial pelo vault e sai pelo credential proxy — o mesmo caminho de
  qualquer integração. Nenhum tipo servido ao browser tem campo em que a chave
  caiba, e o guard `check-credentials` cobre o caminho. Os logs da listagem
  passam pelo mesmo tratamento de redação já existente em `core/llm/redaction.py`.
- **Art. V — One Canonical Runtime**: não toca runtime. O probe é o mesmo para
  qualquer runtime, porque é do provider, não do laço.
- **Art. VI — Provider Neutrality**: **o artigo que governa o desenho**. A
  listagem é uma porta com implementação por provider, e a *ausência* de
  listagem é declarada pelo provider — não um `if` por vendor na superfície
  (cláusula 3: degradar explicitamente e reportar a degradação). A forçagem de
  tool call entra na suíte de contrato que todo adaptador passa (cláusula 2), e
  um deployment só com modelo local continua funcional: ele cai no fallback
  estático rotulado, que é um caminho de primeira classe e não um erro.
- **Art. VII — Learning Is Measured**: nenhum mecanismo de aprendizado é
  alterado.
- **Art. VIII — Layered Architecture**: a porta e a curadoria vivem em
  `core/llm/` (tier 3), que é dono do domínio de modelos; o gateway (tier 1) só
  a chama; `integrations/` não é tocado. `import-linter` roda em `make verify`.
- **Art. IX — Capabilities Are Declared**: um provider de modelo não é uma
  integração do catálogo — não embarca pacote de vendor — e por isso a regra dos
  sete artefatos de paridade (cláusula 5) não se aplica a ele. Nenhuma
  capability é adicionada ou alterada.
- **Art. X — Operator Owns Their Data**: a única chamada externa nova é ao
  endpoint que o próprio operador configurou, com a chave dele, para responder
  quais modelos ele pode usar. Nenhuma telemetria, nenhum phone-home.
- **Art. XI — Single Datastore**: nada de SQL novo. O cache é em processo; o
  histórico de verificação continua pelo port de ledger existente.
- **Art. XII — Test-First, Trace-Backed**: o `tasks.md` abre a fase de console
  com o acceptance spec das alegações de `#m1`/`#m5`, confirmado vermelho antes
  da tela; os testes de backend (curadoria, forçagem, mapeamento de status)
  também precedem a implementação. A rota nova e a rota estendida ganham teste
  de contrato (cláusula 4: o console contra a API que consome é uma dessas
  superfícies). O efeito na suíte sintética é reportado — a expectativa é
  "nenhum", porque isto muda a verificação de setup e não o laço de
  investigação, e "nenhum" medido é resultado aceitável; "não medido" não é.
- **Art. XIII — Language and Attribution**: código, testes e strings de produto
  em inglês (en + pt-BR juntos no i18n). Nenhum arquivo committed passa a
  depender de um não-committed: nenhuma tarefa escreve identificador de
  requisito, número de feature ou caminho de planejamento em código, teste ou
  documento committed — a substância vai no arquivo, a referência fica aqui.

**Veredito**: sem violações. Nada a registrar em Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs_v6/010-provider-out-of-the-box/
├── spec.md
├── plan.md              # este arquivo
├── tasks.md
├── controle.md          # escrito durante a execução, não na geração
└── checklists/requirements.md
```

### Source Code (repository root)

```text
core/llm/catalogue/__init__.py          # novo: a porta de listagem + a curadoria
core/llm/catalogue/gemini.py            # novo: a implementação google_gemini
core/llm/catalogue/cache.py             # novo: cache por deployment/provider com TTL
core/llm/preflight.py                   # _tool_call_check obriga a chamada
core/llm/types.py                       # a obrigação como propriedade do pedido
core/llm/providers/gemini.py            # mapeia a obrigação para mode "ANY"
core/llm/providers/{anthropic,openai_compat,bedrock,azure_openai}.py  # equivalentes
core/llm/verification.py                # list_models ligado; o texto falso sai
config/constants/llm.py                 # TTL, limite de espera, teto do cache
gateway/http/routes/providers.py        # GET .../models; verify devolve os checks

tests/unit/core/llm/                    # curadoria, forçagem, mapeamento, cache
tests/contract/llm/                     # a forçagem na suíte que todo adaptador passa
tests/contract/console/                 # o contrato das rotas que o console consome
tests/security/                         # a chave não aparece em payload nem em log

tools/mockplane/endpoints.py            # o endpoint de listagem no plano de mock
tools/mockplane/dataset/                # a fixture dos 37 nomes reais
fixtures/contract/openapi.json          # documento regenerado
console/src/api/schema.ts               # cliente regenerado a partir dele

console/src/components/status.tsx       # Degraded como quinta palavra canônica
console/src/i18n/{en,pt-BR}.ts          # as strings novas, sempre em par
console/src/surfaces/settings/models.tsx
console/src/surfaces/settings/models-editor.tsx
console/src/surfaces/first-run/verify.tsx
console/visual/screens.json             # se a tela registrada mudar de forma

console/tests/e2e/010-provider-out-of-the-box.acceptance.spec.ts   # novo
console/tests/unit/surfaces/settings/models.test.tsx
console/tests/unit/surfaces/first-run.test.tsx
```

**Structure Decision**: mantém a divisão de tiers vigente. O domínio de modelos
(listar, curar, cachear) é de `core/llm/`; o gateway serve e autoriza; o console
renderiza sem recalcular. A curadoria mora ao lado da porta e não na rota,
porque a mesma curadoria serve o CLI de primeira execução e a rota — e uma cópia
na segunda superfície seria a que envelhece.

## Decisões de design

- **A obrigação de chamar a ferramenta é do pedido, não do adaptador.** Se
  `gemini.py` passasse a mandar `"ANY"` sempre, toda invocação do produto
  perderia o direito de responder em texto. A propriedade entra em
  `InvokeRequest` e cada adaptador a traduz para o seu wire; o probe é o único
  chamador que a liga. É também o que a torna testável por captura de request em
  vez de por chamada real.

- **`failed` sob obrigação, `degraded` por declaração.** São dois fatos
  diferentes e continuam separados: um modelo que, obrigado, não chamou a
  ferramenta, não serve — isso é uma falha. Um modelo cujo descriptor diz não
  suportar ferramentas é um vazio de catálogo deste build, não um veredito sobre
  o modelo; segue `degraded`, e nenhuma chamada é gasta para descobrir isso.

- **`list_models` já existe e nunca teve chamador.** `verify_model` aceita o
  parâmetro desde sempre; o gateway o omite, e é por isso que `_model_remedy`
  cai no ramo que afirma que o endpoint não pôde ser perguntado. Ligar a porta
  nova nesse parâmetro mata o texto falso e enche `alternatives` — o trabalho é
  ligar, não inventar.

- **A rota de verificação passa a devolver os checks.** Hoje ela devolve
  `verified: bool` e o console só pode traduzir para dois estados. Devolver
  nome/status/detalhe/duração por check é o que permite espelhar em vez de
  traduzir, e é também o que dá a latência que `#m5` mostra por linha.

- **Listar é grátis, verificar não.** A separação que a rota de providers já
  documenta é mantida: a verificação continua sendo `POST` por gesto do
  operador, porque gasta tokens; a listagem acompanha a renderização, porque não
  gasta — e mesmo assim é cacheada, para que abrir a tela três vezes não vire
  três chamadas ao vendor.

- **O fallback é um estado, não um erro.** A lista estática do onboarding
  continua existindo e passa a ser rotulada quando é usada. Um provider local
  que não sabe listar chega nesse mesmo estado pelo caminho normal, sem ramo
  especial — o que é exigido por provider-neutralidade e não só elegante.

- **`Degraded` entra no componente de chip, não em cada tela.** As cinco
  palavras são declaradas num lugar só (`status.tsx` + os dois catálogos de
  i18n), e as telas passam a status em vez de escolher palavra. É o que impede
  a sexta palavra de nascer na próxima tela.

- **A contagem do setup não é mexida aqui.** `#m5` mostra "Step 5 of 7 · 2 steps
  left" porque a 020 vai calcular isso num lugar só. Esta feature muda o
  conteúdo do card do passo — chips, latências, rodapé de degradados, `Continue`
  — e deixa o cabeçalho como está, para não criar a segunda fonte que a 020
  existe para eliminar.

## Gates que esta feature toca

| Gate | Por quê |
|---|---|
| `make verify` | roda tudo abaixo; é o que a CI executa |
| `check-constants` | TTL, espera e teto do cache como constantes nomeadas |
| `check-credentials` | a listagem lê credencial — precisa passar pelo vault/proxy |
| `check-vendor-sdks` | a implementação de listagem fica em `core/llm/`, não fora |
| `check-imports` | a porta em tier 3, o consumo em tier 1 |
| `check-display-names` | os modelos listados ganham nome de exibição |
| `console-client-check` | o cliente do console é regenerado do OpenAPI atualizado |
| `console-test` / `console-e2e` | unit e behaviour, incluindo o acceptance spec |
| `console-visual` | baseline das telas registradas, recapturada deliberadamente |
| contract (`tests/contract/llm`, `tests/contract/console`) | adaptadores e rotas |
| suíte transversal (`console/tests/e2e/transversal-rules.spec.ts`) | nasce na 020; a partir dela roda em toda fronteira — aqui ainda não existe |

## Complexity Tracking

Sem violações constitucionais. Nada a justificar.
