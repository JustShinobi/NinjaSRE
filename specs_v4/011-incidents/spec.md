# 011 — Incidents

A tela mais saudável do grupo Now. Os problemas são de contexto, não de
mecânica.

## Problemas

### 1. [bloqueia entendimento] O vazio não explica o vazio

O empty state diz "A detector opens an incident when what it watches crosses
its threshold. None has." — mas neste deployment **não há detector nenhum
ligado** (Detectors: "No detectors yet", guardian desligado). O texto sugere
que tudo está bem; a verdade é que nada está olhando. O empty state precisa
distinguir os dois estados:

- Nenhum detector ativo ⇒ "Nenhum detector está ligado, então nenhum incidente
  será aberto. Ative a observação contínua" + link (Detectors/Configuration).
- Detectores ativos e nada disparou ⇒ o texto atual, que aí sim tranquiliza.

O dado para distinguir já existe (o rodapé Guardian mostra "Detectors live
0 of 0").

### 2. [polimento] Filtros que filtram nada

State/Severity aparecem com única opção "Any" quando não há incidentes.
Filtros sem opções escondem-se; ou ficam desabilitados com tooltip.

### 3. [polimento] Duplicação do CTA na árvore de acessibilidade

"See what is being watched for" aparece duas vezes (botão aninhado em card
clicável). Um único elemento interativo.

### 4. [polimento] Sem preview do que um incidente será

O operador em pré-alfa nunca viu um incidente. Um link "como um incidente se
parece" (screenshot/exemplo em doc) ou um incidente de demonstração tornaria o
conceito concreto — a referência (demo.opensre.in) faz onboarding inteiro em
cima de cenários de exemplo. Opcional, mas barato.

## Critérios de aceite

- Com zero detectores ativos, o empty state diz explicitamente que nada está
  observando e aponta o caminho de ativação.
- Nenhum controle de filtro aparece com uma única opção "Any".
