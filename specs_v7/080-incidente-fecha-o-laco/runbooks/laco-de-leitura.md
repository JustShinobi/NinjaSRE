# Roteiro — o laço de leitura

**O que este roteiro é.** Uma travessia de ponta a ponta que começa num alerta
que **já está** disparando e termina na proposta de remediação. Ele lê; não
escreve nada no estate, não aprova nada, não derruba nada.

**O que este roteiro não é.** Não é a demo do laço inteiro. Nada aqui pede
janela combinada, nada aqui pede que o operador esteja acordado, e nada aqui
altera o mundo. Se um passo pedir para você aprovar alguma coisa, você está no
roteiro errado — o outro é `laco-inteiro.md`.

**Quem pode executar.** Qualquer pessoa com acesso de leitura ao console de
staging e ao banco. Não é preciso ter participado da onda. Tempo esperado: 15
minutos.

**Quantas vezes.** Quantas quiser. Executar duas vezes seguidas e comparar a
evidência é parte do roteiro (passo final).

---

## 0. Onde as coisas ficam

| Coisa | Onde |
|---|---|
| Console | `https://stg-ninjasre.lan.kyo.ninja` |
| Gateway (webhooks) | `https://stg-ninjasre.lan.kyo.ninja/webhooks/alertmanager` |
| Namespace | `k3s-stg-ninjasre` (k3s) |
| Banco | `ninjasre-stg-db`, `10.20.20.54` |
| Host de infraestrutura | alcançado por `ssh root@192.168.68.159` |

**Segredos.** Este roteiro não transcreve nenhum. Onde ele precisa de um, ele
diz **onde buscá-lo**:

| Segredo | Onde está |
|---|---|
| Usuário e senha do console | o cofre do operador; nunca neste arquivo |
| String de conexão do banco | a variável `NINJASRE_DATABASE_URL` **de dentro do pod** `app` |
| Credencial do webhook | o `Secret` do namespace que o Alertmanager já usa |
| Token do Proxmox | o proxy de credencial; nunca lido por nada aqui |

Se você se pegou copiando um valor para dentro de um arquivo de evidência,
pare: a varredura de segredo (`laco-inteiro.md`, passo de fechamento) reprova a
evidência inteira por isso.

---

## 1. O coletor de evidência — o comando exato

Toda estação que alega gravação é provada por uma consulta com **a saída
literal**. As consultas não são digitadas de memória: elas vivem em
`tools/demo_evidence` e são invocadas assim.

**Imprimir o SQL, sem tocar em banco nenhum** (serve para conferir o que vai
rodar, e para colar num `psql` à mão):

```sh
uv run python -m tools.demo_evidence plan \
  --org <ORG_ID> --run <RUN_ID> --incident <INCIDENT_ID>
```

**Executar e gravar a saída literal**, um arquivo por estação:

```sh
uv run python -m tools.demo_evidence collect \
  --org <ORG_ID> --run <RUN_ID> --incident <INCIDENT_ID> \
  --out specs_v7/080-incidente-fecha-o-laco/evidence/consultas \
  --exec "ssh root@192.168.68.159 kubectl exec -i -n k3s-stg-ninjasre deploy/app -- sh -c 'psql -X -q -v ON_ERROR_STOP=1 \"\$NINJASRE_DATABASE_URL\"'"
```

O que `--exec` recebe é uma linha de comando que **lê o SQL da entrada padrão**.
Ela é dividida em argumentos por `shlex`, nunca entregue a um shell desta
máquina: o único shell envolvido é o `sh -c` de dentro do pod, que é quem
resolve a variável de ambiente com a string de conexão. Nenhuma senha aparece
nesta linha, e nenhuma aparece no arquivo de saída.

O coletor **recusa** qualquer coisa que não seja um `SELECT` e recusa
identificador com caractere fora de `A-Z a-z 0-9 _ - . : @ + /`. Isso é
proposital: ele existe para não virar um caminho de escrita ao banco de
staging.

