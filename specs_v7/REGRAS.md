# specs_v7 — Auditoria das regras que governam as ondas

Feita em 2026-08-23, a pedido do operador: "estamos desenvolvendo specs em cima
de regras que talvez estejam defasadas". Corpus auditado: a constituição
(`.specify/memory/constitution.md`, 13 artigos, local), os ADRs 0001–0015, o
`AGENTS.md` raiz, as regras transversais de UI herdadas da v5/v6
(`console/tests/e2e/transversal-rules.spec.ts` + mockups normativos), as
decisões de onda do `specs_v6/README.md`, e o `CLAUDE.md` local.

Veredito curto: **o corpo de regras está saudável no conteúdo e defasado na
manutenção** — e tem um buraco: nenhuma regra pega a forma de falha que mais se
repetiu nas últimas ondas ("tudo escrito, nada composto").

---

## 1. Drift de governança (fatos verificados, corrigir é barato)

| Fato | Onde | Ação |
|---|---|---|
| Constituição está em **2.0.0** (last amended 2026-08-04) enquanto `CLAUDE.md` afirma **2.1.0** (Artigos V, IX, XI, XII emendados pelo ADR 0015) | `constitution.md:3-5` vs `CLAUDE.md` "Repository state" | Escrever a emenda 2.1.0 de fato no arquivo — ou corrigir o CLAUDE.md se a decisão nunca foi ratificada. Hoje o Constitution Check das specs roda contra um texto que uma das duas fontes diz estar errado |
| ADR 0009 segue **Status: Accepted** apesar de o ADR 0015 declarar **Supersedes: 0009** | `0009-full-integration-parity.md:3` vs `0015:4` | Status do 0009 → "Superseded by 0015". O próprio `docs/adr/README.md` define que reversão é um ADR novo que *supersede* — o status é a metade que faltou |
| Índice de ADRs lista só **0001–0011**; 0012, 0013, 0014 e 0015 existem sem linha | `docs/adr/README.md:6-18` | Completar a tabela; a regra 4 do próprio índice também exige a linha na traceability de `docs/roadmap.md` |

