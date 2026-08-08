import type { ReactNode } from 'react';

/**
 * Broken on purpose: a sentence written into a component instead of taken from
 * the message catalogue, and an attribute a screen reader will announce in one
 * language whatever the viewer chose.
 *
 * Both are things the completeness test cannot see. It compares the locales it
 * is given; it has nothing at all to say about a string that never reached a
 * catalogue — and that is the string that ships untranslated, because it looks
 * correct to the person reviewing it.
 *
 * `tests/contract/console/test_console_gate.py` splices this into the tree and
 * requires the lint step to reject it by name.
 */
export function Untranslated(): ReactNode {
  return (
    <section aria-label="Everything that is waiting">
      <h2>Nothing needs you right now</h2>
    </section>
  );
}
