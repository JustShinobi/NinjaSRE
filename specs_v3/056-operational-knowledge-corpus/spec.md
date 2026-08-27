# 056 — A história escrita

A plataforma promete melhorar a cada investigação. Este cluster chega com dois
anos de operação já escritos, e ignorá-los seria começar do zero por opção.

## O que existe

Em `/root/infra-cluster/docs/`:

| Corpo | Volume | O que é |
|---|---|---|
| `runbooks/` | **54** | Procedimentos. Como recuperar, migrar, auditar, cortar. |
| `postmortem/` | **10** | Falhas reais, com diretórios de evidência ao lado. |
| `adr/` | 3 | Decisões de arquitetura e seus porquês. |
| `analysis/`, `plans/`, `prd/`, `specs/`, `migration/` | — | Contexto de projeto. |

Mais `policies/firewall/` — aliases de datacenter, ipsets, regras de cluster e
perfis por workload. Regra de firewall é conhecimento operacional: metade dos
"não consigo alcançar X" tem resposta ali.

Os postmortems são o material mais valioso, porque cada um é um par
sintoma → causa já resolvido por um humano neste mesmo cluster:

- `2026-07-17-adguard-dns-stall-both-instances.md` e
  `2026-07-20-adguard-dns-recurrence-memcg-oom.md` — a mesma falha duas vezes, a
  segunda com a causa raiz real. Um par assim ensina mais que dez runbooks.
- `2026-07-27-vxlan-overlay-mtu-1450-sobre-underlay-1450.md` — MTU de overlay
  igual ao do underlay. Explica a zona `vk8s` carregar `mtu: 1450` no
  `zones.yaml`.
- `2026-07-28-signoz-validation-clickhouse-system-log-storm.md` — a stack de
  observabilidade derrubando a si mesma.
- `2026-04-24-pve02-fileserver-nfs-hard-mount-stall.md` — hard mount NFS travando
  o nó.

Há também `docs/runbooks/cluster-double-check-queries.md`, que é literalmente uma
lista de consultas de verificação que um operador experiente roda — pronta para
virar detector.

## O que já existe do lado da plataforma

`GET /v1/knowledge/documents`, `/{document_id}`, `GET /v1/memory/search`,
`/memory/stats`, `GET /v1/observations`. Telas `/knowledge` e `/memory` já
renderizam. A permissão `knowledge.write` existe. Falta a ingestão.

## Escopo

### A. Ingestão de um corpus Markdown

Uma origem de conhecimento é um diretório ou repositório com documentos Markdown.
Para cada documento: caminho, título, conteúdo, data de modificação, e uma
classificação — runbook, postmortem, decisão, política.

A classificação vem do caminho, não de um modelo. `docs/runbooks/x.md` é um
runbook. Inferir isso com LLM seria gastar uma chamada para descobrir o que o
diretório já diz.

**Reingestão é idempotente e detecta mudança por conteúdo**, não por horário: um
runbook reescrito é uma versão nova; um `touch` não é nada.

### B. O que um postmortem contribui além do texto

Um postmortem tem estrutura que um runbook não tem: sintoma, o que foi
investigado, causa raiz, correção, e frequentemente recorrência. Extrair esses
campos — na ingestão, uma vez, não a cada busca — torna possível a pergunta que
importa numa investigação: *"este sintoma já aconteceu aqui?"*

Os dois postmortems de DNS do AdGuard são o caso de teste: mesmo sintoma, duas
entradas, a segunda contendo a causa que a primeira não achou. Uma busca por
"AdGuard DNS parou" precisa devolver as duas, na ordem certa, e deixar claro que
a segunda é a que explica.

### C. Ligar conhecimento ao estate

Um runbook sobre AdGuard e o recurso `adguard` (CT 115, zona infra, criticidade
alta) são a mesma coisa vista de dois lados. A ligação é por nome de host e por
domínio — ambos estão no `services.yaml`, e o `tags` de cada workload já traz
`host-adguard.kyo.ninja`.

Ligado, uma investigação sobre um recurso traz o que já se escreveu sobre ele
sem ninguém precisar buscar.

### D. Consultas de verificação viram detectores candidatos

`cluster-double-check-queries.md` é uma lista de verificações que já se sabe
valerem a pena. Esta spec não as transforma em detectores automaticamente —
propõe cada uma como candidata, com o texto de origem, para um humano habilitar.
`POST /v1/detectors/{id}/dry-run` existe justamente para ver o que teria
disparado antes de deixar disparar.

## O que não fazer

- **Não copiar segredo.** O repositório tem `.env.local` e referências a
  Infisical. A ingestão trata apenas Markdown sob `docs/` e YAML sob `policies/`,
  e varre o que ingere em busca do formato de credencial antes de gravar.
- **Não ingerir o repositório inteiro.** São 15.880 arquivos, a maioria estado de
  OpenTofu, lockfiles e `.tmp`. O corpus é `docs/` e `policies/`; o resto é ruído
  caro.
- **Não tratar documento como verdade sobre o presente.** Um runbook descreve o
  que era verdade quando foi escrito. O estate diz o que é verdade agora. Quando
  discordam, o estate ganha e a discordância é reportável.

## Aceitação

1. Os 54 runbooks, 10 postmortems e 3 ADRs são ingeridos e buscáveis, com
   classificação derivada do caminho.
2. Uma busca por "AdGuard DNS" devolve os dois postmortems e o runbook de
   recuperação, com o de julho/20 identificável como o que traz a causa raiz.
3. Reingerir sem mudança não cria versão nova; reingerir após edição cria.
4. Recursos do estate resolvem para os documentos que os mencionam, por hostname
   ou domínio.
5. Um teste tenta ingerir um arquivo com credencial no formato conhecido e a
   ingestão o recusa nomeando o arquivo, sem registrar o valor.
6. As consultas de verificação aparecem como detectores candidatos, desabilitados,
   com o trecho de origem.
