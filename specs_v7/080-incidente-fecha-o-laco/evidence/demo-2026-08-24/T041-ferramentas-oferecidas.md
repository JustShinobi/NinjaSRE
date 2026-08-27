# T041 (E6) — o conjunto de ferramentas oferecido

**Esta tarefa derrubou o achado principal que eu tinha escrito sobre esta onda.**
Eu havia concluído que o laço não fecha porque o catálogo não tem capacidade que
atue sobre infraestrutura. Está errado, e o erro tem origem rastreável: derivei a
conclusão de um `grep` por `SideEffectLevel.WRITE_*` dentro de `integrations/`,
que achou três arquivos, e generalizei de três arquivos para o catálogo inteiro.

## O catálogo, medido em vez de grepado

`GET /v1/capabilities`, contra o deployment que serve:

    ferramentas declaradas          80
    não-leitura                     24
      write_reversible              15
      write_irreversible             6
      destructive                    3
    por domínio
      remediation                   20
      communication                  2
      incident / methodology          2

Treze das vinte de remediação são do Proxmox. `proxmox_start_guest` existe, é
`write_reversible`, domínio `remediation`. O balcão compôs **20** capacidades —
o mesmo número — e o plano de controle ligou **13** para o Proxmox. A maquinaria
não está vazia; está cheia.

## O que foi oferecido ao run da demo

O store grava o conjunto por turno, em `run_turns.payload->'offered_capabilities'`.
Para o run `d393d5d0…`, o da CT122 parada, foram **40** — exatamente o teto de
`MAX_AGENT_TOOL_SCHEMAS`. Treze delas são ações de remediação:

    clear_cache            cordon_drain_node      proxmox_ha_relocate
    proxmox_migrate_guest  proxmox_reboot_guest   proxmox_resume_guest
    proxmox_shutdown_guest proxmox_stop_guest     proxmox_suspend_guest
    restart_workload       rollback_deployment    run_on_node
    toggle_feature_flag

**Nenhuma capacidade foi oferecida só para devolver recusa**, que é a metade da
alegação desta tarefa: `_can_carry` filtra antes do ranqueamento qualquer ação
que o balcão não trate, então uma ação oferecida é uma ação que este deployment
consegue levar até o efeito.

## O achado, e ele é preciso

O alerta dizia, textualmente, que um convidado **estava rodando e parou**. O
seletor ofereceu sete maneiras de mexer num convidado:

    parar (destrutiva) · desligar · suspender · reiniciar ·
    retomar · migrar · relocar por HA

E **cortou `proxmox_start_guest`**, que é a única que conserta este incidente.

Não é que o agente tenha escolhido não agir. **Ele não tinha como.** Tinha a
ação destrutiva que causa este incidente e não tinha a que o desfaz.

A causa está em `gateway/runtime/investigator.py::_select_tools`: as candidatas
são ranqueadas por `CatalogueRanker` contra `IncidentSignals(alert_source,
summary)` e cortadas em 40. Com sete integrações conectadas há mais de 40
candidatas, então o corte é real e alguém fica de fora — e neste incidente quem
ficou foi a ação que o resolve.

No run do laço de leitura, sobre outro alerta, seis ações de convidado foram
oferecidas entre as mesmas 40. O ranqueamento responde ao alerta; o que ele não
faz é garantir que a ação que desfaz o estado descrito esteja entre as que
sobrevivem ao corte.

## O que isso muda no que a onda afirmou

O laço **pode** fechar. A maquinaria está construída, o balcão trata vinte ações,
o portão se registra por run, e treze ações chegaram a ser oferecidas.

O que impediu esta demo de fechar foi o ranqueamento, não o vocabulário — e essa
é uma correção com dono, um arquivo e uma linha, em vez de uma decisão de escopo
de produto que eu havia empurrado para o operador.

## Como isto foi encontrado

Porque o operador perguntou por que esta tarefa não podia ser feita. Ela podia:
o transcript está no store, o conjunto oferecido é gravado por turno, e o
catálogo responde por uma chamada. Eu não tinha olhado nenhum dos três.

---

## Segunda correção: o ranqueamento também não era a explicação

Escrevi acima que o seletor cortou `proxmox_start_guest` por ranqueamento.
Fui medir e a coisa é mais interessante.

**O balcão trata a ação.** `capabilities/tools/remediation/proxmox/guests.py`
declara `START` com `capability="proxmox_start_guest"`, e
`components_for(START, verifier=StartedVerifier())` lhe dá os quatro
componentes que o balcão exige. Ela não é filtrada por `_can_carry`.

**E o ranqueamento não a rejeita por princípio.** Rodado localmente contra um
sinal desta forma, `proxmox_start_guest` sai em 19º com escore 0,909 — dentro
de qualquer corte de 40. Enquanto isso `proxmox_reboot_guest` sai em 77º com
escore **zero** e *foi* oferecido ao run real.

Ou seja: a posição depende do objetivo real da investigação, que eu não
consigo reconstruir, e reconstruí-lo por aproximação produz uma ordem que
contradiz o que aconteceu. **Não vou afirmar a causa que não medi** — foi
exatamente assim que errei duas vezes nesta mesma investigação.

