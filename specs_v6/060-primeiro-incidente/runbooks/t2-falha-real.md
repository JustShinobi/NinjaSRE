# T2 — a falha real, controlada

Derruba de propósito um contêiner escolhido, numa janela combinada, e observa o
produto correlacionar métrica com estado, diagnosticar a causa e **propor** a
religada — sem executar nada.

É o roteiro que prova a coisa que o T1 não prova: que o diagnóstico vem de
evidência colhida, e não de um alerta sintético cujo texto já dizia a resposta.

---

## O que este roteiro não é

**O passo destrutivo é digitado por uma pessoa.** Não vira script, não vira
automação, não vira `for`. Um roteiro que derruba contêiner sozinho é a
contradição exata da postura que a feature existe para demonstrar.

**Uma vítima por vez, uma janela por vez.** Nenhum segundo contêiner é derrubado
para "testar de novo" sem nova combinação.

---

## A vítima

Escolha entre os dois aprovados. Ambos são serviços cuja ausência temporária é
tolerável, e ambos ficam de pé por conta própria depois de religados.

| Vítima | Onde | Observação |
|---|---|---|
| **`redis`** | **CT122, pve01, 10.20.20.52** | **a vítima deste roteiro.** Autorizada pelo operador, declarada fora de uso, e — ao contrário das outras — genuinamente observada |
| `dockge` | CT123, pve01 | autorizada, mas **não serve**: não é alvo de scrape nem de sonda, então parar não dispara nada |
| `streamlink-webui` | CT139, pve01 | do plano; não observada, e já estava parada em 2026-08-20 |
| `bazarr` | CT103, pve01 | do plano; não observada |

`dockge` é a única das três autorizada explicitamente para derrubada de teste.
As outras duas vêm do plano e exigem combinação antes.

### Por que a vítima é a `redis`, e não a `dockge`

A vítima precisa ser duas coisas ao mesmo tempo: **descartável** e
**observada**. Só a `redis` é as duas.

Conferido em 2026-08-20 contra a configuração real do Prometheus: **não existe
regra que dispare quando um LXC qualquer para.** Existe `InstanceDown`
(`up{job!="pve-exporter"} == 0`), que vale para alvos de scrape, e
`BlackboxProbeFailed`, restrita a uma lista fixa de sondas. `dockge`,
`streamlink-webui` e `bazarr` não estão em nenhuma das duas — parar qualquer
uma delas não dispara nada, e o roteiro morreria na primeira etapa sem que isso
fosse defeito do produto.

A `redis` é o alvo de scrape `10.20.20.52:9121` do job `redis-exporter`,
rotulado `service: redis`, `node: pve01`, `criticality: high`.

### O que exatamente dispara, e em quanto tempo

Parar a CT122 derruba o exporter junto, porque ele vive no mesmo contêiner. Duas
regras casam, ambas com `for: 2m` e `severity: critical`:

| Regra | Expressão | Dispara? |
|---|---|---|
| `InstanceDown` | `up{job!="pve-exporter"} == 0` | **sim** |
| `RedisExporterDown` | `up{job="redis-exporter"} == 0` | **sim** |
| `RedisInstanceDown` | `redis_up == 0` | **provavelmente não** — ver abaixo |

`RedisInstanceDown` compara `redis_up` com zero. Com o contêiner parado a
métrica não fica zero: ela some. Uma série ausente não satisfaz `== 0`, então
essa regra tende a **não** disparar. Não é defeito e não é motivo para esperar
mais — é a diferença entre "respondeu que está mal" e "não respondeu".

**Conte com ~2 minutos até o alerta, mais os 10s de `group_wait` da rota
crítica.** Antes disso, silêncio é o esperado, não sintoma.

O `severity: critical` é o que importa para este roteiro: é o rótulo que a rota
do Alertmanager casa para chegar aos receivers críticos, e portanto ao NinjaSRE.

