# Roteiro — o laço inteiro

**O que este roteiro é.** Uma janela combinada em que o operador para um
contêiner descartável e observado e assiste — sem tocar em mais nada — o alerta
disparar sozinho, o incidente abrir, a investigação rodar e gravar, o relato
aparecer legível, a proposta de religar surgir com plano de reversão, e a
execução acontecer **só depois** de ele aprovar, olhando.

**O que este roteiro não é.**

- **Não é um script.** O passo destrutivo é digitado por uma pessoa, uma vez.
  Não existe automação, laço ou alvo de `make` que o execute, e criar um seria
  transformar a única prova de que uma pessoa decidiu em mais uma linha de log.
- **Não é reexecutável à vontade.** Uma vítima por vez, uma janela por vez.
  Nenhum segundo recurso é derrubado para "testar de novo" sem nova combinação
  com o operador.
- **Não emite alerta sintético.** O alerta dispara por conta própria ou a
  estação reprova como ambiente. Um alerta injetado à mão prova que o webhook
  aceita POST, que é a coisa que ninguém duvidava.
- **Não aprova por API.** A aprovação é dada por uma pessoa, na interface. Uma
  aprovação por chamada de API é uma aprovação que o produto poderia ter dado a
  si mesmo, e a frase "aprovação humana" perde o sentido no exato instante em
  que ela passa a importar.

**Quem precisa estar ciente antes.** O operador (é ele quem digita o passo
destrutivo e quem aprova) e quem quer que dependa do serviço da vítima. A
combinação é anterior ao roteiro, não parte dele.

---

## 0. Onde as coisas ficam, e o comando do coletor

Idênticos aos de `laco-de-leitura.md`, seções 0 e 1. Em resumo:

```sh
uv run python -m tools.demo_evidence collect \
  --org <ORG_ID> --run <RUN_ID> --incident <INCIDENT_ID> \
  --approval <APPROVAL_ID> --resource <RESOURCE_ID> \
  --out specs_v7/080-incidente-fecha-o-laco/evidence/consultas \
  --exec "ssh root@192.168.68.159 kubectl exec -i -n k3s-stg-ninjasre deploy/app -- sh -c 'psql -X -q -v ON_ERROR_STOP=1 \"\$NINJASRE_DATABASE_URL\"'"
```

**Nenhum segredo é transcrito neste arquivo.** A string de conexão é resolvida
de dentro do pod; a credencial do console vem do cofre do operador; o token do
Proxmox nunca é lido por ninguém aqui — ele fica atrás do proxy de credencial,
que é o único a vê-lo.

---

## 1. A REVERSÃO MANUAL — escrita antes de qualquer mudança

Este bloco vem **antes** do passo destrutivo de propósito. A reversão é
escrita antes de a mudança acontecer, nunca depois.

```sh
ssh root@192.168.68.159 'ssh pve01 "pct start 122"'
ssh root@192.168.68.159 'ssh pve01 "pct status 122"'
```

**Ela vale a qualquer instante e não depende do produto.** Se qualquer coisa
parecer errada — em qualquer estação, antes ou depois da aprovação, com a
proposta pendente ou rejeitada — religue o contêiner **sem esperar pelo
produto**. A validação não deixa o serviço refém dela, e não há passo deste
roteiro cuja evidência valha mais que o serviço voltar.

Se a vítima for outra que não a CT122 (ver §3, P6), substitua o VMID e o nó
neste bloco **antes** de seguir.

---

## 2. A vítima: descartável **e** observada

Uma vítima precisa ser as duas coisas ao mesmo tempo. A maioria dos contêineres
de um homelab é só a primeira, e **não existe regra que dispare quando um LXC
qualquer para** — parar um contêiner invisível às regras faz o roteiro morrer na
primeira estação sem que isso seja defeito do produto.

| Fato | Valor | Como se confere |
|---|---|---|
| Identidade | `redis`, CT122, nó `pve01`, `10.20.20.52` | `pct status 122` em `pve01` |
| Por que é descartável | declarada fora de uso; autorizada pelo operador na validação anterior — **e reconfirmada na abertura da janela** | resposta do operador, registrada em P6 |
| Qual regra a observa | alvo de scrape `10.20.20.52:9121` do job `redis-exporter`; `InstanceDown` (`up{job!="pve-exporter"} == 0`) e `RedisExporterDown`, ambas `for: 2m`, `severity: critical` | a regra, lida do Prometheus da stack |
| Como se reverte à mão | `pct start 122` em `pve01` | §1 |

