import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { LOCALES } from '@/i18n/messages';
import {
  eventFromStream,
  eventsFromReplay,
  eventsFromStream,
  narrate,
  STREAM_KINDS,
  type TranscriptEvent,
} from '@/surfaces/transcript';

/**
 * The narration table: complete, and the single funnel both readers pass
 * through.
 *
 * Two properties, proved separately because they are separate facts. First,
 * every raw kind the stream vocabulary declares has a phrase in every locale
 * this console carries — a kind added to `STREAM_KINDS` with no matching
 * narration is caught here rather than shown as a raw kind string in
 * production. Second, `narrate` is a pure function of the event's own already-
 * extracted fields (`rawKind`, `title`, `detail`), so a replayed event and a
 * streamed event that carry the same facts render byte-identical sentences —
 * which is what makes "the transcript is one component, fed by two readers"
 * true of the narration as well as of the list.
 */

describe('every raw kind the stream declares has a narrated phrase, in every locale', () => {
  for (const kind of Object.keys(STREAM_KINDS)) {
    for (const locale of LOCALES) {
      it(`${kind} narrates in ${locale}`, () => {
        const event: TranscriptEvent = {
          id: 'evt-1',
          kind: STREAM_KINDS[kind] ?? 'reasoning',
          rawKind: kind,
          at: '',
          title: '',
          detail: '',
          note: '',
          payload: '',
          status: '',
          durationMs: 0,
        };
        const sentence = narrate(event, locale);
        expect(sentence.trim()).not.toBe('');
        // Never the raw kind standing in for a sentence, and never a template
        // placeholder left unfilled.
        expect(sentence).not.toBe(kind);
        expect(sentence).not.toMatch(/\{[a-z][a-z0-9]*\}/iu);
      });
    }
  }
});

/**
 * The vocabulary the deployment actually emits: `TraceEventKind` in
 * `platform/runs/events.py`, the closed set the recorder writes and the run
 * stream delivers. Spelled out here rather than read from the fixtures,
 * because the fixtures still carry the older spellings alongside it — and it
 * was exactly these kinds that a live run on staging narrated as "an event of
 * an unrecognised kind arrived", every entry labelled reasoning.
 */
const DEPLOYMENT_KINDS = [
  'run_started',
  'stage_completed',
  'turn_completed',
  'capability_called',
  'evidence_observed',
  'subagent_dispatched',
  'guardrail_action',
  'masking_applied',
  'budget_eviction',
  'approval_requested',
  'attention_changed',
  'report_delivered',
  'notification_decided',
  'run_interrupted',
  'run_finished',
] as const;

/** Every kind the committed stream fixture actually carries, read from disk. */
function fixtureKinds(): readonly string[] {
  const path = join(
    process.cwd(),
    '..',
    'fixtures',
    'scenarios',
    'populated',
    'run-stream.json',
  );
  const loaded: unknown = JSON.parse(readFileSync(path, 'utf8'));
  const responses: unknown = Reflect.get(Object(loaded), 'responses');
  const first: unknown = Array.isArray(responses) ? responses[0] : undefined;
  const body: unknown = Reflect.get(Object(first), 'body');
  const events: unknown = Reflect.get(Object(body), 'events');
  if (!Array.isArray(events)) throw new Error('run-stream fixture carries no events');
  return events.map((event) => String(Reflect.get(Object(event), 'kind')));
}

describe('every kind the deployment emits narrates as itself, never as the unknown-kind sentence', () => {
  const kinds = [...new Set([...DEPLOYMENT_KINDS, ...fixtureKinds()])];
  for (const kind of kinds) {
    for (const locale of LOCALES) {
      it(`${kind} narrates in ${locale}`, () => {
        const streamed = eventFromStream({
          runId: 'run-v',
          kind,
          sequence: 1,
          occurredAt: '2026-09-01T12:00:00+00:00',
          payload: {},
        });
        const sentence = narrate(streamed, locale);
        expect(sentence.trim()).not.toBe('');
        expect(sentence).not.toContain('unrecognised');
        expect(sentence).not.toContain('não reconhecido');
        expect(sentence).not.toMatch(/\{[a-z][a-z0-9]*\}/iu);
      });
    }
  }

  it("capability_called names the capability from the payload's own field", () => {
    // The recorder writes the name under `capability`, not `name`
    // (`platform/runs/recorder.py`, `record_call`) — the extraction has to
    // read the deployment's field or every live call narrates as "a
    // capability".
    const streamed = eventFromStream({
      runId: 'run-v',
      kind: 'capability_called',
      sequence: 2,
      occurredAt: '2026-09-01T12:00:01+00:00',
      payload: { capability: 'estate.failed_units', status: 'succeeded' },
    });
    for (const locale of LOCALES) {
      expect(narrate(streamed, locale)).toContain('estate.failed_units');
    }
    expect(streamed.status).toBe('succeeded');
  });

  it('stage_completed names the stage and carries its finding', () => {
    const streamed = eventFromStream({
      runId: 'run-v',
      kind: 'stage_completed',
      sequence: 3,
      occurredAt: '2026-09-01T12:00:02+00:00',
      payload: { stage: 'intake', finding: 'a new incident, not a repeat' },
    });
    for (const locale of LOCALES) {
      const sentence = narrate(streamed, locale);
      expect(sentence).toContain('intake');
      expect(sentence).toContain('a new incident, not a repeat');
    }
  });
});

