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
  'nav.group.settings': 'Configuration',
  'nav.firstRun': 'Setup',
  'nav.dashboard': 'Dashboard',
  'nav.incidents': 'Incidents',
  'nav.runs': 'Investigations',
  'nav.decisions': 'Decisions',
  // Kept for the areas the reorganisation folded into a tab of something
  // else: the sentence a cross-link renders still needs a name for the
  // screen it points at, even once that screen no longer has a menu entry
  // of its own.
  'nav.approvals': 'Actions awaiting approval',
  'nav.proposals': 'Proposed changes',
  'nav.resources': 'Resources',
  'nav.topology': 'Topology',
  'nav.detectors': 'Detectors',
  'nav.memory': 'Memory',
  'nav.knowledge': 'Knowledge',
  'nav.integrations': 'Integrations',
  'nav.integrationsNotCovered': 'Not covered, and why',
  'nav.signals': 'Signals',
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
  // The same four levels, in the short form a subtitle or a heading states
  // beside a node's own name — never the sentence above, which carries its
  // own full stop and reads as a fragment once another clause follows it.
  'autonomy.level.propose_only.short': 'Propose only',
  'autonomy.level.act_on_low_risk.short': 'Act on low risk',
  'autonomy.level.act_and_report.short': 'Act and report',
  'autonomy.level.act_silently.short': 'Act silently',
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
  // The sum of the two tabs it replaced — a decision waiting is a decision
  // waiting, whichever tab it would open to.
  'nav.pending.decisions': '{count} decisions waiting',
  'nav.pending.approvals': '{count} actions awaiting approval',
  'nav.pending.proposals': '{count} proposals waiting',
  'nav.pending.incidents': '{count} open incidents',
  'nav.pending.runs': '{count} failed investigations',

  // --- What each area is for ---------------------------------------------------
  'page.firstRun.title': 'Setup',
  'page.firstRun.context':
    'What to set up, in order, with the reason for each and the option to stop after any of them.',
  'page.dashboard.title': 'Overview',
  'page.dashboard.context':
    'What needs a person, what is running, and how the estate is.',
  'page.incidents.title': 'Incidents',
  'page.incidents.context': 'What a detector opened, and what happened to it since.',
  'page.runs.title': 'Investigations',
  'page.runs.context':
    'Every investigation this deployment has recorded, newest first. Open one where it sits.',
  'page.decisions.title': 'Decisions',
  'page.decisions.context':
    'What the agent wants to do now, and what it wants the deployment to become.',
  'page.integrations.title': 'Integrations',
  'page.integrations.context':
    'Every integration this deployment can hold a credential for, its state, and a way to test it.',
  'page.integrationsNotCovered.title': 'Not covered, and why',
  'page.integrationsNotCovered.context':
    'Every vendor this catalogue does not reach, and why — cannot be reached, or was evaluated and decided against.',
  'page.signals.title': 'Signals',
  'page.signals.context':
    'What enters continuous observation, and where an alert ends up once it has.',
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

  // --- Tabs on a screen a fusion built ------------------------------------------
  // One catalogue entry per tab, on the fused screens rather than scattered
  // beside each donor screen's own block, because a tab label is about the
  // fusion and not about the content underneath it.
  'decisions.tabs': 'What needs a decision',
  'decisions.tab.actions': 'Actions',
  // Short, like every other tab label in this console — the panel beneath
  // it already carries the full "Proposed changes" name, and repeating the
  // same two words in the other order here would read as a typo of it
  // rather than as a deliberate abbreviation.
  'decisions.tab.changes': 'Changes',
  'knowledge.tabs': 'What the agent knows about this environment',
  'knowledge.tab.learned': 'Learned',
  'knowledge.tab.documents': 'Documents',
  'knowledge.tab.topology': 'Topology',
  'signals.tabs': 'What enters observation and what leaves it',
  'signals.tab.intake': 'Intake',
  'signals.tab.observation': 'Continuous observation',
  'signals.tab.schedules': 'Schedules',
  'signals.tab.destinations': 'Destinations',
  'admin.tabs': 'Who may do what, and who did',
  'admin.tab.people': 'People',
  'admin.tab.audit': 'Audit',
  'agent.tab.team': 'Team context',

  // --- Where data comes from and where it goes ---------------------------------
  'data.ingress.title': 'What arrives',
  // The two chip words a receiver's own state resolves to \u2014 never a third,
  // and never translated to a synonym of either.
  'data.ingress.receiving': 'Receiving',
  'data.ingress.ready': 'Ready \u2014 nothing arrived yet',
  'data.ingress.last': 'Last delivery',
  // A wider, coarser span than `last`: how much has arrived recently, not
  // only whether anything just did.
  'data.ingress.week': '{count} this week',
  'data.ingress.copyUrl': 'Copy URL',
  'data.ingress.receiverYaml': 'Copy Alertmanager receiver YAML',
  'data.ingress.sample': 'Last payload, masked',
  'data.ingress.empty.heading': 'No receiver is configured',
  'data.ingress.empty.body':
    'Point an alert router at one of this deployment\u2019s webhook addresses and its deliveries appear here.',
  'data.ingress.empty.action': 'Open the catalogue',
  // The receiver's own collapsed detail (Reference): what stays out of the
  // compact row until it is asked for.
  'data.ingress.detail.title': 'Format & test',
  'data.ingress.detail.summary':
    'Expected format, trust mechanism, and a delivery test.',
  'data.ingress.detail.format': 'Expects:',
  // The intake sources the environment-validated scope could not carry \u2014
  // said on the screen the gap is felt on, not only in the catalogue. The
  // vendors are not named here: a surface that lists them is a surface still
  // offering them, and the roadmap is where that list belongs.
  'data.ingress.retired':
    'Four other intake sources moved to the roadmap \u2014 they return with an environment that can validate them.',
  'data.rules.title': 'What happens to it',
  'data.rules.action': 'Action:',
  'data.rules.catchAll': 'Everything no rule above matched ends here.',
  'data.rules.empty.heading': 'No rule is configured',
  'data.rules.empty.body':
    'Every verified delivery is investigated by the team that verified it.',
  'data.rules.empty.action': 'Open configuration',
  'data.chain.label': 'What happens to an alert here',
  'data.chain.intake.empty': 'No source has delivered yet',
  'data.chain.rule.empty': 'No rule is configured yet',
  'data.chain.action.empty': 'No action runs yet',
  'data.chain.destination.empty': 'No destination is configured yet',
  'data.simulate.title': 'Test a delivery',
  'data.simulate.purpose':
    'See which rule would catch a payload and which team it would reach, before anything is saved.',
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
  'settings.schedulesDestinations.advanced.transit.title':
    'Routing rules and delivery destinations',
  // No noun in this title may repeat one from `advanced.transit.title` above
  // — the chain on Alert intake promises "destination" and has to land on
  // the one section that owns it, unambiguously.
  'settings.schedulesDestinations.advanced.surfaces.title':
    'Chat channels, report recipients and notification sinks',
  'settings.schedulesDestinations.advanced.field.transitRules': 'Routing rules',
  'settings.schedulesDestinations.advanced.field.transitDestinations':
    'Delivery destinations',
  'settings.schedulesDestinations.advanced.field.channels': 'Chat channels',
  'settings.schedulesDestinations.advanced.field.reportDestinations':
    'Report destinations',
  'settings.schedulesDestinations.advanced.field.notificationSinks':
    'Notification sinks',
  'data.delivery.masking': 'Masking policy:',
  'data.delivery.resend': 'Send again',
  'data.delivery.resending': 'Sending\u2026',
  'data.delivery.resent': 'Delivered',
  'data.delivery.resendFailed': 'It did not arrive this time either.',
  'data.delivery.empty.heading': 'No destination is declared',
  'data.delivery.empty.body': 'Nothing is told when an investigation concludes.',
  'data.delivery.empty.action': 'Open configuration',
  // The CTA contract applied to the one case the empty state names a more
  // specific reason than "declare a destination": nothing configured can
  // carry a message at all, so the action lands in the catalogue, filtered
  // to the category that fixes it — never on the schema editor the sentence
  // does not mention.
  'data.delivery.unconfigurable.action': 'Connect an integration',
  // Beside a degraded destination's own reason, linking to the credential
  // that would resolve it.
  'data.delivery.unusable.link': 'Check the credential',
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
  'noAdministrator.title': 'This deployment has no administrator yet',
  'noAdministrator.body': 'Run the command below on the host to create one.',
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
  'pagination.landmark': 'Pagination',

  // --- The credential and verification vocabulary --------------------------------
  // The one word `StatusChip` renders for each of the five states declared in
  // `design/status.ts`, whatever backend spelling — a resource's health, an
  // integration's health, a checklist's readiness — it was translated from.
  'status.credential.notConnected': 'Not connected',
  'status.credential.stored': 'Stored',
  'status.credential.verified': 'Verified',
  'status.credential.degraded': 'Degraded',
  'status.credential.failing': 'Failing',
  'status.credential.unknown': 'Unknown',
  'status.resource.healthy': 'healthy',
  'status.resource.degraded': 'degraded',
  'status.resource.unhealthy': 'unhealthy',
  'status.resource.unknown': 'unknown',
  'status.resource.stale': 'stale',
  'status.resource.maintenance': 'in maintenance',
  'status.resource.absent': 'absent',
  'status.credential.unknown.explain':
    "This deployment's gateway could not be reached, so the real state could not be read.",

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
  'transcript.note': 'Why these capabilities were offered',
  'transcript.duration': '{ms} ms',
  'transcript.events': '{count} events',
  'transcript.events.one': '{count} event',
  // The board's own second half of this caption (`RunView.dc.html`:
  // "31 eventos · o mais novo primeiro") — its own key, not folded into
  // `transcript.events` above, because that key is shared with the audit
  // log's own count (`settings/audit.tsx`), which is not ordered this way.
  'transcript.newestFirst': 'newest first',
  'transcript.empty.heading': 'No transcript yet',
  'transcript.empty.body':
    'A transcript appears as soon as the investigation takes its first turn. Nothing has been recorded for this one.',
  'transcript.empty.action': 'Back to the investigations',

  // The toggle between the narrated sentence (the default) and the raw
  // payload every event actually carries. Two words, read by the toggle
  // itself and by nothing else.
  'transcript.view.narrated': 'Narrated',
  'transcript.view.raw': 'Raw',
  'transcript.view.payload': 'Raw payload',

  // One lead sentence per raw kind the stream vocabulary declares
  // (`STREAM_KINDS`, `transcript.ts`). `{name}` is only ever filled with a
  // real capability or sub-agent name — never left as a literal placeholder —
  // and the event's own `detail` is appended after the lead by `narrate`,
  // never folded into the template itself.
  'transcript.narration.runStarted': 'Objective accepted',
  'transcript.narration.turnStarted': 'A new turn began',
  'transcript.narration.modelReasoned': 'The model reasoned',
  'transcript.narration.toolCalled': 'Called {name}',
  'transcript.narration.toolSucceeded': '{name} returned',
  'transcript.narration.toolFailed': '{name} failed',
  'transcript.narration.observationRecorded': 'An observation was recorded',
  'transcript.narration.evidenceRetained': 'Evidence was retained',
  'transcript.narration.memoryRecalled': 'A memory was recalled',
  'transcript.narration.subagentDispatched': 'Dispatched {name}',
  'transcript.narration.subagentReturned': '{name} returned',
  'transcript.narration.guardrailWithheld': 'A guardrail withheld an action',
  'transcript.narration.guardrailApplied': 'A guardrail was applied',
  'transcript.narration.interactionOpened': 'The investigation is waiting on a person',
  'transcript.narration.interactionAnswered': 'The open question was answered',
  'transcript.narration.runCompleted': 'The investigation completed',
  'transcript.narration.runFailed': 'The investigation failed',
  // The floor every event has: a kind this build has never met still names
  // itself, in a sentence, rather than falling back to a raw payload block.
  'transcript.narration.unknown': 'An event of an unrecognised kind arrived: {kind}',
  'transcript.narration.unnamedCapability': 'a capability',
  'transcript.narration.unnamedSubagent': 'a sub-agent',

  // --- The run's pipeline rail -----------------------------------------------------
  'run.stage.rail.title': 'Pipeline',
  'run.stage.future': 'Stage {number}',
  'run.usage.awaiting': 'The first turn has not arrived yet.',
  'run.links.watching': 'Watching for resources this investigation touches.',
  'run.findings.title': 'Findings so far',
  'run.findings.none': 'No stage has finished with a finding yet.',

  // --- The overview --------------------------------------------------------------
  // --- The Painel: "Em execução agora" ------------------------------------------
  'dashboard.runBand.title': 'Running now',
  'dashboard.runBand.flight': 'in flight',
  'dashboard.runBand.followed': 'followed',
  'dashboard.runBand.blocked': 'blocked on you',
  'dashboard.runBand.more': 'all investigations →',
  'dashboard.runBand.empty': 'Nothing is running right now — every investigation has finished or none has started.',
  'dashboard.runBand.empty.action': 'Start one →',

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
  'dashboard.stat.timeToCause': 'Time to a cause',
  'dashboard.stat.timeToCause.context': 'median of {settled} · slowest {slowest}',
  'dashboard.stat.timeToCause.context.none': 'No investigation has finished yet.',
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
  'credential.minScope': 'Minimum permission:',
  'credential.guide': 'Step-by-step guide',

  // --- The guided first run -----------------------------------------------------------
  // Where the operator is, by position and by name, with what is left on the
  // same line — one denominator, the same seven-screen sequencing the steps
  // panel and the dashboard's own card both read their own numbers from.
  'firstRun.wizard.position': 'Step {n} of {total} — {name}',
  'firstRun.wizard.pending.one': '{count} step left',
  'firstRun.wizard.pending': '{count} steps left',
  'firstRun.steps.title': 'What is left',
  'firstRun.steps.done': 'Every step is done',
  // The dashboard's own hero says "{count} of {total} steps left" for this
  // same fact, from the same source.
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
  'firstRun.credential.checking': 'Asking the provider whether this key works…',
  'firstRun.credential.accepted':
    'The provider accepted this key and listed the models below.',
  'firstRun.credential.notListed':
    'The key is stored, but the provider would not list what it serves:',
  'firstRun.credential.chooseModel': 'Which of these this deployment thinks with:',

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
  // What the preview names each field by — never the dotted configuration
  // path (`models.investigator.model`) the request actually sends.
  'firstRun.model.field.provider': 'Provider',
  'firstRun.model.field.model': 'Investigation model',

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
  'firstRun.verify.nothing':
    'Nothing is configured yet, so there is nothing to check. Store a provider credential first.',
  'firstRun.verify.remedy': 'What to do:',
  'firstRun.verify.findings': 'What it found that cannot be relied on:',
  // Which field a failure sends somebody to. The provider one is the mockup's
  // own worked example — a real model that answered without calling a tool —
  // and the correction is another model of the same provider's, not a
  // different provider necessarily.
  'firstRun.verify.fix.provider': 'Choose another model',
  'firstRun.verify.fix.integration': 'Review the credential',
  'firstRun.verify.fullDiagnosis': 'Full diagnosis',
  'firstRun.verify.fullDiagnosis.summary':
    'The rest of what the deployment reported about this check.',
  // "{count} of {total}" rather than a bare count, matching the progress
  // line above it: a number with nothing to compare it against reads as more
  // definite than it is.
  'firstRun.verify.pending': '{count} of {total} not yet verified',
  'firstRun.verify.continueAnyway': 'Continue anyway',
  'firstRun.verify.latency': 'answered in {ms} ms',
  'firstRun.verify.footer.noneDegraded': 'none degraded',
  'firstRun.verify.footer.degraded': '{count} check(s) degraded',
  'firstRun.verify.footer.noneFailing': 'none failing',
  'firstRun.verify.footer.failing': '{name} is failing',
  'firstRun.verify.continue': 'Continue',
  'firstRun.verify.blockedBy': 'Held back by:',

  'firstRun.established.title': 'What is set up so far',
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

  // The banner a step that hands over shows, while the wizard sent it there
  // has anything still to finish.
  'firstRun.return.body': 'The guided setup sent you here to finish this step.',
  'firstRun.return.cta': 'Continue setup',

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
  'runs.live.title': 'Live now',
  'runs.live.count.one': '{count} in flight',
  'runs.live.count': '{count} in flight',
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
  'run.usage.unpriced': 'No published price for this model',
  'run.usage.unpriced.short': 'unpriced',
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

  // --- One investigation, opened where it sits -------------------------------------
  //
  // The list opens a run in place rather than navigating to it, so these
  // strings are read on the list screen and on the run's own page alike.
  'runs.row.open': 'Open this investigation',
  'runs.row.opening': 'Opening this investigation…',
  'runs.row.close': 'Close this investigation',
  'runs.row.openPage': 'Open on its own page',
  'run.evidence.backed': '{backed} of {claims} claims backed',
  'run.evidence.unassessed': 'no claim to back',
  'run.evidence.unassessed.explain':
    'This investigation never assessed its own evidence, which is not the same as having found nothing.',
  'run.evidence.missing.explain':
    'The investigation named {missing} thing(s) it still could not read.',
  'run.measure.duration': 'Time to a cause',
  'run.measure.calls': 'Capabilities called',
  'run.measure.trigger': 'Triggered by',
  'run.measure.tokens': 'Tokens',
  'run.measure.unpriced': 'This model publishes no price.',
  'run.section.happened': 'What happened',
  'run.section.reaches': 'What it reaches',
  'run.section.order': 'In order',
  'run.section.why': 'Why',
  'run.section.todo': 'What to do',
  'run.section.did': 'What it did',
  'run.section.remembered': 'Worth remembering',
  'run.happened.none': 'This investigation wrote no report beyond the line above.',
  'run.reaches.none': 'This investigation is not filed under an incident.',
  'run.remembered.written': 'written to the corpus',
  'run.remembered.none': 'This investigation wrote nothing to the corpus.',
  'run.remembered.unknown':
    'This console could not read {dependency}, so whether this investigation wrote anything to the corpus is not known.',
  'run.why.supporting': 'What backs it',
  'run.why.missing': 'What nobody could read',
  'run.why.none': 'This investigation never assessed its own evidence.',
  'run.todo.none': 'Nothing from this investigation is waiting on a person.',
  'run.did.summary': '{events} events across {turns} turns',
  // What the section counts once the trace records stages. Turns are still
  // counted for a run whose trace holds none, because that run genuinely has
  // nothing but turns and saying "0 stages" about it would be a fact about
  // this console rather than about the investigation.
  'run.did.stages': '{events} events across {stages} stages',
  'run.did.calls': '{calls} calls',
  'run.did.more': 'Show {count} more calls',
  'run.did.noRationale': 'This turn recorded no reasoning.',
  'run.did.wroteReport': 'This turn wrote the report above.',
  // The six stages, named as an operator reads them rather than as the trace
  // spells them. `gather_evidence` is a field name; "Gather evidence" is what
  // the stage is called on the screen that has always described the six.
  'run.stage.resolve_integrations': 'Resolve integrations',
  'run.stage.intake': 'Intake',
  'run.stage.plan_evidence': 'Plan evidence',
  'run.stage.gather_evidence': 'Gather evidence',
  'run.stage.diagnose': 'Diagnose',
  'run.stage.deliver': 'Deliver',
  // What a stage that produced no loop turn shows instead. Not a stand-in for
  // a turn: intake and diagnosis each make one model call and hand back a
  // value, and this is that call counted. A stage with neither turns nor model
  // calls made none, which is also true and also worth being able to see.
  'run.stage.modelCalls': '{calls} model calls',
  'run.stage.noFinding': 'This stage recorded no finding.',
  'run.report.copy': 'Copy as Markdown',
  'run.report.copied': 'Copied',
  'run.report.copyRefused': 'The browser refused the clipboard',

  // --- Incidents -------------------------------------------------------------------
  'incidents.column.severity': 'Severity',
  'incidents.column.title': 'Incident',
  'incidents.column.state': 'State',
  'incidents.column.detector': 'Detector',
  'incidents.column.opened': 'Opened',
  'incidents.column.subjects': 'Subjects',
  'incidents.filter.state': 'State',
  'incidents.filter.severity': 'Severity',
  'dashboard.band.active': 'Guardian active',
  'dashboard.band.silent': 'Guardian silent',
  'dashboard.band.meta':
    '{posture} · {live} of {total} detectors live · {watched} resources watched',
  'dashboard.band.meta.noDetectors':
    '{posture} · no detector configured · {watched} resources watched',
  'dashboard.stat.degraded.context.noDetectors':
    '{count} open findings behind them, and no detector is switched on to raise one into an incident',
  'dashboard.band.flight': 'Runs in flight',
  'dashboard.band.blocked': 'Blocked on you',
  'dashboard.band.detectors': 'Detectors live',
  'dashboard.band.held': 'Incidents held',
  'dashboard.band.idle': 'Nothing is being investigated right now.',
  'dashboard.band.silent.body':
    'The guardian is not reporting ready, so nothing is being watched and nothing will be raised. Everything below is the last thing this deployment knew.',
  'dashboard.band.started': 'started {since}',
  'dashboard.stat.unattended': 'Handled without a person',
  'dashboard.stat.unattended.context':
    '{closed} of {total} incidents closed themselves',
  'dashboard.stat.unattended.context.none': 'nothing has closed yet',
  'dashboard.attention.more': 'and {count} more waiting',
  'dashboard.recurring.title': 'What keeps happening',
  'dashboard.recurring.note': 'Grouped by subject, not by firing',
  'dashboard.recurring.empty.heading': 'Nothing has recurred',
  'dashboard.recurring.empty.body':
    'A condition that fires more than once on the same subject is collected here, so a problem that keeps coming back is one row rather than a page of them.',
  'dashboard.recurring.empty.action': 'See every incident',
  'dashboard.held.title': 'The agent is on it',
  'incidents.filter.view': 'View',
  'incidents.view.grouped': 'By subject',
  'incidents.view.flat': 'Every firing',
  'incidents.group.count': '{count} firings',
  'incidents.group.wasSeverity': 'was {severity}',
  'incidents.group.count.one': 'Fired once',
  'incidents.group.since': 'recurring since {since}',
  'incidents.group.expand': 'Show every firing of {title}',
  'incidents.group.summary': '{subjects} subjects · {firings} firings',
  'incidents.filter.state.investigating': 'Investigating',
  'incidents.filter.state.resolved': 'Resolved',
  'incidents.filter.severity.critical': 'Critical',
  'incidents.header.summary':
    '{subjects} subjects · {firings} firings · {critical} critical in progress',
  'incidents.timeline.title': 'Firings in the last 24h',
  'incidents.timeline.now': 'now',
  'incidents.timeline.overflow': 'and {count} more before yesterday',
  'incidents.cause.live': 'investigation in progress →',
  'incidents.cause.found': 'Last cause found:',
  'incidents.coverage.gap': '{count} degraded findings have no detector watching them',
  'incidents.coverage.action': 'Turn on a detector →',
  'incidents.list.title': 'Incidents',
  'incidents.list.caption': 'Open and recently closed incidents',
  // --- Why this deployment is empty, as opposed to what the feature is for ----
  // Shared by every screen downstream of the setup: incidents, approvals, the
  // graph, the episodes, the documents. See `surfaces/emptiness.ts` — the point
  // is that "nothing is wrong" and "nothing is watching" must stop rendering
  // identically, because they are opposite situations.
  'empty.cause.setup':
    'Nothing has happened here yet because this deployment is still being set up — the next step is "{step}".',
  'empty.cause.setup.action': 'Finish setting up',
  'empty.cause.watching':
    'No detector is switched on, so nothing is being watched and nothing will open by itself.',
  'empty.cause.watching.action': 'Turn on continuous observation',
  // Deliberately two facts and no diagnosis: the console can count finished
  // investigations and read the corpus, and it cannot read why extraction
  // failed — no endpoint serves that. See `surfaces/emptiness.ts`.
  'empty.cause.extraction':
    '{finished} investigations have finished and none of them left an episode behind. What turns a finished investigation into an episode is a model call, and each role picks its own model.',
  'empty.cause.extraction.action': 'Check the model each role uses',

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

  // --- The incident page (M6): header chips, subtitle, investigation, ---------
  // --- proposed action and the evidence trail ----------------------------------
  // The incident's own state, and the two words a chip carries for it. Kept
  // separate from `Badge`'s raw-status vocabulary, because this chip is read
  // in the viewer's language rather than in the wire's.
  'incident.chip.state.open': 'Open',
  'incident.chip.state.investigating': 'Investigating',
  'incident.chip.state.awaitingHuman': 'Awaiting a person',
  'incident.chip.state.remediating': 'Remediating',
  'incident.chip.state.resolved': 'Resolved',
  'incident.chip.state.suppressed': 'Suppressed',
  'incident.chip.state.closedWithoutAction': 'Closed without action',
  // Distinct from every named state above: this incident's own detail failed
  // to load, so its state was never learned — never the same chip as `.open`,
  // which is a claim about the incident rather than an admission the read
  // never answered.
  'incident.chip.state.unknown': 'Unknown',
  'incident.chip.state.unknown.explain':
    'This incident could not be read, so its state could not be told.',
  // Whether an investigation has run against this incident at all, and
  // whether it has delivered its report — read from the timeline itself
  // rather than from a run status this route does not carry.
  'incident.chip.investigation.none': 'No investigation',
  'incident.chip.investigation.running': 'Investigation running',
  'incident.chip.investigation.finished': 'Investigation finished',
  // Distinct from `.none`: this incident's own detail failed to load, so
  // whether an investigation exists at all was never learned — "no
  // investigation" and "could not tell" call for opposite next steps.
  'incident.chip.investigation.unknown': 'Unknown',
  'incident.chip.investigation.unknown.explain':
    'This incident could not be read, so whether it has an investigation could not be told either.',
  'incident.chip.investigation.unseen.explain':
    'This incident names a run, and nothing has recorded a trace for it yet, so where the investigation got to is not known here.',
  'incident.header.unreadable': 'This incident could not be read',

  'incident.origin.alert': 'Alertmanager',
  'incident.origin.detector': "this deployment's own detectors",
  'incident.origin.human': 'a person',
  'incident.subtitle.started': 'started {when}',
  'incident.subtitle.zone': 'zone {zone}',

  'incident.investigation.title': 'Investigation',
  'incident.investigation.steps.one': '{count} step',
  'incident.investigation.steps.other': '{count} steps',
  'incident.investigation.empty.heading': 'No investigation has run',
  'incident.investigation.empty.body':
    'This incident has no investigation attached yet. The runtime step in setup names what is pending before one can start.',
  'incident.investigation.empty.action': 'Check the runtime step',
  'incident.investigation.step.receipt': 'Alert received',
  'incident.investigation.step.hypotheses': 'Hypotheses drawn',
  'incident.investigation.step.evidence': 'Evidence',
  'incident.investigation.step.diagnosis': 'Diagnosis',
  'incident.investigation.step.delivery': 'Report delivered',

  'incident.evidenceTrail.title': 'Evidence trail',
  'incident.evidenceTrail.body':
    'Every query, answer and token spent, in order. Nothing here is prose without a source.',
  'incident.evidenceTrail.link': 'Open the full run',
  'incident.evidenceTrail.empty.heading': 'No run to trace yet',
  'incident.evidenceTrail.empty.body':
    'This incident has no investigation run attached, so there is no evidence trail to open.',
  'incident.evidenceTrail.empty.action': 'Check the runtime step',

  'incident.proposedAction.title': 'Proposed action',
  'incident.proposedAction.state.pending': 'Awaiting decision',
  'incident.proposedAction.state.approved': 'Approved',
  'incident.proposedAction.state.rejected': 'Rejected',
  'incident.proposedAction.state.expired': 'Expired',
  'incident.proposedAction.posture': 'Posture is {posture} — nothing runs without you.',
  'incident.proposedAction.approve': 'Approve and run',
  'incident.proposedAction.reject': 'Reject',
  'incident.proposedAction.reason': 'Reason',
  'incident.proposedAction.reasonRequired': 'A reason is required to reject.',
  'incident.proposedAction.decisionFailed': 'The decision was not recorded. Try again.',
  'incident.proposedAction.radius.resources.one': '{count} resource',
  'incident.proposedAction.radius.resources.other': '{count} resources',
  'incident.proposedAction.radius.zone': 'zone {zone}',
  'incident.proposedAction.radius.criticality': 'criticality {criticality}',
  'incident.proposedAction.empty.heading': 'Nothing proposed yet',
  'incident.proposedAction.empty.body':
    'No investigation has concluded with a remediation to decide on for this incident.',
  'incident.proposedAction.empty.action': 'See the investigation',

  // --- Approvals ---------------------------------------------------------------------
  'approvals.title': 'Actions awaiting approval',
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
  'approvals.expired.note':
    'The window for answering this closed, and the deployment refuses a decision taken after it. What it was proposed against was read before then and nobody has looked since, so ask for it again to decide on a current reading.',
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
  // What the proposed action's own worst-case side effect means, for the
  // Autonomy row above — the same slugs `config/constants/security.py`
  // declares, ordered least to most dangerous, in words rather than as the
  // bare deployment spelling.
  'sideEffect.chip.read': 'Reads',
  'sideEffect.chip.read_sensitive': 'Reads, sensitive',
  'sideEffect.chip.write_reversible': 'Writes, reversible',
  'sideEffect.chip.write_irreversible': 'Writes, irreversible',
  'sideEffect.chip.destructive': 'Destructive',
  'sideEffect.level.read': 'Read — nothing on the estate changes.',
  'sideEffect.level.read_sensitive':
    'Sensitive read — nothing changes, but what comes back should be handled carefully.',
  'sideEffect.level.write_reversible':
    'Reversible write — this changes the estate, and the change can be undone.',
  'sideEffect.level.write_irreversible':
    'Irreversible write — this changes the estate in a way that cannot be undone.',
  'sideEffect.level.destructive':
    'Destructive — this removes something from the estate, with nothing left to roll back.',

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
  'resources.none.placedOrGraded':
    'Nothing in this estate has been placed in a zone or graded for criticality yet.',
  'resources.none.placed': 'Nothing in this estate has been placed in a zone yet.',
  'resources.none.graded':
    'Nothing in this estate has been graded for criticality yet.',
  'resources.none.action': 'Declare them',
  'resources.summary.watched': 'watched',
  'resources.summary.unaccounted': 'unaccounted for',
  'resources.summary.watched.count': '{count} watched',
  'resources.summary.legend': '{count} {health}',
  'resources.card.lastSeen': 'seen {when}',
  'resources.card.unhealthySince': '{since} out',
  'resources.filter.kind.any': 'All',
  'resources.node.none': 'No node declared',
  'resources.node.count': '{count} resources on this node',
  'resources.node.unhealthyCount': '{count} unhealthy',
  'resources.node.seeUnhealthy': 'See the {count} unhealthy of {node} →',
  'resources.node.seeAll': 'See all {count} resources of {node} →',
  'resources.synthesis.line':
    '{count} {kind} unhealthy since {since} — all on {node}, same start window',
  'resources.synthesis.action': 'investigate as a batch →',
  'resources.synthesis.objective':
    'What took down {count} {kind} on {node} since {since}?',
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
  'resources.undeclared.title': 'Not in the inventory',
  'resources.undeclared.body':
    'The source reports these and the declared inventory does not name them. Add them to the inventory, or ignore them if they should not be tracked.',
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
  'detectors.state.enabled': 'Enabled',
  'detectors.state.disabled': 'Disabled',
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
  // What a stored expression says, for the list. Only the shapes the presets
  // can write are named here; anything else keeps the expression alone rather
  // than being described approximately.
  'schedules.frequency.daily': 'Every day at {time}',
  'schedules.frequency.weekdays': 'Every weekday at {time}',
  'schedules.frequency.weekly': 'Every {weekday} at {time}',
  'schedules.frequency.monthly': 'The 1st of each month, at {time}',
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
  // The presets: a readable frequency that generates the cron field above
  // rather than replacing it, so "toda segunda às 08:00" and a hand-written
  // expression are two ways to arrive at the same field.
  'schedules.create.frequency': 'Frequency',
  'schedules.create.frequencyHelp':
    'A readable frequency, which writes the cron field above rather than replacing it.',
  'schedules.create.frequency.custom': 'Custom cron',
  'schedules.create.frequency.daily': 'Every day',
  'schedules.create.frequency.weekdays': 'Every weekday (Monday to Friday)',
  'schedules.create.frequency.weekly': 'Every week, on a chosen day',
  'schedules.create.frequency.monthly': 'Every month, on the 1st',
  'schedules.create.weekday': 'Day of week',
  'schedules.create.weekday.monday': 'Monday',
  'schedules.create.weekday.tuesday': 'Tuesday',
  'schedules.create.weekday.wednesday': 'Wednesday',
  'schedules.create.weekday.thursday': 'Thursday',
  'schedules.create.weekday.friday': 'Friday',
  'schedules.create.weekday.saturday': 'Saturday',
  'schedules.create.weekday.sunday': 'Sunday',
  'schedules.create.time': 'Time',
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
  'memory.componentType.service': 'services',
  'memory.componentType.node': 'nodes',
  'memory.componentType.guest': 'guests',
  'memory.componentType.cluster': 'cluster',
  'memory.episode.outcome.resolved': 'Resolved',
  'memory.episode.outcome.mitigated': 'Mitigated',
  'memory.episode.outcome.inconclusive': 'Inconclusive',
  'memory.episode.outcome.falsePositive': 'False positive',
  'memory.episode.openInvestigation': 'open investigation →',
  'memory.count': '{count} episodes',
  'memory.learned.title': 'What the agent learned from this',
  'memory.learned.empty':
    'Nothing distilled yet. Learnings are proposed once episodes agree, and wait here for review.',
  'memory.learned.from': 'from {run}',
  'memory.learned.promote': 'promote to document',
  'memory.preview.documents': '{count} documents ingested',
  'memory.preview.documents.empty': 'Documents — nothing ingested yet',
  'memory.preview.open': 'open →',
  'memory.preview.topology': '{count} nodes observed',
  'memory.preview.topology.empty': 'Topology — nothing observed yet',
  'memory.search': 'Search episodes',
  'memory.stats.title': 'What the corpus holds',
  'memory.stats.episodes': 'Episodes',
  'memory.episodes.empty.heading': 'No episodes yet',
  'memory.episodes.empty.body':
    'An episode is written when an investigation ends, and none has been written yet.',
  // The same mechanism with its second clause dropped, for the collapsed
  // section that goes on to name a cause. "None has been written yet"
  // followed by a sentence counting the investigations that finished is the
  // panel saying the same thing twice and disagreeing with itself in tone.
  'memory.episodes.empty.mechanism':
    'An episode is written when an investigation ends.',
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
  // Advanced, collapsed sections on the Documents tab: policy switches for
  // what an investigation may consult, and where the change source reads
  // from — technical groups the raw configuration editor used to carry.
  'knowledge.advanced.heading': 'Advanced settings',
  'knowledge.advanced.changes.title': 'Change source',
  'knowledge.advanced.field.repositoryPath': 'Repository path',
  'knowledge.advanced.field.gitHostVendor': 'Git host vendor',
  'knowledge.advanced.field.gitHostRepository': 'Git host repository',
  'knowledge.advanced.knowledge.title': 'Knowledge access',
  'knowledge.advanced.field.topologyEnabled': 'Follow resource topology',
  'knowledge.advanced.field.knowledgeBaseEnabled': 'Search the knowledge base',
  'knowledge.advanced.memory.title': 'Episodic memory',
  'knowledge.advanced.field.memoryReadEnabled': 'Recall past incidents',
  'knowledge.advanced.field.memoryWriteEnabled': 'Record finished investigations',
  'knowledge.advanced.strategy.title': 'Strategy',
  'knowledge.advanced.field.strategyEnabled': 'Offer distilled playbooks',

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
  'autonomy.tabs':
    'What this deployment may do alone, when it may not, and what always holds',
  'autonomy.tab.posture': 'Posture',
  'autonomy.tab.rules-windows': 'Rules & windows',
  'autonomy.tab.guardrails': 'Guardrails',
  // The subtitle every tab shares — it belongs to the page, not to Posture —
  // replacing the static description `page.context` gives every other
  // Settings page, since neither the node nor the posture in force is a fact
  // a catalogue can hold.
  'autonomy.subtitle': 'Node: {node} · Posture now: {posture}',
  // An active override outranks the saved level: what actually governs right
  // now is the override's, and this says so rather than reporting the saved
  // level as if nothing temporary were in force.
  'autonomy.subtitle.override':
    'Node: {node} · Posture now: {posture}, from a temporary override',
  'autonomy.posture.title': 'What this deployment may do on its own',
  'autonomy.posture.save': 'Save posture',
  // Follows the level selector and its Save, never precedes them — the
  // sentence a reader gets once they have already seen the control it
  // explains.
  'autonomy.posture.empty.scopeLead': 'Rules that narrow or widen one scope live in',
  'autonomy.posture.guardrails.title': 'Guardrails in effect',
  'autonomy.rules.title': 'Rules, in resolution order',
  'autonomy.column.scope': 'Scope',
  'autonomy.column.matcher': 'Matcher',
  'autonomy.column.level': 'Level',
  'autonomy.column.risk': 'Risk bound',
  'autonomy.column.applies': 'Applies to',
  'autonomy.editor.level': 'Level',
  'autonomy.editor.simulation.title': 'Simulate this change',
  'autonomy.editor.simulation.description':
    'Replays what this node has actually decided recently, under the change above, and says what would be different — the save button appears once you have seen it.',
  'autonomy.editor.preview': 'What would this decide differently?',
  'autonomy.editor.previewing': 'Asking the deployment…',
  'autonomy.editor.explain': 'Explain',
  'autonomy.editor.explaining': 'Explaining…',
  'autonomy.editor.explainIntro': 'Or check a single hypothetical action instead:',
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
  'autonomy.editor.dryRunOn': 'Simulate every decision across the deployment',
  'autonomy.editor.dryRunOff': 'Decide for real again',
  'autonomy.editor.dryRunBanner':
    'Simulating: every action is decided and none of them is performed. This deployment proposes and does not act.',
  'autonomy.editor.decision': 'Decision',
  'autonomy.editor.winningRule': 'Winning rule',
  'autonomy.override.duration': 'Expires',
  'autonomy.override.reason': 'Granted because',
  'autonomy.override.grantedBy': 'Granted by',
  // What the header button says and what the side panel is titled — the same
  // phrase names both, so whoever opens the panel finds the words they
  // clicked waiting for them at the top of what opened.
  'autonomy.override.temporary.title': 'Temporary override',
  'autonomy.override.temporary.close': 'Close',
  'autonomy.override.panel.title': 'Grant or revoke an override',
  'autonomy.override.grant.title': 'Grant an override',
  'autonomy.override.grant.name': 'Name',
  'autonomy.override.grant.nameHelp':
    'A short identifier for this override, unique on this node. It appears in the audit trail and is what a revoke names.',
  'autonomy.override.grant.level': 'Level',
  // The label itself, not a caption beside it, says this is recorded — a
  // reader who only reads labels still learns where a reason ends up.
  'autonomy.override.grant.reason': 'Reason — recorded in the audit trail',
  'autonomy.override.grant.reasonHelp':
    'Recorded in the audit trail beside the override, for whoever reviews it later.',
  'autonomy.override.grant.duration': 'Duration',
  'autonomy.override.grant.durationDefault': 'Default (2 hours)',
  'autonomy.override.grant.durationOneHour': '1 hour',
  'autonomy.override.grant.durationEightHours': '8 hours',
  'autonomy.override.grant.durationTwentyFourHours': '24 hours',
  'autonomy.override.grant.durationCustom': 'Custom duration…',
  'autonomy.override.grant.seconds': 'Seconds (optional)',
  'autonomy.override.grant.submit': 'Grant',
  'autonomy.override.grant.granting': 'Granting…',
  'autonomy.override.grant.granted': 'Granted. It will expire on its own.',
  'autonomy.override.grant.reasonRequired':
    'A reason is required before this can be granted.',
  'autonomy.override.revoke.title': 'Revoke an override',
  'autonomy.override.revoke.empty': 'No override is active on this node right now.',
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
  // One key per destination, replacing the single "Look at the
  // configuration" label every empty state on this route used to share —
  // three different destinations is three different sentences, not one that
  // named none of them honestly.
  'autonomy.cta.createRule': 'Create the first rule',
  'autonomy.cta.recordBound': 'Record a freeze or a budget',
  'autonomy.cta.grantOverride': 'Grant an override',
  'autonomy.glossary.rule':
    'A rule decides what this deployment may do for one scope, from the whole deployment down to a single resource — read in order, least specific first.',
  'autonomy.glossary.bound':
    'A bound is a limit no rule can raise — the emergency stop, a freeze window, a spend cap — checked after a rule decides, and able to refuse it.',
  'autonomy.glossary.override':
    "An override is a temporary, reasoned raise of one scope's level, granted on the record and gone the moment it expires or is revoked.",
  'autonomy.editor.newRule.title': 'Create a rule',
  'autonomy.editor.newRule.scope': 'Scope',
  'autonomy.editor.newRule.level': 'Level',
  'autonomy.editor.newRule.team': 'Team',
  'autonomy.editor.newRule.resourceKind': 'Resource kind',
  'autonomy.editor.newRule.resourceId': 'Resource',
  'autonomy.editor.newRule.capability': 'Capability',
  'autonomy.editor.newRule.labelName': 'Label name',
  'autonomy.editor.newRule.labelValue': 'Label value',
  'autonomy.editor.newRule.add': 'Add rule',
  'autonomy.scope.deployment': 'The whole deployment',
  'autonomy.scope.team': 'One team',
  'autonomy.scope.resource_kind': 'One kind of resource',
  'autonomy.scope.labels': 'Resources carrying a label',
  'autonomy.scope.capability': 'One capability',
  'autonomy.scope.resource': 'One resource',
  'autonomy.scope.capability_resource': 'One capability on one resource',
  'autonomy.freezes.title': 'Create a freeze window',
  'autonomy.freeze.name': 'Name',
  'autonomy.freeze.start': 'Starts',
  'autonomy.freeze.end': 'Ends',
  'autonomy.freeze.reason': 'Reason',
  'autonomy.freeze.add': 'Add freeze',
  'autonomy.budgets.title': 'Create a budget',
  'autonomy.budget.name': 'Name',
  'autonomy.budget.limit': 'Limit',
  'autonomy.budget.countedBy': 'Counted by',
  'autonomy.budget.add': 'Add budget',

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
  // Human titles for the technical sections whose own schema paths used to
  // stand in as a title — the path a section's fields sit under is never
  // printed as a title again.
  // A section this catalogue has not named yet still gets one: the
  // humanised form of its own name, not its raw path (see `sectionTitle` in
  // `preview.tsx`).
  'configuration.section.policiesMasking': 'Masking',
  'configuration.section.policiesGuardrails': 'Guardrails',
  'configuration.section.policiesApprovals': 'Approvals',
  'configuration.section.policiesAutonomy': 'Autonomy',
  'configuration.section.notificationPolicy': 'Notification policy',
  'configuration.provenance.default': 'Deployment default',
  'configuration.provenance.setAt': 'Set at: {node}',
  'configuration.provenance.mixed': 'Set across more than one node',
  // An effective-configuration table's own Value column: a boolean as a
  // state a reader can act on, a genuinely absent value marked as such, and
  // the two durations this screen group actually shows — never the payload
  // literal, and never a blank cell standing in for any of them.
  'configuration.value.on': 'On',
  'configuration.value.off': 'Off',
  'configuration.value.notSet': 'Not set',
  'configuration.value.hours.one': '{count} hour',
  'configuration.value.hours': '{count} hours',
  'configuration.value.seconds.one': '{count} second',
  'configuration.value.seconds': '{count} seconds',
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
  'teamContext.budgetConsequence': 'What goes over budget is refused, not truncated.',
  'teamContext.overBudget':
    'Over the budget. The deployment will refuse this until it is shorter.',
  'teamContext.disabled':
    'The operating context is switched off for this node. It is stored and nothing is sent.',
  'teamContext.addSection': 'Add a section',
  'teamContext.addSection.disabledReason': 'Type a name before adding a section.',
  'teamContext.sectionName': 'Section name',
  'teamContext.remove': 'Clear this section',
  'teamContext.empty.heading': 'Nothing written here yet',
  'teamContext.empty.body':
    'No level of this tree has written any operating context, so every investigation starts from the shipped prompt alone. The starting document below is derived from what this deployment has already discovered.',
  'teamContext.empty.action': 'Look at the organisation',
  'teamContext.template.title': 'A starting point, from what is already known',
  'teamContext.template.lead':
    'Derived from this deployment’s own estate — the kinds it holds, the zones its addresses sit on, the source that answers each signal question. Nothing here is written until you save it.',
  'teamContext.template.use': 'Use the starting document',
  'teamContext.preview.title': 'What the model will be sent',
  'teamContext.preview.lead':
    'The exact text the next investigation’s system prompt will carry, assembled by the deployment. The save appears once you have asked for it.',
  'teamContext.preview.submit': 'Show me the prompt',
  'teamContext.preview.disabledReason':
    'Change a section before asking for the prompt.',
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
  'catalogue.search': 'Name, domain or capability',
  'catalogue.search.empty': 'Nothing here matches that search.',
  'catalogue.domains.nav': 'Jump to a domain',
  'catalogue.count': '{enabled} of {total} enabled',
  'catalogue.column.name': 'Capability',
  'catalogue.column.domain': 'Domain',
  'catalogue.column.effect': 'Side effect',
  'catalogue.column.integrations': 'Needs',
  'catalogue.column.enabled': 'Enabled here',
  'catalogue.state.enabled': 'Enabled',
  'catalogue.state.disabled': 'Disabled',
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
  // The delivery-token-group block only (alert-intake.tsx): the trust
  // sentence beside the receiver's token control. `ingress.verification`
  // above is a different, still-legitimate use on the same page (the
  // per-source verification description) and is untouched.
  'ingress.delivery.authenticated': 'Authenticated with delivery token',
  'ingress.delivery.unauthenticated': 'No delivery token has authenticated this yet.',
  'ingress.token.issue': 'Issue a delivery token',
  'ingress.token.issuing': 'Issuing\u2026',
  'ingress.token.rotate': 'Rotate',
  'ingress.token.shownOnce':
    'Copy it now. It is shown once and is never readable again \u2014 the deployment keeps only a hash of it.',
  'ingress.token.failed': 'The deployment refused to issue it.',
  'ingress.token.unreachable': 'The deployment could not be reached.',
  'firstRun.integrations.foundHere': 'Found in your estate at',
  'catalogue.integrations.count.total': 'in the catalogue',
  'catalogue.integrations.count.connected': 'connected',
  'catalogue.integrations.count.available': 'available',
  'catalogue.integrations.title': 'Integrations',
  'catalogue.integrations.advanced.title': 'Advanced: configured vendors',
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
  // One word each, for the filter's own options — the sentences above say the
  // same thing at the length a collapsed card affords; the filter needs the
  // length a dropdown affords instead.
  'catalogue.integrations.filter.state.unconfigured': 'Not connected',
  'catalogue.integrations.filter.state.unknown': 'Stored',
  'catalogue.integrations.filter.state.healthy': 'Verified',
  'catalogue.integrations.filter.state.degraded': 'Failing',

  // --- The integrations catalogue: connected first, the rest a search --------------
  'catalogue.integrations.summary.suggested':
    '{suggested} of them are already running in this estate — connect one and it stops being a guess.',
  'catalogue.integrations.connected.title': 'Connected',
  'catalogue.integrations.connected.manage': 'Manage',
  'catalogue.integrations.filter.view.connected': 'Connected · {count}',
  'catalogue.integrations.filter.view.suggested': 'Suggested · {count}',
  'catalogue.integrations.available.title': 'Available',
  'catalogue.integrations.suggested.title': 'Suggested by your estate',
  'catalogue.integrations.suggested.evidence':
    'Found at {address}, on resource {resource}',
  // The estate found this vendor, but never resolved a legible name for the
  // resource it is running on. Address and kind, never the raw identifier —
  // that stays recoverable as a data attribute, not folded into this sentence.
  'catalogue.integrations.suggested.evidence.unresolved':
    'Found at {address}, on a {kind}',
  'catalogue.integrations.suggested.connect': 'Connect',
  'catalogue.integrations.search.label': 'Search by name, category or capability',
  'catalogue.integrations.search.empty.heading': 'Nothing matches that',
  'catalogue.integrations.search.empty.body':
    'No integration in the catalogue matches this search or filter.',
  'catalogue.integrations.search.empty.clear': 'Clear the search',
  'catalogue.integrations.filter.category': 'Category',
  'catalogue.integrations.category.logstore': 'Log store',
  'catalogue.integrations.category.metrics': 'Metrics',
  'catalogue.integrations.category.tracing': 'Tracing',
  'catalogue.integrations.category.cloud_control_plane': 'Cloud',
  'catalogue.integrations.category.database': 'Database',
  'catalogue.integrations.category.vcs': 'Version control',
  'catalogue.integrations.category.cicd': 'CI/CD',
  'catalogue.integrations.category.ticketing': 'Ticketing',
  'catalogue.integrations.category.incident': 'Incident management',
  'catalogue.integrations.category.communication': 'Chat & on-call',
  'catalogue.integrations.category.data_platform': 'Data',
  'catalogue.integrations.category.model_provider': 'Model provider',
  'catalogue.integrations.footer.gaps':
    '{count} integrations moved to the roadmap · see the list and why',
  'catalogue.integrations.panel.close': 'Close',
  'catalogue.integrations.panel.notFound': 'This integration is not in the catalogue.',
  'catalogue.integrations.panel.notFound.action': 'Back to Integrations',
  'catalogue.integrations.panel.permissions.heading': 'Required permissions',
  'catalogue.integrations.panel.permissions.grantedAt': 'Granted at',
  'catalogue.integrations.panel.readOnly':
    'You do not hold the permission to change this integration.',
  'catalogue.integrations.panel.direction.outbound':
    'This deployment calls it. Nothing arrives from it, and the credential below is what it presents when it calls.',
  'catalogue.integrations.panel.direction.both':
    'Both ways. This deployment reads its API with the credential below, and it posts alerts here with a different one \u2014 a delivery token, issued separately.',
  'catalogue.integrations.panel.intake.action': 'Point your alert router at it',
  'catalogue.integrations.panel.security':
    'Stored in the vault; never shown again. Testing it makes a real request — stored and working are different states.',
  'catalogue.integrations.panel.saveAndTest': 'Save and test',
  'catalogue.integrations.panel.testing': 'Saving and testing…',
  'catalogue.integrations.panel.docs.heading': 'Package documentation',
  'catalogue.integrations.panel.docs.toggle': 'Read the package documentation',
  'catalogue.integrations.panel.docs.unreadable':
    "This vendor's own documentation could not be read.",
  // More than one team holds a credential for this vendor. The process does
  // not choose one in silence: it falls back to the organisation-wide
  // handle, and this is what says that decision was made.
  'catalogue.integrations.panel.credentialTeamAmbiguous':
    'More than one team holds a credential for this vendor. Investigations use the organisation-wide credential until this is resolved.',
  // --- A connected integration's panel: state and actions, not an empty form ------
  'catalogue.integrations.panel.storedInVault':
    'This credential is stored in the vault.',
  // For a vendor that ships no authentication of its own. Saying a credential
  // is stored for one that stores none is a sentence that sends somebody
  // looking for a key nobody ever entered.
  'catalogue.integrations.panel.connectedByAddress':
    'This vendor needs no credential of its own. It is connected by the address above.',
  'catalogue.integrations.panel.testAgain': 'Test again',
  'catalogue.integrations.panel.replaceCredential': 'Replace credential',
  // Shared by two exits: leaving "Replace credential" without saving, and
  // leaving the disconnect confirmation without disconnecting.
  'catalogue.integrations.panel.cancel': 'Cancel',
  'catalogue.integrations.panel.disconnect': 'Disconnect',
  'catalogue.integrations.panel.disconnect.consequence':
    'This removes the stored credential from the vault. The integration returns to Available until it is reconnected.',
  // --- Certificate trust: what this deployment checks the endpoint against ---------
  'catalogue.integrations.panel.trust.heading': 'Certificate trust',
  'catalogue.integrations.panel.trust.intro':
    'What this deployment accepts from the certificate this address presents. Declared for this address only — moving the address starts over.',
  'catalogue.integrations.panel.trust.fingerprintsLabel': 'Pinned fingerprints',
  'catalogue.integrations.panel.trust.fingerprintsHelp':
    "One SHA-256 fingerprint per line, copied from the node's own interface. A cluster lists one fingerprint per node in the same declaration.",
  'catalogue.integrations.panel.trust.certificateLabel': 'Certificate authority (PEM)',
  'catalogue.integrations.panel.trust.certificateHelp':
    'The authority the cluster minted for itself. Covers every node whose certificate chains to it — the form a cluster usually wants.',
  'catalogue.integrations.panel.trust.submit': 'Declare trust',
  'catalogue.integrations.panel.trust.sending': 'Declaring…',
  'catalogue.integrations.panel.trust.saved': 'Declared. Testing the connection now.',
  'catalogue.integrations.panel.trust.refused': 'The deployment refused it:',
  'catalogue.integrations.panel.trust.unreachable':
    'The deployment could not be reached.',
  'catalogue.integrations.panel.trust.unverifiedHeading': 'Accept without verifying',
  'catalogue.integrations.panel.trust.unverifiedReasonLabel': 'Why',
  'catalogue.integrations.panel.trust.unverifiedReasonHelp':
    'Recorded with your name and the moment you accept, because giving up certificate verification is a decision, not a setting.',

  // --- The reference page for vendors this catalogue does not cover ----------------
  'catalogue.notCovered.title': 'Not covered, and why',
  'catalogue.notCovered.intro':
    'Every vendor this catalogue does not reach, and why: some cannot be reached from a credential proxy that speaks only HTTP, and some were evaluated and decided against.',
  'catalogue.notCovered.back': 'Back to Integrations',

  // --- Administration ----------------------------------------------------------------------------
  'admin.principals.title': 'People and machines',
  'admin.principals.serviceAccount':
    'A service account created at deploy, with no email.',
  // The account-facing vocabulary: what kind of principal this is, and
  // whether it may currently sign in — never the transport words the API
  // reports (`service_account`, `is_active`) and never health vocabulary
  // (`HEALTHY`), which describes a resource and not a person.
  'principal.kind.person': 'Person',
  'principal.kind.serviceAccount': 'Service account',
  'principal.state.active': 'Active',
  'principal.state.suspended': 'Suspended',
  // What a group of machine tokens has actually done, not the health of a
  // resource — a token group is never "healthy".
  'tokenGroup.state.inUse': 'In use',
  // Whether a schedule fires on its clock, or an operator turned it off —
  // not the health of a resource; a schedule is never "healthy" either.
  'schedule.state.enabled': 'Enabled',
  'schedule.state.disabled': 'Disabled',
  // Whether single sign-on is currently the way in — not the health of a
  // resource; the finer distinction (tested, not yet tested, not
  // configured) stays the sentence beside this chip.
  'sso.state.active': 'Active',
  'sso.state.inactive': 'Inactive',
  'admin.column.principal': 'Principal',
  'admin.column.kind': 'Kind',
  'admin.column.active': 'Active',
  // The primary action Members & roles never had: a person, created without
  // leaving the page, with the local password they sign in with. Absent for
  // a viewer who may not write identity — see `PrincipalsPanel`'s own doc.
  'admin.principals.create.displayName': 'Display name',
  'admin.principals.create.email': 'Email',
  'admin.principals.create.password': 'Initial password',
  'admin.principals.create.passwordHelp': 'What this person signs in with locally.',
  'admin.principals.create.action': 'Create person',
  'admin.principals.create.creating': 'Creating…',
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
  'admin.grant.addAction': 'Grant this administrative role',
  'admin.grant.addConsequence': 'They can do everything this role allows, immediately.',
  'admin.grant.addClose': 'Close',
  'admin.grant.addCancel': 'Do not grant it',
  // The role picker's own help text: what the selected role permits, as a
  // human sentence bounded by how many permission domains it reaches rather
  // than by how many permissions it holds — a role with dozens of them still
  // reads as one sentence, never a disguised list. `rolePermissions` names
  // the expansion that holds the full list instead.
  'admin.grant.role.summary.one': 'Reaches {count} permission domain',
  'admin.grant.role.summary': 'Reaches {count} permission domains',
  'admin.grant.rolePermissions': 'See every permission',
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
  'admin.tokens.revokedGroup.one': '{count} revoked',
  'admin.tokens.revokedGroup': '{count} revoked',
  'admin.column.token': 'Token',
  'admin.column.scopes': 'Scopes',
  'admin.column.expires': 'Expires',
  // What an active session identifies itself by, alongside who holds it: the
  // deployment has no device or network origin to report, so this is when it
  // started — "since when" rather than a bare session number.
  'admin.column.origin': 'Started',
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
  // Shown in place of the not-tested state, and only while every field is
  // still exactly as the deployment answered it and nobody has touched or
  // submitted the form — the deployment has not been asked to configure
  // this, as opposed to having tried and not yet passed a check.
  'admin.sso.notConfigured': 'Not configured yet',
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
  'live.state.live': 'Live',
  'live.state.refreshing': 'Refreshing',
  'live.state.stale': 'Not updating',
  'live.state.paused': 'Paused',
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
  'agent.tab.topology': 'Pipeline',
  'agent.tab.tools': 'Tools',
  'agent.tab.autonomy': 'Autonomy',
  'agent.graph.title':
    'The investigation, from the orchestrator down to the specialists',
  'agent.rank.orchestrator': 'Orchestrator',
  'agent.rank.stages': 'Stages',
  'agent.rank.specialists': 'Specialists',
  'agent.stages.title': 'The stages an investigation runs',
  'agent.metro.title': 'The six stages of an investigation',
  'agent.metro.subtitle':
    'every run walks this line, and the transcript groups by stage',
  'agent.metro.inFlight': '{count} investigations in flight',
  'agent.metro.copy.resolve_integrations':
    'Discovers what this team can call; with nothing, it ends early.',
  'agent.metro.copy.intake':
    'Decides whether there is an incident and links it to one already open, when it is the same.',
  'agent.metro.copy.plan_evidence':
    'Scores the capabilities and chooses where it is worth starting.',
  'agent.metro.copy.gather_evidence':
    'Runs the planned reads and keeps only what supports something.',
  'agent.metro.copy.diagnose':
    'Forms hypotheses and tests them against the retained evidence.',
  'agent.metro.copy.deliver':
    'Writes the cause, proposes the action, and records the episode.',
  'agent.metro.tools.ratio': '{enabled} of {total} enabled',
  'agent.metro.tools.read': 'Reads · {count}',
  'agent.metro.tools.writeReversible': 'Writes, reversible · {count}',
  'agent.metro.tools.destructive': 'Destructive · {count}',
  'agent.metro.team.budget': '{used} of {budget} tokens',
  'agent.metro.team.empty':
    'No fact written yet. Environment facts join every investigation\u2019s prompt.',
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
  'agent.specialists.state.enabled': 'Enabled',
  'agent.specialists.state.disabled': 'Disabled',
  'agent.models.title': 'What each role runs on',
  'agent.models.body':
    'A stage names a role, never a model. What a role resolves to is configuration, and every row here says which node supplied it.',
  'agent.models.default': 'deployment default — nobody bound this role',
  'agent.models.inherited': 'no choice of its own — follows the investigator',
  'agent.models.from': 'from {node}',
  'agent.models.empty.heading': 'No role is described here',
  'agent.models.empty.body':
    'The deployment could not say which roles it resolves. Every role still runs on the deployment default.',
  'agent.models.empty.action': 'Edit the configuration',
  'agent.budgets.title': 'What one investigation may spend',
  'agent.budgets.body':
    'A team may lower any of these and may not raise one past its ceiling. The ceiling is a constant in the deployment, not a setting.',
  'agent.budgets.ceiling': 'ceiling {ceiling}',
  'agent.budgets.maxIterations': 'Max iterations',
  'agent.budgets.maxParallelSubagents': 'Max parallel specialists',
  'agent.budgets.maxSubagentDepth': 'Max specialist depth',
  'agent.budgets.toolBudget': 'Tool budget',
  'agent.budgets.empty.heading': 'No budget is described here',
  'agent.budgets.empty.body':
    'The deployment did not describe the budget fields for this node, so the ceilings cannot be shown.',
  'agent.budgets.empty.action': 'Edit the configuration',
  // Advanced, collapsed section of the Topology tab: the per-role prompt
  // overrides, the operating-context ablation switch, and the one budget
  // (max_subagent_iterations) the read-only panel above does not name.
  'agent.advanced.title': 'Advanced agent settings',
  'agent.advanced.field.promptInvestigator': 'Investigator prompt override',
  'agent.advanced.field.promptIntake': 'Intake prompt override',
  'agent.advanced.field.promptDiagnose': 'Diagnose prompt override',
  'agent.advanced.field.operatingContextEnabled': 'Send operating context',
  'agent.advanced.field.maxSubagentIterations': 'Max specialist iterations',
  'agent.document.untouched':
    'Nothing has been overridden for this node: it runs the shipped pipeline as it stands. The document below says so in the deployment’s own words.',
  'agent.document.title': 'The same topology, as the document',
  'agent.empty.heading': 'The pipeline could not be described',
  'agent.empty.body':
    'The deployment did not answer with the stages an investigation runs. Nothing here is configuration; it is what the build is.',
  'agent.empty.action': 'Edit the configuration',
  // The catalogue's own read half, absorbed here: every tool and skill this
  // deployment declares, searchable — the same table `catalogue.tsx` used to
  // draw, on its own route, before Integrations took the write half.
  'agent.tools.browse': 'Find a tool or skill',
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
  'agent.tools.advanced.title': 'Advanced capability settings',
  'agent.bridged.title': 'Servers outside this deployment',
  'agent.bridged.body':
    'A tool from one of these came from somewhere the operator does not run. Its tools are enumerated when the deployment reaches the server, and one nobody classified cannot execute.',
  'agent.bridged.empty.heading': 'No outside server is registered',
  'agent.bridged.empty.body':
    'Every tool this team can run is one this build ships. Register a bridged server to add tools from elsewhere.',
  'agent.bridged.empty.action': 'Edit the configuration',
  'agent.bridged.state.enabled': 'Enabled',
  'agent.bridged.state.disabled': 'Disabled',
  'agent.outlook.title': 'What would happen, by class of action',
  'agent.outlook.body':
    'One sentence per class, answered by the deployment itself under the policy as it stands right now.',
  'agent.outlook.reason': 'Why:',
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
  // The panel below is the whole of this page's content, not a filtered
  // sub-view — so its own heading names the same concept the sidebar and the
  // page title already do, rather than a second phrasing of it.
  'proposals.title': 'Proposed changes',
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

  // --- The Settings hub: its own entry, and the subnav's groups and pages ------
  // The subnav's group names and every page name below stay in English in
  // every locale — they are the product's own vocabulary for these places,
  // the same way an integration's own name is never translated.
  'nav.settings': 'Settings',
  'settings.subnav.label': 'Settings pages',
  'page.settings.title': 'Settings',
  'page.settings.context':
    'Everything about this deployment that is not incident work: who has access, how the agent behaves, and where data comes from.',
  'settings.group.organization': 'Organisation',
  'settings.group.agent': 'Agent',
  'settings.group.data': 'Data',
  'settings.page.membersRoles': 'Members & roles',
  'settings.page.membersRoles.context':
    'Who exists in this deployment, the roles they hold, and the sessions they have open.',
  'settings.page.singleSignOn': 'Single sign-on',
  'settings.page.singleSignOn.context': 'How people sign in without a local password.',
  'settings.page.machineTokens': 'Machine tokens',
  'settings.page.machineTokens.context':
    'Credentials issued for a script or a service, grouped by what created them.',
  'settings.page.auditLog': 'Audit log',
  'settings.page.auditLog.context': 'Who did what, when, and against which resource.',
  'settings.page.modelsProviders': 'Models & providers',
  'settings.page.modelsProviders.context':
    'Which model drives investigations, and the credential it runs on.',
  'settings.page.autonomyGuardrails': 'Autonomy & guardrails',
  'settings.page.autonomyGuardrails.context':
    'What this deployment may do on its own, and what it must ask about.',
  'settings.page.notifications': 'Notifications',
  'settings.page.notifications.context':
    'Where a report goes once an investigation finishes, and when to stay quiet.',
  'settings.page.alertIntake': 'Alert intake',
  'settings.page.alertIntake.context':
    'What arrives, and the rules that decide what happens to it.',
  'settings.page.schedulesDestinations': 'Schedules & destinations',
  'settings.page.schedulesDestinations.context':
    'The investigations that run on a clock, and where an alert ends up once it has one.',
  // Shared by every page the subnav lists before the feature that owns it has
  // shipped — named honestly rather than left off the subnav, because a route
  // that exists and says so is worth more than one invented to fill the gap.
  'settings.notBuilt.body':
    'This page is part of the {group} rework, which has not shipped yet.',
  'settings.notBuilt.action': 'Back to Settings',

  // --- Settings: Models & providers -----------------------------------------
  'settings.models.role.investigator': 'Investigator',
  'settings.models.role.subagent': 'Subagent',
  'settings.models.role.intake': 'Intake',
  'settings.models.role.diagnose': 'Diagnose',
  'settings.models.role.extraction': 'Extraction',
  'settings.models.role.embedding': 'Embedding',
  'settings.models.role.selection': 'Selection',
  'settings.models.role.summarisation': 'Summarisation',
  'settings.models.empty.body':
    'No provider answered. Connect one from the integrations catalogue to choose what drives an investigation.',
  'settings.models.empty.action': 'Open the integrations catalogue',
  'settings.models.provider': 'Provider',
  'settings.models.model.known': 'Model',
  'settings.models.model.free': 'Model',
  'settings.models.toolCalling.supported': ' — supports tool calling',
  'settings.models.toolCalling.unsupported': ' — does not support tool calling',
  'settings.models.toolCalling.unknown': ' — tool calling not confirmed',
  'settings.models.verificationNote': 'Last verification:',
  'settings.models.notConnected': 'No credential is stored for this provider.',
  'settings.models.connectCredential': 'Connect a credential',
  'settings.models.advanced.title': 'Advanced roles',
  'settings.models.advanced.lead':
    'Subagent, intake, diagnose, extraction, embedding, selection and summarisation inherit the investigator’s default unless fixed here.',
  'settings.models.advanced.inherits': 'Inherits the default',
  'settings.models.revert': 'Return to inheriting the default',
  'settings.models.reverted': 'Will inherit the default once saved',
  'settings.models.saveAndVerify': 'Save and verify',
  'settings.models.saving': 'Saving…',
  'settings.models.testWithoutSaving': 'Test without saving',
  'settings.models.verifying': 'Verifying…',
  'settings.models.verified': 'A check reached this provider and it answered.',
  'settings.models.verificationFailed': 'The check did not pass.',
  'settings.models.saved': 'Saved. This is what the agent now runs on.',
  'settings.models.failed': 'The deployment refused this change.',
  'settings.models.unreachable': 'The deployment could not be reached.',
  'settings.models.nothingChanges': 'Nothing would change.',
  'settings.models.checkAgain': 'Check again',
  'settings.models.checking': 'Checking…',
  'settings.models.chooseVerifiedModel': 'Choose a model from the verified list',
  'settings.models.reloadModels': 'Reload models',
  'settings.models.reloadingModels': 'Reloading…',
  'settings.models.staticModelsLabel':
    'Static list — the endpoint could not be asked what it currently serves.',
  'settings.models.advanced.summaryAll':
    '{total} roles, all inherit the investigator’s default',
  'settings.models.advanced.summaryPartial':
    '{total} roles, {inheriting} inherit the investigator’s default',
  'settings.models.check.credentials': 'Credentials',
  'settings.models.check.authentication': 'Authentication',
  'settings.models.check.toolCalling': 'Tool calling',
  'settings.models.check.structuredOutput': 'Structured output',
  'settings.models.check.streaming': 'Streaming',
  'settings.models.consequence.credentials':
    'No credential resolved, so nothing was called.',
  'settings.models.consequence.authentication':
    'The endpoint rejected this deployment’s credential.',
  'settings.models.consequence.toolCalling':
    'Investigations are sequences of tool calls — this model may stall on them.',
  'settings.models.consequence.structuredOutput':
    'The pipeline’s stages exchange typed documents — this model may fail mid-investigation.',
  'settings.models.consequence.streaming':
    'Streamed output would not reach the console.',

  // --- Settings: Notifications -----------------------------------------------
  'settings.notifications.contractNote':
    'Every value here can only make the platform ceiling stricter.',
  'settings.notifications.field.quiet_hours_enabled': 'Quiet hours',
  'settings.notifications.field.quiet_hours_start': 'Quiet hours start',
  'settings.notifications.field.quiet_hours_end': 'Quiet hours end',
  'settings.notifications.field.timezone': 'Timezone',
  'settings.notifications.field.cooldown_seconds': 'Repeat suppression',
  'settings.notifications.field.notifications_per_hour': 'Notifications per hour',

  // --- Settings: Autonomy & guardrails — the guardrails section --------------
  'settings.autonomy.guardrails.title': 'Guardrails',
  'settings.autonomy.guardrails.lead':
    'Masking, secret detection and approval — edited here, in the same document a rule or a bound is.',
  'settings.autonomy.guardrails.invariant.secret':
    'A match for a secret is always looked at. This cannot be switched off; enforcing or observing decides only whether a match is blocked or only recorded.',
  'settings.autonomy.guardrails.invariant.approval':
    'A write always needs a person to approve it, whatever the threshold below is set to.',
  'settings.autonomy.guardrails.masking.enabled': 'Masking enabled',
  'settings.autonomy.guardrails.masking.level': 'Masking level',
  'settings.autonomy.guardrails.mode': 'Guardrail mode',
  'settings.autonomy.guardrails.ruleset': 'Ruleset',
  'settings.autonomy.guardrails.threshold': 'Approval threshold',
  'settings.autonomy.guardrails.expiryHours': 'Approval request expiry (hours)',
  // What each masking level, guardrail mode and approval threshold actually
  // means, read by `guardrail-values.ts` — the same table's Value column
  // that used to print `write_reversible` verbatim, in a monospace face,
  // beside every other row's own sentence. `off`/`standard`/`strict` already
  // read as words on their own; `local_models_exempt` gets one anyway, so
  // the cell is never three plain values and one dressed-up one.
  'guardrail.maskingLevel.off': 'Off',
  'guardrail.maskingLevel.standard': 'Standard',
  'guardrail.maskingLevel.strict': 'Strict',
  'guardrail.maskingLevel.local_models_exempt': 'Exempt for local models',
  // What enforcing and observing do to a match, not the schema's own word
  // for the mode — the same distinction `settings.autonomy.guardrails.
  // invariant.secret` already draws in prose, said here as the table's own
  // two-value vocabulary.
  'guardrail.mode.enforcing': 'Enforcing — matches are blocked',
  'guardrail.mode.observing': 'Observing — matches are recorded, not blocked',
  // What each threshold actually gates, in the fewest words that still say
  // it correctly. The schema refuses a threshold above `write_reversible` —
  // a write must always be able to reach a person — so these three are every
  // legal value, not a sample of a larger set.
  'guardrail.approvalThreshold.read': 'Every action needs a person',
  'guardrail.approvalThreshold.read_sensitive':
    'Every sensitive read and write needs a person',
  'guardrail.approvalThreshold.write_reversible': 'Every write needs a person',
  'settings.autonomy.guardrails.edit': 'Edit',
  'settings.autonomy.guardrails.cancel': 'Cancel',

  // --- Settings: Autonomy & guardrails — the autonomy scalars, advanced ------
  'settings.autonomy.advanced.title': 'Advanced autonomy settings',
  'settings.autonomy.advanced.field.allowUnverifiableActions':
    'Allow unverifiable actions',
  'settings.autonomy.advanced.field.dryRun': 'Simulate everything for this team',
  'settings.autonomy.advanced.field.recurrenceThreshold': 'Recurrence threshold',
  'settings.autonomy.advanced.field.recurrenceWindowSeconds':
    'Recurrence window (seconds)',

  // --- Settings: Single sign-on — advanced claim mapping ----------------------
  'settings.sso.advanced.title': 'Advanced claim mapping',
  'settings.sso.advanced.field.claimsSubject': 'Subject claim',
  'settings.sso.advanced.field.claimsEmail': 'Email claim',
  'settings.sso.advanced.field.claimsDisplayName': 'Display name claim',
  'settings.sso.advanced.field.claimsGroups': 'Groups claim',

  // --- Settings: Alert intake — advanced observation settings -----------------
  'settings.alertIntake.advanced.title': 'Advanced observation settings',
  'settings.alertIntake.advanced.field.paused': 'Watching paused',
  'settings.alertIntake.advanced.field.pauseReason': 'Why watching is paused',
  'settings.alertIntake.advanced.field.bridgeEnabled': 'Use existing monitoring',
  'settings.alertIntake.advanced.field.bridgeDashboardBaseUrl': 'Dashboard base URL',
  'settings.alertIntake.advanced.field.bridgeMappingIntervalSeconds':
    'Re-match interval (seconds)',
  'settings.alertIntake.advanced.field.bridgeHistoryLookbackSeconds':
    'History lookback (seconds)',
  'settings.alertIntake.advanced.field.bridgeLogWindowSeconds': 'Log window (seconds)',
  'settings.alertIntake.advanced.field.bridgeLogLineLimit': 'Log line limit',
  'settings.alertIntake.advanced.field.bridgeUseShippedRules':
    'Use shipped exporter mappings',
  'settings.alertIntake.advanced.field.bridgeUseShippedLogSelectors':
    'Use shipped log queries',
  'settings.alertIntake.advanced.field.bridgeLogsEnabled': 'Read logs from this system',
  'settings.alertIntake.advanced.field.bridgeLogsName': 'Log system name',
  'settings.alertIntake.advanced.field.bridgeLogsEndpoint': 'Log system address',
  'settings.alertIntake.advanced.field.bridgeLogsIntegration': 'Log system integration',
  'settings.alertIntake.advanced.field.bridgeMetricsEnabled':
    'Read metrics from this system',
  'settings.alertIntake.advanced.field.bridgeMetricsName': 'Metrics system name',
  'settings.alertIntake.advanced.field.bridgeMetricsEndpoint': 'Metrics system address',
  'settings.alertIntake.advanced.field.bridgeMetricsIntegration':
    'Metrics system integration',
  'settings.alertIntake.advanced.field.guardianEnabled': 'Run the shipped detector set',
  'settings.alertIntake.advanced.field.guardianClusterShape': 'Detected cluster shape',
  'settings.alertIntake.advanced.field.guardianHeartbeatDestination':
    'Heartbeat destination',
  'settings.alertIntake.advanced.field.guardianDeclaredIntentSource':
    'Declared intent source',

  // --- Settings: Audit log ----------------------------------------------------
  'settings.auditLog.period.label': 'Period',
  'settings.auditLog.period.days': 'Last {days} days',

  // --- Settings: Machine tokens ------------------------------------------------
  'settings.machineTokens.purposeHelp':
    'Issuing another token for a purpose that already has one replaces it — the change is recorded in the audit log.',
  'settings.machineTokens.detail': 'Individual tokens',
  'settings.machineTokens.superseded.one':
    'Replaced {count} earlier token issued for the same purpose.',
  'settings.machineTokens.superseded':
    'Replaced {count} earlier tokens issued for the same purpose.',
  'settings.machineTokens.revokeOlder': 'Revoke all but the newest',
  'settings.machineTokens.revokingOlder': 'Revoking…',
  'settings.machineTokens.revokeOlderConsequence':
    'Every older token for this purpose stops authenticating now.',
  'settings.machineTokens.revokeOlderConfirm': 'Revoke them',
  'settings.machineTokens.revokeOlderCancel': 'Leave them working',
  'settings.machineTokens.count.one': '{count} token',
  'settings.machineTokens.count': '{count} tokens',
  'settings.machineTokens.lastUsed': 'Last used',
  'settings.machineTokens.neverUsed': 'Never used',
  // The list this screen shows once a caller — Alert intake's own "Rotate",
  // today — arrives with a scope already named in the address.
  'settings.machineTokens.filteredBy': 'Showing tokens scoped to {scope}.',
  'settings.machineTokens.clearFilter': 'Show all tokens',
  'settings.machineTokens.empty.heading': 'No machine tokens yet',
  'settings.machineTokens.empty.body':
    'Tokens issued for a script or a service appear here, grouped by what they were issued for.',
  'settings.machineTokens.empty.action': 'Issue a token',
  'settings.machineTokens.scopesSelected.one': '{count} scope selected',
  'settings.machineTokens.scopesSelected': '{count} scopes selected',
  'settings.machineTokens.template.alertDelivery.name': 'Alert delivery',
  'settings.machineTokens.template.alertDelivery.purpose':
    'Marks the one scope an alert router needs to deliver into this deployment.',
  'settings.machineTokens.template.readOnlyAutomation.name': 'Read-only automation',
  'settings.machineTokens.template.readOnlyAutomation.purpose':
    'Marks every read scope you hold, for a script that only ever looks.',
  'settings.machineTokens.template.disabled':
    'Not available: this template needs a scope outside what you may issue.',
  'settings.machineTokens.destructiveScope.orgDelete':
    'Org Delete lets whoever holds this token delete the entire organisation.',
  'settings.machineTokens.destructiveScope.ownerAssign':
    'Owner Assign lets whoever holds this token grant the owner role to anyone.',
  'settings.machineTokens.destructiveScope.impersonationUse':
    'Impersonation Use lets whoever holds this token act as any other person in this deployment.',

  // --- Settings: Single sign-on -------------------------------------------------
  'settings.sso.step.configure': 'Configure',
  'settings.sso.step.test': 'Test',
  'settings.sso.step.activate': 'Activate',
  'settings.sso.field.provider.help':
    'What you call this identity provider — shown nowhere but here.',
  'settings.sso.field.issuer.help':
    "The issuer URL your provider documents, exactly as it appears there. Usually under the provider's own OpenID configuration page.",
  'settings.sso.field.clientId.help':
    'The client id this deployment registered with the provider when it was set up as an application.',
  'settings.sso.field.authorisation.help':
    "Where the provider's own sign-in page lives — usually named 'authorization_endpoint' in its OpenID configuration.",
  'settings.sso.field.token.help':
    "Where a sign-in code is exchanged for a token — usually named 'token_endpoint'.",
  'settings.sso.field.jwks.help':
    "Where the provider publishes the keys that sign its tokens — usually named 'jwks_uri'.",
  'settings.sso.field.redirect.help':
    'Where the provider sends somebody back to once they have signed in. Register this exact address with the provider.',
  'settings.sso.field.defaultNode.help':
    'Where somebody lands when their groups map to no team in particular — required, because a directory that returns no groups still has to go somewhere.',
  'settings.sso.result.subject': 'Subject',
  'settings.sso.result.email': 'Email',
  'settings.sso.result.team': 'Team',
  'settings.sso.result.team.default': 'the default team, no group matched',
  'settings.sso.result.failed': 'This claim set failed the test:',
  'settings.sso.fallback':
    'Local sign-in stays available as a fallback, whatever this provider is set to — nobody is locked out by a broken identity provider alone.',
  'decisions.card.steps': 'What will happen',
  'decisions.card.rollback': 'If it goes wrong — rollback',
  'decisions.card.noRollback': 'No rollback recorded — this action cannot be undone.',
  'decisions.card.why': 'Why',
  'decisions.card.evidence': 'Evidence behind this',
  'decisions.card.evidenceLink': 'view',
  'decisions.card.blastRadius': 'Blast radius',
  'decisions.card.blastRadius.text': '{count} resource(s) known, depth {depth}',
  'decisions.card.blastRadius.unknown':
    'Unknown — the topology graph could not be read',
  'decisions.card.rawPayload': 'raw action payload',
  'decisions.card.notRecorded': 'Not recorded.',
  'decisions.card.risk': 'Risk',
  'decisions.card.outcome': 'Decided',
  'decisions.card.appliedAndVerified': 'applied and verified',
  'decisions.card.autonomy.reversible':
    '{level} — queued, applies only after your yes.',
  'decisions.card.autonomy.irreversible':
    '{level} — queued, applies only after your yes.',
  'decisions.expiredFooter.explanation':
    'The window for this proposal closed — the environment was read before it expired. Propose again to decide on a current reading.',
  'decisions.expiredFooter.repropose': 'Propose again, now',
  'decisions.expiredFooter.discard': 'Discard',
  'decisions.expiredFooter.failed': 'The deployment did not answer. Nothing changed.',
  'decisions.decided.heading': 'Decided recently',
  'decisions.decided.empty': 'Nothing has been decided yet.',
  'decisions.decided.outcome.approved': 'approved by {who}',
  'decisions.decided.outcome.approvedVerified':
    'approved by {who}, applied and verified',
  'decisions.decided.outcome.rejected': 'rejected by {who}: {reason}',
  'decisions.decided.outcome.rejectedNoReason': 'rejected by {who}',
  'decisions.decided.outcome.discarded': 'discarded by {who}',
} as const;

/** Every key the console may render. Derived, so a typo is a type error. */
export type MessageKey = keyof typeof EN;
