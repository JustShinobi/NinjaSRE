# Tasks: Confiança de certificado

**Input**: Design documents from `specs_v7/070-confianca-de-certificado/`

**Prerequisites**: spec.md, plan.md. Nenhuma feature desta onda é pré-requisito;
a 070 roda no slot S3 em paralelo com a 030.

**Tests**: test-first, sem exceção nesta feature. Cada tarefa de comportamento
tem um teste que aterrissa antes, é rodado, e o vermelho é **registrado** no
`controle.md` com a mensagem da falha. Uma mudança de fronteira de segurança
validada só depois do fato não distingue "está certo" de "o teste não olha".

## Regras que valem para toda tarefa deste arquivo

1. **Nada de identificador de planejamento em arquivo committed.** Nenhum teste,
   comentário, docstring, documento gerado ou mensagem de commit cita
   identificador de requisito, número de artigo, número de feature ou caminho de
   diretório de planejamento. A substância vai no arquivo; a referência fica
   nesta spec.
2. **Esta feature não é dona dos arquivos de escrita única.** Não editar
   `console/src/i18n/*.ts`, `console/src/shell/routes.ts` nem
   `console/visual/screens.json`. Chave nova é declarada no relatório final e
   referenciada no código; o merge do slot aplica. Editar um deles devolve o
   trabalho para reparo.
3. **Nenhuma tarefa toca outro diretório de feature.**
4. **Segredo nunca em log nem em auditoria.** Fingerprint pode. PEM, chave
   privada, token, ticket e senha, jamais. Toda tarefa que escreve um registro
   confere isto no próprio teste.
5. **Não existe caixa de seleção.** Se em algum momento a implementação
   introduzir um campo booleano que desligue verificação, o desenho saiu do
   trilho: pare e reporte.
6. **Um lugar só pode não verificar.** Se a implementação precisar de um segundo,
   pare e reporte em vez de abrir o segundo.
7. **A ordem é a do plano.** Vocabulário antes de aplicação, aplicação antes de
   escrita, escrita antes de composição, composição antes de staging.

---

## Phase 0: Linha de base

- [x] **T001** Rodar `make verify` na árvore intacta e guardar o log **fora do
      repositório**. Registrar no `controle.md`: exit code, contagem de testes,
      e qualquer falha preexistente. Sem esta linha de base, uma falha
      preexistente é debitada desta feature e uma falha desta feature se esconde
      atrás de "já estava assim". Se não estiver verde, parar e reportar antes de
      escrever qualquer teste.

- [x] **T002** Registrar o estado de partida do Proxmox no staging, lido do
      ambiente e não de um documento: o veredito atual da integração, a mensagem
      exata que o painel mostra, e a contagem
      `select count(*) from estate_resources where source='proxmox' and absent_since is null;`.
      Esses três fatos são o "antes" contra o qual o critério de pronto é medido.

---

## Phase 1: O vocabulário desce um tier

- [x] **T003** [Teste] Rodar a suíte de transporte do Proxmox que já existe e
      registrar que ela está verde. Ela é a rede de segurança desta fase: nenhum
      dos seus casos pode ser alterado, e todos têm de continuar passando sem
      edição depois da mudança. Uma suíte de segurança que foi "ajustada" para
      continuar passando não provou nada.

- [x] **T004** [Teste] Escrever, em `tests/unit/platform/credentials/`, o teste
      do vocabulário de confiança no tier do proxy: as quatro formas, o padrão
      sendo o seguro, a construção de "não verificado" exigindo razão e
      identidade não vazias, a recusa de valor sem cabeçalho de certificado, a
      recusa nominal de valor com cabeçalho de chave privada, as duas grafias de
      fingerprint aceitas, o conjunto de fingerprints, e a lista de endereços que
      a declaração nomeia. Confirmar vermelho — o módulo ainda não existe.

