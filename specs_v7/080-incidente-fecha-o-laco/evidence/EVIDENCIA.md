# Evidência consolidada — o incidente fecha o laço

> **Este arquivo é o gabarito, e ele aterrissou antes da demo.** Todo campo
> abaixo está em branco de propósito. Um roteiro escrito depois da execução é um
> relatório disfarçado; uma tabela de evidência preenchida depois do fato é uma
> lembrança. O que decide se a onda fechou é o que entra nestes campos, e o
> formato deles foi fixado antes de alguém saber o que ia acontecer.
>
> Preencher é do orquestrador, que alcança o cluster e o banco. Quem escreveu o
> gabarito não alcança nenhum dos dois, e por isso não escreveu um único número
> aqui.

**Veredito da demo, em uma frase:** _(a preencher — §7)_

---

## 1. A versão que a demo mediu

| Fato | Valor |
|---|---|
| Commit da árvore da onda | _(a preencher)_ |
| Features mergeadas com veredito PASS | _(a preencher, uma linha por feature)_ |
| `make verify` antes de publicar | _(exit code / testes / duração)_ |
| Digests publicados por `make deploy-stg` | _(a preencher)_ |
| Estado do Argo no instante da demo | _(saída de `kubectl get application stg-ninjasre -n argocd`, com o instante)_ |
| Pods de pé | _(saída de `kubectl get pods -n k3s-stg-ninjasre`)_ |
| `/health/ready` do `app` | _(saída literal)_ |
| A URL pública respondendo | _(código HTTP e instante)_ |

Uma evidência que não aponta uma versão prova algo sobre um sistema que não se
sabe qual era. As duas linhas do Argo e do serviço são conferidas
**separadamente**: reconciliar Git não é responder HTTP.

---

## 2. Aptidão do ambiente — conferido, nunca alterado

| # | Item | Conferido? | Saída / onde |
|---|---|---|---|
| A1 | Identificador da organização | | |
| A2 | Provedor de modelo **Verified**, chave vinda do cofre | | |
| A3 | Proxmox conectado, confiança de certificado declarada | | |
| A4 | `/resources` lista recursos reais; contagem de `estate_resources` | | |
| A5 | Token do Proxmox com gerência de energia (`VM.PowerMgmt` em `/vms`) — **não alterado** | | |
| A6 | Vítima confirmada pelo operador | | |
| A7 | Vítima `running` | | |
| A8 | Regra de alerta que cobre a vítima, ativa; expressão e `for` | | |
| A9 | Rota do Alertmanager casa a severidade emitida | | |
| A10 | Webhook recusa entrega sem credencial | | |
| A11 | Alertas já disparando agora (matéria-prima do laço de leitura) | | |
| A12 | Balcão de remediação: `desk_composed` ou `desk_skipped` + `missing` | | |

Um item não conferido **não bloqueia por si**: ele bloqueia a estação que
depende dele, e isso fica escrito na linha da estação.

---

## 3. O que o staging media antes da demo — o vermelho registrado

O gabarito só prova alguma coisa se as consultas devolverem os valores de
partida **antes** da demo. Uma consulta que já devolvesse verde antes não
estaria medindo o laço.

| Consulta | Valor de partida esperado (medido em 2026-08-23) | Valor medido a seco | Confere? |
|---|---|---|---|
| `run_turns` para um run pré-onda | `0` | | |
| `tool_calls` para um run pré-onda | `0` | | |
| `evidence` para um run pré-onda | `0` | | |
| `trace_events` (total da instância) | `73`, para 37 runs concluídos | | |
| `agent_runs.summary` recente | começa com `###` | | |
| `approvals` de remediação | nenhuma linha, para nenhum run | | |
| `rollback_plans` | nenhuma linha | | |
| `remediation_outcomes` | nenhuma linha | | |
| `estate_resources` | estate vazio | | |

Saída literal em `evidence/consultas/000-partida.txt`.

**Sem esta seção preenchida, a evidência posterior não tem contraste e o
gabarito não foi provado.**

---

## 4. As estações

