# Parte invariante do briefing — vale para toda feature da onda specs_v5

Registrado para confronto. Cada briefing por feature (`001.md`, `010.md`, …)
carrega isto mais o que é próprio da feature.

## Como a árvore é medida

O baseline da onda está em `specs_v5/CONFRONTO.md` §0. Ele diz, com número, o
que estava verde e o que estava vermelho **antes de qualquer subagent**:

- 7 contratos de import mantidos, 0 quebrados, sobre 1672 arquivos
- 85 integrações em paridade total, toda permissão sondada
- console: prettier, eslint, `tsc --noEmit`, **1945 testes vitest em 125
  arquivos**, cobertura 95.34/90.91/93.05/97.57 (piso 90), build, client-check,
  budget, e2e `behaviour` + `first-day` + `visual`
- pytest: **14031+ passed, 0 failed, 25 skipped** (três falhas anteriores foram
  corrigidas antes da onda — §0.2 do dossiê diz quais e por quê)

**Qualquer vermelho que aparecer depois é seu até você provar o contrário com o
texto do erro.** "Já estava quebrado" é uma alegação verificável, e eu verifico.

## Nunca

- **Nunca** `git add`, `git commit`, `git stash`, `git checkout` de arquivo.
  Sua entrega é a árvore de trabalho suja. O orquestrador commita.
- Nunca rode `make console-visual-accept`, `console-e2e`, nem nada que
  reescreva baseline commitado — **a menos que uma task da sua própria
  `tasks.md` peça**. Se pedir, capture deliberadamente e diga no relatório
  quais baselines você gravou, pelo nome.
- Se você adicionar tela a `console/visual/screens.json` sem uma task que peça
  captura: **não deixe o gate fabricar o baseline**. `python -m tools.console_gate e2e`
  escreve um PNG placeholder para toda tela declarada sem baseline, e o teste de
  cobertura só confere que o arquivo existe. Onze PNGs byte-idênticos já
  passaram por captura assim. Apague o que o gate escreveu e reporte o baseline
  como ausente, pelo nome.
- Nunca cite identificador de requisito (`FR-001`), critério (`SC-002`), artigo
  da constituição, número de feature, ou caminho de `specs_v5/` em arquivo
  commitado — código, teste, comentário, `AGENTS.md`. Todo diretório de onda é
  gitignored: quem clonar o repositório não tem esses documentos. Diga a
  substância.
- Nunca nomeie projeto upstream ou prior art em lugar nenhum do repositório.
- Nunca adicione `Co-Authored-By:` nem rodapé de "generated with".
- Nunca toque no diretório de spec de outra feature.
- Nunca toque em `tests/unit/tools/test_console_smoke.py` nem em
  `tests/contract/integrations/test_integration_parity.py` — são a correção de
  baseline do orquestrador, não sua.

## Sempre

- **Test-first com o vermelho visto.** O teste que falha entra antes da
  implementação e você **roda e vê** o vermelho. Inferir que "teria falhado"
  não é confirmação e não pode ser relatado como uma. Se em algum item você não
  conseguiu ver o vermelho antes, diga isso nessas palavras, item por item.
- **Todo texto novo entra em `console/src/i18n/en.ts` e em `pt-BR.ts`.** Fonte,
  comentários, identificadores e copy em inglês; o catálogo pt-BR é
  **brasileiro**: tela, arquivo, ação, salvar, excluir, ativar, contatar,
  objetivo. Nunca ecrã, ficheiro, acção, gravar, apagar, activar, contactar.
- **Nenhum literal de cor.** Cor por papel: `text-text`, `text-muted`,
  `bg-surface`, `bg-sunken`, `border-border`, `text-accent`. O accent significa
  interação; `success`/`warning`/`danger`/`info`/`neutral` significam estado, e
  cor nunca é o único portador.
- **Estado de tela mora na URL.** Nada de estado no cliente para painel de
  detalhe, filtro ou ordenação.
- **Dependência ausente quebra o painel, nunca a rota.** `panelRead` mais
  `state`/`dependency`/`empty` do `Panel`.
