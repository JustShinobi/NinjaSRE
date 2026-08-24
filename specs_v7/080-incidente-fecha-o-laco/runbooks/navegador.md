# Roteiro de navegador — o laço inteiro, com um humano no meio

**Para quem tem um navegador de verdade na mão**, não um Playwright. Cada passo
diz **onde clicar** e **o que a tela deve dizer** se o laço estiver fechado.
Onde a tela pode dizer outra coisa e ainda assim estar certa, isso está escrito
junto — porque um roteiro que só descreve o sucesso transforma qualquer desvio
em pânico.

As frases entre aspas são a **cópia real do catálogo em inglês**, lida de
`console/src/i18n/en.ts`. Se a sessão estiver em pt-BR a frase muda, e o
sentido não.

Base: `https://stg-ninjasre.lan.kyo.ninja`.

---

## Antes de abrir o navegador — três leituras que decidem o dia

Estas três respostas mudam o que você vai ver, e é melhor tê-las antes de estar
com a janela aberta e o contêiner parado.

### 1. O balcão de remediação compôs?

```sh
ssh root@192.168.68.159 "kubectl logs -n k3s-stg-ninjasre deploy/app --since=24h | grep -E 'remediation\.(control_plane_bound|control_plane_skipped|desk_composed|desk_skipped)'"
```

- `remediation.control_plane_bound` (com `integration`, `endpoints`, `trust`,
  `capabilities=13`) seguido de `remediation.desk_composed` (com `capabilities`
  e `profile=kubernetes`) ⇒ **o deployment sabe agir.** Siga.
- `remediation.desk_skipped` com uma lista `missing` ⇒ **o deployment não sabe
  agir**, e a linha diz de qual peça. As estações E7, E8 e E9 ficam **não
  exercidas**, com a lista `missing` anexada como evidência. Isso não é
  reprovação de tela nem falha de ambiente: é uma condição declarada do
  deployment, dita por ele mesmo.

O perfil de sandbox do staging é Kubernetes, então `_isolation` resolve e essa
não é a peça que pode faltar.

### 2. Quanto da história é anterior à coluna de manchete?

```sh
uv run python -m tools.demo_evidence plan --org <ORG_ID>
```

Pegue a consulta `E5/headline-coverage` e rode-a. Ela devolve `runs`,
`without_a_sentence` e `document_opens_with_syntax`.

**Isto explica uma coisa que já apareceu.** Duas regras transversais falham
contra o staging e passam contra a fixture — markdown cru e identificador como
nome, ambas em `/runs/{id}`. A fixture só tem runs com manchete; o staging tem
37 runs de antes de a coluna existir, todos com manchete vazia e `summary`
começando com `###`. Se `without_a_sentence` vier alto, essa é a explicação
mais provável: a suíte abre o **primeiro run da lista**, que é um run velho, e
mede o caminho de fallback em vez do caminho normal.

**O que isso significa para a demo:** o run da demo é **novo**, criado durante
a janela, e recebe a manchete no fechamento. A estação E5 deve passar para ele.
Se E5 falhar **para o run da demo**, aí sim é defeito de produto com dona.

Isto é hipótese, não veredito — quem apura de quem é o defeito é o verificador
independente. O que este roteiro faz é não confundir os dois casos.

### 3. O token do Proxmox pode ligar um convidado?

Religar exige `VM.PowerMgmt` no caminho `/vms`. Se o token for de leitura, a
estação E9 falha por privilégio — o que é um **desfecho registrável**, não uma
surpresa: grava-se a falha com a razão nomeada, e o plano de reversão não roda
porque nada mudou. Conceder escrita ao token é decisão do operador sobre
fronteira de segurança, não deste roteiro.

---

## Passo 0 — entrar

**Onde clicar:** abra `https://stg-ninjasre.lan.kyo.ninja`. Se aparecer o
formulário de acesso, entre com a credencial de operador — do cofre; este
arquivo não a transcreve.

**O que a tela deve dizer:** o painel inicial, com a navegação lateral. Se
aparecer um aviso de que este deployment não tem administrador, pare: o caminho
canônico é `ninjasre setup admin --name <nome>`, e isso é anterior à demo.

