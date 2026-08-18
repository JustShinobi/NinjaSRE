'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Input } from '@/components/form';
import { SsoStateChip } from '@/components/status';
import type { Locale } from '@/i18n/messages';
import { SSO_FIELDS, type SsoField } from './sso-fields';

/**
 * Configuring an identity provider as a flow: configure, test with a real
 * claim set, and only then let it be the way in.
 *
 * The state machine below is unchanged from the one this replaces
 * (`surfaces/sso.tsx`'s `SsoForm`, still in service until the Administration
 * screen it belongs to is retired): the deployment's own `verified` flag
 * decides whether Activate exists at all, an edit clears it locally the
 * instant a field changes, and the deployment's own answer after Save or Test
 * is the only thing ever written to state. What changes here is what the
 * three moments look like — three sections in the order they happen, each
 * field carries what it is and where to find it, and the test's answer is the
 * claims themselves (identity, team, role), not one collapsed sentence.
 */

export const SSO_ENDPOINT = '/api/sso';

export interface SsoSetupLabels {
  readonly field: Readonly<Record<SsoField, string>>;
  /** What the field is, and where to find it in the provider's own console. */
  readonly fieldHelp: Readonly<Record<SsoField, string>>;
  readonly stepConfigure: string;
  readonly stepTest: string;
  readonly stepActivate: string;
  readonly save: string;
  readonly saving: string;
  readonly test: string;
  readonly testing: string;
  readonly claims: string;
  readonly claimsHelp: string;
  readonly activate: string;
  readonly activating: string;
  readonly active: string;
  readonly verified: string;
  readonly notVerified: string;
  /** Shown instead of `notVerified` while nothing is configured and nobody
   * has touched or submitted the form yet — "nothing recorded" is a
   * different fact from "recorded and not yet tested". */
  readonly notConfigured: string;
  readonly testFirst: string;
  readonly pendingEdit: string;
  readonly failed: string;
  readonly unreachable: string;
  readonly problems: string;
  readonly resultSubject: string;
  readonly resultEmail: string;
  readonly resultTeam: string;
  readonly resultTeamDefault: string;
  readonly resultFailed: string;
  readonly fallback: string;
}

export interface SsoSetupProps {
  readonly settings: Readonly<Record<SsoField, string>>;
  readonly isActive: boolean;
  readonly verified: boolean;
  readonly problems: readonly string[];
  readonly labels: SsoSetupLabels;
  readonly locale: Locale;
}

function text(record: unknown, name: string): string {
  const found: unknown = Reflect.get(Object(record), name);
  return typeof found === 'string' ? found : '';
}

/**
 * The field `problem` is about, read from its own leading word — the
 * deployment names the field it is complaining about first, before the rest
 * of the sentence. `undefined` for a problem naming no field this form
 * declares, which stays unanchored rather than guessed at.
 */
function problemField(problem: string): SsoField | undefined {
  const token = problem.split(' ')[0] ?? '';
  return SSO_FIELDS.find((field) => field === token);
}

/** `problem`, with the payload key at its head replaced by the field's own label. */
function humanised(problem: string, labels: SsoSetupLabels): string {
  const field = problemField(problem);
  if (field === undefined) return problem;
  return `${labels.field[field]}${problem.slice(field.length)}`;
}

interface TestOutcome {
  readonly succeeded: boolean;
  readonly subject: string;
  readonly email: string;
  readonly mappedNodeId: string;
  readonly usedDefault: boolean;
  readonly problems: readonly string[];
}

