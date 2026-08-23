# Tarefas — 053 O cluster Proxmox como o primeiro estate

Depende de 051 (rota de escrita de credencial, superfície de verify). A
renderização do passo do wizard depende do shell do wizard de 052, mas todo
comportamento e rota aqui são testáveis sem ele.

## Phase 1 — privilégios superficiados

- **T-001** Teste falhando: `READ_PRIVILEGES` inclui `SDN.Audit` em `/` e
  `Sys.Syslog` em `/`, cada um com `capabilities` nomeando o que desbloqueia; o
  check de consistência de declaração cobre as adições. Implemente em
  `integrations/proxmox/privileges.py`.
- **T-002** Teste de contrato falhando: `POST /v1/integrations/{name}/verify/report`
  executa o verifier da integração e retorna seu documento de relatório (para
  proxmox: a forma `PrivilegeReport.to_record()` — `read_sufficient`,
  falhas nomeadas com caminhos, `granted_at`); uma integração sem deep verifier
  responde 404 com uma frase. Implemente a rota + linha de permissão.
- **T-003** Teste falhando: um token faltando `Sys.Syslog` produz um relatório
  nomeando-o com seu caminho e efeito — nunca uma falha genérica (aceitação
  1). Dirija através do verifier com uma resposta `/access/permissions`
  encenada.

## Phase 2 — preview de discovery

- **T-004** Teste de contrato falhando: `POST /v1/estate/discovery/preview` executa
  discovery, retorna contagens (nodes, guests, em execução, por-zona uma vez que T-007
  aterrissa), e armazena nada — afirmado pela leitura do estate depois.
  Implemente; linha de rota + permissão (`estate.manage`).
- **T-005** Teste falhando: confirmar a preview registra a fonte de discovery
  proxmox então o scheduled sweep a reclama (semântica de reclamação existente de
  `schedule.py`). Implemente a rota de confirmação ou
  parâmetro.

## Phase 3 — zonas e enriquecimento

- **T-006** Testes falhando para `ZoneMap` em `platform/estate/enrichment.py`:
  CIDR → zona, IP não-combinado → vazio + reportado, CIDRs sobrepostos recusados em
  construção. Implemente.
- **T-007** Testes falhando para a ingestão de infra-cluster
  (`integrations/proxmox/enrichment.py`): lê `zones`/`cts`/`nodes`/
  `services` YAML de uma árvore de fixture moldada como o repositório real,
  valida contra cópias agrupadas de seus JSON Schemas, produz anotações de criticality/
  tier/domain chaveadas por VMID e a `ZoneMap`. Documentos inválidos
  são recusados nomeando cada problema de uma vez (o padrão `InventoryInvalid`).
  Limites (tamanho máximo, entradas máximas) como constantes em
  `config/constants/estate.py`.
- **T-008** Teste falhando: cada valor de string ingerido passa através de
  `platform.estate.attributes.screened`; um arquivo de fixture carregando um
  valor com forma de credencial é recusado nomeando o arquivo, valor não-logado.
- **T-009** Testes falhando para aplicação: anotações apenas anexam a
  recursos que a fonte ao vivo reportou; um VMID presente apenas no arquivo
  se torna uma entrada de divergência, não um recurso; um recurso sem
  criticality declarado não carrega nenhum. Implemente aplicação de enriquecimento no
  pós-passo do sweep.
- **T-010** Teste falhando: o relatório de divergência é armazenado com o
  relatório de sweep e servido (estenda as rotas estate summary/resource), e
  `/resources` marca linhas divergentes (mudança de console, D3 §3). Implemente.

## Phase 4 — topologia

- **T-011** Testes falhando: após um sweep com enriquecimento, o gráfico segura
  nós de zona com edges de membros de guest, e um nó de serviço traefik-domain
  com um edge para seu workload. `GET /v1/topology/{node_id}` para um
  nó hipervisor retorna seus guests. Implemente escrita de gráfico no
  pós-passo de enriquecimento através da porta de topologia existente.

## Phase 5 — a prova moldada como cluster

- **T-012** A fixture HAL9000: um dataset de discovery registrado com 2 nodes,
  57 CTs (49 em execução) e os sete CIDRs de zona; testes afirmam as contagens por-zona
  (infra 25, apps 21, dmz 7, ci 2, backup 1), zero recursos sem zona, e
  cobertura de criticality combinando com o inventário de fixture (aceitação 2–4).
- **T-013** Teste falhando: pare um guest no segundo sweep da fixture — o
  recurso registra uma transição de estado, mesma identidade, sem reescrita
  (aceitação 5; mecanismo existe, isto o fixa ao caminho Proxmox).
- **T-014** Passo do wizard no console (precisa do shell de 052): endpoint +
  token → verify → relatório de privilégio renderizado com falhas e efeitos →
  contagens de preview → confirmar. Testes de componente primeiro; e2e contra o
  plano mock.
- **T-015** `make verify` + `make test-postgres` verde (colunas de estate/
  atributos tocam suites de contrato de persistência). Execute o onboarding real
  contra HAL9000 uma vez; registre contagens e surpresas em deviations.

## Definição de pronto

1. Um token com privilégios insuficientes é recusado no wizard com a
   lista nominal do que está faltando (T-003, T-014).
2. Discovery contra a fixture encontra 2 nodes e 57 containers; contagens
   por-zona combinam com `cts.yaml` (T-012). Os mesmos números confirmados uma
   vez contra o cluster ao vivo, registrados em deviations.
3. Cada recurso carrega uma zona derivada de IP; IPs não-combinados são impossíveis
   de perder (entrada de divergência) e zero neste cluster (T-006/T-012).
4. Criticality do repositório aterrissa em cada recurso declarado;
   recursos apenas-arquivo aparecem como divergência (T-009/T-010).
5. Um container parado é uma transição de estado registrada (T-013).
6. A topologia de um node retorna seus guests; um service domain se resolve para seu
   workload (T-011).

## Dependências em outras features specs_v3

- **051** (dura): rota de credencial, superfície de verify.
- **052** (mole): o shell do wizard para T-014; toda outra tarefa é
  independente de console.
- **Alimenta 054** (ordenação de integração relevante lê o estate descoberto),
  **055** (mapa de zona + domain edges resolvem alertas), **057** (componente →
  mapeamento de workload anda na mesma ingestão de services.yaml), **059** (o
  template de contexto deriva zonas deste estate).