O laço de leitura exercita E1 a E7. O laço inteiro continua em E8, E9 e E10.

Cada estação carrega: **o que se esperava ver**, **a evidência que se viu**, a
**consulta com a saída literal**, o **veredito** e o **instante**.

Vereditos possíveis: `PASSOU` · `REPROVOU (produto)` · `REPROVOU (ambiente)` ·
`NÃO EXERCIDA` — este último com a razão nomeada, nunca "aprovada por omissão".

### E1 — o alerta dispara sozinho

- **Expectativa:** dentro do `for` da regra mais o `group_wait` da rota, o
  alerta fica ativo sem ninguém o ter emitido.
- **Evidência (tela):** —
- **Consulta / comando e saída literal:** _(a preencher)_
- **Veredito:** _(a preencher)_
- **Instante:** _(a preencher)_

### E2 — a entrega chega autenticada

- **Expectativa:** a entrega registrada com origem, horário e resultado; a mesma
  rota recusa quem chega sem credencial.
- **Evidência (tela):** `telas/E2-alert-intake.png`
- **Consulta / comando e saída literal:** _(a preencher)_
- **Veredito:** _(a preencher)_
- **Instante:** _(a preencher)_

### E3 — o incidente abre com título legível e sujeito resolvido

- **Expectativa:** título que é uma frase; sujeito que o estate resolve; zero
  painéis "não foi possível preencher"; nenhum `%3A`, `%40` ou `%2B` na URL.
- **Evidência (tela):** `telas/E3-incidents.png`, `telas/E3-incident-detail.png`
- **Consulta / saída literal:** `consultas/E3-*`
- **Veredito:** _(a preencher)_
- **Instante:** _(a preencher)_

### E4 — a investigação grava turnos, chamadas, evidência e custo

- **Expectativa:** N chamadas na tela ⇔ N chamadas no banco; o que cada uma
  devolveu; custo por turno; lido **depois de um reload**.
- **Evidência (tela):** `telas/E4-run-detail.png`
- **Consulta / saída literal:** `consultas/E4-*`
- **Valor de partida ao lado:** `run_turns=0`, `tool_calls=0`, `evidence=0`
- **Veredito:** _(a preencher)_
- **Instante:** _(a preencher)_

### E5 — o relato é legível: sentença e documento renderizado

- **Expectativa:** o título é uma sentença; o relato é documento desenhado como
  documento; nenhum caractere de sintaxe markdown aparece como texto.
- **Evidência (tela):** `telas/E5-report.png`
- **Consulta / saída literal:** `consultas/E5-sentenca.txt`
- **Valor de partida ao lado:** todo `summary` recente começava com `###`
- **Veredito:** _(a preencher)_
- **Instante:** _(a preencher)_

### E6 — as ferramentas condizem com as integrações configuradas

- **Expectativa:** nenhuma capacidade de vendor que este deployment não
  conectou; nenhuma capacidade de remediação oferecida só para devolver recusa.
- **Evidência (tela):** `telas/E6-agent-tools.png`
- **Consulta / comando e saída literal:** _(as exclusões registradas no log)_
- **Veredito:** _(a preencher)_
- **Instante:** _(a preencher)_

### E7 — a proposta com plano de reversão aguarda decisão

- **Expectativa:** exatamente uma proposta para o run da demo, com plano de
  reversão, alcance de um recurso, postura declarada, e o chip aguardando
  decisão. **Nada executa sem o operador.**
- **Evidência (tela):** `telas/E7-decisions.png`, `telas/E7-incident-action.png`
- **Consulta / saída literal:** `consultas/E7-*`
- **Valor de partida ao lado:** zero propostas; `/decisions` eternamente vazio
- **Veredito:** _(a preencher)_
- **Instante:** _(a preencher)_

### E8 — o humano aprova, e a decisão é registrada antes de qualquer efeito

- **Expectativa:** estado, decisor, instante e motivo em `approvals`; o evento
  correspondente na auditoria; o plano de reversão **já registrado antes**.
