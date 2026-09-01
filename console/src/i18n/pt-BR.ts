import type { MessageKey } from './en';

/**
 * Brazilian Portuguese.
 *
 * Typed as partial on purpose. A total type would make the completeness test
 * unfailable — the compiler would refuse an incomplete catalogue, and a test
 * that cannot fail is a test that proves nothing about the day somebody adds a
 * key in a hurry. So the type permits a gap, the runtime falls back per key, and
 * `tests/unit/i18n/catalogue.test.ts` names any gap that is left.
 */
export const PT_BR: Partial<Record<MessageKey, string>> = {
  'app.name': 'NinjaSRE',
  'app.skipToContent': 'Ir para o conteúdo',

  'nav.label': 'Áreas',
  'nav.group.now': 'Agora',
  'nav.group.environment': 'Ambiente',
  'nav.group.settings': 'Configuração',
  'nav.firstRun': 'Configuração inicial',
  'nav.dashboard': 'Painel',
  'nav.incidents': 'Incidentes',
  'nav.runs': 'Investigações',
  'nav.decisions': 'Decisões',
  // Mantidas para as áreas que a reorganização dobrou dentro de uma aba de
  // outra tela: a frase de um link cruzado ainda precisa de um nome para a
  // tela que ele aponta, mesmo sem entrada própria no menu.
  'nav.approvals': 'Ações aguardando aprovação',
  'nav.proposals': 'Mudanças propostas',
  'nav.resources': 'Recursos',
  'nav.topology': 'Topologia',
  'nav.detectors': 'Detectores',
  'nav.memory': 'Memória',
  'nav.knowledge': 'Conhecimento',
  'nav.integrations': 'Integrações',
  'nav.integrationsNotCovered': 'Não coberto, e por quê',
  'nav.signals': 'Sinais',
  'autonomy.level.propose_only':
    'Apenas propor — toda ação é registrada para uma pessoa aprovar. Nada roda sem isso.',
  'autonomy.level.act_on_low_risk':
    'Agir em baixo risco — roda sozinho até o limite de risco escolhido; o que for mais arriscado continua esperando uma pessoa.',
  'autonomy.level.act_and_report':
    'Agir e reportar — roda sozinho e avisa alguém depois, seja qual for o risco.',
  'autonomy.level.act_silently':
    'Agir em silêncio — roda sozinho e não reporta nada. Escolha este nível de propósito.',
  // As mesmas quatro posturas, na forma curta que um subtítulo ou um título
  // usa ao lado do nome de um nó — nunca a frase acima, que carrega seu
  // próprio ponto final e vira um fragmento quando outra oração a segue.
  'autonomy.level.propose_only.short': 'Apenas propor',
  'autonomy.level.act_on_low_risk.short': 'Agir em baixo risco',
  'autonomy.level.act_and_report.short': 'Agir e reportar',
  'autonomy.level.act_silently.short': 'Agir em silêncio',
  'nav.autonomy': 'Autonomia',
  'nav.catalogue': 'Catálogo',
  'nav.administration': 'Administração',
  'nav.configuration': 'Configuração',
  'nav.teamContext': 'Contexto da equipe',
  'nav.audit': 'Auditoria',
  'nav.data': 'Dados',
  'nav.open': 'Abrir a navegação',
  'nav.close': 'Fechar a navegação',
  'nav.pending': '{count} aguardando',
  'nav.pending.decisions': '{count} decisões aguardando',
  'nav.pending.approvals': '{count} ações aguardando aprovação',
  'nav.pending.proposals': '{count} propostas aguardando',
  'nav.pending.incidents': '{count} incidentes abertos',
  'nav.pending.runs': '{count} investigações falhadas',

  'page.firstRun.title': 'Configuração inicial',
  'page.firstRun.context':
    'O que configurar, em ordem, com a razão de cada passo e a opção de parar depois de qualquer um deles.',
  'credential.submit': 'Salvar esta credencial',
  'credential.sending': 'Salvando…',
  'credential.stored': 'Guardada no cofre. Nunca é mostrada de novo.',
  'credential.absent': 'Esta não declara nenhum campo de credencial.',
  'credential.whereToGetIt': 'Onde obter:',
  'credential.required': 'Todo campo obrigatório precisa de um valor.',
  'credential.saved': 'Guardada. Nada do que você digitou fica aqui.',
  'credential.minScope': 'Permissão mínima:',
  'credential.guide': 'Guia passo a passo',

  'firstRun.wizard.position': 'Passo {n} de {total} — {name}',
  'firstRun.wizard.pending.one': '{count} passo faltando',
  'firstRun.wizard.pending': '{count} passos faltando',
  'firstRun.steps.title': 'O que falta',
  'firstRun.steps.done': 'Tudo pronto',
  'firstRun.progress': '{left} de {total} passos faltando',
  'firstRun.steps.empty.heading': 'Este deployment não disse o que falta',
  'firstRun.steps.empty.body':
    'Esta tela é desenhada a partir da checklist de configuração do próprio deployment, e ela não respondeu. O resto do console não é afetado.',
  'firstRun.steps.empty.action': 'Ir para a visão geral',
  'firstRun.refused': 'O deployment recusou:',
  'firstRun.unreachable': 'Não foi possível alcançar o deployment.',

  'firstRun.step.provider': 'Escolher um provider de modelo',
  'firstRun.step.credential': 'Salvar a credencial dele',
  'firstRun.step.model': 'Escolher um modelo',
  'firstRun.step.integrations': 'Conectar o que ele pode consultar',
  'firstRun.step.verify': 'Verificar que cada coisa funciona',
  'firstRun.step.estate': 'Dar a ele um parque para observar',
  'firstRun.step.alerts': 'Apontar seus alertas para ele',
  'firstRun.step.here': 'Você está aqui',
  'firstRun.step.onScreen': 'Continua em {screen}',

  'firstRun.why.provider':
    'Nada pode ser verificado sem um, e a plataforma se recusa a iniciar sem um configurado. Os nove são oferecidos nos mesmos termos, incluindo o que roda no seu próprio hardware.',
  'firstRun.why.credential':
    'O valor vai direto para o cofre. Não é escrito em configuração, não é devolvido, e nunca é mostrado de novo — nem mascarado.',
  'firstRun.why.model':
    'Com qual modelo este deployment pensa. Salvar pergunta ao deployment no que a mudança resultaria antes de fazê-la.',
  'firstRun.why.integrations':
    'Opcionais, todas elas. Um deployment com provider e sem integração ainda investiga — a partir do que lhe é contado em vez do que consegue consultar.',
  'firstRun.why.verify':
    'Não é opcional, e não é grátis: cada verificação faz uma requisição real. Uma credencial guardada e uma que funciona são os dois estados que você tenta distinguir às três da manhã.',
  'firstRun.why.estate':
    'O que transforma uma plataforma instalada numa que sabe do que é responsável.',
  'firstRun.why.alerts':
    'Os receptores existem. Nada aponta para eles ainda, então nada chega sozinho.',

  'firstRun.provider.local': 'Roda na sua própria infraestrutura',
  'firstRun.provider.hosted': 'Hospedado — as requisições saem da sua infraestrutura',
  'firstRun.provider.choose': 'Usar este provider',
  'firstRun.credential.chooseFirst': 'Nenhum provider foi escolhido ainda.',
  'firstRun.credential.checking': 'Perguntando ao provedor se esta chave funciona…',
  'firstRun.credential.accepted':
    'O provedor aceitou esta chave e listou os modelos abaixo.',
  'firstRun.credential.notListed':
    'A chave foi guardada, mas o provedor não quis listar o que serve:',
  'firstRun.credential.chooseModel': 'Com qual destes esta instalação pensa:',

  'firstRun.model.known': 'Modelo',
  'firstRun.model.free': 'Identificador do modelo',
  'firstRun.model.preview': 'O que isto mudaria?',
  'firstRun.model.previewing': 'Perguntando…',
  'firstRun.model.save': 'Salvar',
  'firstRun.model.saving': 'Salvando…',
  'firstRun.model.wouldChange': 'Salvar isto resultaria em:',
  'firstRun.model.nothingWouldChange': 'Nada mudaria: isto já é o que se aplica.',
  'firstRun.model.saved': 'Salvo.',
  'firstRun.model.needsPreview': 'Veja o que mudaria antes de salvar.',
  'firstRun.model.field.provider': 'Provedor',
  'firstRun.model.field.model': 'Modelo de investigação',

  'firstRun.integrations.search': 'Buscar no catálogo',
  'firstRun.integrations.none': 'Nada no catálogo corresponde a isso.',
  'firstRun.integrations.connected': 'Há uma credencial guardada para esta.',
  'firstRun.integrations.notConnected': 'Nada está guardado para esta.',
  'firstRun.integrations.optional':
    'Todas estas são opcionais, e uma que falhe não abandona as outras.',
  'firstRun.integrations.summary': 'Conectadas nesta sessão: {names}.',
  'firstRun.integrations.summaryNone': 'Nada foi conectado nesta sessão.',
  'firstRun.integrations.failed': 'Estas foram recusadas e podem ser tentadas de novo:',

  'firstRun.verify.check': 'Verificar',
  'firstRun.verify.checking': 'Verificando…',
  'firstRun.verify.retry': 'Verificar de novo',
  'firstRun.verify.nothing':
    'Nada está configurado ainda, então não há o que verificar. Guarde primeiro uma credencial de provider.',
  'firstRun.verify.remedy': 'O que fazer:',
  'firstRun.verify.findings': 'O que foi encontrado e n\u00e3o \u00e9 confi\u00e1vel:',
  'firstRun.verify.fix.provider': 'Escolher outro modelo',
  'firstRun.verify.fix.integration': 'Revisar a credencial',
  'firstRun.verify.fullDiagnosis': 'Diagn\u00f3stico completo',
  'firstRun.verify.fullDiagnosis.summary':
    'O resto do que o deployment relatou sobre esta verifica\u00e7\u00e3o.',
  'firstRun.verify.pending': '{count} de {total} ainda sem verifica\u00e7\u00e3o',
  'firstRun.verify.continueAnyway': 'Continuar mesmo assim',
  'firstRun.verify.latency': 'respondeu em {ms} ms',
  'firstRun.verify.footer.noneDegraded': 'nenhum degradado',
  'firstRun.verify.footer.degraded':
    '{count} verifica\u00e7\u00e3o(\u00f5es) degradada(s)',
  'firstRun.verify.footer.noneFailing': 'nenhum falhando',
  'firstRun.verify.footer.failing': '{name} est\u00e1 falhando',
  'firstRun.verify.continue': 'Continuar',
  'firstRun.verify.blockedBy': 'Impedido por:',

  'firstRun.established.title': 'O que já está configurado',
  'firstRun.established.empty.heading': 'Nada está configurado ainda',
  'firstRun.established.empty.body':
    'Tudo para o que este deployment tem credencial aparece aqui, com se algo realmente chegou lá. Ele não tem nenhuma, então ainda não consegue investigar.',
  'firstRun.established.empty.action': 'Escolher um provider de modelo',
  'firstRun.estate.integration':
    'O parque vem de {integration}, cuja credencial está guardada.',
  'firstRun.estate.check': 'Perguntar ao cluster o que este token pode fazer',
  'firstRun.estate.checking': 'Perguntando…',
  'firstRun.estate.recheck': 'Perguntar de novo',
  'firstRun.estate.sufficient':
    'O token consegue ler tudo o que este deployment precisa.',
  'firstRun.estate.insufficient':
    'O token não consegue ler tudo o que este deployment precisa.',
  'firstRun.estate.missingRead': 'Faltando, e cada um impede algo de funcionar:',
  'firstRun.estate.missingAdvisory':
    'Concedido pelo papel recomendado e não presente. Nada deixa de funcionar hoje:',
  'firstRun.estate.grantedAt': 'Concedido em:',
  'firstRun.estate.preview': 'Ver o que seria descoberto',
  'firstRun.estate.previewing': 'Vendo…',
  'firstRun.estate.found':
    '{nodes} nós, {guests} convidados, {running} em execução, {zones} zonas. Nada foi guardado.',
  'firstRun.estate.unplaced':
    '{count} deles estão em nenhuma rede declarada, então não carregam zona.',
  'firstRun.estate.incomplete':
    'O cluster não terminou de enumerar em uma passagem, então estes são um piso e não um total.',
  'firstRun.estate.confirm': 'Descobrir este parque a partir de agora',
  'firstRun.estate.confirming': 'Registrando…',
  'firstRun.estate.confirmed': 'Registrado. A primeira varredura está pronta agora.',
  'firstRun.estate.needsPreview':
    'Veja primeiro. Confirmar sem ter lido as contagens é um formulário, não uma decisão.',
  'firstRun.handover.estate': 'Ir para o parque',
  'firstRun.handover.alerts': 'Ir para os detectores',
  'firstRun.runtimeGap.heading': 'O que está realmente impedindo isso',
  'firstRun.complete.heading': 'Está tudo pronto.',
  'firstRun.complete.body':
    'Todos os passos acima estão concluídos, e este deployment já consegue conduzir uma investigação de verdade. Aperte Investigar, no topo de qualquer tela, para rodar a primeira.',
  'firstRun.complete.body.noPermission':
    'Todos os passos acima estão concluídos, e este deployment já consegue conduzir uma investigação de verdade. Peça a alguém que possa iniciar uma para rodar a primeira.',

  'firstRun.return.body':
    'A configuração guiada te mandou aqui para terminar este passo.',
  'firstRun.return.cta': 'Continuar a configuração',

  'setup.noProvider.heading': 'Nenhum provider de modelo está configurado',
  'setup.noProvider.body':
    'Nada pode ser investigado até que haja um. É uma credencial, e a plataforma oferece nove providers, incluindo um que roda no seu próprio hardware.',
  'setup.noProvider.action': 'Escolher um provider',

  'tutorial.title': 'O que é isto, em cinco telas',
  'tutorial.skip': 'Pular',
  'tutorial.close': 'Fechar',
  'tutorial.next': 'Próximo',
  'tutorial.back': 'Voltar',
  'tutorial.done': 'Começar a configurar',
  'tutorial.progress': '{step} de {total}',
  'tutorial.slide.1.title': 'Ele investiga, não apenas alerta',
  'tutorial.slide.1.body':
    'Um alerta chega, uma investigação começa, e o que volta é um diagnóstico com a evidência por trás dele — não um gráfico e um dar de ombros.',
  'tutorial.slide.2.title': 'Como uma investigação funciona',
  'tutorial.slide.2.body':
    'Ele raciocina, chama as ferramentas que suas integrações liberam, guarda cada leitura que usou, e para quando consegue dizer por quê. Você pode assistir, interromper e assumir.',
  'tutorial.slide.3.title': 'O que conectar',
  'tutorial.slide.3.body':
    'Um provider de modelo primeiro — nada funciona sem um. Depois, o que ele deve poder consultar. A qualidade decorre do que ele consegue ler.',
  'tutorial.slide.4.title': 'O que ele pode fazer sozinho',
  'tutorial.slide.4.body':
    'Nada, até você dizer o contrário. Toda mudança é proposta com seu raio de impacto e seu rollback até a postura dizer que ele pode agir.',
  'tutorial.slide.5.title': 'Teste antes de valer',
  'tutorial.slide.5.body':
    'Descreva um incidente e veja uma investigação real rodar. Sem nada conectado ele raciocina e não consulta nada, o que é honesto em vez de impressionante.',

  'live.investigate.caveat':
    'A qualidade depende do que está conectado. Sem nenhuma integração configurada o agente raciocina e não consulta nada.',

  'page.dashboard.title': 'Visão geral',
  'page.dashboard.context':
    'O que precisa de uma pessoa, o que está em curso e como está o parque.',
  'page.incidents.title': 'Incidentes',
  'page.incidents.context': 'O que um detector abriu e o que aconteceu desde então.',
  'page.runs.title': 'Investigações',
  'page.runs.context':
    'Todas as investigações que esta instalação registrou, da mais recente para a mais antiga. Abra uma onde ela está.',
  'page.decisions.title': 'Decisões',
  'page.decisions.context':
    'O que o agente quer fazer agora, e o que ele quer que o deployment se torne.',
  'page.integrations.title': 'Integrações',
  'page.integrations.context':
    'Cada integração para a qual este deployment pode salvar uma credencial, seu estado, e uma forma de testá-la.',
  'page.integrationsNotCovered.title': 'Não coberto, e por quê',
  'page.integrationsNotCovered.context':
    'Todo vendor que este catálogo não alcança, e por quê — não é alcançável, ou foi avaliado e decidido contra.',
  'page.signals.title': 'Sinais',
  'page.signals.context':
    'O que entra em observação contínua, e para onde um alerta vai depois de entrar.',
  'page.approvals.title': 'Ações aguardando aprovação',
  'page.approvals.context':
    'Ações que o agente quer realizar agora, à espera da sua aprovação. Cada uma traz seu raio de impacto e plano de reversão.',
  'page.proposals.title': 'Mudanças propostas',
  'page.proposals.context':
    'Tudo o que o agente propôs e ninguém decidiu. Cada proposta carrega o que mudaria, por quê, e a investigação de onde veio.',
  'page.resources.title': 'Recursos',
  'page.resources.context': 'Tudo o que a instalação observa, e a saúde de cada item.',
  'page.topology.title': 'Topologia',
  'page.topology.context':
    'Como o parque está ligado, tal como a plataforma o entende.',
  'page.detectors.title': 'Detectores',
  'page.detectors.context':
    'O que está sendo observado, com que frequência, e o que disparou.',
  'page.memory.title': 'Memória',
  'page.memory.context':
    'O que as investigações anteriores deixaram, e o que foi aprendido com elas.',
  'page.knowledge.title': 'Conhecimento',
  'page.knowledge.context': 'Os documentos que uma investigação pode ler.',
  'page.autonomy.title': 'Autonomia',
  'page.autonomy.context':
    'O que esta instalação pode fazer sozinha, e o que tem de perguntar antes.',
  'page.configuration.title': 'Configuração',
  'page.configuration.context':
    'A árvore da organização, e o resultado a que uma mudança nela levaria.',
  'page.teamContext.title': 'Contexto da equipe',
  'page.teamContext.context':
    'Fatos sobre este ambiente de que toda investigação devia partir.',
  'page.catalogue.title': 'Catálogo',
  'page.catalogue.context':
    'Todas as ferramentas e competências que esta instalação declara, e quais delas a sua equipe pode usar.',
  'page.administration.title': 'Administração',
  'page.administration.context':
    'Identidades, os papéis que detêm, os tokens de máquina emitidos e como as pessoas iniciam sessão.',
  'page.audit.title': 'Auditoria',
  'page.audit.context': 'Quem fez o quê, quando, e sobre que recurso.',
  'page.pending':
    'Esta área chega com as telas de dados. A moldura à volta dela está pronta.',

  // --- Abas de uma tela que uma fusão construiu ---------------------------------
  'decisions.tabs': 'O que precisa de uma decisão',
  'decisions.tab.actions': 'Ações',
  'decisions.tab.changes': 'Mudanças',
  'knowledge.tabs': 'O que o agente sabe sobre este ambiente',
  'knowledge.tab.learned': 'Aprendido',
  'knowledge.tab.documents': 'Documentos',
  'knowledge.tab.topology': 'Topologia',
  'signals.tabs': 'O que entra em observação e o que sai dela',
  'signals.tab.intake': 'Entrada',
  'signals.tab.observation': 'Observação contínua',
  'signals.tab.schedules': 'Agendas',
  'signals.tab.destinations': 'Destinos',
  'admin.tabs': 'Quem pode o quê, e quem fez o quê',
  'admin.tab.people': 'Pessoas',
  'admin.tab.audit': 'Auditoria',
  'agent.tab.team': 'Contexto do time',

  'shell.search': 'Procurar recursos, investigações, incidentes',
  'shell.search.shortcut': 'Ctrl K',
  'shell.theme': 'Tema',
  'shell.density.comfortable': 'Linhas confortáveis',
  'shell.density.compact': 'Linhas compactas',
  'shell.theme.light': 'Claro',
  'shell.theme.dark': 'Escuro',
  'shell.theme.system': 'Seguir o sistema',
  'shell.investigate': 'Investigar',
  'shell.viewTour': 'Ver o tour',
  'shell.account': 'Conta',
  'shell.account.signOut': 'Terminar sessão',
  'shell.account.impersonate': 'Agir como outra pessoa',
  'shell.account.language': 'Idioma',
  'shell.language.en': 'English',
  'shell.language.pt-BR': 'Português (Brasil)',
  'shell.deployment': 'Instalação',
  'shell.close': 'Fechar',

  // --- The emergency stop ------------------------------------------------------
  'stop.engage': 'Parar a automação',
  'stop.consequence':
    'Isto para toda escrita automática, imediatamente, em tudo o que este deployment faz. As investigações continuam rodando e propondo; nada é aplicado até alguém liberar.',
  'stop.confirm': 'Parar tudo agora',
  'stop.cancel': 'Deixar a correr',
  'stop.release': 'Deixar a automação correr de novo',
  'stop.engaged':
    'As escritas automáticas estão paradas. As investigações continuam rodando e propondo; nada é aplicado.',
  'stop.engaged.by': 'Parado por {by}, {since}.',
  'stop.engaged.unknown': 'Parado antes de esta tela poder dizer quem ou quando.',
  'stop.engaged.howToRelease':
    'Quem puder parar este deployment também pode liberá-lo, no topo da tela.',
  'stop.reason': 'Parado a partir do console.',
  'stop.autonomy': 'Rever a postura de Autonomia',
  'stop.refused': 'O deployment recusou mudar a paragem.',
  'stop.unreachable': 'Não foi possível alcançar o deployment. Pare-o à mão.',

  'shell.guardian.active': 'Guardião ativo',
  'shell.guardian.silent': 'Guardião silencioso',
  'shell.guardian.state': '{liveness} · {posture}',
  'shell.guardian.posture.propose': 'apenas propõe',
  'shell.guardian.posture.act': 'a agir',
  'shell.guardian.posture.frozen': 'congelado',
  'shell.guardian.tooltip':
    'O que a postura significa: "apenas propõe" mostra cada mudança e o seu raio de impacto, e não aplica nada até você aprovar. Abra Autonomia para ver ou mudar.',

  'notifications.title': 'Precisa de você',
  'notifications.open': 'Notificações',
  'notifications.unread': '{count} por ler',
  'notifications.empty': 'Nada está à espera de uma pessoa.',
  'notifications.resolved': 'Resolvido noutro lugar',

  'failure.technical': 'Detalhe técnico',
  'failure.investigator.title': 'As investigações ainda não estão ligadas',
  'failure.investigator.action':
    'Este deployment não tem um runtime para investigar — o modelo escolhido aqui não tem nada a ver com isso. Quem o opera precisa fornecer um runtime; a configuração guiada nomeia essa dependência assim que tudo o resto aqui estiver pronto.',
  'failure.credential.title': 'Falta uma chave para algo que isto precisava',
  'failure.credential.action':
    'Guarde a credencial do sistema que isto tentava alcançar.',
  'failure.vaultKey.title': 'Uma chave guardada não pode ser lida de volta',
  'failure.vaultKey.action':
    'A chave de encriptação deste deployment mudou desde que a credencial foi guardada. Guarde-a de novo.',
  'failure.store.title': 'Este deployment não alcança a própria base de dados',
  'failure.store.action':
    'Nada neste console resolve isto — quem opera o deployment precisa de olhar.',
  'failure.migrations.title': 'Este deployment está rodando um esquema antigo',
  'failure.migrations.action':
    'A base de dados está atrás do código. Quem opera o deployment precisa de aplicar as migrações.',
  'failure.unknown.title': 'Algo correu mal que este console não sabe explicar',
  'failure.unknown.action':
    'As palavras do próprio deployment estão no detalhe técnico abaixo.',

  'palette.title': 'Paleta de comandos',
  'palette.placeholder':
    'Procure recursos, incidentes e investigações, ou vá para uma página',
  'palette.empty': 'Nada corresponde a isso.',
  'palette.empty.partial':
    'Nada do que foi procurado corresponde a isso — há mais de uma página de resultados por percorrer.',
  'palette.group.resources': 'Recursos',
  'palette.group.incidents': 'Incidentes',
  'palette.group.found-runs': 'Investigações correspondentes',
  'palette.group.navigate': 'Ir para',
  'palette.group.runs': 'Investigações recentes',
  'palette.group.actions': 'Ações',
  'palette.close': 'Fechar a paleta',

  'noAdministrator.title': 'Este deployment ainda não tem administrador',
  'noAdministrator.body': 'Rode o comando abaixo no host para criar um.',
  'signIn.title': 'Entrar',
  'signIn.context': 'Este console contata a sua instalação e mais nada.',
  'signIn.username': 'Usuário',
  'signIn.password': 'Senha',
  'signIn.submit': 'Entrar',
  'signIn.rejected': 'Esse usuário e essa senha não foram aceitos.',
  'signIn.unreachable': 'Não foi possível contatar a instalação.',
  'signIn.expired':
    'A sua sessão terminou. Entre de novo para voltar ao ponto onde estava.',
  'session.expiring': 'Esta sessão termina em {duration}.',
  'session.expiring.action': 'Continuar com sessão iniciada',
  'session.impersonation.label': 'Personificação',
  'session.impersonation.banner': '{actor} está agindo como {subject}.',

  'error.title': 'Não foi possível mostrar esta página',
  'error.context':
    'O resto do console continua funcionando. Tentar de novo recarrega apenas esta página.',
  'error.retry': 'Tentar de novo',
  'notFound.title': 'Não existe essa página',
  'notFound.context': 'O endereço não corresponde a nenhuma área deste console.',
  'notFound.action': 'Ir para a visão geral',

  'breadcrumb.label': 'Trilho',
  'avatar.unknown': 'Pessoa desconhecida',
  'pagination.previous': 'Anterior',
  'pagination.next': 'Próximo',
  'pagination.position': 'Página {page} de {pages}',
  'pagination.landmark': 'Paginação',

  // O vocabulário do board para os estados que o produto conhece.
  'status.running': 'Rodando',
  'status.completed': 'Completada',
  'status.failed': 'Falhou',
  'status.succeeded': 'Sucedeu',
  'status.expired': 'Expirada',
  'status.investigating': 'Investigando',
  'status.resolved': 'Resolvido',
  'status.remediating': 'Remediando',
  'status.open': 'Aberto',
  'status.awaiting_human': 'Esperando alguém',
  'status.critical': 'Crítico',
  'status.medium': 'Médio',
  'status.active': 'Ativa',
  'status.propose': 'Propor',
  'status.proposed': 'Proposta',
  'status.credential.notConnected': 'Não conectada',
  'status.credential.stored': 'Armazenada',
  'status.credential.verified': 'Verificada',
  'status.credential.degraded': 'Degradada',
  'status.credential.failing': 'Falhando',
  'status.credential.unknown': 'Desconhecida',
  'status.resource.healthy': 'saudável',
  'status.resource.degraded': 'degradado',
  'status.resource.unhealthy': 'não saudável',
  'status.resource.unknown': 'desconhecido',
  'status.resource.stale': 'desatualizado',
  'status.resource.maintenance': 'em manutenção',
  'status.resource.absent': 'ausente',
  'status.credential.unknown.explain':
    'O gateway deste deployment não pôde ser contatado, então o estado real não pôde ser lido.',

  'surface.loading': 'A carregar {panel}…',
  'surface.error.heading': 'Não foi possível preencher este painel',
  'surface.error.detail':
    'não respondeu. O resto desta página não é afetado e apenas este painel será tentado de novo.',
  'surface.error.retry': 'Tentar este painel de novo',
  'surface.open': 'Abrir',
  'surface.sort.ascending': 'ordenar por {column}, do menor para o maior',
  'surface.sort.descending': 'ordenar por {column}, do maior para o menor',
  'surface.filter.any': 'Qualquer',
  'surface.showing': 'A mostrar {shown} de {total}.',
  'surface.none': 'Não registrado',
  'surface.export': 'Exportar',
  'surface.payload.bounded':
    '{total} linhas no conteúdo; a mostrar as primeiras {shown}.',
  'surface.payload.expand': 'Mostrar o conteúdo completo',
  'surface.payload.collapse': 'Limitar de novo',
  'surface.payload.copy': 'Copiar o conteúdo em bruto',
  'surface.payload.copied': 'Copiado',

  'transcript.title': 'Transcrição da investigação',
  'transcript.kind.objective': 'Objetivo',
  'transcript.kind.reasoning': 'Raciocínio',
  'transcript.kind.call': 'Chamada de capacidade',
  'transcript.kind.result': 'Resultado da capacidade',
  'transcript.kind.evidence': 'Prova guardada',
  'transcript.kind.recall': 'Recuperação de memória',
  'transcript.kind.dispatch': 'Sub-agente despachado',
  'transcript.kind.return': 'Sub-agente devolveu',
  'transcript.kind.guardrail': 'Salvaguarda — ação retida',
  'transcript.kind.interaction': 'Interação humana',
  'transcript.kind.report': 'Relatório',
  'transcript.position': 'A mostrar os eventos {first} a {last} de {total}.',
  'transcript.earlier': 'Eventos anteriores',
  'transcript.later': 'Eventos seguintes',
  'transcript.empty': 'Esta investigação não registrou eventos.',
  'transcript.arguments': 'Argumentos',
  'transcript.result': 'Resultado',
  'transcript.note': 'Por que estas capacidades foram oferecidas',
  'transcript.duration': '{ms} ms',
  'transcript.events': '{count} eventos',
  'transcript.events.one': '{count} evento',
  'transcript.newestFirst': 'o mais novo primeiro',
  'transcript.empty.heading': 'Ainda não há transcrição',
  'transcript.empty.body':
    'A transcrição aparece assim que a investigação dá o primeiro passo. Nada foi registrado nesta.',
  'transcript.empty.action': 'Voltar às investigações',

  // O alternador entre a frase narrada (padrão) e o payload bruto que todo
  // evento carrega. Duas palavras, lidas só pelo próprio alternador.
  'transcript.view.narrated': 'Narrado',
  'transcript.view.raw': 'Bruto',
  'transcript.view.payload': 'Payload bruto',

  // Uma frase por tipo cru que o vocabulário do stream declara
  // (`STREAM_KINDS`, `transcript.ts`). `{name}` só é preenchido com um nome
  // real de capacidade ou subagente — nunca deixado como placeholder literal
  // — e o `detail` do próprio evento é acrescentado depois da frase por
  // `narrate`, nunca embutido no modelo.
  'transcript.narration.runStarted': 'Objetivo aceito',
  'transcript.narration.stageCompleted': 'Estágio concluído — {name}',
  'transcript.narration.turnCompleted': 'O turno terminou',
  'transcript.narration.evidenceObserved': 'Uma evidência foi anotada',
  'transcript.narration.maskingApplied': 'Conteúdo sensível foi mascarado',
  'transcript.narration.budgetEviction': 'Contexto além do orçamento foi descartado',
  'transcript.narration.approvalRequested': 'Uma aprovação foi pedida',
  'transcript.narration.attentionChanged':
    'A investigação começou ou parou de esperar uma pessoa',
  'transcript.narration.reportDelivered': 'Um relatório foi entregue',
  'transcript.narration.notificationDecided': 'Uma política de notificação decidiu',
  'transcript.narration.runInterrupted': 'A investigação foi interrompida',
  'transcript.narration.runFinished': 'A investigação terminou',
  'transcript.narration.hypothesisFormed': 'Uma hipótese se formou',
  'transcript.narration.turnStarted': 'Um novo turno começou',
  'transcript.narration.modelReasoned': 'O modelo raciocinou',
  'transcript.narration.toolCalled': 'Chamou {name}',
  'transcript.narration.toolSucceeded': '{name} retornou',
  'transcript.narration.toolFailed': '{name} falhou',
  'transcript.narration.observationRecorded': 'Uma observação foi registrada',
  'transcript.narration.evidenceRetained': 'Uma evidência foi retida',
  'transcript.narration.memoryRecalled': 'Uma memória foi recuperada',
  'transcript.narration.subagentDispatched': 'Despachou {name}',
  'transcript.narration.subagentReturned': '{name} retornou',
  'transcript.narration.guardrailWithheld': 'Uma proteção reteve uma ação',
  'transcript.narration.guardrailApplied': 'Uma proteção foi aplicada',
  'transcript.narration.interactionOpened': 'A investigação está esperando uma pessoa',
  'transcript.narration.interactionAnswered': 'A pergunta em aberto foi respondida',
  'transcript.narration.runCompleted': 'A investigação foi concluída',
  'transcript.narration.runFailed': 'A investigação falhou',
  // O piso que todo evento tem: um tipo que esta versão nunca viu ainda se
  // nomeia, numa frase, em vez de cair para um bloco de payload bruto.
  'transcript.narration.unknown': 'Chegou um evento de tipo não reconhecido: {kind}',
  'transcript.narration.unnamedCapability': 'uma capacidade',
  'transcript.narration.unnamedSubagent': 'um subagente',
  'transcript.narration.unnamedStage': 'um estágio',

  // --- O rail de estágios do run ---------------------------------------------------
  'run.stage.rail.title': 'Pipeline',
  'run.stage.future': 'Estágio {number}',
  'run.usage.awaiting': 'O primeiro turno ainda não chegou.',
  'run.links.watching': 'Observando os recursos que esta investigação toca.',
  'run.findings.title': 'Descobertas até agora',
  'run.findings.none': 'Nenhum estágio terminou com uma descoberta ainda.',

  // --- O Painel: "Em execução agora" ------------------------------------------
  'dashboard.runBand.title': 'Em execução agora',
  // Os substantivos que dizem o que cada contagem conta: sem eles a linha
  // e' "0 · 12 · 0" e o leitor tem que adivinhar o segundo numero.
  'dashboard.runBand.flight': 'investigações em voo',
  'dashboard.runBand.followed': 'incidentes acompanhados',
  'dashboard.runBand.blocked': 'bloqueado em você',
  'dashboard.runBand.more': 'todas as investigações →',
  // O estagio em curso, pelo nome, e onde ele cai entre os seis.
  'dashboard.runBand.stage': '{stage} · {position} de {total}',
  'dashboard.runBand.empty':
    'Nada está rodando agora — toda investigação terminou ou nenhuma foi iniciada.',
  'dashboard.runBand.empty.action': 'Investigar algo →',

  // --- O Painel: "Precisa de você" (decidido em linha) -------------------------
  'dashboard.decisionBand.title': 'Precisa de você',
  'dashboard.decisionBand.plan': 'O que vai acontecer',
  'dashboard.decisionBand.rollback': 'Como reverte',
  'dashboard.decisionBand.approve': 'Aprovar',
  'dashboard.decisionBand.reject': 'Recusar',
  'dashboard.decisionBand.rejectSubmit': 'Confirmar recusa',
  'dashboard.decisionBand.cancel': 'Cancelar',
  'dashboard.decisionBand.reason': 'Razão',
  'dashboard.decisionBand.reasonRequired': 'Uma razão é obrigatória para recusar.',
  'dashboard.decisionBand.failed': 'A decisão não pôde ser registrada. Tente de novo.',
  'dashboard.decisionBand.noPermission':
    'Você não tem a permissão para decidir isto. Peça a quem tem.',
  'dashboard.decisionBand.viewPlan': 'Ver plano →',
  'dashboard.decisionBand.empty': 'Nada espera uma decisão agora.',
  'dashboard.decisionBand.empty.action': 'Ver o histórico de decisões →',
  'dashboard.decisionBand.more': '{count} a mais esperando →',

  // --- Os cinco KPIs (de GET /v1/overview) -----------------------------------
  'dashboard.kpi.watched': 'Recursos vigiados',
  'dashboard.kpi.watched.breakdownJoiner': ' · ',
  'dashboard.kpi.degraded': 'Degradados agora',
  'dashboard.kpi.degraded.noDetector': 'Nenhum detector promove achado a incidente',
  'dashboard.kpi.degraded.context': 'contado a partir da saúde atual do estate',
  'dashboard.kpi.selfResolved': 'Fechados sozinhos',
  'dashboard.kpi.selfResolved.context': '{closed} de {total} incidentes',
  'dashboard.kpi.selfResolved.context.none': 'Nenhum incidente fechou ainda',
  'dashboard.kpi.successRate': 'Taxa de sucesso',
  'dashboard.kpi.successRate.context': '{succeeded} de {total} investigações',
  'dashboard.kpi.successRate.context.none': 'Nenhuma investigação terminou ainda',
  'dashboard.kpi.timeToCause': 'Tempo até a causa',
  'dashboard.kpi.timeToCause.context': 'mediana {median} · pior {worst}',
  'dashboard.kpi.timeToCause.context.none': 'Nenhuma investigação terminou ainda',
  'dashboard.kpi.readFailed': 'Não pôde ser lido',
  'dashboard.kpi.sparkline.label': 'Tendência de {count} dias',
  'dashboard.kpi.drill': 'Ver a lista por trás desta figura',
  'dashboard.kpi.configureDetectors': 'Configurar detectores →',

  // --- "O que insiste em acontecer" (janela de 48h) --------------------------
  'dashboard.subjects.empty': 'Nada se repetiu nas últimas 48 horas.',
  'dashboard.subjects.empty.action': 'Ver Incidentes →',

  'dashboard.attention.title': 'Precisa de você',
  'dashboard.attention.count': '{count} itens precisam de você',
  'dashboard.attention.count.one': '{count} item precisa de você',
  'dashboard.attention.oldest': 'À espera há mais tempo: {age}',
  'dashboard.attention.empty.heading': 'Nada está à espera de uma pessoa',
  'dashboard.attention.empty.body':
    'Aprovações, perguntas do agente e investigações falhadas aparecem aqui assim que existirem. Não existe nenhuma.',
  'dashboard.attention.empty.action': 'Ver o que está rodando',
  'dashboard.stat.watched': 'Recursos vigiados',
  'dashboard.stat.watched.context': '{kinds}',
  'dashboard.stat.healthy': 'Saudáveis',
  'dashboard.stat.healthy.context': '{count} de {total} na última varredura',
  'dashboard.stat.degraded': 'Degradados e não saudáveis',
  'dashboard.stat.degraded.context':
    '{count} constatações abertas por trás deles; {live} de {total} detectores estão ligados para transformar uma delas num incidente',
  'dashboard.stat.runs': 'Investigações recentes',
  'dashboard.stat.runs.context': '{failed} delas falharam',
  'dashboard.stat.successRate': 'Taxa de sucesso',
  'dashboard.stat.successRate.context':
    '{succeeded} de {settled} investigações concluídas tiveram sucesso',
  'dashboard.stat.successRate.context.none': 'Ainda não terminou nenhuma investigação',
  'dashboard.stat.timeToCause': 'Tempo até a causa',
  'dashboard.stat.timeToCause.context': 'mediana de {settled} · mais lenta {slowest}',
  'dashboard.stat.timeToCause.context.none': 'Nenhuma investigação terminou ainda.',
  'dashboard.stat.drill': 'Ver a lista por trás deste número',
  'dashboard.activity.title': 'Atividade ao vivo',
  'dashboard.activity.empty.heading': 'Ainda não aconteceu nada',
  'dashboard.activity.empty.body':
    'Investigações, incidentes e decisões aparecem aqui à medida que acontecem. Conecte uma fonte de infraestrutura e a primeira varredura começa em até um minuto.',
  'dashboard.activity.empty.action': 'Conectar uma fonte',
  'dashboard.activity.more': 'linha do tempo completa →',
  'dashboard.liveActivity.count': '{count}×',
  'dashboard.liveActivity.investigationStarted': 'Investigação iniciada',
  'dashboard.liveActivity.causeFound': 'Causa encontrada',
  'dashboard.liveActivity.investigationEnded': 'Investigação encerrada',
  'dashboard.liveActivity.incidentOpened': 'Incidente aberto',
  'dashboard.liveActivity.incidentSelfResolved': 'Incidente fechado sozinho',
  'dashboard.liveActivity.decisionProposed': 'Remediação proposta',
  'dashboard.liveActivity.decisionDecided': 'Decisão registrada',
  // O segundo termo da segunda linha de cada entrada: o que produziu
  // aquilo. Duas destas palavras nomeiam o tipo da entrada; as outras
  // duas dizem o que o deployment de fato registrou (que ninguem tocou,
  // que alguem precisa decidir).
  'dashboard.liveActivity.by.investigation': 'investigação',
  'dashboard.liveActivity.by.awaitingApproval': 'aguardando aprovação',
  'dashboard.liveActivity.by.noHuman': 'sem intervenção humana',
  'dashboard.liveActivity.by.decision': 'decisão',
  'dashboard.hero.title': 'Continuar a configuração',
  'dashboard.hero.remaining': '{count} de {total} passos por fazer',
  'dashboard.hero.next': 'Próximo',
  'dashboard.hero.action': 'Continuar a configuração',
  'dashboard.hero.empty.heading': 'O estado da configuração não pôde ser lido',
  'dashboard.hero.empty.body':
    'Isto é lido a partir da checklist de configuração da própria instalação, e ela não respondeu. O resto desta página não é afetado.',
  'dashboard.hero.empty.action': 'Abrir os primeiros passos',
  'dashboard.guardian.title': 'Guardião',
  'dashboard.guardian.posture': 'Postura',
  'dashboard.guardian.liveness': 'Vivacidade',
  'dashboard.guardian.detectors': 'Detectores ativos',
  'dashboard.guardian.detectors.value': '{live} de {total}',
  'dashboard.guardian.review': 'Rever a postura',
  'dashboard.guardian.empty.heading': 'O guardião não reportou',
  'dashboard.guardian.empty.body':
    'Um guardião que parou é exatamente igual a um cluster sem problemas, por isso este painel avisa em vez de ficar calado.',
  'dashboard.guardian.empty.action': 'Ver a instalação',

  'runs.column.run': 'Investigação',
  'runs.column.status': 'Estado',
  'runs.column.trigger': 'Origem',
  'runs.column.subject': 'Assunto',
  'runs.column.started': 'Início',
  'runs.column.duration': 'Duração',
  'runs.column.cost': 'Custo',
  'runs.filter.status': 'Estado',
  'runs.filter.trigger': 'Origem',
  'runs.list.title': 'Investigações',
  'runs.trigger.manual': 'Manual',
  'runs.trigger.alert': 'Alerta',
  'runs.trigger.scheduled': 'Agendada',
  'runs.trigger.specialist': 'Especialista',
  'runs.list.caption': 'Todas as investigações registradas por esta instalação',
  'runs.live.title': 'Vivas agora',
  'runs.live.count.one': '{count} em voo',
  'runs.live.count': '{count} em voo',
  'runs.empty.heading': 'Ainda não há investigações',
  'runs.empty.body':
    'Uma investigação é registrada quando um alerta, um horário ou uma pessoa inicia uma. Nenhuma foi registrada.',
  'runs.empty.action': 'Iniciar uma investigação',
  'runs.filtered.heading': 'Nenhuma investigação corresponde a esses filtros',
  'runs.filtered.body':
    'Todos os filtros estão no endereço, por isso limpá-los é uma navegação e a vista que tinha continua compartilhável.',
  'runs.filtered.action': 'Limpar os filtros',
  'run.summary.title': 'O que esta investigação encontrou',
  'run.usage.title': 'Custo e tokens',
  'run.usage.model': 'Modelo',
  'run.usage.turn': 'Passo',
  'run.usage.turns': 'Passos',
  'run.usage.calls': 'Chamadas',
  'run.usage.tokens': 'Tokens',
  'run.usage.cost': 'Custo',
  'run.usage.unrecorded': 'sem registro de custo para este run',
  'run.usage.unpriced': 'Sem preço publicado para este modelo',
  'run.usage.unpriced.short': 'sem preço',
  'run.usage.apportioned':
    'A investigação reporta um total; a divisão abaixo é esse total repartido pelos seus passos.',
  'run.usage.empty.heading': 'Nenhum custo registrado',
  'run.usage.empty.body':
    'O custo e os tokens são registrados por passo. Esta investigação ainda não deu nenhum.',
  'run.usage.empty.action': 'Voltar às investigações',
  'run.changes.title': 'O que mudou, na mesma régua',
  'run.changes.body':
    'Cada mudança que a investigação consultou, posicionada contra o instante em que ela começou. Uma mudança marcada como gerenciando o recurso afetado alterou algo que o governa; uma marcada como coincidência apenas divide a janela.',
  'run.changes.investigation': 'esta investigação começou',
  'run.changes.window': 'de {start} até {end}',
  'run.links.title': 'O que esta investigação tocou',
  'run.links.resources': 'Recursos',
  'run.links.incident': 'Incidente',
  'run.links.readOnly': 'só leitura até aqui · nenhuma escrita proposta ainda',
  'run.links.empty.heading': 'Ainda nada ligado',
  'run.links.empty.body':
    'Recursos e incidentes são ligados à medida que a investigação os nomeia. Esta não nomeou nenhum.',
  'run.links.empty.action': 'Ver o parque',

  // --- Uma investigação, aberta onde ela está --------------------------------------
  'runs.row.open': 'Abrir esta investigação',
  'runs.row.opening': 'Abrindo esta investigação…',
  'runs.row.close': 'Fechar esta investigação',
  'runs.row.openPage': 'Abrir na página dela',
  'run.evidence.backed': '{backed} de {claims} afirmações sustentadas',
  'run.evidence.unassessed': 'nada a sustentar',
  'run.evidence.unassessed.explain':
    'Esta investigação nunca avaliou a própria evidência, o que não é o mesmo que não ter achado nada.',
  'run.evidence.missing.explain':
    'A investigação nomeou {missing} coisa(s) que ainda não conseguiu ler.',
  'run.measure.duration': 'Tempo até a causa',
  'run.measure.calls': 'Capacidades chamadas',
  'run.measure.trigger': 'Disparada por',
  'run.measure.tokens': 'Tokens',
  'run.measure.unpriced': 'Este modelo não publica preço.',
  'run.section.happened': 'O que aconteceu',
  'run.section.reaches': 'O que ela alcança',
  'run.section.order': 'Em ordem',
  'run.section.why': 'Por quê',
  'run.section.todo': 'O que fazer',
  'run.section.did': 'O que ela fez',
  'run.section.remembered': 'Vale lembrar',
  'run.happened.none': 'Esta investigação não escreveu relatório além da linha acima.',
  'run.reaches.none': 'Esta investigação não está arquivada sob nenhum incidente.',
  'run.remembered.written': 'escrito no corpus',
  'run.remembered.none': 'Esta investigação não escreveu nada no corpus.',
  'run.remembered.unknown':
    'Este console não conseguiu ler {dependency}, então não se sabe se esta investigação escreveu algo no corpus.',
  'run.why.supporting': 'O que sustenta',
  'run.why.missing': 'O que ninguém conseguiu ler',
  'run.why.none': 'Esta investigação nunca avaliou a própria evidência.',
  'run.todo.none': 'Nada desta investigação está esperando por uma pessoa.',
  'run.did.summary': '{events} eventos em {turns} turnos',
  'run.did.stages': '{events} eventos em {stages} etapas',
  'run.did.calls': '{calls} chamadas',
  'run.did.more': 'Mostrar mais {count} chamadas',
  'run.did.noRationale': 'Este turno não registrou raciocínio.',
  'run.did.wroteReport': 'Este turno escreveu o relatório acima.',
  'run.stage.resolve_integrations': 'Resolver integrações',
  'run.stage.intake': 'Triagem',
  'run.stage.plan_evidence': 'Planejar evidência',
  'run.stage.gather_evidence': 'Reunir evidência',
  'run.stage.diagnose': 'Diagnosticar',
  'run.stage.deliver': 'Entregar',
  'run.stage.modelCalls': '{calls} chamadas ao modelo',
  'run.stage.noFinding': 'Esta etapa não registrou constatação.',
  'run.report.copy': 'Copiar como Markdown',
  'run.report.copied': 'Copiado',
  'run.report.copyRefused': 'O navegador recusou a área de transferência',

  'incidents.column.severity': 'Gravidade',
  'incidents.column.title': 'Incidente',
  'incidents.column.state': 'Estado',
  'incidents.column.detector': 'Detector',
  'incidents.column.opened': 'Aberto',
  'incidents.column.subjects': 'Assuntos',
  'incidents.filter.state': 'Estado',
  'incidents.filter.severity': 'Gravidade',
  'dashboard.band.active': 'Guardião ativo',
  'dashboard.band.silent': 'Guardião silencioso',
  'dashboard.band.meta':
    '{posture} · {live} de {total} detectores vivos · {watched} recursos observados',
  'dashboard.band.meta.noDetectors':
    '{posture} · nenhum detector configurado · {watched} recursos observados',
  'dashboard.stat.degraded.context.noDetectors':
    '{count} achados abertos por trás deles, e nenhum detector ligado para transformar algum em incidente',
  'dashboard.band.flight': 'Investigações em curso',
  'dashboard.band.blocked': 'Travado em você',
  'dashboard.band.detectors': 'Detectores vivos',
  'dashboard.band.held': 'Incidentes assumidos',
  'dashboard.band.idle': 'Nada está sendo investigado neste momento.',
  'dashboard.band.silent.body':
    'O guardião não está reportando prontidão, então nada está sendo observado e nada será levantado. Tudo abaixo é a última coisa que este deployment soube.',
  'dashboard.band.started': 'iniciada {since}',
  'dashboard.stat.unattended': 'Resolvido sem uma pessoa',
  'dashboard.stat.unattended.context':
    '{closed} de {total} incidentes se fecharam sozinhos',
  'dashboard.stat.unattended.context.none': 'nada foi fechado ainda',
  'dashboard.attention.more': 'e mais {count} esperando',
  'dashboard.recurring.title': 'O que insiste em acontecer',
  'dashboard.recurring.tally':
    '{subjects} assuntos · {firings} disparos · agrupado por assunto',
  'dashboard.recurring.tally.one':
    '{subjects} assunto · {firings} disparos · agrupado por assunto',
  'dashboard.recurring.more': 'ver os {count} assuntos →',
  'dashboard.recurring.more.one': 'ver o assunto →',
  'dashboard.recurring.empty.heading': 'Nada se repetiu',
  'dashboard.recurring.empty.body':
    'Uma condição que dispara mais de uma vez no mesmo assunto é reunida aqui, para que um problema recorrente seja uma linha e não uma página delas.',
  'dashboard.recurring.empty.action': 'Ver todos os incidentes',
  'dashboard.held.title': 'O agente está cuidando',
  'incidents.filter.view': 'Exibição',
  'incidents.view.grouped': 'Por assunto',
  'incidents.view.flat': 'Cada disparo',
  'incidents.group.wasSeverity': 'foi {severity}',
  'incidents.group.since': 'recorrente desde {since}',
  'incidents.group.expand': 'Mostrar cada disparo de {title}',
  'incidents.group.summary': '{subjects} assuntos · {firings} disparos',
  'incidents.filter.state.investigating': 'Investigando',
  'incidents.filter.state.resolved': 'Resolvido',
  'incidents.filter.severity.critical': 'Crítico',
  'incidents.header.summary':
    '{subjects} assuntos · {firings} disparos · {critical} críticos em investigação',
  'incidents.timeline.title': 'Disparos nas últimas 24 h',
  'incidents.timeline.now': 'agora',
  'incidents.timeline.overflow': 'e mais {count} antes de ontem',
  'incidents.cause.live': 'investigação em andamento →',
  'incidents.cause.found': 'Última causa encontrada:',
  'incidents.coverage.gap': '{count} achados degradados estão sem detector ligado',
  'incidents.coverage.action': 'Ligar detector →',
  'incidents.list.title': 'Incidentes',
  'incidents.list.caption': 'Incidentes abertos e recentemente fechados',
  'empty.cause.setup':
    'Ainda não aconteceu nada aqui porque este deployment continua sendo configurado — o próximo passo é "{step}".',
  'empty.cause.setup.action': 'Terminar a configuração',
  'empty.cause.watching':
    'Nenhum detector está ligado, portanto nada está sendo observado e nada se abrirá sozinho.',
  'empty.cause.watching.action': 'Ligar a observação contínua',
  'empty.cause.extraction':
    '{finished} investigações terminaram e nenhuma delas deixou um episódio para trás. O que transforma uma investigação encerrada em episódio é uma chamada de modelo, e cada papel escolhe o seu.',
  'empty.cause.extraction.action': 'Ver o modelo de cada papel',

  'incidents.empty.heading': 'Nenhum incidente aberto',
  'incidents.empty.body':
    'Um detector abre um incidente quando o que vigia ultrapassa o seu limiar. Nenhum o fez.',
  'incidents.empty.action': 'Ver o que está sendo vigiado',
  'incidents.preview.link': 'Ver um incidente de exemplo',
  'incidents.preview.title': 'Como é um incidente',
  'incidents.preview.body':
    'Um incidente nomeia o que ultrapassou o limiar de um detector, o assunto afetado e a evidência que o tornou acionável. Este é um exemplo, não um incidente real.',
  'incidents.preview.label.detector': 'Detector',
  'incidents.preview.label.subject': 'Assunto',
  'incidents.preview.label.evidence': 'Evidência',
  'incidents.preview.example.title': 'Armazenamento quase cheio',
  'incidents.preview.example.detector': 'datastore-near-full',
  'incidents.preview.example.subject': 'store-cove',
  'incidents.preview.example.evidence': 'data_percent = 95.65',
  'incident.subject.title': 'Assunto',
  'incident.subject.resource': 'Recurso',
  'incident.subject.kind': 'Tipo',
  'incident.subject.health': 'Saúde',
  'incident.subject.lastSeen': 'Visto pela última vez',
  'incident.derivation.title': 'Porquê degradado',
  'incident.derivation.lead':
    'Derivado de {count} sinais — não de uma cadeia de texto do fornecedor.',
  'incident.derivation.retained': 'O estado em bruto do fornecedor é conservado.',
  'incident.derivation.empty.heading': 'Nenhuma derivação registrada',
  'incident.derivation.empty.body':
    'A saúde é derivada de sinais nomeados contra limiares nomeados. Nenhum foi registrado para este assunto.',
  'incident.derivation.empty.action': 'Ver os detectores',
  'incident.timeline.title': 'Cronologia',
  'incident.timeline.empty.heading': 'Ainda não aconteceu nada',
  'incident.timeline.empty.body':
    'As mudanças de estado são registradas aqui à medida que acontecem. Este incidente não teve nenhuma desde que abriu.',
  'incident.timeline.empty.action': 'Voltar à lista de incidentes',

  // --- A tela do incidente (M6) -------------------------------------------------
  'incident.chip.state.open': 'Aberto',
  'incident.chip.state.investigating': 'Investigando',
  'incident.chip.state.awaitingHuman': 'Aguardando uma pessoa',
  'incident.chip.state.remediating': 'Corrigindo',
  'incident.chip.state.resolved': 'Resolvido',
  'incident.chip.state.suppressed': 'Suprimido',
  'incident.chip.state.closedWithoutAction': 'Encerrado sem ação',
  'incident.chip.state.unknown': 'Desconhecido',
  'incident.chip.state.unknown.explain':
    'Não foi possível ler este incidente, então também não foi possível saber o seu estado.',
  'incident.chip.investigation.none': 'Sem investigação',
  'incident.chip.investigation.running': 'Investigação em andamento',
  'incident.chip.investigation.finished': 'Investigação concluída',
  'incident.chip.investigation.unknown': 'Desconhecido',
  'incident.chip.investigation.unknown.explain':
    'Não foi possível ler este incidente, então também não foi possível saber se ele tem uma investigação.',
  'incident.chip.investigation.unseen.explain':
    'Este incidente nomeia uma investigação e nada gravou o traço dela ainda, então onde ela chegou não se sabe aqui.',
  'incident.header.unreadable': 'Não foi possível ler este incidente',

  'incident.origin.alert': 'Alertmanager',
  'incident.origin.detector': 'os detectores deste deployment',
  'incident.origin.human': 'uma pessoa',
  'incident.subtitle.started': 'iniciado {when}',
  'incident.subtitle.zone': 'zona {zone}',

  'incident.investigation.title': 'Investigação',
  'incident.investigation.steps.one': '{count} passo',
  'incident.investigation.steps.other': '{count} passos',
  'incident.investigation.empty.heading': 'Nenhuma investigação rodou',
  'incident.investigation.empty.body':
    'Este incidente ainda não tem investigação anexada. O passo de runtime na configuração nomeia a pendência antes que uma possa começar.',
  'incident.investigation.empty.action': 'Ver o passo de runtime',
  'incident.investigation.step.receipt': 'Alerta recebido',
  'incident.investigation.step.hypotheses': 'Hipóteses levantadas',
  'incident.investigation.step.evidence': 'Evidência',
  'incident.investigation.step.diagnosis': 'Diagnóstico',
  'incident.investigation.step.delivery': 'Relatório entregue',

  'incident.evidenceTrail.title': 'Trilha de evidências',
  'incident.evidenceTrail.body':
    'Cada consulta, resposta e token gasto, em ordem. Nada aqui é prosa sem uma fonte.',
  'incident.evidenceTrail.link': 'Abrir o run completo',
  'incident.evidenceTrail.empty.heading': 'Ainda não há run para seguir',
  'incident.evidenceTrail.empty.body':
    'Este incidente não tem run de investigação anexado, então não há trilha de evidências para abrir.',
  'incident.evidenceTrail.empty.action': 'Ver o passo de runtime',

  'incident.proposedAction.title': 'Ação proposta',
  'incident.proposedAction.state.pending': 'Aguardando decisão',
  'incident.proposedAction.state.approved': 'Aprovada',
  'incident.proposedAction.state.rejected': 'Rejeitada',
  'incident.proposedAction.state.expired': 'Expirada',
  'incident.proposedAction.posture': 'A postura é {posture} — nada executa sem você.',
  'incident.proposedAction.approve': 'Aprovar e executar',
  'incident.proposedAction.reject': 'Rejeitar',
  'incident.proposedAction.reason': 'Motivo',
  'incident.proposedAction.reasonRequired': 'Um motivo é obrigatório para rejeitar.',
  'incident.proposedAction.decisionFailed':
    'A decisão não foi registrada. Tente novamente.',
  'incident.proposedAction.radius.resources.one': '{count} recurso',
  'incident.proposedAction.radius.resources.other': '{count} recursos',
  'incident.proposedAction.radius.zone': 'zona {zone}',
  'incident.proposedAction.radius.criticality': 'criticidade {criticality}',
  'incident.proposedAction.empty.heading': 'Nada proposto ainda',
  'incident.proposedAction.empty.body':
    'Nenhuma investigação concluiu com uma correção a decidir para este incidente.',
  'incident.proposedAction.empty.action': 'Ver a investigação',

  'approvals.title': 'Ações aguardando aprovação',
  'approvals.group.overdue': 'Depois do prazo',
  'approvals.group.today': 'À espera hoje',
  'approvals.group.later': 'À espera há mais tempo',
  'approvals.empty.heading': 'Nada está à espera de uma decisão',
  'approvals.empty.body':
    'Uma mudança que precisa de uma pessoa aparece aqui com o seu raio de impacto e o seu plano de reversão. Nenhuma aparece.',
  'approvals.empty.action': 'Ver o que está rodando',
  'approvals.otherInbox': 'Para mudanças que o agente propôs para o deployment:',
  'approvals.empty.rule':
    'A regra ativa pede aprovação para ações em {threshold} e acima.',
  'approvals.empty.rule.default': 'Esse é o padrão do deployment.',
  'approvals.empty.rule.setAt': 'Está definido em {node}.',
  'approvals.expired.note':
    'O prazo para responder a esta ação terminou, e o deployment recusa uma decisão tomada depois dele. O estado sobre o qual ela foi proposta foi lido antes disso e ninguém olhou desde então — peça a ação de novo para decidir sobre uma leitura atual.',
  'proposal.title': 'Ação proposta — aguardando a sua decisão',
  'proposal.risk': 'Risco {level} de 5',
  'proposal.target': 'Alvo',
  'proposal.current': 'Estado actual',
  'proposal.change': 'Mudança proposta',
  'proposal.protects': 'O que cada um protege',
  'proposal.blast': 'Raio de impacto',
  'proposal.rollback': 'Plano de reversão',
  'proposal.verification': 'Verificação',
  'proposal.autonomy': 'Autonomia',
  'proposal.approve': 'Aprovar',
  'proposal.reject': 'Rejeitar',
  'proposal.reason': 'Porque está sendo rejeitada',
  'proposal.reason.required': 'É obrigatório indicar um motivo para rejeitar.',
  'proposal.norollback': 'Sem plano de reversão — esta mudança é irreversível.',
  'proposal.queued': 'Esta mudança é posta em fila em vez de aplicada.',
  // O que o pior efeito colateral da ação proposta significa, para a linha
  // Autonomia acima — os mesmos valores que security.py declara, do menos ao
  // mais perigoso, em palavras em vez do nome cru que o deployment manda.
  'sideEffect.chip.read': 'Leitura',
  'sideEffect.chip.read_sensitive': 'Leitura sensível',
  'sideEffect.chip.write_reversible': 'Escrita reversível',
  'sideEffect.chip.write_irreversible': 'Escrita irreversível',
  'sideEffect.chip.destructive': 'Destrutiva',
  'sideEffect.level.read': 'Leitura — nada muda no parque.',
  'sideEffect.level.read_sensitive':
    'Leitura sensível — nada muda, mas o que volta deve ser tratado com cuidado.',
  'sideEffect.level.write_reversible':
    'Escrita reversível — isso muda o parque, e a mudança pode ser desfeita.',
  'sideEffect.level.write_irreversible':
    'Escrita irreversível — isso muda o parque de um jeito que não pode ser desfeito.',
  'sideEffect.level.destructive':
    'Destrutiva — isso remove algo do parque, sem nada para reverter.',

  'resources.column.name': 'Recurso',
  'resources.column.kind': 'Tipo',
  'resources.column.parent': 'Pai',
  'resources.column.state': 'Estado',
  'resources.column.utilisation': 'Utilização',
  'resources.column.lastSeen': 'Visto',
  'resources.column.zone': 'Zona',
  'resources.column.criticality': 'Criticidade',
  'resources.filter.zone': 'Zona',
  'resources.filter.criticality': 'Criticidade',
  'resources.filter.health': 'Saúde',
  'resources.filter.problem': 'Degradados ou não saudáveis',
  'resources.zone.unplaced': 'Sem zona',
  'resources.zone.unplaced.hint':
    'Nenhuma rede declarada cobre o endereço deste recurso. Declare a zona dele na configuração.',
  'resources.criticality.ungraded': 'Sem classificação',
  'resources.criticality.ungraded.hint':
    'Ninguém declarou a criticidade deste recurso. Declare-a na configuração.',
  'resources.list.title': 'Recursos',
  'resources.list.caption': 'Tudo o que esta instalação vigia',
  'resources.sorted': 'Pior primeiro',
  'resources.sorted.hint':
    'A ordem padrão — clique no cabeçalho de uma coluna abaixo para ordenar de outro jeito.',
  'resources.none.placedOrGraded':
    'Nada neste ambiente foi colocado em uma zona nem teve criticidade definida ainda.',
  'resources.none.placed': 'Nada neste ambiente foi colocado em uma zona ainda.',
  'resources.none.graded': 'Nada neste ambiente teve criticidade definida ainda.',
  'resources.none.action': 'Declarar',
  'resources.summary.watched': 'observados',
  'resources.summary.unaccounted': 'sem estado',
  'resources.summary.watched.count': '{count} vigiados',
  'resources.summary.legend': '{count} {health}',
  'resources.order.worst': 'Piores primeiro',
  'resources.card.lastSeen': 'visto {when}',
  'resources.card.unhealthySince': '{since} fora',
  'resources.filter.kind.any': 'Todos',
  'resources.node.none': 'Sem nó declarado',
  'resources.node.count': '{count} recursos neste nó',
  'resources.node.unhealthyCount': '{count} não saudáveis',
  'resources.node.seeUnhealthy': 'Ver os {count} não saudáveis de {node} →',
  'resources.node.seeAll': 'Ver os {count} recursos de {node} →',
  'resources.synthesis.line':
    '{count} {kind} não saudáveis há mais de {since} — todos em {node}, mesma janela de início',
  'resources.synthesis.action': 'investigar em lote →',
  'resources.synthesis.objective':
    'O que derrubou {count} {kind} em {node} desde {since}?',
  'resources.filter.name': 'Nome do recurso',
  'resources.divergent.mark': '(fora do inventário)',
  'resources.divergent.hint':
    'O inventário declarado é o arquivo que diz o que deveria existir aqui, e este recurso não está nele. Adicione-o ao inventário, ou ignore se ele não deveria ser rastreado.',
  'resources.detail.back': 'Voltar à lista',
  'resources.signals.title': 'De onde vêm os sinais dele',
  'resources.signals.body':
    'Qual fonte responde cada pergunta sobre este recurso, e por qual chave. Um container compartilha o kernel do host, então o uso de recursos dele é lido da série do próprio host e não de dentro do guest.',
  'resources.signals.missing': 'nada configurado responde isso',
  'resources.documents.title': 'O que já se escreveu sobre ele',
  'resources.documents.body':
    'Documentos do corpus que nomeiam este recurso, com o nome que cada um usou. Uma ligação feita por nome pode estar errada \u2014 o nome está aqui para você julgar.',
  'resources.changes.title': 'O que mudou por baixo dele',
  'resources.changes.body':
    'Mudanças correlacionadas pelo recurso, não pelo relógio. Uma mudança marcada como gerenciando este recurso alterou algo que o governa; uma marcada como coincidência apenas divide a janela, e está aqui para você descartá-la.',
  'resources.changes.manages': 'gerencia este recurso',
  'resources.changes.policy': 'política compartilhada',
  'resources.changes.coincidence': 'apenas a mesma janela',
  'resources.changes.unapplied': 'commitada, nunca aplicada',
  'resources.departed.title': 'Declarado e ausente',
  'resources.departed.body':
    'O inventário ainda nomeia estes e a fonte não os reporta mais. Um recurso que existe só num arquivo é um recurso que não existe mais.',
  'resources.undeclared.title': 'Fora do inventário',
  'resources.undeclared.body':
    'A fonte reporta estes e o inventário declarado não os nomeia. Adicione-os ao inventário, ou ignore se não deveriam ser rastreados.',
  'resources.unresolved.title': 'Alertas sobre o que não está aqui',
  'resources.unresolved.body':
    'Algo está alertando sobre um alvo que este parque não contém. Ou ninguém o varreu ainda, ou um receptor de alertas aponta para a implantação errada — e vale saber qual dos dois.',
  'resources.empty.heading': 'Ainda não há recursos',
  'resources.empty.body':
    'Ligue uma fonte de infra-estrutura e o parque preenche-se sozinho dentro de um minuto. Nada aqui é introduzido à mão.',
  'resources.empty.action': 'Ligar uma fonte',

  'detectors.column.name': 'Detector',
  'detectors.column.watches': 'O que vigia',
  'detectors.column.severity': 'Gravidade',
  'detectors.column.coverage': 'Cobertura',
  'detectors.column.verdict': 'Último veredicto',
  'detectors.column.enabled': 'Ativo',
  'detectors.state.enabled': 'Ativo',
  'detectors.state.disabled': 'Inativo',
  'detectors.proposed': 'proposto por um documento',
  'detectors.list.title': 'Detectores',
  'detectors.list.caption':
    'Cada detector, o que vigia e o que encontrou da última vez',
  'detectors.empty.heading': 'Ainda não há detectores',
  'detectors.empty.body':
    'Os detectores vêm com a instalação e aparecem aqui assim que a observação contínua estiver rodando.',
  'detectors.empty.action': 'Ligar uma fonte',
  'detectors.control.dryRun': 'Pré-visualizar o que isto dispararia',
  'detectors.control.dryRunning': 'Verificando…',
  'detectors.control.wouldFire': 'Isto dispararia com o que está armazenado agora.',
  'detectors.control.wouldNotFire':
    'Isto não dispararia com o que está armazenado agora.',
  'detectors.control.observations': 'O que concluiria agora',
  'detectors.control.noObservations': 'Nada é observado para este detector ainda.',
  'detectors.control.enable': 'Ativar',
  'detectors.control.enabling': 'Ativando…',
  'detectors.control.disable': 'Desativar',
  'detectors.control.disabling': 'Desativando…',
  'detectors.control.cancel': 'Cancelar',
  'detectors.control.failed': 'A instalação recusou isto.',
  'detectors.control.unreachable': 'Não foi possível contatar a instalação.',

  // --- Schedules -------------------------------------------------------------------------
  'schedules.title': 'Investigações agendadas',
  'schedules.caption':
    'Cada investigação recorrente que esta equipe agendou, e em que corre',
  'schedules.empty.heading': 'Ainda não há investigações agendadas',
  'schedules.empty.body':
    'Um agendamento corre uma investigação segundo uma expressão cron, por si só, sem que alguém a inicie. Ainda não há nenhum configurado para esta equipe.',
  'schedules.empty.action': 'Criar um abaixo',
  'schedules.column.name': 'Nome',
  'schedules.column.cron': 'Cron',
  'schedules.column.objective': 'Objetivo',
  'schedules.column.timezone': 'Fuso horário',
  'schedules.column.nextRun': 'Próxima investigação',
  'schedules.column.enabled': 'Ativo',
  'schedules.never': 'Não agendado',
  'schedules.frequency.daily': 'Todo dia às {time}',
  'schedules.frequency.weekdays': 'De segunda a sexta, às {time}',
  'schedules.frequency.weekly': 'Toda {weekday} às {time}',
  'schedules.frequency.monthly': 'Todo dia 1º do mês, às {time}',
  'schedules.enable': 'Ativar',
  'schedules.enabling': 'Ativando…',
  'schedules.disable': 'Desativar',
  'schedules.disabling': 'Desativando…',
  'schedules.save': 'Salvar',
  'schedules.saving': 'Salvando…',
  'schedules.delete': 'Excluir agendamento',
  'schedules.deleteConsequence':
    'Esta investigação agendada é removida imediatamente, e nada a repõe a partir daqui.',
  'schedules.deleteCancel': 'Cancelar',
  'schedules.deleteClose': 'Fechar',
  'schedules.create.title': 'Agendar uma nova investigação',
  'schedules.create.jobId': 'Identificador',
  'schedules.create.name': 'Nome',
  'schedules.create.cron': 'Cron',
  'schedules.create.objective': 'Objetivo',
  'schedules.create.timezone': 'Fuso horário',
  'schedules.create.jobIdHelp':
    'Um identificador estável que este agendamento mantém mesmo se o nome mudar depois.',
  'schedules.create.nameHelp':
    'O que os operadores veem nesta lista. Pode renomear à vontade; o identificador não muda.',
  'schedules.create.cronHelp':
    'Cinco campos — minuto, hora, dia do mês, mês, dia da semana. `0 8 * * 1` roda toda segunda às 08:00.',
  'schedules.create.objectiveHelp':
    'A instrução com que a investigação roda, exatamente como se alguém a tivesse digitado para começar uma à mão.',
  'schedules.create.timezoneHelp':
    'O fuso em que a expressão cron é lida. Um nome IANA, como America/Sao_Paulo.',
  'schedules.create.frequency': 'Frequência',
  'schedules.create.frequencyHelp':
    'Uma frequência legível, que escreve no campo cron acima em vez de substituí-lo.',
  'schedules.create.frequency.custom': 'Cron personalizado',
  'schedules.create.frequency.daily': 'Todo dia',
  'schedules.create.frequency.weekdays': 'Todo dia útil (segunda a sexta)',
  'schedules.create.frequency.weekly': 'Toda semana, em um dia escolhido',
  'schedules.create.frequency.monthly': 'Todo mês, no dia 1',
  'schedules.create.weekday': 'Dia da semana',
  'schedules.create.weekday.monday': 'Segunda-feira',
  'schedules.create.weekday.tuesday': 'Terça-feira',
  'schedules.create.weekday.wednesday': 'Quarta-feira',
  'schedules.create.weekday.thursday': 'Quinta-feira',
  'schedules.create.weekday.friday': 'Sexta-feira',
  'schedules.create.weekday.saturday': 'Sábado',
  'schedules.create.weekday.sunday': 'Domingo',
  'schedules.create.time': 'Horário',
  'schedules.create.submit': 'Criar agendamento',
  'schedules.create.submitting': 'Criando…',
  'schedules.create.created': 'Agendamento criado: {name}.',
  'schedules.create.previewing': 'Verificando a expressão cron…',
  'schedules.create.previewLabel': 'Próximo disparo previsto:',
  'schedules.failed': 'A instalação recusou isto.',
  'schedules.unreachable': 'Não foi possível contatar a instalação.',

  'memory.episodes.title': 'Episódios',
  'memory.episodes.caption': 'O que as investigações passadas deixaram',
  'memory.column.title': 'Episódio',
  'memory.column.outcome': 'Desfecho',
  'memory.column.components': 'Componentes',
  'memory.column.occurred': 'Ocorreu',
  'memory.filter.component': 'Componente',
  'memory.filter.outcome': 'Desfecho',
  'memory.componentType.service': 'serviços',
  'memory.componentType.node': 'nós',
  'memory.componentType.guest': 'guests',
  'memory.componentType.cluster': 'cluster',
  'memory.episode.outcome.resolved': 'Resolvido',
  'memory.episode.outcome.mitigated': 'Mitigado',
  'memory.episode.outcome.inconclusive': 'Inconclusivo',
  'memory.episode.outcome.falsePositive': 'Falso positivo',
  'memory.episode.openInvestigation': 'abrir investigação →',
  'memory.count': '{count} episódios',
  'memory.learned.title': 'O que o agente aprendeu com isso',
  'memory.learned.empty':
    'Nada destilado ainda. Aprendizados são propostos quando episódios concordam entre si, e esperam aqui por revisão.',
  'memory.learned.from': 'de {run}',
  'memory.learned.promote': 'promover a documento',
  'memory.preview.documents': '{count} documentos ingeridos',
  'memory.preview.documents.empty': 'Documentos — nada ingerido ainda',
  'memory.preview.open': 'abrir →',
  'memory.preview.topology': '{count} nós observados',
  'memory.preview.topology.empty': 'Topologia — nada observado ainda',
  'memory.search': 'Procurar episódios',
  'memory.stats.title': 'O que o acervo contém',
  'memory.stats.episodes': 'Episódios',
  'memory.episodes.empty.heading': 'Ainda não há episódios',
  'memory.episodes.empty.body':
    'Um episódio é escrito quando uma investigação termina, e nenhum foi escrito ainda.',
  'memory.episodes.empty.mechanism':
    'Um episódio é escrito quando uma investigação termina.',
  'memory.episodes.empty.action': 'Ver o que está em execução',
  'memory.strategies.title': 'Estratégias',
  'memory.strategies.lead':
    'Uma estratégia é sintetizada a partir dos episódios abaixo, juntamente com os anti-padrões que esses episódios produziram.',
  'memory.strategies.supporting': 'Episódios de apoio',
  'memory.strategies.antipatterns': 'Anti-padrões',
  'memory.strategies.edit': 'Editar esta estratégia',
  'memory.strategies.empty.heading': 'Ainda não há estratégias',
  'memory.strategies.empty.body':
    'Uma estratégia é sintetizada quando episódios suficientes concordam sobre o que resultou. Não foram registrados que cheguem.',
  'memory.strategies.empty.action': 'Ver os episódios',

  'knowledge.documents.title': 'Documentos',
  'knowledge.documents.caption': 'Os documentos que uma investigação pode ler',
  'knowledge.column.title': 'Documento',
  'knowledge.column.kind': 'Tipo',
  'knowledge.column.updated': 'Atualizado',
  'knowledge.search': 'Procurar na base de conhecimento',
  'knowledge.documents.empty.heading': 'Nada foi ingerido',
  'knowledge.documents.empty.body':
    'Ainda nada, e este console não tem nenhum controle de upload nem de ligar uma fonte para oferecer. Um documento chega a este corpus quando a sincronização com que o deployment foi configurado o traz, ou quando uma investigação propõe um e alguém o aprova.',
  'knowledge.documents.empty.action': 'Ver o que foi proposto',
  'knowledge.proposals.title': 'Proposto por um agente',
  'knowledge.proposals.lead':
    'Mudanças que uma investigação propôs, à espera de revisão na mesma fila de qualquer outra mudança proposta.',
  'knowledge.proposals.empty.heading': 'Nada está à espera de revisão',
  'knowledge.proposals.empty.body':
    'Quando uma investigação aprende algo que vale a pena escrever, propõe a mudança aqui em vez de a fazer.',
  'knowledge.proposals.empty.action': 'Ver os documentos',
  'knowledge.advanced.heading': 'Ajustes avançados',
  'knowledge.advanced.changes.title': 'Origem das mudanças',
  'knowledge.advanced.status.none': 'nenhuma configurada',
  'knowledge.advanced.status.changes': 'ligada a {vendor}',
  'knowledge.advanced.status.consulting': 'consultando {parts}',
  'knowledge.advanced.status.nothing': 'não consultando nada',
  'knowledge.advanced.status.topology': 'topologia',
  'knowledge.advanced.status.documents': 'documentos',
  'knowledge.advanced.status.saving': 'guardando · {count} episódios',
  'knowledge.advanced.status.notSaving': 'não guardando',
  'knowledge.advanced.status.on': 'ligada',
  'knowledge.advanced.status.off': 'desligada',
  'knowledge.advanced.field.repositoryPath': 'Caminho do repositório',
  'knowledge.advanced.field.gitHostVendor': 'Provedor do git host',
  'knowledge.advanced.field.gitHostRepository': 'Repositório do git host',
  'knowledge.advanced.knowledge.title': 'Acesso ao conhecimento',
  'knowledge.advanced.field.topologyEnabled': 'Seguir a topologia de recursos',
  'knowledge.advanced.field.knowledgeBaseEnabled': 'Buscar na base de conhecimento',
  'knowledge.advanced.memory.title': 'Memória episódica',
  'knowledge.advanced.field.memoryReadEnabled': 'Recuperar incidentes anteriores',
  'knowledge.advanced.field.memoryWriteEnabled': 'Registrar investigações concluídas',
  'knowledge.advanced.strategy.title': 'Estratégia',
  'knowledge.advanced.field.strategyEnabled': 'Oferecer playbooks destilados',

  'topology.graph.title': 'Vizinhança',
  'topology.list.title': 'O mesmo grafo, em lista',
  'topology.dependencies': 'Depende de',
  'topology.dependents': 'Dependem dele',
  'topology.blast': 'Raio de impacto',
  'topology.depth': 'Profundidade {depth}',
  'topology.bounded':
    'A mostrar {shown} de {total} vizinhos; a lista abaixo tem todos.',
  'topology.select': 'Escolher um nó',
  'topology.empty.heading': 'Nenhuma topologia registrada',
  'topology.empty.body':
    'O grafo é construído a partir do que as investigações observam. Nada foi observado sobre este nó.',
  'topology.empty.action': 'Ver o parque',

  'autonomy.tabs':
    'O que esta instalação pode fazer sozinha, quando não pode, e o que sempre vale',
  'autonomy.tab.posture': 'Postura',
  'autonomy.tab.rules-windows': 'Regras e janelas',
  'autonomy.tab.guardrails': 'Guardrails',
  'autonomy.subtitle': 'Nó: {node} · Postura agora: {posture}',
  'autonomy.subtitle.override':
    'Nó: {node} · Postura agora: {posture}, por uma exceção temporária',
  'autonomy.posture.title': 'O que esta instalação pode fazer sozinha',
  'autonomy.posture.save': 'Salvar postura',
  'autonomy.posture.empty.scopeLead':
    'Regras que estreitam ou ampliam um âmbito vivem em',
  'autonomy.posture.guardrails.title': 'Guardrails em vigor',
  'autonomy.rules.title': 'Regras, por ordem de resolução',
  'autonomy.column.scope': 'Âmbito',
  'autonomy.column.matcher': 'Seletor',
  'autonomy.column.level': 'Nível',
  'autonomy.column.risk': 'Limite de risco',
  'autonomy.column.applies': 'Aplica-se a',
  'autonomy.editor.level': 'Nível',
  'autonomy.editor.simulation.title': 'Simular esta mudança',
  'autonomy.editor.simulation.description':
    'Repete o que este nó decidiu de fato recentemente, sob a mudança acima, e diz o que seria diferente — o botão de salvar aparece assim que você vê isso.',
  'autonomy.editor.preview': 'O que isto decidiria de forma diferente?',
  'autonomy.editor.previewing': 'Perguntando ao deployment…',
  'autonomy.editor.explain': 'Explicar',
  'autonomy.editor.explaining': 'Explicando…',
  'autonomy.editor.explainIntro': 'Ou verifique uma única ação hipotética:',
  'autonomy.editor.capability': 'Capacidade',
  'autonomy.editor.resource': 'Recurso',
  'autonomy.editor.save': 'Salvar esta postura',
  'autonomy.editor.saving': 'Salvando…',
  'autonomy.editor.saved':
    'Guardado. É isto que o deployment pode fazer sozinho agora.',
  'autonomy.editor.failed': 'O deployment recusou esta postura.',
  'autonomy.editor.unreachable': 'Não foi possível alcançar o deployment.',
  'autonomy.editor.previewFirst':
    'Veja o que isto teria decidido de forma diferente antes de salvar. A lista do que passa a ser autônomo é a metade que importa ler.',
  'autonomy.editor.considered': 'Consideradas',
  'autonomy.editor.changed': 'Decididas diferente',
  'autonomy.editor.newlyAutonomous': 'Passam a autônomas',
  'autonomy.editor.nothingChanges': 'Nada passaria a ser mais autônomo.',
  'autonomy.editor.dryRunOn': 'Simular toda decisão do deployment',
  'autonomy.editor.dryRunOff': 'Voltar a decidir de verdade',
  'autonomy.editor.dryRunBanner':
    'Simulando: cada ação é decidida e nenhuma é executada. Este deployment propõe e não age.',
  'autonomy.editor.decision': 'Decisão',
  'autonomy.editor.winningRule': 'Regra vencedora',
  'autonomy.override.duration': 'Expira',
  'autonomy.override.reason': 'Concedido porque',
  'autonomy.override.grantedBy': 'Concedido por',
  'autonomy.override.temporary.title': 'Exceção temporária',
  'autonomy.override.temporary.close': 'Fechar',
  'autonomy.override.panel.title': 'Conceder ou revogar uma exceção',
  'autonomy.override.grant.title': 'Conceder uma exceção',
  'autonomy.override.grant.name': 'Nome',
  'autonomy.override.grant.nameHelp':
    'Um identificador curto para esta exceção, único neste nó. Aparece na trilha de auditoria e é o nome que uma revogação usa.',
  'autonomy.override.grant.level': 'Nível',
  'autonomy.override.grant.reason': 'Motivo — registrado na trilha de auditoria',
  'autonomy.override.grant.reasonHelp':
    'Registrado na trilha de auditoria junto com a exceção, para quem for revisá-la depois.',
  'autonomy.override.grant.duration': 'Duração',
  'autonomy.override.grant.durationDefault': 'Padrão (2 horas)',
  'autonomy.override.grant.durationOneHour': '1 hora',
  'autonomy.override.grant.durationEightHours': '8 horas',
  'autonomy.override.grant.durationTwentyFourHours': '24 horas',
  'autonomy.override.grant.durationCustom': 'Duração personalizada…',
  'autonomy.override.grant.seconds': 'Segundos (opcional)',
  'autonomy.override.grant.submit': 'Conceder',
  'autonomy.override.grant.granting': 'Concedendo…',
  'autonomy.override.grant.granted': 'Concedida. Vai expirar sozinha.',
  'autonomy.override.grant.reasonRequired':
    'É preciso um motivo antes que isto possa ser concedido.',
  'autonomy.override.revoke.title': 'Revogar uma exceção',
  'autonomy.override.revoke.empty': 'Nenhuma exceção está ativa neste nó agora.',
  'autonomy.override.revoke.submit': 'Revogar',
  'autonomy.override.revoke.revoking': 'Revogando…',
  'autonomy.override.revoke.revoked': 'Revogada.',
  'autonomy.override.failed': 'O deployment recusou isto.',
  'autonomy.override.unreachable': 'Não foi possível alcançar o deployment.',
  'autonomy.footer': 'A ausência de uma regra resolve para apenas-propor.',
  'autonomy.dry_run': 'Tudo aqui é simulado: o modo de simulação está ligado neste nó.',
  'autonomy.bound.stopped': 'Escritas automáticas paradas',
  'autonomy.bounds.title': 'Limites e exceções de nível',
  'autonomy.preview.title': 'Pré-visualizar antes de aplicar',
  'autonomy.preview.lead':
    'O que a mudança pendente teria feito contra o histórico registrado.',
  'autonomy.preview.apply': 'Aplicar esta postura',
  'autonomy.empty.heading': 'Nenhuma política registrada',
  'autonomy.empty.body':
    'Sem regra registrada, tudo resolve para apenas-propor. Esse é o comportamento seguro, não um erro.',
  'autonomy.cta.createRule': 'Criar a primeira regra',
  'autonomy.cta.recordBound': 'Registrar um congelamento ou um teto',
  'autonomy.cta.grantOverride': 'Conceder uma exceção',
  'autonomy.glossary.rule':
    'Uma regra decide o que este deployment pode fazer para um âmbito, do deployment inteiro até um único recurso — lida em ordem, da menos específica à mais específica.',
  'autonomy.glossary.bound':
    'Um limite é um teto que nenhuma regra ultrapassa — a parada de emergência, uma janela de congelamento, um teto de gasto — verificado depois que uma regra decide, e capaz de recusar o que ela decidiu.',
  'autonomy.glossary.override':
    'Uma exceção é um aumento temporário e justificado do nível de um âmbito, concedida em registro e encerrada assim que expira ou é revogada.',
  'autonomy.editor.newRule.title': 'Criar uma regra',
  'autonomy.editor.newRule.scope': 'Âmbito',
  'autonomy.editor.newRule.level': 'Nível',
  'autonomy.editor.newRule.team': 'Time',
  'autonomy.editor.newRule.resourceKind': 'Tipo de recurso',
  'autonomy.editor.newRule.resourceId': 'Recurso',
  'autonomy.editor.newRule.capability': 'Capacidade',
  'autonomy.editor.newRule.labelName': 'Nome do rótulo',
  'autonomy.editor.newRule.labelValue': 'Valor do rótulo',
  'autonomy.editor.newRule.add': 'Adicionar regra',
  'autonomy.scope.deployment': 'O deployment inteiro',
  'autonomy.scope.team': 'Um time',
  'autonomy.scope.resource_kind': 'Um tipo de recurso',
  'autonomy.scope.labels': 'Recursos que carregam um rótulo',
  'autonomy.scope.capability': 'Uma capacidade',
  'autonomy.scope.resource': 'Um recurso',
  'autonomy.scope.capability_resource': 'Uma capacidade em um recurso',
  'autonomy.freezes.title': 'Criar uma janela de congelamento',
  'autonomy.freeze.name': 'Nome',
  'autonomy.freeze.start': 'Começa',
  'autonomy.freeze.end': 'Termina',
  'autonomy.freeze.reason': 'Motivo',
  'autonomy.freeze.add': 'Adicionar congelamento',
  'autonomy.budgets.title': 'Criar um teto de gasto',
  'autonomy.budget.name': 'Nome',
  'autonomy.budget.limit': 'Limite',
  'autonomy.budget.countedBy': 'Contado por',
  'autonomy.budget.add': 'Adicionar teto',

  'configuration.tree.title': 'Organização',
  'configuration.values.title': 'Configuração efetiva',
  'configuration.column.setting': 'Definição',
  'configuration.column.value': 'Valor',
  'configuration.column.provenance': 'Definido em',
  'configuration.locked': 'Bloqueado aqui',
  'configuration.required': 'Obrigatório',
  'configuration.gated': 'Sujeito a aprovação',
  'configuration.locked.detail': 'Uma mudança feita aqui seria recusada.',
  'configuration.required.detail': 'Este valor não pode ser limpo.',
  'configuration.gated.detail':
    'Salvar isto põe a mudança em fila em vez de a aplicar.',
  'configuration.preview.title': 'O que salvar iria resolver',
  'configuration.preview.lead':
    'Foi a instalação que calculou isto, não o console. Uma junção do lado do cliente que concorda hoje é uma que discorda depois da próxima mudança.',
  'configuration.preview.before': 'Agora',
  'configuration.preview.after': 'Depois de salvar',
  'configuration.preview.empty.heading': 'Nada mudaria',
  'configuration.preview.empty.body':
    'Uma pré-visualização é a resposta da instalação a uma alteração. Não há nenhuma pendente para este nó.',
  'configuration.preview.empty.action': 'Ver os valores efetivos',
  'teamContext.sections.title': 'O que este ambiente é',
  'teamContext.sections.lead':
    'Fatos que um operador escreve uma vez e que entram no prompt de toda investigação. São acrescentados ao prompt distribuído, nunca no lugar dele — as substituições de prompt na tela de Configuração são a outra coisa, e essas substituem-no.',
  'teamContext.factNotInstruction':
    'Escreva fatos, não instruções. “As métricas de um container vêm do host, por vmid” muda como o agente lê o que observa; “reinicie sempre o serviço primeiro” é um procedimento, e um procedimento pertence a um runbook ou à política de autonomia, onde é auditável e reversível.',
  'teamContext.runbooks': 'Os runbooks vivem em Conhecimento',
  'teamContext.policy': 'Os procedimentos vivem em Autonomia',
  'teamContext.column.section': 'Seção',
  'teamContext.column.body': 'O que diz',
  'teamContext.provenance': 'Definido em',
  'teamContext.budget': 'Orçamento do prompt',
  'teamContext.budgetUsed': 'de {budget} tokens · {percent}%',
  'teamContext.budgetConsequence':
    'O que ultrapassa o orçamento é recusado, não truncado.',
  'teamContext.overBudget':
    'Acima do orçamento. A instalação recusa isto enquanto não for mais curto.',
  'teamContext.disabled':
    'O contexto operacional está desligado neste nó. Fica guardado e nada é enviado.',
  'teamContext.addSection': 'Acrescentar uma seção',
  'teamContext.addSection.disabledReason':
    'Digite um nome antes de acrescentar uma seção.',
  'teamContext.sectionName': 'Nome da seção',
  'teamContext.remove': 'Limpar esta seção',
  'teamContext.empty.heading': 'Ainda não há nada escrito aqui',
  'teamContext.empty.body':
    'Nenhum nível desta árvore escreveu contexto operacional, portanto cada investigação parte apenas do prompt distribuído. O documento inicial abaixo é derivado do que esta instalação já descobriu.',
  'teamContext.empty.action': 'Ver a organização',
  'teamContext.template.title': 'Um ponto de partida, a partir do que já se sabe',
  'teamContext.template.lead':
    'Derivado do próprio parque desta instalação — os tipos que tem, as zonas em que os endereços estão, a fonte que responde a cada pergunta de sinal. Nada aqui fica escrito até salvar.',
  'teamContext.template.use': 'Usar o documento inicial',
  'teamContext.preview.title': 'O que o modelo vai receber',
  'teamContext.preview.lead':
    'O texto exato que o prompt de sistema da próxima investigação vai levar, montado pela instalação. O botão de salvar aparece quando o tiver pedido.',
  'teamContext.preview.submit': 'Mostrar o prompt final',
  'teamContext.preview.disabledReason': 'Altere uma seção antes de pedir o prompt.',
  'teamContext.preview.previewing': 'Montando…',
  'teamContext.preview.first':
    'Veja o prompt antes de o salvar. Este texto é enviado em cada chamada ao modelo de cada investigação.',
  'teamContext.save': 'Salvar',
  'teamContext.saving': 'Salvando…',
  'teamContext.saved': 'Guardado. A próxima investigação leva isto.',
  'teamContext.failed': 'O deployment recusou este contexto.',
  'teamContext.unreachable': 'Não foi possível contatar o deployment.',
  'teamContext.roles': 'Enviado para',
  'teamContext.role.investigator': 'Investigador',
  'teamContext.role.subagent': 'Subagente',
  'teamContext.rolesNote': 'Os dois papéis leem as mesmas seções.',
  'teamContext.savedNote':
    'Salvo por deployment — cada investigação nova já nasce lendo isto.',
  'teamContext.example.factLabel': 'Fato:',
  'teamContext.example.factQuote': '"Métricas de contêiner vêm do host, por vmid"',
  'teamContext.example.factTail': '— muda como o agente lê o que vê.',
  'teamContext.example.instructionLabel': 'Instrução:',
  'teamContext.example.instructionQuote': '"sempre reinicie o serviço primeiro"',
  'teamContext.example.instructionTail': '— procedimento não mora aqui.',

  'configuration.editor.title': 'Mudar o que se aplica aqui',
  'configuration.editor.lead':
    'Cada controle abaixo vem do esquema do próprio deployment. Mude o que precisar e depois veja o que salvar iria resolver — o botão de salvar aparece quando o tiver visto.',
  'configuration.editor.submit': 'Pré-visualizar esta mudança',
  'configuration.editor.save': 'Salvar',
  'configuration.editor.saving': 'Salvando…',
  'configuration.editor.saved': 'Guardado. Os valores acima são os novos.',
  'configuration.editor.failed': 'O deployment recusou esta mudança.',
  'configuration.editor.unreachable': 'Não foi possível contatar o deployment.',
  'configuration.editor.previewFirst':
    'Pré-visualize esta mudança antes de a salvar — o diff é o único lugar onde a herança é visível.',
  'configuration.editor.clear': 'Remover esta substituição',
  'configuration.editor.cleared': 'Vai voltar a ser herdado',
  'configuration.editor.redundant': 'Já é herdado com este valor de',
  'configuration.editor.reverts': 'Volta a',
  'configuration.editor.notEditable':
    'Uma lista ou uma seção livre: é substituída por inteiro na escrita, por isso não se edita campo a campo.',
  'configuration.editor.inherited': 'ainda nada',
  'configuration.editor.addEntry': 'Adicionar outro',
  'configuration.editor.removeEntry': 'Remover',
  'configuration.editor.moveUp': 'Mover para antes',
  'configuration.editor.moveDown': 'Mover para depois',
  'configuration.editor.entryPosition': 'Avaliada',
  'configuration.editor.emptyList': 'Nada declarado aqui ainda.',
  'configuration.editor.useSuggested': 'Usar o endereço encontrado aqui:',
  'configuration.editor.setAt': 'Definido em:',
  'configuration.editor.usingDefault': 'Usando o padrão do deployment:',
  'configuration.editor.toc': 'Ir para uma seção',
  'configuration.editor.search': 'Buscar um campo',
  'configuration.editor.searchEmpty': 'Nenhum campo corresponde a esta busca.',
  'configuration.editor.generalSection': 'Geral',
  'configuration.section.policiesMasking': 'Masking',
  'configuration.section.policiesGuardrails': 'Guardrails',
  'configuration.section.policiesApprovals': 'Aprovações',
  'configuration.section.policiesAutonomy': 'Autonomia',
  'configuration.section.notificationPolicy': 'Política de notificação',
  'configuration.provenance.default': 'Padrão do deployment',
  'configuration.provenance.setAt': 'Definido em: {node}',
  'configuration.provenance.mixed': 'Definido em mais de um nó',
  'configuration.value.on': 'Ativado',
  'configuration.value.off': 'Desativado',
  'configuration.value.notSet': 'Não definido',
  'configuration.value.hours.one': '{count} hora',
  'configuration.value.hours': '{count} horas',
  'configuration.value.seconds.one': '{count} segundo',
  'configuration.value.seconds': '{count} segundos',
  'configuration.empty.heading': 'Nenhuma configuração aqui',
  'configuration.empty.body':
    'Cada nó herda do nó acima. Este não define nada de seu, por isso o que se aplica é o que o pai aplica.',
  'configuration.empty.action': 'Ver a organização',

  'catalogue.title': 'Capacidades',
  'catalogue.tools': 'Ferramentas',
  'catalogue.skills': 'Competências',
  'catalogue.search': 'Nome, domínio ou capacidade',
  'catalogue.search.empty': 'Nada aqui corresponde a essa busca.',
  'catalogue.domains.nav': 'Ir para um domínio',
  'catalogue.count': '{enabled} de {total} habilitadas',
  'catalogue.column.name': 'Capacidade',
  'catalogue.column.domain': 'Domínio',
  'catalogue.column.effect': 'Efeito',
  'catalogue.column.integrations': 'Precisa de',
  'catalogue.column.enabled': 'Ativa aqui',
  'catalogue.state.enabled': 'Ativa',
  'catalogue.state.disabled': 'Inativa',
  'catalogue.blocked': 'Requer a integração {integration}',
  'catalogue.blocked.action': 'Conectar',
  'catalogue.empty.heading': 'Nenhuma capacidade declarada',
  'catalogue.empty.body':
    'Uma capacidade é declarada pela instalação e não configurada aqui. Esta não declara nenhuma.',
  'catalogue.empty.action': 'Ver a configuração',
  'catalogue.gaps.title': 'Não coberto, e por quê',
  'catalogue.gaps.decided': '— avaliado e descartado',
  'catalogue.gaps.unreachable': '— não dá para alcançar daqui',
  'catalogue.gaps.resolution': 'O que mudaria isso:',
  'ingress.title': 'Para onde enviar alertas',
  'ingress.body':
    'O \u00fanico passo que acontece fora desta implanta\u00e7\u00e3o. Aponte o roteador de alertas para o endere\u00e7o do seu tipo e ele vai interpretar o corpo que aquele sistema j\u00e1 envia \u2014 nada aqui \u00e9 escrito na sua pilha de observabilidade.',
  'ingress.verification': 'Confiado por',
  'ingress.delivery.authenticated': 'Autenticado com o token de entrega',
  'ingress.delivery.unauthenticated': 'Nenhum token de entrega autenticou isso ainda.',
  'ingress.token.issue': 'Emitir um token de entrega',
  'ingress.token.issuing': 'Emitindo\u2026',
  'ingress.token.rotate': 'Rotacionar',
  'ingress.token.shownOnce':
    'Copie agora. \u00c9 mostrado uma vez e nunca mais pode ser lido \u2014 o deployment guarda apenas um hash dele.',
  'ingress.token.failed': 'O deployment recusou a emiss\u00e3o.',
  'ingress.token.unreachable': 'N\u00e3o foi poss\u00edvel alcan\u00e7ar o deployment.',
  'firstRun.integrations.foundHere': 'Encontrado no seu estate em',
  'catalogue.integrations.count.total': 'no catálogo',
  'catalogue.integrations.count.connected': 'conectadas',
  'catalogue.integrations.count.available': 'disponíveis',
  'catalogue.integrations.title': 'Integrações',
  'catalogue.integrations.advanced.title': 'Avançado: vendors configurados',
  'catalogue.integrations.state': 'Ligação',
  'catalogue.integrations.verified': 'Última verificação',
  'catalogue.integrations.verify': 'Verificar agora',
  'catalogue.integrations.expand': 'Mostrar o formulário de credencial',
  'catalogue.integrations.collapse': 'Ocultar o formulário de credencial',
  'catalogue.integrations.empty.heading': 'Nada está ligado',
  'catalogue.integrations.empty.body':
    'Uma integração é o que permite a uma investigação ler ou mudar algo fora desta instalação. Nenhuma está instalada.',
  'catalogue.integrations.empty.action': 'Ver a configuração',
  'catalogue.credential.title': 'Credenciais',
  'catalogue.credential.replace': 'Substituir esta credencial',
  'catalogue.credential.stored':
    'Existe uma credencial guardada. Nunca voltará a ser mostrada.',
  'catalogue.credential.absent': 'Não há credencial guardada.',
  'catalogue.credential.state.unconfigured':
    'Nenhuma credencial está guardada para esta integração ainda.',
  'catalogue.credential.state.unknown':
    'Uma credencial está guardada, mas nada verificou ainda.',
  'catalogue.credential.state.healthy': 'Verificada — a última verificação passou.',
  'catalogue.credential.state.degraded':
    'Falhando — a última verificação encontrou um problema.',
  // Uma palavra cada, para as opções do próprio filtro — as frases acima
  // dizem o mesmo no espaço que um card recolhido permite; o filtro precisa
  // do espaço que uma lista suspensa permite.
  'catalogue.integrations.filter.state.unconfigured': 'Não conectada',
  'catalogue.integrations.filter.state.unknown': 'Armazenada',
  'catalogue.integrations.filter.state.healthy': 'Verificada',
  'catalogue.integrations.filter.state.degraded': 'Falhando',

  // --- O catálogo de integrações: conectadas primeiro, o resto é uma busca ---------
  'catalogue.integrations.summary.suggested':
    '{suggested} delas já estão rodando neste ambiente — conecte uma e ela deixa de ser um chute.',
  'catalogue.integrations.connected.title': 'Conectadas',
  'catalogue.integrations.connected.manage': 'Gerenciar',
  'catalogue.integrations.filter.view.connected': 'Conectadas · {count}',
  'catalogue.integrations.filter.view.suggested': 'Sugeridas · {count}',
  'catalogue.integrations.available.title': 'Disponíveis',
  'catalogue.integrations.suggested.title': 'Sugerida pelo seu ambiente',
  'catalogue.integrations.suggested.evidence':
    'Encontrado em {address}, no recurso {resource}',
  // O ambiente encontrou o fornecedor, mas não resolveu um nome legível para o
  // recurso em que ele está rodando. Endereço e tipo, nunca o identificador
  // cru — que continua recuperável como atributo de dado, fora desta frase.
  'catalogue.integrations.suggested.evidence.unresolved':
    'Encontrado em {address}, em um recurso do tipo {kind}',
  'catalogue.integrations.suggested.connect': 'Conectar',
  'catalogue.integrations.search.label': 'Buscar por nome, categoria ou capacidade',
  'catalogue.integrations.search.empty.heading': 'Nada corresponde a isso',
  'catalogue.integrations.search.empty.body':
    'Nenhuma integração do catálogo corresponde a esta busca ou filtro.',
  'catalogue.integrations.search.empty.clear': 'Limpar a busca',
  'catalogue.integrations.filter.category': 'Categoria',
  'catalogue.integrations.category.logstore': 'Armazenamento de logs',
  'catalogue.integrations.category.metrics': 'Métricas',
  'catalogue.integrations.category.tracing': 'Rastreamento',
  'catalogue.integrations.category.cloud_control_plane': 'Nuvem',
  'catalogue.integrations.category.database': 'Banco de dados',
  'catalogue.integrations.category.vcs': 'Controle de versão',
  'catalogue.integrations.category.cicd': 'CI/CD',
  'catalogue.integrations.category.ticketing': 'Emissão de tickets',
  'catalogue.integrations.category.incident': 'Gestão de incidentes',
  'catalogue.integrations.category.communication': 'Chat e plantão',
  'catalogue.integrations.category.data_platform': 'Dados',
  'catalogue.integrations.category.model_provider': 'Provedor de modelo',
  'catalogue.integrations.footer.gaps':
    '{count} integrações movidas para o roadmap · veja a lista e o motivo',
  'catalogue.integrations.panel.close': 'Fechar',
  'catalogue.integrations.panel.notFound': 'Esta integração não está no catálogo.',
  'catalogue.integrations.panel.notFound.action': 'Voltar para Integrações',
  'catalogue.integrations.panel.permissions.heading': 'Permissões exigidas',
  'catalogue.integrations.panel.permissions.grantedAt': 'Concedida em',
  'catalogue.integrations.panel.readOnly':
    'Você não tem a permissão para alterar esta integração.',
  'catalogue.integrations.panel.direction.outbound':
    'Esta implanta\u00e7\u00e3o chama esse servi\u00e7o. Nada chega dele, e a credencial abaixo \u00e9 o que ela apresenta ao chamar.',
  'catalogue.integrations.panel.direction.both':
    'Nos dois sentidos. Esta implanta\u00e7\u00e3o l\u00ea a API dele com a credencial abaixo, e ele envia alertas para c\u00e1 com outra \u2014 um token de entrega, emitido \u00e0 parte.',
  'catalogue.integrations.panel.intake.action':
    'Aponte seu roteador de alertas para c\u00e1',
  'catalogue.integrations.panel.security':
    'Guardada no vault; nunca é exibida de novo. O teste faz uma requisição real — armazenada e funcionando são estados diferentes.',
  'catalogue.integrations.panel.saveAndTest': 'Salvar e testar',
  'catalogue.integrations.panel.testing': 'Salvando e testando…',
  'catalogue.integrations.panel.docs.heading': 'Documentação do pacote',
  'catalogue.integrations.panel.docs.toggle': 'Ler a documentação do pacote',
  'catalogue.integrations.panel.docs.unreadable':
    'A documentação deste fornecedor não pôde ser lida.',
  // Mais de um time detém credencial para este fornecedor. O processo não
  // escolhe um em silêncio: ele cai para o handle da organização, e esta é
  // a frase que diz que essa decisão foi tomada.
  'catalogue.integrations.panel.credentialTeamAmbiguous':
    'Mais de um time detém credencial para este fornecedor. As investigações usam a credencial da organização até isso ser resolvido.',
  // --- Painel de uma integração conectada: estado e ações, nunca um formulário vazio ---
  'catalogue.integrations.panel.storedInVault':
    'Esta credencial está guardada no vault.',
  // Para um fornecedor que não traz autenticação própria. Dizer que há uma
  // credencial guardada onde não há nenhuma manda alguém procurar uma chave
  // que ninguém digitou.
  'catalogue.integrations.panel.connectedByAddress':
    'Este fornecedor não pede credencial própria. Ele está conectado pelo endereço acima.',
  'catalogue.integrations.panel.testAgain': 'Testar de novo',
  'catalogue.integrations.panel.replaceCredential': 'Substituir credencial',
  // Compartilhado por duas saídas: sair de "Substituir credencial" sem
  // salvar, e sair da confirmação de desconexão sem desconectar.
  'catalogue.integrations.panel.cancel': 'Cancelar',
  'catalogue.integrations.panel.disconnect': 'Desconectar',
  'catalogue.integrations.panel.disconnect.consequence':
    'Isso remove a credencial guardada no vault. A integração volta para Disponíveis até ser reconectada.',
  // --- Confiança de certificado: o que este deployment confere no endereço ---------
  'catalogue.integrations.panel.trust.heading': 'Confiança de certificado',
  'catalogue.integrations.panel.trust.intro':
    'O que este deployment aceita do certificado que este endereço apresenta. Declarado para este endereço apenas — trocar o endereço reinicia a decisão.',
  'catalogue.integrations.panel.trust.fingerprintsLabel': 'Fingerprints pinados',
  'catalogue.integrations.panel.trust.fingerprintsHelp':
    'Um fingerprint SHA-256 por linha, copiado da própria interface do nó. Um cluster lista um fingerprint por nó na mesma declaração.',
  'catalogue.integrations.panel.trust.certificateLabel':
    'Autoridade do certificado (PEM)',
  'catalogue.integrations.panel.trust.certificateHelp':
    'A autoridade que o cluster mintou para si mesmo. Cobre todo nó cujo certificado encadeia até ela — a forma que um cluster costuma preferir.',
  'catalogue.integrations.panel.trust.submit': 'Declarar confiança',
  'catalogue.integrations.panel.trust.sending': 'Declarando…',
  'catalogue.integrations.panel.trust.saved': 'Declarado. Testando a conexão agora.',
  'catalogue.integrations.panel.trust.refused': 'O deployment recusou:',
  'catalogue.integrations.panel.trust.unreachable':
    'Não foi possível alcançar o deployment.',
  'catalogue.integrations.panel.trust.unverifiedHeading': 'Aceitar sem verificar',
  'catalogue.integrations.panel.trust.unverifiedReasonLabel': 'Por quê',
  'catalogue.integrations.panel.trust.unverifiedReasonHelp':
    'Registrado com seu nome e o instante da aceitação, porque abrir mão da verificação de certificado é uma decisão, não um ajuste.',

  // --- A página de referência dos vendors que este catálogo não cobre --------------
  'catalogue.notCovered.title': 'Não coberto, e por quê',
  'catalogue.notCovered.intro':
    'Todo vendor que este catálogo não alcança, e por quê: alguns não são alcançáveis por um proxy de credencial que fala só HTTP, e outros foram avaliados e decididos contra.',
  'catalogue.notCovered.back': 'Voltar para Integrações',

  'admin.principals.title': 'Pessoas e máquinas',
  'admin.principals.serviceAccount': 'Conta de serviço criada no deploy, sem e-mail.',
  'principal.kind.person': 'Pessoa',
  'principal.kind.serviceAccount': 'Conta de serviço',
  'principal.state.active': 'Ativa',
  'principal.state.suspended': 'Suspensa',
  'tokenGroup.state.inUse': 'Em uso',
  'schedule.state.enabled': 'Ativado',
  'schedule.state.disabled': 'Desativado',
  'sso.state.active': 'Ativo',
  'sso.state.inactive': 'Inativo',
  'admin.column.principal': 'Identidade',
  'admin.column.kind': 'Tipo',
  'admin.column.active': 'Ativa',
  'admin.principals.create.displayName': 'Nome de exibição',
  'admin.principals.create.email': 'E-mail',
  'admin.principals.create.password': 'Senha inicial',
  'admin.principals.create.passwordHelp':
    'A senha com que esta pessoa entra localmente.',
  'admin.principals.create.action': 'Criar pessoa',
  'admin.principals.create.creating': 'Criando…',
  'admin.grants.title': 'Atribuições',
  'admin.grant.nodeHelp': 'Deixe em branco para atribuir em toda a organização.',
  'admin.grant.organisation': 'Toda a organização',
  'admin.grant.add': 'Atribuir este papel',
  'admin.grant.adding': 'Atribuindo…',
  'admin.grant.remove': 'Remover',
  'admin.grant.removing': 'Removendo…',
  'admin.grant.removeAction': 'Remover esta atribuição',
  'admin.grant.removeConsequence': 'A pessoa perde este papel imediatamente.',
  'admin.grant.removeClose': 'Fechar',
  'admin.grant.removeCancel': 'Manter a atribuição',
  'admin.grant.addAction': 'Atribuir este papel administrativo',
  'admin.grant.addConsequence':
    'A pessoa pode fazer tudo que este papel permite, imediatamente.',
  'admin.grant.addClose': 'Fechar',
  'admin.grant.addCancel': 'Não atribuir',
  'admin.grant.role.summary.one': 'Alcança {count} domínio de permissão',
  'admin.grant.role.summary': 'Alcança {count} domínios de permissão',
  'admin.grant.rolePermissions': 'Ver cada permissão',
  'admin.column.role': 'Papel',
  'admin.column.node': 'Nó',
  'admin.tokens.title': 'Tokens de máquina',
  'admin.tokens.name': 'Para que serve',
  'admin.tokens.issue': 'Emitir um token',
  'admin.tokens.issuing': 'Emitindo…',
  'admin.tokens.shownOnce':
    'Esta é a única vez que este valor aparece. O deployment guarda um hash dele, por isso nada — incluindo este console — o consegue ler de volta.',
  'admin.tokens.revoke': 'Revogar',
  'admin.tokens.revoking': 'Revogando…',
  'admin.tokens.revoked': 'Revogado',
  'admin.tokens.revokeConsequence':
    'Os clientes que usam este token deixam de autenticar agora.',
  'admin.tokens.revokeConfirm': 'Revogar',
  'admin.tokens.revokeCancel': 'Deixar a funcionar',
  'admin.tokens.failed': 'O deployment recusou isto.',
  'admin.tokens.unreachable': 'Não foi possível alcançar o deployment.',
  'admin.tokens.revokedGroup.one': '{count} revogado',
  'admin.tokens.revokedGroup': '{count} revogados',
  'admin.column.token': 'Token',
  'admin.column.scopes': 'Âmbitos',
  'admin.column.expires': 'Expira',
  'admin.column.origin': 'Início',
  'admin.sso.title': 'Início de sessão único',
  'admin.sso.provider': 'Provider',
  'admin.sso.issuer': 'Emissor',
  'admin.sso.clientId': 'Id do cliente',
  'admin.sso.authorisation': 'Endpoint de autorização',
  'admin.sso.token': 'Endpoint de token',
  'admin.sso.jwks': 'Conjunto de chaves',
  'admin.sso.redirect': 'Redirecionar de volta para',
  'admin.sso.defaultNode': 'Equipe padrão',
  'admin.sso.save': 'Salvar esta configuração',
  'admin.sso.saving': 'Salvando…',
  'admin.sso.test': 'Testar com um conjunto de claims real',
  'admin.sso.testing': 'Testando…',
  'admin.sso.claims': 'As claims que o seu provider devolveu',
  'admin.sso.claimsHelp':
    'Cole o que o provider devolveu para um usuário de teste. É lido da mesma forma que um sign-in real.',
  'admin.sso.activate': 'Tornar esta a forma de entrar',
  'admin.sso.activating': 'Ativando…',
  'admin.sso.active': 'Ativo. As pessoas entram por este provider.',
  'admin.sso.verified': 'Testado. Ainda não foi tornado a forma de entrar.',
  'admin.sso.notVerified': 'Não testado. Não pode ser ativado enquanto não for.',
  'admin.sso.testFirst':
    'Teste esta configuração antes de a ativar. Um provider não testado é cada operador trancado fora.',
  'admin.sso.pendingEdit': 'Guarde esta mudança e depois teste de novo.',
  'admin.sso.failed': 'O deployment recusou isto.',
  'admin.sso.unreachable': 'Não foi possível alcançar o deployment.',
  'admin.sso.problems': 'Esta configuração não pode ser usada:',
  'admin.sso.notConfigured': 'Ainda não configurado',
  'admin.sso.configure': 'Configurar o início de sessão único',
  'admin.sso.state': 'Estado',
  'admin.empty.heading': 'Ninguém além de você',
  'admin.empty.body':
    'Identidades, atribuições e tokens aparecem aqui à medida que são emitidos. Só existe a conta com que iniciou sessão.',
  'admin.empty.action': 'Emitir um token',

  'audit.title': 'Auditoria',
  'audit.caption': 'Quem fez o quê, quando e sobre que recurso',
  'audit.column.occurred': 'Quando',
  'audit.column.actor': 'Identidade',
  'audit.column.action': 'Ação',
  'audit.column.subject': 'Assunto',
  'audit.column.outcome': 'Desfecho',
  'audit.filter.actor': 'Identidade',
  'audit.filter.action': 'Ação',
  'audit.empty.heading': 'Nada foi registrado',
  'audit.empty.body':
    'Todas as ações com consequência são escritas aqui quando acontecem. Nenhuma aconteceu no período que está vendo.',
  'audit.empty.action': 'Alargar o período',

  // --- Live -----------------------------------------------------------------------------------------
  'live.state.live': 'Ao vivo',
  'live.state.refreshing': 'Atualizando',
  'live.state.stale': 'Sem atualizar',
  'live.state.paused': 'Pausado',
  'live.connection': 'Conexão',
  'live.connection.connecting': 'Conectando',
  'live.connection.connected': 'Ao vivo',
  'live.connection.reconnecting': 'Reconectando',
  'live.connection.idle': 'Pausado em segundo plano',
  'live.connection.disconnected': 'Sem transmissão',
  'live.stale':
    'Esta transcrição parou de atualizar. O que está na tela é tudo o que havia chegado.',
  'live.reload': 'Reconectar',
  'live.new': '{count} novos',
  'live.new.action': 'Ir para o mais recente',
  'live.ended.completed': 'Esta investigação terminou.',
  'live.ended.failed': 'Esta investigação falhou.',
  'live.ended.cancelled': 'Esta investigação foi interrompida.',
  'live.attention.approval': 'Aprovação',
  'live.attention.question': 'Pergunta',
  'live.decided': 'Decidido por {who}',
  'live.decided.elsewhere': 'outra pessoa',
  'live.question.title': 'O agente está aguardando uma resposta',
  'live.question.label': 'Sua resposta',
  'live.question.answer': 'Responder e continuar',
  'live.question.required':
    'A investigação retoma quando isto for respondido, então precisa de uma resposta.',
  'live.takeover.title': 'Controle',
  'live.takeover.take': 'Assumir o controle',
  'live.takeover.resume': 'Devolver ao agente',
  'live.takeover.cancel': 'Interromper esta investigação',
  'live.takeover.taken':
    'Você está no controle. A investigação pausa no próximo ponto seguro.',
  'live.takeover.consequence':
    'Ela para no próximo ponto seguro, mantém o que já descobriu e não pode ser reiniciada.',
  'live.takeover.keep': 'Deixar em execução',
  'live.takeover.close': 'Fechar',
  'live.context.title': 'Acrescentar contexto',
  'live.context.label': 'Algo que esta investigação deveria saber',
  'live.context.send': 'Enviar sem interromper',
  'live.context.sent': 'Entregue no próximo turno.',
  'live.outcome.dismiss': 'Dispensar esta mensagem',
  'live.outcome.recorded': 'na transcrição desta investigação',
  'live.outcome.refused': 'O deployment recusou: {reason}',
  'live.outcome.unreachable': 'Não foi possível alcançar o deployment.',
  'nav.agent': 'O agente',
  'page.agent.title': 'O agente',
  'page.agent.context':
    'O que ele é, o que ele pode fazer e o que ele vai fazer sem perguntar a ninguém.',
  'agent.tabs': 'O que o agente é, o que pode e o que fará sozinho',
  'agent.tab.topology': 'Pipeline',
  'agent.tab.tools': 'Ferramentas',
  'agent.tab.autonomy': 'Autonomia',
  'agent.metro.title': 'Os seis estágios de uma investigação',
  'agent.metro.subtitle':
    'todo run percorre esta linha, e o transcript agrupa por estágio',
  'agent.metro.inFlight': '{count} investigações em voo',
  'agent.metro.copy.resolve_integrations':
    'Descobre o que este time pode chamar; sem nada, encerra cedo.',
  'agent.metro.copy.intake':
    'Decide se há incidente e liga ao já aberto quando é o mesmo.',
  'agent.metro.copy.plan_evidence':
    'Pontua as capacidades e escolhe por onde vale começar.',
  'agent.metro.copy.gather_evidence':
    'Executa as leituras planejadas e retém só o que sustenta algo.',
  'agent.metro.copy.diagnose': 'Forma hipóteses e as testa contra a evidência retida.',
  'agent.metro.copy.deliver': 'Escreve a causa, propõe a ação e registra o episódio.',
  'agent.metro.name.resolve_integrations': 'Resolver integrações',
  'agent.metro.name.intake': 'Triagem',
  'agent.metro.name.plan_evidence': 'Planejar evidência',
  'agent.metro.name.gather_evidence': 'Coletar evidência',
  'agent.metro.name.diagnose': 'Diagnosticar',
  'agent.metro.name.deliver': 'Entregar',
  'agent.metro.regime.model': 'modelo: {role}',
  'agent.metro.regime.deterministic': 'determinístico',
  'agent.metro.regime.none': 'sem modelo',
  'agent.metro.runningNow': 'rodando agora',
  'agent.metro.tools.ratio': '{enabled} de {total} habilitadas',
  'agent.metro.tools.read': 'Lê · {count}',
  'agent.metro.tools.writeReversible': 'Escreve, reversível · {count}',
  'agent.metro.tools.destructive': 'Destrutiva · {count}',
  'agent.metro.tools.catalogue': 'catálogo completo →',
  'agent.metro.autonomy.footer':
    'Nenhuma classe roda sozinha: tudo é diagnosticado e proposto para uma pessoa decidir.',
  'agent.metro.autonomy.adjust': 'ajustar política →',
  'agent.metro.team.budget': '{used} de {budget} tokens',
  'agent.metro.team.empty':
    'Nenhum fato escrito ainda. Fatos do ambiente entram no prompt de toda investigação.',
  'agent.metro.team.note': 'o que passa do orçamento é recusado, nunca truncado',
  'agent.metro.team.investigator': '→ Investigador',
  'agent.metro.team.subagent': '→ Subagente',
  'agent.metro.team.write': 'escrever fatos do ambiente →',
  'agent.stage.role': 'papel de modelo: {role}',
  'agent.stage.noModel': 'nenhuma chamada de modelo',
  'agent.stage.consults': 'Consulta:',
  'agent.specialists.title': 'Os especialistas que esta equipe declara',
  'agent.specialists.edit':
    'Quais especialistas existem é configuração, editada um campo por vez.',
  'agent.specialists.editLink': 'Editar a seção de agentes',
  'agent.specialists.empty.heading': 'Esta equipe não declara especialistas',
  'agent.specialists.empty.body':
    'A investigação continua rodando; ela mesma faz a coleta em vez de despachar alguém. Declare um especialista para dividir o trabalho.',
  'agent.specialists.empty.action': 'Editar a configuração',
  'agent.specialists.state.enabled': 'Ativado',
  'agent.specialists.state.disabled': 'Desativado',
  'agent.models.title': 'Em que cada papel roda',
  'agent.models.body':
    'Uma etapa nomeia um papel, nunca um modelo. Aquilo em que um papel resolve é configuração, e cada linha aqui diz qual nó forneceu o valor.',
  'agent.models.default': 'padrão do deployment — ninguém vinculou este papel',
  'agent.models.inherited': 'sem escolha própria — segue o investigador',
  'agent.models.followSummary': '{count} papéis seguem o investigador',
  'agent.models.from': 'de {node}',
  'agent.models.empty.heading': 'Nenhum papel está descrito aqui',
  'agent.models.empty.body':
    'O deployment não disse quais papéis ele resolve. Todo papel continua rodando no padrão do deployment.',
  'agent.models.empty.action': 'Editar a configuração',
  'agent.budgets.title': 'O que uma investigação pode gastar',
  'agent.budgets.body':
    'Uma equipe pode baixar qualquer um destes e não pode subir nenhum além do seu teto. O teto é uma constante do deployment, não um ajuste.',
  'agent.budgets.ceiling': 'teto {ceiling}',
  'agent.budgets.maxIterations': 'Máximo de iterações',
  'agent.budgets.maxParallelSubagents': 'Máximo de especialistas em paralelo',
  'agent.budgets.maxSubagentDepth': 'Profundidade máxima de especialistas',
  'agent.budgets.toolBudget': 'Orçamento de ferramentas',
  'agent.budgets.empty.heading': 'Nenhum orçamento está descrito aqui',
  'agent.budgets.empty.body':
    'O deployment não descreveu os campos de orçamento deste nó, então os tetos não podem ser mostrados.',
  'agent.budgets.empty.action': 'Editar a configuração',
  'agent.advanced.title': 'Configurações avançadas do agente',
  'agent.advanced.field.promptInvestigator': 'Substituição do prompt do investigador',
  'agent.advanced.field.promptIntake': 'Substituição do prompt de admissão',
  'agent.advanced.field.promptDiagnose': 'Substituição do prompt de diagnóstico',
  'agent.advanced.field.operatingContextEnabled': 'Enviar contexto operacional',
  'agent.advanced.field.maxSubagentIterations': 'Máximo de iterações do especialista',
  'agent.document.untouched':
    'Nada foi sobrescrito para este nó: ele roda o pipeline como ele veio. O documento abaixo diz isso nas palavras da própria instalação.',
  'agent.document.title': 'A mesma topologia, como documento',
  'agent.document.show': 'mostrar o documento',
  'agent.empty.heading': 'Não foi possível descrever o pipeline',
  'agent.empty.body':
    'O deployment não respondeu com as etapas que uma investigação executa. Nada aqui é configuração; é o que o build é.',
  'agent.empty.action': 'Editar a configuração',
  'agent.tools.browse': 'Encontrar uma tool ou skill',
  'agent.tools.effect.all': 'Todas',
  'agent.tools.effect.read': 'Lê',
  'agent.tools.effect.write_reversible': 'Escreve reversível',
  'agent.tools.effect.write_irreversible': 'Escreve irreversível',
  'agent.tools.effect.destructive': 'Destrutiva',
  'agent.tools.domain.remediation': 'Remediação',
  'agent.tools.domain.cloud_control_plane': 'Plano de controle',
  'agent.tools.domain.skills': 'Skills',
  'agent.tools.domain.methodology': 'Metodologia',
  'agent.tools.domain.logstore': 'Logstore',
  'agent.tools.domain.communication': 'Comunicação',
  'agent.tools.domain.metrics': 'Métricas',
  'agent.tools.domain.incident': 'Incidente',
  'agent.tools.domain.cicd': 'CI/CD',
  'agent.tools.domain.vcs': 'VCS',
  'agent.tools.domain.database': 'Banco de dados',
  'agent.tools.domain.tracing': 'Tracing',
  'agent.tools.domain.changes': 'Mudanças',
  'agent.tools.domain.model_provider': 'Provedor de modelo',
  'agent.tools.domain.observability': 'Observabilidade',
  'agent.tools.domain.topology': 'Topologia',
  'agent.tools.domain.estate': 'Estate',
  'agent.tools.domain.other': 'Outros',
  'agent.tools.domainMeta':
    '{count} capacidades · {enabled} habilitadas · as destrutivas pedem aprovação sempre',
  'agent.tools.showing': 'mostrando {shown} de {total} ·',
  'agent.tools.showAll': 'ver todas as capacidades de {domain} →',
  'agent.tools.footer':
    'Efeitos colaterais vêm do catálogo, não do agente — o que é destrutivo pede aprovação sempre.',
  'agent.tools.origin': 'do servidor {server}',
  'agent.tools.blocked': 'indisponível aqui: {integration} não está configurada',
  'agent.tools.unknown':
    'este deployment ainda não tem árvore de organização, então nada foi resolvido',
  'agent.tools.empty.heading': 'Nada neste grupo',
  'agent.tools.empty.body':
    'Nenhuma capacidade deste build cai neste grupo, ou não foi possível perguntar ao deployment.',
  'agent.tools.empty.action': 'Editar a configuração',
  'agent.tools.advanced.title': 'Configurações avançadas de capacidades',
  'agent.bridged.title': 'Servidores fora deste deployment',
  'agent.bridged.body':
    'Uma ferramenta vinda de um destes veio de onde o operador não manda. Suas ferramentas são enumeradas quando o deployment alcança o servidor, e uma que ninguém classificou não pode executar.',
  'agent.bridged.empty.heading': 'Nenhum servidor externo registrado',
  'agent.bridged.empty.body':
    'Toda ferramenta que esta equipe pode rodar é uma que este build entrega. Registre um servidor externo para acrescentar ferramentas de fora.',
  'agent.bridged.empty.action': 'Editar a configuração',
  'agent.bridged.state.enabled': 'Ativado',
  'agent.bridged.state.disabled': 'Desativado',
  'agent.autonomy.class.trivial': 'Trivial',
  'agent.autonomy.class.low': 'Baixa',
  'agent.autonomy.class.moderate': 'Moderada',
  'agent.autonomy.class.high': 'Alta',
  'agent.autonomy.class.critical': 'Perigosa',
  'agent.autonomy.policyChip': 'Política atual: {posture}',
  'agent.autonomy.nobodyAlone': 'nada roda sem uma pessoa decidir',
  'agent.autonomy.seeRule': 'ver a regra que resolve isso →',
  'agent.autonomy.change.title': 'Mudar a política',
  'agent.autonomy.change.body':
    'Regras declaradas por classe ou por capacidade mudam o veredito de "Propor" para executar com aprovação, ou executar sozinho. Cada regra diz o que cobre — e o que não estiver coberto continua caindo aqui.',
  'agent.autonomy.change.note': 'mudança de política é uma decisão registrada',
  'agent.outlook.title': 'O que aconteceria, por classe de ação',
  'agent.outlook.body':
    'Uma frase por classe, respondida pelo próprio deployment sob a política tal como ela está agora.',
  'agent.outlook.reason': 'Por quê:',
  'agent.outlook.bound': 'barrado por {bound}',
  'agent.outlook.dryRun':
    'Tudo aqui é simulado: dry-run está ligado para este nó, então nada é executado.',
  'agent.outlook.edit': 'Mudar o que este deployment pode fazer sozinho',
  'agent.outlook.empty.heading': 'Não foi possível ler a postura',
  'agent.outlook.empty.body':
    'Este nó ainda não carrega política de autonomia, então nada foi decidido sobre o que pode acontecer sem uma pessoa. A ausência resolve para apenas propor.',
  'agent.outlook.empty.action': 'Definir a postura',
  'agent.replay.title': 'E o que ela decidiu, sobre o que de fato aconteceu',
  'agent.replay.body':
    'O deployment reproduziu o próprio registro de ações recentes contra a postura tal como ela está. Isto fica ao lado das classes acima, não no lugar delas: um deployment no primeiro dia não tem registro, e é nesse dia que alguém decide se confia nele.',
  'agent.replay.empty.heading': 'Nada foi registrado ainda',
  'agent.replay.empty.body':
    'Nenhuma ação chegou ao motor de política nesta janela, então não há o que reproduzir. As classes acima continuam dizendo o que aconteceria.',

  'live.investigate.title': 'Iniciar uma investigação',
  'live.investigate.objective': 'O que deve ser investigado?',
  'live.investigate.start': 'Investigar',
  'live.investigate.cancel': 'Cancelar',
  'live.investigate.hint':
    'O objetivo diz do que a investigação trata — o agente decide o caminho.',
  'live.investigate.ctrlEnter': 'Ctrl ↵ para iniciar',
  'live.investigate.suggestions': 'Ou comece de onde o ambiente está',
  'live.investigate.suggestion.recurring':
    'Por que {subject} insiste em voltar? {count} disparos',
  'live.investigate.suggestion.unhealthy': 'O que derrubou {count} recursos?',
  'live.investigate.suggestion.audit': 'Auditar a saúde geral do cluster {name}',
  'live.investigate.footer.team': 'Vai rodar com o time {team} · {posture}',
  'live.investigate.footer.postureOnly': 'Vai rodar · {posture}',
  'live.investigate.footer.stages':
    '6 estágios · você acompanha ao vivo, evento a evento',
  'live.investigate.required': 'Um objetivo é aquilo de que a investigação trata.',
  'live.investigate.started': 'A investigação foi iniciada.',
  'live.investigate.close': 'Fechar',
  'data.ingress.title': 'O que chega',
  'data.ingress.receiving': 'Recebendo',
  'data.ingress.ready': 'Pronta \u2014 nada chegou ainda',
  'data.ingress.last': '\u00daltima entrega',
  'data.ingress.week': '{count} nesta semana',
  'data.ingress.copyUrl': 'Copiar URL',
  'data.ingress.receiverYaml': 'Copiar YAML do receiver do Alertmanager',
  'data.ingress.sample': '\u00daltimo payload, mascarado',
  'data.ingress.empty.heading': 'Nenhum receptor configurado',
  'data.ingress.empty.body':
    'Aponte um roteador de alertas para um dos endere\u00e7os de webhook deste deployment e as entregas aparecem aqui.',
  'data.ingress.empty.action': 'Abrir o cat\u00e1logo',
  'data.ingress.detail.title': 'Formato e teste',
  'data.ingress.detail.summary':
    'Formato esperado, mecanismo de confian\u00e7a, e um teste de entrega.',
  'data.ingress.detail.format': 'Espera:',
  'data.ingress.retired':
    'Outras quatro fontes de entrada foram para o roadmap \u2014 elas voltam com um ambiente que consiga valid\u00e1-las.',
  'data.rules.title': 'O que fazer com isso',
  'data.rules.action': 'A\u00e7\u00e3o:',
  'data.rules.catchAll': 'Tudo o que nenhuma regra acima pegou termina aqui.',
  'data.rules.empty.heading': 'Nenhuma regra configurada',
  'data.rules.empty.body':
    'Toda entrega verificada vira investiga\u00e7\u00e3o da equipe que a verificou.',
  'data.rules.empty.action': 'Abrir a configura\u00e7\u00e3o',
  'data.chain.label': 'O que acontece com um alerta aqui',
  'data.chain.intake.empty': 'Nenhuma fonte entregou ainda',
  'data.chain.rule.empty': 'Nenhuma regra configurada ainda',
  'data.chain.action.empty': 'Nenhuma a\u00e7\u00e3o roda ainda',
  'data.chain.destination.empty': 'Nenhum destino configurado ainda',
  'data.simulate.title': 'Testar uma entrega',
  'data.simulate.purpose':
    'Veja qual regra pegaria um payload e qual equipe ele alcan\u00e7aria, antes de salvar qualquer coisa.',
  'data.simulate.source': 'Receptor',
  'data.simulate.payload': 'Payload',
  'data.simulate.action': 'Simular',
  'data.simulate.running': 'Simulando\u2026',
  'data.simulate.save': 'Salvar',
  'data.simulate.needed':
    'Simule este payload antes de salvar, para ver o efeito primeiro.',
  'data.simulate.failed': 'O deployment recusou a simula\u00e7\u00e3o.',
  'data.simulate.unreachable': 'N\u00e3o foi poss\u00edvel alcan\u00e7ar o deployment.',
  'data.simulate.malformed': 'Isso n\u00e3o \u00e9 JSON v\u00e1lido.',
  'data.delivery.title': 'Para onde vai o resultado',
  'settings.schedulesDestinations.advanced.transit.title':
    'Regras de roteamento e destinos de entrega',
  'settings.schedulesDestinations.advanced.surfaces.title':
    'Canais de chat, destinatários de relatório e alvos de notificação',
  'settings.schedulesDestinations.advanced.field.transitRules': 'Regras de roteamento',
  'settings.schedulesDestinations.advanced.field.transitDestinations':
    'Destinos de entrega',
  'settings.schedulesDestinations.advanced.field.channels': 'Canais de chat',
  'settings.schedulesDestinations.advanced.field.reportDestinations':
    'Destinos de relat\u00f3rio',
  'settings.schedulesDestinations.advanced.field.notificationSinks':
    'Alvos de notifica\u00e7\u00e3o',
  'data.delivery.masking': 'Pol\u00edtica de mascaramento:',
  'data.delivery.resend': 'Enviar de novo',
  'data.delivery.resending': 'Enviando\u2026',
  'data.delivery.resent': 'Entregue',
  'data.delivery.resendFailed': 'Tamb\u00e9m n\u00e3o chegou desta vez.',
  'data.delivery.empty.heading': 'Nenhum destino declarado',
  'data.delivery.empty.body':
    'Ningu\u00e9m \u00e9 avisado quando uma investiga\u00e7\u00e3o conclui.',
  'data.delivery.empty.action': 'Abrir a configura\u00e7\u00e3o',
  'data.delivery.unconfigurable.action': 'Conectar uma integra\u00e7\u00e3o',
  'data.delivery.unusable.link': 'Verificar a credencial',
  'data.provenance.open': 'Para onde isso foi?',
  'data.provenance.source': 'Chegou por',
  'data.provenance.rule': 'Regra',
  'data.provenance.team': 'Equipe',
  'data.provenance.run': 'Investiga\u00e7\u00e3o',
  'data.provenance.resource': 'Recurso',
  'data.provenance.none': 'Nada chegou aqui para rastrear.',
  'page.data.title': 'Dados',
  'page.data.context':
    'O que entra, o que se faz com isso, e para onde vai o resultado.',
  // --- Changes the agent has proposed ------------------------------------------
  // O painel abaixo é todo o conteúdo desta tela, não uma subvisão filtrada —
  // então o próprio título nomeia o mesmo conceito que o menu e o título da
  // página já usam, em vez de uma segunda forma de dizer a mesma coisa.
  'proposals.title': 'Mudanças propostas',
  'proposals.empty.heading': 'O agente não propôs nada',
  'proposals.empty.body':
    'As propostas vêm das investigações e das verificações documentadas no seu repositório. Nada aqui é aplicado sem a sua aprovação.',
  'proposals.empty.action': 'Ver o que está em execução',
  'proposals.otherInbox': 'Para ações que o agente quer realizar agora:',
  'proposals.acceptance': '{approved} de {decided} propostas decididas foram aceitas',
  'proposals.acceptance.none': 'Nada foi decidido ainda',
  'proposals.type.knowledge': 'Conhecimento',
  'proposals.type.operating_context': 'Contexto operacional',
  'proposals.type.detector': 'Detector',
  'proposals.type.configuration': 'Configuração',
  'proposals.field.type': 'Tipo',
  'proposals.field.rationale': 'Por quê',
  'proposals.field.evidence': 'Evidência',
  'proposals.field.origin': 'Da investigação',
  'proposals.field.node': 'Onde se aplica',
  'proposals.field.effect': 'O que mudaria',
  'proposals.openRun': 'Abrir a investigação',
  'proposals.effect.show': 'Mostrar o que isto faria',
  'proposals.effect.loading': 'Perguntando à instalação',
  'proposals.effect.failed': 'A instalação não respondeu. Nada foi alterado.',
  'proposals.effect.text': 'O texto como seria salvo',
  'proposals.effect.preview': 'A configuração que isto resolveria',
  'proposals.effect.dryRun': 'O que este detector teria encontrado',
  'proposals.effect.dryRun.quiet': 'Não teria encontrado nada no histórico armazenado.',
  'proposals.approveFirst':
    'Aprovar fica disponível depois que você vir o que isto faria.',
  'proposals.approve': 'Aprovar e aplicar',
  'proposals.reject': 'Recusar',
  'proposals.reason': 'Por que está sendo recusada',
  'proposals.reason.required': 'É obrigatório informar um motivo para recusar.',
  'proposals.prior.heading': 'Recusada antes',
  'proposals.prior.entry': '{who} em {when}: {reason}',
  'attention.proposal': 'Mudança proposta',

  // --- O hub de Settings: sua própria entrada, e os grupos e páginas da subnav -
  // Os nomes dos grupos da subnav e de cada página abaixo ficam em inglês em
  // todo idioma — são o vocabulário do próprio produto para esses lugares, do
  // mesmo jeito que o nome de uma integração nunca é traduzido.
  'nav.settings': 'Ajustes',
  'settings.subnav.label': 'Páginas de ajustes',
  'page.settings.title': 'Ajustes',
  'page.settings.context':
    'Tudo sobre esta instalação que não é trabalho de incidente: quem tem acesso, como o agente se comporta e de onde os dados vêm.',
  'settings.group.organization': 'Organisation',
  'settings.group.agent': 'Agent',
  'settings.group.data': 'Data',
  'settings.page.membersRoles': 'Members & roles',
  'settings.page.membersRoles.context':
    'Quem existe nesta instalação, os papéis que cada um tem e as sessões abertas.',
  'settings.page.singleSignOn': 'Single sign-on',
  'settings.page.singleSignOn.context': 'Como as pessoas entram sem uma senha local.',
  'settings.page.machineTokens': 'Machine tokens',
  'settings.page.machineTokens.context':
    'Credenciais emitidas para um script ou serviço, agrupadas pelo que as criou.',
  'settings.page.auditLog': 'Audit log',
  'settings.page.auditLog.context': 'Quem fez o quê, quando, e contra qual recurso.',
  'settings.page.modelsProviders': 'Models & providers',
  'settings.page.modelsProviders.context':
    'Qual modelo conduz as investigações, e a credencial em que ele roda.',
  'settings.page.autonomyGuardrails': 'Autonomy & guardrails',
  'settings.page.autonomyGuardrails.context':
    'O que esta instalação pode fazer por conta própria, e sobre o que precisa perguntar.',
  'settings.page.notifications': 'Notifications',
  'settings.page.notifications.context':
    'Para onde um relatório vai quando uma investigação termina, e quando ficar em silêncio.',
  'settings.page.alertIntake': 'Alert intake',
  'settings.page.alertIntake.context':
    'O que chega, e as regras que decidem o que acontece com aquilo.',
  'settings.page.schedulesDestinations': 'Schedules & destinations',
  'settings.page.schedulesDestinations.context':
    'As investigações que rodam por horário, e para onde um alerta vai depois de chegar.',
  // Compartilhada por toda página que a subnav lista antes de a funcionalidade
  // dona dela ser entregue — nomeada com honestidade em vez de deixada de fora
  // da subnav, porque uma rota que existe e diz isso vale mais que uma tela
  // inventada só para preencher o espaço.
  'settings.notBuilt.body':
    'Esta tela faz parte da reformulação de {group}, que ainda não foi lançada.',
  'settings.notBuilt.action': 'Voltar para Ajustes',

  // --- Ajustes: Models & providers -------------------------------------------
  'settings.models.role.investigator': 'Investigador',
  'settings.models.role.subagent': 'Subagente',
  'settings.models.role.intake': 'Entrada',
  'settings.models.role.diagnose': 'Diagnóstico',
  'settings.models.role.extraction': 'Extração',
  'settings.models.role.embedding': 'Embedding',
  'settings.models.role.selection': 'Seleção',
  'settings.models.role.summarisation': 'Resumo',
  'settings.models.empty.body':
    'Nenhum provider respondeu. Conecte um no catálogo de integrações para escolher o que conduz uma investigação.',
  'settings.models.empty.action': 'Abrir o catálogo de integrações',
  'settings.models.provider': 'Provider',
  'settings.models.model.known': 'Modelo',
  'settings.models.model.free': 'Modelo',
  'settings.models.toolCalling.supported': ' — suporta tool calling',
  'settings.models.toolCalling.unsupported': ' — não suporta tool calling',
  'settings.models.toolCalling.unknown': ' — tool calling não confirmado',
  'settings.models.verificationNote': 'Última verificação:',
  'settings.models.notConnected':
    'Nenhuma credencial está guardada para este provider.',
  'settings.models.connectCredential': 'Conectar uma credencial',
  'settings.models.advanced.title': 'Papéis avançados',
  'settings.models.advanced.lead':
    'Subagent, intake, diagnose, extraction, embedding, selection e summarisation herdam o padrão do investigator, a menos que fixados aqui.',
  'settings.models.advanced.inherits': 'Herda o padrão',
  'settings.models.revert': 'Voltar a herdar o padrão',
  'settings.models.reverted': 'Vai herdar o padrão assim que salvo',
  'settings.models.saveAndVerify': 'Salvar e verificar',
  'settings.models.saving': 'Salvando…',
  'settings.models.testWithoutSaving': 'Testar sem salvar',
  'settings.models.verifying': 'Verificando…',
  'settings.models.verified': 'Uma verificação alcançou este provider e ele respondeu.',
  'settings.models.verificationFailed': 'A verificação não passou.',
  'settings.models.saved': 'Salvo. É nisto que o agente roda agora.',
  'settings.models.failed': 'A instalação recusou esta mudança.',
  'settings.models.unreachable': 'Não foi possível contatar a instalação.',
  'settings.models.nothingChanges': 'Nada mudaria.',
  'settings.models.checkAgain': 'Verificar novamente',
  'settings.models.checking': 'Verificando…',
  'settings.models.chooseVerifiedModel': 'Escolha um modelo da lista verificada',
  'settings.models.reloadModels': 'Recarregar modelos',
  'settings.models.reloadingModels': 'Recarregando…',
  'settings.models.staticModelsLabel':
    'Lista estática — não foi possível perguntar ao endpoint o que ele serve hoje.',
  'settings.models.advanced.summaryAll':
    '{total} papéis, todos herdam o padrão do investigator',
  'settings.models.advanced.summaryPartial':
    '{total} papéis, {inheriting} herdam o padrão do investigator',
  'settings.models.check.credentials': 'Credenciais',
  'settings.models.check.authentication': 'Autenticação',
  'settings.models.check.toolCalling': 'Chamada de ferramenta',
  'settings.models.check.structuredOutput': 'Saída estruturada',
  'settings.models.check.streaming': 'Streaming',
  'settings.models.consequence.credentials':
    'Nenhuma credencial foi resolvida, então nada foi chamado.',
  'settings.models.consequence.authentication':
    'O endpoint rejeitou a credencial desta instalação.',
  'settings.models.consequence.toolCalling':
    'Investigações são sequências de chamadas de ferramenta — este modelo pode travar nelas.',
  'settings.models.consequence.structuredOutput':
    'Os estágios do pipeline trocam documentos tipados — este modelo pode falhar no meio de uma investigação.',
  'settings.models.consequence.streaming':
    'A saída em streaming não chegaria ao console.',

  // --- Ajustes: Notifications -------------------------------------------------
  'settings.notifications.contractNote':
    'Cada valor aqui só pode tornar o teto da plataforma mais estrito.',
  'settings.notifications.field.quiet_hours_enabled': 'Horário de silêncio',
  'settings.notifications.field.quiet_hours_start': 'Início do silêncio',
  'settings.notifications.field.quiet_hours_end': 'Fim do silêncio',
  'settings.notifications.field.timezone': 'Fuso horário',
  'settings.notifications.field.cooldown_seconds': 'Supressão de repetição',
  'settings.notifications.field.notifications_per_hour': 'Notificações por hora',

  // --- Ajustes: Autonomy & guardrails — a seção de guardrails -----------------
  'settings.autonomy.guardrails.title': 'Guardrails',
  'settings.autonomy.guardrails.lead':
    'Masking, detecção de segredo e aprovação — editados aqui, no mesmo documento de uma regra ou de um limite.',
  'settings.autonomy.guardrails.invariant.secret':
    'Um match de segredo sempre é olhado. Isso não pode ser desligado; enforcing ou observing decide só se um match é bloqueado ou apenas registrado.',
  'settings.autonomy.guardrails.invariant.approval':
    'Um write sempre precisa de aprovação de uma pessoa, seja qual for o limiar abaixo.',
  'settings.autonomy.guardrails.masking.enabled': 'Masking ativado',
  'settings.autonomy.guardrails.masking.level': 'Nível de masking',
  'settings.autonomy.guardrails.mode': 'Modo do guardrail',
  'settings.autonomy.guardrails.ruleset': 'Conjunto de regras',
  'settings.autonomy.guardrails.threshold': 'Limiar de aprovação',
  'settings.autonomy.guardrails.expiryHours': 'Validade do pedido de aprovação (horas)',
  // O que cada nível de masking, modo de guardrail e limiar de aprovação
  // realmente significa, lido por `guardrail-values.ts` — a mesma tabela cuja
  // coluna Valor chegou a imprimir `write_reversible` ao pé da letra, em
  // monoespaçado, ao lado da frase de toda outra linha. "off"/"standard"/
  // "strict" já se leem como palavras sozinhas; "local_models_exempt" ganha
  // uma tradução também, para a célula nunca ser três valores simples e um só
  // enfeitado.
  'guardrail.maskingLevel.off': 'Desativado',
  'guardrail.maskingLevel.standard': 'Padrão',
  'guardrail.maskingLevel.strict': 'Estrito',
  'guardrail.maskingLevel.local_models_exempt': 'Isento para modelos locais',
  // O que enforcing e observing fazem com uma correspondência, não a palavra
  // que o esquema usa para o modo — a mesma distinção que
  // `settings.autonomy.guardrails.invariant.secret` já traça em prosa, dita
  // aqui no vocabulário de dois valores da própria tabela.
  'guardrail.mode.enforcing': 'Aplicando — correspondências são bloqueadas',
  'guardrail.mode.observing':
    'Observando — correspondências são registradas, não bloqueadas',
  // O que cada limiar realmente exige aprovação, nas menos palavras que ainda
  // dizem isso corretamente. O esquema recusa um limiar acima de
  // `write_reversible` — uma escrita sempre precisa poder chegar a uma
  // pessoa — então estes três são todo valor permitido, não uma amostra de
  // um conjunto maior.
  'guardrail.approvalThreshold.read': 'Toda ação precisa de uma pessoa',
  'guardrail.approvalThreshold.read_sensitive':
    'Toda leitura sensível e escrita precisa de uma pessoa',
  'guardrail.approvalThreshold.write_reversible': 'Toda escrita precisa de uma pessoa',
  'settings.autonomy.guardrails.edit': 'Editar',
  'settings.autonomy.guardrails.cancel': 'Cancelar',

  'settings.autonomy.advanced.title': 'Configurações avançadas de autonomia',
  'settings.autonomy.advanced.field.allowUnverifiableActions':
    'Permitir ações não verificáveis',
  'settings.autonomy.advanced.field.dryRun': 'Simular tudo para esta equipe',
  'settings.autonomy.advanced.field.recurrenceThreshold': 'Limiar de recorrência',
  'settings.autonomy.advanced.field.recurrenceWindowSeconds':
    'Janela de recorrência (segundos)',

  'settings.sso.advanced.title': 'Mapeamento avançado de claims',
  'settings.sso.advanced.field.claimsSubject': 'Claim de assunto',
  'settings.sso.advanced.field.claimsEmail': 'Claim de e-mail',
  'settings.sso.advanced.field.claimsDisplayName': 'Claim de nome de exibição',
  'settings.sso.advanced.field.claimsGroups': 'Claim de grupos',

  'settings.alertIntake.advanced.title': 'Configurações avançadas de observação',
  'settings.alertIntake.advanced.field.paused': 'Observação pausada',
  'settings.alertIntake.advanced.field.pauseReason':
    'Por que a observação está pausada',
  'settings.alertIntake.advanced.field.bridgeEnabled': 'Usar o monitoramento existente',
  'settings.alertIntake.advanced.field.bridgeDashboardBaseUrl':
    'URL base dos dashboards',
  'settings.alertIntake.advanced.field.bridgeMappingIntervalSeconds':
    'Intervalo de correspondência (segundos)',
  'settings.alertIntake.advanced.field.bridgeHistoryLookbackSeconds':
    'Retrospecto do histórico (segundos)',
  'settings.alertIntake.advanced.field.bridgeLogWindowSeconds':
    'Janela de logs (segundos)',
  'settings.alertIntake.advanced.field.bridgeLogLineLimit': 'Limite de linhas de log',
  'settings.alertIntake.advanced.field.bridgeUseShippedRules':
    'Usar os mapeamentos de exportador prontos',
  'settings.alertIntake.advanced.field.bridgeUseShippedLogSelectors':
    'Usar as consultas de log prontas',
  'settings.alertIntake.advanced.field.bridgeLogsEnabled': 'Ler logs deste sistema',
  'settings.alertIntake.advanced.field.bridgeLogsName': 'Nome do sistema de logs',
  'settings.alertIntake.advanced.field.bridgeLogsEndpoint':
    'Endereço do sistema de logs',
  'settings.alertIntake.advanced.field.bridgeLogsIntegration':
    'Integração do sistema de logs',
  'settings.alertIntake.advanced.field.bridgeMetricsEnabled':
    'Ler métricas deste sistema',
  'settings.alertIntake.advanced.field.bridgeMetricsName':
    'Nome do sistema de métricas',
  'settings.alertIntake.advanced.field.bridgeMetricsEndpoint':
    'Endereço do sistema de métricas',
  'settings.alertIntake.advanced.field.bridgeMetricsIntegration':
    'Integração do sistema de métricas',
  'settings.alertIntake.advanced.field.guardianEnabled':
    'Executar o conjunto de detectores prontos',
  'settings.alertIntake.advanced.field.guardianClusterShape':
    'Formato de cluster detectado',
  'settings.alertIntake.advanced.field.guardianHeartbeatDestination':
    'Destino do heartbeat',
  'settings.alertIntake.advanced.field.guardianDeclaredIntentSource':
    'Origem da intenção declarada',

  // --- Ajustes: Log de auditoria ----------------------------------------------
  'settings.auditLog.period.label': 'Período',
  'settings.auditLog.period.days': 'Últimos {days} dias',

  // --- Ajustes: Tokens de máquina ----------------------------------------------
  'settings.machineTokens.purposeHelp':
    'Emitir outro token para uma finalidade que já tem um substitui o anterior — a troca fica registrada no log de auditoria.',
  'settings.machineTokens.detail': 'Tokens individuais',
  'settings.machineTokens.superseded.one':
    'Substituiu {count} token anterior emitido para a mesma finalidade.',
  'settings.machineTokens.superseded':
    'Substituiu {count} tokens anteriores emitidos para a mesma finalidade.',
  'settings.machineTokens.revokeOlder': 'Revogar todos menos o mais recente',
  'settings.machineTokens.revokingOlder': 'Revogando…',
  'settings.machineTokens.revokeOlderConsequence':
    'Todo token mais antigo dessa finalidade para de autenticar agora.',
  'settings.machineTokens.revokeOlderConfirm': 'Revogar',
  'settings.machineTokens.revokeOlderCancel': 'Manter funcionando',
  'settings.machineTokens.count.one': '{count} token',
  'settings.machineTokens.count': '{count} tokens',
  'settings.machineTokens.lastUsed': 'Último uso',
  'settings.machineTokens.neverUsed': 'Nunca usado',
  'settings.machineTokens.filteredBy': 'Mostrando tokens com o escopo {scope}.',
  'settings.machineTokens.clearFilter': 'Mostrar todos os tokens',
  'settings.machineTokens.empty.heading': 'Nenhum token de máquina ainda',
  'settings.machineTokens.empty.body':
    'Tokens emitidos para um script ou serviço aparecem aqui, agrupados pela finalidade com que foram emitidos.',
  'settings.machineTokens.empty.action': 'Emitir um token',
  'settings.machineTokens.scopesSelected.one': '{count} escopo selecionado',
  'settings.machineTokens.scopesSelected': '{count} escopos selecionados',
  'settings.machineTokens.template.alertDelivery.name': 'Entrega de alertas',
  'settings.machineTokens.template.alertDelivery.purpose':
    'Marca o único escopo que um roteador de alertas precisa para entregar neste deployment.',
  'settings.machineTokens.template.readOnlyAutomation.name':
    'Automação somente leitura',
  'settings.machineTokens.template.readOnlyAutomation.purpose':
    'Marca todo escopo de leitura que você detém, para um script que só olha.',
  'settings.machineTokens.template.disabled':
    'Não disponível: esta predefinição precisa de um escopo fora do que você pode emitir.',
  'settings.machineTokens.destructiveScope.orgDelete':
    'Org Delete permite que quem tiver este token exclua a organização inteira.',
  'settings.machineTokens.destructiveScope.ownerAssign':
    'Owner Assign permite que quem tiver este token conceda o papel de owner a qualquer pessoa.',
  'settings.machineTokens.destructiveScope.impersonationUse':
    'Impersonation Use permite que quem tiver este token aja como qualquer outra pessoa neste deployment.',

  // --- Ajustes: Single sign-on --------------------------------------------------
  'settings.sso.step.configure': 'Configurar',
  'settings.sso.step.test': 'Testar',
  'settings.sso.step.activate': 'Ativar',
  'settings.sso.field.provider.help':
    'Como você chama esse provedor de identidade — não aparece em nenhum outro lugar.',
  'settings.sso.field.issuer.help':
    'A URL do issuer que seu provedor documenta, exatamente como aparece lá. Geralmente na própria página de configuração OpenID do provedor.',
  'settings.sso.field.clientId.help':
    'O client id que este deployment registrou junto ao provedor quando foi configurado como aplicação.',
  'settings.sso.field.authorisation.help':
    "Onde fica a própria tela de login do provedor — geralmente chamada de 'authorization_endpoint' na configuração OpenID dele.",
  'settings.sso.field.token.help':
    "Onde um código de login é trocado por um token — geralmente chamado de 'token_endpoint'.",
  'settings.sso.field.jwks.help':
    "Onde o provedor publica as chaves que assinam os tokens dele — geralmente chamado de 'jwks_uri'.",
  'settings.sso.field.redirect.help':
    'Para onde o provedor manda alguém de volta depois do login. Registre esse endereço exato junto ao provedor.',
  'settings.sso.field.defaultNode.help':
    'Onde alguém cai quando os grupos dela não mapeiam para nenhum time em particular — obrigatório, porque um diretório que não retorna grupos ainda precisa mandar para algum lugar.',
  'settings.sso.result.subject': 'Assunto',
  'settings.sso.result.email': 'E-mail',
  'settings.sso.result.team': 'Time',
  'settings.sso.result.team.default': 'o time padrão, nenhum grupo casou',
  'settings.sso.result.failed': 'Este conjunto de claims reprovou no teste:',
  'settings.sso.fallback':
    'O login local continua disponível como alternativa, seja qual for o estado deste provedor — ninguém fica trancado para fora só porque um provedor de identidade quebrou.',
  'decisions.card.steps': 'O que vai acontecer',
  'decisions.card.rollback': 'Se der errado — reversão',
  'decisions.card.noRollback':
    'Nenhuma reversão registrada — esta ação não pode ser desfeita.',
  'decisions.card.why': 'Por quê',
  'decisions.card.evidence': 'Evidência que sustenta',
  'decisions.card.evidenceLink': 'ver',
  'decisions.card.blastRadius': 'Raio de alcance',
  'decisions.card.blastRadius.text':
    '{count} recurso(s) conhecido(s), profundidade {depth}',
  'decisions.card.blastRadius.unknown':
    'Desconhecido — o grafo de topologia não pôde ser lido',
  'decisions.card.rawPayload': 'payload bruto da ação',
  'decisions.card.notRecorded': 'Não registrado.',
  'decisions.card.risk': 'Risco',
  'decisions.card.outcome': 'Decidida',
  'decisions.card.appliedAndVerified': 'aplicada e verificada',
  'decisions.card.autonomy.reversible':
    '{level} — fica na fila e só aplica depois do seu sim.',
  'decisions.card.autonomy.irreversible':
    '{level} — fica na fila e só aplica depois do seu sim.',
  'decisions.expiredFooter.explanation':
    'A janela desta proposta fechou — o ambiente foi lido antes de expirar. Proponha de novo para decidir sobre uma leitura atual.',
  'decisions.expiredFooter.repropose': 'Propor de novo, agora',
  'decisions.expiredFooter.discard': 'Descartar',
  'decisions.expiredFooter.failed': 'O deployment não respondeu. Nada mudou.',
  'decisions.decided.heading': 'Decididas recentemente',
  'decisions.decided.empty': 'Nada foi decidido ainda.',
  'decisions.decided.outcome.approved': 'aprovada por {who}',
  'decisions.decided.outcome.approvedVerified':
    'aprovada por {who}, aplicada e verificada',
  'decisions.decided.outcome.rejected': 'rejeitada por {who}: {reason}',
  'decisions.decided.outcome.rejectedNoReason': 'rejeitada por {who}',
  'decisions.decided.outcome.discarded': 'descartada por {who}',
};
