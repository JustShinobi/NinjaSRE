# Tarefas — 055 Fechando o loop

Depende de 053 (estate + mapa de zona + edges service→workload) e 054 (mapa de
sinais). Ordenado, um commit cada um, teste-primeiro.

## Phase 1 — alerta → recurso

- **T-001** Testes unitários falhando para
  `platform/estate/alert_resolution.py`: IP de label instance resolve para o
  recurso que segura aquele IP primário; label `vmid` resolve o guest
  diretamente; um domain de target blackbox resolve através do
  edge service→workload; um target não-combinado produz um registro `UnresolvedAlertTarget`,
  nunca `None`-e-esqueça. Implemente.
- **T-002** Teste falhando: o handler de webhook armazena a resolução no
  incidente e passa o recurso para o contexto de investigação; um
  target não resolvido é armazenado com o incidente e visível via a API.
  Implemente a fiação do handler (`gateway/webhooks/router.py::handle`).
- **T-003** Console: targets não-resolvidos renderizados ao lado das
  entradas de divergência de 053 (teste de componente primeiro).

## Phase 2 — agrupamento

- **T-004** Testes falhando: o adapter do Alertmanager carrega `groupKey`; o
  fingerprint prefere chave de grupo + recurso resolvido quando presente e cai
  de volta para a composição atual; fixtures construídas a partir das formas de
  payload AdGuard-OOM e ClickHouse-storm produzem uma investigação com
  deliveries ligadas. Implemente no adapter e `gateway/webhooks/dedup.py`.
- **T-005** Teste falhando pinando o comportamento existente para a
  forma do Alertmanager: `firing` depois `resolved` para um grupo = uma
  investigação, a resolução registrada (aceitação 3).

## Phase 3 — o painel de ingress pronto para colar

- **T-006** Teste falhando: uma nova permissão mínima webhook-delivery existe,
  é concedível a um machine token via `POST /identity/tokens`, e concede
  nada mais (um token segurando apenas ela não pode ler `/v1/runs`).
- **T-007** Painel do console: URL, emissão de token com segredo show-once, e
  o payload esperado nomeado per fonte; testes de componente primeiro. Vive na
  superfície de integrações/ingress até que 062 a dê a tela Dados.

## Phase 4 — a primeira investigação

- **T-008** Cenário sintético: um alerta de container-pressure contra o
  estate de fixture produz uma conclusão cuja evidência abrange proxmox +
  prometheus(pve-exporter, chaveado por VMID) + loki, cada afirmação carregando sua
  origem. Confirme que falha antes da fiação (o cenário é o teste
  falhando), depois fiação o que quer que a falha nomeie — em módulos de 053/054, não
  em prompts. Reporte o delta de suite de cenário e a ablação de resolução.
- **T-009** Teste falhando para a postura dry-run: uma execução encenada atingindo uma
  conclusão de classe de remediação registra uma proposta, executa nenhuma
  capacidade com efeito colateral, e o registro "teria feito" é legível
  (aceitação 5).
- **T-010** Teste falhando: o caminho inteiro se reproduz —
  `GET /v1/runs/{run_id}/replay` reconstrói a investigação T-008 de
  seus eventos registrados (aceitação 6; rota existe, isto pina o novo
  conteúdo).

## Phase 5 — validação ao vivo (deviations, não gate)

- **T-011** `make verify` verde. Contra HAL9000: aponte o Alertmanager do cluster
  para o deployment (config aplicado via `infra-cluster`), dispare
  um alerta de teste, e registre em deviations: tempo de disparo para criação de run
  (< 1 minuto — aceitação 1), o recurso resolvido, as fontes de evidência
  no relatório resultante, e a saída de replay.

## Definição de pronto

1. Um alerta do Alertmanager deliberadamente disparado alcança o deployment e
   cria uma investigação em um minuto (T-011, medido e registrado).
2. O alerta se resolve para o recurso correto de estate; um target desconhecido
   produz um achado armazenado e visível (T-001/T-002/T-003).
3. `firing` + `resolved` de um grupo ⇒ uma investigação (T-004/T-005).
4. A investigação resultante cita ≥3 fontes distintas com atribuição
   por-afirmação (T-008 no gate; T-011 ao vivo).
5. Com dry-run ligado, remediação existe apenas como proposta registrada (T-009).
6. A investigação é reproduzível via a rota de replay (T-010).

## Dependências em outras features specs_v3

- **053** (dura): mapa de zona, atributos de IP-primária, edges service→workload.
- **054** (dura): mapa de sinais dirigindo coleta multi-fonte.
- **056** (mole): a quarta fonte ("o que foi escrito sobre este
  recurso") se junta ao cenário uma vez que o corpus aterrissa; T-008 é escrito para
  passar em três fontes e estender para quatro.
- **058** (para frente): superfície de edição de dry-run; aqui é afirmada, não
  editada. **062** absorve o painel de T-007 na tela Dados.
