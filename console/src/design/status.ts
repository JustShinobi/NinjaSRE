/**
 * The one place a status becomes a role, and a role becomes a shape.
 *
 * Nothing maps a status to a colour. A status maps to a semantic role, the role
 * maps to a token pair, and the token pair is the only thing a component ever
 * sees — so two screens cannot disagree about what "degraded" looks like,
 * because neither of them decides.
 *
 * Every status also carries a shape. Roughly one man in twelve cannot separate
 * the hues this palette uses for success and danger, and a status carried by
 * colour alone is a status those viewers do not have. The shape is not a
 * decoration on top of the colour; it is the second carrier the requirement
 * asks for, and the two neutral states carry different ones for exactly that
 * reason.
 */

import type { SemanticRole } from './tokens';

/**
 * The statuses the gateway reports for a run.
 *
 * This is the persistence store's own enumeration, served verbatim —
 * `gateway/http/routes/investigations.py::summary_of` writes
 * `status=run.status.value` with no translation, so this is the one closed
 * set a real run's status ever arrives in. It is not the runtime's own
 * status (how one loop iteration ended: completed, partial, cancelled,
 * failed) and it is not a fixture's invention — a repository check
 * (`tools/check_run_status_vocabulary.py`) reads this array and the store's
 * enumeration and reproves the build the moment either lists a word the
 * other does not.
 *
 * `succeeded` is deliberately absent from this list even though the shared
 * presentation table below still knows it: a tool call's own outcome
 * (`ToolCallStatus.SUCCEEDED`) is spelled the same word for an unrelated
 * fact, and a transcript badge still needs to draw it.
 */
export const RUN_STATUSES = [
  'running',
  'suspended',
  'completed',
  'cancelled',
  'failed',
  'interrupted',
] as const;

export type RunStatus = (typeof RUN_STATUSES)[number];

/**
 * Every word that means a run is still doing something — still taking tool
 * calls, on its own.
 *
 * `suspended` is deliberately absent. A run in that state has stopped
 * calling tools and is paused on a person's decision, which is neither
 * "still working" nor "settled and will not change again" — it is its own
 * third thing, surfaced by the open-interaction panel rather than by a live
 * transcript stream watching for tool calls that are not coming.
 */
const LIVE_RUN_STATUSES: readonly string[] = ['running'];

/**
 * Every word that means a run has finished and will not change again.
 *
 * `interrupted` counts as settled here even though it is not a conclusion:
 * nothing is going to resume producing events for a run the store only
 * marked this way because the process that was running it is gone, so a
 * live transcript has nothing further to wait for.
 */
const SETTLED_RUN_STATUSES: readonly string[] = [
  'completed',
  'cancelled',
  'failed',
  'interrupted',
];

/** The statuses a resource, detector or dependency reports. */
export const RESOURCE_STATUSES = [
  'healthy',
  'degraded',
  'unhealthy',
  'unknown',
  'stale',
  'maintenance',
  'absent',
] as const;

export type ResourceStatus = (typeof RESOURCE_STATUSES)[number];

/**
 * The words the data surfaces put in a chip that are not a run's status or a
 * resource's health.
 *
 * A severity, an incident's state, a decision's state, and how reversible an
 * action is. They are declared here for the reason everything else is: a screen
 * that needed a red chip and wrote one would be a screen that decides what red
 * means, and by the fourth screen "critical" is three different reds.
 *
 * `awaiting_approval` is a run status the gateway reports that the run-status
 * list above does not carry, because it belongs to the interaction rather than
 * to the run. It is declared here so it is not drawn as an unknown word.
 */
export const ATTENTION_STATUSES = [
  'critical',
  'high',
  'medium',
  'low',
  'info',
  'open',
  'investigating',
  'awaiting_human',
  'remediating',
  'resolved',
  'suppressed',
  'closed_without_action',
  'awaiting_approval',
  'approval',
  'question',
  'failure',
  'pending',
  'approved',
  'rejected',
  'expired',
  'read_only',
  'reversible',
  'irreversible',
  'locked',
  'disabled',
  'revoked',
] as const;

export type AttentionStatus = (typeof ATTENTION_STATUSES)[number];

