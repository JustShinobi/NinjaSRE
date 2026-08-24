import type { ReactNode } from 'react';

import type { MessageKey } from '@/i18n/en';
import { message } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { SettingsPageHeader } from '@/shell/area';
import { settingsPageFor } from '@/shell/routes';
import { provenanceLabel } from '@/design/provenance-label';
import type { SurfaceContext } from '../context';
import { readSetupState } from '../emptiness';
import { requestedSetupReturn, SetupReturnBanner } from '../first-run/return-banner';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import {
  authorised,
  dataOf,
  dependencyOf,
  field,
  list,
  pairs,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { ModelsEditor, type ProviderOption, type RoleValue } from './models-editor';
import { valueAt } from './values';
import { placedTree } from '../tree';
import { readViewState, resolveNode, type FilterName } from '../url-state';

/**
 * Which model drives an investigation, and the eight roles that may each run
 * on their own — covering the `models.*` schema group whole, in one page.
 *
 * The investigator's own choice is the whole reason this page exists (spec's
 * own motivation: it is the one setting the guided setup's own verification
 * diagnosis sends an operator to fix, and today that destination is 38
 * accordions deep in the raw editor). The seven advanced roles are the same
 * shape, collapsed, because they cost a reader nothing until asked for.
 *
 * **Nothing here recomputes what "bound" means.** A role's provider and model
 * are bound — chosen on purpose rather than falling through to the deployment
 * default — exactly when `GET /v1/config/{node_id}` reports provenance for
 * it; that is the same fact `ModelsConfig.bound_roles` computes server-side,
 * read back rather than reconstructed.
 */

export const MODELS_FILTERS: readonly FilterName[] = ['node'];

/** The permission that decides whether the editor is on the page at all. */
const WRITE = 'config.write';

/** The eight roles, investigator first: `config/constants/config_service.py`'s `MODEL_ROLES`. */
const ROLES = [
  'investigator',
  'subagent',
  'intake',
  'diagnose',
  'extraction',
  'embedding',
  'selection',
  'summarisation',
] as const;

/** The catalogue key naming one role, in the console's own words. */
const ROLE_LABEL: Readonly<Record<(typeof ROLES)[number], MessageKey>> = {
  investigator: 'settings.models.role.investigator',
  subagent: 'settings.models.role.subagent',
  intake: 'settings.models.role.intake',
  diagnose: 'settings.models.role.diagnose',
  extraction: 'settings.models.role.extraction',
  embedding: 'settings.models.role.embedding',
  selection: 'settings.models.role.selection',
  summarisation: 'settings.models.role.summarisation',
};

/** One provider's model list, joined to what the registry knows about tool calling. */
function modelsOf(detail: unknown): ProviderOption['models'] {
  const capabilities = list(detail, 'model_capabilities');
  if (capabilities.length > 0) {
    return capabilities.map((entry) => ({
      modelId: text(entry, 'model_id'),
      supportsTools:
        field(entry, 'supports_tools') === true
          ? true
          : field(entry, 'supports_tools') === false
            ? false
            : null,
    }));
  }
  // A provider whose onboarding names no models (an operator types one in) —
  // `first-run/model.tsx` takes the same free-field branch for the same fact.
  return list(detail, 'models').map((modelId) => ({
    modelId: typeof modelId === 'string' ? modelId : '',
    supportsTools: null,
  }));
}

export async function ModelsSettingsScreen(
  context: SurfaceContext,
): Promise<ReactNode> {
  const { credential, locale, viewer, search } = context;
  const state = readViewState(search, MODELS_FILTERS);
  const init = authorised(credential);
  const writable = may(viewer, WRITE);

  const tree = await panelRead('/v1/config', () => read('/v1/config', init));
  const nodeId = resolveNode(state, viewer, placedTree(dataOf(tree)));

  const nothing = { status: 'ready' as const, data: {} as unknown };
  const effective =
    nodeId === ''
      ? nothing
      : await panelRead<unknown>('/v1/config/{node_id}', () =>
          read('/v1/config/{node_id}', { ...init, params: { node_id: nodeId } }),
        );

  const providersList = await panelRead('/v1/providers', () =>
    read('/v1/providers', init),
  );
  const providerIds = list(dataOf(providersList), 'providers').map((entry) =>
    text(entry, 'provider_id'),
  );

  // `Promise.allSettled`, not `Promise.all`: nine independent reads, one per
  // provider, and one provider's own hiccup must not blank the whole panel —
  // the same "a dependency that fails takes down its own region, never the
  // page" rule as everywhere else, applied one level inside a single panel's
  // own fetch instead of only between panels.
  const details = await panelRead<readonly unknown[]>(
    '/v1/providers/{provider_id}',
    async () => {
      const settled = await Promise.allSettled(
        providerIds.map((providerId) =>
          read('/v1/providers/{provider_id}', {
            ...init,
            params: { provider_id: providerId },
          }),
        ),
      );
      const found: unknown[] = [];
      for (const entry of settled) {
        if (entry.status === 'fulfilled') found.push(entry.value);
      }
      return found;
    },
  );

  const providers: readonly ProviderOption[] = (dataOf(details) ?? []).map(
    (detail) => ({
      providerId: text(detail, 'provider_id'),
      displayName: text(detail, 'display_name'),
      configured: field(detail, 'configured') === true,
      verified: field(detail, 'verified') === true,
      readiness: text(detail, 'readiness'),
      detail: text(detail, 'detail'),
      models: modelsOf(detail),
    }),
  );

  const values = field(dataOf(effective), 'values');
  const provenance = new Map(pairs(dataOf(effective), 'provenance'));

  const roles: readonly RoleValue[] = ROLES.map((role) => {
    const providerPath = `models.${role}.provider`;
    const modelPath = `models.${role}.model`;
    const providerValue = valueAt(values, providerPath);
    const modelValue = valueAt(values, modelPath);
    return {
      role,
      label: message(locale, ROLE_LABEL[role]),
      provider: typeof providerValue === 'string' ? providerValue : '',
      model: typeof modelValue === 'string' ? modelValue : '',
      bound: provenance.has(providerPath) || provenance.has(modelPath),
      providerOrigin: provenanceLabel(locale, providerPath, provenance),
      modelOrigin: provenanceLabel(locale, modelPath, provenance),
    };
  });

  const setup = await readSetupState(credential);
  const page = settingsPageFor('settings-models-providers');

  const empty = providers.length === 0;

  return (
    <>
      <SettingsPageHeader page={page} locale={locale} />
      <SetupReturnBanner
        locale={locale}
        setup={setup}
        requested={requestedSetupReturn(search.get('return'))}
      />

      <Panel
        title={message(locale, page.label)}
        state={
          providersList.status === 'error' || details.status === 'error'
            ? 'error'
            : nodeId === ''
              ? 'empty'
              : stateOf(details, empty)
        }
        dependency={dependencyOf(
          providersList.status === 'error' ? providersList : details,
        )}
        labels={panelLabels(locale, message(locale, page.label))}
        empty={{
          heading: message(locale, page.label),
          body: message(locale, 'settings.models.empty.body'),
          actionLabel: message(locale, 'settings.models.empty.action'),
          href: '/integrations',
        }}
      >
        <ModelsEditor
          nodeId={nodeId}
          locale={locale}
          writable={writable}
          providers={providers}
          roles={roles}
          labels={{
            provider: message(locale, 'settings.models.provider'),
            knownModel: message(locale, 'settings.models.model.known'),
            freeModel: message(locale, 'settings.models.model.free'),
            toolCallingSupported: message(
              locale,
              'settings.models.toolCalling.supported',
            ),
            toolCallingUnsupported: message(
              locale,
              'settings.models.toolCalling.unsupported',
            ),
            toolCallingUnknown: message(locale, 'settings.models.toolCalling.unknown'),
            verificationNote: message(locale, 'settings.models.verificationNote'),
            notConnected: message(locale, 'settings.models.notConnected'),
            connectCredential: message(locale, 'settings.models.connectCredential'),
            advancedTitle: message(locale, 'settings.models.advanced.title'),
            advancedLead: message(locale, 'settings.models.advanced.lead'),
            inherits: message(locale, 'settings.models.advanced.inherits'),
            revert: message(locale, 'settings.models.revert'),
            reverted: message(locale, 'settings.models.reverted'),
            saveAndVerify: message(locale, 'settings.models.saveAndVerify'),
            saving: message(locale, 'settings.models.saving'),
            testWithoutSaving: message(locale, 'settings.models.testWithoutSaving'),
            verifying: message(locale, 'settings.models.verifying'),
            verified: message(locale, 'settings.models.verified'),
            verificationFailed: message(locale, 'settings.models.verificationFailed'),
            saved: message(locale, 'settings.models.saved'),
            failed: message(locale, 'settings.models.failed'),
            unreachable: message(locale, 'settings.models.unreachable'),
            before: message(locale, 'configuration.preview.before'),
            after: message(locale, 'configuration.preview.after'),
            nothingChanges: message(locale, 'settings.models.nothingChanges'),
            origin: message(locale, 'configuration.column.provenance'),
            checkAgain: message(locale, 'settings.models.checkAgain'),
            checking: message(locale, 'settings.models.checking'),
            chooseVerifiedModel: message(locale, 'settings.models.chooseVerifiedModel'),
            reloadModels: message(locale, 'settings.models.reloadModels'),
            reloadingModels: message(locale, 'settings.models.reloadingModels'),
            staticModelsLabel: message(locale, 'settings.models.staticModelsLabel'),
            advancedSummaryAll: message(locale, 'settings.models.advanced.summaryAll'),
            advancedSummaryPartial: message(
              locale,
              'settings.models.advanced.summaryPartial',
            ),
            checkLabels: {
              credentials: message(locale, 'settings.models.check.credentials'),
              authentication: message(locale, 'settings.models.check.authentication'),
              'tool calling': message(locale, 'settings.models.check.toolCalling'),
              'structured output': message(
                locale,
                'settings.models.check.structuredOutput',
              ),
              streaming: message(locale, 'settings.models.check.streaming'),
            },
            checkConsequences: {
              credentials: message(locale, 'settings.models.consequence.credentials'),
              authentication: message(
                locale,
                'settings.models.consequence.authentication',
              ),
              'tool calling': message(
                locale,
                'settings.models.consequence.toolCalling',
              ),
              'structured output': message(
                locale,
                'settings.models.consequence.structuredOutput',
              ),
              streaming: message(locale, 'settings.models.consequence.streaming'),
            },
          }}
        />
      </Panel>
    </>
  );
}
