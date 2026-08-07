// Three literals at once, one per kind the design system closes: a colour
// written out, a length that is not a step of the spacing scale, and a duration
// written out instead of taken from the motion scale. Each of them is the thing
// a design system decays into when nothing rejects it.
import type { ReactNode } from 'react';

export function Swatch(): ReactNode {
  return (
    <div className="p-9 rounded-lg" style={{ background: '#0f6f5c', transition: 'all 250ms' }}>
      Reclaim 41 GiB
    </div>
  );
}
