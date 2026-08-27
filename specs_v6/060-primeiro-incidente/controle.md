# Controle — 060, o primeiro incidente ponta a ponta

O que o código prova, o que ficou pendente, e o que foi descoberto no caminho.
Nada aqui é afirmado sem evidência; onde a evidência é fraca, está dito que é.

**28 commits**, de `704783f` a `a916ad7`, sobre `9cc8d35`.

---

## O que está fechado

| Tarefa | Estado | Evidência |
|---|---|---|
| T001, T003 | pronta | fixtures gerados pelo builder, 108 testes de contrato incluindo rebuild byte-a-byte |
| T002 | pronta | incidente detalhado com run anexado e os sete passos |
| T004 | pronta | **14/14 verdes** com backing `compose`; vermelho de 14/14 registrado antes |
| T005 | caracterização | 5 alegações já verdes; cada uma invertida e vista falhar antes de ser aceita |
| T006 | pronta | as três alegações verdes |
| T007 | pronta | 5 testes; as três superfícies asseridas **em conjunto** |
| T008 | pronta | 8 testes; vermelho genuíno provado duas vezes |
| T009–T012 | pronta | entrega, recusa, duplicata e resolução; contagem de incidentes asserida |
| T013, T014 | pronta | token de finalidade única; recusa agora visível no ledger |
| T015–T019 | pronta | fábrica de runtime; guarda do runtime canônico 6/6 |
| T020–T022 | pronta | cinco tipos de passo; migração reversível **exercitada contra Postgres real** |
| T023–T027 | pronta | recibo, hipóteses, diagnóstico, entrega, sumário |
| T028 | pronta | rota servindo consulta, resultado e os três números |
| T029–T032 | pronta | tela do M6; orçamento de rolagem em **1080px** contra teto de 2160 |
| T033–T037 | ver pendências | quatro fechadas, duas parciais |
| T038 | **aprovada** | 401 de dentro do CT136, sem alterar nada |
| T041, T043 | pronta | runbooks escritos |
| T046 | pronta | palavra canônica + conclusão sem lastro vira hipótese |
| T049, T050, T051, T052 | pronta | baseline reapontada e revisada; transversal 25/7/0; cenários sintéticos 257 |

### A alegação central, provada como ausência

O produto é *propose-only*, e isso só se prova pelo que **não** acontece:

- `_nothing_ran()` lê o **ledger de remediação** — onde uma execução escreveria —
  e o encontra vazio **antes e depois** de aprovar.
- Aprovar sem plano de reversão: 400, estado permanece `PENDING`, `decided_by`
  nulo, nada executou.
- Rejeitar sem motivo: o teste se chama `never_reaches_the_store`. A alegação é
  ausência no store, não erro na rota. Na tela, `fetch` **não é chamado**.
- Sem evidência que sustente, o cartão de ação proposta **não aparece** — e isso
  funciona porque o domínio recusa chamar de diagnóstico uma conclusão sem
  lastro, então a tela só precisa perguntar se há diagnóstico.

### O segredo, provado de três formas

O valor do delivery token nunca chega ao registro:

1. **Estrutural** — `receipt` não tem parâmetro por onde passar um valor.
2. **Comportamental** — `_leak_scan` percorre **todo campo do dataclass** por
   reflexão, na entrada e na timeline inteira.
3. **Meta** — um terceiro teste planta o segredo num rótulo para provar que o
   scan não é vacuamente verdadeiro.

E ponta a ponta: uma entrega real com token real, varrendo timeline, incidente,
linhas de trânsito e a amostra mascarada.

---

## Pendências

### Duas parciais da Fase 6

**T047 — a entrada `CORRELATED` não é gravada.** O defeito real foi corrigido:
o adaptador usava só o alerta líder e descartava silenciosamente os outros
membros do grupo, contradizendo o próprio docstring. Agora todo membro vira
subject, e a **contagem** de incidentes é asserida em 1. O que falta é a entrada
explícita na timeline. Ela exigiria acrescentar o tamanho do grupo ao
`NormalisedAlert`, que muda `to_record` e ricocheteia nos contratos de fixture —
mudança de domínio que não cabia com segurança no fim desta feature. A alegação
"não produz duplicados sem explicação" está fechada; a alegação "a decisão
aparece na timeline" não.

**T048 — a distinção existe, mas não é alcançável por um clique.**
`ExecutionOutcome.UNCHANGED` é valor distinto de `SUCCEEDED` e `FAILED`, e a
correção separou dois fatos que compartilhavam nome: um conjunto de resultados
vazio (control plane perguntado que não respondeu — falha real) de um conjunto
onde toda peça reporta que não mudou (respondeu por todas, nenhuma precisava
mover). Isso também corrigiu um defeito pré-existente, com **dois testes
committed que codificavam o errado como correto** — reescritos por inteiro.

