'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/action';
import { Textarea } from '@/components/form';
import { Drawer } from '@/components/overlay';
import { message, type Locale } from '@/i18n/messages';
import { act, RUN_ENDPOINT } from './act';
import { Announcer } from './announcer';
import { announce, dismiss, type Outcome } from './outcomes';

/**
 * Starting an investigation from wherever you happen to be.
 *
 * A drawer rather than a page, because the thing an operator is looking at when
 * they decide to investigate is the reason they are investigating. Navigating
 * to a form loses it, and what they type instead is a worse objective than the
 * one they would have written with the screen still in front of them.
 *
 * A drawer rather than a modal for the same reason: the context behind it stays
 * visible. A modal is for a confirmation and nothing else.
 */

export interface InvestigateDrawerProps {
  readonly open: boolean;
  readonly locale: Locale;
  readonly onClose: () => void;
  /**
   * Whether anything is connected for the investigation to consult.
   *
   * The drawer says so when nothing is. A run against a deployment with no
   * integration still happens and is still a real investigation — it reasons
   * from what it is told and consults nothing — and somebody who was not warned
   * reads that as the product being poor rather than as the estate being
   * unconnected.
   */
  readonly integrationsConfigured?: boolean;
  /**
   * Whether this process holds a runtime to drive an investigation with.
   *
   * Read here rather than discovered by pressing Start: the request would
   * refuse with `InvestigatorNotConfigured` regardless of what was typed,
   * and this is the one place this console can say so *before* that happens
   * instead of after. The sentence shown is `failure.investigator.action` —
   * the same one the reactive failure translation shows once a run has
   * actually failed — read from the one catalogue entry both share, so the
   * two can never disagree about what is missing.
   */
  readonly runtimeComposed?: boolean;
  /** Where the new run's page is. Injected so the suite can watch it. */
  readonly navigate?: (href: string) => void;
}

export function InvestigateDrawer({
  open,
  locale,
  onClose,
  integrationsConfigured = true,
  runtimeComposed = true,
  navigate,
}: InvestigateDrawerProps): ReactNode {
  const router = useRouter();
  const [objective, setObjective] = useState('');
  const [sending, setSending] = useState(false);
  const [outcomes, setOutcomes] = useState<readonly Outcome[]>([]);

  const objectiveGiven = objective.trim() !== '';
  // An objective alone does not make this startable: without a runtime the
  // request refuses no matter what was typed, and offering a button that is
  // guaranteed to fail is worse than disabling it with the reason attached.
  const startable = objectiveGiven && runtimeComposed;

  async function start(): Promise<void> {
    setSending(true);
    const applied = await act(RUN_ENDPOINT, { action: 'start', text: objective });
    setSending(false);
    if (applied.ok && applied.runId !== '') {
      setObjective('');
      onClose();
      // The router rather than the address bar: a full document load would
      // throw away the frame that is already painted, on the one navigation
      // that happens while somebody is waiting for a run to start.
      const href = `/runs/${applied.runId}`;
      if (navigate === undefined) router.push(href);
      else navigate(href);
      return;
    }
    setOutcomes((held) =>
      announce(held, {
        id: 'investigate-refused',
        role: 'danger',
        message: message(
          locale,
          applied.reachable ? 'live.outcome.refused' : 'live.outcome.unreachable',
          {
            reason: applied.reason,
          },
        ),
        // Refused or not, a start attempt is in the audit trail — which is
        // where somebody looks when they are sure they pressed the button.
        recordedAt: { href: '/audit', label: message(locale, 'nav.audit') },
      }),
    );
  }

  if (!open) return null;

  // `w-full max-w-prose`, never `w-prose`: the second names no utility this
  // stylesheet declares, so the drawer had no width of its own and collapsed
  // onto whatever the longest line inside it happened to be.
  return (
    <div className="fixed inset-y-0 right-0 z-10 flex w-full max-w-prose flex-col overflow-y-auto">
      <Drawer
        open
        title={message(locale, 'live.investigate.title')}
        closeLabel={message(locale, 'live.investigate.close')}
        onClose={onClose}
      >
        <div data-testid="investigate-drawer" className="flex flex-col gap-3">
          {/* The harder blocker first: a deployment with no runtime cannot
              start a real investigation at all, which is a different claim
              from "quality is lower than it could be" below it. */}
          {runtimeComposed ? null : (
            <p className="text-meta text-warning" data-testid="investigate-runtime-gap">
              {message(locale, 'failure.investigator.action')}
            </p>
          )}
          {/* Beside the field rather than after the disappointment. This is
              what resolves "I want to see it work" against "I have not
              connected anything yet": the run is real either way, and the
              difference in what it can reach is stated rather than discovered. */}
          {integrationsConfigured ? null : (
            <p className="text-meta text-muted" data-testid="investigate-caveat">
              {message(locale, 'live.investigate.caveat')}
            </p>
          )}
          <Textarea
            label={message(locale, 'live.investigate.objective')}
            name="objective"
            rows={3}
            value={objective}
            onValueChange={setObjective}
          />
          <div className="flex items-center gap-3 flex-wrap">
            <Button
              variant="primary"
              data-testid="start-investigation"
              state={sending ? 'loading' : startable ? 'default' : 'disabled'}
              onClick={() => {
                void start();
              }}
            >
              {message(locale, 'live.investigate.start')}
            </Button>
            {/* Gated on the objective alone, not on `startable`: the runtime
                caveat above already names its own blocker, and repeating it
                here as "an objective is required" would misname the reason
                for somebody who typed one and is blocked by the runtime
                instead. */}
            {objectiveGiven ? null : (
              <span className="text-meta text-muted">
                {message(locale, 'live.investigate.required')}
              </span>
            )}
          </div>
          <Announcer
            locale={locale}
            outcomes={outcomes}
            onDismiss={(id) => {
              setOutcomes((held) => dismiss(held, id));
            }}
          />
        </div>
      </Drawer>
    </div>
  );
}
