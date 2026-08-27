import { resolveCta } from '@/design/empty-state';
import { message, type Locale } from '@/i18n/messages';
import { readSetup, type DeploymentSetup } from './first-run/plan';
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
 * The cause an unfinished setup puts on the one screen that names its own
 * dependency, or ``null`` once that specific step is done.
 *
 * ``dependsOn`` is a checklist step name — the one the calling screen is
 * actually downstream of, never "however many steps are still outstanding
 * somewhere". A deployment with three steps left elsewhere and this one done
 * is a deployment this screen has nothing to blame the setup for: the count
 * used to say so anyway, which is the false causality this function exists
 * to stop asserting. `null` when the deployment does not declare a step by
 * that name at all — an unknown dependency is a caller's defect, not a
 * reason to guess at a sentence.
 */
export function setupCause(
  locale: Locale,
  setup: DeploymentSetup,
  dependsOn: string,
): Cause | null {
  const step = setup.steps.find((entry) => entry.name === dependsOn);
  if (step === undefined || step.state === 'done') return null;
  return {
    body: message(locale, 'empty.cause.setup', { step: step.title ?? '' }),
    actionLabel: message(locale, 'empty.cause.setup.action'),
    href: resolveCta({ route: '/first-run' }).href,
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
    href: resolveCta({ route: '/signals', query: { tab: 'observation' } }).href,
  };
}

/**
 * The cause an empty corpus has when the chain above it plainly ran.
 *
 * The episodes panel explains its own mechanism — an episode is written when
 * an investigation ends, and none has been written yet — and on a deployment
 * with finished investigations behind it the second half of that is simply
 * untrue. The two situations it collapses are opposite: a deployment that has
 * not investigated anything yet is waiting, and a deployment that has
 * investigated fifty things and written nothing down is losing every one of
 * them. Rendered identically, the first is what a reader assumes, so the
 * failure is invisible for as long as nobody counts the runs by hand.
 *
 * ``finished`` is investigations that *completed*, not investigations that
 * stopped. A cancelled or failed run has no conclusion to extract an episode
 * from, so counting one here would blame the corpus for a gap nothing was
 * ever going to fill.
 *
 * What this deliberately does not say is why. Extraction records its own
 * reason — the model call it makes, and the failure it came back with — and no
 * endpoint serves it, so the console cannot read one. It has two facts, the
 * count and the corpus, and it says exactly what those two support: the runs
 * ended, nothing came out of them, and the step between the two is a model
 * call configured per role. Naming a provider error the console has not seen
 * would be the same invention in the other direction.
 */
export function extractionCause(locale: Locale, finished: number): Cause | null {
  if (finished <= 0) return null;
  return {
    body: message(locale, 'empty.cause.extraction', { finished: String(finished) }),
    actionLabel: message(locale, 'empty.cause.extraction.action'),
    href: resolveCta({ route: '/settings/models-providers' }).href,
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
