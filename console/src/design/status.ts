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

/** The statuses the gateway reports for a run. */
export const RUN_STATUSES = [
  'queued',
  'running',
  'waiting',
  'succeeded',
  'failed',
  'cancelled',
] as const;

export type RunStatus = (typeof RUN_STATUSES)[number];

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
  'closed',
  'suppressed',
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
  queued: { role: 'neutral', shape: 'hollow-circle' },
  running: { role: 'info', shape: 'rotated-square' },
  waiting: { role: 'warning', shape: 'triangle' },
  succeeded: { role: 'success', shape: 'filled-circle' },
  failed: { role: 'danger', shape: 'square' },
  cancelled: { role: 'neutral', shape: 'dash' },
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
  // An incident's state.
  open: { role: 'danger', shape: 'square' },
  investigating: { role: 'info', shape: 'rotated-square' },
  closed: { role: 'success', shape: 'filled-circle' },
  suppressed: { role: 'neutral', shape: 'dimmed-circle' },
  // What is waiting on a person, and what happened to it.
  awaiting_approval: { role: 'warning', shape: 'triangle' },
  approval: { role: 'warning', shape: 'triangle' },
  question: { role: 'info', shape: 'hollow-circle' },
  failure: { role: 'danger', shape: 'square' },
  pending: { role: 'warning', shape: 'hollow-circle' },
  approved: { role: 'success', shape: 'filled-circle' },
  rejected: { role: 'danger', shape: 'square' },
  expired: { role: 'neutral', shape: 'dash' },
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

/** Whether a run in `status` has finished and will not change again. */
export function isSettled(status: string): boolean {
  return status === 'succeeded' || status === 'failed' || status === 'cancelled';
}
