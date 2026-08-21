import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
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

/**
 * Who exists, what they hold, and what has been issued on their behalf.
 *
 * Three panels with three permissions between them: a viewer who may read
 * principals but not manage tokens sees the first two and not the third. Absent,
 * not disabled — the panel is not in the document at all, so there is nothing to
 * tell them a capability exists that somebody else has.
 *
 * Single sign-on is stated rather than configured here: nothing serves its
 * settings yet, and a form that posted nowhere would be worse than a sentence
 * saying where it will live.
 */

const TOKENS = 'token.manage';
const SSO = 'sso.manage';

export async function AdministrationScreen(
  context: SurfaceContext,
): Promise<ReactNode> {
  const { credential, locale, viewer, now, zone } = context;
  const init = authorised(credential);

  const [principals, grants, tokens] = await Promise.all([
    panelRead('/identity/principals', () => read('/identity/principals', init)),
    panelRead('/identity/grants', () => read('/identity/grants', init)),
    may(viewer, TOKENS)
      ? panelRead<unknown>('/identity/tokens', () => read('/identity/tokens', init))
      : Promise.resolve({ status: 'ready' as const, data: {} }),
  ]);

  const people = list(dataOf(principals), 'users');
  const held = list(dataOf(grants), 'grants');
  const issued = list(dataOf(tokens), 'tokens');
  const none = message(locale, 'surface.none');

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
          <ul className="flex flex-col gap-2 text-small">
            {held.map((grant) => (
              <li
                key={text(grant, 'grant_id')}
                data-testid="grant"
                className="flex items-center gap-3 min-w-0"
              >
                <span className="font-mono truncate">
                  {text(grant, 'principal_id')}
                </span>
                <span className="ml-auto flex items-center gap-2">
                  <Badge status={text(grant, 'role')} />
                  <span className="text-meta text-muted">{text(grant, 'node_id')}</span>
                </span>
              </li>
            ))}
          </ul>
        </Panel>

        {may(viewer, TOKENS) ? (
          <Panel
            title={message(locale, 'admin.tokens.title')}
            state={stateOf(tokens, issued.length === 0)}
            dependency={dependencyOf(tokens)}
            labels={panelLabels(locale, message(locale, 'admin.tokens.title'))}
            empty={emptyState}
          >
            <ul className="flex flex-col gap-2 text-small">
              {issued.map((token) => {
                const expires = timestamp(locale, text(token, 'expires_at'), now, zone);
                return (
                  <li
                    key={text(token, 'token_id')}
                    data-testid="token"
                    className="flex items-center gap-3 min-w-0"
                  >
                    <span className="truncate">{text(token, 'name')}</span>
                    <span className="text-meta text-muted truncate">
                      {list(token, 'scopes').map(String).join(', ')}
                    </span>
                    <span className="ml-auto flex items-center gap-2">
                      {/* Never the secret. A token is shown once, at issue, by
                          the deployment — and never again by anything. */}
                      <Badge status={flag(token, 'revoked') ? 'revoked' : 'healthy'} />
                      <span className="text-meta text-muted">
                        {expires.relative === '' ? none : expires.relative}
                      </span>
                    </span>
                  </li>
                );
              })}
            </ul>
          </Panel>
        ) : null}

        {may(viewer, SSO) ? (
          <Panel
            title={message(locale, 'admin.sso.title')}
            state="empty"
            labels={panelLabels(locale, message(locale, 'admin.sso.title'))}
            empty={{
              heading: message(locale, 'admin.sso.title'),
              body: message(locale, 'page.administration.context'),
              actionLabel: message(locale, 'admin.sso.configure'),
              href: '/configuration',
            }}
          />
        ) : null}
      </div>
    </>
  );
}
