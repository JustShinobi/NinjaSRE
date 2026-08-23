# Tarefas — 056 A história escrita

Nenhuma dependência dura dentro da wave (a tabela da spec diz "—"); o
link de estate (Phase 3) precisa que os atributos enriquecidos de 053 sejam *úteis*
mas é construído e testado contra fixtures. Ordenado, um commit cada um, teste-primeiro.

## Phase 1 — a fonte do corpus

- **T-001** Corpus de fixture sob `fixtures/`: uma árvore moldada como o
  repositório real (runbooks, as duas postmortems do AdGuard com sua
  estrutura de heading, um ADR, YAML de política de firewall, mais decoys —
  `.env.local`, estado tofu, lockfiles) com conteúdo anonimizado.
- **T-002** Testes falhando: a fonte do corpus enumera exatamente Markdown
  sob `docs/` e YAML sob `policies/`; cada decoy é intocado;
  limites (máximo de arquivos, máximo de bytes) são constantes nomeadas e excedê-los
  recusa nomeando o limite. Implemente
  enumeração de `platform/knowledge/base/sync/corpus.py`.
- **T-003** Testes falhando: classificação deriva do caminho
  (runbook/postmortem/decision/policy/general); `DocumentType` ganha os
  membros faltantes com o teste de enum fechado atualizado e sua docstring
  dizendo por quê. Implemente.
- **T-004** Testes falhando: sync ingere através de `KnowledgeIngestor.ingest`;
  re-sync sem mudança é `UNCHANGED` por documento; um corpo editado
  supersede para version+1; um `touch` não muda nada (checksum). Implemente
  o loop de sync.
- **T-005** Teste falhando (aceitação 5): um arquivo de fixture carregando um
  credencial de formato conhecido é recusado; o resultado nomeia o arquivo e regras;
  o valor não aparece em nenhum log, resultado, ou linha armazenada.

## Phase 2 — extração de postmortem

- **T-006** Testes falhando para extração estrutural: as postmortems de
  fixture produzem sintoma, causa raiz, correção, e recorrência-de; a
  recorrência-de da fixture July-20 nomeia a de July-17; ambas as direções
  armazenadas em metadados. Implemente.
- **T-007** Testes falhando para o fallback de modelo: uma fixture sem heading
  passa por `get_llm(extraction-role)` com um modelo encenado; resultado
  cachado por checksum (segundo sync faz zero chamadas de modelo); sem
  provider configurado ⇒ somente estrutural com a degradação nomeada no
  relatório de sync. Implemente.
- **T-008** Teste de busca falhando (aceitação 2): querying o sintoma do
  AdGuard retorna ambas as postmortems e o runbook de recuperação, com a
  entrada carregando causa-raiz distinguível na forma de resultado. Implemente
  o ranking/anotação no caminho de busca.
- **T-009** Ablação de extração sobre a fixture de avaliação de dez postmortems;
  reporte o número.

## Phase 3 — knowledge ↔ estate

- **T-010** Testes falhando: ingestão de um documento mencionando um hostname/
  domain que combina com um atributo de recurso escreve um edge de topologia
  document→resource; sem match escreve nada; re-sync é idempotente em edges.
  Implemente.
- **T-011** Teste de contrato falhando: o detalhe do recurso lista documentos que
  o mencionam; o painel do console os renderiza (teste de componente). Implemente.

## Phase 4 — candidate detectors

- **T-012** Testes falhando: syncing a fixture double-check-queries cria
  linhas de detector desativadas, cada uma com `origin` citando o documento e o
  excerpt da fonte; eles renderizam como candidatos na tela de detectors;
  `dry-run` funciona em um; nada dispara enquanto desativado. Implemente.

## Phase 5 — o corpus real

- **T-013** `make verify` + `make test-postgres` verde (mudanças de metadados
  da knowledge store tocam a suite de contrato). Contra o cluster: sync
  `/root/infra-cluster` `docs/` + `policies/`; registre em deviations as
  contagens (54 runbooks, 10 postmortems, 3 ADRs), qualquer arquivo rejeitado, e o
  transcript de busca do AdGuard.

## Definição de pronto

1. O corpus de fixture ingere com classificação derivada de caminho, e as
   contagens do corpus real combinam com as do repositório, registradas em deviations
   (T-002/T-003/T-013).
2. "AdGuard DNS" retorna ambas as postmortems e o runbook com a
   entrada explicadora marcada (T-008, e o transcript ao vivo).
3. Re-sync sem mudança não cria versão; uma edição cria uma (T-004).
4. Um recurso resolve para os documentos mencionando-o por hostname/domain
   (T-010/T-011).
5. A fixture de credencial é recusada nomeando o arquivo, valor em lugar nenhum
   (T-005).
6. As queries de verificação existem como candidate detectors desativados com
   excerpts da fonte (T-012).

## Dependências em outras features specs_v3

- **053** (mole): atributos de hostname/domain de recurso tornam Phase 3
  combinar recursos reais; fixtures carregam a mesma forma de atributo de qualquer forma.
- **Alimenta 055**: a quarta fonte de evidência para a primeira investigação.
- **Alimenta 061**: a forma de detector disabled-with-origin e o caminho de
  proposta de documento são o que a fila de proposta reutiliza.
