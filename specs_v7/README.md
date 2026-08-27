# specs_v7 — O produto conta o que fez, e o incidente fecha o laço

Onda proposta em 2026-08-23 a partir do diagnóstico do staging k3s
(`stg-ninjasre.lan.kyo.ninja`, Full HD) somado à leitura de código e do
`backlog.md`. Diagnóstico completo, com cada defeito cravado em `file:line` ou
no banco: [DIAGNOSTICO.md](DIAGNOSTICO.md).

Estado: **material de partida** — specs por feature ainda não geradas. Este
README fixa as decisões e o recorte; a geração (spec/plan/tasks por feature,
na forma da casa) é o próximo passo, com os mockups normativos onde a feature
é de console.

As próprias regras que governam as ondas foram auditadas a pedido do operador
— drift de governança, regras violadas vs regras defasadas, e o buraco que
deixou "tudo escrito, nada composto" passar cinco vezes: [REGRAS.md](REGRAS.md).

## As decisões que governam a onda

1. **O relato é dois fatos, não um.** Toda investigação produz um **headline**
   (uma sentença, apta a ser título, coluna e push notification) e um
   **report** (documento markdown, renderizado como leitura). `summary` hoje
   carrega os dois misturados e o console assume que é o primeiro. O contrato
   (`InvestigationSummary`) muda, o prompt de entrega pede a sentença, e
   nenhuma tela volta a imprimir `###` cru.
2. **Se rodou, está registrado.** Uma investigação que fez N tool calls mostra
   N tool calls, com o que cada uma devolveu, o custo por turno e os recursos
   tocados — lido do store depois de reload, não do processo que a rodou. As
   tabelas `run_turns`/`tool_calls`/`evidence` deixam de ser decorativas: o
   recorder é composto no caminho de produção e o DoD é a contagem no banco
   batendo com a contagem na tela.
3. **Uma fonte por fato.** Verified/Stored, gating de setup, chips de
   investigação, contagens — cada fato tem um dono e toda tela que o cita lê
   do dono. Nenhuma tela afirma o negativo ("No investigation") quando o que
   houve foi uma leitura falhada.
4. **Identidade endereçável.** Incidente tem id opaco e curto na URL; run tem
   headline como nome; `/investigations` e `/setup` respondem (redirect); o
   que a interface chama pelo nome, a rota atende pelo nome.
5. **Agir continua fail-closed, mas passa a existir.** Os gates que já estão
   escritos são compostos em propose-only: proposta com rollback → aprovação
   humana → execução registrada. Quem não ligou autonomia vê a proposta parar
   por política declarada, não por composição ausente.
6. **Mockup vira teste antes da tela** (herdado da v6, continua normativo):
   feature de console embarca `console/tests/e2e/<slug>.acceptance.spec.ts`
   confirmado vermelho antes da implementação; a suíte transversal roda em
   toda fronteira de feature e ganha os bans novos desta onda (markdown cru,
   placeholder duplo em telas de "Now", id hex como título).
7. **A onda zera o backlog.** Todo item de `backlog.md` ou é escopo de uma
   feature desta onda (nomeada na tabela abaixo), ou é tarefa operacional com
   dono e evidência (checklist ao fim deste README). Nada fica "fora" sem um
   destes dois destinos. DoD da onda inclui: `backlog.md` reescrito contendo
   apenas o que a própria onda descobriu de novo.

## Índice proposto e ordem de execução

| Feature | Domínio | Depende de |
|---|---|---|
| 000-regras-e-governanca | Emenda 2.1.0 pendente escrita de fato + emenda "composed or it is not shipped" (2.2.0, ADR próprio); status/índice dos ADRs corrigidos (0009→Superseded, 0012–0015 na tabela); CLAUDE.md atualizado; suíte transversal estendida com os bans novos (REGRAS.md §3–§4) | — |
| 001-registro-do-que-o-agente-fez | Compor o recorder no caminho de produção: turns, tool_calls, evidence, custo por turno; headline/report no contrato e no prompt de entrega; vínculos (recursos/incidente) gravados | — |
| 010-leitura-do-relato | Console lê o registro: markdown renderizado (sanitizado), título/aba/coluna = headline, transcript e custo reais, "What this investigation touched" vivo, controles só em run vivo, meta-linhas sem placeholder duplo | 001 |
| 020-identidade-enderecavel | Id opaco de incidente nas URLs (+ decode único na borda, fix da dupla codificação `api.ts:66`), título do incidente = `incident.title`, redirects `/investigations`→`/runs` e `/setup`→`/first-run`, listas com sujeito nomeado | — |
| 030-uma-fonte-por-fato | Verified/Stored do provider numa fonte só (vault), causa de vazio dos Decisions/Knowledge dizendo a verdade, chips do incidente derivados de leitura bem-sucedida (senão "estado desconhecido"), listas dinâmicas (fim do Full Route Cache congelado) — com teste que prova que a lista bate no gateway | — |
| 040-decisao-composta | `RemediationGate`/`AutonomyGate` construídos na composition root; interações pendentes com onde aparecer; Decisions vivo; ferramentas filtradas pelas integrações configuradas (`TeamCatalogueResolver`/`ResolveIntegrationsStage` com caller de produção) | 001 |
| 050-primeiro-administrador | Um deployment novo produz seu próprio primeiro admin sem ler código-fonte: decidir entre first-run screen × token de boot trocável × `ninjasre setup admin` (o backlog já analisou os três), com a janela fechando de vez e sem segunda porta onde há identity provider; unificar o seam "credencial trocada vale no sign-in"; corrigir o `UniqueViolation` do e-mail vazio para o segundo service account | — |
| 060-o-catalogo-ensina | Todo campo de credencial com `min_scope` e `guide_url` (28/40 e 29/40 hoje vazios); `IntegrationPanel` passa `whereToGetIt` como o first-run já faz; o `docs.md` de cada pacote servido por rota; a refusal de credencial em HTTP claro diz o que fazer (usar TLS ou não guardar credencial) | — |
| 070-confianca-de-certificado | `CertificateTrust` (fingerprint pinado, PEM, `unverified` registrado) carregado da configuração até o egress do credential proxy — desenhado como mudança de fronteira de segurança: quem aceita, por vendor ou por endereço, o que a auditoria grava; erro nomeia o certificado, nunca "no node answered" | — |
| 080-incidente-fecha-o-laco | Cenário ponta-a-ponta no staging real: alerta do Alertmanager → investigação com transcript gravado → root cause legível → ação proposta com rollback → aprovação em propose-only → timeline e episódio registrados; o Proxmox conectado de verdade (via 070) povoando o estate | 001, 010, 020, 030, 040, 070 |

