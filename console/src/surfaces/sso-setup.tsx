'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Input } from '@/components/form';
import { Badge } from '@/components/status';
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
}

function text(record: unknown, name: string): string {
  const found: unknown = Reflect.get(Object(record), name);
  return typeof found === 'string' ? found : '';
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

  const current = (field: SsoField): string => values[field] ?? settings[field];
  const edited = SSO_FIELDS.some((field) => current(field) !== settings[field]);

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
      : labels.notVerified;

  return (
    <div data-testid="sso-setup-flow" className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-2">
        <Badge status={state.active ? 'healthy' : 'disabled'} />
        <span data-testid="sso-state" className="text-meta text-muted">
          {stateLabel}
        </span>
      </div>

      {state.problems.length === 0 ? null : (
        <ul
          data-testid="sso-problems"
          className="flex flex-col gap-1 text-meta text-danger"
        >
          <li>{labels.problems}</li>
          {state.problems.map((problem) => (
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
              value={current(field)}
              onValueChange={(next) => {
                setValues((was) => ({ ...was, [field]: next }));
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
