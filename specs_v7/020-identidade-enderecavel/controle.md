# Controle — 020-identidade-enderecavel

Estado verificado contra o código mergeado em `master`, não contra intenção.

**Como este arquivo foi escrito.** A feature rodou numa worktree isolada, onde
`specs_v7/` não existe (está no `.git/info/exclude`). O implementer entregou
este texto no relatório final e o orquestrador o gravou aqui após o merge do
slot.

Verificação independente do `spec-verifier` em contexto limpo: **pendente**.
A validação determinística e a de staging passaram, rodadas pelo orquestrador.
Em 2026-08-24, uma auditoria à parte confrontou as seis tarefas que tinham
ficado desmarcadas contra o código e o staging real — ver "Auditoria de
2026-08-24" ao final deste arquivo — e a onda está agora em 63 de 65, com as
duas que continuam desmarcadas justificadas em "O que fica pendente" abaixo.

## Peça | Estado | Detalhe

| Peça | Estado | Detalhe |
|---|---|---|
| Forma pública derivada | FEITO | `platform/persistence/ports/incident_store.py` — prefixo mais dezesseis hexadecimais, derivada do identificador interno |
| Campo obrigatório no incidente | FEITO | sem default: um incidente sem endereço não é construível |
| Unicidade por organização | FEITO | índice único `(org_id, public_id)` — colisão vira escrita falha, nunca "abriu o incidente errado" |
| Busca pela forma pública | FEITO | fake e Postgres |
| Derivação ao abrir o incidente | FEITO | `platform/incidents/lifecycle.py` |
| As duas grafias resolvem | FEITO | `platform/incidents/service.py` — mesma resolução para detalhe, fechamento e supressão |
| Ausência é nomeada, não é erro de servidor | FEITO | teste de contrato próprio |
| Contrato de leitura carrega o endereço | FEITO | `gateway/http/routes/incidents.py` — listagem e detalhe |
| Migração com backfill, reversível | FEITO | `0017_incident_public_id` (re-parenteada no merge — ver adiante); importa a função de derivação em vez de reimplementá-la; ida e volta agora exercitadas contra PostgreSQL real por `tests/contract/persistence/test_incident_public_id_migration.py` (auditoria de 2026-08-24) |
| **Decodificação única na borda** | FEITO | `console/src/shell/route-params.ts`, aplicado às quatro rotas dinâmicas reais; a dupla codificação em `console/src/lib/api.ts` documentada como invariante |
| Título e aba nunca são identificador | FEITO | `console/src/surfaces/screens/incident-detail.tsx` |
| Leitura falhada não afirma negativo | FEITO | o chip de investigação é suprimido em vez de afirmar ausência |
| Quatro superfícies usam o endereço, nenhuma codifica | FEITO | lista, dashboard (duas ocorrências), busca e detalhe de run |
| Rotas respondem pelos nomes | FEITO | `/investigations` → `/runs`, `/setup` → `/first-run`; tabela renomeada para o que ela é |
| Acceptance spec | FEITO | `console/tests/e2e/020-identidade-enderecavel.acceptance.spec.ts` — dezesseis alegações, dezesseis testes, verdes; doze alegações staging-safe confirmadas de verdade contra `https://stg-ninjasre.lan.kyo.ninja` na auditoria de 2026-08-24 (ver seção própria) |
| Dataset simulado **gerado**, não editado à mão | FEITO | `tools/mockplane/capture/projection.py` — o endereço é derivado na construção e o registro de detalhe é chaveado por ele |
| Cobertura do console | FEITO | 90,03% de ramificações, acima do limiar |
| Gate completo do console | FEITO | `console_gate all` exit 0, incluindo o e2e do projeto inteiro |

## A conta da allowlist transversal: 10 → 8

Duas entradas caíram, ambas de `/incidents/{id}`, e ambas confirmadas por
execução real com a entrada removida:

- **identificador como nome** — o identificador composto e percent-encoded
  deixou de chegar onde a tela põe título;
- **afirmação negativa** — a tela deixou de afirmar um negativo a partir de uma
  leitura que falhou.

A terceira daquela rota, **dois placeholders**, continua e continua vermelha —
ela depende de uma leitura de painel que falha, não do formato do identificador.
Essa assimetria é a prova de que o cenário violador não foi enfraquecido: se as
três tivessem sumido juntas, o dataset teria sido maquiado em vez de o produto
ter sido consertado.

**Estado final não é o alvo, e isto fica registrado**: a onda quer um chip que
*diga que não sabe*, não um chip ausente. Suprimir é melhor que mentir e pior
que dizer a verdade. Transformar a ausência em "estado desconhecido" explícito é
da feature de fonte-por-fato, que precisará manter esta regra verde ao fazer a
troca.

