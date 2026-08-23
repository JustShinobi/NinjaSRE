# specs_v5 — Rework da área de Settings

Onda gerada em 2026-08-14 a partir da análise visual das seis telas do grupo
Settings (Full HD, front local preview 3101, backend do repositório) e do
brainstorm com o operador.

**Referência visual de DoD**: [mockups/settings-v5.html](mockups/settings-v5.html)
— abra no navegador. Os mockups refletem o escopo final (navegação híbrida,
substituição 100% do editor cru) e são normativos em layout, hierarquia,
agrupamento e vocabulário (pixels exatos não). Âncoras: `#mockup-1` (shell
híbrido, specs 010/040), `#mockup-2` e `#mockup-3` (catálogo e credencial,
spec 020), `#mockup-4` (wizard, spec 030). Versão publicada (idêntica):
<https://claude.ai/code/artifact/727c731f-5a52-4a79-8ac2-d357979d0ceb>

## As decisões que governam a onda

Registradas aqui porque cada spec as assume; revisá-las é revisar a onda.

1. **Navegação híbrida.** Integrations permanece como entrada própria na
   sidebar (uso frequente); todo o resto do grupo Settings vira uma única
   entrada **Settings** com navegação secundária própria (Organização /
   Agente / Dados). Isso revisa parte da decisão da spec 090 da v4
   (13 áreas na sidebar) — decisão do operador em 2026-08-14.
2. **O editor de configuração cru morre.** Substituição 100% por telas
   humanas com paridade total de schema; nada de "Advanced escape hatch".
3. **Escopo inclui o shell.** Vocabulário de estado, empty states e contratos
   de CTA valem para o produto inteiro, não só para Settings.
4. **Uma feature por domínio**, implementáveis e testáveis em sequência.

## Índice e ordem de execução

| Spec | Domínio | Depende de |
|---|---|---|
| [001](001-fundacao-vocabulario-ux/spec.md) | Fundação: vocabulário de estado, registro de nomes, contrato de CTA, orçamento de rolagem | — |
| [010](010-navegacao-settings/spec.md) | Navegação híbrida e shell de Settings | 001 |
| [020](020-integrations-catalogo/spec.md) | Catálogo de integrações navegável | 001 |
| [030](030-setup-wizard/spec.md) | Setup como wizard com contagem única | 001, 010 |
| [040](040-agente/spec.md) | Telas do agente: Models & providers, Autonomy & guardrails, Notifications | 010 |
| [050](050-organizacao/spec.md) | Organização: Members, SSO, Machine tokens, Audit (com fixes) | 010 |
| [060](060-dados/spec.md) | Dados: Alert intake, Schedules & destinations | 010, 020 |
| [070](070-migracao-editor-cru/spec.md) | Aposentadoria do editor cru com paridade de schema | 040, 050, 060 |

020 e 030 podem andar em paralelo depois de 001/010; 040, 050 e 060 também
são paralelizáveis entre si.

Cada feature carrega o trio completo do spec-kit — `spec.md` (o quê e por
quê), `plan.md` (como, com Constitution Check) e `tasks.md` (passos
numerados, test-first) — mais `checklists/requirements.md`. O `tasks.md` de
cada uma termina atualizando um `controle.md` da feature, no padrão da v4.

## Onde os testes moram (corrigido em 2026-08-14)

A onda foi escrita citando caminhos de teste que **os runners deste
repositório não coletam**. Um teste num caminho não coletado não roda, e um
teste que não roda é evidência fabricada. Os caminhos foram corrigidos em
todas as specs; os fatos que os governam:

- `console/vitest.config.ts` coleta **só** `tests/unit/**/*.test.ts` e
  `tests/unit/**/*.test.tsx`. Um `.test.ts` dentro de `console/src/` nunca é
  executado. Testes unitários vão em `console/tests/unit/<área>/`.
- `console/playwright.config.ts` tem `testDir: 'tests'` e três projetos:
  `behaviour` (`tests/e2e`), `first-day` (`tests/first-day`, cenário de
  deployment vazio) e `visual` (`tests/visual`). **`console/e2e/` não
  existe.** Specs de comportamento vão em `console/tests/e2e/`.
- O `use.viewport` global do Playwright é `1440×900`, fixo e deliberado. Toda
  medição em 1080p declara o próprio viewport, explicitamente.

## Ferramentas do spec-kit

`.specify/feature.json` aponta para a feature ativa. Antes de rodar
`/speckit-plan` ou `/speckit-tasks` para outra feature desta onda, aponte-o
para o diretório dela (ou exporte `SPECIFY_FEATURE_DIRECTORY`), por exemplo:

```json
{ "feature_directory": "specs_v5/020-integrations-catalogo" }
```
