'use client';

import { useEffect, useState, type ReactNode } from 'react';
import NextLink from 'next/link';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/action';
import { ConfirmDestructive, Drawer } from '@/components/overlay';
import { StatusChip } from '@/components/status';
import { credentialStatus } from '@/design/status';
import type { Locale } from '@/i18n/messages';
import {
  CREDENTIAL_ENDPOINT,
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
 *
 * A connected integration never opens on this write form. `credentialStatus`
 * — the one place the console already reconciles every backend spelling of a
 * credential's state onto five canonical words — decides whether *anything*
 * is stored; every value but `'not_connected'` means something is, including
 * `'degraded'` and `'failing'`, because losing a credential's verification
 * does not lose the credential. What such a panel shows instead is the state
 * and three actions that make sense on top of it: test it again, replace it
 * through the identical write-only form ("Replace credential" only toggles
 * which half of this component is on screen — no second form exists), or
 * disconnect it through the confirmation the component library already
 * imposes on every destructive write in this console.
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
  /**
   * The address the estate's own discovery already found this service
   * running at, when it found one.
   *
   * Empty is the ordinary case, and it renders nothing at all — never a
   * guessed address and never another deployment's. The only legitimate
   * source for a non-empty value is the catalogue's own `suggested.address`,
   * the same field the Suggested section already reads; nothing here ever
   * invents one from a vendor's default port or a constant on the screen.
   */
  readonly discoveredAddress: string;
  /**
   * Which way this vendor's traffic flows: `outbound` when this deployment only
   * calls it, `both` when it also posts alerts here. Served by the catalogue,
   * derived there from the webhook router's own source list rather than
   * declared per vendor.
   *
   * It is on the screen because two different secrets share the word "token".
   * The credential written below is always the outbound one; a vendor that also
   * delivers needs a delivery token as well, issued somewhere else and held by
   * the alert router rather than by this deployment.
   */
  readonly direction: string;
  /** Where this vendor posts, when it posts. Empty for an outbound-only vendor. */
  readonly intakePath: string;
}

export interface IntegrationPanelLabels {
  readonly close: string;
  /** `submit`/`sending` here are "Save and test" / "Saving and testing…". */
  readonly credential: CredentialLabels;
  readonly security: string;
  readonly notFound: string;
  readonly notFoundAction: string;
  /** The second link a missing integration's panel offers: the roadmap list. */
  readonly notFoundRoadmap: string;
  readonly testing: string;
  readonly unreachable: string;
  /** Shown instead of the form for a viewer who reached this without `writable`. */
  readonly readOnly: string;
  readonly permissionsHeading: string;
  /** The prefix before `permission.where` — "Granted at", never a full sentence. */
  readonly grantedAt: string;
  /** What precedes the estate's own discovered address, when there is one. */
  readonly foundHere: string;
  /** What a connected integration's panel says about where its credential lives. */
  readonly storedInVault: string;
  readonly testAgain: string;
  readonly replaceCredential: string;
  /** Leaving "Replace credential" unsaved, and leaving the disconnect confirmation unconfirmed. */
  readonly cancel: string;
  readonly disconnect: string;
  /** What "Disconnect" removes, said before the write happens. */
  readonly disconnectConsequence: string;
  /** What a vendor this deployment only reads is described as. */
  readonly directionOutbound: string;
  /** What a vendor that also delivers alerts here is described as. */
  readonly directionBoth: string;
  /** The heading over the step that happens outside this deployment. */
  readonly intakeTitle: string;
  /** What that step is, in one sentence. */
  readonly intakeBody: string;
  /** What the link to the alert-intake screen is called. */
  readonly intakeAction: string;
}