## O que está provado, e é suficiente

1. `proxmox_start_guest` existe, é `write_reversible`, tem os quatro
   componentes, e o balcão a trata.
2. Ela **não** estava entre as 40 oferecidas ao run da demo.
3. Sete outras ações sobre convidados estavam: parar, desligar, suspender,
   reiniciar, retomar, migrar, relocar.
4. O incidente era, textualmente, um convidado que estava rodando e parou.

O agente tinha sete maneiras de mexer naquele convidado e nenhuma que o
resolvesse. Ele não escolheu não agir.

## E o defeito que impede de saber por quê

O store grava, por turno, um campo chamado **`selection_rationale`**.

    turno 1   offered_capabilities: 40   selection_rationale: (vazio)
    turno 2   offered_capabilities: 40   selection_rationale: (vazio)
    turno 3   offered_capabilities: 40   selection_rationale: (vazio)
    turno 4   offered_capabilities: 40   selection_rationale: (vazio)
    turno 5   offered_capabilities: 40   selection_rationale: o resumo da investigação

Nos quatro turnos que fizeram seleção ele está vazio. No quinto carrega o
relatório do modelo, que não é a razão da seleção de coisa nenhuma.

**Existe um campo para explicar por que uma capacidade foi ou não oferecida, e
ele não explica.** É por isso que a pergunta acima ficou sem resposta: não
porque a informação seja inalcançável, mas porque o lugar onde ela deveria
estar está vazio — e um campo vazio com um nome desses é pior que campo
nenhum, porque quem procura acha e conclui que não há o que dizer.

Este é o achado com dono e com conserto claro. E é da mesma família de tudo o
que esta onda vem fechando: uma superfície que afirma explicar e não explica.

---

## Terceira correção, e desta vez a causa está medida

As duas explicações acima estavam erradas, e a terceira não é minha honra:
**fui eu quem causou o efeito que passei o dia chamando de defeito do produto.**

A regra de alerta que escrevi tem a descrição em português. Todo o catálogo de
capacidades declara os seus casos de uso em inglês, e o escorador ordena por
sobreposição de termos entre o resumo do incidente e esses casos de uso.

Uma frase, duas línguas, medido com o escorador do próprio produto:

    "ProxmoxGuestStopped: redis (lxc/122) estava em execucao no no pve01 e parou."
      proxmox_start_guest      0.0000
      proxmox_stop_guest       0.0000
      proxmox_shutdown_guest   0.0000

    "ProxmoxGuestStopped: The guest redis (lxc/122) was running on node pve01
     and has stopped."
      proxmox_start_guest      0.7407
      proxmox_stop_guest       0.7692
      proxmox_shutdown_guest   0.7692

E o que isso faz com a seleção inteira, ranqueando as 60 candidatas que este
deployment conectou:

| descrição do alerta | posição de `proxmox_start_guest` | escore | resultado |
|---|---|---|---|
| português | 63º | 0,000 | **cortada** |
| inglês | **13º** | 1,818 | **oferecida** |

**Uma variável.** O idioma em que o operador escreve o alerta decide se o
deployment recebe a ação que conserta o incidente.

## O achado que sobra, e é maior que o que eu procurava

Não é que o catálogo esteja vazio — tem 24 capacidades de escrita. Não é que o
ranqueamento seja arbitrário — ele põe a ação em 13º quando os termos casam.

É que **a seleção depende do idioma e nada diz isso**. Um deployment cujos
alertas estão na língua do operador pontua **todas** as capacidades em zero, e
aí o desempate é por nome: entrar na oferta passa a depender da posição no
alfabeto. Foi exatamente o que a gravação mostrou — vinte capacidades cortadas,
todas com escore zero, ordenadas alfabeticamente, e `proxmox_start_guest` entre
elas porque "s" vem tarde.

O produto degrada em silêncio. Não recusa, não avisa, não pontua diferente de
um empate legítimo: entrega quarenta ferramentas escolhidas por ordem
alfabética e segue como se tivesse escolhido.

Isto não é hipótese de laboratório. Eu escrevi aquele alerta em português
porque é a língua do operador deste deployment, que é o que qualquer operador
brasileiro faria, e o efeito apareceu na primeira tentativa.

## O que foi consertado, e o que fica

Consertei a **minha** regra: `infra-cluster` commit `d74b3f3`, a descrição
reescrita em inglês, com a razão no comentário para que ninguém a traduza de
volta sem saber o que custa.

O que **não** consertei é o produto, e é decisão de escopo com dono: ou o
escorador deixa de depender do idioma, ou um deployment cujos alertas não estão
em inglês precisa ser avisado disso em vez de descobrir por acidente.

E nada disto seria visível sem a instrumentação que este mesmo trabalho
produziu. Antes dela o campo `selection_rationale` estava vazio e a resposta era
inalcançável; depois dela a própria gravação do run diz `ranked 60, offered 40,
cut by the ceiling 20` e nomeia cada uma com o seu escore. **Foi o produto,
instrumentado, que me mostrou que o erro era meu.**
