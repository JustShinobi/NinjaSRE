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
  'nav.group.operate': 'Operar',
  'nav.group.estate': 'Parque',
  'nav.group.learn': 'Aprender',
  'nav.group.govern': 'Governar',
  'nav.dashboard': 'Painel',
  'nav.incidents': 'Incidentes',
  'nav.runs': 'Execuções',
  'nav.approvals': 'Aprovações',
  'nav.resources': 'Recursos',
  'nav.topology': 'Topologia',
  'nav.detectors': 'Detectores',
  'nav.memory': 'Memória',
  'nav.knowledge': 'Conhecimento',
  'nav.autonomy': 'Autonomia',
  'nav.configuration': 'Configuração',
  'nav.audit': 'Auditoria',
  'nav.open': 'Abrir a navegação',
  'nav.close': 'Fechar a navegação',
  'nav.pending': '{count} aguardando',

  'page.dashboard.title': 'Visão geral',
  'page.dashboard.context':
    'O que precisa de uma pessoa, o que está em curso e como está o parque.',
  'page.incidents.title': 'Incidentes',
  'page.incidents.context': 'O que um detector abriu e o que aconteceu desde então.',
  'page.runs.title': 'Investigações',
  'page.runs.context':
    'Todas as execuções que esta instalação registou, da mais recente para a mais antiga.',
  'page.approvals.title': 'Aprovações',
  'page.approvals.context':
    'Mudanças à espera de uma decisão, e a reversão que existe por trás de cada uma.',
  'page.resources.title': 'Recursos',
  'page.resources.context': 'Tudo o que a instalação observa, e a saúde de cada item.',
  'page.topology.title': 'Topologia',
  'page.topology.context':
    'Como o parque está ligado, tal como a plataforma o entende.',
  'page.detectors.title': 'Detectores',
  'page.detectors.context':
    'O que está a ser observado, com que frequência, e o que disparou.',
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
  'page.audit.title': 'Auditoria',
  'page.audit.context': 'Quem fez o quê, quando, e sobre que recurso.',
  'page.pending':
    'Esta área chega com as telas de dados. A moldura à volta dela está pronta.',

  'shell.search': 'Procurar recursos, execuções, incidentes',
  'shell.search.shortcut': 'Ctrl K',
  'shell.theme': 'Tema',
  'shell.theme.light': 'Claro',
  'shell.theme.dark': 'Escuro',
  'shell.theme.system': 'Seguir o sistema',
  'shell.investigate': 'Investigar',
  'shell.account': 'Conta',
  'shell.account.signOut': 'Terminar sessão',
  'shell.account.impersonate': 'Agir como outra pessoa',
  'shell.deployment': 'Instalação',
  'shell.close': 'Fechar',

  'shell.guardian.active': 'Guardião activo',
  'shell.guardian.silent': 'Guardião silencioso',
  'shell.guardian.state': '{liveness} · {posture}',
  'shell.guardian.posture.propose': 'apenas propõe',
  'shell.guardian.posture.act': 'a agir',
  'shell.guardian.posture.frozen': 'congelado',

  'notifications.title': 'Precisa de si',
  'notifications.open': 'Notificações',
  'notifications.unread': '{count} por ler',
  'notifications.empty': 'Nada está à espera de uma pessoa.',
  'notifications.resolved': 'Resolvido noutro lugar',

  'palette.title': 'Paleta de comandos',
  'palette.placeholder': 'Ir para uma página, uma execução ou uma acção',
  'palette.empty': 'Nada corresponde a isso.',
  'palette.group.navigate': 'Ir para',
  'palette.group.runs': 'Execuções recentes',
  'palette.group.actions': 'Acções',
  'palette.close': 'Fechar a paleta',

  'signIn.title': 'Entrar',
  'signIn.context': 'Esta consola contacta a sua instalação e mais nada.',
  'signIn.credential': 'Token da API',
  'signIn.submit': 'Entrar',
  'signIn.rejected': 'Essa credencial não foi aceite.',
  'signIn.unreachable': 'Não foi possível contactar a instalação.',
  'signIn.expired':
    'A sua sessão terminou. Entre de novo para voltar ao ponto onde estava.',
  'session.expiring': 'Esta sessão termina em {duration}.',
  'session.expiring.action': 'Continuar com sessão iniciada',
  'session.impersonation.label': 'Personificação',
  'session.impersonation.banner': '{actor} está a agir como {subject}.',

  'error.title': 'Não foi possível mostrar esta página',
  'error.context':
    'O resto da consola continua a funcionar. Tentar de novo recarrega apenas esta página.',
  'error.retry': 'Tentar de novo',
  'notFound.title': 'Não existe essa página',
  'notFound.context': 'O endereço não corresponde a nenhuma área desta consola.',
  'notFound.action': 'Ir para a visão geral',

  'breadcrumb.label': 'Trilho',
  'avatar.unknown': 'Pessoa desconhecida',
  'pagination.previous': 'Anterior',
  'pagination.next': 'Seguinte',
  'pagination.position': 'Página {page} de {pages}',
};
