import type { ReactNode } from 'react';

import { cx } from '@/design/cx';
import {
  credentialStatus,
  type CredentialStatus,
  type Shape,
  statusPresentation,
} from '@/design/status';
import type { SemanticRole } from '@/design/tokens';
import type { MessageKey } from '@/i18n/en';
import { message, type Locale } from '@/i18n/messages';

/**
 * Status, drawn twice.
 *
 * Every state in this console carries a label *and* a shape. Roughly one man in
 * twelve cannot separate this palette's success from its danger, and a console
 * whose only difference between "healthy" and "unhealthy" is a hue is a console
 * those operators are reading at three in the morning without the information.
 *
 * The shape is not decoration on top of the colour. It is the second carrier,
 * and the two states that share the neutral role — unknown and stale — carry
 * different ones for that reason, which is asserted rather than assumed.
 */

/** The tint, foreground and boundary each role wears. */
const ROLE_SKIN: Readonly<Record<SemanticRole, string>> = {
  success: 'bg-success-bg text-success border-success',
  warning: 'bg-warning-bg text-warning border-warning',
  danger: 'bg-danger-bg text-danger border-danger',
  info: 'bg-info-bg text-info border-info',
  neutral: 'bg-neutral-bg text-neutral border-border-strong',
};

/** The fill each role gives a shape. */
const ROLE_FILL: Readonly<Record<SemanticRole, string>> = {
  success: 'bg-success border-success',
  warning: 'bg-warning border-warning',
  danger: 'bg-danger border-danger',
  info: 'bg-info border-info',
  neutral: 'bg-neutral border-neutral',
};

/**
 * How each shape is drawn.
 *
 * Sizes come from the icon scale rather than from the spacing scale: these are
 * glyphs sitting on a text baseline, and a glyph that grew with the padding
 * would drift away from the letters beside it.
 */
const SHAPE_CLASS: Readonly<Record<Shape, string>> = {
  'filled-circle': 'icon-inline rounded-full',
  'hollow-circle': 'icon-inline rounded-full bg-transparent edge-ring',
  'dimmed-circle': 'icon-inline rounded-full opacity-50',
  square: 'icon-inline',
  'rotated-square': 'icon-inline rotate-45',
  triangle: 'icon-inline clip-triangle',
  dash: 'icon-inline h-0 edge-ring rounded-full',
};

export interface ShapeMarkProps {
  readonly shape: Shape;
  readonly role: SemanticRole;
  readonly className?: string;
}

/** The glyph itself, which is what carries the meaning when colour cannot. */
function ShapeMark({ shape, role, className }: ShapeMarkProps): ReactNode {
  return (
    <span
      data-shape={shape}
      aria-hidden="true"
      className={cx(
        SHAPE_CLASS[shape],
        ROLE_FILL[role],
        'edge inline-block shrink-0',
        className,
      )}
    />
  );
}

export interface BadgeProps {
  /** The status as the API reported it. Never translated, never trimmed away. */
  readonly status: string;
  readonly className?: string;
}

/**
 * A status, as a chip: shape, then the word.
 *
 * The word is always the status the API sent. A status the console has never
 * heard of gets the neutral role and its own text — never blank, never an
 * error, because a provider one version ahead is not a fault.
 */
export function Badge({ status, className }: BadgeProps): ReactNode {
  const presented = statusPresentation(status);
  return (
    <span
      data-role={presented.role}
      data-known={presented.known}
      className={cx(
        'inline-flex items-center gap-1 px-2 rounded-1 edge text-micro uppercase',
        ROLE_SKIN[presented.role],
        className,
      )}
    >
      <ShapeMark shape={presented.shape} role={presented.role} />
      {presented.label}
    </span>
  );
}

export interface StatusDotProps {
  readonly status: string;
  /**
   * Whether this dot is the only thing saying what the status is.
   *
   * Normally it is not — a label sits beside it, and a dot that announced
   * itself would say "healthy" twice on every row. When a dense table really
   * does show nothing else, this gives the shape an accessible name.
   */
  readonly standalone?: boolean;
  readonly className?: string;
}

/** The smallest status there is: one shape, in one role's colour. */
export function StatusDot({
  status,
  standalone = false,
  className,
}: StatusDotProps): ReactNode {
  const presented = statusPresentation(status);
  if (!standalone) {
    return (
      <ShapeMark
        shape={presented.shape}
        role={presented.role}
        className={cx('', className)}
      />
    );
  }
  return (
    <span
      role="img"
      aria-label={presented.label}
      data-shape={presented.shape}
      data-role={presented.role}
      className={cx(
        SHAPE_CLASS[presented.shape],
        ROLE_FILL[presented.role],
        'edge inline-block shrink-0',
        className,
      )}
    />
  );
}

