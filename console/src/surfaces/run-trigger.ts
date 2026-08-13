import { message, type Locale, type MessageKey } from '@/i18n/messages';

/** The operator-facing catalogue entry for each trigger value the API emits. */
const TRIGGER_MESSAGES: Readonly<Record<string, MessageKey>> = {
  alert: 'runs.trigger.alert',
  chat: 'runs.trigger.manual',
  console: 'runs.trigger.manual',
  interactive: 'runs.trigger.manual',
  manual: 'runs.trigger.manual',
  schedule: 'runs.trigger.scheduled',
  subagent: 'runs.trigger.specialist',
  webhook: 'runs.trigger.alert',
};

/** A readable fallback for a future trigger value absent from the catalogue. */
function fallbackLabel(raw: string): string {
  return raw
    .trim()
    .split(/[_-]+/u)
    .filter((part) => part !== '')
    .map((part, index) =>
      index === 0
        ? `${part.charAt(0).toUpperCase()}${part.slice(1).toLowerCase()}`
        : part.toLowerCase(),
    )
    .join(' ');
}

/** The localized label for an API trigger value, without exposing its slug. */
export function triggerLabel(locale: Locale, raw: string): string {
  const key = TRIGGER_MESSAGES[raw.trim().toLowerCase()];
  if (key !== undefined) return message(locale, key);

  const fallback = fallbackLabel(raw);
  return fallback === '' ? message(locale, 'surface.none') : fallback;
}