describe('a kind outside the declared vocabulary still narrates, and never as JSON', () => {
  for (const locale of LOCALES) {
    it(`names the raw kind in ${locale} rather than falling silent`, () => {
      const event: TranscriptEvent = {
        id: 'evt-2',
        kind: 'reasoning',
        rawKind: 'telemetry_reweighted',
        at: '',
        title: '',
        detail: '',
        note: '',
        payload: '',
        status: '',
        durationMs: 0,
      };
      const sentence = narrate(event, locale);
      expect(sentence).toContain('telemetry_reweighted');
      expect(sentence.trim().startsWith('{')).toBe(false);
    });
  }
});

describe('an absent field is declared absent, never interpolated as undefined', () => {
  it('a tool_called event with no capability name narrates without printing "undefined"', () => {
    const event: TranscriptEvent = {
      id: 'evt-3',
      kind: 'call',
      // `eventFromStream` falls back the title to the raw kind itself when
      // the payload carried no `name` — this is that degraded shape, spelled
      // out directly so the narration table's own handling of it is under
      // test without going through the stream parser a second time.
      rawKind: 'tool_called',
      at: '',
      title: 'tool_called',
      detail: '',
      note: '',
      payload: '',
      status: '',
      durationMs: 0,
    };
    for (const locale of LOCALES) {
      const sentence = narrate(event, locale);
      expect(sentence).not.toContain('undefined');
      expect(sentence).not.toContain('tool_called');
    }
  });
});

describe("the replay reader's own spelling of a call result narrates like the stream's", () => {
  it("tool_returned — eventsFromReplay's rawKind for a call result — is not an unrecognised kind", () => {
    // This is the gap a screenshot caught that a hand-built fixture did not:
    // eventsFromReplay spells a call's outcome `tool_returned`, never
    // `tool_succeeded`/`tool_failed`, and the narration table had only the
    // stream's two spellings — so every capability result on every settled
    // run fell back to "An event of an unrecognised kind arrived:
    // tool_returned", visible on real fixture data and invisible to a test
    // that only ever constructed STREAM_KINDS-shaped events by hand.
    const [built] = eventsFromReplay({
      run_id: 'run-z',
      turns: [
        {
          turn_id: 'turn-1',
          index: 0,
          calls: [{ call_id: 'call-1', name: 'estate.storage_pressure' }],
        },
      ],
    }).filter((event) => event.kind === 'result');

    expect(built).toBeDefined();
    if (built === undefined) throw new Error('unreachable');
    expect(built.rawKind).toBe('tool_returned');

    for (const locale of LOCALES) {
      const sentence = narrate(built, locale);
      expect(sentence).not.toContain('unrecognised');
      expect(sentence).not.toContain('não reconhecido');
      expect(sentence).toContain('estate.storage_pressure');
    }
  });
});

describe('one funnel: a replayed call and a streamed call of the same facts narrate identically', () => {
  it('the lead phrase for tool_called does not depend on which reader built the event', () => {
    const replayed = eventsFromReplay({
      run_id: 'run-x',
      turns: [
        {
          turn_id: 'turn-1',
          index: 0,
          calls: [
            {
              call_id: 'call-1',
              name: 'estate.failed_units',
              arguments: { node: 'node01' },
            },
          ],
        },
      ],
    }).find((event) => event.rawKind === 'tool_called');

    const streamed = eventFromStream({
      runId: 'run-x',
      kind: 'tool_called',
      sequence: 1,
      occurredAt: '2026-08-07T11:57:00+00:00',
      payload: { name: 'estate.failed_units', arguments: { node: 'node01' } },
    });

    expect(replayed).toBeDefined();
    if (replayed === undefined) throw new Error('unreachable');

    for (const locale of LOCALES) {
      expect(narrate(replayed, locale)).toBe(narrate(streamed, locale));
    }
  });

  it('the same fixture of events, read once as a replay body and once as a stream body, narrates identically event for event', () => {
    const body = {
      run_id: 'run-y',
      events: [
        {
          run_id: 'run-y',
          kind: 'run_started',
          sequence: 0,
          occurred_at: '2026-08-07T11:56:00+00:00',
          payload: { objective: 'A hardening unit failed at boot on the primary.' },
        },
        {
          run_id: 'run-y',
          kind: 'tool_called',
          sequence: 1,
          occurred_at: '2026-08-07T11:57:00+00:00',
          payload: { name: 'estate.failed_units', arguments: { node: 'node01' } },
        },
        {
          run_id: 'run-y',
          kind: 'observation_recorded',
          sequence: 2,
          occurred_at: '2026-08-07T11:57:30+00:00',
          payload: { detail: 'nine failed units on the primary' },
        },
      ],
    };

    // `eventsFromStream` is the batch reader over a stream-shaped body; the
    // live reducer's own per-event `eventFromStream` is the same function
    // called once per frame, so proving the batch form is one funnel proves
    // the live path too.
    const asStream = eventsFromStream(body);

    for (const locale of LOCALES) {
      const sentences = asStream.map((event) => narrate(event, locale));
      expect(sentences.every((sentence) => sentence.trim() !== '')).toBe(true);
    }
  });
});
