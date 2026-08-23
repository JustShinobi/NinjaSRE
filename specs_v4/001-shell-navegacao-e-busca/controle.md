# Controle — 001 Shell

| Item | Estado | Detalhe |
|---|---|---|
| 1. Tour reaparece para sempre | **FEITO** (`bf5f055`, corrigido em `d9cdbae`; replay implementado nesta entrega) | Dispensa gravada em `surfaces.console.tutorial_dismissed` e lida antes de montar o overlay. **A correcção original partia o dashboard**: `dashboard.tsx` é server component e chamava um módulo `'use client'`. A leitura mudou para `first-run/tutorial-setting.ts`, sem directiva, que os dois lados importam. O replay explícito está no menu da conta e na palette, e o overlay tem fechamento por X. |
| 2. CTA final não navega | **FEITO** (`bf5f055`) | Último slide faz `close()` + `router.push('/first-run')`. |
| 3. Busca global não busca | **FEITO** (`53b5d8a`; contrato real corrigido nesta entrega) | Três leituras em paralelo atrás de um courier; recursos usam `display_name` e apontam para `/resources?selected=id`; o filtro de permissões fica na shell, ao lado do mesmo filtro por que passam os comandos locais. |
| 4. Erro técnico cru no sino | **FEITO** (`d71c01a`; palette coberta nesta entrega) | `surfaces/failures.ts`, aplicada nas quatro superfícies que repetiam o mesmo stack e também aos hints de runs recentes/encontrados na palette. |
| 5. Modal do tour sem posição estável | **FEITO** (lote 6) | Ver abaixo: a causa não era a descrita. |
| 6. Seletor de idioma / fallback pt→pt-BR | **FEITO** (lote 6) | Ver abaixo. |
| 7. Pluralização | **FEITO** (`bf5f055`; badge semântico corrigido nesta entrega) | `formatCount`, chaves `.one` nos dois catálogos e badge de Runs rotulado como execuções falhadas. |
| 8. Botões da topbar sem rótulo acessível | **FEITO com a premissa corrigida** | Ver abaixo. |
| 9. "Stop automation" sem fricção | **FEITO com a premissa corrigida** | Ver abaixo; o diálogo também referencia explicitamente a postura de Autonomy. |
| 10. Guardian footer sem link | **FEITO** (lote 6) | `GuardianFooter` é um link para `/autonomy`, com tooltip de uma linha sobre o que propose-only significa. |

## Item 5 — a causa não era "muda de largura e posição"

Era uma classe fantasma. O card usava **`w-prose`, que não nomeia utilitário
nenhum que esta folha de estilo declare** — só `max-w-prose` existe, e é
utilitário estático do Tailwind (65ch), não do espaço de nomes `--container-*`.
Sem largura própria, o card encolhia e crescia conforme o slide mais longo.
Corrigido para `w-full max-w-prose`, mais uma região de altura fixa e rolável
para o título+corpo, de modo que Back e Next ficam no mesmo sítio nos cinco
passos.

**Havia uma segunda ocorrência viva**, encontrada a partir deste diagnóstico e
corrigida na integração: `live/investigate.tsx` — o drawer do Investigate também
não tinha largura própria. Verificado independentemente no tema do Tailwind que
`--container-prose` não existe.

É o footgun que o `console/AGENTS.md` já avisa noutra forma: a escala é fechada e
sem base, `p-9` não produz CSS — e `w-prose` também não.

## Item 6 — metade já existia e nunca tinha sido escrita

`resolveLocale` passou a fazer uma passagem ordenada por tag: match exacto
primeiro, depois prefixo de língua, de modo que a preferência mais alta ganha à
mais baixa. O docstring, que argumentava *contra* o prefixo, foi reescrito para
argumentar a favor.

A metade de persistência **já estava construída**: `LOCALE_COOKIE` e
`requestLocale()` liam o cookie do lado do servidor desde antes de haver forma de
o escrever. Faltava o `storeLocale()`, que é a metade que faltava — cookie e não
`localStorage`, porque cada string vem de `message()` chamada em server
components, que não lêem `localStorage`. Selector de dois botões no menu da conta.

**Auditoria do catálogo pt-BR: 0 chaves em falta**, antes e depois.

## Itens 8 e 9 — duas afirmações da spec caíram

**8.** A spec dizia que o switcher de organização e o avatar eram `button` sem
nome acessível. **Nenhum dos dois existe no código:** `deployment-name` é um
`<span>` e o `<summary>` da conta já tem `aria-label`. A auditoria foi feita
contra outro build, ou contra o que se esperava encontrar. O que restava de real
era menor e foi feito: `title` nos ícones de tema e densidade.

**9.** A spec dizia "se não houver confirmação, adicionar uma". **Havia** —
`role="alertdialog"`, nomeia a consequência, exige segundo clique. O que faltava
era a outra metade da frase: quem parou, desde quando, como religa. O gateway já
respondia `scopes` com `engaged_by`/`engaged_at` em
`GET/POST/DELETE /v1/autonomy/kill-switch`, e o `shell/load.ts` **descartava-o**.

Fechado na integração o resto que o agente reportou sem poder tocar: o courier
`app/api/kill-switch/route.ts` também descartava `scopes` no POST/DELETE, portanto
uma paragem feita na própria sessão era atribuída ao viewer que carregou no botão
e corrigida só no reload seguinte. Agora encaminha, e `stop.tsx` lê a resposta do
deployment pela **mesma função** que o frame do servidor usa — `stoppageFrom`,
movida para `shell/stoppage.ts`, sem directiva, pelo motivo do item 1. Um
deployment que não diz quem parou continua a não dizer: `null`, e a shell escreve
"antes de esta página poder dizer quem ou quando", em vez de inventar.

**DoD desta spec:** concluído. O replay "Ver o tour" está disponível no menu
da conta e na palette; as divergências encontradas pela auditoria estão
registradas em `analise-controle.md`.
