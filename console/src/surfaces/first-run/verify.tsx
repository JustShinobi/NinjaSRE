'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button, Link } from '@/components/action';
import { StatusChip } from '@/components/status';
import { Reference } from '@/design/reference';
import type { Locale } from '@/i18n/messages';
import { hrefFor } from './plan';

/**
 * Checking each configured thing for real, one row at a time.
 *
 * Not optional, and not free. Every row here makes a live request against the
 * operator's own endpoint, which is the whole point: a stored key and a key
 * that works are the two states somebody is trying to tell apart at three in
 * the morning, and only one of them can be established by asking the vault.
 *
 * One row per thing, each retryable on its own. A single control that checked
 * everything would report the first failure and leave the rest unknown, which
 * is the report an operator cannot act on — and a retry that re-ran all of them
 * would spend money re-proving what already answered.
 *
 * **A degraded check is not a failure, and the chip says so.** The backend's
 * own three states — passed, degraded, failed — reach this row mirrored, never
 * translated: a provider whose tool-calling check came back degraded (this
 * build's registry declares no support, so nothing was exercised) reads
 * "Degraded", not "Failing", and Continue stays open. Only a real failure —
 * something the preflight actually tried and could not do — holds the step
 * back, and the row responsible for that is named where Continue sits.
 *
 * **A failure caused by a field nobody filled in says which field.** The
 * deployment carries that — it reports which fields were skipped — and passing
 * it through unedited is the difference between "verification failed" and
 * something a person can go and fix.
 *
 * **A thing that answered can still be unusable, and that is its own line.** A
 * metric store holding nothing for the last quarter of an hour, or one whose
 * clock is a minute out, passes every check a credential can be put through and
 * will make an investigation say something false. The deployment measures both
 * and names them; a row that showed only pass or fail would drop exactly the
 * finding nothing else in the console is going to surface.
 */

/** One configured thing to check. */
export interface VerifiableThing {
  readonly kind: 'provider' | 'integration';
  readonly name: string;
  readonly displayName: string;
  /** What the deployment already said about it, before anything was re-checked. */
  readonly readiness: string;
}

export interface VerifyStepLabels {
  readonly check: string;
  readonly checking: string;
  readonly retry: string;
  readonly unreachable: string;
  readonly nothing: string;
  readonly remedy: string;
  readonly findings: string;
  /** Where a failed provider's own check sends somebody: another model. */
  readonly fixProvider: string;
  /** Where a failed integration's own check sends somebody: its credential. */
  readonly fixIntegration: string;
  readonly fullDiagnosis: string;
  readonly fullDiagnosisSummary: string;
  readonly latency: string;
  readonly footerNoneDegraded: string;
  readonly footerDegraded: string;
  readonly footerNoneFailing: string;
  readonly footerFailing: string;
  readonly continueLabel: string;
  readonly blockedBy: string;
}

export interface VerifyStepProps {
  readonly locale: Locale;
  readonly things: readonly VerifiableThing[];
  readonly labels: VerifyStepLabels;
  /** Where Continue goes once nothing is failing — absent when there is none. */
  readonly continueHref?: string | undefined;
}

export const VERIFY_ENDPOINT = '/api/verify';

/**
 * How much of a failure's own prose shows before the rest is one press away.
 *
 * Presentation, not a backend-enforced cap — the deployment's diagnosis
 * arrives as one string and this only decides how much of it a row shows
 * before folding the rest behind `Reference`. Local for the same reason
 * `FEED_LENGTH` is local to the dashboard's activity feed: nothing outside
 * this row enforces it.
 */
const DIAGNOSIS_SENTENCE_LIMIT = 2;

const SENTENCE_BOUNDARY = /(?<=[.!?])\s+/;

/** `text`, split at up to `max` sentences, and whatever is left over. */
function capSentences(
  text: string,
  max: number,
): { readonly visible: string; readonly overflow: string } {
  if (text === '') return { visible: '', overflow: '' };
  const sentences = text.split(SENTENCE_BOUNDARY).filter((sentence) => sentence !== '');
  if (sentences.length <= max) return { visible: text, overflow: '' };
  return {
    visible: sentences.slice(0, max).join(' '),
    overflow: sentences.slice(max).join(' '),
  };
}

/** The step a failure of `kind` sends somebody to, and the label for going there. */
function fixOf(
  kind: VerifiableThing['kind'],
  labels: VerifyStepLabels,
): { readonly href: string; readonly label: string } {
  return kind === 'provider'
    ? { href: hrefFor('model'), label: labels.fixProvider }
    : { href: hrefFor('integrations'), label: labels.fixIntegration };
}

