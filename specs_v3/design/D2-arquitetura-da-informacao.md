# D2 — Arquitetura da informação

## O problema com a navegação de hoje

Quatorze telas em quatro grupos — Operate, Estate, Learn, Govern. Os grupos são
defensáveis e o resultado não funciona, por dois motivos:

**Os nomes descrevem o sistema, não a tarefa.** "Govern" contém Configuration,
Administration, Autonomy e Audit — quatro coisas que só têm em comum serem
chatas. Um operador que quer trocar um limiar não pensa "vou governar".

**Não há hierarquia de frequência.** Dashboard e Audit têm o mesmo peso visual, e
um deles é aberto cem vezes mais que o outro.

## A navegação proposta

Três zonas, separadas por frequência de uso, não por assunto:

```
▸ AGORA          o que está acontecendo
   Painel
   Incidentes
   Investigações
   Aprovações              ← contador quando houver pendência

▸ O AMBIENTE     o que existe e o que se sabe
   Recursos
   Topologia
   Detectores
   Conhecimento
   Memória

▸ AJUSTES        o que a plataforma é
   Primeiros passos        ← só enquanto a checklist não fecha
   Agente
   Integrações
   Dados                   ← entrada, roteamento, saída (062)
   Configuração
   Contexto da equipe
   Mudanças propostas      ← contador quando houver pendência
   Identidade e acesso
   Auditoria
```

Quatro mudanças que carregam a maior parte do ganho:

1. **"Agora" no topo, sempre.** É onde alguém está quando algo quebrou.
2. **Contadores nos dois lugares que esperam decisão humana** — aprovações e
   mudanças propostas. Uma fila que só existe atrás de um item de menu é uma fila
   que cresce até alguém descobri-la.
3. **"Primeiros passos" aparece e some.** Enquanto a checklist tiver item
   pendente ele fica; fechada, sai da navegação e continua alcançável por
   Ajustes.
4. **"Dados" como item próprio** (spec 062). Entrada, roteamento e saída são a
   pergunta "de onde veio e para onde foi", e ela não é uma configuração entre
   outras.

## Hierarquia dentro da tela

Três níveis, e nunca um quarto:

- **Cabeçalho de área** — onde estou, e a ação principal daqui.
- **Painéis** — cada um com um estado próprio: carregando, vazio, erro, pronto.
  Uma dependência indisponível derruba seu painel, jamais a rota (spec 050).
- **Linhas e campos** — o conteúdo.

Um painel que precisa de sub-painéis está tentando ser uma tela. Vira uma.

## Estados vazios são conteúdo

Todo painel vazio diz três coisas, nesta ordem: **o que falta**, **por que**, e
**o que fazer**, com o que fazer sendo um link para o lugar exato.

A tela de Configuration já faz isso — *"No configuration here. Every node
inherits from the one above it. This one sets nothing of its own"* — e é o padrão
para todas.

**Números zerados não são estado vazio.** `0 investigações` num deployment novo é
um fato honesto e fica visível. Esconder o painel até haver dado é como o produto
parece quebrado no primeiro dia.

## Ações destrutivas e irreversíveis

Três níveis, e o meio é o que costuma faltar:

| Nível | Exemplo | Tratamento |
|---|---|---|
| reversível | entrar em manutenção, desabilitar detector | age direto, desfazer visível |
| consequente | promover configuração, aprovar mudança | exige ver o efeito antes (preview / dry-run) |
| irreversível | revogar token, desligar guardrail | confirmação que nomeia o que se perde |

"Tem certeza?" não é confirmação. Confirmação nomeia a consequência.

## Busca

Uma paleta por atalho de teclado, sobre recursos, investigações, incidentes,
documentos e telas. Num estate de 57 recursos em sete zonas, navegar por menu
para chegar num container específico é a interação errada.

## Responsividade

O alvo real é um monitor grande. Mas incidente chega no celular, e há duas coisas
que precisam funcionar lá: **ler uma investigação** e **aprovar ou recusar**.
Configuração pode exigir tela grande; decidir, não.
