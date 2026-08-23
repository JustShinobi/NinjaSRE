# specs_v6 — Diagnóstico: Settings pós-v5, escopo validável e o primeiro incidente

Análise feita em 2026-08-16 sobre o front local (preview 3100) em 1920×1080,
backend do repositório rodando no CT254 (release `20260816-202103-eb8c6f1` =
HEAD `eb8c6f1` — confirmado). Toda tela do grupo Settings foi percorrida com a
barra de rolagem inteira; toda afirmação de defeito abaixo foi vista na tela ou
cravada em código com `file:line`.

**Referência visual de DoD desta onda**: [mockups/settings-v6.html](mockups/settings-v6.html).

---

## 1. Estado por tela (o que existe hoje)

| Tela | Altura (viewports 1080p) | Veredito |
|---|---|---|
| `/settings/members-roles` | 1.0 | Funcional, com vazamentos de vocabulário e sem ação de criar/convidar pessoa |
| `/settings/single-sign-on` | 1.5 | Funcional, mas valida antes de o usuário digitar e mostra erros em snake_case |
| `/settings/machine-tokens` | 1.0 | Funcional; default de escopos perigoso (27/27 marcados) |
| `/settings/audit-log` | 1.0 | **Quebrada**: "Showing 200 of 156,735" com tabela vazia |
| `/settings/models-providers` | 1.1 | Funcional; verificação falhando exibida como parágrafo sem hierarquia; copy "Set at Set at:" |
| `/settings/autonomy-guardrails` | 2.3 | Kitchen-sink; tabela Guardrails **sem nenhum valor** na coluna VALUE |
| `/settings/notifications` | 1.0 | Mesma tabela **sem valores**; só schema-browser por baixo |
| `/settings/alert-intake` | 2.1 | Funcional; 7 fontes idênticas repetidas, jargão `webhook.deliver` |
| `/settings/schedules-destinations` | 1.4 | Funcional; tabela-fantasma sob empty state; 2 "Advanced" com nomes sobrepostos |
| `/integrations` | ~2.0 (paginado) | Muito melhor pós-v5; detalhe abre como painel no rodapé do catálogo (não slide-over) |
| `/first-run` | 1.0 | Estrutura boa; **duas contagens divergentes na mesma tela** |

## 2. Defeitos confirmados (ordenados por gravidade)

### P0 — bloqueiam o produto ser configurado/usado

1. **O setup nunca fecha: verificação de tool-calling reprova qualquer modelo Gemini.**
   Cadeia completa, cravada:
   - O probe (`core/llm/preflight.py:168` `_tool_call_check`) pede "Call the echo
     tool…" mas o cliente Gemini monta `functionCallingConfig: {mode: "AUTO"}`
     (`core/llm/providers/gemini.py:193`) — modo em que o modelo pode
     legitimamente responder em texto. Reproduzido no CT254 com o env do serviço:
     `gemini-2.5-flash` → `[degraded] tool calling — the model answered without
     calling the tool`, e o **preflight como um todo PASSA**.
   - O console traduz esse `degraded` como **"Failing"** e o passo 5 do wizard
     nunca completa. Backend diz "usável", UI diz "Failing" — sobre o mesmo dado.
   - Fix da spec: probe com `mode: "ANY"` (e `tool_choice` equivalente nos outros
     providers) + estado do console espelhando o status real do preflight
     (passed/degraded/failed), com degraded explicado e não bloqueante.