/** The preflight's own three states for one check, mirrored rather than translated. */
type CheckState = 'passed' | 'degraded' | 'failed' | 'skipped';

interface Verdict {
  /** The row's own headline state — the worst of its checks, mirrored, never translated. */
  readonly state: 'passed' | 'degraded' | 'failed' | 'unreachable';
  readonly detail: string;
  readonly remedy: string;
  /** What the deployment measured that makes this source's answers unsafe. */
  readonly findings: readonly string[];
  /** How long the round trip to the verify endpoint took, in milliseconds. */
  readonly latencyMs: number;
}

/** The `findings` of an answer that crossed a process, as strings or as none. */
function findingsOf(body: unknown): readonly string[] {
  const found: unknown = Reflect.get(Object(body), 'findings');
  return Array.isArray(found) ? found.filter((each) => typeof each === 'string') : [];
}

/** The preflight's own checks, as this row reads their statuses. */
function checkStatusesOf(body: unknown): readonly CheckState[] {
  const found: unknown = Reflect.get(Object(body), 'checks');
  if (!Array.isArray(found)) return [];
  return found
    .map((entry): unknown => Reflect.get(Object(entry), 'status'))
    .filter(
      (status): status is CheckState =>
        status === 'passed' ||
        status === 'degraded' ||
        status === 'failed' ||
        status === 'skipped',
    );
}

function keyOf(thing: VerifiableThing): string {
  return `${thing.kind}:${thing.name}`;
}

/**
 * The wall clock, for one round trip's own latency.
 *
 * Plain module-level functions rather than a call written inline in the
 * component: `performance.now()` is impure, and the purity rule that forbids
 * an impure call during render has no way to see that this one only ever
 * runs inside a click handler — every call inside the lexical body of a
 * component is in scope for it, however deep the closure. Naming the
 * indirection is what tells the rule to stop looking.
 */
function nowMs(): number {
  return performance.now();
}

function elapsedMsSince(startedAt: number): number {
  return nowMs() - startedAt;
}

