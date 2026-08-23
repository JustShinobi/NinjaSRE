# specs_v7 — Diagnóstico: o que uma investigação mostra, e o incidente que não fecha

Análise feita em 2026-08-23 sobre o **staging real no k3s**
(`https://stg-ninjasre.lan.kyo.ninja`, namespace `k3s-stg-ninjasre`, ingress
`/ → web:http`, `/webhooks → app:http`), em 1920×1080, com o banco consultado
direto (`10.20.20.54`, `ninjasre-stg-db`). Toda afirmação abaixo foi vista na
tela, confirmada no banco, ou cravada em código com `file:line`. A investigação
de referência do operador: `/runs/3d794ff63b5c49c9b1067cf1b3f469f0`.

Contexto que distingue esta onda da v6: a v6 fechou o setup e o primeiro
incidente *tecnicamente* — webhook entra, investigação roda, modelo responde,
`make verify` passa. O que este diagnóstico encontra é a camada seguinte: **o
produto executa e não consegue contar o que fez.** O relato existe (o modelo
escreveu um root-cause completo), mas chega à tela como documento markdown cru
no lugar de um título; a mecânica existe (39 trace events), mas as tabelas que
a tela lê estão zeradas; a decisão existe (gates escritos, rotas permissionadas),
mas nada as compõe.

---

## 1. Estado por tela (staging, Full HD)

| Tela | Veredito |
|---|---|
| `/runs/{id}` (detalhe) | **Quebrada como leitura**: markdown cru (`###`, backticks, `**`) como H1 gigante, como título da aba e como corpo do painel; transcript "recorded no events"; custo "No cost recorded"; vínculos "Nothing linked yet"; badge "Paused in the background" num run completed; painel Control oferece "Stop this investigation" em run que terminou há 23 min |
| `/runs` (lista) | Coluna SUBJECT = o mesmo markdown truncado ("### Incident Findings & Root Cause A..."); coluna INVESTIGATION = hex truncado (`e19e882a`); linha com SUBJECT "Not recorded" e DURATION "Not recorded" |
| `/incidents` (lista) | Funcional na aparência — mas renderizou **sem nenhuma chamada chegar ao app** (cache RSC; ver defeito 6) |
| `/incidents/{id}` | **Quebrada**: H1 é o id URL-encoded (`alert%3Aalertmanager%3Ac046...%2B00%3A00`), dois painéis "This panel could not be filled", chip "No investigation" contradizendo o INVESTIGATING da lista, subtítulo "Not recorded · ... · zone Unplaced · Not recorded" |
| `/` (dashboard) | Coerente; "14 items need you" com padrão bom (severidade, causa, idade) |
| `/decisions` | Vazio com causa **falsa**: "3 step(s) are outstanding, and investigations cannot run until they are done" — 37 investigações rodaram |
| `/resources` | "No resources yet" + "Alerts for things not here" (padrão bom); estate não popula porque o Proxmox está Degraded (certificado — backlog) |
| `/knowledge` | Vazio com a mesma causa falsa dos Decisions |
| `/agent` | Boa: topologia dos estágios, abas Tools/Autonomy/Team context |
| `/integrations` | Boa pós-v6; Proxmox Degraded com a frase "Neither the credential proxy nor any configured Proxmox node answered" (a mensagem errada para um problema de certificado — backlog) |
| `/settings/*` | Members & roles e Models & providers OK (Gemini **Verified**, modelos dinâmicos — entrega da v6/handoff confirmada) |
| `/first-run` | Estrutura v6 de pé; mas "Connect a model provider — You are here" com o Gemini **Stored** aqui e **Verified** em Models & providers (ver defeito 5) |
| `/investigations`, `/setup` | **404** ("There is no such page") — ver defeito 7 |

## 2. Defeitos confirmados (por gravidade)

### P0 — o produto não conta o que fez

**1. O relato do agente chega cru: markdown como título, aba, subject e corpo.**
Cadeia completa, cravada:

- O runtime grava o documento markdown inteiro do modelo em
  `agent_runs.summary`. Banco de staging, literal:
  `completed | ### Incident Findings & Root Cause Analysis\n\n#### 1. Cause…` —
  todas as linhas recentes começam com `###`.