/**
 * Whether what is on a screen is arriving.
 *
 * Declared here rather than styled where it is shown, for the reason every
 * other status is: a live indicator each screen coloured for itself is a live
 * indicator that means something slightly different on each of them. And this
 * one carries more weight than most — a transcript that stopped updating and a
 * run that stopped producing events look identical, so the shape has to be
 * readable by somebody who cannot separate this palette's success from its
 * danger.
 */
export const CONNECTION_STATUSES = [
  'connecting',
  'connected',
  'reconnecting',
  'idle',
  'disconnected',
] as const;

export type ConnectionStatus = (typeof CONNECTION_STATUSES)[number];

/**
 * The one vocabulary for a credential's own state, and for what the last live
 * check against it found.
 *
 * Declared once, here, and consumed everywhere a screen shows a credential or
 * a verification — Setup, Integrations, Administration, a card doing its own
 * check. Before this there were at least two backend spellings for the same
 * four facts (the integration catalogue's health — `healthy` / `degraded` /
 * `unknown` / `unconfigured` — and the first-run checklist's own three-word
 * readiness), and a handful of free-form sentences on top of both
 * ("it answered", "stored, unchecked"). `credentialStatus` below is the one
 * place that reconciles every spelling onto this set, so no screen chooses a
 * synonym for a fact one of these five words already has.
 */
export const CREDENTIAL_STATUSES = [
  'not_connected',
  'stored',
  'verified',
  'degraded',
  'failing',
  'unknown',
] as const;

export type CredentialStatus = (typeof CREDENTIAL_STATUSES)[number];

/**
 * Every raw spelling a backend vocabulary uses for one of the five, mapped
 * onto the canonical word.
 *
 * The subtle one is `unknown`: the integration catalogue's `HealthStatus`
 * uses that exact word for "a credential exists and nothing has checked it
 * yet" — which is this vocabulary's `stored`, not its own `unknown`. This
 * module's `unknown` is reserved for the degrade: a spelling nothing here
 * declares, which is what a screen is left holding when the gateway that
 * would say which of the four it actually is cannot be reached.
 */
const CREDENTIAL_STATUS_ALIASES: Readonly<Record<string, CredentialStatus>> = {
  unconfigured: 'not_connected',
  absent: 'not_connected',
  not_connected: 'not_connected',
  configured: 'stored',
  unknown: 'stored',
  stored: 'stored',
  healthy: 'verified',
  verified: 'verified',
  degraded: 'degraded',
  failing: 'failing',
};

/**
 * `value`, translated onto the one credential vocabulary.
 *
 * Never throws and never returns a sixth word: a spelling this mapping does
 * not recognise — a future vendor state, an empty read, a typo — degrades to
 * `'unknown'` rather than inventing one of the other four. FR-001's edge case
 * is exactly this: a chip may say it does not know, and must never guess.
 */
export function credentialStatus(value: string): CredentialStatus {
  return CREDENTIAL_STATUS_ALIASES[value] ?? 'unknown';
}

/** The shapes a status can be drawn as, so colour is never on its own. */
export const SHAPES = [
  'filled-circle',
  'hollow-circle',
  'dimmed-circle',
  'square',
  'rotated-square',
  'triangle',
  'dash',
] as const;

export type Shape = (typeof SHAPES)[number];

/** How one status is presented: its role, its shape, and what it is called. */
export interface StatusPresentation {
  readonly role: SemanticRole;
  readonly shape: Shape;
  readonly label: string;
  /** Whether the mapping recognised it, which decides nothing about how it renders. */
  readonly known: boolean;
}

