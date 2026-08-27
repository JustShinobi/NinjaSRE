# 052 — Primeiro uso no console

**Depende de:** 051.

Um operador entra num deployment novo e é informado do que fazer, em ordem, com a
razão de cada passo e a possibilidade de parar depois de qualquer um deles.

## O que o operador precisa configurar, e por que cada coisa

O assistente da CLI já estabelece a ordem, e a ordem é o projeto:

1. **Um provider de modelo.** Nada mais pode ser verificado sem um, e a plataforma
   se recusa a iniciar sem um configurado. Nove são oferecidos com o mesmo peso,
   incluindo o local.
2. **A credencial desse provider**, para dentro do cofre.
3. **Um modelo**, entre os que o provider é conhecido por servir.
4. **Integrações** — oferecidas, nunca obrigatórias. Um deployment com provider e
   sem integração ainda investiga, a partir do que lhe é contado em vez do que
   consegue consultar. Forçar uma escolha aqui é como se abandona o fluxo no
   passo três.
5. **Verificação** — não opcional, e faz uma requisição real.

A isso o console acrescenta dois passos que a CLI não tem onde colocar:

6. **Um estate para observar.** Nesta validação, o cluster Proxmox (053). É o
   passo que transforma uma plataforma instalada numa que sabe do que é
   responsável.
7. **De onde os alertas chegam.** Os receptores de webhook já existem; nada aponta
   para eles (055).

## Onde isso mora

**Revisado.** A primeira versão desta spec mandava redirecionar para uma rota
`/first-run` fora do shell, bloqueando até haver provider verificado. Está
errado, e caminhar por uma implementação madura do mesmo problema mostrou por
quê: o redirecionamento esconde o produto justamente de quem ainda está
decidindo se vai usá-lo.

O modelo correto tem três partes:

**O dashboard aparece sempre.** Mesmo zerado — `0 investigações`, `0% de
sucesso`, `MTTD N/A`. Números honestos num deployment novo são informação, não
constrangimento, e a alternativa (esconder o produto atrás de um formulário) é
pior.

**Um tutorial em passos, por cima, dispensável.** Uma sobreposição com indicador
de progresso e um `Pular` visível, que explica em ordem: o que a plataforma faz,
como a investigação funciona, o que conectar, como ajustar o agente, e como
testar antes de valer. Ele ensina enquanto o produto está atrás dele, em vez de
no lugar dele.

**Uma checklist persistente que sabe onde você parou.** É o
`GET /v1/setup/checklist` da 051, exposto como um painel que não some enquanto
houver passo pendente, com o item que falta clicável. É isto — e não o
redirecionamento — que garante que ninguém abandone a configuração pela metade:
o estado fica visível no lugar onde a pessoa trabalha.

Um deployment sem provider ainda precisa dizer isso com clareza, e continua sem
poder investigar. A diferença é que ele diz **num aviso acionável dentro do
dashboard**, não trancando a porta.

### Duas coisas a mais que valem copiar

**Um painel de ações rápidas** ao lado do estado: carregar conhecimento,
configurar o agente, ver a memória. São exatamente os passos que a checklist
está cobrando, alcançáveis num clique a partir de onde a pessoa já está.

**Um "testar agora" antes de valer para produção.** Descrever um incidente em
texto e ver a investigação rodar, com a ressalva escrita ao lado: *a qualidade
depende das integrações configuradas; sem elas o agente raciocina mas não
consulta nada*. Isso resolve a tensão entre "quero ver funcionando" e "ainda não
liguei nada", e é honesto sobre a diferença. `POST /v1/investigations` já existe;
falta o gatilho na interface.

## O formato de cada passo

Um passo por tela, com a lista de passos visível e os concluídos reabríveis. Todo
passo é um formulário que posta numa rota que existe — é exatamente para isso que
a 051 vem primeiro.

**Provider.** Os nove, cada um com seu `display_name`, se roda localmente ou é
hospedado, e sua string de `guidance`. A orientação não é enfeite: *"Hosted.
Requests leave your infrastructure for Anthropic's API"* é a frase que faz alguém
num ambiente regulado escolher diferente, e já está escrita para todos os
providers.

**Credencial.** Campos gerados a partir dos `CredentialFieldSpec` declarados pelo
provider — `label`, `help`, `secret`, `required`. Campos secretos são
`type="password"`, `autocomplete="off"` e **somente-escrita**: o valor posta uma
vez e nunca é renderizado de volta, nem mascarado, porque um valor mascarado no
DOM ainda é um valor no DOM. O `where_to_get_it` aparece ao lado do campo.

**Modelo.** Os modelos conhecidos do provider quando ele os declara; um campo
livre com o padrão quando não declara.

**Integrações.** O catálogo, pesquisável, com as relevantes para um estate
descoberto em primeiro lugar. Cada uma abre o mesmo formulário dirigido por
schema. Falhar numa não abandona as outras — o `setup_many` já continua depois de
uma falha e reporta no fim, e o console não pode ser mais rígido que a CLI.

**Verificar.** Uma verificação real por coisa configurada, cada uma com sua linha
de resultado e sua repetição. Uma falha nomeia o campo que foi pulado quando essa
é a causa; o `SetupOutcome.skipped` já carrega isso.

## O que não pode acontecer

- **Nenhum segredo é ecoado.** Nem em resposta, nem em atributo renderizado no
  servidor, nem no payload de um React Server Component, nem em erro. A rota de
  sessão do console já estabelece esse padrão para a senha.
- **Nenhuma credencial em URL**, parâmetro de query ou redirecionamento.
- **Nenhum passo grava credencial em configuração.** A rota de credencial da 051
  é o único caminho.
- **O assistente é retomável.** O estado mora no deployment — a checklist — não no
  navegador. Quem fecha a aba depois do passo três volta no passo quatro, e quem
  roda o assistente da CLI em vez disso vê o console concordar.

## Estados vazios fazem parte desta spec

Um deployment em meio ao onboarding renderiza honestamente, não em branco. A tela
de Configuration já faz isso bem — *"No configuration here. Every node inherits
from the one above it. This one sets nothing of its own"* — e esse padrão vale
para toda tela que o operador alcance antes de o estate existir: dizer o que
falta, por quê, e qual passo estabelece aquilo.

## Aceitação

1. Um deployment novo renderiza o dashboard com números zerados, mostra o
   tutorial dispensável, e exibe a checklist com o passo pendente clicável — sem
   redirecionar para fora do shell.
2. O fluxo completo termina no navegador sem nenhuma participação da CLI,
   resultando num provider verificado e ao menos uma integração verificada.
3. Um teste percorre o fluxo e varre todo corpo de resposta, linha de log e
   página renderizada procurando o segredo informado; falha se ele aparecer.
4. Matar o navegador no meio do fluxo e voltar retoma no passo certo.
5. Rodar `ninjasre onboard` contra o mesmo deployment produz o mesmo estado de
   checklist — as duas superfícies concordam porque leem uma fonte só.
6. Toda tela alcançada antes de o estate existir nomeia o que falta e qual passo
   fornece aquilo.