- [x] **T005** Criar `platform/credentials/proxy/trust.py` com o vocabulário. É a
      forma que hoje vive no pacote Proxmox, generalizada em três pontos: o
      fingerprint vira conjunto, a declaração carrega os endereços para os quais
      vale, e a prosa deixa de falar de um vendor específico e passa a falar do
      componente que aplica. Preservar integralmente: o padrão ser verificar, a
      impossibilidade de construir "não verificado" sem razão e identidade, o erro
      próprio para essa tentativa, a descrição de uma linha para um relatório, e o
      registro de auditoria sem material de certificado.

- [x] **T006** Reescrever `integrations/proxmox/certificates.py` como declaração
      sobre o vocabulário comum: mantém o nome que exporta hoje, mantém o valor
      padrão do Proxmox, mantém a prosa que explica por que o plano de gestão de
      um hipervisor é o último lugar para ensinar que aviso de certificado é
      ruído. Rodar T003 de novo, sem editar um caso sequer.

- [x] **T007** Rodar as checagens de contrato de import. O tier do proxy não pode
      ter passado a importar o tier das integrações. Se passou, a mudança foi na
      direção errada.

---

## Phase 2: A recusa vira de primeira classe

- [x] **T008** [Teste] Em `tests/unit/platform/credentials/`, escrever o teste das
      razões de erro: certificado não confiado é uma razão distinta de upstream
      inalcançável; ela atravessa o motor sem virar outra coisa; ela vira um
      status próprio na resposta interna do proxy; e o desfecho da auditoria a
      registra como negada com a razão certa. Confirmar vermelho.

- [x] **T009** [Teste] Escrever o teste das três frases: não confiado nomeia o
      fingerprint observado; pin quebrado nomeia o esperado **e** o observado,
      identificados; nome que não confere nomeia o endereço configurado e o nome
      que o certificado carrega. E o teste negativo que é metade do ponto: a
      frase de rede indisponível não menciona certificado, e nenhuma das três
      menciona nó que não respondeu. Confirmar vermelho.

- [x] **T010** Acrescentar a razão e as três formas de recusa em
      `platform/credentials/proxy/errors.py`, e o status correspondente no mapa
      de status do aplicativo do proxy. Escolher um status que um chamador que lê
      só o número ainda leve à ação certa, e escrever no código por que aquele —
      um certificado recusado não é "o vendor não respondeu".

- [x] **T011** Fazer a razão nova atravessar `engine.py` sem ser reembalada.
      Conferir no teste que o achatamento genérico de exceção do envio não a
      captura: ela já é um erro do proxy e tem de subir como está.

---

## Phase 3: A aplicação, no remetente

Esta é a fase de maior risco técnico. Ela vem antes de qualquer campo de
configuração de propósito: se pinar não funcionar, é melhor descobrir agora do
que depois de três camadas de carregamento prontas.

- [x] **T012** [Teste] Em `tests/contract/` (contrato do proxy), escrever o teste
      dos três modos contra um servidor TLS **local**, com certificado e
      autoridade gerados dentro do próprio teste — sem rede, sem fixture binária
      no repositório, sem chave privada committed. Os quatro casos:
      (a) sem declaração, contra certificado desconhecido ⇒ recusa por
      certificado;
      (b) fingerprint correto ⇒ a chamada chega e volta;
      (c) certificado de autoridade fornecido ⇒ a chamada chega e volta;
      (d) não verificado, declarado com razão e identidade ⇒ a chamada chega e
      volta.
      Confirmar vermelho.

- [x] **T013** [Teste] No mesmo lugar, o teste do pin quebrado: fingerprint
      declarado diferente do apresentado ⇒ recusa; repetir a chamada ⇒ recusa de
      novo, sem degradar para o repositório do sistema nem para não verificado; a
      declaração lida depois continua sendo a que o operador escreveu. E o caso
      de cluster: três fingerprints declarados, um nó trocando de certificado ⇒ só
      as chamadas àquele nó recusam. Confirmar vermelho.

- [x] **T014** [Teste] O teste do nome que não confere: autoridade fornecida que
      valida a cadeia, endereço configurado que o certificado não nomeia ⇒ a
      terceira mensagem, não a primeira. Confirmar vermelho.

