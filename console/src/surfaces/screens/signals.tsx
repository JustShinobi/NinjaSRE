import type { ReactNode } from 'react';

import { TabLinks } from '@/components';
import { message } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { readViewState, type FilterName } from '../url-state';
import { DestinationsTab, IntakeTab } from './data';
import { ObservationTab, SchedulesTab } from './detectors';

/**
 * What enters continuous observation, and where an alert ends up once it has
 * — the two halves of one pipe that used to sit in different zones of the
 * menu for no reason a reader could see.
 *
 * Four tabs, in the order a delivery actually moves through them: Intake
 * (what arrives and the rules that decide what happens to it), Continuous
 * observation (the detectors that watch the estate on their own), Schedules
 * (the investigations that watch it on a clock instead), Destinations
 * (where a delivery ends up, and what to do about one that failed).
 */

export const SIGNALS_TABS = [
  'intake',
  'observation',
  'schedules',
  'destinations',
] as const;

export type SignalsTab = (typeof SIGNALS_TABS)[number];

const SIGNALS_FILTERS: readonly FilterName[] = ['tab'];

/** Who may see or change this team's scheduled investigations. */
const SCHEDULE_MANAGE = 'schedule.manage';

export async function SignalsScreen(context: SurfaceContext): Promise<ReactNode> {
  const { locale, search, viewer } = context;
  const state = readViewState(search, SIGNALS_FILTERS);

  // Absent, not disabled: `GET /v1/schedules` itself takes `schedule.manage`,
  // so a viewer without it never sees a tab whose content would be a blank
  // panel, the same "presence decides" rule the sidebar itself follows.
  const allowed = may(viewer, SCHEDULE_MANAGE)
    ? SIGNALS_TABS
    : SIGNALS_TABS.filter((each) => each !== 'schedules');
  const requested = state.filters.tab ?? '';
  const tab: SignalsTab = allowed.find((each) => each === requested) ?? allowed[0];

  // Only the selected tab reads anything.
  const content =
    tab === 'intake'
      ? await IntakeTab(context)
      : tab === 'observation'
        ? await ObservationTab(context)
        : tab === 'schedules'
          ? await SchedulesTab(context)
          : await DestinationsTab(context);

  return (
    <>
      <AreaHeader area={areaFor('signals')} locale={locale} />

      <TabLinks
        label={message(locale, 'signals.tabs')}
        selected={tab}
        tabs={allowed.map((each) => ({
          id: each,
          label: message(locale, `signals.tab.${each}`),
          href: `?tab=${each}`,
        }))}
      />

      <div className="mt-4">{content}</div>
    </>
  );
}
