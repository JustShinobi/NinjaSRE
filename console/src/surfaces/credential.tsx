'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Input } from '@/components/form';
import { apiOrigin } from '@/lib/api';

/**
 * Replacing an integration's credential — and the three things this field does
 * not do.
 *
 * It does not render a stored secret back. There is no code path here that could:
 * the value shown is always the empty string until somebody types, and what the
 * screen says about an existing credential is *that there is one*, never what it
 * is. A field pre-filled with a secret is a secret in the document, in the
 * accessibility tree, and in every screenshot anybody takes of the page.
 *
 * It does not update. The form replaces, always, because a partial edit of a
 * credential is a credential nobody can reason about.
 *
 * And it posts to the **API origin** rather than to the console's. The console is
 * a client of the deployment; a secret that went through the console's own
 * process would be a secret in a second place, and the second place is the one
 * nobody remembers to audit.
 */

export interface CredentialLabels {
  readonly title: string;
  readonly replace: string;
  readonly stored: string;
  readonly absent: string;
  readonly verify: string;
}

export interface CredentialFieldProps {
  readonly integration: string;
  /** The credential fields this integration declares. */
  readonly required: readonly string[];
  readonly labels: CredentialLabels;
}

/** A write-only credential field, posting to the deployment. */
export function CredentialField({
  integration,
  required,
  labels,
}: CredentialFieldProps): ReactNode {
  // Never seeded from anything. The only value this ever holds is one somebody
  // has just typed into it.
  const [value, setValue] = useState('');

  return (
    <form
      // The API origin, not this one.
      action={`${apiOrigin()}/v1/integrations/${encodeURIComponent(integration)}/verify`}
      method="post"
      data-testid="credential"
      data-integration={integration}
      className="flex flex-wrap items-end gap-3"
    >
      {required.map((field) => (
        <Input
          key={field}
          label={field}
          name={field}
          type="password"
          value={value}
          onValueChange={setValue}
        />
      ))}
      <p className="text-meta text-muted">
        {required.length === 0 ? labels.absent : labels.stored}
      </p>
      <Button variant="secondary" type="submit" data-testid="verify">
        {labels.verify}
      </Button>
    </form>
  );
}