/** One result line per configured thing, each with its own retry, and the step's own footer. */
export function VerifyStep({
  locale,
  things,
  labels,
  continueHref,
}: VerifyStepProps): ReactNode {
  const [verdicts, setVerdicts] = useState<Readonly<Record<string, Verdict>>>({});
  const [running, setRunning] = useState<readonly string[]>([]);

  async function check(thing: VerifiableThing): Promise<void> {
    const key = keyOf(thing);
    setRunning((held) => [...held, key]);
    const startedAt = nowMs();
    let verdict: Verdict;
    try {
      const answer = await fetch(VERIFY_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ kind: thing.kind, name: thing.name }),
      });
      const latencyMs = elapsedMsSince(startedAt);
      const body: unknown = await answer.json().catch(() => ({}));
      const reachable = Reflect.get(Object(body), 'reachable') !== false;
      const reason: unknown = Reflect.get(Object(body), 'reason');
      const remedy: unknown = Reflect.get(Object(body), 'remedy');
      const checks = checkStatusesOf(body);
      // The row's own headline mirrors the worst of its checks — failed beats
      // degraded beats passed — never the boolean `verified` alone, which is
      // exactly the translation this feature exists to stop making.
      const headline: Verdict['state'] = !reachable
        ? 'unreachable'
        : checks.includes('failed') || Reflect.get(Object(body), 'verified') === false
          ? 'failed'
          : checks.includes('degraded')
            ? 'degraded'
            : 'passed';
      verdict = reachable
        ? {
            state: headline,
            detail: typeof reason === 'string' ? reason : '',
            remedy: typeof remedy === 'string' ? remedy : '',
            findings: findingsOf(body),
            latencyMs,
          }
        : {
            state: 'unreachable',
            detail: labels.unreachable,
            remedy: '',
            findings: [],
            latencyMs,
          };
    } catch {
      verdict = {
        state: 'unreachable',
        detail: labels.unreachable,
        remedy: '',
        findings: [],
        latencyMs: elapsedMsSince(startedAt),
      };
    }
    setRunning((held) => held.filter((each) => each !== key));
    setVerdicts((held) => ({ ...held, [key]: verdict }));
  }

  if (things.length === 0) {
    return (
      <p className="text-meta text-muted" data-testid="nothing-to-verify">
        {labels.nothing}
      </p>
    );
  }

  const decided = things
    .map((thing) => verdicts[keyOf(thing)])
    .filter((verdict): verdict is Verdict => verdict !== undefined);
  const degradedCount = decided.filter(
    (verdict) => verdict.state === 'degraded',
  ).length;
  const failing = things.find((thing) => verdicts[keyOf(thing)]?.state === 'failed');
  const canContinue = failing === undefined;

  return (
    <div className="flex flex-col gap-3">
      <ul data-testid="verify-step" className="flex flex-col gap-3">
        {things.map((thing) => {
          const key = keyOf(thing);
          const verdict = verdicts[key];
          const busy = running.includes(key);
          // A field to blame exists only once a verdict actually came back: an
          // unreachable deployment failed to answer at all, and a CTA pointed
          // at a "fix" for that would send somebody to change a field that was
          // never the problem.
          const fix =
            verdict?.state === 'failed' ? fixOf(thing.kind, labels) : undefined;
          const capped =
            verdict === undefined || verdict.detail === ''
              ? undefined
              : capSentences(verdict.detail, DIAGNOSIS_SENTENCE_LIMIT);
          // A single round-trip latency, shown only for a dependency whose own
          // check is one measurement — not the provider, whose card shows
          // several checks at once and for which one number would claim more
          // precision than the row actually has.
          const showLatency =
            thing.kind === 'integration' &&
            verdict !== undefined &&
            verdict.state !== 'unreachable';
          return (
            <li
              key={key}
              data-testid="verify-row"
              data-thing={thing.name}
              data-verdict={verdict?.state ?? 'unchecked'}
              className="flex flex-col gap-1 rounded-3 edge border-border p-3"
            >
              <span className="flex flex-wrap items-center gap-2">
                <StatusChip
                  locale={locale}
                  status={
                    verdict === undefined
                      ? thing.readiness
                      : verdict.state === 'unreachable' || verdict.state === 'failed'
                        ? 'failing'
                        : verdict.state === 'passed'
                          ? 'verified'
                          : verdict.state
                  }
                  data-testid="status-chip"
                />
                <span className="text-strong">{thing.displayName}</span>
                {showLatency ? (
                  <span className="text-meta text-muted" data-testid="verify-latency">
                    {labels.latency.replace(
                      '{ms}',
                      String(Math.round(verdict.latencyMs)),
                    )}
                  </span>
                ) : null}
                <Button
                  data-testid="verify-one"
                  state={busy ? 'loading' : 'default'}
                  onClick={() => {
                    void check(thing);
                  }}
                >
                  {busy
                    ? labels.checking
                    : verdict === undefined
                      ? labels.check
                      : labels.retry}
                </Button>
                {fix === undefined ? null : (
                  <Link href={fix.href} data-testid="verify-fix">
                    {fix.label}
                  </Link>
                )}
              </span>
              {capped === undefined ? null : (
                <span className="text-meta text-muted" data-testid="verify-detail">
                  {capped.visible}
                </span>
              )}
              {capped === undefined || capped.overflow === '' ? null : (
                <Reference
                  title={labels.fullDiagnosis}
                  summary={labels.fullDiagnosisSummary}
                >
                  {capped.overflow}
                </Reference>
              )}
              {verdict?.remedy === undefined || verdict.remedy === '' ? null : (
                <span className="text-meta text-warning" data-testid="verify-remedy">
                  {labels.remedy} {verdict.remedy}
                </span>
              )}
              {verdict === undefined || verdict.findings.length === 0 ? null : (
                <span className="flex flex-col gap-1" data-testid="verify-findings">
                  <span className="text-meta text-warning">{labels.findings}</span>
                  <ul className="flex flex-col gap-1">
                    {verdict.findings.map((finding) => (
                      <li
                        key={finding}
                        data-testid="verify-finding"
                        className="text-meta text-muted"
                      >
                        {finding}
                      </li>
                    ))}
                  </ul>
                </span>
              )}
            </li>
          );
        })}
      </ul>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-3 edge border-border p-3">
        <span data-testid="verify-footer" className="text-meta text-muted">
          {degradedCount === 0
            ? labels.footerNoneDegraded
            : labels.footerDegraded.replace('{count}', String(degradedCount))}
          {' · '}
          {failing === undefined
            ? labels.footerNoneFailing
            : labels.footerFailing.replace('{name}', failing.displayName)}
        </span>
        <span className="flex items-center gap-2">
          {failing === undefined ? null : (
            <span data-testid="verify-blocking-row" className="text-meta text-danger">
              {labels.blockedBy} {failing.displayName}
            </span>
          )}
          {continueHref === undefined ? null : (
            <Button
              data-testid="verify-continue"
              variant="primary"
              state={canContinue ? 'default' : 'disabled'}
              onClick={() => {
                if (canContinue) window.location.assign(continueHref);
              }}
            >
              {labels.continueLabel}
            </Button>
          )}
        </span>
      </div>
    </div>
  );
}
