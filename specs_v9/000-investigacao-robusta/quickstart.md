# Quickstart de implementação e validação

Este roteiro descreve como implementar a feature em incrementos verificáveis. Ele não substitui
`tasks.md`; serve como critério de integração e demonstração fim a fim.

## 1. Preparar o ambiente

```bash
uv sync --all-extras
cd console && npm ci && cd ..
```

Para os contratos reais de persistência, disponibilize o PostgreSQL de teste do projeto:

```bash
make test-postgres
```

Antes de alterar código, capture a linha de base dos cenários de recorrência e dos indicadores
de staging em um artefato versionado de teste. Dados de produção/staging devem ser agregados e
redigidos; fixtures não carregam payloads, nomes internos nem credenciais.

## 2. Implementar por fatias test-first

### Fatia A — identidade de evidência

1. Adicione primeiro contratos de port para dois runs que usam o mesmo `evidence_id`.
2. Faça fake e PostgreSQL provarem isolamento por `(org_id, run_id, evidence_id)`.
3. Adicione testes de upgrade, integridade e downgrade da migração.
4. Migre resolução, citação, tool calls e episode builder para a chave composta.

Comando rápido esperado:

```bash
make fast SCOPE=platform/persistence
make test-postgres
```

### Fatia B — ocorrência durável e exclusão mútua

1. Escreva testes concorrentes que enviem a mesma entrega e entregas distintas equivalentes.
2. Implemente ocorrência, decisão e `claim_open_incident` nos ports/fakes/PostgreSQL.
3. Adicione `active_run_id` e a reivindicação transacional do run.
4. Faça webhook e entradas equivalentes usarem o serviço de intake canônico.
5. Remova índices em memória do caminho autoritativo somente depois dos contratos verdes.
6. Teste crash/retry e reconciliação de incidentes presos em `investigating`.

Comandos rápidos esperados:

```bash
make fast SCOPE=platform/incidents
make fast SCOPE=gateway/webhooks
make test-postgres
```

### Fatia C — postmortem curado

1. Escreva os contratos do store para estados, revisões, tenant e idempotência.
2. Implemente a montagem determinística de rascunho a partir de incidente/run.
3. Implemente revisão, publicação, supersessão, arquivamento e feedback.
4. Indexe apenas a revisão publicada no namespace `postmortems`.
5. Garanta que secret guard, retenção e exportação cubram conteúdo e embeddings.

Comandos rápidos esperados:

```bash
make fast SCOPE=platform/knowledge
make test-postgres
```

### Fatia D — recorrência e eficiência

1. Adicione cenários sintéticos: recorrência confirmada, candidata contradita, mudança material
   e problema novo semelhante.
2. Implemente classificação determinística anterior ao run.
3. Introduza `recurrence_validation` como modo do pipeline canônico, com limites nomeados.
4. Permita recall semântico apenas depois de evidência atual e registre sua influência.
5. Filtre capabilities indisponíveis e adicione cache negativo por run.
6. Persista resultado diagnóstico e métricas por fase.
7. Adicione as ablações independentes `postmortems` e `recurrence_path`.

Comandos rápidos esperados:

```bash
make fast SCOPE=core/pipeline
make fast SCOPE=platform/memory
make test-sweeps
```

### Fatia E — API e console

1. Incorpore `contracts/postmortems.openapi.yaml` ao OpenAPI canônico.
2. Adicione handlers, permissões e testes de isolamento/idempotência/concorrência.
3. Regenere o cliente TypeScript e atualize mockplane/fixtures.
4. Adicione `Postmortem` às tabs de Knowledge, com filtros na URL.
5. Adicione ações nos detalhes de incidente e investigação, editor/revisão/publicação e
   visualização das correlações/feedbacks.
6. Passe toda escrita pelas courier routes e cubra estados vazio, carregando, erro, conflito de
   revisão e permissão negada.

Comandos rápidos esperados:

```bash
make fast SCOPE=gateway
cd console && npm test && npm run build
```

Use os nomes exatos dos scripts existentes no `package.json` durante a implementação; se os
aliases acima divergirem, o contrato é passar os checks já definidos pelo pacote, sem criar um
segundo sistema de testes.

## 3. Cenário de aceitação fim a fim

