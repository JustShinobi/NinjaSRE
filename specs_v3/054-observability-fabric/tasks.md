# Tarefas — 054 Conectando os sinais

Depende de 051 (rotas de credencial + deep-verify) e 053 (estate populado,
rota `/verify/report`). Ordenado, um commit cada um, teste-primeiro.

## Phase 1 — verificação que investiga

- **T-001** Testes falhando para `DataWindowProbe` em
  `integrations/_verification/`: leitura em janela autenticada retornando dados
  ⇒ ok; 200-vazio ⇒ `EMPTY_WINDOW` com conselho; negação/irraachável mantêm
  seus estados existentes. Limite de janela é uma constante nomeada. Implemente.
- **T-002** Testes falhando para `ClockSkewProbe`: offset dentro de tolerância ⇒
  ok com valor medido; além ⇒ degradado nomeando o offset; uma fonte
  que não reporta tempo ⇒ inconclusivo, dito assim. Implemente.
- **T-003** Fiação ambos os probes nos seis verifiers de observabilidade, um
  commit por par de integrações, cada um com um teste de transporte encenado
  primeiro. Suite de paridade de integração permanece verde entre ~90.
- **T-004** Teste de contrato falhando: `/v1/integrations/{name}/verify/report`
  para prometheus inclui os resultados de janela e skew; o passo verify do
  wizard e `ninjasre integrations verify` os renderizam (testes de superfície).

## Phase 2 — o mapa de sinais

- **T-005** Testes unitários falhando para `platform/estate/signal_map.py`: um recurso
  LXC com prometheus configurado resolve *pressure* para
  prometheus/pve-exporter chaveado por VMID; *up* resolve para proxmox;
  *logs* para loki/openobserve quando configurado; uma questão sem
  fonte configurada resolve para uma ausência explícita nomeando a integração faltante.
  Conjunto de questão como constantes. Implemente.
- **T-006** Teste de contrato falhando:
  `GET /v1/estate/resources/{resource_id}` carrega o bloco `signals`.
  Implemente; regenere `schema.ts`; tela de detalhe de recurso renderiza o
  bloco (teste de componente).
- **T-007** Teste falhando: a ferramenta Prometheus pressure, dado um
  recurso LXC, emite um seletor pve-exporter contendo o VMID e nenhum
  nome de métrica interno de guest (aceitação 2). Implemente o ponto de
  entrada que consulta o mapa.
- **T-008** Cenário sintético: investigação de LXC memory-pressure deve citar
  série lado-host; ablação com o mapa desativado mostra a diferença.
  Reporte o delta de suite de cenário.

## Phase 3 — ordenação dirigida por estate

- **T-009** Teste falhando: o matcher de catálogo sugere `prometheus` com
  o endereço pre-preenchido quando o estate segura um recurso que combina, e
  sugere nada caso contrário. Implemente em `platform/estate/`; exponha como
  `suggested` em `GET /v1/integrations`.
- **T-010** O passo de integrações do wizard ordena entradas sugeridas primeiro com
  o endpoint pre-preenchido (teste de console); o wizard CLI mostra a mesma ordem.

## Phase 4 — lacunas registradas

- **T-011** Teste falhando: a resposta do catálogo lista `gatus` e `netbox`
  como lacunas conhecidas com razões; tela do catálogo as renderiza acinzentadas com a
  razão. Implemente `KNOWN_GAPS`.

## Phase 5 — contra a stack real

- **T-012** `make verify` verde. Depois, contra HAL9000 (registrado em
  deviations, não no gate): verifique todos os seis contra os endereços reais —
  cada um retorna dados de janela recente; o check de skew reporta offsets medidos;
  o mapa de sinais do recurso AdGuard nomeia pve-exporter para pressure.

## Definição de pronto

1. Seis integrações verificam contra os endereços reais e cada verificação
   retorna dados de uma janela recente, não meramente 200 (T-001/T-003/T-012).
2. Uma query de pressure LXC comprovadamente usa métricas host por VMID e comprovadamente
   não usa métricas internas de guest (T-007, e o cenário T-008).
3. Cada recurso de estate resolve ao menos uma fonte "up" e uma fonte "logs",
   ou nomeia a integração faltante explicitamente (T-005/T-006).
4. Uma fonte cujo relógio está off além de tolerância verifica como degradada com
   o offset medido (T-002).
5. Gatus e NetBox aparecem como lacunas conhecidas com razões escritas na
   resposta de catálogo e tela (T-011).

## Dependências em outras features specs_v3

- **051** (dura): escrita de credencial, base de rota deep-verify.
- **053** (dura): estate populado (tipos, VMIDs, zonas) para o mapa e
  a ordenação; a rota `/verify/report` que introduziu.
- **Alimenta 055**: o mapa de sinais é como a primeira investigação alcança quatro
  fontes; **alimenta 059**: o template de contexto lista as fontes do mapa;
  **alimenta 060**: ferramentas acinzentadas por integração faltante leem os mesmos
  fatos de integração-configurada.