**Mas nada disso é alcançado por um clique real.** A rota de decisão chama só
`uow.approvals.decide(...)`: nenhum import de execução, nenhuma chamada de
capacidade. **Aprovar uma ação proposta hoje registra a decisão e não executa
nada.**

O botão diz **"Approve and run"**, palavra exigida pela T034 por ser a do
mockup. Para um produto propose-only isso é defensável — nada executa sem
decisão, e a decisão fica registrada — mas o rótulo promete mais do que o
produto faz. Quem for ligar a execução herda esta linha.

### As fases operacionais

| Fase | Estado |
|---|---|
| **O-A (T038)** | **aprovada.** 401 de dentro do CT136 sem token. Nada alterado. |
| **O-B (T039)** | pendente — acrescentar o receiver ao lado do existente |
| **O-C (T040)** | pendente — publicar release e apontar a configuração |
| **T1 (T042)** | pendente — depende de O-B e O-C |
| **T2 (T044, T045)** | pendente — vítima escolhida: **CT122 `redis`** |

O acesso existe: `ssh pve01` e `ssh pve02` funcionam sem senha, e o repositório
de infra está em pve02. O que falta é a decisão de alterar uma stack de
monitoring viva.

**Correções de endereço que o plano tinha erradas** — verificadas, não supostas:

- o gateway está em **192.168.68.73**, não `.74` (o endereço não é estável);
- o Alertmanager é o **CT136 em 10.20.20.36**; `10.20.20.37` é o CT137
  `prometheus`;
- a configuração vive em **pve02**, no caminho que o plano nomeia.

**A vítima do T2 precisa ser descartável E observada.** `dockge`,
`streamlink-webui` e `bazarr` não são observadas por nada — pará-las não dispara
alerta e o roteiro morreria na primeira etapa sem que isso fosse defeito do
produto. `redis` (CT122, 10.20.20.52) é o alvo de scrape do `redis-exporter`.
Duas regras disparam, ambas com `for: 2m` e `severity: critical`;
`RedisInstanceDown` provavelmente **não** dispara, porque compara `redis_up == 0`
e com o contêiner parado a métrica some em vez de zerar.

---

## Defeitos encontrados que não eram desta feature

A feature encontrou mais defeitos entregues do que implementou funcionalidade:

1. **A stack compose não subia.** Mount do postgres em `/var/lib/postgresql/data`
   com imagem 18. Falhava de volume novo, para qualquer operador.
2. **`proxy` e `console` em crash-loop** — validavam provider sem recebê-lo.
3. **O chart Helm nunca entregava a credencial**: montava
   `NINJASRE_PROVIDER_CREDENTIAL`, nome que **nenhum código lê**.
4. **Dois workloads do chart** nunca recebiam provider — o Job de migração
   validava antes do próprio branch de migrar, então migrações não rodavam.
5. **O job de CI `console-e2e-compose` falhava sem ninguém notar** desde a troca
   da imagem base.
6. **A baseline visual do incidente apontava para um incidente inexistente** —
   várias features aceitaram e compararam um estado de "não encontrado".
7. **Uma entrega recusada não era registrada** em lugar nenhum durável.
8. **`outcome_of()` chamava de falha um alvo já satisfeito**, com dois testes
   codificando isso como correto.
9. **`formatCurrency` arredondava `$0.004` para `$0.00`** — lido como "de graça",
   e o detalhe do run tinha o mesmo problema.

---

## Instrumentos que mentiam

Três, todos do mesmo formato — a ferramenta usada para conferir não enxergava o
que estava errado:

- **`compose_stack()` não reconstruía as imagens.** Uma execução serviu um
  backend de horas antes e devolveu 9 de 14 vermelhos sobre rotas que o código
  rodando não tinha. Corrigido — e o primeiro conserto reconstruía **tudo**,
  inclusive a imagem do banco que baixa uma extensão da rede, quebrando o backing
  em máquina sem acesso. Agora reconstrói só os três serviços com código nosso.
- **`vitest --pool=forks` não aplica os limiares de cobertura.** Uma fatia viu
  verde; o gate reprovou em 89,8% contra piso de 90.
- **O hook de pre-commit faz `git stash` do não-staged**, o que torna commitar
  durante uma execução viva uma corrida.

---

## Onde a evidência é fraca

- **T005 nasceu verde.** É caracterização, não correção. Cada alegação foi
  invertida e vista falhar antes de ser aceita, mas nada foi construído ali.
- **A mesa de `ask_human` não está ligada.** A investigação roda e não consegue
  perguntar a humano no meio.
- **`ReActLoop` nunca emite `RunStatus.FAILED`** por caminho alcançável. O
  tratamento existe por completude de contrato, testado por stub.
- **`RecordedTurn.cost` é `float = 0.0`, não `float | None`.** A rota distingue
  ausente de zero corretamente, mas nada a montante produz a ausência.
- **A maior parte foi provada contra o fake**, não contra Postgres real. As
  exceções estão nomeadas: a migração e o round-trip dos cinco tipos.
