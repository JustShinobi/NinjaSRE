# Specification Quality Checklist: Confiança de certificado

**Purpose**: Validar completude e qualidade da especificação antes do planejamento
**Created**: 2026-08-23
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] Sem detalhe de implementação (linguagem, framework, API) na spec — as
      escolhas de módulo e de tipo estão no plan, que é onde elas pertencem
- [x] Focada em valor para o operador e na decisão de fronteira
- [x] Escrita para quem decide, não só para quem implementa
- [x] Todas as seções obrigatórias preenchidas

## Requirement Completeness

- [x] Nenhum marcador [NEEDS CLARIFICATION] restante — as questões que restam são
      operacionais e estão listadas em Notes, não escondidas dentro de um FR
- [x] Requisitos testáveis e sem ambiguidade
- [x] Critérios de sucesso mensuráveis
- [x] Critérios de sucesso agnósticos de tecnologia
- [x] Todos os cenários de aceitação definidos
- [x] Casos de borda identificados
- [x] Escopo claramente delimitado
- [x] Dependências e premissas identificadas
- [x] Cada requisito é atômico — uma vírgula é fronteira de requisito, e nenhum
      requisito carrega duas obrigações separadas por vírgula

## Feature Readiness

- [x] Todo requisito funcional tem critério de aceitação claro
- [x] Os cenários de usuário cobrem os fluxos primários
- [x] A feature atende os resultados mensuráveis dos critérios de sucesso
- [x] Nenhum detalhe de implementação vazou para a especificação

## Verificações de fronteira de segurança (específicas desta feature)

- [x] **Quem pode aceitar não verificado está decidido**, não deixado para a
      implementação: permissão dedicada, distinta da de gerir integração, com o
      rationale de por que pinar não a exige e não verificar exige
- [x] **O escopo da aceitação está decidido com rationale**: por endereço, não
      por vendor, e a consequência de um PEM de autoridade cobrir o cluster está
      escrita em vez de descoberta depois
- [x] **O que a auditoria grava está enumerado campo a campo** — quem, quando,
      integração, endereços, forma, fingerprint, razão — e o que ela nunca grava
      também
- [x] **Pin quebrado tem comportamento declarado**: recusa nomeando o
      fingerprint novo, sem fallback silencioso e sem adoção automática
- [x] **`unverified` continua exigindo razão e identidade em todo o caminho** —
      no vocabulário, na validação do documento, na rota de escrita e na tela
- [x] **A ausência de booleano é um requisito**, não uma convenção: nenhum campo
      que desligue verificação existe em nenhum schema
- [x] **A identidade de quem aceitou vem do servidor**, e um valor vindo do
      cliente é ignorado — está como requisito e como cenário de aceitação
- [x] **As duas mensagens de falha nunca se confundem** está como requisito
      positivo (a frase de certificado nomeia o fingerprint) e negativo (a frase
      de rede não menciona certificado)
- [x] A terceira mensagem — nome que não confere — foi identificada como caso
      real do staging e não foi achatada nas outras duas
- [x] **Fingerprint pode ser logado; chave e token jamais** está escrito nos dois
      sentidos, com a consulta que prova
- [x] **A decisão Proxmox-first × carrier genérico está tomada** no plan, com
      rationale, e o limite de não sobre-entregar está no Out of Scope: nenhum
      outro pacote de integração é alterado
- [x] O critério de pronto é o Proxmox real conectando, e não um mecanismo
      habilitado no catálogo inteiro
- [x] O que **não** muda está declarado: sandbox, política de rede, caminho
      sancionado do cliente, bundle de autoridade por ambiente
- [x] Existe teste de contrato do proxy para os três modos, e o pin quebrado tem
      o seu

## Verificações de forma da onda

- [x] A feature declara que **não é dona** dos arquivos de escrita única no slot
      S3, e que entrega chaves de i18n como bloco no relatório
- [x] O plan declara **qual composition root constrói** o mecanismo, com nome de
      arquivo e função, e o tasks.md tem tarefa explícita de composição com prova
      no caminho de serving
- [x] O DoD inclui **contagens no banco de staging**, com as consultas exatas
      escritas na spec
- [x] Os acceptance de staging estão marcados como read-only (declarar e ler;
      descoberta é leitura)
- [x] Test-first: o vermelho aterrissa antes da implementação em toda fase de
      comportamento, e o registro do vermelho é tarefa

## Notes

- Esta é a feature sensível da onda. O critério de revisão não é "os requisitos
  estão completos", é **"a fronteira ficou melhor desenhada do que estava"**. A
  resposta que a spec sustenta: antes, verificação era binária por processo e
  impossível de afrouxar sem editar código; depois, ela é declarável por
  endereço, a forma que afrouxa exige permissão dedicada, razão e registro, e o
  lugar capaz de afrouxar continua sendo um só — agora com teste que prova que é
  um só.
- O maior risco técnico está no plan e não escondido aqui: verificar fingerprint
  com a biblioteca padrão é o único ponto com forma não óbvia. Ele foi colocado
  cedo na sequência de propósito, para falhar antes de três camadas de
  carregamento existirem.
- **Perguntas em aberto para o operador** — nenhuma bloqueia a geração, e todas
  têm um padrão declarado que segue valendo se não houver resposta:
  1. **O papel administrativo é o certo para a permissão nova?** O padrão é
     administrador e acima, com o operador de integrações **fora**. Se o
     deployment do homelab é operado por uma pessoa só que não usa o papel
     administrativo no dia a dia, isso vira atrito toda vez; o padrão continua
     sendo o defensável e a exceção é uma concessão de papel, não uma mudança de
     desenho.
  2. **O Proxmox do staging está apontado por nome ou por endereço IP?** Se for
     IP, o certificado fornecido vai falhar a verificação de nome e o caminho
     bom é o fingerprint. A tarefa de staging já tenta o fingerprint primeiro por
     causa disso, mas saber a resposta antes economiza um ciclo.
  3. **O cluster tem quantos nós que este deployment vai alcançar?** Um nó
     favorece fingerprint; vários favorecem o PEM da autoridade do cluster. A
     spec suporta os dois e a recomendação por caso está no plan.
  4. **Existe alguma integração além do Proxmox que hoje falha por certificado?**
     Se existir, ela não entra nesta feature — mas saber disso muda a prioridade
     de estender a declaração para outro pacote na onda seguinte.