Execução em **pares paralelos com validação em staging** — o protocolo
completo (slots S0–S5, propriedade dos arquivos de escrita única, mecânica de
worktrees, ciclo `make deploy-stg` → acceptance contra
`stg-ninjasre.lan.kyo.ninja` → evidência) está em [EXECUCAO.md](EXECUCAO.md),
que é também o opt-in que a skill `spec-wave` exige para paralelizar:

```
S0: 000 → S1: 001 ∥ 020 → S2: 010 ∥ 040 → S3: 030 ∥ 070 → S4: 050 ∥ 060 → S5: 080
```

A 000 ganha uma tarefa a mais por causa disso: `tools/spec_validation browser
--backing staging` (aponta os acceptance specs para a URL real com credencial
de operador vinda do ambiente, sem subir nada).

**Decisão de audiência (registrada em EXECUCAO.md §5):** o produto é para
outros; a primeira validação de eficácia é na infra atual — o que mantém 050 e
060 na onda com prioridade plena e faz dos serviços reais do cluster o corpus
de validação das investigações.

## Backlog → destino (a onda zera o backlog)

Cada item de `backlog.md`, com seu destino nesta onda:

| Item do backlog | Destino |
|---|---|
| A deployment should produce its own first administrator | **050** |
| The screen has room the packages have not filled (guias de credencial) | **060** |
| Four seams between configured and running | **040** (narrowing, resolver, pipeline) + **030** (chave env vs vault) |
| A vendor with a self-signed certificate cannot be connected | **070** |
| The alert router had no way to reach this deployment, twice over | fixado no que era produto; o resto é **ops-1** (resolver DNS morto nos containers de monitoração) |
| Two seams the deep verify opened | **030** (credencial de time vs binding org-wide resolvem igual) + **060** (mensagem da refusal em HTTP claro) |
| A deployment cannot hold two service accounts | **050** |
| An investigation that ran leaves the run detail empty | **001** |
| The half of the product that acts is not composed | **040** |
| The Infisical operator in the cluster cannot authenticate | **ops-2** (não é defeito deste produto; corrigir o KUBERNETES_AUTH do operator ou documentar o bypass) |
| The model gateway needs a key that exists nowhere | **ops-3** (emitir a chave no console do gateway e guardar no vault; staging já roda com Gemini) |

**Checklist operacional (dono: operador/infra, evidência exigida no confronto
da onda):**

- **ops-1** — apontar os três containers de monitoração para um resolver vivo;
  evidência: `.lan.kyo.ninja` resolvendo de dentro de cada um.
- **ops-2** — Infisical operator autenticando de novo (ou decisão registrada
  de conviver com o secret manual); evidência: `InfisicalSecret` sincronizando.
- **ops-3** — chave do gateway de modelos emitida e no vault; evidência:
  provider Ollama Verified no console.

**Fora da onda de verdade (único item):** o deployment `console` legado no
chart — remoção é um commit no repo GitOps; entra como tarefa da 000 se
sobrar folga, senão fica anotado no próprio chart.

## Evidências de partida (verificadas em 2026-08-23)

- Banco staging: `tool_calls=0`, `run_turns=0`, `evidence=0`,
  `trace_events=73` com 37 runs completed; todo `agent_runs.summary` recente
  começa com `###`.
- `readFailure` (`console/src/surfaces/failures.ts:154`) devolve o documento
  inteiro como título; sem renderizador de markdown no `console/package.json`.
- Ids de incidente no banco: `alert:alertmanager:<sha256>@<ISO+00:00>`;
  `params.incidentId` chega percent-encoded e `bind()` re-encoda
  (`console/src/lib/api.ts:66-76`).
- `/incidents` renderizou sem requisição no access log do `app` (cache RSC).
- Gemini Verified via vault/proxy; Alertmanager entregando alertas reais
  (RestoreDrillStale, CronJobStale, InstanceDown…) — matéria-prima da 080.
