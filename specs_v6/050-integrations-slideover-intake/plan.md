# Implementation Plan: Integrações em slide-over e Alert intake enxuto

**Branch**: `feat/v6-050-integrations-slideover-intake` | **Date**: 2026-08-16 |
**Spec**: [spec.md](spec.md)

**Input**: Feature specification from
`specs_v6/050-integrations-slideover-intake/spec.md`

**Referência visual (DoD)**: `specs_v6/mockups/settings-v6.html#m4` (catálogo em
três seções e slide-over) e `#m3` (intake de três fontes, YAML do receiver,
cadeia de quatro nós).

## Summary

Duas telas ficam do tamanho do que o corte da 001 deixou. `/integrations` perde
a paginação e ganha a terceira seção nomeada; o detalhe deixa de ser um bloco no
rodapé do documento e passa a ser um painel sobreposto, com o deep-link
preservado e a rolagem intacta nos dois sentidos. `/settings/alert-intake` cai
de sete cartões idênticos para três fontes com estado real, ganha a URL e o YAML
do receiver prontos para colar, troca "Trusted by webhook.deliver" por um
delivery token nomeado com rotação, e desenha a cadeia intake → regra → ação →
destino com cada nó linkando a tela dona.

O trabalho concentra-se no console. O gateway ganha três acréscimos pequenos e
bem delimitados: o endereço descoberto pelo estate exposto para uso como
placeholder, a distinção explícita entre credencial guardada e credencial
verificada, e o bloco de receiver do Alertmanager gerado a partir da
configuração do deployment em vez de montado na tela.

## Technical Context

**Language/Version**: TypeScript (console, Next.js App Router com Server
Components); Python 3.12 (gateway)

**Primary Dependencies**:

- `console/src/surfaces/screens/integrations.tsx` — a tela do catálogo, que hoje
  renderiza `IntegrationPanel` depois de `AdvancedConfigSection`, no fim do
  documento.
- `console/src/surfaces/integration-panel.tsx` — o painel de credencial, que já
  usa `Drawer` e já restaura rolagem ao desmontar.
- `console/src/components/overlay.tsx` — **a causa do defeito**: `Drawer` chama
  `Overlay` com `modal={false}` e sem classe de posição, e `Overlay` devolve um
  `<div role="dialog">` comum. Sem posicionamento nem portal, o "slide-over" é
  um bloco no fluxo do documento, na posição em que a tela o renderiza — o
  rodapé. É aqui que o conserto mora, não na tela.
- `console/src/surfaces/integration-catalogue.tsx` — o grid, que recebe
  `pageSize={INTEGRATIONS_CATALOGUE_PAGE_SIZE}` (24, espelhando a constante
  Python de superfícies). Com 85 itens isso dá as quatro páginas observadas;
  com 15, dá uma página e um controle inútil.
- `console/src/surfaces/settings/alert-intake.tsx` — a tela de intake, que já lê
  ingress, regras, entregas e receivers, e que exibe `verification` cru sob o
  rótulo "Trusted by".
- `console/src/surfaces/ingress.tsx` — o componente de emissão de delivery
  token.
- `console/src/surfaces/settings/schedules-destinations.tsx` — as duas seções
  avançadas de nomes sobrepostos.
- `gateway/http/routes/integrations.py`, `gateway/http/routes/ingress.py`,
  `gateway/http/routes/transit.py` — as rotas que servem os acréscimos.

**Storage**: N/A — nenhuma tabela nova. Credenciais seguem no vault pelo fluxo
existente, write-only.

**Testing**: Playwright behaviour (acceptance da feature + suíte transversal),
Playwright visual (as duas rotas), vitest para as unidades do console, pytest
contract para o payload estendido e para o gerador do receiver.

**Target Platform**: Console web (viewport global do Playwright 1440×900; as
medições de orçamento de rolagem declaram 1080p no próprio teste)

**Project Type**: Web, com extensão de payload no gateway

**Performance Goals**: as duas telas em ≤2 viewports a 1080p; busca filtra no
cliente sem requisição por tecla, com os dados que a página já carregou

**Constraints**: nenhum segredo guardado é reexibido — nem em campo, nem em
atributo do DOM, nem no bloco YAML copiado; nenhum segredo na URL do deep-link;
strings de produto só via i18n, en e pt-BR juntos; `console/src/i18n/*.ts`,
`console/src/shell/routes.ts` e `console/visual/screens.json` são de escrita
única na onda e a execução é sequencial

**Scale/Scope**: catálogo de 15 integrações; três fontes de intake; quatro nós
de cadeia; duas rotas com baseline visual

## Constitution Check

*GATE: verificado antes do desenho e novamente depois dele.*

