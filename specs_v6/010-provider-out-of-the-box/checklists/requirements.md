# Specification Quality Checklist: Provider out-of-the-box

**Purpose**: Validar a completude e a qualidade da especificação antes do
planejamento
**Created**: 2026-08-16
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] Nenhum detalhe de implementação nos requisitos (linguagem, framework, API)
- [x] Focada no valor para o operador e na necessidade do produto
- [x] Escrita para quem não vai ler o código
- [x] Todas as seções obrigatórias preenchidas

## Requirement Completeness

- [x] Nenhum marcador [NEEDS CLARIFICATION] restante
- [x] Requisitos testáveis e sem ambiguidade
- [x] Requisitos atômicos — uma vírgula é fronteira de requisito
- [x] Critérios de sucesso mensuráveis
- [x] Critérios de sucesso independentes de tecnologia
- [x] Todos os cenários de aceitação definidos
- [x] Casos de borda identificados
- [x] Escopo delimitado, com as fronteiras com outras features declaradas
- [x] Dependências e premissas identificadas

## Feature Readiness

- [x] Todo requisito funcional tem critério de aceitação claro
- [x] Os cenários cobrem o fluxo principal ponta a ponta (chave → lista →
      escolha → verificação → passo do setup fechado)
- [x] A feature atende aos resultados mensuráveis declarados
- [x] Nenhum detalhe de implementação vazou para a especificação

## Aderência às regras da onda

- [x] Documentos em pt-BR; strings de produto em inglês, com o par pt-BR, via
      i18n
- [x] Todo requisito de tela cita a âncora do mockup (`#m1`, `#m5`) e as
      alegações normativas viraram requisitos individuais
- [x] Acceptance-first: o `tasks.md` abre a fase de console com o spec de
      aceitação do mockup, com o vermelho confirmado antes da tela
- [x] Testes apontados para onde os runners coletam (`console/tests/unit/`,
      `console/tests/e2e/`, Python conforme `pytest.ini`); `console/e2e/` não é
      citado em lugar nenhum
- [x] O vocabulário de estado é o único da onda, e a palavra de degradação
      existe porque o preflight a produz
- [x] Os gates tocados estão listados explicitamente no `plan.md`
- [x] O `tasks.md` termina atualizando o `controle.md` da feature
- [x] Nenhuma tarefa instrui escrever identificador de requisito, artigo da
      constituição, número de feature ou caminho de planejamento em arquivo
      committed

## Notes

- Os fatos técnicos citados como evidência (probe em modo `AUTO`, lista estática
  de seis modelos, 37 modelos servidos pelo endpoint em 2026-08-16, o texto
  falso sobre não poder perguntar ao endpoint) foram verificados em 2026-08-16
  contra o backend do CT254 e contra o próprio código; a especificação os cita
  sem re-derivar.
- As decisões de escopo desta onda foram tomadas pelo operador em 2026-08-16 e
  estão registradas no README da onda — por isso nenhum marcador
  [NEEDS CLARIFICATION] restou.
- Três fronteiras foram declaradas em vez de resolvidas aqui: a contagem única
  de passos do setup (020), a varredura de vocabulário cru fora destas duas
  telas (030) e o corte do catálogo de integrações (001, pré-requisito).
- A suíte transversal executável nasce na feature 020; esta feature ainda não
  pode rodá-la, e a alegação transversal que ela própria consegue medir
  (orçamento de rolagem, com viewport 1080p declarado) foi embutida no seu
  acceptance spec.
- `controle.md` não é criado na geração: ele é escrito durante a execução, pelo
  implementador, com o que o código provar.