`RedisInstanceDown` **tende a não disparar**: a série `redis_up` some em vez de
zerar quando o exporter cai junto. Isso é esperado e não é sintoma.

**Vítimas que não servem, e por quê**: `streamlink-webui` (CT139) e `bazarr`
(CT103) não são alvo de scrape nem de sonda — pará-las não dispara nada. A CT139
já estava parada em 2026-08-20. **O contêiner do próprio deployment nunca é
vítima**: derrubá-lo mede a ausência do observador, não o produto.

**Se a `redis` for recusada pelo operador**: a candidata alternativa é qualquer
alvo de scrape ou sonda real cujo serviço ele declare dispensável por dez
minutos. A identidade da vítima é parâmetro conferido no primeiro passo
justamente para que a troca não exija reescrever o roteiro — troque §1, §2 e P7,
e siga.

---

## 3. Pré-condições — a janela não abre sem todas

| # | O que conferir | Comando / onde | Se falhar |
|---|---|---|---|
| P1 | Todas as features da onda mergeadas e publicadas; Argo `Synced + Healthy` | `ssh root@192.168.68.159 'kubectl get application stg-ninjasre -n argocd'` | **ambiente** — a demo não começa |
| P2 | O serviço responde, conferido separadamente de P1 | `curl -sf -o /dev/null -w '%{http_code}\n' https://stg-ninjasre.lan.kyo.ninja/` e `kubectl exec -n k3s-stg-ninjasre deploy/app -- curl -s http://localhost:8420/health/ready` | **ambiente** |
| P3 | O provedor de modelo está **Verified**, e a chave vem do cofre | `/settings/models-providers` | E4 não roda; **ambiente** se for chave, achado da 030 se as duas telas discordarem |
| P4 | O Proxmox está conectado, com a confiança de certificado declarada, e `/resources` lista recursos reais | `/integrations` e `/resources` | E3 mostra sujeito não resolvido; E9 não tem por onde chegar ao vendor |
| P5 | O token do Proxmox tem gerência de energia de convidados (`VM.PowerMgmt` no caminho `/vms`) — **sem alterar o token** | o console do Proxmox, na tela de tokens de API | **decisão pendente do operador**: conceder escrita ao token do produto é decisão de fronteira de segurança dele. E9 fica **não exercível**, e é marcada assim, nunca aprovada por omissão |
| P6 | O operador confirma a vítima, **na abertura da janela** | pergunta direta, resposta registrada | **nenhum passo destrutivo acontece sem esta resposta** |
| P7 | A vítima está **running** | `ssh root@192.168.68.159 'ssh pve01 "pct status 122"'` | **INTERROMPER** — ver a caixa abaixo |
| P8 | A regra que cobre a vítima existe e está ativa; a rota do Alertmanager casa a severidade que ela emite | Prometheus e Alertmanager da stack | E1 falharia por ausência de regra, e alguém leria isso como defeito do produto |
| P9 | O webhook recusa sem credencial | a sonda de recusa de `laco-de-leitura.md`, Passo 2 | achado de produto |
| P10 | O balcão de remediação compôs | `kubectl logs deploy/app \| grep remediation.desk_` | se `desk_skipped`, E7 a E9 ficam **não exercidas** com a lista `missing` anexada |
| P11 | O gabarito rodou a seco e devolveu os valores de partida | `tools.demo_evidence collect` **antes** da demo | sem isto a evidência posterior não tem contraste |

> ### P7 é uma parada, não um aviso
>
> **A vítima já parada interrompe o roteiro.** O passo destrutivo não pode parar
> o que já está parado, e um alerta que já estava disparando não foi disparado
> por este teste. Seguir assim é colher um incidente verdadeiro e concluir dele
> uma coisa falsa — o pior desfecho possível deste roteiro, pior que não
> executá-lo.
>
> Se ela estiver parada: religue-a (§1), espere o alerta resolver, confirme
> `running`, e só então reabra a janela.

