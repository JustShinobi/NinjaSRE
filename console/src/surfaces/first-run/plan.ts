import { field, flag, list, text } from '../read';

/**
 * Where a deployment is in its own setup, computed rather than remembered.
 *
 * There is no wizard cursor anywhere in this console — not in a cookie, not in
 * `localStorage`, not in a React state that survives a navigation. The step
 * somebody is on is a **function of what the deployment says about itself**, so
 * closing the tab after the credential form and coming back is the same
 * computation as never having left, and running the CLI's guided setup instead
 * moves the same document. Two surfaces agree because there is one source, not
 * because they were written to agree.
 *
 * The seven steps are the spec's, and the deployment's own vocabulary is only
 * four checklist steps plus a three-valued readiness. That is not a mismatch to
 * paper over: each of the seven is answered by something the deployment
 * actually records, and where two of them are answered by the *same* fact —
 * choosing a provider and storing its credential — they are done together,
 * because there is nothing a deployment remembers about the first without the
 * second.
 */

/** The order the platform is set up in, one step per screen. */
export const WIZARD_STEPS = [
  'provider',
  'credential',
  'model',
  'integrations',
  'verify',
  'estate',
  'alerts',
] as const;

export type WizardStep = (typeof WIZARD_STEPS)[number];

/** How far along one thing is, in the deployment's own three words. */
export type Readiness = 'absent' | 'configured' | 'verified';

/** One integration this deployment declares, and how far along it is. */
export interface IntegrationReadiness {
  readonly name: string;
  readonly readiness: string;
}

/** One checklist step, as the deployment reports it. */
export interface ChecklistStep {
  readonly name: string;
  readonly state: string;
  readonly title?: string;
  readonly detail?: string;
  readonly action?: string;
}

/** Everything the seven steps are decided from. */
export interface DeploymentSetup {
  readonly complete: boolean;
  readonly provider: string;
  readonly integrations: readonly IntegrationReadiness[];
  readonly steps: readonly ChecklistStep[];
  /** Whether the configuration this viewer's node resolves to names a model. */
  readonly modelChosen: boolean;
  /**
   * The provider this deployment is configured to run, or `''`.
   *
   * Carried because some providers are also catalogue integrations — Gemini
   * both drives investigations and appears in the vendor catalogue — and the
   * checklist therefore lists one stored credential under two headings. Without
   * the name there is no way to tell which of the listed integrations *is* the
   * provider, and the verification step asks for one thing to be checked twice.
   */
  readonly providerName: string;
  /**
   * The name of the checklist step the deployment itself points at next, or
   * `''` once none is left. The route's own `next` field — read here for the
   * first time and the reason it is read at all: it is what tells the
   * checklist panel and the dashboard card which of `steps` to highlight,
   * without either inventing that answer from `WIZARD_STEPS`, a list
   * `setup.steps` has no entry-for-entry correspondence with.
   */
  readonly next: string;
}

/** The checklist step that says an estate exists. */
export const SOURCE_STEP = 'infrastructure-source';

/** The checklist step that says an investigation has finished here. */
export const INVESTIGATION_STEP = 'first-investigation';

/**
 * The checklist step that says something here can actually drive an
 * investigation, distinct from the seven wizard steps above.
 *
 * There is no wizard step of its own for it: the dependency it names — a
 * runtime composed by whoever deployed this — is not a configuration field,
 * so it has no page in this wizard to be "done" on. It is still read, on the
 * last step, so a deployment stuck here is told what is actually stopping it
 * rather than left to discover it by pressing Investigate and reading an
 * exception.
 */
export const RUNTIME_STEP = 'investigation-runtime';

/** Where the wizard writes and reads the model it was told to use. */
export const MODEL_PROVIDER_SETTING = 'models.investigator.provider';
export const MODEL_SETTING = 'models.investigator.model';

/**
 * The value at a dotted `path` in an effective document, walked segment by
 * segment. The document is nested the way the schema is; read as one flat key,
 * every setting would answer undefined forever.
 */