/** Configure a provider, test it against real claims, and only then activate it. */
export function SsoSetupFlow({
  settings,
  isActive,
  verified,
  problems,
  labels,
  locale,
}: SsoSetupProps): ReactNode {
  const [values, setValues] = useState<Readonly<Record<string, string>>>({});
  const [claims, setClaims] = useState('');
  const [state, setState] = useState({
    active: isActive,
    verified,
    problems: [...problems],
  });
  const [busy, setBusy] = useState('');
  const [failure, setFailure] = useState('');
  const [result, setResult] = useState<TestOutcome | null>(null);
  // Virgin, touched by field, or submitted — what decides whether a problem
  // the deployment already reported may be shown. A field this operator has
  // not reached yet, on a form nobody has submitted, shows nothing: the
  // deployment's own verdict is true, and it is still not an accusation
  // until the operator had a chance to answer it.
  const [touched, setTouched] = useState<ReadonlySet<SsoField>>(new Set());
  const [submitted, setSubmitted] = useState(false);

  const current = (field: SsoField): string => values[field] ?? settings[field];
  const edited = SSO_FIELDS.some((field) => current(field) !== settings[field]);

  /** Whether `problem` may be shown yet, given what has been touched or submitted. */
  function visible(problem: string): boolean {
    if (submitted) return true;
    const field = problemField(problem);
    return field !== undefined && touched.has(field);
  }

  const shown = state.problems.filter(visible);
  /** `field`'s own first visible problem, humanised — `undefined` once it has none. */
  function errorFor(field: SsoField): string | undefined {
    const found = shown.find((problem) => problemField(problem) === field);
    return found === undefined ? undefined : humanised(found, labels);
  }
  // A problem naming no field this form declares has nowhere to be anchored
  // beside, so it falls back to a list of its own — shown only once
  // submission means every pending problem is fair to show.
  const unanchored = shown.filter((problem) => problemField(problem) === undefined);

  // Genuinely nothing recorded, and nobody has asked yet: the neutral
  // summary, not the ordinary "not tested" wording, which would read as a
  // deployment that tried and failed rather than one nobody has configured.
  const nothingConfigured = SSO_FIELDS.every((field) => settings[field] === '');
  const unconfigured = nothingConfigured && touched.size === 0 && !submitted;

  async function ask(operation: string, payload: unknown): Promise<unknown> {
    setBusy(operation);
    setFailure('');
    let response: Response;
    try {
      response = await fetch(SSO_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ operation, payload }),
      });
    } catch {
      setBusy('');
      setFailure(labels.unreachable);
      return null;
    }
    const body: unknown = await response.json().catch(() => ({}));
    setBusy('');
    if (!response.ok) {
      const reason: unknown = Reflect.get(Object(body), 'reason');
      setFailure(typeof reason === 'string' && reason !== '' ? reason : labels.failed);
      return null;
    }
    return Reflect.get(Object(body), 'answer');
  }

  function adopt(answered: unknown): void {
    const problemList: unknown = Reflect.get(Object(answered), 'problems');
    setState({
      active: Reflect.get(Object(answered), 'is_active') === true,
      verified: Reflect.get(Object(answered), 'verified') === true,
      problems: Array.isArray(problemList) ? problemList.map(String) : [],
    });
  }

  async function save(): Promise<void> {
    // Submission itself, not the answer it eventually gets: a save the
    // deployment goes on to refuse is still the moment every pending problem
    // becomes fair to show.
    setSubmitted(true);
    const payload: Record<string, unknown> = {};
    for (const field of SSO_FIELDS) payload[field] = current(field);
    const answered = await ask('save', payload);
    if (answered === null) return;
    setValues({});
    setResult(null);
    adopt(answered);
  }

  async function test(): Promise<void> {
    let parsed: unknown;
    try {
      parsed = JSON.parse(claims);
    } catch {
      setFailure(labels.failed);
      return;
    }
    const answered = await ask('test', { claims: parsed });
    if (answered === null) return;
    const succeeded = Reflect.get(Object(answered), 'succeeded') === true;
    const problemList: unknown = Reflect.get(Object(answered), 'problems');
    setResult({
      succeeded,
      subject: text(answered, 'subject'),
      email: text(answered, 'email'),
      mappedNodeId: text(answered, 'mapped_node_id'),
      usedDefault: Reflect.get(Object(answered), 'used_default') === true,
      problems: Array.isArray(problemList) ? problemList.map(String) : [],
    });
    setState((was) => ({ ...was, verified: succeeded }));
  }

  async function makeActive(): Promise<void> {
    const answered = await ask('activate', {});
    if (answered !== null) adopt(answered);
  }

  const stateLabel = state.active
    ? labels.active
    : state.verified
      ? labels.verified
      : unconfigured
        ? labels.notConfigured
        : labels.notVerified;

  return (
    <div data-testid="sso-setup-flow" className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-2">
        <SsoStateChip locale={locale} active={state.active} />
        <span data-testid="sso-state" className="text-meta text-muted">
          {stateLabel}
        </span>
      </div>

      {unanchored.length === 0 ? null : (
        <ul
          data-testid="sso-problems"
          className="flex flex-col gap-1 text-meta text-danger"
        >
          <li>{labels.problems}</li>
          {unanchored.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}

      <section data-testid="sso-step-configure" className="flex flex-col gap-3">
        <h3 className="text-strong">{labels.stepConfigure}</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {SSO_FIELDS.map((field) => (
            <Input
              key={field}
              label={labels.field[field]}
              name={field}
              description={labels.fieldHelp[field]}
              error={errorFor(field)}
              value={current(field)}
              onValueChange={(next) => {
                setValues((was) => ({ ...was, [field]: next }));
              }}
              onBlur={() => {
                setTouched((was) => (was.has(field) ? was : new Set(was).add(field)));
              }}
            />
          ))}
        </div>
        <div>
          <Button
            variant="primary"
            data-testid="save-sso"
            state={busy === 'save' ? 'loading' : edited ? 'default' : 'disabled'}
            onClick={() => {
              void save();
            }}
          >
            {busy === 'save' ? labels.saving : labels.save}
          </Button>
        </div>
      </section>

      <section data-testid="sso-step-test" className="flex flex-col gap-3">
        <h3 className="text-strong">{labels.stepTest}</h3>
        <Input
          label={labels.claims}
          name="sso-claims"
          description={labels.claimsHelp}
          value={claims}
          onValueChange={setClaims}
        />
        <div>
          <Button
            data-testid="test-sso"
            state={
              busy === 'test'
                ? 'loading'
                : claims.trim() === '' || edited
                  ? 'disabled'
                  : 'default'
            }
            onClick={() => {
              void test();
            }}
          >
            {busy === 'test' ? labels.testing : labels.test}
          </Button>
        </div>

        {result === null ? null : result.succeeded ? (
          <dl data-testid="sso-test-result" className="flex flex-col gap-1 text-meta">
            <div className="flex gap-2">
              <dt className="text-muted">{labels.resultSubject}</dt>
              <dd data-testid="sso-result-subject">{result.subject}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-muted">{labels.resultEmail}</dt>
              <dd data-testid="sso-result-email">{result.email}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-muted">{labels.resultTeam}</dt>
              <dd data-testid="sso-result-team">
                {result.mappedNodeId}
                {result.usedDefault ? ` (${labels.resultTeamDefault})` : ''}
              </dd>
            </div>
          </dl>
        ) : (
          <ul
            data-testid="sso-test-result"
            className="flex flex-col gap-1 text-meta text-danger"
          >
            <li>{labels.resultFailed}</li>
            {result.problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}
      </section>

      <section data-testid="sso-step-activate" className="flex flex-col gap-3">
        <h3 className="text-strong">{labels.stepActivate}</h3>
        {/* Absent, never disabled. A control that exists and refuses is one
            somebody presses during an incident and then reports as broken. */}
        {state.verified && !edited ? (
          <div>
            <Button
              data-testid="activate-sso"
              state={busy === 'activate' ? 'loading' : 'default'}
              onClick={() => {
                void makeActive();
              }}
            >
              {busy === 'activate' ? labels.activating : labels.activate}
            </Button>
          </div>
        ) : (
          <span data-testid="sso-test-first" className="text-meta text-muted">
            {edited ? labels.pendingEdit : labels.testFirst}
          </span>
        )}
        <p data-testid="sso-fallback" className="text-meta text-muted">
          {labels.fallback}
        </p>
      </section>

      {failure === '' ? null : (
        <span data-testid="sso-failure" className="text-meta text-danger">
          {failure}
        </span>
      )}
    </div>
  );
}