1. Dispare um alerta novo com `delivery_id=A`.
2. Confirme uma ocorrência, um incidente e exatamente um run ativo.
3. Reenvie `delivery_id=A`; confirme que a resposta é idempotente e não cria ocorrência/run.
4. Envie a mesma condição com `delivery_id=B`; confirme nova ocorrência ligada ao incidente e
   ao run ativo, sem segunda investigação.
5. Encerre a investigação com evidência citada e crie um rascunho pelo detalhe do incidente.
6. Revise os critérios de recorrência e publique o postmortem.
7. Envie nova ocorrência equivalente depois do encerramento.
8. Confirme que o run inicia em `recurrence_validation`, coleta evidência atual, consulta o
   postmortem depois do anchor e termina como `known_recurrence_confirmed`.
9. Envie outra ocorrência parecida, mas com um fato material contraditório.
10. Confirme escalada no mesmo run para `full_investigation` e ausência de confirmação falsa.
11. Marque uma associação como incorreta e confirme auditoria/visibilidade para revisão.
12. Superseda o postmortem e confirme que novas ocorrências usam somente o sucessor.

## 4. Verificações quantitativas

Execute o corpus com quatro células, mantendo cenários e provider fixos:

| Postmortems | Caminho de recorrência | Objetivo |
|---|---|---|
| desligado | desligado | baseline sem aprendizagem nova |
| ligado | desligado | isolar qualidade do recall |
| desligado | ligado | controle negativo; não deve confirmar sem conhecimento |
| ligado | ligado | medir feature completa |

O relatório deve incluir:

- precisão da classificação, `recall@3`, taxa de falsa confirmação e empates da recorrência;
- taxa de raiz correta e de inconclusão honesta;
- cobertura de evidência e referências resolvíveis;
- runs por ocorrência/incidente e violações de exclusão mútua;
- tokens, chamadas, falhas e duração por fase;
- consultas a postmortem, candidatos, confirmações, rejeições e feedback;
- chamadas bloqueadas por indisponibilidade antes e depois da mudança.

Além das quatro células focadas em postmortem/caminho curto, execute controles independentes dos
eixos existentes de leitura de memória episódica e estratégia. O relatório final deve conseguir
atribuir separadamente o ganho de episódios, estratégias, postmortems e roteamento curto, sem
exigir uma matriz combinatória cega quando uma seleção direcionada cobre a interação.

Os success criteria da spec são gates. Economia de tokens não compensa regressão de qualidade,
citação ou segurança.

Para cada comparação, fixe versão do cenário/corpus, runtime, provider/modelo, configuração de
limites e período. Use pelo menos 200 cenários rotulados antes da execução: no mínimo 100
recorrências com postmortem relevante conhecido e 100 negativos de problema novo, contradição ou
mudança material. A mediana de investigação completa equivalente vem da célula do mesmo cenário
com `postmortems` e `recurrence_path` desligados.

Carregue 10.000 postmortems no mesmo tenant de teste, limite páginas a 50 itens e meça p95 do
endpoint e da ação no console; os gates são 500 ms e um segundo, respectivamente. Conte apenas
respostas bem-sucedidas no objetivo de latência e reporte erros separadamente.

Valide SC-012 em sessão moderada de primeira utilização com pelo menos 10 operadores que tenham
permissão de curadoria e não conheçam o roteiro. Sem ajuda ou documentação, cronometre da ação
“Criar postmortem” até publicação confirmada. Registre de forma anonimizada versão da interface,
tempo, conclusão e ponto de falha; pelo menos 90% devem concluir em menos de cinco minutos.

## 5. Gate final

```bash
make verify
make test-postgres
```

Também execute as suites sintéticas/ablação e os E2E que exigem infraestrutura conforme a
documentação do repositório. Para a interface, valide com Playwright determinístico e faça a
revisão visual no Orca Browser em staging, cobrindo desktop e viewport estreita.

## 6. Evidência esperada para handoff

- resultados dos gates e cenários com comandos reproduzíveis;
- relatório de migração/integridade de evidence refs;
- comparação das quatro células de ablação;
- amostra de trace mostrando anchor antes do recall e influência do postmortem;
- prova concorrente de um único run ativo;
- screenshots ou gravações do fluxo Postmortem em staging;
- plano de rollback da ativação de correlação durável e da migração de chave;
- nenhum segredo, payload bruto de cliente ou identificador sensível nos artefatos.
