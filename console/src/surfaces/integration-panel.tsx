'use client';

import { useEffect, useState, type ReactNode } from 'react';
import NextLink from 'next/link';
import { useRouter } from 'next/navigation';

import { Drawer } from '@/components/overlay';
import { StatusChip } from '@/components/status';
import type { Locale } from '@/i18n/messages';
import {
  CredentialField,
  type CredentialFieldSpec,
  type CredentialLabels,
} from './credential';
import { VERIFY_ENDPOINT } from './first-run/verify';
import { consumeScrollPosition, peekScrollPosition } from './scroll-memory';

/**
 * The credential panel: a slide-over on the catalogue, one integration at a
 * time, closing back to exactly where the operator was.
 *
 * "Save and test" is one action wearing one label rather than a store
 * somebody has to remember to follow with a check. `CredentialField` already
 * does the storing and already calls back once it has; this listens for that
 * callback and makes the second request itself, through the same `/api/verify`
 * courier the guided run's own verify step uses. The two intermediate states —
 * storing, then testing — are both visible, and the button's own label is the
 * one it started with: "Save and test" is what was asked for, and it stays
 * true the whole time the click is being honoured.
 */

/**
 * One vendor permission the credential needs, whole — never only its name.
 *
 * This is the declared, probed content FR-006's "minimum permission" is
 * about: `tools.verify_integrations` makes the call each of these names, so
 * `grants` and `where` are not a guess written down beside the name, they are
 * what the vendor was actually asked and what it said the name is for.
 */
export interface PermissionSpec {
  readonly name: string;
  readonly grants: string;
  readonly where: string;
  readonly capabilities: readonly string[];
}

export interface IntegrationPanelItem {
  readonly name: string;
  readonly displayName: string;
  readonly categoryLabel: string;
  readonly summary: string;
  readonly health: string;
  readonly healthDetail: string;
  readonly fields: readonly CredentialFieldSpec[];
  readonly permissions: readonly PermissionSpec[];
}

export interface IntegrationPanelLabels {
  readonly close: string;
  /** `submit`/`sending` here are "Save and test" / "Saving and testing…". */
  readonly credential: CredentialLabels;
  readonly security: string;
  readonly notFound: string;
  readonly notFoundAction: string;
  readonly testing: string;
  readonly unreachable: string;
  /** Shown instead of the form for a viewer who reached this without `writable`. */
  readonly readOnly: string;
  readonly permissionsHeading: string;
  /** The prefix before `permission.where` — "Granted at", never a full sentence. */
  readonly grantedAt: string;
}

export interface IntegrationPanelProps {
  readonly locale: Locale;
  /** The name the address requested, shown as the title when nothing resolves. */
  readonly requestedName: string;
  readonly item: IntegrationPanelItem | null;
  readonly closeHref: string;
  /**
   * Whether this viewer holds `integration.manage`. The area itself is gated
   * on the same permission, so a viewer without it cannot reach this panel in
   * the running console — this is the same "absent, not disabled" rule held a
   * second time, for a viewer this component is handed directly by a test.
   */
  readonly writable: boolean;
  readonly labels: IntegrationPanelLabels;
}

interface Verdict {
  readonly status: 'verified' | 'failing';
  readonly detail: string;
}

