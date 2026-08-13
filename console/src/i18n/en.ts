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
  'nav.group.now': 'Now',
  'nav.group.environment': 'The environment',
  'nav.group.settings': 'Settings',
  'nav.firstRun': 'First steps',
  'nav.dashboard': 'Dashboard',
  'nav.incidents': 'Incidents',
  'nav.runs': 'Investigations',
  'nav.approvals': 'Actions awaiting approval',
  'nav.proposals': 'Proposed changes',
  'nav.resources': 'Resources',
  'nav.topology': 'Topology',
  'nav.detectors': 'Detectors',
  'nav.memory': 'Memory',
  'nav.knowledge': 'Knowledge',
  // What each autonomy posture actually permits, at the point somebody chooses
  // it. The deployment sends these as slugs — `propose_only`, `act_on_low_risk`
  // — and a `<Select>` offering four slugs is a control whose most consequential
  // option is indistinguishable from its least. A posture an operator misreads
  // is a posture they did not choose.
  'autonomy.level.propose_only':
    'Propose only — every action is written up for a person to approve. Nothing runs without one.',
  'autonomy.level.act_on_low_risk':
    'Act on low risk — runs on its own up to the risk bound chosen; anything riskier still waits for a person.',
  'autonomy.level.act_and_report':
    'Act and report — runs on its own and tells somebody afterwards, whatever the risk.',
  'autonomy.level.act_silently':
    'Act silently — runs on its own and reports nothing. Choose this one deliberately.',
  'nav.autonomy': 'Autonomy',
  'nav.configuration': 'Configuration',
  'nav.teamContext': 'Team context',
  'nav.catalogue': 'Catalogue',
  'nav.agent': 'The agent',
  'nav.administration': 'Administration',
  'nav.audit': 'Audit',
  'nav.data': 'Data',
  'nav.open': 'Open navigation',
  'nav.close': 'Close navigation',
  'nav.pending': '{count} waiting',
  'nav.pending.approvals': '{count} actions awaiting approval',
  'nav.pending.proposals': '{count} proposals waiting',
  'nav.pending.incidents': '{count} open incidents',
  'nav.pending.runs': '{count} failed investigations',

  // --- What each area is for ---------------------------------------------------
  'page.firstRun.title': 'First steps',
  'page.firstRun.context':
    'What to set up, in order, with the reason for each and the option to stop after any of them.',
  'page.dashboard.title': 'Overview',
  'page.dashboard.context':
    'What needs a person, what is running, and how the estate is.',
  'page.incidents.title': 'Incidents',
  'page.incidents.context': 'What a detector opened, and what happened to it since.',
  'page.runs.title': 'Investigations',
  'page.runs.context':
    'Every investigation this deployment has recorded, newest first.',
  'page.approvals.title': 'Actions awaiting approval',
  'page.approvals.context':
    'Actions the agent wants to take now, waiting for your approval. Each carries its blast radius and rollback plan.',
  'page.proposals.title': 'Proposed changes',
  'page.proposals.context':
    'Everything the agent has proposed and nobody has decided. Each carries what would change, why, and the investigation it came out of.',
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
  'page.teamContext.title': 'Team context',
  'page.teamContext.context':
    'Facts about this environment that every investigation should start from.',
  'page.catalogue.title': 'Catalogue',
  'page.catalogue.context':
    'Every tool and skill this deployment declares, and which of them your team may run.',
  'page.agent.title': 'The agent',
  'page.agent.context':
    'What it is, what it can do, and what it will do without asking anybody.',
  'page.administration.title': 'Administration',
  'page.administration.context':
    'Principals, the roles they hold, the machine tokens issued, and how people sign in.',
  'page.audit.title': 'Audit',
  'page.audit.context': 'Who did what, when, and against which resource.',
  'page.data.title': 'Data',
  'page.data.context': 'What arrives, what is done with it, and where the result goes.',
  'page.pending':
    'This surface arrives with the data screens. The shell around it is complete.',

  // --- Where data comes from and where it goes ---------------------------------
  'data.ingress.title': 'What arrives',
  'data.ingress.never': 'Nothing has ever arrived here',
  'data.ingress.last': 'Last delivery',
  'data.ingress.sample': 'Last payload, masked',
  'data.ingress.empty.heading': 'No receiver is configured',
  'data.ingress.empty.body':
    'Point an alert router at one of this deployment\u2019s webhook addresses and its deliveries appear here.',
  'data.ingress.empty.action': 'Open the catalogue',
  'data.rules.title': 'What happens to it',
  'data.rules.action': 'Action:',
  'data.rules.catchAll': 'Everything no rule above matched ends here.',
  'data.rules.empty.heading': 'No rule is configured',
  'data.rules.empty.body':
    'Every verified delivery is investigated by the team that verified it.',
  'data.rules.empty.action': 'Open configuration',
  'data.simulate.source': 'Receiver',
  'data.simulate.payload': 'Payload',
  'data.simulate.action': 'Simulate',
  'data.simulate.running': 'Simulating\u2026',
  'data.simulate.save': 'Save',
  'data.simulate.needed':
    'Simulate this payload before saving, so the effect is seen first.',
  'data.simulate.failed': 'The deployment refused the simulation.',
  'data.simulate.unreachable': 'The deployment could not be reached.',
  'data.simulate.malformed': 'That is not valid JSON.',
  'data.delivery.title': 'Where the result goes',
  'data.delivery.masking': 'Masking policy:',
  'data.delivery.resend': 'Send again',
  'data.delivery.resending': 'Sending\u2026',
  'data.delivery.resent': 'Delivered',
  'data.delivery.resendFailed': 'It did not arrive this time either.',
  'data.delivery.empty.heading': 'No destination is declared',
  'data.delivery.empty.body': 'Nothing is told when an investigation concludes.',
  'data.delivery.empty.action': 'Open configuration',
  'data.provenance.open': 'Where did this go?',
  'data.provenance.source': 'Arrived by',
  'data.provenance.rule': 'Rule',
  'data.provenance.team': 'Team',
  'data.provenance.run': 'Investigation',
  'data.provenance.resource': 'Resource',
  'data.provenance.none': 'Nothing has arrived here to trace.',

  // --- The utility bar ---------------------------------------------------------
  'shell.search': 'Search resources, investigations, incidents',
  'shell.search.shortcut': 'Ctrl K',
  'shell.theme': 'Theme',
  'shell.density.comfortable': 'Comfortable rows',
  'shell.density.compact': 'Compact rows',
  'shell.theme.light': 'Light',
  'shell.theme.dark': 'Dark',
  'shell.theme.system': 'Follow the system',
  'shell.investigate': 'Investigate',
  'shell.viewTour': 'View the tour',
  'shell.account': 'Account',
  'shell.account.signOut': 'Sign out',
  'shell.account.impersonate': 'Act as somebody else',
  'shell.account.language': 'Language',
  'shell.language.en': 'English',
  'shell.language.pt-BR': 'Português (Brasil)',
  'shell.deployment': 'Deployment',
  'shell.close': 'Close',

  // --- The emergency stop ------------------------------------------------------
  'stop.engage': 'Stop automation',
  'stop.consequence':
    'This stops every automated write, immediately, everywhere this deployment acts. Investigations keep running and keep proposing; nothing is applied until somebody releases it.',
  'stop.confirm': 'Stop everything now',
  'stop.cancel': 'Leave it running',
  'stop.release': 'Let automation run again',
  'stop.engaged':
    'Automated writes are stopped. Investigations still run and still propose; nothing is applied.',
  'stop.engaged.by': 'Stopped by {by}, {since}.',
  'stop.engaged.unknown': 'Stopped before this page could say who or when.',
  'stop.engaged.howToRelease':
    'Anyone who may stop this deployment can release it from the top of the screen.',
  'stop.reason': 'Stopped from the console.',
  'stop.autonomy': 'Review the Autonomy posture',
  'stop.refused': 'The deployment refused to change the stop.',
  'stop.unreachable': 'The deployment could not be reached. Stop it by hand.',

  // --- The sidebar footer ------------------------------------------------------
  'shell.guardian.active': 'Guardian active',
  'shell.guardian.silent': 'Guardian silent',
  'shell.guardian.state': '{liveness} · {posture}',
  'shell.guardian.posture.propose': 'propose-only',
  'shell.guardian.posture.act': 'acting',
  'shell.guardian.posture.frozen': 'frozen',
  'shell.guardian.tooltip':
    'What the posture means: propose-only shows every change and its blast radius, and applies nothing until you approve it. Open Autonomy to see or change it.',

  // --- The notification centre -------------------------------------------------
  'notifications.title': 'Needs you',
  'notifications.open': 'Notifications',
  'notifications.unread': '{count} unread',
  'notifications.empty': 'Nothing is waiting on a person.',
  'notifications.resolved': 'Resolved elsewhere',

  // --- What a failure is called, when the deployment names an exception --------
  // Every one of these replaces a sentence written for whoever deploys this,
  // shown to whoever opened the console. The raw text is still available under
  // "technical detail" — see `surfaces/failures.ts`.
  'failure.technical': 'Technical detail',
  'failure.investigator.title': 'Investigations are not switched on yet',
  // Not "finish choosing a model": this fires whether or not one has been
  // chosen. It is the deployment's own runtime, composed by whoever operates
  // it, and telling somebody to redo a configuration step that is already
  // done sends them back to a screen with nothing left for them to change.
  // Also read verbatim by `InvestigateDrawer` (`src/live/investigate.tsx`) as
  // its own before-the-click caveat — one sentence, so the two surfaces
  // cannot drift onto two different explanations for the same missing
  // runtime.
  'failure.investigator.action':
    'This deployment has no runtime to investigate with — the model chosen here has nothing to do with that. Whoever operates it needs to supply a runtime; the guided setup names the dependency once everything else here is done.',
  'failure.credential.title': 'A key is missing for something this needed',
  'failure.credential.action':
    'Store the credential for the system this was trying to reach.',
  'failure.vaultKey.title': 'A stored key cannot be read back',
  'failure.vaultKey.action':
    'This deployment’s encryption key has changed since the credential was stored. Store it again.',
  'failure.store.title': 'This deployment cannot reach its own database',
  'failure.store.action':
    'Nothing in this console fixes it — whoever runs the deployment needs to look.',
  'failure.migrations.title': 'This deployment is running an older schema',
  'failure.migrations.action':
    'The database is behind the code. Whoever runs the deployment needs to apply the migrations.',
  'failure.unknown.title': 'Something went wrong that this console cannot explain',
  'failure.unknown.action':
    'The deployment’s own words are under the technical detail below.',

  // --- The command palette -----------------------------------------------------
  'palette.title': 'Command palette',
  'palette.placeholder':
    'Search resources, incidents and investigations, or go to a page',
  'palette.empty': 'Nothing matches that.',
  // A page was read and nothing in it matched, which is not the same claim as
  // the thing not existing. Saying so is the difference between a search
  // somebody trusts and one they learn to check by hand afterwards.
  'palette.empty.partial':
    'Nothing in what was searched matches that — there is more than one page of results to look through.',
  'palette.group.resources': 'Resources',
  'palette.group.incidents': 'Incidents',
  'palette.group.found-runs': 'Matching investigations',
  'palette.group.navigate': 'Go to',
  'palette.group.runs': 'Recent investigations',
  'palette.group.actions': 'Actions',
  'palette.close': 'Close the palette',

  // --- The session -------------------------------------------------------------
  'signIn.title': 'Sign in',
  'signIn.context': 'This console reaches your deployment and nothing else.',
  'signIn.username': 'Username',
  'signIn.password': 'Password',
  'signIn.submit': 'Sign in',
  'signIn.rejected': 'That username and password were not accepted.',
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
  // Named, because these are appended to a column heading and a reader hears
  // the two together. "Started sort, smallest first" is not a sentence and does
  // not say which column it is about — three specs reported it independently,
  // from Investigations, Resources and Audit. The current direction is carried
  // by `aria-sort` on the header; what this says is what pressing it will do.
  'surface.sort.ascending': 'sort by {column}, smallest first',
  'surface.sort.descending': 'sort by {column}, largest first',
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
  'transcript.empty': 'This investigation recorded no events.',
  'transcript.arguments': 'Arguments',
  'transcript.result': 'Result',
  'transcript.duration': '{ms} ms',
  'transcript.events': '{count} events',
  'transcript.events.one': '{count} event',
  'transcript.empty.heading': 'No transcript yet',
  'transcript.empty.body':
    'A transcript appears as soon as the investigation takes its first turn. Nothing has been recorded for this one.',
  'transcript.empty.action': 'Back to the investigations',

  // --- The overview --------------------------------------------------------------
  'dashboard.attention.title': 'Needs you',
  'dashboard.attention.count': '{count} items need you',
  'dashboard.attention.count.one': '{count} item needs you',
  'dashboard.attention.oldest': 'Waiting longest: {age}',
  'dashboard.attention.empty.heading': 'Nothing is waiting on a person',
  'dashboard.attention.empty.body':
    'Approvals, agent questions and failed investigations appear here the moment one exists. There are none.',
  'dashboard.attention.empty.action': 'See what is running',
  'dashboard.stat.watched': 'Resources watched',
  'dashboard.stat.watched.context': '{kinds}',
  'dashboard.stat.healthy': 'Healthy',
  'dashboard.stat.healthy.context': '{count} of {total} at the last sweep',
  'dashboard.stat.degraded': 'Degraded and unhealthy',
  'dashboard.stat.degraded.context':
    '{count} open findings behind them; {live} of {total} detectors are switched on to raise one of them into an incident',
  'dashboard.stat.runs': 'Recent investigations',
  'dashboard.stat.runs.context': '{failed} of them failed',
  'dashboard.stat.successRate': 'Success rate',
  'dashboard.stat.successRate.context':
    '{succeeded} of {settled} finished investigations succeeded',
  'dashboard.stat.successRate.context.none': 'No investigation has finished yet',
  'dashboard.stat.drill': 'See the list behind this figure',
  'dashboard.activity.title': 'Recent activity',
  'dashboard.activity.empty.heading': 'Nothing has happened yet',
  'dashboard.activity.empty.body':
    'Investigations, incidents and sweeps appear here as they happen. Connect an infrastructure source and the first sweep starts within a minute.',
  'dashboard.activity.empty.action': 'Connect a source',
  'dashboard.hero.title': 'Continue setting up',
  'dashboard.hero.remaining': '{count} of {total} steps left',
  'dashboard.hero.next': 'Next',
  'dashboard.hero.action': 'Continue setting up',
  'dashboard.hero.empty.heading': 'Setup state could not be read',
  'dashboard.hero.empty.body':
    'This is drawn from the deployment’s own setup checklist, and it did not answer. Everything else on this page is unaffected.',
  'dashboard.hero.empty.action': 'Open first steps',
  'dashboard.quickActions.title': 'Quick actions',
  'dashboard.quickActions.empty.heading': 'Nothing to do from here',
  'dashboard.quickActions.empty.body':
    'These are the destinations the setup checklist is asking for. It is asking for none.',
  'dashboard.quickActions.empty.action': 'Go to the overview',
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

  // --- Writing a credential, wherever it is written from -----------------------------
  'credential.submit': 'Store this credential',
  'credential.sending': 'Storing…',
  'credential.stored': 'Stored in the vault. It is never shown again.',
  'credential.absent': 'This one declares no credential fields.',
  'credential.whereToGetIt': 'Where to get it:',
  'credential.required': 'Every required field needs a value.',
  'credential.saved': 'Stored. Nothing you typed is kept here.',

  // --- The guided first run -----------------------------------------------------------
  'firstRun.steps.title': 'What is left',
  'firstRun.steps.done': 'Every step is done',
  // The dashboard's own hero says "{count} of {total} steps left" for this
  // same fact; this line used to say "done" instead, which made the two
  // screens state one number in two framings a reader had to reconcile by
  // hand.
  'firstRun.progress': '{left} of {total} steps left',
  'firstRun.steps.empty.heading': 'This deployment did not say what is left',
  'firstRun.steps.empty.body':
    'The setup checklist is what this screen is drawn from, and it could not be read. The rest of the console is unaffected.',
  'firstRun.steps.empty.action': 'Go to the overview',
  'firstRun.refused': 'The deployment refused:',
  'firstRun.unreachable': 'The deployment could not be reached.',

  'firstRun.step.provider': 'Choose a model provider',
  'firstRun.step.credential': 'Store its credential',
  'firstRun.step.model': 'Choose a model',
  'firstRun.step.integrations': 'Connect what it may look at',
  'firstRun.step.verify': 'Check that each of them works',
  'firstRun.step.estate': 'Give it an estate to watch',
  'firstRun.step.alerts': 'Point your alerts at it',
  'firstRun.step.here': 'You are here',
  // The map from a poetic step name to the screen it actually leads to. Only
  // the two steps this feature hands over to a real screen carry one — the
  // other five are sub-steps of this same wizard, with no screen of their
  // own to name.
  'firstRun.step.onScreen': 'Continues on {screen}',

  'firstRun.why.provider':
    'Nothing can be verified without one, and the platform refuses to start without one configured. All nine are offered on the same terms, including the one that runs on your own hardware.',
  'firstRun.why.credential':
    'The value goes straight to the vault. It is not written to configuration, not returned, and never shown again — not even masked.',
  'firstRun.why.model':
    'Which model this deployment thinks with. Saving asks the deployment what the change would resolve to before it is made.',
  'firstRun.why.integrations':
    'Optional, every one of them. A deployment with a provider and no integration still investigates — from what it is told rather than from what it can go and look at.',
  'firstRun.why.verify':
    'Not optional, and not free: each check makes a real request. A stored credential and a working one are the two states you are trying to tell apart at three in the morning.',
  'firstRun.why.estate':
    'What turns an installed platform into one that knows what it is responsible for.',
  'firstRun.why.alerts':
    'The receivers exist. Nothing points at them yet, so nothing arrives on its own.',

  'firstRun.provider.local': 'Runs on your own infrastructure',
  'firstRun.provider.hosted': 'Hosted — requests leave your infrastructure',
  'firstRun.provider.choose': 'Use this provider',
  'firstRun.credential.chooseFirst': 'No provider has been chosen yet.',

  'firstRun.model.known': 'Model',
  'firstRun.model.free': 'Model identifier',
  'firstRun.model.preview': 'What would this change?',
  'firstRun.model.previewing': 'Asking…',
  'firstRun.model.save': 'Save it',
  'firstRun.model.saving': 'Saving…',
  'firstRun.model.wouldChange': 'Saving this would resolve to:',
  'firstRun.model.nothingWouldChange':
    'Nothing would change: this is already what applies.',
  'firstRun.model.saved': 'Saved.',
  'firstRun.model.needsPreview': 'See what it would change before saving it.',

  'firstRun.integrations.search': 'Search the catalogue',
  'firstRun.integrations.none': 'Nothing in the catalogue matches that.',
  'firstRun.integrations.connected': 'A credential is stored for this one.',
  'firstRun.integrations.notConnected': 'Nothing is stored for this one.',
  'firstRun.integrations.optional':
    'Every one of these is optional, and one that fails does not abandon the rest.',
  'firstRun.integrations.summary': 'Connected in this session: {names}.',
  'firstRun.integrations.summaryNone': 'Nothing has been connected in this session.',
  'firstRun.integrations.failed': 'These were refused and can be tried again:',

  'firstRun.verify.check': 'Check it',
  'firstRun.verify.checking': 'Checking…',
  'firstRun.verify.retry': 'Check it again',
  'firstRun.verify.passed': 'It answered.',
  'firstRun.verify.failed': 'It did not answer.',
  'firstRun.verify.unchecked': 'Nobody has checked this one.',
  'firstRun.verify.nothing':
    'Nothing is configured yet, so there is nothing to check. Store a provider credential first.',
  'firstRun.verify.remedy': 'What to do:',
  'firstRun.verify.findings': 'It answered, and what it answered cannot be relied on:',

  'firstRun.established.title': 'What is set up so far',
  'firstRun.established.verified': 'it answered',
  'firstRun.established.configured': 'stored, unchecked',
  'firstRun.established.empty.heading': 'Nothing is set up yet',
  'firstRun.established.empty.body':
    'Everything this deployment holds a credential for appears here, with whether anything has actually reached it. It holds none, so it cannot investigate yet.',
  'firstRun.established.empty.action': 'Choose a model provider',
  'firstRun.estate.integration':
    'The estate comes from {integration}, whose credential is stored.',
  'firstRun.estate.check': 'Ask the cluster what this token may do',
  'firstRun.estate.checking': 'Asking…',
  'firstRun.estate.recheck': 'Ask again',
  'firstRun.estate.sufficient': 'The token can read everything this deployment needs.',
  'firstRun.estate.insufficient':
    'The token cannot read everything this deployment needs.',
  'firstRun.estate.missingRead': 'Missing, and each one stops something working:',
  'firstRun.estate.missingAdvisory':
    'Granted by the recommended role and not held. Nothing stops working today:',
  'firstRun.estate.grantedAt': 'Granted at:',
  'firstRun.estate.preview': 'Look at what would be discovered',
  'firstRun.estate.previewing': 'Looking…',
  'firstRun.estate.found':
    '{nodes} nodes, {guests} guests, {running} running, {zones} zones. Nothing has been stored.',
  'firstRun.estate.unplaced':
    '{count} of them sit on no declared network, so they carry no zone.',
  'firstRun.estate.incomplete':
    'The cluster did not finish enumerating in one pass, so these are a floor rather than a total.',
  'firstRun.estate.confirm': 'Discover this estate from now on',
  'firstRun.estate.confirming': 'Registering…',
  'firstRun.estate.confirmed': 'Registered. The first sweep is due now.',
  'firstRun.estate.needsPreview':
    'Look first. Confirming without having read the counts is a form, not a decision.',
  'firstRun.handover.estate': 'Go to the estate',
  'firstRun.handover.alerts': 'Go to the detectors',
  // What names the dependency the seven steps above have no page for: a
  // runtime composed by whoever deployed this, not a configuration field.
  // Read from the checklist's own fifth step, so this and the self-check
  // cannot drift onto two different sentences for the same fact.
  'firstRun.runtimeGap.heading': 'What is actually stopping this',
  // The final state: six of seven wizard steps done, a runtime composed, and
  // no investigation has finished yet — the one moment this is genuinely
  // "you are ready" rather than "you already ran one".
  'firstRun.complete.heading': 'Everything here is ready.',
  'firstRun.complete.body':
    'Every step above is done, and this deployment can drive a real investigation. Press Investigate, at the top of any screen, to run the first one.',
  'firstRun.complete.body.noPermission':
    'Every step above is done, and this deployment can drive a real investigation. Ask somebody who may start one to run the first.',

  // --- Setup and the tutorial, where an operator is already working ---------------------
  // The checklist panel and the quick-action list that used to live here went
  // with the components that read them: the remaining plan is the dashboard's
  // hero, and the destinations are named by their own screens' headers.
  'setup.noProvider.heading': 'No model provider is configured',
  'setup.noProvider.body':
    'Nothing can be investigated until one is. It takes one credential, and the platform offers nine providers including one that runs on your own hardware.',
  'setup.noProvider.action': 'Choose a provider',

  'tutorial.title': 'What this is, in five screens',
  'tutorial.skip': 'Skip',
  'tutorial.close': 'Close',
  'tutorial.next': 'Next',
  'tutorial.back': 'Back',
  'tutorial.done': 'Start setting it up',
  'tutorial.progress': '{step} of {total}',
  'tutorial.slide.1.title': 'It investigates, it does not just alert',
  'tutorial.slide.1.body':
    'An alert arrives, an investigation starts, and what comes back is a diagnosis with the evidence behind it — not a graph and a shrug.',
  'tutorial.slide.2.title': 'How an investigation works',
  'tutorial.slide.2.body':
    'It reasons, calls the tools your integrations unlock, keeps every reading it used, and stops when it can say why. You can watch it, interrupt it, and take over.',
  'tutorial.slide.3.title': 'What to connect',
  'tutorial.slide.3.body':
    'A model provider first — nothing works without one. Then whatever it should be allowed to look at. Quality follows from what it can read.',
  'tutorial.slide.4.title': 'What it may do on its own',
  'tutorial.slide.4.body':
    'Nothing, until you say otherwise. Every change is proposed with its blast radius and its rollback until the posture says it may act.',
  'tutorial.slide.5.title': 'Try it before it counts',
  'tutorial.slide.5.body':
    'Describe an incident and watch a real investigation run. With nothing connected it reasons and consults nothing, which is honest rather than impressive.',

  // --- Runs ------------------------------------------------------------------------
  'runs.column.run': 'Investigation',
  'runs.column.status': 'Status',
  'runs.column.trigger': 'Trigger',
  'runs.column.subject': 'Subject',
  'runs.column.started': 'Started',
  'runs.column.duration': 'Duration',
  'runs.column.cost': 'Cost',
  'runs.filter.status': 'Status',
  'runs.filter.trigger': 'Trigger',
  'runs.list.title': 'Investigations',
  'runs.trigger.manual': 'Manual',
  'runs.trigger.alert': 'Alert',
  'runs.trigger.scheduled': 'Scheduled',
  'runs.trigger.specialist': 'Specialist',
  'runs.list.caption': 'Every investigation this deployment has recorded',
  'runs.empty.heading': 'No investigations yet',
  'runs.empty.body':
    'An investigation is recorded whenever an alert, a schedule or a person starts one. None has been.',
  'runs.empty.action': 'Start an investigation',
  'runs.filtered.heading': 'No investigation matches those filters',
  'runs.filtered.body':
    'Every filter is in the address, so clearing them is one navigation and the view you had is still shareable.',
  'runs.filtered.action': 'Clear the filters',
  'run.summary.title': 'What this investigation found',
  'run.usage.title': 'Cost and tokens',
  'run.usage.model': 'Model',
  'run.usage.turn': 'Turn',
  'run.usage.turns': 'Turns',
  'run.usage.calls': 'Calls',
  'run.usage.tokens': 'Tokens',
  'run.usage.cost': 'Cost',
  'run.usage.apportioned':
    'The investigation reports one total; the split below is that total apportioned across its turns.',
  'run.usage.empty.heading': 'No cost recorded',
  'run.usage.empty.body':
    'Cost and tokens are recorded per turn. This investigation has taken no turns yet.',
  'run.usage.empty.action': 'Back to the investigations',
  'run.changes.title': 'What changed, on the same ruler',
  'run.changes.body':
    'Every change the investigation looked at, placed against the moment it began. A change marked as managing the affected resource altered something that governs it; one marked as a coincidence only shares the window.',
  'run.changes.investigation': 'this investigation began',
  'run.changes.window': 'from {start} to {end}',
  'run.links.title': 'What this investigation touched',
  'run.links.resources': 'Resources',
  'run.links.incident': 'Incident',
  'run.links.empty.heading': 'Nothing linked yet',
  'run.links.empty.body':
    'Resources and incidents are linked as the investigation names them. This one has named none.',
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
  // --- Why this deployment is empty, as opposed to what the feature is for ----
  // Shared by every screen downstream of the setup: incidents, approvals, the
  // graph, the episodes, the documents. See `surfaces/emptiness.ts` — the point
  // is that "nothing is wrong" and "nothing is watching" must stop rendering
  // identically, because they are opposite situations.
  'empty.cause.setup':
    'Nothing has happened here yet because this deployment is still being set up — {count} step(s) are outstanding, and investigations cannot run until they are done.',
  'empty.cause.setup.action': 'Finish setting up',
  'empty.cause.watching':
    'No detector is switched on, so nothing is being watched and nothing will open by itself.',
  'empty.cause.watching.action': 'Turn on continuous observation',

  'incidents.empty.heading': 'No open incidents',
  'incidents.empty.body':
    'A detector opens an incident when what it watches crosses its threshold. None has.',
  'incidents.empty.action': 'See what is being watched for',
  'incidents.preview.link': 'See an example incident',
  'incidents.preview.title': 'What an incident looks like',
  'incidents.preview.body':
    'An incident names what crossed a detector threshold, the affected subject, and the evidence that made it actionable. This is an example, not a live incident.',
  'incidents.preview.label.detector': 'Detector',
  'incidents.preview.label.subject': 'Subject',
  'incidents.preview.label.evidence': 'Evidence',
  'incidents.preview.example.title': 'Datastore near full',
  'incidents.preview.example.detector': 'datastore-near-full',
  'incidents.preview.example.subject': 'store-cove',
  'incidents.preview.example.evidence': 'data_percent = 95.65',
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
  'approvals.otherInbox': 'For changes the agent has proposed for the deployment:',
  'approvals.empty.rule':
    'The active rule asks for approval for actions at {threshold} and above.',
  'approvals.empty.rule.default': 'This is the deployment default.',
  'approvals.empty.rule.setAt': 'It is set at {node}.',
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
  'resources.column.zone': 'Zone',
  'resources.column.criticality': 'Criticality',
  'resources.filter.zone': 'Zone',
  'resources.filter.criticality': 'Criticality',
  'resources.filter.health': 'Health',
  'resources.filter.problem': 'Degraded or unhealthy',
  'resources.zone.unplaced': 'Unplaced',
  'resources.zone.unplaced.hint':
    'No declared network covers this resource’s address. Declare its zone in configuration.',
  'resources.criticality.ungraded': 'Ungraded',
  'resources.criticality.ungraded.hint':
    'Nobody has declared how critical this resource is. Declare it in configuration.',
  'resources.list.title': 'Resources',
  'resources.list.caption': 'Everything this deployment watches',
  'resources.sorted': 'Worst first',
  'resources.sorted.hint':
    'The default order — click a column heading below to sort a different way.',
  // Every health state the badges below use gets a number here, including
  // unhealthy — which had none anywhere on the screen while `problems` folded
  // it into degraded. A header that cannot be added up against the table under
  // it is a header nobody trusts twice.
  'resources.summary':
    '{watched} watched · {healthy} healthy · {degraded} degraded · {unhealthy} unhealthy',
  'resources.filter.name': 'Resource name',
  'resources.divergent.mark': '(not in the inventory)',
  'resources.divergent.hint':
    'The declared inventory is the file that says what should exist here, and this resource is not in it. Add it to the inventory, or ignore it if it should not be tracked.',
  'resources.detail.back': 'Back to the list',
  'resources.signals.title': 'Where its signals come from',
  'resources.signals.body':
    'Which source answers each question about this resource, and by what key. A container shares its host\u2019s kernel, so its resource usage is read from the host\u2019s own series rather than from inside the guest.',
  'resources.signals.missing': 'nothing configured answers this',
  'resources.documents.title': 'What has been written about it',
  'resources.documents.body':
    'Documents from the corpus that name this resource, with the name each one used. A link drawn from a name can be wrong \u2014 the name is here so you can tell.',
  'resources.changes.title': 'What changed underneath it',
  'resources.changes.body':
    'Changes correlated through the resource rather than by the clock. A change marked as managing this resource altered something that governs it; one marked as a coincidence only shares the window, and is here so you can rule it out.',
  'resources.changes.manages': 'manages this resource',
  'resources.changes.policy': 'shared policy',
  'resources.changes.coincidence': 'same window only',
  'resources.changes.unapplied': 'committed, never applied',
  'resources.departed.title': 'Declared and gone',
  'resources.departed.body':
    'The inventory still names these and the source no longer reports them. A resource that exists only in a file is one that no longer exists.',
  'resources.unresolved.title': 'Alerts for things not here',
  'resources.unresolved.body':
    'Something is alerting about a target this estate does not hold. Either nobody has swept it, or an alert receiver is pointed at the wrong deployment — and both are worth knowing.',
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
  'detectors.proposed': 'proposed by a document',
  'detectors.list.title': 'Detectors',
  'detectors.list.caption': 'Every detector, what it watches and what it last found',
  'detectors.empty.heading': 'No detectors yet',
  'detectors.empty.body':
    'Detectors ship with the deployment and appear here once continuous observation is running.',
  'detectors.empty.action': 'Connect a source',
  'detectors.control.dryRun': 'Preview what this would fire on',
  'detectors.control.dryRunning': 'Checking…',
  'detectors.control.wouldFire': 'This would fire against what is stored now.',
  'detectors.control.wouldNotFire': 'This would not fire against what is stored now.',
  'detectors.control.observations': 'What it would conclude now',
  'detectors.control.noObservations': 'Nothing is observed for this detector yet.',
  'detectors.control.enable': 'Enable',
  'detectors.control.enabling': 'Enabling…',
  'detectors.control.disable': 'Disable',
  'detectors.control.disabling': 'Disabling…',
  'detectors.control.cancel': 'Cancel',
  'detectors.control.failed': 'The deployment refused this.',
  'detectors.control.unreachable': 'The deployment could not be reached.',

  // --- Schedules -------------------------------------------------------------------------
  'schedules.title': 'Scheduled investigations',
  'schedules.caption':
    'Every recurring investigation this team has scheduled, and what it runs on',
  'schedules.empty.heading': 'No scheduled investigations',
  'schedules.empty.body':
    'A schedule runs an investigation on a cron expression, on its own, without somebody starting it. None is set up for this team yet.',
  'schedules.empty.action': 'Create one below',
  'schedules.column.name': 'Name',
  'schedules.column.cron': 'Cron',
  'schedules.column.objective': 'Objective',
  'schedules.column.timezone': 'Timezone',
  'schedules.column.nextRun': 'Next investigation',
  'schedules.column.enabled': 'Enabled',
  'schedules.never': 'Not scheduled',
  'schedules.enable': 'Enable',
  'schedules.enabling': 'Enabling…',
  'schedules.disable': 'Disable',
  'schedules.disabling': 'Disabling…',
  'schedules.save': 'Save',
  'schedules.saving': 'Saving…',
  'schedules.delete': 'Delete schedule',
  'schedules.deleteConsequence':
    'This scheduled investigation is removed immediately, and nothing restores it from here.',
  'schedules.deleteCancel': 'Cancel',
  'schedules.deleteClose': 'Close',
  'schedules.create.title': 'Schedule a new investigation',
  'schedules.create.jobId': 'Identifier',
  'schedules.create.name': 'Name',
  'schedules.create.cron': 'Cron',
  'schedules.create.objective': 'Objective',
  'schedules.create.timezone': 'Timezone',
  // Help beside the fields rather than in documentation nobody has open. The
  // identifier/name distinction and the cron layout are the two things an
  // operator gets wrong, and the deployment's refusal does not say which of
  // five positions was at fault.
  'schedules.create.jobIdHelp':
    'A stable identifier this schedule keeps even if its name changes later.',
  'schedules.create.nameHelp':
    'What operators see in this list. Safe to rename; the identifier does not move.',
  'schedules.create.cronHelp':
    'Five fields — minute, hour, day of month, month, day of week. `0 8 * * 1` runs every Monday at 08:00.',
  'schedules.create.objectiveHelp':
    'The instruction the investigation runs with, exactly as if somebody had typed it to start one by hand.',
  'schedules.create.timezoneHelp':
    'The zone the cron expression is read in. An IANA name, such as Europe/Lisbon.',
  'schedules.create.submit': 'Create schedule',
  'schedules.create.submitting': 'Creating…',
  'schedules.create.created': 'Schedule created: {name}.',
  'schedules.create.previewing': 'Checking the cron expression…',
  'schedules.create.previewLabel': 'Would next fire:',
  'schedules.failed': 'The deployment refused this.',
  'schedules.unreachable': 'The deployment could not be reached.',

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
  // "Configure ingestion" named a control that does not exist. The gateway
  // serves two knowledge routes and both are reads; there is no upload, no
  // paste, and no connect-a-source anywhere in this console. A document arrives
  // one of two ways, and both are named here rather than implied.
  'knowledge.documents.empty.body':
    'Nothing here yet, and this console has no upload or connect-a-source control to offer. A document reaches this corpus when the sync your deployment was set up with brings it in, or when an investigation proposes one and a reviewer approves it.',
  'knowledge.documents.empty.action': 'Review what has been proposed',
  'knowledge.proposals.title': 'Proposed by an agent',
  'knowledge.proposals.lead':
    'Changes an investigation proposed, awaiting review in the same queue as every other proposed change.',
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
  'autonomy.editor.level': 'Level',
  'autonomy.editor.preview': 'What would this decide differently?',
  'autonomy.editor.previewing': 'Asking the deployment…',
  'autonomy.editor.explain': 'Explain one action',
  'autonomy.editor.explaining': 'Explaining…',
  'autonomy.editor.capability': 'Capability',
  'autonomy.editor.resource': 'Resource',
  'autonomy.editor.save': 'Save this posture',
  'autonomy.editor.saving': 'Saving…',
  'autonomy.editor.saved': 'Saved. This is what the deployment may now do on its own.',
  'autonomy.editor.failed': 'The deployment refused this posture.',
  'autonomy.editor.unreachable': 'The deployment could not be reached.',
  'autonomy.editor.previewFirst':
    'See what this would have decided differently before saving it. The list of what becomes autonomous is the half worth reading.',
  'autonomy.editor.considered': 'Considered',
  'autonomy.editor.changed': 'Decided differently',
  'autonomy.editor.newlyAutonomous': 'Newly autonomous',
  'autonomy.editor.nothingChanges': 'Nothing would become more autonomous.',
  'autonomy.editor.dryRunOn': 'Simulate everything',
  'autonomy.editor.dryRunOff': 'Stop simulating',
  'autonomy.editor.dryRunBanner':
    'Simulating: every action is decided and none of them is performed. This deployment proposes and does not act.',
  'autonomy.editor.decision': 'Decision',
  'autonomy.editor.winningRule': 'Winning rule',
  'autonomy.override.duration': 'Expires',
  'autonomy.override.reason': 'Granted because',
  'autonomy.override.grantedBy': 'Granted by',
  'autonomy.override.panel.title': 'Grant or revoke an override',
  'autonomy.override.grant.title': 'Grant an override',
  'autonomy.override.grant.name': 'Name',
  'autonomy.override.grant.level': 'Level',
  'autonomy.override.grant.reason': 'Reason',
  'autonomy.override.grant.seconds': 'Seconds (optional)',
  'autonomy.override.grant.submit': 'Grant',
  'autonomy.override.grant.granting': 'Granting…',
  'autonomy.override.grant.granted': 'Granted. It will expire on its own.',
  'autonomy.override.grant.reasonRequired':
    'A reason is required before this can be granted.',
  'autonomy.override.revoke.title': 'Revoke an override',
  'autonomy.override.revoke.name': 'Name of the override',
  'autonomy.override.revoke.submit': 'Revoke',
  'autonomy.override.revoke.revoking': 'Revoking…',
  'autonomy.override.revoke.revoked': 'Revoked.',
  'autonomy.override.failed': 'The deployment refused this.',
  'autonomy.override.unreachable': 'The deployment could not be reached.',
  'autonomy.footer': 'Absence of a rule resolves to propose-only.',
  'autonomy.dry_run': 'Everything here is simulated: dry-run is on for this node.',
  'autonomy.bound.stopped': 'Automated writes stopped',
  'autonomy.bounds.title': 'Bounds and level overrides',
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
  'configuration.editor.title': 'Change what applies here',
  'configuration.editor.lead':
    'Every control below comes from the deployment’s own schema. Change what you need, then see what saving would resolve to — the save appears once you have.',
  'configuration.editor.submit': 'Preview this change',
  'configuration.editor.save': 'Save',
  'configuration.editor.saving': 'Saving…',
  'configuration.editor.saved': 'Saved. The values above are the new ones.',
  'configuration.editor.failed': 'The deployment refused this change.',
  'configuration.editor.unreachable': 'The deployment could not be reached.',
  'configuration.editor.previewFirst':
    'Preview this change before saving it — the diff is the only place inheritance is visible.',
  'configuration.editor.clear': 'Remove this override',
  'configuration.editor.cleared': 'Will go back to being inherited',
  'configuration.editor.redundant': 'Already inherited with this value from',
  'configuration.editor.reverts': 'Reverts to',
  'configuration.editor.notEditable':
    'A list of plain values or a free-form section: it replaces entirely on write, so it is not edited a field at a time.',
  'configuration.editor.inherited': 'nothing yet',
  'configuration.editor.addEntry': 'Add another',
  'configuration.editor.removeEntry': 'Remove',
  'configuration.editor.moveUp': 'Move earlier',
  'configuration.editor.moveDown': 'Move later',
  'configuration.editor.entryPosition': 'Evaluated',
  'configuration.editor.emptyList': 'Nothing declared here yet.',
  'configuration.editor.useSuggested': 'Use the address found here:',
  'configuration.editor.setAt': 'Set at:',
  'configuration.editor.usingDefault': 'Using the deployment default:',
  'configuration.editor.toc': 'Jump to a section',
  'configuration.editor.search': 'Find a field',
  'configuration.editor.searchEmpty': 'No field matches this search.',
  'configuration.editor.generalSection': 'General',
  'configuration.provenance.default': 'Deployment default',
  'configuration.provenance.setAt': 'Set at: {node}',
  'configuration.provenance.mixed': 'Set across more than one node',
  'configuration.empty.heading': 'No configuration here',
  'configuration.empty.body':
    'Every node inherits from the one above it. This one sets nothing of its own, so what applies is what its parent applies.',
  'configuration.empty.action': 'Look at the organisation',

  // --- The team's operating context --------------------------------------------
  'teamContext.sections.title': 'What this environment is',
  'teamContext.sections.lead':
    'Facts an operator writes once, added to the prompt of every investigation. They are added to the shipped prompt, never in place of it — the prompt overrides on the Configuration screen are the other thing, and they replace it.',
  'teamContext.factNotInstruction':
    'Write facts, not instructions. “Container metrics come from the host, by vmid” changes how an agent reads what it sees; “always restart the service first” is a procedure, and a procedure belongs in a runbook or in the autonomy policy, where it is auditable and reversible.',
  'teamContext.runbooks': 'Runbooks live in Knowledge',
  'teamContext.policy': 'Procedures live in Autonomy',
  'teamContext.column.section': 'Section',
  'teamContext.column.body': 'What it says',
  'teamContext.provenance': 'Set at',
  'teamContext.budget': 'Prompt budget',
  'teamContext.budgetUsed': '{used} of {budget} tokens',
  'teamContext.overBudget':
    'Over the budget. The deployment will refuse this until it is shorter.',
  'teamContext.disabled':
    'The operating context is switched off for this node. It is stored and nothing is sent.',
  'teamContext.addSection': 'Add a section',
  'teamContext.sectionName': 'Section name',
  'teamContext.remove': 'Clear this section',
  'teamContext.empty.heading': 'Nothing written here yet',
  'teamContext.empty.body':
    'No level of this tree has written any operating context, so every investigation starts from the shipped prompt alone. The starting document below is derived from what this deployment has already discovered.',
  'teamContext.empty.action': 'Look at the organisation',
  'teamContext.template.title': 'A starting point, from what is already known',
  'teamContext.template.lead':
    'Derived from this deployment’s own estate — the kinds it holds, the zones its addresses sit on, the source that answers each signal question. Nothing here is written until you save it.',
  'teamContext.template.use': 'Start from this',
  'teamContext.preview.title': 'What the model will be sent',
  'teamContext.preview.lead':
    'The exact text the next investigation’s system prompt will carry, assembled by the deployment. The save appears once you have asked for it.',
  'teamContext.preview.submit': 'Show me the prompt',
  'teamContext.preview.previewing': 'Assembling…',
  'teamContext.preview.first':
    'See the prompt before saving it. This text is sent on every model call of every investigation.',
  'teamContext.save': 'Save',
  'teamContext.saving': 'Saving…',
  'teamContext.saved': 'Saved. The next investigation carries this.',
  'teamContext.failed': 'The deployment refused this context.',
  'teamContext.unreachable': 'The deployment could not be reached.',
  'teamContext.roles': 'Sent to',

  // --- The capability catalogue ------------------------------------------------------------------
  'catalogue.title': 'Capabilities',
  'catalogue.tools': 'Tools',
  'catalogue.skills': 'Skills',
  'catalogue.search': 'Find a tool or skill by name or domain',
  'catalogue.search.empty': 'Nothing here matches that search.',
  'catalogue.domains.nav': 'Jump to a domain',
  'catalogue.count': '{enabled} of {total} enabled',
  'catalogue.column.name': 'Capability',
  'catalogue.column.domain': 'Domain',
  'catalogue.column.effect': 'Side effect',
  'catalogue.column.integrations': 'Needs',
  'catalogue.column.enabled': 'Enabled here',
  'catalogue.blocked': 'Requires the {integration} integration',
  'catalogue.blocked.action': 'Connect it',
  'catalogue.empty.heading': 'No capabilities declared',
  'catalogue.empty.body':
    'A capability is declared by the deployment rather than configured here. This one declares none.',
  'catalogue.empty.action': 'Look at the configuration',
  'catalogue.gaps.title': 'Not covered, and why',
  'catalogue.gaps.decided': '— weighed and decided against',
  'catalogue.gaps.unreachable': '— cannot be reached from here',
  'catalogue.gaps.resolution': 'What would change it:',
  'ingress.title': 'Where to send alerts',
  'ingress.body':
    'The one step that happens outside this deployment. Point the alert router at the address for its own kind, and it will parse the body that system already sends \u2014 nothing here is written into your monitoring stack.',
  'ingress.verification': 'Trusted by',
  'ingress.token.issue': 'Issue a delivery token',
  'ingress.token.issuing': 'Issuing\u2026',
  'ingress.token.shownOnce':
    'Copy it now. It is shown once and is never readable again \u2014 the deployment keeps only a hash of it.',
  'ingress.token.failed': 'The deployment refused to issue it.',
  'ingress.token.unreachable': 'The deployment could not be reached.',
  'firstRun.integrations.foundHere': 'Found in your estate at',
  'catalogue.integrations.title': 'Integrations',
  'catalogue.integrations.state': 'Connection',
  'catalogue.integrations.verified': 'Last verified',
  'catalogue.integrations.verify': 'Verify now',
  'catalogue.integrations.expand': 'Show the credential form',
  'catalogue.integrations.collapse': 'Hide the credential form',
  'catalogue.integrations.empty.heading': 'Nothing is connected',
  'catalogue.integrations.empty.body':
    'An integration is what lets an investigation read or change anything outside this deployment. None is installed.',
  'catalogue.integrations.empty.action': 'Look at the configuration',
  'catalogue.credential.title': 'Credentials',
  'catalogue.credential.replace': 'Replace this credential',
  'catalogue.credential.stored': 'A credential is stored. It is never shown again.',
  'catalogue.credential.absent': 'No credential is stored.',
  'catalogue.credential.state.unconfigured':
    'No credential is stored for this integration yet.',
  'catalogue.credential.state.unknown':
    'A credential is stored, but nothing has checked it yet.',
  'catalogue.credential.state.healthy': 'Verified — the last check passed.',
  'catalogue.credential.state.degraded': 'Failing — the last check found a problem.',

  // --- Administration ----------------------------------------------------------------------------
  'admin.principals.title': 'People and machines',
  'admin.column.principal': 'Principal',
  'admin.column.kind': 'Kind',
  'admin.column.active': 'Active',
  'admin.grants.title': 'Grants',
  'admin.grant.nodeHelp': 'Leave blank to grant it across the whole organisation.',
  'admin.grant.organisation': 'Whole organisation',
  'admin.grant.add': 'Grant this role',
  'admin.grant.adding': 'Granting…',
  'admin.grant.remove': 'Remove',
  'admin.grant.removing': 'Removing…',
  'admin.grant.removeAction': 'Remove this grant',
  'admin.grant.removeConsequence': 'They lose this role immediately.',
  'admin.grant.removeClose': 'Close',
  'admin.grant.removeCancel': 'Leave it granted',
  'admin.column.role': 'Role',
  'admin.column.node': 'Node',
  'admin.tokens.title': 'Machine tokens',
  'admin.tokens.name': 'What it is for',
  'admin.tokens.issue': 'Issue a token',
  'admin.tokens.issuing': 'Issuing…',
  'admin.tokens.shownOnce':
    'This is the only time this value is shown. The deployment stores a hash of it, so nothing — including this console — can read it back.',
  'admin.tokens.revoke': 'Revoke',
  'admin.tokens.revoking': 'Revoking…',
  'admin.tokens.revoked': 'Revoked',
  'admin.tokens.revokeConsequence': 'Clients using this token stop authenticating now.',
  'admin.tokens.revokeConfirm': 'Revoke it',
  'admin.tokens.revokeCancel': 'Leave it working',
  'admin.tokens.failed': 'The deployment refused this.',
  'admin.tokens.unreachable': 'The deployment could not be reached.',
  'admin.tokens.revokedGroup': '{count} revoked',
  'admin.column.token': 'Token',
  'admin.column.scopes': 'Scopes',
  'admin.column.expires': 'Expires',
  'admin.sso.title': 'Single sign-on',
  'admin.sso.provider': 'Provider',
  'admin.sso.issuer': 'Issuer',
  'admin.sso.clientId': 'Client id',
  'admin.sso.authorisation': 'Authorisation endpoint',
  'admin.sso.token': 'Token endpoint',
  'admin.sso.jwks': 'Key set',
  'admin.sso.redirect': 'Redirect back to',
  'admin.sso.defaultNode': 'Default team',
  'admin.sso.save': 'Save this configuration',
  'admin.sso.saving': 'Saving…',
  'admin.sso.test': 'Test it with a real claim set',
  'admin.sso.testing': 'Testing…',
  'admin.sso.claims': 'The claims your provider returned',
  'admin.sso.claimsHelp':
    'Paste what the provider sent back for one test user. It is run through the same reading a real sign-in takes.',
  'admin.sso.activate': 'Make this the way in',
  'admin.sso.activating': 'Activating…',
  'admin.sso.active': 'Active. People sign in through this provider.',
  'admin.sso.verified': 'Tested. It has not been made the way in yet.',
  'admin.sso.notVerified': 'Not tested. It cannot be made the way in until it is.',
  'admin.sso.testFirst':
    'Test this configuration before making it the way in. An untested provider is every operator locked out.',
  'admin.sso.pendingEdit': 'Save this change, then test it again.',
  'admin.sso.failed': 'The deployment refused this.',
  'admin.sso.unreachable': 'The deployment could not be reached.',
  'admin.sso.problems': 'This configuration cannot be used:',
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

  // --- Live: a run watched as it happens ------------------------------------------------------------
  'live.connection': 'Connection',
  'live.connection.connecting': 'Connecting',
  'live.connection.connected': 'Live',
  'live.connection.reconnecting': 'Reconnecting',
  'live.connection.idle': 'Paused in the background',
  'live.connection.disconnected': 'Not live',
  'live.stale':
    'This transcript stopped updating. What is on screen is everything that had arrived.',
  'live.reload': 'Reconnect',
  'live.new': '{count} new',
  'live.new.action': 'Go to the newest',
  'live.ended.completed': 'This investigation has finished.',
  'live.ended.failed': 'This investigation failed.',
  'live.ended.cancelled': 'This investigation was stopped.',
  'live.attention.approval': 'Approval',
  'live.attention.question': 'Question',
  'live.decided': 'Decided by {who}',
  'live.decided.elsewhere': 'somebody else',
  'live.question.title': 'The agent is waiting on an answer',
  'live.question.label': 'Your answer',
  'live.question.answer': 'Answer and continue',
  'live.question.required':
    'The investigation resumes when this is answered, so it needs one.',
  'live.takeover.title': 'Control',
  'live.takeover.take': 'Take over',
  'live.takeover.resume': 'Hand back to the agent',
  'live.takeover.cancel': 'Stop this investigation',
  'live.takeover.taken':
    'You have control. The investigation pauses at its next safe point.',
  'live.takeover.consequence':
    'It stops at its next safe point, keeps what it has found, and cannot be started again.',
  'live.takeover.keep': 'Leave it running',
  'live.takeover.close': 'Close',
  'live.context.title': 'Add context',
  'live.context.label': 'Something this investigation should know',
  'live.context.send': 'Send without stopping it',
  'live.context.sent': 'Delivered on the next turn.',
  'live.outcome.dismiss': 'Dismiss this message',
  'live.outcome.recorded': 'in this investigation’s transcript',
  'live.outcome.refused': 'The deployment refused: {reason}',
  'live.outcome.unreachable': 'The deployment could not be reached.',
  'live.investigate.title': 'Start an investigation',
  'live.investigate.objective': 'What should be looked into?',
  'live.investigate.start': 'Start it',
  'live.investigate.required': 'An objective is what the investigation is about.',
  'live.investigate.started': 'The investigation has started.',
  'live.investigate.close': 'Close',

  // --- The agent: what it is, what it can do, what it will do alone ------------
  'agent.tabs': 'What the agent is, can do, and will do alone',
  'agent.tab.topology': 'Topology',
  'agent.tab.tools': 'Tools',
  'agent.tab.autonomy': 'Autonomy',
  'agent.graph.title':
    'The investigation, from the orchestrator down to the specialists',
  'agent.rank.orchestrator': 'Orchestrator',
  'agent.rank.stages': 'Stages',
  'agent.rank.specialists': 'Specialists',
  'agent.stages.title': 'The stages an investigation runs',
  'agent.stage.role': 'model role: {role}',
  'agent.stage.noModel': 'no model call',
  'agent.stage.consults': 'Consults:',
  'agent.specialists.title': 'The specialists this team declares',
  'agent.specialists.edit':
    'Which specialists exist is configuration, edited a field at a time.',
  'agent.specialists.editLink': 'Edit the agents section',
  'agent.specialists.empty.heading': 'This team declares no specialists',
  'agent.specialists.empty.body':
    'The investigation still runs; it does the gathering itself instead of dispatching anybody. Declare a specialist to split the work.',
  'agent.specialists.empty.action': 'Edit the configuration',
  'agent.models.title': 'What each role runs on',
  'agent.models.body':
    'A stage names a role, never a model. What a role resolves to is configuration, and every row here says which node supplied it.',
  'agent.models.default': 'deployment default — nobody bound this role',
  'agent.models.from': 'from {node}',
  'agent.models.empty.heading': 'No role is described here',
  'agent.models.empty.body':
    'The deployment could not say which roles it resolves. Every role still runs on the deployment default.',
  'agent.models.empty.action': 'Edit the configuration',
  'agent.budgets.title': 'What one investigation may spend',
  'agent.budgets.body':
    'A team may lower any of these and may not raise one past its ceiling. The ceiling is a constant in the deployment, not a setting.',
  'agent.budgets.ceiling': 'ceiling {ceiling}',
  'agent.budgets.empty.heading': 'No budget is described here',
  'agent.budgets.empty.body':
    'The deployment did not describe the budget fields for this node, so the ceilings cannot be shown.',
  'agent.budgets.empty.action': 'Edit the configuration',
  'agent.document.title': 'The same topology, as the document',
  'agent.empty.heading': 'The pipeline could not be described',
  'agent.empty.body':
    'The deployment did not answer with the stages an investigation runs. Nothing here is configuration; it is what the build is.',
  'agent.empty.action': 'Edit the configuration',
  'agent.tools.reads': 'Tools that read',
  'agent.tools.reads.body': 'These consult something and change nothing.',
  'agent.tools.writes': 'Tools that write',
  'agent.tools.writes.body':
    'These change something. Every one of them passes the autonomy policy before it runs.',
  'agent.tools.origin': 'from the {server} server',
  'agent.tools.blocked': 'not available here: {integration} is not configured',
  'agent.tools.unknown':
    'this deployment has no organisation tree yet, so nothing was resolved',
  'agent.tools.empty.heading': 'Nothing in this group',
  'agent.tools.empty.body':
    'No capability of this build falls in this group, or the deployment could not be asked.',
  'agent.tools.empty.action': 'Edit the configuration',
  'agent.bridged.title': 'Servers outside this deployment',
  'agent.bridged.body':
    'A tool from one of these came from somewhere the operator does not run. Its tools are enumerated when the deployment reaches the server, and one nobody classified cannot execute.',
  'agent.bridged.empty.heading': 'No outside server is registered',
  'agent.bridged.empty.body':
    'Every tool this team can run is one this build ships. Register a bridged server to add tools from elsewhere.',
  'agent.bridged.empty.action': 'Edit the configuration',
  'agent.outlook.title': 'What would happen, by class of action',
  'agent.outlook.body':
    'One sentence per class, answered by the deployment itself under the policy as it stands right now.',
  'agent.outlook.bound': 'stopped by the {bound}',
  'agent.outlook.dryRun':
    'Everything here is simulated: dry-run is on for this node, so nothing is performed.',
  'agent.outlook.edit': 'Change what this deployment may do on its own',
  'agent.outlook.empty.heading': 'The posture could not be read',
  'agent.outlook.empty.body':
    'This node carries no autonomy policy yet, so nothing has been decided about what may happen without a person. Absence resolves to propose-only.',
  'agent.outlook.empty.action': 'Set the posture',
  'agent.replay.title': 'And what it did decide, on what actually happened',
  'agent.replay.body':
    'The deployment replayed its own record of recent actions against the posture as it stands. This is beside the classes above, not instead of them: a deployment on its first day has no record, and that is the day somebody decides whether to trust it.',
  'agent.replay.empty.heading': 'Nothing has been recorded yet',
  'agent.replay.empty.body':
    'No action has reached the policy engine in this window, so there is nothing to replay. The classes above still say what would happen.',

  'live.investigate.caveat':
    'Quality depends on what is connected. With no integration configured the agent reasons and consults nothing.',
  // --- Changes the agent has proposed ------------------------------------------
  'proposals.title': 'Changes the agent has proposed',
  'proposals.empty.heading': 'The agent has proposed nothing',
  'proposals.empty.body':
    'Proposals arrive from investigations and from the documented checks in your corpus. Nothing here is applied until you approve it.',
  'proposals.empty.action': 'See what is running',
  'proposals.otherInbox': 'For actions the agent wants to take now:',
  'proposals.acceptance': '{approved} of {decided} decided proposals accepted',
  'proposals.acceptance.none': 'Nothing has been decided yet',
  'proposals.type.knowledge': 'Knowledge',
  'proposals.type.operating_context': 'Operating context',
  'proposals.type.detector': 'Detector',
  'proposals.type.configuration': 'Configuration',
  'proposals.field.type': 'Kind',
  'proposals.field.rationale': 'Why',
  'proposals.field.evidence': 'Evidence',
  'proposals.field.origin': 'From the investigation',
  'proposals.field.node': 'Where it lands',
  'proposals.field.effect': 'What would change',
  'proposals.openRun': 'Open the investigation',
  'proposals.effect.show': 'Show what this would do',
  'proposals.effect.loading': 'Asking the deployment',
  'proposals.effect.failed': 'The deployment did not answer. Nothing was changed.',
  'proposals.effect.text': 'The text as it would be written',
  'proposals.effect.preview': 'The configuration this would resolve to',
  'proposals.effect.dryRun': 'What this detector would have found',
  'proposals.effect.dryRun.quiet': 'It would have found nothing in the stored history.',
  'proposals.approveFirst':
    'Approving is available once you have seen what this would do.',
  'proposals.approve': 'Approve and apply',
  'proposals.reject': 'Reject',
  'proposals.reason': 'Why it is being rejected',
  'proposals.reason.required': 'A reason is required to reject.',
  'proposals.prior.heading': 'Refused before',
  'proposals.prior.entry': '{who} on {when}: {reason}',
  'attention.proposal': 'Proposed change',
} as const;

/** Every key the console may render. Derived, so a typo is a type error. */
export type MessageKey = keyof typeof EN;
