import type { ReactNode } from 'react';

import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { ObservationTab } from './detectors';

/**
 * Continuous observation: what this deployment watches for on its own,
 * without a person or a clock starting it.
 *
 * The address this screen answers at is retired from the sidebar and from
 * every Settings page's own subnav — `/signals?tab=observation` is the one
 * variant of the old four-tab Signals screen this wave's Settings pages do
 * not carry onward, because none of the nine replaces continuous
 * observation. What used to be its three siblings moved: Intake and
 * Destinations to `settings/alert-intake` and
 * `settings/schedules-destinations`, Schedules to the latter as well. This
 * screen is what is left once they are gone — one tab, not four, so the tab
 * chrome the four of them needed left with them.
 */
export async function SignalsScreen(context: SurfaceContext): Promise<ReactNode> {
  const { locale } = context;

  return (
    <>
      <AreaHeader area={areaFor('signals')} locale={locale} />
      <div className="mt-4">{await ObservationTab(context)}</div>
    </>
  );
}