Sem `--approval` e sem `--resource`, as estações E7 a E10 saem como **não
coletadas**, com a razão escrita no próprio arquivo. Para este roteiro isso é o
esperado até você ter o identificador da proposta (estação E7).

---

## 2. Pré-condições — conferir antes, não durante

| # | O que conferir | Comando / onde | Desfecho se falhar |
|---|---|---|---|
| P1 | O deployment responde | `curl -sf -o /dev/null -w '%{http_code}\n' https://stg-ninjasre.lan.kyo.ninja/` | **ambiente** — reexecutar depois |
| P2 | O Argo reconciliou a versão que se quer medir | `ssh root@192.168.68.159 'kubectl get application stg-ninjasre -n argocd'` → `Synced` **e** `Healthy` | **ambiente** |
| P3 | Os pods estão de pé | `ssh root@192.168.68.159 'kubectl get pods -n k3s-stg-ninjasre'` | **ambiente** |
| P4 | O identificador da organização | `SELECT org_id, name FROM organisations;` | sem isto nenhuma consulta roda |
| P5 | Existe pelo menos um alerta disparando | a lista de alertas ativos do Alertmanager da stack de monitoração | **ambiente** — sem matéria-prima, reexecutar noutra hora |

`Synced + Healthy` diz que o cluster reflete o Git. **Não** diz que alguém
atende. P1 e P2 se conferem separadamente e nenhum substitui o outro.

---

## 3. A tabela de estações

| Estação | O que se espera ver | Onde se olha | Evidência exigida |
|---|---|---|---|
| **E1** — o alerta existe | Um alerta real ativo, com nome de regra, severidade e instante de início | Alertmanager da stack | saída literal da listagem de alertas ativos |
| **E2** — a entrega chegou autenticada | Uma entrega registrada, com origem, instante e resultado; e a mesma rota **recusando** quem chega sem credencial | `/settings/alert-intake`; sonda de recusa por `curl` | screenshot da tela + código de resposta da sonda |
| **E3** — o incidente abriu legível | Título que é uma frase, sujeito resolvido, zero painéis "não foi possível preencher", nenhum `%3A`/`%40`/`%2B` na URL | `/incidents` e `/incidents/{endereço}` | screenshot full-page das duas + consulta `E3-incidente` |
| **E4** — a investigação gravou | Transcript com N chamadas e o que cada uma devolveu; custo por turno; "o que esta investigação tocou" preenchido; nenhum controle de run vivo num run terminado | `/runs/{runId}`, **depois de um reload** | screenshot full-page + consultas `E4-*` |
| **E5** — o relato é legível | Título é uma sentença; o relato é documento renderizado; nenhum `#`, `**` ou `|` aparecendo como texto | `/runs/{runId}` | screenshot full-page + consulta `E5-sentenca` |
| **E6** — as ferramentas condizem | Nenhuma capacidade de vendor que este deployment não conectou; nenhuma capacidade de remediação oferecida só para devolver recusa | transcript do run + `/agent` | screenshot + a lista de exclusões do log do processo |
| **E7** — a proposta aguarda | Uma proposta com plano de reversão, alcance, postura declarada, e o chip **aguardando decisão** | `/decisions` e o painel de ação no incidente | screenshot full-page das duas + consultas `E7-*` |

O laço de leitura **para em E7**. E8, E9 e E10 são do outro roteiro.

---

## 4. Classificação de desfechos, escrita antes da execução

A regra que separa os dois: **se a mesma execução, repetida amanhã sem mudar
uma linha de código, tem chance razoável de passar, é ambiente. Se ela vai
falhar igual até alguém mudar código, é produto.**

