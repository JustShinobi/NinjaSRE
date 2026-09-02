'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/action';
import { Textarea } from '@/components/form';
import { Modal } from '@/components/overlay';
import { ArrowRightIcon, PlayIcon, SearchIcon } from '@/design/icons';
import { isMessageKey, message, type Locale } from '@/i18n/messages';
import type { LauncherBriefing } from '@/shell/load';
import { act, RUN_ENDPOINT } from './act';
import { Announcer } from './announcer';
import { announce, dismiss, type Outcome } from './outcomes';

/**
 * Starting an investigation from wherever you happen to be.
 *
 * A centred modal, as the board draws it (`StartInvestigation.dc.html`): the
 * objective field, the shortcut, and — before anything is typed — up to three
 * suggestions derived from where the environment already is. The suggestions
 * are derived from what the console already carries (the incident listing,
 * the estate's own summary), never invented: with no data for the first two,
 * only the always-true audit offer appears.
 *
 * The footer says what will actually happen — which team it runs with, that
 * it only proposes, and that the six stages are followed live — because the
 * moment before starting an autonomous investigation is exactly when somebody
 * asks what they are about to set off.
 */

export interface InvestigateLauncherProps {
  readonly open: boolean;
  readonly locale: Locale;
  readonly onClose: () => void;
  /**
   * Whether anything is connected for the investigation to consult.
   *
   * The launcher says so when nothing is. A run against a deployment with no
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
   * instead of after.
   */
  readonly runtimeComposed?: boolean;
  /** Where the environment already is, for the suggestions and the footer. */
  readonly briefing?: LauncherBriefing;
  /** The deployment's own name — the cluster the audit suggestion names. */
  readonly deploymentName?: string;
  /** What the guardian currently permits, the sidebar footer's own datum. */
  readonly posture?: string;
  /** Where the new run's page is. Injected so the suite can watch it. */
  readonly navigate?: (href: string) => void;
}

/** The posture, in the same words the sidebar's own footer uses. */
function postureWord(locale: Locale, posture: string): string {
  const key = `shell.guardian.posture.${posture}`;
  return isMessageKey(key) ? message(locale, key) : posture;
}