2. **Investigações desligadas por falta de runtime** ("This deployment has no
   runtime to investigate with"). Os 2 incidentes do dashboard morrem nisso há
   5 dias. O fluxo do primeiro incidente depende de resolver o runtime — a spec
   da feature precisa tratá-lo como pré-condição de DoD (deploy do runtime no
   CT254 e verificação no próprio produto).

### P1 — quebram uma tela ou mentem para o operador

3. **Audit log vazio com contador cheio**: "Showing 200 of 156,735", cabeçalhos
   WHEN/PRINCIPAL/ACTION/SUBJECT/OUTCOME e **zero linhas** (server-rendered, sem
   erro de console). Era correção nomeada na v5 ("reconciliar 200 events ×
   Nothing recorded") — não aconteceu.
4. **Tabelas de configuração sem valores**: em Autonomy (Guardrails) e
   Notifications, a coluna VALUE está vazia nas 12 linhas (Masking enabled,
   Quiet hours, Timezone…). A tabela informa só "Deployment default" — o
   operador não descobre o valor efetivo de nada.
5. **Contagem do setup divergente na mesma tela**: header "Step 5 of 7" vs
   painel "3 of 5 steps left" (e são 2 os pendentes, não 3). O mesmo defeito que
   a v5 mandou matar ("uma só contagem, calculada num lugar só") voltou com
   outros números. Também aparece no card do dashboard.
6. **SSO valida formulário virgem**: 8 erros vermelhos (`client_id is required`,
   `jwks_uri is required`…) antes de qualquer digitação, em snake_case,
   enquanto os labels do form são humanos ("Client id", "Key set").

### P2 — corroem a confiança/clareza

7. Vocabulário cru sobrevivente (regra v5 violada): chip `SERVICE_ACCOUNT`,
   chips `HEALTHY` para pessoas e grupos de token, `google_gemini` em texto de
   erro, `models.investigator.model` no preview do wizard, grupos
   `policies.masking`/`surfaces.notification_policy` como títulos,
   "Trusted by webhook.deliver", IDs `res-8f81848…` nas sugestões do catálogo,
   sessão exibida como "59".
8. "1 tokens" (plural), "Set at Set at: default" (copy duplicada).
9. Machine tokens: 27 escopos **todos marcados por padrão** — um token novo
   nasce com `Org Delete`, `Owner Assign`, `Impersonation Use`. Default seguro é
   nenhum (ou template mínimo por finalidade).
10. Autonomy é um kitchen-sink de 2.3 viewports: postura + regras + freeze +
    budgets + overrides + simulação (3 botões de 3 estilos sem contexto) +
    guardrails + schema-browser, numa página. A v5 mandava ≤2 viewports.
11. CTA "Look at the configuration" (empty state de Rules) na verdade abre
    `#new-rule` na própria página — rótulo promete outra coisa.
12. `/configuration` redireciona para **Members & roles** — quem procurava o
    editor aposentado cai numa tela de pessoas sem explicação.
13. Detalhe de integração é um painel **no rodapé do catálogo** (2.141px):
    clicar numa integração te joga para o fim da página, fora do padrão
    slide-over que o mockup-3 da v5 fixou como normativo. Para integração já
    verificada, o form mostra Token vazio + "Save and test" desabilitado —
    parece quebrado (falta "Test again"/estado explícito de "guardada").
14. Members & roles sem ação primária de criar/convidar pessoa; grants em
    lista de permissões cruas (`approval.read, config.read, …`) como help text.

## 3. Aderência às regras transversais da v5

| Regra v5 | Veredito |
|---|---|
| Navegação híbrida (Settings + subnav 3 grupos) | ✅ Entregue |
| Catálogo navegável, contagem no topo | ✅ Entregue (paginação em vez de seções; aceitável) |
| Setup como wizard, handoff para telas reais | ✅ Estrutura entregue |
| Editor cru substituído por completo | ⚠️ Rota morta ✅, mas metade das "telas donas" é schema-browser reskinado (`policies.*` collapsibles) com tabela de valores vazia |
| Uma só contagem no setup | ❌ Violada (defeito #5) |
| Vocabulário único de estado (Não conectada/Armazenada/Verificada/Falhando) | ⚠️ Chips novos existem; HEALTHY/SERVICE_ACCOUNT/snake_case sobrevivem |
| Nome de exibição obrigatório (id cru só em contexto técnico) | ❌ Violada em ≥7 lugares (defeito #7) |
| CTA aterrissa no alvo com o verbo certo | ⚠️ "Look at the configuration"→`#new-rule`; `/configuration`→members-roles |
| Ajuda mora no campo; sem prosa sob título | ❌ Autonomy tem 3 parágrafos conceituais sob o título |
| Rolagem é bug (≤2 viewports 1080p) | ❌ Autonomy 2.3; Alert intake 2.1 |
| Reconciliar Audit "200 × nothing" | ❌ Não feita (defeito #3) |
| Credencial em slide-over (mockup-3) | ❌ Painel no rodapé |
| Agrupar tokens do bootstrap + expurgo | ✅ Entregue ("bootstrap · 12 revoked") |

## 4. Inventário do cluster × catálogo (a decisão de escopo)

Cluster HAL9000 (pve01+pve02, Qdevice). Fonte:
`/root/infra-cluster/inventory/cluster/services.yaml` + stack de monitoring em
`/root/infra-cluster/services/monitoring/stack/`.

**Observabilidade real hoje**: Prometheus (10.20.20.37:9090) + **Alertmanager**
(mesma stack, com regras em `prometheus/rules/cluster-alerts.yml`: InstanceDown,
BlackboxProbeFailed HTTP/TCP/DNS, RedisInstanceDown, PostgresInstanceDown,
SSLCertExpiry, ProxmoxClusterApiDown…) + Grafana (CT133) + Loki+Promtail +
Blackbox + Gatus (CT138) + OpenObserve (CT121) + SigNoz (CT111) + n8n
(workflow Alertmanager→Pushover). O Alertmanager já entrega webhook para o
antecessor (`opensre-critical → http://10.20.20.65:9001/alertmanager`) — o
NinjaSRE assume esse lugar.

**Catálogo atual: 85 integrações. Validáveis contra o cluster: 13.**

| Grupo | Integrações | Situação |
|---|---|---|
| Conectadas e verificadas | `proxmox`, `prometheus`, `google_gemini` | Manter |
| Rodando no cluster, só conectar | `alertmanager`, `grafana`, `loki`, `openobserve`, `signoz`, `redis` (CT122, exporter já existe) | Manter |
| Rodando, exigem exposição/rota de rede | `kubernetes` (k3s CT164, zona vk8s), `argocd` (GitOps de produção no k3s — `gitops/k3s-gitops-prod/` no repo infra) | Manter (validação condicional) |
| Conta que o operador já usa | `pushover` (n8n já entrega lá), `hermes` (serviço próprio, 10.20.20.51) | Manter |
| Confirmar com o operador | `github`, `telegram`, `discord`, `whatsapp` (my-whatz existe, parado) | Perguntar |
| **Remover → roadmap** | As demais ~68–72 (aws\*, azure\*, gcp, datadog, sentry, pagerduty, opsgenie, jira, slack, snowflake, splunk, …) e `proxmox_backup_server` (sem PBS no cluster — `pvesm status` só cifs/dir/lvmthin) | Remover do produto; intenção registrada em roadmap |
| **Faltando no catálogo** (roadmap de criação) | **PostgreSQL** (CT129 é o banco real do cluster e não há integração), Traefik, Gatus, n8n, Infisical, AdGuard/DNS | Roadmap |

A remoção não é só apagar diretórios: cada pacote tem fixtures, docs e a suíte
de paridade (85 em paridade total hoje) + página de catálogo + fontes de intake
(`/webhooks/{datadog,opsgenie,pagerduty,sentry}` saem; ficam `alertmanager`,
`grafana`, `generic`). A spec da feature precisa listar todos os pontos de
contagem/contrato que mudam.

## 5. Cenário de teste do primeiro incidente (desenho)

Pré-condições descobertas na análise:

- CT254 = `192.168.68.74`; gateway `:8420`; `POST /webhooks/alertmanager`
  responde **401** sem token → o trust é o delivery token emitido em
  Settings → Alert intake ("Issue a delivery token").
- Verificar rota de rede zona infra (10.20.20.x) → LAN (192.168.68.74). O
  webhook atual do Alertmanager alcança 10.20.20.65; mesmo firewall precisa
  liberar o destino novo.
- Runtime de investigação instalado (defeito P0-2) e provider verificado
  (P0-1).

**T1 — Alerta sintético (zero risco, valida intake→investigação):**
`amtool`/`curl POST` na API do Alertmanager (`/api/v2/alerts`) com um alerta
fabricado (`alertname=NinjaSRETest`, labels apontando um serviço real) →
rota do Alertmanager entrega no webhook do NinjaSRE → incidente aparece em
`/incidents` → investigação roda (Prometheus + Proxmox) → relatório propõe
diagnóstico em modo propose-only.

**T2 — Falha real controlada (valida o troubleshoot):**
`pct stop` num serviço de criticidade média da zona apps (candidatos:
`streamlink-webui` CT139, `bazarr` CT103 — confirmar com o operador) →
`InstanceDown`/`BlackboxProbeFailed` dispara de verdade → NinjaSRE recebe,
correlaciona métricas do Prometheus com estado do CT via Proxmox, e o
diagnóstico esperado nomeia "container parado" com a ação de religar
(proposta, não executada — propose-only). Rollback: `pct start`.

DoD do fluxo: dos dois cenários, existir **um incidente em `/incidents` com
timeline legível** — alerta recebido → hipóteses → evidências (queries feitas)
→ diagnóstico → ação proposta aguardando decisão — e o operador consegue
aprovar/rejeitar a partir da tela.

## 6. Proposta de features da onda specs_v6

| # | Feature | Essência | Depende de |
|---|---|---|---|
| 001 | Escopo validável | Cortar catálogo para o conjunto validável; intake reduzido; roadmap registrado; contagens/paridade/docs ajustados | — |
| 010 | Confiabilidade da configuração | Defeitos P0-1 (probe ANY + estado degraded honesto), P1-3 (audit), P1-4 (valores nas tabelas), P1-5 (contagem única), P1-6 (SSO sem validação prematura) | — |
| 020 | Settings sem vocabulário cru | Regras v5 aplicadas de verdade: display names em todo lugar, chips únicos, defaults seguros de token, copy fixes | 010 |
| 030 | Rework Autonomy + telas donas de verdade | Autonomy ≤1.5 viewport (postura/regras/guardrails com valores), fim do schema-browser como face principal | 010 |
| 040 | Integrations: detalhe em slide-over + intake enxuto | Mockup-3 da v5 cumprido; alert-intake com 3 fontes e estado real; cadeia intake→rota→destino visível | 001 |
| 050 | Primeiro incidente ponta a ponta | Runtime como pré-condição verificada, webhook Alertmanager→NinjaSRE com delivery token, cenários T1/T2, timeline de investigação em `/incidents/[id]` | 001, 010 |

(Numeração e recorte a validar no brainstorm; 020/030/040 podem fundir ou
paralelizar conforme o apetite.)

## 7. Decisões confirmadas pelo operador (2026-08-16)

1. **Corte**: lista de 13 confirmada, **+ GitHub e Telegram** (15 no total).
   WhatsApp e Discord saem (my-whatz é outra aplicação, não um canal deste
   produto).
2. **Vítima do T2**: `streamlink-webui` (CT139) ou `bazarr` (CT103), aprovados.
3. **Roadmap das removidas**: seção committed em `docs/roadmap.md` — escrita
   em 2026-08-16 ("Integration scope (revised)"), só vendors, e o critério
   Coverage do MVP DoD reescrito. A feature 001 emenda ADR 0009/constituição
   no mesmo sentido: paridade por integração embarcada, amplitude estagiada.
4. **Runtime no CT254**: parte da feature do primeiro incidente, como
   pré-condição verificável de DoD.
5. **Recorte**: specs detalhadas, sem fusão — e o fluxo do provider Gemini
   ganhou feature própria (010). Evidência nova que a motiva: a lista de
   modelos é hardcoded (`core/llm/onboarding/gemini.py:28-33`, 6 modelos,
   parada duas gerações atrás), enquanto `GET /v1beta/models` com a chave do
   deployment lista **37 modelos generateContent**, incluindo
   `gemini-3.5-flash`, `gemini-3.6-flash` e `gemini-3.7-flash` — testado de
   dentro do CT254 em 2026-08-16. O texto do produto ("This endpoint could
   not be asked what else it serves") é factualmente falso. O fluxo-alvo é
   out-of-the-box: chave → lista da API (curada para modelos de texto) →
   escolha → verificação com tool-calling forçado.
6. **Validação contínua de aderência**: cada feature de console embarca um
   acceptance spec Playwright que codifica as alegações normativas do mockup,
   escrito antes da tela e confirmado vermelho; as regras transversais viram
   suíte executável (`console/tests/e2e/transversal-rules.spec.ts`) rodada a
   cada fronteira de feature. spec-wave, spec-implementer e spec-verifier
   foram atualizados nesse sentido em 2026-08-16.
7. **Ajuste de 2ª rodada no corte (pós-geração)**: `argocd` **entra** (o
   cluster roda Argo CD — GitOps de produção em `gitops/k3s-gitops-prod/` no
   repo infra) e `docker` **sai** (ferramenta local, não é alvo de
   troubleshoot remoto). Total permanece 15. `gatus` e `n8n` saíram da lista
   "faltando criar" do roadmap (não precisam). Specs, roadmap e mockups
   ajustados no mesmo dia.