- **Art. I — Evidência sobre asserção**: cada afirmação das duas telas nasce de
  um dado servido. "Receiving", a última entrega e o volume da semana vêm do
  ledger de entregas; um nó da cadeia sem valor configurado diz que não há em
  vez de exibir um exemplo plausível (FR-070, FR-072); a contagem do topo é
  derivada do payload e nunca literal (FR-005). O placeholder de endereço vem da
  descoberta do estate, e a sua ausência é uma ausência visível (FR-029, edge
  case do estate que não conhece o endereço).
- **Art. II — Autonomia limitada**: nada nesta feature roda o agente. A única
  constante de limite envolvida é a de tamanho de página do catálogo, e ela sai
  junto com o seu único consumidor, em vez de virar um número órfão — o que o
  próprio artigo pede ao proibir limites que não moram em módulo dono.
- **Art. III — Somente leitura por padrão**: "Disconnect" e "rotate" são
  escritas de configuração feitas por um humano na sua própria superfície, não
  ações do agente. A confirmação nomeia o alvo e o que será removido (FR-040),
  usando a confirmação destrutiva que a biblioteca já impõe. Nenhuma ação nova
  atinge produção.
- **Art. IV — Segredos nunca alcançam o agente**: o formulário continua
  write-only e nenhum valor guardado é reexibido (FR-032). O bloco YAML é o
  ponto sensível desta feature e foi desenhado contra o artigo: ele carrega o
  nome do delivery token e um marcador explícito no lugar do valor, e só carrega
  um segredo real no caso em que esse segredo acabou de ser emitido e já está na
  tela do operador (FR-058). Nenhum segredo viaja na URL do deep-link (FR-033).
- **Art. V — Um runtime canônico**: não tocado. Nenhuma mudança de runtime,
  nenhum adapter.
- **Art. VI — Neutralidade de provider**: não tocado. Nenhum SDK de vendor,
  nenhuma capacidade condicionada a provider.
- **Art. VII — Aprendizado é medido**: não tocado. Nenhum mecanismo de memória.
- **Art. VIII — Arquitetura em camadas**: o console é fora da árvore de tiers
  Python e `check-console-boundary` continua valendo nos dois sentidos. O
  gerador do bloco de receiver mora no módulo que possui a entrega de ingress e
  é servido pelo gateway (Tier 1), nunca montado por concatenação na tela
  (FR-057) — que é a forma que este artigo chama de "comportamento no arquivo
  compartilhado mais próximo". A remoção da paginação apaga a constante junto
  com o seu consumidor, como a cláusula 4 exige.
- **Art. IX — Capacidades são declaradas**: nenhuma capability nova. A paridade
  das 15 integrações é entregue pela 001; esta feature não pode reduzi-la, e
  `check-integrations` e `check-integration-docs` continuam no conjunto de gates
  rodados.
- **Art. X — O operador é dono dos dados**: nada sai do host. "Copy URL" e
  "Copy … YAML" escrevem na área de transferência local; nenhuma telemetria,
  nenhum fetch para fora.
- **Art. XI — Datastore único**: nenhuma SQL, nenhuma Cypher, nenhum acesso
  fora dos ports. Todas as leituras são das rotas HTTP existentes.
- **Art. XII — Test-first, lastreado em traço**: a fase de testes do console
  abre com o acceptance spec da feature codificando as alegações de M4 e M3,
  confirmado vermelho antes de qualquer tela mudar. Os acréscimos de payload
  ganham teste de contrato antes da implementação. O efeito no corpus sintético
  é medido e reportado — a expectativa é "nenhum", porque nada aqui toca
  investigação, mas "não medido" não é resultado aceitável. As asserções sobre
  posição de rolagem medem comportamento, não texto de código.
- **Art. XIII — Idioma e atribuição**: todo texto de produto em inglês, via
  i18n, com pt-BR ao lado (FR-077). Nenhum identificador de requisito, número de
  artigo, número de feature ou caminho de planejamento entra em arquivo
  committed — o que a tela ou o teste precisar saber é dito por extenso lá.

Nenhuma violação. A seção Complexity Tracking fica vazia.

## Project Structure

### Documentation (this feature)

```text
specs_v6/050-integrations-slideover-intake/
├── spec.md
├── plan.md                    # este arquivo
├── tasks.md
├── controle.md                # escrito pelo implementador, não na geração
└── checklists/requirements.md
```

### Source Code (repository root)