const DECLARED: Readonly<Record<string, { role: SemanticRole; shape: Shape }>> = {
  // Runs.
  running: { role: 'info', shape: 'rotated-square' },
  // Paused on a human decision — the persistence store's own word for the
  // fact `awaiting_approval` used to spell inconsistently across fixtures.
  // Same role and shape `waiting` drew, because it is the same fact.
  suspended: { role: 'warning', shape: 'triangle' },
  completed: { role: 'success', shape: 'filled-circle' },
  // A tool call's own word for succeeding, not a run's: the persistence
  // store never writes this spelling for where a run is (RUN_STATUSES
  // above does not carry it), but `ToolCallStatus.SUCCEEDED` does, and the
  // transcript's own call badges still read it through this shared table.
  succeeded: { role: 'success', shape: 'filled-circle' },
  failed: { role: 'danger', shape: 'square' },
  cancelled: { role: 'neutral', shape: 'dash' },
  // Nobody knows how far this run got — the process running it is gone,
  // and recording it as a failure would put a conclusion in the history
  // that nothing established. Its own shape, borrowing neither `failed`'s
  // nor `cancelled`'s, for exactly that reason.
  interrupted: { role: 'neutral', shape: 'dimmed-circle' },
  // Resources.
  healthy: { role: 'success', shape: 'filled-circle' },
  degraded: { role: 'warning', shape: 'triangle' },
  unhealthy: { role: 'danger', shape: 'square' },
  unknown: { role: 'neutral', shape: 'hollow-circle' },
  stale: { role: 'neutral', shape: 'dimmed-circle' },
  maintenance: { role: 'info', shape: 'rotated-square' },
  absent: { role: 'neutral', shape: 'dash' },
  // A credential's own state, ahead of anything a live check could say about
  // it. Its own shape — not `absent`'s, so a reader who has learned "dash
  // means nothing is stored" is not asked to know that this is the same
  // dash on a different word.
  unconfigured: { role: 'neutral', shape: 'dash' },
  // Severity. `critical` and `high` are both danger and are told apart by their
  // shape, which is the whole reason a shape is carried at all.
  critical: { role: 'danger', shape: 'square' },
  high: { role: 'danger', shape: 'triangle' },
  medium: { role: 'warning', shape: 'triangle' },
  low: { role: 'info', shape: 'rotated-square' },
  info: { role: 'info', shape: 'hollow-circle' },
  // An incident's state. Every member of the store's own enumeration and
  // nothing else, which `make check-incident-states` proves in both
  // directions. `closed` used to sit here and is not a member: the gateway
  // writes `incident.state.value` verbatim and the route refuses any filter
  // outside the enumeration by name, so every screen comparing against
  // `closed` was comparing against a word that cannot arrive.
  open: { role: 'danger', shape: 'square' },
  investigating: { role: 'info', shape: 'rotated-square' },
  // Waiting on a person, which is the same fact `suspended` carries for a run
  // and is drawn the same way for that reason.
  awaiting_human: { role: 'warning', shape: 'triangle' },
  // A write to production is happening right now. Warning rather than info:
  // this is the only incident state during which the estate is being changed,
  // and its own shape, so it is never mistaken for `investigating` — which is
  // the agent reading rather than the agent acting.
  remediating: { role: 'warning', shape: 'square' },
  // Terminal, and the outcome the product exists to produce.
  resolved: { role: 'success', shape: 'filled-circle' },
  suppressed: { role: 'neutral', shape: 'dimmed-circle' },
  // Terminal with nothing done. Neutral rather than success: an incident a
  // person shut without a fix is not an incident that was solved, and drawing
  // it green is how a deployment's success rate lies.
  closed_without_action: { role: 'neutral', shape: 'dash' },
  // What is waiting on a person, and what happened to it.
  awaiting_approval: { role: 'warning', shape: 'triangle' },
  approval: { role: 'warning', shape: 'triangle' },
  question: { role: 'info', shape: 'hollow-circle' },
  failure: { role: 'danger', shape: 'square' },
  pending: { role: 'warning', shape: 'hollow-circle' },
  approved: { role: 'success', shape: 'filled-circle' },
  rejected: { role: 'danger', shape: 'square' },
  expired: { role: 'neutral', shape: 'dash' },
  // How an investigation ended, where that is not one of the words above.
  // `resolved` is already declared with the incident state it shares, and
  // means the same thing on both. Amber and hollow, as the board draws it: an
  // investigation that reached no root cause is not a failure to be drawn in
  // red, and it is emphatically not a success — it is the case the learning
  // corpus exists to improve on, so it is drawn as something still open.
  inconclusive: { role: 'warning', shape: 'hollow-circle' },
  // How reversible an action is. This is the one an operator reads before
  // pressing something, so it is never carried by colour alone either.
  read_only: { role: 'success', shape: 'filled-circle' },
  reversible: { role: 'warning', shape: 'triangle' },
  irreversible: { role: 'danger', shape: 'square' },
  // States of a thing that has been turned off or fixed in place.
  locked: { role: 'warning', shape: 'triangle' },
  disabled: { role: 'neutral', shape: 'dash' },
  revoked: { role: 'neutral', shape: 'dash' },
  // Whether what is on the screen is arriving. `disconnected` is danger rather
  // than neutral on purpose: a transcript that has stopped updating is a
  // transcript somebody is about to draw a conclusion from.
  connecting: { role: 'info', shape: 'hollow-circle' },
  connected: { role: 'success', shape: 'filled-circle' },
  reconnecting: { role: 'warning', shape: 'rotated-square' },
  idle: { role: 'neutral', shape: 'dimmed-circle' },
  disconnected: { role: 'danger', shape: 'square' },
  // An audit event's own outcome. `failed` is already declared above, shared
  // with runs — the same word means the same thing whichever record it is on.
  allowed: { role: 'success', shape: 'filled-circle' },
  denied: { role: 'danger', shape: 'square' },
  // The credential and verification vocabulary. Its own four shapes rather
  // than reusing `unconfigured`/`healthy`/`degraded` above: those three are
  // the raw words two different backend vocabularies (a resource's health, an
  // integration's health) already speak, and this is the one, translated,
  // canonical set every screen shows instead of them. `stored` gets a shape
  // no other neutral-or-otherwise entry above carries, so it reads as its own
  // fact rather than as a dim copy of `unconfigured` or of `unknown`.
  not_connected: { role: 'neutral', shape: 'dash' },
  stored: { role: 'info', shape: 'dimmed-circle' },
  verified: { role: 'success', shape: 'filled-circle' },
  failing: { role: 'danger', shape: 'square' },
  // A tool's own side effect, worst case, ordered by how hard it is to undo.
  // The two reads change nothing on the estate; the two writes do; `destructive`
  // has no reversible twin at all and is worse than `write_irreversible`, which
  // is why it is the one entry here that reaches `irreversible`'s own shape.
  read: { role: 'success', shape: 'filled-circle' },
  read_sensitive: { role: 'info', shape: 'hollow-circle' },
  write_reversible: { role: 'warning', shape: 'triangle' },
  write_irreversible: { role: 'danger', shape: 'triangle' },
  destructive: { role: 'danger', shape: 'square' },
  // What a governed action would be decided to do, read before anything
  // happens — never what already happened, so this shares no word with an
  // audit event's own `allowed`/`denied` above. `execute` and `simulate` are
  // the same permission class (the deployment would act on its own); `approve`
  // and `propose` both wait on a person; `refuse` is the one this class of
  // action never reaches at all.
  execute: { role: 'danger', shape: 'square' },
  simulate: { role: 'info', shape: 'rotated-square' },
  approve: { role: 'warning', shape: 'triangle' },
  propose: { role: 'warning', shape: 'hollow-circle' },
  refuse: { role: 'neutral', shape: 'dash' },
  // An autonomy posture — what a scope may do without asking. `propose_only`
  // is the safe end and `act_silently` the most autonomous, and the four read
  // distinguishably for exactly the reason severity above does. Declared here
  // for the resolved chip that pairs this with the deployment's own word for
  // it; `Badge` itself never reaches these, because its label is never
  // translated and a posture read as a raw slug is the defect this exists to
  // end.
  propose_only: { role: 'success', shape: 'filled-circle' },
  act_on_low_risk: { role: 'info', shape: 'rotated-square' },
  act_and_report: { role: 'warning', shape: 'triangle' },
  act_silently: { role: 'danger', shape: 'square' },
};

