# Tarefas — 052 Primeira execução no console

Depende de 051 sendo merged: cada passo do wizard posta para uma rota que 051 construiu
(`/v1/providers*`, `PUT /v1/integrations/{name}/credential`, estendida
`/v1/setup/checklist`). Não comece a Phase 2 antes dessas rotas responderem.

## Phase 1 — navegação e shell

- **T-001** Testes falhando: `NAV_GROUPS` reagrupado para as três zonas D2 com
  cada área existente atribuída; suites sidebar/palette/deep-link verdes
  contra o novo agrupamento. Implemente em `console/src/shell/routes.ts` +
  catálogos i18n.
- **T-002** Teste falhando: uma área com um hook `visible` está ausente de
  `visibleAreas` quando o hook diz assim, presente caso contrário. Implemente o
  hook; adicione a área `first-run` gatilhada em incompletude de checklist (leitura de
  checklist fornecida pelo layout do shell, através de `panelRead` então uma
  falha de checklist degrada para "mostrada").

## Phase 2 — o wizard

- **T-003** Teste de componente falhando: a tela do wizard deriva seu passo
  atual do `next` da checklist e renderiza a lista de passos com
  passos completados reabrindo. Implemente o esqueleto da tela em `/first-run`.
- **T-004** Passo de provider: teste primeiro — nove providers renderizados com
  nome de exibição, marcador local/hospedado, texto de guidance, peso igual. Implemente
  contra `GET /v1/providers`.
- **T-005** Passo de credencial: testes primeiro — campos gerados das
  specs do provider (`label`, `help`, `secret`→`type="password"` +
  `autocomplete="off"`, `required`), `where_to_get_it` ao lado do campo,
  valor nunca renderizado de volta após submissão (afirme que o DOM não possui valor,
  mascarado ou caso contrário). Reconecte `CredentialField` para
  `PUT /v1/integrations/{name}/credential` com submissão fetch; lado
  do gateway: aceitação de session-cookie + escopo CORS para as rotas de
  credencial e verify (teste em `tests/security/`).
- **T-006** Passo de model: teste primeiro — modelos conhecidos oferecidos, campo livre com
  padrão caso contrário; salvar passa por preview-then-write na rota de
  config (o padrão proxy `/api/preview` existente).
- **T-007** Passo de integrations: teste primeiro — catálogo pesquisável, formulário
  dirigido por schema por-integração, uma falha não abandona o resto,
  falhas reportadas ao final.
- **T-008** Passo de verify: teste primeiro — uma linha de resultado por coisa
  configurada, cada retentável; uma falha causada por campo pulado nomeia o campo.
- **T-009** Passos 6–7 (estate, alert ingress): links dirigidos pelos
  passos de checklist, cada um nomeando o que estabelece e qual tela o fornece.

## Phase 3 — dashboard e tutorial

- **T-010** Painel de checklist no dashboard: teste primeiro — renderiza passos,
  passo pendente liga no wizard, painel ausente quando completo. Implemente.
- **T-011** Aviso de nenhum-provider + painel de ações-rápidas: testes primeiro (aviso
  presente exatamente quando a checklist diz nenhum provider; três links).
- **T-012** Gatilho de investigação na topbar em cada tela, com a
  linha de advertência de integração na gaveta. Teste: gatilho acessível de duas
  áreas diferentes; advertência presente quando nenhuma integração é configurada.
- **T-013** Overlay de tutorial: testes primeiro — descartável, `Pular` visível,
  indicador de progresso, `prefers-reduced-motion` respeitado, nunca mostrado quando
  a checklist está completa, descarte armazenado lado deployment e honrado
  de um contexto de navegador fresco.

## Phase 4 — as provas que a spec nomeia

- **T-014** e2e: fluxo completo do navegador em um deployment vazio — dashboard com
  figuras zeradas, tutorial, wizard através de provider→credential→model→
  integration→verify, terminando com checklist mostrando provider verificado. Sem
  redirecionamento para fora do shell em ponto algum.
- **T-015** varredura de segredo e2e: o fluxo de T-014 com um segredo sentinela;
  scan cada corpo de resposta, página renderizada, payload RSC e linha de
  log do processo do console capturada pela sentinela; falhe em qualquer hit.
- **T-016** retomabilidade e2e: mate o contexto do navegador no meio do fluxo (após o
  passo de credencial), reabra, afirme que o wizard retoma no passo de model.
- **T-017** Acordo entre superfícies: teste de integração dirigindo `ninjasre
  onboard` (via `RemoteClient`) contra o mesmo deployment in-process que
  os testes do console usam, afirmando que ambos produzem o mesmo documento de checklist.
- **T-018** Auditoria de estado-vazio: para cada tela acessível antes de um estate
  existir, um teste afirmando seu estado vazio nomeia o que está faltando e liga
  o passo de estabelecimento (estende as props `empty` de Panel onde elas ficam
  aquém da regra what/why/where de D2).
- **T-019** Baselines visuais re-capturadas (`make console-visual-accept`);
  `make verify` verde.

## Definição de pronto

1. Um deployment fresco mostra o dashboard (figuras zeradas), o tutorial
   descartável, e a checklist com o passo pendente clicável — sem redirecionamento
   (T-014, e uma vez à mão contra o container de validação).
2. O fluxo completo termina no navegador sem envolvimento de CLI, terminando
   com um provider verificado e ao menos uma integração verificada (T-014).
3. A varredura de segredo sentinela passa (T-015).
4. Navegador morto no meio do fluxo retoma no passo certo (T-016).
5. `ninjasre onboard` e o console concordam no estado de checklist (T-017).
6. Cada tela pré-estate nomeia o que está faltando e qual passo o fornece
   (T-018).

## Dependências em outras features specs_v3

- **051** (dura): rotas de providers, escrita de credencial, extensão de checklist.
- **050** (ordenação): o walk do shell no canary smoke exercitará
  `/first-run` uma vez que esteja em `AREAS` — cobertura grátis, nenhum trabalho aqui.
- **053/055** (para frente): passos 6–7 ligam para superfícies que essas features entregam;
  até que aterrem os links apontam para o texto `action` da checklist, que é
  honesto ("o que está faltando, por quê, onde").
