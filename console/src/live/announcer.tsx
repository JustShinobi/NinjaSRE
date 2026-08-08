'use client';

import type { ReactNode } from 'react';

import { Toast } from '@/components/feedback';
import { message, type Locale } from '@/i18n/messages';
import type { Outcome } from './outcomes';

/**
 * Where announced outcomes are shown.
 *
 * Each one names where the same thing is written down, and the type will not
 * let one exist without that. This component is only the announcement — the
 * record is the transcript, the audit view or the notification centre, and it
 * is there whether anybody read the toast or not.
 */
export function Announcer({
  locale,
  outcomes,
  onDismiss,
}: {
  readonly locale: Locale;
  readonly outcomes: readonly Outcome[];
  readonly onDismiss: (id: string) => void;
}): ReactNode {
  if (outcomes.length === 0) return null;
  return (
    <div data-testid="outcomes" className="flex flex-col gap-2">
      {outcomes.map((outcome) => (
        <Toast
          key={outcome.id}
          role={outcome.role}
          message={outcome.message}
          recordedAt={outcome.recordedAt}
          dismissLabel={message(locale, 'live.outcome.dismiss')}
          onDismiss={() => {
            onDismiss(outcome.id);
          }}
        />
      ))}
    </div>
  );
}
