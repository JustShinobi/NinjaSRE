# Plano — 055 Fechando o loop

## O que existe, verificado — mais do que a spec assume

`gateway/webhooks/router.py::handle` já implementa a maioria do pipeline de
ingress: limite de payload (`WEBHOOK_MAX_PAYLOAD_BYTES`), roteamento de verifier
per-team (`WebhookSourceConfig` — "qualquer verifier que verifique a requisição
decide o team"), idempotência de delivery (`webhook_idempotency`), load shedding,
normalização (`adapter_for(profile.source).normalise(RawAlert(...))`),
deduplicação de fingerprint (`gateway/webhooks/dedup.py` — fonte + componentes
normalizados + nome de alerta, dentro de `ALERT_DEDUP_WINDOW_SECONDS`, **ligado nunca
dropado**), manuseio de resolução (`alert.resolved` fecha em vez de abrir uma
segunda run), levantamento de incidente, `start_investigation`, e
`IncidentLifecycle.attach_run`.

Então **aceitação 3 (firing→resolved é um evento) é substancialmente comportamento
existente**; a tarefa é um teste pinando para a forma de payload do Alertmanager,
mais o refinamento de group-key abaixo. As peças genuinamente faltantes:

1. nada resolve um alerta para um **recurso de estate**;
2. nada diz ao operador o que colar em Alertmanager;
3. nenhuma prova que um alerta real produz uma investigação multi-fonte;
4. a postura dry-run não é afirmada end-to-end.

## Escopo A — o que o operador cola em Alertmanager

Um painel (console; 062 depois o absorve na tela Dados) que renderiza,
per webhook source: a URL (`POST /webhooks/alertmanager` no endereço do
deployment), o machine token, e a forma de payload esperada. O token é
emitido via `POST /identity/tokens` existente com uma **nova permissão mínima**
para entrega de webhook apenas — receber um alerta não deve ser
permissão para ler qualquer coisa. **Decisão**: as rotas de webhook são declaradas
com configuração de verifier per-fonte (a costura `WebhookSourceConfig`); o painel
dirija a emissão de token existente e mostra o segredo uma vez, no padrão
show-once de 058 (a docstring `DurableCredentialView` em
`gateway/http/routes/first_run.py` a define: "retornado exatamente uma vez… a store
segura um hash"). A própria config de receiver do Alertmanager é escrita pelo
operador em `infra-cluster` e aplicada por `./infra` — NinjaSRE renderiza o
snippet, nunca escreve para a stack (a regra 054).

## Escopo B — alerta → recurso

Novo módulo `platform/estate/alert_resolution.py`, função pura de um
`NormalisedAlert` + o estate para uma resolução:

- label `instance`/`host` → IP → `ZoneMap.zone_for` (053) → recurso por
  atributo de IP-primária;
- label `vmid` (alertas pve-exporter) → lookup direto de guest por native id;
- blackbox `target` → domain → workload via o edge de topologia service→workload
  que 053 construiu de `services.yaml`;
- **sem match ⇒ um achado, não um descarte**: um registro `UnresolvedAlertTarget`
  armazenado com o incidente e superficiado em `/resources` ao lado das
  entradas de divergência de 053 — mesmo princípio, mesma costura de renderização.

O resultado de resolução desce para o contexto inicial da investigação
(caminho `context`/`alert_id` de `start_investigation`) então o agent começa com
a identidade do recurso, e para o registro de incidente então `/incidents` pode ligar
o recurso.

**Decisão — resolução é lado-estate (tier 3), não lado-webhook (tier 1)**:
o handler de webhook a chama, mas as regras de roteamento de 062 e os detectors
precisam da mesma função, e tier 1 não deve possuir lógica que consumidores tier 2/3 querem.

## Escopo C — refinamento de agrupamento

O fingerprint existente usa fonte + nome de alerta + componentes. Alertmanager
envia seu próprio `groupKey`; o adapter é estendido para carregá-lo e o
fingerprint para preferi-lo quando presente (chave de grupo + recurso resolvido), janela
inalterada. As duas postmortems do cluster (recorrência OOM do AdGuard, storm de logs do
ClickHouse) se tornam os payloads de fixture: um storm de notificações de um
grupo dentro da janela produz uma investigação com deliveries ligadas.

## Escopo D — a primeira investigação real

O objetivo mensurável: um alerta produz uma investigação citando evidência de
≥3 fontes distintas, cada afirmação atribuída. Mecanismo, não prompt:

- o contexto de alerta carrega o recurso resolvido;
- o mapa de sinais (054) diz à seleção de capacidade quais integrações respondem
  qual questão para esse recurso;
- a investigação coleta estado de guest (proxmox), métricas host por VMID
  (prometheus), linhas de log para a janela (loki/openobserve), e — quando 056
  tiver aterrado — escrita prévia sobre o recurso.

Comprovado duas vezes: um **cenário sintético** em `tests/synthetic/` (modelo
encenado + respostas de integração registradas, afirmando que o conjunto de evidência
da conclusão abrange três fontes e cada afirmação carrega uma origem — Artigo I é
checkável porque entradas de evidência carregam fontes), e uma vez **ao vivo** contra
HAL9000 com um alerta deliberadamente disparado, registrado em deviations com a
saída `GET /v1/runs/{run_id}/replay` (aceitação 6 — a rota replay
existe).

Se o cenário sintético não consegue alcançar três fontes, o defeito é arquivado
contra o mapa ou estate de 053/054 — esta feature não faz patch em prompts para
compensar (a spec diz exatamente isto; o plano a torna a regra de trabalho).

## Escopo E — propor, nunca agir

O dry-run da política de autonomy é o mecanismo existente
(`PolicySet.dry_run`, resolução honrando-o — `platform/autonomy/`). Esta
feature afirma a postura end-to-end: com dry-run ligado, uma conclusão
de classe de remediação produz uma proposta registrada (o ledger de approvals/
remediação) e comprovadamente executa nada — o teste dirija uma investigação
encenada a uma proposta de remediação e afirme que nenhuma capacidade com
efeito colateral executou e o registro "teria feito" existe. Nenhum novo
mecanismo; 058 constrói o editor, 060 a leitura.

## O que esta feature NÃO faz

- Sem execução de remediação, sem integração de chat, sem
  investigações agendadas.
- Sem *regras* de roteamento (qual team, open-vs-log-vs-discard) — 062. Aqui todo
  delivery verificado segue o caminho um-team-per-verifier existente.
- Sem tela de observabilidade de ingress (último delivery, contagens, rejeições) — 062;
  esta feature armazena o que aquela tela precisará (registros de delivery já
  existem via idempotência/auditoria; lacunas são para 062 fechar).

## Verificação de constituição

- **I** — o teste de citação multi-fonte afirma entradas de evidência com
  origens; um alvo não resolvido é um achado armazenado.
- **II** — janela de dedup, limite de payload, shedding já são constantes nomeadas;
  nada novo sem limites.
- **III** — dry-run afirmado; o caminho de proposta é o único caminho.
- **IV** — tokens de webhook são machine tokens, hashed em repouso; mostrado uma vez.
- **VII** — o cenário aterrissa na suite sintética; o mecanismo de resolução
  é ablatable (resolução desligada ⇒ o cenário mostra a
  diferença); delta de suite de cenário reportado.
- **VIII** — resolução em `platform/estate/`, handler permanece um chamador.
- **XII** — fixtures das formas de alerta das postmortems reais; execução ao vivo é
  deviations-registrada, nunca um gate.
