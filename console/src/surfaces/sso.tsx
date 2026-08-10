'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Input } from '@/components/form';
import { Badge } from '@/components/status';

/**
 * Pointing this deployment at an identity provider, in the order that is safe.
 *
 * **Activate is unreachable until a test has passed on the document as it
 * stands.** SSO is the path every human uses, so a misconfiguration is not a
 * degraded feature — it is every operator locked out of the tool they would use
 * to fix it, during whatever incident prompted the change. So the control is
 * absent rather than disabled, and its absence is decided by the deployment's
 * own `verified` flag rather than by anything this component remembers.
 *
 * **An edit invalidates the test, and the console does not have to know that.**
 * `verified` is derived from the settings themselves, so a form that has been
 * edited but not saved shows no activate control because there is a pending
 * change; and a form that has been saved shows none because the save cleared
 * the deployment's own result. Two mechanisms, one property, and neither of
 * them is a rule this file applies.
 */

/** Where all three writes go. The console's own process, forwarding once. */
export const SSO_ENDPOINT = '/api/sso';

/** The fields a provider is described by. Order is the order they are filled in. */
export const SSO_FIELDS = [
  'provider',
  'issuer',
  'client_id',
  'authorisation_endpoint',
  'token_endpoint',
  'jwks_uri',
  'redirect_uri',
  'default_node_id',
] as const;

export type SsoField = (typeof SSO_FIELDS)[number];

export interface SsoLabels {
  readonly field: Readonly<Record<SsoField, string>>;
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
}

export interface SsoFormProps {
  /** What the deployment currently holds, field by field. */
  readonly settings: Readonly<Record<SsoField, string>>;
  readonly isActive: boolean;
  /** The deployment's own answer to "has a test passed on *these* settings". */
  readonly verified: boolean;
  readonly problems: readonly string[];
  readonly labels: SsoLabels;
}

function text(record: unknown, name: string): string {
  const found: unknown = Reflect.get(Object(record), name);
  return typeof found === 'string' ? found : '';
}

/** Configure a provider, test it, and only then let it be the way in. */
export function SsoForm({
  settings,
  isActive,
  verified,
  problems,
  labels,
}: SsoFormProps): ReactNode {
  const [values, setValues] = useState<Readonly<Record<string, string>>>({});
  const [claims, setClaims] = useState('');
  const [state, setState] = useState({
    active: isActive,
    verified,
    problems: [...problems],
  });
  const [busy, setBusy] = useState('');
  const [failure, setFailure] = useState('');
  const [tested, setTested] = useState('');

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

  /** Take the deployment's own answer, never a guess about what it became. */
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
    setTested('');
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
    setTested(
      succeeded
        ? text(answered, 'mapped_node_id') || labels.verified
        : ((Reflect.get(Object(answered), 'problems') as string[] | undefined)?.join(
            '; ',
          ) ?? labels.failed),
    );
    setState((was) => ({ ...was, verified: succeeded }));
  }

  async function makeActive(): Promise<void> {
    const answered = await ask('activate', {});
    if (answered !== null) adopt(answered);
  }

  return (
    <div data-testid="sso-form" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge status={state.active ? 'healthy' : 'disabled'} />
        <span data-testid="sso-state" className="text-meta text-muted">
          {state.active
            ? labels.active
            : state.verified
              ? labels.verified
              : labels.notVerified}
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

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {SSO_FIELDS.map((field) => (
          <Input
            key={field}
            label={labels.field[field]}
            name={field}
            value={current(field)}
            onValueChange={(next) => {
              setValues((was) => ({ ...was, [field]: next }));
            }}
          />
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3">
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

      <Input
        label={labels.claims}
        name="sso-claims"
        description={labels.claimsHelp}
        value={claims}
        onValueChange={setClaims}
      />

      <div className="flex flex-wrap items-center gap-3">
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

        {/* Absent, never disabled. A control that exists and refuses is one
            somebody presses during an incident and then reports as broken. */}
        {state.verified && !edited ? (
          <Button
            data-testid="activate-sso"
            state={busy === 'activate' ? 'loading' : 'default'}
            onClick={() => {
              void makeActive();
            }}
          >
            {busy === 'activate' ? labels.activating : labels.activate}
          </Button>
        ) : (
          <span data-testid="sso-test-first" className="text-meta text-muted">
            {edited ? labels.pendingEdit : labels.testFirst}
          </span>
        )}
      </div>

      {tested === '' ? null : (
        <span data-testid="sso-test-result" className="text-meta text-muted">
          {tested}
        </span>
      )}
      {failure === '' ? null : (
        <span data-testid="sso-failure" className="text-meta text-danger">
          {failure}
        </span>
      )}
    </div>
  );
}