- O contrato não tem outro campo: `InvestigationSummary`
  (`gateway/http/routes/investigations.py:35-60`) carrega `summary: str | None`
  e nada mais — não existe "headline" separado de "report".
- O console assume que `summary` é uma sentença: `readFailure`
  (`console/src/surfaces/failures.ts:154`) devolve o texto inteiro como
  `title` quando não parece exceção; `run-detail.tsx:96,129` faz
  `title = said.title` e entrega ao `PageHeader` **e** ao `<title>` da aba
  (`console/src/app/(shell)/runs/[runId]/page.tsx:50`); o painel "What this
  investigation found" imprime a mesma string num `<p>`.
- A lista (`runs.tsx`) trunca a mesma string na coluna SUBJECT.
- **Não existe renderizador de markdown no console** — nenhuma dependência
  (`react-markdown`/`remark`/`marked` ausentes do `console/package.json`).

Direção de fix (é design, não patch): separar **headline** (uma sentença,
gerada — pedida ao modelo no prompt de entrega ou sintetizada do alerta) de
**report** (o documento, renderizado como markdown sanitizado num painel de
leitura). A lista mostra o *sujeito* (nome do alerta/recurso), nunca o relato.

**2. O detalhe de todo incidente ingerido por alerta está irrecuperável.**

- Os ids são compostos e cheios de reservados:
  `alert:alertmanager:<sha256>@2026-08-22T23:43:23.303208+00:00` (banco,
  literal).
- O Next entrega `params.incidentId` **ainda percent-encoded**; a página usa o
  valor cru como título e como parâmetro
  (`console/src/app/(shell)/incidents/[incidentId]/page.tsx:19,31-32`) — por
  isso o H1 mostra `alert%3A…%2B00%3A00`.
- `bind()` re-encoda na montagem da URL da API
  (`console/src/lib/api.ts:66-76` faz `encodeURIComponent(value)` sobre o valor
  já encodado) — dupla codificação; o id que chega ao gateway não é o do banco.
- Resultado observado: os dois painéis servidos por
  `/v1/incidents/{incident_id}` falham ("did not answer"), o RSC responde 503,
  e o fallback `title = text(incident,'title') || incidentId`
  (`incident-detail.tsx:166`) imprime o id encodado como título.