/** Whether `value` is a run status the gateway is known to report. */
export function isRunStatus(value: string): value is RunStatus {
  return (RUN_STATUSES as readonly string[]).includes(value);
}

/** Whether `value` is a resource status the console has a shape for. */
export function isResourceStatus(value: string): value is ResourceStatus {
  return (RESOURCE_STATUSES as readonly string[]).includes(value);
}

/**
 * How `status` is presented.
 *
 * A status the mapping has never heard of is neutral, keeps its own text, and
 * says so in `known` — never blank, and never an error. A provider that invents
 * a state is a provider one version ahead, not a fault.
 */
export function statusPresentation(status: string): StatusPresentation {
  const declared = DECLARED[status];
  if (declared !== undefined) {
    return { role: declared.role, shape: declared.shape, label: status, known: true };
  }
  const trimmed = status.trim();
  return {
    role: 'neutral',
    shape: 'hollow-circle',
    label: trimmed.length > 0 ? trimmed : 'unreported',
    known: false,
  };
}

/** The role `status` is rendered in. */
export function roleFor(status: string): SemanticRole {
  return statusPresentation(status).role;
}

/**
 * Everything an incident may be, in the store's own order.
 *
 * A closed set, in the shape `RUN_STATUSES` already has, and held against
 * `platform.persistence.ports.incident_store.IncidentState` in both directions
 * by `make check-incident-states`. It exists because the alternative had just
 * failed in production: the overview compared `state === 'closed'` against an
 * enumeration with no such member, so the comparison never once matched and
 * every incident the agent had finished was counted as one waiting on a
 * person. A word written at a call site is held against nothing.
 */
