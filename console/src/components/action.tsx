import NextLink from 'next/link';
import type { ButtonHTMLAttributes, ReactNode } from 'react';

import { cx } from '@/design/cx';
import { ArrowRightIcon } from '@/design/icons';

/**
 * The three ways the console asks somebody to do something.
 *
 * Weight follows consequence, which is the third design principle and the one
 * that decides how these look. The destructive variant is the heaviest thing in
 * the library, and it is heavy in two carriers rather than one: it is red, and
 * it says so in its accessible name. Eight per cent of men cannot tell this
 * palette's danger from its accent, and "the button was red" is not a defence
 * anybody would accept after a recovery point was deleted.
 */

/** Every state a control declares, and therefore every state the gallery shows. */
export const CONTROL_STATES = [
  'default',
  'hover',
  'active',
  'focus',
  'disabled',
  'loading',
  'error',
] as const;

export type ControlState = (typeof CONTROL_STATES)[number];

export const BUTTON_VARIANTS = [
  'primary',
  'secondary',
  'quiet',
  'destructive',
] as const;

export type ButtonVariant = (typeof BUTTON_VARIANTS)[number];

/**
 * Geometry, shared by every variant and every state.
 *
 * One string, used by all of them, is what makes "no layout shift between
 * states" a property of the code rather than a thing somebody checks. A state
 * may only add colour.
 */
export const CONTROL_SHAPE =
  'inline-flex items-center justify-center gap-2 h-control px-3 rounded-2 edge text-body font-sans';

export const VARIANT_SKIN: Readonly<Record<ButtonVariant, string>> = {
  primary: 'bg-accent text-on-accent border-accent hover:opacity-90 motion-hover',
  secondary: 'bg-surface text-text border-border-strong hover:bg-hover motion-hover',
  quiet: 'bg-transparent text-muted border-transparent hover:bg-hover motion-hover',
  // Tinted, not filled. The board draws the destructive control as a ground of
  // `danger-bg` carrying `danger` text, which is the same grammar every other
  // tinted thing here already speaks — a status chip and an inline callout both
  // write it. Filling it inverted the two: the ground took the text's colour and
  // the text took the ground's, which reads as a primary button that happens to
  // be red rather than as the one control that needs a second thought.
  destructive: 'bg-danger-bg text-danger border-danger hover:bg-hover motion-hover',
};

/** What a forced state looks like, for the gallery. Colour only, never a box. */
export const STATE_SKIN: Readonly<Record<ControlState, string>> = {
  default: '',
  hover: 'opacity-90',
  active: 'opacity-80',
  focus: 'outline-accent',
  disabled: 'opacity-50 cursor-not-allowed',
  loading: 'opacity-70 cursor-progress',
  error: 'border-danger text-danger',
};

export interface ButtonProps extends Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  'className' | 'disabled'
> {
  readonly variant?: ButtonVariant;
  readonly state?: ControlState;
  readonly children: ReactNode;
}

/**
 * A pressable control.
 *
 * `state` is how the gallery renders every state without a pointer; a screen
 * passes `default` and lets the browser's own pseudo-classes do the rest. The
 * two states that mean "do not press me" — disabled and loading — actually
 * disable the control rather than only looking like it, because a control that
 * looks unavailable and fires is worse than one that does neither.
 */
export function Button({
  variant = 'secondary',
  state = 'default',
  children,
  ...rest
}: ButtonProps): ReactNode {
  const inert = state === 'disabled' || state === 'loading';
  return (
    <button
      type="button"
      {...rest}
      data-variant={variant}
      data-state={state}
      disabled={inert}
      aria-busy={state === 'loading' ? true : undefined}
      className={cx(CONTROL_SHAPE, VARIANT_SKIN[variant], STATE_SKIN[state])}
    >
      {children}
      {variant === 'destructive' ? (
        // Not decoration. This is the second carrier: the accessible name says
        // the action is destructive even when the colour cannot.
        <span className="sr-only"> (destructive)</span>
      ) : null}
    </button>
  );
}

export interface IconButtonProps extends Omit<ButtonProps, 'children' | 'variant'> {
  /** What the control does, in words. Required — there is nothing else to read. */
  readonly label: string;
  readonly icon: ReactNode;
  readonly variant?: ButtonVariant;
}

/**
 * A control whose only content is a shape.
 *
 * `label` is required rather than optional, which is the whole design: an
 * optional accessible name is a name somebody omits, and to a screen reader an
 * unnamed icon button is a button called "button".
 */
export function IconButton({
  label,
  icon,
  variant = 'quiet',
  state = 'default',
  ...rest
}: IconButtonProps): ReactNode {
  const inert = state === 'disabled' || state === 'loading';
  return (
    <button
      type="button"
      {...rest}
      aria-label={label}
      data-variant={variant}
      data-state={state}
      disabled={inert}
      aria-busy={state === 'loading' ? true : undefined}
      className={cx(
        'inline-flex items-center justify-center size-control rounded-2 edge',
        VARIANT_SKIN[variant],
        STATE_SKIN[state],
      )}
    >
      {icon}
    </button>
  );
}

export interface LinkProps {
  readonly href: string;
  readonly children: ReactNode;
  /** Whether the destination is outside this deployment. */
  readonly external?: boolean;
  readonly 'data-testid'?: string;
}

/** The one skin, so the two elements below cannot drift apart. */
const LINK_SKIN =
  'inline-flex items-center gap-1 text-accent underline underline-offset-2 motion-hover hover:opacity-80';

/**
 * A navigation, as a link.
 *
 * An external destination says so in the accessible name as well as with the
 * arrow, because a viewer who cannot see the arrow still deserves to know that
 * the tab is about to change under them.
 *
 * The two destinations are two elements, and that is the whole of the
 * difference between them. Somewhere else on the web is a plain anchor: the
 * router has nothing to say about a host it does not serve. Somewhere else in
 * *this* console is a router transition — the same `href` in the document, so
 * the address is still what a screen is, the link is still copyable and it
 * still works with JavaScript disabled, but following it swaps the screen
 * instead of tearing the document down and building it again.
 *
 * Prefetching is off. Every route in this console is rendered on demand, so a
 * prefetch is a full server render and a set of reads against the deployment;
 * doing that for each link a viewer merely scrolls past would spend the
 * deployment's capacity on the ones nobody follows.
 */
export function Link({
  href,
  children,
  external = false,
  ...rest
}: LinkProps): ReactNode {
  if (external) {
    return (
      <a
        {...rest}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className={LINK_SKIN}
      >
        {children}
        <ArrowRightIcon />
        <span className="sr-only"> (opens in a new tab)</span>
      </a>
    );
  }

  return (
    <NextLink {...rest} href={href} prefetch={false} className={LINK_SKIN}>
      {children}
    </NextLink>
  );
}
