import type { ReactNode } from 'react';

import { TabLinks } from '@/components';
import { Badge } from '@/components/status';
import { timestamp } from '@/i18n/format';
import { message, type Locale } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { GrantPanel, type Grant } from '../grants';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import { SsoForm, type SsoField } from '../sso';
import { SessionPanel, TokenPanel, type SessionEntry } from '../tokens';
// From the directive-free module, never from `../tokens`: this screen is
// resolved on the server, and a client export called from here throws the whole
// route rather than the component that asked for it.
import { isConsoleSession, type IssuedToken } from '../token-identity';
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
import { readViewState, type FilterName } from '../url-state';
import { AuditTab } from './audit';

/**
 * Who exists, what they hold, and what has been issued on their behalf.
 *
 * Four panels with three permissions between them: a viewer who may read
 * principals but not manage tokens sees the first two and not the last two.
 * Absent, not disabled — the panel is not in the document at all, so there is
 * nothing to tell them a capability exists that somebody else has.
 *
 * **Sessions and machine tokens are the same store, read as two lists.**
 * `/identity/tokens` answers with both under one shape — a browser sign-in and a
 * credential somebody minted are both, structurally, an `ApiToken` — but nobody
 * reading this screen thinks of their own browser tab as a "machine token", and
 * a token list that is mostly sign-ins is a token list nobody can audit. Every
 * record named exactly `platform/identity/local_accounts.py`'s
 * `CREDENTIAL_NAME` is a session; the panel groups those by the person they
 * belong to and ends them as a group. Everything else is a machine token, shown
 * as before.
 *
 * The token panel is never empty for somebody who may manage tokens: a
 * deployment with no machine tokens is exactly the deployment that needs the
 * control to issue one, and an empty state saying "none yet" with no way to
 * make one is a dead end.
 */

const TOKENS = 'token.manage';
const SSO = 'sso.manage';
const GRANTS = 'identity.write';

/**
 * The Principals panel's second line, for one record.
 *
 * Their email where the deployment recorded one. A service account — the
 * bootstrap administrator is the one every deployment has — is created
 * without an email by design, because it is not a person; showing "Not
 * recorded" there reads as something this deployment forgot rather than as
 * what the record actually is, so this names it instead. A blank email on a
 * record that is not a service account (which the current identity model
 * never produces, but nothing here assumes it never will) falls back to the
 * id, the same way a session with no known display name does.
 */
export function principalIdentity(locale: Locale, person: unknown): string {
  const email = text(person, 'email');
  if (email !== '') return email;
  return text(person, 'kind') === 'service_account'
    ? message(locale, 'admin.principals.serviceAccount')
    : text(person, 'user_id');
}

