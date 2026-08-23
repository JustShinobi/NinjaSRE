# specs_v6 — Escopo validável, configuração confiável e o primeiro incidente

Onda gerada em 2026-08-16 a partir do diagnóstico completo das telas de
Settings (Full HD, preview 3100, backend CT254 em `eb8c6f1`), do inventário do
cluster HAL9000 via pve02 e do brainstorm com o operador. Diagnóstico
completo, com cada defeito cravado em `file:line`: [DIAGNOSTICO.md](DIAGNOSTICO.md).

**Referência visual de DoD**: [mockups/settings-v6.html](mockups/settings-v6.html)
— M1..M6, normativos em layout, hierarquia, agrupamento e vocabulário (pixels
não). Versão publicada (idêntica):
<https://claude.ai/code/artifact/26135e19-9bd8-49b3-9848-d882c5e00136>.
As regras transversais da v5 (`specs_v5/mockups/settings-v5.html`, Parte 3)
continuam normativas por referência.

## As decisões que governam a onda

1. **Só se embarca o que o ambiente valida.** O catálogo cai de 85 para **15**
   integrações (proxmox, prometheus, alertmanager, grafana, loki, openobserve,
   signoz, redis, kubernetes, argocd, google_gemini, pushover, hermes, github,
   telegram — ajuste de 2ª rodada: argocd entrou no lugar de docker, que é
   ferramenta local e não alvo de troubleshoot). O resto sai do produto e vive em `docs/roadmap.md` ("Integration
   scope (revised 2026-08-16)"). Paridade continua total — por integração
   embarcada. A 001 emenda ADR 0009 e a constituição nesse sentido.
2. **Provider é fluxo out-of-the-box.** Chave → lista de modelos carregada da
   API do vendor (curada) → escolha → verificação com tool-calling **forçado**
   (`mode: "ANY"`) → estado espelhado (passed · degraded · failed), nunca
   traduzido. Evidência: 37 modelos via `GET /v1beta/models` de dentro do
   CT254 contra 6 hardcoded em `core/llm/onboarding/gemini.py`.
3. **Mockup vira teste antes da tela.** Toda feature de console embarca
   `console/tests/e2e/<slug>.acceptance.spec.ts` com as alegações normativas
   do seu mockup, confirmado vermelho antes da implementação. As regras
   transversais viram `console/tests/e2e/transversal-rules.spec.ts` (bans de
   vocabulário, orçamento de rolagem ≤2 viewports em 1080p, contagem única,
   coluna de valor nunca vazia), rodada a cada fronteira de feature pelo
   orquestrador — a aderência é validada durante a onda, não no confronto
   final. spec-wave/spec-implementer/spec-verifier já exigem isso.
4. **O primeiro incidente fecha ponta a ponta no cluster real.** Alertmanager
   da stack (10.20.20.37) → webhook autenticado por delivery token →
   investigação com timeline → ação proposta em propose-only. Runtime de
   investigação no CT254 é pré-condição verificável da feature, não suposição.

## Índice e ordem de execução

| Spec | Domínio | Depende de |
|---|---|---|
| [001](001-escopo-validavel/spec.md) | Corte do catálogo para o validável; intake enxuto; gates/paridade/ADR ajustados | — |
| [010](010-provider-out-of-the-box/spec.md) | Fluxo do provider: lista dinâmica de modelos, probe honesto, estados espelhados, tela M1 e passo do wizard | 001 |
| [020](020-confiabilidade-telas/spec.md) | Telas dizem a verdade: audit com linhas, colunas Value preenchidas, contagem única, SSO sem validação prematura, copy; suíte transversal | — |
| [030](030-vocabulario-defaults/spec.md) | Vocabulário sem cru; defaults seguros de token; higiene de IDs | 020 |
| [040](040-autonomy-tres-abas/spec.md) | Autonomy em três abas ≤1.5 viewport, valores presentes, override em painel (M2) | 020 |
| [050](050-integrations-slideover-intake/spec.md) | Catálogo pós-corte sem paginação, detalhe em slide-over (M4); Alert intake enxuto com cadeia visível (M3) | 001 |
| [060](060-primeiro-incidente/spec.md) | Runtime verificado, webhook Alertmanager→NinjaSRE, cenários T1/T2, timeline de investigação (M6) | 001, 010, 050 |

Execução **sequencial** na ordem acima (árvore compartilhada; arquivos de
escrita única: `console/src/i18n/*.ts`, `console/src/shell/routes.ts`,
`console/visual/screens.json`). A suíte transversal nasce na 020; da 030 em
diante ela roda em toda fronteira de feature.

## Onde os testes moram (herdado da v5, continua valendo)

- Vitest coleta **só** `console/tests/unit/**/*.test.ts(x)`.
- Playwright: `behaviour` (`console/tests/e2e`), `first-day`
  (`console/tests/first-day`), `visual` (`console/tests/visual`);
  `console/e2e/` **não existe**. Acceptance specs desta onda:
  `console/tests/e2e/<slug>.acceptance.spec.ts`.
- Viewport global do Playwright é 1440×900; medição de orçamento de rolagem em
  1080p declara o próprio viewport explicitamente.

## Ferramentas do spec-kit

`.specify/feature.json` aponta a feature ativa. Para gerar/planejar outra
feature, exporte `SPECIFY_FEATURE_DIRECTORY=<dir absoluto da feature>` em vez
de editar o arquivo — obrigatório quando mais de um contexto trabalha a onda.

## Fatos de infra que as specs assumem (verificados em 2026-08-16)

- Backend: pve02/CT254 (`192.168.68.74`), gateway `:8420`, release-symlink
  `/opt/ninjasre/current` = `eb8c6f1`.
- `POST /webhooks/alertmanager` responde 401 sem delivery token (o trust).
- Alertmanager real: stack de monitoring em 10.20.20.37 (config no repo
  infra-cluster do pve02), receiver webhook já aponta para o antecessor em
  `10.20.20.65:9001` — o NinjaSRE assume esse padrão de entrega.
- Regras prontas para cenário: InstanceDown, BlackboxProbeFailed (HTTP/TCP/
  DNS), RedisInstanceDown, PostgresInstanceDown, SSLCertExpiry,
  ProxmoxCluster/NodeApiDown.
- Vítimas aprovadas para T2: `streamlink-webui` (CT139) ou `bazarr` (CT103);
  reversão por `pct start`.
- Sem PBS no cluster; sem integração PostgreSQL no catálogo (ambos roadmap).
