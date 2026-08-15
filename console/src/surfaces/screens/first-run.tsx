import type { ReactNode } from 'react';

import { Link } from '@/components/action';
import { StatusChip, StatusDot } from '@/components/status';
import { cx } from '@/design/cx';
import { message, type Locale } from '@/i18n/messages';
import { formatNumber } from '@/i18n/format';
import { AreaHeader } from '@/shell/area';
import { areaByPath, areaFor, settingsPageByPath } from '@/shell/routes';
import { may } from '@/session/viewer';
import { checklistTitle } from './first-run-heading';
import { credentialLabels, panelLabels, verifyLabels } from '../labels';
import { Panel } from '../panel';
import { CredentialField, type CredentialFieldSpec } from '../credential';
import { EstateStep } from '../first-run/estate';
import { IntegrationsStep, type IntegrationOffer } from '../first-run/integrations';
import { ModelStep } from '../first-run/model';
import {
  INVESTIGATION_STEP,
  RUNTIME_STEP,
  SOURCE_STEP,
  WIZARD_STEPS,
  configuredIntegrations,
  currentStep,
  hrefFor,
  nextStep,
  outstanding,
  planFor,
  readSetup,
  stepBlocking,
  stepDone,
  type DeploymentSetup,
  type WizardStep,
} from '../first-run/plan';
import { VerifyStep, type VerifiableThing } from '../first-run/verify';
import { withSetupReturn } from '../first-run/return-banner';
import {
  authorised,
  dataOf,
  dependencyOf,
  field,
  flag,
  list,
  optionalRead,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { viewerNode } from '../tree';
import type { SurfaceContext } from '../context';

/**
 * The guided first run — inside the shell, and never in front of it.
 *
 * The first version of this screen was a redirect: a deployment with no
 * provider was sent here and held here until it had one. That is wrong, and it
 * is wrong in a way that costs the product the people it is trying to keep. The
 * person looking at a console on its first day is deciding whether to keep it,
 * and a form in front of the door hides exactly the thing they came to see. So
 * this is an ordinary area with an ordinary address, the dashboard renders at
 * zero, and what stops somebody abandoning the setup half way is a checklist
 * that stays visible where they are working rather than a door that will not
 * open.
 *
 * **Nothing here is remembered.** The step is derived from the deployment's own
 * checklist (see `../first-run/plan.ts`), so closing the tab and coming back
 * resumes correctly by construction, and running the CLI's guided setup instead
 * moves the same document. There is no cursor to disagree with.
 *
 * The last two steps hand over rather than doing the work: an estate and an
 * alert route are established by screens that arrive with the features that own
 * them. Until they do, the step says what is missing, why it matters, and which
 * screen provides it — which is the whole of what an honest empty state owes
 * somebody.
 */

/** Where the alert receivers and the estate onboarding will be reached. */
/** The catalogue category an estate is discovered from. */
const ESTATE_CATEGORY = 'cloud_control_plane';

// Alert intake, not Signals: the hybrid navigation retired /signals to a
// redirect that depends on the checklist being closed nowhere it can read,
// and a handover that named the retired address would keep working only for
// as long as that redirect exists to catch it. Naming the final address
// directly means the next cleanup that removes the redirect table breaks
// nothing here.
const HANDOVER: Readonly<Record<'estate' | 'alerts', string>> = {
  estate: '/resources',
  alerts: '/settings/alert-intake',
};

/** `step`'s handover address, with the parameter its screen offers a way back for. */
function handoverHref(step: 'estate' | 'alerts'): string {
  return withSetupReturn(HANDOVER[step]);
}

/**
 * The screen `step` hands over to, in its own words for it — or `''` for a
 * step that has none.
 *
 * Five of the seven steps have no screen to name: they are sub-steps of this
 * one wizard, and a "continues on" label on them would invent a destination
 * that does not exist. Read from `HANDOVER`, the same address the link at
 * the bottom of the step already navigates to, so the map and the link can
 * never name two different screens for the same step.
 *
 * Checked against both route manifests, because a handover can land on a
 * top-level area (Resources) or on a Settings subnav page (Alert intake),
 * and only one of the two lists knows either.
 */
function handoverScreen(locale: Locale, step: WizardStep): string {
  if (step !== 'estate' && step !== 'alerts') return '';
  const area = areaByPath(HANDOVER[step]);
  if (area !== undefined) return message(locale, area.label);
  const page = settingsPageByPath(HANDOVER[step]);
  return page === undefined ? '' : message(locale, page.label);
}

/**
 * Where the deployment says this vendor is already running, if it says so.
 *
 * Read rather than derived. The estate and the catalogue are both the
 * deployment's, and the rule that matches one against the other lives there —
 * a second copy here would be a second answer to "which of these do I need".
 */
function suggestionOf(
  record: unknown,
): { readonly address: string; readonly because: string } | undefined {
  const found = field(record, 'suggested');
  if (found === null || found === undefined) return undefined;
  const address = text(found, 'address');
  return address === '' ? undefined : { address, because: text(found, 'because') };
}

function fieldsOf(record: unknown, key: string): readonly CredentialFieldSpec[] {
  return list(record, key).map((declared) => ({
    name: text(declared, 'name'),
    label: text(declared, 'label'),
    help: text(declared, 'help'),
    secret: flag(declared, 'secret'),
    required: flag(declared, 'required'),
    environmentVariable: text(declared, 'environment_variable'),
  }));
}

/** The checklist step whose subject is `name`, for a handover step's own words. */
function detailOf(
  setup: DeploymentSetup,
  name: string,
): { detail: string; action: string } {
  const step = setup.steps.find((each) => each.name === name);
  return { detail: step?.detail ?? '', action: step?.action ?? '' };
}

export async function FirstRunScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, search, viewer } = context;
  const init = authorised(credential);
  // The steps below write configuration at this node, so it has to resolve to
  // a node that exists — the viewer's team, or the root of the visible tree
  // for a session that names none.
  const node = await viewerNode(viewer, init);

  const [checklist, providers, integrations, schemas, effective] = await Promise.all([
    panelRead('/v1/setup/checklist', () => read('/v1/setup/checklist', init)),
    panelRead('/v1/providers', () => read('/v1/providers', init)),
    panelRead('/v1/integrations', () => read('/v1/integrations', init)),
    // Both of these answer 404 at a node that carries nothing of its own, which
    // is the ordinary state of the deployment this screen exists for.
    optionalRead('/v1/config/{node_id}/integration-schemas', () =>
      node === ''
        ? Promise.resolve({})
        : read('/v1/config/{node_id}/integration-schemas', {
            ...init,
            params: { node_id: node },
          }),
    ),
    optionalRead('/v1/config/{node_id}', () =>
      node === ''
        ? Promise.resolve({})
        : read('/v1/config/{node_id}', { ...init, params: { node_id: node } }),
    ),
  ]);

  const setup = readSetup(dataOf(checklist), field(dataOf(effective), 'values'));
  const requested = search.get('step');
  const here = currentStep(setup, requested);
  const plan = planFor(setup, requested);

  const providerRecords = list(dataOf(providers), 'providers');
  // Which provider the credential and model steps are about: the one the
  // address names, or the one this deployment already holds a credential for.
  // Never a guess — with neither, the credential step sends somebody back to
  // the choice rather than showing a form for a vendor nobody picked.
  const chosen =
    search.get('provider') ??
    text(
      providerRecords.find((record) => flag(record, 'configured')),
      'provider_id',
    );
  // The provider this deployment actually runs, which is not always the one the
  // address names: `?provider=` is what somebody is *looking at* on the choice
  // step. The two lists below subtract this one, because a provider that is
  // also a catalogue vendor is one stored credential rather than two — and
  // subtracting whatever the address happened to name would hide a different
  // vendor from the list of things to check.
  const runningProvider =
    setup.providerName === ''
      ? text(
          providerRecords.find((record) => flag(record, 'configured')),
          'provider_id',
        )
      : setup.providerName;

  const detail =
    chosen === ''
      ? undefined
      : dataOf(
          await optionalRead('/v1/providers/{provider_id}', () =>
            read('/v1/providers/{provider_id}', {
              ...init,
              params: { provider_id: chosen },
            }),
          ),
        );

  const declared = new Map(
    list(dataOf(schemas), 'schemas').map((schema) => [text(schema, 'name'), schema]),
  );
  // Which connected integration an estate is discovered from. A cloud control
  // plane is what knows the whole shape of an estate — a log store does not —
  // and it has to be *configured*, because previewing a cluster nothing holds a
  // credential for would refuse for a reason the step could not explain.
  // Nothing configured leaves this empty, and the step hands over instead.
  const estateSource =
    list(dataOf(integrations), 'integrations')
      .filter(
        (record) =>
          text(record, 'category') === ESTATE_CATEGORY &&
          setup.integrations.some(
            (entry) =>
              entry.name === text(record, 'name') && entry.readiness !== 'absent',
          ),
      )
      .map((record) => text(record, 'name'))
      .at(0) ?? '';

  const offers: readonly IntegrationOffer[] = list(
    dataOf(integrations),
    'integrations',
  ).map((record) => {
    const name = text(record, 'name');
    const schema = declared.get(name);
    return {
      name,
      displayName: schema === undefined ? name : text(schema, 'display_name'),
      summary: text(record, 'summary'),
      category: text(record, 'category'),
      // The node's own declared schema when the deployment serves one, and
      // the catalogue's own structured fields when it does not. A deployment
      // whose node holds no configuration yet still has to be connectable.
      fields:
        schema === undefined
          ? fieldsOf(record, 'fields')
          : fieldsOf(schema, 'credential_fields'),
      configured: setup.integrations.some(
        (entry) => entry.name === name && entry.readiness !== 'absent',
      ),
      suggested: suggestionOf(record),
    };
  });

  const verifiable: readonly VerifiableThing[] = [
    ...(setup.provider === 'absent'
      ? []
      : [
          {
            kind: 'provider' as const,
            name: chosen,
            displayName: text(
              providerRecords.find((record) => text(record, 'provider_id') === chosen),
              'display_name',
            ),
            readiness: setup.provider,
          },
        ]),
    // The chosen provider is excluded here for the reason it is excluded from
    // `established` below: a provider that is also a catalogue integration —
    // Gemini both drives investigations and appears in the catalogue — is one
    // stored credential and one thing to check. Listed twice it read as
    // "Google Gemini" and "google_gemini", two rows an operator has to check
    // separately, one of which is the same key under its internal name.
    ...configuredIntegrations(setup)
      .filter((entry) => entry.name !== runningProvider)
      .map((entry) => ({
        kind: 'integration' as const,
        name: entry.name,
        displayName:
          offers.find((offer) => offer.name === entry.name)?.displayName ?? entry.name,
        readiness: entry.readiness,
      })),
  ];

  // Everything this deployment actually holds a credential for, provider
  // included. "Ticked" and "established" are different claims and this is the
  // second one.
  //
  // The chosen provider is excluded from the integrations spread below rather
  // than left to collide: a provider that is also a generic integration —
  // Gemini both drives investigations and appears in the integration
  // catalogue — is one stored credential, not two, and this list claims to
  // show what is established, not how many places a fact is recorded.
  const established: readonly {
    name: string;
    displayName: string;
    readiness: string;
  }[] = [
    ...(setup.provider === 'absent'
      ? []
      : [
          {
            name: chosen === '' ? 'provider' : chosen,
            displayName: text(
              providerRecords.find((record) => text(record, 'provider_id') === chosen),
              'display_name',
            ),
            readiness: setup.provider,
          },
        ]),
    ...configuredIntegrations(setup)
      .filter((entry) => entry.name !== runningProvider)
      .map((entry) => ({
        ...entry,
        displayName:
          offers.find((offer) => offer.name === entry.name)?.displayName ?? entry.name,
      })),
  ];

  const stepTitle = (step: WizardStep): string =>
    message(locale, `firstRun.step.${step}`);

  // A heading is a claim about the list under it, so it changes when the list
  // does: "What is left" over "7 of 7 done" is two claims disagreeing. Picked
  // from outstanding(setup) and setup.steps.length — the exact numbers the
  // progress line below already reads — rather than from a tally of the
  // console's own seven screens, which is a second count with a different
  // denominator (the checklist route's own steps) and can disagree with the
  // first by construction.
  const checklistHeading = message(
    locale,
    checklistTitle(setup.steps.length - outstanding(setup), setup.steps.length),
  );

  // What the seven steps above have no page of their own for: whether this
  // process actually holds a runtime to drive an investigation with. `undefined`
  // once it does, or on a deployment whose checklist has not been asked — the
  // honest default, since a step this screen cannot find is not a blocker this
  // screen can name.
  const runtimeStep = setup.steps.find((step) => step.name === RUNTIME_STEP);
  const runtimeGap =
    runtimeStep !== undefined && runtimeStep.state !== 'done' ? runtimeStep : undefined;

  // The final state: every step but the last is done, the runtime is not
  // what is blocking it, and no investigation has finished yet. Distinct
  // from `setup.complete`, which cannot be true until an investigation
  // *has* finished — this is the moment right before that, and the only one
  // where "you are ready to run your first one" is actually true rather
  // than stale.
  const alertsStepDone = plan.find((entry) => entry.step === 'alerts')?.done ?? false;
  const readyForFirstInvestigation =
    here === 'alerts' && runtimeGap === undefined && !alertsStepDone;
  const mayInvestigate = may(viewer, 'investigation.run');

  return (
    <>
      <AreaHeader area={areaFor('first-run')} locale={locale} />

      {/* A position, not a count: which of the console's own seven screens
          this is, and by name. The progress line inside the steps panel below
          states a different, checklist-sourced count and the two are allowed
          to cite different numbers because they measure different things —
          this is the wizard's own denominator, said as what it is. */}
      <p className="mb-4 text-meta text-muted" data-testid="wizard-position">
        {message(locale, 'firstRun.wizard.position', {
          n: formatNumber(locale, WIZARD_STEPS.indexOf(here) + 1),
          total: formatNumber(locale, WIZARD_STEPS.length),
          name: stepTitle(here),
        })}
      </p>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="flex flex-col gap-5 min-w-0">
          <Panel
            title={checklistHeading}
            state={stateOf(checklist, false)}
            dependency={dependencyOf(checklist)}
            labels={panelLabels(locale, checklistHeading)}
            empty={{
              heading: message(locale, 'firstRun.steps.empty.heading'),
              body: message(locale, 'firstRun.steps.empty.body'),
              actionLabel: message(locale, 'firstRun.steps.empty.action'),
              href: '/',
            }}
          >
            <p className="mb-3 text-meta text-muted" data-testid="first-run-progress">
              {message(locale, 'firstRun.progress', {
                left: formatNumber(locale, outstanding(setup)),
                total: formatNumber(locale, setup.steps.length),
              })}
            </p>
            <ol className="flex flex-col gap-1">
              {plan.map((entry) => (
                <li
                  key={entry.step}
                  // The current step is the one carrier of "you are here" this
                  // panel has: a done/pending status dot says what has happened,
                  // never where somebody is now, and without this every entry
                  // that is not yet done looked the same as every other one.
                  className={cx(
                    'flex items-center gap-2 rounded-2 px-2 py-1',
                    entry.current ? 'bg-sunken edge border-border-strong' : '',
                  )}
                >
                  {/* Every step is a link, including the ones already done:
                      reopening a completed step is a navigation rather than a
                      mode, so it survives a reload and can be sent to a
                      colleague. */}
                  <Link
                    href={entry.href}
                    data-testid="wizard-step"
                    data-step={entry.step}
                    data-done={entry.done}
                    data-current={entry.current}
                  >
                    <StatusDot status={entry.done ? 'healthy' : 'unknown'} />
                    {stepTitle(entry.step)}
                  </Link>
                  {/* The map spec.md asks for: which screen a step that hands
                      over actually leads to, named beside the step rather
                      than discovered by finishing it. Absent for the five
                      steps that stay on this one wizard. */}
                  {handoverScreen(locale, entry.step) === '' ? null : (
                    <span
                      className="text-meta text-muted"
                      data-testid="wizard-step-screen"
                      data-step={entry.step}
                    >
                      {message(locale, 'firstRun.step.onScreen', {
                        screen: handoverScreen(locale, entry.step),
                      })}
                    </span>
                  )}
                  {entry.current ? (
                    <span
                      data-testid="wizard-step-here"
                      className="ml-auto text-micro text-accent"
                    >
                      {message(locale, 'firstRun.step.here')}
                    </span>
                  ) : null}
                </li>
              ))}
            </ol>
          </Panel>

          {/* What has actually been established, as distinct from what has been
              ticked. On a deployment where nothing has, this is the panel that
              says so and names the step that changes it. */}
          <Panel
            title={message(locale, 'firstRun.established.title')}
            state={stateOf(checklist, established.length === 0)}
            dependency={dependencyOf(checklist)}
            labels={panelLabels(locale, message(locale, 'firstRun.established.title'))}
            empty={{
              heading: message(locale, 'firstRun.established.empty.heading'),
              body: message(locale, 'firstRun.established.empty.body'),
              actionLabel: message(locale, 'firstRun.established.empty.action'),
              href: '/first-run?step=provider',
            }}
          >
            <ul className="flex flex-col gap-1 text-small" data-testid="established">
              {established.map((entry) => (
                <li key={entry.name} className="flex items-center gap-2">
                  <span className="min-w-0 truncate">
                    {entry.displayName === '' ? entry.name : entry.displayName}
                  </span>
                  <span className="ml-auto">
                    <StatusChip locale={locale} status={entry.readiness} />
                  </span>
                </li>
              ))}
            </ul>
          </Panel>
        </div>

        <div className="lg:col-span-2 min-w-0">
          <Panel
            title={stepTitle(here)}
            state={stateOf(here === 'provider' ? providers : checklist, false)}
            dependency={dependencyOf(here === 'provider' ? providers : checklist)}
            labels={panelLabels(locale, stepTitle(here))}
            empty={{
              heading: message(locale, 'firstRun.steps.empty.heading'),
              body: message(locale, 'firstRun.steps.empty.body'),
              actionLabel: message(locale, 'firstRun.steps.empty.action'),
              href: '/',
            }}
          >
            <div
              data-testid="wizard-body"
              data-step={here}
              className="flex flex-col gap-4"
            >
              <p className="text-small text-muted">
                {message(locale, `firstRun.why.${here}`)}
              </p>

              {here === 'provider' ? (
                <ul className="flex flex-col gap-3" data-testid="provider-choice">
                  {providerRecords.map((record) => {
                    const id = text(record, 'provider_id');
                    return (
                      <li
                        key={id}
                        data-testid="provider-option"
                        data-provider={id}
                        data-local={flag(record, 'local')}
                        // Every provider is drawn the same way, the local one
                        // included. A listing that gave one of them a heading
                        // of its own would make the others look like the
                        // choice somebody had to go and find.
                        className="flex flex-col gap-1 rounded-3 edge border-border p-3"
                      >
                        <span className="flex flex-wrap items-center gap-2">
                          <span className="text-strong">
                            {text(record, 'display_name')}
                          </span>
                          <span
                            className="text-meta text-muted"
                            data-testid="provider-siting"
                          >
                            {message(
                              locale,
                              flag(record, 'local')
                                ? 'firstRun.provider.local'
                                : 'firstRun.provider.hosted',
                            )}
                          </span>
                        </span>
                        <span
                          className="text-meta text-muted"
                          data-testid="provider-guidance"
                        >
                          {text(record, 'detail')}
                        </span>
                        <Link
                          href={`/first-run?step=credential&provider=${encodeURIComponent(id)}`}
                          data-testid="choose-provider"
                        >
                          {message(locale, 'firstRun.provider.choose')}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              ) : null}

              {here === 'credential' ? (
                chosen === '' ? (
                  <p className="text-meta text-muted" data-testid="no-provider-chosen">
                    {message(locale, 'firstRun.credential.chooseFirst')}{' '}
                    <Link href="/first-run?step=provider">
                      {message(locale, 'firstRun.step.provider')}
                    </Link>
                  </p>
                ) : (
                  <>
                    <p
                      className="text-small text-muted"
                      data-testid="provider-guidance-detail"
                    >
                      {text(detail, 'guidance')}
                    </p>
                    <CredentialField
                      integration={chosen}
                      fields={fieldsOf(detail, 'fields')}
                      whereToGetIt={text(detail, 'where_to_get_it')}
                      labels={credentialLabels(locale)}
                    />
                  </>
                )
              ) : null}

              {here === 'model' ? (
                chosen === '' ? (
                  <p className="text-meta text-muted" data-testid="no-provider-chosen">
                    {message(locale, 'firstRun.credential.chooseFirst')}{' '}
                    <Link href="/first-run?step=provider">
                      {message(locale, 'firstRun.step.provider')}
                    </Link>
                  </p>
                ) : (
                  <ModelStep
                    provider={chosen}
                    models={list(detail, 'models').map(String)}
                    defaultModel={text(detail, 'default_model')}
                    nodeId={node}
                    labels={{
                      known: message(locale, 'firstRun.model.known'),
                      free: message(locale, 'firstRun.model.free'),
                      preview: message(locale, 'firstRun.model.preview'),
                      previewing: message(locale, 'firstRun.model.previewing'),
                      save: message(locale, 'firstRun.model.save'),
                      saving: message(locale, 'firstRun.model.saving'),
                      wouldChange: message(locale, 'firstRun.model.wouldChange'),
                      nothingWouldChange: message(
                        locale,
                        'firstRun.model.nothingWouldChange',
                      ),
                      saved: message(locale, 'firstRun.model.saved'),
                      refused: message(locale, 'firstRun.refused'),
                      unreachable: message(locale, 'firstRun.unreachable'),
                      needsPreview: message(locale, 'firstRun.model.needsPreview'),
                    }}
                  />
                )
              ) : null}

              {here === 'integrations' ? (
                <IntegrationsStep
                  offers={offers}
                  labels={{
                    search: message(locale, 'firstRun.integrations.search'),
                    none: message(locale, 'firstRun.integrations.none'),
                    connected: message(locale, 'firstRun.integrations.connected'),
                    notConnected: message(locale, 'firstRun.integrations.notConnected'),
                    optional: message(locale, 'firstRun.integrations.optional'),
                    summary: message(locale, 'firstRun.integrations.summary'),
                    summaryNone: message(locale, 'firstRun.integrations.summaryNone'),
                    failed: message(locale, 'firstRun.integrations.failed'),
                    foundHere: message(locale, 'firstRun.integrations.foundHere'),
                    credential: credentialLabels(locale),
                  }}
                />
              ) : null}

              {here === 'verify' ? (
                <VerifyStep
                  locale={locale}
                  things={verifiable}
                  labels={verifyLabels(locale)}
                />
              ) : null}

              {/* "Continue anyway": available whenever verification is not
                  done and nothing about it blocks moving on. The pending
                  count is read from `verifiable` — the same single-source
                  list VerifyStep itself renders — never from what this
                  browser session has or has not tried checking, which is
                  what keeps this a fourth reading of one fact rather than a
                  count of its own. */}
              {here === 'verify' &&
              verifiable.length > 0 &&
              !stepDone('verify', setup) &&
              !stepBlocking('verify', setup) ? (
                <div
                  data-testid="verify-continue-anyway"
                  className="flex flex-wrap items-center justify-between gap-3 rounded-3 edge border-border p-3"
                >
                  <p className="text-meta text-muted" data-testid="verify-pending">
                    {message(locale, 'firstRun.verify.pending', {
                      count: formatNumber(
                        locale,
                        verifiable.filter((thing) => thing.readiness !== 'verified')
                          .length,
                      ),
                      total: formatNumber(locale, verifiable.length),
                    })}
                  </p>
                  <Link
                    href={hrefFor(nextStep('verify') ?? 'estate')}
                    data-testid="continue-anyway"
                  >
                    {message(locale, 'firstRun.verify.continueAnyway')}
                  </Link>
                </div>
              ) : null}

              {here === 'estate' && estateSource !== '' ? (
                <EstateStep
                  integration={estateSource}
                  zones={{}}
                  labels={{
                    integration: message(locale, 'firstRun.estate.integration'),
                    check: message(locale, 'firstRun.estate.check'),
                    checking: message(locale, 'firstRun.estate.checking'),
                    recheck: message(locale, 'firstRun.estate.recheck'),
                    sufficient: message(locale, 'firstRun.estate.sufficient'),
                    insufficient: message(locale, 'firstRun.estate.insufficient'),
                    missingRead: message(locale, 'firstRun.estate.missingRead'),
                    missingAdvisory: message(locale, 'firstRun.estate.missingAdvisory'),
                    grantedAt: message(locale, 'firstRun.estate.grantedAt'),
                    preview: message(locale, 'firstRun.estate.preview'),
                    previewing: message(locale, 'firstRun.estate.previewing'),
                    found: message(locale, 'firstRun.estate.found'),
                    unplaced: message(locale, 'firstRun.estate.unplaced'),
                    incomplete: message(locale, 'firstRun.estate.incomplete'),
                    confirm: message(locale, 'firstRun.estate.confirm'),
                    confirming: message(locale, 'firstRun.estate.confirming'),
                    confirmed: message(locale, 'firstRun.estate.confirmed'),
                    needsPreview: message(locale, 'firstRun.estate.needsPreview'),
                    refused: message(locale, 'firstRun.refused'),
                    unreachable: message(locale, 'firstRun.unreachable'),
                  }}
                />
              ) : null}

              {/* The dependency none of the seven steps above names: a runtime
                  composed by whoever operates this deployment, which is not a
                  configuration field and so has no step of its own to be
                  "done" on. Read from the checklist's own fifth step and shown
                  once nothing else is left, so a deployment stuck here is told
                  what is actually stopping it rather than left to discover it
                  by pressing Investigate and reading an exception. Absent once
                  this process actually holds one. */}
              {here === 'alerts' && runtimeGap !== undefined ? (
                <div
                  data-testid="runtime-gap"
                  className="flex flex-col gap-2 rounded-3 edge border-border-strong p-3"
                >
                  <p className="text-strong" data-testid="runtime-gap-heading">
                    {message(locale, 'firstRun.runtimeGap.heading')}
                  </p>
                  <p className="text-small text-muted" data-testid="runtime-gap-detail">
                    {runtimeGap.detail ?? ''}
                  </p>
                  <p className="text-small text-muted" data-testid="runtime-gap-action">
                    {runtimeGap.action ?? ''}
                  </p>
                </div>
              ) : null}

              {/* The final state spec.md asks for: nothing left but pressing
                  Investigate. Superseding the generic handover below rather
                  than sitting beside it — both would say "start an
                  investigation" in two different voices, and this is also
                  the one place a viewer who may not start one is told to ask
                  somebody who can, rather than pointed at a control that is
                  not in the DOM for them. */}
              {readyForFirstInvestigation ? (
                <div
                  data-testid="setup-complete"
                  className="flex flex-col gap-2 rounded-3 edge border-success p-3"
                >
                  <p className="text-strong" data-testid="setup-complete-heading">
                    {message(locale, 'firstRun.complete.heading')}
                  </p>
                  <p
                    className="text-small text-muted"
                    data-testid="setup-complete-body"
                  >
                    {message(
                      locale,
                      mayInvestigate
                        ? 'firstRun.complete.body'
                        : 'firstRun.complete.body.noPermission',
                    )}
                  </p>
                  {/* What the conclusion resumes: what got configured, by
                      display name and by the canonical state — the same
                      claim `established` already makes, reused rather than
                      restated in different words. */}
                  <ul
                    className="flex flex-col gap-1 text-small"
                    data-testid="setup-complete-summary"
                  >
                    {established.map((entry) => (
                      <li key={entry.name} className="flex items-center gap-2">
                        <span className="min-w-0 truncate">
                          {entry.displayName === '' ? entry.name : entry.displayName}
                        </span>
                        <span className="ml-auto">
                          <StatusChip locale={locale} status={entry.readiness} />
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {(here === 'estate' && estateSource === '') ||
              (here === 'alerts' && !readyForFirstInvestigation) ? (
                <div
                  data-testid="handover"
                  data-step={here}
                  className="flex flex-col gap-2"
                >
                  <p className="text-small text-muted" data-testid="handover-detail">
                    {
                      detailOf(
                        setup,
                        here === 'estate' ? SOURCE_STEP : INVESTIGATION_STEP,
                      ).detail
                    }
                  </p>
                  <p className="text-small text-muted" data-testid="handover-action">
                    {
                      detailOf(
                        setup,
                        here === 'estate' ? SOURCE_STEP : INVESTIGATION_STEP,
                      ).action
                    }
                  </p>
                  <Link href={handoverHref(here)} data-testid="handover-link">
                    {message(locale, `firstRun.handover.${here}`)}
                  </Link>
                </div>
              ) : null}
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