/** The "People" tab of Administration: who exists, and what they hold. */
async function PeopleTab(context: SurfaceContext): Promise<ReactNode> {
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
  const roleCatalogue = list(dataOf(roles), 'roles');
  const catalogue = roleCatalogue.map((role) => text(role, 'name'));
  // What each role in `catalogue` permits, keyed by its own name — composed
  // from the deployment's own permission list rather than words this console
  // maintains, for the reason `admin.grants.title`'s panel doc gives about the
  // role list itself: a second copy would be the copy that goes stale. Shown at
  // the point of choice by `GrantPanel`'s role select.
  const roleDescriptions = Object.fromEntries(
    roleCatalogue.map((role) => [
      text(role, 'name'),
      list(role, 'permissions').map(String).join(', '),
    ]),
  );
  const issued = list(dataOf(tokens), 'tokens');
  const none = message(locale, 'surface.none');

  // A person's own name where one is recorded for them, their id otherwise —
  // used to label both a grant and a browser session by who holds it.
  const principalLabel = (userId: string): string => {
    const found = people.find((person) => text(person, 'user_id') === userId);
    return found === undefined || text(found, 'display_name') === ''
      ? userId
      : text(found, 'display_name');
  };

  // A browser sign-in and a machine credential are the same record, structurally
  // — see the panel doc above — split here so each list only ever holds what it
  // says it holds.
  const sessionTokens = issued.filter((token) =>
    isConsoleSession({ name: text(token, 'name') }),
  );
  const machineTokens = issued.filter(
    (token) => !isConsoleSession({ name: text(token, 'name') }),
  );
  // Ended sessions are not shown here at all: this panel is for deciding who is
  // currently signed in, and a session's history belongs to the audit trail
  // rather than to a list an operator is triaging live access from.
  const liveSessions: readonly SessionEntry[] = sessionTokens
    .filter((token) => !flag(token, 'revoked'))
    .map((token) => ({
      tokenId: text(token, 'token_id'),
      principalId: text(token, 'user_id'),
      principalLabel: principalLabel(text(token, 'user_id')),
      expires: timestamp(locale, text(token, 'expires_at'), now, zone).relative,
    }));

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
                  {principalIdentity(locale, person)}
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
            roleDescriptions={roleDescriptions}
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
          // Titled "Active" rather than "Sessions": this console has a column
          // header (`admin.column.active`) for exactly this idea and no panel
          // title for it yet. A dedicated `admin.sessions.title` — "Active
          // sessions" — is the better word and is reported as wanted; this is
          // the composition available without inventing a catalogue entry.
          <Panel
            title={message(locale, 'admin.column.active')}
            state={stateOf(tokens, liveSessions.length === 0)}
            dependency={dependencyOf(tokens)}
            labels={panelLabels(locale, message(locale, 'admin.column.active'))}
            empty={emptyState}
          >
            <SessionPanel
              sessions={liveSessions}
              labels={{
                person: message(locale, 'admin.column.principal'),
                expires: message(locale, 'admin.column.expires'),
                // No dedicated "end all sessions" vocabulary exists yet (see
                // the report), so the same revoke verbs the token list already
                // uses are reused for the bulk action underneath these too.
                endAll: message(locale, 'admin.tokens.revoke'),
                ending: message(locale, 'admin.tokens.revoking'),
                endConfirm: message(locale, 'admin.tokens.revokeConfirm'),
                endCancel: message(locale, 'admin.tokens.revokeCancel'),
                endConsequence: message(locale, 'admin.tokens.revokeConsequence'),
                failed: message(locale, 'admin.tokens.failed'),
                unreachable: message(locale, 'admin.tokens.unreachable'),
              }}
            />
          </Panel>
        ) : null}

        {may(viewer, TOKENS) ? (
          <Panel
            title={message(locale, 'admin.tokens.title')}
            state={stateOf(tokens, false)}
            dependency={dependencyOf(tokens)}
            labels={panelLabels(locale, message(locale, 'admin.tokens.title'))}
            empty={emptyState}
          >
            <TokenPanel
              tokens={machineTokens.map((token): IssuedToken => {
                const expires = timestamp(locale, text(token, 'expires_at'), now, zone);
                return {
                  tokenId: text(token, 'token_id'),
                  name: text(token, 'name'),
                  scopes: list(token, 'scopes').map(String),
                  revoked: flag(token, 'revoked'),
                  expires: expires.relative,
                };
              })}
              // The form asks only what a token is for (see `tokens.tsx`'s own
              // doc); the scope it actually gets is fixed to this viewer's own
              // permissions, shown here rather than left to be discovered on
              // the list afterwards.
              issuedScopes={viewer.permissions}
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
                columnToken: message(locale, 'admin.column.token'),
                columnScopes: message(locale, 'admin.column.scopes'),
                columnExpires: message(locale, 'admin.column.expires'),
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
              // Never the deployment's declarative validation of the document
              // as it stands on load — `SsoForm` renders this list unconditionally
              // from mount, and the deployment always answers with "issuer is
              // required" and seven siblings for a form nobody has touched yet.
              // Validation belongs to save and test, which `adopt()` already
              // renders from their own live responses; an untouched load has
              // nothing to confess.
              problems={[]}
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

/** The two tabs, People first because it is the one read every day. */
export const ADMINISTRATION_TABS = ['people', 'audit'] as const;

export type AdministrationTab = (typeof ADMINISTRATION_TABS)[number];

/** The tab the address names, and the first one when it names nothing known. */
export function tabFrom(value: string): AdministrationTab {
  return ADMINISTRATION_TABS.find((tab) => tab === value) ?? ADMINISTRATION_TABS[0];
}

/**
 * The address filters this wrapper reads for itself.
 *
 * `AuditTab`'s own `AUDIT_FILTERS` already declares `tab`, so a filter or a
 * sort clicked on the Audit tab carries it through without this constant's
 * help; this one exists only so the wrapper can ask which tab is selected
 * before it decides which content to fetch at all.
 */
const ADMINISTRATION_FILTERS: readonly FilterName[] = ['tab'];

export async function AdministrationScreen(
  context: SurfaceContext,
): Promise<ReactNode> {
  const { locale, search } = context;
  const state = readViewState(search, ADMINISTRATION_FILTERS);
  const tab = tabFrom(state.filters.tab ?? '');

  // Only the selected tab reads anything, the same "fetch what is showing"
  // rule `agent.tsx` and `decisions.tsx` both follow for their own tabs.
  const content = tab === 'people' ? await PeopleTab(context) : await AuditTab(context);

  return (
    <>
      <AreaHeader area={areaFor('administration')} locale={locale} />

      <TabLinks
        label={message(locale, 'admin.tabs')}
        selected={tab}
        tabs={ADMINISTRATION_TABS.map((each) => ({
          id: each,
          label: message(locale, `admin.tab.${each}`),
          href: `?tab=${each}`,
        }))}
      />

      <div className="mt-4">{content}</div>
    </>
  );
}
