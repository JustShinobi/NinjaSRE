import type { ReactNode } from 'react';

import { Link } from '@/components/action';
import { StatusDot } from '@/components/status';
import { message } from '@/i18n/messages';
import { formatNumber } from '@/i18n/format';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import { checklistTitle } from './first-run-heading';
import { credentialLabels, panelLabels } from '../labels';
import { Panel } from '../panel';
import { CredentialField, type CredentialFieldSpec } from '../credential';
import { EstateStep } from '../first-run/estate';
import { IntegrationsStep, type IntegrationOffer } from '../first-run/integrations';
import { ModelStep } from '../first-run/model';
import { VerifyStep, type VerifiableThing } from '../first-run/verify';
import {
  INVESTIGATION_STEP,
  SOURCE_STEP,
  WIZARD_STEPS,
  configuredIntegrations,
  currentStep,
  planFor,
  readSetup,
  type DeploymentSetup,
  type WizardStep,
} from '../first-run/plan';
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

const HANDOVER: Readonly<Record<'estate' | 'alerts', string>> = {
  estate: '/resources',
  alerts: '/detectors',
};

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
  const node = viewer.teamNodeId;

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
      // The declared schema when the deployment serves one, and the names the
      // catalogue lists when it does not. A deployment whose node holds no
      // configuration yet still has to be connectable.
      fields:
        schema === undefined
          ? list(record, 'required_credentials').map((required) => ({
              name: String(required),
              label: String(required),
              help: '',
              secret: true,
              required: true,
            }))
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
    ...configuredIntegrations(setup).map((entry) => ({
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
  const established: readonly { name: string; readiness: string }[] = [
    ...(setup.provider === 'absent'
      ? []
      : [{ name: chosen === '' ? 'provider' : chosen, readiness: setup.provider }]),
    ...configuredIntegrations(setup),
  ];

  const stepTitle = (step: WizardStep): string =>
    message(locale, `firstRun.step.${step}`);

  // A heading is a claim about the list under it, so it changes when the list
  // does: "What is left" over "7 of 7 done" is two claims disagreeing.
  const checklistHeading = message(
    locale,
    checklistTitle(plan.filter((entry) => entry.done).length, WIZARD_STEPS.length),
  );

  return (
    <>
      <AreaHeader area={areaFor('first-run')} locale={locale} />

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
                done: formatNumber(locale, plan.filter((entry) => entry.done).length),
                total: formatNumber(locale, WIZARD_STEPS.length),
              })}
            </p>
            <ol className="flex flex-col gap-1">
              {plan.map((entry) => (
                <li key={entry.step}>
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
                  <StatusDot
                    status={entry.readiness === 'verified' ? 'healthy' : 'unknown'}
                  />
                  <span className="min-w-0 truncate">{entry.name}</span>
                  <span className="ml-auto text-meta text-muted">
                    {message(
                      locale,
                      entry.readiness === 'verified'
                        ? 'firstRun.established.verified'
                        : 'firstRun.established.configured',
                    )}
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
                  things={verifiable}
                  labels={{
                    check: message(locale, 'firstRun.verify.check'),
                    checking: message(locale, 'firstRun.verify.checking'),
                    retry: message(locale, 'firstRun.verify.retry'),
                    passed: message(locale, 'firstRun.verify.passed'),
                    failed: message(locale, 'firstRun.verify.failed'),
                    unchecked: message(locale, 'firstRun.verify.unchecked'),
                    unreachable: message(locale, 'firstRun.unreachable'),
                    nothing: message(locale, 'firstRun.verify.nothing'),
                    remedy: message(locale, 'firstRun.verify.remedy'),
                    findings: message(locale, 'firstRun.verify.findings'),
                  }}
                />
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

              {(here === 'estate' && estateSource === '') || here === 'alerts' ? (
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
                  <Link href={HANDOVER[here]} data-testid="handover-link">
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
