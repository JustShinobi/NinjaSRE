import type { ReactNode } from 'react';

import type { MessageKey } from '@/i18n/en';
import { message } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { SettingsPageHeader } from '@/shell/area';
import { settingsPageFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { AdvancedConfigSection } from '../advanced-config-section';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import {
  authorised,
  dataOf,
  dependencyOf,
  flag,
  list,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { SsoSetupFlow } from '../sso-setup';
import { SSO_FIELDS, type SsoField } from '../sso-fields';
import { placedTree } from '../tree';
import { readViewState, resolveNode, type FilterName } from '../url-state';

/**
 * Single sign-on, on its own page and as a flow.
 *
 * The eight-field form this replaces (`administration.tsx`'s own, still
 * mounted there until that screen is retired) already posts through the same
 * three routes and the same state machine `SsoSetupFlow` keeps — see that
 * module's own doc for why nothing about validity, verification or
 * activation changes here. What this page adds is the console making that
 * contract legible: configure, test, activate as three sections instead of
 * one undifferentiated form, a sentence with every field saying what it is,
 * the test's own answer broken into the claims it resolved, and the local
 * fallback declared rather than assumed.
 */

const ID = 'settings-single-sign-on';

/** The permission the gateway requires to change this deployment's configuration. */
const WRITE = 'config.write';

const SSO_ADVANCED_FILTERS: readonly FilterName[] = ['node'];

/**
 * The four claim names, with no control of their own before this: which
 * piece of the sign-in token carries which fact. Technical, provider-specific
 * and rare to change once set, which is why they sit in a collapsed section
 * beneath the configure/test/activate flow rather than inside it.
 */
const SSO_CLAIMS_ADVANCED_PREFIX = 'policies.sso.claims.';

const SSO_CLAIMS_ADVANCED_FIELD_LIST: readonly {
  readonly path: string;
  readonly label: MessageKey;
}[] = [
  {
    path: 'policies.sso.claims.subject',
    label: 'settings.sso.advanced.field.claimsSubject',
  },
  {
    path: 'policies.sso.claims.email',
    label: 'settings.sso.advanced.field.claimsEmail',
  },
  {
    path: 'policies.sso.claims.display_name',
    label: 'settings.sso.advanced.field.claimsDisplayName',
  },
  {
    path: 'policies.sso.claims.groups',
    label: 'settings.sso.advanced.field.claimsGroups',
  },
];

async function content(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer, search } = context;

  const answer = await panelRead('/identity/sso', () =>
    read('/identity/sso', authorised(credential)),
  );
  const data = dataOf(answer);

  const settings: Record<SsoField, string> = Object.fromEntries(
    SSO_FIELDS.map((field) => [field, text(data, field)]),
  ) as Record<SsoField, string>;

  const init = authorised(credential);
  const writable = may(viewer, WRITE);
  const state = readViewState(search, SSO_ADVANCED_FILTERS);
  const tree = await panelRead('/v1/config', () => read('/v1/config', init));
  const nodeId = resolveNode(state, viewer, placedTree(dataOf(tree)));

  // Nothing empty, ready: the claim rows still render, blank, for a node this
  // deployment has not overridden any claim mapping at. Read regardless of
  // `writable` — the effective-value table shows every viewer of this page
  // what each claim resolves to, not only one who may change it.
  const nothing = { status: 'ready' as const, data: {} as unknown };
  const configFields =
    nodeId === ''
      ? nothing
      : await panelRead<unknown>('/v1/config/{node_id}/fields', () =>
          read('/v1/config/{node_id}/fields', { ...init, params: { node_id: nodeId } }),
        );

  return (
    <>
      <Panel
        title={message(locale, 'admin.sso.title')}
        state={stateOf(answer, false)}
        dependency={dependencyOf(answer)}
        labels={panelLabels(locale, message(locale, 'admin.sso.title'))}
        empty={{
          heading: message(locale, 'admin.sso.configure'),
          body: message(locale, 'settings.page.singleSignOn.context'),
          actionLabel: message(locale, 'admin.sso.configure'),
          href: '/settings/single-sign-on',
        }}
      >
        <SsoSetupFlow
          settings={settings}
          isActive={flag(data, 'is_active')}
          verified={flag(data, 'verified')}
          problems={list(data, 'problems').map(String)}
          labels={{
            field: {
              provider: message(locale, 'admin.sso.provider'),
              issuer: message(locale, 'admin.sso.issuer'),
              client_id: message(locale, 'admin.sso.clientId'),
              authorisation_endpoint: message(locale, 'admin.sso.authorisation'),
              token_endpoint: message(locale, 'admin.sso.token'),
              jwks_uri: message(locale, 'admin.sso.jwks'),
              redirect_uri: message(locale, 'admin.sso.redirect'),
              default_node_id: message(locale, 'admin.sso.defaultNode'),
            },
            fieldHelp: {
              provider: message(locale, 'settings.sso.field.provider.help'),
              issuer: message(locale, 'settings.sso.field.issuer.help'),
              client_id: message(locale, 'settings.sso.field.clientId.help'),
              authorisation_endpoint: message(
                locale,
                'settings.sso.field.authorisation.help',
              ),
              token_endpoint: message(locale, 'settings.sso.field.token.help'),
              jwks_uri: message(locale, 'settings.sso.field.jwks.help'),
              redirect_uri: message(locale, 'settings.sso.field.redirect.help'),
              default_node_id: message(locale, 'settings.sso.field.defaultNode.help'),
            },
            stepConfigure: message(locale, 'settings.sso.step.configure'),
            stepTest: message(locale, 'settings.sso.step.test'),
            stepActivate: message(locale, 'settings.sso.step.activate'),
            save: message(locale, 'admin.sso.save'),
            saving: message(locale, 'admin.sso.saving'),
            test: message(locale, 'admin.sso.test'),
            testing: message(locale, 'admin.sso.testing'),
            claims: message(locale, 'admin.sso.claims'),
            claimsHelp: message(locale, 'admin.sso.claimsHelp'),
            activate: message(locale, 'admin.sso.activate'),
            activating: message(locale, 'admin.sso.activating'),
            active: message(locale, 'admin.sso.active'),
            verified: message(locale, 'admin.sso.verified'),
            notVerified: message(locale, 'admin.sso.notVerified'),
            notConfigured: message(locale, 'admin.sso.notConfigured'),
            testFirst: message(locale, 'admin.sso.testFirst'),
            pendingEdit: message(locale, 'admin.sso.pendingEdit'),
            failed: message(locale, 'admin.sso.failed'),
            unreachable: message(locale, 'admin.sso.unreachable'),
            problems: message(locale, 'admin.sso.problems'),
            resultSubject: message(locale, 'settings.sso.result.subject'),
            resultEmail: message(locale, 'settings.sso.result.email'),
            resultTeam: message(locale, 'settings.sso.result.team'),
            resultTeamDefault: message(locale, 'settings.sso.result.team.default'),
            resultFailed: message(locale, 'settings.sso.result.failed'),
            fallback: message(locale, 'settings.sso.fallback'),
          }}
        />
      </Panel>

      <div className="mt-5">
        <AdvancedConfigSection
          title={message(locale, 'settings.sso.advanced.title')}
          prefix={SSO_CLAIMS_ADVANCED_PREFIX}
          nodeId={nodeId}
          locale={locale}
          writable={writable}
          fields={SSO_CLAIMS_ADVANCED_FIELD_LIST.map(({ path, label }) => ({
            path,
            label: message(locale, label),
          }))}
          rawFields={dataOf(configFields)}
        />
      </div>
    </>
  );
}

export async function SingleSignOnScreen(context: SurfaceContext): Promise<ReactNode> {
  return (
    <>
      <SettingsPageHeader page={settingsPageFor(ID)} locale={context.locale} />
      {await content(context)}
    </>
  );
}