## Ressalva de honestidade sobre a ordem

O backend foi implementado **antes** de o acceptance spec ser escrito, contra a
ordem que a onda exige. Consequência real: as primeiras alegações não podiam
ficar vermelhas contra a árvore original, porque o backend já resolvia as duas
grafias. O vermelho documentado é contra a árvore com **backend corrigido e
console intocado** — prova válida do defeito do console, mas não prova contra a
árvore intacta. O implementer declarou isto por conta própria.

O acceptance spec entrou como commit próprio antes dos commits de tela, de modo
que o vermelho-primeiro do console é auditável no histórico.

## O que fica pendente, nomeado, não escondido

1. ~~Migração não exercitada contra PostgreSQL real por esta feature.~~
   **Resolvido na auditoria de 2026-08-24** — ver "Auditoria de 2026-08-24"
   abaixo. `tests/contract/persistence/test_incident_public_id_migration.py`
   agora exercita a migração, ida e volta, contra PostgreSQL real, com dados
   gravados na forma exata que a revisão anterior deixou a tabela.
2. **Fechamento e supressão** resolvem as duas grafias pela mesma função do
   detalhe, mas sem teste de contrato dedicado além do que o teste do detalhe
   cobre por construção compartilhada.
3. **Verificação independente [do `spec-verifier` em contexto limpo] ainda não
   rodou** sobre esta feature. A auditoria de 2026-08-24, abaixo, confrontou as
   seis tarefas que tinham ficado desmarcadas contra o código e o staging real,
   mas não é o mesmo processo que o `spec-verifier` corre — as duas coisas não
   devem ser confundidas.
4. **T002 e T057 continuam desmarcadas, e continuam corretas desmarcadas.**
   Nenhuma das duas é alcançável por quem só tem a credencial de operador do
   console: as cinco consultas de evidência da migração são SQL cru contra
   `ninjasre-stg-db` (`10.20.20.54`), e essa credencial não está em lugar
   nenhum que esta auditoria tenha acesso — só `NINJASRE_STAGING_URL`,
   `NINJASRE_STAGING_USERNAME` e `NINJASRE_STAGING_CREDENTIAL` (a senha da
   conta web) estão no `.env` da raiz. Aplicar a migração (T057) seria também
   uma escrita no staging compartilhado, explicitamente fora do que esta
   auditoria pode fazer. E a captura "antes" que T002 pede não existe mais
   para ser capturada: a evidência ao vivo coletada em T058/T059 (endereço
   curto `inc_…` já servido, formulário público já presente na listagem)
   mostra que a migração **já tinha rodado** contra o staging antes desta
   sessão começar — o "antes" que T002 precisaria já não é reconstituível por
   leitura nenhuma.

## Descobertas registradas para quem mexer nisto depois

- O plano simulado resolve uma resposta gravada por correspondência **exata** do
  argumento, sem decodificar nem tentar variantes: uma fixture de detalhe de
  incidente precisa ser chaveada pela forma pública, ou o console corrigido
  recebe "não encontrado" para tudo.
- **A ordem dos registros num arquivo de fixture não é estável.** A correção do
  gerador trocou a chave de ordenação por um digest, e dois arquivos committed
  assumiam "o primeiro registro é o incidente investigado" — suposição que nunca
  foi verdadeira, só estável por acidente. Ambos foram corrigidos para achar o
  incidente pela propriedade que o define. Nada deve depender daquela ordem.
- O gate completo do console roda verificação de formatação além de lint,
  tipos e testes; rodar só os três deixa passar formatação fora do padrão.

## Reconciliação de `tasks.md`

Os marcadores **não foram marcados pelo implementer**: ele rodou em worktree,
onde este diretório não existe. Foram reconciliados pelo orquestrador contra o
relatório, o código e os gates, e as tarefas de validação em staging ficaram
desmarcadas quando dependem de trabalho que é do orquestrador.

## Auditoria de 2026-08-24 — as seis tarefas que ficaram desmarcadas

A onda estava em 59 de 65. Seis tarefas continuavam sem marca e sem explicação
ao lado: T002, T025, T026, T057, T058, T059. Cada uma foi confrontada contra o
código e, onde fazia sentido, contra o staging real — nunca contra a leitura
do próprio `tasks.md`. Quatro viraram FEITO com prova nova; duas continuam
desmarcadas, e a razão de cada uma está acima, em "O que fica pendente".

**T025 e T026 — a migração exercitada contra PostgreSQL real.** Não existia
nenhum teste, em lugar nenhum do repositório, que aplicasse a revisão
`0017_incident_public_id` contra um Postgres de verdade com incidentes já
gravados na forma anterior. `tests/contract/persistence/test_incident_public_id_migration.py`
fecha essa lacuna com dois testes, seguindo o padrão já estabelecido em
`tests/contract/persistence/test_operations.py` (`downgrade_to`/`upgrade_to_head`
sobre o `gateway` fixture parametrizado):