- **Evidência (tela):** `telas/E8-approval.png`
- **Consulta / saída literal:** `consultas/E8-*`
- **Veredito:** _(a preencher)_
- **Instante:** _(a preencher)_

### E9 — a execução acontece pelo gate

- **Expectativa:** o convidado volta a rodar; o desfecho gravado em
  `remediation_outcomes`; o episódio em `episodes`; a entrada de ação na
  timeline. Uma **falha nomeada** também fecha o laço; o que não fecha é falha
  silenciosa.
- **Evidência (comando):** `pct status <VMID>`
- **Consulta / saída literal:** `consultas/E9-*`
- **Veredito:** _(a preencher)_
- **Instante:** _(a preencher)_

### E10 — o incidente reflete o desfecho

- **Expectativa:** o incidente mostra o que aconteceu, em vez de continuar
  parado no diagnóstico.
- **Evidência (tela):** `telas/E10-incident-after.png`
- **Consulta / saída literal:** `consultas/E10-*`
- **Veredito:** _(a preencher)_
- **Instante:** _(a preencher)_

### R — a rejeição, em ocorrência diferente

- **Expectativa:** rejeitar sem motivo é **recusado**; rejeitar com motivo é
  **registrado**; as duas decisões aparecem na auditoria com autor, ação,
  assunto e resultado.
- **Evidência (tela):** `telas/R1-rejection-refused.png`,
  `telas/R2-rejection-recorded.png`
- **Consulta / saída literal:** `consultas/R-*`
- **Veredito:** _(a preencher)_
- **Instante:** _(a preencher)_

---

## 5. As tarefas operacionais — verificadas, não executadas

Nenhuma linha desta seção altera infraestrutura. Cada uma registra o estado
real, feito ou não. Uma não concluída **não reprova a demo por si**; ela marca
como **não exercida** a estação que dependia dela, e entra no backlog novo.

| Tarefa | Evidência exigida | Estado real | Saída |
|---|---|---|---|
| Resolução de nomes nos contêineres de monitoração | um nome do domínio do deployment resolvendo **de dentro de cada** contêiner | | |
| Sincronização do segredo gerenciado | um recurso de segredo gerenciado efetivamente sincronizando, **ou** a decisão registrada de conviver com o segredo escrito à mão | | |
| Chave do gateway de modelos | o provedor correspondente aparecendo **Verified** no console | | |

**Estações marcadas não exercidas por causa de uma destas:** _(a preencher)_

---

## 6. Achados

| # | Descrição | Estação | Classificação | Dona / "sem dono" | Destino |
|---|---|---|---|---|---|
| | | | | | |

- **Achado de produto com dona:** entregue ao orquestrador com a estação e a
  evidência. **Não é consertado aqui.** A decisão de gastar um ciclo de reparo é
  dele.
- **Achado sem dona na onda:** vira entrada do backlog novo, na forma que o
  arquivo já pratica.
- **Depois de um reparo aceito:** a estação afetada é **reexecutada e a
  evidência substituída** — nunca acumulada como se as duas capturas fossem
  verdadeiras ao mesmo tempo.

---

## 7. Veredito

**Em uma frase:** _(a preencher)_

| Estação | Veredito |
|---|---|
| E1 | |
| E2 | |
| E3 | |
| E4 | |
| E5 | |
| E6 | |
| E7 | |
| E8 | |
| E9 | |
| E10 | |
| R | |

**Estações não exercidas, com a razão:** _(a preencher)_

---

## 8. A varredura de segredo — sem ela a evidência não é entregue

| Verificação | Resultado |
|---|---|
| Nenhum token, chave, senha ou credencial no texto deste arquivo | |
| Nenhum token, chave, senha ou credencial nos arquivos de `consultas/` | |
| Nenhum token, chave, senha ou credencial **dentro das screenshots** | |

Uma screenshot com um valor de token é um vazamento tão real quanto um commit
com ele. E conferir vazamento com um `grep` que recebe o segredo como argumento
sempre dá falso positivo, porque o próprio `grep` nasce com ele em `argv` — use
um arquivo de padrões, ou a saída de um comando, nunca o valor na linha.
