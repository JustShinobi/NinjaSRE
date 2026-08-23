# Feature Specification: Catálogo de integrações navegável

**Feature Branch**: `feat/v5-020-integrations-catalogo`

**Created**: 2026-08-14

**Status**: Draft

**Input**: User description: "Rework de /integrations: conectadas primeiro, sugestões do estate em destaque, busca e filtro por categoria, grid compacto com nomes de exibição, credencial em painel lateral com instruções, referência de vendors não cobertos em página própria. Mata a barra de rolagem de 13 telas."

**Referência visual (DoD)**: [../mockups/settings-v5.html#mockup-2](../mockups/settings-v5.html#mockup-2) (catálogo: ordem das seções, busca, chips de filtro, grid) e [#mockup-3](../mockups/settings-v5.html#mockup-3) (painel lateral de credencial: labels, ajuda por campo, "Salvar e testar"). Integrations é entrada própria da sidebar, na rota `/integrations`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ver o que está conectado, primeiro (Priority: P1)

Um operador abre Integrations e vê imediatamente o que está conectado e em que
estado, seguido do que o próprio ambiente sugere conectar — antes de qualquer
item não configurado.

**Why this priority**: Hoje as 2 integrações configuradas afogam no meio de 82
cards "UNCONFIGURED" em ordem alfabética, em 11.730px de página. A pergunta
nº 1 do operador ("o que eu uso e está saudável?") é a última que a tela
responde.

**Independent Test**: Com 2 conectadas e 1 sugerida, a primeira dobra da
página responde o que está conectado, o estado de cada uma e a sugestão.

**Acceptance Scenarios**:

1. **Given** um deployment com Prometheus e Proxmox verificadas, **When** o
   operador abre Integrations, **Then** a seção "Connected" lista as duas com
   chip de estado do vocabulário canônico e ação de gerenciar, acima de
   qualquer outra seção.
2. **Given** um estate onde o Grafana foi descoberto rodando, **When** a tela
   abre, **Then** a sugestão aparece em destaque com a evidência ("encontrado
   em <endereço>, no recurso <nome>") e ação de conectar — usando os dados de
   sugestão que a API já serve.
3. **Given** nenhuma integração conectada, **When** a tela abre, **Then** a
   seção de sugestões (se houver) e o catálogo aparecem, sem seção "Connected"
   vazia.

### User Story 2 - Encontrar uma integração em segundos (Priority: P1)

O operador encontra qualquer uma das 84 integrações por busca ou filtro de
categoria, num grid compacto com nome de exibição, categoria e resumo de uma
linha.

**Why this priority**: É o defeito nomeado pelo operador ("a scroll bar fica
gigante"). Lista plana sem busca não escala para 84 itens e escalará pior.

**Independent Test**: Medir a altura da página com o catálogo completo e o
tempo até encontrar três integrações dadas pelo nome.

**Acceptance Scenarios**:

1. **Given** o catálogo aberto, **When** o operador digita "post" na busca,
   **Then** o grid reduz em tempo real aos itens cujo nome, categoria ou
   capacidade casa com o termo.
2. **Given** o filtro de categoria "Chat & on-call" ativo, **When** o grid é
   exibido, **Then** só integrações dessa categoria aparecem, e o chip do
   filtro indica o estado ativo.
3. **Given** nenhum filtro, **When** a página abre com 84 integrações,
   **Then** a altura total não excede 2 viewports em 1080p (grid paginado ou
   virtualizado), e o total é comunicado ("84 disponíveis · 2 conectadas").
4. **Given** um termo de busca sem resultado, **When** o grid esvazia,
   **Then** o empty state oferece limpar a busca e o link para a referência
   de vendors não cobertos.

### User Story 3 - Conectar com instruções, testar no mesmo gesto (Priority: P2)

Conectar uma integração abre um painel lateral sobre o catálogo com o
formulário de credencial: labels humanas, instrução de onde obter cada valor,
permissão mínima exigida, e "Salvar e testar" como ação única.

**Why this priority**: O formulário atual tem labels cruas ("token",
"project"), nenhuma instrução, e deixa o estado "Stored" como fim silencioso
de fluxo — a diferença entre armazenada e funcionando é invisível até uma
investigação falhar às 3 da manhã (o próprio produto avisa isso em prosa).

**Independent Test**: Conectar uma integração nova de ponta a ponta só com o
que o painel mostra, sem consultar documentação externa.

**Acceptance Scenarios**:

1. **Given** o card do BigQuery, **When** o operador clica em conectar,
   **Then** um painel lateral abre com nome de exibição, categoria, resumo,
   campos com label humana e texto de ajuda dizendo onde obter o valor e a
   permissão mínima, e link "guia passo a passo".
2. **Given** o formulário preenchido, **When** o operador clica em "Salvar e
   testar", **Then** a credencial é gravada e o teste real roda na sequência;
   o resultado aparece como chip canônico (Verified/Failing) com diagnóstico.
3. **Given** o painel aberto, **When** o operador fecha, **Then** volta ao
   catálogo na mesma posição de rolagem e com os mesmos filtros.
4. **Given** um deep link `/integrations/<nome>`, **When** aberto, **Then** o
   catálogo abre com o painel daquela integração já aberto.

### User Story 4 - Saber o que não é coberto, quando perguntar (Priority: P3)

A explicação de vendors não cobertos ("Not covered, and why") vive em página
de referência própria, linkada do rodapé do catálogo e da busca sem resultado.

**Independent Test**: O texto integral existe na página de referência; o
catálogo contém apenas o link.

**Acceptance Scenarios**:

1. **Given** o catálogo aberto, **When** o operador rola até o fim, **Then**
   encontra um link "N vendors não cobertos, e por quê" — não os nove
   parágrafos.
2. **Given** a página de referência, **When** aberta, **Then** cada vendor
   traz causa ("não alcançável daqui" vs "avaliado e decidido contra"),
   razão e o que mudaria a decisão — o conteúdo atual, estruturado.

### Edge Cases

- Integração com credencial gravada cuja verificação nunca rodou: estado
  "Stored", com a ação de testar oferecida no painel e na linha da seção
  Connected (aparece em Connected, não no grid).
- Integração "Failing": permanece na seção Connected com chip crítico e
  diagnóstico — falha de credencial não a devolve ao catálogo.
- Sugestão do estate para integração já conectada: não aparece como sugestão.
- Falha ao gravar/testar por indisponibilidade do gateway: erro nomeado no
  painel, formulário preservado.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A página DEVE apresentar, nesta ordem: seção Connected (quando
  não vazia), seção de sugestões do estate (quando não vazia), e o catálogo
  filtrável.
- **FR-002**: A página DEVE oferecer busca em tempo real por nome de
  exibição, categoria e capacidade, e filtros por categoria e por estado
  (Connected, Suggested, All).
- **FR-003**: Cada item do catálogo DEVE exibir nome de exibição, categoria e
  resumo de uma linha vindos do backend; o id cru não aparece no grid.
- **FR-004**: O catálogo completo DEVE caber em até 2 viewports (1080p) por
  paginação ou virtualização; o total e a contagem por filtro são exibidos.
- **FR-005**: O formulário de credencial DEVE abrir em painel lateral
  preservando o contexto do catálogo, com deep link por integração.
- **FR-006**: Cada campo de credencial DEVE ter label humana, instrução de
  obtenção e permissão/escopo mínimo; esses textos fazem parte do catálogo de
  cada integração no backend.
- **FR-007**: "Salvar e testar" DEVE ser a ação primária única; o teste roda
  imediatamente após gravar e o resultado usa o vocabulário canônico. A nota
  de segurança ("guardada no vault; nunca exibida de novo; o teste faz uma
  requisição real") permanece, em duas frases.
- **FR-008**: As linhas de estado redundantes do card atual DEVEM desaparecer;
  o estado é um chip único por item.
- **FR-009**: Os vendors não cobertos DEVEM mover para página de referência
  própria, linkada do catálogo; o dado continua servido junto do catálogo pela
  API, como hoje.
- **FR-010**: O fluxo DEVE respeitar o desenho de segredos vigente: valores de
  credencial seguem write-only (nunca reexibidos), e o painel não exibe
  segredo armazenado.

### Key Entities

- **Item de catálogo**: id, nome de exibição, categoria, resumo, capacidades,
  credenciais exigidas (cada uma com label, instrução, escopo mínimo), estado,
  diagnóstico, sugestão do estate (opcional).
- **Sugestão do estate**: integração, endereço, recurso de origem, evidência.

## Success Criteria *(mandatory)*

- **SC-001**: A altura da página com 84 integrações cai de ~13 viewports para
  no máximo 2 em 1080p.
- **SC-002**: Encontrar uma integração nomeada leva menos de 10 segundos
  usando a busca.
- **SC-003**: Um operador conecta uma integração nova de ponta a ponta sem
  consultar documentação externa (teste de usabilidade com 3 integrações de
  campos distintos).
- **SC-004**: O estado exibido de cada integração é idêntico ao servido pela
  API em 100% dos casos (sem texto de estado duplicado ou divergente).

## Assumptions

- A API atual (`GET /v1/integrations`) já serve categoria, resumo, saúde e
  sugestão; a spec assume extensão do catálogo para labels/instruções de
  credencial, sem definir o formato.
- Logos: iniciais estilizadas bastam nesta onda (logos reais de vendors
  envolvem marca registrada; fica fora de escopo).
- A ordenação por relevância continua vindo do backend (contrato atual).

## Dependencies

- 001 (vocabulário de estado, registro de exibição, contrato de CTA).
- 060 consome o filtro por categoria via deep link (Destinations → chat).
