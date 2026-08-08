'use client';

import type { ReactNode } from 'react';
import { useCallback, useState } from 'react';

import { Button } from '@/components/action';
import { Textarea } from '@/components/form';
import { ConfirmDestructive } from '@/components/overlay';
import { message, type Locale } from '@/i18n/messages';
import { publishResolved } from '@/shell/attention';
import { act, ANSWER_ENDPOINT, RUN_ENDPOINT, type Applied } from './act';
import { Announcer } from './announcer';
import { announce, dismiss, type Outcome } from './outcomes';

/**
 * The four things an operator does to a run without leaving the page it is on.
 *
 * Answering the agent's question, adding context to a run that keeps going,
 * taking control of one, and stopping one. All four are optimistic — the screen
 * says what happened before the deployment has confirmed it — and all four
 * revert with the deployment's own reason if it refuses, because a screen that
 * goes on asserting something that was rejected is worse than a screen that
 * waited.
 *
 * Every outcome is announced *and* recorded: the toast names the run's own
 * transcript, which is where the event lands whether anybody read the toast or
 * not.
 */

/** What every control here shares: who is looking, and which run. */
interface ControlProps {
  readonly runId: string;
  readonly locale: Locale;
}

/** The durable record every outcome on this page names. */
function recorded(runId: string, locale: Locale): Outcome['recordedAt'] {
  return { href: `/runs/${runId}`, label: message(locale, 'live.outcome.recorded') };
}

/** How a refusal reads, in the deployment's own words where it gave any. */
function refusal(applied: Applied, locale: Locale): string {
  if (!applied.reachable) return message(locale, 'live.outcome.unreachable');
  return message(locale, 'live.outcome.refused', {
    reason:
      applied.reason === ''
        ? message(locale, 'live.decided.elsewhere')
        : applied.reason,
  });
}

/** The announcement stack every control on this page publishes into. */
function useOutcomes(): {
  readonly outcomes: readonly Outcome[];
  readonly say: (outcome: Outcome) => void;
  readonly drop: (id: string) => void;
} {
  const [outcomes, setOutcomes] = useState<readonly Outcome[]>([]);
  const say = useCallback((outcome: Outcome) => {
    setOutcomes((held) => announce(held, outcome));
  }, []);
  const drop = useCallback((id: string) => {
    setOutcomes((held) => dismiss(held, id));
  }, []);
  return { outcomes, say, drop };
}

export interface AnswerControlsProps extends ControlProps {
  /** The interaction the question belongs to; the API is addressed by it. */
  readonly interactionId: string;
  readonly question: string;
  readonly options: readonly string[];
}

/**
 * An agent's question, answered where it was asked.
 *
 * Answering is what resumes the run — the interaction is what it is blocked on
 * — so the control says so rather than calling itself "submit". A person who
 * thinks they are filing a note does not come back to check.
 */
export function AnswerControls({
  runId,
  locale,
  interactionId,
  question,
  options,
}: AnswerControlsProps): ReactNode {
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [answered, setAnswered] = useState(false);
  const { outcomes, say, drop } = useOutcomes();

  const answerable = text.trim() !== '';

  async function answer(option: string): Promise<void> {
    setSending(true);
    // On screen first. The event that closes this interaction is on its way,
    // and this stands in for it until it arrives.
    setAnswered(true);
    const applied = await act(ANSWER_ENDPOINT, { interactionId, text, option });
    setSending(false);
    if (applied.ok) {
      publishResolved(interactionId);
      say({
        id: `${interactionId}-answered`,
        role: 'success',
        message: question,
        recordedAt: recorded(runId, locale),
      });
      return;
    }
    // Put it back. The question is still open and still needs somebody.
    setAnswered(false);
    say({
      id: `${interactionId}-refused`,
      role: 'danger',
      message: refusal(applied, locale),
      recordedAt: recorded(runId, locale),
    });
  }

  if (answered) {
    return (
      <p data-testid="answered" className="text-small text-muted">
        {message(locale, 'live.question.title')}
        <Announcer locale={locale} outcomes={outcomes} onDismiss={drop} />
      </p>
    );
  }

  return (
    <div data-testid="answer" className="flex flex-col gap-3">
      <p className="text-small">{question}</p>
      <Textarea
        label={message(locale, 'live.question.label')}
        name="answer"
        rows={2}
        value={text}
        onValueChange={setText}
      />
      <div className="flex items-center gap-3 flex-wrap">
        {options.map((option) => (
          <Button
            key={option}
            data-testid="answer-option"
            state={sending ? 'loading' : 'default'}
            onClick={() => {
              setText(option);
              void answer(option);
            }}
          >
            {option}
          </Button>
        ))}
        <Button
          variant="primary"
          data-testid="answer-send"
          state={sending ? 'loading' : answerable ? 'default' : 'disabled'}
          onClick={() => {
            void answer('');
          }}
        >
          {message(locale, 'live.question.answer')}
        </Button>
        {answerable ? null : (
          <span className="text-meta text-muted">
            {message(locale, 'live.question.required')}
          </span>
        )}
      </div>
      <Announcer locale={locale} outcomes={outcomes} onDismiss={drop} />
    </div>
  );
}

