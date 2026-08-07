/**
 * The mapping from a run's status to the semantic role a screen renders it in.
 *
 * Nothing maps a status to a colour. A status maps to a role, and a role maps
 * to a token pair, so two screens cannot disagree about what "failed" looks
 * like because neither of them decides. The token half arrives with the design
 * system; this is the half that exists as soon as there is anything to render.
 */

export const ROLES = ['success', 'warning', 'danger', 'info', 'neutral'] as const;

export type Role = (typeof ROLES)[number];

/**
 * The statuses the gateway reports for a run.
 *
 * Kept as a list rather than inferred from the generated client: the client is
 * regenerated from the API document, and a status disappearing from it should
 * fail this module's tests rather than silently narrow a union.
 */
export const RUN_STATUSES = [
  'queued',
  'running',
  'waiting',
  'succeeded',
  'failed',
  'cancelled',
] as const;

export type RunStatus = (typeof RUN_STATUSES)[number];

const ROLE_OF: Readonly<Record<RunStatus, Role>> = {
  queued: 'neutral',
  running: 'info',
  waiting: 'warning',
  succeeded: 'success',
  failed: 'danger',
  cancelled: 'neutral',
};

/** Whether `value` is a status the gateway is known to report. */
export function isRunStatus(value: string): value is RunStatus {
  return (RUN_STATUSES as readonly string[]).includes(value);
}

/**
 * The role `status` is rendered in.
 *
 * An unrecognised status is neutral rather than an error: a gateway one version
 * ahead of the console must not blank a screen, and a status nobody has a
 * colour for is exactly the thing "neutral" is for.
 */
export function roleFor(status: string): Role {
  return isRunStatus(status) ? ROLE_OF[status] : 'neutral';
}

/** Whether a run in `status` has finished and will not change again. */
export function isSettled(status: string): boolean {
  return status === 'succeeded' || status === 'failed' || status === 'cancelled';
}
