# 057 — Código e deploy como sinal

**Depende de:** 051, 053.

Esta spec existe porque eu deixei uma categoria inteira de fora.

## A lacuna

O diagrama que descreve o propósito do produto organiza as fontes em quatro
categorias: **Production Systems, Observability, Knowledge, Code**. As specs 053,
054 e 056 cobrem as três primeiras. A quarta não tem nada.

E é a categoria que responde à pergunta que um SRE faz primeiro, antes de
qualquer métrica:

> **O que mudou pouco antes disso quebrar?**

Uma investigação que consulta métrica, log e trace e nunca pergunta "houve deploy
nos últimos 30 minutos" está fazendo arqueologia num sistema onde a resposta
costuma estar no `git log`.

## Por que é barato neste cluster

O `/root/infra-cluster` **é** a fonte de mudança. Não é um repositório de
aplicação qualquer — é o que aplica o estado do cluster:

- toda mudança de infraestrutura passa pelo `./infra apply --component <x>`,
  dirigido por OpenTofu;
- o histórico git tem mensagens estruturadas e legíveis
  (`fix(services)!: Decommission CT109`, `feat(runners): harden reliability...`);
- existe `.infra-state/` com o estado das aplicações;
- os componentes têm nome, e o nome mapeia para zonas e workloads que o 053 já
  descobriu.

E o catálogo do NinjaSRE já tem `github`, `gitlab`, `bitbucket` e `argocd`.
Nenhuma integração nova precisa ser escrita para o caso comum.

## Escopo

### A. Uma origem de mudança

Uma origem de mudança responde a uma pergunta com janela: *o que foi alterado
entre T-N e T, e por quem*. Para cada mudança: identificador, autor, instante,
mensagem, arquivos tocados, e — quando houver — o componente ou serviço afetado.

Duas implementações para esta validação:

1. **Repositório git** — commits numa janela, com os caminhos alterados.
2. **Aplicações de infraestrutura** — o registro de `./infra apply`, que é a
   mudança que de fato tocou o cluster. Um commit que ninguém aplicou não mudou
   nada, e essa distinção é a diferença entre correlação e coincidência.

A segunda é mais valiosa e mais específica deste ambiente. Se apenas uma for
construída, que seja ela.

### B. Correlação com o recurso, não com o relógio

Correlacionar só por tempo produz falso positivo em toda janela movimentada. A
correlação precisa passar pelo recurso:

- caminho alterado → componente (`services/monitoring/...` → componente
  `monitoring`);
- componente → workloads que ele gerencia, pelo estate do 053;
- workload → o recurso do alerta.

Uma mudança que tocou `policies/firewall/` e um alerta de conectividade num
workload cujo perfil de firewall está naquele diretório é uma correlação forte.
A mesma mudança e um alerta de disco cheio não é correlação nenhuma, ainda que
tenham acontecido no mesmo minuto.

**A força da correlação é reportada, não escondida.** "Houve uma mudança na
janela, que tocou este workload" e "houve uma mudança na janela" são afirmações
diferentes, e apresentá-las como iguais é como uma investigação acusa a coisa
errada com confiança.

### C. O que a investigação passa a poder afirmar

Com isto, um relatório pode conter a frase que hoje ele não pode:

> O erro começou às 14:32. Às 14:19 o componente `monitoring` foi aplicado,
> alterando `services/monitoring/stack/`. O workload afetado é gerenciado por
> esse componente.

E, tão importante quanto, pode conter a negativa com a mesma confiança: *nenhuma
mudança tocou este recurso nas últimas 24 horas* — que é o que faz alguém parar
de procurar no lugar errado.

## Fora de escopo

- Reverter uma mudança. Isso é remediação, e remediação vem depois da política de
  autonomia.
- Ler o conteúdo do diff para julgar mérito. A correlação é sobre *o quê* e
  *quando*, não sobre se a mudança estava certa.
- Repositórios de aplicação. Este cluster deploya infraestrutura; quando houver
  aplicação instrumentada, a mesma origem de mudança serve.

## Aceitação

1. Uma origem de mudança responde "o que mudou entre T-N e T" contra o
   repositório real, com autor, instante e caminhos.
2. Uma mudança correlaciona com um recurso do estate por caminho → componente →
   workload, e não apenas por proximidade temporal.
3. A força da correlação aparece no relatório, e uma correlação apenas temporal é
   rotulada como tal.
4. Uma investigação sobre um recurso sem mudanças recentes afirma isso
   explicitamente.
5. Nenhum segredo do repositório entra na plataforma — vale a mesma varredura da
   056.
