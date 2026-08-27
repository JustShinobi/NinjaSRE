# Plano — 054 Conectando os sinais

## O que existe, verificado

- As seis integrações (`prometheus`, `alertmanager`, `grafana`, `loki`,
  `openobserve`, `signoz`) cada uma envia os sete artefatos; seus verifiers
  seguem um frame (`integrations/_verification/framework.py::Connectivity` +
  `PermissionProbe` por permissão, ex.
  `integrations/prometheus/verifier.py::PrometheusVerifier` — conectividade é
  `/api/v1/status/buildinfo`, permissões probed pela leitura mais barata, cada
  falha traduzida para conselho de operador em `_ADVICE`).
- `POST /v1/integrations/{name}/verify` é shallow (credencial presente/
  atual/decriptável); 053 adiciona `POST /v1/integrations/{name}/verify/report`
  para o documento deep verifier. 054 constrói naquela rota, não uma nova.
- O `guest_pressure` tool da integração Proxmox já lê métricas lado-host
  por VMID; `clock_skew` existe como uma ferramenta Proxmox. Nenhuma regra existe
  ainda para o caminho sourced por Prometheus.
- `platform/persistence/ports/signal_store.py` segura janelas de sinal do detector;
  é **não** uma metrics store e permanece assim (o "nenhuma segunda
  time-series store" da spec já é a arquitetura).

## Escopo A — ordenação dirigida por estate no wizard

O passo de integrations (052) ganha uma ordenação de relevância derivada do
estate que 053 descobriu: um recurso cujo nome de exibição ou tags combinam com
uma integração no catálogo (`prometheus` CT em zona infra → integração `prometheus`)
é oferecido primeiro, com o endpoint pre-preenchido do IP primário do
recurso e da porta padrão declarada da integração.

**Decisão — a derivação vive no lado do servidor**, como um campo na
resposta de catálogo de integrações (`suggested: {address, from_resource}` por
entrada, computado por um pequeno matcher em `platform/estate/`), não no
console. O console precisaria do estate *e* do catálogo *e* da
regra de combinação; o wizard CLI beneficia da mesma ordenação grátis, e
duas superfícies computando relevância diferentemente é a falha de duas-respostas
que a constituição continua advertindo. O matcher é baseado em nome/tag e total —
nenhuma chamada LLM, nenhuma adivinhação: uma não-combinação simplesmente mantém
a ordem do catálogo.

## Escopo B — o mapa de sinais

Nova maquinaria de plataforma: `platform/estate/signal_map.py`. Para um recurso,
qual integração configurada responde cada uma das seis questões (up? /
pressure? / logs? / traces? / firing? / dashboards?).

- Derivado, não armazenado por recurso: do tipo e zona do recurso, o
  conjunto de integrações *configuradas e verificadas*, e regras por-questão. As
  regras são dados (`config/constants/observation.py` nomeia o conjunto de questão;
  o mapeamento é enviado como padrões e é configuração sob a árvore de 058
  depois — esta feature envia a derivação e a superfície de leitura).
- Servido como parte do detalhe do recurso
  (`GET /v1/estate/resources/{resource_id}` ganha um bloco `signals`: questão
  → integração → chaveado-por), e consumido pela seleção de capacidade então uma
  investigação pergunta à fonte que o mapa nomeia.
- **A regra LXC é uma regra do mapa, dita uma vez**: para um recurso do tipo
  container LXC, a questão *pressure* se resolve para Prometheus **via
  série pve-exporter chaveada por VMID**, nunca a coletores internos de guest.
  A entrada do mapa carrega a chave (`vmid`) então a ferramenta de query constrói o
  seletor certo. As ferramentas Prometheus metric ganham um ponto de
  entrada com escopo de recurso que consulta o mapa — o teste prova que uma
  query de pressure LXC contém o seletor pve-exporter chaveado por VMID e nenhum
  nome de métrica interno de guest (aceitação 2).

**Decisão — o mapa é o mecanismo, a postmortem é a fixture.** A
classe memcg-OOM do AdGuard do próprio histórico do cluster se torna um
cenário sintético: uma investigação de um container LXC sob pressão de memória deve
citar a série lado-host. Isso aterrissa em `tests/synthetic/` então a regra é
medida, não afirmada (postura do Artigo VII).

## Escopo C — verificação que investiga

O relatório deep verifier (053's `/verify/report`) é estendido para
integrações de observabilidade com duas novas famílias de probe em
`integrations/_verification/`:

- **`DataWindowProbe`**: uma query autenticada sobre uma janela recente
  (constante `VERIFY_WINDOW_MINUTES` em `config/constants/`) que deve retornar
  ao menos uma série/linha. 200-com-vazio é reportado como seu próprio estado —
  `EMPTY_WINDOW`, distinto de negado e de irraachável — com conselho
  ("Prometheus respondeu e não segura nada pelos últimos N minutos; checa
  scrape targets"). Implementado por integração pela leitura em janela mais barata
  que seu cliente já tem (`query_metric`, Loki `query_range`, …).
- **`ClockSkewProbe`**: compara o tempo reportado da fonte (de headers de resposta
  ou do status endpoint do vendor) contra o relógio da plataforma;
  além de `CLOCK_SKEW_TOLERANCE_SECONDS` a integração é reportada
  **degradada** com o offset medido (aceitação 4). Mesma rationale que a
  ferramenta Proxmox `clock_skew` documenta; a constante de tolerância é compartilhada.

Ambos estendem a forma existente `probes()`/report então a CLI, a
rota deep-verify, e o passo verify do wizard todos a renderizam sem novo plumbing.
A rota shallow verify permanece barata e inalterada.

## Escopo D — Gatus e NetBox como lacunas registradas

Ambas as decisões são "não construir", e a spec quer a lacuna *registrada com
sua razão*. **Decisão — lacunas conhecidas são dados no catálogo de
integrações**, não prosa: `integrations/_catalogue/` ganha uma pequena
declaração `KNOWN_GAPS` (nome, o que responderia, por que não é construído,
o que mudaria a decisão), servida em `GET /v1/integrations` e mostrada
pela tela do catálogo acinzentada com a razão. Isto é o que torna
aceitação 5 observável, e é onde a próxima conversa "deveríamos construir X"
começa de.

## O que esta feature NÃO faz

- Sem webhook ingress, sem resolução de alerta-para-recurso (055).
- Sem mudança à stack de observabilidade do cluster; NinjaSRE apenas lê.
- Sem ingestão de métrica em NinjaSRE — o mapa de sinais aponta para origens.
- Sem instrumentação OTLP de aplicações.
- O *editor* de mapa de sinais não é construído; o mapa é derivado. Overrides via
  a árvore de config são 058-adjacentes e aterram apenas se a validação mostra uma
  falha de derivação.

## Verificação de constituição

- **I** — cada afirmação de verify carrega o que foi chamado e o que voltou
  (padrão `probe_description` estendido para os novos probes); uma janela vazia
  é nomeada, nunca passada como saudável.
- **II** — tamanho de janela, tolerância de skew, orçamentos de probe são constantes nomeadas.
- **III/IV** — probes somente-leitura através do transporte de proxy; clients não seguram
  credencial (padrão `_client` retido).
- **VI/VII** — a regra LXC é medida por um cenário sintético com o
  mecanismo capaz de ser ablated (mapa on/off), então sua contribuição é um número.
- **VIII** — famílias de probe em `integrations/_verification/` (tier 2), mapa em
  `platform/estate/` (tier 3), constantes em tier 4; sem imports para cima.
- **XII** — testes falhando por probe e por regra de mapa antes de implementação;
  delta de suite de cenário reportado (esperado: o novo cenário, sem regressão).

## Raio de impacto

`integrations/_verification/framework.py` (compartilhado por ~90 integrações — as
novas famílias de probe são aditivas, suite de paridade deve permanecer verde);
`gateway/http/routes/integrations.py` (forma de resposta do catálogo — console
regeneração de `schema.ts`); rota de detalhe de recurso e tela; seleção de
capacidade para as ferramentas Prometheus.