| Estação | Desfecho de **ambiente** (reexecuta) | Desfecho de **produto** (bloqueia) e a feature dona |
|---|---|---|
| E1 | Nenhum alerta disparando agora; a stack de monitoração fora do ar | — (E1 não exercita código deste produto) |
| E2 | O alerta dispara e a entrega não chega **porque a origem não resolve o nome do deployment** ⇒ é a tarefa operacional de resolução de nomes, não o webhook | A entrega chega e é aceita **sem** credencial; ou é recusada **com** a credencial correta ⇒ *dona: a borda de webhooks* |
| E3 | O incidente ainda não abriu (janela de agrupamento do Alertmanager) | Título é um identificador; painel "não foi possível preencher"; URL com `%3A`/`%40`/`%2B`; sujeito não resolve tendo recurso no estate ⇒ *dona: identidade endereçável (020) para o endereço e o título; uma fonte por fato (030) para a causa de vazio* |
| E4 | A investigação ainda está rodando | Contagem na tela diferente da contagem no banco; transcript vazio com `tool_calls > 0` no banco; custo em branco havendo turno ⇒ *dona: registro do que o agente fez (001) para a gravação; leitura do relato (010) para a leitura* |
| E5 | — | Sintaxe markdown aparecendo como texto; título que é o documento inteiro ⇒ *dona: leitura do relato (010)* |
| E6 | — | Ferramenta de vendor não conectado oferecida ao turno; capacidade de remediação oferecida sem o balcão composto ⇒ *dona: decisão composta (040)* |
| E7 | A investigação concluiu **sem evidência suficiente para propor** — nenhuma proposta aparece, **e isso é correto**: registre o run como cenário de leitura e siga | Proposta existe no banco e `/decisions` diz "vazio porque o setup não terminou"; proposta sem plano de reversão; proposta já decidida sem ninguém ter decidido ⇒ *dona: decisão composta (040) para a proposta; uma fonte por fato (030) para a causa de vazio* |

Há um terceiro desfecho, e ele é o mais provável nesta fase da onda:
**`/decisions` vazio porque o balcão de remediação não compôs.** Isso não é
falha de tela e não é falha de ambiente — é uma condição declarada do
deployment, e o produto a diz de si mesmo. Confira antes de classificar:

```sh
ssh root@192.168.68.159 "kubectl logs -n k3s-stg-ninjasre deploy/app --since=24h | grep -E 'remediation\.(control_plane_bound|control_plane_skipped|desk_composed|desk_skipped)'"
```

Uma destas linhas **sempre** aparece depois do boot:

- `remediation.control_plane_bound` seguido de `remediation.desk_composed`
  (com `capabilities` e `profile`) — o deployment sabe agir, e E7 deve produzir
  proposta;
- `remediation.desk_skipped` com a lista `missing` — o deployment **não** sabe
  agir, e a razão está na própria linha. E7 fica **não exercida**, com a lista
  `missing` anexada como evidência. Não é aprovação por omissão e não é
  reprovação do produto.

---

## 5. A execução, passo a passo

### Passo 1 — E1: escolher o alerta

Liste os alertas ativos no Alertmanager da stack de monitoração e escolha um.
Registre **qual** e **por quê** (o critério: um alerta cujo sujeito o estate
deste deployment conhece dá uma travessia mais rica em E3; um que ninguém
conhece ainda serve, e E3 mostra "alerta para coisa que não está aqui", que é
uma resposta correta).

Anote: nome da regra, severidade, instante de início.

### Passo 2 — E2: a entrega, e a recusa

**A sonda que vale é a de recusa**, porque ela não cria dado:

```sh
curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST https://stg-ninjasre.lan.kyo.ninja/webhooks/alertmanager \
  -H 'content-type: application/json' -d '{}'
```

Registre o código. Um código de recusa é o resultado esperado; um `2xx` aqui é
**defeito de produto**, e é o único caminho deste roteiro que escreve.

Depois abra `/settings/alert-intake` e fotografe a entrega que corresponde ao
alerta do Passo 1: origem, instante, resultado.

### Passo 3 — E3: o incidente

Abra `/incidents`, ache o incidente do alerta escolhido, e abra o detalhe.
Confira, olhando:

