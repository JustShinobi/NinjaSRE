# Veredito visual — 050 Painel vivo, slot S3

Feito no Orca Browser contra o staging (`https://stg-ninjasre.lan.kyo.ninja/`),
depois do deploy dos três componentes, do rollout confirmado por listagem de
pods e das nove rotas aquecidas autenticadas. Locale pt-BR, escolhido pelo
cookie `ninjasre_locale` — que é como um leitor troca de idioma, e o que
`requestLocale` prefere sobre o `accept-language`. O `DEFAULT_LOCALE` do
console é `en`, então a primeira renderização em inglês era comportamento
correto e não defeito.

| Tela | Tema | Veredito |
|---|---|---|
| `/` | dark | **CONFORME** |
| `/` | light | **CONFORME** |

Os dois desvios que este gate encontrou foram corrigidos e reconferidos na
tela viva, não no código.

## O que este gate achou, e a suíte verde não

**1. "O que continua acontecendo" onde o board manda "O que insiste em
acontecer".** Os dois artboards dizem a frase; a própria spec a repete sete
vezes, entre elas a AN-11 e a SC-006. Nada em `DIVERGENCIAS.md` registrava a
troca, e desvio sem registro é FAIL de slot pelo §3 do `EXECUCAO.md`.

Passou por baixo da suíte porque **nenhum teste afirmava o nome da seção** —
localizavam o painel por `data-testid`. E, mais fundo: `playwright.config.ts:40`
fixa `locale: 'en-GB'`, então **nenhum teste e2e conseguia ver uma string em
pt-BR**, enquanto o board é inteiramente pt-BR. A superfície de conformidade
com o artboard era invisível ao Playwright por construção. Isso é achado de
onda, não da 050, e está no confronto.

Corrigido em `pt-BR.ts:800`; asserção nova em `painel-vivo.acceptance.spec.ts`
com controle negativo nos dois sentidos.

**2. Identificador cru como texto de linha.** A linha do `InstanceDown` lia
`res-76ab1466…`. O primeiro reparo resolveu o nome do estate e ela passou a
ler `pve01 · res-76ab1466…` — e a AN-12 **ficou verde**, porque seu regex era
ancorado em `^res-` e o `pve01` entrou na frente.

Isso não fechava nada. A **SC-007** proíbe o padrão em *qualquer texto visível*
do Painel, e a **FR-024** diz que o identificador interno aparece *no máximo
como tooltip, nunca como texto da linha*. O teste tinha ficado verde porque o
defeito andou de lado.

Achado lendo a tela depois do deploy, não rodando a suíte. Segundo reparo: com
`isOpaque(subject)` — condicionado assim para não quebrar a 060, que afirma
`toContainText('ct-102')` no mesmo componente compartilhado — a linha passa a
mostrar só o nome, e o id vive apenas no `title`. A asserção foi reescrita para
a redação real da SC-007: sem âncora, sobre o texto visível do Painel.

Reconferido na tela viva: **zero ocorrências** de `res-[0-9a-f]{8}` e zero de
hex ≥16 no snapshot inteiro. A linha lê `InstanceDown · pve01`. As demais
linhas mantiveram suas cadeias de metadados intactas — o conserto não decepou
metadado por atacado.

## O que confere

- Todas as seções que a spec nomeia, com dado real, nos dois temas: banda de
  execução, "Precisa de você", os cinco KPIs com valor, sparkline e legenda de
  decomposição, o agrupamento por assunto e a atividade ao vivo.
- Os seis segmentos de estágio da AN-03 no cartão vivo, com o atual distinto do
  concluído e do futuro — em `dashboard-{dark,light}-live-run.png`.
- O cartão titulado pelo objetivo digitado, palavra por palavra: a alegação da
  020 vista na tela.
- O chip de frescor apanhado nos dois estados entre as capturas.

## Observações que não são defeitos desta feature

- Os chips de assunto dizem "Resolved" num console pt-BR. É deliberado e
  documentado: `status.tsx:192` diz que o `Badge` é "o único chip que carrega
  uma palavra que o deployment escreveu, não uma que este console escolheu".
  Vale decisão do operador só porque a mesma palavra sai "Resolvido" em
  `/incidents`.
- `dashboard.kpi.sparkline.label` é `'Tendência de {count} dias'`, então com
  `count=1` anuncia "Tendência de 1 dias". É nome acessível da sparkline, não
  texto desenhado — não afeta a comparação com o artboard, mas é erro de
  concordância numa chave da própria 050.

## Evidência

| Arquivo | O que mostra |
|---|---|
| `dashboard-dark.png` | `/`, escuro, estado final pós-reparos |
| `dashboard-light.png` | `/`, claro, estado final pós-reparos |
| `dashboard-dark-live-run.png` | `/`, escuro, com o run vivo aos 46s e os seis segmentos |
| `dashboard-light-live-run.png` | `/`, claro, com o run vivo aos 26s |

As duas com cartão vivo trazem o run `0a8e5cb259614ac7baeaaea1bc0566e8`, o
único criado no slot. As duas finais não têm cartão porque ele terminou — e o
§4 do `EXECUCAO.md` dá um run por slot, então não se abre outro para render
uma captura mais bonita.