- **Ausente, não desabilitado.** Painel que o viewer não pode ver não está no
  documento. Controle desabilitado que fica tem de dizer por quê.
- **Segredo é write-only.** Campo de credencial posta uma vez e nunca é
  renderizado de volta, nem mascarado.
- **Toda constante mora em `config/constants/`**, no módulo do domínio que a
  possui. Todo limite, page size, timeout ou orçamento que o console manda é
  **lido** da constante do backend que o impõe — nunca escolhido. Já houve tela
  mandando `limit=500` contra um `MAX_QUERY_PAGE_SIZE` de 200 que *levanta* em
  vez de encurtar a página, e o plano de fixtures não tinha teto, então nada
  ficou vermelho.
- **Todo valor de enum, string de status e nome de papel que o console
  renderiza é conferido contra o port ou enum que o declara** em `platform/` ou
  `core/` — nunca contra `fixtures/` nem `tools/mockplane/`. Quando discordarem,
  a declaração vence: conserte o mock no único lugar onde é declarado e
  reconstrua os cenários. Já houve fixture com `actor_kind` `"person"`/`"machine"`
  contra um enum real `user|token|agent|system`, e `outcome` `"succeeded"`,
  palavra que `AuditOutcome` nunca teve. Suíte verde, produto errado.
- **`exactOptionalPropertyTypes` está ligado**: propriedade opcional que pode
  faltar é `foo?: string | undefined`.
- **`console/src/shell/routes.ts` é a única lista do que existe como rota**, e
  cada entrada carrega a permissão que o *gateway* exige, copiada por nome;
  `tests/contract/console/test_console_shell.py` segura uma contra a outra.
  Mudou uma, muda a outra.
- **A tabela de tiers do `AGENTS.md` raiz é imposta, não sugerida.** Nenhum SDK
  de LLM fora de `core/llm/`, nenhum SQL fora de `platform/persistence/`,
  nenhuma credencial fora de `platform/credentials/proxy/`, nenhum import
  Python de `console`.

## Como ler a especificação

- **Vírgula em requisito é fronteira de requisito.** Enumere cada oração de
  cada FR e de cada cenário de aceitação como uma linha própria do ledger antes
  de escrever código. Já houve spec pedindo "credencial, teste, e filtro": as
  telas foram feitas, o filtro — último substantivo da frase — não foi feito
  por ninguém, e o controle dizia feito.
- **O verbo e o tempo do cenário são o requisito.** "Preview" não é "confirm",
  "antes" não é "depois", "filtrado por categoria" não é "o catálogo". Já
  entregaram a confirmação do que acabara de ser criado no lugar da prévia do
  que *seria* — mesma tela, mesmos dados, pergunta diferente, e passou por
  pronto para todo mundo que não releu o critério.
- **Ache o que já existe antes de construir.** Rode os testes dos arquivos que
  você vai mudar *antes* de mudá-los. Linha do ledger já satisfeita é
  **verificada**, não reconstruída, e o relatório diz "já valia, verificado em
  `file:line`" — nunca a apresenta como conserto.
- **Persiga a causa raiz entre tiers.** Defeito visível numa tela é
  rotineiramente produzido em `gateway/`, em `platform/`, ou no plano de mock.
  Conserte onde está errado, não onde aparece.

## O relatório final

Para **cada** linha do ledger — todo FR, todo cenário de aceitação, todo edge
case, todo SC, toda task numerada:

1. estado final e o `file:line` que prova;
2. todo arquivo criado ou mudado;
3. todo gate rodado e seu resultado **real** — gate não rodado é listado como
   não rodado, com o porquê; gate que falhou é listado como falhou, com o texto
   do erro;
4. toda linha do ledger que você deliberadamente deixou, e qual spec a possui;
5. tudo que a spec, o plano ou o mockup não responderam, e o que você assumiu.

Eu abro cada `file:line` que você citar, rodo de novo cada gate que você disser
ter rodado, e rodo os testes que você disser ter escrito. Onde a árvore
discordar de você, a discordância vai para `specs_v5/CONFRONTO.md` com as duas
versões. **Subestime em vez de superestimar**: uma pendência nomeada custa
muito menos que uma conclusão que não se sustenta.
