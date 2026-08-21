'use client';

import type { ReactNode } from 'react';
import { useCallback, useEffect, useId, useRef } from 'react';

import { Button, IconButton } from '@/components/action';
import { cx } from '@/design/cx';
import { CloseIcon } from '@/design/icons';

/**
 * The two overlays, and the one rule about when each is used.
 *
 * A modal is for a confirmation and nothing else. Everything else is a drawer,
 * which keeps the context behind it visible — an operator answering a question
 * about a run should be able to see the run. A modal that appeared for a detail
 * view would hide the thing the detail is about.
 *
 * Four properties decide whether an overlay works, and all four are only ever
 * experienced from a keyboard: focus goes in, focus stays in, escape dismisses,
 * and focus comes back. A pointer user never finds out that any of them is
 * missing, which is why they are tested by pressing keys.
 */

/** Everything inside `root` that a keyboard can reach. */
function focusable(root: HTMLElement): HTMLElement[] {
  return [
    ...root.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ];
}

/**
 * The geometry a caller opts into: anchored to the page rather than sitting
 * wherever it was written in the document.
 *
 * Left off `Overlay`'s own default because two of `Drawer`'s existing callers
 * already solved "beside the content, not on top of it" themselves — the
 * shell's nav drawer wraps it in its own `fixed inset-y-0 left-0` box, the
 * investigate drawer in its own `fixed inset-y-0 right-0` box, each with a
 * different anchor and width — and a third renders it bare inside a static
 * list of component demos. Making this the default would nest a second,
 * conflicting `fixed` box inside the first two and break the third outright.
 * A caller asks for it instead.
 */
const FLOATING_DRAWER_CLASS_NAME =
  'fixed inset-y-0 right-0 z-10 w-full max-w-prose overflow-y-auto';

interface OverlayProps {
  readonly open: boolean;
  readonly title: string;
  readonly onClose: () => void;
  readonly children: ReactNode;
  /** Whether the rest of the page is inert while this is open. */
  readonly modal: boolean;
  /** What the dismiss control is called, in the viewer's language. */
  readonly closeLabel: string;
  readonly className?: string;
  /** Named only so a caller can say where focus goes back to. */
  readonly returnFocusTo?: string;
  /**
   * Whether this overlay is anchored above the page rather than rendered as
   * a block in its own document flow. Defaults to `false`: a caller that
   * says nothing gets exactly today's rendering.
   */
  readonly floating?: boolean;
}

function Overlay({
  open,
  title,
  onClose,
  children,
  modal,
  closeLabel,
  className,
  floating = false,
}: OverlayProps): ReactNode {
  const headingId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(null);

  const dismiss = useCallback(() => {
    onClose();
  }, [onClose]);

  useEffect(() => {
    if (!open) return undefined;
    opener.current = document.activeElement;
    const first = panel.current === null ? null : focusable(panel.current)[0];
    first?.focus();

    if (modal) {
      document.body.setAttribute('data-scroll-locked', 'true');
    }

    const onKey = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        event.preventDefault();
        dismiss();
      }
      if (event.key !== 'Tab' || panel.current === null) return;
      const reachable = focusable(panel.current);
      const first_ = reachable[0];
      const last = reachable[reachable.length - 1];
      if (first_ === undefined || last === undefined) return;
      if (event.shiftKey && document.activeElement === first_) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first_.focus();
      }
    };

    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.removeAttribute('data-scroll-locked');
      // Focus goes back to whatever opened this. Without it a keyboard user
      // lands at the top of the document every time an overlay closes.
      if (opener.current instanceof HTMLElement) opener.current.focus();
    };
  }, [open, modal, dismiss]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal={modal ? true : undefined}
      aria-labelledby={headingId}
      ref={panel}
      data-floating={floating ? 'true' : undefined}
      className={cx(
        'bg-raised edge border-border rounded-4 shadow-2 p-5 flex flex-col gap-4 motion-overlay',
        floating && FLOATING_DRAWER_CLASS_NAME,
        className,
      )}
    >
      <header className="flex items-center gap-3">
        <h2 id={headingId} className="text-section">
          {title}
        </h2>
        <span className="ml-auto">
          <IconButton label={closeLabel} icon={<CloseIcon />} onClick={dismiss} />
        </span>
      </header>
      {children}
    </div>
  );
}

export interface ModalProps {
  readonly open: boolean;
  readonly title: string;
  readonly onClose: () => void;
  readonly children: ReactNode;
  /** What the dismiss control is called, in the viewer's language. */
  readonly closeLabel: string;
  readonly returnFocusTo?: string;
}

/** A confirmation, and nothing else. */
export function Modal({
  open,
  title,
  onClose,
  closeLabel,
  children,
}: ModalProps): ReactNode {
  return (
    <Overlay
      open={open}
      title={title}
      onClose={onClose}
      closeLabel={closeLabel}
      modal
      className="max-w-prose"
    >
      {children}
    </Overlay>
  );
}

export interface DrawerProps {
  readonly open: boolean;
  readonly title: string;
  readonly onClose: () => void;
  readonly children: ReactNode;
  /** What the dismiss control is called, in the viewer's language. */
  readonly closeLabel: string;
  /**
   * Whether this drawer floats above the page, anchored to it, instead of
   * rendering as a block wherever the screen wrote it.
   *
   * Opt-in, not the default: see `FLOATING_DRAWER_CLASS_NAME`'s own comment
   * for why the other callers of this component cannot have that decision
   * made for them.
   */
  readonly floating?: boolean;
}

/** Detail, beside the thing it is about rather than on top of it. */
export function Drawer({
  open,
  title,
  onClose,
  closeLabel,
  children,
  floating = false,
}: DrawerProps): ReactNode {
  return (
    <Overlay
      open={open}
      title={title}
      onClose={onClose}
      closeLabel={closeLabel}
      modal={false}
      floating={floating}
    >
      {children}
    </Overlay>
  );
}

export interface ConfirmDestructiveProps {
  readonly open: boolean;
  /** The dismiss control's name and the cancelling option's, in the viewer's language. */
  readonly labels: { readonly close: string; readonly cancel: string };
  /** What will be changed, named. Not "this item" — the actual thing. */
  readonly target: string;
  readonly action: string;
  readonly consequence: string;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
}

/**
 * The confirmation a destructive action requires.
 *
 * In the library rather than in each screen, so that "name the target" is not
 * something anybody has to remember. The safe option sits beside the
 * destructive one rather than behind it — a confirmation whose only visible
 * control is the dangerous one is a confirmation that has stopped being one.
 */
export function ConfirmDestructive({
  open,
  target,
  action,
  consequence,
  labels,
  onConfirm,
  onCancel,
}: ConfirmDestructiveProps): ReactNode {
  return (
    <Modal open={open} title={action} onClose={onCancel} closeLabel={labels.close}>
      <p className="text-small font-mono">{target}</p>
      <p className="text-small text-warning">{consequence}</p>
      <div className="flex gap-3">
        <Button variant="destructive" onClick={onConfirm}>
          {action}
        </Button>
        <Button onClick={onCancel}>{labels.cancel}</Button>
      </div>
    </Modal>
  );
}
