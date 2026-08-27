# 022 — Detectors

Duas features não relacionadas dividem a tela, e nenhuma das duas diz como
sair do estado vazio.

## Problemas

### 1. [bloqueia entendimento] O vazio aponta para o lugar errado

"Detectors ship with the deployment and appear here once continuous
observation is running." + botão **"Connect a source"**. Mas as fontes já
estão conectadas (Prometheus e Proxmox respondem); o que falta é **ligar o
guardian** (`policies.observation.guardian.enabled`, hoje "Set at nothing
yet"). O CTA manda o operador para onde ele já esteve e não resolve. Corrigir
a cadeia: o empty state verifica o estado real (fontes ok? guardian ligado?) e
oferece a ação que falta — idealmente um toggle "Ativar observação contínua"
aqui mesmo, já que a Configuration descreve isso como "a single flag porque
essa é toda a interação que a feature promete".

### 2. [bloqueia entendimento] "Scheduled investigations" é outra tela morando aqui

Agendamento de investigações não é um detector. O formulário cru — Identifier,
Name, Cron, Objective, Timezone e um botão — aparece sem: validação ou helper
de cron (nem um exemplo), explicação de "Identifier" vs "Name", preview do
próximo disparo, ou qualquer indicação do que "Objective" alimenta. A tabela
acima dele renderiza só o header (NAME CRON OBJECTIVE ...) sem linha de vazio.

Correção mínima: mover para um card com título explicativo, helper de cron
("`0 8 * * 1` = toda segunda às 08:00"), preview do próximo disparo, e empty
state na tabela. Correção estrutural (spec 090): agendamentos moram junto do
resto de "entrada de trabalho" (Alerting & ingest), não em Detectors.

### 3. [polimento] Título e subtítulo prometem o que a tela não mostra

"What is being watched for, how often, and what fired." — quando houver
detectores, ok; hoje nada na tela responde nenhuma das três perguntas.

## Critérios de aceite

- Com fontes conectadas e guardian desligado, a tela oferece a ativação da
  observação contínua diretamente ou por link direto ao campo exato.
- O formulário de agendamento valida cron, mostra o próximo disparo e explica
  cada campo.
- Nenhuma tabela renderiza header sem corpo nem empty state.
