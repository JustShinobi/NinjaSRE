import { message, type Locale } from '@/i18n/messages';
import { formatNumber, timestamp } from '@/i18n/format';
import type { CredentialLabels } from './credential';
import type { VerifyStepLabels } from './first-run/verify';
import type { PanelLabels } from './panel';
import type { PayloadLabels, Bound } from './payload';
import type { RowListLabels } from './rows';
import type { EventTime, TranscriptLabels } from './transcript-view';
import {
  TRANSCRIPT_KINDS,
  type TranscriptEvent,
  type TranscriptKind,
} from './transcript';
import { TRANSCRIPT_WINDOW } from './transcript-view';

/**
 * The sentences the shared surface components render, from the catalogue.
 *
 * Every one of these is a string a person reads, so none of them is written in a
 * component. Gathering them here rather than at each call site is what keeps
 * twelve screens saying the same thing about the same failure — "this panel
 * could not be filled" is one sentence in one place, not twelve that drift.
 */

/** What a panel says while it loads, when it fails, and to retry. */
export function panelLabels(locale: Locale, panel: string): PanelLabels {
  return {
    loading: message(locale, 'surface.loading', { panel }),
    errorHeading: message(locale, 'surface.error.heading'),
    errorDetail: message(locale, 'surface.error.detail'),
    retry: message(locale, 'surface.error.retry'),
  };
}

/**
 * Every sentence a write-only credential form renders.
 *
 * One builder for both call sites — the catalogue's replace-this-credential and
 * the guided run's connect-this-vendor — because they are the same form doing
 * the same thing, and two sets of words for one operation is how one of them
 * ends up promising something the other does not.
 */
export function credentialLabels(locale: Locale): CredentialLabels {
  return {
    submit: message(locale, 'credential.submit'),
    sending: message(locale, 'credential.sending'),
    stored: message(locale, 'credential.stored'),
    absent: message(locale, 'credential.absent'),
    whereToGetIt: message(locale, 'credential.whereToGetIt'),
    required: message(locale, 'credential.required'),
    saved: message(locale, 'credential.saved'),
    refused: message(locale, 'firstRun.refused'),
    unreachable: message(locale, 'firstRun.unreachable'),
    minScope: message(locale, 'credential.minScope'),
    guide: message(locale, 'credential.guide'),
  };
}

/**
 * Every sentence a per-row "check it for real" control renders.
 *
 * One builder for both call sites — the guided first run's verify step and
 * the catalogue's per-integration card — for the same reason
 * `credentialLabels` is: it is the same live check against the same vendor,
 * and two sets of words for one operation is how one of them ends up
 * promising something the other does not.
 */
export function verifyLabels(locale: Locale): VerifyStepLabels {
  return {
    check: message(locale, 'firstRun.verify.check'),
    checking: message(locale, 'firstRun.verify.checking'),
    retry: message(locale, 'firstRun.verify.retry'),
    unreachable: message(locale, 'firstRun.unreachable'),
    nothing: message(locale, 'firstRun.verify.nothing'),
    remedy: message(locale, 'firstRun.verify.remedy'),
    findings: message(locale, 'firstRun.verify.findings'),
    fixProvider: message(locale, 'firstRun.verify.fix.provider'),
    fixIntegration: message(locale, 'firstRun.verify.fix.integration'),
    fullDiagnosis: message(locale, 'firstRun.verify.fullDiagnosis'),
    fullDiagnosisSummary: message(locale, 'firstRun.verify.fullDiagnosis.summary'),
  };
}

/** What a bounded payload says about its bound. */
export function payloadLabels(locale: Locale, bound: Bound): PayloadLabels {
  return {
    bounded: message(locale, 'surface.payload.bounded', {
      total: formatNumber(locale, bound.total),
      shown: formatNumber(locale, bound.shown),
    }),
    expand: message(locale, 'surface.payload.expand'),
    collapse: message(locale, 'surface.payload.collapse'),
    copy: message(locale, 'surface.payload.copy'),
    copied: message(locale, 'surface.payload.copied'),
  };
}

/** What a long list calls its caption, its sort controls and its rows' links. */
export function rowLabels(locale: Locale, caption: string): RowListLabels {
  return {
    caption,
    sortedAscending: message(locale, 'surface.sort.ascending'),
    sortedDescending: message(locale, 'surface.sort.descending'),
    open: message(locale, 'surface.open'),
  };
}

/** Every sentence the transcript renders, for one particular transcript. */
export function transcriptLabels(
  locale: Locale,
  events: readonly TranscriptEvent[],
): TranscriptLabels {
  const first = Math.max(1, events.length - TRANSCRIPT_WINDOW + 1);
  const kinds = Object.fromEntries(
    TRANSCRIPT_KINDS.map((kind) => [kind, message(locale, `transcript.kind.${kind}`)]),
  ) as Record<TranscriptKind, string>;

  return {
    kinds,
    position: message(locale, 'transcript.position', {
      first: formatNumber(locale, first),
      last: formatNumber(locale, events.length),
      total: formatNumber(locale, events.length),
    }),
    earlier: message(locale, 'transcript.earlier'),
    later: message(locale, 'transcript.later'),
    empty: message(locale, 'transcript.empty'),
    arguments: message(locale, 'transcript.arguments'),
    result: message(locale, 'transcript.result'),
    payload: payloadLabels(locale, { total: 0, shown: 0 }),
  };
}

/** Each event's instant and duration, formatted once on the server. */
export function eventTimes(
  locale: Locale,
  events: readonly TranscriptEvent[],
  now: Date,
  zone: string,
): Readonly<Record<string, EventTime>> {
  const times: Record<string, EventTime> = {};
  for (const event of events) {
    const instant =
      event.at === ''
        ? { relative: '', absolute: '', iso: '' }
        : timestamp(locale, event.at, now, zone);
    times[event.id] = {
      ...instant,
      duration:
        event.durationMs > 0
          ? message(locale, 'transcript.duration', {
              ms: formatNumber(locale, event.durationMs),
            })
          : '',
    };
  }
  return times;
}
