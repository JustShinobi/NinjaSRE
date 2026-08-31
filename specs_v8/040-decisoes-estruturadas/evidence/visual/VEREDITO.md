# Veredito visual — Decisões, slot S2

Capturado no staging real depois do deploy de todos os componentes e do
aquecimento das rotas. Cada captura teve o tema conferido duas vezes antes de
valer: a escolha declarada pelo próprio controle e a cor de fundo medida. O
controle é tri-estado (claro → escuro → sistema), então um clique não é "o
outro tema" — vindo do escuro ele cai em sistema, que renderiza claro e parece
sucesso.

Comparado com `design/padrao-2026-08/Decisions.dc.html`.

| Tela × tema | Veredito |
|---|---|
| `/decisions` escuro | CONFORME — com uma ressalva de dado, abaixo |
| `/decisions` claro | idem |
| `/decisions?tab=changes` escuro | CONFORME |
| `/decisions?tab=changes` claro | CONFORME |

## O que conforma, e é a maior parte

A anatomia do cartão é a do artboard: título, medidor "Risco N de 5" com as
cinco barras, chip de estado à direita; "O que vai acontecer" numerado com o
nome da capacidade em mono; "Se der errado — reversão" numerado; "Por quê";
"Evidência que sustenta" com um `ver →` por item; "Raio de alcance"; a linha de
autonomia numa caixa contornada; e o payload bruto atrás de um disclosure, não
como conteúdo primário.

O rodapé âmbar da expirada está inteiro — a frase explicando que a janela
fechou, "Propor de novo, agora" preenchido e "Descartar" discreto — e é o que
fecha o beco sem saída que a auditoria de partida desta onda registrou. Abaixo,
"Decididas recentemente" com o desfecho por linha.

## O desvio, com a causa cravada

**"Por quê" imprime a mesma string que "O que vai acontecer".** Não é a tela
inventando: o banco guarda um único campo `rationale`, e o cartão o renderiza
nas duas seções. O artboard desenha dois textos genuinamente diferentes — o
passo é o que será executado, o porquê é a justificativa do ambiente.

Repetir é pior do que mostrar uma vez só, porque faz o cartão parecer dizer
duas coisas quando diz uma. O conserto honesto, sem inventar dado que a
implantação não tem, é imprimir uma vez, na seção a que a frase pertence.

## Diferenças que não são desvio

- **Dado.** Os textos, contagens e evidências do staging não são os do
  artboard. O raio de alcance vem `0 recurso(s) conhecido(s)` porque a
  topologia do staging não registra dependentes deste recurso.
- **Idioma.** O board é pt-BR e a sessão capturada estava em inglês. i18n, com
  as duas metades do catálogo presentes e em paridade.


## A segunda rodada: o desvio fechou, e onde ele ainda aparece

O reparo não estava onde o desvio aparecia. O cartão nunca esteve errado — ele
recebe "por quê" e "passo 1" como dois campos independentes. Quem escrevia o
mesmo valor nos dois era o construtor do payload, no servidor. O passo passou a
carregar a operação que a ação já computava: *a operação exata que uma pessoa
poderia rodar no lugar*. Nenhuma linha de console mudou.

**Provado no ambiente real, e não só em teste.** A proposta expirada do staging
foi reproposta pela própria tela — a única escrita propose-only que o protocolo
permite —, e os dois payloads gravados dizem o seguinte:

| aprovação | `steps[0].description` | igual ao `intent`? |
|---|---|---|
| expirada, gravada antes do reparo | a justificativa | **sim** |
| reproposta, gravada depois | `proxmox_start_guest(kind='lxc', node='pve01', vmid=122)` | **não** |

**A ressalva, que é de dado e não de código.** Um payload é documento gravado,
então o reparo não é retroativo: a aprovação expirada guarda a duplicação com
que nasceu. E ela é justamente o cartão que a tela expande, porque a fila é
montada com expiradas primeiro. Quem olhar `/decisions` no staging hoje vai ver
a repetição no cartão de cima — não porque o defeito persista, mas porque
aquela linha é anterior à correção. Isto quase foi registrado como defeito
remanescente; foi conferido lendo os dois payloads de dentro do cluster.

## O que o repropor mediu, de resto

Total de 4 para 5 linhas, uma nova pendente carregando `origin_approval_id` — o
vínculo de origem que a feature prometeu —, e a expirada continua expirada.
Nada foi apagado: todo desfecho é um estado.
