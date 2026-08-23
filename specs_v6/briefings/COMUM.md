# Briefing comum — vale para toda feature da onda specs_v6

Leia antes do briefing da sua feature: [../README.md](../README.md) (decisões e
ordem), [../DIAGNOSTICO.md](../DIAGNOSTICO.md) (defeitos com `file:line`,
inventário, cenários) e o mockup da sua feature em
[../mockups/settings-v6.html](../mockups/settings-v6.html).

## Regras de escrita das specs (herdam a v5, com adições)

1. **pt-BR** em spec.md/plan.md/tasks.md/checklists; código e strings de
   produto em inglês via i18n (en + pt-BR sempre juntos).
2. Specs podem citar FR-/SC- entre si e apontar mockups/briefings — são
   documentos não-committed. Mas **nenhuma tarefa pode instruir** escrever
   FR-, artigos da constituição, números de feature ou caminhos de planejamento
   em arquivo committed (código, teste, AGENTS.md). A substância vai no
   arquivo; a referência fica na spec.
3. Todo requisito de tela cita a âncora do mockup (`#m1`…`#m6`) e as alegações
   normativas viram FRs individuais — uma vírgula é fronteira de requisito.
4. **Acceptance-first é obrigatório em feature de console**: o tasks.md abre a
   fase de testes com `console/tests/e2e/<slug>.acceptance.spec.ts` codificando
   as alegações do mockup (seções e ordem, palavras exatas dos chips, destino
   de CTA, contagem única, coluna de valor preenchida, orçamento de rolagem),
   confirmado vermelho antes da tela. Viewport 1080p declarado no próprio spec
   quando medir rolagem.
5. Testes moram onde os runners coletam: unit em `console/tests/unit/`,
   Playwright behaviour em `console/tests/e2e/`, visual em
   `console/tests/visual/`; Python conforme pytest.ini. Um caminho não
   coletado é evidência fabricada.
6. Vocabulário de estado de credencial/verificação em todo o produto:
   **Not connected · Stored · Verified · Degraded · Failing** (en) /
   **Não conectada · Armazenada · Verificada · Degradada · Falhando** (pt-BR).
   Degraded existe porque o preflight o produz; nenhuma tela o traduz para
   outra palavra.
7. tasks.md termina atualizando o `controle.md` da feature (padrão v4/v5), e
   inclui a atualização de `console/visual/screens.json` + captura deliberada
   de baseline quando a feature mexe em tela registrada.
8. Cada spec lista explicitamente os gates que toca (paridade, contagens,
   check-integration-docs, test_contract_coverage etc.) — nada de descobrir no
   implement.

## Fatos que nenhuma spec re-deriva (já verificados)

- Preflight: probe de tool-calling em `core/llm/preflight.py:168` com
  `mode: "AUTO"` em `core/llm/providers/gemini.py:193`; degraded não bloqueia o
  backend (`PreflightReport.ok`), e o console é quem trava.
- Modelos hardcoded: `core/llm/onboarding/gemini.py:28-33` (6 modelos);
  `GET https://generativelanguage.googleapis.com/v1beta/models` com a chave do
  deployment lista 37 modelos generateContent (inclui 3.5/3.6/3.7-flash).
  Curadoria necessária: excluir famílias image/tts/robotics/lyria/gemma-embed;
  a capacidade de tool-calling é confirmada pela verificação, não pela lista.
- Webhook: `POST http://192.168.68.74:8420/webhooks/alertmanager` → 401 sem
  delivery token.
- Estado do deployment: dashboard com 2 incidentes mortos em "no runtime to
  investigate with"; modelo atual `gemini-2.5-flash` (trocado em 2026-08-16).
