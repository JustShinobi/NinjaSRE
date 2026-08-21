'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Input } from '@/components/form';
import { cx } from '@/design/cx';
import { AlertTriangleIcon } from '@/design/icons';

/**
 * Replacing a credential — and the four things this field does not do.
 *
 * It does not render a stored secret back. There is no code path here that
 * could: the value of every field is the empty string until somebody types, and
 * it is set back to the empty string the moment the write is accepted. What the
 * screen says about an existing credential is *that there is one*, never what
 * it is, and never a masked rendering of it — a masked value in the DOM is
 * still a value in the DOM, in the accessibility tree, and in every screenshot
 * anybody takes of the page.
 *
 * It does not update. The form replaces, always, because a partial edit of a
 * credential is a credential nobody can reason about.
 *
 * It does not navigate. A native form post would put the response in the
 * address bar's history entry and leave the browser's own credential manager
 * offering to remember it; `fetch` keeps the whole exchange inside the page and
 * lets a refusal be shown against the field it is about.
 *
 * And it does not decide anything. Which fields exist, which are secret and
 * which are required all come from the vendor's own declared schema, handed in.
 * A form that knew what a vendor needs would be a second copy of the schema and
 * the one that goes stale.
 */

/** One field of a vendor's credential schema, as the deployment declares it. */
export interface CredentialFieldSpec {
  readonly name: string;
  readonly label: string;
  readonly help: string;
  readonly secret: boolean;
  readonly required: boolean;
  /**
   * The variable an operator may set instead of typing a value here.
   *
   * Shown beside the field so the two routes to one credential are visibly the
   * same credential. Empty for an integration, which declares none.
   */
  readonly environmentVariable?: string;
  /**
   * The least the vendor's own permission model has to grant this field, in
   * the vendor's own words. Absent where the deployment does not confidently
   * know the minimum — never a guess, because a guessed scope is a permission
   * an operator pastes into the vendor's own console and finds wrong during an
   * incident rather than before one.
   */
  readonly minScope?: string;
  /** A step-by-step guide for obtaining this field's value. Absent is ordinary. */
  readonly guideUrl?: string;
}

/** What sits under the input: the field's own help, and where else it can come from. */
function describe(field: CredentialFieldSpec): string {
  const variable = field.environmentVariable ?? '';
  if (variable === '') return field.help;
  const alternative = `Or set ${variable} in the deployment's environment.`;
  return field.help === '' ? alternative : `${field.help} ${alternative}`;
}

export interface CredentialLabels {
  readonly submit: string;
  readonly sending: string;
  readonly stored: string;
  readonly absent: string;
  readonly whereToGetIt: string;
  readonly required: string;
  readonly saved: string;
  readonly refused: string;
  readonly unreachable: string;
  /** What precedes a field's own minimum permission, when it declares one. */
  readonly minScope: string;
  /** What a field's own step-by-step guide link is called, when it has one. */
  readonly guide: string;
}

export interface CredentialFieldProps {
  /** The integration or provider this credential is for. */
  readonly integration: string;
  readonly fields: readonly CredentialFieldSpec[];
  /** Where a person gets this credential, shown beside the fields. */
  readonly whereToGetIt?: string;
  readonly labels: CredentialLabels;
  /** Called once the deployment has accepted the write. */
  readonly onStored?: (integration: string) => void;
}

/** Where a credential is written. The console's own process, forwarding once. */
export const CREDENTIAL_ENDPOINT = '/api/credential';

/** What a write did, in the words the caller renders. */
type Result = { readonly role: 'success' | 'danger'; readonly message: string } | null;