---

## 4. A tabela de estações

| Estação | O que se espera ver | Onde se olha | Evidência exigida |
|---|---|---|---|
| **E1** — o alerta dispara sozinho | O alerta ativo no Alertmanager, com o instante, sem ninguém o ter emitido | Alertmanager da stack | saída literal da listagem, com o instante |
| **E2** — a entrega chega autenticada | A entrega registrada com origem, horário e resultado | `/settings/alert-intake` | screenshot full-page |
| **E3** — o incidente abre legível | Título que é uma frase; sujeito resolvido; zero painéis "não foi possível preencher"; nenhum `%3A`/`%40`/`%2B` na URL | `/incidents`, `/incidents/{endereço}` | screenshot full-page + consultas `E3-*` |
| **E4** — a investigação grava | Turnos, chamadas com o que cada uma devolveu, evidência e custo por turno — lidos **depois de um reload** | `/runs/{runId}` | screenshot full-page + consultas `E4-*` |
| **E5** — o relato é legível | Título é uma sentença; relato é documento renderizado; nenhum caractere de sintaxe como texto | `/runs/{runId}` | screenshot full-page + consulta `E5-sentenca` |
| **E6** — as ferramentas condizem | Nenhuma capacidade de vendor não conectado; nenhuma remediação oferecida só para recusar | transcript + log da seleção | screenshot + saída do log |
| **E7** — a proposta aguarda | Proposta com plano de reversão, alcance de um recurso, postura declarada, chip aguardando decisão | `/decisions` e o painel no incidente | screenshot full-page + consultas `E7-*` |
| **E8** — o humano aprova | Decisão, decisor e instante gravados **antes** de qualquer efeito; plano de reversão já registrado antes | `/decisions`, pela interface | screenshot + consultas `E8-*` + evento de auditoria |
| **E9** — a execução pelo gate | O convidado voltando a rodar; desfecho gravado; episódio gravado; entrada de ação na timeline | `pct status`, `/runs/{runId}`, incidente | `pct status` + consultas `E9-*` |
| **E10** — o incidente reflete o desfecho | O incidente mostra o que aconteceu, em vez de continuar parado no diagnóstico | `/incidents/{endereço}` | screenshot full-page + consultas `E10-*` |

---

## 5. Classificação de desfechos, escrita antes da execução

Regra: **se a mesma execução, repetida amanhã sem mudar uma linha de código,
tem chance razoável de passar, é ambiente. Se ela vai falhar igual até alguém
mudar código, é produto.**

| Estação | **Ambiente** (reexecuta; o que reconferir e por onde reentrar) | **Produto** (bloqueia) e a feature dona |
|---|---|---|
| E1 | Não disparou dentro do `for` da regra mais o `group_wait` da rota ⇒ reconferir: a regra existe e está ativa (P8), o alvo de scrape é o que se pensa, a rota casa `severity: critical`. Reentrar em P7. **Silêncio antes do `for` é o esperado, não sintoma** | — |
| E2 | O alerta disparou e a entrega não chegou **porque a origem não resolve o nome do deployment** ⇒ é a tarefa operacional de resolução de nomes; reentrar depois dela | Entrega aceita sem credencial, ou recusada com a credencial correta ⇒ *dona: a borda de webhooks* |
| E3 | O incidente ainda não abriu (agrupamento do Alertmanager) ⇒ esperar o `group_interval` | Título é identificador; painel irrecuperável; URL percent-encoded ⇒ *dona: identidade endereçável (020)*. Sujeito não resolve com o recurso no estate ⇒ *dona: uma fonte por fato (030)* |
| E4 | A investigação ainda roda ⇒ esperar e recarregar | Contagem da tela ≠ contagem do banco; transcript vazio com `tool_calls > 0`; custo em branco havendo turno ⇒ *donas: registro do que o agente fez (001) e leitura do relato (010)* |
| E5 | — | Markdown cru como texto; título que é o documento ⇒ *dona: leitura do relato (010)* |
| E6 | — | Ferramenta de vendor não conectado oferecida; remediação oferecida sem balcão composto ⇒ *dona: decisão composta (040)* |
| E7 | **A investigação concluiu sem evidência suficiente para propor** ⇒ nenhuma proposta aparece, **e isso é correto**. O run vira cenário de leitura e o laço inteiro reexecuta com outra ocorrência. Também: `desk_skipped` no log ⇒ E7–E9 **não exercidas**, com a lista `missing` anexada | Proposta no banco e `/decisions` dizendo que está vazio por outra razão; proposta sem plano de reversão ⇒ *donas: decisão composta (040) e uma fonte por fato (030)* |
| E8 | — | Decisão gravada **depois** do efeito; plano de reversão gravado depois da execução; aprovação sem decisor ou sem instante ⇒ *dona: decisão composta (040)* |
| E9 | Falha no vendor por privilégio insuficiente, quorum ausente ou guest travado ⇒ grava-se **a falha, com a razão nomeada**, e o plano de reversão não roda porque nada mudou. **Falha nomeada fecha o laço com desfecho negativo; o que não fecha o laço é falha silenciosa** | A execução age sobre "o mesmo número em outro nó" depois de o convidado migrar; a execução acontece sem passar pelo gate; a recusa da chamada direta deixou de valer ⇒ *dona: decisão composta (040)* |
| E10 | — | O incidente continua parado no diagnóstico com desfecho gravado no banco ⇒ *donas: decisão composta (040) e identidade endereçável (020)* |