- `test_the_migration_addresses_every_pre_existing_incident_and_reverses_cleanly`
  — desce o banco até `0016_incident_run_ids_index` (a revisão anterior, sem
  `public_id`), grava três incidentes com `INSERT` cru exatamente na forma que
  aquela revisão deixou a tabela — `alert:alertmanager:…@…` como `incident_id`,
  nenhuma coluna nova —, sobe para `head`, e confere: toda linha ganhou forma
  pública, nenhuma se repete dentro da organização, o total de linhas não
  mudou, e nenhum `incident_id` mudou. Desce de novo e confere que a coluna e o
  índice somem, e que os três incidentes continuam lá pelo mesmo `incident_id`.
  Termina subindo para `head` outra vez, para não deixar o fixture compartilhado
  num esquema que os outros testes do diretório não esperam.
- `test_the_backfilled_value_matches_the_codes_own_derivation` — o mesmo
  cenário, mas a asserção é `row.public_id == public_incident_id(row.incident_id)`
  para cada linha: o valor que a migração gravou contra o valor que a função do
  código deriva, sobre um Postgres real, não por leitura do código-fonte.

Rodados com `uv run pytest tests/contract/persistence/test_incident_public_id_migration.py --postgres -v`:
`2 passed, 2 skipped` (o `skipped` é a variante `[fakes]` do mesmo teste — não
há Alembic contra um banco em memória, então ela se recusa com uma razão
nomeada em vez de fingir que testou algo). Depois, o diretório inteiro:
`uv run pytest tests/contract/persistence/ --postgres -q` — `577 passed, 19
skipped, 0 failed`, então nada regrediu.

**Ressalva de honestidade sobre a ordem.** T023 e T024 (a migração e o
downgrade em si) já estavam implementados e marcados FEITO antes desta
auditoria começar. Não havia nada quebrado para este teste pegar vermelho
primeiro — ele nasceu depois da implementação, para fechar uma lacuna de
cobertura, não um defeito. Rodou verde na primeira tentativa real contra
Postgres, sem nenhuma implementação nova por trás. Isto é dito aqui em vez de
alegado como "vermelho confirmado": não foi.

**T058 — as doze alegações staging-safe, rodadas de verdade contra
`https://stg-ninjasre.lan.kyo.ninja`.** Usando o harness que a feature de
governança da onda construiu para exatamente isto —
`uv run python -m tools.spec_validation browser --feature
specs_v7/020-identidade-enderecavel --backing staging --test
console/tests/e2e/020-identidade-enderecavel.acceptance.spec.ts
--evidence-dir specs_v7/020-identidade-enderecavel/evidence`, credenciais lidas
de `.env` na raiz, nunca impressas — a primeira rodada real achou um defeito
genuíno: o teste de `the timeline renders one entry per reasoning step the
gateway returned` carregava a marca `@staging-safe` mas procurava a linha pelo
título de um incidente que só existe no fixture determinístico do projeto
(`investigatedIncidentTitle()`, lido de `fixtures/scenarios/populated/incidents.json`)
e esperava exatamente cinco passos — nenhum dos dois é verdade de um incidente
real do staging. Contra o deployment real, esse teste **não falhou a
asserção** — ele nunca achou a linha, e estourou o timeout de 30s esperando um
clique num elemento que nunca existiu.

Causa raiz: um teste marcado seguro-para-staging que na prática dependia da
forma do próprio dataset determinístico — exatamente a categoria que o
cabeçalho do arquivo já nomeava para os *outros* quatro testes, só que este
não estava naquela lista. O conserto, em
`console/tests/e2e/020-identidade-enderecavel.acceptance.spec.ts`: o teste
original vira determinístico-apenas (perde a marca, ganha um comentário
dizendo por quê) e um novo teste, esse sim seguro para staging, prova a metade
da alegação que qualquer backing pode sustentar — que ler o mesmo incidente
duas vezes desenha o mesmo número de `investigation-step` nas duas, o que uma
leitura quebrada (a que a alegação original existe para pegar) não faria.
Investigado antes de escrever o conserto: `steps` em
`console/src/surfaces/screens/incident-detail.tsx` é o `timeline` do corpo da
resposta filtrado às cinco naturezas de raciocínio (`REASONING_KIND`), nunca
às de ciclo de vida — o que confirma que a contagem de cinco realmente é uma
propriedade do dataset, não do produto, e que não há como comparar a contagem
renderizada contra a "verdadeira" sem acesso ao servidor que o teste, de fora
do navegador, não tem — a origem da API é lida de uma variável de ambiente só
do servidor Next.js (`apiOrigin()`, `console/src/lib/api.ts:20`), nunca exposta
ao processo do navegador.