function valueAt(values: unknown, path: string): unknown {
  let cursor: unknown = values;
  for (const segment of path.split('.')) {
    cursor = field(cursor, segment);
  }
  return cursor;
}

/** `name` when it is a step of this wizard, and nothing when it is not. */
export function stepAt(name: string | null | undefined): WizardStep | undefined {
  return WIZARD_STEPS.find((step) => step === name);
}

function stateOfStep(setup: DeploymentSetup, name: string): string {
  return setup.steps.find((step) => step.name === name)?.state ?? '';
}

/** Every integration that holds something, verified or not. */
export function configuredIntegrations(
  setup: DeploymentSetup,
): readonly IntegrationReadiness[] {
  return setup.integrations.filter((entry) => entry.readiness !== 'absent');
}

/**
 * The integrations the verification step actually asks about.
 *
 * The configured ones, minus the model provider where it is also a catalogue
 * vendor. That subtraction is the whole function: the provider is checked by
 * the provider row — against the model, which is the check that means
 * something — and counting it again as an integration made the step
 * uncompletable, because the second row is the one the screen deliberately does
 * not show.
 */
export function verifiableIntegrations(
  setup: DeploymentSetup,
): readonly IntegrationReadiness[] {
  return configuredIntegrations(setup).filter(
    (entry) => setup.providerName === '' || entry.name !== setup.providerName,
  );
}

/**
 * Whether `step` needs nothing further.
 *
 * Each answer is a fact the deployment records, and where no such fact exists
 * the step is *not* done — the honest direction, because a wizard that
 * congratulated somebody on a step nothing had happened for is a wizard that
 * ends with a deployment that cannot investigate.
 */
export function stepDone(step: WizardStep, setup: DeploymentSetup): boolean {
  // The deployment's own verdict wins outright. These seven are a finer view of
  // the four steps the platform keeps, and a finer view that contradicted the
  // coarser one would put a console and a terminal into disagreement about a
  // deployment that is finished — which is the exact failure the single source
  // is for.
  if (setup.complete) return true;
  const configured = configuredIntegrations(setup);
  switch (step) {
    // Two steps, one fact. A provider chosen and not paid for leaves nothing
    // behind, and a credential cannot be stored without naming the provider it
    // is for, so the deployment records exactly one thing about both.
    case 'provider':
    case 'credential':
      return setup.provider !== 'absent';
    case 'model':
      return setup.provider !== 'absent' && setup.modelChosen;
    case 'integrations':
      return configured.length > 0;
    case 'verify': {
      const checkable = verifiableIntegrations(setup);
      return (
        setup.provider === 'verified' &&
        configured.length > 0 &&
        checkable.every((entry) => entry.readiness === 'verified')
      );
    }
    case 'estate':
      return stateOfStep(setup, SOURCE_STEP) === 'done';
    case 'alerts':
      return stateOfStep(setup, INVESTIGATION_STEP) === 'done';
  }
}

/**
 * How many of the deployment's own checklist steps still need something.
 *
 * Read from `setup.steps` — the array `GET /v1/setup/checklist` actually
 * carries, the same one `ninjasre onboard` reads — never from `WIZARD_STEPS`,
 * which is a client-only sequencing concept the checklist route has no
 * counterpart for and the CLI has no way to reproduce. This is the one
 * number every surface that states "how much setup is left" reads: the
 * checklist panel's own heading and progress line, and the dashboard card.
 * The wizard header's "Step N of 7" is a different fact — which of the seven
 * *screens* is showing — and keeps its own denominator below; what changed
 * here is that nothing computes a second, competing "how much is left" from
 * the wizard's own step list any more.
 */
export function outstanding(setup: DeploymentSetup): number {
  // The deployment's own verdict wins outright, the same rule `stepDone`
  // follows for the same reason: a finished deployment whose historical
  // step rows were never individually rewritten to `'done'` must still read
  // as finished, not as one still owing work nobody can act on any more.
  if (setup.complete) return 0;
  return setup.steps.filter((step) => step.state !== 'done').length;
}