/** The slide-over drawer: category, state, the write-only form, and its test. */
export function IntegrationPanel({
  locale,
  requestedName,
  item,
  closeHref,
  writable,
  labels,
}: IntegrationPanelProps): ReactNode {
  const router = useRouter();
  const [testing, setTesting] = useState(false);
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  // Two corrections, one effect. On mount: the RSC swap that brought this
  // panel in can leave the browser having clamped `window.scrollY` down to a
  // document that was briefly shorter mid-navigation (see `scroll-memory.ts`
  // for why) — peeked, not consumed, because the cleanup below still needs
  // the same value. On unmount: the scroll position the catalogue was at
  // when this panel opened is restored the moment this component goes away
  // — the close button, Escape, and navigating anywhere else all unmount it
  // the same way, so one cleanup covers every path shut. Guarded to
  // `/integrations` because a viewer who left the area entirely (a different
  // nav link, say) should not have this page's memory of a scroll position
  // nudge whatever page they landed on.
  useEffect(() => {
    const remembered = peekScrollPosition();
    if (remembered !== null && window.scrollY !== remembered) {
      window.scrollTo(0, remembered);
    }
    return () => {
      if (!window.location.pathname.startsWith('/integrations')) return;
      const restored = consumeScrollPosition();
      if (restored !== null) window.scrollTo(0, restored);
    };
  }, []);

  function close(): void {
    router.replace(closeHref, { scroll: false });
  }

  async function testNow(name: string): Promise<void> {
    setTesting(true);
    setVerdict(null);
    setUnreachable(false);
    try {
      const answer = await fetch(VERIFY_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ kind: 'integration', name }),
      });
      const body: unknown = await answer.json().catch(() => ({}));
      const reachable = Reflect.get(Object(body), 'reachable') !== false;
      if (!reachable) {
        setUnreachable(true);
      } else {
        const verified = Reflect.get(Object(body), 'verified') === true;
        const reason: unknown = Reflect.get(Object(body), 'reason');
        setVerdict({
          status: verified ? 'verified' : 'failing',
          detail: typeof reason === 'string' ? reason : '',
        });
      }
    } catch {
      setUnreachable(true);
    }
    setTesting(false);
  }

  return (
    <Drawer
      open
      floating
      title={item?.displayName ?? requestedName}
      onClose={close}
      closeLabel={labels.close}
    >
      {item === null ? (
        <div className="flex flex-col gap-3">
          <p className="text-meta text-muted">{labels.notFound}</p>
          <NextLink
            href={closeHref}
            scroll={false}
            className="text-accent underline underline-offset-2 motion-hover hover:opacity-80"
          >
            {labels.notFoundAction}
          </NextLink>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-meta text-muted">
            {item.categoryLabel} · {item.summary}
          </p>
          <StatusChip locale={locale} status={item.health} />
          {item.healthDetail === '' ? null : (
            <p className="text-meta text-muted" data-testid="panel-health-detail">
              {item.healthDetail}
            </p>
          )}
          {item.permissions.length === 0 ? null : (
            <div className="flex flex-col gap-2" data-testid="required-permissions">
              <h3 className="text-micro uppercase tracking-wide text-muted">
                {labels.permissionsHeading}
              </h3>
              <ul className="flex flex-col gap-1">
                {item.permissions.map((permission) => (
                  <li
                    key={permission.name}
                    data-testid="required-permission"
                    className="text-meta text-muted"
                  >
                    <span className="text-strong">{permission.name}</span> —{' '}
                    {permission.grants}
                    {permission.where === '' ? null : (
                      <>
                        {' · '}
                        {labels.grantedAt} {permission.where}
                      </>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {writable ? (
            <>
              <CredentialField
                integration={item.name}
                fields={item.fields}
                labels={labels.credential}
                onStored={(name) => {
                  void testNow(name);
                }}
              />
              {testing ? (
                <p
                  className="text-meta text-muted"
                  role="status"
                  data-testid="credential-testing"
                >
                  {labels.testing}
                </p>
              ) : null}
              {verdict === null ? null : (
                <p
                  className="flex items-center gap-2"
                  data-testid="credential-outcome"
                  role="status"
                >
                  <StatusChip locale={locale} status={verdict.status} />
                  {verdict.detail === '' ? null : (
                    <span className="text-meta text-muted">{verdict.detail}</span>
                  )}
                </p>
              )}
              {unreachable ? (
                <p
                  role="alert"
                  className="text-meta text-danger"
                  data-testid="credential-outcome"
                >
                  {labels.unreachable}
                </p>
              ) : null}
              <p
                className="text-meta text-muted"
                data-testid="credential-security-note"
              >
                {labels.security}
              </p>
            </>
          ) : (
            // Absent, not disabled: the same rule the area's own gate already
            // holds, applied a second time for a viewer this component is
            // handed directly rather than through the area's own route guard.
            <p className="text-meta text-muted" data-testid="credential-read-only">
              {labels.readOnly}
            </p>
          )}
        </div>
      )}
    </Drawer>
  );
}
