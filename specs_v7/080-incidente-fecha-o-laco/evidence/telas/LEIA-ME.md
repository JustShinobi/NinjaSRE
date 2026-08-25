# As telas, e qual estação cada uma serve

Capturas **full-page a 1920 de largura**, contra o staging real
(`stg-ninjasre.lan.kyo.ninja`), em 2026-08-25, pela suíte transversal com o
backing de staging. Cinco arquivos, não oito: **uma tela serve mais de uma
estação quando é a mesma tela**, e copiar o mesmo pixel sob três nomes faria
este diretório parecer três medições onde houve uma.

| arquivo | estações que ele serve | o que se lê nele |
|---|---|---|
| `incidents-list.png` | E3 (lista) | a coluna `DETECTOR` dizendo `alertmanager` em toda linha, o estado real por incidente, e nenhum título que seja identificador |
| `incident-detail.png` | E2, E3 (detalhe), E10 | a entrega autenticada, o sujeito, o título, e o desfecho — as três estações leem a mesma tela, em momentos diferentes do laço |
| `run-detail.png` | E4, E5 | o transcript com as chamadas e o que cada uma devolveu, o custo por turno, e o relato renderizado como documento |
| `decisions.png` | E7 | a fila de decisões, vazia, dizendo a própria causa |
| `dashboard.png` | — | a tela inicial, para contexto |

## O que estas capturas **não** são

Elas são de **2026-08-25**, depois do laço, não de dentro dele. Para uma
alegação sobre **o que uma estação mostrava no seu instante**, a captura válida
é a de `../demo-2026-08-24/`, tirada durante a execução — mais estreita (1280)
e correta no tempo. Para uma alegação sobre **largura, transbordo ou o que cabe
na tela**, a captura válida é esta, que está na resolução que a especificação
declara.

Nenhuma das duas substitui a outra, e é por isso que as duas ficam.

## Duas estações sem captura dedicada, nomeadas em vez de omitidas

- **E6 — as ferramentas oferecidas.** A rota do agente não está no varrimento
  transversal, então não há captura dela aqui. A evidência desta estação é
  outra e é mais forte: a gravação do próprio run, com `ranked 60, offered 40,
  cut by the ceiling 20` e o escore de cada candidata, em
  `../demo-2026-08-24/T041-ferramentas-oferecidas.md`.
- **E8, E9, R — aprovar, executar, rejeitar.** Não foram exercidas, então não
  há tela para capturar. A razão está em `../EVIDENCIA.md` §4 e §7, e não é
  omissão.

## Os arquivos com nome de teste

Os `e2e-transversal-rules-spec-ts-*.png` são a saída bruta do varrimento, um
por rota e por regra, com o nome que o próprio arnês dá. Ficam porque são o que
o comando produziu; os cinco acima são os mesmos pixels sob o nome da estação.
