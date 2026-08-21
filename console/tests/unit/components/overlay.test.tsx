import { render, screen } from '@testing-library/react';
import { useState, type ReactNode } from 'react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ConfirmDestructive, Drawer, Modal } from '@/components/overlay';

/**
 * The two overlays, and the four things an overlay has to get right.
 *
 * Focus goes in, focus stays in, escape dismisses, and focus comes back to
 * whatever opened it. Each of those is tested by driving the keyboard, because
 * each of them is only ever experienced from a keyboard — a pointer user never
 * finds out that the focus trap is missing.
 *
 * The third component here is not a primitive so much as a rule: a destructive
 * action requires a confirmation that names the target. It is in the library
 * rather than in each screen so that "name the target" is not a thing anybody
 * has to remember.
 */

describe('Modal', () => {
  it('is a dialog with a name, and is modal', () => {
    render(
      <Modal open title="Confirm reclaim" onClose={vi.fn()} closeLabel="Close">
        <p>41 GiB will be removed.</p>
      </Modal>,
    );
    const dialog = screen.getByRole('dialog', { name: 'Confirm reclaim' });

    expect(dialog).toHaveAttribute('aria-modal', 'true');
  });

  it('renders nothing at all when it is closed', () => {
    render(
      <Modal open={false} title="Confirm reclaim" onClose={vi.fn()} closeLabel="Close">
        <p>41 GiB will be removed.</p>
      </Modal>,
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('moves focus into itself when it opens', () => {
    render(
      <Modal open title="Confirm reclaim" onClose={vi.fn()} closeLabel="Close">
        <button type="button">Reclaim</button>
      </Modal>,
    );
    expect(screen.getByRole('dialog')).toContainElement(
      document.activeElement as HTMLElement,
    );
  });

  it('keeps focus inside, in both directions', async () => {
    render(
      <Modal open title="Confirm reclaim" onClose={vi.fn()} closeLabel="Close">
        <button type="button">First</button>
        <button type="button">Last</button>
      </Modal>,
    );

    const close = screen.getByRole('button', { name: /close/i });
    const last = screen.getByRole('button', { name: 'Last' });

    last.focus();
    await userEvent.tab();
    expect(document.activeElement).toBe(close);

    await userEvent.tab({ shift: true });
    expect(document.activeElement).toBe(last);
  });

  it('dismisses on escape and gives focus back to whatever opened it', async () => {
    const closed = vi.fn();
    render(
      <>
        <button type="button">Open</button>
        <Modal
          open
          title="Confirm reclaim"
          onClose={closed}
          returnFocusTo="opener"
          closeLabel="Close"
        >
          <button type="button">Reclaim</button>
        </Modal>
      </>,
    );

    await userEvent.keyboard('{Escape}');
    expect(closed).toHaveBeenCalledOnce();
  });

  it('locks the page behind it, so the background does not scroll away', () => {
    const { unmount } = render(
      <Modal open title="Confirm reclaim" onClose={vi.fn()} closeLabel="Close">
        <p>content</p>
      </Modal>,
    );
    expect(document.body).toHaveAttribute('data-scroll-locked', 'true');

    unmount();
    expect(document.body).not.toHaveAttribute('data-scroll-locked');
  });
});

describe('Drawer', () => {
  it('keeps the context behind it visible, which is why it is not a modal', () => {
    render(
      <Drawer open title="Evidence" onClose={vi.fn()} closeLabel="Close">
        <p>The last sweep.</p>
      </Drawer>,
    );
    const drawer = screen.getByRole('dialog', { name: 'Evidence' });

    expect(drawer).not.toHaveAttribute('aria-modal', 'true');
  });

  it('dismisses on escape', async () => {
    const closed = vi.fn();
    render(
      <Drawer open title="Evidence" onClose={closed} closeLabel="Close">
        <p>The last sweep.</p>
      </Drawer>,
    );

    await userEvent.keyboard('{Escape}');
    expect(closed).toHaveBeenCalledOnce();
  });

  // Four consumers wrap this component in their own positioning today — the
  // shell's nav drawer, the investigate drawer — or rely on it staying a
  // plain block — the component gallery's demo list. None of the four asked
  // for an overlay, so the geometry stays opt-in: nothing changes for a
  // `Drawer` that does not request it.
  it('renders as a plain block in the document flow when nobody asks for the overlay', () => {
    render(
      <Drawer open title="Evidence" onClose={vi.fn()} closeLabel="Close">
        <p>The last sweep.</p>
      </Drawer>,
    );
    const drawer = screen.getByRole('dialog', { name: 'Evidence' });

    expect(drawer).not.toHaveClass('fixed');
    expect(drawer).not.toHaveAttribute('data-floating');
  });

  describe('the overlay geometry, once a caller asks for it', () => {
    it('is taken out of the document flow and anchored above the page', () => {
      render(
        <Drawer open floating title="Evidence" onClose={vi.fn()} closeLabel="Close">
          <p>The last sweep.</p>
        </Drawer>,
      );
      const drawer = screen.getByRole('dialog', { name: 'Evidence' });

      // `fixed` is the load-bearing class: it is what takes the panel out of
      // the document's own flow in a real browser, which is what the
      // acceptance spec measures directly (computed `position`, and that the
      // document does not grow to fit the panel in). jsdom never resolves
      // Tailwind's stylesheet, so this test can only prove the class made it
      // onto the node — `data-floating` is the second, environment-
      // independent signal of the same decision.
      expect(drawer).toHaveClass('fixed');
      expect(drawer).toHaveAttribute('data-floating', 'true');
    });

    // The four properties below are only ever experienced from a keyboard,
    // and every one of them already worked before this geometry existed.
    // Each is re-proven here, on the floating variant specifically, so a
    // geometry change that silently cost the focus trap could not pass by
    // only ever being measured for position.

    it('moves focus into itself when it opens', () => {
      render(
        <Drawer open floating title="Evidence" onClose={vi.fn()} closeLabel="Close">
          <button type="button">Reclaim</button>
        </Drawer>,
      );
      expect(screen.getByRole('dialog')).toContainElement(
        document.activeElement as HTMLElement,
      );
    });

    it('keeps focus inside, in both directions', async () => {
      render(
        <Drawer open floating title="Evidence" onClose={vi.fn()} closeLabel="Close">
          <button type="button">First</button>
          <button type="button">Last</button>
        </Drawer>,
      );

      const close = screen.getByRole('button', { name: /close/i });
      const last = screen.getByRole('button', { name: 'Last' });

      last.focus();
      await userEvent.tab();
      expect(document.activeElement).toBe(close);

      await userEvent.tab({ shift: true });
      expect(document.activeElement).toBe(last);
    });

    it('dismisses on escape', async () => {
      const closed = vi.fn();
      render(
        <Drawer open floating title="Evidence" onClose={closed} closeLabel="Close">
          <p>The last sweep.</p>
        </Drawer>,
      );

      await userEvent.keyboard('{Escape}');
      expect(closed).toHaveBeenCalledOnce();
    });

    it('gives focus back to whatever opened it, once it closes', async () => {
      // A real open/close cycle, not a component already mounted open: the
      // property under test is that focus *returns* to the element that had
      // it before the drawer opened, which only means something if that
      // element was actually focused first.
      function Harness(): ReactNode {
        const [open, setOpen] = useState(false);
        return (
          <>
            <button
              type="button"
              onClick={() => {
                setOpen(true);
              }}
            >
              Open
            </button>
            <Drawer
              open={open}
              floating
              title="Evidence"
              onClose={() => {
                setOpen(false);
              }}
              closeLabel="Close"
            >
              <button type="button">Reclaim</button>
            </Drawer>
          </>
        );
      }
      render(<Harness />);

      const opener = screen.getByRole('button', { name: 'Open' });
      opener.focus();
      await userEvent.click(opener);
      expect(screen.getByRole('dialog')).toBeInTheDocument();

      await userEvent.keyboard('{Escape}');
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(document.activeElement).toBe(opener);
    });
  });
});

describe('ConfirmDestructive', () => {
  it('names the target in the confirmation, not just in the screen behind it', () => {
    render(
      <ConfirmDestructive
        open
        target="local-lvm on pve02"
        action="Reclaim 41 GiB"
        consequence="One of the items is a recovery point."
        labels={{ close: 'Close', cancel: 'Cancel' }}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getByRole('dialog')).toHaveTextContent('local-lvm on pve02');
    expect(
      screen.getByText('One of the items is a recovery point.'),
    ).toBeInTheDocument();
  });

  it('puts the safe option beside the destructive one rather than behind it', () => {
    render(
      <ConfirmDestructive
        open
        target="local-lvm on pve02"
        action="Reclaim 41 GiB"
        consequence="One of the items is a recovery point."
        labels={{ close: 'Close', cancel: 'Cancel' }}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: /Reclaim 41 GiB/ })).toHaveAttribute(
      'data-variant',
      'destructive',
    );
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
  });

  it('confirms only on the confirmation, never on the way past', async () => {
    const confirmed = vi.fn();
    const cancelled = vi.fn();
    render(
      <ConfirmDestructive
        open
        target="local-lvm on pve02"
        action="Reclaim 41 GiB"
        consequence="One of the items is a recovery point."
        labels={{ close: 'Close', cancel: 'Cancel' }}
        onConfirm={confirmed}
        onCancel={cancelled}
      />,
    );

    await userEvent.keyboard('{Escape}');
    expect(confirmed).not.toHaveBeenCalled();
    expect(cancelled).toHaveBeenCalledOnce();

    await userEvent.click(screen.getByRole('button', { name: /Reclaim 41 GiB/ }));
    expect(confirmed).toHaveBeenCalledOnce();
  });
});