### Casos de borda declarados antes, não decididos na hora

- **Alguém religa o contêiner à mão antes da aprovação.** A proposta continua
  **aguardando** e não vira executada sozinha. Aprovar depois disso encontra o
  recurso já no estado desejado e registra **esse** resultado, em vez de fingir
  que agiu. Esse é o desfecho correto e ele é evidência tão boa quanto o sucesso.
- **A aprovação expira antes de o operador decidir.** A proposta expirada é um
  desfecho legítimo e registrado. A demo reexecuta a partir da investigação, e a
  expiração **não é apagada** do registro.
- **O convidado migrou de nó entre a proposta e a aprovação.** O alvo aprovado
  deixou de ser o alvo real. A execução não pode agir sobre o mesmo número em
  outro nó; se ela agir, é defeito de produto com dona, e o roteiro registra
  assim.
- **Uma tarefa operacional não foi executada.** Não bloqueia a demo, salvo se a
  estação depender dela — nesse caso a estação é marcada **não exercida**, e a
  tarefa entra no backlog novo com o estado real.
- **Um defeito de uma feature já dada como PASS.** Volta como reparo da feature
  dona, dentro do limite de ciclos de reparo da onda. Este roteiro não o
  conserta e não o esconde. Depois de um reparo aceito, **a estação afetada é
  reexecutada e a evidência é substituída**, nunca acumulada como se as duas
  capturas fossem verdadeiras ao mesmo tempo.

---

## 6. A janela

### Passo 0 — abrir

Registre o instante de abertura e a confirmação verbal da vítima (P6).
**Reconfira `pct status`** — o estado pode ter mudado desde P7.

### Passo 1 — O PASSO DESTRUTIVO

Digitado por uma pessoa, uma vez:

```sh
ssh root@192.168.68.159 'ssh pve01 "pct stop 122"'
```

**Anote a hora.** Ela é a referência de tudo o que vem depois.

**Não emita alerta nenhum.** O alerta tem que disparar por conta própria, e é
isso — e só isso — que separa este roteiro do laço de leitura.

A partir daqui, **nada mais é digitado até a estação E7**. Ficar assistindo é o
trabalho.

### Passo 2 — E1: o alerta dispara sozinho

Espere o `for` da regra (2 minutos) mais o `group_wait` da rota. Registre o
alerta ativo no Alertmanager com o instante, e registre que ninguém o emitiu.

### Passo 3 — E2: a entrega chega autenticada

`/settings/alert-intake` — a entrega correspondente, com origem, horário e
resultado. Screenshot full-page.

### Passo 4 — E3: o incidente abre

`/incidents` → o detalhe. Anote o endereço curto do incidente. Screenshot
full-page das duas telas.

### Passo 5 — E4: a investigação grava

`/runs/{runId}`, **depois de um reload**. Screenshot full-page. Rode o coletor
com `--run` e `--incident` e anexe as contagens e o custo por turno.

