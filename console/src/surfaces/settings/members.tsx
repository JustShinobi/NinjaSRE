import type { ReactNode } from 'react';

import { formatCount, timestamp } from '@/i18n/format';
import { message, type Locale } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { SettingsPageHeader } from '@/shell/area';
import { settingsPageFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { GrantPanel, type Grant, type RoleDescription } from '../grants';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import { PrincipalsPanel, type PrincipalRow } from '../principals';
import { SessionPanel, type SessionEntry } from '../tokens';
import { isConsoleSession } from '../token-identity';
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
 * The Principals panel's second line, for one record.
 *
 * Their email where the deployment recorded one; a service account is
 * created without one by design, so that state is named rather than shown as
 * something this deployment forgot to record.
 */
function principalIdentity(locale: Locale, person: unknown): string {
  const email = text(person, 'email');
  if (email !== '') return email;
  return text(person, 'kind') === 'service_account'
    ? message(locale, 'admin.principals.serviceAccount')
    : text(person, 'user_id');
}

/**
 * Members & roles: who exists, what they hold, and who is signed in.
 *
 * The simplest of the four pages this desmembramento builds, because it is
 * the part of the old Administration screen that already worked — this page
 * is a reapresentation, not a rebuild. What it deliberately does not carry
 * forward is the other two subjects `PeopleTab` used to stack underneath it:
 * machine tokens have their own page now (`settings/machine-tokens.tsx`) and
 * so does single sign-on (`settings/sso.tsx`), and neither is read from here
 * — a page reads only what it shows.
 *
 * The last-owner guard this page's grant removal relies on already lives on
 * the gateway (`identity.py`'s `remove_grant`, calling
 * `require_owner_retained`) and `GrantPanel` already surfaces its refusal as
 * its own message rather than a generic failure — both predate this feature
 * and are only reused here, not rebuilt.
 */

const ID = 'settings-members-roles';
const TOKENS = 'token.manage';
// Gates two writes on this page, not one: granting a role, and — the primary
// action this page gained alongside it — creating the person to grant one to.
const IDENTITY_WRITE = 'identity.write';

async function content(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer, now, zone } = context;
  const init = authorised(credential);

  const [principals, grants, roles, tokens] = await Promise.all([
    panelRead('/identity/principals', () => read('/identity/principals', init)),
    panelRead('/identity/grants', () => read('/identity/grants', init)),
    // Asked for rather than compiled in — see `admin.grants.title`'s own
    // reasoning, which applies here unchanged: a second copy of the role
    // catalogue written into a front end is the copy that goes stale the day
    // a permission is added.
    panelRead('/identity/roles', () => read('/identity/roles', init)),
    may(viewer, TOKENS)
      ? panelRead<unknown>('/identity/tokens', () => read('/identity/tokens', init))
      : Promise.resolve({ status: 'ready' as const, data: {} }),
  ]);

  const people = list(dataOf(principals), 'users');
  const held = list(dataOf(grants), 'grants');
  const roleCatalogue = list(dataOf(roles), 'roles');
  const catalogue = roleCatalogue.map((role) => text(role, 'name'));
  // A human summary derived from the catalogue's own shape — how many
  // distinct permission domains a role reaches — rather than a sentence
  // written by hand per role, which is the copy that goes stale the day a
  // permission is added. The raw permission list travels alongside it, for
  // whoever expands the disclosure `GrantPanel` renders beside the choice.
  const roleDescriptions: Readonly<Record<string, RoleDescription>> =
    Object.fromEntries(
      roleCatalogue.map((role) => {
        const permissions = list(role, 'permissions').map(String);
        const domains = new Set(
          permissions.map((permission) => permission.split('.')[0] ?? permission),
        );
        const description: RoleDescription = {
          summary: formatCount(
            locale,
            domains.size,
            'admin.grant.role.summary.one',
            'admin.grant.role.summary',
          ),
          permissions,
        };
        return [text(role, 'name'), description];
      }),
    );
  const issued = list(dataOf(tokens), 'tokens');

  const principalLabel = (userId: string): string => {
    const found = people.find((person) => text(person, 'user_id') === userId);
    return found === undefined || text(found, 'display_name') === ''
      ? userId
      : text(found, 'display_name');
  };

  // Only sessions live here; a machine token belongs to its own page now.
  const liveSessions: readonly SessionEntry[] = issued
    .filter((token) => isConsoleSession({ name: text(token, 'name') }))
    .filter((token) => !flag(token, 'revoked'))
    .map((token) => ({
      tokenId: text(token, 'token_id'),
      principalId: text(token, 'user_id'),
      principalLabel: principalLabel(text(token, 'user_id')),
      expires: timestamp(locale, text(token, 'expires_at'), now, zone).relative,
      // The deployment has no device or origin to report — `created_at` is
      // the one additional fact it already knows, so a session identifies by
      // who and since when rather than by a bare token number.
      origin: timestamp(locale, text(token, 'created_at'), now, zone).relative,
    }));

  const emptyState = {
    heading: message(locale, 'admin.empty.heading'),
    body: message(locale, 'settings.page.membersRoles.context'),
    actionLabel: message(locale, 'admin.empty.action'),
    href: '/settings/members-roles',
  };

  return (
    <div className="flex flex-col gap-5">
      <Panel
        title={message(locale, 'admin.principals.title')}
        state={stateOf(principals, people.length === 0)}
        dependency={dependencyOf(principals)}
        labels={panelLabels(locale, message(locale, 'admin.principals.title'))}
        empty={emptyState}
      >
        <PrincipalsPanel
          principals={people.map((person): PrincipalRow => ({
            userId: text(person, 'user_id'),
            displayName: text(person, 'display_name'),
            identity: principalIdentity(locale, person),
            kind: text(person, 'kind'),
            isActive: flag(person, 'is_active'),
          }))}
          canWrite={may(viewer, IDENTITY_WRITE)}
          locale={locale}
          labels={{
            displayName: message(locale, 'admin.principals.create.displayName'),
            email: message(locale, 'admin.principals.create.email'),
            password: message(locale, 'admin.principals.create.password'),
            passwordHelp: message(locale, 'admin.principals.create.passwordHelp'),
            create: message(locale, 'admin.principals.create.action'),
            creating: message(locale, 'admin.principals.create.creating'),
            failed: message(locale, 'admin.tokens.failed'),
            unreachable: message(locale, 'admin.tokens.unreachable'),
          }}
        />
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
          canWrite={may(viewer, IDENTITY_WRITE)}
          labels={{
            principal: message(locale, 'admin.column.principal'),
            role: message(locale, 'admin.column.role'),
            rolePermissions: message(locale, 'admin.grant.rolePermissions'),
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
            addAction: message(locale, 'admin.grant.addAction'),
            addConsequence: message(locale, 'admin.grant.addConsequence'),
            addClose: message(locale, 'admin.grant.addClose'),
            addCancel: message(locale, 'admin.grant.addCancel'),
            failed: message(locale, 'admin.tokens.failed'),
            unreachable: message(locale, 'admin.tokens.unreachable'),
          }}
        />
      </Panel>

      {may(viewer, TOKENS) ? (
        <Panel
          title={message(locale, 'admin.sessions.title')}
          state={stateOf(tokens, liveSessions.length === 0)}
          dependency={dependencyOf(tokens)}
          labels={panelLabels(locale, message(locale, 'admin.sessions.title'))}
          empty={emptyState}
        >
          <SessionPanel
            sessions={liveSessions}
            labels={{
              person: message(locale, 'admin.column.principal'),
              origin: message(locale, 'admin.column.origin'),
              expires: message(locale, 'admin.column.expires'),
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
    </div>
  );
}

export async function MembersScreen(context: SurfaceContext): Promise<ReactNode> {
  return (
    <>
      <SettingsPageHeader page={settingsPageFor(ID)} locale={context.locale} />
      {await content(context)}
    </>
  );
}