**Mecanismo do drift, cravado no histórico (2026-08-23):** a metade committed
dessa governança **foi escrita** — `6d1ede6` ("ship only the integrations an
environment can validate", 2026-08-17) pôs o 0009 em "Superseded by 0015",
acrescentou as linhas do índice e a seção "Integration scope" do roadmap — e
**foi revertida por `19431fc`** ("standardize delivery descriptor…"), que
sobrescreveu exatamente esses hunks em arquivos que não eram do seu assunto.
Consequência dupla: (1) a 000 recupera esse conteúdo de `6d1ede6` em vez de
reescrevê-lo; (2) é o caso concreto que justifica a regra de merge do
EXECUCAO.md — um commit largo que carrega estado velho de arquivos alheios
desfaz governança sem ninguém decidir.
| `CLAUDE.md` "Repository state" descreve o estado da fundação (pré-ondas) | `CLAUDE.md` | Atualizar — sessões novas são orientadas por fatos velhos |

## 2. Regras certas que o produto viola hoje — não mudar a regra, compor o comportamento

- **Artigo I.2** — "a tool result that never entered the trace did not happen".
  Staging: `tool_calls=0`, `run_turns=0`, `evidence=0` com 37 investigações
  completed. A regra está correta e é exatamente o que a feature 001 implementa.
  O que falta é *enforcement*: nada em `make verify` prova que o **caminho de
  serving** grava — os testes provam as peças. Proposta: o gate da 001/050
  afirma contagens no store depois de uma investigação real (compose ou
  staging), não só no harness.
- **Artigo III** — aprovação por ação + rollback gravado. As peças existem e
  estão medidas: 80 capacidades, 44 `read` + 12 `read_sensitive`, 24 que
  escrevem (15 reversíveis, 6 irreversíveis, 3 destrutivas), 24 declarando
  `requires_approval` com razão e rollback ao lado; `RemediationGate`
  (`platform/remediation/gating.py:187`) e `AutonomyGate`
  (`platform/autonomy/decision.py:168`) escritos; rotas de aprovação
  permissionadas. **Nenhuma composition root constrói os dois gates** — só
  testes, contract tests e o mock data plane. A regra está certa; o
  comportamento é inexistente. Feature 040.

## 3. O buraco: nenhuma regra pega "escrito mas não composto"

A forma se repetiu, com o mesmo desfecho, em cinco lugares independentes:
o deep verifier (antes de ser composto), o recorder de investigação (defeito 3
da v7), `RemediationGate`/`AutonomyGate` (defeito 4), `build_pipeline`/
`ResolveIntegrationsStage` (sem caller de produção), `TeamCatalogueResolver`
(nunca instanciado). Em todos: Constitution Check aprovou o plano, testes
verdes provaram as peças, `make verify` passou — e o fio nunca foi ligado.
Fail-closed segurou o risco; nada segurou a mentira de completude.

**Proposta de emenda** (MINOR, com ADR próprio — "Composed or it is not
shipped", provavelmente cláusulas novas no Artigo XII ou um Artigo XIV):

1. Todo mecanismo mergeado é **alcançável a partir de uma composition root de
   serving**, ou o próprio módulo declara `dormant` com a referência do que o
   liga. Um símbolo construído apenas por testes não é uma entrega.
2. O DoD de toda feature inclui **evidência do caminho de serving** (deploy
   real ou compose de produção) para o comportamento novo — o harness prova a
   peça, nunca a composição.
3. O confronto de fim de onda (CONFRONTO.md) ganha uma coluna fixa: "quem
   constrói isso em produção?", respondida com `file:line` da composition root.

## 4. Regras que merecem alteração

- **Artigo XIII.1 / ADR 0010 (English-only, inclusive user-facing text).**
  Contradição instalada: o console carrega maquinaria de i18n completa
  (`requestLocale`, `Locale`, catálogo de mensagens), a operação real recebe
  alertas anotados em pt-BR, e o operador é brasileiro. Ou (a) mantém
  English-only e remove a maquinaria morta, ou (b) emenda: código, comentários,
  commits, docs e prompts em inglês; **texto de UI localizável via catálogo**.
  Recomendação: (b) — a UI já é bilíngue à revelia, só que por acidente.
  MINOR + ADR.
- **Regras transversais de UI: escopo e bans.** O corpus v5/v6 é normativo
  para Settings; as telas de "Now" (runs, incidents, dashboard) violam o
  espírito sem violar a letra. Estender a suíte com os bans que esta rodada
  encontrou: markdown cru impresso como texto; id hex como título/nome;
  placeholder atrás de placeholder na mesma linha-meta; controle de run vivo
  em run terminado; estado afirmado no negativo ("No investigation") quando a
  leitura falhou.
- **Viewport normativo.** Playwright global é 1440×900; o padrão operacional
  declarado pelo operador é Full HD. A v6 já exigia que medições de orçamento
  declarassem 1080p explicitamente — formalizar: **1920×1080 é o viewport
  normativo de medição**, e o global do Playwright migra quando custar pouco.
- **"One canonical console" (espírito do Artigo V aplicado a superfícies).**
  Existem duas superfícies de console: `console/` (Next, servida como `web` no
  cluster) e `surfaces/console` (Python, renderiza HTML próprio com sign-in —
  `surfaces/console/pages/shell.py`), além de um deployment `console` legado
  de pé no k3s ao lado do `web`. O `AGENTS.md` chama `surfaces/` de "console
  backend-for-frontend", que não descreve o que o pacote faz hoje. Decidir o
  estatuto (canônica × experimental × morta) e aplicar o Artigo VIII.4
  (compat morre no mesmo change) ao que for legado — inclusive o deployment
  no chart.

## 5. Regras reafirmadas (auditar não é reescrever)

- **Fail-closed dos stubs de remediação** (`PERMISSION_DENIED` por padrão) — é
  a razão de a metade não composta ser *segura* em vez de perigosa. A 040
  compõe por cima; o default não relaxa.
- **Tiers + import contracts, credential proxy, single datastore, test-first,
  no-telemetry, capability metadata** — enforcement real, sem drift observado,
  sem razão para tocar.
- **ADR 0008 (paridade de providers)** — segue fazendo sentido: a lista de
  "supported" é curada, e o contrato único por provider é o que manteve o
  Gemini verificável pelo mesmo caminho dos demais.
- **ADR 0012/0013/0014 (fidelidade de design expira; paleta preserva
  vocabulário; referência de design comitada)** — corretos e em uso; só falta
  a linha no índice (§1).

## 6. Como isso entra na onda

Uma feature **000-regras-e-governanca**, curta e primeira: escreve a emenda
2.1.0 pendente + a emenda nova do §3 (vira 2.2.0), corrige status e índice dos
ADRs, atualiza o CLAUDE.md local, e estende a suíte transversal com os bans do
§4. Tudo o mais da onda passa a ser especificado contra regras que dizem a
verdade — que é o ponto do pedido do operador.
