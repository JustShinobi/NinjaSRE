# 059 — Contexto operacional da equipe

**Depende de:** 058. **Reforça:** 054, 055.

Fatos que um humano escreve uma vez e que entram em toda investigação. É a
diferença entre um agente genérico e um agente que conhece *este* ambiente.

## A lacuna, com precisão

O `AgentsConfig` já tem `PromptOverrides` — um prompt de sistema por papel
(`investigator`, `intake`, `diagnose`), cada um caindo de volta no prompt
enviado com o produto. E o cabeçalho do módulo é explícito sobre a decisão:
*"prompt defaults are code; prompt overrides are configuration"*.

Isso é **substituir**. O que falta é **acrescentar**.

A diferença não é acadêmica:

- Substituir o prompt do investigador significa que o operador perde as
  melhorias do prompt distribuído para sempre, e ninguém percebe — a
  configuração continua válida enquanto o texto envelhece.
- Acrescentar fatos operacionais é seguro por construção: o prompt distribuído
  continua a evoluir, e o que o operador escreveu continua verdadeiro.

Um operador que só tem "substituir" para dizer *"nossos containers são LXC"* vai
copiar o prompt inteiro, colar a frase no fim, e ficar preso na versão daquele
dia. O campo errado força o uso errado.

## Por que este cluster torna isso urgente

Há pelo menos três fatos sobre este ambiente que nenhuma integração ensina e que
mudam a conclusão de uma investigação:

1. **Métrica de container LXC vem do host, por VMID** — não de dentro do guest
   (spec 054). Um agente que não sabe disso lê o número errado com confiança.
2. **A zona `vk8s` tem MTU 1450 sobre underlay 1450**, e existe um postmortem
   sobre exatamente essa armadilha. É um fato de rede que explica uma classe
   inteira de sintoma.
3. **`criticality` não vem do Proxmox**, vem do inventário — e é o que separa
   "um container parado" de "um incidente".

Escrever isso uma vez, num lugar, e ter em toda investigação é provavelmente a
melhoria de qualidade mais barata de toda a specs_v3.

## Escopo

### A. Um campo aditivo, por nó

`AgentsConfig` ganha contexto operacional: texto estruturado em seções
nomeadas, acrescentado ao prompt do sistema em vez de substituí-lo, **por nó da
árvore de configuração** — de modo que a organização declare o que vale para
todo mundo e uma equipe acrescente o que é só dela, com a mesma herança e a
mesma proveniência de qualquer outro valor (058).

Seções nomeadas em vez de um bloco de texto livre porque uma seção pode ser
herdada, sobrescrita ou removida por nível, e um bloco só pode ser substituído
inteiro.

### B. Limites, e por que existem

- **Orçamento de tokens declarado e verificado.** Contexto operacional entra em
  toda investigação, logo todo caractere é pago em toda chamada. Passar do
  orçamento é erro de validação, não truncamento silencioso.
- **Sem segredo.** A mesma varredura da 056 vale aqui, e com mais razão: este
  texto vai para o provider de modelo. Um campo que aceita texto livre e é
  enviado para fora é exatamente onde uma senha acaba colada.
- **É fato, não instrução.** A distinção importa: *"containers LXC reportam
  métrica pelo host"* é um fato que melhora o raciocínio; *"sempre reinicie o
  serviço antes de investigar"* é uma instrução, e instrução operacional
  pertence a runbook (056) ou a política de autonomia (058), onde é auditável e
  reversível. A interface deve dizer isso, e os modelos devem exemplificar
  fatos.

### C. Um template inicial, específico deste deployment

Uma pessoa diante de um campo de texto vazio escreve nada. Um template com as
seções que valem a pena — o que roda aqui, como a rede é organizada, o que
significa criticidade, onde as métricas realmente moram, quem é chamado —
transforma "escreva o contexto" numa tarefa de preencher lacunas.

Para a validação, boa parte do template pode ser **derivada**: as zonas e seus
`/24` vêm do estate do 053, as fontes de sinal vêm do mapa da 054. O que sobra
para o humano é o que só ele sabe.

### D. Onde aparece

Uma tela própria, editável, com pré-visualização de como o texto entra no prompt
— a mesma disciplina da 058: nada é salvo sem que se veja o efeito. E o efeito
aqui é literalmente o texto que o modelo vai receber.

## Fora de escopo

- Contexto por investigação. Isso é a descrição do incidente, não configuração.
- Geração automática do contexto por LLM. Derivar do estate é dado; inventar
  fatos operacionais não é.
- Substituir `PromptOverrides`. Os dois coexistem, e a interface deve deixar
  claro que um acrescenta e o outro substitui.

## Aceitação

1. O contexto operacional é acrescentado ao prompt do sistema sem remover o
   prompt distribuído, e um teste prova que os dois chegam ao modelo.
2. Seções herdam pela árvore de configuração com proveniência, como qualquer
   outro valor.
3. Passar do orçamento de tokens é recusado na validação, nomeando o excesso.
4. Um contexto contendo algo com formato de credencial é recusado, sem registrar
   o valor.
5. O template inicial vem preenchido com as zonas e fontes de sinal que o estate
   já descobriu.
6. A tela mostra o texto final que o modelo receberá, antes de salvar.
