# Tarefas — 057 Código e deploy como sinal

Depende de 051 (caminho de credencial para fontes de git-host) e 053 (mapeamento
componente → workload do enriquecimento). Ordenado, um commit cada um, teste-primeiro.

## Phase 1 — o conceito de mudança

- **T-001** Testes falhando para o protocolo `ChangeSource` e o registro `Change`
  em `platform/changes/`: forma de query de janela; applied vs committed
  como um field; limites de janela e contagem-resultado como constantes nomeadas em
  `config/constants/changes.py`. Implemente o protocolo (corpos somente-docstring —
  `make check-protocols`).
- **T-002** Testes falhando para a fonte `infra_apply` contra um fixture
  apply record + git log moldado como o repositório real (mensagens estruturadas,
  `.infra-state/`): mudanças na janela com autor, instante,
  mensagem, caminhos, componente; um commit nunca aplicado é marcado assim.
  Implemente.
- **T-003** Teste falhando: mensagens de commit e caminhos passam screening de
  guardrail antes de entrar em um trace ou resultado; uma mensagem de fixture carregando um
  shape de credencial é redatada com a regra nomeada (aceitação 5).
- **T-004** Testes falhando para a fonte git-host: adapter sobre a
  listagem de commits de clientes de integração existentes, vendor escolhido por
  configuração, mesmo shape `Change` saindo. Implemente.

## Phase 2 — correlação

- **T-005** Testes falhando para `platform/changes/correlation.py`: path →
  componente da lista de componentes ingerida; componente → workload via
  mapeamento de 053; força como enumeração fechada
  (`MANAGES_RESOURCE` / `TOUCHES_SHARED_POLICY` / `WINDOW_ONLY`); o
  fixture de política de firewall correlaciona para o workload cujo perfil vive
  lá; um alerta de disco-cheio contra a mesma mudança é `WINDOW_ONLY`.
  Implemente.
- **T-006** Teste falhando: a janela vazia retorna uma entrada de evidência
  negativa explícita nomeando as fontes consultadas e a janela (aceitação
  4). Implemente.

## Phase 3 — the capability

- **T-007** Failing contract test for the `changes_in_window` tool:
  declared metadata complete (read side-effect level, evidence source, use
  cases), schema bounded, result rows carry strength labels. Scaffold via
  `tools/scaffold_capability.py`, implement.
- **T-008** Synthetic scenario: alert at T, apply at T−13min on the
  managing component ⇒ the conclusion cites the change with
  `MANAGES_RESOURCE` strength; ablation with correlation disabled reported.
  A second scenario asserts the negative sentence on a quiet resource.

## Phase 4 — the surfaces

- **T-009** Run screen footer: timeline overlay marking correlated changes
  on the same ruler as the investigation window (D3 §2). Component test
  first; visual baseline re-captured.
- **T-010** Resource detail: "recent changes" panel from the same
  correlation. Component test first.

## Phase 5 — proof

- **T-011** `make verify` green; scenario-suite delta reported. Against the
  real repository (deviations, not gate): `changes_in_window` over a real
  window returns the actual applies with authors and paths; one recorded
  transcript.

## Definition of done

1. A change source answers "what changed between T−N and T" against the
   real repository with author, instant and paths (T-002/T-011).
2. A change correlates to a resource through path → component → workload,
   and the fixture proves temporal-only proximity does not produce
   `MANAGES_RESOURCE` (T-005).
3. Correlation strength appears in the report; `WINDOW_ONLY` is labelled as
   temporal coincidence (T-005/T-008).
4. An investigation over a quiet resource states "no change touched this
   resource in the window" as evidence, not as silence (T-006/T-008).
5. The credential-shaped commit message is redacted with the rule named
   (T-003).

## Dependencies on other specs_v3 features

- **051** (hard, git-host source only): credential path. The `infra_apply`
  source needs no credential.
- **053** (hard): component → workload mapping; resource identities.
- **Feeds** the D3 §2 run screen (timeline overlay is this feature) and
  060's tool catalogue (one more read tool with declared integration
  requirements).