/** Where each of the five canonical credential words is declared. */
const CREDENTIAL_STATUS_LABEL: Readonly<Record<CredentialStatus, MessageKey>> = {
  not_connected: 'status.credential.notConnected',
  stored: 'status.credential.stored',
  verified: 'status.credential.verified',
  degraded: 'status.credential.degraded',
  failing: 'status.credential.failing',
  unknown: 'status.credential.unknown',
};

export interface StatusChipProps {
  readonly locale: Locale;
  /** The status as any surface reports it — any spelling `credentialStatus` recognises. */
  readonly status: string;
  readonly className?: string;
  readonly 'data-testid'?: string;
}

/**
 * A credential's own state, or what the last check against it found — the one
 * chip every screen renders it as, in the viewer's language.
 *
 * Unlike `Badge`, which shows the raw word a status arrives as (and is right
 * to, for a run's status or a resource's health), this never shows a raw
 * backend spelling. `status` is translated onto one of the five canonical
 * words before anything is rendered, so "healthy", "configured" and
 * "verified" — three different vocabularies' way of saying the same thing —
 * draw as the identical chip. The degrade carries a tooltip explaining why,
 * because "Unknown" alone does not say whether that is the credential's own
 * state or a gateway this reader's screen could not reach.
 */
export function StatusChip({
  locale,
  status,
  className,
  'data-testid': testId,
}: StatusChipProps): ReactNode {
  const canonical = credentialStatus(status);
  const presented = statusPresentation(canonical);
  const label = message(locale, CREDENTIAL_STATUS_LABEL[canonical]);
  const explain =
    canonical === 'unknown'
      ? message(locale, 'status.credential.unknown.explain')
      : undefined;
  return (
    <span
      data-role={presented.role}
      data-credential-status={canonical}
      data-testid={testId}
      title={explain}
      className={cx(
        'inline-flex items-center gap-1 px-2 rounded-1 edge text-micro',
        ROLE_SKIN[presented.role],
        className,
      )}
    >
      <ShapeMark shape={presented.shape} role={presented.role} />
      {label}
    </span>
  );
}

/**
 * A chip whose label and role are already resolved by the caller, never a
 * value the API sent for transport — the raw material `Badge` is right to
 * print for a run or a resource, but wrong for a fact about a person or a
 * group of credentials, which has no business being shown to a viewer in
 * `SCREAMING_SNAKE_CASE` or a language it does not read.
 */
interface ResolvedChipProps {
  readonly role: SemanticRole;
  readonly shape: Shape;
  readonly label: string;
  readonly testId: string;
  readonly className?: string | undefined;
}

function ResolvedChip({
  role,
  shape,
  label,
  testId,
  className,
}: ResolvedChipProps): ReactNode {
  return (
    <span
      data-testid={testId}
      data-role={role}
      className={cx(
        'inline-flex items-center gap-1 px-2 rounded-1 edge text-micro',
        ROLE_SKIN[role],
        className,
      )}
    >
      <ShapeMark shape={shape} role={role} />
      {label}
    </span>
  );
}

/** The two ways a principal is created, read off `/identity/principals`'s own `kind`. */
const PRINCIPAL_KIND_LABEL: Readonly<Record<string, MessageKey>> = {
  user: 'principal.kind.person',
  service_account: 'principal.kind.serviceAccount',
};

export interface PrincipalKindChipProps {
  readonly locale: Locale;
  /** `kind` as `/identity/principals` reports it — `'user'` or `'service_account'`. */
  readonly kind: string;
  readonly className?: string;
}

/**
 * A principal's own kind, in the viewer's language — never `SERVICE_ACCOUNT`
 * shouted in the transport's own case, and never `user` mistaken for a role.
 *
 * A kind this catalogue has not declared a label for still shows its own raw
 * word rather than nothing: the same rule every status chip in this module
 * holds, because a deployment one version ahead is not a rendering fault.
 */
export function PrincipalKindChip({
  locale,
  kind,
  className,
}: PrincipalKindChipProps): ReactNode {
  const key = PRINCIPAL_KIND_LABEL[kind];
  const label = key === undefined ? kind : message(locale, key);
  return (
    <ResolvedChip
      role="neutral"
      shape="hollow-circle"
      label={label}
      testId="principal-kind"
      className={className}
    />
  );
}

