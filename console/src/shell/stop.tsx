'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { message, type Locale } from '@/i18n/messages';
import { may, type Viewer } from '@/session/viewer';

/**
 * The emergency stop, in the frame rather than on a screen.
 *
 * Two halves with two different audiences, and the split is the whole design.
 *
 * **The banner is for everybody.** A dashboard where nothing is happening looks
 * identical whether nothing needed doing or every automated write is stopped,
 * and only one of those is something a person has to be told. So it renders for
 * every viewer, on every screen, and it does not go away until the stop is
 * released.
 *
 * **The control is for whoever may stop the deployment.** Absent rather than
 * disabled, the same rule the rest of the shell follows. It is in the utility
 * bar because engaging it is what somebody does when something is going wrong,
 * and at that moment nobody navigates to a settings page to find a button.
 *
 * The confirmation names the consequence in words rather than asking "are you
 * sure": what stops is *every automated write, immediately*, and an operator who
 * has read that sentence has made a different decision from one who clicked
 * through a dialogue.
 */

/** Where the two writes go. The console's own process, forwarding once. */
export const KILL_SWITCH_ENDPOINT = '/api/kill-switch';

/** Who may stop the deployment. A responder, not an administrator. */
const ENGAGE = 'remediation.execute';

export interface KillSwitchProps {
  readonly viewer: Viewer;
  readonly locale: Locale;
  /** What the deployment said when the frame was rendered. */
  readonly engaged: boolean;
}

/** The control, for a viewer who may use it. */
export function KillSwitchControl({
  viewer,
  locale,
  engaged,
}: KillSwitchProps): ReactNode {
  const [stopped, setStopped] = useState(engaged);
  const [confirming, setConfirming] = useState(false);
  const [working, setWorking] = useState(false);
  const [failure, setFailure] = useState('');

  if (!may(viewer, ENGAGE)) return null;

  async function decide(method: 'POST' | 'DELETE'): Promise<void> {
    setWorking(true);
    setFailure('');
    let answer: Response;
    try {
      answer = await fetch(KILL_SWITCH_ENDPOINT, {
        method,
        headers: { 'content-type': 'application/json' },
        ...(method === 'POST'
          ? { body: JSON.stringify({ reason: message(locale, 'stop.reason') }) }
          : {}),
      });
    } catch {
      setWorking(false);
      setFailure(message(locale, 'stop.unreachable'));
      return;
    }
    const body: unknown = await answer.json().catch(() => ({}));
    setWorking(false);
    setConfirming(false);
    if (!answer.ok) {
      setFailure(message(locale, 'stop.refused'));
      return;
    }
    setStopped(Reflect.get(Object(body), 'engaged') === true);
  }

  if (stopped) {
    return (
      <Button
        data-testid="release-stop"
        state={working ? 'loading' : 'default'}
        onClick={() => {
          void decide('DELETE');
        }}
      >
        {message(locale, 'stop.release')}
      </Button>
    );
  }

  return (
    <span className="relative inline-flex items-center gap-2">
      <Button
        variant="destructive"
        data-testid="engage-stop"
        onClick={() => {
          setConfirming(true);
        }}
      >
        {message(locale, 'stop.engage')}
      </Button>
      {confirming ? (
        <span
          data-testid="stop-confirm"
          role="alertdialog"
          aria-label={message(locale, 'stop.engage')}
          className="absolute right-0 top-full z-10 mt-1 flex w-max max-w-prose flex-col gap-2 rounded-3 edge border-danger bg-raised p-3 shadow-2"
        >
          {/* The consequence in words. "Are you sure" asks nothing; this says
              what stops, and it says it before the control that stops it. */}
          <span className="text-small text-text">
            {message(locale, 'stop.consequence')}
          </span>
          <span className="flex items-center gap-2">
            <Button
              variant="destructive"
              data-testid="confirm-stop"
              state={working ? 'loading' : 'default'}
              onClick={() => {
                void decide('POST');
              }}
            >
              {message(locale, 'stop.confirm')}
            </Button>
            <Button
              data-testid="cancel-stop"
              onClick={() => {
                setConfirming(false);
              }}
            >
              {message(locale, 'stop.cancel')}
            </Button>
          </span>
        </span>
      ) : null}
      {failure === '' ? null : (
        <span data-testid="stop-failure" className="text-meta text-danger">
          {failure}
        </span>
      )}
    </span>
  );
}

export interface KillSwitchBannerProps {
  readonly locale: Locale;
  readonly engaged: boolean;
}

/** The banner, for every viewer, on every screen. */
export function KillSwitchBanner({
  locale,
  engaged,
}: KillSwitchBannerProps): ReactNode {
  if (!engaged) return null;
  return (
    <p
      data-testid="stop-banner"
      role="status"
      className="flex items-center gap-3 bg-danger-bg px-5 py-1 text-small text-danger"
    >
      {message(locale, 'stop.engaged')}
    </p>
  );
}