---

## Passo 1 — a fotografia do antes

Antes de derrubar nada, quatro telas. Screenshot full-page de cada uma, em
1920×1080. É o "antes" contra o qual todo o resto contrasta.

| Onde clicar | O que a tela deve dizer |
|---|---|
| `/settings/models-providers` | o provedor de modelo com o estado **Verified**. Se disser *Stored* ou *Configured*, a chave existe e ninguém a verificou — a investigação pode não rodar |
| `/integrations` | Proxmox conectado. Se houver recusa mencionando certificado, a frase traz **dois fingerprints** — o apresentado e o esperado. Se disser "Neither the credential proxy nor any configured Proxmox node answered", essa é a mensagem antiga e é achado de produto |
| `/resources` | recursos reais do Proxmox, com nome. Uma lista vazia aqui significa que o sujeito do incidente não vai resolver em E3 |
| `/decisions`, aba **Actions** | provavelmente "Nothing is waiting on a decision" — é o estado de partida correto |

---

## Passo 2 — o passo destrutivo

**Não é no navegador.** Uma pessoa digita, uma vez:

```sh
ssh root@192.168.68.159 'ssh pve01 "pct stop 122"'
```

**Anote a hora.** É a referência de tudo o que vem depois. Não emita alerta
nenhum: o alerta tem que disparar sozinho, e é isso que separa este roteiro do
laço de leitura.

A reversão manual vale a qualquer instante, não depende do produto, e não
espera por ele:

```sh
ssh root@192.168.68.159 'ssh pve01 "pct start 122"'
```

---

## Passo 3 — E1 e E2: o alerta dispara e a entrega chega

Espere o `for` da regra (2 minutos) mais o `group_wait` da rota. **Silêncio
antes disso é o esperado, não sintoma.**

**Onde clicar:** `/signals`, aba **Intake** — ou `/settings/alert-intake`.

**O que a tela deve dizer:** uma entrega recente, com origem, horário e
resultado, correspondente ao alerta da CT122.

**Se não houver entrega e o alerta estiver ativo no Alertmanager:** o mais
provável é que a origem não resolva o nome deste deployment — a tarefa
operacional de resolução de nomes, não o webhook. Desfecho de **ambiente**.

---

## Passo 4 — E3: o incidente abre

**Onde clicar:** `/incidents`, e então a linha do incidente novo.

**O que a tela deve dizer:**

- o **título é uma frase**, não um identificador. Um título como
  `alert:alertmanager:9f8e…` é defeito de produto;
- a **barra de endereço** mostra algo como `/incidents/inc_a1b2c3d4e5f60718` —
  **sem** `%3A`, `%40` ou `%2B`. Percent-encoding aqui é defeito de produto;
- **nenhum painel** diz que não foi possível preencher;
- o **chip de investigação** diz o estado real. Se disser "Unknown", isso é
  correto e deliberado: a tela admite que a leitura não respondeu, em vez de
  afirmar um negativo. Passe o mouse — o tooltip nomeia a dependência que
  falhou;
- o painel **"Proposed action"** ainda deve dizer **"Nothing proposed yet"** e
  *"No investigation has concluded with a remediation to decide on for this
  incident."* — a investigação nem terminou.

**Anote o endereço curto do incidente**, o que está na URL. É o `--incident` do
coletor.

---

## Passo 5 — E4: a investigação gravou

**Onde clicar:** do incidente, abra o run. **Depois recarregue a página.** O
ponto desta estação é ler do armazenamento, não do processo que rodou.

**O que a tela deve dizer:**

- o transcript lista **N chamadas de ferramenta**, cada uma com o que devolveu;
- a tabela de **custo por turno** tem uma linha por turno. Um turno sem preço
  aparece **vazio**, não como zero — zero é um preço, vazio é a ausência de um;
- o painel do que a investigação tocou está preenchido;
- **não há controle de run vivo** num run terminado. Um botão de cancelar num
  run concluído é defeito de produto.

**A pergunta desta estação é uma só:** a contagem na tela bate com a contagem
no banco? Rode o coletor com `--run` e compare.

---

