import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { GrantPanel, type Grant } from '../grants';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import { SsoForm, type SsoField } from '../sso';
import { TokenPanel, type IssuedToken } from '../tokens';
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

/**
 * Who exists, what they hold, and what has been issued on their behalf.
 *
 * Three panels with three permissions between them: a viewer who may read
 * principals but not manage tokens sees the first two and not the third. Absent,
 * not disabled — the panel is not in the document at all, so there is nothing to
 * tell them a capability exists that somebody else has.
 *
 * The token panel is never empty for somebody who may manage tokens: a
 * deployment with no machine tokens is exactly the deployment that needs the
 * control to issue one, and an empty state saying "none yet" with no way to
 * make one is a dead end.
 */

const TOKENS = 'token.manage';
const SSO = 'sso.manage';
const GRANTS = 'identity.write';

export async function AdministrationScreen(
  context: SurfaceContext,
): Promise<ReactNode> {
  const { credential, locale, viewer, now, zone } = context;
  const init = authorised(credential);

  const [principals, grants, roles, tokens, sso] = await Promise.all([
    panelRead('/identity/principals', () => read('/identity/principals', init)),
    panelRead('/identity/grants', () => read('/identity/grants', init)),
    // Asked for rather than compiled in. Which roles exist is the deployment's
    // answer — `tools/console_roles` gives the reason: a second copy of the
    // catalogue written in a front end is the copy that is wrong on the day
    // somebody adds a permission, and a form offering a role this build does
    // not have is a form whose every submission is refused.
    panelRead('/identity/roles', () => read('/identity/roles', init)),
    may(viewer, TOKENS)
      ? panelRead<unknown>('/identity/tokens', () => read('/identity/tokens', init))
      : Promise.resolve({ status: 'ready' as const, data: {} }),
    may(viewer, SSO)
      ? panelRead<unknown>('/identity/sso', () => read('/identity/sso', init))
      : Promise.resolve({ status: 'ready' as const, data: {} }),
  ]);

  const people = list(dataOf(principals), 'users');
  const held = list(dataOf(grants), 'grants');
  const catalogue = list(dataOf(roles), 'roles').map((role) => text(role, 'name'));
  const issued = list(dataOf(tokens), 'tokens');
  const none = message(locale, 'surface.none');

  // Field by field rather than by spreading the body: the form is driven by the
  // closed list the module declares, and a body carrying an extra key must not
  // become a control nobody wrote.
  const ssoSettings: Record<SsoField, string> = {
    provider: text(dataOf(sso), 'provider'),
    issuer: text(dataOf(sso), 'issuer'),
    client_id: text(dataOf(sso), 'client_id'),
    authorisation_endpoint: text(dataOf(sso), 'authorisation_endpoint'),
    token_endpoint: text(dataOf(sso), 'token_endpoint'),
    jwks_uri: text(dataOf(sso), 'jwks_uri'),
    redirect_uri: text(dataOf(sso), 'redirect_uri'),
    default_node_id: text(dataOf(sso), 'default_node_id'),
  };

  const emptyState = {
    heading: message(locale, 'admin.empty.heading'),
    body: message(locale, 'admin.empty.body'),
    actionLabel: message(locale, 'admin.empty.action'),
    href: '/administration',
  };

  return (
    <>
      <AreaHeader area={areaFor('administration')} locale={locale} />

      <div className="flex flex-col gap-5">
        <Panel
          title={message(locale, 'admin.principals.title')}
          state={stateOf(principals, people.length === 0)}
          dependency={dependencyOf(principals)}
          labels={panelLabels(locale, message(locale, 'admin.principals.title'))}
          empty={emptyState}
        >
          <ul className="flex flex-col gap-2 text-small">
            {people.map((person) => (
              <li
                key={text(person, 'user_id')}
                data-testid="principal"
                className="flex items-center gap-3 min-w-0"
              >
                <span className="truncate">{text(person, 'display_name')}</span>
                <span className="text-meta text-muted truncate">
                  {text(person, 'email') === '' ? none : text(person, 'email')}
                </span>
                <span className="ml-auto flex items-center gap-2">
                  <Badge status={text(person, 'kind')} />
                  <Badge status={flag(person, 'is_active') ? 'healthy' : 'disabled'} />
                </span>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel
          title={message(locale, 'admin.grants.title')}
          state={stateOf(grants, held.length === 0)}
          dependency={dependencyOf(grants)}
          labels={panelLabels(locale, message(locale, 'admin.grants.title'))}
          empty={emptyState}
        >
          <GrantPanel
            grants={held.map((grant): Grant => ({
              grantId: text(grant, 'grant_id'),
              principalId: text(grant, 'principal_id'),
              role: text(grant, 'role'),
              nodeId: text(grant, 'node_id'),
            }))}
            principals={people.map((person) => ({
              id: text(person, 'user_id'),
              label: text(person, 'display_name'),
            }))}
            roles={catalogue}
            canWrite={may(viewer, GRANTS)}
            labels={{
              principal: message(locale, 'admin.column.principal'),
              role: message(locale, 'admin.column.role'),
              node: message(locale, 'admin.column.node'),
              nodeHelp: message(locale, 'admin.grant.nodeHelp'),
              organisation: message(locale, 'admin.grant.organisation'),
              add: message(locale, 'admin.grant.add'),
              adding: message(locale, 'admin.grant.adding'),
              remove: message(locale, 'admin.grant.remove'),
              removing: message(locale, 'admin.grant.removing'),
              removeAction: message(locale, 'admin.grant.removeAction'),
              removeConsequence: message(locale, 'admin.grant.removeConsequence'),
              removeClose: message(locale, 'admin.grant.removeClose'),
              removeCancel: message(locale, 'admin.grant.removeCancel'),
              failed: message(locale, 'admin.tokens.failed'),
              unreachable: message(locale, 'admin.tokens.unreachable'),
            }}
          />
        </Panel>

        {may(viewer, TOKENS) ? (
          <Panel
            title={message(locale, 'admin.tokens.title')}
            state={stateOf(tokens, false)}
            dependency={dependencyOf(tokens)}
            labels={panelLabels(locale, message(locale, 'admin.tokens.title'))}
            empty={emptyState}
          >
            <TokenPanel
              tokens={issued.map((token): IssuedToken => {
                const expires = timestamp(locale, text(token, 'expires_at'), now, zone);
                return {
                  tokenId: text(token, 'token_id'),
                  name: text(token, 'name'),
                  scopes: list(token, 'scopes').map(String),
                  revoked: flag(token, 'revoked'),
                  expires: expires.relative,
                };
              })}
              labels={{
                name: message(locale, 'admin.tokens.name'),
                issue: message(locale, 'admin.tokens.issue'),
                issuing: message(locale, 'admin.tokens.issuing'),
                shownOnce: message(locale, 'admin.tokens.shownOnce'),
                revoke: message(locale, 'admin.tokens.revoke'),
                revoking: message(locale, 'admin.tokens.revoking'),
                revoked: message(locale, 'admin.tokens.revoked'),
                revokedGroup: message(locale, 'admin.tokens.revokedGroup'),
                revokeConsequence: message(locale, 'admin.tokens.revokeConsequence'),
                revokeConfirm: message(locale, 'admin.tokens.revokeConfirm'),
                revokeCancel: message(locale, 'admin.tokens.revokeCancel'),
                failed: message(locale, 'admin.tokens.failed'),
                unreachable: message(locale, 'admin.tokens.unreachable'),
                none: none,
              }}
            />
          </Panel>
        ) : null}

        {may(viewer, SSO) ? (
          <Panel
            title={message(locale, 'admin.sso.title')}
            state={stateOf(sso, false)}
            dependency={dependencyOf(sso)}
            labels={panelLabels(locale, message(locale, 'admin.sso.title'))}
            empty={emptyState}
          >
            <SsoForm
              settings={ssoSettings}
              isActive={flag(dataOf(sso), 'is_active')}
              verified={flag(dataOf(sso), 'verified')}
              problems={list(dataOf(sso), 'problems').map(String)}
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
                testFirst: message(locale, 'admin.sso.testFirst'),
                pendingEdit: message(locale, 'admin.sso.pendingEdit'),
                failed: message(locale, 'admin.sso.failed'),
                unreachable: message(locale, 'admin.sso.unreachable'),
                problems: message(locale, 'admin.sso.problems'),
              }}
            />
          </Panel>
        ) : null}
      </div>
    </>
  );
}