export const INCIDENT_STATES = [
  'open',
  'investigating',
  'awaiting_human',
  'remediating',
  'resolved',
  'suppressed',
  'closed_without_action',
] as const;

export type IncidentState = (typeof INCIDENT_STATES)[number];

/** The three the store's own `is_closed` property returns true for. */
const TERMINAL_INCIDENT_STATES: readonly string[] = [
  'resolved',
  'suppressed',
  'closed_without_action',
];

/**
 * The four an incident can still be in, as a listing asks for them.
 *
 * Derived rather than written twice: a second literal is a second thing to
 * forget, which is the whole shape of the defect above.
 */
export const LIVE_INCIDENT_STATES: readonly string[] = INCIDENT_STATES.filter(
  (state) => !TERMINAL_INCIDENT_STATES.includes(state),
);

/**
 * The live states that are a person's problem.
 *
 * `open` because nothing has picked it up yet, and `awaiting_human` because
 * the deployment stopped and asked. Those two, and no others.
 *
 * This is the distinction the overview never drew, and not drawing it is why
 * its headline was an indictment: every incident that had not ended went into
 * "N items need you", the ones the agent had picked up and was actively
 * working included. A product whose claim is that it investigates without you
 * was using its first screen to count how much it had left undone.
 */
export const HUMAN_INCIDENT_STATES: readonly string[] = ['open', 'awaiting_human'];

/**
 * The live states the agent is holding — reading, or writing to the estate.
 *
 * These belong on the overview too, and prominently. They are the answer to
 * "is it working", which is a different question from "does it need me" and
 * the one an operator actually opens the console asking.
 */
export const AGENT_INCIDENT_STATES: readonly string[] = LIVE_INCIDENT_STATES.filter(
  (state) => !HUMAN_INCIDENT_STATES.includes(state),
);

/** Whether an incident in `state` has ended and needs nobody. */
export function isTerminalIncident(state: string): boolean {
  return TERMINAL_INCIDENT_STATES.includes(state);
}

/** Whether an incident in `state` is blocked on a person rather than on the agent. */
export function needsAPerson(state: string): boolean {
  return HUMAN_INCIDENT_STATES.includes(state);
}

/** Whether a run in `status` has finished and will not change again. */
export function isSettled(status: string): boolean {
  return SETTLED_RUN_STATUSES.includes(status);
}

/**
 * Whether a run in `status` is live: steerable, watchable, worth a stream.
 *
 * Affirmative rather than "not settled" — the decision this replaces treated
 * every status neither list had a word for as live by default, which is how
 * a run whose status the console had never seen ended up offered a stop
 * button. A status this function has not declared is neither live nor
 * settled; it is drawn as the unknown word it is, and offered nothing.
 */
export function isLiveRun(status: string): boolean {
  return LIVE_RUN_STATUSES.includes(status);
}