export interface AccountStateChipProps {
  readonly locale: Locale;
  /** Whether this principal may currently sign in — `/identity/principals`'s `is_active`. */
  readonly active: boolean;
  readonly className?: string;
}

/**
 * Whether a principal's own account may sign in — account vocabulary, never
 * a resource's health. `HEALTHY` never describes a person; `Active` and
 * `Suspended` are the words this console uses for one instead.
 */
export function AccountStateChip({
  locale,
  active,
  className,
}: AccountStateChipProps): ReactNode {
  return (
    <ResolvedChip
      role={active ? 'success' : 'neutral'}
      shape={active ? 'filled-circle' : 'dash'}
      label={message(
        locale,
        active ? 'principal.state.active' : 'principal.state.suspended',
      )}
      testId="principal-state"
      className={className}
    />
  );
}

export interface TokenGroupStateChipProps {
  readonly locale: Locale;
  /** Whether any token in this group has a recorded `last_used_at`. */
  readonly everUsed: boolean;
  readonly className?: string;
}

/**
 * What a group of machine tokens has actually done — in use, or never used —
 * rather than the literal, fixed `healthy` this chip used to be handed
 * regardless of the group it described.
 */
export function TokenGroupStateChip({
  locale,
  everUsed,
  className,
}: TokenGroupStateChipProps): ReactNode {
  return (
    <ResolvedChip
      role={everUsed ? 'success' : 'neutral'}
      shape={everUsed ? 'filled-circle' : 'dash'}
      label={message(
        locale,
        everUsed ? 'tokenGroup.state.inUse' : 'settings.machineTokens.neverUsed',
      )}
      testId="token-group-state"
      className={className}
    />
  );
}

export interface ScheduleStateChipProps {
  readonly locale: Locale;
  /** Whether this schedule currently runs — `/v1/schedules`'s own `enabled`. */
  readonly enabled: boolean;
  readonly className?: string;
}

/**
 * Whether a schedule currently fires on its clock — never a resource's
 * health. A schedule an operator turned off is disabled, not `HEALTHY`'s
 * opposite; the same distinction `AccountStateChip` draws for a person's own
 * account and `TokenGroupStateChip` draws for a group of machine tokens.
 */
export function ScheduleStateChip({
  locale,
  enabled,
  className,
}: ScheduleStateChipProps): ReactNode {
  return (
    <ResolvedChip
      role={enabled ? 'success' : 'neutral'}
      shape={enabled ? 'filled-circle' : 'dash'}
      label={message(
        locale,
        enabled ? 'schedule.state.enabled' : 'schedule.state.disabled',
      )}
      testId="schedule-state"
      className={className}
    />
  );
}

export interface SsoStateChipProps {
  readonly locale: Locale;
  /** Whether this provider is currently the way people sign in. */
  readonly active: boolean;
  readonly className?: string;
}

/**
 * Whether single sign-on is currently the way in — never a resource's
 * health. A provider that has not been made active is not "unhealthy"; it is
 * simply not, yet, how anyone signs in. The finer distinction (tested but
 * not activated, not yet tested, not configured) stays the sentence already
 * beside this chip — this only ever carries the same two-way fact the chip
 * itself always has.
 */
export function SsoStateChip({
  locale,
  active,
  className,
}: SsoStateChipProps): ReactNode {
  return (
    <ResolvedChip
      role={active ? 'success' : 'neutral'}
      shape={active ? 'filled-circle' : 'dash'}
      label={message(locale, active ? 'sso.state.active' : 'sso.state.inactive')}
      testId="sso-state-chip"
      className={className}
    />
  );
}

export interface DetectorStateChipProps {
  readonly locale: Locale;
  /** Whether this detector currently evaluates its subjects — `/v1/detectors`'s own `enabled`. */
  readonly enabled: boolean;
  readonly className?: string;
}

/**
 * Whether a detector is currently evaluating what it watches — never a
 * resource's health. The column this chip sits under is itself titled
 * "Enabled", so this renders exactly that word rather than the raw health
 * word `healthy` a detector's own record has no business carrying: turning a
 * detector off is an operator's decision, not a degrade.
 */
export function DetectorStateChip({
  locale,
  enabled,
  className,
}: DetectorStateChipProps): ReactNode {
  return (
    <ResolvedChip
      role={enabled ? 'success' : 'neutral'}
      shape={enabled ? 'filled-circle' : 'dash'}
      label={message(
        locale,
        enabled ? 'detectors.state.enabled' : 'detectors.state.disabled',
      )}
      testId="detector-state"
      className={className}
    />
  );
}

