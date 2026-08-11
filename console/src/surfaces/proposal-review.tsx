'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Textarea } from '@/components/form';
import { Badge } from '@/components/status';
import { publishResolved } from '@/shell/attention';

/**
 * Deciding one proposal, with what it would do on the screen first.
 *
 * **The approve control does not exist until the effect has rendered.** It is a
 * client guarantee and it has to be: no API can know whether a person read a
 * diff, and a decision that demanded a "seen it" token would prove only that
 * the browser had asked. What can be built is a document with nothing in it to
 * press — which is the same structure the configuration editor uses for
 * preview-before-save, for the same reason.
 *
 * **Rejecting needs no effect and does need a reason.** Refusing narrows what
 * happens rather than widening it, so there is nothing to preview; the reason is
 * required because it is what the *next* proposal of the same thing is read
 * against, and the route handler enforces it too.
 *
 * **Nothing is computed here.** The configuration a proposal would resolve to is
 * the deployment's answer; so is what a detector would have found. This
 * component posts and renders. A merge or a threshold evaluation written here
 * would agree with the deployment until the day it did not.
 */

/** Where every read and every write goes. The console's own process, forwarding once. */
export const PROPOSAL_ENDPOINT = '/api/proposal';

export interface ProposalReviewLabels {
  readonly show: string;
  readonly loading: string;
  readonly failed: string;
  readonly text: string;
  readonly preview: string;
  readonly dryRun: string;
  readonly dryRunQuiet: string;
  readonly approveFirst: string;
  readonly approve: string;
  readonly reject: string;
  readonly reason: string;
  readonly reasonRequired: string;
}

export interface ProposalReviewProps {
  readonly proposalId: string;
  /** knowledge · operating_context · detector · configuration. */
  readonly kind: string;
  /** The mechanism that answers "what would this do", as the deployment names it. */
  readonly mechanism: string;
  /** What that mechanism is asked about: a node, or a detector. */
  readonly target: string;
  /** The settings patch a configuration or context proposal would write. */
  readonly payload: Readonly<Record<string, unknown>>;
  /** The final text, for the kinds whose effect is their own words. */
  readonly finalText: string;
  /** Absent for a viewer who may not decide — absent, never disabled. */
  readonly decidable: boolean;
  readonly labels: ProposalReviewLabels;
}

/** What came back from asking the deployment what this would do. */
interface Effect {
  readonly kind: 'text' | 'lines' | 'empty' | 'failed';
  readonly lines: readonly string[];
}

function rows(record: unknown, name: string): readonly unknown[] {
  const found: unknown = Reflect.get(Object(record), name);
  return Array.isArray(found) ? found : [];
}

/** The changed paths a configuration preview reports, as one line each. */
function fromPreview(answer: unknown): Effect {
  const changes: unknown = Reflect.get(Object(answer), 'changes');
  const rows = Array.isArray(changes) ? changes : [];
  const rendered = rows.map((row) => {
    const path = String(Reflect.get(Object(row), 'path') ?? '');
    const before = JSON.stringify(Reflect.get(Object(row), 'before') ?? null);
    const after = JSON.stringify(Reflect.get(Object(row), 'after') ?? null);
    return `${path}: ${before} → ${after}`;
  });
  return rendered.length === 0
    ? { kind: 'empty', lines: [] }
    : { kind: 'lines', lines: rendered };
}

/** The prompt a context proposal would produce, which is the literal effect. */
function fromContextPreview(answer: unknown): Effect {
  const context = String(Reflect.get(Object(answer), 'context') ?? '');
  return context === ''
    ? { kind: 'empty', lines: [] }
    : { kind: 'text', lines: [context] };
}

/** What a detector would have concluded against the signals already stored. */
function fromDryRun(answer: unknown): Effect {
  const observed = rows(answer, 'observations').map((row) => {
    const subject = String(Reflect.get(Object(row), 'subject') ?? '');
    const verdict = String(Reflect.get(Object(row), 'verdict') ?? '');
    const detail = String(Reflect.get(Object(row), 'detail') ?? '');
    return [subject, verdict, detail].filter((part) => part !== '').join(' — ');
  });
  return observed.length === 0
    ? { kind: 'empty', lines: [] }
    : { kind: 'lines', lines: observed };
}