- [x] **T015** [Teste] O teste de que o padrão não afrouxou: sem declaração e sem
      bundle nomeado, o contexto continua tão estrito quanto a biblioteca é —
      incluindo a conformidade que hoje só é relaxada quando existe bundle. O
      afrouxamento acompanha o certificado fornecido pela configuração e nada
      além dele. Confirmar vermelho ou verde conforme o caso, e registrar qual.

- [x] **T016** Implementar em `gateway/proxy/sender.py` a resolução de contexto
      por endereço: o remetente deixa de ter um contexto e passa a receber um
      registro de confiança do qual deriva o contexto do endereço de cada
      chamada. Requisitos de forma:
      - o contexto de um endereço é construído uma vez e reaproveitado, não por
        requisição;
      - um endereço sem declaração recebe o contexto padrão de hoje, intacto;
      - a verificação de fingerprint compara o SHA-256 do certificado
        apresentado com o conjunto declarado, e é ela quem substitui a
        verificação de identidade quando há pin;
      - a captura de erro de TLS deixa de ser achatada junto com falha de rede —
        é essa linha que hoje confunde as duas.

- [x] **T017** Registrar no `controle.md` a decisão de forma que a pinagem com a
      biblioteca padrão exigiu, e por quê. Se ela for feia, ela é feia e
      documentada; o que não pode acontecer é ela virar "então não verifica".

---

## Phase 4: A declaração na configuração

- [x] **T018** [Teste] Em `tests/unit/platform/config_service/`, escrever o teste
      da seção de confiança na entrada de integração: as quatro formas; o padrão
      quando ausente; a recusa nomeada de "não verificado" sem razão; a recusa
      nomeada sem identidade; a recusa de cabeçalho de chave privada; a ausência
      de qualquer booleano de desligar verificação (o documento é fechado, então
      escrever um campo desses é recusado, não ignorado); os endereços que a
      declaração nomeia. Confirmar vermelho.

- [x] **T019** Acrescentar a seção em
      `platform/config_service/schema/integrations.py`, tipada e fechada, ao lado
      do endereço. Escrever no próprio arquivo por que um certificado público
      pode viver ali e uma chave privada não.

- [x] **T020** [Teste] O teste da varredura de valor com forma de segredo que o
      documento já faz: um PEM de certificado **não** é recusado por ela; um bloco
      de chave privada **é**. Confirmar vermelho e implementar o que faltar.

---

## Phase 5: Quem pode

- [x] **T021** [Teste] Em `tests/unit/platform/identity/`, escrever o teste da
      permissão dedicada: ela existe, é distinta da de gerir integração, é
      classificada como escrita pela derivação por verbo (e não por uma segunda
      lista), não está no conjunto do papel que apenas opera integrações, e está
      no conjunto administrativo e acima. Confirmar vermelho.

- [x] **T022** Acrescentar a permissão em `platform/identity/permissions.py` e ao
      conjunto do papel administrativo. Escrever no arquivo, em uma ou duas
      frases, por que pinar não exige esta permissão e não verificar exige — a
      distinção é o desenho, e sem ela alguém a "simplifica" no próximo release.

- [x] **T023** [Teste] Em `tests/contract/` (rota de integrações), escrever o
      teste do portão: sem a permissão, aceitar não verificado é recusado
      nomeando a permissão e **nada** é gravado — nem o endereço, nem a
      credencial, nem parte da declaração; com a permissão e sem razão, recusado
      nomeando o que falta; com as duas, gravado. E o teste que fecha a porta
      lateral: uma identidade de "quem aceitou" enviada no corpo da requisição é
      ignorada, e o que fica gravado é o principal autenticado. Confirmar
      vermelho.

---

## Phase 6: A escrita, o registro, e a sobrevivência do campo

