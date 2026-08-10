'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { StatusDot } from '@/components/status';

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
  readonly passed: string;
  readonly failed: string;
  readonly unchecked: string;
  readonly unreachable: string;
  readonly nothing: string;
  readonly remedy: string;
  readonly findings: string;
}

export interface VerifyStepProps {
  readonly things: readonly VerifiableThing[];
  readonly labels: VerifyStepLabels;
}

export const VERIFY_ENDPOINT = '/api/verify';

interface Verdict {
  readonly state: 'passed' | 'failed' | 'unreachable';
  readonly detail: string;
  readonly remedy: string;
  /** What the deployment measured that makes this source's answers unsafe. */
  readonly findings: readonly string[];
}

/** The `findings` of an answer that crossed a process, as strings or as none. */
function findingsOf(body: unknown): readonly string[] {
  const found: unknown = Reflect.get(Object(body), 'findings');
  return Array.isArray(found) ? found.filter((each) => typeof each === 'string') : [];
}

function keyOf(thing: VerifiableThing): string {
  return `${thing.kind}:${thing.name}`;
}

/** One result line per configured thing, each with its own retry. */
export function VerifyStep({ things, labels }: VerifyStepProps): ReactNode {
  const [verdicts, setVerdicts] = useState<Readonly<Record<string, Verdict>>>({});
  const [running, setRunning] = useState<readonly string[]>([]);

  async function check(thing: VerifiableThing): Promise<void> {
    const key = keyOf(thing);
    setRunning((held) => [...held, key]);
    let verdict: Verdict;
    try {
      const answer = await fetch(VERIFY_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ kind: thing.kind, name: thing.name }),
      });
      const body: unknown = await answer.json().catch(() => ({}));
      const reachable = Reflect.get(Object(body), 'reachable') !== false;
      const reason: unknown = Reflect.get(Object(body), 'reason');
      const remedy: unknown = Reflect.get(Object(body), 'remedy');
      verdict = reachable
        ? {
            state: Reflect.get(Object(body), 'verified') === true ? 'passed' : 'failed',
            detail: typeof reason === 'string' ? reason : '',
            remedy: typeof remedy === 'string' ? remedy : '',
            findings: findingsOf(body),
          }
        : {
            state: 'unreachable',
            detail: labels.unreachable,
            remedy: '',
            findings: [],
          };
    } catch {
      verdict = {
        state: 'unreachable',
        detail: labels.unreachable,
        remedy: '',
        findings: [],
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

  return (
    <ul data-testid="verify-step" className="flex flex-col gap-3">
      {things.map((thing) => {
        const key = keyOf(thing);
        const verdict = verdicts[key];
        const busy = running.includes(key);
        return (
          <li
            key={key}
            data-testid="verify-row"
            data-thing={thing.name}
            data-verdict={verdict?.state ?? 'unchecked'}
            className="flex flex-col gap-1 rounded-3 edge border-border p-3"
          >
            <span className="flex flex-wrap items-center gap-2">
              <StatusDot
                status={
                  verdict === undefined
                    ? 'unknown'
                    : verdict.state === 'passed'
                      ? 'healthy'
                      : 'failed'
                }
              />
              <span className="text-strong">{thing.displayName}</span>
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
            </span>
            <span className="text-meta text-muted">
              {verdict === undefined
                ? labels.unchecked
                : `${verdict.state === 'passed' ? labels.passed : labels.failed} ${verdict.detail}`.trim()}
            </span>
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
  );
}
