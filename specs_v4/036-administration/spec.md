# 036 — Administration

## Problemas

### 1. [bloqueia entendimento] A lista de tokens é um despejo

"Machine tokens" lista **~70 entradas "Console sign-in"** (sessões de browser,
uma por login, três por hora durante esta auditoria) misturadas com tokens
`bootstrap`, cada uma com seu Revoke, mais "88 revoked" no rodapé. Problemas
em cadeia:

- Sessões de console não são "machine tokens" na cabeça de ninguém; separar
  **Sessões ativas** (agrupadas por pessoa/dispositivo, com "encerrar todas")
  de **Tokens de máquina** (nomeados, com escopo e uso).
- Por que cada page-load parece emitir/renovar um token com validade de 12h?
  Se é renovação de sessão, não deveria virar linha nova; investigar a
  emissão (isso também polui o Audit — spec 038).
- Colunas sem header (o que é "in 12 hours" vs "4 hours ago"? expiração vs
  emissão — adivinhação).

### 2. [bloqueia entendimento] SSO grita erros antes de qualquer input

A seção Single sign-on abre com "This configuration cannot be used:" seguida
de **8 mensagens "X is required"** — antes de o operador tocar num campo.
Validação exibe-se on-submit (ou on-blur por campo), nunca no estado
intocado. O conteúdo em si (testar com claims reais antes de ativar,
"an untested provider is every operator locked out") é excelente — só está
sendo entregue como bronca.

### 3. [bloqueia entendimento] Grants e roles em slug

`bootstrap-administrator`, `local-admin`, roles `viewer/responder/operator/
admin/owner` sem uma linha dizendo o que cada role pode. O select de role
precisa de descrição por opção (mesmo padrão da spec 031 para níveis de
autonomia).

### 4. [polimento] "Bootstrap administrator — Not recorded"

"Not recorded" como identidade do principal parece erro. Dizer o que é
("conta de serviço criada no deploy, sem e-mail").

### 5. [polimento] Issue a token sem escopo

O formulário pede só "What it is for" — e os tokens listados têm escopos
(`investigation.read, token.manage`). Onde se escolhe o escopo do token novo?
Se é fixo, dizer qual; se não, expor a escolha.

## Critérios de aceite

- Sessões e tokens de máquina são listas separadas; sessões agrupadas.
- Um login não gera linhas novas acumulando indefinidamente.
- Nenhuma validação visível antes da primeira interação com o formulário.
- Toda role/escopo tem descrição no ponto de escolha.