A pergunta desta estação é uma só: **a contagem na tela bate com a contagem no
banco?**

### Passo 6 — E5: o relato é legível

Screenshot full-page. Anexe a consulta que mostra a sentença separada do
documento.

### Passo 7 — E6: as ferramentas condizem

Transcript mais a lista de ferramentas do agente e as exclusões registradas no
log.

### Passo 8 — E7: a proposta aguarda

`/decisions` e o painel de ação no incidente. Screenshot full-page das duas.
Anexe as consultas de `approvals` e `rollback_plans`. Anote o identificador da
aprovação e o do recurso.

### Passo 9 — **CONFERIR E4 A E7 ANTES DE APROVAR**

Este passo não produz evidência nova, e existe mesmo assim.

A aprovação é o último passo e ela **encerra** a única execução que responde "o
registro ficou completo?". Aprovar antes de olhar o transcript, o custo, o
relato e a proposta desperdiça a janela: depois da execução, o run terminado não
volta ao estado em que estava, e você terá capturado o depois sem ter capturado
o antes.

Confira as quatro estações. Só então siga.

### Passo 10 — E8: o humano aprova

**Pela interface, olhando.** Registre o instante.

Anexe: a consulta que mostra estado, decisor, instante e motivo em `approvals`,
e o evento de auditoria correspondente. Confira que decisão, decisor e instante
foram gravados **antes** de qualquer efeito, e que o plano de reversão já estava
registrado.

### Passo 11 — E9: a execução acontece pelo gate

Evidência: `pct status 122` dizendo `running`; o desfecho em
`remediation_outcomes`; o episódio em `episodes`; a entrada de ação na timeline
do incidente.

Uma falha nomeada aqui é um desfecho legítimo — veja a linha E9 da §5.

### Passo 12 — E10: o incidente reflete o desfecho

Screenshot full-page do detalhe do incidente depois da execução. Anexe as
consultas de `incident_timeline` e `incidents`.

### Passo 13 — o alerta resolve

Confira que o alerta resolveu e que a resolução fechou o incidente que a
abertura criou.

### Passo 14 — reversão

**Confirme que o convidado está `running`.** Se a execução não o religou,
religue à mão imediatamente (§1). Este passo não é opcional e não espera pela
evidência.

### Passo 15 — fechar a janela

Registre o instante de fechamento e o resumo do que aconteceu em
`evidence/EVIDENCIA.md`.

---

## 7. A estação de rejeição

**Em ocorrência diferente da que foi aprovada.** Nunca na mesma: rejeitar a
proposta que já foi aprovada não exercita o caminho de recusa, exercita a
ausência de idempotência.

A segunda ocorrência é outro alerta real já ativo com proposta, ou uma segunda
janela combinada — a escolha é do operador e fica registrada.

| Passo | O que fazer | O que se espera |
|---|---|---|
| R1 | Rejeitar **sem motivo** | **é recusado**, nomeando que o motivo é obrigatório. Screenshot |
| R2 | Rejeitar **com motivo** | **é registrado**: estado, decisor, instante e motivo. Screenshot + consulta de `approvals` |
| R3 | Conferir a auditoria | a aprovação do Passo 10 **e** a rejeição de R2 aparecem com autor, ação, assunto e resultado. Saída literal anexada |

Um caminho de aprovação que nunca recusou não foi exercitado.

---

## 8. O que este roteiro entrega

- `evidence/EVIDENCIA.md` preenchido estação por estação: expectativa,
  evidência, consulta, saída literal, veredito e **instante** — de modo que a
  ordem temporal do laço seja auditável.
- Screenshots full-page em 1920×1080 em `evidence/telas/`, uma por estação que
  é tela, nomeadas pela estação.
- Um arquivo por estação em `evidence/consultas/`, com a consulta e a saída
  literal, e o valor de partida ao lado.
- O digest publicado e o estado do Argo no instante da demo — uma evidência que
  não aponta uma versão prova algo sobre um sistema que não se sabe qual era.

**A evidência não é entregue** antes da varredura por credencial, token, chave
ou senha — em texto **e dentro das screenshots**. Uma screenshot com um valor de
token é um vazamento tão real quanto um commit com ele.
