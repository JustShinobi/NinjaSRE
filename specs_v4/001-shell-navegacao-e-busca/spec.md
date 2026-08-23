# 001 — Shell: tour, busca, notificações, topbar, i18n

O que envolve todas as telas. Três defeitos aqui aparecem para o operador antes
de qualquer tela individual.

## Problemas

### 1. [quebrado] O tour de onboarding reaparece para sempre

Reproduzido duas vezes: concluir o tour pelo botão final ("Start setting up") e
dispensá-lo por "Skip" — em ambos os casos, a próxima visita ao Overview reabre
o modal em "1 of 5". A configuração `surfaces.console.tutorial_dismissed`
existe no schema precisamente para registrar a dispensa do lado do deployment e
não está sendo escrita (ou lida).

**Correção:** qualquer saída do tour (Skip, X, concluir) grava
`tutorial_dismissed` e o modal nunca mais abre sozinho. Reabrir vira uma ação
explícita (entrada "Ver o tour" no menu do usuário ou na palette).

### 2. [quebrado] O CTA final do tour não leva a lugar nenhum

O passo 5 ("Try it before it counts") termina em um botão **"Start setting
up"** que apenas fecha o modal e deixa o operador no mesmo dashboard. O botão
promete navegação e não navega. Correção: navegar para `/first-run`.

### 3. [bloqueia entendimento] A busca global não busca o que promete

Placeholder: *"Search resources, runs, incidents"*. Digitar `signoz` — nome de
um recurso presente na tela Resources — devolve **"Nothing matches that"**. O
que a palette (Ctrl+K) realmente contém: navegação entre páginas, runs
recentes e a ação Investigate.

**Correção:** ou a busca busca (recursos por nome, runs por id/assunto,
incidentes por título — a API de resources já responde a lista completa), ou o
placeholder para de prometer. A primeira opção é a certa: numa ferramenta de
operação, "digitar o nome da coisa doente" é o caminho mais curto que existe.

### 4. [bloqueia entendimento] Erro técnico cru como notificação

O sino mostra "Needs you — 1 unread" com o texto integral
`InvestigatorNotConfigured: ... Set NINJASRE_INVESTIGATOR to 'module:factory'`.
É a quarta superfície repetindo o mesmo stack (dashboard, run list, run detail,
sino). Ver spec 010 para a tradução proposta; aqui fica o princípio: **nenhuma
mensagem de exceção do gateway aparece verbatim no shell**. Erros conhecidos
têm tradução ("O investigador ainda não foi configurado — termine o passo X"),
com link para o passo, e o texto cru fica num "ver detalhe técnico".

### 5. [bloqueia entendimento] Modal do tour sem posição estável

O modal muda de largura e posição a cada passo — os botões Back/Next pulam sob
o cursor (verificado: cliques sucessivos na mesma coordenada erram o botão).
Largura fixa, posição fixa, botões no mesmo lugar do primeiro ao último passo.

### 6. [bloqueia entendimento] Não há como trocar de idioma

O console carrega `pt-BR` no bundle, mas o locale só é resolvido do
`Accept-Language`, com match exato de tag — `pt` não ativa `pt-BR`
(`console/src/i18n/messages.ts`). Não existe seletor na UI; o menu do usuário
só tem Account / Act as somebody else / Sign out.

**Correção:** (a) seletor de idioma no menu do usuário, persistido; (b) match
por prefixo de língua: `pt` e `pt-PT` caem em `pt-BR` enquanto for o único
português; (c) auditar cobertura do catálogo pt-BR antes de anunciar.

### 7. [polimento] Pluralização e microtextos

- "**1 items** need you" — plural fixo.
- "**1 events**" no transcript do run.
- Badge de contagem no item Runs do sidebar é o número de runs *failed*, mas
  nada diz isso — parece contagem de runs.

### 8. [polimento] Botões da topbar sem rótulo acessível

O switcher de organização ("NinjaSRE" + ícone) e o avatar não têm `aria-label`
(a árvore de acessibilidade lista `button` sem nome). "Theme" e "Compact rows"
têm rótulo mas são ícones sem tooltip — o de densidade é indecifrável sem
hover.

### 9. [verificar] "Stop automation" sem fricção

Botão vermelho permanente na topbar. Não foi acionado nesta auditoria para não
alterar o estado do deployment; verificar se há confirmação e o que o botão
comunica depois de parado (como se religa, quem parou, desde quando). Se não
houver confirmação, adicionar uma — é a ação de maior consequência visível no
shell. A relação com a tela Autonomy (posture) precisa aparecer no diálogo.

### 10. [polimento] Rodapé "Guardian active · propose-only"

Jargão sem link. Tornar clicável, levando à tela que explica e controla a
postura (Autonomy), com tooltip de uma linha explicando o que "propose-only"
significa.

## Critérios de aceite

- Dispensar o tour uma vez ⇒ nunca mais reabre sozinho, em qualquer navegador.
- "Start setting up" navega para `/first-run`.
- Buscar o nome exato de um recurso existente na palette encontra o recurso.
- Nenhum texto `InvestigatorNotConfigured`/env var aparece no sino.
- Trocar o idioma para pt-BR pela UI e recarregar mantém pt-BR.
