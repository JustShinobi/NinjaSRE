# Controle — 020-identidade-enderecavel

Estado verificado contra o código mergeado em `master`, não contra intenção.

**Como este arquivo foi escrito.** A feature rodou numa worktree isolada, onde
`specs_v7/` não existe (está no `.git/info/exclude`). O implementer entregou
este texto no relatório final e o orquestrador o gravou aqui após o merge do
slot.

Verificação independente: **pendente**. A validação determinística e a de
staging passaram, rodadas pelo orquestrador; o `spec-verifier` em contexto
limpo ainda não rodou sobre esta feature.

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
| Migração com backfill, reversível | FEITO | `0017_incident_public_id` (re-parenteada no merge — ver adiante); importa a função de derivação em vez de reimplementá-la |
| **Decodificação única na borda** | FEITO | `console/src/shell/route-params.ts`, aplicado às quatro rotas dinâmicas reais; a dupla codificação em `console/src/lib/api.ts` documentada como invariante |
| Título e aba nunca são identificador | FEITO | `console/src/surfaces/screens/incident-detail.tsx` |
| Leitura falhada não afirma negativo | FEITO | o chip de investigação é suprimido em vez de afirmar ausência |
| Quatro superfícies usam o endereço, nenhuma codifica | FEITO | lista, dashboard (duas ocorrências), busca e detalhe de run |
| Rotas respondem pelos nomes | FEITO | `/investigations` → `/runs`, `/setup` → `/first-run`; tabela renomeada para o que ela é |
| Acceptance spec | FEITO | `console/tests/e2e/020-identidade-enderecavel.acceptance.spec.ts` — dezesseis alegações, quinze testes, verdes |
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

1. **Migração não exercitada contra PostgreSQL real por esta feature.** O
   verificador do outro lado do slot rodou a cadeia inteira — que inclui esta
   migração, já re-parenteada — contra PostgreSQL real, sem erro. A lacuna está
   fechada por essa via, não por trabalho desta feature.
2. **Fechamento e supressão** resolvem as duas grafias pela mesma função do
   detalhe, mas sem teste de contrato dedicado além do que o teste do detalhe
   cobre por construção compartilhada.
3. **Verificação independente ainda não rodou** sobre esta feature.

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