```text
console/src/components/overlay.tsx                        # Drawer ganha posição de slide-over
console/src/surfaces/integration-panel.tsx                # estado guardado + três ações
console/src/surfaces/integration-catalogue.tsx            # fim da paginação, seção Available
console/src/surfaces/screens/integrations.tsx             # três seções, contagem, rodapé do roadmap
console/src/surfaces/settings/alert-intake.tsx            # três fontes, YAML, trust, cadeia
console/src/surfaces/ingress.tsx                          # linha de confiança e rotação
console/src/surfaces/settings/schedules-destinations.tsx  # nomes disjuntos das seções avançadas
console/src/i18n/en.ts                                    # escrita única na onda
console/src/i18n/pt-BR.ts                                 # escrita única na onda
console/visual/screens.json                               # escrita única na onda
console/tests/e2e/050-integrations-slideover-intake.acceptance.spec.ts
console/tests/unit/surfaces/...                           # unidades das duas telas
gateway/http/routes/integrations.py                       # endereço do estate, estado guardado
gateway/http/routes/ingress.py                            # bloco de receiver do Alertmanager
tests/contract/console/                                   # o console como cliente da API
```

**Structure Decision**: a feature vive no console, com três acréscimos de
payload no gateway. Nenhum diretório novo; nenhuma dependência nova.

## Decisões de design

1. **O slide-over não é um componente novo — é o `Overlay` ganhando posição.**
   `IntegrationPanel` já usa `Drawer`, já trava foco, já responde a Escape e já
   restaura a rolagem capturada ao desmontar. O que falta é geometria:
   `Overlay` renderiza um `<div>` no fluxo, então o painel aparece onde a tela o
   escreve, que é depois da seção avançada, no fim de um documento de 2.141px.
   O conserto é dar ao `Drawer` a sua sobreposição — ancorada à direita, acima
   do conteúdo, sem empurrar o catálogo — no componente compartilhado. Corrigir
   isso na tela seria escrever geometria de overlay dentro de uma superfície, e
   deixaria o próximo drawer com o mesmo defeito.

   **Raio de alcance a verificar antes de mexer**: `Drawer` tem quatro
   consumidores — `console/src/surfaces/integration-panel.tsx`,
   `console/src/shell/shell.tsx`, `console/src/live/investigate.tsx` e
   `console/src/gallery/registry.tsx`. Dar geometria ao componente muda os
   quatro. Os três que não são desta feature precisam ser vistos abertos antes e
   depois; se algum deles depender de o drawer ocupar espaço no fluxo, a
   sobreposição passa a ser opção do componente em vez de comportamento único, e
   o painel de integração é quem a pede. A decisão entre as duas formas é
   tomada com os três na tela, não antes.

2. **A rolagem passa a ser propriedade testada, não efeito colateral.** A
   captura e a restauração já existem; o que nunca existiu foi um teste que
   medisse a posição antes, durante e depois. O acceptance spec mede as três, e
   mede também onde o deep-link aterrissa, porque é exatamente a diferença entre
   "o painel abre" e "o painel abre sem me levar para o fim da página".

3. **Fim da paginação, não um número maior.** Subir o tamanho de página
   esconderia o problema até o catálogo crescer de novo. A seção Available passa
   a listar o que resta, a constante sai com o seu consumidor, e o teste de
   altura passa a ser a régua — o mesmo raciocínio que fez o catálogo caber
   quando eram 85, aplicado agora ao tamanho real.

4. **Guardada e verificada são estados diferentes, e a tela passa a saber
   disso.** O payload já distingue não configurada, guardada sem verificação e
   degradada; a tela hoje só ramifica em "tem credencial ou não". As três ações
   do painel de uma integração conectada saem dessa distinção, e é ela que
   remove o campo vazio com botão morto.

5. **O YAML é gerado por quem possui a entrega.** A URL do deployment e o nome
   do token vivem na configuração; montar o bloco na tela criaria uma segunda
   verdade que envelhece sozinha na primeira mudança de endereço. O gateway
   devolve o bloco pronto e a tela copia o que recebeu.

6. **O segredo do YAML.** Um delivery token guardado nunca é reexibido, então o
   bloco traz o header com o nome do token e um marcador no lugar do valor. A
   exceção é o gesto de emissão: ali o valor está na tela porque acabou de
   nascer, e copiar o YAML completo naquele momento é o caminho que faz o
   copy-paste funcionar de primeira. Fora dele, um YAML que carregasse o segredo
   seria uma reexibição.

7. **A cadeia lê das telas donas, sem endpoint novo.** Os quatro nós saem das
   mesmas leituras que intake, regras e destinos já fazem. Um nó vazio é uma
   informação — "não há regra" — e por isso a faixa nunca encolhe para menos de
   quatro nós.

8. **Os nomes sobrepostos são resolvidos por vocabulário, não por layout.** As
   duas seções avançadas de schedules-destinations dizem hoje "delivery
   destinations" e "report destinations" sob o mesmo prefixo "Advanced:". Enquanto
   as duas contiverem o mesmo substantivo, nenhum nó da cadeia consegue prometer
   um destino e aterrissar no lugar certo. Renomear para termos disjuntos, ou
   fundir numa seção só, é pré-requisito da cadeia — não um polimento.

## Complexity Tracking

> Preenchido apenas quando o Constitution Check tem violações a justificar.

Nenhuma violação a registrar.
