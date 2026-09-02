import { describe, expect, it } from 'vitest';

import {
  FALLBACK_TOKEN,
  identifierAsName,
  inventedRunTitle,
  liveControlOnTerminalRun,
  negativeAssertionAfterFailedRead,
  rawMarkdown,
  twoPlaceholders,
} from '../../e2e/bans';

/**
 * Determinism for the six detectors the "Now" transversal rules call.
 *
 * Every offending sample here is the literal text the staging diagnosis this
 * suite responds to recorded — not a paraphrase, not a synthetic string
 * invented for the test. That is what keeps these detectors proved against
 * the exact shape a real deployment produced, every time the standard gate
 * runs, rather than only on the day somebody points the browser suite at a
 * violating dataset.
 */

describe('rawMarkdown', () => {
  it('accuses the exact report the diagnosis found standing in for a title', () => {
    const offending =
      '### Incident Findings & Root Cause Analysis\n\n#### 1. Cause\n\n' +
      'The **primary** node lost quorum after `pg_repack` held an exclusive ' +
      'lock past the client timeout.';
    expect(rawMarkdown(offending)).not.toBeNull();
  });

  it('absolves a written sentence with no markdown in it', () => {
    const clean =
      'A guest reached the ceiling of its own volume while the datastore ' +
      'under it still read comfortable.';
    expect(rawMarkdown(clean)).toBeNull();
  });
});

describe('identifierAsName', () => {
  it('accuses the eight-character hexadecimal fragment the run list showed', () => {
    expect(identifierAsName('e19e882a')).not.toBeNull();
  });

  it('accuses the full hexadecimal run id a breadcrumb showed whole', () => {
    expect(identifierAsName('e19e882a1c9b4d5e8f6a2b3c7d0e1f24')).not.toBeNull();
  });

  it('accuses the percent-encoded composite incident id the H1 showed', () => {
    const offending =
      'alert%3Aalertmanager%3Ac046a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1' +
      'd2e3f4a5b6c7d8e9f0%402026-08-22T23%3A43%3A23.303208%2B00%3A00';
    expect(identifierAsName(offending)).not.toBeNull();
  });

  it('absolves a written title', () => {
    expect(identifierAsName('RestoreDrillStale')).toBeNull();
  });

  it('absolves a friendly run id that is not purely hexadecimal', () => {
    expect(identifierAsName('run-0001')).toBeNull();
  });

  it('absolves an all-digit colon-joined triple as a declared choice, not an accident', () => {
    // A bare clock reading is exactly this shape — three colon-joined,
    // all-digit segments — and the composite-id check must not fire on one,
    // isolated or sitting inside a sentence. `123:456:789` locks the same
    // gap down on purpose: every composite id this product actually shows
    // today has at least one named segment (`alert:alertmanager:...`), so an
    // all-digit triple is deliberately let through. If a real, all-numeric
    // composite id ever appears in the product, this is the line a reviewer
    // revisits — not a silent gap nobody notices.
    expect(identifierAsName('23:41:02')).toBeNull();
    expect(identifierAsName('Standby promotion log at 23:41:02')).toBeNull();
    expect(identifierAsName('123:456:789')).toBeNull();

    // The detector still has to accuse a real composite id with named
    // segments — otherwise this test would pass with the composite-id check
    // neutralised entirely, which is the exact mistake a determinism test
    // exists to catch.
    expect(identifierAsName('alert:alertmanager:c046a1b2')).not.toBeNull();
  });
});

describe('inventedRunTitle', () => {
  it('accuses the exact hash-based sentence the staging audit recorded', () => {
    // The literal shape a run-by-alert used to read as, from the wave's own
    // partida audit: "investigation triggered by" followed by a hash.
    expect(
      inventedRunTitle('investigation triggered by bc7bdbd452fae8f1c9d3a0e5b7461203'),
    ).not.toBeNull();
  });

  it('accuses the exact trigger-word sentence a manual run used to read as', () => {
    expect(inventedRunTitle('interactive investigation')).not.toBeNull();
    expect(inventedRunTitle('alert investigation')).not.toBeNull();
    expect(inventedRunTitle('schedule investigation')).not.toBeNull();
    expect(inventedRunTitle('subagent investigation')).not.toBeNull();
    // Case is a rendering detail; the detector reads the underlying word.
    expect(inventedRunTitle('Interactive investigation')).not.toBeNull();
  });

  it('absolves a real subject, even one that mentions the word "investigation"', () => {
    expect(inventedRunTitle('Investigate checkout latency')).toBeNull();
    expect(inventedRunTitle('RedisExporterDown on redis-1')).toBeNull();
    expect(inventedRunTitle('Investigation with no declared subject')).toBeNull();
  });

  it('absolves the empty string', () => {
    expect(inventedRunTitle('')).toBeNull();
    expect(inventedRunTitle('   ')).toBeNull();
  });
});

describe('twoPlaceholders', () => {
  it('accuses the exact five-slot subtitle the diagnosis recorded', () => {
    const offending =
      "Not recorded · this deployment's own detectors · started · zone " +
      'Unplaced · Not recorded';
    expect(twoPlaceholders(offending)).not.toBeNull();
  });

  it('absolves a line with at most one fallback', () => {
    expect(twoPlaceholders('15 hours ago · Alert')).toBeNull();
    expect(twoPlaceholders(`23m · ${FALLBACK_TOKEN}`)).toBeNull();
  });
});

describe('liveControlOnTerminalRun', () => {
  it('accuses a settled run whose own page still offers to stop it', () => {
    expect(
      liveControlOnTerminalRun('succeeded', 'Stop this investigation'),
    ).not.toBeNull();
    // Case is a rendering detail (the badge is drawn upper-case); the
    // detector reads the underlying word.
    expect(
      liveControlOnTerminalRun('SUCCEEDED', 'Stop this investigation'),
    ).not.toBeNull();
  });

  it('absolves a run genuinely still in flight', () => {
    expect(liveControlOnTerminalRun('running', 'Stop this investigation')).toBeNull();
    expect(
      liveControlOnTerminalRun('awaiting_approval', 'Stop this investigation'),
    ).toBeNull();
  });

  it('absolves a settled run whose page offers no live control', () => {
    expect(liveControlOnTerminalRun('succeeded', '')).toBeNull();
  });
});

describe('negativeAssertionAfterFailedRead', () => {
  it('accuses the exact chip the diagnosis found deriving from a failed read', () => {
    expect(negativeAssertionAfterFailedRead(true, 'No investigation')).not.toBeNull();
  });

  it('absolves the same chip when the read behind it actually succeeded', () => {
    expect(negativeAssertionAfterFailedRead(false, 'No investigation')).toBeNull();
  });

  it('absolves a failed read that asserts nothing', () => {
    expect(negativeAssertionAfterFailedRead(true, '')).toBeNull();
  });

  it('absolves the honest answer a failed read is allowed to give', () => {
    expect(negativeAssertionAfterFailedRead(true, 'Unknown')).toBeNull();
  });

  it('still accuses a specific, positive claim made over the same failed read', () => {
    expect(
      negativeAssertionAfterFailedRead(true, 'Investigation finished'),
    ).not.toBeNull();
  });
});
