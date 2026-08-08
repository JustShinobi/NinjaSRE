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
  'nav.catalogue': 'Catalogue',
  'nav.administration': 'Administration',
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
  'page.catalogue.title': 'Catalogue',
  'page.catalogue.context':
    'Every tool and skill this deployment declares, and which of them your team may run.',
  'page.administration.title': 'Administration',
  'page.administration.context':
    'Principals, the roles they hold, the machine tokens issued, and how people sign in.',
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

  // --- What every data-bearing region says on its own behalf --------------------
  'surface.loading': 'Loading {panel}…',
  'surface.error.heading': 'This panel could not be filled',
  'surface.error.detail':
    'did not answer. The rest of this page is unaffected and this panel alone will be retried.',
  'surface.error.retry': 'Retry this panel',
  'surface.open': 'Open',
  'surface.sort.ascending': 'sort, smallest first',
  'surface.sort.descending': 'sort, largest first',
  'surface.filter.any': 'Any',
  'surface.showing': 'Showing {shown} of {total}.',
  'surface.none': 'Not recorded',
  'surface.export': 'Export',
  'surface.payload.bounded': '{total} lines in the payload; showing the first {shown}.',
  'surface.payload.expand': 'Show the full payload',
  'surface.payload.collapse': 'Bound it again',
  'surface.payload.copy': 'Copy the raw payload',
  'surface.payload.copied': 'Copied',

  // --- The transcript ------------------------------------------------------------
  'transcript.title': 'Investigation transcript',
  'transcript.kind.objective': 'Objective',
  'transcript.kind.reasoning': 'Reasoning',
  'transcript.kind.call': 'Capability call',
  'transcript.kind.result': 'Capability result',
  'transcript.kind.evidence': 'Evidence retained',
  'transcript.kind.recall': 'Memory recall',
  'transcript.kind.dispatch': 'Sub-agent dispatched',
  'transcript.kind.return': 'Sub-agent returned',
  'transcript.kind.guardrail': 'Guardrail — action withheld',
  'transcript.kind.interaction': 'Human interaction',
  'transcript.kind.report': 'Report',
  'transcript.position': 'Showing events {first} to {last} of {total}.',
  'transcript.earlier': 'Earlier events',
  'transcript.later': 'Later events',
  'transcript.empty': 'This run recorded no events.',
  'transcript.arguments': 'Arguments',
  'transcript.result': 'Result',
  'transcript.duration': '{ms} ms',
  'transcript.events': '{count} events',
  'transcript.empty.heading': 'No transcript yet',
  'transcript.empty.body':
    'A transcript appears as soon as the run takes its first turn. Nothing has been recorded for this one.',
  'transcript.empty.action': 'Back to the run list',

  // --- The overview --------------------------------------------------------------
  'dashboard.attention.title': 'Needs you',
  'dashboard.attention.count': '{count} items need you',
  'dashboard.attention.oldest': 'Oldest {age}',
  'dashboard.attention.empty.heading': 'Nothing is waiting on a person',
  'dashboard.attention.empty.body':
    'Approvals, agent questions and failed runs appear here the moment one exists. There are none.',
  'dashboard.attention.empty.action': 'See what is running',
  'dashboard.stat.watched': 'Resources watched',
  'dashboard.stat.watched.context': '{kinds}',
  'dashboard.stat.healthy': 'Healthy',
  'dashboard.stat.healthy.context': '{count} of {total} at the last sweep',
  'dashboard.stat.degraded': 'Degraded and unhealthy',
  'dashboard.stat.degraded.context': '{count} open findings behind them',
  'dashboard.stat.runs': 'Runs in the last day',
  'dashboard.stat.runs.context': '{failed} of them failed',
  'dashboard.stat.drill': 'See the list behind this figure',
  'dashboard.activity.title': 'Recent activity',
  'dashboard.activity.empty.heading': 'Nothing has happened yet',
  'dashboard.activity.empty.body':
    'Runs, incidents and sweeps appear here as they happen. Connect an infrastructure source and the first sweep starts within a minute.',
  'dashboard.activity.empty.action': 'Connect a source',
  'dashboard.estate.title': 'Estate health',
  'dashboard.estate.empty.heading': 'No resources yet',
  'dashboard.estate.empty.body':
    'Connect an infrastructure source and the estate populates itself within a minute. Nothing here is entered by hand.',
  'dashboard.estate.empty.action': 'Connect a source',
  'dashboard.guardian.title': 'Guardian',
  'dashboard.guardian.posture': 'Posture',
  'dashboard.guardian.liveness': 'Liveness',
  'dashboard.guardian.detectors': 'Detectors live',
  'dashboard.guardian.detectors.value': '{live} of {total}',
  'dashboard.guardian.review': 'Review the posture',
  'dashboard.guardian.empty.heading': 'The guardian has not reported',
  'dashboard.guardian.empty.body':
    'A guardian that stopped looks exactly like a cluster with no problems, so this panel says so rather than staying quiet.',
  'dashboard.guardian.empty.action': 'Look at the deployment',

  // --- Runs ------------------------------------------------------------------------
  'runs.column.run': 'Run',
  'runs.column.status': 'Status',
  'runs.column.trigger': 'Trigger',
  'runs.column.subject': 'Subject',
  'runs.column.started': 'Started',
  'runs.column.duration': 'Duration',
  'runs.column.cost': 'Cost',
  'runs.filter.status': 'Status',
  'runs.filter.trigger': 'Trigger',
  'runs.list.title': 'Runs',
  'runs.list.caption': 'Every run this deployment has recorded',
  'runs.empty.heading': 'No runs yet',
  'runs.empty.body':
    'A run is recorded whenever an alert, a schedule or a person starts an investigation. None has been.',
  'runs.empty.action': 'Start an investigation',
  'runs.filtered.heading': 'No run matches those filters',
  'runs.filtered.body':
    'Every filter is in the address, so clearing them is one navigation and the view you had is still shareable.',
  'runs.filtered.action': 'Clear the filters',
  'run.summary.title': 'What this run found',
  'run.usage.title': 'Cost and tokens',
  'run.usage.model': 'Model',
  'run.usage.turn': 'Turn',
  'run.usage.turns': 'Turns',
  'run.usage.calls': 'Calls',
  'run.usage.tokens': 'Tokens',
  'run.usage.cost': 'Cost',
  'run.usage.apportioned':
    'The run reports one total; the split below is that total apportioned across its turns.',
  'run.usage.empty.heading': 'No cost recorded',
  'run.usage.empty.body':
    'Cost and tokens are recorded per turn. This run has taken no turns yet.',
  'run.usage.empty.action': 'Back to the run list',
  'run.links.title': 'What this run touched',
  'run.links.resources': 'Resources',
  'run.links.incident': 'Incident',
  'run.links.empty.heading': 'Nothing linked yet',
  'run.links.empty.body':
    'Resources and incidents are linked as the run names them. This one has named none.',
  'run.links.empty.action': 'See the estate',

  // --- Incidents -------------------------------------------------------------------
  'incidents.column.severity': 'Severity',
  'incidents.column.title': 'Incident',
  'incidents.column.state': 'State',
  'incidents.column.detector': 'Detector',
  'incidents.column.opened': 'Opened',
  'incidents.column.subjects': 'Subjects',
  'incidents.filter.state': 'State',
  'incidents.filter.severity': 'Severity',
  'incidents.list.title': 'Incidents',
  'incidents.list.caption': 'Open and recently closed incidents',
  'incidents.empty.heading': 'No open incidents',
  'incidents.empty.body':
    'A detector opens an incident when what it watches crosses its threshold. None has.',
  'incidents.empty.action': 'See what is being watched for',
  'incident.subject.title': 'Subject',
  'incident.subject.resource': 'Resource',
  'incident.subject.kind': 'Kind',
  'incident.subject.health': 'Health',
  'incident.subject.lastSeen': 'Last seen',
  'incident.derivation.title': 'Why degraded',
  'incident.derivation.lead': 'Derived from {count} signals — not a provider string.',
  'incident.derivation.retained': 'The raw provider status is retained.',
  'incident.derivation.empty.heading': 'No derivation recorded',
  'incident.derivation.empty.body':
    'Health is derived from named signals against named thresholds. None was recorded for this subject.',
  'incident.derivation.empty.action': 'See the detectors',
  'incident.timeline.title': 'Timeline',
  'incident.timeline.empty.heading': 'Nothing has happened yet',
  'incident.timeline.empty.body':
    'State changes are recorded here as they happen. This incident has had none since it opened.',
  'incident.timeline.empty.action': 'Back to the incident list',

  // --- Approvals ---------------------------------------------------------------------
  'approvals.title': 'Waiting on a decision',
  'approvals.group.overdue': 'Past its expiry',
  'approvals.group.today': 'Waiting today',
  'approvals.group.later': 'Waiting longer',
  'approvals.empty.heading': 'Nothing is waiting on a decision',
  'approvals.empty.body':
    'A change that needs a person appears here with its blast radius and its rollback plan. None does.',
  'approvals.empty.action': 'See what is running',
  'proposal.title': 'Proposed action — awaiting your decision',
  'proposal.risk': 'Risk {level} of 5',
  'proposal.target': 'Target',
  'proposal.current': 'Current state',
  'proposal.change': 'Proposed change',
  'proposal.protects': 'What each protects',
  'proposal.blast': 'Blast radius',
  'proposal.rollback': 'Rollback plan',
  'proposal.verification': 'Verification',
  'proposal.autonomy': 'Autonomy',
  'proposal.approve': 'Approve',
  'proposal.reject': 'Reject',
  'proposal.reason': 'Why it is being rejected',
  'proposal.reason.required': 'A reason is required to reject.',
  'proposal.norollback': 'No rollback plan — this change is irreversible.',
  'proposal.queued': 'This change is queued rather than applied.',

  // --- Resources ---------------------------------------------------------------------
  'resources.column.name': 'Resource',
  'resources.column.kind': 'Kind',
  'resources.column.parent': 'Parent',
  'resources.column.state': 'State',
  'resources.column.utilisation': 'Utilisation',
  'resources.column.lastSeen': 'Last seen',
  'resources.filter.kind': 'Kind',
  'resources.filter.state': 'State',
  'resources.list.title': 'Resources',
  'resources.list.caption': 'Everything this deployment watches',
  'resources.sorted': 'Worst first',
  'resources.summary': '{watched} watched · {healthy} healthy · {degraded} degraded',
  'resources.empty.heading': 'No resources yet',
  'resources.empty.body':
    'Connect an infrastructure source and the estate populates itself within a minute. Nothing here is entered by hand.',
  'resources.empty.action': 'Connect a source',

  // --- Detectors ----------------------------------------------------------------------
  'detectors.column.name': 'Detector',
  'detectors.column.watches': 'What it watches',
  'detectors.column.severity': 'Severity',
  'detectors.column.coverage': 'Coverage',
  'detectors.column.verdict': 'Last verdict',
  'detectors.column.enabled': 'Enabled',
  'detectors.list.title': 'Detectors',
  'detectors.list.caption': 'Every detector, what it watches and what it last found',
  'detectors.empty.heading': 'No detectors yet',
  'detectors.empty.body':
    'Detectors ship with the deployment and appear here once continuous observation is running.',
  'detectors.empty.action': 'Connect a source',

  // --- Memory --------------------------------------------------------------------------
  'memory.episodes.title': 'Episodes',
  'memory.episodes.caption': 'What past investigations left behind',
  'memory.column.title': 'Episode',
  'memory.column.outcome': 'Outcome',
  'memory.column.components': 'Components',
  'memory.column.occurred': 'Occurred',
  'memory.filter.component': 'Component',
  'memory.filter.outcome': 'Outcome',
  'memory.search': 'Search episodes',
  'memory.stats.title': 'What the corpus holds',
  'memory.stats.episodes': 'Episodes',
  'memory.episodes.empty.heading': 'No episodes yet',
  'memory.episodes.empty.body':
    'An episode is written when an investigation ends. None has ended yet, so there is nothing to recall.',
  'memory.episodes.empty.action': 'See what is running',
  'memory.strategies.title': 'Strategies',
  'memory.strategies.lead':
    'A strategy is synthesised from the episodes below it, together with the anti-patterns those episodes produced.',
  'memory.strategies.supporting': 'Supporting episodes',
  'memory.strategies.antipatterns': 'Anti-patterns',
  'memory.strategies.edit': 'Edit this strategy',
  'memory.strategies.empty.heading': 'No strategies yet',
  'memory.strategies.empty.body':
    'A strategy is synthesised once enough episodes agree about what worked. Not enough have been recorded.',
  'memory.strategies.empty.action': 'Look at the episodes',

  // --- Knowledge -------------------------------------------------------------------------
  'knowledge.documents.title': 'Documents',
  'knowledge.documents.caption': 'The documents an investigation is allowed to read',
  'knowledge.column.title': 'Document',
  'knowledge.column.kind': 'Kind',
  'knowledge.column.updated': 'Updated',
  'knowledge.search': 'Search the knowledge base',
  'knowledge.documents.empty.heading': 'Nothing has been ingested',
  'knowledge.documents.empty.body':
    'A document reaches an investigation only after it is ingested here. None has been.',
  'knowledge.documents.empty.action': 'Configure ingestion',
  'knowledge.proposals.title': 'Proposed by an agent',
  'knowledge.proposals.lead': 'Changes an investigation proposed, awaiting review.',
  'knowledge.proposals.empty.heading': 'Nothing is awaiting review',
  'knowledge.proposals.empty.body':
    'When an investigation learns something worth writing down it proposes the change here rather than making it.',
  'knowledge.proposals.empty.action': 'Look at the documents',

  // --- Topology ---------------------------------------------------------------------------
  'topology.graph.title': 'Neighbourhood',
  'topology.list.title': 'The same graph, as a list',
  'topology.dependencies': 'Depends on',
  'topology.dependents': 'Depended on by',
  'topology.blast': 'Blast radius',
  'topology.depth': 'Depth {depth}',
  'topology.bounded':
    'Showing {shown} of {total} neighbours; the list below has all of them.',
  'topology.select': 'Select a node',
  'topology.empty.heading': 'No topology recorded',
  'topology.empty.body':
    'The graph is built from what investigations observe. Nothing has been observed about this node yet.',
  'topology.empty.action': 'See the estate',

  // --- Autonomy -----------------------------------------------------------------------------
  'autonomy.rules.title': 'Rules, in resolution order',
  'autonomy.column.scope': 'Scope',
  'autonomy.column.matcher': 'Matcher',
  'autonomy.column.level': 'Level',
  'autonomy.column.risk': 'Risk bound',
  'autonomy.column.applies': 'Applies to',
  'autonomy.footer': 'Absence of a rule resolves to propose-only.',
  'autonomy.bounds.title': 'Bounds no level overrides',
  'autonomy.preview.title': 'Preview before applying',
  'autonomy.preview.lead':
    'What the pending change would have done against recorded history.',
  'autonomy.preview.apply': 'Apply this posture',
  'autonomy.empty.heading': 'No policy recorded',
  'autonomy.empty.body':
    'With no rule recorded, everything resolves to propose-only. That is the safe default rather than an error.',
  'autonomy.empty.action': 'Look at the configuration',

  // --- Configuration --------------------------------------------------------------------------
  'configuration.tree.title': 'Organisation',
  'configuration.values.title': 'Effective configuration',
  'configuration.column.setting': 'Setting',
  'configuration.column.value': 'Value',
  'configuration.column.provenance': 'Set at',
  'configuration.locked': 'Locked here',
  'configuration.required': 'Required',
  'configuration.gated': 'Approval-gated',
  'configuration.locked.detail': 'A change made here would be refused.',
  'configuration.required.detail': 'This value may not be cleared.',
  'configuration.gated.detail': 'Saving this queues a change rather than applying it.',
  'configuration.preview.title': 'What saving would resolve to',
  'configuration.preview.lead':
    'The deployment computed this, not the console. A client-side merge that agrees today is one that disagrees after the next change.',
  'configuration.preview.before': 'Now',
  'configuration.preview.after': 'After saving',
  'configuration.preview.empty.heading': 'Nothing would change',
  'configuration.preview.empty.body':
    'A preview is the deployment’s answer to a patch. No patch is pending for this node.',
  'configuration.preview.empty.action': 'Look at the effective values',
  'configuration.empty.heading': 'No configuration here',
  'configuration.empty.body':
    'Every node inherits from the one above it. This one sets nothing of its own, so what applies is what its parent applies.',
  'configuration.empty.action': 'Look at the organisation',

  // --- The capability catalogue ------------------------------------------------------------------
  'catalogue.title': 'Capabilities',
  'catalogue.tools': 'Tools',
  'catalogue.skills': 'Skills',
  'catalogue.column.name': 'Capability',
  'catalogue.column.domain': 'Domain',
  'catalogue.column.effect': 'Side effect',
  'catalogue.column.integrations': 'Needs',
  'catalogue.column.enabled': 'Enabled here',
  'catalogue.blocked': 'Blocked by {integration}',
  'catalogue.empty.heading': 'No capabilities declared',
  'catalogue.empty.body':
    'A capability is declared by the deployment rather than configured here. This one declares none.',
  'catalogue.empty.action': 'Look at the configuration',
  'catalogue.integrations.title': 'Integrations',
  'catalogue.integrations.state': 'Connection',
  'catalogue.integrations.verified': 'Last verified',
  'catalogue.integrations.verify': 'Verify now',
  'catalogue.integrations.empty.heading': 'Nothing is connected',
  'catalogue.integrations.empty.body':
    'An integration is what lets an investigation read or change anything outside this deployment. None is installed.',
  'catalogue.integrations.empty.action': 'Look at the configuration',
  'catalogue.credential.title': 'Credentials',
  'catalogue.credential.replace': 'Replace this credential',
  'catalogue.credential.stored': 'A credential is stored. It is never shown again.',
  'catalogue.credential.absent': 'No credential is stored.',

  // --- Administration ----------------------------------------------------------------------------
  'admin.principals.title': 'People and machines',
  'admin.column.principal': 'Principal',
  'admin.column.kind': 'Kind',
  'admin.column.active': 'Active',
  'admin.grants.title': 'Grants',
  'admin.column.role': 'Role',
  'admin.column.node': 'Node',
  'admin.tokens.title': 'Machine tokens',
  'admin.column.token': 'Token',
  'admin.column.scopes': 'Scopes',
  'admin.column.expires': 'Expires',
  'admin.tokens.issue': 'Issue a token',
  'admin.tokens.revoke': 'Revoke',
  'admin.sso.title': 'Single sign-on',
  'admin.sso.configure': 'Configure single sign-on',
  'admin.sso.state': 'State',
  'admin.empty.heading': 'Nobody but you',
  'admin.empty.body':
    'Principals, grants and tokens appear here as they are issued. Only the account you are signed in with exists.',
  'admin.empty.action': 'Issue a token',

  // --- Audit ---------------------------------------------------------------------------------------
  'audit.title': 'Audit',
  'audit.caption': 'Who did what, when, and against which resource',
  'audit.column.occurred': 'When',
  'audit.column.actor': 'Principal',
  'audit.column.action': 'Action',
  'audit.column.subject': 'Subject',
  'audit.column.outcome': 'Outcome',
  'audit.filter.actor': 'Principal',
  'audit.filter.action': 'Action',
  'audit.empty.heading': 'Nothing has been recorded',
  'audit.empty.body':
    'Every consequential action is written here as it happens. None has happened in the period you are looking at.',
  'audit.empty.action': 'Widen the period',
} as const;

/** Every key the console may render. Derived, so a typo is a type error. */
export type MessageKey = keyof typeof EN;
