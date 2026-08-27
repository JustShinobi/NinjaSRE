# D3 — As telas que decidem o produto

Cinco telas carregam a impressão inteira. As outras nove são variações delas.
Os mockups navegáveis estão no artifact que acompanha estas specs; aqui ficam as
decisões e o porquê de cada uma.

---

## 1. Painel — a primeira tela, cheia ou vazia

**Três faixas, nesta ordem:**

1. **O que precisa de você.** Aprovações pendentes, mudanças propostas, origens
   que pararam de entregar. Se não houver nada, a faixa some — é a única que
   pode sumir.
2. **O que está acontecendo.** Incidentes abertos e investigações correndo, com
   movimento real enquanto correm.
3. **Como temos ido.** Investigações, taxa de conclusão, tempo até a causa. Trinta
   dias.

**Num deployment novo, as três aparecem com números zerados**, e a checklist de
primeiros passos ocupa a coluna da direita com o passo pendente clicável. O
produto aparece; o que falta é dito dentro dele.

**A ação principal — investigar — fica no cabeçalho, sempre.** Não atrás de um
menu, não só quando há incidente. É a coisa que o produto faz.

> **Decisão revisada.** A primeira versão da spec 052 redirecionava um deployment
> novo para uma rota de configuração, bloqueando o painel. Está errado:
> esconde o produto de quem ainda está decidindo se vai usá-lo.

---

## 2. Investigação — a tela que prova a tese

É aqui que "investiga com evidência" é verdade ou é marketing. Três colunas:

**Esquerda — o que foi perguntado.** O alerta ou a descrição, o recurso, o
instante, e o que já se sabia sobre esse recurso antes de começar.

**Centro — o raciocínio, enquanto acontece.** Cada passo é uma linha: qual
subagente, que ferramenta chamou, contra qual origem, e o que voltou. Expansível
para o dado bruto. **Streaming de verdade** — a rota já existe.

Duas regras aqui, e são as que fazem esta tela valer:

- **Toda afirmação carrega sua origem, visível sem clique.** "Uso de memória em
  94%" sozinho é uma alegação; com `pve-exporter · vmid 115 · 14:31` é evidência.
- **O que falhou aparece.** Uma consulta que voltou vazia, uma origem fora do ar,
  uma ferramenta sem integração configurada — tudo na mesma trilha. Uma
  investigação que só mostra o que deu certo está escondendo por que a conclusão
  é fraca.

**Direita — a conclusão.** Causa raiz com confiança declarada, evidência ligada
de volta aos passos, e o que se propõe fazer — nunca executado sem decisão
enquanto o dry-run estiver ligado.

**Rodapé — a linha do tempo com a mudança sobreposta** (spec 057). O deploy que
aconteceu treze minutos antes do erro, na mesma régua. É a resposta visual à
pergunta que se faz primeiro.

---

## 3. Recursos — o estate, e o que ele significa

57 containers em sete zonas. Uma tabela plana é inútil; uma árvore é lenta.

**Padrão: agrupado por zona, ordenado por criticidade, denso.** As colunas que
importam: nome, zona, criticidade, estado, o nó, e quando foi visto pela última
vez. Filtro por zona e por criticidade em um clique.

**Divergência é conteúdo, não erro.** Um recurso que sumiu do Proxmox mas está no
inventário, ou apareceu sem estar, entra na lista marcado — não some e não vira
alerta. É informação sobre o estate (spec 053).

O detalhe de um recurso abre com o que o produto sabe dele em um lugar: sinais
disponíveis e de onde vêm, documentos que o mencionam, investigações passadas,
mudanças recentes que o tocaram.

---

## 4. O agente — o que ele é, o que pode, o que fará sozinho

Três abas, respondendo às três perguntas da spec 060.

**Topologia** — o grafo hierárquico: o orquestrador, os sub-orquestradores, os
especialistas. Estado no próprio nó, clique para configurar. Uma visão em texto
estruturado ao lado, para quem prefere editar o documento.

**Ferramentas** — agrupadas pela única distinção que muda o risco: **as que leem
e as que escrevem**. Cada uma com a integração que exige e se ela está
configurada. Ferramenta sem integração aparece apagada com o motivo — é a
explicação para uma investigação que não chegou a lugar nenhum.

**Autonomia** — em texto, o que aconteceria com cada classe de ação sob a
política atual. O kill switch fica alcançável de qualquer tela, não aqui dentro:
engajá-lo é o que se faz quando algo está errado, e nesse momento ninguém procura
submenu.

**O modelo não é fixado por etapa.** Existem oito papéis de modelo, cada um com
provider próprio, e a tela mostra o papel. Uma interface que exibe o
identificador de um fornecedor ao lado de cada agente assume o que o deployment
escolheu.

---

## 5. Dados — de onde veio, para onde vai

A seção da spec 062, e a tela que mais se beneficia de ser desenhada como
**trânsito** e não como formulário.

**Layout em três colunas, na direção do fluxo:**

```
   ENTRADA              ROTEAMENTO             SAÍDA
   Alertmanager ──┐
   Grafana ───────┼──▶  regras, em ordem  ──▶  destinos
   Webhook ───────┘     (a que casou fica       por evento
                         destacada)              e detalhe
```

Cada origem mostra **a última entrega e quando** — verde se chegou algo na
janela, apagado se nunca chegou. Uma origem configurada que nunca entregou é a
falha mais cara desta categoria porque é silenciosa, e aqui ela é a coisa mais
visível da tela.

**Simulação no lugar onde a regra se edita.** Colar um payload, ver qual regra
pega, para qual equipe vai, o que dispara — antes de salvar.

**A última regra é sempre visível**, e o que ela faz com o que não casou é
escolha explícita.

---

## O que vale para todas

- **Nada que decide comportamento é salvo sem mostrar o efeito.** Preview de
  configuração, dry-run de detector, explain de autonomia, simulação de
  roteamento — o mecanismo já existe em todos os casos.
- **Origem em toda afirmação.** Configuração mostra de qual nível o valor veio;
  investigação mostra de qual consulta o número veio; entrega mostra por qual
  rota o alerta entrou.
- **Falha é conteúdo do painel, nunca da rota.**
- **Segredo não aparece.** Nem mascarado, nem em atributo, nem em erro. Campo de
  credencial é somente-escrita.
