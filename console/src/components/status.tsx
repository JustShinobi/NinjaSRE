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

/**
 * The shape every status chip is drawn in.
 *
 * One carrier of the signal, not three. This used to be a stroke *and* a tint
 * *and* coloured text, wrapped around eleven-pixel capitals tracked out to
 * 0.06em — the vocabulary an administrative console used a decade ago, and a
 * measurable cost besides: a reader scans by word shape, and capitals flatten
 * every word to the same rectangle. Fifty of them in a column stopped being
 * read at all.
 *
 * Every value here is a step that already existed. `rounded-full` is a
 * declared radius rather than a written number, `text-meta` is the
 * twelve-pixel step at regular weight, and the box is padding rather than a
 * height nobody could derive.
 *
 * Exported because a chip outside this module is still a chip. The frame's
 * freshness indicator was written with `h-control` in place of `py-1` and so
 * rendered with no vertical padding at all — visibly thinner than every other
 * chip in the product, on the one chip that is on every screen. Naming the
 * geometry once is what makes that a thing a test can hold rather than a thing
 * a reviewer has to notice at four chips' distance.
 */
export const CHIP_SHAPE =
  'inline-flex items-center gap-2 px-2 py-1 rounded-full text-meta';

/**
 * The tint and foreground each role wears.
 *
 * The pair is `${role}` on `${role}-bg`, which the contrast proof already
 * measures at 4.5:1 in both themes — so losing the border costs no legibility
 * and WCAG 1.4.11 does not apply to a chip that is not a control.
 *
 * Neutral is the one exception and keeps a boundary. Its tint is the page
 * ground in the dark theme, so an unbordered neutral chip on a raised card
 * reads as a hole punched through it rather than as an object on it.
 */
const ROLE_SKIN: Readonly<Record<SemanticRole, string>> = {
  success: 'bg-success-bg text-success',
  warning: 'bg-warning-bg text-warning',
  danger: 'bg-danger-bg text-danger',
  info: 'bg-info-bg text-info',
  neutral: 'bg-neutral-bg text-neutral edge border-border',
};

/** The fill each role gives a solid shape. */
const ROLE_FILL: Readonly<Record<SemanticRole, string>> = {
  success: 'bg-success border-success',
  warning: 'bg-warning border-warning',
  danger: 'bg-danger border-danger',
  info: 'bg-info border-info',
  neutral: 'bg-neutral border-neutral',
};

/**
 * The ring each role gives a hollow shape, and no fill at all.
 *
 * A table of its own rather than `ROLE_FILL` with `bg-transparent` added
 * beside it, because that arrangement did not work and passed every test
 * anyway. Two background utilities on one element are not decided by the order
 * of the class attribute; they are decided by the order of the generated
 * stylesheet, which Tailwind writes alphabetically. `bg-transparent` therefore
 * beat `bg-danger`, `bg-info`, `bg-neutral` and `bg-success`, and lost to
 * `bg-warning` — so a warning hollow circle rendered solid, and `pending` and
 * `propose` became the same filled disc as `completed` with only a hue between
 * them. On the one pair of statuses this whole module exists to keep apart.
 *
 * Splitting the two tables means the mark never carries two backgrounds, so
 * there is no ordering left to lose. That property is asserted directly, and
 * it survives a role named alphabetically after `transparent` — which the
 * previous arrangement would have silently broken all over again.
 */
const ROLE_RING: Readonly<Record<SemanticRole, string>> = {
  success: 'bg-transparent border-success',
  warning: 'bg-transparent border-warning',
  danger: 'bg-transparent border-danger',
  info: 'bg-transparent border-info',
  neutral: 'bg-transparent border-neutral',
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
  'hollow-circle': 'icon-inline rounded-full edge-ring',
  'dimmed-circle': 'icon-inline rounded-full opacity-50',
  square: 'icon-inline',
  'rotated-square': 'icon-inline rotate-45',
  triangle: 'icon-inline clip-triangle',
  dash: 'icon-inline h-0 edge-ring rounded-full',
};

/**
 * The shapes drawn as an outline, which are the ones that take the ring.
 *
 * `dash` is deliberately not one of them: its box has no height, so the fill
 * has nothing to paint and the border is the whole of the mark either way.
 * Listing it here would change nothing on screen and would claim a difference
 * that is not there.
 */
const HOLLOW_SHAPES: readonly Shape[] = ['hollow-circle'];

export interface ShapeMarkProps {
  readonly shape: Shape;
  readonly role: SemanticRole;
  /**
   * What to call the mark when it is the only thing saying what the status is.
   *
   * Absent for the ordinary case, where a word sits beside it and a mark that
   * announced itself would say "healthy" twice on every row.
   */
  readonly name?: string;
  readonly className?: string;
}