## Passo 6 — E5: o relato é legível

**Onde clicar:** a mesma tela do run.

**O que a tela deve dizer:**

- o **título é uma sentença**;
- o relato é um **documento desenhado como documento** — cabeçalhos como
  cabeçalhos, listas como listas;
- **nenhum caractere de sintaxe markdown aparece como texto.**

**Se aparecer markdown cru:** antes de chamar de defeito, confira se este é o
run **da demo** ou um run velho — ver a leitura 2, no topo deste arquivo. Para
o run da demo, markdown cru é defeito de produto com dona; para um run anterior
à coluna de manchete, é o caminho de fallback, e é outra conversa.

---

## Passo 7 — E6: as ferramentas condizem

**Onde clicar:** `/agent`.

**O que a tela deve dizer:** as capacidades que este deployment de fato pode
usar. Nenhuma de vendor não conectado.

E no log, o que foi excluído e por quê:

```sh
ssh root@192.168.68.159 "kubectl logs -n k3s-stg-ninjasre deploy/app --since=2h | grep -E 'tool_selection|integrations_unresolved|zero_integration'"
```

**Uma consequência declarada, para não assustar:** com o balcão composto,
quatro capacidades acima de leitura sensível deixam de ser oferecidas —
`alertmanager_acknowledge_incident`, `propose_knowledge`,
`pushover_post_message` e `telegram_post_message`. Elas não têm componentes de
remediação registrados, e o filtro está fazendo exatamente o que deve. É
mudança de comportamento visível e conhecida, não regressão.

---

## Passo 8 — E7: a proposta aguarda

**Onde clicar:** `/decisions`, aba **Actions**. Depois volte ao incidente e
role até o painel **"Proposed action"**.

**O que a tela deve dizer, no painel do incidente:**

- o chip **"Awaiting decision"**;
- a frase **"Posture is {postura} — nothing runs without you."**;
- o **alcance**: "1 resource" — um recurso, sem efeito sobre vizinhos;
- **"Rollback plan"** com os passos. Se aparecer **"No rollback plan — this
  change is irreversible."**, pare: a remediação escolhida devia ser reversível;
- um campo **"Reason"**, um botão **"Approve and run"** e um botão **"Reject"**.

**Se o painel disser "Nothing proposed yet":** dois casos, e eles são
diferentes.

1. **A investigação concluiu sem evidência suficiente para propor.** Isso é
   **correto**. O run vira cenário de leitura, e o laço inteiro reexecuta com
   outra ocorrência.
2. **O balcão não compôs** — leitura 1, no topo. E7 a E9 ficam **não
   exercidas**, com a lista `missing` anexada.

**Nada é aprovado ainda.**

---

## Passo 9 — PARE E CONFIRA E4 A E7

Este passo não produz evidência, e existe mesmo assim.

A aprovação **encerra** a única execução que responde "o registro ficou
completo?". Depois dela o run não volta ao estado em que estava, e você terá
capturado o depois sem ter capturado o antes.

Confira as quatro estações. Só então siga.

---

## Passo 10 — E8: aprovar, olhando

**Onde clicar:** no painel **"Proposed action"** do incidente, escreva um motivo
no campo **"Reason"** — opcional para aprovar, e vale a pena, porque ele vai
para a auditoria — e clique em **"Approve and run"**.

**O que a tela deve dizer depois:** o chip muda para **"Approved"**. Se
aparecer **"The decision was not recorded. Try again."**, a decisão **não**
aconteceu; não é um aviso cosmético.

### O que o botão faz, exatamente — e o que ele não diz

O rótulo diz "Approve and run", e a ordem no servidor é esta, nesta sequência:

1. a decisão é gravada — estado, decisor, instante e motivo — e a transação
   fecha;
2. o evento de auditoria é gravado, com `action = approval.decide` e
   `outcome = allowed`;
3. **só então** a execução é levada adiante pelo gate.

**Aprovar exige que o plano de reversão já esteja gravado.** Não é convenção:
aprovar sem plano devolve `400`, e é por isso que a ordem "plano antes da
execução" não depende de ninguém lembrar dela.

