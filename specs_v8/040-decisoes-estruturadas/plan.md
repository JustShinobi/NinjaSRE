# Implementation Plan: Decisões estruturadas — o cartão no lugar do JSON, e a expirada com saída

**Branch**: `feat/v8-040-decisoes-estruturadas` | **Date**: 2026-08-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v8/040-decisoes-estruturadas/spec.md`

**Referência visual (DoD)**: `design/padrao-2026-08/Decisions.dc.html` e
`design/padrao-2026-08/DecisionsLight.dc.html`, normativos (decisão 1 da
onda). Acceptance em
`console/tests/e2e/decisoes-estruturadas.acceptance.spec.ts`, vermelho antes.
Viewport normativo: 1440×1040.

## Summary

Um defeito de apresentação com três consequências — o documento da ação
impresso como texto, a expirada sem saída, o badge contando o inacionável — e
todos os dados já existem no payload (spec, fato 2). O trabalho:

1. **O contrato passa a servir a decisão por campo.** A listagem e o detalhe
   de aprovações ganham os campos que o cartão renderiza (título humano,
   risco com score/escala, passos, reversão, evidência, raio, autonomia,
   estados e instantes), mais o filtro de estado para as decididas. O
   documento integral continua num campo único para o payload bruto.
2. **A expirada ganha o endpoint de re-proposta**, servido pelo mesmo
   mecanismo que propôs a original (o gate composto pela onda anterior), com
   idempotência por origem e recusa nomeada quando a origem não existe mais.
   Descartar vira transição registrada, nunca deleção.
3. **A tela vira o cartão do artboard** — `ApprovalsTab`/`ProposalCard`
   reescritos na anatomia do board sobre a fundação da 000 — e o badge da
   sidebar passa a contar só pendentes dentro da janela.

O que **não** muda: o mecanismo de decidir (endpoints de interação
existentes), o propose-only, o Painel (da 050), o vivo por push (da 010), e
qualquer arquivo da fundação visual (congelada após o S0).

## Technical Context

**Language/Version**: Python 3.12 (gateway, platform de propostas/aprovações)
e TypeScript (console Next).

**Primary Dependencies**:
`gateway/http/routes/` (a rota que serve `/v1/approvals` — arquivo cravado na
partida, tarefa própria), `platform/proposals/service.py` (`ProposalQueue`,
`propose:167`, `pending:216`, `decided:224`), `platform/approvals/`
(modelos e store), a raiz de composição do gate de remediação que a onda
anterior compôs (cravada na partida),
`console/src/surfaces/screens/decisions.tsx`,
`console/src/surfaces/screens/approvals.tsx`,
`console/src/surfaces/screens/proposals.tsx`,
`console/src/surfaces/proposal.tsx`, `console/src/surfaces/decision.tsx`,
`console/src/shell/load.ts` (`countsFrom` — o badge),
`fixtures/contract/openapi.json` e `console/src/api/schema.ts` (regenerados).

**Storage**: PostgreSQL, o store de aprovações existente. Mudanças de
esquema: o estado `discarded` e o vínculo de origem da re-proposta
(`origin_approval_id` ou equivalente que o modelo já comporte) — migração
reversível se e somente se o modelo atual não os comportar; a decisão é
tomada na partida lendo `platform/approvals/models.py` e o store, e
registrada no controle. Nenhuma linha é apagada por nenhum caminho novo.

**Testing**: pytest — contrato da listagem/detalhe por campo, contrato da
re-proposta (criada, idempotente, recusa nomeada), unidade da derivação de
título e score; vitest — o cartão (pendente/expirada/decidida, campos
ausentes), o badge; Playwright — acceptance das 14 alegações, marcação
staging-safe conforme spec; suíte visual — decisões pendente e expirada nos
dois temas.

**Target Platform**: gateway + console no k3s de staging
(`stg-ninjasre.lan.kyo.ninja`), deploy pelo orquestrador no fim do S2
(`make deploy-stg COMPONENTS="app web"`).

**Project Type**: contrato + persistência mínima + console na mesma feature,
porque o cartão nasce no campo servido e morre no pixel comparado com o
artboard.

**Performance Goals**: a listagem por campo é a mesma leitura de hoje com
projeção maior; a derivação de título e score é pura e por linha; nenhuma
chamada nova por cartão renderizado.

**Constraints**: `make verify` verde partindo de verde; fundação visual
congelada (token/ícone novo → declarado no relatório, nunca editado aqui);
single-write do slot é da 060 (chaves i18n e `console/visual/screens.json`
declaradas no relatório final); nenhum arquivo de outra feature tocado;
nenhuma linha de aprovação apagada.

**Scale/Scope**: duas rotas estendidas + uma nova (re-proposta) + um filtro
de estado; uma derivação de título e uma de score; possivelmente uma migração
pequena; quatro arquivos de tela reescritos; um contador corrigido; dataset
simulado com três estados; ~14 alegações de acceptance.

## Constitution Check

*GATE: precisa passar antes da execução. Reconferir ao final.*

| Artigo | Como este plano satisfaz |
|---|---|
| I — Evidência sobre asserção | O cartão mostra a evidência **com fonte** (FR-010) e o veredito visual é contra artboard comitado, no staging real. A leitura falhada diz que falhou (FR-023) em vez de afirmar "nada proposto". |
| II — Autonomia limitada | Propose-only intacto. A re-proposta produz **proposta pendente**, nunca execução; decidir continua humano, pelos endpoints existentes. |
| III — Leitura por padrão | As escritas novas são três transições registradas — repropor, descartar, decidir (existente) — todas atrás de controle humano com permissão conferida. |
| IV — Segredo nunca chega ao agente | Não toca o proxy de credencial. O payload bruto já é servido hoje; nenhum campo novo expõe segredo (o documento observado não carrega credencial). |
| V — Um runtime canônico | Não toca runtime. |
| VI — Neutralidade de provedor | Não toca abstração de provedor. |
| VII — Aprendizado é medido | `prior_effectiveness` é **lido** e mostrado; nenhum mecanismo de aprendizado é alterado. |
| VIII — Arquitetura em camadas | Derivações de título/score vivem no lado servidor junto do modelo de aprovação; o console lê pelo cliente gerado; import-linter roda no fecho. |
| IX — Capacidades declaradas | Nenhuma capacidade nova. A re-proposta reusa a capacidade da proposta original pelo gate composto. |
| X — O operador é dono dos dados | Nada sai do host. Descartar e expirar marcam; a contagem de linhas da tabela não decresce (consulta no DoD). |
| XI — Datastore único | Acesso pelo store/porta existente; se houver migração, reversível e com downgrade exercitado por teste. |
| XII — Test-first, rastreado | Acceptance e contratos aterrissam vermelhos com mensagem registrada; comportamento de decidir existente é caracterizado antes (continua igual); efeito na suíte sintética medido e reportado ("sem efeito" esperado). |
| XIII — Idioma e atribuição | Código e commits em inglês; UI pelo catálogo `en`+`pt-BR` (chaves declaradas no relatório — dona do slot aplica); nenhum identificador de planejamento em arquivo committed. |
| XIV — Composto ou não foi entregue | Abaixo. |

### Qual composition root constrói isto

- **Leitura por campo**: não há objeto novo — é projeção nova na rota que já
  serve `/v1/approvals` (caminho literal cravado; arquivo Python localizado
  na primeira tarefa e registrado no controle com `file:line`), alimentada
  pelo store de aprovações existente. O fio de serving é o mesmo de hoje:
  console → cliente gerado → gateway → store.
- **Re-proposta**: o handler novo na mesma rota-família chama o mecanismo de
  proposta que a onda anterior compôs na raiz de serving
  (`RemediationGate`/fila de propostas — `platform/proposals/service.py:167`
  `propose()` é o ponto de entrada da fila; a raiz que constrói o gate é
  cravada na partida e registrada no controle). Nenhum mecanismo novo dormente:
  o botão do cartão é o caller de produção no dia do merge.
- **Badge**: `countsFrom` (`console/src/shell/load.ts`) passa a ler a
  contagem filtrada — mesmo fio de shell que já constrói a sidebar.
- **Prova exigida no DoD** (não é "teste verde no harness"): a expirada real
  do staging re-proposta pelo botão, a pendente nova visível e decidida, o
  badge acompanhando — mais as consultas da spec.

## Decisões de projeto (fechadas aqui, não no código)

1. **Shape do contrato.** `GET /v1/approvals?state=pending|decided&limit=N`
   e `GET /v1/approvals/{approval_id}` passam a servir, por decisão:
   `approval_id`, `state`, `title`, `requester`, `origin{run_id, headline,
   incident_id}`, `category`, `intent`, `risk{class, score, scale}`,
   `steps[]{ordinal, summary, capability}`,
   `rollback[]{ordinal, summary, capability}`,
   `evidence[]{summary, reference}`, `blast_radius{count, depth, known}`,
   `autonomy{side_effect_level, reversible, queued}`,
   `prior_effectiveness{summary}`, `created_at`, `expires_at`,
   `decided_at`, `decided_by`, `verdict`, `raw` (o documento integral).
   Ausência é declarada (`""`/`[]`/`known:false`), nunca chave omitida.
2. **Título humano.** Derivado no servidor: verbo da capacidade + alvo
   (ex.: `proxmox_start_guest` + `lxc/122@pve01` → "Religar o guest lxc/122
   em pve01" na língua do deployment, como o headline da v7); fallback: o
   campo `summary` do documento; nunca `capability` cru, nunca id.
3. **Score de risco.** Determinístico no servidor, escala 5:
   base por `side_effect_level` (leitura=1, escrita reversível=2, escrita
   irreversível=4, destrutiva=5), +1 se `blast_radius.count>1` ou
   `depth>2`, teto 5; `risk_class` servida ao lado. Consistente com o
   staging observado: escrita reversível com `depth:3` → 3, que é o "Risk 3
   of 5" que a tela atual mostra.
4. **Re-proposta.** `POST /v1/approvals/{approval_id}/repropose` → `201` com
   `{approval_id}` da nova; `409` com causa nomeada quando já existe pendente
   da mesma origem (devolve a existente no corpo — idempotência FR-017);
   `422` com causa nomeada quando a origem não resolve mais (plano/capacidade
   ausente). Só aceita `state=expired`; pendente não se re-propõe.
5. **Descartar.** `POST /v1/approvals/{approval_id}/discard` → transição para
   `discarded`, registrada com autor; aparece no histórico; nunca deleta.
6. **Badge.** A contagem servida ao shell passa a ser `pending ∧ não
   expirada`; a soma com a aba Changes permanece (uma proposta de mudança
   pendente continua contando).

## Estrutura da mudança

- **Fase servidor**: projeção por campo + derivações + `state=` + repropose +
  discard + (se preciso) migração; contratos pytest vermelhos primeiro.
- **Fase console**: `ApprovalsTab`/`ProposalCard`/`DecisionControls` na
  anatomia do artboard; histórico; badge; empty states; unit vitest vermelhos
  primeiro; acceptance Playwright vermelho desde a Fase 0.
- **Fase artefatos**: openapi + cliente TS regenerados; dataset simulado com
  os três estados; linha do registro visual declarada no relatório.
- **Fase fecho**: gates locais; no merge do slot, deploy-stg + acceptance
  @staging + gate visual Orca (EXECUCAO.md §3) com VEREDITO.md.

## Riscos e como o plano os corta

- **A rota-arquivo e a raiz do gate não estão cravadas nesta spec.** Primeira
  tarefa é cravá-las com codegraph e registrar `file:line` no controle —
  nenhuma edição antes disso.
- **Modelo de aprovação sem `discarded`/origem.** Decisão binária na partida:
  campo existente comporta → sem migração; não comporta → migração reversível
  pequena, downgrade testado.
- **`repropose` num ambiente onde a origem era um run efêmero.** A recusa
  nomeada (`422`) é comportamento correto e testado — o botão então diz o que
  faltou; o cartão nunca quebra.
- **Duas fontes para o mesmo título** (lista e detalhe). O título nasce numa
  função só, usada pelas duas projeções; teste de contrato compara os dois.
