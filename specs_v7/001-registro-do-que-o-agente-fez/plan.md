# Implementation Plan: Registro do que o agente fez — se rodou, está escrito

**Branch**: `feat/v7-001-registro-do-que-o-agente-fez` | **Date**: 2026-08-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v7/001-registro-do-que-o-agente-fez/spec.md`

**Referência visual (DoD)**: nenhuma. Feature backend-only, sem tela própria e
sem acceptance spec Playwright — ver o cabeçalho da spec. A superfície que lê
tudo isto é da 010. O que substitui a evidência de tela são as consultas de
banco enumeradas na spec.

## Summary

Três mudanças que se sustentam uma na outra.

**Primeira: alguém escreve.** O `RunRecorder` existe, está correto, e nada no
caminho de serving o chama. Um adaptador novo em tier 3 traduz o que o laço
canônico produz — `Turn`, `ToolExecution`, `EvidenceEntry` — para o vocabulário
que o recorder já aceita, e é registrado como hook no `HookRegistry` que
`ReActInvestigationRunner` já constrói por investigação. Escreve enquanto o run
acontece, uma unidade de trabalho por escrita, porque o run vive mais que
qualquer transação.

**Segunda: o relato vira dois campos.** `agent_runs` ganha uma coluna de
sentença; `agent_runs.summary` continua sendo o documento. O prompt de entrega
passa a pedir a sentença, e o produto sintetiza uma do sujeito quando o modelo
não a der. O contrato ganha os dois campos, o documento HTTP é regenerado e o
cliente TypeScript sai dele na mesma feature.

**Terceira: um só escritor.** Ligar o recorder é ligar o segundo lugar que o
docstring de `start_investigation` avisa que existe. O recibo do alerta fica com
`start_investigation`, e o caminho concorrente dentro do runner sai da árvore.

## Technical Context

**Language/Version**: Python 3.12 (recorder, runtime, gateway, migração);
TypeScript apenas como artefato gerado (`console/src/api/schema.ts`)

**Primary Dependencies**: `platform/runs/recorder.py` (`RunRecorder`,
`RecordedTurn`, `RecordedCall`), `platform/persistence/ports/run_trace_store.py`,
`core/agent/turn.py` (`Turn`, `UsageRecord`), `core/agent/hooks/registry.py`,
`core/pipeline/build.py` (`investigation_hooks`),
`gateway/runtime/investigator.py`, `gateway/http/asgi.py`,
`gateway/http/runtime.py`, `gateway/http/orchestration.py`,
`gateway/http/routes/investigations.py`, `gateway/http/routes/runs.py`,
`config/prompts/investigation.py`, alembic em
`platform/persistence/migrations/`

**Storage**: PostgreSQL. Uma coluna nova em `agent_runs`, por migração
reversível, com `NOT NULL DEFAULT ''`. Nenhuma linha existente tem conteúdo
reescrito. As tabelas `run_turns`, `tool_calls`, `evidence` e `trace_events` já
existem e não mudam de forma — passam a receber linhas.

**Testing**: pytest. Unitários do adaptador de gravação e da síntese da
sentença; contrato para os campos novos e para o replay com custo; arquitetura
para "o caminho de serving compõe o recorder"; a suíte de persistência contra
Postgres real para a migração de ida e de volta. Sem Playwright.

**Target Platform**: gateway Python servido no k3s de staging; validação por
`make deploy-stg` no fim do slot.

**Project Type**: composição de mecanismo existente + mudança de contrato de
fronteira.

**Performance Goals**: uma escrita por turno e uma por chamada, cada uma em sua
própria unidade de trabalho. O custo é linear no que a investigação já fez, e a
truncação que o recorder aplica é o que impede uma chamada grande de dominá-lo.

**Constraints**: nenhuma escrita pode contornar a redação de guardrail; a falha
ao gravar não derruba a investigação; a verificação completa precisa terminar
verde tendo partido de verde; `core` e `platform` podem se importar, `core` não
pode importar tier 1 nem tier 2 — o adaptador de gravação mora em `platform`.

**Scale/Scope**: um adaptador novo, um hook registrado, uma coluna, um campo de
prompt, dois campos de contrato, um documento HTTP e um cliente regenerados.

## Composição — qual root constrói o quê

*Exigência da constituição pós-000: um mecanismo mergeado é alcançável a partir
de uma composition root de serving, e o plano diz qual.*

| Peça | Quem a constrói, em produção | Observação |
|---|---|---|
| `RunRecorder` para o começo e o fim do run | `gateway/http/orchestration.py`, dentro de `start_investigation` e de `_drive` | Já é assim hoje. Não muda. |
| Recibo do alerta na linha do tempo | `gateway/http/orchestration.py:start_investigation` | **Único escritor.** O caminho concorrente sai da árvore. |
| Adaptador de gravação do trace (novo) | `gateway/http/asgi.py:investigator_of`, que passa a receber o store e a anexá-lo ao runner que a fábrica devolveu | Um só ponto de anexo, chamado pelas duas rotas de composição |
| `ReActInvestigationRunner` | `gateway/runtime/factory.py:build_investigator`, nomeado pela configuração do deployment | Continua sem argumento e continua sem store — é o que um operador nomeia |
| Reanexo depois da configuração ser lida | `gateway/http/runtime.py:recompose_investigator`, chamando o mesmo `investigator_of` | É por aqui que a composição sobrevive ao rebuild |
| `HookRegistry` da investigação | `gateway/runtime/investigator.py:_build_runtime`, a partir de `investigation_hooks()` | Passa a registrar o hook de gravação quando o runner tem onde escrever |
| Pipeline por estágios (`build_pipeline`) | **ninguém, deliberadamente** | Não ganha chamador de produção nesta feature. É da 040 decidir. |

**Por que o anexo é em `investigator_of` e não na fábrica.** A fábrica que a
configuração nomeia é, por contrato documentado, uma função sem argumento: é o
que permite a um operador *nomear* um runtime em vez de escrevê-lo. Ela não pode
segurar um handle de banco. O store existe em `build_deployment`, e existe de
novo em `recompose_investigator` — e essas duas são exatamente as duas
chamadoras de `investigator_of`. Colocar o anexo dentro dela é o que garante que
as duas concordem. Colocá-lo nas duas chamadoras seria repetir a forma do
defeito que a reconstrução do investigador já custou uma vez: dois lugares que
precisam ser mudados juntos e não são.

**Como o adaptador sabe em que organização escrever.** `InvestigationStart`
ganha a identidade da organização, ao lado do nó de time que ela já carrega. Ela
é o objeto de dados que atravessa a fronteira, e completá-la é mais barato que
alargar a assinatura do protocolo `InvestigationRunner` — que teria de mudar em
toda implementação, inclusive nas falsas que dirigem a superfície nos testes.
A alternativa considerada e recusada: passar um escopo já vinculado por
investigação, o que faria o runner segurar estado por run fora do `_live` que
ele já tem.

**Por que hook, e não gravar no fim.** Gravar tudo em `_drive`, depois que
`investigate` retorna, seria mais simples e estaria errado por três razões: o
stream ao vivo passaria a entregar o run inteiro no último instante; um processo
que morresse no meio não deixaria nada; e um run cancelado — que por design para
entre iterações — perderia as iterações que já tinham acontecido. A regra do
artigo de evidência é sobre o resultado ter entrado no trace, não sobre ele
aparecer lá algum dia.

## Constitution Check

*GATE: precisa passar antes da execução. Reconferir ao final.* Feito contra a
constituição **como ela fica depois da 000** — 2.2.0, com a cláusula de
composição.

| Artigo | Como este plano satisfaz |
|---|---|
| I — Evidência sobre asserção | É o artigo que a feature implementa. "Um resultado de ferramenta que nunca entrou no trace não aconteceu" está literalmente violado no staging hoje, com 37 investigações e três tabelas zeradas. O plano não afrouxa a regra: ele liga o caminho que a torna verdadeira, e o DoD é a contagem no banco, não o verde do harness. |
| II — Autonomia limitada | Não toca laço, orçamento nem teto. O `RunRequest` continua saindo com os defaults do próprio tipo, que são os tetos do artigo. Gravar não consome iteração. |
| III — Leitura por padrão | Não toca semântica de escrita nem de aprovação. Uma chamada recusada passa a ser **gravada como recusada**, o que fortalece a auditoria da recusa sem mudar a recusa. |
| IV — Segredo nunca chega ao agente | O caminho novo escreve **através** do `RunRecorder`, que redige por guardrail antes de persistir. Isto é normativo no plano: nenhuma escrita nova pode chamar o store diretamente. Um trace com segredo é um segredo num segundo armazém que ninguém audita e que a retenção guarda por noventa dias. |
| V — Um runtime canônico | O laço canônico continua sendo o único que produz número publicável. O plano registra o que ele produz; não introduz runtime nem o troca. O pipeline por estágios continua sem chamador de produção, e o plano diz isso em voz alta para que ninguém o ligue por engano na mesma janela. |
| VI — Neutralidade de provedor | O turno grava o modelo que respondeu, vindo do que o cliente de provedor reporta, pelo mesmo caminho para todo provedor. Um provedor sem preço publicado grava sem preço — a ausência é do provedor, não uma exceção codificada para ele. |
| VII — Aprendizado é medido | Não muda mecanismo de aprendizado. Efeito colateral favorável: o corpus episódico passa a ter transcript real por trás das conclusões que ele indexa. |
| VIII — Arquitetura em camadas | O adaptador de gravação mora em `platform/` porque precisa de `core.agent` e de `platform.runs` ao mesmo tempo, e o contrato de camadas permite exatamente isso (`core : platform`). O registro do hook é feito em tier 1, que é onde a composição mora. A cláusula 4 — a compatibilidade morre na mesma mudança — é o que decide que o segundo escritor de recibo sai da árvore em vez de ficar desligado. |
| IX — Capacidades declaradas | Não muda declaração de capacidade. O que muda é que a invocação de uma passa a ser registrada, com o nível de efeito colateral já disponível no contexto do hook. |
| X — O operador é dono dos dados | Nada sai do host. O que a feature acrescenta é dado do operador armazenado no banco do operador, sob a retenção que já existe. |
| XI — Datastore único | Cláusula 2: a escrita nova vai por `RunTraceStore`, nunca por SQL solto. Cláusula 3: a coluna nova vem por migração **reversível**, e o plano exige que a volta seja exercitada contra um banco com dados, não apenas escrita. |
| XII — Test-first, rastreado | Cláusula 1: cada comportamento novo aterrissa com seu teste vermelho confirmado antes da implementação. Cláusula 3: **é a que morde aqui** — ligar o recorder e mudar o prompt de entrega são mudanças que afetam investigação, e o efeito sobre a suíte de cenários sintéticos tem de ser medido e reportado. "Sem efeito" é resposta; "não medido" não é. Cláusula 4: os campos novos entram nos testes de contrato. |
| XIII — Idioma e atribuição | Todo arquivo committed em inglês. Nenhum arquivo committed cita identificador de requisito, número de artigo, número de feature nem caminho de planejamento — a substância vai no arquivo, a referência fica nesta spec. |
| **Composição (cláusula nova da 2.2.0)** | A tabela "Composição" acima responde a pergunta "quem constrói isto em produção?" com arquivo e função para cada peça. O `tasks.md` tem tarefa explícita de composição e um teste de arquitetura que reprova se o caminho de serving deixar de compor o recorder. Verde no harness não fecha nenhuma tarefa de comportamento desta feature; a contagem no banco de staging fecha. |

### Complexity Tracking

Uma peça nova de verdade — o adaptador que traduz o vocabulário do laço para o
do recorder — e um campo novo em dois objetos de dados. Nada de estrutura nova,
nenhum tier novo, nenhum port novo. O ganho compensa: cinco superfícies que
hoje leem tabelas vazias passam a ler tabelas cheias sem que nenhuma delas mude.

Um item merece registro por ser aumento de superfície, não redução: o contrato
carrega três campos de relato durante uma feature (sentença, documento e o
`summary` que sobrevive). É deliberado e tem prazo — sai quando o último leitor
sair, e o último leitor é da 010, no slot seguinte. Manter um só campo agora
significaria um slot inteiro com o console sem relato nenhum.

## Project Structure

### Documentation (this feature)

```text
specs_v7/001-registro-do-que-o-agente-fez/
├── spec.md
├── plan.md              # este arquivo
├── tasks.md
├── controle.md          # do implementer, não deste plano
└── checklists/requirements.md
```

### Source Code (repository root)

```text
platform/runs/recorder.py                        # RecordedTurn.cost passa a admitir ausência
platform/runs/recording.py                       # NOVO: o adaptador laço → recorder
platform/runs/headline.py                        # NOVO: síntese e normalização da sentença
platform/persistence/ports/run_trace_store.py    # AgentRun ganha a sentença
platform/persistence/postgres/models.py          # coluna nova em agent_runs
platform/persistence/postgres/repositories/run_trace_store.py
platform/persistence/fakes/run_trace_store.py
platform/persistence/migrations/versions/0015_*.py   # coluna nova, reversível
core/pipeline/build.py                           # investigation_hooks aceita o hook de gravação
gateway/runtime/investigator.py                  # registra o hook; perde o segundo recibo
gateway/http/services.py                         # InvestigationStart ganha a organização
gateway/http/asgi.py                             # investigator_of recebe o store e anexa
gateway/http/runtime.py                          # recompose_investigator passa o store
gateway/http/orchestration.py                    # passa a organização adiante
gateway/http/routes/investigations.py            # contrato: sentença + documento
gateway/http/routes/runs.py                      # replay: turnos sem preço, vínculos
gateway/webhooks/router.py                       # continua o dono do recibo
config/prompts/investigation.py                  # o prompt de entrega pede a sentença
fixtures/contract/openapi.json                   # regenerado
console/src/api/schema.ts                        # regenerado a partir do documento
fixtures/scenarios/*/runs.json                   # campos novos nas fixtures
tests/unit/platform/runs/                        # adaptador, síntese, custo ausente
tests/contract/                                  # contrato novo, replay com custo
tests/architecture/                              # o caminho de serving compõe o recorder
tests/contract/persistence/                      # migração de ida e de volta
```

**Structure Decision**: dois módulos novos em `platform/runs/`, ao lado do
recorder que eles servem. Nenhum pacote novo, nenhuma alteração de contrato de
import.

## Decisões de design

- **O adaptador mora em `platform/runs/`, não em `core/agent/hooks/builtin/`.**
  Ele precisa de `core.agent.turn` e de `platform.runs.recorder` ao mesmo tempo.
  O contrato de camadas declara `core` e `platform` como pares que podem se
  importar, então `platform` importando `core.agent` é permitido e o inverso
  também — mas colocar o adaptador em `core` faria o runtime canônico depender
  de um armazém, que é justamente o que os hooks existem para evitar. O hook
  observa; quem escreve mora do lado de quem tem o store.

- **Uma unidade de trabalho por escrita.** O run vive minutos e uma transação
  não. Segurar uma aberta por toda a investigação bloquearia uma conexão do pool
  pelo tempo do run e perderia tudo num rollback. Cada turno e cada chamada
  abrem a sua, escrevem e fecham — que é a mesma forma que `_drive` já usa para
  fechar o run.

- **A falha de gravação é registrada, nunca propagada.** Um trace que não pôde
  ser escrito é um problema; uma investigação derrubada porque o trace não pôde
  ser escrito é dois. O hook engole a exceção e a registra como falha de hook,
  que é o mecanismo que o laço já tem para isso e que já aparece no resultado do
  run.

- **O custo ausente precisa de um tipo que o expresse.** `RecordedTurn.cost` é
  hoje `float = 0.0`, e a agregação de custo trata `None` como "sem preço" — ou
  seja, o caminho de leitura já sabe distinguir, e o caminho de escrita não sabe
  dizer. O tipo passa a admitir ausência. É a menor mudança que impede a feature
  de fabricar zeros, e a convenção já é a da casa: o resumo de investigação
  omite custo em vez de mentir zero.

- **A sentença é normalizada na escrita e sintetizada na leitura.** Normalizada
  na escrita porque um modelo que devolveu três parágrafos com marcação já
  desobedeceu, e guardar isso é guardar o defeito. Sintetizada na leitura porque
  um run antigo não tem sentença e escrever uma agora gravaria como fato do run
  algo que a leitura derivou — a distinção entre o que aconteceu e o que
  inferimos é a mesma que separa evidência de conclusão.

- **A síntese nunca lê o documento.** É a regra que impede a regressão exata que
  a rodada encontrou. A sentença sintetizada sai do sujeito: nome do alerta e
  recurso quando o run veio de um alerta, objetivo declarado quando veio de um
  operador. Um documento truncado como título é o defeito, não o fallback.

- **`headline` é a palavra da casa, não uma palavra nova.** O vocabulário já
  existe nos prompts — o resumo de achado de sub-agente, o título de entrada
  ruidosa, o título de alerta duplicado. Inventar um sinônimo criaria duas
  palavras para um conceito num produto que tem uma.

- **O recibo fica com `start_investigation`.** Dos dois lugares que o docstring
  nomeia, esse é o que escreve dentro da transação que reserva a identidade do
  run, antes de a resposta sair — o que dá ao recibo a mesma atomicidade da
  reserva. O caminho concorrente no runner sai da árvore inteiro, com seus
  testes reapontados para afirmar o escritor único. Deixá-lo desligado por
  configuração seria manter viva a possibilidade de duplicação que o docstring
  avisa, sem o custo de removê-la.

- **O pipeline por estágios não ganha chamador de produção aqui.** Ele existe,
  está testado, e dar-lhe um caller é uma decisão sobre *como* investigar, não
  sobre *registrar* o que a investigação fez. Ligá-lo na mesma janela em que o
  recorder é ligado criaria dois produtores de evento para o mesmo run, que é
  precisamente a duplicação que esta feature está eliminando do lado do recibo.

- **A coluna nova é a da sentença; o documento fica onde está.** `summary`
  guarda o documento em 37 linhas reais no staging. Renomear a coluna seria uma
  migração de conteúdo por estética de nome. A leitura é que passa a chamar
  aquela coluna de documento.

- **O documento HTTP e o cliente TypeScript saem na mesma feature.** Regenerar o
  contrato é `python -m tools.mockplane.cli contract`; regenerar o cliente é
  `make console-client`; a checagem de desvio é `make console-client-check`. Uma
  mudança de contrato que deixa o cliente para depois é uma fronteira quebrada
  que só aparece no slot seguinte — foi o efeito clássico da onda passada.

- **A ordem é gate-primeiro.** Os testes que afirmam "um run que fez N chamadas
  tem N registros de chamada" e "a resposta traz sentença e documento" entram
  antes de qualquer composição, e são confirmados vermelhos contra a árvore
  atual. Uma gravação validada só depois do fato não distingue "gravei certo" de
  "o teste não olha" — e este é o defeito de um mecanismo que passou cinco
  ondas com testes verdes e fio desligado.

- **A linha de base é artefato.** A verificação completa é capturada antes da
  primeira mudança, junto com a contagem da suíte de cenários sintéticos. Sem
  ela, uma falha preexistente é debitada desta feature e uma falha desta feature
  se esconde atrás de "já estava assim".

## Risco conhecido de fronteira, e o que fazer com ele

`console/src/api/schema.ts` e `fixtures/contract/openapi.json` são artefatos
gerados que **esta feature e a 020 podem tocar no mesmo slot** — a 020 mexe em
identidade de incidente e pode alterar as mesmas rotas de leitura. Eles não
constam da lista de arquivos de escrita única do protocolo de execução, então
não há dono declarado.

Regra que este plano adota: cada lado **regenera** os dois artefatos a partir do
seu próprio código e **não os resolve à mão**; no merge do slot, o orquestrador
descarta as duas versões, aplica os dois diffs de código e regenera uma vez só,
rodando a checagem de desvio depois. Um artefato gerado resolvido linha a linha
num conflito é um artefato que deixou de corresponder ao gerador.

Isto vale como pedido explícito ao orquestrador da onda, e está repetido na
última tarefa do `tasks.md`.
