# 062 — Ingestão e entrega: de onde veio, para onde vai

**Depende de:** 051, 058. **Absorve parte de:** 055.

Uma seção de configuração própria para o trânsito de dados: o que entra, de onde,
por onde passa, o que sai e para quem. Hoje isso está espalhado por sete rotas de
webhook, um catálogo de integrações e nenhuma tela.

## Por que é uma seção própria, e não um canto da configuração

A configuração hierárquica da 058 responde *"que valor vale aqui"*. Esta seção
responde uma pergunta diferente, e é a pergunta que o operador faz quando algo
não chegou ou chegou errado:

> **De onde veio isto, e para onde foi?**

São perguntas de trânsito, não de valor. Misturá-las com limiares e orçamentos é
como o operador acaba abrindo cinco telas para descobrir por que um alerta não
virou investigação.

## Escopo

### A. Entrada — o que chega, e por onde

As sete rotas de webhook já existem (`alertmanager`, `grafana`, `datadog`,
`pagerduty`, `opsgenie`, `sentry`, `generic`). O que falta é a superfície que as
torna operáveis:

- **Por origem**: a URL, o token, o formato esperado, e o que o remetente precisa
  configurar do lado dele — pronto para copiar. O token é de máquina, com
  permissão mínima; receber alerta não é permissão de investigar tudo.
- **Estado ao vivo**: última entrega recebida, contagem por janela, e as últimas
  rejeitadas com o motivo. Uma origem configurada que nunca entregou nada é
  indistinguível de uma que não existe, e essa é a falha mais cara desta
  categoria — porque é silenciosa.
- **Amostra do último payload**, com a política de mascaramento aplicada. É o que
  responde "o formato mudou?" sem ninguém abrir tcpdump.

### B. Roteamento — o que fazer com o que chegou

Regras avaliadas em ordem, cada uma dizendo: **que sinais casam**, **para qual
equipe vão**, e **o que acontece** — abrir investigação, apenas registrar, ou
descartar com motivo.

O casamento usa o que a 055 já define: rótulos do alerta resolvidos a um recurso
do estate por endereço, VMID ou domínio. Uma regra pode casar por origem, por
zona, por criticidade ou por recurso — e a zona e a criticidade vêm do estate da
053, não de texto digitado.

**Toda regra tem simulação.** Colar um payload real, ou escolher uma entrega
recente, e ver qual regra pega, para qual equipe vai e o que dispararia — antes
de salvar. É a mesma disciplina do `preview` da 058 e do `dry-run` de detector:
nada que decide comportamento é salvo sem que se veja o efeito.

**A última regra é sempre visível**, e o que ela faz com o que não casou é uma
escolha explícita, não um padrão implícito. Descarte silencioso é como um alerta
some sem ninguém saber que sumiu.

### C. Saída — para onde vai o resultado

O simétrico da entrada, e hoje inexistente. Um destino declara: que eventos
recebe (investigação concluída, remediação proposta, aprovação pendente,
degradação de origem), por qual canal, e com qual nível de detalhe.

O nível de detalhe é uma decisão de segurança, não de gosto: um resumo num canal
de chat e o relatório completo atrás de um link autenticado é uma escolha
diferente de mandar tudo no corpo da mensagem. **Nenhum destino recebe segredo
ou evidência bruta por padrão** — o que sai é o que a política de mascaramento
deixa sair, e o destino mostra qual política está aplicada.

Falha de entrega é estado visível, com repetição e com histórico. Um relatório
que não chegou é pior que um que não existiu, porque alguém está esperando por
ele.

### D. Proveniência — a coluna que amarra tudo

Todo dado que a plataforma usa carrega de onde veio, e isso precisa ser
consultável a partir da tela: este achado veio desta consulta, nesta origem,
neste instante; este alerta entrou por esta rota, casou nesta regra, foi para
esta equipe.

Já existe a metade difícil: a configuração tem proveniência por valor e a
investigação atribui cada afirmação à sua origem. Falta a mesma disciplina para o
trânsito.

## Fora de escopo

- Transformar payload com script do operador. Uma linguagem de transformação é um
  produto dentro do produto, e um lugar novo para segredo aparecer.
- Fila de mensagens própria. As origens já entregam por HTTP.
- Criar as integrações de saída que ainda não existem no catálogo. Esta spec
  define a superfície; quais canais existem é a 051/054.

## Aceitação

1. Cada rota de entrada mostra URL, token, formato e a última entrega — com data,
   resultado e amostra mascarada.
2. Uma origem configurada que nunca entregou aparece como tal, sem o operador
   precisar procurar.
3. Uma regra de roteamento pode ser simulada contra um payload real antes de
   salvar, mostrando regra, equipe e ação.
4. O destino do que não casou é uma escolha explícita e visível.
5. Um destino de saída declara eventos, canal e nível de detalhe, e mostra a
   política de mascaramento aplicada.
6. Uma entrega que falhou aparece com motivo e pode ser repetida.
7. Dado um achado, a interface responde de qual consulta, origem e instante ele
   veio.
