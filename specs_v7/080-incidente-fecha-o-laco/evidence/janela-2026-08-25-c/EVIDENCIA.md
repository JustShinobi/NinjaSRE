# A quarta janela — e a causa real, medida até o fim

CT122 fora das 22:02:21Z às 22:06:23Z. Versão `gitops 9c70cb4d2876`, com o
`INVESTIGATION_SYSTEM_PROMPT` publicado. Portão local completo verde antes de
publicar: `make verify` exit 0, 12.779 passed / 31 skipped, 37 benchmarks.

## O prompt funcionou

Pela primeira vez em quatro janelas, o agente **chamou** a ação:

| # | capacidade | resultado |
|---|---|---|
| 0 | `prometheus_active_alerts` | succeeded |
| 1 | `proxmox_guest_tasks` | succeeded |
| 2 | `proxmox_guest_start_diagnosis` | succeeded |
| 3 | `logs_for_resource` | failed (sem fonte de log) |
| 4 | `grafana_recent_changes` | succeeded |
| 5 | `proxmox_ha_state` | succeeded |
| 6 | **`proxmox_start_guest`** | **failed** |
| 7 | `assess_evidence_sufficiency` | succeeded |

`approvals` = 0, `rollback_plans` = 0.

## Defeito 1 — o portão recebe os argumentos vazios

O log do processo, `deploy/app`, em 22:05:36.317Z:

```json
{"point": "pre_tool_use", "hook": "remediation.pre_tool_use",
 "error": "proxmox_start_guest needs the node, the guest number and the guest
           kind, and was given {}. A write that guessed any of the three would
           reach a guest with the same number and a different identity.",
 "event": "agent.hook_failed", "level": "warning"}
```

E a chamada gravada, na mesma instância:

```json
"arguments": {"kind": "lxc", "node": "pve01", "vmid": 122}
```

**O modelo mandou os três argumentos e o portão viu `{}`.**
`core/agent/hooks/registry.py:132` monta `arguments = dict(call.arguments)`, e
o `ToolCall` que chega ao ponto `pre_tool_use` está vazio. Como toda escrita
atravessa esse portão, toda escrita levanta exceção e **nenhuma jamais vira
proposta** — que é por que `approvals` nunca saiu de zero em nenhuma janela.

### A fronteira do que está apurado

Localizado: `capabilities/tools/remediation/proxmox/plane.py::_guest_of` levanta
o erro porque `action.arguments` está vazio, e o `action_for` do portão monta
esses argumentos a partir de `call.arguments`. Então o `ToolCall` que chega ao
ponto `pre_tool_use` está vazio.

**Não apurado**: qual camada perde os argumentos entre o modelo e o gancho. O
candidato mais provável é a leitura da resposta do provedor
(`core/llm/providers/gemini.py:174-184` faz `function_call.get("args")` e cai
para `{}` quando o valor não é um mapa), mas a linha gravada em `tool_calls`
carrega os três argumentos, então alguma coisa os tem. Duas leituras do mesmo
instante discordam, e dizer qual está certa exige medir — não deduzir.

## Defeito 2 — o portão falha aberto

`core/agent/hooks/registry.py:139`:

```python
except Exception as error:  # noqa: BLE001 — a crash is not a decision
    failures.append(_failure(hook, error))
    logger.warning("agent.hook_failed", ...)
```

A falha é coletada, registrada como aviso, e **a chamada segue**. Foi por isso
que o corpo de `proxmox_start_guest` rodou e recusou.

**E isto é deliberado, não um descuido.** A docstring do próprio módulo o
declara e dá a razão: *"A crash in `pre_tool_use` is read as `Allow`, never as
`Deny`. Reading it as a denial sounds safer and is not: a broken masking rule
would silently disable every write in the system."* O argumento é bom para um
gancho de mascaramento.

Não houve dano porque toda capacidade de remediação carrega a própria rede
(`capabilities/tools/remediation/_base.py::UNGATED_REFUSAL`), e foi ela que
segurou — o que provavelmente é a estratificação pretendida.

O que fica como tensão a revisitar, e não como defeito: para o portão do Artigo
III especificamente, um crash **é** um allow, e hoje quem sustenta a garantia é
a rede de segurança da capacidade, não o portão. Uma capacidade de remediação
que algum dia não a carregue executaria sem aprovação, e nada no portão
notaria. Vale distinguir, no registro de ganchos, um gancho observador de um
gancho de decisão — mas essa é decisão de desenho de quem escreveu a razão
acima, não conserto que uma sessão de execução deva fazer sozinha.

## A cadeia inteira, e o que cada janela eliminou

| # | explicação | eliminada por |
|---|---|---|
| 1 | o catálogo não tem ação de infraestrutura | contagem: 24 de escrita, 20 de remediação |
| 2 | o escorador corta a ação pelo idioma do alerta | regra reescrita; oferecida em 20ª de 40 |
| 3 | a evidência do motivo não chega (501) | endpoint consertado; as duas leituras passam |
| 4 | a parada parece manutenção deliberada | parada provocada sem registro de tarefa |
| 5 | o agente não sabe que pode propor | prompt de serviço; **ele chamou** |
| **6** | **o portão recebe `{}` e falha aberto** | **é esta. Medida no log do processo.** |

Cinco explicações caíram antes desta, e todas as cinco eram verdadeiras a
respeito de algo — só nenhuma era a causa. A lição que fica é sobre método: as
quatro primeiras foram deduzidas de leitura de código e de contagens, e a que
valeu veio do log do processo no instante da falha, que ninguém tinha aberto.