export interface IntegrationPanelProps {
  readonly locale: Locale;
  /** The name the address requested, shown as the title when nothing resolves. */
  readonly requestedName: string;
  readonly item: IntegrationPanelItem | null;
  readonly closeHref: string;
  /** Where the roadmap's reference page lives — offered beside the way back, for a name the cut removed. */
  readonly notCoveredHref: string;
  /** Where an operator goes to finish an inbound integration. */
  readonly intakeHref: string;
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
  notCoveredHref,
  intakeHref,
  writable,
  labels,
}: IntegrationPanelProps): ReactNode {
  const router = useRouter();
  const [testing, setTesting] = useState(false);
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  // Toggles which half of the writable branch is on screen: the connected
  // state and its three actions, or the write-only form underneath
  // "Replace credential". Never true for an integration that opened with
  // nothing stored — that case already shows the form, with nothing to
  // replace it with.
  const [replacing, setReplacing] = useState(false);
  // Set the moment a disconnect succeeds, ahead of the server round-trip
  // `router.refresh()` starts below. Without this the actions view would
  // keep reading "connected" against a credential that is already gone,
  // for however long the refetch takes.
  const [disconnected, setDisconnected] = useState(false);
  const [confirmingDisconnect, setConfirmingDisconnect] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [disconnectFailure, setDisconnectFailure] = useState('');

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

  /** Remove the stored credential, every version, after the confirmation. */
  async function disconnect(name: string): Promise<void> {
    if (disconnecting) return;
    setDisconnecting(true);
    setDisconnectFailure('');
    let answer: Response;
    try {
      answer = await fetch(CREDENTIAL_ENDPOINT, {
        method: 'DELETE',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ integration: name }),
      });
    } catch {
      setDisconnecting(false);
      setConfirmingDisconnect(false);
      setDisconnectFailure(labels.credential.unreachable);
      return;
    }
    const body: unknown = await answer.json().catch(() => ({}));
    setDisconnecting(false);
    // Closed here, success or failure, the same way the confirmation this
    // component reuses is closed everywhere else it appears — the failure,
    // if there is one, is said below rather than held behind a dialog that
    // is still open over it.
    setConfirmingDisconnect(false);
    if (!answer.ok) {
      const reason: unknown = Reflect.get(Object(body), 'reason');
      setDisconnectFailure(
        `${labels.credential.refused} ${typeof reason === 'string' ? reason : ''}`.trim(),
      );
      return;
    }
    setDisconnected(true);
    setVerdict(null);
    setUnreachable(false);
    // What the vault now holds is a fact the next render has to ask for
    // again, not a client guess about it — the same discipline the
    // guardrails table already applies after a write of its own.
    router.refresh();
  }

  const connected =
    item !== null && credentialStatus(item.health) !== 'not_connected' && !disconnected;
  const showForm = item !== null && (!connected || replacing);

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
            data-testid="panel-not-found-back"
            className="text-accent underline underline-offset-2 motion-hover hover:opacity-80"
          >
            {labels.notFoundAction}
          </NextLink>
          <NextLink
            href={notCoveredHref}
            data-testid="panel-not-found-roadmap"
            className="text-accent underline underline-offset-2 motion-hover hover:opacity-80"
          >
            {labels.notFoundRoadmap}
          </NextLink>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-meta text-muted">
            {item.categoryLabel} · {item.summary}
          </p>
          <p className="text-meta text-muted" data-testid="panel-direction">
            {item.direction === 'both'
              ? labels.directionBoth
              : labels.directionOutbound}
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
              {showForm ? (
                <>
                  {item.discoveredAddress === '' ? null : (
                    <p
                      className="text-meta text-accent"
                      data-testid="panel-discovered-address"
                    >
                      {labels.foundHere} {item.discoveredAddress}
                    </p>
                  )}
                  <CredentialField
                    integration={item.name}
                    fields={item.fields}
                    labels={labels.credential}
                    onStored={(name) => {
                      setReplacing(false);
                      void testNow(name);
                    }}
                  />
                  {replacing ? (
                    <div>
                      <Button
                        variant="quiet"
                        data-testid="cancel-replace"
                        onClick={() => {
                          setReplacing(false);
                        }}
                      >
                        {labels.cancel}
                      </Button>
                    </div>
                  ) : null}
                </>
              ) : (
                <div className="flex flex-col gap-3" data-testid="credential-connected">
                  <p
                    className="text-meta text-muted"
                    data-testid="credential-stored-note"
                  >
                    {labels.storedInVault}
                  </p>
                  <div className="flex flex-wrap items-center gap-3">
                    <Button
                      variant="secondary"
                      data-testid="test-again"
                      state={testing ? 'loading' : 'default'}
                      onClick={() => {
                        void testNow(item.name);
                      }}
                    >
                      {labels.testAgain}
                    </Button>
                    <Button
                      variant="secondary"
                      data-testid="replace-credential"
                      onClick={() => {
                        setReplacing(true);
                        setVerdict(null);
                        setUnreachable(false);
                      }}
                    >
                      {labels.replaceCredential}
                    </Button>
                    <Button
                      variant="destructive"
                      data-testid="disconnect-credential"
                      onClick={() => {
                        setConfirmingDisconnect(true);
                      }}
                    >
                      {labels.disconnect}
                    </Button>
                  </div>
                </div>
              )}

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
              {disconnectFailure === '' ? null : (
                <p
                  role="alert"
                  className="text-meta text-danger"
                  data-testid="disconnect-outcome"
                >
                  {disconnectFailure}
                </p>
              )}

              <p
                className="text-meta text-muted"
                data-testid="credential-security-note"
              >
                {labels.security}
              </p>

              {item.direction === 'both' ? (
                // The step that closes the loop, on the screen the operator is
                // already on. Everything above stores a credential this
                // deployment presents; this is the one that makes anything
                // arrive, and it happens in the alert router rather than here.
                <div
                  className="flex flex-col gap-2 rounded-2 edge px-3 py-2"
                  data-testid="panel-intake-handover"
                >
                  <h3 className="text-micro uppercase tracking-wide text-muted">
                    {labels.intakeTitle}
                  </h3>
                  <p className="text-meta text-muted">{labels.intakeBody}</p>
                  {item.intakePath === '' ? null : (
                    <p className="text-meta text-muted">
                      <code>{item.intakePath}</code>
                    </p>
                  )}
                  <NextLink
                    href={intakeHref}
                    data-testid="panel-intake-link"
                    className="text-meta text-accent underline underline-offset-2 motion-hover hover:opacity-80"
                  >
                    {labels.intakeAction}
                  </NextLink>
                </div>
              ) : null}

              <ConfirmDestructive
                open={confirmingDisconnect}
                target={item.displayName}
                action={labels.disconnect}
                consequence={labels.disconnectConsequence}
                labels={{ close: labels.close, cancel: labels.cancel }}
                onConfirm={() => {
                  void disconnect(item.name);
                }}
                onCancel={() => {
                  setConfirmingDisconnect(false);
                }}
              />
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
