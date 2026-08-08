/**
 * The source catalogue.
 *
 * English is the source locale rather than the fallback of last resort: every
 * key is written here first, `MessageKey` is derived from this object, and a
 * component naming a key that is not here fails to compile. Every other locale
 * is measured against it, so "the catalogue is complete" has something to be
 * complete *about*.
 *
 * Keys read `area.thing.detail` and never carry a component name. A component
 * gets renamed; the sentence it renders does not, and a key that moved with the
 * component would strand every translation.
 */
export const EN = {
  // --- The product itself ------------------------------------------------------
  'app.name': 'NinjaSRE',
  'app.skipToContent': 'Skip to content',

  // --- Navigation --------------------------------------------------------------
  'nav.label': 'Areas',
  'nav.group.operate': 'Operate',
  'nav.group.estate': 'Estate',
  'nav.group.learn': 'Learn',
  'nav.group.govern': 'Govern',
  'nav.dashboard': 'Dashboard',
  'nav.incidents': 'Incidents',
  'nav.runs': 'Runs',
  'nav.approvals': 'Approvals',
  'nav.resources': 'Resources',
  'nav.topology': 'Topology',
  'nav.detectors': 'Detectors',
  'nav.memory': 'Memory',
  'nav.knowledge': 'Knowledge',
  'nav.autonomy': 'Autonomy',
  'nav.configuration': 'Configuration',
  'nav.audit': 'Audit',
  'nav.open': 'Open navigation',
  'nav.close': 'Close navigation',
  'nav.pending': '{count} waiting',

  // --- What each area is for ---------------------------------------------------
  'page.dashboard.title': 'Overview',
  'page.dashboard.context':
    'What needs a person, what is running, and how the estate is.',
  'page.incidents.title': 'Incidents',
  'page.incidents.context': 'What a detector opened, and what happened to it since.',
  'page.runs.title': 'Investigations',
  'page.runs.context': 'Every run this deployment has recorded, newest first.',
  'page.approvals.title': 'Approvals',
  'page.approvals.context':
    'Changes waiting on a decision, and the rollback behind each.',
  'page.resources.title': 'Resources',
  'page.resources.context':
    'Everything the deployment watches, and the health of each.',
  'page.topology.title': 'Topology',
  'page.topology.context':
    'How the estate is connected, as the platform understands it.',
  'page.detectors.title': 'Detectors',
  'page.detectors.context': 'What is being watched for, how often, and what fired.',
  'page.memory.title': 'Memory',
  'page.memory.context':
    'What past investigations left behind, and what was learned from them.',
  'page.knowledge.title': 'Knowledge',
  'page.knowledge.context': 'The documents an investigation is allowed to read.',
  'page.autonomy.title': 'Autonomy',
  'page.autonomy.context':
    'What this deployment may do on its own, and what it must ask about.',
  'page.configuration.title': 'Configuration',
  'page.configuration.context':
    'The organisation tree, and what a change to it would resolve to.',
  'page.audit.title': 'Audit',
  'page.audit.context': 'Who did what, when, and against which resource.',
  'page.pending':
    'This surface arrives with the data screens. The shell around it is complete.',

  // --- The utility bar ---------------------------------------------------------
  'shell.search': 'Search resources, runs, incidents',
  'shell.search.shortcut': 'Ctrl K',
  'shell.theme': 'Theme',
  'shell.theme.light': 'Light',
  'shell.theme.dark': 'Dark',
  'shell.theme.system': 'Follow the system',
  'shell.investigate': 'Investigate',
  'shell.account': 'Account',
  'shell.account.signOut': 'Sign out',
  'shell.account.impersonate': 'Act as somebody else',
  'shell.deployment': 'Deployment',
  'shell.close': 'Close',

  // --- The sidebar footer ------------------------------------------------------
  'shell.guardian.active': 'Guardian active',
  'shell.guardian.silent': 'Guardian silent',
  'shell.guardian.state': '{liveness} · {posture}',
  'shell.guardian.posture.propose': 'propose-only',
  'shell.guardian.posture.act': 'acting',
  'shell.guardian.posture.frozen': 'frozen',

  // --- The notification centre -------------------------------------------------
  'notifications.title': 'Needs you',
  'notifications.open': 'Notifications',
  'notifications.unread': '{count} unread',
  'notifications.empty': 'Nothing is waiting on a person.',
  'notifications.resolved': 'Resolved elsewhere',

  // --- The command palette -----------------------------------------------------
  'palette.title': 'Command palette',
  'palette.placeholder': 'Go to a page, a run, or an action',
  'palette.empty': 'Nothing matches that.',
  'palette.group.navigate': 'Go to',
  'palette.group.runs': 'Recent runs',
  'palette.group.actions': 'Actions',
  'palette.close': 'Close the palette',

  // --- The session -------------------------------------------------------------
  'signIn.title': 'Sign in',
  'signIn.context': 'This console reaches your deployment and nothing else.',
  'signIn.credential': 'API token',
  'signIn.submit': 'Sign in',
  'signIn.rejected': 'That credential was not accepted.',
  'signIn.unreachable': 'The deployment could not be reached.',
  'signIn.expired': 'Your session ended. Sign in again to return to where you were.',
  'session.expiring': 'This session ends in {duration}.',
  'session.expiring.action': 'Stay signed in',
  'session.impersonation.label': 'Impersonation',
  'session.impersonation.banner': '{actor} is acting as {subject}.',

  // --- When a page fails -------------------------------------------------------
  'error.title': 'This page could not be shown',
  'error.context':
    'The rest of the console still works. Retrying reloads this page alone.',
  'error.retry': 'Try again',
  'notFound.title': 'There is no such page',
  'notFound.context': 'The address does not name an area of this console.',
  'notFound.action': 'Go to the overview',

  // --- Strings a primitive renders on its own behalf ---------------------------
  'breadcrumb.label': 'Breadcrumb',
  'avatar.unknown': 'Unknown person',
  'pagination.previous': 'Previous',
  'pagination.next': 'Next',
  'pagination.position': 'Page {page} of {pages}',
} as const;

/** Every key the console may render. Derived, so a typo is a type error. */
export type MessageKey = keyof typeof EN;