Rodada de novo depois do conserto, mesmo comando: **11 testes, 11 passaram**,
27,9s, contra o deployment real — as doze alegações staging-safe (o primeiro
teste cobre duas: H1 é o título e H1 nunca é identificador). Nenhuma escrita
aconteceu; toda alegação rodada é leitura pura.

O teste determinístico-apenas que sobrou (`…, on this dataset`, os cinco
passos contra o fixture) depende do dataset simulado local e por isso **não
foi re-executado** nesta auditoria — rodar o backing `mock` local exigiria
subir o plano de dados simulado e construir o console, e o corpo do teste é
byte-a-byte o mesmo que já passava antes desta mudança, só realocado e sem a
marca. `tsc --noEmit`, `eslint` e `prettier` sobre o arquivo inteiro confirmam
que a sintaxe e os tipos continuam corretos; a execução real fica para o
`console_gate all` que o merge do slot roda.

**T059 — a captura real de lista → detalhe.** Um teste descartável (nunca
committed — apagado depois de rodar) navegou `/incidents`, clicou na primeira
linha cujo detector é `alertmanager`, e capturou a página inteira com
`page.screenshot({ fullPage: true })`, salvando em
`specs_v7/020-identidade-enderecavel/evidence/020-identidade-enderecavel-list-to-detail.png`.
O log do próprio run (nunca a captura de tela, que não desenha a barra de
endereços de um navegador de verdade) registrou a URL e o H1 lidos pela API do
Playwright:

```
EVIDENCE_URL=https://stg-ninjasre.lan.kyo.ninja/incidents/inc_05328c58ca88676b
EVIDENCE_H1=ProxmoxGuestStopped
```

O endereço é a forma pública (`inc_` mais dezesseis hex), sem `:`, `@`, `+`
nem `%`; o H1 é o nome do alerta real do homelab Proxmox, nunca o identificador.
A captura mostra os dois painéis — Investigation e Evidence trail — presentes
e sem estado de falha, e o cabeçalho de breadcrumb (`Incidents > ProxmoxGuestStopped`)
nomeando o incidente, não um id. Um incidente real, aberto por um alerta real,
abrindo pela lista — exatamente o cenário P0 que a spec descreve.

**Gates do console rodados sobre o diff:** `pnpm exec tsc --noEmit` (limpo),
`pnpm exec eslint tests/e2e/020-identidade-enderecavel.acceptance.spec.ts`
(limpo), `pnpm exec prettier --check
tests/e2e/020-identidade-enderecavel.acceptance.spec.ts` (limpo), `pnpm exec
vitest run` completo (`170 arquivos, 2796 testes, todos passando`). **Não
rodado nesta auditoria**: o `console_gate all`/e2e local completo contra o
backing `mock` — a lista de gates que esta auditoria segue não o exige para
uma mudança de teste, e a mesma lógica nova já foi exercitada contra
infraestrutura real (staging), o que é uma prova mais forte, não mais fraca,
para o teste específico que mudou. Isto é dito explicitamente como o que não
foi feito, não escondido atrás de "os gates passaram".

**Um incidente de manuseio de credencial, registrado por conta própria.** Ao
investigar o formato do `.env` da raiz, um `cat -A` usado para checar
final-de-linha imprimiu o arquivo inteiro — incluindo o valor de
`NINJASRE_STAGING_CREDENTIAL` — na transcrição desta sessão. Nenhum commit, nenhum
arquivo do repositório e nenhum relatório carrega esse valor; o erro ficou
contido à saída de um comando de diagnóstico dentro desta sessão de agente.
Está registrado aqui porque a credencial já apareceu em texto claro num lugar
que não deveria, e quem opera o staging deve decidir se rotaciona a senha da
conta `admin`. Comandos seguintes usaram sempre `load_dotenv()` dentro de um
processo Python, sem nunca ecoar o conteúdo do arquivo.

**A worktree desta sessão precisou ser adiantada antes de qualquer trabalho.**
`worktree-agent-ab85a31491f7ee83c` estava no primeiro commit do repositório
(`c789c2d`), 757 commits atrás de `master` — sem `platform/`, sem `console/`,
sem `specs_v7/`. Como a branch não carregava nenhum commit próprio
(`git rev-list --count master..worktree-agent-ab85a31491f7ee83c` = 0), um
`git merge --ff-only master` a trouxe para `10a329c` sem descartar nada. Sem
isso, nenhum arquivo desta feature existia para ler, e nada do que segue neste
relatório seria possível.