export interface SpecialistStateChipProps {
  readonly locale: Locale;
  /** Whether the configuration still dispatches this specialist. */
  readonly enabled: boolean;
  readonly className?: string;
}

/**
 * Whether a team's own configuration still dispatches this specialist —
 * never a resource's health. The hierarchy graph beside this list already
 * draws a specialist switched off as "disabled"; this chip names the same
 * fact in the same word, in the row the graph's own accessible copy sits
 * next to.
 */
export function SpecialistStateChip({
  locale,
  enabled,
  className,
}: SpecialistStateChipProps): ReactNode {
  return (
    <ResolvedChip
      role={enabled ? 'success' : 'neutral'}
      shape={enabled ? 'filled-circle' : 'dash'}
      label={message(
        locale,
        enabled
          ? 'agent.specialists.state.enabled'
          : 'agent.specialists.state.disabled',
      )}
      testId="specialist-state"
      className={className}
    />
  );
}

export interface BridgedServerStateChipProps {
  readonly locale: Locale;
  /** Whether the configuration still registers this outside server. */
  readonly enabled: boolean;
  readonly className?: string;
}

/**
 * Whether a team's own configuration still registers a bridged server —
 * never a resource's health, and never the same fact as whether the server
 * answered when reached (that is what the tool rows beside it, dimmed with
 * their own reason, already say). A server an operator turned off is
 * disabled, not `HEALTHY`'s opposite.
 */
export function BridgedServerStateChip({
  locale,
  enabled,
  className,
}: BridgedServerStateChipProps): ReactNode {
  return (
    <ResolvedChip
      role={enabled ? 'success' : 'neutral'}
      shape={enabled ? 'filled-circle' : 'dash'}
      label={message(
        locale,
        enabled ? 'agent.bridged.state.enabled' : 'agent.bridged.state.disabled',
      )}
      testId="bridged-server-state"
      className={className}
    />
  );
}

export interface CapabilityAvailabilityChipProps {
  readonly locale: Locale;
  /** Whether this node's own catalogue currently lets this capability run. */
  readonly available: boolean;
  readonly className?: string;
}

/**
 * Whether this node's catalogue currently lets a tool run — never a
 * resource's health. The column this chip sits under already asks "Enabled
 * here?", so this renders exactly that word; a blocked tool never reaches
 * this chip at all — what blocks it, structured and where relevant linked to
 * the integration that would fix it, is what the same cell renders instead.
 */
export function CapabilityAvailabilityChip({
  locale,
  available,
  className,
}: CapabilityAvailabilityChipProps): ReactNode {
  return (
    <ResolvedChip
      role={available ? 'success' : 'neutral'}
      shape={available ? 'filled-circle' : 'dash'}
      label={message(
        locale,
        available ? 'catalogue.state.enabled' : 'catalogue.state.disabled',
      )}
      testId="capability-available"
      className={className}
    />
  );
}

export interface CheckChipProps {
  readonly name: string;
  /** The preflight's own vocabulary for one check: passed, degraded, failed, or skipped. */
  readonly status: 'passed' | 'degraded' | 'failed' | 'skipped';
  readonly className?: string;
  readonly 'data-testid'?: string;
}

/** The role a preflight check's own status carries — never the credential vocabulary's. */
const CHECK_ROLE: Readonly<Record<CheckChipProps['status'], SemanticRole>> = {
  passed: 'success',
  degraded: 'warning',
  failed: 'danger',
  skipped: 'neutral',
};

/**
 * One preflight check, named — not the five-word credential vocabulary.
 *
 * `StatusChip` always shows one of the five canonical words; a check's own
 * name ("Tool calling", "Structured output") is a different kind of label
 * that still has to carry a role rather than a literal colour, which is what
 * this borrows `ROLE_SKIN` and `ShapeMark` for directly.
 */
export function CheckChip({
  name,
  status,
  className,
  'data-testid': testId,
}: CheckChipProps): ReactNode {
  const role = CHECK_ROLE[status];
  return (
    <span
      data-role={role}
      data-check-status={status}
      data-testid={testId}
      className={cx(
        'inline-flex items-center gap-1 px-2 rounded-1 edge text-micro',
        ROLE_SKIN[role],
        className,
      )}
    >
      <ShapeMark
        shape={
          role === 'success'
            ? 'filled-circle'
            : role === 'warning'
              ? 'triangle'
              : role === 'danger'
                ? 'square'
                : 'dash'
        }
        role={role}
      />
      {name}
    </span>
  );
}