**O contêiner do NinjaSRE não serve como vítima**, ainda que derrubá-lo esteja
autorizado para outros fins. Se o NinjaSRE está fora, não há quem investigue: o
roteiro mediria a própria ausência do observador. Ele é alvo legítimo para
publicar release e reiniciar serviço, e não para este roteiro.

### Confira o estado inicial — e não pule esta parte

```sh
ssh pve01 'pct status <VMID>'
```

Precisa dizer **running** antes de começar.

Uma vítima que já estava parada não pode ser parada pelo passo destrutivo, e um
alerta que já estava disparando não foi disparado por este teste. Se você seguir
com a vítima já parada, vai colher um incidente verdadeiro e concluir dele uma
coisa falsa — que o roteiro funcionou.

---

## Pré-condições

1. **T1 verde**, com a reexecução conferida — um incidente, não três.
2. **O-C verificada**: o runtime existe e uma investigação inicia de verdade.
3. **Janela combinada** com o operador, que está ciente e acordado.
4. **Vítima escolhida** entre as duas, e confirmada `running`.

---

## O passo destrutivo

Digitado à mão, uma vez:

```sh
ssh pve01 'pct stop <VMID>'
```

Anote a hora. Ela é a referência de tudo que vem depois.

**Não emita alerta nenhum.** O alerta tem que disparar por conta própria — é
justamente isso que separa o T2 do T1. Se você emitir, o roteiro perde o
sentido.

---

## A evidência esperada

Confira na ordem. O tempo entre uma etapa e a próxima é real: o `group_wait` da
rota crítica é de 10s, e o detector leva o tempo dele.

### 1. O alerta disparou sozinho

O Alertmanager mostra o alerta ativo, sem que ninguém o tenha emitido.

### 2. A entrega chegou

A tela de Alert intake mostra a entrega nova, com origem, horário e resultado.

### 3. A investigação correlacionou

Na timeline do incidente, as evidências mostram a consulta executada **e** o
resultado — a métrica de sonda falhando, e o estado do contêiner no Proxmox
dizendo parado. As duas coisas, não uma frase sobre elas.

Esta é a etapa que o T1 não consegue exercer. Aqui o diagnóstico tem que ser
construído a partir do que foi colhido.

### 4. O diagnóstico nomeia a causa

Uma frase, dizendo que o contêiner está parado — e apoiada nas evidências acima
dela, não em cima do texto do alerta.

### 5. A ação proposta espera

O cartão mostra a ação de religar, o blast radius, a postura, e o chip
aguardando decisão. **Nada foi executado.**

**Não aprove ainda.** Confira primeiro que a evidência está toda registrada. A
aprovação é o último passo, e aprová-la antes de olhar é desperdiçar a única
execução do roteiro que responde "o registro ficou completo?".

---

## Reversão

Manual, imediata e independente do produto:

```sh
ssh pve01 'pct start <VMID>'
```

Vale a qualquer momento e não depende de nada. Se a ação proposta for aprovada, o
efeito é a mesma religada. Se for rejeitada, ou se a investigação travar, ou se
qualquer coisa parecer errada, religue à mão sem esperar por nada.

**Não espere o produto para religar.** O roteiro está validando o produto; o
serviço não é refém dessa validação.

Depois: confirme `pct status <VMID>` dizendo **running**, e confirme que o alerta
resolveu — e que a notificação de resolução fechou o incidente que a abertura
criou.

---

## As duas decisões

Com o incidente do T2 na tela, exercite os dois caminhos — um em cada incidente,
não os dois no mesmo:

- **Aprovar** num caso: registra decisão, decisor e instante **antes** de
  qualquer efeito, e a ação acima de leitura tem plano de reversão registrado
  antes de executar.
- **Rejeitar** noutro: exige motivo. Uma rejeição sem motivo é recusada.

Depois confira que **as duas** aparecem no audit log com autor, ação, assunto e
resultado.
