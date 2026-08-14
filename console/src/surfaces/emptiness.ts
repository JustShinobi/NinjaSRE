import { message, type Locale } from '@/i18n/messages';
import { outstanding, readSetup, type DeploymentSetup } from './first-run/plan';
import type { PanelEmpty } from './panel';
import { authorised, dataOf, field, optionalRead, read } from './read';

/**
 * Why *this* deployment has nothing to show, rather than what the feature is for.
 *
 * Every empty state in the console explains the mechanism and stops there:
 * "a detector opens an incident when what it watches crosses its threshold;
 * none has", "the graph is built from what investigations observe; nothing has
 * been observed yet", "an episode is written when an investigation ends; none
 * has ended". All three are true, all three are useless, and all three are the
 * same omission — on this deployment nothing has happened because the setup is
 * unfinished, and no screen says so.
 *
 * The distinction is the whole point. "Nothing is wrong" and "nothing is
 * watching" render identically today, and they are opposite situations: the
 * first is a deployment working, the second is a deployment that will stay
 * silent through the incident it was bought to catch.
 *
 * **A cause is local or it is not a cause.** Anything this module returns names
 * a fact about this deployment and the screen that fixes it. Where nothing is
 * wrong, it returns `null` and the screen keeps its own words — because on a
 * configured deployment the mechanism *is* the right explanation, and a console
 * that blamed the setup forever would be the same failure in the other
 * direction.
 */

/** One reason this deployment, specifically, is empty — and the way out. */
export interface Cause {
  readonly body: string;
  readonly actionLabel: string;
  readonly href: string;
}

/**
 * The cause an unfinished setup puts on every screen downstream of it.
 *
 * ``null`` once the checklist is complete. Downstream is most of the console:
 * incidents come from detectors, the graph and the episodes come from
 * investigations, and none of those can happen before the deployment can
 * investigate at all.
 */
export function setupCause(locale: Locale, setup: DeploymentSetup): Cause | null {
  const left = outstanding(setup);
  if (left === 0) return null;
  return {
    body: message(locale, 'empty.cause.setup', { count: String(left) }),
    actionLabel: message(locale, 'empty.cause.setup.action'),
    href: '/first-run',
  };
}

/**
 * The cause for a screen fed by continuous observation, when none is running.
 *
 * Separate from the setup cause and checked before it, because it is the more
 * specific of the two: a deployment can finish its checklist and still have no
 * detector switched on, and "finish the setup" would then be advice for
 * something already done.
 */
export function watchingCause(locale: Locale, live: number): Cause | null {
  if (live > 0) return null;
  return {
    body: message(locale, 'empty.cause.watching'),
    actionLabel: message(locale, 'empty.cause.watching.action'),
    href: '/signals?tab=observation',
  };
}

/**
 * ``empty``, with the local cause replacing its body and its action.
 *
 * The heading stays: it names what would be here, which is true either way.
 * What changes is the sentence under it and where the button goes — from the
 * feature's mechanism to this deployment's reason.
 */
export function emptyBecause(empty: PanelEmpty, cause: Cause | null): PanelEmpty {
  if (cause === null) return empty;
  return {
    heading: empty.heading,
    body: cause.body,
    actionLabel: cause.actionLabel,
    href: cause.href,
  };
}

/**
 * The first cause that applies, most specific first.
 *
 * One sentence, not a list. A screen that recited every reason it was empty
 * would be a screen nobody finishes reading, and the operator only needs the
 * next thing to do.
 */
export function firstCause(...causes: readonly (Cause | null)[]): Cause | null {
  return causes.find((cause) => cause !== null) ?? null;
}

/**
 * What the deployment says about its own setup, for a screen that needs the cause.
 *
 * Its own read rather than something threaded from the shell: these screens are
 * server components rendered independently, and a prop would mean every layout
 * between here and the shell knowing about a checklist it does not render. The
 * read is optional and a failure resolves to "nothing outstanding", which
 * leaves the screen's own words in place — the safe direction, because a
 * console that could not read the checklist must not start telling people their
 * setup is broken.
 */
export async function readSetupState(credential: string): Promise<DeploymentSetup> {
  const init = authorised(credential);
  const [checklist, effective] = await Promise.all([
    optionalRead('/v1/setup/checklist', () => read('/v1/setup/checklist', init)),
    optionalRead('/v1/config/{node_id}', () => Promise.resolve({})),
  ]);
  return readSetup(dataOf(checklist), field(dataOf(effective), 'values'));
}
