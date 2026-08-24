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