**E a armadilha que você precisa conhecer:** se a execução falhar, a rota
**mesmo assim devolve sucesso**, de propósito — uma falha em agir é um fato
sobre este deployment, e transformá-la em erro diria ao revisor que a decisão
dele não foi registrada quando foi. Então **a tela dizendo "Approved" não
significa que a ação rodou.** Quem responde isso é o log:

```sh
ssh root@192.168.68.159 "kubectl logs -n k3s-stg-ninjasre deploy/app --since=1h | grep -E 'remediation\.approval_(carried_out|not_carried_out)'"
```

- `remediation.approval_carried_out`, com `permitted` e `reason` ⇒ passou pelo
  gate;
- `remediation.approval_not_carried_out`, com `reason` ⇒ não passou, e a linha
  diz por quê: sem balcão, ou sem componentes para a capacidade.

---

## Passo 11 — E9: a execução

**Fora do navegador:**

```sh
ssh root@192.168.68.159 'ssh pve01 "pct status 122"'
```

**O que se espera:** `status: running`.

**No navegador:** volte ao incidente e recarregue.

**Uma falha nomeada aqui é desfecho legítimo** — privilégio insuficiente,
quorum ausente, convidado travado. Grava-se a falha com a razão, e o plano de
reversão não roda porque nada mudou. **Falha nomeada fecha o laço com desfecho
negativo; o que não fecha o laço é falha silenciosa.**

---

## Passo 12 — E10: o incidente reflete o desfecho

**Onde clicar:** `/incidents/{endereço}`.

**O que a tela deve dizer:** a linha do tempo do incidente ganhou a entrada da
ação, e o incidente mostra o desfecho — em vez de continuar parado no
diagnóstico.

Screenshot full-page.

---

## Passo 13 — reversão, antes da evidência

```sh
ssh root@192.168.68.159 'ssh pve01 "pct status 122"'
```

**Se não estiver `running`, religue à mão agora.** Este passo não é opcional e
não espera pela coleta. A validação não deixa o serviço refém dela.

---

## Passo 14 — a rejeição, em ocorrência diferente

**Nunca na mesma proposta que foi aprovada.** Use outro alerta real com
proposta, ou uma segunda janela.

| Passo | Onde clicar | O que a tela deve dizer |
|---|---|---|
| R1 | No painel **"Proposed action"**, deixe **"Reason" vazio** e olhe o botão **"Reject"** | ele está **desabilitado**, e ao lado aparece **"A reason is required to reject."** — a recusa sem motivo é impedida *antes* do clique, com a razão escrita. Não espere uma mensagem de erro: espere um controle desabilitado que diz por quê |
| R2 | Escreva um motivo e clique em **"Reject"** | o chip muda para **"Rejected"**. Nada executa |
| R3 | `/administration`, aba **Audit** — ou `/settings/audit-log` | as **duas** decisões, com autor, ação, assunto e resultado: a aprovação com `outcome = allowed` e a rejeição com `outcome = denied`, ambas com `action = approval.decide` |

Um caminho de aprovação que nunca recusou não foi exercitado.

---

## Passo 15 — fechar

Registre o instante de fechamento em `evidence/EVIDENCIA.md`, e rode o coletor
uma última vez com **todos** os parâmetros:

```sh
uv run python -m tools.demo_evidence collect \
  --org <ORG_ID> --run <RUN_ID> --incident <INCIDENT_ID> \
  --approval <APPROVAL_ID> --resource <RESOURCE_ID> \
  --out specs_v7/080-incidente-fecha-o-laco/evidence/consultas \
  --exec "ssh root@192.168.68.159 kubectl exec -i -n k3s-stg-ninjasre deploy/app -- sh -c 'psql -X -q -v ON_ERROR_STOP=1 \"\$NINJASRE_DATABASE_URL\"'"
```

E varra a evidência inteira — texto **e screenshots** — atrás de credencial,
token, chave ou senha. Uma screenshot com um valor de token é um vazamento tão
real quanto um commit com ele.

Ao conferir vazamento, **não passe o segredo como argumento do `grep`**: o
próprio `grep` nasce com ele em `argv`, e o resultado é sempre falso positivo.
Use um arquivo de padrões.