/**
 * Where a deployment is in its own checklist, as one fact: how many steps
 * there are in total and how many of them still need something — both read
 * from `setup.steps`, so the checklist panel and the dashboard card can never
 * cite a different denominator than `outstanding` itself does.
 */
export interface SetupProgress {
  readonly total: number;
  readonly pending: number;
}

/** `setup`'s progress through its own checklist steps. */
export function setupProgress(setup: DeploymentSetup): SetupProgress {
  return {
    total: setup.steps.length,
    pending: outstanding(setup),
  };
}

/**
 * The step to show: the one an address asks for, or the first unfinished one.
 *
 * An address wins so a completed step can be reopened — which is the whole of
 * "completed steps reopen", and it is a navigation rather than a mode. A
 * deployment with nothing left shows the last step rather than nothing at all:
 * falling off the end of a wizard is a blank page.
 */
export function currentStep(
  setup: DeploymentSetup,
  requested?: string | null,
): WizardStep {
  const asked = stepAt(requested);
  if (asked !== undefined) return asked;
  return WIZARD_STEPS.find((step) => !stepDone(step, setup)) ?? 'alerts';
}

/** Where a step lives, so a completed one is a link rather than a memory. */
export function hrefFor(step: WizardStep): string {
  return `/first-run?step=${step}`;
}

/**
 * Whether `step`, left unfinished, stops the wizard rather than merely
 * slowing it down.
 *
 * Declared per step, and answered from the same fact `stepDone` already
 * reads for `verify` — not from which *kind* of thing is failing a check.
 * The mockup's own worked example fails the model provider's own
 * verification (a real model that answers without calling a tool) and still
 * offers to continue, because a provider that exists and answers badly is a
 * different fact from no provider existing at all: the first has something
 * to explore with, the second has nothing a re-check could ever be about.
 * Every other step has no blocking rule of its own yet.
 */
export function stepBlocking(step: WizardStep, setup: DeploymentSetup): boolean {
  if (step === 'verify') return setup.provider === 'absent';
  return false;
}

/** The step that comes after `step`, or `undefined` past the last one. */
export function nextStep(step: WizardStep): WizardStep | undefined {
  return WIZARD_STEPS[WIZARD_STEPS.indexOf(step) + 1];
}

/** One row of the step list the screen keeps visible. */
export interface PlannedStep {
  readonly step: WizardStep;
  readonly done: boolean;
  readonly current: boolean;
  readonly href: string;
}

/** The seven, in order, with exactly one of them current. */
export function planFor(
  setup: DeploymentSetup,
  requested?: string | null,
): readonly PlannedStep[] {
  const here = currentStep(setup, requested);
  return WIZARD_STEPS.map((step) => ({
    step,
    done: stepDone(step, setup),
    current: step === here,
    href: hrefFor(step),
  }));
}

/**
 * What the checklist and the effective configuration between them say.
 *
 * Defensive on purpose. Both reads can fail, and a failed read must resolve to
 * *nothing has been done* rather than to a finished setup: the first is a
 * wizard that offers a step somebody has already taken, and the second is a
 * console that tells a deployment with no provider that it is ready.
 */
export function readSetup(checklist: unknown, values: unknown): DeploymentSetup {
  const provider = text(checklist, 'provider');
  return {
    complete: flag(checklist, 'complete'),
    provider: provider === '' ? 'absent' : provider,
    integrations: list(checklist, 'integrations').map((entry) => ({
      name: text(entry, 'name'),
      readiness: text(entry, 'readiness'),
    })),
    steps: list(checklist, 'steps').map((entry) => ({
      name: text(entry, 'name'),
      state: text(entry, 'state'),
      title: text(entry, 'title'),
      detail: text(entry, 'detail'),
      action: text(entry, 'action'),
    })),
    modelChosen: typeof valueAt(values, MODEL_SETTING) === 'string',
    providerName: providerNameOf(values),
    next: text(checklist, 'next'),
  };
}

/** The configured provider's name, or `''` when the configuration names none. */
function providerNameOf(values: unknown): string {
  const named = valueAt(values, MODEL_PROVIDER_SETTING);
  return typeof named === 'string' ? named : '';
}
