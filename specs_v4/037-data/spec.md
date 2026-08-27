# 037 — Data

Conteúdo denso e genuinamente útil (endpoints de webhook por vendor, com
autenticação e formato). Os problemas são de forma e de um risco técnico.

## Problemas

### 1. [bloqueia entendimento] Três colunas, três features, uma tela

"What arrives" (7 webhooks de entrada), "What happens to it" (regras de
roteamento + simulador) e "Where the result goes" (destinos) dividem a
largura. A do meio é a mais confusa: "1. catch-all / Everything no rule above
matched ends here" (não há regra acima — o texto pressupõe uma lista que não
existe no vazio), um select "Receiver", um textarea "Payload" e botões
"Simulate/Save" sem dizer que isto é um **testador de roteamento**. Dar título
honesto ("Testar uma entrega"), e só mostrar a régua de regras quando houver
regras.

### 2. [risco] URLs de webhook em http:// com IP interno

Cada card exibe `http://192.168.68.74:8420/webhooks/...` — esquema http (a
console está em https) e IP interno. Se essa é a URL real de ingest, exibir
com o host público correto do deployment; se o gateway atende https, nunca
anunciar http. Copiável com um clique (hoje é texto solto).

### 3. [bloqueia entendimento] "Nothing has ever arrived here" sete vezes em vermelho

Estado normal de um deployment recém-configurado gritando em cor de erro,
7 vezes. Neutro ("aguardando o primeiro alerta"), com destaque apenas quando
um webhook *configurado no alertmanager do operador* silencia por muito tempo
— estado que a tela não distingue hoje.

### 4. [polimento] "Where did this go?" colapsado sem indicação de conteúdo

Sete disclosure-links idênticos; expandir para quê? (histórico de entregas?).
Rotular com o que contém ("últimas entregas: 0").

### 5. [polimento] "Issue a delivery token" solto

Botão órfão entre seções, sem explicar que os webhooks aceitam "a machine
token scoped to alert delivery" (o texto está nos cards). Aproximar botão e
explicação.

## Critérios de aceite

- O simulador tem nome e propósito legíveis; a régua de regras só aparece com
  regras.
- Nenhuma URL http:// numa página https; copiar URL com um clique.
- Estado "nunca chegou nada" não usa cor de erro.
