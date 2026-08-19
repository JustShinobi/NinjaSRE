import type { ReactNode } from 'react';

import { Link } from '@/components/action';
import { timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { SettingsPageHeader } from '@/shell/area';
import { settingsPageFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { MachineTokenGroups, type MachineToken } from '../machine-token-groups';
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
import { isConsoleSession } from '../token-identity';
import { readViewState, type FilterName } from '../url-state';

/**
 * Machine tokens, grouped by purpose, with the causes of accumulation treated
 * rather than only the symptom.
 *
 * This page reads `/identity/tokens` and shows only what is not a browser
 * session — see `token-identity.ts`'s own doc for why a session and a
 * machine token share one store and one shape, and why telling them apart
 * happens here rather than in the deployment. Members & roles reads the same
 * endpoint for the opposite half of it.
 */

const ID = 'settings-machine-tokens';

/**
 * Belt and braces alongside the Settings page's own gate
 * (`settings-machine-tokens`'s permission, enforced before this ever
 * renders): the whole panel is absent rather than merely un-writable for a
 * viewer who somehow reaches this screen without it — the same rule
 * `PeopleTab`'s own token panel already follows for its own write control.
 */
const TOKENS = 'token.manage';

/**
 * The one filter this screen answers to: which scope its tokens must carry.
 *
 * Declared and read through the address, per the console's own rule that a
 * screen's state lives in its URL rather than in memory a link cannot carry.
 * Alert intake's own "Rotate" is the first caller: it names the delivery
 * permission on its way here so the list an operator lands on is already the
 * token it meant, not the full, undifferentiated one they would have to
 * search by hand.
 */
const MACHINE_TOKENS_FILTERS: readonly FilterName[] = ['scope'];

/** `scope`, with its separators opened into spaces — never the raw spelling. */
function humanizedScope(scope: string): string {
  const words = scope.split(/[._-]+/).filter((word) => word.length > 0);
  if (words.length === 0) return scope;
  return words
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

function machineToken(
  record: unknown,
  locale: Parameters<typeof timestamp>[0],
  now: Date,
  zone: string,
): MachineToken {
  const createdAt = text(record, 'created_at');
  const lastUsedAt = text(record, 'last_used_at');
  const expiresAt = text(record, 'expires_at');
  return {
    tokenId: text(record, 'token_id'),
    name: text(record, 'name'),
    description: text(record, 'description'),
    scopes: list(record, 'scopes').map(String),
    createdAt,
    lastUsed:
      lastUsedAt === '' ? '' : timestamp(locale, lastUsedAt, now, zone).relative,
    expires: expiresAt === '' ? '' : timestamp(locale, expiresAt, now, zone).relative,
    revoked: flag(record, 'revoked'),
  };
}

async function content(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer, now, zone, search } = context;
  const scope = readViewState(search, MACHINE_TOKENS_FILTERS).filters.scope;

  const answer = await panelRead('/identity/tokens', () =>
    read('/identity/tokens', authorised(credential)),
  );
  const records = list(dataOf(answer), 'tokens')
    .filter((record) => !isConsoleSession({ name: text(record, 'name') }))
    .filter(
      (record) =>
        scope === undefined || list(record, 'scopes').map(String).includes(scope),
    );
  const tokens = records.map((record) => machineToken(record, locale, now, zone));

  const labels = {
    purpose: message(locale, 'admin.tokens.name'),
    purposeHelp: message(locale, 'settings.machineTokens.purposeHelp'),
    description: message(locale, 'settings.machineTokens.detail'),
    scopes: message(locale, 'admin.column.scopes'),
    issue: message(locale, 'admin.tokens.issue'),
    issuing: message(locale, 'admin.tokens.issuing'),
    shownOnce: message(locale, 'admin.tokens.shownOnce'),
    revoke: message(locale, 'admin.tokens.revoke'),
    revoking: message(locale, 'admin.tokens.revoking'),
    revokeConsequence: message(locale, 'admin.tokens.revokeConsequence'),
    revokeConfirm: message(locale, 'admin.tokens.revokeConfirm'),
    revokeCancel: message(locale, 'admin.tokens.revokeCancel'),
    revokeOlder: message(locale, 'settings.machineTokens.revokeOlder'),
    revokingOlder: message(locale, 'settings.machineTokens.revokingOlder'),
    revokeOlderConsequence: message(
      locale,
      'settings.machineTokens.revokeOlderConsequence',
    ),
    revokeOlderConfirm: message(locale, 'settings.machineTokens.revokeOlderConfirm'),
    revokeOlderCancel: message(locale, 'settings.machineTokens.revokeOlderCancel'),
    failed: message(locale, 'admin.tokens.failed'),
    unreachable: message(locale, 'admin.tokens.unreachable'),
    none: message(locale, 'surface.none'),
    lastUsedLabel: message(locale, 'settings.machineTokens.lastUsed'),
    neverUsed: message(locale, 'settings.machineTokens.neverUsed'),
    empty: message(locale, 'settings.machineTokens.empty.body'),
  };

  return (
    // Never Panel's own empty state: a deployment with no machine tokens yet
    // is exactly the deployment that needs the issue form in front of it, and
    // `MachineTokenGroups` already says so inline (`labels.empty`) below the
    // form rather than in place of it — the same reason `TokenPanel` (the
    // panel this absorbs) was never empty for somebody who may manage tokens.
    <Panel
      title={message(locale, 'admin.tokens.title')}
      state={stateOf(answer, false)}
      dependency={dependencyOf(answer)}
      labels={panelLabels(locale, message(locale, 'admin.tokens.title'))}
      empty={{
        heading: message(locale, 'settings.machineTokens.empty.heading'),
        body: message(locale, 'settings.machineTokens.empty.body'),
        actionLabel: message(locale, 'settings.machineTokens.empty.action'),
        href: '/settings/machine-tokens',
      }}
    >
      {may(viewer, TOKENS) ? (
        <>
          {scope === undefined ? null : (
            <p className="text-meta text-muted" data-testid="machine-tokens-filter">
              {message(locale, 'settings.machineTokens.filteredBy', {
                scope: humanizedScope(scope),
              })}{' '}
              <Link
                href="/settings/machine-tokens"
                data-testid="machine-tokens-filter-clear"
              >
                {message(locale, 'settings.machineTokens.clearFilter')}
              </Link>
            </p>
          )}
          <MachineTokenGroups
            tokens={tokens}
            issuedScopes={viewer.permissions}
            labels={labels}
            locale={locale}
          />
        </>
      ) : null}
    </Panel>
  );
}

export async function MachineTokensScreen(context: SurfaceContext): Promise<ReactNode> {
  return (
    <>
      <SettingsPageHeader page={settingsPageFor(ID)} locale={context.locale} />
      {await content(context)}
    </>
  );
}
