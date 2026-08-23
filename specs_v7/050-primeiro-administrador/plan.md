# Implementation Plan: Primeiro administrador — um deployment novo produz o seu

**Branch**: `feat/v7-050-primeiro-administrador` | **Date**: 2026-08-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs_v7/050-primeiro-administrador/spec.md`

**Referência visual (DoD)**: nenhuma tela nova. Duas telas existentes ganham um
bloco no estado "sem administrador local"; as **Alegações normativas** da spec
são o contrato e o acceptance spec as codifica. Viewport de medição 1920×1080.

**Slot**: S4, em par com a 060. Esta feature **não é dona** dos arquivos de
escrita única — chaves i18n vão no relatório final, não nos arquivos.

## Summary

O caminho canônico para o primeiro administrador passa a ser um comando do
CLI, `ninjasre setup admin`, e a credencial que o boot já emite passa a ser o
convite que nomeia esse comando em vez de uma promessa que a tela não cumpre. A
porta do sign-in local deixa de ser "a variável de ambiente está configurada" e
passa a ser "este deployment tem administrador local habilitado" — um fato do
banco, com registro único por deployment, que só um ato deliberado torna
verdadeiro. A troca da credencial de bootstrap passa a produzir uma conta com
passphrase além do token, fechando o seam em que o operador segurava algo que o
formulário não sabia usar. E a unicidade de e-mail deixa de valer para
principals sem endereço, o que destrava o segundo service account de qualquer
deployment.

Nada disso afrouxa as três invariantes que o raciocínio existente defende. Elas
são preservadas por substância e reescritas em termos do fato novo: uma entrada
que ninguém pediu continua sendo uma entrada; um deployment com identity
provider continua não ganhando segunda porta; a passphrase embarcada continua
recusada fora de demonstração declarada.

## Technical Context

**Language/Version**: Python 3.12 (identidade, persistência, CLI, gateway);
TypeScript (console, dois blocos de aviso e o fato que os alimenta)

**Primary Dependencies**: `platform/identity/local_accounts.py`,
`platform/identity/break_glass.py` (a construção de hash),
`platform/startup/bootstrap.py`, `platform/persistence/ports/identity_repository.py`,
`platform/persistence/postgres/{models.py,repositories/identity_repository.py}`,
`platform/persistence/fakes/identity_repository.py`,
`platform/persistence/migrations/versions/`,
`gateway/http/{asgi.py,routes/identity.py,routes/first_run.py,security/first_run_routes.py}`,
`gateway/http/serve.py`, `surfaces/cli/commands/setup.py`,
`console/src/app/sign-in/page.tsx`, `console/src/surfaces/screens/first-run.tsx`

**Storage**: PostgreSQL. Duas revisões novas: o registro de abertura do
sign-in local, e a unicidade de e-mail passando a ignorar principals sem
endereço. As duas com `downgrade` real.

**Testing**: pytest — unidade de identidade e de bootstrap, contrato de
persistência contra os dois backends, contrato de deployment para o fluxo
ponta-a-ponta, e um teste de concorrência contra Postgres real. Vitest para o
bloco de aviso. Playwright para o acceptance spec da feature.

**Target Platform**: backend Python + console web + CLI distribuído na imagem

**Project Type**: identidade e primeiro acesso, transversal a persistência,
gateway, CLI e console

**Performance Goals**: o caminho de recusa do sign-in não pode ganhar
verificação de passphrase nova. Ele ganha exatamente uma leitura indexada, feita
incondicionalmente, antes do ramo — o custo comparativo entre um nome que existe
e um que não existe fica como está.

**Constraints**: a conta local que o staging já usa continua entrando sem
migração e sem passo manual. Nenhuma rota não autenticada nova. Nenhum
`--force` no caminho do identity provider.

**Scale/Scope**: um comando novo no CLI, um registro novo no banco, uma
mudança de índice, uma mudança de contrato numa rota de first-run, dois blocos
de aviso no console.

## Constitution Check

*GATE: precisa passar antes da execução. Reconferir ao final.*

Checagem contra a constituição **como ela fica depois da 000** (2.2.0, com a
cláusula de composição).

| Artigo | Como este plano satisfaz |
|---|---|
| I — Evidência sobre asserção | O DoD não é "os testes passam": é a transcrição de um terminal, num deployment limpo de compose, do primeiro start até a sessão estabelecida. A afirmação "quem não leu nada entra" só é aceita como observação registrada. O teste de concorrência roda contra Postgres real, porque uma corrida provada contra um store em memória não é uma corrida. |
| II — Autonomia limitada | Não toca laço, orçamento nem limite de autonomia. |
| III — Leitura por padrão | Não muda semântica de escrita nem de aprovação de nenhuma capacidade. As escritas desta feature são de identidade, feitas por quem já tem o host ou já tem a credencial de bootstrap. |
| IV — Segredo nunca chega ao agente | Nenhuma passphrase entra em log, em auditoria, em saída de comando ou em resposta HTTP. A passphrase não é aceita por argumento de linha de comando (fica no histórico do shell e na tabela de processos) nem lida do ambiente por conta própria. A credencial de bootstrap continua impressa e não logada. |
| V — Um runtime canônico | O comando novo não compõe um segundo runtime: usa a mesma `platform.startup` que o gateway usa, pelo mesmo `store_factory` que os outros comandos de setup já usam. `surfaces/` continua não importando `gateway/`. |
| VI — Neutralidade de provedor | Não toca abstração de provedor. |
| VII — Aprendizado é medido | Não toca mecanismo de aprendizado. |
| VIII — Arquitetura em camadas | A regra nova vive em `platform/identity`; a persistência entra pela porta que já existe; o gateway e o CLI são dois clientes da mesma regra, não duas cópias dela. As checagens de contrato de import rodam no gate final. |
| IX — Capacidades declaradas | Não acrescenta capacidade. A permissão que a rota de troca exige não é alargada. |
| X — O operador é dono dos dados | Nada sai do host. Nenhuma conta existente é apagada, inclusive quando um identity provider é ativado. A migração desce, ou recusa dizendo o que impede. |
| XI — Datastore único | O registro de abertura vive no mesmo Postgres, pela mesma porta, com a mesma unit of work. Nenhum estado de identidade novo em arquivo. |
| XII — Test-first, rastreado | Cada comportamento novo tem seu vermelho antes da implementação, capturado com a mensagem real: a recusa por deployment já administrado, a recusa por identity provider ativo, a corrida, o segundo service account sem e-mail, o sign-in com a conta que a troca criou, e as dez alegações normativas. |
| XIII — Idioma e atribuição | Todo arquivo committed em inglês; texto de tela pelo catálogo, com en obrigatório e pt-BR junto. Nenhum identificador de requisito, número de artigo, número de feature ou caminho de planejamento em arquivo committed. |
| **Composição (2.2.0)** | **É a cláusula que morde aqui.** Ver a seção seguinte: cada mecanismo novo tem uma composition root nomeada e uma prova no caminho de serving. |

### Qual composition root constrói cada mecanismo

A cláusula de composição exige nome e lugar, não intenção. Para cada peça
nova:

| Mecanismo | Quem o constrói em produção |
|---|---|
| Leitura da abertura do sign-in local por tentativa | `LocalSignIn`, já construída em `gateway/http/asgi.py::build_deployment`; passa a receber o gateway que já recebe e a consultar a abertura no início de `sign_in`. |
| Escrita da abertura + criação do administrador | Uma função de `platform/identity/` chamada por **dois** clientes de produção: o comando do CLI (`surfaces/cli/commands/setup.py`, registrado em `surfaces/cli/app.py`) e a rota de troca (`gateway/http/routes/first_run.py::durable_credential`). |
| Gating da emissão da credencial de bootstrap | `platform/startup/bootstrap.py::bring_up`, chamada por `gateway/http/serve.py` no boot — o caminho que o entrypoint da imagem já executa. |
| Convite impresso | `platform/startup/bootstrap.py::announcement`, impressa por `gateway/http/serve.py`. |
| Fato "sem administrador local" servido ao console | Uma rota pública de disponibilidade no gateway, registrada na tabela de rotas de first-run, lida pela tela de sign-in. |
| Unicidade de e-mail que ignora ausência | `platform/persistence/postgres/repositories/identity_repository.py` e o fake, provados pela suíte de contrato que roda contra os dois. |

**Prova no caminho de serving**: um deployment levantado por
`deploy/compose/docker-compose.yml`, sem `NINJASRE_LOCAL_ACCOUNT_PASSWORD_HASH`,
percorrido do primeiro start até a sessão estabelecida. "Testes verdes no
harness" não fecham nenhuma tarefa de comportamento desta feature.

### Complexity Tracking

Uma tabela nova e um índice alterado. A alternativa sem tabela — inferir a
abertura de "existe algum usuário com passphrase armazenada" — foi considerada
e recusada: ela reabre exatamente a invariante que o código defende, porque a
rota de criação de principal armazena passphrase e passaria a abrir a porta
sozinha. A tabela existe para que "alguém tem senha" e "a porta está aberta"
continuem sendo dois fatos.

## Project Structure

### Documentation (this feature)

```text
specs_v7/050-primeiro-administrador/
├── spec.md
├── plan.md              # este arquivo
├── tasks.md
├── controle.md          # do implementer, não deste plano
└── checklists/requirements.md
```

### Source Code (repository root)

```text
platform/identity/enrolment.py                          # novo: a abertura e a criação de administrador
platform/identity/local_accounts.py                     # a porta passa a ser o fato, não o campo
platform/identity/errors.py                             # recusas novas, escritas para gente
platform/persistence/ports/identity_repository.py       # porta da abertura; e-mail ausente declarado
platform/persistence/postgres/models.py                 # tabela da abertura; índice parcial de e-mail
platform/persistence/postgres/repositories/identity_repository.py
platform/persistence/fakes/identity_repository.py
platform/persistence/migrations/versions/0015_*.py      # abertura do sign-in local
platform/persistence/migrations/versions/0016_*.py      # e-mail ausente fora da unicidade
platform/startup/bootstrap.py                           # gating da emissão; convite reescrito
gateway/http/serve.py                                   # imprime o convite novo
gateway/http/asgi.py                                    # composition root do sign-in
gateway/http/routes/first_run.py                        # a troca passa a criar conta com passphrase
gateway/http/routes/identity.py                         # colisão de e-mail com mensagem de gente
gateway/http/security/first_run_routes.py               # rota de disponibilidade declarada
config/constants/security.py                            # nomes e chave de exclusão
config/constants/first_run.py                           # o comando canônico, como texto único
surfaces/cli/commands/setup.py                          # `ninjasre setup admin`
console/src/app/sign-in/page.tsx                        # bloco de aviso
console/src/surfaces/screens/first-run.tsx              # mesmo bloco, mesma chave
console/src/surfaces/read.ts                            # leitura do fato de disponibilidade
fixtures/contract/openapi.json                          # regenerado
tests/unit/platform/identity/                           # porta, comando, recusas
tests/unit/platform/startup/test_bootstrap.py           # gating e convite
tests/unit/surfaces/cli/commands/test_setup.py          # o comando
tests/contract/persistence/test_identity_repository.py  # e-mail ausente nos dois backends
tests/contract/persistence/                             # a corrida, contra o Postgres real da suíte
tests/contract/deployment/test_first_run_sign_in.py     # o seam da troca
tests/contract/deployment/test_local_account_sign_in.py # a porta redefinida
tests/contract/deployment/test_compose_up.py            # a prova no caminho de serving
console/tests/unit/                                     # o bloco de aviso
console/tests/e2e/primeiro-administrador.acceptance.spec.ts
```

**Structure Decision**: um módulo novo em `platform/identity/`, porque a regra
tem dois clientes de produção (CLI e gateway) e precisa existir num lugar que
nenhum dos dois possua. Tudo o mais é mudança em arquivo que já existe.

## Decisões de design

- **O comando é o caminho canônico, e a razão é a superfície.** Das três formas
  que o backlog analisou, é a única que não acrescenta porta na rede. Quem pode
  executá-lo já tem shell no host, já pode ler o banco e as variáveis de
  ambiente; a conta que ele cria não concede nada de novo a quem o rodou. Não
  há janela para fechar, logo não há janela que possa ficar aberta por acidente
  — e é essa ausência, não uma implementação cuidadosa, que satisfaz o segundo
  critério do backlog.

- **A tela de first-run que cria a conta foi recusada, e a recusa é o que
  permite a afirmação forte.** Ela é a mais descobrível das três, e é também a
  única que instala uma rota não autenticada cuja correção depende de fechar
  direito sob réplicas, sob arquivo de estado divergente do banco e sob
  identity provider. Sem ela, esta feature pode afirmar sem asterisco: nenhuma
  rota não autenticada cria administrador. A tela mantém o papel que sobrou —
  ela **nomeia** o mecanismo.

- **A credencial impressa no boot vira convite, não segunda porta.** Ela já
  existe, já tem vida curta, já é gasta na troca, já tem duas permissões. O que
  muda é que ela para de ser emitida quando o deployment já é administrado ou
  tem identity provider ativo, e que o bloco impresso passa a nomear o comando.
  O bloco de hoje diz "Sign in with this credential" e isso é falso; corrigir a
  frase é parte do trabalho, não um detalhe de redação.

- **A porta é um fato do banco, e é por isso que a invariante sobrevive.** O
  raciocínio de `local_accounts.py` diz que a porta é o campo estar
  configurado, deployment-wide, e que criar um principal não abre porta
  nenhuma. Generalizar de "o campo está configurado" para "há abertura
  registrada" preserva as duas metades: só um ato deliberado registra a
  abertura, e a rota de criação de principal continua não a registrando. Sem a
  tabela, a inferência natural — "existe usuário com passphrase" — quebraria
  exatamente essa segunda metade.

- **A leitura da abertura é por tentativa; a conta de ambiente continua sendo
  resolvida na construção.** A abertura muda em tempo de execução (alguém roda o
  comando com o processo de pé) e precisa valer sem reiniciar. A conta de
  ambiente não muda em tempo de execução e continua sendo resolvida no boot,
  porque é isso que faz um deployment carregando a passphrase embarcada falhar
  ao subir em vez de falhar na frente de alguém.

- **O custo do caminho de recusa não muda de forma.** A leitura da abertura é
  uma consulta indexada, feita incondicionalmente antes do ramo, sem hash. As
  duas verificações de passphrase que hoje acontecem sempre continuam
  acontecendo sempre. Nada nesta feature acrescenta uma verificação por
  administrador cadastrado — administradores criados são usuários com passphrase
  armazenada e caem no caminho de resolução por endereço que já existe, com
  custo fixo.

- **A corrida tem dois árbitros e o de baixo é o que decide.** A chave primária
  do registro de abertura é o árbitro final: inserir e não sobrescrever, ler de
  volta, e quem leu a linha de outro perdeu. Por cima disso, o mesmo tipo de
  exclusão que o boot já usa para migrações, com chave própria, para que o
  caminho comum não chegue a colidir. Inventar um segundo mecanismo de
  coordenação seria a decisão errada num repositório que já tem um.

- **O e-mail ausente sai da unicidade em vez de ganhar um valor sentinela.**
  Dar ao principal de bootstrap um endereço sintético resolveria o sintoma e
  criaria um endereço que parece um endereço, que a busca encontra e que uma
  tela imprime. A forma escolhida é a dobra ficar ausente quando não há
  endereço, e o índice de unicidade passar a ignorar as ausências. A busca por
  endereço vazio deixa de casar com essas linhas, o que é o comportamento certo
  e hoje não é garantido.

- **A descida da migração é honesta sobre o que não pode desfazer.** Se dois
  principals sem endereço existirem, voltar à unicidade total é impossível sem
  perder um deles. A descida não escolhe por conta própria: ela recusa nomeando
  os principals e dizendo que um endereço precisa ser dado a todos menos um. É
  reversível no sentido que importa — nada foi destruído e o operador sabe o
  que decidir.

- **A mensagem de colisão é traduzida na fronteira que já traduz.** O
  repositório Postgres já converte violações em erros de domínio ao redor do
  flush. A colisão de endereço passa por ali e sai nomeando o endereço. A
  verificação prévia na rota de identidade fica onde está: ela dá a mensagem
  boa no caso comum, e a tradução cobre a corrida que ela não pega.

- **O aviso na tela revela "não reclamado" e nada além.** O fato servido é
  ternário — sem administrador, administrado, identity provider — e não carrega
  nome de deployment, versão, organização nem contagem. Ele revela que o
  deployment está sem dono, o que é uma informação real; o que ela não dá é uma
  forma de entrar, porque abrir a porta exige shell no host ou o arquivo de
  credencial. A decisão de aceitar essa revelação está registrada, e a
  alternativa (restringir o aviso) é uma questão aberta para o operador.

- **A recusa de sign-in não é tocada.** O bloco de aviso é uma região da
  página, resolvida antes de qualquer tentativa. Ele não é escrito no lugar de
  uma recusa, não a enriquece e não muda o que ela distingue. Um teste guarda
  isso explicitamente, porque é o ponto onde uma mudança bem-intencionada
  destruiria a propriedade que a recusa única existe para ter.

- **O identity provider é lido de uma fonte só.** O estado ativo da
  configuração de single sign-on já existe e o console já o lê. Esta feature lê
  o mesmo, pelo mesmo serviço de configuração, e não introduz uma segunda
  noção de "tem IdP" que pudesse discordar da primeira.

- **Sem `--force` no caminho do identity provider.** Um operador trancado para
  fora por um identity provider quebrado tem o caminho de emergência que o
  produto já tem — prazo, motivo escrito, log em nível de erro. A recusa aponta
  para ele. Uma opção de override aqui seria a segunda porta que o critério
  proíbe, com um nome que a faz parecer segura.

- **O CLI é o dono das duas perguntas seguintes.** "Como troco a passphrase" e
  "como crio o segundo administrador" são o mesmo comando: nome novo cria, nome
  existente recusa dizendo como rotacionar, rotação explícita rotaciona. Nenhuma
  das duas exige variável de ambiente nem restart, que é o que hoje não tem
  resposta.
