'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Drawer } from '@/components/overlay';

/**
 * The rare-action pattern for a screen where one control is meant to cost
 * more than the rest: absent from the page's own layout, reachable through
 * one button in the header, opened into a side panel that leaves everything
 * else on the screen visible behind it.
 *
 * Its own component, distinct from whatever the panel shows, because the
 * button and the panel share one thing no server component can hold —
 * whether the panel is open right now — and the button has to render inside
 * the page header, which a server component builds. `Drawer` itself already
 * returns `null` while closed, so the panel's contents are genuinely
 * unmounted rather than merely hidden — nothing here reserves space for
 * them until the button is pressed.
 */

export interface OverridePanelProps {
  /**
   * What the header button says, and the panel's own title. The same
   * phrase names both, so whoever opens the panel from the button finds the
   * words they clicked waiting for them at the top of what opened.
   */
  readonly label: string;
  /** What the panel's own dismiss control is called. */
  readonly closeLabel: string;
  readonly children: ReactNode;
}

/** A header button that opens `children` into a side panel, and nothing else. */
export function OverridePanel({
  label,
  closeLabel,
  children,
}: OverridePanelProps): ReactNode {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        data-testid="open-override-panel"
        onClick={() => {
          setOpen(true);
        }}
      >
        {label}
      </Button>
      <Drawer
        open={open}
        title={label}
        onClose={() => {
          setOpen(false);
        }}
        closeLabel={closeLabel}
      >
        <div className="flex flex-col gap-5">{children}</div>
      </Drawer>
    </>
  );
}
