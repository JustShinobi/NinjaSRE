# NinjaSRE — Guia Arquitetural e Operacional (PT-BR)

> **Documentação técnica gerada com base no código-fonte real da aplicação.**

O **NinjaSRE** é uma plataforma de **Engenharia de Confiabilidade de Sites (SRE) orientada por Inteligência Artificial**, totalmente **self-hosted** (executada no seu próprio ambiente / infraestrutura privada). 

Ele investiga incidentes em produção, coleta evidências reais de telemetria, identifica causas-raiz estritamente comprovadas, propõe planos de remediação acionáveis (com aprovação humana e rollback obrigatório) e aprende continuamente a cada incidente sem vazar dados ou credenciais.

---

## 📑 Sumário

1. [Princípios Inegociáveis (Pilares de Design)](#-1-princípios-inegociáveis-pilares-de-design)
2. [Como a Aplicação Funciona](#-2-como-a-aplicação-funciona)
   - [Pipeline de Investigação em 6 Estágios](#pipeline-de-investigação-em-6-estágios)
   - [Loop de Raciocínio (ReAct Loop)](#loop-de-raciocínio-react-loop)
   - [Memória Episódica e Aprendizado](#memória-episódica-e-aprendizado)
3. [Segurança e Proxy de Credenciais](#-3-segurança-e-proxy-de-credenciais)
4. [Arquitetura de Pacotes (Tier Architecture)](#-4-arquitetura-de-pacotes-tier-architecture)
5. [Stack Tecnológica Completa](#-5-stack-tecnológica-completa)
6. [Topologia de Deploy (Containers e Redes)](#-6-topologia-de-deploy-containers-e-redes)
7. [Catálogo de Integrações (80+ Ferramentas)](#-7-catálogo-de-integrações-80-ferramentas)
8. [Superfícies de Interação (Interfaces)](#-8-superfícies-de-interação-interfaces)
9. [Guia de Operação e Comandos Úteis](#-9-guia-de-operação-e-comandos-úteis)

---

## 🛡️ 1. Princípios Inegociáveis (Pilares de Design)

O NinjaSRE foi construído sobre contratos arquiteturais rígidos, validados automaticamente no CI por scripts de linting e contratos de importação:

| Princípio | O que significa na prática | Onde é validado |
|---|---|---|
| **Evidência sobre Afirmação** | Uma conclusão **precisa** carregar as observações e métricas que a sustentam. Suposições não fundamentadas são tratadas apenas como hipóteses. O que não foi registrado no trace não existiu. | `core/pipeline/stages/diagnose/` |
| **Autonomia Bounded (Limitada)** | Não existem "números mágicos" de loops ou tokens soltos no código. Tetos de loops, timeouts e limites de contexto são constantes nominais em `config/constants/`. | `tools/check_constants.py` |
| **Somente-Leitura por Padrão (Read-Only by default)** | Qualquer ferramenta sem `side_effect_level` declarado é tratada como escrita perigosa. Qualquer ação de alteração/remediação exige **aprovação humana por ação** e um **plano de rollback testado**. | `capabilities/` & `platform/guardrails/` |
| **Zero Segredos no Agente (Mandatory Credential Proxy)** | O LLM, prompts e logs **nunca** têm acesso a tokens, chaves de API ou senhas reais. O agente usa `CredentialHandles` opacos; o segredo é injetado na borda da rede pelo serviço isolado de proxy. | `platform/credentials/proxy/` |
| **Datastore Único (Single Datastore)** | Um único cluster PostgreSQL armazena dados relacionais, vetores (`pgvector`) e grafo de topologia (`Apache AGE`). Nenhuma query SQL ou Cypher é permitida fora de `platform/persistence/`. | `platform/persistence/` & `tools/check_raw_sql.py` |
| **Neutralidade de Provedores de LLM** | Suporte unificado a Anthropic, OpenAI, Gemini, Bedrock, Azure, Ollama, vLLM, etc., via extras opcionais do Python. O core não importa SDKs de fornecedores diretamente. | `core/llm/` & `tools/check_vendor_sdks.py` |
| **Privacidade Total / Sem Telemetria Externa** | Nenhum dado analítico, log de erro ou telemetria é enviado para servidores externos. 100% dos dados permanecem no host do operador. | `tools/check_dependencies.py` |

---

## ⚙️ 2. Como a Aplicação Funciona

Quando um alerta ou incidente ocorre (via Webhook, PagerDuty, Alertmanager, Slack ou chamada manual via CLI/Web Console), o NinjaSRE inicia uma execução orquestrada.

### Pipeline de Investigação em 6 Estágios

O fluxo segue uma máquina de estados sequencial e determinística:

```
[ Ingestão / Alerta ]
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. RESOLVE_INTEGRATIONS                                     │
│    Identifica quais ferramentas de monitoramento e nuvem    │
│    estão configuradas para o serviço/ambiente afetado.      │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. INTAKE (Triagem)                                         │
│    Filtra ruído, desduplica alertas recorrentes e cria      │
│    a entidade de Incidente rastreável.                      │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. PLAN_EVIDENCE                                            │
│    Consulta a topologia da infraestrutura e a memória       │
│    episódica para planejar quais métricas/logs coletar.     │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. GATHER_EVIDENCE (Loop ReAct)                             │
│    Executa consultas reais (Prometheus, Loki, K8s, AWS, etc)│
│    usando ferramentas especializadas e sub-agentes.         │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. DIAGNOSE                                                 │
│    Analisa as evidências coletadas, descarta hipóteses,     │
│    calcula nível de confiança e aponta a causa-raiz.        │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. DELIVER                                                  │
│    Gera o relatório estruturado, notifica canais (Slack,    │
│    Teams, Console), propõe remediação e grava o episódio.   │
└─────────────────────────────────────────────────────────────┘
```

Se o estágio `INTAKE` detectar que o alerta é apenas ruído ou duplicata, a execução é encerrada precocemente com status `NOISE` ou `DUPLICATE`, poupando tokens e processamento.

---

### Loop de Raciocínio (ReAct Loop)

No estágio de coleta de evidências (`gather_evidence`):
1. **Orçamento de Contexto (`ContextBudget`)**: Monitora o consumo de tokens e a profundidade de chamadas.
2. **Sub-Agentes Especialistas**: Delegação de tarefas paralelas ou específicas (ex: especialista em Kubernetes, especialista em Logs, especialista em Banco de Dados).
3. **Cache de Ferramentas & Anti-Estagnação**: Evita chamadas repetidas idênticas e detecta quando a investigação não está avançando, forçando novas linhas de investigação.
4. **Mascaramento em Tempo Real**: Qualquer dado sensível (PII, tokens, dados bancários/senhas) retornado por comandos ou logs é mascarado antes de entrar no contexto do modelo.

---

### Memória Episódica e Aprendizado

O NinjaSRE não é apenas um chatbot reativo; ele melhora a cada execução:
- **Grafo de Topologia (`Apache AGE`)**: Modela nós de infraestrutura (Serviços, Pods, Bancos, Filas, APIs) e seus relacionamentos de dependência.
- **Memória de Episódios (`pgvector`)**: Converte incidentes passados em *embeddings* vetoriais. Em novos incidentes, realiza busca semântica para resgatar diagnósticos anteriores que apresentaram sintomas semelhantes e quais passos de remediação funcionaram.
- **Ablações e Regressão Contínua**: O repositório conta com um harness sintético offline com dezenas de cenários reais para garantir que novos aprendizados não causem regressão no diagnóstico.

---

## 🔒 3. Segurança e Proxy de Credenciais

Uma das maiores inovações de segurança do NinjaSRE é a separação rígida entre a lógica do agente e a posse das credenciais:

```
┌─────────────────────────┐          ┌─────────────────────────┐          ┌───────────────────────────┐
│     NinjaSRE Agent      │          │    Credential Proxy     │          │    Serviço Externo        │
│   (Processo /app)       │          │     (Processo /proxy)   │          │ (AWS, Datadog, K8s, etc.) │
└────────────┬────────────┘          └────────────┬────────────┘          └─────────────┬─────────────┘
             │                                    │                                     │
             │ HTTP Request com Handle opaco      │                                     │
             │ Header: X-Credential-Handle: 9a3f… │                                     │
             │───────────────────────────────────>│                                     │
             │                                    │ 1. Valida Handle no Vault interno   │
             │                                    │ 2. Recupera chave privada / token   │
             │                                    │ 3. Assina requisição (ex: SigV4)    │
             │                                    │ 4. Injeta Bearer / Basic / API-Key  │
             │                                    │                                     │
             │                                    │ Requisição autenticada real         │
             │                                    │────────────────────────────────────>│
             │                                    │                                     │
             │                                    │ Resposta da API                     │
             │                                    │<────────────────────────────────────│
             │ Resposta (sem segredos)            │                                     │
             │<───────────────────────────────────│                                     │
```

* O contêiner da aplicação **não possui** as chaves de acesso a provedores de nuvem ou ferramentas de monitoramento.
* O contêiner de proxy reside em uma rede intermediária dedicada e atua como uma barreira criptográfica auditável.

---

## 🏗️ 4. Arquitetura de Pacotes (Tier Architecture)

O código é estritamente organizado em camadas (Tiers). As dependências apontam **exclusivamente para baixo**:

```
Tier 1: [ surfaces/ ] (CLI/Console)   |   [ gateway/ ] (REST/Webhooks/Chat)
                   │                               │
                   ▼                               ▼
Tier 2: [ capabilities/ ] (Tools/Skills) ──> [ integrations/ ] (80+ Clientes)
                   │                               │
                   ▼                               ▼
Tier 3: [ core/ ] (Agent/ReAct/Pipeline) <───> [ platform/ ] (Persistence/Vault/Memory)
                   │                               │
                   ▼                               ▼
Tier 4: [ config/ ] (Constantes/Prompts/Envs)
```

- `surfaces/`: Clientes para humanos — CLI Typer, REPL interativo e backend-for-frontend da console.
- `gateway/`: Portas de entrada — rotas FastAPI, streaming SSE, webhooks de alertas e bots de chat.
- `capabilities/`: Ferramentas executáveis pelo agente, com declaração de tipos e side-effects.
- `integrations/`: Um pacote isolado por provedor externo (config, schema de credencial, verifier e client).
- `core/`: O cérebro — pipeline de 6 estágios, ReAct loop, abstração unificada de LLMs e sub-agentes.
- `platform/`: Serviços transversais — persistência (PostgreSQL, pgvector, AGE), cofre de credenciais, proxy, guardrails, mascaramento e observabilidade.
- `config/`: Constantes nomeadas, definições de schemas e prompts (não importa nada de código).
- `console/`: Frontend Web independente em TypeScript / Next.js.

---

## 💻 5. Stack Tecnológica Completa

### Backend & Runtime (Python)
- **Linguagem**: Python 3.12+ (tipagem estrita com `mypy --strict`, formatação com `ruff`).
- **Web & API Gateway**: `FastAPI`, `Uvicorn`, Server-Sent Events (SSE).
- **Banco de Dados & ORM**: `PostgreSQL 16`, `SQLAlchemy 2.0 (Async)`, `asyncpg`, `Alembic`.
- **Vetores e Grafo**: Extensão `pgvector` (busca por similaridade de embeddings) e `Apache AGE` (grafo de topologia openCypher).
- **CLI & Terminal**: `Typer`, `Rich` (renderização e degradação elegante para terminais simples), `prompt-toolkit`.
- **Validação & Segurança**: `Pydantic v2`, `PyYAML`, `Cryptography` (cifras simétricas para credenciais em repouso).
- **Logs & Observabilidade**: `Structlog`, OpenTelemetry (OTel exporter).

### Frontend (Console Web)
- **Framework**: `Next.js 16` (App Router, Standalone output).
- **UI & Estilização**: `React 19`, `Tailwind CSS 4`.
- **Linguagem**: `TypeScript 5.9`.
- **Testes & Qualidade**: `Playwright` (testes E2E comportamentais e regressão visual), `Vitest` (testes unitários), `ESLint`, `Prettier`.
- **Geração de Tipos**: `openapi-typescript` sincronizado diretamente com o OpenAPI da API FastAPI.

### Provedores de Modelos de Linguagem (LLMs)
Abstração provider-agnostic com suporte nativo a:
- **Anthropic**: Claude 3.5 Sonnet, Claude 3 Opus, Claude 3.7 Sonnet.
- **OpenAI**: GPT-4o, GPT-4o-mini, séries o1/o3.
- **Google**: Gemini 1.5 Pro, Gemini 2.0 Flash/Pro via `google-genai`.
- **AWS Bedrock**: Claude, Llama e Titan via `boto3`.
- **Azure OpenAI**: Modelos hospedados na nuvem Microsoft.
- **Modelos Locais & Self-Hosted**: `Ollama`, `vLLM`, `NVIDIA NIM`, `OpenRouter`, `LiteLLM`, `DeepSeek`.

---

## 🐳 6. Topologia de Deploy (Containers e Redes)

Uma implantação padrão (`docker-compose.yml`) sobe exatamente **4 contêineres** organizados em redes com isolamento estrito:

```
                     ┌────────────────────────────────────────┐
                     │          REDE EXTERNA (egress)         │
                     └───────┬────────────────────────┬───────┘
                             │                        │
                    (Chama provedores)         (Injeta chaves)
                             │                        │
                             ▼                        ▼
┌──────────────┐     ┌──────────────┐         ┌──────────────┐     ┌──────────────┐
│   console    │────>│     app      │────────>│    proxy     │────>│   postgres   │
│ (Porta 8421) │     │ (Porta 8420) │         │ (Porta 8422) │     │ (Porta 5432) │
└──────┬───────┘     └──────┬───────┘         └──────┬───────┘     └──────┬───────┘
       │                    │                        │                    │
       └────────────────────┴────────────────────────┴────────────────────┘
                     ┌────────────────────────────────────────┐
                     │          REDE INTERNA (internal)       │
                     │       (Sem rota para a Internet)       │
                     └────────────────────────────────────────┘
```

1. **`postgres`**: PostgreSQL com `pgvector` + `Apache AGE`. Totalmente isolado na rede interna.
2. **`proxy`**: Credential Proxy. Conecta-se ao banco (para ler credenciais cifradas) e à rede egress para falar com serviços externos.
3. **`app`**: API REST, orquestração e runtime do agente. Fala com o banco, com a LLM e com o proxy.
4. **`console`**: Next.js Web Console exposto na porta `8421` (ou atrás de reverse proxy corporativo).

---

## 🔌 7. Catálogo de Integrações (80+ Ferramentas)

O NinjaSRE possui conectores completos divididos por domínios:

* **Métricas & Monitoramento**: Prometheus, VictoriaMetrics, Grafana, Datadog, New Relic, Coralogix, SigNoz, OpenObserve, Better Stack, Groundcover.
* **Logs & Tracing**: Grafana Loki, VictoriaLogs, Elasticsearch, OpenSearch, Splunk, Tempo, Jaeger, Honeycomb, AWS CloudTrail.
* **Nuvem & Infraestrutura**: Kubernetes, Docker, AWS (EKS, ECS, EC2, RDS, S3, ELB, Lambda), Google Cloud (GCP), Microsoft Azure, Azure Monitor, Proxmox VE, Proxmox Backup Server, Railway, Vercel.
* **Bancos de Dados & Storage**: PostgreSQL, MySQL, Redis, MongoDB Atlas, ClickHouse, Snowflake, BigQuery, Supabase, Azure SQL.
* **Filas & Pipelines de Dados**: Apache Kafka, RabbitMQ, Apache Airflow, Temporal, Dagster, Prefect, Apache Flink, Apache Spark.
* **CI/CD & Controle de Versão**: GitHub, GitLab, Bitbucket, ArgoCD, Jenkins.
* **Gerenciamento de Incidentes**: PagerDuty, Opsgenie, VictorOps/Splunk On-Call, Incident.io, FireHydrant, Blameless.
* **Comunicação & Colaboração**: Slack, Microsoft Teams, Discord, Telegram, Jira, ServiceNow, Linear, ClickUp, Confluence, Google Docs, Notion, Trello, Twilio, WhatsApp, Pushover, Rocket.Chat.

---

## 🖥️ 8. Superfícies de Interação (Interfaces)

1. **Web Console**: Dashboard completo com visualização de incidentes ativos, topologia visual, linha do tempo da investigação, traces de chamadas e painel de aprovação humana de remediações.
2. **CLI Unificada (`ninjasre`)**: Linha de comando para operadores e administradores:
   - `ninjasre investigate`: Dispara uma investigação imediata de um sintoma ou serviço.
   - `ninjasre incidents`: Lista, detalha e gerencia o ciclo de vida dos incidentes.
   - `ninjasre remediation`: Visualiza e aprova/rejeita ações de correção sugeridas.
   - `ninjasre estate`: Descobre e inspeciona ativos da infraestrutura.
   - `ninjasre doctor`: Realiza diagnóstico de saúde da própria plataforma e conectores.
   - `ninjasre autonomy`: Gerencia políticas de autonomia e limites de execução.
3. **Chat Bots**: Suporte a comandos interativos e relatórios em tempo real no Slack, Microsoft Teams, Discord e Telegram.
4. **API REST / SSE**: Documentação OpenAPI gerada automaticamente (`/docs`), permitindo integrar o NinjaSRE a qualquer pipeline existente.

---

## 🚀 9. Guia de Operação e Comandos Úteis

### Subindo em Ambiente Local (Docker Compose)
```bash
# 1. Copiar o arquivo de exemplo de ambiente
cp deploy/compose/.env.example deploy/compose/.env

# 2. Configurar a chave do provedor de LLM e a chave de criptografia do banco
# Ex: ANTHROPIC_API_KEY=sk-... ou OPENAI_API_KEY=sk-...
# Ex: NINJASRE_DATABASE_ENCRYPTION_KEY=$(openssl rand -hex 32)

# 3. Subir os serviços
docker compose -f deploy/compose/docker-compose.yml up -d
```

Acesse:
- **Console Web**: `http://localhost:8421`
- **API REST / Swagger**: `http://localhost:8420/docs`

---

### Comandos de Desenvolvimento e Qualidade (Makefile)

O repositório possui uma suíte de automação completa via `Makefile`:

```bash
make install          # Sincroniza ambiente de desenvolvimento via uv
make test             # Roda a suíte completa de testes unitários e contratuais
make test-postgres    # Executa testes contra banco PostgreSQL real (pgvector + AGE)
make test-synthetic   # Roda o catálogo de cenários sintéticos offline (sem gastar tokens)
make verify           # Portão completo de CI (linter, types, limites de import, contratos)
make preflight        # Valida conectividade com a LLM configurada fazendo chamada real
make backup           # Gera backup completo (relacional, vetorial e grafo)
make restore          # Restaura backup no banco de dados
make docs-serve       # Renderiza e serve o site da documentação localmente
```

---

## 📌 Resumo da Proposta de Valor

O **NinjaSRE** une o poder de raciocínio de Grandes Modelos de Linguagem à disciplina de engenharia de confiabilidade:
- **Não alucina causas**: Cada diagnóstico é amarrado a logs, queries e métricas reais rastreáveis.
- **Não executa comandos destrutivos sem você**: Mudanças exigem aprovação explícita e rollback planejado.
- **Não expõe seus segredos**: O modelo nunca toca em tokens ou dados sensíveis.
- **Não perde o histórico**: Aprende com a memória episódica dos seus próprios incidentes.
- **Privacidade total**: Roda inteiramente na sua infraestrutura.
