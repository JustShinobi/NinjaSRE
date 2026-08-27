# T1 — o alerta sintético, de ponta a ponta

Emite um alerta de teste no Alertmanager da stack e confere que ele atravessa o
produto inteiro: entrega recebida, incidente aberto, investigação com os cinco
passos, relatório entregue e ação proposta aguardando decisão.

**Nada real é derrubado.** A reversão deste roteiro é "nenhuma", e isso é uma
propriedade dele, não um descuido: o alerta é sintético, o alvo é um serviço que
continua de pé, e o único efeito colateral é uma linha a mais no histórico.

---

## Pré-condições

Cada uma verificada antes de começar. Uma falha aqui interrompe o roteiro; não
se compensa uma pré-condição ausente seguindo mesmo assim.

| # | Pré-condição | Como conferir | Aprovado quando |
|---|---|---|---|
| 1 | A rota de rede existe | de dentro do CT136: `curl -s -o /dev/null -w '%{http_code}' -X POST -H 'content-type: application/json' -d '{}' http://<gateway>:8420/webhooks/alertmanager` | responde **401** |
| 2 | O receiver está aplicado | `pct exec 136 -- grep -c 'ninjasre' /etc/alertmanager/alertmanager.yml` | ≥ 1, e a recarga já aconteceu |
| 3 | O runtime existe | no produto: o passo de runtime do setup consta como concluído | concluído, não "processo no ar" |
| 4 | O provider está verificado | no produto: a tela de provider mostra verificado | verificado, não apenas configurado |

A pré-condição 1 é a fase O-A e já foi aprovada. A 2 é a O-B. A 3 é a O-C. A 4
vem da feature do provider.

**O endereço do gateway não é estável.** Já mudou de `.74` para `.73` durante
esta onda. Confirme antes de usar, em vez de copiar de um comando antigo.

---

## O token

O delivery token é emitido na tela de Alert intake e mostrado **uma única vez**.
Ele não é transcrito neste arquivo e não deve ser transcrito em nenhum outro.

- Onde ele foi guardado: junto dos demais segredos da stack de monitoring, no
  mesmo lugar em que o receiver o lê.
- Se ele se perdeu: emita outro pela tela e revogue o anterior. Uma leitura
  posterior nunca devolve o valor, por construção — não procure.

---

## O comando

O Alertmanager aceita alertas pela sua própria API. O alerta abaixo é sintético:
o nome de regra é de teste, e os rótulos apontam um serviço que está de pé.

```sh
# de um host que alcança o Alertmanager
curl -sS -X POST http://<alertmanager>:9093/api/v2/alerts \
  -H 'content-type: application/json' \
  -d '[{
    "labels": {
      "alertname": "NinjaSRESynthetic",
      "severity":  "critical",
      "service":   "<serviço real, de pé>",
      "instance":  "<instância do mesmo serviço>",
      "zone":      "<zona do serviço>"
    },
    "annotations": {
      "summary":     "alerta sintético de validação ponta a ponta",
      "description": "emitido à mão pelo roteiro T1; nada foi derrubado"
    },
    "startsAt": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"
  }]'
```

`severity: critical` não é decoração: é o rótulo que a rota do Alertmanager casa
para chegar aos receivers críticos. Um alerta com outra severidade é agrupado
noutro lugar e não chega.

O agrupamento é por `severity`, `alertname` e `service`, com `group_wait` de 10s
na rota crítica. Espere esses segundos antes de concluir que não chegou.

---

## A evidência esperada, etapa por etapa

Confira **na ordem**. A primeira que falhar é onde o problema está, e as
seguintes não têm significado até ela passar.

### 1. A entrega chegou

Na tela de **Alert intake**, a fonte Alertmanager mostra o instante da última
entrega recebida, com origem e resultado.

*Falha comum*: a tela mostra a fonte configurada mas sem entrega nenhuma. Isso é
uma rota bloqueada ou um token errado — não é "ainda não processou".

### 2. O incidente abriu

Em `/incidents` existe um incidente novo cujo assunto é o serviço dos rótulos.

*Falha comum*: dois incidentes para o mesmo alerta. Isso é falha de correlação e
é defeito, não ruído.

### 3. A timeline tem os cinco passos

Em `/incidents/<id>`, o cartão de investigação mostra recebimento, hipóteses,
evidências, diagnóstico e entrega — cada um com hora, e o cabeçalho com contagem
de passos, duração e custo.

*Falha comum*: o cartão aparece vazio ou diz que não há investigação. Isso é
ausência de runtime, e significa que a pré-condição 3 não estava de fato
satisfeita — "o processo subiu" não é a mesma coisa.

### 4. O relatório saiu

O passo de entrega nomeia os destinos para onde o relatório foi.

### 5. A ação proposta espera

O cartão de ação proposta mostra o chip de estado aguardando decisão, a ação em
uma frase, o blast radius e a postura — e **nada foi executado**.

---

## A reexecução — a parte que mais gente pula

Emita **a mesma notificação pelo menos três vezes** e confirme que existe
**exatamente um** incidente.

```sh
for i in 1 2 3; do <o mesmo comando acima>; sleep 2; done
```

Conte os incidentes daquele serviço antes e depois. A alegação não é "a resposta
disse duplicado" — é que a **contagem não mudou**. Um teste que confere a
resposta em vez do estado não prova nada sobre o segundo incidente que não deve
existir.

---

## Reversão

**Nenhuma.** Nada real foi derrubado.

O que fica para trás é um incidente sintético no histórico. Se ele incomodar,
feche-o pela tela como qualquer outro — mas ele é evidência de que o caminho
funciona, e há bons motivos para deixá-lo.

Se o receiver precisar sair, isso é a reversão da fase O-B e não deste roteiro:
restaurar a cópia do arquivo de configuração e recarregar.
