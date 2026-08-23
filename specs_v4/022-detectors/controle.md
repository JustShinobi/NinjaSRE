# Controle — 022 Detectors

| Item | Estado |
|---|---|
| 1. Vazio aponta o lugar errado (guardian) | FEITO — já estava correto antes desta auditoria, com teste de regressão próprio (`detectors.test.tsx`) que cita o bug literalmente. Ver `relatorio-confronto.md`, item 1. |
| 2. "Scheduled investigations" cru na tela errada | FEITO — duas passagens. Card, helper de cron com exemplo, explicação de cada campo, empty state na tabela e validação de cron via round-trip já estavam prontos. Na primeira passagem eu tratei uma confirmação pós-criação como suficiente para "mostra o próximo disparo" — o coordenador devolveu o item: a confirmação responde "o que acabei de criar", não "o que isto fará antes de eu criar", que é o que o critério de aceite pede. Segunda passagem: preview de verdade, ponta a ponta, teste vermelho antes em ambas as camadas — rota `POST /v1/schedules/preview` no gateway (reaproveitando `CronExpression`, sem um segundo parser), contrato OpenAPI e client do console regenerados, operação `preview` no courier, e o preview ao vivo no formulário, ao lado do campo, mostrando a recusa quando o cron seria recusado. A confirmação pós-criação da primeira passagem foi mantida — o coordenador chamou-a de "melhoria real" e não é o que estava sendo devolvido. Corrigido também, no mesmo formulário: português europeu em dezoito chaves (duas famílias — "a fazer" em vez de gerúndio, e a consoante muda de antes do acordo ortográfico). Ver `relatorio-confronto.md`, item 2, para as duas passagens completas. |
| 3. Título promete o que não mostra | FEITO — nenhum critério de aceite cobre este item isoladamente; o formato "tabela vazia não responde as três perguntas" já é resolvido pelo mesmo mecanismo de empty state dos itens 1 e 2, em toda a shell. Ver `relatorio-confronto.md`, item 3. |

Onda 3/4 (a fusão em Signals, spec 090, muda o destino da tela inteira —
por isso a correção local não veio antes da decisão estrutural).

**Achado adicional, rastreado e deliberadamente não corrigido nesta
auditoria:** ligar `policies.observation.guardian.enabled` (o CTA que o item 1
já oferece corretamente) não faz `/v1/detectors` mostrar nada — o catálogo
embarcado (`platform/guardian/resolution.py`) e a listagem de detectores
(`platform/observation/detectors/config.py`) são dois pipelines
independentes, e o console TypeScript nunca lê `/v1/config/{node_id}/guardian`
(a única rota que resolve o catálogo embarcado). O empty state já aponta para
o controle certo; o controle, uma vez ligado, não muda o que esta tela
mostra. Unir os dois pipelines é maior que esta spec e nenhum dos três
critérios de aceite pede isso — ver o relatório para a evidência completa
(`platform/incidents/service.py:150-153`, `config.py:70-100`,
`gateway/http/routes/config.py:785-809`, e a divergência do fixture
`fixtures/scenarios/populated/detectors.json` frente ao backend real).

**Segundo achado adicional, também rastreado e não corrigido:** dentro de
`schedules.*`/`detectors.*` em `pt-BR.ts`, "esta equipa" (`schedules.caption`,
`schedules.empty.body`) é a mesma família de erro (grafia europeia de
"equipe") mas aparece de forma consistente também em `nav.teamContext` e
`page.teamContext.title` — uma tela diferente, fora do escopo desta spec.
Corrigir só as duas ocorrências nesta tela quebraria essa consistência em vez
de resolvê-la. Nomeado, não tocado.

**Terceiro achado, sobre o próprio ambiente de verificação, não desta
spec:** `tests/architecture/test_one_fictional_deployment.py` falha porque
`specs_v4/` nunca foi somado à lista de diretórios que ele ignora (só
`specs` e `specs_v2` estão lá) — `specs_v4/021-topology/relatorio-confronto.md`,
um relatório que esta auditoria só leu, já nomeia "Northwind" e já falha
nesse teste sozinho, o que prova que o gate está vermelho desde antes desta
sessão. `specs_v4/` é gitignored, então nenhum dos dois relatórios chega a um
commit real. Não corrigido aqui: é um arquivo fora do alcance da spec 022.