export function InvestigateLauncher({
  open,
  locale,
  onClose,
  integrationsConfigured = true,
  runtimeComposed = true,
  briefing = { teamName: '', recurring: null, unhealthy: 0 },
  deploymentName = '',
  posture = 'propose',
  navigate,
}: InvestigateLauncherProps): ReactNode {
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
        recordedAt: {
          href: '/administration?tab=audit',
          label: message(locale, 'nav.audit'),
        },
      }),
    );
  }

  if (!open) return null;

  // Up to three offers, most specific first — and always the audit, which is
  // true of any environment and is the honest floor when nothing else is.
  const suggestions: readonly {
    readonly id: string;
    readonly text: string;
    readonly role: 'danger' | 'info';
  }[] = [
    ...(briefing.recurring === null
      ? []
      : [
          {
            id: 'recurring',
            text: message(locale, 'live.investigate.suggestion.recurring', {
              subject: briefing.recurring.subject,
              count: briefing.recurring.count,
            }),
            role: 'danger' as const,
          },
        ]),
    ...(briefing.unhealthy > 1
      ? [
          {
            id: 'unhealthy',
            text: message(locale, 'live.investigate.suggestion.unhealthy', {
              count: briefing.unhealthy,
            }),
            role: 'danger' as const,
          },
        ]
      : []),
    {
      id: 'audit',
      text: message(locale, 'live.investigate.suggestion.audit', {
        name: deploymentName,
      }),
      role: 'info' as const,
    },
  ];

  return (
    <div
      data-testid="investigate-overlay"
      className="fixed inset-0 z-10 flex items-center justify-center bg-sunken/80 p-5"
    >
      <div className="w-full max-w-prose">
        <Modal
          open
          title={message(locale, 'live.investigate.title')}
          icon={
            <span
              aria-hidden="true"
              className="flex size-7 shrink-0 items-center justify-center rounded-2 bg-accent-bg text-accent edge border-accent"
            >
              <SearchIcon className="icon-head" />
            </span>
          }
          closeLabel={message(locale, 'live.investigate.close')}
          onClose={onClose}
        >
          <div
            data-testid="investigate-drawer"
            className="flex flex-col gap-4"
            onKeyDown={(event) => {
              if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
                event.preventDefault();
                if (startable && !sending) void start();
              }
            }}
          >
            {/* The harder blocker first: a deployment with no runtime cannot
                start a real investigation at all, which is a different claim
                from "quality is lower than it could be" below it. */}
            {runtimeComposed ? null : (
              <p
                className="text-meta text-warning"
                data-testid="investigate-runtime-gap"
              >
                {message(locale, 'failure.investigator.action')}
              </p>
            )}
            {/* Beside the field rather than after the disappointment: the run
                is real either way, and the difference in what it can reach is
                stated rather than discovered. */}
            {integrationsConfigured ? null : (
              <p className="text-meta text-muted" data-testid="investigate-caveat">
                {message(locale, 'live.investigate.caveat')}
              </p>
            )}

            <div className="flex flex-col gap-1">
              <Textarea
                label={message(locale, 'live.investigate.objective')}
                name="objective"
                rows={3}
                value={objective}
                onValueChange={setObjective}
              />
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-micro text-muted">
                  {message(locale, 'live.investigate.hint')}
                </span>
                <span className="ml-auto font-mono text-micro text-muted">
                  {message(locale, 'live.investigate.ctrlEnter')}
                </span>
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <span className="text-micro font-semibold tracking-wide uppercase text-muted">
                {message(locale, 'live.investigate.suggestions')}
              </span>
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion.id}
                  type="button"
                  data-testid="investigate-suggestion"
                  data-suggestion={suggestion.id}
                  className="flex cursor-pointer items-center gap-3 rounded-2 edge border-border bg-sunken px-3 py-2 text-left text-small motion-hover hover:bg-hover"
                  onClick={() => {
                    setObjective(suggestion.text);
                  }}
                >
                  <span
                    aria-hidden="true"
                    className={
                      suggestion.role === 'danger'
                        ? 'icon-inline shrink-0 bg-danger'
                        : 'icon-inline shrink-0 rounded-full bg-info'
                    }
                  />
                  <span className="min-w-0 flex-1">{suggestion.text}</span>
                  <ArrowRightIcon
                    aria-hidden="true"
                    className="icon-inline shrink-0 text-muted"
                  />
                </button>
              ))}
            </div>

            <div className="flex flex-wrap items-center gap-3 edge border-border border-x-0 border-b-0 pt-3">
              <div className="flex min-w-0 flex-col gap-1">
                <span className="text-micro text-muted" data-testid="investigate-team">
                  {briefing.teamName === ''
                    ? message(locale, 'live.investigate.footer.postureOnly', {
                        posture: postureWord(locale, posture),
                      })
                    : message(locale, 'live.investigate.footer.team', {
                        team: briefing.teamName,
                        posture: postureWord(locale, posture),
                      })}
                </span>
                <span className="text-micro text-muted">
                  {message(locale, 'live.investigate.footer.stages')}
                </span>
              </div>
              <span className="ml-auto flex items-center gap-3">
                <Button variant="quiet" onClick={onClose}>
                  {message(locale, 'live.investigate.cancel')}
                </Button>
                <Button
                  variant="primary"
                  data-testid="start-investigation"
                  state={sending ? 'loading' : startable ? 'default' : 'disabled'}
                  onClick={() => {
                    void start();
                  }}
                >
                  <PlayIcon aria-hidden="true" className="icon-inline" />
                  {message(locale, 'live.investigate.start')}
                </Button>
              </span>
            </div>
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
            <Announcer
              locale={locale}
              outcomes={outcomes}
              onDismiss={(id) => {
                setOutcomes((held) => dismiss(held, id));
              }}
            />
          </div>
        </Modal>
      </div>
    </div>
  );
}