/** A write-only credential form, generated from the vendor's own schema. */
export function CredentialField({
  integration,
  fields,
  whereToGetIt = '',
  labels,
  onStored,
}: CredentialFieldProps): ReactNode {
  // Never seeded from anything. The only values this ever holds are ones
  // somebody has just typed, and they are dropped as soon as they are accepted.
  const [values, setValues] = useState<Readonly<Record<string, string>>>({});
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<Result>(null);

  const missing = fields.some(
    (field) => field.required && (values[field.name] ?? '').trim() === '',
  );

  async function store(): Promise<void> {
    setSending(true);
    setResult(null);
    let answer: Response;
    try {
      answer = await fetch(CREDENTIAL_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ integration, values }),
      });
    } catch {
      setSending(false);
      setResult({ role: 'danger', message: labels.unreachable });
      return;
    }
    const written: unknown = await answer.json().catch(() => ({}));
    setSending(false);
    if (answer.ok) {
      // Dropped here rather than left for the next render. What was typed has
      // reached the vault, and holding it any longer is holding it for nothing.
      setValues({});
      setResult({ role: 'success', message: labels.saved });
      onStored?.(integration);
      return;
    }
    const reason: unknown = Reflect.get(Object(written), 'reason');
    const reachable = Reflect.get(Object(written), 'reachable') !== false;
    setResult({
      role: 'danger',
      message: reachable
        ? `${labels.refused} ${typeof reason === 'string' ? reason : ''}`.trim()
        : labels.unreachable,
    });
  }

  return (
    <div
      data-testid="credential"
      data-integration={integration}
      className="flex flex-col gap-3"
    >
      {fields.length === 0 ? (
        <p className="text-meta text-muted">{labels.absent}</p>
      ) : (
        fields.map((field) => (
          <div key={field.name} className="flex flex-col gap-1">
            <Input
              label={field.label === '' ? field.name : field.label}
              name={field.name}
              // A secret is a password field with the browser's own memory turned
              // off. An operations credential offered back by autofill on a
              // shared machine is the failure this one attribute prevents.
              type={field.secret ? 'password' : 'text'}
              autoComplete={field.secret ? 'off' : undefined}
              {...(describe(field) === '' ? {} : { description: describe(field) })}
              value={values[field.name] ?? ''}
              onValueChange={(value) => {
                setValues((held) => ({ ...held, [field.name]: value }));
              }}
            />
            {field.minScope === undefined || field.minScope === '' ? null : (
              <p className="text-meta text-muted" data-testid="credential-field-scope">
                {labels.minScope} <code>{field.minScope}</code>
              </p>
            )}
            {field.guideUrl === undefined || field.guideUrl === '' ? null : (
              <a
                href={field.guideUrl}
                target="_blank"
                rel="noreferrer"
                className="text-meta text-accent underline underline-offset-2 motion-hover hover:opacity-80"
                data-testid="credential-field-guide"
              >
                {labels.guide}
              </a>
            )}
          </div>
        ))
      )}

      {whereToGetIt === '' ? null : (
        <p className="text-meta text-muted" data-testid="where-to-get-it">
          {labels.whereToGetIt} {whereToGetIt}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="primary"
          data-testid="store-credential"
          state={sending ? 'loading' : missing ? 'disabled' : 'default'}
          onClick={() => {
            void store();
          }}
        >
          {sending ? labels.sending : labels.submit}
        </Button>
        {missing ? (
          <span className="text-meta text-muted">{labels.required}</span>
        ) : null}
        <span className="text-meta text-muted">{labels.stored}</span>
      </div>

      {result === null ? null : (
        // Boxed and iconed rather than a bare coloured line, and `alert`
        // rather than `status` for a refusal — the same fix the model step's
        // own outcome needed, for the same reason: colour was the only
        // carrier telling a refusal apart from a write that worked.
        <p
          role={result.role === 'success' ? 'status' : 'alert'}
          data-testid="credential-result"
          className={cx(
            'flex items-center gap-2 rounded-2 edge px-3 py-2 text-meta',
            result.role === 'success'
              ? 'bg-success-bg text-success border-success'
              : 'bg-danger-bg text-danger border-danger',
          )}
        >
          {result.role === 'success' ? null : (
            <span aria-hidden="true">
              <AlertTriangleIcon />
            </span>
          )}
          {result.message}
        </p>
      )}
    </div>
  );
}