- [x] **T024** [Teste] O teste que a experiência desta base de código pede: gravar
      uma declaração de confiança, depois gravar um endereço pela rota normal, e
      conferir que a declaração continua lá. A função que reescreve a lista de
      entradas copia um conjunto fixo de campos, e um campo novo que não entre
      nessa lista é apagado no primeiro salvamento seguinte. Confirmar vermelho.

- [x] **T025** Implementar a escrita em `gateway/http/integration_endpoints.py`,
      no mesmo formato do endereço: upsert na entrada da integração, no nó da
      organização, lista inteira reescrita. Incluir o campo novo na cópia da
      entrada — é o que T024 cobra.

- [x] **T026** [Teste] O teste do evento de auditoria da escrita: um evento por
      declaração, com principal autenticado, instante do servidor, integração,
      endereços, forma, fingerprints quando há, razão quando há. E a asserção
      negativa: nenhum cabeçalho de certificado, nenhum cabeçalho de chave
      privada, nenhum token no payload. Confirmar vermelho.

- [x] **T027** Emitir o evento na rota, com a ação e o tipo de recurso nomeados
      em `config/constants/security.py` — nomeados lá pelo mesmo motivo que os
      outros: uma ação escrita à mão no ponto de chamada é uma ação que a consulta
      de auditoria não encontra.

- [x] **T028** [Teste] O teste dos dois escalares novos na linha de resolução:
      forma em vigor sempre, fingerprint quando pinada; e numa recusa por
      certificado, o desfecho negado com a razão nova e o fingerprint
      **observado**. Conferir que o registro continua fechado — que não há
      caminho para um ponto de chamada acrescentar um campo. Confirmar vermelho.

- [x] **T029** Implementar os dois campos em `platform/credentials/proxy/audit.py`
      e preenchê-los em `engine.py`.

- [x] **T030** [Teste] O teste da invalidação por troca de endereço: declaração
      feita para um endereço, endereço trocado, chamada ao novo ⇒ recusa por
      certificado até nova decisão. E o caso irmão: acrescentar endereço não
      estende a ele uma aceitação de "não verificado" existente. Confirmar
      vermelho.

---

## Phase 7: Composição — sem isto, nada do acima existe em produção

- [x] **T031** [Teste] Em `tests/unit/gateway/proxy/`, escrever o teste da
      composição: o motor construído por `build_proxy_engine` tem um remetente que
      recebeu um registro de confiança, e não um remetente com contexto único. É
      o teste que impede esta feature de ser mais uma escrita e não composta.
      Confirmar vermelho.

- [x] **T032** Passar o registro em `gateway/proxy/composition.py`. O remetente
      não pode conseguir um registro por outro caminho: a composição é a única
      maneira.

- [x] **T033** [Teste] O teste da leitura da configuração: a confiança sai da
      árvore junto com os hosts, na mesma leitura; uma declaração que nomeia
      integração não instalada é ignorada e registrada; uma declaração removida
      deixa de valer no ciclo seguinte porque o ciclo reconstrói em vez de
      acumular. Confirmar vermelho.

- [x] **T034** Implementar a leitura em `gateway/proxy/hosts.py`, ao lado da
      leitura de host que já está lá, e ligar no ciclo de
      `gateway/proxy/__main__.py`. Um ciclo, uma leitura, os dois reconstruídos
      juntos.

- [x] **T035** [Teste] O teste de resiliência que o ciclo já promete: uma
      configuração ilegível deixa o que está em vigor em vigor e registra a
      falha, em vez de recusar todas as chamadas. Confirmar vermelho ou verde e
      registrar qual.

---

## Phase 8: Onde o operador lê

- [x] **T036** [Teste] Escrever o teste do braço novo na tabela de mensagens do
      verificador Proxmox: a razão de certificado tem sua frase, e a frase de
      "nenhum nó respondeu" deixa de ser o que aparece para um problema de
      certificado. Confirmar vermelho.

- [x] **T037** Acrescentar o braço em `integrations/proxmox/verifier.py`.

- [x] **T038** Fazer a verificação profunda relatar em uma linha a forma de
      confiança em vigor (`gateway/http/deep_verification.py`), reusando a
      descrição de uma linha que o vocabulário já produz.

