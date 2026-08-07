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
