# Plano — 056 A história escrita

## O que existe, verificado — três dos seis itens de aceitação são mecanismo

`platform/knowledge/base/` já fornece:

- **Ingestão com screening**:
  `platform/knowledge/base/ingestion.py::KnowledgeIngestor.ingest` tela
  cada documento através do motor de guardrail, recusa em
  material de credencial **nomeando as regras e localizações, nunca a match**
  (`rejection_reason`: "O texto combinado não é reproduzido aqui"), chunks
  (limite `MAX_DOCUMENT_CHUNKS`), incorpora, armazena. Aceitação 5 é este
  comportamento mais um teste com forma de corpus.
- **Idempotência baseada em conteúdo**: `existing.checksum == document.checksum ⇒
  UNCHANGED`; um corpo mudado supersede com `version + 1`
  (`Document.superseded_by` — "uma busca retornando duas versões de um
  procedimento disse ao agent seguir o que leu primeiro").
  Aceitação 3 é este comportamento; um `touch` nunca muda um checksum.
- **Documentos tipados**: `Document.document_type` (`DocumentType` StrEnum,
  RUNBOOK padrão), `tags`, `source_uri`, `Citation` com localização — o
  lado de leitura (`GET /v1/knowledge/documents`, tela `/knowledge`,
  permissão `knowledge.write`) os renderiza hoje.
- **Um framework de sync**: `platform/knowledge/base/sync/port.py` com uma
  fonte de Google Docs ao lado — a forma que uma nova fonte implementa.

O que não existe: uma **fonte de corpus filesystem/repository**, classificação
derivada de caminho, extração de campos de postmortem, o link knowledge↔estate, e
candidatos de detector a partir das queries de double-check.

## Escopo A — a fonte do corpus

Uma nova fonte de sync `platform/knowledge/base/sync/corpus.py`: um diretório (ou
arquivo/URL buscado — mesma decisão de transporte que o enriquecimento de 053:
somente-leitura, path-or-URL, nada executado) cujo conjunto legível é **exatamente**
Markdown sob `docs/` e YAML sob `policies/` — o repositório de 15.880 arquivos
nunca é percorrido além daqueles raízes, forçado pela allowlist da própria fonte e um
teste com uma árvore de fixture contendo `.env.local`, estado tofu e lockfiles
que devem todos ser intocados.

- **Classificação a partir do caminho, sem chamada de modelo**: `docs/runbooks/*` →
  RUNBOOK, `docs/postmortem/*` → POSTMORTEM, `docs/adr/*` → DECISION,
  `policies/**` → POLICY, `docs/**` restante → um tipo geral. Se
  `DocumentType` carece de membros POSTMORTEM/POLICY eles são adicionados (teste de
  enum fechado atualizado com a razão, precedente 043-deviations para editar um
  teste de taxonomia fechada).
- `source_uri` é o caminho relativo ao repositório — a citação que um operador
  pode abrir.
- Sync reutiliza `ingest` por documento, então screening, limites, idempotência e
  versionamento são herdados, não reimplementados.

## Escopo B — o que uma postmortem contribui além de texto

Extração estruturada em ingestão, uma vez, nunca por busca: sintoma,
investigado, causa raiz, correção, recorrência-de. Dois extractors, tentados em
ordem:

1. **Estrutural**: as postmortems do corpus seguem uma convenção de heading;
   extração baseada em seção (maquinário `section_at` existe em ingestão) é
   livre e determinístico.
2. **Fallback assistido por modelo** para documentos que os headings perdem, através
   de `core.llm.get_llm` com o papel `extraction` existente
   (`ModelsConfig` já o declara — nenhum novo papel), limitado e cachado por
   checksum de documento então re-syncs custam nada.

Campos extraídos aterram na bolsa de metadados do documento (o
padrão chave-metadados de `platform/knowledge/base/models.py`) e na
forma de resultado de busca, então "esse sintoma aconteceu aqui" classifica
postmortems por correspondência de sintoma. **O par AdGuard é a fixture de
aceitação**: uma busca pelo sintoma retorna ambas, ordenadas, com a entrada de
July-20 identificável como a que carrega a causa raiz (seu `recurrence-of` nomeia
a entrada de July-17 — o link é extraído, ambas as direções armazenadas).

**Decisão — qualidade de extração é medida (Artigo VII)**: as dez postmortems do
corpus se tornam uma fixture de avaliação; o extrator é enviado com uma
ablação (somente estrutural vs com fallback de modelo) então a contribuição da
chamada de modelo é um número, e um deployment sem provider configurado ainda
ingere com extração estrutural sozinha — degradada explicitamente, funcional
(Artigo VI.4).

## Escopo C — knowledge ↔ estate

Uma tabela de link derivada em ingestão: document ↔ resource, combinado por hostname
e domain. As chaves de match vêm do enriquecimento de 053 (as tags `host-*.kyo.ninja`
de cada workload e traefik domain são atributos de recurso). Armazenado
como edges de topologia (nó document → nó resource — o gráfico é o
único lugar onde "quem toca quem" vive, portas do Artigo XI), servido no
detalhe de recurso (o painel `documents that mention this` que o plano de 053 deixou para
esta feature), e injetado no contexto de investigação via o caminho
de recuperação de conhecimento existente — recuperação permanece dirigida por agent (Artigo VII.3): o
link torna a recuperação *findable*, não pré-injeta.

## Escopo D — queries de verificação como candidate detectors

`docs/runbooks/cluster-double-check-queries.md` é analisado em sync em
declarações de candidate detector: **desativado**, cada um carregando o
excerpt da fonte e a citação do documento. Eles aparecem na tela de detectors como
candidatos; habilitar é o ato do operador, previsualizando com o
`POST /v1/detectors/{id}/dry-run` existente. **Decisão — candidatos são armazenados como
linhas ordinárias de detector com `enabled=false` e um `origin` nomeando o
documento**, não uma loja de candidatos paralela: a superfície de detectors, dry-run
e as rotas enable/disable todas existem, e uma segunda fila precisaria de suas próprias
rotas e tela para sem comportamento. (061 depois reutiliza exatamente essa forma
para candidate detectors propostos por agent.)

## O que esta feature NÃO faz

- Nenhuma superfície de *autoria* de documento; o corpus é a fonte de verdade e
  re-sync é o caminho de escrita. (Documentos agent-*propostos* são 061.)
- Sem mutação de estate: um runbook que contradiz o estate é reportável
  (o link do documento carrega `last_synced` vs `last_seen` do estate; o
  painel de detalhe diz qual é o atual) — o estate vence, o documento
  nunca é editado.
- Sem sincronização genérica de host-git (integrações github/gitlab existem para
  o sinal de mudança de 057; essa fonte lê arquivos, não histórico).

## Verificação de constituição

- **I** — citações carregam caminho + seção (`Citation` existe); resultados
  de extração carregam a seção de onde vieram.
- **II** — limites de contagem-de-arquivo/tamanho para a sincronização como constantes nomeadas;
  `MAX_DOCUMENT_CHUNKS` já limita documentos.
- **IV** — screening herdado; o teste fixture-com-credencial é
  aceitação 5, e a recusa nomeia o arquivo, nunca o valor.
- **VI** — extração degrada para estrutural sem um provider.
- **VII** — ablação de extração; o mecanismo de link-estate é exercível
  pela quarta fonte do cenário de 055, cujo delta é reportado.
- **VIII/XI** — fonte de sync em `platform/knowledge/base/sync/`, links via
  porta de topologia, sem SQL fora de persistência.
- **XII** — corpus de fixture (uma cópia raspada das *formas* da árvore real,
  não seu conteúdo) comprometido sob `fixtures/`; a ingestão real 54/10/3
  é uma execução deviations-registrada contra o cluster.
