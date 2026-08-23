# 050 — Duas telas quebradas

Independente de todo o resto. Pequena, e vale entregar primeiro porque é a única
spec que conserta algo que já deveria funcionar.

## O defeito

Duas das quatorze telas do console devolvem **HTTP 500** ao serem abertas por um
operador autenticado com todas as permissões:

```
GET /catalogue  -> 500
GET /autonomy   -> 500
```

O log do servidor dá a causa exata:

```
Error: /v1/config/{node_id}/catalogue needs a value for {node_id}
Error: /v1/autonomy/policy/{node_id} needs a value for {node_id}
```

O cliente monta a URL com o template literal, sem substituir `{node_id}`. As
telas que funcionam — `/configuration`, `/resources`, `/topology` — ou resolvem
um nó antes de chamar, ou chamam rota sem parâmetro.

A `/configuration` mostra qual é o caminho certo: ela lê o nó de
`?node=` e, na ausência dele, usa a raiz da árvore que `GET /v1/config` devolveu.
`/catalogue` e `/autonomy` não fazem nem uma coisa nem outra, e quebram antes de
o operador ter qualquer chance de escolher um nó — não há como chegar ao estado
bom a partir do estado inicial.

## Escopo

### A. Resolver o nó antes de chamar

As duas telas adotam o mesmo padrão da `/configuration`: nó de `?node=` quando
houver, senão a raiz da árvore. Uma tela cujo dado depende de um nó não pode
chamar sem um.

### B. Falhar como painel, não como página

Mesmo corrigido, uma dependência pode estar indisponível. O componente `Panel` já
tem estados de erro e de vazio, e as telas boas os usam — é por isso que
`/resources` renderiza mesmo sem recursos. Uma dependência ausente derruba um
painel, não a rota inteira.

Isto vale para as quatorze telas, não só para as duas: nenhuma tela do shell pode
responder 500 por causa de uma dependência. O erro é do painel.

### C. Cobertura de smoke que teria pego isto

O smoke check do fluxo canary hoje verifica `/health/live`, `/health/ready`,
`/openapi.json`, `ready:true` e `store_state:healthy` — tudo na API, nada no
console. Foi por isso que duas telas 500 passaram por um deploy validado.

Estender para percorrer, autenticado, todas as rotas do shell e exigir 200 em
cada uma. É barato: são quatorze requisições contra um processo que já está de
pé. Fica no fluxo canary, junto com o resto — e é a razão de a próxima tela
quebrada não chegar a ser promovida.

Depende do console passar a ser servido junto com a aplicação, o que hoje não
acontece (ver a nota de deployment no README). Enquanto não acontecer, o smoke
roda contra o console de desenvolvimento apontando para a API do container.

## Aceitação

1. `/catalogue` e `/autonomy` devolvem 200 num deployment sem nada configurado.
2. Nenhuma das quatorze rotas do shell devolve 500 quando uma dependência da API
   está indisponível — o painel afetado mostra seu estado de erro e a página
   renderiza.
3. O smoke check do canary percorre as quatorze rotas autenticado e falha o deploy
   se alguma não devolver 200.
4. Um teste cobre especificamente o caso "nenhum nó selecionado" para toda tela
   cujo dado dependa de um nó.