/** The glyph itself, which is what carries the meaning when colour cannot. */
function ShapeMark({ shape, role, name, className }: ShapeMarkProps): ReactNode {
  return (
    <span
      data-shape={shape}
      {...(name === undefined
        ? // Decorative, because a word is sitting next to it.
          { 'aria-hidden': true as const }
        : // The only thing saying what the status is, so it is named — and it
          // carries the role, which is what a suite reads when the mark is
          // standing on its own rather than inside a chip that already has one.
          { role: 'img', 'aria-label': name, 'data-role': role })}
      className={cx(
        SHAPE_CLASS[shape],
        HOLLOW_SHAPES.includes(shape) ? ROLE_RING[role] : ROLE_FILL[role],
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
        CHIP_SHAPE,
        // The one chip carrying a word the deployment wrote rather than one
        // this console chose, so it is the one that needs casing at all.
        'capitalize',
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
  // The same mark, named. Composed by `ShapeMark` rather than beside it: this
  // branch used to spell the class list out a second time, which is how the two
  // copies would eventually disagree about how a shape is drawn — and one of
  // them would be the copy nobody looked at.
  return (
    <ShapeMark
      shape={presented.shape}
      role={presented.role}
      name={presented.label}
      className={cx('', className)}
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
      className={cx(CHIP_SHAPE, ROLE_SKIN[presented.role], className)}
    >
      <ShapeMark shape={presented.shape} role={presented.role} />
      {label}
    </span>
  );
}

/**
 * A chip whose label and role are already resolved by the caller, never a
 * value the API sent for transport — the raw material `Badge` is right to
 * print for a run or a resource, but wrong for a fact about a person, a
 * group of credentials, or an autonomy posture, none of which has any
 * business being shown to a viewer in `SCREAMING_SNAKE_CASE` or a language
 * it does not read.
 *
 * Exported for a caller that already has both halves — a role and shape from
 * `statusPresentation`, a label from its own translated vocabulary — and
 * needs nothing else this module can name for it. `postures.ts` is exactly
 * this: the slug decides the role and shape, and the deployment's own word,
 * translated, decides the label, and the two never travel through `Badge`
 * together.
 */
export interface ResolvedChipProps {
  readonly role: SemanticRole;
  readonly shape: Shape;
  readonly label: string;
  readonly testId: string;
  readonly className?: string | undefined;
  /**
   * What an unknown or otherwise unresolved state names as its own
   * explanation — the same tooltip technique `StatusChip` already uses for
   * its own `unknown` word, offered here for a chip whose label the caller
   * resolves itself.
   */
  readonly title?: string | undefined;
}

export function ResolvedChip({
  role,
  shape,
  label,
  testId,
  className,
  title,
}: ResolvedChipProps): ReactNode {
  return (
    <span
      data-testid={testId}
      data-role={role}
      {...(title === undefined ? {} : { title })}
      className={cx(CHIP_SHAPE, ROLE_SKIN[role], className)}
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

/** The five side-effect levels, least to most consequential. */
const SIDE_EFFECT_LEVELS = [
  'read',
  'read_sensitive',
  'write_reversible',
  'write_irreversible',
  'destructive',
] as const;

type SideEffectLevel = (typeof SIDE_EFFECT_LEVELS)[number];

/** Which role and shape each level carries. Escalating, and never colour alone. */
const SIDE_EFFECT: Readonly<
  Record<SideEffectLevel, { readonly role: SemanticRole; readonly shape: Shape }>
> = {
  read: { role: 'neutral', shape: 'filled-circle' },
  read_sensitive: { role: 'info', shape: 'hollow-circle' },
  write_reversible: { role: 'warning', shape: 'rotated-square' },
  write_irreversible: { role: 'danger', shape: 'triangle' },
  destructive: { role: 'danger', shape: 'square' },
};

/** The short label each level wears in a chip. */
const SIDE_EFFECT_CHIP: Readonly<Record<SideEffectLevel, MessageKey>> = {
  read: 'sideEffect.chip.read',
  read_sensitive: 'sideEffect.chip.read_sensitive',
  write_reversible: 'sideEffect.chip.write_reversible',
  write_irreversible: 'sideEffect.chip.write_irreversible',
  destructive: 'sideEffect.chip.destructive',
};

/** The sentence each level carries as its explanation. */
const SIDE_EFFECT_SENTENCE: Readonly<Record<SideEffectLevel, MessageKey>> = {
  read: 'sideEffect.level.read',
  read_sensitive: 'sideEffect.level.read_sensitive',
  write_reversible: 'sideEffect.level.write_reversible',
  write_irreversible: 'sideEffect.level.write_irreversible',
  destructive: 'sideEffect.level.destructive',
};

export interface SideEffectChipProps {
  readonly locale: Locale;
  /** The level as the catalogue declares it. */
  readonly level: string;
  readonly className?: string;
}

/**
 * What a capability does to the estate, in words rather than in its spelling.
 *
 * This went through `Badge` for a year, which capitalises the first letter of
 * whatever the API sent and prints the rest — so the column read
 * `Write_reversible` and `Read_sensitive`: neither an identifier a reader could
 * paste anywhere nor a phrase in any language. `Badge` is right for a run's or
 * a resource's status, where a provider one version ahead may invent a word
 * this console has never heard of and printing it verbatim is the only honest
 * move. A side-effect level is not that: it is a closed set this console has
 * carried full sentences for since the guardrails shipped, and it was the one
 * place those sentences were not being used.
 *
 * The sentence stays, as the chip's own explanation. A level the catalogue
 * invents still falls through to its own spelling rather than to a blank.
 */
export function SideEffectChip({
  locale,
  level,
  className,
}: SideEffectChipProps): ReactNode {
  const known = (SIDE_EFFECT_LEVELS as readonly string[]).includes(level)
    ? (level as SideEffectLevel)
    : undefined;
  if (known === undefined) {
    return <Badge status={level} {...(className === undefined ? {} : { className })} />;
  }
  return (
    <ResolvedChip
      role={SIDE_EFFECT[known].role}
      shape={SIDE_EFFECT[known].shape}
      label={message(locale, SIDE_EFFECT_CHIP[known])}
      title={message(locale, SIDE_EFFECT_SENTENCE[known])}
      testId="capability-side-effect"
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
      className={cx(CHIP_SHAPE, ROLE_SKIN[role], className)}
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