/** Approve, or reject with a reason, once what it would do has been read. */
export function ProposalReview({
  proposalId,
  kind,
  mechanism,
  target,
  payload,
  finalText,
  decidable,
  labels,
}: ProposalReviewProps): ReactNode {
  const [effect, setEffect] = useState<Effect | null>(
    // The kinds whose effect is their own words need no round trip: the text is
    // already on the page, so requiring a fetch before approving would be a
    // ceremony rather than a guarantee.
    mechanism === 'text' ? { kind: 'text', lines: [finalText] } : null,
  );
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState('');
  const [sending, setSending] = useState(false);

  async function ask(): Promise<void> {
    setAsking(true);
    try {
      const answer = await fetch(PROPOSAL_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          operation: mechanism === 'config-preview' ? 'preview' : mechanism,
          target,
          payload:
            mechanism === 'detector-dry-run'
              ? {}
              : mechanism === 'context-preview'
                ? contextPatch(payload)
                : { patch: payload },
        }),
      });
      const body: unknown = await answer.json().catch(() => ({}));
      if (!answer.ok) {
        setEffect({ kind: 'failed', lines: [] });
        return;
      }
      setEffect(
        mechanism === 'detector-dry-run'
          ? fromDryRun(body)
          : mechanism === 'context-preview'
            ? fromContextPreview(body)
            : fromPreview(body),
      );
    } catch {
      setEffect({ kind: 'failed', lines: [] });
    } finally {
      setAsking(false);
    }
  }

  function decide(verdict: 'approve' | 'reject'): void {
    setSending(true);
    void fetch(PROPOSAL_ENDPOINT, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        operation: 'decide',
        target: proposalId,
        payload: { verdict, reason },
      }),
    })
      .then((answer) => {
        if (answer.ok) publishResolved(proposalId);
      })
      .finally(() => {
        setSending(false);
      });
  }

  const seen = effect !== null && effect.kind !== 'failed';
  const rejectable = reason.trim() !== '';

  return (
    <div data-testid="proposal-review" data-kind={kind} className="flex flex-col gap-3">
      {effect === null ? (
        <Button
          variant="secondary"
          data-testid="show-effect"
          state={asking ? 'loading' : 'default'}
          onClick={() => {
            void ask();
          }}
        >
          {asking ? labels.loading : labels.show}
        </Button>
      ) : (
        <section data-testid="effect" data-effect={effect.kind}>
          <h4 className="text-meta text-muted mb-1">{headingFor(mechanism, labels)}</h4>
          {effect.kind === 'failed' ? (
            <p className="text-small text-danger">{labels.failed}</p>
          ) : effect.kind === 'empty' ? (
            <p className="text-small text-muted">{labels.dryRunQuiet}</p>
          ) : effect.kind === 'text' ? (
            <pre className="text-small bg-raised rounded-2 p-3 whitespace-pre-wrap break-words">
              {effect.lines.join('\n')}
            </pre>
          ) : (
            <ul className="flex flex-col gap-1">
              {effect.lines.map((line) => (
                <li key={line} className="flex items-start gap-2 min-w-0">
                  <Badge status={kind} />
                  <span className="text-small min-w-0 break-all">{line}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {decidable ? (
        <>
          <Textarea
            label={labels.reason}
            name="reason"
            rows={2}
            value={reason}
            onValueChange={setReason}
          />
          <div className="flex items-center gap-3 flex-wrap">
            {seen ? (
              <Button
                variant="primary"
                data-testid="approve"
                state={sending ? 'loading' : 'default'}
                onClick={() => {
                  decide('approve');
                }}
              >
                {labels.approve}
              </Button>
            ) : (
              <span className="text-meta text-muted" data-testid="approve-first">
                {labels.approveFirst}
              </span>
            )}
            <Button
              variant="destructive"
              data-testid="reject"
              state={sending ? 'loading' : rejectable ? 'default' : 'disabled'}
              onClick={() => {
                decide('reject');
              }}
            >
              {labels.reject}
            </Button>
            {rejectable ? null : (
              <span className="text-meta text-muted">{labels.reasonRequired}</span>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}

/** The heading each mechanism's answer is shown under. */
function headingFor(mechanism: string, labels: ProposalReviewLabels): string {
  if (mechanism === 'detector-dry-run') return labels.dryRun;
  if (mechanism === 'text') return labels.text;
  if (mechanism === 'context-preview') return labels.text;
  return labels.preview;
}

/**
 * The body the context preview takes, from the patch the proposal carries.
 *
 * The route asks for sections and an enabled flag rather than a settings patch,
 * so the two shapes are reconciled here — at the one place that posts, rather
 * than in the payload the proposal was stored with, which has to stay exactly
 * what the applier will write.
 */
function contextPatch(
  payload: Readonly<Record<string, unknown>>,
): Record<string, unknown> {
  const agents: unknown = Reflect.get(Object(payload), 'agents');
  const context: unknown = Reflect.get(Object(agents), 'operating_context');
  const sections: unknown = Reflect.get(Object(context), 'sections');
  return {
    sections: typeof sections === 'object' && sections !== null ? sections : {},
    enabled: Reflect.get(Object(context), 'enabled') !== false,
  };
}
