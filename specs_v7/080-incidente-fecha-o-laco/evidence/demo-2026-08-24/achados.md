# Achados da demo — 2026-08-24

CT122 (`redis`, `pve01`) parada às **10:26:29Z**. Cadeia observada de ponta a
ponta contra staging real e hipervisor real.

## A cadeia, com horários

| estação | o que aconteceu | quando |
|---|---|---|
| — | `pct stop 122` | 10:26:29Z |
| E1 | `ProxmoxGuestStopped` ativa (`activeAt`) | 10:27:34Z |
| E1 | dispara depois do `for: 2m` | 10:29:34Z |
| E2 | `POST /webhooks/alertmanager` → **202** | 10:29:45Z |
| E3 | incidente `inc_05328c58ca88676b` aberto | 10:29:45Z |
| E4 | investigação gravada (`run_ids` preenchido) | 10:29:45Z |

**Cinco incidentes**, não um. Quatro regras já cobriam o mesmo contêiner pelo
lado do serviço e dispararam *antes* da regra de convidado:
`DatabaseTcpProbeFailed` (10:28:15), `GatusEndpointHealthcheckFailed`
(10:28:30), `InstanceDown` e `RedisExporterDown` (10:29:45).

## O que passou

- **Identidade endereçável (020).** `inc_05328c58ca88676b` — curta, estável,
  sem `%3A`, `%40` ou `%2B` na barra de endereço.
- **Nenhum painel diz que não pôde preencher.**
- **O chip de investigação diz o estado real** — *Investigation running*, não
  *Unknown*.
- **`Proposed action` diz "Nothing proposed yet"** com a frase completa, que é
  o estado correto enquanto a investigação não concluiu.
- **A entrega foi autenticada e a tela diz por quem** — *"the delivery was
  authenticated by alertmanager-delivery"*.
- **Os rótulos do alerta aparecem literais**, sem reescrita.

## Achado 1 — o título é o nome do alerta, não uma frase

A tela mostra `ProxmoxGuestStopped` como título do incidente. O roteiro exige
uma frase e nomeia `alert:alertmanager:9f8e…` como defeito. Isto não é aquilo —
não é o identificador composto —, mas também não é uma frase.

A frase existe: `subjects[0].detail` guarda *"Redis Exporter indisponível"* no
incidente irmão, e a descrição da regra que escrevi produz *"redis (lxc/122)
estava em execução no nó pve01 e parou."* Nada disso chega ao título.

## Achado 2 — o cabeçalho atribui o incidente ao nó errado

O cabeçalho diz **`node pve02`**. O corpo do alerta, na mesma tela, diz
**`node=pve01`**. A CT122 roda no `pve01`; `192.168.68.159` é o `pve02`, que é
apenas onde o `pve-exporter` está hospedado.

O cabeçalho está lendo `instance` — o endereço de quem *raspou* a métrica — e
apresentando-o como o nó do sujeito. Um operador que leia o cabeçalho e abra
uma sessão no nó indicado vai ao nó errado, e a mesma tela contém a informação
correta três linhas abaixo.

Isto é da mesma família dos defeitos que esta onda vem fechando: um campo que
afirma com confiança um fato que ele não mediu.

## Observação — o custo não foi gravado

O painel da investigação diz `5 steps · 23s · Not recorded`. A duração e os
passos estão lá; o custo não. Vale confrontar com o que a 001 promete gravar.

### 3. ~~A descoberta não resolve o nó do convidado~~ — **este achado estava errado**

Eu escrevi que todo `native_id` sai como `lxc/HAL9000/unknown/122` porque o
segmento do nó fica sem resolver, e apontei isso como provável causa do achado
anterior. **As duas coisas estão erradas.**

`integrations/proxmox/identity.py` diz o que aquele formato é:

    guest_identity  ->  {kind}/{cluster}/{created_at or "unknown"}/{vmid}
    node_identity   ->  node/{cluster}/{node}

O terceiro segmento é o **instante de criação**, não o nó, e `unknown` é o valor
documentado para quando o provedor não deu essa hora. O nó é excluído de
propósito: a identidade de um convidado tem de sobreviver a uma migração entre
nós, enquanto a de um nó é o próprio nome — renomear um nó não é uma operação,
é removê-lo do cluster e devolvê-lo.

Eu li um formato que não conhecia, vi uma palavra que parecia uma falta, e
construí uma causa em cima dela. Quem apurou foi um verificador que abriu o
arquivo em vez de repetir o que três leituras anteriores já vinham repetindo.

**O achado 2 continua de pé** — o cabeçalho nomeia o host do exportador, e isso
foi provado pelo contraste entre as duas travessias, não por esta dedução. O que
cai é a causa que lhe atribuí.

Fica no lugar um achado menor e real: o instante de criação **está** ausente em
todos os convidados descobertos. Pelo desenho da própria função, um convidado
que ganhe esse campo depois passa a ser "visivelmente uma identidade diferente",
o que significa que uma descoberta futura pode duplicar o que já existe.

