'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Input } from '@/components/form';
import { AccountStateChip, PrincipalKindChip } from '@/components/status';
import type { Locale } from '@/i18n/messages';

/**
 * Members & roles' primary action: a person, created without leaving the
 * page.
 *
 * **Absence, not disablement, is the caller's job.** `canWrite` decides
 * whether the form exists at all, the same rule `GrantPanel` already follows
 * for the write half of this exact screen — a viewer who may only read
 * identity sees who exists and nothing that invites them to add to it.
 *
 * **The created person renders through the same two chips as everyone
 * else.** A creation's answer is turned into the same `PrincipalRow` shape
 * the caller already resolved every other row into, and the row is appended
 * to the list rather than replacing it wholesale — so `PrincipalKindChip` and
 * `AccountStateChip` are the only place either fact is ever worded, for a row
 * this panel started with or one it just created.
 *
 * **Nothing this form sends is ever echoed back.** The gateway's own answer
 * to a creation carries no password field to begin with; this panel clears
 * the one it collected the moment the request settles, success or not, so a
 * password that was just typed does not linger in a form nobody is looking
 * at any more.
 */

export const PRINCIPAL_ENDPOINT = '/api/principals';

/** One row of the Principals list: what every other row already resolved, plus what a creation answers with. */
export interface PrincipalRow {
  readonly userId: string;
  readonly displayName: string;
  /** The line under the name — an email, or the deployment's own words for not recording one. */
  readonly identity: string;
  /** `/identity/principals`'s own `kind`, resolved to a label by `PrincipalKindChip`. */
  readonly kind: string;
  /** Whether this principal may currently sign in, resolved to a label by `AccountStateChip`. */
  readonly isActive: boolean;
}

export interface PrincipalsLabels {
  readonly displayName: string;
  readonly email: string;
  readonly password: string;
  readonly passwordHelp: string;
  readonly create: string;
  readonly creating: string;
  readonly failed: string;
  readonly unreachable: string;
}

export interface PrincipalsPanelProps {
  readonly principals: readonly PrincipalRow[];
  readonly canWrite: boolean;
  readonly locale: Locale;
  readonly labels: PrincipalsLabels;
}

interface Answered {
  readonly reachable: boolean;
  readonly ok: boolean;
  readonly reason: string;
  readonly answer: unknown;
}

/** One field of `record`, read as a string, and the empty string when it is not one. */
function text(record: unknown, name: string): string {
  const found: unknown = Reflect.get(Object(record), name);
  return typeof found === 'string' ? found : '';
}

/** Whether `record.name` is exactly `true`. Never truthiness. */
function flag(record: unknown, name: string): boolean {
  return Reflect.get(Object(record), name) === true;
}

async function ask(payload: unknown): Promise<Answered> {
  let response: Response;
  try {
    response = await fetch(PRINCIPAL_ENDPOINT, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch {
    return { reachable: false, ok: false, reason: '', answer: undefined };
  }
  const body: unknown = await response.json().catch(() => ({}));
  const reason: unknown = Reflect.get(Object(body), 'reason');
  return {
    reachable: true,
    ok: response.ok,
    reason: typeof reason === 'string' ? reason : '',
    answer: Reflect.get(Object(body), 'answer'),
  };
}

/** Everyone who exists, and — for whoever may write identity — the means to add one more. */
export function PrincipalsPanel({
  principals,
  canWrite,
  locale,
  labels,
}: PrincipalsPanelProps): ReactNode {
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [added, setAdded] = useState<readonly PrincipalRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState('');

  const rows = [...principals, ...added];
  const ready =
    displayName.trim() !== '' && email.trim() !== '' && password.trim() !== '';

  async function create(): Promise<void> {
    setBusy(true);
    setFailure('');
    const answered = await ask({
      email: email.trim(),
      display_name: displayName.trim(),
      password,
    });
    setBusy(false);
    setPassword('');
    if (!answered.reachable) {
      setFailure(labels.unreachable);
      return;
    }
    if (!answered.ok) {
      setFailure(answered.reason === '' ? labels.failed : answered.reason);
      return;
    }
    const userId = text(answered.answer, 'user_id');
    if (userId !== '') {
      setAdded((was) => [
        ...was,
        {
          userId,
          displayName: text(answered.answer, 'display_name'),
          identity: text(answered.answer, 'email'),
          kind: text(answered.answer, 'kind'),
          isActive: flag(answered.answer, 'is_active'),
        },
      ]);
      setDisplayName('');
      setEmail('');
    }
  }

  return (
    <div data-testid="principals-panel" className="flex flex-col gap-3">
      <ul className="flex flex-col gap-2 text-small">
        {rows.map((person) => (
          <li
            key={person.userId}
            data-testid="principal"
            className="flex items-center gap-3 min-w-0"
          >
            <span className="truncate">{person.displayName}</span>
            <span className="text-meta text-muted truncate">{person.identity}</span>
            <span className="ml-auto flex items-center gap-2">
              <PrincipalKindChip locale={locale} kind={person.kind} />
              <AccountStateChip locale={locale} active={person.isActive} />
            </span>
          </li>
        ))}
      </ul>

      {!canWrite ? null : (
        <div className="flex flex-wrap items-end gap-3">
          <Input
            label={labels.displayName}
            name="person-display-name"
            value={displayName}
            onValueChange={setDisplayName}
          />
          <Input
            label={labels.email}
            name="person-email"
            value={email}
            onValueChange={setEmail}
          />
          <Input
            label={labels.password}
            name="person-password"
            // A secret is a password field with the browser's own memory
            // turned off — the same reason `credential.tsx`'s own secret
            // fields carry both, even though this one is typed by an
            // administrator rather than pasted from a vendor.
            type="password"
            autoComplete="off"
            description={labels.passwordHelp}
            value={password}
            onValueChange={setPassword}
          />
          <Button
            variant="primary"
            data-testid="create-person"
            state={busy ? 'loading' : ready ? 'default' : 'disabled'}
            onClick={() => {
              void create();
            }}
          >
            {busy ? labels.creating : labels.create}
          </Button>
        </div>
      )}

      {failure === '' ? null : (
        <p data-testid="principal-create-failure" className="text-meta text-danger">
          {failure}
        </p>
      )}
    </div>
  );
}