- o título é uma frase, não um identificador;
- a barra de endereço **não** contém `%3A`, `%40` nem `%2B`;
- nenhum painel diz "não foi possível preencher";
- o sujeito do incidente aponta um recurso que `/resources` lista — ou diz,
  explicitamente, que o sujeito não está no estate.

Anote o endereço curto do incidente (o que está na URL) — é o parâmetro
`--incident` do coletor. Screenshot full-page de `/incidents` e do detalhe.

### Passo 4 — E4: a investigação, lida do store

Do detalhe do incidente, abra o run. **Dê um reload** — o ponto desta estação é
ler do store, não do processo que rodou.

Confira: quantidade de chamadas no transcript, o que cada uma devolveu, a
tabela de custo por turno, o painel do que a investigação tocou, e a **ausência**
de controle de run vivo num run terminado.

Anote o identificador do run — é o parâmetro `--run` do coletor.

Rode o coletor (comando na seção 1) com `--org`, `--run` e `--incident`.
A contagem que a tela mostra tem de bater com a contagem que o banco devolve.

### Passo 5 — E5: o relato

Na mesma tela: o título é uma sentença; o relato é um documento desenhado como
documento. Nenhum `###`, `**`, `|` ou `-` de lista aparecendo como texto.

A consulta `E5-sentenca` mostra os dois campos lado a lado: a sentença e os
primeiros 120 caracteres do documento. A prova é a sentença **não** começar com
sintaxe markdown.

### Passo 6 — E6: as ferramentas

Duas leituras, e nenhuma delas é uma tela nova:

1. No transcript, as ferramentas que a investigação de fato chamou.
2. No log do processo, o que foi **excluído** da seleção e por quê:

```sh
ssh root@192.168.68.159 "kubectl logs -n k3s-stg-ninjasre deploy/app --since=24h | grep -E 'tool_selection|integrations_unresolved|zero_integration'"
```

O que se afirma aqui: nenhuma capacidade de vendor que este deployment não
conectou foi oferecida ao modelo, e nenhuma capacidade de remediação foi
oferecida só para devolver recusa.

### Passo 7 — E7: a proposta

Abra `/decisions` e o painel de ação proposta dentro do incidente. Confira:
a proposta, o plano de reversão, o alcance (um recurso), a postura declarada, e
o chip dizendo que aguarda decisão.

**Nada é aprovado aqui.** Se houver um botão de aprovar, não o aperte: aprovar
por este roteiro invalida a demo do laço inteiro, que precisa da aprovação
acontecendo uma vez, com o operador olhando.

Anote o identificador da aprovação e o do recurso, e rode o coletor de novo com
`--approval` e `--resource` para fechar as consultas de E7.

Se `/decisions` estiver vazio, siga a seção 4 antes de classificar.

### Passo 8 — a repetibilidade

Execute os passos 3 a 7 **uma segunda vez**, sobre o mesmo incidente, e compare
a evidência. O esperado é a mesma evidência nas duas.

Onde variar, escreva **o quê** e **por quê** na própria saída — por exemplo:
uma investigação que ainda estava rodando na primeira passagem e concluiu na
segunda faz o transcript crescer; isso é variação legítima e nomeada, e não é
falha de repetibilidade.

---

## 6. Reversão

Este roteiro não faz mudança nenhuma. Não há o que reverter.

A única exceção é a sonda de recusa do Passo 2, que faz uma requisição sem
credencial: se ela for **aceita**, um incidente espúrio pode ter sido aberto —
feche-o pela interface e registre o achado como defeito de produto.

---

## 7. O que este roteiro entrega

- Uma linha por estação em `evidence/EVIDENCIA.md`, com expectativa, evidência,
  consulta, saída literal, veredito e instante.
- Screenshots full-page em 1920×1080 em `evidence/telas/`, nomeadas pela
  estação.
- Um arquivo por estação em `evidence/consultas/`, com a consulta e a saída
  literal — nunca uma afirmação sobre a saída.