- [x] **T039** [Teste] Em `console/tests/unit/`, o teste do painel: os campos de
      confiança aparecem pelo mecanismo de campos declarados; a ação de aceitar
      não verificado exige razão escrita e não é uma caixa de seleção; quem não
      tem a permissão não a vê disponível; e a frase da recusa exibida é a que o
      servidor mandou, não uma genérica. Confirmar vermelho.

- [x] **T040** Implementar no painel da integração, sem componente novo. As
      chaves de i18n usadas são referenciadas no código e **declaradas no
      relatório final** — não editar o catálogo.

- [x] **T041** Atualizar `integrations/proxmox/docs.md`: além das três formas
      programáticas que já documenta, o caminho de configuração — onde se declara,
      qual permissão cada forma exige, o que a auditoria grava, e o que acontece
      quando o certificado do nó muda. Manter a documentação em inglês e
      autocontida.

---

## Phase 9: As garantias que precisam de teste próprio

- [x] **T042** [Teste] Arquitetura: existe exatamente **um** lugar na árvore capaz
      de construir um contexto TLS que não verifica, e ele é o remetente do
      proxy. O teste falha nomeando o arquivo se aparecer um segundo.

- [x] **T043** [Teste] Arquitetura: nenhum schema de credencial, de configuração
      ou de capacidade tem campo booleano que desligue verificação.

- [x] **T044** [Teste] Nenhuma capacidade do catálogo lê ou escreve declaração de
      confiança.

- [x] **T045** [Teste] A política de rede dos sandboxes é idêntica à de antes
      desta feature — sandbox não fala com o proxy e isso não mudou. "Não
      mexemos" não é evidência.

- [x] **T046** Rodar `make verify` inteiro e comparar com a linha de base de T001.
      Verde partindo de verde, e a comparação é a evidência.

---

## Phase 10: Staging — o critério de pronto

Roda depois do merge do slot, pelo ciclo do protocolo da onda. Os itens abaixo
são **read-only** contra o ambiente compartilhado: declarar confiança e ler.
Nada nesta feature escreve no hipervisor.

- [x] **T047** Declarar a confiança do Proxmox real pela interface do staging.
      Tentar o **fingerprint primeiro** — o certificado nomeia o nó, e se a
      integração estiver apontada para um endereço IP o certificado fornecido vai
      falhar a verificação de nome. Se a terceira mensagem aparecer, ela é o
      caminho esperado e a evidência dela vale tanto quanto a do sucesso.

- [x] **T048** Verificar a integração e capturar a evidência: o veredito, a
      mensagem, e a captura de tela do painel.

- [x] **T049** Rodar a descoberta e conferir que o estate povoou:
      `select count(*) from estate_resources where source='proxmox' and absent_since is null;`
      maior que zero, comparado com o "antes" de T002.

- [x] **T050** Conferir a aceitação registrada:
      `select occurred_at, actor_kind, actor_id, outcome, detail from audit_events where resource_kind='integration' and resource_id='proxmox' order by occurred_at desc limit 10;`
      — o principal autenticado, o instante, a forma, os endereços, a razão
      quando há.

- [x] **T051** Quebrar o pin de propósito: declarar um fingerprint que não
      corresponde, provocar uma chamada, e capturar a mensagem. Ela tem de conter
      os dois fingerprints e não conter a frase de nó que não respondeu.
      Restaurar em seguida a declaração correta.

- [x] **T052** Conferir que nada sensível vazou:
      `select count(*) from audit_events where detail::text like '%BEGIN CERTIFICATE%' or detail::text like '%PRIVATE KEY%' or detail::text like '%PVEAPIToken%';`
      — esperado zero. Repetir a varredura nos logs do pod do proxy.

- [x] **T053** Escrever o relatório final com: as chaves de i18n e os textos em
      inglês como bloco para o merge aplicar; a permissão nova e a quem foi
      concedida; as decisões de forma que a implementação exigiu; e o que ficou
      como pergunta para o operador.