- Sondagem: a rota responde para o id cru e para o encodado (400 "needs a
  bearer token" de dentro do pod — roteamento OK); a leitura autenticada do
  console nunca chega ao app (nenhuma linha no access log do `app` durante os
  loads, só as sondas).

Direção de fix: id de incidente **opaco e curto** nas URLs (o composto pode
continuar sendo chave interna), decode único e explícito na borda, título do
incidente vindo de `incident.title` (a lista já o tem: "RestoreDrillStale").

**3. Toda investigação termina com transcript, custo e vínculos zerados.**
O item do backlog ("An investigation that ran leaves the run detail empty")
continua literalmente atual no staging:

```
tool_calls | run_turns | evidence | trace_events
         0 |         0 |        0 |           73   (≈2 por run: started/finished)
```

Na tela: "1 event" / "This investigation recorded no events", "No cost
recorded … has taken no turns yet", "Nothing linked yet". A narrativa
sobrevive só em `summary`; a mecânica que a tela foi construída para ler
(`/v1/runs/{run_id}/replay` → turns/tool_calls/evidence) nunca é gravada.
`start_investigation` avisa no próprio docstring: o recorder é "um runner
composto com um lugar para registrar o raciocínio" — e nada o compõe. Mesmo
formato de seam do deep-verifier: tudo escrito, nada ligado.

**4. A metade do produto que age é inexistente como comportamento — os testes
existem, a composição não.** (backlog + medição independente de outro agente,
confirmada) O inventário é real: **80 capacidades registradas** — 44 `read` +
12 `read_sensitive`, 24 que escrevem (15 reversíveis, 6 irreversíveis, 3
destrutivas), **24 declarando `requires_approval`** com razão e rollback ao
lado. Os portões existem de verdade: `RemediationGate`
(`platform/remediation/gating.py:187`) e `AutonomyGate`
(`platform/autonomy/decision.py:168`), com rotas de aprovação e proposta já
permissionadas no console. E **nenhuma composition root constrói nenhum dos
dois** — `RemediationGate(` e `AutonomyGate(` só aparecem em testes, contract
tests e no mock data plane. O guarda que segura isso é fail-closed e está no
lugar certo: o corpo de toda capacidade de remediação é um coto deliberado que
responde `PERMISSION_DENIED` ("runs through the remediation gate… refuses when
neither exists") — o agente não age sozinho, mas também não age nunca.
Consequência visível: "Proposed action — Nothing proposed yet" em todo
incidente, `/decisions` eternamente vazio, o fluxo do incidente parando no
diagnóstico. Efeitos colaterais anexos: `_select_tools` não filtra por
`side_effect_level`, então o modelo pode receber uma ferramenta de remediação
no orçamento de esquemas, gastar uma chamada nela e levar a recusa — turno
perdido e transcript confuso; `pending_interactions` devolve nada e
`answer_interaction` recusa, então mesmo um gate composto não teria onde pôr a
pergunta. Junto do mesmo seam: o investigador não filtra ferramentas pelas
integrações configuradas (`gateway/runtime/investigator.py`, docstring),
`TeamCatalogueResolver` nunca é instanciado, `build_pipeline`/
`ResolveIntegrationsStage` sem caller de produção. Mesma forma do deep
verifier antes de ser composto: ADR 0006 decidido, peças escritas, fio nunca
ligado.

### P1 — telas que mentem ou se contradizem

**5. Estados contando histórias diferentes sobre o mesmo fato.**
- Lista de incidentes: chip **INVESTIGATING**; detalhe do mesmo incidente:
  chip **"No investigation"** (o detalhe deriva o chip da leitura que falhou —
  defeito 2 — e afirma o negativo em vez de "não sei").
- `/decisions` e `/knowledge` afirmam "investigations **cannot run** until
  [3 steps] are done" enquanto `/runs` lista 37 — a causa de vazio
  (`empty.cause.setup`, via `setupCause` em `console/src/surfaces/emptiness.ts:46`)
  afirma uma causalidade que o gating real não tem.
- `/first-run`: "Connect a model provider — **You are here**", Gemini
  **Stored**; `/settings/models-providers`: o mesmo Gemini **Verified**. O
  checklist e o verify leem fontes diferentes — o mesmo seam que o backlog
  crava em "The investigator's model key comes from the environment, not the
  vault".
- Run completed com badge "Paused in the background" e painel Control ativo
  ("Stop this investigation", vermelho) — controles de um run vivo sobre um
  run que acabou. (`run-detail.tsx` esconde o painel Takeover quando
  `!running`, mas o estado que veio do run não é o settled esperado —
  sintoma a investigar junto do defeito 3.)

**6. Listas renderizam de cache como se fossem vivas.** `/incidents` carregou
completa sem **uma** requisição chegar ao `app` (access log limpo durante o
load; só health checks). `authorised()` põe `cache: 'no-store'` por request
(`console/src/surfaces/read.ts:26`), mas a rota inteira está sendo servida do
Full Route Cache do Next. Um operador olhando a lista de incidentes está
olhando o passado sem nenhum aviso. As páginas de lista precisam ser
declaradas dinâmicas (ou revalidadas por evento), e isso merece teste.

**7. Rotas fantasmas e nomes que não se encontram.** A área se chama
**Investigations** (sidebar, busca "Search resources, investigations,
incidents"), a rota real é `/runs`, e `/investigations` responde "There is no
such page". `/setup` idem (real: `/first-run`). Quem digita o nome que o
produto usa cai em 404 sem redirect.

**8. Meta-linhas de placeholder.** Subtítulo do incidente quebrado:
"Not recorded · this deployment's own detectors · started · zone Unplaced ·
Not recorded" — cinco slots, três em fallback, lidos como uma sentença sem
sujeito. Na lista de runs: SUBJECT "Not recorded", DURATION "Not recorded".
Placeholder atrás de placeholder era regra de banimento da v5/v6 para
Settings; as telas de "Now" precisam da mesma regra.

### P2 — corroem clareza e confiança

**9. Identidade dos runs é hex.** Coluna INVESTIGATION = `e19e882a`,
breadcrumb = id inteiro, duração "11s" como único fato humano. Com o headline
do defeito 1 resolvido, o id sai do papel de nome.

**10. Idioma misto.** Annotations dos alertas em pt-BR ("excedeu a janela
maxima sem sucesso") dentro de UI 100% en. O console tem `requestLocale` e
catálogo i18n — decidir e aplicar (en consistente, ou pt-BR do deployment),
não misturar por acidente.

**11. A cadeia Proxmox continua cortada** (backlog): certificado self-signed
sem caminho de confiança até o proxy → integração Degraded → estate vazio →
"Alerts for things not here" para todo alerta → incidente sem subject
resolvível → "zone Unplaced". O primeiro elo é o certificado; a tela reporta
o último ("no node answered").

**12. Miudezas vistas no tour.** "23 minutes ago · Alert · 11s" como única
meta do run; painel "Cost and tokens" com CTA "Back to the investigations"
dentro do card; coluna SUBJECTS da lista de incidentes é um número sem
tooltip/explicação.

## 3. O que o backlog já sabia (referência cruzada)

| Item do backlog | Situação vista | Onda |
|---|---|---|
| Run detail vazio (`trace_events` sem `tool_calls`/`turns`/`evidence`) | Confirmado no banco e na tela | v7 (núcleo) |
| A metade que age não composta | Confirmado na tela (Decisions/Proposed action) | v7 (núcleo) |
| Investigador não filtra por integrações; `TeamCatalogueResolver`; pipeline sem caller | Não visível na tela, confirmado em código | v7 |
| Chave do modelo: env vs vault | Sintoma visível (Stored vs Verified) | v7 |
| Proxmox self-signed | Visível (Degraded + estate vazio) | v7 — feature 070 (desenhada como mudança de fronteira de segurança) |
| Primeiro administrador de um deployment novo | Não tocado nesta rodada | v7 — feature 050 |
| Guias de credencial (`min_scope`/`guide_url`) | Não tocado | v7 — feature 060 |
| Alertmanager/DNS do cluster de monitoração | Infra, não produto | v7 — checklist ops-1 (com evidência no confronto) |
| Gateway de modelo sem chave (Ollama) | Staging usa Gemini; sem bloqueio | v7 — checklist ops-3 |
| Dois service accounts (UniqueViolation no email vazio) | Não retestado | v7 — feature 050 |

## 4. Fatos de infra verificados (2026-08-23)

- k3s `k3s-stg-ninjasre`: pods `app`, `web` (console Next 16.3.0, porta 8425),
  `console` (deployment legado ainda de pé — candidato a remoção do chart),
  `proxy`. Ingress: `/ → web`, `/webhooks → app`.
- Banco `ninjasre-stg-db` (10.20.20.54): 36 tabelas; contagens citadas acima.
- Gemini configurado e Verified via vault/proxy (entrega do handoff anterior
  confirmada); 37 investigações executadas contra alertas reais do
  Alertmanager da stack.
- Incidentes reais em aberto: RestoreDrillStale, CronJobStale,
  ProxmoxCriticalLogDetected, BlackboxProbeFailed, InstanceDown — matéria-prima
  boa para o cenário ponta-a-ponta da onda.

## 5. O recorte que este diagnóstico sugere

Quatro veios, na ordem da dependência real:

1. **Registrar** — compor o recorder: turns, tool_calls, evidence e custo
   gravados por toda investigação; headline/report separados no contrato.
2. **Mostrar** — o console lê o que foi registrado: markdown renderizado,
   título curto, transcript real, custo real, listas com sujeito; ids opacos
   e rotas que respondem pelos nomes que o produto usa.
3. **Não mentir** — uma fonte por fato: gating do setup, verified/stored,
   chips de estado, listas sem cache congelado, placeholders banidos das
   telas de "Now".
4. **Agir** — os gates compostos em propose-only: proposta → aprovação →
   execução registrada; Decisions vivo; ferramentas filtradas pelo que o time
   conectou.

O detalhamento em features, ordem e DoD fica no [README.md](README.md).
