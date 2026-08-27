# 058 — Configuração, depois do primeiro uso

O primeiro uso estabelece o mínimo viável. Esta spec cobre tudo o que se muda
depois — e é onde o console deixa de ser um visualizador.

## Por que isto é separado da 052

O primeiro uso é linear e acontece uma vez. A configuração contínua é hierárquica,
acontece sob pressão, e a pergunta que ela precisa responder não é "o que eu
coloco aqui" e sim **"onde isto está definido, e o que acontece se eu mudar"**.
São dois problemas de interface distintos e misturá-los produz um assistente que
ninguém usa duas vezes.

O backend já resolveu a parte difícil. `GET /v1/config/{node_id}` devolve os
valores efetivos **com proveniência** — de qual nível cada valor veio. A tela
`configuration.tsx` já renderiza essa coluna e o comentário no código explica por
quê: *"'Where is this set' is the question every configuration screen gets asked
and almost none answers, and without it an operator changes a value at the wrong
level, sees no effect, and concludes the console is broken."*

Tudo isso existe e é somente-leitura. Falta o editor.

## Escopo

### A. Editor da árvore de configuração

Rota já existe: `PUT /v1/config/{node_id}`, com
`POST /v1/config/{node_id}/preview` ao lado.

O painel de preview **já está no console**, atrás da permissão `config.write`, e
já renderiza *"What saving would resolve to / Nothing would change"*. Ele hoje
não tem nada que produza um patch. Esta spec adiciona:

- edição por campo, dirigida pelo catálogo do nó
  (`GET /v1/config/{node_id}/catalogue`) — tipo, faixa, padrão e descrição vêm do
  catálogo, não de uma tabela no front;
- **preview obrigatório antes de salvar**: a rota de preview é chamada com o
  patch pendente e o resultado é mostrado como diff dos valores efetivos, com a
  proveniência de cada valor alterado;
- o aviso, no próprio diff, quando um valor é definido num nível que já herda o
  mesmo valor do pai — a causa número um de "mudei e não teve efeito";
- limpar um valor num nó, voltando a herdar, como operação de primeira classe e
  distinta de defini-lo igual ao pai.

### B. Política de autonomia

Rotas já existem, e são mais completas que o resto:
`PUT /v1/autonomy/policy/{node_id}`, `/bounds`, `/dry-run`, `/explain`,
`/overrides`, `/preview`, além do kill switch em
`POST|DELETE /v1/autonomy/kill-switch`.

Nenhuma delas tem superfície. Esta é a decisão de configuração de maior
consequência da plataforma — o que pode acontecer sem uma pessoa — e hoje só é
alcançável por chamada HTTP direta. Escopo:

- ler e escrever a política por nó, com `preview` e `explain` mostrados **antes**
  do salvar, nunca depois;
- alternar o modo dry-run com destaque visual, porque é a diferença entre um
  sistema que propõe e um que age;
- o kill switch como controle próprio e sempre alcançável, não escondido atrás de
  navegação — engajá-lo é o que se faz quando algo está errado, e nesse momento
  ninguém procura submenu;
- concessões de override com a duração e o motivo visíveis na própria lista.

### C. Administração

`administration.tsx` hoje declara honestamente que SSO é *"stated rather than
configured here"*. As rotas existem: `GET|PUT /identity/sso`, `/sso/test`,
`/sso/activate`. Escopo:

- configurar SSO, com `test` obrigatório antes de `activate` — a rota de teste
  existe justamente para que ninguém ative um provedor de identidade quebrado e
  se tranque para fora;
- emitir e revogar tokens de máquina (`POST /identity/tokens`,
  `POST /identity/tokens/revoke`, `DELETE /identity/tokens/{id}`), com o segredo
  mostrado **uma única vez** no momento da emissão e nunca recuperável, no mesmo
  padrão da credencial de bootstrap;
- conceder e remover papéis (`POST|DELETE /identity/grants`), com a recusa de
  remoção do último owner exibida como o erro que ela é, não como falha genérica.

### D. Detectores e agendamentos

Rotas completas: enable, disable, dry-run para detectores; CRUD completo para
agendamentos. Ambas as telas são somente-leitura hoje. O dry-run de um detector é
particularmente valioso na validação — mostra o que ele teria disparado sobre o
histórico real do cluster antes de deixá-lo disparar de verdade.

## O que continua sem editor, e por quê

- **Credenciais** já foram tratadas em 051/052. Aqui aparecem apenas como estado:
  configurada, verificada, quando foi verificada pela última vez. Nenhum valor.
- **Guardrails** (`GET /v1/config/{node_id}/guardian`) são um arquivo editável
  pelo operador, carregado em todo deployment. Editá-lo pela UI significa que um
  deployment pode se deixar sem proteção por um erro de digitação num formulário.
  Fica somente-leitura nesta spec, com o caminho do arquivo indicado.

## Aceitação

1. Mudar um valor de configuração pelo console exige ver o preview, e o preview
   mostra a proveniência de cada valor alterado.
2. Definir num nó um valor idêntico ao herdado produz um aviso explícito.
3. A política de autonomia é editável, com `explain` mostrado antes de salvar, e o
   kill switch é alcançável a partir de qualquer tela.
4. SSO não pode ser ativado sem um teste bem-sucedido no mesmo formulário.
5. O segredo de um token emitido aparece uma vez e não é recuperável depois.
6. Toda escrita nova aparece na auditoria com ator, recurso e resultado.
