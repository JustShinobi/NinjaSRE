import { message, type Locale, type MessageKey } from '@/i18n/messages';

/**
 * Turning what the deployment said into something the person reading it can do.
 *
 * One rule, and it is the whole module: **no exception message from the gateway
 * is ever a headline in this console.** It reached four surfaces at once — the
 * dashboard band, the run list, the run detail, and the notification bell all
 * rendered `InvestigatorNotConfigured: ... Set NINJASRE_INVESTIGATOR to
 * 'module:factory'` verbatim. That sentence is addressed to whoever deploys the
 * thing; it was being shown to whoever opened the console, on a screen that
 * has a button leading to the fix.
 *
 * Three things follow from that, and each is a decision rather than a detail.
 *
 * **The raw text is kept, not discarded.** It moves behind "technical detail",
 * because the person who *does* deploy the thing opens the same console, and a
 * translation that destroyed the original would make this module a downgrade
 * for them.
 *
 * **An unrecognised exception is still not printed as a headline.** The
 * recognised list will always be shorter than the set of things that can go
 * wrong, and a layer that only helped with the four failures somebody thought
 * of would leave the fifth looking exactly as it does today.
 *
 * **A sentence a person wrote survives untouched.** Most run summaries are
 * summaries. Turning those into "the investigation failed" would cost more
 * than the problem this solves, so the test for "is this an exception" is
 * deliberately narrow: a leading identifier in `SomeName:` form and nothing
 * else.
 */

/** What the console can say about one failure. */
export interface FailureReading {
  /** Whether this is a failure the console has a translation for. */
  readonly known: boolean;
  /** The headline. Never an exception message, and never a class name. */
  readonly title: string;
  /** What to do about it, in a sentence. Empty when there is nothing to say. */
  readonly action: string;
  /** Where the fix lives, or `''` where no screen in this console fixes it. */
  readonly href: string;
  /** The deployment's own words, kept for whoever wants them. */
  readonly technical: string;
}

/** One failure this console recognises, and what it does about it. */
interface KnownFailure {
  /** What identifies it in the deployment's text. Matched case-sensitively. */
  readonly marker: string;
  readonly title: MessageKey;
  readonly action: MessageKey;
  /**
   * Where the fix lives. `''` where no screen here fixes it — a database that
   * is down has no button, and one that led somewhere unhelpful would be worse
   * than none.
   */
  readonly href: string;
}

/**
 * The failures worth naming, most specific first.
 *
 * Ordered rather than keyed, because one text can carry two markers and the
 * first match should be the one that names the operator's actual next step.
 */
const KNOWN: readonly KnownFailure[] = [
  {
    marker: 'InvestigatorNotConfigured',
    title: 'failure.investigator.title',
    action: 'failure.investigator.action',
    href: '/first-run?step=model',
  },
  {
    marker: 'CredentialNotConfigured',
    title: 'failure.credential.title',
    action: 'failure.credential.action',
    href: '/first-run?step=credential',
  },
  {
    marker: 'VaultKeyMismatch',
    title: 'failure.vaultKey.title',
    action: 'failure.vaultKey.action',
    href: '/first-run?step=credential',
  },
  {
    marker: 'StoreUnavailable',
    title: 'failure.store.title',
    action: 'failure.store.action',
    href: '',
  },
  {
    marker: 'MigrationsPending',
    title: 'failure.migrations.title',
    action: 'failure.migrations.action',
    href: '',
  },
];

/**
 * Whether `text` reads as a raised exception rather than as a written sentence.
 *
 * Narrow on purpose: an identifier of at least two words in camel case,
 * followed by a colon, at the very start. `ZeroDivisionError: ...` matches;
 * "The checkout database ran out of connections at 02:14." does not, and
 * neither does anything with a space before the colon.
 */
function looksRaised(text: string): boolean {
  return /^[A-Z][A-Za-z0-9]*[a-z][A-Z][A-Za-z0-9]*:/.test(text);
}

/**
 * What to tell somebody about `raw`, in `locale`.
 *
 * `raw` is whatever the deployment put in the field — a run's summary, an error
 * body, a status line. Empty in, empty out: a missing summary is nothing to say
 * rather than a failure to report.
 */
export function readFailure(raw: string, locale: Locale): FailureReading {
  const text = raw.trim();
  if (text === '') {
    return { known: false, title: '', action: '', href: '', technical: '' };
  }

  const found = KNOWN.find((failure) => text.includes(failure.marker));
  if (found !== undefined) {
    return {
      known: true,
      title: message(locale, found.title),
      action: message(locale, found.action),
      href: found.href,
      technical: raw,
    };
  }

  if (looksRaised(text)) {
    return {
      known: false,
      title: message(locale, 'failure.unknown.title'),
      action: message(locale, 'failure.unknown.action'),
      href: '',
      technical: raw,
    };
  }

  // A sentence somebody wrote for a person. It passes through unedited, and
  // there is no technical detail to offer because this *is* the detail.
  return { known: false, title: raw, action: '', href: '', technical: '' };
}