export interface TakeoverControlsProps extends ControlProps {
  /** Whether the run is still going. A finished run is steered by nobody. */
  readonly running: boolean;
}

/**
 * Taking control of a run, handing it back, and stopping it.
 *
 * Taking over is not stopping: the run suspends at its next safe point and
 * keeps what it has found, and handing it back resumes it with what the person
 * did in context. Stopping is the one that cannot be undone, so it is the one
 * behind a confirmation that names the run and says what stopping it costs.
 */
export function TakeoverControls({
  runId,
  locale,
  running,
}: TakeoverControlsProps): ReactNode {
  const [held, setHeld] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [sending, setSending] = useState(false);
  const { outcomes, say, drop } = useOutcomes();

  async function steer(action: string, optimistic: boolean): Promise<void> {
    setSending(true);
    const before = held;
    setHeld(optimistic);
    const applied = await act(RUN_ENDPOINT, { runId, action });
    setSending(false);
    if (applied.ok) {
      say({
        id: `${runId}-${action}`,
        role: action === 'cancel' ? 'warning' : 'success',
        message: message(locale, 'live.takeover.taken'),
        recordedAt: recorded(runId, locale),
      });
      return;
    }
    setHeld(before);
    say({
      id: `${runId}-${action}-refused`,
      role: 'danger',
      message: refusal(applied, locale),
      recordedAt: recorded(runId, locale),
    });
  }

  return (
    <div
      data-testid="takeover"
      data-held={held ? 'true' : 'false'}
      className="flex flex-col gap-3"
    >
      <div className="flex items-center gap-3 flex-wrap">
        {held ? (
          <Button
            data-testid="hand-back"
            state={sending ? 'loading' : 'default'}
            onClick={() => {
              void steer('resume', false);
            }}
          >
            {message(locale, 'live.takeover.resume')}
          </Button>
        ) : (
          <Button
            data-testid="take-over"
            state={sending || !running ? 'disabled' : 'default'}
            onClick={() => {
              void steer('take-over', true);
            }}
          >
            {message(locale, 'live.takeover.take')}
          </Button>
        )}
        <Button
          variant="destructive"
          data-testid="stop-run"
          state={running ? 'default' : 'disabled'}
          onClick={() => {
            setConfirming(true);
          }}
        >
          {message(locale, 'live.takeover.cancel')}
        </Button>
      </div>
      {held ? (
        <p className="text-small text-muted">
          {message(locale, 'live.takeover.taken')}
        </p>
      ) : null}

      {/* Named target, named consequence. "This will change something" is not a
          confirmation; it is a second click. */}
      <ConfirmDestructive
        open={confirming}
        target={runId}
        action={message(locale, 'live.takeover.cancel')}
        consequence={message(locale, 'live.takeover.consequence')}
        labels={{
          close: message(locale, 'live.takeover.close'),
          cancel: message(locale, 'live.takeover.keep'),
        }}
        onConfirm={() => {
          setConfirming(false);
          void steer('cancel', held);
        }}
        onCancel={() => {
          setConfirming(false);
        }}
      />
      <Announcer locale={locale} outcomes={outcomes} onDismiss={drop} />
    </div>
  );
}

/**
 * Something the investigation should know, delivered without stopping it.
 *
 * The alternative an operator reaches for otherwise is cancelling the run and
 * starting a new one with a better objective, which throws away everything it
 * had found. A note on the next turn costs nothing and keeps the evidence.
 */
export function AddContext({ runId, locale }: ControlProps): ReactNode {
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const { outcomes, say, drop } = useOutcomes();

  const sendable = text.trim() !== '';

  async function send(): Promise<void> {
    setSending(true);
    const said = text;
    // Cleared immediately: the note is on its way, and a box that stayed full
    // is a box somebody sends twice.
    setText('');
    const applied = await act(RUN_ENDPOINT, { runId, action: 'message', text: said });
    setSending(false);
    if (applied.ok) {
      say({
        id: `${runId}-context`,
        role: 'success',
        message: message(locale, 'live.context.sent'),
        recordedAt: recorded(runId, locale),
      });
      return;
    }
    // Put the words back, so nobody has to type them again to find out why.
    setText(said);
    say({
      id: `${runId}-context-refused`,
      role: 'danger',
      message: refusal(applied, locale),
      recordedAt: recorded(runId, locale),
    });
  }

  return (
    <div data-testid="add-context" className="flex flex-col gap-3">
      <Textarea
        label={message(locale, 'live.context.label')}
        name="context"
        rows={2}
        value={text}
        onValueChange={setText}
      />
      <Button
        data-testid="send-context"
        state={sending ? 'loading' : sendable ? 'default' : 'disabled'}
        onClick={() => {
          void send();
        }}
      >
        {message(locale, 'live.context.send')}
      </Button>
      <Announcer locale={locale} outcomes={outcomes} onDismiss={drop} />
    </div>
  );
}
